# A2Z MIS 360 — Disaster Recovery Runbook

This runbook covers what to do when production breaks. It assumes you
have already read the [Deployment Guide](DEPLOYMENT_GUIDE.md) and have
operator access to the A2Z hosts.

## Recovery objectives

| Metric | Target |
|---|---|
| **RTO** (max time to restore service) | 1 hour |
| **RPO** (max data loss accepted) | 24 hours (last daily backup) |
| **MTTD** (max time to detect outage) | 5 minutes |

These targets assume the deployment follows the [Deployment Guide](DEPLOYMENT_GUIDE.md)
(daily `pg_dump`, daily `data/` rsync to S3, immutable audit archive).

## Severity classification

| Sev | Definition | Response |
|---|---|---|
| **SEV-1** | Total outage, data integrity at risk | Page on-call immediately, war room, all hands |
| **SEV-2** | Degraded service, partial outage | Page on-call within 15 min, fix during business hours |
| **SEV-3** | Single-feature broken, no data risk | File ticket, fix in next sprint |
| **SEV-4** | Cosmetic / docs / nice-to-have | Backlog |

## Common scenarios

### 1. PostgreSQL is down

**Symptoms:** API returns 500 on every endpoint except `/api/health`;
`/api/health` itself may return `degraded`.

**First response:**
1. SSH to the DB host: `systemctl status postgresql`
2. If stopped, start it: `systemctl start postgresql`
3. Tail the log: `journalctl -u postgresql --since '15 min ago'`
4. If the log shows disk full → see scenario 2
5. If the log shows out-of-memory → restart, then increase work_mem
6. If unrecoverable → restore from backup (scenario 4)

**During the outage**, the application falls back to JSON-only mode
for tables where `TABLE_USE_DB[t]` is True but the connection failed.
This is by design — `is_postgres_ready()` returns False so callers
take the JSON path. Reads work; writes append to JSON. **Once PG
recovers, the JSON drift must be reconciled** — see scenario 6.

### 2. Disk full on the DB host

**Symptoms:** PG starts crashing with "could not extend file"; the
host's `/` or `/var/lib/postgresql` is at 100%.

1. Check what's full: `df -h`
2. If WAL is the culprit: `du -sh /var/lib/postgresql/16/main/pg_wal`.
   Don't delete files manually — they're needed for replication and
   PITR. Instead:
   - Run `SELECT pg_switch_wal();` and wait for archive_command to drain
   - Or, in extremis, increase `max_wal_size` and reload
3. If the DB itself is too big:
   - Identify oldest audit_logs: `SELECT min(created_at) FROM audit.audit_logs;`
   - If > retention policy: `DELETE FROM audit.audit_logs WHERE created_at < now() - interval '730 days';`
     Then `VACUUM FULL audit.audit_logs;`
4. Provision more disk volume. Don't run a banking platform with < 20% free.

### 3. API process dead but DB up

**Symptoms:** `curl /api/health` fails with connection refused;
`systemctl status a2z-api` shows `failed`.

1. Check the journal: `journalctl -u a2z-api --since '15 min ago'`
2. Common causes:
   - Python crash on startup (env var missing) → check `EnvironmentFile=`
   - JWT secret unset → set `A2Z_JWT_SECRET`
   - Port already in use → `ss -tlnp | grep 8502`
3. Restart: `systemctl restart a2z-api`
4. Verify: `curl -fs http://localhost:8502/api/health`

### 4. Restore from PG backup

**When to use:** PG corruption, accidental DROP TABLE, ransomware.

```bash
# 1. Stop application services to prevent writes
systemctl stop a2z-api a2z-app

# 2. Identify the most recent backup
ls -lh /var/backups/a2z-*.pgcustom

# 3. Drop and recreate the database (DESTRUCTIVE)
sudo -u postgres dropdb a2z_prod
sudo -u postgres createdb -O a2z a2z_prod

# 4. Restore
sudo -u postgres pg_restore --dbname=a2z_prod /var/backups/a2z-2026-04-28.pgcustom

# 5. Re-apply schema (idempotent, ensures any new tables exist)
python -c "from utils.db import get_schema_sql; print(get_schema_sql())" | psql "$A2Z_DSN"

# 6. Restart application
systemctl start a2z-api a2z-app

# 7. Smoke test
curl -fs http://localhost:8502/api/health
```

After restore, **inform users of data loss extent** (everything between
the backup time and the outage time). Consider re-running ETL for
that window if CBS/FLEXCUBE export files are still available.

### 5. FLEXCUBE feed broken

**Symptoms:** Daily CBS extract failed; bsc actuals stale; pipeline
deals not updating; `scripts/test_flexcube_pipeline.py --mode=live`
fails L1 (Connectivity) or L5 (Full sync).

**Decision tree:**
- L1 failed → adapter can't reach FLEXCUBE. Check VPN/SFTP credentials,
  certificate expiry. Open ticket with Oracle ops if persistent.
- L2 failed → schema drift (FLEXCUBE column added/renamed). Update
  `EXPECTED_SCHEMAS` in `scripts/test_flexcube_pipeline.py` and the
  adapter mapping in `utils/flexcube_adapter.py`. Test in mock mode
  first.
- L4 failed (< 99% match) → reconciliation drift between staging
  and the A2Z mart. Run `python scripts/reconcile_flexcube.py
  --window=24h` to identify breaks.
- L5 failed (rows lost) → ETL truncation. Check `scripts/etl_flexcube.py`
  log for truncation point; re-run ETL from the last good extract.

**While FLEXCUBE is down**, A2Z continues serving from the last good
extract. Set the platform banner via Admin → Banner ("CBS data is
24h+ stale; refresh expected at HH:MM").

### 6. JSON ↔ PG drift after PG recovery

**Symptoms:** PG was offline for an extended period; writes happened
to JSON only; PG and JSON now disagree.

For each table where `TABLE_USE_DB[t] == True`:

```bash
# Compare row counts
ROW_COUNT_PG=$(psql -tAc "SELECT count(*) FROM users")
ROW_COUNT_JSON=$(jq 'length' data/users.json)
echo "PG: $ROW_COUNT_PG  JSON: $ROW_COUNT_JSON"
```

If they differ, the JSON is authoritative for the drift window:

```bash
# Re-migrate the table
python scripts/migrate_to_postgres.py --table=users --force-overwrite
```

Communicate any data revisions to affected users via email + the
in-app banner.

### 7. Compromised credentials

**Symptoms:** Suspicious logins from unusual geographies; unexpected
admin actions in the audit log.

```bash
# 1. Force token expiry NOW (rotate JWT secret)
NEW_SECRET=$(openssl rand -hex 32)
echo "A2Z_JWT_SECRET=$NEW_SECRET" >> /etc/a2z/env
systemctl restart a2z-api
# Every existing token is immediately invalid.

# 2. Identify the compromised account from audit log
psql -c "
  SELECT actor, action, created_at, request_id
  FROM audit.audit_logs
  WHERE created_at > now() - interval '24 hours'
  ORDER BY created_at DESC LIMIT 200;"

# 3. Disable the account
psql -c "UPDATE users SET disabled=true WHERE username='<suspect>';"

# 4. Force password reset for all users (admin path)
# In the app: Admin → Users → "Force password reset on next login (all)"
```

## Validation after recovery

Before declaring "service restored":

```bash
# 1. Audit must pass
python scripts/audit.py
# Expected: 20+ gates pass, 0 fail.

# 2. Smoke test
TOKEN=$(curl -s -X POST .../api/auth/login -d '{...}' | jq -r .access_token)
curl -fs -H "Authorization: Bearer $TOKEN" .../api/dashboard/md

# 3. Pipeline validation (if FLEXCUBE was affected)
python scripts/test_flexcube_pipeline.py --mode=live
# Expected: exit 0, all five levels passed.

# 4. Spot-check the highest-traffic page in a browser
# Login as a manager, view BSC summary and pipeline list.
```

## Communication template

```
SUBJECT: [SEV-X] A2Z MIS 360 Incident Report — YYYY-MM-DD

What happened:
  <one paragraph>

When:
  Detected: HH:MM TZ
  Resolved: HH:MM TZ
  Total downtime: N minutes

Impact:
  - <users affected>
  - <data loss extent, if any>
  - <features unavailable>

Root cause:
  <one paragraph>

Resolution:
  <bullet list>

Follow-up actions:
  - [ ] <action>, owner @<name>, due <date>
```

Send to: ops@<bank>, executive sponsor, CISO if SEV-1 or security-related.

## Known gotchas

- **The `data/` directory is read by streamlit's filesystem watcher.**
  Don't `rsync` aggressively to it during business hours — the page
  reload churn frustrates users. Run rsync from cron at 02:00.
- **`pg_dump -Fc` is the only supported backup format.** Plain SQL dumps
  break on schema-qualified tables (`audit.audit_logs`, `performance.actuals`).
- **The audit script reads `coverage.xml`, `load_results.json`,
  `flexcube_validation_results.json`.** These are NOT backup-critical;
  CI regenerates them. They're in `.gitignore`.
- **`scripts/migrate_to_postgres.py --force-overwrite` will overwrite
  PG-side changes.** Only run during a known-quiet window.

## Where to learn more

- [Deployment Guide](DEPLOYMENT_GUIDE.md) — how it was set up
- [Security Architecture](SECURITY_ARCHITECTURE.md) — incident classification
- [PostgreSQL Migration Guide](POSTGRESQL_MIGRATION_GUIDE.md) — recovery scenario 6
- [FLEXCUBE Cutover Runbook](FLEXCUBE_CUTOVER_RUNBOOK.md) — recovery scenario 5

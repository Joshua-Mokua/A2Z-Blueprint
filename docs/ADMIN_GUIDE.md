# A2Z MIS 360 — Admin Guide

This guide covers day-to-day operational tasks for A2Z administrators —
the people who manage users, configure modules, run audits, and handle
incidents. It assumes you've already read the
[Deployment Guide](DEPLOYMENT_GUIDE.md) (for the platform layout) and
the [Manager User Manual](USER_MANUAL_MANAGER.md) (for the management
features that admins also have).

This is NOT a system administrator guide for Linux/PG ops — that's
covered in [Deployment Guide](DEPLOYMENT_GUIDE.md) and the
[DR Runbook](DR_RUNBOOK.md). This is the **A2Z application admin** guide.

## Admin role

In A2Z, "admin" is a role assignment, not a separate account. Users
with the `Admin` role get:
- Access to the full **Admin** module (left sidebar)
- Permission to run cache clears and force scorecard recomputes
- Permission to disable users and reassign work
- Read access to all audit logs across the bank
- Permission to manage organisational configuration (KPI library,
  pillar weights, scoring scale, performance bands)

The role is granted in **Admin → Users → \<user\> → Set Role**. Audit
gate **G3** ensures every action that mutates data is logged with the
acting username.

## The Admin module

The sidebar shows 6 sections (audit gate **G5** enforces this count):

| Section | What's there |
|---|---|
| **Users** | Create / edit / disable users, role assignments, password resets |
| **Module Config** | Per-module enablement, refresh schedules, threshold tuning |
| **KPI Library** | Add/edit KPI definitions, role→KPI mappings, default targets |
| **Audit** | Search the audit trail, export reports, retention policy |
| **System** | Cache stats, health probes, recompute jobs, banner config |
| **Reports** | Cross-bank reports admins run for compliance / regulators |

If you only see 5 sections, the registry is broken — file a SEV-2.

## Daily admin tasks

### 1. Check the system banner

Go to **Admin → System → Banner**.

If FLEXCUBE was unstable overnight or there's known stale data,
post a banner so users know. Sample text:

> Pipeline data refreshed 2026-04-29 09:15 (delayed by FLEXCUBE
> connectivity issue). Next refresh expected 12:00. — Operations

### 2. Run the audit

```bash
ssh a2z-prod
cd /opt/a2z
source .venv/bin/activate
python scripts/audit.py
```

Expected output: `Score: 20+/20+ gates = 100.0% — PASS`.

If any gate fails, open the failure detail (the audit prints
violations for each failed gate). Fix the root cause; **don't suppress
the failure**.

For unusual breaks, dump JSON for analysis:
```bash
python scripts/audit.py --json > /tmp/audit-$(date +%F).json
```

### 3. Process new user creation requests

HR sends a daily list of new joiners. For each:

```
Admin → Users → New User
  Username:    <firstname###>
  Staff code:  <300###>
  Full name:   <as in HR>
  Role:        <from joining ticket>
  Branch:      <from HR>
  Start date:  <onboarding date>
```

After creation, verify the welcome email went out (Admin → System →
Email Log).

### 4. Process leavers

HR sends a daily list of leavers. For each:

```
Admin → HR → Reassignment Wizard
  → Pick the leaver
  → Show open work (deals, alerts, approvals, PRs)
  → Reassign to <covering banker>
  → Confirm
  → Click "Disable account"
```

Don't delete. Disable preserves audit history.

### 5. Review failed audit alerts

Go to **Admin → Audit → Failed Actions**. This shows actions that the
authorisation layer rejected (403s, unauthenticated 401s, RBAC denials).

A handful of these per day is normal (people clicking on unauthorised
links). A spike (50+ in an hour) deserves investigation — could be a
phishing campaign or compromised credential. See
[DR Runbook](DR_RUNBOOK.md) scenario 7.

## Weekly admin tasks

### Force a full scorecard recompute

If you've changed KPI weights, scoring scale, or the active-KPI list,
trigger a full recompute:

```
Admin → System → Recompute → Run scorecards from <date>
```

This is intensive (~5 minutes for a 500-staff bank). Run during
off-hours.

### Clear the cache

```
Admin → System → Cache → Clear all
```

The cache also clears automatically on app restart. Manual clear is
useful when you've directly inserted data in PG and want users to see
it without restarting.

### Check disk + DB metrics

Go to **Admin → System → Health** for a rolled-up view:
- DB size + growth rate
- Audit log count + retention compliance
- Disk free %
- API request volume + p95 latency

If any metric is out of band, escalate to platform engineering.

## Monthly admin tasks

### Audit log archive

```bash
# Audit logs older than 90 days move to immutable cold storage.
# This is a compliance requirement.
psql -c "
  COPY (SELECT * FROM audit.audit_logs
        WHERE created_at < now() - interval '90 days'
          AND created_at > now() - interval '13 months')
  TO '/var/lib/postgresql/exports/audit_$(date +%Y_%m).csv'
  CSV HEADER;"

# Then upload to immutable S3 bucket
aws s3 cp /var/lib/postgresql/exports/audit_$(date +%Y_%m).csv \
   s3://<bank>-audit-archive/a2z/ \
   --storage-class GLACIER

# Then prune (only after S3 upload confirmed)
psql -c "
  DELETE FROM audit.audit_logs
  WHERE created_at < now() - interval '90 days';"
```

### Review module config drift

Module config is per-bank tuning (e.g. AML alert SLA, dormancy threshold).
Go to **Admin → Module Config → Audit Drift** to see what's been changed
and by whom over the month.

If a change doesn't make sense, query the team that owns it.

### Pillar weight review

Once a year (typically January), the bank's BSC weights get refreshed.
You enable this from **Admin → KPI Library → Pillar Weights**.
**Do not change mid-period** — every staff scorecard recalculates on
save and existing scores invalidate.

## KPI library management

Go to **Admin → KPI Library**.

### Adding a new KPI

1. Click **New KPI**
2. Fill in:
   - **ID** (e.g. `K072` — must be unique)
   - **Name** (display name)
   - **Pillar** (Financial / Customer Focus / Operational Excellence /
     People & Learning)
   - **Direction** (`higher` for "more is better", `lower` for "less
     is better")
   - **Unit** (KES, %, count, days, etc.)
   - **CBS source** (the column path if computed from CBS, e.g.
     `accounts.deposit_bal`)
   - **Default weight** (0.0–1.0; suggested for roles using this KPI)
   - **Description** (one-paragraph definition for users)
3. Save. The KPI is **inactive** by default — it doesn't compute yet.
4. Activate via **KPI Library → Active KPIs → Add**.
5. Assign to roles via **KPI Library → Role Mappings → \<role\> → Add KPI**.

### Editing an existing KPI

Direction, CBS source, and unit changes are **structural** — they
require a recompute and may invalidate historical data. Don't change
these casually.

Weight and description changes are safe.

If you ever need to RETIRE a KPI mid-year, deactivate it (don't
delete — historical scores reference it).

## Module config

Go to **Admin → Module Config**.

Each module has tunable parameters:

| Module | Common knobs |
|---|---|
| Pipeline | Days-late threshold (default 14), stage list |
| AML | SLA hours per alert priority |
| Credit | Default DSR threshold for auto-decline |
| Loan applications | TAT budget per stage |
| Branch operations | Cash-up tolerance, exception escalation |

Changes here apply at next page load (no restart needed). All changes
are audit-logged with the actor.

## Module enablement

Go to **Admin → Module Config → Enable / Disable**.

To temporarily disable a module across the bank (e.g. while you
investigate a data issue):

1. Set the module's `enabled` flag to `false`
2. Click **Apply** — the module hides from sidebars within 60s (cache TTL)
3. Investigate, fix, re-enable

Disabled modules don't compute KPIs; the KPIs they feed report
"data unavailable" until re-enabled.

## Force recomputes

Go to **Admin → System → Recompute**.

Three scopes:

- **Single user** — recomputes one staff's scorecard from current data
- **Branch** — recomputes everyone in a branch
- **Bank-wide** — recomputes all scorecards (intensive, run off-hours)

Each recompute writes a new row to `audit_trail` with the actor and
the recompute scope.

## Common admin questions

### "A KPI shows 'data unavailable' for everyone"

The module producing it is disabled OR the FLEXCUBE pipeline failed
overnight. Check:
1. **Admin → Module Config → \<module\> → Enabled?** — must be `true`
2. **Admin → System → Health → FLEXCUBE pipeline** — must show green

If both are green and KPIs are still empty, force a recompute. If
that doesn't fix it, file a SEV-2.

### "How do I prove who changed X?"

Go to **Admin → Audit → Search**. Filter by:
- Entity (e.g. `pipeline_deals`)
- Entity ID (the row's ID)
- Action (`update` / `delete` / etc.)
- Date range

You'll get the actor, the before/after diff, and the request_id.

### "A user can't login despite the right password"

Check in this order:

1. **Admin → Users → \<user\>** — `disabled=false`?
2. **Account locked?** — too many failed attempts (5 in 15 min by
   default). Click "Unlock".
3. **Password expired?** (90-day default policy). Force-reset.
4. **JWT secret rotated?** They'll be logged out everywhere — they
   just need to re-enter credentials.
5. **Right URL?** People bookmark old / staging URLs.

### "How do I bulk-update something?"

There's no bulk-edit UI for safety. Use the SQL escape hatch:

1. Connect via `psql "$A2Z_DSN"` from the app host
2. Wrap your update in a transaction:
   ```sql
   BEGIN;
   UPDATE pipeline_deals
      SET stage = 'Closed Lost'
    WHERE open_date < '2025-01-01' AND stage IN ('Initial Contact', 'Qualified');
   -- Verify the row count is what you expected
   SELECT count(*) FROM pipeline_deals WHERE stage = 'Closed Lost';
   COMMIT;  -- or ROLLBACK if surprised
   ```
3. Audit-log it manually:
   ```sql
   INSERT INTO audit.audit_logs (actor, entity, action, detail)
   VALUES ('admin-bulk-update', 'pipeline_deals', 'update',
           '{"reason":"closing stale deals", "count": 47}');
   ```

Bulk SQL updates **must** be audit-logged manually — the API path
auto-logs but direct SQL doesn't.

### "Someone's data was wrong and I fixed it. How do I document it?"

1. Open **Admin → Audit → Note** and write a short narrative
2. Include the entity, the staff affected, the before/after, your
   reason
3. Tag the staff's manager so they're aware

This creates an "admin-note" audit row that survives the data-correction.

## Where to learn more

- [Deployment Guide](DEPLOYMENT_GUIDE.md) — platform topology
- [DR Runbook](DR_RUNBOOK.md) — incident response
- [Security Architecture](SECURITY_ARCHITECTURE.md) — RBAC model + threats
- [PostgreSQL Migration Guide](POSTGRESQL_MIGRATION_GUIDE.md) — moving more tables to PG
- [Admin Conventions](ADMIN_CONVENTIONS.md) — rules every admin page follows

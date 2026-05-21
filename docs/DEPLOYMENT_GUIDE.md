# A2Z MIS 360 — Deployment Guide

This guide walks an operator through deploying A2Z MIS 360 to a
production environment. The platform has three components:

- **Streamlit app** — the user-facing UI (port 8501 by default)
- **FastAPI service** — the data API consumed by the app and external
  systems (port 8502)
- **PostgreSQL** — the system of record (PG 16+)

It also depends on:
- **FLEXCUBE** — Oracle FLEXCUBE 12 (or live SFTP staging from same)
- **Disk-mounted JSON files** — legacy storage for tables not yet
  migrated; lives under `data/`

## Reference architecture

```
                                  ┌──────────────────────┐
                  ┌──── HTTPS ────│  Reverse proxy       │
                  │               │  (nginx / Cloudflare)│
                  │               └────┬────────────┬────┘
                  │                    │            │
                  │            ┌───────┴────┐  ┌────┴───────┐
                  │            │ Streamlit  │  │ FastAPI    │
                  │            │ :8501      │  │ :8502      │
                  │            └─────┬──────┘  └─────┬──────┘
                  │                  │               │
                  │            ┌─────┴───────────────┴────┐
                  │            │ utils/db.py (the seam)   │
                  │            └────────────┬─────────────┘
                  │                         │
                  │            ┌────────────┴──────────────┐
   Banker         │            │                            │
   browser  ─────┘             ▼                            ▼
                       ┌───────────────┐          ┌─────────────────┐
                       │ PostgreSQL 16 │          │ data/*.json     │
                       │ (system of    │          │ (legacy JSON,   │
                       │  record)      │          │  not yet      │
                       └───────┬───────┘          │  migrated)     │
                               │                  └─────────────────┘
                               │
                       ┌───────┴────────┐
                       │ FLEXCUBE 12    │
                       │ (via SFTP /    │
                       │  /api adapter) │
                       └────────────────┘
```

## Prerequisites

- Linux host (Ubuntu 22.04 LTS or RHEL 9; the codebase has no Windows-only
  paths but is tested on Linux)
- Python 3.11
- PostgreSQL 16 with `uuid-ossp` and `pgcrypto` extensions
- ≥ 4 GB RAM, 2 vCPU minimum (8 GB / 4 vCPU recommended for ≥ 100 users)
- 50 GB disk for the database volume + 10 GB for the application
- Outbound HTTPS for FLEXCUBE adapter (live mode); none for synthetic mode
- An LDAP/AD bind user if SSO is enabled (optional, off by default)

## Environment variables

The application reads configuration from environment variables, never
from a `.env` file in production. Use systemd `EnvironmentFile=` or
your orchestrator's secret store.

### Required

| Variable | Purpose |
|---|---|
| `A2Z_USE_DB` | `true` to route to PostgreSQL; `false` for JSON-only |
| `A2Z_DB_HOST` | PG host |
| `A2Z_DB_PORT` | PG port (default 5432) |
| `A2Z_DB_USER` | PG user |
| `A2Z_DB_PASSWORD` | PG password (use a secret store) |
| `A2Z_DB_NAME` | PG database name |
| `A2Z_JWT_SECRET` | Random 32+ byte secret for JWT signing |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `A2Z_API_PORT` | 8502 | FastAPI port |
| `A2Z_STREAMLIT_PORT` | 8501 | Streamlit port |
| `A2Z_JWT_TTL_SECONDS` | 28800 | JWT expiry (8 h) |
| `A2Z_FLEXCUBE_MODE` | synthetic | `synthetic` / `mock` / `live` |
| `A2Z_LOG_LEVEL` | INFO | log level |
| `A2Z_AUDIT_RETENTION_DAYS` | 730 | retention for audit_logs |

## Initial deployment

### 1. Provision PostgreSQL

```bash
psql -U postgres << 'SQL'
CREATE USER a2z WITH PASSWORD '<strong-password>';
CREATE DATABASE a2z_prod OWNER a2z;
\c a2z_prod
GRANT ALL ON SCHEMA public TO a2z;
SQL
```

### 2. Apply schema

```bash
export A2Z_DB_HOST=...
export A2Z_DB_USER=a2z
export A2Z_DB_PASSWORD=...
export A2Z_DB_NAME=a2z_prod

python -c "from utils.db import get_schema_sql; print(get_schema_sql())" \
  | psql "host=$A2Z_DB_HOST user=$A2Z_DB_USER password=$A2Z_DB_PASSWORD dbname=$A2Z_DB_NAME"
```

`get_schema_sql()` is the single source of truth for the DDL. Re-running
it is idempotent (`CREATE TABLE IF NOT EXISTS`).

### 3. Install application

```bash
git clone https://github.com/<org>/A2Z-Blueprint.git /opt/a2z
cd /opt/a2z
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Bootstrap initial data

```bash
# Migrate any seeded JSON to PG (only run once)
python scripts/migrate_to_postgres.py
```

This is idempotent at the row level — re-running won't duplicate data,
but it will overwrite changes made directly in PG. Don't run after
go-live.

### 5. Configure systemd units

`/etc/systemd/system/a2z-api.service`:

```ini
[Unit]
Description=A2Z MIS 360 API
After=network.target postgresql.service

[Service]
Type=simple
User=a2z
WorkingDirectory=/opt/a2z
EnvironmentFile=/etc/a2z/env
ExecStart=/opt/a2z/.venv/bin/python -m utils.api
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/a2z-app.service`:

```ini
[Unit]
Description=A2Z MIS 360 UI
After=network.target a2z-api.service

[Service]
Type=simple
User=a2z
WorkingDirectory=/opt/a2z
EnvironmentFile=/etc/a2z/env
ExecStart=/opt/a2z/.venv/bin/streamlit run app.py --server.port 8501 --server.headless true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now a2z-api a2z-app
```

### 6. Configure reverse proxy

Sample nginx server block (TLS termination + upstream routing):

```nginx
server {
    listen 443 ssl http2;
    server_name a2z.example.com;

    ssl_certificate     /etc/letsencrypt/live/a2z.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/a2z.example.com/privkey.pem;

    # API (REST)
    location /api/ {
        proxy_pass         http://127.0.0.1:8502;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Streamlit (UI)
    location / {
        proxy_pass         http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 86400s;
    }
}
```

### 7. Smoke test

```bash
# API health
curl -s https://a2z.example.com/api/health | jq .

# Login and read the dashboard
TOKEN=$(curl -s -X POST https://a2z.example.com/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<bootstrap-pw>"}' \
  | jq -r .access_token)

curl -s https://a2z.example.com/api/dashboard/md \
  -H "Authorization: Bearer $TOKEN" | jq '.score'
```

If both calls return `200`, the platform is up.

## Upgrades

Standard upgrade flow (no-downtime if behind a reverse proxy with
multiple replicas; ~30 s downtime for single-host installs):

```bash
cd /opt/a2z

# 1. Take an audited PG dump
sudo -u postgres pg_dump -Fc a2z_prod > /var/backups/a2z-pre-$(date +%F).pgcustom

# 2. Pull new code (use a tag, never `main`)
git fetch --tags
git checkout v5.36   # or whichever release

# 3. Refresh deps
source .venv/bin/activate
pip install -r requirements.txt

# 4. Apply any new schema (idempotent)
python -c "from utils.db import get_schema_sql; print(get_schema_sql())" \
  | psql "$A2Z_DSN"

# 5. Run audit before restart — must report 0 violations
python scripts/audit.py

# 6. Restart services
systemctl restart a2z-api a2z-app

# 7. Re-smoke-test
curl -fsS https://a2z.example.com/api/health
```

If the audit reports any failed gate, **do not restart**. Roll back
with `git checkout <previous-tag>` and investigate.

## Health checks

Three probes for liveness/readiness:

| Probe | URL | Expected |
|---|---|---|
| App liveness | `/_stcore/health` | 200 with `OK` |
| API liveness | `/api/health` | 200 with `{"status":"healthy"}` |
| API ready | `/api/cache/stats` | 200 (requires JWT — use a service account) |

Configure your orchestrator's health check on `/api/health` for
read-side health; the cache/stats probe verifies the auth chain too
but costs a JWT exchange.

## Observability

The API logs to stdout in JSON with the following structure:

```json
{
  "ts":          "2026-04-29T08:13:02Z",
  "level":       "INFO",
  "logger":      "a2z.api",
  "request_id":  "uuid",
  "method":      "GET",
  "path":        "/api/dashboard/md",
  "status":      200,
  "duration_ms": 87
}
```

Forward to your observability stack (Loki/Grafana, ELK, Datadog).

Key metrics to alert on:
- `http_5xx_rate > 1% over 5m` (API errors)
- `http_p99 > 5s over 5m` (degradation)
- `pg_pool_exhausted_count > 0` (connection saturation)
- `jwt_validation_failures_per_min > 100` (potential brute-force)

## Backups

Production must run:
- `pg_dump -Fc a2z_prod` daily, 30-day retention
- `data/` rsync to S3 daily (legacy JSON files for tables not yet migrated)
- Audit log archive monthly to immutable storage (compliance requirement)

The DR Runbook documents the restore procedure.

## Where to learn more

- [DR Runbook](DR_RUNBOOK.md) — what to do when things break
- [Security Architecture](SECURITY_ARCHITECTURE.md) — threat model + controls
- [PostgreSQL Migration Guide](POSTGRESQL_MIGRATION_GUIDE.md) — moving more tables to PG
- [Admin Guide](ADMIN_GUIDE.md) — day-to-day operator tasks

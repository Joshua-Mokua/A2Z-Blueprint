# PgBouncer connection pooling for A2Z MIS 360

**Version:** v10.74 ops hygiene drop
**Status:** Preparatory — apply when scale demands it
**Scope:** Connection pooling layer between application + Postgres

## Why PgBouncer

Postgres allocates ~10MB of memory per connection. Default `max_connections` is 100. A Streamlit deployment with 50 concurrent users + a FastAPI service + ETL workers + DBA tools will hit that limit and start refusing connections (`FATAL: sorry, too many clients already`). The platform survives the squeeze by holding queries in queue, but interactive UX degrades sharply.

PgBouncer sits between the application and Postgres. It maintains a small pool of long-lived Postgres connections (typically 25-50) and multiplexes thousands of brief application connections onto that pool. Latency overhead is microseconds. The pool is transparent to application code — same SQL works identically.

## When to apply this

- Concurrent users approaching 50+
- Multiple application processes (Streamlit + FastAPI + ETL workers)
- Connection-exhaustion errors visible in Postgres logs
- Production deployment with a small Postgres instance (db.t3.medium or similar) that can't safely be configured for hundreds of native connections

## When NOT to apply

- Single-user development environment (overkill, adds ops complexity)
- Small Ecobank pilot (≤10 concurrent users) on dedicated DB hardware (Postgres handles this directly)
- Workloads dependent on session-level Postgres state (prepared statements at session level, session GUCs) — these are incompatible with `transaction` pool mode

## Files in this directory

| File | Purpose |
|---|---|
| `docker-compose.pgbouncer.yml` | Compose service definition — layer with your existing compose |
| `pgbouncer.ini` | PgBouncer runtime configuration (pool sizes, timeouts, auth) |
| `userlist.txt.template` | Template for hashed credentials — copy to `userlist.txt` and fill in |
| `README.md` | This file |

## Apply procedure

### 1. Generate hashed credentials

For each Postgres role that will authenticate through PgBouncer:

```bash
# Format: md5(password + username)
echo -n "your_password_hereyour_username_here" | md5sum
# Output: <32-hex-chars>  -

# Or via psql connected to your Postgres:
SELECT 'md5' || md5('your_password_here' || 'your_username_here');
```

Edit `deployment/pgbouncer/userlist.txt` (copy from `userlist.txt.template`) and add one line per role:

```
"a2z_app" "md5<32-hex-chars>"
"stats_user" "md5<32-hex-chars>"
```

Restrict file permissions:

```bash
chmod 600 deployment/pgbouncer/userlist.txt
```

Add to `.gitignore` so credentials never reach version control:

```
deployment/pgbouncer/userlist.txt
```

### 2. Adjust pool sizes for your workload

Defaults in `pgbouncer.ini` are conservative for a tier-2 bank workload:

- `max_client_conn = 500` — accept up to 500 concurrent web/API clients
- `default_pool_size = 25` — maintain 25 Postgres connections per database/user combo
- `reserve_pool_size = 5` — extra 5 connections under load spikes

For a small pilot, you can reduce both pool sizes by half. For a busy production deployment with multiple Streamlit instances, double them — but keep `max_db_connections` (the upstream Postgres limit) below your Postgres `max_connections` setting.

### 3. Layer with existing compose

Your application probably has a primary `docker-compose.yml`. PgBouncer is layered with `-f`:

```bash
docker compose \
    -f docker-compose.yml \
    -f deployment/pgbouncer/docker-compose.pgbouncer.yml \
    up -d
```

The pgbouncer container joins your existing application network (set `COMPOSE_NETWORK` env var or edit the network name in the YAML).

### 4. Update application connection strings

Anywhere your application connects to Postgres at `postgres:5432`, change to `pgbouncer:6432`. Typical locations:

- `.env` — `DATABASE_URL=postgresql://a2z_app:password@pgbouncer:6432/a2z`
- `utils/db.py` — connection factory
- `scripts/migrate_to_postgres.py` — keep pointing at `postgres:5432` (DDL doesn't pool well)
- ETL workers — point at `pgbouncer:6432`

### 5. Validate

Connect to PgBouncer's stats console:

```bash
docker exec -it a2z-pgbouncer psql -h localhost -U stats_user pgbouncer
```

Run:

```sql
SHOW POOLS;
SHOW STATS;
SHOW CLIENTS;
```

Confirm `cl_active`, `sv_active`, `sv_idle` counts match your traffic pattern.

## Pool mode caveat

The default `pool_mode = transaction` reuses Postgres connections at transaction boundaries. This breaks any application code that relies on session-level state across transactions:

- Server-side cursors with `WITH HOLD` — fine, they survive transaction boundaries
- Prepared statements at session level (`PREPARE foo AS ...` outside a transaction) — **broken**
- `SET` commands outside transactions — **broken** (use `SET LOCAL` inside transactions instead)
- `LISTEN/NOTIFY` — **broken**, requires session mode

A2Z MIS 360 itself is `transaction`-mode safe — the engines are stateless function calls, the FastAPI handlers do not use session-level prepared statements, and the ETL pipeline manages its own session affinity. **If you add NOTIFY/LISTEN handlers later, route them through a separate pool with `pool_mode = session`.**

## Operational notes

**Health check:** PgBouncer exposes `pg_isready` against its own stats DB. The compose health check verifies the container is up but does not verify upstream Postgres connectivity. Add an external monitor that periodically runs a query through PgBouncer.

**Logs:** PgBouncer logs to stdout. With `log_connections = 1` enabled, expect ~2 lines per HTTP request that hits a Streamlit page. For production, consider setting `log_connections = 0` and only logging errors.

**Restart safety:** PgBouncer drains active connections on SIGINT (graceful) but kills them on SIGTERM (rapid). Application code should already handle dropped connections via reconnect logic — confirm `utils/db.py` does so.

**Per Rule 7:** PgBouncer is a connection pool, not a query router. It does not inspect SQL, does not enforce row-level security, does not modify transactions. Authentication still flows through Postgres roles. Do not assume PgBouncer adds security boundary — application-level access control via `pages/_access.py` and Postgres role-level permissions remain the source of truth.

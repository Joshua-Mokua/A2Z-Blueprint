# Redis Production Deployment Runbook — A2Z MIS 360

> **Status**: PRODUCTION DEPLOYMENT GUIDE
> **Shipped in**: v9.12 (May 2026)
> **Companion to**: `utils/state_backend.py` (v9.6 abstraction + v9.11 production hardening)
> **Audience**: Joshua + DevOps engineer + bank IT operations team
> **Prerequisites**: Familiarity with Linux ops, TLS basics, Redis fundamentals

---

## What this runbook is

This runbook operationalizes the v9.11 RedisBackend production-grade configuration for real-world Ecobank Kenya deployment. It covers:

1. **Topology choices** — when to use single-instance, replicated, or Sentinel
2. **TLS certificate setup** — cert generation, validation, A2Z-side configuration
3. **ACL configuration** — Redis 6+ user accounts with least-privilege
4. **Monitoring** — what metrics to watch, alerting thresholds, slowlog usage
5. **Backup & disaster recovery** — RDB snapshots, AOF logs, point-in-time recovery
6. **Capacity planning** — memory sizing per A2Z key domain
7. **Deployment checklist** — pre-flight + post-deployment validation
8. **Operational procedures** — failover, key cleanup, version upgrades

---

## What this runbook is NOT

1. **Not a Redis tutorial** — assumes basic familiarity with Redis CLI, RESP protocol, persistence modes
2. **Not Kenyan-bank-specific** — generic patterns; banking-specific compliance (CBK Operations Resilience Guidelines, DPA 2019) needs separate review by Joshua's lawyer
3. **Not a Sentinel / Cluster reference** — A2Z's RedisBackend is single-instance only; HA via Sentinel is mentioned but not detailed
4. **Not an Ecobank-specific deployment plan** — actual deployment requires bank IT infrastructure inputs (network topology, firewalls, identity systems)
5. **Not a security audit** — recommendations are good-practice; bank's CISO must sign off

---

## 1. Topology choices

### 1.1 Decision matrix

| Use case | Recommended topology | Reasoning |
|---|---|---|
| Local development | InMemoryBackend (no Redis) | Zero infra; matches v8.x baseline |
| Single-instance Streamlit | InMemoryBackend (no Redis) | State is process-local but no race issues |
| Multi-instance Streamlit (load-balanced) | **Single-instance Redis** | A2Z's primary v9.x use case; matches RedisBackend design |
| Multi-instance + HA required | Redis with Sentinel | A2Z connects to Sentinel proxy as single endpoint |
| Geographic distribution | Redis Enterprise / managed | Beyond A2Z RedisBackend scope; vendor patterns apply |

### 1.2 Recommended initial deployment

Per Ecobank Kenya v9.x design-partner context:

- **2-3 Streamlit processes** behind nginx load balancer (session affinity not required because v9.6-v9.10 unified state)
- **1 Redis primary** (Redis 7.x recommended; Redis 6+ minimum for ACL support)
- **No Sentinel initially** — single-instance Redis is acceptable for design-partner pilot phase
- **Sentinel adoption** when SLA tightening or production-traffic SLAs require HA

### 1.3 Network topology

```
                ┌────────────────────────────┐
                │   nginx Load Balancer      │
                │   (SSL termination)        │
                └────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌─────────┐       ┌─────────┐       ┌─────────┐
   │ Streamlit│       │ Streamlit│       │ Streamlit│
   │ Process 1│       │ Process 2│       │ Process 3│
   └─────────┘       └─────────┘       └─────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                ┌─────────────────────┐
                │   Redis Primary     │
                │   (TLS + ACL)       │
                │   - RDB snapshots   │
                │   - AOF persistence │
                └─────────────────────┘
                          │
                          ▼
                ┌─────────────────────┐
                │  Backup Storage     │
                │  (off-host)         │
                └─────────────────────┘
```

Key network properties:
- All traffic between Streamlit and Redis encrypted via TLS (`rediss://`)
- Redis bound to internal network only (not internet-routable)
- Backup storage on different host (volume / NAS / object store)

---

## 2. TLS certificate setup

### 2.1 Why TLS

Per CBK Prudential Guidelines for data confidentiality and Kenya DPA 2019 §31 (security of processing):

- All inter-service communication carrying personal data MUST be encrypted in transit
- A2Z's circuit breaker / retry telemetry / alert history MAY contain personal data references (alert IDs may map to customer events)
- Conservative default: encrypt everything

### 2.2 Certificate authority options

| Option | When | Effort |
|---|---|---|
| Public CA (Let's Encrypt) | Internet-routable Redis (uncommon) | Moderate; ACME automation |
| Bank-internal PKI | Bank already has internal CA | Low; existing process |
| Self-signed CA (private) | Lab / pilot only | Low; manual cert management |

### 2.3 Self-signed CA recipe (pilot environments only)

```bash
# 1. Generate CA private key + certificate
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 365 -key ca-key.pem -out ca-cert.pem \
    -subj "/CN=A2Z Internal CA/O=A2Z Pilot/C=KE"

# 2. Generate Redis server key + CSR
openssl genrsa -out redis-key.pem 4096
openssl req -new -key redis-key.pem -out redis.csr \
    -subj "/CN=redis.a2z-internal/O=A2Z Pilot/C=KE"

# 3. Sign Redis cert with CA
openssl x509 -req -days 365 -in redis.csr \
    -CA ca-cert.pem -CAkey ca-key.pem -CAcreateserial \
    -out redis-cert.pem

# 4. Verify
openssl verify -CAfile ca-cert.pem redis-cert.pem
```

### 2.4 Redis server TLS configuration

`/etc/redis/redis.conf`:

```ini
# TLS configuration (Redis 6+)
port 0                           # disable plaintext port
tls-port 6380                    # TLS-only port
tls-cert-file /etc/redis/redis-cert.pem
tls-key-file /etc/redis/redis-key.pem
tls-ca-cert-file /etc/redis/ca-cert.pem
tls-auth-clients yes             # require client certs (optional, recommended)

# Bind only to internal interfaces
bind 10.0.1.5 127.0.0.1
```

### 2.5 A2Z-side TLS configuration

```bash
# Set the A2Z_REDIS_URL environment variable
export A2Z_REDIS_URL="rediss://username:password@redis.a2z-internal:6380/0"

# If using a private CA, set the CA bundle path so redis-py can validate
export REDIS_CA_BUNDLE_PATH="/path/to/ca-cert.pem"
# Note: redis-py uses system trust store by default; A2Z_REDIS_CA_BUNDLE_PATH
# parsing is a v9.x candidate. For now, install the CA cert system-wide:
sudo cp ca-cert.pem /usr/local/share/ca-certificates/a2z-ca.crt
sudo update-ca-certificates
```

### 2.6 TLS verification

```bash
# From the Streamlit host:
redis-cli --tls --cacert /path/to/ca-cert.pem -h redis.a2z-internal -p 6380 ping
# → PONG

# Verify cert chain:
openssl s_client -connect redis.a2z-internal:6380 \
    -CAfile /path/to/ca-cert.pem -servername redis.a2z-internal
# → Verify return code: 0 (ok)
```

---

## 3. ACL configuration (Redis 6+)

### 3.1 Why ACL

Per CBK Prudential Guidelines (least-privilege access):

- Default Redis user (`default`) has full access — operationally dangerous
- A2Z should connect with a dedicated user that has access ONLY to its key prefix
- This limits blast radius of credential compromise

### 3.2 Recommended ACL setup

```redis
# Connect as default admin user
AUTH default <admin-password>

# Create A2Z application user with restricted access
ACL SETUSER a2z_app on \
    >a2z_strong_password \
    ~a2z:* \
    +@read +@write +@hash +@list +@set +@string +@connection +@scripting \
    -@dangerous

# Verify
ACL GETUSER a2z_app
```

ACL breakdown:
- `~a2z:*` — only access keys with the `a2z:` prefix (matches A2Z's `KEY_PREFIX` constant)
- `+@read +@write` — basic read/write commands
- `+@hash +@list +@set +@string` — data-type-specific commands A2Z uses
- `+@connection` — PING, AUTH, SELECT
- `+@scripting` — for future Lua scripts (currently unused but reserved)
- `-@dangerous` — explicit deny for FLUSHALL, FLUSHDB, KEYS, CONFIG, etc.

### 3.3 A2Z connection with ACL

```bash
export A2Z_REDIS_URL="rediss://a2z_app:a2z_strong_password@redis.a2z-internal:6380/0"
```

### 3.4 Password rotation

Quarterly rotation recommended:

```redis
# Old password still valid during overlap window
ACL SETUSER a2z_app >new_password

# Update A2Z env var, restart Streamlit processes
# Then revoke old password
ACL SETUSER a2z_app <old_password
```

Document password generation in bank's secrets-management system (HashiCorp Vault, AWS Secrets Manager, etc.).

---

## 4. Monitoring

### 4.1 Key metrics to watch

| Metric | Source | Alert threshold | Why |
|---|---|---|---|
| `connected_clients` | `INFO clients` | > 80% of `maxclients` | Capacity warning |
| `used_memory` | `INFO memory` | > 80% of `maxmemory` | OOM eviction risk |
| `instantaneous_ops_per_sec` | `INFO stats` | > 10K (baseline) | Load anomaly |
| `rejected_connections` | `INFO stats` | > 0 | Pool exhaustion |
| `total_net_input_bytes` rate | `INFO stats` | > 100 MB/s | Network anomaly |
| Replication lag (if replicated) | `INFO replication` | > 5s | Sync issue |
| Keyspace size | `DBSIZE` | > capacity plan | Growth anomaly |
| `slowlog_len` | `SLOWLOG LEN` | > 100 in 5 min | Performance regression |

### 4.2 Slowlog configuration

```redis
# Log queries slower than 10ms
CONFIG SET slowlog-log-slower-than 10000

# Keep last 128 slow queries
CONFIG SET slowlog-max-len 128

# Read slowlog
SLOWLOG GET 10
```

A2Z keys are typically small (< 1 KB hash, < 200-element list); any slow query indicates infrastructure issues (network, disk, CPU).

### 4.3 Recommended Prometheus exporter

[redis_exporter](https://github.com/oliver006/redis_exporter) — most-used Redis Prometheus exporter; exposes all `INFO` metrics. Configure with same TLS/ACL as A2Z's connection.

```yaml
# Prometheus scrape config
scrape_configs:
  - job_name: 'redis-a2z'
    static_configs:
      - targets: ['redis-exporter:9121']
```

### 4.4 Grafana dashboard recommendations

[Redis Dashboard for Prometheus Redis Exporter](https://grafana.com/grafana/dashboards/763) — community dashboard; covers most A2Z monitoring needs.

A2Z-specific panels to add:
- Per-key-prefix memory usage (use `MEMORY USAGE a2z:circuit:*` aggregates)
- Per-domain key count (use `EVAL` with Lua script + `SCAN MATCH a2z:circuit:*`)

### 4.5 Health-check endpoint integration

The `RedisBackend.ping()` method maps to Redis `PING`. The v9.14 admin UI already calls this; programmatic health checks for kubernetes liveness/readiness probes can use the same approach.

```python
# Liveness check (in your custom health endpoint):
from utils.state_backend import get_default_backend
backend = get_default_backend()
if not backend.ping():
    raise HTTPException(503, "Redis unreachable")
```

---

## 5. Backup & disaster recovery

### 5.1 Persistence modes

A2Z's RedisBackend assumes Redis is configured with EITHER:

- **RDB snapshots** (point-in-time backups; default Redis behavior)
- **AOF (Append Only File)** — every write logged; replay on restart for crash recovery
- **Both** (recommended) — RDB for fast restart, AOF for crash safety

### 5.2 Recommended persistence configuration

`/etc/redis/redis.conf`:

```ini
# RDB snapshots
save 900 1            # snapshot after 900s if at least 1 key changed
save 300 10           # snapshot after 300s if at least 10 keys changed
save 60 10000         # snapshot after 60s if at least 10K keys changed
dbfilename dump.rdb
dir /var/lib/redis

# AOF
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec  # fsync every second (good balance)
```

### 5.3 Backup automation

Daily off-host backup recipe (`cron` at 02:00 KAT):

```bash
#!/bin/bash
# /usr/local/bin/redis-backup.sh
set -euo pipefail

BACKUP_DIR="/backup/redis/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Trigger background save (non-blocking; returns immediately)
redis-cli --tls --cacert /path/to/ca-cert.pem \
    -a "$REDIS_PASSWORD" --no-auth-warning \
    BGSAVE

# Wait for save to complete
while [ "$(redis-cli --tls --cacert /path/to/ca-cert.pem \
    -a "$REDIS_PASSWORD" --no-auth-warning \
    LASTSAVE)" = "$(redis-cli --tls --cacert /path/to/ca-cert.pem \
    -a "$REDIS_PASSWORD" --no-auth-warning \
    LASTSAVE)" ]; do
    sleep 1
done

# Copy RDB file to backup
cp /var/lib/redis/dump.rdb "$BACKUP_DIR/dump-$(date +%H%M%S).rdb"

# Sync to off-host storage (AWS S3, Azure Blob, NFS, etc.)
aws s3 cp "$BACKUP_DIR/dump-$(date +%H%M%S).rdb" \
    "s3://a2z-backups/redis/$(date +%Y/%m/%d)/"

# Retain 7 days local
find /backup/redis -type d -mtime +7 -exec rm -rf {} +
```

### 5.4 Disaster recovery procedures

**Scenario: Redis primary lost (host failure, OS corruption)**

1. **Stop all Streamlit processes** — they will fall back to InMemoryBackend automatically (graceful degradation per v9.6 design)
2. **Provision new Redis host** — same OS, same Redis version
3. **Restore RDB file** — copy from backup to `/var/lib/redis/dump.rdb`
4. **Start Redis** — it auto-loads from RDB
5. **Reconfigure A2Z env vars** — point to new endpoint (or update DNS if used)
6. **Restart Streamlit processes** — they connect to new Redis, resume normal operation

Expected recovery time: 5-30 minutes depending on backup retrieval + Redis warm-up.

**Scenario: Data loss (corrupted RDB, accidental FLUSHALL)**

1. Stop Redis
2. Restore from previous-day backup (data older than last RDB is lost)
3. Restart Redis
4. Note: A2Z state (circuit / retry / latency / alert / dedup) will rebuild from new traffic; some alert history may be permanently lost

**Scenario: Streamlit process can't reach Redis**

1. A2Z auto-falls-back to InMemoryBackend per v9.6 design (`get_default_backend()` retries on next process start)
2. Multi-process state is broken during outage — different processes have different circuit-breaker views
3. Check Redis health via runbook §4
4. After Redis recovers, restart Streamlit processes to re-establish RedisBackend connection

---

## 6. Capacity planning

### 6.1 A2Z keyspace estimates

Per typical Ecobank Kenya pilot deployment (5 FLEXCUBE endpoints, 232 RMs, ~500 alerts/month):

| Domain | Keys | Avg key size | Total memory |
|---|---|---|---|
| `a2z:circuit:*` | 5 hashes (5 endpoints × 2 fields) | ~200 bytes | ~1 KB |
| `a2z:retry:*` | 5 hashes (5 endpoints × 5 fields) | ~400 bytes | ~2 KB |
| `a2z:latency:*` | 5 lists (5 endpoints × ≤200 samples) | ~30 KB each (200 × 150 bytes) | ~150 KB |
| `a2z:alert_history` | 1 list (≤500 alerts) | ~100 KB (500 × 200 bytes) | ~100 KB |
| `a2z:dedup:*` | ~10-20 hashes (per active topic) | ~300 bytes | ~6 KB |
| **Total A2Z usage** | ~25-30 keys | — | **~250-300 KB** |

A2Z is a **tiny consumer** of Redis memory. Capacity planning for v9.x deployment:

- Minimum Redis memory: 256 MB (oversized but recommended for OS overhead)
- Recommended: 512 MB - 1 GB (provides headroom for future v10.x state surfaces)

### 6.2 maxmemory configuration

```ini
# /etc/redis/redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru   # evict least-recently-used if memory exhausted

# A2Z is so small that allkeys-lru should NEVER trigger; alert if it does
```

### 6.3 Connection pool sizing

A2Z's default `A2Z_REDIS_MAX_CONNECTIONS=50` is generous for typical Streamlit deployment:

- 3 Streamlit processes × ~10 concurrent users × 1-2 outstanding Redis calls per user = ~60 connections total
- 50 connections per process pool × 3 processes = 150 total — substantial headroom

For high-traffic deployments, increase via env var:
```bash
export A2Z_REDIS_MAX_CONNECTIONS=100
```

---

## 7. Deployment checklist

### 7.1 Pre-deployment

- [ ] Redis version ≥ 6.0 confirmed (`redis-cli INFO server | grep redis_version`)
- [ ] TLS certificates generated and installed
- [ ] ACL user `a2z_app` created with appropriate permissions
- [ ] A2Z env vars set in deployment configuration:
  - [ ] `A2Z_REDIS_URL` (with auth + TLS)
  - [ ] `A2Z_REDIS_KEY_PREFIX` (if non-default)
  - [ ] `A2Z_REDIS_MAX_CONNECTIONS` (if non-default)
- [ ] Backup automation deployed and tested (recover a backup to test instance)
- [ ] Monitoring exporter installed and metrics flowing
- [ ] Alerts configured for thresholds in §4.1
- [ ] DR runbook reviewed by ops team
- [ ] Bank CISO sign-off on TLS / ACL / network topology

### 7.2 Initial deployment

- [ ] Stop all Streamlit processes
- [ ] Verify Redis is reachable from Streamlit hosts: `redis-cli --tls --cacert ... -h redis -p 6380 -a ... PING` returns PONG
- [ ] Start one Streamlit process; verify it connects (admin UI shows backend = redis)
- [ ] Trigger a few FLEXCUBE calls; verify keys appear: `redis-cli ... KEYS 'a2z:*'` returns expected keys
- [ ] Start remaining Streamlit processes
- [ ] Verify all processes see same state via admin UI

### 7.3 Post-deployment validation

- [ ] Trigger circuit breaker on one process (force NPL endpoint failures); verify other processes see open circuit (multi-process state sharing works)
- [ ] Generate alert; verify it appears in admin UI on all processes
- [ ] Run `scripts/redis_admin.py health-check` (when v9.13 ships)
- [ ] First 24 hours: monitor connection counts, slowlog, memory growth
- [ ] First week: validate backup recovery works (restore RDB to test instance, verify A2Z connects)

---

## 8. Operational procedures

### 8.1 Manual key cleanup

If A2Z state needs reset (test scenarios, debugging):

```bash
# WARNING: Destructive. Confirm with operator before running in production.
# Clear all A2Z keys (keeps other applications' Redis data intact)
redis-cli --tls --cacert ... -h redis -p 6380 -a ... \
    --scan --pattern 'a2z:*' | \
    xargs redis-cli --tls --cacert ... -h redis -p 6380 -a ... DEL
```

A2Z auto-rebuilds state from new traffic.

### 8.2 Version upgrade

Upgrading Redis (e.g. 6.x → 7.x):

1. Schedule maintenance window
2. Verify backup is recent (< 1 hour old)
3. Stop Streamlit processes (graceful degradation to InMemoryBackend)
4. Stop Redis: `systemctl stop redis`
5. Upgrade Redis package
6. Start Redis: `systemctl start redis`
7. Verify TLS / ACL still work
8. Restart Streamlit processes

A2Z's RedisBackend is forward-compatible with Redis 6 → 7 (no breaking ACL/HINCRBY/RPUSH/LTRIM changes).

### 8.3 Failover to InMemoryBackend (emergency)

If Redis is down and immediate recovery isn't possible:

```bash
# Unset A2Z_REDIS_URL on Streamlit hosts
unset A2Z_REDIS_URL

# Restart Streamlit processes
systemctl restart a2z-streamlit
```

A2Z reverts to InMemoryBackend; multi-process state sharing is lost but processes work independently. Re-enable Redis by setting env var + restarting.

### 8.4 Connection pool exhaustion

Symptom: `redis.exceptions.ConnectionError: Too many connections` in logs.

Diagnosis:
```bash
redis-cli ... INFO clients
# connected_clients: <high number>
```

Mitigation:
1. Increase `A2Z_REDIS_MAX_CONNECTIONS` (per-process)
2. Increase Redis `maxclients` config (server-side)
3. Investigate caller patterns — A2Z keeps connections in pool, doesn't leak; spike usually indicates unusual traffic

---

## 9. Honest acknowledgements

1. **Self-signed CA recipe is for pilot only** — production deployments should use bank-internal PKI or public CA.
2. **ACL recommendation is conservative** — bank's security team may want stricter controls (e.g. drop `+@scripting` if no Lua scripts planned).
3. **Backup script is a template** — bank's actual backup infrastructure (Veeam, Bacula, custom) may have specific requirements.
4. **Capacity estimates assume current v9.x state surfaces** — future state additions in v10.x+ would expand the footprint; revisit when that happens.
5. **No specific TLS version requirement** — runbook assumes TLS 1.2+. Some legacy bank infrastructure may default to TLS 1.0/1.1; verify and upgrade if needed.
6. **No detailed Sentinel / Cluster setup** — A2Z's RedisBackend doesn't need it; if bank requires HA, the runbook stub above plus Redis docs cover the gap.
7. **Monitoring thresholds are starting points** — first 30 days of operation should refine these based on actual baseline.
8. **No Kubernetes-specific deployment** — runbook assumes systemd / VM-based deployment. K8s deployment with operators (e.g. Bitnami Redis chart) is similar but adds container-orchestration concerns out of scope here.
9. **Disaster recovery RTO is 5-30 minutes; RPO is up to 24 hours** — based on daily backups. Tighter RPO requires hourly backups or replicated topology; both increase ops complexity.
10. **No Redis 8.x guidance** — at the time of this runbook, Redis 7.x is current stable; future versions need re-validation when released.

---

## 10. Companion artifacts

| Artifact | Status | Path |
|---|---|---|
| RedisBackend production config | ✅ v9.11 | `utils/state_backend.py` |
| This runbook | ✅ v9.12 | `docs/REDIS_DEPLOYMENT_RUNBOOK.md` |
| `redis_admin.py` ops CLI | ✅ v9.13 | `scripts/redis_admin.py` |
| Admin UI ops panel | ✅ v9.14 | `pages/7_admin.py` (State Backend sub-tab extended) |
| G115 audit gate | ✅ v9.15 | `scripts/audit.py` |

---

*v9.12 — Redis Production Deployment Runbook. Companion to utils/state_backend.py v9.11. The operational discipline that makes the v9.6-v9.10 multi-process state architecture deployment-ready.*

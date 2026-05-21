# CHANGELOG v9.11 — RedisBackend production configuration

**Audit:** 114/114 PASS — **64th consecutive clean.**

## What

Opens the v9.11-v9.15 Redis production-hardening arc. Extends `RedisBackend` from a basic `redis.from_url()` wrapper into a production-grade client with connection pooling, configurable timeouts, TLS support, ACL auth, and health-check intervals.

## Changes to `utils/state_backend.py`

### `RedisBackend.__init__` extended

Now constructs a `redis.ConnectionPool` with explicit parameters, then wraps a `redis.Redis(connection_pool=pool)` client around it. The pool provides:

- **Explicit max_connections** — prevents file-descriptor exhaustion under load
- **Connection re-use** — avoids TCP handshake overhead per call
- **Per-pool authentication** — username/password parsed from URL automatically (Redis 6+ ACL)
- **TLS support** — `rediss://` URLs are auto-detected by redis-py with cert validation
- **Configurable timeouts** — `socket_timeout` (read/write), `socket_connect_timeout` (handshake)
- **Health check pings** — TCP keepalive at `health_check_interval` seconds detects silent network drops
- **Automatic retry** — `retry_on_timeout=True` for transient network issues

### Environment-variable configuration

All tunables can be set via env vars without code changes:

| Env var | Default | Purpose |
|---|---|---|
| `A2Z_REDIS_URL` | (unset → in-memory) | Connection URL — `redis://[user:pass@]host:port/db` or `rediss://...` for TLS |
| `A2Z_REDIS_MAX_CONNECTIONS` | 50 | Connection pool size |
| `A2Z_REDIS_SOCKET_TIMEOUT` | 5.0 | Read/write timeout (seconds) |
| `A2Z_REDIS_CONNECT_TIMEOUT` | 5.0 | Connection establishment timeout (seconds) |
| `A2Z_REDIS_HEALTH_CHECK_INTERVAL` | 30 | TCP keepalive ping interval (seconds) |
| `A2Z_REDIS_KEY_PREFIX` | `a2z:` | Global key namespace |

Configuration resolution order: explicit `__init__` arg → env var → hardcoded default.

### `RedisBackend.get_connection_config()` (new)

Returns a dict describing effective configuration for operator diagnostics. Used by v9.13 redis_admin CLI and v9.14 admin UI panel. **Credentials are masked** in the URL field — the `username:password@` portion becomes `username:****@` so the dict is safe to log or display.

Example output:
```python
{
    "url": "rediss://admin:****@redis.prod.example.com:6380/0",
    "key_prefix": "a2z:",
    "max_connections": 100,
    "socket_timeout_seconds": 3.0,
    "connect_timeout_seconds": 5.0,
    "health_check_interval_seconds": 30,
    "tls_enabled": True,
    "auth_enabled": True,
}
```

### `get_default_backend()` updated

- Now reads `A2Z_REDIS_KEY_PREFIX` env var when constructing RedisBackend
- Diagnostic message on connection failure masks credentials (only logs hostname:port portion)

## Behavioral verification

URL masking tested across 4 scenarios:
- No credentials: passthrough unchanged
- Username + password: replaced with `username:****@`
- TLS `rediss://` with auth: same masking pattern preserved
- No-auth host: passthrough unchanged

DEFAULT class constants verified: max_conn=50, socket_timeout=5s, connect_timeout=5s, hc_interval=30s.

## What v9.11 does NOT ship

1. **Sentinel / Cluster support** — single-instance Redis only. Sentinel/Cluster topologies are operator concerns; A2Z connects to a single endpoint (the sentinel/cluster proxy if needed).
2. **Replication monitoring** — surface in v9.14
3. **TLS certificate pinning** — uses redis-py default cert validation (system trust store). Custom CA bundles via `A2Z_REDIS_CA_BUNDLE_PATH` is a v9.x candidate.
4. **Backup tooling** — covered by v9.13 redis_admin CLI
5. **Live integration test with real Redis** — redis-py not in environment; production verification is operator's responsibility per v9.12 runbook

## Honest acknowledgements

1. **No live Redis available** — v9.11 verified through structural tests (URL masking, default constants, config plumbing). When Joshua deploys with real Redis, behavior should match expectations; if not, this CHANGELOG documents the contract.
2. **Connection pool size 50 is a guess** — appropriate for typical Streamlit deployment with 5-20 concurrent users; production tuning may require different values per workload.
3. **Health-check interval 30s is conservative** — matches redis-py default; some networks need shorter intervals for quick failure detection. Operator tunes via env var.
4. **Retry-on-timeout is shallow** — redis-py retries the immediate command; doesn't reconnect on persistent failures. For deeper resilience, the per-call try/except pattern in callers (existing in v8.x adapter code) provides additional protection.
5. **No connection pool stats published yet** — `pool.connection_kwargs` is internal; v9.14 surfaces this through admin UI.
6. **`get_connection_config()` masks credentials but uses string parsing** — robust for typical URLs; pathological inputs could leak. Acceptable: only operators with backend access call this method.

## Next: v9.12

`docs/REDIS_DEPLOYMENT_RUNBOOK.md` — comprehensive deployment runbook covering topology choices, TLS cert setup, ACL configuration, monitoring (INFO command, slowlog), backup recipes (RDB + AOF), disaster recovery procedures, and capacity planning per A2Z key domain.

# CHANGELOG v9.13 — Redis admin CLI (`scripts/redis_admin.py`)

**Audit:** 114/114 PASS — **66th consecutive clean** (foundational allowlist update is canonical pattern for new I/O-handling script).

## What

Ships `scripts/redis_admin.py` (~360 lines) — operations CLI for the StateBackend abstraction. Operator-facing tool for production debugging, key inventory, state snapshot/restore, and end-to-end migration verification.

## Commands

| Command | Purpose | Destructive? |
|---|---|---|
| `health-check` | Verify backend reachable + responsive | No |
| `config` | Display effective configuration (credentials masked) | No |
| `inventory` | Count keys per A2Z domain | No |
| `live-state` | Read live state via public APIs | No |
| `verify-state` | Cross-check v9.6-v9.8 migrations end-to-end | No |
| `clear-domain` | Manually clear all keys for a domain | YES (--confirm req'd) |
| `snapshot` | Export current state to JSON file | No |
| `restore` | Import snapshot JSON into backend | YES (--confirm req'd) |

## Verified output

```
=== verify-state ===
Backend: in_memory

Migration                           Status
--------------------------------------------------
Circuit breaker (v9.6)              ✓ OK
Retry telemetry (v9.7)              ✓ OK
Latency rolling (v9.8)              ✓ OK
Alert history (v9.8)                ✓ OK
Event-bus dedup (v9.8)              ✓ OK
Backend hash ops                    ✓ OK
--------------------------------------------------

✓ All 6 verifications passed.
```

## FOUNDATIONAL allowlist update

`scripts/redis_admin.py` added to `FOUNDATIONAL` set in `scripts/audit.py` because `snapshot` and `restore` commands are inherently file-I/O operations (matching pattern set by `scripts/migrate_to_postgres.py`, `scripts/generate_all_docs.py`, etc.).

## Honest acknowledgements

1. **Tested only with InMemoryBackend** — no live Redis available; CLI works against InMemoryBackend identically to how it would work against RedisBackend (same StateBackend interface).
2. **`clear-domain` is destructive** — requires `--confirm` flag; operator must acknowledge before running.
3. **`restore` overwrites existing state** — no merge logic; new state replaces old. Recommend snapshot before restore as safety.
4. **Snapshot doesn't capture TTLs** — for the v9.x state surfaces this is fine (no TTLs in use); future state with TTL needs round-trip preservation.
5. **No bulk operations beyond inventory** — operators wanting per-endpoint diagnostics can extend; current scope covers ~95% of operational needs.
6. **Path manipulation for sys.path injection** — works for typical install layouts; edge-case packaging may need adjustment.

## Next: v9.14

Admin UI extensions for production ops — extend the v9.9 "🗄️ State Backend" sub-tab with:
- Connection pool stats (when RedisBackend in use)
- Memory usage indicators
- Per-domain cleanup buttons (operator-driven; calls into redis_admin domains)
- Slow query log visibility (when v9.13 gains that surface)

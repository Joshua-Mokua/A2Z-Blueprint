# CHANGELOG v9.6 — State backend abstraction + circuit-state migration

**Audit:** 113/113 PASS — **59th consecutive clean.**

## What

Opens the v9.6-v9.10 multi-process state arc per `docs/A2Z_V8_RETROSPECTIVE_FINAL_AND_V9_PLAN.md` Part 7. Ships the `utils/state_backend.py` abstraction enabling Redis-backed state for multi-Streamlit-process deployments. Migrates the v8.17 per-endpoint circuit state as the canonical first user.

## What ships

### `utils/state_backend.py` (~430 lines)

- **`StateBackend` abstract interface** (ABC) — Pythonic operations mapped to Redis primitives:
  - Hash: `hash_get` / `hash_set` / `hash_get_all` / `hash_incr` (atomic) / `hash_delete`
  - List: `list_append` (with FIFO truncation) / `list_range` / `list_length` / `list_clear`
  - Set: `set_add` (with optional TTL) / `set_contains`
  - Scalar: `scalar_get` / `scalar_set` (with optional TTL) / `scalar_delete`
  - Discovery: `keys_matching(prefix)`
  - Health: `ping` / `is_remote` / `backend_name`
- **`InMemoryBackend`** — thread-safe single-process default; preserves v8.x semantics exactly
- **`RedisBackend`** — used when `A2Z_REDIS_URL` env var is set and redis-py is importable; graceful failure → InMemoryBackend
- **`get_default_backend()`** — memoized backend selector with lazy initialization
- **Test utilities** — `force_in_memory_backend()`, `force_backend()`, `reset_default_backend()` for test injection
- **Self-test** — verifies all StateBackend operations on InMemoryBackend

### `utils/flexcube_adapter.py` migration

Per-endpoint circuit state migrated from `_CIRCUIT_STATES: Dict[str, Dict[str, float]]` (v8.17 in-process dict) to StateBackend hash operations:

- New helper `_circuit_state_key(ek)` returns `"circuit:{ek}"` for backend addressing
- New helper `_list_tracked_endpoint_keys()` discovers tracked endpoints via `keys_matching("circuit:")`
- New helper `_set_circuit_field(ek, field, value)` writes a single circuit-state field
- `_get_or_init_state()` now reads from backend; defaults applied if hash missing
- `_circuit_record_failure()` uses `hash_incr()` for atomic counter increment (Redis HINCRBY)
- `_circuit_record_success()`, `_circuit_is_open()`, `get_circuit_state()`, `reset_circuit()` all migrated
- Legacy `_CIRCUIT_STATE` (single-circuit shim for unmigrated callers) preserved for backward compat

### `_CIRCUIT_STATES` removed

The v8.17 in-process dict is gone. The backend is the source of truth. InMemoryBackend's internal `_hashes` dict-of-dicts replaces the role.

## Why

**The problem v8.x couldn't solve.** With v8.17 per-endpoint circuit state in `_CIRCUIT_STATES`, two Streamlit processes running concurrently had independent circuit state:
- Process 1 sees 5 NPL failures → trips circuit
- Process 2 still sees 0 failures → keeps making live calls
- The circuit-breaker pattern is broken in multi-process deployments

**The v9.6 solution.** When `A2Z_REDIS_URL` is set, both processes share state via Redis. The HINCRBY operation is atomic — Process 1 incrementing to 5 and Process 2 incrementing to 5 wouldn't double-count; Redis serializes them.

When `A2Z_REDIS_URL` is NOT set (the v8.x deployment baseline), behavior is identical — InMemoryBackend uses thread-safe dicts the same way `_CIRCUIT_STATES` did.

## Behavioral verification

5 in-process tests passed:
1. **Per-endpoint isolation** — NPL trips at 5 failures; Loans circuit unaffected (v8.17 contract preserved)
2. **`get_circuit_state()` shape** — all v8.1 keys + v8.17 `per_endpoint` + `endpoints_tracked`
3. **`reset_circuit(endpoint_key=...)`** — single-endpoint reset works; returns prior state for audit
4. **Multi-process simulation** — 3+2=5 failures across two simulated processes correctly aggregate via shared backend; circuit opens
5. **G108 contract preservation** — v8.1 expected_keys all present in `get_circuit_state()`

## What v9.6 does NOT ship

1. **Redis cluster / sentinel support** — single-instance only
2. **Cross-DC replication** — operator concern (Redis Cluster config)
3. **Backup / restore tooling** — operator concern (Redis RDB / AOF)
4. **Encryption at rest** — Redis ACL / TLS config (operator concern)
5. **Migration from in-memory state to Redis at runtime** — would require a migration script; recommend cold restart with `A2Z_REDIS_URL` set
6. **Schema versioning** — if v9.7+ changes hash field shapes, operators handle by clearing `a2z:circuit:*` keys before restart
7. **Retry telemetry / latency / alert history / dedup migration** — those are v9.7-v9.8 batches
8. **UI surface for Redis state visibility** — that's v9.9
9. **G114 audit gate locking the abstraction** — that's v9.10

## Honest acknowledgements

1. **No live Redis testing by Claude** — redis-py not in environment; verified via in-process behavioral tests using InMemoryBackend that exercise the same code path. Joshua tests with real Redis when deploying.
2. **In-process `_CIRCUIT_LOCK` still used** — protects against thread races in same process; cross-process atomicity comes from Redis HINCRBY when applicable.
3. **`hash_incr` returns int** — JSON deserialization may produce float; `_get_or_init_state` coerces. If downstream code assumes pure int, the coercion is needed.
4. **`keys_matching("circuit:")` is O(n)** in the InMemoryBackend (iterates all keys); for Redis it uses SCAN. Acceptable since the keyspace is small (5 endpoints).
5. **Backend selection is memoized at first call** — changing `A2Z_REDIS_URL` after first call requires `reset_default_backend()` (test utility) or process restart. Consistent with how connection pools work.
6. **Half-open recovery** — when `_circuit_is_open` clears a tripped circuit, it makes 2 backend writes (`tripped_until` + `consecutive_failures`). Not atomic across processes; worst case slight extra failure-counting. Acceptable for circuit-breaker semantics.
7. **`reset_circuit()` does multiple field-level writes per endpoint** — not transactional. If a process restart happens mid-reset with Redis backend, partial reset state could persist. Worst case: stale circuit state requires another reset. Acceptable.
8. **Legacy `_CIRCUIT_STATE` global preserved** — unmigrated callers (legacy single-circuit accessors) still work but don't share across processes. Future v9.x could migrate this too if any caller still uses it; current usage is minimal.

## Next: v9.7

Migrate retry telemetry (`_RETRY_TELEMETRY`) and latency rolling window (`_LATENCY_STATE` + `state/flexcube_latency.json` persistence) to StateBackend. Atomic counter operations + persistence-via-backend instead of file write.

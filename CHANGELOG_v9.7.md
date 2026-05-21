# CHANGELOG v9.7 — Retry telemetry migration to StateBackend

**Audit:** 113/113 PASS — **60th consecutive clean.** ⭐ (60-streak milestone)

## What

Migrates v8.19 per-endpoint retry telemetry (`_RETRY_TELEMETRY: Dict[str, Dict[str, int]]`) from in-process dict to StateBackend hash operations. Each counter increment uses atomic `hash_incr()` (Redis HINCRBY when remote).

## Changes

- New helper `_retry_state_key(ek)` returns `"retry:{ek}"` for backend addressing
- New helper `_list_tracked_retry_endpoints()` discovers tracked endpoints via `keys_matching("retry:")`
- New helper `_get_retry_counters(ek)` reads all 5 counter fields, defaulting missing to 0
- `_record_retry_outcome()` uses 2-3 atomic `hash_incr()` calls per outcome
- `get_retry_telemetry()` reads from backend; preserves shape exactly
- `reset_retry_telemetry()` deletes hash keys via `hash_delete()`
- `_RETRY_TELEMETRY` global dict and `_get_or_init_retry()` helper REMOVED

## Behavioral verification

Same 4-outcome scenario as v8.19's original test:
- 3 Loans outcomes: success-no-retry, success-after-2-retries, fail-after-2-retries
- 1 NPL outcome: success-after-1-retry
- Result: `Loans: total=3, retries=4, recovery_pct=50.0` (identical to v8.19)
- Summary: `requests_total=4, retries_triggered=5, recovery_pct=66.7` (identical to v8.19)

Multi-process simulation:
- 2 simulated processes each record outcomes via shared backend
- Atomic `hash_incr()` correctly aggregates: 2+1=3 requests total
- In real Redis: HINCRBY guarantees this atomicity across processes

## v8.19 semantics preserved

| Property | v8.19 | v9.7 |
|---|---|---|
| Per-endpoint counters (5 fields) | ✓ | ✓ |
| Recovery rate calculation | ✓ | ✓ |
| Avg retries per request | ✓ | ✓ |
| Summary aggregation | ✓ | ✓ |
| Per-endpoint reset | ✓ | ✓ |
| Cross-process atomicity | ✗ in-process only | ✓ via Redis HINCRBY |

## Honest acknowledgements

1. **`_record_retry_outcome` makes 2-3 backend calls per outcome.** For Redis: 2-3 round trips per request. Acceptable since this happens once per FLEXCUBE call (typically 100-1000 RPS at most). Future optimization could batch via Redis pipeline.
2. **In-process `_RETRY_TELEMETRY_LOCK` retained** — protects against thread races within same process; cross-process atomicity comes from `hash_incr` Redis HINCRBY.
3. **No persistence layer for in-memory case** — InMemoryBackend doesn't write to disk. Process restart loses telemetry. v8.x had the same behavior — telemetry was never disk-persisted (only latency was).
4. **Reset is non-atomic across multiple endpoints** — `reset_retry_telemetry()` with no key argument iterates and deletes per-endpoint. If process crashes mid-reset, partial reset state persists. Worst case: another reset call fixes it. Acceptable.
5. **`_get_retry_counters` reads 5 fields then casts to int** — JSON deserialization may produce other numeric types; explicit cast preserves int contract.
6. **No alerting on telemetry trends** — observability counter exists but doesn't publish to event_bus or alerts when recovery rate drops. Future v9.x candidate.

## Next: v9.8

Migrate latency rolling window + alert history + event-bus dedup to StateBackend in a single batch. After v9.8, all multi-process state is unified through the abstraction.

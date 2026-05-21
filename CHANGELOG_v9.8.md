# CHANGELOG v9.8 — Latency + alert history + dedup migration

**Audit:** 113/113 PASS — **61st consecutive clean.**

## What

Completes the v9.6-v9.8 state-migration phase by routing the remaining three multi-process state surfaces through StateBackend. After v9.8, ALL v8.x in-process global state has been migrated to the abstraction.

## Changes

### `utils/flexcube_adapter.py` — latency rolling window

- `_LATENCY_SAMPLES: Dict[str, list]` REMOVED
- Backend key prefix `latency:`; each endpoint's samples become a backend list with FIFO truncation at `LATENCY_WINDOW_SIZE=200`
- `_record_latency()` uses `list_append(max_length=...)` for atomic FIFO
- `get_latency_state()` reads via `list_range()` per endpoint
- File persistence (`flexcube_data/latency_state.json`) preserved for **InMemoryBackend only**; skipped when `is_remote()` since Redis has its own durability (RDB/AOF)
- `_load_latency_from_disk` now populates the backend on first call

### `utils/smart_alerts.py` — alert history

- `_ALERT_HISTORY: List[Dict]` REMOVED
- Backend key `alert_history` is a backend list of JSON-serialized alert dicts with FIFO truncation at `ALERT_HISTORY_MAX_ENTRIES=500`
- `record_alert_history()` uses `list_append`; idempotency check reads existing entries first
- `acknowledge_alert()` reads full list, modifies matching entry, rewrites entire list (O(n) — acceptable since acks are operator-driven and rare)
- File persistence preserved for InMemoryBackend; skipped for Redis

### `utils/event_bus.py` — dedup statistics

- `_DEDUP_STATS: Dict[str, Dict[str, int]]` REMOVED
- Backend key prefix `dedup:`; each topic becomes a hash with 3 counter fields (`total_publish_calls`, `dedup_hits`, `unique_published`)
- `publish()` uses 1-2 atomic `hash_incr()` calls per publication
- `get_dedup_stats()` reads via `keys_matching("dedup:")` + `hash_get_all()` per topic

## Behavioral verification

All four scenarios pass with identical numbers to v8.x originals:

```
✓ Latency: count=3, success=66.7%, p50=200, p95=300 (matches v8.2)
✓ Alert history: 2 entries, 1 acked, idempotency on alert_id (matches v8.25)
✓ Dedup stats: total=4, hits=1, unique=3 (matches v8.23)
✓ Multi-process atomic counter increments verified
```

## v9.6-v9.8 cumulative migration

| State | v8.x location | v9.x backend key prefix | Multi-process safe |
|---|---|---|---|
| Per-endpoint circuit | `_CIRCUIT_STATES` (v8.17) | `circuit:` | ✓ via HINCRBY |
| Retry telemetry | `_RETRY_TELEMETRY` (v8.19) | `retry:` | ✓ via HINCRBY |
| Latency rolling window | `_LATENCY_SAMPLES` + JSON file (v8.2/v8.24) | `latency:` | ✓ via RPUSH+LTRIM |
| Alert history | `_ALERT_HISTORY` + JSON file (v8.25) | `alert_history` | ✓ via RPUSH (acks rewrite) |
| Dedup stats | `_DEDUP_STATS` (v8.23) | `dedup:` | ✓ via HINCRBY |

The InMemoryBackend (default) preserves v8.x semantics exactly. Setting `A2Z_REDIS_URL=redis://host:6379/0` flips to RedisBackend without code changes.

## Honest acknowledgements

1. **Acknowledgement of an alert is O(n)** — must read+rewrite entire list. Acceptable because acks are infrequent operator actions; for high-volume scenarios consider a separate `ack:` hash keyed by alert_id alongside the list.
2. **Latency file persistence skipped for Redis backend** — when `A2Z_REDIS_URL` is set, the JSON file becomes stale. Recommend operators clear `flexcube_data/latency_state.json` after switching to Redis. Alternatively a v9.x candidate is to delete the file on first Redis-backend startup.
3. **No data migration tooling** — switching from in-memory to Redis loses existing in-process state. Recommended workflow: cold restart with `A2Z_REDIS_URL` set; circuit/retry/latency rebuild from new traffic; alert history reloads from JSON file once per process if file persists.
4. **`_BUS_LOCK` retained** for in-process consistency of the events cache (`_BUS_CACHE`); cross-process atomicity for dedup counters comes from `hash_incr`. The events cache itself is NOT yet backend-backed — that would be a v10.x candidate (more complex because Event objects have type structure).
5. **JSON serialization round-trips for backend storage** — when InMemoryBackend reads back a list value, the dict structure is preserved exactly; for RedisBackend, the JSON serialize/deserialize cycle may upgrade `int` to `float` in edge cases. Tests cover the common paths.
6. **No alerting on dedup-rate trends** — observability counters exist but aren't wired into the alert system. v9.x candidate.

## Next: v9.9

Admin UI surface for Redis-backed state. Add a panel in `pages/7_admin.py` System section showing:
- Backend type (in_memory / redis)
- Connection state (ping result)
- Key statistics (count of circuit / retry / latency / dedup keys)
- Cross-process state verification (whether two simulated processes see the same data)

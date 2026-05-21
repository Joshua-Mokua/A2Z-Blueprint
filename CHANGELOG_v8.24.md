# CHANGELOG v8.24 — Latency persistence (closes v8.6 ack #10)

**Audit:** 111/111 PASS — **50th consecutive clean.** ⭐

## What

Closes v8.6 retrospective ack #10. Latency telemetry rolling window now persists to disk so observability survives process restarts (Streamlit redeployment, container restart).

## Changes

- New constants `LATENCY_PERSIST_PATH` (default: `flexcube_data/latency_state.json`) + `LATENCY_PERSIST_INTERVAL_SECONDS = 30.0` (write throttle)
- New flag `_LATENCY_LOADED` — one-shot to load disk state on first `_record_latency()` call per process
- New `_load_latency_from_disk()` — defensive JSON loader; silently degrades on missing/corrupt/permission errors; never fails startup
- New `_persist_latency_to_disk()` — atomic write via tmp+replace; throttled to ≥30s between writes; silently degrades on disk errors
- `_record_latency()` updated to load on first call + opportunistically persist after recording
- `reset_latency_state()` extended to also delete the on-disk file so reset survives restart

## Why

Before v8.24:
- Operator runs system for hours, accumulates p50/p95/p99 telemetry
- Streamlit container redeployed (typical: weekly ops cycle)
- All telemetry lost; observability "starts fresh" at every restart
- Trend analysis impossible without external sink

After v8.24:
- Same scenario, redeployment preserves last 200 samples per endpoint
- p50/p95/p99 reflect continuous history across restarts
- 30s throttle bounds I/O cost; atomic writes prevent corruption

## Behavioral test

```
=== Process 1: record 3 samples ===
  Endpoints: 2, total_calls: 3 ✓

=== Simulate process restart: clear in-memory + reset _LATENCY_LOADED ===

=== Process 2: record 1 new sample (triggers disk load on first record) ===
  Endpoints: 2, total_calls: 4  ←  3 reloaded from disk + 1 new
  
=== Test reset clears disk file ===
  reset_latency_state() called
  LATENCY_PERSIST_PATH.exists() → False ✓
```

## v8.6 backlog burndown — now 10/12 closed (83%)

| # | Ack | Status |
|---|---|---|
| 1-9 except 10-12 | (closed v8.7-v8.23) | ✅ |
| **10** | **Latency persistence** | **✅ closed (v8.24)** |
| 11 | Alert-history persistence | ⏳ |
| 12 | Multi-language alerts (i18n) | ⏳ |

## Honest acknowledgements

1. Persistence is best-effort — disk full / permission errors silently degrade telemetry but never fail the request path; correct trade-off for observability layer.
2. 30-second throttle means up to 30s of recent samples can be lost on a hard crash; acceptable for telemetry (not transactional data).
3. JSON serialization of full window: ~5KB per endpoint × 5 endpoints = ~25KB per write; bounded growth; cheap.
4. Atomic write via tmp+replace prevents corruption mid-write but doesn't survive partial-disk-write scenarios (kernel-level fsync would; not added because telemetry isn't critical enough to warrant it).
5. Disk format is JSON object with `saved_at_iso` + `endpoints` dict; if format ever changes, `_load_latency_from_disk()` falls back to empty (safe default).
6. No automatic compaction or rotation; the rolling window itself is bounded so the file never grows unbounded.
7. Concurrent processes writing the same file (multi-instance deployments) would race on the atomic write; last-writer-wins; acceptable for telemetry where exact-correctness isn't required.

## Next: v8.25 — Alert-history persistence (ack #11)

Same pattern applied to `utils/smart_alerts.py` so alert history (which alerts fired, when, were they acknowledged) survives process restart.

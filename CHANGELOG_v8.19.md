# CHANGELOG v8.19 — Retry-count telemetry (closes v8.6 ack #9)

**Audit:** 110/110 PASS — **45th consecutive clean.**

## What

Closes v8.6 retrospective ack #9 by adding per-endpoint retry telemetry to `utils/flexcube_adapter.py`. Operators can now see how often retry/circuit-breaker pattern is recovering transient failures.

## Changes

- New `_RETRY_TELEMETRY` dict-of-dicts keyed by endpoint_key
- 5 counters per endpoint: requests_total, retries_triggered, succeeded_no_retry, succeeded_after_retry, failed_after_retries
- 2 derived metrics: `retry_recovery_rate_pct` (% of retries that recovered) + `avg_retries_per_request` (overall flakiness)
- New `_record_retry_outcome(endpoint_path, retries_used, succeeded)` instrumentation in `_live_request()` retry loop
- New `get_retry_telemetry()` accessor returning per-endpoint + aggregate summary
- New `reset_retry_telemetry(endpoint_key=None)` admin function with audit trail

## Behavioral test

```
After 4 simulated outcomes (3 Loans: success/retry-success/retry-fail; 1 NPL: retry-success):
  PortfolioService/Loans: total=3, retries=4, recovery_pct=50.0, avg_retries=1.33
  PortfolioService/NPL:   total=1, retries=1, recovery_pct=100.0, avg_retries=1.0
  Summary: total=4, retries=5, recovery_pct=66.7, avg_retries=1.25
✓ All assertions pass — recovery rate calculated correctly.
```

## v8.6 backlog burndown — now 7/12 closed (58%)

| # | Ack | Status |
|---|---|---|
| 1-6 | (closed v8.7-v8.17) | ✅ |
| **9** | **Retry-count telemetry** | **✅ closed (v8.19)** |
| 7, 8, 10, 11, 12 | open | ⏳ |

## Honest acknowledgements

1. No live FLEXCUBE testing — verified via in-process behavioral test calling `_record_retry_outcome()` directly.
2. Counters are in-memory; lost on process restart (matches v8.1-v8.17 pattern).
3. Recovery rate denominator excludes successes-without-retry (it measures retry effectiveness, not overall success).
4. No automatic alerting when `retry_recovery_rate_pct` drops below threshold; future v8.20+ enhancement could publish to event_bus.
5. `_record_retry_outcome()` is a side-effect call after the request completes; adds ~5μs overhead per request — negligible.
6. Counters never roll over (Python int is arbitrary precision); future v9.x could add periodic rotation if memory becomes a concern.

## Next: v8.20 — Per-endpoint timeout config (ack #7)

Currently single `batch_seconds` timeout for all endpoints. Some endpoints (e.g. NPL aggregate) may need longer timeouts than others (e.g. customer lookup). Per-endpoint override config.

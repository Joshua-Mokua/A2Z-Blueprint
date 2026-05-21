# CHANGELOG v8.21 — Combined UI surface for retry telemetry + per-endpoint timeouts

**Audit:** 110/110 PASS — **47th consecutive clean.**

## What

Closes the canonical engine-then-UI pattern for both v8.19 (retry telemetry) and v8.20 (per-endpoint timeouts) in a single batch. Adds 2 new expanders to `pages/91_systems_view.py` after the existing v8.2 latency telemetry expander.

## Changes

### 1. Retry telemetry expander (🔁 v8.19 surface)

- Renders only when `requests_total > 0` (silent in synthetic mode)
- Header shows: total requests + total retries + recovery rate %
- Table columns: Endpoint / Requests / Retries / Avg retries / 1st-try OK / Recovered / Failed / Recovery %
- Recovery rate explanation in caption (high = retries doing their job; low = root cause investigation needed)

### 2. Per-endpoint timeout config expander (⏱️ v8.20 surface)

- Always rendered (config is static, not runtime-derived)
- Header shows: count of endpoint overrides
- Table columns: Endpoint / Timeout (s)
- Caption explains fallback to default `batch_seconds` / `rest_seconds` for endpoints not listed
- Footer caption explains how to override (edit `_default_config()` or save custom config)

## Imports added

```python
from utils.flexcube_adapter import (..., 
                                      get_retry_telemetry as _fc_retry,
                                      get_config as _fc_config)
```

## Honest acknowledgements

1. No live Streamlit deployment verification by Claude — UI compile-tested.
2. Per-endpoint timeout config is read-only in this batch; UI editing of overrides is a v9.x candidate.
3. Recovery rate denominator excludes 1st-try successes (it specifically measures retry effectiveness).
4. Both new expanders are inside the existing `try / except: pass` block — defensive against module loading issues.
5. Tables use pandas DataFrame (already imported as `pd` on this page); no new dependencies.

## Status snapshot at end of v8.18-v8.21 sequence

- **v8.18**: Per-endpoint circuit UI surface ✓
- **v8.19**: Retry-count telemetry engine (ack #9) ✓
- **v8.20**: Per-endpoint timeout config engine (ack #7) ✓
- **v8.21**: Combined UI surface for v8.19 + v8.20 ✓

**v8.6 retrospective backlog: 8/12 closed (67%)** — 4 acks remain (#8 event-bus dedup, #10 latency persistence, #11 alert-history persistence, #12 multi-language alerts).

## Next: v8.22 — G111 audit gate locking v8.17-v8.21 resilience contracts

Adds new audit gate that verifies:
- `get_retry_telemetry()` returns expected dict shape
- `endpoint_timeouts` config dict exists with required structure
- `reset_retry_telemetry()` is importable
- `_record_retry_outcome()` is importable

Pushes audit suite 110 → 111 gates. Locks the v8.17 + v8.19 + v8.20 resilience improvements as permanent invariants. Closes the 5-batch v8.18-v8.22 arc.

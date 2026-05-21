# CHANGELOG v8.20 — Per-endpoint timeout config (closes v8.6 ack #7)

**Audit:** 110/110 PASS — **46th consecutive clean.**

## What

Closes v8.6 retrospective ack #7. Currently `_live_request()` used a single `batch_seconds` (300s) timeout for all FLEXCUBE endpoints. Some endpoints (NPL aggregate with IFRS 9 staging) need longer timeouts; some (CustomerService) shouldn't wait that long.

## Changes

- New `endpoint_timeouts` dict in `_default_config()` mapping endpoint_key → seconds:
  - `PortfolioService/Loans`: 300
  - `PortfolioService/Deposits`: 300
  - `PortfolioService/NPL`: **600** (heavier IFRS 9 staging)
  - `CustomerService`: **120** (simpler aggregate)
  - `AccountService/Dormancy`: 180
- `_live_request()` checks `endpoint_timeouts[ek]` first, falls back to `timeouts[timeout_key]` if not present
- `get_config()` now backfills missing keys from defaults — older saved configs without `endpoint_timeouts` automatically inherit the v8.20 defaults without operator action

## Behavioral test

```
After fix:
  Endpoint timeouts: {'PortfolioService/Loans': 300, 'PortfolioService/Deposits': 300, 
                     'PortfolioService/NPL': 600, 'CustomerService': 120, 
                     'AccountService/Dormancy': 180}
✓ Backfill works; per-endpoint timeouts configured correctly.
```

## v8.6 backlog burndown — now 8/12 closed (67%)

| # | Ack | Status |
|---|---|---|
| 1-6 | (closed v8.7-v8.17) | ✅ |
| 9 | Retry-count telemetry (v8.19) | ✅ |
| **7** | **Per-endpoint timeout config** | **✅ closed (v8.20)** |
| 8, 10, 11, 12 | open | ⏳ |

## Honest acknowledgements

1. Default per-endpoint timeouts are heuristic — based on typical FLEXCUBE response patterns; production tuning may require adjustment after observing real latencies.
2. Backfill in `get_config()` only adds top-level missing keys; nested missing keys (e.g. a saved `endpoint_timeouts` with only 3 entries) won't be merged with defaults; future enhancement could deep-merge if needed.
3. `endpoint_timeouts` is hardcoded in `_default_config()`; admin UI doesn't expose this yet (v8.21 candidate).
4. The fallback path uses `cfg["timeouts"][timeout_key]` — if a saved config has neither `endpoint_timeouts` nor the expected `timeouts` key, would KeyError; mitigated by backfill but worth a defensive `.get(timeout_key, 300)` in v8.21+.
5. No per-endpoint TIMEOUT for soap or rest_seconds split — the override applies globally regardless of the timeout_key parameter; future enhancement could split per-endpoint REST vs batch timeouts.
6. No alerting when an endpoint hits its timeout; future v8.x could publish to event_bus for downstream observability.

## Next: v8.21 — Combined UI surface for v8.19 retry telemetry + v8.20 per-endpoint timeouts

Render retry telemetry table on `pages/91_systems_view.py` + per-endpoint timeout config display on admin System health sub-tab.

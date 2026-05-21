# CHANGELOG v8.18 — Per-endpoint circuit UI surface

**Audit:** 110/110 PASS — **44th consecutive clean.**

## What

Closes v8.17's canonical engine-then-UI pattern by adding a per-endpoint circuit table to `pages/91_systems_view.py`.

## Changes

- New expander on FLEXCUBE status block: "🎯 Per-endpoint circuit state (v8.17)"
- Auto-expands when any endpoint circuit is open
- Renders pandas DataFrame: Endpoint / Consecutive failures / Status / Reopens-in countdown
- Selective per-endpoint reset buttons (only shown for endpoints with non-zero failures or open state)
- Each button calls `reset_circuit(endpoint_key=ek)` — clears one endpoint without affecting others

## Operator workflow

When operators open the systems-view page during a partial FLEXCUBE outage:
1. Aggregate banner (existing) shows "circuit OPEN" if any endpoint tripped
2. Per-endpoint expander auto-opens, shows which specific endpoints failed
3. Operators reset just the affected endpoint(s) without disrupting healthy ones

## Honest acknowledgements

1. No live Streamlit deployment verification by Claude — UI compile-tested.
2. Reset buttons use `key=` slugs derived from endpoint key (with `/` → `_`); collision unlikely with current 5 endpoints.
3. Auto-expand triggers on `is_open=True` only; consecutive failures > 0 (warning state) does NOT auto-expand to avoid noise during transient blips.
4. Maximum 3 buttons per row via `min(len(troubled), 3)` columns; if 4+ endpoints simultaneously troubled, wraps to next row.
5. `import pandas as _pd` happens inside the expander block; ~5ms cost only when expander renders; acceptable.

## Next: v8.19

Retry-count telemetry engine (closes v8.6 ack #9). ~50 lines in flexcube_adapter; per-endpoint counters for retries-triggered, retries-succeeded, retries-failed.

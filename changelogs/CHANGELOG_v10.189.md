# CHANGELOG — v10.189

**Drop:** v10.189
**Standard:** ENH-165 — Executive Resource Optimization Dashboard
**Module:** Resource Optimization
**Status:** active

---

## Summary

Tenth and final standard of the Resource Optimization arc — the
capstone aggregator. Composes data from all 9 prior arc engines
(ENH-156..164) into a single board-level read-only `ExecutiveDashboard`
snapshot with a composite `resource_optimization_health_index` (0–100).

The engine is strictly read-only. It calls `board_summary()` on each
upstream engine and never mutates anything. When an engine isn't
attached, its dashboard section comes back with `available=False` and
a note explaining why — no fabricated data, no fallback fiction.

The composite health index publishes only when at least 2 of the 4
sub-indices (TSL / Utilisation / Wellbeing / Culture) are available.
Below that threshold, the composite is `None` and the operator sees
explicitly that they have insufficient signal coverage.

This drop closes ENH-156..165. The arc closure ceremony with G156/G157
audit gates and the cockpit page lands at v10.190.

---

## Files added

- `utils/executive_resource_dashboard.py` — engine (~370 LOC)
- `tests/test_executive_resource_dashboard_v10_189.py` — 43 tests across
  10 classes

## Files modified

- `utils/standards_registry.py` — ENH-165 set to `status='active'`,
  `affected_engines=('executive_resource_dashboard',)`,
  `implementation_batch='v10.189'`
- `pages/7_admin.py` — Tier 32 Resource Optimization Suite gains its
  tenth and final entry under `executive_resource_dashboard`

## Audit gates

No new gates this drop (closure-tier gates G156/G157 land at v10.190
with the arc closure ceremony). Audit holds at **155/155 PASS = 100.0%**.

---

## Engine surface

### Construction

All 9 upstream engines are optional keyword arguments:

```python
ExecutiveResourceDashboard(
    work_mode_engine=None,            # ENH-156
    workload_forecasting_engine=None,  # ENH-157
    tsl_engine=None,                  # ENH-158
    balancing_engine=None,            # ENH-159
    utilization_engine=None,          # ENH-160
    wellbeing_engine=None,            # ENH-161
    hybrid_simulator=None,            # ENH-162
    investment_case_engine=None,      # ENH-163
    integrity_culture_engine=None,    # ENH-164
)
```

### Outputs

`ExecutiveDashboard.snapshot(snapshot_id)` returns:

- `sections` — tuple of 9 `DashboardSection` records, one per upstream
  engine. Each section has `section_id`, `title`, `available` (bool),
  `payload` (the engine's `board_summary()` output or `None`), and
  `notes` (which standard it sources from).
- `resource_optimization_health_index` — 0-100 composite, or `None` if
  fewer than 2 sub-indices are available.
- `health_index_components` — flat dict of available sub-indices only.
- `health_index_weights` — full weights dict (0.25 each for tsl /
  utilisation / wellbeing / culture).
- `n_engines_attached`, `n_engines_available` — coverage counters.
- `snapshot_at` — ISO timestamp.

### Sub-index extraction

Per upstream engine:

| Engine | Sub-index name | Source key in board_summary | Method |
|---|---|---|---|
| ENH-158 TSL | `tsl_health` | `plans_by_outcome['exact']` / `n_plans` × 100 |
| ENH-160 Utilisation | `utilization_health` | `current_band_distribution['balanced']` / total × 100 |
| ENH-161 Wellbeing | `wellbeing_health` | `bands_distribution`: green=100, amber=50, red=0 weighted avg |
| ENH-164 Culture | `culture_health` | `bands_distribution`: strong=100, dev=75, at_risk=50, crit=0 weighted avg |

### Composite math

Weighted average over **available** components only, with the weights
renormalised to the available subset. So if only wellbeing and culture
are available, the composite is `(wb*0.25 + cult*0.25) / 0.5` = simple
average of the two.

`MIN_COMPONENTS_FOR_COMPOSITE = 2` — below that, the composite is
`None` rather than a single-source pseudo-index.

### Graceful degradation

Three failure modes, all tested:

1. **Engine not attached** → section.available = False, payload None
2. **Engine attached but `board_summary()` raises** → section.available
   = False (handled by `_safe_call`)
3. **Engine attached but no `board_summary` method** → section.available
   = False

The dashboard never crashes because of an upstream issue.

### Honest deferrals (declared in `board_summary()`)

1. **REAL_TIME_REFRESH** — snapshot at call time only. No streaming, no
   push notifications. Operator calls `snapshot()` to refresh.
2. **DRILL_DOWN_NAVIGATION** — aggregation engine produces data only.
   Team-level navigation lives in the cockpit UI (v10.190).
3. **PREDICTIVE_FORECAST_OVERLAY** — each upstream engine produces its
   own outlook (e.g. ENH-157 forecasts). The dashboard does not blend
   or re-forecast.
4. **CUSTOM_KPI_DEFINITIONS** — KPIs are fixed. Operators extend by
   composing with other module dashboards in the cockpit.

---

## Validation

### Tests

```
PASSED: 43 | FAILED: 0
```

Coverage spans:

- `TestModuleShape` — public surface, weights sum=1.0 (5 tests)
- `TestRegistry` — ENH-165 active and wired (3)
- `TestHubIntegration` — Tier 32 entry + ordering (2)
- `TestGracefulDegradation` — empty dashboard, all-9 sections, distinct
  IDs, no fabricated components (5)
- `TestSubIndexExtraction` — TSL / utilisation / wellbeing / culture
  sub-indices populate from real engines (4)
- `TestCompositeMath` — single → None, two → publishes, full → in
  range, weights recorded, components-only-includes-available (5)
- `TestSnapshotSemantics` — snapshot_id required, snapshots accumulate,
  no upstream mutation (3)
- `TestSafeCallGracefulFailure` — failing board_summary, missing
  method (2)
- `TestSerialization` — dashboard + section to_dict (2)
- `TestHonestDeferrals` — all 4 deferrals + reg basis + weights
  exposed (3)
- `TestNoRegression` — ENH-156..164 still active (9)

### Audit

```
Score: 155/155 gates = 100.0% — PASS
```

---

## What this unlocks

**v10.190 — Resource Optimization MODULE CLOSURE CEREMONY** (next).
That drop will:

- Add `pages/29_resource_optimization_cockpit.py` — the Streamlit
  cockpit consuming this dashboard
- Add `utils/api_resource_optimization.py` — REST endpoints
- Add Tier 4F closure marker
- Wire audit gates G156 + G157
- Bump audit to 157/157 PASS

This will be the 4th fully-closed module on the platform after Treasury
(v10.155 G150/G151), AML/Compliance (v10.169 G152/G153), and Legal
(v10.179 G154/G155).

---

## Notes

- Engine is pure Python, deterministic, no dependencies on optional
  upstream engines at construction time (but graceful when they're
  absent).
- The `_safe_call` helper is the linchpin of graceful degradation — it
  catches any exception from upstream `board_summary()` calls and
  returns the default. The dashboard cannot be brought down by a
  flaky upstream.
- Regulatory basis: BSC all four perspectives + CBK Prudential
  Guideline CBK/PG/01 (governance — board MIS).
- This is the 213th active standard on the platform.

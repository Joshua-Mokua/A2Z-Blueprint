# CHANGELOG v10.181 — ENH-157 Workload Forecasting & Prediction Engine

## What this drop ships

Second standard of the Resource Optimization arc. Greenfield —
inspect-first found unrelated `cash_forecasting.py` and
`rwa_optimization.py`; nothing that forecasts workload on
operational channels.

`utils/workload_forecasting.py` (~470 LOC) provides per-channel
workload forecasting (transaction volume, call volume, branch
footfall, RM activity, settlement load) over configurable
horizons with confidence intervals.

## Engine surface

- `ForecastMethod` enum: SEASONAL_NAIVE, LINEAR_TREND, EXTERNAL
- `HorizonUnit` enum: DAY, WEEK, MONTH
- `ForecastSnapshot` frozen dataclass — immutable record of a
  single forecast event
- Two built-in deterministic forecasters:
  - `seasonal_naive_forecaster` — weekly seasonality default
    (configurable `season_length`), period-over-period variance
    bands, falls back to last-value-repeat when history shorter
    than season
  - `linear_trend_forecaster` — OLS fit, residual stddev bands,
    falls back to flat when history has only one point
- `register_forecaster(name, callable)` — pluggable hook for
  external forecasters (the ML model team's swap-in point)
- `evaluate_snapshot()` — back-testing: MAPE, WAPE, prediction
  interval coverage against `record_actual()` data
- `board_summary()` with regulatory_basis + 4 honest deferrals

## Honest deferrals (named in `board_summary()`)

| Deferral | Status |
|---|---|
| ML_BACKBONE_XGBOOST | Standard description claims "XGBoost 0.99 correlation" — engine ships SeasonalNaive + LinearTrend baselines only; ML hook open via `register_forecaster()` |
| WEATHER_HOLIDAY_REGRESSORS | No external regressor enrichment |
| AUTO_RETRAIN_SCHEDULE | Caller controls retrain cadence |
| HIERARCHICAL_RECONCILIATION | Channels forecast independently |

This is the right honesty discipline: the standard's description
mentions XGBoost and a 0.99 correlation figure, but no model
weights, training data, or pipeline exist in the repo. Shipping
mock XGBoost would be fabrication. Instead, the engine names the
gap and exposes the integration hook.

## Confidence intervals on every point

Every forecast point is `(date, point, lower, upper)`. The
invariant `lower ≤ point ≤ upper` is asserted in tests. Empty or
zero-variance history produces degenerate bands (point = lower =
upper) — operators see the absence of variability rather than a
fabricated band.

## Snapshot immutability

`ForecastSnapshot` is `@dataclass(frozen=True)`. Once a forecast
is created, it cannot be mutated. Re-forecasting creates a new
snapshot with a new ID. Test `TestSnapshotImmutability`
verifies the frozen contract.

## Tests — 25 across 9 classes

- `TestModuleShape` (1)
- `TestRegistry` (1) — ENH-157 active, batch v10.181
- `TestHubIntegration` (1)
- `TestHistoryIngestion` (4) — count, negative reject, empty
  channel reject, sort order
- `TestForecasters` (5) — seasonal naive, short-history fallback,
  linear trend extrapolation, single-point flat, empty-history
  reject for both
- `TestForecastEngine` (5) — snapshot creation, zero horizon
  reject, missing channel reject, external registration,
  unregistered external reject
- `TestBackTesting` (4) — negative actual reject, MAPE/coverage
  computation, no-overlap path, unknown snapshot reject
- `TestSnapshotImmutability` (1)
- `TestHonestDeferrals` (1) — all 4 deferrals named, XGBoost
  named in deferral description
- `TestNoRegression` (2) — audit still 155/155, v10.180 still works

**25/25 PASS.**

## Apply order

1. `utils/workload_forecasting.py` — new engine
2. `utils/standards_registry.py` — ENH-157 active, batch v10.181
3. `pages/7_admin.py` — Tier 32 entry appended after ENH-156
4. `tests/test_workload_forecasting_v10_181.py` — 25 tests
5. Run audit → 155/155 PASS

## Resource Optimization arc roadmap

| Standard | Engine | Status |
|---|---|---|
| ENH-156 | work_mode_declaration | active (v10.180) |
| ENH-157 | workload_forecasting | **active (v10.181)** |
| ENH-158 | (tsl_optimization) | planned |
| ENH-159 | (cross_channel_balancing) | planned |
| ENH-160 | (utilization_dashboard) | planned |
| ENH-161 | (wellbeing_burnout) | planned |
| ENH-162 | (whatif_scheduler) | planned |
| ENH-163 | (resource_investment_case) | planned |
| ENH-164 | (integrity_culture_score) | planned |
| ENH-165 | (executive_resource_dashboard) | planned |

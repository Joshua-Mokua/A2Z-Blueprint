# CHANGELOG v10.63 + v10.64 — finance arc batches 5/10 + 6/10

**Status:** finance arc progresses to 6/10 standards active.
**Audit:** 134/134 PASS · **G128:** STABLE (329 modules · 832 imports · 3 HARD baseline)
**Active standards:** 131 → **133** / 260 (+2 ENH-253/254)
**Scenario library:** 102 → **110** (+8: 4 PFA + 4 CFO)
**Total self-tests across stack:** 257/257 PASS

---

## v10.63 — ENH-253 Predictive Financial Analytics

### What it does

Diagnostic forecasting + variance analysis + driver decomposition + trend signal engine. Three deterministic forecasting methods plus an ML-hook for caller-supplied predictors. Per Rule 6, when ML cannot run the engine surfaces `ml_disabled=True` with reason — engine NEVER fabricates predictions. Per Rule 7, forecasts and findings are surfaced for operator review; engine never auto-rebudgets, never reallocates capital, never auto-revises on actuals ingestion.

### Module

`utils/predictive_financial_analytics.py` (~830 lines · 20/20 tests · all PASS first run).

### Forecast methods

| Method | Algorithm | Sample size | Confidence |
| --- | --- | --- | --- |
| `LINEAR_TREND` | OLS slope/intercept on time index | min 4; falls back to flat-projection with `ml_disabled` flag | 1.96σ residual band |
| `SEASONAL_NAIVE` | h-step ahead = value from h-periods-ago in prior cycle | min 8 (= season period); falls back to LINEAR_TREND with `ml_disabled` flag | none |
| `EXPONENTIAL_SMOOTHING` | single-exponential, alpha caller-supplied in (0,1] | any | none |
| `ML_HOOK` | caller's `ml_predictor` callable | depends on caller | depends on caller |

When `ML_HOOK` is requested but no `ml_predictor` is supplied, the engine sets `ml_disabled=True` with reason `"ML_HOOK requested but no ml_predictor supplied — falling back to LINEAR_TREND"` and uses the deterministic fallback. **Engine never returns fabricated ML predictions** — Rule 6 contract.

### Variance analysis

3-tier materiality (`IMMATERIAL` < threshold / `MATERIAL` ≥ threshold / `HIGHLY_MATERIAL` ≥ 3× threshold) × 3 directions (`FAVOURABLE` / `UNFAVOURABLE` / `NEUTRAL`). The `higher_is_better` flag on `ActualVsExpected` inverts the direction semantics — for cost metrics, actual < expected is FAVOURABLE.

### Driver decomposition

Surfaces all `DriverContribution` amounts + `explained_kes` + `residual_kes` + `residual_pct_of_total` for sanity check. The residual percentage tells the operator how much of the total variance is unexplained by the named drivers — high residual means the decomposition is incomplete.

### Trend signals

4 `TrendSignal` enums (`UPTREND` / `DOWNTREND` / `FLAT` / `INFLECTION`). FLAT threshold is 1% relative slope. INFLECTION detected via sign-change between first-half slope and second-half slope (requires sample ≥ 2× MIN_SAMPLE_FOR_TREND).

### Rule 1 / Rule 7

- 9 frozen dataclasses including `TimeSeriesPoint` (non-empty period), `ActualVsExpected` (metric_name validated).
- Every `Forecast` surfaces `method_used + horizon + sample_size + ml_disabled + ml_disabled_reason + inputs_used (period strings) + framework_refs`.
- Every `VarianceFinding` surfaces `actual + expected + variance_kes + variance_pct + direction + materiality + threshold + framework_refs`.
- Every `DriverDecomposition` surfaces `total_variance + contributions + explained + residual + residual_pct + framework_refs`.
- Engine never auto-rebudgets, never reallocates capital, never auto-revises forecasts on new actuals, never mutates inputs.
- `_test_engine_does_not_mutate_inputs` verifies frozen contract.

### Scenarios

- **PFA-01 LINEAR_TREND forecast** — 12-month upward-trend history, 3-period horizon continues the trend, `ml_disabled=False`.
- **PFA-02 variance analysis multi-direction** — revenue 5% short = MATERIAL UNFAVOURABLE; opex 10% under with `higher_is_better=False` = FAVOURABLE; provisions 200% over = HIGHLY_MATERIAL.
- **PFA-03 driver decomposition** — total variance 60k = price 80k + volume −40k + mix 10k = 50k explained, 10k unexplained (16.67%).
- **PFA-04 ml_disabled fallback** — ML_HOOK without predictor → `ml_disabled=True` with reason; falls back to LINEAR_TREND deterministic (NOT fabricated ML); 3 forecasts still produced.

16/16 PFA assertions PASS.

### Honest scope notes

1. **No auto-tuned smoothing parameters.** Caller supplies `smoothing_alpha`. ETS / Holt-Winters / state-space methods would auto-tune; this engine doesn't.
2. **No exogenous regressors.** Forecasts are univariate. No support for "forecast revenue conditional on GDP growth + inflation" — that's an ML-hook responsibility.
3. **Confidence bands only on LINEAR_TREND.** Other methods don't produce bands. Caller can wrap with bootstrap / quantile estimation if needed.
4. **No driver attribution math** — engine takes operator-supplied driver contributions verbatim. It doesn't compute price/volume/mix variances from raw data; that's domain-specific bookkeeping the caller does.
5. **Trend INFLECTION uses simple half-vs-half slope sign change.** Misses some real inflections; may flag noise as inflection. Smoothing or change-point detection would be more robust but adds complexity.

---

## v10.64 — ENH-254 Finance Intelligence Dashboard (CFO View)

### What it does

Diagnostic CFO KPI aggregation engine. **Split implementation per v10.46-amended protocol** (matches the pattern used for ENH-245): data layer ships now, UI layer at v10.68 closure cockpit consumes these metrics. Six metric families with thresholds, trend tracking, breach alerts.

### Module

`utils/finance_intelligence_dashboard.py` (~770 lines · 15/15 tests · all PASS first run).

### Six metric families

| Family | KPIs | Thresholds |
| --- | --- | --- |
| **PROFITABILITY** | NIM, ROA, ROE, COST_TO_INCOME | NIM ≥ 4%, ROA ≥ 1.5%, ROE ≥ 15%, C/I ≤ 55% |
| **CAPITAL** | CAR (consumed from ENH-252) | ≥ 14.5% (CBK PG 03 §4) |
| **LIQUIDITY** | LIQ (consumed from ENH-252) | ≥ 20% (CBK PG 04) |
| **GROWTH** | LOAN/DEPOSIT/CUSTOMER growth (only with prior period) | informational, no thresholds |
| **EFFICIENCY** | COST_PER_TRANSACTION, CUSTOMERS_PER_BRANCH | informational, no thresholds |
| **ASSET_QUALITY** | NPL_RATIO, COVERAGE_RATIO | NPL ≤ 6% (CBK guidance), coverage ≥ 70% |

### Threshold status 4-tier

- `OK` — value safely within threshold
- `WARNING` — within 10% of threshold (margin alert before breach)
- `BREACH` — threshold violated
- `NOT_APPLICABLE` — informational metric with no threshold

### Alert severity by family

When a KPI breaches its threshold, an `ExecutiveAlert` fires:
- **CRITICAL** for CAPITAL or LIQUIDITY breaches (regulatory-grade)
- **WARNING** for everything else

The alert carries a `recommended_action_category` — a category like `"review capital plan / RWA optimisation"` or `"review credit policy / collections"`. **Engine deliberately does NOT recommend specific actions** — that's operator policy per Rule 7. The category guides the operator toward the right team/discipline; the actual decision is theirs.

### Rule 1 / Rule 7

- 4 frozen dataclasses: `PeriodFinancials` (15 financial fields with non-empty period + non-negative balance validation), `Kpi` (full inputs_used dict + trend + threshold_status + prior_value + framework_refs), `ExecutiveAlert`, `CfoDashboard` (with `by_family` + `by_threshold_status` aggregates).
- Every `Kpi` surfaces `metric_name + family + period + value + unit + inputs_used dict + trend + prior_value + threshold + threshold_status + framework_refs`.
- Engine never sends notifications/emails (caller drives escalation), never persists state, never auto-acts on alerts, never mutates inputs.
- `_test_recommended_action_is_category_not_action` explicitly verifies the action-category-not-action discipline.

### Scenarios

- **CFO-01 healthy state** — 5 KPI families populated (no growth without prior); 0 breaches, 0 alerts.
- **CFO-02 capital breach CRITICAL** — CAR 10% < 14.5% → BREACH + CRITICAL alert; action category mentions capital plan / RWA.
- **CFO-03 NPL breach WARNING** — NPL 8.3% > 6% → BREACH + WARNING (not CRITICAL — credit issue, not regulatory-grade); inputs_used surfaces npl + loans for drill-down.
- **CFO-04 with prior** — 3 growth KPIs produced; NIM trend UP (improved); prior_value populated; loan growth 9.09% computed correctly.

16/16 CFO assertions PASS.

### Honest scope notes

1. **CAR and LIQ consumed as ratios — no recomputation.** Engine takes the ratios as supplied (typically from ENH-252). It doesn't validate the underlying capital/liquidity components — that's ENH-252's job. Production callers will pipeline ENH-252 → ENH-254.
2. **No drill-down to entity/segment/product.** Aggregates at the bank-wide level only. The original standard description mentioned drill-down dimensions; that requires multi-dimensional input shape (entity/segment cubes), which is out of scope for the data layer. The closure cockpit at v10.68 will surface drill-down via separate per-entity invocations of the engine.
3. **Customer count is a bare integer.** No active/inactive/churn segmentation. Production CRM data would have richer customer attributes; engine takes the simple count.
4. **Growth KPIs require prior period.** If only current is supplied, growth family is empty — engine doesn't fabricate baseline.
5. **No forward-looking projections.** Pure trailing-period view. Forward-looking metrics (e.g., "projected ROE next quarter") would compose with ENH-253 but that's a caller-side composition, not engine logic here.
6. **Threshold values are hardcoded defaults.** Operators wanting tighter NIM (e.g., 5% min for premium-tier banks) need to subclass or override at construction. A future enhancement could accept a `ThresholdProfile` config object.

---

## Combined gate verification

- `python3 scripts/audit.py` → **Score: 134/134 gates = 100.0% — PASS**
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings match baseline exactly** (329 modules · 832 imports · HARD=3 unchanged · +2 modules / +2 imports across the two batches)
- All 16 engine self-tests green: **257/257**

## Lean+Compact protocol — applied (v10.46 amended)

Per batch (v10.63, v10.64):
- 1 ENH per batch ✅
- Engine Hub Tier addition DEFERRED to arc closure (v10.68) ✅
- Master Prompt update DEFERRED to arc closure ✅
- UI integration DEFERRED to arc closure (v10.64 explicitly split-implementation per protocol amendment) ✅
- Audit + G128 + scenario library extension SHIPPED ✅
- Per Rule 1 every dataclass surfaces full provenance ✅
- Per Rule 6 ml_disabled flag explicit when ML hook unavailable (PFA-04) ✅
- Per Rule 7 engine diagnostic only — verified by mutation tests ✅

## Files changed across the two batches

- **NEW** `utils/predictive_financial_analytics.py` (~830 lines, 20 tests)
- **NEW** `utils/finance_intelligence_dashboard.py` (~770 lines, 15 tests)
- **MOD** `utils/standards_registry.py` (2 standards activated with full descriptions)
- **MOD** `utils/scenario_simulator.py` (+8 scenarios + library extensions + `_make_financials` helper with realistic ROE-passing fixtures)
- **NEW** `CHANGELOG_v10.63_to_v10.64.md` (this file)

## finance arc state

| Standard | Module | Status | Batch |
| --- | --- | --- | --- |
| ENH-249 | finance_close_orchestrator | active | v10.59 |
| ENH-250 | intercompany_matching | active | v10.60 |
| ENH-251 | consolidated_tb_engine | active | v10.61 |
| ENH-252 | cbk_regulatory_reporting | active | v10.62 |
| **ENH-253** | **predictive_financial_analytics** | **active** | **v10.63** |
| **ENH-254** | **finance_intelligence_dashboard** | **active** (data; UI at v10.68) | **v10.64** |
| ENH-255 | financial_statement_generator | planned | v10.65 |
| ENH-256 | tax_compliance_reporting | planned | v10.66 |
| ENH-257 | multi_entity_multi_currency | planned | v10.67 |
| ENH-258 | finance_audit_compliance | planned | v10.67+ |
| closure | G135 + G136 + Tier 27 + cockpit | planned | v10.68 |

## Next session

Per Joshua's direction (2 batches per drop), next session will ship **v10.65 ENH-255 Financial Statement Generator** + **v10.66 ENH-256 Tax Compliance & Reporting**. ENH-255 will consume `ConsolidatedTrialBalance` from ENH-251 and produce IFRS-format statements (BS, P&L, OCI, equity, cash flows). ENH-256 will cover Kenyan tax compliance (corporation tax, VAT, withholding tax, excise duty) — diagnostic only, never files returns.

**146 consecutive clean batches.** 12 closed arcs hold; finance arc at 6/10.

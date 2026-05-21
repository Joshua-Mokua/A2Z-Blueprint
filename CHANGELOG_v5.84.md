# A2Z MIS 360 — CHANGELOG v5.84

**v5.84 Fourteenth Integration Batch — Predictive Performance (#20 + #21)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 10th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🔮 FORWARD-LOOKING ANALYTICS.** First predictive integration complementing v5.79 retrospective HR Performance. Cumulative: **32 of 116 standards integrated.** Fourteenth integration batch.

---

## Strategic milestone — temporal HR analytics complete

| Time | What | Standard | Integrated in |
|---|---|---|---|
| **Past period** | Compensation equity, engagement scores, performance ratings | #63, #64 | v5.79 |
| **Right now** | Strengths, promotion readiness, overall BSC score | **#20** | **v5.84** ⭐ |
| **End of period** | KPI achievement projection (linear extrapolation + probability) | **#21** | **v5.84** ⭐ |

HR teams and managers now have a complete temporal picture: past-period grades and engagement (retrospective), strengths and promotion readiness right now (insights), and end-of-period KPI projections (predictive). The page integrations together cover the major HR analytics surface a tier-2 bank typically purchases as a standalone HR Information System.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.84 wires **2 standards** in one batch using **2 engines** (1 class + 1 function):
- **Standard #20 Performance Insights** → `performance_insights.py` (`get_performance_insights` function)
- **Standard #21 Predictive Performance** → `predictive_performance.py` (`PredictivePerformance` class)

---

## What was modified

### `pages/2_people.py` — Predictive Performance sub-tab added
**1899 → 2286 lines (+387)**

Section 0 "📊 Insights" sub-tabs expanded from 4 to 5 (well within G4 limit since they are sub-tabs, not top-level):

| # | Sub-tab | Status |
|---|---|---|
| 0 | 📊 HR overview | unchanged |
| 1 | 📈 Team insights | unchanged |
| 2 | ⚖️ Compensation Equity (Standard #63) | added v5.79 |
| 3 | 🎯 Engagement & Performance (Standard #64) | added v5.79 |
| **4** | **🔮 Predictive Performance (Standards #20 + #21)** | **NEW v5.84** |

The People page is now **the longest single page in the app at 2286 lines** (next is 1266-line `14_branch_log.py`).

### Predictive Performance sub-tab — 3 inner tabs

**🔮 KPI Achievement Forecast (#21)** — uses `PredictivePerformance` engine with dependency injection:
- Page provides closures for `active_kpis_fn`, `target_lookup_fn`, `actual_lookup_fn`, `period_fn`, `period_bounds_fn`, `days_elapsed_fn`
- Engine returns linear extrapolation prediction with probability factoring `days_remaining`
- Period progress banner shows day X of Y with N days remaining
- Overall verdict bands: ON TRACK (≥85%) / AT RISK (≥50%) / OFF TRACK (<50%)
- Per-KPI table with current / target / predicted / pace_per_day / probability with traffic-light emojis 🟢/🟡/🔴
- User-editable demo dataset of 1-8 KPIs
- Configurable period start/end dates

**✨ Performance Insights (#20)** — uses `get_performance_insights` module function:
- Engine validates staff_code against `users.json` and returns `{}` for unknown staff (defensive null-object pattern)
- Computes overall BSC score (0-5)
- Strengths: KPIs ≥`STRENGTH_THRESHOLD_PCT=110%` sorted desc, top `DEFAULT_MAX_STRENGTHS=5`
- Promotion readiness clamped [0, 1]
- `signals_present` meta dict shows which inputs were available — Rule 6 transparency
- User can edit 6-row KPI achievement table, slider for promo readiness 0-1 and overall score 0-5
- Surfaces "Unknown staff_code" error clearly when staff not in users.json

**🌳 Engine Reference** — engine constants for both #20 and #21:
- #21: `DEFAULT_BASE_SPREAD=0.2`, `ACCURACY_TOLERANCE_PCT=0.15`, `SPEC_ACCURACY_TARGET=0.85`, model=linear_extrapolation
- #20: `STRENGTH_THRESHOLD_PCT=110%`, `DEFAULT_MAX_STRENGTHS=5`, promotion readiness clamp [0, 1], overall score 0-5
- Closing caption explains forward-looking vs retrospective analytics distinction

### Engine files — UNCHANGED
`utils/predictive_performance.py` and `utils/performance_insights.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 2 engine paths verified end-to-end

**#21 KPI Achievement Forecast** — 3 KPIs at day 45 of 64-day period:

| KPI | Current | Target | Predicted | Probability | Reading |
|---|---|---|---|---|---|
| K001 | 60 | 100 | 85.33 | **20.7%** | Will fall short — accurate signal |
| K002 | 65 | 70 | 92.44 | **95.0%** | Close to target, on track |
| K003 | 38 | 40 | 54.04 | **96.2%** | Slow pace but already near target |

Overall prediction = **0.706** (composite of three KPI probabilities)

**Rule 6 transparency confirmed**: when K003 actual missing → `kpis_skipped=1`, `kpis_predicted=2`

**#20 Performance Insights** with real staff_code 300001:

| Metric | Value |
|---|---|
| Staff name | William Mwanake (looked up from users.json) |
| Overall BSC score | 3.6 / 5 |
| Strengths (≥110%) | [K001, K006, K002] (correctly sorted desc by 125% / 120% / 111.4%) |
| Promotion readiness | 0.75 |

**Edge cases verified**:
- **Promotion readiness clamping**: 1.5 input → **1.0** output (correctly clamped to [0,1])
- **Unknown staff**: code 999999 → `{}` (defensive empty dict)

---

## Critical engine API specifics documented

These were verified during build (13 findings — both engines have non-trivial conventions):

### `PredictivePerformance` (#21):

1. **Constructor takes 6 dependency-injection callbacks** plus optional `base_spread`. ALL callbacks have sensible defaults reading from `data/` directory if not provided.

2. **🆕 `active_kpis_fn` MUST return list of dicts with key `id` (not `kpi_id`)** — KPIs without an `id` key are silently skipped. **Non-obvious gotcha** discovered during integration.

3. `target_lookup_fn` and `actual_lookup_fn` return `Optional[Decimal]`. None values cause the KPI to be skipped (Rule 6 with `kpis_skipped` count surfaced).

4. `period_bounds_fn` returns `Tuple[date, date]` for (period_start, period_end).

5. `days_elapsed_fn(period, today)` returns int. Engine uses `pace_per_day = current / days_elapsed × total_days`. For `today` past period_end, `days_remaining = max(0, ...)` so probability calculations collapse to near zero — engine known limitation.

6. Returns `predictions` dict keyed by kpi_id with `KPIPrediction` asdict including `current_value` / `target` / `predicted_value` / `probability` / `days_elapsed` / `days_remaining` / `total_days` / `pace_per_day` / `model`.

7. `overall_prediction` is composite of individual KPI probabilities — exact formula not documented in source but observed to be roughly geometric/weighted mean.

### `get_performance_insights` (#20):

8. **Module-level function NOT a class method** — takes 5 dependency-injection callbacks all optional with defaults reading from `data/`.

9. **🆕 Validates `staff_code` against `_staff_lookup` (users.json) and returns `{}` for unknown staff** — defensive null-object pattern. Page must check for empty dict.

10. **🆕 KPI dicts in `kpi_status_fn` MUST have key `kpi_id` (NOT `id`) and `achievement_pct`** — DIFFERENT convention from `predictive_performance.py` which uses `id`. Engine-author preference inconsistency.

11. **Strengths returned as list of `kpi_id` STRINGS** not full dicts — page must look up display name from original input data.

12. **`promotion_readiness` clamped to [0, 1]** — values outside this range are coerced. Non-numeric values default to 0.0 (defensive).

13. **`meta.signals_present` dict has 3 keys** (kpi_status, growth_plan, overall_score) — all True if all 3 callbacks returned non-empty results. Allows caller to detect partial-data scenarios.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "Predictive #21: staff=300001 predicted=3 skipped=0 overall=0.706")
audit_log("IFRS_ENGINE_USED", uname, "Insights #20: staff=300001 score=3.6 strengths=3 promo=0.75")
```

---

## ✅ Tenth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.83). G3 + G4 lessons embedded in process.

---

## Honesty discipline visualised

- **Period progress banner** shows day X of Y with days remaining — no hidden time math
- **Probability traffic-light emojis** at 85% / 50% boundaries
- **ON_TRACK / AT_RISK / OFF_TRACK overall verdict** based on aggregate probability
- **kpis_skipped count surfaced** for missing target/actual data (Rule 6)
- **Promotion readiness clamping** explained in caption (1.5 → 1.0)
- **"Unknown staff_code" error** with explicit guidance to use real staff_code from users.json
- **signals_present meta dict** shows which inputs were available
- **Strengths threshold + max** explicit in caption
- **Forward-looking vs retrospective distinction** explained in Engine Reference closing caption
- Every engine call audit-logged

---

## What didn't change

- Both engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G20 + G21 still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.83 pages — unchanged
- The 4 existing sub-tabs in Section 0 (HR overview / Team insights / Compensation Equity / Engagement & Performance) — completely untouched
- Sections 1, 2, 3 (Records / Leave / Discipline & Dev) — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.83

| | v5.83 | v5.84 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **30** | **32** ⭐ (+2) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 11 | **11** (re-enhances 2_people.py from v5.79) |
| Lines added across pages this batch | +384 (channels) | +387 (people) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 2-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering — especially the editable KPI tables and the period progress banner with HTML formatting.

2. **32 of 116 integrated** — 84 standards remain library-only.

3. **The People page is now 2286 lines — the longest single page in the app** by a significant margin (next is 1266-line `14_branch_log.py`). The 5 sub-tabs in Section 0 are clearly delineated under `with sub[N]:` blocks; existing v5.79 code untouched. Risk of regression on existing tabs is minimal but non-zero given the page size.

4. **Predictive engine uses linear extrapolation only** — no seasonality, no trend analysis, no ML. The engine's `SPEC_ACCURACY_TARGET=85%` is aspirational; actual accuracy depends heavily on KPI shape. **KPIs with non-linear pace** (e.g. campaign-driven sales with end-of-quarter spike) **will be poorly predicted by linear extrapolation**. Documented engine limitation; future v7+ ML-based predictor would be a separate spec deviation if needed.

5. **Predictive accuracy near or past period_end is artifact-low** — when `days_remaining=0`, probability calculations collapse to near zero even for KPIs already at or above target, because the engine extrapolates pace past period_end (which is meaningless). Page surfaces the period progress banner so users can see this; **production guidance should be "don't run prediction past period_end — at that point use actuals not predictions"**.

6. **Performance Insights returns `{}` for unknown staff** — engine validates against users.json. For non-staff users (consultants, contractors not in users.json), the engine returns empty dict and page shows error. **This is correct** — performance insights only make sense for staff with KPI history.

7. **Strengths returned as KPI IDs not display names** — page does its own lookup from the input data table. If KPI ID format changes (e.g. K001 → KPI_001), the lookup will fail silently and strength rows will show "—" for name. Defensive but a known coupling point.

8. **Promotion readiness comes from growth plan dict — not directly from any engine** — the engine simply reads `plan.get("promotion_readiness", 0)` and clamps. The actual readiness assessment is the responsibility of the manager filling out the growth plan. Engine doesn't compute it from KPI data, performance ratings, or tenure. Documented as design choice, not bug.

9. **🆕 The two engines use INCONSISTENT dict key names** — `predictive_performance.py` expects KPI dicts with key `id`, while `performance_insights.py` expects `kpi_id`. Engine-author preference inconsistency; page handles by passing different dict shapes to each. Could be reconciled in a future engine harmonization batch.

10. **No persistence — predictions are computed live and audit-logged but not stored**. Engine has a `PREDICTIONS_FILE` constant (`data/predictions.json`) but the page integration doesn't write to it. **Production deployment that wants to track prediction accuracy over time** (e.g. compare predicted vs actual at period_end to compute SPEC_ACCURACY_TARGET) **would need to wire persistence**. Documented deferred enhancement.

---

## Strategic narrative — forward-looking analytics complement retrospective

**v5.79 integrated retrospective HR Performance** (#63 + #64) — answering "what happened?".

**v5.84 adds the forward-looking complement** (#20 + #21) — answering "what will happen?" and "what are this person's strengths right now?".

The temporal picture is now complete:

- **Retrospective** (v5.79): pay equity audits, engagement scores from past surveys, performance ratings from completed cycles
- **Real-time** (v5.84 #20): strengths visible right now, promotion readiness right now, BSC score right now
- **Forward-looking** (v5.84 #21): KPI achievement projections for end of current period

The page integrations together cover the major HR analytics surface a tier-2 bank typically purchases as a standalone HR Information System.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Project / Audit / Compliance pages | various smaller engines (RCSA #44, KYC/AML #36) | Shift to governance/control axis |
| (2) | Channel Income | channel_income | Third Channels enhancement (cost-to-serve) |
| (3) | Smart Alerts | smart_alerts | Enhance pages/36_smart_alerts.py |
| (4) | Customer Insights | customer_insights | If not already covered |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With both Branch and Channels axes complete, regulatory framework arc complete, and HR temporal picture complete, recommend **(1) Project / Audit / Compliance pages** for v5.85 — would shift to a different functional axis (governance/control) after the strong run of operational and analytical batches.

---

**Cumulative tally:** 116 standards delivered, **32 integrated into UI via 3 dedicated pages + 11 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🔮 **Forward-looking HR analytics integrated** (Performance Insights #20 + Predictive Performance #21).

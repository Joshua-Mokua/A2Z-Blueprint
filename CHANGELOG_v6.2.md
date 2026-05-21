# A2Z MIS 360 — CHANGELOG v6.2

**v6.2 Thirty-Second Integration Batch — Stress Testing DEPTH (#51)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 7th consecutive)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🛡️ DAILY-RISK TRIFECTA DEPTH COMPLETE.** 6th depth-batch application across 6 distinct domains. Cumulative: **52 of 116 standards integrated.**

---

## Strategic milestone — daily-risk trifecta depth complete

The platform has 3 daily risk-management standards that govern bank prudential health:

| Standard | Vintage | Initial Integration | Depth Coverage |
|---|---|---|---|
| **IRRBB** (#107) | v5.72 | 4 sub-tabs: rate shock + EVE + EaR + duration gap | ✅ Already comprehensive at integration |
| **LCR/NSFR** (#113+#114) | v5.76 | 4 sub-tabs: each ratio + counterbalancing + run-off | ✅ Already comprehensive at integration |
| **Stress Testing** (#51) | v5.78 | 4 sub-tabs: inputs + 3-scenario + projection + reverse | **v6.2 ⭐ NEW DEPTH ADDED** |

**v6.2 closes the trifecta.** All 3 daily-risk standards now have mature depth surfaces beyond initial integration.

Combined with previous depth coverage (HR-comp + HR-engagement + governance + compliance + customer), the bank now has **6 functional domains with mature depth coverage**.

---

## What this batch is — and what it isn't

**Pure depth integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v6.2 wires **Standard #51 Stress Testing DEPTH** (`stress_testing.py`). All 4 engine paths were already wired in v5.78's 4 st_sub_tabs. v6.2 adds:

1. **Composed analytics** combining 3 engine paths into Executive Scorecard
2. **Multi-scenario comparison views** (sensitivity matrix + multi-period trajectory)
3. **Buffer adequacy mapping** with 5-band classification

---

## What was modified

### `pages/35_stress_testing.py` — 5th sub-tab + 4 inner tabs (G4-strict)
**568 → 999 lines (+431)**

`st_sub_tabs` expanded 4 → 5 (G4-strict ≤7). New 5th sub-tab **"📦 Stress Testing Depth (#51, v6.2)"** contains 4 inner tabs:

| # | Inner tab | Engine paths used |
|---|---|---|
| 0 | 📋 Stress Executive Scorecard | run_supervisory_scenarios + reverse_stress_test |
| 1 | 🎯 Sensitivity Analysis Batch | run_supervisory_scenarios (per-scenario shocks) |
| 2 | 📈 Multi-Period Trajectory | capital_projection × 3 scenarios |
| 3 | 🎚️ Capital Buffer Adequacy Map | run_supervisory_scenarios |

### 📋 Stress Executive Scorecard — 4 sections

**1️⃣ Starting capital position**: starting CAR + CBK minimum + buffer above min

**2️⃣ 3-scenario stress impact**: table with starting CAR / stressed CAR / drop pp / breach flag per scenario

**3️⃣ Reverse stress test fragility**: NPL increase to breach + rate shock to breach + stressed CAR at breach point

**4️⃣ Overall verdict GREEN/AMBER/RED** based on issues from {worst breach, ADVERSE breach, buffer thin <5pp, fragile NPL <30pp to breach}

### 🎯 Sensitivity Analysis Batch

Sweeps the 7 shock dimensions across 3 scenarios:
- gdp_growth_delta_pp
- interest_rate_shock_bps
- npl_increase_pct
- asset_price_shock_pct
- fx_devaluation_pct
- deposit_outflow_pct
- rwa_inflation_pct

Output: per-scenario shock matrix + resulting CAR comparison + bar chart of CAR drop magnitudes + dominant risk driver insight via NPL transmission factor heuristic.

### 📈 Multi-Period Trajectory

Runs `capital_projection` for ALL 3 scenarios. Output:
- Year-over-year CAR matrix (Years × Scenarios)
- Line chart trajectory comparison
- Per-scenario first-breach-year analysis

### 🎚️ Capital Buffer Adequacy Map

5-band adequacy classification:
- ✅ STRONG ≥10pp above CBK min
- 🟢 ADEQUATE ≥5pp
- 🟡 THIN ≥2pp
- 🟠 MARGINAL ≥0pp
- 🔴 INADEQUATE <0pp (breach)

Plus erosion analysis + remediation guidance for marginal/inadequate scenarios (capital raise, RWA reduction, profit retention).

### Engine file — UNCHANGED
`utils/stress_testing.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED

---

## 4 engine paths verified across 4 scenarios

**Test bank baseline**: Tier-2 Kenya bank — KES 25B capital / 100B RWA / 25% starting CAR / +10.5pp buffer over CBK 14.5%.

**Scenario 1 — Executive Scorecard**:
- Starting CAR: 25.00% (buffer +10.50pp)
- BASELINE stressed: 28.00% (no breach)
- ADVERSE stressed: **13.45% (BREACH)** — just below 14.5%
- SEVERELY_ADVERSE stressed: **1.28% (CATASTROPHIC BREACH)**
- Reverse: bank breaches at NPL+35pp / rate+0bps
- Verdict: **RED** (multiple issues — both ADVERSE and SEVERELY_ADVERSE breach)

**Scenario 2 — Sensitivity Matrix** (7 shock dims × 3 scenarios):
- ADVERSE applies +30% NPL increase → triggers dominant-driver heuristic insight
- Engine transmission factor NPL_INCREASE_TO_LOSS_FACTOR=0.45 means each pp NPL → 0.45pp loan-book loss
- v6.2 surfaces this with mitigation focus recommendations (collections + early-warning + provisioning)

**Scenario 3 — Multi-Period Trajectory** (3 scenarios × 3 years):
- BASELINE: Y1=28% / Y2=31% / Y3=34% — capital strengthens through profit retention
- ADVERSE: Y1=13.45% (BREACH) / Y2=3.79% / **Y3=-4.23% (insolvent)**
- SEVERELY_ADVERSE: Y1=1.28% (BREACH) / Y2=-13.95% / **Y3=-23.14% (deeply insolvent)**
- Triggers Year-1 breaches warning for 2 scenarios

**Scenario 4 — Buffer Adequacy Map**:
- BASELINE: starting +10.50pp / stressed +13.50pp → **STRONG**
- ADVERSE: starting +10.50pp / stressed -1.05pp → **INADEQUATE (breach)**
- SEVERELY_ADVERSE: starting +10.50pp / stressed -13.22pp → **INADEQUATE (severe breach)**

Triggers ICAAP capital plan remediation language for 2 inadequate scenarios.

---

## Critical engine API specifics documented

12 findings verified during build:

1. **`StressTestingEngine` has 4 STATIC class methods** — apply_scenario, capital_projection, reverse_stress_test, run_supervisory_scenarios.

2. **`StressTestInputs` has 8 fields**: capital + RWA + loan_book + NPL + securities + FX + profit (Optional[Decimal]) + horizon_years (int, required).

3. **🆕 SCENARIO_SHOCKS dict has 3 scenarios × 7 shock dimensions each**:
   - BASELINE: all zeros
   - ADVERSE: gdp -3pp / rate +200bps / npl +30% / asset -15% / fx +8% / deposit -5% / rwa +10%
   - SEVERELY_ADVERSE: gdp -6pp / rate +400bps / npl +60% / asset -30% / fx +15% / deposit -15% / rwa +25%
   
   Calibrated to typical CBK + IMF supervisory test calibrations.

4. **🆕 `run_supervisory_scenarios` returns 5 keys**: scenarios (dict per 3 scenarios) + worst_scenario + worst_stressed_car_pct + any_scenario_breaches_cbk_min + verdict (PASS/FAIL). The verdict is engine-built, not caller-side.

5. **🆕 Each scenario result has 9 keys**: scenario name + shock_parameters dict (7 sub-keys) + starting_capital + starting_rwa + starting_car + stressed_capital + stressed_rwa + stressed_car + car_drop_pp + breaches_cbk_minimum.

6. **🆕 `capital_projection` returns 3 keys**: scenario + horizon_years + yearly_projection (list of dicts). **Engine compounds losses each year** — Y2 builds on Y1 stressed state, not original.

7. **🆕 `reverse_stress_test` returns 5 keys**: breach_npl_pct + breach_rate_bps + stressed_car_pct + breach_threshold_pct + starting_car_pct. Algorithm walks NPL + rate up in 5pp / 50bps increments until CAR drops below threshold.

8. **🆕 Engine constants byte-for-byte**:
   - CBK_TOTAL_CAR_MIN_PCT_LOCAL=14.5 (CBK PG/03)
   - NPL_INCREASE_TO_LOSS_FACTOR=0.45
   - ASSET_PRICE_SHOCK_TO_PROVISIONS=0.5
   - RATE_SHOCK_TO_NII_BPS=0.5

9. **🆕 Engine compounds projection year-over-year** so Y3 may show negative capital (bank insolvent). Engine reports honest math; production may want display clipping.

10. **🆕 `_build_inputs()` helper accessible across sub-tabs** — Python's `with` doesn't create new scope, so v5.78's helper inside `st_sub_tabs[1]` is accessible in v6.2's `st_sub_tabs[4]` depth tabs via enclosing-scope lookup.

11. **🆕 No engine path for single-dimension shock sweep** — engine accepts pre-built scenarios via SCENARIO_SHOCKS dict. v6.2 sensitivity batch uses 3 supervisory scenarios as proxies. Engine extension `apply_scenario_with_custom_shocks(inputs, shock_dict)` would enable true single-shock sweeps.

12. **🆕 Reverse stress test only sweeps NPL + rate** — not all 7 shocks. Production may want full 7-dimensional reverse stress.

---

## Audit logging

Every depth invocation produces `IFRS_ENGINE_USED` events:

```
audit_log("IFRS_ENGINE_USED", uname, "Stress #51 (depth): scorecard start_car=25.00% adverse_breach=True reverse_npl=35 issues=4")
audit_log("IFRS_ENGINE_USED", uname, "Stress #51 (depth): sensitivity shock_dims=7 scenarios=3")
audit_log("IFRS_ENGINE_USED", uname, "Stress #51 (depth): trajectory horizon=3y early_breach=2 no_breach=1")
audit_log("IFRS_ENGINE_USED", uname, "Stress #51 (depth): buffer map inadequate=2 marginal=0 thin=0")
```

---

## ✅ Seventh consecutive clean-first-try

Audit clean on first attempt — **7th consecutive after v5.96 + v5.97 + v5.98 + v5.99 + v6.0 + v6.1**. G4-strict + depth-batch templates routine.

---

## Honesty discipline visualised

- **CBK PG/03 referenced** — regulatory framework anchored
- **Engine constants surfaced byte-for-byte** — NPL_INCREASE_TO_LOSS_FACTOR transparent in dominant-driver insight
- **Negative capital reported honestly** — Y3 -4.23% surfaces real insolvency math
- **5-band adequacy classification** — explicit thresholds (10/5/2/0)
- **First-breach-year analysis** — transparent breach timing per scenario
- **Buffer erosion math** — starting buffer vs stressed buffer made explicit
- **Remediation options listed** — capital raise / RWA reduction / dividend deferral
- **ICAAP language** — board-pack-ready terminology
- **Verdict logic transparent** — issues counted, listed, surfaced
- Every depth call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G51 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v6.1 pages — unchanged (except 35_stress_testing which gains depth)
- Top-level tabs in `35_stress_testing.py` — completely untouched (5 tabs unchanged)
- Sub-tabs 0-3 in `st_sub_tabs` — completely untouched
- TAB 1-3 (Scenario Runner / Side-by-Side / Custom Scenario / ICAAP Report) — untouched
- The `_build_inputs()` helper — UNCHANGED (just reused in depth tabs)
- `app.py` — unchanged

---

## Comparison vs v6.1

| | v6.1 | v6.2 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **51** | **52** ⭐ (+1 — Stress Testing depth) |
| Audit gates | 103/103 (clean first try) | 103/103 (**clean first try**) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| Modified existing pages cumulative | 15 | 15 (re-enhances 35_stress_testing) |
| Lines added across pages this batch | +1021 (v6.1 dual-page) | +431 (v6.2 single-page) |
| 35_stress_testing.py total lines | 568 | **999** |
| Clean-first-try streak | 6 | **7** |
| **Depth batches cumulative** | 5 | **6** ⭐ |
| **Domains with depth coverage** | 5 | **6** (+ daily-risk trifecta complete) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude** — page passes `python -m py_compile`, module-level engine import test, and 4-scenario engine call simulation. User must run `streamlit run app.py` locally to confirm browser rendering.

2. **52 of 116 integrated** — 64 standards remain library-only.

3. **All inner tabs use engine output from current Inputs tab** — no synthetic data in depth tabs themselves; user changes input + clicks compute + sees depth view of THAT bank's situation. **Improvement over previous depth batches** which used hardcoded portfolios.

4. **🆕 Sensitivity Analysis is NOT a true single-shock sweep** — engine doesn't expose single-dimension shock sweeping. v6.2 sensitivity batch uses the 3 pre-built scenarios as proxies. Production deployment with custom-shock support could decompose ADVERSE = 30% NPL alone vs 200bps rate alone vs combined.

5. **🆕 Multi-period trajectory uses engine's compounding** — Y2 builds on Y1 stressed state, so Y3 projections may show negative capital ("bank insolvent"). v6.2 displays raw values per Rule 6 honesty; production may want clipping or insolvency markers.

6. **🆕 Buffer adequacy bands (10/5/2/0) HARD-CODED** — production may want bank-specific bands aligned to risk appetite statement.

7. **🆕 Sensitivity dominant-driver heuristic uses NPL transmission factor as proxy** — actual dominance depends on bank balance sheet composition (loan-heavy → NPL dominates; trading-heavy → asset price dominates). Production with bank-specific composition could compute true dominance.

8. **🆕 Reverse stress only sweeps NPL + rate** — engine limitation. Production may want full 7-dimensional reverse stress.

9. **🆕 No multi-shock interactions** — engine treats shocks independently within each scenario; real-world stress events have non-linear interactions (rate shock causes NPL increase, FX devaluation causes asset price drop). Production with non-linear modeling could surface this.

10. **🆕 No peer comparison** — bank's resilience can't be compared to industry quartiles without peer data. Production deployment with regulatory peer benchmarks (CBK industry stress test results) could surface relative resilience.

11. **🆕 No capital plan integration** — depth tabs identify capital needs but don't feed into capital-plan workflow. Production deployment with capital_plan.json could surface remediation actions with target dates.

12. **🆕 No connection to credit-risk depth** — stress testing's NPL shock should connect to credit risk's ECL projections (#20/#21). v6.2 surfaces stress shocks but doesn't feed into ECL recalculation. Future v6.x batch could create stress-credit-risk linkage (engine extension required).

---

## Strategic narrative — daily-risk trifecta depth complete + 6 domains with depth

After v6.2, the platform has:

| Functional domain | Depth-batch vintage |
|---|---|
| Customer-centric (CLV) | v5.95 |
| HR Compensation | v5.97 |
| HR Engagement | v5.98 |
| Controls/Governance | v5.99 |
| Compliance/AML | v6.1 |
| **Risk Management (Stress Testing)** | **v6.2** ⭐ |

**6 of approximately 10 functional domains have mature depth coverage.** Remaining domains for future depth batches:
- Credit risk (#20+#21+#23) — likely triple-page depth
- Treasury operations (#37+#38) — dual-page
- Branch operations
- Channels income/cost/reliability suite

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | **Credit Risk depth (#20+#21+#23)** | credit_risk + ifrs9_staging + behavioral_pd | TRIPLE-page depth batch — would prove dual-page pattern scales to 3 pages |
| (2) | AML-health composite addition | composite_scores | Extend with `aml_health_composite()` |
| (3) | Customer-value composite UI surfacing | composite_scores | Extends v5.96 |
| (4) | RCSA-health composite UI surfacing | composite_scores | Extends v5.99 |
| (5) | Treasury depth | various | Dual-page across IRRBB + LCR/NSFR |
| (6) | More depth batches | various | Branch + Channels + NPS + Smart Alerts |
| (7) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With Stress Testing depth integrated and daily-risk trifecta depth complete, recommend **(1) Credit Risk depth** for v6.3 — the credit risk axis is the largest remaining unsurfaced engine surface in the platform. Would also be the **first triple-page depth batch**, proving the multi-page pattern scales further.

---

**Cumulative tally:** 116 standards delivered, **52 integrated into UI via 3 dedicated pages + 15 enhanced existing pages + 1 utility module**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications, **6 depth batches across 6 distinct domains**, 7 consecutive clean-first-try.

🛡️ **Daily-risk trifecta depth complete.** IRRBB + LCR/NSFR + Stress Testing all have mature depth surfaces.

✅ **Clean-first-try streak: 7** (G4-strict + depth-batch templates routine).

📦 **Sixth depth batch** confirms template scales across all daily-risk standards.

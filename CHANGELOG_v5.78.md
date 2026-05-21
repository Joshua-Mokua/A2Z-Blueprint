# A2Z MIS 360 — CHANGELOG v5.78

**v5.78 Eighth Integration Batch — Stress Testing (Standard #79)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 4th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **Daily risk-management trifecta complete.** IRRBB (v5.72) + LCR/NSFR (v5.76) + **Stress Tests (v5.78)** all now have engine-driven UI. Cumulative: **23 of 116 standards integrated.**

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.78 closes a strategic loop. The CBK supervises three near-daily risk metrics:

| Risk dimension | Reporting cadence | Integrated in |
|---|---|---|
| Capital Adequacy / IRRBB / Investment Portfolio | Quarterly (CBK PG/02) | v5.72 |
| Liquidity (LCR daily, NSFR quarterly, FX EOD) | Daily-to-quarterly | v5.76 |
| **Stress Tests / Reverse Stress / Capital Projection** | **Semi-annual + on-demand (CBK ICAAP)** | **v5.78** ⭐ |

A risk team running daily/weekly checks now has **all three risk dimensions** hands-on rather than as library functions. The reverse stress test in particular is CBK ICAAP's most demanding requirement — *"what would it take to break us?"* — and was not previously surfaced anywhere in the UI.

---

## What was modified

### `pages/35_stress_testing.py` — CBK Supervisory Stress tab added
**229 → 567 lines (+338)**

Top-level tab list expanded from 4 to 5 (within G4's 7-tab limit):

| # | Tab | Status |
|---|---|---|
| 0 | 📊 Scenario Runner | unchanged |
| 1 | 📈 Side-by-Side | unchanged |
| 2 | 🎛️ Custom Scenario | unchanged |
| 3 | 📄 ICAAP Report | unchanged |
| **4** | **🏛️ CBK Supervisory (Standard #79)** | **NEW** |

### CBK Supervisory tab — 4 sub-tabs

**📋 Inputs** — 8 bank starting-position parameters (total capital / RWA / loan book / NPL stock / securities / FX position / annual pre-tax profit / horizon years). Defaults reflect a representative Tier-2 Kenyan bank: 25B capital · 150B RWA · 11.1% NPL on 120B loans · 5B annual profit. Pre-stress CAR computed live with **WELL_CAPITALISED / AT_MINIMUM / ALREADY_BREACHING** traffic-light status. Engine constants reference table shows:

- `CBK_TOTAL_CAR_MIN_PCT_LOCAL` = **14.5%** (Basel III + 4pp local prudential floor)
- `NPL_INCREASE_TO_LOSS_FACTOR` = **0.45** (each 1% NPL increase = 0.45% loss against capital)
- `RATE_SHOCK_TO_NII_BPS` = **0.5** (each 100bps shock = 0.5% NII delta vs loan book)
- `ASSET_PRICE_SHOCK_TO_PROVISIONS` = **0.5** (each 1% asset price drop = 0.5% provisioning)

Plus full SCENARIO_SHOCKS table for BASELINE / ADVERSE / SEVERELY_ADVERSE showing 7 shock parameters per scenario.

**🎯 3-Scenario Run** — deterministic point-in-time run of all 3 supervisory scenarios. Overall PASS/FAIL verdict banner. Worst-scenario identified with worst stressed CAR. Per-scenario table with starting CAR / stressed CAR / CAR drop in pp / stressed capital / stressed RWA / breach indicator.

**📈 Capital Projection** — multi-year compounded projection. Choose any of the 3 scenarios. Project capital path year-by-year with table + line chart of CAR trajectory vs CBK floor. Identifies first breach year if any with explicit breach KES capital + CAR percentage.

**🔄 Reverse Stress Test** — CBK ICAAP requirement. Searches for minimum NPL increase × rate shock combination that breaches the threshold (default = CBK floor 14.5%, user-configurable). Produces **FRAGILE / MODERATE / RESILIENT** resilience assessment based on +NPL pp at breach. **Plain-English interpretation** of what numbers mean — *"if your NPL ratio rises by +X pp AND interest rates move by +Y bps, your CAR drops to Z%, breaching CBK's floor"*.

### Engine file — UNCHANGED
`utils/stress_testing.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 4 engine paths verified end-to-end

**Realistic Ecobank-sized inputs**: 25B capital / 150B RWA / 11.1% NPL on 120B loans / 50B securities / 2.5B FX / 5B annual profit / 3yr horizon.

| Engine call | Input | Output |
|---|---|---|
| `apply_scenario(BASELINE)` | as above | Starting CAR 16.67% → stressed **20.00%** (no shocks + profit accretion), no breach |
| `apply_scenario(ADVERSE)` | as above | → stressed **5.97% CAR**, **BREACH** ⛔ |
| `apply_scenario(SEVERELY_ADVERSE)` | as above | → stressed **-5.48% CAR** (negative capital!), **BREACH** ⛔ |
| `run_supervisory_scenarios()` | as above | worst=**SEVERELY_ADVERSE @ -5.48%**, verdict=**FAIL** |
| `capital_projection(ADVERSE, 3yr)` | as above | Year 1: 9.85B/5.97% breach · Year 2: -5.30B/-2.92% breach · Year 3: -20.45B/-10.24% breach |
| `reverse_stress_test()` | as above | Breach at **+15% NPL** + 0bps rate → CAR **13.90%** (FRAGILE for this bank profile) |

**Edge case — strong bank** (80B capital / 200B RWA / 2% NPL / 60B securities / 15B annual profit):

| Engine call | Output |
|---|---|
| `run_supervisory_scenarios()` | Worst=SEVERELY_ADVERSE **@ 18.14%** CAR (above floor) → verdict=**PASS** |
| `reverse_stress_test()` | Breaches only at **+90% NPL increase** (RESILIENT) |

**Engine logic confirmed**: realistic Tier-2 bank fails CBK supervisory test; well-capitalised bank with low NPL passes comfortably. Reverse stress correctly differentiates fragility profiles.

---

## Critical engine API specifics documented

These were verified during smoke testing — the stress engine has subtle behaviour worth documenting:

1. **`StressTestInputs`** is a dataclass with 8 fields all `Optional[Decimal]` except `horizon_years: int = 3`. Missing inputs return `None` results gracefully (Rule 1 transparency).

2. **`apply_scenario(inputs, scenario)`** returns dict with: `scenario`, `shock_parameters` (the SCENARIO_SHOCKS for that key), `starting_capital_kes`, `starting_rwa_kes`, `starting_car_pct`, `stressed_capital_kes`, `stressed_rwa_kes`, `stressed_car_pct`, `car_drop_pp`, `breaches_cbk_minimum`, `cbk_minimum_pct`.

3. **`run_supervisory_scenarios(inputs)`** returns: `scenarios` (per-scenario results), `worst_scenario`, `worst_stressed_car_pct`, `any_scenario_breaches_cbk_min`, `verdict` (PASS/FAIL).

4. **`capital_projection(inputs, scenario)`** returns: `scenario`, `horizon_years`, `yearly_projection` (list of dicts each with `year_index`, `capital_kes`, `rwa_kes`, `car_pct`, `breaches_cbk_min`).

5. **`reverse_stress_test(inputs, breach_threshold_pct=14.5)`** returns: `breach_npl_pct`, `breach_rate_bps`, `stressed_car_pct`, `breach_threshold_pct`, `starting_car_pct`. **`breach_npl_pct` and `stressed_car_pct` may be `None`** if no breach found within search grid (NPL up to `REVERSE_STRESS_MAX_NPL_PCT=100%`, rate up to `REVERSE_STRESS_MAX_RATE_BPS=1500bps` in 5% / 50bps grid steps).

6. **BASELINE scenario produces capital growth** (16.67% → 20.00% in our test) because it includes annual pre-tax profit accretion as the zero-shock baseline (25B + 5B = 30B). This is the engine's design: no shocks but profit still flows.

7. **Capital projection deliberately excludes profit accretion under stressed scenarios** — assumes profitability is itself stressed under adverse conditions. Conservative design choice. The default 5B annual profit is therefore only used in `apply_scenario` baseline, not in `capital_projection`.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event including verdict + worst CAR for traceability:

```
audit_log("IFRS_ENGINE_USED", uname, "Stress #79: 3-scenario verdict=FAIL, worst=SEVERELY_ADVERSE @ -5.48%")
audit_log("IFRS_ENGINE_USED", uname, "Stress #79: projection ADVERSE 3yr, first_breach_year=1")
audit_log("IFRS_ENGINE_USED", uname, "Stress #79: reverse stress, breach @ NPL+15%, rate+0bps, stressed_car=13.90%")
```

---

## ✅ Fourth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 vendors, v5.76 treasury/alm, v5.77 remaining IFRS). G3 (audit_log alias) and G4 (7-tab limit) lessons embedded in process. The page had 4 top-level tabs; adding 1 brings to exactly 5, well within the 7-tab limit.

---

## Honesty discipline visualised

- **Pre-stress CAR traffic light** (WELL_CAPITALISED / AT_MINIMUM / ALREADY_BREACHING) lets users see baseline before running tests
- **Engine constants reference table** in Inputs sub-tab shows exact calibration — no hidden coefficients
- **SCENARIO_SHOCKS dict surfaced** byte-for-byte so users see what shocks each scenario applies
- **PASS/FAIL verdict banner** with worst-case CAR explicitly stated
- **First breach year identified** in capital projection — not just "may breach"
- **Reverse stress with FRAGILE / MODERATE / RESILIENT assessment** — interpretive, not just numeric
- **Plain-English interpretation** of reverse stress numbers ("if X then Y")
- Every engine call audit-logged with verdict and worst CAR

---

## What didn't change

- Engine source file (`utils/stress_testing.py`) — byte-for-byte unchanged
- `scripts/audit.py` — gate G79 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.77 pages — unchanged
- The 4 existing tabs in `35_stress_testing.py` (Scenario Runner, Side-by-Side, Custom Scenario, ICAAP Report) — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.77

| | v5.77 | v5.78 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **22** | **23** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 6 | **7** |
| Lines added across pages this batch | +885 (new page 90) | +338 (stress_testing) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 4-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering, especially the line chart in Capital Projection sub-tab.

2. **23 of 116 integrated** — 93 standards remain library-only.

3. **Inputs are user-entered with sensible defaults — they do NOT auto-pull from CBS or treasury data.** Deliberate because stress testing inputs are a judgment call:
   - Which capital base — fully-loaded Tier 1+2 or transitional?
   - RWA on a stressed basis or current?
   - Pre-tax profit using a base case or a stressed expectation?
   
   The defaults reflect a representative Ecobank-sized Kenyan Tier-2 bank but **should be replaced with real ICAAP-aligned figures before any production use**.

4. **Engine has NO scenario calibration UI** — `SCENARIO_SHOCKS` are bound byte-for-byte. CBK's actual supervisory scenarios change over time; this engine uses fixed Basel-III-style shocks (-3pp/-6pp GDP, +200/+400 bps rates, +30%/+60% NPL increase, etc.). For new CBK Supervisory scenarios (e.g. annual ICAAP-2025 specific calibration), engine code change required. The reference table in Inputs sub-tab shows the bound calibration so users see what's actually being applied.

5. **Capital projection is deliberately conservative** — does NOT include pre-tax profit accretion year-on-year under stressed scenarios (assumes profit itself is stressed). Means projected CAR will be lower than a scenario where profit continues to flow. The default 5B annual profit is therefore unused in projection.

6. **Reverse stress test grid is 5% NPL step × 50 bps rate step** — fine granularity but not continuous. Fractional breach points are not resolved (e.g. if the bank breaches at NPL+12.5%, the engine reports +15%). For ICAAP submission requiring exact breach calibration, finer grid would be needed (engine code change).

7. **Inputs tab uses separate widgets from the existing "Scenario Runner" tab** in the page — intentionally no auto-sync because the existing scenarios use AI-narrative shocks while this engine uses deterministic shocks. User enters input twice if comparing both flows. Documented as a known UX limitation; the alternative (shared state) would couple the deterministic engine to the AI flow which is undesirable.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | HR Performance | #63 + #64 | Enhance `pages/2_people.py` (2 standards in one batch, heavily-used by HR/admin) |
| (2) | CBK Returns | #80 | Enhance regulatory reporting pages |
| (3) | Project / Audit / Compliance | various smaller engines | Multiple smaller integrations |
| (4) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer due to regression risk) |

With the daily risk-management trifecta now complete (v5.72 + v5.76 + v5.78), recommend **(1) HR Performance** for v5.79 — completes a different functional axis (people management) and integrates 2 standards in one batch.

Future batches will increasingly target operational risk + regulatory reporting + HR engines rather than core IFRS or risk metrics, as the major IFRS framework is now covered (v5.77) and the risk-management trifecta is now complete (v5.78).

---

**Cumulative tally:** 116 standards delivered, **23 integrated into UI via 3 dedicated pages + 7 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

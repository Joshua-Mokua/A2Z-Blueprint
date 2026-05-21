# A2Z MIS 360 — CHANGELOG v5.76

**v5.76 Sixth Integration Batch — Treasury / ALM (FX + Liquidity)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **Daily-supervised regulatory metrics now in user hands.** First batch to enhance **two pages in one shipment**. Cumulative: **15 of 116 standards integrated.**

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.76 wires two **daily-supervised** regulatory standards:
- **#75 FX Position Monitoring** (CBK PG/03) — FX exposure limits reported end-of-day
- **#71 Basel III LCR + NSFR** (Liquidity Risk) — LCR daily, NSFR quarterly but driven by daily monitoring

These complement the v5.72 Capital & Risk integration which covered quarterly-to-annual metrics (CAR, IRRBB, Investment Portfolio, Credit Risk Scoring). With v5.76, the standards library now spans the full regulatory reporting cadence from daily through annual.

---

## What was modified

### `pages/25_treasury.py` — FX Position Monitoring tab added
**521 → 779 lines (+258)**

Section 2 (Risk & Control) sub-tabs expanded from 3 to 4:

| # | Sub-tab | Status |
|---|---|---|
| 0 | 📊 ALM & Liquidity | unchanged |
| 1 | 🔒 Limits & Blotter | unchanged |
| 2 | 📐 IFRS 9 | unchanged |
| **3** | **💱 FX Position Monitoring** | **NEW (Standard #75)** |

**FX Monitoring tab** (3 inner sub-tabs):
- **📊 Net Open Position** — auto-aggregates `treasury_fx.json` deal data by currency (BUY=asset, SELL=liability heuristic), allows manual override, surfaces NOP per currency with LONG/SHORT type indicators
- **🚧 Limit Compliance Check** — CBK PG/03 limits (single ≤10% / aggregate ≤20% of core capital), GREEN/AMBER/RED status, per-currency breach list, detail table on demand
- **🔍 Aggregation Method Comparison** — SHORTHAND_METHOD vs SUM_ABSOLUTE side-by-side; explains when method choice matters

### `pages/81_alm.py` — LCR/NSFR tab added (within existing 7-tab budget)
**190 → 457 lines (+267)**

**Critical structural decision**: ALM had 7 top-level tabs already (at G4 limit). Used the v5.73 sub-tab containment pattern:

- **"📊 Gap Analysis"** tab renamed to **"📊 Gap Analysis & Liquidity"**
- Restructured into 2 sub-tabs:
  - 📊 Gap Analysis (original logic preserved byte-for-byte)
  - 💧 LCR / NSFR (Standard #71, integrated v5.76) (new)
- Other 6 top-level tabs (Funding, ALCO, Contingency, New Snapshot, Config, BSC) **completely untouched**

**LCR / NSFR sub-tab** (2 inner sub-tabs):

**💧 LCR (30-day stress):**
- HQLA inputs at 3 levels with engine haircuts (Level 1 = 0%, Level 2A = 15%, Level 2B = 50%)
- 6 outflow categories with engine factors (Retail stable 5%, less-stable 10%, SME ops 25%, corp non-fin 40%, financial 100%, undrawn credit 10%)
- 3 inflow categories (capped at 75% of outflows per Basel III)
- GREEN/AMBER/RED status with compliance verdict
- Per-bucket detail expander showing capping behaviour

**🏗️ NSFR (12-month stable funding):**
- 5 ASF categories (Tier 1/2 cap 100%, retail <1Y 90%, wholesale <1Y 50%, op deposits 50%)
- 5 RSF categories (cash 0%, L1 HQLA 5%, retail loans <1Y 50%, corp loans ≥1Y 85%, mortgage 65%)
- Status verdict + per-category breakdown table

### Engine files — UNCHANGED
`utils/fx_position.py` and `utils/liquidity_risk.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Both pages already registered.

---

## 7 engine paths verified end-to-end

**FX Position (#75) — 4 paths:**

| Input | Engine call | Output |
|---|---|---|
| 3 positions: USD long 2B, EUR short 0.5B, GBP long 0.5B | `net_open_position_per_currency()` | 3 currencies, LONG/SHORT types correct |
| 15B core capital | `fx_exposure_limit_check()` | aggregate **16.67%** (within 20% limit), USD **13.33% > 10% breach**, **status=RED** |
| Same positions | `aggregate_net_open_position("SHORTHAND_METHOD")` | **2.5B** (max of 2.5B long, 0.5B short) |
| Same positions | `aggregate_net_open_position("SUM_ABSOLUTE")` | **3.0B** (sum of \|NOPs\|) |

**Notable**: limit check returned status=**RED with 1 single-currency breach** even though aggregate was within 20% limit. This is exactly why the CBK PG/03 framework imposes both single AND aggregate limits — a Treasury monitoring only aggregate would miss the USD concentration.

**Liquidity (#71) — 3 paths:**

| Input | Engine call | Output |
|---|---|---|
| 15B L1 + 4B L2A + 1B L2B HQLA / 85B outflows + 2B inflows | `lcr()` | LCR **236.25%**, status=GREEN, compliant |
| 15B Tier 1 + 80B retail < 1Y / 25B mortgage + 15B L1 HQLA | `nsfr()` | NSFR **511.76%**, status=GREEN, compliant |
| Inflows capped at 75% of outflows | within `lcr()` | capping logic applied automatically |

---

## Critical engine API specifics documented

These were caught during smoke testing — engine constants are strict and aliased categories don't match.

**FX Position:**
- `FxPosition` fields: `position_id`, `currency`, **`fx_assets_kes_equivalent`**, **`fx_liabilities_kes_equivalent`**, `spot_rate_to_kes`
- `fx_exposure_limit_check` returns `aggregate_pct`, `aggregate_breach`, `single_currency_breaches`, `status`, `per_currency`
- Method strings: **"SHORTHAND_METHOD"** (not just "SHORTHAND") and **"SUM_ABSOLUTE"**

**Liquidity Risk:**
- `HqlaHolding(asset_id=, level=, market_value_kes=)` — level must be **"LEVEL_1"** / **"LEVEL_2A"** / **"LEVEL_2B"**
- `CashFlowItem(item_id=, category=, direction=, balance_kes=)` — direction is **"OUTFLOW"** or **"INFLOW"**, category MUST match `OUTFLOW_RATES_PCT` / `INFLOW_RATES_PCT` keys exactly
- **Outflow categories**: RETAIL_DEPOSITS_STABLE, RETAIL_DEPOSITS_LESS_STABLE, SME_OPERATIONAL, CORPORATE_NON_FINANCIAL, **FINANCIAL_COUNTERPARTY** (not WHOLESALE_NON_OP), UNDRAWN_CREDIT_FACILITIES, UNDRAWN_LIQUIDITY_FACILITIES, DERIVATIVES_NET_OUTFLOW
- **ASF categories**: **TIER_1_CAPITAL** (not TIER_1_TIER_2_CAPITAL), TIER_2_CAPITAL, **RETAIL_DEPOSITS_LT_1Y** (not STABLE_RETAIL_DEPOSITS), WHOLESALE_FUNDING_LT_1Y, OPERATIONAL_DEPOSITS, OTHER_LIABILITIES_LT_6M
- **RSF categories**: CASH, CENTRAL_BANK_RESERVES, **LEVEL_1_HQLA** (not LEVEL_1), LEVEL_2A_HQLA, LEVEL_2B_HQLA, RETAIL_LOANS_LT_1Y, RETAIL_LOANS_GTE_1Y, CORPORATE_LOANS_LT_1Y, CORPORATE_LOANS_GTE_1Y, **MORTGAGE_LOANS** (not PERFORMING_RESIDENTIAL_MORTGAGE), OTHER_ASSETS

**The page surfaces these exact category names** in input field labels alongside their factor percentages, so users see what they're entering rather than a generic label that hides the engine binding.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "FX #75: NOP per ccy, count=3")
audit_log("IFRS_ENGINE_USED", uname, "FX #75: Limit check core_cap=15B, agg_pct=16.67%, status=RED, single_breaches=1")
audit_log("IFRS_ENGINE_USED", uname, "FX #75: Method compare SHORT=2500000000.00, ABS=3000000000.00")
audit_log("IFRS_ENGINE_USED", uname, "Liquidity #71: LCR 236.25%, status=GREEN, compliant=True")
audit_log("IFRS_ENGINE_USED", uname, "Liquidity #71: NSFR 511.76%, status=GREEN, compliant=True")
```

---

## No guardrails tripped this batch

This is the first integration batch since v5.71/72 (the original adds-only ones) where the audit was **clean on first attempt**.

The G4 (7-tab) lesson from v5.73 stuck — I used sub-tab containment on ALM rather than adding an 8th top-level tab. The G3 (audit_log alias) lesson from v5.75 stuck — I imported `audit_log` directly without aliasing.

Two clean lessons embedded in process. Audit framework continues to enforce architectural quality.

---

## Honesty discipline visualised

- **Engine category names surfaced in input labels** — users see exact strings (e.g. "Retail deposits stable @ 5%") rather than abstracted descriptions
- **Single-currency limit breach drives status=RED** even when aggregate is within limits — engine binds CBK PG/03's dual-test interpretation
- **Level 2 cap behaviour** disclosed when applied (`cap_applied=True` surfaced in per-bucket expander)
- **75% inflow cap** hard-coded into Basel III LCR — page shows both gross and capped inflows in detail
- **SHORTHAND vs SUM_ABSOLUTE comparison** is interactive — users see why method choice matters
- Every engine call audit-logged with `IFRS_ENGINE_USED` events

---

## What didn't change

- Both engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G73 (FX) / G71 (LCR/NSFR) still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.75 pages — unchanged
- The 6 ALM tabs (Funding, ALCO, Contingency, New Snapshot, Config, BSC) — unchanged
- The Treasury Section 0 (Overview) and Section 1 (Products) — unchanged

---

## Comparison vs v5.75

| | v5.75 | v5.76 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **13** | **15** ⭐ (+2) |
| Audit gates | 103/103 | 103/103 (unchanged, clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 89 numbered | 89 numbered (unchanged) |
| **Modified existing pages cumulative** | 4 | **6** (first 2-page batch) |
| Lines added across pages this batch | +594 (customer360) | +525 (treasury +258 / alm +267) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Pages pass `python -m py_compile`, module-level import test, and 7-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering.

2. **15 of 116 integrated** — 101 standards remain library-only.

3. **Treasury FX Position uses heuristic mapping** of `treasury_fx.json` deal data: BUY side → assets, SELL side → liabilities, unspecified side split 50/50. This is a simplification — true FX assets/liabilities accounting is more complex (settled vs unsettled, accrued interest in foreign currency, off-balance derivative exposures). The heuristic gives a representative starting point that the user can override before computing limits. **For production, the FX deal book should be properly accounted before being passed to the engine.**

4. **`fx_rates` from `treasury_config.json`** populates default spot rates; user can override. The engine uses KES-equivalent inputs directly so spot rate is metadata only (helpful context, not part of computation).

5. **LCR/NSFR inputs are user-entered** — they do NOT auto-populate from any data source. Deliberate because Basel III categorisation is judgemental (e.g. "is this deposit operational or non-operational?"). The page binds engine constants byte-for-byte so users see the actual factor percentages they're using; no hidden assumptions.

6. **Level 2 cap (40%) and Level 2B sub-cap (15%)** apply automatically in LCR computation — engine returns `cap_applied=True/False` and the page surfaces this in the per-bucket detail expander when applicable.

7. **ALM page restructure preserves all original content byte-for-byte** in the Gap Analysis sub-tab — original logic relocated under `_liq_sub_tabs[0]` exactly. The 6 other top-level tabs are completely untouched.

8. **`treasury_config.json` `fx_rates` fallback** uses ad-hoc rates {USD: 130.50, EUR: 141.20, GBP: 165.80} per the existing page; in production these would come from a market data feed.

9. **The two pages render LCR data on different parts of the screen** — Treasury page shows simplified liquidity ratios in its existing ALM section (unchanged), while ALM page now has the full LCR/NSFR engine. There's no automatic synchronisation between them. For a unified view, the Treasury page would need to call the same engine. Out of scope for this batch.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | Remaining IFRS Engines | #101-#108 | New consolidated page (would integrate **8 standards in one batch**, taking total 15 → 23) |
| (2) | Stress Testing | #79 | Enhance `pages/35_stress_testing.py` |
| (3) | HR Performance | #63 + #64 | Enhance `pages/2_people.py` |
| (4) | BSC Main Page | various | Enhance `pages/1_perform.py` (1908 lines, **higher regression risk**) |
| (5) | CBK Returns | various | Enhance regulatory reporting pages |

Recommend **(1) Remaining IFRS Engines** for v5.77 if **scaling integration breadth fast** is the priority — would more than double the integration tally in a single batch (15 → 23). Single new consolidated page would mirror the v5.71/72 dedicated-page pattern.

Alternative: **(2) Stress Testing** if regulatory urgency outweighs breadth — stress test results feed directly into capital adequacy planning.

---

**Cumulative tally:** 116 standards delivered, **15 integrated into UI via 2 dedicated pages + 6 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

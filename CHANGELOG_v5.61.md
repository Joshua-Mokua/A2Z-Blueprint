# A2Z MIS 360 — CHANGELOG v5.61

**Volume Fifteen — Capital Adequacy / Regulatory Returns**
**Released:** April 2026
**Audit gates:** 76/76 = 100% PASS (was 73/73)
**Test count:** 40 files / 1248 tests (was 39/1180 — added 68 in `tests/test_volume_fifteen_batch.py`)

---

## Standards delivered (4 — all Cat B regulatory ratios)

### #77 Capital Adequacy Ratio (Cat B)
**Module:** `utils/capital_adequacy.py` (~410 LOC)
**Engine:** `CapitalAdequacyEngine`

7 entries: `eligible_cet1`, `eligible_at1`, `eligible_tier2`, `total_capital`, `car_ratios`, `leverage_ratio`, `capital_buffers`.

**Basel III minimums byte-for-byte:**
- BASEL_CET1_MIN = 4.5%
- BASEL_TIER1_MIN = 6.0%
- BASEL_TOTAL_CAR_MIN = 8.0%

**CBK PG/02 minimums byte-for-byte:**
- CBK_CET1_MIN = 10.5%
- CBK_TIER1_MIN = 12.0%
- CBK_TOTAL_CAR_MIN = 14.5%

**Buffer constants byte-for-byte:**

| Constant | Value |
|---|---|
| CAPITAL_CONSERVATION_BUFFER | 2.5% |
| COUNTERCYCLICAL_BUFFER_MAX | 2.5% |
| DSIB_BUFFER_MIN | 1.0% |
| DSIB_BUFFER_MAX | 3.5% |
| LEVERAGE_RATIO_MIN | 3.0% |
| TIER2_CAP_PCT_OF_TIER1 | 100% |

**8 CET1_DEDUCTION_TYPES:** GOODWILL, OTHER_INTANGIBLES, DEFERRED_TAX_ASSETS, MORTGAGE_SERVICING_RIGHTS, INVESTMENTS_IN_OWN_SHARES, RECIPROCAL_CROSS_HOLDINGS, SHORTFALL_PROVISIONS, GAIN_ON_SALE_SECURITISATION.

**Tier 2 caps:**
- General provisions in Tier 2 capped at 1.25% of total RWA per Basel
- Total Tier 2 capped at 100% of Tier 1 per Basel III

**Status determination:** GREEN ≥ CBK_min + 2pp, AMBER ≥ CBK_min, RED < CBK_min.

**Honesty rules:**
- **Rule 1:** ratios=None when RWA≤0 or total_exposures≤0
- **Rule 6:** missing core components surfaced in `missing_core_components_count`

**Self-test:** 16/16 PASS

---

### #78 Risk-Weighted Assets (Cat B)
**Module:** `utils/risk_weighted_assets.py` (~470 LOC)
**Engine:** `RwaEngine`

5 entries: `credit_rwa` (with CCF + CRM), `operational_rwa_bia` (negative years excluded), `operational_rwa_sa`, `market_rwa`, `total_rwa`.

**22 CREDIT_RISK_WEIGHTS_PCT byte-for-byte (Basel III Standardised Approach):**

| Asset class | Weight |
|---|---|
| SOVEREIGN_AAA_TO_AA- | 0% |
| SOVEREIGN_A+_TO_A- | 20% |
| SOVEREIGN_BBB+_TO_BBB- | 50% |
| SOVEREIGN_BB+_TO_B- | 100% |
| SOVEREIGN_BELOW_B- | 150% |
| BANK_AAA_TO_AA- | 20% |
| BANK_UNRATED | 50% |
| CORPORATE_AAA_TO_AA- | 20% |
| CORPORATE_BBB+_TO_BB- | 100% |
| CORPORATE_UNRATED | 100% |
| RETAIL_QUALIFYING | 75% |
| RETAIL_NON_QUALIFYING | 100% |
| MORTGAGE_RESIDENTIAL | 35% |
| MORTGAGE_COMMERCIAL | 100% |
| PAST_DUE_LT_20PCT_PROVS | 150% |
| PAST_DUE_GTE_20PCT_PROVS | 100% |
| EQUITY_LISTED | 250% |
| EQUITY_PRIVATE | 400% |
| OTHER_ASSETS | 100% |

**6 CCF_PCT byte-for-byte:**

| Off-balance category | CCF |
|---|---|
| DIRECT_CREDIT_SUBSTITUTE | 100% |
| TRANSACTION_RELATED_CONTINGENT | 50% |
| TRADE_RELATED_CONTINGENT | 20% |
| COMMITMENTS_GTE_1Y | 50% |
| COMMITMENTS_LT_1Y_REVOCABLE | 0% |
| COMMITMENTS_LT_1Y_IRREVOCABLE | 20% |

**Operational risk constants byte-for-byte:**
- BIA_ALPHA = 15% (Basel III)
- RWA_CONVERSION_FACTOR = 12.5 (= 1 / 8% capital ratio)

**8 SA_BETA business lines byte-for-byte:**

| Business line | Beta |
|---|---|
| CORPORATE_FINANCE | 18% |
| TRADING_AND_SALES | 18% |
| RETAIL_BANKING | 12% |
| COMMERCIAL_BANKING | 15% |
| PAYMENT_AND_SETTLEMENT | 18% |
| AGENCY_SERVICES | 15% |
| ASSET_MANAGEMENT | 12% |
| RETAIL_BROKERAGE | 12% |

**Critical compliance details:**
- **BIA negative-year exclusion:** only positive gross income years counted in 3-year average per Basel
- **EAD computation:** `on_balance + (off_balance × CCF) - eligible_collateral`
- **Total RWA:** Credit + Market + Operational

**Honesty rules:**
- **Rule 1:** market_rwa=None when capital charge None
- **Rule 6:** unknown asset_class excluded with sample surfaced

**Self-test:** 19/19 PASS

---

### #79 Stress Testing Framework (Cat B)
**Module:** `utils/stress_testing.py` (~430 LOC)
**Engine:** `StressTestingEngine`

4 entries: `apply_scenario`, `run_supervisory_scenarios`, `reverse_stress_test`, `capital_projection`.

**3 STRESS_SCENARIOS byte-for-byte (CBK ICAAP supervisory):**

| Parameter | BASELINE | ADVERSE | SEVERELY_ADVERSE |
|---|---|---|---|
| gdp_growth_delta_pp | 0 | -3 | -6 |
| interest_rate_shock_bps | 0 | 200 | 400 |
| npl_increase_pct | 0 | 30 | 60 |
| asset_price_shock_pct | 0 | -15 | -30 |
| fx_devaluation_pct | 0 | 8 | 15 |
| deposit_outflow_pct | 0 | 5 | 15 |
| rwa_inflation_pct | 0 | 10 | 25 |

**Translation factors byte-for-byte:**
- NPL_INCREASE_TO_LOSS_FACTOR = 0.45 (avg LGD on new NPLs)
- ASSET_PRICE_SHOCK_TO_PROVISIONS = 0.5 (50% of paper losses → realised)
- RATE_SHOCK_TO_NII_BPS = 0.5 (half of rate shock impact)

**Profit cushion logic:** annual_pre_tax_profit added back to capital each year (capped at 0 if negative — never adds losses).

**EVE-style loss attribution:**
- `stressed_capital = starting_capital - (NPL_loss + securities_loss + fx_loss) + profit_buffer`
- `stressed_rwa = starting_rwa × (1 + rwa_inflation_pct/100)`

**Reverse stress test:** 2D grid search over NPL × rate.
- NPL step = 5%, max = 100%
- Rate step = 50 bps, max = 1500 bps
- First breach below CBK 14.5% threshold wins

**Honesty rules:**
- **Rule 1:** stressed_car=None when starting RWA≤0
- Deterministic — same input → same output verified

**Self-test:** 15/15 PASS

---

### #80 Regulatory Returns Generator (Cat B)
**Module:** `utils/regulatory_returns.py` (~410 LOC)
**Engine:** `RegulatoryReturnsEngine`

4 entries: `generate_bsd1_daily_liquidity`, `generate_bsd2_balance_sheet`, `generate_bsd3_capital_adequacy`, `generate_bsd17_credit_quality`.

**4 BSD_RETURN_TYPES + frequencies byte-for-byte:**

| Return | Frequency | Purpose |
|---|---|---|
| BSD_1 | DAILY | Liquidity ratio |
| BSD_2 | WEEKLY | Statement of Financial Position |
| BSD_3 | MONTHLY | Capital Adequacy |
| BSD_17 | MONTHLY | Credit Quality classification |

**CBK statutory liquidity ratio (different from Basel LCR — CBK Banking Act PG/05) byte-for-byte:**
- STATUTORY_LIQUIDITY_RATIO_MIN = 20%

**5 LOAN_CLASSIFICATIONS (CBK PG/04) byte-for-byte:**

| Classification | Days past due | Provision % |
|---|---|---|
| NORMAL | 0-30 | 1% |
| WATCH | 31-60 | 3% |
| SUBSTANDARD | 61-90 | 20% |
| DOUBTFUL | 91-180 | 50% |
| LOSS | 181+ | 100% |

**BSD-2 balance sheet check:** validates total_assets = total_liabilities + equity within KES 100 rounding tolerance.

**BSD-3 single-source-of-truth:** imports CBK minimums directly from `utils.capital_adequacy` (no duplication).

**Honesty rules:**
- **Rule 1:** ratios=None when denominator≤0 (deposits=0 → liquidity_ratio=None; RWA=0 → CAR=None)
- **Rule 6:** missing required fields → return NOT generated (fail closed) with `validation_errors[]` surfaced

**Self-test:** 18/18 PASS

---

## Audit gates added (3)

### G74 `capital_adequacy_correct`
Inline programmatic — Basel III minimums + CBK PG/02 minimums + 5 buffer constants byte-for-byte. **Runtime:** CET1 computation 5+2+3+0.5-0.1-0.05=10.35B verified; Tier 2 general provisions cap (500M/10B → 125M); Rule 1 RWA=0 → ratios=None; Rule 1 zero exposures → leverage_ratio=None; buffer invalid input rejected; Rule 6 missing components surfaced.

**Tampering verified:** BASEL_CET1_MIN_PCT (4.5→1.0) caught.

### G75 `rwa_correct`
Inline programmatic — 11 CREDIT_RISK_WEIGHTS_PCT + 5 CCF_PCT + BIA constants + 3 SA_BETA business lines byte-for-byte. **Runtime:** 100M sovereign → 0 RWA; 100M mortgage residential → 35M RWA; 100M off-balance × 50% CCF × 100% RW = 50M RWA; BIA 1B avg × 15% × 12.5 = 1.875B operational RWA; market 100M × 12.5 = 1.25B RWA. Rule 1 + Rule 6 paths.

**Tampering verified:** MORTGAGE_RESIDENTIAL (35→90) caught.

### G76 `stress_test_returns_correct`
Combined inline programmatic for #79 + #80.
- **Stress (#79):** 3 scenarios + ADVERSE/SEVERELY_ADVERSE shock parameters byte-for-byte; factor constants 0.45/0.5 byte-for-byte; SEVERELY_ADVERSE worst scenario verified; Rule 1 + unknown scenario rejected
- **Returns (#80):** 4 BSD types + frequencies byte-for-byte; STATUTORY_LIQUIDITY=20% byte-for-byte; 5 LOAN_CLASSIFICATIONS + day ranges + provisions byte-for-byte; runtime BSD-1 (13B/50B = 26%); BSD-17 5 loans → 60% NPL + 1.74M provisions; Rule 1 + Rule 6

**Tampering verified:**
- SCENARIO_SHOCKS["SEVERELY_ADVERSE"]["npl_increase_pct"] (60→0) caught
- LOAN_PROVISION_PCT["LOSS"] (100→10) caught

---

## Spec deviations (cumulative — UNCHANGED at 9)

No new spec deviations introduced in v5.61. All 4 standards delivered as Cat B with full deterministic implementation.

---

## Rule application status (UNCHANGED)

- **Rule 4 applications:** 6 (no change in v5.61)
- **Rule 7 applications:** 6 (no change in v5.61 — all 4 standards Cat B regulatory ratios, no ML branches)

---

## Why this batch matters

The Capital Adequacy / Regulatory Returns batch represents the bank's **core supervisory submission capability**. Every metric here goes directly to CBK BSD on prescribed schedules:
- **Daily** BSD-1 (liquidity ratio)
- **Weekly** BSD-2 (statement of financial position)
- **Monthly** BSD-3 (capital adequacy) + BSD-17 (credit quality)

Byte-for-byte fidelity to Basel III + CBK PG/02 + CBK PG/04 + CBK PG/05 numerical specifications is critical — these are the exact numbers the CBK supervisor matches against bank submissions, and any drift becomes a regulatory finding.

The combination of:
- Decimal precision (28 digits)
- Tier 2 provisions cap at 1.25% RWA
- Basel III BIA negative-year exclusion
- Three-scenario supervisory stress framework
- Reverse stress 2D grid search
- Single-source-of-truth import from `utils.capital_adequacy` in BSD-3
- Explicit Rule 1 + Rule 6 honesty paths

means: when the bank reports CET1=13.5%, Tier1=14.7%, Total CAR=16.8%, Leverage=4.2%, Statutory Liquidity=26%, NPL=8.5%, severely-adverse stressed CAR=15.1% — those numbers can be submitted to CBK BSD with confidence that they are not the result of silent imputation, default-classification of loans into safer buckets, or operational risk inflation from negative-year cherry-picking.

**Volume Fifteen completes the regulatory backbone.** With Volumes Fourteen (Treasury/ALM) and Fifteen (Capital/Returns) shipped, the platform now covers the **full prudential reporting stack** — LCR/NSFR/IRRBB/FX (#73-#76) + CAR/RWA/Stress/BSD Returns (#77-#80) — that defines a CBK-supervised commercial bank's regulatory existence.

---

## What's new in v5.61 vs v5.60

| | v5.60 | v5.61 |
|--|-------|-------|
| Standards delivered | 76 | **80** |
| Audit gates | 73/73 | **76/76 = 100%** |
| Test files | 39 | **40** |
| Total tests | 1180 | **1248** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 4 applications | 6 | 6 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Next: Volume Sixteen #81-#84

Anticipated standards (subject to A2Z_Continuation_Spec_v6.md):
- #81-#84 — likely Audit / Internal Controls or Reporting Automation

Target: 4 engines + tests + 3 gates G77-G79 → 79/79.

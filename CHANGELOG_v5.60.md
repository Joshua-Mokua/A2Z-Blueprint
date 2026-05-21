# A2Z MIS 360 — CHANGELOG v5.60

**Volume Fourteen — Treasury / ALM Intelligence**
**Released:** April 2026
**Audit gates:** 73/73 = 100% PASS (was 70/70)
**Test count:** 39 files / 1180 tests (was 38/1115 — added 65 in `tests/test_volume_fourteen_batch.py`)

---

## Standards delivered (4 — all Cat B regulatory ratios)

### #73 Liquidity Risk LCR/NSFR (Cat B)
**Module:** `utils/liquidity_risk.py` (~470 LOC)
**Engine:** `LiquidityRiskEngine`

6 entries: `hqla_value` (haircuts + Level 2 caps), `net_cash_outflows_30d` (75% inflow cap), `lcr`, `available_stable_funding`, `required_stable_funding`, `nsfr`.

**HQLA classifications byte-for-byte (Basel III standardised):**

| Level | Haircut | Notes |
|---|---|---|
| LEVEL_1 | 0% | Cash, central bank reserves, govt securities |
| LEVEL_2A | 15% | Sovereign / PSE / MDB securities |
| LEVEL_2B | 50% | Corporate bonds, equities |

**Caps:** Level 2 total ≤ 40% of HQLA; Level 2B ≤ 15% of HQLA.

**Compliance thresholds byte-for-byte:**
- LCR_MIN = 100%
- NSFR_MIN = 100%
- INFLOW_CAP = 75% of outflows

**8 OUTFLOW_RATES_PCT byte-for-byte (Basel III standardised):**

| Category | Rate |
|---|---|
| RETAIL_DEPOSITS_STABLE | 5% |
| RETAIL_DEPOSITS_LESS_STABLE | 10% |
| SME_OPERATIONAL | 25% |
| CORPORATE_NON_FINANCIAL | 40% |
| FINANCIAL_COUNTERPARTY | 100% |
| UNDRAWN_CREDIT_FACILITIES | 10% |
| UNDRAWN_LIQUIDITY_FACILITIES | 30% |
| DERIVATIVES_NET_OUTFLOW | 100% |

**4 INFLOW_RATES_PCT, 6 ASF_FACTORS_PCT, 11 RSF_FACTORS_PCT** — all byte-for-byte per Basel III standardised tables.

**Honesty rules:**
- **Rule 1:** LCR=None when NCO≤0; NSFR=None when RSF≤0
- **Rule 6:** holdings/deposits with missing values surfaced in `excluded_count`; **NEVER silently classified into highest-quality bucket**

**Self-test:** 17/17 PASS

---

### #74 Interest Rate Risk in Banking Book (Cat B)
**Module:** `utils/irrbb.py` (~360 LOC)
**Engine:** `IrrbbEngine`

4 entries: `repricing_gap` (cumulative gap by tenor), `nii_sensitivity_200bps` (12-month time-weighted), `eve_sensitivity` (PV-based with mid-bucket duration), `all_scenarios_summary`.

**11 REPRICING_BUCKETS byte-for-byte** with bucket midpoint days:

| Bucket | Midpoint days |
|---|---|
| ON_DEMAND | 1 |
| 1M | 15 |
| 3M | 60 |
| 6M | 135 |
| 1Y | 270 |
| 2Y | 540 |
| 3Y | 900 |
| 5Y | 1440 |
| 7Y | 2160 |
| 10Y | 3240 |
| 10Y_PLUS | 4320 |

**6 SHOCK_SCENARIOS byte-for-byte (BCBS 368 standardised April 2016):**

| Scenario | Definition |
|---|---|
| PARALLEL_UP | all = +200 bps |
| PARALLEL_DOWN | all = -200 bps |
| STEEPENER | short = -65, long = +90 |
| FLATTENER | short = +90, long = -65 |
| SHORT_RATE_UP | short = +300 |
| SHORT_RATE_DOWN | short = -300 |

**Outlier thresholds byte-for-byte (BCBS 368 + CBK supervisory):**
- EVE_OUTLIER_THRESHOLD = 15% of Tier 1 capital
- NII_OUTLIER_THRESHOLD = 5% of Tier 1 capital
- NII_STANDARD_SHOCK = 200 bps

**NII formula:** Only buckets repricing within 1 year contribute (ON_DEMAND, 1M, 3M, 6M, 1Y); time-weighted by `(365 - midpoint_days) / 365`.

**EVE formula:** `-net_position × duration × shock_decimal` per bucket, summed; uses bucket midpoint years as duration approximation. Short = ON_DEMAND through 1Y, long = 5Y+, others (2Y, 3Y) blended midpoint.

**Honesty rules:**
- **Rule 1:** NII/EVE outlier_pct=None when tier_1_capital≤0
- **Rule 6:** missing RSA/RSL excluded with count; unknown buckets excluded

**Self-test:** 14/14 PASS

---

### #75 FX Position Monitoring (Cat B)
**Module:** `utils/fx_position.py` (~310 LOC)
**Engine:** `FxPositionMonitoringEngine`

4 entries: `net_open_position_per_currency`, `aggregate_net_open_position`, `fx_exposure_limit_check`, `fx_pnl_attribution`.

**CBK Banking Act / PG/03 limits byte-for-byte:**
- SINGLE_CURRENCY_LIMIT = 10% of core capital
- AGGREGATE_FX_LIMIT = 20% of core capital

**14 SUPPORTED_CURRENCIES (ISO 4217):** USD, EUR, GBP, JPY, CHF, CNY, INR, ZAR, UGX, TZS, RWF, ETB, AED, ZMW (Kenyan banking context — covers EAC + major trading partners).

**2 AGGREGATION_METHODS:**
- SHORTHAND_METHOD = max(sum_long, sum_short) — Basel standardised
- SUM_ABSOLUTE = sum_long + sum_short — more conservative

**Status bands:** RED on any breach, AMBER when within 80% of aggregate limit, GREEN otherwise.

**Honesty rules:**
- **Rule 1:** aggregate_pct=None when core_capital≤0
- **Rule 6:** positions with missing assets/liabilities excluded; **unknown currency codes surfaced in `unknown_currencies[]`** (NEVER silently aggregated as USD or any default)

**Self-test:** 15/15 PASS

---

### #76 Investment Portfolio Analytics (Cat B)
**Module:** `utils/investment_portfolio.py` (~470 LOC)
**Engine:** `InvestmentPortfolioEngine`

6 entries: `portfolio_market_value`, `bond_modified_duration` (Macaulay/Modified), `portfolio_weighted_duration`, `yield_to_maturity` (Newton-Raphson), `hqla_classification`, `concentration_risk`.

**7 INSTRUMENT_TYPES byte-for-byte:** GOVERNMENT_BOND, TREASURY_BILL, CORPORATE_BOND, MUNICIPAL_BOND, EQUITY, MUTUAL_FUND, STRUCTURED_NOTE.

**4 HQLA_CLASS:** LEVEL_1, LEVEL_2A, LEVEL_2B, NON_HQLA.

**RATING_TO_HQLA_LEVEL byte-for-byte:**
- AAA / AA+ / AA / AA- → LEVEL_1
- A+ / A / A- → LEVEL_2A
- BBB+ / BBB / BBB- → LEVEL_2B
- Below BBB- → NON_HQLA

**HQLA classification logic:** is_sovereign first → LEVEL_1; TREASURY_BILL → LEVEL_1; EQUITY → NON_HQLA; rating-based fallback for all others.

**Concentration limits byte-for-byte (CBK PG/04):**
- SINGLE_ISSUER_LIMIT = 25% of core capital
- SINGLE_SECTOR_LIMIT = 35% of investment book

**Bond mathematics:**
- Macaulay Duration = `sum(t × CF_t / (1+y)^t) / PV` (in periods, divided by frequency for years)
- Modified Duration = `Macaulay / (1 + y/k)` where k = compounding frequency (semi-annual default freq=2)

**YTM solver (Newton-Raphson):**
- max_iterations = 100
- tolerance = Decimal("0.0001")
- derivative `dpv/dy = -t × cf / (1+y)^(t+1)`
- convergence on `|f| < 0.0001`
- initial guess = coupon rate
- **At-par convergence verified:** 12% coupon at price=100 → YTM≈12% within 0.05 tolerance

**Honesty rules:**
- **Rule 1:** YTM=None on non-convergence; portfolio_modified_duration=None on zero MV
- **Rule 6:** bonds with missing required fields excluded with reason="missing_required_fields"; matured bonds → reason="matured_or_invalid_dates"

**Self-test:** 19/19 PASS

---

## Audit gates added (3)

### G71 `liquidity_risk_correct`
Inline programmatic — verifies 3 HQLA haircuts + 3 compliance thresholds + 2 Level 2 caps + 6 OUTFLOW_RATES + ASF/RSF factors byte-for-byte. **Runtime checks:** 100M LEVEL_2A → 85M after 15% haircut; 100M retail stable @ 5% runoff → 5M outflow; 100M wholesale inflow vs 40M corporate outflow → capped at 30M (75% of 40M). Rule 1 + Rule 6 paths.

**Tampering verified:** LEVEL_2A haircut (15→5) caught.

### G72 `irrbb_correct`
Inline programmatic — 11 REPRICING_BUCKETS + 6 SHOCK_SCENARIOS (both legs of STEEPENER/FLATTENER) + 3 outlier thresholds byte-for-byte. Rule 1 + Rule 6 paths; unknown scenario rejected; outlier detection runtime: 10B gap vs 100M T1 → NII outlier=True.

**Tampering verified:** PARALLEL_UP shock (200→100) caught.

### G73 `treasury_alm_correct`
Combined inline programmatic for #75 + #76.
- **FX (#75):** 2 limits + 8 currencies + 2 methods byte-for-byte; SHORTHAND vs SUM_ABSOLUTE divergence (20M long + 30M short → SHORTHAND=30M, SUM_ABSOLUTE=50M); single 30%>10% breach; Rule 1 + Rule 6 (unknown currency surfaced)
- **Portfolio (#76):** 2 concentration limits + 4 HQLA_CLASS + rating mapping byte-for-byte; **YTM Newton-Raphson at-par convergence verified**; 60M issuer vs 100M capital → 25% breach

**Tampering verified:**
- SINGLE_CURRENCY_LIMIT_PCT (10→50) caught
- SINGLE_ISSUER_LIMIT_PCT (25→90) caught

---

## Spec deviations (cumulative — UNCHANGED at 9)

No new spec deviations introduced in v5.60. All 4 standards delivered as Cat B with full deterministic implementation.

| # | Volume | Deviation |
|---|---|---|
| 1 | v5.49 | Heatmap React→Streamlit/plotly |
| 2 | v5.51 | React SPA + React Native scaffolding |
| 3 | v5.52 | Rule 7 / Cat D scaffolding pattern formalised |
| 4 | v5.52 | #48 LLM commentary deferred |
| 5 | v5.55 | CBK reports: 3 of 8 implemented, 5 deferred |
| 6 | v5.56 | FATCA Form 8966 XML and OECD CRS XML deferred to v7 |
| 7 | v5.57 | ML-based sentiment classification deferred to v7 |
| 8 | v5.59 | ML-based churn classifier (gradient boosting / neural net) deferred to v7 |
| 9 | v5.59 | ML-based recommender (collaborative filtering / deep learning) deferred to v7 |

---

## Rule application status (UNCHANGED)

- **Rule 4 applications:** 6 (no change in v5.60)
- **Rule 7 applications:** 6 (no change in v5.60 — all 4 standards Cat B regulatory ratios)

---

## Why this batch matters

The Treasury / ALM Intelligence batch represents the bank's **first-line regulatory-defense capability**. Every metric here is what CBK supervisors and Basel reviewers actively check during inspections.

Byte-for-byte fidelity to the standardised Basel III + BCBS 368 + CBK PG/03 + CBK PG/04 numerical specifications is critical — these are the literal numbers that determine whether the bank passes or fails its regulatory ratios.

The combination of:
- Decimal precision (28 digits)
- Newton-Raphson YTM convergence
- BCBS 368 six-scenario IRRBB framework
- Explicit Rule 1 + Rule 6 honesty paths

means: when the engine reports LCR=145%, NSFR=132%, NII outlier=False, EVE outlier=False, single-currency FX exposures all<10%, aggregate FX<20%, no issuer concentration breach — the bank can submit those numbers to CBK BSD with confidence that they are not the result of silent imputation, default-classification into safer buckets, or floating-point drift.

---

## What's new in v5.60 vs v5.59

| | v5.59 | v5.60 |
|--|-------|-------|
| Standards delivered | 72 | **76** |
| Audit gates | 70/70 | **73/73 = 100%** |
| Test files | 38 | **39** |
| Total tests | 1115 | **1180** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 4 applications | 6 | 6 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Next: Volume Fifteen — Capital Adequacy / Regulatory Returns (#77-#80)

Anticipated standards (subject to A2Z_Continuation_Spec_v6.md):
- #77 Capital Adequacy Ratio (CAR) — Tier 1, Tier 2, Total CAR per Basel III + CBK
- #78 Risk-Weighted Assets (RWA) — Standardised Approach
- #79 Stress Testing Framework — supervisory + reverse stress
- #80 Regulatory Returns Generator — CBK BSD reports

Target: 4 engines + tests + 3 gates G74-G76 → 76/76.

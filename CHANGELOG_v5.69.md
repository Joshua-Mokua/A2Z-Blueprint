# A2Z MIS 360 — CHANGELOG v5.69

**Volume Twenty-Three — IFRS Provisions / Disclosures / Presentation / Policies**
**Released:** April 2026
**Audit gates:** 100/100 = 100% PASS (was 97/97) — **G100 milestone**
**Test count:** 48 files / 2106 tests (was 47/1977 — added 129 in `tests/test_volume_twenty_three_batch.py`)
**Milestone:** Third post-centennial volume — 15 IFRS pillars now bound to byte-for-byte definitions; 100 audit gates milestone matched to 112 standards.

---

## Standards delivered (4 — all Cat B)

### #109 IAS 37 Provisions / Contingent Liabilities & Contingent Assets
**File:** `utils/provisions.py` (~632 LOC)
**Regulatory anchor:** IAS 37 (recognition of provisions, contingent liabilities, contingent assets — the asymmetric treatment principle)
**Engine:** `ProvisionsEngine`
**Methods:** `probability_classification`, `liability_treatment`, `asset_treatment`, `provision_measurement`, `onerous_contract_test`, `reimbursement_treatment`

**Byte-for-byte literals:**
- 4 `PROBABILITY_LEVELS` (IAS 37.23): VIRTUALLY_CERTAIN, PROBABLE, POSSIBLE, REMOTE
- 3 `RECOGNITION_OUTCOMES`: RECOGNISE, DISCLOSE, NEITHER
- 3 `PROVISION_TYPES`: LEGAL_OBLIGATION, CONSTRUCTIVE_OBLIGATION, ONEROUS_CONTRACT
- 5 `PROVISION_RECOGNITION_CRITERIA` (IAS 37.14)
- 3 `EXPECTED_VALUE_METHODS` (IAS 37.39): SINGLE_OBLIGATION, LARGE_POPULATION, CONTINUOUS_RANGE
- `VIRTUALLY_CERTAIN_PCT_MIN = Decimal("95")`
- `PROBABLE_PCT_MIN = Decimal("51")`
- `POSSIBLE_PCT_MIN = Decimal("5")`

**Runtime verified:**
- Probability classification at all 4 boundaries (96=VIRTUALLY_CERTAIN, 95 inclusive, 70=PROBABLE, 51 inclusive, 50=POSSIBLE, 5 inclusive, 4=REMOTE)
- **Liability treatment:** PROBABLE+reliable_estimate=RECOGNISE; PROBABLE+no_estimate=DISCLOSE; POSSIBLE=DISCLOSE; REMOTE=NEITHER
- **ASYMMETRIC asset treatment** per IAS 37.31-35 — VIRTUALLY_CERTAIN=RECOGNISE; **PROBABLE=DISCLOSE only (NOT recognised)**; POSSIBLE/REMOTE=NEITHER

**Rules applied:**
- Rule 1: classification=None when probability missing
- Rule 6: probability > 100% rejected (fail closed)

**Self-test:** 33/33

---

### #110 IFRS 7 Financial Instruments Disclosures
**File:** `utils/ifrs7_disclosures.py`
**Regulatory anchor:** IFRS 7 (significance, risk types, hedging, concentration disclosures)

**Byte-for-byte literals:**
- 3 `DISCLOSURE_CATEGORIES`: SIGNIFICANCE_TO_FINANCIAL_POSITION, NATURE_AND_EXTENT_OF_RISKS, QUANTITATIVE_RISK_DATA
- 3 `RISK_TYPES` (IFRS 7.31-42): CREDIT_RISK, LIQUIDITY_RISK, MARKET_RISK
- 4 `CREDIT_QUALITY_BANDS`: INVESTMENT_GRADE, NON_INVESTMENT_GRADE, SUB_INVESTMENT_GRADE, UNRATED
- 5 `MATURITY_BUCKETS`: ON_DEMAND, UP_TO_3_MONTHS, THREE_TO_12_MONTHS, ONE_TO_5_YEARS, OVER_5_YEARS
- 3 `MARKET_RISK_VARIABLES`: INTEREST_RATE, FOREIGN_EXCHANGE, EQUITY_PRICE
- 3 `HEDGE_TYPES` (IFRS 7.21-24): FAIR_VALUE_HEDGE, CASH_FLOW_HEDGE, NET_INVESTMENT_HEDGE
- `INDUSTRY_CONCENTRATION_PCT_THRESHOLD = Decimal("25")`
- `SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD = Decimal("10")`

**Self-test:** 33/33

---

### #111 IAS 1 Presentation of Financial Statements
**File:** `utils/ias1_presentation.py`
**Regulatory anchor:** IAS 1 (statement components, going concern, current/non-current classification, OCI recycling, materiality)

**Byte-for-byte literals:**
- 5 `COMPLETE_STATEMENTS_COMPONENTS` (IAS 1.10): SoFP, SoP&L+OCI, SoCE, SoCF, Notes
- 3 `GOING_CONCERN_OUTCOMES`
- 5 `CURRENT_ASSET_CRITERIA` (IAS 1.66)
- 5 `CURRENT_LIABILITY_CRITERIA` (IAS 1.69)
- 2 `OCI_CLASSIFICATIONS`: RECYCLABLE_TO_PNL, NEVER_RECYCLED
- 5 `OCI_LINE_ITEMS`: REVALUATION_SURPLUS, FVTOCI_DEBT_FAIR_VALUE_CHANGES, FVTOCI_EQUITY_FAIR_VALUE_CHANGES, CASH_FLOW_HEDGE_RESERVE, DEFINED_BENEFIT_REMEASUREMENT
- **OCI_RECYCLING_MAP** (the most error-prone area in IFRS):
  - REVALUATION_SURPLUS → NEVER_RECYCLED (IAS 16)
  - FVTOCI_DEBT_FAIR_VALUE_CHANGES → RECYCLABLE_TO_PNL (IFRS 9 — recycles on disposal)
  - **FVTOCI_EQUITY_FAIR_VALUE_CHANGES → NEVER_RECYCLED** (IFRS 9 — most common error)
  - CASH_FLOW_HEDGE_RESERVE → RECYCLABLE_TO_PNL (IFRS 9 — recycles when hedged item affects P&L)
  - DEFINED_BENEFIT_REMEASUREMENT → NEVER_RECYCLED (IAS 19R)
- 2 `STATEMENT_FORMATS`: SINGLE_STATEMENT, TWO_STATEMENT
- `MATERIALITY_PCT_OF_EQUITY = Decimal("5")`
- `MATERIALITY_PCT_OF_REVENUE = Decimal("5")`
- `MATERIALITY_PCT_OF_TOTAL_ASSETS = Decimal("1")`

**Self-test:** 33/33

---

### #112 IAS 8 Accounting Policies, Changes in Estimates & Errors
**File:** `utils/ias8_policies.py`
**Regulatory anchor:** IAS 8 (policy hierarchy, change classification, application methods, error correction)

**Byte-for-byte literals:**
- 3 `CHANGE_TYPES` (IAS 8.5): CHANGE_IN_ACCOUNTING_POLICY, CHANGE_IN_ACCOUNTING_ESTIMATE, CORRECTION_OF_PRIOR_PERIOD_ERROR
- 3 `APPLICATION_METHODS`: RETROSPECTIVE_APPLICATION (policies), PROSPECTIVE_APPLICATION (estimates), RETROSPECTIVE_RESTATEMENT (errors)
- 3 `ERROR_PRESENTATION_OUTCOMES`: RESTATE_COMPARATIVE_AMOUNTS, RESTATE_OPENING_BALANCES, DISCLOSE_ONLY (when impracticable)
- 4 `POLICY_CHANGE_TRIGGERS`: REQUIRED_BY_IFRS, VOLUNTARY_FAITHFUL_REPRESENTATION, VOLUNTARY_RELEVANT_INFORMATION, NOT_PERMITTED
- 5 `POLICY_HIERARCHY_LEVELS` (IAS 8.10-12)
- 3 `ESTIMATE_CHANGE_REASONS`: NEW_INFORMATION, NEW_DEVELOPMENTS, MORE_EXPERIENCE
- `PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY = Decimal("1")`
- `PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT = Decimal("5")`

**Self-test:** 31/31

---

## Audit gates added (3) — milestone G100

### G98 — provisions_correct
- All #109 byte-for-byte literals (4 levels, 3 outcomes, 3 types, 5 criteria, 3 methods, thresholds 95/51/5)
- Runtime: probability classification at all 4 boundaries; liability treatment 4 paths; **ASYMMETRIC asset treatment 4 paths** (the conservatism principle in production code)
- **Tamper test:** VIRTUALLY_CERTAIN_PCT_MIN (95→1) caught

### G99 — ifrs7_disclosures_correct
- All #110 byte-for-byte literals (3 categories, 3 risks, 4 credit bands, 5 maturity buckets, 3 mkt vars, 3 hedge types, concentration thresholds 25%/10%)
- **Tamper test:** RISK_TYPES dropped CREDIT_RISK caught

### G100 — ias1_ias8_correct (combined #111 + #112)
- **IAS 1:** 5 statement components + 3 going concern + 5 current asset criteria + 5 current liability criteria + 2 OCI classifications + 5 OCI line items + **complete OCI_RECYCLING_MAP byte-for-byte** + 2 statement formats + materiality (5%/5%/1%)
- **IAS 8:** 3 change types + 3 application methods + 3 error outcomes + 4 policy triggers + 5 hierarchy levels + 3 estimate reasons + prior period error materiality (1%/5%)
- **Tamper tests:** OCI recycling for FVTOCI_DEBT (RECYCLABLE→NEVER) caught; CHANGE_TYPES dropped CHANGE_IN_ACCOUNTING_POLICY caught

---

## Comparison vs v5.68

| | v5.68 | v5.69 |
|--|-------|-------|
| Standards | 108 | **112** |
| Audit gates | 97/97 = 100% | **100/100 = 100%** ⭐ |
| Test files | 47 | **48** |
| Test count | 1977 | **2106** (+129) |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Spec deviations (cumulative — still 9, no new in v5.69)

1. (v5.49) Heatmap React→Streamlit/plotly
2. (v5.51) React SPA + React Native scaffolding
3. (v5.52) Rule 7 / Cat D scaffolding pattern formalised
4. (v5.52) #48 LLM commentary deferred
5. (v5.55) CBK reports: 3 of 8 implemented, 5 deferred
6. (v5.56) FATCA Form 8966 XML and OECD CRS XML deferred to v7
7. (v5.57) ML-based sentiment classification deferred to v7
8. (v5.59) ML-based churn classifier deferred to v7
9. (v5.59) ML-based recommender deferred to v7

**No new spec deviations in v5.69.** All 4 standards Cat B with full deterministic implementation.

---

## Strategic narrative — Three high-stakes regulatory boundary semantics

This volume materialises three of the most commonly misstated areas in regulated bank financial reporting:

**IAS 37 asymmetric treatment (#109)** — the conservatism principle is encoded in production code, not as a guideline but as a literal threshold split:
- Liabilities recognised at **PROBABLE (>50%)**
- Assets recognised only at **VIRTUALLY_CERTAIN (≥95%)**

The most common banking misstatement is recognising a contingent asset at PROBABLE (a recoverable from insurance settlement, a claimed tax refund), inflating earnings. The engine returns DISCLOSE not RECOGNISE for PROBABLE assets — fail-closed by design per IAS 37.34.

**IAS 1 OCI recycling map (#111)** — the bank's OCI items recycle to P&L at different times and via different rules. The map encodes them precisely:

| OCI item | Recycling | Source |
|---|---|---|
| Revaluation surplus | NEVER | IAS 16 |
| FVTOCI debt | RECYCLABLE on disposal | IFRS 9 |
| **FVTOCI equity** | **NEVER** | **IFRS 9** |
| Cash flow hedge reserve | RECYCLABLE when hedged item affects P&L | IFRS 9 |
| DB remeasurement | NEVER | IAS 19R |

Banks routinely get equity FVTOCI recycling wrong because **IAS 39 used to allow recycling of available-for-sale equity gains, but IFRS 9 explicitly removed this**. The transition was deliberate. The engine binds the post-IFRS 9 rule.

**IAS 8 retrospective vs prospective (#112)** — the engine binds the application method to the change type:
- Policy changes → retrospective restatement of prior periods
- Estimate changes → prospective only (no restatement)
- Errors → retrospective restatement

The most common audit finding is treating a policy change as an estimate change (prospective only) to avoid restating comparatives. Restating comparatives forces prior years to look worse and is therefore disliked by management — but IAS 8 doesn't permit the workaround.

**15 IFRS pillars now bound to byte-for-byte definitions:**
IFRS 7, IFRS 9, IFRS 10, IAS 28, IFRS 11, IFRS 13, IFRS 15, IFRS 16, IAS 1, IAS 8, IAS 12, IAS 19, IAS 21, IAS 33, IAS 36, IAS 37 — every IFRS standard most regulated banks materially rely on for consolidated financial reporting **plus the framework standards (IAS 1 presentation, IAS 8 policies)** that govern how the other standards are applied.

**Cumulative tally:** 112 standards delivered, 100 audit gates ⭐, 2106 tests, 9 spec deviations, 6 Rule 7 applications.

---

**Plan reminder:** per Joshua's evening message, after one more standards volume (V24) we pivot to the integration layer before the next continuation batch.

**Next options for V24 (#113-#116):**
- IFRS 5 Non-Current Assets Held for Sale & Discontinued Operations
- IAS 7 Cash Flow Statements
- IFRS 8 Operating Segments
- IAS 24 Related Party Disclosures

Or specialised banking topics: CECL, hedge accounting refinement, structured products. Target 103/103.

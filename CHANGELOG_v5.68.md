# A2Z MIS 360 — CHANGELOG v5.68

**Volume Twenty-Two — IFRS Impairment / Deferred Tax / Revenue / Earnings Per Share**
**Released:** April 2026
**Audit gates:** 97/97 = 100% PASS (was 94/94)
**Test count:** 47 files / 1977 tests (was 46/1855 — added 122 in `tests/test_volume_twenty_two_batch.py`)
**Milestone:** Second post-centennial volume — 11 IFRS pillars now bound to byte-for-byte definitions.

---

## Standards delivered (4 — all Cat B)

### #105 IAS 36 Asset Impairment
**File:** `utils/asset_impairment.py` (~566 LOC)
**Regulatory anchor:** IAS 36 (recoverable amount, impairment indicators, CGU, reversal rules)
**Engine:** `ImpairmentEngine`
**Methods:** `value_in_use_pv`, `recoverable_amount`, `impairment_loss`, `validate_impairment_indicator`, `cgu_classification`, `reversal_eligibility`

**Byte-for-byte literals:**
- 3 `RECOVERABLE_AMOUNT_BASES` (IAS 36.6/18): VALUE_IN_USE, FAIR_VALUE_LESS_COSTS_OF_DISPOSAL, HIGHER_OF
- 7 `IMPAIRMENT_INDICATORS_EXTERNAL` (IAS 36.12)
- 5 `IMPAIRMENT_INDICATORS_INTERNAL` (IAS 36.12)
- 3 `ASSET_TEST_FREQUENCIES` (IAS 36.9-10): ANNUAL_MANDATORY (goodwill + indefinite-life intangibles), ANNUAL_IF_INDICATOR, AT_INDICATOR_TRIGGER
- 2 `ASSET_GROUPINGS`: INDIVIDUAL_ASSET, CASH_GENERATING_UNIT
- `GOODWILL_REVERSAL_PROHIBITED = True` (IAS 36.124)
- `OTHER_ASSET_REVERSAL_ALLOWED = True` (subject to ceiling per IAS 36.117-118)

**Runtime verified:**
- VIU at 0% over (1, 100K) + (2, 100K) = 200,000.00 (sum)
- VIU at 10% on (1, 100K) ≈ 90,909.09 (in [90K, 91K] band)
- recoverable = max(VIU 800K, FVLCD 900K) = 900,000.00 with basis tracking
- VIU > FVLCD → use VIU; only one available → use that one (IAS 36.20)
- Impairment loss CA 1.2M - RA 1M = 200,000.00 (impaired=True, post_CA=1M)
- CA ≤ RA → no impairment, loss=0
- Indicator INTEREST_RATE_INCREASE → category=EXTERNAL; PHYSICAL_DAMAGE → INTERNAL
- CGU classification: independent_CFs=True → INDIVIDUAL_ASSET, False → CASH_GENERATING_UNIT
- **GOODWILL reversal NEVER allowed** per IAS 36.124
- TANGIBLE_ASSET reversal allowed (subject to ceiling)
- Unknown asset_type → reversal_allowed=False (conservative default)

**Rules applied:**
- Rule 1: recoverable_amount=None when both VIU and FVLCD missing
- Rule 6: unknown indicator rejected; negative discount rate / negative CA / negative RA rejected (fail closed)

**Self-test:** 32/32

---

### #106 IAS 12 Income Taxes (Deferred Tax)
**File:** `utils/deferred_tax.py` (~536 LOC)
**Regulatory anchor:** IAS 12 (temporary differences, DTL/DTA, recoverability test, allocation buckets)
**Engine:** `DeferredTaxEngine`
**Methods:** `temporary_difference`, `classify_temporary_difference`, `deferred_tax`, `dta_recoverability`, `current_tax_expense`, `total_tax_expense`

**Byte-for-byte literals:**
- 3 `TEMPORARY_DIFFERENCE_TYPES` (IAS 12.5): TAXABLE, DEDUCTIBLE, NIL
- 5 `COMMON_TEMPORARY_DIFFERENCE_SOURCES`: DEPRECIATION_DIFFERENCE, PROVISION_TIMING, REVALUATION_GAIN, UNREALISED_GAIN_LOSS, LOSS_CARRYFORWARD
- 3 `DEFERRED_TAX_RECOGNITION_OUTCOMES`: RECOGNISE_FULLY, RECOGNISE_PARTIALLY, DO_NOT_RECOGNISE
- 2 `PROFIT_OR_LOSS_ALLOCATION_BUCKETS` (IAS 12.58): P_AND_L, OCI
- 5 `EXEMPTIONS_FROM_RECOGNITION` (IAS 12.15/24/39/40)

**Runtime verified:**
- TD = 1M CA - 800K tax_base = 200,000
- Classify TD>0 → TAXABLE, TD<0 → DEDUCTIBLE, TD=0 → NIL
- Deferred tax 200K × 30% = 60,000.00 (DEFERRED_TAX_LIABILITY)
- Deferred tax -200K × 30% = -60,000.00 (DEFERRED_TAX_ASSET)
- **DTA recoverability** -200K with future profit 500K → RECOGNISE_FULLY (200K recognised)
- -200K with future profit 100K → RECOGNISE_PARTIALLY (100K recognised)
- **-200K with future profit None → DO_NOT_RECOGNISE** per IAS 12.34 (conservative)
- -200K with future profit 0 → DO_NOT_RECOGNISE
- Current tax 1M @ 30% = 300,000.00
- Tax loss position (negative taxable profit) → current_tax = 0.00 with tax_loss_position=True

**Rules applied:**
- Rule 1: deferred_tax=None when CA, tax_base, or rate missing
- Rule 6: negative tax rate rejected (fail closed); DTA recognition without evidence rejected (conservative)

**Self-test:** 30/30

---

### #107 IFRS 15 Revenue Recognition
**File:** `utils/revenue_recognition.py` (~591 LOC)
**Regulatory anchor:** IFRS 15 (5-step model, contract criteria, performance obligations, control transfer)
**Engine:** `RevenueRecognitionEngine`
**Methods:** `identify_contract`, `identify_performance_obligations`, `determine_transaction_price`, `allocate_transaction_price`, `revenue_recognition_pattern`, `validate_contract_modification`

**Byte-for-byte literals:**
- 5 `IFRS_15_STEPS` (IFRS 15.IN7)
- 5 `CONTRACT_CRITERIA` (IFRS 15.9): PARTIES_APPROVED, RIGHTS_IDENTIFIABLE, PAYMENT_TERMS_IDENTIFIABLE, COMMERCIAL_SUBSTANCE, COLLECTION_PROBABLE
- 2 `RECOGNITION_PATTERNS`: POINT_IN_TIME, OVER_TIME
- 3 `OVER_TIME_CRITERIA` (IFRS 15.35)
- 5 `INDICATORS_OF_CONTROL_TRANSFER` (IFRS 15.38)
- 3 `VARIABLE_CONSIDERATION_TYPES`: DISCOUNT, REBATE, REFUND_OR_RETURN
- 3 `CONTRACT_MODIFICATION_TYPES` (IFRS 15.18-21): SEPARATE_CONTRACT, TERMINATION_AND_NEW, CUMULATIVE_CATCH_UP

**Runtime verified:**
- Contract recognised when ALL 5 criteria met
- **COLLECTION_PROBABLE=False blocks recognition** (fail closed)
- Transaction price = 1M fixed + 50K variable + 0 non-cash - 20K payable = 1,030,000.00
- Allocation TP=1000 with SSPs {A:600, B:400} → A gets 600.00, B gets 400.00 (proportional per IFRS 15.74)
- Recognition pattern OVER_TIME when ANY of 3 criteria met
- Default POINT_IN_TIME when no over-time criterion met
- Modification SEPARATE_CONTRACT requires distinct + standalone price (fail closed)

**Rules applied:**
- Rule 1: transaction_price=None when fixed missing; allocation=None when TP or SSP empty
- Rule 6: unknown modification rejected; collection NOT probable blocks recognition; non-positive total SSP rejected

**Self-test:** 28/28

---

### #108 IAS 33 Earnings Per Share
**File:** `utils/earnings_per_share.py` (~641 LOC)
**Regulatory anchor:** IAS 33 (basic + diluted EPS, weighted average shares, treasury stock method, anti-dilution test)
**Engine:** `EarningsPerShareEngine`
**Methods:** `weighted_avg_shares`, `basic_eps`, `diluted_eps`, `treasury_stock_method`, `if_converted_method`, `dilutive_classification`

**Byte-for-byte literals:**
- 3 `EPS_TYPES`: BASIC, DILUTED, CONTINUING_OPERATIONS
- 3 `SHARE_TRANSACTION_TYPES`: ISSUANCE, BUYBACK, BONUS_OR_SPLIT
- 4 `POTENTIAL_ORDINARY_SHARE_TYPES` (IAS 33.7): CONVERTIBLE_BONDS, CONVERTIBLE_PREFERRED_SHARES, SHARE_OPTIONS_WARRANTS, CONTINGENTLY_ISSUABLE_SHARES
- 2 `DILUTION_OUTCOMES` (IAS 33.41): DILUTIVE, ANTI_DILUTIVE
- 3 `EPS_PRESENTATION_REQUIREMENTS` (IAS 33.67)

**Runtime verified:**
- WANS 1M opening + no transactions over 365 days = 1,000,000
- Mid-period issuance: 1M × 365/365 + 100K × 183/365 ≈ 1.05M weighted
- BONUS_OR_SPLIT applied retrospectively (treated as if at start)
- Treasury stock method: 100K options × $10 strike = 1M proceeds; buyback at $20 market = 50K shares; net dilutive = 50K
- **ANTI_DILUTIVE potential ordinary shares MUST be excluded** per IAS 33.43

**Rules applied:**
- Rule 1: WANS=None when opening_shares missing; basic_eps=None when WANS=0
- Rule 6: negative shares rejected; ANTI_DILUTIVE inclusion rejected (fail closed)

**Self-test:** 32/32

---

## Audit gates added (3)

### G95 — asset_impairment_correct
- Verifies all #105 byte-for-byte literals (3 bases, 7 external + 5 internal indicators, 3 frequencies, 2 groupings, both reversal flags)
- Runtime: VIU 0% sum and 10% discount; recoverable max with basis tracking; impairment loss with post-impairment CA; indicator EXTERNAL/INTERNAL categorisation; CGU classification; **GOODWILL reversal NEVER allowed**; TANGIBLE allowed
- Rule 1: both missing recoverable inputs → None
- Rule 6: unknown indicator rejected; negative discount rate rejected
- **Tamper test:** GOODWILL_REVERSAL_PROHIBITED (True→False) caught

### G96 — deferred_tax_correct
- Verifies all #106 byte-for-byte literals (3 TD types, 5 sources, 3 outcomes, 2 buckets, 5 exemptions)
- Runtime: TD = CA - tax_base; classification by sign; DTL when TD>0 and DTA when TD<0; **DTA recoverability with conservative DO_NOT_RECOGNISE when no future profit evidence** per IAS 12.34; current tax with tax loss position
- Rule 1: missing inputs → None
- Rule 6: negative tax rate rejected
- **Tamper test:** TEMPORARY_DIFFERENCE_TYPES dropped NIL caught

### G97 — revenue_eps_correct (combined #107 + #108)
- **REVENUE:** 5 IFRS 15 steps + 5 contract criteria + 2 recognition patterns + 3 over-time criteria + 5 control transfer indicators + 3 variable consideration + 3 modification types byte-for-byte
- **EPS:** 3 EPS types + 3 share transaction types + 4 potential ordinary share types + 2 dilution outcomes + 3 presentation requirements byte-for-byte
- Runtime REVENUE: contract all-5-met; collection-fail blocks; transaction price computation; SSP-proportional allocation; OVER_TIME when any criterion met; modification rejection
- Runtime EPS: WANS basic case; missing opening → None
- **Tamper tests:** CONTRACT_CRITERIA dropped COLLECTION_PROBABLE caught; EPS_TYPES dropped DILUTED caught

---

## Comparison vs v5.67

| | v5.67 | v5.68 |
|--|-------|-------|
| Standards | 104 | **108** |
| Audit gates | 94/94 = 100% | **97/97 = 100%** |
| Test files | 46 | **47** |
| Test count | 1855 | **1977** (+122) |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Spec deviations (cumulative — still 9, no new in v5.68)

1. (v5.49) Heatmap React→Streamlit/plotly
2. (v5.51) React SPA + React Native scaffolding
3. (v5.52) Rule 7 / Cat D scaffolding pattern formalised
4. (v5.52) #48 LLM commentary deferred
5. (v5.55) CBK reports: 3 of 8 implemented, 5 deferred
6. (v5.56) FATCA Form 8966 XML and OECD CRS XML deferred to v7
7. (v5.57) ML-based sentiment classification deferred to v7
8. (v5.59) ML-based churn classifier deferred to v7
9. (v5.59) ML-based recommender deferred to v7

**No new spec deviations in v5.68.** All 4 standards Cat B with full deterministic implementation.

---

## Strategic narrative — Boundary semantics that banks routinely get wrong

This volume materialises four standards where the precise boundary semantics matter, and getting them wrong is the most common cause of restated accounts:

**IAS 36 (#105) Asset Impairment** binds:
- `recoverable_amount = max(VIU, FVLCD)` exactly per IAS 36.18 (HIGHER of, not arithmetic average — banks routinely average and underreport recoverable amount)
- The goodwill reversal prohibition per IAS 36.124 (NEVER reversed regardless of conditions). The engine returns `reversal_allowed=False` for GOODWILL with explicit rationale, because reversing goodwill impairment would create circular reasoning where the bank could re-recognise goodwill that was already extinguished.

**IAS 12 (#106) Deferred Tax** materialises the conservative DTA recoverability test per IAS 12.34:
- When future taxable profit is **not evidenced** (None), the engine returns `DO_NOT_RECOGNISE`
- When evidenced but ≤ 0, also `DO_NOT_RECOGNISE`
- Only when future profit ≥ utilisable does it return `RECOGNISE_FULLY`
- This is conservative — banks tend to default to RECOGNISE_FULLY when they should not, inflating DTAs that won't be recovered.

**IFRS 15 (#107) Revenue Recognition** binds the 5-step model with exact criterion semantics:
- ALL 5 contract criteria must be met for contract recognition
- **COLLECTION_PROBABLE=False blocks all revenue** — this is fail-closed because IFRS 15.9 requires collection probability before any revenue can be recognised
- Allocation uses standalone selling price ratio (not arbitrary, not historical, not management's preference)
- OVER_TIME requires ANY of 3 IFRS 15.35 criteria (not all — banks sometimes require all three and incorrectly default to POINT_IN_TIME)

**IAS 33 (#108) Earnings Per Share** implements the dilution test correctly:
- Only DILUTIVE potential ordinary shares are included in diluted EPS
- ANTI_DILUTIVE shares MUST be excluded per IAS 33.43
- The most common EPS misstatement is including anti-dilutive convertibles to inflate the share count denominator (which artificially reduces diluted EPS, making earnings look more diluted than they actually are — disclosure-driven manipulation)

**11 IFRS pillars now bound to byte-for-byte definitions:**
IFRS 9, IFRS 10, IAS 28, IFRS 11, IFRS 13, IFRS 15, IFRS 16, IAS 12, IAS 19, IAS 21, IAS 33, IAS 36 — every IFRS standard most regulated banks materially rely on for consolidated financial reporting.

**Cumulative tally:** 108 standards delivered, 97 audit gates, 1977 tests, 9 spec deviations, 6 Rule 7 applications.

---

**Next:** Volume Twenty-Three #109-#112 — likely additional IFRS standards (IAS 37 Provisions, IFRS 7 Financial Instruments Disclosures, IAS 1 Presentation, IAS 8 Accounting Policies and Errors) — or pivot to specialised banking topics (CECL, IRRBB enhancement, hedge accounting). Target 100/100 gates.

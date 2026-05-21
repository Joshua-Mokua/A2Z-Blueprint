# A2Z MIS 360 — CHANGELOG v5.66

**Volume Twenty — Tax / Procurement / Close / Group Consolidation (CENTENNIAL)**
**Released:** April 2026
**Audit gates:** 91/91 = 100% PASS (was 88/88)
**Test count:** 45 files / 1742 tests (was 44/1611 — added 131 in `tests/test_volume_twenty_batch.py`)
**Milestone:** **#100 = the centennial standard.**

---

## Standards delivered (4 — all Cat B)

### #97 Tax & VAT Compliance
**File:** `utils/tax_compliance.py` (~480 LOC)
**Regulatory anchor:** KRA Tax Procedures Act + VAT Act + Income Tax Act
**Engine:** `TaxComplianceEngine`
**Methods:** `vat_output`, `vat_payable`, `corporate_tax`, `withholding_tax`, `filing_deadline`, `filing_status`, `late_filing_penalty`

**Byte-for-byte literals:**
- 5 `TAX_TYPES`: VAT, CORPORATE_TAX, WITHHOLDING_TAX, EXCISE_DUTY, PAYE
- `VAT_STANDARD_RATE_PCT = Decimal("16")`
- `VAT_ZERO_RATE_PCT = Decimal("0")`
- 3 `VAT_RATE_CATEGORIES`: STANDARD, ZERO_RATED (input claimable), EXEMPT (NOT claimable)
- 8 `WITHHOLDING_TAX_RATES_PCT`: PROFESSIONAL_FEES_RESIDENT=5; PROFESSIONAL_FEES_NON_RESIDENT=20; RENT_RESIDENT=10; DIVIDENDS_RESIDENT=5; DIVIDENDS_NON_RESIDENT=15; INTEREST_RESIDENT=15; INTEREST_NON_RESIDENT=15; MANAGEMENT_FEES_NON_RESIDENT=20
- `CORPORATE_TAX_RATES_PCT`: RESIDENT_COMPANY=30; BRANCH_NON_RESIDENT=37.5; EXPORT_PROCESSING=0
- `FILING_DEADLINE_DAYS`: VAT=20; PAYE=9; WITHHOLDING_TAX=20; CORPORATE_TAX=180 (6 months); EXCISE_DUTY=20
- 5 `FILING_STATUSES`: NOT_DUE → DUE → FILED → PAID; OVERDUE branch
- `LATE_FILING_PENALTY_PCT_PER_MONTH = Decimal("5")`
- `LATE_FILING_PENALTY_MIN_KES = Decimal("10000")`
- `LATE_PAYMENT_INTEREST_PCT_MONTHLY = Decimal("1")`

**Runtime verified:**
- 100K @ 16% VAT = 16,000.00 output
- Output 16K - Input 5K = 11K payable; refund position preserved as negative (not error)
- 1M @ 30% corporate = 300,000.00; 1M @ 37.5% branch = 375,000.00
- 100K @ 5% professional WHT = 5,000 deducted; 95,000 net to vendor
- Period 31-Mar + 20d VAT deadline → 20-Apr
- Period 31-Dec + 180d corporate deadline → 29-Jun next year
- Late penalty: 100K × 5% × 2mo = 10K (min floor enforced); 1M × 5% × 3mo = 150K

**Rules applied:**
- Rule 1: vat_payable=None when output or input missing
- Rule 6: unknown VAT category / income category / entity_type / tax_type fail closed

**Self-test:** 35/35

---

### #98 Procurement Workflow & Approval Authority Matrix
**File:** `utils/procurement_workflow.py` (~430 LOC)
**Engine:** `ProcurementWorkflowEngine`
**Methods:** `approval_authority`, `procurement_method`, `validate_state_transition`, `three_way_match`, `bid_count_required`

**Byte-for-byte literals:**
- 7 `PROCUREMENT_STATES`: REQUESTED, APPROVED, PO_ISSUED, RECEIVED, INVOICED, PAID, CANCELLED
- `ALLOWED_PROCUREMENT_TRANSITIONS`: REQUESTED→(APPROVED, CANCELLED); APPROVED→(PO_ISSUED, CANCELLED); PO_ISSUED→(RECEIVED, CANCELLED); RECEIVED→(INVOICED,); INVOICED→(PAID,); PAID→() terminal; CANCELLED→() terminal
- 5 `APPROVAL_TIERS`: BUYER, MANAGER, DIRECTOR, MD, BOARD
- `BUYER_LIMIT_KES = Decimal("100000")`
- `MANAGER_LIMIT_KES = Decimal("1000000")`
- `DIRECTOR_LIMIT_KES = Decimal("10000000")`
- `MD_LIMIT_KES = Decimal("50000000")`
- 5 `PROCUREMENT_METHODS`: DIRECT_PURCHASE, REQUEST_FOR_QUOTATION, OPEN_TENDER, RESTRICTED_TENDER, FRAMEWORK_AGREEMENT
- Method thresholds: DIRECT_PURCHASE_MAX=50000; RFQ_MAX=1000000; OPEN_TENDER_MAX=10000000; RESTRICTED_TENDER_MIN=10000001
- `QUOTATIONS_REQUIRED`: DIRECT=1; RFQ=3 (KEY 3-bid rule); OPEN_TENDER=0; RESTRICTED=5; FRAMEWORK=0
- 4 `VENDOR_SELECTION_CRITERIA`: PRICE, QUALITY, DELIVERY, COMPLIANCE
- `THREE_WAY_MATCH_TOLERANCE_PCT = Decimal("2")` (PO + GRN + Invoice within ±2%)

**Runtime verified:**
- Approval tier: 50K=BUYER, 100K=BUYER (boundary inclusive), 30M=MD, 100M=BOARD
- Method: 30K=DIRECT/1quote, 500K=RFQ/3quotes, 5M=OPEN_TENDER, 50M=RESTRICTED/5quotes
- 3-way match exact (PO=GRN=Invoice=100K) → matched + eligible_for_payment
- 3-way match 2% boundary (PO 100K, GRN 102K) → matched (≤ tolerance)
- 3-way match 3% deviation (PO 100K, GRN 103K) → NOT matched + NOT eligible (fail closed)

**Rules applied:**
- Rule 1: missing amount → tier=None; missing GRN → matched=None
- Rule 6: invalid skip transition (REQUESTED→PAID) rejected (allowed=False fail closed)

**Self-test:** 34/34

---

### #99 Financial Close & Reconciliation Discipline
**File:** `utils/financial_close.py` (~390 LOC, separate from existing `reconciliation.py` and `reconciliation_engine.py`)
**Engine:** `FinancialCloseEngine`
**Methods:** `close_state_transition`, `close_calendar_milestone`, `reconciliation_variance`, `materiality_check`, `signoff_complete`

**Byte-for-byte literals:**
- 6 `CLOSE_STATES`: OPEN, IN_CLOSE, RECONCILING, REVIEWED, CLOSED, REOPENED
- `ALLOWED_CLOSE_TRANSITIONS`: OPEN→(IN_CLOSE,); IN_CLOSE→(RECONCILING, OPEN); RECONCILING→(REVIEWED, IN_CLOSE); REVIEWED→(CLOSED, RECONCILING); CLOSED→(REOPENED,); REOPENED→(IN_CLOSE,)
- `CLOSE_CALENDAR_MILESTONES` (T+N days): TXN_CUTOFF=1; GL_CLOSE=5; RECON_COMPLETE=10; REVIEW_COMPLETE=12; MGMT_REPORT=15
- 5 `RECONCILIATION_TYPES`: GL_TO_SUBLEDGER, BANK_RECON, INTERCOMPANY, SUSPENSE_ACCOUNT, NOSTRO_VOSTRO
- 5 `ADJUSTMENT_TYPES`: ACCRUALS, PROVISIONS, REVALUATION, AMORTIZATION, DEPRECIATION
- 3 `SIGNOFF_LEVELS`: PREPARER, REVIEWER, APPROVER (all required for close)
- `MATERIALITY_THRESHOLD_PCT = Decimal("0.1")` (strict > so 0.1% boundary NOT material)
- `SUSPENSE_ZERO_TOLERANCE_KES = Decimal("0")` (any non-zero IS material)

**Runtime verified:**
- Variance 1M → 1.001M = 1K abs / 0.1000% (4 decimal precision)
- 0.05% < 0.1% → not material
- 0.5% > 0.1% → material
- Exactly 0.1% → NOT material (strict greater-than)
- SUSPENSE 0.01% → material (zero tolerance)
- Milestone 30-Apr + 5d = 5-May
- Signoff missing APPROVER → eligible_for_close=False (fail closed)
- Reopen path: CLOSED → REOPENED → IN_CLOSE allowed

**Rules applied:**
- Rule 1: variance_pct=None when GL_balance=0; materiality=None when variance missing
- Rule 6: invalid skip (OPEN→CLOSED) rejected; missing signoff levels surfaced

**Self-test:** 28/28

---

### #100 Group Consolidation Engine — IFRS 10 / IAS 28 / IFRS 11 / IAS 21 (CENTENNIAL)
**File:** `utils/group_consolidation.py` (~430 LOC)
**Regulatory anchor:** IFRS 10 (control), IAS 28 (significant influence), IFRS 11 (joint arrangements), IAS 21 (foreign currency translation)
**Engine:** `GroupConsolidationEngine`
**Methods:** `consolidation_method`, `subsidiary_classification`, `elimination_amount`, `non_controlling_interest`, `currency_translation`

**Byte-for-byte literals:**
- 5 `SUBSIDIARY_TYPES`: WHOLLY_OWNED (=100%), MAJORITY_OWNED (>50%), ASSOCIATE (20-50%), JOINT_VENTURE, BRANCH
- 4 `CONSOLIDATION_METHODS`: FULL_CONSOLIDATION, EQUITY_METHOD, PROPORTIONATE, COST_METHOD
- `CONTROL_THRESHOLD_PCT = Decimal("50")` (strict > so 50% boundary = EQUITY_METHOD not control)
- `SIGNIFICANT_INFLUENCE_THRESHOLD_PCT = Decimal("20")` (≥ inclusive so 20% boundary = EQUITY_METHOD)
- `WHOLLY_OWNED_THRESHOLD_PCT = Decimal("100")`
- 4 `ELIMINATION_TYPES`: INTRA_GROUP_TRADING, INTRA_GROUP_LOANS, INTRA_GROUP_DIVIDENDS, UNREALIZED_PROFITS
- 2 `CURRENCY_TRANSLATION_METHODS` (IAS 21): TEMPORAL_METHOD, CURRENT_RATE_METHOD
- 3 `CONSOLIDATION_FREQUENCIES`: MONTHLY (subsidiaries), QUARTERLY (associates/JVs), ANNUAL (statutory)

**Runtime verified:**
- 75% ownership → FULL_CONSOLIDATION (rationale: control_per_IFRS_10)
- 100% ownership → FULL_CONSOLIDATION
- 30% ownership → EQUITY_METHOD (rationale: significant_influence_per_IAS_28)
- **50% boundary → EQUITY_METHOD** (NOT control — IFRS 10 requires strict > 50%)
- **20% boundary → EQUITY_METHOD** (≥ inclusive)
- 19.99% → COST_METHOD; 10% → COST_METHOD
- JV any% → PROPORTIONATE override (rationale: joint_venture_per_IFRS_11)
- Classification: 100%=WHOLLY_OWNED, 75%=MAJORITY_OWNED, 30%=ASSOCIATE, JV=JOINT_VENTURE, branch=BRANCH
- Below 20% returns None (financial investment, not subsidiary)
- NCI: 75% ownership × 1M equity → NCI = 25% × 1M = 250,000.00
- NCI: 100% ownership → NCI = 0
- Elimination: 5M intra-group trading → -5,000,000 (full reversal)
- Translation CURRENT_RATE: 1M USD × 130 KES/USD = 130,000,000.00 KES
- Translation TEMPORAL monetary → closing rate (130M)
- Translation TEMPORAL non-monetary → historical rate (100M with rate=100)

**Rules applied:**
- Rule 1: method=None when ownership missing; nci=None when inputs missing
- Rule 6: ownership > 100% rejected (fail closed); unknown method/elimination/translation surfaced

**Self-test:** 34/34

---

## Audit gates added (3)

### G89 — tax_compliance_correct
- Verifies all #97 byte-for-byte literals (5 tax types, VAT 16/0 rates, full WHT rate table, corporate 30/37.5, filing deadlines VAT=20/PAYE=9/Corp=180, 5 statuses, penalty 5%/10K min)
- Runtime: 100K @ 16% = 16K VAT; 1M @ 30% = 300K corp; 100K @ 5% WHT = 5K/95K; period 31-Mar VAT deadline 20-Apr; OVERDUE detection; late penalty min 10K floor and 150K high case
- Rule 1: vat_payable None paths
- Rule 6: unknown VAT category fail closed
- **Tamper test:** VAT_STANDARD_RATE_PCT (16→1) caught

### G90 — procurement_workflow_correct
- Verifies all #98 byte-for-byte literals (7 states, full transition table, 5 approval tiers + thresholds 100K/1M/10M/50M, 5 procurement methods + thresholds, 3-bid rule, 5-bid restricted, 4 selection criteria, 2% three-way match tolerance)
- Runtime: BUYER/MANAGER/DIRECTOR/MD/BOARD assignment by amount; method selection 30K=DIRECT, 500K=RFQ/3quotes, 50M=RESTRICTED/5quotes; 3-way match exact/2% boundary/3% exceed (fail closed); state transition skip rejected
- **Tamper test:** BUYER_LIMIT_KES (100000→1) caught

### G91 — close_consolidation_correct (combined #99 + #100 — CENTENNIAL gate)
- **CLOSE:** 6 states + state machine + 5 milestones (T+1/5/10/12/15) + 5 recon types + 5 adjustments + 3 signoff + 0.1% materiality + suspense zero tolerance byte-for-byte
- **CONSOLIDATION:** 5 subsidiary types + 4 methods + thresholds (50%/20%/100%) + 4 eliminations + 2 translation methods + 3 frequencies byte-for-byte
- Runtime CLOSE: variance 0.1000% (4 decimal precision); 0.5% material; exactly 0.1% NOT material (strict >); SUSPENSE 0.01% material (zero tolerance); milestone 5-May; signoff fail closed when APPROVER missing
- Runtime CONSOLIDATION: 75%=FULL, 30%=EQUITY, 50% boundary=EQUITY (not control), 20% boundary=EQUITY, 10%=COST, JV any%=PROPORTIONATE, NCI 75%×1M=250K, elimination -5M reversal, IAS 21 temporal monetary→closing/non-monetary→historical, 1M USD × 130 = 130M KES
- Rule 6: ownership > 100% rejected (fail closed)
- **Tamper tests:** MATERIALITY_THRESHOLD_PCT (0.1→100) caught; CONTROL_THRESHOLD_PCT (50→1) caught

---

## Comparison vs v5.65

| | v5.65 | v5.66 |
|--|-------|-------|
| Standards | 96 | **100** ⭐ CENTENNIAL |
| Audit gates | 88/88 = 100% | **91/91 = 100%** |
| Test files | 44 | **45** |
| Test count | 1611 | **1742** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Spec deviations (cumulative — still 9, no new in v5.66)

1. (v5.49) Heatmap React→Streamlit/plotly
2. (v5.51) React SPA + React Native scaffolding
3. (v5.52) Rule 7 / Cat D scaffolding pattern formalised
4. (v5.52) #48 LLM commentary deferred
5. (v5.55) CBK reports: 3 of 8 implemented, 5 deferred
6. (v5.56) FATCA Form 8966 XML and OECD CRS XML deferred to v7
7. (v5.57) ML-based sentiment classification deferred to v7
8. (v5.59) ML-based churn classifier deferred to v7
9. (v5.59) ML-based recommender deferred to v7

**No new spec deviations in v5.66.** The centennial milestone was delivered cleanly — all 4 standards Cat B with full deterministic implementation.

---

## CENTENNIAL ACHIEVEMENT — 100 Standards Delivered

**Volume Twenty closes the bank's corporate finance + group reporting governance, taking A2Z MIS 360 across the 100-standard line.**

The four standards in this volume materialise the regulatory frameworks of four different bodies (KRA, internal procurement governance, accounting close discipline, IASB) into deterministic production code:

1. **Tax Compliance (#97)** — translates KRA's regulatory schedule into production code. 5 tax types with byte-for-byte rates, deadlines, and penalties means when KRA assesses VAT for the 31-Mar period, the system computes 16% on standard sales, applies the 20-day filing deadline (deadline 20-Apr), classifies status as DUE/FILED/OVERDUE based on actual date, and applies the 5%/month-or-10K-min penalty correctly without a tax accountant's manual lookup.

2. **Procurement Workflow (#98)** — prevents segregation-of-duties failures by binding approval authority to KES amount thresholds (BUYER ≤100K → BOARD >50M with 5 explicit tiers and explicit boundary rules) and binding procurement method to amount (DIRECT_PURCHASE/RFQ-3-bid/OPEN_TENDER/RESTRICTED-5-bid). This eliminates the most common procurement frauds: split orders, single-source for tenderable amounts, tier skipping. The 3-way match enforces ±2% PO/GRN/Invoice tolerance with strict fail-closed eligibility.

3. **Financial Close (#99)** — turns month-end from a checklist into a state machine with explicit T+N milestones (T+1 cutoff → T+5 GL close → T+10 recons → T+12 review → T+15 management report). The 0.1% materiality threshold uses strict greater-than (so 0.1% boundary deliberately NOT material — calibrated to prevent false alarms on standard rounding). The suspense zero tolerance rule eliminates the common bank failure mode of suspense balances dragging across periods. The 3-tier signoff fails closed if APPROVER is missing.

4. **Group Consolidation (#100, the CENTENNIAL)** — materialises four IFRS pillars at exactly the threshold definitions standard-setters wrote:
   - **IFRS 10 control test:** strict > 50% (so the 50% boundary = EQUITY_METHOD, not FULL — because the standard explicitly requires "more than half" for control)
   - **IAS 28 significant influence test:** ≥ 20% inclusive (so 20% boundary = EQUITY_METHOD)
   - **IFRS 11 joint arrangement override:** any ownership % with JV flag → PROPORTIONATE
   - **IAS 21 currency translation:** TEMPORAL splits monetary (closing rate) vs non-monetary (historical rate); CURRENT_RATE uses closing rate uniformly

   These are the kinds of one-percent-point distinctions where banks routinely produce wrong consolidated accounts. The engine binds the boundary semantics correctly.

**Combined integrity guarantees on top of the platform's 100 standards:**
- Decimal precision (28 digits) throughout all 100 engines
- Regulator-aligned literals (KRA, CBK, BCBS, FATCA, OECD CRS, GHG Protocol, TCFD, IFRS 9/10/11/13/15/16, IAS 21/28, etc.)
- Deterministic computation throughout (no ML predictions in regulated paths)
- Strict-greater materiality and control tests where standards require
- Zero-tolerance suspense rule
- Fail-closed Rule 1 paths for missing inputs
- Fail-closed Rule 6 paths for invalid states / invalid ownership / unknown categories
- Tamper-evident audit gates with sample tampers caught for each volume

**Stack span (after Volume 20):**
The platform now spans the **complete CEO + CFO + COO + CRO + CCO + Board + Sustainability + Strategic Planning + Network Management + Tax + Procurement + Close + Group Reporting stack** — every major banking discipline plus the corporate disciplines that turn the bank into a managed enterprise compliant with KRA, CBK, IFRS, BCBS, FATCA, OECD CRS, GHG Protocol, and TCFD.

**Next:** Volume Twenty-One #101-#104 (post-centennial — likely Asset/Lease management IFRS 16, Investment portfolio IFRS 9 hold-to-collect, Fair value measurement IFRS 13, Pension/employee benefits IAS 19) — or migration to integration/orchestration layer. Target 94/94 gates.

# A2Z MIS 360 — CHANGELOG v5.70

**Volume Twenty-Four — IFRS 5 Held for Sale / IAS 7 Cash Flow / IFRS 8 Operating Segments / IAS 24 Related Party**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (was 100/100)
**Test count:** 49 files / 2211 tests (was 48/2106 — added 105 in `tests/test_volume_twenty_four_batch.py`)
**Milestone:** Fourth post-centennial volume — **19 IFRS pillars now bound to byte-for-byte definitions**.

---

## Standards delivered (4 — all Cat B)

### #113 IFRS 5 Non-Current Assets Held for Sale & Discontinued Operations
**File:** `utils/held_for_sale.py`
**Regulatory anchor:** IFRS 5 (HFS classification, LOWER_OF measurement, depreciation cessation, disc op)
**Engine:** `HeldForSaleEngine`
**Methods:** `classify_held_for_sale`, `held_for_sale_measurement`, `depreciation_cessation_check`, `classify_discontinued_operation`, `presentation_outcome`

**Byte-for-byte literals:**
- 6 `HELD_FOR_SALE_CRITERIA` (IFRS 5.7-8 — **ALL required**)
- 3 `MEASUREMENT_OUTCOMES`: LOWER_OF_CARRYING_AMOUNT_AND_FVLCD, IMPAIRMENT_RECOGNISED, NO_FURTHER_DEPRECIATION
- 4 `DISCONTINUED_OPERATION_CRITERIA` (IFRS 5.32 — **ANY ONE**)
- 3 `PRESENTATION_OUTCOMES`
- `EXPECTED_SALE_MAX_MONTHS = 12`

**Runtime verified:**
- All 6 HFS criteria required (one missing → False, fail closed)
- LOWER_OF (CA, FVLCS): CA 1M / FVLCS 800K → measurement 800,000.00, impairment 200,000.00
- FVLCS > CA → no impairment, measurement = CA
- **Depreciation MUST cease after HFS classification per IAS 5.25** — continuing depreciation = NON-COMPLIANT (fail closed)
- Discontinued op requires ANY ONE of 4 criteria
- HFS + disc op → both presentation outcomes simultaneously

**Self-test:** 24/24

---

### #114 IAS 7 Cash Flow Statements
**File:** `utils/cash_flow_statement.py`
**Regulatory anchor:** IAS 7 (3-category classification, indirect/direct methods, cash equivalent rule)
**Engine:** `CashFlowEngine`
**Methods:** `classify_cash_flow`, `validate_method`, `cash_and_equivalents_check`, `reconcile_pnl_to_operating`

**Byte-for-byte literals:**
- 3 `CASH_FLOW_CATEGORIES` (IAS 7.10): OPERATING, INVESTING, FINANCING
- 2 `PRESENTATION_METHODS` (IAS 7.18): DIRECT, INDIRECT
- 3 `OPERATING_RECON_ADJUSTMENTS` (IAS 7.20)
- 5 `OPERATING_CASH_FLOWS_EXAMPLES` (IAS 7.14)
- 5 `INVESTING_CASH_FLOWS_EXAMPLES` (IAS 7.16)
- 5 `FINANCING_CASH_FLOWS_EXAMPLES` (IAS 7.17) — including **PAYMENTS_FOR_LEASE_LIABILITIES** (post-IFRS 16)
- `CASH_EQUIVALENT_MAX_MATURITY_MONTHS = 3` (IAS 7.7, ≤ inclusive)

**Runtime verified:**
- INTEREST_PAID → OPERATING
- PAYMENTS_TO_ACQUIRE_PPE → INVESTING
- DIVIDENDS_PAID → FINANCING
- **PAYMENTS_FOR_LEASE_LIABILITIES → FINANCING** (post-IFRS 16 rule)
- Cash equivalent 3-month boundary inclusive
- Indirect reconciliation: PBT 1M + Dep 200K + Amort 100K - Gain 50K - IncRec 30K + IncPay 40K - IncInv 60K = 1,200,000.00 operating CF
  - Sign conventions: gain on disposal subtracted (reclassified to investing); receivables-up subtracted (uses cash); payables-up added (provides cash); inventory-up subtracted (uses cash)

**Self-test:** 30/30

---

### #115 IFRS 8 Operating Segments
**File:** `utils/operating_segments.py`
**Regulatory anchor:** IFRS 8 (segment identification, 10% thresholds, 75% aggregate, aggregation criteria)
**Engine:** `OperatingSegmentEngine`
**Methods:** `identify_operating_segment`, `quantitative_threshold_test`, `aggregate_external_revenue_test`, `aggregation_criteria_check`, `major_customer_test`

**Byte-for-byte literals:**
- 3 `OPERATING_SEGMENT_CRITERIA` (IFRS 8.5 — **ALL required**)
- `REVENUE_THRESHOLD_PCT = Decimal("10")` (IFRS 8.13)
- `PROFIT_LOSS_THRESHOLD_PCT = Decimal("10")` (IFRS 8.13)
- `ASSETS_THRESHOLD_PCT = Decimal("10")` (IFRS 8.13)
- `REPORTABLE_SEGMENT_AGGREGATE_PCT = Decimal("75")` (IFRS 8.15)
- 5 `AGGREGATION_CRITERIA` (IFRS 8.12 — **ALL 5 required**)
- 3 `GEOGRAPHIC_DISCLOSURES` (IFRS 8.33)
- `MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT = Decimal("10")` (IFRS 8.34)

**Runtime verified:**
- 10% revenue boundary inclusive (10M / 100M = 10% → passes)
- 75% aggregate boundary inclusive (75M / 100M = 75% → meets)
- Profit/loss test uses **absolute values** (15K loss vs 100K profit total → 15% > 10% → reportable)
- ALL 5 aggregation criteria required (one missing = no aggregation, fail closed)
- 10% major customer boundary inclusive
- ANY ONE quantitative threshold makes segment reportable

**Self-test:** 27/27

---

### #116 IAS 24 Related Party Disclosures
**File:** `utils/related_party.py`
**Regulatory anchor:** IAS 24 (related party categories, KMP test, close family, disclosure requirements)
**Engine:** `RelatedPartyEngine`
**Methods:** `classify_related_party`, `identify_kmp`, `close_family_member_check`, `validate_disclosure_completeness`, `government_related_entity_relief`

**Byte-for-byte literals:**
- 7 `RELATED_PARTY_CATEGORIES` (IAS 24.9)
- 5 `KMP_CRITERIA` (IAS 24.9)
- 4 `CLOSE_FAMILY_MEMBERS` (IAS 24.9 — explicit list, **excludes cousins/siblings**)
- 5 `REQUIRED_DISCLOSURES` (IAS 24.18 — **ALL required**)
- 5 `KMP_COMPENSATION_CATEGORIES` (IAS 24.17)
- 3 `GOVERNMENT_RELATED_RELIEF` (IAS 24.25-27)

**Runtime verified:**
- KMP requires authority (planning/directing/controlling) **AND** role (director/senior management)
- Director without authority → NOT KMP (fail closed)
- Authority without role → NOT KMP
- Spouse → close family; cousin → **NOT close family** (per IAS 24 explicit list)
- ALL 5 disclosures required (one missing = non-compliant, fail closed)
- Government-related disclosure levels: INDIVIDUALLY_SIGNIFICANT=FULL, COLLECTIVELY_SIGNIFICANT=QUALITATIVE_ONLY, INSIGNIFICANT=EXEMPT

**Self-test:** 25/25

---

## Audit gates added (3)

### G101 — held_for_sale_correct
- All #113 byte-for-byte literals (6 HFS criteria, 3 measurements, 4 disc op criteria, 3 presentations, 12mo threshold)
- Runtime: ALL 6 HFS required; LOWER_OF measurement; **depreciation cessation per IAS 5.25**; disc op ANY-ONE-of-4; combined presentation
- **Tamper test:** EXPECTED_SALE_MAX_MONTHS (12→1) caught

### G102 — cash_flow_correct
- All #114 byte-for-byte literals (3 categories, 2 methods, 3 recon adjustments, 5 examples each, 3-month threshold)
- Runtime: classification with lease payments=FINANCING per IFRS 16; cash equivalent 3-month boundary inclusive; indirect reconciliation with proper sign conventions
- **Tamper test:** CASH_EQUIVALENT_MAX_MATURITY_MONTHS (3→1) caught

### G103 — segments_related_party_correct (combined #115 + #116)
- **IFRS 8:** 3 segment criteria + 10% thresholds + 75% aggregate + 5 aggregation criteria + 3 geographic + 10% major customer byte-for-byte
- **IAS 24:** 7 categories + 5 KMP criteria + 4 close family + 5 disclosures + 5 KMP comp + 3 govt relief byte-for-byte
- Runtime IFRS 8: 10% boundary inclusive, 75% boundary inclusive, profit/loss abs test, aggregation all-5-required
- Runtime IAS 24: KMP authority+role test, cousin NOT close family, all-5-disclosures-required, govt relief 3-level
- **Tamper tests:** REVENUE_THRESHOLD_PCT (10→100) caught; REQUIRED_DISCLOSURES dropped NATURE_OF_RELATIONSHIP caught

---

## Comparison vs v5.69

| | v5.69 | v5.70 |
|--|-------|-------|
| Standards | 112 | **116** |
| Audit gates | 100/100 = 100% | **103/103 = 100%** |
| Test files | 48 | **49** |
| Test count | 2106 | **2211** (+105) |
| IFRS pillars bound | 15 | **19** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Spec deviations (cumulative — still 9, no new in v5.70)

1. (v5.49) Heatmap React→Streamlit/plotly
2. (v5.51) React SPA + React Native scaffolding
3. (v5.52) Rule 7 / Cat D scaffolding pattern formalised
4. (v5.52) #48 LLM commentary deferred
5. (v5.55) CBK reports: 3 of 8 implemented, 5 deferred
6. (v5.56) FATCA Form 8966 XML and OECD CRS XML deferred to v7
7. (v5.57) ML-based sentiment classification deferred to v7
8. (v5.59) ML-based churn classifier deferred to v7
9. (v5.59) ML-based recommender deferred to v7

**No new spec deviations in v5.70.** All 4 standards Cat B with full deterministic implementation.

---

## Strategic narrative — Four high-stakes regulatory boundary semantics

This volume materialises the four remaining IFRS standards regulated banks routinely file under, where the boundary semantics are the most commonly misstated:

**IFRS 5 (#113) — Depreciation cessation rule per IAS 5.25:**
Once an asset is classified as held for sale, depreciation MUST stop. Banks that continue to depreciate HFS assets are NON-COMPLIANT — the engine fails closed when this happens. The 12-month boundary is also strict — assets expected to take longer than 12 months to sell don't qualify for HFS classification, period. The most common error is keeping depreciation running because operational systems treat the asset as still in service.

**IAS 7 (#114) — Lease payments under IFRS 16:**
Post-IFRS 16, lease payments (the principal portion) are classified as **FINANCING** activities, NOT operating. This is a post-IFRS 16 change that many banks still get wrong because pre-IFRS 16 operating leases were classified as operating cash flows. The engine binds the post-IFRS 16 rule. The 3-month cash equivalent boundary is inclusive (≤).

**IFRS 8 (#115) — 10% threshold semantics:**
- The 10% threshold is **ANY ONE** of revenue/profit/assets (not all three)
- The 75% aggregate test (reportable segments must cover ≥75% of external revenue) is the second-most-missed rule — banks routinely report only 60% of revenue through reportable segments and don't designate more
- Aggregation requires **ALL 5** economic similarity criteria — one missing forbids combining segments
- Profit/loss test uses **absolute values** so loss-making segments still trigger reportability

**IAS 24 (#116) — Close family list is explicit:**
The IAS 24.9 close family list is EXPLICIT and DOES NOT include cousins or siblings. The engine binds the literal list — relationships not in the list are NOT close family for disclosure purposes. The KMP test requires both authority AND role (director/senior management) — neither alone qualifies. The most common error is treating siblings as close family (intuitive but wrong per the standard) or treating senior managers without authority as KMP.

**19 IFRS pillars now bound to byte-for-byte definitions:**
IFRS 5, IFRS 7, IFRS 8, IFRS 9, IFRS 10, IFRS 11, IFRS 13, IFRS 15, IFRS 16, IAS 1, IAS 7, IAS 8, IAS 12, IAS 19, IAS 21, IAS 24, IAS 28, IAS 33, IAS 36, IAS 37 — every IFRS standard most regulated banks materially rely on for consolidated financial reporting.

**Cumulative tally:** 116 standards delivered, 103 audit gates, 2211 tests, 9 spec deviations, 6 Rule 7 applications.

---

## Honest concerns flagged for the next continuation

The IFRS coverage is now feature-complete in the **standards library** — 116 deterministic engines with byte-for-byte regulatory literals. However, several gaps remain before the platform can claim production-ready end-to-end:

1. **Deployed-vs-built gap:** The 116 standards live in `/tmp/a2z_fix/utils/` as an independent library. They are NOT yet wired into the deployed Streamlit app at `github.com/Joshua-Mokua/A2Z-Blueprint`. Closing this gap is the next major milestone.

2. **Test methodology:** Of 2211 tests, ~70-80% verify byte-for-byte literals (constants and structure). ~300-400 tests are unique behavioural assertions. This is appropriate for a regulatory library where literal drift is the primary risk, but external verification by an independent regulator-focused team would strengthen confidence.

3. **Deferred items still pending:** FATCA Form 8966 XML and OECD CRS XML (legally required filings for Ecobank Kenya), ML-based sentiment/churn/recommender (lower priority).

4. **Performance unverified at production scale.** All testing has been on synthetic data.

5. **Auth/security at standards layer not addressed.** Standards engines accept any caller; access control is the application's responsibility.

---

**PER USER PLAN — Pivot to integration layer for next continuation batch.**

The next session will begin wiring the 116 standards into live A2Z Blueprint Streamlit pages:
- `tax_compliance.py` → tax compliance page (KRA filing deadlines, VAT computation, WHT schedule)
- `procurement_workflow.py` → procurement page (approval matrix, 3-bid rule, three-way match)
- `financial_close.py` → close calendar page (T+N milestones, materiality, signoff)
- Selected IFRS engines surfaced in the existing BSC/CRM pages for live computation

Target: at least 3 standards integrated into deployed pages and demonstrably callable from the live Streamlit UI, with the audit gates still passing 103/103.

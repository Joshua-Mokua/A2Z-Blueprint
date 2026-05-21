# A2Z MIS 360 — CHANGELOG v5.65

**Volume Nineteen — Strategic Planning & Network Management**
**Released:** April 2026
**Audit gates:** 88/88 = 100% PASS (was 85/85)
**Test count:** 44 files / 1611 tests (was 43/1491 — added 120 in `tests/test_volume_nineteen_batch.py`)

---

## Standards delivered (4 — all Cat B)

### #93 Strategic Planning / Budget vs Actual / Forecasting
**File:** `utils/strategic_planning.py` (~440 LOC)
**Engine:** `StrategicPlanningEngine`
**Methods:** `variance`, `variance_tier`, `forecast` (3 methods), `validate_budget_state_transition`, `reforecast_trigger`

**Byte-for-byte literals:**
- 5 `BUDGET_LINE_CATEGORIES`: REVENUE, OPEX, NPAT, CAPEX, BALANCE_SHEET_GROWTH
- 3 `VARIANCE_DIRECTIONS`: FAVORABLE, UNFAVORABLE, NEUTRAL
- 3 `VARIANCE_TIERS`: GREEN, AMBER, RED
- `GREEN_VARIANCE_THRESHOLD_PCT = Decimal("5")`
- `AMBER_VARIANCE_THRESHOLD_PCT = Decimal("10")`
- 3 `FORECAST_METHODS`: STRAIGHT_LINE, RUN_RATE, SEASONALLY_ADJUSTED
- 5 `BUDGET_CYCLE_STATES`: DRAFT, REVIEW, BOARD_APPROVED, IN_EXECUTION, CLOSED
- `ALLOWED_BUDGET_TRANSITIONS`: DRAFT→(REVIEW); REVIEW→(BOARD_APPROVED, DRAFT); BOARD_APPROVED→(IN_EXECUTION); IN_EXECUTION→(CLOSED); CLOSED→() terminal
- `INCOME_LIKE_CATEGORIES = (REVENUE, NPAT, BALANCE_SHEET_GROWTH)`
- `EXPENSE_LIKE_CATEGORIES = (OPEX, CAPEX)`
- `QUARTERLY_REFORECAST_MONTHS = 3`
- `DEVIATION_REFORECAST_PCT = Decimal("10")`

**Runtime verified:**
- REVENUE 100→110 = +10% FAVORABLE; OPEX 100→90 = under-spend FAVORABLE
- Tier classification: 3%=GREEN, 5%=AMBER (boundary), 10%=AMBER (boundary), 15%=RED
- STRAIGHT_LINE: 50M YTD over 6mo → 100M.00 forecast
- RUN_RATE: 30M YTD + 5M/mo × 6 remaining → 60M.00
- SEASONALLY_ADJUSTED: 50M YTD with even seasonal indices → 100M.00

**Rules applied:**
- Rule 1: variance_pct=None when budget=0 (denominator zero)
- Rule 6: invalid budget state transitions REJECTED (DRAFT→BOARD_APPROVED skip = fail closed)

**Self-test:** 35/35

---

### #94 Branch Performance Management & Peer Benchmarking
**File:** `utils/branch_performance.py` (~340 LOC)
**Engine:** `BranchPerformanceEngine`
**Methods:** `branch_pnl`, `cost_income_ratio`, `return_on_avg_assets`, `quartile_rank`, `peer_benchmark_metrics`, `lifecycle_stage`

**Byte-for-byte literals:**
- 6 `BRANCH_PNL_LINES`: NII, NON_INTEREST_INCOME, OPEX_DIRECT, OPEX_ALLOCATED, IMPAIRMENT, NPBT
- 4 `PERFORMANCE_TIERS`: TIER_1 (top 25%), TIER_2 (50-75%), TIER_3 (25-50%), TIER_4 (bottom 25%)
- `TIER_1_THRESHOLD_PCT = Decimal("75")`, `TIER_2_THRESHOLD_PCT = Decimal("50")`, `TIER_3_THRESHOLD_PCT = Decimal("25")`
- 3 `BRANCH_LIFECYCLE_STAGES`: NEW (<2yr), GROWTH (2-5yr), MATURE (5+yr)
- `LIFECYCLE_BANDS_YEARS`: NEW=(0, 2); GROWTH=(2, 5); MATURE=(5, 999)
- 3 `PEER_GROUP_LOCATIONS`: TIER_1_CITIES, TIER_2_CITIES, RURAL
- 3 `PEER_GROUP_SIZES`: LARGE, MEDIUM, SMALL
- 3 `BENCHMARK_PERCENTILES`: PERCENTILE_25, MEDIAN, PERCENTILE_75

**P&L formula:** NPBT = NII + Non-Interest Income − OpEx Direct − OpEx Allocated − Impairment

**Runtime verified:**
- NPBT(100, 20, 40, 20, 10) = 50; total_income=120, total_opex=60
- C/I ratio: 60/120 × 100 = 50%
- ROAA: 50/1000 × 100 = 5%
- Quartile rank: branch=100 vs peers [10..95] → TIER_1
- Quartile rank: branch=5 vs peers [10..95] → TIER_4
- Lifecycle classification: 0=NEW, 2=GROWTH, 5=MATURE

**Rules applied:**
- Rule 1: cost_income=None when total_income=0; ROAA=None when avg_assets=0; quartile=None when peer_values empty; npbt=None when any P&L input missing
- Rule 6: missing_inputs list surfaced when P&L incomplete

**Self-test:** 26/26

---

### #95 Customer Lifetime Value & Segment Profitability
**File:** `utils/customer_value_segments.py` (~370 LOC, separate from existing #70 `customer_lifetime_value.py` which covers a different CLV facet)
**Engine:** `CustomerValueEngine`
**Methods:** `clv` (NPV-based), `segment_classification`, `tenure_band`, `activity_status`, `segment_profitability_aggregate`

**Byte-for-byte literals:**
- 6 `CUSTOMER_SEGMENTS`: MASS, AFFLUENT, HNW, SME, CORPORATE, GOVERNMENT
- 4 `SEGMENT_TIERS`: PLATINUM, GOLD, SILVER, BRONZE
- `SEGMENT_TIER_BANDS_KES`:
  - PLATINUM = (1000000, 999999999999)
  - GOLD = (250000, 999999)
  - SILVER = (50000, 249999)
  - BRONZE = (0, 49999)
- 4 `TENURE_BANDS`: NEW (<1yr), DEVELOPING (1-3yr), ESTABLISHED (3-7yr), LOYAL (7+yr)
- `TENURE_BAND_YEARS`: NEW=(0, 1); DEVELOPING=(1, 3); ESTABLISHED=(3, 7); LOYAL=(7, 999)
- 3 `ACTIVITY_STATUSES`: ACTIVE, DORMANT, ATTRITED
- `DORMANT_THRESHOLD_DAYS = 90`
- `ATTRITED_THRESHOLD_DAYS = 180`
- `DEFAULT_DISCOUNT_RATE_PCT = Decimal("15")` (cost of capital)

**CLV formula:**
```
CLV = Σ (annual_contribution × retention_rate^t) / (1 + r)^t for t = 0..tenure-1
```
(textbook NPV with decreasing survival probability)

**Runtime verified:**
- 1yr 100K @ 100% retention 0% discount → CLV = 100,000.00
- 3yr 100K @ 80% retention 10% discount → CLV ≈ 225,620 (in [220K, 230K] band)
- Default discount used when not specified: 15%
- Segment: 1.5M=PLATINUM; 1M boundary=PLATINUM; 500K=GOLD; 100K=SILVER; 10K=BRONZE
- Activity: 30d=ACTIVE; 90d=DORMANT (boundary); 180d=ATTRITED (boundary)

**Rules applied:**
- Rule 1: clv=None when annual_contribution≤0 or tenure≤0 or retention≤0
- Rule 6: unknown segment surfaced; unknown activity status returns None

**Self-test:** 32/32

---

### #96 Third-Party / Vendor Risk Management
**File:** `utils/vendor_risk.py` (~430 LOC)
**Regulatory anchor:** CBK Risk Management Guideline on Outsourcing (2014)
**Engine:** `VendorRiskEngine`
**Methods:** `due_diligence_completeness`, `review_due`, `sla_breach_severity`, `vendor_concentration_check`

**Byte-for-byte literals:**
- 5 `VENDOR_CATEGORIES`: CRITICAL_TECH, NON_CRITICAL_TECH, FACILITIES, PROFESSIONAL_SERVICES, OUTSOURCED_OPS
- 4 `VENDOR_TIERS`: TIER_1_CRITICAL, TIER_2_HIGH, TIER_3_MEDIUM, TIER_4_LOW
- 5 `DUE_DILIGENCE_CHECKS`: FINANCIAL_HEALTH, INFOSEC_CERT, BUSINESS_CONTINUITY, REGULATORY_COMPLIANCE, GEOGRAPHIC_RISK
- `REVIEW_CADENCE_DAYS`: TIER_1_CRITICAL=365 (annual); TIER_2_HIGH=730 (biennial); TIER_3_MEDIUM=1095 (triennial); TIER_4_LOW=1825 (5-yearly/on-renewal)
- 4 `SLA_BREACH_SEVERITIES`: CRITICAL, HIGH, MEDIUM, LOW
- `SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS`: CRITICAL=4; HIGH=2; MEDIUM=1; LOW=0
- `VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT = Decimal("25")` (strict > so exactly 25% does NOT alert)
- `CONTRACT_RENEWAL_NOTICE_DAYS = 180` (6-month notice for TIER_1/TIER_2)
- `CRITICAL_TIER_REQUIRED_CHECKS` = all 5 DD checks (TIER_1/TIER_2 onboarding)
- `LOWER_TIER_REQUIRED_CHECKS` = (FINANCIAL_HEALTH, REGULATORY_COMPLIANCE) for TIER_3/TIER_4

**Runtime verified:**
- TIER_1 with all 5 DD checks → eligible_for_onboarding=True
- TIER_1 missing GEOGRAPHIC_RISK → eligible=False (fail closed)
- TIER_3 with FINANCIAL_HEALTH+REGULATORY_COMPLIANCE → eligible
- Last review 30d ago (TIER_1, 365d cadence) → 335d remaining ON_TRACK
- Last review 400d ago → -36d OVERDUE (is_overdue=True)
- SLA: 6hr=CRITICAL; 4hr=CRITICAL (boundary); 3hr=HIGH; 1.5hr=MEDIUM; 0.5hr=LOW
- Concentration: 800K of 1M total = 80% > 25% → alert=True
- Concentration: 4 vendors at exactly 25% each → no alert (uses strict > not ≥)

**Rules applied:**
- Rule 1: review_due_in_days=None when last_review_date missing; concentration_pct=None when zero spend
- Rule 6: missing critical DD checks block onboarding (not silently allowed); unknown tier/category surfaced

**Self-test:** 27/27

---

## Audit gates added (3)

### G86 — strategic_planning_correct
- Verifies all #93 byte-for-byte literals (5 categories, 3 directions, 3 tiers, thresholds 5/10, 3 forecast methods, 5 cycle states, state machine transitions, reforecast constants 3mo/10%, INCOME_LIKE/EXPENSE_LIKE category split)
- Runtime: REVENUE 100→110 FAVORABLE; OPEX 100→90 FAVORABLE; tier 3%=GREEN, 5%=AMBER, 10%=AMBER, 15%=RED; STRAIGHT_LINE 100M; RUN_RATE 60M; SEASONAL 100M
- Rule 1: zero budget → variance_pct=None
- Rule 6: invalid transition (DRAFT→BOARD_APPROVED) rejected
- Reforecast triggers: QUARTERLY_CADENCE @ 3mo, DEVIATION_THRESHOLD @ 15%
- **Tamper test:** AMBER_VARIANCE_THRESHOLD_PCT (10→100) caught

### G87 — branch_performance_correct
- Verifies all #94 byte-for-byte literals (6 P&L lines, 4 perf tiers, thresholds 75/50/25, 3 lifecycle stages with bands, 3 peer locations, 3 sizes, 3 percentiles)
- Runtime: NPBT 100+20-40-20-10=50; total_income=120; total_opex=60; C/I ratio=50%; ROAA=5%; quartile top→TIER_1, bottom→TIER_4
- Rule 1: zero income → C/I=None; zero assets → ROAA=None; empty peer group → tier=None; missing P&L input → npbt=None
- **Tamper test:** TIER_1_THRESHOLD_PCT (75→1) caught

### G88 — customer_vendor_correct (combined #95 + #96)
- **CUSTOMER:** 6 segments + 4 tiers + bands + 4 tenure bands + 3 activity statuses + 90/180-day thresholds + 15% discount byte-for-byte
- **VENDOR:** 5 categories + 4 tiers + 5 DD checks + cadence (365/730/1095/1825) + 4 severities + downtime thresholds + 25% concentration byte-for-byte
- Runtime CLV: 1yr 100K @ 100% retention 0% discount → 100,000.00
- Runtime segment: 1.5M=PLATINUM, 500K=GOLD, 100K=SILVER, 10K=BRONZE; 1M boundary=PLATINUM
- Runtime activity: 30d=ACTIVE, 90d=DORMANT, 180d=ATTRITED
- Runtime DD: TIER_1 with all 5 → eligible; missing 1 → ineligible (fail closed)
- Runtime review: overdue detection (-36d for 400d-old TIER_1)
- Runtime SLA: 4hr boundary=CRITICAL; 3hr=HIGH; 1.5hr=MEDIUM; 0.5hr=LOW
- Runtime concentration: 80%>25%→alert; exactly 25%×4→no alert (strict >)
- Rule 1: missing last_review → review_due_in_days=None
- **Tamper tests:** VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT (25→100) caught; REVIEW_CADENCE_DAYS["TIER_1_CRITICAL"] (365→1) caught

---

## Comparison vs v5.64

| | v5.64 | v5.65 |
|--|-------|-------|
| Standards | 92 | **96** |
| Audit gates | 85/85 = 100% | **88/88 = 100%** |
| Test files | 43 | **44** |
| Test count | 1491 | **1611** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Spec deviations (cumulative — still 9, no new in v5.65)

1. (v5.49) Heatmap React→Streamlit/plotly
2. (v5.51) React SPA + React Native scaffolding
3. (v5.52) Rule 7 / Cat D scaffolding pattern formalised
4. (v5.52) #48 LLM commentary deferred
5. (v5.55) CBK reports: 3 of 8 implemented, 5 deferred
6. (v5.56) FATCA Form 8966 XML and OECD CRS XML deferred to v7
7. (v5.57) ML-based sentiment classification deferred to v7
8. (v5.59) ML-based churn classifier deferred to v7
9. (v5.59) ML-based recommender deferred to v7

**No new spec deviations in v5.65** — all 4 standards Cat B with full deterministic implementation.

---

## What this delivers strategically

**Volume Nineteen caps the four-tier governance stack:**
Strategic Planning (Vol 19) drives operational performance management (Vol 18) which is consolidated through reporting automation (Vol 17) which is verified by audit (Vol 16) — all of which are now operating on a foundation of three lines of defence (Vols 9-10), Treasury/Capital (Vols 14-15), and operational disciplines (Vols 11-13).

**The four lenses for CEO + Board + CFO:**

1. **Strategic Planning (#93)** — turns budgeting from a once-a-year exercise into a continuous discipline. Variance tiering (5%/10%) flags drift early; three forecast methods (straight-line, run-rate, seasonal) provide independent triangulation against the budget; the 5-state cycle machine enforces governance flow; quarterly + ±10% reforecast triggers eliminate stale assumptions.

2. **Branch Performance Management (#94)** — turns the network from a cost line into a portfolio of comparable economic units. Every branch ranks by quartile (TIER_1 top 25% vs TIER_4 bottom 25%) against location-and-size-matched peers, with C/I ratio + ROAA + lifecycle stage adjustments preventing apples-to-oranges comparisons of NEW vs MATURE branches.

3. **Customer Lifetime Value (#95)** — moves customer profitability from balance-sheet snapshot to NPV horizon. 6 segments × 4 value tiers × 4 tenure bands × 3 activity statuses creates a 288-cell decision matrix; the 15% cost-of-capital discount and explicit retention-rate compounding ensure CLV reflects true future value rather than historical revenue.

4. **Third-Party Risk (#96)** — materialises CBK's 2014 Outsourcing Guideline as production controls. 4 vendor tiers gated by 5 DD checks for critical vendors (vs 2 for non-critical); per-tier review cadences (365/730/1095/1825 days); 4-tier SLA breach severity (4hr/2hr/1hr/0hr); 25% concentration threshold that fail-closes when any single vendor dominates a category.

**Combined integrity guarantees:**
- Decimal precision (28 digits) throughout all four engines
- NPV computation with explicit retention-rate compounding
- Deterministic forecast methods (no ML/predictions)
- Strict greater-than concentration test (exactly 25% does NOT alert)
- Fail-closed DD requirements for critical vendors
- Fail-closed Rule 1 paths for zero-budget/zero-income/zero-tenure/missing-review-date
- Explicit Rule 6 surfacing for unknown categories/tiers/states

When the bank reports Q3 budget variance of 7.3% (AMBER), Branch Mombasa Road quartile rank TIER_1, customer Acme Corp CLV of 1.85M KES (PLATINUM tier), and vendor TechSwitch concentration alert at 47% of CRITICAL_TECH spend — those numbers, those classifications, those alerts are **independently verifiable, drift-detected, audit-trail-enforced, and tamper-evident**.

**Next:** Volume Twenty #97-#100 (centennial milestone — likely Tax/VAT compliance, Procurement workflow, Financial close/reconciliation, Group consolidation).

# A2Z MIS 360 — CHANGELOG v5.59

**Volume Thirteen — Customer Intelligence**
**Released:** April 2026
**Audit gates:** 70/70 = 100% PASS (was 67/67)
**Test count:** 38 files / 1115 tests (was 37/1050 — added 65 in `tests/test_volume_thirteen_batch.py`)

---

## Standards delivered (4)

### #69 Customer Segmentation (Cat B)
**Module:** `utils/customer_segmentation.py` (~360 LOC)
**Engine:** `CustomerSegmentationEngine`

4 entries: `rfm_scores` (deterministic quintile-based), `rfm_segment` (11-segment), `value_tier_assignment`, `lifecycle_stage`.

**Spec literals byte-for-byte:**
- 11 RFM_SEGMENTS: CHAMPIONS, LOYAL, POTENTIAL_LOYALIST, NEW_CUSTOMERS, PROMISING, NEED_ATTENTION, ABOUT_TO_SLEEP, AT_RISK, CANNOT_LOSE_THEM, HIBERNATING, LOST
- 4 VALUE_TIERS: HNI / MASS_AFFLUENT / MASS / SMALL with thresholds KES 50M / 5M / 100K
- 4 LIFECYCLE_STAGES: NEW (<90d) / GROWING (<365d) / MATURE / DORMANT (≥180d since last txn — overrides others)

**Critical RFM segment ordering**: (1,1,1) → LOST (not HIBERNATING). The LOST check (r=1, f≤2, m≤2) precedes HIBERNATING in the segment classification logic.

**Honesty rules:**
- **Rule 1:** customers with no transactions in window → unscored (NEVER imputed)
- **Rule 6:** None balance → `unassigned_count` surfaced (NEVER silently bucketed); missing onboarded_date → reason surfaced

**Self-test:** 16/16 PASS

---

### #70 Customer Lifetime Value (Cat B)
**Module:** `utils/customer_lifetime_value.py` (~340 LOC)
**Engine:** `CustomerLifetimeValueEngine`

4 entries: `product_revenue`, `clv_npv` (5-year NPV with `Decimal` prec=28), `profitability_segment`, `clv_aggregate`.

**PRODUCT_YIELDS_PCT byte-for-byte (8 products):**

| Product | NIM/Fee % |
|---|---|
| SAVINGS | 0.5 |
| CURRENT | 3.0 |
| TERM_DEPOSIT | 1.0 |
| PERSONAL_LOAN | 12.0 |
| MORTGAGE | 4.5 |
| CREDIT_CARD | 18.0 |
| TRADE_FINANCE | 6.0 |
| INVESTMENT | 1.0 |

**NPV defaults byte-for-byte:**
- HORIZON = 5 years
- DISCOUNT_RATE = 12.0% (CBR-aligned)
- MARGIN = 60.0% of revenue
- SERVICING = KES 2,400/yr

**Profitability segments:** HIGH_VALUE ≥ KES 500K, MEDIUM ≥ 50K, LOW ≥ 0, UNPROFITABLE < 0.

**NPV formula:** `sum_t [contribution / (1+r)^t]` for t=1..N with `getcontext().prec=28`.

**Honesty rules:**
- **Rule 1:** clv=None when no scoreable holdings (returns reason="no_scoreable_holdings")
- **Rule 6:** holdings with None balance excluded with count surfaced; unknown product types excluded; **NEVER imputes average values**

**Self-test:** 15/15 PASS

---

### #71 Churn Prediction (Cat D + **5th Rule 7 application**)
**Module:** `utils/churn_prediction.py` (~370 LOC)
**Engine:** `ChurnPredictionEngine`

5 entries: `_rule_based_score` (private deterministic), `churn_score_rule_based` (public deterministic API), `churn_score_predict(signals, ml_churn_fn=None)` (Rule 7 scaffolding), `churn_segment`, `retention_intervention_priority`.

**CHURN_FEATURE_WEIGHTS byte-for-byte (sum=100):**

| Feature | Weight |
|---|---|
| no_txn_60_days | 30 |
| balance_dropping_50pct | 20 |
| complaint_unresolved | 15 |
| competitor_check | 10 |
| single_product_only | 10 |
| csat_low | 10 |
| tenure_under_1y | 5 |

**Trigger thresholds byte-for-byte:**
- NO_TXN_DAYS = 60
- BALANCE_DROP_PCT = 50%
- COMPLAINT_OPEN_DAYS = 14
- CSAT_LOW ≤ 2
- TENURE_NEW < 365d

**Segment thresholds:** HIGH_RISK ≥ 70, MEDIUM_RISK ≥ 40, LOW_RISK ≥ 20, STABLE < 20.

### **5th Rule 7 application** — applied to **survival/churn classification**

`churn_score_predict(signals, ml_churn_fn=None)`:
- **No model loaded:** `basis="rule_based"`, `ml_score=None`, `reason="no_ml_churn_model_loaded"`, `rule_based_score` surfaced, `spec_deviation` surfaced
- **ML succeeds:** `basis="ml"`, `ml_score=<value>`, **rule_based_score ALSO surfaced** for transparency
- **ML fails:** `basis="rule_based"`, `reason=f"ml_churn_error:{type(e).__name__}"`, falls back

**SPEC_DEVIATION_NOTE byte-for-byte:**
> "ML-based churn classifier (gradient boosting / neural net) is downstream work; v6 ships rule-based weighted-sum churn scoring"

`retention_intervention_priority` filters to HIGH/MEDIUM and sorts by score desc. Customers with >3 missing signals → `low_confidence_count` (NEVER assumed risk-free).

**Self-test:** 15/15 PASS

---

### #72 Cross-Sell / Next-Best-Action (Cat D + **6th Rule 7 application**)
**Module:** `utils/cross_sell_nba.py` (~470 LOC)
**Engine:** `CrossSellNextBestActionEngine`

6 entries: `product_eligibility` (default-deny), `_rule_based_nba`, `next_best_action_rule_based`, `next_best_action_predict(customer, ml_recommender_fn=None)` (Rule 7), `cross_sell_priority_list`.

**RECOMMENDABLE_PRODUCTS byte-for-byte (8 products):** SAVINGS, CURRENT, TERM_DEPOSIT, PERSONAL_LOAN, MORTGAGE, CREDIT_CARD, INVESTMENT, INSURANCE

**NBA_RULE_WEIGHTS byte-for-byte (7 rules):**

| Rule | Weight |
|---|---|
| high_savings_signals_mortgage | 80 |
| high_income_no_credit_card | 70 |
| current_acct_no_savings | 60 |
| stable_balance_signals_investment | 65 |
| lifecycle_new_no_card | 50 |
| growing_lifecycle_no_term_deposit | 40 |
| low_engagement_signals_savings | 30 |

**Eligibility minimums byte-for-byte:**
- PERSONAL_LOAN_MIN_INCOME = KES 30,000
- MORTGAGE_MIN_INCOME = KES 80,000
- CREDIT_CARD_MIN_INCOME = KES 40,000
- INVESTMENT_MIN_BALANCE = KES 100,000
- MIN_TENURE_FOR_UNSECURED = 180 days

**Priority tiers:** HOT ≥ 70, WARM ≥ 40, COLD < 40.

### **6th Rule 7 application** — applied to **multi-class ranking/recommendation**

`next_best_action_predict(customer, ml_recommender_fn=None)`:
- **No model loaded:** `basis="rule_based"`, `ml_recommendations=None`, `reason="no_ml_recommender_loaded"`, `rule_based_recommendations` surfaced, `spec_deviation` surfaced
- **ML succeeds:** `basis="ml"`, `ml_recommendations=<list>`, **rule_based_recommendations ALSO surfaced**
- **ML fails:** `basis="rule_based"`, `reason=f"ml_recommender_error:{type(e).__name__}"`, falls back

**SPEC_DEVIATION_NOTE byte-for-byte:**
> "ML-based recommender (collaborative filtering / deep learning) is downstream work; v6 ships rule-based deterministic propensity scoring"

### **Rule 6 default-deny on missing eligibility data:**
- missing income → `eligible=False, reason="missing_income_data"` (NEVER silent allow)
- missing tenure → `eligible=False, reason="missing_tenure_data"`
- open complaint blocks all recommendations (`reason="open_complaint"`)
- already-held products excluded

**Self-test:** 19/19 PASS

---

## Audit gates added (3)

### G68 `customer_segmentation_correct`
Inline programmatic — verifies 11 RFM_SEGMENTS + 4 VALUE_TIERS + 4 LIFECYCLE_STAGES + 3 value tier thresholds byte-for-byte; RFM classification verified on edge cases (5,5,5)=CHAMPIONS, (1,1,1)=LOST, (0,5,5)=LOST, (1,3,5)=CANNOT_LOSE_THEM; Rule 1 + Rule 6 paths.

**Tampering verified:** VALUE_TIER_HNI_MIN (50M→10M) caught.

### G69 `customer_lifetime_value_correct`
Inline programmatic — 8 PRODUCT_YIELDS_PCT + NPV defaults (horizon=5/discount=12/margin=60/servicing=2400) + profitability thresholds byte-for-byte; Rule 1 + Rule 6 paths; NPV determinism verified; profitability classification on 750k=HIGH_VALUE, -1000=UNPROFITABLE, None=UNKNOWN.

**Tampering verified:** CURRENT yield (3.0→5.0) caught.

### G70 `customer_predictive_correct`
Combined inline programmatic for #71 + #72 — verifies BOTH 5th and 6th Rule 7 applications.
- **Churn (#71):** thresholds 70/40/20 + 7 weights summing to 100 + 3 trigger thresholds + SPEC_DEVIATION_NOTE byte-for-byte; **Rule 7 no-model + ML-fail paths** including rule_based_score surfaced + ml_churn_error type captured + determinism
- **Cross-Sell (#72):** 8 RECOMMENDABLE_PRODUCTS + 7 NBA_RULE_WEIGHTS + 5 min thresholds + SPEC_DEVIATION_NOTE byte-for-byte; **Rule 7 no-model + ML-fail paths**; **Rule 6 default-deny on missing income/tenure**; open complaint blocks recs

**Tampering verified:**
- CHURN_HIGH_RISK_THRESHOLD (70→40) caught
- NBA SPEC_DEVIATION_NOTE drift caught

---

## Spec deviations (cumulative — now 9, +2 new)

| # | Volume | Deviation |
|---|---|---|
| 1 | v5.49 | Heatmap React→Streamlit/plotly |
| 2 | v5.51 | React SPA + React Native scaffolding |
| 3 | v5.52 | Rule 7 / Cat D scaffolding pattern formalised |
| 4 | v5.52 | #48 LLM commentary deferred |
| 5 | v5.55 | CBK reports: 3 of 8 implemented, 5 deferred |
| 6 | v5.56 | FATCA Form 8966 XML and OECD CRS XML deferred to v7 |
| 7 | v5.57 | ML-based sentiment classification deferred to v7 |
| **8** | **v5.59** | **ML-based churn classifier (gradient boosting / neural net) deferred to v7** |
| **9** | **v5.59** | **ML-based recommender (collaborative filtering / deep learning) deferred to v7** |

---

## Rule 7 application milestone

The **5th and 6th Rule 7 applications** mark a critical milestone for the platform's no-silent-ML-prediction discipline. The pattern is now applied across **6 distinct ML modalities**:

| # | Standard | Modality |
|---|---|---|
| 1 | #41 (v5.53) | Binary classification (dormancy) |
| 2 | #48 (v5.52) | Text generation (BI commentary) |
| 3 | #53 (v5.55) | Numerical regression (credit default probability) |
| 4 | #64 (v5.57) | NLP/text classification (employee sentiment) |
| **5** | **#71 (v5.59)** | **Survival/churn classification** |
| **6** | **#72 (v5.59)** | **Multi-class ranking/recommendation** |

Every predictive output across all 6 modalities surfaces:
1. The rule-based deterministic baseline (`rule_based_score` / `rule_based_recommendations`)
2. The ML output (or `None` with reason if unavailable)
3. An explicit `basis` field ("ml" or "rule_based") — never silent substitution
4. SPEC_DEVIATION_NOTE when rule-based is the deployed mode

Per the master prompt: *"No silent ML predictions — every model-driven scoring/decision must surface model identity, training date, and confidence-or-fall-back to deterministic baseline."*

---

## Rule 6 default-deny pattern (compliance safeguard)

The Cross-Sell engine (#72) implements a critical compliance safeguard: **missing eligibility data NEVER permits a recommendation; the system fails closed.**

```python
if customer.monthly_income_kes is None:
    return {"eligible": False, "reason": "missing_income_data"}
```

Combined with:
- Open complaint blocks all recs (`reason="open_complaint"`)
- Already-held products excluded
- Tenure check for unsecured products (180-day minimum)

This pattern prevents the common failure mode where a default value (e.g., "assume KES 50,000 income") leads to ineligible offers being presented to customers.

---

## What's new in v5.59 vs v5.58

| | v5.58 | v5.59 |
|--|-------|-------|
| Standards delivered | 68 | **72** |
| Audit gates | 67/67 | **70/70 = 100%** |
| Test files | 37 | **38** |
| Total tests | 1050 | **1115** |
| Spec deviations | 7 | **9 (+2)** |
| Rule 4 applications | 6 | 6 (no change) |
| **Rule 7 applications** | **4** | **6 (+2)** |

---

## Next: Volume Fourteen — Treasury / ALM Intelligence (#73-#76)

Anticipated standards (subject to A2Z_Continuation_Spec_v6.md):
- #73 Liquidity Risk (LCR / NSFR per Basel III + CBK)
- #74 Interest Rate Risk in Banking Book (IRRBB)
- #75 FX Position Monitoring (Open FX exposure limits per CBK)
- #76 Investment Portfolio Analytics (HQLA + bond duration + yield)

Target: 4 engines + tests + 3 gates G71-G73 → 73/73.

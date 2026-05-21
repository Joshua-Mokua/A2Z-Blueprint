# A2Z MIS 360 — CHANGELOG v5.89

**v5.89 Nineteenth Integration Batch — Cross-sell NBA (#59)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 15th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **💰 REVENUE/CUSTOMER GROWTH AXIS OPENS.** First revenue/growth integration after the deep compliance/control work in v5.81-v5.88. Cumulative: **38 of 116 standards integrated.** Nineteenth integration batch.

---

## Strategic milestone — revenue/customer growth axis opens

After 4 deep compliance/control batches (v5.81 + v5.85 + v5.86 + v5.88), v5.89 opens a new axis:

| Axis | Theme | Batches |
|---|---|---|
| Compliance/control | Regulatory + COSO + ORM + KYC/AML + TxnMonitor | v5.81, v5.85, v5.86, v5.88 |
| **Revenue/customer growth** | **NBA cross-sell scoring** | **v5.89** ⭐ |

The Cross-sell team operating `pages/45_crosssell.py` can now use engine-generated NBA scoring alongside the existing manual segment/branch/funnel views. The 7-rule NBA engine handles the major Tier-2 bank cross-sell scenarios.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.89 wires **Standard #59 Cross-sell NBA** (`cross_sell_nba.py`) — deterministic rule-based propensity scoring per Rule 7 (ML predictor deferred per spec deviation #9).

---

## What was modified

### `pages/45_crosssell.py` — NBA Engine + Priority List + Engine Reference tabs added
**96 → 687 lines (+591)**

Top-level tabs expanded from 4 to 7 (exactly at G4's 7-tab limit):

| # | Tab | Status |
|---|---|---|
| 0-3 | Segment View · Branch Ranking · NBA Opportunities · Conversion Funnel | unchanged |
| **4** | **🎯 NBA Engine (Standard #59)** | **NEW** |
| **5** | **📋 Priority List (Standard #59)** | **NEW** |
| **6** | **🌳 Engine Reference (Standard #59)** | **NEW** |

### NBA Engine tab — 3 sub-tabs

**🔍 Single Customer NBA** — input customer profile (income / savings / current balance / tenure / lifecycle / 8 product-held flags / open complaint flag). Engine returns:
- Ranked recommendations with score / rule / rationale / tier
- HOT 🔥 (≥70) / WARM 🌤️ (≥40) / COLD ❄️ (<40) traffic-light tiers
- Tier-based action guidance for top recommendation

**✅ Product Eligibility** — 8 RECOMMENDABLE_PRODUCTS dropdown. Engine returns:
- `eligible` boolean
- First-failure reason: `already_held` / `income_below_threshold:K` / `balance_below_threshold:K` / `tenure_below_minimum:N` / `has_open_complaint` / `passed_all_checks`

**🌳 Demo Customer Builder** — 7 pre-configured scenarios:
1. High savings + no mortgage (mortgage rule)
2. High income + no credit card (card rule)
3. Current account only (savings rule)
4. New customer + no card (lifecycle rule)
5. Stable mature customer (investment rule)
6. Low engagement (savings nudge)
7. Customer with open complaint (excluded)

### Priority List tab

8-customer portfolio demo dataset spanning HNW/RET/SME/NEW/DECLINING profiles plus a fully-cross-sold customer and a complaint-excluded one.

Engine returns:
- Top opportunities sorted by score desc
- HOT/WARM/COLD distribution
- Bar chart of product opportunity strength (sum of scores per product)
- Pipeline guidance based on HOT count ≥5 (strong) or ≥2 (immediate follow-up)

### Engine Reference tab — 4 reference tables

**7 NBA rules sorted by weight desc** with human-readable descriptions:

| Rule | Weight | Description |
|---|---|---|
| high_savings_signals_mortgage | **80** | Savings ≥500K + no mortgage → MORTGAGE |
| high_income_no_credit_card | 70 | Income ≥100K + no card → CREDIT_CARD |
| stable_balance_signals_investment | 65 | Stable savings + no investment → INVESTMENT |
| current_acct_no_savings | 60 | Current holder + no savings → SAVINGS |
| lifecycle_new_no_card | 50 | NEW + tenure-eligible → CREDIT_CARD |
| growing_lifecycle_no_term_deposit | 40 | GROWTH + balance ≥50K → TERM_DEPOSIT |
| low_engagement_signals_savings | 30 | Low balance/tenure → basic SAVINGS nudge |

**3 tier thresholds** with action guidance.

**8 RECOMMENDABLE_PRODUCTS**: SAVINGS / CURRENT / TERM_DEPOSIT / PERSONAL_LOAN / MORTGAGE / CREDIT_CARD / INVESTMENT / INSURANCE.

**6 eligibility threshold rows** byte-for-byte:

| Product | Min income | Min balance | Min tenure |
|---|---|---|---|
| PERSONAL_LOAN | 30K | — | 180 days |
| CREDIT_CARD | 40K | — | 180 days |
| MORTGAGE | 80K | — | — |
| INVESTMENT | — | 100K | — |
| TERM_DEPOSIT | — | 50K | — |
| SAVINGS / CURRENT / INSURANCE | — | — | — |

**Spec deviation #9 surfaced in UI** with explicit warning that ML recommender is deferred per Rule 7.

### Engine file — UNCHANGED
`utils/cross_sell_nba.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 4 engine paths verified end-to-end

**`next_best_action_rule_based` — 4 representative scenarios:**

| Scenario | Recommendations | Rules applied |
|---|---|---|
| high_savings_no_mortgage | 2 | MORTGAGE 80 HOT, INVESTMENT 65 WARM |
| high_income_no_card | 1 | CREDIT_CARD 70 HOT |
| current_no_savings | 1 | SAVINGS 60 WARM |
| **complaint_excluded** | **0** | — (excluded by `last_complaint_open=True`) |

**`product_eligibility` — high-savings customer across 5 products:**

| Product | Eligible | Reason |
|---|---|---|
| MORTGAGE | ✅ | passed_all_checks |
| CREDIT_CARD | ⛔ | already_held |
| PERSONAL_LOAN | ✅ | passed_all_checks |
| INVESTMENT | ✅ | passed_all_checks |
| TERM_DEPOSIT | ✅ | passed_all_checks |

**`next_best_action_predict` Rule 7 confirmed**: without `ml_recommender_fn` returns 0 recommendations with score=None tier=None — no silent fallback.

**`cross_sell_priority_list` 4-customer portfolio**:
- total_customers=4, customers_with_no_recs=1, total_opportunities=4
- Top sorted by score desc: C001 MORTGAGE 80 HOT / C002 CREDIT_CARD 70 HOT / C001 INVESTMENT 65 WARM / C003 SAVINGS 60 WARM

**Engine logic confirmed**: 7 rules cover all major Tier-2 cross-sell scenarios. Open complaint correctly excludes customer entirely. ML predictor honors Rule 7 (no silent fallback).

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CrossSellNextBestActionEngine` has 4 STATIC class methods** — `next_best_action_rule_based`, `next_best_action_predict`, `product_eligibility`, `cross_sell_priority_list`. No instance state, easy to wire.

2. **`CustomerForCrossSell` requires customer_id + cif_id as REQUIRED**, all other 14 fields optional.

3. **🆕 `next_best_action_rule_based` returns dict WITHOUT top-level score/tier** — those are per-recommendation only. The `recommendations` list has each entry with score/tier; the wrapping dict has `recommendation_count` + `recommendations` + `applied_rules`.

4. **🆕 `next_best_action_predict` enforces Rule 7** — without `ml_recommender_fn` callback returns empty recommendations with score=None tier=None and a `note` field explaining ML deferred. **No silent fallback** to rule_based which would mask the missing ML capability.

5. **`product_eligibility` returns dict** with `eligible` boolean + `reason` string. First-failure reason format: `already_held` / `income_below_threshold:K` / `balance_below_threshold:K` / `tenure_below_minimum:N` / `has_open_complaint` / `passed_all_checks`.

6. **`cross_sell_priority_list` aggregates** next_best_action_rule_based across all customers, sorts globally by score desc, truncates to max_count. **One customer can have multiple opportunities** in the list (different products).

7. **`cross_sell_priority_list` exposes** total_customers + customers_with_no_recs + total_opportunities + top_opportunities — caller can compute pipeline-strength metrics.

8. **🆕 `last_complaint_open=True` excludes customer entirely from NBA** (returns 0 recs) — customer service should resolve complaint before cross-sell.

9. **Engine eligibility checks `has_X` flag matching the requested product** (e.g. MORTGAGE checks `has_mortgage`).

10. **Tier thresholds**: HOT≥70, WARM≥40, COLD<40 — bound byte-for-byte from `NBA_HOT_THRESHOLD` and `NBA_WARM_THRESHOLD`.

11. **`cross_sell_priority_list` respects max_count** even with many opportunities — caller can request top 5 vs top 50 to size the RM team's outreach list.

12. **Engine HARD-CODES rule weights and eligibility thresholds** — production deployment that wants tunable thresholds (e.g. for different markets) would need engine code change. Current values are reasonable Tier-2 bank defaults.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "CrossSell #59: NBA CUST_2026_001 recs=2 hot=1 warm=1 cold=0")
audit_log("IFRS_ENGINE_USED", uname, "CrossSell #59: eligibility MORTGAGE eligible=True reason=passed_all_checks")
audit_log("IFRS_ENGINE_USED", uname, "CrossSell #59: scenario DEMO_001 recs=2 applied=['high_savings_signals_mortgage', 'stable_balance_signals_investment']")
audit_log("IFRS_ENGINE_USED", uname, "CrossSell #59: priority_list total=8 no_recs=2 opps=10 top_returned=10")
```

---

## ✅ Fifteenth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.88). G3 + G4 lessons embedded. Page now sits at exactly G4's 7-tab limit.

---

## Honesty discipline visualised

- **All 7 rules surfaced** with weights + descriptions in Engine Reference
- **Tier thresholds explicit** — HOT≥70, WARM≥40, COLD<40 with action guidance
- **Eligibility reasons surfaced verbatim** — first-failure transparency (Rule 6)
- **Spec deviation #9 surfaced in UI** — explicit warning about ML deferred
- **Rule 7 enforced visibly** — `next_best_action_predict` returns empty without ML fn
- **Complaint exclusion documented** — `last_complaint_open=True` excludes from NBA
- **Engine response details displayed** — JSON viewer for product eligibility responses
- **Pipeline strength metrics** — HOT/WARM/COLD distribution + product opportunity bar chart
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G59 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9 (engine surfaces #9 in UI but pre-existing)
- Rule 7 application count — still 6
- All v5.71-v5.88 pages — unchanged
- The 4 existing tabs in `45_crosssell.py` (Segment View / Branch Ranking / NBA Opportunities / Conversion Funnel) — completely untouched
- The existing `crosssell_data.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.88

| | v5.88 | v5.89 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **37** | **38** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 14 | **15** (45_crosssell.py is a new entry) |
| Lines added across pages this batch | +523 (smart_alerts) | +591 (crosssell) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 4-path engine call simulation across 4 customer scenarios. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **3-sub-tab nesting** under NBA Engine within the now 7-tab top-level structure (page is at exactly the G4 7-tab limit).

2. **38 of 116 integrated** — 78 standards remain library-only.

3. **All sub-tabs use hard-coded demo data** — Single Customer NBA uses user-entered values, Priority List uses 8-customer demo portfolio, Demo Customer Builder uses 7 pre-configured scenarios. Production deployment would feed via `customers_register.json` matching CustomerForCrossSell schema or live CBS query. The page is a teaching/QA tool not a production batch processor.

4. **🆕 Engine uses rule-based scoring only** — Rule 7 (no silent ML predictions) is honored: `next_best_action_predict` without ml_recommender_fn returns empty recommendations with explicit note. **Production deployment that has trained an ML model can plug it in via the callback**; until then, deterministic rule-based scoring is the primary path. **Documented spec deviation #9 surfaced in UI**.

5. **🆕 7-rule catalog is fixed in engine** — adding new cross-sell rules (e.g. "insurance from mortgage holders", "premium card from high spend on standard card") requires engine code change. Production deployment that wants market-specific rules would need engine extension.

6. **Eligibility thresholds are HARD-CODED** at PERSONAL_LOAN=30K / CREDIT_CARD=40K / MORTGAGE=80K / INVESTMENT=100K balance / TERM_DEPOSIT=50K balance / 180-day unsecured tenure. These reflect typical Tier-2 Kenya bank standards. Different markets or risk appetites would need different thresholds — engine code change required.

7. **🆕 Tier thresholds (HOT≥70, WARM≥40, COLD<40) are global** — same thresholds apply regardless of customer segment. **In reality, an HNW customer with score 50 might warrant HOT-tier follow-up while a retail customer with same score does not.** Production deployment may want segment-specific tier thresholds.

8. **🆕 Open complaint exclusion is binary** — engine excludes customer from ALL NBA when `last_complaint_open=True`. **In reality, complaint topic matters** (a card-related complaint shouldn't necessarily block mortgage NBA). Production deployment may want complaint-category-aware exclusion logic.

9. **Per-customer max recommendations not capped** — engine returns ALL rule matches for a customer. A customer matching 5 rules gets 5 recommendations; for outreach prioritization, RM team likely wants top 1-2 only. Cross-sell Priority List caps GLOBAL max_count but per-customer there's no cap. Pages can post-process if needed.

10. **No support for time-decay of recommendations** — a recommendation generated today is treated identically to one generated 60 days ago in subsequent priority lists. Production deployment with persistent NBA storage should add freshness scoring.

11. **🆕 Engine operates on a single customer's static state** — no behavioral signals (recent product abandonment, browse history, customer service interactions). **Tier-1 banks layer behavioral signals on top of rule-based NBA**. Production deployment can extend by adding behavioral fields to CustomerForCrossSell.

12. **Engine doesn't model dependencies between products** — e.g. Investment recommendation makes more sense for customers WITH a current account but engine doesn't enforce this. Recommendations may be technically eligible but contextually weird. Sophistication-vs-simplicity trade-off.

---

## Strategic narrative — revenue/customer growth axis opens

After 4 deep compliance/control batches, v5.89 pivots to revenue/growth:

| Recent batches | Theme |
|---|---|
| v5.81 CBK Returns | Compliance: regulatory reporting |
| v5.85 RCSA Internal Controls + Op Risk | Compliance: governance/control |
| v5.86 KYC/AML Risk | Compliance: customer-level risk |
| v5.88 Transaction Monitoring | Compliance: proactive alerting |
| **v5.89 Cross-sell NBA** | **Revenue: customer growth** ⭐ |

The Cross-sell team can now use engine-generated NBA scoring alongside the existing manual segment/branch/funnel views. The 7-rule NBA engine handles the major Tier-2 bank cross-sell scenarios (mortgage from high savings, credit card from high income, investment from stable balance, savings nudge for current-only customers, lifecycle-driven card recommendations, term deposit growth signal, basic engagement nudge).

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Customer Segmentation | customer_segmentation | RFM analysis, behavioral clusters — natural extension of cross-sell theme |
| (2) | Churn Prediction | churn_prediction | Proactive retention (revenue protection) |
| (3) | Customer Lifetime Value | customer_lifetime_value | Already partially covered in v5.75 Customer 360 |
| (4) | Customer Profitability | customer_profitability | Revenue analytics |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With cross-sell integrated, recommend **(1) Customer Segmentation** for v5.90 — would build on revenue/growth axis with RFM-style customer clustering, complementing v5.89's NBA scoring with portfolio-level clustering analytics.

---

**Cumulative tally:** 116 standards delivered, **38 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

💰 **Revenue/customer growth axis opens** (Cross-sell NBA #59 deterministic rule-based scoring per Rule 7).

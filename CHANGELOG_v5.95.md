# A2Z MIS 360 — CHANGELOG v5.95

**v5.95 Twenty-Fifth Integration Batch — Customer Lifetime Value DEPTH (#95)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS — **but on RETRY after initial G4 failure**
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **📦 PLATFORM'S FIRST DEPTH BATCH.** Extends v5.75 CLV integration with the 3 engine paths v5.75 didn't surface. Cumulative: **44 of 116 standards integrated.** Twenty-fifth integration batch.

---

## Strategic milestone — first depth batch

v5.95 establishes a new batch type: **depth batch** rather than new-engine batch. The CLV engine has 4 methods; v5.75 surfaced 2 (clv_npv + product_yields constants) plus a basic portfolio scan. v5.95 surfaces the remaining 3 paths:

| Engine path | v5.75 status | v5.95 status |
|---|---|---|
| `clv_npv` | ✅ surfaced | ✅ + sensitivity analysis added |
| `product_yields` constants | ✅ surfaced | unchanged |
| Portfolio scan by segment | ✅ surfaced | unchanged |
| **`product_revenue`** | ❌ not surfaced | **✅ NEW** |
| **`clv_aggregate`** | ❌ not surfaced | **✅ NEW** |
| **`profitability_segment` standalone** | ❌ not surfaced | **✅ NEW** |

The 9-sub-tab CLV/Profitability stack (6 from v5.75/v5.92 + 1 new from v5.95 with 3 inner tabs) now covers the **FULL engine surface** for both #95 CLV and #57 Customer Profitability.

---

## ⚠ G4-strict lesson learned (audit failure on first attempt)

**Initial draft had 9 clv_sub_tabs which FAILED audit** on first attempt:

```
G4 tab_counts: 1 pages exceed 7-tab limit
  • 34_customer360.py: 9 sub-tabs
```

Sub-tab groups are also capped at 7 — not just top-level. The audit code in `scripts/audit.py:gate_tab_counts` checks every `<var> = st.tabs([...])` regardless of nesting depth:

```python
if len(labels) < 8:
    continue
# ... if indent ≥ 4 and len(labels) > 7: violation
```

**Fix**: collapsed 3 v5.95 sub-tabs into 1 sub-tab containing 3 inner tabs:

```
clv_sub_tabs (7 entries)
  ├─ "💰 Customer CLV Calculator"          [v5.75]
  ├─ "🌳 Product Yield Reference"           [v5.75]
  ├─ "📊 Portfolio CLV Distribution"        [v5.75]
  ├─ "💵 Customer P&L"                       [v5.92]
  ├─ "🎯 Allocation Method Comparison"       [v5.92]
  ├─ "🌳 Profitability Engine Reference"    [v5.92, renamed for clarity]
  └─ "📦 CLV Depth (Standard #95, v5.95)"  [NEW]
       └─ _clv_depth_inner (3 entries)
            ├─ "📦 Per-Holding Revenue"
            ├─ "🔬 Sensitivity Analysis"
            └─ "🌐 Portfolio NPV Aggregate"
```

**This is the first audit failure since v5.74** — 20-clean-streak technically broken. Going forward:

> **G4-strict rule**: Any `st.tabs([...])` call needs ≤7 labels, regardless of nesting depth. For depth integrations into existing sub-tab structures, use **"1 sub-tab + N inner tabs"** pattern, not N+ flat sub-tabs.

---

## What this batch is — and what it isn't

**Pure depth integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.95 wires the 3 v5.75-uncovered paths of **Standard #95 CLV** (`customer_lifetime_value.py`).

---

## What was modified

### `pages/34_customer360.py` — new sub-tab with 3 inner tabs
**2148 → 2600 lines (+452)**

**Top-level tabs UNCHANGED at 7** (G4 limit). Tab[5] CLV's `clv_sub_tabs` **expanded from 6 to 7** (right at G4 sub-tab cap). The new sub-tab "📦 CLV Depth" contains 3 inner tabs.

### Per-Holding Revenue (inner tab)

User inputs N holdings (1-8) with product type + balance, plus optional UNKNOWN_PRODUCT toggle to test Rule 6.

Engine returns:
- `holding_count` + `scored_count` + `excluded_count` + `total_annual_revenue_kes`
- `per_holding` list with holding_id / product_type / balance_kes / yield_pct / annual_revenue_kes

Page renders:
- 4 metrics (total / scored / excluded / total revenue)
- Per-holding table with **% of total** column
- Bar chart of revenue by holding
- Rule 6 warning when excluded > 0 — engine doesn't silently zero unknown products

### Sensitivity Analysis (inner tab)

User inputs demo customer (tenure + 2 product balances). Single button runs all 3 sensitivity sweeps:

**Horizon sensitivity (1-15 years):**

| Horizon | NPV (KES) |
|---|---|
| 1y | 49K |
| 5y | 197K |
| 10y | 309K |
| 15y | 372K |

**7.6x range** — surfaces why bank must set explicit horizon policy.

**Discount rate sensitivity (6-22%):**

| Rate | NPV (KES) |
|---|---|
| 6% | 230K |
| 12% | 197K |
| 20% | 163K |

**1.4x range** — modest decay because most cash flows in early years.

**Contribution margin sensitivity (30-80%):**

Linear — doubling margin doubles CLV.

### Portfolio NPV Aggregate (inner tab)

User inputs portfolio size (5-50), horizon, discount rate, plus 10%-unscored toggle to test Rule 6.

Engine returns 5 keys: `scored_count` + `unscored_count` + `total_clv_npv_kes` + `median_clv_kes` + `segment_distribution`.

Page renders:
- 4 top metrics
- Unscored warning
- **Profitability segment distribution** with traffic-light emojis 💎 HIGH_VALUE / 🟢 MEDIUM / 🟡 LOW / 🔴 UNPROFITABLE
- Bar chart
- **Concentration insights**:
  - HIGH_VALUE ≥20% → strong portfolio quality
  - UNPROFITABLE ≥20% → tier-shift candidate flag
- Expandable engine constants reference

### Engine file — UNCHANGED
`utils/customer_lifetime_value.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED

---

## 4 engine paths verified across 6 scenarios

**`product_revenue`** with 4 holdings + 1 UNKNOWN_PRODUCT:
- scored=4, excluded=1, total_revenue=280K
- UNKNOWN_PRODUCT excluded but surfaced in `excluded_count` (Rule 6)

**`clv_npv` horizon sensitivity** (same customer, 1y → 15y):
- 49K → 197K → 309K → 372K (**7.6x range**)

**`clv_npv` discount sensitivity** (6% / 12% / 20%):
- 230K → 197K → 163K (modest decay)

**`clv_npv` margin sensitivity** (30% / 60% / 80%):
- 94K → 197K → 265K (**linear**)

**`clv_aggregate`** with 10-customer mixed portfolio:
- 2 HIGH_VALUE / 0 MEDIUM / 4 LOW / 4 UNPROFITABLE
- **Notable**: MEDIUM tier hard to hit (gap between 50K and 500K thresholds)

**`clv_aggregate`** with mixed valid/invalid:
- 2 scored / 2 unscored when missing tenure_years OR holdings (Rule 6)

**`profitability_segment(None)` → "UNKNOWN"** — important Rule 6 path.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CustomerLifetimeValueEngine` has 4 STATIC class methods** — `clv_npv`, `clv_aggregate`, `product_revenue`, `profitability_segment`. No instance state.

2. **`clv_npv` returns 10 keys** but **does NOT include profitability_segment** — caller must call `profitability_segment(clv_npv_kes)` separately to get HIGH_VALUE/MEDIUM/LOW/UNPROFITABLE label.

3. **🆕 `clv_aggregate` returns 5 keys**: `scored_count`, `unscored_count`, `total_clv_npv_kes`, `median_clv_kes`, `segment_distribution` (dict of {segment_name: count}).

4. **🆕 `product_revenue` returns 5 keys**: `holding_count`, `scored_count`, `excluded_count`, `total_annual_revenue_kes`, `per_holding` (list of dicts).

5. **🆕 PRODUCT_YIELDS_PCT has 8 entries**: SAVINGS=0.5, CURRENT=3.0, TERM_DEPOSIT=1.0, PERSONAL_LOAN=12.0, MORTGAGE=4.5, CREDIT_CARD=18.0, TRADE_FINANCE=8.0, INVESTMENT=1.0. Production may want different yields for FX-fee-heavy SME or trade-finance corporates.

6. **Unknown product types are excluded NOT zeroed** — engine surfaces them in `excluded_count` (Rule 6 transparency).

7. **🆕 PROFITABILITY_SEGMENTS has 4 tiers** with thresholds:
   - HIGH_VALUE ≥ KES 500K
   - MEDIUM ≥ KES 50K
   - LOW ≥ 0
   - UNPROFITABLE < 0
   - **The gap between MEDIUM (≥50K) and HIGH_VALUE (≥500K) is wide** — production may want intermediate tiers.

8. **🆕 `profitability_segment(None)` returns "UNKNOWN"** — critical Rule 6 path. Pages mistakenly assuming non-None will treat None as LOW.

9. **Customers without `tenure_years` OR without `holdings` go to unscored_count** in clv_aggregate — engine doesn't try to estimate.

10. **CLV is highly sensitive to assumptions**: horizon 7.6x range, discount 1.4x, margin linear (2.7x). **Bank policy on these assumptions must precede production deployment**.

11. **🆕 DEFAULT_CONTRIBUTION_MARGIN_PCT=60.0** — reasonable for retail banking. **May overstate for FX-fee-heavy SME** (margins can be 80%+) **or understate for low-touch deposit-only relationships** (margins can be 30-40%).

12. **🆕 DEFAULT_ANNUAL_SERVICING_COST_KES=2400** — KES 200/month, very low, reflects digital-first economics. Production with branch-heavy customer base may want higher servicing cost.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "CLV #95: per-holding revenue scored=4 excluded=1 total_rev=280000")
audit_log("IFRS_ENGINE_USED", uname, "CLV #95: sensitivity tenure=3y horizon_spread=323000 discount_spread=66000")
audit_log("IFRS_ENGINE_USED", uname, "CLV #95: aggregate scored=10 unscored=0 total=1100000 median=24000 seg={'HIGH_VALUE': 2, 'MEDIUM': 0, 'LOW': 4, 'UNPROFITABLE': 4}")
```

---

## ⚠ Streak broken: G4-strict rule learned

**Initial draft FAILED G4 audit** on first attempt (9 sub-tabs in clv_sub_tabs). Fixed by restructuring to 7 sub-tabs + 1 sub-tab having 3 inner tabs. **The 20-clean-first-try streak is technically broken** — restart counter at 0.

**Lesson**: G4 caps both top-level tabs AND sub-tab groups at ≤7. Documented going forward as **G4-strict**.

**Going forward pattern**: depth integrations into existing sub-tab structures should use **"1 sub-tab + N inner tabs"**, not flat N+ sub-tabs.

---

## Honesty discipline visualised

- **G4-strict failure documented** — first audit failure since v5.74; lesson absorbed
- **Sensitivity analysis surfaces 7.6x horizon spread** — bank policy decision visible
- **MEDIUM tier gap surfaced** — segment distribution shows tier hard to hit
- **Rule 6 unscored handling** — customers without tenure_years OR holdings surfaced
- **Unknown product types excluded NOT zeroed** — Rule 6 transparency
- **Margin sensitivity is linear** — explicit caption explaining
- **Default assumption caveats** — caption notes 60% margin may overstate FX-fee SME, understate deposit-only
- **CLV NPV vs current-period PBT relationship** — caption explains v5.92 Profitability is current period, v5.95 CLV is NPV
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G95 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.94 pages — unchanged
- The other 6 top-level tabs in `34_customer360.py` — completely untouched
- The 6 existing CLV/Profitability sub-tabs (3 from v5.75 + 3 from v5.92) — unchanged except for renaming "🌳 Engine Reference (v5.92)" → "🌳 Profitability Engine Reference (v5.92)" for clarity
- The `customer_intelligence.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.94

| | v5.94 | v5.95 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **43** | **44** ⭐ (+1) |
| Audit gates | 103/103 (clean first try) | 103/103 (**after retry** — first failure since v5.74) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 15 | **15** (re-enhances 34_customer360.py) |
| Lines added across pages this batch | +402 (crosssell v5.94) | +452 (customer360 v5.95) |
| **34_customer360.py total lines** | 2148 | **2600** (largest non-people page) |
| **Sub-tab containment applications** | 9 | **9** (no new — used inner-tabs pattern instead) |
| Clean-first-try streak | 20 | **broken at 20** |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 6-scenario engine call simulation. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **NEW 7th sub-tab "📦 CLV Depth" with 3 inner tabs**. Users navigating from v5.92 will need to drill 1 level deeper than v5.92's 6-sub-tab structure.

2. **44 of 116 integrated** — 72 standards remain library-only.

3. **Per-Holding Revenue uses user-entered values** — production deployment would feed via CBS query joined to product master.

4. **Sensitivity Analysis uses fixed 7-point sweeps** for horizon (1, 2, 3, 5, 7, 10, 15), 7-point for discount (6, 8, 10, 12, 15, 18, 22), 6-point for margin (30, 40, 50, 60, 70, 80) — production deployment with finer granularity would need different sweep arrays.

5. **🆕 Portfolio NPV Aggregate uses synthetic 5-tier portfolio** (20% HNW + 20% mass-affluent + 20% mass + 20% small + 20% mixed) — production needs real customer master query.

6. **🆕 G4-strict lesson**: both top-level AND sub-tab groups capped at 7. The pattern "1 sub-tab + N inner tabs" preserves G4 compliance and is now standard tooling for depth integrations. **First audit failure since v5.74** — 20-clean-streak broken. Documented for future batches.

7. **No support for CLV cohort analysis** — engine returns single-snapshot aggregate, not multi-period cohort tracking. Production deployment with persistent CLV history could add cohort wrapper.

8. **No support for CLV-weighted segmentation** — v5.90 RFM uses transaction signals, v5.95 CLV is balance-and-yield-based. **The two segmentation lenses are independent**; a customer can be CHAMPIONS (RFM) but UNPROFITABLE (CLV) due to high transaction frequency on low-margin products. Production may want a unified scoring layer.

9. **🆕 PRODUCT_YIELDS_PCT is HARD-CODED** — adding new product types or adjusting yields requires engine code change. Production in different markets needs market-specific overrides.

10. **🆕 No support for FTP-based CLV** — CLV uses flat 60% margin assumption. Bank with sophisticated FTP could compute true contribution per product per customer. **Customer Profitability engine v5.92 supports FTP mode for current-period P&L but CLV engine doesn't extend this to NPV**. Documented as deferred enhancement.

11. **🆕 Customer balances treated as STATIC** — engine assumes balance_or_outstanding_kes stays constant over horizon. **Reality is customers grow or shrink relationships** — a 30-year-old customer with KES 500K savings might have KES 2M by year 10. Production with growth modeling could integrate with v5.91 Churn (likelihood of relationship continuing).

12. **Sensitivity analysis is single-customer** — doesn't show how portfolio total CLV varies with assumptions (would need clv_aggregate across each parameter sweep). Production with computational budget could surface this.

---

## Strategic narrative — depth batch pattern

v5.95 establishes a new batch type: **depth batch** — extending an existing engine integration with engine surface that wasn't covered initially. Most prior batches were "new engine" batches that wired one new standard each. This pattern is valuable when:

1. An engine is rich enough that initial integration only surfaces obvious paths
2. The unsurfaced paths add genuine analytical value
3. The page real estate exists (G4 budget) for additional sub-tabs

**The 9-sub-tab CLV/Profitability stack now covers the FULL engine surface** for both #95 CLV and #57 Customer Profitability:

| # | Sub-tab | Standard | Vintage |
|---|---|---|---|
| 0 | 💰 Customer CLV Calculator | #95 | v5.75 |
| 1 | 🌳 Product Yield Reference | #95 | v5.75 |
| 2 | 📊 Portfolio CLV Distribution | #95 | v5.75 |
| 3 | 💵 Customer P&L | #57 | v5.92 |
| 4 | 🎯 Allocation Method Comparison | #57 | v5.92 |
| 5 | 🌳 Profitability Engine Reference | #57 | v5.92 |
| 6 | **📦 CLV Depth** (3 inner: Per-Holding / Sensitivity / Aggregate) | **#95** | **v5.95** ⭐ |

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Customer Value Segments | customer_value_segments | Third segmentation lens (RFM behavioral + CLV NPV-based + value-segments alternative) |
| (2) | Compensation Equity depth | compensation_equity | If engine has features beyond v5.79 |
| (3) | Employee Engagement depth | employee_engagement | If engine has features beyond v5.79 |
| (4) | More depth batches | various | Review v5.71-v5.85 for engine surfaces not exposed |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With CLV depth integrated, the customer-centric quartet now has full depth coverage. Recommend **(1) Customer Value Segments** for v5.96 — adds a third segmentation lens.

---

**Cumulative tally:** 116 standards delivered, **44 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

📦 **Platform's first depth batch** (CLV #95 — surfaces 3 engine paths v5.75 didn't cover).

⚠ **G4-strict rule learned**: both top-level AND sub-tab groups capped at ≤7. Use "1 sub-tab + N inner tabs" pattern for depth integrations.

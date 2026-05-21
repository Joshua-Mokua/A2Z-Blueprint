# A2Z MIS 360 — CHANGELOG v5.94

**v5.94 Twenty-Fourth Integration Batch — Allocation Optimizer (#57)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 20th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🎯 RESOURCE ALLOCATION AXIS OPENS.** First integration on a new functional dimension distinct from customer-centric quartet and HR axis. Cumulative: **43 of 116 standards integrated.** Twenty-fourth integration batch.

---

## Strategic milestone — resource allocation axis opens

After the customer-centric quartet (v5.89-v5.92) and HR axis (v5.79+v5.84+v5.93) closed out, v5.94 establishes a new functional dimension:

| Axis | Core question | Integrated in |
|---|---|---|
| Customer-centric quartet | What to offer / How to group / Who to retain / How profitable | v5.89-v5.92 |
| HR axis | What happened / What should happen / How to make it happen | v5.79 + v5.84 + v5.93 |
| **Resource allocation** | **How to deploy resources optimally (RM time, capacity, capital)** | **v5.94** ⭐ |

The three axes compose:
- **Customer-centric** identifies opportunities (NBA / churn / segments)
- **HR** identifies who can act (coaching scripts / capacity / engagement)
- **Allocation** identifies optimal pairing (which customer to which RM)

The resource allocation axis is currently scoped to **RM-customer assignment** but the algorithmic pattern (greedy capacity-constrained with marginal-gain ordering) generalizes to other allocation problems: branch resource allocation, marketing spend allocation, capital allocation across business units.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.94 wires **Standard #57 Customer Allocation Optimizer** (`allocation_optimizer.py`) — greedy capacity-constrained algorithm assigns customers to RMs to maximize total projected PBT subject to per-RM capacity caps.

---

## What was modified

### `pages/45_crosssell.py` — sub-tab containment on tab[5] Priority List
**687 → 1089 lines (+402)**

**Top-level tabs UNCHANGED at 7** (already at G4 limit since v5.89). **9th application of sub-tab containment pattern** (cumulative: v5.73, v5.76, v5.79, v5.81, v5.83, v5.87, v5.90, v5.91, **v5.94**):

Tab[5] "📋 Priority List" wrapped with 4 sub-tabs:

| # | Sub-tab | Status |
|---|---|---|
| 0 | 📋 Cross-sell Priority (existing) | preserved byte-for-byte from v5.89 |
| **1** | **🎯 Optimize RM Allocation (#57)** | **NEW** |
| **2** | **🔬 What-If Projection (#57)** | **NEW** |
| **3** | **🌳 Allocation Engine Reference (#57)** | **NEW** |

### Optimize RM Allocation sub-tab

Interactive — user inputs:
- Segment + period
- Customer count slider (3-10) + per-RM capacity slider (1-5)

Engine builds 5 DI callbacks from inputs (synthetic profit matrix, round-robin current allocation), returns:
- `assignments` list with customer_id / rm_code / projected_pbt / current_rm / **marginal_gain** / upstream_ftp_mode
- `total_potential_gain` + `total_projected_pbt`
- `provisional` flag (data quality signal)
- `meta` dict with 11 fields including `unassignable` + `rm_utilization` + `algorithm_caveats`

Page renders:
- 4 metric tiles
- Provisional warning when triggered
- Data quality warning when present
- **Assignments table with current → recommended RM transitions**
- RM capacity utilization metrics (assigned/capacity per RM)
- Unassignable customers warning with reasons (Rule 6 transparency)
- Expandable engine metadata viewer

### What-If Projection sub-tab

Interactive — user inputs customer ID + period + comma-separated RM list. For each RM, engine's `project_profitability_if_served_by(customer_id, rm_code, period)` returns dict {projected_pbt, ftp_mode} or **None if RM ineligible**.

Page output:
- Eligible RMs sorted by PBT desc
- **Best-fit RM** in green banner
- Comparison table with eligible + ineligible RMs distinguished
- Rule 6 transparency caption when ineligible RMs surface

### Allocation Engine Reference sub-tab — 4 reference tables

**Engine constants:**

| Constant | Value | Meaning |
|---|---|---|
| DEFAULT_RM_CAPACITY | 30 | Max customers when capacity_fn unspecified |
| PROVISIONAL_FTP_OFF_THRESHOLD | 0.5 (50%) | Triggers `provisional=True` |

**5 DI callbacks** with returns + purpose.

**Full engine output structure** as JSON code block.

**Algorithm caption** explaining greedy_capacity_constrained_v1 with engine's own caveat surfaced.

### Engine file — UNCHANGED
`utils/allocation_optimizer.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 2 engine paths verified across 5 scenarios

**`optimize_rm_allocation`:**

| Scenario | Result |
|---|---|
| 5 customers / 3 RMs / capacity 2-3-2 | 5 assignments, gain=95K, PBT=375K, util RM001=1/2, RM002=2/3, RM003=2/2 |
| **Capacity exceeded** (8 customers, total capacity 7) | **7 assignments + 1 unassignable** ("all eligible RMs at capacity") |
| **Provisional triggers** (60% FTP-off projections) | **provisional=True**, upstream_ftp_modes={off:10, on:5} |
| Empty segment | 0 assignments + data_quality_warning="Segment has no customers — nothing to allocate" |

**`project_profitability_if_served_by` (C001 across 3 RMs)**: 50K / 75K / 60K with ftp_mode=on — best-fit RM is RM002.

**Engine logic confirmed**: greedy algorithm with marginal-gain ordering produces optimal small-fixture allocations. Capacity caps respected. Provisional flag triggers correctly at threshold. Empty segments handled gracefully.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CustomerAllocationOptimizer` is an INSTANCE class** with **5 DI callbacks** (customers_in_segment_fn, rms_for_segment_fn, rm_capacity_fn, current_allocation_fn, projection_fn) — fewer than v5.92 Customer Profitability's 8 but each has narrower contract.

2. **2 public methods**: `optimize_rm_allocation(segment, period="")` for segment-level optimization, `project_profitability_if_served_by(customer_id, rm_code, period="")` for single-customer-single-RM what-if utility.

3. **🆕 `optimize_rm_allocation` returns dict** with: `segment` + `period` + `assignments` (LIST not dict) + `total_potential_gain` + `total_projected_pbt` + `provisional` (bool) + `data_quality_warning` + `meta` (dict). **Pages mistakenly looking for `allocations` dict find empty `{}`** — non-obvious gotcha.

4. **🆕 `meta` dict has 11 fields**: `customers_in_segment` + `rms_in_segment` + `assignments_made` + `unassignable` (list of {customer_id, reason}) + `unassignable_count` + `rm_utilization` (dict like "RM001": "1/2") + `upstream_ftp_modes` (count by mode) + `provisional_threshold_pct` + `algorithm` + `algorithm_caveats` + `generated_at`.

5. **`projection_fn` signature**: `(customer_id, rm_code, period)` → `{"projected_pbt": float, "ftp_mode": "on"|"off"|"unknown"}` OR `None` if RM ineligible / data missing. **None vs missing dict matters** — caller distinguishes "no projection available" from "data error".

6. **🆕 PROVISIONAL_FTP_OFF_THRESHOLD=0.5** — when ≥50% of projection calls return ftp_mode='off', engine sets `provisional=True` signaling data quality issue. Production should aim for FTP-on projections from upstream Customer Profitability engine (v5.92).

7. **🆕 DEFAULT_RM_CAPACITY=30** — used when capacity_fn returns None or unspecified RMs. Reasonable Tier-2 bank default but may need adjustment for HNW (lower for white-glove) or retail (higher for digital-mostly).

8. **Algorithm: greedy_capacity_constrained_v1** — engine self-describes with explicit caveat in `meta.algorithm_caveats`: *"Greedy with marginal-gain ordering. Hits optimal on labelled small fixtures; for >100 customers consider Hungarian / LP solver."*

9. **🆕 Marginal gain calculation requires current_allocation_fn**: returns `rm_code | None` for each customer. Engine computes `(projected_pbt with new RM) - (projected_pbt with current RM)` when current is non-None; if current is None, marginal_gain equals projected_pbt.

10. **🆕 Unassignable customers surface in `meta.unassignable`** with reason field — engine doesn't silently drop them. Reasons include "all eligible RMs at capacity" or "no RM eligible for this customer". Caller can decide whether to expand RM pool, override capacity, or flag for manual handling.

11. **`upstream_ftp_modes` dict counts projection calls by mode** — useful debugging signal showing how many times engine queried with each ftp_mode. Can flag data plumbing issues if seeing unexpected "unknown" entries.

12. **Engine has internal `_empty_result(segment, period, warning)` helper** — when segment has no customers or no RMs, returns valid result skeleton with data_quality_warning narrative explaining the empty state. **Caller should always check `assignments` length first before iterating**.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "AllocOpt #57: segment=HNW period=2025-12 customers=5 assignments=5 gain=95000 pbt=375000 provisional=False unassignable=0")
audit_log("IFRS_ENGINE_USED", uname, "AllocOpt #57: whatif C001 rms_compared=3 eligible=3 best_rm=RM002")
```

---

## ✅ Twentieth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.93). G3 + G4 lessons embedded.

---

## Honesty discipline visualised

- **Engine's own algorithm caveat surfaced** — *"for >100 customers consider Hungarian / LP solver"* in Engine Reference
- **Provisional flag** rendered as warning banner with explicit threshold explanation
- **Unassignable customers** with reasons in dedicated table (Rule 6 transparency)
- **RM capacity utilization** explicit metrics ("assigned/capacity")
- **Best-fit RM** banner in What-If
- **Ineligible RMs** distinguished in What-If table with caption
- **Engine integration with v5.92 Profitability** documented (caller must wire projection_fn to upstream engine)
- **5 DI callbacks** with input/output schemas in Engine Reference
- **Resource allocation axis** strategic context explicit
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G57 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.93 pages — unchanged
- The 4 existing tabs in `45_crosssell.py` (Segment View / Branch Ranking / NBA Opportunities / Conversion Funnel) — unchanged
- Tabs[4] NBA Engine + Tabs[6] Engine Reference — unchanged
- The original v5.89 Cross-sell Priority output in tab[5] sub-tab[0] — preserved byte-for-byte
- The existing `crosssell_data.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.93

| | v5.93 | v5.94 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **42** | **43** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 15 | **15** (re-enhances 45_crosssell.py from v5.89) |
| Lines added across pages this batch | +520 (people v5.93) | +402 (crosssell v5.94) |
| **45_crosssell.py total lines** | 687 | **1089** |
| **Sub-tab containment applications** | 8 | **9** |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 5-scenario engine call simulation. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **NEW 4-sub-tab structure under tab[5]** (the original Cross-sell Priority output has moved into sub-tab[0], preserved byte-for-byte, so users navigating from v5.93 will need to drill one level deeper).

2. **43 of 116 integrated** — 73 standards remain library-only.

3. **All sub-tabs use deterministic synthetic profitability matrix** — Optimize RM Allocation generates a (customer_index × rm_index) → PBT matrix from base+modifier arithmetic. Production would feed via 5 DI callbacks connecting to: customer-segment registry + RM-segment registry + RM capacity master + current allocation table + **Customer Profitability engine v5.92** (projection_fn feeds back to calculate_customer_pnl with hypothetical RM).

4. **🆕 Greedy algorithm explicit caveat** — engine's own meta.algorithm_caveats notes that for >100 customers a Hungarian or LP solver should be used. **Production deployment with large segments (HNW typically <100 RMs but Mass Affluent could be >1000) must wrap with optimal solver**. Engine remains correct on small problems (≤100) but may give suboptimal results on large ones.

5. **🆕 Provisional flag is a data quality signal not an error** — when ≥50% of projections use FTP-off mode, engine sets `provisional=True`. **The output is still computed and returned** — caller decides whether to surface to users or block. Page surfaces a warning banner. Production deployment with rigorous data quality may want to BLOCK users from acting on provisional outputs.

6. **No support for multi-objective optimization** — engine maximizes total_potential_gain only. Real-world RM allocation balances multiple objectives: maximize PBT but also balance RM workload, prefer keeping existing relationships intact, avoid concentration risk per RM. Production may want objective-weighting parameters or constraint specs.

7. **🆕 No re-allocation cost modeled** — engine treats every (customer, RM) pair as zero-cost to switch. **In reality, switching a customer's RM has hidden costs** (RM onboarding time, customer relationship rebuilding, possibly customer churn). Production may want a switch-cost adjustment that pulls marginal_gain down by some fraction when current_rm differs from recommended_rm.

8. **No support for time horizon** — engine optimizes single-period PBT. **Real allocation decisions span multiple periods** — a customer that's marginal this period might be a future high-value target. Multi-period optimization would need extended engine.

9. **🆕 Algorithm doesn't model RM expertise/specialization** — projection_fn could capture this if upstream Customer Profitability engine factors it in, but the allocation engine treats RMs as fungible within their segment-eligibility. **In reality, a Trade Finance specialist RM serves an importer better than a generalist RM even if both are HNW-segment-eligible**.

10. **No support for customer preferences** — engine doesn't model whether customer has expressed RM preference (e.g. "I want to stay with Sarah"). Forced reassignment can damage relationships. Production should layer customer-veto logic.

11. **🆕 Demo data uses deterministic synthetic matrix** — production deployment must integrate with v5.92 Customer Profitability engine's calculate_customer_pnl method, feeding hypothetical (customer, period) pairs WHERE the upstream engine's allocation_inputs_fn returns the candidate RM's allocation profile. **The integration with v5.92 is documented but NOT wired** — caption notes the connection but page uses standalone synthetic matrix.

12. **🆕 Engine doesn't persist allocation decisions** — `save_allocation()` and `get_allocation()` helpers exist in the module (data/rm_allocations.json) but **aren't called from the page**. Production deployment with workflow needs (e.g. "propose allocation → manager approves → execute") would need to wire these helpers. Currently the page generates fresh allocations on each click.

---

## Strategic narrative — resource allocation axis opens

After the customer-centric quartet (v5.89-v5.92) and HR axis (v5.79+v5.84+v5.93) closed out, v5.94 establishes a new functional dimension. The three axes compose naturally:

| Axis | Identifies | Examples |
|---|---|---|
| Customer-centric | **Opportunities** | HIGH_RISK churn customer in CANNOT_LOSE_THEM segment with negative PBT |
| HR | **Capacity to act** | Which RM has bandwidth + skill for retention conversation |
| **Resource allocation** | **Optimal pairing** | **Match the at-risk customer to best-fit RM with capacity** |

The 9th application of sub-tab containment pattern is now mature standard tooling. v5.94 also extends `pages/45_crosssell.py` for the second time after v5.89 — the page is becoming the cross-sell + relationship management hub.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Customer Lifetime Value depth | customer_lifetime_value | Engine-level FTP-based CLV beyond v5.75 |
| (2) | Customer Value Segments | customer_value_segments | Alternative segmentation lens (different from v5.90 RFM) |
| (3) | Compensation Equity depth | compensation_equity | If engine has features beyond v5.79 |
| (4) | Employee Engagement depth | employee_engagement | If engine has features beyond v5.79 |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer due to regression risk) |

With resource allocation axis opened, recommend **(1) Customer Lifetime Value depth** for v5.95 — would extend the customer-centric surface with engine-level CLV depth (v5.75 covers basic CLV but the engine likely has FTP-based CLV calculation, NPV horizon variations, multi-product CLV that v5.75 integration doesn't surface).

---

**Cumulative tally:** 116 standards delivered, **43 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🎯 **Resource allocation axis opens** (Allocation Optimizer #57 — greedy capacity-constrained algorithm).

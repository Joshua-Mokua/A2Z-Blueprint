# A2Z MIS 360 — CHANGELOG v5.97

**v5.97 Twenty-Seventh Integration Batch — Compensation Equity DEPTH (#63)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 2nd consecutive after v5.96 restored streak)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **📦 SECOND DEPTH BATCH establishes pattern as mature standard tooling.** Cumulative: **46 of 116 standards integrated.** Twenty-seventh integration batch.

---

## Strategic milestone — depth-batch pattern matures

v5.97 is the platform's **second depth batch** after v5.95 (CLV depth). Both follow the same pattern:

| Depth batch | Existing integration | Depth opportunity | Pattern |
|---|---|---|---|
| **v5.95** CLV depth | v5.75 (4 sub-tabs) | 3 unsurfaced engine paths | 1 sub-tab + 3 inner tabs |
| **v5.97** Compensation depth | v5.79 (4 sub-tabs) | Composed analytics + unused fields | 1 sub-tab + 4 inner tabs |

The depth-batch pattern is now mature standard tooling:

> **When engine has rich return data or unused dataclass fields, deepen rather than ship a new standard.**

Both depth batches share the same insight: initial integration surfaces engine paths individually, but **caller-side composition + previously-unused fields create genuine analytical value beyond simple path-by-path display**.

v5.97 also pioneers the **Executive Scorecard pattern** — single-screen multi-engine summary with traffic-light verdict — applicable to other multi-output engines.

---

## What this batch is — and what it isn't

**Pure depth integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.97 wires **Standard #63 Compensation Equity DEPTH** (`compensation_equity.py`). All 4 engine paths were already wired in v5.79; v5.97 adds:

1. **Composed analytics** combining multiple engine paths
2. **Previously-unused CompensationRecord fields**: `branch_code` + `position_in_band`
3. **Caller-side cost simulator** for board-level remediation budget approval

---

## What was modified

### `pages/2_people.py` — 5th sub-tab + 4 inner tabs (G4-strict)
**2806 → 3223 lines (+417, longest page in app by far)**

**Top-level sections UNCHANGED at 4** (well under G4 limit). Section 2 "💰 Comp Equity" sub-tabs `ce_sub_tabs` **expanded from 4 to 5** (G4-strict respected ≤7):

| # | Sub-tab | Status |
|---|---|---|
| 0 | 👫 Gender Pay Gap | unchanged from v5.79 |
| 1 | 👑 CEO-to-Median Ratio | unchanged from v5.79 |
| 2 | 📐 Internal Equity (Compa-ratio) | unchanged from v5.79 |
| 3 | 📊 Pay Distribution by Grade | unchanged from v5.79 |
| **4** | **📦 Compensation Depth (#63, v5.97)** | **NEW** |

The new sub-tab uses **G4-strict pattern** (1 sub-tab + 4 inner tabs, all ≤7):

### 📋 Executive Scorecard (inner tab)

Single-screen summary combining 3 engine paths into traffic-light scorecard for board reporting:

**1️⃣ Gender pay gap** — M/F/Unknown headcount + raw severity tile + adjusted severity tile

**2️⃣ CEO-to-median ratio** — CEO salary / median / ratio severity tile

**3️⃣ Internal equity** — in-band % + below + above + no-midpoint counts

**4️⃣ Overall verdict**:
- ✅ GREEN — all metrics in healthy ranges
- ⚠ AMBER — one issue (targeted remediation)
- 🚨 RED — multiple issues (comprehensive review)

Issues counted from: {adj_gap MODERATE/HIGH, CEO HIGH/EXTREME, below>0, above>0}

### 🏢 Branch-Level Analytics (inner tab)

**Uses CompensationRecord.branch_code field that v5.79 doesn't surface.**

Per-branch table with:
- Headcount + total + avg + median + range
- Below/above band counts (per-branch invocation of internal_equity_ratios)
- Status emoji 🔴/✅

Total payroll bar chart by branch + warning when branches have band issues.

**Useful for**: branch managers reviewing local pay distribution, regional pay pattern analysis (HQ vs branches).

### 📊 Position-in-Band (inner tab)

**Uses CompensationRecord.position_in_band field (P25/P50/P75) that v5.79 doesn't analyze.**

Output:
- Overall position distribution table + bar chart
- Per-grade × position breakdown matrix
- **Compression detection**: ≥60% at P75 → compression warning, ≥60% at P25 → headroom available

**Why position concentration matters**:
- 80% at P75 → pay compression risk (no upside without grade-shift)
- 80% at P25 → headroom for merit increases without structural changes

### 🎯 Underpaid-Uplift Simulator (inner tab)

Interactive slider 0.80-1.10 for target compa-ratio. Engine identifies BELOW_BAND staff via internal_equity_ratios. Computes:

- target_salary = grade_midpoint × target_compa
- uplift = target_salary - current_salary
- Aggregate cost across affected staff

Per-staff table + aggregate metrics + **% of total payroll context** for board pack.

**Default 0.95** brings underpaid staff to mid-band; 1.57% of typical payroll = fits in single merit cycle.

### Engine file — UNCHANGED
`utils/compensation_equity.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED

---

## 3 engine paths verified across 5 scenarios

**Test dataset**: 15 staff records spanning EXEC/M3/M2/M1/S2/S1/T1 grades, HQ/BR01/BR02 branches, M/F gender mix, P25/P50/P75 positions, 2 deliberately underpaid (S008, S011).

**Scenario 1 — Executive Scorecard combination:**
- Raw GPG = -54.17% (HIGH severity — but driven by female-MD outlier)
- **Adjusted GPG = 1.0% (FAIR)** — within-grade analysis exonerates the bank
- CEO ratio = 7.4× (HEALTHY) — appropriate for Tier-2 Kenya
- Internal equity = 13 in-band, 2 below-band, 0 above-band

**Insight**: This reveals exactly why grade-adjusted analysis matters. A naive "raw gap" reading would flag this as discriminatory; the adjusted analysis shows pay is fair within grades.

**Scenario 2 — Branch-level distribution:**
- BR01: 5 staff, total KES 3.15M, 1 below-band
- BR02: 5 staff, total KES 2.98M, 1 below-band
- HQ: 5 staff, total KES 15.1M, 0 below-band

**Insight**: Pay issues localized to branches (M1 + S2 grades). Branch managers can spot and remediate at their level.

**Scenario 3 — Position concentration**: 33%/33%/33% in deterministic test data (real banks would skew).

**Scenario 4 — Underpaid uplift @ 0.95:**
- 2 affected staff (S008, S011)
- Total uplift: KES 332,500
- **1.57% of total payroll** (KES 21.23M)

**Insight**: Fits within single 3-5% merit cycle. Board approval defensible.

**Scenario 5 — Edge cases**:
- CEO ID not found → returns None (caller surfaces error, doesn't crash)
- Empty records → all paths return None gracefully

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`CompensationEquityEngine` has 4 STATIC class methods** — gender_pay_gap, ceo_to_median_ratio, internal_equity_ratios, pay_distribution_by_grade. All already wired in v5.79.

2. **`CompensationRecord` has 8 fields**: 5 required (staff_id, base_salary_kes, grade, role, branch_code) + 3 optional (gender, position_in_band, grade_midpoint_kes). v5.97 surfaces previously-unused `branch_code` + `position_in_band`.

3. **🆕 `gender_pay_gap` returns 10 keys** including separate raw vs adjusted gap (raw uses overall medians, adjusted is grade-weighted). v5.79 surfaces both; v5.97 scorecard combines into single tile pair.

4. **🆕 `ceo_to_median_ratio` returns None for invalid CEO ID** — caller must check. v5.97 scorecard surfaces error message vs ratio metrics.

5. **🆕 `internal_equity_ratios` returns 5 keys**: records, below_band_count, above_band_count, in_band_count, no_midpoint_count. Records list contains per-staff compa_ratio + band.

6. **🆕 Compa-ratio band thresholds** from engine constants:
   - COMPA_RATIO_HEALTHY_MIN=0.8
   - COMPA_RATIO_HEALTHY_MAX=1.2
   - Engine returns string "BELOW_BAND" / "IN_BAND" / "ABOVE_BAND"

7. **🆕 CEO ratio severity thresholds**:
   - HEALTHY ≤ 50× (CEO_RATIO_HEALTHY_MAX)
   - ELEVATED 50-100×
   - HIGH 100-300× (CEO_RATIO_HIGH_THRESHOLD=100)
   - EXTREME > 300×
   - Tier-2 Kenya bank likely 5-15× (HEALTHY)

8. **🆕 Pay gap severity thresholds**:
   - FAIR ≤ 5% (PAY_GAP_FAIR_MAX_PCT)
   - MODERATE 5-10% (PAY_GAP_MODERATE_MAX_PCT)
   - HIGH > 10%
   - Engine bands raw and adjusted separately

9. **`gender_pay_gap` per_grade list is EMPTY when by_grade=False** — caller must pass by_grade=True. v5.79 always passes True.

10. **🆕 No engine path for branch-level summaries** — engine treats records as flat list. v5.97 implements branch-level analytics via caller-side filtering + per-branch invocation. Documented as deferred engine enhancement.

11. **🆕 No engine path for position-in-band concentration** — same pattern as branches. v5.97 implements caller-side aggregation.

12. **🆕 Underpaid-uplift simulator is caller-side composition** — engine doesn't have built-in remediation cost calculator. v5.97 builds on internal_equity_ratios output by joining with original records to access grade_midpoint_kes for cost computation.

---

## Audit logging

Every depth invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "Comp #63 (depth): scorecard issues=2 adj_gap=1.0 ceo_ratio=7.4 below=2 above=0")
audit_log("IFRS_ENGINE_USED", uname, "Comp #63 (depth): branch analytics branches=3 with_issues=2")
audit_log("IFRS_ENGINE_USED", uname, "Comp #63 (depth): position analytics P25=33% P75=33%")
audit_log("IFRS_ENGINE_USED", uname, "Comp #63 (depth): uplift target=0.95 affected=2 cost=332500 pct=1.57")
```

---

## ✅ Second consecutive clean-first-try

Audit clean on first attempt — **2nd consecutive after v5.96 restored streak from v5.95 break**. G4-strict pattern absorbed and routine.

> Top-level tabs ≤7 AND sub-tab groups ≤7. Depth integrations use **"1 sub-tab + N inner tabs"** pattern.

v5.97 followed exactly: 5 ce_sub_tabs (top-level) + 4 _ce_depth_inner (in new sub-tab) — both ≤7.

---

## Honesty discipline visualised

- **Raw vs adjusted GPG distinction explicit** — adjusted gap is the true equity test
- **Severity thresholds byte-for-byte** from engine constants
- **GREEN/AMBER/RED verdict logic explicit** — issue counting transparent
- **Branch-level analytics surfaces issues localized to branches**
- **Position concentration thresholds (60%) explicit** in code (caveat noted as caller-side parameter)
- **Compa-ratio band labels** ("BELOW_BAND", "IN_BAND", "ABOVE_BAND") preserved from engine
- **Uplift simulator only handles BELOW_BAND** — design simplification documented (overpaid staff are policy-sensitive)
- **% of payroll context** for uplift cost — board can sanity-check vs merit budget
- **CEO not found returns None** — graceful error vs crash
- Every depth call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G63 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.96 pages — unchanged
- Sections 0-1 + 3 in `2_people.py` — completely untouched
- The 4 existing ce_sub_tabs (v5.79) — unchanged
- Section 0's BSC sub-tabs (v5.79) + Section 1's predictive performance — unchanged
- The `staff_register.xlsx` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.96

| | v5.96 | v5.97 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **45** | **46** ⭐ (+1) |
| Audit gates | 103/103 (clean first try) | 103/103 (**clean first try**) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 15 | **15** (re-enhances 2_people.py) |
| Lines added across pages this batch | +516 (customer360 v5.96) | +417 (people v5.97) |
| **2_people.py total lines** | 2806 | **3223** (longest page in app, by far) |
| Clean-first-try streak | restored to 1 | **2** |
| **Depth batches cumulative** | 1 (v5.95) | **2** (+v5.97) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude** — page passes `python -m py_compile`, module-level engine import test, and 5-scenario engine call simulation. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **NEW 5th sub-tab "📦 Compensation Depth" with 4 inner tabs**. The page now has the **deepest section structure**: top-level Section 2 → ce_sub_tabs[4] → _ce_depth_inner[0..3].

2. **46 of 116 integrated** — 70 standards remain library-only.

3. **Executive Scorecard composes 3 engine paths** but doesn't include pay_distribution_by_grade — that requires per-grade selection so doesn't fit single-screen summary. v5.79 sub-tab[3] still surfaces it independently.

4. **🆕 Branch-Level Analytics uses caller-side per-branch invocation** of internal_equity_ratios — production deployment with 35+ branches would benefit from engine-level `branch_level_summary` method. Performance acceptable for ≤50 branches.

5. **🆕 Position-in-Band analytics requires position_in_band data** in CompensationRecord — production deployment must populate this from HR pay-band-position assignments. Without populated data, sub-tab shows informational message.

6. **🆕 Compression detection thresholds (60%) are HARD-CODED** in caller code — production may want configurable thresholds. Documented as caller-side parameter.

7. **Underpaid-uplift simulator uses target_compa SLIDER 0.80-1.10** — production may want preset targets ("bring everyone to 0.85" / "midpoint 1.0" / "P75 1.10") rather than free-form slider.

8. **🆕 Uplift simulator only handles BELOW_BAND staff** — doesn't address ABOVE_BAND (overpaid). Design simplification — overpaid staff are policy-sensitive (typically grandfathered or red-circled rather than reduced).

9. **🆕 No multi-period scenario** — uplift cost is single-snapshot. Real remediation may phase across 2-3 years to fit annual merit budget.

10. **🆕 Branch-level analytics doesn't normalize by cost-of-living** — comparing absolute branch payrolls across regions ignores Nairobi vs Mombasa vs Kisumu CoL differences. Defensible at this stage (Kenya regional differentials <15%).

11. **🆕 Three engine analyses don't unify into composite score** — Executive Scorecard surfaces them side-by-side. Production may want explicit weighted composite (e.g. pay_equity_score = 0.4 × adj_gpg + 0.3 × ceo_ratio + 0.3 × compa_band). **Same gap pattern as customer segmentation lenses** (v5.90 RFM + v5.95 CLV + v5.96 Customer Value) lacking unified score.

12. **No support for time-series compensation tracking** — engine returns single-snapshot scores. "Did our gender pay gap improve from 8% to 4% over 3 years?" requires session-history persistence + delta computation.

---

## Strategic narrative — depth-batch pattern matures

v5.97 confirms the depth-batch pattern as standard tooling:

| Depth batch | Engine | What v5.x already had | What depth adds |
|---|---|---|---|
| **v5.95** CLV | customer_lifetime_value | 4 sub-tabs (clv_npv calculator + product yields + portfolio scan + profitability tabs) | 3 unsurfaced engine paths (product_revenue, sensitivity sweeps, clv_aggregate) |
| **v5.97** Compensation | compensation_equity | 4 sub-tabs (gender + CEO + compa-ratio + distribution) | Composed analytics (Exec Scorecard) + 2 unused fields (branch_code, position_in_band) + remediation cost simulator |

Both depth batches are **value-additive without standards-additive** — same engine, deeper UI surface. The pattern is replicable to other rich engines:

- RCSA (v5.85) could deepen with cross-control aggregation
- AML (v5.86) could deepen with correlated-risk analytics
- Stress testing (v5.78) could deepen with scenario library

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Employee Engagement depth | employee_engagement | Likely features beyond v5.79 (eNPS, theme analysis, driver concentration) — symmetric depth coverage with v5.97 |
| (2) | More depth batches | various | Review v5.71-v5.85 for unsurfaced engine paths |
| (3) | Composite scoring layer (segmentation) | NEW | Combines v5.90 + v5.95 + v5.96 lenses (engine code change required) |
| (4) | Composite scoring layer (compensation) | NEW | Unified pay-equity score from gender + CEO + internal equity |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With Compensation Equity depth integrated, recommend **(1) Employee Engagement depth** for v5.98 — would complete the v5.79-extended HR axis depth coverage symmetrically (Compensation depth v5.97 + Engagement depth v5.98).

---

**Cumulative tally:** 116 standards delivered, **46 integrated into UI via 3 dedicated pages + 15 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

📦 **Second depth batch establishes pattern as mature standard tooling.** Executive Scorecard pattern pioneered — applicable to other multi-output engines.

✅ **Clean-first-try streak: 2** (G4-strict routine after v5.95 lesson absorbed).

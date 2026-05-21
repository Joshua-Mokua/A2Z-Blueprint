# Changelog — v10.376 PM Framework Bridge (Phase A Third / Course Correction)

**Date:** 2026-05-13
**Phase:** 4 (sixty-first arc — Phase A third batch / course correction)
**Audit:** G262 added (locks PM review + bridge + MD cockpit integration; AST-verified read-only)
**Tests:** 14/14 PASSED in `test_v10376_pm_framework_bridge.py`; 250 prior tests unchanged = **264 total**
**Verifier:** 328/328 checks pass on a clean extract
**G162 baseline:** 4022 (70 consecutive zero-drift batches)
**Master prompt:** v4.19 → v4.20 (lockstep — twenty-first consecutive batch)

---

## Your direction

> "Continue. Note, the other objective of the entire system is performance management and we have a whole performance framework with BSC and KPI with a target cascade from the MD, I really don't want us to lose the gist of this system. This happened to me and I have had to work so hard to try and get the development of this system back on course. I still continue insisting a complete 360 system review and understanding even as we proceed."

This is the most important course correction so far. The unification arc (v10.368-v10.375) focused entirely on PBT — which is **one** KPI of 109 active. The system's PRIMARY purpose is performance management: BSC + KPI Library + Target Cascade from MD downwards. v10.376 corrects course by:

1. **Doing a deep 360 review** of the PM framework
2. **Identifying the drift** between canonical engines and PM framework
3. **Building the first bridge** (read-only) so MD sees one number for PBT
4. **Establishing the pattern** that Phase D will apply to all 108 remaining KPIs

## What v10.376 delivered

### 1. `docs/PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md` — NEW (~14KB, 9 Parts)

The deep survey: 185 KPIs (109 active), 4+2 pillars, 227 roles, 1,051 cascade entries, 8,167 actuals records per period. MD has 12 KPIs (including PBT). 21 of 109 KPIs are cascaded.

**Part 1** — System scale verified
**Part 2** — Where canonical PBT fits (discovery: PBT IS kpi_id="PBT", pillar=Financial, weight=0.2, source="management_accounts" — the drift)
**Part 3** — Unification pattern generalized to all KPIs (Phase D scope)
**Part 4** — Drift catalogue: KPI-ID mismatch, pillar weight drift, source_module drift, cascade-vs-fixed-threshold gaps
**Part 5** — How the MD's daily question should be answered
**Part 6** — Refined roadmap with PM framework as primary
**Part 7** — What v10.376 actually delivers (concrete scope)
**Part 8** — Decisions awaiting Joshua
**Part 9** — Honest acknowledgement of drift

### 2. `utils/canonical_pbt_bsc_view.py` — NEW (~380 LOC, 5 self-tests)

**Read-only bridge** joining canonical profitability with Performance Management:

```python
@dataclass
class MDPBTSummary:
    actual: float                       # from compute_pbt_from_cbs (G250)
    target: float                       # from target_cascade.json::300001|PBT|2026 (G258)
    achievement_pct: float
    delta: float
    allocations: List[Dict]             # 12 direct reports + cascaded amounts
    drill_links: Dict[str, str]
    canonical_engine_status: Dict       # G250/G256/G257/G258/G253/G261 provenance
    body_system_axes: Dict              # skeleton/circulatory/function
    note: str

def get_md_pbt_summary(cbs_dir, period) → MDPBTSummary
def get_md_cascade_allocations(period) → List[Dict] (enriched with v10.374 tier)
def format_md_pbt_card(summary) → Streamlit-ready markdown
```

**Read-only invariant**: AST-verified that no `submit`/`submit_batch`/`_persist` imports come from `bsc_engine`. Write-bridge is deferred to v10.377+ when all consumers of source_module are mapped.

**Engine provenance documented** — every G-gate the bridge depends on is in `canonical_engine_status` so the UI can show users exactly what's reconciling.

**Body-system axes documented** — Joshua's framing now coded into the summary itself (skeleton/circulatory/function).

### 3. MD cockpit (`pages/100_md_cockpit.py`) — ENHANCED

BSC Summary tab gets a new section AFTER the existing perspective scores (no existing logic disturbed). New section:
- 4-metric KPI box row: Canonical PBT / Cascade Target / Achievement % / 12 reports
- "Lineage + body-system axes" expander showing engine provenance + 3 axes
- "12 cascade allocations" expander with the dataframe enriched by v10.374 tier
- Drill links to Branch Ranking (113), SBU Drill-down (114), Staff PBT (120, v10.375), Target Cascade (12)

If the bridge fails (e.g. canonical engine unavailable), the section shows a graceful warning and the existing BSC perspectives still render normally.

### G262 audit gate

Locks 5 invariants:
1. PM review document has all 9 Parts
2. Bridge module has all 7 canonical symbols
3. MD cockpit imports + uses the bridge
4. End-to-end probe: `get_md_pbt_summary` returns a populated summary with all expected fields (actual ≠ 0 OR explanatory note; all 6 canonical gates referenced; both skeleton + circulatory axes documented; drill_links contain staff_pbt)
5. **Read-only invariant**: AST inspection confirms bridge does NOT import `bsc_engine.submit`/`submit_batch`/`_persist`

### Tests — 14/14 across 4 sections

**Section 1 (PM review):** doc present and >10KB, all 9 Parts, drift documented concretely (KPI-ID drift, Pillar weight drift, Source-module drift)

**Section 2 (bridge):** module + 7 symbols, canonical actual returned non-zero, joins with MD cascade target, allocations enriched with role taxonomy, AST-verified read-only, all 6 canonical gates in engine_status, all 3 body-system axes

**Section 3 (MD cockpit + G262):** cockpit integrates bridge, G262 passes

**Section 4 (no regression):** all 7 prior unification identities still hold, role taxonomy still 100% coverage

## Files changed

| File | Change |
|---|---|
| `docs/PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md` | **NEW** (~14KB, 9 Parts) |
| `utils/canonical_pbt_bsc_view.py` | **NEW** (~380 LOC, 5 self-tests) |
| `pages/100_md_cockpit.py` | **ENHANCED** — +79 LOC in BSC Summary tab (no existing logic touched) |
| `scripts/audit.py` | **NEW** `gate_pm_framework_bridge` (G262) with AST read-only check |
| `scripts/verify_local_state.py` | Extended to 328 checks |
| `tests/integration/test_v10376_pm_framework_bridge.py` | **NEW** — 14 tests across 4 sections |
| `docs/Master_Prompt_v4.20.md` | **NEW** — lockstep bump from v4.19 |

## Verified outcome

| Metric | Value |
|---|---|
| Course corrected toward PM framework | **YES** |
| PM ecosystem understood | **109 active KPIs, 4+2 pillars, 227 roles, 1,051 cascade entries, 8,167 actuals/period** |
| Canonical PBT now visible in MD cockpit alongside BSC scores | **YES** |
| Bridge read-only invariant | **LOCKED** (AST-verified) |
| Audit gates | 261 → **262** (G262 added) |
| All 7 prior unification identities | still PASS |
| All v10.374 + v10.375 invariants | still PASS |
| Tests | +14 in v10.376; **264 total across v10.358–v10.376** |
| Verifier | 309 → **328 checks** |
| Master prompt | v4.19 → **v4.20** — lockstep (21 consecutive batches) |
| G162 baseline | 4022 (**70 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **This batch is a course correction, and the acknowledgement is in the artifact**. Part 9 of the review document is titled "Honest acknowledgement of drift" — it explicitly says: "I (Claude) went deep on PBT unification without fully integrating with the PM framework. The cumulative result: engine excellence in isolation. Joshua's intervention is what prevented this from accumulating further."

2. **Read-only bridge is the safe move**. Writing canonical PBT into `bsc_actuals_*.json` via `bsc_engine.submit()` would mean another `source_module` entering the actuals stream. Today the actuals have many source_modules; adding one is fine but **deprecating others is risky** because some are bound to legacy consumers. Mapping all submit-callers is v10.377+ scope.

3. **PBT KPI is found in kpi_library.json with `source: management_accounts`**. This means today's BSC PBT actual probably comes from a parsed management-accounts file, not from CBS. The canonical engine (v10.370) is more authoritative (atomic, identity-locked) but isn't yet the source. Bridging means: read both, show canonical in MD cockpit, leave management_accounts in place for any existing consumers, eventually deprecate management_accounts after coverage check.

4. **MD's 12 KPIs reveal severe KPI-ID drift**. The roles_kpis['Managing Director'] list contains `DEP_GROWTH`, `LOAN_GROWTH`, `FEES_COMM`, `CIR`, `NIM`, `ROE`, `NEW_CUST`, `DIGITAL_ACT`, `NPS` — **none of these IDs appear in `kpi_library.json::kpis`**. Only PBT, NPL_RATIO, DILIGENCE have matching definitions. This is the biggest PM framework drift item; v10.378 should canonicalise IDs.

5. **Pillar weight drift is severe too**. Library array says 40/25/25/10 (the canonical BSC weights). The `pillar_weights` field shows 68/14/6/12. Different consumers may use different weights. The MD's composite BSC score depends on which file each consumer reads. Documented; deferred to dedicated batch.

6. **80% of active KPIs have no cascade target**. 109 active KPIs, 21 cascaded. The remaining 88 are scored against fixed thresholds. This may be intentional (some KPIs like NPS or audit-score don't cascade — they're absolute thresholds) but worth Joshua's review.

7. **The bridge enriches allocations with v10.374 role taxonomy on-the-fly**. If `classify_role` can't import or fails, allocations still return but with `profitability_tier='unknown'`. The bridge degrades gracefully.

8. **The body-system axes are now in code, not just prose**. `MDPBTSummary.body_system_axes` returns a dict with skeleton/circulatory/function definitions. Future bridges can reuse this framing. The "function" axis is acknowledged as "future v10.4XX work" — not implemented yet.

9. **MD cockpit integration is additive only**. The new section appears AFTER the existing perspective scores + drill info. If anything goes wrong in the bridge, the existing BSC perspectives still render. Try/except wraps the entire new section.

10. **Bridge module has zero upward imports beyond the canonical engines**. Same pattern as v10.364's pbt_computation: this is a leaf module that consumes the engine layer; nothing above it consumes anything below it incorrectly.

11. **`get_md_cascade_allocations` is called separately** in addition to via summary. This lets future callers query just the cascade tree without running the canonical engine (which takes ~1.5s). The summary call combines both.

12. **The PM review document explicitly identifies Phase D scope** as applying the unification pattern to all 108 remaining active KPIs. That's a substantial program but now explicitly mapped per pillar (Financial 37 / Customer Focus 18 / Operational Excellence 25 / People & Learning 12 / Process 13 / Risk 3).

13. **Rule N2 held — single concern: surface canonical PBT in PM framework, read-only**. The customer master merge (Phase B start, v10.377) is deferred. KPI-ID canonicalisation (v10.378) is deferred. Pillar weight reconciliation is deferred. Write-bridge is deferred.

14. **The v10.376 review document's Part 9 includes the acknowledgement**: "every future canonical engine must include a BSC bridge as part of its ship scope. The unification work is incomplete without integration into Performance Management, because Performance Management is the system's primary purpose."

15. **Phase A is COMPLETE** with v10.376. v10.374 (taxonomy) + v10.375 (UI) + v10.376 (PM bridge). Phase B opens with v10.377 (customer master merge per Joshua approval).

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10376_session_cumulative.zip` flat
4. Run `python scripts\verify_local_state.py` → expect **ALL 328 CHECKS PASSED**
5. **Open MD Cockpit page (100_md_cockpit.py) → Tab 2: BSC Summary.** Scroll past the existing 4 perspective scores. You should now see:
   - "🧭 Canonical PBT — Cross-Module Integration (v10.376)"
   - Canonical PBT box (KES X.XB)
   - Cascade Target box (KES 22.00B if cascade data present)
   - Achievement % box
   - 12 reports box
   - Expandable "📚 Lineage + body-system axes" panel
   - Expandable "📊 12 cascade allocations" panel
   - Drill links to Branch Ranking, SBU Drill-down, Staff PBT (v10.375 page), Target Cascade

6. **Read the deep PM framework review:** `docs\PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md` — this is the strategic anchor for Phase D (applying the unification pattern to all 108 remaining KPIs).

7. Read `docs\Master_Prompt_v4.20.md`

8. (Optional, takes >5min) Audit → expect **262/262 PASS**

## What comes next — v10.377

**v10.377 — Customer master merge** (Phase B first batch, per your earlier approval "merge into 1"). Today:
- `customer_intelligence.json` — 3,206 customers, marketing master
- CBS `customers.csv` — 100 (seed) or 700K (production), transactions master
- Two different universes with potential overlap

Goal: one unified customer master that all downstream consumers (customer 360, customer_profitability, marketing, segmentation, RM portfolio assignments) share. Pattern: same as profitability unification — atomic per-customer record + reconciliation identity (every consumer sees the same N customers) + canonical engine + audit gate + backward compat.

Want me to continue with v10.377?

# Changelog — v10.394 Line Manager Hierarchy & Fixed KPI Mechanism Review

**Date:** 2026-05-13
**Phase:** Phase C2 third review batch — Target Cascade Rescue arc
**Phase 4 arc count:** seventy-eighth arc
**Audit:** G279 added
**Tests:** 12/12 PASSED in `test_v10394_hierarchy_and_fixed_kpi_review.py`
**Verifier:** 504/504 checks pass on clean extract
**G162 baseline:** 4022 (87 consecutive zero-drift batches)
**Master prompt:** v4.36 → v4.37 (lockstep — 38 consecutive batches)
**Type:** REVIEW ONLY — zero code/data changes beyond doc + gate + tests

---

## Your direction

> "continue, note the fixed KPI is the reserve of the MD since they might change, we have a tap in the target cascade module where the MD ticks what needs to be fixed, remember also not all ratios are fixed e.g NPL varies from branch to branch. Then the cascade follows the line manager hierarchy, we had one defined which you also need to do a deep dive to review and see, it is the same hierarchy that flows upwards right from the pipeline module"

Four-part guidance:
1. Fixed KPI = MD's reserve (existing tap/tab)
2. Not all ratios are fixed (NPL varies per branch)
3. Cascade follows line manager hierarchy
4. Same hierarchy used by pipeline module upward flow

v10.394 is the **deep-dive review** you asked for — confirms each point, surfaces what diverges, plans alignment.

## What I confirmed (4 Architectural Truths A1-A4)

| ID | Truth |
|---|---|
| **A1** | Fixed KPI status is MD's reserve — exists at `pages/12_cascade.py` Tab "🔒 Fixed KPIs" (MD-only access). Mechanism in `utils/core.py::CascadeManager` (`set_fixed_kpis`, `get_fixed_kpis`, `get_fixed_value`, `is_fixed`). Data in `data/fixed_kpis.json` (quarterly periods, currently 16 fixed KPIs for 2026-Q1). BSC consumes correctly in `pages/1_perform.py`. **No rebuild needed.** |
| **A2** | Not all ratios are fixed. NPL Ratio, PBT, Total NFI, NIM, ROE, CIR all correctly in `_v10324_removed_from_fixed` (vary per unit). CX Score, Audit Score, CASA Ratio, PAR, Compliance Score IS in current fixed list (bank-wide). |
| **A3** | Canonical line manager hierarchy is at `data/org_hierarchy_config.json::role_manager_whitelist` (26 subordinate roles). Uses ACTUAL data role names ("Chief Retail Banking Officer" not "Director Retail Banking", "Area Manager" not "Regional Head"). |
| **A4** | Fixed KPI tab UI is correctly designed — MD ticks + enters value, replicates to all staff carrying that KPI. |

## What I found that diverges (9 findings TC33-TC41)

| # | Severity | Finding |
|---|---|---|
| TC33 | 🟡 MEDIUM | Canonical hierarchy lives in `role_manager_whitelist` field, NOT a field called `hierarchy` |
| **TC34** | 🟠 HIGH | Cascade page (`pages/12_cascade.py`) tries to load field `hierarchy` (wrong name) — always falls back to hardcoded HIERARCHY constant |
| **TC35** | 🟠 HIGH | Pipeline page (`pages/3_pipeline.py`) has inline `_HIER` with **8 pre-canonical role names** that don't match data ("Managing Director" / "Director Retail Banking" / "Regional Head" / "Branch Credit Manager" / "Direct Sales Officer") |
| **TC36** | 🟠 HIGH | Cascade page's fallback HIERARCHY has the same 8 wrong role names as pipeline |
| TC37 | 🟠 HIGH | 8 specific role-name mismatches documented: Managing Director vs Chief Executive & Managing Director; Director Retail Banking vs Chief Retail Banking Officer; Director Commercial Banking vs Chief Commercial Officer; Chief Finance Officer vs Chief Financial Officer; Chief Operations Officer vs Chief Operating Officer; Head Of Retail vs Head of Retail Banking; Regional Head vs Area Manager; Branch Credit Manager vs (doesn't exist) |
| TC38 | 🟡 MEDIUM | Period mismatch — `fixed_kpis.json` uses quarterly (2026-Q1), `target_cascade.json` + `bank_targets.json` use annual (2026). CascadeManager must translate. |
| **TC39** | 🔴 **CRITICAL** | **NPL Ratio (human name) is removed-from-fixed (correctly per-branch); but NPL_RATIO (UPPERCASE_SNAKE) IS in current fixed list — same KPI, two names, two fix-statuses.** Naming bug from v10.391 TC3/TC11 intersects Fixed KPI mechanism. |
| TC40 | 🟠 HIGH | My `cascade_structure_engine.WITHIN_BRANCH_ROLE_PAIRS` has **9 missing + 6 extra pairs** vs canonical role_manager_whitelist. Built from inspection, not from canonical. |
| TC41 | 🟢 LOW | Spelling duplicates in role_manager_whitelist ("Senior Manager -Credit Analysis" with space-hyphen AND "Senior Manager-Credit Analysis" no space — same role, two spellings) |

## What this means for the rescue arc

**Revised execution sequence after this review:**

| Batch | Concern | Driver | Notes |
|---|---|---|---|
| **v10.395** | **Align WITHIN_BRANCH_ROLE_PAIRS to canonical role_manager_whitelist** | TC40 | First action batch; single concern, no decisions |
| v10.396 | Re-cascade using canonical hierarchy + Fixed KPI mechanism | TC32 + A3 | Resolves TC18/TC21/TC22/TC25/TC32 |
| v10.397 | Cascade page reads canonical hierarchy (fix field name) | TC34 | One-line bug + remove fallback |
| v10.398 | Pipeline page reads canonical hierarchy (remove inline _HIER) | TC35 | Unify with cascade source |
| v10.399 | Period harmonization quarterly↔annual | TC38 | CascadeManager translation |
| v10.400 | NPL Ratio / NPL_RATIO consolidation | TC39 | Subset of v10.397 KPI vocabulary work |

**No new Joshua decisions surfaced** — your guidance answered C5 + the hierarchy question. C1, C2, C3, C4, C6 from v10.391 remain on backlog but don't block v10.395-v10.400.

## Verified outcome

| Metric | Value |
|---|---|
| Design doc `LINE_MANAGER_HIERARCHY_AND_FIXED_KPI_REVIEW_v10.394.md` (10 Parts) | ✅ |
| 4 architectural truths A1-A4 documented | ✅ |
| 9 findings TC33-TC41 with severities | ✅ |
| Cross-check engine pairs vs canonical (live data probe) | ✅ |
| NPL contradiction surfaced (TC39 CRITICAL) | ✅ |
| 12 integration tests on live data | ✅ |
| 206 Phase B+C+C2 arc tests pass total | ✅ |
| Audit gates | 278 → **279** |
| Verifier | 499 → **504 checks** |
| Master prompt lockstep | **38/38 consecutive batches** |
| G162 baseline | 4022 (**87 consecutive zero-drift batches**) |
| Zero data/code changes | ✅ |

## 15 honest acknowledgements

1. **You were right on all four points.** Fixed KPI mechanism exists and works. Canonical hierarchy exists in `role_manager_whitelist`. NPL is correctly per-branch. Pipeline uses same hierarchy direction-flipped. v10.394 confirms each.

2. **My v10.393 engine had approximate WITHIN_BRANCH_ROLE_PAIRS** — built from inspection, not canonical. 9 missing + 6 extra. v10.395 will derive from canonical.

3. **TC39 (NPL Ratio naming contradiction) is the most insidious bug** I've surfaced. Same KPI, two naming conventions, two opposite fix-statuses. Caller-dependent BSC behavior. Fix is part of v10.391 TC11 vocabulary consolidation.

4. **Pipeline `_HIER` and cascade `HIERARCHY` both contain "Managing Director"** as the root role — but the actual user William Mwanake has role "Chief Executive & Managing Director". So when either page tries `_HIER[my_role]`, the MD's lookup fails. Both pages have downstream code paths that compensate, but it's fragile.

5. **The cascade page's bug is one line**: `_org_hier = _get_org().get("hierarchy", {})` looks for field "hierarchy", but the canonical store calls it "role_manager_whitelist". One-line fix in v10.397.

6. **`role_manager_whitelist` is upward-pointing** (subordinate → [managers]); the cascade walks downward; the pipeline walks upward. Both use the same canonical via inversion. v10.398 unifies via a shared helper.

7. **The Fixed KPI tab is genuinely well-designed** — MD-only guard, per-pillar grouping, value-input with format awareness (% vs absolute), checkbox state preservation. v10.394 just confirms; v10.395+ uses it.

8. **`_v10324_removed_from_fixed` is a great pattern** — the data file documents its own evolution. v10.394 reads it to confirm A2 (NPL/PBT/etc correctly removed).

9. **The 16 currently-fixed KPIs are a sensible MD-controlled set**: CX Score, Audit Score, Staff Productivity, CASA Ratio, PAR, Account/Channel Dormancy, plus 7 legacy K-codes, plus COMPLIANCE_SCORE plus the TC39-contradictory NPL_RATIO.

10. **Pattern: review batch → action batches → mid-arc discovery → guidance-driven review → action.** v10.391 → v10.392 → v10.393 (TC32 discovery) → v10.394 (guidance review) → v10.395+ (execution). Each turn refines the plan; the arc converges.

11. **No backup directory created** (review only) — pattern matches v10.391.

12. **12 tests verify live data, not just doc text** — every architectural truth and finding gets an executable probe. If data drifts, tests will catch it.

13. **TC41 (spelling duplicates)** is the smallest finding — "Senior Manager-X" vs "Senior Manager -X" with extra space. Probably normalisation; trivial fix. Listed for completeness.

14. **53 Phase C2 tests now exist** (15+11+15+12) across the four batches. Each ratchets against live data. Good regression safety.

15. **Decision count summary**: from v10.391 we had C1-C6. Your guidance answered C5 (ratios) + the implicit "what hierarchy to use" (canonical). C1, C2, C3, C4, C6 remain on the backlog for later batches but do NOT block v10.395-v10.400 execution.

## On your end

1. Close Streamlit
2. Extract `a2z_v10394_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **504/504**
4. Read `docs\LINE_MANAGER_HIERARCHY_AND_FIXED_KPI_REVIEW_v10.394.md` (10 Parts)
5. Open the Fixed KPI tab in cascade page to verify it works as A4 says (only as MD)
6. Tell me **"continue"** → v10.395 = align `WITHIN_BRANCH_ROLE_PAIRS` to canonical (single concern, no decisions, low risk)

## What's next — v10.395

**Single concern**: replace inspection-based `WITHIN_BRANCH_ROLE_PAIRS` constant in `utils/cascade_structure_engine.py` with derivation from canonical `org_hierarchy_config.json::role_manager_whitelist`.

1. Add helper that loads role_manager_whitelist
2. Filter to branch-level managers (exclude Area Manager, Senior Branch Manager, Head of Branches, C-suite — those have regional/HQ supervision)
3. Compute (manager_role, subordinate_role) pairs
4. Update `WITHIN_BRANCH_ROLE_PAIRS` to use derived set (or expose as function)
5. Re-run `full_audit()` — expect different cross_branch_count and multi_sender_count
6. Update G278 + tests as needed

After v10.395, the engine accurately reflects canonical. v10.396 (re-cascade) can confidently use it.

Continue?

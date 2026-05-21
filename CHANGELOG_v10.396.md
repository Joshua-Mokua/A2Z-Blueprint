# Changelog — v10.396 Canonical Hierarchy Aligned with Joshua's Clarification

**Date:** 2026-05-13
**Phase:** Phase C2 fifth action batch — Target Cascade Rescue arc
**Phase 4 arc count:** eightieth arc
**Audit:** G281 added
**Tests:** 10/10 PASSED in `test_v10396_hierarchy_aligned.py`
**Verifier:** 515/515 checks pass
**G162 baseline:** 4022 (89 consecutive zero-drift batches)
**Master prompt:** v4.38 → v4.39 (lockstep — 40 consecutive batches)
**Type:** **CONFIG CHANGE ONLY** — no code modifications (architectural payoff)

---

## Your direction

> "note at branches we can either have a senior branch manager or a branch manager, this is depended on the size of the branch. The branch operations manager, in BRM (Branch Relationship manager - in big branches), SRO senior Relationship Officer, RO Personal/Business Banker and DSR reports to the branch manager, the branch operations supervisor, teller, Customer Service report to the branch operations manager but hope all this can now be aligned well from the admin config"

Your clarification revealed two specific divergences in canonical config:

1. **Senior Branch Manager was tier 3** (regional supervision) — but Joshua says SBM is a branch top for big branches (should be tier 4 like Branch Manager)
2. **DSR was canonically under BOS/BOM** — but Joshua says DSR reports to Branch Manager

Plus the implicit: **big-branch tops (SBM) have the SAME subordinates as regular-branch tops (BM)** — meaning SBM should be alt manager for BOM/BRM/BSRO/RO PB/RO BB.

## What v10.396 did

Three canonical changes to `data/org_hierarchy_config.json` — pure config alignment, no code:

### Change 1: SBM tier 3 → 4

```json
"role_tiers": {
    "Senior Branch Manager": 4   // was 3
}
```

Big-branch top, not regional supervision. Equal to Branch Manager.

### Change 2: SBM added as alt manager for branch subordinates

```json
"role_manager_whitelist": {
    "Branch Operations Manager": ["Branch Manager", "Senior Branch Manager"],   // added SBM
    "Branch Relationship Manager": ["Branch Manager", "Senior Branch Manager"],  // added SBM
    "Branch Senior Relationship Officer": ["Branch Manager", "Branch Relationship Manager", "Senior Branch Manager"],
    "Relationship Officer-Personal Banker": ["Branch Relationship Manager", "Branch Manager", "Senior Branch Manager"],
    "Relationship Officer-Business Banker": ["Branch Relationship Manager", "Branch Manager", "Senior Branch Manager"]
}
```

### Change 3: DSR reporting line moved BOS/BOM → BM/SBM

```json
"role_manager_whitelist": {
    "Direct Sales Representative": ["Branch Manager", "Senior Branch Manager"],   // was [BOS, BOM]
    "Direct Sales Representative - Assets & Liabilities": ["Branch Manager", "Senior Branch Manager"]
}
```

Plus added `_v10396_joshua_clarification` provenance note documenting the change.

## Engine auto-derivation effects

v10.395's dynamic engine reads the updated canonical without any code change. Live effects:

| Metric | Before v10.396 | After v10.396 |
|---|---|---|
| WITHIN_BRANCH_ROLE_PAIRS count | 17 | **22** |
| Pairs added | — | 5 (Senior Branch Manager → BOM/BRM/BSRO/RO PB/RO BB; BM/SBM → DSR variants) |
| Pairs removed | — | 4 (BOS/BOM → DSR variants) |
| Cross-branch violations | 19,026 | **25,893** |
| Multi-sender ambiguities | 10,269 | 10,269 |
| Critical rep-sender roles | 58 | 58 |

**Cross-branch climb is CORRECT.** Previously SBM was tier 3 (treated as regional → multi-branch cascade OK). Now SBM is tier 4 (branch top → cross-branch cascade is a violation). Same staff data, more accurate evaluation.

## Why this is architecturally beautiful

The v10.395 → v10.396 progression demonstrates **config-driven design done right**:

- v10.395 made the engine read from canonical config (no hardcoded role names)
- v10.396 updated the canonical config to match Joshua's clarification
- **Zero lines of code changed in v10.396**
- Engine instantly reflects the new business reality

This is what Joshua asked for: "hope all this can now be aligned well from the admin config". The architecture supports it.

## Data verification

8 SBMs in users.json across 8 distinct branches:
- Kenyatta Avenue, FB Towers Retail, FB Towers Corporate, Thika, Mombasa Kenyatta Avenue (+3 more)

1 SBM per branch — confirms Joshua's "big branches have SBM" model. SBMs are NOT covering multiple branches as regional supervisors.

## What v10.396 deliberately did NOT do

Per Rule N2 (single concern: canonical alignment):
- Did NOT re-cascade target_cascade.json (v10.397 territory)
- Did NOT change code in cascade_structure_engine.py (config-only)
- Did NOT add admin UI for editing hierarchy (v10.398 territory)
- Did NOT touch fixed_kpis.json or pipeline `_HIER`

Single concern: align canonical to Joshua's clarification.

## Verified outcome

| Metric | Value |
|---|---|
| Config alignment applied (3 changes) | ✅ |
| Backup at `data/_v10396_backups/org_hierarchy_config.json.before` | ✅ |
| Provenance note `_v10396_joshua_clarification` documents changes | ✅ |
| Engine auto-derives new 22 pairs (vs 17 before) | ✅ |
| All 10 v10.396 tests pass | ✅ |
| All 229 Phase B+C+C2 arc tests pass | ✅ |
| Audit gates | 280 → **281** |
| Verifier | 509 → **515 checks** |
| Master prompt lockstep | **40/40 consecutive batches** |
| G162 baseline | 4022 (**89 consecutive zero-drift batches**) |
| Zero code modifications | ✅ |

## Phase C2 progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.391-v10.394~~ | Diagnosis + cycle fix + engine + review | ✅ |
| ~~v10.395~~ | WITHIN_BRANCH dynamic from config | ✅ |
| ~~**v10.396**~~ | **Canonical aligned with Joshua's clarification** | ✅ **DONE** |
| v10.397 | Re-cascade (resolves TC18/TC21/TC22/TC25/TC32) | next |
| v10.398 | Admin UI to EDIT hierarchy from config | covers your "reporting lines from admin" point |
| v10.399 | Period harmonization | |
| v10.400 | NPL naming consolidation | |

## 12 honest acknowledgements

1. **Config-only change.** Zero lines of Python touched. The architectural payoff from v10.395's dynamic engine.

2. **Your clarification was specific and actionable** — 3 concrete divergences with clear fixes. Made the alignment mechanical.

3. **Cross-branch violations rose, not fell.** That's CORRECT — SBM cross-branch cascades that were ignored (tier 3 = regional) are now flagged (tier 4 = branch). Same data, more accurate evaluation.

4. **8 SBMs across 8 branches confirmed.** Data already reflects your description; we just told the engine.

5. **Same architectural pattern as v10.380** (KPI alias resolver). Each rescue batch validates the canonical-driven pattern.

6. **Backup preserved.** `data/_v10396_backups/org_hierarchy_config.json.before` for rollback if needed.

7. **Provenance note** `_v10396_joshua_clarification` in the config itself documents the change. Self-documenting data.

8. **Tier 3 still excluded from within-branch.** Area Manager (true regional supervisor) remains tier 3 and is correctly excluded. Only SBM moved.

9. **DSR pairs cleaner now.** BM/SBM → DSR replaces the previous BOS/BOM → DSR. v10.397 re-cascade will use this.

10. **Patch zip much smaller this time** — just config diff + 1 test + audit + master prompt. Code is unchanged.

11. **v10.398 is now the obvious next admin work** — UI to let MD/admin edit `org_hierarchy_config.json::role_tiers` and `role_manager_whitelist` from within the app. Covers "reporting lines from admin" fully.

12. **The body's nervous system is becoming addressable** from admin. v10.395 made the engine listen to admin config; v10.396 demonstrated admin config can change reality. v10.398 will give MD the steering wheel.

## On your end

1. Close Streamlit
2. Extract `a2z_v10396_patch.zip` flat on top of v10.395 state
3. Run `python scripts\verify_local_state.py` → expect **515/515**
4. Verify the engine: `python utils\cascade_structure_engine.py` → cross-branch shows **25,893** (was 19,026; rose because SBM cross-branch is now flagged)
5. Tell me **"continue"** → v10.397 = re-cascade using updated canonical + Fixed KPI mechanism

## What v10.397 will do

**Re-cascade** — single batch that resolves TC18, TC21, TC22, TC25, TC32 simultaneously:

1. Read canonical `role_manager_whitelist` (now Joshua-aligned)
2. Read `fixed_kpis.json` to know which KPIs to SKIP (per Joshua's C5 + A1)
3. For each non-fixed KPI in bank_targets:
   - For each branch manager (BM or SBM at that branch):
     - Cascade to their actual same-branch subordinates per canonical
4. Backup current target_cascade.json
5. Replace target_cascade.json with new per-staff cascade
6. Re-run cascade_structure_engine.full_audit() — expect: 0 cycles, 0 within-branch cross-branch violations, 0 multi-sender ambiguities, 0 critical representative-sender roles

After v10.397, the cascade is structurally healthy. The remaining work (v10.398+) is UI + period harmonization.

Continue?

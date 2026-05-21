# Changelog — v10.395 WITHIN_BRANCH_ROLE_PAIRS Dynamic from Admin Config

**Date:** 2026-05-13
**Phase:** Phase C2 fourth action batch — Target Cascade Rescue arc
**Phase 4 arc count:** seventy-ninth arc
**Audit:** G280 added
**Tests:** 12/12 PASSED in `test_v10395_within_branch_pairs_dynamic.py`
**Verifier:** 509/509 checks pass
**G162 baseline:** 4022 (88 consecutive zero-drift batches)
**Master prompt:** v4.37 → v4.38 (lockstep — 39 consecutive batches)
**Delivery:** **PATCH ZIP ONLY** (per your efficiency request)

---

## Your direction

> "continue, session cumulative zip has grown large and it is taking time to extract, it is possible to zip what is changing for extraction but ensure we don't miss out on any change, also the rest of the downloads seem to slow us down... we can stick to the code and keep the changes. Then as you continue confirm that the role names that apply to the hierarchy stem from the admin config like the KPIs since different banks may name different roles differently and we don't want those hardcoded, and that also the reporting lines can be set from the admin"

Three asks:
1. **Patch-only delivery** — drop cumulative zip + individual files
2. **No hardcoded role names** — different banks deploy with their own taxonomies
3. **Reporting lines from admin** — config-driven, not code-driven

v10.395 addresses #2. Admin UI for #3 comes in v10.398. Patch delivery starts now (#1).

## What v10.395 did

Replaced the hardcoded 15-pair set literal in `utils/cascade_structure_engine.py`:

**Before (v10.393):**
```python
WITHIN_BRANCH_ROLE_PAIRS: Set[Tuple[str, str]] = {
    ("Branch Manager", "Branch Operations Manager"),
    ("Branch Operations Supervisor", "Teller"),
    ...
}
```

**After (v10.395):**
```python
def load_role_tiers() -> Dict[str, int]: ...
def load_role_manager_whitelist() -> Dict[str, List[str]]: ...
def load_branch_tier_threshold() -> int: ...
def load_within_branch_role_pairs() -> Set[Tuple[str, str]]:
    """A pair is within-branch iff BOTH roles at tier >= threshold."""

WITHIN_BRANCH_ROLE_PAIRS = load_within_branch_role_pairs()
```

## Rule

A `(manager_role, subordinate_role)` pair is within-branch iff:
- subordinate has the manager in `role_manager_whitelist`
- AND `role_tiers[manager_role] >= branch_tier_threshold`
- AND `role_tiers[subordinate_role] >= branch_tier_threshold`

**Default threshold = 4** (tier 4+ is branch-level). Bank can override via `branch_tier_threshold` config field.

Tier system (from `org_hierarchy_config.json::role_tiers`):
- 0 = MD (root)
- 1 = C-suite (HQ)
- 2 = Heads/Directors (HQ)
- 3 = Senior managers + Area Manager (REGIONAL — multi-branch supervision)
- 4 = Managers (branch-level)
- 5 = Officers (branch-level)
- 6 = Frontline (branch-level)

Tier 3 (Area Manager, Senior Branch Manager) correctly excluded — regional supervision crosses branches legitimately.

## Live findings shift

| Metric | v10.393 (hardcoded) | v10.395 (canonical) |
|---|---|---|
| Within-branch pair count | 15 | **17** |
| Cross-branch violations | 25,137 | **19,026** (canonical-aligned) |
| Multi-sender ambiguities | 10,269 | **10,269** (independent) |
| Pairs added vs hardcoded | — | 9 (BM→ROs, BOM→Teller/CSO/DSR, BRM→BSRO, BOS→DSR) |
| Pairs removed vs hardcoded | — | 6 (BSRO→ROs, BM→BCM, BOM→SDCO, etc.) |

**TC40 (v10.394 finding) RESOLVED**: engine pairs now match canonical exactly.

## Bank portability achieved

The engine is now bank-agnostic. To deploy A2Z MIS 360 at a different bank:
- Update `data/org_hierarchy_config.json::role_tiers` with that bank's role taxonomy
- Update `role_manager_whitelist` with that bank's reporting lines
- Optionally override `branch_tier_threshold` if their tier system differs

**No code changes needed.** The cascade structure engine reflects whatever the admin config says.

## What v10.395 deliberately did NOT do

Per Rule N2 (single concern):
- Did NOT add admin UI for editing the hierarchy (v10.398 territory)
- Did NOT re-cascade (v10.396 territory)
- Did NOT fix cascade page's wrong field name bug (v10.397 territory)
- Did NOT change pipeline `_HIER` (v10.398 territory)
- Did NOT touch `fixed_kpis.json`

## Test adjustments

- `test_v10393_canonical_within_branch_pairs` — updated to use canonical pairs (BSRO→RO PB removed since canonical says BRM/BM supervises ROs, not BSRO)
- `test_v10394_engine_within_branch_pairs_diverges_from_canonical` — **RETIRED** (renamed `_RETIRED_v10395`); TC40 divergence resolved
- `cascade_structure_engine.self_test()` test #9 updated to verify tier respect rather than specific role-name literals

Same pattern as v10.392 retiring v10.391's TC20 test: when the bug is fixed, the test that verified the bug existed correctly fails.

## Verified outcome

| Metric | Value |
|---|---|
| Engine has 4 dynamic helpers | ✅ |
| No hardcoded role-name literals in WITHIN_BRANCH set | ✅ |
| Engine remains leaf-pure (AST-verified) | ✅ |
| 17 pairs derived from canonical | ✅ |
| All pairs respect tier threshold | ✅ |
| Tier-3 (regional) roles excluded | ✅ |
| Configurable threshold (default 4) | ✅ |
| 12 v10.395 integration tests pass | ✅ |
| 218 Phase B+C+C2 arc tests pass total | ✅ |
| Audit gates | 279 → **280** |
| Verifier | 504 → **509 checks** |
| Master prompt lockstep | **39/39 consecutive batches** |
| G162 baseline | 4022 (**88 consecutive zero-drift batches**) |

## Phase C2 progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.391~~ | Deep diagnosis | ✅ DONE |
| ~~v10.392~~ | TC20 circular cascade fix | ✅ DONE |
| ~~v10.393~~ | Structure engine + TC32 discovery | ✅ DONE |
| ~~v10.394~~ | Hierarchy + Fixed KPI review | ✅ DONE |
| ~~**v10.395**~~ | **WITHIN_BRANCH dynamic from canonical** | ✅ **DONE** |
| v10.396 | Re-cascade using canonical hierarchy + Fixed KPI | next |
| v10.397 | Cascade page reads canonical (fix `hierarchy` field name lookup) | |
| v10.398 | Pipeline page reads canonical; admin UI to EDIT hierarchy | |
| v10.399 | Period harmonization (quarterly ↔ annual) | |
| v10.400 | NPL Ratio / NPL_RATIO naming consolidation | |

## 12 honest acknowledgements

1. **Architectural fix, not data fix.** v10.395 doesn't change cascade data; it changes how the engine sees what data SHOULD look like. The 19,026 violations were always there; we just now count them canonically.

2. **Engine is now bank-portable.** Different banks deploy with different role taxonomies; engine reads whatever the admin config says.

3. **TC40 resolved cleanly.** v10.394 surfaced 9 missing + 6 extra pairs; v10.395 derives from canonical → 0 divergence.

4. **Tier-3 exclusion is principled, not arbitrary.** Tier 3 = regional supervision (Area Manager, Senior Branch Manager). Multi-branch cascade from these roles is legitimate. The tier threshold encodes this rule.

5. **Threshold default = 4 is bank-specific to Ecobank Kenya** but admin-configurable. Other banks override `branch_tier_threshold`.

6. **Engine remains leaf-pure** — AST-verified. The new helpers don't import from `utils.*` upward. Just read JSON, return data.

7. **Module constant + function pattern.** `WITHIN_BRANCH_ROLE_PAIRS` is populated at import; refreshable via function. Best of both: fast access + admin-update visibility on re-import.

8. **Same pattern as v10.380** (KPI Alias Resolver). KPI vocabulary moved from hardcoded to admin-configurable. Now role vocabulary follows. Pattern: canonical data + helpers + module constant.

9. **Test pattern stable**: test changes are SMALL (rename one test, update one set membership check). 53 → 65 Phase C2 tests; 218 arc total.

10. **No backup file needed** — code change only, no data change. Pattern matches v10.390 financial_ratios_engine.

11. **Delivery efficiency**: dropping the cumulative zip + individual files saves you significant extraction time per batch. The patch zip alone (~10KB) contains every change.

12. **Joshua's "ensure we don't miss out on any change"** — the patch zip is byte-identical to the diff against v10.394 cumulative. Same files, less weight.

## On your end

1. Close Streamlit
2. Extract `a2z_v10395_patch.zip` flat ON TOP OF your v10.394 state
3. Run `python scripts\verify_local_state.py` → expect **509/509**
4. Test the engine: `python utils\cascade_structure_engine.py` → expect 9 self-tests pass, **cross-branch shows 19,026** (was 25,137)
5. Tell me **"continue"** → v10.396 = re-cascade using canonical hierarchy + Fixed KPI mechanism (resolves TC18/TC21/TC22/TC25/TC32 in one batch)

## What v10.396 will do

Re-generate `target_cascade.json` from scratch using:
- Canonical hierarchy (`role_manager_whitelist`)
- Bank targets (`bank_targets.json`)
- Fixed KPI list (`fixed_kpis.json`) — SKIP cascading these per A1 (MD reserves)
- Per-staff branch awareness (no cross-branch contamination)

Outcome: cascade structure engine reports 0 cycles, 0 critical representative-sender roles, 0 within-branch cross-branch violations, 0 multi-sender ambiguities. All five Phase C2 symptoms resolved in one operation.

Continue?

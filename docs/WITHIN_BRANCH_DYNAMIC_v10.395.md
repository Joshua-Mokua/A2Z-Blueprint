# WITHIN_BRANCH_ROLE_PAIRS Dynamic from Admin Config

**Version anchor:** v10.395 (May 2026)
**Per:** Joshua's directive — *"role names that apply to the hierarchy stem from the admin config like the KPIs since different banks may name different roles differently and we don't want those hardcoded, and that also the reporting lines can be set from the admin"*
**Phase:** Phase C2 — Target Cascade Rescue arc (fourth action batch)
**Audit:** G280 added
**Tests:** 12/12 PASSED in `test_v10395_within_branch_pairs_dynamic.py`

## Part 1 — Problem

`utils/cascade_structure_engine.py` shipped in v10.393 with a hardcoded 15-pair set literal of within-branch role pairs:

```python
WITHIN_BRANCH_ROLE_PAIRS = {
    ("Branch Manager", "Branch Operations Manager"),
    ("Branch Operations Supervisor", "Teller"),
    ...
}
```

Two problems:
1. **Bank portability** — different banks name roles differently. "Branch Manager" might be "Branch Head" elsewhere. Hardcoded strings = can't deploy.
2. **Admin control** — Joshua wants reporting lines settable from admin UI (v10.398). If roles are hardcoded, admin edits to config are ignored.

## Part 2 — Solution

Replace the hardcoded set with derivation from the canonical store `data/org_hierarchy_config.json` (already populated; same one v10.394 confirmed as canonical).

Four new helper functions:

```python
def load_role_tiers() -> Dict[str, int]:
    """Canonical role→tier (0..6) from org_hierarchy_config.json::role_tiers"""

def load_role_manager_whitelist() -> Dict[str, List[str]]:
    """Canonical subordinate→[managers] from role_manager_whitelist"""

def load_branch_tier_threshold() -> int:
    """branch_tier_threshold field; default 4"""

def load_within_branch_role_pairs() -> Set[Tuple[str, str]]:
    """Pairs where BOTH roles have tier >= threshold"""

WITHIN_BRANCH_ROLE_PAIRS = load_within_branch_role_pairs()  # at import
```

## Part 3 — The rule

A `(manager, subordinate)` pair is **within-branch** iff:

1. Subordinate has this manager in `role_manager_whitelist`
2. AND `tiers[manager] >= branch_tier_threshold`
3. AND `tiers[subordinate] >= branch_tier_threshold`

Default threshold = **4** (Ecobank Kenya). Configurable per bank via optional `branch_tier_threshold` field.

Tier system (canonical):

| Tier | Layer | Within-branch sender? |
|---|---|---|
| 0 | MD | No (root) |
| 1 | C-suite | No (HQ) |
| 2 | Heads/Directors | No (HQ) |
| 3 | Senior managers, Area Manager | **No (regional supervision is legitimately multi-branch)** |
| 4 | Managers (Branch Manager, BOM, BRM) | **Yes** |
| 5 | Officers (BOS, BSRO, RO PB/BB) | **Yes** |
| 6 | Frontline (Teller, CSO, DSR) | **Yes** |

## Part 4 — Live findings shift

| Metric | v10.393 (hardcoded) | v10.395 (canonical) |
|---|---|---|
| Within-branch pairs | 15 | **17** |
| Cross-branch violations | 25,137 | **19,026** |
| Multi-sender ambiguities | 10,269 | 10,269 |

**Pairs that v10.395 ADDS** (canonical recognizes, my v10.393 hardcoded set missed):
- Branch Manager → Relationship Officer-Business Banker
- Branch Manager → Relationship Officer-Personal Banker
- Branch Operations Manager → Customer Service Officer
- Branch Operations Manager → Teller
- Branch Operations Manager → Direct Sales Representative (2 variants)
- Branch Operations Supervisor → Direct Sales Representative (2 variants)
- Branch Relationship Manager → Branch Senior Relationship Officer

**Pairs that v10.395 REMOVES** (my v10.393 set had, canonical doesn't):
- Branch Manager → Branch Credit Manager (BCM doesn't exist per TC17)
- Branch Operations Manager → Senior Digital Channels Officer (SDCO has own line)
- Branch Senior Relationship Officer → 4 RO/DSR pairs (canonical says BRM/BM supervises ROs, not BSRO)

## Part 5 — Bank portability

To deploy A2Z MIS 360 at a different bank:

1. Update `data/org_hierarchy_config.json::role_tiers` with that bank's role names + tiers
2. Update `role_manager_whitelist` with that bank's reporting lines
3. Optionally set `branch_tier_threshold` if their tier system differs
4. Restart the app

**Zero code changes needed.** The engine reflects whatever the admin config says.

## Part 6 — What v10.395 deliberately did NOT do

Per Rule N2 (single concern: dynamic derivation):
- Did NOT add admin UI for editing hierarchy (v10.398 territory)
- Did NOT re-cascade target_cascade.json (v10.396 territory)
- Did NOT fix cascade page's `hierarchy` field-name bug (v10.397 territory)
- Did NOT touch pipeline `_HIER` (v10.398 territory)
- Did NOT change fixed_kpis.json

Single concern: make the engine read from canonical instead of hardcoded.

## Part 7 — Test deltas

- `test_v10393_canonical_within_branch_pairs` — updated to use canonical pairs (BSRO → RO PB removed; canonical says ROs report to BRM/BM)
- `test_v10394_engine_within_branch_pairs_diverges_from_canonical` — **RETIRED** (renamed `_RETIRED_v10395`); TC40 divergence resolved
- `cascade_structure_engine.self_test()` test #9 updated to verify tier respect rather than specific role-name literals

Same pattern as v10.392 retiring v10.391's TC20 test: when the bug is fixed, the test that verified the bug existed correctly fails.

## Part 8 — Honest acknowledgements

1. **Architectural change, not data change.** v10.395 changes how the engine SEES the rules, not the data itself. The 19,026 violations were always there; we now count them canonically.

2. **TC40 (v10.394 finding) is resolved cleanly.** 9 missing + 6 extra → 0 divergence.

3. **Engine remains leaf-pure** (AST-verified). The new helpers don't import from `utils.*` upward. Just read JSON, return data.

4. **Threshold default = 4 is Ecobank Kenya specific** but admin-configurable. Other banks override.

5. **Module constant + function pattern**: `WITHIN_BRANCH_ROLE_PAIRS` is populated at import; refreshable via function. Best of both worlds.

6. **Same architectural pattern as v10.380** (KPI Alias Resolver). KPI vocabulary moved from hardcoded to admin-configurable. Now role vocabulary follows. Pattern: canonical data + helpers + module constant.

7. **No data change, no backup file.** Code change only. Pattern matches v10.390 financial_ratios_engine.

8. **Patch-only delivery starts now.** Per Joshua's request, no cumulative zip, no separate doc files. Patch zip alone contains all changes.

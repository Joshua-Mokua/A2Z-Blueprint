# Canonical Hierarchy Aligned with Joshua's Clarification

**Version anchor:** v10.396 (May 2026)
**Per:** Joshua's directive 2026-05-13 — *"at branches we can either have a senior branch manager or a branch manager, this is depended on the size of the branch... BOM, BRM, BSRO, RO PB, RO BB, DSR report to the branch manager... BOS, Teller, CSO report to the branch operations manager... hope all this can now be aligned well from the admin config"*
**Phase:** Phase C2 fifth action batch
**Audit:** G281 added
**Type:** **CONFIG CHANGE ONLY** — zero code modifications

## Part 1 — Problem

Joshua's clarification revealed canonical config diverged from the actual operating model in three ways:

| Aspect | Canonical was | Joshua's truth |
|---|---|---|
| Senior Branch Manager tier | 3 (regional supervision) | **4 (branch top)** |
| SBM as alt manager for branch subs | NOT listed | **YES** (big-branch top, same reports as BM) |
| DSR reporting line | BOS, BOM | **BM, SBM** |

## Part 2 — Solution

**Three config changes in `data/org_hierarchy_config.json`:**

### Change 1 — SBM tier
```json
"role_tiers": { "Senior Branch Manager": 4 }   // was 3
```

### Change 2 — SBM as alt manager
```json
"role_manager_whitelist": {
    "Branch Operations Manager": ["Branch Manager", "Senior Branch Manager"],
    "Branch Relationship Manager": ["Branch Manager", "Senior Branch Manager"],
    "Branch Senior Relationship Officer": ["Branch Manager", "Branch Relationship Manager", "Senior Branch Manager"],
    "Relationship Officer-Personal Banker": ["Branch Relationship Manager", "Branch Manager", "Senior Branch Manager"],
    "Relationship Officer-Business Banker": ["Branch Relationship Manager", "Branch Manager", "Senior Branch Manager"]
}
```

### Change 3 — DSR reporting line
```json
"role_manager_whitelist": {
    "Direct Sales Representative": ["Branch Manager", "Senior Branch Manager"],
    "Direct Sales Representative - Assets & Liabilities": ["Branch Manager", "Senior Branch Manager"]
}
```

Plus `_v10396_joshua_clarification` provenance note documents what changed and why.

## Part 3 — Engine auto-derivation effects

v10.395's dynamic engine reads the updated canonical without any code change:

```
WITHIN_BRANCH_ROLE_PAIRS:  17 → 22 pairs
  Added:    SBM → BOM/BRM/BSRO/RO PB/RO BB/DSR/DSR-A&L (7)
            BM → DSR/DSR-A&L (2)  [via canonical: DSR ← BM,SBM]
  Removed:  BOS → DSR/DSR-A&L (2)
            BOM → DSR/DSR-A&L (2)

Cross-branch violations:  19,026 → 25,893
```

Cross-branch climb is **correct** — SBM cross-branch cascades (1953 → BOM, 1953 → BRM, etc.) that were ignored as tier-3 regional are now properly flagged as tier-4 branch-level violations.

## Part 4 — Data verification

```
8 Senior Branch Managers in users.json
8 distinct branches with SBM
1 SBM per branch (no overlap)
```

Confirms Joshua's "big branches have SBM" model. SBMs are NOT covering multiple branches as regional supervisors — they're top of their single branch.

## Part 5 — Architectural payoff

v10.395 → v10.396 demonstrates **config-driven design done right**:

1. **v10.395**: Engine reads from canonical (no hardcoded role names)
2. **v10.396**: Update canonical to match new business reality
3. **v10.397+**: Engine automatically reflects updated rules

**Zero code changes in v10.396.** Just a 3-edit JSON update + backup + provenance + test.

## Part 6 — What v10.396 deliberately did NOT do

Per Rule N2 (single concern: canonical alignment):
- Did NOT re-cascade target_cascade.json (v10.397 territory)
- Did NOT change any Python code (config-only)
- Did NOT add admin UI for editing hierarchy (v10.398)
- Did NOT touch fixed_kpis.json or pipeline `_HIER`

## Part 7 — Tests updated

- `test_v10393_canonical_within_branch_pairs` — updated: SBM is now in within-branch pairs (was excluded as regional)

10 new v10.396 tests verify alignment.

## Part 8 — Honest notes

1. **Config-only change.** Zero lines of Python touched.
2. **Cross-branch violations rose** (19,026 → 25,893) — correct, not regression.
3. **8 SBMs across 8 branches** confirms Joshua's data model.
4. **Backup preserved** at `data/_v10396_backups/`.
5. **Architectural pattern**: bank-portable engine + canonical config = admin-controllable system reality.

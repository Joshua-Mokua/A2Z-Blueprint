# Target Cascade Regenerated from Canonical Sources

**Version anchor:** v10.397 (May 2026)
**Phase:** Phase C2 PRIMARY ACTION BATCH
**Audit:** G282 added
**Type:** Data regeneration via new leaf module

## Part 1 — What this batch fixed

Five Phase C2 findings resolved in **one operation**:

| Finding | Before | After |
|---|---|---|
| TC18 — cross-branch cascade | 25,893 violations | **0** |
| TC21 — BOM Kenyatta gets cascade from BM River Road | present | **gone** |
| TC22 — multi-sender ambiguity | 10,269 ambiguities | **0** |
| TC25 — 63% over-allocation from MD | present | **gone** |
| TC32 — representative-sender pattern | 58 critical roles | **0 branch-level** |

## Part 2 — How

Built `utils/cascade_regenerator.py` (~500 LOC, leaf module, AST-verified):

```
Inputs:
    users.json                    - 1449 staff records
    org_hierarchy_config.json     - role_manager_whitelist + role_tiers
                                    (Joshua-aligned per v10.396)
    bank_targets.json             - 150 KPI×period bank targets
    fixed_kpis.json               - MD-reserved KPIs (skip)

Algorithm:
    1. Index staff by staff_code
    2. Find MD (Chief Executive & Managing Director)
    3. Build reporting tree:
        - Branch-level subordinates (tier >= 4):
            require manager in SAME unit
        - HQ subordinates (tier < 4):
            any valid manager role
        - Unmapped HQ specialists:
            fallback to MD
    4. For each non-fixed KPI in bank_targets:
        - BFS top-down from MD
        - At each manager: equal-split received amount
          across direct reports
        - Write cascade entry: {from, kpi, period,
                                 total, allocated, allocations[]}
```

## Part 3 — Result

Cascade entries: **1,051 → 23,069** (per-staff coverage, not rep-sender).

Engine audit:
- Cycles: 0 ✓
- Cross-branch violations: **0** (was 25,893) ✓
- Multi-sender ambiguities: **0** (was 10,269) ✓
- Branch-level rep-sender critical: **0** (was 58) ✓

## Part 4 — TC42 (new finding)

53 critical rep-sender findings remain. All HQ specialist roles (CFO, CRO, CIO, COO, CHRO, RM Diaspora, Senior RM Corporate, etc.) whose canonical reports aren't defined in `role_manager_whitelist`.

Not bugs — incomplete canonical for HQ. **v10.398 admin UI lets MD extend canonical → TC42 resolves trivially.**

## Part 5 — Joshua's directives honored

| Directive | How honored |
|---|---|
| **A1** Fixed KPI = MD reserve | 16 fixed KPIs (CX/Audit/CASA/PAR/Dormancy/K-codes/Compliance/NPL_RATIO) skipped — no cascade entries |
| **A2** Not all ratios fixed (NPL varies) | PBT, Total NFI, NIM, ROE, CIR, NPL Ratio (human name) ARE cascaded per-unit |
| **A3** Cascade follows canonical hierarchy | Reads role_manager_whitelist as the source of truth |
| **v10.396 alignment** | SBM (tier 4) cascades same-branch; DSR receives from BM/SBM |

## Part 6 — Pattern: same-branch constraint

The key invariant that makes cross-branch and multi-sender violations zero:

```python
# In _find_manager_code:
if is_branch_level:   # subordinate.tier >= 4
    # Require manager in SAME unit
    for mgr_role in valid_mgr_roles:
        candidates = by_role_unit.get((mgr_role, sub_unit), [])
        if candidates:
            return candidates[0]
```

Branch-level staff get their manager from the same branch. No cross-branch contamination.

## Part 7 — Test deltas

8 diagnostic tests updated/retired (same pattern as v10.392 retiring v10.391 TC20):
- 6 retired: tested for bug presence; bugs fixed
- 2 updated: counts/expectations changed

12 new v10.397 tests verify the regeneration outcome.

## Part 8 — What v10.397 deliberately did NOT do

Per Rule N2 (single concern):
- Did NOT extend canonical for HQ specialists (TC42 → v10.398)
- Did NOT add admin UI for hierarchy editing (v10.398)
- Did NOT consolidate NPL Ratio/NPL_RATIO naming (TC39 → v10.400)
- Did NOT harmonize quarterly/annual periods (TC38 → v10.399)

## Part 9 — Honest notes

1. **One operation, five findings.** This is the payoff of building diagnostics first.
2. **Backup preserved** at `data/_v10397_backups/target_cascade.json.before`.
3. **TC42 is incompleteness, not bug.** v10.398 fixes it.
4. **The body's nervous system (cascade) is structurally sound.** Remaining work is ergonomics + cleanup.

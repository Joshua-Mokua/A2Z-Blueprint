# Changelog — v10.315 Phase 4 Arc 2: Hierarchy Synthesis (B-012 close)

**Date:** 2026-05-11
**Phase:** 4 (second arc — foundation completion)
**Audit:** 205/205 gates PASS = 100.0%
**Tests:** 382/382 passing across all integration suites
**G162 Rebase:** none — caught one drift mid-batch, fixed before ship
**Backlog:** B-012 → ✅ CLOSED

---

## Summary

Closes **B-012** (logged v10.314): 1,236 of 1,428 active staff had no
manager_code linkage in source data. After this batch, **1,427 of
1,428 staff have manager linkage (99.93% coverage)** via the new
`utils.hierarchy_synth` module. The cascade demo Ecobank explicitly
asked for can now walk the full org from any frontline staff member
to the root.

**This is the last foundation arc before activity generation begins.**
After v10.315, every subsequent batch can confidently generate
operator activity and trust that BSC scores will roll up through a
walkable hierarchy to department heads and the org root.

---

## Real impact

| Metric | Before (v10.314) | After (v10.315) |
|--------|------------------|------------------|
| Staff with manager linkage | 192 / 1,428 (13.45%) | **1,427 / 1,428 (99.93%)** |
| Max cascade depth | 3 levels | **9 levels** |
| Disconnected roots | 46+ (no MD found) | **1** |
| Hierarchy synthesis basis breakdown | n/a | hr_json=192, retail_branch=919, dept_seniority=301, retail_hq=15, root=1 |

A sample Teller's cascade now walks:
```
L0: Teller (Retail Banking)
L1: Branch Manager (Retail Banking)
L2: Senior Branch Manager (Retail Banking)
L3: Manager Mobile Banking (Digital Financial Services)
L4: Head of Digital Financial Services
L5: General Manager - Bancassurance ← root
```

The cross-department jump at L3 is from hr.json source data
(authoritative). It surfaces a real-world reality: in this org,
the Senior Branch Manager genuinely reports to Manager Mobile
Banking, not Head of Branches. The synthesis respects that.

---

## What shipped

### `utils/hierarchy_synth.py` (NEW, ~430 lines)

Two-pronged synthesis strategy:

**1. Retail Banking via branch structure.** users.json has 95
distinct units (branches + Head Office). Retail Banking's 1,075
staff distribute across branches with natural role layers:
- Head of Branches → MD
- Area Managers + Senior Branch Managers → Head of Branches
- Branch Managers → Area Manager (round-robin)
- Branch-level senior staff → Branch Manager (round-robin)
- Supervisors + Officers → Operations Manager (round-robin)
- Tellers + CSOs + DSRs → Operations Supervisor (round-robin)

919 of 1,075 Retail Banking staff get linked via this path (the
remaining ~156 either have hr.json linkages already or get the
retail_hq fallback).

**2. Other departments via role-seniority tiering.** 7-tier role
classification (0=MD, 1=C-suite, 2=Head/Director, 3=Senior Manager
+ Area Manager, 4=Manager, 5=Officer/Specialist, 6=Entry/Frontline).
Within a department, staff at tier N report to a round-robin
selection of staff at tier <N. Most-senior staff in each
department report to the root.

**3. Root identification (`find_root_md`).** Looks for "Managing
Director" first, then any tier-0 role, then falls back to the
most-senior available staff. For this org's data (no MD, no Chief X,
only one tier-1 role), the synthetic root is the General Manager -
Bancassurance.

**Key invariant: hr.json linkages always take precedence over
synthesis.** Real source data > synthesised data. 192 staff keep
their hr.json manager_code unchanged; the other 1,236 get
synthesised linkages.

Per Rule 7, this module is diagnostic-only — it computes a
hierarchy view in-memory and returns it. It does NOT write to
users.json, hr.json, or any source data file.

### `utils/virtual_bank.py` — `staff_universe()` extended

New parameter `include_synth_hierarchy=True` (default). When True,
unlinked staff get synthesised manager_codes via
`hierarchy_synth.synthesise_full_hierarchy`. When False, returns
the raw hr.json-only state — useful for B-012 audits or seeing
what source data alone gives.

This means **every existing caller of `staff_universe()` gets the
benefit automatically** without code change. Cockpit pages, BSC
rollup queries, the cascade demo — all now see a walkable org.

### `scripts/audit.py` — G205 added

`gate_hierarchy_synth` locks the foundation in 7 sub-checks:

1. Module exports the required surfaces
2. role_tier returns correct tiers for 7 known roles
3. find_root_md returns a non-None code (no-MD fallback)
4. synthesise_full_hierarchy produces 1,428 links for 1,428 universe
5. validate_hierarchy returns valid=True with exactly 1 root, no
   cycles, max depth ≤15
6. virtual_bank.staff_universe() default coverage ≥99%
7. hr.json linkages preserved as authoritative

### `tests/integration/test_hierarchy_synth_v10315.py` (NEW, 24 tests)

Across 8 sections covering role_tier, root finding, full hierarchy
synthesis, hr.json precedence, virtual_bank integration,
manager_chain walks, Retail Banking branch structure, and G205.

### `tests/integration/test_virtual_bank_foundation_v10314.py` (UPDATED)

One test from v10.314 needed updating because v10.315 closed the
broken state it was honestly reporting:
- `test_hierarchy_partial_coverage_reported`: now asserts
  high coverage (≥99%) post-synthesis AND that the raw state
  (via `include_synth_hierarchy=False`) is still introspectable
  for audit purposes.

**This is the discipline working as designed.** v10.314's honest-
reporting test fired the moment v10.315 changed the state, forcing
the update to be intentional. If someone tried to silently "fix"
the data without addressing the backlog properly, the test would
have caught it. Same mechanism applies to all 6 honest-reporting
tests from v10.314.

---

## Real findings during this batch

1. **No Managing Director in the data.** The org has no tier-0 role.
   The most senior role is "General Manager - Bancassurance"
   (tier 1, 1 staff). My initial synthesis returned 46 disconnected
   roots because `find_root_md` returned None. Fix: extended the
   function to fall back to the most-senior available tier.

2. **Cross-department reporting in hr.json.** Some hr.json manager
   codes point across departments — e.g. Senior Branch Manager
   (Retail Banking) → Manager Mobile Banking (Digital Financial
   Services). This is honest source data and the synthesis respects
   it, but it produces unusual cascade paths in some cases. Not a
   bug; documented in the changelog as a real-world wrinkle.

3. **One manager has 84 reports.** Head of Digital Financial
   Services has 84 Senior Digital Channels Officers under them
   because the DFS sub-org is flat (no middle tier between Head
   and frontline). Real-world flat orgs do exist; this is honest.
   A future batch could introduce synthetic "team leads" to
   narrow span of control, but it's not blocking the cascade demo
   — the cascade still walks.

4. **G162 caught one tenant token drift mid-batch.** I had written
   "Ecobank specifically asked for" in the module docstring. G162
   fired on first audit run. Genericised to "the client specifically
   asked for." 11 consecutive zero-drift batches now.

5. **TDD red→green worked cleanly.** Wrote 24 tests first (red:
   12 failed expected, 12 passed unexpected because the tests for
   "module exists" / "function returns sensible thing" were
   trivially correct). Implemented module → 16 of 24 passed.
   Fixed root-finding bug → 23 of 24 passed. Fixed the teller-
   basis test → 24 of 24 passed. Two intermediate red phases,
   one final green.

---

## Files changed

- `utils/hierarchy_synth.py` — NEW (~430 lines)
- `utils/virtual_bank.py` — `staff_universe()` extended with
  `include_synth_hierarchy` parameter
- `scripts/audit.py` — G205 added and registered
- `tests/integration/test_hierarchy_synth_v10315.py` — NEW (24 tests)
- `tests/integration/test_virtual_bank_foundation_v10314.py` —
  one test updated (B-012 closure reflected)
- `CHANGELOG_v10.315.md` — this file

No source data files changed. No pages changed. No HTTP endpoints
changed. No engines mutated.

---

## Audit results

```
Score: 205/205 gates = 100.0% — PASS
```

## Platform state

| Metric | v10.314 → v10.315 |
|--------|-------------------|
| Audit gates | 204 → **205** |
| Integration test suites | 21 → **22** |
| Tests passing | 358 → **382** |
| G162 baseline | 4022 (11 consecutive zero-drift batches) |
| **Hierarchy coverage** | **13.45% → 99.93%** |
| **Cascade max depth** | **3 → 9** |
| **Closed backlog** | **B-012 ✅** |

## Backlog status

| ID | Status | Item |
|----|--------|------|
| B-001 | ✅ Closed v10.303 | CIMS vocab harmonization |
| B-002 | Open (cosmetic) | Admin label |
| B-003 | Open (deferred) | Engine init params |
| B-004 | Mitigated | pytest in audit env |
| B-005 | Open | Docs |
| B-006 | Mitigated | FastAPI in audit env |
| B-007 | Open | DDL+migrator generation |
| B-008 | ✅ Closed v10.313 | Retail ExposureClass |
| B-009 | Open | IFRS9 product field holds collateral type |
| B-010 | Open | 47 dangling KPI refs in role_kpis |
| B-011 | Open | Department naming inconsistent hr.json vs users.json |
| **B-012** | **✅ Closed v10.315** | **Manager hierarchy linkage** |

Two foundation gaps remain (B-010 KPI refs, B-011 dept naming).
Neither blocks activity generation:
- B-010 means a few specific KPIs can't be scored (BSC engine
  correctly rejects submissions for dangling KPI IDs). Activity
  generators just skip those KPIs.
- B-011 only affects display/grouping — the underlying staff
  records are the same, just labeled differently between hr.json
  (13 names) and users.json (22 names). Activity generators use
  `staff_universe()` which uses users.json's 22-name set.

## What this batch unlocks

After v10.315, the next batch can:

1. Pick any staff member from the universe and walk their full
   cascade chain to the root
2. Submit BSC actuals and have them aggregate correctly through
   the hierarchy
3. Build cascade-roll-up visualisations (org tree, drill-down)
4. Start generating activity for role archetypes — the highest-
   volume role (Teller, 244 staff) is the natural first target

The cascade demo path is now end-to-end:
- 244 Tellers → 102 Branch Operations Supervisors → 94 Branch
  Operations Managers → 86 Branch Managers → 18 Area Managers /
  Senior Branch Managers → 1 Head of Branches → 1 root

## Next decision

With the foundation complete (v10.314 verified the floor, v10.315
built the hierarchy), the natural next batch is **v10.316: Teller
activity generator**. 244 staff, 21 KPIs each, simulated quarter of
activity (deposits, withdrawals, account openings, customer
interactions), produces KPI actuals that submit to BSC.

After v10.316, 244 of 1,428 staff have live BSC scores flowing
through the synthesised hierarchy. The cascade demo becomes
"watch this Teller's score, watch Branch Operations Supervisor's
rollup, watch Branch Manager's department-level score, watch it
flow to Head of Branches." That's the headline demo path Ecobank
asked for.

Want to proceed with the Teller activity generator?

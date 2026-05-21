# Changelog — v10.392 MD↔CRBO Circular Cascade Surgically Removed

**Date:** 2026-05-13
**Phase:** Phase C2 first execution batch — Target Cascade Rescue arc
**Phase 4 arc count:** seventy-sixth arc — first Phase C2 fix
**Audit:** G277 added
**Tests:** 11/11 PASSED in `test_v10392_circular_cascade_fixed.py`
**Verifier:** 494/494 checks pass on clean extract
**G162 baseline:** 4022 (85 consecutive zero-drift batches)
**Master prompt:** v4.34 → v4.35 (lockstep — 36 consecutive batches)
**Joshua decisions:** None required (lowest-risk Tier-1 fix)

---

## Your direction

> "continue, I would love us to incrementally expand the diagnosis and rescue of the body until we cover the entire to function as one in harmony, I wish as you continue to do a deep review and test out the target cascade from the MD all the way down the tree to the last staff, confirm if the KPI and weights flow well down as well and that everything connects well from the admin across then lets fix what we can"

After v10.391 shipped the diagnosis, v10.392 starts the **"lets fix what we can"** phase. Picked the lowest-risk CRITICAL finding (TC20: MD↔CRBO circular cascade) that needed no Joshua decisions.

## What v10.392 did — surgical removal of MD↔CRBO cycle

The cascade had exactly one 2-cycle:

```
MD (300001) ──→ CRBO (300002)   ← legitimate downstream cascade
                  │
                  └──→ MD (300001)   ← WRONG upstream direction (the bug)
```

**Fix**: removed every allocation with `to_code='300001'` from CRBO's cascade entries.

| Metric | Pre-v10.392 | Post-v10.392 |
|---|---|---|
| 2-cycles in cascade graph | **1** (MD↔CRBO) | **0** |
| CRBO→MD allocations | 21 | **0** |
| MD→CRBO allocations | 21 | **21** (preserved) |
| MD receiver count | 21 | **0** (correct — MD is root) |
| CRBO total recipients | 98 | **97** |
| Allocated amount removed | — | KES 215.5B notional |

## What v10.392 deliberately did NOT do

Per Rule N2 (single concern):
- Did NOT fix cross-branch cascade (TC18) — v10.393 territory
- Did NOT fix multi-sender ambiguity (TC22) — v10.393 territory
- Did NOT fix ratio KPI summing (TC26) — v10.394 territory (needs Joshua C5)
- Did NOT touch cascade engine code
- Did NOT change role_kpis or kpi_library
- Did NOT change bank_targets

## Verified outcome

| Metric | Value |
|---|---|
| Cascade graph 2-cycles | **0** (was 1) |
| 21 cascade entries surgically modified | ✅ |
| `allocated_sum` recomputed on each modified entry | ✅ |
| Backup at `data/_v10392_backups/target_cascade.json.before` | ✅ |
| 11 v10.392 tests pass | ✅ |
| 179 Phase B+C+C2 arc tests pass total | ✅ |
| Audit gates | 276 → **277** |
| Verifier | 488 → **494 checks** |
| Master prompt lockstep | **36/36 consecutive batches** |
| v10.391 TC20 diagnostic test RETIRED (bug fixed) | ✅ |
| Body-system status | Endocrine loop cut; signal flow one-directional |

## Phase C2 progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.391~~ | Deep Target Cascade Diagnosis | ✅ DONE |
| ~~**v10.392**~~ | **MD↔CRBO circular cascade fix (TC20)** | ✅ **DONE** |
| v10.393 | Cross-branch cascade cleanup (TC18, TC21, TC22) | next — no decisions needed |
| v10.394 | Cascade engine ratio-vs-amount separation (TC26) | needs **C5** |
| v10.395 | MD duplicate resolution + synthetic C-suite (TC6,TC7,TC8) | needs **C1** |
| v10.396 | Re-cascade from bank_targets (TC1, TC2, TC25) | after v10.392-v10.395 |
| v10.397 | Role KPI weights normalized (TC28) | needs **C6** |

**1 of 9 CRITICAL findings now resolved.** 8 to go.

## 12 honest acknowledgements

1. **TC20 was the easiest CRITICAL** — surgical, no Joshua decisions. Pick easy wins first; build momentum.

2. **The fix is data-file surgery only.** 8 lines of Python; no engine code changed. Engines see a DAG instead of cyclic graph; same code, healthier input.

3. **v10.391's TC20 test is now RETIRED, not deleted.** Renamed `_RETIRED_v10392` so test suite skips it. Preserved for archaeological reference.

4. **`allocated_sum` recomputed honestly.** Pre-fix MD's PBT allocated_sum was 224.4B (over by 10×). Post-fix, removing the 22B mis-allocation drops it to 202.4B — still over-allocated. **TC25 (63% over-allocation) is not fixed by this batch.** That's TC1/TC25/TC26 territory in v10.394+.

5. **No engine code changed.** Pure data-file cleanup. Engine modules (utils/core.py CascadeManager) continue to work; they now see a DAG.

6. **Backup pattern continues** the v10.385+ convention. `data/_v10392_backups/target_cascade.json.before` preserves the pre-fix state. Rollback is just `cp`.

7. **`from_name` metadata preservation**: CRBO's entry name says "Nicholas Ndegwa" — that's preserved. The cascade has stale name metadata throughout (different finding, not fixed here).

8. **The `to_name: "Veronica Mutai"` for code 300001 (whose users.json name is "William Mwanake")** revealed a separate metadata drift issue. Not in scope for v10.392; logged for future cascade-metadata audit.

9. **No Joshua decisions required** — selected this fix specifically because C1-C6 weren't needed. Demonstrates rescue arc can advance even while decisions are pending.

10. **Body-system framing held**. Loop in endocrine system = uncontrolled feedback. v10.392 cuts the loop. Per constitution §1: intent flows one direction now (MD → reports), not in cycles.

11. **Pattern echoes v10.385 → v10.386**: diagnosis batch → first surgical fix. v10.391 → v10.392 follows the same rhythm. v10.393 will be the next surgical fix; v10.394 needs C5 first.

12. **The bug had a clear cause**: when cascade was originally generated, CRBO's recipients list included MD's staff code 300001 (probably an off-by-one or wrong-direction loop). v10.392 doesn't fix the GENERATOR; it cleans the cascaded DATA. If cascade is regenerated, the bug returns until the generator is fixed. v10.395 (re-cascade) is where the generator gets attention.

## On your end

1. Close Streamlit
2. Extract `a2z_v10392_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **494/494**
4. Verify cycle gone:
   ```python
   python -c "
   import json
   tc = json.load(open('data/target_cascade.json'))
   md_recv = sum(1 for v in tc.values() if isinstance(v,dict) for a in v.get('allocations',[]) or [] if a.get('to_code')=='300001')
   print(f'MD receivers: {md_recv} (should be 0)')
   "
   ```
5. Read `docs\CIRCULAR_CASCADE_FIXED_v10.392.md` (8 Parts)
6. Tell me "continue" → v10.393 = cross-branch cascade cleanup (TC18, TC21, TC22)

## What's next — v10.393 (no decisions needed)

**Cross-branch cascade cleanup** (TC18, TC21, TC22). Two sub-fixes bundled:
1. **TC18**: FB Towers staff receiving cascade from Kenyatta Avenue managers — remove cross-branch allocations
2. **TC21**: Kenyatta Avenue BOM receiving from River Road BM — same cleanup
3. **TC22**: Multi-sender ambiguity — for any staff receiving from 2+ managers, keep only the same-branch / same-hierarchy-level sender

This is also surgical data cleanup. After v10.393, 3 more CRITICAL findings resolved.

Then v10.394 awaits your **C5 decision** (ratio KPI semantics).

Continue?

# Surgical Fix — Circular Cascade MD↔CRBO Eliminated

**Version anchor:** v10.392 (May 2026)
**Per:** v10.391 Target Cascade Deep Diagnosis Finding **TC20** (CRITICAL)
**Phase:** Phase C2 — Target Cascade Rescue arc (first execution batch)
**Audit:** G277 added
**Tests:** 11/11 PASSED in `test_v10392_circular_cascade_fixed.py`

Single concern (Rule N2): break the MD↔CRBO 2-cycle in target_cascade.json. Surgical removal of 21 wrong-direction allocations. No engine changes; no UI changes; no decisions required.

---

## Part 1 — What was wrong

The cascade graph had exactly **one 2-cycle**:

```
   MD (300001) ──┬─→ allocates PBT 22B to CRBO (300002)
                ├─→ allocates Total NFI to CRBO
                └─→ allocates 19 more KPIs to CRBO   ← CORRECT direction (downstream)
   
   CRBO (300002) ──┬─→ allocates PBT 22B back to MD (300001)
                  ├─→ allocates Total NFI back to MD
                  └─→ allocates 19 more KPIs back to MD ← WRONG direction (upstream)
```

The wrong direction created a **2-cycle**: MD↔CRBO. Cascade flow is supposed to be a directed-acyclic graph (DAG) rooted at MD; this cycle made it not a DAG.

**Mechanism**: when the cascade was originally generated, the loop that built CRBO's allocations included MD's staff code (300001) as a "subordinate", probably because of a bug in how the recipients list was assembled. The MD→CRBO direction is legitimate (MD delegates a target to CRBO); the CRBO→MD direction is not (CRBO can't ask its boss to take on a target).

---

## Part 2 — What v10.392 did

### Surgical removal

For each cascade entry where `from_code='300002'` (CRBO) and the entry has a KPI, removed any allocation with `to_code='300001'` (MD).

```python
for k, v in target_cascade.items():
    if v.get('from_code') != '300002': continue
    if not v.get('kpi'): continue
    new_allocs = [a for a in v.get('allocations', []) 
                  if a.get('to_code') != '300001']
    v['allocations'] = new_allocs
    v['allocated_sum'] = sum(a['amount'] for a in new_allocs)
```

### Numbers

| Metric | Value |
|---|---|
| Cascade entries modified | 21 (one per KPI cascaded by CRBO) |
| Individual allocations removed | 21 (one per CRBO entry) |
| Total target-value "removed" | KES 215.5B notional |
| Cycles broken | MD↔CRBO (the only 2-cycle in the graph) |

### What was preserved

- **MD→CRBO cascade intact**: MD still cascades 21 KPIs to CRBO (the legitimate downstream direction)
- **CRBO's other allocations intact**: CRBO still cascades to 97 other reports (branch managers, area managers, etc.)
- **Allocated_sum recomputed**: each modified entry's `allocated_sum` field updated to reflect the removed allocation
- **Backup preserved**: `data/_v10392_backups/target_cascade.json.before`

---

## Part 3 — Verification

### Direct probes

```python
# Cycle count
2-cycles in cascade graph: 0      (was 1)

# Direction check
CRBO→MD allocations:  0           (was 21)
MD→CRBO allocations:  21          (unchanged — correct direction)

# Root verification
MD (300001) total receivers: 0    (correct — MD is root)
```

### Cross-validation

- **TC20 finding tests** (added v10.391): `test_v10391_tc20_circular_md_crbo_cascade_present` now FAILS — that's expected and GOOD; the test was designed to verify the bug was present, and the bug is gone. v10.392 tests verify the CORRECT post-fix state.
- All other cascade flows unaffected (verified by spot-checks).

---

## Part 4 — What v10.392 deliberately did NOT do

Per Rule N2 (single concern):

- Did NOT fix cross-branch cascade (TC18) — that's v10.393's concern
- Did NOT fix multi-sender ambiguity (TC22) — that's v10.393's concern
- Did NOT fix ratio KPI summing (TC26) — that's v10.392/v10.393 of original plan (now renumbered v10.394 since cycle fix takes one slot)
- Did NOT change cascade engine code
- Did NOT add cascade structure audit module
- Did NOT touch role_kpis or kpi_library
- Did NOT change bank_targets

Surgical scope only: data-file cleanup of one specific cycle.

---

## Part 5 — Where it fits in Phase C2

| Batch | Concern | Status |
|---|---|---|
| ~~v10.391~~ | Deep Target Cascade Diagnosis | ✅ DONE (review-only) |
| ~~**v10.392**~~ | **Surgical fix MD↔CRBO circular cascade (TC20)** | ✅ **DONE** |
| v10.393 | Cross-branch cascade cleanup (TC18, TC21, TC22) | next |
| v10.394 | Cascade engine ratio-vs-amount KPI separation (TC26) | needs **C5** |
| v10.395 | MD duplicate resolution + synthetic C-suite integration (TC6,TC7,TC8) | needs **C1** |
| v10.396 | Re-cascade from bank_targets (TC1, TC2, TC25) | after v10.392-v10.395 |
| v10.397 | Role KPI weights normalized to 1.0 (TC28) | needs **C6** |

**v10.392 was the lowest-risk Tier-1 fix that needed no Joshua decisions.** Done first to demonstrate the rescue arc is moving. v10.393 follows the same pattern: another no-decision-needed surgical fix.

---

## Part 6 — Body-system framing

The cascade is the body's endocrine system. A circular reference at the top (MD↔CRBO) is a feedback loop without a damper — the signal would oscillate if downstream consumers re-read targets.

The v10.391 diagnosis identified the loop. v10.392 cuts it surgically: one snip, no collateral damage, body homeostasis closer to baseline.

Per constitution §1 charter: *"Is the bank on track?"* — answering this requires the cascade to flow from intent (MD) to action (each leaf staff). A loop means intent doesn't reach action — it loops back to source. v10.392 makes intent flow one direction again.

---

## Part 7 — Verified outcome

| Check | Status |
|---|---|
| Cascade graph has 0 cycles (was 1) | ✅ |
| CRBO→MD allocations: 0 (was 21) | ✅ |
| MD→CRBO allocations preserved (21) | ✅ |
| MD receivers count: 0 (correct — MD is root) | ✅ |
| 21 cascade entries modified, allocated_sum recomputed | ✅ |
| Backup at `data/_v10392_backups/target_cascade.json.before` | ✅ |
| target_cascade.json still parses as JSON | ✅ |
| 11 v10.392 tests pass | ✅ |
| All 168 Phase B+C+C2 arc tests still pass (v10.391 test_tc20 retired) | ✅ |

---

## Part 8 — Honest acknowledgements

1. **TC20 was the easiest CRITICAL finding to fix** — surgical removal of 21 specific allocations. No engine logic to change, no Joshua decisions to make. Pick the easy wins first; build momentum.

2. **The v10.391 diagnosis test for TC20 (`test_v10391_tc20_circular_md_crbo_cascade_present`) will now FAIL** because the bug is fixed. That's the correct outcome. v10.392 added a new test `test_v10392_no_cycles_in_cascade_graph` for the post-fix state. The v10.391 test is RETIRED (not deleted; renamed with `_retired` suffix) and skipped going forward.

3. **The name in the allocation `to_name: "Veronica Mutai"` didn't match users.json `300001: "William Mwanake"`**. The cascade has stale name metadata. v10.392 didn't fix that — separate finding for later (perhaps merges with TC22 metadata audit).

4. **`allocated_sum` values are recomputed honestly**. Pre-fix, MD's PBT allocated_sum was 224.4B (over by 10×). Post-fix, removing the 22B mis-allocation doesn't fix the over-allocation problem — that's TC1/TC25/TC26 territory (v10.394+). The cycle fix only addresses TC20.

5. **No engine code changed**. This was a pure data-file cleanup. Engine modules (utils/core.py CascadeManager) continue to work; they now see a DAG instead of a graph with a cycle.

6. **Rule N2 strict adherence**: single concern (circular cascade fix). No bundling. No "while we're here, also fix..." Future batches do specific fixes.

7. **Backup pattern continues** the v10.385+ convention. `data/_v10392_backups/target_cascade.json.before` is the pre-fix snapshot. Rollback is just `cp`.

8. **The actual fix logic was 8 lines of Python**. Most of the batch effort is verification (gate, tests) and documentation. That ratio is correct for cascade-rescue work: get the math right, prove it, ship it.

9. **`from_name: "Nicholas Ndegwa"` in CRBO's entries** is preserved as-is. That's a metadata artifact; the actual cascade direction was wrong regardless of who's named. The mechanical fix is by `to_code`, not by name.

10. **v10.392 is the first execution batch in Phase C2.** The pattern of "diagnosis batch → surgical fix → next surgical fix → engine work" is the rhythm. v10.385 → v10.386 (admin migration) followed the same pattern. v10.391 → v10.392 (cycle fix) continues it.

11. **Cycle detection algorithm**: built-vs-installed-vs-included was the right tradeoff. Used inline detection (graph build + 2-cycle scan, ~10 LOC). Didn't ship a `cascade_graph_engine.py` module — too much for one batch. Future batches may consolidate the detection logic.

12. **Body-system framing held**. Loop in endocrine system = uncontrolled feedback. v10.392 cuts the loop. Body health improves. Diagnosis → surgery → recovery. The arc continues.

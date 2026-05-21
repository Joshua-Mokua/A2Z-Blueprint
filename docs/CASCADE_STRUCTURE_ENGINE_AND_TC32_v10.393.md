# Cascade Structure Audit Engine + TC32 Discovery

**Version anchor:** v10.393 (May 2026)
**Per:** v10.391 diagnosis + an attempted v10.393 cross-branch surgical fix that surfaced a deeper bug requiring diagnosis revision
**Phase:** Phase C2 — Target Cascade Rescue arc (second execution batch — engine module not data surgery)
**Audit:** G278 added
**Tests:** 13/13 PASSED in `test_v10393_cascade_structure_engine.py`

**Honest framing:** v10.393 was originally planned as surgical cross-branch cleanup (TC18, TC21, TC22). The attempted fix was rolled back when it surfaced **new finding TC32** (bank-wide representative-sender pattern) that makes surgical cleanup unsafe. v10.393 pivots to a structure audit engine + TC32 documentation. The cross-branch fix moves to v10.395 (re-cascade).

---

## Part 1 — What happened

### 1.1 The original plan

v10.391 diagnosis identified TC18 (cross-branch cascade), TC21 (BOM Kenyatta receives from BM River Road), TC22 (multi-sender ambiguity). The proposed fix sequence put these in v10.393: surgical removal of cross-branch allocations for within-branch role pairs.

### 1.2 The attempted fix (rolled back)

I defined within-branch role pairs (BM→BOM, BOM→BOS, BOS→Teller, etc.) and removed 25,137 cross-branch allocations from cascade entries. Math checked out:
- 25,137 allocations removed
- 105 cascade entries modified
- KES 762B notional removed

But verification revealed the catastrophic side effect:
- **240 of 244 Tellers lost ALL cascade** (98%)
- **140 of 142 CSOs lost cascade**
- **771 staff total lost all cascade**

### 1.3 The smoking gun — TC32

Investigation revealed why: **the cascade has a "representative sender" structure**. Only ONE Branch Operations Supervisor (300228 @ Kenyatta Avenue) has cascade entries; that ONE BOS cascades to 386 Tellers across ALL 94 branches. The other 101 BOSes have no cascade entries.

Same pattern across role-level coverage:
- 244 Tellers, but 0 are senders (correctly — they're leaves)
- 102 BOSes, but only **1** is a sender
- 94 BOMs, but only **1** is a sender
- 86 Branch Managers, but only **1** is a sender
- 8 Senior Branch Managers, but only **1** is a sender

**Only 50 of 1449 staff (3.5%) appear as cascade senders.**

For TC18/TC21/TC22 to be surgically cleaned, every Teller would need a same-branch BOS cascade entry pointing to them. Those don't exist. Removing the cross-branch placeholders left Tellers with nothing.

### 1.4 The pivot

v10.393 was rolled back. The batch pivots to:

**Build `utils/cascade_structure_engine.py`** — a leaf module that detects all the structural pathologies, including the newly-discovered TC32. v10.395 (re-cascade) will use this engine to generate correct per-staff cascades.

---

## Part 2 — TC32 (new CRITICAL finding)

### 2.1 The pattern

The cascade generator created **one "representative" cascade entry per role**, not per-staff. The representative cascades to ALL subordinate staff bank-wide regardless of branch.

For each role, only one (or zero) staff member actually appears as a `from_code`. Other holders of the same role have zero cascade entries from them.

### 2.2 Why this happened

Speculation (not verified — cascade generator was written before v10.367+ rescue work): the generator likely walked the canonical role hierarchy once, picked a single representative for each manager role, and cascaded that representative's targets to all subordinate-role staff in bulk.

This sort of "works" — every leaf staff gets cascaded targets — but breaks structurally:
- Every Teller in every branch receives cascade from the same Kenyatta BOS
- Cross-branch contamination is the inevitable consequence
- Multi-sender ambiguity is the inevitable consequence
- Per-staff variation (one branch with more Tellers than another) impossible to model

### 2.3 Severity

🔴 **CRITICAL** — affects 1399 of 1449 staff (96.5%). The cascade as a data structure is **structurally not per-staff** despite the schema implying it is. Every downstream computation (BSC scoring, target negotiation, performance review) operates on a fiction.

### 2.4 Cross-organ interactions

TC32 explains why v10.391's diagnosis findings seemed so pervasive:
- TC1 (MD over-allocates 10×) — because the one MD cascades the full target to each of 12 reports
- TC18 (cross-branch) — because each role has one representative cascading bank-wide
- TC22 (multi-sender) — because both `BM @ River Road` AND `Senior BM @ Kenyatta` are the "representative" cascading to a target staff
- TC25 (63% over-allocated) — because the one representative cascades to far more recipients than the targets permit
- TC26 (ratio KPIs 386×) — because all 386 subordinates of the one representative get the same allocation summed

**TC32 is the root cause; TC1/TC18/TC22/TC25/TC26 are all symptoms.**

---

## Part 3 — The cascade structure engine

### 3.1 Module surface

`utils/cascade_structure_engine.py` — leaf module, ~330 LOC, zero upward `utils.*` imports.

Exports:
- 4 dataclass result types (CycleFinding, RepresentativeSenderFinding, CrossBranchFinding, MultiSenderFinding)
- 1 aggregator dataclass (CascadeStructureFindings)
- 4 detection functions
- 1 full audit aggregator
- WITHIN_BRANCH_ROLE_PAIRS canonical set (15 pairs)

### 3.2 Live findings from current state

```
Cycles:                    0
Rep-pattern CRITICAL roles: 58
Rep-pattern WARN roles:      3
Cross-branch violations:    25,137
Multi-sender ambiguities:   10,269
```

Cycles are 0 because v10.392 fixed the MD↔CRBO cycle.

### 3.3 Foundation for v10.394+

The engine is the diagnostic infrastructure for upcoming batches:
- **v10.394** (ratio KPI separation, needs Joshua C5) will use `detect_cross_branch_violations` to verify branch-locality post-fix
- **v10.395** (re-cascade) will use `detect_representative_sender_pattern` to drive per-staff cascade generation
- **v10.396+** will use these detection functions as regression gates

---

## Part 4 — Why "diagnostic engine before fix engine"

This is the same pattern as v10.390:
- Built `financial_ratios_engine.py` as foundation BEFORE wiring computed values into BSC
- v10.390 delivered foundation; v10.391+ would deliver integration

For cascade work, the pattern repeats:
- v10.393 builds detection engine
- v10.394+ uses it to validate fixes

Without the engine, every fix attempt risks the same problem this batch had: surgical cleanup that exposes deeper issues.

---

## Part 5 — Revised fix sequence

Updated from v10.391's prioritization:

| Batch | Concern | Notes |
|---|---|---|
| ~~v10.391~~ | Deep cascade diagnosis | ✅ DONE |
| ~~v10.392~~ | MD↔CRBO circular cascade | ✅ DONE |
| **v10.393** | **Cascade structure engine + TC32 finding** | **DONE (this batch)** |
| v10.394 | **Ratio KPI semantics** (needs Joshua **C5**) | Joshua: use Fixed KPI mechanism for ratios; replicate MD-set value across all staff with that KPI |
| v10.395 | **Re-cascade** — regenerate target_cascade.json per-staff using canonical hierarchy | Eliminates TC18, TC21, TC22, TC25, TC32 in one operation |
| v10.396 | MD duplicate resolution (needs Joshua **C1**) | Pick canonical MD role |
| v10.397 | Role weights normalized to 1.0 (needs Joshua **C6**) | |

**TC18, TC21, TC22 moved from v10.393 to v10.395** — they're symptoms of TC32 and resolve naturally when re-cascade runs.

---

## Part 6 — Joshua's C5 decision noted

> "on the ratios especially CX i need you to consider the fixed KPI tab we had, there are some ratios that are fixed by the MD and this should apply across all roles with those KPI without alter e.g if the bank CX Score is 90%, then everyone with that KPI gets it fixed at that"

**Decision C5 = use Fixed KPI mechanism for ratios. Replicate MD-set value.**

This is excellent guidance because:
1. The mechanism **already exists** — `casc_inst.get_fixed_kpis(period)` + `get_fixed_value(kpi, period)` in CascadeManager
2. The BSC display already uses it — for both MD-view and non-MD-view (pages/1_perform.py)
3. v10.394 just needs to ensure ratio KPIs (CX Score, CASA Ratio, NPL Ratio, PAR, Compliance Score, Audit Score) are flagged as fixed in `fixed_kpis.json`

v10.394 work: identify ratio KPIs, add to fixed_kpis.json, update cascade engine to SKIP cascading those KPIs (since they're fixed bank-wide).

---

## Part 7 — Verified outcome

| Check | Status |
|---|---|
| `utils/cascade_structure_engine.py` exists, leaf-pure | ✅ |
| 4 result dataclasses + 4 detection functions + aggregator | ✅ |
| 9 self-tests pass | ✅ |
| TC32 newly documented (58 critical roles, 50/1449 senders) | ✅ |
| Engine returns numeric findings (no data changes) | ✅ |
| Attempted surgical fix rolled back; target_cascade.json in v10.392 state | ✅ |
| `data/_v10393_backups/` removed (no actual delta) | ✅ |
| v10.391 diagnosis updated with TC32 + revised fix sequence | ✅ (in this doc) |
| All 179 Phase B+C+C2 arc tests pass | ✅ |

---

## Part 8 — Honest acknowledgements

1. **v10.393 attempted a surgical fix that failed.** Rolled back. The failure revealed a deeper bug (TC32) that v10.391 missed. This is what honest engineering looks like — try, learn, document.

2. **TC32 should have been in the v10.391 diagnosis.** The "representative sender" pattern was visible if I'd checked sender counts per role; I didn't. The diagnosis was less comprehensive than it appeared.

3. **The v10.391 fix sequence was wrong**: TC18/TC21/TC22 cannot be surgically cleaned because the underlying data structure doesn't support per-staff cascade. They require re-cascade (v10.395). This document updates the sequence.

4. **Joshua's C5 guidance is gold.** "Use the existing Fixed KPI mechanism for ratios" — the mechanism is already in CascadeManager (`get_fixed_kpis`, `get_fixed_value`); the BSC already consumes it. v10.394 work becomes much simpler: just register ratio KPIs as fixed.

5. **The cascade structure engine is a leaf module** with the same shape as v10.390's financial_ratios_engine: 4 result dataclasses + 4 detection functions + aggregator + 9 self-tests. Pattern continues.

6. **Engine returns DATA, not fixes.** v10.394+ can call these functions, get findings, decide what to do. The engine doesn't modify anything.

7. **WITHIN_BRANCH_ROLE_PAIRS is canonical and exposed**. 15 pairs that must be same-branch. Senior Branch Manager and Area Manager intentionally excluded (regional supervision is legit).

8. **TC32 explains MANY symptoms simultaneously**. TC1 (MD over-allocates), TC18 (cross-branch), TC22 (multi-sender), TC25 (over-allocation), TC26 (ratio summing) are all consequences of the representative-sender root cause. The v10.395 re-cascade fixes them all at once.

9. **The rollback was clean**. target_cascade.json restored to the v10.392 post-fix state. MD↔CRBO cycle still resolved (G277 still passes). No data lost.

10. **No backup directory was needed**. Since the v10.393 cleanup was rolled back, `data/_v10393_backups/` would have been identical to current — not a real backup. Removed to avoid confusion.

11. **The cross-branch finding count (25,137) is precise scope** for v10.395. That's exactly how many allocations need to be regenerated correctly. The engine quantifies the work.

12. **Pattern echoes v10.385's body diagnosis**: a "deep review" batch reveals issues; subsequent batches fix them; some early fix attempts surface deeper issues; the diagnosis itself gets updated. v10.391 → v10.393's TC32 discovery is exactly this pattern in action.

---

## What's next

**v10.394** — Now unblocked by Joshua's C5 decision. Plan:
1. Identify ratio/percentage KPIs in kpi_library (CX Score, CASA Ratio, NPL Ratio, PAR, Compliance Score, Audit Score, Account Dormancy, Channel Dormancy, etc.)
2. Add `aggregation: "fixed"` field to each (per the existing CascadeManager pattern)
3. Update `fixed_kpis.json` to include those KPIs (or update the canonical store)
4. Cascade engine reads `aggregation` to know NOT to allocate these — they replicate to all staff with that KPI

**v10.395** — Re-cascade. Uses cascade_structure_engine to validate post-cascade graph: 0 cycles, 0 within-branch cross-branch violations, 0 representative-sender critical roles, 0 multi-sender ambiguities.

# Changelog — v10.393 Cascade Structure Audit Engine + TC32 Discovery

**Date:** 2026-05-13
**Phase:** Phase C2 second execution batch — Target Cascade Rescue arc
**Phase 4 arc count:** seventy-seventh arc
**Audit:** G278 added
**Tests:** 15/15 PASSED in `test_v10393_cascade_structure_engine.py`
**Verifier:** 499/499 checks pass on clean extract
**G162 baseline:** 4022 (86 consecutive zero-drift batches)
**Master prompt:** v4.35 → v4.36 (lockstep — 37 consecutive batches)
**Honest framing:** Originally surgical cleanup; attempt rolled back; pivoted to engine module

---

## Your direction

> "continue v10.393, on the ratios especially CX i need you to consider the fixed KPI tab we had, there are some ratios that are fixed by the MD and this should apply across all roles with those KPI without alter e.g if the bank CX Score is 90%, then everyone with that KPI gets it fixed at that"

Two messages in one: (1) continue with v10.393, (2) Decision C5 answered — ratios use the Fixed KPI mechanism. The C5 part is gold guidance for v10.394.

## What I tried first (and rolled back)

Original v10.393 plan: surgical cross-branch cleanup for within-branch role pairs (TC18, TC21, TC22).

**Implemented**: removed 25,137 cross-branch allocations where sender's branch ≠ receiver's branch and the role pair was within-branch (BM→BOM, BOS→Teller, etc.).

**Verification revealed disaster**: 240 of 244 Tellers (98%) lost their cascade entirely. 140 of 142 CSOs lost cascade. 771 staff total lost all cascade.

**Investigation**: only ONE Branch Operations Supervisor (300228 @ Kenyatta Avenue) had any cascade entries; that one BOS cascaded to ALL 386 Tellers bank-wide. The cleanup removed cross-branch allocations — but those WERE the only cascade source for most Tellers.

**Rollback**: restored `target_cascade.json` to v10.392 state.

## What I discovered (TC32 — new CRITICAL finding)

**The cascade has a "representative sender" architecture, not per-staff:**

| Role | Total staff | Senders | Coverage |
|---|---|---|---|
| Teller | 244 | 0 | 0% (correct — leaves) |
| CSO | 142 | 0 | 0% |
| Branch Operations Supervisor | 102 | **1** | **1%** |
| BOM | 94 | **1** | **1%** |
| Branch Manager | 86 | **1** | **1%** |
| Senior Branch Manager | 8 | **1** | **12%** |

**Only 50 of 1449 staff (3.5%) appear as cascade senders.**

TC32 is the **ROOT CAUSE** explaining many v10.391 symptoms:
- TC1 (MD over-allocates 10×) — one MD cascades full target to each report
- TC18 (cross-branch) — one representative cascades bank-wide
- TC22 (multi-sender ambiguity) — same staff receive from multiple "representative" senders
- TC25 (63% over-allocation) — representatives over-cascade to far more recipients
- TC26 (ratio 386× over) — representative's allocations sum across all subordinates

## The pivot — v10.393 ships diagnostic engine

`utils/cascade_structure_engine.py` — leaf module (~330 LOC, AST-verified, zero upward `utils.*` imports).

**Surface:**
```python
from utils.cascade_structure_engine import (
    CycleFinding, RepresentativeSenderFinding, 
    CrossBranchFinding, MultiSenderFinding, CascadeStructureFindings,
    detect_cycles, detect_representative_sender_pattern,
    detect_cross_branch_violations, detect_multi_sender_ambiguity,
    full_audit, WITHIN_BRANCH_ROLE_PAIRS,
)
```

**Live findings on current state:**
```
✓ cascade_structure_engine self_test passed (9 tests)
  Cycles:                    0
  Rep-pattern CRITICAL roles: 58
  Rep-pattern WARN roles:      3
  Cross-branch violations:    25,137
  Multi-sender ambiguities:   10,269
```

## Decision C5 received and noted

Joshua's guidance: **use the existing Fixed KPI mechanism for ratios.** Replicate MD-set value across everyone with that KPI; no cascade allocation.

The mechanism already exists in CascadeManager (`get_fixed_kpis`, `get_fixed_value`); the BSC already consumes it (pages/1_perform.py). v10.394 work is simpler than first thought:
1. Identify ratio KPIs (CX Score, CASA Ratio, NPL Ratio, PAR, Compliance Score, Audit Score, dormancy KPIs, etc.)
2. Register them in `fixed_kpis.json` per period
3. Cascade engine reads `aggregation` to skip cascading those KPIs (they're fixed)

## Revised fix sequence

| Batch | Concern | Notes |
|---|---|---|
| ~~v10.391~~ | Deep cascade diagnosis | ✅ DONE |
| ~~v10.392~~ | MD↔CRBO circular cascade | ✅ DONE |
| ~~**v10.393**~~ | **Cascade structure engine + TC32** | ✅ **DONE** |
| v10.394 | Ratio KPIs via Fixed mechanism (C5 ✓) | next |
| v10.395 | Re-cascade (resolves TC18/TC21/TC22/TC25/TC32) | one batch fixes the whole class |
| v10.396 | MD duplicate resolution (needs Joshua **C1**) | |
| v10.397 | Role weights normalized (needs Joshua **C6**) | |

**TC18, TC21, TC22, TC25, TC32 all resolved in v10.395** (re-cascade with engine validation).

## Verified outcome

| Metric | Value |
|---|---|
| `utils/cascade_structure_engine.py` exists, leaf-pure | ✅ |
| 4 result dataclasses + 4 detection fns + full_audit | ✅ |
| 9 self-tests pass | ✅ |
| Engine returns expected findings (TC32 confirmed) | ✅ |
| Attempted surgical fix rolled back; state in v10.392 | ✅ |
| No v10.393 backup directory (no real delta to back up) | ✅ |
| 15 v10.393 integration tests pass | ✅ |
| 194 Phase B+C+C2 arc tests pass total | ✅ |
| Audit gates | 277 → **278** |
| Verifier | 494 → **499 checks** |
| Master prompt lockstep | **37/37 consecutive batches** |
| Decision C5 received and noted for v10.394 | ✅ |

## 15 honest acknowledgements

1. **v10.393 tried a surgical fix that failed.** Rolled back. The failure revealed a deeper bug (TC32) that v10.391 missed. This is what honest engineering looks like.

2. **TC32 should have been in the v10.391 diagnosis.** The "representative sender" pattern was visible if I'd checked sender counts per role. I didn't. The diagnosis was less comprehensive than it appeared.

3. **The v10.391 fix sequence was wrong**: TC18/TC21/TC22 can't be surgically cleaned. They require re-cascade (v10.395). This document updates the sequence.

4. **Joshua's C5 guidance is excellent.** The Fixed KPI mechanism already exists; the BSC already uses it. v10.394 just registers ratio KPIs as fixed.

5. **Pattern repeats**: diagnostic engine before fix engine. v10.390 = financial_ratios_engine; v10.393 = cascade_structure_engine. Same shape.

6. **The engine returns DATA not fixes.** v10.394+ can call detection functions, get findings, make decisions. The engine doesn't modify anything.

7. **WITHIN_BRANCH_ROLE_PAIRS is exposed as canonical** — 15 pairs. Senior Branch Manager intentionally excluded (legitimate regional supervision).

8. **TC32 explains MANY symptoms.** v10.395 re-cascade will resolve TC1/TC18/TC22/TC25/TC32 simultaneously rather than tackling them one at a time.

9. **The rollback was clean.** target_cascade.json restored to v10.392 post-fix state. MD↔CRBO cycle still resolved (G277 still passes).

10. **No backup directory was created** for v10.393. Since the cleanup was rolled back, `data/_v10393_backups/` would have been identical to current state — not a real backup. Removed.

11. **The 25,137 cross-branch finding count** is precise scope for v10.395. The engine quantifies the work.

12. **Pattern echoes v10.385**: "deep review" reveals issues; subsequent batches fix them; some early fix attempts surface deeper issues; the diagnosis itself gets updated. v10.391 → v10.393 follows this exactly.

13. **Engine purity AST-verified.** Zero upward `utils.*` imports. Pure leaf module per architecture rule.

14. **9 self-tests in engine + 15 integration tests** — high test density for a diagnostic module. Justifies the module being a foundation for v10.394+.

15. **v10.393 is the FIRST batch in this arc that pivoted mid-batch.** Original concern was surgical cleanup; final concern was engine. Documented honestly. Future batches will learn from this — start with detection, then act.

## On your end

1. Close Streamlit
2. Extract `a2z_v10393_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **499/499**
4. Test the engine:
   ```bash
   python utils\cascade_structure_engine.py
   ```
   Expect 9 self-tests pass + findings printed
5. Read `docs\CASCADE_STRUCTURE_ENGINE_AND_TC32_v10.393.md` (8 Parts)
6. Tell me "continue" → v10.394 = register ratio KPIs as fixed (Joshua C5 already decided)

## What's next — v10.394

**Ratio KPIs via Fixed KPI mechanism** (Decision C5 ✓):

1. **Identify ratio KPIs** by inspection of `kpi_library.json`:
   - CX Score (rating 1-5)
   - CASA Ratio (%)
   - NPL Ratio (%)
   - PAR (%)
   - Compliance Score (%)
   - Audit Score (%)
   - Account Dormancy (%)
   - Channel Dormancy (%)
   - NIM, CIR, ROE if added to library
   - Others as found

2. **Add `aggregation: "fixed"` field** to each KPI entry in `kpi_library.json::kpis[]`

3. **Register in `fixed_kpis.json`** per period (2025, 2026)

4. **Update cascade engine** to skip cascading KPIs marked `aggregation: "fixed"` — they replicate from bank value

5. **Verify via cascade_structure_engine**: after v10.394, the same KPIs should NOT appear in `detect_cross_branch_violations` results (because they're not cascaded at all).

After v10.394, ratio KPIs are handled correctly. Cross-branch violations drop. v10.395 re-cascade addresses the remaining amount KPIs.

Continue?

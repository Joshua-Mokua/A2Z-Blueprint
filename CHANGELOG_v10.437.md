# Changelog — v10.437 HR Rescue Arc Batch 1: CIMS + SLA Relocation

**Date:** 2026-05-14
**Phase:** HR Rescue Arc — Batch 1 of 6 (placement)
**Audit:** G323 added (cumulative 323 gates)
**Tests:** 15/15 PASSED in `test_v10437_hr_relocation.py` + 1 forward-compat patch on v10.436
**Combined regression:** 234 v10.4xx tests PASSED (219 prior + 15 new)
**Verifier:** 805 → **812** (+7 v10.437 checks)
**G162 baseline:** 4022 (130 consecutive zero-drift batches)
**Master prompt:** v4.79 → v4.80 (lockstep — 81 consecutive batches)

**🎯 HR HEALTH: 53.0% → 57.5%** (module placement now 100% — first rescue dimension complete).
**360 harmony 100% preserved. BSC rescue 100% preserved.**

---

## What this batch executed

Per v10.436 audit: 2 pages misplaced in `people_hr`. v10.437 relocates both:

### Move 1: `13_sla.py` (SLA Tracker)
- `department_primary`: `people_hr` → **`operations`**
- `module_path`: `people_hr.sla_tracker` → **`operations.sla_tracker`**
- `require_access` in page file: `"people_hr.sla_tracker"` → **`"operations.sla_tracker"`**
- `secondary_visibility`: kept `sales_customer` (cross-dept readable)

**Rationale**: SLA Tracker monitors operational SLA adherence across categories (Account Opening, Loan Processing, etc.). It's an operations metric, not an HR matter.

### Move 2: `18_cims.py` (CIMS)
- `department_primary`: `people_hr` → **`operations`**
- `module_path`: `people_hr.cims` → **`operations.cims`**
- `require_access` in page file: `"people_hr.cims"` → **`"operations.cims"`**
- `secondary_visibility`: kept `sales_customer`

**Rationale**: CIMS = Customer Instruction Management System. Its **5 sub-pages already lived in `operations`**:
- `105_cims_capture.py`
- `106_cims_process.py`
- `107_cims_compliance.py`
- `108_cims_closure.py`
- `109_cims_live.py`

The legacy `18_cims.py` was the only stray in HR — now reunited with its workflow family.

## Backups

All in `data/_v10437_backups/`:
- `_manifest.json.before`
- `13_sla.py.before`
- `18_cims.py.before`

Reversible if needed.

## Manifest stamp

```json
"_v10437_relocations": {
  "shipped": "v10.437",
  "ts": "2026-05-14",
  "relocations": [
    {"file": "13_sla.py", "from": "people_hr", "to": "operations"},
    {"file": "18_cims.py", "from": "people_hr", "to": "operations"}
  ],
  "rationale": "CIMS sub-pages 105-109 already in operations; SLA Tracker is operational SLA monitoring, not HR."
}
```

## Verified outcome

| Metric | v10.436 (audit-only) | v10.437 (first rescue batch) |
|---|---|---|
| Audit gates | 322 | **323** |
| Verifier checks | 805 | **812** (+7) |
| Lockstep batches | 80 | **81** consecutive |
| G162 baseline | 4022 (129) | 4022 (**130** zero-drift) |
| **HR Module placement** | 50% (2 misplaced) | **100%** ✓ |
| **HR overall health** | **53.0%** | **57.5%** ↑ |
| Pages in HR | 7 (2 misplaced) | **5 (all correctly placed)** |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |

## Pages now in People (HR)

5 pages, all correctly placed:
1. `2_people.py` — People (substantial: 3,783 LOC, 13 tabs)
2. `42_lms.py` — Learning Management (stub: 109 LOC)
3. `43_pip.py` — Performance Improvement (stub: 135 LOC)
4. `58_workforce.py` — Workforce Planning (stub: 86 LOC)
5. `60_disciplinary.py` — Disciplinary Register (stub: 110 LOC)

## Forward-compat patch on v10.436

`test_v10436_misplaced_pages_identified` previously asserted CIMS + SLA were detected as misplaced. After v10.437 moved them, that detection returns 0 by design. Test updated to verify the **detection mechanism still exists** (`MISPLACED_HR_PAGES` constant) rather than the historical mismatch state.

## 10 honest acknowledgements

1. **Cleanest possible relocation.** Manifest update + 2 require_access patches. No engine changes; no data fixes. Pure restructuring.

2. **CIMS reunification is the most satisfying part.** 5 sub-pages already in operations; the parent was alone in HR. Now together.

3. **HR Health jumped 4.5 percentage points** from one placement fix. The other 5 rescue dimensions (engine wiring, page stubs, API coverage, data backing, missing pages) each contribute proportionally.

4. **No data writes.** Just manifest JSON + 2 page files. Easy to undo from backups.

5. **Access control consistency preserved.** Both pages had `secondary_visibility` already configured for the destination dept, so the relocation aligns module_path with where they were already visible.

6. **The forward-compat test pattern is correct.** Rather than letting v10.436 test break, I patched it to assert the engine's detection logic (constant) rather than the resulting state (which v10.437 deliberately changed).

7. **Operations is the right home.** SLA monitoring is operational; CIMS is workflow processing. Neither is "about staff" (HR's actual domain).

8. **The 4 stub HR pages now feel more conspicuous.** With CIMS + SLA gone, the stub-ness of LMS, PIP, Workforce, Disciplinary becomes the dominant issue — exactly what v10.438-v10.440 will address.

9. **Idempotent if re-run.** The migration only changes specific keys to known target values. Re-running on the now-correct state is a no-op.

10. **5 rescue priorities → 4 after this batch.** "Move misplaced pages" priority is done; remaining: wire engines, build out stubs, API endpoints, create new HR pages.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10437_patch.zip` on top of v10.436 state (overwrite all)
3. `python scripts/verify_local_state.py` → expect **812/812**
4. **Open Streamlit → Admin → 📊 Performance → 🩺 BSC Health → "🏥 HR Section Health Audit"**
5. Confirm:
   - Module placement section: ✅ 5 correctly placed, **0 misplaced**
   - Overall health: **57.5%** (up from 53.0%)
   - Rescue priorities: **4 remaining** (was 5)
6. Tell me **"continue"** → v10.438 = HR Rescue Batch 2 (wire `peer_learning` into `42_lms.py` + `gamification` into `2_people.py`)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424–v10.435~~ | BSC + Cascade + Onboarding/Exit | **DONE** |
| ~~v10.436~~ | HR section diagnostic | **DONE** (53% surfaced) |
| ~~**v10.437**~~ | **HR Rescue: Relocate CIMS + SLA** | **DONE (this batch — 57.5%)** |
| **v10.438** | HR Rescue: Wire #14 (PeerLearning) + #17 (Gamification) into LMS + People | **Next** |
| v10.439 | HR Rescue: Wire #18 (Efficiency) + #19 (Wellness) into PIP + People | |
| v10.440 | HR Rescue: Build onboarding + exit pages | |
| v10.441 | HR Rescue: FastAPI endpoints for 6 engines | |
| v10.442 | HR Rescue: PostgreSQL migration scaffold | |
| v10.443+ | People standards QA gap closure | After rescue arc |

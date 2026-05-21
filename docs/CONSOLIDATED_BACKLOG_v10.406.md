# Full Backlog Consolidated — Nothing Slips Through

**Date:** 2026-05-14
**Per Joshua:** "Option A, but don't forget the other batches we are still working on before I brought this in"
**Method:** Reconciliation of all open items across rescue arc + Joshua's standards + earlier deep review + new QA standards doc

---

## Master Sequence — Option A confirmed

E1-E7 first (in order), then F2/F3/F5 architectural, then housekeeping. **22 batches identified** to bring the body to full health.

| Batch | Source | Category | Status | Concern |
|---|---|---|---|---|
| ~~v10.403~~ | Cleanup sweep | Data | ✅ DONE | Synthetic chiefs + Admin exclusion + KPI dup marking |
| ~~v10.404~~ | Joshua F4 | Critical bug | ✅ DONE | Regenerator preserves manual allocations |
| ~~v10.405~~ | User-flagged | UX repair | ✅ DONE | Target guidance ribbon + weight check visibility |
| **v10.406** | QA standards E1 | UI wire | **NEXT** | Wire `manager_rollup` into cascade UI (Real-Time Progress Rollup) |
| v10.407 | QA standards E2 | Feature build | | Strategic pillar visualization & impact |
| v10.408 | QA standards E3 | Feature build | | Target scenario simulator (what-if allocations) |
| v10.409 | QA standards E4 | Enhancement | | Negotiation workflow with escalation chain |
| v10.410 | QA standards E5 | Enhancement | | Executive Cascade Health Dashboard (bank-wide rollup) |
| v10.411 | QA standards E6 | Feature build | | Bottom-up capacity feedback |
| v10.412 | QA standards E7 | Feature build | | Cascade API & Integration (HRIS/payroll/bonus exports) |
| v10.413 | Joshua F2 | Architectural | | Per-layer buffer + MD per-KPI cap |
| v10.414 | Joshua F3 | Architectural | | Per-line-manager retain authorization (per direct report tick) |
| v10.415 | Joshua F5 + perf views | Architectural | | Dual-view BSC (primary=stretch, secondary=base aside) |
| v10.416 | Cleanup sweep C-WT | Data integrity | | Role weight renormalization (225/227 roles broken — BSC math wrong) |
| v10.417 | Cleanup sweep B1-B4 | Data | | KPI library dedup follow-through (4 alias pairs migration) |
| v10.418 | Cleanup sweep D2 | Housekeeping | | Backup retention cleanup (122 MB overlapping rescue arc backups) |
| v10.419 | Cleanup sweep D3 | Housekeeping | | Physically remove 11 retired test functions across 3 files |
| v10.420 | Cleanup sweep D4 | Decision pending | | Reconcile 8 archived uppercase bank_target entries with human form |
| v10.421 | Cleanup sweep F1 | Decision pending | | Pillar weights: 68/14/6/12 (current crisis) vs 40/25/25/10 (Kaplan-Norton balanced) |
| v10.422 | Earlier deep review | Verification | | CBS baseline computation (snapshot 31 Dec 2025 per RM) |
| v10.423 | Earlier deep review | Verification | | PBT computation from CBS data (live actuals integration) |
| v10.424 | Earlier deep review | Verification | | MD BSC shows bank targets once set in Cascade (verify integration) |

---

## Inventory check — items from memory that need attention

### From userMemories "Pending work (known backlog)":
1. ~~CBS baseline computation~~ → **v10.422** (live data dependency; deferred)
2. ~~MD BSC to show bank targets~~ → **v10.424** (verify integration)
3. ~~Live actuals engine — CBS data refresh auto-updates~~ → **v10.422-v10.423** (live data dependency)
4. ~~PBT computation from CBS data~~ → **v10.423** (live data dependency)
5. ~~Some branch roles missing from certain branches~~ → SYNTHETIC DATA ISSUE; not a code fix
6. ~~Pipeline analytics for MD~~ → ALREADY RESOLVED v10.x (confirmed working in deep test)

### From userMemories "Phase B/C backlog":
- ~~Pipeline analytics for MD~~ → confirmed fixed
- ~~Role weight renormalization~~ → **v10.416**

### From cleanup sweep v10.403 prep doc:
- A1-A5 data pollution → ✅ DONE in v10.403
- B1-B4 KPI lib duplicates → MARKED in v10.403, full dedup in **v10.417**
- C-WT1-WT4 role weights → **v10.416**
- D1-D4 housekeeping → D1 done v10.403; **D2 → v10.418, D3 → v10.419, D4 → v10.420**
- E-C1 through E-C9 cascade module issues:
  - E-C1 ✅ DONE (v10.404)
  - E-C2 + E-C3 → **v10.413** (per-layer buffer)
  - E-C5 ✅ DONE (v10.403)
  - E-C6 (remaining indicator) ✅ DONE (verified intact v10.405)
  - E-C7 (retain) → **v10.414**
  - E-C8 (Fixed KPI hiding) → already correctly rendered (verified v10.405); minor enhancement bundled in **v10.415**
  - E-C9 (ancestry display) → bundled in **v10.407** (strategic pillar viz) or **v10.410** (health dashboard)
- F1-F6 decisions:
  - F1 pillar weights → **v10.421**
  - F2 buffer semantics → answered (per-KPI cap) → **v10.413**
  - F3 retain → answered (per-line-manager tick) → **v10.414**
  - F4 regenerate → answered (preserve) → ✅ DONE v10.404
  - F5 Fixed KPI display → answered (greyed for full visibility — already correct) → bundled in **v10.415**
  - F6 archived uppercase bank_target reconciliation → **v10.420**

### From QA standards doc (this session):
- E1 → **v10.406** (NEXT)
- E2 → **v10.407**
- E3 → **v10.408**
- E4 → **v10.409**
- E5 → **v10.410**
- E6 → **v10.411**
- E7 → **v10.412**

---

## Sequencing rationale

**E1-E7 first** (per Joshua's Option A) because:
1. E1 is engine-already-built, pure UI wire — same low-risk pattern as v10.405's suggest_target wire
2. E5 (cascade health dashboard) gives MD visibility before F2 (buffer) adds complexity
3. E6 (capacity feedback) must land before F2 — staff need to flag constraints before managers stretch
4. F2/F3/F5 are architectural — best landed once E1-E7 visibility tools exist to verify correctness

**F2-F5 architectural** (v10.413-v10.415) once E1-E7 lay the foundation:
- v10.413 per-layer buffer can rely on E5 health dashboard to verify cascade integrity post-buffer
- v10.414 retain mechanism builds on E4 escalation chain
- v10.415 dual-view BSC needs E1 rollup to compute stretch-vs-base achievement

**Data integrity v10.416-v10.420** after structural features:
- Role weight renormalization (v10.416) is HIGH priority for BSC accuracy but can wait until features stable
- KPI lib dedup (v10.417) needs care — references must migrate cleanly
- Backups/decisions (v10.418-v10.421) are pure housekeeping

**Verification batches v10.422-v10.424** last — require real CBS data dependency.

---

## What v10.406 will do (next batch)

**Scope**: Wire `utils/manager_rollup.py` (544 LOC, already built) into `pages/12_cascade.py`.

**Concrete changes**:
1. Import `compute_team_rollup`, `compute_recursive_score` in cascade page
2. Add new tab **"📊 Team progress"** OR enhance existing Cascade Tree with live rollup metrics
3. Per direct report show: target, YTD actual, achievement %, variance, color-coded health
4. Per manager show: team aggregate vs their own received target (variance analysis)
5. Auto-refresh when actuals update (read from live_actuals sidecar)
6. Tolerate missing data gracefully (some periods, some staff with no actuals)

**Tests + audit gate**:
- G292: verify manager_rollup wired into cascade page
- ~10 integration tests covering rollup math + UI presence + edge cases

**Expected outcome**:
- MD sees live aggregate progress of all 10 chiefs' teams
- Each chief sees live aggregate of their heads
- Each Branch Manager sees live team progress of BOM/BCM/RO trees
- Variance analysis shows over/under per KPI per team

**Engine state**: 0/0/0/0 preserved (no schema changes).

---

## Health-check matrix at v10.405

| Body part | Status |
|---|---|
| Cascade engine (cycles/cross-branch/multi-sender/rep) | ✅ 0/0/0/0 |
| Canonical hierarchy admin UI | ✅ Working |
| Profitability engines (customer + RM) | ✅ Canonical-wired |
| Period harmonization | ✅ Consistent |
| KPI naming consolidation | ✅ Resolved |
| MD cascade recipients | ✅ Correct (10 chiefs) |
| Manual allocation preservation | ✅ v10.404 |
| Target guidance matrix | ✅ Wired v10.405 |
| Weight visibility | ✅ Always-shown v10.405 |
| Allocation sum indicator | ✅ Verified intact |
| Real-time progress rollup | ⏳ v10.406 |
| Strategic pillar viz | ⏳ v10.407 |
| Target what-if simulator | ⏳ v10.408 |
| Negotiation escalation | ⏳ v10.409 |
| Executive cascade health | ⏳ v10.410 |
| Bottom-up capacity feedback | ⏳ v10.411 |
| Cascade exports/API | ⏳ v10.412 |
| Per-layer buffer | ⏳ v10.413 |
| Per-line-manager retain | ⏳ v10.414 |
| Dual-view BSC | ⏳ v10.415 |
| Role weight renormalization | ⏳ v10.416 |
| KPI lib dedup follow-through | ⏳ v10.417 |
| Backup retention cleanup | ⏳ v10.418 |
| Retired test cleanup | ⏳ v10.419 |
| Archived bank_target reconciliation | ⏳ v10.420 |
| Pillar weights decision | ⏳ v10.421 |
| CBS baseline / PBT computation | ⏳ v10.422-v10.423 (live data dep) |
| MD BSC integration verification | ⏳ v10.424 |

---

## Proceeding to v10.406 now

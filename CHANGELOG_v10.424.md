# Changelog — v10.424 BSC Deep Audit Engine (BSC Rescue Phase opens)

**Date:** 2026-05-14
**Phase:** BSC Rescue Phase **OPENS** (Phase 2d closed in v10.423)
**Audit:** G310 added (cumulative 310 gates)
**Tests:** 17/17 PASSED in `test_v10424_bsc_audit_engine.py`
**Regression:** 352/352 v10.4xx tests PASSED (284 v10.40x-v10.41x + 68 v10.42x)
**Verifier:** 731/731 checks pass (724 → 731, +7 v10.424 checks)
**G162 baseline:** 4022 (117 consecutive zero-drift batches)
**Master prompt:** v4.66 → v4.67 (lockstep — 68 consecutive batches)

---

## What this batch is

The **diagnostic foundation** for the BSC Rescue arc you scoped. Per your directive: every staff has complete befitting BSC; React migration ready; admin config functioning; 100% interconnection BSC↔cascade; canonical hierarchy alignment; no ambiguities or duplications.

Before fixing anything, this batch builds the audit engine that surfaces every BSC integrity issue as queryable, structured, JSON-serializable data. Every fix batch from v10.425 onwards can be tracked against the same audit categories so we know exactly when the body is healthy.

The engine is **READ-ONLY**. No data modification this batch.

## Live findings on current state — what the audit found

**Overall health: 28.6% — 1 critical + 4 warnings**

| # | Category | Status | Detail |
|---|---|---|---|
| 1 | Staff coverage | ✓ | 1437/1437 — every register row has BSC entries |
| 2 | KPI completeness | ⚠️ | 8 incomplete BSCs — 6 Chiefs at 2/8 KPIs (only Compliance Score), 2 at 7/8 |
| 3 | Pillar canonical | ⚠️ | 221 BSC rows use non-canonical "Operational" alias instead of "Operational Excellence" |
| 4 | Weight normalization | ⚠️ | 494/1437 staff have Weight column sums ≠ 1.0 (range 1.0–4.28) |
| 5 | Library alignment | ⚠️ | 81/106 BSC KPIs (76%) NOT registered in kpi_library — 23.58% alignment |
| 6 | Cascade linkage | 🔴 | 10 cascade staff missing from BSC by code |
| 7 | Duplicate rows | ✓ | 0 duplicate (staff, KPI) pairs |

The 6 Chiefs with only the Compliance Score KPI are the most visible issue — anyone opening MD-level BSC dashboards sees broken-looking executives. The 81 unregistered KPIs include real things like "FD Rate Variance vs Market", "BNC Penetration Rate", "Diaspora Remittances Volume" that are functioning in actuals but not in the library — that's a library-actuals split that fix batches will reconcile.

## What v10.424 built

### NEW `utils/bsc_audit_engine.py` (~500 LOC)

Zero streamlit imports. 18th React-ready engine module.

**Constants:**
- `CANONICAL_PILLARS` — Kaplan-Norton 4: Financial, Customer Focus, Operational Excellence, People & Learning (matches v10.423)
- `WEIGHT_TOLERANCE = 0.01` — 1% tolerance for sum-to-1.0 checks
- `MIN_KPIS_BY_ROLE_TIER` — band-driven thresholds (exec_chief=8, director=8, head=6, regional=5, branch_manager=5, manager=4, specialist=3, officer=3, support=2)

**Public API — 7 audit functions + rollup:**

| Function | Returns | Purpose |
|---|---|---|
| `audit_staff_coverage()` | `StaffCoverageAudit` | Every register row has BSC entries |
| `audit_kpi_completeness()` | `KPICompletenessAudit` | Each staff has KPIs for role tier |
| `audit_pillar_canonical()` | `PillarCanonicalAudit` | Only 4 canonical pillars |
| `audit_weight_normalization()` | `WeightNormalizationAudit` | Per-staff Weight sums = 1.0 |
| `audit_library_alignment()` | `LibraryAlignmentAudit` | BSC KPIs ↔ kpi_library |
| `audit_cascade_linkage()` | `CascadeLinkageAudit` | Cascaded targets reflected in BSC |
| `audit_duplicate_rows()` | `DuplicateRowAudit` | No (staff, KPI) doubles |
| `bsc_full_audit()` | `BSCFullAudit` | Rollup + health score |

**8 dataclasses**, all JSON-serializable via `to_dict()`.

**Role tier classifier** (`_classify_role_tier`) maps role names to bands — used for KPI count thresholds. Aligns with the canonical org hierarchy: MD/Chief → exec_chief, Director → director, Head Of → head, Regional Head → regional, Branch Manager → branch_manager, Manager → manager, Specialist/Analyst/Advisor → specialist, Officer → officer, else → support.

### NEW `scripts/audit_bsc.py` runner

```bash
# Human-readable report
python scripts/audit_bsc.py

# JSON for tooling / React frontend
python scripts/audit_bsc.py --json
```

Prints all 7 categories with samples + per-category counts + overall health.

### NEW 7 FastAPI endpoints in `utils/api.py`

All `GET` (read-only) with JWT-required:

| Path | Returns |
|---|---|
| `/api/v1/bsc-audit/full` | Full rollup (BSCFullAudit) |
| `/api/v1/bsc-audit/staff-coverage` | StaffCoverageAudit |
| `/api/v1/bsc-audit/kpi-completeness` | KPICompletenessAudit |
| `/api/v1/bsc-audit/pillar-canonical` | PillarCanonicalAudit |
| `/api/v1/bsc-audit/weight-normalization` | WeightNormalizationAudit |
| `/api/v1/bsc-audit/library-alignment` | LibraryAlignmentAudit |
| `/api/v1/bsc-audit/cascade-linkage` | CascadeLinkageAudit |

### Audit gate G310

Verifies engine API (7 audits + rollup + 8 classes + 3 constants) + AST zero-streamlit + runner --json flag + 7 endpoints + engine state 0/0/0/0 + E2E real data audit + JSON serialization.

## Verified outcome

| Metric | v10.423 | v10.424 |
|---|---|---|
| Audit gates | 309 | **310** |
| v10.4xx tests | 335 | **352** (+17) |
| Verifier | 724 | **731** (+7) |
| API endpoints | 40 | **47** (+7) |
| React-ready engines | 17 | **18** |
| Lockstep batches | 67 | **68** consecutive |
| G162 baseline | 4022 (116) | 4022 (**117** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## Architecture — what React sees

A React BSC health dashboard:

```typescript
// 1. Full audit
const audit = await api.get('/api/v1/bsc-audit/full');
// {
//   staff_coverage:    { register_count: 1437, bsc_unique_staff: 1437, coverage_pct: 100 },
//   kpi_completeness:  { total_staff: 1437, incomplete_count: 8, avg_kpis_per_staff: 21.33 },
//   pillar_canonical:  { non_canonical_pillars: {"Operational": 221}, ... },
//   weight_normalization: { not_normalized_count: 494, ... },
//   library_alignment: { bsc_kpis_not_in_library: [...81], alignment_pct: 23.58 },
//   cascade_linkage:   { cascaded_targets_not_in_bsc: [...10], ... },
//   duplicate_rows:    { duplicate_count: 0 },
//   overall_health_pct: 28.6,
//   issues_by_severity: { critical: 1, warning: 4, info: 0 }
// }

// 2. Drill into a category
const completeness = await api.get('/api/v1/bsc-audit/kpi-completeness');
// { incomplete_entries: [{ staff_name, role, kpi_count, threshold, pillars_covered }] }
```

Same engine the runner script + future Streamlit admin tab call. Diagnostic dashboard wires up without any UI-only logic.

## The rescue arc — what comes next

Suggested fix batch order, smallest blast radius first:

| Batch | Concern | Estimated effort |
|---|---|---|
| **v10.425** | Pillar canonical merge ("Operational" → "Operational Excellence") | Small — flip 221 rows + regenerator guard |
| **v10.426** | Library alignment (register 81 missing KPIs OR remove from actuals) | Medium — needs decision on each KPI |
| **v10.427** | Chief BSC completeness (rebuild 6 chiefs' BSCs from role_kpis) | Medium — needs canonical chief-KPI mapping |
| **v10.428** | Weight normalization in actuals (regenerate from `role_normalized_weights`) | Small — data regeneration |
| **v10.429** | Cascade-BSC linkage (10 missing staff investigation) | Small — investigate + fix or drop |

After v10.429, the audit should report **100% overall health** and the BSC will be testing-ready, fully React/FastAPI compatible, with no ambiguities or duplications, and 100% interconnected to cascade.

## 10 honest acknowledgements

1. **Read-only engine on purpose.** Diagnosis before treatment. Building a fix engine in the same batch would mix concerns and make this 1500 LOC instead of 500.

2. **Health scoring is binary per category.** Either a category passes (no issues found) or it doesn't. Within categories, severity flags critical (coverage/cascade/duplicate gaps) vs. warning (completeness/canonical/normalization/alignment). No partial credit — we want clean signal.

3. **6 chiefs at 2/8 KPIs is an "incomplete" not "missing".** They have *some* BSC entries (Compliance Score), they just don't have the expected breadth. Their fix (v10.427) is to assign the full chief-tier KPI set from `role_kpis`.

4. **The 76% library-alignment gap is huge.** 81 KPIs in BSC actuals aren't in `kpi_library.json`. This is the actuals file diverging from canonical. Reconciling means either (a) adding the 81 to the library properly (with pillar + role assignments + weight) or (b) dropping them from actuals if not real KPIs. Most of the 81 (FD Rate Variance, BNC Penetration, Diaspora Remittances, etc.) look like real specialty KPIs — they should probably be added.

5. **Weight normalization is at the actuals row level.** Different from v10.419's `role_normalized_weights` migration (which fixed the kpi_library role weights). The actuals file's Weight column was generated by old logic and never re-derived from the v10.419 normalized data. v10.428 will close that loop.

6. **The 10 cascade staff missing from BSC are likely role-mismatch artifacts.** Cascade entries by staff_code; BSC by name. Could be EXEC-* or ADMIN-prefixed codes that exist in cascade legacy data but not in canonical staff register. v10.429 will diagnose.

7. **Tier thresholds are conservative.** A "support" role at 2 KPIs passes the threshold. The intent is to surface obviously incomplete BSCs (chiefs with 2, directors with 0) not nitpick specialized roles with legitimately small scorecards.

8. **18 React-ready engines now.** All zero-streamlit, all dataclass-returning. The discipline that v10.412 locked in keeps producing — every audit category exposed via FastAPI from day one.

9. **47 total API endpoints.** Up 7 in this batch. The BSC audit dashboard is now buildable as pure React/FastAPI without touching Streamlit.

10. **The "body as one" framing has a concrete metric now.** 28.6% health → 100% health is the rescue arc's success criterion. Each subsequent batch moves the percentage. Visible, measurable, trackable.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10424_patch.zip` on top of v10.423 state
3. `python scripts/verify_local_state.py` → expect **731/731**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/bsc_audit_engine.py` → engine self-test (7 checks)
6. **Run the audit on your workspace data**: `python scripts/audit_bsc.py` → see the per-category breakdown
7. (Optional) `python scripts/audit_bsc.py --json > bsc_audit.json` for tooling
8. Decide priorities for v10.425+ fix batches (default is the order in "rescue arc — what comes next" above)
9. Tell me **"continue"** → v10.425 = pillar canonical merge (smallest blast radius)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.419-v10.423~~ | ~~Phase 2d data integrity housekeeping~~ | **DONE** |
| **v10.424** | **BSC Deep Audit Engine** | **DONE (this batch)** |
| v10.425 | Pillar canonical merge | Next |
| v10.426 | Library alignment (81 unregistered KPIs) | After v10.425 |
| v10.427 | Chief BSC completeness | After v10.426 |
| v10.428 | Weight normalization in actuals | After v10.427 |
| v10.429 | Cascade-BSC linkage gap | After v10.428 |
| v10.430+ | BSC scorecard table dual-view (consume v10.417 engine) | After audit health = 100% |
| v10.431+ | MD BSC pulls bank targets | Pending CBS decisions |
| v10.432+ | React SPA frontend build | Pending |

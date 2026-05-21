# Changelog — v10.314 Phase 4 Arc 1: Virtual Bank Foundation Verification

**Date:** 2026-05-11
**Phase:** 4 (first arc — verification before generation)
**Audit:** 204/204 gates PASS = 100.0%
**Tests:** 358/358 passing across 21 integration suites (13 skipped in audit env)
**G162 Rebase:** none — module stays tenant-token neutral
**Backlog:** B-010, B-011, B-012 logged

---

## Summary

First arc of Phase 4. Verifies the virtual-bank foundation — staff
universe, role-to-KPI mapping, hierarchy, KPI library integrity,
BSC submission path — before any activity generation starts. Locks
what works through G204, logs three new backlog items for what
doesn't.

**No activity generated. No data modified. No source files changed.**
This is the verification arc that subsequent batches build on.

## Findings at a glance

| Layer | Status | Detail |
|-------|--------|--------|
| Role → KPI mapping | ✅ 100% | All 1,428 active staff have a role in the KPI library |
| BSC submission path | ✅ 21/22 | One staff per department; only Legal fails (dangling KPI ref) |
| Combined staff universe | ✅ 1,428 | hr.json (200) + users.json (1,438), merged with users authoritative for dept |
| KPI library integrity | ⚠️ 77.29% | 47 dangling refs in `role_kpis`, 41 unused KPIs (B-010) |
| Manager hierarchy | ⚠️ 13.45% | 192 of 1,428 linked; users.json has no manager_code (B-012) |
| Department naming | ⚠️ inconsistent | hr.json 13 vs users.json 22 names (B-011) |
| BSC coverage | ⚠️ 2.8% | 40 of 1,428 scored; gap to be closed by generators v10.315+ |

## What shipped

### `utils/virtual_bank.py` (NEW, ~470 lines)

The single source of truth for virtual-bank introspection. 11 public
exports:

- `staff_universe(active_only=True)` — Dict[str, StaffRecord] across both rosters
- `staff_by_department(active_only=True)` — grouped view
- `kpi_library()`, `role_kpi_ids(role)`, `staff_kpi_ids(staff_code)`,
  `active_kpi_definitions()`, `all_kpi_definitions()` — KPI lookups
- `manager_chain(staff_code, max_depth=10)` — walks upward
- `direct_reports(manager_code)` — finds direct reports
- `verify_role_mapping_coverage()` — 100% today
- `verify_kpi_library_integrity()` — surfaces 47 dangling refs
- `verify_bsc_submission_path()` — tests one submission per dept
- `verify_hierarchy()` — 13.45% linkage today
- `coverage_report()` — frozen CoverageReport dataclass with all metrics

Per Rule 7 (engines are diagnostic-only), the module never mutates
source data or auto-submits actuals beyond the explicit verification
path (`verify_bsc_submission_path()` — tagged
`source_module="virtual_bank_verification"` for traceability).

All file reads route through `utils.db.load_json` (G2 compliant).

### `scripts/audit.py` — G204 added

Locks the foundation in its current verified state. Checks:

1. Module exports the 11 required surfaces
2. `staff_universe()` returns ≥1,400 records
3. Role mapping coverage stays at 100%
4. Hierarchy has ≥150 linked staff with depth ≥1
5. `CoverageReport` is a frozen dataclass with required fields

**Critical design**: G204 locks the verification *capability*, not
the verification *outcome*. The honest gaps (47 dangling KPIs, 86%
unlinked hierarchy) are reported through the verification functions,
not blocked by the gate. Future batches that fix B-010/B-011/B-012
improve the metrics; G204 still passes because what it locks is the
ability to detect those issues.

### `tests/integration/test_virtual_bank_foundation_v10314.py` (NEW, 17 tests)

Across 8 sections:

1. Staff universe shape + size + frozen records
2. Department coverage
3. Role mapping at 100%
4. KPI library integrity reported honestly (NOT asserted clean — B-010)
5. Hierarchy partial coverage reported honestly (NOT asserted clean — B-012)
6. BSC submission path for ≥20 departments
7. Coverage report aggregator
8. G204 gate liveness

6 of the 17 tests are **honest-reporting tests** — they assert the
broken state is correctly captured, not that the system is clean.
This is the test discipline for verification arcs: if someone later
"fixes" the data quietly without addressing the backlog, these tests
fire and force the change to be intentional.

### `VIRTUAL_BANK_FOUNDATION_REPORT_v10.314.md` (NEW)

The full deliverable for handover — what works, what doesn't, three
new backlog items, recommended next batch.

## Real findings during this batch

1. **G2 catches direct file I/O across utils/.** My initial draft of
   `_load_json` used `path.read_text()` directly. G2 flagged it
   immediately. Fixed by routing through `utils.db.load_json` —
   same pattern every other module uses. The G2 catch was useful;
   I'd have shipped a discipline drift without it.

2. **`utils.db` exports `db`, not `a2z_db`.** First attempted import
   failed in the audit gate. Fixed by checking actual `utils/db.py`
   exports.

3. **The hierarchy gap is bigger than initial scout suggested.** My
   first scout said hr.json's 161 staff have manager_codes and most
   resolve. The unified universe view confirms 192 (the hr-detail
   subset is larger than I first counted), but the gap for the rest
   of users.json — 1,236 staff with no linkage — is the real
   blocker. Cascade demo to Ecobank can't work past depth-3 for
   86% of the org without B-012.

4. **The KPI library issue compounds the cascade problem.** Legal's
   role maps to `LEGAL_SLA_DOCS` which isn't defined in `kpis[]`.
   Same issue affects 47 KPIs across many roles. The BSC engine
   correctly rejects these (validator checks the KPI exists in the
   library), so activity generators can't accidentally submit
   against dangling KPIs — but every role with a dangling primary
   KPI loses that scoring dimension. B-010 needs deliberate
   per-KPI judgment.

5. **users.json is the authoritative department source.** hr.json
   has 13 cleaner department names; users.json has 22 names that
   include operational layers like "Retail Banking" (1,075 staff —
   75% of the org). The cascade demo must work against users.json
   naming since Retail Banking dominates. `staff_universe()`
   reflects this.

6. **Phase 3 discipline carried over cleanly.** TDD red→green, G2
   compliance, single-batch zip delivery, audit gate per arc,
   integration tests per arc, no source-data mutation — every rule
   from Phase 3 still applies. Phase 4 begins with the same shape.

## Files changed

- `utils/virtual_bank.py` — NEW (~470 lines)
- `scripts/audit.py` — G204 added and registered
- `tests/integration/test_virtual_bank_foundation_v10314.py` — NEW
  (17 tests)
- `VIRTUAL_BANK_FOUNDATION_REPORT_v10.314.md` — NEW (handover doc)
- `CHANGELOG_v10.314.md` — this file

No source data files changed. No pages changed. No HTTP endpoints
changed. No previously-shipped Phase 3 surfaces changed.

## Audit results

```
Score: 204/204 gates = 100.0% — PASS
```

## Platform state

| Metric | v10.313 → v10.314 |
|--------|-------------------|
| Audit gates | 203 → **204** |
| Integration test suites | 20 → **21** |
| Tests passing | 341 → **358** |
| G162 baseline | 4022 (10 consecutive zero-drift batches) |
| G163 ratchet | unchanged |
| Live cockpits | 4 (unchanged) |
| HTTP endpoints | 25 (unchanged) |
| New backlog items | +3 (B-010, B-011, B-012) |

## Honest backlog status

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
| **B-010** | **NEW** | KPI library has 47 dangling refs in role_kpis + 41 unused KPIs |
| **B-011** | **NEW** | Department naming inconsistent between hr.json (13) and users.json (22) |
| **B-012** | **NEW (HIGH)** | 1,236 of 1,428 staff have no manager_code linkage — blocks cascade demo |

## Decision point for next batch

Two paths:

**Path A — B-012 first (hierarchy synthesis), then Teller generator.**
Fixes the cascade-demo blocker first. Synthesises manager linkages
for the 1,236 unlinked staff from department + role + band
conventions so the cascade walks the full 1,428. After that, the
Teller activity generator (244 staff, 21 KPIs) gives the demo live
numbers flowing through the now-walkable hierarchy.

**Path B — Teller generator first, then B-012.**
Gives the demo "live numbers" faster but the cascade story is weak
until B-012 ships. Cascade can only walk the 192 linked staff;
drill-downs into Retail Banking (75% of the org) dead-end at the
unlinked layer.

**Recommend Path A.** Ecobank explicitly asked for "target cascade
flow within the hierarchy perfectly." Path A delivers exactly that.
Path B delivers half. Order matters here.

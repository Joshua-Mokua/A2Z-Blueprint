# Virtual Bank Foundation Report — v10.314

**Date:** 2026-05-11
**Audit:** 204/204 PASS · **Tests:** 358/358 across 21 suites
**Phase 4 first batch:** verification arc, no activity generated

---

## Why this batch exists

Before generating any operator activity, KPI actuals, or BSC scores
across the virtual bank, we need to know the foundation is sound.
Activity built on a broken foundation produces wrong numbers that
look real — the worst kind of bug. This batch audits the foundation,
locks what works, and surfaces what's broken so we plan around it.

## What the foundation looks like today

### ✅ Role-to-KPI mapping: 100% coverage

Every one of **1,428 active users** has a role that appears in the
KPI library's `role_kpis` mapping. No staff is "orphaned" — every
staff has a roleset of KPIs they could in principle be scored on.

This was the foundational concern at the start of Phase 4 planning,
and it's clean. Activity generators can confidently look up any
staff's KPIs without worrying about gaps.

### ✅ BSC submission path: 21/22 departments clean

The end-to-end path (`submit → persist → get_actual → retrieve`)
works for 21 of 22 departments tested. One staff member per
department, one KPI per staff, one submission per department:
all but Legal complete cleanly. The exception (Legal's
`LEGAL_SLA_DOCS`) is a data issue, not a code issue — see B-010.

### ✅ Combined staff universe: 1,428 active records

The `staff_universe()` function unifies hr.json (200 records with
manager linkage and HR detail) and users.json (1,438 records with
broader org population) into a single keyed-by-`staff_code` view.
Of the 1,428 active staff:
- 192 have manager linkage (from hr.json)
- 1,236 do not (from users.json — no manager_code field)
- All 1,428 have role + department + KPI roleset

### ⚠️ KPI library integrity: 77.29%

The KPI library references **47 KPIs in `role_kpis` that aren't
defined in `kpis[]`**. Examples include `LEGAL_SLA_DOCS`,
`AUDIT_SCORE`, `CIR`, `DEP_GROWTH`, `LOAN_GROWTH`. Conversely,
**41 KPIs are defined but never referenced** by any role.

This is logged as **B-010** and intentionally NOT fixed in this
batch — the verification arc reports truth, it doesn't stealth-
patch data. Fixing B-010 is a separate batch that needs to decide
per-KPI: add the missing definition, or remove the dangling
reference. Today we surface this honestly through
`verify_kpi_library_integrity()`.

### ⚠️ Manager hierarchy: 13.45% linkage

Only 192 of 1,428 staff have `manager_code` populated. The
hr.json subset has hierarchies (chain depth 1-3), but users.json
has no manager field at all, so 1,236 staff (86.6% of the org)
have no upward chain.

This is logged as **B-012**. Activity generation can proceed without
this (each staff scores on their own KPIs), but the **cascade demo
to Ecobank will need this fixed** — they specifically asked to see
"target cascade flow within the hierarchy perfectly." A follow-on
batch (v10.315 candidate) will synthesise manager linkages from
department + role + band conventions so the cascade chain is walkable
for the full 1,428.

### ⚠️ Department naming inconsistency

hr.json uses 13 department names (Finance, Credit, Legal, Marketing,
Treasury, Risk, Operations, Strategy, Audit, IT, Compliance, HR,
Branch). users.json uses 22 (the same set plus Retail Banking,
Digital Financial Services, Bancassurance, Commercial & Corporate,
Contact Centre, Trade Finance, Support Services, Diaspora &
Special Segments, Agency Banking, Business Intelligence,
Cybersecurity, Executive, Internal Audit, Marketing, Risk &
Compliance — some are renamed from hr.json, some are new).

The `staff_universe()` function uses **users.json as the
authoritative department source** since it has the wider, more
operationally-realistic structure. Logged as **B-011**. Activity
generation works against the users.json naming.

### ⚠️ BSC coverage: 2.8%

Today: 40 of 1,428 staff have any BSC score recorded. 1,388 staff
have zero history. Closing this gap is the main purpose of Phase 4
batches v10.315 onward — activity generators per role will produce
KPI actuals that submit to the BSC engine, accruing scores per
staff per period.

## Three new backlog items logged

| ID | Severity | Item |
|----|----------|------|
| **B-010** | Medium | KPI library has 47 dangling references in `role_kpis` (KPIs referenced but not defined in `kpis[]`) and 41 unused KPIs (defined but not referenced). Surfaced via `verify_kpi_library_integrity()`. Fix is per-KPI judgment: add the definition or remove the reference. |
| **B-011** | Low | Department naming inconsistent between hr.json (13 depts) and users.json (22 depts). `staff_universe()` treats users.json as authoritative. Reconcile in a later batch if hr.json needs to match the broader naming. |
| **B-012** | **High** | 1,236 of 1,428 staff have no `manager_code` linkage. Manager hierarchy only walks for the 192 hr.json staff. **Blocks the cascade demo Ecobank explicitly asked to see.** Fix: synthesise manager linkages from department + role + band conventions, or extend users.json with manager_code. Candidate batch v10.315. |

## Module shipped: `utils/virtual_bank.py`

Single source of truth for the foundation. ~470 lines, no side
effects (except `verify_bsc_submission_path()` which does submit
tagged records — caller-aware).

**Public surface (11 exports):**

- `staff_universe(active_only=True)` — unified Dict[str, StaffRecord]
- `staff_by_department(active_only=True)` — grouped by department
- `kpi_library()` — parsed JSON view
- `role_kpi_ids(role)` — KPIs for a role
- `staff_kpi_ids(staff_code)` — KPIs for a specific staff
- `active_kpi_definitions()` — active KPIs keyed by ID
- `all_kpi_definitions()` — all KPIs keyed by ID
- `manager_chain(staff_code, max_depth=10)` — walks upward
- `direct_reports(manager_code)` — finds direct reports
- `verify_role_mapping_coverage()` — 100% today
- `verify_kpi_library_integrity()` — 77.29% today (47 dangling)
- `verify_bsc_submission_path()` — 21/22 departments clean
- `verify_hierarchy()` — 13.45% linkage today
- `coverage_report()` — frozen dataclass with all findings

All reads route through `utils.db.load_json` (G2 compliant). The
module is diagnostic-only per Rule 7 — it inspects and reports,
never mutates source data, never auto-submits actuals beyond the
explicit verification path.

## Audit gate G204

Locks the foundation in its current verified state:
- Module exports the 11 required surfaces
- `staff_universe()` returns ≥1,400 records
- Role mapping coverage stays at 100%
- Manager hierarchy has ≥150 linked staff with depth ≥1
- `CoverageReport` is a frozen dataclass

The honest gaps (dangling KPIs, missing hierarchy linkage) are
**reported through the verification functions, not blocked by the
gate**. The gate locks the verification *capability*, not the
verification *outcome*. Future batches that fix B-010/B-011/B-012
will improve the metrics; G204 still passes because the capability
is what's locked.

## Test suite: 17 tests across 8 sections

`tests/integration/test_virtual_bank_foundation_v10314.py`:

1. Staff universe shape + size + frozen records
2. Department coverage (≥20 departments, Retail Banking largest)
3. Role mapping at 100%
4. KPI library integrity reported honestly (NOT asserted clean)
5. Hierarchy partial coverage reported honestly (NOT asserted clean)
6. BSC submission for ≥20 departments
7. Coverage report aggregator + frozen dataclass
8. G204 gate liveness

Of these, 6 are honest-reporting tests (they assert the broken
state is correctly captured, not that the system is clean). This
is deliberate: if anyone later "fixes" the data quietly without
addressing the underlying backlog, the honest-reporting tests fire
and force the change to be intentional.

## What this batch unlocks

After v10.314, every subsequent batch can:

1. Import `staff_universe()` to enumerate the 1,428 staff
2. Import `staff_kpi_ids(code)` to know what KPIs each staff
   should be scored on
3. Submit BSC actuals through the verified path
4. Trust that role mapping coverage is 100% (no orphans)
5. Be aware of and design around B-010/B-011/B-012

Activity generators (Tellers, CSOs, RMs, etc.) can now start. Each
generator imports `staff_universe()`, filters by role, generates
plausible activity, submits actuals. The pattern is templated.

## What this batch did NOT do

- Generated zero activity (no transactions, no KPI movement)
- Submitted zero BSC actuals beyond the 21 verification records
  (one per department, tagged `source_module="virtual_bank_verification"`)
- Fixed zero data quality issues (B-010, B-011, B-012 all open)
- Changed zero source data files

This is intentional. The verification arc reports truth before any
activity is generated. The next batch (v10.315 candidate) addresses
either B-012 (hierarchy synthesis) or the first activity generator,
depending on which path you choose.

## Next decision

The Ecobank demo wants cascade flow through the hierarchy. That
makes **B-012 (hierarchy synthesis)** the next batch — without it,
the cascade demo can't walk past depth-3 for 87% of the org.

Alternatively, the first activity generator (Teller, 244 staff,
21 KPIs) could ship first, giving Ecobank-demoable BSC scores for
17% of the org without addressing hierarchy. The cascade story
would be weaker but the "live numbers moving" story would be
stronger.

Recommended sequence: **B-012 first (hierarchy synthesis,
v10.315), then Teller generator (v10.316)**. This gives a complete
end-to-end demo path: activity flows → KPI actuals → BSC scores →
cascade rollup through the hierarchy → MD sees the full org.

Without B-012, the cascade story has dead ends; without the
generator, the demo has no live numbers. We need both, in that
order.

# CHANGELOG v10.180 — ENH-156 Employee Work Mode Declaration Engine

## What this drop ships

First standard of the Resource Optimization arc (ENH-156..ENH-165).
Greenfield engine, no inspect-first hits — the existing
`utils/initiative_resource.py` (Standard #52) and
`utils/allocation_optimizer.py` (Standard #24) are unrelated
domains (project allocation, RM-customer allocation).

`utils/work_mode_declaration.py` (~430 LOC) provides a self-
declaration tool for employees to record their work mode (REMOTE,
HYBRID, ONSITE, FIELD) over an effective date range, with
privacy-by-design.

## Engine surface

- 4 enums: `WorkMode` (4 values), `DeclarationStatus` (7 states),
  `TransitionOutcome` (5 outcomes), plus `ALLOWED_TRANSITIONS` map
- 1 frozen dataclass: `WorkModeDeclaration` with date-range
  validation in `__post_init__`
- `WorkModeDeclarationEngine` with `declare()`, `transition()`,
  `get()`, `list_for_employee()`, `list_active_in_window()`,
  `mode_distribution_by_department()`, `board_summary()`

## Privacy contract

- `list_for_employee()` is gated: only the employee themselves,
  their direct manager, or HR_ADMIN can read. Other roles or
  unrelated managers receive `[]`
- Aggregate `mode_distribution_by_department` suppresses any
  department cell with n < `PRIVACY_MIN_CELL_SIZE` (=5) to prevent
  re-identification
- Suppressed departments are listed by name in
  `departments_suppressed_n_lt_threshold` so operators can see
  the suppression rather than a silent omission
- REVOKED requires either the employee themselves or HR_ADMIN
  (e.g. termination), with a non-empty `reason`
- Engine never silently overrides employee intent — there is no
  manager-driven REJECTED state; disagreements escalate offline

## State machine

```
DRAFT → SUBMITTED → ACKNOWLEDGED → ACTIVE → EXPIRED
              ↓            ↓          ↓
              REVOKED ←────┴──────────┘   (employee-/HR-driven)
              SUPERSEDED ← ┴──────────┘   (auto on overlap)
```

EXPIRED, REVOKED, SUPERSEDED are terminal — `ALLOWED_TRANSITIONS`
maps each to `frozenset()`.

## Auto-supersede on overlap

When a declaration becomes ACTIVE, `_supersede_overlapping()`
scans for prior SUBMITTED/ACKNOWLEDGED/ACTIVE declarations for
the same employee whose effective range overlaps and transitions
them to SUPERSEDED with a `(SYSTEM, "superseded by WMD-...")`
history entry. Non-overlapping prior declarations are untouched.

## Regulatory basis

- Kenya Employment Act §10 (terms of employment must be in
  writing) — declaration captures the work-arrangement element
- Data Protection Act 2019 §25 (purpose limitation) — declarations
  used for resource optimization, not surveillance
- Internal Hybrid Work Framework (post-2023)

## Honest deferrals (named in `board_summary()`)

| Deferral | Status |
|---|---|
| HRIS_INTEGRATION | Workday/SuccessFactors push deferred |
| AUTO_SCHEDULE_SYNC | Calendar/attendance push deferred |
| ML_PATTERN_DETECTION | Declared vs actual presence requires attendance data |

## Tests — 27 across 8 classes

- `TestModuleShape` — enum coverage, terminal states have empty
  transition sets
- `TestRegistry` — ENH-156 active, batch v10.180
- `TestHubIntegration` — Tier 32 marker present in 7_admin.py
- `TestDeclareCreation` — DRAFT default, date validation,
  empty employee_id rejected
- `TestStateMachine` — full happy path, backward transitions
  rejected, terminal states are terminal
- `TestRevokeOwnership` — reason required, non-owner blocked,
  HR_ADMIN can revoke
- `TestAutoSupersede` — overlapping ACTIVE supersedes, non-
  overlapping does not
- `TestPrivacy` — unrelated employee blocked, self/manager
  allowed, other manager blocked, small-n cells suppressed,
  above-threshold cells published
- `TestHonestDeferrals` — all three deferrals named in
  board_summary
- `TestNoRegression` — full audit still 155/155 PASS

## Apply order

1. `utils/work_mode_declaration.py` — new engine
2. `utils/standards_registry.py` — ENH-156 status='active',
   affected_engines=('work_mode_declaration',), batch='v10.180'
3. `pages/7_admin.py` — Tier 32 — Resource Optimization Suite
   inserted after Tier 31 close
4. `tests/test_work_mode_declaration_v10_180.py` — 27 tests
5. Run `python scripts/audit.py` → 155/155 PASS

## Audit

`Score: 155/155 gates = 100.0% — PASS` (unchanged — engine drop,
not a closure).

## Resource Optimization arc roadmap

| Standard | Engine | Status |
|---|---|---|
| ENH-156 | work_mode_declaration | **active (v10.180)** |
| ENH-157 | (workload_forecasting) | planned |
| ENH-158 | (tsl_optimization) | planned |
| ENH-159 | (cross_channel_balancing) | planned |
| ENH-160 | (utilization_dashboard) | planned |
| ENH-161 | (wellbeing_burnout) | planned |
| ENH-162 | (whatif_scheduler) | planned |
| ENH-163 | (resource_investment_case) | planned |
| ENH-164 | (integrity_culture_score) | planned |
| ENH-165 | (executive_resource_dashboard) | planned |

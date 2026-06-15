# CHANGELOG v10.565 — Batch B2: register-driven branch-head scope

## What
A branch head now sees everyone in their OWN branch, instead of self-only.
Scope is resolved from the authoritative staff register by staff_code -> Unit,
and bounded to that single Unit (no cross-branch visibility).

utils/core_audit.py:
- BRANCH_HEAD_ROLES = {"senior branch manager", "branch manager"} (explicit,
  case-insensitive, easy to audit/extend).
- _register_staff_index() — cached staff_code -> {role, unit, region, name}
  from data/staff_register.xlsx (clean columns only; no tree inference, so it
  cannot over-scope). Empty on error -> safe fallback.
- get_visible_staff(): after the all-view (admin/root) check and BEFORE the
  legacy REPORTING_TREE lookup, a branch-head role is scoped to its register
  Unit. Falls through to the legacy/self-only path if the role isn't a branch
  head, the staff_code is unknown, or the Unit is "Head Office".

## Why this and not a full reporting-tree resolver
A naive register "Reports To" chain over-scopes catastrophically: every Area
Manager is tagged Region="Head Office" (no real region), so region-fallback
funnels the whole branch network under one Area Manager (1203 of 1438 staff),
and branch staff report to "Branch Manager" while branch heads are titled
"Senior Branch Manager", severing the branch tree. Until those register-data
gaps are fixed, only the clean Unit column drives scope — bounded and safe.

## Verified
- Senior Branch Manager (Thika) -> 17 staff, Unit=={Thika} (bounded).
- A different Senior Branch Manager -> only their own branch (no leakage).
- Teller -> self-only (not a branch head).
- Area Manager -> NOT branch-scoped (the 1203 over-scope is avoided).

## Still self-only / fallback until register data is fixed
Area Manager, Regional roles, Head of Branches, CRBO. Unlocks with no code
change once Area/Regional roles carry a real Region (not "Head Office") and the
Branch Manager / Senior Branch Manager title mismatch is reconciled.

## Test
tests/test_batchB2_branch_head_scope.py (run in the project venv).

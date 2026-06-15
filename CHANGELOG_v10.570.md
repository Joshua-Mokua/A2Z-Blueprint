# CHANGELOG v10.570 — Batch B6: branch test logins self-heal (login persistence)

## Problem
After any users.json reset, only the canonical role logins (william, admin,
role accounts) came back — they self-heal via UserManager.ensure_test_logins().
The register branch chain (300xxx: immaculate0716, frank0731, …) did NOT, so
scope-testing logins kept vanishing ("only william is able to login").
Diagnosed with scripts/check_login.py: "No register-staff (300xxx) accounts
present — seed never ran" even though they had been seeded earlier.

## Fix (the "express login" parity you asked for)
- utils/test_logins.py: add branch_test_logins() — a static list of the 11
  Thika chain accounts (username, password, full_name, role, staff_code, unit,
  region, can_view_all). can_view_all is False for everyone except the register
  root (william0001), so cascade scope is exercised honestly.
- utils/core.py: UserManager.ensure_branch_test_logins() restores any missing
  branch account (correct can_view_all/unit/region/_protected), and __init__
  now calls it after ensure_test_logins(). Cheap when healthy (membership
  checks only). So the branch logins persist across any users.json reset, the
  same way the canonical set does.

Note: deal scope is role-based (get_visible_staff ignores can_view_all), so the
flag is kept correct for clarity but isn't what governs visibility — B1/B2 do.

## Verified
- branch_test_logins(): 11 accounts, password convention holds, only
  william0001 is all-view.
- ensure_branch_test_logins(): restores a popped account; it then authenticates.

## Test
tests/test_batchB6_branch_login_selfheal.py (run in the project venv).

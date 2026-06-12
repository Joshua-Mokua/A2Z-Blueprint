# CHANGELOG v10.544 — Per-role test-login seed

Adds scripts/seed_test_logins.py: creates ONE stable, loginable test
account for each of the 49 canonical roles (utils.role_taxonomy), so the
React UI can be exercised through every role during the frontend phase.

## Account contract
- active=True, must_change_password=False, _protected=True, can_view_all=True
- username = role slug (top-exec pinned to william001 for continuity)
- password = EcoStaff + last-4 of staff_code (william001 -> EcoStaff0001)
- Writes TEST_LOGINS.md (full username/role/password key).

## Safety
- Backs up data/users.json (timestamped) before writing (Trap #12).
- Aborts on empty/missing users.json (no default-account fallback).
- Touches ONLY test accounts; the migrated 487-staff population in
  PostgreSQL is untouched. users.json is the test-login file by design.

## Run
  python scripts\seed_test_logins.py            # create/refresh
  python scripts\seed_test_logins.py --dry-run  # preview

## Deferred (P-AUTH-b, next)
- Harden UserManager._load() so a transient read error LOGS + backs up
  instead of silently overwriting users.json with the 3 defaults
  (root cause of the disappearing test logins).

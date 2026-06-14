# CHANGELOG v10.550 — Phase P Batch P-AUTH-d: full per-role self-heal

Widens the P-AUTH-c self-heal from the CEO login only to ALL canonical
role logins, so no role test account can vanish mid-testing.

## What changed
- NEW utils/test_logins.py — canonical_test_logins(): single source of
  truth deriving one account per canonical role (utils.role_taxonomy),
  cached. Password = EcoStaff + last-4 of staff_code; william001 pinned.
- utils/core.py — UserManager.ensure_test_logins() now iterates the shared
  canonical set (full role coverage), with a CEO-only fallback if the
  taxonomy import ever fails. Still cheap when healthy (membership checks,
  writes only on restore).
- scripts/seed_test_logins.py — refactored to consume canonical_test_logins()
  too, so seed and self-heal can never drift.
- tests/test_p_auth_d_full_selfheal.py — source-scan + behavioral.

## Effect
After any users.json reset, the next UserManager() construction (i.e. the
next API request) restores all role logins automatically.

## Verification
- py_compile (test_logins/core/seed) -> OK
- proof: 49 unique accounts, william001 -> EcoStaff0001, self-heal would
  restore all 49 after a 3-default reset -> pass

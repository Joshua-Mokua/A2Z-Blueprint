# CHANGELOG v10.554 — Hardening Batch H3: identity enrichment (keystone)

## Symptom
After H2 let deal creation work, the created deal (D0010) returned 404
"out-of-scope", and did not appear in the deal list or manager validation
queues — even for william001 (CEO), who created it.

## Root cause
get_current_user (utils/auth_jwt.py) returns ONLY JWT claims
(username/role/scope) — no staff_code/full_name. get_visible_staff_codes
floors visibility to the caller's own staff_code and walks REPORTING_TREE
from the caller's identity; with staff_code empty, the visible set was EMPTY,
so the creator's own deal was out of scope. This is the same thin-identity
class H1 patched for one route — but it affects EVERY consumer of identity.

## Fix (utils/auth_jwt.py)
get_current_user now enriches the user dict from users.json (the authoritative
source — JWT is never trusted for these) with staff_code, full_name,
can_view_all, managed_staff_codes/roles/units, department. Only missing/blank
keys are filled; explicit token claims (role) are never overwritten. Lazy
UserManager import (no cycle); best-effort (auth still works if store
unreadable). This feeds pipeline scope, deal creation, and queues at once.

## Verified
- py_compile auth_jwt.py -> OK
- enrichment fills william001 -> staff_code 0001 + can_view_all True, role
  preserved from JWT; scope floor then includes 0001 so the creator's deal
  is visible; unknown user is a safe no-op.

## Note on manager queues
A freshly created Lead-stage deal is visible in the LIST immediately. Whether
it appears in the VALIDATION queue depends on the deal's stage/validation
rules (Lead-stage deals are not necessarily pending manager validation) —
that is separate from this visibility fix.

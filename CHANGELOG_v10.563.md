# CHANGELOG v10.563 — branch test logins (real register staff, frontline → CEO)

## What
scripts/seed_branch_test_logins.py — generates test logins for ONE branch's
full chain from the REAL staff register (300xxx codes), not the synthetic
000x accounts. Default branch: Thika (11 logins, Teller → CEO).

Why real staff: william001 (staff_code 0001) is synthetic and absent from the
register hierarchy — the source of the scope band-aids. These logins use the
register's actual people, so cascade scope resolves against real data.

- Password = EcoStaff + last-4 of staff_code (matches utils/test_logins).
- Username = lowercase first name + last-4 (e.g. william0001).
- Backs up users.json (timestamped) before writing; idempotent; aborts if
  users.json is missing/empty (no accidental defaults overwrite).
- Writes BRANCH_TEST_LOGINS.md credentials key.

USAGE: python scripts/seed_branch_test_logins.py --branch Thika
       python scripts/seed_branch_test_logins.py --branch Thika --list

## Scope behaviour to expect (important)
- william0001 (Chief Executive & Managing Director, register root) → sees ALL
  deals (B1 data-driven all-view).
- Every other level (Area Manager, Senior Branch Manager, Teller, …) → SELF-ONLY
  for now, because their register role names don't match the hardcoded
  REPORTING_TREE. Full per-level cascade (each level sees its register subtree)
  lands with the mid-level scope rebuild — these logins are its test bed.

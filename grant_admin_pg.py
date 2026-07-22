#!/usr/bin/env python3
"""Grant super access (is_admin + can_view_all) directly in POSTGRES.

Why this exists: grant_admin.py writes data/users.json, but the app now reads users from
Postgres — so those grants never took effect. This writes where the app actually looks.

is_admin=True is the flag that matters: get_visible_staff returns the FULL roster for
is_admin (no hierarchy conditions), and it unlocks admin screens. can_view_all is set too
for legacy paths.

    python grant_admin_pg.py KE406 KE1298 KE1347            # dry run — shows changes
    python grant_admin_pg.py KE406 KE1298 KE1347 --apply
    python grant_admin_pg.py --find "Mary"                  # look up a staff code by name
"""
import sys
from utils.db import db as _db

args = sys.argv[1:]

# name lookup helper
if "--find" in args:
    q = args[args.index("--find") + 1]
    rows = _db.fetch_all(
        "SELECT staff_code, full_name, role, department, is_admin FROM users "
        "WHERE full_name ILIKE %s ORDER BY full_name", (f"%{q}%",)) or []
    print(f"=== staff matching {q!r} ===")
    for r in rows:
        print(f"   {r.get('staff_code'):10} {r.get('full_name'):32} "
              f"{str(r.get('role'))[:28]:28} admin={r.get('is_admin')}")
    if not rows:
        print("   (none found)")
    sys.exit(0)

apply = "--apply" in args
codes = [a.strip().upper() for a in args if not a.startswith("--")]
if not codes:
    print(__doc__); sys.exit(1)

print(f"=== grant super access (is_admin + can_view_all) to {len(codes)} staff ===\n")
found = []
for c in codes:
    rows = _db.fetch_all(
        "SELECT username, staff_code, full_name, role, is_admin, can_view_all "
        "FROM users WHERE UPPER(staff_code)=%s OR UPPER(username)=%s", (c, c)) or []
    if not rows:
        print(f"   !! {c}: NOT FOUND in Postgres"); continue
    r = rows[0]
    found.append(r)
    print(f"   {c}: {r.get('full_name')}  ({r.get('role')})")
    print(f"        now:  is_admin={r.get('is_admin')} can_view_all={r.get('can_view_all')}")
    print(f"        after: is_admin=True  can_view_all=True")

if not apply:
    print("\n[DRY-RUN] re-run with --apply to grant")
    sys.exit(0)

for r in found:
    _db.execute(
        "UPDATE users SET is_admin=TRUE, can_view_all=TRUE WHERE username=%s",
        (r.get("username"),))
print(f"\ngranted to {len(found)} staff.")

# verify
print("\n=== verify ===")
for r in found:
    v = _db.fetch_all("SELECT staff_code, full_name, is_admin, can_view_all FROM users "
                      "WHERE username=%s", (r.get("username"),)) or []
    if v:
        x = v[0]
        ok = bool(x.get("is_admin"))
        print(f"   [{'PASS' if ok else 'FAIL'}] {x.get('staff_code')} {x.get('full_name')} "
              f"is_admin={x.get('is_admin')}")
print("\nRestart the API server, then these logins see everything with no hierarchy limits.")

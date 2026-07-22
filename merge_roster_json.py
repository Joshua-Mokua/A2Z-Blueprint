#!/usr/bin/env python3
"""Merge data/staff_roster.json (362 real staff, from Josh's Postgres) into THIS
server's Postgres users table WITHOUT touching any existing login.

Unlike load_roster_json.py (wipe-and-replace, staff-code usernames — breaks AD
login for every existing account), this:
  - MATCHES roster entries to existing users by staff_code, falling back to a
    case-insensitive full_name match.
  - For a MATCH: backfills department/unit/role/band/gender/region/reports_to/
    dotted/date_of_employment onto the EXISTING username. Never touches
    username, password, email, is_admin, active.
  - For NO MATCH: inserts a NEW user, keyed by the roster's staff_code as
    username (no AD account exists for them yet) — same convention
    staff_projection.export_logins_from_db uses (must_change_password=True,
    default password EcoStaff+last4).

    python merge_roster_json.py               # dry run — counts + samples
    python merge_roster_json.py --apply        # write it
"""
import json, sys
from pathlib import Path

def main():
    apply = "--apply" in sys.argv[1:]
    src = Path("data/staff_roster.json")
    if not src.exists():
        print("data/staff_roster.json not found"); sys.exit(1)
    roster = json.loads(src.read_text(encoding="utf-8")).get("users", [])
    print(f"roster: {len(roster)} staff")

    from utils.db import db as _db
    if not _db.is_postgres_ready():
        print("Postgres not ready"); sys.exit(1)

    existing = _db.fetch_all("SELECT username, staff_code, full_name FROM users") or []
    by_code = {str(r["staff_code"]).strip().upper(): r["username"]
               for r in existing if r.get("staff_code")}
    by_name = {str(r["full_name"]).strip().lower(): r["username"]
               for r in existing if r.get("full_name")}

    matched, inserted, skipped = [], [], []
    for u in roster:
        code = str(u.get("staff_code", "")).strip().upper()
        name = str(u.get("full_name", "")).strip()
        username = by_code.get(code) or by_name.get(name.lower())
        if username:
            matched.append((username, u))
        else:
            inserted.append(u)

    print(f"matched to existing logins: {len(matched)}")
    print(f"to insert as new (no existing login): {len(inserted)}")
    for username, u in matched[:5]:
        print(f"   MATCH  {u.get('staff_code')} {u.get('full_name'):30} -> existing username {username!r}")
    for u in inserted[:5]:
        print(f"   NEW    {u.get('staff_code')} {u.get('full_name'):30} -> would create username {u.get('staff_code')!r}")

    if not apply:
        print("\n[DRY-RUN] re-run with --apply to write. No existing username, password, "
              "email, is_admin, or active flag is ever touched by this script.")
        return

    for username, u in matched:
        md = u.get("metadata") or {}
        _db.execute(
            """UPDATE users SET department=%s, unit=%s, role=COALESCE(NULLIF(role,''), %s),
               metadata = metadata || %s::jsonb
               WHERE username=%s""",
            (u.get("department", ""), u.get("unit", ""), u.get("role", ""),
             json.dumps({
                 "band": md.get("band", ""), "gender": md.get("gender", ""),
                 "region": md.get("region", ""), "reports_to": md.get("reports_to", ""),
                 "dotted": md.get("dotted", []),
                 "date_of_employment": md.get("date_of_employment", ""),
             }),
             username))

    from utils.core import UserManager
    um = UserManager()

    ins = 0
    for u in inserted:
        code = str(u.get("staff_code", "")).strip()
        md = u.get("metadata") or {}
        # Same convention as staff_projection.export_logins_from_db: default
        # password EcoStaff+last4, must_change_password=True on first login.
        pwd_hash = um.hash_pw(f"EcoStaff{code[-4:]}")
        _db.execute(
            """INSERT INTO users (username, password_hash, full_name, email, role,
                department, unit, staff_code, active, is_admin, can_view_all,
                must_change_password, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (username) DO NOTHING""",
            (code, pwd_hash, u.get("full_name", ""), u.get("email", ""), u.get("role", "Staff"),
             u.get("department", ""), u.get("unit", ""), code,
             bool(u.get("active", True)), bool(u.get("is_admin", False)),
             bool(u.get("can_view_all", False)), True,
             json.dumps({
                 "band": md.get("band", ""), "gender": md.get("gender", ""),
                 "region": md.get("region", ""), "reports_to": md.get("reports_to", ""),
                 "dotted": md.get("dotted", []),
                 "date_of_employment": md.get("date_of_employment", ""),
             })))
        ins += 1

    print(f"\nupdated {len(matched)} existing logins, inserted {ins} new staff-code accounts.")
    print("Restart the API, then: python export_pg_to_register.py --apply")

if __name__ == "__main__":
    main()

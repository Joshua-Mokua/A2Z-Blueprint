#!/usr/bin/env python3
"""
Migrate data/users.json → Postgres users table.

Run once (or re-run safely — it upserts, never duplicates).

Usage:
    cd /var/www/a2z-blueprint/A2Z-Blueprint
    set -a && source .env && set +a
    venv/bin/python scripts/migrate_users_to_db.py

    # Dry-run (print what would be inserted, don't write):
    venv/bin/python scripts/migrate_users_to_db.py --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    from utils.db import db

    if not db.is_postgres_ready():
        print("ERROR: Postgres not ready. Check A2Z_USE_DB and A2Z_DB_* env vars.")
        sys.exit(1)

    users_file = Path("data/users.json")
    if not users_file.exists():
        print(f"ERROR: {users_file} not found.")
        sys.exit(1)

    raw = json.loads(users_file.read_text(encoding="utf-8"))
    # Structure: {username: {password, full_name, role, ...}}
    if not isinstance(raw, dict):
        print("ERROR: users.json is not a dict keyed by username.")
        sys.exit(1)

    inserted = updated = skipped = 0

    for username, u in raw.items():
        username = str(username).strip()
        if not username:
            skipped += 1
            continue

        pwd_hash = str(u.get("password") or "").strip()
        if not pwd_hash:
            print(f"  SKIP {username}: no password hash")
            skipped += 1
            continue

        role     = str(u.get("role") or "Staff").strip()
        is_admin = role.lower() in ("admin",) or bool(u.get("is_admin"))

        record = {
            "username":           username,
            "password_hash":      pwd_hash,
            "full_name":          str(u.get("full_name") or "").strip() or None,
            "email":              str(u.get("email") or "").strip() or None,
            "role":               role,
            "department":         str(u.get("department") or "").strip() or None,
            "unit":               str(u.get("unit") or "").strip() or None,
            "staff_code":         str(u.get("staff_code") or "").strip() or None,
            "active":             bool(u.get("active", True)),
            "is_admin":           is_admin,
            "can_view_all":       bool(u.get("can_view_all", False)),
            "must_change_password": bool(u.get("must_change_password", False)),
        }

        if args.dry_run:
            print(f"  DRY  {username:20s}  role={role:25s}  admin={is_admin}")
            continue

        try:
            existing = db.fetch_one(
                "SELECT username FROM users WHERE username = %s", (username,)
            )
            db.execute(
                """
                INSERT INTO users
                    (username, password_hash, full_name, email, role, department,
                     unit, staff_code, active, is_admin, can_view_all, must_change_password)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (username) DO UPDATE SET
                    password_hash       = EXCLUDED.password_hash,
                    full_name           = EXCLUDED.full_name,
                    email               = EXCLUDED.email,
                    role                = EXCLUDED.role,
                    department          = EXCLUDED.department,
                    unit                = EXCLUDED.unit,
                    staff_code          = EXCLUDED.staff_code,
                    active              = EXCLUDED.active,
                    is_admin            = EXCLUDED.is_admin,
                    can_view_all        = EXCLUDED.can_view_all,
                    must_change_password = EXCLUDED.must_change_password
                """,
                (
                    record["username"], record["password_hash"], record["full_name"],
                    record["email"], record["role"], record["department"],
                    record["unit"], record["staff_code"], record["active"],
                    record["is_admin"], record["can_view_all"], record["must_change_password"],
                ),
            )
            if existing:
                updated += 1
                print(f"  UPD  {username:20s}  role={role}")
            else:
                inserted += 1
                print(f"  INS  {username:20s}  role={role}")
        except Exception as exc:
            print(f"  ERR  {username}: {exc}")
            skipped += 1

    if args.dry_run:
        print(f"\nDry run: {len(raw)} users would be processed.")
        return

    total = db.fetch_scalar("SELECT COUNT(*) FROM users")
    print(f"\nDone — inserted={inserted}  updated={updated}  skipped={skipped}")
    print(f"Total users in Postgres now: {total}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Add any missing columns to the EXISTING users table.

The users table was created by an older schema, so columns the current code writes
(metadata, email, department, band, gender, must_change_password) may not exist —
which is why the staff upload failed with:
    column "metadata" of relation "users" does not exist

This ALTERs the live table to match. Idempotent: ADD COLUMN IF NOT EXISTS, so it is
safe to run repeatedly and never touches existing data.

    python migrate_users_columns.py            # show what's missing
    python migrate_users_columns.py --apply
"""
import sys

WANT = [
    ("email",                "VARCHAR(200)"),
    ("department",           "VARCHAR(200)"),
    ("unit",                 "VARCHAR(200)"),
    ("band",                 "VARCHAR(20)"),
    ("gender",               "VARCHAR(20)"),
    ("staff_code",           "VARCHAR(50)"),
    ("is_admin",             "BOOLEAN NOT NULL DEFAULT false"),
    ("can_view_all",         "BOOLEAN NOT NULL DEFAULT false"),
    ("must_change_password", "BOOLEAN NOT NULL DEFAULT false"),
    ("metadata",             "JSONB DEFAULT '{}'"),
]

def main():
    apply = "--apply" in sys.argv
    from utils.db import db
    have = {r["column_name"] for r in (db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'users'") or [])}
    print("existing columns:", ", ".join(sorted(have)) or "(none?)")
    missing = [(c, t) for c, t in WANT if c not in have]
    if not missing:
        print("\nnothing missing — the table already has every column the code writes.")
        return
    print(f"\nMISSING ({len(missing)}):")
    for c, t in missing:
        print(f"   {c:22} {t}")
    if not apply:
        print("\n[DRY-RUN] re-run with --apply to ALTER the table.")
        return
    for c, t in missing:
        sql = f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {c} {t}"
        print("  ->", sql)
        db.execute(sql)
    print("\ndone. Re-run the staff upload.")

if __name__ == "__main__":
    main()

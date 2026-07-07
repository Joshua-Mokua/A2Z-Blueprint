#!/usr/bin/env python3
"""
migrate_users.py -- Copy all users from users.json into PostgreSQL.

Run once from your project folder:
    .venv\Scripts\activate
    python migrate_users.py

Requirements:
    - PostgreSQL running with a2z_mis360 database created
    - Tables created (run create_tables.sql in pgAdmin first)
    - Environment variables set (see below)
    - pip install psycopg2-binary bcrypt

Environment variables to set first (in terminal or Windows settings):
    set A2Z_DB_HOST=localhost
    set A2Z_DB_PORT=5432
    set A2Z_DB_NAME=a2z_mis360
    set A2Z_DB_USER=a2z_app
    set A2Z_DB_PASSWORD=A2ZAppPass2026!
"""

import os, sys, json
from pathlib import Path

DB_HOST = os.getenv("A2Z_DB_HOST", "localhost")
DB_PORT = int(os.getenv("A2Z_DB_PORT", "5432"))
DB_NAME = os.getenv("A2Z_DB_NAME", "a2z_mis360")
DB_USER = os.getenv("A2Z_DB_USER", "a2z_app")
DB_PASS = os.getenv("A2Z_DB_PASSWORD", "")

if not DB_PASS:
    print("ERROR: A2Z_DB_PASSWORD not set.")
    print("Run:  set A2Z_DB_PASSWORD=A2ZAppPass2026!")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 not installed.")
    print("Run:  pip install psycopg2-binary")
    sys.exit(1)

print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}...")
try:
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )
    conn.autocommit = False
    print("Connected to PostgreSQL")
except Exception as e:
    print(f"\nERROR: {e}")
    print("\nTroubleshooting:")
    print("  1. Is PostgreSQL running? Open Services in Windows and check.")
    print("  2. Did you create the database a2z_mis360 in pgAdmin?")
    print("  3. Did you run create_tables.sql in pgAdmin first?")
    print("  4. Is the password correct?")
    sys.exit(1)

users_file = Path(__file__).parent / "data" / "users.json"
if not users_file.exists():
    print(f"ERROR: {users_file} not found")
    sys.exit(1)

users = json.loads(users_file.read_text(encoding="utf-8"))
print(f"Loaded {len(users):,} users from users.json")
print("Migrating to PostgreSQL...")

inserted = 0
errors   = 0
cur      = conn.cursor()

for username, ud in users.items():
    try:
        metadata = {
            "band": ud.get("band", ""),
            "gender": ud.get("gender", ""),
            "accessible_modules": ud.get("accessible_modules", []),
            "hidden_modules": ud.get("hidden_modules", []),
        }
        cur.execute("""
            INSERT INTO users (
                username, password_hash, full_name, email, role,
                department, unit, staff_code,
                active, is_admin, can_view_all, is_dept_super_user,
                dept_super_user_for, is_ict_admin, must_change_password,
                metadata
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (username) DO UPDATE SET
                password_hash        = EXCLUDED.password_hash,
                full_name            = EXCLUDED.full_name,
                role                 = EXCLUDED.role,
                department           = EXCLUDED.department,
                active               = EXCLUDED.active,
                is_admin             = EXCLUDED.is_admin,
                can_view_all         = EXCLUDED.can_view_all,
                metadata             = EXCLUDED.metadata
        """, (
            username,
            ud.get("password", ""),
            ud.get("full_name", ""),
            ud.get("email", ""),
            ud.get("role", ""),
            ud.get("department", ""),
            ud.get("unit", ""),
            str(ud.get("staff_code", "")),
            bool(ud.get("active", True)),
            bool(ud.get("is_admin", False)),
            bool(ud.get("can_view_all", False)),
            bool(ud.get("is_dept_super_user", False)),
            ud.get("dept_super_user_for", ""),
            bool(ud.get("is_ict_admin", False)),
            bool(ud.get("must_change_password", False)),
            json.dumps(metadata),
        ))
        inserted += 1
        if inserted % 200 == 0:
            print(f"  {inserted:,} / {len(users):,} done...")
    except Exception as e:
        errors += 1
        print(f"  SKIP {username}: {e}")
        conn.rollback()
        if errors > 20:
            print("Too many errors. Aborting.")
            sys.exit(1)

conn.commit()
cur.close()
conn.close()

print(f"\n{'='*50}")
print(f"Done! Migrated {inserted:,} users. Errors: {errors}")
print(f"\nNext steps:")
print(f"  1. Open: utils/db.py")
print(f"  2. Find: TABLE_USE_DB")
print(f"  3. Change: \"users\": False")
print(f"     To:     \"users\": True")
print(f"  4. Restart: streamlit run app.py")
print(f"  5. Log in — users now come from PostgreSQL!")

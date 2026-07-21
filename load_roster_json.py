#!/usr/bin/env python3
"""ALEX RUNS THIS on the bank server: load data/staff_roster.json into Postgres,
replacing the fake staff. Wipe-and-replace, preserving admin logins.

    .venv\\Scripts\\activate
    python load_roster_json.py --dry-run           # preview: counts, preserved logins
    python load_roster_json.py --apply             # do it
    python load_roster_json.py --apply --keep admin,william001,<alex_login>

Preserves --keep logins (default: admin, william001). ADD ALEX'S ADMIN LOGIN to --keep
if it differs, or he loses access. Backs up existing users to users_backup_<ts>.json first.
"""
import json, sys, time
from pathlib import Path

def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    keep = ["admin", "william001"]
    if "--keep" in args:
        keep = args[args.index("--keep")+1].split(",")
    keep_set = set(k.strip() for k in keep)

    src = Path("data/staff_roster.json")
    if not src.exists():
        print("data/staff_roster.json not found — did you pull it?"); sys.exit(1)
    payload = json.loads(src.read_text(encoding="utf-8"))
    users = payload.get("users", [])
    has_hashes = payload.get("includes_hashes", False)
    print(f"roster file: {len(users)} users, includes_hashes={has_hashes}")
    print(f"preserve logins: {sorted(keep_set)}")

    from utils.db import db as _db
    if not _db.is_postgres_ready():
        print("Postgres not ready on this machine — check DB is running."); sys.exit(1)

    existing = _db.fetch_all("SELECT username, full_name FROM users") or []
    print(f"current users in this Postgres: {len(existing)}")
    preserved = [u for u in existing if u.get("username") in keep_set]
    print(f"will preserve: {[u.get('username') for u in preserved]}")
    print(f"will delete: {len(existing) - len(preserved)}  then insert: {len(users)}")

    if not apply:
        print("\n[DRY-RUN] re-run with --apply to write. Nothing changed.")
        return

    # backup
    bpath = Path(f"users_backup_{int(time.time())}.json")
    bpath.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    print(f"backed up current users -> {bpath}")

    # delete all except keep
    if keep_set:
        ph = ",".join(["%s"]*len(keep_set))
        _db.execute(f"DELETE FROM users WHERE username NOT IN ({ph})", tuple(keep_set))
    else:
        _db.execute("DELETE FROM users", ())

    STANDARD_HASH_NOTE = ("must_change_password set True; login = EcoStaff+last4 rule "
                          "applies if no hash shipped")
    ins = 0
    for u in users:
        if u.get("username") in keep_set:
            continue  # don't overwrite preserved admin
        md = u.get("metadata") or {}
        pwd = u.get("password_hash") if has_hashes else None
        _db.execute(
            """INSERT INTO users
               (username, password_hash, full_name, email, role, department, unit,
                staff_code, band, gender, active, is_admin, can_view_all,
                must_change_password, metadata)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (username) DO UPDATE SET
                 password_hash=EXCLUDED.password_hash,
                 full_name=EXCLUDED.full_name, role=EXCLUDED.role,
                 department=EXCLUDED.department, unit=EXCLUDED.unit,
                 staff_code=EXCLUDED.staff_code, active=EXCLUDED.active,
                 metadata=EXCLUDED.metadata""",
            (u.get("username"), pwd, u.get("full_name"), u.get("email",""),
             u.get("role"), u.get("department",""), u.get("unit",""),
             u.get("staff_code"), u.get("band",""), u.get("gender",""),
             u.get("active", True), u.get("is_admin", False),
             u.get("can_view_all", False),
             u.get("must_change_password", not has_hashes),
             json.dumps(md)))
        ins += 1

    after = _db.fetch_all("SELECT COUNT(*) AS c FROM users")
    print(f"\ninserted {ins}. users table now: {after[0].get('c') if after else '?'}")
    print("Restart the API server, then staff log in with their domain accounts.")
    if not has_hashes:
        print("NOTE: no hashes shipped — logins use EcoStaff+last4; users may need first-login reset.")

if __name__ == "__main__":
    main()

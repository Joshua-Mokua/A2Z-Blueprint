"""scripts/seed_test_logins.py — one protected test login per canonical role.

WHY
---
During the frontend phase we need to view the React UI through every
role's eyes (nav, permissions, manager-only actions, cascade scope, CEO
dashboard). This seeds ONE stable, loginable test account per canonical
role from utils.role_taxonomy, all exempted from forced rotation and
marked _protected so the admin UI won't delete them.

`users.json` is intentionally the test-login file (the real 487-staff
population lives in PostgreSQL); this script only adds/refreshes the
test accounts and never touches the migrated population.

CONVENTIONS
-----------
- username : slug of the role (lowercase, underscores). The top-exec role
             is pinned to `william001` for continuity with existing use.
- password : EcoStaff + last-4 of the account's staff_code (system
             convention; william001 -> EcoStaff0001).
- flags    : active=True, must_change_password=False, _protected=True.
- can_view_all=True for ALL test accounts so every role can actually SEE
  data in the UI during inspection. Role-based nav/permission differences
  (e.g. Manager Queues) still render correctly because those derive from
  the ROLE, not from can_view_all. To test cascade scope-HIDING for a
  given role, flip its can_view_all to False afterwards.

SAFETY
------
- Backs up data/users.json (timestamped) before any write (Trap #12).
- Aborts if users.json is missing/empty (won't let UserManager fall back
  to its 3-account defaults).
- Writes TEST_LOGINS.md — the full username/role/password key.

USAGE (project root, venv active)
---------------------------------
  python scripts\\seed_test_logins.py            # create/refresh + write key
  python scripts\\seed_test_logins.py --dry-run  # preview, no writes
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Roles pinned to a specific username for continuity / convenience.
USERNAME_OVERRIDES = {
    "Chief Executive & Managing Director": "william001",
}
# staff_code (and thus password suffix) pinned for those usernames.
STAFFCODE_OVERRIDES = {
    "william001": "0001",  # -> password EcoStaff0001
}


def _slug(role: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", role.lower()).strip("_")
    return re.sub(r"_+", "_", s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from utils.core import DATA_DIR, UserManager  # type: ignore
    from utils.role_taxonomy import list_all_classified_roles  # type: ignore

    users_file = DATA_DIR / "users.json"
    raw = users_file.read_text(encoding="utf-8") if users_file.exists() else ""
    if not raw.strip():
        print(f"ABORT: {users_file} missing/empty — refusing to run.")
        return 2

    roles = list_all_classified_roles()
    role_names = sorted(
        (r.get("role") if isinstance(r, dict) else str(r)) for r in roles
    )

    um = UserManager()

    # ── backup before mutation ─────────────────────────────────────────
    if not args.dry_run:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = users_file.with_name(f"users.json.bak-{stamp}")
        shutil.copy2(users_file, backup)
        print(f"Backup written: {backup}")

    # ── assign staff codes (skip 0001, reserved for william001) ────────
    rows = []          # (username, role, staff_code, password)
    next_code = 2
    for role in role_names:
        username = USERNAME_OVERRIDES.get(role, _slug(role))
        if username in STAFFCODE_OVERRIDES:
            code = STAFFCODE_OVERRIDES[username]
        else:
            code = f"{next_code:04d}"
            next_code += 1
        password = "EcoStaff" + code[-4:]
        rows.append((username, role, code, password))

    # ── create / refresh ───────────────────────────────────────────────
    created = 0
    for username, role, code, password in rows:
        if args.dry_run:
            print(f"  would seed {username:<40} role={role}")
            continue
        um.add_user(
            username, password, f"Test {role}",
            role=role, staff_code=code,
            can_view_all=True, can_execute=True,
        )
        um.users[username]["_protected"] = True
        um.users[username]["must_change_password"] = False
        created += 1

    if args.dry_run:
        print(f"\nDRY RUN — {len(rows)} accounts would be seeded.")
        return 0

    um.save_users()

    # ── write the credential key ───────────────────────────────────────
    md = ["# TEST_LOGINS — per-role test accounts",
          "",
          f"_Generated {_dt.datetime.now().isoformat(timespec='seconds')} by "
          "scripts/seed_test_logins.py. All accounts: active, no forced "
          "rotation, _protected, can_view_all=True._",
          "",
          "| Username | Role | Password |",
          "|---|---|---|"]
    for username, role, code, password in rows:
        md.append(f"| `{username}` | {role} | `{password}` |")
    md.append("")
    (ROOT / "TEST_LOGINS.md").write_text("\n".join(md), encoding="utf-8")

    print(f"\nSeeded {created} role test accounts.")
    print(f"Credential key written: TEST_LOGINS.md")
    print("Top-exec login: william001 / EcoStaff0001 "
          "(Chief Executive & Managing Director).")
    print("\nNOTE: re-run this after any users.json reset to restore the set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""scripts/fix_test_logins.py — unblock test-account logins.

WHY THIS EXISTS
---------------
The staff generators (generate_staff.py, generate_staff_v2.py) stamp
`must_change_password: True` on every non-protected account. After any
staff-data regeneration, test accounts like william001 authenticate
successfully but receive a must_rotate-scope token that every endpoint
except /change-password rejects — which presents as "can't log in."

This tool clears that trap for named accounts (sets must_change_password
=False, active=True), without touching passwords by default. It drives
UserManager directly so the on-disk format and any bcrypt hashing match
the app exactly.

SAFETY
------
- Backs up data/users.json to data/users.json.bak-YYYYMMDD-HHMMSS before
  any write (Trap #12 — backup before mutation).
- Aborts if users.json is missing/empty (never lets UserManager fall back
  to its 3-account defaults and clobber a real file).
- Prints only REDACTED credential shape (bcrypt / sha256 / plaintext +
  length) — never a raw hash or password (Trap #13).

USAGE (run from project root, venv active)
------------------------------------------
  python scripts\\fix_test_logins.py --list
      Show every currently-loginable account (active and not forced to
      rotate). Read-only.

  python scripts\\fix_test_logins.py william001
      Unblock william001 (clear must_change_password, ensure active).

  python scripts\\fix_test_logins.py william001 olive001 jason001
      Unblock several accounts at once.

  python scripts\\fix_test_logins.py william001 --reset-pw
      Also reset the password to the canonical EcoStaff+<last4 of staff
      code> (use only if login still fails after the flag fix, meaning
      the stored hash genuinely diverged).

  python scripts\\fix_test_logins.py william001 --protect
      Also mark the account _protected so the admin UI won't delete it
      (does NOT survive a full staff regeneration — see the note printed
      at the end for the durable fix).

  Add --dry-run to preview changes without writing.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

# Make `import utils.core` work when run from the project root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pw_shape(stored: str) -> str:
    """Redacted description of a stored credential — never the value."""
    if not isinstance(stored, str) or not stored:
        return "MISSING"
    if stored.startswith(("$2a$", "$2b$", "$2y$")):
        return f"bcrypt(len={len(stored)})"
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored.lower()):
        return "sha256-hex"
    return f"plaintext(len={len(stored)})"


def _redacted(username: str, u: dict) -> str:
    return (
        f"{username:<16} active={u.get('active')!s:<5} "
        f"must_change_password={u.get('must_change_password')!s:<5} "
        f"protected={bool(u.get('_protected'))!s:<5} "
        f"pw={_pw_shape(u.get('password', ''))} "
        f"staff_code={u.get('staff_code', '')}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Unblock test-account logins.")
    ap.add_argument("usernames", nargs="*", help="accounts to unblock")
    ap.add_argument("--list", action="store_true",
                    help="list currently-loginable accounts and exit")
    ap.add_argument("--reset-pw", action="store_true",
                    help="reset password to EcoStaff+<last4 of staff code>")
    ap.add_argument("--protect", action="store_true",
                    help="mark account _protected (anti-delete)")
    ap.add_argument("--dry-run", action="store_true",
                    help="preview without writing")
    args = ap.parse_args()

    from utils.core import DATA_DIR, UserManager  # type: ignore

    users_file = DATA_DIR / "users.json"
    raw = users_file.read_text(encoding="utf-8") if users_file.exists() else ""
    if not raw.strip():
        print(f"ABORT: {users_file} is missing or empty. Refusing to run so "
              f"UserManager can't fall back to default accounts.")
        return 2

    um = UserManager()  # loads DATA_DIR/users.json

    # ── --list mode (read-only) ────────────────────────────────────────
    if args.list or not args.usernames:
        loginable = sorted(
            uname for uname, u in um.users.items()
            if u.get("active") and not u.get("must_change_password")
        )
        blocked = sorted(
            uname for uname, u in um.users.items()
            if u.get("active") and u.get("must_change_password")
        )
        print(f"\nLoginable now (active, no forced rotation): {len(loginable)}")
        for uname in loginable[:40]:
            print("  ✓", _redacted(uname, um.users[uname]))
        if len(loginable) > 40:
            print(f"  … (+{len(loginable) - 40} more)")
        print(f"\nActive but trapped in must_change_password: {len(blocked)}")
        for uname in blocked[:40]:
            print("  ⚠", _redacted(uname, um.users[uname]))
        if len(blocked) > 40:
            print(f"  … (+{len(blocked) - 40} more)")
        if not args.usernames:
            print("\nPass one or more usernames to unblock them, e.g.:")
            print("  python scripts\\fix_test_logins.py william001")
        return 0

    # ── backup before any mutation (Trap #12) ──────────────────────────
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = users_file.with_name(f"users.json.bak-{stamp}")
    if not args.dry_run:
        shutil.copy2(users_file, backup)
        print(f"Backup written: {backup}")

    changed = 0
    for uname in args.usernames:
        u = um.users.get(uname)
        if u is None:
            print(f"  ✗ {uname}: NOT FOUND — skipping")
            continue
        print(f"  before: {_redacted(uname, u)}")
        u["active"] = True
        u["must_change_password"] = False
        if args.protect:
            u["_protected"] = True
        if args.reset_pw:
            sc = str(u.get("staff_code", "") or "")
            if len(sc) >= 4:
                new_pw = "EcoStaff" + sc[-4:]
                u["password"] = um.hash_pw(new_pw)
                print(f"          password reset to canonical EcoStaff+{sc[-4:]}")
            else:
                print(f"          (no usable staff_code; password left as-is)")
        print(f"  after:  {_redacted(uname, u)}")
        changed += 1

    if args.dry_run:
        print("\nDRY RUN — no changes written.")
        return 0

    if changed:
        um.save_users()
        print(f"\nSaved. {changed} account(s) updated.")
        print("Try logging in again with EcoStaff+<last4 of staff code> "
              "(e.g. william001 -> EcoStaff0001).")
    else:
        print("\nNothing changed.")
    print("\nNOTE: this fixes the CURRENT users.json. A full staff "
          "regeneration will re-stamp must_change_password=True unless the "
          "generators are taught to exempt these usernames — say the word "
          "and I'll ship that durable guard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

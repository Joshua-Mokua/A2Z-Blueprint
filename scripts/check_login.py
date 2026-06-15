"""scripts/check_login.py — diagnose why a login fails (redacted output).

Usage:  python scripts/check_login.py <username> [password]

Shows whether the account exists, is active, and whether the password
verifies — WITHOUT printing the stored hash (only its format/length, per the
no-raw-credentials rule). Tests the real UserManager.authenticate path used by
/api/auth/login.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def fmt(stored: str) -> str:
    if not stored:
        return "EMPTY"
    if stored.startswith(("$2b$", "$2a$", "$2y$")):
        return f"bcrypt (len {len(stored)})  ✓ verifiable"
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored.lower()):
        return "sha256-hex (len 64)  ✓ verifiable (legacy path)"
    return f"PLAINTEXT-or-unknown (len {len(stored)})  ✗ NOT verifiable"


def main():
    if len(sys.argv) < 2:
        print("usage: python scripts/check_login.py <username> [password]")
        return
    username = sys.argv[1]
    from utils.core import UserManager  # type: ignore
    um = UserManager()
    u = um.users.get(username)
    if not u:
        print(f"[X] '{username}' is NOT in users.json.")
        print("    -> the branch seed didn't create it. Re-run:")
        print("       python scripts/seed_branch_test_logins.py --branch Thika")
        hits = [(k, v.get("staff_code"), v.get("role"))
                for k, v in um.users.items()
                if str(v.get("staff_code", "")).startswith("300")][:12]
        if hits:
            print("    Register-staff accounts currently present:")
            for k, c, r in hits:
                print(f"       {k:18s} staff_code={c}  role={r}")
        else:
            print("    (No register-staff (300xxx) accounts present at all — seed never ran.)")
        return
    code = str(u.get("staff_code", ""))
    pw = sys.argv[2] if len(sys.argv) > 2 else "EcoStaff" + code[-4:]
    print(f"username       : {username}")
    print(f"exists         : yes")
    print(f"active         : {u.get('active')}")
    print(f"must_change_pw : {u.get('must_change_password')}")
    print(f"staff_code     : {code}")
    print(f"role           : {u.get('role')}")
    print(f"password field : {fmt(u.get('password', ''))}")
    print(f"trying password: '{pw}'")
    ok, _ = um.authenticate(username, pw)
    print(f"AUTH RESULT    : {'PASS ✓' if ok else 'FAIL ✗'}")
    if not ok:
        print("  If password field is PLAINTEXT -> you ran the OLD seed; apply v10.566")
        print("     and re-run: python scripts/seed_branch_test_logins.py --branch Thika")
        print("  If active is False/None -> account inactive.")


if __name__ == "__main__":
    main()

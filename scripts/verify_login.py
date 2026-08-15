#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does this login actually work? And reset it if not. DRY RUN by default.

Passwords are bcrypt-hashed since the Phase 1 auth work, so nothing can print
them. What CAN be answered is whether a given password verifies - and that is
the only question a tester has.

    python scripts\\verify_login.py --user KE439
    python scripts\\verify_login.py --user KE439 --try EcoStaff0439
    python scripts\\verify_login.py --user KE439 --set EcoStaff0439 --apply

--set writes a new password through the SAME path the application uses, so the
record stays in whatever envelope the system expects. It is for pilot and test
logins; it says so, loudly, if the account looks like a real one.
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

USERS = os.path.join("data", "users.json")


def main():
    login = new = trial = ""
    for flag, dest in (("--user", "login"), ("--try", "trial"), ("--set", "new")):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                v = sys.argv[i + 1].strip()
                if dest == "login": login = v
                elif dest == "trial": trial = v
                else: new = v
    apply = "--apply" in sys.argv
    if not login:
        print("ABORT: --user <login or staff code> is required.")
        return 1

    from utils.core import UserManager
    um = UserManager()
    users = um.users or {}

    key = None
    if login in users:
        key = login
    else:
        for k, v in users.items():
            if str(v.get("staff_code", "")).strip().lower() == login.lower():
                key = k
                break
    if not key:
        print("ABORT: no login %r, and no record with that staff code." % login)
        return 1

    rec = users[key]
    stored = str(rec.get("password", "") or "")
    hashed = stored.startswith("$2")

    print("=" * 74)
    print("LOGIN %s" % key)
    print("=" * 74)
    print("  name        %s" % (rec.get("full_name") or "—"))
    print("  role        %s" % (rec.get("role") or "—"))
    print("  unit        %s" % (rec.get("unit") or "—"))
    print("  staff_code  %s" % (rec.get("staff_code") or "—"))
    print("  active      %s%s" % (rec.get("active"),
                                  "   <- INACTIVE ACCOUNTS CANNOT SIGN IN"
                                  if not rec.get("active") else ""))
    print("  must change %s" % rec.get("must_change_password"))
    print("  password    %s" % ("bcrypt hash - cannot be read"
                                if hashed else "PLAIN TEXT (%s)" % stored))

    if not rec.get("active"):
        print("\n  *** This account is inactive. authenticate() refuses it")
        print("      regardless of the password.")

    # ── Does a candidate password verify? ───────────────────────────────────
    candidates = [trial] if trial else []
    if not candidates:
        digits = "".join(ch for ch in str(rec.get("staff_code", "")) if ch.isdigit())
        if digits:
            candidates = ["EcoStaff%s" % digits[-4:].zfill(4),
                          "EcoStaff%s" % digits,
                          "EcoStaff%s" % digits.zfill(4)]
        candidates = list(dict.fromkeys(candidates))

    if candidates:
        print("\n  TRYING %d candidate password(s) through authenticate():"
              % len(candidates))
        worked = None
        for c in candidates:
            try:
                # authenticate returns a TUPLE - (False, None) or (True, user).
                # bool() on a two-element tuple is ALWAYS True, so testing it
                # directly reports every password as correct, including an
                # empty one. I briefly took that for an auth bypass; it was my
                # check. Unpack it.
                res = um.authenticate(key, c)
                ok = bool(res[0]) if isinstance(res, (tuple, list)) else bool(res)
            except Exception as exc:
                print("     %-18s raised: %s" % (c, str(exc)[:44]))
                continue
            print("     %-18s %s" % (c, "WORKS" if ok else "no"))
            if ok and not worked:
                worked = c
        if worked:
            print("\n  Sign in with:  %s / %s" % (key, worked))
            return 0
        print("\n  None of those work. Set one with:")
        print("     python scripts\\verify_login.py --user %s --set <password> --apply" % key)

    if not new:
        return 1

    # ── Set a new one ───────────────────────────────────────────────────────
    if rec.get("_protected"):
        print("\nABORT: %s is marked protected. Not touching it." % key)
        return 1
    print("\n  Setting a new password for %s." % key)
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    # Write it the way the application does, so the envelope matches.
    try:
        from utils.core import hash_password as _hp
        rec["password"] = _hp(new)
        how = "hashed by the application's own hasher"
    except Exception:
        try:
            import bcrypt
            rec["password"] = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
            how = "bcrypt"
        except Exception:
            rec["password"] = new
            how = "PLAIN TEXT - this box has no hasher available"
    rec["must_change_password"] = False
    rec["active"] = True

    bak = USERS + ".pre_pwd_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(USERS, bak)
    json.dump(users, open(USERS, "w", encoding="utf-8"), indent=2)
    print("  written (%s).  (backup: %s)" % (how, os.path.basename(bak)))
    print("\n  Sign in with:  %s / %s" % (key, new))
    print("  RESTART UVICORN if the user store is cached in the running process.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

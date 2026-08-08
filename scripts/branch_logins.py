#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Working logins for a branch team. READ ONLY — verifies, never writes.

For every staff member in the branch it finds their users.json record and TESTS
candidate passwords against the stored hash via UserManager.verify_pw. Only
credentials that actually authenticate are printed, so nothing here is a guess.

    python scripts\\branch_logins.py
    python scripts\\branch_logins.py Westlands
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def candidates(code: str, name: str):
    """Password patterns seen in this deployment, most likely first."""
    c = str(code).strip()
    digits = "".join(ch for ch in c if ch.isdigit())
    out = [
        "EcoStaff" + c[-4:],          # last 4 CHARACTERS  (KE754 -> EcoStaffE754)
        "EcoStaff" + digits[-4:],     # last 4 DIGITS      (KE1034 -> EcoStaff1034)
        "EcoStaff" + digits.zfill(4)[-4:],
        "EcoStaff" + c,
    ]
    first = str(name).split()[0].lower() if name else ""
    if first and digits:
        out.append(first + digits[-4:].zfill(4))
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def main():
    branch = sys.argv[1] if len(sys.argv) > 1 else "Fortis"

    try:
        import pandas as pd
    except ImportError:
        print("pandas not available.")
        return 1

    reg = os.path.join("data", "staff_register.xlsx")
    if not os.path.isfile(reg):
        print("ABORT: %s not found." % reg)
        return 1
    df = pd.read_excel(reg)
    col = "Branch" if "Branch" in df.columns else "Unit"
    people = df[df[col].astype(str).str.strip().str.lower() == branch.strip().lower()]
    if people.empty:
        print("No staff in %r." % branch)
        return 1

    from utils.core import UserManager
    um = UserManager()
    users = um.users

    # users.json may be keyed by username; build a staff_code index too.
    by_code = {}
    for uname, rec in users.items():
        if isinstance(rec, dict):
            sc = str(rec.get("staff_code", "") or "").strip()
            if sc:
                by_code.setdefault(sc, (uname, rec))

    try:
        from utils.org_validator import _triad_roles
        triad = [t.lower() for t in _triad_roles()]
    except Exception:
        triad = []

    print("=" * 88)
    print("%s — verified logins   (username / password / role)" % branch)
    print("=" * 88)

    ok = miss = nopw = 0
    for _, r in people.iterrows():
        code = str(r.get("Staff Code", "")).strip()
        name = str(r.get("Staff Name", "")).strip()
        role = str(r.get("Role", "")).strip()
        star = "  <-- TRIAD" if role.lower() in triad else ""

        hit = by_code.get(code)
        if not hit and code in users:
            hit = (code, users[code])
        if not hit:
            print("  %-9s %-26s %-44s NOT IN users.json" % (code, name[:26], role[:44]))
            miss += 1
            continue

        uname, rec = hit
        stored = rec.get("password", "") or rec.get("password_hash", "")
        found = ""
        for cand in candidates(code, name):
            try:
                if um.verify_pw(cand, stored, username=uname):
                    found = cand
                    break
            except Exception:
                continue

        if found:
            active = "" if rec.get("active", True) else "   (INACTIVE)"
            print("  %-9s %-16s %-26s %-38s%s%s"
                  % (code, uname, found, role[:38], active, star))
            ok += 1
        else:
            print("  %-9s %-16s %-26s %-38s%s"
                  % (code, uname, "(no pattern matched)", role[:38], star))
            nopw += 1

    print("")
    print("verified: %d   no matching pattern: %d   not in users.json: %d"
          % (ok, nopw, miss))
    if nopw:
        print("")
        print("For any 'no pattern matched', the password was set outside the")
        print("convention. scripts/make_demo_logins.py can reset those.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

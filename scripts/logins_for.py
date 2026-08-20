#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Who can sign in, for a function or a unit. READ ONLY.

    python scripts\\logins_for.py --function commercial
    python scripts\\logins_for.py --unit "Head Office"
    python scripts\\logins_for.py --function commercial --unit "Head Office"
    python scripts\\logins_for.py --role "Relationship Manager"

Lists the login, the staff code, the role, and whether the account is active
and can actually authenticate. It does NOT print passwords: it shows the
CONVENTION, and flags anybody whose password does not follow it, because those
are the accounts that will fail in a demo and nobody will know why.

FUNCTIONS are groups of role words, so you do not have to know how the register
spells a title:

    commercial   commercial, corporate, SME, agribusiness, trade, diaspora,
                 institutional, business banking, cash management
    retail       retail, branch, teller, customer service, personal banking
    credit       credit, risk, remedial, recoveries
    treasury     treasury, FX, dealer, ALM
    legal        legal, company secretary
    exco         MD, chief, director, head of

Nothing is written.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

FUNCTIONS = {
    "commercial": ("commercial", "corporate", "sme", "agribusiness", "trade",
                   "diaspora", "institutional", "business banking",
                   "cash management", "transaction banking"),
    "retail": ("retail", "branch", "teller", "customer service",
               "personal banking", "consumer"),
    "credit": ("credit", "risk", "remedial", "recover"),
    "treasury": ("treasury", "fx ", "dealer", "alm", "ficc"),
    "legal": ("legal", "company secretary"),
    "exco": ("managing director", "chief", "director", "head of"),
}


def main():
    func = unit = role = ""
    for flag in ("--function", "--unit", "--role"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                v = sys.argv[i + 1].strip()
                if flag == "--function":
                    func = v.lower()
                elif flag == "--unit":
                    unit = v.lower()
                else:
                    role = v.lower()
    if not (func or unit or role):
        print("Give at least one of --function, --unit or --role.\n")
        print("  functions: %s" % ", ".join(sorted(FUNCTIONS)))
        return 1
    if func and func not in FUNCTIONS:
        print("ABORT: unknown function %r. Known: %s"
              % (func, ", ".join(sorted(FUNCTIONS))))
        return 1

    from utils.core import UserManager
    users = UserManager().users or {}
    words = FUNCTIONS.get(func, ())

    rows = []
    for login, rec in users.items():
        r = str(rec.get("role", "") or "")
        un = str(rec.get("unit", "") or rec.get("department", "") or "")
        rl, ul = r.lower(), un.lower()
        if words and not any(w in rl or w in ul for w in words):
            continue
        if unit and unit not in ul:
            continue
        if role and role not in rl:
            continue
        rows.append((login, rec, r, un))

    rows.sort(key=lambda x: (str(x[3]), str(x[2]), str(x[0])))

    what = " / ".join(x for x in (func, unit, role) if x)
    print("=" * 92)
    print("WHO CAN SIGN IN  —  %s" % what)
    print("=" * 92)
    if not rows:
        print("  Nobody matches. Try a broader --function, or --unit alone.")
        return 0

    print("  %-16s %-9s %-28s %-24s %s"
          % ("LOGIN", "CODE", "NAME", "ROLE", "STATUS"))
    odd = []
    for login, rec, r, un in rows:
        code = str(rec.get("staff_code", "") or "")
        active = bool(rec.get("active"))
        pw = str(rec.get("password", "") or "")
        expected = "EcoStaff" + code[-4:] if len(code) >= 4 else ""
        status = "active" if active else "*** INACTIVE ***"
        if active and expected and pw and pw != expected and not pw.startswith("$2"):
            status += "  password not the convention"
            odd.append((login, code))
        print("  %-16s %-9s %-28s %-24s %s"
              % (login[:16], code, str(rec.get("full_name", ""))[:28], r[:24], status))

    print("\n  %d account(s). Password convention: EcoStaff + the last four of" % len(rows))
    print("  the staff code — KE1265 signs in with EcoStaff1265.")
    if odd:
        print("\n  *** These will NOT accept the convention password:")
        for login, code in odd[:8]:
            print("        %-16s %s" % (login, code))
        print("      Reset one with:  python scripts\\verify_login.py --user %s"
              % odd[0][0])
        print("                       --set EcoStaff%s --apply" % odd[0][1][-4:])

    inactive = [x for x in rows if not x[1].get("active")]
    if inactive:
        print("\n  *** %d cannot sign in at all (active is false)." % len(inactive))
    return 0


if __name__ == "__main__":
    sys.exit(main())

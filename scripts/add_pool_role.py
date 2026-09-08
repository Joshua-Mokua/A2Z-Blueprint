#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Add a role to the credit work pool.

A case reaches an analyst two ways: it is assigned to them, or their ROLE is in
the pool list and the case's STATUS is in the pool statuses. That is how a
branch-approved case reaches the segment analysts without anyone assigning it.

Korir is a Credit Risk Manager. The pool roles list six roles and none of them
matches, so the pool never opens for him - however far the cases have come.

    python scripts/add_pool_role.py
    python scripts/add_pool_role.py --role "credit risk" --apply

Roles match as case-insensitive substrings, so "credit risk" covers Credit Risk
Manager, Credit Risk Officer and Head of Credit Risk.

Read only without --apply.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")


def main():
    apply = "--apply" in sys.argv
    role = ""
    if "--role" in sys.argv:
        i = sys.argv.index("--role")
        if i + 1 < len(sys.argv):
            role = sys.argv[i + 1].strip()

    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pv = cfg.get("pool_visibility") or {}
    roles = [str(r) for r in (pv.get("roles") or [])]
    statuses = [str(s) for s in (pv.get("statuses") or [])]

    print("=" * 76)
    print("WHO SEES THE CREDIT WORK POOL")
    print("=" * 76)
    print("  roles (substring, case-insensitive)")
    for r in roles:
        print("     %s" % r)
    print("\n  statuses in the pool")
    print("     %s" % ", ".join(statuses))

    # Who in the bank would and would not match.
    try:
        sys.path.insert(0, os.getcwd())
        from utils.core import UserManager
        users = [v for v in (UserManager().users or {}).values() if v.get("active")]
        low = [r.lower() for r in roles]
        seen, missed = set(), {}
        for u in users:
            rr = str(u.get("role", "") or "")
            if any(x in rr.lower() for x in low):
                seen.add(rr)
            elif "credit" in rr.lower() or "risk" in rr.lower():
                missed[rr] = missed.get(rr, 0) + 1
        if missed:
            print("\n  CREDIT-SIDE ROLES THAT DO NOT MATCH ANY OF THE ABOVE")
            for rr, n in sorted(missed.items(), key=lambda x: -x[1]):
                print("     %-44s %d person(s)" % (rr[:44], n))
            print("\n  These people see only their own assigned cases and their")
            print("  cascade. The pool never opens for them.")
    except Exception as exc:
        print("\n  (could not read the staff list: %s)" % str(exc)[:50])

    if not role:
        print("\n  To add one:")
        print('     python scripts/add_pool_role.py --role "credit risk" --apply')
        return 0

    if any(role.strip().lower() == r.strip().lower() for r in roles):
        print("\n  %r is already in the list." % role)
        return 0

    print("\n  Adding %r." % role)
    print("  It matches as a substring, so it covers every role containing it.")
    try:
        matches = sorted({str(u.get("role", "")) for u in users
                          if role.lower() in str(u.get("role", "")).lower()})
        if matches:
            print("\n  This will open the pool to:")
            for m in matches:
                print("     %s" % m)
        else:
            print("\n  Nobody active holds a role containing %r. Check the" % role)
            print("  spelling against the register before applying.")
    except Exception:
        pass

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_pool_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    cfg.setdefault("pool_visibility", {})
    cfg["pool_visibility"]["roles"] = roles + [role]
    cfg["pool_visibility"]["statuses"] = statuses
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn. Cases already at a pool status appear immediately -")
    print("nothing needs reassigning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

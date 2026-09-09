#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Which roles see every deal in the bank.

    python scripts/set_all_view_roles.py
    python scripts/set_all_view_roles.py --add "credit risk manager" --apply

This is a real grant: the role sees the whole book, every branch, every
segment. Matched on the WHOLE role string, lowercased - not a substring - so
"credit risk manager" does not also catch "credit risk officer". Add each
spelling you mean.

Read only without --apply.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "org_config.json")


def main():
    apply = "--apply" in sys.argv
    add = ""
    if "--add" in sys.argv:
        i = sys.argv.index("--add")
        if i + 1 < len(sys.argv):
            add = sys.argv[i + 1].strip()

    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    extra = [str(r) for r in (cfg.get("all_view_roles") or [])]

    print("=" * 74)
    print("ROLES THAT SEE EVERY DEAL")
    print("=" * 74)
    print("  built in: managing director, chief executive, admin,")
    print("            head of branches (and spelling variants)")
    print("\n  added by the bank:")
    if extra:
        for r in extra:
            print("     %s" % r)
    else:
        print("     none")

    try:
        sys.path.insert(0, os.getcwd())
        from utils.core import UserManager
        users = [v for v in (UserManager().users or {}).values() if v.get("active")]
        low = {r.strip().lower() for r in extra}
        if low:
            who = [u for u in users
                   if str(u.get("role", "")).strip().lower() in low]
            print("\n  people this covers: %d" % len(who))
            for u in who[:10]:
                print("     %-26s %s" % (str(u.get("full_name"))[:26], u.get("role")))
    except Exception as exc:
        print("\n  (could not read the staff list: %s)" % str(exc)[:50])

    if not add:
        print("\n  To add one:")
        print('     python scripts/set_all_view_roles.py --add "credit risk manager" --apply')
        return 0
    if any(add.strip().lower() == r.strip().lower() for r in extra):
        print("\n  %r is already there." % add)
        return 0

    print("\n  Adding %r." % add)
    print("  Matched on the WHOLE role string, so add each spelling you mean.")
    try:
        exact = [u for u in users
                 if str(u.get("role", "")).strip().lower() == add.strip().lower()]
        print("\n  This will cover %d person(s):" % len(exact))
        for u in exact:
            print("     %-26s %s" % (str(u.get("full_name"))[:26], u.get("role")))
        if not exact:
            near = sorted({str(u.get("role", "")) for u in users
                           if add.split()[0].lower() in str(u.get("role", "")).lower()})
            if near:
                print("\n  Nobody holds that exact role. Similar spellings:")
                for r in near[:8]:
                    print("     %s" % r)
                print("  Check before applying - a near miss grants nothing.")
    except Exception:
        pass

    print("\n  This is a real grant: the whole book, every branch and segment.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_allview_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    cfg["all_view_roles"] = extra + [add]
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

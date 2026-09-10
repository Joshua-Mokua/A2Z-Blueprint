#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Who may complete a disbursement.

The default is ["Treasury Back Office"]. The register writes the settlement
team as "Service Officer, TROPS" and "Team Leader-Trade & Trops", which matches
nothing - so nobody in the bank can disburse.

    python scripts/set_disbursement_roles.py
    python scripts/set_disbursement_roles.py --add trops --apply

Roles match as case-insensitive substrings. Read only without --apply.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "pipeline_settings.json")


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
    roles = [str(r) for r in (cfg.get("disbursement_roles") or ["Treasury Back Office"])]

    print("=" * 76)
    print("WHO MAY DISBURSE")
    print("=" * 76)
    for r in roles:
        print("     %s" % r)

    try:
        sys.path.insert(0, os.getcwd())
        from utils.core import UserManager
        users = [v for v in (UserManager().users or {}).values() if v.get("active")]
        low = [r.lower() for r in roles]
        can = [u for u in users
               if any(x in str(u.get("role", "")).lower() for x in low)
               or any(k in str(u.get("role", "")).lower()
                      for k in ("chief", "managing", "director"))
               or u.get("is_admin")]
        print("\n  people who match: %d" % len(can))
        for u in can[:10]:
            print("     %-26s %s" % (str(u.get("full_name"))[:26], u.get("role")))
        if not can:
            print("     NOBODY. The first disbursement will be refused.")
        settle = sorted({str(u.get("role", "")) for u in users
                         if "trop" in str(u.get("role", "")).lower()})
        if settle:
            print("\n  settlement roles in the register:")
            for r in settle:
                mark = "" if any(x in r.lower() for x in low) else "   <-- no match"
                print("     %-44s%s" % (r[:44], mark))
    except Exception as exc:
        print("\n  (could not read the staff list: %s)" % str(exc)[:50])

    if not add:
        print("\n  To add one:")
        print("     python scripts/set_disbursement_roles.py --add trops --apply")
        return 0
    if any(add.lower() == r.lower() for r in roles):
        print("\n  %r is already there." % add)
        return 0

    print("\n  Adding %r. It matches as a substring, so it covers every role" % add)
    print("  containing it.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_disb_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    cfg["disbursement_roles"] = roles + [add]
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

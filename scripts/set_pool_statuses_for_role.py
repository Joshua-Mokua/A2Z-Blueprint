#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Narrow what one pool role sees.

    python scripts/set_pool_statuses_for_role.py
    python scripts/set_pool_statuses_for_role.py --role "credit risk" \
        --statuses approved --apply

A role listed here sees only those statuses. Every other role keeps the shared
list. Read only without --apply.
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
    statuses = ""
    for flag in ("--role", "--statuses"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--role":
                    role = sys.argv[i + 1].strip()
                else:
                    statuses = sys.argv[i + 1].strip()

    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pv = cfg.get("pool_visibility") or {}
    shared = [str(x) for x in (pv.get("statuses") or [])]
    per = dict(pv.get("role_statuses") or {})

    print("=" * 76)
    print("WHAT EACH POOL ROLE SEES")
    print("=" * 76)
    print("  shared list (any role without its own)")
    print("     %s\n" % ", ".join(shared))
    if per:
        print("  narrowed")
        for k, v in per.items():
            print("     %-24s %s" % (k, ", ".join(str(x) for x in v)))
    else:
        print("  narrowed: none - every role sees the shared list")

    if not role or not statuses:
        print("\n  To narrow one:")
        print('     python scripts/set_pool_statuses_for_role.py \\')
        print('         --role "credit risk" --statuses approved --apply')
        print("\n  Statuses are comma-separated. Use the names from the shared")
        print("  list above.")
        return 0

    want = [s.strip() for s in statuses.split(",") if s.strip()]
    unknown = [s for s in want if s.lower() not in
               {x.strip().lower() for x in shared}]
    print("\n  %r will see only: %s" % (role, ", ".join(want)))
    if unknown:
        print("\n  These are not in the shared list: %s" % ", ".join(unknown))
        print("  A status nothing ever carries means the role sees nothing.")
        print("  Check the spelling before applying.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_poolst_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    per[role] = want
    cfg.setdefault("pool_visibility", {})
    cfg["pool_visibility"]["role_statuses"] = per
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

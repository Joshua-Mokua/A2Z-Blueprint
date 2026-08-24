#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Hide a module from the sidebar, for THIS deployment only. DRY RUN by default.

RULING (2026-08-24): "on the bank side we need to hide the dashboard, i.e. the
first item on the sidebar for now - it is having misleading information."

A dashboard showing figures nobody has validated is worse than no dashboard.
An RM reads it as the bank's position and repeats it in a meeting.

NO CODE CHANGE IS NEEDED. The sidebar already reads `hidden_modules` from
org_config.json - a file each deployment owns - so the pilot hides a module in
ITS config and the developer's box keeps it. That is why the list is empty in
the source and must stay empty: a hardcoded hide would remove the module from
both sides, and there is no reason the person building it should lose a screen
the bank is not ready to show.

    python scripts\hide_modules.py
    python scripts\hide_modules.py --hide /
    python scripts\hide_modules.py --hide /,/initiatives,/profitability --apply
    python scripts\hide_modules.py --show / --apply

KEYED ON ROUTE, NOT LABEL. "EKE Sales Pro" and "A2Z Sales Pro" are the same
module under two brandings, and a list keyed on the words would stop matching
after a rebrand.

    /                  Dashboard
    /perform           Balanced Scorecard
    /cascade           Target Cascade
    /initiatives       Initiatives
    /profitability     Profitability
    /sla               SLA Monitor
    /pipeline/warehouse  Deals Warehouse
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "org_config.json")

KNOWN = {
    "/": "Dashboard",
    "/perform": "Balanced Scorecard",
    "/cascade": "Target Cascade",
    "/initiatives": "Initiatives",
    "/profitability": "Profitability",
    "/sla": "SLA Monitor",
    "/pipeline": "A2Z Sales Pro",
    "/analytics": "Sales Pro Analytics",
    "/pipeline/queues": "Manager Queues",
    "/pipeline/channels": "Origin Channels",
    "/referrals": "Referral Analytics",
    "/branch-log": "Daily Log",
    "/pipeline/warehouse": "Deals Warehouse",
    "/portfolio": "Portfolio",
    "/lms": "Department Review / Credit Analysis",
    "/credit-admin": "Credit Admin",
    "/troops": "Trops Disbursement",
    "/treasury/rates": "Treasury Rate Desk",
    "/credit-analytics": "Credit Analytics",
    "/cbs": "Customer Lookup",
    "/admin/config": "Administration",
}


def main():
    apply = "--apply" in sys.argv
    hide, show = [], []
    for flag, into in (("--hide", hide), ("--show", show)):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                into.extend([x.strip() for x in sys.argv[i + 1].split(",")
                             if x.strip()])
    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1

    cfg = json.load(open(CFG, encoding="utf-8"))
    current = list(cfg.get("hidden_modules") or [])

    print("=" * 72)
    print("MODULES HIDDEN ON THIS DEPLOYMENT")
    print("=" * 72)
    print("  config      %s" % CFG)
    print("  hidden now  %d" % len(current))
    for r in current:
        print("     %-24s %s" % (r, KNOWN.get(r, "(unknown route)")))

    if not (hide or show):
        print("\n  ROUTES YOU CAN HIDE")
        for r, lbl in KNOWN.items():
            mark = "  <- hidden" if r in current else ""
            print("     %-24s %s%s" % (r, lbl, mark))
        print("\n  Nothing changed. Choose:")
        print("     python scripts\\hide_modules.py --hide / --apply")
        return 0

    unknown = [r for r in hide + show if r not in KNOWN]
    if unknown:
        print("\n  *** these routes are not in the sidebar: %s"
              % ", ".join(unknown))
        print("      They will still be written - a route this script does")
        print("      not know about may be real - but check the spelling.")

    after = [r for r in current if r not in show]
    for r in hide:
        if r not in after:
            after.append(r)

    print("\n  AFTER")
    if not after:
        print("     nothing hidden")
    for r in after:
        print("     %-24s %s" % (r, KNOWN.get(r, "(unknown route)")))

    if after == current:
        print("\n  No change.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_hide_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    cfg["hidden_modules"] = after
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("\nRESTART UVICORN and hard-refresh. No rebuild is needed - the")
    print("sidebar reads this at run time.")
    print("\nTHIS FILE IS THE DEPLOYMENT'S OWN. It does not travel in a")
    print("release, so hiding it here does not hide it on the pilot, and")
    print("hiding it there does not hide it here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

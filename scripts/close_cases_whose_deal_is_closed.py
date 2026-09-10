#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Close the credit case when its deal has been closed.

A deal cancelled or closed lost leaves its case behind. The case keeps its
status and its value, and every total on the credit screens keeps counting it.
The KES 1B keyed in error was closed as a deal and reopened correctly - the
old case is still 'returned' and still worth a billion on every screen.

    python scripts/close_cases_whose_deal_is_closed.py
    python scripts/close_cases_whose_deal_is_closed.py --apply

Read only without --apply. A case is closed only where its deal is closed;
nothing is inferred from the value.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())


def kes(v):
    try:
        return "KES %s" % format(int(float(v or 0)), ",")
    except (TypeError, ValueError):
        return "-"


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    from utils.api_lms_routes import _lam

    lam = _lam()
    apps = getattr(lam, "apps", []) or []
    deals = {str(d.get("id")): d for d in (PipelineManager().deals or [])}

    stale = []
    for a in apps:
        st = str(a.get("status") or "").lower()
        if st in ("closed", "withdrawn", "cancelled", "disbursed", "declined"):
            continue
        d = deals.get(str(a.get("pipeline_deal_id") or ""))
        if not d:
            continue
        ds = str(d.get("stage") or "").lower()
        if ds.startswith("closed") or d.get("cancelled") or d.get("status") == "cancelled":
            stale.append((a, d))

    total = sum(float(a.get("amount") or 0) for a in apps
                if str(a.get("status") or "").lower()
                not in ("closed", "withdrawn", "cancelled", "disbursed", "declined"))
    stale_v = sum(float(a.get("amount") or 0) for a, _d in stale)

    print("=" * 88)
    print("CASES STILL OPEN AFTER THEIR DEAL WAS CLOSED")
    print("=" * 88)
    print("  open cases          %d, %s" % (
        sum(1 for a in apps if str(a.get("status") or "").lower()
            not in ("closed", "withdrawn", "cancelled", "disbursed", "declined")),
        kes(total)))
    print("  deal closed         %d, %s\n" % (len(stale), kes(stale_v)))

    if not stale:
        print("  None. Every open case has an open deal.")
        return 0

    print("  %-11s %-28s %-14s %-22s %s"
          % ("CASE", "CLIENT", "CASE STATUS", "DEAL", "VALUE"))
    for a, d in sorted(stale, key=lambda x: -float(x[0].get("amount") or 0)):
        print("  %-11s %-28s %-14s %-22s %s"
              % (str(a.get("id"))[:11], str(a.get("client_name"))[:28],
                 str(a.get("status"))[:14],
                 "%s %s" % (d.get("id"), str(d.get("stage"))[:12]),
                 kes(a.get("amount"))))

    share = (stale_v / total * 100) if total else 0
    print("\n  %s of the %s on the credit screens - %.0f%% - is deals that"
          % (kes(stale_v), kes(total), share))
    print("  no longer exist.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for a, d in stale:
        lam.update(str(a.get("id")), {
            "status": "closed",
            "status_before_close": a.get("status"),
            "closed_at": stamp,
            "closed_reason": "the deal (%s) was closed as %s"
                             % (d.get("id"), d.get("stage")),
        })
    print("\nClosed %d case(s). Restart uvicorn." % len(stale))
    return 0


if __name__ == "__main__":
    sys.exit(main())

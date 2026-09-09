#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Take back cases marked ready for credit risk by a BRANCH committee.

A branch committee's recommendation sends a case to the segment analyst. It
was marking the case committee_recommended, which put it on credit risk's
screen instead.

Only cases whose ONLY approving committee is a branch one are put back. A case
a department committee has also recommended stays where it is.

    python scripts/unmark_branch_recommendations.py
    python scripts/unmark_branch_recommendations.py --apply

Read only without --apply.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

APPROVING = ("APPROVED", "RECOMMENDED", "SUPPORTED")


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    from utils.api_lms_routes import _lam

    lam = _lam()
    apps = {str(a.get("id")): a for a in (getattr(lam, "apps", []) or [])}
    deals = PipelineManager().deals or []

    found, kept = [], []
    for d in deals:
        app_id = str(d.get("lms_application_id") or "").strip()
        a = apps.get(app_id)
        if not a:
            continue
        if str(a.get("status") or "").strip().lower() != "committee_recommended":
            continue
        recs = d.get("committee_records") or {}
        approving = [c for c, r in recs.items()
                     if isinstance(r, dict)
                     and str(r.get("outcome", "")).upper() in APPROVING]
        if not approving:
            continue
        dept = [c for c in approving
                if not str(c).upper().startswith("BCC_BRN")]
        if dept:
            kept.append((a, dept))
        else:
            found.append((d, a, approving))

    print("=" * 88)
    print("MARKED READY FOR CREDIT RISK BY A BRANCH COMMITTEE")
    print("=" * 88)
    print("  marked committee_recommended  %d" % (len(found) + len(kept)))
    print("  a department committee too    %d  (left alone)" % len(kept))
    print("  BRANCH ONLY                   %d  (put back)\n" % len(found))

    if kept:
        print("  LEFT ALONE - a department committee recommended these too")
        for a, dept in kept:
            print("     %-11s %-30s %s"
                  % (str(a.get("id"))[:11], str(a.get("client_name"))[:30],
                     ", ".join(dept)))
        print("")

    if not found:
        print("  Nothing to put back.")
        return 0

    print("  %-11s %-30s %-14s %s"
          % ("CASE", "CLIENT", "PUT BACK TO", "RECOMMENDED BY"))
    for d, a, approving in found:
        back = str(a.get("status_before_backfill") or "referred_to_committee")
        print("  %-11s %-30s %-14s %s"
              % (str(a.get("id"))[:11], str(a.get("client_name"))[:30],
                 back[:14], ", ".join(approving)))

    print("\n  These belong with the segment analyst, not credit risk. Each")
    print("  goes back to the status it had.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    n = 0
    for d, a, approving in found:
        back = str(a.get("status_before_backfill") or "referred_to_committee")
        try:
            lam.update(str(a.get("id")), {
                "status": back,
                "unmarked_at": stamp,
                "unmarked_reason": ("recommended by a branch committee (%s), "
                                    "which sends a case to the segment analyst"
                                    % ", ".join(approving)),
            })
            n += 1
        except Exception as exc:
            print("  could not update %s: %s" % (a.get("id"), str(exc)[:50]))
    print("\nPut back %d case(s). Restart uvicorn." % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())

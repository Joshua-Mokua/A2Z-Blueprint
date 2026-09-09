#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mark cases their committee has already recommended.

Until now a committee recommendation was written onto the deal and never onto the
case, so a case reads 'referred_to_committee' whether the committee has met or
not. CS2 fixes that from now on. These are the ones already decided.

A case is marked only where its deal carries a committee record with an
approving outcome. Nothing is inferred from the stage.

    python scripts/mark_already_approved_cases.py
    python scripts/mark_already_approved_cases.py --apply

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

    found, later_return, unclear = [], [], []
    for d in deals:
        app_id = str(d.get("lms_application_id") or "").strip()
        if not app_id or app_id not in apps:
            continue
        recs = d.get("committee_records") or {}
        approving = [(c, r) for c, r in recs.items()
                     if isinstance(r, dict)
                     and str(r.get("outcome", "")).upper() in APPROVING]
        if not approving:
            continue
        a = apps[app_id]
        status = str(a.get("status") or "").strip().lower()
        if status == "committee_recommended":
            continue
        # Do not drag a case backwards - one already with credit admin or
        # disbursed has moved past this.
        if status in ("credit_admin", "disbursed", "declined", "closed"):
            continue

        # A RETURN AFTER THE APPROVAL MEANS IT NEEDS REWORK, NOT FORWARDING.
        # Found in the pilot: LMS00001 was returned on 03-09 having been
        # approved on 02-09. Marking it recommended would hide that it is
        # waiting on a correction.
        _cttee, _rec = approving[-1]
        _approved_at = str(_rec.get("closed_at") or _rec.get("recorded_at")
                           or _rec.get("decided_at") or "").strip()
        _returned_at = str(a.get("returned_at") or "").strip()
        # THE CURRENT STATUS SETTLES IT. A case that is not 'returned' now has
        # had its rework resolved, whatever the timestamps say - D0676 was
        # returned on the 3rd and approved by B1 on the 7th, and an approval
        # record with no timestamp made the first version give up on it.
        #
        # Only a case STILL out for rework needs the order comparing.
        if status == "returned":
            if _returned_at and _approved_at and _returned_at > _approved_at:
                later_return.append((d, a, _returned_at, _approved_at))
                continue
            if not _approved_at:
                unclear.append((d, a, "still out for rework and the approval "
                                      "carries no timestamp - the order cannot "
                                      "be told"))
                continue
            if not _returned_at:
                unclear.append((d, a, "status is 'returned' and no returned_at "
                                      "is recorded - the order cannot be told"))
                continue
        found.append((d, a, _cttee, status))

    print("=" * 92)
    print("CASES THEIR COMMITTEE HAS ALREADY RECOMMENDED")
    print("=" * 92)
    print("  deals with a case  %d" % len(apps))
    print("  to mark            %d" % len(found))
    print("  returned since     %d  (left alone - they need rework)"
          % len(later_return))
    print("  order unclear      %d  (left alone - somebody should look)\n"
          % len(unclear))

    if later_return:
        print("  RETURNED AFTER THE COMMITTEE APPROVED - NOT MARKED")
        for d, a, r, ap in later_return:
            print("     %-11s %-26s returned %s, approved %s"
                  % (str(a.get("id"))[:11], str(d.get("client_name"))[:26],
                     r[:16], ap[:16]))
        print("")
    if unclear:
        print("  ORDER CANNOT BE TOLD - NOT MARKED")
        for d, a, why in unclear:
            print("     %-11s %-26s %s"
                  % (str(a.get("id"))[:11], str(d.get("client_name"))[:26], why))
        print("")
    if not found:
        print("  Nothing to mark.")
        return 0

    print("  %-11s %-9s %-26s %-22s %s"
          % ("CASE", "DEAL", "CLIENT", "STATUS NOW", "RECOMMENDED BY"))
    for d, a, cttee, status in found:
        print("  %-11s %-9s %-26s %-22s %s"
              % (str(a.get("id"))[:11], str(d.get("id"))[:9],
                 str(d.get("client_name"))[:26], status[:22], cttee))

    print("\n  These become 'committee_recommended', which is what credit risk")
    print("  should be pointed at.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    n = 0
    for d, a, cttee, status in found:
        try:
            lam.update(str(a.get("id")), {
                "status": "committee_recommended",
                "status_before_backfill": status,
                "committee_recommended_by": cttee,
                "committee_recommended_at": stamp,
            })
            n += 1
        except Exception as exc:
            print("  could not update %s: %s" % (a.get("id"), str(exc)[:50]))
    print("\nMarked %d case(s). Restart uvicorn." % n)
    print("Each keeps status_before_backfill.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

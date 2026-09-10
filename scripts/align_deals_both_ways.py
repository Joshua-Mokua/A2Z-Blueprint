#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bring every deal to where its case actually is - forward or back.

align_deal_stage_to_case only moves a deal FORWARD. That was deliberate: a
status should not drag a deal backwards by accident. But it leaves the deals
that were walked ahead by hand standing in front of their cases, and those are
what make the funnel disagree with the credit screens - 11 against 5.

This moves a deal EITHER WAY to match its case. Backward moves are listed
separately and each is recorded on the journey, because a deal going backwards
is something an owner will notice.

    python scripts/align_deals_both_ways.py
    python scripts/align_deals_both_ways.py --apply
    python scripts/align_deals_both_ways.py --forward-only --apply

Read only without --apply.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

STATUS_TO_STAGE = {
    "submitted":              "Department Credit Analysis",
    "assigned":               "Department Credit Analysis",
    "in_review":              "Department Credit Analysis",
    "info_requested":         "Department Credit Analysis",
    "returned":               "Documentation",
    "recommended":            "Department Credit Committee Review",
    "ready_for_committee":    "Department Credit Committee Review",
    "referred_to_committee":  "Department Credit Committee Review",
    "committee_recommended":  "Credit Analysis",
    "committee_approved":     "Credit Analysis",
    "credit_admin":           "Credit Administration",
    "disbursed":              "Trops",
}


def main():
    apply = "--apply" in sys.argv
    fwd_only = "--forward-only" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A
    from utils.api_lms_routes import _lam

    apps = {str(a.get("id")): a for a in (getattr(_lam(), "apps", []) or [])}
    pm = PipelineManager()
    deals = pm.deals or []

    fwd, back, stuck = [], [], []
    for d in deals:
        a = apps.get(str(d.get("lms_application_id") or "").strip())
        if not a:
            continue
        want = STATUS_TO_STAGE.get(str(a.get("status") or "").strip().lower())
        if not want:
            continue
        cur = str(d.get("stage") or "")
        if cur.lower().startswith("closed") or cur == want:
            continue
        try:
            flow = [str(x) for x in (A._stage_flow_for(
                d.get("product_type") or d.get("product", "")) or [])]
        except Exception:
            flow = []
        if want not in flow or cur not in flow:
            stuck.append((d, a, cur, want))
            continue
        (fwd if flow.index(want) > flow.index(cur) else back).append(
            (d, a, cur, want))

    print("=" * 96)
    print("DEALS THAT DO NOT MATCH THEIR CASE")
    print("=" * 96)
    print("  deals with a case   %d" % sum(
        1 for d in deals if str(d.get("lms_application_id") or "").strip()))
    print("  behind their case   %d  (move forward)" % len(fwd))
    print("  AHEAD of their case %d  (move back)" % len(back))
    print("  cannot place        %d\n" % len(stuck))

    def show(rows, title):
        if not rows:
            return
        print("  %s" % title)
        print("  %-9s %-24s %-30s %-30s %s"
              % ("DEAL", "CLIENT", "STAGE NOW", "SHOULD BE", "CASE IS"))
        for d, a, cur, want in rows:
            print("  %-9s %-24s %-30s %-30s %s"
                  % (str(d.get("id"))[:9], str(d.get("client_name"))[:24],
                     cur[:30], want[:30], a.get("status")))
        print("")

    show(fwd, "BEHIND - the case moved and the deal did not")
    show(back, "AHEAD - the deal was moved without the case")
    if stuck:
        print("  CANNOT PLACE - the stage is not in the product's flow:")
        for d, a, cur, want in stuck[:10]:
            print("     %-9s %-30s wants %-30s" % (str(d.get("id"))[:9], cur[:30], want[:30]))
        print("     normalise_deal_stages.py first.\n")

    plan = fwd + ([] if fwd_only else back)
    if not plan:
        print("  Nothing to move.")
        return 0
    if fwd_only and back:
        print("  --forward-only: leaving %d ahead-of-case deal(s) alone."
              % len(back))
    if not apply:
        print("\nDry run. Re-run with --apply.")
        if back and not fwd_only:
            print("\n  %d deal(s) will move BACKWARD. Their owners will see it."
                  % len(back))
            print("  Each keeps stage_before_align and says why on the journey.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for d, a, cur, want in plan:
        d["stage_before_align"] = cur
        d["stage"] = want
        d["aligned_at"] = stamp
        d["aligned_reason"] = ("brought into line with the credit case, which "
                               "is at %r" % a.get("status"))
        try:
            pm.add_activity({
                "deal_id": str(d.get("id")),
                "staff_code": d.get("staff_code", ""),
                "staff_name": d.get("staff_name", ""),
                "activity_type": "Stage Change",
                "note": ("Stage: %s -> %s. Brought into line with the credit "
                         "case, which is at %s." % (cur, want, a.get("status"))),
                "outcome": want,
            })
        except Exception:
            pass
    pm._save_deals()
    print("\nMoved %d deal(s): %d forward, %d back."
          % (len(plan), len(fwd), 0 if fwd_only else len(back)))

    ok = fail = 0
    for d, _a, _c, _w in plan:
        try:
            A._db_sync_pipeline_deal(d)
            ok += 1
        except Exception:
            fail += 1
    print("synced to the database: %d ok, %d failed" % (ok, fail))
    if fail:
        print("\n  THE FUNNEL READS THE DATABASE. Until those %d are pushed,"
              % fail)
        print("  the funnel will not show this. resync_deals_to_database.py")
        return 1
    print("\nRestart uvicorn and hard-refresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

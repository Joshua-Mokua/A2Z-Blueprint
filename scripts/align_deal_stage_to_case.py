#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bring a deal's stage up to where its credit case actually is.

The case status is what the credit workflow acts on. The deal's stage is what
the funnel displays. When a case is referred to a committee and nothing moves
the deal, the two disagree and the funnel understates real progress.

This corrects deals whose case is AHEAD of them. It never pushes a case
forward, and it never moves a deal ahead of its case.

    python scripts/align_deal_stage_to_case.py
    python scripts/align_deal_stage_to_case.py --apply

Read only without --apply.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

# What each case status says about where the deal should be standing.
WANTS = {
    "referred_to_committee": "committee",
    "with_committee": "committee",
    "approved": "after_committee",
    "with_credit_admin": "credit administration",
    "disbursed": "trops",
}


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A
    try:
        from utils.api_lms_routes import _lam
        apps = {str(a.get("id")): a for a in (getattr(_lam(), "apps", []) or [])}
    except Exception as exc:
        print("Could not read the applications: %s" % str(exc)[:60])
        return 1

    pm = PipelineManager()
    deals = pm.deals or []

    plan, unclear = [], []
    for d in deals:
        a = apps.get(str(d.get("lms_application_id") or ""))
        if not a:
            continue
        status = str(a.get("status") or "").strip().lower()
        want = WANTS.get(status)
        if not want:
            continue

        prod = d.get("product_type") or d.get("product") or ""
        try:
            flow = [str(x) for x in (A._stage_flow_for(prod) or [])]
        except Exception:
            flow = []
        cur = str(d.get("stage") or "")
        if not flow or cur not in flow:
            unclear.append((d, a, "the deal's stage %r is not in the %r flow"
                            % (cur, prod)))
            continue

        at = flow.index(cur)
        target = ""
        if want == "committee":
            for n in flow[at + 1:]:
                if "committee" in n.lower():
                    target = n
                    break
        elif want == "after_committee":
            seen = False
            for n in flow[at + 1:]:
                if "committee" in n.lower():
                    seen = True
                    continue
                if seen and not n.lower().startswith("closed"):
                    target = n
                    break
        else:
            for n in flow[at + 1:]:
                if want in n.lower():
                    target = n
                    break

        if not target:
            unclear.append((d, a, "no stage ahead of %r matches a case at %r"
                            % (cur, status)))
        elif target != cur:
            plan.append((d, a, cur, target))

    print("=" * 90)
    print("DEALS WHOSE CASE HAS MOVED ON WITHOUT THEM")
    print("=" * 90)
    print("  deals with a case  %d" % sum(
        1 for d in deals if str(d.get("lms_application_id") or "").strip()))
    print("  to correct         %d" % len(plan))
    print("  cannot place       %d\n" % len(unclear))

    if plan:
        print("  %-9s %-24s %-26s %-26s %s"
              % ("DEAL", "CLIENT", "STAGE NOW", "SHOULD BE", "CASE IS AT"))
        for d, a, cur, target in plan:
            print("  %-9s %-24s %-26s %-26s %s"
                  % (str(d.get("id"))[:9], str(d.get("client_name"))[:24],
                     cur[:26], target[:26], a.get("status")))

    if unclear:
        print("\n  Cannot place these - moving them would be a guess:")
        for d, a, why in unclear[:8]:
            print("     %-9s %s" % (str(d.get("id"))[:9], why))

    if not plan:
        print("\n  Nothing to correct.")
        return 0
    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\n  This only moves a deal FORWARD to where its case already is.")
        print("  It never advances a case, and never moves a deal past one.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for d, a, cur, target in plan:
        d["stage_before_alignment"] = cur
        d["stage"] = target
        d["aligned_at"] = stamp
        d["aligned_reason"] = ("the credit case was at %r while the deal still "
                               "showed %r" % (a.get("status"), cur))
        try:
            pm.add_activity({
                "deal_id": str(d.get("id")),
                "staff_code": d.get("staff_code", ""),
                "staff_name": d.get("staff_name", ""),
                "activity_type": "Stage Change",
                "note": ("Stage: %s -> %s. Brought into line with the credit "
                         "case, which was already at %s."
                         % (cur, target, a.get("status"))),
                "outcome": target,
            })
        except Exception as exc:
            print("  could not write the journey entry for %s: %s"
                  % (d.get("id"), str(exc)[:40]))
    pm._save_deals()
    print("\nCorrected %d deal(s)." % len(plan))

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d, _a, _c, _t in plan:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("Synced %d to the database." % n)
    except Exception as exc:
        print("\nCould not sync to the database: %s" % str(exc)[:50])
        print("The files changed and Postgres did not, so the funnel will")
        print("still show the old stages. Fix before relying on this.")
        return 1

    print("\nRestart uvicorn. Each deal keeps stage_before_alignment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

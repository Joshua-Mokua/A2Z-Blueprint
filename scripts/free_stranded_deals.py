#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Free deals a committee pushed past the point where they can be submitted.

A committee approval advances the deal one stage. On a deal that was never
submitted, that pushes it past Documentation - and submission requires
Documentation, so no application can be created and the deal is stuck.

Moves each back to the stage its product expects a submission from. The
committee's vote and outcome are untouched.

    python scripts/free_stranded_deals.py
    python scripts/free_stranded_deals.py --apply

Read only without --apply.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

CREDIT_SIDE = ("branch credit committee", "department credit", "credit analysis",
               "credit administration", "trops", "offer letter",
               "legal - security perfection")


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A

    pm = PipelineManager()
    deals = pm.deals or []

    def creditish(s):
        t = str(s or "").strip().lower()
        return bool(t) and any(w in t for w in CREDIT_SIDE)

    stuck = [d for d in deals
             if creditish(d.get("stage"))
             and not str(d.get("lms_application_id") or "").strip()
             and (d.get("committee_records") or d.get("committee_votes"))]

    print("=" * 88)
    print("DEALS A COMMITTEE PUSHED PAST SUBMISSION")
    print("=" * 88)
    print("  deals   %d" % len(deals))
    print("  stuck   %d\n" % len(stuck))
    if not stuck:
        print("  None. Every deal at a credit stage either has a case or was")
        print("  not moved there by a committee.")
        return 0

    plan, unclear = [], []
    for d in stuck:
        prod = d.get("product_type") or d.get("product") or ""
        target = ""
        try:
            _docs, doc_stage = A._product_document_config(d)
            target = str(doc_stage or "").strip()
        except Exception:
            target = ""
        if not target:
            try:
                flow = [str(x) for x in (A._stage_flow_for(prod) or [])]
                for cand in ("Documentation", "Initiation"):
                    if cand in flow:
                        target = cand
                        break
            except Exception:
                target = ""
        if target and not creditish(target):
            plan.append((d, target))
        else:
            unclear.append(d)

    print("  %-9s %-26s %-30s %s"
          % ("DEAL", "CLIENT", "STAGE NOW", "BACK TO"))
    for d, t in plan:
        print("  %-9s %-26s %-30s %s"
              % (str(d.get("id"))[:9], str(d.get("client_name"))[:26],
                 str(d.get("stage"))[:30], t))
    if unclear:
        print("\n  Cannot place these - moving them would be a guess:")
        for d in unclear[:8]:
            print("     %-9s %s" % (str(d.get("id"))[:9], d.get("product_type")))

    if not plan:
        print("\n  Nothing can be moved safely.")
        return 1
    print("\n  The owner then submits to credit as normal. The committee's")
    print("  vote stays on the deal - it does not have to sit again.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for d, t in plan:
        d["stage_before_free"] = d.get("stage", "")
        d["stage"] = t
        d["freed_at"] = stamp
        d["freed_reason"] = ("a committee advanced this past the point where "
                             "it could be submitted, and it had no credit case")
    pm._save_deals()
    print("\nFreed %d deal(s)." % len(plan))

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d, _t in plan:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("Synced %d to the database." % n)
    except Exception as exc:
        print("\nCould not sync to the database: %s" % str(exc)[:50])
        return 1
    print("\nRestart uvicorn, then tell each owner to submit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

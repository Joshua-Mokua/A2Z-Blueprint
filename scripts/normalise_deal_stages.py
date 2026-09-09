#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Put deals back onto stage names their product flow actually defines.

A deal sitting at a name no flow contains is stuck twice over:

  - no funnel bucket matches it, so it is counted in the family tab and shown
    in no row - which is why the tab says 123 and the rows add to 75
  - SOT1 refuses to move it, because it will not write a stage the flow does
    not define and will not compute from one either

So a case can be recommended by a department committee and its deal cannot
follow, and nobody can see where it is.

    python scripts/normalise_deal_stages.py
    python scripts/normalise_deal_stages.py --apply

Read only without --apply. Each deal keeps stage_before_normalise.
"""
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.getcwd())

# The legacy or misspelled name -> what the flows call it.
RENAME = {
    "consumer credit analysis":       "Department Credit Analysis",
    "credit assessment - bcc":        "Branch Credit Committee Review",
    "credit assessment":              "Department Credit Analysis",
    "credit analysis & assesment":    "Credit Analysis",
    "credit analyst & assesment":     "Credit Analysis",
    "credit analysis & assessment":   "Credit Analysis",
    "credit admin":                   "Credit Administration",
    "credit administarion":           "Credit Administration",
    "troops":                         "Trops",
    "closed - trops":                 "Closed Won",
    "closed lost - trops":            "Closed Lost",
}


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A

    pm = PipelineManager()
    deals = pm.deals or []

    plan, unknown = [], Counter()
    for d in deals:
        cur = str(d.get("stage") or "").strip()
        if not cur:
            continue
        prod = d.get("product_type") or d.get("product") or ""
        try:
            flow = [str(x) for x in (A._stage_flow_for(prod) or [])]
        except Exception:
            flow = []
        if not flow or cur in flow:
            continue
        want = RENAME.get(cur.lower())
        if want and want in flow:
            plan.append((d, cur, want))
        else:
            unknown[cur] += 1

    print("=" * 92)
    print("DEALS AT A STAGE THEIR FLOW DOES NOT DEFINE")
    print("=" * 92)
    print("  deals                 %d" % len(deals))
    print("  off their flow        %d" % (len(plan) + sum(unknown.values())))
    print("  can be put back       %d" % len(plan))
    print("  no obvious match      %d\n" % sum(unknown.values()))

    if plan:
        byname = Counter((c, w) for _d, c, w in plan)
        print("  %-38s %-38s %s" % ("STAGE NOW", "BECOMES", "DEALS"))
        for (c, w), n in byname.most_common():
            print("  %-38s %-38s %d" % (c[:38], w[:38], n))

    if unknown:
        print("\n  NO OBVIOUS MATCH - left alone, tell me what each should be:")
        for s, n in unknown.most_common():
            print("     %-46s %d deal(s)" % (s[:46], n))

    if not plan:
        print("\n  Nothing to put back.")
        return 0

    print("\n  Putting these back does two things: the funnel can show them,")
    print("  and their deals can follow their cases again.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for d, cur, want in plan:
        d["stage_before_normalise"] = cur
        d["stage"] = want
        d["normalised_at"] = stamp
        try:
            pm.add_activity({
                "deal_id": str(d.get("id")),
                "staff_code": d.get("staff_code", ""),
                "staff_name": d.get("staff_name", ""),
                "activity_type": "Stage Change",
                "note": ("Stage: %s -> %s. %r is not a stage this product's "
                         "flow defines." % (cur, want, cur)),
                "outcome": want,
            })
        except Exception:
            pass
    pm._save_deals()
    print("\nPut back %d deal(s)." % len(plan))

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d, _c, _w in plan:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("Synced %d to the database." % n)
    except Exception as exc:
        print("\nCould not sync to the database: %s" % str(exc)[:50])
        print("The files changed and Postgres did not - the funnel reads the")
        print("database, so nothing will look different until this works.")
        return 1

    print("\nRestart uvicorn. Then run:")
    print("   python scripts/align_deal_stage_to_case.py --apply")
    print("so the ones with a case catch up to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Move deals sitting at Lead to Initiation.

Lead is left over from an earlier journey. The flows begin at Initiation, so a
deal at Lead sits outside every funnel bucket and outside the stage rules -
it cannot be advanced, validated or reported on properly.

    python scripts/move_lead_deals.py
    python scripts/move_lead_deals.py --apply

Read only without --apply. Each deal keeps stage_before_move.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

OLD_STAGES = ("lead", "contacted", "qualified")


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    pm = PipelineManager()
    deals = pm.deals or []

    hits = [d for d in deals
            if str(d.get("stage", "") or "").strip().lower() in OLD_STAGES]

    print("=" * 84)
    print("DEALS AT A STAGE THE FLOWS NO LONGER USE")
    print("=" * 84)
    print("  deals       %d" % len(deals))
    print("  to move     %d\n" % len(hits))
    if not hits:
        print("  None. Every deal is on a stage its flow defines.")
        return 0

    print("  %-8s %-28s %-14s %-16s %s"
          % ("DEAL", "CLIENT", "STAGE NOW", "OWNER", "PRODUCT"))
    for d in hits:
        print("  %-8s %-28s %-14s %-16s %s"
              % (str(d.get("id"))[:8], str(d.get("client_name"))[:28],
                 str(d.get("stage"))[:14], str(d.get("staff_code"))[:16],
                 str(d.get("product_type") or d.get("product") or "")[:20]))

    print("\n  All move to Initiation, which is where every flow begins.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for d in hits:
        was = d.get("stage", "")
        d["stage_before_move"] = was
        d["stage"] = "Initiation"
        d["stage_moved_at"] = stamp
        try:
            pm.add_activity({
                "deal_id": str(d.get("id")),
                "staff_code": d.get("staff_code", ""),
                "staff_name": d.get("staff_name", ""),
                "activity_type": "Stage Change",
                "note": ("Stage: %s -> Initiation. %r is not a stage any flow "
                         "defines." % (was, was)),
                "outcome": "Initiation",
            })
        except Exception as exc:
            print("  could not write the journey entry for %s: %s"
                  % (d.get("id"), str(exc)[:40]))
    pm._save_deals()
    print("\nMoved %d." % len(hits))

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d in hits:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("Synced %d to the database." % n)
    except Exception as exc:
        print("\nCould not sync to the database: %s" % str(exc)[:50])
        print("The files changed and Postgres did not, so the funnel will")
        print("still show them at the old stage.")
        return 1

    print("\nRestart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

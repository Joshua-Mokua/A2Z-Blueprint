#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Send deals that reached credit without a case back to be submitted. DRY RUN.

FROM THE PILOT (2026-09-07): "I have these cases at Credit Analysis but
Catherine is unable to see them."

The analyst's queue lists CREDIT CASES, not deals. A case is created by Submit
to Credit, which runs the document checklist, opens the application, records
who submitted it, and advances the stage. A deal that reached a credit stage
any other way - an RM advancing it by hand - has no application behind it, so
there is nothing for her screen to list.

    python scripts\return_orphan_credit_deals.py
    python scripts\return_orphan_credit_deals.py --apply

WHAT THIS DOES: moves each such deal back to the stage its product expects a
submission from - usually Documentation - so its owner can press Submit to
Credit and it enters properly.

WHAT IT DELIBERATELY DOES NOT DO: create the applications. That would write a
submission that never happened - no document check, no submitter, an SLA clock
starting from a fiction - and in a bank that record is read later by people who
assume it means what it says.

IT ONLY TOUCHES DEALS WITH NO CREDIT CASE. A deal with an application is in
credit properly and is left alone, whatever its stage.

EACH ONE KEEPS ITS HISTORY: the stage it was standing on is recorded as
stage_before_return, so nothing is lost and the move is reversible.

THE OWNER MUST THEN SUBMIT IT. This puts the deals where they can be submitted;
it does not submit them. Tell the owners, or they will find their deals have
moved backwards with no explanation.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

CREDIT_SIDE = (
    "branch credit committee", "department credit", "credit analysis",
    "credit administration", "credit administarion", "trops",
    "management credit committee", "board credit committee",
    "legal - security perfection", "offer letter", "disbursement",
)


def main():
    apply = "--apply" in sys.argv

    from utils.core import PipelineManager
    import utils.api as A

    pm = PipelineManager()
    deals = pm.deals or []

    def creditish(s):
        t = str(s or "").strip().lower()
        return bool(t) and any(w in t for w in CREDIT_SIDE)

    orphans = [d for d in deals
               if creditish(d.get("stage"))
               and not str(d.get("lms_application_id") or "").strip()]

    print("=" * 88)
    print("DEALS IN CREDIT WITH NO CREDIT CASE")
    print("=" * 88)
    print("  deals               %d" % len(deals))
    print("  to send back        %d\n" % len(orphans))
    if not orphans:
        print("  None. Every deal at a credit stage has an application behind")
        print("  it. If an analyst still cannot see one, the fault is her")
        print("  scope rather than the deal.")
        return 0

    plan, stuck = [], []
    for d in orphans:
        prod = str(d.get("product_type") or d.get("product") or "")
        target = ""
        try:
            # Where does this product expect a submission FROM?
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
                if not target and flow:
                    target = flow[0]
            except Exception:
                target = ""
        if target and not creditish(target):
            plan.append((d, target))
        else:
            stuck.append((d, target))

    if plan:
        print("  %-9s %-24s %-30s %s"
              % ("DEAL", "CLIENT", "FROM", "BACK TO"))
        for d, t in plan[:25]:
            print("  %-9s %-24s %-30s %s"
                  % (str(d.get("id"))[:9], str(d.get("client_name"))[:24],
                     str(d.get("stage"))[:30], t))
        if len(plan) > 25:
            print("     ... and %d more" % (len(plan) - 25))
    if stuck:
        print("\n  CANNOT PLACE THESE - their product has no stage to submit")
        print("  from, so moving them would be a guess:")
        for d, _t in stuck[:8]:
            print("     %-9s %-24s product=%s"
                  % (str(d.get("id"))[:9], str(d.get("client_name"))[:24],
                     d.get("product_type") or d.get("product")))

    if not plan:
        print("\n  Nothing can be moved safely.")
        return 1
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("\n  AFTERWARDS the OWNER must press Submit to Credit on each.")
        print("  This puts them where they can be submitted; it does not")
        print("  submit them. Tell the owners, or they will find their deals")
        print("  have moved backwards with no explanation.")
        return 0

    stamp = datetime.now().isoformat(timespec="seconds")
    for d, t in plan:
        d["stage_before_return"] = d.get("stage", "")
        d["stage"] = t
        d["returned_reason"] = ("reached a credit stage without a credit case "
                                "behind it, so no analyst could see it")
        d["returned_at"] = stamp
    pm._save_deals()
    print("\nsent %d deal(s) back." % len(plan))

    try:
        from utils.api import _db_sync_pipeline_deal as _sync
        n = 0
        for d, _t in plan:
            try:
                _sync(d)
                n += 1
            except Exception:
                pass
        print("synced %d to the database." % n)
    except Exception as exc:
        print("\n*** COULD NOT SYNC TO THE DATABASE: %s" % str(exc)[:44])
        print("    The files are changed and Postgres is not, so a DB-first")
        print("    read will still show them in credit AND NOTHING WILL HAVE")
        print("    CHANGED for the team. Fix this before telling anybody.")
        return 1

    print("\nRESTART UVICORN, then tell each owner to submit their deal.")
    print("The stage each was standing on is kept as stage_before_return.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

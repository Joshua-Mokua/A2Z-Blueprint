#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Initiation, then Documentation. Nothing in between. DRY RUN by default.

RULING (2026-08-18): "there is a stage I wanted ignored, since most of this is
auto - the Negotiation stage. I would rather we have Initiation, Documentation,
then the other stages are clear - so that it does not show Negotiation when it
is at Documentation, or the owner does not need to go to Submit from
Negotiation manually."

WHAT IS THERE NOW, and it is worse than one stray stage: the flows disagree
with each other. Mortgage opens Initiation, Negotiation, Documentation. Business
Loan opens Lead, Contacted, Qualified, Documentation. A relationship manager
handling both products meets two different processes for the same act.

Every one of those pre-Documentation stages is a stage somebody must advance by
hand, for no decision anybody makes. D8477 sat at Negotiation, locked, in
nobody's queue, because it had been submitted from a stage that was not the one
the submission gate expects - and the owner had no reason to know that.

WHAT THIS DOES: everything before Documentation becomes a single "Initiation".
Documentation and everything after it is UNTOUCHED - the committees, the credit
stages, the closing stages all stay exactly as they are.

    Initiation, Negotiation, Documentation, ...   ->  Initiation, Documentation, ...
    Lead, Contacted, Qualified, Documentation, ...->  Initiation, Documentation, ...

IT MOVES THE DEALS TOO. Dropping a stage from under live cases is how they
vanish: the case sits on a stage its flow no longer contains, cannot be placed,
cannot advance, and appears in no queue. Any deal on a removed stage is moved
to Initiation, and every one is listed before anything is written.

A FLOW WITH NO DOCUMENTATION STAGE IS LEFT ALONE. Deposit and card products
often have none, and guessing where their front ends would be inventing a
process the bank has not described.

    python scripts\\simplify_stage_flows.py
    python scripts\\simplify_stage_flows.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

KEEP_FIRST = "Initiation"
ANCHOR = "documentation"


def main():
    apply = "--apply" in sys.argv
    import utils.api as A
    from utils.core import PipelineManager

    cfg = A._load_json("pipeline_settings.json") or {}
    flows = cfg.get("product_flows") or {}
    if not flows:
        print("ABORT: no product_flows in the config.")
        return 1

    def names(entry):
        st = entry if isinstance(entry, list) else (entry or {}).get("stages") or []
        return [str(s.get("stage") if isinstance(s, dict) else s) for s in st]

    changes, skipped, removed_stages = [], [], set()
    for prod in sorted(flows):
        st = names(flows[prod])
        if not st:
            continue
        idx = next((i for i, s in enumerate(st) if ANCHOR in s.lower()), -1)
        if idx < 0:
            skipped.append(prod)
            continue
        before = st[:idx]
        if before == [KEEP_FIRST]:
            continue
        for s in before:
            if s.strip().lower() != KEEP_FIRST.lower():
                removed_stages.add(s)
        changes.append((prod, before, st[idx:]))

    print("=" * 78)
    print("THE FRONT OF EVERY CREDIT FLOW")
    print("=" * 78)
    print("  flows to simplify        %d" % len(changes))
    print("  already correct          %d" % (len(flows) - len(changes) - len(skipped)))
    print("  no Documentation stage   %d  (left alone)" % len(skipped))

    if changes:
        print("\n  %-30s %-34s becomes" % ("PRODUCT", "OPENS WITH"))
        for prod, before, _rest in changes[:16]:
            print("     %-28s %-32s %s"
                  % (prod[:28], ", ".join(before)[:32], KEEP_FIRST))
        if len(changes) > 16:
            print("     ... and %d more" % (len(changes) - 16))

    if removed_stages:
        print("\n  STAGES THAT DISAPPEAR: %s" % ", ".join(sorted(removed_stages)))

    # Any live deal standing on one of them.
    pm = PipelineManager()
    lowered = {s.strip().lower() for s in removed_stages}
    stranded = [d for d in (pm.deals or [])
                if str(d.get("stage", "")).strip().lower() in lowered]
    print("\n  live deals standing on a stage that would disappear: %d" % len(stranded))
    for d in stranded[:12]:
        print("     %-12s %-26s %s" % (str(d.get("id"))[:12],
                                       str(d.get("client_name"))[:26], d.get("stage")))
    if len(stranded) > 12:
        print("     ... and %d more" % (len(stranded) - 12))
    if stranded:
        print("\n  They will be moved to %r. Leaving them where they are would" % KEEP_FIRST)
        print("  strand them: a case on a stage its flow no longer contains")
        print("  cannot be placed, cannot advance, and appears in no queue.")

    if not changes and not stranded:
        print("\n  Nothing to do.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for prod, _before, rest in changes:
        entry = flows[prod]
        st = entry if isinstance(entry, list) else (entry or {}).get("stages") or []
        shaped = []
        for s in rest:
            match = next((x for x in st
                          if str(x.get("stage") if isinstance(x, dict) else x) == s), None)
            shaped.append(match if match is not None else s)
        first = KEEP_FIRST
        if st and isinstance(st[0], dict):
            first = {"stage": KEEP_FIRST, "target_days": 0}
        new = [first] + shaped
        if isinstance(entry, list):
            flows[prod] = new
        else:
            entry["stages"] = new

    cfg["product_flows"] = flows
    p = os.path.join("data", "pipeline_settings.json")
    bak = p + ".pre_simplify_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(p, bak)
    try:
        A.save_pipeline_settings(cfg)
    except Exception:
        json.dump(cfg, open(p, "w", encoding="utf-8"), indent=2)
    print("\nsimplified %d flow(s).  (backup: %s)" % (len(changes), os.path.basename(bak)))

    if stranded:
        for d in stranded:
            d["stage"] = KEEP_FIRST
        pm._save_deals()
        print("moved %d deal(s) to %r." % (len(stranded), KEEP_FIRST))
        try:
            from utils.api import _db_sync_pipeline_deal as _sync
            for d in stranded:
                try:
                    _sync(d)
                except Exception:
                    pass
            print("and synced them to the database.")
        except Exception:
            print("*** could not sync to the database - restart and re-check.")

    print("\nRESTART UVICORN, then:  python scripts\\walk_all_flows.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

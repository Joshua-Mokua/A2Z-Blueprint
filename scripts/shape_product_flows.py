#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Every product: Initiation, Documentation, its own journey, closure. DRY RUN.

RULING (2026-08-19): "each product needed to have its own unique flow. The
basic structure we have agreed upon is Initiation, Documentation, then the
approval journeys to closure of each."

So three parts, and only the middle differs:

    Initiation          common
    Documentation       common - the papers
    <this product>      ITS OWN. A credit product goes to committees; an
                        account gets opened; a deposit gets booked.
    Closed Won / Lost   common

WHAT IS THERE NOW. The 13 credit products already have distinct middles -
branch committee, department analysis, department committee, credit analysis -
and are LEFT ALONE. The other 23 are mostly generic sales stages: Lead,
Contacted, Qualified, Proposal, Negotiation. Ten of them have no Documentation
stage at all, so a current account is opened without the papers being a step.

THIS SCRIPT WILL NOT INVENT A JOURNEY. Where a product already names its own
middle stage - Current Account has "Account Openned", Fixed Deposit has "Fixed
Deposit Openned" - that stage is KEPT and everything generic around it is
dropped. Where a product names nothing of its own, it is REPORTED, not guessed
at: the bank has not said what happens between the papers and the close, and
writing "Approval" there would be me deciding a process I have not been told.

Generic stages dropped: Lead, Contacted, Qualified, Proposal, Negotiation,
Offer / Proposal. Every one is a stage somebody advances by hand for no
decision anybody makes.

    python scripts\\shape_product_flows.py
    python scripts\\shape_product_flows.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

FIRST = "Initiation"
DOCS = "Documentation"
WON, LOST = "Closed Won", "Closed Lost"

GENERIC = {"lead", "contacted", "qualified", "proposal", "negotiation",
           "offer / proposal", "offer/proposal", "prospecting",
           "needs analysis", "lead/cutomer instructions",
           "lead/customer instructions"}


def main():
    apply = "--apply" in sys.argv
    import utils.api as A
    from utils.core import PipelineManager

    cfg = A._load_json("pipeline_settings.json") or {}
    flows = cfg.get("product_flows") or {}
    if not flows:
        print("ABORT: no product_flows.")
        return 1

    def names(entry):
        st = entry if isinstance(entry, list) else (entry or {}).get("stages") or []
        return [str(s.get("stage") if isinstance(s, dict) else s) for s in st]

    credit, shaped, bare, already = [], [], [], []
    for prod in sorted(flows):
        st = names(flows[prod])
        if not st:
            continue
        if any("committee" in s.lower() for s in st):
            credit.append(prod)
            continue
        # Its OWN stages: not generic, not the common four.
        own = [s for s in st
               if s.strip().lower() not in GENERIC
               and s.strip().lower() not in (FIRST.lower(), DOCS.lower(),
                                             WON.lower(), LOST.lower())]
        want = [FIRST, DOCS] + own + [WON, LOST]
        if st == want:
            already.append(prod)
        elif own:
            shaped.append((prod, st, want))
        else:
            bare.append((prod, st))

    print("=" * 78)
    print("EVERY PRODUCT: INITIATION, DOCUMENTATION, ITS OWN JOURNEY, CLOSURE")
    print("=" * 78)
    print("  credit products, left alone      %d" % len(credit))
    print("  already in this shape            %d" % len(already))
    print("  to be shaped                     %d" % len(shaped))
    print("  NAME NOTHING OF THEIR OWN        %d" % len(bare))

    if shaped:
        print("\n  THESE KEEP THEIR OWN STAGE AND LOSE THE GENERIC ONES:\n")
        for prod, was, want in shaped:
            print("     %s" % prod)
            print("        was  %s" % " -> ".join(was))
            print("        now  %s" % " -> ".join(want))

    if bare:
        print("\n  *** THESE HAVE NO JOURNEY OF THEIR OWN, only generic sales")
        print("      stages. I will NOT guess at what happens between the")
        print("      papers and the close - that is the bank's process to")
        print("      state, not mine to invent:\n")
        for prod, was in bare[:14]:
            print("     %-30s %s" % (prod[:30], " -> ".join(was)[:44]))
        if len(bare) > 14:
            print("     ... and %d more" % (len(bare) - 14))
        print("\n      Tell me the middle stage for each family - an account is")
        print("      'opened', a policy is 'issued', a card is 'dispatched' -")
        print("      and I will shape them properly.")

    # Nothing may be stranded.
    lowered = set()
    for prod, was, want in shaped:
        lowered |= {s.strip().lower() for s in was if s not in want}
    pm = PipelineManager()
    stranded = [d for d in (pm.deals or [])
                if str(d.get("stage", "")).strip().lower() in lowered]
    print("\n  live deals standing on a stage that would disappear: %d" % len(stranded))
    for d in stranded[:10]:
        print("     %-12s %-24s %s" % (str(d.get("id"))[:12],
                                       str(d.get("client_name"))[:24], d.get("stage")))

    if not shaped:
        print("\n  Nothing to shape.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for prod, _was, want in shaped:
        entry = flows[prod]
        st = entry if isinstance(entry, list) else (entry or {}).get("stages") or []
        dictish = bool(st) and isinstance(st[0], dict)
        new = []
        for s in want:
            match = next((x for x in st
                          if str(x.get("stage") if isinstance(x, dict) else x) == s), None)
            if match is not None:
                new.append(match)
            else:
                new.append({"stage": s, "target_days": 0} if dictish else s)
        if isinstance(entry, list):
            flows[prod] = new
        else:
            entry["stages"] = new

    cfg["product_flows"] = flows
    p = os.path.join("data", "pipeline_settings.json")
    bak = p + ".pre_shape_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(p, bak)
    try:
        A.save_pipeline_settings(cfg)
    except Exception:
        json.dump(cfg, open(p, "w", encoding="utf-8"), indent=2)
    print("\nshaped %d flow(s).  (backup: %s)" % (len(shaped), os.path.basename(bak)))

    if stranded:
        for d in stranded:
            d["stage"] = FIRST
        pm._save_deals()
        print("moved %d deal(s) to %r rather than strand them." % (len(stranded), FIRST))

    print("\nRESTART UVICORN, then:  python scripts\\walk_all_flows.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

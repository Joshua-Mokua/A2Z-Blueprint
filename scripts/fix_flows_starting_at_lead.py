#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Eleven product flows still begin at "Lead".

LD1 stopped new deals landing at Lead, and move_lead_deals.py moved 29 existing
ones to Initiation. The product FLOWS were never changed, so they still start
at a stage nothing uses.

A deal at Initiation on one of these products is on a stage its flow does not
contain. No funnel bucket shows it - the tab counts it and the rows do not -
and SOT1 will not move it, because it refuses to write or read a stage the
flow does not define.

That is the 49.

    python scripts/fix_flows_starting_at_lead.py
    python scripts/fix_flows_starting_at_lead.py --apply

Renames the first stage from Lead to Initiation, keeping its SLA and
everything after it. Read only without --apply.
"""
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime

CFG = os.path.join("data", "pipeline_settings.json")
OLD_FIRST = ("lead", "lead/cutomer instructions", "lead/customer instructions")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pf = cfg.get("product_flows") or {}

    used = Counter()
    try:
        sys.path.insert(0, os.getcwd())
        from utils.core import PipelineManager
        for d in (PipelineManager().deals or []):
            p = str(d.get("product_type") or d.get("product") or "").strip()
            s = str(d.get("stage") or "").strip()
            if p and s:
                used[(p, s)] += 1
    except Exception as exc:
        print("(could not read the deals: %s)" % str(exc)[:50])

    plan = []
    for name, entry in pf.items():
        stages = entry.get("stages") or []
        if not stages:
            continue
        first = str(stages[0].get("stage", "") or "").strip()
        if first.lower() not in OLD_FIRST:
            continue
        names = {str(s.get("stage", "")).strip() for s in stages}
        if "Initiation" in names:
            print("  %s already has an Initiation stage - skipping, it needs"
                  % name)
            print("     a person to decide which of the two is right.")
            continue
        stuck = sum(n for (p, s), n in used.items()
                    if p == name and s not in names)
        plan.append((name, first, stages, stuck))

    print("=" * 88)
    print("PRODUCT FLOWS THAT STILL BEGIN AT LEAD")
    print("=" * 88)
    print("  products with a flow   %d" % len(pf))
    print("  starting at Lead       %d\n" % len(plan))
    if not plan:
        print("  None. Every flow starts at a stage in use.")
        return 0

    print("  %-32s %-30s %s" % ("PRODUCT", "FIRST STAGE NOW", "DEALS STUCK"))
    total = 0
    for name, first, _st, stuck in sorted(plan, key=lambda x: -x[3]):
        total += stuck
        print("  %-32s %-30s %d" % (name[:32], first[:30], stuck))
    print("\n  deals stuck on a stage their flow does not contain: %d" % total)
    print("\n  Each flow's first stage becomes Initiation. Its SLA and every")
    print("  stage after it are untouched.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_leadflow_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    for name, _first, stages, _stuck in plan:
        stages[0]["stage"] = "Initiation"
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn and hard-refresh.")
    print("\nThose deals should then appear in the funnel's first row, and")
    print("their deals can move again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

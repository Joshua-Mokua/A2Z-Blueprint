#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Add a Rework stage to the product flows.

A returned case needs somewhere to sit that is not a stage it has passed and
not one it has not reached. Without it, a return either leaves the deal where
it was - and submission is blocked - or drops it to Documentation, and a case
returned from the department committee has to climb every gate again.

Rework sits after Documentation. It is where a case waits while somebody
fixes something, and it is visible as itself in the funnel rather than hiding
inside another stage.

    python scripts/add_rework_stage.py
    python scripts/add_rework_stage.py --apply

Read only without --apply.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "pipeline_settings.json")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pf = cfg.get("product_flows") or {}
    sf = cfg.get("stage_flows") or {}

    plan_p, plan_c = [], []
    for name, entry in pf.items():
        stages = entry.get("stages") or []
        names = [str(s.get("stage", "")).strip() for s in stages]
        if "Rework" in names:
            continue
        if "Documentation" not in names:
            continue
        plan_p.append((name, entry, names.index("Documentation") + 1))
    for cls, stages in sf.items():
        names = [str(x) for x in (stages or [])]
        if "Rework" in names or "Documentation" not in names:
            continue
        plan_c.append((cls, stages, names.index("Documentation") + 1))

    print("=" * 76)
    print("ADD A REWORK STAGE")
    print("=" * 76)
    print("  product flows      %d, %d need it" % (len(pf), len(plan_p)))
    print("  class flows        %d, %d need it\n" % (len(sf), len(plan_c)))

    if not plan_p and not plan_c:
        print("  Every flow already has one, or has no Documentation stage to")
        print("  put it after.")
        return 0

    for name, _e, at in plan_p[:12]:
        print("     %-34s after Documentation (position %d)" % (name[:34], at))
    if len(plan_p) > 12:
        print("     ... and %d more" % (len(plan_p) - 12))
    for cls, _s, at in plan_c:
        print("     class %-28s after Documentation (position %d)" % (cls, at))

    print("\n  A returned case sits here until the work is done, then goes back")
    print("  to the stage it froze at - not to the beginning.")
    print("\n  It is NOT a credit-side stage, so the guard that stops a deal")
    print("  being walked into credit does not block a return.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_rework_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    for _name, entry, at in plan_p:
        entry["stages"].insert(at, {"stage": "Rework", "sla_days": 3,
                                    "probability": 15})
    for _cls, stages, at in plan_c:
        stages.insert(at, "Rework")
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn.")
    print("\nThe funnel will show a Rework column once a case is in one. If it")
    print("does not, its bucket needs the stage - fix_remaining_funnel_buckets.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

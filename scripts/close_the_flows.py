#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Give every product flow a way to end. DRY RUN by default.

FROM THE PILOT (2026-08-18): audit_200 found thirteen products whose flow has
no closing stage - Mortgage, Term Loan, Personal Loan, Credit Card, Working
Capital, Trade Finance and others. A case reaching the end of one of those has
nowhere to go: it cannot be won, it cannot be lost, and it sits at the last
stage for ever while somebody wonders why it will not close.

WHY walk_all_flows PASSED AND audit_200 DID NOT, which is worth knowing before
you trust either: walk_all_flows checks that every stage has a NEXT stage, and
skips the last one. It never asks whether the last one lets you close. Two
tests, two different questions, and only one of them was the right one to ask.

WHAT IT ADDS. "Closed Won" and "Closed Lost", at the end, only to flows that
have neither. Nothing is reordered and no existing stage is touched.

IT WILL NOT GUESS AT A HALF-CLOSED FLOW. A flow with "Closed Won" but no
"Closed Lost" is reported and left alone: somebody may have meant that, and a
script that completes half-finished intentions is how a config drifts away from
the person who wrote it.

    python scripts\\close_the_flows.py
    python scripts\\close_the_flows.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

WON, LOST = "Closed Won", "Closed Lost"


def main():
    apply = "--apply" in sys.argv
    try:
        import utils.api as A
        cfg = A._load_json("pipeline_settings.json") or {}
    except Exception as exc:
        print("ABORT: cannot read pipeline_settings.json: %s" % exc)
        return 1
    flows = cfg.get("product_flows") or {}
    if not flows:
        print("ABORT: no product_flows in the config.")
        return 1

    def names(entry):
        st = entry if isinstance(entry, list) else (entry or {}).get("stages") or []
        return [str(s.get("stage") if isinstance(s, dict) else s) for s in st]

    fix, half, fine = [], [], []
    for prod in sorted(flows):
        st = names(flows[prod])
        if not st:
            continue
        low = [s.lower() for s in st]
        has_won = any(s == WON.lower() for s in low)
        has_lost = any(s == LOST.lower() for s in low)
        if has_won and has_lost:
            fine.append(prod)
        elif has_won or has_lost:
            half.append((prod, WON if has_won else LOST))
        else:
            fix.append((prod, st[-1]))

    print("=" * 76)
    print("CAN EVERY PRODUCT'S CASE BE CLOSED")
    print("=" * 76)
    print("  already closable      %d" % len(fine))
    print("  half-closed           %d" % len(half))
    print("  NO WAY TO CLOSE       %d" % len(fix))

    if half:
        print("\n  These have one closing stage and not the other. LEFT ALONE -")
        print("  somebody may have meant that, and a script that finishes")
        print("  half-made decisions is how a config drifts:\n")
        for prod, which in half:
            print("     %-32s has %s only" % (prod[:32], which))

    if not fix:
        print("\n  Every product can be closed. Nothing to do.")
        return 0

    print("\n  These would take a case in and never let it out. %s and %s"
          % (WON, LOST))
    print("  will be added at the end of each:\n")
    for prod, last in fix:
        print("     %-32s currently ends at %s" % (prod[:32], last[:26]))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for prod, _last in fix:
        entry = flows[prod]
        if isinstance(entry, list):
            entry.extend([WON, LOST])
        else:
            st = entry.setdefault("stages", [])
            # Match the shape already in use, so nothing downstream has to
            # cope with two kinds of entry in one list.
            if st and isinstance(st[0], dict):
                st.extend([{"stage": WON, "target_days": 0},
                           {"stage": LOST, "target_days": 0}])
            else:
                st.extend([WON, LOST])

    cfg["product_flows"] = flows
    p = os.path.join("data", "pipeline_settings.json")
    if not os.path.isfile(p):
        print("ABORT: %s not found - not writing." % p)
        return 1
    bak = p + ".pre_close_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(p, bak)
    try:
        import utils.api as A
        A.save_pipeline_settings(cfg)
    except Exception:
        json.dump(cfg, open(p, "w", encoding="utf-8"), indent=2)
    print("\nclosed %d flow(s).  (backup: %s)" % (len(fix), os.path.basename(bak)))
    print("RESTART UVICORN - the flow config is read at start.")
    print("\nCheck with:  python scripts\\close_the_flows.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

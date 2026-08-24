#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
What is waiting for each committee, and does the queue agree? READ ONLY.

FROM THE PILOT (2026-08-24): Jane opens Manager Queues and sees "Committee 2".
Upendo opens the same screen and sees "Committee 0".

Either there are no Commercial cases waiting - which is a fact about the
pipeline, not a fault - or the queue is not finding them. Those look identical
on screen and only one of them needs fixing.

This counts what is ACTUALLY waiting for each committee from the deal store,
then asks the queue endpoint what it would show, and prints both.

    python scripts\diag_committee_queue.py

A DIFFERENCE IS THE BUG. Agreement means the shelf is genuinely empty and
nobody needs to chase it.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    cfg_path = os.path.join("data", "lms_config.json")
    if not os.path.isfile(cfg_path):
        print("ABORT: %s not found." % cfg_path)
        return 1
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
    seated = [c for c in pal
              if any(str(m.get("staff_code", "")).strip()
                     for m in (c.get("members") or []) if isinstance(m, dict))]
    if not seated:
        print("No committee has anybody seated.")
        return 1

    try:
        from utils.core import PipelineManager, UserManager
        deals = PipelineManager().deals or []
        users = UserManager().users or {}
    except Exception as exc:
        print("ABORT: cannot read the stores: %s" % str(exc)[:60])
        return 1

    print("=" * 84)
    print("WHAT IS WAITING FOR EACH COMMITTEE")
    print("=" * 84)
    print("  deals in the pipeline  %d\n" % len(deals))

    by_code = {}
    for login, rec in users.items():
        c = str(rec.get("staff_code", "")).strip().lower()
        if c:
            by_code[c] = dict(rec, username=login)

    disagree, unknown = [], []
    for c in seated:
        code = str(c.get("code"))
        name = str(c.get("name"))
        # A deal is before this committee when its journey names it and it has
        # not yet been resolved. Read the deal rather than trusting a flag.
        waiting = []
        for d in deals:
            j = d.get("committee_journey") or d.get("committees") or []
            if isinstance(j, dict):
                j = [j]
            for step in j:
                if not isinstance(step, dict):
                    continue
                if str(step.get("code") or step.get("committee") or "") != code:
                    continue
                if str(step.get("outcome") or step.get("status") or "").lower() \
                        in ("", "pending", "awaiting", "open", "referred"):
                    waiting.append(d)
                break
        print("  %s  %s" % (code, name))
        print("     in the deal store        %d waiting" % len(waiting))
        for d in waiting[:4]:
            print("        %-10s %-28s %s" % (str(d.get("id"))[:10],
                                              str(d.get("client_name"))[:28],
                                              d.get("stage")))

        # What the queue endpoint would hand the first seated member.
        first = next((m for m in (c.get("members") or [])
                      if isinstance(m, dict)
                      and str(m.get("staff_code", "")).strip()), None)
        u = by_code.get(str(first.get("staff_code", "")).strip().lower()) \
            if first else None
        shown = "?"
        if u:
            try:
                from utils.api import pipeline_queue_committee as _q
                r = _q(user=u)
                rows = (r.get("items") or r.get("deals")
                        or r.get("committee") or r.get("rows") or [])
                shown = str(len(rows))
            except Exception as exc:
                shown = "err %s" % str(exc)[:26]
        print("     the queue would show     %s   (as %s)"
              % (shown, (first or {}).get("name", "?")))
        # A CHECK THAT COULD NOT CHECK MUST NOT REPORT AGREEMENT.
        # The first version compared "0 waiting" against "err cannot import"
        # and printed THE QUEUE AGREES WITH THE DEAL STORE - while Jane could
        # plainly see two cases on her screen. An all-clear from a check that
        # never ran is worse than no check.
        if not shown.isdigit():
            unknown.append((code, shown))
            print("     *** COULD NOT ASK THE QUEUE - this proves nothing")
        elif int(shown) != len(waiting):
            disagree.append((code, len(waiting), int(shown)))
            print("     *** THESE DISAGREE")
        print("")

    print("=" * 84)
    if unknown:
        print("THIS CHECK DID NOT RUN")
        print("=" * 84)
        for code, why in unknown:
            print("  * %s: %s" % (code, why))
        print("\n  Nothing is proved either way. Fix the call before believing")
        print("  any number above - Jane can see two cases on her screen, so a")
        print("  zero here means this script is wrong, not the pipeline.")
        return 1
    if disagree:
        print("THE QUEUE DOES NOT MATCH THE DEAL STORE")
        print("=" * 84)
        for code, real, shown in disagree:
            print("  * %s: %d waiting, %d shown" % (code, real, shown))
        print("\n  A case waiting for a committee that its own members cannot")
        print("  see does not get decided. This is the bug to chase.")
        return 1
    print("THE QUEUE AGREES WITH THE DEAL STORE")
    print("=" * 84)
    print("\n  Where a committee shows 0, nothing is waiting for it. That is a")
    print("  fact about the pipeline, not a fault - put a case in front of it")
    print("  and it will appear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Set how a committee decides. DRY RUN by default.

    python scripts\set_committee_voting_rule.py
    python scripts\set_committee_voting_rule.py --committee B4 \
        --rule SINGLE_APPROVER --apply

THE RULES:

    SIMPLE_MAJORITY            more than half of those voting. A tie is
                               REJECTED - the defensive default.
    SUPERMAJORITY_TWO_THIRDS   two thirds or more
    UNANIMOUS                  everyone voting says yes
    CHAIR_TIEBREAKER           majority, and the chair breaks a tie
    SINGLE_APPROVER            ONE YES APPROVES, whatever else is cast

SINGLE_APPROVER IS A REAL REDUCTION IN CONTROL and the script says so before it
writes. It suits a department committee that screens cases on their way
somewhere else. It does not suit the body that grants final authority, and this
refuses to set it on a board or management committee without --i-mean-it.

A dissenting vote is still recorded and named in the outcome, so a single
approval never quietly erases an objection.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")
RULES = ("SIMPLE_MAJORITY", "SUPERMAJORITY_TWO_THIRDS", "UNANIMOUS",
         "CHAIR_TIEBREAKER", "SINGLE_APPROVER")
FINAL_AUTHORITY = ("board", "management")


def main():
    apply = "--apply" in sys.argv
    forced = "--i-mean-it" in sys.argv
    code = rule = ""
    for flag in ("--committee", "--rule"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--committee":
                    code = sys.argv[i + 1].strip().upper()
                else:
                    rule = sys.argv[i + 1].strip().upper()

    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []

    print("=" * 74)
    print("HOW EACH COMMITTEE DECIDES")
    print("=" * 74)
    for c in pal:
        print("  %-4s %-44s %s" % (c.get("code"), str(c.get("name"))[:44],
                                   c.get("voting_rule") or "SIMPLE_MAJORITY"))

    if not (code or rule):
        print("\n  THE RULES YOU CAN SET")
        for r in RULES:
            print("     %s" % r)
        print("\n  To change one:")
        print("     python scripts\\set_committee_voting_rule.py \\")
        print("         --committee B4 --rule SINGLE_APPROVER --apply")
        return 0

    if rule not in RULES:
        print("\nABORT: %r is not a rule. Choose from: %s"
              % (rule, ", ".join(RULES)))
        return 1
    c = next((x for x in pal if str(x.get("code", "")).upper() == code), None)
    if not c:
        print("\nABORT: there is no committee %r." % code)
        return 1

    was = c.get("voting_rule") or "SIMPLE_MAJORITY"
    print("\n  %s  %s" % (code, c.get("name")))
    print("     from  %s" % was)
    print("     to    %s" % rule)
    if was == rule:
        print("\n  No change.")
        return 0

    name = str(c.get("name", "")).lower()
    if rule == "SINGLE_APPROVER":
        print("\n  *** ONE MEMBER'S APPROVAL WILL CARRY A CASE HERE.")
        print("      A dissenting vote is still recorded and named in the")
        print("      outcome, so an objection is not erased - but it does not")
        print("      stop the case.")
        if any(w in name for w in FINAL_AUTHORITY) and not forced:
            print("\nABORT: %r looks like a body that grants FINAL authority."
                  % c.get("name"))
            print("       A single approver there means one person can commit")
            print("       the bank. If that is genuinely intended, re-run with")
            print("       --i-mean-it.")
            return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_rule_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    c["voting_rule"] = rule
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("\nRESTART UVICORN. Cases already before this committee use the new")
    print("rule when they are resolved - votes already cast still count.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

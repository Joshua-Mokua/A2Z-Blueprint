#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Show and set everything that governs a committee, in one place.

Four settings decide how a committee behaves, and they interact:

    members              who may vote
    quorum               how many must vote before the decision counts
    voting rule          how the votes are read once quorum is met
    chair required       whether the chair or a deputy must be one of them
    amount threshold     the value at or above which this committee is used

    python scripts/committee_settings.py
    python scripts/committee_settings.py --committee B1
    python scripts/committee_settings.py --committee B1 --threshold 5000000 --apply

Read only without --apply. Members are edited on the Committee Admin screen,
not here.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")


def kes(v):
    try:
        return "KES %s" % format(int(float(v or 0)), ",")
    except (TypeError, ValueError):
        return str(v or "-")


def main():
    apply = "--apply" in sys.argv
    code = ""
    threshold = None
    for flag in ("--committee", "--threshold"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--committee":
                    code = sys.argv[i + 1].strip().upper()
                else:
                    try:
                        threshold = float(sys.argv[i + 1])
                    except ValueError:
                        print("--threshold must be a number.")
                        return 1

    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
    default_q = (cfg.get("credit_workflow") or {}).get("default_min_quorum")
    default_q = 2 if default_q is None else int(default_q)

    show = [c for c in pal if not code or str(c.get("code", "")).upper() == code]
    if code and not show:
        print("There is no committee %r." % code)
        return 1

    for c in show:
        members = [m for m in (c.get("members") or [])
                   if isinstance(m, dict) and str(m.get("staff_code", "")).strip()]
        q = c.get("min_quorum_count")
        q_eff = int(q) if q is not None else default_q
        rule = c.get("voting_rule") or "SIMPLE_MAJORITY"
        chair_req = c.get("chair_vote_required", True)
        chair = c.get("chaired_by") or ""
        deps = [m for m in members if m.get("deputy_chair")]
        thr = c.get("amount_threshold_kes")

        print("=" * 76)
        print("%s  %s" % (c.get("code"), c.get("name")))
        print("=" * 76)
        print("  members           %d" % len(members))
        for m in members:
            marks = []
            if str(m.get("name", "")).strip().lower() == str(chair).strip().lower():
                marks.append("chair")
            if m.get("deputy_chair"):
                marks.append("deputy")
            print("     %-9s %-28s %s"
                  % (m.get("staff_code"), str(m.get("name"))[:28],
                     ("(" + ", ".join(marks) + ")") if marks else ""))
        print("  quorum            %s%s"
              % (q_eff, "" if q is not None else "  (bank default)"))
        print("  voting rule       %s" % rule)
        print("  chair must vote   %s" % ("yes" if chair_req else "no"))
        if chair_req and not deps and chair:
            on = any(str(m.get("name", "")).strip().lower()
                     == str(chair).strip().lower() for m in members)
            if not on:
                print("     the named chair is not a member - the requirement")
                print("     is ignored, or nothing here could ever close")
            else:
                print("     no deputy named - if the chair is away this stalls")
        print("  used at or above  %s" % (kes(thr) if thr is not None else "no limit set"))

        # What this combination actually means in practice.
        print("\n  In practice:")
        if q_eff <= 1:
            print("     ONE person's vote decides. A committee of one is not a")
            print("     committee - the default floor of 2 exists because an")
            print("     audit found a single YES approving a facility.")
        elif rule == "SINGLE_APPROVER":
            print("     %d members must vote; one YES among them approves."
                  % q_eff)
        elif rule == "UNANIMOUS":
            print("     %d must vote and all must say yes." % q_eff)
        elif rule == "SUPERMAJORITY_TWO_THIRDS":
            print("     %d must vote and two thirds must say yes." % q_eff)
        else:
            print("     %d must vote and more than half must say yes." % q_eff)
        if q_eff > len(members) and members:
            print("     Quorum is higher than the membership - nothing here")
            print("     can ever be decided.")
        if not chair_req:
            print("     The chair need not be among them.")
        print("")

    if threshold is None or not code:
        if not code:
            print("Name one to change its threshold:")
            print("   python scripts/committee_settings.py --committee B1 \\")
            print("       --threshold 5000000 --apply")
        return 0

    c = show[0]
    was = c.get("amount_threshold_kes")
    print("  threshold from %s to %s" % (kes(was), kes(threshold)))
    print("  Deals at or above this value use this committee.")
    others = sorted(((x.get("amount_threshold_kes") or 0), x.get("code"))
                    for x in pal if x is not c
                    and x.get("amount_threshold_kes") is not None)
    if others:
        print("\n  The other thresholds, for comparison:")
        for t, cd in others:
            print("     %-5s %s" % (cd, kes(t)))
        clash = [cd for t, cd in others if abs(float(t) - threshold) < 1]
        if clash:
            print("\n  %s already sits at this value. Two committees with the"
                  % ", ".join(clash))
            print("  same threshold means the routing has to break the tie some")
            print("  other way, which is rarely what anybody intended.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_thr_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    c["amount_threshold_kes"] = threshold
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

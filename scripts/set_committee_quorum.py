#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Set how many members must vote before a committee's decision stands.

The voting rule decides the OUTCOME. Quorum decides whether the vote is
counted at all. A committee on SINGLE_APPROVER with a quorum of 2 still waits
for two people - one YES among them approves, but one YES on its own does not
reach the gate.

    python scripts/set_committee_quorum.py
    python scripts/set_committee_quorum.py --committee B1 --quorum 1 --apply

Read only without --apply.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")


def main():
    apply = "--apply" in sys.argv
    forced = "--i-mean-it" in sys.argv
    code = ""
    quorum = None
    for flag in ("--committee", "--quorum"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--committee":
                    code = sys.argv[i + 1].strip().upper()
                else:
                    try:
                        quorum = int(sys.argv[i + 1])
                    except ValueError:
                        print("--quorum must be a number.")
                        return 1

    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
    default = (cfg.get("credit_workflow") or {}).get("default_min_quorum")

    print("=" * 78)
    print("HOW MANY MUST VOTE")
    print("=" * 78)
    print("  bank default  %s\n" % (default if default is not None else "2"))
    print("  %-4s %-38s %-9s %s" % ("", "COMMITTEE", "QUORUM", "RULE"))
    for c in pal:
        q = c.get("min_quorum_count")
        members = [m for m in (c.get("members") or [])
                   if isinstance(m, dict) and str(m.get("staff_code", "")).strip()]
        print("  %-4s %-38s %-9s %s"
              % (c.get("code"), str(c.get("name"))[:38],
                 q if q is not None else "(default)",
                 c.get("voting_rule") or "SIMPLE_MAJORITY"))
        if len(members) and q is not None and q > len(members):
            print("       quorum %s but only %d member(s) - nothing can ever"
                  " reach it" % (q, len(members)))

    if not code or quorum is None:
        print("\n  To change one:")
        print("     python scripts/set_committee_quorum.py --committee B1 \\")
        print("         --quorum 1 --apply")
        return 0

    c = next((x for x in pal if str(x.get("code", "")).upper() == code), None)
    if not c:
        print("\nThere is no committee %r." % code)
        return 1

    members = [m for m in (c.get("members") or [])
               if isinstance(m, dict) and str(m.get("staff_code", "")).strip()]
    was = c.get("min_quorum_count")
    print("\n  %s  %s" % (code, c.get("name")))
    print("     members   %d" % len(members))
    print("     from      %s" % (was if was is not None else "(default)"))
    print("     to        %s" % quorum)

    if quorum > len(members) and members:
        print("\n  Quorum %d but only %d member(s). No decision could ever"
              % (quorum, len(members)))
        print("  reach it. Refusing.")
        return 1

    if quorum <= 1:
        print("\n  A quorum of %d means ONE PERSON'S VOTE DECIDES." % quorum)
        print("")
        print("  The default floor is 2 because of an audit finding: a single")
        print("  YES had approved a credit facility. The arithmetic was right;")
        print("  nothing checked how many people had voted. The note in the")
        print("  code reads: one person is not a committee.")
        print("")
        print("  Setting 1 here reverses that control for this committee. It")
        print("  may be the right call for a screening body that is one step")
        print("  in a longer chain - but it should be a decision somebody has")
        print("  taken, not a side effect of wanting cases to move.")
        if not forced:
            print("\n  If that is intended, re-run with --i-mean-it.")
            return 1

    if was == quorum:
        print("\n  No change.")
        return 0
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_quorum_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    c["min_quorum_count"] = quorum
    c["quorum_set_at"] = datetime.now().isoformat(timespec="seconds")
    if quorum <= 1:
        c["quorum_note"] = ("set to %d deliberately; the default floor of 2 "
                            "comes from an audit finding that one person is "
                            "not a committee" % quorum)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn. Cases already waiting close on the next vote, or")
    print("run close_waiting_committees.py to sweep the ones already voted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

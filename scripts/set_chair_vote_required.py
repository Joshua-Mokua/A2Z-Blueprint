#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Say whether a committee needs its chair's vote to close. DRY RUN by default.

    python scripts\set_chair_vote_required.py
    python scripts\set_chair_vote_required.py --committee B1 --off --apply
    python scripts\set_chair_vote_required.py --committee B1 --on  --apply

REQUIRED (the default) - the decision closes only when quorum is met AND the
chair, or a named deputy, has voted. Right for a body whose chair carries the
authority.

NOT REQUIRED - quorum alone closes it. Right where the bank has decided the
chair's presence is not a condition, and where a fully-voted committee sitting
still because one person is on leave is the worse outcome.

QUORUM APPLIES EITHER WAY. This says whether a PARTICULAR person must have
voted, not how many must have.

IT REFUSES ON A BOARD OR MANAGEMENT COMMITTEE without --i-mean-it. Those bodies
grant final authority, and "the chair need not be there" is a different
proposition for them than for a department screening committee.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")
FINAL_AUTHORITY = ("board", "management")


def main():
    apply = "--apply" in sys.argv
    forced = "--i-mean-it" in sys.argv
    off = "--off" in sys.argv
    on = "--on" in sys.argv
    code = ""
    if "--committee" in sys.argv:
        i = sys.argv.index("--committee")
        if i + 1 < len(sys.argv):
            code = sys.argv[i + 1].strip().upper()

    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []

    print("=" * 78)
    print("DOES THE CHAIR HAVE TO VOTE?")
    print("=" * 78)
    for c in pal:
        req = c.get("chair_vote_required", True)
        members = [m for m in (c.get("members") or [])
                   if isinstance(m, dict) and str(m.get("staff_code", "")).strip()]
        deps = [m for m in members if m.get("deputy_chair")]
        ops = [m for m in members if "operations" in str(m.get("role", "")).lower()]
        note = ""
        if req and not deps and not ops and members:
            note = "   <- and no deputy: it stalls if the chair is away"
        print("  %-4s %-40s %s%s"
              % (c.get("code"), str(c.get("name"))[:40],
                 "required" if req else "not required", note))

    if not code:
        print("\n  To change one:")
        print("     python scripts\\set_chair_vote_required.py \\")
        print("         --committee B1 --off --apply")
        print("\n  Naming a deputy is the OTHER answer, and often the better")
        print("  one - it keeps a named person accountable for closing the")
        print("  vote:  python scripts\\name_deputy_chairs.py")
        return 0

    if off == on:
        print("\nABORT: choose one of --off or --on.")
        return 1
    c = next((x for x in pal if str(x.get("code", "")).upper() == code), None)
    if not c:
        print("\nABORT: there is no committee %r." % code)
        return 1

    was = bool(c.get("chair_vote_required", True))
    now = not off
    print("\n  %s  %s" % (code, c.get("name")))
    print("     from  %s" % ("required" if was else "not required"))
    print("     to    %s" % ("required" if now else "not required"))
    if was == now:
        print("\n  No change.")
        return 0

    name = str(c.get("name", "")).lower()
    if off:
        print("\n  *** THIS COMMITTEE WILL DECIDE WITHOUT ITS CHAIR.")
        print("      Quorum still applies - enough members must vote. What")
        print("      changes is that no PARTICULAR person has to be one of")
        print("      them.")
        print("      A decision taken in the chair's absence is recorded as")
        print("      such, not left looking like one they attended.")
        if any(w in name for w in FINAL_AUTHORITY) and not forced:
            print("\nABORT: %r grants FINAL authority." % c.get("name"))
            print("       'The chair need not be there' is a different")
            print("       proposition for that body than for a department")
            print("       screening committee. If it is genuinely intended,")
            print("       re-run with --i-mean-it.")
            return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_chairreq_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    c["chair_vote_required"] = now
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("\nRESTART UVICORN. A case already waiting on the chair closes as")
    print("soon as the next vote arrives, or on the votes already cast when")
    print("the endpoint is next called.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

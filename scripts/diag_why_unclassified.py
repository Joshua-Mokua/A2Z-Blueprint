#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Why are these deals unclassified? READ ONLY.

FROM THE BANK (2026-09-04): "the list of unclassified is growing - could it be
the CIB, who are based at head office, since for them the branch was not really
a must but we were capturing their segment?"

A fair hypothesis and worth testing rather than assuming. Three different
things get called "unclassified" and they have different causes:

    NO BRANCH        the deal carries no originating branch, so it shows as
                     unassigned in branch views
    NO SEGMENT       client_type does not map to consumer / commercial / cib,
                     so no segment analyst owns it
    SECTOR "OTHER"   the officer chose "Other / Not Classified" from the CBK
                     sector list - a real option, chosen not defaulted

    python scripts\diag_why_unclassified.py

Prints each, and crosses them with the OWNER'S UNIT - so if it is the CIB desk
at head office, that will be visible rather than inferred.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def main():
    from utils.core import PipelineManager
    try:
        from utils.api_lms_scope import _app_segment
    except Exception:
        _app_segment = lambda a: ""
    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
        unit_of = {}
        for _i, r in roster.iterrows():
            c = str(r.get("Staff Code") or "").strip()
            if c:
                unit_of[c] = str(r.get("Unit") or r.get("Department") or "").strip()
    except Exception:
        unit_of = {}

    deals = PipelineManager().deals or []
    print("=" * 84)
    print("WHY ARE DEALS UNCLASSIFIED?")
    print("=" * 84)
    print("  deals  %d\n" % len(deals))

    no_branch, no_segment, other_sector = [], [], []
    for d in deals:
        if not str(d.get("branch") or "").strip():
            no_branch.append(d)
        if not (_app_segment(d) or ""):
            no_segment.append(d)
        sec = str(d.get("sector") or "").strip().lower()
        if not sec or "not classified" in sec or sec == "other":
            other_sector.append(d)

    def by_unit(rows, title):
        print("  %s: %d" % (title, len(rows)))
        if not rows:
            return
        c = Counter(unit_of.get(str(r.get("staff_code") or "").strip(), "(unknown)")
                    for r in rows)
        for u, n in c.most_common(6):
            print("     %-42s %d" % (str(u)[:42], n))
        ct = Counter(str(r.get("client_type") or "(blank)") for r in rows)
        print("     client types: %s"
              % ", ".join("%s=%d" % (k, v) for k, v in ct.most_common(5)))
        print("")

    by_unit(no_branch, "NO BRANCH - shows as unassigned")
    by_unit(no_segment, "NO SEGMENT - no segment analyst owns it")
    by_unit(other_sector, "SECTOR is Other / Not Classified")

    print("=" * 84)
    print("READING THIS")
    print("=" * 84)
    print("  If the units above are the CIB desk and head office, the")
    print("  hypothesis holds and the fix is to ask head office for a branch")
    print("  too - which BF1 and BF3 already do once the toggle is on.")
    print("\n  If the units are BRANCHES, it is not CIB: those deals were")
    print("  raised before the branch field was shown to branch officers, and")
    print("  backfill_branch_from_validator.py will place most of them.")
    print("\n  SECTOR is a separate question. 'Other / Not Classified' is a")
    print("  real CBK option that officers are CHOOSING - it is not a default")
    print("  and not a missing field. If it is being chosen for speed, that is")
    print("  a training matter before it is a code one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

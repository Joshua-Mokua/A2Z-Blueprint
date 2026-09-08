#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""List every register entry that will cause a validation refusal.

Two faults do it, and both look identical to a user: a staff code that appears
more than once, and an officer with no branch at all. Either way a lookup
cannot resolve a branch, the branch test matches nothing, and the deal reads
"not yours to validate".

    python scripts/list_incomplete_register_rows.py

Read only. Fix these in the register and the whole class stops.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def main():
    from utils.api_pipeline_scope import get_staff_roster
    from utils.core import PipelineManager

    df = get_staff_roster()
    col = "Branch" if "Branch" in df.columns else "Unit"
    deals = PipelineManager().deals or []
    owns = Counter(str(d.get("staff_code", "") or "").strip() for d in deals)

    rows = []
    for _i, r in df.iterrows():
        rows.append({
            "code": str(r.get("Staff Code") or "").strip(),
            "name": str(r.get("Staff Name") or "").strip(),
            "role": str(r.get("Role") or "").strip(),
            "branch": str(r.get(col) or "").strip(),
        })

    codes = Counter(x["code"] for x in rows if x["code"])
    dupes = sorted(c for c, n in codes.items() if n > 1)
    nobranch = [x for x in rows if x["code"] and not x["branch"]]

    print("=" * 88)
    print("REGISTER ENTRIES THAT WILL REFUSE A VALIDATION")
    print("=" * 88)
    print("  rows in the register  %d" % len(rows))
    print("  duplicate codes       %d" % len(dupes))
    print("  no %-18s %d\n" % (col.lower() + ":", len(nobranch)))

    if dupes:
        print("  DUPLICATE STAFF CODES")
        print("  %-9s %-26s %-30s %-16s %s"
              % ("CODE", "NAME", "ROLE", col.upper(), "DEALS"))
        for c in dupes:
            for x in [y for y in rows if y["code"] == c]:
                print("  %-9s %-26s %-30s %-16s %s"
                      % (x["code"], x["name"][:26], x["role"][:30],
                         x["branch"] or "-", owns.get(c, 0)))
            print("")

    hurt = [x for x in nobranch if owns.get(x["code"], 0) > 0]
    if hurt:
        print("  NO %s, AND THEY OWN DEALS - these are the ones users hit"
              % col.upper())
        print("  %-9s %-26s %-30s %s" % ("CODE", "NAME", "ROLE", "DEALS"))
        for x in sorted(hurt, key=lambda y: -owns.get(y["code"], 0)):
            print("  %-9s %-26s %-30s %d"
                  % (x["code"], x["name"][:26], x["role"][:30],
                     owns.get(x["code"], 0)))

    quiet = [x for x in nobranch if not owns.get(x["code"], 0)]
    if quiet:
        print("\n  No %s and no deals yet - they will hit this the first time"
              % col.lower())
        print("  they raise one: %d officer(s)" % len(quiet))
        for x in quiet[:10]:
            print("     %-9s %-26s %s" % (x["code"], x["name"][:26], x["role"][:30]))
        if len(quiet) > 10:
            print("     ... and %d more" % (len(quiet) - 10))

    print("\n" + "=" * 88)
    if not dupes and not nobranch:
        print("Every entry can resolve a branch.")
        print("=" * 88)
        return 0
    print("What to do")
    print("=" * 88)
    print("  A duplicate: deactivate the incomplete account from the staff")
    print("  registry - not delete, so the audit trail still points at a")
    print("  person who exists.")
    print("")
    print("  No %s: fill it in. One cell, and every deal that officer"
          % col.lower())
    print("  raises from then on inherits it.")
    print("")
    print("  DD1 makes the system pick the complete row meanwhile, so nobody")
    print("  is blocked while this is tidied. It does not make the register")
    print("  right.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Add reasons a credit analyst can return a case for rework. DRY RUN by default.

FROM THE BANK (2026-09-04): the twelve reasons configured today are all
commercial - audited accounts, collateral valuation, board resolution, title
deed. Nothing covers a consumer case, so an analyst returning a salaried loan
had to pick something that did not describe the problem.

    python scripts\set_rework_reasons.py
    python scripts\set_rework_reasons.py --apply
    python scripts\set_rework_reasons.py --add "Some other reason" --apply
    python scripts\set_rework_reasons.py --remove "Land search required" --apply

WHAT IS BEING ADDED, and why each is worded as it is:

    1/3 rule violation
        The statutory limit on how much of a salary can service debt. Named
        the way the credit team says it, not "affordability breach" - a reason
        code an analyst has to translate is a reason code they will not use.

    Loan limit - multiplier exceeded
        The salary multiplier cap. "exceeded" added: "loan limit - multiplier"
        alone does not say what is wrong with it.

    CRB report - adverse listing or score
        NOT a duplicate of "CRB report outstanding", which already exists and
        means the report is MISSING. This one means the report arrived and
        something in it is the problem. Two different conversations with the
        customer, so two different codes.

    Tenor outside product terms
    Statements not certified or confirmed
    DSR outside policy
    Payslip and salary statement do not match
    Pricing outside approved band

NOTHING IS REMOVED. The commercial reasons stay; a bank does both kinds of
lending.

Writes to data/lms_config.json - the deployment's own file, which does not
travel in a release. Alex runs this on his side.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")

CONSUMER = [
    "1/3 rule violation",
    "Loan limit - multiplier exceeded",
    "CRB report - adverse listing or score",
    "Tenor outside product terms",
    "Statements not certified or confirmed",
    "DSR outside policy",
    "Payslip and salary statement do not match",
    "Pricing outside approved band",
]


def main():
    apply = "--apply" in sys.argv
    add, remove = list(CONSUMER), []
    if "--add" in sys.argv:
        i = sys.argv.index("--add")
        if i + 1 < len(sys.argv):
            add = [sys.argv[i + 1]]
    if "--remove" in sys.argv:
        i = sys.argv.index("--remove")
        if i + 1 < len(sys.argv):
            remove = [sys.argv[i + 1]]
            add = []

    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    current = [str(r) for r in (cfg.get("rework_reasons") or [])]

    print("=" * 76)
    print("REASONS A CASE CAN BE RETURNED FOR REWORK")
    print("=" * 76)
    print("  configured now  %d" % len(current))
    for r in current:
        print("     %s" % r)

    lower = {r.strip().lower() for r in current}
    new = [r for r in add if r.strip().lower() not in lower]
    dupes = [r for r in add if r.strip().lower() in lower]
    gone = [r for r in remove if r.strip().lower() in lower]
    absent = [r for r in remove if r.strip().lower() not in lower]

    if new:
        print("\n  TO ADD (%d)" % len(new))
        for r in new:
            print("     %s" % r)
    if dupes:
        print("\n  ALREADY THERE, skipped")
        for r in dupes:
            print("     %s" % r)
    if gone:
        print("\n  TO REMOVE")
        for r in gone:
            print("     %s" % r)
    if absent:
        print("\n  NOT CONFIGURED, cannot remove")
        for r in absent:
            print("     %s" % r)

    # A near-duplicate is worth flagging: two codes that mean almost the same
    # thing get used interchangeably and the reporting stops meaning anything.
    for r in new:
        head = r.split()[0].lower()
        near = [c for c in current
                if c.lower().startswith(head) and c.strip().lower() != r.strip().lower()]
        if near:
            print("\n  *** %r sits close to:" % r)
            for c in near:
                print("        %s" % c)
            print("      Two codes that mean nearly the same thing get used")
            print("      interchangeably, and the reporting stops meaning")
            print("      anything. Keep both only if they describe DIFFERENT")
            print("      problems - a report that is missing is not a report")
            print("      that is bad.")

    after = [r for r in current if r.strip().lower()
             not in {x.strip().lower() for x in gone}] + new
    if after == current:
        print("\n  No change.")
        return 0
    print("\n  AFTER  %d reason(s)" % len(after))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_rework_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    cfg["rework_reasons"] = after
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("\nRESTART UVICORN. The new reasons appear wherever an analyst")
    print("returns a case - no rebuild needed, the list is read at run time.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

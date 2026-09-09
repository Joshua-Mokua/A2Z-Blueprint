#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fill the condition library credit risk picks from.

The endpoints and the two groups already exist - pre_approval and
pre_disbursement - and the library is empty, so the decision screen has nothing
to offer and every condition has to be typed by hand.

    python scripts/set_condition_library.py
    python scripts/set_condition_library.py --seed --apply
    python scripts/set_condition_library.py --add-pre-disbursement "New one" --apply

The seed is a starting point from what the committees have actually been
writing on cases. The bank should edit it - a library nobody recognises gets
ignored and people type their own anyway.

Read only without --apply.
"""
import json
import os
import shutil
import sys
from datetime import datetime

CFG = os.path.join("data", "lms_config.json")

SEED_PRE_APPROVAL = [
    "Satisfactory CRB report",
    "Employer confirmation / callback verification",
    "Certified and confirmed bank statements",
    "Payslip and salary statement reconciled",
    "DSR within policy",
    "1/3 rule satisfied",
    "Facility within the salary multiplier",
    "Tenor within product terms",
    "Pricing within the approved band",
    "PEP screening cleared",
]

SEED_PRE_DISBURSEMENT = [
    "Salary domiciliation confirmed",
    "Signed offer letter on file",
    "Loan agreement executed",
    "Credit life insurance in place",
    "Security perfected / charge registered",
    "Existing facility offsets confirmed",
    "Standing order or check-off instruction lodged",
    "Account open and active",
    "KYC complete and current",
    "Disbursement account details verified",
]


def main():
    apply = "--apply" in sys.argv
    seed = "--seed" in sys.argv
    add_pre = add_dis = ""
    for flag, var in (("--add-pre-approval", "pre"),
                      ("--add-pre-disbursement", "dis")):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if var == "pre":
                    add_pre = sys.argv[i + 1]
                else:
                    add_dis = sys.argv[i + 1]

    if not os.path.isfile(CFG):
        print("%s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    lib = dict(cfg.get("condition_library") or {})
    pre = [str(x) for x in (lib.get("pre_approval") or [])]
    dis = [str(x) for x in (lib.get("pre_disbursement") or [])]

    print("=" * 74)
    print("THE CONDITION LIBRARY")
    print("=" * 74)
    print("  pre-approval      %d" % len(pre))
    for c in pre:
        print("     %s" % c)
    print("\n  pre-disbursement  %d" % len(dis))
    for c in dis:
        print("     %s" % c)

    changed = False
    if seed:
        new_pre = [c for c in SEED_PRE_APPROVAL if c not in pre]
        new_dis = [c for c in SEED_PRE_DISBURSEMENT if c not in dis]
        if new_pre or new_dis:
            print("\n  TO SEED")
            for c in new_pre:
                print("     pre-approval      %s" % c)
            for c in new_dis:
                print("     pre-disbursement  %s" % c)
            pre, dis = pre + new_pre, dis + new_dis
            changed = True
        else:
            print("\n  Everything in the seed is already there.")
    if add_pre and add_pre not in pre:
        print("\n  adding to pre-approval: %s" % add_pre)
        pre.append(add_pre)
        changed = True
    if add_dis and add_dis not in dis:
        print("\n  adding to pre-disbursement: %s" % add_dis)
        dis.append(add_dis)
        changed = True

    if not changed:
        if not (seed or add_pre or add_dis):
            print("\n  To start from what the committees have been writing:")
            print("     python scripts/set_condition_library.py --seed --apply")
            print("\n  Or add one:")
            print('     python scripts/set_condition_library.py \\')
            print('         --add-pre-disbursement "Salary domiciliation" --apply')
        return 0

    print("\n  These are what credit risk picks from when approving, and what")
    print("  credit admin ticks off before a case can go to TROPS. Edit them")
    print("  to the bank's own wording - a library nobody recognises gets")
    print("  ignored and people type their own anyway.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_condlib_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    cfg["condition_library"] = {"pre_approval": pre, "pre_disbursement": dis}
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nWritten. Backup: %s" % os.path.basename(bak))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

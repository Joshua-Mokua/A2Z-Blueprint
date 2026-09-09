#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A referral starts at Initiation, not Lead.

The referral endpoint hardcodes stage "Lead". Nothing else in the bank's
journey uses it - the flows begin at Initiation - so a referred lead lands
outside every funnel bucket, outside the stage rules, and shows as
unclassified.

Also moves any deal already sitting at Lead.

    python scripts/patch_ld1_referrals_start_at_initiation.py            # dry run
    python scripts/patch_ld1_referrals_start_at_initiation.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '        "stage":                "Lead",'
NEW = ('        # Initiation, not Lead. The flows start at Initiation and\n'
       '        # nothing else uses Lead - a referral landing there sits\n'
       '        # outside every funnel bucket and every stage rule.\n'
       '        "stage":                "Initiation",')

DOC_OLD = '``product_type="Referral"``, ``stage="Lead"``. The portfolio'
DOC_NEW = '``product_type="Referral"``, ``stage="Initiation"``. The portfolio'


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "Initiation, not Lead" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The referral stage matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    if s.count(DOC_OLD) == 1:
        s = s.replace(DOC_OLD, DOC_NEW, 1)

    if '"stage":                "Lead"' in s:
        print("A referral would still be created at Lead.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("New referrals start at Initiation.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Deals already at Lead are moved by move_lead_deals.py.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ld1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn, then move the existing ones:")
    print("   python scripts/move_lead_deals.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

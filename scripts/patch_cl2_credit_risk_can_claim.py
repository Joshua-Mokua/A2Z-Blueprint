#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A committee-recommended case can be claimed.

Credit risk is about to be two people. Without claiming, both see the same
pool and both can work the same case - or each assumes the other has.

committee_recommended is added to the statuses that permit assignment, the
same way referred_to_committee was when a case coming back from committee
could be seen and not picked up.

    python scripts/patch_cl2_credit_risk_can_claim.py            # dry run
    python scripts/patch_cl2_credit_risk_can_claim.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_mutations.py")

OLD = "    'analyst_confirmed',\n}"
NEW = ("    'analyst_confirmed',\n"
       "    # Credit risk is about to be two people. Without this they share a\n"
       "    # pool and both work the same case, or each assumes the other has.\n"
       "    'committee_recommended',\n}")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "committee_recommended" in s:
        print("Already applied.")
        return 1
    if "STATUSES_PERMITTING_ASSIGN" not in s:
        print("The status set is not in this file.")
        return 1
    if s.count(OLD) != 1:
        print("The status set matched %d times." % s.count(OLD))
        print("Apply allow_claim_after_committee.py first - this extends it.")
        return 1

    s = s.replace(OLD, NEW, 1)

    for keep in ("'submitted'", "'referred_to_committee'"):
        if keep not in s:
            print("%s was lost from the set." % keep)
            return 1
    for bad in ("disbursed", "declined", "closed"):
        i = s.index("STATUSES_PERMITTING_ASSIGN")
        if bad in s[i:s.index("}", i)]:
            print("A %s case could be claimed, which reopens finished work." % bad)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A committee-recommended case can be claimed.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cl2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

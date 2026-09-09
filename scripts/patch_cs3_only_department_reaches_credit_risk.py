#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Only a DEPARTMENT committee's recommendation reaches credit risk.

CS2 marks a case committee_recommended whenever any committee approves. A
BRANCH committee also recommends, and its recommendation means something quite
different: the case goes to the segment analyst, not to credit risk.

So Korir's screen showed ten cases where five belong to him. Seven had come
from BCC_BRN014, BCC_BRN009, BCC_BRN005, BCC_BRN012 and BCC_BRN017 - branch
committees whose work sends a case to Catherine and the commercial analysts.

A branch committee still records its outcome and still advances the deal.
It just does not mark the case as ready for credit risk.

    python scripts/patch_cs3_only_department_reaches_credit_risk.py            # dry run
    python scripts/patch_cs3_only_department_reaches_credit_risk.py --apply

Branch committees are identified by their code - BCC_BRN* - which is how the
palette generates them.
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''        if str(outcome).upper() in ("APPROVED", "RECOMMENDED", "SUPPORTED"):
            _app_id = str(deal.get("lms_application_id") or "").strip()
            if _app_id:'''

NEW = '''        # ── ONLY A DEPARTMENT COMMITTEE SENDS A CASE TO CREDIT RISK ─────────
        # A branch committee recommends too, and its recommendation means the
        # case goes to the SEGMENT ANALYST. Marking it ready for credit risk
        # put seven branch cases on Korir's screen alongside the five that were
        # his, and neither he nor the funnel could tell them apart.
        #
        # A branch committee still records its outcome and still advances the
        # deal. It just does not mark the case ready for credit risk.
        _is_branch_cttee = str(code or "").upper().startswith("BCC_BRN")
        if (not _is_branch_cttee
                and str(outcome).upper() in ("APPROVED", "RECOMMENDED", "SUPPORTED")):
            _app_id = str(deal.get("lms_application_id") or "").strip()
            if _app_id:'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "ONLY A DEPARTMENT COMMITTEE SENDS" in s:
        print("Already applied.")
        return 1
    if "AND SAY SO ON THE CREDIT CASE" not in s:
        print("CS2 is not applied - there is nothing to narrow.")
        return 1
    if s.count(OLD) != 1:
        print("The approval block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "BCC_BRN" not in NEW:
        print("Branch committees are not identified.")
        return 1
    # The deal must still advance and the record must still be written for a
    # branch committee - this narrows one thing only.
    i = s.index("ONLY A DEPARTMENT COMMITTEE SENDS")
    before = s[max(0, i - 2000):i]
    if "committee_records" not in before:
        print("The committee record is no longer written before this. A branch")
        print("committee must still record its outcome.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Only a department committee marks a case ready for credit risk.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cs3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nThe seven already marked from branch committees stay marked.")
    print("Put them back with:")
    print("   python scripts/unmark_branch_recommendations.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

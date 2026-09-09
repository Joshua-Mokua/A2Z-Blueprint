#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Let the TROPS team see credit admin cases.

Two gates stand between TROPS and a disbursement:

    seeing the case      _is_credit_admin_department_role - no TROPS term
    disbursing it        disbursement_roles - ["Treasury Back Office"]

The register spells the roles "Service Officer, TROPS" and "Team Leader-Trade &
Trops". Neither matches either gate, so nobody in the bank can disburse and
nobody can see the cases waiting to be.

This fixes the first gate. The second is config:

    python scripts/set_disbursement_roles.py --add trops --apply

TROPS is matched as a WORD. It is short enough to appear inside other words,
and this grants department-wide visibility.

    python scripts/patch_tr1_trops_sees_and_disburses.py            # dry run
    python scripts/patch_tr1_trops_sees_and_disburses.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_credit_admin_scope.py")

OLD = '    if "chief credit" in role or "credit admin" in role or "credit administrat" in role:'

NEW = '''    # TROPS settle and disburse, so they need to see the cases that reach
    # them. The register writes "Service Officer, TROPS" and "Team
    # Leader-Trade & Trops" - matched as a word, since this grants
    # department-wide visibility and a substring would be too generous.
    if _re_trops.search(role):
        return True
    if "chief credit" in role or "credit admin" in role or "credit administrat" in role:'''

ANCHOR = "def _is_credit_admin_department_role"
BLOCK = '''# "Service Officer, TROPS" and "Team Leader-Trade & Trops" are how the register
# writes the settlement team. Word-bounded, and it covers the TROOPS spelling
# the codebase uses in places.
_re_trops = _re.compile(r"\\btro+ps\\b")


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "_re_trops" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The role check matched %d times." % s.count(OLD))
        return 1
    if s.count(ANCHOR) != 1:
        print("The function matched %d times." % s.count(ANCHOR))
        return 1

    if "import re as _re" not in s:
        imp = "from typing import"
        if s.count(imp) != 1:
            print("Could not find the import block.")
            return 1
        s = s.replace(imp, "import re as _re\n" + imp, 1)
    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    s = s.replace(OLD, NEW, 1)

    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1

    import re
    rx = re.compile(r"\btro+ps\b")
    should = ["service officer, trops", "team leader-trade & trops",
              "troops officer", "head of trops"]
    shouldnt = ["tropical desk", "metropolis manager", "trophy"]
    bad = [r for r in should if not rx.search(r)] + \
          [r for r in shouldnt if rx.search(r)]
    if bad:
        print("The pattern is wrong on: %s" % ", ".join(bad))
        return 1
    print("Matches TROPS and TROOPS; not tropical, metropolis or trophy.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_tr1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nThey can now SEE the cases. They still cannot disburse until:")
    print("   python scripts/set_disbursement_roles.py --add trops --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())

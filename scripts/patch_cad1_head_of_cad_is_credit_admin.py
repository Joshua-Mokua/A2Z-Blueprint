#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Recognise "Head, CAD" as a credit admin department role.

The department-wide check matches spelled-out role strings - "credit admin",
"credit administrat", "chief credit". Sera's role is the abbreviation, "Head,
CAD", which contains none of them. Her own officers see every case in the
department and she sees none, because a case would never have her as the RM.

CAD is matched as a WORD, not a substring: "cad" appears inside academic,
cadre and decade, and this grants department-wide visibility, so a loose match
would hand it to people it was never meant for.

    python scripts/patch_cad1_head_of_cad_is_credit_admin.py            # dry run
    python scripts/patch_cad1_head_of_cad_is_credit_admin.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_credit_admin_scope.py")

OLD = ('    if "chief credit" in role or "credit admin" in role '
       'or "credit administrat" in role:')

NEW = '''    # CAD is the abbreviation the register uses - "Head, CAD", "CAD Officer".
    # Matched as a WORD: "cad" sits inside academic, cadre and decade, and this
    # grants department-wide visibility, so a substring match would hand it to
    # roles it was never meant for.
    if _re_cad.search(role):
        return True
    if "chief credit" in role or "credit admin" in role or "credit administrat" in role:'''

IMPORT_ANCHOR = "def _is_credit_admin_department_role"
IMPORT_BLOCK = '''# "Head, CAD" and "CAD Officer" are how the register abbreviates the Credit
# Administration Department. Word-bounded so it cannot match academic or cadre.
_re_cad = _re.compile(r"\\bcad\\b")


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "_re_cad" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The role check matched %d times." % s.count(OLD))
        return 1
    if s.count(IMPORT_ANCHOR) != 1:
        print("The function matched %d times." % s.count(IMPORT_ANCHOR))
        return 1

    # Sit beside the existing imports. A __future__ import must stay first,
    # so anchor on the typing line rather than guessing an offset.
    if "import re as _re" not in s:
        anchor = "from typing import"
        if s.count(anchor) != 1:
            print("Could not find the import block to add re to.")
            return 1
        s = s.replace(anchor, "import re as _re\n" + anchor, 1)
    s = s.replace(IMPORT_ANCHOR, IMPORT_BLOCK + IMPORT_ANCHOR, 1)
    s = s.replace(OLD, NEW, 1)

    if r"\bcad\b" not in s:
        print("CAD is not word-bounded.")
        return 1
    if "chief credit" not in s:
        print("The existing matches were lost.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1

    import re
    rx = re.compile(r"\bcad\b")
    should = ["head, cad", "cad officer", "head of cad", "cad manager"]
    shouldnt = ["academic advisor", "cadre lead", "decade review",
                "cadet officer", "advocacy"]
    bad = [r for r in should if not rx.search(r)] + \
          [r for r in shouldnt if rx.search(r)]
    if bad:
        print("The pattern is wrong on: %s" % ", ".join(bad))
        return 1
    print("Matches Head, CAD and CAD Officer; not academic, cadre or decade.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cad1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Sera (KE956) then sees her department's cases")
    print("the way her own officers already do.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

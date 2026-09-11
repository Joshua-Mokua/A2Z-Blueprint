#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Marking a case ready advances it even if the deal is not exactly on its
analysis stage.

RC3 finds the next committee stage only when the deal's current stage is in
the product flow: `if cur in flow`. A deal frozen at Rework by a return, or on
a stage whose spelling does not match the flow, fails that test - so the status
changes, the deal never moves, and the committee never sees the case. This is
why "the analyst cannot advance to committee".

Now, if the current stage is not found, it advances to the DEPARTMENT credit
committee stage the flow defines - which is where a marked-ready case belongs -
rather than doing nothing.

    python scripts/patch_fx2_ready_advances_from_anywhere.py            # dry run
    python scripts/patch_fx2_ready_advances_from_anywhere.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '''                    target = ""
                    # The next COMMITTEE stage ahead of where the deal stands.
                    if cur in flow:
                        for nxt in flow[flow.index(cur) + 1:]:
                            if "committee" in nxt.lower():
                                target = nxt'''

NEW = '''                    target = ""
                    # Marking ready means the DEPARTMENT committee - that is
                    # what the act is, whatever stage the deal is on. Going to
                    # the nearest committee ahead sent a case frozen at Rework
                    # to the branch committee by mistake; and "if cur in flow"
                    # left a deal on an unrecognised stage behind entirely.
                    for nxt in flow:
                        if ("department" in nxt.lower()
                                and "committee" in nxt.lower()):
                            target = nxt
                            break
                    # No department committee in this product's flow: the next
                    # committee ahead, or the last committee it has.
                    if not target and cur in flow:
                        for nxt in flow[flow.index(cur) + 1:]:
                            if "committee" in nxt.lower():
                                target = nxt
                                break
                    if not target:
                        for nxt in flow:
                            if "committee" in nxt.lower():
                                target = nxt'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1
    s = open(MOD, encoding="utf-8").read()
    if "Marking ready means the DEPARTMENT committee" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("RC3's target block matched %d times - RC3 must be applied first."
              % s.count(OLD))
        return 1
    s = s.replace(OLD, NEW, 1)
    if "department" not in NEW.lower():
        print("The fallback does not prefer the department committee.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Marking ready advances to the department committee even when the")
    print("deal's stage is not found in the flow.")
    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0
    shutil.copy2(MOD, MOD + ".pre_fx2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    py_compile.compile(MOD, doraise=True)
    print("Compiles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

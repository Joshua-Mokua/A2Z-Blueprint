#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Choose the duplicate row by the fields that decide what a person can see.

DD1 kept whichever duplicate row had the most filled-in fields. That is the
wrong measure: a row full of incidental columns can beat the one carrying
Department, Unit or Reports To - and those are what scope is built from.

A head-office analyst sees their whole Department. Lose Department on the
chosen row and their view empties. Catherine's Sales Pro went blank exactly
this way.

Scope fields now count for far more than the rest, and a row missing all of
them can never win against one that has any.

    python scripts/patch_dd2_keep_the_row_that_carries_scope.py            # dry run
    python scripts/patch_dd2_keep_the_row_that_carries_scope.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_pipeline_scope.py")

OLD = """                filled = df.notna().sum(axis=1)
                for col in df.columns:
                    filled = filled + (df[col].astype(str).str.strip() != "").astype(int)"""

NEW = """                # THE FIELDS THAT DECIDE WHAT SOMEBODY SEES COUNT FOR MORE.
                # Counting every column equally let a row full of incidental
                # values beat the one carrying Department, Unit or Reports To -
                # and scope is built from those. A head-office analyst sees
                # their whole Department; lose it and their view empties.
                SCOPE_COLS = ("Department", "Unit", "Branch", "Reports To",
                              "Role", "Region")
                filled = df.notna().sum(axis=1)
                for col in df.columns:
                    has = (df[col].astype(str).str.strip() != "").astype(int)
                    filled = filled + (has * (25 if col in SCOPE_COLS else 1))"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "SCOPE_COLS" in s:
        print("Already applied.")
        return 1
    if "ONE ROW PER STAFF CODE" not in s:
        print("DD1 is not applied - there is nothing to correct.")
        return 1
    if s.count(OLD) != 1:
        print("The scoring block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "Department" not in NEW or "Reports To" not in NEW:
        print("The fields scope is built from are not weighted.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("The row carrying Department, Unit and Reports To now wins.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_dd2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. The roster caches for a few minutes, so give it")
    print("that before checking Catherine's Sales Pro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

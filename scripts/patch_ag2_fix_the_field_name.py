#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AG1 reads the wrong field, so it has never blocked anything.

The guard reads payload.stage and payload.to_stage. PipelineDealAdvance has
neither - its field is new_stage. So _target has been empty since the day AG1
was applied, the condition never fired, and an RM walked D0747 from
Documentation to Credit Analysis on 8 September, four days after we believed
this was closed.

The self-check passed because it tested the shape of the code and never the
field name.

    python scripts/patch_ag2_fix_the_field_name.py            # dry run
    python scripts/patch_ag2_fix_the_field_name.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''    _target = str(getattr(payload, "stage", "") or getattr(payload, "to_stage", "")
                  or "").strip()'''

NEW = '''    # new_stage is what PipelineDealAdvance actually carries. Reading "stage"
    # and "to_stage" left this empty and the guard below never fired.
    _target = str(getattr(payload, "new_stage", "") or "").strip()'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if 'getattr(payload, "new_stage"' in s and '_target = str(getattr(payload, "stage"' not in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The target assignment matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # The field must be one the model really has - the whole fault was reading
    # a name that does not exist.
    mp = os.path.join("utils", "api_pipeline_models.py")
    if os.path.isfile(mp):
        m = open(mp, encoding="utf-8").read()
        i = m.find("class PipelineDealAdvance")
        if i < 0:
            print("Could not find PipelineDealAdvance to check the field against.")
            return 1
        body = m[i:m.index("\nclass ", i + 10)]
        if "new_stage" not in body:
            print("PipelineDealAdvance has no new_stage field. Check the model")
            print("before applying - this is the same mistake again.")
            return 1
        print("PipelineDealAdvance.new_stage confirmed on the model.")
    if '_target = str(getattr(payload, "stage"' in s:
        print("The old read survives.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("The guard now reads the field the request carries.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ag2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn, then TEST IT: as a non-admin, try to advance a")
    print("deal from Documentation to Department Credit Analysis. It must be")
    print("refused. If it is not, this is still not working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

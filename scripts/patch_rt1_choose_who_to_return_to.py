#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Choose who a returned case goes back to.

A return always goes to the deal's owner, and comes back to whoever returned
it. That is right when the owner has to fetch a document. It is wrong when
credit risk wants the segment analyst to redo a DSR, or the analyst wants the
recommender to revisit a condition - both end up at the owner, who cannot do
either.

Accepts return_to (a staff code) and return_to_name. Omitted, it behaves
exactly as now.

    python scripts/patch_rt1_choose_who_to_return_to.py            # dry run
    python scripts/patch_rt1_choose_who_to_return_to.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '''    lam.update(app_id, {
        "status": "returned",
        "rework_history": history,
        "rework_reasons": reason,
        # WHO TO COME BACK TO. Cleared when the owner resubmits.
        "returned_by_code": me,
        "returned_by_name": myname,
        "returned_at": datetime.now().isoformat(timespec="seconds"),
    })'''

NEW = '''    # ── WHO IT GOES TO ────────────────────────────────────────────────────
    # A return always went to the deal's owner. That is right when a document
    # is missing and wrong when the work belongs to somebody else - credit
    # risk asking the segment analyst to redo a DSR, or the analyst asking a
    # recommender to revisit a condition. Both landed on the owner, who could
    # do neither.
    #
    # return_to is a staff code from the people already on the case. Omitted,
    # this behaves exactly as before.
    _to_code = str(payload.get("return_to", "") or "").strip()
    _to_name = str(payload.get("return_to_name", "") or "").strip()

    _updates = {
        "status": "returned",
        "rework_history": history,
        "rework_reasons": reason,
        # WHO TO COME BACK TO. Cleared when the owner resubmits.
        "returned_by_code": me,
        "returned_by_name": myname,
        "returned_at": datetime.now().isoformat(timespec="seconds"),
    }
    if _to_code:
        _updates["return_to_code"] = _to_code
        _updates["return_to_name"] = _to_name
        # Assign it to them, so it lands on their screen rather than waiting
        # to be found. The pool would otherwise hide it behind everything else.
        _updates["analyst"] = {"code": _to_code, "name": _to_name, "role": ""}
    lam.update(app_id, _updates)'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "WHO IT GOES TO" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The return update matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if '"returned_by_code": me' not in NEW:
        print("The case would no longer come back to whoever returned it.")
        return 1
    if 'if _to_code:' not in NEW:
        print("Omitting return_to would change the existing behaviour.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A return can name who it goes to; omitted, nothing changes.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_rt1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. The picker is on the credit risk workbench.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

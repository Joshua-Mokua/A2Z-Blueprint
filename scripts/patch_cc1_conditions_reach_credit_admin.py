#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The conditions credit risk sets reach credit admin's tick-list.

Credit risk records a decision with pre-disbursement conditions - salary
domiciliation, offsets, perfection. The endpoint writes them to

    app["pre_disbursement_conditions"]

and the credit admin case is built from

    app["decision"]["conditions"]

Two different places. So credit admin's tick-list arrives empty, and since
nothing disburses until every condition is met, an empty list either blocks
the case or opens the gate on nothing. Neither is what the bank asked for.

Reads the pre-disbursement conditions first, falling back to what it used
before, so a case decided the old way still behaves as it did.

    python scripts/patch_cc1_conditions_reach_credit_admin.py            # dry run
    python scripts/patch_cc1_conditions_reach_credit_admin.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '''        case_id = CreditAdminManager().create_case_from_application(
            app,
            conditions=(decision.get("conditions") or None),
            authority=str(decision.get("authority", "") or ""),
        )'''

NEW = '''        # ── THE CONDITIONS CREDIT RISK ACTUALLY SET ─────────────────────────
        # The decision writes app["pre_disbursement_conditions"] as
        # [{text, met, kind}]. This read app["decision"]["conditions"], which
        # nothing writes - so credit admin's tick-list arrived empty and the
        # disbursement gate had nothing to hold.
        #
        # The older key is still honoured, so a case decided before this
        # behaves as it did.
        _pre_disb = app.get("pre_disbursement_conditions") or []
        _conds = None
        if _pre_disb:
            _conds = [(c.get("text") if isinstance(c, dict) else str(c))
                      for c in _pre_disb
                      if (c.get("text") if isinstance(c, dict) else str(c))]
        if not _conds:
            _conds = decision.get("conditions") or None
        case_id = CreditAdminManager().create_case_from_application(
            app,
            conditions=_conds,
            authority=str(decision.get("authority", "") or ""),
        )'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "THE CONDITIONS CREDIT RISK ACTUALLY SET" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The case creation matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if 'decision.get("conditions")' not in NEW:
        print("A case decided the old way would lose its conditions.")
        return 1
    if 'pre_disbursement_conditions' not in NEW:
        print("The new key is not read.")
        return 1
    # The endpoint writes them as dicts; the case builder takes text.
    if 'c.get("text")' not in NEW:
        print("A dict would be passed where text is expected.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Credit admin's tick-list is what credit risk set.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cc1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Cases already handed to credit admin keep the")
    print("conditions they were given - this is for the next one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

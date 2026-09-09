#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A return for rework brings the deal back to where it can be submitted.

Returning a case changes the case and never touches the deal. So the deal
stays at whatever stage it had reached - a committee stage, past Documentation
- and submission requires Documentation. The owner attaches every document
asked for and the Submit button stays dead.

    "This deal was returned for rework but after the rework, we aren't able to
     submit the docs."

Same shape as D0644: a deal standing where nothing can move it.

The return now moves the deal back to the stage its product expects a
submission from. The case is unchanged; only the deal follows it.

    python scripts/patch_rk1_a_return_brings_the_deal_back.py            # dry run
    python scripts/patch_rk1_a_return_brings_the_deal_back.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '''    audit_log("LMS_RETURNED_FOR_REWORK", str(user.get("username", "") or ""),
              "%s|%s" % (app_id, reason[:80]))'''

NEW = '''    # ── AND BRING THE DEAL BACK ──────────────────────────────────────────────
    # A return changed the case and left the deal where it stood - usually at a
    # committee stage, past Documentation. Submission requires Documentation,
    # so the owner attached everything asked for and the Submit button stayed
    # dead. Benjamin reported it; D0644 was the same shape.
    #
    # Best effort: a return must never fail because the deal could not be
    # moved. But it is recorded either way.
    try:
        _deal_id = str(app.get("pipeline_deal_id") or "").strip()
        if _deal_id:
            from utils.core import PipelineManager as _PM_rk
            from utils.api import _product_document_config as _pdc, \\
                _stage_flow_for as _flow_rk
            _pm_rk = _PM_rk()
            _d = _pm_rk.get_deal(_deal_id)
            if _d and not str(_d.get("stage", "")).lower().startswith("closed"):
                _docs, _doc_stage = _pdc(_d)
                _back = str(_doc_stage or "").strip()
                if not _back:
                    _fl = [str(x) for x in (_flow_rk(
                        _d.get("product_type") or _d.get("product", "")) or [])]
                    _back = "Documentation" if "Documentation" in _fl else ""
                _cur = str(_d.get("stage", "") or "")
                if _back and _back != _cur:
                    _pm_rk.update_stage(
                        _deal_id, _back,
                        "Returned for rework - brought back so the documents "
                        "can be resubmitted.",
                        str(user.get("username", "") or ""))
    except Exception as _exc:
        audit_log("LMS_RETURN_DEAL_NOT_MOVED",
                  str(user.get("username", "") or ""),
                  "%s|%s" % (app_id, str(_exc)[:70]))

    audit_log("LMS_RETURNED_FOR_REWORK", str(user.get("username", "") or ""),
              "%s|%s" % (app_id, reason[:80]))'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "AND BRING THE DEAL BACK" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The return audit line matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "_product_document_config" not in NEW:
        print("It would guess a stage rather than ask the product.")
        return 1
    if 'startswith("closed")' not in NEW:
        print("A closed deal could be reopened by a return.")
        return 1
    if "LMS_RETURN_DEAL_NOT_MOVED" not in NEW:
        print("A failure would be silent, and the owner would be stuck again.")
        return 1
    # The names it uses must be in this route's scope.
    i = s.index("AND BRING THE DEAL BACK")
    head = s[max(0, i - 3000):i]
    for name in ("app", "app_id", "user"):
        if name not in head:
            print("%r is not in scope where this runs." % name)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A return brings the deal back to where it can be submitted.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_rk1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Deals already stuck from an earlier return are")
    print("freed by:  python scripts/free_stranded_deals.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

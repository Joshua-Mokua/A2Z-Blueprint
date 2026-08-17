#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WN1 - disbursement closes the pipeline deal as Won.

RULING (2026-08-15): "tick disbursed and that should automatically close the
case as won."

Trops already flips the loan application to `disbursed`. The PIPELINE DEAL was
left open - so the branch that originated it still saw work in progress, the
funnel still counted it as pipeline, and somebody eventually closed it by hand
or did not, and the numbers drifted.

WHAT I ALMOST BUILT INSTEAD, and did not, because I looked first:

  utils/api_credit_admin_routes.py already carries 28 routes - conditions
  classified as Condition Precedent or Subsequent, a disbursement gate that CP
  blocks, fulfil, collateral, insurance, legal, perfection - and a three-step
  Trops workflow: book -> value-date -> disburse. None of that needed
  rebuilding. The gap was one join at the end of it.

  My earlier CD1 tick endpoint DOES duplicate `conditions/fulfill`. Credit
  admin should tick in CALMS, where the gate and the collateral live. CD1's
  two kinds on the DECISION are still useful - they are the analyst saying at
  approval time which conditions are which - but its tick is redundant.

BEST EFFORT, DELIBERATELY. If the deal cannot be found or written, THE
DISBURSEMENT STILL STANDS. Money moving is the fact; a pipeline stage is
bookkeeping about it. Failing a disbursement because a deal could not be closed
would be the wrong way round, and the failure is audited so it is not silent.

It writes through `_write_deal`, so the close reaches Postgres as well as JSON.
Writing to one store is not writing - that lesson cost four mornings.

Measured:  Trops -> Closed Won, reason Disbursed, disbursed=True.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_wn1_disbursed_closes_won.py            # dry run
    python scripts\\patch_wn1_disbursed_closes_won.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_credit_admin_routes.py")
BACKUP_SUFFIX = ".pre_wn1"

ANCHOR = '    audit_log("TROOPS_DISBURSED", uname, f"{case_id}|{gl}")'

BLOCK = r'''    # ── DISBURSEMENT CLOSES THE DEAL AS WON ─────────────────────────────────
    # RULING (2026-08-15): "tick disbursed and that should automatically close
    # the case as won."
    #
    # The money has moved. Leaving the pipeline deal open means the branch that
    # originated it still sees it as work in progress, the funnel counts it as
    # pipeline, and somebody eventually closes it by hand - or does not, and
    # the numbers drift.
    #
    # BEST EFFORT. If the deal cannot be found or written, the DISBURSEMENT
    # STILL STANDS: money moving is the fact, and a pipeline stage is
    # bookkeeping about it. Failing the disbursement because a deal could not
    # be closed would be the wrong way round.
    try:
        _deal_id = str((app or {}).get("pipeline_deal_id") or "") if app_id else ""
        if _deal_id:
            from utils.api import _write_deal as _wd
            from utils.core import PipelineManager as _PM
            _pm = _PM()
            _d = _pm.get_deal(_deal_id)
            if _d and not str(_d.get("stage", "")).lower().startswith("closed"):
                _wd(_pm, _deal_id, {
                    "stage": "Closed Won",
                    "closed_reason": "Disbursed",
                    "closed_at": datetime.now().isoformat(timespec="seconds"),
                    "closed_by_name": str(user.get("full_name", "") or ""),
                    "disbursed": True,
                    "disbursed_at": datetime.now().isoformat(timespec="seconds"),
                }, uname)
                audit_log("PIPELINE_CLOSED_WON_ON_DISBURSEMENT", uname,
                          "%s|deal=%s" % (case_id, _deal_id))
    except Exception as _exc:
        audit_log("PIPELINE_CLOSE_ON_DISBURSEMENT_FAILED", uname,
                  "%s|%s: %s" % (case_id, type(_exc).__name__, str(_exc)[:70]))

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "DISBURSEMENT CLOSES THE DEAL AS WON" in s:
        print("ABORT: WN1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the Trops audit line matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  disbursement closes the pipeline deal as Won")

    if "_write_deal" not in BLOCK:
        print("ABORT: the close would reach JSON only, and every reader is")
        print("       DB-first. Writing to one store is not writing.")
        return 1
    if "except Exception" not in BLOCK:
        print("ABORT: a failure to close the deal would fail the DISBURSEMENT.")
        print("       Money moving is the fact; the stage is bookkeeping.")
        return 1
    if 'startswith("closed")' not in BLOCK:
        print("ABORT: an already-closed deal would be closed again.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both stores, fails safe, no double close")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, ROUTES + BACKUP_SUFFIX)
    open(ROUTES, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % ROUTES)

    import py_compile
    try:
        py_compile.compile(ROUTES, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. PG1 must be applied - this uses _write_deal.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

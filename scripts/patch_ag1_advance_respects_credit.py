#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AG1 - the owner cannot walk a deal into credit by advancing stages.

FROM THE BANK (2026-09-04), from one deal's own audit trail:

    16:09  Returned for rework           the credit analyst asked for documents
    12:08  Consumer Credit Analysis -> Documentation          by the RM
    12:21  Documentation -> Branch Credit Committee Review    by the RM
    12:21  Branch Credit Committee Review -> Department Credit Analysis
    15:08  Department Credit Analysis -> Credit Analysis      by the RM

THIRTY-TWO SECONDS FOR THREE STAGES, and the case arrived at Credit Analysis
without a committee sitting, without an analyst being assigned, and without
anybody submitting it.

THE ADVANCE ENDPOINT CHECKS CASCADE SCOPE AND NOTHING ELSE. It does not consult
_deal_locked, it does not consult can_advance_stage, and it does not ask
whether the stage being entered is one an originator should be able to reach.

ENTERING CREDIT IS A SUBMISSION, NOT A STAGE CHANGE. submit-to-credit exists
for it: it checks the document checklist, creates the credit application,
records who submitted it, and advances the stage itself. Walking the same
distance by hand skips every one of those.

WHAT THIS CHANGES: an advance may not move a deal INTO a credit-side stage.

    Initiation -> Documentation            allowed, as now
    Documentation -> Branch Credit Cttee   REFUSED - submit to credit instead
    Credit Analysis -> Credit Admin        REFUSED for an originator; the
                                           credit workflow moves it
    anything -> Closed Won / Closed Lost   allowed, as now

WHO IS NOT AFFECTED. Admins are unchanged. The credit workflow's own automatic
advances do not come through this endpoint - submit-to-credit advances the deal
itself, and committee and analyst actions move it from their own endpoints.

WHY REFUSE RATHER THAN WARN. A deal at Credit Analysis that no analyst has been
assigned is invisible to the people who should be working it, and shows in the
funnel as progress that has not happened. Reporting it after the fact does not
undo either.

Usage (from project root, .venv active):
    python scripts\patch_ag1_advance_respects_credit.py            # dry run
    python scripts\patch_ag1_advance_respects_credit.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

ANCHOR = '''    from utils.api_pipeline_scope import get_visible_staff_codes'''

BLOCK = '''    # ── ENTERING CREDIT IS A SUBMISSION, NOT A STAGE CHANGE ─────────────────
    # RULING (2026-09-04), from one deal's audit trail: an RM walked a returned
    # case from Documentation to Credit Analysis in thirty-two seconds - no
    # committee sat, no analyst was assigned, nobody submitted it.
    #
    # submit-to-credit exists for this: it checks the document checklist,
    # creates the credit application, records who submitted, and advances the
    # stage itself. Walking the same distance by hand skips all of it.
    #
    # An admin is unaffected, and the credit workflow's own advances do not
    # come through this endpoint.
    _CREDIT_SIDE = (
        "branch credit committee", "department credit", "credit analysis",
        "credit administration", "credit administarion", "trops",
        "management credit committee", "board credit committee",
        "legal - security perfection", "offer letter", "disbursement",
    )

    def _is_credit_side(_s):
        _t = str(_s or "").strip().lower()
        return bool(_t) and any(_w in _t for _w in _CREDIT_SIDE)

'''

GUARD_ANCHOR = '''        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")'''

GUARD = '''        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    # Refuse to ENTER a credit-side stage by hand. Leaving one is not blocked -
    # a case can still be closed or returned from where it stands.
    _target = str(getattr(payload, "stage", "") or getattr(payload, "to_stage", "")
                  or "").strip()
    _from = str(deal.get("stage", "") or "").strip()
    # INTO a credit stage FROM ANYWHERE - not only from outside. The audit
    # trail that prompted this shows the last hop as Department Credit Analysis
    # -> Credit Analysis, also by the RM: blocking only the way in would have
    # stopped three of the four moves and left the one that mattered most.
    #
    # A CLOSING STAGE IS ALWAYS ALLOWED. A case must be closable from wherever
    # it stands, including from inside credit.
    _closing = _target.strip().lower().startswith("closed")
    if (_target and _is_credit_side(_target) and not _closing
            and not user.get("is_admin")):
        _audit("API_PIPELINE_ADVANCE_INTO_CREDIT_REFUSED", user,
               f"deal_id={deal_id} from={_from!r} to={_target!r}")
        raise HTTPException(
            status_code=400,
            detail=("A deal enters credit by being submitted, not by changing "
                    "its stage. Use Submit to Credit - it checks the documents, "
                    "opens the credit case and moves the stage for you."))'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "ENTERING CREDIT IS A SUBMISSION" in s:
        print("ABORT: AG1 looks applied.")
        return 1

    i = s.find('@app.post("/api/pipeline/deals/{deal_id}/advance"')
    if i < 0:
        print("ABORT: the advance endpoint is not in this file.")
        return 1
    j = s.index("\n@app.", i + 10)
    body = s[i:j]
    if body.count(ANCHOR) != 1 or body.count(GUARD_ANCHOR) != 1:
        print("ABORT: anchors matched %d / %d times inside the endpoint."
              % (body.count(ANCHOR), body.count(GUARD_ANCHOR)))
        return 1

    new_body = body.replace(ANCHOR, BLOCK + ANCHOR, 1)
    new_body = new_body.replace(GUARD_ANCHOR, GUARD, 1)
    s = s[:i] + new_body + s[j:]
    print("  ok  an advance may not enter a credit stage")

    if "_closing" not in GUARD:
        print("ABORT: a deal in credit could not be closed. It must be")
        print("       closable from wherever it stands.")
        return 1
    if 'user.get("is_admin")' not in GUARD:
        print("ABORT: admins would be blocked too.")
        return 1
    if "_audit(" not in GUARD:
        print("ABORT: a refusal must be recorded - somebody tried, and that is")
        print("       worth knowing.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: leaving credit still allowed, admin kept, audited")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ag1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Deals ALREADY walked into credit stay where they")
    print("are - this stops the next one. Those need moving back by hand, and")
    print("the audit trail shows which they are.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

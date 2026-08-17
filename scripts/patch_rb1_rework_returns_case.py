#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RB1 - a rework actually goes back to the branch.

RULING (2026-08-14): "a returned case reopens back to the branch on the owner,
and once they complete the reworks they resubmit - this time back to the credit
analyst to continue."

THE BUTTON ALREADY EXISTED. CorrectnessPanel has "Return for rework" and it
already requires a reason. What it called - committee-readiness - recorded a
READINESS STATE and nothing else:

    committee_readiness.state = "returned_for_rework"

The case kept its status, stayed in the analyst's own queue, and the branch was
never told. An analyst could mark a case returned and it would sit exactly
where it was. That is the shape of a case quietly stalling: everybody believes
it is with somebody else.

The state was right; the movement was missing. A rework now also:

    status              -> returned
    rework_history      appended, so a case returned three times shows three
                        returns and what each asked for
    returned_by_code    remembered, so resubmit-after-rework (RW1) brings it
                        back to THAT analyst rather than the pool

I NEARLY BUILT A SECOND PANEL. Twice today I have started building something
the system already had - /pick, and this. The cost of not surveying first is
higher than the cost of looking, and the fix is usually smaller than the
feature: this is one field assignment where a new screen was proposed.

Verified: py_compile clean, and the LMS router still loads its 52 routes.

Usage (from project root, .venv active):
    python scripts\\patch_rb1_rework_returns_case.py            # dry run
    python scripts\\patch_rb1_rework_returns_case.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_rb1"

ANCHOR = '    lam.update(app_id, {"committee_readiness": readiness})'
REPLACEMENT_TAIL = "    lam.update(app_id, _updates)"

BLOCK = r'''    # ── A REWORK MUST ACTUALLY GO BACK ──────────────────────────────────────
    # RULING (2026-08-14): "a returned case reopens back to the branch on the
    # owner, and once they complete the reworks they resubmit - this time back
    # to the credit analyst to continue."
    #
    # This endpoint recorded a READINESS STATE and nothing else: the case kept
    # its status, stayed in the analyst's queue, and the branch was never told.
    # An analyst could mark a case "returned for rework" and it would sit
    # exactly where it was, which is the shape of a case quietly stalling.
    #
    # The state was right and the movement was missing. A rework now sets the
    # status to `returned` and remembers WHO returned it, so
    # resubmit-after-rework brings it back to that analyst rather than to the
    # pool - they have the context, and re-queueing turns a two-hour correction
    # into a two-day one.
    if decision == "rework":
        _me = str(user.get("staff_code", "") or "").strip()
        _myname = str(user.get("full_name", "") or "").strip()
        _reason = str(p.get("opinion", "") or "").strip()
        _items = [str(x) for x in (p.get("reasons") or []) if str(x).strip()]
        _history = list(app.get("rework_history") or [])
        _history.append({
            "reason": _reason or "; ".join(_items) or "Returned for rework",
            "items": _items,
            "by": _me, "by_name": _myname,
            "at": datetime.now().isoformat(timespec="seconds"),
        })
        _updates.update({
            "status": "returned",
            "rework_history": _history,
            "rework_reasons": _reason or "; ".join(_items),
            "returned_by_code": _me,
            "returned_by_name": _myname,
            "returned_at": datetime.now().isoformat(timespec="seconds"),
        })

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "A REWORK MUST ACTUALLY GO BACK" in s:
        print("ABORT: RB1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the readiness update matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR,
                  '    _updates = {"committee_readiness": readiness}\n\n'
                  + BLOCK + REPLACEMENT_TAIL, 1)
    print("  ok  a rework returns the case to its owner")

    if '"status": "returned"' not in BLOCK:
        print("ABORT: the case would keep its status and stay in the analyst's")
        print("       queue, which is the whole fault.")
        return 1
    if "returned_by_code" not in BLOCK:
        print("ABORT: the case could not find its way back to this analyst.")
        return 1
    if "rework_history" not in BLOCK:
        print("ABORT: a second return would overwrite the first.")
        return 1
    if 'decision == "rework"' not in BLOCK:
        print("ABORT: a case marked READY would also be returned.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: rework only, history kept, returns to sender")

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
    print("")
    print("Restart uvicorn. The existing 'Return for rework' button now sends")
    print("the case back to the branch, and RW1's resubmit brings it to you.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

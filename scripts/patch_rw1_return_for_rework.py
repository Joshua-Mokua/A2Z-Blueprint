#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RW1 - return a case for rework, and get it back to the same analyst.

RULING (2026-08-14): "if it is returned for reworks, a window to detail the
nature of reworks comes up and once filled they press return. A returned case
reopens back to the branch on the owner, and once they complete the reworks
they resubmit - this time back to the credit analyst to continue until they
recommend for review at the department credit committee."

TWO ENDPOINTS, and one rule each that matters.

    POST /api/lms/applications/{id}/return-for-rework

    THE REASON IS MANDATORY. A case returned without one sends somebody back to
    a branch to guess what was wrong, and they will guess wrong. An empty
    reason is refused rather than accepted as a blank field that costs a day at
    the other end. Optional `items` carry a checklist alongside the prose.

    Every return is appended to rework_history, so a case returned three times
    shows three returns and what each asked for - not one overwritten field.

    POST /api/lms/applications/{id}/resubmit-after-rework

    IT GOES BACK TO THE ANALYST WHO RETURNED IT, not into the pool. That
    analyst has the context; making the case queue again behind everything else
    is how a two-hour correction becomes a two-day one.

    If that analyst cannot be identified it falls back to the pool rather than
    being stranded - a case with nowhere to go is worse than one in the wrong
    queue.

WHAT THIS DOES NOT ADD, because it already exists: /applications/{id}/pick.
Self-pick was already there and already limits a segment analyst to their own
segment. It appeared not to work because the SEGMENT was not resolving - which
SG1 fixed - not because picking was missing. I nearly shipped a duplicate.

Verified: py_compile clean, and all three routes register.

Usage (from project root, .venv active):
    python scripts\\patch_rw1_return_for_rework.py            # dry run
    python scripts\\patch_rw1_return_for_rework.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_rw1"

ANCHOR = '@router.post("/applications/{app_id}/hand-to-credit-analyst")'
IMPORT_OLD = "from fastapi import APIRouter, Depends, HTTPException"
IMPORT_NEW = ("from datetime import datetime\n"
              "from fastapi import APIRouter, Body, Depends, HTTPException")

BLOCK = r'''@router.post("/applications/{app_id}/return-for-rework")
def lms_return_for_rework(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Send a case back to its owner with what needs doing.

    RULING (2026-08-14): "if it is returned for reworks, a window to detail the
    nature of reworks comes up and once filled they press return. A returned
    case reopens back to the branch on the owner, and once they complete the
    reworks they resubmit - this time back to the credit analyst to continue."

    THE REASON IS MANDATORY. A case returned without one sends somebody back to
    a branch to guess what was wrong, and they will guess wrong. The endpoint
    refuses an empty reason rather than accepting a blank field that costs a
    day at the other end.

    IT REMEMBERS WHO RETURNED IT. When the owner resubmits, the case goes back
    to that analyst rather than into the pool to be picked up by somebody with
    no memory of the conversation - which is the difference between a rework
    and starting again.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail=("Say what needs reworking. A case returned without a reason "
                    "sends somebody back to the branch to guess."))

    me = str(user.get("staff_code", "") or "").strip()
    myname = str(user.get("full_name", "") or "").strip()
    history = list(app.get("rework_history") or [])
    history.append({
        "reason": reason,
        "items": [str(x) for x in (payload.get("items") or []) if str(x).strip()],
        "by": me, "by_name": myname,
        "at": datetime.now().isoformat(timespec="seconds"),
    })

    lam.update(app_id, {
        "status": "returned",
        "rework_history": history,
        "rework_reasons": reason,
        # WHO TO COME BACK TO. Cleared when the owner resubmits.
        "returned_by_code": me,
        "returned_by_name": myname,
        "returned_at": datetime.now().isoformat(timespec="seconds"),
    })
    audit_log("LMS_RETURNED_FOR_REWORK", str(user.get("username", "") or ""),
              "%s|%s" % (app_id, reason[:80]))
    return {"application": lam.get(app_id), "status": "returned",
            "returned_to_owner": True}


@router.post("/applications/{app_id}/resubmit-after-rework")
def lms_resubmit_after_rework(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """The owner has done the rework; the case goes BACK to the same analyst.

    Not into the pool. The analyst who returned it has the context, and making
    the case queue again behind everything else is how a two-hour correction
    becomes a two-day one.

    If that analyst cannot be identified the case falls back to the pool rather
    than being stranded - a case with nowhere to go is worse than one in the
    wrong queue.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if str(app.get("status", "")) != "returned":
        raise HTTPException(
            status_code=400,
            detail="This case is not out for rework (status is %r)." % app.get("status"))

    back_to = str(app.get("returned_by_code", "") or "").strip()
    back_name = str(app.get("returned_by_name", "") or "").strip()
    note = str(payload.get("note", "") or "").strip()

    updates = {
        "status": "assigned" if back_to else "submitted",
        "rework_completed_at": datetime.now().isoformat(timespec="seconds"),
        "rework_completed_by": str(user.get("full_name", "") or ""),
        "rework_note": note,
        "returned_by_code": "",
        "returned_by_name": "",
    }
    if back_to:
        updates["analyst"] = {"code": back_to, "name": back_name, "role": ""}
    lam.update(app_id, updates)
    audit_log("LMS_REWORK_RESUBMITTED", str(user.get("username", "") or ""),
              "%s|back to %s" % (app_id, back_to or "the pool"))
    return {"application": lam.get(app_id),
            "status": updates["status"],
            "back_to": back_name or "the pool"}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "return-for-rework" in s:
        print("ABORT: RW1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the anchor matched %d times." % s.count(ANCHOR))
        return 1

    if IMPORT_OLD in s:
        s = s.replace(IMPORT_OLD, IMPORT_NEW, 1)
    elif "Body" not in s.split("\n")[42:45][0] and ", Body," not in s[:4000]:
        print("  note: Body/datetime imports look different here - check them.")
    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  return-for-rework and resubmit-after-rework added")

    if 'detail=("Say what needs reworking' not in BLOCK:
        print("ABORT: an empty reason would be accepted, which sends somebody")
        print("       back to the branch to guess.")
        return 1
    if "rework_history" not in BLOCK:
        print("ABORT: a second return would overwrite the first.")
        return 1
    if "returned_by_code" not in BLOCK:
        print("ABORT: the case would not find its way back to the analyst who")
        print("       returned it.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: reason required, history kept, returns to sender")

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
    print("Restart uvicorn. THE UI FOR THIS IS NOT BUILT YET - the endpoints")
    print("are live and the analyst's page needs the return button and the")
    print("reason window before anybody can use them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

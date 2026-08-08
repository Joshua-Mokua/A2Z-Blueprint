#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
E2 - exception endpoints: make E1 reachable.

E1 gave a missed day the ability to carry a reason and, when that reason
excuses it, to stop carrying a target. E2 is how a manager records one.

ADDS
  GET  /api/branch-log/exception-reasons
       The taxonomy from config, each entry carrying excuses_target so the UI
       can tell a manager, BEFORE they commit, whether the reason they picked
       will remove the day's target.

  POST /api/branch-log/exceptions        { staff_code, date, reason, note }
       Permission is the SAME as validating that person's log - the branch
       triad inside a branch, the line manager at Head Office - because
       excusing a day changes their variance, which is a validation-weight
       decision, not an administrative one.

       Refuses a non-working day: excusing a Sunday is meaningless, and
       allowing it would let a manager paper over days that never carried a
       target anyway.

       Refuses a reason that still charges the target when no note is given
       (enforced in E1's store) - a deficit that will be acted upon must carry
       an explanation the person can answer.

  POST /api/branch-log/exceptions/clear  { staff_code, date }
       The day reverts to its normal target.

ALSO: /validation-queue rows now carry exception / exception_note / excused, so
a manager can see at a glance that a blank row is EXCUSED rather than neglected.
An excused row shows target 0 and should not be chased.

VERIFIED the exception is scoped to one person and one day - the failure that
would matter most here is one person's leave excusing everybody:

    KE111 on leave 2026-08-05  -> target 0.0
    KE222 same day             -> target 25.0
    KE111 the following day    -> target 25.0

NOT in this batch: submit-on-behalf (recording actual figures FOR someone).
Recording the reason is the urgent half - "Refused" and "On leave" are what
change the arithmetic and what a person needs the chance to answer. Entering
numbers on their behalf is E2b and needs a date-explicit write path, since
BranchLogManager.submit() hardcodes date.today().

Usage (from project root, .venv active):
    python scripts\\patch_e2_exception_endpoints.py            # dry run
    python scripts\\patch_e2_exception_endpoints.py --apply    # write + .pre_e2 backup
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_e2"

API_ANCHOR = '@router.get("/validation-queue")'

ROW_OLD = '''            base.update({"log_id": "", "status": "missing", "validated": False,
                         "auto_submitted": False, "index": 0.0,
                         "target": _target_for({"log_date": iso}),
                         "remarks": "", "manager_note": "", "can_act": False})'''

ENDPOINTS_NEW = r'''@router.get("/exception-reasons")
def branch_log_exception_reasons(user: dict = Depends(get_current_user)):
    """The exception taxonomy for the UI, straight from config.

    Each entry carries excuses_target so the client can warn a manager that a
    reason will (or will not) remove the day's target before they commit to it.
    """
    from utils.branch_log_exceptions import reasons
    return {"reasons": reasons()}


@router.post("/exceptions")
def branch_log_set_exception(payload: dict = Body(default_factory=dict),
                             user: dict = Depends(get_current_user)):
    """Record WHY a staff member has no log for a day.

    Permission is the same as validating that person's log — the branch triad
    inside a branch, the line manager at Head Office — because excusing a day
    changes their variance, which is a validation-weight decision.

    payload: { staff_code, date, reason, note }
    """
    from datetime import date as _date
    me = _identity(user)
    staff_code = str(payload.get("staff_code", "") or "").strip()
    day = str(payload.get("date") or _date.today())[:10]
    reason = str(payload.get("reason", "") or "").strip()
    note = str(payload.get("note", "") or "")
    if not staff_code:
        raise HTTPException(status_code=400, detail="staff_code is required")

    if not _is_admin(user):
        try:
            from utils.org_validator import can_validate_daily_log
            allowed = can_validate_daily_log(me.get("staff_code", ""), staff_code)
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="You are not a permitted validator for this staff member.")

    # A working day only: excusing a rest day is meaningless, and allowing it
    # would let a manager paper over days that never carried a target anyway.
    try:
        from utils import workcal as _wc
        if not _wc.is_working_day(day):
            raise HTTPException(
                status_code=400,
                detail="That date is not a working day — it already carries no target.")
    except HTTPException:
        raise
    except Exception:
        pass

    from utils.branch_log_exceptions import set_exception
    try:
        rec = set_exception(staff_code, day, reason, note,
                            me.get("staff_code", ""), me.get("staff_name", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    audit_log("BRANCH_LOG_EXCEPTION", str(user.get("username", "") or ""),
              detail=f"staff={staff_code} date={day} reason={reason} "
                     f"excuses={rec.get('excuses_target')}")
    return {"exception": rec}


@router.post("/exceptions/clear")
def branch_log_clear_exception(payload: dict = Body(default_factory=dict),
                               user: dict = Depends(get_current_user)):
    """Remove an exception — the day reverts to carrying its normal target."""
    from datetime import date as _date
    me = _identity(user)
    staff_code = str(payload.get("staff_code", "") or "").strip()
    day = str(payload.get("date") or _date.today())[:10]
    if not staff_code:
        raise HTTPException(status_code=400, detail="staff_code is required")
    if not _is_admin(user):
        try:
            from utils.org_validator import can_validate_daily_log
            allowed = can_validate_daily_log(me.get("staff_code", ""), staff_code)
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(status_code=403,
                                detail="You are not a permitted validator for this staff member.")
    from utils.branch_log_exceptions import clear_exception
    removed = clear_exception(staff_code, day)
    audit_log("BRANCH_LOG_EXCEPTION_CLEAR", str(user.get("username", "") or ""),
              detail=f"staff={staff_code} date={day} removed={removed}")
    return {"removed": removed}


'''

ROW_NEW = r'''            # E2: a missing day may carry an exception. An EXCUSED one has no
            # target, so it must not read as a deficit the manager should chase.
            try:
                from utils.branch_log_exceptions import exception_for
                exc = exception_for(code, iso) or {}
            except Exception:
                exc = {}
            base.update({"log_id": "", "status": "missing", "validated": False,
                         "auto_submitted": False, "index": 0.0,
                         "target": _target_for({"log_date": iso,
                                                "staff_code": code}),
                         "remarks": "", "manager_note": "", "can_act": False,
                         "exception": exc.get("reason", ""),
                         "exception_note": exc.get("note", ""),
                         "excused": bool(exc.get("excuses_target"))})'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    api = open(API, encoding="utf-8").read()

    if "/exception-reasons" in api:
        print("ABORT: exception endpoints already present - E2 looks applied.")
        return 1
    if "branch_log_exceptions" not in open(
            os.path.join("utils", "branch_log_analytics.py"), encoding="utf-8").read():
        print("ABORT: apply patch_e1_exceptions.py first.")
        return 1
    if api.count(API_ANCHOR) != 1:
        print("ABORT: queue anchor matched %d times." % api.count(API_ANCHOR))
        return 1
    if api.count(ROW_OLD) != 1:
        print("ABORT: missing-row block matched %d times." % api.count(ROW_OLD))
        return 1

    api = api.replace(API_ANCHOR, ENDPOINTS_NEW + API_ANCHOR, 1)
    print("  ok  GET /exception-reasons, POST /exceptions, POST /exceptions/clear")

    api = api.replace(ROW_OLD, ROW_NEW, 1)
    print("  ok  queue rows carry exception / excused")

    for route in ('@router.get("/exception-reasons")',
                  '@router.post("/exceptions")',
                  '@router.post("/exceptions/clear")'):
        if api.count(route) != 1:
            print("ABORT: post-check - %s appears %d times." % (route, api.count(route)))
            return 1
    if api.count('@router.get("/validation-queue")') != 1:
        print("ABORT: post-check - validation-queue route count changed.")
        return 1
    if "can_validate_daily_log" not in api:
        print("ABORT: post-check - permission check missing.")
        return 1
    print("  ok  post-checks: three new routes, queue intact, permission wired")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRestart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AC1 - the owner can accept a decline, and the case closes as Lost.

RULING (2026-08-15): "it should go back to the owner who is to click on appeal
or accept the decision - if they accept it closes as lost."

The APPEAL half already existed - /applications/{id}/appeal, requiring a
declined status and a reason. This is the other half. Without it a declined
case had one exit and no other: appeal, or sit there. Cases that sit are how a
pipeline stops meaning anything.

THE OWNER DECIDES, NOT CREDIT. A decline is credit's answer; whether to contest
it belongs to the person who raised the case. So anybody who is not the owner
or their manager is refused - accepting on somebody else's behalf closes their
deal for them.

    not the owner        403
    not declined         400, naming the status it is in
    an appeal pending    400 - it cannot be accepted until that is answered

IT CLOSES THE PIPELINE DEAL, through _write_deal so the close reaches Postgres.
Best effort and audited if it fails: the acceptance stands either way, because
the decision is the fact and the stage is bookkeeping about it.

Verified: py_compile clean, and all four guards measured.

Usage (from project root, .venv active):
    python scripts\\patch_ac1_accept_decline.py            # dry run
    python scripts\\patch_ac1_accept_decline.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_ac1"

ANCHOR = '@router.post("/applications/{app_id}/appeal")'

BLOCK = r'''@router.post("/applications/{app_id}/accept-decline")
def lms_accept_decline(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """The owner accepts a decline, and the case closes as Lost.

    RULING (2026-08-15): "it should go back to the owner who is to click on
    appeal or accept the decision - if they accept it closes as lost."

    The appeal half already existed. This is the other half, and without it a
    declined case had one exit and no other: appeal, or sit there. Cases that
    sit are how a pipeline stops meaning anything.

    THE OWNER DECIDES, not credit. A decline is credit's answer; whether to
    contest it belongs to the person who raised the case. So this refuses
    anybody who is not the owner or their manager - accepting on somebody
    else's behalf closes their deal for them.

    IT CLOSES THE PIPELINE DEAL TOO. Leaving it open means the branch still
    sees work in progress and the funnel still counts it. Best effort, and
    audited if it fails: the acceptance stands either way, because the decision
    is the fact and the stage is bookkeeping about it.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")

    status = str(app.get("status", "") or "").lower()
    if status != "declined":
        raise HTTPException(
            status_code=400,
            detail="This case is not declined (it is %r), so there is nothing "
                   "to accept." % app.get("status"))
    if bool(app.get("appeal_pending")):
        raise HTTPException(
            status_code=400,
            detail="An appeal is already pending on this case. It cannot be "
                   "accepted until that is answered.")

    me = str(user.get("staff_code", "") or "").strip()
    owner = str(app.get("rm_code", "") or "").strip()
    visible = get_visible_staff_codes(user)
    if not (user.get("is_admin") or me == owner or owner in visible):
        raise HTTPException(
            status_code=403,
            detail="Only the case owner or their manager can accept a decline.")

    note = str(payload.get("note", "") or "").strip()
    lam.update(app_id, {
        "status": "declined_accepted",
        "appeal_window_open": False,
        "awaiting_owner_response": False,
        "decline_accepted_at": datetime.now().isoformat(timespec="seconds"),
        "decline_accepted_by": str(user.get("full_name", "") or ""),
        "decline_accepted_note": note,
    })

    closed = ""
    try:
        deal_id = str(app.get("pipeline_deal_id") or "")
        if deal_id:
            from utils.api import _write_deal as _wd
            from utils.core import PipelineManager as _PM
            pm = _PM()
            d = pm.get_deal(deal_id)
            if d and not str(d.get("stage", "")).lower().startswith("closed"):
                _wd(pm, deal_id, {
                    "stage": "Closed Lost",
                    "closed_reason": str(app.get("decline_reason", "")
                                         or "Credit declined"),
                    "closed_at": datetime.now().isoformat(timespec="seconds"),
                    "closed_by_name": str(user.get("full_name", "") or ""),
                }, str(user.get("username", "") or ""))
                closed = deal_id
    except Exception as exc:
        audit_log("PIPELINE_CLOSE_ON_ACCEPT_FAILED",
                  str(user.get("username", "") or ""),
                  "%s|%s: %s" % (app_id, type(exc).__name__, str(exc)[:70]))

    audit_log("LMS_DECLINE_ACCEPTED", str(user.get("username", "") or ""),
              "%s%s" % (app_id, "|closed %s" % closed if closed else ""))
    return {"application": lam.get(app_id), "status": "declined_accepted",
            "deal_closed": closed or None}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "accept-decline" in s:
        print("ABORT: AC1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the appeal route matched %d times." % s.count(ANCHOR))
        return 1
    if "A DECISION MOVES THE CASE" not in s:
        print("ABORT: DM1 must be applied first - without it a decline never")
        print("       reaches the owner, so there is nothing to accept.")
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  the owner can accept a decline")

    if "Only the case owner" not in BLOCK:
        print("ABORT: anybody could close somebody else's deal.")
        return 1
    if "appeal_pending" not in BLOCK:
        print("ABORT: a case with an appeal pending could be accepted out from")
        print("       under it.")
        return 1
    if "_write_deal" not in BLOCK:
        print("ABORT: the close would reach JSON only.")
        return 1
    if "Closed Lost" not in BLOCK:
        print("ABORT: the deal would not close.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: owner only, appeal respected, both stores")

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

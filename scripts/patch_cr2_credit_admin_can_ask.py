#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Credit admin can ask the branch for something, and the branch is told.

Credit admin has no way back. When they need a signed offer letter, an account
opened, or something confirmed, there is no route to the owner and no way to
ask - so it happens on the phone and the file records nothing.

Adds POST /api/credit-admin/cases/{case_id}/request-from-branch.

    names one person or several
    says what is needed
    emails them
    records it on the case, with what was asked and by whom
    does NOT move the case - credit admin keeps it

A request is not a rejection, and the case does not go backwards. The work
waits with credit admin while somebody fetches a document.

    python scripts/patch_cr2_credit_admin_can_ask.py            # dry run
    python scripts/patch_cr2_credit_admin_can_ask.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_credit_admin_routes.py")

ANCHOR = '@router.post("/cases/{case_id}/conditions/classify",'

BLOCK = '''def _ca_tell(staff_code: str, subject: str, body: str) -> None:
    """Tell somebody credit admin needs something. Never fails the caller."""
    code = str(staff_code or "").strip()
    if not code:
        return
    try:
        from utils.notifications import notify_staff
        if not notify_staff(code, subject, body):
            audit_log("NOTIFY_NOT_SENT", "system",
                      "%s|%s" % (code, subject[:60]))
    except Exception as exc:
        audit_log("NOTIFY_FAILED", "system",
                  "%s|%s" % (code, str(exc)[:60]))


@router.post("/cases/{case_id}/request-from-branch")
def credit_admin_request_from_branch(
    case_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Ask the branch or the owner for something, without moving the case.

    A signed offer letter, an account opened, a detail confirmed. Credit admin
    keeps the case - the work waits here while somebody fetches a document -
    and the request goes on the file with who asked and what for.

    Body: to (a staff code, or a list of them), to_name, what.
    """
    payload = payload or {}
    cam = _cam()
    case = next((c for c in (cam.cases or []) if str(c.get("id")) == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    if not _ca_manager_in_scope(user, case):
        raise HTTPException(status_code=403,
                            detail="This case is not in your scope.")

    what = str(payload.get("what", "") or "").strip()
    if len(what) < 5:
        raise HTTPException(
            status_code=400,
            detail=("Say what you need. A request with no detail sends "
                    "somebody looking for something they cannot identify."))

    raw = payload.get("to")
    to = []
    if isinstance(raw, (list, tuple)):
        to = [{"code": str((x or {}).get("code", x) or "").strip(),
               "name": str((x or {}).get("name", "") or "").strip()}
              for x in raw if str((x or {}).get("code", x) or "").strip()]
    elif str(raw or "").strip():
        to = [{"code": str(raw).strip(),
               "name": str(payload.get("to_name", "") or "").strip()}]
    if not to:
        # Nobody named: the deal's owner, who submitted it.
        owner = str(case.get("rm_code") or case.get("staff_code") or "").strip()
        if owner:
            to = [{"code": owner, "name": str(case.get("rm_name") or "")}]
    if not to:
        raise HTTPException(status_code=400,
                            detail="Name who you are asking.")

    import datetime as _d
    reqs = list(case.get("branch_requests") or [])
    entry = {
        "what": what,
        "to": to,
        "asked_by": str(user.get("staff_code", "") or ""),
        "asked_by_name": str(user.get("full_name", "") or ""),
        "asked_at": _d.datetime.now().isoformat(timespec="seconds"),
        "fulfilled": False,
    }
    reqs.append(entry)
    case["branch_requests"] = reqs
    case["awaiting_branch"] = True
    try:
        cam.save()
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail="Could not record the request: %s" % str(exc)[:60])

    for p in to:
        _ca_tell(p["code"],
                 "Credit admin needs something on %s" % case_id,
                 "<p>%s has asked for this on <b>%s</b>:</p><p>%s</p>"
                 % (entry["asked_by_name"] or "Credit admin", case_id, what))

    audit_log("CREDIT_ADMIN_ASKED_BRANCH",
              str(user.get("username", "") or ""),
              "%s|to=%s|%s" % (case_id, ",".join(p["code"] for p in to), what[:60]))
    return {"case_id": case_id, "asked": [p["code"] for p in to],
            "awaiting_branch": True}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "request-from-branch" in s:
        print("Already applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("Could not find the classify route to sit beside (%d)."
              % s.count(ANCHOR))
        return 1

    for name in ("_cam", "_ca_manager_in_scope", "audit_log",
                 "get_current_user", "Depends", "HTTPException"):
        if name not in s:
            print("%s is not in this module." % name)
            return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)

    if '"awaiting_branch"' not in BLOCK:
        print("Nothing would mark the case as waiting.")
        return 1
    if "len(what) < 5" not in BLOCK:
        print("A request with no detail would be accepted.")
        return 1
    if "notify_staff" not in BLOCK:
        print("Nobody would be told.")
        return 1
    if 'case["stage"]' in BLOCK or "update_stage" in BLOCK:
        print("This would move the case. It must not - credit admin keeps it.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Credit admin can ask one person or several, and they are emailed.")
    print("The case does not move - the work waits with credit admin.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cr2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. The control on the credit admin screen is a")
    print("separate patch; until then the endpoint exists and nothing calls it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

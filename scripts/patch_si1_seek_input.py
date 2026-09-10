#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Credit risk can ask a committee member for input without returning the case.

A hard case sometimes needs a specific committee member's input before credit
risk will decide. Today the only way to involve somebody is to RETURN the case,
which marks it 'returned' - and that says on the file that the analyst's work
was deficient. It was not; a question was asked.

Adds POST /lms/applications/{app_id}/seek-input.

    the case stays where it is and with whoever holds it
    the named person is asked, and it appears on their screen
    their answer is recorded on the journey
    the decision waits, and nothing about the case says it was rejected

    python scripts/patch_si1_seek_input.py            # dry run
    python scripts/patch_si1_seek_input.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

ANCHOR = '@router.post("/applications/{app_id}/escalate-to-chief"'

BLOCK = '''@router.post("/applications/{app_id}/seek-input")
def lms_seek_input(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Ask a named person for input, without returning the case.

    A return says the work was deficient. A question is not that. The case
    stays where it is and with whoever holds it; the person asked sees it, and
    their answer goes on the journey beside everything else.

    Body: to (staff code), to_name, question. A question is required - a
    request with no question is an interruption, not a consultation.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404,
                            detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_view"):
        raise HTTPException(status_code=403,
                            detail="Application is out of scope")

    to_code = str(payload.get("to", "") or "").strip()
    to_name = str(payload.get("to_name", "") or "").strip()
    question = str(payload.get("question", "") or "").strip()
    if not to_code:
        raise HTTPException(status_code=400,
                            detail="Name who you are asking.")
    if len(question) < 10:
        raise HTTPException(
            status_code=400,
            detail=("Say what you are asking them. A request with no question "
                    "is an interruption rather than a consultation."))

    reqs = list(app.get("input_requests") or [])
    reqs.append({
        "asked_by": str(user.get("staff_code", "") or ""),
        "asked_by_name": str(user.get("full_name", "") or ""),
        "to": to_code,
        "to_name": to_name,
        "question": question,
        "asked_at": _dt_now_lms() if "_dt_now_lms" in globals()
                    else datetime.now().isoformat(timespec="seconds"),
        "answered": False,
    })
    # The status is deliberately untouched. The case has not moved and has not
    # been rejected - somebody has been asked a question about it.
    lam.update(app_id, {"input_requests": reqs,
                        "awaiting_input_from": to_code})
    audit_log("LMS_INPUT_SOUGHT", str(user.get("username", "") or ""),
              "%s|from=%s|%s" % (app_id, to_code, question[:60]))
    return {"application_id": app_id, "asked": to_code, "status": app.get("status")}


@router.post("/applications/{app_id}/input-response")
def lms_input_response(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Answer a request for input. Recorded, not decisive.

    The answer goes on the journey. It does not approve or decline anything -
    credit risk still decides, now with the input they asked for.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404,
                            detail=f"Application '{app_id}' not found")
    me = str(user.get("staff_code", "") or "").strip()
    reqs = list(app.get("input_requests") or [])
    mine = [r for r in reqs
            if isinstance(r, dict) and not r.get("answered")
            and str(r.get("to", "")).strip() == me]
    if not mine:
        raise HTTPException(
            status_code=403,
            detail="Nobody has asked you for input on this case.")

    answer = str(payload.get("answer", "") or "").strip()
    if len(answer) < 5:
        raise HTTPException(status_code=400, detail="Say what your view is.")
    stance = str(payload.get("stance", "") or "").strip().lower()

    for r in reqs:
        if r is mine[-1]:
            r["answered"] = True
            r["answer"] = answer
            r["stance"] = stance or "commented"
            r["answered_by_name"] = str(user.get("full_name", "") or "")
            r["answered_at"] = datetime.now().isoformat(timespec="seconds")
            break
    lam.update(app_id, {"input_requests": reqs,
                        "awaiting_input_from": ""})
    audit_log("LMS_INPUT_GIVEN", str(user.get("username", "") or ""),
              "%s|%s|%s" % (app_id, stance or "commented", answer[:60]))
    return {"application_id": app_id, "input": stance or "commented"}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "seek-input" in s:
        print("Already applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("Could not find the escalate route to sit beside (%d)."
              % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)

    if '"status"' in BLOCK.split("lam.update(app_id, {\"input_requests\": reqs,")[1][:120]:
        print("Asking for support would change the status.")
        return 1
    if "len(question) < 10" not in BLOCK:
        print("A request with no question would be accepted.")
        return 1
    if "Nobody has asked you" not in BLOCK:
        print("Anybody could answer on somebody else's behalf.")
        return 1
    for name in ("_lam", "resolve_application_permissions", "audit_log",
                 "datetime", "Body", "Depends"):
        if name not in s.split("@router.post(\"/applications/{app_id}/seek-input\")")[0]:
            print("%s is not available in this module." % name)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Credit risk can ask; the person asked can answer; the status")
    print("does not move and nothing says the case was rejected.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ss1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. The control on the workbench is a separate patch;")
    print("until then the endpoints exist and nothing calls them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

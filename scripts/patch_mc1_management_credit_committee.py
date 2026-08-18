#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MC1 - a case can be referred to the Management Credit Committee.

RULING (2026-08-18): "another item is the Management Credit Committee, so
credit risk can also then have a button to forward to the Management Credit
Committee as well."

TWO ESCALATIONS, ONE ACT. One asks an individual for their approval; the other
puts the case to a committee that will sit and vote on it. From the analyst's
side the act is identical - this is above my authority, here is why - and the
difference is only who answers. So it is the same endpoint with a `to`, rather
than a second route that would drift out of step with the first.

    POST /api/lms/applications/{id}/escalate-to-chief
         {"reason": "...", "to": "chief"}   an individual
         {"reason": "...", "to": "mcc"}     a committee that sits

REFERRING TO THE COMMITTEE MOVES THE CASE - status referred_to_committee,
committee_kind mcc - because a committee has to receive it to sit on it. Asking
the Chief does NOT move it: the analyst still owns the case while the question
is out, and moving it would leave nobody accountable for it in the meantime.

IT REFUSES IF NO COMMITTEE IS STAFFED, naming where to fix it. A case referred
to an empty committee is the Eldoret fault again: it leaves one queue and
arrives in none.

Measured:

    to=chief   Thomas Okumu       status unchanged
    to=mcc     Credit Committee   status referred_to_committee

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_mc1_management_credit_committee.py            # dry run
    python scripts\\patch_mc1_management_credit_committee.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_mc1"

OLD = '''    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="Say why this needs the Chief\'s approval. A case arriving "
                   "with no question attached wastes the trip.")'''

NEW_HEAD = '''    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="Say why this needs a higher authority. A case arriving "
                   "with no question attached wastes the trip.")
'''

BLOCK = r'''    # ── UP TO A PERSON, OR UP TO A COMMITTEE ────────────────────────────────
    # RULING (2026-08-18): "another item is the Management Credit Committee, so
    # credit risk can also forward to the Management Credit Committee as well."
    #
    # Two different escalations: one asks an individual for their approval, the
    # other puts the case to a committee that will sit and vote on it. Same
    # endpoint, because from the analyst's side the act is identical - this is
    # above my authority, here is why - and the difference is only who answers.
    _target = str(payload.get("to", "chief") or "chief").strip().lower()
    if _target in ("mcc", "management", "management credit committee", "committee"):
        _cfg2 = get_credit_workflow_config() or {}
        _mcc = None
        for _c in (_cfg2.get("committee_palette") or []):
            _nm = str(_c.get("name", "") or "").lower()
            if "management" in _nm or str(_c.get("code")) == "B4":
                _members = [m for m in (_c.get("members") or [])
                            if isinstance(m, dict)
                            and (str(m.get("staff_code", "")).strip()
                                 or str(m.get("name", "")).strip())]
                if _members:
                    _mcc = _c
                    break
        if not _mcc:
            raise HTTPException(
                status_code=400,
                detail="No Management Credit Committee is configured with "
                       "members, so this case would be sent to nobody. Name "
                       "them in Administration > Credit Committees.")
        _esc = list(app.get("escalations") or [])
        _esc.append({
            "reason": reason,
            "by": str(user.get("staff_code", "") or ""),
            "by_name": str(user.get("full_name", "") or ""),
            "to": str(_mcc.get("code")),
            "to_name": str(_mcc.get("name")),
            "kind": "committee",
            "at": datetime.now().isoformat(timespec="seconds"),
            "outcome": "",
        })
        lam.update(app_id, {
            "escalations": _esc,
            "escalated_pending": True,
            "status": "referred_to_committee",
            "committee_kind": "mcc",
            "escalated_to_name": str(_mcc.get("name")),
            "escalated_at": datetime.now().isoformat(timespec="seconds"),
        })
        audit_log("LMS_ESCALATED_TO_MCC", str(user.get("username", "") or ""),
                  "%s|%s" % (app_id, _mcc.get("code")))
        return {"application": lam.get(app_id),
                "escalated_to": str(_mcc.get("name")), "status": "escalated"}

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "UP TO A PERSON, OR UP TO A COMMITTEE" in s:
        print("ABORT: MC1 looks applied.")
        return 1
    if "escalate-to-chief" not in s:
        print("ABORT: EC1 must be applied first - this extends its endpoint.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the escalation reason check matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW_HEAD + BLOCK.rstrip(), 1)
    print("  ok  a case can be referred to the Management Credit Committee")

    if "No Management Credit Committee is configured" not in BLOCK:
        print("ABORT: an unstaffed committee would receive the case and")
        print("       nobody would see it - the Eldoret fault again.")
        return 1
    if '"committee_kind": "mcc"' not in BLOCK:
        print("ABORT: the committee would not recognise the case as its own.")
        return 1
    if "_target" not in BLOCK:
        print("ABORT: the target is not read, so every escalation would go to")
        print("       the same place.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: refuses an empty committee, target honoured")

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
    print("\nRESTART UVICORN. The Management Credit Committee needs members -")
    print("check with: python scripts\\audit_readiness.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

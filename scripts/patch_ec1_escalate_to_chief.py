#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
EC1 - a case can be pushed to the Chief Credit Risk.

RULING (2026-08-15): the bank credit analyst may "approve with pre-approval
conditions, pre-disbursement conditions, return for additional documentation or
information, or push to the Chief Credit Risk for their approval as well."

THE CHIEF IS RESOLVED FROM CONFIG, NOT HARDCODED. Today that is Thomas Okumu,
Director Credit Risk Management, who also chairs B4 - and his name appears
nowhere in this code. A bank changes its people more often than its software,
and a name in the source is a name somebody has to find and edit later.
Resolution order:

    credit_workflow.chief_credit_risk    an explicit setting
    the chair of committee B4            where the authority already sits
    a register role matching             director / head of credit risk

IF NONE RESOLVES, THE ESCALATION IS REFUSED and says which of the three to set.
Sending a case to nobody is the Eldoret fault exactly: it leaves one queue and
arrives in none.

A REASON IS REQUIRED. A case arriving on the Chief's desk with no question
attached wastes the trip.

THE CASE DOES NOT CHANGE HANDS. Escalation asks a question of somebody senior;
the analyst still owns it and the answer comes back to them. Moving the case
would leave nobody accountable for it while it was away.

Measured:

    no reason        400
    with a reason    escalated to Thomas Okumu, recorded with who and why,
                     status unchanged

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_ec1_escalate_to_chief.py            # dry run
    python scripts\\patch_ec1_escalate_to_chief.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_ec1"

ANCHOR = '@router.post("/applications/{app_id}/accept-decline")'

BLOCK = r'''@router.post("/applications/{app_id}/escalate-to-chief")
def lms_escalate_to_chief(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Send a case up to the Chief Credit Risk for their approval.

    RULING (2026-08-15): the bank credit analyst may "approve with pre-approval
    conditions, pre-disbursement conditions, return for additional
    documentation or information, or push to the Chief Credit Risk for their
    approval as well."

    THE CHIEF IS A PERSON, RESOLVED FROM CONFIG, NOT A HARDCODED NAME. A bank
    changes its people more often than its software, and a name in the code is
    a name somebody has to find and edit later - so not even this comment names
    the current holder. Resolution order:

        credit_workflow.chief_credit_risk        an explicit setting
        the chair of committee B4                where the authority already sits
        a register role matching director/head of credit risk

    If none resolves, the escalation is REFUSED and says so. Sending a case to
    nobody is the Eldoret fault: it leaves the queue and arrives nowhere.

    THE CASE STAYS WHERE IT IS. Escalation asks a question of somebody senior;
    it does not hand the case over. The analyst still owns it, and the answer
    comes back to them.
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_update"):
        raise HTTPException(status_code=403,
                            detail="You cannot escalate this case.")

    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="Say why this needs the Chief's approval. A case arriving "
                   "with no question attached wastes the trip.")

    # ── WHO IS THE CHIEF ────────────────────────────────────────────────────
    chief = {}
    try:
        cfg = get_credit_workflow_config() or {}
    except Exception:
        cfg = {}
    explicit = cfg.get("chief_credit_risk") or {}
    if isinstance(explicit, dict) and (explicit.get("staff_code") or explicit.get("name")):
        chief = {"code": str(explicit.get("staff_code", "") or ""),
                 "name": str(explicit.get("name", "") or "")}
    if not chief:
        for c in (cfg.get("committee_palette") or []):
            if str(c.get("code")) == "B4" and str(c.get("chaired_by", "") or "").strip():
                chief = {"code": str(c.get("chair_staff_code", "") or ""),
                         "name": str(c.get("chaired_by"))}
                break
    if not chief:
        try:
            from utils.api_pipeline_scope import get_staff_roster
            df = get_staff_roster()
            for _i, r in df.iterrows():
                role = str(r.get("Role") or "").lower()
                if ("credit risk" in role
                        and ("director" in role or "head" in role or "chief" in role)):
                    chief = {"code": str(r.get("Staff Code") or ""),
                             "name": str(r.get("Staff Name") or "")}
                    break
        except Exception:
            pass
    if not chief or not (chief.get("code") or chief.get("name")):
        raise HTTPException(
            status_code=400,
            detail="No Chief Credit Risk is configured, so this case would be "
                   "sent to nobody. Set credit_workflow.chief_credit_risk, or "
                   "name a chair on committee B4.")

    escalations = list(app.get("escalations") or [])
    escalations.append({
        "reason": reason,
        "by": str(user.get("staff_code", "") or ""),
        "by_name": str(user.get("full_name", "") or ""),
        "to": chief.get("code"),
        "to_name": chief.get("name"),
        "at": datetime.now().isoformat(timespec="seconds"),
        "outcome": "",
    })
    lam.update(app_id, {
        "escalations": escalations,
        "escalated_pending": True,
        "escalated_to_code": chief.get("code"),
        "escalated_to_name": chief.get("name"),
        "escalated_at": datetime.now().isoformat(timespec="seconds"),
    })
    audit_log("LMS_ESCALATED_TO_CHIEF", str(user.get("username", "") or ""),
              "%s|to %s" % (app_id, chief.get("name") or chief.get("code")))
    return {"application": lam.get(app_id), "escalated_to": chief.get("name"),
            "status": "escalated"}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "escalate-to-chief" in s:
        print("ABORT: EC1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the accept-decline route matched %d times." % s.count(ANCHOR))
        print("       AC1 must be applied first.")
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  a case can be pushed to the Chief Credit Risk")

    # No person's name may be hardcoded.
    for name in ("Thomas", "Okumu", "KE820"):
        if name in BLOCK:
            print("ABORT: %r is hardcoded. The Chief must be resolved from" % name)
            print("       config, or somebody edits source when a person moves.")
            return 1
    if "chief_credit_risk" not in BLOCK:
        print("ABORT: the explicit config setting is not consulted.")
        return 1
    if "No Chief Credit Risk is configured" not in BLOCK:
        print("ABORT: an unresolved Chief would send the case to nobody, which")
        print("       is the fault that cost two days at Eldoret.")
        return 1
    if "Say why this needs" not in BLOCK:
        print("ABORT: a case could arrive with no question attached.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: no hardcoded name, refuses when unresolved")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())

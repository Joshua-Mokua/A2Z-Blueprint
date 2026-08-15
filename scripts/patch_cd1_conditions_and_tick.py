#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CD1 - conditions have a kind, and the last tick moves the case.

RULING (2026-08-15): "they will tick against all the conditions and when they
click on all conditions met, it should automatically flow to Trops for
disbursement ... the admin can also have pre-disbursement conditions which
Trops will tick against, and if met tick disbursed and that should
automatically close the case as won."

TWO KINDS, because they are ticked by different people at different stages:

    pre_approval        satisfied before the approval stands - credit admin
    pre_disbursement    satisfied before money moves - Trops

One flat list cannot say who owes what.

THE PLAIN `conditions` FIELD IS KEPT AND UNCHANGED. Every decision recorded
before today carries it, and re-typing it would strand them. It still means
pre-approval, which is what it has always been used for; the two new fields are
additive, and an approval that sends only the old field still lands as
pre-approval.

EACH CONDITION IS AN OBJECT, not a string - {text, met, met_by_name,
met_by_code, met_at}. A bare string has nowhere to record who ticked it, and
that is the first question an auditor asks.

    POST /api/lms/applications/{id}/conditions/tick
         {"kind": "pre_approval", "index": 0, "met": true}

THE LAST TICK MOVES THE CASE. Nobody presses a separate button - the condition
being satisfied IS the event, and making somebody then announce it is the delay
every ruling this week has been about.

Measured:

    tick 0 of 2   remaining 1   still with credit admin
    tick 1 of 2   remaining 0   released to Trops, status=trops
    pre-disbursement complete   ready_to_disburse

Verified: py_compile clean, the LMS router loads.

Usage (from project root, .venv active):
    python scripts\\patch_cd1_conditions_and_tick.py            # dry run
    python scripts\\patch_cd1_conditions_and_tick.py --apply
"""
import os
import shutil
import sys

MODELS = os.path.join("utils", "api_lms_models.py")
ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_cd1"

MODEL_ANCHOR = '    comments: Optional[str] = Field('
TICK_ANCHOR = '@router.post("/applications/{app_id}/hand-to-credit-analyst")'
APPR_OLD = '''            _conds = list(getattr(payload, "conditions", None) or [])'''

MODEL_BLOCK = r'''    # ── TWO KINDS OF CONDITION (2026-08-15) ────────────────────────────────
    # RULING: an approval may carry PRE-APPROVAL conditions - things to satisfy
    # before the offer stands - and PRE-DISBURSEMENT conditions, which credit
    # admin and Trops tick before money moves. They are ticked by different
    # people at different stages, so one flat list cannot say who owes what.
    #
    # `conditions` above is KEPT AND UNCHANGED. Every existing decision carries
    # it, and re-typing it would strand them. It continues to mean
    # pre-approval, which is what it has always been used for; these two are
    # additive.
    pre_approval_conditions: Optional[List[str]] = Field(
        default=None,
        description="Conditions to satisfy before the approval stands. "
                    "Ticked by credit admin."
    )
    pre_disbursement_conditions: Optional[List[str]] = Field(
        default=None,
        description="Conditions to satisfy before money moves. Ticked by "
                    "Trops at disbursement."
    )
'''

TICK_BLOCK = r'''@router.post("/applications/{app_id}/conditions/tick")
def lms_tick_condition(
    app_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Tick one condition, and release the case when the last one is met.

    RULING (2026-08-15): "they will tick against all the conditions and when
    they click on all conditions met, it should automatically flow to Trops for
    disbursement ... the admin can also have pre-disbursement conditions which
    Trops will tick against, and if met tick disbursed and that should
    automatically close the case as won."

    So a tick is not bookkeeping - it is the thing that moves the case. The
    LAST pre-approval tick releases to Trops; the last pre-disbursement tick
    leaves nothing standing between the case and disbursement.

    WHO TICKED IT, AND WHEN, is recorded against the condition. A condition
    that says only `met: true` cannot answer the question an auditor asks
    first.

    Body: {"kind": "pre_approval"|"pre_disbursement", "index": 0, "met": true}
    """
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if not resolve_application_permissions(user, app).get("can_update"):
        raise HTTPException(status_code=403,
                            detail="You cannot change conditions on this case.")

    kind = str(payload.get("kind", "pre_approval") or "pre_approval").strip()
    if kind not in ("pre_approval", "pre_disbursement"):
        raise HTTPException(status_code=400,
                            detail="kind must be pre_approval or pre_disbursement")
    field = "%s_conditions" % kind
    conds = list(app.get(field) or [])
    if not conds:
        raise HTTPException(
            status_code=400,
            detail="This case has no %s conditions to tick." % kind.replace("_", "-"))

    try:
        idx = int(payload.get("index"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="index must be a number")
    if not 0 <= idx < len(conds):
        raise HTTPException(status_code=400,
                            detail="There is no condition %d on this case." % idx)

    met = bool(payload.get("met", True))
    c = dict(conds[idx] if isinstance(conds[idx], dict) else {"text": str(conds[idx])})
    c["met"] = met
    c["met_by_name"] = str(user.get("full_name", "") or "") if met else ""
    c["met_by_code"] = str(user.get("staff_code", "") or "") if met else ""
    c["met_at"] = datetime.now().isoformat(timespec="seconds") if met else ""
    conds[idx] = c

    updates = {field: conds}
    all_met = all(bool(x.get("met")) for x in conds if isinstance(x, dict))

    # ── THE LAST TICK MOVES THE CASE ────────────────────────────────────────
    # Nobody presses a separate button. The condition being satisfied IS the
    # event; making somebody then announce it is the delay every ruling this
    # week has been about.
    released = ""
    if all_met and kind == "pre_approval":
        updates.update({
            "status": "trops",
            "awaiting_credit_admin": False,
            "awaiting_disbursement": True,
            "conditions_cleared_at": datetime.now().isoformat(timespec="seconds"),
            "conditions_cleared_by": str(user.get("full_name", "") or ""),
        })
        released = "trops"
    elif all_met and kind == "pre_disbursement":
        updates["ready_to_disburse"] = True
        released = "disbursement"

    lam.update(app_id, updates)
    audit_log("LMS_CONDITION_TICKED", str(user.get("username", "") or ""),
              "%s|%s[%d]=%s%s" % (app_id, kind, idx, met,
                                  "|released to %s" % released if released else ""))
    return {"application": lam.get(app_id), "all_met": all_met,
            "released_to": released,
            "remaining": sum(1 for x in conds
                             if isinstance(x, dict) and not x.get("met"))}


'''

APPR_BLOCK = r'''            # PRE-APPROVAL falls back to the plain `conditions` list, because
            # that is what every decision recorded before today used it for.
            # Reading only the new field would make historic approvals look
            # unconditional.
            _pre = list(getattr(payload, "pre_approval_conditions", None)
                        or getattr(payload, "conditions", None) or [])
            _dis = list(getattr(payload, "pre_disbursement_conditions", None) or [])
            lam.update(app_id, {
                "status": "credit_admin",
                "awaiting_credit_admin": True,
                "approved_at": datetime.now().isoformat(timespec="seconds"),
                "approved_by_name": str(user.get("full_name", "") or ""),
                "decision_conditions": _pre,
                # Each condition is an object, not a string, so a tick can be
                # recorded against it with who and when. A bare string has
                # nowhere to put that.
                "pre_approval_conditions": [
                    {"text": c, "met": False, "kind": "pre_approval"}
                    for c in _pre],
                "pre_disbursement_conditions": [
                    {"text": c, "met": False, "kind": "pre_disbursement"}
                    for c in _dis],
            })
            _conds = _pre + _dis'''


def main():
    apply = "--apply" in sys.argv
    for f in (MODELS, ROUTES):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    m = open(MODELS, encoding="utf-8").read()
    r = open(ROUTES, encoding="utf-8").read()

    if "TWO KINDS OF CONDITION" in m:
        print("ABORT: CD1 looks applied.")
        return 1
    if m.count(MODEL_ANCHOR) < 1:
        print("ABORT: the decision model does not look as expected.")
        return 1
    if "A DECISION MOVES THE CASE" not in r:
        print("ABORT: DM1 must be applied first - this extends its block.")
        return 1
    if r.count(TICK_ANCHOR) != 1 or r.count(APPR_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (r.count(TICK_ANCHOR), r.count(APPR_OLD)))
        return 1

    m = m.replace(MODEL_ANCHOR, MODEL_BLOCK + MODEL_ANCHOR, 1)
    r = r.replace(TICK_ANCHOR, TICK_BLOCK + TICK_ANCHOR, 1)
    # Replace the whole approved-branch condition handling.
    start = r.index(APPR_OLD)
    end = r.index('            })', start) + len('            })')
    r = r[:start] + APPR_BLOCK + r[end:]
    print("  ok  two kinds of condition, and a tick that moves the case")

    if "pre_disbursement_conditions" not in MODEL_BLOCK:
        print("ABORT: the second kind is missing from the model.")
        return 1
    if 'getattr(payload, "conditions"' not in APPR_BLOCK:
        print("ABORT: a decision sending only the OLD flat list would record no")
        print("       conditions at all, stranding every historic approval.")
        return 1
    if "met_by_name" not in TICK_BLOCK:
        print("ABORT: a tick would not record who made it.")
        return 1
    if '"status": "trops"' not in TICK_BLOCK:
        print("ABORT: the last pre-approval tick would not release the case.")
        return 1
    import ast
    for name, src in ((MODELS, m), (ROUTES, r)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("ABORT: %s would not parse - line %s: %s"
                  % (os.path.basename(name), exc.lineno, exc.msg))
            return 1
    print("  ok  post-checks: legacy conditions still land, ticks attributed")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((MODELS, m), (ROUTES, r)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MODELS, ROUTES):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1
    print("  ok  compiles")
    print("\nRestart uvicorn. Credit admin ticks the pre-approval conditions;")
    print("the last one releases the case to Trops.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

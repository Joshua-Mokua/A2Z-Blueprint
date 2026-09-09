#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Let a deal's value be amended, with a reason, recorded on the journey.

A value gets keyed wrong, or a customer's ability to service turns out lower
than they hoped. Both are ordinary. Correcting them by script is not.

This adds POST /api/pipeline/deals/{id}/amend-value.

Who may:
    the deal's owner        while it has not gone to credit
    a manager in scope      at any point
    an admin                at any point

A reason is required. The change lands on the case journey as an Amendment
event, so the deal answers the question later.

    python scripts/patch_am1_amend_deal_value.py            # dry run
    python scripts/patch_am1_amend_deal_value.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

ANCHOR = '@app.post("/api/pipeline/deals/{deal_id}/advance")'

BLOCK = '''@app.post("/api/pipeline/deals/{deal_id}/amend-value", tags=["pipeline"])
def pipeline_deal_amend_value(
    deal_id: str,
    payload: dict = Body(default_factory=dict),
    user: dict = Depends(get_current_user),
):
    """Change a deal's value, with a reason, recorded on its journey.

    Two ordinary things make a value wrong: it was keyed wrong, or the
    customer's ability to service turned out lower than they hoped. Neither
    should need an engineer.

    The owner may amend while the deal has not gone to credit. After that it
    takes a manager, because an analyst has assessed the old figure and
    somebody senior should know it moved.
    """
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_manager_actions import is_manager
    from utils.api_pipeline_mutations import invalidate_pipeline_caches
    from datetime import datetime as _dt

    from utils.core import PipelineManager as _PM_for_amend
    pm = _PM_for_amend()
    deal = pm.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    try:
        new_value = float(payload.get("value"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400,
                            detail="A new value is required, as a number.")
    if new_value <= 0:
        raise HTTPException(status_code=400,
                            detail="A deal value must be more than zero.")

    reason = str(payload.get("reason", "") or "").strip()
    if len(reason) < 5:
        raise HTTPException(
            status_code=400,
            detail=("Say why the value is changing. In six months somebody "
                    "will ask, and the deal should answer."))

    my_code = str(user.get("staff_code", "") or "").strip()
    owner = str(deal.get("staff_code", "") or "").strip()
    is_owner = bool(my_code) and my_code == owner
    in_scope = owner in set(get_visible_staff_codes(user) or [])
    mgr = is_manager(user) and (in_scope or bool(user.get("is_admin")))
    gone_to_credit = bool(str(deal.get("lms_application_id") or "").strip())

    if not (user.get("is_admin") or mgr or (is_owner and not gone_to_credit)):
        _audit("API_DEAL_AMEND_VALUE_FORBIDDEN", user, f"deal_id={deal_id}")
        if is_owner and gone_to_credit:
            raise HTTPException(
                status_code=403,
                detail=("This deal is with credit. An analyst has assessed the "
                        "current figure, so a manager has to make the change."))
        raise HTTPException(status_code=403,
                            detail="This deal is not yours to amend.")

    old = deal.get("amount_kes") or deal.get("deal_value") or 0
    try:
        old_f = float(old or 0)
    except (TypeError, ValueError):
        old_f = 0.0
    if abs(old_f - new_value) < 0.01:
        return {"deal_id": deal_id, "value": new_value, "changed": False}

    for k in ("amount_kes", "deal_value"):
        if k in deal:
            deal[k] = new_value
    if "amount_kes" not in deal and "deal_value" not in deal:
        deal["amount_kes"] = new_value
    deal["value_amended_at"] = _dt.now().isoformat(timespec="seconds")
    deal["value_amended_by"] = str(user.get("username", "") or "")

    # On the journey, in the same shape as a stage change, so it reads in
    # sequence with everything else that happened to this deal.
    try:
        pm.add_activity({
            "deal_id": deal_id,
            "staff_code": deal.get("staff_code", ""),
            "staff_name": deal.get("staff_name", ""),
            "activity_type": "Value amended",
            "note": ("Value: %s -> %s. %s (by %s)"
                     % (format(int(old_f), ","), format(int(new_value), ","),
                        reason, user.get("full_name") or user.get("username"))),
            "outcome": str(int(new_value)),
        })
    except Exception as exc:
        logger.warning("could not write the amendment to the journey for %s: %s",
                       deal_id, exc)

    pm._save_deals()
    _audit("API_DEAL_AMEND_VALUE", user,
           f"deal_id={deal_id}|{old_f:.0f}->{new_value:.0f}|{reason[:80]}")
    try:
        _db_sync_pipeline_deal(deal)
    except Exception as exc:
        logger.warning("amended %s but could not sync to the database: %s",
                       deal_id, exc)
    invalidate_pipeline_caches()
    return {"deal_id": deal_id, "was": old_f, "value": new_value,
            "changed": True, "reason": reason}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "amend-value" in s:
        print("Already applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("The advance route matched %d times." % s.count(ANCHOR))
        return 1
    if "_dt.datetime" not in s and "import datetime as _dt" not in s:
        print("datetime is not imported as _dt in this module.")
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)

    if "len(reason) < 5" not in BLOCK:
        print("A reason is not required.")
        return 1
    if "gone_to_credit" not in BLOCK:
        print("An owner could amend a deal an analyst has already assessed.")
        return 1
    if "_audit(" not in BLOCK:
        print("The change would not be audited.")
        return 1
    if "add_activity" not in BLOCK:
        print("The change would not appear on the case journey.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Endpoint added: owner before credit, manager after, reason required.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_am1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. The UI panel is a separate patch; until then the")
    print("endpoint can be called directly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

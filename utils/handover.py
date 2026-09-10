# -*- coding: utf-8 -*-
"""One return, one notification, for every desk in the credit chain.

WHY THIS EXISTS
---------------
By 2026-09-09 there were three ways to send work back and three ways to tell
somebody about it:

    /return-for-rework          moved the case and the deal
    committee-readiness         wrote a note and moved nothing
    credit-admin branch_requests kept its own list and moved nothing

    notify_staff                the original
    _tell                       added to api_lms_routes
    _ca_tell                    added to api_credit_admin_routes

Every fix to one missed the others. A fortnight of reports - Catherine's
returns not returning, owners unable to resubmit, D0644 stranded - came from
that split. The same shape had already cost a week on stage buckets, which
were also defined in three places.

So: one function that sends work back, one that tells somebody. Every desk
calls the same code. A fix lands everywhere or nowhere.

WHAT A RETURN IS
----------------
Somebody needs something done before the work can continue. It is not a
rejection and it does not undo what has been decided.

    the case remembers where it froze, and goes back THERE
    one person or several are named, and each is told
    who asked, what for, and when are on the file
    the case is assigned to the first person named, so it lands on a screen

WHAT IT IS NOT
--------------
A decision. Nothing here approves, declines or advances anything.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Iterable, List, Optional


# ── TELLING SOMEBODY ─────────────────────────────────────────────────────────

def notify(staff_code: str, subject: str, body_html: str = "",
           context: str = "") -> bool:
    """Tell one person something happened. Never raises.

    A handover nobody is told about waits until somebody opens a screen. But a
    notification that silently fails is worse than none, because everybody
    assumes it went - so a failure is written to the audit trail.
    """
    code = str(staff_code or "").strip()
    if not code:
        return False
    try:
        from utils.notifications import notify_staff
        sent = bool(notify_staff(code, subject, body_html))
    except Exception as exc:                                # pragma: no cover
        _audit("NOTIFY_FAILED", "%s|%s|%s" % (code, subject[:40], str(exc)[:50]))
        return False
    if not sent:
        _audit("NOTIFY_NOT_SENT", "%s|%s|%s" % (code, subject[:50], context[:40]))
    return sent


def notify_many(people: Iterable[Dict[str, str]], subject: str,
                body_html: str = "", context: str = "") -> int:
    """Tell several people. Returns how many were actually reached."""
    n = 0
    for p in (people or []):
        code = str((p or {}).get("code", "") or "").strip()
        if code and notify(code, subject, body_html, context):
            n += 1
    return n


def _audit(action: str, detail: str) -> None:
    try:
        from utils.core_audit import audit_log
        audit_log(action, "system", detail)
    except Exception:                                       # pragma: no cover
        pass


# ── WHO IS BEING ASKED ───────────────────────────────────────────────────────

def people_from(raw: Any, fallback_code: str = "",
                fallback_name: str = "") -> List[Dict[str, str]]:
    """Normalise however the caller named people into one shape.

    Accepts a staff code, a dict, or a list of either. Falls back to one named
    person - usually the deal's owner - when nothing is given, because a
    request addressed to nobody reaches nobody.
    """
    out: List[Dict[str, str]] = []

    def add(code: Any, name: Any = "") -> None:
        c = str(code or "").strip()
        if c and not any(p["code"] == c for p in out):
            out.append({"code": c, "name": str(name or "").strip()})

    if isinstance(raw, (list, tuple)):
        for x in raw:
            if isinstance(x, dict):
                add(x.get("code") or x.get("staff_code"), x.get("name"))
            else:
                add(x)
    elif isinstance(raw, dict):
        add(raw.get("code") or raw.get("staff_code"), raw.get("name"))
    elif raw:
        add(raw)

    if not out:
        add(fallback_code, fallback_name)
    return out


# ── SENDING WORK BACK ────────────────────────────────────────────────────────

REWORK_STAGE = "Rework"


def send_back(app_id: str, *, to: Any, reason: str, user: Dict[str, Any],
              asked_from: str, reasons: Optional[List[str]] = None,
              set_status: bool = True) -> Dict[str, Any]:
    """Send a case back to one person or several. The single return path.

    Parameters
    ----------
    app_id      the credit case
    to          a staff code, a dict, or a list of either. Empty means the
                deal's owner.
    reason      what needs doing. Required - a return with no reason sends
                somebody looking for something they cannot identify.
    user        who is asking
    asked_from  the desk asking: 'analyst', 'credit risk', 'credit admin',
                'trops'. Recorded, and used in what the person is told.
    set_status  True marks the case 'returned' AND freezes the deal at Rework -
                the work stops until it comes back. False records the request
                and tells the person, and moves NOTHING: the desk keeps the
                case and the deal stays where it is.

                Found in simulation: with False, the deal was still being moved
                to Rework while the case stayed put - which is the
                stage-versus-status divergence this whole exercise removed.
                Both move together or neither does.

    When it does freeze, the deal remembers the stage it left and returns
    THERE rather than climbing from the beginning.
    """
    reason = str(reason or "").strip()
    if len(reason) < 5:
        raise ValueError("Say what needs doing. A return with no reason sends "
                         "somebody looking for something they cannot identify.")

    from utils.api_lms_routes import _lam
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise LookupError("Application '%s' not found" % app_id)

    me = str(user.get("staff_code", "") or "").strip()
    myname = str(user.get("full_name", "") or "").strip()
    now = _dt.datetime.now().isoformat(timespec="seconds")

    owner_code = str(app.get("rm_code") or app.get("staff_code") or "").strip()
    owner_name = str(app.get("rm_name") or "").strip()
    people = people_from(to, owner_code, owner_name)
    if not people:
        raise ValueError("Name who you are asking.")

    updates: Dict[str, Any] = {
        "return_to": people,
        "returned_by_code": me,
        "returned_by_name": myname,
        "returned_at": now,
        "returned_from": asked_from,
        "returned_reason": reason,
    }
    if reasons:
        updates["rework_reasons"] = list(reasons)
    if set_status:
        updates["status"] = "returned"
    # It lands on their screen rather than waiting to be found.
    updates["analyst"] = {"code": people[0]["code"],
                          "name": people[0]["name"], "role": ""}

    # The deal moves only when the case does. Anything else puts the two out
    # of step, which is the fault this module exists to end.
    froze_at = ""
    if set_status:
        froze_at = _freeze_deal(app, reason, myname or me, user)
        if froze_at:
            updates["froze_at_stage"] = froze_at

    lam.update(app_id, updates)
    _audit("HANDOVER_SENT_BACK",
           "%s|from=%s|to=%s|%s"
           % (app_id, asked_from, ",".join(p["code"] for p in people),
              reason[:60]))

    notify_many(
        people,
        "%s needs something on %s" % (asked_from.title() or "Credit", app_id),
        "<p>%s has sent <b>%s</b> back to you.</p><p>%s</p>"
        % (myname or asked_from, app_id, reason),
        context="send_back:%s" % asked_from)

    return {"application_id": app_id,
            "returned_to": [p["code"] for p in people],
            "froze_at_stage": froze_at,
            "status": updates.get("status", app.get("status"))}


def _freeze_deal(app: Dict[str, Any], reason: str, byname: str,
                 user: Dict[str, Any]) -> str:
    """Move the deal to Rework and return the stage it left.

    Best effort: a return must never fail because the deal could not be moved,
    but a failure is recorded - an owner who cannot resubmit is what this
    exists to prevent.
    """
    deal_id = str(app.get("pipeline_deal_id") or "").strip()
    if not deal_id:
        return ""
    try:
        from utils.core import PipelineManager
        from utils.api import _stage_flow_for, _product_document_config
        pm = PipelineManager()
        d = pm.get_deal(deal_id)
        if not d:
            return ""
        cur = str(d.get("stage", "") or "")
        if cur.lower().startswith("closed"):
            return ""
        flow = [str(x) for x in (_stage_flow_for(
            d.get("product_type") or d.get("product", "")) or [])]
        target = REWORK_STAGE if REWORK_STAGE in flow else ""
        if not target:
            # No Rework stage configured: the document stage, so the owner can
            # at least resubmit. Less good - the case loses its place.
            _docs, doc_stage = _product_document_config(d)
            target = str(doc_stage or "").strip()
        if not target or target == cur:
            return cur
        pm.update_stage(deal_id, target,
                        "Sent back by %s: %s" % (byname, reason[:80]),
                        str(user.get("username", "") or ""))
        return cur
    except Exception as exc:
        _audit("HANDOVER_DEAL_NOT_FROZEN",
               "%s|%s" % (deal_id, str(exc)[:60]))
        return ""


def bring_back(app_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """The work is done - put the deal back where it froze.

    Returns to the stage the case left, not to the beginning. A case sent back
    from the department committee should not climb every gate again.
    """
    from utils.api_lms_routes import _lam
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise LookupError("Application '%s' not found" % app_id)

    froze = str(app.get("froze_at_stage", "") or "").strip()
    deal_id = str(app.get("pipeline_deal_id") or "").strip()
    restored = ""
    if froze and deal_id:
        try:
            from utils.core import PipelineManager
            pm = PipelineManager()
            d = pm.get_deal(deal_id)
            if d and not str(d.get("stage", "")).lower().startswith("closed"):
                pm.update_stage(deal_id, froze,
                                "Sent back work is done - returned to where it "
                                "was.", str(user.get("username", "") or ""))
                restored = froze
        except Exception as exc:
            _audit("HANDOVER_NOT_RESTORED", "%s|%s" % (deal_id, str(exc)[:60]))

    back_to = str(app.get("returned_by_code", "") or "").strip()
    lam.update(app_id, {
        "status": "assigned" if back_to else "submitted",
        "froze_at_stage": "",
        "return_to": [],
        "returned_by_code": "",
        "returned_by_name": "",
    })
    if back_to:
        notify(back_to, "%s is back with you" % app_id,
               "<p><b>%s</b> has been worked and is back with you.</p>" % app_id,
               context="bring_back")
    _audit("HANDOVER_BROUGHT_BACK",
           "%s|to=%s|stage=%s" % (app_id, back_to or "pool", restored or "-"))
    return {"application_id": app_id, "back_to": back_to,
            "restored_stage": restored}

"""
utils/referral_escalation — the 24-hour clock, and the ladder it climbs.

RULINGS (2026-08-09)
    Acceptance or return is due within 24 hours of sending.
    A referral does NOT expire for the person who referred it; it ESCALATES
    upward until a decision is given, stopping at the unit owner (Director).

WHAT "24 HOURS" MEANS HERE. One WORKING day at the same clock time, via
utils.workcal. A referral sent 16:00 on Friday is due 16:00 on Monday, not
16:00 on Saturday. The alternative reading - 24 working HOURS, which at an
eight-hour day is three working days - would have made the window far longer
than "24 hours" suggests to the person waiting.

THE LADDER climbs the structures that already exist; it defines nothing new:

    recipient
      -> their validator      daily_log_validators_for (branch triad, or the
                              line manager at Head Office)
      -> the unit owner       org_validator.unit_for_role - a Director
      -> STOPS THERE          the MD and Business Manager SEE it, but ownership
                              stays with the Director

Escalating past the Director would relocate the silence rather than resolve it:
a queue at the top that nobody owns is a dumping ground, not an escalation.

Nothing here changes a referral's state. It reports where the clock stands and
who should be leaned on - the decision is always a person's.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_WORKING_DAYS = 1


def window_days() -> int:
    """The acceptance window, in working days. Config-driven."""
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("referral_window_working_days")
        if v is not None:
            return max(int(v), 0)
    except Exception:
        pass
    return DEFAULT_WINDOW_WORKING_DAYS


def _parse(ts) -> Optional[datetime]:
    txt = str(ts or "").strip()
    if not txt:
        return None
    try:
        return datetime.fromisoformat(txt.replace("Z", "+00:00").split("+")[0])
    except ValueError:
        try:
            return datetime.fromisoformat(txt[:10])
        except ValueError:
            return None


def due_at(referred_at) -> Optional[datetime]:
    """When a decision is due: N working days on, at the same clock time."""
    sent = _parse(referred_at)
    if not sent:
        return None
    n = window_days()
    if n <= 0:
        return sent
    try:
        from utils import workcal
        d = workcal.add_business_days(sent.date(), n)
    except Exception:
        d = sent.date() + timedelta(days=n)
    return datetime.combine(d, sent.time())


def referred_at_of(deal: dict) -> str:
    """When this referral was sent — the last hop, which is the live one."""
    chain = deal.get("referral_chain") or []
    if chain:
        last = chain[-1]
        if isinstance(last, dict):
            for k in ("at", "referred_at", "timestamp"):
                if last.get(k):
                    return str(last[k])
    for k in ("referred_at", "created_at", "open_date"):
        if deal.get(k):
            return str(deal[k])
    return ""


def escalation_ladder(recipient_code: str) -> list:
    """Who to lean on, in order, ending at the unit owner.

    Reuses daily_log_validators_for and unit_for_role. Returns
    [{level, code, name, role}], never raising - an escalation path that blows
    up is worse than a short one.
    """
    out = []
    try:
        from utils.org_validator import daily_log_validators_for, unit_for_role
    except Exception:
        return out

    try:
        res = daily_log_validators_for(str(recipient_code or "")) or {}
        for v in (res.get("validators") or [])[:3]:
            code = str(v.get("validator_code") or "")
            if code and code != str(recipient_code):
                out.append({"level": "validator", "code": code,
                            "name": str(v.get("validator_name") or code),
                            "role": str(v.get("validator_role") or "")})
    except Exception as exc:
        logger.debug("referral ladder: validator lookup failed: %s", exc)

    try:
        from utils.org_validator import _register, _s
        df = _register()
        if not df.empty:
            me = df[df["Staff Code"] == _s(recipient_code)]
            if not me.empty:
                unit = unit_for_role(_s(me.iloc[0].get("Role", "")))
                if unit:
                    holders = df[df["Role"].astype(str).str.strip() == unit]
                    if not holders.empty:
                        h = holders.iloc[0]
                        out.append({"level": "unit_owner",
                                    "code": _s(h.get("Staff Code", "")),
                                    "name": _s(h.get("Staff Name", "")),
                                    "role": unit})
                    else:
                        out.append({"level": "unit_owner", "code": "",
                                    "name": unit, "role": unit})
    except Exception as exc:
        logger.debug("referral ladder: unit owner lookup failed: %s", exc)

    seen, uniq = set(), []
    for x in out:
        k = x["code"] or x["name"]
        if k and k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq


def clock_for(deal: dict, now: Optional[datetime] = None) -> dict:
    """Where this referral stands against its window.

    status:
        decided   accepted or declined already
        due       still inside the window
        overdue   past it, and escalating - NEVER expired
    """
    now = now or datetime.now()
    state = str(deal.get("referral_status") or "")
    sent_txt = referred_at_of(deal)
    sent = _parse(sent_txt)
    due = due_at(sent_txt)

    if state in ("accepted", "declined"):
        return {"status": "decided", "state": state, "sent_at": sent_txt,
                "due_at": due.isoformat() if due else "", "hours_left": 0.0,
                "overdue_hours": 0.0, "escalate_to": []}

    if not due:
        return {"status": "due", "state": state or "pending", "sent_at": sent_txt,
                "due_at": "", "hours_left": 0.0, "overdue_hours": 0.0,
                "escalate_to": []}

    delta_h = (due - now).total_seconds() / 3600.0
    overdue = delta_h < 0
    recipient = str(deal.get("referred_to_code") or deal.get("staff_code") or "")
    return {
        "status": "overdue" if overdue else "due",
        "state": state or "pending",
        "sent_at": sent_txt,
        "due_at": due.isoformat(),
        "hours_left": round(max(delta_h, 0.0), 1),
        "overdue_hours": round(abs(delta_h), 1) if overdue else 0.0,
        # Only compute the ladder when it is actually needed - it reads the
        # register, and doing that for every in-window referral would be the
        # per-row cost this codebase has paid for twice.
        "escalate_to": escalation_ladder(recipient) if overdue else [],
    }

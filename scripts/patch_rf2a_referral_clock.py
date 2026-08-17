#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RF2a - the referral clock and bench (backend).

RULINGS (2026-08-09)
    Acceptance or return is due within 24 hours of sending.
    A referral does NOT expire for the referrer - it ESCALATES until a decision
    is given, stopping at the unit owner (the Director).

WHAT "24 HOURS" MEANS. One WORKING day at the same clock time, via workcal.
A referral sent 16:00 Friday is due 16:00 the next working day - not 16:00 on a
day nobody was rostered for. The alternative reading, 24 working HOURS, is three
working days at an eight-hour day: far longer than "24 hours" suggests to the
person waiting.

NOTE ON SATURDAYS: your calendar treats Saturday as a working day at half
weight, so a Friday referral falls due on Saturday. If referrals should skip
Saturdays that is a config change (referral_window_working_days, or the work
calendar), not code.

THE LADDER climbs structures that already exist and defines nothing new:

    recipient -> their validator (branch triad, or line manager at Head Office)
              -> the unit owner  (org_validator.unit_for_role - a Director)
              -> STOPS

The MD and Business Manager SEE it at that point; ownership stays with the
Director. Escalating past them would relocate the silence rather than resolve
it - a queue at the top that nobody owns is a dumping ground.

The ladder is computed ONLY for an overdue referral. Building it reads the
staff register, and doing that for every in-window referral is the per-row cost
this codebase has already paid for twice.

ADDS
  utils/referral_escalation.py - window_days, due_at, escalation_ladder,
      clock_for. Nothing here changes a referral's state; it reports where the
      clock stands and who to lean on. The decision is always a person's.

  GET /api/pipeline/referrals/bench - what is waiting on ME, and WHAT I SENT
      that is still unactioned. The second list is the point: today a referrer
      sends one and hears nothing, with no screen that says "three people have
      been sitting on yours". Oldest first.

      It FAILS LOUD if the caller's staff code cannot be resolved. The first
      draft guarded the lookup with globals() and would have returned an empty
      bench - indistinguishable from "nothing is waiting on you".

MEASURED (Monday 10:00, window = 1 working day):
    sent Friday 16:00     overdue by 42h
    sent last Monday      overdue by 145h
    already accepted      decided, clock stops

FRONTEND IS RF2b.

Usage (from project root, .venv active):
    python scripts\patch_rf2a_referral_clock.py            # dry run
    python scripts\patch_rf2a_referral_clock.py --apply    # write + .pre_rf2a backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "referral_escalation.py")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_rf2a"

ANCHOR = '@app.get("/api/pipeline/leaderboard")'

MODULE = r'''"""
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
'''

ENDPOINT = r'''@app.get("/api/pipeline/referrals/bench")
def pipeline_referral_bench(user: dict = Depends(get_current_user)):
    """The referral bench: what is waiting on ME, and what I sent that is still
    unactioned.

    The second list is the point. Today a referrer sends a referral and hears
    nothing - there is no screen that says "three people have been sitting on
    yours". Referrals do not expire (ruling 2026-08-09); they escalate, so an
    overdue one carries the ladder of people to lean on.
    """
    from utils.staff_code import canon as _canon_b
    from utils.referral_escalation import clock_for, referred_at_of

    # _resolve_actor is defined later in this module but resolved at CALL time,
    # so a direct call is correct and a globals() guard would only mask a real
    # failure by silently yielding an empty staff code - which would return an
    # empty bench that looks like "nothing waiting on you".
    actor_code, _actor_name, _priv = _resolve_actor(user)
    my = _canon_b(actor_code or "")
    if not my:
        raise HTTPException(status_code=400,
                            detail="Your staff identity could not be resolved.")
    deals = _acquire_scoped_deals(user)

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _row(d):
        c = clock_for(d)
        return {
            "deal_id": str(d.get("id") or ""),
            "client": str(d.get("client_name") or d.get("client_cif") or ""),
            "product": str(d.get("product") or d.get("deal_category") or ""),
            "value": _val(d),
            "from_code": str(d.get("referred_by_code") or ""),
            "from_name": str(d.get("referred_by") or d.get("referred_by_name") or ""),
            "to_code": str(d.get("referred_to_code") or ""),
            "to_name": str(d.get("referred_to") or ""),
            "sent_at": referred_at_of(d),
            "clock": c,
        }

    referrals = [d for d in deals if d.get("is_referral")]
    pending = [d for d in referrals
               if str(d.get("referral_status") or "") == "pending"]

    incoming = [_row(d) for d in pending
                if _canon_b(d.get("referred_to_code")) == my]
    outgoing = [_row(d) for d in pending
                if _canon_b(d.get("referred_by_code")) == my]

    # Oldest first: the one nobody has touched is the one that needs a name
    # attached to it.
    incoming.sort(key=lambda r: r["sent_at"])
    outgoing.sort(key=lambda r: r["sent_at"])

    return {
        "incoming": incoming,
        "outgoing": outgoing,
        "incoming_overdue": sum(1 for r in incoming if r["clock"]["status"] == "overdue"),
        "outgoing_overdue": sum(1 for r in outgoing if r["clock"]["status"] == "overdue"),
    }


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - RF2a looks applied." % MOD)
        return 1

    api = open(API, encoding="utf-8").read()
    if "/api/pipeline/referrals/bench" in api:
        print("ABORT: the bench endpoint is already registered.")
        return 1
    if api.count(ANCHOR) != 1:
        print("ABORT: anchor matched %d times - apply patch_pl1_pipeline_ranking.py first."
              % api.count(ANCHOR))
        return 1
    if "_resolve_actor" not in api:
        print("ABORT: _resolve_actor not found; the bench cannot identify the caller.")
        return 1
    if not os.path.isfile(os.path.join("utils", "org_validator.py")):
        print("ABORT: org_validator missing - the escalation ladder depends on it.")
        return 1

    for token in ("escalation_ladder", "clock_for", "due_at", "window_days"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    # The ladder must be lazy: building it for every in-window referral would
    # read the register per row.
    if 'escalation_ladder(recipient) if overdue else []' not in MODULE:
        print("ABORT: the ladder is not computed lazily.")
        return 1
    # The endpoint must not silently return an empty bench.
    if "globals().get" in ENDPOINT:
        print("ABORT: the endpoint still guards the actor lookup with globals().")
        return 1
    if "could not be resolved" not in ENDPOINT:
        print("ABORT: the endpoint does not fail loud on an unresolved identity.")
        return 1
    print("  ok  embedded module and endpoint validated")

    api = api.replace(ANCHOR, ENDPOINT + ANCHOR, 1)
    if api.count('@app.get("/api/pipeline/referrals/bench")') != 1:
        print("ABORT: post-check - bench route count is not 1.")
        return 1
    if api.count(ANCHOR) != 1:
        print("ABORT: post-check - the leaderboard route was disturbed.")
        return 1
    print("  ok  post-checks: one bench route, leaderboard intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    for path in (MOD, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn, then check the bench:")
    print("  /api/pipeline/referrals/bench")
    return 0


if __name__ == "__main__":
    sys.exit(main())

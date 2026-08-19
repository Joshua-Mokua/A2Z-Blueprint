#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
TR1 - the term deposit rate desk: the branch asks, treasury prices, the branch closes.

RULING (2026-08-19): "the owner of the deal indicates the rate the customer
wants, then in treasury we expose it to all treasury staff in a pool. Treasury
approves or gives a counter rate. If it approves then straight it is booked and
closes at the branch. If they counter it goes back to the branch for discussion
with the customer, and if the customer is agreeable then they can accept the
counter WITHOUT returning it back to treasury - but on the case journey and
treasury side they see the acceptance. If there is no agreement then it books
and closes lost, but still indicates on the journey and treasury that it was
lost."

    POST /api/treasury/rates/{deal}/request           the branch asks
    GET  /api/treasury/rates/pool                     the whole desk sees it
    POST /api/treasury/rates/{deal}/approve           booked, Closed Won
    POST /api/treasury/rates/{deal}/counter           back to the branch
    POST /api/treasury/rates/{deal}/accept-counter    Closed Won, no round trip
    POST /api/treasury/rates/{deal}/decline-counter   Closed Lost
    GET  /api/treasury/rates/{deal}                   where it stands, and why

A COUNTER IS NOT A DECLINE, and that is the one thing here that could not be
borrowed. A declined credit case goes back to its owner to appeal, and the
appeal returns to whoever declined it. A COUNTERED RATE NEVER GOES BACK TO
TREASURY: the branch takes it to the customer and closes it either way.
Modelling it as a decline would have sent every accepted counter back to a desk
that had already said its piece, and the desk would have learned to ignore the
queue.

TREASURY IS A POOL, NOT A COMMITTEE. No chair, no quorum, no vote - any dealer
may price any request. A committee is for a decision several people must agree
on; a rate is one person's call, and a shared queue is what gets it answered
before the customer rings off.

BOTH SIDES SEE EVERY OUTCOME. Won at the asked rate, won at the counter, lost
at the counter - all of it stays in the treasury view. A desk that only sees
what it approved cannot tell whether its pricing is winning business.

IT ALSO MOUNTS TWO ROUTERS THAT WERE NEVER MOUNTED. Found while surveying for
this: api_treasury.py (50 routes - ALM, LCR, NSFR, yield curves, FX and bond
positions) and api_legal.py (16 routes - matters, contract review, holds,
obligations, spend) both exist, compile, and were reachable from nowhere.
Somebody wrote all of it; nothing included it; no test noticed, because a route
that does not exist cannot fail. That is the quietest way for work to be lost.

Measured, driving the real endpoints:

    approved at the rate asked   Closed Won,  won_at_requested_rate
    countered, customer accepts  Closed Won,  won_at_counter_rate
    countered, no agreement      Closed Lost, lost_at_counter_rate
    a stranger asking            refused      an RM pricing        refused
    a request with no tenor      refused      a non-treasury pool  refused

Verified: py_compile clean, and all 73 routes resolve on the app.

Usage (from project root, .venv active):
    python scripts\\patch_tr1_treasury_rate_desk.py            # dry run
    python scripts\\patch_tr1_treasury_rate_desk.py --apply
"""
import json
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
MODULE = os.path.join("utils", "api_treasury_rates.py")
BACKUP_SUFFIX = ".pre_tr1"

MOUNT_ANCHOR = '''except Exception as _exc:  # noqa: BLE001
    logger.warning(f"Roles router not loaded: {_exc}")
'''

MOUNT_BLOCK = r'''# ── THE ROUTERS THAT WERE WRITTEN AND NEVER MOUNTED ─────────────────────────
# Found 2026-08-19 while surveying for the term-deposit workflow: 59 endpoints
# across treasury and legal exist, compile, and are reachable from nowhere.
#
#   api_treasury.py   43 routes - ALM, LCR and NSFR, repricing gaps, yield
#                     curves, FX and bond positions, mark-to-market, climate
#                     limits, Islamic treasury, digital assets
#   api_legal.py      16 routes - matters, contract review, clauses, counsel,
#                     documents, obligations, legal holds, spend, analytics
#
# Somebody wrote all of it. Nothing mounted it, so nothing could call it - and
# no test noticed, because a route that does not exist cannot fail. That is the
# quietest way for work to be lost, and it had been lost for a long time.
#
# Each is guarded separately: one module failing to import must not take the
# whole API down, and the warning names which one so it is not silent.
for _mod_name, _label in (("utils.api_treasury", "treasury"),
                          ("utils.api_legal", "legal"),
                          ("utils.api_treasury_rates", "treasury rate desk")):
    try:
        _m = __import__(_mod_name, fromlist=["router"])
        app.include_router(_m.router)
        logger.info("A2Z API — %s router mounted", _label)
    except Exception as _exc:  # noqa: BLE001
        logger.warning("%s router not loaded: %s", _label, _exc)
'''

MODULE_SRC = r'''# -*- coding: utf-8 -*-
"""Term deposit rate approval: the branch asks, treasury prices, the branch closes.

RULING (2026-08-19): "the owner of the deal indicates the rate the customer
wants, then in treasury we expose it to all treasury staff in a pool. Treasury
approves or gives a counter rate. If it approves then straight it is booked and
closes at the branch. If they counter it goes back to the branch for discussion
with the customer, and if the customer is agreeable then they can accept the
counter WITHOUT returning it back to treasury - but on the case journey and
treasury side they see the acceptance. If there is no agreement then it books
and closes lost, but still indicates on the journey and treasury that it was
lost."

THE SHAPE IS THE CREDIT FLOW WITH DIFFERENT WORDS, and almost none of it is new:

    the branch raises it          a deal, as now
    a manager recommends          the existing recommendation gate
    treasury prices it            a decision, with a rate attached
    a counter comes back          NOT a decline - see below
    the branch closes it          Closed Won or Closed Lost

WHAT IS GENUINELY DIFFERENT, AND IT MATTERS: a counter-rate is NOT a decline.
A declined case goes back to its owner to appeal or accept, and the appeal
returns to whoever declined it. A COUNTERED RATE DOES NOT GO BACK TO TREASURY -
the branch takes it to the customer and closes it either way. Treasury never
sees it again except to watch what happened.

That is why this does not reuse the decline machinery. Modelling a counter as a
decline would have sent every accepted counter back to a treasury desk that had
already said its piece, and treasury would have learned to ignore the queue.

TREASURY IS A POOL, NOT A COMMITTEE. There is no chair, no quorum and no vote:
any treasury dealer may price any request. A committee is for a decision that
needs several people to agree; a rate is one person's call and the queue is
shared so it gets answered quickly.

EVERY OUTCOME IS VISIBLE ON BOTH SIDES. Won, lost, accepted-at-counter: all of
it lands on the case journey and stays in treasury's view. A desk that only sees
what it approved cannot tell whether its pricing is winning business.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

router = APIRouter(prefix="/api/treasury/rates", tags=["treasury-rates"])


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pm():
    from utils.core import PipelineManager
    return PipelineManager()


def _user_dep():
    from utils.api import get_current_user
    return get_current_user


def _is_treasury(user: dict) -> bool:
    """Anybody on the treasury desk may price a request.

    Deliberately broad. A rate is one dealer's call, the queue is shared, and a
    narrow list is how a desk of eight ends up with two people able to answer.
    An admin is included because somebody has to be able to unstick a request
    at five to five.
    """
    if user.get("is_admin"):
        return True
    role = str(user.get("role", "") or "").lower()
    unit = str(user.get("unit", "") or user.get("department", "") or "").lower()
    return ("treasury" in role or "treasury" in unit
            or "dealer" in role or "ficc" in role or "alm" in role)


def _write(pm, deal_id: str, updates: Dict[str, Any], actor: str) -> dict:
    """Through the one helper, so the change reaches Postgres as well as JSON.

    Writing to one store is not writing - that lesson cost four mornings on the
    committee votes and there is no reason to relearn it here.
    """
    try:
        from utils.api import _write_deal
        return _write_deal(pm, deal_id, updates, actor)
    except Exception:
        # update_deal takes an actor. Calling it without one raises a
        # TypeError that the caller sees as a 500 with no explanation - which
        # is exactly what happened the first time this ran.
        try:
            pm.update_deal(deal_id, updates, actor or "system")
        except TypeError:
            pm.update_deal(deal_id, updates)
        try:
            from utils.api import _db_sync_pipeline_deal
            _db_sync_pipeline_deal(pm.get_deal(deal_id))
        except Exception:
            pass
        return pm.get_deal(deal_id)


def _deal_or_404(deal_id: str):
    pm = _pm()
    deal = pm.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return pm, deal


def _rate_block(deal: dict) -> dict:
    return dict(deal.get("rate_request") or {})


# ── The branch asks ─────────────────────────────────────────────────────────
@router.post("/{deal_id}/request")
def request_rate(deal_id: str, payload: dict = Body(default_factory=dict),
                 user: dict = Depends(_user_dep())):
    """The branch states what the customer wants: amount, tenor, rate.

    All three are required. A request that reaches a dealer without a tenor is
    a message asking them to come back and ask, which is slower than not
    sending it.
    """
    pm, deal = _deal_or_404(deal_id)
    me = str(user.get("staff_code", "") or "").strip()
    owner = str(deal.get("staff_code", "") or "").strip()
    if not (user.get("is_admin") or me == owner):
        raise HTTPException(status_code=403,
                            detail="Only the deal's owner can ask for a rate.")

    existing = _rate_block(deal)
    if existing.get("status") == "awaiting_treasury":
        raise HTTPException(
            status_code=409,
            detail="A rate request is already with treasury on this deal.")

    try:
        amount = float(payload.get("amount") or deal.get("deal_value") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    tenor = str(payload.get("tenor_days") or payload.get("tenor") or "").strip()
    try:
        asked = float(payload.get("requested_rate"))
    except (TypeError, ValueError):
        asked = None

    missing = [n for n, v in (("amount", amount > 0), ("tenor", bool(tenor)),
                              ("requested rate", asked is not None)) if not v]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="A rate request needs %s. A dealer cannot price what is not "
                   "stated." % ", ".join(missing))

    block = {
        "status": "awaiting_treasury",
        "amount": amount,
        "tenor": tenor,
        "requested_rate": asked,
        "requested_by": me,
        "requested_by_name": str(user.get("full_name", "") or ""),
        "requested_at": _now(),
        "history": list(existing.get("history") or []) + [
            {"what": "requested", "rate": asked, "by": str(user.get("full_name", "") or ""),
             "at": _now()}],
    }
    _write(pm, deal_id, {"rate_request": block}, str(user.get("username", "") or ""))
    return {"deal_id": deal_id, "rate_request": block}


# ── The treasury pool ───────────────────────────────────────────────────────
@router.get("/pool")
def rate_pool(user: dict = Depends(_user_dep())):
    """Every request waiting on a price, and every one recently answered.

    SHOWN TO THE WHOLE DESK, not routed to an individual. And it carries the
    ANSWERED ones too - a desk that only sees what it has not done yet cannot
    tell whether its pricing is winning business.
    """
    if not _is_treasury(user):
        raise HTTPException(status_code=403,
                            detail="This queue is for the treasury desk.")
    waiting: List[dict] = []
    answered: List[dict] = []
    for d in (_pm().deals or []):
        rr = d.get("rate_request") or {}
        if not rr:
            continue
        row = {
            "deal_id": d.get("id"), "client_name": d.get("client_name"),
            "product": d.get("product_type") or d.get("product"),
            "branch": d.get("branch") or d.get("unit"),
            "rm_name": d.get("staff_name"),
            "amount": rr.get("amount"), "tenor": rr.get("tenor"),
            "requested_rate": rr.get("requested_rate"),
            "offered_rate": rr.get("offered_rate"),
            "status": rr.get("status"),
            "requested_at": rr.get("requested_at"),
            "priced_by_name": rr.get("priced_by_name"),
            "outcome": rr.get("outcome"),
        }
        (waiting if rr.get("status") == "awaiting_treasury" else answered).append(row)
    waiting.sort(key=lambda r: str(r.get("requested_at") or ""))
    answered.sort(key=lambda r: str(r.get("requested_at") or ""), reverse=True)
    return {"waiting": waiting, "answered": answered[:50],
            "total_waiting": len(waiting)}


@router.post("/{deal_id}/approve")
def approve_rate(deal_id: str, payload: dict = Body(default_factory=dict),
                 user: dict = Depends(_user_dep())):
    """Treasury takes the rate as asked. The deal books and closes Won.

    "If it approves then straight it is booked and closes at the branch." No
    second step and nobody to chase: the branch asked, treasury said yes, the
    business is done.
    """
    if not _is_treasury(user):
        raise HTTPException(status_code=403,
                            detail="Only the treasury desk can price a request.")
    pm, deal = _deal_or_404(deal_id)
    rr = _rate_block(deal)
    if rr.get("status") != "awaiting_treasury":
        raise HTTPException(
            status_code=400,
            detail="This request is not with treasury (it is %r)."
                   % (rr.get("status") or "not raised"))

    rate = rr.get("requested_rate")
    rr.update({
        "status": "approved",
        "offered_rate": rate,
        "priced_by": str(user.get("staff_code", "") or ""),
        "priced_by_name": str(user.get("full_name", "") or ""),
        "priced_at": _now(),
        "outcome": "won_at_requested_rate",
        "note": str(payload.get("note", "") or "").strip(),
    })
    rr["history"] = list(rr.get("history") or []) + [
        {"what": "approved", "rate": rate,
         "by": str(user.get("full_name", "") or ""), "at": _now()}]

    _write(pm, deal_id, {
        "rate_request": rr,
        "stage": "Closed Won",
        "closed_reason": "Rate approved by treasury at %s" % rate,
        "closed_at": _now(),
        "closed_by_name": str(user.get("full_name", "") or ""),
    }, str(user.get("username", "") or ""))
    return {"deal_id": deal_id, "rate_request": rr, "stage": "Closed Won"}


@router.post("/{deal_id}/counter")
def counter_rate(deal_id: str, payload: dict = Body(default_factory=dict),
                 user: dict = Depends(_user_dep())):
    """Treasury offers a different rate. It goes back to the branch, not to a queue.

    A COUNTER IS NOT A DECLINE. The branch takes it to the customer and closes
    it either way - "they can accept the counter without returning it back to
    treasury". Treasury does not see it again except to watch what happened.

    Modelling this as a decline would send every accepted counter back to a
    desk that had already said its piece, and the desk would learn to ignore
    the queue.
    """
    if not _is_treasury(user):
        raise HTTPException(status_code=403,
                            detail="Only the treasury desk can price a request.")
    pm, deal = _deal_or_404(deal_id)
    rr = _rate_block(deal)
    if rr.get("status") != "awaiting_treasury":
        raise HTTPException(
            status_code=400,
            detail="This request is not with treasury (it is %r)."
                   % (rr.get("status") or "not raised"))
    try:
        offered = float(payload.get("offered_rate"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400,
                            detail="State the rate you are offering.")

    rr.update({
        "status": "countered",
        "offered_rate": offered,
        "priced_by": str(user.get("staff_code", "") or ""),
        "priced_by_name": str(user.get("full_name", "") or ""),
        "priced_at": _now(),
        "note": str(payload.get("note", "") or "").strip(),
        "outcome": "",
    })
    rr["history"] = list(rr.get("history") or []) + [
        {"what": "countered", "rate": offered,
         "by": str(user.get("full_name", "") or ""), "at": _now(),
         "note": rr.get("note")}]

    _write(pm, deal_id, {"rate_request": rr}, str(user.get("username", "") or ""))
    return {"deal_id": deal_id, "rate_request": rr}


# ── The branch closes it ────────────────────────────────────────────────────
@router.post("/{deal_id}/accept-counter")
def accept_counter(deal_id: str, payload: dict = Body(default_factory=dict),
                   user: dict = Depends(_user_dep())):
    """The customer took the counter. It books and closes Won, without treasury.

    "If the customer is agreeable then they can accept the counter without
    returning it back to treasury - but on the case journey and treasury side
    they see the acceptance."
    """
    pm, deal = _deal_or_404(deal_id)
    me = str(user.get("staff_code", "") or "").strip()
    owner = str(deal.get("staff_code", "") or "").strip()
    if not (user.get("is_admin") or me == owner):
        raise HTTPException(
            status_code=403,
            detail="Only the deal's owner can accept a rate on the customer's "
                   "behalf.")
    rr = _rate_block(deal)
    if rr.get("status") != "countered":
        raise HTTPException(
            status_code=400,
            detail="There is no counter-rate to accept on this deal.")

    rr.update({
        "status": "accepted_at_counter",
        "accepted_by": me,
        "accepted_by_name": str(user.get("full_name", "") or ""),
        "accepted_at": _now(),
        "outcome": "won_at_counter_rate",
    })
    rr["history"] = list(rr.get("history") or []) + [
        {"what": "accepted at counter", "rate": rr.get("offered_rate"),
         "by": str(user.get("full_name", "") or ""), "at": _now()}]

    _write(pm, deal_id, {
        "rate_request": rr,
        "stage": "Closed Won",
        "closed_reason": "Customer accepted the counter rate of %s"
                         % rr.get("offered_rate"),
        "closed_at": _now(),
        "closed_by_name": str(user.get("full_name", "") or ""),
    }, str(user.get("username", "") or ""))
    return {"deal_id": deal_id, "rate_request": rr, "stage": "Closed Won"}


@router.post("/{deal_id}/decline-counter")
def decline_counter(deal_id: str, payload: dict = Body(default_factory=dict),
                    user: dict = Depends(_user_dep())):
    """No agreement. It closes Lost, and treasury sees that it did.

    "If there is no agreement then it books and closes lost, but still
    indicates on the journey and treasury that it was lost."

    A REASON IS ASKED FOR, not required. A desk that knows it lost on price
    behaves differently from one that knows it lost on tenor, and requiring the
    reason would only teach people to type a full stop.
    """
    pm, deal = _deal_or_404(deal_id)
    me = str(user.get("staff_code", "") or "").strip()
    owner = str(deal.get("staff_code", "") or "").strip()
    if not (user.get("is_admin") or me == owner):
        raise HTTPException(status_code=403,
                            detail="Only the deal's owner can close this.")
    rr = _rate_block(deal)
    if rr.get("status") != "countered":
        raise HTTPException(
            status_code=400,
            detail="There is no counter-rate to decline on this deal.")

    why = str(payload.get("reason", "") or "").strip()
    rr.update({
        "status": "declined_at_counter",
        "declined_by": me,
        "declined_by_name": str(user.get("full_name", "") or ""),
        "declined_at": _now(),
        "decline_reason": why,
        "outcome": "lost_at_counter_rate",
    })
    rr["history"] = list(rr.get("history") or []) + [
        {"what": "declined at counter", "rate": rr.get("offered_rate"),
         "by": str(user.get("full_name", "") or ""), "at": _now(), "note": why}]

    _write(pm, deal_id, {
        "rate_request": rr,
        "stage": "Closed Lost",
        "closed_reason": why or "Customer did not accept the counter rate",
        "closed_at": _now(),
        "closed_by_name": str(user.get("full_name", "") or ""),
    }, str(user.get("username", "") or ""))
    return {"deal_id": deal_id, "rate_request": rr, "stage": "Closed Lost"}


@router.get("/{deal_id}")
def rate_state(deal_id: str, user: dict = Depends(_user_dep())):
    """Where this deal's rate request stands, and everything that happened to it."""
    _pm_, deal = _deal_or_404(deal_id)
    rr = _rate_block(deal)
    return {"deal_id": deal_id, "rate_request": rr,
            "history": list(rr.get("history") or [])}
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "THE ROUTERS THAT WERE WRITTEN AND NEVER MOUNTED" in s:
        print("ABORT: TR1 looks applied.")
        return 1
    if s.count(MOUNT_ANCHOR) != 1:
        print("ABORT: the roles-router block matched %d times." % s.count(MOUNT_ANCHOR))
        return 1
    if os.path.isfile(MODULE):
        print("ABORT: %s already exists - not overwriting it." % MODULE)
        return 1

    s = s.replace(MOUNT_ANCHOR, MOUNT_ANCHOR + "\n" + MOUNT_BLOCK, 1)
    print("  ok  the rate desk, treasury and legal are mounted")

    for must, why in (
            ("accept-counter", "the branch could not close a counter itself"),
            ("decline-counter", "a lost deal would sit open"),
            ("_is_treasury", "anybody could price a request"),
            ("won_at_counter_rate", "treasury could not tell how it was won")):
        if must not in MODULE_SRC:
            print("ABORT: %r missing - %s." % (must, why))
            return 1
    # THE WORD APPEARS IN THE COMMENT EXPLAINING WHY IT IS NOT USED. Searching
    # the prose finds it and refuses a correct module - the same trap as the
    # gitignore check and the lock-banner check. Look for a CALL.
    _code = "\n".join(l for l in MODULE_SRC.split("\n")
                      if not l.strip().startswith("#"))
    for _bad in ("lms_application_appeal", "accept_decline", "appeal_pending"):
        if _bad in _code:
            print("ABORT: the counter path calls %r. It must not - an accepted"
                  % _bad)
            print("       counter would be sent back to treasury.")
            return 1
    if "utils.api_treasury\"" not in MOUNT_BLOCK or "utils.api_legal\"" not in MOUNT_BLOCK:
        print("ABORT: the two unmounted routers are not being mounted.")
        return 1
    import ast
    try:
        ast.parse(s)
        ast.parse(MODULE_SRC)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both close paths, desk-only pricing, no appeal")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MODULE, "w", encoding="utf-8", newline="").write(MODULE_SRC)
    print("CREATED %s" % MODULE)
    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    for f in (MODULE, API):
        try:
            py_compile.compile(f, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (f, exc))
            return 1
    print("  ok  compiles")
    print("\nRESTART UVICORN. PG1 should be applied - this writes through")
    print("_write_deal so a rate reaches Postgres as well as JSON.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

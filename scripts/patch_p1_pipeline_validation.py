#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
P1 - pipeline validation on the daily-log structure (backend).

YOUR RULING: "the pipeline validation i need it to follow the exact structure
and path we have used for the daily log for consistency and ease of use by the
management", and "the same format that recognises holidays etc and days will
also apply".

THE TIERS ARE IDENTICAL, and so is the machinery behind them:

    tier 1  the deal owner's validator   validates individual deals
    tier 2  Head of Branches             countersigns the branch pipeline day
    tier 3  the Director                 countersigns the unit pipeline day
            MD / Business Manager        observe, and may return

SHARED, NOT COPIED
    unit-day store          utils.branch_day, domain="pipeline" (from G1)
    branch countersigners   org_validator.branches_validated_by
    unit countersigners     org_validator.units_validated_by
    observation tier        units_validated_by(...)["top_of_house"]
    working calendar        utils.workcal

    A branch can hold an OPEN pipeline day and a CLOSED daily-log day at the
    same time without the two interfering - that is what the domain key buys.

THE CALENDAR APPLIES, as you asked. A pipeline day is expected only on a
WORKING day: Sundays and gazetted holidays return nothing to validate, and
Saturday is a half day as everywhere else. A deal desk is never asked to close
a day the bank was shut.

ONE DELIBERATE DIFFERENCE. Individual deals keep the PIPELINE's own validator
rule, org_validator.resolve_validator - which has a branch override the daily
log deliberately does not (line_manager_of's docstring says so explicitly).
Forcing the daily log's rule onto deals would have been "consistency" that
quietly changed who signs off a deal. The TIERS are the same; the tier-1 rule
stays the pipeline's.

ADDS  GET  /api/pipeline-validation/queue?date=&branch=
      GET  /api/pipeline-validation/days?date=
      POST /api/pipeline-validation/days/submit
      POST /api/pipeline-validation/days/validate

  The queue's `branch` parameter is tier-2 READ-ONLY inspection: can_act is
  forced false server-side, so the API and the UI agree rather than the UI
  merely hiding buttons.

  Closing a branch pipeline day REFUSES while any deal that day is still
  unvalidated, naming them. The daily log's equivalent refuses on
  over-reporting; the principle is the same - a day with open work is not a
  closed day.

Deals themselves do not move. This module validates and closes days.

FRONTEND IS P2, together with the Manager Queues restructure to
"Pipeline validation / Daily log validation" and the removal of Cancellation.

Verified: py_compile clean on the module and on api.py, router registered, four
routes.

Usage (from project root, .venv active):
    python scripts\patch_p1_pipeline_validation.py            # dry run
    python scripts\patch_p1_pipeline_validation.py --apply    # write + .pre_p1v backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_pipeline_validation.py")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_p1v"

ANCHOR = """from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)"""

WIRE = """from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)

# Pipeline validation - the same tier structure and the same calendar as the
# Daily Log, sharing utils.branch_day under domain="pipeline" rather than a
# parallel store.
from utils.api_pipeline_validation import router as pipeline_validation_router
app.include_router(pipeline_validation_router)"""

MODULE = r'''"""
utils/api_pipeline_validation — pipeline validation on the SAME structure as the
Daily Log (additive, new module).

RULING (2026-08-09): "the pipeline validation i need it to follow the exact
structure and path we have used for the daily log for consistency and ease of
use by the management".

So the tiers are identical, and so is the machinery behind them:

    tier 1  the deal owner's validator      validates individual deals
            (utils.org_validator.resolve_validator - the PIPELINE's own rule,
             which differs from the daily log's on purpose: a deal has a branch
             override the daily log deliberately does not)
    tier 2  Head of Branches                countersigns the branch pipeline day
    tier 3  the Director                    countersigns the unit pipeline day
            MD / Business Manager           observe, and may return

WHAT IS SHARED, NOT COPIED
    the unit-day store          utils.branch_day, domain=DOMAIN_PIPELINE (G1)
    who countersigns a branch   org_validator.branches_validated_by
    who countersigns a unit     org_validator.units_validated_by
    who observes                units_validated_by(...)["top_of_house"]
    the working calendar        utils.workcal

THE CALENDAR APPLIES HERE TOO (your instruction). A pipeline day is only
expected on a WORKING day: Sundays and gazetted holidays return nothing to
validate, and Saturday is a half day like everywhere else. A deal desk is not
asked to close a day the bank was shut.

Deals themselves stay where they are - this module validates and closes days; it
does not move deal storage.
"""
from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth_jwt import get_current_user
from utils.core_audit import audit_log

router = APIRouter(prefix="/api/pipeline-validation", tags=["pipeline-validation"])

_DOMAIN = "pipeline"


def _me(user: dict) -> dict:
    """Caller identity, resolved the same way the daily log resolves it."""
    from utils.api_branch_log import _identity
    return _identity(user)


def _is_admin(user: dict) -> bool:
    from utils.api_branch_log import _is_admin as _a
    return _a(user)


def _dims() -> dict:
    from utils.api_branch_log import _roster_dims
    return _roster_dims()


def _parse_day(date: str):
    try:
        return _date.fromisoformat(str(date)[:10]) if date else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")


def _rest_day(day):
    """(is_rest, label). The calendar is the same one the Daily Log uses."""
    try:
        from utils import workcal
        if not workcal.is_working_day(day):
            return True, workcal.holiday_label(day)
    except Exception:
        pass
    return False, ""


def _deals_for(day_iso: str) -> list:
    """Deals whose activity belongs to this day.

    Uses created_at where present and falls back to open_date - the same
    fallback the case journey uses. A DATE-only open_date is compared as a date,
    never parsed into a clock time, which is the defect TZ-1 fixed on the
    frontend.
    """
    try:
        from utils.core import PipelineManager
        pm = PipelineManager()
        deals = list(getattr(pm, "deals", []) or [])
    except Exception:
        return []
    out = []
    for d in deals:
        stamp = str(d.get("created_at") or d.get("open_date") or "")[:10]
        if stamp == day_iso:
            out.append(d)
    return out


@router.get("/queue")
def pipeline_validation_queue(date: str = "", branch: str = "",
                              user: dict = Depends(get_current_user)):
    """TIER 1: deals awaiting this caller's validation for one day.

    Scope is the canonical visibility engine, as everywhere else. Passing
    `branch` gives a tier-2 caller a READ-ONLY view of that branch's deals -
    can_act is forced false server-side, so the API and the UI agree rather than
    the UI merely hiding buttons.
    """
    from utils.staff_code import canon
    me = _me(user)
    my_code = str(me.get("staff_code", "") or "")
    day = _parse_day(date)
    iso = day.isoformat()

    rest, label = _rest_day(day)
    if rest:
        return {"rows": [], "date": iso, "working_day": False, "label": label,
                "pending": 0, "mode": ""}

    dims = _dims()
    inspect_only = False
    if branch:
        try:
            from utils.org_validator import branches_validated_by
            scope = branches_validated_by(my_code)
        except Exception:
            scope = {"branches": []}
        if branch not in (scope.get("branches") or []) and not _is_admin(user):
            raise HTTPException(status_code=403,
                                detail=f"{branch} is not a branch you oversee.")
        inspect_only = True
        visible = {canon(d.get("code") or ck) for ck, d in dims.items()
                   if str((d or {}).get("branch") or "").strip() == branch}
    else:
        try:
            from utils.api_pipeline_scope import get_visible_staff_codes
            visible = {canon(c) for c in get_visible_staff_codes({
                "staff_code": my_code, "role": me.get("role", ""),
                "full_name": me.get("staff_name", ""), "unit": me.get("unit", ""),
                "is_admin": bool(user.get("is_admin")),
                "can_view_all": bool(user.get("can_view_all")),
            })}
        except Exception:
            visible = {canon(my_code)} if my_code else set()

    rows, pending = [], 0
    for d in _deals_for(iso):
        code = canon(d.get("staff_code"))
        if code not in visible:
            continue
        dd = dims.get(code) or {}
        validated = bool(d.get("manager_validated"))
        # A caller may act only where they are the deal's validator - never on
        # the strength of a role title.
        can_act = False
        if not inspect_only and not validated:
            if _is_admin(user):
                can_act = True
            else:
                try:
                    from utils.org_validator import resolve_validator
                    v = resolve_validator(str(d.get("staff_code") or ""))
                    can_act = str(v.get("validator_code") or "") == my_code
                except Exception:
                    can_act = False
        if can_act:
            pending += 1
        rows.append({
            "deal_id": str(d.get("id") or ""),
            "staff_code": str(d.get("staff_code") or ""),
            "staff_name": dd.get("full_name", "") or str(d.get("staff_name") or ""),
            "role": dd.get("role", ""),
            "branch": dd.get("branch", "") or str(d.get("unit") or ""),
            "client": str(d.get("client_name") or d.get("client_cif") or ""),
            "product": str(d.get("product") or d.get("deal_category") or ""),
            "stage": str(d.get("stage") or ""),
            "deal_value": float(d.get("deal_value") or 0),
            "validated": validated,
            "validated_by": str(d.get("validated_by_name") or d.get("validated_by") or ""),
            "can_act": can_act,
        })

    rows.sort(key=lambda r: (r["validated"], r["staff_name"]))
    return {"rows": rows, "date": iso, "working_day": True, "label": "",
            "pending": pending, "branch": branch,
            "mode": "inspect" if inspect_only else "validate"}


@router.get("/days")
def pipeline_validation_days(date: str = "", user: dict = Depends(get_current_user)):
    """TIER 2/3: the branches and units this caller countersigns, for one day.

    Mirrors /api/branch-log/branch-days exactly, reading the same store with
    domain=pipeline so a branch can have an open pipeline day and a closed
    daily-log day without the two interfering.
    """
    from utils.staff_code import canon
    me = _me(user)
    my_code = str(me.get("staff_code", "") or "")
    day = _parse_day(date)
    iso = day.isoformat()

    rest, label = _rest_day(day)
    if rest:
        return {"rows": [], "date": iso, "working_day": False, "label": label,
                "top_of_house": False}

    try:
        from utils.org_validator import branches_validated_by, units_validated_by
        bscope = branches_validated_by(my_code)
        uscope = units_validated_by(my_code)
    except Exception:
        bscope, uscope = {"branches": []}, {"units": [], "top_of_house": False}

    branches = list(bscope.get("branches") or [])
    if not branches and not uscope.get("top_of_house"):
        return {"rows": [], "date": iso, "working_day": True,
                "top_of_house": False}

    dims = _dims()
    deals = _deals_for(iso)
    by_branch = {}
    for d in deals:
        dd = dims.get(canon(d.get("staff_code"))) or {}
        b = str(dd.get("branch") or d.get("unit") or "").strip()
        by_branch.setdefault(b, []).append(d)

    if uscope.get("top_of_house"):
        branches = sorted({b for b in by_branch if b} | set(branches))

    from utils.branch_day import list_branch_days
    subs = list_branch_days(iso, branches, domain=_DOMAIN)

    rows = []
    for b in sorted(branches):
        ds = by_branch.get(b, [])
        validated = sum(1 for x in ds if x.get("manager_validated"))
        rec = subs.get(b) or {}
        rows.append({
            "branch": b,
            "deals": len(ds),
            "validated": validated,
            "pending": max(len(ds) - validated, 0),
            "value": round(sum(float(x.get("deal_value") or 0) for x in ds), 2),
            "status": rec.get("status", "draft"),
            "submitted_by_name": rec.get("submitted_by_name", ""),
            "validated_by_name": rec.get("validated_by_name", ""),
            "return_note": rec.get("return_note", ""),
        })
    return {"rows": rows, "date": iso, "working_day": True,
            "top_of_house": bool(uscope.get("top_of_house")),
            "can_return": bool(uscope.get("top_of_house")) or _is_admin(user)}


@router.post("/days/submit")
def pipeline_day_submit(payload: dict = Body(default_factory=dict),
                        user: dict = Depends(get_current_user)):
    """TIER 1: close the branch's pipeline day.

    Refuses while any deal that day is still unvalidated - the daily log's
    equivalent refuses on over-reporting, and the principle is the same: a day
    that still has open work is not closed.
    """
    from utils.staff_code import canon
    me = _me(user)
    branch = str(payload.get("branch", "") or "").strip()
    day = str(payload.get("date") or _date.today())[:10]
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    try:
        from utils.org_validator import staff_validated_by
        scope = staff_validated_by(me.get("staff_code", ""))
    except Exception:
        scope = {"mode": ""}
    if scope.get("mode") != "triad" and not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Only the branch management triad can close a branch day.")

    dims = _dims()
    ds = [d for d in _deals_for(day)
          if str((dims.get(canon(d.get("staff_code"))) or {}).get("branch") or "").strip() == branch]
    open_deals = [d for d in ds if not d.get("manager_validated")]
    if open_deals:
        raise HTTPException(
            status_code=409,
            detail="%d deal(s) still awaiting validation: %s"
                   % (len(open_deals),
                      ", ".join(str(d.get("id")) for d in open_deals[:6])))

    from utils.branch_day import submit_branch_day
    rec = submit_branch_day(
        branch, day, me.get("staff_code", ""), me.get("staff_name", ""),
        round(sum(float(d.get("deal_value") or 0) for d in ds), 2),
        {}, {}, {"deals": len(ds), "validated": len(ds)}, domain=_DOMAIN)
    audit_log("PIPELINE_DAY_SUBMIT", str(user.get("username", "") or ""),
              detail=f"branch={branch} date={day} deals={len(ds)}")
    return {"pipeline_day": rec}


@router.post("/days/validate")
def pipeline_day_validate(payload: dict = Body(default_factory=dict),
                          user: dict = Depends(get_current_user)):
    """TIER 2/3: countersign a branch pipeline day, or return it with a reason."""
    me = _me(user)
    branch = str(payload.get("branch", "") or "").strip()
    day = str(payload.get("date") or _date.today())[:10]
    approve = bool(payload.get("approved", True))
    note = str(payload.get("note", "") or "")
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    try:
        from utils.org_validator import branches_validated_by, units_validated_by
        bscope = branches_validated_by(me.get("staff_code", ""))
        top = bool(units_validated_by(me.get("staff_code", "")).get("top_of_house"))
    except Exception:
        bscope, top = {"branches": []}, False
    if branch not in (bscope.get("branches") or []) and not top and not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail=f"{branch} is not a branch you countersign.")

    from utils.branch_day import validate_branch_day, return_branch_day
    try:
        rec = (validate_branch_day(branch, day, me.get("staff_code", ""),
                                   me.get("staff_name", ""), note, domain=_DOMAIN)
               if approve else
               return_branch_day(branch, day, me.get("staff_code", ""),
                                 me.get("staff_name", ""), note, domain=_DOMAIN))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    audit_log("PIPELINE_DAY_VALIDATE" if approve else "PIPELINE_DAY_RETURN",
              str(user.get("username", "") or ""), detail=f"branch={branch} date={day}")
    return {"pipeline_day": rec}
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - P1 looks applied." % MOD)
        return 1

    api = open(API, encoding="utf-8").read()
    if "api_pipeline_validation" in api:
        print("ABORT: the pipeline validation router is already registered.")
        return 1
    if api.count(ANCHOR) != 1:
        print("ABORT: router anchor matched %d times (expected 1)." % api.count(ANCHOR))
        return 1

    # G1 is the store this depends on: without the domain key, a pipeline day
    # would overwrite the daily-log day for the same branch and date.
    bd = os.path.join("utils", "branch_day.py")
    if not os.path.isfile(bd):
        print("ABORT: utils/branch_day.py missing - apply patch_b2_branch_day.py first.")
        return 1
    if "DOMAIN_PIPELINE" not in open(bd, encoding="utf-8").read():
        print("ABORT: apply patch_g1_domain_store.py first, or a pipeline day would")
        print("       overwrite the daily-log day for the same branch and date.")
        return 1

    for token in ("DOMAIN", "workcal", "branches_validated_by",
                  "resolve_validator", "units_validated_by"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    for route in ('@router.get("/queue")', '@router.get("/days")',
                  '@router.post("/days/submit")', '@router.post("/days/validate")'):
        if MODULE.count(route) != 1:
            print("ABORT: embedded module has %d of %s." % (MODULE.count(route), route))
            return 1
    print("  ok  embedded module validated (%d lines, 4 routes)"
          % (MODULE.count("\n") + 1))

    api = api.replace(ANCHOR, WIRE, 1)
    if api.count("include_router(pipeline_validation_router)") != 1:
        print("ABORT: post-check - router not registered exactly once.")
        return 1
    if api.count("include_router(branch_log_router)") != 1:
        print("ABORT: post-check - the branch-log router registration changed.")
        return 1
    print("  ok  api.py - router registered once, branch-log untouched")

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

    print("\nRestart uvicorn, then check a branch manager's queue:")
    print("  /api/pipeline-validation/queue?date=YYYY-MM-DD")
    return 0


if __name__ == "__main__":
    sys.exit(main())

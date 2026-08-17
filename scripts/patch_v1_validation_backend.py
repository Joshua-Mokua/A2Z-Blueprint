#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V1 - daily-log validation backend: branch triad + day-scoped queue.

RULINGS IMPLEMENTED (2026-08-08):
  * Branch staff are validated by the BRANCH MANAGEMENT TRIAD; Head Office
    staff by the pure line manager.
  * No bulk validate - each row is actioned individually (frontend concern,
    noted here so V2 does not add one).
  * Staff who filed NOTHING still appear in the queue, so a manager sees who
    owes a log.

WHAT THIS ADDS

1. utils/org_validator.py - daily_log_validators_for(staff_code) and
   can_validate_daily_log(validator, staff). The triad is resolved from the
   staff register by ROLE within the person's own unit, and the role names come
   from org_config.json (`daily_log_branch_validator_roles`), NOT from code -
   branch titles change and a rename must not need a deploy. The register shows
   the three real roles as:

       Branch Manager                                  11
       Assistant Branch Service & Operations Manager    8
       Customer Service Manager                        15

   Only 11 Branch Managers cover 17 branches, so org_config.acting_bm is folded
   in for Mombasa Moi, Eldoret, Thika, Karatina and Nyeri. A branch with no
   triad member at all falls back to the line manager rather than leaving a log
   unvalidatable.

2. data/org_config.json - the `daily_log_branch_validator_roles` key.

3. GET /api/branch-log/validation-queue?date=YYYY-MM-DD - one day, rows shaped
   exactly like the history grid so Manager Queues can reuse its columns and
   colours. Includes never-filed staff (status='missing', can_act=false), and
   returns nothing at all on a rest day - nobody should be asked to validate a
   Sunday.

4. POST /api/branch-log/{id}/validate now checks can_validate_daily_log instead
   of the _is_manager role-substring guess. Admins keep an override. This closes
   a real hole: previously ANY role containing "head" or "manager" could
   validate ANY log in scope.

Verified: py_compile clean on both modules; the endpoint appears exactly once.

Usage (from project root, .venv active):
    python scripts\\patch_v1_validation_backend.py            # dry run
    python scripts\\patch_v1_validation_backend.py --apply    # write + .pre_v1 backups
"""
import json
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
CFG = os.path.join("data", "org_config.json")
BACKUP_SUFFIX = ".pre_v1"

TRIAD_ROLES = [
    "Branch Manager",
    "Assistant Branch Service & Operations Manager",
    "Customer Service Manager",
]

OV_ANCHOR = "def resolve_validator(owner_code: str) -> dict:"
API_ANCHOR = '@router.get("/history-grid")'
GUARD_OLD = '''    """Supervisor validates (approves/rejects) a submitted log."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Supervisor/manager access required.")'''

TRIAD_NEW = r'''# ── Daily-log validators ─────────────────────────────────────────────────────
# RULING (2026-08-08): a BRANCH log is validated by the branch management triad;
# a HEAD OFFICE log is validated by the pure line manager.
#
# The triad role names live in org_config.json, not here — branch titles change
# and a rename must not require a code deploy. The fallback below is only used
# when the key is absent.
_DEFAULT_TRIAD_ROLES = [
    "Branch Manager",
    "Assistant Branch Service & Operations Manager",
    "Customer Service Manager",
]


def _triad_roles() -> list:
    """Branch roles permitted to validate daily logs, from org_config.json."""
    try:
        from utils.config import load_org_config
        roles = load_org_config().get("daily_log_branch_validator_roles")
        if isinstance(roles, list) and roles:
            return [str(r) for r in roles if str(r).strip()]
    except Exception:
        pass
    return list(_DEFAULT_TRIAD_ROLES)


def _acting_bm_for(unit: str) -> str:
    """org_config.acting_bm covers branches with no substantive Branch Manager
    (11 BMs across 17 branches). Returns a staff code or ''."""
    try:
        from utils.config import load_org_config
        acting = load_org_config().get("acting_bm") or {}
        for k, v in acting.items():
            if _s(k).lower() == _s(unit).lower():
                return _s(v)
    except Exception:
        pass
    return ""


def daily_log_validators_for(staff_code: str) -> dict:
    """Who may validate this person's DAILY LOG.

    Branch staff  -> every holder of a triad role in their own unit, plus the
                     acting Branch Manager where org_config names one.
    Head Office    -> the pure reporting-tree line manager (line_manager_of).

    Returns {"mode": "triad"|"line_manager", "unit": str,
             "validators": [{validator_code, validator_name, validator_role,
                             validator_unit, ...}]}
    Read-only; never raises. An empty validators list means "unresolved" and the
    caller should fall back to admin, exactly as resolve_validator does.
    """
    df = _register()
    if df.empty or "Staff Code" not in df.columns:
        return {"mode": "line_manager", "unit": "",
                "validators": [_admin_fallback("staff register unavailable")]}

    person = df[df["Staff Code"] == _s(staff_code)]
    if person.empty:
        return {"mode": "line_manager", "unit": "",
                "validators": [_admin_fallback(f"staff {staff_code} not in register")]}

    p = person.iloc[0]
    unit = _s(p.get("Unit", ""))

    # Head Office (and anyone with no unit) keeps the line-manager model.
    if not unit or unit.lower() == _HEAD_OFFICE:
        return {"mode": "line_manager", "unit": unit,
                "validators": [line_manager_of(staff_code)]}

    wanted = _triad_roles()
    out, seen = [], set()
    for _, row in df.iterrows():
        if _s(row.get("Unit", "")).lower() != unit.lower():
            continue
        have = _s(row.get("Role", ""))
        if not any(_role_matches(have, w) for w in wanted):
            continue
        code = _s(row.get("Staff Code", ""))
        if code and code not in seen and code != _s(staff_code):
            seen.add(code)
            out.append(_found(row))

    acting = _acting_bm_for(unit)
    if acting and acting not in seen:
        hit = df[df["Staff Code"] == acting]
        if not hit.empty:
            rec = _found(hit.iloc[0])
            rec["via"] = "acting BM for %s" % unit
            out.append(rec)
            seen.add(acting)

    if not out:
        # No triad member in this branch — fall back to the line manager rather
        # than leaving the log unvalidatable.
        return {"mode": "line_manager", "unit": unit,
                "validators": [line_manager_of(staff_code)]}

    return {"mode": "triad", "unit": unit, "validators": out}


def can_validate_daily_log(validator_code: str, staff_code: str) -> bool:
    """True when validator_code is permitted to validate staff_code's daily log."""
    vc = _s(validator_code)
    if not vc:
        return False
    res = daily_log_validators_for(staff_code)
    return any(_s(v.get("validator_code")) == vc for v in res.get("validators", []))


'''

QUEUE_NEW = r'''@router.get("/validation-queue")
def branch_log_validation_queue(date: str = "", user: dict = Depends(get_current_user)):
    """Daily-log validation queue for ONE day, in the same row shape as the
    history grid so Manager Queues can reuse its column and colour vocabulary.

    WHO APPEARS: every staff member this caller is a permitted validator for,
    per utils.org_validator.daily_log_validators_for — the branch management
    triad inside a branch, the pure line manager at Head Office. This endpoint
    does not decide that rule; it asks for it.

    Staff who filed NOTHING are included (ruling 2026-08-08) so a manager can
    see who owes a log, carrying status='missing' and no actions.

    Rest days are excluded outright: nobody should be asked to validate a Sunday.
    """
    from datetime import date as _date
    from utils.branch_log import metric_keys, fields_schema
    from utils.branch_log_analytics import _target_for
    from utils.staff_code import canon as _canon_q

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")

    try:
        day = _date.fromisoformat(str(date)[:10]) if date else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    # Rest days carry no target and nothing to validate.
    try:
        from utils import workcal as _wc
        if not _wc.is_working_day(day):
            return {"rows": [], "columns": [], "date": day.isoformat(),
                    "working_day": False, "label": _wc.holiday_label(day),
                    "mode": "", "pending": 0}
    except Exception:
        pass

    dims = _roster_dims()
    from utils.org_validator import daily_log_validators_for

    # Everyone this caller may validate. Resolved from the roster, so it covers
    # staff who have never filed.
    mine, mode = [], ""
    for ck, d in dims.items():
        code = d.get("code") or ck
        if _canon_q(code) == _canon_q(my_code):
            continue
        try:
            res = daily_log_validators_for(code)
        except Exception:
            continue
        if any(str(v.get("validator_code") or "") == my_code
               for v in res.get("validators", [])):
            mine.append((code, d))
            mode = mode or res.get("mode", "")

    if not mine:
        return {"rows": [], "columns": [], "date": day.isoformat(),
                "working_day": True, "label": "", "mode": mode, "pending": 0}

    blm = BranchLogManager()
    logs = blm.get_history(days=45)
    iso = day.isoformat()
    by_code = {}
    for l in logs:
        if str(l.get("log_date"))[:10] == iso:
            by_code[_canon_q(l.get("staff_code"))] = l

    mkeys = metric_keys()
    rows, pending = [], 0
    for code, d in mine:
        l = by_code.get(_canon_q(code))
        base = {
            "log_date": iso,
            "staff_code": code,
            "staff_name": d.get("full_name", ""),
            "role": d.get("role", ""),
            "department": d.get("department", ""),
            "branch": d.get("branch", ""),
        }
        if not l:
            base.update({"log_id": "", "status": "missing", "validated": False,
                         "auto_submitted": False, "index": 0.0,
                         "target": _target_for({"log_date": iso}),
                         "remarks": "", "manager_note": "", "can_act": False})
            for k in mkeys:
                base[k] = 0
        else:
            status = str(l.get("status", "submitted"))
            validated = bool(l.get("validated"))
            base.update({
                "log_id": str(l.get("id", "")),
                "status": status,
                "validated": validated,
                "auto_submitted": bool(l.get("auto_submitted")),
                "index": round(float(l.get("index") or 0), 2),
                "target": _target_for(l),
                "remarks": str(l.get("remarks") or ""),
                "manager_note": str(l.get("manager_note") or ""),
                "validated_by": str(l.get("validated_by") or ""),
                "can_act": (not validated) and status in ("submitted", "auto_submitted"),
            })
            for k in mkeys:
                base[k] = l.get(k, 0)
            if base["can_act"]:
                pending += 1
        rows.append(base)

    rows.sort(key=lambda r: (r["status"] != "missing", str(r.get("staff_name") or "")))

    from utils.branch_log_analytics import tier_of
    columns = [{"key": f["key"], "label": f["label"], "unit": f.get("unit", ""),
                "type": f.get("type", "int"), "tier": tier_of(f["key"])}
               for f in fields_schema() if f.get("type") != "text"]

    return {"rows": rows, "columns": columns, "date": iso, "working_day": True,
            "label": "", "mode": mode, "pending": pending}


'''

GUARD_NEW = r'''    """Validate (approve/reject) a submitted log.

    Permission comes from utils.org_validator.can_validate_daily_log - the
    branch triad inside a branch, the line manager at Head Office - not from a
    role-substring guess. Admins retain an override.
    """
    me = _identity(user)
    blm_probe = BranchLogManager()
    _target = next((l for l in blm_probe.get_history(days=120)
                    if str(l.get("id")) == str(log_id)), None)
    if not _target:
        raise HTTPException(status_code=404, detail=f"Log {log_id} not found")
    if not _is_admin(user):
        try:
            from utils.org_validator import can_validate_daily_log
            allowed = can_validate_daily_log(me.get("staff_code", ""),
                                             str(_target.get("staff_code") or ""))
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="You are not a permitted validator for this staff member.")
'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API, CFG):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "daily_log_validators_for" in ov:
        print("ABORT: org_validator already has daily_log_validators_for - V1 looks applied.")
        return 1
    if "validation-queue" in api:
        print("ABORT: api_branch_log already has /validation-queue.")
        return 1
    if "_DIMS_CACHE" not in api:
        print("ABORT: apply the Phase 3 chain first (patch_p3g_rows_reset.py last).")
        return 1

    for label, hay, anchor in (("org_validator", ov, OV_ANCHOR),
                               ("api_branch_log", api, API_ANCHOR),
                               ("validate guard", api, GUARD_OLD)):
        if hay.count(anchor) != 1:
            print("ABORT: %s anchor matched %d times (expected 1)."
                  % (label, hay.count(anchor)))
            return 1

    ov = ov.replace(OV_ANCHOR, TRIAD_NEW + OV_ANCHOR, 1)
    print("  ok  org_validator - daily_log_validators_for / can_validate_daily_log")

    api = api.replace(API_ANCHOR, QUEUE_NEW + API_ANCHOR, 1)
    print("  ok  api_branch_log - GET /validation-queue")

    api = api.replace(GUARD_OLD, GUARD_NEW, 1)
    print("  ok  api_branch_log - validate gated on the canonical check")

    # structural post-checks
    if api.count('@router.get("/validation-queue")') != 1:
        print("ABORT: post-check - validation-queue route count is not 1.")
        return 1
    if api.count("for sc, staff_logs in by_staff.items():") != 1:
        print("ABORT: post-check - history-grid row loop count changed.")
        return 1
    if "can_validate_daily_log" not in api:
        print("ABORT: post-check - validate endpoint is not using the canonical check.")
        return 1
    print("  ok  post-checks: one queue route, grid loop intact, guard wired")

    cfg = json.loads(open(CFG, encoding="utf-8").read())
    cfg_changed = "daily_log_branch_validator_roles" not in cfg
    if cfg_changed:
        cfg["daily_log_branch_validator_roles"] = list(TRIAD_ROLES)
        print("  ok  org_config - daily_log_branch_validator_roles")
    else:
        print("  ..  org_config already has daily_log_branch_validator_roles")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((OV, ov), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    if cfg_changed:
        shutil.copy2(CFG, CFG + BACKUP_SUFFIX)
        tmp = CFG + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, CFG)
        print("APPLIED %s" % CFG)

    import py_compile
    for path in (OV, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. Then check the queue for a branch manager:")
    print("  curl \"http://localhost:8502/api/branch-log/validation-queue?date=2026-08-07\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())

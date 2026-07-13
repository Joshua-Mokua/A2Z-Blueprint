"""api_branch_log.py — FastAPI routes for the Daily Branch Log.

Staff submit their own daily activity log; supervisors (managers) review and
validate. Scope: a manager validates within their unit; staff see their own
history. Mounted by utils/api.py.
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth_jwt import get_current_user
from utils.core_audit import audit_log
from utils.branch_log import BranchLogManager, fields_schema

router = APIRouter(prefix="/api/branch-log", tags=["branch-log"])


def _identity(user: dict) -> dict:
    """Resolve the caller's staff identity (code, name, unit, role) server-side."""
    username = str(user.get("username", "") or "")
    code = str(user.get("staff_code", "") or "")
    name = ""
    unit = ""
    role = str(user.get("role", "") or "")
    try:
        from utils.core import UserManager
        full = UserManager().users.get(username) or {}
        code = str(full.get("staff_code", "") or code)
        name = str(full.get("full_name", "") or "")
        role = str(full.get("role", "") or role)
        unit = str(full.get("unit", "") or full.get("department", "") or "")
    except Exception:
        pass
    if not unit and code:
        try:
            from utils.api_pipeline_scope import get_staff_roster
            df = get_staff_roster()
            hit = df[df["Staff Code"].astype(str).str.strip() == code]
            if not hit.empty:
                r0 = hit.iloc[0]
                unit = str(r0.get("Unit", "") or "")
                if not name:
                    name = str(r0.get("Staff Name", "") or "")
                if not role:
                    role = str(r0.get("Role", "") or "")
        except Exception:
            pass
    return {"staff_code": code, "staff_name": name, "unit": unit, "role": role}


def _is_manager(user: dict) -> bool:
    try:
        from utils.api_pipeline_manager_actions import is_manager
        if is_manager(user):
            return True
    except Exception:
        pass
    role = str(user.get("role", "") or "").lower()
    return user.get("is_admin") or "admin" in role or "manager" in role or "head" in role


@router.get("/fields")
def branch_log_fields(user: dict = Depends(get_current_user)):
    """The daily-log metric schema (key, label, type, unit, BSC KPI link)."""
    return {"fields": fields_schema()}


@router.get("/auto-activities")
def branch_log_auto_activities(user: dict = Depends(get_current_user)):
    """Today's system-tracked activities for the current user, to pre-fill the
    daily-log feed (read-only) so they only key untracked items. Derived from the
    activity stream (stage changes / updates) and referral hops they made."""
    me = _identity(user)
    code = str(me.get("staff_code") or "")
    if not code:
        return {"activities": [], "date": ""}
    from utils.core import PipelineManager
    from datetime import date
    pm = PipelineManager()
    today = date.today().isoformat()

    def hhmm(ts: str) -> str:
        s = str(ts or "")
        return s[11:16] if len(s) >= 16 else ""

    feed = []
    try:
        for a in pm.get_activities(staff_code=code, limit=300):
            ts = str(a.get("recorded_at") or "")
            if not ts.startswith(today):
                continue
            feed.append({"at": ts, "time": hhmm(ts),
                         "kind": str(a.get("activity_type") or "Activity"),
                         "detail": str(a.get("note") or a.get("outcome") or "")})
    except Exception:
        pass
    try:
        for d in pm.get_deals():
            for h in (d.get("referral_chain") or []):
                if str(h.get("from_code") or "") != code:
                    continue
                ts = str(h.get("at") or "")
                if not ts.startswith(today):
                    continue
                client = str(d.get("client_name") or "a client")
                to = str(h.get("to_name") or h.get("to_code") or "")
                to_dept = str(h.get("to_dept") or "")
                suffix = f" ({to_dept})" if to_dept else ""
                feed.append({"at": ts, "time": hhmm(ts), "kind": "Referral made",
                             "detail": f"{client} \u2192 {to}{suffix}"})
    except Exception:
        pass
    feed.sort(key=lambda e: e.get("at") or "")
    return {"activities": feed, "date": today}


@router.get("/config")
def branch_log_config_get(user: dict = Depends(get_current_user)):
    """Per-activity weights + daily index target (admin-configured), with fields."""
    from utils.branch_log import load_log_config
    cfg = load_log_config()
    return {"activity_weights": cfg.get("activity_weights", {}) or {},
            "daily_index_target": cfg.get("daily_index_target", 0) or 0,
            "fields": fields_schema()}


@router.post("/config")
def branch_log_config_set(payload: dict = Body(default_factory=dict),
                          user: dict = Depends(get_current_user)):
    """Set activity weights (points) + daily index target. Admin only."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log import load_log_config, save_log_config
    cfg = load_log_config()
    if isinstance(payload.get("activity_weights"), dict):
        weights = {}
        for k, v in payload["activity_weights"].items():
            try:
                weights[str(k)] = float(v or 0)
            except (TypeError, ValueError):
                weights[str(k)] = 0.0
        cfg["activity_weights"] = weights
    if "daily_index_target" in payload:
        try:
            cfg["daily_index_target"] = float(payload.get("daily_index_target") or 0)
        except (TypeError, ValueError):
            cfg["daily_index_target"] = 0.0
    save_log_config(cfg)
    audit_log("BRANCH_LOG_CONFIG", str(user.get("username", "") or ""), "weights/target updated")
    return {"status": "saved",
            "activity_weights": cfg.get("activity_weights", {}),
            "daily_index_target": cfg.get("daily_index_target", 0)}


@router.get("/ranking")
def branch_log_ranking(days: int = 30, user: dict = Depends(get_current_user)):
    """Staff ranked by cumulative productivity index over the period. Admin sees
    all; a manager sees their reporting team; others see themselves."""
    from utils.branch_log import daily_index_target, compute_index, _METRIC_KEYS
    me = _identity(user)
    blm = BranchLogManager()
    logs = blm.get_history(days=days)
    if not _is_admin(user):
        mycode = me["staff_code"]
        if _is_manager(user):
            logs = _reports_to_me(logs, mycode) + [l for l in logs if str(l.get("staff_code")) == mycode]
        else:
            logs = [l for l in logs if str(l.get("staff_code")) == mycode]
    agg: dict = {}
    for l in logs:
        sc = str(l.get("staff_code") or "")
        if not sc:
            continue
        idx = l.get("index")
        if idx is None:
            idx = compute_index({k: l.get(k, 0) for k in _METRIC_KEYS})
        r = agg.setdefault(sc, {"staff_code": sc, "staff_name": l.get("staff_name"),
                                "unit": l.get("unit"), "index": 0.0, "days": 0})
        r["index"] += float(idx or 0)
        r["days"] += 1
    target = daily_index_target()
    rows = sorted(agg.values(), key=lambda x: x["index"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["index"] = round(r["index"], 2)
        r["avg_per_day"] = round(r["index"] / r["days"], 2) if r["days"] else 0
        r["target"] = target
    return {"ranking": rows, "days": days, "daily_index_target": target}


@router.get("/mine")
def branch_log_mine(days: int = 14, user: dict = Depends(get_current_user)):
    """The caller's own recent log entries."""
    me = _identity(user)
    if not me["staff_code"]:
        return {"logs": [], "identity": me}
    blm = BranchLogManager()
    return {"logs": blm.get_history(staff_code=me["staff_code"], days=days), "identity": me}


def _is_admin(user: dict) -> bool:
    return bool(user.get("is_admin")) or "admin" in str(user.get("role", "")).lower()


def _reports_to_me(logs: list, my_code: str) -> list:
    """Keep only logs whose submitter's direct line manager (pure reporting
    tree) is this manager. Resolution is cached per submitter within the call."""
    if not my_code:
        return []
    from utils.org_validator import line_manager_of
    cache: dict = {}
    out = []
    for l in logs:
        sc = str(l.get("staff_code", "") or "")
        if sc not in cache:
            cache[sc] = str(line_manager_of(sc).get("validator_code") or "")
        if cache[sc] == my_code:
            out.append(l)
    return out


@router.get("/pending")
def branch_log_pending(user: dict = Depends(get_current_user)):
    """Entries awaiting validation, routed by the reporting tree: a manager
    sees logs from staff who report to them; admin sees all."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Supervisor/manager access required.")
    me = _identity(user)
    blm = BranchLogManager()
    all_pending = blm.get_pending_validation(unit=None)
    if _is_admin(user):
        return {"logs": all_pending}
    return {"logs": _reports_to_me(all_pending, me["staff_code"])}


@router.get("/history")
def branch_log_history(unit: str = "", days: int = 7, user: dict = Depends(get_current_user)):
    """History routed by the reporting tree: managers see their reports'
    submitted logs; admin sees all; everyone else sees their own."""
    me = _identity(user)
    blm = BranchLogManager()
    if _is_manager(user):
        if _is_admin(user):
            return {"logs": blm.get_history(days=days)}
        return {"logs": _reports_to_me(blm.get_history(days=days), me["staff_code"])}
    return {"logs": blm.get_history(staff_code=me["staff_code"], days=days)}


@router.post("")
def branch_log_submit(payload: dict = Body(default_factory=dict),
                      user: dict = Depends(get_current_user)):
    """Submit (or update) the caller's log for today."""
    me = _identity(user)
    if not me["staff_code"]:
        raise HTTPException(status_code=400, detail="Your staff identity could not be resolved.")
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    blm = BranchLogManager()
    rec = blm.submit(me["staff_code"], me["staff_name"], me["unit"], me["role"], values or {})
    audit_log("BRANCH_LOG_SUBMIT", user.get("username", "unknown"),
              detail=f"log={rec.get('id')} unit={me['unit']}")
    return {"log": rec}


@router.post("/{log_id}/validate")
def branch_log_validate(log_id: str, payload: dict = Body(default_factory=dict),
                        user: dict = Depends(get_current_user)):
    """Supervisor validates (approves/rejects) a submitted log."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Supervisor/manager access required.")
    approved = bool(payload.get("approved", True))
    note = str(payload.get("note", "") or "")
    blm = BranchLogManager()
    rec = blm.validate(log_id, str(user.get("username", "") or ""), note, approved)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Log {log_id} not found")
    audit_log("BRANCH_LOG_VALIDATE", user.get("username", "unknown"),
              detail=f"log={log_id} approved={approved}")
    return {"log": rec}

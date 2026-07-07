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

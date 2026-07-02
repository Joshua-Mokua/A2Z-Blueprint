#!/usr/bin/env python3
"""scripts/apply_request_assignment_backend.py — B2 backend: request assignment loop.

Analyst requests a pool case -> stored on app['assignment_requests']. Chief sees a
consolidated requests list and assigns (to requester or anyone) via the existing
assign endpoint, which now also clears the requests.

Endpoints added to the LMS router (utils/api_lms_routes.py):
  POST /api/lms/applications/{id}/request-assignment  {note?}
  GET  /api/lms/applications/assignment-requests       -> cases with pending requests
Plus: the assign endpoint clears assignment_requests on success.

SAFE: .pre_reqassign backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_reqassign")
MARKER = "# === B2: ASSIGNMENT REQUESTS ==="

BLOCK = r'''

# === B2: ASSIGNMENT REQUESTS ===
@router.post("/applications/{app_id}/request-assignment",
             response_model=LoanAppMutationResponse)
def lms_request_assignment(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """An analyst requests to be assigned an unassigned (pool) case. The caller
    must be able to see the case (pool visibility) and the case must be
    unassigned + submitted. Records the request on the app; the Chief resolves it."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    if (app.get('analyst') or {}).get('code'):
        raise HTTPException(status_code=400, detail="This case is already assigned.")
    if str(app.get('status', '') or '').lower() != 'submitted':
        raise HTTPException(status_code=400, detail="Only submitted (unassigned) cases can be requested.")
    from datetime import datetime as _dt
    reqs = list(app.get('assignment_requests', []) or [])
    if any(str(r.get('by_code')) == caller_code for r in reqs):
        raise HTTPException(status_code=400, detail="You have already requested this case.")
    reqs.append({
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "at": _dt.now().isoformat(timespec="seconds"),
        "note": str((payload or {}).get('note', '') or ''),
    })
    lam.update(app_id, {"assignment_requests": reqs})
    audit_log("LMS_ASSIGNMENT_REQUESTED", str(user.get('username', '') or ''),
              f"{app_id}|by={caller_code}")
    return {"application": lam.get(app_id), "status": "requested"}


@router.get("/applications/assignment-requests")
def lms_assignment_requests(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The consolidated list of cases with pending assignment requests, for a
    manager to resolve. Manager-tier only. Scoped to the caller's visibility."""
    if not is_manager(user):
        raise HTTPException(status_code=403, detail="Manager authority required")
    lam = _lam()
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    out = []
    for app in lam.apps:
        reqs = app.get('assignment_requests') or []
        if not reqs:
            continue
        if (app.get('analyst') or {}).get('code'):
            continue  # already assigned — requests are moot
        if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
            continue
        out.append({
            "id": app.get("id"),
            "client_name": app.get("client_name"),
            "product": app.get("product"),
            "amount": app.get("amount"),
            "rm_name": app.get("rm_name"),
            "status": app.get("status"),
            "requests": reqs,
        })
    return {"cases": out, "count": len(out)}
# === END B2: ASSIGNMENT REQUESTS ===
'''

def patch_assign_clears_requests(s: str) -> str:
    """Make the assign endpoint clear assignment_requests on success."""
    anchor = '''    updated = lam.get(app_id)
    return {"application": updated, "status": "assigned"}'''
    if anchor in s and "assignment_requests" not in s.split("def lms_application_assign")[1].split("def ")[1]:
        new = '''    # B2: clear any pending assignment requests now the case is assigned.
    try:
        lam.update(app_id, {"assignment_requests": []})
    except Exception:
        pass
    updated = lam.get(app_id)
    return {"application": updated, "status": "assigned"}'''
        return s.replace(anchor, new, 1)
    return s

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted api_lms_routes.py from .pre_reqassign")
    else:
        print("  no .pre_reqassign backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print("  --dry-run: would append request endpoints + clear-on-assign."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = patch_assign_clears_requests(s)
    s = s.rstrip() + "\n" + BLOCK + "\n"
    ROUTES.write_text(s, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

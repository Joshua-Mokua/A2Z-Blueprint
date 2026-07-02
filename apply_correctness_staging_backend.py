#!/usr/bin/env python3
"""scripts/apply_correctness_staging_backend.py — C2: correctness-staging layer.

The Chief assigns a case with a PURPOSE — 'decisioning' (analyse+decide) or
'correctness' (validate packaging for committee). The assignee sees which.
A correctness reviewer marks the case ready_for_committee (optionally keying an
opinion) OR returns it for rework. Ready cases surface to the Chief to route to MCC;
rework cases stay in staging so once fixed they proceed without redoing the process.

- assign endpoint stamps assignment_purpose from the payload (model already allows extra).
- POST /applications/{id}/committee-readiness {ready|rework, opinion?, reasons?}
  sets committee_readiness = {state, by, at, opinion}.

SAFE: .pre_correctness backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_correctness")
MARKER = "# === C2: CORRECTNESS STAGING ==="

BLOCK = r'''

# === C2: CORRECTNESS STAGING ===
@router.post("/applications/{app_id}/committee-readiness",
             response_model=LoanAppMutationResponse)
def lms_committee_readiness(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """A correctness reviewer marks a case ready_for_committee or returns it for
    rework, optionally keying an opinion for the Chief. The assigned reviewer OR a
    manager may act. Ready cases become routable to committee; rework cases stay in
    staging with a reason so they can be fixed and re-submitted."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    # Only the assigned reviewer or a manager may set readiness.
    is_assignee = str((app.get('analyst') or {}).get('code') or '') == caller_code
    if not (is_assignee or is_manager(user) or user.get('is_admin')):
        raise HTTPException(status_code=403, detail="Only the assigned reviewer or a manager can set readiness")
    p = payload or {}
    decision = str(p.get("decision", "") or "").lower()  # "ready" | "rework"
    if decision not in ("ready", "rework"):
        raise HTTPException(status_code=400, detail="decision must be 'ready' or 'rework'")
    from datetime import datetime as _dt
    readiness = {
        "state": "ready_for_committee" if decision == "ready" else "returned_for_rework",
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "at": _dt.now().isoformat(timespec="seconds"),
        "opinion": str(p.get("opinion", "") or ""),
        "reasons": p.get("reasons") if isinstance(p.get("reasons"), list) else [],
    }
    lam.update(app_id, {"committee_readiness": readiness})
    audit_log("LMS_COMMITTEE_READINESS",
              str(user.get('username', '') or ''), f"{app_id}|{readiness['state']}")
    return {"application": lam.get(app_id), "status": readiness["state"]}
# === END C2: CORRECTNESS STAGING ===
'''

def patch_assign_purpose(s: str) -> str:
    """Stamp assignment_purpose from the payload after a successful assign."""
    anchor = '''    # B2: clear any pending assignment requests now the case is assigned.
    try:
        lam.update(app_id, {"assignment_requests": []})
    except Exception:
        pass'''
    if anchor in s and "assignment_purpose" not in s:
        new = '''    # B2: clear any pending assignment requests now the case is assigned.
    # C2: stamp the assignment purpose (decisioning | correctness) from the payload.
    try:
        _purpose = str(payload_dict.get("purpose", "") or "decisioning").lower()
        if _purpose not in ("decisioning", "correctness"):
            _purpose = "decisioning"
        lam.update(app_id, {"assignment_requests": [], "assignment_purpose": _purpose})
    except Exception:
        pass'''
        return s.replace(anchor, new, 1)
    return s

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted from .pre_correctness")
    else:
        print("  no .pre_correctness backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print("  --dry-run: would stamp purpose + add committee-readiness endpoint."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = patch_assign_purpose(s)
    s = s.rstrip() + "\n" + BLOCK + "\n"
    ROUTES.write_text(s, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""scripts/apply_reject_appeal_backend.py — 4b-6: reject -> owner fallback.

When a committee REJECTS, the deal returns to the owner, who can:
  - APPEAL a rejected committee gate: clears that gate's rejected record so it can
    be re-decided (re-opens the gate), logs the appeal on the deal
    (appeals[] with reason, by, at, prior_outcome).
  - CLOSE AS LOST: set the deal stage to 'Closed Lost'.

Endpoints:
  POST /api/pipeline/deals/{id}/committee-appeal  {code, reason}
  POST /api/pipeline/deals/{id}/close-lost         {reason?}

Owner/admin scoped. Appeal target = same committee (re-decide); escalation later.
SAFE: .pre_appeal backup. Idempotent. --revert. Requires 4b-4.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_appeal")
MARKER = "# === REJECT -> OWNER FALLBACK (4b-6) ==="

BLOCK = r'''

# === REJECT -> OWNER FALLBACK (4b-6) ===
@app.post("/api/pipeline/deals/{deal_id}/committee-appeal", tags=["pipeline"])
def appeal_committee_decision(deal_id: str, payload: dict = Body(default_factory=dict),
                              user: dict = Depends(get_current_user)):
    """Appeal a REJECTED committee gate: clears its record so it can be re-decided,
    and logs the appeal. Owner/admin only."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    from datetime import datetime as _dt
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    perms = resolve_deal_permissions(deal, user, visible)
    if not perms.get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    my_code = str(user.get("staff_code", "") or "").strip()
    is_admin_like = bool(user.get("is_admin")) or "admin" in str(user.get("role", "")).lower()
    is_owner = bool(my_code) and my_code == str(deal.get("staff_code", "") or "").strip()
    if not (is_owner or is_admin_like):
        raise HTTPException(status_code=403, detail="Only the deal owner (or admin) can appeal.")

    code = str(payload.get("code", "")).strip()
    reason = str(payload.get("reason", "") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="committee code is required")
    if not reason:
        raise HTTPException(status_code=400, detail="an appeal reason is required")
    records = dict(deal.get("committee_records", {}) or {})
    rec = records.get(code) or {}
    if str(rec.get("outcome", "")).upper() != "REJECTED":
        raise HTTPException(status_code=400,
            detail=f"'{code}' is not in a rejected state — nothing to appeal")

    appeals = list(deal.get("appeals", []) or [])
    appeals.append({
        "code": code,
        "reason": reason,
        "prior_outcome": rec.get("outcome"),
        "prior_votes": rec.get("votes", []),
        "by": str(user.get("username", "") or ""),
        "at": _dt.now().isoformat(timespec="seconds"),
        "outcome": "PENDING",
    })
    # clear the rejected record so the gate re-opens for a fresh decision
    records.pop(code, None)
    pm.update_deal(deal_id, {"committee_records": records, "appeals": appeals},
                   str(user.get("username", "") or ""))
    _audit("API_DEAL_COMMITTEE_APPEAL", user, f"deal={deal_id}|code={code}")
    return {"status": "appealed", "code": code,
            "message": f"{code} re-opened for a fresh decision.", "appeals": appeals}


@app.post("/api/pipeline/deals/{deal_id}/close-lost", tags=["pipeline"])
def close_deal_as_lost(deal_id: str, payload: dict = Body(default_factory=dict),
                       user: dict = Depends(get_current_user)):
    """Close the deal as Lost (owner's option after a committee rejection)."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    perms = resolve_deal_permissions(deal, user, visible)
    if not perms.get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    my_code = str(user.get("staff_code", "") or "").strip()
    is_admin_like = bool(user.get("is_admin")) or "admin" in str(user.get("role", "")).lower()
    is_owner = bool(my_code) and my_code == str(deal.get("staff_code", "") or "").strip()
    if not (is_owner or is_admin_like):
        raise HTTPException(status_code=403, detail="Only the deal owner (or admin) can close the deal.")
    reason = str(payload.get("reason", "") or "").strip()
    pm.update_deal(deal_id, {"stage": "Closed Lost", "close_reason": reason},
                   str(user.get("username", "") or ""))
    _audit("API_DEAL_CLOSE_LOST", user, f"deal={deal_id}|reason={reason[:60]}")
    return {"status": "closed_lost", "deal_id": deal_id}
# === END REJECT -> OWNER FALLBACK ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_appeal")
    else:
        print("  no .pre_appeal backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print(f"  --dry-run: would append reject/appeal endpoints ({len(BLOCK)} chars)."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  appended reject/appeal endpoints. Restart API.")

if __name__ == "__main__":
    main()

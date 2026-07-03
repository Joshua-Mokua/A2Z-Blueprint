#!/usr/bin/env python3
"""scripts/apply_committee_routing_backend.py — C1: Chief routes by limit.

Adds GET /api/lms/applications/{id}/committee-routing that returns:
  - the committee tier ladder
  - the tier SUGGESTED by the case amount (first tier whose authority_limit >= amount;
    uncapped tier if none)
  - can_refer (status permits + caller is manager)
The Chief's UI uses this to escalate to the suggested committee OR override.
The actual referral still uses the existing committee/refer endpoint (entry_tier).

SAFE: .pre_crouting backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_crouting")
MARKER = "# === C1: COMMITTEE ROUTING (suggest tier by limit) ==="

BLOCK = r'''

# === C1: COMMITTEE ROUTING (suggest tier by limit) ===
def _suggest_committee_tier(amount_kes: float) -> dict:
    """First tier whose authority_limit_kes >= amount (i.e. can decide it).
    A tier with authority_limit_kes None (uncapped) catches everything above the
    highest limit. Returns the suggested tier dict, or the highest tier."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    tiers = get_committee_tiers()
    if not tiers:
        return {}
    # tiers sorted ascending by tier number; limits generally increase.
    for t in tiers:
        lim = t.get("authority_limit_kes")
        if lim is None:
            return t  # uncapped — decides anything
        try:
            if amount_kes <= float(lim):
                return t
        except (TypeError, ValueError):
            continue
    return tiers[-1]  # above all limits -> highest tier


@router.get("/applications/{app_id}/committee-routing")
def lms_committee_routing(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Routing helper for the Chief: the tier ladder + the tier suggested by the
    case amount + whether it can be referred now. Manager-tier."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
        raise HTTPException(status_code=403, detail="Application is out of scope")
    try:
        amount = float(app.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    suggested = _suggest_committee_tier(amount)
    can_refer = is_manager(user) and is_valid_lms_transition(
        str(app.get("status", "")), "referred_to_committee")
    return {
        "tiers": get_committee_tiers(),
        "amount": amount,
        "suggested_tier": suggested.get("tier"),
        "suggested_name": suggested.get("name"),
        "can_refer": bool(can_refer),
        "current_status": app.get("status"),
    }
# === END C1: COMMITTEE ROUTING ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted from .pre_crouting")
    else:
        print("  no .pre_crouting backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print("  --dry-run: would append committee-routing endpoint."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    ROUTES.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

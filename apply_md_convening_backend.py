#!/usr/bin/env python3
"""scripts/apply_md_convening_backend.py — C4: MD convening queue.

The MD (or a manager) sees referred cases grouped by committee tier — count, case
details, pre-read tally per case, and whether it's been convened yet. A "Convene"
action stamps the committee as convened (opening the binding vote, which uses the
existing committee/vote + committee/resolve endpoints).

Adds:
  GET  /api/lms/committee/convening-queue  -> {tiers:[{tier,name,count,cases:[...]}]}
  POST /api/lms/applications/{id}/committee/convene  -> stamps committee.convened

SAFE: .pre_convene backup on api_lms_routes.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_convene")
MARKER = "# === C4: MD CONVENING QUEUE ==="

BLOCK = r'''

# === C4: MD CONVENING QUEUE ===
@router.get("/committee/convening-queue")
def lms_convening_queue(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Referred cases grouped by committee tier, for the MD to see what's awaiting
    convening. Each case carries its pre-read tally + whether it's convened yet.
    Manager-tier (the MD is a manager)."""
    if not is_manager(user):
        raise HTTPException(status_code=403, detail="Manager authority required")
    lam = _lam()
    visible_codes = get_visible_staff_codes(user)
    caller_code = str(user.get('staff_code', '') or '')
    caller_role = str(user.get('role', '') or '')
    _PREREAD_V = ("leaning_approve", "leaning_decline", "questions")
    tiers_map: Dict[Any, Dict[str, Any]] = {}
    for app in lam.apps:
        if str(app.get("status", "") or "") != "referred_to_committee":
            continue
        if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code, caller_role=caller_role):
            continue
        committee = app.get("committee") or {}
        tier = committee.get("current_tier")
        tier_name = committee.get("current_tier_name")
        prereads = [r for r in (app.get("committee_prereads") or []) if r.get("tier") == tier]
        tally = {v: sum(1 for r in prereads if r.get("view") == v) for v in _PREREAD_V}
        case = {
            "id": app.get("id"),
            "client_name": app.get("client_name"),
            "product": app.get("product"),
            "amount": app.get("amount"),
            "pre_read_count": len(prereads),
            "pre_read_tally": tally,
            "convened": bool(committee.get("convened", False)),
            "sla": app.get("sla"),
        }
        key = tier if tier is not None else 0
        if key not in tiers_map:
            tiers_map[key] = {"tier": tier, "name": tier_name, "count": 0, "cases": []}
        tiers_map[key]["count"] += 1
        tiers_map[key]["cases"].append(case)
    tiers = [tiers_map[k] for k in sorted(tiers_map.keys(), key=lambda x: (x is None, x))]
    return {"tiers": tiers,
            "total": sum(t["count"] for t in tiers),
            "awaiting": sum(1 for t in tiers for c in t["cases"] if not c["convened"])}


@router.post("/applications/{app_id}/committee/convene",
             response_model=LoanAppMutationResponse)
def lms_committee_convene(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The MD convenes the committee for a case — stamps committee.convened, opening
    the binding vote. Manager-tier."""
    if not is_manager(user):
        raise HTTPException(status_code=403, detail="Manager authority required to convene")
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if str(app.get("status", "") or "") != "referred_to_committee":
        raise HTTPException(status_code=400, detail="Case is not before a committee")
    committee = dict(app.get("committee") or {})
    from datetime import datetime as _dt
    committee["convened"] = True
    committee["convened_by"] = str(user.get('full_name', '') or user.get('username', '') or '')
    committee["convened_at"] = _dt.now().isoformat(timespec="seconds")
    lam.update(app_id, {"committee": committee})
    audit_log("LMS_COMMITTEE_CONVENED", str(user.get('username', '') or ''), app_id)
    return {"application": lam.get(app_id), "status": "referred_to_committee"}
# === END C4 ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted from .pre_convene")
    else:
        print("  no .pre_convene backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print("  --dry-run: would add convening-queue + convene endpoints."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    ROUTES.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

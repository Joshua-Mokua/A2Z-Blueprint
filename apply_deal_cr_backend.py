#!/usr/bin/env python3
"""scripts/apply_deal_cr_backend.py — 4b-3: deal-level CR (originate at branch).

The deal owner fills the Credit Report ON THE DEAL, after documents complete,
before submission. Reuses the existing CR template + autopopulate + build_cr_view
(they read fields a deal already has), storing values under deal['cr'] (same
shape as app['cr']).

Endpoints:
  GET  /api/pipeline/deals/{id}/cr   -> template + auto + saved values
  POST /api/pipeline/deals/{id}/cr   -> save {values, completed}; if completed,
       required fields enforced.

Scope-guarded (owner/admin can_view). SAFE: .pre_dealcr backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_dealcr")
MARKER = "# === DEAL-LEVEL CR ENDPOINTS (4b-3) ==="

BLOCK = r'''

# === DEAL-LEVEL CR ENDPOINTS (4b-3) ===
@app.get("/api/pipeline/deals/{deal_id}/cr", tags=["pipeline"])
def get_deal_cr(deal_id: str, user: dict = Depends(get_current_user)):
    """The deal's Credit Report: template + auto-populated + saved values.
    The CR originates at the branch (deal owner) after documents are complete."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    from utils.api_lms_cr import build_cr_view
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return build_cr_view(deal)


@app.post("/api/pipeline/deals/{deal_id}/cr", tags=["pipeline"])
def save_deal_cr(deal_id: str, payload: dict = Body(default_factory=dict),
                 user: dict = Depends(get_current_user)):
    """Save the deal owner's CR field values. If completed=true, required
    fields are enforced. Stored under deal['cr'] (mirrors app['cr'] shape)."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    from utils.api_lms_cr import build_cr_view, missing_required
    from datetime import datetime as _dt
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    values = payload.get("values")
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")
    completed = bool(payload.get("completed"))
    if completed:
        missing = missing_required(deal, values)
        if missing:
            raise HTTPException(status_code=400,
                detail="Cannot mark CR complete — required fields missing: " + ", ".join(missing))
    cr = {
        "values": values,
        "completed": completed,
        "updated_by": str(user.get("username", "") or ""),
        "updated_at": _dt.now().isoformat(timespec="seconds"),
    }
    pm.update_deal(deal_id, {"cr": cr}, str(user.get("username", "") or ""))
    _audit("API_DEAL_CR_SAVE", user, f"deal={deal_id}|completed={completed}")
    deal2 = _get_or_hydrate_deal(pm, deal_id)
    return build_cr_view(deal2)
# === END DEAL-LEVEL CR ENDPOINTS ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_dealcr")
    else:
        print("  no .pre_dealcr backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print(f"  --dry-run: would append deal CR endpoints ({len(BLOCK)} chars)."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  appended deal-level CR endpoints. Restart API.")

if __name__ == "__main__":
    main()

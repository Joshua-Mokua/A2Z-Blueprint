#!/usr/bin/env python3
"""scripts/apply_journey_backend.py — 4b-2: per-product committee journey.

Adds an ordered committee_journey (list of committee codes from the 4b-1 palette)
to each product's flow config. Empty journey = CR-only path. Validated against
the palette (each code must exist). Amount-triggered committees are injected at
resolution time (later batch), not stored here.

Also adds a resolver GET /api/pipeline/deals/{id}/committee-journey that returns
the EFFECTIVE journey for a deal = product's configured journey ∪ amount-triggered
committees, in order — the read path batches 4-5 will gate on.

SAFE: .pre_journey backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_journey")

# 1. extend the entry to carry committee_journey
ENTRY_ANCHOR = '''    entry = {
        "client_types": payload.get("client_types", []) or [],
        "stages": payload.get("stages", []) or [],
        "required_documents": payload.get("required_documents", []) or [],
        "documents_required_at_stage": str(payload.get("documents_required_at_stage", "") or ""),
    }'''
ENTRY_NEW = '''    entry = {
        "client_types": payload.get("client_types", []) or [],
        "stages": payload.get("stages", []) or [],
        "required_documents": payload.get("required_documents", []) or [],
        "documents_required_at_stage": str(payload.get("documents_required_at_stage", "") or ""),
        "committee_journey": payload.get("committee_journey", []) or [],
    }'''

# 2. validator: journey codes must exist in the palette
VAL_ANCHOR = '''    dstage = entry.get("documents_required_at_stage")
    if dstage:
        stage_names = {str(s.get("stage", "")).strip() for s in stages}
        if str(dstage).strip() not in stage_names:
            return False, f"documents_required_at_stage '{dstage}' is not one of this product's stages"'''
VAL_NEW = VAL_ANCHOR + '''
    journey = entry.get("committee_journey")
    if journey is not None:
        if not isinstance(journey, list) or any(not isinstance(x, str) for x in journey):
            return False, "committee_journey must be a list of committee codes"
        try:
            palette_codes = {str(c.get("code")) for c in _read_committee_palette()}
        except Exception:
            palette_codes = set()
        for code in journey:
            if palette_codes and code not in palette_codes:
                return False, f"committee '{code}' is not in the committee palette"'''

# 3. effective-journey resolver endpoint
MARKER = "# === COMMITTEE JOURNEY RESOLVER (4b-2) ==="
BLOCK = r'''

# === COMMITTEE JOURNEY RESOLVER (4b-2) ===
def _product_committee_journey(deal: dict) -> list:
    """The product's configured committee_journey (ordered codes). [] if none."""
    product = str(deal.get("product") or deal.get("product_type") or "").strip()
    if not product:
        return []
    pcfg = _load_json("pipeline_settings.json") or {}
    flows = pcfg.get("product_flows", {}) if isinstance(pcfg, dict) else {}
    entry = flows.get(product) if isinstance(flows, dict) else None
    if not isinstance(entry, dict):
        return []
    j = entry.get("committee_journey") or []
    return [str(c) for c in j if str(c).strip()]


def _effective_committee_journey(deal: dict) -> list:
    """Effective journey = product-configured committees, plus any palette
    committee whose amount_threshold_kes is met by the deal amount (auto-trigger),
    de-duplicated, preserving configured order then appending triggered ones."""
    configured = _product_committee_journey(deal)
    out = list(configured)
    try:
        amount = float(deal.get("deal_value") or deal.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    for c in _read_committee_palette():
        thr = 0.0
        try:
            thr = float(c.get("amount_threshold_kes", 0) or 0)
        except (TypeError, ValueError):
            thr = 0.0
        code = str(c.get("code"))
        if thr > 0 and amount >= thr and code not in out:
            out.append(code)
    return out


@app.get("/api/pipeline/deals/{deal_id}/committee-journey", tags=["pipeline"])
def get_deal_committee_journey(deal_id: str, user: dict = Depends(get_current_user)):
    """The effective committee journey for a deal (configured + amount-triggered),
    with each committee's palette definition for display."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    codes = _effective_committee_journey(deal)
    palette = {str(c.get("code")): c for c in _read_committee_palette()}
    journey = [palette.get(code, {"code": code, "name": code}) for code in codes]
    return {"journey": journey, "codes": codes,
            "cr_only": len(codes) == 0}
# === END COMMITTEE JOURNEY RESOLVER ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_journey")
    else:
        print("  no .pre_journey backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    checks = {
        "entry": ENTRY_ANCHOR in s and "committee_journey" not in s.split("entry = {")[1].split("}")[0],
        "validator": VAL_ANCHOR in s and "committee_journey must be" not in s,
        "resolver": MARKER not in s,
    }
    print("  checks:", {k: ("ok" if v else "skip") for k, v in checks.items()})
    if dry:
        print("  --dry-run: nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    if checks["entry"]:
        s = s.replace(ENTRY_ANCHOR, ENTRY_NEW, 1)
    if checks["validator"]:
        s = s.replace(VAL_ANCHOR, VAL_NEW, 1)
    if checks["resolver"]:
        s = s.rstrip() + "\n" + BLOCK + "\n"
    API.write_text(s, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

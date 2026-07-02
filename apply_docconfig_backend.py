#!/usr/bin/env python3
"""scripts/apply_docconfig_backend.py — Batch 1 of the credit-docs feature.

Per-product document configuration in product setup:
  - _validate_product_flow accepts optional required_documents (list[str]) and
    documents_required_at_stage (str, must be one of the flow's stages or blank).
  - the product-flow upsert persists both fields onto the product entry.
  - NEW GET /api/admin/document-catalog -> master document list (from lms_config
    document_checklist tiers + CR + Branch Committee Decision), for the admin
    picker.

This is CONFIG ONLY — no upload, no gate yet (later batches). Backward-compatible:
products without these fields behave exactly as before.

SAFE: backs up utils/api.py (.pre_docconfig). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_docconfig")

# 1. extend the validator: inject doc-field checks before its final return path.
VAL_ANCHOR = '''        if "win_probability" in s and s.get(\"win_probability\") is not None:
            try:
                wp = float(s.get(\"win_probability\"))
            except (TypeError, ValueError):
                return False, f\"stage '{nm}': win_probability must be a number\"'''

VAL_NEW = VAL_ANCHOR + '''
    # Batch 1: optional per-product document config.
    rd = entry.get("required_documents")
    if rd is not None:
        if not isinstance(rd, list) or any(not isinstance(x, str) for x in rd):
            return False, "required_documents must be a list of strings"
    dstage = entry.get("documents_required_at_stage")
    if dstage:
        stage_names = {str(s.get("stage", "")).strip() for s in stages}
        if str(dstage).strip() not in stage_names:
            return False, f"documents_required_at_stage '{dstage}' is not one of this product's stages"'''

# 2. extend the upsert entry to carry the two fields.
ENTRY_ANCHOR = '''    entry = {
        "client_types": payload.get("client_types", []) or [],
        "stages": payload.get("stages", []) or [],
    }'''
ENTRY_NEW = '''    entry = {
        "client_types": payload.get("client_types", []) or [],
        "stages": payload.get("stages", []) or [],
        "required_documents": payload.get("required_documents", []) or [],
        "documents_required_at_stage": str(payload.get("documents_required_at_stage", "") or ""),
    }'''

# 3. new document-catalog endpoint.
CATALOG_MARKER = "# === DOCUMENT CATALOG ENDPOINT ==="
CATALOG_BLOCK = '''

# === DOCUMENT CATALOG ENDPOINT ===
@app.get("/api/admin/document-catalog", tags=["admin"])
def admin_document_catalog(user: dict = Depends(get_current_user)):
    """Master list of documents an admin can require per product. Sourced from
    lms_config document_checklist tiers, plus workflow artifacts (Credit Report,
    Branch Committee Decision). De-duplicated, case-normalized, sorted."""
    cfg = _load_json("lms_config.json") or {}
    dc = cfg.get("document_checklist", {}) if isinstance(cfg, dict) else {}
    docs = set()
    for tier, items in dc.items():
        if isinstance(items, list):
            for d in items:
                if isinstance(d, str) and d.strip():
                    docs.add(d.strip())
    # normalize known casing dupes
    norm = {}
    for d in docs:
        key = d.lower()
        norm[key] = norm.get(key, d)  # keep first-seen canonical
    catalog = sorted(set(norm.values()))
    # workflow artifacts that also travel as required items
    for extra in ("Credit Report", "Branch Committee Decision"):
        if extra not in catalog:
            catalog.append(extra)
    return {"documents": sorted(set(catalog))}
# === END DOCUMENT CATALOG ENDPOINT ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_docconfig")
    else:
        print("  no .pre_docconfig backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")

    checks = {
        "validator": VAL_ANCHOR in s and "Batch 1: optional per-product document config" not in s,
        "entry": ENTRY_ANCHOR in s and "documents_required_at_stage" not in s.split("entry = {")[1].split("}")[0] if "entry = {" in s else False,
        "catalog": CATALOG_MARKER not in s,
    }
    print("  anchor checks:", {k: ("ok" if v else "MISS/skip") for k, v in checks.items()})
    if not checks["validator"] and "Batch 1: optional" not in s:
        print("  ERROR: validator anchor not found — aborting."); sys.exit(1)

    if dry:
        print("  --dry-run: nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")

    if checks["validator"]:
        s = s.replace(VAL_ANCHOR, VAL_NEW, 1)
    if ENTRY_ANCHOR in s:
        s = s.replace(ENTRY_ANCHOR, ENTRY_NEW, 1)
    if checks["catalog"]:
        s = s.rstrip() + "\n" + CATALOG_BLOCK + "\n"
    API.write_text(s, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

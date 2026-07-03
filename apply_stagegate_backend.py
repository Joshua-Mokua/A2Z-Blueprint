#!/usr/bin/env python3
"""scripts/apply_stagegate_backend.py — Batch 4a: submit-to-credit stage gate.

Submit-to-credit is only allowed when the deal is at the stage its PRODUCT
configured for documents (documents_required_at_stage, from Batch 1). If the
product has no doc-stage configured, no stage restriction applies (backward
compatible). Uses _product_document_config (Batch 2).

Exposes stage-gate info in the checklist state so the UI can explain why submit
is blocked. SAFE: .pre_stagegate backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_stagegate")

ANCHOR = '''    is_owner = bool(my_code) and my_code == str(deal.get("staff_code", "") or "").strip()
    terminal = str(deal.get("stage", "")) in ("Closed Won", "Closed Lost")
    return {
        "required": required,
        "provided": provided,
        "missing": missing,
        "already_submitted": already,
        "lms_application_id": deal.get("lms_application_id"),
        "can_submit": (is_owner or is_admin_like) and not already
                      and not terminal and perms.get("can_view", False),
    }'''

NEW = '''    is_owner = bool(my_code) and my_code == str(deal.get("staff_code", "") or "").strip()
    terminal = str(deal.get("stage", "")) in ("Closed Won", "Closed Lost")
    # Batch 4a: stage gate. If the product configured a doc-stage, submission is
    # only allowed when the deal is AT that stage. Unset = no stage restriction.
    _prod_docs, doc_stage = _product_document_config(deal)
    current_stage = str(deal.get("stage", "") or "").strip()
    stage_ok = True
    stage_required = ""
    if doc_stage:
        stage_required = doc_stage
        stage_ok = (current_stage == doc_stage)
    return {
        "required": required,
        "provided": provided,
        "missing": missing,
        "already_submitted": already,
        "lms_application_id": deal.get("lms_application_id"),
        "current_stage": current_stage,
        "stage_required": stage_required,
        "stage_ok": stage_ok,
        "can_submit": (is_owner or is_admin_like) and not already
                      and not terminal and stage_ok and perms.get("can_view", False),
    }'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_stagegate")
    else:
        print("  no .pre_stagegate backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if "stage_ok" in s and "Batch 4a: stage gate" in s:
        print("  already applied."); return
    if ANCHOR not in s:
        print("  ERROR: _credit_submission_state return anchor not found."); sys.exit(1)
    if dry:
        print("  --dry-run: would add stage gate to _credit_submission_state."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = s.replace(ANCHOR, NEW, 1)
    # also add an explicit stage message to the submit endpoint's block reason
    old_block = '''        if state["already_submitted"]:
            raise HTTPException(status_code=400,
                detail=f"Deal already submitted to credit "
                       f"(application {state['lms_application_id']}).")
        raise HTTPException(status_code=403,
            detail="Only the deal owner (or an admin) can submit it to credit.")'''
    new_block = '''        if state["already_submitted"]:
            raise HTTPException(status_code=400,
                detail=f"Deal already submitted to credit "
                       f"(application {state['lms_application_id']}).")
        if not state.get("stage_ok", True):
            raise HTTPException(status_code=400,
                detail=f"Cannot submit to credit — this product requires the deal "
                       f"to be at stage '{state.get('stage_required')}' "
                       f"(currently '{state.get('current_stage')}').")
        raise HTTPException(status_code=403,
            detail="Only the deal owner (or an admin) can submit it to credit.")'''
    if old_block in s:
        s = s.replace(old_block, new_block, 1)
    API.write_text(s, encoding="utf-8")
    print("  applied stage gate. Restart API.")

if __name__ == "__main__":
    main()

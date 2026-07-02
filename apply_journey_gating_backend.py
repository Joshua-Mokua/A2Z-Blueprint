#!/usr/bin/env python3
"""scripts/apply_journey_gating_backend.py — 4b-5: CR + committee journey gating.

Extends _credit_submission_state so submit-to-credit additionally requires:
  - CR complete (deal['cr']['completed']) when the product/journey needs a CR, AND
  - every committee gate in the deal's EFFECTIVE journey has an APPROVED record.

A REJECTED gate makes cr/committee not-ok (surfaced; owner fallback handled 4b-6).
When the journey is empty (CR-only path), only CR completeness applies.

Exposes cr_ok, cr_required, committee_ok, committee_pending[], committee_rejected[]
so the UI can explain what's outstanding.

SAFE: .pre_jgate backup. Idempotent. --revert. Requires 4b-2 + 4b-4 applied.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_jgate")

ANCHOR = '''    if doc_stage:
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

NEW = '''    if doc_stage:
        stage_required = doc_stage
        stage_ok = (current_stage == doc_stage)
    # Batch 4b-5: CR + committee journey gating.
    journey_codes = _effective_committee_journey(deal)
    cr = deal.get("cr", {}) if isinstance(deal.get("cr"), dict) else {}
    cr_required = True  # CR is the baseline artifact (Josh: "a CR should suffice")
    cr_ok = bool(cr.get("completed"))
    records = deal.get("committee_records", {}) or {}
    committee_pending = []
    committee_rejected = []
    for code in journey_codes:
        rec = records.get(code) or {}
        outcome = str(rec.get("outcome", "")).upper()
        if outcome == "APPROVED":
            continue
        if outcome == "REJECTED":
            committee_rejected.append(code)
        else:
            committee_pending.append(code)
    committee_ok = (len(committee_pending) == 0 and len(committee_rejected) == 0)
    return {
        "required": required,
        "provided": provided,
        "missing": missing,
        "already_submitted": already,
        "lms_application_id": deal.get("lms_application_id"),
        "current_stage": current_stage,
        "stage_required": stage_required,
        "stage_ok": stage_ok,
        "cr_required": cr_required,
        "cr_ok": cr_ok,
        "committee_ok": committee_ok,
        "committee_pending": committee_pending,
        "committee_rejected": committee_rejected,
        "can_submit": (is_owner or is_admin_like) and not already
                      and not terminal and stage_ok
                      and (cr_ok or not cr_required)
                      and committee_ok
                      and perms.get("can_view", False),
    }'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_jgate")
    else:
        print("  no .pre_jgate backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if "Batch 4b-5: CR + committee journey gating" in s:
        print("  already applied."); return
    if "_effective_committee_journey" not in s:
        print("  ERROR: 4b-2 must be applied first."); sys.exit(1)
    if ANCHOR not in s:
        print("  ERROR: _credit_submission_state anchor not found (is 4a applied?)."); sys.exit(1)
    # also extend the submit endpoint's block reasons for CR/committee
    old_block = '''        if not state.get("stage_ok", True):
            raise HTTPException(status_code=400,
                detail=f"Cannot submit to credit — this product requires the deal "
                       f"to be at stage '{state.get('stage_required')}' "
                       f"(currently '{state.get('current_stage')}').")
        raise HTTPException(status_code=403,
            detail="Only the deal owner (or an admin) can submit it to credit.")'''
    new_block = '''        if not state.get("stage_ok", True):
            raise HTTPException(status_code=400,
                detail=f"Cannot submit to credit — this product requires the deal "
                       f"to be at stage '{state.get('stage_required')}' "
                       f"(currently '{state.get('current_stage')}').")
        if state.get("committee_rejected"):
            raise HTTPException(status_code=400,
                detail="Cannot submit to credit — committee(s) rejected: "
                       + ", ".join(state["committee_rejected"])
                       + ". The deal returns to the owner (appeal or close).")
        if state.get("committee_pending"):
            raise HTTPException(status_code=400,
                detail="Cannot submit to credit — committee decision(s) outstanding: "
                       + ", ".join(state["committee_pending"]) + ".")
        if state.get("cr_required") and not state.get("cr_ok"):
            raise HTTPException(status_code=400,
                detail="Cannot submit to credit — the Credit Report (CR) must be completed first.")
        raise HTTPException(status_code=403,
            detail="Only the deal owner (or an admin) can submit it to credit.")'''
    if dry:
        print("  --dry-run: would add CR + committee gating."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = s.replace(ANCHOR, NEW, 1)
    if old_block in s:
        s = s.replace(old_block, new_block, 1)
    else:
        print("  NOTE: submit-endpoint block-reason anchor not found; state gating still active.")
    API.write_text(s, encoding="utf-8")
    print("  applied CR + committee gating. Restart API.")

if __name__ == "__main__":
    main()

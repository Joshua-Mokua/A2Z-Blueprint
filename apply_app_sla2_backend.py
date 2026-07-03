#!/usr/bin/env python3
"""scripts/apply_app_sla2_backend.py — C-SLA2: two-level SLA (stage/My + overall).

Adds a SECOND SLA clock to each application:
  - overall (existing): case age vs sla_target_days — the customer promise.
  - stage ("My SLA"): elapsed since the case entered its current stage/owner vs that
    stage's target_days (from the SLA step config). When Lilian is assigned, her clock
    starts then, against the credit-assessment step budget.

Requires a stage-entry timestamp. We stamp `stage_entered_at` when the case is
assigned (submit_to_credit) and fall back to last_updated for pre-existing cases.

Enhances _app_sla_status (added by C-SLA) to include a `stage` sub-status.
Stamps stage_entered_at in core.submit_to_credit.

SAFE: .pre_appsla2 backups on api.py + core.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
CORE = ROOT / "utils" / "core.py"
API_BAK = API.with_suffix(".py.pre_appsla2")
CORE_BAK = CORE.with_suffix(".py.pre_appsla2")

# --- 1. Enhance _app_sla_status to add the stage clock ---
# We replace the return dict of _app_sla_status with one that also computes stage SLA.
OLD_RETURN = '''    return {
        "state": state,
        "elapsed_business_days": elapsed,
        "target_days": target,
        "remaining_business_days": remaining,
        "overdue_business_days": overdue,
        "breached": overdue > 0,
    }


def _attach_sla_to_apps(apps: list) -> list:'''

NEW_RETURN = '''    overall = {
        "state": state,
        "elapsed_business_days": elapsed,
        "target_days": target,
        "remaining_business_days": remaining,
        "overdue_business_days": overdue,
        "breached": overdue > 0,
    }
    # --- Stage / "My" SLA: current stage clock vs that stage's target_days. ---
    stage = None
    try:
        smap = _sla_stage_step_map(cfg)
        # Map the app's status to an SLA step. Assigned/analysis -> credit_assessment.
        status_key = status
        step_key = smap.get(status_key)
        if not step_key and status_key in ("assigned", "info_requested"):
            step_key = "credit_assessment"
        if step_key:
            stage_target = _sla_step_target(cfg, step_key)
            stage_base = (app.get("stage_entered_at") or app.get("assigned_at")
                          or app.get("last_updated") or base_ts)
            if stage_target > 0 and stage_base:
                s_elapsed = _business_days_since(stage_base)
                s_overdue = max(0, s_elapsed - stage_target)
                s_remaining = stage_target - s_elapsed
                if s_overdue > 0:
                    s_state = "breached"
                elif s_remaining <= _sla_due_soon_days(cfg):
                    s_state = "due_soon"
                else:
                    s_state = "on_track"
                stage = {
                    "state": s_state,
                    "step_key": step_key,
                    "elapsed_business_days": s_elapsed,
                    "target_days": stage_target,
                    "remaining_business_days": s_remaining,
                    "overdue_business_days": s_overdue,
                    "breached": s_overdue > 0,
                }
    except Exception:
        stage = None
    # Return overall at top level (back-compat) + nested overall/stage.
    out = dict(overall)
    out["overall"] = overall
    out["stage"] = stage
    return out


def _attach_sla_to_apps(apps: list) -> list:'''

def patch_core(s):
    """Stamp stage_entered_at when a case is assigned (submit_to_credit)."""
    anchor = '''        updates = {"status": "assigned", "last_updated": datetime.now().date().isoformat()}
        if analyst_code:
            updates["analyst"] = {"code": analyst_code, "name": analyst_name}
        return self.update(app_id, updates)'''
    if anchor in s and "stage_entered_at" not in s.split("def submit_to_credit")[1].split("def record_decision")[0]:
        new = '''        _now = datetime.now().isoformat(timespec="seconds")
        updates = {"status": "assigned", "last_updated": datetime.now().date().isoformat()}
        if analyst_code:
            updates["analyst"] = {"code": analyst_code, "name": analyst_name}
            # C-SLA2: the analyst's stage clock starts now.
            updates["assigned_at"] = _now
            updates["stage_entered_at"] = _now
        return self.update(app_id, updates)'''
        return s.replace(anchor, new, 1), True
    return s, False

def revert():
    for bak, tgt in ((API_BAK, API), (CORE_BAK, CORE)):
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a = API.read_text(encoding="utf-8")
    c = CORE.read_text(encoding="utf-8")
    a_ch = OLD_RETURN in a and '"overall": overall' not in a
    c_new, c_ch = patch_core(c)
    print(f"  api.py (_app_sla_status stage clock): {'change' if a_ch else 'skip'}")
    print(f"  core.py (stamp stage_entered_at): {'change' if c_ch else 'skip'}")
    if not a_ch and OLD_RETURN not in a and '"overall": overall' not in a:
        print("  ERROR: _app_sla_status not found — apply C-SLA (app_sla.zip) first."); sys.exit(1)
    if dry:
        print("  --dry-run: nothing written."); return
    if a_ch:
        if not API_BAK.exists(): API_BAK.write_text(a, encoding="utf-8")
        API.write_text(a.replace(OLD_RETURN, NEW_RETURN, 1), encoding="utf-8")
    if c_ch:
        if not CORE_BAK.exists(): CORE_BAK.write_text(c, encoding="utf-8")
        CORE.write_text(c_new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""scripts/apply_committee_climb_backend.py — C1b: climb-ladder + MCC-mandatory.

Corrects committee routing per banking practice: cases CLIMB the ladder. A case
whose amount needs Board/Group must ENTER at the MCC (management_cc) and climb, with
each verdict captured before the next — unless an admin toggle disables it.

- Adds _committee_require_mcc() reading lms_config.require_mcc_before_higher (default True).
- Adds _committee_entry_tier(amount): the tier the case ENTERS at (MCC if final is
  higher and the rule is on), vs _suggest_committee_tier which is the FINAL authority.
- Enhances the committee-routing endpoint to return entry_tier + final_tier + require_mcc.
- Admin: POST /api/lms/committee/require-mcc {enabled} to toggle (config admin).

SAFE: .pre_climb backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_climb")
MARKER = "# === C1b: CLIMB LADDER + MCC-MANDATORY ==="

HELPERS = r'''

# === C1b: CLIMB LADDER + MCC-MANDATORY ===
def _committee_require_mcc() -> bool:
    """Admin toggle: cases needing Board/Group must pass MCC first. Default True."""
    try:
        from pathlib import Path as _Path
        p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if p.exists():
            import json as _json
            cfg = _json.loads(p.read_text(encoding="utf-8")) or {}
            v = cfg.get("require_mcc_before_higher")
            if v is not None:
                return bool(v)
    except Exception:
        pass
    return True


def _committee_mcc_tier() -> dict:
    """The MCC tier (key management_cc), or the middle tier as a fallback."""
    from utils.api_lms_committee_tiers import get_committee_tiers
    tiers = get_committee_tiers()
    for t in tiers:
        if str(t.get("key", "")).lower() in ("management_cc", "mcc"):
            return t
    # fallback: second tier if present
    return tiers[1] if len(tiers) > 1 else (tiers[0] if tiers else {})


def _committee_entry_tier(amount_kes: float) -> dict:
    """The tier the case ENTERS at. If the final authority is above MCC and the
    require-MCC rule is on, entry = MCC (the case then climbs). Otherwise entry =
    the final authority tier (small cases enter directly at their committee)."""
    final = _suggest_committee_tier(amount_kes)
    if not final:
        return {}
    if not _committee_require_mcc():
        return final
    mcc = _committee_mcc_tier()
    if not mcc:
        return final
    try:
        # if the final authority sits ABOVE MCC, the case must enter at MCC.
        if int(final.get("tier", 0)) > int(mcc.get("tier", 0)):
            return mcc
    except (TypeError, ValueError):
        pass
    return final
# === END C1b ===
'''

ADMIN_ENDPOINT = r'''

@router.post("/committee/require-mcc")
def lms_committee_set_require_mcc(
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(require_config_admin),
) -> Dict[str, Any]:
    """Admin toggle: require MCC before Board/Group. Config-admin gated."""
    enabled = bool((payload or {}).get("enabled", True))
    from pathlib import Path as _Path
    p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
    import json as _json
    cfg = {}
    try:
        if p.exists():
            cfg = _json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        cfg = {}
    cfg["require_mcc_before_higher"] = enabled
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    import os as _os
    _os.replace(str(tmp), str(p))
    return {"status": "saved", "require_mcc_before_higher": enabled}
'''

def patch(s):
    if MARKER in s:
        return s, False
    # ensure _Path is available (it is used elsewhere); append helpers + admin endpoint
    s = s.rstrip() + "\n" + HELPERS + "\n" + ADMIN_ENDPOINT + "\n"
    # enhance the routing return dict
    old_ret = '''    suggested = _suggest_committee_tier(amount)
    can_refer = is_manager(user) and is_valid_lms_transition(
        str(app.get("status", "")), "referred_to_committee")
    return {
        "tiers": get_committee_tiers(),
        "amount": amount,
        "suggested_tier": suggested.get("tier"),
        "suggested_name": suggested.get("name"),
        "can_refer": bool(can_refer),
        "current_status": app.get("status"),
    }'''
    new_ret = '''    final = _suggest_committee_tier(amount)
    entry = _committee_entry_tier(amount)
    can_refer = is_manager(user) and is_valid_lms_transition(
        str(app.get("status", "")), "referred_to_committee")
    return {
        "tiers": get_committee_tiers(),
        "amount": amount,
        # C1b: entry (where it starts) vs final (ultimate authority). The case
        # climbs from entry to final, capturing each verdict.
        "entry_tier": entry.get("tier"),
        "entry_name": entry.get("name"),
        "final_tier": final.get("tier"),
        "final_name": final.get("name"),
        "require_mcc": _committee_require_mcc(),
        "must_climb": bool(entry.get("tier") and final.get("tier")
                           and entry.get("tier") != final.get("tier")),
        # back-compat: suggested_* now points at the ENTRY tier (what to pre-select).
        "suggested_tier": entry.get("tier"),
        "suggested_name": entry.get("name"),
        "can_refer": bool(can_refer),
        "current_status": app.get("status"),
    }'''
    s = s.replace(old_ret, new_ret, 1)
    return s, True

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted from .pre_climb")
    else:
        print("  no .pre_climb backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    new, ch = patch(s)
    print(f"  api_lms_routes.py: {'change' if ch else 'skip (already applied)'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if ch:
        if not BAK.exists(): BAK.write_text(s, encoding="utf-8")
        ROUTES.write_text(new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

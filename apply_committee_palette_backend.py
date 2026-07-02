#!/usr/bin/env python3
"""scripts/apply_committee_palette_backend.py — 4b-1: committee palette config.

Introduces an admin-editable PALETTE of credit committees (BCC1, DCC, BCC2, BCC3,
GCC by default — all renamable/editable) stored at
lms_config.credit_workflow.committee_palette. Each committee:
  { code, name, chaired_by?, recording_mode(single|voting), voting_rule,
    amount_threshold_kes(0=none), members:[{name,role}] }

Endpoints (config-admin gated):
  GET  /api/admin/committee-palette         -> {committees:[...]}
  POST /api/admin/committee-palette         -> upsert one {committee:{...}} or {delete:code}
  POST /api/admin/committee-palette/seed     -> seed the 5 defaults if palette empty

Leaves the legacy single `committee` config untouched (backward compatible).
SAFE: .pre_cmtepalette backup on api.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_cmtepalette")
MARKER = "# === COMMITTEE PALETTE ENDPOINTS (4b-1) ==="

BLOCK = r'''

# === COMMITTEE PALETTE ENDPOINTS (4b-1) ===
_COMMITTEE_RECORDING_MODES = ("single", "voting")
_COMMITTEE_VOTING_RULES = ("SIMPLE_MAJORITY", "SUPERMAJORITY_TWO_THIRDS", "UNANIMOUS")

_DEFAULT_COMMITTEE_PALETTE = [
    {"code": "BCC1", "name": "Branch Credit Committee", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},
    {"code": "DCC", "name": "Head Office Department Credit Committee", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},
    {"code": "BCC2", "name": "Business Credit Committee", "chaired_by": "Managing Director",
     "recording_mode": "voting", "voting_rule": "SIMPLE_MAJORITY",
     "amount_threshold_kes": 0, "members": []},
    {"code": "BCC3", "name": "Board Credit Committee", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SUPERMAJORITY_TWO_THIRDS",
     "amount_threshold_kes": 1000000000, "members": []},
    {"code": "GCC", "name": "Group Credit Committee", "chaired_by": "",
     "recording_mode": "voting", "voting_rule": "SUPERMAJORITY_TWO_THIRDS",
     "amount_threshold_kes": 2000000000, "members": []},
]


def _read_committee_palette() -> list:
    cfg = _load_json("lms_config.json") or {}
    cw = cfg.get("credit_workflow", {}) if isinstance(cfg, dict) else {}
    pal = cw.get("committee_palette")
    return pal if isinstance(pal, list) else []


def _write_committee_palette(palette: list):
    from utils.core import _data_path  # noqa
    import json as _json
    p = ROOT / "data" / "lms_config.json"
    cfg = _load_json("lms_config.json") or {}
    cw = cfg.get("credit_workflow", {})
    if not isinstance(cw, dict):
        cw = {}
    cw["committee_palette"] = palette
    cfg["credit_workflow"] = cw
    # backup then write
    try:
        from datetime import datetime as _dt
        if p.exists():
            shutil.copyfile(p, p.with_suffix(f".pre_cmtepalette_{_dt.now():%Y%m%d-%H%M%S}.json"))
    except Exception:
        pass
    p.write_text(_json.dumps(cfg, indent=2), encoding="utf-8")


def _validate_committee(c: dict) -> tuple:
    if not isinstance(c, dict):
        return False, "committee must be an object"
    code = str(c.get("code", "")).strip()
    name = str(c.get("name", "")).strip()
    if not code:
        return False, "committee code is required"
    if not name:
        return False, "committee name is required"
    rm = str(c.get("recording_mode", "voting"))
    if rm not in _COMMITTEE_RECORDING_MODES:
        return False, f"recording_mode must be one of {_COMMITTEE_RECORDING_MODES}"
    vr = str(c.get("voting_rule", "SIMPLE_MAJORITY"))
    if vr not in _COMMITTEE_VOTING_RULES:
        return False, f"voting_rule must be one of {_COMMITTEE_VOTING_RULES}"
    try:
        float(c.get("amount_threshold_kes", 0) or 0)
    except (TypeError, ValueError):
        return False, "amount_threshold_kes must be a number"
    members = c.get("members", [])
    if not isinstance(members, list):
        return False, "members must be a list"
    return True, ""


@app.get("/api/admin/committee-palette", tags=["admin"])
def get_committee_palette(user: dict = Depends(get_current_user)):
    """The admin-editable palette of credit committees."""
    return {"committees": _read_committee_palette(),
            "recording_modes": list(_COMMITTEE_RECORDING_MODES),
            "voting_rules": list(_COMMITTEE_VOTING_RULES)}


@app.post("/api/admin/committee-palette/seed", tags=["admin"])
def seed_committee_palette(user: dict = Depends(require_config_admin)):
    """Seed the 5 default committees if the palette is empty."""
    pal = _read_committee_palette()
    if pal:
        return {"status": "exists", "committees": pal}
    _write_committee_palette(list(_DEFAULT_COMMITTEE_PALETTE))
    _audit("COMMITTEE_PALETTE_SEED", user, f"n={len(_DEFAULT_COMMITTEE_PALETTE)}")
    return {"status": "seeded", "committees": _DEFAULT_COMMITTEE_PALETTE}


@app.post("/api/admin/committee-palette", tags=["admin"])
def upsert_committee_palette(payload: dict = Body(default_factory=dict),
                             user: dict = Depends(require_config_admin)):
    """Add/edit a committee ({committee:{...}}) or delete one ({delete:code})."""
    palette = _read_committee_palette()
    if payload.get("delete"):
        code = str(payload.get("delete")).strip()
        palette = [c for c in palette if str(c.get("code")) != code]
        _write_committee_palette(palette)
        _audit("COMMITTEE_PALETTE_DELETE", user, f"code={code}")
        return {"status": "saved", "deleted": code, "committees": palette}
    c = payload.get("committee")
    ok, reason = _validate_committee(c if isinstance(c, dict) else {})
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    code = str(c.get("code")).strip()
    norm = {
        "code": code,
        "name": str(c.get("name")).strip(),
        "chaired_by": str(c.get("chaired_by", "") or ""),
        "recording_mode": str(c.get("recording_mode", "voting")),
        "voting_rule": str(c.get("voting_rule", "SIMPLE_MAJORITY")),
        "amount_threshold_kes": float(c.get("amount_threshold_kes", 0) or 0),
        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip()}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],
    }
    replaced = False
    for i, existing in enumerate(palette):
        if str(existing.get("code")) == code:
            palette[i] = norm; replaced = True; break
    if not replaced:
        palette.append(norm)
    _write_committee_palette(palette)
    _audit("COMMITTEE_PALETTE_UPSERT", user, f"code={code} replaced={replaced}")
    return {"status": "saved", "committee": norm, "committees": palette}
# === END COMMITTEE PALETTE ENDPOINTS ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_cmtepalette")
    else:
        print("  no .pre_cmtepalette backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print(f"  --dry-run: would append committee palette endpoints ({len(BLOCK)} chars)."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  appended committee palette endpoints. Restart API.")

if __name__ == "__main__":
    main()

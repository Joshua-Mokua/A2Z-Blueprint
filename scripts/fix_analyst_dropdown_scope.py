#!/usr/bin/env python3
"""scripts/fix_analyst_dropdown_scope.py — make my-analysts robust to unit divergence.

Root cause: Credit Analysts have Unit="Head Office", but the CCO scope walk filters
units:["Credit"], so get_visible_staff_codes excludes them -> empty dropdown.

Fix: credit-manager users (CCO, Senior Manager Credit Analysis, admin, MD) see the
FULL credit-analyst pool from the roster (assigning is a deliberate manager action).
Non-managers fall back to visible scope. Role match tightened to credit-analyst
roles only (excludes cyber/SOC/business analysts).

SAFE: .pre_ddscope backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_ddscope")

OLD = '_ANALYST_ROLE_HINTS = ("analyst",)  # substring match, case-insensitive\n\n\n@app.get("/api/lms/my-analysts", tags=["lms"])\ndef get_my_analysts(user: dict = Depends(get_current_user)):\n    """The assigning manager\'s assignable credit analysts \u2014 their visible staff\n    filtered to analyst-type roles. Powers the assign-analyst dropdown."""\n    from utils.api_pipeline_scope import get_visible_staff_codes, get_staff_roster\n    visible = get_visible_staff_codes(user)\n    roster = get_staff_roster()\n    analysts = []\n    try:\n        for _, row in roster.iterrows():\n            code = str(row.get("Staff Code", "") or "").strip()\n            role = str(row.get("Role", "") or "")\n            if not code or code not in visible:\n                continue\n            if any(h in role.lower() for h in _ANALYST_ROLE_HINTS):\n                analysts.append({\n                    "staff_code": code,\n                    "name": str(row.get("Staff Name", "") or ""),\n                    "role": role,\n                    "unit": str(row.get("Unit", "") or ""),\n                })\n    except Exception as exc:\n        logger.warning("my-analysts: roster scan failed: %s", exc)\n    analysts.sort(key=lambda a: a["name"])\n    return {"analysts": analysts, "count": len(analysts)}'

NEW = '''def _is_analyst_role(role: str) -> bool:
    """A credit-analyst role (excludes cyber/SOC/business analysts)."""
    r = str(role or "").lower()
    if "cyber" in r or "soc" in r or "business analyst" in r:
        return False
    return "credit analyst" in r or "credit analysis" in r


_CREDIT_MANAGER_HINTS = ("chief credit", "credit officer", "head of credit",
                         "credit analysis", "senior manager", "credit manager",
                         "managing director", "admin")


def _is_credit_manager(user: dict) -> bool:
    if bool(user.get("is_admin")):
        return True
    r = str(user.get("role", "") or "").lower()
    return any(h in r for h in _CREDIT_MANAGER_HINTS)


@app.get("/api/lms/my-analysts", tags=["lms"])
def get_my_analysts(user: dict = Depends(get_current_user)):
    """Assignable credit analysts for the assign-analyst dropdown. Credit managers
    see the FULL analyst pool (the scope walk's unit filter wrongly excludes
    analysts whose Unit diverges from "Credit" \u2014 e.g. Unit="Head Office").
    Non-managers fall back to their visible scope."""
    from utils.api_pipeline_scope import get_visible_staff_codes, get_staff_roster
    roster = get_staff_roster()
    manager = _is_credit_manager(user)
    visible = set() if manager else get_visible_staff_codes(user)
    analysts = []
    try:
        for _, row in roster.iterrows():
            code = str(row.get("Staff Code", "") or "").strip()
            role = str(row.get("Role", "") or "")
            if not code:
                continue
            if not manager and code not in visible:
                continue
            if _is_analyst_role(role):
                analysts.append({
                    "staff_code": code,
                    "name": str(row.get("Staff Name", "") or ""),
                    "role": role,
                    "unit": str(row.get("Unit", "") or ""),
                })
    except Exception as exc:
        logger.warning("my-analysts: roster scan failed: %s", exc)
    analysts.sort(key=lambda a: a["name"])
    return {"analysts": analysts, "count": len(analysts)}'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_ddscope")
    else:
        print("  no .pre_ddscope backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if "_is_credit_manager" in s:
        print("  already applied."); return
    if OLD not in s:
        print("  ERROR: original my-analysts endpoint not found."); sys.exit(1)
    if dry:
        print("  --dry-run: would make my-analysts manager-aware + tighten role match."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.replace(OLD, NEW, 1), encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

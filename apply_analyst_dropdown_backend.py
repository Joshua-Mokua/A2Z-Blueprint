#!/usr/bin/env python3
"""scripts/apply_analyst_dropdown_backend.py — analyst dropdown for assignment.

GET /api/lms/my-analysts — the assigning manager's assignable credit analysts
(their visible staff filtered to analyst-type roles), so the assign panel offers
a dropdown instead of free-text code/name entry.

Roles treated as analysts: any whose role contains "Analyst" (Credit Analyst,
Senior Credit Analyst, etc.) — configurable via _ANALYST_ROLE_HINTS.

SAFE: .pre_analystdd backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_analystdd")
MARKER = "# === MY ANALYSTS DROPDOWN (assignment) ==="

BLOCK = r'''

# === MY ANALYSTS DROPDOWN (assignment) ===
_ANALYST_ROLE_HINTS = ("analyst",)  # substring match, case-insensitive


@app.get("/api/lms/my-analysts", tags=["lms"])
def get_my_analysts(user: dict = Depends(get_current_user)):
    """The assigning manager's assignable credit analysts — their visible staff
    filtered to analyst-type roles. Powers the assign-analyst dropdown."""
    from utils.api_pipeline_scope import get_visible_staff_codes, get_staff_roster
    visible = get_visible_staff_codes(user)
    roster = get_staff_roster()
    analysts = []
    try:
        for _, row in roster.iterrows():
            code = str(row.get("Staff Code", "") or "").strip()
            role = str(row.get("Role", "") or "")
            if not code or code not in visible:
                continue
            if any(h in role.lower() for h in _ANALYST_ROLE_HINTS):
                analysts.append({
                    "staff_code": code,
                    "name": str(row.get("Staff Name", "") or ""),
                    "role": role,
                    "unit": str(row.get("Unit", "") or ""),
                })
    except Exception as exc:
        logger.warning("my-analysts: roster scan failed: %s", exc)
    analysts.sort(key=lambda a: a["name"])
    return {"analysts": analysts, "count": len(analysts)}
# === END MY ANALYSTS DROPDOWN ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_analystdd")
    else:
        print("  no .pre_analystdd backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print(f"  --dry-run: would append my-analysts endpoint ({len(BLOCK)} chars)."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  appended my-analysts endpoint. Restart API.")

if __name__ == "__main__":
    main()

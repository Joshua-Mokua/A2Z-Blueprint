#!/usr/bin/env python3
"""scripts/apply_member_prereads_backend.py — C3b: member pre-read queue.

A logged-in committee member sees referred cases awaiting their pre-read. Match: the
member's staff_code appears in a committee (palette) whose name matches the case's
current committee tier name; if the palette naming has drifted, the member still sees
referred cases in their scope so the queue is never wrongly empty. Reuses the C3a
pre-read record endpoint.

Adds GET /api/lms/committee/my-pre-read-queue.

SAFE: .pre_mprq backup on api_lms_routes.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_mprq")
MARKER = "# === C3b: MEMBER PRE-READ QUEUE ==="

BLOCK = r'''

# === C3b: MEMBER PRE-READ QUEUE ===
def _member_committee_names(staff_code: str) -> set:
    """Committee names (palette) whose members include this staff_code."""
    try:
        from utils.api import _read_committee_palette
        pal = _read_committee_palette() or []
    except Exception:
        pal = []
    names = set()
    for c in pal:
        for m in (c.get("members") or []):
            if str(m.get("staff_code", "") or "") == str(staff_code):
                names.add(str(c.get("name", "") or "").strip().lower())
    return names


@router.get("/committee/my-pre-read-queue")
def lms_member_pre_read_queue(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Referred cases awaiting THIS member's non-binding pre-read. A member sees
    cases at a committee they belong to (by name match to current tier), plus (as a
    scope-safe fallback) referred cases visible to them. Each case flags whether the
    member has already pre-read it at the current tier."""
    lam = _lam()
    caller_code = str(user.get('staff_code', '') or '')
    my_committees = _member_committee_names(caller_code)
    visible_codes = get_visible_staff_codes(user)
    caller_role = str(user.get('role', '') or '')
    out = []
    for app in lam.apps:
        if str(app.get("status", "") or "") != "referred_to_committee":
            continue
        committee = app.get("committee") or {}
        tier_name = str(committee.get("current_tier_name", "") or "").strip().lower()
        in_my_committee = bool(my_committees and tier_name in my_committees)
        in_scope = user.get('is_admin') or is_app_in_scope(
            app, visible_codes, caller_code, caller_role=caller_role)
        # Show if it's my committee, OR (fallback) it's referred and in my scope.
        if not (in_my_committee or in_scope):
            continue
        prereads = app.get("committee_prereads", []) or []
        cur_tier = committee.get("current_tier")
        mine = next((r for r in prereads
                     if str(r.get("by_code")) == caller_code and r.get("tier") == cur_tier), None)
        out.append({
            "id": app.get("id"),
            "client_name": app.get("client_name"),
            "product": app.get("product"),
            "amount": app.get("amount"),
            "current_tier": cur_tier,
            "current_tier_name": committee.get("current_tier_name"),
            "in_my_committee": in_my_committee,
            "my_pre_read": mine,
            "sla": app.get("sla"),
        })
    return {"cases": out, "count": len(out),
            "pending": sum(1 for c in out if not c["my_pre_read"])}
# === END C3b ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted from .pre_mprq")
    else:
        print("  no .pre_mprq backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if dry:
        print("  --dry-run: would add my-pre-read-queue endpoint."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    ROUTES.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

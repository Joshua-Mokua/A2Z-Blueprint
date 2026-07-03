#!/usr/bin/env python3
"""scripts/apply_committee_members_backend.py — C3a: committee members + pre-read.

Committee members become real users (staff_code) so they can be notified + record
an independent NON-BINDING pre-read on a referred case (leaning_approve /
leaning_decline / questions + note). Binding vote still happens when the MD convenes.

- upsert_committee_palette: preserve staff_code on members.
- POST /applications/{id}/committee/pre-read {view, note?} — a member records their
  non-binding view. Stored on app['committee_prereads'] keyed by member.
- GET  /applications/{id}/committee/pre-reads — the collected pre-reads.

SAFE: .pre_members backups (api.py + api_lms_routes.py). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
ROUTES = ROOT / "utils" / "api_lms_routes.py"
API_BAK = API.with_suffix(".py.pre_members")
ROUTES_BAK = ROUTES.with_suffix(".py.pre_members")
ROUTES_MARKER = "# === C3a: COMMITTEE PRE-READ ==="

PREREAD_BLOCK = r'''

# === C3a: COMMITTEE PRE-READ ===
_PREREAD_VIEWS = ("leaning_approve", "leaning_decline", "questions")

@router.post("/applications/{app_id}/committee/pre-read",
             response_model=LoanAppMutationResponse)
def lms_committee_pre_read(
    app_id: str,
    payload: Dict[str, Any] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """A committee member records an independent, NON-BINDING pre-read on a case
    that is before the committee. This informs the convened meeting; it is not the
    binding vote. One pre-read per member (re-submitting updates it)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    if str(app.get("status", "") or "") != "referred_to_committee":
        raise HTTPException(status_code=400, detail="Case is not before the committee")
    p = payload or {}
    view = str(p.get("view", "") or "").lower()
    if view not in _PREREAD_VIEWS:
        raise HTTPException(status_code=400,
                            detail=f"view must be one of {list(_PREREAD_VIEWS)}")
    caller_code = str(user.get('staff_code', '') or '')
    from datetime import datetime as _dt
    prereads = list(app.get("committee_prereads", []) or [])
    entry = {
        "by_code": caller_code,
        "by_name": str(user.get('full_name', '') or user.get('username', '') or ''),
        "view": view,
        "note": str(p.get("note", "") or ""),
        "at": _dt.now().isoformat(timespec="seconds"),
        "tier": (app.get("committee") or {}).get("current_tier"),
    }
    # replace this member's prior pre-read at the current tier, if any.
    prereads = [r for r in prereads
                if not (str(r.get("by_code")) == caller_code and r.get("tier") == entry["tier"])]
    prereads.append(entry)
    lam.update(app_id, {"committee_prereads": prereads})
    audit_log("LMS_COMMITTEE_PREREAD", str(user.get('username', '') or ''),
              f"{app_id}|{view}")
    return {"application": lam.get(app_id), "status": "pre_read_recorded"}


@router.get("/applications/{app_id}/committee/pre-reads")
def lms_committee_pre_reads(
    app_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """The collected pre-reads for a case (for the Chief / MD to see leanings)."""
    lam = _lam()
    app = lam.get(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found")
    prereads = app.get("committee_prereads", []) or []
    cur_tier = (app.get("committee") or {}).get("current_tier")
    at_tier = [r for r in prereads if r.get("tier") == cur_tier]
    tally = {v: sum(1 for r in at_tier if r.get("view") == v) for v in _PREREAD_VIEWS}
    return {"pre_reads": at_tier, "all": prereads, "tally": tally,
            "current_tier": cur_tier}
# === END C3a ===
'''

def patch_api(s):
    """Preserve staff_code in the member normalisation of upsert_committee_palette."""
    anchor = '''        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip()}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],'''
    if anchor in s:
        new = '''        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip(),
             "staff_code": str(m.get("staff_code", "") or "").strip()}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],'''
        return s.replace(anchor, new, 1), True
    return s, False

def revert():
    for bak, tgt in ((API_BAK, API), (ROUTES_BAK, ROUTES)):
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a = API.read_text(encoding="utf-8")
    r = ROUTES.read_text(encoding="utf-8")
    a_new, a_ch = patch_api(a)
    r_ch = ROUTES_MARKER not in r
    print(f"  api.py (member staff_code): {'change' if a_ch else 'skip'}")
    print(f"  api_lms_routes.py (pre-read endpoints): {'change' if r_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if a_ch:
        if not API_BAK.exists(): API_BAK.write_text(a, encoding="utf-8")
        API.write_text(a_new, encoding="utf-8")
    if r_ch:
        if not ROUTES_BAK.exists(): ROUTES_BAK.write_text(r, encoding="utf-8")
        ROUTES.write_text(r.rstrip() + "\n" + PREREAD_BLOCK + "\n", encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

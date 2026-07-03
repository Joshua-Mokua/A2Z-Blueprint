#!/usr/bin/env python3
"""scripts/apply_exco_funnel_backend.py — C3c: EXCO full-funnel visibility grant.

An admin can grant a committee member (intended for EXCO-level members serving with
the MD) FULL pipeline+credit funnel visibility for forward planning — the same broad
view the MD gets. Granted per-member via a full_funnel flag on the committee member.

- upsert_committee_palette: preserve full_funnel on members.
- get_visible_staff_codes: if the caller is a granted full-funnel member, return the
  FULL roster (same outcome as MD/admin), so they see the whole funnel.

SAFE: .pre_exco backups (api.py + api_pipeline_scope.py). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
SCOPE = ROOT / "utils" / "api_pipeline_scope.py"
API_BAK = API.with_suffix(".py.pre_exco")
SCOPE_BAK = SCOPE.with_suffix(".py.pre_exco")

def patch_api(s):
    """Preserve full_funnel on committee members in the palette upsert."""
    anchor = '''        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip(),
             "staff_code": str(m.get("staff_code", "") or "").strip()}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],'''
    if anchor in s:
        new = '''        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip(),
             "staff_code": str(m.get("staff_code", "") or "").strip(),
             "full_funnel": bool(m.get("full_funnel", False))}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],'''
        return s.replace(anchor, new, 1), True
    return s, False

def patch_scope(s):
    """Inject a full-funnel-member check into get_visible_staff_codes."""
    if "_is_exco_full_funnel_member" in s:
        return s, False
    # add the helper + call it at the top of get_visible_staff_codes.
    helper = '''
def _is_exco_full_funnel_member(user_data: dict) -> bool:
    """C3c: True if this user's staff_code is a committee member granted the
    full_funnel flag — an EXCO-level member the admin has elevated to see the whole
    pipeline+credit funnel for planning (same broad view as the MD)."""
    code = str(user_data.get("staff_code", "") or "")
    if not code:
        return False
    try:
        from utils.api import _read_committee_palette
        for c in (_read_committee_palette() or []):
            for m in (c.get("members") or []):
                if str(m.get("staff_code", "") or "") == code and bool(m.get("full_funnel", False)):
                    return True
    except Exception:
        return False
    return False


'''
    # insert the helper just before def get_visible_staff_codes
    s = s.replace("def get_visible_staff_codes(user_data: dict) -> Set[str]:",
                  helper + "def get_visible_staff_codes(user_data: dict) -> Set[str]:", 1)
    # inject the full-funnel short-circuit: after roster is fetched, if granted,
    # return ALL roster staff codes.
    anchor = '''    roster = get_staff_roster()
    if roster is None or len(roster) == 0:
        return visible'''
    new = '''    roster = get_staff_roster()
    if roster is None or len(roster) == 0:
        return visible

    # C3c: a granted EXCO full-funnel member sees the whole roster (like the MD).
    if _is_exco_full_funnel_member(user_data) and "Staff Code" in roster.columns:
        return {str(c) for c in roster["Staff Code"].tolist() if c} | visible'''
    s = s.replace(anchor, new, 1)
    return s, True

def revert():
    for bak, tgt in ((API_BAK, API), (SCOPE_BAK, SCOPE)):
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a = API.read_text(encoding="utf-8")
    sc = SCOPE.read_text(encoding="utf-8")
    a_new, a_ch = patch_api(a)
    sc_new, sc_ch = patch_scope(sc)
    print(f"  api.py (member full_funnel): {'change' if a_ch else 'skip'}")
    print(f"  api_pipeline_scope.py (full-funnel scope): {'change' if sc_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if a_ch:
        if not API_BAK.exists(): API_BAK.write_text(a, encoding="utf-8")
        API.write_text(a_new, encoding="utf-8")
    if sc_ch:
        if not SCOPE_BAK.exists(): SCOPE_BAK.write_text(sc, encoding="utf-8")
        SCOPE.write_text(sc_new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""scripts/apply_staff_admin_gate_fix.py — fix the Staff Admin 403.

The staff-admin endpoints used require_admin (strict exact-match role == "admin"
or "director"), which 403s the MD / CEO whose role is the full title
"Chief Executive & Managing Director". The Configuration panel already uses
require_config_admin (lenient substring match: admin/director/chief/managing),
which correctly admits the executive tier. Staff administration is the same
access tier, so switch the 5 staff endpoints to require_config_admin.

Destructive endpoints (clear_cache, fx_upsert_rate) stay on strict require_admin.

SAFE: backs up utils/api.py (.pre_gatefix). Idempotent. --revert restores it.
Run:  python scripts\\apply_staff_admin_gate_fix.py [--dry-run] [--revert]
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_gatefix")

# Only the 5 staff-admin endpoint guard lines. We match the full def line to be
# precise and avoid touching clear_cache / fx_upsert_rate.
TARGETS = [
    ('def get_admin_staff(user: dict = Depends(require_admin)):',
     'def get_admin_staff(user: dict = Depends(require_config_admin)):'),
    ('def create_admin_staff(payload: _StaffCreate, user: dict = Depends(require_admin)):',
     'def create_admin_staff(payload: _StaffCreate, user: dict = Depends(require_config_admin)):'),
    ('                       user: dict = Depends(require_admin)):',
     '                       user: dict = Depends(require_config_admin)):'),
    ('def deactivate_admin_staff(username: str, user: dict = Depends(require_admin)):',
     'def deactivate_admin_staff(username: str, user: dict = Depends(require_config_admin)):'),
    ('def reactivate_admin_staff(username: str, user: dict = Depends(require_admin)):',
     'def reactivate_admin_staff(username: str, user: dict = Depends(require_config_admin)):'),
]


def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_gatefix")
    else:
        print("  no .pre_gatefix backup found")


def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    changes = []
    for old, new in TARGETS:
        if new in s and old not in s:
            changes.append((old, "already applied")); continue
        n = s.count(old)
        if n != 1:
            print(f"  ERROR: anchor not unique ({n}x): {old[:60]}"); sys.exit(1)
        changes.append((old, "will change"))
    print(f"  {sum(1 for _,st in changes if st=='will change')} endpoint(s) to switch to require_config_admin")
    for old, st in changes:
        print(f"      [{st}] {old.strip()[:70]}")
    if dry:
        print("  --dry-run: nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    for old, new in TARGETS:
        if old in s:
            s = s.replace(old, new)
    API.write_text(s, encoding="utf-8")
    print("  applied. Restart the API for the new gate to take effect.")


if __name__ == "__main__":
    main()

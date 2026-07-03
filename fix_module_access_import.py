#!/usr/bin/env python3
"""scripts/fix_module_access_import.py — add the missing fetchAccessModules /
AccessModule imports to StaffAdmin.tsx (TSC TS2304 fix).

The module-access React patch used the component's exports but the import
injection anchored on an upload-UI line that isn't present yet, so the import
was skipped. This adds them directly after reactivateAdminStaff.

SAFE: backs up the file (.pre_modimport). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "StaffAdmin.tsx"
BAK = PAGE.with_suffix(".tsx.pre_modimport")

def revert():
    if BAK.exists():
        shutil.copy2(BAK, PAGE); BAK.unlink(); print("  reverted StaffAdmin.tsx")
    else:
        print("  no .pre_modimport backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    s = PAGE.read_text(encoding="utf-8")
    if "fetchAccessModules" in s and "  fetchAccessModules," in s:
        print("  import already present — nothing to do."); return
    anchor = "  reactivateAdminStaff,\n"
    if anchor not in s:
        print("  ERROR: anchor 'reactivateAdminStaff,' not found"); sys.exit(1)
    add = "  reactivateAdminStaff,\n  fetchAccessModules,\n  type AccessModule,\n"
    if "--dry-run" in sys.argv:
        print("  --dry-run: would add fetchAccessModules + AccessModule imports."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = s.replace(anchor, add, 1)
    PAGE.write_text(s, encoding="utf-8")
    print("  added fetchAccessModules + AccessModule imports.")

if __name__ == "__main__":
    main()

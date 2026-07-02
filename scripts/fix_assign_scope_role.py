#!/usr/bin/env python3
"""scripts/fix_assign_scope_role.py — fix assign/decision 403 for credit managers.

Root cause: is_app_in_scope has a pool-visibility branch that lets credit roles
(CCO, credit manager, etc.) act on pool apps — but it only runs when caller_role
is passed. The LIST/detail endpoints pass caller_role; the ASSIGN and DECISION
endpoints do NOT, so a CCO can SEE app LMS00731 in the list but gets 403 on assign
(the pool branch is skipped, and unit-divergence means rm_code isn't in the
CCO's Credit-unit-filtered visible set).

Fix: pass caller_role in the assign + decision scope checks, matching the list
path. This makes the three defense-in-depth gates consistent.

SAFE: .pre_assignrole backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "utils" / "api_lms_routes.py"
BAK = ROUTES.with_suffix(".py.pre_assignrole")

OLD = "    if not user.get('is_admin') and not is_app_in_scope(app, visible_codes, caller_code):"
NEW = ("    if not user.get('is_admin') and not is_app_in_scope(\n"
       "            app, visible_codes, caller_code,\n"
       "            caller_role=str(user.get('role', '') or '')):")

def revert():
    if BAK.exists():
        shutil.copy2(BAK, ROUTES); BAK.unlink(); print("  reverted api_lms_routes.py from .pre_assignrole")
    else:
        print("  no .pre_assignrole backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = ROUTES.read_text(encoding="utf-8")
    n = s.count(OLD)
    print(f"  found {n} scope-check call(s) missing caller_role (expect 2: assign + decision)")
    if n == 0:
        print("  nothing to fix (already patched or anchor changed)."); return
    if dry:
        print("  --dry-run: would add caller_role to those calls."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s = s.replace(OLD, NEW)  # replace ALL occurrences (assign + decision)
    ROUTES.write_text(s, encoding="utf-8")
    print(f"  patched {n} call(s). Restart API.")

if __name__ == "__main__":
    main()

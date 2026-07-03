#!/usr/bin/env python3
"""scripts/apply_dept_scope_backend.py — CA3a: department-role visibility for
credit-admin cases.

FIX (CA3-G3): credit-admin cases are scoped by the originating RM's cascade, so the
CREDIT/LEGAL DEPARTMENT roles (Chief Credit, Credit Admin officers, Legal chief/
officers, credit managers) — who own credit admin — could not see the cases at all
(the RM sits in Retail/Commercial, never in their cascade). This widens credit-admin
case visibility so department roles see cases department-wide (like admins already
do). RM-cascade behaviour is unchanged; this is purely additive.

- api_credit_admin_scope.py: _is_credit_admin_department_role(user); both
  filter_cases_by_visible_codes and is_case_in_scope accept an optional `user` and
  return all/true for department roles.
- api_credit_admin_routes.py + permissions: pass `user` through so the widening
  applies to list, detail, and can_view.

SAFE: .pre_deptscope backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ROOT / "utils" / "api_credit_admin_scope.py"
ROUTES = ROOT / "utils" / "api_credit_admin_routes.py"
PERMS = ROOT / "utils" / "api_credit_admin_permissions.py"
SCOPE_BAK = SCOPE.with_suffix(".py.pre_deptscope")
ROUTES_BAK = ROUTES.with_suffix(".py.pre_deptscope")
PERMS_BAK = PERMS.with_suffix(".py.pre_deptscope")

def patch_scope(s):
    if "_is_credit_admin_department_role" in s:
        return s, False
    helper = '''

def _is_credit_admin_department_role(user: Dict[str, Any]) -> bool:
    """CA3a: the CREDIT/LEGAL department roles that own credit admin and must see
    its cases department-wide (not only via the originating RM's cascade). Matches
    the real staff-register role spellings (Credit Admin Officer, Manager- Legal,
    Legal Officer, Chief Credit Officer, etc.) by substring."""
    if not user:
        return False
    if user.get("is_admin"):
        return True
    role = str(user.get("role", "") or "").lower()
    if not role:
        return False
    # credit-admin / credit-oversight
    if "chief credit" in role or "credit admin" in role or "credit administrat" in role:
        return True
    if "credit monitoring" in role or "credit reporting" in role or "credit analysis" in role:
        return True
    # legal (charging)
    if "legal" in role:
        return True
    return False
'''
    # insert helper after the module docstring / imports (before filter fn)
    s = s.replace("def filter_cases_by_visible_codes(",
                  helper.lstrip("\n") + "\n\ndef filter_cases_by_visible_codes(", 1)
    # widen filter to accept user
    s = s.replace(
        "def filter_cases_by_visible_codes(\n    cases: List[Dict[str, Any]],\n    visible_codes: Set[str],\n) -> List[Dict[str, Any]]:",
        "def filter_cases_by_visible_codes(\n    cases: List[Dict[str, Any]],\n    visible_codes: Set[str],\n    user: Optional[Dict[str, Any]] = None,\n) -> List[Dict[str, Any]]:")
    s = s.replace(
        "    return [\n        c for c in cases\n        if str(c.get('rm_code', '') or '') in visible_codes\n    ]",
        "    if user is not None and _is_credit_admin_department_role(user):\n"
        "        return list(cases)  # CA3a: department roles see all credit-admin cases\n"
        "    return [\n        c for c in cases\n        if str(c.get('rm_code', '') or '') in visible_codes\n    ]")
    # widen is_case_in_scope to accept user
    s = s.replace(
        "def is_case_in_scope(\n    case: Dict[str, Any],\n    visible_codes: Set[str],\n) -> bool:",
        "def is_case_in_scope(\n    case: Dict[str, Any],\n    visible_codes: Set[str],\n    user: Optional[Dict[str, Any]] = None,\n) -> bool:")
    s = s.replace(
        '''    if not case:
        return False
    rm_code = str(case.get('rm_code', '') or '')
    return bool(rm_code) and (rm_code in visible_codes)''',
        '''    if not case:
        return False
    if user is not None and _is_credit_admin_department_role(user):
        return True  # CA3a: department roles see all credit-admin cases
    rm_code = str(case.get('rm_code', '') or '')
    return bool(rm_code) and (rm_code in visible_codes)''')
    # ensure Optional imported
    if "Optional" not in s.split("\n")[0:40].__str__():
        s = s.replace("from typing import List, Dict, Any, Set",
                      "from typing import List, Dict, Any, Set, Optional", 1)
    return s, True

def patch_routes(s):
    if "filter_cases_by_visible_codes(cam.cases, visible_codes, user)" in s:
        return s, False
    ch = False
    if "cases = filter_cases_by_visible_codes(cam.cases, visible_codes)" in s:
        s = s.replace("cases = filter_cases_by_visible_codes(cam.cases, visible_codes)",
                      "cases = filter_cases_by_visible_codes(cam.cases, visible_codes, user)", 1); ch = True
    # pass user into is_case_in_scope calls in this file
    s2 = s.replace("is_case_in_scope(case, visible_codes)", "is_case_in_scope(case, visible_codes, user)")
    if s2 != s:
        s = s2; ch = True
    return s, ch

def patch_perms(s):
    if "is_case_in_scope(case, visible_codes, user)" in s:
        return s, False
    if "in_scope = is_case_in_scope(case, visible_codes)" in s:
        return s.replace("in_scope = is_case_in_scope(case, visible_codes)",
                         "in_scope = is_case_in_scope(case, visible_codes, user)", 1), True
    return s, False

def revert():
    for bak, tgt in ((SCOPE_BAK, SCOPE), (ROUTES_BAK, ROUTES), (PERMS_BAK, PERMS)):
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    sc = SCOPE.read_text(encoding="utf-8")
    r = ROUTES.read_text(encoding="utf-8")
    pm = PERMS.read_text(encoding="utf-8")
    sc_new, sc_ch = patch_scope(sc)
    r_new, r_ch = patch_routes(r)
    pm_new, pm_ch = patch_perms(pm)
    print(f"  api_credit_admin_scope.py: {'change' if sc_ch else 'skip'}")
    print(f"  api_credit_admin_routes.py: {'change' if r_ch else 'skip'}")
    print(f"  api_credit_admin_permissions.py: {'change' if pm_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if sc_ch:
        if not SCOPE_BAK.exists(): SCOPE_BAK.write_text(sc, encoding="utf-8")
        SCOPE.write_text(sc_new, encoding="utf-8")
    if r_ch:
        if not ROUTES_BAK.exists(): ROUTES_BAK.write_text(r, encoding="utf-8")
        ROUTES.write_text(r_new, encoding="utf-8")
    if pm_ch:
        if not PERMS_BAK.exists(): PERMS_BAK.write_text(pm, encoding="utf-8")
        PERMS.write_text(pm_new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()

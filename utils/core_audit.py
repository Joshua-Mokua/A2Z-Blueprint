"""utils.core_audit — audit logging, access control, and approval helpers.

This module is the FIRST step in splitting utils/core.py (6,672 lines) into
focused submodules. For now, it re-exports symbols from utils.core so
existing imports keep working unchanged. Future sessions will move the
implementations physically into this module under the protection of the
v5.20 test suite.

Migration path for callers:
    OLD:  from utils.core import audit_log
    NEW:  from utils.core_audit import audit_log

The G14 audit gate (added in v5.21) tracks the percentage of pages using
the new import paths. It does NOT fail the build for old imports — those
remain valid until utils.core is fully decomposed.

Symbols re-exported:
    Logging          : audit_log
    Approvals        : requires_dual_approval, submit_for_approval,
                       get_pending_approvals
    Department       : get_user_department, is_dept_super_user,
                       is_ict_admin, get_dept_modules
    Access           : check_access, check_page_access,
                       get_visible_staff, tab_visible_cascade,
                       fix_view_all_permissions
    Password helpers : _hash_password
"""
from __future__ import annotations

from utils.core import (
    audit_log,
    requires_dual_approval,
    submit_for_approval,
    get_pending_approvals,
    get_user_department,
    is_dept_super_user,
    is_ict_admin,
    get_dept_modules,
    check_access,
    check_page_access,
    get_visible_staff,
    tab_visible_cascade,
    fix_view_all_permissions,
    _hash_password,
)

__all__ = [
    "audit_log",
    "requires_dual_approval",
    "submit_for_approval",
    "get_pending_approvals",
    "get_user_department",
    "is_dept_super_user",
    "is_ict_admin",
    "get_dept_modules",
    "check_access",
    "check_page_access",
    "get_visible_staff",
    "tab_visible_cascade",
    "fix_view_all_permissions",
    "_hash_password",
]

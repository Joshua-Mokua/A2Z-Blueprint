"""Auth & RBAC framework — single source of truth for access control.

Per Joshua doctrine Phase 3 EC4: Authentication & RBAC.
Every page must call `require_access(role_or_module)` to gate visibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

DATA_DIR = Path(__file__).parent.parent / "data"


def _load_users() -> Dict[str, Any]:
    try:
        return json.loads((DATA_DIR / "users.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_current_user() -> Optional[Dict[str, Any]]:
    """Return the currently logged-in user from Streamlit session_state."""
    try:
        import streamlit as st
        return st.session_state.get("user")
    except Exception:
        return None


def is_admin(user: Optional[Dict[str, Any]] = None) -> bool:
    user = user or get_current_user() or {}
    return bool(user.get("is_admin") or user.get("is_ict_admin"))


def has_access(module: str, user: Optional[Dict[str, Any]] = None) -> bool:
    """Check if user has access to a module/page."""
    user = user or get_current_user() or {}
    if is_admin(user) or user.get("can_view_all"):
        return True
    accessible = user.get("accessible_modules", []) or []
    if "all" in accessible:
        return True
    hidden = user.get("hidden_modules", []) or []
    if module in hidden:
        return False
    if accessible and module not in accessible:
        return False
    return True


def require_access(module: str, user: Optional[Dict[str, Any]] = None) -> bool:
    """Gate a page — blocks render if user lacks access.

    Returns True if access granted (caller should continue rendering).
    Returns False if access denied (caller should st.stop or return).
    """
    try:
        import streamlit as st
    except Exception:
        return True  # outside streamlit context, allow
    user = user or get_current_user()
    if not user:
        st.warning("Please log in to access this page.")
        return False
    if not has_access(module, user):
        st.error(f"Access denied: you don't have permission for '{module}'.")
        st.info(f"Logged in as: {user.get('full_name','?')} ({user.get('role','?')})")
        return False
    return True


# Convenience aliases for legacy code
check_access = has_access

# v10.498 Stage C Batch 1b — OI-1 resolved per ROLE_GOVERNANCE.md (CGR1).
# The previous alias `require_role = require_access` was misleading
# (the name suggested role-tier RBAC; the implementation was module-access).
# Renamed to `require_module_access`. No callsites used the old name
# (verified by findstr on 2026-05-22, zero matches in pages/ or utils/),
# so the deprecation alias was unnecessary. Removed cleanly.
#
# Future enterprise JWT RBAC factory (`require_role` taking a list of
# role tiers) is ASPIRATIONAL per GOVERNANCE_REALITY_INDEX.md; when it
# ships in utils/auth_jwt.py, this module won't collide because the
# Streamlit symbol no longer uses that name.
require_module_access = require_access

__all__ = ["get_current_user", "is_admin", "has_access",
           "require_access", "check_access",
           "require_module_access"]
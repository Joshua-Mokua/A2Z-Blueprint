"""pages/_access.py — Central access guard. Import at top of every page.

v10.200: dotted-path access support added. require_access() auto-detects
the form by checking whether the argument contains a '.' character:

    require_access("treasury")          # legacy flat form (works as before)
    require_access("treasury_alm.alm")  # new dotted form (v10.200+)

Dotted form resolution chain (most-specific to fallback):
    1. Explicit grant for "treasury_alm.alm" in user.accessible_modules_dotted
    2. Wildcard grant for "treasury_alm.*" in user.accessible_modules_dotted
    3. Department grant for "treasury_alm" in user.accessible_modules_dotted
    4. Legacy check_access() using current_module_key from manifest

Backward compatibility:
    - Existing pages calling require_access("treasury") work unchanged.
    - Users without accessible_modules_dotted in their record fall through
      directly to legacy check_access — same behavior as v10.199.
    - The dotted form is opt-in. Pages can migrate at their own pace.

Per master prompt v3.62 line 957: "prefer extending existing patterns
over inventing new ones." This refactor extends the existing access
mechanism rather than replacing it.
"""
import streamlit as st
import pandas as pd
from utils.core_audit import check_access, get_visible_staff, tab_visible_cascade
from utils.core import MODULE_ACCESS


def check_access_dotted(user_data: dict, dotted_path: str) -> tuple:
    """v10.200 — Dotted-path access resolution.

    Resolution order:
      1. Admin or can_view_all → True
      2. Explicit dotted grant (e.g. user has "treasury_alm.alm")
      3. Wildcard grant (e.g. user has "treasury_alm.*")
      4. Department grant (e.g. user has "treasury_alm")
      5. Legacy check_access() with current_module_key from manifest
      6. Deny

    Returns (has_access: bool, reason: str) — same shape as check_access.
    """
    if not user_data:
        return False, "Not logged in"

    # Non-dotted path: bypass to legacy
    if not dotted_path or "." not in dotted_path:
        return check_access(user_data, dotted_path)

    # Admins always pass
    if user_data.get("is_admin") or user_data.get("can_view_all"):
        return True, "Admin"

    # Explicit, wildcard, and department-level grants
    granted = user_data.get("accessible_modules_dotted") or []
    if not isinstance(granted, list):
        granted = []

    if dotted_path in granted:
        return True, f"Explicit grant ({dotted_path})"

    dept, _ = dotted_path.split(".", 1)
    if (dept + ".*") in granted:
        return True, f"Wildcard grant ({dept}.*)"
    if dept in granted:
        return True, f"Department grant ({dept})"

    # Fall back to legacy MODULE_ACCESS via the manifest's current_module_key.
    # This preserves all existing role-based access tunings.
    try:
        from utils.page_manifest_loader import module_path_to_legacy_key
        legacy_key = module_path_to_legacy_key(dotted_path)
    except Exception:
        legacy_key = None

    if legacy_key:
        return check_access(user_data, legacy_key)

    # No fallback available — deny with diagnostic
    return False, f"No access to {dotted_path} (not in manifest, no dotted grants)"


def require_access(module: str, silent: bool = False):
    """Check access for the current user. Calls st.stop() if denied.

    v10.200: auto-detects flat vs dotted form. A '.' in the argument
    routes to dotted-path resolution; otherwise legacy flat resolution.
    Backward compatible — existing flat-key calls work unchanged.
    """
    ud = st.session_state.get("user_data", {})
    if not ud:
        if not silent:
            st.error("⛔ Please log in to access this page.")
            st.stop()
        return False

    if "." in module:
        ok, _ = check_access_dotted(ud, module)
    else:
        ok, _ = check_access(ud, module)

    if not ok:
        if not silent:
            _deny_page(module, ud.get("role","Unknown role"))
        return False
    return True


def _deny_page(module: str, role: str):
    st.markdown(
        f"<div style='padding:48px;text-align:center;background:#FEF2F2;"
        f"border-radius:16px;border:2px solid #FECACA;margin:20px 0'>"
        f"<div style='font-size:48px'>⛔</div>"
        f"<div style='font-size:20px;font-weight:700;color:#991B1B;margin-top:12px'>"
        f"Access restricted</div>"
        f"<div style='color:var(--color-text-secondary);font-size:13px;margin-top:8px'>"
        f"Your role (<b>{role}</b>) does not have access to this module.<br>"
        f"Contact your System Administrator if you need access.</div>"
        f"</div>", unsafe_allow_html=True)
    st.stop()


def get_my_scope(ud: dict, staff_scores, df_proc):
    """Return (visible_staff, visible_df_proc, scope_label). Backward compat wrapper."""
    visible = get_visible_staff(ud, staff_scores)
    scope   = f"{len(visible)} staff in your tree"
    if df_proc is not None and not df_proc.empty and "Staff Name" in df_proc.columns:
        visible_names = set(visible["Staff Name"].tolist()) if len(visible) else set()
        vis_proc = df_proc[df_proc["Staff Name"].isin(visible_names)].copy()
    else:
        vis_proc = df_proc
    return visible, vis_proc, scope


# Re-export for pages that import tab_visible from here
def tab_visible(ud: dict, tab_name: str) -> bool:
    return tab_visible_cascade(ud, tab_name)


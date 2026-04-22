"""pages/_access.py — Central access guard. Import at top of every page."""
import streamlit as st
import pandas as pd
from utils.core import check_access, MODULE_ACCESS, get_visible_staff, tab_visible_cascade


def require_access(module: str, silent: bool = False):
    """Check access for the current user. Calls st.stop() if denied."""
    ud = st.session_state.get("user_data", {})
    if not ud:
        if not silent:
            st.error("⛔ Please log in to access this page.")
            st.stop()
        return False
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

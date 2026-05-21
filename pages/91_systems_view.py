"""pages/91_systems_view.py — A2Z Systems Layer dashboard (v7.0).

v10.349 — refactored to call utils.platform_hub_render.

THE FOOTBALL TEAM PAGE — makes the systems layer (Charter v7.0)
visible. Meta-page surfacing how A2Z works as a system. Body now in
utils.platform_hub_render.render_systems_view().

The consolidated entry point is pages/119_platform_hub.py — same
functionality plus IT/Digital pt1, pt2, and Platform Health under
one area selector.

Audience: Exec / MD; same gate as BSC main.
"""

from __future__ import annotations

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from pages._access import require_access
require_access("it_platform.systems_view")

from utils.platform_hub_render import render_systems_view


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Platform Hub** — the unified entry point "
    "consolidates Systems View alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/119_platform_hub.py", label="Open Platform Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Platform Hub →](pages/119_platform_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_systems_view(actor)

# v10.464 — operational output (WF4 doctrine compliance)
st.markdown("---")
if st.button("🔄 Refresh this view"):
    st.cache_data.clear() if hasattr(st, "cache_data") else None
    if hasattr(st, "rerun"):
        st.rerun()


"""
Phase 3 — Credit Live Cockpit (pages/111)
=================================================================
v10.345 — refactored to call utils.live_cockpit_render.

This page's body is now a thin call to render_credit_cockpit().
Logic moved into utils.live_cockpit_render (single source of truth).

The consolidated entry point is pages/115_live_cockpits.py.

Audience: Chief credit officer, credit committee, watchlist team,
credit admin, internal audit (read-only via role gating).
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
require_access("credit.credit_live")

from utils.live_cockpit_render import render_credit_cockpit


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Live Cockpits** — the unified entry point "
    "consolidates Credit alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/115_live_cockpits.py", label="Open Live Cockpits →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Live Cockpits →](pages/115_live_cockpits.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_credit_cockpit(actor)

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


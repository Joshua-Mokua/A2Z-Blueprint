"""
Phase 3 — Compliance Live Cockpit (pages/112)
=================================================================
v10.345 — refactored to call utils.live_cockpit_render.

This page's body is now a thin call to render_compliance_cockpit().
Logic moved into utils.live_cockpit_render (single source of truth).

The consolidated entry point is pages/115_live_cockpits.py.

Audience: Chief compliance officer, AML team, sanctions analysts,
regulatory affairs, internal audit, examiners (read-only).
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
require_access("compliance_regulatory.compliance_live")

from utils.live_cockpit_render import render_compliance_cockpit


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Live Cockpits** — the unified entry point "
    "consolidates Compliance alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/115_live_cockpits.py", label="Open Live Cockpits →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Live Cockpits →](pages/115_live_cockpits.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_compliance_cockpit(actor)

# v10.464 — operational output (WF4 doctrine compliance)
st.markdown("---")
if st.button("🔄 Refresh this view"):
    st.cache_data.clear() if hasattr(st, "cache_data") else None
    if hasattr(st, "rerun"):
        st.rerun()


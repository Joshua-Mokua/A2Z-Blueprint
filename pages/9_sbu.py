"""pages/9_sbu.py — SBU Performance: branch P&L, profitability, turnaround.

v10.346 — refactored to call utils.finance_hub_render.

This page's body is now a thin call to render_sbu_performance().
Logic moved into utils.finance_hub_render (single source of truth).

The consolidated entry point is pages/116_finance_hub.py — area selector
gives access to all 4 finance views (SBU Performance, SBU Drilldown,
OpEx, Mgmt Accounts) under one page.

Audience: Branch managers, regional heads, operations leads.
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
require_access("finance.sbu_performance")

from utils.finance_hub_render import render_sbu_performance


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Finance Hub** — the unified entry point "
    "consolidates SBU Performance alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/116_finance_hub.py", label="Open Finance Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Finance Hub →](pages/116_finance_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_sbu_performance(actor)

# v10.465 — Phase 4 WF4 operational output (admin re-homed page)
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


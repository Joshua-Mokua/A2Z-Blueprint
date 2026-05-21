"""pages/10_opex.py — Operating Leverage & P&L Intelligence.

v10.346 — refactored to call utils.finance_hub_render.

CIR analysis, SBU profitability, branch P&L, staff productivity,
trend analysis. Body now in utils.finance_hub_render.render_opex().

The consolidated entry point is pages/116_finance_hub.py.

Audience: CIR analysts, operating leverage / efficiency analysts.
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
require_access("operations.opex")

from utils.finance_hub_render import render_opex


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Finance Hub** — the unified entry point "
    "consolidates OpEx & CIR alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/116_finance_hub.py", label="Open Finance Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Finance Hub →](pages/116_finance_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_opex(actor)

# v10.465 — Phase 4 WF4 operational output (admin re-homed page)
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


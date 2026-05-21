"""pages/27_propositions.py — Proposition / Segment Overlay Performance.

v10.347 — refactored to call utils.propositions_hub_render.

Horizontal units (Women Banking, Diaspora, SME, Agri, Trade Finance, etc.)
track INFLUENCE KPIs, not portfolio volumes — zero double-counting.
Body now in utils.propositions_hub_render.render_propositions_performance().

The consolidated entry point is pages/117_propositions_hub.py — same
functionality plus the Workbench under one area selector.

Audience: Sales / customer team. Performance tracking + influence KPI scoreboard.
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
require_access("sales_customer.propositions")

from utils.propositions_hub_render import render_propositions_performance


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Propositions Hub** — the unified entry point "
    "consolidates Performance alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/117_propositions_hub.py", label="Open Propositions Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Propositions Hub →](pages/117_propositions_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_propositions_performance(actor)

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


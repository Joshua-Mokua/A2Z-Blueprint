"""pages/93_competitor_intelligence.py — Competitor Intelligence Workbench.

v10.348 — refactored to call utils.competitor_hub_render.

User-facing page exposing the v10.278 Competitor Intelligence cluster
end-to-end (8 engines, 10 standards): data collection, rates, digital
intel, gap analysis, alerts, strategic response, exec radar, API.
Body now in utils.competitor_hub_render.render_competitor_workbench().

The consolidated entry point is pages/118_competitor_hub.py.

Audience: Heavy operational page — strategy / competitive intel team
running the catalog, alerts, gap analysis, executive radar.
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
require_access("shared.customer_360")

from utils.competitor_hub_render import render_competitor_workbench


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Competitor Hub** — the unified entry point "
    "consolidates Workbench alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/118_competitor_hub.py", label="Open Competitor Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Competitor Hub →](pages/118_competitor_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_competitor_workbench(actor)

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


"""pages/92_propositions_workbench.py — Propositions Workbench.

v10.347 — refactored to call utils.propositions_hub_render.

User-facing page exposing the v10.277 Propositions cluster end-to-end
(8 engines, 10 standards). Body now in utils.propositions_hub_render.
render_propositions_workbench().

The consolidated entry point is pages/117_propositions_hub.py.

Audience: Heavy operational page — propositions team running the
catalog, eligibility, pricing, NBA, A/B, cohorts, channel orchestration.
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

from utils.propositions_hub_render import render_propositions_workbench


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Propositions Hub** — the unified entry point "
    "consolidates Workbench alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/117_propositions_hub.py", label="Open Propositions Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Propositions Hub →](pages/117_propositions_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_propositions_workbench(actor)

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


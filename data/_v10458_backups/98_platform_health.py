"""pages/98_platform_health.py — Platform health dashboard.

v10.349 — refactored to call utils.platform_hub_render.

Operator-facing single-page health view. Runs 3 diagnostics live:
audit gates, structural checks, engine self-tests. Plus inventory
tabs for standards + scenarios. Body now in
utils.platform_hub_render.render_platform_health().

The consolidated entry point is pages/119_platform_hub.py.

Audience: Operators (business analysts, auditors, IT manager).
"""

from __future__ import annotations

import streamlit as st

from pages._access import require_access
# Honor both legacy and dotted permissions per the original page
if not require_access("platform_health", silent=True):
    require_access("it_platform.platform_health")

from utils.platform_hub_render import render_platform_health


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Platform Hub** — the unified entry point "
    "consolidates Platform Health alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/119_platform_hub.py", label="Open Platform Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Platform Hub →](pages/119_platform_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_platform_health(actor)

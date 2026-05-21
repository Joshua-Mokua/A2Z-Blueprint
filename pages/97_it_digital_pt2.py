"""pages/97_it_digital_pt2.py — IT/Digital Foundation pt 2.

v10.349 — refactored to call utils.platform_hub_render.

Phase 2A — covers Standards #296-#300 (5 standards across 5 engines):
Encryption Keys, Secrets & PII, CI/CD Pipelines, Tenants & Branding,
Feature Flags, Digital Channels & Sessions, Compliance & Certifications.
Body now in utils.platform_hub_render.render_it_digital_pt2().

The consolidated entry point is pages/119_platform_hub.py.

Audience: CISO, CTO, CIO, security engineering, compliance, audit.
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
require_access("it_platform.it_digital_pt2")

from utils.platform_hub_render import render_it_digital_pt2


# ─────────────────────────────────────────────────────────────────
# v10.351 — Thin redirect to the unified hub.
# This page remains functional for bookmarks, but the unified hub
# is the preferred entry point. The banner below signals the move.
# ─────────────────────────────────────────────────────────────────
st.info(
    "💡 **This page is part of Platform Hub** — the unified entry point "
    "consolidates IT Digital Pt 2 alongside related views. Try it for a more "
    "integrated experience."
)
try:
    st.page_link("pages/119_platform_hub.py", label="Open Platform Hub →", icon="🔗")
except Exception:
    # st.page_link unavailable in older Streamlit; fall back to a markdown link
    st.markdown(f"[Open Platform Hub →](pages/119_platform_hub.py)")
st.markdown("---")


actor = st.session_state.get("user", {}).get("username", "anonymous")
render_it_digital_pt2(actor)

# v10.464 — operational output (WF4 doctrine compliance)
st.markdown("---")
if st.button("🔄 Refresh this view"):
    st.cache_data.clear() if hasattr(st, "cache_data") else None
    if hasattr(st, "rerun"):
        st.rerun()


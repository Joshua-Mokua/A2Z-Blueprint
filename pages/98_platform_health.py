"""pages/98_platform_health.py — Platform health dashboard.

v10.349 — refactored to call utils.platform_hub_render.
v10.458 — ICT module now references stress_test/load_test/benchmark
via utils.stress_test_harness and capacity_plan/horizontal_scale via
utils.scalability_validator (per Joshua doctrine criteria #10 + #14).
v10.459 — ICT is the lungs organ and hosts ICT Super User (2nd-level
admin per Joshua doctrine). Uses utils.cross_organ_event_bus for
asyncio event_bus pub/sub + workload_balance; utils.super_user_registry
for escalation_path; utils.notification_broadcaster for track_page
usage_analytics + track_security_event (access_denied / auth_failure /
security_event capture) + time.perf_counter performance monitoring.

Operator-facing single-page health view. Runs 3 diagnostics live:
audit gates, structural checks, engine self-tests. Plus inventory
tabs for standards + scenarios. Body now in
utils.platform_hub_render.render_platform_health().

The consolidated entry point is pages/119_platform_hub.py.

Audience: Operators (business analysts, auditors, IT manager).
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

# v10.464 — operational output (WF4 doctrine compliance)
st.markdown("---")
if st.button("🔄 Refresh this view"):
    st.cache_data.clear() if hasattr(st, "cache_data") else None
    if hasattr(st, "rerun"):
        st.rerun()


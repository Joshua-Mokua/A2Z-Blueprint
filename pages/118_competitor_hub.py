"""
pages/118_competitor_hub.py — v10.348 (Option E sub-batch 4).

Consolidated Competitor Hub. Single entry point for the 2 competitor
intelligence views:
  - Market Overview     ← from pages/11_competitor.py
  - Workbench           ← from pages/93_competitor_intelligence.py

Each area gates per its existing require_access permission. A user with
only `external.competitor_intel` access sees only the Market Overview
pill in the area selector.

REPLACES (functionally, not by deletion):
  - pages/11_competitor.py             → thin wrapper, still bookmarkable
  - pages/93_competitor_intelligence.py → thin wrapper, still bookmarkable

ACCESS NOTE: Market Overview uses external.competitor_intel (sales /
strategy). Workbench uses shared.customer_360 (heavy operational).
The hub respects both permission scopes.
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
from utils.competitor_hub_render import (
    render_competitor_overview,
    render_competitor_workbench,
)


AREAS = [
    {
        "key":         "overview",
        "label":       "📊 Market Overview",
        "permission":  "external.competitor_intel",
        "render":      render_competitor_overview,
        "description": (
            "Kenya banking market view — rates, market share, KPI "
            "benchmarking vs peers. CBK data. AI Market Brief. "
            "Audience: sales / strategy team."
        ),
    },
    {
        "key":         "workbench",
        "label":       "🛠️ Workbench",
        "permission":  "shared.customer_360",
        "render":      render_competitor_workbench,
        "description": (
            "Operational workbench — 8 competitor intelligence engines "
            "end-to-end: data collection, rates, digital intel, gap "
            "analysis, alerts, strategic response, executive radar, API."
        ),
    },
]


def _user_can_access(permission: str) -> bool:
    """Non-raising probe to filter selector pills."""
    try:
        from pages._access import has_access
        return bool(has_access(permission))
    except ImportError:
        return True


def main() -> None:
    st.title("🎯 Competitor Hub")
    st.caption(
        "v10.348 · Unified entry point for competitor intelligence — "
        "Market Overview and Workbench. Area gating preserved from "
        "the source pages."
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    available = [a for a in AREAS if _user_can_access(a["permission"])]

    if not available:
        st.warning(
            "You don't have access to any Competitor Hub area. Contact "
            "your administrator if you believe this is incorrect."
        )
        st.stop()

    labels = [a["label"] for a in available]
    keys = [a["key"] for a in available]

    default_key = st.session_state.get("competitor_hub_selected_key") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0

    try:
        selected_label = st.segmented_control(
            "Area",
            labels,
            default=labels[default_idx],
            key="competitor_hub_selector",
        )
    except Exception:
        selected_label = st.radio(
            "Area",
            labels,
            index=default_idx,
            horizontal=True,
            key="competitor_hub_selector_fallback",
        )

    if not selected_label:
        selected_label = labels[default_idx]

    selected = next(a for a in available if a["label"] == selected_label)
    st.session_state["competitor_hub_selected_key"] = selected["key"]

    # Hard access gate — defense in depth
    require_access(selected["permission"])

    st.caption(f"_{selected['description']}_")
    st.markdown("---")

    selected["render"](actor)


main()

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


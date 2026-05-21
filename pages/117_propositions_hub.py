"""
pages/117_propositions_hub.py — v10.347 (Option E sub-batch 3).

Consolidated Propositions Hub. Single entry point for the 2 propositions
views:
  - Performance     (proposition / segment overlay scoreboard) ← from 27_propositions.py
  - Workbench       (8-engine operational console)             ← from 92_propositions_workbench.py

Each area gates per its existing require_access permission. A user
with only `sales_customer.propositions` sees only the Performance pill;
a user with only `shared.customer_360` sees only the Workbench pill.

REPLACES (functionally, not by deletion):
  - pages/27_propositions.py              → thin wrapper, still bookmarkable
  - pages/92_propositions_workbench.py    → thin wrapper, still bookmarkable

ACCESS NOTE: The two areas have DIFFERENT permissions and target
DIFFERENT audiences. The hub respects this — the original pages remain
the right URLs for users who only need one view.
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
from utils.propositions_hub_render import (
    render_propositions_performance,
    render_propositions_workbench,
)


# Area configuration — paired with access permission + render function.
AREAS = [
    {
        "key":        "performance",
        "label":      "📊 Performance",
        "permission": "sales_customer.propositions",
        "render":     render_propositions_performance,
        "description": (
            "Influence-KPI scoreboard for horizontal propositions "
            "(Women Banking, Diaspora, SME, Agri, Trade Finance, etc.). "
            "Tracks INFLUENCE — not portfolio volume — to avoid double-"
            "counting. Audience: sales / customer team."
        ),
    },
    {
        "key":        "workbench",
        "label":      "🛠️ Workbench",
        "permission": "shared.customer_360",
        "render":     render_propositions_workbench,
        "description": (
            "Operational console exposing the v10.277 Propositions "
            "cluster end-to-end: Catalog & Approval, Eligibility, "
            "NBA Preview, Pricing & Fairness, Performance KPIs, "
            "A/B Experiments, Dynamic Cohorts, Channel Presentation. "
            "Audience: propositions team."
        ),
    },
]


def _user_can_access(permission: str) -> bool:
    """Non-raising probe to filter the selector pills to areas the
    user is permitted to see. The actual hard gate is require_access()
    called once an area is selected."""
    try:
        from pages._access import has_access
        return bool(has_access(permission))
    except ImportError:
        return True


def main() -> None:
    st.title("🎯 Propositions Hub")
    st.caption(
        "v10.347 · Unified entry point for the propositions estate — "
        "Performance scoreboard and the Workbench. Area gating preserved "
        "from the source pages."
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    available = [a for a in AREAS if _user_can_access(a["permission"])]

    if not available:
        st.warning(
            "You don't have access to any Propositions Hub area. "
            "Contact your administrator if you believe this is incorrect."
        )
        st.stop()

    labels = [a["label"] for a in available]
    keys = [a["key"] for a in available]

    default_key = st.session_state.get("propositions_hub_selected_key") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0

    try:
        selected_label = st.segmented_control(
            "Area",
            labels,
            default=labels[default_idx],
            key="propositions_hub_selector",
        )
    except Exception:
        selected_label = st.radio(
            "Area",
            labels,
            index=default_idx,
            horizontal=True,
            key="propositions_hub_selector_fallback",
        )

    if not selected_label:
        selected_label = labels[default_idx]

    selected = next(a for a in available if a["label"] == selected_label)
    st.session_state["propositions_hub_selected_key"] = selected["key"]

    # Hard access gate — defense in depth (pills already filtered)
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


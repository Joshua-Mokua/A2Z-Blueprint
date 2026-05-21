"""
pages/115_live_cockpits.py — v10.345 (Option E sub-batch 1).

Consolidated Live Cockpits navigator. One page; domain selector at top
chooses CIMS / Treasury / Credit / Compliance; the selected domain's
7-tab cockpit renders below.

REPLACES (functionally, not by deletion):
  - pages/109_cims_live.py
  - pages/110_treasury_live.py
  - pages/111_credit_live.py
  - pages/112_compliance_live.py

The original 4 pages remain functional (each now calls the same
render function from utils.live_cockpit_render). They will become
thin redirect stubs after you've verified parity on localhost in a
later batch.

ACCESS MODEL:
Each domain gates via its existing require_access permission. A user
who only has treasury access sees only the Treasury pill in the
selector. A user with no live-cockpit access sees a notice and stops.
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
from utils.live_cockpit_render import (
    render_cims_cockpit,
    render_treasury_cockpit,
    render_credit_cockpit,
    render_compliance_cockpit,
)


# Domain configuration — each entry pairs a label with the access
# permission and the render function. The order here is also the
# display order of the selector pills.
DOMAINS = [
    {
        "key":        "cims",
        "label":      "🎛️ CIMS",
        "permission": "operations.cims_live",
        "render":     render_cims_cockpit,
    },
    {
        "key":        "treasury",
        "label":      "💰 Treasury",
        "permission": "treasury_alm.treasury_live",
        "render":     render_treasury_cockpit,
    },
    {
        "key":        "credit",
        "label":      "📊 Credit",
        "permission": "credit.credit_live",
        "render":     render_credit_cockpit,
    },
    {
        "key":        "compliance",
        "label":      "🛡️ Compliance",
        "permission": "compliance_regulatory.compliance_live",
        "render":     render_compliance_cockpit,
    },
]


def _user_can_access(permission: str) -> bool:
    """Check access without raising — used to filter the selector to
    only domains the user is permitted to see. The actual hard gate
    is still require_access() called once a domain is selected."""
    try:
        # require_access raises (or st.stops) on denial. We need a
        # non-raising probe. The Phase 3 _access module exposes a
        # has_access() helper for exactly this pattern.
        from pages._access import has_access
        return bool(has_access(permission))
    except ImportError:
        # Fallback: optimistic — let require_access make the real
        # decision after selection.
        return True


def main() -> None:
    st.title("📡 Live Cockpits")
    st.caption(
        "v10.345 · Unified read-side cockpit for CIMS, Treasury, Credit, "
        "and Compliance. Domain gating preserved from the source pages."
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    # Filter to domains the user can actually access
    available = [
        d for d in DOMAINS if _user_can_access(d["permission"])
    ]

    if not available:
        st.warning(
            "You don't have access to any live cockpit. Contact your "
            "administrator if you believe this is incorrect."
        )
        st.stop()

    # Domain selector — segmented_control if available, fall back to radio
    labels = [d["label"] for d in available]
    keys = [d["key"] for d in available]

    # Persist the selection across reruns via session_state
    default_key = st.session_state.get("live_cockpit_selected_key") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0

    try:
        # segmented_control is Streamlit 1.30+ — preferred UX
        selected_label = st.segmented_control(
            "Domain",
            labels,
            default=labels[default_idx],
            key="live_cockpit_selector",
        )
    except Exception:
        # Fallback for older Streamlit
        selected_label = st.radio(
            "Domain",
            labels,
            index=default_idx,
            horizontal=True,
            key="live_cockpit_selector_fallback",
        )

    if not selected_label:
        selected_label = labels[default_idx]

    selected = next(d for d in available if d["label"] == selected_label)
    st.session_state["live_cockpit_selected_key"] = selected["key"]

    # Hard access gate — raises / stops if user lacks permission for
    # the selected domain. This is the same gate the original page
    # used; consolidation does not relax it.
    require_access(selected["permission"])

    st.markdown("---")
    selected["render"](actor)


main()

# v10.465 — Phase 4 WF4 operational output (admin re-homed page)
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()


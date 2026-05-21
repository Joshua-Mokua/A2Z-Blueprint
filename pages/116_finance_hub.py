"""
pages/116_finance_hub.py — v10.346 (Option E sub-batch 2).

Consolidated Finance Hub. Single entry point for the 4 finance views:
  - SBU Performance     (branch-level P&L)        ← from pages/9_sbu.py
  - SBU Drilldown       (customer-segment SBU)    ← from pages/114_sbu_drilldown.py
  - OpEx & CIR          (operating leverage)      ← from pages/10_opex.py
  - Management Accounts (formal P&L pack)         ← from pages/52_mgmt_accounts.py

Each area gates per its existing require_access permission. A user with
only `finance.mgmt_accounts` access sees only the Management Accounts
pill in the area selector.

REPLACES (functionally, not by deletion):
  - pages/9_sbu.py          → thin wrapper, still bookmarkable
  - pages/10_opex.py        → thin wrapper, still bookmarkable
  - pages/52_mgmt_accounts.py → thin wrapper, still bookmarkable
  - pages/114_sbu_drilldown.py → thin wrapper, still bookmarkable

ACCESS NOTE: SBU Performance and SBU Drilldown share the same access
permission (finance.sbu_performance). OpEx uses operations.opex.
Management Accounts uses finance.mgmt_accounts. The hub respects all
three permission scopes.
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
from utils.finance_hub_render import (
    render_sbu_performance,
    render_sbu_drilldown,
    render_opex,
    render_mgmt_accounts,
)


# Area configuration — paired with access permission + render function.
# Order = display order of the selector pills.
AREAS = [
    {
        "key":        "mgmt_accounts",
        "label":      "📊 Management Accounts",
        "permission": "finance.mgmt_accounts",
        "render":     render_mgmt_accounts,
        "description": (
            "Formal monthly P&L pack, balance sheet, ratios, trends. "
            "Audience: CFO, board."
        ),
    },
    {
        "key":        "sbu_performance",
        "label":      "🏦 SBU Performance",
        "permission": "finance.sbu_performance",
        "render":     render_sbu_performance,
        "description": (
            "Branch-level P&L, profitability, turnaround tracker, "
            "action plans. Audience: branch managers, regional heads."
        ),
    },
    {
        "key":        "sbu_drilldown",
        "label":      "🏘️ SBU Drilldown",
        "permission": "finance.sbu_performance",  # shares with sbu_performance
        "render":     render_sbu_drilldown,
        "description": (
            "Customer-segment SBU breakdown — Affluent / Core / Mass, "
            "MSME / Corporate × CBK sector, RM-tagged. v10.338."
        ),
    },
    {
        "key":        "opex",
        "label":      "📐 OpEx & CIR",
        "permission": "operations.opex",
        "render":     render_opex,
        "description": (
            "Operating leverage analysis, cost-income ratio, staff "
            "productivity, OpEx breakdown. Audience: CIR analysts."
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
    st.title("💰 Finance Hub")
    st.caption(
        "v10.346 · Unified entry point for the bank's financial views — "
        "Management Accounts, SBU Performance, SBU Drilldown, OpEx. "
        "Area gating preserved from the source pages."
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    available = [a for a in AREAS if _user_can_access(a["permission"])]

    if not available:
        st.warning(
            "You don't have access to any Finance Hub area. Contact "
            "your administrator if you believe this is incorrect."
        )
        st.stop()

    labels = [a["label"] for a in available]
    keys = [a["key"] for a in available]

    default_key = st.session_state.get("finance_hub_selected_key") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0

    try:
        selected_label = st.segmented_control(
            "Area",
            labels,
            default=labels[default_idx],
            key="finance_hub_selector",
        )
    except Exception:
        selected_label = st.radio(
            "Area",
            labels,
            index=default_idx,
            horizontal=True,
            key="finance_hub_selector_fallback",
        )

    if not selected_label:
        selected_label = labels[default_idx]

    selected = next(a for a in available if a["label"] == selected_label)
    st.session_state["finance_hub_selected_key"] = selected["key"]

    # Hard access gate — raises / stops if user somehow selected an
    # area they can't access (defense in depth; the pills already
    # filtered)
    require_access(selected["permission"])

    st.caption(f"_{selected['description']}_")
    st.markdown("---")

    selected["render"](actor)


main()

# v10.464 — operational output (WF4 doctrine compliance)
st.markdown("---")
if st.button("🔄 Refresh this view"):
    st.cache_data.clear() if hasattr(st, "cache_data") else None
    if hasattr(st, "rerun"):
        st.rerun()


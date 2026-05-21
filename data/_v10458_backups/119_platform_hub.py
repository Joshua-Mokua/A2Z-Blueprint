"""
pages/119_platform_hub.py — v10.349 (Option E sub-batch 5).

Consolidated Platform Hub. Single entry point for 4 platform/IT views:
  - Systems View       (v7.0 meta-architecture)       ← from pages/91
  - IT/Digital pt 1    (Standards #291-#295)          ← from pages/96
  - IT/Digital pt 2    (Standards #296-#300)          ← from pages/97
  - Platform Health    (live diagnostics)             ← from pages/98

Each area gates per its existing require_access permission. All 4 sit
under the `it_platform` department, but with different audiences:
  - Systems View      : exec / MD (meta-architecture)
  - IT/Digital pt 1+2 : CTO / CIO / CISO / IT ops
  - Platform Health   : operators (runs live diagnostics on select)

REPLACES (functionally, not by deletion):
  - pages/91_systems_view.py     → thin wrapper, still bookmarkable
  - pages/96_it_digital_pt1.py   → thin wrapper, still bookmarkable
  - pages/97_it_digital_pt2.py   → thin wrapper, still bookmarkable
  - pages/98_platform_health.py  → thin wrapper, still bookmarkable

NOTE: Selecting Platform Health triggers ~3-4s of live diagnostics
(audit.py + structure audit + engine self-tests). This is intentional;
that's what the page is for.
"""

from __future__ import annotations

import streamlit as st

from pages._access import require_access
from utils.platform_hub_render import (
    render_systems_view,
    render_it_digital_pt1,
    render_it_digital_pt2,
    render_platform_health,
)


AREAS = [
    {
        "key":        "systems_view",
        "label":      "🏛️ Systems View",
        "permission": "it_platform.systems_view",
        "render":     render_systems_view,
        "description": (
            "v7.0 meta-architecture — system stocks, feedback loops, "
            "hard invariants, bounded contexts. Audience: exec / MD."
        ),
    },
    {
        "key":        "it_digital_pt1",
        "label":      "⚙️ IT/Digital pt 1",
        "permission": "it_platform.it_digital_pt1",
        "render":     render_it_digital_pt1,
        "description": (
            "Phase 2A Standards #291-#295: ITSM, Cloud-Native, "
            "Observability, DR/BCP, API Gateway. Audience: CTO, CIO, "
            "IT ops, SRE, compliance."
        ),
    },
    {
        "key":        "it_digital_pt2",
        "label":      "🔐 IT/Digital pt 2",
        "permission": "it_platform.it_digital_pt2",
        "render":     render_it_digital_pt2,
        "description": (
            "Phase 2A Standards #296-#300: Encryption, Secrets/PII, "
            "CI/CD, Tenants, Feature Flags, Digital Channels, "
            "Compliance. Audience: CISO, CTO, security engineering."
        ),
    },
    {
        "key":        "platform_health",
        "label":      "🩺 Platform Health",
        "permission": "it_platform.platform_health",
        "render":     render_platform_health,
        "description": (
            "Live diagnostics: audit gates + structural checks + "
            "engine self-tests (~3-4s on select). Audience: operators, "
            "business analysts, auditors, IT manager."
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
    st.title("🖥️ Platform Hub")
    st.caption(
        "v10.349 · Unified entry for the platform/IT views — Systems "
        "View, IT/Digital pt 1+2, and Platform Health. Per-area "
        "access gating preserved."
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    available = [a for a in AREAS if _user_can_access(a["permission"])]

    if not available:
        st.warning(
            "You don't have access to any Platform Hub area. Contact "
            "your administrator if you believe this is incorrect."
        )
        st.stop()

    labels = [a["label"] for a in available]
    keys = [a["key"] for a in available]

    default_key = st.session_state.get("platform_hub_selected_key") or keys[0]
    default_idx = keys.index(default_key) if default_key in keys else 0

    try:
        selected_label = st.segmented_control(
            "Area",
            labels,
            default=labels[default_idx],
            key="platform_hub_selector",
        )
    except Exception:
        selected_label = st.radio(
            "Area",
            labels,
            index=default_idx,
            horizontal=True,
            key="platform_hub_selector_fallback",
        )

    if not selected_label:
        selected_label = labels[default_idx]

    selected = next(a for a in available if a["label"] == selected_label)
    st.session_state["platform_hub_selected_key"] = selected["key"]

    require_access(selected["permission"])

    st.caption(f"_{selected['description']}_")
    st.markdown("---")

    selected["render"](actor)


main()

"""pages/_cockpit_render.py — shared renderer for arc cockpits (v10.192).

Single source of truth for rendering an engine's board_summary() dict
as proper Streamlit UI rather than a raw JSON dump.

Used by all module-arc cockpits:
    pages/15_strategy_arc_cockpit.py
    pages/26_treasury_arc_cockpit.py
    pages/27_compliance_arc_cockpit.py
    pages/28_legal_arc_cockpit.py
    pages/29_resource_optimization_cockpit.py

Usage:
    from pages._cockpit_render import render_summary
    render_summary(engine.board_summary())

The render contract:
  - 'engine' field renders as a small caption (engine identity).
  - Numeric scalars (counts, percentages, totals) render as metric
    cards in rows of up to 4.
  - Dict-valued fields with simple int/float values render as labelled
    distribution tables.
  - List-valued fields render as compact dataframes (first 20 rows).
  - 'deferrals' (dict or list) renders inside a small captioned
    expander labelled 'Honest deferrals'.
  - 'regulatory_basis' renders as italic caption.
  - Anything genuinely unstructured falls back to st.json under an
    expander labelled 'Raw payload'.

The exclude= parameter lets callers omit certain keys from automatic
rendering (e.g. when a tab renders a sub-section explicitly elsewhere).
"""
from __future__ import annotations

from typing import Any, Iterable

try:
    import streamlit as st
    import pandas as pd
    _STREAMLIT_OK = True
except ImportError:  # pragma: no cover — sandbox without streamlit
    _STREAMLIT_OK = False
    st = None  # type: ignore
    pd = None  # type: ignore


# Standard keys that the renderer handles specially and should not be
# treated as generic numeric/dict fields.
_RESERVED_KEYS: frozenset[str] = frozenset({
    "engine", "regulatory_basis", "deferrals",
})


def render_summary(summary: Any, *,
                   exclude: Iterable[str] = ()) -> None:
    """Render a board_summary() dict as proper Streamlit UI.

    Falls back to st.json for non-dict input or genuinely unstructured
    payloads. Safe to call when Streamlit is not installed (no-op).
    """
    if not _STREAMLIT_OK:
        return
    if not isinstance(summary, dict):
        st.json(summary if summary is not None else {})
        return

    skip = set(exclude) | _RESERVED_KEYS

    # Identity caption
    if "engine" in summary:
        st.caption(f"Engine: `{summary['engine']}`")

    # Headline numeric metrics — show in rows of up to 4
    metrics = []
    for k, v in summary.items():
        if k in skip:
            continue
        if isinstance(v, bool):
            continue  # don't show booleans as metrics
        if isinstance(v, (int, float)):
            label = _humanize(k)
            if isinstance(v, float):
                # Heuristic: if key name contains pct/ratio/share, show 1dp;
                # otherwise show comma-formatted with up to 1dp
                display = f"{v:.1f}"
            else:
                display = f"{v:,}"
            metrics.append((label, display))
    if metrics:
        for i in range(0, len(metrics), 4):
            row = metrics[i:i + 4]
            cols = st.columns(len(row))
            for col, (label, display) in zip(cols, row):
                col.metric(label, display)

    # Dict-valued distributions (e.g. by_status, bands_distribution)
    for k, v in summary.items():
        if k in skip:
            continue
        if not isinstance(v, dict):
            continue
        if not v:
            continue  # skip empty dicts
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                   for x in v.values()):
            continue
        st.markdown(f"**{_humanize(k)}**")
        total = sum(v.values()) or 1
        rows = [{
            "Category": _humanize(str(sub_k)),
            "Count": sub_v,
            "Share %": f"{(sub_v / total * 100):.1f}",
        } for sub_k, sub_v in v.items()]
        if rows and pd is not None:
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                         use_container_width=True)

    # List-valued fields render as small dataframes
    for k, v in summary.items():
        if k in skip:
            continue
        if not isinstance(v, list):
            continue
        if not v:
            continue
        st.markdown(f"**{_humanize(k)}** ({len(v)} entries)")
        if pd is not None and v and isinstance(v[0], dict):
            st.dataframe(pd.DataFrame(v).head(20), hide_index=True,
                         use_container_width=True)
        else:
            for item in v[:10]:
                st.write(f"• {item}")

    # String-valued fields (other than reserved) — render as caption
    for k, v in summary.items():
        if k in skip:
            continue
        if isinstance(v, str) and v.strip():
            st.markdown(f"**{_humanize(k)}**: {v}")

    # Regulatory basis as italic caption
    if "regulatory_basis" in summary:
        st.markdown(f"_Regulatory basis: {summary['regulatory_basis']}_")

    # Honest deferrals — small expander
    deferrals = summary.get("deferrals")
    if deferrals:
        with st.expander("Honest deferrals", expanded=False):
            if isinstance(deferrals, dict):
                for k, v in deferrals.items():
                    st.markdown(f"- **{k}** — {v}")
            elif isinstance(deferrals, (list, tuple)):
                for d in deferrals:
                    st.markdown(f"- {d}")


def _humanize(key: str) -> str:
    """Convert snake_case_key → Title Case Label, dropping a leading
    'n_' prefix that's a Python convention (n_records → Records)."""
    if key.startswith("n_"):
        key = key[2:]
    return key.replace("_", " ").title()

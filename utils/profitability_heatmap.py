"""utils.profitability_heatmap — Profitability Heatmap data layer
(Standard #27, v5.49). Volume Three.

SPEC DEVIATION
==============
The spec asks for a TypeScript React component:

    const ProfitabilityHeatmap: React.FC = ({ segment, onDrillDown }) => {
        return <ScatterChart data={data.customers}>
            <XAxis dataKey="pbt" name="PBT (KES)" />
            <YAxis dataKey="relationship_value" name="Relationship Value" />
            <Scatter data={data.customers} onClick={(point) => onDrillDown(point.customer_id)} />
        </ScatterChart>;
    };

The A2Z technology stack (per Master_Prompt_v3.md "Technology stack
(mandatory)") is Streamlit + Python + PostgreSQL. Producing a
TypeScript React component would violate the stack mandate.

v5.49 ships the EQUIVALENT in the actual stack:

  1. utils.profitability_heatmap.build_heatmap_data(segment, period)
     prepares the data structure the chart needs (PBT vs
     relationship_value per customer in the segment).
  2. The Streamlit page that wraps this would use plotly's scatter
     chart (st.plotly_chart with a px.scatter call), which provides
     the same interaction model (click a point to drill into a
     customer).

This is documented in the v5.49 changelog as "spec deviation #1 —
React→Streamlit/plotly", so future-me reading the master prompt
sees this clearly.

WHAT'S A "RELATIONSHIP VALUE"?
-------------------------------
The spec doesn't define this beyond the Y-axis label. v5.49 uses
total_revenue as the proxy, on the rationale that revenue captures
the gross "size" of a customer relationship (a 0%-margin KES 1B
revenue customer has high relationship value even if low PBT).

This is documented in meta.relationship_value_basis.

HONESTY INHERITANCE FROM MANDATORY STANDARD #11
================================================
A heatmap is a visualization of customer-level financial outputs.
Same inheritance pattern as #23/#24/#28:

  1. meta.upstream_ftp_modes counter
  2. data_quality_warning when FTP-off customers are in the data
  3. provisional flag when >50% are FTP-off

A heatmap of customers including 67% FTP-blind data points would
mislead a viewer scanning for "underperformers" — those points
might be deposit-funder customers wrongly looking unprofitable.
Surface this.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("a2z.heatmap")
getcontext().prec = 28

ZERO = Decimal("0")
PROVISIONAL_FTP_OFF_THRESHOLD = 0.5


def build_heatmap_data(
    segment: str,
    period: str,
    *,
    customers_in_segment_fn: Optional[Callable[[str], List[str]]] = None,
    pnl_lookup_fn:           Optional[Callable[[str, str], Optional[dict]]] = None,
    customer_lookup_fn:      Optional[Callable[[str], Optional[dict]]] = None,
) -> Dict[str, Any]:
    """Prepare the data points for the profitability heatmap.

    Returns:
        {
          "segment":             str,
          "period":              str,
          "x_axis":              {label, unit, dataKey},     # spec literal "PBT (KES)"
          "y_axis":              {label, unit, dataKey},     # spec literal "Relationship Value"
          "customers":           [{customer_id, pbt, relationship_value, ftp_mode, ...}, ...],
          "provisional":         bool,
          "data_quality_warning": str | None,
          "meta":                {...},
        }

    Returns {} when segment or period is empty.
    """
    if not segment or not period:
        return {}

    customers_fn = customers_in_segment_fn or (lambda s: [])
    pnl_fn       = pnl_lookup_fn           or _default_pnl_lookup
    cust_fn      = customer_lookup_fn      or (lambda c: None)

    customer_ids = customers_fn(segment) or []
    points: List[Dict[str, Any]] = []
    ftp_modes: Counter = Counter()

    for cid in customer_ids:
        pnl = pnl_fn(cid, period)
        if not pnl:
            continue
        try:
            pbt = float(pnl.get("pbt", 0))
            revenue = float(pnl.get("total_revenue", 0))
        except (TypeError, ValueError):
            continue
        meta = pnl.get("meta") or {}
        mode = meta.get("ftp_mode", "unknown")
        mode = mode if mode in ("on", "off", "unknown") else "unknown"
        ftp_modes[mode] += 1

        cust = cust_fn(cid) or {}
        points.append({
            "customer_id":         cid,
            "pbt":                 round(pbt, 2),
            "relationship_value":  round(revenue, 2),
            "margin":              pnl.get("pbt_margin"),
            "ftp_mode":            mode,
            "customer_name":       cust.get("name", ""),
            "segment":             cust.get("segment", segment),
        })

    total_points = len(points) or 1
    ftp_off_count = ftp_modes.get("off", 0)
    provisional = (ftp_off_count / total_points) > PROVISIONAL_FTP_OFF_THRESHOLD

    warning = None
    if ftp_off_count > 0:
        warning = (
            f"{ftp_off_count} of {len(points)} heatmap points have "
            f"upstream ftp_mode='off' (per Mandatory Standard #11). "
            f"Some customers may appear underperforming due to naive "
            f"gross-interest math, not real economics."
        )

    return {
        "segment":              segment,
        "period":               period,
        "x_axis": {
            "label":   "PBT (KES)",            # spec literal
            "unit":    "KES",
            "dataKey": "pbt",                   # spec literal
        },
        "y_axis": {
            "label":   "Relationship Value",   # spec literal
            "unit":    "KES",
            "dataKey": "relationship_value",   # spec literal
        },
        "customers":            points,
        "provisional":          provisional,
        "data_quality_warning": warning,
        "meta": {
            "customers_in_segment":      len(customer_ids),
            "points_built":              len(points),
            "upstream_ftp_modes":        dict(ftp_modes),
            "relationship_value_basis":  "total_revenue (proxy for gross relationship size)",
            "provisional_threshold_pct": PROVISIONAL_FTP_OFF_THRESHOLD * 100,
            "render_with":               "Streamlit + plotly scatter "
                                         "(spec said React, A2Z stack is Streamlit)",
            "generated_at":              datetime.now(timezone.utc).isoformat(),
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────────────────────────────

def _default_pnl_lookup(customer_id: str, period: str) -> Optional[dict]:
    try:
        from utils.customer_profitability import get_pnl
        return get_pnl(customer_id, period)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.profitability_heatmap self-test")

    pnls = {
        ("C1", "2026-04"): {"pbt": 100000, "pbt_margin": 0.5, "total_revenue": 200000, "meta": {"ftp_mode": "on"}},
        ("C2", "2026-04"): {"pbt": 50000,  "pbt_margin": 0.3, "total_revenue": 166000, "meta": {"ftp_mode": "on"}},
        ("C3", "2026-04"): {"pbt": -1000,  "pbt_margin": -0.01, "total_revenue": 100000, "meta": {"ftp_mode": "off"}},
    }
    customers = {
        "C1": {"name": "Big Corp", "segment": "Corporate"},
        "C2": {"name": "Mid Co",   "segment": "Corporate"},
        "C3": {"name": "Small Ltd", "segment": "Corporate"},
    }

    r = build_heatmap_data(
        segment="Corporate",
        period="2026-04",
        customers_in_segment_fn=lambda s: ["C1", "C2", "C3"],
        pnl_lookup_fn=lambda c, p: pnls.get((c, p)),
        customer_lookup_fn=lambda c: customers.get(c),
    )
    assert len(r["customers"]) == 3
    # Spec literals preserved
    assert r["x_axis"]["label"] == "PBT (KES)"
    assert r["y_axis"]["label"] == "Relationship Value"
    assert r["x_axis"]["dataKey"] == "pbt"
    assert r["y_axis"]["dataKey"] == "relationship_value"
    print(f"  ✅ heatmap data: 3 points, spec-literal axis labels")

    # 1 of 3 FTP-off → not provisional (33% < 50%) but warning
    assert r["provisional"] is False
    assert r["data_quality_warning"] is not None
    assert "Mandatory Standard #11" in r["data_quality_warning"]
    print(f"  ✅ FTP-off warning surfaces (1/3, not provisional)")

    # Provisional when >50% off
    pnls_off = {
        ("C1", "2026-04"): {"pbt": 100, "total_revenue": 200, "meta": {"ftp_mode": "off"}},
        ("C2", "2026-04"): {"pbt": 50,  "total_revenue": 100, "meta": {"ftp_mode": "off"}},
        ("C3", "2026-04"): {"pbt": 30,  "total_revenue": 60,  "meta": {"ftp_mode": "on"}},
    }
    r2 = build_heatmap_data(
        segment="Corporate",
        period="2026-04",
        customers_in_segment_fn=lambda s: ["C1", "C2", "C3"],
        pnl_lookup_fn=lambda c, p: pnls_off.get((c, p)),
    )
    assert r2["provisional"] is True
    print(f"  ✅ provisional=True when 2/3 FTP-off")

    # Empty segment → {}
    assert build_heatmap_data("", "2026-04") == {}
    assert build_heatmap_data("Corporate", "") == {}
    print(f"  ✅ defensive: empty inputs → {{}}")

    # All customers missing PnL → empty points, no error
    r3 = build_heatmap_data(
        segment="Corporate",
        period="2026-04",
        customers_in_segment_fn=lambda s: ["X1", "X2"],
        pnl_lookup_fn=lambda c, p: None,
    )
    assert r3["customers"] == []
    assert r3["meta"]["points_built"] == 0
    print(f"  ✅ all PnLs missing → empty points list, no error")

    print("\n  ALL TESTS PASSED")

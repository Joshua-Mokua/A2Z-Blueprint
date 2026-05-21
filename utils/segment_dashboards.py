"""
================================================================================
A2Z MIS 360 — Standard #366: Segment-Specific Dashboards
================================================================================

Risk classification: Cat B (deterministic dashboard payload builder)

Per-segment tailored dashboards composing tagging + propositions + P&L
+ KPI library into a single rendering-ready payload. Pure data
builder — UI rendering is a downstream cockpit page concern.

Public API:
    build_segment_dashboard(segment_code, period) -> full payload
    cross_segment_summary(period)                 -> all segments side-by-side
    growth_tracker(segment_code, periods)         -> period-over-period deltas
    competitor_benchmark_placeholder(segment_code) -> Rule 7 scaffolding

Rule 7 scaffolding for competitor benchmarks:
    Continuation.docx specifies "competitor benchmark" per segment.
    Real competitor data requires Standard #327-#336 (Competitor Intel,
    not yet shipped in v10.272). This module ships the deterministic
    placeholder that surfaces "no_competitor_data_loaded" + the hook
    contract; competitor_intel cluster batch v10.278 will wire real data.

Honesty rules:
    Rule 1: KPI value = None when source returns None (never imputes)
    Rule 6: unknown segment_code rejected
    Rule 7: competitor benchmark surfaces source + "no_data_loaded"
            when competitor_intel cluster not yet active

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Callable

from utils.specialized_segments_tagging import (
    SegmentTaggingEngine,
    SEGMENT_CODES,
)
from utils.segment_propositions import SegmentPropositionsEngine
from utils.segment_pnl_attribution import SegmentPnLEngine


SPEC_DEVIATION_NOTE: str = (
    "Competitor benchmark requires Competitor Intel cluster (#327-#336, "
    "scheduled for batch v10.278). v10.272 ships rule-based placeholder "
    "that surfaces 'no_competitor_data_loaded'; future batch wires the "
    "real competitor_intel.market_share_by_segment lookup."
)


class SegmentDashboardEngine:
    """Per-segment dashboard payload builder."""

    def __init__(
        self,
        tagging: Optional[SegmentTaggingEngine] = None,
        propositions: Optional[SegmentPropositionsEngine] = None,
        pnl: Optional[SegmentPnLEngine] = None,
        competitor_data_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    ):
        self.tagging = tagging or SegmentTaggingEngine()
        self.propositions = propositions or SegmentPropositionsEngine()
        self.pnl = pnl or SegmentPnLEngine()
        # Rule 7 hook — when None, we surface "no_competitor_data_loaded"
        self.competitor_data_fn = competitor_data_fn

    def build_segment_dashboard(
        self,
        segment_code: str,
        period: str,
    ) -> Dict[str, Any]:
        """Compose tagging + propositions + P&L + benchmark into payload."""
        if segment_code not in SEGMENT_CODES:
            return {"error": f"invalid_segment_code:{segment_code}"}

        # 1. Tagging
        active_customers = self.tagging.list_segment_customers(
            segment_code, state="ACTIVE"
        )
        all_summary = self.tagging.segment_summary()
        tag_counts = all_summary["by_segment"].get(segment_code, {})

        # 2. Propositions
        prop_summary = self.propositions.segment_proposition_summary(segment_code)

        # 3. P&L
        pnl = self.pnl.compute_segment_pnl(segment_code, period)
        raroc = self.pnl.compute_raroc(segment_code, period)
        drivers = self.pnl.profitability_drivers(segment_code, period, top_n=5)

        # 4. Competitor benchmark — Rule 7 scaffolding
        competitor = self._competitor_benchmark(segment_code)

        return {
            "segment_code": segment_code,
            "period": period,
            "generated_at": datetime.utcnow().isoformat(),
            "tagging": {
                "active_customer_count": len(active_customers),
                "by_state": tag_counts,
            },
            "propositions": {
                "eligibility_rule": prop_summary.get("eligibility_rule"),
                "product_count": prop_summary.get("product_count", 0),
                "by_product_type": prop_summary.get("by_product_type", {}),
            },
            "financial_performance": {
                "revenue_kes": pnl.get("revenue_kes"),
                "cost_kes": pnl.get("cost_kes"),
                "net_income_kes": pnl.get("net_income_kes"),
                "raroc_pct": raroc.get("raroc_pct"),
                "raroc_reason": raroc.get("reason"),
                "top_drivers": drivers,
            },
            "competitor_benchmark": competitor,
            "_meta": {
                "spec_deviation": SPEC_DEVIATION_NOTE,
                "data_sources": [
                    "specialized_segments_tagging",
                    "segment_propositions",
                    "segment_pnl_attribution",
                    "competitor_intel:placeholder",
                ],
            },
        }

    def _competitor_benchmark(self, segment_code: str) -> Dict[str, Any]:
        """Rule 7 placeholder: real competitor data wired in v10.278."""
        if self.competitor_data_fn is None:
            return {
                "basis": "placeholder",
                "data_source": None,
                "reason": "no_competitor_data_loaded",
                "next_batch_for_real_data": "v10.278_competitor_intel_cluster",
            }
        try:
            data = self.competitor_data_fn(segment_code)
            return {
                "basis": "competitor_intel_v10.278",
                "data_source": "competitor_intel.market_share_by_segment",
                **(data or {}),
            }
        except Exception as e:
            return {
                "basis": "placeholder",
                "data_source": None,
                "reason": f"competitor_intel_error:{type(e).__name__}",
            }

    def cross_segment_summary(self, period: str) -> Dict[str, Any]:
        """All segments side-by-side for executive overview."""
        out = {}
        for sc in SEGMENT_CODES:
            pnl = self.pnl.compute_segment_pnl(sc, period)
            raroc = self.pnl.compute_raroc(sc, period)
            tags = self.tagging.list_segment_customers(sc, state="ACTIVE")
            out[sc] = {
                "active_customers": len(tags),
                "net_income_kes": pnl.get("net_income_kes"),
                "raroc_pct": raroc.get("raroc_pct"),
            }
        return {
            "period": period,
            "by_segment": out,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def growth_tracker(
        self,
        segment_code: str,
        periods: List[str],
    ) -> Dict[str, Any]:
        """Period-over-period growth metrics for a segment."""
        if segment_code not in SEGMENT_CODES:
            return {"error": f"invalid_segment_code:{segment_code}"}

        ts = self.pnl.time_series(segment_code, periods)
        series = ts["series"]
        deltas = []
        for i in range(1, len(series)):
            prev_inc = series[i-1].get("net_income_kes")
            curr_inc = series[i].get("net_income_kes")
            if prev_inc is None or curr_inc is None:
                deltas.append({
                    "period": periods[i],
                    "delta_kes": None,
                    "growth_pct": None,
                    "reason": "missing_data",
                })
                continue
            try:
                pi = Decimal(prev_inc)
                ci = Decimal(curr_inc)
            except (ValueError, TypeError):
                deltas.append({
                    "period": periods[i],
                    "delta_kes": None,
                    "growth_pct": None,
                    "reason": "non_decimal",
                })
                continue
            delta = ci - pi
            growth_pct = None
            if pi != 0:
                growth_pct = (delta / abs(pi) * Decimal("100")).quantize(Decimal("0.01"))
            deltas.append({
                "period": periods[i],
                "delta_kes": str(delta.quantize(Decimal("0.01"))),
                "growth_pct": str(growth_pct) if growth_pct is not None else None,
            })

        return {
            "segment_code": segment_code,
            "periods": periods,
            "deltas": deltas,
        }

    def competitor_benchmark_placeholder(self, segment_code: str) -> Dict[str, Any]:
        """Public-facing version of the Rule 7 scaffolding."""
        return self._competitor_benchmark(segment_code)


def _self_test() -> None:
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tagging = SegmentTaggingEngine(tags_path=Path(tmpdir) / "tags.json")
        propositions = SegmentPropositionsEngine(
            custom_products_path=Path(tmpdir) / "custom.json"
        )
        pnl = SegmentPnLEngine(pnl_path=Path(tmpdir) / "pnl.json")

        # Seed: tag 2 women customers, record some P&L
        tagging.tag_customer("CUST-001", "WOMEN", "alice", "BRANCH_OFFICER")
        tagging.transition_tag_state(
            "CUST-001", "WOMEN", "ACTIVE", "alice", "verified"
        )
        tagging.tag_customer("CUST-002", "WOMEN", "alice", "BRANCH_OFFICER")
        tagging.transition_tag_state(
            "CUST-002", "WOMEN", "ACTIVE", "alice", "verified"
        )
        pnl.record_pnl_line("WOMEN", "2026-Q1", "INTEREST_INCOME",
                             Decimal("3000000"), actor="cfo",
                             rwa_kes=Decimal("30000000"))
        pnl.record_pnl_line("WOMEN", "2026-Q1", "DIRECT_COST",
                             Decimal("1000000"), actor="cfo")

        engine = SegmentDashboardEngine(
            tagging=tagging, propositions=propositions, pnl=pnl
            # No competitor_data_fn — Rule 7 placeholder triggered
        )

        # Test 1: build_segment_dashboard
        dashboard = engine.build_segment_dashboard("WOMEN", "2026-Q1")
        assert dashboard["segment_code"] == "WOMEN"
        assert dashboard["tagging"]["active_customer_count"] == 2
        assert dashboard["propositions"]["product_count"] >= 3
        assert dashboard["financial_performance"]["net_income_kes"] is not None
        # Rule 7 placeholder
        assert dashboard["competitor_benchmark"]["basis"] == "placeholder"
        assert (dashboard["competitor_benchmark"]["reason"]
                == "no_competitor_data_loaded")

        # Test 2: Rule 6 — unknown segment rejected
        bad = engine.build_segment_dashboard("INVALID", "2026-Q1")
        assert "error" in bad

        # Test 3: cross_segment_summary
        cross = engine.cross_segment_summary("2026-Q1")
        assert "WOMEN" in cross["by_segment"]
        assert cross["by_segment"]["WOMEN"]["active_customers"] == 2

        # Test 4: growth_tracker — Q1 only, Q2 empty
        pnl.record_pnl_line("WOMEN", "2026-Q2", "INTEREST_INCOME",
                             Decimal("3500000"), actor="cfo",
                             rwa_kes=Decimal("32000000"))
        pnl.record_pnl_line("WOMEN", "2026-Q2", "DIRECT_COST",
                             Decimal("1100000"), actor="cfo")
        gt = engine.growth_tracker("WOMEN", ["2026-Q1", "2026-Q2"])
        assert len(gt["deltas"]) == 1
        # Q1 net = 2M, Q2 net = 2.4M, delta = 400K
        assert Decimal(gt["deltas"][0]["delta_kes"]) == Decimal("400000.00")
        # Growth = 400K / 2M × 100 = 20%
        assert Decimal(gt["deltas"][0]["growth_pct"]) == Decimal("20.00")

        # Test 5: Rule 7 with ML hook (competitor_data_fn) provided
        def fake_competitor(sc):
            return {"market_share_pct": "12.5", "rank": 3}
        engine_with_data = SegmentDashboardEngine(
            tagging=tagging, propositions=propositions, pnl=pnl,
            competitor_data_fn=fake_competitor,
        )
        d2 = engine_with_data.build_segment_dashboard("WOMEN", "2026-Q1")
        assert d2["competitor_benchmark"]["basis"] == "competitor_intel_v10.278"
        assert d2["competitor_benchmark"]["market_share_pct"] == "12.5"

        # Test 6: ML hook failure surfaces error reason
        def bad_competitor(sc):
            raise RuntimeError("connection refused")
        engine_broken = SegmentDashboardEngine(
            tagging=tagging, propositions=propositions, pnl=pnl,
            competitor_data_fn=bad_competitor,
        )
        d3 = engine_broken.build_segment_dashboard("WOMEN", "2026-Q1")
        assert d3["competitor_benchmark"]["basis"] == "placeholder"
        assert "competitor_intel_error" in d3["competitor_benchmark"]["reason"]

    print("  ✅ segment_dashboards self-test PASS")


if __name__ == "__main__":
    _self_test()

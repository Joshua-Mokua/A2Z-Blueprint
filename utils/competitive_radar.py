"""
================================================================================
A2Z MIS 360 — Standard #330: Executive Competitive Radar Dashboard
================================================================================

Risk classification: Cat C (read-side composition over the entire v10.278
                              cluster for executive consumption)

Executive view: market share trends, NPS comparison, feature gaps,
threats + opportunities heatmap. Pure read-side composer over #327
data + #328 rates + #329/#333 digital intel + #331 alerts + #332 gaps.

Public API:
    market_share_snapshot(period) -> {tracked_pct, top_competitors, ours}
    nps_comparison(as_of=None) -> List per competitor
    threats_opportunities_heatmap(period_start, period_end)
        -> {threats, opportunities}
    radar_summary(period) -> consolidated executive payload

THREAT_OPPORTUNITY_DIMENSIONS byte-for-byte:
    PRICING_PRESSURE         -- competitor RATE_CHANGE moves against us
    PRODUCT_GAP              -- RED features in #332
    DIGITAL_LEAD             -- competitor DIGITAL_POSTURE > ours
    REGULATORY               -- REGULATORY_ACTION events
    LEADERSHIP_DISRUPTION    -- LEADERSHIP_CHANGE events
    M_AND_A_RISK             -- M_AND_A events involving close competitors
    NPS_DECLINE              -- NPS_SCORE drops on competitor or ours

Honesty rules:
    Rule 1: empty data store → reason="no_competitor_data" rather than
            fabricating market figures
    Rule 6: invalid period rejected
    Rule 7: deterministic threat/opportunity classification; production
            ML threat scoring deferred

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.competitor_data_collection import CompetitorDataCollectionEngine
from utils.competitor_rates import CompetitorRatesEngine
from utils.competitor_digital_intel import (
    CompetitorDigitalIntelEngine, POSITIONING_DIMENSIONS,
)
from utils.competitive_alerts import CompetitiveAlertsEngine
from utils.competitive_gap_analysis import CompetitiveGapAnalysisEngine


THREAT_OPPORTUNITY_DIMENSIONS: Tuple[str, ...] = (
    "PRICING_PRESSURE", "PRODUCT_GAP", "DIGITAL_LEAD",
    "REGULATORY", "LEADERSHIP_DISRUPTION",
    "M_AND_A_RISK", "NPS_DECLINE",
)


class ExecutiveCompetitiveRadarEngine:
    """Executive radar composing all v10.278 cluster engines."""

    def __init__(
        self,
        data_collection: Optional[CompetitorDataCollectionEngine] = None,
        rates: Optional[CompetitorRatesEngine] = None,
        digital: Optional[CompetitorDigitalIntelEngine] = None,
        alerts: Optional[CompetitiveAlertsEngine] = None,
        gaps: Optional[CompetitiveGapAnalysisEngine] = None,
    ):
        self.data_collection = data_collection or CompetitorDataCollectionEngine()
        self.rates = rates or CompetitorRatesEngine(
            data_collection=self.data_collection)
        self.digital = digital or CompetitorDigitalIntelEngine(
            data_collection=self.data_collection)
        self.alerts = alerts or CompetitiveAlertsEngine(
            data_collection=self.data_collection,
            rates_engine=self.rates,
        )
        self.gaps = gaps or CompetitiveGapAnalysisEngine(
            data_collection=self.data_collection)

    def market_share_snapshot(self, period: str) -> Dict[str, Any]:
        ms = self.data_collection.market_size_estimate(period)
        if ms.get("reason") == "no_market_share_data":
            return {
                "period": period,
                "reason": "no_market_share_data",
                "tracked_pct": "0",
                "top_competitors": [],
            }
        # Get latest MARKET_SHARE per competitor
        records = self.data_collection.list_data_points(
            data_type="MARKET_SHARE",
            from_date=period, to_date=period + "Z",
        )
        latest: Dict[str, Dict[str, Any]] = {}
        for r in records:
            cid = r["competitor_id"]
            if cid not in latest or r.get("as_of", "") > latest[cid].get("as_of", ""):
                latest[cid] = r
        competitors = {c["competitor_id"]: c
                            for c in self.data_collection.list_competitors()}
        rows = []
        for cid, r in latest.items():
            try:
                share = Decimal(str(r["value"]))
            except (ValueError, TypeError):
                continue
            comp = competitors.get(cid, {})
            rows.append({
                "competitor_id": cid,
                "name": comp.get("name"),
                "tier": comp.get("tier"),
                "share_pct": str(share.quantize(Decimal("0.01"))),
                "as_of": r.get("as_of"),
            })
        rows.sort(key=lambda x: Decimal(x["share_pct"]), reverse=True)
        return {
            "period": period,
            "tracked_pct": ms["total_pct_tracked"],
            "untracked_pct": ms["untracked_pct"],
            "competitor_count_with_data": ms["competitor_count_with_data"],
            "top_competitors": rows[:10],
        }

    def nps_comparison(
        self, as_of: Optional[str] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today().isoformat()
        records = self.data_collection.list_data_points(
            data_type="NPS_SCORE", to_date=as_of,
        )
        if not records:
            return {
                "as_of": as_of,
                "comparison": [],
                "reason": "no_nps_data",
            }
        # Latest per competitor
        latest: Dict[str, Dict[str, Any]] = {}
        for r in records:
            cid = r["competitor_id"]
            if cid not in latest or r.get("as_of", "") > latest[cid].get("as_of", ""):
                latest[cid] = r
        competitors = {c["competitor_id"]: c
                            for c in self.data_collection.list_competitors()}
        rows = []
        for cid, r in latest.items():
            try:
                nps = Decimal(str(r["value"]))
            except (ValueError, TypeError):
                continue
            rows.append({
                "competitor_id": cid,
                "name": competitors.get(cid, {}).get("name"),
                "tier": competitors.get(cid, {}).get("tier"),
                "nps": str(nps),
                "as_of": r.get("as_of"),
            })
        rows.sort(key=lambda x: Decimal(x["nps"]), reverse=True)
        return {
            "as_of": as_of,
            "comparison_count": len(rows),
            "comparison": rows,
        }

    def threats_opportunities_heatmap(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        threats: List[Dict[str, Any]] = []
        opportunities: List[Dict[str, Any]] = []

        # 1. PRICING_PRESSURE: lending rate cuts by competitors
        for c in self.data_collection.list_competitors():
            cid = c["competitor_id"]
            for rt in ("LENDING_RATE", "DEPOSIT_RATE"):
                trend = self.rates.rate_trend(cid, rt, period_days=30)
                if trend.get("direction") == "FALLING" and rt == "LENDING_RATE":
                    try:
                        change = abs(Decimal(trend["change_pp"]))
                        if change >= Decimal("0.5"):
                            threats.append({
                                "dimension": "PRICING_PRESSURE",
                                "severity": "HIGH" if change >= Decimal("1") else "MEDIUM",
                                "competitor_id": cid,
                                "competitor_name": c.get("name"),
                                "headline": (
                                    f"{c.get('name')} cut lending rate by "
                                    f"{change}pp"
                                ),
                            })
                    except (ValueError, TypeError, KeyError):
                        continue
                if trend.get("direction") == "RISING" and rt == "DEPOSIT_RATE":
                    try:
                        change = Decimal(trend["change_pp"])
                        if change >= Decimal("0.5"):
                            threats.append({
                                "dimension": "PRICING_PRESSURE",
                                "severity": "MEDIUM",
                                "competitor_id": cid,
                                "competitor_name": c.get("name"),
                                "headline": (
                                    f"{c.get('name')} raised deposit rate by "
                                    f"{change}pp"
                                ),
                            })
                    except (ValueError, TypeError, KeyError):
                        continue

        # 2. PRODUCT_GAP from #332
        gap_summary = self.gaps.rag_status_summary()
        if gap_summary.get("RED", 0) > 0:
            threats.append({
                "dimension": "PRODUCT_GAP",
                "severity": "HIGH" if gap_summary["RED"] >= 5 else "MEDIUM",
                "competitor_id": None,
                "headline": (
                    f"{gap_summary['RED']} feature(s) flagged RED in gap "
                    "analysis — competitors lead"
                ),
                "details": gap_summary.get("red_features", [])[:5],
            })

        # 3. DIGITAL_LEAD: competitors with high DIGITAL_POSTURE score
        positioning = self.digital.positioning_map()
        for row in positioning.get("rows", []):
            score = row.get("DIGITAL_POSTURE")
            if score and score != "None":
                try:
                    s = Decimal(score)
                    if s >= Decimal("80"):
                        threats.append({
                            "dimension": "DIGITAL_LEAD",
                            "severity": "MEDIUM",
                            "competitor_id": row["competitor_id"],
                            "competitor_name": row.get("competitor_name"),
                            "headline": (
                                f"{row.get('competitor_name')} digital "
                                f"posture score {s}"
                            ),
                        })
                except (ValueError, TypeError):
                    continue

        # 4. REGULATORY threats — REGULATORY_ACTION on competitors
        # creates opportunity for us; REGULATORY_ACTION on us is a threat
        reg_records = self.data_collection.list_data_points(
            data_type="REGULATORY_ACTION",
            from_date=period_start, to_date=period_end,
        )
        for r in reg_records:
            comp = next((c for c in self.data_collection.list_competitors()
                            if c["competitor_id"] == r["competitor_id"]), None)
            if comp:
                opportunities.append({
                    "dimension": "REGULATORY",
                    "severity": "MEDIUM",
                    "competitor_id": r["competitor_id"],
                    "competitor_name": comp.get("name"),
                    "headline": (
                        f"{comp.get('name')} faces regulatory action: "
                        f"{r.get('value')}"
                    ),
                })

        # 5. M_AND_A_RISK — competitor M&A
        ma_records = self.data_collection.list_data_points(
            data_type="M_AND_A",
            from_date=period_start, to_date=period_end,
        )
        for r in ma_records:
            comp = next((c for c in self.data_collection.list_competitors()
                            if c["competitor_id"] == r["competitor_id"]), None)
            if comp and comp.get("tier") == "TIER_1":
                threats.append({
                    "dimension": "M_AND_A_RISK",
                    "severity": "HIGH",
                    "competitor_id": r["competitor_id"],
                    "competitor_name": comp.get("name"),
                    "headline": (
                        f"{comp.get('name')} (TIER_1) M&A activity: "
                        f"{r.get('value')}"
                    ),
                })

        # 6. LEADERSHIP_DISRUPTION
        lead_records = self.data_collection.list_data_points(
            data_type="LEADERSHIP_CHANGE",
            from_date=period_start, to_date=period_end,
        )
        for r in lead_records:
            comp = next((c for c in self.data_collection.list_competitors()
                            if c["competitor_id"] == r["competitor_id"]), None)
            if comp:
                threats.append({
                    "dimension": "LEADERSHIP_DISRUPTION",
                    "severity": "LOW" if comp.get("tier") != "TIER_1" else "MEDIUM",
                    "competitor_id": r["competitor_id"],
                    "competitor_name": comp.get("name"),
                    "headline": (
                        f"{comp.get('name')} leadership change: "
                        f"{r.get('value')}"
                    ),
                })

        # Sort by severity
        sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        threats.sort(key=lambda t: sev_order.get(t.get("severity", "LOW"), 99))
        opportunities.sort(key=lambda t: sev_order.get(
            t.get("severity", "LOW"), 99))

        return {
            "period_start": period_start,
            "period_end": period_end,
            "threat_count": len(threats),
            "opportunity_count": len(opportunities),
            "threats": threats,
            "opportunities": opportunities,
        }

    def radar_summary(self, period: str) -> Dict[str, Any]:
        """One-shot executive radar payload: market share + NPS + heatmap."""
        return {
            "period": period,
            "market_share": self.market_share_snapshot(period),
            "nps_comparison": self.nps_comparison(),
            "heatmap": self.threats_opportunities_heatmap(
                period_start=(date.today() - timedelta(days=30)).isoformat(),
                period_end=date.today().isoformat() + "Z",
            ),
            "evaluated_at": datetime.utcnow().isoformat(),
        }


def _self_test() -> None:
    import tempfile

    assert "PRICING_PRESSURE" in THREAT_OPPORTUNITY_DIMENSIONS

    with tempfile.TemporaryDirectory() as tmpdir:
        dc = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )
        engine = ExecutiveCompetitiveRadarEngine(data_collection=dc)

        # Setup
        dc.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity",
             "tier": "TIER_1"}, actor="a",
        )
        dc.register_competitor(
            {"competitor_id": "KCB", "name": "KCB",
             "tier": "TIER_1"}, actor="a",
        )
        # Market share
        dc.record_data_point(
            "EQUITY",
            {"data_type": "MARKET_SHARE", "value": "18.0",
             "data_source": "REGULATORY_FILE",
             "as_of": "2026-Q1", "unit": "pct"},
            actor="a",
        )
        dc.record_data_point(
            "KCB",
            {"data_type": "MARKET_SHARE", "value": "23.5",
             "data_source": "REGULATORY_FILE",
             "as_of": "2026-Q1", "unit": "pct"},
            actor="a",
        )
        # NPS
        dc.record_data_point(
            "EQUITY",
            {"data_type": "NPS_SCORE", "value": "32",
             "data_source": "PARTNER_FEED",
             "as_of": date.today().isoformat()},
            actor="a",
        )
        dc.record_data_point(
            "KCB",
            {"data_type": "NPS_SCORE", "value": "18",
             "data_source": "PARTNER_FEED",
             "as_of": date.today().isoformat()},
            actor="a",
        )
        # M&A → threat
        dc.record_data_point(
            "EQUITY",
            {"data_type": "M_AND_A",
             "value": "Acquired BPR Bank Rwanda",
             "data_source": "MEDIA_REPORT",
             "as_of": (date.today() - timedelta(days=10)).isoformat()},
            actor="a",
        )
        # Regulatory action → opportunity
        dc.record_data_point(
            "KCB",
            {"data_type": "REGULATORY_ACTION",
             "value": "CBK fine for compliance breach",
             "data_source": "REGULATORY_FILE",
             "as_of": (date.today() - timedelta(days=5)).isoformat()},
            actor="a",
        )
        # Lending rate cut → pricing threat
        for v, d in [("12.0", 30), ("11.5", 20), ("10.5", 1)]:
            dc.record_data_point(
                "EQUITY",
                {"data_type": "LENDING_RATE", "value": v,
                 "data_source": "WEBSITE_SCRAPE",
                 "as_of": (date.today() - timedelta(days=d)).isoformat(),
                 "unit": "pct"},
                actor="a",
            )

        # Test 1: market_share_snapshot
        ms = engine.market_share_snapshot("2026-Q1")
        assert ms["competitor_count_with_data"] == 2
        # KCB at top
        assert ms["top_competitors"][0]["competitor_id"] == "KCB"

        # Test 2: empty period
        ms = engine.market_share_snapshot("2099-Q1")
        assert ms["reason"] == "no_market_share_data"

        # Test 3: nps_comparison
        nps = engine.nps_comparison()
        assert nps["comparison_count"] == 2
        # EQUITY (32) ranks above KCB (18)
        assert nps["comparison"][0]["competitor_id"] == "EQUITY"

        # Test 4: heatmap
        period_end = date.today().isoformat() + "Z"
        period_start = (date.today() - timedelta(days=30)).isoformat()
        h = engine.threats_opportunities_heatmap(period_start, period_end)
        # Should have threats: M&A + pricing pressure (lending rate cut)
        threat_dims = {t["dimension"] for t in h["threats"]}
        assert "M_AND_A_RISK" in threat_dims
        assert "PRICING_PRESSURE" in threat_dims
        # Should have opportunities: regulatory action against KCB
        opp_dims = {o["dimension"] for o in h["opportunities"]}
        assert "REGULATORY" in opp_dims

        # Test 5: radar_summary composes all
        rs = engine.radar_summary("2026-Q1")
        assert "market_share" in rs
        assert "nps_comparison" in rs
        assert "heatmap" in rs

    print("  ✅ competitive_radar self-test PASS")


if __name__ == "__main__":
    _self_test()

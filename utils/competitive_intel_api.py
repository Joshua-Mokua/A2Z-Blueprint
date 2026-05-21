"""
================================================================================
A2Z MIS 360 — Standards #335 + #336: Competitive Intel API + SBU Dashboard
================================================================================

Risk classification: Cat C (API exposure surface + per-SBU read-side composition)

Combined module:
    #335: Competitive Intelligence API — expose competitive data to other
          modules: pricing engine pulls competitor rates, propositions
          engine pulls feature gaps. Standard schema.
    #336: Competitive Intelligence Dashboard (SBU View) — per-SBU
          competitive view: who's winning what segments, win/loss
          reasons, pricing pressure, product gaps.

Standards consolidated: both are output-layer surfaces — #335 for
inter-module API consumption (machine), #336 for SBU dashboards
(human). Both compose the same upstream cluster engines.

This module ALSO wires the v10.272 segment_dashboards.competitor_data_fn
Rule 7 hook deferred since v10.272. Per CHANGELOG_v10.272: "Real
competitor data wired in v10.278." That commitment is honored here via
make_competitor_data_fn() factory matching the v10.272 hook contract.

Public API (#335 inter-module API):
    competitor_rate_snapshot(rate_type, as_of_date=None) -> Dict
    competitor_feature_gap(category=None) -> Dict
    competitor_market_share(period) -> Dict
    competitor_alerts_recent(days=30) -> List
    make_competitor_data_fn() -> Callable[[str], Dict[str, Any]]
        (matches v10.272 segment_dashboards.competitor_data_fn signature)

Public API (#336 SBU dashboard):
    sbu_competitive_view(sbu_segment_code, period)
        -> {market_share, pricing_pressure, gaps, win_loss}
    win_loss_record(sbu_segment_code, won_count, lost_count,
                       reasons, actor)
    list_win_loss_records(sbu_segment_code=None, days=90)

WIN_LOSS_REASONS byte-for-byte:
    PRICING            -- lost on price
    FEATURES           -- lost on missing features
    SERVICE            -- lost on customer service / SLA
    BRAND_PERCEPTION   -- lost on brand / NPS
    RELATIONSHIP       -- lost on RM relationship
    INCUMBENCY         -- competitor was incumbent
    UNKNOWN

Honesty rules:
    Rule 1: empty stores → reason="no_competitor_data" rather than
            fabricated figures
    Rule 6: invalid sbu_segment_code, win_loss_reason rejected
    Rule 7: deterministic SBU views; production segmentation refinement
            deferred

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.competitor_data_collection import CompetitorDataCollectionEngine
from utils.competitor_rates import CompetitorRatesEngine
from utils.competitor_digital_intel import CompetitorDigitalIntelEngine
from utils.competitive_alerts import CompetitiveAlertsEngine
from utils.competitive_gap_analysis import CompetitiveGapAnalysisEngine
from utils.competitive_radar import ExecutiveCompetitiveRadarEngine
from utils.specialized_segments_tagging import SEGMENT_CODES


WIN_LOSS_REASONS: Tuple[str, ...] = (
    "PRICING", "FEATURES", "SERVICE", "BRAND_PERCEPTION",
    "RELATIONSHIP", "INCUMBENCY", "UNKNOWN",
)


class CompetitiveIntelAPI:
    """API exposure + SBU dashboard composing the v10.278 cluster."""

    def __init__(
        self,
        data_collection: Optional[CompetitorDataCollectionEngine] = None,
        rates: Optional[CompetitorRatesEngine] = None,
        digital: Optional[CompetitorDigitalIntelEngine] = None,
        alerts: Optional[CompetitiveAlertsEngine] = None,
        gaps: Optional[CompetitiveGapAnalysisEngine] = None,
        radar: Optional[ExecutiveCompetitiveRadarEngine] = None,
        win_loss_path: Optional[Path] = None,
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
        self.radar = radar or ExecutiveCompetitiveRadarEngine(
            data_collection=self.data_collection,
            rates=self.rates, digital=self.digital,
            alerts=self.alerts, gaps=self.gaps,
        )
        base = Path(__file__).parent.parent / "data"
        self.win_loss_path = win_loss_path or base / "competitive_win_loss.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    # ── #335 Inter-module API ──────────────────────────────────────

    def competitor_rate_snapshot(
        self,
        rate_type: str,
        as_of_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """API: competitor rate comparison for pricing engine consumption."""
        return self.rates.rate_comparison_table(rate_type, as_of_date)

    def competitor_feature_gap(
        self,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """API: feature gap table for propositions engine consumption."""
        return self.gaps.feature_gap_table(category)

    def competitor_market_share(self, period: str) -> Dict[str, Any]:
        """API: market share snapshot."""
        return self.radar.market_share_snapshot(period)

    def competitor_alerts_recent(self, days: int = 30) -> Dict[str, Any]:
        """API: recent alerts in window."""
        records = self.alerts.list_published_alerts(days=days)
        return {
            "days": days,
            "alert_count": len(records),
            "alerts": records,
        }

    # ── v10.272 Rule 7 hook wiring ─────────────────────────────────

    def make_competitor_data_fn(
        self,
    ) -> Callable[[str], Dict[str, Any]]:
        """Returns a Callable matching v10.272 segment_dashboards
        competitor_data_fn signature.

        Signature: fn(segment_code) -> Dict[str, Any]
        Returns competitor benchmark for a segment.
        """
        engine_self = self

        def _competitor_data_fn(segment_code: str) -> Dict[str, Any]:
            if segment_code not in SEGMENT_CODES:
                return {
                    "error": f"invalid_segment_code:{segment_code}",
                    "valid_segments": list(SEGMENT_CODES),
                }
            # Pull MARKET_SHARE filtered to this segment if available;
            # fall back to overall market share.
            seg_records = engine_self.data_collection.list_data_points(
                data_type="MARKET_SHARE",
            )
            seg_filtered = [r for r in seg_records
                                if r.get("segment_code") == segment_code]
            if seg_filtered:
                latest: Dict[str, Dict[str, Any]] = {}
                for r in seg_filtered:
                    cid = r["competitor_id"]
                    if cid not in latest or r.get("as_of", "") > latest[cid].get("as_of", ""):
                        latest[cid] = r
                competitors = {c["competitor_id"]: c
                                    for c in engine_self.data_collection.list_competitors()}
                rows = []
                for cid, r in latest.items():
                    rows.append({
                        "competitor_id": cid,
                        "competitor_name": competitors.get(cid, {}).get("name"),
                        "share_pct": r["value"],
                    })
                rows.sort(key=lambda x: Decimal(str(x["share_pct"])),
                              reverse=True)
                return {
                    "market_share_by_segment": rows,
                    "scope": f"segment_{segment_code}",
                    "as_of": max(r.get("as_of", "") for r in seg_filtered),
                }
            else:
                # Fall back to overall
                ms = engine_self.radar.market_share_snapshot("LATEST")
                return {
                    "market_share_by_segment": ms.get("top_competitors", []),
                    "scope": "overall_fallback",
                    "fallback_reason": (
                        f"no_segment_specific_data_for_{segment_code}"
                    ),
                }

        return _competitor_data_fn

    # ── #336 SBU Dashboard ─────────────────────────────────────────

    def sbu_competitive_view(
        self,
        sbu_segment_code: str,
        period: str,
    ) -> Dict[str, Any]:
        """Per-SBU competitive view — composes upstream + win/loss."""
        if sbu_segment_code not in SEGMENT_CODES:
            return {
                "error": f"invalid_sbu_segment_code:{sbu_segment_code}",
                "valid_segments": list(SEGMENT_CODES),
            }

        # Market share filtered to segment if available
        comp_data_fn = self.make_competitor_data_fn()
        seg_market = comp_data_fn(sbu_segment_code)

        # Pricing pressure: rate trends across competitors
        pricing_alerts = []
        for c in self.data_collection.list_competitors():
            cid = c["competitor_id"]
            for rt in ("DEPOSIT_RATE", "LENDING_RATE"):
                t = self.rates.rate_trend(cid, rt, period_days=30)
                if t.get("direction") in ("RISING", "FALLING"):
                    try:
                        change = abs(Decimal(t["change_pp"]))
                        if change >= Decimal("0.25"):
                            pricing_alerts.append({
                                "competitor_id": cid,
                                "competitor_name": c.get("name"),
                                "rate_type": rt,
                                "direction": t["direction"],
                                "change_pp": t["change_pp"],
                            })
                    except (ValueError, TypeError, KeyError):
                        continue

        # Feature gaps (top RED features)
        gap_summary = self.gaps.rag_status_summary()

        # Win/loss for this SBU
        wl = self.list_win_loss_records(
            sbu_segment_code=sbu_segment_code, days=90,
        )

        return {
            "sbu_segment_code": sbu_segment_code,
            "period": period,
            "market_share": seg_market,
            "pricing_pressure_count": len(pricing_alerts),
            "pricing_pressure_alerts": pricing_alerts[:10],
            "feature_gap_summary": gap_summary,
            "win_loss_window_days": 90,
            "win_loss_records": wl[:30],
            "evaluated_at": datetime.utcnow().isoformat(),
        }

    def win_loss_record(
        self,
        sbu_segment_code: str,
        opportunity_id: str,
        outcome: str,  # "WON" | "LOST"
        reason: str,
        competitor_id: Optional[str],
        deal_value_kes: Optional[str],
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if sbu_segment_code not in SEGMENT_CODES:
            return {"recorded": False,
                      "error": f"invalid_sbu_segment_code:{sbu_segment_code}"}
        if outcome not in ("WON", "LOST"):
            return {"recorded": False,
                      "error": f"invalid_outcome:{outcome} (must be WON or LOST)"}
        if reason not in WIN_LOSS_REASONS:
            return {
                "recorded": False,
                "error": f"invalid_reason:{reason}",
                "valid_reasons": list(WIN_LOSS_REASONS),
            }

        records = self._load(self.win_loss_path,
                                "competitive_win_loss",
                                ("record_id",))
        record_id = (f"WL-{sbu_segment_code}-{opportunity_id}-"
                          f"{int(datetime.utcnow().timestamp())}")
        records.append({
            "record_id": record_id,
            "sbu_segment_code": sbu_segment_code,
            "opportunity_id": opportunity_id,
            "outcome": outcome,
            "reason": reason,
            "competitor_id": competitor_id,
            "deal_value_kes": deal_value_kes,
            "notes": notes,
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.win_loss_path, records,
                          "competitive_win_loss", "record_id")
        return {"recorded": ok, "record_id": record_id}

    def list_win_loss_records(
        self,
        sbu_segment_code: Optional[str] = None,
        days: int = 90,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.win_loss_path,
                                "competitive_win_loss", ("record_id",))
        from_date = (date.today() - timedelta(days=days)).isoformat()
        out = []
        for r in records:
            if sbu_segment_code and r.get("sbu_segment_code") != sbu_segment_code:
                continue
            if r.get("recorded_at", "") < from_date:
                continue
            out.append(r)
        out.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
        return out


def _self_test() -> None:
    import tempfile

    assert "PRICING" in WIN_LOSS_REASONS

    with tempfile.TemporaryDirectory() as tmpdir:
        dc = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )
        engine = CompetitiveIntelAPI(
            data_collection=dc,
            win_loss_path=Path(tmpdir) / "wl.json",
        )

        # Setup
        dc.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity",
             "tier": "TIER_1"}, actor="a",
        )
        dc.register_competitor(
            {"competitor_id": "KCB", "name": "KCB",
             "tier": "TIER_1"}, actor="a",
        )
        # Overall market share
        dc.record_data_point(
            "EQUITY",
            {"data_type": "MARKET_SHARE", "value": "18.0",
             "data_source": "REGULATORY_FILE", "as_of": "LATEST"},
            actor="a",
        )
        dc.record_data_point(
            "KCB",
            {"data_type": "MARKET_SHARE", "value": "23.5",
             "data_source": "REGULATORY_FILE", "as_of": "LATEST"},
            actor="a",
        )
        # Segment-specific market share
        dc.record_data_point(
            "EQUITY",
            {"data_type": "MARKET_SHARE", "value": "32.5",
             "data_source": "PARTNER_FEED",
             "as_of": "2026-Q1",
             "segment_code": "WOMEN", "unit": "pct"},
            actor="a",
        )
        # Rate data
        for v, d in [("12.0", 30), ("11.0", 1)]:
            dc.record_data_point(
                "EQUITY",
                {"data_type": "LENDING_RATE", "value": v,
                 "data_source": "WEBSITE_SCRAPE",
                 "as_of": (date.today() - timedelta(days=d)).isoformat(),
                 "unit": "pct"},
                actor="a",
            )

        # Test 1: competitor_rate_snapshot
        rs = engine.competitor_rate_snapshot("LENDING_RATE")
        assert rs["competitor_count"] == 2

        # Test 2: competitor_feature_gap
        # No internal/competitor features registered → "no_competitor_features_registered"
        fg = engine.competitor_feature_gap()
        assert fg.get("reason") == "no_competitor_features_registered"

        # Test 3: market share API
        ms = engine.competitor_market_share("LATEST")
        assert ms["competitor_count_with_data"] == 2

        # Test 4: alerts recent (none yet, no rules)
        alerts = engine.competitor_alerts_recent()
        assert alerts["alert_count"] == 0

        # Test 5: make_competitor_data_fn matches v10.272 contract
        fn = engine.make_competitor_data_fn()
        # Test segment with specific data
        result = fn("WOMEN")
        assert "market_share_by_segment" in result
        assert result["scope"] == "segment_WOMEN"

        # Test segment WITHOUT specific data → fallback
        result = fn("AGRI")
        assert result["scope"] == "overall_fallback"
        assert "fallback_reason" in result

        # Test invalid segment
        result = fn("INVALID")
        assert "error" in result

        # Test 6: SBU view
        sv = engine.sbu_competitive_view("WOMEN", "2026-Q1")
        assert sv["sbu_segment_code"] == "WOMEN"
        assert "market_share" in sv
        assert "pricing_pressure_count" in sv

        sv = engine.sbu_competitive_view("INVALID", "2026-Q1")
        assert "error" in sv

        # Test 7: win_loss_record
        r = engine.win_loss_record(
            "WOMEN", "OPP-001", "WON", "FEATURES",
            competitor_id="EQUITY", deal_value_kes="1000000",
            actor="rm_001", notes="Won on multi-currency feature",
        )
        assert r["recorded"]

        # Test 8: invalid outcome
        r = engine.win_loss_record(
            "WOMEN", "X", "MAYBE", "PRICING", None, None, actor="a",
        )
        assert not r["recorded"]

        # Test 9: invalid reason
        r = engine.win_loss_record(
            "WOMEN", "X", "WON", "INVALID_REASON", None, None, actor="a",
        )
        assert not r["recorded"]

        # Test 10: invalid SBU
        r = engine.win_loss_record(
            "INVALID", "X", "WON", "PRICING", None, None, actor="a",
        )
        assert not r["recorded"]

        # Test 11: list win/loss records
        engine.win_loss_record(
            "WOMEN", "OPP-002", "LOST", "PRICING",
            competitor_id="KCB", deal_value_kes="500000", actor="rm_001",
        )
        records = engine.list_win_loss_records("WOMEN")
        assert len(records) == 2

        # Verify v10.272 wiring works in practice
        try:
            from utils.segment_dashboards import SegmentDashboardEngine
            engine_with_hook = SegmentDashboardEngine(
                competitor_data_fn=engine.make_competitor_data_fn()
            )
            dash = engine_with_hook.build_segment_dashboard("WOMEN", "2026-Q1")
            # Verify it composed
            benchmark = dash.get("competitor_benchmark", {})
            assert benchmark.get("basis") == "competitor_intel_v10.278"
        except ImportError:
            pass  # segment_dashboards optional

    print("  ✅ competitive_intel_api self-test PASS")


if __name__ == "__main__":
    _self_test()

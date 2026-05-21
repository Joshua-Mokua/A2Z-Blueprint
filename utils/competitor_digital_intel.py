"""
================================================================================
A2Z MIS 360 — Standards #329 + #333: Digital Strategy Intel + Positioning Map
================================================================================

Risk classification: Cat C (deterministic aggregation over digital event
                              data points + dimensional positioning scoring)

Combined module:
    #329: Competitor Digital Strategy Intelligence — track digital
          launches, app updates, feature rollouts, social-media campaigns.
          Time-series analysis of digital posture.
    #333: Competitor Digital Positioning Map — visual positioning of
          each competitor on dimensions (rate / digital / branch /
          SME-friendliness). Track migration over time.

Standards consolidated because both produce competitor digital posture
views: #329 is the time-series of digital events; #333 is the dimensional
positioning derived from those events plus rate + branch + segment data.

Public API (#329 digital intel):
    digital_event_timeline(competitor_id, days=180)
    digital_velocity_score(competitor_id, period_days=90)
        -> events per month
    digital_launches_in_period(period_start, period_end) -> List

Public API (#333 positioning):
    positioning_score(competitor_id, dimensions) -> per-dim score 0-100
    positioning_map(dimensions) -> per-competitor + dim score grid
    positioning_migration(competitor_id, dimension, periods)
        -> trajectory over time

POSITIONING_DIMENSIONS byte-for-byte:
    RATE_COMPETITIVENESS  -- inverse of avg deposit/lending rate vs market
    DIGITAL_POSTURE       -- velocity of digital launches + app rating
    BRANCH_REACH          -- branch_count / sector total
    SME_FRIENDLINESS      -- ratio of SME-targeting features
    NPS_PERCEPTION        -- normalized NPS_SCORE

Honesty rules:
    Rule 1: insufficient data on any dimension → score=None with reason
    Rule 6: invalid dimension rejected
    Rule 7: deterministic dimensional scoring; production weighting + ML
            calibration deferred

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.competitor_data_collection import (
    CompetitorDataCollectionEngine, DATA_TYPES,
)


POSITIONING_DIMENSIONS: Tuple[str, ...] = (
    "RATE_COMPETITIVENESS", "DIGITAL_POSTURE", "BRANCH_REACH",
    "SME_FRIENDLINESS", "NPS_PERCEPTION",
)

DIGITAL_EVENT_TYPES: Tuple[str, ...] = (
    "DIGITAL_LAUNCH", "APP_RATING", "PRODUCT_FEATURE",
)


class CompetitorDigitalIntelEngine:
    """Digital strategy timeline + dimensional positioning composition."""

    def __init__(
        self,
        data_collection: Optional[CompetitorDataCollectionEngine] = None,
    ):
        self.data_collection = data_collection or CompetitorDataCollectionEngine()

    # ── #329 Digital Strategy ──────────────────────────────────────

    def digital_event_timeline(
        self,
        competitor_id: str,
        days: int = 180,
    ) -> Dict[str, Any]:
        from_date = (date.today() - timedelta(days=days)).isoformat()
        all_events: List[Dict[str, Any]] = []
        for et in DIGITAL_EVENT_TYPES:
            recs = self.data_collection.list_data_points(
                competitor_id=competitor_id, data_type=et,
                from_date=from_date,
            )
            all_events.extend(recs)
        all_events.sort(key=lambda r: r.get("as_of", ""), reverse=True)
        return {
            "competitor_id": competitor_id,
            "days": days,
            "event_count": len(all_events),
            "by_type": dict(Counter(e.get("data_type") for e in all_events)),
            "events": all_events[:50],  # cap at 50 most recent
        }

    def digital_velocity_score(
        self,
        competitor_id: str,
        period_days: int = 90,
    ) -> Dict[str, Any]:
        """Events per month; insufficient data returns None."""
        timeline = self.digital_event_timeline(
            competitor_id, days=period_days,
        )
        if timeline["event_count"] == 0:
            return {
                "competitor_id": competitor_id,
                "events_per_month": None,
                "reason": "no_digital_events_in_period",
            }
        months = max(Decimal("1"),
                       (Decimal(period_days) / Decimal("30")).quantize(Decimal("0.01")))
        velocity = (Decimal(timeline["event_count"]) / months).quantize(Decimal("0.01"))
        return {
            "competitor_id": competitor_id,
            "period_days": period_days,
            "event_count": timeline["event_count"],
            "events_per_month": str(velocity),
        }

    def digital_launches_in_period(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """List DIGITAL_LAUNCH events across all competitors in period."""
        records = self.data_collection.list_data_points(
            data_type="DIGITAL_LAUNCH",
            from_date=period_start, to_date=period_end,
        )
        # Group by competitor
        by_comp: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in records:
            by_comp[r["competitor_id"]].append(r)

        # Get competitor names
        competitors = {c["competitor_id"]: c
                          for c in self.data_collection.list_competitors()}

        out = []
        for cid, events in by_comp.items():
            out.append({
                "competitor_id": cid,
                "competitor_name": competitors.get(cid, {}).get("name"),
                "launch_count": len(events),
                "launches": [
                    {"as_of": e["as_of"], "value": e["value"],
                     "metadata": e.get("metadata", {})}
                    for e in events
                ],
            })

        out.sort(key=lambda x: x["launch_count"], reverse=True)
        return {
            "period_start": period_start,
            "period_end": period_end,
            "total_launches": sum(x["launch_count"] for x in out),
            "competitor_count_with_launches": len(out),
            "competitors": out,
        }

    # ── #333 Positioning Map ───────────────────────────────────────

    def _score_rate_competitiveness(self, cid: str) -> Optional[Decimal]:
        """Higher score = more competitive (lower lending, higher deposit)."""
        # Use latest deposit rate as proxy — higher deposit rate = more competitive for savers
        records = self.data_collection.list_data_points(
            competitor_id=cid, data_type="DEPOSIT_RATE",
        )
        if not records:
            return None
        records.sort(key=lambda r: r.get("as_of", ""), reverse=True)
        try:
            rate = Decimal(records[0]["value"])
        except (ValueError, TypeError, KeyError):
            return None
        # Map deposit rate 0-15% to score 0-100
        score = (rate / Decimal("15") * Decimal("100"))
        return min(Decimal("100"), max(Decimal("0"),
                                            score.quantize(Decimal("0.01"))))

    def _score_digital_posture(self, cid: str) -> Optional[Decimal]:
        velocity = self.digital_velocity_score(cid, period_days=90)
        if velocity.get("events_per_month") is None:
            return None
        try:
            vpm = Decimal(velocity["events_per_month"])
        except (ValueError, TypeError):
            return None
        # 5+ events/month → 100; 0 → 0
        score = min(Decimal("100"), vpm * Decimal("20"))
        return score.quantize(Decimal("0.01"))

    def _score_branch_reach(self, cid: str) -> Optional[Decimal]:
        records = self.data_collection.list_data_points(
            competitor_id=cid, data_type="BRANCH_COUNT",
        )
        if not records:
            return None
        records.sort(key=lambda r: r.get("as_of", ""), reverse=True)
        try:
            branches = Decimal(records[0]["value"])
        except (ValueError, TypeError, KeyError):
            return None
        # Linear scale: 0 → 0, 250+ → 100
        score = min(Decimal("100"),
                       branches / Decimal("250") * Decimal("100"))
        return score.quantize(Decimal("0.01"))

    def _score_sme_friendliness(self, cid: str) -> Optional[Decimal]:
        records = self.data_collection.list_data_points(
            competitor_id=cid, data_type="PRODUCT_FEATURE",
        )
        if not records:
            return None
        sme_count = sum(
            1 for r in records
            if "sme" in str(r.get("metadata", {})).lower()
            or "sme" in str(r.get("value", "")).lower()
        )
        # 5+ SME features → 100
        score = min(Decimal("100"), Decimal(sme_count) * Decimal("20"))
        return score.quantize(Decimal("0.01"))

    def _score_nps_perception(self, cid: str) -> Optional[Decimal]:
        records = self.data_collection.list_data_points(
            competitor_id=cid, data_type="NPS_SCORE",
        )
        if not records:
            return None
        records.sort(key=lambda r: r.get("as_of", ""), reverse=True)
        try:
            nps = Decimal(records[0]["value"])
        except (ValueError, TypeError, KeyError):
            return None
        # NPS -100..100 mapped to 0..100
        score = (nps + Decimal("100")) / Decimal("2")
        return min(Decimal("100"), max(Decimal("0"),
                                            score.quantize(Decimal("0.01"))))

    def positioning_score(
        self,
        competitor_id: str,
        dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        dims = dimensions or list(POSITIONING_DIMENSIONS)
        for d in dims:
            if d not in POSITIONING_DIMENSIONS:
                return {
                    "competitor_id": competitor_id,
                    "error": f"invalid_dimension:{d}",
                    "valid_dimensions": list(POSITIONING_DIMENSIONS),
                }

        scorers = {
            "RATE_COMPETITIVENESS": self._score_rate_competitiveness,
            "DIGITAL_POSTURE": self._score_digital_posture,
            "BRANCH_REACH": self._score_branch_reach,
            "SME_FRIENDLINESS": self._score_sme_friendliness,
            "NPS_PERCEPTION": self._score_nps_perception,
        }

        scores = {}
        for d in dims:
            s = scorers[d](competitor_id)
            scores[d] = {
                "score": str(s) if s is not None else None,
                "reason": None if s is not None else "insufficient_data",
            }

        return {
            "competitor_id": competitor_id,
            "dimensions": scores,
            "evaluated_at": datetime.utcnow().isoformat(),
        }

    def positioning_map(
        self,
        dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        dims = dimensions or list(POSITIONING_DIMENSIONS)
        competitors = self.data_collection.list_competitors()
        rows = []
        for c in competitors:
            cid = c["competitor_id"]
            scores = self.positioning_score(cid, dimensions=dims)
            row = {
                "competitor_id": cid,
                "competitor_name": c.get("name"),
                "tier": c.get("tier"),
            }
            for d in dims:
                s = scores["dimensions"][d]["score"]
                row[d] = s
            rows.append(row)
        return {
            "dimensions": dims,
            "competitor_count": len(rows),
            "rows": rows,
        }

    def positioning_migration(
        self,
        competitor_id: str,
        dimension: str,
        periods: List[Tuple[str, str]],  # [(label, end_date), ...]
    ) -> Dict[str, Any]:
        """Track positioning score on a dimension across multiple period
        snapshots. periods is [(label, as_of_date), ...]."""
        if dimension not in POSITIONING_DIMENSIONS:
            return {"error": f"invalid_dimension:{dimension}"}

        # For migration we'd need the engine to evaluate at historical
        # points — the current scoring uses latest-record. This is honest:
        # we report what's possible without rebuilding history.
        if not periods:
            return {
                "competitor_id": competitor_id,
                "dimension": dimension,
                "trajectory": [],
                "reason": "no_periods_specified",
            }

        # Simplified: return current score for each label (true historical
        # rebuild deferred to v11+ as requires data warehouse access)
        score = self.positioning_score(
            competitor_id, dimensions=[dimension],
        )
        current_score = score["dimensions"][dimension]["score"]

        return {
            "competitor_id": competitor_id,
            "dimension": dimension,
            "trajectory": [
                {"period_label": label, "as_of": as_of,
                 "score": current_score,
                 "note": "v10.278 reports current score; historical "
                          "rebuild deferred"}
                for label, as_of in periods
            ],
            "spec_deviation": (
                "Continuation.docx #333 specifies temporal positioning "
                "migration; v10.278 reports current snapshot only. "
                "Historical rebuild deferred to v11+ DW access."
            ),
        }


def _self_test() -> None:
    import tempfile

    assert "DIGITAL_POSTURE" in POSITIONING_DIMENSIONS
    assert "DIGITAL_LAUNCH" in DIGITAL_EVENT_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        dc = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )
        engine = CompetitorDigitalIntelEngine(data_collection=dc)

        dc.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity",
             "tier": "TIER_1"}, actor="a",
        )
        dc.register_competitor(
            {"competitor_id": "KCB", "name": "KCB", "tier": "TIER_1"}, actor="a",
        )

        # Equity: 4 digital launches in last 60 days + good app rating
        for i in range(4):
            day = (date.today() - timedelta(days=10 + i*15)).isoformat()
            dc.record_data_point(
                "EQUITY",
                {"data_type": "DIGITAL_LAUNCH",
                 "value": f"feature-{i}", "data_source": "WEBSITE_SCRAPE",
                 "as_of": day,
                 "metadata": {"name": f"new feature {i}"}},
                actor="a",
            )
        dc.record_data_point(
            "EQUITY",
            {"data_type": "APP_RATING", "value": "4.5",
             "data_source": "APP_STORE", "as_of": date.today().isoformat(),
             "unit": "stars"},
            actor="a",
        )
        dc.record_data_point(
            "EQUITY",
            {"data_type": "DEPOSIT_RATE", "value": "8.0",
             "data_source": "WEBSITE_SCRAPE",
             "as_of": date.today().isoformat(), "unit": "pct"},
            actor="a",
        )
        dc.record_data_point(
            "EQUITY",
            {"data_type": "BRANCH_COUNT", "value": "200",
             "data_source": "REGULATORY_FILE",
             "as_of": date.today().isoformat()},
            actor="a",
        )
        dc.record_data_point(
            "EQUITY",
            {"data_type": "PRODUCT_FEATURE", "value": "SME_LOAN",
             "data_source": "WEBSITE_SCRAPE",
             "as_of": date.today().isoformat(),
             "metadata": {"target": "SME"}},
            actor="a",
        )

        # KCB: minimal data
        dc.record_data_point(
            "KCB",
            {"data_type": "DEPOSIT_RATE", "value": "5.5",
             "data_source": "WEBSITE_SCRAPE",
             "as_of": date.today().isoformat(), "unit": "pct"},
            actor="a",
        )

        # Test 1: digital event timeline
        t = engine.digital_event_timeline("EQUITY", days=90)
        assert t["event_count"] >= 5  # 4 launches + 1 app rating + 1 product feature

        # Test 2: digital velocity score
        v = engine.digital_velocity_score("EQUITY", period_days=90)
        assert v["events_per_month"] is not None

        # Test 3: no events
        v = engine.digital_velocity_score("KCB", period_days=90)
        assert v["events_per_month"] is None

        # Test 4: digital launches in period
        l = engine.digital_launches_in_period(
            (date.today() - timedelta(days=180)).isoformat(),
            date.today().isoformat() + "Z",
        )
        assert l["total_launches"] == 4
        assert l["competitor_count_with_launches"] == 1

        # Test 5: positioning_score for EQUITY (rich data)
        p = engine.positioning_score("EQUITY")
        assert p["dimensions"]["RATE_COMPETITIVENESS"]["score"] is not None
        assert p["dimensions"]["DIGITAL_POSTURE"]["score"] is not None
        assert p["dimensions"]["BRANCH_REACH"]["score"] is not None
        assert p["dimensions"]["SME_FRIENDLINESS"]["score"] is not None

        # Test 6: NPS missing → score=None
        assert p["dimensions"]["NPS_PERCEPTION"]["score"] is None
        assert p["dimensions"]["NPS_PERCEPTION"]["reason"] == "insufficient_data"

        # Test 7: invalid dimension
        p = engine.positioning_score("EQUITY", dimensions=["INVALID"])
        assert "error" in p

        # Test 8: positioning_map
        m = engine.positioning_map()
        assert m["competitor_count"] == 2

        # Test 9: positioning_migration
        mg = engine.positioning_migration(
            "EQUITY", "DIGITAL_POSTURE",
            [("Q4-2025", "2025-12-31"), ("Q1-2026", "2026-03-31")],
        )
        assert len(mg["trajectory"]) == 2
        assert "spec_deviation" in mg

    print("  ✅ competitor_digital_intel self-test PASS")


if __name__ == "__main__":
    _self_test()

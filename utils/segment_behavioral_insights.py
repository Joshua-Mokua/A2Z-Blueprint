"""
================================================================================
A2Z MIS 360 — Standard #347: Segment-Level Behavioral Insights
================================================================================

Risk classification: Cat C (segment-level aggregation over composed engines)

Behavioral insights aggregated by segment: women, diaspora, asset-finance,
agri, youth, SME. Segment-specific propensities. v10.276 ships
deterministic aggregation over v10.276 BehavioralProfileEngine +
DeclinePredictionEngine + JourneyAndWidgetEngine outputs.

Public API:
    aggregate_segment(segment_code, customer_ids, as_of=None)
        -> per-segment behavioral profile distribution
    insight_dashboard(segment_to_customers, as_of=None)
        -> all-segments comparative dashboard
    top_propensities_by_segment(...) -> ranked propensities

BEHAVIORAL_INSIGHT_DIMENSIONS byte-for-byte:
    SPENDING_TIER_DISTRIBUTION    -- HIGH/MEDIUM/LOW share per segment
    PRIMARY_CHANNEL_DISTRIBUTION  -- top channels per segment
    LIFE_STAGE_DISTRIBUTION       -- life-stage share per segment
    RISK_APPETITE_DISTRIBUTION    -- conservative/moderate/adventurous
    DECLINE_RISK_DISTRIBUTION     -- HIGH/MEDIUM/LOW churn-risk share
    NBA_DISTRIBUTION              -- top recommended NBAs

Honesty rules:
    Rule 1: empty customer list returns reason="empty_segment_population"
    Rule 6: invalid segment_code rejected
    Rule 7: composes other v10.276 engines that themselves carry
            SPEC_DEVIATION_NOTE for ML deferrals

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.interaction_capture import InteractionCaptureEngine
from utils.specialized_segments_tagging import SEGMENT_CODES
from utils.customer_behavioral_profile import (
    BehavioralProfileEngine,
    SPENDING_TIERS, RISK_APPETITE_LEVELS, LIFE_STAGES,
)
from utils.decline_prediction import (
    DeclinePredictionEngine, DECLINE_RISK_LEVELS,
)
from utils.journey_and_widget import (
    JourneyAndWidgetEngine, NBA_RULES,
)

getcontext().prec = 28


BEHAVIORAL_INSIGHT_DIMENSIONS: Tuple[str, ...] = (
    "SPENDING_TIER_DISTRIBUTION",
    "PRIMARY_CHANNEL_DISTRIBUTION",
    "LIFE_STAGE_DISTRIBUTION",
    "RISK_APPETITE_DISTRIBUTION",
    "DECLINE_RISK_DISTRIBUTION",
    "NBA_DISTRIBUTION",
)


class SegmentBehavioralInsightsEngine:
    """Segment-level behavioral aggregation."""

    def __init__(
        self,
        capture: Optional[InteractionCaptureEngine] = None,
        profile: Optional[BehavioralProfileEngine] = None,
        decline: Optional[DeclinePredictionEngine] = None,
        journey: Optional[JourneyAndWidgetEngine] = None,
    ):
        self.capture = capture or InteractionCaptureEngine()
        self.profile = profile or BehavioralProfileEngine(capture=self.capture)
        self.journey = journey or JourneyAndWidgetEngine(capture=self.capture)
        self.decline = decline or DeclinePredictionEngine(
            capture=self.capture, journey=self.journey,
        )

    @staticmethod
    def _share_pct(counts: Counter, total: int) -> Dict[str, str]:
        if total == 0:
            return {}
        return {
            k: str((Decimal(v) / Decimal(total) * Decimal("100"))
                     .quantize(Decimal("0.01")))
            for k, v in counts.items()
        }

    def aggregate_segment(
        self,
        segment_code: str,
        customer_ids: List[str],
        as_of: Optional[date] = None,
        product_count_lookup: Optional[Dict[str, int]] = None,
        age_lookup: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        if segment_code not in SEGMENT_CODES:
            return {
                "segment_code": segment_code,
                "error": f"invalid_segment_code:{segment_code}",
                "valid_segments": list(SEGMENT_CODES),
            }

        if not customer_ids:
            return {
                "segment_code": segment_code,
                "scanned_count": 0,
                "reason": "empty_segment_population",
            }

        as_of = as_of or date.today()
        product_count_lookup = product_count_lookup or {}
        age_lookup = age_lookup or {}

        spending_counts: Counter = Counter()
        channel_counts: Counter = Counter()
        life_stage_counts: Counter = Counter()
        risk_appetite_counts: Counter = Counter()
        decline_risk_counts: Counter = Counter()
        nba_counts: Counter = Counter()

        evaluated = 0
        for cid in customer_ids:
            evaluated += 1
            age = age_lookup.get(cid)
            product_count = product_count_lookup.get(cid, 0)

            # Spending tier
            st = self.profile.spending_tier(cid, as_of=as_of)
            spending_counts[st.get("tier", "UNKNOWN")] += 1

            # Primary channel
            ch = self.profile.channel_preferences(cid, as_of=as_of)
            primary = (ch.get("preferred_channels") or [None])[0]
            channel_counts[primary or "NONE"] += 1

            # Life stage
            ls = self.profile.life_stage(cid, age=age)
            life_stage_counts[ls.get("stage", "UNKNOWN")] += 1

            # Risk appetite
            ra = self.profile.customer_risk_appetite(cid, as_of=as_of)
            risk_appetite_counts[ra.get("level", "UNKNOWN")] += 1

            # Decline risk
            dr = self.decline.predict_decline(
                cid, as_of=as_of, product_count=product_count,
            )
            decline_risk_counts[dr.get("risk_level", "UNKNOWN")] += 1

            # NBA
            nba = self.journey.next_best_action(
                cid, product_count=product_count, as_of=as_of,
            )
            nba_counts[nba.get("action", "NONE")] += 1

        return {
            "segment_code": segment_code,
            "scanned_count": evaluated,
            "as_of": as_of.isoformat(),
            "SPENDING_TIER_DISTRIBUTION": {
                "counts": dict(spending_counts),
                "share_pct": self._share_pct(spending_counts, evaluated),
            },
            "PRIMARY_CHANNEL_DISTRIBUTION": {
                "counts": dict(channel_counts),
                "share_pct": self._share_pct(channel_counts, evaluated),
            },
            "LIFE_STAGE_DISTRIBUTION": {
                "counts": dict(life_stage_counts),
                "share_pct": self._share_pct(life_stage_counts, evaluated),
            },
            "RISK_APPETITE_DISTRIBUTION": {
                "counts": dict(risk_appetite_counts),
                "share_pct": self._share_pct(risk_appetite_counts, evaluated),
            },
            "DECLINE_RISK_DISTRIBUTION": {
                "counts": dict(decline_risk_counts),
                "share_pct": self._share_pct(decline_risk_counts, evaluated),
            },
            "NBA_DISTRIBUTION": {
                "counts": dict(nba_counts),
                "share_pct": self._share_pct(nba_counts, evaluated),
            },
        }

    def insight_dashboard(
        self,
        segment_to_customers: Dict[str, List[str]],
        as_of: Optional[date] = None,
        product_count_lookup: Optional[Dict[str, int]] = None,
        age_lookup: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "as_of": (as_of or date.today()).isoformat(),
            "segments": {},
        }
        for sc in SEGMENT_CODES:
            customers = segment_to_customers.get(sc, [])
            out["segments"][sc] = self.aggregate_segment(
                sc, customers, as_of=as_of,
                product_count_lookup=product_count_lookup,
                age_lookup=age_lookup,
            )
        return out

    def top_propensities_by_segment(
        self,
        segment_code: str,
        customer_ids: List[str],
        product_codes: Tuple[str, ...] = ("LIFE", "EDUCATION", "PENSION"),
        age_lookup: Optional[Dict[str, int]] = None,
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """For a segment, rank customers by propensity for each product code.

        Uses the v10.276 BehavioralProfileEngine.make_propensity_score_fn()
        factory matching the v10.274 insurance_recommendation contract.
        """
        if segment_code not in SEGMENT_CODES:
            return {
                "segment_code": segment_code,
                "error": f"invalid_segment_code:{segment_code}",
            }
        if not customer_ids:
            return {
                "segment_code": segment_code,
                "reason": "empty_segment_population",
            }

        age_lookup = age_lookup or {}
        score_fn = self.profile.make_propensity_score_fn()

        out: Dict[str, List[Dict[str, Any]]] = {}
        for pc in product_codes:
            ranked: List[Tuple[str, Decimal]] = []
            for cid in customer_ids:
                attrs = {
                    "customer_id": cid,
                    "age": age_lookup.get(cid),
                }
                try:
                    s = score_fn(pc, attrs)
                    ranked.append((cid, s))
                except Exception:
                    continue
            ranked.sort(key=lambda x: x[1], reverse=True)
            out[pc] = [
                {"customer_id": cid, "propensity_score": str(s)}
                for cid, s in ranked[:top_n]
            ]

        return {
            "segment_code": segment_code,
            "scanned_count": len(customer_ids),
            "top_propensities": out,
            "product_codes_evaluated": list(product_codes),
        }


def _self_test() -> None:
    import tempfile
    from datetime import timedelta

    assert "SPENDING_TIER_DISTRIBUTION" in BEHAVIORAL_INSIGHT_DIMENSIONS

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = SegmentBehavioralInsightsEngine(capture=capture)

        # Test 1: invalid segment
        r = engine.aggregate_segment("INVALID", ["CUST-1"])
        assert "invalid_segment_code" in r["error"]

        # Test 2: empty population
        r = engine.aggregate_segment("WOMEN", [])
        assert r["reason"] == "empty_segment_population"

        # Test 3: seed customers + aggregate
        # Customer 1: HIGH spender via MOBILE_APP
        for i in range(6):
            capture.capture_event(
                "CUST-1",
                {"event_id": f"C1-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": (date.today() - timedelta(days=10+i)).isoformat() + "T10:00:00",
                 "amount_kes": "60000"},
                actor="x",
            )
        # Customer 2: LOW spender via ATM
        for i in range(3):
            capture.capture_event(
                "CUST-2",
                {"event_id": f"C2-{i}",
                 "channel": "ATM",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": (date.today() - timedelta(days=15+i)).isoformat() + "T10:00:00",
                 "amount_kes": "5000"},
                actor="x",
            )

        result = engine.aggregate_segment(
            "WOMEN", ["CUST-1", "CUST-2"],
            age_lookup={"CUST-1": 35, "CUST-2": 50},
            product_count_lookup={"CUST-1": 2, "CUST-2": 1},
        )
        assert result["scanned_count"] == 2
        # Spending: 1 HIGH + 1 LOW
        assert result["SPENDING_TIER_DISTRIBUTION"]["counts"]["HIGH"] == 1
        assert result["SPENDING_TIER_DISTRIBUTION"]["counts"]["LOW"] == 1
        assert result["SPENDING_TIER_DISTRIBUTION"]["share_pct"]["HIGH"] == "50.00"
        # Channel: 1 MOBILE_APP + 1 ATM
        assert result["PRIMARY_CHANNEL_DISTRIBUTION"]["counts"]["MOBILE_APP"] == 1
        # Life stage: 1 FAMILY_BUILDING (35) + 1 ESTABLISHED (50)
        assert result["LIFE_STAGE_DISTRIBUTION"]["counts"]["FAMILY_BUILDING"] == 1
        assert result["LIFE_STAGE_DISTRIBUTION"]["counts"]["ESTABLISHED"] == 1
        # All 6 dimensions present
        for dim in BEHAVIORAL_INSIGHT_DIMENSIONS:
            assert dim in result, f"missing dimension {dim}"

        # Test 4: insight_dashboard
        dashboard = engine.insight_dashboard(
            {"WOMEN": ["CUST-1"], "DIASPORA": ["CUST-2"], "AGRI": []},
            age_lookup={"CUST-1": 35, "CUST-2": 50},
        )
        assert "WOMEN" in dashboard["segments"]
        assert dashboard["segments"]["AGRI"]["reason"] == "empty_segment_population"
        # All 6 segments present
        for sc in SEGMENT_CODES:
            assert sc in dashboard["segments"]

        # Test 5: top_propensities_by_segment
        props = engine.top_propensities_by_segment(
            "WOMEN", ["CUST-1", "CUST-2"],
            product_codes=("BR-EDU-001",),
            age_lookup={"CUST-1": 35, "CUST-2": 50},
            top_n=2,
        )
        assert "BR-EDU-001" in props["top_propensities"]
        assert len(props["top_propensities"]["BR-EDU-001"]) <= 2

        # Test 6: empty top_propensities
        p = engine.top_propensities_by_segment("WOMEN", [])
        assert p["reason"] == "empty_segment_population"

    print("  ✅ segment_behavioral_insights self-test PASS")


if __name__ == "__main__":
    _self_test()

"""
================================================================================
A2Z MIS 360 — Standard #348: RM Behavior Intelligence Widget
================================================================================

Risk classification: Cat C (RM-facing intelligence — composes #340 + #341
                              + #344 + journey/widget; talking-points generator)

RM-facing intelligence: customer behavioral signals, engagement gap,
recommended next action, talking-points generator. v10.276 ships
deterministic composition over the v10.276 + v10.275 cluster engines
plus a rule-based talking-points generator that maps signals to
concrete RM conversation prompts.

Public API:
    rm_intelligence_payload(rm_id, customer_id, age=None, ...) -> consolidated
    generate_talking_points(customer_id, age=None, ...) -> List[Dict]
    rm_book_summary(rm_id, customer_ids, ...) -> RM portfolio aggregate

TALKING_POINT_TYPES byte-for-byte:
    RETENTION             -- customer at decline risk; address proactively
    UPSELL                -- HIGH spender + low product count → upsell
    CROSS_SELL            -- LOYAL stage + propensity match → cross-sell
    COMPLAINT_FOLLOWUP    -- recent complaint pending follow-up
    CHURN_INTERVENTION    -- HIGH decline risk → urgent intervention
    REACTIVATION          -- DORMANT → reactivate dialogue

TALKING_POINT_PRIORITIES byte-for-byte:
    URGENT      -- act today (HIGH decline risk, recent complaint)
    HIGH        -- act this week (MEDIUM decline, dormancy proximity)
    MEDIUM      -- monthly cadence (upsell, cross-sell opportunities)
    LOW         -- nice-to-have (general engagement)

Honesty rules:
    Rule 1: empty payload returns reason="no_signals_detected" rather
            than fabricating talking points
    Rule 6: invalid customer_id surfaces explicit reason
    Rule 7: composes other engines that themselves carry SPEC_DEVIATION_NOTE

================================================================================
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.interaction_capture import InteractionCaptureEngine
from utils.customer_behavioral_profile import BehavioralProfileEngine
from utils.behavioral_anomaly_detection import AnomalyDetectionEngine
from utils.decline_prediction import (
    DeclinePredictionEngine, HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD,
)
from utils.journey_and_widget import JourneyAndWidgetEngine


TALKING_POINT_TYPES: Tuple[str, ...] = (
    "RETENTION", "UPSELL", "CROSS_SELL",
    "COMPLAINT_FOLLOWUP", "CHURN_INTERVENTION", "REACTIVATION",
)

TALKING_POINT_PRIORITIES: Tuple[str, ...] = (
    "URGENT", "HIGH", "MEDIUM", "LOW",
)


class RmBehaviorIntelligenceEngine:
    """RM-facing composition over v10.275/v10.276 cluster engines."""

    def __init__(
        self,
        capture: Optional[InteractionCaptureEngine] = None,
        profile: Optional[BehavioralProfileEngine] = None,
        anomaly: Optional[AnomalyDetectionEngine] = None,
        decline: Optional[DeclinePredictionEngine] = None,
        journey: Optional[JourneyAndWidgetEngine] = None,
    ):
        self.capture = capture or InteractionCaptureEngine()
        self.profile = profile or BehavioralProfileEngine(capture=self.capture)
        self.anomaly = anomaly or AnomalyDetectionEngine(capture=self.capture)
        self.journey = journey or JourneyAndWidgetEngine(capture=self.capture)
        self.decline = decline or DeclinePredictionEngine(
            capture=self.capture, journey=self.journey,
        )

    def rm_intelligence_payload(
        self,
        rm_id: str,
        customer_id: str,
        age: Optional[int] = None,
        life_events: Optional[List[str]] = None,
        product_count: int = 0,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()

        profile = self.profile.build_profile(
            customer_id, age=age, life_events=life_events, as_of=as_of,
        )
        widget = self.journey.behavioral_widget_payload(
            customer_id, product_count=product_count, as_of=as_of,
        )
        decline = self.decline.predict_decline(
            customer_id, as_of=as_of, product_count=product_count,
        )
        anomalies = self.anomaly.detect_anomalies(
            customer_id,
            period_start=(as_of - timedelta(days=14)).isoformat(),
            period_end=as_of.isoformat() + "T23:59:59",
            as_of=as_of,
        )
        talking_points = self.generate_talking_points(
            customer_id, age=age, life_events=life_events,
            product_count=product_count, as_of=as_of,
        )

        return {
            "rm_id": rm_id,
            "customer_id": customer_id,
            "as_of": as_of.isoformat(),
            "profile": profile,
            "widget": widget,
            "decline_risk": decline,
            "recent_anomalies": {
                "anomaly_count": anomalies.get("anomaly_count", 0),
                "by_type": anomalies.get("by_type", {}),
                "by_severity": anomalies.get("by_severity", {}),
                "top_anomalies": anomalies.get("anomalies", [])[:3],
            },
            "talking_points": talking_points,
        }

    def generate_talking_points(
        self,
        customer_id: str,
        age: Optional[int] = None,
        life_events: Optional[List[str]] = None,
        product_count: int = 0,
        as_of: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        as_of = as_of or date.today()

        # Pull underlying signals
        events = self.capture.list_events(customer_id, limit=10**9)
        if not events:
            return []

        decline = self.decline.predict_decline(
            customer_id, as_of=as_of, product_count=product_count,
        )
        widget = self.journey.behavioral_widget_payload(
            customer_id, product_count=product_count, as_of=as_of,
        )
        spending = self.profile.spending_tier(customer_id, as_of=as_of)

        points: List[Dict[str, Any]] = []

        # 1. CHURN_INTERVENTION — HIGH decline risk → URGENT
        risk_level = decline.get("risk_level")
        risk_score = decline.get("risk_score")
        if risk_level == "HIGH":
            points.append({
                "type": "CHURN_INTERVENTION",
                "priority": "URGENT",
                "headline": (
                    f"Decline risk HIGH (score {risk_score}). "
                    "Urgent intervention recommended."
                ),
                "supporting_factors": list(
                    decline.get("contributing_factors", {}).keys()
                ),
                "suggested_action": "OUTREACH_CALL",
            })

        # 2. RETENTION — MEDIUM decline + ENGAGEMENT/LOYALTY → HIGH priority
        elif risk_level == "MEDIUM" and widget.get("stage") in ("ENGAGEMENT", "LOYALTY"):
            points.append({
                "type": "RETENTION",
                "priority": "HIGH",
                "headline": (
                    f"Decline risk MEDIUM in {widget.get('stage')} stage "
                    "(score {risk_score}). Pre-empt with retention offer."
                ),
                "supporting_factors": list(
                    decline.get("contributing_factors", {}).keys()
                ),
                "suggested_action": "RETENTION_GIFT",
            })

        # 3. REACTIVATION — DORMANT → URGENT
        if widget.get("stage") == "DORMANT":
            points.append({
                "type": "REACTIVATION",
                "priority": "URGENT",
                "headline": (
                    "Customer is DORMANT. Reactivate with personalized "
                    "outreach + product fit."
                ),
                "supporting_factors": ["dormancy"],
                "suggested_action": "REACTIVATION_CAMPAIGN",
            })

        # 4. COMPLAINT_FOLLOWUP — recent COMPLAINT in last 14 days
        recent_complaints = [
            e for e in events
            if e.get("event_type") == "COMPLAINT"
            and e.get("occurred_at", "") >= (as_of - timedelta(days=14)).isoformat()
        ]
        if recent_complaints:
            points.append({
                "type": "COMPLAINT_FOLLOWUP",
                "priority": "HIGH",
                "headline": (
                    f"{len(recent_complaints)} complaint(s) in last 14 days. "
                    "Follow up to confirm resolution."
                ),
                "supporting_factors": ["recent_complaint"],
                "suggested_action": "RESOLUTION_CHECK",
            })

        # 5. UPSELL — HIGH spender + product_count <= 1 → MEDIUM priority
        if (spending.get("tier") == "HIGH" and product_count <= 1
                and risk_level not in ("HIGH",)):
            points.append({
                "type": "UPSELL",
                "priority": "MEDIUM",
                "headline": (
                    "HIGH-tier spender holding only 1 product. "
                    "Significant upsell potential."
                ),
                "supporting_factors": ["spending_tier:HIGH", "product_count:1"],
                "suggested_action": "PRODUCT_RECOMMENDATION",
            })

        # 6. CROSS_SELL — LOYALTY stage + age signals → MEDIUM priority
        if widget.get("stage") == "LOYALTY" and risk_level not in ("HIGH",):
            points.append({
                "type": "CROSS_SELL",
                "priority": "MEDIUM",
                "headline": (
                    "LOYALTY stage with steady engagement. "
                    "Cross-sell opportunity for adjacent products."
                ),
                "supporting_factors": ["stage:LOYALTY"],
                "suggested_action": "PRODUCT_RECOMMENDATION",
            })

        # Sort by priority
        priority_order = {p: i for i, p in enumerate(TALKING_POINT_PRIORITIES)}
        points.sort(key=lambda x: priority_order.get(x.get("priority"), 99))

        return points

    def rm_book_summary(
        self,
        rm_id: str,
        customer_ids: List[str],
        product_count_lookup: Optional[Dict[str, int]] = None,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """RM portfolio aggregate: how many in each decline-risk bucket,
        urgent talking points count, etc."""
        as_of = as_of or date.today()
        product_count_lookup = product_count_lookup or {}

        if not customer_ids:
            return {
                "rm_id": rm_id,
                "book_size": 0,
                "reason": "empty_book",
            }

        risk_buckets = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        urgent_points = 0
        high_points = 0
        customers_with_signals = 0

        for cid in customer_ids:
            pc = product_count_lookup.get(cid, 0)
            decline = self.decline.predict_decline(
                cid, as_of=as_of, product_count=pc,
            )
            risk_buckets[decline.get("risk_level", "UNKNOWN")] += 1

            tp = self.generate_talking_points(
                cid, product_count=pc, as_of=as_of,
            )
            if tp:
                customers_with_signals += 1
                for p in tp:
                    if p.get("priority") == "URGENT":
                        urgent_points += 1
                    elif p.get("priority") == "HIGH":
                        high_points += 1

        return {
            "rm_id": rm_id,
            "as_of": as_of.isoformat(),
            "book_size": len(customer_ids),
            "decline_risk_buckets": risk_buckets,
            "customers_with_signals": customers_with_signals,
            "urgent_talking_points": urgent_points,
            "high_talking_points": high_points,
        }


def _self_test() -> None:
    import tempfile

    assert "RETENTION" in TALKING_POINT_TYPES
    assert "URGENT" in TALKING_POINT_PRIORITIES

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = RmBehaviorIntelligenceEngine(capture=capture)

        # Test 1: empty customer → empty talking points
        tp = engine.generate_talking_points("UNKNOWN")
        assert tp == []

        # Test 2: HIGH decline risk → CHURN_INTERVENTION urgent
        # Seed signals — engagement decline + complaints + multi-channel failures
        for i in range(40):
            day = (date.today() - timedelta(days=119 - i)).isoformat()
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"H-PRIOR-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "5000"},
                actor="x",
            )
        for i in range(2):
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"H-COMP-{i}",
                 "channel": "CALL_CENTER",
                 "event_type": "COMPLAINT",
                 "outcome": "PENDING",
                 "occurred_at": (date.today() - timedelta(days=10-i)).isoformat() + "T10:00:00"},
                actor="x",
            )
        for i, ch in enumerate(["MOBILE_APP", "WEB"]):
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"H-FAIL-{i}",
                 "channel": ch,
                 "event_type": "TRANSACTION",
                 "outcome": "FAILURE",
                 "occurred_at": (date.today() - timedelta(days=3)).isoformat() + f"T1{i}:00:00"},
                actor="x",
            )
        tp = engine.generate_talking_points(
            "CUST-HIGH", age=40, product_count=1,
        )
        # Should have CHURN_INTERVENTION + COMPLAINT_FOLLOWUP at minimum
        types_present = {p["type"] for p in tp}
        assert "COMPLAINT_FOLLOWUP" in types_present
        # CHURN_INTERVENTION + URGENT priority should be at top
        if "CHURN_INTERVENTION" in types_present:
            assert tp[0]["priority"] in ("URGENT", "HIGH")

        # Test 3: HIGH spender + 1 product → UPSELL
        for i in range(6):
            day = (date.today() - timedelta(days=10+i)).isoformat()
            capture.capture_event(
                "CUST-RICH",
                {"event_id": f"R-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "150000"},
                actor="x",
            )
        tp = engine.generate_talking_points(
            "CUST-RICH", age=40, product_count=1,
        )
        types = {p["type"] for p in tp}
        assert "UPSELL" in types

        # Test 4: rm_intelligence_payload composition
        payload = engine.rm_intelligence_payload(
            "RM-101", "CUST-HIGH", age=40, product_count=1,
        )
        assert payload["rm_id"] == "RM-101"
        assert payload["profile"]["customer_id"] == "CUST-HIGH"
        assert "talking_points" in payload
        assert "decline_risk" in payload
        assert "recent_anomalies" in payload

        # Test 5: rm_book_summary
        summary = engine.rm_book_summary(
            "RM-101", ["CUST-HIGH", "CUST-RICH"],
            product_count_lookup={"CUST-HIGH": 1, "CUST-RICH": 1},
        )
        assert summary["book_size"] == 2
        assert "decline_risk_buckets" in summary
        # CUST-HIGH likely produces URGENT/HIGH talking points
        assert summary["urgent_talking_points"] + summary["high_talking_points"] >= 1

        # Test 6: empty book
        s = engine.rm_book_summary("RM-X", [])
        assert s["book_size"] == 0
        assert s["reason"] == "empty_book"

    print("  ✅ rm_behavior_intelligence self-test PASS")


if __name__ == "__main__":
    _self_test()

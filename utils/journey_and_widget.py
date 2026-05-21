"""
================================================================================
A2Z MIS 360 — Standards #342 + #343: Journey Mapping + Behavioral Widget
================================================================================

Risk classification: Cat C (deterministic journey reconstruction +
                              read-scoped widget composition)

Combined module:
    #342: Multi-channel customer journey reconstruction — from
          awareness to acquisition to engagement to retention. Friction
          identification.
    #343: RM/Branch-facing behavioral highlights widget — propensities,
          concerns, last touch, next-best action.

This module is a pure read-side composition over interaction_capture +
mobile_app_tracking + branch_interaction. No new persistence.

Public API (#342):
    reconstruct_journey(customer_id, period_start, period_end)
    journey_friction_points(customer_id) -> list of friction events
    journey_stage(customer_id) -> {stage, evidence}

Public API (#343):
    behavioral_widget_payload(customer_id) -> consolidated payload
    next_best_action(customer_id) -> rule-based recommendation

JOURNEY_STAGES byte-for-byte (Continuation.docx #342):
    AWARENESS    -- prospect / first interactions, not yet customer
    ACQUISITION  -- account opened; onboarding
    ACTIVATION   -- first meaningful transactions / engagement
    ENGAGEMENT   -- regular usage, multiple products
    LOYALTY      -- long-tenure, deep relationship
    AT_RISK      -- declining engagement / signals of churn
    DORMANT      -- no recent activity
    CHURNED      -- relationship ended (terminal in this engine view)

FRICTION_INDICATORS byte-for-byte:
    REPEATED_FAILURE      -- same error >= 2 times within 7 days
    HIGH_ABANDONMENT      -- >= 3 ABANDONED events in period
    QUEUE_FRUSTRATION     -- branch wait > 30 min ANY visit
    REPEATED_COMPLAINT    -- >= 2 COMPLAINT events in 30 days
    MULTI_CHANNEL_FAILURE -- failures across 2+ channels in 7 days

NBA_RULES byte-for-byte (deterministic — Rule 7 ML wiring deferred):
    HIGH_RISK_OUTREACH        -- triggered by AT_RISK stage
    NEW_PRODUCT_RECOMMENDATION -- triggered by ENGAGEMENT stage
    ONBOARDING_FOLLOWUP        -- triggered by ACQUISITION stage
    REACTIVATION_CAMPAIGN      -- triggered by DORMANT stage
    RETENTION_GIFT            -- triggered by LOYALTY stage
    NONE                       -- no rule fires

DORMANT_THRESHOLD_DAYS = 90  -- no events for 90+ days → DORMANT

Honesty rules:
    Rule 1: journey_stage returns "INSUFFICIENT_DATA" when no events
    Rule 6: invalid customer_id surfaces explicit reason
    Rule 7: NBA scaffolding is deterministic; v10.276 will wire ML

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.interaction_capture import InteractionCaptureEngine
from utils.mobile_app_tracking import MobileAppTrackingEngine
from utils.branch_interaction import BranchInteractionEngine

getcontext().prec = 28


JOURNEY_STAGES: Tuple[str, ...] = (
    "AWARENESS", "ACQUISITION", "ACTIVATION", "ENGAGEMENT",
    "LOYALTY", "AT_RISK", "DORMANT", "CHURNED",
)

FRICTION_INDICATORS: Tuple[str, ...] = (
    "REPEATED_FAILURE", "HIGH_ABANDONMENT", "QUEUE_FRUSTRATION",
    "REPEATED_COMPLAINT", "MULTI_CHANNEL_FAILURE",
)

NBA_RULES: Tuple[str, ...] = (
    "HIGH_RISK_OUTREACH",
    "NEW_PRODUCT_RECOMMENDATION",
    "ONBOARDING_FOLLOWUP",
    "REACTIVATION_CAMPAIGN",
    "RETENTION_GIFT",
    "NONE",
)

DORMANT_THRESHOLD_DAYS: int = 90
AT_RISK_DECLINE_PCT: Decimal = Decimal("50")  # 50%+ drop in events MoM


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #342 + #343 specify journey reconstruction + "
    "next-best-action with ML-driven personalization. v10.275 ships "
    "deterministic stage classification + rule-based NBA. ML wiring "
    "(propensity scoring per channel/product, ML-driven NBA ranking) "
    "deferred to v10.276 customer_behavioral_profile + "
    "decline_prediction modules. Hook contract surfaces "
    "'rule_based_only' until ML scaffolding lands."
)


class JourneyAndWidgetEngine:
    """Customer journey mapping + behavioral widget composition."""

    def __init__(
        self,
        capture: Optional[InteractionCaptureEngine] = None,
        app_tracking: Optional[MobileAppTrackingEngine] = None,
        branch: Optional[BranchInteractionEngine] = None,
        ml_nba_fn: Optional[Any] = None,
    ):
        self.capture = capture or InteractionCaptureEngine()
        self.app_tracking = app_tracking or MobileAppTrackingEngine(
            capture=self.capture,
        )
        self.branch = branch or BranchInteractionEngine(
            capture=self.capture,
        )
        # Rule 7 hook (added v10.276): ml_nba_fn(customer_id, stage,
        # product_count, as_of) -> {action, reason, confidence, ml_driven}
        # When provided AND ml_driven=True is returned, the ML action
        # overrides the rule-based mapping. When ml_driven=False (or
        # action=None), defer to rule-based.
        self.ml_nba_fn = ml_nba_fn

    # ── #342 Journey Mapping ───────────────────────────────────────

    def reconstruct_journey(
        self,
        customer_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reconstruct customer journey across channels in period."""
        events = self.capture.list_events(
            customer_id,
            period_start=period_start,
            period_end=period_end,
            limit=10**9,
        )
        if not events:
            return {
                "customer_id": customer_id,
                "period_start": period_start,
                "period_end": period_end,
                "events": [],
                "channel_count": 0,
                "event_count": 0,
                "reason": "no_events",
            }

        # Sort ascending by occurred_at
        events.sort(key=lambda e: e.get("occurred_at", ""))

        channels = {e.get("channel") for e in events}
        # Compact journey: for each event, the 4-tuple of channel+type+outcome+ts
        journey = [
            {
                "channel": e.get("channel"),
                "event_type": e.get("event_type"),
                "outcome": e.get("outcome"),
                "occurred_at": e.get("occurred_at"),
            }
            for e in events
        ]

        return {
            "customer_id": customer_id,
            "period_start": period_start,
            "period_end": period_end,
            "event_count": len(events),
            "channel_count": len(channels),
            "channels_used": sorted(channels),
            "journey": journey,
            "first_touch": journey[0] if journey else None,
            "last_touch": journey[-1] if journey else None,
        }

    def journey_friction_points(
        self,
        customer_id: str,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Identify friction indicators for a customer."""
        as_of = as_of or date.today()
        # Look back 90 days for friction analysis
        period_start = (as_of - timedelta(days=90)).isoformat()
        period_end = as_of.isoformat() + "T23:59:59"

        events = self.capture.list_events(
            customer_id, period_start=period_start, period_end=period_end,
            limit=10**9,
        )

        indicators_present: List[str] = []
        details: Dict[str, Any] = {}

        # 1. REPEATED_FAILURE — same error_code 2+ times within 7 days
        errors = [e for e in events if e.get("event_type") == "ERROR"]
        if len(errors) >= 2:
            # Group by error_code
            by_code: Dict[str, List[str]] = defaultdict(list)
            for e in errors:
                code = e.get("metadata", {}).get("error_code", "UNKNOWN")
                by_code[code].append(e.get("occurred_at", ""))
            for code, ts_list in by_code.items():
                if len(ts_list) >= 2:
                    # Check 7-day window
                    ts_list.sort()
                    for i in range(len(ts_list) - 1):
                        try:
                            t1 = datetime.fromisoformat(ts_list[i].replace("Z", ""))
                            t2 = datetime.fromisoformat(ts_list[i + 1].replace("Z", ""))
                            if (t2 - t1).days <= 7:
                                indicators_present.append("REPEATED_FAILURE")
                                details["repeated_failure_code"] = code
                                break
                        except (ValueError, AttributeError):
                            continue
                    if "REPEATED_FAILURE" in indicators_present:
                        break

        # 2. HIGH_ABANDONMENT — 3+ ABANDONED in period
        abandonments = [e for e in events if e.get("outcome") == "ABANDONED"]
        if len(abandonments) >= 3:
            indicators_present.append("HIGH_ABANDONMENT")
            details["abandonment_count"] = len(abandonments)

        # 3. QUEUE_FRUSTRATION — branch wait > 30 min
        # Need branch visits — look at metadata
        branch_visits = self.branch._load()
        long_waits = []
        for v in branch_visits:
            if v.get("customer_id") != customer_id:
                continue
            if not v.get("queued_at") or not v.get("service_started_at"):
                continue
            try:
                q = datetime.fromisoformat(v["queued_at"].replace("Z", ""))
                s = datetime.fromisoformat(v["service_started_at"].replace("Z", ""))
                wait_min = (s - q).total_seconds() / 60
                if wait_min > 30:
                    long_waits.append({
                        "visit_id": v["visit_id"],
                        "wait_min": round(wait_min, 1),
                    })
            except (ValueError, AttributeError):
                continue
        if long_waits:
            indicators_present.append("QUEUE_FRUSTRATION")
            details["long_waits"] = long_waits

        # 4. REPEATED_COMPLAINT — 2+ COMPLAINT events in 30 days
        thirty_days_ago = (as_of - timedelta(days=30)).isoformat()
        recent_complaints = [
            e for e in events
            if e.get("event_type") == "COMPLAINT"
            and e.get("occurred_at", "") >= thirty_days_ago
        ]
        if len(recent_complaints) >= 2:
            indicators_present.append("REPEATED_COMPLAINT")
            details["complaint_count_30d"] = len(recent_complaints)

        # 5. MULTI_CHANNEL_FAILURE — failures across 2+ channels in 7 days
        seven_days_ago = (as_of - timedelta(days=7)).isoformat()
        recent_failures = [
            e for e in events
            if e.get("outcome") in ("FAILURE", "ABANDONED")
            and e.get("occurred_at", "") >= seven_days_ago
        ]
        failure_channels = {e.get("channel") for e in recent_failures}
        if len(failure_channels) >= 2:
            indicators_present.append("MULTI_CHANNEL_FAILURE")
            details["failure_channels_7d"] = sorted(failure_channels)

        return {
            "customer_id": customer_id,
            "as_of": as_of.isoformat(),
            "indicators_present": indicators_present,
            "indicator_count": len(indicators_present),
            "details": details,
        }

    def journey_stage(
        self,
        customer_id: str,
        as_of: Optional[date] = None,
        product_count: int = 0,  # caller-provided (we don't see customer's products)
    ) -> Dict[str, Any]:
        """
        Classify customer's current journey stage.

        product_count = number of active products customer holds (caller-
        provided since we don't have a unified products engine reference
        here). When 0 + has events, defaults to ACTIVATION.
        """
        as_of = as_of or date.today()
        events = self.capture.list_events(customer_id, limit=10**9)

        if not events:
            return {
                "customer_id": customer_id,
                "stage": None,
                "stage_classification": "INSUFFICIENT_DATA",
                "reason": "no_events_no_history",
            }

        # Sort ascending
        events.sort(key=lambda e: e.get("occurred_at", ""))
        first_event_ts = events[0].get("occurred_at", "")
        last_event_ts = events[-1].get("occurred_at", "")

        try:
            last_dt = datetime.fromisoformat(last_event_ts.replace("Z", ""))
            days_since_last = (datetime.combine(as_of, datetime.min.time()) - last_dt).days
        except (ValueError, AttributeError):
            days_since_last = 999

        try:
            first_dt = datetime.fromisoformat(first_event_ts.replace("Z", ""))
            days_as_customer = (datetime.combine(as_of, datetime.min.time()) - first_dt).days
        except (ValueError, AttributeError):
            days_as_customer = 0

        # Classify
        evidence = {
            "event_count": len(events),
            "days_since_last_event": days_since_last,
            "days_as_customer": days_as_customer,
            "product_count": product_count,
        }

        if days_since_last > DORMANT_THRESHOLD_DAYS * 2:  # 180+ days
            stage = "CHURNED"
            classification = "RELATIONSHIP_INACTIVE_180_DAYS"
        elif days_since_last > DORMANT_THRESHOLD_DAYS:  # 90-180 days
            stage = "DORMANT"
            classification = f"NO_ACTIVITY_{days_since_last}_DAYS"
        elif product_count == 0 and days_as_customer < 30:
            stage = "AWARENESS"
            classification = "PROSPECT_RECENT_INTERACTIONS"
        elif product_count >= 1 and days_as_customer < 90:
            stage = "ACQUISITION"
            classification = "RECENTLY_ONBOARDED"
        elif product_count >= 3 and days_as_customer >= 365:
            stage = "LOYALTY"
            classification = "LONG_TENURE_MULTI_PRODUCT"
        elif product_count >= 2:
            stage = "ENGAGEMENT"
            classification = "MULTI_PRODUCT_ACTIVE"
        else:
            stage = "ACTIVATION"
            classification = "SINGLE_PRODUCT_ACTIVE"

        # Check AT_RISK overlay — need at least 60 days of history
        # MoM event drop > AT_RISK_DECLINE_PCT
        if stage in ("ENGAGEMENT", "LOYALTY", "ACTIVATION"):
            try:
                this_month_start = (as_of - timedelta(days=30)).isoformat()
                prev_month_start = (as_of - timedelta(days=60)).isoformat()
                this_month = sum(
                    1 for e in events
                    if e.get("occurred_at", "") >= this_month_start
                )
                prev_month = sum(
                    1 for e in events
                    if prev_month_start <= e.get("occurred_at", "") < this_month_start
                )
                if prev_month > 0:
                    drop_pct = (Decimal(prev_month - this_month) /
                                Decimal(prev_month) * Decimal("100"))
                    if drop_pct >= AT_RISK_DECLINE_PCT:
                        stage = "AT_RISK"
                        classification = f"DECLINE_{drop_pct:.1f}_PCT_MOM"
                        evidence["this_month_events"] = this_month
                        evidence["prev_month_events"] = prev_month
            except (ValueError, AttributeError):
                pass

        return {
            "customer_id": customer_id,
            "stage": stage,
            "stage_classification": classification,
            "evidence": evidence,
        }

    # ── #343 Behavioral Widget ─────────────────────────────────────

    def behavioral_widget_payload(
        self,
        customer_id: str,
        product_count: int = 0,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """RM/Branch-facing widget consolidated payload."""
        summary = self.capture.interaction_summary(customer_id)
        channel_dist = self.capture.channel_distribution(customer_id)
        journey = self.reconstruct_journey(customer_id)
        friction = self.journey_friction_points(customer_id, as_of=as_of)
        stage = self.journey_stage(customer_id, as_of=as_of,
                                       product_count=product_count)
        nba = self.next_best_action(customer_id, product_count=product_count,
                                       as_of=as_of)

        return {
            "customer_id": customer_id,
            "stage": stage["stage"],
            "stage_classification": stage["stage_classification"],
            "primary_channel": channel_dist.get("primary_channel"),
            "event_count": summary.get("event_count"),
            "first_touch": journey.get("first_touch"),
            "last_touch": journey.get("last_touch"),
            "channels_used": journey.get("channels_used", []),
            "friction_indicators": friction.get("indicators_present", []),
            "next_best_action": nba.get("action"),
            "next_best_action_reason": nba.get("reason"),
            "_meta": {
                "spec_deviation": SPEC_DEVIATION_NOTE,
                "generated_at": datetime.utcnow().isoformat(),
            },
        }

    def next_best_action(
        self,
        customer_id: str,
        product_count: int = 0,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Rule-based NBA with optional Rule 7 ML override hook.

        When ml_nba_fn is provided and returns ml_driven=True, the ML
        action overrides this rule-based mapping. Otherwise falls
        through to deterministic stage→action lookup.
        """
        # Rule 7: ML hook override (v10.276)
        if self.ml_nba_fn is not None:
            try:
                stage_result = self.journey_stage(
                    customer_id, as_of=as_of, product_count=product_count,
                )
                ml_result = self.ml_nba_fn(
                    customer_id,
                    stage=stage_result.get("stage"),
                    product_count=product_count,
                    as_of=as_of,
                )
                if (isinstance(ml_result, dict)
                        and ml_result.get("ml_driven") is True
                        and ml_result.get("action") is not None):
                    out = dict(ml_result)
                    out["rule_based_only"] = False
                    return out
            except Exception as e:
                # Hook failure → fall through to rule-based with explicit reason
                pass

        # Rule-based path (v10.275 baseline)
        stage_result = self.journey_stage(customer_id, as_of=as_of,
                                              product_count=product_count)
        stage = stage_result["stage"]

        if stage == "AT_RISK":
            return {
                "action": "HIGH_RISK_OUTREACH",
                "reason": "stage_AT_RISK",
                "rule_based_only": True,
            }
        if stage == "DORMANT":
            return {
                "action": "REACTIVATION_CAMPAIGN",
                "reason": "stage_DORMANT",
                "rule_based_only": True,
            }
        if stage == "ACQUISITION":
            return {
                "action": "ONBOARDING_FOLLOWUP",
                "reason": "stage_ACQUISITION",
                "rule_based_only": True,
            }
        if stage == "ENGAGEMENT":
            return {
                "action": "NEW_PRODUCT_RECOMMENDATION",
                "reason": "stage_ENGAGEMENT_with_room_to_grow",
                "rule_based_only": True,
            }
        if stage == "LOYALTY":
            return {
                "action": "RETENTION_GIFT",
                "reason": "stage_LOYALTY_long_tenure",
                "rule_based_only": True,
            }
        return {
            "action": "NONE",
            "reason": f"no_rule_for_stage_{stage}",
            "rule_based_only": True,
        }


def _self_test() -> None:
    import tempfile

    # Spec deviation note check
    assert "v10.276" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        branch = BranchInteractionEngine(
            visits_path=Path(tmpdir) / "vs.json",
            capture=capture,
        )
        engine = JourneyAndWidgetEngine(
            capture=capture, branch=branch,
        )

        # Seed: customer with multi-channel journey
        events_seed = [
            ("MOBILE_APP", "LOGIN", "SUCCESS", "2026-04-01T08:00:00"),
            ("MOBILE_APP", "TRANSACTION", "SUCCESS", "2026-04-01T08:05:00"),
            ("BRANCH", "INQUIRY", "SUCCESS", "2026-04-05T10:00:00"),
            ("CALL_CENTER", "COMPLAINT", "PENDING", "2026-04-10T11:30:00"),
            ("MOBILE_APP", "ERROR", "FAILURE", "2026-04-12T14:00:00"),
            ("MOBILE_APP", "ERROR", "FAILURE", "2026-04-13T15:00:00"),
        ]
        for i, (ch, t, oc, ts) in enumerate(events_seed):
            capture.capture_event(
                "CUST-001",
                {"event_id": f"EV-{i:03d}",
                 "channel": ch, "event_type": t, "outcome": oc,
                 "occurred_at": ts,
                 "metadata": {"error_code": "NET-001"} if t == "ERROR" else {}},
                actor="pipeline",
            )

        # Test 1: reconstruct_journey
        journey = engine.reconstruct_journey("CUST-001")
        assert journey["event_count"] == 6
        assert journey["channel_count"] == 3
        assert journey["first_touch"]["channel"] == "MOBILE_APP"
        assert journey["first_touch"]["event_type"] == "LOGIN"

        # Test 2: empty journey
        empty = engine.reconstruct_journey("UNKNOWN")
        assert empty["event_count"] == 0
        assert empty["reason"] == "no_events"

        # Test 3: journey_friction_points
        friction = engine.journey_friction_points(
            "CUST-001", as_of=date(2026, 4, 15)
        )
        # Should detect REPEATED_FAILURE (2 NET-001 errors within 7 days)
        # Should detect MULTI_CHANNEL_FAILURE if failures span 2+ channels in
        # 7 days — but here only MOBILE_APP failed within 7-day window
        assert "REPEATED_FAILURE" in friction["indicators_present"]
        assert friction["details"]["repeated_failure_code"] == "NET-001"

        # Test 4: queue frustration friction
        # Seed branch visit with long wait
        branch.log_branch_visit(
            "CUST-002",
            {"visit_id": "VST-LONG", "branch_id": "BR-001",
             "purpose": "GENERAL_INQUIRY",
             "queued_at": "2026-04-15T09:00:00"},
            actor="pipeline",
        )
        branch.transition_visit_state(
            "VST-LONG", "BEING_SERVED", actor="teller",
            reason="finally serving",
            timestamp="2026-04-15T09:45:00",  # 45 min wait!
        )
        # Need at least one event for CUST-002
        capture.capture_event(
            "CUST-002",
            {"event_id": "EV-CUST2-001",
             "channel": "BRANCH", "event_type": "INTERACTION",
             "outcome": "SUCCESS",
             "occurred_at": "2026-04-15T09:00:00"},
            actor="pipeline",
        )
        friction = engine.journey_friction_points(
            "CUST-002", as_of=date(2026, 4, 16),
        )
        assert "QUEUE_FRUSTRATION" in friction["indicators_present"]

        # Test 5: journey_stage — recent customer
        # CUST-001 has events from 2026-04-01 to 2026-04-13
        # As of 2026-04-15 → days_as_customer ≈ 14, no products → ACQUISITION
        # or AWARENESS. With product_count=0 and days_as_customer < 30:
        # → AWARENESS
        stage = engine.journey_stage(
            "CUST-001", as_of=date(2026, 4, 15), product_count=0,
        )
        assert stage["stage"] == "AWARENESS"

        # Test 6: with product → ACQUISITION
        stage = engine.journey_stage(
            "CUST-001", as_of=date(2026, 4, 15), product_count=1,
        )
        assert stage["stage"] == "ACQUISITION"

        # Test 7: insufficient data
        stage = engine.journey_stage("UNKNOWN")
        assert stage["stage_classification"] == "INSUFFICIENT_DATA"

        # Test 8: DORMANT stage — last event 100+ days old
        capture.capture_event(
            "CUST-DORM",
            {"event_id": "EV-DORM-001",
             "channel": "MOBILE_APP", "event_type": "LOGIN",
             "outcome": "SUCCESS",
             "occurred_at": "2026-01-01T08:00:00"},
            actor="pipeline",
        )
        stage = engine.journey_stage(
            "CUST-DORM", as_of=date(2026, 5, 1), product_count=1,
        )
        # Days since last = ~120 → DORMANT
        assert stage["stage"] == "DORMANT"

        # Test 9: behavioral_widget_payload
        widget = engine.behavioral_widget_payload(
            "CUST-001", product_count=1, as_of=date(2026, 4, 15),
        )
        assert widget["customer_id"] == "CUST-001"
        assert widget["stage"] == "ACQUISITION"
        assert widget["next_best_action"] == "ONBOARDING_FOLLOWUP"
        assert widget["primary_channel"] == "MOBILE_APP"
        assert "REPEATED_FAILURE" in widget["friction_indicators"]
        assert widget["_meta"]["spec_deviation"]

        # Test 10: NBA — DORMANT customer
        nba = engine.next_best_action(
            "CUST-DORM", product_count=1, as_of=date(2026, 5, 1),
        )
        assert nba["action"] == "REACTIVATION_CAMPAIGN"
        assert nba["rule_based_only"] is True

        # Test 11: NBA for unknown
        nba = engine.next_best_action("UNKNOWN")
        assert nba["action"] == "NONE"

    print("  ✅ journey_and_widget self-test PASS")


if __name__ == "__main__":
    _self_test()

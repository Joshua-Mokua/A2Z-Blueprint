"""
================================================================================
A2Z MIS 360 — Standard #338: Mobile App Interaction Tracking
================================================================================

Risk classification: Cat C (in-app event tracking — funnel + cohort analysis)

In-app event tracking: screens, taps, sessions, abandonment, errors.
Funnel + cohort analysis on top of the interaction_capture event store.

Public API:
    record_screen_view(customer_id, screen_data, actor)
    record_tap(customer_id, tap_data, actor)
    record_session(customer_id, session_data, actor)
    funnel_analysis(funnel_steps, period_start, period_end) -> conversion
    cohort_retention(cohort_definition, period_start, weeks_ahead=8)
    abandonment_summary(period_start, period_end) -> screen-level drop-off
    error_summary(period_start, period_end) -> error frequency

APP_EVENT_TYPES byte-for-byte (Continuation.docx #338):
    SCREEN_VIEW       -- screen rendered
    TAP               -- user tap / click on element
    SESSION_START     -- app opened
    SESSION_END       -- app closed / backgrounded
    ABANDONMENT       -- explicit drop-off mid-flow
    ERROR             -- in-app error encountered

These integrate into interaction_capture.EVENT_TYPES via cross-mapping:
    SCREEN_VIEW       → INTERACTION
    TAP               → INTERACTION
    SESSION_START     → LOGIN
    SESSION_END       → LOGOUT
    ABANDONMENT       → INTERACTION (with outcome=ABANDONED)
    ERROR             → ERROR

DEFAULT_SESSION_TIMEOUT_MINUTES = 30  -- inactivity → SESSION_END

Honesty rules:
    Rule 1: funnel_analysis returns None conversion_pct for empty funnels
    Rule 6: invalid app_event_type rejected
    Rule 4: actor required (audit trail via interaction_capture)

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.interaction_capture import (
    InteractionCaptureEngine,
    INTERACTION_CHANNELS,
    EVENT_TYPES,
    EVENT_OUTCOMES,
)

getcontext().prec = 28


APP_EVENT_TYPES: Tuple[str, ...] = (
    "SCREEN_VIEW", "TAP", "SESSION_START", "SESSION_END",
    "ABANDONMENT", "ERROR",
)

# Cross-mapping byte-for-byte (G168 will lock)
APP_TO_INTERACTION_TYPE: Dict[str, str] = {
    "SCREEN_VIEW":   "INTERACTION",
    "TAP":           "INTERACTION",
    "SESSION_START": "LOGIN",
    "SESSION_END":   "LOGOUT",
    "ABANDONMENT":   "INTERACTION",
    "ERROR":         "ERROR",
}

DEFAULT_SESSION_TIMEOUT_MINUTES: int = 30


class MobileAppTrackingEngine:
    """In-app event tracking — funnel + cohort analytics."""

    def __init__(
        self,
        capture: Optional[InteractionCaptureEngine] = None,
    ):
        # Composes interaction_capture as the persistence + read surface.
        self.capture = capture or InteractionCaptureEngine()

    def _record_app_event(
        self,
        customer_id: str,
        app_event_type: str,
        screen_or_action: str,
        occurred_at: str,
        actor: str,
        outcome: str = "SUCCESS",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Internal helper — translate app event to interaction event."""
        if app_event_type not in APP_EVENT_TYPES:
            return {
                "captured": False,
                "error": f"invalid_app_event_type:{app_event_type}",
                "valid_types": list(APP_EVENT_TYPES),
            }

        # Generate unique event_id
        ts = occurred_at.replace(":", "").replace("-", "").replace("T", "")
        event_id = f"APP-{customer_id}-{app_event_type}-{ts}-{screen_or_action[:20]}"

        merged_meta = dict(metadata or {})
        merged_meta["app_event_type"] = app_event_type
        merged_meta["screen_or_action"] = screen_or_action

        return self.capture.capture_event(
            customer_id,
            {
                "event_id": event_id,
                "channel": "MOBILE_APP",
                "event_type": APP_TO_INTERACTION_TYPE[app_event_type],
                "outcome": outcome,
                "occurred_at": occurred_at,
                "session_id": session_id,
                "device_id": device_id,
                "metadata": merged_meta,
            },
            actor=actor,
        )

    def record_screen_view(
        self,
        customer_id: str,
        screen_name: str,
        occurred_at: str,
        actor: str,
        session_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record_app_event(
            customer_id, "SCREEN_VIEW", screen_name, occurred_at,
            actor, outcome="SUCCESS",
            metadata={"screen": screen_name},
            session_id=session_id, device_id=device_id,
        )

    def record_tap(
        self,
        customer_id: str,
        element_id: str,
        screen_name: str,
        occurred_at: str,
        actor: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record_app_event(
            customer_id, "TAP", element_id, occurred_at,
            actor, outcome="SUCCESS",
            metadata={"screen": screen_name, "element_id": element_id},
            session_id=session_id,
        )

    def record_session(
        self,
        customer_id: str,
        session_id: str,
        start_at: str,
        end_at: Optional[str],
        actor: str,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record SESSION_START + SESSION_END."""
        out = {"start": None, "end": None}
        out["start"] = self._record_app_event(
            customer_id, "SESSION_START", session_id, start_at,
            actor, outcome="SUCCESS",
            metadata={"session_id": session_id},
            session_id=session_id, device_id=device_id,
        )
        if end_at:
            out["end"] = self._record_app_event(
                customer_id, "SESSION_END", session_id, end_at,
                actor, outcome="SUCCESS",
                metadata={"session_id": session_id},
                session_id=session_id, device_id=device_id,
            )
        return out

    def record_abandonment(
        self,
        customer_id: str,
        flow_name: str,
        last_screen: str,
        occurred_at: str,
        actor: str,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record_app_event(
            customer_id, "ABANDONMENT", flow_name, occurred_at,
            actor, outcome="ABANDONED",
            metadata={"flow": flow_name, "last_screen": last_screen},
            session_id=session_id,
        )

    def record_error(
        self,
        customer_id: str,
        error_code: str,
        screen_name: str,
        occurred_at: str,
        actor: str,
        error_message: str = "",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._record_app_event(
            customer_id, "ERROR", error_code, occurred_at,
            actor, outcome="FAILURE",
            metadata={"screen": screen_name, "error_code": error_code,
                       "error_message": error_message},
            session_id=session_id,
        )

    # ── Analytics ──────────────────────────────────────────────────

    def funnel_analysis(
        self,
        funnel_steps: List[str],
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """
        Compute funnel conversion across ordered screens.

        Each step is a screen_name; a customer counts at step N if they
        had a SCREEN_VIEW for step N at any point in period AND already
        appeared at step N-1.
        """
        if not funnel_steps:
            return {
                "steps": [],
                "step_results": [],
                "overall_conversion_pct": None,
                "reason": "empty_funnel",
            }

        # Pull all MOBILE_APP screen views in period
        all_records = self.capture._load()
        in_period = [
            r for r in all_records
            if r.get("channel") == "MOBILE_APP"
            and r.get("event_type") == "INTERACTION"
            and r.get("metadata", {}).get("app_event_type") == "SCREEN_VIEW"
            and period_start <= r.get("occurred_at", "") <= period_end
        ]

        # Group by customer → set of screens viewed (with first occurrence)
        cust_screens: Dict[str, Dict[str, str]] = defaultdict(dict)
        for r in in_period:
            cid = r.get("customer_id")
            screen = r.get("metadata", {}).get("screen", "")
            if not cid or not screen:
                continue
            if screen not in cust_screens[cid]:
                cust_screens[cid][screen] = r["occurred_at"]

        # Compute step-by-step conversion (must complete in order)
        step_results = []
        eligible_customers: Optional[set] = None
        for i, step in enumerate(funnel_steps):
            if i == 0:
                # All customers who viewed step 0
                step_customers = {
                    cid for cid, scrs in cust_screens.items()
                    if step in scrs
                }
                eligible_customers = step_customers
            else:
                # Must have viewed step AFTER step-1
                step_customers = set()
                prev_step = funnel_steps[i - 1]
                for cid in (eligible_customers or set()):
                    scrs = cust_screens.get(cid, {})
                    if step in scrs and scrs[step] >= scrs.get(prev_step, ""):
                        step_customers.add(cid)
                eligible_customers = step_customers

            step_count = len(step_customers)
            from_count = (step_results[0]["count"] if step_results else step_count)
            conv_pct = (
                (Decimal(step_count) / Decimal(from_count) * Decimal("100"))
                .quantize(Decimal("0.01"))
                if from_count > 0 else None
            )
            step_results.append({
                "step": step,
                "count": step_count,
                "conversion_from_step_0_pct": str(conv_pct) if conv_pct is not None else None,
            })

        # Overall conversion: last / first
        if step_results and step_results[0]["count"] > 0:
            overall = (Decimal(step_results[-1]["count"]) /
                          Decimal(step_results[0]["count"]) *
                          Decimal("100")).quantize(Decimal("0.01"))
        else:
            overall = None

        return {
            "steps": funnel_steps,
            "period_start": period_start,
            "period_end": period_end,
            "step_results": step_results,
            "overall_conversion_pct": str(overall) if overall is not None else None,
        }

    def cohort_retention(
        self,
        cohort_event_type: str,
        cohort_period_start: str,
        cohort_period_end: str,
        weeks_ahead: int = 8,
    ) -> Dict[str, Any]:
        """
        Compute weekly retention for customers whose first cohort_event_type
        landed in the cohort window.

        Returns retention_pct for week 0, week 1, ..., week N-1.
        """
        if weeks_ahead <= 0:
            return {"weeks": [], "reason": "weeks_ahead_must_be_positive"}

        all_records = self.capture._load()
        # Find cohort: customers whose FIRST event of the type fell in window
        first_event: Dict[str, str] = {}
        for r in all_records:
            if r.get("channel") != "MOBILE_APP":
                continue
            app_t = r.get("metadata", {}).get("app_event_type")
            if app_t != cohort_event_type:
                continue
            cid = r.get("customer_id")
            ts = r.get("occurred_at", "")
            if not cid or not ts:
                continue
            if cid not in first_event or ts < first_event[cid]:
                first_event[cid] = ts

        cohort = {
            cid: ts for cid, ts in first_event.items()
            if cohort_period_start <= ts <= cohort_period_end
        }
        cohort_size = len(cohort)
        if cohort_size == 0:
            return {
                "cohort_size": 0,
                "weeks": [],
                "reason": "empty_cohort",
            }

        # For each customer in cohort, compute week buckets relative to their
        # first event
        cust_active_weeks: Dict[str, set] = defaultdict(set)
        for r in all_records:
            if r.get("channel") != "MOBILE_APP":
                continue
            cid = r.get("customer_id")
            if cid not in cohort:
                continue
            try:
                t = datetime.fromisoformat(r["occurred_at"].replace("Z", ""))
                start = datetime.fromisoformat(
                    cohort[cid].replace("Z", "")
                )
            except (ValueError, KeyError, AttributeError):
                continue
            week_idx = (t - start).days // 7
            if 0 <= week_idx < weeks_ahead:
                cust_active_weeks[cid].add(week_idx)

        # Aggregate
        week_counts = [0] * weeks_ahead
        for cid, weeks in cust_active_weeks.items():
            for w in weeks:
                week_counts[w] += 1

        weeks_out = []
        for w in range(weeks_ahead):
            pct = (Decimal(week_counts[w]) / Decimal(cohort_size) *
                     Decimal("100")).quantize(Decimal("0.01"))
            weeks_out.append({
                "week_index": w,
                "active_count": week_counts[w],
                "retention_pct": str(pct),
            })

        return {
            "cohort_event_type": cohort_event_type,
            "cohort_period_start": cohort_period_start,
            "cohort_period_end": cohort_period_end,
            "cohort_size": cohort_size,
            "weeks": weeks_out,
        }

    def abandonment_summary(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Top screens / flows where users abandoned."""
        all_records = self.capture._load()
        abandonments = [
            r for r in all_records
            if r.get("channel") == "MOBILE_APP"
            and r.get("metadata", {}).get("app_event_type") == "ABANDONMENT"
            and period_start <= r.get("occurred_at", "") <= period_end
        ]

        by_flow = Counter(
            r.get("metadata", {}).get("flow", "UNKNOWN") for r in abandonments
        )
        by_screen = Counter(
            r.get("metadata", {}).get("last_screen", "UNKNOWN")
            for r in abandonments
        )

        return {
            "period_start": period_start,
            "period_end": period_end,
            "total_abandonments": len(abandonments),
            "by_flow": dict(by_flow.most_common(20)),
            "by_last_screen": dict(by_screen.most_common(20)),
        }

    def error_summary(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Error frequency by code/screen."""
        all_records = self.capture._load()
        errors = [
            r for r in all_records
            if r.get("channel") == "MOBILE_APP"
            and r.get("metadata", {}).get("app_event_type") == "ERROR"
            and period_start <= r.get("occurred_at", "") <= period_end
        ]

        by_code = Counter(
            r.get("metadata", {}).get("error_code", "UNKNOWN") for r in errors
        )
        by_screen = Counter(
            r.get("metadata", {}).get("screen", "UNKNOWN") for r in errors
        )

        return {
            "period_start": period_start,
            "period_end": period_end,
            "total_errors": len(errors),
            "by_error_code": dict(by_code.most_common(20)),
            "by_screen": dict(by_screen.most_common(20)),
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = MobileAppTrackingEngine(capture=capture)

        # Test 1: record screen view
        r = engine.record_screen_view(
            "CUST-001", "HOME",
            "2026-04-15T08:00:00", actor="app_pipeline",
            session_id="SES-001", device_id="DEV-1",
        )
        assert r["captured"], r

        # Test 2: invalid app event type rejected at internal level
        r = engine._record_app_event(
            "CUST-001", "INVALID_TYPE", "x",
            "2026-04-15T08:00:00", actor="x",
        )
        assert not r["captured"]
        assert "invalid_app_event_type" in r["error"]

        # Test 3: full funnel — HOME → ACCOUNTS → TRANSFER → CONFIRM
        funnel = ["HOME", "ACCOUNTS", "TRANSFER", "CONFIRM"]

        # Customer A: completes full funnel
        engine.record_screen_view("CUST-A", "ACCOUNTS",
                                       "2026-04-15T08:01:00", actor="app")
        engine.record_screen_view("CUST-A", "HOME",
                                       "2026-04-15T08:00:00", actor="app")
        engine.record_screen_view("CUST-A", "TRANSFER",
                                       "2026-04-15T08:02:00", actor="app")
        engine.record_screen_view("CUST-A", "CONFIRM",
                                       "2026-04-15T08:03:00", actor="app")

        # Customer B: stops at TRANSFER
        engine.record_screen_view("CUST-B", "HOME",
                                       "2026-04-15T09:00:00", actor="app")
        engine.record_screen_view("CUST-B", "ACCOUNTS",
                                       "2026-04-15T09:01:00", actor="app")
        engine.record_screen_view("CUST-B", "TRANSFER",
                                       "2026-04-15T09:02:00", actor="app")

        # Customer C: only HOME
        engine.record_screen_view("CUST-C", "HOME",
                                       "2026-04-15T10:00:00", actor="app")

        result = engine.funnel_analysis(
            funnel, "2026-04-15", "2026-04-16",
        )
        # Step 0 (HOME): 4 — CUST-001 from test 1 + CUST-A + CUST-B + CUST-C
        assert result["step_results"][0]["count"] == 4
        # Step 1 (ACCOUNTS): 2
        assert result["step_results"][1]["count"] == 2
        # Step 2 (TRANSFER): 2
        assert result["step_results"][2]["count"] == 2
        # Step 3 (CONFIRM): 1
        assert result["step_results"][3]["count"] == 1
        # Overall conversion: 1/4 = 25.00
        assert result["overall_conversion_pct"] == "25.00"

        # Test 4: empty funnel surfaces reason
        empty = engine.funnel_analysis([], "2026-04-15", "2026-04-16")
        assert empty["overall_conversion_pct"] is None
        assert empty["reason"] == "empty_funnel"

        # Test 5: abandonment recording
        engine.record_abandonment(
            "CUST-B", "TRANSFER_FLOW", "TRANSFER",
            "2026-04-15T09:03:00", actor="app",
        )
        ab = engine.abandonment_summary("2026-04-15", "2026-04-16")
        assert ab["total_abandonments"] == 1
        assert "TRANSFER_FLOW" in ab["by_flow"]

        # Test 6: error recording
        engine.record_error(
            "CUST-A", "NET-001", "TRANSFER",
            "2026-04-15T08:02:30", actor="app",
            error_message="network timeout",
        )
        errs = engine.error_summary("2026-04-15", "2026-04-16")
        assert errs["total_errors"] == 1
        assert "NET-001" in errs["by_error_code"]

        # Test 7: session recording (start + end)
        out = engine.record_session(
            "CUST-D", "SES-D-1",
            "2026-04-15T11:00:00", "2026-04-15T11:15:00",
            actor="app", device_id="DEV-D",
        )
        assert out["start"]["captured"]
        assert out["end"]["captured"]

        # Test 8: cohort retention
        # Cohort: SCREEN_VIEW first occurrence in 2026-04-15
        cohort = engine.cohort_retention(
            "SCREEN_VIEW",
            "2026-04-15", "2026-04-15T23:59:59",
            weeks_ahead=2,
        )
        # Should include CUST-001 + A + B + C (CUST-D had SESSION_START not SCREEN_VIEW)
        assert cohort["cohort_size"] == 4
        # Week 0: all 4 active
        assert cohort["weeks"][0]["active_count"] == 4
        assert cohort["weeks"][0]["retention_pct"] == "100.00"

        # Test 9: empty cohort
        empty_cohort = engine.cohort_retention(
            "SCREEN_VIEW", "2027-01-01", "2027-01-31", weeks_ahead=4,
        )
        assert empty_cohort["cohort_size"] == 0
        assert empty_cohort["reason"] == "empty_cohort"

        # Test 10: invalid weeks_ahead
        bad = engine.cohort_retention(
            "SCREEN_VIEW", "2026-04-15", "2026-04-15", weeks_ahead=0,
        )
        assert "must_be_positive" in bad["reason"]

    print("  ✅ mobile_app_tracking self-test PASS")


if __name__ == "__main__":
    _self_test()

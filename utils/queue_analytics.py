"""
================================================================================
A2Z MIS 360 — Standard #68: Queue Analytics & Customer Experience Engine
================================================================================

Risk classification: Cat B (deterministic queueing statistics + CX metrics)

Queueing analytics + customer experience indicators:
    - wait_time_distribution(queue, period)         -- p50/p90 + bucket histogram
    - service_time_distribution(queue, period)      -- p50/p90 service duration
    - abandonment_rate(period)                      -- joiners that left without service
    - csat_aggregate(period)                        -- weighted CSAT score
    - first_call_resolution(interactions)           -- % of issues resolved on 1st contact
    - peak_hour_load(period)                        -- hour-of-day arrival rate

CSAT scoring (industry standard 1-5 scale):
    1=very_dissatisfied, 2=dissatisfied, 3=neutral, 4=satisfied, 5=very_satisfied
    CSAT_PCT = (count_4_or_5 / total_responses) × 100

Honesty rules applied:
    Rule 1: rates = None when denominator <= 0 (no joiners → no abandonment rate)
    Rule 6: missing arrival/service timestamps surfaced in observations_excluded[]

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# CSAT scale (1-5)
CSAT_MIN_SCORE = 1
CSAT_MAX_SCORE = 5
CSAT_SATISFIED_MIN = 4   # 4 or 5 = satisfied (top-2-box)

# Wait time histogram buckets (minutes)
WAIT_TIME_BUCKETS_MIN: Tuple[Tuple[str, int, int], ...] = (
    ("UNDER_2", 0, 2),
    ("2_5", 2, 5),
    ("5_10", 5, 10),
    ("10_15", 10, 15),
    ("15_30", 15, 30),
    ("OVER_30", 30, 999),
)

# CSAT severity thresholds
CSAT_HEALTHY_PCT = 80.0
CSAT_AMBER_PCT = 65.0
# < 65 = RED

# Abandonment rate thresholds
ABANDONMENT_HEALTHY_PCT = 5.0
ABANDONMENT_AMBER_PCT = 10.0
# > 10% = RED

# First call resolution thresholds
FCR_HEALTHY_PCT = 75.0
FCR_AMBER_PCT = 60.0


@dataclass
class QueueEvent:
    event_id: str
    queue_id: str
    customer_id: str
    arrival_at: datetime
    service_start_at: Optional[datetime] = None
    service_end_at: Optional[datetime] = None
    abandoned_at: Optional[datetime] = None  # left without service


@dataclass
class CsatResponse:
    response_id: str
    interaction_id: str
    customer_id: str
    score: int  # 1-5
    submitted_at: datetime
    channel: Optional[str] = None


@dataclass
class CustomerInteraction:
    interaction_id: str
    customer_id: str
    issue_category: str
    contact_count: int  # how many touches to resolve (1 = FCR)
    resolved: bool
    started_at: datetime


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n == 1:
        return float(s[0])
    rank = (pct / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(s[lo]) + (float(s[hi]) - float(s[lo])) * frac


def _wait_minutes(e: QueueEvent) -> Optional[float]:
    """Wait time = service_start - arrival, or abandonment - arrival."""
    if e.service_start_at is not None:
        delta = (e.service_start_at - e.arrival_at).total_seconds() / 60
        return max(0.0, delta)
    if e.abandoned_at is not None:
        delta = (e.abandoned_at - e.arrival_at).total_seconds() / 60
        return max(0.0, delta)
    return None


def _service_minutes(e: QueueEvent) -> Optional[float]:
    if e.service_start_at is None or e.service_end_at is None:
        return None
    delta = (e.service_end_at - e.service_start_at).total_seconds() / 60
    return max(0.0, delta)


class QueueAnalyticsEngine:
    """Deterministic queueing + CX analytics."""

    @staticmethod
    def wait_time_distribution(events: List[QueueEvent], queue_id: Optional[str] = None) -> Dict[str, Any]:
        """Wait time p50/p90 + bucket histogram."""
        rel = [e for e in events if (queue_id is None or e.queue_id == queue_id)]
        valid = []
        excluded = []
        for e in rel:
            w = _wait_minutes(e)
            if w is None:
                excluded.append(e.event_id)
            else:
                valid.append(w)

        if not valid:
            return {
                "queue_id": queue_id,
                "observations_count": 0,
                "observations_excluded": len(excluded),
                "p50_min": None,
                "p90_min": None,
                "buckets": {},
                "reason": "no_valid_observations",
            }

        # Bucket histogram
        buckets: Dict[str, int] = {b[0]: 0 for b in WAIT_TIME_BUCKETS_MIN}
        for w in valid:
            for label, lo, hi in WAIT_TIME_BUCKETS_MIN:
                if lo <= w < hi:
                    buckets[label] += 1
                    break
            else:
                # Last bucket inclusive
                buckets[WAIT_TIME_BUCKETS_MIN[-1][0]] += 1

        return {
            "queue_id": queue_id,
            "observations_count": len(valid),
            "observations_excluded": len(excluded),
            "p50_min": round(_percentile(valid, 50), 2),
            "p90_min": round(_percentile(valid, 90), 2),
            "max_min": round(max(valid), 2),
            "buckets": buckets,
        }

    @staticmethod
    def service_time_distribution(events: List[QueueEvent], queue_id: Optional[str] = None) -> Dict[str, Any]:
        rel = [e for e in events if (queue_id is None or e.queue_id == queue_id)]
        valid = []
        excluded = []
        for e in rel:
            s = _service_minutes(e)
            if s is None:
                excluded.append(e.event_id)
            else:
                valid.append(s)
        if not valid:
            return {
                "queue_id": queue_id,
                "observations_count": 0,
                "observations_excluded": len(excluded),
                "p50_min": None,
                "p90_min": None,
                "reason": "no_completed_services",
            }
        return {
            "queue_id": queue_id,
            "observations_count": len(valid),
            "observations_excluded": len(excluded),
            "p50_min": round(_percentile(valid, 50), 2),
            "p90_min": round(_percentile(valid, 90), 2),
            "max_min": round(max(valid), 2),
        }

    @staticmethod
    def abandonment_rate(events: List[QueueEvent]) -> Dict[str, Any]:
        """
        Abandonment % = abandoned / (abandoned + served) × 100.
        Rule 1: returns None when no joiners.
        """
        served = sum(1 for e in events if e.service_start_at is not None)
        abandoned = sum(1 for e in events if e.abandoned_at is not None and e.service_start_at is None)
        total = served + abandoned

        if total == 0:
            return {
                "total_joiners": 0,
                "served_count": 0,
                "abandoned_count": 0,
                "abandonment_pct": None,
                "severity": None,
                "reason": "no_joiners",
            }

        rate = (abandoned / total) * 100
        if rate <= ABANDONMENT_HEALTHY_PCT:
            severity = "GREEN"
        elif rate <= ABANDONMENT_AMBER_PCT:
            severity = "AMBER"
        else:
            severity = "RED"

        return {
            "total_joiners": total,
            "served_count": served,
            "abandoned_count": abandoned,
            "abandonment_pct": round(rate, 2),
            "severity": severity,
        }

    @staticmethod
    def csat_aggregate(responses: List[CsatResponse]) -> Dict[str, Any]:
        """
        CSAT % top-2-box (4 or 5 of 5). Rule 1: None on no responses.
        Rule 6: scores outside 1-5 excluded and counted.
        """
        valid = [r for r in responses if CSAT_MIN_SCORE <= r.score <= CSAT_MAX_SCORE]
        excluded = len(responses) - len(valid)

        if not valid:
            return {
                "total_responses": 0,
                "excluded_count": excluded,
                "csat_pct": None,
                "average_score": None,
                "severity": None,
                "reason": "no_valid_responses",
            }

        satisfied = sum(1 for r in valid if r.score >= CSAT_SATISFIED_MIN)
        avg = sum(r.score for r in valid) / len(valid)
        pct = (satisfied / len(valid)) * 100

        if pct >= CSAT_HEALTHY_PCT:
            severity = "GREEN"
        elif pct >= CSAT_AMBER_PCT:
            severity = "AMBER"
        else:
            severity = "RED"

        return {
            "total_responses": len(valid),
            "excluded_count": excluded,
            "satisfied_count": satisfied,
            "csat_pct": round(pct, 2),
            "average_score": round(avg, 2),
            "severity": severity,
        }

    @staticmethod
    def first_call_resolution(interactions: List[CustomerInteraction]) -> Dict[str, Any]:
        """
        FCR % = single-contact resolutions / total resolved interactions × 100.
        Rule 1: None on no resolved interactions.
        """
        resolved = [i for i in interactions if i.resolved]
        if not resolved:
            return {
                "total_interactions": len(interactions),
                "resolved_count": 0,
                "fcr_count": 0,
                "fcr_pct": None,
                "severity": None,
                "reason": "no_resolved_interactions",
            }
        fcr = sum(1 for i in resolved if i.contact_count == 1)
        pct = (fcr / len(resolved)) * 100
        if pct >= FCR_HEALTHY_PCT:
            severity = "GREEN"
        elif pct >= FCR_AMBER_PCT:
            severity = "AMBER"
        else:
            severity = "RED"
        return {
            "total_interactions": len(interactions),
            "resolved_count": len(resolved),
            "fcr_count": fcr,
            "fcr_pct": round(pct, 2),
            "severity": severity,
        }

    @staticmethod
    def peak_hour_load(events: List[QueueEvent]) -> Dict[str, Any]:
        """Hour-of-day arrival count distribution."""
        hours: Dict[int, int] = {h: 0 for h in range(24)}
        for e in events:
            h = e.arrival_at.hour
            hours[h] = hours.get(h, 0) + 1
        if not events:
            return {"total_arrivals": 0, "peak_hour": None, "peak_count": 0, "by_hour": hours}
        peak = max(hours.items(), key=lambda x: x[1])
        return {
            "total_arrivals": len(events),
            "peak_hour": peak[0],
            "peak_count": peak[1],
            "by_hour": hours,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _qe(**kw):
    defaults = dict(
        event_id="E1", queue_id="Q1", customer_id="C1",
        arrival_at=_dt("2026-01-01T10:00:00+00:00"),
        service_start_at=_dt("2026-01-01T10:05:00+00:00"),
        service_end_at=_dt("2026-01-01T10:08:00+00:00"),
    )
    defaults.update(kw)
    return QueueEvent(**defaults)


def _test_wait_distribution_basic():
    events = [
        _qe(event_id="E1", arrival_at=_dt("2026-01-01T10:00:00+00:00"),
            service_start_at=_dt("2026-01-01T10:01:00+00:00")),  # 1 min
        _qe(event_id="E2", arrival_at=_dt("2026-01-01T10:00:00+00:00"),
            service_start_at=_dt("2026-01-01T10:07:00+00:00")),  # 7 min
        _qe(event_id="E3", arrival_at=_dt("2026-01-01T10:00:00+00:00"),
            service_start_at=_dt("2026-01-01T10:12:00+00:00")),  # 12 min
    ]
    r = QueueAnalyticsEngine.wait_time_distribution(events)
    assert r["observations_count"] == 3
    assert r["buckets"]["UNDER_2"] == 1
    assert r["buckets"]["5_10"] == 1
    assert r["buckets"]["10_15"] == 1


def _test_wait_distribution_excluded_rule6():
    e = _qe(service_start_at=None, abandoned_at=None)
    r = QueueAnalyticsEngine.wait_time_distribution([e])
    assert r["observations_count"] == 0
    assert r["observations_excluded"] == 1


def _test_wait_distribution_empty_rule1():
    r = QueueAnalyticsEngine.wait_time_distribution([])
    assert r["p50_min"] is None


def _test_service_time_basic():
    events = [_qe()]
    r = QueueAnalyticsEngine.service_time_distribution(events)
    assert r["p50_min"] == 3.0  # 3 min service


def _test_abandonment_rate_basic():
    events = [
        _qe(event_id="E1"),  # served
        _qe(event_id="E2"),  # served
        QueueEvent(event_id="E3", queue_id="Q1", customer_id="C3",
                  arrival_at=_dt("2026-01-01T10:00:00+00:00"),
                  service_start_at=None,
                  abandoned_at=_dt("2026-01-01T10:08:00+00:00")),
    ]
    r = QueueAnalyticsEngine.abandonment_rate(events)
    assert r["total_joiners"] == 3
    assert r["abandoned_count"] == 1
    assert round(r["abandonment_pct"], 1) == 33.3
    assert r["severity"] == "RED"


def _test_abandonment_no_joiners_rule1():
    r = QueueAnalyticsEngine.abandonment_rate([])
    assert r["abandonment_pct"] is None


def _test_abandonment_green():
    events = [_qe(event_id=f"E{i}") for i in range(20)]  # 20 served, 0 abandoned
    r = QueueAnalyticsEngine.abandonment_rate(events)
    assert r["abandonment_pct"] == 0.0
    assert r["severity"] == "GREEN"


def _test_csat_basic():
    responses = [
        CsatResponse(response_id=f"R{i}", interaction_id=f"I{i}", customer_id=f"C{i}",
                    score=5, submitted_at=_dt("2026-01-01T10:00:00+00:00"))
        for i in range(8)
    ]
    responses += [
        CsatResponse(response_id="R9", interaction_id="I9", customer_id="C9",
                    score=2, submitted_at=_dt("2026-01-01T10:00:00+00:00")),
        CsatResponse(response_id="R10", interaction_id="I10", customer_id="C10",
                    score=3, submitted_at=_dt("2026-01-01T10:00:00+00:00")),
    ]
    r = QueueAnalyticsEngine.csat_aggregate(responses)
    assert r["satisfied_count"] == 8
    assert r["csat_pct"] == 80.0
    assert r["severity"] == "GREEN"


def _test_csat_invalid_score_excluded_rule6():
    responses = [
        CsatResponse(response_id="R1", interaction_id="I1", customer_id="C1",
                    score=99, submitted_at=_dt("2026-01-01T10:00:00+00:00")),
        CsatResponse(response_id="R2", interaction_id="I2", customer_id="C2",
                    score=5, submitted_at=_dt("2026-01-01T10:00:00+00:00")),
    ]
    r = QueueAnalyticsEngine.csat_aggregate(responses)
    assert r["excluded_count"] == 1
    assert r["total_responses"] == 1


def _test_csat_no_responses_rule1():
    r = QueueAnalyticsEngine.csat_aggregate([])
    assert r["csat_pct"] is None


def _test_fcr_basic():
    interactions = [
        CustomerInteraction(interaction_id=f"I{i}", customer_id=f"C{i}",
                           issue_category="ACCOUNT", contact_count=1, resolved=True,
                           started_at=_dt("2026-01-01T10:00:00+00:00"))
        for i in range(8)
    ]
    interactions += [
        CustomerInteraction(interaction_id="I9", customer_id="C9",
                           issue_category="ACCOUNT", contact_count=3, resolved=True,
                           started_at=_dt("2026-01-01T10:00:00+00:00")),
        CustomerInteraction(interaction_id="I10", customer_id="C10",
                           issue_category="ACCOUNT", contact_count=2, resolved=True,
                           started_at=_dt("2026-01-01T10:00:00+00:00")),
    ]
    r = QueueAnalyticsEngine.first_call_resolution(interactions)
    assert r["fcr_count"] == 8
    assert r["fcr_pct"] == 80.0
    assert r["severity"] == "GREEN"


def _test_fcr_no_resolved_rule1():
    interactions = [
        CustomerInteraction(interaction_id="I1", customer_id="C1",
                           issue_category="ACCOUNT", contact_count=2, resolved=False,
                           started_at=_dt("2026-01-01T10:00:00+00:00"))
    ]
    r = QueueAnalyticsEngine.first_call_resolution(interactions)
    assert r["fcr_pct"] is None


def _test_peak_hour():
    events = [
        _qe(event_id=f"E{i}", arrival_at=_dt(f"2026-01-01T10:{i:02d}:00+00:00"))
        for i in range(10)
    ]
    events += [_qe(event_id="E20", arrival_at=_dt("2026-01-01T11:00:00+00:00"))]
    r = QueueAnalyticsEngine.peak_hour_load(events)
    assert r["peak_hour"] == 10
    assert r["peak_count"] == 10


def _test_csat_thresholds_byte_for_byte():
    assert CSAT_HEALTHY_PCT == 80.0
    assert CSAT_AMBER_PCT == 65.0
    assert CSAT_SATISFIED_MIN == 4


def _test_abandonment_thresholds_byte_for_byte():
    assert ABANDONMENT_HEALTHY_PCT == 5.0
    assert ABANDONMENT_AMBER_PCT == 10.0


def self_test() -> bool:
    tests = [
        _test_wait_distribution_basic,
        _test_wait_distribution_excluded_rule6,
        _test_wait_distribution_empty_rule1,
        _test_service_time_basic,
        _test_abandonment_rate_basic,
        _test_abandonment_no_joiners_rule1,
        _test_abandonment_green,
        _test_csat_basic,
        _test_csat_invalid_score_excluded_rule6,
        _test_csat_no_responses_rule1,
        _test_fcr_basic,
        _test_fcr_no_resolved_rule1,
        _test_peak_hour,
        _test_csat_thresholds_byte_for_byte,
        _test_abandonment_thresholds_byte_for_byte,
    ]
    print("=" * 60)
    print("Queue Analytics & CX Engine — Self-Tests (#68)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

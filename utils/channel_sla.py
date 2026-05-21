"""
================================================================================
A2Z MIS 360 — Standard #67: Channel SLA Monitoring Engine
================================================================================

Risk classification: Cat B (deterministic uptime + percentile latency aggregation)

Computes per-channel SLA metrics for digital + assisted channels:
    - uptime_pct(channel, period)           -- (uptime_ms / total_ms) × 100
    - response_time_distribution(channel)   -- p50/p90/p99 latency
    - channel_sla_summary(period)           -- all channels traffic-light status
    - incident_mtbf_mttr(channel)           -- mean time between failures + repair

CBK PG/15 + standard banking SLA expectations:
    Mobile / Internet / API : 99.9% uptime; p99 < 2000ms
    ATM                     : 99.5% uptime
    USSD / Agent            : 99.5% uptime
    Branch                  : 99% uptime (during business hours)

Honesty rules applied:
    Rule 1: uptime_pct = None when total_ms <= 0 (cannot compute ratio)
    Rule 6: missing observation timestamps surfaced; downtime windows with
            unknown end-time conservatively counted as ongoing (NEVER assumed closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# Spec literals
CHANNELS: Tuple[str, ...] = (
    "BRANCH", "ATM", "MOBILE", "INTERNET", "USSD", "AGENT", "POS", "API",
)

# SLA targets per channel (uptime % per CBK + industry standard)
CHANNEL_UPTIME_TARGET_PCT: Dict[str, Decimal] = {
    "MOBILE": Decimal("99.9"),
    "INTERNET": Decimal("99.9"),
    "API": Decimal("99.9"),
    "ATM": Decimal("99.5"),
    "USSD": Decimal("99.5"),
    "AGENT": Decimal("99.5"),
    "POS": Decimal("99.5"),
    "BRANCH": Decimal("99.0"),
}

# Latency targets (milliseconds, p99)
CHANNEL_LATENCY_TARGET_P99_MS: Dict[str, int] = {
    "MOBILE": 2000,
    "INTERNET": 2000,
    "API": 2000,
    "ATM": 5000,
    "USSD": 8000,
    "POS": 3000,
    "AGENT": 5000,
    "BRANCH": 30000,  # transaction processing
}

# Status thresholds (gap from target, percentage points)
UPTIME_GREEN_GAP_MAX_PP = Decimal("0.0")     # at or above target
UPTIME_AMBER_GAP_MAX_PP = Decimal("0.5")     # within 0.5pp below target
# Below that = RED


@dataclass
class ChannelOutage:
    outage_id: str
    channel: str
    started_at: datetime
    ended_at: Optional[datetime] = None  # None = ongoing
    severity: str = "PARTIAL"  # FULL or PARTIAL


@dataclass
class LatencyObservation:
    obs_id: str
    channel: str
    response_time_ms: int
    observed_at: datetime


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Deterministic linear-interpolation percentile."""
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


class ChannelSlaMonitoringEngine:
    """Deterministic uptime + latency + MTBF/MTTR computation."""

    @staticmethod
    def uptime_pct(
        outages: List[ChannelOutage],
        channel: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Dict[str, Any]:
        """
        Compute uptime % for a channel over a period.
        Rule 1: returns None when period_end <= period_start.
        Rule 6: outages with no ended_at conservatively run to period_end.
        """
        if channel not in CHANNELS:
            return {"channel": channel, "error": f"unknown_channel:{channel}", "valid": list(CHANNELS)}

        if period_end <= period_start:
            return {
                "channel": channel,
                "uptime_pct": None,
                "reason": "invalid_period",
            }

        total_seconds = (period_end - period_start).total_seconds()
        if total_seconds <= 0:
            return {
                "channel": channel,
                "uptime_pct": None,
                "reason": "period_zero_seconds",
            }

        channel_outages = [o for o in outages if o.channel == channel]
        downtime_seconds = 0.0
        ongoing_count = 0
        for o in channel_outages:
            o_start = max(o.started_at, period_start)
            # Rule 6: outage with no ended_at - conservatively count to period_end
            if o.ended_at is None:
                o_end = period_end
                ongoing_count += 1
            else:
                o_end = min(o.ended_at, period_end)
            if o_end > o_start:
                # Full outage = full duration counted; partial = 50% counted (industry convention)
                weight = 1.0 if o.severity == "FULL" else 0.5
                downtime_seconds += (o_end - o_start).total_seconds() * weight

        uptime = max(0.0, total_seconds - downtime_seconds)
        uptime_pct = (uptime / total_seconds) * 100

        target = CHANNEL_UPTIME_TARGET_PCT.get(channel)
        if target is None:
            severity = None
        else:
            target_f = float(target)
            gap_pp = target_f - uptime_pct
            if gap_pp <= float(UPTIME_GREEN_GAP_MAX_PP):
                severity = "GREEN"
            elif gap_pp <= float(UPTIME_AMBER_GAP_MAX_PP):
                severity = "AMBER"
            else:
                severity = "RED"

        return {
            "channel": channel,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "total_seconds": total_seconds,
            "downtime_seconds": round(downtime_seconds, 2),
            "uptime_pct": round(uptime_pct, 4),
            "target_pct": str(target) if target else None,
            "severity": severity,
            "ongoing_outages_count": ongoing_count,
            "outage_count": len(channel_outages),
        }

    @staticmethod
    def response_time_distribution(
        observations: List[LatencyObservation],
        channel: str,
    ) -> Dict[str, Any]:
        """Compute p50/p90/p99 response time. Rule 1: None on empty."""
        if channel not in CHANNELS:
            return {"channel": channel, "error": f"unknown_channel:{channel}"}

        ch_obs = [o for o in observations if o.channel == channel]
        valid = [float(o.response_time_ms) for o in ch_obs if o.response_time_ms >= 0]
        excluded = len(ch_obs) - len(valid)

        if not valid:
            return {
                "channel": channel,
                "observations_count": 0,
                "observations_excluded": excluded,
                "p50_ms": None,
                "p90_ms": None,
                "p99_ms": None,
                "reason": "no_valid_observations",
            }

        p50 = _percentile(valid, 50)
        p90 = _percentile(valid, 90)
        p99 = _percentile(valid, 99)
        target_p99 = CHANNEL_LATENCY_TARGET_P99_MS.get(channel)
        if p99 is None or target_p99 is None:
            severity = None
        elif p99 <= target_p99:
            severity = "GREEN"
        elif p99 <= target_p99 * 1.5:
            severity = "AMBER"
        else:
            severity = "RED"

        return {
            "channel": channel,
            "observations_count": len(valid),
            "observations_excluded": excluded,
            "p50_ms": round(p50, 1) if p50 else None,
            "p90_ms": round(p90, 1) if p90 else None,
            "p99_ms": round(p99, 1) if p99 else None,
            "max_ms": max(valid),
            "p99_target_ms": target_p99,
            "severity": severity,
        }

    @staticmethod
    def channel_sla_summary(
        outages: List[ChannelOutage],
        observations: List[LatencyObservation],
        period_start: datetime,
        period_end: datetime,
    ) -> Dict[str, Any]:
        """Bank-wide channel SLA summary."""
        results = []
        for ch in CHANNELS:
            up = ChannelSlaMonitoringEngine.uptime_pct(outages, ch, period_start, period_end)
            lat = ChannelSlaMonitoringEngine.response_time_distribution(observations, ch)
            # Combined severity: any RED → RED, else any AMBER → AMBER, else GREEN
            severities = [s for s in (up.get("severity"), lat.get("severity")) if s]
            if "RED" in severities:
                combined = "RED"
            elif "AMBER" in severities:
                combined = "AMBER"
            elif severities:
                combined = "GREEN"
            else:
                combined = None
            results.append({
                "channel": ch,
                "uptime_pct": up.get("uptime_pct"),
                "uptime_severity": up.get("severity"),
                "p99_ms": lat.get("p99_ms"),
                "latency_severity": lat.get("severity"),
                "combined_severity": combined,
            })
        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "channels": results,
        }

    @staticmethod
    def incident_mtbf_mttr(
        outages: List[ChannelOutage],
        channel: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Dict[str, Any]:
        """Mean time between failures + mean time to recover."""
        ch_out = sorted(
            [o for o in outages if o.channel == channel and o.started_at >= period_start],
            key=lambda x: x.started_at,
        )
        completed = [o for o in ch_out if o.ended_at is not None]

        # MTTR = avg duration of completed outages
        if not completed:
            mttr_minutes = None
        else:
            total_min = sum((o.ended_at - o.started_at).total_seconds() / 60 for o in completed)
            mttr_minutes = total_min / len(completed)

        # MTBF = mean gap between consecutive outage starts
        if len(ch_out) < 2:
            mtbf_hours = None
        else:
            gaps = []
            for i in range(1, len(ch_out)):
                gap = (ch_out[i].started_at - ch_out[i - 1].started_at).total_seconds() / 3600
                gaps.append(gap)
            mtbf_hours = sum(gaps) / len(gaps)

        return {
            "channel": channel,
            "outage_count": len(ch_out),
            "completed_outages": len(completed),
            "mttr_minutes": round(mttr_minutes, 2) if mttr_minutes is not None else None,
            "mtbf_hours": round(mtbf_hours, 2) if mtbf_hours is not None else None,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _test_uptime_no_outages_green():
    r = ChannelSlaMonitoringEngine.uptime_pct(
        [], "MOBILE",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    assert r["uptime_pct"] == 100.0
    assert r["severity"] == "GREEN"


def _test_uptime_with_outage():
    outages = [ChannelOutage(
        outage_id="O1", channel="MOBILE",
        started_at=_dt("2026-01-01T10:00:00+00:00"),
        ended_at=_dt("2026-01-01T10:30:00+00:00"),
        severity="FULL",
    )]
    r = ChannelSlaMonitoringEngine.uptime_pct(
        outages, "MOBILE",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    # 30 min outage in 1440 min = 97.92% uptime → below 99.9% target → RED
    assert r["uptime_pct"] < 99.9
    assert r["severity"] == "RED"


def _test_uptime_partial_outage_half_weighted():
    """PARTIAL outage counts at 50% of duration."""
    outages = [ChannelOutage(
        outage_id="O1", channel="MOBILE",
        started_at=_dt("2026-01-01T10:00:00+00:00"),
        ended_at=_dt("2026-01-01T11:00:00+00:00"),
        severity="PARTIAL",
    )]
    r = ChannelSlaMonitoringEngine.uptime_pct(
        outages, "MOBILE",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    # 60 min PARTIAL = 30 min full-weight downtime
    assert abs(r["downtime_seconds"] - 1800) < 1


def _test_uptime_invalid_period_rule1():
    r = ChannelSlaMonitoringEngine.uptime_pct(
        [], "MOBILE",
        _dt("2026-01-02T00:00:00+00:00"),
        _dt("2026-01-01T00:00:00+00:00"),  # end before start
    )
    assert r["uptime_pct"] is None


def _test_uptime_unknown_channel():
    r = ChannelSlaMonitoringEngine.uptime_pct(
        [], "WEIRD",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    assert "error" in r


def _test_uptime_ongoing_outage_rule6():
    """Rule 6: outage with no ended_at runs to period_end (not silently closed)."""
    outages = [ChannelOutage(
        outage_id="O1", channel="MOBILE",
        started_at=_dt("2026-01-01T20:00:00+00:00"),
        ended_at=None,  # ongoing
        severity="FULL",
    )]
    r = ChannelSlaMonitoringEngine.uptime_pct(
        outages, "MOBILE",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    # 20:00 to 24:00 = 4 hours = 14400 sec downtime
    assert abs(r["downtime_seconds"] - 14400) < 1
    assert r["ongoing_outages_count"] == 1


def _test_response_time_basic():
    obs = [
        LatencyObservation(obs_id=f"O{i}", channel="MOBILE", response_time_ms=100 + i,
                          observed_at=_dt("2026-01-01T10:00:00+00:00"))
        for i in range(100)
    ]
    r = ChannelSlaMonitoringEngine.response_time_distribution(obs, "MOBILE")
    assert r["observations_count"] == 100
    assert r["p99_ms"] is not None
    assert r["severity"] == "GREEN"  # all < 2000ms target


def _test_response_time_breach():
    obs = [LatencyObservation(obs_id=f"O{i}", channel="MOBILE", response_time_ms=5000,
                             observed_at=_dt("2026-01-01T10:00:00+00:00")) for i in range(10)]
    r = ChannelSlaMonitoringEngine.response_time_distribution(obs, "MOBILE")
    assert r["severity"] == "RED"  # 5000 > 1.5 × 2000


def _test_response_time_no_observations_rule1():
    r = ChannelSlaMonitoringEngine.response_time_distribution([], "MOBILE")
    assert r["p99_ms"] is None


def _test_channels_byte_for_byte():
    for ch in ("BRANCH", "ATM", "MOBILE", "INTERNET", "USSD", "AGENT", "POS", "API"):
        assert ch in CHANNELS


def _test_uptime_targets_byte_for_byte():
    assert CHANNEL_UPTIME_TARGET_PCT["MOBILE"] == Decimal("99.9")
    assert CHANNEL_UPTIME_TARGET_PCT["ATM"] == Decimal("99.5")


def _test_summary_aggregates():
    obs = [LatencyObservation(obs_id="O1", channel="MOBILE", response_time_ms=100,
                             observed_at=_dt("2026-01-01T10:00:00+00:00"))]
    r = ChannelSlaMonitoringEngine.channel_sla_summary(
        [], obs,
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    assert len(r["channels"]) == len(CHANNELS)


def _test_mttr_basic():
    outages = [
        ChannelOutage(outage_id="O1", channel="MOBILE",
                     started_at=_dt("2026-01-01T10:00:00+00:00"),
                     ended_at=_dt("2026-01-01T10:30:00+00:00")),
        ChannelOutage(outage_id="O2", channel="MOBILE",
                     started_at=_dt("2026-01-02T10:00:00+00:00"),
                     ended_at=_dt("2026-01-02T11:00:00+00:00")),
    ]
    r = ChannelSlaMonitoringEngine.incident_mtbf_mttr(
        outages, "MOBILE",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-03T00:00:00+00:00"),
    )
    assert r["mttr_minutes"] == 45.0  # avg of 30 + 60
    assert r["mtbf_hours"] == 24.0


def _test_mttr_no_data_rule1():
    r = ChannelSlaMonitoringEngine.incident_mtbf_mttr(
        [], "MOBILE",
        _dt("2026-01-01T00:00:00+00:00"),
        _dt("2026-01-02T00:00:00+00:00"),
    )
    assert r["mttr_minutes"] is None
    assert r["mtbf_hours"] is None


def self_test() -> bool:
    tests = [
        _test_uptime_no_outages_green,
        _test_uptime_with_outage,
        _test_uptime_partial_outage_half_weighted,
        _test_uptime_invalid_period_rule1,
        _test_uptime_unknown_channel,
        _test_uptime_ongoing_outage_rule6,
        _test_response_time_basic,
        _test_response_time_breach,
        _test_response_time_no_observations_rule1,
        _test_channels_byte_for_byte,
        _test_uptime_targets_byte_for_byte,
        _test_summary_aggregates,
        _test_mttr_basic,
        _test_mttr_no_data_rule1,
    ]
    print("=" * 60)
    print("Channel SLA Monitoring Engine — Self-Tests (#67)")
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

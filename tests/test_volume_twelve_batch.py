"""
================================================================================
A2Z MIS 360 — Volume Twelve Batch Tests (Standards #65-#68 Operations Excellence)
================================================================================

Tests Standards #65 Operations Dashboard, #66 Branch Operations Excellence,
#67 Channel SLA Monitoring, #68 Queue Analytics & CX.

Total: 54 unit tests covering deterministic ops scoring, TAT/error/wait time
       analytics, channel uptime + latency, queueing + CSAT/FCR.

Run via:
    pytest tests/test_volume_twelve_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.operations_dashboard import (
    OperationsDashboardEngine, OpsKpiReading,
    KPI_FAMILIES, LOWER_IS_BETTER_KPIS, UNIT_TYPES,
    STATUS_GREEN_THRESHOLD, STATUS_AMBER_THRESHOLD,
    STATUS_GREEN, STATUS_AMBER, STATUS_RED, STATUS_NO_DATA,
    _to_decimal as ops_dec,
)
from utils.branch_ops_excellence import (
    BranchOpsExcellenceEngine, TransactionRecord, WaitTimeObservation, OpsIncident,
    TAT_TARGETS, CUSTOMER_WAIT_P90_TARGET_MIN, CUSTOMER_WAIT_AMBER_P90_MIN,
    ERROR_RATE_GREEN_MAX, ERROR_RATE_AMBER_MAX,
    INCIDENT_STATUS_OPEN, INCIDENT_STATUS_INVESTIGATING,
    INCIDENT_STATUS_RESOLVED, INCIDENT_STATUS_ESCALATED,
    ALLOWED_INCIDENT_TRANSITIONS,
)
from utils.channel_sla import (
    ChannelSlaMonitoringEngine, ChannelOutage, LatencyObservation,
    CHANNELS, CHANNEL_UPTIME_TARGET_PCT, CHANNEL_LATENCY_TARGET_P99_MS,
    UPTIME_GREEN_GAP_MAX_PP, UPTIME_AMBER_GAP_MAX_PP,
)
from utils.queue_analytics import (
    QueueAnalyticsEngine, QueueEvent, CsatResponse, CustomerInteraction,
    WAIT_TIME_BUCKETS_MIN,
    CSAT_HEALTHY_PCT, CSAT_AMBER_PCT, CSAT_SATISFIED_MIN,
    ABANDONMENT_HEALTHY_PCT, ABANDONMENT_AMBER_PCT,
    FCR_HEALTHY_PCT, FCR_AMBER_PCT,
)


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ============================================================================
# #65 Operations Dashboard (12)
# ============================================================================

def _kpi(**kw):
    defaults = dict(
        kpi_id="K1", kpi_family="VOLUME", kpi_name="TXN_COUNT",
        unit_id="BR001", unit_type="BRANCH",
        actual=ops_dec(950), target=ops_dec(1000),
        period="2025_M12", direction="HIGHER_IS_BETTER",
    )
    defaults.update(kw)
    return OpsKpiReading(**defaults)


class TestOperationsDashboard:

    def test_kpi_families_byte_for_byte(self):
        for f in ("VOLUME", "QUALITY", "TIMELINESS", "PRODUCTIVITY", "COST"):
            assert f in KPI_FAMILIES

    def test_unit_types_byte_for_byte(self):
        for u in ("BRANCH", "BACK_OFFICE", "CALL_CENTER", "OPERATIONS_HUB"):
            assert u in UNIT_TYPES

    def test_status_thresholds_byte_for_byte(self):
        assert STATUS_GREEN_THRESHOLD == Decimal("0.95")
        assert STATUS_AMBER_THRESHOLD == Decimal("0.85")

    def test_status_green(self):
        r = OperationsDashboardEngine.compute_status(ops_dec(950), ops_dec(1000))
        assert r["status"] == STATUS_GREEN

    def test_status_amber(self):
        r = OperationsDashboardEngine.compute_status(ops_dec(900), ops_dec(1000))
        assert r["status"] == STATUS_AMBER

    def test_status_red(self):
        r = OperationsDashboardEngine.compute_status(ops_dec(500), ops_dec(1000))
        assert r["status"] == STATUS_RED

    def test_lower_is_better(self):
        r = OperationsDashboardEngine.compute_status(ops_dec(2), ops_dec(5), direction="LOWER_IS_BETTER")
        assert r["status"] == STATUS_GREEN

    def test_lower_is_better_breach(self):
        r = OperationsDashboardEngine.compute_status(ops_dec(10), ops_dec(5), direction="LOWER_IS_BETTER")
        assert r["status"] == STATUS_RED

    def test_no_data_target_zero_rule1(self):
        r = OperationsDashboardEngine.compute_status(ops_dec(100), ops_dec(0))
        assert r["status"] == STATUS_NO_DATA

    def test_no_data_missing_actual_rule6(self):
        r = OperationsDashboardEngine.compute_status(None, ops_dec(100))
        assert r["status"] == STATUS_NO_DATA

    def test_unit_scorecard_rolled_red(self):
        readings = [_kpi(kpi_id="K1", actual=ops_dec(500))]
        sc = OperationsDashboardEngine.unit_scorecard(readings, "BR001")
        assert sc["rolled_status"] == STATUS_RED

    def test_portfolio_summary(self):
        readings = [_kpi(kpi_id="K1", unit_id="BR001"), _kpi(kpi_id="K2", unit_id="BR002")]
        s = OperationsDashboardEngine.portfolio_summary(readings)
        assert s["total_units"] == 2


# ============================================================================
# #66 Branch Ops Excellence (13)
# ============================================================================

def _txn(**kw):
    defaults = dict(
        txn_id="T1", branch_id="BR001", transaction_type="ACCOUNT_OPENING",
        initiated_at=_dt("2026-01-01T10:00:00+00:00"),
        completed_at=_dt("2026-01-01T15:00:00+00:00"),
        has_error=False,
    )
    defaults.update(kw)
    return TransactionRecord(**defaults)


class TestBranchOpsExcellence:

    def test_tat_targets_byte_for_byte(self):
        assert TAT_TARGETS["ACCOUNT_OPENING"] == 1
        assert TAT_TARGETS["LOAN_DISBURSEMENT"] == 5
        assert TAT_TARGETS["CARD_ISSUANCE"] == 7

    def test_wait_targets_byte_for_byte(self):
        assert CUSTOMER_WAIT_P90_TARGET_MIN == 10
        assert CUSTOMER_WAIT_AMBER_P90_MIN == 15

    def test_error_thresholds_byte_for_byte(self):
        assert ERROR_RATE_GREEN_MAX == Decimal("1.0")
        assert ERROR_RATE_AMBER_MAX == Decimal("3.0")

    def test_tat_basic(self):
        txns = [_txn(business_days_elapsed=1), _txn(business_days_elapsed=2)]
        r = BranchOpsExcellenceEngine.turnaround_time(txns, "ACCOUNT_OPENING")
        assert r["target_business_days"] == 1
        assert r["sla_compliant_count"] == 1

    def test_tat_unknown_type(self):
        r = BranchOpsExcellenceEngine.turnaround_time([], "WEIRD")
        assert "error" in r

    def test_tat_no_completed_rule1(self):
        r = BranchOpsExcellenceEngine.turnaround_time(
            [_txn(completed_at=None)], "ACCOUNT_OPENING"
        )
        assert r["median_days"] is None

    def test_error_rate_severities(self):
        txns = [_txn(txn_id=f"T{i}", has_error=False) for i in range(98)]
        txns += [_txn(txn_id="T99", has_error=True), _txn(txn_id="T100", has_error=True)]
        r = BranchOpsExcellenceEngine.error_rate_by_branch(txns)
        br = r["branches"][0]
        assert br["error_rate_pct"] == 2.0
        assert br["severity"] == "AMBER"

    def test_wait_time_basic(self):
        obs = [
            WaitTimeObservation(obs_id="O1", branch_id="BR001", customer_id="C1",
                               queue_join_at=_dt("2026-01-01T10:00:00+00:00"),
                               service_start_at=_dt("2026-01-01T10:05:00+00:00")),
        ]
        r = BranchOpsExcellenceEngine.customer_wait_time(obs)
        assert r["severity"] == "GREEN"

    def test_wait_time_excluded_rule6(self):
        obs = [WaitTimeObservation(obs_id="O1", branch_id="BR001", customer_id="C1",
                                  queue_join_at=_dt("2026-01-01T10:00:00+00:00"),
                                  service_start_at=None)]
        r = BranchOpsExcellenceEngine.customer_wait_time(obs)
        assert r["observations_excluded"] == 1

    def test_incident_skip_rejected_rule4(self):
        inc = OpsIncident(incident_id="I1", branch_id="BR001",
                         severity="HIGH", description="x")
        ok, _ = BranchOpsExcellenceEngine.transition_incident(
            inc, INCIDENT_STATUS_RESOLVED, "off1", "fixed")
        assert not ok

    def test_incident_normal_path(self):
        inc = OpsIncident(incident_id="I1", branch_id="BR001",
                         severity="HIGH", description="x")
        assert BranchOpsExcellenceEngine.transition_incident(
            inc, INCIDENT_STATUS_INVESTIGATING, "off1")[0]
        assert BranchOpsExcellenceEngine.transition_incident(
            inc, INCIDENT_STATUS_RESOLVED, "off1", "fixed")[0]

    def test_incident_terminal(self):
        assert ALLOWED_INCIDENT_TRANSITIONS[INCIDENT_STATUS_RESOLVED] == ()

    def test_incident_resolution_reason_required(self):
        inc = OpsIncident(incident_id="I1", branch_id="BR001",
                         severity="HIGH", description="x", status=INCIDENT_STATUS_INVESTIGATING)
        ok, _ = BranchOpsExcellenceEngine.transition_incident(
            inc, INCIDENT_STATUS_RESOLVED, "off1", None)
        assert not ok


# ============================================================================
# #67 Channel SLA (14)
# ============================================================================

class TestChannelSla:

    def test_channels_byte_for_byte(self):
        for ch in ("BRANCH", "ATM", "MOBILE", "INTERNET", "USSD", "AGENT", "POS", "API"):
            assert ch in CHANNELS

    def test_uptime_targets_byte_for_byte(self):
        assert CHANNEL_UPTIME_TARGET_PCT["MOBILE"] == Decimal("99.9")
        assert CHANNEL_UPTIME_TARGET_PCT["ATM"] == Decimal("99.5")

    def test_latency_targets_byte_for_byte(self):
        assert CHANNEL_LATENCY_TARGET_P99_MS["MOBILE"] == 2000
        assert CHANNEL_LATENCY_TARGET_P99_MS["ATM"] == 5000

    def test_uptime_no_outages(self):
        r = ChannelSlaMonitoringEngine.uptime_pct(
            [], "MOBILE",
            _dt("2026-01-01T00:00:00+00:00"),
            _dt("2026-01-02T00:00:00+00:00"),
        )
        assert r["uptime_pct"] == 100.0

    def test_uptime_with_outage(self):
        outages = [ChannelOutage(outage_id="O1", channel="MOBILE",
                                started_at=_dt("2026-01-01T10:00:00+00:00"),
                                ended_at=_dt("2026-01-01T11:00:00+00:00"),
                                severity="FULL")]
        r = ChannelSlaMonitoringEngine.uptime_pct(
            outages, "MOBILE",
            _dt("2026-01-01T00:00:00+00:00"),
            _dt("2026-01-02T00:00:00+00:00"),
        )
        assert r["uptime_pct"] < 99.9
        assert r["severity"] == "RED"

    def test_uptime_partial_half_weighted(self):
        outages = [ChannelOutage(outage_id="O1", channel="MOBILE",
                                started_at=_dt("2026-01-01T10:00:00+00:00"),
                                ended_at=_dt("2026-01-01T11:00:00+00:00"),
                                severity="PARTIAL")]
        r = ChannelSlaMonitoringEngine.uptime_pct(
            outages, "MOBILE",
            _dt("2026-01-01T00:00:00+00:00"),
            _dt("2026-01-02T00:00:00+00:00"),
        )
        # 60 min PARTIAL = 30 min effective downtime
        assert abs(r["downtime_seconds"] - 1800) < 1

    def test_uptime_invalid_period_rule1(self):
        r = ChannelSlaMonitoringEngine.uptime_pct(
            [], "MOBILE",
            _dt("2026-01-02T00:00:00+00:00"),
            _dt("2026-01-01T00:00:00+00:00"),
        )
        assert r["uptime_pct"] is None

    def test_uptime_unknown_channel(self):
        r = ChannelSlaMonitoringEngine.uptime_pct(
            [], "WEIRD",
            _dt("2026-01-01T00:00:00+00:00"),
            _dt("2026-01-02T00:00:00+00:00"),
        )
        assert "error" in r

    def test_uptime_ongoing_outage_rule6(self):
        outages = [ChannelOutage(outage_id="O1", channel="MOBILE",
                                started_at=_dt("2026-01-01T20:00:00+00:00"),
                                ended_at=None, severity="FULL")]
        r = ChannelSlaMonitoringEngine.uptime_pct(
            outages, "MOBILE",
            _dt("2026-01-01T00:00:00+00:00"),
            _dt("2026-01-02T00:00:00+00:00"),
        )
        assert r["ongoing_outages_count"] == 1

    def test_latency_basic(self):
        obs = [LatencyObservation(obs_id=f"O{i}", channel="MOBILE",
                                 response_time_ms=100,
                                 observed_at=_dt("2026-01-01T10:00:00+00:00"))
              for i in range(50)]
        r = ChannelSlaMonitoringEngine.response_time_distribution(obs, "MOBILE")
        assert r["severity"] == "GREEN"

    def test_latency_breach(self):
        obs = [LatencyObservation(obs_id=f"O{i}", channel="MOBILE",
                                 response_time_ms=5000,
                                 observed_at=_dt("2026-01-01T10:00:00+00:00"))
              for i in range(10)]
        r = ChannelSlaMonitoringEngine.response_time_distribution(obs, "MOBILE")
        assert r["severity"] == "RED"

    def test_latency_no_observations_rule1(self):
        r = ChannelSlaMonitoringEngine.response_time_distribution([], "MOBILE")
        assert r["p99_ms"] is None

    def test_summary_aggregates(self):
        r = ChannelSlaMonitoringEngine.channel_sla_summary(
            [], [],
            _dt("2026-01-01T00:00:00+00:00"),
            _dt("2026-01-02T00:00:00+00:00"),
        )
        assert len(r["channels"]) == len(CHANNELS)

    def test_mttr_basic(self):
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
        assert r["mttr_minutes"] == 45.0


# ============================================================================
# #68 Queue Analytics & CX (15)
# ============================================================================

def _qe(**kw):
    defaults = dict(
        event_id="E1", queue_id="Q1", customer_id="C1",
        arrival_at=_dt("2026-01-01T10:00:00+00:00"),
        service_start_at=_dt("2026-01-01T10:03:00+00:00"),
        service_end_at=_dt("2026-01-01T10:08:00+00:00"),
    )
    defaults.update(kw)
    return QueueEvent(**defaults)


class TestQueueAnalytics:

    def test_csat_thresholds_byte_for_byte(self):
        assert CSAT_HEALTHY_PCT == 80.0
        assert CSAT_AMBER_PCT == 65.0
        assert CSAT_SATISFIED_MIN == 4

    def test_abandonment_thresholds_byte_for_byte(self):
        assert ABANDONMENT_HEALTHY_PCT == 5.0
        assert ABANDONMENT_AMBER_PCT == 10.0

    def test_fcr_thresholds_byte_for_byte(self):
        assert FCR_HEALTHY_PCT == 75.0
        assert FCR_AMBER_PCT == 60.0

    def test_wait_buckets_byte_for_byte(self):
        labels = [b[0] for b in WAIT_TIME_BUCKETS_MIN]
        for l in ("UNDER_2", "2_5", "5_10", "10_15", "15_30", "OVER_30"):
            assert l in labels

    def test_wait_distribution_basic(self):
        events = [
            _qe(event_id="E1",
                arrival_at=_dt("2026-01-01T10:00:00+00:00"),
                service_start_at=_dt("2026-01-01T10:01:00+00:00")),
            _qe(event_id="E2",
                arrival_at=_dt("2026-01-01T10:00:00+00:00"),
                service_start_at=_dt("2026-01-01T10:12:00+00:00")),
        ]
        r = QueueAnalyticsEngine.wait_time_distribution(events)
        assert r["observations_count"] == 2

    def test_wait_excluded_rule6(self):
        e = _qe(service_start_at=None, abandoned_at=None)
        r = QueueAnalyticsEngine.wait_time_distribution([e])
        assert r["observations_excluded"] == 1

    def test_wait_empty_rule1(self):
        r = QueueAnalyticsEngine.wait_time_distribution([])
        assert r["p50_min"] is None

    def test_service_distribution(self):
        r = QueueAnalyticsEngine.service_time_distribution([_qe()])
        assert r["p50_min"] == 5.0

    def test_abandonment_basic(self):
        events = [_qe(event_id="E1"), _qe(event_id="E2"),
                  QueueEvent(event_id="E3", queue_id="Q1", customer_id="C3",
                            arrival_at=_dt("2026-01-01T10:00:00+00:00"),
                            service_start_at=None,
                            abandoned_at=_dt("2026-01-01T10:08:00+00:00"))]
        r = QueueAnalyticsEngine.abandonment_rate(events)
        assert r["abandoned_count"] == 1
        assert round(r["abandonment_pct"], 1) == 33.3

    def test_abandonment_no_joiners_rule1(self):
        r = QueueAnalyticsEngine.abandonment_rate([])
        assert r["abandonment_pct"] is None

    def test_csat_basic(self):
        responses = [
            CsatResponse(response_id=f"R{i}", interaction_id=f"I{i}", customer_id=f"C{i}",
                        score=5, submitted_at=_dt("2026-01-01T10:00:00+00:00"))
            for i in range(8)
        ]
        responses += [CsatResponse(response_id="R9", interaction_id="I9", customer_id="C9",
                                   score=2, submitted_at=_dt("2026-01-01T10:00:00+00:00")),
                     CsatResponse(response_id="R10", interaction_id="I10", customer_id="C10",
                                  score=3, submitted_at=_dt("2026-01-01T10:00:00+00:00"))]
        r = QueueAnalyticsEngine.csat_aggregate(responses)
        assert r["csat_pct"] == 80.0
        assert r["severity"] == "GREEN"

    def test_csat_invalid_score_rule6(self):
        responses = [
            CsatResponse(response_id="R1", interaction_id="I1", customer_id="C1",
                        score=99, submitted_at=_dt("2026-01-01T10:00:00+00:00")),
        ]
        r = QueueAnalyticsEngine.csat_aggregate(responses)
        assert r["excluded_count"] == 1

    def test_csat_no_responses_rule1(self):
        r = QueueAnalyticsEngine.csat_aggregate([])
        assert r["csat_pct"] is None

    def test_fcr_basic(self):
        interactions = [
            CustomerInteraction(interaction_id=f"I{i}", customer_id=f"C{i}",
                               issue_category="ACCOUNT", contact_count=1, resolved=True,
                               started_at=_dt("2026-01-01T10:00:00+00:00"))
            for i in range(8)
        ]
        interactions += [CustomerInteraction(interaction_id=f"I{i}", customer_id=f"C{i}",
                                            issue_category="ACCOUNT", contact_count=2, resolved=True,
                                            started_at=_dt("2026-01-01T10:00:00+00:00"))
                        for i in range(8, 10)]
        r = QueueAnalyticsEngine.first_call_resolution(interactions)
        assert r["fcr_pct"] == 80.0

    def test_fcr_no_resolved_rule1(self):
        r = QueueAnalyticsEngine.first_call_resolution([
            CustomerInteraction(interaction_id="I1", customer_id="C1",
                               issue_category="ACCOUNT", contact_count=2, resolved=False,
                               started_at=_dt("2026-01-01T10:00:00+00:00"))])
        assert r["fcr_pct"] is None

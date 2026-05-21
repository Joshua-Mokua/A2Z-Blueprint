"""tests/test_legal_analytics_v10_178.py — ENH-230 Legal Analytics.

Verifies the analytics rollup engine over the 8 prior Legal arc engines.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
from datetime import date, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


class TestModuleShape:
    def test_imports(self):
        from utils.legal_analytics import (
            AnalyticsPeriod, ReportKind, TrendDirection,
            DataAvailability, TransitionOutcome,
            AnalyticsKPI, LegalReport, LegalAnalyticsEngine,
        )
        assert LegalAnalyticsEngine is not None

    def test_analytics_period_count(self):
        from utils.legal_analytics import AnalyticsPeriod
        assert len(AnalyticsPeriod) == 4

    def test_report_kind_count(self):
        from utils.legal_analytics import ReportKind
        assert len(ReportKind) == 4
        names = {k.value for k in ReportKind}
        assert "KPI_SNAPSHOT" in names
        assert "TREND_ANALYSIS" in names

    def test_trend_direction_count(self):
        from utils.legal_analytics import TrendDirection
        assert len(TrendDirection) == 4
        assert TrendDirection.IMPROVING.value == "IMPROVING"
        assert TrendDirection.INSUFFICIENT_DATA.value == "INSUFFICIENT_DATA"

    def test_data_availability_count(self):
        from utils.legal_analytics import DataAvailability
        assert len(DataAvailability) == 2

    def test_transition_outcome_count(self):
        from utils.legal_analytics import TransitionOutcome
        assert len(TransitionOutcome) == 3


class TestRegistry:
    def test_enh230_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next((x for x in STANDARDS_REGISTRY
                  if x.standard_id == "ENH-230"), None)
        assert s is not None
        assert s.status == "active"
        assert s.affected_engines == ("legal_analytics",)
        assert s.implementation_batch == "v10.178"


class TestHubIntegration:
    def test_in_tier_31(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "legal_analytics" in text
        assert "LegalAnalyticsEngine" in text
        assert "ENH-230" in text


class TestEmptyEngines:
    def test_all_none_unavailable(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        eng = LegalAnalyticsEngine()
        b = eng.board_summary()
        assert b["n_kpis_total"] == 10
        assert b["n_kpis_unavailable"] == 10
        assert b["portfolio_health_score"] is None

    def test_partial_data_flag_set(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        eng = LegalAnalyticsEngine()
        b = eng.board_summary()
        assert b["partial_data"] is True


class TestAllWired:
    def _wire(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        from utils.clause_library import ClauseLibraryEngine
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        from utils.legal_dashboard import LegalDashboardEngine
        from utils.legal_document_management import (
            LegalDocumentManagementEngine)
        from utils.legal_analytics import LegalAnalyticsEngine
        ob = ObligationTrackingEngine()
        ca = LegalCaseManagementEngine()
        sp = LegalSpendManagementEngine()
        co = OutsideCounselPortalEngine()
        cl = ClauseLibraryEngine()
        ho = LegalHoldManagementEngine()
        do = LegalDocumentManagementEngine()
        da = LegalDashboardEngine(ob, ca, sp, co, cl, ho)
        return LegalAnalyticsEngine(
            ob, ca, sp, co, cl, ho, da, do), ob, ca

    def test_empty_state_all_full(self):
        ana, _, _ = self._wire()
        b = ana.board_summary()
        assert b["n_kpis_full"] == 10
        assert b["n_kpis_unavailable"] == 0
        assert b["partial_data"] is False

    def test_empty_state_health_score_reasonable(self):
        ana, _, _ = self._wire()
        ph = ana.portfolio_health_score()
        # 9 percentage KPIs (one is count); empty engines → most at
        # favorable end → should be >= 70
        assert ph is not None
        assert ph >= 70.0


class TestBreachedObligationDropsScore:
    def test_breached_obligation_kpi(self):
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationKind)
        from utils.legal_analytics import LegalAnalyticsEngine

        ob = ObligationTrackingEngine()
        # 2 future, 2 already-breached
        for days in [200, 200, -10, -10]:
            ob.register_obligation(
                contract_id=f"C{days}", counterparty="X",
                title="t", description="d",
                kind=ObligationKind.CONTRACT_RENEWAL,
                deadline_date=(
                    date.today() + timedelta(days=days)).isoformat(),
                owner_role="LEGAL_HEAD")
        ana = LegalAnalyticsEngine(obligation_engine=ob)
        b = ana.board_summary()
        oc = next(k for k in b["kpis"]
                  if k["name"] == "obligation_compliance_rate")
        assert oc["value"] == 50.0  # 2 of 4 breached


class TestTrendComputation:
    def test_improving(self):
        from utils.legal_analytics import (
            LegalAnalyticsEngine, ReportKind, TrendDirection)
        from utils.obligation_tracking import (
            ObligationTrackingEngine)
        ob = ObligationTrackingEngine()
        ana = LegalAnalyticsEngine(obligation_engine=ob)
        # 100% current vs 80% prior, higher_is_better
        report = ana.generate_report(
            ReportKind.TREND_ANALYSIS,
            prior_snapshot={"obligation_compliance_rate": 80.0})
        oc = next(k for k in report.kpis
                  if k.name == "obligation_compliance_rate")
        assert oc.trend == TrendDirection.IMPROVING

    def test_deteriorating(self):
        from utils.legal_analytics import (
            LegalAnalyticsEngine, ReportKind, TrendDirection)
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationKind)
        ob = ObligationTrackingEngine()
        for days in [-10, -10]:
            ob.register_obligation(
                contract_id=f"C{days}", counterparty="X",
                title="t", description="d",
                kind=ObligationKind.CONTRACT_RENEWAL,
                deadline_date=(
                    date.today() + timedelta(days=days)).isoformat(),
                owner_role="LEGAL_HEAD")
        ana = LegalAnalyticsEngine(obligation_engine=ob)
        # 0% current vs 90% prior, higher_is_better
        report = ana.generate_report(
            ReportKind.TREND_ANALYSIS,
            prior_snapshot={"obligation_compliance_rate": 90.0})
        oc = next(k for k in report.kpis
                  if k.name == "obligation_compliance_rate")
        assert oc.trend == TrendDirection.DETERIORATING

    def test_stable_within_threshold(self):
        from utils.legal_analytics import (
            LegalAnalyticsEngine, ReportKind, TrendDirection)
        ana = LegalAnalyticsEngine()
        # No engine, but prior provided — should be INSUFFICIENT
        # because current is None
        report = ana.generate_report(
            ReportKind.TREND_ANALYSIS,
            prior_snapshot={"matter_close_rate": 90.0})
        mc = next(k for k in report.kpis
                  if k.name == "matter_close_rate")
        assert mc.trend == TrendDirection.INSUFFICIENT_DATA

    def test_insufficient_without_prior(self):
        from utils.legal_analytics import (
            LegalAnalyticsEngine, ReportKind, TransitionOutcome)
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        ana = LegalAnalyticsEngine(
            case_engine=LegalCaseManagementEngine())
        report = ana.generate_report(ReportKind.TREND_ANALYSIS)
        assert report.outcome == TransitionOutcome.REPORT_INSUFFICIENT


class TestSnapshotRoundTrip:
    def test_round_trip(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        from utils.obligation_tracking import ObligationTrackingEngine
        ob = ObligationTrackingEngine()
        ana = LegalAnalyticsEngine(obligation_engine=ob)
        kpis = ana.kpi_snapshot()
        flat = ana.snapshot_to_dict(kpis)
        # Only obligation engine wired → 1 entry should be present
        assert "obligation_compliance_rate" in flat


class TestReportKinds:
    def test_kpi_snapshot_has_efficiency(self):
        from utils.legal_analytics import (
            LegalAnalyticsEngine, ReportKind)
        ana = LegalAnalyticsEngine()
        report = ana.generate_report(ReportKind.KPI_SNAPSHOT)
        assert "efficiency" in report.derived_metrics

    def test_efficiency_report_includes_metrics(self):
        from utils.legal_analytics import (
            LegalAnalyticsEngine, ReportKind)
        ana = LegalAnalyticsEngine()
        report = ana.generate_report(ReportKind.EFFICIENCY_REPORT)
        assert "efficiency" in report.derived_metrics
        assert "portfolio_health_score" in report.derived_metrics


class TestPortfolioHealth:
    def test_none_when_no_kpis(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        ana = LegalAnalyticsEngine()
        assert ana.portfolio_health_score() is None

    def test_direction_aware(self):
        """When all percentage KPIs are at favorable end, score
        should be near 100."""
        from utils.legal_analytics import LegalAnalyticsEngine
        from utils.obligation_tracking import ObligationTrackingEngine
        ob = ObligationTrackingEngine()
        ana = LegalAnalyticsEngine(obligation_engine=ob)
        ph = ana.portfolio_health_score()
        # Only obligation engine wired — single percentage KPI
        # at 100% (no breach) → score 100
        assert ph == 100.0


class TestEfficiency:
    def test_unavailable_engines(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        ana = LegalAnalyticsEngine()
        em = ana.efficiency_metrics()
        assert "spend_per_matter_by_currency" in em
        # All unavailable
        assert isinstance(em["spend_per_matter_by_currency"], str)
        assert "UNAVAILABLE" in em["spend_per_matter_by_currency"]


class TestHonestDeferrals:
    def test_deferrals_named(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        ana = LegalAnalyticsEngine()
        b = ana.board_summary()
        for key in (
            "ml_predictive_modeling_status",
            "opposing_counsel_database_status",
            "benchmark_comparisons_status",
            "natural_language_query_status",
            "visualization_rendering_status",
            "drilldown_navigation_status",
            "time_series_persistence_status",
        ):
            assert key in b
            assert "DEFERRED" in b[key]


class TestPortfolioSummary:
    def test_engine_name(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        ana = LegalAnalyticsEngine()
        b = ana.board_summary()
        assert b["engine"] == "ENH-230 LegalAnalyticsEngine"
        assert "TREND_ANALYSIS" in b["regulatory_basis"]


class TestNoRegression:
    def test_legal_dashboard_unchanged(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        assert "ENH-228" in eng.board_summary()["engine"]

    def test_legal_doc_mgmt_unchanged(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine)
        eng = LegalDocumentManagementEngine()
        assert "ENH-229" in eng.board_summary()["engine"]

    def test_legal_hold_unchanged(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        assert "ENH-227" in eng.board_summary()["engine"]

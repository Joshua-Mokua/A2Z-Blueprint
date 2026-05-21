"""tests/integration/test_v10_26_audit_dashboards_portal.py — v10.26.

Phase 2 batch 4 (Audit/GRC arc batch 4): auditor dashboard + external
portal + committee reporting + board risk dashboard.
ENH-207 + ENH-208 + ENH-209 + ENH-AUD-R3.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1026Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import audit_dashboards_portal  # noqa

    def test_public_symbols(self):
        from utils import audit_dashboards_portal as m
        for sym in (
            # Auditor dashboard
            "DashboardViewMode", "KPIDirection", "KPIStatus",
            "AuditorDashboardKPI", "build_default_kpi_catalog",
            "AuditorDashboardSnapshot",
            # External auditor portal
            "ExternalAuditorAccessLevel",
            "ExternalAuditorRequestType",
            "EngagementScope", "ExternalAuditorAccessLog",
            "authorize_external_access",
            # Committee reporting
            "ReportingFrequency",
            "MINIMUM_AUDIT_COMMITTEE_REPORTING",
            "RiskHeatmapCell", "compute_risk_heatmap_cell",
            "PlanVsActual", "AuditCommitteeReport",
            "build_risk_heatmap_summary",
            # Board risk dashboard
            "RiskCategory", "RiskAppetiteStatus",
            "QuantifiedRiskMetric", "BoardRiskDashboard",
            # Engine
            "AuditDashboardsPortalEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1026SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import audit_dashboards_portal
        audit_dashboards_portal.self_test()


class TestV1026RegistryAlignment(unittest.TestCase):
    def test_16_audit_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "audit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 16)

    def test_v10_26_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "audit" and s.status == "active"}
        for sid in ("ENH-207", "ENH-208", "ENH-209", "ENH-AUD-R3"):
            self.assertIn(sid, active_ids)


class TestV1026AuditorDashboard(unittest.TestCase):
    """ENH-207 — Auditor dashboard & mobile."""

    def test_kpi_status_direction_aware(self):
        from utils.audit_dashboards_portal import (
            AuditorDashboardKPI, KPIDirection, KPIStatus)
        # HIGHER_IS_BETTER below threshold = RED
        k = AuditorDashboardKPI(
            kpi_name="Coverage",
            current_value=Decimal("60"),
            threshold_amber=Decimal("80"),
            threshold_red=Decimal("70"),
            direction=KPIDirection.HIGHER_IS_BETTER, unit="%")
        self.assertEqual(k.status(), KPIStatus.RED)

    def test_target_range_kpi_within(self):
        from utils.audit_dashboards_portal import (
            AuditorDashboardKPI, KPIDirection, KPIStatus)
        k = AuditorDashboardKPI(
            kpi_name="Capital Ratio",
            current_value=Decimal("18"),
            direction=KPIDirection.TARGET_RANGE,
            target_range_low=Decimal("14.5"),
            target_range_high=Decimal("22"))
        self.assertEqual(k.status(), KPIStatus.GREEN)

    def test_default_kpi_catalog_has_8_kpis(self):
        from utils.audit_dashboards_portal import (
            build_default_kpi_catalog)
        kpis = build_default_kpi_catalog(
            n_open_issues=10, n_overdue_issues=2,
            n_failed_tests=5, n_overdue_remediations=1,
            n_overdue_alerts=0, n_critical_anomalies=0,
            n_concentration_breaches=0,
            n_overdue_assessments=0)
        self.assertEqual(len(kpis), 8)

    def test_mobile_view_filters_to_top_4(self):
        from utils.audit_dashboards_portal import (
            AuditorDashboardSnapshot, AuditorDashboardKPI,
            KPIDirection, DashboardViewMode)
        snap = AuditorDashboardSnapshot(
            snapshot_id="S1", generated_at_utc="t",
            view_mode=DashboardViewMode.DESKTOP_FULL,
            kpis=tuple(
                AuditorDashboardKPI(
                    kpi_name=f"K{i}",
                    current_value=Decimal(str(i)),
                    threshold_amber=Decimal("3"),
                    threshold_red=Decimal("8"),
                    direction=KPIDirection.LOWER_IS_BETTER)
                for i in range(10)))
        mobile = snap.for_mobile(
            mode=DashboardViewMode.MOBILE_SUMMARY)
        self.assertEqual(len(mobile.kpis), 4)


class TestV1026ExternalAuditorPortal(unittest.TestCase):
    """ENH-208 — External auditor portal."""

    def _scope(self):
        from utils.audit_dashboards_portal import (
            EngagementScope, ExternalAuditorRequestType,
            ExternalAuditorAccessLevel)
        return EngagementScope(
            engagement_id="ENG1",
            external_audit_firm="PwC Kenya",
            engagement_name="FY2026 Statutory Audit",
            fiscal_period_start="2026-01-01",
            fiscal_period_end="2026-12-31",
            in_scope_entity_ids=("E1", "E2"),
            in_scope_request_types=(
                ExternalAuditorRequestType.TEST_RESULTS,
                ExternalAuditorRequestType.CONTROL_NARRATIVES),
            access_level=ExternalAuditorAccessLevel.READ_ONLY)

    def test_engagement_active_within_period(self):
        scope = self._scope()
        self.assertTrue(scope.is_active(as_of=date(2026, 6, 1)))

    def test_engagement_inactive_year_after(self):
        scope = self._scope()
        self.assertFalse(scope.is_active(as_of=date(2028, 1, 1)))

    def test_authorize_outside_request_type_denied(self):
        from utils.audit_dashboards_portal import (
            authorize_external_access,
            ExternalAuditorRequestType)
        granted, reason = authorize_external_access(
            scope=self._scope(),
            requested_object_type="BoardMinute",
            requested_object_id="BM1",
            request_type=ExternalAuditorRequestType.BOARD_MINUTES,
            requested_action="VIEW", as_of=date(2026, 6, 1))
        self.assertFalse(granted)
        self.assertIn("not in engagement scope", reason)

    def test_authorize_download_with_read_only_denied(self):
        from utils.audit_dashboards_portal import (
            authorize_external_access,
            ExternalAuditorRequestType)
        granted, reason = authorize_external_access(
            scope=self._scope(),
            requested_object_type="TestResult",
            requested_object_id="T1",
            request_type=ExternalAuditorRequestType.TEST_RESULTS,
            requested_action="DOWNLOAD",
            as_of=date(2026, 6, 1))
        self.assertFalse(granted)

    def test_authorize_view_within_scope_granted(self):
        from utils.audit_dashboards_portal import (
            authorize_external_access,
            ExternalAuditorRequestType)
        granted, _ = authorize_external_access(
            scope=self._scope(),
            requested_object_type="TestResult",
            requested_object_id="T1",
            request_type=ExternalAuditorRequestType.TEST_RESULTS,
            requested_action="VIEW", as_of=date(2026, 6, 1))
        self.assertTrue(granted)


class TestV1026CommitteeReporting(unittest.TestCase):
    """ENH-209 — Audit committee reporting."""

    def test_minimum_quarterly(self):
        from utils.audit_dashboards_portal import (
            MINIMUM_AUDIT_COMMITTEE_REPORTING, ReportingFrequency)
        self.assertEqual(
            MINIMUM_AUDIT_COMMITTEE_REPORTING,
            ReportingFrequency.QUARTERLY)

    def test_risk_heatmap_invalid_inputs_raise(self):
        from utils.audit_dashboards_portal import (
            compute_risk_heatmap_cell)
        with self.assertRaises(ValueError):
            compute_risk_heatmap_cell(
                likelihood=6, impact=3, risk_ids=())

    def test_heatmap_summary_categorizes_by_score(self):
        from utils.audit_dashboards_portal import (
            RiskHeatmapCell, build_risk_heatmap_summary)
        cells = (
            RiskHeatmapCell(likelihood=1, impact=1, n_risks=2,
                              risk_score=1),
            RiskHeatmapCell(likelihood=5, impact=5, n_risks=1,
                              risk_score=25),
        )
        summary = build_risk_heatmap_summary(cells=cells)
        self.assertEqual(summary["low"], 2)
        self.assertEqual(summary["critical"], 1)

    def test_plan_vs_actual_completion_and_variance(self):
        from utils.audit_dashboards_portal import PlanVsActual
        pva = PlanVsActual(
            fiscal_year=2026, planned_engagements=10,
            completed_engagements=4, in_progress_engagements=3,
            cancelled_engagements=1, planned_hours=2000,
            actual_hours_to_date=2400)
        self.assertEqual(pva.completion_pct(), Decimal("40"))
        self.assertEqual(pva.hours_variance_pct(), Decimal("20"))


class TestV1026BoardRiskDashboard(unittest.TestCase):
    """ENH-AUD-R3 — Board-ready risk-quantified dashboard."""

    def test_within_appetite(self):
        from utils.audit_dashboards_portal import (
            QuantifiedRiskMetric, RiskCategory, RiskAppetiteStatus)
        m = QuantifiedRiskMetric(
            metric_name="Credit",
            risk_category=RiskCategory.CREDIT,
            current_value_kes=Decimal("50000000"),
            appetite_limit_kes=Decimal("100000000"))
        self.assertEqual(
            m.appetite_status(),
            RiskAppetiteStatus.WITHIN_APPETITE)

    def test_approaching_limit_at_85pct(self):
        from utils.audit_dashboards_portal import (
            QuantifiedRiskMetric, RiskCategory, RiskAppetiteStatus)
        m = QuantifiedRiskMetric(
            metric_name="OpRisk",
            risk_category=RiskCategory.OPERATIONAL,
            current_value_kes=Decimal("85"),
            appetite_limit_kes=Decimal("100"))
        self.assertEqual(
            m.appetite_status(),
            RiskAppetiteStatus.APPROACHING_LIMIT)

    def test_breach_at_105pct(self):
        from utils.audit_dashboards_portal import (
            QuantifiedRiskMetric, RiskCategory, RiskAppetiteStatus)
        m = QuantifiedRiskMetric(
            metric_name="Cyber",
            risk_category=RiskCategory.CYBERSECURITY,
            current_value_kes=Decimal("105"),
            appetite_limit_kes=Decimal("100"))
        self.assertEqual(
            m.appetite_status(),
            RiskAppetiteStatus.LIMIT_BREACH)

    def test_dashboard_breaches_filter(self):
        from utils.audit_dashboards_portal import (
            BoardRiskDashboard, QuantifiedRiskMetric,
            RiskCategory)
        dash = BoardRiskDashboard(
            dashboard_id="BD1", fiscal_period="Q1-2026",
            generated_at_utc="t",
            risk_metrics=(
                QuantifiedRiskMetric(
                    metric_name="A", risk_category=RiskCategory.CREDIT,
                    current_value_kes=Decimal("50"),
                    appetite_limit_kes=Decimal("100")),
                QuantifiedRiskMetric(
                    metric_name="B",
                    risk_category=RiskCategory.CYBERSECURITY,
                    current_value_kes=Decimal("110"),
                    appetite_limit_kes=Decimal("100")),
            ))
        breaches = dash.metrics_in_breach()
        self.assertEqual(len(breaches), 1)
        self.assertEqual(breaches[0].metric_name, "B")

    def test_total_exposure_aggregation(self):
        from utils.audit_dashboards_portal import (
            BoardRiskDashboard, QuantifiedRiskMetric,
            RiskCategory)
        dash = BoardRiskDashboard(
            dashboard_id="BD1", fiscal_period="Q1-2026",
            generated_at_utc="t",
            risk_metrics=(
                QuantifiedRiskMetric(
                    metric_name="A",
                    risk_category=RiskCategory.CREDIT,
                    current_value_kes=Decimal("100"),
                    appetite_limit_kes=Decimal("200")),
                QuantifiedRiskMetric(
                    metric_name="B",
                    risk_category=RiskCategory.CREDIT,
                    current_value_kes=Decimal("50"),
                    appetite_limit_kes=Decimal("100")),
            ))
        totals = dash.total_exposure_by_category()
        self.assertEqual(totals[RiskCategory.CREDIT], Decimal("150"))


class TestV1026EngineEndToEnd(unittest.TestCase):
    def test_engine_full_external_auditor_flow(self):
        from utils.audit_dashboards_portal import (
            AuditDashboardsPortalEngine, EngagementScope,
            ExternalAuditorRequestType,
            ExternalAuditorAccessLevel)
        eng = AuditDashboardsPortalEngine()
        eng.register_engagement(EngagementScope(
            engagement_id="ENG1",
            external_audit_firm="PwC",
            engagement_name="FY2026",
            fiscal_period_start="2026-01-01",
            fiscal_period_end="2026-12-31",
            in_scope_entity_ids=("E1",),
            in_scope_request_types=(
                ExternalAuditorRequestType.TEST_RESULTS,),
            access_level=ExternalAuditorAccessLevel.READ_ONLY))
        # Try outside scope → denied
        log = eng.request_access(
            engagement_id="ENG1",
            auditor_user_id="ext_1",
            object_type="BoardMinute", object_id="BM1",
            request_type=ExternalAuditorRequestType.BOARD_MINUTES,
            action="VIEW", timestamp="t",
            as_of=date(2026, 6, 1))
        self.assertFalse(log.access_granted)
        self.assertEqual(len(eng.denied_access_attempts()), 1)


class TestV1026Coexistence(unittest.TestCase):
    def test_four_audit_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine)
        from utils.audit_analytics_vendor import (
            AuditAnalyticsVendorEngine)
        from utils.audit_dashboards_portal import (
            AuditDashboardsPortalEngine)
        engines = [
            AuditCoreEngine(entity_name="X"),
            AuditControlsIssuesEngine(entity_name="X"),
            AuditAnalyticsVendorEngine(entity_name="X"),
            AuditDashboardsPortalEngine(entity_name="X"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

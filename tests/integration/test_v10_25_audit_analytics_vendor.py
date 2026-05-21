"""tests/integration/test_v10_25_audit_analytics_vendor.py — v10.25.

Phase 2 batch 4 (Audit/GRC arc batch 3): analytics + vendor risk +
always-on assurance + cybersecurity framework integration.
ENH-205 + ENH-AUD-R2 + ENH-AUD-R5 + ENH-AUD-R6.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1025Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import audit_analytics_vendor  # noqa

    def test_public_symbols(self):
        from utils import audit_analytics_vendor as m
        for sym in (
            # Analytics
            "AnomalyDetectionMethod", "AnomalySeverity",
            "AnomalyResult", "compute_mean_std",
            "detect_z_score_anomalies", "detect_iqr_anomalies",
            "BENFORD_EXPECTED_DIGIT_PCT", "BenfordTestResult",
            "first_digit", "benford_conformance_test",
            "detect_with_ml_hook",
            # Vendor risk
            "VendorTier", "VendorCategory", "VendorRiskDimension",
            "VendorOnboardingStatus",
            "DEFAULT_VENDOR_REASSESSMENT_DAYS",
            "VendorRiskScore", "Vendor",
            "compute_overall_risk_score",
            "compute_concentration_risk",
            "DEFAULT_CONCENTRATION_THRESHOLD_PCT",
            "excessive_concentration_categories",
            # Always-on assurance
            "AssurancePriority", "ASSURANCE_RESPONSE_SLA_MINUTES",
            "AlertChannel", "AssuranceAlert",
            "select_channels_for_priority",
            # Cyber framework
            "NISTCSFFunction", "NIST_CSF_V2_CATEGORIES",
            "ISO27001ControlGroup", "ISO_27001_2022_CONTROL_COUNTS",
            "ISO_27001_2022_TOTAL_CONTROLS",
            "CISControlGroup", "CIS_V8_CONTROL_COUNT",
            "CIS_V8_SUBCONTROL_COUNT",
            "CyberFrameworkCoverage", "assess_nist_csf_coverage",
            # Engine
            "AuditAnalyticsVendorEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1025SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import audit_analytics_vendor
        audit_analytics_vendor.self_test()


class TestV1025RegistryAlignment(unittest.TestCase):
    def test_12_audit_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "audit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 12)

    def test_v10_25_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "audit" and s.status == "active"}
        for sid in ("ENH-205", "ENH-AUD-R2", "ENH-AUD-R5", "ENH-AUD-R6"):
            self.assertIn(sid, active_ids)


class TestV1025Analytics(unittest.TestCase):
    """ENH-205 — AI-powered audit analytics."""

    def test_z_score_detects_3sigma_outlier(self):
        from utils.audit_analytics_vendor import (
            detect_z_score_anomalies, AnomalySeverity)
        values = [(f"R{i}", Decimal(str(50 + i % 10)))
                    for i in range(100)]
        values.append(("OUT", Decimal("10000")))
        results = detect_z_score_anomalies(values=values)
        out = [r for r in results if r.record_id == "OUT"]
        self.assertEqual(len(out), 1)
        self.assertIn(out[0].severity, (
            AnomalySeverity.CRITICAL, AnomalySeverity.HIGH))

    def test_iqr_detects_extreme_outlier(self):
        from utils.audit_analytics_vendor import detect_iqr_anomalies
        values = [(f"R{i}", Decimal(str(50 + i)))
                    for i in range(30)]
        values.append(("OUT", Decimal("100000")))
        results = detect_iqr_anomalies(values=values)
        out = [r for r in results if r.record_id == "OUT"]
        self.assertEqual(len(out), 1)

    def test_benford_distribution_sums_to_100(self):
        from utils.audit_analytics_vendor import (
            BENFORD_EXPECTED_DIGIT_PCT)
        total = sum(BENFORD_EXPECTED_DIGIT_PCT.values(), Decimal("0"))
        self.assertGreater(total, Decimal("99.9"))
        self.assertLess(total, Decimal("100.1"))

    def test_benford_uniform_distribution_chi_square_high(self):
        from utils.audit_analytics_vendor import benford_conformance_test
        # Synthetic values uniformly distributed across digits 1-9
        values = []
        for d in range(1, 10):
            for i in range(20):
                values.append(Decimal(f"{d}{i:02d}"))
        result = benford_conformance_test(values=values)
        # Not Benford-distributed → high chi-square
        self.assertGreater(result.chi_square_statistic, Decimal("10"))

    def test_ml_hook_no_detector_returns_empty(self):
        """Rule 7: no detector → empty, no fabricated findings."""
        from utils.audit_analytics_vendor import detect_with_ml_hook
        results = detect_with_ml_hook(records=[{"x": 1}])
        self.assertEqual(len(results), 0)


class TestV1025VendorRisk(unittest.TestCase):
    """ENH-AUD-R2 — Vendor risk monitoring."""

    def test_assessment_cadence_critical_180_days(self):
        from utils.audit_analytics_vendor import (
            DEFAULT_VENDOR_REASSESSMENT_DAYS, VendorTier)
        self.assertEqual(
            DEFAULT_VENDOR_REASSESSMENT_DAYS[VendorTier.CRITICAL], 180)

    def test_concentration_breach_at_25pct_threshold(self):
        """80% in cloud category triggers breach at 25% threshold."""
        from utils.audit_analytics_vendor import (
            Vendor, VendorTier, VendorCategory,
            VendorOnboardingStatus,
            excessive_concentration_categories)
        vendors = [
            Vendor(
                vendor_id="BIG", vendor_name="Cloud",
                vendor_tier=VendorTier.CRITICAL,
                vendor_category=VendorCategory.CLOUD_INFRASTRUCTURE,
                onboarding_status=VendorOnboardingStatus.ACTIVE,
                services_provided="cloud",
                annual_spend_kes=Decimal("80000")),
            Vendor(
                vendor_id="SM", vendor_name="Small",
                vendor_tier=VendorTier.LOW,
                vendor_category=VendorCategory.PROFESSIONAL_SERVICES,
                onboarding_status=VendorOnboardingStatus.ACTIVE,
                services_provided="x",
                annual_spend_kes=Decimal("20000")),
        ]
        breaches = excessive_concentration_categories(
            vendors=vendors, threshold_pct=Decimal("25"))
        self.assertEqual(len(breaches), 1)

    def test_engine_assess_unregistered_vendor_raises(self):
        from utils.audit_analytics_vendor import (
            AuditAnalyticsVendorEngine, VendorRiskDimension)
        eng = AuditAnalyticsVendorEngine()
        with self.assertRaises(KeyError):
            eng.assess_vendor_risk(
                vendor_id="UNKNOWN",
                dimension_scores={
                    VendorRiskDimension.FINANCIAL: Decimal("50")},
                assessment_date="2026-01-01")

    def test_engine_assessment_computes_next_due(self):
        from utils.audit_analytics_vendor import (
            AuditAnalyticsVendorEngine, Vendor, VendorTier,
            VendorCategory, VendorOnboardingStatus,
            VendorRiskDimension)
        eng = AuditAnalyticsVendorEngine()
        eng.register_vendor(Vendor(
            vendor_id="V1", vendor_name="X",
            vendor_tier=VendorTier.CRITICAL,
            vendor_category=VendorCategory.CORE_BANKING,
            onboarding_status=VendorOnboardingStatus.ACTIVE,
            services_provided="x"))
        score = eng.assess_vendor_risk(
            vendor_id="V1",
            dimension_scores={
                VendorRiskDimension.FINANCIAL: Decimal("60"),
                VendorRiskDimension.CYBER: Decimal("70")},
            assessment_date="2026-01-01")
        self.assertEqual(score.next_assessment_due, "2026-06-30")

    def test_overall_risk_score_simple_average(self):
        from utils.audit_analytics_vendor import (
            VendorRiskDimension, compute_overall_risk_score)
        score = compute_overall_risk_score(
            dimension_scores={
                VendorRiskDimension.FINANCIAL: Decimal("60"),
                VendorRiskDimension.CYBER: Decimal("80")})
        self.assertEqual(score, Decimal("70"))


class TestV1025AlwaysOnAssurance(unittest.TestCase):
    """ENH-AUD-R5 — 24/7 always-on assurance."""

    def test_p1_critical_15_minute_sla(self):
        from utils.audit_analytics_vendor import (
            ASSURANCE_RESPONSE_SLA_MINUTES, AssurancePriority)
        self.assertEqual(
            ASSURANCE_RESPONSE_SLA_MINUTES[
                AssurancePriority.P1_CRITICAL], 15)

    def test_p1_alert_overdue_after_30_min(self):
        from utils.audit_analytics_vendor import (
            AssuranceAlert, AssurancePriority)
        alert = AssuranceAlert(
            alert_id="A1", priority=AssurancePriority.P1_CRITICAL,
            detected_at_utc="2026-04-23T10:00:00Z")
        self.assertTrue(alert.is_overdue_for_response(
            as_of_utc="2026-04-23T10:30:00Z"))

    def test_acknowledged_alert_not_overdue(self):
        from utils.audit_analytics_vendor import (
            AssuranceAlert, AssurancePriority)
        alert = AssuranceAlert(
            alert_id="A1", priority=AssurancePriority.P1_CRITICAL,
            detected_at_utc="2026-04-23T10:00:00Z",
            acknowledged_at_utc="2026-04-23T10:10:00Z",
            acknowledged_by_user_id="alice")
        self.assertFalse(alert.is_overdue_for_response(
            as_of_utc="2026-04-23T15:00:00Z"))

    def test_p1_routes_to_pagerduty(self):
        from utils.audit_analytics_vendor import (
            AssurancePriority, AlertChannel,
            select_channels_for_priority)
        chans = select_channels_for_priority(
            AssurancePriority.P1_CRITICAL)
        self.assertIn(AlertChannel.PAGERDUTY, chans)
        self.assertIn(AlertChannel.SMS, chans)


class TestV1025CyberFramework(unittest.TestCase):
    """ENH-AUD-R6 — Cybersecurity framework integration."""

    def test_iso_27001_2022_total_93(self):
        from utils.audit_analytics_vendor import (
            ISO_27001_2022_TOTAL_CONTROLS,
            ISO_27001_2022_CONTROL_COUNTS)
        self.assertEqual(ISO_27001_2022_TOTAL_CONTROLS, 93)
        self.assertEqual(
            sum(ISO_27001_2022_CONTROL_COUNTS.values()), 93)

    def test_nist_csf_v2_six_functions(self):
        from utils.audit_analytics_vendor import NISTCSFFunction
        self.assertEqual(len(NISTCSFFunction), 6)
        # GOVERN is new in v2.0
        self.assertEqual(NISTCSFFunction.GOVERN.value, "GV")

    def test_cis_v8_153_subcontrols(self):
        from utils.audit_analytics_vendor import (
            CIS_V8_CONTROL_COUNT, CIS_V8_SUBCONTROL_COUNT)
        self.assertEqual(CIS_V8_CONTROL_COUNT, 18)
        self.assertEqual(CIS_V8_SUBCONTROL_COUNT, 153)

    def test_nist_csf_full_coverage(self):
        from utils.audit_analytics_vendor import (
            NISTCSFFunction, NIST_CSF_V2_CATEGORIES,
            assess_nist_csf_coverage)
        full = {
            fn: len(cats)
            for fn, cats in NIST_CSF_V2_CATEGORIES.items()}
        coverage = assess_nist_csf_coverage(
            n_implemented_per_function=full)
        for fn_cov in coverage.values():
            self.assertEqual(fn_cov.coverage_pct, Decimal("100"))
            self.assertTrue(fn_cov.meets_target())


class TestV1025Coexistence(unittest.TestCase):
    def test_three_audit_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine)
        from utils.audit_analytics_vendor import (
            AuditAnalyticsVendorEngine)
        a = AuditCoreEngine(entity_name="X")
        b = AuditControlsIssuesEngine(entity_name="X")
        c = AuditAnalyticsVendorEngine(entity_name="X")
        for e in (a, b, c):
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

"""
================================================================================
A2Z MIS 360 — Volume Sixteen Batch Tests (Standards #81-#84 Internal Audit)
================================================================================

Tests Standards #81 Audit Universe & Risk-Based Audit Planning, #82 Internal
Controls Framework (COSO + ISA 530), #83 Issue Management & Remediation,
#84 Audit Reporting & Audit Committee Dashboard.

Total: 85 unit tests covering IIA risk-based audit planning, COSO 2013
       framework with 17 principles, ISA 530 sample sizing, PCAOB AS 2201
       deficiency severity classification, audit issue lifecycle, and
       ISA 700 audit reporting.

Run via:
    pytest tests/test_volume_sixteen_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.audit_universe import (
    AuditUniverseEngine, AuditableEntity,
    HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD,
    RISK_TIERS, AUDIT_FREQUENCY_MONTHS,
    INHERENT_RISK_WEIGHTS_PCT, CONTROL_RATINGS, CONTROL_RATING_BANDS,
    ENTITY_TYPES,
)
from utils.internal_controls import (
    InternalControlsEngine, ControlTest, ControlDeficiency,
    COSO_COMPONENTS, COSO_PRINCIPLES, TOTAL_COSO_PRINCIPLES,
    SAMPLE_SIZES_BY_RISK, DEFICIENCY_SEVERITIES,
    TOLERABLE_EXCEPTION_RATE_PCT,
    SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT, MATERIAL_WEAKNESS_THRESHOLD_PCT,
)
from utils.issue_management import (
    IssueManagementEngine, AuditIssue,
    ISSUE_SEVERITIES, SLA_TARGET_DAYS,
    AGING_BUCKETS, AGING_BUCKET_DAYS,
    ESCALATION_THRESHOLD_DAYS, CLUSTER_ESCALATION_THRESHOLD,
    CRITICAL_IMPACT_KES, HIGH_IMPACT_KES, MEDIUM_IMPACT_KES,
)
from utils.audit_reporting import (
    AuditReportingEngine, AuditReport, AuditRecommendation,
    AUDIT_OPINIONS, REQUIRED_REPORT_SECTIONS,
    COVERAGE_THRESHOLDS_PCT, COVERAGE_RATINGS,
    RECOMMENDATION_AGING_MONTHS, RECOMMENDATION_AGING_BUCKETS,
)


# ============================================================================
# #81 Audit Universe (18)
# ============================================================================

def _entity(**kw):
    defaults = dict(
        entity_id="E1", entity_name="Branch Nairobi CBD",
        entity_type="BRANCH",
        financial_materiality_kes=Decimal("60000000"),
        transaction_volume=Decimal("70"),
        regulatory_exposure=Decimal("80"),
        fraud_susceptibility=Decimal("60"),
        process_complexity=Decimal("50"),
        change_velocity=Decimal("40"),
        control_score=Decimal("70"),
    )
    defaults.update(kw)
    return AuditableEntity(**defaults)


class TestAuditUniverse:

    def test_risk_tier_thresholds_byte_for_byte(self):
        assert HIGH_RISK_THRESHOLD == Decimal("70")
        assert MEDIUM_RISK_THRESHOLD == Decimal("40")

    def test_audit_frequency_byte_for_byte(self):
        assert AUDIT_FREQUENCY_MONTHS["HIGH"] == 12
        assert AUDIT_FREQUENCY_MONTHS["MEDIUM"] == 24
        assert AUDIT_FREQUENCY_MONTHS["LOW"] == 36

    def test_inherent_weights_sum_to_100(self):
        assert sum(INHERENT_RISK_WEIGHTS_PCT.values()) == Decimal("100")

    def test_inherent_weights_byte_for_byte(self):
        assert INHERENT_RISK_WEIGHTS_PCT["financial_materiality_kes"] == Decimal("30")
        assert INHERENT_RISK_WEIGHTS_PCT["transaction_volume"] == Decimal("15")
        assert INHERENT_RISK_WEIGHTS_PCT["regulatory_exposure"] == Decimal("20")
        assert INHERENT_RISK_WEIGHTS_PCT["fraud_susceptibility"] == Decimal("15")
        assert INHERENT_RISK_WEIGHTS_PCT["process_complexity"] == Decimal("10")
        assert INHERENT_RISK_WEIGHTS_PCT["change_velocity"] == Decimal("10")

    def test_control_rating_bands_byte_for_byte(self):
        assert CONTROL_RATING_BANDS["EFFECTIVE"] == (Decimal("90"), Decimal("100"))
        assert CONTROL_RATING_BANDS["LARGELY_EFFECTIVE"] == (Decimal("70"), Decimal("89"))
        assert CONTROL_RATING_BANDS["PARTIALLY_EFFECTIVE"] == (Decimal("50"), Decimal("69"))
        assert CONTROL_RATING_BANDS["INEFFECTIVE"] == (Decimal("25"), Decimal("49"))
        assert CONTROL_RATING_BANDS["NON_EXISTENT"] == (Decimal("0"), Decimal("24"))

    def test_inherent_score_basic(self):
        r = AuditUniverseEngine.inherent_risk_score(_entity())
        assert r["inherent_risk_score"] == "68.50"

    def test_residual_risk_with_control(self):
        r = AuditUniverseEngine.residual_risk_score(_entity())
        assert r["risk_tier"] == "LOW"

    def test_residual_no_control_assumes_worst(self):
        r = AuditUniverseEngine.residual_risk_score(_entity(control_score=None))
        assert r["control_basis"] == "no_control_data_assumed_no_mitigation"

    def test_high_risk_classification(self):
        e = _entity(financial_materiality_kes=Decimal("200000000"),
                    transaction_volume=Decimal("100"),
                    regulatory_exposure=Decimal("100"),
                    fraud_susceptibility=Decimal("100"),
                    process_complexity=Decimal("100"),
                    change_velocity=Decimal("100"),
                    control_score=Decimal("10"))
        r = AuditUniverseEngine.residual_risk_score(e)
        assert r["risk_tier"] == "HIGH"
        assert r["audit_frequency_months"] == 12

    def test_inherent_missing_factors_rule6(self):
        e = _entity(transaction_volume=None, fraud_susceptibility=None)
        r = AuditUniverseEngine.inherent_risk_score(e)
        assert "transaction_volume" in r["missing_factors"]

    def test_inherent_all_missing_rule6(self):
        e = AuditableEntity(entity_id="E1", entity_name="X", entity_type="BRANCH")
        r = AuditUniverseEngine.inherent_risk_score(e)
        assert r["inherent_risk_score"] is None

    def test_residual_no_inherent_rule1(self):
        e = AuditableEntity(entity_id="E1", entity_name="X", entity_type="BRANCH")
        r = AuditUniverseEngine.residual_risk_score(e)
        assert r["residual_risk_score"] is None

    def test_control_rating_effective(self):
        r = AuditUniverseEngine.control_environment_score(Decimal("95"))
        assert r["control_rating"] == "EFFECTIVE"

    def test_control_rating_ineffective(self):
        r = AuditUniverseEngine.control_environment_score(Decimal("30"))
        assert r["control_rating"] == "INEFFECTIVE"

    def test_control_rating_out_of_range(self):
        r = AuditUniverseEngine.control_environment_score(Decimal("150"))
        assert "error" in r

    def test_audit_plan_high_risk_annual(self):
        e = _entity(financial_materiality_kes=Decimal("200000000"),
                    transaction_volume=Decimal("100"),
                    regulatory_exposure=Decimal("100"),
                    fraud_susceptibility=Decimal("100"),
                    process_complexity=Decimal("100"),
                    change_velocity=Decimal("100"),
                    control_score=Decimal("0"))
        plan = AuditUniverseEngine.generate_audit_plan(
            [e], plan_start=date(2026, 1, 1), plan_horizon_years=3)
        assert len([a for a in plan["scheduled_audits"]]) == 3

    def test_audit_plan_low_risk_triennial(self):
        plan = AuditUniverseEngine.generate_audit_plan(
            [_entity(control_score=Decimal("95"))],
            plan_start=date(2026, 1, 1), plan_horizon_years=3)
        assert len(plan["scheduled_audits"]) == 1

    def test_audit_universe_summary(self):
        entities = [_entity(entity_id=f"E{i}") for i in range(5)]
        r = AuditUniverseEngine.audit_universe_summary(entities)
        assert r["total_entities"] == 5


# ============================================================================
# #82 Internal Controls (23)
# ============================================================================

class TestInternalControls:

    def test_coso_components_byte_for_byte(self):
        for c in ("CONTROL_ENVIRONMENT", "RISK_ASSESSMENT", "CONTROL_ACTIVITIES",
                  "INFORMATION_COMMUNICATION", "MONITORING_ACTIVITIES"):
            assert c in COSO_COMPONENTS

    def test_total_principles_byte_for_byte(self):
        total = sum(len(p) for p in COSO_PRINCIPLES.values())
        assert total == TOTAL_COSO_PRINCIPLES == 17

    def test_principles_per_component_byte_for_byte(self):
        # Verify principle counts byte-for-byte per component
        assert len(COSO_PRINCIPLES["CONTROL_ENVIRONMENT"]) == 5
        assert len(COSO_PRINCIPLES["RISK_ASSESSMENT"]) == 4
        assert len(COSO_PRINCIPLES["CONTROL_ACTIVITIES"]) == 3
        assert len(COSO_PRINCIPLES["INFORMATION_COMMUNICATION"]) == 3
        assert len(COSO_PRINCIPLES["MONITORING_ACTIVITIES"]) == 2

    def test_sample_sizes_byte_for_byte(self):
        assert SAMPLE_SIZES_BY_RISK["LOW"] == 25
        assert SAMPLE_SIZES_BY_RISK["MEDIUM"] == 40
        assert SAMPLE_SIZES_BY_RISK["HIGH"] == 60
        assert SAMPLE_SIZES_BY_RISK["KEY"] == 90

    def test_tolerance_byte_for_byte(self):
        assert TOLERABLE_EXCEPTION_RATE_PCT["LOW"] == Decimal("10")
        assert TOLERABLE_EXCEPTION_RATE_PCT["MEDIUM"] == Decimal("5")
        assert TOLERABLE_EXCEPTION_RATE_PCT["HIGH"] == Decimal("2")
        assert TOLERABLE_EXCEPTION_RATE_PCT["KEY"] == Decimal("0")

    def test_severity_thresholds_byte_for_byte(self):
        assert SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT == Decimal("1")
        assert MATERIAL_WEAKNESS_THRESHOLD_PCT == Decimal("5")

    def test_deficiency_severities_byte_for_byte(self):
        for s in ("DEFICIENCY", "SIGNIFICANT_DEFICIENCY", "MATERIAL_WEAKNESS"):
            assert s in DEFICIENCY_SEVERITIES

    def test_sample_size_low(self):
        r = InternalControlsEngine.sample_size("LOW")
        assert r["sample_size"] == 25

    def test_sample_size_key(self):
        r = InternalControlsEngine.sample_size("KEY")
        assert r["sample_size"] == 90

    def test_sample_size_unknown(self):
        r = InternalControlsEngine.sample_size("WEIRD")
        assert "error" in r

    def test_control_test_effective(self):
        t = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM", sample_size=40, exceptions_found=0)
        r = InternalControlsEngine.test_control(t)
        assert r["outcome"] == "EFFECTIVE"

    def test_control_test_partially_effective(self):
        t = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM", sample_size=40, exceptions_found=2)
        r = InternalControlsEngine.test_control(t)
        assert r["outcome"] == "PARTIALLY_EFFECTIVE"

    def test_control_test_ineffective(self):
        t = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="KEY", sample_size=90, exceptions_found=1)
        r = InternalControlsEngine.test_control(t)
        assert r["outcome"] == "INEFFECTIVE"

    def test_control_test_sample_inadequate(self):
        t = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="KEY", sample_size=30, exceptions_found=0)
        r = InternalControlsEngine.test_control(t)
        assert r["sample_adequate"] is False

    def test_control_test_zero_sample_rule1(self):
        t = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES",
                       risk_level="MEDIUM", sample_size=0, exceptions_found=0)
        r = InternalControlsEngine.test_control(t)
        assert r["effectiveness_pct"] is None

    def test_control_test_missing_data_rule6(self):
        t = ControlTest(test_id="T1", control_id="C1",
                       coso_component="CONTROL_ACTIVITIES", risk_level="MEDIUM")
        r = InternalControlsEngine.test_control(t)
        assert r["outcome"] is None

    def test_deficiency_classification_basic(self):
        d = ControlDeficiency(
            deficiency_id="D1", control_id="C1", description="X",
            estimated_financial_impact_kes=Decimal("500000"),
            total_assets_kes=Decimal("1000000000"))
        r = InternalControlsEngine.classify_deficiency(d)
        assert r["severity"] == "DEFICIENCY"

    def test_deficiency_significant(self):
        d = ControlDeficiency(
            deficiency_id="D1", control_id="C1", description="X",
            estimated_financial_impact_kes=Decimal("20000000"),
            total_assets_kes=Decimal("1000000000"))
        r = InternalControlsEngine.classify_deficiency(d)
        assert r["severity"] == "SIGNIFICANT_DEFICIENCY"

    def test_deficiency_material_weakness(self):
        d = ControlDeficiency(
            deficiency_id="D1", control_id="C1", description="X",
            estimated_financial_impact_kes=Decimal("60000000"),
            total_assets_kes=Decimal("1000000000"))
        r = InternalControlsEngine.classify_deficiency(d)
        assert r["severity"] == "MATERIAL_WEAKNESS"

    def test_deficiency_escalates_no_compensating(self):
        d = ControlDeficiency(
            deficiency_id="D1", control_id="C1", description="X",
            estimated_financial_impact_kes=Decimal("100000"),
            total_assets_kes=Decimal("1000000000"),
            affects_financial_reporting=True,
            compensating_controls_exist=False)
        r = InternalControlsEngine.classify_deficiency(d)
        assert r["severity"] == "SIGNIFICANT_DEFICIENCY"

    def test_deficiency_zero_assets_rule1(self):
        d = ControlDeficiency(
            deficiency_id="D1", control_id="C1", description="X",
            estimated_financial_impact_kes=Decimal("100000"),
            total_assets_kes=Decimal("0"))
        r = InternalControlsEngine.classify_deficiency(d)
        assert r["severity"] is None

    def test_coso_component_score_basic(self):
        ratings = {p: Decimal("80") for principles in COSO_PRINCIPLES.values()
                   for p in principles}
        r = InternalControlsEngine.coso_component_score(ratings)
        assert r["overall_score"] == "80.00"

    def test_effectiveness_summary(self):
        results = [
            {"coso_component": "CONTROL_ACTIVITIES", "outcome": "EFFECTIVE"},
            {"coso_component": "CONTROL_ACTIVITIES", "outcome": "EFFECTIVE"},
            {"coso_component": "MONITORING_ACTIVITIES", "outcome": "INEFFECTIVE"},
        ]
        r = InternalControlsEngine.control_effectiveness_summary(results)
        assert r["overall_effectiveness_pct"] == "66.67"


# ============================================================================
# #83 Issue Management (26)
# ============================================================================

def _issue(**kw):
    defaults = dict(
        issue_id="I1", description="Test issue",
        business_unit="RETAIL_BANKING",
        status="OPEN",
        raised_date=date(2026, 1, 1),
        estimated_financial_impact_kes=Decimal("5000000"),
    )
    defaults.update(kw)
    return AuditIssue(**defaults)


class TestIssueManagement:

    def test_severities_byte_for_byte(self):
        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            assert s in ISSUE_SEVERITIES

    def test_sla_targets_byte_for_byte(self):
        assert SLA_TARGET_DAYS["CRITICAL"] == 30
        assert SLA_TARGET_DAYS["HIGH"] == 60
        assert SLA_TARGET_DAYS["MEDIUM"] == 90
        assert SLA_TARGET_DAYS["LOW"] == 180

    def test_aging_buckets_byte_for_byte(self):
        for b in ("CURRENT", "EARLY_AGED", "AGED", "PROLONGED", "OVERDUE"):
            assert b in AGING_BUCKETS

    def test_aging_bucket_days_byte_for_byte(self):
        assert AGING_BUCKET_DAYS["CURRENT"] == (0, 30)
        assert AGING_BUCKET_DAYS["EARLY_AGED"] == (31, 60)
        assert AGING_BUCKET_DAYS["AGED"] == (61, 90)
        assert AGING_BUCKET_DAYS["PROLONGED"] == (91, 180)

    def test_escalation_thresholds_byte_for_byte(self):
        assert ESCALATION_THRESHOLD_DAYS["CRITICAL"] == 30
        assert ESCALATION_THRESHOLD_DAYS["HIGH"] == 60
        assert ESCALATION_THRESHOLD_DAYS["MEDIUM"] == 90

    def test_cluster_threshold_byte_for_byte(self):
        assert CLUSTER_ESCALATION_THRESHOLD == 5

    def test_severity_critical(self):
        i = _issue(estimated_financial_impact_kes=Decimal("200000000"))
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] == "CRITICAL"

    def test_severity_high(self):
        i = _issue(estimated_financial_impact_kes=Decimal("50000000"))
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] == "HIGH"

    def test_severity_medium(self):
        i = _issue(estimated_financial_impact_kes=Decimal("5000000"))
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] == "MEDIUM"

    def test_severity_low(self):
        i = _issue(estimated_financial_impact_kes=Decimal("100000"))
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] == "LOW"

    def test_severity_regulatory_escalates(self):
        i = _issue(estimated_financial_impact_kes=Decimal("100000"),
                   is_regulatory_finding=True)
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] == "CRITICAL"

    def test_severity_fraud_escalates(self):
        i = _issue(estimated_financial_impact_kes=Decimal("100000"),
                   is_fraud_related=True)
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] == "CRITICAL"

    def test_severity_missing_impact_rule6(self):
        i = _issue(estimated_financial_impact_kes=None)
        r = IssueManagementEngine.classify_issue_severity(i)
        assert r["severity"] is None

    def test_aging_bucket_current(self):
        i = _issue(raised_date=date(2026, 4, 15))
        r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
        assert r["aging_bucket"] == "CURRENT"

    def test_aging_bucket_overdue(self):
        i = _issue(raised_date=date(2025, 10, 1))
        r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
        assert r["aging_bucket"] == "OVERDUE"

    def test_aging_bucket_uses_closed_date(self):
        i = _issue(raised_date=date(2026, 1, 1), status="CLOSED",
                   closed_date=date(2026, 2, 1))
        r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
        assert r["days_open"] == 31

    def test_aging_bucket_missing_date_rule6(self):
        i = _issue(raised_date=None)
        r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
        assert r["aging_bucket"] is None

    def test_sla_breach_high(self):
        i = _issue(raised_date=date(2026, 1, 30), severity="HIGH", status="OPEN")
        r = IssueManagementEngine.sla_breach_check(i, date(2026, 4, 30))
        assert r["sla_breach"] is True

    def test_sla_no_breach(self):
        i = _issue(raised_date=date(2026, 4, 1), severity="HIGH", status="OPEN")
        r = IssueManagementEngine.sla_breach_check(i, date(2026, 4, 30))
        assert r["sla_breach"] is False

    def test_sla_breach_closed_late(self):
        i = _issue(raised_date=date(2026, 1, 1), severity="HIGH",
                   status="CLOSED", closed_date=date(2026, 4, 30))
        r = IssueManagementEngine.sla_breach_check(i, date(2026, 4, 30))
        assert r["sla_breach"] is True

    def test_escalation_critical_30days(self):
        i = _issue(raised_date=date(2026, 3, 31), severity="CRITICAL", status="OPEN")
        r = IssueManagementEngine.escalation_required(i, date(2026, 4, 30))
        assert r["escalation_required"] is True
        assert r["escalation_target"] == "BOARD_AUDIT_COMMITTEE"

    def test_escalation_not_required(self):
        i = _issue(raised_date=date(2026, 4, 25), severity="CRITICAL", status="OPEN")
        r = IssueManagementEngine.escalation_required(i, date(2026, 4, 30))
        assert r["escalation_required"] is False

    def test_escalation_skipped_for_closed(self):
        i = _issue(raised_date=date(2026, 1, 1), severity="CRITICAL",
                   status="CLOSED", closed_date=date(2026, 2, 1))
        r = IssueManagementEngine.escalation_required(i, date(2026, 4, 30))
        assert r["escalation_required"] is False

    def test_kri_summary_basic(self):
        issues = [
            _issue(issue_id="I1", severity="HIGH", status="OPEN",
                   raised_date=date(2026, 4, 1)),
            _issue(issue_id="I2", severity="MEDIUM", status="CLOSED",
                   raised_date=date(2026, 3, 1), closed_date=date(2026, 3, 20)),
        ]
        r = IssueManagementEngine.kri_summary(issues, date(2026, 4, 30))
        assert r["closure_rate_pct"] == "50.00"

    def test_kri_summary_empty_rule1(self):
        r = IssueManagementEngine.kri_summary([], date(2026, 4, 30))
        assert r["closure_rate_pct"] is None

    def test_kri_cluster_escalation(self):
        issues = [
            _issue(issue_id=f"I{i}", business_unit="RETAIL",
                   raised_date=date(2025, 8, 1), severity="HIGH", status="OPEN")
            for i in range(6)
        ]
        r = IssueManagementEngine.kri_summary(issues, date(2026, 4, 30))
        assert len(r["cluster_escalations"]) == 1


# ============================================================================
# #84 Audit Reporting (18)
# ============================================================================

def _report(**kw):
    defaults = dict(
        report_id="R1", entity_audited="Branch Nairobi",
        audit_period_start=date(2026, 1, 1),
        audit_period_end=date(2026, 3, 31),
        opinion="UNQUALIFIED",
        sections_present=list(REQUIRED_REPORT_SECTIONS),
        issued_date=date(2026, 4, 15),
    )
    defaults.update(kw)
    return AuditReport(**defaults)


def _rec(**kw):
    defaults = dict(
        recommendation_id="REC1", report_id="R1",
        description="Test", raised_date=date(2026, 1, 1),
        is_open=True, severity="MEDIUM",
    )
    defaults.update(kw)
    return AuditRecommendation(**defaults)


class TestAuditReporting:

    def test_audit_opinions_byte_for_byte(self):
        for o in ("UNQUALIFIED", "QUALIFIED", "ADVERSE", "DISCLAIMER"):
            assert o in AUDIT_OPINIONS

    def test_required_sections_byte_for_byte(self):
        for s in ("EXECUTIVE_SUMMARY", "SCOPE_AND_OBJECTIVES", "METHODOLOGY",
                  "DETAILED_FINDINGS", "MANAGEMENT_RESPONSE", "RECOMMENDATIONS",
                  "OPINION", "APPENDICES"):
            assert s in REQUIRED_REPORT_SECTIONS

    def test_coverage_thresholds_byte_for_byte(self):
        assert COVERAGE_THRESHOLDS_PCT["EXCELLENT"] == Decimal("90")
        assert COVERAGE_THRESHOLDS_PCT["GOOD"] == Decimal("75")
        assert COVERAGE_THRESHOLDS_PCT["ADEQUATE"] == Decimal("60")

    def test_recommendation_aging_byte_for_byte(self):
        assert RECOMMENDATION_AGING_MONTHS["RECENT"] == (0, 6)
        assert RECOMMENDATION_AGING_MONTHS["AGED"] == (7, 12)
        assert RECOMMENDATION_AGING_MONTHS["PROLONGED"] == (13, 24)

    def test_coverage_ratings_byte_for_byte(self):
        for r in ("EXCELLENT", "GOOD", "ADEQUATE", "INADEQUATE"):
            assert r in COVERAGE_RATINGS

    def test_opinion_validation_clean(self):
        r = AuditReportingEngine.validate_audit_opinion(_report())
        assert r["valid"] is True

    def test_opinion_unknown(self):
        r = AuditReportingEngine.validate_audit_opinion(_report(opinion="WEIRD"))
        assert r["valid"] is False

    def test_opinion_missing_sections(self):
        r = AuditReportingEngine.validate_audit_opinion(
            _report(sections_present=["EXECUTIVE_SUMMARY"]))
        assert r["valid"] is False

    def test_opinion_missing_period(self):
        r = AuditReportingEngine.validate_audit_opinion(
            _report(audit_period_start=None))
        assert r["valid"] is False

    def test_coverage_excellent(self):
        r = AuditReportingEngine.audit_universe_coverage(100, 95)
        assert r["rating"] == "EXCELLENT"

    def test_coverage_good(self):
        r = AuditReportingEngine.audit_universe_coverage(100, 80)
        assert r["rating"] == "GOOD"

    def test_coverage_adequate(self):
        r = AuditReportingEngine.audit_universe_coverage(100, 65)
        assert r["rating"] == "ADEQUATE"

    def test_coverage_inadequate(self):
        r = AuditReportingEngine.audit_universe_coverage(100, 30)
        assert r["rating"] == "INADEQUATE"

    def test_coverage_zero_universe_rule1(self):
        r = AuditReportingEngine.audit_universe_coverage(0, 5)
        assert r["coverage_pct"] is None

    def test_recommendations_summary(self):
        recs = [
            _rec(recommendation_id="R1", raised_date=date(2026, 4, 1)),
            _rec(recommendation_id="R2", raised_date=date(2025, 9, 1)),
            _rec(recommendation_id="R3", raised_date=date(2024, 6, 1)),
            _rec(recommendation_id="R4", raised_date=date(2026, 1, 1),
                 is_open=False, closed_date=date(2026, 2, 1)),
        ]
        r = AuditReportingEngine.outstanding_recommendations_summary(recs, date(2026, 4, 30))
        assert r["open_count"] == 3

    def test_recommendations_excluded_rule6(self):
        recs = [_rec(raised_date=None)]
        r = AuditReportingEngine.outstanding_recommendations_summary(recs, date(2026, 4, 30))
        assert r["excluded_count"] == 1

    def test_dashboard_basic(self):
        reports = [_report(report_id=f"R{i}") for i in range(3)]
        recs = [_rec(recommendation_id=f"REC{i}", raised_date=date(2026, 1, 1))
                for i in range(5)]
        r = AuditReportingEngine.generate_audit_committee_dashboard(
            reports, recs, total_universe_count=10, ref_date=date(2026, 4, 30))
        assert r["valid_reports"] == 3

    def test_dashboard_invalid_reports_surfaced(self):
        reports = [_report(report_id="R1"),
                   _report(report_id="R2", opinion="WEIRD")]
        r = AuditReportingEngine.generate_audit_committee_dashboard(
            reports, [], total_universe_count=10, ref_date=date(2026, 4, 30))
        assert len(r["invalid_reports"]) == 1

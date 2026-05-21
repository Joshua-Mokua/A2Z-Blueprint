"""
================================================================================
A2Z MIS 360 — Volume Eleven Batch Tests (Standards #61-#64 HR Intelligence)
================================================================================

Tests Standards #61 Workforce Analytics, #62 Compensation & Pay Equity,
#63 Performance & Talent Pipeline, #64 Employee Engagement Intelligence.

Total: 49 unit tests covering deterministic workforce metrics, pay equity
       statistics, calibration distribution, and Rule 7 sentiment scaffolding.

Run via:
    pytest tests/test_volume_eleven_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.workforce_analytics import (
    WorkforceAnalyticsEngine, StaffRecord,
    EMPLOYMENT_STATUSES, TENURE_BUCKETS, AGE_BANDS,
    SPAN_OF_CONTROL_HEALTHY_MIN, SPAN_OF_CONTROL_HEALTHY_MAX, SPAN_OF_CONTROL_OVERLOADED,
    ATTRITION_LOW_PCT, ATTRITION_HEALTHY_MAX_PCT, ATTRITION_HIGH_PCT,
)
from utils.compensation_equity import (
    CompensationEquityEngine, CompensationRecord,
    PAY_GAP_FAIR_MAX_PCT, PAY_GAP_MODERATE_MAX_PCT,
    COMPA_RATIO_HEALTHY_MIN, COMPA_RATIO_HEALTHY_MAX,
    CEO_RATIO_HEALTHY_MAX, CEO_RATIO_HIGH_THRESHOLD,
)
from utils.performance_talent import (
    PerformanceTalentEngine, PerformanceReview, SuccessionPlan,
    RATING_LEVELS, CALIBRATION_TARGETS, READINESS_LEVELS,
    BENCH_HEALTHY_PCT, BENCH_AT_RISK_PCT,
    REVIEW_STATUS_DRAFT, REVIEW_STATUS_MANAGER_SUBMITTED,
    REVIEW_STATUS_CALIBRATED, REVIEW_STATUS_FINALIZED, REVIEW_STATUS_DISPUTED,
    ALLOWED_REVIEW_TRANSITIONS,
)
from utils.employee_engagement import (
    EmployeeEngagementEngine, SurveyResponse, StaffSignals,
    ENGAGEMENT_DRIVERS, FLIGHT_RISK_FACTOR_WEIGHTS,
    FLIGHT_RISK_HIGH_THRESHOLD, FLIGHT_RISK_MEDIUM_THRESHOLD,
    POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS,
    SPEC_DEVIATION_NOTE as ENG_SPEC_DEVIATION_NOTE,
)


# ============================================================================
# #61 Workforce Analytics (11)
# ============================================================================

def _staff(**kw):
    defaults = dict(
        staff_id="S1", branch_code="B1", role="TELLER", grade="G3",
        employment_status="ACTIVE", hire_date="2020-01-01",
    )
    defaults.update(kw)
    return StaffRecord(**defaults)


class TestWorkforceAnalytics:

    def test_employment_statuses_byte_for_byte(self):
        for s in ("ACTIVE", "ON_LEAVE", "TERMINATED", "RESIGNED", "RETIRED"):
            assert s in EMPLOYMENT_STATUSES

    def test_span_thresholds(self):
        assert SPAN_OF_CONTROL_HEALTHY_MIN == 4
        assert SPAN_OF_CONTROL_HEALTHY_MAX == 12
        assert SPAN_OF_CONTROL_OVERLOADED == 15

    def test_attrition_thresholds(self):
        assert ATTRITION_LOW_PCT == 5.0
        assert ATTRITION_HEALTHY_MAX_PCT == 12.0
        assert ATTRITION_HIGH_PCT == 20.0

    def test_headcount_basic(self):
        staff = [_staff(staff_id="S1", branch_code="B1"), _staff(staff_id="S2", branch_code="B2")]
        r = WorkforceAnalyticsEngine.headcount_by_dimension(staff, "2026-01-01", ["branch_code"])
        assert r["total_active_headcount"] == 2

    def test_attrition_zero_opening_rule1(self):
        r = WorkforceAnalyticsEngine.attrition_rate([], "2025-01-01", "2025-12-31")
        assert r["rate_pct"] is None

    def test_span_of_control_overloaded(self):
        staff = [_staff(staff_id="M1")]
        for i in range(20):
            staff.append(_staff(staff_id=f"R{i}", manager_id="M1"))
        r = WorkforceAnalyticsEngine.span_of_control(staff)
        assert r["overloaded_count"] == 1

    def test_tenure_buckets_byte_for_byte(self):
        labels = [b[0] for b in TENURE_BUCKETS]
        for l in ("UNDER_1Y", "1_3Y", "3_5Y", "5_10Y", "OVER_10Y"):
            assert l in labels

    def test_demographic_unknown_rule6(self):
        staff = [_staff(staff_id="S1", gender=None)]
        r = WorkforceAnalyticsEngine.demographic_mix(staff, "2026-01-01")
        assert r["gender_distribution"]["UNKNOWN"] == 1

    def test_invalid_date_handled(self):
        r = WorkforceAnalyticsEngine.headcount_by_dimension([], "BAD", ["branch_code"])
        assert "error" in r

    def test_headcount_unknown_dimension(self):
        r = WorkforceAnalyticsEngine.headcount_by_dimension([], "2026-01-01", ["weird"])
        assert "error" in r

    def test_attrition_severity_high(self):
        staff = [_staff(staff_id=f"S{i}", hire_date="2024-01-01") for i in range(4)]
        staff[0].termination_date = "2025-06-01"
        r = WorkforceAnalyticsEngine.attrition_rate(staff, "2025-01-01", "2025-12-31")
        assert r["severity"] == "HIGH"


# ============================================================================
# #62 Compensation & Pay Equity (10)
# ============================================================================

def _comp(**kw):
    defaults = dict(
        staff_id="S1", base_salary_kes=Decimal("100000"), grade="G3",
        role="TELLER", branch_code="B1", gender="M",
        grade_midpoint_kes=Decimal("100000"),
    )
    defaults.update(kw)
    return CompensationRecord(**defaults)


class TestCompensationEquity:

    def test_pay_gap_thresholds(self):
        assert PAY_GAP_FAIR_MAX_PCT == 5.0
        assert PAY_GAP_MODERATE_MAX_PCT == 10.0

    def test_compa_ratio_band_byte_for_byte(self):
        assert COMPA_RATIO_HEALTHY_MIN == 0.80
        assert COMPA_RATIO_HEALTHY_MAX == 1.20

    def test_distribution_basic(self):
        recs = [
            _comp(staff_id=f"S{i}", base_salary_kes=Decimal(str(100000 + i * 50000)), grade="G3")
            for i in range(3)
        ]
        r = CompensationEquityEngine.pay_distribution_by_grade(recs, "G3")
        assert r["headcount"] == 3
        assert r["median"] == "150000"

    def test_distribution_no_records_rule1(self):
        r = CompensationEquityEngine.pay_distribution_by_grade([], "G3")
        assert r["median"] is None

    def test_pay_gap_basic(self):
        recs = [
            _comp(staff_id="M1", gender="M", base_salary_kes=Decimal("100000")),
            _comp(staff_id="F1", gender="F", base_salary_kes=Decimal("90000")),
        ]
        r = CompensationEquityEngine.gender_pay_gap(recs)
        assert r["raw_gap_pct"] == 10.0

    def test_pay_gap_no_male_rule1(self):
        recs = [_comp(gender="F")]
        r = CompensationEquityEngine.gender_pay_gap(recs)
        assert r["raw_gap_pct"] is None

    def test_unknown_gender_rule6(self):
        recs = [_comp(staff_id="S1", gender=None), _comp(staff_id="S2", gender="M")]
        r = CompensationEquityEngine.gender_pay_gap(recs)
        assert r["unknown_gender_count"] == 1

    def test_compa_ratio_band_classification(self):
        recs = [
            _comp(staff_id="S1", base_salary_kes=Decimal("70000"), grade_midpoint_kes=Decimal("100000")),
            _comp(staff_id="S2", base_salary_kes=Decimal("100000"), grade_midpoint_kes=Decimal("100000")),
            _comp(staff_id="S3", base_salary_kes=Decimal("130000"), grade_midpoint_kes=Decimal("100000")),
        ]
        r = CompensationEquityEngine.internal_equity_ratios(recs)
        assert r["below_band_count"] == 1
        assert r["in_band_count"] == 1
        assert r["above_band_count"] == 1

    def test_ceo_ratio_high(self):
        recs = [
            _comp(staff_id="CEO", base_salary_kes=Decimal("12000000")),
            _comp(staff_id="S1", base_salary_kes=Decimal("100000")),
            _comp(staff_id="S2", base_salary_kes=Decimal("100000")),
        ]
        r = CompensationEquityEngine.ceo_to_median_ratio(recs, "CEO")
        assert r["ratio"] == 120.0
        assert r["severity"] == "HIGH"

    def test_ceo_not_found(self):
        r = CompensationEquityEngine.ceo_to_median_ratio([], "MISSING")
        assert r["ratio"] is None


# ============================================================================
# #63 Performance & Talent (12)
# ============================================================================

def _review(**kw):
    defaults = dict(
        review_id="R1", staff_id="S1", period="2025_H2", rating="MEETS",
        manager_id="M1",
    )
    defaults.update(kw)
    return PerformanceReview(**defaults)


class TestPerformanceTalent:

    def test_rating_levels_byte_for_byte(self):
        for level in ("EXCEEDS", "MEETS_PLUS", "MEETS", "DEVELOPING", "UNSATISFACTORY"):
            assert level in RATING_LEVELS

    def test_calibration_targets_byte_for_byte(self):
        assert CALIBRATION_TARGETS["EXCEEDS"] == (10.0, 15.0)
        assert CALIBRATION_TARGETS["MEETS"] == (50.0, 55.0)
        assert CALIBRATION_TARGETS["UNSATISFACTORY"] == (0.0, 5.0)

    def test_distribution_empty_rule1(self):
        r = PerformanceTalentEngine.rating_distribution([], "2025_H2")
        assert r["distribution"]["EXCEEDS"]["pct"] is None

    def test_unrated_surfaced_rule6(self):
        revs = [_review(rating=None)]
        r = PerformanceTalentEngine.rating_distribution(revs, "2025_H2")
        assert r["total_unrated"] == 1

    def test_calibration_inflation_caught(self):
        revs = [_review(review_id=f"R{i}", staff_id=f"S{i}", rating="EXCEEDS", manager_id="M1") for i in range(5)]
        r = PerformanceTalentEngine.calibration_compliance_by_manager(revs, "2025_H2")
        assert r["managers_with_calibration_issues"] == 1

    def test_succession_no_critical_rule1(self):
        r = PerformanceTalentEngine.succession_bench_strength([])
        assert r["bench_strength_pct"] is None

    def test_review_workflow_skip_rejected(self):
        rev = _review()
        ok, _ = PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_FINALIZED, "M1")
        assert not ok

    def test_review_workflow_normal_path(self):
        rev = _review()
        assert PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_MANAGER_SUBMITTED, "M1")[0]
        assert PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_CALIBRATED, "HR1")[0]

    def test_finalized_terminal_rule4(self):
        rev = _review(review_status=REVIEW_STATUS_FINALIZED)
        ok, _ = PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_DRAFT, "M1")
        assert not ok

    def test_actor_id_required(self):
        rev = _review()
        ok, _ = PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_MANAGER_SUBMITTED, "")
        assert not ok

    def test_hipo_pipeline(self):
        revs = [
            _review(review_id="R1", staff_id="S1", period="2024_H1", rating="EXCEEDS"),
            _review(review_id="R2", staff_id="S1", period="2024_H2", rating="EXCEEDS"),
        ]
        r = PerformanceTalentEngine.high_potential_pipeline(revs, periods_required=2)
        assert "S1" in r["hipo_staff_ids"]

    def test_hipo_insufficient_history_rule6(self):
        revs = [_review(review_id="R1", staff_id="S1", period="2024_H1", rating="EXCEEDS")]
        r = PerformanceTalentEngine.high_potential_pipeline(revs, periods_required=2)
        assert r["insufficient_history_count"] == 1


# ============================================================================
# #64 Employee Engagement (16)
# ============================================================================

def _resp(**kw):
    defaults = dict(
        response_id="R1", staff_id="S1", survey_period="2025_Q4",
        overall_likert=4, enps_score=8,
    )
    defaults.update(kw)
    return SurveyResponse(**defaults)


class TestEmployeeEngagement:

    def test_engagement_drivers_byte_for_byte(self):
        for d in ("LEADERSHIP", "COMPENSATION", "GROWTH_DEVELOPMENT",
                  "WORK_LIFE_BALANCE", "RECOGNITION", "PURPOSE_MEANING"):
            assert d in ENGAGEMENT_DRIVERS

    def test_flight_risk_weights_byte_for_byte(self):
        assert FLIGHT_RISK_FACTOR_WEIGHTS["engagement_below_40"] == 30
        assert FLIGHT_RISK_FACTOR_WEIGHTS["compensation_below_p25"] == 25

    def test_engagement_score_basic(self):
        resps = [_resp(overall_likert=5), _resp(overall_likert=4), _resp(overall_likert=3)]
        r = EmployeeEngagementEngine.engagement_score(resps)
        assert r["score"] == 75.0

    def test_engagement_no_respondents_rule1(self):
        r = EmployeeEngagementEngine.engagement_score([])
        assert r["score"] is None

    def test_enps_basic(self):
        resps = [_resp(enps_score=10), _resp(enps_score=9), _resp(enps_score=7), _resp(enps_score=5)]
        r = EmployeeEngagementEngine.enps(resps)
        assert r["enps"] == 25.0

    def test_enps_no_respondents_rule1(self):
        r = EmployeeEngagementEngine.enps([])
        assert r["enps"] is None

    def test_drivers_breakdown_missing_rule6(self):
        resps = [_resp(driver_scores={"LEADERSHIP": 5})]
        r = EmployeeEngagementEngine.drivers_breakdown(resps)
        assert r["LEADERSHIP"]["respondents"] == 1
        assert r["COMPENSATION"]["score"] is None

    def test_sentiment_no_model_rule7(self):
        r = EmployeeEngagementEngine.sentiment_score("I love this great team")
        assert r["basis"] == "rule_based"
        assert r["ml_sentiment"] is None
        assert r["reason"] == "no_ml_sentiment_model_loaded"

    def test_sentiment_negative(self):
        r = EmployeeEngagementEngine.sentiment_score("This place is terrible toxic")
        assert r["rule_based_sentiment"] < 0

    def test_sentiment_neutral(self):
        r = EmployeeEngagementEngine.sentiment_score("just another day")
        assert r["rule_based_sentiment"] == 0

    def test_sentiment_ml_succeeds(self):
        r = EmployeeEngagementEngine.sentiment_score("hi", ml_sentiment_fn=lambda t: (0.5, {"ok": True}))
        assert r["basis"] == "ml"
        assert "rule_based_sentiment" in r

    def test_sentiment_ml_fails_rule7(self):
        def fail(t): raise ValueError("oops")
        r = EmployeeEngagementEngine.sentiment_score("hi", ml_sentiment_fn=fail)
        assert r["basis"] == "rule_based"
        assert "ml_sentiment_error" in r["reason"]

    def test_sentiment_determinism(self):
        r1 = EmployeeEngagementEngine.sentiment_score("I love this")
        r2 = EmployeeEngagementEngine.sentiment_score("I love this")
        assert r1["rule_based_sentiment"] == r2["rule_based_sentiment"]

    def test_flight_risk_high(self):
        s = StaffSignals(
            staff_id="S1", engagement_score=30, last_promotion_years_ago=4,
            compensation_percentile=20, last_two_ratings=["DEVELOPING", "UNSATISFACTORY"],
            tenure_years=3,
        )
        r = EmployeeEngagementEngine.flight_risk_indicators(s)
        assert r["score"] == 100
        assert r["severity"] == "HIGH"

    def test_flight_risk_missing_rule6(self):
        s = StaffSignals(staff_id="S1")
        r = EmployeeEngagementEngine.flight_risk_indicators(s)
        assert "engagement_score" in r["missing_signals"]

    def test_spec_deviation_byte_for_byte(self):
        expected = (
            "ML-based sentiment classification is downstream work; "
            "v6 ships rule-based keyword sentiment scoring"
        )
        assert ENG_SPEC_DEVIATION_NOTE == expected

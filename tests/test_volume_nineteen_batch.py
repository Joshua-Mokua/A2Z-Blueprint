"""
================================================================================
A2Z MIS 360 — Volume Nineteen Batch Tests (Standards #93-#96 Strategic & Network)
================================================================================

Tests Standards #93 Strategic Planning, #94 Branch Performance,
#95 Customer Lifetime Value, #96 Third-Party / Vendor Risk Management.

Total: 120 unit tests covering budget variance + 3 forecast methods +
       budget cycle state machine + reforecast triggers; branch P&L +
       quartile ranking + peer percentiles + lifecycle stages; CLV NPV +
       4-tier segment classification + tenure bands + activity status;
       vendor tier classification + 5 due-diligence checks + per-tier
       review cadence + 4-tier SLA breach severity + concentration alerts.

Run via:
    pytest tests/test_volume_nineteen_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:
    pytest = None  # type: ignore

from utils.strategic_planning import (
    StrategicPlanningEngine,
    BUDGET_LINE_CATEGORIES, VARIANCE_DIRECTIONS, VARIANCE_TIERS,
    GREEN_VARIANCE_THRESHOLD_PCT, AMBER_VARIANCE_THRESHOLD_PCT,
    FORECAST_METHODS, BUDGET_CYCLE_STATES, ALLOWED_BUDGET_TRANSITIONS,
    INCOME_LIKE_CATEGORIES, EXPENSE_LIKE_CATEGORIES,
    QUARTERLY_REFORECAST_MONTHS, DEVIATION_REFORECAST_PCT,
)
from utils.branch_performance import (
    BranchPerformanceEngine, BranchPnlInputs,
    BRANCH_PNL_LINES, PERFORMANCE_TIERS,
    TIER_1_THRESHOLD_PCT, TIER_2_THRESHOLD_PCT, TIER_3_THRESHOLD_PCT,
    BRANCH_LIFECYCLE_STAGES, LIFECYCLE_BANDS_YEARS,
    PEER_GROUP_LOCATIONS, PEER_GROUP_SIZES, BENCHMARK_PERCENTILES,
)
from utils.customer_value_segments import (
    CustomerValueEngine, ClvInputs,
    CUSTOMER_SEGMENTS, SEGMENT_TIERS, SEGMENT_TIER_BANDS_KES,
    TENURE_BANDS, TENURE_BAND_YEARS, ACTIVITY_STATUSES,
    DORMANT_THRESHOLD_DAYS, ATTRITED_THRESHOLD_DAYS,
    DEFAULT_DISCOUNT_RATE_PCT,
)
from utils.vendor_risk import (
    VendorRiskEngine, VendorRecord,
    VENDOR_CATEGORIES, VENDOR_TIERS, DUE_DILIGENCE_CHECKS,
    REVIEW_CADENCE_DAYS, SLA_BREACH_SEVERITIES,
    SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS,
    VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT,
    CONTRACT_RENEWAL_NOTICE_DAYS,
    CRITICAL_TIER_REQUIRED_CHECKS, LOWER_TIER_REQUIRED_CHECKS,
)


# ============================================================================
# #93 Strategic Planning (35)
# ============================================================================

class TestStrategicPlanning:

    def test_categories_byte_for_byte(self):
        for c in ("REVENUE", "OPEX", "NPAT", "CAPEX", "BALANCE_SHEET_GROWTH"):
            assert c in BUDGET_LINE_CATEGORIES
        assert len(BUDGET_LINE_CATEGORIES) == 5

    def test_directions_byte_for_byte(self):
        for d in ("FAVORABLE", "UNFAVORABLE", "NEUTRAL"):
            assert d in VARIANCE_DIRECTIONS

    def test_tiers_byte_for_byte(self):
        for t in ("GREEN", "AMBER", "RED"):
            assert t in VARIANCE_TIERS

    def test_thresholds_byte_for_byte(self):
        assert GREEN_VARIANCE_THRESHOLD_PCT == Decimal("5")
        assert AMBER_VARIANCE_THRESHOLD_PCT == Decimal("10")

    def test_methods_byte_for_byte(self):
        for m in ("STRAIGHT_LINE", "RUN_RATE", "SEASONALLY_ADJUSTED"):
            assert m in FORECAST_METHODS

    def test_states_byte_for_byte(self):
        for s in ("DRAFT", "REVIEW", "BOARD_APPROVED", "IN_EXECUTION", "CLOSED"):
            assert s in BUDGET_CYCLE_STATES
        assert len(BUDGET_CYCLE_STATES) == 5

    def test_transitions_byte_for_byte(self):
        assert ALLOWED_BUDGET_TRANSITIONS["DRAFT"] == ("REVIEW",)
        assert "BOARD_APPROVED" in ALLOWED_BUDGET_TRANSITIONS["REVIEW"]
        assert "DRAFT" in ALLOWED_BUDGET_TRANSITIONS["REVIEW"]
        assert ALLOWED_BUDGET_TRANSITIONS["BOARD_APPROVED"] == ("IN_EXECUTION",)
        assert ALLOWED_BUDGET_TRANSITIONS["CLOSED"] == ()

    def test_reforecast_constants_byte_for_byte(self):
        assert QUARTERLY_REFORECAST_MONTHS == 3
        assert DEVIATION_REFORECAST_PCT == Decimal("10")

    def test_revenue_favorable(self):
        r = StrategicPlanningEngine.variance("REVENUE", Decimal("100"), Decimal("110"))
        assert r["direction"] == "FAVORABLE"

    def test_revenue_unfavorable(self):
        r = StrategicPlanningEngine.variance("REVENUE", Decimal("100"), Decimal("90"))
        assert r["direction"] == "UNFAVORABLE"

    def test_opex_favorable_underspend(self):
        r = StrategicPlanningEngine.variance("OPEX", Decimal("100"), Decimal("90"))
        assert r["direction"] == "FAVORABLE"

    def test_opex_unfavorable_overspend(self):
        r = StrategicPlanningEngine.variance("OPEX", Decimal("100"), Decimal("110"))
        assert r["direction"] == "UNFAVORABLE"

    def test_capex_favorable_underspend(self):
        r = StrategicPlanningEngine.variance("CAPEX", Decimal("100"), Decimal("80"))
        assert r["direction"] == "FAVORABLE"

    def test_npat_favorable(self):
        r = StrategicPlanningEngine.variance("NPAT", Decimal("100"), Decimal("120"))
        assert r["direction"] == "FAVORABLE"

    def test_neutral_variance(self):
        r = StrategicPlanningEngine.variance("REVENUE", Decimal("100"), Decimal("100"))
        assert r["direction"] == "NEUTRAL"

    def test_zero_budget_rule1(self):
        r = StrategicPlanningEngine.variance("REVENUE", Decimal("0"), Decimal("100"))
        assert r["variance_pct"] is None

    def test_unknown_category_rule6(self):
        r = StrategicPlanningEngine.variance("WEIRD", Decimal("100"), Decimal("110"))
        assert r["computed"] is False

    def test_missing_inputs_rule1(self):
        r = StrategicPlanningEngine.variance("REVENUE", None, Decimal("100"))
        assert r["computed"] is False

    def test_tier_green(self):
        assert StrategicPlanningEngine.variance_tier(Decimal("3")) == "GREEN"
        assert StrategicPlanningEngine.variance_tier(Decimal("-3")) == "GREEN"

    def test_tier_amber(self):
        assert StrategicPlanningEngine.variance_tier(Decimal("7")) == "AMBER"
        assert StrategicPlanningEngine.variance_tier(Decimal("5")) == "AMBER"
        assert StrategicPlanningEngine.variance_tier(Decimal("10")) == "AMBER"

    def test_tier_red(self):
        assert StrategicPlanningEngine.variance_tier(Decimal("15")) == "RED"

    def test_tier_none_passes_through(self):
        assert StrategicPlanningEngine.variance_tier(None) is None

    def test_forecast_straight_line(self):
        r = StrategicPlanningEngine.forecast(
            "STRAIGHT_LINE", Decimal("50000000"), 6, 12)
        assert r["forecast"] == "100000000.00"

    def test_forecast_run_rate(self):
        r = StrategicPlanningEngine.forecast(
            "RUN_RATE", Decimal("30000000"), 6, 12,
            last_3mo_avg=Decimal("5000000"))
        assert r["forecast"] == "60000000.00"

    def test_forecast_seasonally_adjusted(self):
        r = StrategicPlanningEngine.forecast(
            "SEASONALLY_ADJUSTED", Decimal("50000000"), 6, 12,
            seasonal_indices=[Decimal("1")] * 12)
        assert r["forecast"] == "100000000.00"

    def test_forecast_unknown_method(self):
        r = StrategicPlanningEngine.forecast("WEIRD", Decimal("50000000"), 6, 12)
        assert r["computed"] is False

    def test_forecast_run_rate_missing_avg(self):
        r = StrategicPlanningEngine.forecast(
            "RUN_RATE", Decimal("30000000"), 6, 12, last_3mo_avg=None)
        assert r["computed"] is False

    def test_forecast_seasonal_missing_indices(self):
        r = StrategicPlanningEngine.forecast(
            "SEASONALLY_ADJUSTED", Decimal("50000000"), 6, 12)
        assert r["computed"] is False

    def test_forecast_invalid_months(self):
        r = StrategicPlanningEngine.forecast(
            "STRAIGHT_LINE", Decimal("50000000"), months_elapsed=13, total_months=12)
        assert r["computed"] is False

    def test_budget_transition_valid(self):
        r = StrategicPlanningEngine.validate_budget_state_transition("DRAFT", "REVIEW")
        assert r["allowed"] is True

    def test_budget_transition_invalid_skip(self):
        r = StrategicPlanningEngine.validate_budget_state_transition(
            "DRAFT", "BOARD_APPROVED")
        assert r["allowed"] is False

    def test_budget_terminal_no_exit(self):
        r = StrategicPlanningEngine.validate_budget_state_transition("CLOSED", "DRAFT")
        assert r["allowed"] is False

    def test_reforecast_quarterly_trigger(self):
        r = StrategicPlanningEngine.reforecast_trigger(3, Decimal("2"))
        assert "QUARTERLY_CADENCE" in r["triggers"]

    def test_reforecast_deviation_trigger(self):
        r = StrategicPlanningEngine.reforecast_trigger(1, Decimal("15"))
        assert "DEVIATION_THRESHOLD" in r["triggers"]

    def test_reforecast_no_trigger(self):
        r = StrategicPlanningEngine.reforecast_trigger(1, Decimal("3"))
        assert r["should_reforecast"] is False


# ============================================================================
# #94 Branch Performance (26)
# ============================================================================

class TestBranchPerformance:

    def test_pnl_lines_byte_for_byte(self):
        for l in ("NII", "NON_INTEREST_INCOME", "OPEX_DIRECT",
                  "OPEX_ALLOCATED", "IMPAIRMENT", "NPBT"):
            assert l in BRANCH_PNL_LINES
        assert len(BRANCH_PNL_LINES) == 6

    def test_tiers_byte_for_byte(self):
        for t in ("TIER_1", "TIER_2", "TIER_3", "TIER_4"):
            assert t in PERFORMANCE_TIERS
        assert len(PERFORMANCE_TIERS) == 4

    def test_thresholds_byte_for_byte(self):
        assert TIER_1_THRESHOLD_PCT == Decimal("75")
        assert TIER_2_THRESHOLD_PCT == Decimal("50")
        assert TIER_3_THRESHOLD_PCT == Decimal("25")

    def test_lifecycle_stages_byte_for_byte(self):
        for s in ("NEW", "GROWTH", "MATURE"):
            assert s in BRANCH_LIFECYCLE_STAGES

    def test_lifecycle_bands_byte_for_byte(self):
        assert LIFECYCLE_BANDS_YEARS["NEW"] == (0, 2)
        assert LIFECYCLE_BANDS_YEARS["GROWTH"] == (2, 5)
        assert LIFECYCLE_BANDS_YEARS["MATURE"] == (5, 999)

    def test_peer_locations_byte_for_byte(self):
        for l in ("TIER_1_CITIES", "TIER_2_CITIES", "RURAL"):
            assert l in PEER_GROUP_LOCATIONS

    def test_peer_sizes_byte_for_byte(self):
        for s in ("LARGE", "MEDIUM", "SMALL"):
            assert s in PEER_GROUP_SIZES

    def test_benchmark_percentiles_byte_for_byte(self):
        for p in ("PERCENTILE_25", "MEDIAN", "PERCENTILE_75"):
            assert p in BENCHMARK_PERCENTILES

    def test_branch_pnl_full(self):
        r = BranchPerformanceEngine.branch_pnl(BranchPnlInputs(
            branch_id="B1", nii=Decimal("100"),
            non_interest_income=Decimal("20"),
            opex_direct=Decimal("40"), opex_allocated=Decimal("20"),
            impairment=Decimal("10"),
        ))
        assert r["npbt"] == "50"

    def test_branch_pnl_missing_input_rule1(self):
        r = BranchPerformanceEngine.branch_pnl(BranchPnlInputs(
            branch_id="B1", nii=Decimal("100"),
            opex_direct=Decimal("40"), opex_allocated=Decimal("20"),
            impairment=Decimal("10"),
        ))
        assert r["computed"] is False

    def test_cost_income_ratio_basic(self):
        r = BranchPerformanceEngine.cost_income_ratio(Decimal("60"), Decimal("120"))
        assert r == Decimal("50")

    def test_cost_income_ratio_zero_income_rule1(self):
        r = BranchPerformanceEngine.cost_income_ratio(Decimal("60"), Decimal("0"))
        assert r is None

    def test_cost_income_ratio_missing_rule1(self):
        r = BranchPerformanceEngine.cost_income_ratio(None, Decimal("120"))
        assert r is None

    def test_roaa_basic(self):
        r = BranchPerformanceEngine.return_on_avg_assets(Decimal("50"), Decimal("1000"))
        assert r == Decimal("5")

    def test_roaa_zero_assets_rule1(self):
        r = BranchPerformanceEngine.return_on_avg_assets(Decimal("50"), Decimal("0"))
        assert r is None

    def test_quartile_top(self):
        r = BranchPerformanceEngine.quartile_rank(
            Decimal("100"),
            [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]])
        assert r["tier"] == "TIER_1"

    def test_quartile_middle(self):
        r = BranchPerformanceEngine.quartile_rank(
            Decimal("60"),
            [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]])
        assert r["tier"] == "TIER_2"

    def test_quartile_bottom(self):
        r = BranchPerformanceEngine.quartile_rank(
            Decimal("5"),
            [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 95]])
        assert r["tier"] == "TIER_4"

    def test_quartile_empty_peer_group_rule1(self):
        r = BranchPerformanceEngine.quartile_rank(Decimal("50"), [])
        assert r["tier"] is None

    def test_quartile_missing_branch_value(self):
        r = BranchPerformanceEngine.quartile_rank(None, [Decimal("50")])
        assert r["tier"] is None

    def test_peer_benchmark_metrics(self):
        r = BranchPerformanceEngine.peer_benchmark_metrics(
            [Decimal(str(x)) for x in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]])
        assert r["n"] == 10

    def test_peer_benchmark_empty_rule1(self):
        r = BranchPerformanceEngine.peer_benchmark_metrics([])
        assert r["median"] is None

    def test_lifecycle_new(self):
        assert BranchPerformanceEngine.lifecycle_stage(0) == "NEW"

    def test_lifecycle_growth(self):
        assert BranchPerformanceEngine.lifecycle_stage(2) == "GROWTH"

    def test_lifecycle_mature(self):
        assert BranchPerformanceEngine.lifecycle_stage(5) == "MATURE"

    def test_lifecycle_missing_rule1(self):
        assert BranchPerformanceEngine.lifecycle_stage(None) is None


# ============================================================================
# #95 Customer Value & Segments (32)
# ============================================================================

class TestCustomerValue:

    def test_segments_byte_for_byte(self):
        for s in ("MASS", "AFFLUENT", "HNW", "SME", "CORPORATE", "GOVERNMENT"):
            assert s in CUSTOMER_SEGMENTS
        assert len(CUSTOMER_SEGMENTS) == 6

    def test_segment_tiers_byte_for_byte(self):
        for t in ("PLATINUM", "GOLD", "SILVER", "BRONZE"):
            assert t in SEGMENT_TIERS
        assert len(SEGMENT_TIERS) == 4

    def test_segment_tier_bands_byte_for_byte(self):
        assert SEGMENT_TIER_BANDS_KES["PLATINUM"][0] == 1000000
        assert SEGMENT_TIER_BANDS_KES["GOLD"] == (250000, 999999)
        assert SEGMENT_TIER_BANDS_KES["SILVER"] == (50000, 249999)
        assert SEGMENT_TIER_BANDS_KES["BRONZE"] == (0, 49999)

    def test_tenure_bands_byte_for_byte(self):
        for b in ("NEW", "DEVELOPING", "ESTABLISHED", "LOYAL"):
            assert b in TENURE_BANDS
        assert TENURE_BAND_YEARS["NEW"] == (0, 1)
        assert TENURE_BAND_YEARS["LOYAL"] == (7, 999)

    def test_activity_statuses_byte_for_byte(self):
        for s in ("ACTIVE", "DORMANT", "ATTRITED"):
            assert s in ACTIVITY_STATUSES

    def test_thresholds_byte_for_byte(self):
        assert DORMANT_THRESHOLD_DAYS == 90
        assert ATTRITED_THRESHOLD_DAYS == 180

    def test_discount_rate_byte_for_byte(self):
        assert DEFAULT_DISCOUNT_RATE_PCT == Decimal("15")

    def test_clv_basic(self):
        r = CustomerValueEngine.clv(ClvInputs(
            customer_id="C1", annual_contribution_kes=Decimal("100000"),
            expected_tenure_years=1, retention_rate_pct=Decimal("100"),
            discount_rate_pct=Decimal("0")))
        assert r["clv_kes"] == "100000.00"

    def test_clv_with_retention_and_discount(self):
        r = CustomerValueEngine.clv(ClvInputs(
            customer_id="C2", annual_contribution_kes=Decimal("100000"),
            expected_tenure_years=3, retention_rate_pct=Decimal("80"),
            discount_rate_pct=Decimal("10")))
        clv = Decimal(r["clv_kes"])
        assert clv > Decimal("220000") and clv < Decimal("230000")

    def test_clv_zero_contribution_rule1(self):
        r = CustomerValueEngine.clv(ClvInputs(
            customer_id="C1", annual_contribution_kes=Decimal("0"),
            expected_tenure_years=5, retention_rate_pct=Decimal("90")))
        assert r["clv_kes"] is None

    def test_clv_zero_tenure_rule1(self):
        r = CustomerValueEngine.clv(ClvInputs(
            customer_id="C1", annual_contribution_kes=Decimal("100000"),
            expected_tenure_years=0, retention_rate_pct=Decimal("90")))
        assert r["clv_kes"] is None

    def test_clv_default_discount_rate_used(self):
        r = CustomerValueEngine.clv(ClvInputs(
            customer_id="C1", annual_contribution_kes=Decimal("100000"),
            expected_tenure_years=2, retention_rate_pct=Decimal("90")))
        assert r["discount_rate_pct"] == "15"

    def test_segment_platinum(self):
        assert CustomerValueEngine.segment_classification(Decimal("1500000")) == "PLATINUM"

    def test_segment_gold(self):
        assert CustomerValueEngine.segment_classification(Decimal("500000")) == "GOLD"

    def test_segment_silver(self):
        assert CustomerValueEngine.segment_classification(Decimal("100000")) == "SILVER"

    def test_segment_bronze(self):
        assert CustomerValueEngine.segment_classification(Decimal("10000")) == "BRONZE"

    def test_segment_boundary_platinum(self):
        assert CustomerValueEngine.segment_classification(Decimal("1000000")) == "PLATINUM"

    def test_segment_missing_rule1(self):
        assert CustomerValueEngine.segment_classification(None) is None

    def test_tenure_new(self):
        assert CustomerValueEngine.tenure_band(0.5) == "NEW"

    def test_tenure_developing(self):
        assert CustomerValueEngine.tenure_band(2.0) == "DEVELOPING"

    def test_tenure_established(self):
        assert CustomerValueEngine.tenure_band(5.0) == "ESTABLISHED"

    def test_tenure_loyal(self):
        assert CustomerValueEngine.tenure_band(10.0) == "LOYAL"

    def test_tenure_missing_rule1(self):
        assert CustomerValueEngine.tenure_band(None) is None

    def test_activity_active(self):
        assert CustomerValueEngine.activity_status(30) == "ACTIVE"

    def test_activity_dormant(self):
        assert CustomerValueEngine.activity_status(120) == "DORMANT"

    def test_activity_attrited(self):
        assert CustomerValueEngine.activity_status(200) == "ATTRITED"

    def test_activity_boundary_dormant(self):
        assert CustomerValueEngine.activity_status(90) == "DORMANT"

    def test_activity_boundary_attrited(self):
        assert CustomerValueEngine.activity_status(180) == "ATTRITED"

    def test_activity_missing_rule1(self):
        assert CustomerValueEngine.activity_status(None) is None

    def test_segment_aggregate_basic(self):
        customers = [
            {"customer_id": "C1", "segment": "MASS",
             "annual_contribution_kes": 50000},
            {"customer_id": "C2", "segment": "MASS",
             "annual_contribution_kes": 100000},
        ]
        r = CustomerValueEngine.segment_profitability_aggregate(customers, "MASS")
        assert r["n"] == 2
        assert r["avg_contribution_kes"] == "75000.00"

    def test_segment_aggregate_empty_rule1(self):
        r = CustomerValueEngine.segment_profitability_aggregate([], "MASS")
        assert r["avg_contribution_kes"] is None

    def test_segment_aggregate_unknown_rule6(self):
        r = CustomerValueEngine.segment_profitability_aggregate([], "WEIRD")
        assert r["computed"] is False


# ============================================================================
# #96 Vendor Risk (27)
# ============================================================================

class TestVendorRisk:

    def test_categories_byte_for_byte(self):
        for c in ("CRITICAL_TECH", "NON_CRITICAL_TECH", "FACILITIES",
                  "PROFESSIONAL_SERVICES", "OUTSOURCED_OPS"):
            assert c in VENDOR_CATEGORIES
        assert len(VENDOR_CATEGORIES) == 5

    def test_tiers_byte_for_byte(self):
        for t in ("TIER_1_CRITICAL", "TIER_2_HIGH", "TIER_3_MEDIUM", "TIER_4_LOW"):
            assert t in VENDOR_TIERS
        assert len(VENDOR_TIERS) == 4

    def test_dd_checks_byte_for_byte(self):
        for c in ("FINANCIAL_HEALTH", "INFOSEC_CERT", "BUSINESS_CONTINUITY",
                  "REGULATORY_COMPLIANCE", "GEOGRAPHIC_RISK"):
            assert c in DUE_DILIGENCE_CHECKS
        assert len(DUE_DILIGENCE_CHECKS) == 5

    def test_review_cadence_byte_for_byte(self):
        assert REVIEW_CADENCE_DAYS["TIER_1_CRITICAL"] == 365
        assert REVIEW_CADENCE_DAYS["TIER_2_HIGH"] == 730
        assert REVIEW_CADENCE_DAYS["TIER_3_MEDIUM"] == 1095
        assert REVIEW_CADENCE_DAYS["TIER_4_LOW"] == 1825

    def test_sla_severities_byte_for_byte(self):
        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            assert s in SLA_BREACH_SEVERITIES

    def test_sla_thresholds_byte_for_byte(self):
        assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["CRITICAL"] == 4
        assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["HIGH"] == 2
        assert SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS["MEDIUM"] == 1

    def test_concentration_threshold_byte_for_byte(self):
        assert VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT == Decimal("25")

    def test_renewal_notice_byte_for_byte(self):
        assert CONTRACT_RENEWAL_NOTICE_DAYS == 180

    def test_dd_complete_tier1_all_5(self):
        v = VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL",
                         completed_dd_checks=list(DUE_DILIGENCE_CHECKS))
        r = VendorRiskEngine.due_diligence_completeness(v)
        assert r["complete"] is True

    def test_dd_incomplete_tier1_missing_one(self):
        v = VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL",
                         completed_dd_checks=["FINANCIAL_HEALTH", "INFOSEC_CERT",
                                              "BUSINESS_CONTINUITY",
                                              "REGULATORY_COMPLIANCE"])
        r = VendorRiskEngine.due_diligence_completeness(v)
        assert r["complete"] is False
        assert r["eligible_for_onboarding"] is False

    def test_dd_tier3_only_2_required(self):
        v = VendorRecord(vendor_id="V1", category="PROFESSIONAL_SERVICES",
                         tier="TIER_3_MEDIUM",
                         completed_dd_checks=["FINANCIAL_HEALTH",
                                              "REGULATORY_COMPLIANCE"])
        r = VendorRiskEngine.due_diligence_completeness(v)
        assert r["complete"] is True

    def test_dd_unknown_tier_rule6(self):
        v = VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="WEIRD",
                         completed_dd_checks=list(DUE_DILIGENCE_CHECKS))
        r = VendorRiskEngine.due_diligence_completeness(v)
        assert r["complete"] is False

    def test_review_due_on_track(self):
        v = VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL", last_review_date=date(2026, 4, 1))
        r = VendorRiskEngine.review_due(v, as_of=date(2026, 5, 1))
        assert r["review_due_in_days"] == 335
        assert r["is_overdue"] is False

    def test_review_overdue(self):
        v = VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL", last_review_date=date(2025, 3, 25))
        r = VendorRiskEngine.review_due(v, as_of=date(2026, 4, 30))
        assert r["is_overdue"] is True

    def test_review_missing_last_date_rule1(self):
        v = VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL", last_review_date=None)
        r = VendorRiskEngine.review_due(v)
        assert r["review_due_in_days"] is None

    def test_sla_critical(self):
        assert VendorRiskEngine.sla_breach_severity(Decimal("6")) == "CRITICAL"

    def test_sla_critical_boundary(self):
        assert VendorRiskEngine.sla_breach_severity(Decimal("4")) == "CRITICAL"

    def test_sla_high(self):
        assert VendorRiskEngine.sla_breach_severity(Decimal("3")) == "HIGH"

    def test_sla_medium(self):
        assert VendorRiskEngine.sla_breach_severity(Decimal("1.5")) == "MEDIUM"

    def test_sla_low(self):
        assert VendorRiskEngine.sla_breach_severity(Decimal("0.5")) == "LOW"

    def test_sla_missing_rule1(self):
        assert VendorRiskEngine.sla_breach_severity(None) is None

    def test_concentration_alert_triggered(self):
        vendors = [
            VendorRecord(vendor_id="V1", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL",
                         annual_spend_kes=Decimal("800000")),
            VendorRecord(vendor_id="V2", category="CRITICAL_TECH",
                         tier="TIER_2_HIGH",
                         annual_spend_kes=Decimal("100000")),
            VendorRecord(vendor_id="V3", category="CRITICAL_TECH",
                         tier="TIER_3_MEDIUM",
                         annual_spend_kes=Decimal("100000")),
        ]
        r = VendorRiskEngine.vendor_concentration_check(vendors, "CRITICAL_TECH")
        assert Decimal(r["max_concentration_pct"]) == Decimal("80.00")
        assert r["concentration_alert"] is True

    def test_concentration_no_alert(self):
        vendors = [
            VendorRecord(vendor_id=f"V{i}", category="CRITICAL_TECH",
                         tier="TIER_1_CRITICAL",
                         annual_spend_kes=Decimal("250000"))
            for i in range(1, 5)
        ]
        r = VendorRiskEngine.vendor_concentration_check(vendors, "CRITICAL_TECH")
        assert r["concentration_alert"] is False

    def test_concentration_empty_category(self):
        r = VendorRiskEngine.vendor_concentration_check([], "CRITICAL_TECH")
        assert r["vendor_count"] == 0

    def test_concentration_unknown_category_rule6(self):
        r = VendorRiskEngine.vendor_concentration_check([], "WEIRD")
        assert r["computed"] is False

    def test_critical_tier_required_checks(self):
        assert len(CRITICAL_TIER_REQUIRED_CHECKS) == 5

    def test_lower_tier_required_checks(self):
        assert len(LOWER_TIER_REQUIRED_CHECKS) == 2

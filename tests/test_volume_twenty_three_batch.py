"""
================================================================================
A2Z MIS 360 — Volume Twenty-Three Batch Tests (Standards #109-#112)
================================================================================

Tests Standards #109 IAS 37 Provisions, #110 IFRS 7 Disclosures,
#111 IAS 1 Presentation, #112 IAS 8 Policies/Estimates/Errors.

Total: 130 unit tests covering: 4 probability levels (95%/51%/5%) with asymmetric
liability vs asset treatment; IFRS 7 5 maturity buckets + concentration thresholds
(10%/25%) + market sensitivity + hedge disclosure packs; IAS 1 5 statement
components + going concern + current/non-current classification + OCI recycling
map (5 line items: 2 recyclable, 3 never recycled); IAS 8 3 change types with
distinct application methods + 5-level policy hierarchy + error materiality
(5% profit, 1% equity dual test).

Run via:
    pytest tests/test_volume_twenty_three_batch.py -v
================================================================================
"""

from __future__ import annotations

from decimal import Decimal

from utils.provisions import (
    ProvisionsEngine,
    PROBABILITY_LEVELS, RECOGNITION_OUTCOMES, PROVISION_TYPES,
    PROVISION_RECOGNITION_CRITERIA, EXPECTED_VALUE_METHODS,
    VIRTUALLY_CERTAIN_PCT_MIN, PROBABLE_PCT_MIN, POSSIBLE_PCT_MIN,
)
from utils.ifrs7_disclosures import (
    IFRS7DisclosureEngine,
    DISCLOSURE_CATEGORIES, RISK_TYPES, MATURITY_BUCKETS,
    MARKET_RISK_VARIABLES, HEDGE_TYPES, CREDIT_QUALITY_BANDS,
    SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD,
    INDUSTRY_CONCENTRATION_PCT_THRESHOLD,
)
from utils.ias1_presentation import (
    IAS1PresentationEngine,
    COMPLETE_STATEMENTS_COMPONENTS, GOING_CONCERN_OUTCOMES,
    STATEMENT_FORMATS, CURRENT_ASSET_CRITERIA, CURRENT_LIABILITY_CRITERIA,
    OCI_CLASSIFICATIONS, OCI_LINE_ITEMS, OCI_RECYCLING_MAP,
    MATERIALITY_PCT_OF_REVENUE, MATERIALITY_PCT_OF_TOTAL_ASSETS,
    MATERIALITY_PCT_OF_EQUITY,
)
from utils.ias8_policies import (
    IAS8PoliciesEngine,
    CHANGE_TYPES, APPLICATION_METHODS, POLICY_HIERARCHY_LEVELS,
    POLICY_CHANGE_TRIGGERS, ERROR_PRESENTATION_OUTCOMES,
    ESTIMATE_CHANGE_REASONS,
    PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT,
    PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY,
)


# ============================================================================
# #109 IAS 37 Provisions (33)
# ============================================================================

class TestProvisions:

    def test_probability_levels_byte_for_byte(self):
        for p in ("VIRTUALLY_CERTAIN", "PROBABLE", "POSSIBLE", "REMOTE"):
            assert p in PROBABILITY_LEVELS
        assert len(PROBABILITY_LEVELS) == 4

    def test_recognition_outcomes_byte_for_byte(self):
        for o in ("RECOGNISE", "DISCLOSE", "NEITHER"):
            assert o in RECOGNITION_OUTCOMES

    def test_provision_types_byte_for_byte(self):
        for t in ("LEGAL_OBLIGATION", "CONSTRUCTIVE_OBLIGATION", "ONEROUS_CONTRACT"):
            assert t in PROVISION_TYPES

    def test_recognition_criteria_byte_for_byte(self):
        for c in ("PRESENT_OBLIGATION_FROM_PAST_EVENT", "OUTFLOW_PROBABLE",
                  "RELIABLE_ESTIMATE_POSSIBLE", "SETTLEMENT_DATE_UNCERTAIN",
                  "AMOUNT_UNCERTAIN"):
            assert c in PROVISION_RECOGNITION_CRITERIA
        assert len(PROVISION_RECOGNITION_CRITERIA) == 5

    def test_expected_value_methods_byte_for_byte(self):
        for m in ("SINGLE_OBLIGATION", "LARGE_POPULATION", "CONTINUOUS_RANGE"):
            assert m in EXPECTED_VALUE_METHODS

    def test_thresholds_byte_for_byte(self):
        assert VIRTUALLY_CERTAIN_PCT_MIN == Decimal("95")
        assert PROBABLE_PCT_MIN == Decimal("51")
        assert POSSIBLE_PCT_MIN == Decimal("5")

    def test_classification_virtually_certain(self):
        assert ProvisionsEngine.probability_classification(Decimal("95")) == "VIRTUALLY_CERTAIN"

    def test_classification_probable(self):
        assert ProvisionsEngine.probability_classification(Decimal("51")) == "PROBABLE"

    def test_classification_50pct_is_possible(self):
        """50% NOT probable; PROBABLE requires ≥51%."""
        assert ProvisionsEngine.probability_classification(Decimal("50")) == "POSSIBLE"

    def test_classification_possible(self):
        assert ProvisionsEngine.probability_classification(Decimal("25")) == "POSSIBLE"

    def test_classification_remote(self):
        assert ProvisionsEngine.probability_classification(Decimal("3")) == "REMOTE"

    def test_classification_5pct_boundary(self):
        """5% boundary → POSSIBLE (≥ inclusive)."""
        assert ProvisionsEngine.probability_classification(Decimal("5")) == "POSSIBLE"

    def test_classification_missing_rule1(self):
        assert ProvisionsEngine.probability_classification(None) is None

    def test_classification_over_100_rule6(self):
        assert ProvisionsEngine.probability_classification(Decimal("150")) is None

    def test_liability_recognise_when_probable_and_estimable(self):
        r = ProvisionsEngine.liability_treatment(Decimal("75"), reliable_estimate=True)
        assert r["treatment"] == "RECOGNISE"

    def test_liability_disclose_when_no_estimate(self):
        r = ProvisionsEngine.liability_treatment(Decimal("75"), reliable_estimate=False)
        assert r["treatment"] == "DISCLOSE"

    def test_liability_possible_disclose(self):
        r = ProvisionsEngine.liability_treatment(Decimal("30"))
        assert r["treatment"] == "DISCLOSE"

    def test_liability_remote_neither(self):
        r = ProvisionsEngine.liability_treatment(Decimal("3"))
        assert r["treatment"] == "NEITHER"

    def test_asset_virtually_certain_recognise(self):
        r = ProvisionsEngine.asset_treatment(Decimal("95"))
        assert r["treatment"] == "RECOGNISE"

    def test_asset_probable_disclose(self):
        """75% probable asset → DISCLOSE only (asymmetric vs liability)."""
        r = ProvisionsEngine.asset_treatment(Decimal("75"))
        assert r["treatment"] == "DISCLOSE"

    def test_asset_possible_neither_asymmetric(self):
        """30% possible asset → NEITHER (vs liability which would DISCLOSE)."""
        r = ProvisionsEngine.asset_treatment(Decimal("30"))
        assert r["treatment"] == "NEITHER"

    def test_asset_remote_neither(self):
        r = ProvisionsEngine.asset_treatment(Decimal("3"))
        assert r["treatment"] == "NEITHER"

    def test_measurement_single_obligation(self):
        r = ProvisionsEngine.provision_measurement(
            "SINGLE_OBLIGATION", amount=Decimal("100000"))
        assert r["measurement"] == "100000.00"

    def test_measurement_large_population_expected_value(self):
        """30% × 1M + 70% × 200K = 440K."""
        r = ProvisionsEngine.provision_measurement(
            "LARGE_POPULATION",
            probability_weighted_outcomes=[
                (Decimal("30"), Decimal("1000000")),
                (Decimal("70"), Decimal("200000")),
            ])
        assert r["measurement"] == "440000.00"

    def test_measurement_continuous_range_midpoint(self):
        """Midpoint of 100K-200K = 150K."""
        r = ProvisionsEngine.provision_measurement(
            "CONTINUOUS_RANGE",
            range_low=Decimal("100000"), range_high=Decimal("200000"))
        assert r["measurement"] == "150000.00"

    def test_measurement_unknown_method_rule6(self):
        r = ProvisionsEngine.provision_measurement("WEIRD")
        assert r["computed"] is False

    def test_measurement_inverted_range_rule6(self):
        r = ProvisionsEngine.provision_measurement(
            "CONTINUOUS_RANGE",
            range_low=Decimal("200000"), range_high=Decimal("100000"))
        assert r["computed"] is False

    def test_onerous_contract_loss(self):
        r = ProvisionsEngine.onerous_contract_test(
            Decimal("500000"), Decimal("300000"))
        assert r["onerous"] is True
        assert r["provision"] == "200000.00"

    def test_onerous_not_onerous(self):
        r = ProvisionsEngine.onerous_contract_test(
            Decimal("300000"), Decimal("500000"))
        assert r["onerous"] is False

    def test_onerous_missing_rule1(self):
        r = ProvisionsEngine.onerous_contract_test(None, Decimal("500000"))
        assert r["onerous"] is None

    def test_reimbursement_certain(self):
        r = ProvisionsEngine.reimbursement_treatment(
            True, reimbursement_amount=Decimal("100000"))
        assert r["recognise_asset"] is True

    def test_reimbursement_not_certain(self):
        r = ProvisionsEngine.reimbursement_treatment(False)
        assert r["recognise_asset"] is False

    def test_reimbursement_missing_rule1(self):
        r = ProvisionsEngine.reimbursement_treatment(None)
        assert r["recognise_asset"] is None


# ============================================================================
# #110 IFRS 7 Disclosures (33)
# ============================================================================

class TestIFRS7Disclosures:

    def test_disclosure_categories_byte_for_byte(self):
        for c in ("SIGNIFICANCE_TO_FINANCIAL_POSITION",
                  "NATURE_AND_EXTENT_OF_RISKS",
                  "QUANTITATIVE_RISK_DATA"):
            assert c in DISCLOSURE_CATEGORIES
        assert len(DISCLOSURE_CATEGORIES) == 3

    def test_risk_types_byte_for_byte(self):
        for r in ("CREDIT_RISK", "LIQUIDITY_RISK", "MARKET_RISK"):
            assert r in RISK_TYPES

    def test_maturity_buckets_byte_for_byte(self):
        for b in ("ON_DEMAND", "UP_TO_3_MONTHS", "THREE_TO_12_MONTHS",
                  "ONE_TO_5_YEARS", "OVER_5_YEARS"):
            assert b in MATURITY_BUCKETS
        assert len(MATURITY_BUCKETS) == 5

    def test_market_variables_byte_for_byte(self):
        for v in ("INTEREST_RATE", "FOREIGN_EXCHANGE", "EQUITY_PRICE"):
            assert v in MARKET_RISK_VARIABLES

    def test_hedge_types_byte_for_byte(self):
        for h in ("FAIR_VALUE_HEDGE", "CASH_FLOW_HEDGE", "NET_INVESTMENT_HEDGE"):
            assert h in HEDGE_TYPES

    def test_credit_quality_bands_byte_for_byte(self):
        for b in ("INVESTMENT_GRADE", "NON_INVESTMENT_GRADE",
                  "SUB_INVESTMENT_GRADE", "UNRATED"):
            assert b in CREDIT_QUALITY_BANDS

    def test_concentration_thresholds_byte_for_byte(self):
        assert SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD == Decimal("10")
        assert INDUSTRY_CONCENTRATION_PCT_THRESHOLD == Decimal("25")

    def test_disclosure_class_valid(self):
        r = IFRS7DisclosureEngine.validate_disclosure_class("QUANTITATIVE_RISK_DATA")
        assert r["valid"] is True

    def test_disclosure_class_unknown_rule6(self):
        r = IFRS7DisclosureEngine.validate_disclosure_class("WEIRD")
        assert r["valid"] is False

    def test_concentration_single_above(self):
        """120K / 1M = 12% > 10% → concentrated."""
        r = IFRS7DisclosureEngine.credit_risk_concentration(
            Decimal("120000"), Decimal("1000000"), "SINGLE_COUNTERPARTY")
        assert r["is_concentrated"] is True

    def test_concentration_single_at_threshold(self):
        """Exactly 10% → NOT concentrated (strict >)."""
        r = IFRS7DisclosureEngine.credit_risk_concentration(
            Decimal("100000"), Decimal("1000000"), "SINGLE_COUNTERPARTY")
        assert r["is_concentrated"] is False

    def test_concentration_industry_threshold(self):
        r = IFRS7DisclosureEngine.credit_risk_concentration(
            Decimal("300000"), Decimal("1000000"), "INDUSTRY")
        assert r["is_concentrated"] is True

    def test_concentration_zero_total_rule1(self):
        r = IFRS7DisclosureEngine.credit_risk_concentration(
            Decimal("100000"), Decimal("0"))
        assert r["concentration_pct"] is None

    def test_maturity_on_demand(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(
            0, on_demand=True) == "ON_DEMAND"

    def test_maturity_up_to_3_months(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(60) == "UP_TO_3_MONTHS"

    def test_maturity_3_months_boundary(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(90) == "UP_TO_3_MONTHS"

    def test_maturity_3_to_12_months(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(180) == "THREE_TO_12_MONTHS"

    def test_maturity_1_year_boundary(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(365) == "THREE_TO_12_MONTHS"

    def test_maturity_1_to_5_years(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(1000) == "ONE_TO_5_YEARS"

    def test_maturity_5_years_boundary(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(1825) == "ONE_TO_5_YEARS"

    def test_maturity_over_5_years(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(2000) == "OVER_5_YEARS"

    def test_maturity_negative_rule6(self):
        assert IFRS7DisclosureEngine.classify_maturity_bucket(-10) is None

    def test_liquidity_buckets_aggregate(self):
        r = IFRS7DisclosureEngine.liquidity_maturity_buckets(
            [(60, Decimal("100000")), (200, Decimal("200000")),
             (1000, Decimal("500000")), (2500, Decimal("100000"))],
            on_demand_amount=Decimal("50000"))
        bks = r["buckets"]
        assert bks["ON_DEMAND"] == "50000.00"
        assert bks["UP_TO_3_MONTHS"] == "100000.00"
        assert bks["OVER_5_YEARS"] == "100000.00"

    def test_market_sensitivity_interest(self):
        r = IFRS7DisclosureEngine.market_risk_sensitivity(
            "INTEREST_RATE", Decimal("100000000"), Decimal("1"))
        assert r["impact"] == "1000000.00"

    def test_market_sensitivity_fx(self):
        r = IFRS7DisclosureEngine.market_risk_sensitivity(
            "FOREIGN_EXCHANGE", Decimal("50000000"), Decimal("5"))
        assert r["impact"] == "2500000.00"

    def test_market_sensitivity_unknown_rule6(self):
        r = IFRS7DisclosureEngine.market_risk_sensitivity(
            "WEIRD", Decimal("100000000"), Decimal("1"))
        assert r["computed"] is False

    def test_hedge_pack_fair_value(self):
        r = IFRS7DisclosureEngine.hedge_disclosure_pack("FAIR_VALUE_HEDGE")
        assert r["disclosure_count"] == 6

    def test_hedge_pack_cash_flow(self):
        r = IFRS7DisclosureEngine.hedge_disclosure_pack("CASH_FLOW_HEDGE")
        assert r["disclosure_count"] == 7

    def test_hedge_pack_net_investment(self):
        r = IFRS7DisclosureEngine.hedge_disclosure_pack("NET_INVESTMENT_HEDGE")
        assert r["disclosure_count"] == 6

    def test_hedge_pack_unknown_rule6(self):
        r = IFRS7DisclosureEngine.hedge_disclosure_pack("WEIRD")
        assert r["computed"] is False

    def test_completeness_complete(self):
        r = IFRS7DisclosureEngine.disclosure_completeness(
            ["a", "b"], ["a", "b", "c"])
        assert r["complete"] is True

    def test_completeness_gap(self):
        r = IFRS7DisclosureEngine.disclosure_completeness(
            ["a", "b", "c"], ["a"])
        assert r["complete"] is False
        assert r["missing_count"] == 2

    def test_completeness_empty_required_rule1(self):
        r = IFRS7DisclosureEngine.disclosure_completeness([], [])
        assert r["complete"] is None


# ============================================================================
# #111 IAS 1 Presentation (33)
# ============================================================================

class TestIAS1Presentation:

    def test_components_byte_for_byte(self):
        for c in ("STATEMENT_OF_FINANCIAL_POSITION",
                  "STATEMENT_OF_PROFIT_OR_LOSS_AND_OCI",
                  "STATEMENT_OF_CHANGES_IN_EQUITY",
                  "STATEMENT_OF_CASH_FLOWS",
                  "NOTES_INCLUDING_ACCOUNTING_POLICIES"):
            assert c in COMPLETE_STATEMENTS_COMPONENTS
        assert len(COMPLETE_STATEMENTS_COMPONENTS) == 5

    def test_going_concern_outcomes_byte_for_byte(self):
        for o in ("GOING_CONCERN_ASSESSED",
                  "SIGNIFICANT_UNCERTAINTY_DISCLOSED",
                  "NOT_PREPARED_ON_GOING_CONCERN_BASIS"):
            assert o in GOING_CONCERN_OUTCOMES

    def test_statement_formats_byte_for_byte(self):
        for f in ("SINGLE_STATEMENT", "TWO_STATEMENT"):
            assert f in STATEMENT_FORMATS

    def test_current_asset_criteria_byte_for_byte(self):
        for c in ("EXPECTED_REALISATION_IN_OPERATING_CYCLE",
                  "HELD_PRIMARILY_FOR_TRADING",
                  "EXPECTED_REALISATION_WITHIN_12_MONTHS",
                  "CASH_OR_CASH_EQUIVALENT",
                  "INVENTORY_HELD_FOR_SALE_OR_USE"):
            assert c in CURRENT_ASSET_CRITERIA
        assert len(CURRENT_ASSET_CRITERIA) == 5

    def test_current_liability_criteria_byte_for_byte(self):
        for c in ("EXPECTED_SETTLEMENT_IN_OPERATING_CYCLE",
                  "HELD_PRIMARILY_FOR_TRADING",
                  "DUE_WITHIN_12_MONTHS",
                  "NO_UNCONDITIONAL_RIGHT_TO_DEFER_BEYOND_12M",
                  "LIABILITY_PAYABLE_ON_DEMAND"):
            assert c in CURRENT_LIABILITY_CRITERIA
        assert len(CURRENT_LIABILITY_CRITERIA) == 5

    def test_oci_classifications_byte_for_byte(self):
        for c in ("RECYCLABLE_TO_PNL", "NEVER_RECYCLED"):
            assert c in OCI_CLASSIFICATIONS

    def test_oci_line_items_byte_for_byte(self):
        for i in ("REVALUATION_SURPLUS", "FVTOCI_DEBT_FAIR_VALUE_CHANGES",
                  "FVTOCI_EQUITY_FAIR_VALUE_CHANGES",
                  "CASH_FLOW_HEDGE_RESERVE", "DEFINED_BENEFIT_REMEASUREMENT"):
            assert i in OCI_LINE_ITEMS
        assert len(OCI_LINE_ITEMS) == 5

    def test_oci_recycling_map_byte_for_byte(self):
        assert OCI_RECYCLING_MAP["REVALUATION_SURPLUS"] == "NEVER_RECYCLED"
        assert OCI_RECYCLING_MAP["FVTOCI_DEBT_FAIR_VALUE_CHANGES"] == "RECYCLABLE_TO_PNL"
        assert OCI_RECYCLING_MAP["FVTOCI_EQUITY_FAIR_VALUE_CHANGES"] == "NEVER_RECYCLED"
        assert OCI_RECYCLING_MAP["CASH_FLOW_HEDGE_RESERVE"] == "RECYCLABLE_TO_PNL"
        assert OCI_RECYCLING_MAP["DEFINED_BENEFIT_REMEASUREMENT"] == "NEVER_RECYCLED"

    def test_materiality_thresholds_byte_for_byte(self):
        assert MATERIALITY_PCT_OF_REVENUE == Decimal("5")
        assert MATERIALITY_PCT_OF_TOTAL_ASSETS == Decimal("1")
        assert MATERIALITY_PCT_OF_EQUITY == Decimal("5")

    def test_complete_set_all_5(self):
        r = IAS1PresentationEngine.validate_complete_statements_set(
            list(COMPLETE_STATEMENTS_COMPONENTS))
        assert r["complete"] is True

    def test_complete_set_missing(self):
        r = IAS1PresentationEngine.validate_complete_statements_set(
            ["STATEMENT_OF_FINANCIAL_POSITION"])
        assert r["complete"] is False

    def test_going_concern_standard(self):
        r = IAS1PresentationEngine.going_concern_assessment(False, False)
        assert r["outcome"] == "GOING_CONCERN_ASSESSED"

    def test_going_concern_significant_uncertainty(self):
        r = IAS1PresentationEngine.going_concern_assessment(True, False)
        assert r["outcome"] == "SIGNIFICANT_UNCERTAINTY_DISCLOSED"

    def test_going_concern_alternative_basis(self):
        r = IAS1PresentationEngine.going_concern_assessment(True, True)
        assert r["outcome"] == "NOT_PREPARED_ON_GOING_CONCERN_BASIS"

    def test_going_concern_missing_rule1(self):
        r = IAS1PresentationEngine.going_concern_assessment(None, False)
        assert r["outcome"] is None

    def test_asset_current_when_any(self):
        r = IAS1PresentationEngine.asset_current_classification(
            {"CASH_OR_CASH_EQUIVALENT": True})
        assert r["classification"] == "CURRENT"

    def test_asset_non_current_default(self):
        r = IAS1PresentationEngine.asset_current_classification({})
        assert r["classification"] == "NON_CURRENT"

    def test_liability_current_due_in_12m(self):
        r = IAS1PresentationEngine.liability_current_classification(
            {"DUE_WITHIN_12_MONTHS": True})
        assert r["classification"] == "CURRENT"

    def test_liability_current_no_unconditional_right_to_defer(self):
        r = IAS1PresentationEngine.liability_current_classification(
            {"NO_UNCONDITIONAL_RIGHT_TO_DEFER_BEYOND_12M": True})
        assert r["classification"] == "CURRENT"

    def test_liability_non_current_default(self):
        r = IAS1PresentationEngine.liability_current_classification({})
        assert r["classification"] == "NON_CURRENT"

    def test_oci_revaluation_never_recycled(self):
        r = IAS1PresentationEngine.oci_classification("REVALUATION_SURPLUS")
        assert r["classification"] == "NEVER_RECYCLED"

    def test_oci_fvtoci_debt_recyclable(self):
        r = IAS1PresentationEngine.oci_classification("FVTOCI_DEBT_FAIR_VALUE_CHANGES")
        assert r["classification"] == "RECYCLABLE_TO_PNL"

    def test_oci_fvtoci_equity_never_recycled(self):
        r = IAS1PresentationEngine.oci_classification("FVTOCI_EQUITY_FAIR_VALUE_CHANGES")
        assert r["classification"] == "NEVER_RECYCLED"

    def test_oci_cfh_recyclable(self):
        r = IAS1PresentationEngine.oci_classification("CASH_FLOW_HEDGE_RESERVE")
        assert r["classification"] == "RECYCLABLE_TO_PNL"

    def test_oci_db_remeasurement_never_recycled(self):
        r = IAS1PresentationEngine.oci_classification("DEFINED_BENEFIT_REMEASUREMENT")
        assert r["classification"] == "NEVER_RECYCLED"

    def test_oci_unknown_rule6(self):
        r = IAS1PresentationEngine.oci_classification("WEIRD")
        assert r["computed"] is False

    def test_materiality_revenue_above(self):
        r = IAS1PresentationEngine.materiality_test(
            Decimal("600000"), "REVENUE", Decimal("10000000"))
        assert r["material"] is True

    def test_materiality_revenue_at_threshold(self):
        r = IAS1PresentationEngine.materiality_test(
            Decimal("500000"), "REVENUE", Decimal("10000000"))
        assert r["material"] is False

    def test_materiality_total_assets(self):
        r = IAS1PresentationEngine.materiality_test(
            Decimal("1500000"), "TOTAL_ASSETS", Decimal("100000000"))
        assert r["material"] is True

    def test_materiality_total_assets_at_threshold(self):
        r = IAS1PresentationEngine.materiality_test(
            Decimal("1000000"), "TOTAL_ASSETS", Decimal("100000000"))
        assert r["material"] is False

    def test_materiality_unknown_base_rule6(self):
        r = IAS1PresentationEngine.materiality_test(
            Decimal("100000"), "WEIRD", Decimal("1000000"))
        assert r["computed"] is False

    def test_materiality_zero_base_rule6(self):
        r = IAS1PresentationEngine.materiality_test(
            Decimal("100000"), "REVENUE", Decimal("0"))
        assert r["computed"] is False


# ============================================================================
# #112 IAS 8 Policies (31)
# ============================================================================

class TestIAS8Policies:

    def test_change_types_byte_for_byte(self):
        for c in ("CHANGE_IN_ACCOUNTING_POLICY",
                  "CHANGE_IN_ACCOUNTING_ESTIMATE",
                  "CORRECTION_OF_PRIOR_PERIOD_ERROR"):
            assert c in CHANGE_TYPES
        assert len(CHANGE_TYPES) == 3

    def test_application_methods_byte_for_byte(self):
        for m in ("RETROSPECTIVE_APPLICATION",
                  "PROSPECTIVE_APPLICATION",
                  "RETROSPECTIVE_RESTATEMENT"):
            assert m in APPLICATION_METHODS
        assert len(APPLICATION_METHODS) == 3

    def test_policy_hierarchy_byte_for_byte(self):
        for level in ("APPLY_SPECIFIC_IFRS",
                       "REFER_TO_REQUIREMENTS_FOR_SIMILAR",
                       "REFER_TO_CONCEPTUAL_FRAMEWORK",
                       "REFER_TO_OTHER_STANDARD_SETTERS",
                       "REFER_TO_INDUSTRY_PRACTICE"):
            assert level in POLICY_HIERARCHY_LEVELS
        assert len(POLICY_HIERARCHY_LEVELS) == 5

    def test_change_triggers_byte_for_byte(self):
        for t in ("REQUIRED_BY_IFRS",
                  "VOLUNTARY_FAITHFUL_REPRESENTATION",
                  "VOLUNTARY_RELEVANT_INFORMATION",
                  "NOT_PERMITTED"):
            assert t in POLICY_CHANGE_TRIGGERS
        assert len(POLICY_CHANGE_TRIGGERS) == 4

    def test_error_outcomes_byte_for_byte(self):
        for o in ("RESTATE_COMPARATIVE_AMOUNTS",
                  "RESTATE_OPENING_BALANCES",
                  "DISCLOSE_ONLY"):
            assert o in ERROR_PRESENTATION_OUTCOMES

    def test_estimate_reasons_byte_for_byte(self):
        for r in ("NEW_INFORMATION", "NEW_DEVELOPMENTS", "MORE_EXPERIENCE"):
            assert r in ESTIMATE_CHANGE_REASONS

    def test_materiality_thresholds_byte_for_byte(self):
        assert PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT == Decimal("5")
        assert PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY == Decimal("1")

    def test_classify_change_valid(self):
        r = IAS8PoliciesEngine.classify_change_type("CHANGE_IN_ACCOUNTING_POLICY")
        assert r["valid"] is True

    def test_classify_change_unknown_rule6(self):
        r = IAS8PoliciesEngine.classify_change_type("WEIRD")
        assert r["valid"] is False

    def test_method_policy_retrospective(self):
        r = IAS8PoliciesEngine.required_application_method(
            "CHANGE_IN_ACCOUNTING_POLICY")
        assert r["method"] == "RETROSPECTIVE_APPLICATION"

    def test_method_estimate_prospective(self):
        r = IAS8PoliciesEngine.required_application_method(
            "CHANGE_IN_ACCOUNTING_ESTIMATE")
        assert r["method"] == "PROSPECTIVE_APPLICATION"

    def test_method_error_restatement(self):
        r = IAS8PoliciesEngine.required_application_method(
            "CORRECTION_OF_PRIOR_PERIOD_ERROR")
        assert r["method"] == "RETROSPECTIVE_RESTATEMENT"

    def test_method_unknown_rule6(self):
        r = IAS8PoliciesEngine.required_application_method("WEIRD")
        assert r["method"] is None

    def test_trigger_required(self):
        r = IAS8PoliciesEngine.validate_policy_change_trigger("REQUIRED_BY_IFRS")
        assert r["valid"] is True

    def test_trigger_voluntary_faithful(self):
        r = IAS8PoliciesEngine.validate_policy_change_trigger(
            "VOLUNTARY_FAITHFUL_REPRESENTATION")
        assert r["valid"] is True

    def test_trigger_voluntary_relevant(self):
        r = IAS8PoliciesEngine.validate_policy_change_trigger(
            "VOLUNTARY_RELEVANT_INFORMATION")
        assert r["valid"] is True

    def test_trigger_not_permitted_fail_closed(self):
        r = IAS8PoliciesEngine.validate_policy_change_trigger("NOT_PERMITTED")
        assert r["valid"] is False

    def test_trigger_unknown_rule6(self):
        r = IAS8PoliciesEngine.validate_policy_change_trigger("WEIRD")
        assert r["valid"] is False

    def test_hierarchy_level_1(self):
        assert IAS8PoliciesEngine.policy_hierarchy_level(1) == "APPLY_SPECIFIC_IFRS"

    def test_hierarchy_level_3(self):
        assert IAS8PoliciesEngine.policy_hierarchy_level(3) == "REFER_TO_CONCEPTUAL_FRAMEWORK"

    def test_hierarchy_level_5(self):
        assert IAS8PoliciesEngine.policy_hierarchy_level(5) == "REFER_TO_INDUSTRY_PRACTICE"

    def test_hierarchy_out_of_range_rule6(self):
        assert IAS8PoliciesEngine.policy_hierarchy_level(0) is None
        assert IAS8PoliciesEngine.policy_hierarchy_level(6) is None

    def test_hierarchy_missing_rule1(self):
        assert IAS8PoliciesEngine.policy_hierarchy_level(None) is None

    def test_error_material_by_profit(self):
        r = IAS8PoliciesEngine.error_materiality_test(
            Decimal("60000"), prior_period_profit=Decimal("1000000"))
        assert r["material"] is True
        assert r["outcome"] == "RESTATE_COMPARATIVE_AMOUNTS"

    def test_error_at_profit_threshold(self):
        r = IAS8PoliciesEngine.error_materiality_test(
            Decimal("50000"), prior_period_profit=Decimal("1000000"))
        assert r["material"] is False

    def test_error_material_by_equity(self):
        r = IAS8PoliciesEngine.error_materiality_test(
            Decimal("1500000"), prior_period_equity=Decimal("100000000"))
        assert r["material"] is True

    def test_error_at_equity_threshold(self):
        r = IAS8PoliciesEngine.error_materiality_test(
            Decimal("1000000"), prior_period_equity=Decimal("100000000"))
        assert r["material"] is False

    def test_error_either_base_sufficient(self):
        """Below profit threshold but above equity threshold → material."""
        r = IAS8PoliciesEngine.error_materiality_test(
            Decimal("2000000"),
            prior_period_profit=Decimal("100000000"),
            prior_period_equity=Decimal("100000000"))
        assert r["material"] is True

    def test_error_missing_amount_rule1(self):
        r = IAS8PoliciesEngine.error_materiality_test(
            None, prior_period_profit=Decimal("1000000"))
        assert r["material"] is None

    def test_error_no_base_rule1(self):
        r = IAS8PoliciesEngine.error_materiality_test(Decimal("60000"))
        assert r["material"] is None

    def test_error_negative_amount_uses_abs(self):
        r = IAS8PoliciesEngine.error_materiality_test(
            Decimal("-60000"), prior_period_profit=Decimal("1000000"))
        assert r["material"] is True

"""
================================================================================
A2Z MIS 360 — Volume Twenty-Four Batch Tests (Standards #113-#116 — IFRS 5/IAS 7/IFRS 8/IAS 24)
================================================================================

Tests Standards #113 IFRS 5 Held for Sale & Discontinued Operations,
#114 IAS 7 Cash Flow Statements, #115 IFRS 8 Operating Segments,
#116 IAS 24 Related Party Disclosures.

Total: 106 unit tests covering: HFS criteria all-required + LOWER_OF measurement +
       depreciation cessation; cash flow OPERATING/INVESTING/FINANCING classification +
       indirect method reconciliation; IFRS 8 quantitative thresholds (10%/75%) +
       aggregation criteria (all-5-required) + major customer 10%; IAS 24 7 categories
       + KMP test + close family + 5 required disclosures + govt-related relief.

Run via:
    pytest tests/test_volume_twenty_four_batch.py -v
================================================================================
"""

from __future__ import annotations

from decimal import Decimal

from utils.held_for_sale import (
    HeldForSaleEngine,
    HELD_FOR_SALE_CRITERIA, MEASUREMENT_OUTCOMES,
    DISCONTINUED_OPERATION_CRITERIA, PRESENTATION_OUTCOMES,
    EXPECTED_SALE_MAX_MONTHS,
)
from utils.cash_flow_statement import (
    CashFlowEngine,
    CASH_FLOW_CATEGORIES, PRESENTATION_METHODS, OPERATING_RECON_ADJUSTMENTS,
    OPERATING_CASH_FLOWS_EXAMPLES, INVESTING_CASH_FLOWS_EXAMPLES,
    FINANCING_CASH_FLOWS_EXAMPLES,
    CASH_EQUIVALENT_MAX_MATURITY_MONTHS,
)
from utils.operating_segments import (
    OperatingSegmentEngine,
    OPERATING_SEGMENT_CRITERIA,
    REVENUE_THRESHOLD_PCT, PROFIT_LOSS_THRESHOLD_PCT, ASSETS_THRESHOLD_PCT,
    REPORTABLE_SEGMENT_AGGREGATE_PCT,
    AGGREGATION_CRITERIA, GEOGRAPHIC_DISCLOSURES,
    MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT,
)
from utils.related_party import (
    RelatedPartyEngine,
    RELATED_PARTY_CATEGORIES, KMP_CRITERIA, CLOSE_FAMILY_MEMBERS,
    REQUIRED_DISCLOSURES, KMP_COMPENSATION_CATEGORIES,
    GOVERNMENT_RELATED_RELIEF,
)


# ============================================================================
# #113 IFRS 5 Held for Sale (24)
# ============================================================================

class TestHeldForSale:

    def test_hfs_criteria_byte_for_byte(self):
        for c in ("AVAILABLE_FOR_IMMEDIATE_SALE_IN_PRESENT_CONDITION",
                  "SALE_HIGHLY_PROBABLE", "MANAGEMENT_COMMITTED_TO_PLAN",
                  "ACTIVE_PROGRAMME_TO_LOCATE_BUYER",
                  "MARKETED_AT_REASONABLE_PRICE",
                  "EXPECTED_SALE_WITHIN_12_MONTHS"):
            assert c in HELD_FOR_SALE_CRITERIA
        assert len(HELD_FOR_SALE_CRITERIA) == 6

    def test_measurement_outcomes_byte_for_byte(self):
        for o in ("LOWER_OF_CARRYING_AMOUNT_AND_FVLCD",
                  "IMPAIRMENT_RECOGNISED", "NO_FURTHER_DEPRECIATION"):
            assert o in MEASUREMENT_OUTCOMES

    def test_disc_op_criteria_byte_for_byte(self):
        for c in ("SEPARATE_MAJOR_LINE_OF_BUSINESS",
                  "SEPARATE_MAJOR_GEOGRAPHIC_AREA",
                  "PART_OF_SINGLE_COORDINATED_PLAN",
                  "SUBSIDIARY_ACQUIRED_EXCLUSIVELY_FOR_RESALE"):
            assert c in DISCONTINUED_OPERATION_CRITERIA
        assert len(DISCONTINUED_OPERATION_CRITERIA) == 4

    def test_presentation_outcomes_byte_for_byte(self):
        for o in ("SEPARATE_LINE_ON_BALANCE_SHEET",
                  "SEPARATE_DISCLOSURE_IN_PNL",
                  "DISCLOSE_IN_NOTES_ONLY"):
            assert o in PRESENTATION_OUTCOMES

    def test_max_months_byte_for_byte(self):
        assert EXPECTED_SALE_MAX_MONTHS == 12

    def test_hfs_all_criteria_met(self):
        all_met = {c: True for c in HELD_FOR_SALE_CRITERIA}
        r = HeldForSaleEngine.classify_held_for_sale(all_met)
        assert r["held_for_sale"] is True

    def test_hfs_one_criterion_missing_rule6(self):
        one_missing = {c: True for c in HELD_FOR_SALE_CRITERIA}
        one_missing["EXPECTED_SALE_WITHIN_12_MONTHS"] = False
        r = HeldForSaleEngine.classify_held_for_sale(one_missing)
        assert r["held_for_sale"] is False

    def test_hfs_empty_dict_rule1(self):
        r = HeldForSaleEngine.classify_held_for_sale({})
        assert r["held_for_sale"] is None

    def test_measurement_lower_of_basic(self):
        r = HeldForSaleEngine.held_for_sale_measurement(
            Decimal("1000000"), Decimal("800000"))
        assert r["measurement"] == "800000.00"
        assert r["impairment_loss"] == "200000.00"
        assert r["impaired"] is True

    def test_measurement_no_impairment(self):
        r = HeldForSaleEngine.held_for_sale_measurement(
            Decimal("1000000"), Decimal("1200000"))
        assert r["measurement"] == "1000000.00"
        assert r["impaired"] is False

    def test_measurement_equal(self):
        r = HeldForSaleEngine.held_for_sale_measurement(
            Decimal("1000000"), Decimal("1000000"))
        assert r["impaired"] is False

    def test_measurement_missing_rule1(self):
        r = HeldForSaleEngine.held_for_sale_measurement(None, Decimal("800000"))
        assert r["measurement"] is None

    def test_measurement_negative_rule6(self):
        r = HeldForSaleEngine.held_for_sale_measurement(
            Decimal("-1000"), Decimal("500"))
        assert r["computed"] is False

    def test_depreciation_ceases_when_hfs(self):
        r = HeldForSaleEngine.depreciation_cessation_check(True, Decimal("0"))
        assert r["compliant"] is True

    def test_depreciation_continues_when_hfs_rule6(self):
        r = HeldForSaleEngine.depreciation_cessation_check(True, Decimal("10000"))
        assert r["compliant"] is False

    def test_depreciation_normal_when_not_hfs(self):
        r = HeldForSaleEngine.depreciation_cessation_check(False, Decimal("10000"))
        assert r["compliant"] is True

    def test_depreciation_missing_flag_rule1(self):
        r = HeldForSaleEngine.depreciation_cessation_check(None, Decimal("0"))
        assert r["compliant"] is None

    def test_disc_op_one_criterion_met(self):
        r = HeldForSaleEngine.classify_discontinued_operation(
            {"SEPARATE_MAJOR_LINE_OF_BUSINESS": True})
        assert r["discontinued_operation"] is True

    def test_disc_op_no_criteria(self):
        r = HeldForSaleEngine.classify_discontinued_operation({})
        assert r["discontinued_operation"] is False

    def test_disc_op_all_false(self):
        r = HeldForSaleEngine.classify_discontinued_operation(
            {c: False for c in DISCONTINUED_OPERATION_CRITERIA})
        assert r["discontinued_operation"] is False

    def test_presentation_hfs_only(self):
        r = HeldForSaleEngine.presentation_outcome(True, False)
        assert "SEPARATE_LINE_ON_BALANCE_SHEET" in r["presentation_outcomes"]

    def test_presentation_disc_op_only(self):
        r = HeldForSaleEngine.presentation_outcome(False, True)
        assert "SEPARATE_DISCLOSURE_IN_PNL" in r["presentation_outcomes"]

    def test_presentation_both(self):
        r = HeldForSaleEngine.presentation_outcome(True, True)
        assert "SEPARATE_LINE_ON_BALANCE_SHEET" in r["presentation_outcomes"]
        assert "SEPARATE_DISCLOSURE_IN_PNL" in r["presentation_outcomes"]

    def test_presentation_neither(self):
        r = HeldForSaleEngine.presentation_outcome(False, False)
        assert r["presentation_outcomes"] == ["DISCLOSE_IN_NOTES_ONLY"]


# ============================================================================
# #114 IAS 7 Cash Flow Statements (30)
# ============================================================================

class TestCashFlowStatement:

    def test_categories_byte_for_byte(self):
        for c in ("OPERATING", "INVESTING", "FINANCING"):
            assert c in CASH_FLOW_CATEGORIES
        assert len(CASH_FLOW_CATEGORIES) == 3

    def test_methods_byte_for_byte(self):
        for m in ("DIRECT", "INDIRECT"):
            assert m in PRESENTATION_METHODS

    def test_recon_adjustments_byte_for_byte(self):
        for a in ("NON_CASH_ITEMS", "DEFERRALS_AND_ACCRUALS",
                  "INVESTING_OR_FINANCING_ITEMS"):
            assert a in OPERATING_RECON_ADJUSTMENTS

    def test_operating_examples_byte_for_byte(self):
        assert len(OPERATING_CASH_FLOWS_EXAMPLES) == 5

    def test_investing_examples_byte_for_byte(self):
        assert len(INVESTING_CASH_FLOWS_EXAMPLES) == 5

    def test_financing_examples_byte_for_byte(self):
        assert len(FINANCING_CASH_FLOWS_EXAMPLES) == 5

    def test_cash_equivalent_threshold_byte_for_byte(self):
        assert CASH_EQUIVALENT_MAX_MATURITY_MONTHS == 3

    def test_classify_operating(self):
        r = CashFlowEngine.classify_cash_flow("INTEREST_PAID")
        assert r["category"] == "OPERATING"

    def test_classify_investing(self):
        r = CashFlowEngine.classify_cash_flow("PAYMENTS_TO_ACQUIRE_PPE")
        assert r["category"] == "INVESTING"

    def test_classify_financing(self):
        r = CashFlowEngine.classify_cash_flow("DIVIDENDS_PAID")
        assert r["category"] == "FINANCING"

    def test_classify_lease_payments_financing(self):
        r = CashFlowEngine.classify_cash_flow("PAYMENTS_FOR_LEASE_LIABILITIES")
        assert r["category"] == "FINANCING"

    def test_classify_unknown_rule6(self):
        r = CashFlowEngine.classify_cash_flow("WEIRD")
        assert r["category"] is None

    def test_validate_method_direct(self):
        r = CashFlowEngine.validate_method("DIRECT")
        assert r["valid"] is True

    def test_validate_method_indirect(self):
        r = CashFlowEngine.validate_method("INDIRECT")
        assert r["valid"] is True

    def test_validate_method_unknown_rule6(self):
        r = CashFlowEngine.validate_method("WEIRD")
        assert r["valid"] is False

    def test_cash_equivalent_qualifies(self):
        r = CashFlowEngine.cash_and_equivalents_check(2)
        assert r["qualifies_as_equivalent"] is True

    def test_cash_equivalent_boundary_inclusive(self):
        r = CashFlowEngine.cash_and_equivalents_check(3)
        assert r["qualifies_as_equivalent"] is True

    def test_cash_equivalent_exceeds(self):
        r = CashFlowEngine.cash_and_equivalents_check(4)
        assert r["qualifies_as_equivalent"] is False

    def test_cash_equivalent_zero(self):
        r = CashFlowEngine.cash_and_equivalents_check(0)
        assert r["qualifies_as_equivalent"] is True

    def test_cash_equivalent_missing_rule1(self):
        r = CashFlowEngine.cash_and_equivalents_check(None)
        assert r["qualifies_as_equivalent"] is None

    def test_cash_equivalent_negative_rule6(self):
        r = CashFlowEngine.cash_and_equivalents_check(-1)
        assert r["qualifies_as_equivalent"] is None

    def test_recon_basic(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(
            Decimal("1000000"),
            depreciation=Decimal("200000"),
            amortisation=Decimal("100000"),
            gain_on_disposal=Decimal("50000"),
            increase_in_receivables=Decimal("30000"),
            increase_in_payables=Decimal("40000"),
            increase_in_inventory=Decimal("60000"),
        )
        assert r["operating_cash_flow"] == "1200000.00"

    def test_recon_depreciation_only(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(
            Decimal("500000"), depreciation=Decimal("100000"))
        assert r["operating_cash_flow"] == "600000.00"

    def test_recon_pbt_only(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(Decimal("500000"))
        assert r["operating_cash_flow"] == "500000.00"

    def test_recon_loss_position(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(
            Decimal("-500000"), depreciation=Decimal("100000"))
        assert r["operating_cash_flow"] == "-400000.00"

    def test_recon_missing_pbt_rule1(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(None)
        assert r["operating_cash_flow"] is None

    def test_recon_gain_subtracted(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(
            Decimal("1000000"), gain_on_disposal=Decimal("100000"))
        assert r["operating_cash_flow"] == "900000.00"

    def test_recon_receivables_use_cash(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(
            Decimal("1000000"), increase_in_receivables=Decimal("50000"))
        assert r["operating_cash_flow"] == "950000.00"

    def test_recon_payables_provide_cash(self):
        r = CashFlowEngine.reconcile_pnl_to_operating(
            Decimal("1000000"), increase_in_payables=Decimal("50000"))
        assert r["operating_cash_flow"] == "1050000.00"


# ============================================================================
# #115 IFRS 8 Operating Segments (27)
# ============================================================================

class TestOperatingSegments:

    def test_segment_criteria_byte_for_byte(self):
        for c in ("EARNS_REVENUE_INCURS_EXPENSES",
                  "OPERATING_RESULTS_REGULARLY_REVIEWED",
                  "DISCRETE_FINANCIAL_INFORMATION_AVAILABLE"):
            assert c in OPERATING_SEGMENT_CRITERIA
        assert len(OPERATING_SEGMENT_CRITERIA) == 3

    def test_thresholds_byte_for_byte(self):
        assert REVENUE_THRESHOLD_PCT == Decimal("10")
        assert PROFIT_LOSS_THRESHOLD_PCT == Decimal("10")
        assert ASSETS_THRESHOLD_PCT == Decimal("10")

    def test_aggregate_threshold_byte_for_byte(self):
        assert REPORTABLE_SEGMENT_AGGREGATE_PCT == Decimal("75")

    def test_aggregation_criteria_byte_for_byte(self):
        for c in ("SIMILAR_LONG_TERM_FINANCIAL_PERFORMANCE",
                  "SIMILAR_PRODUCTS_OR_SERVICES",
                  "SIMILAR_PRODUCTION_PROCESSES",
                  "SIMILAR_CUSTOMER_TYPES",
                  "SIMILAR_DISTRIBUTION_METHODS"):
            assert c in AGGREGATION_CRITERIA
        assert len(AGGREGATION_CRITERIA) == 5

    def test_geographic_disclosures_byte_for_byte(self):
        for d in ("REVENUE_FROM_EXTERNAL_CUSTOMERS_BY_COUNTRY",
                  "NON_CURRENT_ASSETS_BY_COUNTRY",
                  "MAJOR_CUSTOMERS_DISCLOSURE"):
            assert d in GEOGRAPHIC_DISCLOSURES

    def test_major_customer_threshold_byte_for_byte(self):
        assert MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT == Decimal("10")

    def test_segment_all_3_met(self):
        all_met = {c: True for c in OPERATING_SEGMENT_CRITERIA}
        r = OperatingSegmentEngine.identify_operating_segment(all_met)
        assert r["is_operating_segment"] is True

    def test_segment_one_missing_rule6(self):
        one_missing = {c: True for c in OPERATING_SEGMENT_CRITERIA}
        one_missing["DISCRETE_FINANCIAL_INFORMATION_AVAILABLE"] = False
        r = OperatingSegmentEngine.identify_operating_segment(one_missing)
        assert r["is_operating_segment"] is False

    def test_segment_empty_rule1(self):
        r = OperatingSegmentEngine.identify_operating_segment({})
        assert r["is_operating_segment"] is None

    def test_threshold_revenue_passes(self):
        r = OperatingSegmentEngine.quantitative_threshold_test(
            Decimal("15000000"), None, None,
            Decimal("100000000"), None, None)
        assert r["revenue_test_passed"] is True
        assert r["reportable"] is True

    def test_threshold_revenue_boundary_inclusive(self):
        r = OperatingSegmentEngine.quantitative_threshold_test(
            Decimal("10000000"), None, None,
            Decimal("100000000"), None, None)
        assert r["revenue_test_passed"] is True

    def test_threshold_below(self):
        r = OperatingSegmentEngine.quantitative_threshold_test(
            Decimal("5000000"), None, None,
            Decimal("100000000"), None, None)
        assert r["revenue_test_passed"] is False

    def test_threshold_assets_passes(self):
        r = OperatingSegmentEngine.quantitative_threshold_test(
            None, None, Decimal("11000000"),
            None, None, Decimal("100000000"))
        assert r["assets_test_passed"] is True

    def test_threshold_any_one_passes_makes_reportable(self):
        r = OperatingSegmentEngine.quantitative_threshold_test(
            Decimal("5000000"), None, Decimal("12000000"),
            Decimal("100000000"), None, Decimal("100000000"))
        assert r["reportable"] is True

    def test_threshold_profit_loss_uses_abs(self):
        r = OperatingSegmentEngine.quantitative_threshold_test(
            None, Decimal("-15000"), None,
            None, Decimal("100000"), None)
        assert r["profit_loss_test_passed"] is True

    def test_aggregate_75_pct_meets(self):
        r = OperatingSegmentEngine.aggregate_external_revenue_test(
            Decimal("80000000"), Decimal("100000000"))
        assert r["meets_75pct_threshold"] is True

    def test_aggregate_75_pct_boundary_inclusive(self):
        r = OperatingSegmentEngine.aggregate_external_revenue_test(
            Decimal("75000000"), Decimal("100000000"))
        assert r["meets_75pct_threshold"] is True

    def test_aggregate_below_75_pct(self):
        r = OperatingSegmentEngine.aggregate_external_revenue_test(
            Decimal("70000000"), Decimal("100000000"))
        assert r["meets_75pct_threshold"] is False

    def test_aggregate_missing_rule1(self):
        r = OperatingSegmentEngine.aggregate_external_revenue_test(
            None, Decimal("100000000"))
        assert r["meets_75pct_threshold"] is None

    def test_aggregation_all_5_met(self):
        all_met = {c: True for c in AGGREGATION_CRITERIA}
        r = OperatingSegmentEngine.aggregation_criteria_check(all_met)
        assert r["can_aggregate"] is True

    def test_aggregation_one_missing_rule6(self):
        one_missing = {c: True for c in AGGREGATION_CRITERIA}
        one_missing["SIMILAR_PRODUCTION_PROCESSES"] = False
        r = OperatingSegmentEngine.aggregation_criteria_check(one_missing)
        assert r["can_aggregate"] is False

    def test_aggregation_empty_rule1(self):
        r = OperatingSegmentEngine.aggregation_criteria_check({})
        assert r["can_aggregate"] is None

    def test_major_customer_passes(self):
        r = OperatingSegmentEngine.major_customer_test(
            Decimal("15000000"), Decimal("100000000"))
        assert r["is_major_customer"] is True

    def test_major_customer_boundary_inclusive(self):
        r = OperatingSegmentEngine.major_customer_test(
            Decimal("10000000"), Decimal("100000000"))
        assert r["is_major_customer"] is True

    def test_major_customer_below(self):
        r = OperatingSegmentEngine.major_customer_test(
            Decimal("5000000"), Decimal("100000000"))
        assert r["is_major_customer"] is False

    def test_major_customer_zero_total_rule1(self):
        r = OperatingSegmentEngine.major_customer_test(
            Decimal("1000"), Decimal("0"))
        assert r["is_major_customer"] is None

    def test_major_customer_missing_rule1(self):
        r = OperatingSegmentEngine.major_customer_test(None, Decimal("100000"))
        assert r["is_major_customer"] is None


# ============================================================================
# #116 IAS 24 Related Party Disclosures (25)
# ============================================================================

class TestRelatedParty:

    def test_categories_byte_for_byte(self):
        for c in ("PARENT_OR_SUBSIDIARY", "FELLOW_SUBSIDIARY",
                  "ASSOCIATE_OR_JOINT_VENTURE",
                  "KEY_MANAGEMENT_PERSONNEL_OR_FAMILY",
                  "POST_EMPLOYMENT_BENEFIT_PLAN",
                  "PARTY_WITH_CONTROL_OVER_KMP",
                  "GOVERNMENT_RELATED"):
            assert c in RELATED_PARTY_CATEGORIES
        assert len(RELATED_PARTY_CATEGORIES) == 7

    def test_kmp_criteria_byte_for_byte(self):
        for c in ("DIRECT_AUTHORITY_FOR_PLANNING",
                  "DIRECT_AUTHORITY_FOR_DIRECTING",
                  "DIRECT_AUTHORITY_FOR_CONTROLLING",
                  "INCLUDES_DIRECTORS",
                  "INCLUDES_SENIOR_MANAGEMENT"):
            assert c in KMP_CRITERIA
        assert len(KMP_CRITERIA) == 5

    def test_close_family_byte_for_byte(self):
        for f in ("SPOUSE_OR_DOMESTIC_PARTNER",
                  "CHILDREN_OF_INDIVIDUAL_OR_PARTNER",
                  "DEPENDENTS_OF_INDIVIDUAL_OR_PARTNER",
                  "DEPENDENTS_OF_SPOUSE_OR_PARTNER"):
            assert f in CLOSE_FAMILY_MEMBERS
        assert len(CLOSE_FAMILY_MEMBERS) == 4

    def test_required_disclosures_byte_for_byte(self):
        for d in ("NATURE_OF_RELATIONSHIP", "AMOUNT_OF_TRANSACTIONS",
                  "OUTSTANDING_BALANCES_AND_TERMS",
                  "PROVISIONS_FOR_DOUBTFUL_DEBTS",
                  "EXPENSE_RECOGNISED_FOR_BAD_DEBTS"):
            assert d in REQUIRED_DISCLOSURES
        assert len(REQUIRED_DISCLOSURES) == 5

    def test_kmp_compensation_byte_for_byte(self):
        for c in ("SHORT_TERM_BENEFITS", "POST_EMPLOYMENT_BENEFITS",
                  "OTHER_LONG_TERM_BENEFITS", "TERMINATION_BENEFITS",
                  "SHARE_BASED_PAYMENTS"):
            assert c in KMP_COMPENSATION_CATEGORIES

    def test_govt_relief_byte_for_byte(self):
        for r in ("INDIVIDUALLY_SIGNIFICANT_TRANSACTIONS",
                  "COLLECTIVELY_SIGNIFICANT_TRANSACTIONS",
                  "PARTIAL_EXEMPTION_FROM_FULL_DISCLOSURE"):
            assert r in GOVERNMENT_RELATED_RELIEF

    def test_classify_parent_subsidiary(self):
        r = RelatedPartyEngine.classify_related_party("PARENT_OR_SUBSIDIARY")
        assert r["valid"] is True

    def test_classify_government_related(self):
        r = RelatedPartyEngine.classify_related_party("GOVERNMENT_RELATED")
        assert r["valid"] is True

    def test_classify_unknown_rule6(self):
        r = RelatedPartyEngine.classify_related_party("WEIRD")
        assert r["valid"] is False

    def test_kmp_director_with_authority(self):
        r = RelatedPartyEngine.identify_kmp({
            "DIRECT_AUTHORITY_FOR_PLANNING": True,
            "INCLUDES_DIRECTORS": True,
        })
        assert r["is_kmp"] is True

    def test_kmp_senior_with_directing_authority(self):
        r = RelatedPartyEngine.identify_kmp({
            "DIRECT_AUTHORITY_FOR_DIRECTING": True,
            "INCLUDES_SENIOR_MANAGEMENT": True,
        })
        assert r["is_kmp"] is True

    def test_kmp_no_authority_not_kmp(self):
        r = RelatedPartyEngine.identify_kmp({"INCLUDES_DIRECTORS": True})
        assert r["is_kmp"] is False

    def test_kmp_authority_no_role_not_kmp(self):
        r = RelatedPartyEngine.identify_kmp({
            "DIRECT_AUTHORITY_FOR_PLANNING": True})
        assert r["is_kmp"] is False

    def test_kmp_empty_rule1(self):
        r = RelatedPartyEngine.identify_kmp({})
        assert r["is_kmp"] is None

    def test_close_family_spouse(self):
        r = RelatedPartyEngine.close_family_member_check(
            "SPOUSE_OR_DOMESTIC_PARTNER")
        assert r["is_close_family"] is True

    def test_close_family_children(self):
        r = RelatedPartyEngine.close_family_member_check(
            "CHILDREN_OF_INDIVIDUAL_OR_PARTNER")
        assert r["is_close_family"] is True

    def test_close_family_unknown(self):
        r = RelatedPartyEngine.close_family_member_check("COUSIN")
        assert r["is_close_family"] is False

    def test_disclosures_all_provided(self):
        all_provided = {d: True for d in REQUIRED_DISCLOSURES}
        r = RelatedPartyEngine.validate_disclosure_completeness(all_provided)
        assert r["complete"] is True

    def test_disclosures_one_missing_rule6(self):
        one_missing = {d: True for d in REQUIRED_DISCLOSURES}
        one_missing["NATURE_OF_RELATIONSHIP"] = False
        r = RelatedPartyEngine.validate_disclosure_completeness(one_missing)
        assert r["complete"] is False

    def test_disclosures_empty_rule1(self):
        r = RelatedPartyEngine.validate_disclosure_completeness({})
        assert r["complete"] is None

    def test_govt_relief_applies(self):
        r = RelatedPartyEngine.government_related_entity_relief(
            True, transaction_significance="INDIVIDUALLY_SIGNIFICANT")
        assert r["applies"] is True
        assert r["disclosure_level"] == "FULL"

    def test_govt_relief_collectively_significant(self):
        r = RelatedPartyEngine.government_related_entity_relief(
            True, transaction_significance="COLLECTIVELY_SIGNIFICANT")
        assert r["disclosure_level"] == "QUALITATIVE_ONLY"

    def test_govt_relief_insignificant(self):
        r = RelatedPartyEngine.government_related_entity_relief(
            True, transaction_significance="INSIGNIFICANT")
        assert r["disclosure_level"] == "EXEMPT"

    def test_govt_relief_not_govt_controlled(self):
        r = RelatedPartyEngine.government_related_entity_relief(False)
        assert r["applies"] is False

    def test_govt_relief_missing_input_rule1(self):
        r = RelatedPartyEngine.government_related_entity_relief(None)
        assert r["applies"] is None

"""
================================================================================
A2Z MIS 360 — Volume Twenty-One Batch Tests (Standards #101-#104 — IFRS Family)
================================================================================

Tests Standards #101 IFRS 16 Lease, #102 IFRS 9 Classification,
#103 IFRS 13 Fair Value, #104 IAS 19 Employee Benefits.

Total: 113 unit tests covering: ROU asset + lease liability + IBR amortization +
       short-term/low-value exemptions; IFRS 9 business model + SPPI test +
       AC/FVTOCI/FVTPL classification; IFRS 13 3-level hierarchy + valuation
       techniques + bid-ask spread + transfer detection; IAS 19 DBO PV +
       net DB liability with asset ceiling + net interest direction +
       service cost components + OCI vs P&L remeasurement split.

Run via:
    pytest tests/test_volume_twenty_one_batch.py -v
================================================================================
"""

from __future__ import annotations

from decimal import Decimal

from utils.lease_accounting import (
    LeaseAccountingEngine,
    LEASE_CLASSIFICATIONS, SHORT_TERM_MAX_MONTHS, LOW_VALUE_THRESHOLD_USD,
    MODIFICATION_TYPES, ROU_DEPRECIATION_METHODS,
)
from utils.ifrs9_classification import (
    IFRS9ClassificationEngine,
    BUSINESS_MODELS, MEASUREMENT_CATEGORIES, INSTRUMENT_TYPES,
    SPPI_FAIL_REASONS,
)
from utils.fair_value_measurement import (
    FairValueEngine,
    FAIR_VALUE_HIERARCHY_LEVELS, VALUATION_TECHNIQUES, INPUT_OBSERVABILITY,
    LEVEL_3_INPUTS, TRANSFER_TYPES,
    HIGHLY_LIQUID_BID_ASK_PCT_MAX, LIQUID_BID_ASK_PCT_MAX,
)
from utils.employee_benefits import (
    EmployeeBenefitsEngine,
    BENEFIT_TYPES, SERVICE_COST_COMPONENTS, REMEASUREMENT_COMPONENTS,
    SHORT_TERM_MAX_MONTHS as IAS19_SHORT_TERM_MAX,
)


# ============================================================================
# #101 IFRS 16 Lease Accounting (24)
# ============================================================================

class TestLeaseAccounting:

    def test_classifications_byte_for_byte(self):
        for c in ("SHORT_TERM", "LOW_VALUE", "STANDARD"):
            assert c in LEASE_CLASSIFICATIONS
        assert len(LEASE_CLASSIFICATIONS) == 3

    def test_thresholds_byte_for_byte(self):
        assert SHORT_TERM_MAX_MONTHS == 12
        assert LOW_VALUE_THRESHOLD_USD == Decimal("5000")

    def test_modification_types_byte_for_byte(self):
        for m in ("SCOPE_INCREASE", "SCOPE_DECREASE",
                  "TERM_EXTENSION", "RATE_CHANGE"):
            assert m in MODIFICATION_TYPES
        assert len(MODIFICATION_TYPES) == 4

    def test_depreciation_methods_byte_for_byte(self):
        for m in ("STRAIGHT_LINE", "USAGE_BASED", "DIMINISHING"):
            assert m in ROU_DEPRECIATION_METHODS

    def test_classification_short_term(self):
        assert LeaseAccountingEngine.lease_classification(6, None) == "SHORT_TERM"

    def test_classification_short_term_boundary(self):
        assert LeaseAccountingEngine.lease_classification(12, None) == "SHORT_TERM"

    def test_classification_low_value(self):
        assert LeaseAccountingEngine.lease_classification(
            36, Decimal("3000")) == "LOW_VALUE"

    def test_classification_low_value_boundary(self):
        assert LeaseAccountingEngine.lease_classification(
            36, Decimal("5000")) == "STANDARD"

    def test_classification_standard(self):
        assert LeaseAccountingEngine.lease_classification(
            36, Decimal("50000")) == "STANDARD"

    def test_classification_missing_term_rule1(self):
        assert LeaseAccountingEngine.lease_classification(None, None) is None

    def test_liability_basic(self):
        r = LeaseAccountingEngine.lease_liability_initial(
            Decimal("100000"), 36, Decimal("10"))
        pv = Decimal(r["pv"])
        assert pv > Decimal("3000000")
        assert pv < Decimal("3200000")

    def test_liability_zero_rate(self):
        r = LeaseAccountingEngine.lease_liability_initial(
            Decimal("100000"), 36, Decimal("0"))
        assert r["pv"] == "3600000.00"

    def test_liability_missing_rule1(self):
        r = LeaseAccountingEngine.lease_liability_initial(
            None, 36, Decimal("10"))
        assert r["pv"] is None

    def test_rou_basic(self):
        r = LeaseAccountingEngine.rou_asset_initial(
            Decimal("3000000"), Decimal("50000"), Decimal("100000"))
        assert r["rou"] == "2950000.00"

    def test_rou_no_costs_or_incentives(self):
        r = LeaseAccountingEngine.rou_asset_initial(
            Decimal("3000000"), None, None)
        assert r["rou"] == "3000000.00"

    def test_rou_missing_liability_rule1(self):
        r = LeaseAccountingEngine.rou_asset_initial(
            None, Decimal("50000"), Decimal("0"))
        assert r["rou"] is None

    def test_depreciation_straight_line(self):
        d = LeaseAccountingEngine.rou_depreciation(Decimal("3600000"), 36)
        assert d == Decimal("100000.00")

    def test_depreciation_missing_rule1(self):
        assert LeaseAccountingEngine.rou_depreciation(None, 36) is None

    def test_depreciation_unknown_method_rule6(self):
        assert LeaseAccountingEngine.rou_depreciation(
            Decimal("3600000"), 36, method="WEIRD") is None

    def test_amortization_basic(self):
        r = LeaseAccountingEngine.lease_liability_amortization(
            Decimal("3000000"), Decimal("100000"), Decimal("10"))
        assert r["interest_portion"] == "25000.00"
        assert r["principal_portion"] == "75000.00"
        assert r["closing_liability"] == "2925000.00"

    def test_amortization_zero_rate(self):
        r = LeaseAccountingEngine.lease_liability_amortization(
            Decimal("3000000"), Decimal("100000"), Decimal("0"))
        assert r["interest_portion"] == "0.00"
        assert r["principal_portion"] == "100000.00"

    def test_amortization_missing_rule1(self):
        r = LeaseAccountingEngine.lease_liability_amortization(
            None, Decimal("100000"), Decimal("10"))
        assert r["computed"] is False

    def test_validate_modification_valid(self):
        r = LeaseAccountingEngine.validate_modification("SCOPE_INCREASE")
        assert r["valid"] is True

    def test_validate_modification_unknown_rule6(self):
        r = LeaseAccountingEngine.validate_modification("WEIRD")
        assert r["valid"] is False


# ============================================================================
# #102 IFRS 9 Classification (26)
# ============================================================================

class TestIFRS9Classification:

    def test_business_models_byte_for_byte(self):
        for m in ("HOLD_TO_COLLECT", "HOLD_TO_COLLECT_AND_SELL", "OTHER"):
            assert m in BUSINESS_MODELS
        assert len(BUSINESS_MODELS) == 3

    def test_measurement_categories_byte_for_byte(self):
        for c in ("AMORTIZED_COST", "FVTOCI_DEBT", "FVTPL",
                  "FVTOCI_EQUITY", "FVTPL_EQUITY"):
            assert c in MEASUREMENT_CATEGORIES
        assert len(MEASUREMENT_CATEGORIES) == 5

    def test_instrument_types_byte_for_byte(self):
        for t in ("DEBT", "EQUITY", "DERIVATIVE"):
            assert t in INSTRUMENT_TYPES

    def test_sppi_fail_reasons_byte_for_byte(self):
        for r in ("LEVERAGE", "CONTINGENT_PRINCIPAL", "EQUITY_LINKED",
                  "PROFIT_PARTICIPATION", "EXTREME_PREPAYMENT"):
            assert r in SPPI_FAIL_REASONS
        assert len(SPPI_FAIL_REASONS) == 5

    def test_business_model_valid(self):
        r = IFRS9ClassificationEngine.business_model_assessment("HOLD_TO_COLLECT")
        assert r["valid"] is True

    def test_business_model_unknown_rule6(self):
        r = IFRS9ClassificationEngine.business_model_assessment("WEIRD")
        assert r["valid"] is False

    def test_sppi_passed(self):
        r = IFRS9ClassificationEngine.sppi_test(True)
        assert r["sppi_passed"] is True

    def test_sppi_failed_with_reason(self):
        r = IFRS9ClassificationEngine.sppi_test(False, fail_reason="LEVERAGE")
        assert r["sppi_passed"] is False

    def test_sppi_unknown_fail_reason_rule6(self):
        r = IFRS9ClassificationEngine.sppi_test(False, fail_reason="WEIRD")
        assert r["computed"] is False

    def test_sppi_missing_rule1(self):
        r = IFRS9ClassificationEngine.sppi_test(None)
        assert r["sppi_passed"] is None

    def test_classify_htc_sppi_pass_amortized_cost(self):
        r = IFRS9ClassificationEngine.classify_debt_instrument(
            "HOLD_TO_COLLECT", True)
        assert r["category"] == "AMORTIZED_COST"

    def test_classify_htcs_sppi_pass_fvtoci_debt(self):
        r = IFRS9ClassificationEngine.classify_debt_instrument(
            "HOLD_TO_COLLECT_AND_SELL", True)
        assert r["category"] == "FVTOCI_DEBT"

    def test_classify_other_residual_fvtpl(self):
        r = IFRS9ClassificationEngine.classify_debt_instrument("OTHER", True)
        assert r["category"] == "FVTPL"

    def test_classify_sppi_fail_forces_fvtpl(self):
        r = IFRS9ClassificationEngine.classify_debt_instrument(
            "HOLD_TO_COLLECT", False)
        assert r["category"] == "FVTPL"

    def test_classify_missing_rule1(self):
        r = IFRS9ClassificationEngine.classify_debt_instrument(None, True)
        assert r["category"] is None

    def test_classify_unknown_bm_rule6(self):
        r = IFRS9ClassificationEngine.classify_debt_instrument("WEIRD", True)
        assert r["category"] is None

    def test_equity_fvtoci_election(self):
        r = IFRS9ClassificationEngine.classify_equity_instrument(
            fvtoci_election=True, held_for_trading=False)
        assert r["category"] == "FVTOCI_EQUITY"

    def test_equity_no_election_fvtpl(self):
        r = IFRS9ClassificationEngine.classify_equity_instrument(
            fvtoci_election=False, held_for_trading=False)
        assert r["category"] == "FVTPL_EQUITY"

    def test_equity_held_for_trading_forces_fvtpl(self):
        r = IFRS9ClassificationEngine.classify_equity_instrument(
            fvtoci_election=True, held_for_trading=True)
        assert r["category"] == "FVTPL_EQUITY"

    def test_equity_missing_election_rule1(self):
        r = IFRS9ClassificationEngine.classify_equity_instrument(None)
        assert r["category"] is None

    def test_reclassification_allowed_when_changes(self):
        r = IFRS9ClassificationEngine.reclassification_allowed(
            "HOLD_TO_COLLECT", "HOLD_TO_COLLECT_AND_SELL")
        assert r["allowed"] is True

    def test_reclassification_not_allowed_same_model(self):
        r = IFRS9ClassificationEngine.reclassification_allowed(
            "HOLD_TO_COLLECT", "HOLD_TO_COLLECT")
        assert r["allowed"] is False

    def test_reclassification_unknown_rule6(self):
        r = IFRS9ClassificationEngine.reclassification_allowed("WEIRD", "OTHER")
        assert r["allowed"] is False

    def test_measurement_method_amortized(self):
        assert IFRS9ClassificationEngine.measurement_method(
            "AMORTIZED_COST") == "effective_interest"

    def test_measurement_method_fvtoci(self):
        assert IFRS9ClassificationEngine.measurement_method(
            "FVTOCI_DEBT") == "fair_value"

    def test_measurement_method_unknown(self):
        assert IFRS9ClassificationEngine.measurement_method("WEIRD") is None


# ============================================================================
# #103 IFRS 13 Fair Value (33)
# ============================================================================

class TestFairValueMeasurement:

    def test_levels_byte_for_byte(self):
        for l in ("LEVEL_1", "LEVEL_2", "LEVEL_3"):
            assert l in FAIR_VALUE_HIERARCHY_LEVELS
        assert len(FAIR_VALUE_HIERARCHY_LEVELS) == 3

    def test_techniques_byte_for_byte(self):
        for t in ("MARKET_APPROACH", "INCOME_APPROACH", "COST_APPROACH"):
            assert t in VALUATION_TECHNIQUES

    def test_observability_byte_for_byte(self):
        for o in ("QUOTED_ACTIVE_MARKET", "OBSERVABLE_OTHER", "UNOBSERVABLE"):
            assert o in INPUT_OBSERVABILITY

    def test_level_3_inputs_byte_for_byte(self):
        for i in ("PROBABILITY_OF_DEFAULT", "LOSS_GIVEN_DEFAULT",
                  "ILLIQUIDITY_DISCOUNT", "MODEL_PARAMETER", "BLOCKAGE_DISCOUNT"):
            assert i in LEVEL_3_INPUTS
        assert len(LEVEL_3_INPUTS) == 5

    def test_transfer_types_byte_for_byte(self):
        for t in ("INTO_LEVEL_3", "OUT_OF_LEVEL_3", "INTER_LEVEL"):
            assert t in TRANSFER_TYPES

    def test_liquidity_thresholds_byte_for_byte(self):
        assert HIGHLY_LIQUID_BID_ASK_PCT_MAX == Decimal("0.5")
        assert LIQUID_BID_ASK_PCT_MAX == Decimal("2")

    def test_hierarchy_level_1(self):
        assert FairValueEngine.hierarchy_level("QUOTED_ACTIVE_MARKET") == "LEVEL_1"

    def test_hierarchy_level_2(self):
        assert FairValueEngine.hierarchy_level("OBSERVABLE_OTHER") == "LEVEL_2"

    def test_hierarchy_level_3(self):
        assert FairValueEngine.hierarchy_level("UNOBSERVABLE") == "LEVEL_3"

    def test_hierarchy_unknown_rule6(self):
        assert FairValueEngine.hierarchy_level("WEIRD") is None

    def test_validate_technique(self):
        r = FairValueEngine.validate_valuation_technique("INCOME_APPROACH")
        assert r["valid"] is True

    def test_validate_technique_unknown_rule6(self):
        r = FairValueEngine.validate_valuation_technique("WEIRD")
        assert r["valid"] is False

    def test_mid_price_basic(self):
        r = FairValueEngine.mid_price(Decimal("100"), Decimal("102"))
        assert r["mid"] == "101.00"

    def test_mid_price_equal(self):
        r = FairValueEngine.mid_price(Decimal("100"), Decimal("100"))
        assert r["mid"] == "100.00"

    def test_mid_price_inverted_rule6(self):
        r = FairValueEngine.mid_price(Decimal("105"), Decimal("100"))
        assert r["computed"] is False

    def test_mid_price_negative_rule6(self):
        r = FairValueEngine.mid_price(Decimal("-10"), Decimal("100"))
        assert r["computed"] is False

    def test_mid_price_missing_rule1(self):
        r = FairValueEngine.mid_price(None, Decimal("100"))
        assert r["mid"] is None

    def test_spread_pct_basic(self):
        s = FairValueEngine.bid_ask_spread_pct(Decimal("100"), Decimal("102"))
        assert s == Decimal("2")

    def test_spread_pct_zero_bid_rule1(self):
        assert FairValueEngine.bid_ask_spread_pct(Decimal("0"), Decimal("100")) is None

    def test_liquidity_highly_liquid(self):
        assert FairValueEngine.liquidity_classification(
            Decimal("0.3")) == "HIGHLY_LIQUID"

    def test_liquidity_boundary_highly(self):
        assert FairValueEngine.liquidity_classification(
            Decimal("0.5")) == "HIGHLY_LIQUID"

    def test_liquidity_liquid(self):
        assert FairValueEngine.liquidity_classification(
            Decimal("1.5")) == "LIQUID"

    def test_liquidity_boundary_liquid(self):
        assert FairValueEngine.liquidity_classification(
            Decimal("2")) == "LIQUID"

    def test_liquidity_illiquid(self):
        assert FairValueEngine.liquidity_classification(
            Decimal("5")) == "ILLIQUID"

    def test_liquidity_missing_rule1(self):
        assert FairValueEngine.liquidity_classification(None) is None

    def test_transfer_into_level_3(self):
        r = FairValueEngine.transfer_detection("LEVEL_2", "LEVEL_3")
        assert r["transfer_type"] == "INTO_LEVEL_3"

    def test_transfer_out_of_level_3(self):
        r = FairValueEngine.transfer_detection("LEVEL_3", "LEVEL_2")
        assert r["transfer_type"] == "OUT_OF_LEVEL_3"

    def test_transfer_inter_level(self):
        r = FairValueEngine.transfer_detection("LEVEL_1", "LEVEL_2")
        assert r["transfer_type"] == "INTER_LEVEL"

    def test_transfer_no_change(self):
        r = FairValueEngine.transfer_detection("LEVEL_2", "LEVEL_2")
        assert r["transfer"] is None

    def test_transfer_unknown_rule6(self):
        r = FairValueEngine.transfer_detection("LEVEL_4", "LEVEL_1")
        assert r["computed"] is False

    def test_disclosure_level_1_minimal(self):
        r = FairValueEngine.disclosure_pack("LEVEL_1")
        assert r["disclosure_count"] == 2

    def test_disclosure_level_3_extensive(self):
        r = FairValueEngine.disclosure_pack("LEVEL_3")
        assert r["disclosure_count"] == 8

    def test_disclosure_unknown_rule6(self):
        r = FairValueEngine.disclosure_pack("WEIRD")
        assert r["computed"] is False


# ============================================================================
# #104 IAS 19 Employee Benefits (30)
# ============================================================================

class TestEmployeeBenefits:

    def test_benefit_types_byte_for_byte(self):
        for t in ("SHORT_TERM",
                  "POST_EMPLOYMENT_DEFINED_CONTRIBUTION",
                  "POST_EMPLOYMENT_DEFINED_BENEFIT",
                  "OTHER_LONG_TERM", "TERMINATION"):
            assert t in BENEFIT_TYPES
        assert len(BENEFIT_TYPES) == 5

    def test_service_cost_components_byte_for_byte(self):
        for c in ("CURRENT_SERVICE_COST", "PAST_SERVICE_COST",
                  "SETTLEMENT_GAIN_LOSS"):
            assert c in SERVICE_COST_COMPONENTS

    def test_remeasurement_components_byte_for_byte(self):
        for c in ("ACTUARIAL_GAIN_LOSS", "ASSET_RETURN_OCI"):
            assert c in REMEASUREMENT_COMPONENTS

    def test_short_term_threshold_byte_for_byte(self):
        assert IAS19_SHORT_TERM_MAX == 12

    def test_classification_short_term_valid(self):
        r = EmployeeBenefitsEngine.benefit_classification(
            "SHORT_TERM", settlement_within_months=6)
        assert r["valid"] is True

    def test_classification_short_term_too_long(self):
        r = EmployeeBenefitsEngine.benefit_classification(
            "SHORT_TERM", settlement_within_months=18)
        assert r["valid"] is False

    def test_classification_short_term_boundary(self):
        r = EmployeeBenefitsEngine.benefit_classification(
            "SHORT_TERM", settlement_within_months=12)
        assert r["valid"] is True

    def test_classification_db_valid(self):
        r = EmployeeBenefitsEngine.benefit_classification(
            "POST_EMPLOYMENT_DEFINED_BENEFIT")
        assert r["valid"] is True

    def test_classification_unknown_rule6(self):
        r = EmployeeBenefitsEngine.benefit_classification("WEIRD")
        assert r["valid"] is False

    def test_dbo_pv_basic(self):
        r = EmployeeBenefitsEngine.db_obligation_pv(
            [(1, Decimal("1000000"))], Decimal("5"))
        pv = Decimal(r["dbo_pv"])
        assert pv > Decimal("952000") and pv < Decimal("953000")

    def test_dbo_pv_multi_year(self):
        r = EmployeeBenefitsEngine.db_obligation_pv(
            [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("5"))
        pv = Decimal(r["dbo_pv"])
        assert pv > Decimal("1850000") and pv < Decimal("1865000")

    def test_dbo_pv_zero_rate(self):
        r = EmployeeBenefitsEngine.db_obligation_pv(
            [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("0"))
        assert r["dbo_pv"] == "2000000.00"

    def test_dbo_pv_missing_rate_rule1(self):
        r = EmployeeBenefitsEngine.db_obligation_pv(
            [(1, Decimal("1000000"))], None)
        assert r["dbo_pv"] is None

    def test_dbo_pv_negative_rate_rule6(self):
        r = EmployeeBenefitsEngine.db_obligation_pv(
            [(1, Decimal("1000000"))], Decimal("-5"))
        assert r["computed"] is False

    def test_dbo_pv_empty_payments_rule1(self):
        r = EmployeeBenefitsEngine.db_obligation_pv([], Decimal("5"))
        assert r["dbo_pv"] is None

    def test_net_liability_basic(self):
        r = EmployeeBenefitsEngine.net_db_liability(
            Decimal("10000000"), Decimal("8000000"))
        assert r["net_position"] == "2000000.00"
        assert r["is_liability"] is True

    def test_net_asset_position(self):
        r = EmployeeBenefitsEngine.net_db_liability(
            Decimal("8000000"), Decimal("10000000"))
        assert r["net_position"] == "-2000000.00"

    def test_asset_ceiling_applied(self):
        r = EmployeeBenefitsEngine.net_db_liability(
            Decimal("8000000"), Decimal("12000000"),
            asset_ceiling=Decimal("1000000"))
        assert r["asset_ceiling_applied"] is True
        assert r["net_position"] == "-1000000.00"

    def test_net_liability_missing_rule1(self):
        r = EmployeeBenefitsEngine.net_db_liability(None, Decimal("8000000"))
        assert r["net_position"] is None

    def test_net_interest_liability_expense(self):
        r = EmployeeBenefitsEngine.net_interest(Decimal("2000000"), Decimal("5"))
        assert r["net_interest"] == "100000.00"
        assert r["is_expense"] is True

    def test_net_interest_asset_income(self):
        r = EmployeeBenefitsEngine.net_interest(Decimal("-2000000"), Decimal("5"))
        assert r["net_interest"] == "-100000.00"
        assert r["is_income"] is True

    def test_net_interest_missing_rule1(self):
        r = EmployeeBenefitsEngine.net_interest(None, Decimal("5"))
        assert r["computed"] is False

    def test_net_interest_negative_rate_rule6(self):
        r = EmployeeBenefitsEngine.net_interest(Decimal("2000000"), Decimal("-5"))
        assert r["computed"] is False

    def test_service_cost_current_only(self):
        r = EmployeeBenefitsEngine.service_cost(Decimal("500000"))
        assert r["total_service_cost"] == "500000.00"

    def test_service_cost_with_past(self):
        r = EmployeeBenefitsEngine.service_cost(
            Decimal("500000"), past_service_cost=Decimal("100000"))
        assert r["total_service_cost"] == "600000.00"

    def test_service_cost_with_all_components(self):
        r = EmployeeBenefitsEngine.service_cost(
            Decimal("500000"), Decimal("100000"), Decimal("50000"))
        assert r["total_service_cost"] == "650000.00"

    def test_service_cost_missing_current_rule1(self):
        r = EmployeeBenefitsEngine.service_cost(None, Decimal("100000"))
        assert r["computed"] is False

    def test_remeasurement_split_basic(self):
        r = EmployeeBenefitsEngine.remeasurement_split(
            Decimal("100000"), Decimal("600000"), Decimal("500000"))
        assert r["asset_return_oci_component"] == "100000.00"
        assert r["oci_total"] == "200000.00"

    def test_remeasurement_actuarial_gain_negative(self):
        r = EmployeeBenefitsEngine.remeasurement_split(
            Decimal("-50000"), Decimal("100000"), Decimal("100000"))
        assert r["asset_return_oci_component"] == "0.00"
        assert r["oci_total"] == "-50000.00"

    def test_remeasurement_missing_rule1(self):
        r = EmployeeBenefitsEngine.remeasurement_split(
            None, Decimal("100000"), Decimal("100000"))
        assert r["computed"] is False

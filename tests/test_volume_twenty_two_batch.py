"""
================================================================================
A2Z MIS 360 — Volume Twenty-Two Batch Tests (Standards #105-#108)
================================================================================

Tests Standards #105 IAS 36 Impairment, #106 IAS 12 Deferred Tax,
#107 IFRS 15 Revenue Recognition, #108 IAS 33 Earnings Per Share.

Total: 122 unit tests covering: recoverable amount = max(VIU, FVLCD); impairment
loss; goodwill reversal prohibition; temporary differences (taxable vs deductible);
DTA recoverability; 5-step IFRS 15 model with contract criteria + performance
obligations + transaction price + allocation + recognition pattern; basic and
diluted EPS with treasury stock method + if-converted method + anti-dilutive rejection.

Run via:
    pytest tests/test_volume_twenty_two_batch.py -v
================================================================================
"""

from __future__ import annotations

from decimal import Decimal

from utils.asset_impairment import (
    ImpairmentEngine,
    RECOVERABLE_AMOUNT_BASES, IMPAIRMENT_INDICATORS_EXTERNAL,
    IMPAIRMENT_INDICATORS_INTERNAL, ASSET_TEST_FREQUENCIES,
    ASSET_GROUPINGS, GOODWILL_REVERSAL_PROHIBITED,
    OTHER_ASSET_REVERSAL_ALLOWED,
)
from utils.deferred_tax import (
    DeferredTaxEngine,
    TEMPORARY_DIFFERENCE_TYPES, COMMON_TEMPORARY_DIFFERENCE_SOURCES,
    DEFERRED_TAX_RECOGNITION_OUTCOMES, PROFIT_OR_LOSS_ALLOCATION_BUCKETS,
    EXEMPTIONS_FROM_RECOGNITION,
)
from utils.revenue_recognition import (
    RevenueRecognitionEngine,
    IFRS_15_STEPS, CONTRACT_CRITERIA, RECOGNITION_PATTERNS,
    OVER_TIME_CRITERIA, INDICATORS_OF_CONTROL_TRANSFER,
    VARIABLE_CONSIDERATION_TYPES, CONTRACT_MODIFICATION_TYPES,
)
from utils.earnings_per_share import (
    EarningsPerShareEngine,
    EPS_TYPES, SHARE_TRANSACTION_TYPES, POTENTIAL_ORDINARY_SHARE_TYPES,
    DILUTION_OUTCOMES, EPS_PRESENTATION_REQUIREMENTS,
)


# ============================================================================
# #105 IAS 36 Impairment (32)
# ============================================================================

class TestAssetImpairment:

    def test_recoverable_bases_byte_for_byte(self):
        for b in ("VALUE_IN_USE", "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL", "HIGHER_OF"):
            assert b in RECOVERABLE_AMOUNT_BASES
        assert len(RECOVERABLE_AMOUNT_BASES) == 3

    def test_external_indicators_byte_for_byte(self):
        for i in ("MARKET_VALUE_DECLINE_SIGNIFICANT", "ADVERSE_TECHNOLOGY_CHANGES",
                  "ADVERSE_MARKET_CHANGES", "ADVERSE_LEGAL_CHANGES",
                  "INTEREST_RATE_INCREASE", "NET_ASSETS_EXCEED_MARKET_CAP",
                  "ECONOMIC_DOWNTURN"):
            assert i in IMPAIRMENT_INDICATORS_EXTERNAL
        assert len(IMPAIRMENT_INDICATORS_EXTERNAL) == 7

    def test_internal_indicators_byte_for_byte(self):
        for i in ("PHYSICAL_DAMAGE", "OBSOLESCENCE", "ASSET_HELD_FOR_DISPOSAL_PLAN",
                  "PERFORMANCE_DECLINE", "RESTRUCTURING_PLAN"):
            assert i in IMPAIRMENT_INDICATORS_INTERNAL
        assert len(IMPAIRMENT_INDICATORS_INTERNAL) == 5

    def test_test_frequencies_byte_for_byte(self):
        for f in ("ANNUAL_MANDATORY", "ANNUAL_IF_INDICATOR", "AT_INDICATOR_TRIGGER"):
            assert f in ASSET_TEST_FREQUENCIES

    def test_asset_groupings_byte_for_byte(self):
        for g in ("INDIVIDUAL_ASSET", "CASH_GENERATING_UNIT"):
            assert g in ASSET_GROUPINGS

    def test_goodwill_reversal_prohibited_byte_for_byte(self):
        assert GOODWILL_REVERSAL_PROHIBITED is True

    def test_viu_basic(self):
        r = ImpairmentEngine.value_in_use_pv(
            [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("5"))
        viu = Decimal(r["viu"])
        assert viu > Decimal("1850000") and viu < Decimal("1865000")

    def test_viu_zero_rate(self):
        r = ImpairmentEngine.value_in_use_pv(
            [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("0"))
        assert r["viu"] == "2000000.00"

    def test_viu_missing_rate_rule1(self):
        r = ImpairmentEngine.value_in_use_pv([(1, Decimal("1000000"))], None)
        assert r["viu"] is None

    def test_viu_negative_rate_rule6(self):
        r = ImpairmentEngine.value_in_use_pv(
            [(1, Decimal("1000000"))], Decimal("-5"))
        assert r["computed"] is False

    def test_viu_empty_flows_rule1(self):
        r = ImpairmentEngine.value_in_use_pv([], Decimal("5"))
        assert r["viu"] is None

    def test_recoverable_amount_higher_of_viu(self):
        r = ImpairmentEngine.recoverable_amount(
            Decimal("1000000"), Decimal("800000"))
        assert r["recoverable_amount"] == "1000000.00"
        assert r["basis"] == "VALUE_IN_USE"

    def test_recoverable_amount_higher_of_fvlcd(self):
        r = ImpairmentEngine.recoverable_amount(
            Decimal("800000"), Decimal("1000000"))
        assert r["recoverable_amount"] == "1000000.00"
        assert r["basis"] == "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL"

    def test_recoverable_amount_only_viu(self):
        r = ImpairmentEngine.recoverable_amount(Decimal("1000000"), None)
        assert r["recoverable_amount"] == "1000000.00"

    def test_recoverable_amount_only_fvlcd(self):
        r = ImpairmentEngine.recoverable_amount(None, Decimal("800000"))
        assert r["recoverable_amount"] == "800000.00"

    def test_recoverable_amount_both_missing_rule1(self):
        r = ImpairmentEngine.recoverable_amount(None, None)
        assert r["recoverable_amount"] is None

    def test_impairment_loss_basic(self):
        r = ImpairmentEngine.impairment_loss(
            Decimal("1200000"), Decimal("1000000"))
        assert r["impairment_loss"] == "200000.00"
        assert r["impaired"] is True

    def test_impairment_loss_no_loss(self):
        r = ImpairmentEngine.impairment_loss(
            Decimal("800000"), Decimal("1000000"))
        assert r["impaired"] is False

    def test_impairment_loss_equal(self):
        r = ImpairmentEngine.impairment_loss(
            Decimal("1000000"), Decimal("1000000"))
        assert r["impaired"] is False

    def test_impairment_loss_missing_rule1(self):
        r = ImpairmentEngine.impairment_loss(None, Decimal("1000000"))
        assert r["impairment_loss"] is None

    def test_impairment_loss_negative_ca_rule6(self):
        r = ImpairmentEngine.impairment_loss(
            Decimal("-100"), Decimal("1000000"))
        assert r["computed"] is False

    def test_indicator_external_valid(self):
        r = ImpairmentEngine.validate_impairment_indicator("INTEREST_RATE_INCREASE")
        assert r["valid"] is True
        assert r["category"] == "EXTERNAL"

    def test_indicator_internal_valid(self):
        r = ImpairmentEngine.validate_impairment_indicator("PHYSICAL_DAMAGE")
        assert r["valid"] is True
        assert r["category"] == "INTERNAL"

    def test_indicator_unknown_rule6(self):
        r = ImpairmentEngine.validate_impairment_indicator("WEIRD")
        assert r["valid"] is False

    def test_cgu_individual(self):
        assert ImpairmentEngine.cgu_classification(True) == "INDIVIDUAL_ASSET"

    def test_cgu_grouped(self):
        assert ImpairmentEngine.cgu_classification(False) == "CASH_GENERATING_UNIT"

    def test_cgu_missing_rule1(self):
        assert ImpairmentEngine.cgu_classification(None) is None

    def test_reversal_goodwill_prohibited(self):
        r = ImpairmentEngine.reversal_eligibility("GOODWILL")
        assert r["reversal_allowed"] is False

    def test_reversal_tangible_allowed(self):
        r = ImpairmentEngine.reversal_eligibility("TANGIBLE_ASSET")
        assert r["reversal_allowed"] is True

    def test_reversal_intangible_allowed(self):
        r = ImpairmentEngine.reversal_eligibility("INTANGIBLE_ASSET")
        assert r["reversal_allowed"] is True

    def test_reversal_cgu_allowed(self):
        r = ImpairmentEngine.reversal_eligibility("CASH_GENERATING_UNIT")
        assert r["reversal_allowed"] is True

    def test_reversal_unknown_default_conservative(self):
        r = ImpairmentEngine.reversal_eligibility("WEIRD")
        assert r["reversal_allowed"] is False


# ============================================================================
# #106 IAS 12 Deferred Tax (30)
# ============================================================================

class TestDeferredTax:

    def test_td_types_byte_for_byte(self):
        for t in ("TAXABLE", "DEDUCTIBLE", "NIL"):
            assert t in TEMPORARY_DIFFERENCE_TYPES
        assert len(TEMPORARY_DIFFERENCE_TYPES) == 3

    def test_td_sources_byte_for_byte(self):
        for s in ("DEPRECIATION_DIFFERENCE", "PROVISION_TIMING",
                  "REVALUATION_GAIN", "UNREALISED_GAIN_LOSS",
                  "LOSS_CARRYFORWARD"):
            assert s in COMMON_TEMPORARY_DIFFERENCE_SOURCES
        assert len(COMMON_TEMPORARY_DIFFERENCE_SOURCES) == 5

    def test_recognition_outcomes_byte_for_byte(self):
        for o in ("RECOGNISE_FULLY", "RECOGNISE_PARTIALLY", "DO_NOT_RECOGNISE"):
            assert o in DEFERRED_TAX_RECOGNITION_OUTCOMES

    def test_allocation_buckets_byte_for_byte(self):
        for b in ("P_AND_L", "OCI"):
            assert b in PROFIT_OR_LOSS_ALLOCATION_BUCKETS

    def test_exemptions_byte_for_byte(self):
        for e in ("INITIAL_RECOGNITION_GOODWILL",
                  "INITIAL_RECOGNITION_TXN_NOT_BUSINESS_COMBINATION",
                  "INITIAL_RECOGNITION_NO_PNL_OR_TAX_IMPACT",
                  "INVESTMENT_IN_SUBSIDIARY_PARENT_CONTROLS",
                  "DISTRIBUTABLE_PROFITS_TIMING"):
            assert e in EXEMPTIONS_FROM_RECOGNITION
        assert len(EXEMPTIONS_FROM_RECOGNITION) == 5

    def test_temporary_difference_taxable(self):
        r = DeferredTaxEngine.temporary_difference(
            Decimal("1000000"), Decimal("800000"))
        assert r["temporary_difference"] == "200000"

    def test_temporary_difference_deductible(self):
        r = DeferredTaxEngine.temporary_difference(
            Decimal("800000"), Decimal("1000000"))
        assert r["temporary_difference"] == "-200000"

    def test_temporary_difference_nil(self):
        r = DeferredTaxEngine.temporary_difference(
            Decimal("1000000"), Decimal("1000000"))
        assert r["temporary_difference"] == "0"

    def test_temporary_difference_missing_rule1(self):
        r = DeferredTaxEngine.temporary_difference(None, Decimal("1000000"))
        assert r["temporary_difference"] is None

    def test_classify_taxable(self):
        assert DeferredTaxEngine.classify_temporary_difference(
            Decimal("200000")) == "TAXABLE"

    def test_classify_deductible(self):
        assert DeferredTaxEngine.classify_temporary_difference(
            Decimal("-200000")) == "DEDUCTIBLE"

    def test_classify_nil(self):
        assert DeferredTaxEngine.classify_temporary_difference(
            Decimal("0")) == "NIL"

    def test_classify_missing_rule1(self):
        assert DeferredTaxEngine.classify_temporary_difference(None) is None

    def test_deferred_tax_dtl(self):
        r = DeferredTaxEngine.deferred_tax(Decimal("200000"), Decimal("30"))
        assert r["deferred_tax"] == "60000.00"
        assert r["classification"] == "DEFERRED_TAX_LIABILITY"

    def test_deferred_tax_dta(self):
        r = DeferredTaxEngine.deferred_tax(Decimal("-200000"), Decimal("30"))
        assert r["deferred_tax"] == "-60000.00"
        assert r["classification"] == "DEFERRED_TAX_ASSET"

    def test_deferred_tax_nil(self):
        r = DeferredTaxEngine.deferred_tax(Decimal("0"), Decimal("30"))
        assert r["deferred_tax"] == "0.00"

    def test_deferred_tax_missing_rule1(self):
        r = DeferredTaxEngine.deferred_tax(None, Decimal("30"))
        assert r["deferred_tax"] is None

    def test_deferred_tax_negative_rate_rule6(self):
        r = DeferredTaxEngine.deferred_tax(Decimal("200000"), Decimal("-5"))
        assert r["computed"] is False

    def test_dta_recoverability_full(self):
        r = DeferredTaxEngine.dta_recoverability(
            Decimal("-100000"), Decimal("200000"))
        assert r["recognition"] == "RECOGNISE_FULLY"

    def test_dta_recoverability_partial(self):
        r = DeferredTaxEngine.dta_recoverability(
            Decimal("-200000"), Decimal("50000"))
        assert r["recognition"] == "RECOGNISE_PARTIALLY"

    def test_dta_recoverability_no_profit(self):
        r = DeferredTaxEngine.dta_recoverability(
            Decimal("-100000"), Decimal("0"))
        assert r["recognition"] == "DO_NOT_RECOGNISE"

    def test_dta_recoverability_no_evidence(self):
        r = DeferredTaxEngine.dta_recoverability(Decimal("-100000"), None)
        assert r["recognition"] == "DO_NOT_RECOGNISE"

    def test_dta_recoverability_missing_td_rule1(self):
        r = DeferredTaxEngine.dta_recoverability(None, Decimal("100000"))
        assert r["computed"] is False

    def test_current_tax_basic(self):
        r = DeferredTaxEngine.current_tax_expense(
            Decimal("1000000"), Decimal("30"))
        assert r["current_tax"] == "300000.00"

    def test_current_tax_loss_position(self):
        r = DeferredTaxEngine.current_tax_expense(
            Decimal("-500000"), Decimal("30"))
        assert r["current_tax"] == "0.00"
        assert r["tax_loss_position"] is True

    def test_current_tax_missing_rule1(self):
        r = DeferredTaxEngine.current_tax_expense(None, Decimal("30"))
        assert r["current_tax"] is None

    def test_current_tax_negative_rate_rule6(self):
        r = DeferredTaxEngine.current_tax_expense(
            Decimal("1000000"), Decimal("-30"))
        assert r["computed"] is False

    def test_total_tax_expense_basic(self):
        r = DeferredTaxEngine.total_tax_expense(
            Decimal("300000"), Decimal("50000"))
        assert r["total_tax_expense_pnl"] == "350000.00"

    def test_total_tax_expense_with_oci(self):
        r = DeferredTaxEngine.total_tax_expense(
            Decimal("300000"), Decimal("50000"), Decimal("20000"))
        assert r["deferred_tax_oci_separate"] == "20000.00"

    def test_total_tax_expense_missing_rule1(self):
        r = DeferredTaxEngine.total_tax_expense(None, Decimal("50000"))
        assert r["computed"] is False


# ============================================================================
# #107 IFRS 15 Revenue (28)
# ============================================================================

class TestRevenueRecognition:

    def test_steps_byte_for_byte(self):
        for s in ("IDENTIFY_CONTRACT", "IDENTIFY_PERFORMANCE_OBLIGATIONS",
                  "DETERMINE_TRANSACTION_PRICE", "ALLOCATE_TRANSACTION_PRICE",
                  "RECOGNISE_REVENUE"):
            assert s in IFRS_15_STEPS
        assert len(IFRS_15_STEPS) == 5

    def test_contract_criteria_byte_for_byte(self):
        for c in ("PARTIES_APPROVED", "RIGHTS_IDENTIFIABLE",
                  "PAYMENT_TERMS_IDENTIFIABLE", "COMMERCIAL_SUBSTANCE",
                  "COLLECTION_PROBABLE"):
            assert c in CONTRACT_CRITERIA
        assert len(CONTRACT_CRITERIA) == 5

    def test_recognition_patterns_byte_for_byte(self):
        for p in ("POINT_IN_TIME", "OVER_TIME"):
            assert p in RECOGNITION_PATTERNS

    def test_over_time_criteria_byte_for_byte(self):
        for c in ("CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS",
                  "PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET",
                  "NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT"):
            assert c in OVER_TIME_CRITERIA
        assert len(OVER_TIME_CRITERIA) == 3

    def test_control_indicators_byte_for_byte(self):
        for i in ("PRESENT_RIGHT_TO_PAYMENT", "LEGAL_TITLE_TRANSFERRED",
                  "PHYSICAL_POSSESSION_TRANSFERRED",
                  "SIGNIFICANT_RISKS_AND_REWARDS_TRANSFERRED",
                  "CUSTOMER_ACCEPTANCE"):
            assert i in INDICATORS_OF_CONTROL_TRANSFER
        assert len(INDICATORS_OF_CONTROL_TRANSFER) == 5

    def test_variable_consideration_types_byte_for_byte(self):
        for t in ("DISCOUNT", "REBATE", "REFUND_OR_RETURN"):
            assert t in VARIABLE_CONSIDERATION_TYPES

    def test_modification_types_byte_for_byte(self):
        for m in ("SEPARATE_CONTRACT", "TERMINATION_AND_NEW",
                  "CUMULATIVE_CATCH_UP"):
            assert m in CONTRACT_MODIFICATION_TYPES

    def test_identify_contract_all_met(self):
        r = RevenueRecognitionEngine.identify_contract({
            "PARTIES_APPROVED": True,
            "RIGHTS_IDENTIFIABLE": True,
            "PAYMENT_TERMS_IDENTIFIABLE": True,
            "COMMERCIAL_SUBSTANCE": True,
            "COLLECTION_PROBABLE": True,
        })
        assert r["contract_recognised"] is True

    def test_identify_contract_collection_not_probable_rule6(self):
        r = RevenueRecognitionEngine.identify_contract({
            "PARTIES_APPROVED": True, "RIGHTS_IDENTIFIABLE": True,
            "PAYMENT_TERMS_IDENTIFIABLE": True, "COMMERCIAL_SUBSTANCE": True,
            "COLLECTION_PROBABLE": False,
        })
        assert r["contract_recognised"] is False

    def test_identify_contract_all_missing(self):
        r = RevenueRecognitionEngine.identify_contract({})
        assert r["contract_recognised"] is False
        assert len(r["criteria_missing_or_false"]) == 5

    def test_identify_performance_obligations_basic(self):
        r = RevenueRecognitionEngine.identify_performance_obligations([
            {"id": "PO1", "is_distinct": True},
            {"id": "PO2", "is_distinct": True},
            {"id": "PO3", "is_distinct": False},
        ])
        assert r["distinct_count"] == 2

    def test_identify_performance_obligations_empty(self):
        r = RevenueRecognitionEngine.identify_performance_obligations([])
        assert r["computed"] is False

    def test_transaction_price_basic(self):
        r = RevenueRecognitionEngine.determine_transaction_price(
            Decimal("1000000"), Decimal("100000"))
        assert r["transaction_price"] == "1100000.00"

    def test_transaction_price_with_payable(self):
        r = RevenueRecognitionEngine.determine_transaction_price(
            Decimal("1000000"),
            consideration_payable_to_customer=Decimal("50000"))
        assert r["transaction_price"] == "950000.00"

    def test_transaction_price_missing_rule1(self):
        r = RevenueRecognitionEngine.determine_transaction_price(None)
        assert r["transaction_price"] is None

    def test_allocate_transaction_price_basic(self):
        r = RevenueRecognitionEngine.allocate_transaction_price(
            Decimal("1000000"),
            {"PO1": Decimal("600"), "PO2": Decimal("400")})
        assert r["allocations"]["PO1"] == "600000.00"
        assert r["allocations"]["PO2"] == "400000.00"

    def test_allocate_transaction_price_proportional(self):
        r = RevenueRecognitionEngine.allocate_transaction_price(
            Decimal("900000"),
            {"PO1": Decimal("500"), "PO2": Decimal("500"), "PO3": Decimal("500")})
        assert r["allocations"]["PO1"] == "300000.00"

    def test_allocate_missing_tp_rule1(self):
        r = RevenueRecognitionEngine.allocate_transaction_price(
            None, {"PO1": Decimal("100")})
        assert r["allocations"] is None

    def test_allocate_empty_ssp_rule1(self):
        r = RevenueRecognitionEngine.allocate_transaction_price(
            Decimal("1000000"), {})
        assert r["allocations"] is None

    def test_recognition_pattern_over_time_one_criterion(self):
        r = RevenueRecognitionEngine.revenue_recognition_pattern({
            "CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS": True,
        })
        assert r["pattern"] == "OVER_TIME"

    def test_recognition_pattern_point_in_time(self):
        r = RevenueRecognitionEngine.revenue_recognition_pattern({
            "CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS": False,
            "PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET": False,
            "NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT": False,
        })
        assert r["pattern"] == "POINT_IN_TIME"

    def test_recognition_pattern_default_empty(self):
        r = RevenueRecognitionEngine.revenue_recognition_pattern({})
        assert r["pattern"] == "POINT_IN_TIME"

    def test_modification_separate_contract_valid(self):
        r = RevenueRecognitionEngine.validate_contract_modification(
            "SEPARATE_CONTRACT", is_distinct=True, is_standalone_price=True)
        assert r["valid"] is True

    def test_modification_separate_contract_inconsistent(self):
        r = RevenueRecognitionEngine.validate_contract_modification(
            "SEPARATE_CONTRACT", is_distinct=True, is_standalone_price=False)
        assert r["valid"] is False

    def test_modification_termination_valid(self):
        r = RevenueRecognitionEngine.validate_contract_modification(
            "TERMINATION_AND_NEW", is_distinct=True, is_standalone_price=False)
        assert r["valid"] is True

    def test_modification_termination_inconsistent(self):
        r = RevenueRecognitionEngine.validate_contract_modification(
            "TERMINATION_AND_NEW", is_distinct=True, is_standalone_price=True)
        assert r["valid"] is False

    def test_modification_cumulative_catchup_valid(self):
        r = RevenueRecognitionEngine.validate_contract_modification(
            "CUMULATIVE_CATCH_UP", is_distinct=False)
        assert r["valid"] is True

    def test_modification_unknown_rule6(self):
        r = RevenueRecognitionEngine.validate_contract_modification("WEIRD")
        assert r["valid"] is False


# ============================================================================
# #108 IAS 33 EPS (32)
# ============================================================================

class TestEarningsPerShare:

    def test_eps_types_byte_for_byte(self):
        for t in ("BASIC", "DILUTED", "CONTINUING_OPERATIONS"):
            assert t in EPS_TYPES

    def test_share_transactions_byte_for_byte(self):
        for t in ("ISSUANCE", "BUYBACK", "BONUS_OR_SPLIT"):
            assert t in SHARE_TRANSACTION_TYPES

    def test_pos_types_byte_for_byte(self):
        for t in ("CONVERTIBLE_BONDS", "CONVERTIBLE_PREFERRED_SHARES",
                  "SHARE_OPTIONS_WARRANTS", "CONTINGENTLY_ISSUABLE_SHARES"):
            assert t in POTENTIAL_ORDINARY_SHARE_TYPES
        assert len(POTENTIAL_ORDINARY_SHARE_TYPES) == 4

    def test_dilution_outcomes_byte_for_byte(self):
        for o in ("DILUTIVE", "ANTI_DILUTIVE"):
            assert o in DILUTION_OUTCOMES

    def test_presentation_byte_for_byte(self):
        for p in ("FACE_OF_INCOME_STATEMENT", "NOTES_RECONCILIATION",
                  "CONTINUING_AND_DISCONTINUED_SEPARATE"):
            assert p in EPS_PRESENTATION_REQUIREMENTS

    def test_wans_no_transactions(self):
        r = EarningsPerShareEngine.weighted_avg_shares(
            Decimal("1000000"), [], period_days=365)
        assert r["wans"] == "1000000.00"

    def test_wans_issuance_mid_year(self):
        r = EarningsPerShareEngine.weighted_avg_shares(
            Decimal("1000000"),
            [("ISSUANCE", 182, Decimal("100000"))],
            period_days=365)
        wans = Decimal(r["wans"])
        assert wans > Decimal("1050000") and wans < Decimal("1051000")

    def test_wans_buyback(self):
        r = EarningsPerShareEngine.weighted_avg_shares(
            Decimal("1000000"),
            [("BUYBACK", 182, Decimal("100000"))],
            period_days=365)
        wans = Decimal(r["wans"])
        assert wans < Decimal("1000000") and wans > Decimal("949000")

    def test_wans_bonus_retrospective(self):
        r = EarningsPerShareEngine.weighted_avg_shares(
            Decimal("1000000"),
            [("BONUS_OR_SPLIT", 100, Decimal("200000"))],
            period_days=365)
        assert r["wans"] == "1200000.00"

    def test_wans_missing_rule1(self):
        r = EarningsPerShareEngine.weighted_avg_shares(None, [], 365)
        assert r["wans"] is None

    def test_wans_negative_rule6(self):
        r = EarningsPerShareEngine.weighted_avg_shares(Decimal("-100"), [], 365)
        assert r["computed"] is False

    def test_basic_eps_basic(self):
        r = EarningsPerShareEngine.basic_eps(
            Decimal("1000000"), Decimal("500000"))
        assert r["basic_eps"] == "2.0000"

    def test_basic_eps_with_preferred(self):
        r = EarningsPerShareEngine.basic_eps(
            Decimal("1000000"), Decimal("500000"), Decimal("100000"))
        assert r["basic_eps"] == "1.8000"

    def test_basic_eps_loss(self):
        r = EarningsPerShareEngine.basic_eps(
            Decimal("-500000"), Decimal("500000"))
        assert r["basic_eps"] == "-1.0000"

    def test_basic_eps_missing_rule1(self):
        r = EarningsPerShareEngine.basic_eps(None, Decimal("500000"))
        assert r["basic_eps"] is None

    def test_basic_eps_zero_shares_rule1(self):
        r = EarningsPerShareEngine.basic_eps(Decimal("1000000"), Decimal("0"))
        assert r["basic_eps"] is None

    def test_treasury_stock_method_dilutive(self):
        r = EarningsPerShareEngine.treasury_stock_method(
            Decimal("100000"), Decimal("10"), Decimal("20"))
        assert r["net_dilutive_shares"] == "50000.00"
        assert r["outcome"] == "DILUTIVE"

    def test_treasury_stock_method_anti_dilutive(self):
        r = EarningsPerShareEngine.treasury_stock_method(
            Decimal("100000"), Decimal("20"), Decimal("15"))
        assert r["outcome"] == "ANTI_DILUTIVE"

    def test_treasury_stock_method_at_money_anti_dilutive(self):
        r = EarningsPerShareEngine.treasury_stock_method(
            Decimal("100000"), Decimal("20"), Decimal("20"))
        assert r["outcome"] == "ANTI_DILUTIVE"

    def test_treasury_stock_method_missing_rule1(self):
        r = EarningsPerShareEngine.treasury_stock_method(
            None, Decimal("10"), Decimal("20"))
        assert r["net_dilutive_shares"] is None

    def test_if_converted_dilutive(self):
        r = EarningsPerShareEngine.if_converted_method(
            Decimal("1000000"), Decimal("500000"),
            Decimal("50000"), Decimal("100000"))
        assert r["outcome"] == "DILUTIVE"

    def test_if_converted_anti_dilutive(self):
        r = EarningsPerShareEngine.if_converted_method(
            Decimal("100000"), Decimal("100000"),
            Decimal("500000"), Decimal("10000"))
        assert r["outcome"] == "ANTI_DILUTIVE"

    def test_if_converted_missing_rule1(self):
        r = EarningsPerShareEngine.if_converted_method(
            None, Decimal("500000"), Decimal("50000"), Decimal("100000"))
        assert r["computed"] is False

    def test_diluted_eps_basic(self):
        r = EarningsPerShareEngine.diluted_eps(
            Decimal("1000000"), Decimal("500000"),
            dilutive_potential_shares=Decimal("100000"))
        assert r["diluted_eps"] == "1.6667"

    def test_diluted_eps_with_adjustments(self):
        r = EarningsPerShareEngine.diluted_eps(
            Decimal("1000000"), Decimal("500000"),
            dilutive_potential_shares=Decimal("100000"),
            adjustments_to_numerator=Decimal("50000"))
        assert r["diluted_eps"] == "1.7500"

    def test_diluted_eps_with_preferred(self):
        r = EarningsPerShareEngine.diluted_eps(
            Decimal("1000000"), Decimal("500000"),
            dilutive_potential_shares=Decimal("100000"),
            preferred_dividends=Decimal("100000"))
        assert r["diluted_eps"] == "1.5000"

    def test_diluted_eps_anti_dilutive_rejected_rule6(self):
        r = EarningsPerShareEngine.diluted_eps(
            Decimal("1000000"), Decimal("500000"),
            dilutive_potential_shares=Decimal("100000"),
            adjustments_to_numerator=Decimal("1000000"))
        assert r["computed"] is False

    def test_diluted_eps_no_pos_equals_basic(self):
        r = EarningsPerShareEngine.diluted_eps(
            Decimal("1000000"), Decimal("500000"))
        assert r["diluted_eps"] == "2.0000"

    def test_dilutive_classification_dilutive(self):
        assert EarningsPerShareEngine.dilutive_securities_classification(
            Decimal("2"), Decimal("1.50")) == "DILUTIVE"

    def test_dilutive_classification_anti_dilutive(self):
        assert EarningsPerShareEngine.dilutive_securities_classification(
            Decimal("2"), Decimal("2.50")) == "ANTI_DILUTIVE"

    def test_dilutive_classification_equal_anti_dilutive(self):
        assert EarningsPerShareEngine.dilutive_securities_classification(
            Decimal("2"), Decimal("2")) == "ANTI_DILUTIVE"

    def test_dilutive_classification_missing_rule1(self):
        assert EarningsPerShareEngine.dilutive_securities_classification(
            None, Decimal("2")) is None

"""
================================================================================
A2Z MIS 360 — Volume Fifteen Batch Tests (Standards #77-#80 Capital/Returns)
================================================================================

Tests Standards #77 Capital Adequacy, #78 RWA, #79 Stress Testing,
#80 Regulatory Returns.

Total: 68 unit tests covering Basel III + CBK PG/02 capital ratios,
       Basel Standardised Approach RWA + BIA operational risk, supervisory
       stress scenarios + reverse stress, and CBK BSD return generation.

Run via:
    pytest tests/test_volume_fifteen_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.capital_adequacy import (
    CapitalAdequacyEngine, CapitalComponents,
    BASEL_CET1_MIN_PCT, BASEL_TIER1_MIN_PCT, BASEL_TOTAL_CAR_MIN_PCT,
    CBK_CET1_MIN_PCT, CBK_TIER1_MIN_PCT, CBK_TOTAL_CAR_MIN_PCT,
    CAPITAL_CONSERVATION_BUFFER_PCT, COUNTERCYCLICAL_BUFFER_MAX_PCT,
    DSIB_BUFFER_MIN_PCT, DSIB_BUFFER_MAX_PCT, LEVERAGE_RATIO_MIN_PCT,
)
from utils.risk_weighted_assets import (
    RwaEngine, CreditExposure, GrossIncomeYear,
    CREDIT_RISK_WEIGHTS_PCT, CCF_PCT,
    BIA_ALPHA_PCT, RWA_CONVERSION_FACTOR, SA_BETA_PCT,
)
from utils.stress_testing import (
    StressTestingEngine, StressTestInputs,
    STRESS_SCENARIOS, SCENARIO_SHOCKS,
    NPL_INCREASE_TO_LOSS_FACTOR, ASSET_PRICE_SHOCK_TO_PROVISIONS,
)
from utils.regulatory_returns import (
    RegulatoryReturnsEngine, Bsd1Inputs, Bsd2Inputs, Bsd3Inputs,
    LoanForClassification,
    BSD_RETURN_TYPES, RETURN_FREQUENCIES,
    STATUTORY_LIQUIDITY_RATIO_MIN_PCT,
    LOAN_CLASSIFICATIONS, LOAN_CLASSIFICATION_DAYS, LOAN_PROVISION_PCT,
)


# ============================================================================
# #77 Capital Adequacy (16)
# ============================================================================

def _components(**kw):
    defaults = dict(
        paid_up_capital_kes=Decimal("5000000000"),
        share_premium_kes=Decimal("2000000000"),
        retained_earnings_kes=Decimal("3000000000"),
        accumulated_oci_kes=Decimal("500000000"),
        goodwill_kes=Decimal("100000000"),
        deferred_tax_assets_kes=Decimal("50000000"),
        subordinated_debt_kes=Decimal("1000000000"),
        general_provisions_kes=Decimal("200000000"),
    )
    defaults.update(kw)
    return CapitalComponents(**defaults)


class TestCapitalAdequacy:

    def test_basel_minimums_byte_for_byte(self):
        assert BASEL_CET1_MIN_PCT == Decimal("4.5")
        assert BASEL_TIER1_MIN_PCT == Decimal("6.0")
        assert BASEL_TOTAL_CAR_MIN_PCT == Decimal("8.0")

    def test_cbk_minimums_byte_for_byte(self):
        assert CBK_CET1_MIN_PCT == Decimal("10.5")
        assert CBK_TIER1_MIN_PCT == Decimal("12.0")
        assert CBK_TOTAL_CAR_MIN_PCT == Decimal("14.5")

    def test_buffer_constants_byte_for_byte(self):
        assert CAPITAL_CONSERVATION_BUFFER_PCT == Decimal("2.5")
        assert COUNTERCYCLICAL_BUFFER_MAX_PCT == Decimal("2.5")
        assert DSIB_BUFFER_MIN_PCT == Decimal("1.0")
        assert DSIB_BUFFER_MAX_PCT == Decimal("3.5")
        assert LEVERAGE_RATIO_MIN_PCT == Decimal("3.0")

    def test_cet1_basic(self):
        r = CapitalAdequacyEngine.eligible_cet1(_components())
        # 5+2+3+0.5 - 0.1-0.05 = 10.35B
        assert Decimal(r["net_cet1_kes"]) == Decimal("10350000000.00")

    def test_tier2_provisions_capped(self):
        c = _components(general_provisions_kes=Decimal("500000000"))
        r = CapitalAdequacyEngine.eligible_tier2(c, Decimal("10000000000"))
        # Cap = 10B × 1.25% = 125M
        assert Decimal(r["general_provisions_capped_kes"]) == Decimal("125000000.00")

    def test_total_capital_tier2_capped_at_tier1(self):
        c = _components(
            paid_up_capital_kes=Decimal("100000000"),
            share_premium_kes=Decimal("0"),
            retained_earnings_kes=Decimal("0"),
            accumulated_oci_kes=Decimal("0"),
            goodwill_kes=Decimal("0"),
            deferred_tax_assets_kes=Decimal("0"),
            subordinated_debt_kes=Decimal("500000000"),
        )
        r = CapitalAdequacyEngine.total_capital(c, None)
        assert r["tier2_cap_applied"] is True

    def test_car_compliant(self):
        r = CapitalAdequacyEngine.car_ratios(_components(), Decimal("50000000000"))
        assert r["compliant_cbk"] is True

    def test_car_breach(self):
        c = _components(
            paid_up_capital_kes=Decimal("1000000000"),
            share_premium_kes=Decimal("0"),
            retained_earnings_kes=Decimal("0"),
            accumulated_oci_kes=Decimal("0"),
            goodwill_kes=Decimal("0"),
            deferred_tax_assets_kes=Decimal("0"),
            subordinated_debt_kes=Decimal("0"),
            general_provisions_kes=Decimal("0"),
        )
        r = CapitalAdequacyEngine.car_ratios(c, Decimal("100000000000"))
        assert r["status"] == "RED"

    def test_car_zero_rwa_rule1(self):
        r = CapitalAdequacyEngine.car_ratios(_components(), Decimal("0"))
        assert r["total_car_pct"] is None

    def test_leverage_ratio_compliant(self):
        r = CapitalAdequacyEngine.leverage_ratio(
            Decimal("10000000000"), Decimal("250000000000"))
        assert r["compliant"] is True

    def test_leverage_ratio_breach(self):
        r = CapitalAdequacyEngine.leverage_ratio(
            Decimal("1000000000"), Decimal("100000000000"))
        assert r["compliant"] is False

    def test_leverage_zero_exposures_rule1(self):
        r = CapitalAdequacyEngine.leverage_ratio(Decimal("1000000000"), Decimal("0"))
        assert r["leverage_ratio_pct"] is None

    def test_buffers_met(self):
        r = CapitalAdequacyEngine.capital_buffers(
            Decimal("12.0"),
            countercyclical_pct=Decimal("1.0"),
            dsib_pct=Decimal("1.0"))
        assert r["buffers_met"] is True

    def test_buffers_breach(self):
        r = CapitalAdequacyEngine.capital_buffers(
            Decimal("5.0"),
            countercyclical_pct=Decimal("0.5"))
        assert r["buffers_met"] is False

    def test_buffers_invalid_input(self):
        r = CapitalAdequacyEngine.capital_buffers(
            Decimal("12.0"),
            countercyclical_pct=Decimal("3.0"))  # > max
        assert "error" in r

    def test_cet1_missing_components_rule6(self):
        c = CapitalComponents()
        r = CapitalAdequacyEngine.eligible_cet1(c)
        assert r["missing_core_components_count"] >= 3


# ============================================================================
# #78 RWA (19)
# ============================================================================

def _exp(**kw):
    defaults = dict(exposure_id="E1", asset_class="CORPORATE_UNRATED",
                    exposure_kes=Decimal("100000000"))
    defaults.update(kw)
    return CreditExposure(**defaults)


class TestRWA:

    def test_credit_weights_byte_for_byte(self):
        assert CREDIT_RISK_WEIGHTS_PCT["SOVEREIGN_AAA_TO_AA-"] == Decimal("0")
        assert CREDIT_RISK_WEIGHTS_PCT["CORPORATE_UNRATED"] == Decimal("100")
        assert CREDIT_RISK_WEIGHTS_PCT["MORTGAGE_RESIDENTIAL"] == Decimal("35")
        assert CREDIT_RISK_WEIGHTS_PCT["RETAIL_QUALIFYING"] == Decimal("75")
        assert CREDIT_RISK_WEIGHTS_PCT["PAST_DUE_LT_20PCT_PROVS"] == Decimal("150")
        assert CREDIT_RISK_WEIGHTS_PCT["EQUITY_LISTED"] == Decimal("250")
        assert CREDIT_RISK_WEIGHTS_PCT["EQUITY_PRIVATE"] == Decimal("400")

    def test_ccf_byte_for_byte(self):
        assert CCF_PCT["DIRECT_CREDIT_SUBSTITUTE"] == Decimal("100")
        assert CCF_PCT["TRADE_RELATED_CONTINGENT"] == Decimal("20")
        assert CCF_PCT["COMMITMENTS_GTE_1Y"] == Decimal("50")
        assert CCF_PCT["COMMITMENTS_LT_1Y_REVOCABLE"] == Decimal("0")

    def test_bia_alpha_byte_for_byte(self):
        assert BIA_ALPHA_PCT == Decimal("15")

    def test_rwa_conversion_factor_byte_for_byte(self):
        assert RWA_CONVERSION_FACTOR == Decimal("12.5")

    def test_sa_betas_byte_for_byte(self):
        assert SA_BETA_PCT["CORPORATE_FINANCE"] == Decimal("18")
        assert SA_BETA_PCT["RETAIL_BANKING"] == Decimal("12")
        assert SA_BETA_PCT["COMMERCIAL_BANKING"] == Decimal("15")

    def test_sovereign_aaa_zero(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="SOVEREIGN_AAA_TO_AA-")])
        assert r["total_credit_rwa_kes"] == "0.00"

    def test_corporate_unrated_100pct(self):
        r = RwaEngine.credit_rwa([_exp()])
        assert r["total_credit_rwa_kes"] == "100000000.00"

    def test_mortgage_residential_35pct(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="MORTGAGE_RESIDENTIAL")])
        assert r["total_credit_rwa_kes"] == "35000000.00"

    def test_retail_qualifying_75pct(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="RETAIL_QUALIFYING")])
        assert r["total_credit_rwa_kes"] == "75000000.00"

    def test_past_due_150pct(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="PAST_DUE_LT_20PCT_PROVS")])
        assert r["total_credit_rwa_kes"] == "150000000.00"

    def test_equity_listed_250pct(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="EQUITY_LISTED")])
        assert r["total_credit_rwa_kes"] == "250000000.00"

    def test_equity_private_400pct(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="EQUITY_PRIVATE")])
        assert r["total_credit_rwa_kes"] == "400000000.00"

    def test_off_balance_with_ccf_50pct(self):
        e = _exp(exposure_kes=Decimal("0"),
                off_balance_amount_kes=Decimal("100000000"),
                off_balance_ccf_category="COMMITMENTS_GTE_1Y")
        r = RwaEngine.credit_rwa([e])
        # 100M × 50% × 100% = 50M
        assert r["total_credit_rwa_kes"] == "50000000.00"

    def test_collateral_reduces_ead(self):
        e = _exp(crm_eligible_collateral_kes=Decimal("30000000"))
        r = RwaEngine.credit_rwa([e])
        assert r["total_credit_rwa_kes"] == "70000000.00"

    def test_unknown_asset_class_rule6(self):
        r = RwaEngine.credit_rwa([_exp(asset_class="WEIRD")])
        assert r["excluded_count"] == 1

    def test_bia_15pct_alpha(self):
        history = [GrossIncomeYear(year=y, gross_income_kes=Decimal("1000000000"))
                   for y in range(2023, 2026)]
        r = RwaEngine.operational_rwa_bia(history)
        # 1B × 15% × 12.5 = 1.875B
        assert Decimal(r["operational_rwa_kes"]) == Decimal("1875000000.00")

    def test_bia_negative_year_excluded(self):
        history = [
            GrossIncomeYear(year=2023, gross_income_kes=Decimal("1000000000")),
            GrossIncomeYear(year=2024, gross_income_kes=Decimal("-500000000")),
            GrossIncomeYear(year=2025, gross_income_kes=Decimal("1000000000")),
        ]
        r = RwaEngine.operational_rwa_bia(history)
        assert Decimal(r["operational_rwa_kes"]) == Decimal("1875000000.00")

    def test_market_rwa_basic(self):
        r = RwaEngine.market_rwa(Decimal("100000000"))
        assert r["market_rwa_kes"] == "1250000000.00"

    def test_market_rwa_none_rule1(self):
        r = RwaEngine.market_rwa(None)
        assert r["market_rwa_kes"] is None


# ============================================================================
# #79 Stress Testing (15)
# ============================================================================

def _inputs(**kw):
    defaults = dict(
        starting_total_capital_kes=Decimal("20000000000"),
        starting_rwa_kes=Decimal("100000000000"),
        starting_loan_book_kes=Decimal("80000000000"),
        starting_npl_kes=Decimal("4000000000"),
        starting_securities_kes=Decimal("20000000000"),
        starting_fx_open_position_kes=Decimal("5000000000"),
        annual_pre_tax_profit_kes=Decimal("1500000000"),
        horizon_years=3,
    )
    defaults.update(kw)
    return StressTestInputs(**defaults)


class TestStressTesting:

    def test_scenarios_byte_for_byte(self):
        for s in ("BASELINE", "ADVERSE", "SEVERELY_ADVERSE"):
            assert s in STRESS_SCENARIOS

    def test_baseline_shocks_byte_for_byte(self):
        s = SCENARIO_SHOCKS["BASELINE"]
        assert s["gdp_growth_delta_pp"] == Decimal("0")
        assert s["interest_rate_shock_bps"] == Decimal("0")
        assert s["npl_increase_pct"] == Decimal("0")

    def test_adverse_shocks_byte_for_byte(self):
        s = SCENARIO_SHOCKS["ADVERSE"]
        assert s["gdp_growth_delta_pp"] == Decimal("-3")
        assert s["interest_rate_shock_bps"] == Decimal("200")
        assert s["npl_increase_pct"] == Decimal("30")
        assert s["asset_price_shock_pct"] == Decimal("-15")

    def test_severely_adverse_shocks_byte_for_byte(self):
        s = SCENARIO_SHOCKS["SEVERELY_ADVERSE"]
        assert s["gdp_growth_delta_pp"] == Decimal("-6")
        assert s["interest_rate_shock_bps"] == Decimal("400")
        assert s["npl_increase_pct"] == Decimal("60")
        assert s["asset_price_shock_pct"] == Decimal("-30")
        assert s["fx_devaluation_pct"] == Decimal("15")

    def test_factor_constants_byte_for_byte(self):
        assert NPL_INCREASE_TO_LOSS_FACTOR == Decimal("0.45")
        assert ASSET_PRICE_SHOCK_TO_PROVISIONS == Decimal("0.5")

    def test_baseline_no_shock(self):
        r = StressTestingEngine.apply_scenario(_inputs(), "BASELINE")
        assert Decimal(r["stressed_car_pct"]) >= Decimal(r["starting_car_pct"])

    def test_adverse_drops_car(self):
        r = StressTestingEngine.apply_scenario(_inputs(), "ADVERSE")
        assert Decimal(r["stressed_car_pct"]) < Decimal(r["starting_car_pct"])

    def test_severely_adverse_worst(self):
        r_adv = StressTestingEngine.apply_scenario(_inputs(), "ADVERSE")
        r_sev = StressTestingEngine.apply_scenario(_inputs(), "SEVERELY_ADVERSE")
        assert Decimal(r_sev["stressed_car_pct"]) < Decimal(r_adv["stressed_car_pct"])

    def test_unknown_scenario(self):
        r = StressTestingEngine.apply_scenario(_inputs(), "WEIRD")
        assert "error" in r

    def test_zero_rwa_rule1(self):
        r = StressTestingEngine.apply_scenario(_inputs(starting_rwa_kes=Decimal("0")), "ADVERSE")
        assert r["stressed_car_pct"] is None

    def test_supervisory_scenarios_all_run(self):
        r = StressTestingEngine.run_supervisory_scenarios(_inputs())
        for s in STRESS_SCENARIOS:
            assert s in r["scenarios"]

    def test_severely_adverse_is_worst(self):
        r = StressTestingEngine.run_supervisory_scenarios(_inputs())
        assert r["worst_scenario"] == "SEVERELY_ADVERSE"

    def test_reverse_stress_finds_breach(self):
        inputs = _inputs(
            starting_total_capital_kes=Decimal("15500000000"),
            starting_rwa_kes=Decimal("100000000000"),
        )
        r = StressTestingEngine.reverse_stress_test(inputs)
        assert r.get("breach_npl_pct") is not None

    def test_reverse_stress_already_below(self):
        inputs = _inputs(
            starting_total_capital_kes=Decimal("10000000000"),
            starting_rwa_kes=Decimal("100000000000"),
        )
        r = StressTestingEngine.reverse_stress_test(inputs)
        assert r["reason"] == "already_below_threshold"

    def test_capital_projection_3yr(self):
        r = StressTestingEngine.capital_projection(_inputs(), "ADVERSE")
        assert len(r["yearly_projection"]) == 3


# ============================================================================
# #80 Regulatory Returns (18)
# ============================================================================

def _bsd1(**kw):
    defaults = dict(
        reporting_date=date(2026, 4, 30),
        cash_kes=Decimal("5000000000"),
        central_bank_balances_kes=Decimal("3000000000"),
        treasury_bills_kes=Decimal("4000000000"),
        other_liquid_assets_kes=Decimal("1000000000"),
        total_deposits_kes=Decimal("50000000000"),
    )
    defaults.update(kw)
    return Bsd1Inputs(**defaults)


def _bsd3(**kw):
    defaults = dict(
        reporting_date=date(2026, 4, 30),
        cet1_kes=Decimal("12000000000"),
        tier1_kes=Decimal("13000000000"),
        total_capital_kes=Decimal("15000000000"),
        total_rwa_kes=Decimal("90000000000"),
    )
    defaults.update(kw)
    return Bsd3Inputs(**defaults)


class TestRegulatoryReturns:

    def test_return_types_byte_for_byte(self):
        for t in ("BSD_1", "BSD_2", "BSD_3", "BSD_17"):
            assert t in BSD_RETURN_TYPES

    def test_frequencies_byte_for_byte(self):
        assert RETURN_FREQUENCIES["BSD_1"] == "DAILY"
        assert RETURN_FREQUENCIES["BSD_2"] == "WEEKLY"
        assert RETURN_FREQUENCIES["BSD_3"] == "MONTHLY"
        assert RETURN_FREQUENCIES["BSD_17"] == "MONTHLY"

    def test_statutory_liquidity_byte_for_byte(self):
        assert STATUTORY_LIQUIDITY_RATIO_MIN_PCT == Decimal("20")

    def test_loan_classifications_byte_for_byte(self):
        for c in ("NORMAL", "WATCH", "SUBSTANDARD", "DOUBTFUL", "LOSS"):
            assert c in LOAN_CLASSIFICATIONS

    def test_classification_days_byte_for_byte(self):
        assert LOAN_CLASSIFICATION_DAYS["NORMAL"] == (0, 30)
        assert LOAN_CLASSIFICATION_DAYS["WATCH"] == (31, 60)
        assert LOAN_CLASSIFICATION_DAYS["SUBSTANDARD"] == (61, 90)
        assert LOAN_CLASSIFICATION_DAYS["DOUBTFUL"] == (91, 180)

    def test_provision_pct_byte_for_byte(self):
        assert LOAN_PROVISION_PCT["NORMAL"] == Decimal("1")
        assert LOAN_PROVISION_PCT["WATCH"] == Decimal("3")
        assert LOAN_PROVISION_PCT["SUBSTANDARD"] == Decimal("20")
        assert LOAN_PROVISION_PCT["DOUBTFUL"] == Decimal("50")
        assert LOAN_PROVISION_PCT["LOSS"] == Decimal("100")

    def test_bsd1_compliant(self):
        r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(_bsd1())
        assert r["compliant"] is True

    def test_bsd1_breach(self):
        inputs = _bsd1(
            cash_kes=Decimal("100000000"),
            central_bank_balances_kes=Decimal("100000000"),
            treasury_bills_kes=Decimal("100000000"),
            other_liquid_assets_kes=Decimal("100000000"),
        )
        r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(inputs)
        assert r["compliant"] is False

    def test_bsd1_missing_field_rule6(self):
        r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(_bsd1(reporting_date=None))
        assert r["generated"] is False

    def test_bsd1_zero_deposits_rule1(self):
        r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(
            _bsd1(total_deposits_kes=Decimal("0")))
        assert r["liquidity_ratio_pct"] is None

    def test_bsd2_balance_check_passes(self):
        inputs = Bsd2Inputs(
            reporting_date=date(2026, 4, 30),
            cash_and_equivalents_kes=Decimal("10000000000"),
            loans_and_advances_kes=Decimal("60000000000"),
            investments_kes=Decimal("20000000000"),
            other_assets_kes=Decimal("10000000000"),
            deposits_kes=Decimal("80000000000"),
            borrowings_kes=Decimal("10000000000"),
            other_liabilities_kes=Decimal("0"),
            shareholders_equity_kes=Decimal("10000000000"),
        )
        r = RegulatoryReturnsEngine.generate_bsd2_balance_sheet(inputs)
        assert r["balance_check_passed"] is True

    def test_bsd2_balance_check_fails(self):
        inputs = Bsd2Inputs(
            reporting_date=date(2026, 4, 30),
            cash_and_equivalents_kes=Decimal("10000000000"),
            loans_and_advances_kes=Decimal("60000000000"),
            deposits_kes=Decimal("80000000000"),
            shareholders_equity_kes=Decimal("5000000000"),
        )
        r = RegulatoryReturnsEngine.generate_bsd2_balance_sheet(inputs)
        assert r["balance_check_passed"] is False

    def test_bsd3_compliant(self):
        r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(_bsd3())
        assert r["compliant_cbk"] is True

    def test_bsd3_zero_rwa_rule1(self):
        r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(
            _bsd3(total_rwa_kes=Decimal("0")))
        assert r["total_car_pct"] is None

    def test_bsd3_missing_field_rule6(self):
        r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(
            _bsd3(cet1_kes=None))
        assert r["generated"] is False

    def test_bsd17_classification_correct(self):
        loans = [LoanForClassification(loan_id=f"L{i}", outstanding_kes=Decimal("1000000"),
                                      days_past_due=d)
                 for i, d in enumerate([15, 45, 75, 120, 200])]
        r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
        # NPL = 3M out of 5M = 60%
        assert r["npl_ratio_pct"] == "60.00"

    def test_bsd17_provisions_correct(self):
        loans = [LoanForClassification(loan_id=f"L{i}", outstanding_kes=Decimal("1000000"),
                                      days_past_due=d)
                 for i, d in enumerate([15, 45, 75, 120, 200])]
        r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
        # 1+3+20+50+100 = 174% on 1M each = 1,740,000
        assert r["total_provisions_kes"] == "1740000.00"

    def test_bsd17_excluded_rule6(self):
        loans = [LoanForClassification(loan_id="L1", outstanding_kes=None, days_past_due=10)]
        r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
        assert r["excluded_count"] == 1

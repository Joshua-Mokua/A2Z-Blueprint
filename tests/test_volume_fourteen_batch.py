"""
================================================================================
A2Z MIS 360 — Volume Fourteen Batch Tests (Standards #73-#76 Treasury/ALM)
================================================================================

Tests Standards #73 Liquidity Risk (LCR/NSFR), #74 IRRBB, #75 FX Position,
#76 Investment Portfolio Analytics.

Total: 65 unit tests covering Basel III + CBK regulatory liquidity ratios,
       interest rate risk in banking book (BCBS 368), CBK FX limits, and
       fixed income analytics.

Run via:
    pytest tests/test_volume_fourteen_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.liquidity_risk import (
    LiquidityRiskEngine, HqlaHolding, CashFlowItem, FundingItem, AssetItem,
    HQLA_LEVELS, HQLA_HAIRCUT_PCT,
    OUTFLOW_RATES_PCT, INFLOW_RATES_PCT, INFLOW_CAP_PCT_OF_OUTFLOWS,
    LCR_MIN_PCT, NSFR_MIN_PCT,
    ASF_FACTORS_PCT, RSF_FACTORS_PCT,
    LEVEL_2_TOTAL_CAP_PCT, LEVEL_2B_CAP_PCT,
)
from utils.irrbb import (
    IrrbbEngine, RepricingBucket, IrrbbInputs,
    REPRICING_BUCKETS, BUCKET_MIDPOINT_DAYS,
    SHOCK_SCENARIOS, VALID_SCENARIOS,
    EVE_OUTLIER_THRESHOLD_PCT, NII_OUTLIER_THRESHOLD_PCT,
    NII_STANDARD_SHOCK_BPS,
)
from utils.fx_position import (
    FxPositionMonitoringEngine, FxPosition,
    SUPPORTED_CURRENCIES, AGGREGATION_METHODS,
    SINGLE_CURRENCY_LIMIT_PCT, AGGREGATE_FX_LIMIT_PCT,
)
from utils.investment_portfolio import (
    InvestmentPortfolioEngine, BondHolding,
    INSTRUMENT_TYPES, HQLA_CLASS, RATING_TO_HQLA_LEVEL,
    SINGLE_ISSUER_LIMIT_PCT, SINGLE_SECTOR_LIMIT_PCT,
)


# ============================================================================
# #73 Liquidity Risk (17)
# ============================================================================

def _hqla(**kw):
    defaults = dict(asset_id="A1", level="LEVEL_1", market_value_kes=Decimal("100000000"))
    defaults.update(kw)
    return HqlaHolding(**defaults)


def _cf(**kw):
    defaults = dict(item_id="I1", category="RETAIL_DEPOSITS_STABLE",
                    direction="OUTFLOW", balance_kes=Decimal("100000000"))
    defaults.update(kw)
    return CashFlowItem(**defaults)


class TestLiquidityRisk:

    def test_haircut_thresholds_byte_for_byte(self):
        assert HQLA_HAIRCUT_PCT["LEVEL_1"] == Decimal("0")
        assert HQLA_HAIRCUT_PCT["LEVEL_2A"] == Decimal("15")
        assert HQLA_HAIRCUT_PCT["LEVEL_2B"] == Decimal("50")

    def test_compliance_thresholds_byte_for_byte(self):
        assert LCR_MIN_PCT == Decimal("100")
        assert NSFR_MIN_PCT == Decimal("100")
        assert INFLOW_CAP_PCT_OF_OUTFLOWS == Decimal("75")

    def test_level2_caps_byte_for_byte(self):
        assert LEVEL_2_TOTAL_CAP_PCT == Decimal("40")
        assert LEVEL_2B_CAP_PCT == Decimal("15")

    def test_outflow_rates_byte_for_byte(self):
        assert OUTFLOW_RATES_PCT["RETAIL_DEPOSITS_STABLE"] == Decimal("5")
        assert OUTFLOW_RATES_PCT["RETAIL_DEPOSITS_LESS_STABLE"] == Decimal("10")
        assert OUTFLOW_RATES_PCT["FINANCIAL_COUNTERPARTY"] == Decimal("100")
        assert OUTFLOW_RATES_PCT["CORPORATE_NON_FINANCIAL"] == Decimal("40")
        assert OUTFLOW_RATES_PCT["UNDRAWN_CREDIT_FACILITIES"] == Decimal("10")

    def test_asf_factors_byte_for_byte(self):
        assert ASF_FACTORS_PCT["TIER_1_CAPITAL"] == Decimal("100")
        assert ASF_FACTORS_PCT["RETAIL_DEPOSITS_LT_1Y"] == Decimal("90")
        assert ASF_FACTORS_PCT["WHOLESALE_FUNDING_LT_1Y"] == Decimal("50")

    def test_rsf_factors_byte_for_byte(self):
        assert RSF_FACTORS_PCT["LEVEL_1_HQLA"] == Decimal("5")
        assert RSF_FACTORS_PCT["MORTGAGE_LOANS"] == Decimal("65")
        assert RSF_FACTORS_PCT["CORPORATE_LOANS_GTE_1Y"] == Decimal("85")

    def test_hqla_level1_no_haircut(self):
        r = LiquidityRiskEngine.hqla_value([_hqla()])
        assert r["level_1_kes"] == "100000000.00"

    def test_hqla_level2a_haircut_15pct(self):
        r = LiquidityRiskEngine.hqla_value([_hqla(level="LEVEL_2A")])
        assert r["level_2a_kes"] == "85000000.00"

    def test_hqla_excluded_rule6(self):
        r = LiquidityRiskEngine.hqla_value([_hqla(market_value_kes=None)])
        assert r["excluded_count"] == 1

    def test_nco_basic_5pct_runoff(self):
        cf = [_cf(category="RETAIL_DEPOSITS_STABLE",
                  balance_kes=Decimal("100000000"))]
        r = LiquidityRiskEngine.net_cash_outflows_30d(cf)
        assert r["total_outflows_kes"] == "5000000.00"

    def test_nco_inflow_capped_75pct(self):
        cf = [_cf(item_id="O", category="CORPORATE_NON_FINANCIAL",
                  direction="OUTFLOW", balance_kes=Decimal("100000000")),
              _cf(item_id="I", category="WHOLESALE_LOAN_INFLOWS",
                  direction="INFLOW", balance_kes=Decimal("100000000"))]
        r = LiquidityRiskEngine.net_cash_outflows_30d(cf)
        assert r["capped_inflows_kes"] == "30000000.00"

    def test_lcr_compliant(self):
        h = [_hqla(market_value_kes=Decimal("100000000"))]
        cf = [_cf()]
        r = LiquidityRiskEngine.lcr(h, cf)
        assert r["compliant"] is True

    def test_lcr_breach(self):
        h = [_hqla(market_value_kes=Decimal("1000000"))]
        cf = [_cf(category="CORPORATE_NON_FINANCIAL",
                  balance_kes=Decimal("100000000"))]
        r = LiquidityRiskEngine.lcr(h, cf)
        assert r["status"] == "RED"

    def test_lcr_zero_outflows_rule1(self):
        h = [_hqla()]
        r = LiquidityRiskEngine.lcr(h, [])
        assert r["lcr_pct"] is None

    def test_nsfr_compliant(self):
        funding = [FundingItem(item_id="F", category="RETAIL_DEPOSITS_LT_1Y",
                              balance_kes=Decimal("1000000000"))]
        assets = [AssetItem(item_id="A", category="RETAIL_LOANS_GTE_1Y",
                           balance_kes=Decimal("1000000000"))]
        r = LiquidityRiskEngine.nsfr(funding, assets)
        assert r["compliant"] is True

    def test_nsfr_breach(self):
        funding = [FundingItem(item_id="F", category="WHOLESALE_FUNDING_LT_1Y",
                              balance_kes=Decimal("100000000"))]
        assets = [AssetItem(item_id="A", category="OTHER_ASSETS",
                           balance_kes=Decimal("1000000000"))]
        r = LiquidityRiskEngine.nsfr(funding, assets)
        assert r["status"] == "RED"

    def test_nsfr_rsf_zero_rule1(self):
        funding = [FundingItem(item_id="F", category="RETAIL_DEPOSITS_LT_1Y",
                              balance_kes=Decimal("1000000000"))]
        r = LiquidityRiskEngine.nsfr(funding, [])
        assert r["nsfr_pct"] is None


# ============================================================================
# #74 IRRBB (14)
# ============================================================================

def _bucket(**kw):
    defaults = dict(bucket="1Y",
                    rate_sensitive_assets_kes=Decimal("1000000000"),
                    rate_sensitive_liabilities_kes=Decimal("800000000"))
    defaults.update(kw)
    return RepricingBucket(**defaults)


class TestIrrbb:

    def test_buckets_byte_for_byte(self):
        for b in ("ON_DEMAND", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "10Y_PLUS"):
            assert b in REPRICING_BUCKETS

    def test_shock_scenarios_byte_for_byte(self):
        assert SHOCK_SCENARIOS["PARALLEL_UP"]["all"] == 200
        assert SHOCK_SCENARIOS["PARALLEL_DOWN"]["all"] == -200
        assert SHOCK_SCENARIOS["STEEPENER"]["short"] == -65
        assert SHOCK_SCENARIOS["STEEPENER"]["long"] == 90
        assert SHOCK_SCENARIOS["FLATTENER"]["short"] == 90
        assert SHOCK_SCENARIOS["FLATTENER"]["long"] == -65
        assert SHOCK_SCENARIOS["SHORT_RATE_UP"]["short"] == 300

    def test_outlier_thresholds_byte_for_byte(self):
        assert EVE_OUTLIER_THRESHOLD_PCT == Decimal("15")
        assert NII_OUTLIER_THRESHOLD_PCT == Decimal("5")

    def test_repricing_gap_basic(self):
        bs = [_bucket(bucket="3M",
                      rate_sensitive_assets_kes=Decimal("500000000"),
                      rate_sensitive_liabilities_kes=Decimal("300000000"))]
        r = IrrbbEngine.repricing_gap(bs)
        assert r["bucket_count"] == 1

    def test_repricing_gap_excluded_rule6(self):
        bs = [_bucket(rate_sensitive_assets_kes=None)]
        r = IrrbbEngine.repricing_gap(bs)
        assert r["excluded_count"] == 1

    def test_nii_up_shock_positive(self):
        bs = [_bucket(bucket="3M",
                      rate_sensitive_assets_kes=Decimal("1000000000"),
                      rate_sensitive_liabilities_kes=Decimal("500000000"))]
        r = IrrbbEngine.nii_sensitivity_200bps(bs, Decimal("100000000"), "UP")
        assert Decimal(r["nii_impact_kes"]) > 0

    def test_nii_outlier_detection(self):
        bs = [_bucket(bucket="3M",
                      rate_sensitive_assets_kes=Decimal("10000000000"),
                      rate_sensitive_liabilities_kes=Decimal("1000000000"))]
        r = IrrbbEngine.nii_sensitivity_200bps(bs, Decimal("100000000"), "UP")
        assert r["is_outlier"] is True

    def test_nii_no_capital_rule1(self):
        r = IrrbbEngine.nii_sensitivity_200bps([_bucket()], None, "UP")
        assert r["outlier_pct"] is None

    def test_eve_parallel_up(self):
        bs = [_bucket(bucket="5Y",
                      rate_sensitive_assets_kes=Decimal("1000000000"),
                      rate_sensitive_liabilities_kes=Decimal("500000000"))]
        r = IrrbbEngine.eve_sensitivity(bs, "PARALLEL_UP", Decimal("100000000"))
        assert Decimal(r["eve_change_kes"]) < 0

    def test_eve_unknown_scenario(self):
        r = IrrbbEngine.eve_sensitivity([_bucket()], "WEIRD", Decimal("100000000"))
        assert "error" in r

    def test_eve_no_capital_rule1(self):
        r = IrrbbEngine.eve_sensitivity([_bucket()], "PARALLEL_UP", None)
        assert r["outlier_pct"] is None

    def test_eve_outlier(self):
        bs = [_bucket(bucket="10Y_PLUS",
                      rate_sensitive_assets_kes=Decimal("10000000000"),
                      rate_sensitive_liabilities_kes=Decimal("0"))]
        r = IrrbbEngine.eve_sensitivity(bs, "PARALLEL_UP", Decimal("100000000"))
        assert r["is_outlier"] is True

    def test_all_scenarios_summary(self):
        bs = [_bucket(bucket="5Y",
                      rate_sensitive_assets_kes=Decimal("1000000000"),
                      rate_sensitive_liabilities_kes=Decimal("500000000"))]
        inputs = IrrbbInputs(buckets=bs, tier_1_capital_kes=Decimal("100000000"))
        r = IrrbbEngine.all_scenarios_summary(inputs)
        assert len(r["eve_scenarios"]) == len(VALID_SCENARIOS)

    def test_nii_standard_shock_byte_for_byte(self):
        assert NII_STANDARD_SHOCK_BPS == 200


# ============================================================================
# #75 FX Position (15)
# ============================================================================

def _pos(**kw):
    defaults = dict(position_id="P1", currency="USD",
                    fx_assets_kes_equivalent=Decimal("100000000"),
                    fx_liabilities_kes_equivalent=Decimal("80000000"),
                    spot_rate_to_kes=Decimal("130"))
    defaults.update(kw)
    return FxPosition(**defaults)


class TestFxPosition:

    def test_currencies_byte_for_byte(self):
        for ccy in ("USD", "EUR", "GBP", "JPY", "CHF", "UGX", "TZS", "RWF"):
            assert ccy in SUPPORTED_CURRENCIES

    def test_methods_byte_for_byte(self):
        for m in ("SHORTHAND_METHOD", "SUM_ABSOLUTE"):
            assert m in AGGREGATION_METHODS

    def test_limits_byte_for_byte(self):
        assert SINGLE_CURRENCY_LIMIT_PCT == Decimal("10")
        assert AGGREGATE_FX_LIMIT_PCT == Decimal("20")

    def test_net_position_long(self):
        r = FxPositionMonitoringEngine.net_open_position_per_currency([_pos()])
        assert r["positions"][0]["position_type"] == "LONG"

    def test_net_position_short(self):
        p = _pos(fx_assets_kes_equivalent=Decimal("50000000"),
                 fx_liabilities_kes_equivalent=Decimal("100000000"))
        r = FxPositionMonitoringEngine.net_open_position_per_currency([p])
        assert r["positions"][0]["position_type"] == "SHORT"

    def test_unknown_currency_rule6(self):
        p = _pos(currency="XYZ")
        r = FxPositionMonitoringEngine.net_open_position_per_currency([p])
        assert "XYZ" in r["unknown_currencies"]

    def test_excluded_missing_value_rule6(self):
        p = _pos(fx_assets_kes_equivalent=None)
        r = FxPositionMonitoringEngine.net_open_position_per_currency([p])
        assert r["excluded_count"] == 1

    def test_aggregate_shorthand(self):
        positions = [_pos(position_id="P1", currency="USD",
                          fx_assets_kes_equivalent=Decimal("100000000"),
                          fx_liabilities_kes_equivalent=Decimal("80000000")),
                     _pos(position_id="P2", currency="EUR",
                          fx_assets_kes_equivalent=Decimal("50000000"),
                          fx_liabilities_kes_equivalent=Decimal("80000000"))]
        r = FxPositionMonitoringEngine.aggregate_net_open_position(positions)
        assert r["aggregate_net_open_position_kes"] == "30000000.00"

    def test_aggregate_sum_absolute(self):
        positions = [_pos(position_id="P1", currency="USD",
                          fx_assets_kes_equivalent=Decimal("100000000"),
                          fx_liabilities_kes_equivalent=Decimal("80000000")),
                     _pos(position_id="P2", currency="EUR",
                          fx_assets_kes_equivalent=Decimal("50000000"),
                          fx_liabilities_kes_equivalent=Decimal("80000000"))]
        r = FxPositionMonitoringEngine.aggregate_net_open_position(positions, "SUM_ABSOLUTE")
        assert r["aggregate_net_open_position_kes"] == "50000000.00"

    def test_limit_check_compliant(self):
        r = FxPositionMonitoringEngine.fx_exposure_limit_check([_pos()], Decimal("1000000000"))
        assert r["status"] == "GREEN"

    def test_limit_check_single_breach(self):
        p = _pos(fx_assets_kes_equivalent=Decimal("30000000"),
                 fx_liabilities_kes_equivalent=Decimal("0"))
        r = FxPositionMonitoringEngine.fx_exposure_limit_check([p], Decimal("100000000"))
        assert len(r["single_currency_breaches"]) == 1

    def test_limit_check_aggregate_breach(self):
        p = _pos(fx_assets_kes_equivalent=Decimal("25000000"),
                 fx_liabilities_kes_equivalent=Decimal("0"))
        r = FxPositionMonitoringEngine.fx_exposure_limit_check([p], Decimal("100000000"))
        assert r["aggregate_breach"] is True

    def test_limit_check_no_capital_rule1(self):
        r = FxPositionMonitoringEngine.fx_exposure_limit_check([_pos()], None)
        assert r.get("aggregate_pct") is None

    def test_aggregate_unknown_method(self):
        r = FxPositionMonitoringEngine.aggregate_net_open_position([_pos()], "WEIRD")
        assert "error" in r

    def test_pnl_attribution(self):
        p = _pos(fx_assets_kes_equivalent=Decimal("130000000"),
                 fx_liabilities_kes_equivalent=Decimal("0"),
                 spot_rate_to_kes=Decimal("130"))
        r = FxPositionMonitoringEngine.fx_pnl_attribution([p], {"USD": Decimal("125")})
        assert Decimal(r["total_pnl_kes"]) == Decimal("5000000.00")


# ============================================================================
# #76 Investment Portfolio (19)
# ============================================================================

def _bond(**kw):
    defaults = dict(holding_id="B1", instrument_type="GOVERNMENT_BOND",
                    issuer="KENYA_GOK", sector="SOVEREIGN",
                    par_value_kes=Decimal("100000000"),
                    market_price_pct=Decimal("98.5"),
                    coupon_rate_pct=Decimal("12.0"),
                    coupon_frequency_per_year=2,
                    maturity_date=date(2030, 6, 30),
                    settlement_date=date(2026, 6, 30),
                    credit_rating="AA",
                    is_sovereign=True)
    defaults.update(kw)
    return BondHolding(**defaults)


class TestInvestmentPortfolio:

    def test_concentration_limits_byte_for_byte(self):
        assert SINGLE_ISSUER_LIMIT_PCT == Decimal("25")
        assert SINGLE_SECTOR_LIMIT_PCT == Decimal("35")

    def test_hqla_class_byte_for_byte(self):
        for c in ("LEVEL_1", "LEVEL_2A", "LEVEL_2B", "NON_HQLA"):
            assert c in HQLA_CLASS

    def test_rating_mapping_byte_for_byte(self):
        assert RATING_TO_HQLA_LEVEL["AAA"] == "LEVEL_1"
        assert RATING_TO_HQLA_LEVEL["A"] == "LEVEL_2A"
        assert RATING_TO_HQLA_LEVEL["BBB-"] == "LEVEL_2B"

    def test_instrument_types_byte_for_byte(self):
        for it in ("GOVERNMENT_BOND", "TREASURY_BILL", "CORPORATE_BOND",
                   "MUNICIPAL_BOND", "EQUITY", "MUTUAL_FUND"):
            assert it in INSTRUMENT_TYPES

    def test_market_value_basic(self):
        r = InvestmentPortfolioEngine.portfolio_market_value([_bond()])
        assert r["total_market_value_kes"] == "98500000.00"

    def test_market_value_excluded_rule6(self):
        r = InvestmentPortfolioEngine.portfolio_market_value([_bond(market_price_pct=None)])
        assert r["excluded_count"] == 1

    def test_modified_duration_basic(self):
        r = InvestmentPortfolioEngine.bond_modified_duration(_bond(), Decimal("12"))
        assert r["modified_duration"] is not None

    def test_modified_duration_missing_data_rule6(self):
        r = InvestmentPortfolioEngine.bond_modified_duration(_bond(coupon_rate_pct=None), Decimal("12"))
        assert r["reason"] == "missing_required_fields"

    def test_modified_duration_matured(self):
        r = InvestmentPortfolioEngine.bond_modified_duration(
            _bond(maturity_date=date(2025, 1, 1)), Decimal("12"))
        assert r["modified_duration"] is None

    def test_portfolio_duration(self):
        r = InvestmentPortfolioEngine.portfolio_weighted_duration([_bond()], Decimal("12"))
        assert r["portfolio_modified_duration"] is not None

    def test_portfolio_duration_zero_mv_rule1(self):
        r = InvestmentPortfolioEngine.portfolio_weighted_duration(
            [_bond(market_price_pct=None)], Decimal("12"))
        assert r["portfolio_modified_duration"] is None

    def test_ytm_at_par_equals_coupon(self):
        b = _bond(market_price_pct=Decimal("100.0"), coupon_rate_pct=Decimal("12.0"))
        r = InvestmentPortfolioEngine.yield_to_maturity(b)
        ytm = Decimal(r["ytm_pct"])
        assert abs(ytm - Decimal("12.0")) < Decimal("0.05")

    def test_ytm_basic(self):
        r = InvestmentPortfolioEngine.yield_to_maturity(_bond())
        assert r["ytm_pct"] is not None

    def test_ytm_missing_data_rule6(self):
        r = InvestmentPortfolioEngine.yield_to_maturity(_bond(par_value_kes=None))
        assert r["ytm_pct"] is None

    def test_hqla_sovereign_level1(self):
        r = InvestmentPortfolioEngine.hqla_classification([_bond()])
        assert Decimal(r["by_level"]["LEVEL_1"]) > Decimal("0")

    def test_hqla_corporate_level2b(self):
        b = _bond(issuer="ACME", sector="INDUSTRIAL", is_sovereign=False,
                 credit_rating="BBB", instrument_type="CORPORATE_BOND")
        r = InvestmentPortfolioEngine.hqla_classification([b])
        assert Decimal(r["by_level"]["LEVEL_2B"]) > Decimal("0")

    def test_hqla_equity_non_hqla(self):
        b = _bond(instrument_type="EQUITY", is_sovereign=False, credit_rating=None)
        r = InvestmentPortfolioEngine.hqla_classification([b])
        assert Decimal(r["by_level"]["NON_HQLA"]) > Decimal("0")

    def test_concentration_issuer_breach(self):
        b = _bond(par_value_kes=Decimal("60000000"), market_price_pct=Decimal("100"))
        r = InvestmentPortfolioEngine.concentration_risk([b], Decimal("100000000"))
        assert len(r["issuer_breaches"]) == 1

    def test_concentration_no_capital_rule1(self):
        r = InvestmentPortfolioEngine.concentration_risk([_bond()], None)
        assert r.get("issuer_breaches") == []

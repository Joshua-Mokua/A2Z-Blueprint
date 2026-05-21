"""
================================================================================
A2Z MIS 360 — Volume Eighteen Batch Tests (Standards #89-#92)
================================================================================

Tests Standards #89 FTP, #90 Product RAROC, #91 Channel Performance,
#92 ESG/Sustainability Reporting (TCFD + GHG Protocol + IFRS S2).

Total: 84 unit tests covering FTP curve interpolation, RAROC formula,
       hurdle-rate tiering, channel mix economics, TCFD 11-disclosure
       validation, and 15-category Scope 3 GHG aggregation.

Run via:
    pytest tests/test_volume_eighteen_batch.py -v
================================================================================
"""

from __future__ import annotations

from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:
    pytest = None  # type: ignore

from utils.funds_transfer_pricing import (
    FtpEngine, FtpCurvePoint,
    FTP_METHODOLOGIES, FTP_CURVE_TENORS_MONTHS,
    LIQUIDITY_PREMIUM_TIERS_BPS, LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS,
)
from utils.product_raroc import (
    ProductRarocEngine, ProductPnl,
    PRODUCT_GROUPS, COST_CATEGORIES, ALLOCATION_METHODOLOGIES,
    HURDLE_RATE_PCT, GREEN_MULTIPLIER, AMBER_MULTIPLIER,
)
from utils.channel_performance import (
    ChannelPerformanceEngine, ChannelMetrics,
    CHANNELS, CHANNEL_COST_PER_TXN_KES, SELF_SERVICE_CHANNELS,
    CHANNEL_AVAILABILITY_TARGET_PCT, CHANNEL_TIERS, CHANNEL_TIER_MAP,
)
from utils.esg_reporting import (
    EsgReportingEngine, TcfdDisclosure, GhgInventory,
    TCFD_PILLARS, TCFD_RECOMMENDED_DISCLOSURES, DISCLOSURE_PILLAR_MAP,
    GHG_SCOPES, SCOPE_3_CATEGORIES, CLIMATE_RISK_TYPES,
    ISSB_DISCLOSURE_TOPICS, TCFD_MIN_COMPLETE_PCT,
)


# ============================================================================
# #89 FTP (20)
# ============================================================================

class TestFtp:

    def _curve(self):
        return [FtpCurvePoint(tenor_months=t, rate_pct=Decimal(r))
                for t, r in [(1, "8.0"), (3, "8.5"), (6, "9.0"), (12, "9.5"),
                             (24, "10.0"), (36, "10.5"), (60, "11.0"), (120, "12.0")]]

    def test_methodologies_byte_for_byte(self):
        for m in ("SINGLE_POOL", "MATCHED_MATURITY"):
            assert m in FTP_METHODOLOGIES
        assert len(FTP_METHODOLOGIES) == 2

    def test_curve_tenors_byte_for_byte(self):
        for t in (1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360):
            assert t in FTP_CURVE_TENORS_MONTHS
        assert len(FTP_CURVE_TENORS_MONTHS) == 11

    def test_liquidity_premium_tiers_byte_for_byte(self):
        assert LIQUIDITY_PREMIUM_TIERS_BPS["SHORT_TERM"] == 10
        assert LIQUIDITY_PREMIUM_TIERS_BPS["MEDIUM_TERM"] == 25
        assert LIQUIDITY_PREMIUM_TIERS_BPS["LONG_TERM"] == 50
        assert LIQUIDITY_PREMIUM_TIERS_BPS["VERY_LONG_TERM"] == 100
        assert LIQUIDITY_PREMIUM_TIERS_BPS["EXTRA_LONG_TERM"] == 150

    def test_liquidity_bands_byte_for_byte(self):
        assert LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS["SHORT_TERM"] == (0, 12)
        assert LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS["MEDIUM_TERM"] == (13, 60)

    def test_mmftp_exact_match(self):
        r = FtpEngine.matched_maturity_ftp_rate(12, self._curve())
        assert r["ftp_rate_pct"] == "9.5000"

    def test_mmftp_interpolation(self):
        r = FtpEngine.matched_maturity_ftp_rate(18, self._curve())
        assert r["ftp_rate_pct"] == "9.7500"

    def test_mmftp_below_shortest(self):
        r = FtpEngine.matched_maturity_ftp_rate(0, self._curve())
        assert r["method"] == "below_shortest_curve_point"

    def test_mmftp_above_longest(self):
        r = FtpEngine.matched_maturity_ftp_rate(360, self._curve())
        assert r["method"] == "above_longest_curve_point"

    def test_mmftp_empty_curve_rule1(self):
        assert FtpEngine.matched_maturity_ftp_rate(12, [])["ftp_rate_pct"] is None

    def test_mmftp_missing_tenor_rule1(self):
        assert FtpEngine.matched_maturity_ftp_rate(None, self._curve())["ftp_rate_pct"] is None

    def test_single_pool_weighted(self):
        r = FtpEngine.single_pool_ftp_rate(
            [Decimal("50000000"), Decimal("50000000")],
            [Decimal("8.0"), Decimal("12.0")])
        assert r["ftp_rate_pct"] == "10.0000"

    def test_single_pool_zero_balance_rule1(self):
        r = FtpEngine.single_pool_ftp_rate([Decimal("0")], [Decimal("10")])
        assert r["ftp_rate_pct"] is None

    def test_single_pool_mismatched_rule1(self):
        r = FtpEngine.single_pool_ftp_rate([Decimal("100")], [Decimal("8"), Decimal("9")])
        assert r["ftp_rate_pct"] is None

    def test_liquidity_premium_short(self):
        r = FtpEngine.liquidity_premium(6)
        assert r["liquidity_premium_bps"] == 10

    def test_liquidity_premium_long(self):
        r = FtpEngine.liquidity_premium(84)
        assert r["liquidity_premium_bps"] == 50

    def test_liquidity_premium_extra_long(self):
        assert FtpEngine.liquidity_premium(360)["liquidity_premium_bps"] == 150

    def test_liquidity_premium_missing_rule1(self):
        assert FtpEngine.liquidity_premium(None)["liquidity_premium_bps"] is None

    def test_nim_split_asset(self):
        r = FtpEngine.net_interest_margin_split(
            Decimal("14"), Decimal("9"), is_asset=True)
        assert r["lending_spread_pct"] == "5.0000"

    def test_nim_split_liability(self):
        r = FtpEngine.net_interest_margin_split(
            Decimal("5"), Decimal("9"), is_asset=False)
        assert r["funding_spread_pct"] == "4.0000"

    def test_nim_split_missing_rule1(self):
        r = FtpEngine.net_interest_margin_split(None, Decimal("9"), is_asset=True)
        assert r["spread_pct"] is None


# ============================================================================
# #90 Product RAROC (24)
# ============================================================================

def _full_pnl():
    return ProductPnl(
        product_id="MORTGAGE_001", product_group="CONSUMER_LENDING",
        interest_income_kes=Decimal("100000000"),
        interest_expense_kes=Decimal("40000000"),
        non_interest_income_kes=Decimal("10000000"),
        direct_costs_kes=Decimal("5000000"),
        allocated_operations_kes=Decimal("3000000"),
        allocated_technology_kes=Decimal("2000000"),
        allocated_overhead_kes=Decimal("4000000"),
        expected_loss_kes=Decimal("8000000"),
        economic_capital_kes=Decimal("200000000"),
    )


class TestProductRaroc:

    def test_product_groups_byte_for_byte(self):
        for p in ("TRANSACTION_BANKING", "CONSUMER_LENDING", "CORPORATE_LENDING",
                  "TRADE_FINANCE", "TREASURY", "BANCASSURANCE"):
            assert p in PRODUCT_GROUPS
        assert len(PRODUCT_GROUPS) == 6

    def test_cost_categories_byte_for_byte(self):
        for c in ("DIRECT_PRODUCT_COSTS", "ALLOCATED_OPERATIONS",
                  "ALLOCATED_TECHNOLOGY", "ALLOCATED_OVERHEAD"):
            assert c in COST_CATEGORIES
        assert len(COST_CATEGORIES) == 4

    def test_allocation_methodologies_byte_for_byte(self):
        for m in ("ABC", "FULL_COST", "MARGINAL"):
            assert m in ALLOCATION_METHODOLOGIES

    def test_hurdle_rate_byte_for_byte(self):
        assert HURDLE_RATE_PCT == Decimal("15")

    def test_tier_multipliers_byte_for_byte(self):
        assert GREEN_MULTIPLIER == Decimal("1.0")
        assert AMBER_MULTIPLIER == Decimal("0.8")

    def test_nii_basic(self):
        assert ProductRarocEngine.net_interest_income(
            Decimal("100"), Decimal("40")) == Decimal("60")

    def test_nii_missing_rule1(self):
        assert ProductRarocEngine.net_interest_income(None, Decimal("40")) is None

    def test_total_opex_full(self):
        r = ProductRarocEngine.total_opex(_full_pnl())
        assert r["total_opex_kes"] == Decimal("14000000")

    def test_total_opex_missing_rule6(self):
        p = _full_pnl()
        p.allocated_overhead_kes = None
        r = ProductRarocEngine.total_opex(p)
        assert "ALLOCATED_OVERHEAD" in r["missing_cost_categories"]

    def test_operating_profit(self):
        r = ProductRarocEngine.operating_profit(_full_pnl())
        assert r["operating_profit_kes"] == Decimal("56000000")

    def test_operating_profit_missing_rule1(self):
        p = _full_pnl()
        p.non_interest_income_kes = None
        r = ProductRarocEngine.operating_profit(p)
        assert r["operating_profit_kes"] is None

    def test_raroc_full(self):
        r = ProductRarocEngine.raroc(_full_pnl())
        assert r["raroc_pct"] == "24.00"

    def test_raroc_zero_capital_rule1(self):
        p = _full_pnl()
        p.economic_capital_kes = Decimal("0")
        assert ProductRarocEngine.raroc(p)["raroc_pct"] is None

    def test_raroc_missing_components_rule1(self):
        p = _full_pnl()
        p.expected_loss_kes = None
        assert ProductRarocEngine.raroc(p)["raroc_pct"] is None

    def test_tier_green(self):
        assert ProductRarocEngine.profitability_tier(Decimal("24"))["tier"] == "GREEN"

    def test_tier_amber(self):
        assert ProductRarocEngine.profitability_tier(Decimal("13"))["tier"] == "AMBER"

    def test_tier_red(self):
        assert ProductRarocEngine.profitability_tier(Decimal("5"))["tier"] == "RED"

    def test_tier_at_hurdle(self):
        assert ProductRarocEngine.profitability_tier(Decimal("15"))["tier"] == "GREEN"

    def test_tier_at_amber_threshold(self):
        assert ProductRarocEngine.profitability_tier(Decimal("12"))["tier"] == "AMBER"

    def test_tier_none_rule6(self):
        assert ProductRarocEngine.profitability_tier(None)["tier"] is None

    def test_allocate_costs_abc(self):
        r = ProductRarocEngine.allocate_costs(
            Decimal("1000000"), {"P1": Decimal("60"), "P2": Decimal("40")},
            method="ABC")
        assert r["allocations"]["P1"] == "600000.00"

    def test_allocate_costs_unknown_method(self):
        r = ProductRarocEngine.allocate_costs(
            Decimal("1000000"), {"P1": Decimal("60")}, method="WEIRD")
        assert r["allocations"] is None

    def test_allocate_costs_zero_total_rule1(self):
        r = ProductRarocEngine.allocate_costs(Decimal("0"), {"P1": Decimal("60")})
        assert r["allocations"] is None

    def test_allocate_costs_no_drivers_rule1(self):
        r = ProductRarocEngine.allocate_costs(Decimal("1000000"), {})
        assert r["allocations"] is None


# ============================================================================
# #91 Channel Performance (20)
# ============================================================================

class TestChannelPerformance:

    def test_channels_byte_for_byte(self):
        for c in ("BRANCH", "ATM", "AGENT", "MOBILE", "INTERNET",
                  "USSD", "CALL_CENTER", "POS", "RTGS", "SWIFT"):
            assert c in CHANNELS
        assert len(CHANNELS) == 10

    def test_channel_costs_byte_for_byte(self):
        assert CHANNEL_COST_PER_TXN_KES["BRANCH"] == Decimal("200")
        assert CHANNEL_COST_PER_TXN_KES["MOBILE"] == Decimal("2")
        assert CHANNEL_COST_PER_TXN_KES["ATM"] == Decimal("50")
        assert CHANNEL_COST_PER_TXN_KES["AGENT"] == Decimal("30")
        assert CHANNEL_COST_PER_TXN_KES["RTGS"] == Decimal("1500")
        assert CHANNEL_COST_PER_TXN_KES["SWIFT"] == Decimal("2500")

    def test_self_service_byte_for_byte(self):
        for s in ("MOBILE", "INTERNET", "USSD"):
            assert s in SELF_SERVICE_CHANNELS
        assert len(SELF_SERVICE_CHANNELS) == 3

    def test_availability_target_byte_for_byte(self):
        assert CHANNEL_AVAILABILITY_TARGET_PCT == Decimal("99.5")

    def test_channel_tiers_byte_for_byte(self):
        for t in ("PHYSICAL", "DIGITAL", "INTERBANK"):
            assert t in CHANNEL_TIERS

    def test_tier_map(self):
        assert CHANNEL_TIER_MAP["BRANCH"] == "PHYSICAL"
        assert CHANNEL_TIER_MAP["MOBILE"] == "DIGITAL"
        assert CHANNEL_TIER_MAP["RTGS"] == "INTERBANK"

    def test_cost_per_txn_basic(self):
        r = ChannelPerformanceEngine.cost_per_transaction(
            Decimal("1000000"), 100000)
        assert r["cost_per_txn_kes"] == "10.00"

    def test_cost_per_txn_zero_count_rule1(self):
        r = ChannelPerformanceEngine.cost_per_transaction(Decimal("1000000"), 0)
        assert r["cost_per_txn_kes"] is None

    def test_cost_per_txn_missing_cost_rule1(self):
        r = ChannelPerformanceEngine.cost_per_transaction(None, 100)
        assert r["cost_per_txn_kes"] is None

    def test_channel_mix_basic(self):
        r = ChannelPerformanceEngine.channel_mix_pct({
            "BRANCH": 100, "MOBILE": 900,
        })
        assert r["mix_pct"]["BRANCH"] == "10.00"
        assert r["mix_pct"]["MOBILE"] == "90.00"

    def test_channel_mix_unknown_surfaced_rule6(self):
        r = ChannelPerformanceEngine.channel_mix_pct({
            "BRANCH": 100, "WEIRD": 50,
        })
        assert "WEIRD" in r["unknown_channels"]

    def test_channel_mix_zero_rule1(self):
        r = ChannelPerformanceEngine.channel_mix_pct({})
        assert r["mix_pct"] is None

    def test_self_service_ratio_basic(self):
        r = ChannelPerformanceEngine.self_service_ratio({
            "MOBILE": 600, "INTERNET": 200, "BRANCH": 200,
        })
        assert r["self_service_ratio_pct"] == "80.00"

    def test_self_service_zero_rule1(self):
        r = ChannelPerformanceEngine.self_service_ratio({})
        assert r["self_service_ratio_pct"] is None

    def test_availability_compliant(self):
        r = ChannelPerformanceEngine.channel_availability_compliance(
            "MOBILE", Decimal("99.7"))
        assert r["compliant"] is True

    def test_availability_non_compliant(self):
        r = ChannelPerformanceEngine.channel_availability_compliance(
            "ATM", Decimal("98.0"))
        assert r["compliant"] is False
        assert r["shortfall_pct"] == "1.50"

    def test_availability_unknown_channel_rule6(self):
        r = ChannelPerformanceEngine.channel_availability_compliance(
            "WEIRD", Decimal("99.7"))
        assert r["compliant"] is None

    def test_availability_missing_rule1(self):
        r = ChannelPerformanceEngine.channel_availability_compliance("MOBILE", None)
        assert r["compliant"] is None

    def test_blended_cost_per_txn(self):
        r = ChannelPerformanceEngine.blended_cost_per_transaction({
            "BRANCH": 500, "MOBILE": 500,
        })
        assert r["blended_cost_per_txn_kes"] == "101.00"

    def test_blended_cost_zero_rule1(self):
        r = ChannelPerformanceEngine.blended_cost_per_transaction({})
        assert r["blended_cost_per_txn_kes"] is None


# ============================================================================
# #92 ESG Sustainability Reporting (20)
# ============================================================================

def _all_disclosures():
    return [TcfdDisclosure(disclosure_id=d, pillar=DISCLOSURE_PILLAR_MAP[d],
                           populated=True)
            for d in TCFD_RECOMMENDED_DISCLOSURES]


def _full_inv():
    return GhgInventory(
        scope_1_tco2e=Decimal("1500"),
        scope_2_tco2e=Decimal("8000"),
        scope_3_tco2e=Decimal("250000"),
    )


class TestEsgReporting:

    def test_tcfd_pillars_byte_for_byte(self):
        for p in ("GOVERNANCE", "STRATEGY", "RISK_MANAGEMENT", "METRICS_AND_TARGETS"):
            assert p in TCFD_PILLARS
        assert len(TCFD_PILLARS) == 4

    def test_tcfd_disclosures_byte_for_byte(self):
        for d in ("GOV_A", "GOV_B", "STR_A", "STR_B", "STR_C",
                  "RISK_A", "RISK_B", "RISK_C", "MET_A", "MET_B", "MET_C"):
            assert d in TCFD_RECOMMENDED_DISCLOSURES
        assert len(TCFD_RECOMMENDED_DISCLOSURES) == 11

    def test_per_pillar_disclosure_counts(self):
        counts = {p: 0 for p in TCFD_PILLARS}
        for d in TCFD_RECOMMENDED_DISCLOSURES:
            counts[DISCLOSURE_PILLAR_MAP[d]] += 1
        assert counts["GOVERNANCE"] == 2
        assert counts["STRATEGY"] == 3
        assert counts["RISK_MANAGEMENT"] == 3
        assert counts["METRICS_AND_TARGETS"] == 3

    def test_ghg_scopes_byte_for_byte(self):
        for s in ("SCOPE_1", "SCOPE_2", "SCOPE_3"):
            assert s in GHG_SCOPES

    def test_scope_3_categories_byte_for_byte(self):
        assert len(SCOPE_3_CATEGORIES) == 15
        assert "INVESTMENTS" in SCOPE_3_CATEGORIES
        assert "BUSINESS_TRAVEL" in SCOPE_3_CATEGORIES

    def test_climate_risk_types_byte_for_byte(self):
        for r in ("ACUTE_PHYSICAL", "CHRONIC_PHYSICAL",
                  "TRANSITION_POLICY", "TRANSITION_TECHNOLOGY",
                  "TRANSITION_MARKET", "TRANSITION_REPUTATION"):
            assert r in CLIMATE_RISK_TYPES
        assert len(CLIMATE_RISK_TYPES) == 6

    def test_issb_topics_byte_for_byte(self):
        for t in ("CLIMATE_GOVERNANCE", "CLIMATE_STRATEGY", "CLIMATE_METRICS"):
            assert t in ISSB_DISCLOSURE_TOPICS

    def test_tcfd_min_complete_byte_for_byte(self):
        assert TCFD_MIN_COMPLETE_PCT == Decimal("100")

    def test_validate_tcfd_full(self):
        r = EsgReportingEngine.validate_tcfd_disclosure(_all_disclosures())
        assert r["complete"] is True

    def test_validate_tcfd_missing_rule6(self):
        disc = _all_disclosures()
        disc[0].populated = False
        r = EsgReportingEngine.validate_tcfd_disclosure(disc)
        assert "GOV_A" in r["missing_disclosures"]

    def test_validate_tcfd_unknown_surfaced(self):
        disc = _all_disclosures()
        disc.append(TcfdDisclosure(disclosure_id="WEIRD", pillar="UNKNOWN",
                                    populated=True))
        r = EsgReportingEngine.validate_tcfd_disclosure(disc)
        assert "WEIRD" in r["unknown_disclosures"]

    def test_ghg_total_full(self):
        r = EsgReportingEngine.ghg_emissions_total(_full_inv())
        assert r["total_tco2e"] == "259500.00"

    def test_ghg_total_missing_scope_rule1(self):
        inv = _full_inv()
        inv.scope_3_tco2e = None
        r = EsgReportingEngine.ghg_emissions_total(inv)
        assert r["total_tco2e"] is None

    def test_climate_risk_physical(self):
        r = EsgReportingEngine.climate_risk_classification("ACUTE_PHYSICAL")
        assert r["family"] == "PHYSICAL"

    def test_climate_risk_transition(self):
        r = EsgReportingEngine.climate_risk_classification("TRANSITION_POLICY")
        assert r["family"] == "TRANSITION"

    def test_climate_risk_unknown_rule6(self):
        r = EsgReportingEngine.climate_risk_classification("WEIRD")
        assert r["family"] is None

    def test_tcfd_pack_complete(self):
        r = EsgReportingEngine.generate_tcfd_pack(_all_disclosures(), _full_inv())
        assert r["complete"] is True
        assert r["eligible_for_distribution"] is True

    def test_tcfd_pack_missing_disclosure_rule6(self):
        disc = _all_disclosures()
        disc[0].populated = False
        r = EsgReportingEngine.generate_tcfd_pack(disc, _full_inv())
        assert r["eligible_for_distribution"] is False

    def test_tcfd_pack_data_quality_issue(self):
        disc = _all_disclosures()
        disc[0].has_data_quality_issues = True
        r = EsgReportingEngine.generate_tcfd_pack(disc, _full_inv())
        assert r["eligible_for_distribution"] is False

    def test_tcfd_pack_per_pillar_counts(self):
        r = EsgReportingEngine.generate_tcfd_pack(_all_disclosures(), _full_inv())
        counts = r["per_pillar_disclosures_present"]
        assert counts["STRATEGY"] == 3

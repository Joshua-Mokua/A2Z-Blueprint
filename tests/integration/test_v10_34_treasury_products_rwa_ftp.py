"""tests/integration/test_v10_34_treasury_products_rwa_ftp.py — v10.34.

Treasury arc batch 2: ENH-234 Treasury Products + ENH-235 RWA
Optimization + ENH-236 FTP Enhancement. Activates 3 of 16 Treasury
standards (now 6/16 active).
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


# ════════════════════════════════════════════════════════════════════════
# Imports
# ════════════════════════════════════════════════════════════════════════

class TestV1034Imports(unittest.TestCase):
    def test_treasury_products_imports(self):
        from utils import treasury_products  # noqa

    def test_rwa_optimization_imports(self):
        from utils import rwa_optimization  # noqa

    def test_fund_transfer_pricing_imports(self):
        from utils import fund_transfer_pricing  # noqa

    def test_treasury_products_public_symbols(self):
        from utils import treasury_products as m
        for sym in (
            "InstrumentType", "IFRS9Classification", "FairValueLevel",
            "YieldCurvePoint", "YieldCurve", "discount_factor",
            "FXPosition", "FXMTMResult",
            "mtm_fx_spot", "mtm_fx_forward",
            "MoneyMarketPosition", "BondPosition", "BondMTMResult",
            "accrued_interest_amount", "mtm_bond_via_yield",
            "TreasuryProductsEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")

    def test_rwa_optimization_public_symbols(self):
        from utils import rwa_optimization as m
        for sym in (
            "AssetClass", "DEFAULT_RISK_WEIGHTS",
            "CCFCategory", "DEFAULT_CCFS",
            "CET1_MIN_PCT", "T1_MIN_PCT",
            "TOTAL_CAPITAL_MIN_PCT",
            "CBK_CET1_MIN_PCT", "CBK_TOTAL_CAPITAL_MIN_PCT",
            "Exposure", "RWAExposureResult",
            "compute_exposure_rwa",
            "CapitalComponents", "CapitalRatioResult",
            "compute_capital_ratios",
            "SACCRAssetClass",
            "SACCR_SUPERVISORY_FACTORS_PCT", "SACCR_ALPHA",
            "SACCRTrade", "SACCREADResult",
            "compute_saccr_ead",
            "RWAOptimizationEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")

    def test_fund_transfer_pricing_public_symbols(self):
        from utils import fund_transfer_pricing as m
        for sym in (
            "FTPProductCategory", "DEFAULT_LIQUIDITY_PREMIUM_BPS",
            "DEFAULT_BEHAVIORAL_TENOR_YEARS",
            "FTPCurvePoint", "FTPCurve",
            "construct_ftp_curve",
            "FTPRateResult", "compute_product_ftp_rate",
            "NIMDecomposition", "decompose_nim",
            "FTPEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV1034SelfTests(unittest.TestCase):
    def test_treasury_products_self_test(self):
        from utils import treasury_products
        treasury_products.self_test()

    def test_rwa_optimization_self_test(self):
        from utils import rwa_optimization
        rwa_optimization.self_test()

    def test_fund_transfer_pricing_self_test(self):
        from utils import fund_transfer_pricing
        fund_transfer_pricing.self_test()


# ════════════════════════════════════════════════════════════════════════
# Standards Alignment
# ════════════════════════════════════════════════════════════════════════

class TestV1034StandardsAlignment(unittest.TestCase):
    def test_three_new_treasury_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory.startswith("treasury")
            and s.status == "active"}
        for sid in ("ENH-234", "ENH-235", "ENH-236"):
            self.assertIn(sid, active_ids)

    def test_six_treasury_standards_active(self):
        """v10.33 (3) + v10.34 (3) = 6 of 16 active."""
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [
            s for s in STANDARDS_REGISTRY
            if s.subcategory.startswith("treasury")
            and s.status == "active"]
        self.assertGreaterEqual(len(active), 6)


# ════════════════════════════════════════════════════════════════════════
# ENH-234: Treasury Products
# ════════════════════════════════════════════════════════════════════════

class TestV1034YieldCurve(unittest.TestCase):
    def test_yield_curve_rejects_unsorted_points(self):
        from utils.treasury_products import (
            YieldCurve, YieldCurvePoint)
        with self.assertRaises(ValueError):
            YieldCurve(
                curve_id="C1", currency="KES",
                as_of_date="2026-05-01",
                points=(
                    YieldCurvePoint(
                        tenor_years=Decimal("2"),
                        rate_pct=Decimal("10")),
                    YieldCurvePoint(
                        tenor_years=Decimal("1"),
                        rate_pct=Decimal("8"))))

    def test_yield_curve_linear_interpolation(self):
        from utils.treasury_products import (
            YieldCurve, YieldCurvePoint)
        curve = YieldCurve(
            curve_id="C1", currency="KES",
            as_of_date="2026-05-01",
            points=(
                YieldCurvePoint(
                    tenor_years=Decimal("1"),
                    rate_pct=Decimal("10")),
                YieldCurvePoint(
                    tenor_years=Decimal("3"),
                    rate_pct=Decimal("14"))))
        self.assertEqual(
            curve.rate(Decimal("2")), Decimal("12.0000"))


class TestV1034FX(unittest.TestCase):
    def test_fx_spot_long_profitable_when_base_strengthens(self):
        from utils.treasury_products import (
            FXPosition, InstrumentType, FairValueLevel,
            mtm_fx_spot)
        p = FXPosition(
            position_id="FX1",
            instrument_type=InstrumentType.FX_SPOT,
            base_currency="USD", quote_currency="KES",
            notional_base=Decimal("1000000"),
            contract_rate=Decimal("130"),
            value_date="2026-05-01",
            is_long_base=True)
        result = mtm_fx_spot(
            position=p, spot_rate=Decimal("135"),
            as_of_date="2026-05-01")
        self.assertEqual(result.pnl_quote, Decimal("5000000.00"))
        self.assertEqual(
            result.fair_value_level, FairValueLevel.LEVEL_1)

    def test_fx_forward_uses_covered_interest_parity(self):
        """KES rates higher than USD → KES forward weakens → +PnL on long USD forward at lower rate."""
        from utils.treasury_products import (
            FXPosition, InstrumentType, YieldCurve,
            YieldCurvePoint, mtm_fx_forward)
        p = FXPosition(
            position_id="FX1",
            instrument_type=InstrumentType.FX_FORWARD,
            base_currency="USD", quote_currency="KES",
            notional_base=Decimal("1000000"),
            contract_rate=Decimal("135"),
            value_date="2026-05-01",
            maturity_date="2027-05-01",
            is_long_base=True)
        usd_curve = YieldCurve(
            curve_id="USD", currency="USD",
            as_of_date="2026-05-01",
            points=(YieldCurvePoint(
                tenor_years=Decimal("1"), rate_pct=Decimal("5")),))
        kes_curve = YieldCurve(
            curve_id="KES", currency="KES",
            as_of_date="2026-05-01",
            points=(YieldCurvePoint(
                tenor_years=Decimal("1"), rate_pct=Decimal("13")),))
        result = mtm_fx_forward(
            position=p, spot_rate=Decimal("130"),
            base_curve=usd_curve, quote_curve=kes_curve,
            as_of_date="2026-05-01")
        # Long USD at 135, market F ≈ 130 × 1.13/1.05 ≈ 139.9 → +PnL
        self.assertGreater(result.pnl_quote, Decimal("0"))


class TestV1034BondPricing(unittest.TestCase):
    def test_bond_at_par_when_yield_equals_coupon(self):
        from utils.treasury_products import (
            BondPosition, InstrumentType, IFRS9Classification,
            mtm_bond_via_yield)
        bond = BondPosition(
            position_id="B1",
            instrument_type=InstrumentType.GOVT_BOND,
            isin="KE0000000001", issuer="GOK",
            currency="KES",
            face_value=Decimal("1000000"),
            coupon_pct=Decimal("10"),
            issue_date="2025-05-01",
            maturity_date="2030-05-01",
            classification=IFRS9Classification.HTM)
        result = mtm_bond_via_yield(
            position=bond, yield_pct=Decimal("10"),
            last_coupon_date="2026-05-01",
            as_of_date="2026-05-01")
        self.assertLess(
            abs(result.clean_price - Decimal("100")), Decimal("1"))


# ════════════════════════════════════════════════════════════════════════
# ENH-235: RWA Optimization
# ════════════════════════════════════════════════════════════════════════

class TestV1034BaselThresholds(unittest.TestCase):
    def test_basel_pillar_1_minima(self):
        from utils.rwa_optimization import (
            CET1_MIN_PCT, T1_MIN_PCT, TOTAL_CAPITAL_MIN_PCT)
        self.assertEqual(CET1_MIN_PCT, Decimal("4.5"))
        self.assertEqual(T1_MIN_PCT, Decimal("6.0"))
        self.assertEqual(TOTAL_CAPITAL_MIN_PCT, Decimal("8.0"))

    def test_cbk_pg_03_minima(self):
        from utils.rwa_optimization import (
            CBK_CET1_MIN_PCT, CBK_TOTAL_CAPITAL_MIN_PCT)
        self.assertEqual(CBK_CET1_MIN_PCT, Decimal("10.5"))
        self.assertEqual(CBK_TOTAL_CAPITAL_MIN_PCT, Decimal("14.5"))


class TestV1034RWAComputation(unittest.TestCase):
    def test_corporate_unrated_100pct_weight(self):
        from utils.rwa_optimization import (
            Exposure, AssetClass, compute_exposure_rwa)
        e = Exposure(
            exposure_id="E1", counterparty="A",
            asset_class=AssetClass.CORPORATE_UNRATED,
            on_bs_amount=Decimal("1000000"))
        result = compute_exposure_rwa(exposure=e)
        self.assertEqual(result.rwa, Decimal("1000000.00"))

    def test_residential_mortgage_35pct_per_cbk(self):
        """CBK PG/03 residential mortgage = 35%."""
        from utils.rwa_optimization import (
            Exposure, AssetClass, compute_exposure_rwa)
        e = Exposure(
            exposure_id="E1", counterparty="John Doe",
            asset_class=AssetClass.MORTGAGE_RESIDENTIAL,
            on_bs_amount=Decimal("1000000"))
        result = compute_exposure_rwa(exposure=e)
        self.assertEqual(result.rwa, Decimal("350000.00"))

    def test_capital_ratios_pass_basel_fail_cbk(self):
        """8% CET1 passes Basel 4.5% but fails CBK 10.5%."""
        from utils.rwa_optimization import (
            CapitalComponents, compute_capital_ratios)
        capital = CapitalComponents(
            cet1_capital=Decimal("800000000"),
            additional_t1_capital=Decimal("0"),
            tier_2_capital=Decimal("0"))
        result = compute_capital_ratios(
            result_id="C1", capital=capital,
            total_rwa=Decimal("10000000000"),
            as_of_date="2026-05-01")
        self.assertTrue(result.is_cet1_compliant_basel)
        self.assertFalse(result.is_cet1_compliant_cbk)


class TestV1034SACCR(unittest.TestCase):
    def test_saccr_alpha_per_bcbs_282(self):
        from utils.rwa_optimization import SACCR_ALPHA
        self.assertEqual(SACCR_ALPHA, Decimal("1.4"))

    def test_saccr_ir_supervisory_factor(self):
        """IR SF = 0.50% per BCBS 282."""
        from utils.rwa_optimization import (
            SACCR_SUPERVISORY_FACTORS_PCT, SACCRAssetClass)
        self.assertEqual(
            SACCR_SUPERVISORY_FACTORS_PCT[
                SACCRAssetClass.INTEREST_RATE],
            Decimal("0.50"))

    def test_saccr_ead_basic(self):
        from utils.rwa_optimization import (
            SACCRAssetClass, SACCRTrade, compute_saccr_ead)
        trades = [SACCRTrade(
            trade_id="T1", counterparty="BankA",
            asset_class=SACCRAssetClass.INTEREST_RATE,
            notional=Decimal("100000000"),
            maturity_years=Decimal("1"))]
        result = compute_saccr_ead(
            counterparty="BankA", trades=trades,
            current_mtm_total=Decimal("0"))
        # PFE = 100M × 0.5% × 1 = 500K; EAD = 1.4 × 500K = 700K
        self.assertEqual(result.ead, Decimal("700000.00"))


# ════════════════════════════════════════════════════════════════════════
# ENH-236: FTP
# ════════════════════════════════════════════════════════════════════════

class TestV1034FTPCurve(unittest.TestCase):
    def test_construct_ftp_curve_no_points_raises_provider(self):
        from utils.fund_transfer_pricing import construct_ftp_curve
        with self.assertRaises(ValueError) as ctx:
            construct_ftp_curve(
                curve_id="C1", currency="KES",
                as_of_date="2026-05-01",
                yield_curve_points=[],
                liquidity_premium_bps=Decimal("0"),
                source_yield_curve_id="YC")
        self.assertIn("REQUIRES_PROVIDER", str(ctx.exception))

    def test_ftp_curve_adds_liquidity_premium(self):
        from utils.fund_transfer_pricing import construct_ftp_curve
        curve = construct_ftp_curve(
            curve_id="C1", currency="KES",
            as_of_date="2026-05-01",
            yield_curve_points=[
                (Decimal("1"), Decimal("10")),
                (Decimal("3"), Decimal("13"))],
            liquidity_premium_bps=Decimal("50"),
            source_yield_curve_id="YC")
        # 50bps = 0.5% added
        self.assertEqual(
            curve.points[0].ftp_rate_pct, Decimal("10.5000"))


class TestV1034NIMDecomposition(unittest.TestCase):
    def test_lending_margin_positive_when_customer_above_ftp(self):
        from utils.fund_transfer_pricing import (
            FTPProductCategory, decompose_nim)
        result = decompose_nim(
            decomposition_id="D1", product_id="L1",
            product_category=FTPProductCategory.LOAN_TERM,
            is_asset=True,
            customer_rate_pct=Decimal("15"),
            ftp_rate_pct=Decimal("10"))
        self.assertEqual(result.spread_pct, Decimal("5.0000"))
        self.assertEqual(result.spread_label, "lending_margin")

    def test_funding_margin_positive_when_ftp_above_customer(self):
        from utils.fund_transfer_pricing import (
            FTPProductCategory, decompose_nim)
        result = decompose_nim(
            decomposition_id="D1", product_id="DEP1",
            product_category=FTPProductCategory.FIXED_DEPOSIT,
            is_asset=False,
            customer_rate_pct=Decimal("5"),
            ftp_rate_pct=Decimal("8"))
        self.assertEqual(result.spread_pct, Decimal("3.0000"))
        self.assertEqual(result.spread_label, "funding_margin")


class TestV1034FTPProductRate(unittest.TestCase):
    def test_demand_deposit_uses_behavioral_tenor(self):
        from utils.fund_transfer_pricing import (
            FTPCurve, FTPCurvePoint, FTPProductCategory,
            compute_product_ftp_rate)
        curve = FTPCurve(
            curve_id="C1", currency="KES", as_of_date="t",
            points=(FTPCurvePoint(
                tenor_years=Decimal("2"),
                ftp_rate_pct=Decimal("11"),
                base_rate_pct=Decimal("11"),
                liquidity_premium_bps=Decimal("0")),),
            source_yield_curve_id="YC")
        result = compute_product_ftp_rate(
            rate_id="R1", product_id="D1",
            product_category=FTPProductCategory.DEMAND_DEPOSIT,
            contractual_tenor_years=None,
            ftp_curve=curve)
        self.assertTrue(result.is_behavioral_tenor)
        self.assertEqual(
            result.tenor_years_used, Decimal("2.0"))


# ════════════════════════════════════════════════════════════════════════
# Composability — yield curve from treasury_products feeds FTP
# ════════════════════════════════════════════════════════════════════════

class TestV1034CrossModuleComposability(unittest.TestCase):
    def test_yield_curve_to_ftp_curve_pipeline(self):
        """v10.34 modules compose: YieldCurve → FTPCurve."""
        from utils.treasury_products import (
            YieldCurve, YieldCurvePoint)
        from utils.fund_transfer_pricing import construct_ftp_curve
        # Build base yield curve
        yc = YieldCurve(
            curve_id="YC-KES", currency="KES",
            as_of_date="2026-05-01",
            points=(
                YieldCurvePoint(
                    tenor_years=Decimal("0.5"),
                    rate_pct=Decimal("8")),
                YieldCurvePoint(
                    tenor_years=Decimal("1"),
                    rate_pct=Decimal("10")),
                YieldCurvePoint(
                    tenor_years=Decimal("3"),
                    rate_pct=Decimal("13"))))
        # Convert to FTP curve via yield curve points + premium
        yield_points = [
            (p.tenor_years, p.rate_pct) for p in yc.points]
        ftp_curve = construct_ftp_curve(
            curve_id="FTP-KES", currency="KES",
            as_of_date="2026-05-01",
            yield_curve_points=yield_points,
            liquidity_premium_bps=Decimal("50"),
            source_yield_curve_id=yc.curve_id)
        # FTP rate at 1y = 10% + 0.5% = 10.5%
        self.assertEqual(
            ftp_curve.ftp_rate(Decimal("1")), Decimal("10.5000"))


# ════════════════════════════════════════════════════════════════════════
# Coexistence with full stack
# ════════════════════════════════════════════════════════════════════════

class TestV1034CoexistenceWithFullStack(unittest.TestCase):
    def test_all_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.model_governance import ModelGovernanceEngine
        from utils.virtual_bank_core import VirtualBankCore
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG)
        from utils.treasury_alm import TreasuryALMEngine
        from utils.treasury_products import TreasuryProductsEngine
        from utils.rwa_optimization import RWAOptimizationEngine
        from utils.fund_transfer_pricing import FTPEngine
        engines = [
            AuditCoreEngine(entity_name="X"),
            ModelGovernanceEngine(entity_name="X"),
            VirtualBankCore(
                entity_name="X", base_seed="s",
                base_date="2026-01-01"),
            CrossSellBanditEngine(
                entity_name="X",
                config=BanditConfig(
                    config_id="C1", model_id="M",
                    feature_names=("balance_log", "intercept"),
                    offer_catalog=DEFAULT_OFFER_CATALOG,
                    alpha=1.0, base_seed="t")),
            TreasuryALMEngine(entity_name="X"),
            TreasuryProductsEngine(entity_name="X"),
            RWAOptimizationEngine(entity_name="X"),
            FTPEngine(entity_name="X"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

"""tests/integration/test_v10_33_treasury_alm.py — v10.33.

Treasury arc batch 1 (foundation): NMD behavioral modeling + Intraday
liquidity (LCR/NSFR per Basel III) + IRRBB (per Basel BCBS 368).
Activates ENH-231 + ENH-232 + ENH-233 of 16-standard Treasury arc.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1033Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import treasury_alm  # noqa

    def test_public_symbols(self):
        from utils import treasury_alm as m
        for sym in (
            # NMD
            "NMDDepositCategory", "DEFAULT_LCR_RUNOFF_RATES",
            "DEFAULT_NSFR_ASF_FACTORS", "NMDDeposit",
            "NMDDecayResult",
            "categorize_lcr_runoff", "categorize_nsfr_asf",
            "compute_decay_analysis",
            # Liquidity
            "LCR_MIN_RATIO", "NSFR_MIN_RATIO",
            "CBK_MIN_CASH_RATIO_PCT",
            "CBK_MIN_LIQUID_ASSETS_PCT",
            "HQLALevel", "HQLA_HAIRCUTS",
            "HQLAPosition", "CashFlow",
            "LCRResult", "compute_lcr",
            "NSFRResult", "compute_nsfr",
            "IntradayLiquidityPosition",
            # IRRBB
            "IRRBBScenario",
            "IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1",
            "MaturityBucket", "BUCKET_MID_YEARS",
            "RatesGapPosition", "RepricingGapResult",
            "compute_repricing_gap",
            "parallel_shock_bps", "short_long_shock_bps",
            "NIIScenarioResult", "compute_nii_sensitivity",
            "EVEScenarioResult", "compute_eve_sensitivity",
            # Engine
            "TreasuryALMEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1033SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import treasury_alm
        treasury_alm.self_test()


class TestV1033StandardsAlignment(unittest.TestCase):
    """ENH-231 + ENH-232 + ENH-233 active in registry."""

    def test_three_treasury_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory.startswith("treasury")
            and s.status == "active"}
        for sid in ("ENH-231", "ENH-232", "ENH-233"):
            self.assertIn(sid, active_ids)


class TestV1033BaselThresholds(unittest.TestCase):
    """Basel III thresholds preserved per regulation."""

    def test_lcr_min_100_pct_per_basel_188(self):
        from utils.treasury_alm import LCR_MIN_RATIO
        self.assertEqual(LCR_MIN_RATIO, Decimal("100"))

    def test_nsfr_min_100_pct_per_basel_295(self):
        from utils.treasury_alm import NSFR_MIN_RATIO
        self.assertEqual(NSFR_MIN_RATIO, Decimal("100"))

    def test_irrbb_outlier_threshold_15_pct_per_bcbs_368(self):
        from utils.treasury_alm import (
            IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1)
        self.assertEqual(
            IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1, Decimal("15"))


class TestV1033NMDModeling(unittest.TestCase):
    """ENH-231 — NMD behavioral modeling."""

    def test_runoff_rates_aligned_with_basel_188(self):
        from utils.treasury_alm import (
            DEFAULT_LCR_RUNOFF_RATES, NMDDepositCategory)
        # Per Basel BCBS 188
        self.assertEqual(
            DEFAULT_LCR_RUNOFF_RATES[
                NMDDepositCategory.RETAIL_STABLE],
            Decimal("3"))
        self.assertEqual(
            DEFAULT_LCR_RUNOFF_RATES[
                NMDDepositCategory.RETAIL_LESS_STABLE],
            Decimal("10"))
        self.assertEqual(
            DEFAULT_LCR_RUNOFF_RATES[
                NMDDepositCategory.INSTITUTIONAL_NON_OPERATIONAL],
            Decimal("100"))

    def test_asf_factors_aligned_with_basel_295(self):
        from utils.treasury_alm import (
            DEFAULT_NSFR_ASF_FACTORS, NMDDepositCategory)
        self.assertEqual(
            DEFAULT_NSFR_ASF_FACTORS[
                NMDDepositCategory.RETAIL_STABLE],
            Decimal("95"))

    def test_decay_analysis_dormancy_detected(self):
        from utils.treasury_alm import (
            NMDDeposit, NMDDepositCategory,
            compute_decay_analysis)
        # 5 deposits all dormant for 90+ days
        deps = [NMDDeposit(
            deposit_id=f"D{i}", cif=f"C{i}",
            category=NMDDepositCategory.RETAIL_STABLE,
            balance=Decimal("100000"), currency="KES",
            open_date="2024-01-01",
            last_movement_date="2024-06-01")
            for i in range(5)]
        result = compute_decay_analysis(
            analysis_id="A1",
            category=NMDDepositCategory.RETAIL_STABLE,
            deposits=deps,
            analysis_date="2026-05-01")
        self.assertEqual(result.n_dormant_90d, 5)


class TestV1033LCR(unittest.TestCase):
    """ENH-232 — LCR per Basel BCBS 188."""

    def test_lcr_compliant_when_hqla_2x_outflows(self):
        from utils.treasury_alm import (
            HQLAPosition, HQLALevel, CashFlow, compute_lcr)
        result = compute_lcr(
            result_id="L1",
            hqla_positions=[HQLAPosition(
                position_id="P1", asset_class="cash",
                level=HQLALevel.LEVEL_1,
                notional=Decimal("200000000"),
                currency="KES")],
            inflows=[],
            outflows=[CashFlow(
                flow_id="O1", direction="OUTFLOW",
                amount=Decimal("100000000"),
                bucket_days=30)],
            as_of_date="2026-05-01")
        self.assertTrue(result.is_compliant)
        self.assertEqual(result.lcr_ratio_pct, Decimal("200.00"))

    def test_lcr_non_compliant_below_100(self):
        from utils.treasury_alm import (
            HQLAPosition, HQLALevel, CashFlow, compute_lcr)
        result = compute_lcr(
            result_id="L1",
            hqla_positions=[HQLAPosition(
                position_id="P1", asset_class="cash",
                level=HQLALevel.LEVEL_1,
                notional=Decimal("50000000"),
                currency="KES")],
            inflows=[],
            outflows=[CashFlow(
                flow_id="O1", direction="OUTFLOW",
                amount=Decimal("100000000"),
                bucket_days=30)],
            as_of_date="2026-05-01")
        self.assertFalse(result.is_compliant)

    def test_lcr_l2a_haircut_15pct(self):
        from utils.treasury_alm import HQLAPosition, HQLALevel
        p = HQLAPosition(
            position_id="P1", asset_class="sov",
            level=HQLALevel.LEVEL_2A,
            notional=Decimal("1000000"),
            currency="KES")
        # 15% haircut → 85% retained
        self.assertEqual(p.lcr_value(), Decimal("850000.00"))

    def test_lcr_inflow_capped_at_75pct(self):
        from utils.treasury_alm import (
            HQLAPosition, HQLALevel, CashFlow, compute_lcr)
        result = compute_lcr(
            result_id="L1",
            hqla_positions=[HQLAPosition(
                position_id="P1", asset_class="cash",
                level=HQLALevel.LEVEL_1,
                notional=Decimal("100000000"),
                currency="KES")],
            inflows=[CashFlow(
                flow_id="I1", direction="INFLOW",
                amount=Decimal("100000000"),
                bucket_days=30)],
            outflows=[CashFlow(
                flow_id="O1", direction="OUTFLOW",
                amount=Decimal("100000000"),
                bucket_days=30)],
            as_of_date="2026-05-01")
        # Inflow capped at 75% × 100M = 75M; net outflow = 25M
        self.assertEqual(
            result.net_cash_outflow_30d, Decimal("25000000.00"))


class TestV1033NSFR(unittest.TestCase):
    def test_nsfr_compliant_above_100(self):
        from utils.treasury_alm import compute_nsfr
        result = compute_nsfr(
            result_id="N1",
            asf_components={"retail": Decimal("950000")},
            rsf_components={"loans": Decimal("700000")},
            as_of_date="2026-05-01")
        self.assertTrue(result.is_compliant)


class TestV1033IRRBB(unittest.TestCase):
    """ENH-233 — IRRBB per Basel BCBS 368."""

    def test_six_scenarios_per_bcbs_368(self):
        from utils.treasury_alm import IRRBBScenario
        # Basel BCBS 368 specifies exactly 6 standardized scenarios
        self.assertEqual(len(IRRBBScenario), 6)

    def test_parallel_up_200bps(self):
        from utils.treasury_alm import (
            IRRBBScenario, parallel_shock_bps)
        self.assertEqual(
            parallel_shock_bps(IRRBBScenario.PARALLEL_UP),
            Decimal("200"))

    def test_parallel_down_negative_200bps(self):
        from utils.treasury_alm import (
            IRRBBScenario, parallel_shock_bps)
        self.assertEqual(
            parallel_shock_bps(IRRBBScenario.PARALLEL_DOWN),
            Decimal("-200"))

    def test_steepener_short_negative_long_positive(self):
        from utils.treasury_alm import (
            IRRBBScenario, short_long_shock_bps)
        short, long = short_long_shock_bps(
            IRRBBScenario.STEEPENER)
        self.assertLess(short, Decimal("0"))
        self.assertGreater(long, Decimal("0"))

    def test_eve_outlier_15pct_threshold(self):
        """ΔEVE > 15% Tier 1 → outlier per Basel BCBS 368."""
        from utils.treasury_alm import (
            RatesGapPosition, MaturityBucket, IRRBBScenario,
            compute_eve_sensitivity,
            IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1)
        # Massive 5y+ asset → significant duration risk
        positions = [RatesGapPosition(
            position_id="P1",
            bucket=MaturityBucket.YEARS_5_PLUS,
            is_asset=True,
            notional=Decimal("10000000000"),
            currency="KES")]
        eve = compute_eve_sensitivity(
            result_id="EVE1",
            scenario=IRRBBScenario.PARALLEL_UP,
            positions=positions,
            base_eve_kes=Decimal("0"),
            tier_1_capital_kes=Decimal("1000000000"),
            as_of_date="2026-05-01")
        self.assertTrue(eve.is_outlier)
        self.assertGreater(
            eve.delta_eve_pct_tier_1,
            IRRBB_OUTLIER_THRESHOLD_PCT_TIER_1)

    def test_run_all_six_scenarios(self):
        from utils.treasury_alm import (
            TreasuryALMEngine, RatesGapPosition,
            MaturityBucket)
        eng = TreasuryALMEngine()
        eng.register_rates_position(RatesGapPosition(
            position_id="P1",
            bucket=MaturityBucket.MONTHS_1_3,
            is_asset=True,
            notional=Decimal("100000000"),
            currency="KES"))
        eng.run_repricing_gap(
            result_id="G1", as_of_date="2026-05-01")
        nii_results, eve_results = eng.run_all_irrbb_scenarios(
            result_id_prefix="ALL", gap_result_id="G1",
            base_nii_kes=Decimal("10000000"),
            base_eve_kes=Decimal("0"),
            tier_1_capital_kes=Decimal("1000000000"),
            as_of_date="2026-05-01")
        self.assertEqual(len(nii_results), 6)
        self.assertEqual(len(eve_results), 6)


class TestV1033EngineEnforcement(unittest.TestCase):
    def test_run_nii_without_gap_raises(self):
        """Per Rule 1 — surface error rather than silently skip."""
        from utils.treasury_alm import (
            TreasuryALMEngine, IRRBBScenario)
        eng = TreasuryALMEngine()
        with self.assertRaises(KeyError):
            eng.run_nii_sensitivity(
                result_id="NII1",
                scenario=IRRBBScenario.PARALLEL_UP,
                gap_result_id="MISSING",
                base_nii_kes=Decimal("100000"),
                as_of_date="2026-05-01")

    def test_inflow_with_outflow_direction_raises(self):
        from utils.treasury_alm import (
            TreasuryALMEngine, CashFlow)
        eng = TreasuryALMEngine()
        with self.assertRaises(ValueError):
            eng.add_inflow(CashFlow(
                flow_id="I1", direction="OUTFLOW",
                amount=Decimal("1000"), bucket_days=1))


class TestV1033CoexistsWithLegacy(unittest.TestCase):
    """treasury_alm coexists with legacy treasury_intelligence."""

    def test_both_modules_importable(self):
        import importlib
        m1 = importlib.import_module("utils.treasury_intelligence")
        m2 = importlib.import_module("utils.treasury_alm")
        # Both have engines under different names
        self.assertTrue(hasattr(m1, "TreasuryIntelligenceEngine"))
        self.assertTrue(hasattr(m2, "TreasuryALMEngine"))


class TestV1033CoexistenceWithFullStack(unittest.TestCase):
    def test_all_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.model_governance import ModelGovernanceEngine
        from utils.virtual_bank_core import VirtualBankCore
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG)
        from utils.treasury_alm import TreasuryALMEngine
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
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

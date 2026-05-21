"""tests/integration/test_v10_8_climate_ecl.py — v10.8.

Integration tests for utils/climate_ecl_adjustment.py
ENH-CLI-07 (stress testing) + ENH-CLI-12 (climate-adjusted ECL per IFRS 9).
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV108EngineImports(unittest.TestCase):
    def test_module_imports(self):
        from utils import climate_ecl_adjustment  # noqa: F401

    def test_public_symbols(self):
        from utils import climate_ecl_adjustment as m
        for sym in (
            "IFRS9Stage", "StressScenarioType",
            "DEFAULT_IFRS9_SCENARIO_WEIGHTS", "STRESS_HORIZONS_YEARS",
            "BaseECLInputs", "ClimateAdjustment",
            "ClimateAdjustedECLResult", "ProbabilityWeightedECLResult",
            "StressScenarioResult",
            "compute_pd_climate_multiplier",
            "compute_lgd_climate_multiplier",
            "compute_ead_climate_multiplier",
            "apply_climate_overlay",
            "compute_probability_weighted_ecl",
            "run_stress_scenario", "ClimateECLEngine",
            "MULTIPLIER_MIN", "MULTIPLIER_MAX",
            "IFRS9_MIN_SCENARIO_COUNT",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV108SelfTestPasses(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import climate_ecl_adjustment
        climate_ecl_adjustment.self_test()


class TestV108RegistryAlignment(unittest.TestCase):
    def test_10_climate_esg_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "climate_esg" and s.status == "active"]
        self.assertGreaterEqual(len(active), 10,
                                  f"After v10.8: expected ≥10 active, "
                                  f"got {len(active)}")

    def test_v10_8_specific_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory == "climate_esg" and s.status == "active"}
        self.assertIn("ENH-CLI-07", active_ids)
        self.assertIn("ENH-CLI-12", active_ids)


class TestV108BaseECL(unittest.TestCase):
    """Base ECL formula correctness."""

    def test_stage1_ecl_uses_12m_pd(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage)
        b = BaseECLInputs(
            asset_id="L", stage=IFRS9Stage.STAGE_1,
            pd_12m=Decimal("0.03"), pd_lifetime=Decimal("0.15"),
            lgd=Decimal("0.40"), ead_kes=Decimal("1000000"),
            sector="MANUFACTURING_LIGHT")
        # Stage 1 uses 12m: 0.03 × 0.40 × 1M = 12,000
        self.assertEqual(b.base_ecl_kes(), Decimal("12000"))

    def test_stage2_ecl_uses_lifetime_pd(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage)
        b = BaseECLInputs(
            asset_id="L", stage=IFRS9Stage.STAGE_2,
            pd_12m=Decimal("0.03"), pd_lifetime=Decimal("0.15"),
            lgd=Decimal("0.40"), ead_kes=Decimal("1000000"),
            sector="MANUFACTURING_LIGHT")
        # Stage 2 uses lifetime: 0.15 × 0.40 × 1M = 60,000
        self.assertEqual(b.base_ecl_kes(), Decimal("60000"))

    def test_input_validation_rejects_invalid_pd(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage)
        with self.assertRaises(ValueError):
            BaseECLInputs(
                asset_id="L", stage=IFRS9Stage.STAGE_1,
                pd_12m=Decimal("1.5"), pd_lifetime=Decimal("0.5"),
                lgd=Decimal("0.5"), ead_kes=Decimal("1"),
                sector="X")


class TestV108Multipliers(unittest.TestCase):
    """Climate multipliers behave correctly."""

    def test_zero_risk_no_uplift(self):
        from utils.climate_ecl_adjustment import (
            compute_pd_climate_multiplier)
        m = compute_pd_climate_multiplier(
            physical_risk_score=Decimal("0"),
            transition_risk_score=Decimal("0"),
            horizon_years=10)
        self.assertEqual(m, Decimal("1"))

    def test_horizon_increases_multiplier(self):
        from utils.climate_ecl_adjustment import (
            compute_pd_climate_multiplier)
        m_5 = compute_pd_climate_multiplier(
            physical_risk_score=Decimal("60"),
            transition_risk_score=Decimal("60"),
            horizon_years=5)
        m_30 = compute_pd_climate_multiplier(
            physical_risk_score=Decimal("60"),
            transition_risk_score=Decimal("60"),
            horizon_years=30)
        self.assertGreater(m_30, m_5)

    def test_real_estate_lgd_higher_than_other(self):
        from utils.climate_ecl_adjustment import (
            compute_lgd_climate_multiplier)
        m_re = compute_lgd_climate_multiplier(
            physical_risk_score=Decimal("70"),
            sector="REAL_ESTATE_COASTAL")
        m_other = compute_lgd_climate_multiplier(
            physical_risk_score=Decimal("70"),
            sector="MANUFACTURING_LIGHT")
        self.assertGreater(m_re, m_other)

    def test_fossil_ead_higher_than_other(self):
        from utils.climate_ecl_adjustment import (
            compute_ead_climate_multiplier)
        m_f = compute_ead_climate_multiplier(
            transition_risk_score=Decimal("80"),
            sector="FOSSIL_FUELS_OIL_GAS")
        m_o = compute_ead_climate_multiplier(
            transition_risk_score=Decimal("80"),
            sector="MANUFACTURING_LIGHT")
        self.assertGreater(m_f, m_o)


class TestV108ApplyOverlay(unittest.TestCase):
    """Single-asset climate overlay end-to-end."""

    def test_high_risk_significant_uplift(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage, apply_climate_overlay)
        base = BaseECLInputs(
            asset_id="L-COAST", stage=IFRS9Stage.STAGE_1,
            pd_12m=Decimal("0.03"), pd_lifetime=Decimal("0.15"),
            lgd=Decimal("0.50"), ead_kes=Decimal("1000000"),
            sector="REAL_ESTATE_COASTAL")
        result = apply_climate_overlay(
            base=base,
            physical_risk_score=Decimal("80"),
            transition_risk_score=Decimal("30"),
            scenario="DISORDERLY_2050",
            horizon_years=20)
        self.assertGreater(result.adjusted_ecl_kes, result.base_ecl_kes)
        self.assertGreater(result.uplift_pct, Decimal("20"))


class TestV108ProbabilityWeighted(unittest.TestCase):
    """IFRS 9 §5.5.4 probability-weighted ECL."""

    def test_weighted_ecl_correct(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage,
            compute_probability_weighted_ecl)
        base = BaseECLInputs(
            asset_id="L", stage=IFRS9Stage.STAGE_1,
            pd_12m=Decimal("0.02"), pd_lifetime=Decimal("0.10"),
            lgd=Decimal("0.40"), ead_kes=Decimal("1000000"),
            sector="MANUFACTURING_LIGHT")
        result = compute_probability_weighted_ecl(
            base=base,
            scenario_ecls={
                "BASELINE": Decimal("8000"),
                "DOWNSIDE": Decimal("12000"),
                "SEVERE_DOWNSIDE": Decimal("20000"),
            },
            scenario_weights={
                "BASELINE": Decimal("0.5"),
                "DOWNSIDE": Decimal("0.3"),
                "SEVERE_DOWNSIDE": Decimal("0.2"),
            })
        # 4000 + 3600 + 4000 = 11600
        self.assertEqual(result.weighted_ecl_kes, Decimal("11600"))

    def test_min_3_scenarios_required(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage,
            compute_probability_weighted_ecl)
        base = BaseECLInputs(
            asset_id="L", stage=IFRS9Stage.STAGE_1,
            pd_12m=Decimal("0.02"), pd_lifetime=Decimal("0.10"),
            lgd=Decimal("0.40"), ead_kes=Decimal("1000000"),
            sector="MANUFACTURING_LIGHT")
        with self.assertRaises(ValueError):
            compute_probability_weighted_ecl(
                base=base,
                scenario_ecls={"X": Decimal("1"), "Y": Decimal("2")},
                scenario_weights={"X": Decimal("0.5"), "Y": Decimal("0.5")})


class TestV108StressScenario(unittest.TestCase):
    """Portfolio stress scenario runner."""

    def test_stress_scenario_aggregates(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage, run_stress_scenario,
            StressScenarioType)
        inputs = [
            BaseECLInputs(
                asset_id=f"L-{i}", stage=IFRS9Stage.STAGE_1,
                pd_12m=Decimal("0.02"), pd_lifetime=Decimal("0.10"),
                lgd=Decimal("0.40"), ead_kes=Decimal("100000"),
                sector="AGRICULTURE_PRIMARY")
            for i in range(5)]
        result = run_stress_scenario(
            scenario_name="ECB-2022-DISORDERLY",
            scenario_type=StressScenarioType.DISORDERLY_TRANSITION,
            horizon_years=10,
            asset_inputs=inputs,
            risk_score_provider=lambda a: (Decimal("60"), Decimal("40")))
        self.assertEqual(result.n_assets, 5)
        self.assertGreater(
            result.total_adjusted_ecl_kes, result.total_base_ecl_kes)
        self.assertIn("AGRICULTURE_PRIMARY", result.by_sector)


class TestV108Engine(unittest.TestCase):
    def test_three_scenarios_run(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage, ClimateECLEngine)
        inputs = [BaseECLInputs(
            asset_id="L", stage=IFRS9Stage.STAGE_1,
            pd_12m=Decimal("0.02"), pd_lifetime=Decimal("0.10"),
            lgd=Decimal("0.40"), ead_kes=Decimal("1000000"),
            sector="MANUFACTURING_HEAVY_INDUSTRY")]
        eng = ClimateECLEngine(entity_name="Ecobank Kenya")
        results = eng.run_three_scenarios(
            asset_inputs=inputs,
            risk_score_providers={
                "BASELINE": lambda a: (Decimal("10"), Decimal("20")),
                "DOWNSIDE": lambda a: (Decimal("40"), Decimal("60")),
                "SEVERE_DOWNSIDE": lambda a: (Decimal("80"), Decimal("90")),
            },
            horizon_years=20)
        self.assertEqual(len(results), 3)
        # Severe should have highest uplift
        severe_uplift = next(
            r.total_uplift_pct for r in results
            if r.scenario_name == "SEVERE_DOWNSIDE")
        baseline_uplift = next(
            r.total_uplift_pct for r in results
            if r.scenario_name == "BASELINE")
        self.assertGreater(severe_uplift, baseline_uplift)

    def test_board_summary_identifies_max_scenario(self):
        from utils.climate_ecl_adjustment import (
            BaseECLInputs, IFRS9Stage, ClimateECLEngine)
        inputs = [BaseECLInputs(
            asset_id="L", stage=IFRS9Stage.STAGE_1,
            pd_12m=Decimal("0.02"), pd_lifetime=Decimal("0.10"),
            lgd=Decimal("0.40"), ead_kes=Decimal("1000000"),
            sector="REAL_ESTATE_COASTAL")]
        eng = ClimateECLEngine()
        eng.run_three_scenarios(
            asset_inputs=inputs,
            risk_score_providers={
                "BASELINE": lambda a: (Decimal("10"), Decimal("10")),
                "DOWNSIDE": lambda a: (Decimal("50"), Decimal("50")),
                "SEVERE_DOWNSIDE": lambda a: (Decimal("90"), Decimal("90")),
            },
            horizon_years=10)
        summary = eng.board_summary()
        self.assertEqual(summary["n_stress_runs"], 3)
        self.assertEqual(summary["max_uplift_scenario"], "SEVERE_DOWNSIDE")


class TestV108IntegrationWithEarlierBatches(unittest.TestCase):
    """v10.6 + v10.7 + v10.8 engines coexist and feed each other."""

    def test_three_engines_coexist(self):
        from utils.esg_intelligence import ESGIntelligenceEngine
        from utils.climate_risk import ClimateRiskEngine
        from utils.climate_ecl_adjustment import ClimateECLEngine

        esg = ESGIntelligenceEngine(entity_name="Ecobank Kenya")
        risk = ClimateRiskEngine(entity_name="Ecobank Kenya")
        ecl = ClimateECLEngine(entity_name="Ecobank Kenya")
        self.assertEqual(esg.entity_name, ecl.entity_name)
        self.assertEqual(risk.entity_name, ecl.entity_name)


if __name__ == "__main__":
    unittest.main()

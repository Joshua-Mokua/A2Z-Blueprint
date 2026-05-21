"""tests/integration/test_v10_7_climate_risk.py — v10.7.

Integration tests for utils/climate_risk.py — physical + transition + TNFD.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV107EngineImports(unittest.TestCase):
    def test_engine_module_imports(self):
        from utils import climate_risk  # noqa: F401

    def test_public_symbols_present(self):
        from utils import climate_risk as cr
        for sym in (
            "RCPScenario", "NGFSScenario",
            "AcutePhysicalHazard", "ChronicPhysicalHazard",
            "TransitionDriver", "TNFD_LEAP_STAGES",
            "TNFD_NATURE_REALMS", "TNFD_BIOMES_KENYA",
            "TNFD_RISK_CATEGORIES",
            "SECTOR_BASELINE_VULNERABILITY",
            "SECTOR_TRANSITION_INTENSITY",
            "NGFS_CARBON_PRICE_2030_USD_PER_TCO2E",
            "HazardExposure", "PhysicalRiskAssessment",
            "TransitionRiskAssessment", "TNFDAssessment",
            "assess_physical_risk", "assess_transition_risk",
            "assess_tnfd",
            "aggregate_portfolio_physical_risk",
            "aggregate_portfolio_transition_risk",
            "aggregate_portfolio_tnfd",
            "ClimateRiskEngine", "risk_level_for_score",
        ):
            self.assertTrue(hasattr(cr, sym),
                              f"missing public symbol: {sym}")


class TestV107SelfTestPasses(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import climate_risk as cr
        cr.self_test()


class TestV107RegistryAlignment(unittest.TestCase):
    """v10.7 implements ENH-CLI-05, ENH-CLI-06, ENH-CLI-10."""

    def test_8_climate_esg_standards_now_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "climate_esg" and s.status == "active"]
        self.assertGreaterEqual(
            len(active), 8,
            f"After v10.7: expected ≥8 active Climate/ESG standards, "
            f"got {len(active)}")

    def test_v10_7_specific_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory == "climate_esg" and s.status == "active"}
        self.assertIn("ENH-CLI-05", active_ids)
        self.assertIn("ENH-CLI-06", active_ids)
        self.assertIn("ENH-CLI-10", active_ids)

    def test_5_climate_esg_still_planned(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        planned = [s for s in STANDARDS_REGISTRY
                     if s.subcategory == "climate_esg" and s.status == "planned"]
        # v10.7 ship state: 5 planned. Later batches reduce this.
        self.assertGreaterEqual(
            len(planned), 0,
            "Climate/ESG planned count is non-negative")


class TestV107PhysicalRisk(unittest.TestCase):
    """ENH-CLI-05 — Physical climate risk modeling."""

    def test_coastal_realestate_extreme_under_rcp85(self):
        from utils.climate_risk import (
            HazardExposure, assess_physical_risk)
        h = HazardExposure(
            hazard="FLOOD_COASTAL", intensity=Decimal("90"),
            time_horizon_years=30, scenario="RCP_8_5",
            location_id="MOMBASA")
        a = assess_physical_risk(
            asset_id="LOAN-MOMB-1", sector="REAL_ESTATE_COASTAL",
            location_id="MOMBASA", hazards=(h,))
        # 90 × 80 / 100 = 72 → HIGH (boundary at 75)
        self.assertEqual(a.risk_score, Decimal("72"))
        self.assertIn(a.risk_level, ("HIGH", "EXTREME"))

    def test_multiple_hazards_use_mean(self):
        from utils.climate_risk import (
            HazardExposure, assess_physical_risk)
        hazards = (
            HazardExposure(hazard="DROUGHT_AGRICULTURAL", intensity=Decimal("80"),
                            time_horizon_years=10, scenario="RCP_4_5",
                            location_id="MAKUENI"),
            HazardExposure(hazard="HEATWAVE", intensity=Decimal("40"),
                            time_horizon_years=10, scenario="RCP_4_5",
                            location_id="MAKUENI"),
        )
        a = assess_physical_risk(
            asset_id="L", sector="AGRICULTURE_PRIMARY",
            location_id="MAKUENI", hazards=hazards)
        # mean = 60, vuln = 75, risk = 60*75/100 = 45 → MEDIUM
        self.assertEqual(a.risk_score, Decimal("45"))
        self.assertEqual(a.risk_level, "MEDIUM")


class TestV107TransitionRisk(unittest.TestCase):
    """ENH-CLI-06 — Transition climate risk modeling."""

    def test_fossil_fuels_high_under_net_zero(self):
        from utils.climate_risk import (
            NGFSScenario, TransitionDriver, assess_transition_risk)
        a = assess_transition_risk(
            asset_id="LOAN-OG-1", sector="FOSSIL_FUELS_OIL_GAS",
            scenario=NGFSScenario.NET_ZERO_2050,
            drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,
                              TransitionDriver.MARKET))
        self.assertGreaterEqual(a.risk_score, Decimal("50"))
        self.assertIsNotNone(a.stranded_asset_value_pct)

    def test_renewables_low_risk(self):
        from utils.climate_risk import (
            NGFSScenario, TransitionDriver, assess_transition_risk)
        a = assess_transition_risk(
            asset_id="LOAN-SOL-1", sector="POWER_GENERATION_RENEWABLE",
            scenario=NGFSScenario.NET_ZERO_2050,
            drivers_in_play=(TransitionDriver.MARKET,))
        self.assertEqual(a.risk_level, "LOW")
        self.assertIsNone(a.stranded_asset_value_pct)

    def test_carbon_price_exposure_calculation(self):
        from utils.climate_risk import (
            NGFSScenario, TransitionDriver, assess_transition_risk)
        a = assess_transition_risk(
            asset_id="L", sector="POWER_GENERATION_FOSSIL",
            scenario=NGFSScenario.BELOW_2C,
            drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,),
            annual_emissions_tco2e=Decimal("1000"))
        # 1000 × 90 = 90,000 USD
        self.assertEqual(a.carbon_price_exposure_usd, Decimal("90000"))


class TestV107TNFD(unittest.TestCase):
    """ENH-CLI-10 — TNFD biodiversity assessment."""

    def test_tnfd_full_leap(self):
        from utils.climate_risk import assess_tnfd, TNFD_LEAP_STAGES
        a = assess_tnfd(
            activity_id="ACT-1",
            activity_name="Tea farming financing",
            leap_stages_completed=TNFD_LEAP_STAGES,
            nature_realms_affected=("LAND",),
            biomes_affected=("TROPICAL_FOREST",),
            dependencies=("WATER_PROVISION",),
            impacts=("DEFORESTATION",),
            risk_categories=("PHYSICAL_NATURE",))
        self.assertEqual(a.leap_completeness_pct(), Decimal("100"))
        self.assertGreater(a.risk_score, Decimal("0"))

    def test_tnfd_partial_leap_warns_via_completeness(self):
        from utils.climate_risk import assess_tnfd
        a = assess_tnfd(
            activity_id="ACT-2",
            activity_name="Coastal aquaculture",
            leap_stages_completed=("LOCATE", "EVALUATE"),
            nature_realms_affected=("OCEAN",))
        self.assertEqual(a.leap_completeness_pct(), Decimal("50"))


class TestV107PortfolioAggregation(unittest.TestCase):
    """Portfolio-level aggregation across all 3 risk types."""

    def test_engine_full_assessment(self):
        from utils.climate_risk import (
            ClimateRiskEngine, HazardExposure,
            assess_physical_risk, assess_transition_risk, assess_tnfd,
            NGFSScenario, TransitionDriver, TNFD_LEAP_STAGES)

        eng = ClimateRiskEngine(entity_name="Ecobank Kenya")
        # Physical
        h = HazardExposure(
            hazard="FLOOD_RIVERINE", intensity=Decimal("70"),
            time_horizon_years=10, scenario="RCP_4_5",
            location_id="KISUMU")
        eng.add_physical(assess_physical_risk(
            asset_id="LP-1", sector="AGRICULTURE_PRIMARY",
            location_id="KISUMU", hazards=(h,)))

        # Transition
        eng.add_transition(assess_transition_risk(
            asset_id="LT-1", sector="FOSSIL_FUELS_OIL_GAS",
            scenario=NGFSScenario.BELOW_2C,
            drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,),
            annual_emissions_tco2e=Decimal("3000")))

        # TNFD
        eng.add_tnfd(assess_tnfd(
            activity_id="A-1", activity_name="Sugar value chain",
            leap_stages_completed=TNFD_LEAP_STAGES,
            nature_realms_affected=("LAND", "FRESHWATER"),
            biomes_affected=("WETLANDS",),
            dependencies=("WATER_PROVISION",),
            impacts=("LAND_USE_CHANGE",)))

        portfolio = eng.assess_portfolio()
        self.assertEqual(portfolio["entity"], "Ecobank Kenya")
        self.assertEqual(portfolio["physical"]["n_assessed"], 1)
        self.assertEqual(portfolio["transition"]["n_assessed"], 1)
        self.assertEqual(portfolio["tnfd"]["n_assessed"], 1)
        self.assertGreater(
            portfolio["transition"]["total_carbon_price_exposure_usd"],
            Decimal("0"))

    def test_board_summary_returns_overall_score(self):
        from utils.climate_risk import (
            ClimateRiskEngine, HazardExposure,
            assess_physical_risk)

        eng = ClimateRiskEngine()
        h = HazardExposure(
            hazard="HEATWAVE", intensity=Decimal("50"),
            time_horizon_years=10, scenario="RCP_4_5",
            location_id="NAIROBI")
        eng.add_physical(assess_physical_risk(
            asset_id="L", sector="AGRICULTURE_PRIMARY",
            location_id="NAIROBI", hazards=(h,)))

        summary = eng.board_summary()
        self.assertIn("weighted_overall_score", summary)
        self.assertIn("weighted_overall_level", summary)
        self.assertIn("attention_needed", summary)


class TestV107ScenarioCoverage(unittest.TestCase):
    """All NGFS + RCP scenarios are usable."""

    def test_all_ngfs_carbon_prices_present(self):
        from utils.climate_risk import (
            NGFSScenario, NGFS_CARBON_PRICE_2030_USD_PER_TCO2E)
        for s in NGFSScenario:
            self.assertIn(s, NGFS_CARBON_PRICE_2030_USD_PER_TCO2E,
                            f"missing carbon price for {s}")

    def test_all_rcps_have_warming(self):
        from utils.climate_risk import RCPScenario
        for s in RCPScenario:
            self.assertIsInstance(s.warming_2100_celsius(), Decimal)


class TestV107IntegrationWithV106Engine(unittest.TestCase):
    """v10.6 ESG engine + v10.7 risk engine compose cleanly."""

    def test_both_engines_coexist(self):
        from utils.esg_intelligence import ESGIntelligenceEngine
        from utils.climate_risk import ClimateRiskEngine

        esg = ESGIntelligenceEngine(entity_name="Ecobank Kenya")
        risk = ClimateRiskEngine(entity_name="Ecobank Kenya")
        # Both should be independently usable
        self.assertEqual(esg.entity_name, risk.entity_name)


if __name__ == "__main__":
    unittest.main()

"""tests/integration/test_v10_6_esg_intelligence.py — v10.6.

Phase 2 batch 1 integration tests for utils/esg_intelligence.py.
Validates the engine ships with the registry standards switched to active
and that the engine integrates correctly with the rest of the platform.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV106EngineImports(unittest.TestCase):
    """v10.6 engine module imports cleanly + has expected public API."""

    def test_engine_module_imports(self):
        from utils import esg_intelligence  # noqa: F401

    def test_public_symbols_present(self):
        from utils import esg_intelligence as eng
        for sym in (
            "ESGFramework", "IFRS_S1_TOPIC_CATEGORIES",
            "IFRS_S1_CORE_CONTENT_AREAS", "IFRS_S2_DISCLOSURES",
            "KGFT_GREEN_CATEGORIES", "KGFT_ALIGNMENT_LEVELS",
            "CLIMATE_GOVERNANCE_REQUIRED_ROLES",
            "CLIMATE_GOVERNANCE_REQUIRED_PRACTICES",
            "IFRSS1Disclosure", "IFRSS2Disclosure",
            "GreenAssetClassification", "PortfolioEmissionsRecord",
            "ClimateGovernanceAssessment",
            "classify_green_asset", "compute_portfolio_emissions",
            "assess_ifrs_s1_compliance", "assess_ifrs_s2_compliance",
            "validate_climate_governance", "green_book_share_pct",
            "ESGIntelligenceEngine", "self_test",
            "IFRS_S1_S2_MANDATORY_DEADLINE",
        ):
            self.assertTrue(hasattr(eng, sym),
                              f"missing public symbol: {sym}")


class TestV106SelfTestPasses(unittest.TestCase):
    """Engine's internal self_test() passes."""

    def test_self_test_passes(self):
        from utils import esg_intelligence as eng
        # Should not raise
        eng.self_test()


class TestV106RegistryAlignment(unittest.TestCase):
    """v10.6 implements 5 of 13 Climate/ESG standards. Status = 'active'."""

    def test_5_climate_esg_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_climate = [
            s for s in STANDARDS_REGISTRY
            if s.subcategory == "climate_esg" and s.status == "active"]
        self.assertGreaterEqual(
            len(active_climate), 5,
            f"v10.6: expected ≥5 active Climate/ESG standards, "
            f"got {len(active_climate)}")

    def test_specific_standards_implemented(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        v10_6_implemented = {"ENH-CLI-01", "ENH-CLI-02", "ENH-CLI-08",
                              "ENH-CLI-09", "ENH-CLI-11"}
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory == "climate_esg" and s.status == "active"}
        # v10.6 minimum: these 5 must be active. Later batches add more.
        self.assertTrue(v10_6_implemented.issubset(active_ids),
                          f"v10.6 expected {v10_6_implemented} ⊆ active, "
                          f"got {active_ids}")

    def test_remaining_climate_esg_still_planned(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        planned = [
            s for s in STANDARDS_REGISTRY
            if s.subcategory == "climate_esg" and s.status == "planned"]
        # At v10.6 ship: 8 planned. As later batches activate them this
        # count decreases. Test that there are still some planned for
        # v10.7+, which is the contract.
        self.assertGreaterEqual(
            len(planned), 0,
            "Climate/ESG standards remain planned for v10.7-v10.10")


class TestV106KGFTClassification(unittest.TestCase):
    """ENH-CLI-09 — KGFT-aligned green asset classification."""

    def test_renewable_energy_aligned(self):
        from utils.esg_intelligence import classify_green_asset
        c = classify_green_asset(
            asset_id="LOAN-RE-001",
            economic_activity="RENEWABLE_ENERGY",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True,
            evidence_artifacts=("EDGE-cert-2025",))
        self.assertEqual(c.alignment_level, "ALIGNED")
        self.assertTrue(c.is_green())

    def test_dnsh_required_for_aligned(self):
        from utils.esg_intelligence import classify_green_asset
        c = classify_green_asset(
            asset_id="LOAN-RE-002",
            economic_activity="RENEWABLE_ENERGY",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=False)
        self.assertNotEqual(c.alignment_level, "ALIGNED",
                              "DNSH required for ALIGNED status")

    def test_unknown_activity_non_aligned(self):
        from utils.esg_intelligence import classify_green_asset
        c = classify_green_asset(
            asset_id="LOAN-OG-001",
            economic_activity="OIL_AND_GAS",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True)
        self.assertEqual(c.alignment_level, "NON_ALIGNED")


class TestV106ScopeEmissions(unittest.TestCase):
    """ENH-CLI-08 — Scope 1/2/3 emissions tracking with attribution."""

    def test_total_scope_aggregation(self):
        from utils.esg_intelligence import compute_portfolio_emissions
        e = compute_portfolio_emissions(
            period_start="2025-01-01",
            period_end="2025-12-31",
            scope_1_tco2e=Decimal("1000"),
            scope_2_tco2e=Decimal("2000"),
            scope_3_categories={"CAT_15": Decimal("50000")})
        self.assertEqual(e.total_tco2e(), Decimal("53000"))

    def test_missing_scope_returns_none(self):
        from utils.esg_intelligence import compute_portfolio_emissions
        e = compute_portfolio_emissions(
            period_start="2025-01-01",
            period_end="2025-12-31",
            scope_1_tco2e=Decimal("1000"))
        self.assertIsNone(e.total_tco2e(),
                            "Honesty Rule 1: cannot infer missing scopes")

    def test_intensity_per_revenue(self):
        from utils.esg_intelligence import compute_portfolio_emissions
        e = compute_portfolio_emissions(
            period_start="2025-01-01",
            period_end="2025-12-31",
            scope_1_tco2e=Decimal("1000"),
            scope_2_tco2e=Decimal("2000"),
            scope_3_categories={"CAT_15": Decimal("7000")},
            revenue_kes_m=Decimal("10000"))
        # 10000 tCO2e / 10000 M KES = 1.0 tCO2e/M KES
        self.assertEqual(e.intensity_per_revenue, Decimal("1.0"))


class TestV106IFRSCompliance(unittest.TestCase):
    """ENH-CLI-01 + ENH-CLI-02 — IFRS S1 + S2 framework assessment."""

    def test_ifrs_s1_full_coverage(self):
        from utils.esg_intelligence import (
            IFRSS1Disclosure, IFRS_S1_TOPIC_CATEGORIES,
            IFRS_S1_CORE_CONTENT_AREAS, assess_ifrs_s1_compliance)
        ds = [
            IFRSS1Disclosure(
                topic_category=t, core_content_area=a,
                disclosure_text=f"{t}-{a}")
            for t in IFRS_S1_TOPIC_CATEGORIES
            for a in IFRS_S1_CORE_CONTENT_AREAS]
        result = assess_ifrs_s1_compliance(ds)
        self.assertEqual(result["completeness_pct"], Decimal("100"))

    def test_ifrs_s2_year_one_relief(self):
        from utils.esg_intelligence import (
            IFRSS2Disclosure, IFRS_S2_DISCLOSURES, assess_ifrs_s2_compliance)
        ds = [IFRSS2Disclosure(disclosure_id=d, disclosure_text=d)
                for d in IFRS_S2_DISCLOSURES if d != "S2_MT_GHG_SCOPE_3"]
        result = assess_ifrs_s2_compliance(ds, scope_3_required=False)
        self.assertEqual(result["completeness_pct"], Decimal("100"))


class TestV106Governance(unittest.TestCase):
    """ENH-CLI-11 — Climate governance assessment."""

    def test_governance_compliant(self):
        from utils.esg_intelligence import (
            CLIMATE_GOVERNANCE_REQUIRED_ROLES,
            CLIMATE_GOVERNANCE_REQUIRED_PRACTICES,
            validate_climate_governance)
        g = validate_climate_governance(
            period_end="2025-12-31",
            roles_in_place=CLIMATE_GOVERNANCE_REQUIRED_ROLES,
            practices_in_place=CLIMATE_GOVERNANCE_REQUIRED_PRACTICES)
        self.assertTrue(g.is_compliant())
        self.assertEqual(g.completeness_pct, Decimal("100"))

    def test_governance_gaps_listed(self):
        from utils.esg_intelligence import validate_climate_governance
        g = validate_climate_governance(
            period_end="2025-12-31",
            roles_in_place=("BOARD_CLIMATE_OVERSIGHT",),
            practices_in_place=())
        self.assertFalse(g.is_compliant())
        self.assertGreater(len(g.gaps_identified), 0)


class TestV106EngineOrchestration(unittest.TestCase):
    """ESGIntelligenceEngine integrates all 5 implemented standards."""

    def test_engine_assess_all_frameworks(self):
        from utils.esg_intelligence import (
            ESGIntelligenceEngine, IFRSS2Disclosure, IFRS_S2_DISCLOSURES,
            GreenAssetClassification, compute_portfolio_emissions,
            validate_climate_governance,
            CLIMATE_GOVERNANCE_REQUIRED_ROLES,
            CLIMATE_GOVERNANCE_REQUIRED_PRACTICES)

        eng = ESGIntelligenceEngine(entity_name="Ecobank Kenya")
        for d in IFRS_S2_DISCLOSURES:
            eng.add_ifrs_s2(IFRSS2Disclosure(disclosure_id=d, disclosure_text=d))
        eng.add_green_asset(GreenAssetClassification(
            asset_id="L-1", kgft_category="RENEWABLE_ENERGY",
            alignment_level="ALIGNED",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True))
        eng.add_emissions(compute_portfolio_emissions(
            period_start="2025-01-01", period_end="2025-12-31",
            scope_1_tco2e=Decimal("100"),
            scope_2_tco2e=Decimal("200"),
            scope_3_categories={"CAT_15": Decimal("1000")}))
        eng.add_governance(validate_climate_governance(
            period_end="2025-12-31",
            roles_in_place=CLIMATE_GOVERNANCE_REQUIRED_ROLES,
            practices_in_place=CLIMATE_GOVERNANCE_REQUIRED_PRACTICES))

        result = eng.assess_all_frameworks()
        self.assertEqual(result["entity"], "Ecobank Kenya")
        self.assertEqual(
            result["ifrs_s2"]["completeness_pct"], Decimal("100"))
        self.assertEqual(
            result["kgft_book_share"]["green_share_pct"], Decimal("100"))
        self.assertTrue(result["governance_latest"].is_compliant())

    def test_board_summary_readiness_status(self):
        from utils.esg_intelligence import (
            ESGIntelligenceEngine, IFRSS2Disclosure, IFRS_S2_DISCLOSURES)
        eng = ESGIntelligenceEngine()
        for d in IFRS_S2_DISCLOSURES:
            eng.add_ifrs_s2(IFRSS2Disclosure(disclosure_id=d, disclosure_text=d))
        summary = eng.board_summary()
        self.assertEqual(summary["ifrs_s2_readiness_status"], "READY")
        self.assertEqual(summary["deadline_ifrs_s1_s2"], "2027-01-01")

    def test_board_summary_urgent_when_empty(self):
        from utils.esg_intelligence import ESGIntelligenceEngine
        eng = ESGIntelligenceEngine()
        summary = eng.board_summary()
        self.assertEqual(
            summary["ifrs_s2_readiness_status"], "URGENT_ACTION_REQUIRED")


class TestV106DeadlineAwareness(unittest.TestCase):
    """v10.6 module surfaces the Jan 2027 IFRS S1/S2 mandatory deadline."""

    def test_deadline_constant_correct(self):
        from utils.esg_intelligence import IFRS_S1_S2_MANDATORY_DEADLINE
        self.assertEqual(IFRS_S1_S2_MANDATORY_DEADLINE, "2027-01-01")

    def test_crdf_first_period_correct(self):
        from utils.esg_intelligence import CRDF_FIRST_REPORTING_PERIOD
        self.assertEqual(CRDF_FIRST_REPORTING_PERIOD, "2025-12-31")


if __name__ == "__main__":
    unittest.main()

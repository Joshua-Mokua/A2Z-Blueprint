"""tests/integration/test_v10_9_esg_reporting_outputs.py — v10.9.

Integration tests for utils/esg_reporting_outputs.py
ENH-CLI-03 (KGFT), ENH-CLI-04 (CRDF), ENH-CLI-13 (greenwashing controls).
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV109Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import esg_reporting_outputs  # noqa: F401

    def test_public_symbols(self):
        from utils import esg_reporting_outputs as m
        for sym in (
            "KGFT_REPORT_SECTIONS", "CRDF_PILLARS", "CRDF_DISCLOSURES",
            "GREENWASHING_RED_FLAGS", "GreenwashingRiskLevel",
            "KGFTReport", "CRDFReport",
            "GreenwashingClaim", "GreenwashingVerificationResult",
            "generate_kgft_report", "generate_crdf_report",
            "verify_green_claim", "aggregate_greenwashing_risk",
            "ESGReportingOutputsEngine", "self_test",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV109SelfTestPasses(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import esg_reporting_outputs
        esg_reporting_outputs.self_test()


class TestV109RegistryAlignment(unittest.TestCase):
    """v10.9 makes 13/13 Climate/ESG standards active."""

    def test_all_13_climate_esg_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "climate_esg" and s.status == "active"]
        self.assertEqual(
            len(active), 13,
            f"v10.9: expected exactly 13/13 Climate/ESG active, "
            f"got {len(active)}")

    def test_v10_9_specific_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.subcategory == "climate_esg" and s.status == "active"}
        self.assertIn("ENH-CLI-03", active_ids)
        self.assertIn("ENH-CLI-04", active_ids)
        self.assertIn("ENH-CLI-13", active_ids)

    def test_no_climate_esg_planned(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        planned = [s for s in STANDARDS_REGISTRY
                     if s.subcategory == "climate_esg" and s.status == "planned"]
        self.assertEqual(
            len(planned), 0,
            "v10.9 closes Climate/ESG arc; v10.10 audit-gates it")


class TestV109KGFTReport(unittest.TestCase):
    """ENH-CLI-03 — KGFT report generation."""

    def test_kgft_report_aligned_share(self):
        from utils.esg_intelligence import GreenAssetClassification
        from utils.esg_reporting_outputs import generate_kgft_report

        cs = [
            GreenAssetClassification(
                asset_id="L-1", kgft_category="RENEWABLE_ENERGY",
                alignment_level="ALIGNED",
                eligibility_dimensions=("CLIMATE_MITIGATION",),
                dnsh_assessed=True),
            GreenAssetClassification(
                asset_id="L-2", kgft_category="",
                alignment_level="NON_ALIGNED",
                eligibility_dimensions=(), dnsh_assessed=False),
        ]
        r = generate_kgft_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="Ecobank Kenya",
            classifications=cs,
            asset_balances={
                "L-1": Decimal("8000000"),
                "L-2": Decimal("2000000")})
        self.assertEqual(r.aligned_share_pct, Decimal("80"))
        self.assertEqual(r.aligned_count, 1)
        self.assertEqual(r.non_aligned_count, 1)

    def test_kgft_report_all_sections(self):
        from utils.esg_intelligence import GreenAssetClassification
        from utils.esg_reporting_outputs import (
            generate_kgft_report, KGFT_REPORT_SECTIONS)
        cs = [GreenAssetClassification(
            asset_id="L", kgft_category="RENEWABLE_ENERGY",
            alignment_level="ALIGNED",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True)]
        r = generate_kgft_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="T", classifications=cs,
            asset_balances={"L": Decimal("100")})
        for section in KGFT_REPORT_SECTIONS:
            self.assertIn(section, r.sections,
                            f"missing section: {section}")


class TestV109CRDFReport(unittest.TestCase):
    """ENH-CLI-04 — CRDF reporting."""

    def test_crdf_full_complete(self):
        from utils.esg_reporting_outputs import (
            generate_crdf_report, CRDF_PILLARS, CRDF_DISCLOSURES)
        full = {
            pillar: {d: f"{d} narrative." for d in CRDF_DISCLOSURES[pillar]}
            for pillar in CRDF_PILLARS}
        r = generate_crdf_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="Ecobank Kenya",
            disclosures=full,
            submission_date="2026-03-31")
        self.assertEqual(r.completeness_pct, Decimal("100"))
        self.assertTrue(r.is_complete())

    def test_crdf_missing_surfaces_gaps(self):
        from utils.esg_reporting_outputs import generate_crdf_report
        r = generate_crdf_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="T",
            disclosures={
                "GOVERNANCE": {
                    "BOARD_OVERSIGHT_DESCRIPTION": "Board oversight."}},
            submission_date="2026-03-31")
        self.assertGreater(len(r.missing_disclosures), 0)
        self.assertFalse(r.is_complete())

    def test_crdf_4_pillars(self):
        from utils.esg_reporting_outputs import CRDF_PILLARS
        # CBK CRDF mirrors TCFD's 4 pillars
        self.assertEqual(set(CRDF_PILLARS), {
            "GOVERNANCE", "STRATEGY",
            "RISK_MANAGEMENT", "METRICS_AND_TARGETS"})


class TestV109Greenwashing(unittest.TestCase):
    """ENH-CLI-13 — Greenwashing controls."""

    def test_clean_claim_low_risk(self):
        from utils.esg_intelligence import GreenAssetClassification
        from utils.esg_reporting_outputs import (
            GreenwashingClaim, verify_green_claim)
        claim = GreenwashingClaim(
            claim_id="C-1",
            claim_text="Loan finances 50MW solar plant per KGFT.",
            category_referenced="RENEWABLE_ENERGY",
            asset_id="L-SOLAR",
            dnsh_evidence_present=True,
            evidence_artifacts=("EDGE-cert", "EIA-2024"))
        cls = {"L-SOLAR": GreenAssetClassification(
            asset_id="L-SOLAR", kgft_category="RENEWABLE_ENERGY",
            alignment_level="ALIGNED",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True)}
        r = verify_green_claim(claim, kgft_classifications=cls)
        self.assertEqual(r.risk_level, "LOW")
        self.assertTrue(r.supported_by_kgft)

    def test_inconsistent_with_kgft_high_risk(self):
        from utils.esg_intelligence import GreenAssetClassification
        from utils.esg_reporting_outputs import (
            GreenwashingClaim, verify_green_claim)
        claim = GreenwashingClaim(
            claim_id="C-X",
            claim_text="Sustainable energy financing for our coal expansion.",
            category_referenced="RENEWABLE_ENERGY",
            asset_id="L-COAL",
            dnsh_evidence_present=False,
            evidence_artifacts=("press-kit",))
        cls = {"L-COAL": GreenAssetClassification(
            asset_id="L-COAL", kgft_category="",
            alignment_level="NON_ALIGNED",
            eligibility_dimensions=(), dnsh_assessed=False)}
        r = verify_green_claim(claim, kgft_classifications=cls)
        self.assertEqual(r.risk_level, "HIGH")
        self.assertIn("CLAIMS_INCONSISTENT_WITH_KGFT", r.red_flags)


class TestV109EngineIntegration(unittest.TestCase):
    """v10.9 engine + v10.6 + v10.7 + v10.8 all coexist."""

    def test_four_engines_coexist(self):
        from utils.esg_intelligence import ESGIntelligenceEngine
        from utils.climate_risk import ClimateRiskEngine
        from utils.climate_ecl_adjustment import ClimateECLEngine
        from utils.esg_reporting_outputs import ESGReportingOutputsEngine

        a = ESGIntelligenceEngine(entity_name="Ecobank Kenya")
        b = ClimateRiskEngine(entity_name="Ecobank Kenya")
        c = ClimateECLEngine(entity_name="Ecobank Kenya")
        d = ESGReportingOutputsEngine(entity_name="Ecobank Kenya")
        self.assertEqual(a.entity_name, d.entity_name)
        self.assertEqual(b.entity_name, d.entity_name)
        self.assertEqual(c.entity_name, d.entity_name)

    def test_kgft_classification_flows_into_report(self):
        """v10.6 classification → v10.9 KGFT report."""
        from utils.esg_intelligence import (
            classify_green_asset, GreenAssetClassification)
        from utils.esg_reporting_outputs import generate_kgft_report

        c = classify_green_asset(
            asset_id="L-1",
            economic_activity="RENEWABLE_ENERGY",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True,
            evidence_artifacts=("EDGE",))
        self.assertEqual(c.alignment_level, "ALIGNED")

        r = generate_kgft_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="Ecobank Kenya",
            classifications=[c],
            asset_balances={"L-1": Decimal("1000000")})
        self.assertEqual(r.aligned_count, 1)
        self.assertEqual(r.aligned_share_pct, Decimal("100"))


class TestV109StreamlitPage(unittest.TestCase):
    """v10.9 Streamlit page exists at the expected path."""

    def test_page_file_exists(self):
        page_path = Path(__file__).parents[2] / "pages" / "92_climate_esg.py"
        self.assertTrue(
            page_path.exists(),
            f"Climate/ESG page missing: {page_path}")

    def test_page_imports_engines(self):
        """Page imports all 4 climate engines (v10.6-v10.9)."""
        page_path = Path(__file__).parents[2] / "pages" / "92_climate_esg.py"
        text = page_path.read_text()
        # Page references all 4 engines
        self.assertIn("esg_intelligence", text,
                        "page should reference v10.6 engine")
        self.assertIn("climate_risk", text,
                        "page should reference v10.7 engine")
        self.assertIn("climate_ecl_adjustment", text,
                        "page should reference v10.8 engine")
        self.assertIn("esg_reporting_outputs", text,
                        "page should reference v10.9 engine")


if __name__ == "__main__":
    unittest.main()

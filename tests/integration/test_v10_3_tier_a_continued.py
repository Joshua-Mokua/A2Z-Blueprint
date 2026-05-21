"""tests/integration/test_v10_3_tier_a_continued.py — v10.3.

Integration tests for v10.3: Tier A continued (Treasury + Revenue + Finance
+ Risk + Trade) + NEW Climate/ESG module.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV103Modules(unittest.TestCase):
    """v10.3 modules: Treasury + Revenue + Finance + Risk + Trade + Climate/ESG."""

    def test_v10_3_minimum_count(self):
        """v10.3 brings total enhancement standards to ≥132."""
        from utils.standards_registry import STANDARDS_REGISTRY
        enh = [s for s in STANDARDS_REGISTRY if s.category == "enhancement"]
        self.assertGreaterEqual(len(enh), 132,
                                  "v10.3: expected ≥132 enhancement standards")

    def test_treasury_module_complete(self):
        from utils.standards_registry import TREASURY_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(TREASURY_ENHANCEMENT_STANDARDS), 16)
        ids = {s.standard_id for s in TREASURY_ENHANCEMENT_STANDARDS}
        for n in range(231, 241):
            self.assertIn(f"ENH-{n}", ids)

    def test_revenue_assurance_complete(self):
        from utils.standards_registry import REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS), 8)
        ids = {s.standard_id for s in REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS}
        for n in range(241, 249):
            self.assertIn(f"ENH-{n}", ids)

    def test_finance_complete(self):
        from utils.standards_registry import FINANCE_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(FINANCE_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in FINANCE_ENHANCEMENT_STANDARDS}
        for n in range(249, 259):
            self.assertIn(f"ENH-{n}", ids)

    def test_credit_model_risk_complete(self):
        from utils.standards_registry import CREDIT_MODEL_RISK_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(CREDIT_MODEL_RISK_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in CREDIT_MODEL_RISK_ENHANCEMENT_STANDARDS}
        for n in range(259, 269):
            self.assertIn(f"ENH-{n}", ids)

    def test_trade_finance_complete(self):
        from utils.standards_registry import TRADE_FINANCE_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(TRADE_FINANCE_ENHANCEMENT_STANDARDS), 12)
        ids = {s.standard_id for s in TRADE_FINANCE_ENHANCEMENT_STANDARDS}
        for n in range(269, 281):
            self.assertIn(f"ENH-{n}", ids)


class TestClimateESGModule(unittest.TestCase):
    """v10.3 NEW Climate/ESG module — IFRS S1/S2 critical (Jan 2027)."""

    def test_climate_esg_module_present(self):
        from utils.standards_registry import CLIMATE_ESG_STANDARDS
        self.assertGreaterEqual(len(CLIMATE_ESG_STANDARDS), 13,
                                  "Climate/ESG: expected ≥13 standards")

    def test_climate_esg_all_research_addition(self):
        """All Climate/ESG standards are research-derived (not in doc)."""
        from utils.standards_registry import CLIMATE_ESG_STANDARDS
        for s in CLIMATE_ESG_STANDARDS:
            self.assertEqual(s.source, "research_addition",
                              f"{s.standard_id}: Climate/ESG should be "
                              f"research_addition (not in Continuation.docx)")

    def test_climate_esg_all_tier_a(self):
        """All Climate/ESG at Tier A (CRITICAL — Jan 2027 deadline)."""
        from utils.standards_registry import CLIMATE_ESG_STANDARDS
        for s in CLIMATE_ESG_STANDARDS:
            self.assertEqual(s.priority_tier, "A",
                              f"{s.standard_id}: Climate/ESG must be Tier A")

    def test_climate_esg_implementation_batch_first(self):
        """Climate/ESG slated for v10.6+ (first Phase 2 sub-arc)."""
        from utils.standards_registry import CLIMATE_ESG_STANDARDS
        for s in CLIMATE_ESG_STANDARDS:
            self.assertIn("v10.6", s.implementation_batch,
                            f"{s.standard_id}: must implement at v10.6+ "
                            f"to meet Jan 2027 IFRS S1/S2 deadline")

    def test_ifrs_s1_s2_present(self):
        """IFRS S1 and S2 explicit standards present."""
        from utils.standards_registry import CLIMATE_ESG_STANDARDS
        ids = {s.standard_id for s in CLIMATE_ESG_STANDARDS}
        self.assertIn("ENH-CLI-01", ids, "IFRS S1 standard missing")
        self.assertIn("ENH-CLI-02", ids, "IFRS S2 standard missing")

    def test_kgft_crdf_present(self):
        """Kenya Green Finance Taxonomy + CRDF reporting standards present."""
        from utils.standards_registry import CLIMATE_ESG_STANDARDS
        ids = {s.standard_id for s in CLIMATE_ESG_STANDARDS}
        self.assertIn("ENH-CLI-03", ids, "KGFT engine missing")
        self.assertIn("ENH-CLI-04", ids, "CRDF reporting missing")


class TestV103PriorityDistribution(unittest.TestCase):
    """v10.3 should add ~92 Tier A + ~30 Tier B + 0 Tier C."""

    def test_tier_a_growth(self):
        """v10.3 brings Tier A standards to ≥92."""
        from utils.standards_registry import STANDARDS_REGISTRY
        tier_a = [s for s in STANDARDS_REGISTRY if s.priority_tier == "A"]
        self.assertGreaterEqual(len(tier_a), 92)

    def test_tier_b_growth(self):
        """v10.3 introduces Tier B (Revenue + Finance + Trade)."""
        from utils.standards_registry import STANDARDS_REGISTRY
        tier_b = [s for s in STANDARDS_REGISTRY if s.priority_tier == "B"]
        self.assertGreaterEqual(len(tier_b), 30)


if __name__ == "__main__":
    unittest.main()

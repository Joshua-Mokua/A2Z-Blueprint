"""tests/integration/test_v10_4_tier_b_c_modules.py — v10.4.

Integration tests for v10.4: 10 remaining modules from Continuation.docx
(IT/Banca/Command/Competitor/C360/Props/Segments/Partners/SLA/Campaigns).
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV104Modules(unittest.TestCase):
    """v10.4 modules: 10 remaining Continuation.docx sections."""

    def test_v10_4_minimum_count(self):
        """v10.4 brings total enhancement standards to ≥234."""
        from utils.standards_registry import STANDARDS_REGISTRY
        enh = [s for s in STANDARDS_REGISTRY if s.category == "enhancement"]
        self.assertGreaterEqual(len(enh), 234,
                                  "v10.4: expected ≥234 enhancement standards")

    def test_it_digital_complete(self):
        from utils.standards_registry import IT_DIGITAL_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(IT_DIGITAL_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in IT_DIGITAL_ENHANCEMENT_STANDARDS}
        for n in range(291, 301):
            self.assertIn(f"ENH-{n}", ids)

    def test_bancassurance_complete(self):
        from utils.standards_registry import BANCASSURANCE_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(BANCASSURANCE_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in BANCASSURANCE_ENHANCEMENT_STANDARDS}
        for n in range(301, 311):
            self.assertIn(f"ENH-{n}", ids)

    def test_command_centre_complete(self):
        from utils.standards_registry import COMMAND_CENTRE_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(COMMAND_CENTRE_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in COMMAND_CENTRE_ENHANCEMENT_STANDARDS}
        for n in range(311, 321):
            self.assertIn(f"ENH-{n}", ids)

    def test_competitor_intel_complete(self):
        from utils.standards_registry import COMPETITOR_INTEL_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(COMPETITOR_INTEL_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in COMPETITOR_INTEL_ENHANCEMENT_STANDARDS}
        for n in range(327, 337):
            self.assertIn(f"ENH-{n}", ids)

    def test_customer_360_complete(self):
        from utils.standards_registry import CUSTOMER_360_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(CUSTOMER_360_ENHANCEMENT_STANDARDS), 12)
        ids = {s.standard_id for s in CUSTOMER_360_ENHANCEMENT_STANDARDS}
        for n in range(337, 349):
            self.assertIn(f"ENH-{n}", ids)

    def test_propositions_complete(self):
        from utils.standards_registry import PROPOSITIONS_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(PROPOSITIONS_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in PROPOSITIONS_ENHANCEMENT_STANDARDS}
        for n in range(349, 359):
            self.assertIn(f"ENH-{n}", ids)

    def test_specialized_segments_complete(self):
        from utils.standards_registry import (
            SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS)
        self.assertGreaterEqual(
            len(SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id
                for s in SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS}
        for n in range(359, 369):
            self.assertIn(f"ENH-{n}", ids)

    def test_partnerships_complete(self):
        from utils.standards_registry import PARTNERSHIPS_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(PARTNERSHIPS_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in PARTNERSHIPS_ENHANCEMENT_STANDARDS}
        for n in range(369, 379):
            self.assertIn(f"ENH-{n}", ids)

    def test_sla_tracker_complete(self):
        from utils.standards_registry import SLA_TRACKER_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(SLA_TRACKER_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in SLA_TRACKER_ENHANCEMENT_STANDARDS}
        for n in range(379, 389):
            self.assertIn(f"ENH-{n}", ids)

    def test_campaigns_complete(self):
        from utils.standards_registry import CAMPAIGNS_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(CAMPAIGNS_ENHANCEMENT_STANDARDS), 10)
        ids = {s.standard_id for s in CAMPAIGNS_ENHANCEMENT_STANDARDS}
        for n in range(389, 399):
            self.assertIn(f"ENH-{n}", ids)


class TestV104PriorityCorrect(unittest.TestCase):
    """v10.4 module priority tier assignments."""

    def test_it_digital_tier_b(self):
        from utils.standards_registry import IT_DIGITAL_ENHANCEMENT_STANDARDS
        for s in IT_DIGITAL_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "B")

    def test_bancassurance_tier_b(self):
        from utils.standards_registry import BANCASSURANCE_ENHANCEMENT_STANDARDS
        for s in BANCASSURANCE_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "B")

    def test_command_centre_tier_b(self):
        from utils.standards_registry import COMMAND_CENTRE_ENHANCEMENT_STANDARDS
        for s in COMMAND_CENTRE_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "B")

    def test_customer_360_tier_b(self):
        from utils.standards_registry import CUSTOMER_360_ENHANCEMENT_STANDARDS
        for s in CUSTOMER_360_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "B")

    def test_sla_tracker_tier_b(self):
        from utils.standards_registry import SLA_TRACKER_ENHANCEMENT_STANDARDS
        for s in SLA_TRACKER_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "B")

    def test_competitor_intel_tier_c(self):
        from utils.standards_registry import (
            COMPETITOR_INTEL_ENHANCEMENT_STANDARDS)
        for s in COMPETITOR_INTEL_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "C")

    def test_propositions_tier_c(self):
        from utils.standards_registry import PROPOSITIONS_ENHANCEMENT_STANDARDS
        for s in PROPOSITIONS_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "C")

    def test_specialized_segments_tier_c(self):
        from utils.standards_registry import (
            SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS)
        for s in SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "C")

    def test_partnerships_tier_c(self):
        from utils.standards_registry import PARTNERSHIPS_ENHANCEMENT_STANDARDS
        for s in PARTNERSHIPS_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "C")

    def test_campaigns_tier_c(self):
        from utils.standards_registry import CAMPAIGNS_ENHANCEMENT_STANDARDS
        for s in CAMPAIGNS_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "C")


class TestV104DistributionCorrect(unittest.TestCase):
    """v10.4 brings expected total counts."""

    def test_total_standards_246(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        self.assertGreaterEqual(len(STANDARDS_REGISTRY), 246)

    def test_tier_b_total(self):
        """v10.4 brings Tier B to ≥82."""
        from utils.standards_registry import STANDARDS_REGISTRY
        tier_b = [s for s in STANDARDS_REGISTRY if s.priority_tier == "B"]
        self.assertGreaterEqual(len(tier_b), 82)

    def test_tier_c_total(self):
        """v10.4 brings Tier C to ≥60."""
        from utils.standards_registry import STANDARDS_REGISTRY
        tier_c = [s for s in STANDARDS_REGISTRY if s.priority_tier == "C"]
        self.assertGreaterEqual(len(tier_c), 60)

    def test_all_20_subcategories_present(self):
        """All 20 enhancement subcategories have at least one standard."""
        from utils.standards_registry import (
            STANDARDS_REGISTRY, ENHANCEMENT_SUBCATEGORIES)
        present_subs = {s.subcategory for s in STANDARDS_REGISTRY
                          if s.subcategory}
        for sub in ENHANCEMENT_SUBCATEGORIES:
            self.assertIn(sub, present_subs,
                            f"Subcategory '{sub}' has no standards")


if __name__ == "__main__":
    unittest.main()

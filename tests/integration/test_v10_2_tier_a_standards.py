"""tests/integration/test_v10_2_tier_a_standards.py — v10.2.

Integration tests for v10.2 Tier A enhancement standards (Credit + RMS +
Audit + Legal). Per Master Prompt v9.29 addendum requirements.

Verifies:
- All 4 module tuples present and well-formed
- Continuation.docx standards #119-#130, #181-#190, #201-#210, #221-#230 registered
- Research additions present per module
- Source field correctly tagged
- Priority tier correctly assigned
- Implementation batch correctly noted
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV102TierAStandards(unittest.TestCase):
    """v10.2 Tier A modules: Credit + RMS + Audit + Legal."""

    def test_v10_2_minimum_count(self):
        """v10.2 ships at least 63 enhancement standards on top of v10.1."""
        from utils.standards_registry import STANDARDS_REGISTRY
        enh = [s for s in STANDARDS_REGISTRY if s.category == "enhancement"]
        self.assertGreaterEqual(len(enh), 63,
                                  "v10.2: expected ≥63 enhancement standards")

    def test_credit_module_complete(self):
        """All Continuation.docx #119-#130 + 7 research additions present."""
        from utils.standards_registry import (
            CREDIT_ENHANCEMENT_STANDARDS, list_standards)
        self.assertGreaterEqual(len(CREDIT_ENHANCEMENT_STANDARDS), 19,
                                  "Credit: expected ≥19 standards "
                                  "(12 doc + 7 research)")
        # All Continuation.docx #119-#130 present
        ids = {s.standard_id for s in CREDIT_ENHANCEMENT_STANDARDS}
        for n in range(119, 131):
            self.assertIn(f"ENH-{n}", ids,
                            f"ENH-{n} missing from Credit module")

    def test_rms_module_complete(self):
        """All Continuation.docx #181-#190 + 7 research additions present."""
        from utils.standards_registry import RMS_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(RMS_ENHANCEMENT_STANDARDS), 17,
                                  "RMS: expected ≥17 standards")
        ids = {s.standard_id for s in RMS_ENHANCEMENT_STANDARDS}
        for n in range(181, 191):
            self.assertIn(f"ENH-{n}", ids,
                            f"ENH-{n} missing from RMS module")

    def test_audit_module_complete(self):
        """All Continuation.docx #201-#210 + 7 research additions present."""
        from utils.standards_registry import AUDIT_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(AUDIT_ENHANCEMENT_STANDARDS), 17,
                                  "Audit: expected ≥17 standards")
        ids = {s.standard_id for s in AUDIT_ENHANCEMENT_STANDARDS}
        for n in range(201, 211):
            self.assertIn(f"ENH-{n}", ids,
                            f"ENH-{n} missing from Audit module")

    def test_legal_module_complete(self):
        """All Continuation.docx #221-#230 present."""
        from utils.standards_registry import LEGAL_ENHANCEMENT_STANDARDS
        self.assertGreaterEqual(len(LEGAL_ENHANCEMENT_STANDARDS), 10,
                                  "Legal: expected ≥10 standards")
        ids = {s.standard_id for s in LEGAL_ENHANCEMENT_STANDARDS}
        for n in range(221, 231):
            self.assertIn(f"ENH-{n}", ids,
                            f"ENH-{n} missing from Legal module")


class TestV102StandardsMetadata(unittest.TestCase):
    """v10.2 standards have all required metadata fields populated."""

    def test_all_enhancement_standards_have_subcategory(self):
        from utils.standards_registry import (
            STANDARDS_REGISTRY, ENHANCEMENT_SUBCATEGORIES)
        for s in STANDARDS_REGISTRY:
            if s.category == "enhancement":
                self.assertIn(s.subcategory, ENHANCEMENT_SUBCATEGORIES,
                                f"{s.standard_id}: invalid subcategory "
                                f"{s.subcategory}")

    def test_all_enhancement_standards_have_priority_tier(self):
        from utils.standards_registry import (
            STANDARDS_REGISTRY, PRIORITY_TIERS)
        for s in STANDARDS_REGISTRY:
            if s.category == "enhancement":
                self.assertIn(s.priority_tier, PRIORITY_TIERS,
                                f"{s.standard_id}: invalid priority_tier "
                                f"{s.priority_tier}")

    def test_all_enhancement_standards_have_source(self):
        valid_sources = (
            "continuation_doc", "research_addition", "cbk_regulatory",
            "internal")
        from utils.standards_registry import STANDARDS_REGISTRY
        for s in STANDARDS_REGISTRY:
            if s.category == "enhancement":
                self.assertIn(s.source, valid_sources,
                                f"{s.standard_id}: invalid source "
                                f"{s.source}")

    def test_all_enhancement_standards_have_implementation_batch(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        for s in STANDARDS_REGISTRY:
            if s.category == "enhancement":
                self.assertTrue(
                    s.implementation_batch,
                    f"{s.standard_id}: missing implementation_batch")

    def test_continuation_doc_standards_count(self):
        """At least 42 continuation_doc-sourced standards (12+10+10+10)."""
        from utils.standards_registry import STANDARDS_REGISTRY
        cd_standards = [s for s in STANDARDS_REGISTRY
                          if s.source == "continuation_doc"]
        self.assertGreaterEqual(len(cd_standards), 42,
                                  f"Expected ≥42 continuation_doc standards, "
                                  f"got {len(cd_standards)}")

    def test_research_addition_standards_count(self):
        """At least 21 research-addition standards (7+7+7)."""
        from utils.standards_registry import STANDARDS_REGISTRY
        ra_standards = [s for s in STANDARDS_REGISTRY
                          if s.source == "research_addition"]
        self.assertGreaterEqual(len(ra_standards), 21,
                                  f"Expected ≥21 research_addition standards, "
                                  f"got {len(ra_standards)}")


class TestV102TierAPriorityCorrect(unittest.TestCase):
    """Tier A modules (Credit + RMS + Audit) at priority A; Legal at C."""

    def test_credit_all_tier_a(self):
        from utils.standards_registry import CREDIT_ENHANCEMENT_STANDARDS
        for s in CREDIT_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "A",
                              f"{s.standard_id}: Credit should be Tier A")

    def test_rms_all_tier_a(self):
        from utils.standards_registry import RMS_ENHANCEMENT_STANDARDS
        for s in RMS_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "A",
                              f"{s.standard_id}: RMS should be Tier A")

    def test_audit_all_tier_a(self):
        from utils.standards_registry import AUDIT_ENHANCEMENT_STANDARDS
        for s in AUDIT_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "A",
                              f"{s.standard_id}: Audit should be Tier A")

    def test_legal_all_tier_c(self):
        from utils.standards_registry import LEGAL_ENHANCEMENT_STANDARDS
        for s in LEGAL_ENHANCEMENT_STANDARDS:
            self.assertEqual(s.priority_tier, "C",
                              f"{s.standard_id}: Legal should be Tier C")


if __name__ == "__main__":
    unittest.main()

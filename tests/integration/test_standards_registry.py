"""tests/integration/test_standards_registry.py — v10.1.

Integration test verifying the v10.1 standards_registry module integrates
correctly with the existing engine catalogue. Per the v9.29 master prompt
addendum: every new module needs at least one integration test.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestStandardsRegistryIntegration(unittest.TestCase):
    """v10.1 standards_registry + utils.* engine modules integration."""

    def test_registry_imports_cleanly(self):
        """utils.standards_registry imports without error."""
        from utils import standards_registry
        self.assertIsNotNone(standards_registry)

    def test_registry_has_v10_1_minimum(self):
        """v10.1 ships at least 12 standards (CBK Prudential Tier 1)."""
        from utils.standards_registry import STANDARDS_REGISTRY
        self.assertGreaterEqual(len(STANDARDS_REGISTRY), 12,
                                  "v10.1: expected ≥12 standards")

    def test_all_standards_have_required_fields(self):
        """Every standard has non-empty id, category, name, source."""
        from utils.standards_registry import STANDARDS_REGISTRY, CATEGORIES
        for s in STANDARDS_REGISTRY:
            self.assertTrue(s.standard_id, f"standard missing id")
            self.assertIn(s.category, CATEGORIES,
                           f"{s.standard_id}: invalid category {s.category}")
            self.assertTrue(s.name, f"{s.standard_id}: missing name")
            self.assertTrue(
                s.regulatory_source,
                f"{s.standard_id}: missing regulatory_source")

    def test_standard_ids_unique(self):
        """Standard IDs must be unique across the registry."""
        from utils.standards_registry import STANDARDS_REGISTRY
        ids = [s.standard_id for s in STANDARDS_REGISTRY]
        self.assertEqual(len(set(ids)), len(ids),
                          "Duplicate standard IDs detected")

    def test_affected_engines_exist(self):
        """Engines referenced by standards must exist in utils/.

        v10.2+: relaxed for status='planned' enhancement standards which
        may reference engines planned for Phase 2 deep implementation
        (v10.6+). Active standards still require existing engines.
        """
        from utils.standards_registry import STANDARDS_REGISTRY
        utils_dir = Path(__file__).resolve().parents[2] / "utils"
        existing_engines = {p.stem for p in utils_dir.glob("*.py")
                              if not p.name.startswith("_")}
        for s in STANDARDS_REGISTRY:
            # Skip forward-reference check for planned standards
            if s.status == "planned":
                continue
            for eng in s.affected_engines:
                self.assertIn(eng, existing_engines,
                                f"{s.standard_id} (status={s.status}) "
                                f"references non-existent engine: "
                                f"utils/{eng}.py")

    def test_threshold_consistency(self):
        """Standards with threshold must have unit + direction."""
        from utils.standards_registry import STANDARDS_REGISTRY
        for s in STANDARDS_REGISTRY:
            if s.threshold is not None:
                self.assertIsNotNone(
                    s.threshold_unit,
                    f"{s.standard_id}: threshold without unit")
                self.assertIn(
                    s.threshold_direction, ("min", "max"),
                    f"{s.standard_id}: invalid threshold_direction "
                    f"{s.threshold_direction}")


class TestStandardsRegistryQueries(unittest.TestCase):
    """Public query API works as documented."""

    def test_list_by_category(self):
        from utils.standards_registry import list_standards
        regs = list_standards(category="regulatory")
        self.assertGreaterEqual(len(regs), 12)
        for s in regs:
            self.assertEqual(s.category, "regulatory")

    def test_list_by_engine(self):
        from utils.standards_registry import list_standards
        cap = list_standards(affected_engine="capital_adequacy")
        self.assertGreaterEqual(len(cap), 1)
        for s in cap:
            self.assertIn("capital_adequacy", s.affected_engines)

    def test_get_standard(self):
        from utils.standards_registry import get_standard
        s = get_standard("CBK-PG-01-CAR-CET1")
        self.assertIsNotNone(s)
        self.assertEqual(s.threshold_direction, "min")

    def test_get_unknown_returns_none(self):
        from utils.standards_registry import get_standard
        s = get_standard("DOES-NOT-EXIST-9999")
        self.assertIsNone(s)


if __name__ == "__main__":
    unittest.main()

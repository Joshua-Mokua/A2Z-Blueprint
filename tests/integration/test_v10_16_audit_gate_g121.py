"""tests/integration/test_v10_16_audit_gate_g121.py — v10.16 Credit arc closure.

Locks Phase 2 batch 2 (Credit deep-impl arc, v10.11-v10.16). Mirrors v10.10
G120 closure pattern. Verifies:
  1. G121 gate is registered + present in GATES list
  2. G121 currently passes (all 19 standards active, 8 engines exist)
  3. All 5 v10.11-v10.15 CHANGELOGs + v10.16 closure CHANGELOG present
  4. Master prompt stamped at v10.16
  5. Engine Hub Tier 8 surfaces all 8 credit engines
  6. G117 coverage still ≥ 95% (engines properly integrated)
  7. Total gate count is 121 (was 120 before v10.16)
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1016G121GateRegistered(unittest.TestCase):
    """G121 is registered as the 121st gate."""

    def test_g121_function_exists(self):
        from scripts.audit import gate_credit_engines_implemented
        self.assertTrue(callable(gate_credit_engines_implemented))

    def test_g121_in_gates_list(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertIn("G121", gate_ids,
                        "G121 must be registered in GATES list")

    def test_g121_is_after_g120(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        idx_120 = gate_ids.index("G120")
        idx_121 = gate_ids.index("G121")
        self.assertGreater(idx_121, idx_120,
                              "G121 must come after G120 in GATES list")

    def test_total_gate_count_is_121(self):
        """At v10.16 closure there were 121 gates. Future arc closures
        (v10.22 added G122) grow the count, so we assert ≥121."""
        from scripts.audit import GATES
        self.assertGreaterEqual(
            len(GATES), 121,
            f"Expected ≥121 gates (121 at v10.16 closure); got {len(GATES)}")


class TestV1016G121Passes(unittest.TestCase):
    """G121 currently passes (Credit arc fully implemented)."""

    def test_g121_passes(self):
        from scripts.audit import gate_credit_engines_implemented
        r = gate_credit_engines_implemented()
        self.assertTrue(
            r["passed"],
            f"G121 should pass; violations: {r.get('violations')}")

    def test_g121_reports_closure_set_preserved(self):
        """G121 summary should report that the v10.16 closure set (19 std)
        is preserved. Total credit count may grow with later enhancements
        (e.g., ENH-CBK-KESONIA in v10.17)."""
        from scripts.audit import gate_credit_engines_implemented
        r = gate_credit_engines_implemented()
        self.assertIn("closure set 19/19 preserved", r["summary"])

    def test_g121_returns_correct_id(self):
        from scripts.audit import gate_credit_engines_implemented
        r = gate_credit_engines_implemented()
        self.assertEqual(r["id"], "G121")
        self.assertEqual(r["name"], "credit_engines_implemented")


class TestV1016AllChangelogsPresent(unittest.TestCase):
    """All 6 v10.11-v10.16 CHANGELOGs are present in the repo."""

    def test_changelog_v10_11_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.11.md").exists())

    def test_changelog_v10_12_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.12.md").exists())

    def test_changelog_v10_13_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.13.md").exists())

    def test_changelog_v10_14_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.14.md").exists())

    def test_changelog_v10_15_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.15.md").exists())

    def test_changelog_v10_16_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.16.md").exists())


class TestV1016MasterPromptVersion(unittest.TestCase):
    """Master prompt is stamped at v10.16."""

    def test_master_prompt_at_v10_16(self):
        content = Path("Master_Prompt_v3.md").read_text(encoding="utf-8")
        self.assertIn("v10.16", content,
                          "Master prompt should reference v10.16")


class TestV1016EngineHubIntegration(unittest.TestCase):
    """Engine Hub Tier 8 surfaces all 8 credit engines."""

    def test_tier_8_in_admin_page(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        self.assertIn("Tier 8", content)

    def test_all_8_credit_engines_in_hub(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        for engine in (
            "ai_underwriting", "applicant_data_sources",
            "risk_based_pricing", "credit_workflow",
            "portfolio_monitoring", "fairness_testing",
            "document_management", "group_exposure",
        ):
            self.assertIn(f'"{engine}"', content,
                            f"Engine Hub missing {engine}")


class TestV1016G117CoverageHolds(unittest.TestCase):
    """G117 (engine hub integration coverage) still passes ≥ 95%."""

    def test_g117_passes(self):
        from scripts.audit import gate_engine_hub_integration_coverage
        r = gate_engine_hub_integration_coverage()
        self.assertTrue(
            r["passed"],
            f"G117 should still pass; violations: {r.get('violations')}")


class TestV1016AuditFullPasses(unittest.TestCase):
    """Full audit returns 121/121 — closure verification."""

    def test_full_audit_passes(self):
        from scripts.audit import GATES
        passing = 0
        failing: list = []
        for gate_id, fn in GATES:
            r = fn()
            if r["passed"]:
                passing += 1
            else:
                failing.append(gate_id)
        self.assertEqual(
            passing, len(GATES),
            f"Expected {len(GATES)} passing gates; failing: {failing}")


class TestV1016AllRequiredEnginesActive(unittest.TestCase):
    """All 8 credit engines + their public symbols are importable."""

    def test_all_8_engines_import(self):
        for module in (
            "utils.ai_underwriting",
            "utils.applicant_data_sources",
            "utils.risk_based_pricing",
            "utils.credit_workflow",
            "utils.portfolio_monitoring",
            "utils.fairness_testing",
            "utils.document_management",
            "utils.group_exposure",
        ):
            try:
                __import__(module)
            except Exception as e:
                self.fail(f"Failed to import {module}: {e}")


class TestV1016Phase2BothArcsClosed(unittest.TestCase):
    """Phase 2 batches 1 (Climate) and 2 (Credit) both have closure gates."""

    def test_g120_climate_passes(self):
        from scripts.audit import gate_climate_esg_engines_implemented
        r = gate_climate_esg_engines_implemented()
        self.assertTrue(r["passed"])

    def test_g121_credit_passes(self):
        from scripts.audit import gate_credit_engines_implemented
        r = gate_credit_engines_implemented()
        self.assertTrue(r["passed"])


if __name__ == "__main__":
    unittest.main()

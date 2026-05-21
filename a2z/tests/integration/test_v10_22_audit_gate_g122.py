"""tests/integration/test_v10_22_audit_gate_g122.py — v10.22 RMS arc closure.

Locks Phase 2 batch 3 (RMS Reconciliation arc, v10.18-v10.22). Mirrors
v10.16 G121 + v10.10 G120 closure patterns.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1022G122GateRegistered(unittest.TestCase):
    """G122 is registered as the 122nd gate."""

    def test_g122_function_exists(self):
        from scripts.audit import gate_rms_engines_implemented
        self.assertTrue(callable(gate_rms_engines_implemented))

    def test_g122_in_gates_list(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertIn("G122", gate_ids)

    def test_g122_after_g121(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        idx_121 = gate_ids.index("G121")
        idx_122 = gate_ids.index("G122")
        self.assertGreater(idx_122, idx_121)

    def test_total_gate_count_is_122(self):
        from scripts.audit import GATES
        self.assertEqual(len(GATES), 122)


class TestV1022G122Passes(unittest.TestCase):
    def test_g122_passes(self):
        from scripts.audit import gate_rms_engines_implemented
        r = gate_rms_engines_implemented()
        self.assertTrue(r["passed"],
                          f"G122 should pass; violations: {r.get('violations')}")

    def test_g122_returns_correct_id(self):
        from scripts.audit import gate_rms_engines_implemented
        r = gate_rms_engines_implemented()
        self.assertEqual(r["id"], "G122")
        self.assertEqual(r["name"], "rms_engines_implemented")

    def test_g122_summary_reports_closure_set_preserved(self):
        from scripts.audit import gate_rms_engines_implemented
        r = gate_rms_engines_implemented()
        self.assertIn("closure set 17/17 preserved", r["summary"])


class TestV1022AllChangelogsPresent(unittest.TestCase):
    """All v10.18-v10.22 CHANGELOGs are present."""

    def test_changelog_v10_18_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.18.md").exists())

    def test_changelog_v10_19_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.19.md").exists())

    def test_changelog_v10_20_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.20.md").exists())

    def test_changelog_v10_21_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.21.md").exists())

    def test_changelog_v10_22_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.22.md").exists())


class TestV1022MasterPromptVersion(unittest.TestCase):
    def test_master_prompt_at_v10_22(self):
        content = Path("Master_Prompt_v3.md").read_text(encoding="utf-8")
        self.assertIn("v10.22", content)


class TestV1022EngineHubIntegration(unittest.TestCase):
    """Engine Hub Tier 10 surfaces all 4 RMS engines."""

    def test_tier_10_in_admin_page(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        self.assertIn("Tier 10", content)

    def test_all_4_rms_engines_in_hub(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        for engine in (
            "reconciliation_matching", "reconciliation_workflow",
            "reconciliation_specialized", "reconciliation_realtime",
        ):
            self.assertIn(f'"{engine}"', content,
                            f"Engine Hub missing {engine}")


class TestV1022AllRequiredEnginesActive(unittest.TestCase):
    def test_all_4_engines_import(self):
        for module in (
            "utils.reconciliation_matching",
            "utils.reconciliation_workflow",
            "utils.reconciliation_specialized",
            "utils.reconciliation_realtime",
        ):
            try:
                __import__(module)
            except Exception as e:
                self.fail(f"Failed to import {module}: {e}")


class TestV1022AuditFullPasses(unittest.TestCase):
    """Full audit returns 122/122 — closure verification."""

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


class TestV1022AllPhase2ArcsClosed(unittest.TestCase):
    """All 3 closed Phase 2 arcs (Climate / Credit / RMS) have closure gates."""

    def test_g120_climate_passes(self):
        from scripts.audit import gate_climate_esg_engines_implemented
        self.assertTrue(gate_climate_esg_engines_implemented()["passed"])

    def test_g121_credit_passes(self):
        from scripts.audit import gate_credit_engines_implemented
        self.assertTrue(gate_credit_engines_implemented()["passed"])

    def test_g122_rms_passes(self):
        from scripts.audit import gate_rms_engines_implemented
        self.assertTrue(gate_rms_engines_implemented()["passed"])


if __name__ == "__main__":
    unittest.main()

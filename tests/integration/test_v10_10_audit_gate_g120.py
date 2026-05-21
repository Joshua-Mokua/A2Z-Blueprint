"""tests/integration/test_v10_10_audit_gate_g120.py — v10.10.

Phase 2 batch 1 (Climate/ESG arc) closure gate verification.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1010G120Registered(unittest.TestCase):
    """G120 gate must be registered in scripts/audit.py."""

    def test_g120_in_gates_list(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _ in GATES]
        self.assertIn("G120", gate_ids,
                        "G120 must be registered in GATES list")

    def test_audit_score_120_of_120(self):
        """At v10.10 closure there were 120 gates and all passed.
        Future arc closures (v10.16 added G121, etc.) grow the count,
        so we assert ≥120 with all-pass rather than ==120."""
        from scripts.audit import run_all
        report = run_all()
        self.assertGreaterEqual(
            report["total"], 120,
            f"expected ≥120 gates (120 at v10.10 closure), "
            f"got {report['total']}")
        self.assertEqual(
            report["passed"], report["total"],
            f"expected all gates to pass; "
            f"got {report['passed']}/{report['total']}")
        self.assertTrue(report["all_passed"])


class TestV1010G120Logic(unittest.TestCase):
    """G120 catches Climate/ESG arc drift."""

    def test_g120_passes_when_all_engines_present(self):
        from scripts.audit import gate_climate_esg_engines_implemented
        result = gate_climate_esg_engines_implemented()
        self.assertTrue(
            result["passed"],
            f"G120 should pass when all engines present; "
            f"violations: {result.get('violations', [])}")
        self.assertEqual(result["id"], "G120")

    def test_g120_summary_mentions_arc(self):
        from scripts.audit import gate_climate_esg_engines_implemented
        result = gate_climate_esg_engines_implemented()
        self.assertIn("Climate/ESG", result["summary"])
        self.assertIn("13/13", result["summary"])


class TestV1010ArcCompleteness(unittest.TestCase):
    """All 4 engines + UI + tests + CHANGELOGs ship together."""

    def test_all_4_engine_modules_present(self):
        root = Path(__file__).parents[2]
        for path in (
            "utils/esg_intelligence.py",
            "utils/climate_risk.py",
            "utils/climate_ecl_adjustment.py",
            "utils/esg_reporting_outputs.py",
        ):
            self.assertTrue(
                (root / path).exists(),
                f"missing engine: {path}")

    def test_ui_page_present(self):
        root = Path(__file__).parents[2]
        self.assertTrue(
            (root / "pages" / "92_climate_esg.py").exists(),
            "v10.9 UI page must exist")

    def test_all_4_integration_tests_present(self):
        root = Path(__file__).parents[2]
        for path in (
            "tests/integration/test_v10_6_esg_intelligence.py",
            "tests/integration/test_v10_7_climate_risk.py",
            "tests/integration/test_v10_8_climate_ecl.py",
            "tests/integration/test_v10_9_esg_reporting_outputs.py",
        ):
            self.assertTrue(
                (root / path).exists(),
                f"missing integration test: {path}")

    def test_all_5_changelogs_present(self):
        root = Path(__file__).parents[2]
        for v in ("v10.6", "v10.7", "v10.8", "v10.9", "v10.10"):
            self.assertTrue(
                (root / f"CHANGELOG_{v}.md").exists(),
                f"missing CHANGELOG_{v}.md")

    def test_all_13_climate_esg_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "climate_esg" and s.status == "active"]
        self.assertEqual(len(active), 13)


if __name__ == "__main__":
    unittest.main()

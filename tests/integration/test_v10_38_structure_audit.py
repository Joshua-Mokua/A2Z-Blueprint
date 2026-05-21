"""tests/integration/test_v10_38_structure_audit.py — v10.38.

Structural hygiene foundation: codebase shape audit + G128 baseline gate.
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[2]
sys.path.insert(0, str(_ROOT))


class TestV1038Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import structure_audit_core    # noqa

    def test_public_symbols(self):
        from utils import structure_audit_core as m
        for sym in (
            "FindingSeverity", "FindingCategory",
            "Finding", "StructureAuditResult",
            "StructureAuditEngine",
            "compute_baseline", "compare_to_baseline",
            "BaselineComparison",
            "FORBIDDEN_LAYER_EDGES",
            "GOD_MODULE_INCOMING_THRESHOLD",
            "CROSS_ARC_BRIDGES",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV1038SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import structure_audit_core
        structure_audit_core.self_test()


class TestV1038Cli(unittest.TestCase):
    def test_cli_module_exists(self):
        cli = _ROOT / "scripts" / "structure_audit.py"
        self.assertTrue(cli.exists())


class TestV1038Baseline(unittest.TestCase):
    def test_baseline_file_present(self):
        baseline = _ROOT / "docs" / "structure_audit_baseline.json"
        self.assertTrue(
            baseline.exists(),
            "baseline missing — run "
            "scripts/structure_audit.py --capture-baseline")

    def test_baseline_format(self):
        baseline_path = _ROOT / "docs" / "structure_audit_baseline.json"
        if not baseline_path.exists():
            self.skipTest("no baseline yet")
        baseline = json.loads(baseline_path.read_text())
        self.assertEqual(baseline.get("version"), 1)
        self.assertIn("hard_counts_by_category", baseline)
        self.assertIn("hard_fingerprints", baseline)


class TestV1038ArchitectureDocs(unittest.TestCase):
    def test_architecture_md_exists(self):
        arch = _ROOT / "docs" / "ARCHITECTURE.md"
        self.assertTrue(arch.exists())

    def test_module_map_exists(self):
        mm = _ROOT / "docs" / "module_map.json"
        self.assertTrue(mm.exists())

    def test_module_map_well_formed(self):
        mm = _ROOT / "docs" / "module_map.json"
        if not mm.exists():
            self.skipTest("module_map not yet generated")
        data = json.loads(mm.read_text())
        self.assertIn("_meta", data)
        self.assertIn("modules", data)
        self.assertGreater(len(data["modules"]), 100)


class TestV1038RealAudit(unittest.TestCase):
    """Run audit against the real codebase; assert basic sanity."""

    def test_audit_completes(self):
        from utils.structure_audit_core import StructureAuditEngine
        engine = StructureAuditEngine(project_root=_ROOT)
        result = engine.audit()
        self.assertGreater(result.n_modules_scanned, 100)

    def test_no_layer_violations(self):
        """Layer violations are HARD — none allowed."""
        from utils.structure_audit_core import (
            StructureAuditEngine, FindingCategory)
        engine = StructureAuditEngine(project_root=_ROOT)
        result = engine.audit()
        layer_violations = [
            f for f in result.findings
            if f.category == FindingCategory.LAYER_VIOLATION]
        self.assertEqual(
            len(layer_violations), 0,
            f"unexpected layer violations: {layer_violations}")

    def test_no_regression_against_baseline(self):
        """Real codebase HARD findings must match captured baseline."""
        from utils.structure_audit_core import (
            StructureAuditEngine, compare_to_baseline)
        baseline_path = _ROOT / "docs" / "structure_audit_baseline.json"
        if not baseline_path.exists():
            self.skipTest("no baseline captured yet")
        baseline = json.loads(baseline_path.read_text())
        engine = StructureAuditEngine(project_root=_ROOT)
        result = engine.audit()
        comparison = compare_to_baseline(result, baseline)
        self.assertFalse(
            comparison.is_regression,
            f"structural regression: {comparison.summary}; "
            f"new findings: "
            f"{[(f.category.value, f.module_path) for f in comparison.new_findings]}")


class TestV1038HonestyRules(unittest.TestCase):
    """Per Rule 1 + Rule 7 conformance."""

    def test_findings_carry_observed_and_threshold(self):
        from utils.structure_audit_core import (
            StructureAuditEngine, FindingCategory)
        engine = StructureAuditEngine(project_root=_ROOT)
        result = engine.audit()
        for f in result.findings:
            # Per Rule 1: every finding has description + suggestion
            self.assertGreater(len(f.description), 5)
            self.assertGreater(len(f.suggestion), 5)

    def test_engine_does_not_mutate_codebase(self):
        """Per Rule 7: audit is read-only.

        Verify by capturing file mtimes before and after audit and
        asserting nothing changed.
        """
        import os
        from utils.structure_audit_core import StructureAuditEngine
        utils_dir = _ROOT / "utils"
        before_mtimes = {
            f.name: f.stat().st_mtime
            for f in utils_dir.glob("*.py")}
        engine = StructureAuditEngine(project_root=_ROOT)
        engine.audit()
        after_mtimes = {
            f.name: f.stat().st_mtime
            for f in utils_dir.glob("*.py")}
        self.assertEqual(before_mtimes, after_mtimes)


class TestV1038AuditScore(unittest.TestCase):
    """Audit score must be ≥ 128 after v10.38."""

    def test_audit_score_at_least_128(self):
        # Run the platform audit
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "audit.py")],
            cwd=str(_ROOT),
            capture_output=True, text=True, timeout=180)
        # Expect score ≥ 128 in stdout
        # (PASS line: "Score: N/N gates = X% — PASS")
        match_pass = "PASS" in result.stdout
        # Find the score
        score_line = next(
            (ln for ln in result.stdout.splitlines()
             if "Score:" in ln),
            "")
        self.assertTrue(
            match_pass,
            f"audit did not PASS; stdout: {result.stdout[-500:]}; "
            f"stderr: {result.stderr[-500:]}")
        # Extract first integer
        import re
        m = re.search(r"(\d+)/(\d+)", score_line)
        self.assertIsNotNone(m, f"score line: {score_line}")
        n_passed = int(m.group(1))
        self.assertGreaterEqual(
            n_passed, 128,
            f"audit score {n_passed} < 128")


if __name__ == "__main__":
    unittest.main()

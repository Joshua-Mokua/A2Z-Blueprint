"""tests/integration/test_v10_36_scenario_simulator.py — v10.36.

Scenario simulation foundation: cross-arc executable scenarios that
exercise the v10.18-35 engine stack. Initial library has 11 Treasury
scenarios; subsequent batches will add more covering Risk, Trade, etc.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1036Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import scenario_simulator  # noqa

    def test_public_symbols(self):
        from utils import scenario_simulator as m
        for sym in (
            "ScenarioCategory", "ScenarioStatus",
            "AssertionResult", "ScenarioResult",
            "Scenario", "ScenarioRunner",
            "TREASURY_SCENARIO_LIBRARY",
            "SPEC_DEVIATION_NOTE",
            # Individual scenarios exposed
            "SCENARIO_LI_01_LCR_COMPLIANT",
            "SCENARIO_LI_02_LCR_BREACH",
            "SCENARIO_IRRBB_01",
            "SCENARIO_CAP_01_CBK_DUAL_THRESHOLD",
            "SCENARIO_FX_01_NET_EXPOSURE",
            "SCENARIO_NIM_01_DECOMPOSITION",
            "SCENARIO_DASH_01_BREACH_ROLLUP",
            "SCENARIO_CF_01_FORECAST",
            "SCENARIO_CF_02_ML_REQUIRES_PROVIDER",
            "SCENARIO_MODGOV_01_REGISTRATION",
            "SCENARIO_CROSS_01_LCR_FULL_PROPAGATION",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV1036SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import scenario_simulator
        scenario_simulator.self_test()


class TestV1036LibraryShape(unittest.TestCase):
    def test_library_size_at_least_11(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY)
        self.assertGreaterEqual(len(TREASURY_SCENARIO_LIBRARY), 11)

    def test_every_scenario_has_unique_id(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY)
        ids = [s.scenario_id for s in TREASURY_SCENARIO_LIBRARY]
        self.assertEqual(len(ids), len(set(ids)))

    def test_categories_cover_multiple_arcs(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY)
        cats = {s.category for s in TREASURY_SCENARIO_LIBRARY}
        # Initial library should hit at least 4 distinct categories
        self.assertGreaterEqual(len(cats), 4)


class TestV1036RunnerContract(unittest.TestCase):
    def test_runner_requires_engines_or_factory(self):
        from utils.scenario_simulator import ScenarioRunner
        with self.assertRaises(ValueError):
            ScenarioRunner()

    def test_runner_rejects_both_modes(self):
        from utils.scenario_simulator import ScenarioRunner
        with self.assertRaises(ValueError):
            ScenarioRunner(
                engines={},
                bundle_factory=lambda: {})

    def test_unknown_engine_skips_cleanly(self):
        from utils.scenario_simulator import (
            ScenarioRunner, ScenarioStatus,
            SCENARIO_LI_01_LCR_COMPLIANT)
        runner = ScenarioRunner(engines={})
        result = runner.run(SCENARIO_LI_01_LCR_COMPLIANT)
        self.assertEqual(result.status, ScenarioStatus.SKIPPED)


class TestV1036FullLibraryPasses(unittest.TestCase):
    """Run every scenario with fresh bundle per scenario; verify all pass."""

    def test_full_library_passes_with_fresh_bundles(self):
        from utils.scenario_simulator import (
            ScenarioRunner, TREASURY_SCENARIO_LIBRARY,
            ScenarioStatus, _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        results = runner.run_all(TREASURY_SCENARIO_LIBRARY)
        failures = [
            r for r in results
            if r.status not in (
                ScenarioStatus.PASS, ScenarioStatus.SKIPPED)]
        self.assertEqual(len(failures), 0, (
            f"unexpected failures: {[(r.scenario_id, r.status.value) for r in failures]}"))

    def test_summary_aggregates(self):
        from utils.scenario_simulator import (
            ScenarioRunner, TREASURY_SCENARIO_LIBRARY,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        runner.run_all(TREASURY_SCENARIO_LIBRARY)
        summary = runner.summary()
        self.assertEqual(
            summary["n_total"], len(TREASURY_SCENARIO_LIBRARY))
        self.assertEqual(summary["n_failures"], 0)


class TestV1036SpecificScenarios(unittest.TestCase):
    """Surface key scenarios for direct asserts."""

    def test_lcr_breach_correctly_detected(self):
        """LI-02: HQLA insufficient → system flags non-compliant."""
        from utils.scenario_simulator import (
            ScenarioRunner, ScenarioStatus,
            SCENARIO_LI_02_LCR_BREACH,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        result = runner.run(SCENARIO_LI_02_LCR_BREACH)
        self.assertEqual(result.status, ScenarioStatus.PASS)

    def test_cbk_dual_threshold_enforced(self):
        """CAP-01: 8% CET1 passes Basel but fails CBK 10.5%."""
        from utils.scenario_simulator import (
            ScenarioRunner, ScenarioStatus,
            SCENARIO_CAP_01_CBK_DUAL_THRESHOLD,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        result = runner.run(SCENARIO_CAP_01_CBK_DUAL_THRESHOLD)
        self.assertEqual(result.status, ScenarioStatus.PASS)
        self.assertEqual(result.n_passed, 3)

    def test_irrbb_outlier_detected_on_extreme_position(self):
        """IRRBB-01: 10B 5y+ asset vs 1B Tier 1 → outlier."""
        from utils.scenario_simulator import (
            ScenarioRunner, ScenarioStatus,
            SCENARIO_IRRBB_01,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        result = runner.run(SCENARIO_IRRBB_01)
        self.assertEqual(result.status, ScenarioStatus.PASS)

    def test_ml_overlay_requires_provider_per_rule_7(self):
        """CF-02: ML overlay without provider raises REQUIRES_PROVIDER."""
        from utils.scenario_simulator import (
            ScenarioRunner, ScenarioStatus,
            SCENARIO_CF_02_ML_REQUIRES_PROVIDER,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        result = runner.run(SCENARIO_CF_02_ML_REQUIRES_PROVIDER)
        self.assertEqual(result.status, ScenarioStatus.PASS)
        # Both assertions in CF-02 must pass
        self.assertEqual(result.n_passed, 2)

    def test_cross_arc_lcr_propagation_end_to_end(self):
        """CROSS-01: ALM detects → dashboard surfaces breach."""
        from utils.scenario_simulator import (
            ScenarioRunner, ScenarioStatus,
            SCENARIO_CROSS_01_LCR_FULL_PROPAGATION,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        result = runner.run(
            SCENARIO_CROSS_01_LCR_FULL_PROPAGATION)
        self.assertEqual(result.status, ScenarioStatus.PASS)
        self.assertEqual(result.n_passed, 2)


class TestV1036DocumentationSurface(unittest.TestCase):
    """Verify scenarios are self-documenting per Rule 1."""

    def test_every_scenario_has_description(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY)
        for s in TREASURY_SCENARIO_LIBRARY:
            self.assertGreater(
                len(s.description), 20,
                f"{s.scenario_id} description too short")

    def test_every_scenario_declares_required_engines(self):
        """Some scenarios are pure (build inline mocks); rest declare engines."""
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY)
        # Most scenarios should declare engines; allow a few to be empty
        n_declared = sum(
            1 for s in TREASURY_SCENARIO_LIBRARY
            if len(s.requires_engines) > 0)
        self.assertGreaterEqual(
            n_declared, len(TREASURY_SCENARIO_LIBRARY) - 3,
            "more than 3 scenarios have empty requires_engines")

    def test_assertion_results_contain_observed_and_expected(self):
        """Per Rule 1: every assertion surfaces both expected and observed."""
        from utils.scenario_simulator import (
            ScenarioRunner, TREASURY_SCENARIO_LIBRARY,
            _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        runner.run_all(TREASURY_SCENARIO_LIBRARY)
        for sid, result in runner.results.items():
            for a in result.assertions:
                self.assertIsNotNone(a.expected)
                self.assertIsNotNone(a.observed)
                self.assertGreater(len(a.description), 5)


if __name__ == "__main__":
    unittest.main()

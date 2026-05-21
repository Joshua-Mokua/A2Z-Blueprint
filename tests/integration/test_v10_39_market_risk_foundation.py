"""tests/integration/test_v10_39_market_risk_foundation.py — v10.39.

Risk arc opens. Market Risk foundation:
- ENH-MR-001 VaR (Parametric / Historical / Monte Carlo)
- ENH-MR-002 Expected Shortfall (FRTB-IMA 97.5%)
- ENH-MR-003 Sensitivity-Based Measures (DV01 / FX delta / equity delta)
- ENH-MR-004 Risk Factor Taxonomy (5 classes + 9 prebuilt scenarios)
- ENH-MR-005 VaR Backtesting (Kupiec POF + Christoffersen indep)
"""
from __future__ import annotations
import random
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[2]
sys.path.insert(0, str(_ROOT))


class TestV1039Imports(unittest.TestCase):
    def test_market_risk_factors_imports(self):
        from utils import market_risk_factors    # noqa

    def test_market_risk_sensitivities_imports(self):
        from utils import market_risk_sensitivities    # noqa

    def test_market_risk_var_imports(self):
        from utils import market_risk_var    # noqa


class TestV1039PublicSurface(unittest.TestCase):
    """Per Rule 1: stable public contract."""

    def test_factors_public(self):
        from utils import market_risk_factors as m
        for sym in (
            "RiskFactor", "RiskFactorClass", "ShockType",
            "FactorShock", "StressScenario",
            "ALL_PREBUILT_SCENARIOS", "RiskFactorRegistry",
            "BCBS_IRRBB_PARALLEL_UP", "BCBS_IRRBB_PARALLEL_DOWN",
            "BCBS_IRRBB_SHORT_UP", "BCBS_IRRBB_SHORT_DOWN",
            "BCBS_IRRBB_STEEPENER", "BCBS_IRRBB_FLATTENER",
            "INTERNAL_FX_SHOCK_USDKES_UP_15",
            "INTERNAL_FX_SHOCK_USDKES_DOWN_10",
            "INTERNAL_EQUITY_CRASH_30",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(
                hasattr(m, sym),
                f"market_risk_factors missing: {sym}")

    def test_sensitivities_public(self):
        from utils import market_risk_sensitivities as m
        for sym in (
            "Sensitivity", "SensitivityType", "SensitivityReport",
            "BondPosition", "FXPosition", "EquityPosition",
            "SensitivityEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(
                hasattr(m, sym),
                f"market_risk_sensitivities missing: {sym}")

    def test_var_public(self):
        from utils import market_risk_var as m
        for sym in (
            "VaRMethodology", "BacktestVerdict",
            "ReturnDistributionSummary", "VaRResult",
            "BacktestResult", "VaREngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(
                hasattr(m, sym),
                f"market_risk_var missing: {sym}")


class TestV1039SelfTests(unittest.TestCase):
    """Run module-level self-tests via the runtime self_test() hooks."""

    def test_factors_self_test(self):
        from utils import market_risk_factors
        market_risk_factors.self_test()

    def test_sensitivities_self_test(self):
        from utils import market_risk_sensitivities
        market_risk_sensitivities.self_test()

    def test_var_self_test(self):
        from utils import market_risk_var
        market_risk_var.self_test()


class TestV1039RiskFactorTaxonomy(unittest.TestCase):
    """ENH-MR-004 — taxonomy invariants."""

    def test_5_factor_classes_present(self):
        from utils.market_risk_factors import RiskFactorClass
        names = {c.name for c in RiskFactorClass}
        self.assertEqual(names, {
            "INTEREST_RATE", "FOREIGN_EXCHANGE", "EQUITY",
            "COMMODITY", "CREDIT_SPREAD"})

    def test_9_prebuilt_scenarios_present(self):
        from utils.market_risk_factors import ALL_PREBUILT_SCENARIOS
        self.assertEqual(len(ALL_PREBUILT_SCENARIOS), 9)

    def test_six_bcbs_irrbb_scenarios_present(self):
        from utils.market_risk_factors import ALL_PREBUILT_SCENARIOS
        ids = {s.scenario_id for s in ALL_PREBUILT_SCENARIOS}
        for expected in (
            "BCBS-IRRBB-1", "BCBS-IRRBB-2", "BCBS-IRRBB-3",
            "BCBS-IRRBB-4", "BCBS-IRRBB-5", "BCBS-IRRBB-6",
        ):
            self.assertIn(
                expected, ids,
                f"BCBS d368 scenario {expected} missing")

    def test_three_internal_scenarios_present(self):
        from utils.market_risk_factors import ALL_PREBUILT_SCENARIOS
        ids = {s.scenario_id for s in ALL_PREBUILT_SCENARIOS}
        for expected in ("INT-FX-1", "INT-FX-2", "INT-EQ-1"):
            self.assertIn(
                expected, ids,
                f"internal scenario {expected} missing")


class TestV1039Sensitivities(unittest.TestCase):
    """ENH-MR-003 — sensitivity computation invariants."""

    def test_dv01_formula(self):
        """DV01 = D_mod × P × 0.0001. 1m KES bond, D=7 → 700 KES/bp."""
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_sensitivities import (
            BondPosition, SensitivityEngine)
        engine = SensitivityEngine()
        pos = BondPosition(
            position_id="test1",
            factor=RiskFactor.IR_KES_GOVT,
            notional_kes=Decimal("1000000"),
            modified_duration=Decimal("7"))
        sens = engine.compute_dv01(pos)
        self.assertAlmostEqual(float(sens.delta), 700.0, places=2)

    def test_dv01_loses_on_parallel_up_shift(self):
        """+200bp on a long bond → loss (PnL < 0)."""
        from utils.market_risk_factors import (
            BCBS_IRRBB_PARALLEL_UP, RiskFactor)
        from utils.market_risk_sensitivities import (
            BondPosition, SensitivityEngine)
        engine = SensitivityEngine()
        pos = BondPosition(
            position_id="test1",
            factor=RiskFactor.IR_KES_GENERIC,
            notional_kes=Decimal("1000000"),
            modified_duration=Decimal("7"))
        sens = engine.compute_dv01(pos)
        shocks = {
            sh.factor: (sh.magnitude, sh.shock_type.value)
            for sh in BCBS_IRRBB_PARALLEL_UP.shocks
        }
        pnl = engine.apply_scenario_pnl(
            sensitivities=(sens,), shocks=shocks)
        self.assertLess(float(pnl), 0)
        self.assertAlmostEqual(float(pnl), -140000.0, delta=5)

    def test_fx_delta_formula(self):
        """FX delta = foreign × spot × 0.01 for a 1% move."""
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_sensitivities import (
            FXPosition, SensitivityEngine)
        engine = SensitivityEngine()
        pos = FXPosition(
            position_id="usd1",
            factor=RiskFactor.FX_USDKES,
            foreign_amount=Decimal("100000"),
            spot_to_kes=Decimal("130"))
        sens = engine.compute_fx_delta(pos)
        self.assertAlmostEqual(float(sens.delta), 130000.0, places=2)

    def test_equity_delta_uses_beta(self):
        """Equity delta = mv × beta × 0.01 (1% market move)."""
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_sensitivities import (
            EquityPosition, SensitivityEngine)
        engine = SensitivityEngine()
        pos = EquityPosition(
            position_id="eq1",
            factor=RiskFactor.EQUITY_NSE_GENERIC,
            market_value_kes=Decimal("5000000"),
            beta=Decimal("1.5"))
        sens = engine.compute_equity_delta(pos)
        self.assertAlmostEqual(float(sens.delta), 75000.0, places=2)

    def test_aggregation_groups_by_class(self):
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_sensitivities import (
            BondPosition, FXPosition, SensitivityEngine)
        engine = SensitivityEngine()
        bond = BondPosition(
            position_id="b1",
            factor=RiskFactor.IR_KES_GOVT,
            notional_kes=Decimal("1000000"),
            modified_duration=Decimal("5"))
        fx = FXPosition(
            position_id="fx1",
            factor=RiskFactor.FX_USDKES,
            foreign_amount=Decimal("100000"),
            spot_to_kes=Decimal("130"))
        sensitivities = (
            engine.compute_dv01(bond),
            engine.compute_fx_delta(fx))
        report = engine.aggregate(sensitivities)
        self.assertGreater(len(report.by_class), 1)


class TestV1039VaRBasics(unittest.TestCase):
    """ENH-MR-001 — VaR computation invariants."""

    def test_parametric_var_positive_loss_magnitude(self):
        from utils.market_risk_var import VaREngine
        rng = random.Random(42)
        returns = [rng.gauss(0, 0.01) for _ in range(250)]
        engine = VaREngine()
        result = engine.parametric_var(
            returns=returns,
            portfolio_value_kes=Decimal("1000000"),
            confidence=Decimal("0.99"),
            horizon_days=1)
        self.assertGreater(result.var_kes, Decimal("0"))

    def test_es_at_least_var(self):
        """ES ≥ VaR by construction."""
        from utils.market_risk_var import VaREngine
        rng = random.Random(7)
        returns = [rng.gauss(0, 0.01) for _ in range(500)]
        engine = VaREngine()
        result = engine.parametric_var(
            returns=returns,
            portfolio_value_kes=Decimal("1000000"),
            confidence=Decimal("0.99"),
            horizon_days=1)
        self.assertGreaterEqual(
            result.expected_shortfall_kes, result.var_kes)

    def test_three_methodologies_close_on_normal_returns(self):
        """For Normal returns, parametric & historical agree
        within ~30%."""
        from utils.market_risk_var import VaREngine
        rng = random.Random(99)
        returns = [rng.gauss(0, 0.01) for _ in range(2000)]
        engine = VaREngine()
        pv = Decimal("1000000")
        conf = Decimal("0.99")
        param = engine.parametric_var(
            returns=returns, portfolio_value_kes=pv,
            confidence=conf, horizon_days=1)
        hist = engine.historical_var(
            returns=returns, portfolio_value_kes=pv,
            confidence=conf, horizon_days=1)
        ratio = float(param.var_kes / hist.var_kes)
        self.assertGreater(ratio, 0.7)
        self.assertLess(ratio, 1.3)


class TestV1039Backtests(unittest.TestCase):
    """ENH-MR-005 — Kupiec + Christoffersen invariants."""

    def test_kupiec_passes_when_breaches_match_expected(self):
        from utils.market_risk_var import (
            VaREngine, BacktestVerdict)
        engine = VaREngine()
        # 10 breaches in 1000 days = 1% — matches 99% VaR exactly
        seq = [False] * 990 + [True] * 10
        rng = random.Random(1)
        rng.shuffle(seq)
        result = engine.kupiec_pof_test(
            breach_sequence=seq,
            var_confidence=Decimal("0.99"),
            significance=Decimal("0.05"))
        self.assertEqual(result.verdict, BacktestVerdict.PASS)

    def test_kupiec_fails_when_breaches_far_above_expected(self):
        from utils.market_risk_var import (
            VaREngine, BacktestVerdict)
        engine = VaREngine()
        # 25 breaches in 250 days = 10% > 1% expected → FAIL
        seq = [False] * 225 + [True] * 25
        rng = random.Random(2)
        rng.shuffle(seq)
        result = engine.kupiec_pof_test(
            breach_sequence=seq,
            var_confidence=Decimal("0.99"),
            significance=Decimal("0.05"))
        self.assertEqual(result.verdict, BacktestVerdict.FAIL)
        self.assertGreater(float(result.test_statistic), 3.841)

    def test_christoffersen_independent_breaches_not_fail(self):
        """Independent breaches at 5% rate → not FAIL."""
        from utils.market_risk_var import (
            VaREngine, BacktestVerdict)
        engine = VaREngine()
        rng = random.Random(11)
        seq = [rng.random() < 0.05 for _ in range(500)]
        result = engine.christoffersen_independence_test(
            breach_sequence=seq,
            significance=Decimal("0.05"))
        self.assertIn(
            result.verdict,
            (BacktestVerdict.PASS,
             BacktestVerdict.INSUFFICIENT_DATA))


class TestV1039StandardsRegistry(unittest.TestCase):
    """ENH-MR-001..005 are active in the registry."""

    def test_5_enh_mr_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        # Filter to v10.39 batch specifically — later batches may add
        # more ENH-MR-* standards (e.g., v10.40 adds ENH-MR-006/007)
        mr = [s for s in STANDARDS_REGISTRY
              if s.standard_id.startswith("ENH-MR-")
              and s.implementation_batch == "v10.39"]
        self.assertEqual(len(mr), 5)
        for s in mr:
            self.assertEqual(
                s.status, "active",
                f"{s.standard_id} is not active")
            self.assertEqual(
                s.implementation_batch, "v10.39",
                f"{s.standard_id} not v10.39")

    def test_affected_engines_resolve_to_real_modules(self):
        import importlib
        from utils.standards_registry import STANDARDS_REGISTRY
        mr = [s for s in STANDARDS_REGISTRY
              if s.standard_id.startswith("ENH-MR-")
              and s.implementation_batch == "v10.39"]
        for std in mr:
            for eng in std.affected_engines:
                try:
                    importlib.import_module(f"utils.{eng}")
                except ImportError as e:
                    self.fail(
                        f"{std.standard_id} engine {eng} not "
                        f"importable: {e}")


class TestV1039ScenarioLibrary(unittest.TestCase):
    """5 RISK-* scenarios exercise the new modules."""

    def test_5_risk_scenarios_in_library(self):
        from utils.scenario_simulator import TREASURY_SCENARIO_LIBRARY
        risk = [s for s in TREASURY_SCENARIO_LIBRARY
                if s.scenario_id.startswith("RISK-")]
        self.assertEqual(len(risk), 5)

    def test_risk_scenarios_pass_when_engines_wired(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY, ScenarioRunner)
        from utils import (
            market_risk_factors, market_risk_sensitivities,
            market_risk_var)
        engines = {
            "market_risk_factors": market_risk_factors,
            "market_risk_sensitivities": market_risk_sensitivities,
            "market_risk_var": market_risk_var,
        }
        runner = ScenarioRunner(engines=engines)
        risk = [s for s in TREASURY_SCENARIO_LIBRARY
                if s.scenario_id.startswith("RISK-")]
        for scen in risk:
            result = runner.run(scen)
            self.assertEqual(
                result.n_failed, 0,
                f"{scen.scenario_id}: {result.n_failed} failures; "
                f"status={result.status}; notes={result.notes}")
            self.assertGreater(
                result.n_passed, 0,
                f"{scen.scenario_id} ran zero assertions; "
                f"status={result.status}")


class TestV1039HonestyRules(unittest.TestCase):
    """Per Rule 1 + Rule 7."""

    def test_scenarios_carry_framework_refs(self):
        from utils.market_risk_factors import ALL_PREBUILT_SCENARIOS
        for scen in ALL_PREBUILT_SCENARIOS:
            self.assertGreater(
                len(scen.framework_refs), 0,
                f"{scen.scenario_id} has no framework_refs")

    def test_var_result_has_methodology_provenance(self):
        from utils.market_risk_var import VaREngine
        rng = random.Random(1)
        returns = [rng.gauss(0, 0.01) for _ in range(250)]
        engine = VaREngine()
        result = engine.parametric_var(
            returns=returns,
            portfolio_value_kes=Decimal("1000000"),
            confidence=Decimal("0.99"),
            horizon_days=1)
        self.assertIsNotNone(result.methodology)
        self.assertGreater(len(result.framework_refs), 0)

    def test_backtest_result_has_full_triage_info(self):
        from utils.market_risk_var import VaREngine
        engine = VaREngine()
        seq = [False] * 990 + [True] * 10
        result = engine.kupiec_pof_test(
            breach_sequence=seq,
            var_confidence=Decimal("0.99"))
        self.assertEqual(result.n_observations, 1000)
        self.assertEqual(result.n_breaches, 10)
        self.assertGreater(len(result.framework_refs), 0)


class TestV1039StructuralIntegrity(unittest.TestCase):
    """G128 baseline must remain stable after v10.39."""

    def test_no_new_circular_imports(self):
        import json
        from utils.structure_audit_core import (
            StructureAuditEngine, compare_to_baseline)
        baseline_path = (
            _ROOT / "docs" / "structure_audit_baseline.json")
        if not baseline_path.exists():
            self.skipTest("no baseline")
        engine = StructureAuditEngine(project_root=_ROOT)
        result = engine.audit()
        baseline = json.loads(baseline_path.read_text())
        comparison = compare_to_baseline(result, baseline)
        self.assertFalse(
            comparison.is_regression,
            f"v10.39 introduced structural regression: "
            f"{comparison.summary}")


class TestV1039AuditScore(unittest.TestCase):
    """Audit score must remain ≥ 128 after v10.39."""

    def test_audit_score_at_least_128(self):
        import re
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "audit.py")],
            cwd=str(_ROOT),
            capture_output=True, text=True, timeout=180)
        self.assertIn(
            "PASS", result.stdout,
            f"audit not PASS: {result.stdout[-500:]}")
        score_line = next(
            (ln for ln in result.stdout.splitlines()
             if "Score:" in ln), "")
        m = re.search(r"(\d+)/(\d+)", score_line)
        self.assertIsNotNone(m, f"score line: {score_line}")
        self.assertGreaterEqual(int(m.group(1)), 128)


if __name__ == "__main__":
    unittest.main()

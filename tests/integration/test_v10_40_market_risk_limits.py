"""tests/integration/test_v10_40_market_risk_limits.py — v10.40.

Risk arc continues — Market Risk Limits & Breach Management:
- ENH-MR-006 Market Risk Limit Framework
- ENH-MR-007 Limit Breach Detection & Escalation
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[2]
sys.path.insert(0, str(_ROOT))


class TestV1040Imports(unittest.TestCase):
    def test_market_risk_limits_imports(self):
        from utils import market_risk_limits    # noqa


class TestV1040PublicSurface(unittest.TestCase):
    """Per Rule 1: stable public contract."""

    def test_limits_public(self):
        from utils import market_risk_limits as m
        for sym in (
            "LimitType", "LimitScope", "BreachSeverity",
            "RiskLimit", "BreachAlert", "MonitorReport",
            "LimitRegistry", "LimitMonitor",
            "ALL_DEFAULT_LIMITS", "build_default_registry",
            "DEFAULT_VAR_LIMIT_99_1D", "DEFAULT_ES_LIMIT_975_10D",
            "DEFAULT_FX_CONCENTRATION_USD",
            "DEFAULT_FX_CLASS_LIMIT", "DEFAULT_EQUITY_CLASS_LIMIT",
            "WARN_THRESHOLD_PCT", "BREACH_THRESHOLD_PCT",
            "SEVERE_THRESHOLD_PCT",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(
                hasattr(m, sym),
                f"market_risk_limits missing: {sym}")


class TestV1040SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import market_risk_limits
        market_risk_limits.self_test()


class TestV1040LimitConstruction(unittest.TestCase):
    """ENH-MR-006 — RiskLimit dataclass invariants."""

    def test_threshold_must_be_positive(self):
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import (
            RiskLimit, LimitType, LimitScope)
        with self.assertRaises(ValueError):
            RiskLimit(
                limit_id="bad",
                limit_type=LimitType.CONCENTRATION,
                scope=LimitScope.SINGLE_FACTOR,
                threshold_kes=Decimal("0"),
                factor=RiskFactor.FX_USDKES,
                description="x", regulatory_source="x",
                framework_refs=(), approval_authority="ALCO",
                effective_date="2026-01-01")

    def test_var_limit_requires_confidence_horizon(self):
        from utils.market_risk_limits import (
            RiskLimit, LimitType, LimitScope)
        with self.assertRaises(ValueError):
            RiskLimit(
                limit_id="bad",
                limit_type=LimitType.VAR_LIMIT,
                scope=LimitScope.PORTFOLIO,
                threshold_kes=Decimal("100000"),
                description="x", regulatory_source="x",
                framework_refs=(), approval_authority="BOARD",
                effective_date="2026-01-01")

    def test_concentration_cannot_be_portfolio_scope(self):
        from utils.market_risk_limits import (
            RiskLimit, LimitType, LimitScope)
        with self.assertRaises(ValueError):
            RiskLimit(
                limit_id="bad",
                limit_type=LimitType.CONCENTRATION,
                scope=LimitScope.PORTFOLIO,
                threshold_kes=Decimal("100000"),
                description="x", regulatory_source="x",
                framework_refs=(), approval_authority="ALCO",
                effective_date="2026-01-01")


class TestV1040LimitRegistry(unittest.TestCase):
    """ENH-MR-006 — LimitRegistry behavior."""

    def test_registry_register_and_retrieve(self):
        from utils.market_risk_limits import (
            LimitRegistry, DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        self.assertTrue(reg.is_active("VAR_99_1D_TRADING_BOOK"))

    def test_double_register_raises(self):
        from utils.market_risk_limits import (
            LimitRegistry, DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        with self.assertRaises(ValueError):
            reg.register(DEFAULT_VAR_LIMIT_99_1D)

    def test_deactivate_preserves_history(self):
        """Deactivating a limit keeps it in storage for audit."""
        from utils.market_risk_limits import (
            LimitRegistry, DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        reg.deactivate("VAR_99_1D_TRADING_BOOK")
        self.assertFalse(reg.is_active("VAR_99_1D_TRADING_BOOK"))
        # But still retrievable (audit-trail preservation)
        self.assertIsNotNone(reg.get("VAR_99_1D_TRADING_BOOK"))

    def test_default_registry_has_5_limits(self):
        from utils.market_risk_limits import build_default_registry
        reg = build_default_registry()
        s = reg.summary()
        self.assertEqual(s["n_total"], 5)
        self.assertEqual(s["n_active"], 5)
        self.assertEqual(s["by_type"]["CONCENTRATION"], 3)
        self.assertEqual(s["by_type"]["VAR_LIMIT"], 1)
        self.assertEqual(s["by_type"]["ES_LIMIT"], 1)

    def test_by_factor_returns_class_limits_too(self):
        """A limit on RiskFactorClass FOREIGN_EXCHANGE applies to
        FX_USDKES, FX_EURKES, etc.
        """
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import build_default_registry
        reg = build_default_registry()
        # FX_USDKES has both single-factor + class limits applicable
        usdkes = reg.by_factor(RiskFactor.FX_USDKES)
        ids = {l.limit_id for l in usdkes}
        self.assertIn("CONC_FX_USDKES_NET", ids)
        self.assertIn("CONC_FX_TOTAL", ids)
        # FX_EURKES has only the class limit
        eur = reg.by_factor(RiskFactor.FX_EURKES)
        eur_ids = {l.limit_id for l in eur}
        self.assertIn("CONC_FX_TOTAL", eur_ids)
        self.assertNotIn("CONC_FX_USDKES_NET", eur_ids)


class TestV1040SeverityClassification(unittest.TestCase):
    """ENH-MR-007 — utilization → severity bands."""

    def test_severity_thresholds(self):
        from utils.market_risk_limits import (
            BreachSeverity, _classify_severity)
        for util, expected in [
            (Decimal("0"), BreachSeverity.WITHIN_LIMIT),
            (Decimal("50"), BreachSeverity.WITHIN_LIMIT),
            (Decimal("79.99"), BreachSeverity.WITHIN_LIMIT),
            (Decimal("80"), BreachSeverity.WARN),
            (Decimal("99.99"), BreachSeverity.WARN),
            (Decimal("100"), BreachSeverity.BREACH),
            (Decimal("119.99"), BreachSeverity.BREACH),
            (Decimal("120"), BreachSeverity.SEVERE_BREACH),
            (Decimal("500"), BreachSeverity.SEVERE_BREACH),
        ]:
            self.assertEqual(
                _classify_severity(util), expected,
                f"{util}% → expected {expected}")


class TestV1040Monitor(unittest.TestCase):
    """ENH-MR-007 — LimitMonitor end-to-end."""

    def test_concentration_within_limit(self):
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import (
            BreachSeverity, LimitMonitor, build_default_registry)
        reg = build_default_registry()
        monitor = LimitMonitor(reg)
        # USD 1bn vs 2bn limit = 50%
        alerts = monitor.check_concentration(exposures_by_factor={
            RiskFactor.FX_USDKES: Decimal("1000000000"),
        })
        single = next(
            a for a in alerts
            if a.limit_id == "CONC_FX_USDKES_NET")
        self.assertEqual(
            single.severity, BreachSeverity.WITHIN_LIMIT)

    def test_concentration_severe_breach(self):
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import (
            BreachSeverity, LimitMonitor, LimitRegistry,
            DEFAULT_FX_CONCENTRATION_USD)
        reg = LimitRegistry()
        reg.register(DEFAULT_FX_CONCENTRATION_USD)
        monitor = LimitMonitor(reg)
        # 2.5bn vs 2bn = 125%
        alerts = monitor.check_concentration(exposures_by_factor={
            RiskFactor.FX_USDKES: Decimal("2500000000"),
        })
        self.assertEqual(len(alerts), 1)
        self.assertEqual(
            alerts[0].severity, BreachSeverity.SEVERE_BREACH)

    def test_var_limit_only_matches_exact_confidence_horizon(self):
        """VaR limit at 99%/1d should not trigger on 95%/1d obs."""
        from utils.market_risk_limits import (
            LimitMonitor, LimitRegistry, DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        monitor = LimitMonitor(reg)
        # Wrong confidence
        a1 = monitor.check_var(
            observed_var_kes=Decimal("100000000"),
            confidence=Decimal("0.95"), horizon_days=1)
        self.assertEqual(len(a1), 0)
        # Wrong horizon
        a2 = monitor.check_var(
            observed_var_kes=Decimal("100000000"),
            confidence=Decimal("0.99"), horizon_days=10)
        self.assertEqual(len(a2), 0)
        # Match — and trigger
        a3 = monitor.check_var(
            observed_var_kes=Decimal("75000000"),
            confidence=Decimal("0.99"), horizon_days=1)
        self.assertEqual(len(a3), 1)

    def test_class_limit_aggregates_across_factors(self):
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import (
            LimitMonitor, LimitRegistry, DEFAULT_FX_CLASS_LIMIT)
        reg = LimitRegistry()
        reg.register(DEFAULT_FX_CLASS_LIMIT)    # 5bn class limit
        monitor = LimitMonitor(reg)
        # 3bn + 2bn + 1bn = 6bn → 120% SEVERE_BREACH
        alerts = monitor.check_concentration(exposures_by_factor={
            RiskFactor.FX_USDKES: Decimal("3000000000"),
            RiskFactor.FX_EURKES: Decimal("2000000000"),
            RiskFactor.FX_GBPKES: Decimal("1000000000"),
        })
        self.assertEqual(len(alerts), 1)
        self.assertEqual(
            alerts[0].observed_kes, Decimal("6000000000"))

    def test_run_pass_aggregates_all_observations(self):
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import (
            LimitMonitor, build_default_registry)
        reg = build_default_registry()
        monitor = LimitMonitor(reg)
        report = monitor.run_pass(
            exposures_by_factor={
                RiskFactor.FX_USDKES: Decimal("1500000000"),
            },
            var_observation=(
                Decimal("45000000"), Decimal("0.99"), 1),
            es_observation=(
                Decimal("180000000"), Decimal("0.975"), 10),
        )
        # At least 3 limits checked (1 single FX, 1 class FX, 1 VaR,
        # 1 ES — equity not relevant here)
        self.assertGreaterEqual(report.n_limits_checked, 3)
        self.assertFalse(report.is_clean())

    def test_negative_exposure_treated_as_absolute(self):
        """Net SHORT counts as exposure for concentration."""
        from utils.market_risk_factors import RiskFactor
        from utils.market_risk_limits import (
            BreachSeverity, LimitMonitor, LimitRegistry,
            DEFAULT_FX_CONCENTRATION_USD)
        reg = LimitRegistry()
        reg.register(DEFAULT_FX_CONCENTRATION_USD)
        monitor = LimitMonitor(reg)
        alerts = monitor.check_concentration(exposures_by_factor={
            RiskFactor.FX_USDKES: Decimal("-2500000000"),
        })
        self.assertEqual(
            alerts[0].severity, BreachSeverity.SEVERE_BREACH)


class TestV1040AlertTriage(unittest.TestCase):
    """Per Rule 1 + Rule 7."""

    def test_alert_carries_full_triage_info(self):
        from utils.market_risk_limits import (
            BreachSeverity, LimitMonitor, LimitRegistry,
            DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        monitor = LimitMonitor(reg)
        alerts = monitor.check_var(
            observed_var_kes=Decimal("60000000"),  # 120%
            confidence=Decimal("0.99"), horizon_days=1)
        a = alerts[0]
        self.assertEqual(a.severity, BreachSeverity.SEVERE_BREACH)
        self.assertEqual(a.observed_kes, Decimal("60000000"))
        self.assertEqual(a.threshold_kes, Decimal("50000000"))
        self.assertEqual(a.utilization_pct, Decimal("120.00"))
        self.assertGreater(len(a.framework_refs), 0)
        self.assertGreater(len(a.suggested_action), 0)
        self.assertIn("Board", a.escalation_target)

    def test_alert_id_deterministic_for_dedup(self):
        from utils.market_risk_limits import (
            LimitMonitor, LimitRegistry, DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        monitor = LimitMonitor(reg)
        alerts1 = monitor.check_var(
            observed_var_kes=Decimal("60000000"),
            confidence=Decimal("0.99"), horizon_days=1)
        alerts2 = monitor.check_var(
            observed_var_kes=Decimal("60000000"),
            confidence=Decimal("0.99"), horizon_days=1)
        self.assertEqual(
            alerts1[0].alert_id, alerts2[0].alert_id)

    def test_severity_bands_have_distinct_escalation_targets(self):
        """Per Rule 7: human oversight scales with severity."""
        from utils.market_risk_limits import (
            BreachSeverity, LimitMonitor, LimitRegistry,
            DEFAULT_VAR_LIMIT_99_1D)
        reg = LimitRegistry()
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        monitor = LimitMonitor(reg)
        # WARN at 90% (45m vs 50m)
        warn = monitor.check_var(
            observed_var_kes=Decimal("45000000"),
            confidence=Decimal("0.99"), horizon_days=1)[0]
        # BREACH at 110%
        breach = monitor.check_var(
            observed_var_kes=Decimal("55000000"),
            confidence=Decimal("0.99"), horizon_days=1)[0]
        # SEVERE at 130%
        severe = monitor.check_var(
            observed_var_kes=Decimal("65000000"),
            confidence=Decimal("0.99"), horizon_days=1)[0]
        self.assertEqual(warn.severity, BreachSeverity.WARN)
        self.assertEqual(breach.severity, BreachSeverity.BREACH)
        self.assertEqual(
            severe.severity, BreachSeverity.SEVERE_BREACH)
        # Three distinct escalation paths
        self.assertNotEqual(
            warn.escalation_target, breach.escalation_target)
        self.assertNotEqual(
            breach.escalation_target, severe.escalation_target)
        self.assertIn("Board", severe.escalation_target)


class TestV1040StandardsRegistry(unittest.TestCase):
    """ENH-MR-006 + ENH-MR-007 are active in registry."""

    def test_2_new_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        new_std = [
            s for s in STANDARDS_REGISTRY
            if s.standard_id in ("ENH-MR-006", "ENH-MR-007")]
        self.assertEqual(len(new_std), 2)
        for s in new_std:
            self.assertEqual(s.status, "active")
            self.assertEqual(s.implementation_batch, "v10.40")
            self.assertEqual(s.affected_engines,
                             ("market_risk_limits",))


class TestV1040ScenarioLibrary(unittest.TestCase):
    """5 LIMITS-* scenarios PASS when engines wired."""

    def test_5_limits_scenarios_in_library(self):
        from utils.scenario_simulator import TREASURY_SCENARIO_LIBRARY
        limits = [
            s for s in TREASURY_SCENARIO_LIBRARY
            if s.scenario_id.startswith("LIMITS-")]
        self.assertEqual(len(limits), 5)

    def test_limits_scenarios_pass(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY, ScenarioRunner)
        from utils import (
            market_risk_factors, market_risk_sensitivities,
            market_risk_var, market_risk_limits)
        engines = {
            "market_risk_factors": market_risk_factors,
            "market_risk_sensitivities": market_risk_sensitivities,
            "market_risk_var": market_risk_var,
            "market_risk_limits": market_risk_limits,
        }
        runner = ScenarioRunner(engines=engines)
        limits = [
            s for s in TREASURY_SCENARIO_LIBRARY
            if s.scenario_id.startswith("LIMITS-")]
        for scen in limits:
            result = runner.run(scen)
            self.assertEqual(
                result.n_failed, 0,
                f"{scen.scenario_id}: {result.n_failed} failures; "
                f"status={result.status}")


class TestV1040StructuralIntegrity(unittest.TestCase):
    """G128 baseline must remain stable after v10.40."""

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
            f"v10.40 introduced structural regression: "
            f"{comparison.summary}")


class TestV1040AuditScore(unittest.TestCase):
    """Audit score must remain ≥ 128 after v10.40."""

    def test_audit_score_at_least_128(self):
        import re
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "audit.py")],
            cwd=str(_ROOT),
            capture_output=True, text=True, timeout=180)
        self.assertIn("PASS", result.stdout)
        score_line = next(
            (ln for ln in result.stdout.splitlines()
             if "Score:" in ln), "")
        m = re.search(r"(\d+)/(\d+)", score_line)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 128)


if __name__ == "__main__":
    unittest.main()

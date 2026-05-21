"""tests/test_tsl_optimization_v10_182.py — v10.182 ENH-158
TSLOptimizationEngine tests."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_module_imports(self):
        from utils import tsl_optimization as t
        for n in ("TSLOptimizationEngine", "TSLTarget",
                   "TSLChannelType", "StaffingOutcome",
                   "StaffingPlan", "erlang_b",
                   "erlang_c_wait_probability",
                   "service_level", "required_agents"):
            assert hasattr(t, n), f"missing: {n}"


class TestRegistry:
    def test_enh_158_active(self):
        m = _load("reg_v182",
                    REPO_ROOT / "utils" / "standards_registry.py")
        s = next(
            (x for x in m.STANDARDS_REGISTRY
             if x.standard_id == "ENH-158"), None)
        assert s.status == "active"
        assert s.affected_engines == ("tsl_optimization",)
        assert s.implementation_batch == "v10.182"


class TestHubIntegration:
    def test_tier_32_has_tsl(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "TSLOptimizationEngine" in text
        assert "ENH-158" in text


class TestErlangCMath:
    def test_classic_erlang_c_textbook(self):
        """Classic textbook: 5 erlangs, 8 agents, 180s AHT, 20s
        threshold → SL ≈ 88%."""
        from utils.tsl_optimization import service_level
        sl = service_level(traffic=5.0, agents=8,
                            aht_seconds=180,
                            threshold_seconds=20)
        assert 0.85 <= sl <= 0.92, (
            f"expected ~0.88, got {sl:.4f}")

    def test_more_agents_higher_sl(self):
        from utils.tsl_optimization import service_level
        sl_5 = service_level(5.0, 5, 180, 20)
        sl_8 = service_level(5.0, 8, 180, 20)
        sl_12 = service_level(5.0, 12, 180, 20)
        assert sl_5 < sl_8 < sl_12

    def test_zero_traffic_perfect_sl(self):
        from utils.tsl_optimization import service_level
        assert service_level(0.0, 1, 60, 30) == 1.0

    def test_traffic_exceeds_agents_unstable(self):
        """When offered traffic >= number of agents the system is
        unstable — service level should not be > 0 for finite
        threshold."""
        from utils.tsl_optimization import service_level
        sl = service_level(traffic=10.0, agents=5,
                            aht_seconds=180,
                            threshold_seconds=20)
        assert sl == 0.0

    def test_required_agents_meets_target(self):
        from utils.tsl_optimization import (
            required_agents, service_level)
        n = required_agents(arrivals_per_hour=120,
                              aht_seconds=240,
                              target_pct=0.80,
                              threshold_seconds=30)
        traffic = 120 * 240 / 3600.0
        sl = service_level(traffic, n, 240, 30)
        assert sl >= 0.80
        # And n-1 should not meet it
        if n > 1:
            sl_below = service_level(traffic, n - 1, 240, 30)
            assert sl_below < 0.80

    def test_required_agents_invalid_target_pct(self):
        from utils.tsl_optimization import required_agents
        for bad in (0.0, 1.0, -0.1, 1.5):
            try:
                required_agents(100, 180, bad, 20)
            except ValueError:
                continue
            raise AssertionError(
                f"expected reject for target_pct={bad}")

    def test_required_agents_negative_arrivals(self):
        from utils.tsl_optimization import required_agents
        try:
            required_agents(-1, 180, 0.8, 20)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_service_level_invalid_aht(self):
        from utils.tsl_optimization import service_level
        try:
            service_level(5.0, 8, 0, 20)
        except ValueError:
            return
        raise AssertionError("expected reject for aht=0")


class TestTSLTarget:
    def test_invalid_pct_rejected(self):
        from utils.tsl_optimization import (
            TSLTarget, TSLChannelType)
        for bad in (0.0, 1.0, -0.5, 2.0):
            try:
                TSLTarget(channel_key="C",
                            channel_type=TSLChannelType.OTHER,
                            target_pct=bad,
                            threshold_seconds=30,
                            aht_seconds=120)
            except ValueError:
                continue
            raise AssertionError(
                f"expected reject for pct={bad}")

    def test_negative_threshold_rejected(self):
        from utils.tsl_optimization import (
            TSLTarget, TSLChannelType)
        try:
            TSLTarget(channel_key="C",
                        channel_type=TSLChannelType.OTHER,
                        target_pct=0.8, threshold_seconds=-1,
                        aht_seconds=120)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_zero_aht_rejected(self):
        from utils.tsl_optimization import (
            TSLTarget, TSLChannelType)
        try:
            TSLTarget(channel_key="C",
                        channel_type=TSLChannelType.OTHER,
                        target_pct=0.8, threshold_seconds=30,
                        aht_seconds=0)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_empty_channel_key_rejected(self):
        from utils.tsl_optimization import (
            TSLTarget, TSLChannelType)
        try:
            TSLTarget(channel_key="",
                        channel_type=TSLChannelType.OTHER,
                        target_pct=0.8, threshold_seconds=30,
                        aht_seconds=120)
        except ValueError:
            return
        raise AssertionError("expected reject")


class TestEngineOptimize:
    def _setup(self):
        from utils.tsl_optimization import (
            TSLOptimizationEngine, TSLTarget, TSLChannelType)
        eng = TSLOptimizationEngine()
        eng.set_target(TSLTarget(
            channel_key="CC:RETAIL",
            channel_type=TSLChannelType.CALL_CENTER,
            target_pct=0.80, threshold_seconds=30,
            aht_seconds=240))
        return eng

    def test_optimize_creates_plan(self):
        eng = self._setup()
        p = eng.optimize_staffing("CC:RETAIL", 120)
        assert p.plan_id.startswith("TSP-")
        assert p.required_agents >= 1
        assert p.achieved_service_level >= 0.80

    def test_optimize_with_planned_shortage(self):
        from utils.tsl_optimization import StaffingOutcome
        eng = self._setup()
        # Required ~11 for 120 cph @ 240s AHT, 80/30 — give 2
        p = eng.optimize_staffing("CC:RETAIL", 120,
                                    planned_agents=2)
        assert p.outcome == StaffingOutcome.SHORTAGE
        assert p.achieved_with_planned is not None

    def test_optimize_with_planned_surplus(self):
        from utils.tsl_optimization import StaffingOutcome
        eng = self._setup()
        p = eng.optimize_staffing("CC:RETAIL", 120,
                                    planned_agents=50)
        assert p.outcome == StaffingOutcome.SURPLUS

    def test_optimize_no_target_rejected(self):
        eng = self._setup()
        try:
            eng.optimize_staffing("MISSING", 100)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_optimize_zero_load_minimal(self):
        eng = self._setup()
        p = eng.optimize_staffing("CC:RETAIL", 0)
        assert p.required_agents >= 1
        # With zero load, even one agent gets perfect SL
        assert p.achieved_service_level == 1.0


class TestScenarioComparison:
    def _setup(self):
        from utils.tsl_optimization import (
            TSLOptimizationEngine, TSLTarget, TSLChannelType)
        eng = TSLOptimizationEngine()
        eng.set_target(TSLTarget(
            channel_key="CC:RETAIL",
            channel_type=TSLChannelType.CALL_CENTER,
            target_pct=0.80, threshold_seconds=30,
            aht_seconds=240))
        return eng

    def test_compare_scenarios_returns_per_target(self):
        eng = self._setup()
        out = eng.compare_scenarios(
            "CC:RETAIL", arrivals_per_hour=120,
            candidate_targets=[(0.70, 30), (0.80, 30),
                                 (0.90, 20)],
            aht_seconds=240)
        assert len(out) == 3
        for r in out:
            assert "required_agents" in r
            assert "feasible" in r

    def test_tighter_target_more_agents(self):
        eng = self._setup()
        out = eng.compare_scenarios(
            "CC:RETAIL", 120,
            [(0.70, 30), (0.80, 30), (0.90, 30), (0.95, 30)],
            aht_seconds=240)
        reqs = [r["required_agents"] for r in out]
        # Strictly non-decreasing
        for i in range(len(reqs) - 1):
            assert reqs[i] <= reqs[i + 1], (
                f"non-monotonic: {reqs}")


class TestHonestDeferrals:
    def test_board_summary_names_deferrals(self):
        from utils.tsl_optimization import TSLOptimizationEngine
        eng = TSLOptimizationEngine()
        b = eng.board_summary()
        defs = b.get("deferrals", {})
        for key in ("ABANDONMENT_MODELLING_ERLANG_A",
                     "SHRINKAGE_FACTOR_ROLLUP",
                     "INTRADAY_INTERVAL_OPTIMIZATION",
                     "MULTI_SKILL_ROUTING"):
            assert key in defs
            assert "DEFERRED" in defs[key]

    def test_board_names_erlang_c_model(self):
        from utils.tsl_optimization import TSLOptimizationEngine
        eng = TSLOptimizationEngine()
        b = eng.board_summary()
        assert "Erlang C" in b["model"]


class TestNoRegression:
    def test_audit_still_155_pass(self):
        m = _load("audit_v182", REPO_ROOT / "scripts" / "audit.py")
        assert len(m.GATES) == 155
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True

    def test_v181_workload_forecasting_works(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine)
        eng = WorkloadForecastingEngine()
        assert "ENH-157" in eng.board_summary()["engine"]

    def test_v180_work_mode_works(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine)
        eng = WorkModeDeclarationEngine()
        assert "ENH-156" in eng.board_summary()["engine"]

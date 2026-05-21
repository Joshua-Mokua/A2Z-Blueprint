"""tests/test_workload_forecasting_v10_181.py — v10.181 ENH-157
WorkloadForecastingEngine tests."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
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
        from utils import workload_forecasting as wf
        for n in ("WorkloadForecastingEngine", "ForecastMethod",
                   "HorizonUnit", "ForecastSnapshot",
                   "seasonal_naive_forecaster",
                   "linear_trend_forecaster"):
            assert hasattr(wf, n), f"missing: {n}"


class TestRegistry:
    def test_enh_157_active(self):
        m = _load("reg_v181",
                    REPO_ROOT / "utils" / "standards_registry.py")
        s = next(
            (x for x in m.STANDARDS_REGISTRY
             if x.standard_id == "ENH-157"), None)
        assert s is not None
        assert s.status == "active"
        assert s.affected_engines == ("workload_forecasting",)
        assert s.implementation_batch == "v10.181"


class TestHubIntegration:
    def test_tier_32_has_workload_forecasting(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "WorkloadForecastingEngine" in text
        assert "ENH-157" in text


class TestHistoryIngestion:
    def _eng(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine)
        return WorkloadForecastingEngine()

    def test_append_returns_count(self):
        eng = self._eng()
        n = eng.append_history(
            "C1",
            [(date.today() - timedelta(days=i), float(i))
             for i in range(5)])
        assert n == 5

    def test_reject_negative(self):
        eng = self._eng()
        try:
            eng.append_history("C", [(date.today(), -1.0)])
        except ValueError:
            return
        raise AssertionError("expected ValueError on negative")

    def test_reject_empty_channel_key(self):
        eng = self._eng()
        try:
            eng.append_history("", [(date.today(), 1.0)])
        except ValueError:
            return
        raise AssertionError("expected ValueError on empty channel")

    def test_history_sorted(self):
        eng = self._eng()
        # Append out of order
        eng.append_history("C", [
            (date.today(), 1.0),
            (date.today() - timedelta(days=2), 2.0),
            (date.today() - timedelta(days=1), 3.0),
        ])
        # Forecast should not blow up
        from utils.workload_forecasting import ForecastMethod
        snap = eng.forecast("C", ForecastMethod.LINEAR_TREND, 1)
        assert len(snap.points) == 1


class TestForecasters:
    def _hist(self, n=14):
        return [(date.today() - timedelta(days=n - 1 - i),
                 100.0 + i * 2)
                for i in range(n)]

    def test_seasonal_naive_returns_horizon_points(self):
        from utils.workload_forecasting import (
            seasonal_naive_forecaster)
        out = seasonal_naive_forecaster(self._hist(), 7)
        assert len(out) == 7
        for d, p, lo, up in out:
            assert lo <= p <= up

    def test_seasonal_naive_short_history_falls_back(self):
        from utils.workload_forecasting import (
            seasonal_naive_forecaster)
        # Less than season_length=7 should still return horizon
        out = seasonal_naive_forecaster(
            [(date.today(), 50.0), (date.today() - timedelta(days=1),
                                     45.0)], 5)
        assert len(out) == 5

    def test_linear_trend_extrapolates_upward(self):
        from utils.workload_forecasting import (
            linear_trend_forecaster)
        # Strictly upward — forecast > last historical value
        out = linear_trend_forecaster(self._hist(), 5)
        assert len(out) == 5
        last_hist_value = 100.0 + 13 * 2
        # Trend forecast should exceed last historical point
        assert out[-1][1] > last_hist_value

    def test_linear_trend_single_point_is_flat(self):
        from utils.workload_forecasting import (
            linear_trend_forecaster)
        out = linear_trend_forecaster([(date.today(), 50.0)], 3)
        assert len(out) == 3
        for _, p, lo, up in out:
            assert p == 50.0
            assert lo == 50.0 and up == 50.0

    def test_empty_history_rejected(self):
        from utils.workload_forecasting import (
            seasonal_naive_forecaster, linear_trend_forecaster)
        for fn in (seasonal_naive_forecaster,
                    linear_trend_forecaster):
            try:
                fn([], 3)
            except ValueError:
                continue
            raise AssertionError(
                f"{fn.__name__} should reject empty history")


class TestForecastEngine:
    def _setup(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine, ForecastMethod)
        eng = WorkloadForecastingEngine()
        hist = [(date.today() - timedelta(days=29 - i),
                 100.0 + i)
                for i in range(30)]
        eng.append_history("CH", hist)
        return eng, ForecastMethod

    def test_forecast_creates_snapshot(self):
        eng, M = self._setup()
        snap = eng.forecast("CH", M.SEASONAL_NAIVE, 7)
        assert snap.snapshot_id.startswith("FCS-")
        assert snap.method == M.SEASONAL_NAIVE
        assert len(snap.points) == 7

    def test_forecast_zero_horizon_rejected(self):
        eng, M = self._setup()
        try:
            eng.forecast("CH", M.SEASONAL_NAIVE, 0)
        except ValueError:
            return
        raise AssertionError("expected ValueError on horizon=0")

    def test_forecast_no_history_rejected(self):
        eng, M = self._setup()
        try:
            eng.forecast("MISSING", M.LINEAR_TREND, 5)
        except ValueError:
            return
        raise AssertionError("expected ValueError on missing channel")

    def test_external_forecaster_registration(self):
        eng, M = self._setup()
        called = {"n": 0}

        def fc(hist, h):
            called["n"] += 1
            last = sorted(hist)[-1][0]
            return [(last + timedelta(days=i+1), 999.0,
                     998.0, 1000.0) for i in range(h)]

        eng.register_forecaster("ml", fc)
        snap = eng.forecast("CH", M.EXTERNAL, 3,
                             external_name="ml")
        assert called["n"] == 1
        assert snap.points[0][1] == 999.0

    def test_external_unregistered_rejected(self):
        eng, M = self._setup()
        try:
            eng.forecast("CH", M.EXTERNAL, 3,
                          external_name="missing")
        except ValueError:
            return
        raise AssertionError(
            "expected ValueError on unregistered external")


class TestBackTesting:
    def test_record_actual_negative_rejected(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine)
        eng = WorkloadForecastingEngine()
        try:
            eng.record_actual("CH", date.today(), -1.0)
        except ValueError:
            return
        raise AssertionError("expected ValueError on negative actual")

    def test_evaluate_with_actuals(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine, ForecastMethod)
        eng = WorkloadForecastingEngine()
        hist = [(date.today() - timedelta(days=29 - i),
                 100.0 + i)
                for i in range(30)]
        eng.append_history("CH", hist)
        snap = eng.forecast("CH", ForecastMethod.LINEAR_TREND, 5)
        # Inject actuals matching forecast horizon
        for date_iso, p, _, _ in snap.points:
            d = date.fromisoformat(date_iso)
            eng.record_actual("CH", d, p * 1.02)
        ev = eng.evaluate_snapshot(snap.snapshot_id)
        assert ev["n_evaluated"] == 5
        assert ev["mape"] is not None
        assert 0 <= ev["coverage_pct"] <= 1.0

    def test_evaluate_no_overlap(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine, ForecastMethod)
        eng = WorkloadForecastingEngine()
        hist = [(date.today() - timedelta(days=10 - i), 100.0)
                for i in range(10)]
        eng.append_history("EMPTY_CH", hist)
        snap = eng.forecast("EMPTY_CH",
                             ForecastMethod.LINEAR_TREND, 3)
        ev = eng.evaluate_snapshot(snap.snapshot_id)
        assert ev["n_evaluated"] == 0
        assert ev["mape"] is None
        assert ev["coverage_pct"] is None

    def test_evaluate_unknown_snapshot_rejected(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine)
        eng = WorkloadForecastingEngine()
        try:
            eng.evaluate_snapshot("FCS-999999")
        except ValueError:
            return
        raise AssertionError("expected ValueError on unknown snapshot")


class TestSnapshotImmutability:
    def test_snapshot_is_frozen(self):
        from utils.workload_forecasting import ForecastSnapshot
        from dataclasses import FrozenInstanceError, fields
        # Verify dataclass is frozen by attempting mutation
        f = fields(ForecastSnapshot)
        assert len(f) > 0
        # Frozen dataclasses raise FrozenInstanceError on setattr —
        # construct a minimal one and try
        from datetime import date as _d
        from utils.workload_forecasting import (
            ForecastMethod, HorizonUnit)
        snap = ForecastSnapshot(
            snapshot_id="X", channel_key="C",
            method=ForecastMethod.LINEAR_TREND,
            horizon_steps=1, horizon_unit=HorizonUnit.DAY,
            history_window_start=_d.today(),
            history_window_end=_d.today(),
            points=tuple(),
        )
        try:
            snap.snapshot_id = "Y"
        except (FrozenInstanceError, AttributeError):
            return
        raise AssertionError("snapshot should be frozen")


class TestHonestDeferrals:
    def test_board_summary_names_deferrals(self):
        from utils.workload_forecasting import (
            WorkloadForecastingEngine)
        eng = WorkloadForecastingEngine()
        b = eng.board_summary()
        defs = b.get("deferrals", {})
        for key in ("ML_BACKBONE_XGBOOST",
                     "WEATHER_HOLIDAY_REGRESSORS",
                     "AUTO_RETRAIN_SCHEDULE",
                     "HIERARCHICAL_RECONCILIATION"):
            assert key in defs
        assert "DEFERRED" in defs["ML_BACKBONE_XGBOOST"]
        assert "XGBoost" in defs["ML_BACKBONE_XGBOOST"]


class TestNoRegression:
    def test_audit_still_155_pass(self):
        m = _load("audit_v181", REPO_ROOT / "scripts" / "audit.py")
        assert len(m.GATES) == 155
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True, (
                f"{gid} regressed: {r.get('violations')}")

    def test_v180_work_mode_still_works(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine)
        eng = WorkModeDeclarationEngine()
        b = eng.board_summary()
        assert "ENH-156" in b["engine"]

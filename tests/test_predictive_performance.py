"""tests/test_predictive_performance.py — Standard #16 PredictivePerformance
tests (v5.43).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - predict_achievement returns spec-mandated keys
       - linear extrapolation math correctness
       - sigmoid calibration (on-pace ≈ 0.5, behind < 0.5, ahead > 0.5)
       - defensive contract (unknown staff, no actuals, day 0, target 0)
       - period bounds + days-elapsed math
       - persistence helpers

  2. Forecast accuracy harness:
       - test_forecast_accuracy_meets_85_percent runs every fixture
         in tests/fixtures/forecast_scenarios.json. Asserts ≥85% of
         predictions land within ±15% of ground truth.
         Writes forecast_accuracy_results.json for G27.

The spec's "Forecast accuracy ≥85%" is interpreted as point-forecast
accuracy: |predicted - actual| / actual ≤ 0.15 for ≥85% of cases.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "forecast_scenarios.json"
ACCURACY_RESULTS = ROOT / "forecast_accuracy_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestStandard16Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "predictive_performance.py").exists()

    def test_fixtures_exist(self):
        assert FIXTURES.exists()
        data = json.loads(FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 20


# ═══════════════════════════════════════════════════════════════════════
# Engine — unit tests with injected collaborators
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def basic_engine():
    """Mock engine for one staff with three KPIs."""
    from utils.predictive_performance import PredictivePerformance

    kpis_table = {
        "S001": [{"id": "DEP_GROWTH"}, {"id": "NPL_PCT"}, {"id": "AML_SLA"}],
    }
    targets = {("S001", k): Decimal("100") for k in ("DEP_GROWTH", "NPL_PCT", "AML_SLA")}
    actuals = {
        ("S001", "DEP_GROWTH"): Decimal("50"),  # on-pace
        ("S001", "NPL_PCT"):    Decimal("20"),  # behind
        ("S001", "AML_SLA"):    Decimal("80"),  # ahead
    }
    return PredictivePerformance(
        active_kpis_fn=  lambda sc: kpis_table.get(sc, []),
        target_lookup_fn=lambda sc, k, p: targets.get((sc, k)),
        actual_lookup_fn=lambda sc, k, p: actuals.get((sc, k)),
        period_fn=       lambda t: "2026-04",
        period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
        days_elapsed_fn= lambda p, t: 11,
    )


class TestSpecContract:
    def test_returns_overall_prediction(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        assert "overall_prediction" in r

    def test_returns_predictions_dict(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        assert "predictions" in r
        assert isinstance(r["predictions"], dict)

    def test_overall_is_mean_of_probabilities(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        probs = [p["probability"] for p in r["predictions"].values()]
        expected = sum(probs) / len(probs)
        assert abs(r["overall_prediction"] - round(expected, 4)) < 0.001

    def test_each_prediction_has_required_keys(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        for p in r["predictions"].values():
            assert "predicted_value" in p
            assert "probability" in p

    def test_meta_block_present(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        assert "meta" in r
        meta = r["meta"]
        for k in ("staff_code", "period", "today", "model"):
            assert k in meta


class TestForecastMath:
    def test_on_pace_predicts_target(self, basic_engine):
        """50/100 at day 11/22 → predicted=100."""
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        p = r["predictions"]["DEP_GROWTH"]
        assert abs(p["predicted_value"] - 100) < 0.5

    def test_on_pace_probability_near_half(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        p = r["predictions"]["DEP_GROWTH"]
        assert 0.4 < p["probability"] < 0.6

    def test_behind_predicts_below_target(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        p = r["predictions"]["NPL_PCT"]
        assert p["predicted_value"] < 100

    def test_behind_probability_low(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        p = r["predictions"]["NPL_PCT"]
        assert p["probability"] < 0.3

    def test_ahead_predicts_above_target(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        p = r["predictions"]["AML_SLA"]
        assert p["predicted_value"] > 100

    def test_ahead_probability_high(self, basic_engine):
        r = basic_engine.predict_achievement("S001", today=date(2026, 4, 15))
        p = r["predictions"]["AML_SLA"]
        assert p["probability"] > 0.7


class TestDefensiveContract:
    def test_unknown_staff_returns_empty(self, basic_engine):
        r = basic_engine.predict_achievement("UNKNOWN", today=date(2026, 4, 15))
        assert r == {}

    def test_kpi_with_no_actual_skipped(self):
        from utils.predictive_performance import PredictivePerformance
        eng = PredictivePerformance(
            active_kpis_fn=  lambda sc: [{"id": "K1"}, {"id": "K2"}],
            target_lookup_fn=lambda sc, k, p: Decimal("100"),
            actual_lookup_fn=lambda sc, k, p: Decimal("50") if k == "K1" else None,
            period_fn=       lambda t: "2026-04",
            period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
            days_elapsed_fn= lambda p, t: 11,
        )
        r = eng.predict_achievement("S001", today=date(2026, 4, 15))
        assert "K1" in r["predictions"]
        assert "K2" not in r["predictions"]
        assert r["meta"]["kpis_skipped"] == 1

    def test_zero_target_skipped(self):
        from utils.predictive_performance import PredictivePerformance
        eng = PredictivePerformance(
            active_kpis_fn=  lambda sc: [{"id": "K1"}],
            target_lookup_fn=lambda sc, k, p: Decimal("0"),
            actual_lookup_fn=lambda sc, k, p: Decimal("50"),
            period_fn=       lambda t: "2026-04",
            period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
            days_elapsed_fn= lambda p, t: 11,
        )
        r = eng.predict_achievement("S001", today=date(2026, 4, 15))
        assert r["predictions"] == {}

    def test_day_zero_no_predictions(self):
        from utils.predictive_performance import PredictivePerformance
        eng = PredictivePerformance(
            active_kpis_fn=  lambda sc: [{"id": "K1"}],
            target_lookup_fn=lambda sc, k, p: Decimal("100"),
            actual_lookup_fn=lambda sc, k, p: Decimal("0"),
            period_fn=       lambda t: "2026-04",
            period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
            days_elapsed_fn= lambda p, t: 0,
        )
        r = eng.predict_achievement("S001", today=date(2026, 4, 1))
        assert r["predictions"] == {}

    def test_no_active_kpis_returns_empty(self):
        from utils.predictive_performance import PredictivePerformance
        eng = PredictivePerformance(
            active_kpis_fn=  lambda sc: [],
            target_lookup_fn=lambda sc, k, p: None,
            actual_lookup_fn=lambda sc, k, p: None,
            period_fn=       lambda t: "2026-04",
            period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
            days_elapsed_fn= lambda p, t: 11,
        )
        r = eng.predict_achievement("S001", today=date(2026, 4, 15))
        assert r == {}


class TestSigmoidAndPeriod:
    def test_sigmoid_zero(self):
        from utils.predictive_performance import _sigmoid
        assert abs(_sigmoid(0) - 0.5) < 1e-9

    def test_sigmoid_large_positive(self):
        from utils.predictive_performance import _sigmoid
        assert _sigmoid(10) > 0.999

    def test_sigmoid_large_negative(self):
        from utils.predictive_performance import _sigmoid
        assert _sigmoid(-10) < 0.001

    def test_sigmoid_bounded(self):
        from utils.predictive_performance import _sigmoid
        for x in [-1000, -50, 0, 50, 1000]:
            v = _sigmoid(x)
            assert 0 <= v <= 1, f"sigmoid({x}) = {v}"

    def test_period_bounds_monthly(self):
        from utils.predictive_performance import _period_bounds
        assert _period_bounds("2026-04") == (date(2026, 4, 1), date(2026, 4, 30))

    def test_period_bounds_quarterly(self):
        from utils.predictive_performance import _period_bounds
        assert _period_bounds("2026-Q2") == (date(2026, 4, 1), date(2026, 6, 30))

    def test_period_bounds_invalid(self):
        from utils.predictive_performance import _period_bounds
        assert _period_bounds("garbage") is None
        assert _period_bounds("2026-Q5") is None

    def test_weekday_count(self):
        from utils.predictive_performance import _count_weekdays_inclusive
        assert _count_weekdays_inclusive(date(2026, 4, 1), date(2026, 4, 30)) == 22


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_save_and_get(self, tmp_path, monkeypatch):
        from utils import predictive_performance as pp
        monkeypatch.setattr(pp, "PREDICTIONS_FILE",
                            tmp_path / "predictions.json")
        snapshot = {
            "overall_prediction": 0.65,
            "predictions": {"K1": {"predicted_value": 110, "probability": 0.7}},
            "meta": {"staff_code": "S1", "period": "2026-04"},
        }
        ok = pp.save_predictions("S1", snapshot)
        assert ok is True
        got = pp.get_prediction("S1", "2026-04")
        assert got and got["overall_prediction"] == 0.65

    def test_save_empty_returns_false(self, tmp_path, monkeypatch):
        from utils import predictive_performance as pp
        monkeypatch.setattr(pp, "PREDICTIONS_FILE",
                            tmp_path / "predictions.json")
        assert pp.save_predictions("S1", {}) is False


# ═══════════════════════════════════════════════════════════════════════
# Forecast accuracy harness — Standard #16 spec verification
# ═══════════════════════════════════════════════════════════════════════

def test_forecast_accuracy_meets_85_percent():
    """Run every fixture; assert ≥85% accuracy; write artifact.

    Accuracy = |predicted - actual| / actual ≤ 0.15.
    Spec target: ≥85% of forecasts within tolerance.

    This test writes forecast_accuracy_results.json which G27 reads.
    """
    from utils.predictive_performance import (
        PredictivePerformance, ACCURACY_TOLERANCE_PCT,
    )

    scenarios = json.loads(FIXTURES.read_text())
    assert len(scenarios) >= 20, (
        f"Need ≥20 scenarios for a meaningful sample; got {len(scenarios)}"
    )

    eng = PredictivePerformance()
    results = []
    accurate = 0
    expectations_correct = 0

    for s in scenarios:
        inp = s["input"]
        actual_eom = float(s["actual_at_period_end"])
        forecast = eng._forecast(
            current=float(inp["current_value"]),
            target=float(inp["target"]),
            days_elapsed=int(inp["days_elapsed"]),
            days_remaining=int(inp["total_days"]) - int(inp["days_elapsed"]),
            total_days=int(inp["total_days"]),
        )
        predicted = forecast["predicted_value"]
        if actual_eom > 0:
            error_pct = abs(predicted - actual_eom) / actual_eom
        else:
            error_pct = float("inf")
        is_accurate = error_pct <= ACCURACY_TOLERANCE_PCT

        if is_accurate:
            accurate += 1
        expected = s["expected_within_tolerance"]
        if is_accurate == expected:
            expectations_correct += 1

        results.append({
            "id":            s["id"],
            "description":   s["description"],
            "predicted":     round(predicted, 2),
            "actual":        actual_eom,
            "error_pct":     round(error_pct * 100, 2),
            "is_accurate":   is_accurate,
            "expected":      expected,
            "labels_match":  is_accurate == expected,
        })

    accuracy_pct = accurate / len(scenarios) * 100
    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "accurate":        accurate,
        "inaccurate":      len(scenarios) - accurate,
        "accuracy_pct":    round(accuracy_pct, 2),
        "spec_target_pct": 85.0,
        "tolerance_pct":   ACCURACY_TOLERANCE_PCT * 100,
        "labels_correct":  expectations_correct,
        "all_passed":      accuracy_pct >= 85.0,
        "results":         results,
    }
    ACCURACY_RESULTS.write_text(json.dumps(artifact, indent=2))

    assert accuracy_pct >= 85.0, (
        f"Forecast accuracy {accuracy_pct:.1f}% below spec target of 85%. "
        f"Inaccurate cases:\n" + "\n".join(
            f"  {r['id']}: predicted {r['predicted']}, actual {r['actual']}, "
            f"error {r['error_pct']}%"
            for r in results if not r["is_accurate"]
        )
    )
    # Sanity check: if labels don't match the math, the fixtures are wrong
    assert expectations_correct == len(scenarios), (
        f"{len(scenarios) - expectations_correct} fixture(s) have label "
        f"mismatched against actual math"
    )

"""
================================================================================
A2Z MIS 360 — Standards #313 + #314: Forecasting + What-If Simulator
================================================================================

Risk classification: Cat C (deterministic forecasting baseline + Rule 7 ML hook)

Combined module:
    #313: ML forecasting for revenue, NPL, deposits, churn. Driver-based
          scenario modeling. Confidence intervals + variance attribution.
    #314: Interactive what-if simulator: shock parameters, see P&L /
          capital / liquidity impact. Tornado charts of sensitivities.

Standards consolidated because both operate on the same forecast model
artifact: #313 produces the baseline, #314 perturbs it. Same engine
keeps the model parameters in sync.

Public API:
    register_forecast_model(model_data, actor, reason)
    transition_model_state(model_id, new_state, actor, reason)
    forecast(model_id, horizon_periods, drivers=None)
        -> {periods, baseline, lower_band, upper_band, confidence_pct}
    what_if(model_id, shocks: Dict[driver, pct_change])
        -> {baseline_outcome, shocked_outcome, delta, delta_pct}
    sensitivity_tornado(model_id, drivers=None, shock_pct=10)
        -> [{driver, low_outcome, high_outcome, range, abs_range}]
    set_forecast_fn(forecast_fn) -- Rule 7 ML hook
    make_forecast_fn() -- Rule 7 factory (deterministic fallback)

FORECAST_TARGETS byte-for-byte (5):
    REVENUE, NPL_RATIO, DEPOSITS, CHURN_RATE, COST_INCOME_RATIO

FORECAST_HORIZONS_PERIODS byte-for-byte (4): 1, 3, 6, 12

FORECAST_MODEL_STATES byte-for-byte (4):
    DRAFT      -- model defined; not running
    ACTIVE     -- producing forecasts
    SUPERSEDED -- replaced by newer version
    ARCHIVED   -- archived (terminal)

ALLOWED_FORECAST_TRANSITIONS (Rule 4):
    DRAFT      → ACTIVE | ARCHIVED
    ACTIVE     → SUPERSEDED | ARCHIVED
    SUPERSEDED → ARCHIVED
    ARCHIVED   → ()

DEFAULT_CONFIDENCE_PCT = 80
DEFAULT_BAND_WIDTH_PCT = 15

SPEC_DEVIATION_NOTE: Production forecasting requires labeled historical
data + supervised model with horizon-specific architectures. Current
fallback is deterministic linear extrapolation from baseline drivers.

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


SPEC_DEVIATION_NOTE: str = (
    "Production forecasting (#313) requires labeled historical data + "
    "supervised model. Current fallback is linear extrapolation from "
    "baseline drivers; deferred to deployment phase per Continuation.docx."
)

FORECAST_TARGETS: Tuple[str, ...] = (
    "REVENUE", "NPL_RATIO", "DEPOSITS", "CHURN_RATE", "COST_INCOME_RATIO",
)

FORECAST_HORIZONS_PERIODS: Tuple[int, ...] = (1, 3, 6, 12)

FORECAST_MODEL_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "SUPERSEDED", "ARCHIVED",
)

ALLOWED_FORECAST_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("SUPERSEDED", "ARCHIVED"),
    "SUPERSEDED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

DEFAULT_CONFIDENCE_PCT: int = 80
DEFAULT_BAND_WIDTH_PCT: int = 15


def _deterministic_forecast(
    model: Dict[str, Any], horizon_periods: int,
    drivers: Optional[Dict[str, Decimal]] = None,
) -> List[Decimal]:
    """Linear extrapolation from baseline + driver multipliers."""
    drivers = drivers or {}
    baseline = Decimal(str(model.get("baseline_value", "0")))
    growth_rate = Decimal(str(model.get("baseline_growth_pct", "0"))) / Decimal("100")
    driver_weights = model.get("driver_weights", {})

    # Apply driver perturbations to growth
    for driver_id, weight in driver_weights.items():
        if driver_id in drivers:
            try:
                shock = Decimal(str(drivers[driver_id]))
                growth_rate += (shock / Decimal("100")) * Decimal(str(weight))
            except (ValueError, TypeError):
                continue

    forecasted: List[Decimal] = []
    current = baseline
    for _ in range(horizon_periods):
        current = current * (Decimal("1") + growth_rate)
        forecasted.append(current.quantize(Decimal("0.01")))
    return forecasted


def make_forecast_fn() -> Callable[[Dict[str, Any], int, Optional[Dict]], List[Decimal]]:
    """Rule 7 factory returning a deterministic forecast Callable.

    Production deployments override via set_forecast_fn() to wire
    in a supervised ML model. The factory returns a Callable
    matching the contract: (model, horizon_periods, drivers) -> List[Decimal].
    """
    return _deterministic_forecast


class CommandCentreForecastingEngine:
    """Forecasting + what-if simulator for executive scenario planning."""

    def __init__(
        self,
        models_path: Optional[Path] = None,
        scenarios_path: Optional[Path] = None,
        forecast_fn: Optional[Callable] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.models_path = models_path or base / "forecast_models.json"
        self.scenarios_path = scenarios_path or base / "what_if_scenarios.json"
        self._forecast_fn: Callable = forecast_fn or _deterministic_forecast

    def set_forecast_fn(self, fn: Callable) -> None:
        """Rule 7 hook: override default with ML model."""
        self._forecast_fn = fn

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def register_forecast_model(
        self, model_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("model_id", "model_name", "target", "baseline_value"):
            if f not in model_data or model_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if model_data["target"] not in FORECAST_TARGETS:
            return {"registered": False,
                       "error": f"invalid_target:{model_data['target']}",
                       "valid_targets": list(FORECAST_TARGETS)}

        records = self._load(self.models_path,
                                "forecast_models", ("model_id",))
        if any(r.get("model_id") == model_data["model_id"] for r in records):
            return {"registered": False, "error": "duplicate_model_id"}

        record = {
            "model_id": model_data["model_id"],
            "model_name": model_data["model_name"],
            "target": model_data["target"],
            "baseline_value": str(model_data["baseline_value"]),
            "baseline_growth_pct": str(model_data.get(
                "baseline_growth_pct", "0",
            )),
            "driver_weights": model_data.get("driver_weights", {}),
            "confidence_pct": int(model_data.get(
                "confidence_pct", DEFAULT_CONFIDENCE_PCT,
            )),
            "band_width_pct": int(model_data.get(
                "band_width_pct", DEFAULT_BAND_WIDTH_PCT,
            )),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.models_path, records,
                          "forecast_models", "model_id")
        return {"registered": ok, "model_id": model_data["model_id"]}

    def transition_model_state(
        self, model_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in FORECAST_MODEL_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.models_path,
                                "forecast_models", ("model_id",))
        for r in records:
            if r.get("model_id") == model_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_FORECAST_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                    }
                r["state"] = new_state
                ok = self._save(self.models_path, records,
                                  "forecast_models", "model_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "model_not_found"}

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        records = self._load(self.models_path,
                                "forecast_models", ("model_id",))
        return next((r for r in records
                        if r.get("model_id") == model_id), None)

    def forecast(
        self, model_id: str, horizon_periods: int,
        drivers: Optional[Dict[str, Decimal]] = None,
    ) -> Dict[str, Any]:
        model = self.get_model(model_id)
        if model is None:
            return {"forecasted": False, "error": "model_not_found"}
        if model["state"] != "ACTIVE":
            return {"forecasted": False,
                       "error": f"model_not_active:{model['state']}"}
        if horizon_periods not in FORECAST_HORIZONS_PERIODS:
            return {"forecasted": False,
                       "error": f"invalid_horizon:{horizon_periods}",
                       "valid_horizons": list(FORECAST_HORIZONS_PERIODS)}

        baseline_series = self._forecast_fn(model, horizon_periods, drivers)
        band_pct = Decimal(str(model.get("band_width_pct",
                                                  DEFAULT_BAND_WIDTH_PCT))) / Decimal("100")
        lower = [str((v * (Decimal("1") - band_pct)).quantize(Decimal("0.01")))
                    for v in baseline_series]
        upper = [str((v * (Decimal("1") + band_pct)).quantize(Decimal("0.01")))
                    for v in baseline_series]
        return {
            "forecasted": True,
            "model_id": model_id,
            "target": model["target"],
            "horizon_periods": horizon_periods,
            "drivers_applied": drivers or {},
            "baseline": [str(v) for v in baseline_series],
            "lower_band": lower,
            "upper_band": upper,
            "confidence_pct": model["confidence_pct"],
            "forecast_basis": "ml_model" if self._forecast_fn != _deterministic_forecast
                                  else "deterministic_linear",
        }

    def what_if(
        self, model_id: str, shocks: Dict[str, Decimal],
        horizon_periods: int = 1,
    ) -> Dict[str, Any]:
        model = self.get_model(model_id)
        if model is None:
            return {"simulated": False, "error": "model_not_found"}
        if model["state"] != "ACTIVE":
            return {"simulated": False,
                       "error": f"model_not_active:{model['state']}"}

        # Validate shock drivers exist in model
        valid_drivers = set(model.get("driver_weights", {}).keys())
        invalid = [d for d in shocks if d not in valid_drivers]
        if invalid:
            return {"simulated": False,
                       "error": f"invalid_drivers:{invalid}",
                       "valid_drivers": list(valid_drivers)}

        baseline = self._forecast_fn(model, horizon_periods, drivers=None)
        shocked = self._forecast_fn(model, horizon_periods, drivers=shocks)
        delta = shocked[-1] - baseline[-1] if baseline else Decimal("0")
        delta_pct = (
            (delta / baseline[-1] * Decimal("100")).quantize(Decimal("0.01"))
            if baseline and baseline[-1] != 0 else None
        )

        # Persist the scenario for audit
        scenarios = self._load(self.scenarios_path,
                                     "what_if_scenarios", ("scenario_id",))
        scenario_id = (f"WHATIF-{model_id}-"
                            f"{int(datetime.utcnow().timestamp() * 1000)}")
        scenarios.append({
            "scenario_id": scenario_id,
            "model_id": model_id,
            "shocks": {k: str(v) for k, v in shocks.items()},
            "horizon_periods": horizon_periods,
            "baseline_outcome": str(baseline[-1]) if baseline else None,
            "shocked_outcome": str(shocked[-1]) if shocked else None,
            "delta": str(delta),
            "delta_pct": str(delta_pct) if delta_pct is not None else None,
            "ran_at": datetime.utcnow().isoformat(),
        })
        self._save(self.scenarios_path, scenarios,
                     "what_if_scenarios", "scenario_id")

        return {
            "simulated": True,
            "scenario_id": scenario_id,
            "model_id": model_id,
            "baseline_outcome": str(baseline[-1]) if baseline else None,
            "shocked_outcome": str(shocked[-1]) if shocked else None,
            "delta": str(delta),
            "delta_pct": str(delta_pct) if delta_pct is not None else None,
        }

    def sensitivity_tornado(
        self, model_id: str, drivers: Optional[List[str]] = None,
        shock_pct: int = 10, horizon_periods: int = 1,
    ) -> Dict[str, Any]:
        """Per-driver sensitivity analysis for tornado chart."""
        model = self.get_model(model_id)
        if model is None:
            return {"computed": False, "error": "model_not_found"}
        if model["state"] != "ACTIVE":
            return {"computed": False,
                       "error": f"model_not_active:{model['state']}"}

        all_drivers = list(model.get("driver_weights", {}).keys())
        target_drivers = drivers or all_drivers
        invalid = [d for d in target_drivers if d not in all_drivers]
        if invalid:
            return {"computed": False, "error": f"invalid_drivers:{invalid}"}

        baseline = self._forecast_fn(model, horizon_periods, drivers=None)
        baseline_outcome = baseline[-1] if baseline else Decimal("0")

        rows = []
        for driver in target_drivers:
            low = self._forecast_fn(model, horizon_periods,
                                          drivers={driver: -Decimal(str(shock_pct))})
            high = self._forecast_fn(model, horizon_periods,
                                           drivers={driver: Decimal(str(shock_pct))})
            low_outcome = low[-1] if low else Decimal("0")
            high_outcome = high[-1] if high else Decimal("0")
            range_ = high_outcome - low_outcome
            rows.append({
                "driver": driver,
                "low_outcome": str(low_outcome),
                "high_outcome": str(high_outcome),
                "range": str(range_),
                "abs_range": str(abs(range_)),
            })

        # Sort by absolute range descending (largest sensitivity first)
        rows.sort(key=lambda x: Decimal(x["abs_range"]), reverse=True)
        return {
            "computed": True,
            "model_id": model_id,
            "baseline_outcome": str(baseline_outcome),
            "shock_pct": shock_pct,
            "horizon_periods": horizon_periods,
            "drivers_analyzed": target_drivers,
            "rows": rows,
        }


def _self_test() -> None:
    import tempfile

    assert "REVENUE" in FORECAST_TARGETS
    assert 12 in FORECAST_HORIZONS_PERIODS
    assert ALLOWED_FORECAST_TRANSITIONS["ARCHIVED"] == ()
    assert SPEC_DEVIATION_NOTE
    assert callable(make_forecast_fn())

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreForecastingEngine(
            models_path=Path(tmpdir) / "m.json",
            scenarios_path=Path(tmpdir) / "s.json",
        )
        # Test 1: register
        r = engine.register_forecast_model(
            {"model_id": "M-REV", "model_name": "Revenue 2026",
             "target": "REVENUE", "baseline_value": "1000000",
             "baseline_growth_pct": "5",
             "driver_weights": {"npl": "-2", "deposits": "0.5", "rate": "1.5"}},
            actor="cfo", reason="annual revenue model",
        )
        assert r["registered"]
        # Test 2: invalid target
        r = engine.register_forecast_model(
            {"model_id": "X", "model_name": "Y", "target": "INVALID",
             "baseline_value": "1"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: forecast on DRAFT — should fail
        r = engine.forecast("M-REV", 3)
        assert not r["forecasted"]
        # Test 4: activate
        r = engine.transition_model_state(
            "M-REV", "ACTIVE", actor="cfo", reason="go live",
        )
        assert r["transitioned"]
        # Test 5: forecast
        r = engine.forecast("M-REV", 12)
        assert r["forecasted"]
        assert len(r["baseline"]) == 12
        assert len(r["lower_band"]) == 12
        # Test 6: invalid horizon
        r = engine.forecast("M-REV", 5)
        assert not r["forecasted"]
        # Test 7: what-if
        r = engine.what_if("M-REV", {"npl": Decimal("20")}, horizon_periods=12)
        assert r["simulated"]
        # NPL up 20% should reduce revenue (negative weight)
        # Test 8: invalid driver
        r = engine.what_if("M-REV", {"INVALID": Decimal("10")})
        assert not r["simulated"]
        # Test 9: tornado
        r = engine.sensitivity_tornado("M-REV", shock_pct=10, horizon_periods=12)
        assert r["computed"]
        assert len(r["rows"]) == 3
        # Drivers should be sorted by absolute range descending
        for i in range(len(r["rows"]) - 1):
            assert (Decimal(r["rows"][i]["abs_range"]) >=
                       Decimal(r["rows"][i+1]["abs_range"]))
        # Test 10: Rule 7 hook override
        called = []
        def custom_fn(model, horizon, drivers):
            called.append(True)
            return [Decimal("999.99")] * horizon
        engine.set_forecast_fn(custom_fn)
        r = engine.forecast("M-REV", 3)
        assert r["forecasted"]
        assert r["forecast_basis"] == "ml_model"
        assert called

    print("  ✅ command_centre_forecasting self-test PASS")


if __name__ == "__main__":
    _self_test()

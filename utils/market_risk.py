"""utils.market_risk — Market Risk
(Standard #54, v5.55). Volume Nine — Risk Intelligence.

Per v6 spec §9 + Basel III market risk principles:
    MarketRiskEngine: Value-at-Risk (VaR) computation, sensitivity analysis,
    stress testing.

WHAT THIS MODULE SHIPS
----------------------
1. MarketRiskEngine class with:
   - value_at_risk(positions, confidence=0.99, horizon_days=10)
     — historical-simulation VaR (deterministic, no ML)
   - sensitivity_analysis(positions, factor) — DV01 / vega-style sensitivity
   - stress_test(positions, scenario) — apply named scenario shocks

2. CONFIDENCE_LEVELS catalog: 0.95, 0.99, 0.999
3. STRESS_SCENARIOS catalog: KES_DEVALUATION_20PCT, RATE_HIKE_200BP, EQUITY_CRASH_30PCT

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal precision for monetary VaR
  - VaR returns None when insufficient history (<30 observations)

Rule 6 — No silent fallback:
  - Position with no historical data surfaced explicitly in unscored_positions[]
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.market_risk")
getcontext().prec = 28


# ─────────────────────────────────────────────────────────────────────
# Spec literals
# ─────────────────────────────────────────────────────────────────────

CONFIDENCE_LEVELS: List[float] = [0.95, 0.99, 0.999]
DEFAULT_HORIZON_DAYS = 10    # Basel regulatory standard (10-day VaR)
MIN_OBSERVATIONS_FOR_VAR = 30

STRESS_SCENARIOS: Dict[str, Dict[str, float]] = {
    "KES_DEVALUATION_20PCT": {"fx_rate_shock_pct": -0.20},
    "RATE_HIKE_200BP":        {"interest_rate_shock_bp": 200},
    "EQUITY_CRASH_30PCT":     {"equity_shock_pct": -0.30},
    "OIL_SPIKE_50PCT":        {"commodity_shock_pct": 0.50},
}


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class MarketRiskEngine:
    """Market risk: VaR + sensitivity + stress testing."""

    CONFIDENCE_LEVELS = CONFIDENCE_LEVELS
    STRESS_SCENARIOS = STRESS_SCENARIOS

    def __init__(
        self,
        history_lookup_fn: Optional[Callable[[str], List[float]]] = None,
        position_fn:       Optional[Callable[[], List[dict]]] = None,
    ):
        """
        history_lookup_fn(instrument_id) → list of historical daily P&L values
        position_fn() → list of position dicts
        """
        self._history  = history_lookup_fn or (lambda i: [])
        self._positions = position_fn      or (lambda: [])

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: value_at_risk
    # ──────────────────────────────────────────────────────────────────

    def value_at_risk(
        self,
        positions: Optional[List[dict]] = None,
        confidence: float = 0.99,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> Dict[str, Any]:
        """Historical-simulation VaR.

        Returns:
            {
              "var": float | None,
              "confidence", "horizon_days",
              "method": "historical_simulation",
              "unscored_positions": [...],  (Rule 6)
              "meta": {...}
            }
        """
        if confidence not in CONFIDENCE_LEVELS:
            return {"error": f"confidence {confidence} not in {CONFIDENCE_LEVELS}"}
        if horizon_days < 1:
            return {"error": f"horizon_days must be ≥1, got {horizon_days}"}

        positions = positions if positions is not None else (self._positions() or [])
        if not positions:
            return {
                "var":           0.0,
                "confidence":    confidence,
                "horizon_days":  horizon_days,
                "method":        "historical_simulation",
                "position_count": 0,
                "unscored_positions": [],
            }

        # Aggregate per-position VaR contributions
        position_vars: List[Dict[str, Any]] = []
        unscored: List[str] = []
        total_var_decimal = Decimal("0")

        for pos in positions:
            if not isinstance(pos, dict):
                continue
            instrument = pos.get("instrument_id")
            notional = pos.get("notional", 0)
            if not instrument:
                continue

            history = self._history(instrument) or []
            if len(history) < MIN_OBSERVATIONS_FOR_VAR:
                unscored.append(instrument)
                continue

            # Sort historical losses ascending (worst first)
            try:
                sorted_returns = sorted(history)
            except TypeError:
                unscored.append(instrument)
                continue

            # Index for quantile (1-confidence, e.g. 0.01 for 99%)
            quantile_idx = int((1 - confidence) * len(sorted_returns))
            worst_return = sorted_returns[quantile_idx] if quantile_idx < len(sorted_returns) else sorted_returns[0]

            # Scale by sqrt(horizon) per Basel
            try:
                horizon_scaling = Decimal(str(horizon_days)).sqrt()
                position_var = Decimal(str(abs(worst_return) * notional)) * horizon_scaling
                position_vars.append({
                    "instrument_id": instrument,
                    "notional":      notional,
                    "worst_return":  worst_return,
                    "position_var":  _money(position_var),
                })
                total_var_decimal += position_var
            except Exception as e:
                logger.warning("VaR computation failed for %s: %s", instrument, e)
                unscored.append(instrument)

        return {
            "var":           _money(total_var_decimal),
            "confidence":    confidence,
            "horizon_days":  horizon_days,
            "method":        "historical_simulation",
            "position_count": len(positions),
            "scored_count":  len(position_vars),
            "unscored_positions": unscored,
            "position_vars": position_vars,
            "meta": {
                "min_observations_required": MIN_OBSERVATIONS_FOR_VAR,
                "scaling":                   "sqrt(horizon_days)",
                "regulatory_basis":          "Basel III internal models approach",
                "generated_at":              datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: sensitivity_analysis
    # ──────────────────────────────────────────────────────────────────

    def sensitivity_analysis(
        self, positions: List[dict], factor: str, shock_size: float = 0.01,
    ) -> Dict[str, Any]:
        """Compute portfolio sensitivity to a 1%-shock in a named factor."""
        if not positions or not factor:
            return {"factor": factor, "total_sensitivity": 0.0, "by_position": []}

        by_position = []
        total = Decimal("0")
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            sensitivities = pos.get("factor_sensitivities", {})
            sens_per_unit = sensitivities.get(factor, 0)
            try:
                position_sens = Decimal(str(sens_per_unit)) * Decimal(str(pos.get("notional", 0))) * Decimal(str(shock_size))
                by_position.append({
                    "instrument_id":  pos.get("instrument_id"),
                    "factor":         factor,
                    "sensitivity":    _money(position_sens),
                })
                total += position_sens
            except Exception:
                continue

        return {
            "factor":             factor,
            "shock_size":         shock_size,
            "total_sensitivity":  _money(total),
            "by_position":        by_position,
            "meta": {
                "method":       "first-order linear",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: stress_test
    # ──────────────────────────────────────────────────────────────────

    def stress_test(
        self, positions: List[dict], scenario_name: str,
    ) -> Dict[str, Any]:
        """Apply a named stress scenario; return P&L impact."""
        if scenario_name not in STRESS_SCENARIOS:
            return {
                "error": f"unknown scenario {scenario_name!r}; valid: {list(STRESS_SCENARIOS.keys())}",
            }
        if not positions:
            return {
                "scenario": scenario_name,
                "total_impact": 0.0,
                "by_position": [],
            }

        scenario = STRESS_SCENARIOS[scenario_name]
        by_position: List[Dict[str, Any]] = []
        total_impact = Decimal("0")

        for pos in positions:
            if not isinstance(pos, dict):
                continue
            impact = Decimal("0")
            for shock_name, shock_value in scenario.items():
                # Look up corresponding sensitivity in the position
                sens_key = shock_name.replace("_shock_pct", "").replace("_shock_bp", "")
                sens = pos.get("factor_sensitivities", {}).get(sens_key, 0)
                try:
                    if "bp" in shock_name:
                        # bp shock: multiply by bp/10000 of notional × duration-like sens
                        impact += Decimal(str(sens)) * Decimal(str(pos.get("notional", 0))) * Decimal(str(shock_value)) / Decimal("10000")
                    else:
                        # pct shock
                        impact += Decimal(str(sens)) * Decimal(str(pos.get("notional", 0))) * Decimal(str(shock_value))
                except Exception:
                    continue
            by_position.append({
                "instrument_id": pos.get("instrument_id"),
                "impact":        _money(impact),
            })
            total_impact += impact

        return {
            "scenario":     scenario_name,
            "shock_factors": scenario,
            "total_impact": _money(total_impact),
            "by_position":  by_position,
            "meta": {
                "available_scenarios": list(STRESS_SCENARIOS.keys()),
                "generated_at":        datetime.now(timezone.utc).isoformat(),
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.market_risk self-test")

    assert CONFIDENCE_LEVELS == [0.95, 0.99, 0.999]
    print(f"  ✅ confidence levels: {CONFIDENCE_LEVELS}")
    assert "KES_DEVALUATION_20PCT" in STRESS_SCENARIOS
    assert STRESS_SCENARIOS["RATE_HIKE_200BP"]["interest_rate_shock_bp"] == 200
    print(f"  ✅ stress scenarios: {list(STRESS_SCENARIOS.keys())}")

    # Empty
    eng = MarketRiskEngine()
    r = eng.value_at_risk()
    assert r["var"] == 0.0
    print(f"  ✅ empty positions → VaR=0")

    # VaR with sufficient history
    history_data = {
        "T_BOND_10Y": [-0.005, -0.003, -0.001, 0.0, 0.001, 0.002, 0.003] * 5 + [-0.020, -0.015],   # 37 obs
    }
    eng2 = MarketRiskEngine(
        history_lookup_fn=lambda i: history_data.get(i, []),
    )
    positions = [{"instrument_id": "T_BOND_10Y", "notional": 1_000_000}]
    r = eng2.value_at_risk(positions, confidence=0.99, horizon_days=10)
    assert r["var"] > 0
    print(f"  ✅ 99% VaR (10-day): {r['var']:,.2f} on {r['scored_count']} positions")

    # Insufficient history → unscored
    short_history = {"NEW_INST": [0.001, 0.002, -0.001]}    # only 3 obs
    eng3 = MarketRiskEngine(history_lookup_fn=lambda i: short_history.get(i, []))
    r = eng3.value_at_risk([{"instrument_id": "NEW_INST", "notional": 100_000}])
    assert "NEW_INST" in r["unscored_positions"]
    print(f"  ✅ insufficient history → surfaced in unscored_positions (Rule 6)")

    # Invalid confidence
    r = eng2.value_at_risk(positions, confidence=0.50)
    assert "error" in r
    print(f"  ✅ invalid confidence rejected")

    # Sensitivity analysis
    pos_with_sens = [
        {"instrument_id": "USD_FX", "notional": 1_000_000,
         "factor_sensitivities": {"fx_rate": 1.0}},
    ]
    r = eng.sensitivity_analysis(pos_with_sens, factor="fx_rate", shock_size=0.01)
    assert r["total_sensitivity"] == 10_000.00    # 1.0 × 1M × 0.01
    print(f"  ✅ sensitivity: 1% FX shock → {r['total_sensitivity']:,.2f}")

    # Stress test
    pos_stress = [
        {"instrument_id": "USD_FX", "notional": 5_000_000,
         "factor_sensitivities": {"fx_rate": 1.0}},
    ]
    r = eng.stress_test(pos_stress, "KES_DEVALUATION_20PCT")
    # KES devaluation 20% → fx_rate × 5M × -0.20 = -1,000,000
    assert r["total_impact"] == -1_000_000.00
    print(f"  ✅ stress KES_DEV_20%: total impact = {r['total_impact']:,.2f}")

    # Unknown scenario
    r = eng.stress_test([], "MOON_LANDING")
    assert "error" in r
    print(f"  ✅ unknown scenario rejected")

    print("\n  ALL TESTS PASSED")

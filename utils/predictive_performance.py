"""utils.predictive_performance — Predictive Performance Analytics
(Standard #16, v5.43).

Per the master spec:

    class PredictivePerformance:
        def predict_achievement(self, staff_code, period_end):
            predictions = {}
            for kpi_id in current_actuals.keys():
                forecast = model.forecast(current_actuals[kpi_id], days_remaining)
                predictions[kpi_id] = {
                    "predicted_value": forecast.value,
                    "probability":     forecast.probability,
                }
            return {"overall_prediction": np.mean([
                p["probability"] for p in predictions.values()
            ])}

Verification:
  - Forecast accuracy ≥85%

How "accuracy" is interpreted
-----------------------------
A forecast is ACCURATE if `|predicted_value - actual_value| / actual_value ≤ 0.15`
(within ±15% of the eventual period-end actual). The 85% bar is then:
≥85% of forecasts in a labeled set land within ±15% of truth. This is
the most defensible interpretation of "forecast accuracy" — it's about
the point-prediction quality, not just whether a binary outcome
materialised.

The model
---------
Linear extrapolation from current pace — the simplest honest forecasting
model. Deterministic, transparent, matches what a banker would
compute manually:

    pace_per_day      = current_value / days_elapsed
    predicted_value   = pace_per_day * total_period_days

For probability of hitting target, we use a sigmoid over the
predicted-vs-target margin, with spread that tightens as the period
progresses (more time left = more uncertainty):

    margin      = (predicted_value - target) / target
    spread      = 0.20 * sqrt(days_remaining / total_period_days)
    probability = sigmoid(margin / spread)

This is a transparent model with no hidden ML magic. No fitted
parameters; no opaque library. The full trace is in the result `meta`
block so callers can verify or override.

Defensive contract
------------------
Returns {} for unknown staff. Returns no prediction for individual
KPIs with:
  - target == 0 (misconfigured)
  - days_elapsed == 0 (period hasn't started yet, no signal to extrapolate)
  - actual is None (not measured yet)
The engine never fabricates predictions where there's no data to
extrapolate from.

Honesty rules
-------------
The engine is a math function applied to observable inputs. It does
NOT:
  - Use opaque ML models with hidden assumptions
  - Pretend high confidence early in the period
  - Hide which inputs produced which prediction

Every result includes a `meta` block with `pace_per_day`, `total_days`,
`days_elapsed`, `days_remaining`, and `model = "linear_extrapolation"`
so the prediction is fully auditable.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.predictive")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"

# ── Defaults ─────────────────────────────────────────────────────────
ACCURACY_TOLERANCE_PCT = 0.15      # ±15% counts as accurate
SPEC_ACCURACY_TARGET   = 0.85      # ≥85% of forecasts within tolerance
DEFAULT_BASE_SPREAD    = 0.20      # base sigmoid spread parameter


# ─────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class KPIPrediction:
    kpi_id:           str = ""
    current_value:    float = 0.0
    target:           float = 0.0
    predicted_value:  float = 0.0
    probability:      float = 0.0    # P(actual ≥ target) at period_end
    days_elapsed:     int = 0
    days_remaining:   int = 0
    total_days:       int = 0
    pace_per_day:     float = 0.0
    model:            str = "linear_extrapolation"


@dataclass
class StaffPrediction:
    staff_code:        str = ""
    period:            str = ""
    today:             str = ""
    period_end:        str = ""
    predictions:       Dict[str, dict] = field(default_factory=dict)
    overall_prediction: float = 0.0
    generated_at:      str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class PredictivePerformance:
    """Standard #16 — Predictive Performance Analytics.

    Stateless: each call returns a fresh predictions dict. Persistence
    is the caller's responsibility (use save_predictions).
    """

    def __init__(
        self,
        active_kpis_fn:   Optional[Callable[[str], List[dict]]] = None,
        target_lookup_fn: Optional[Callable[[str, str, str], Optional[Decimal]]] = None,
        actual_lookup_fn: Optional[Callable[[str, str, str], Optional[Decimal]]] = None,
        period_fn:        Optional[Callable[[date], str]] = None,
        period_bounds_fn: Optional[Callable[[str], Optional[Tuple[date, date]]]] = None,
        days_elapsed_fn:  Optional[Callable[[str, date], int]] = None,
        base_spread:      float = DEFAULT_BASE_SPREAD,
    ):
        """All collaborators injectable for testability.

        active_kpis_fn(staff_code) -> [{"id"}, ...]
        target_lookup_fn(staff_code, kpi_id, period) -> Decimal | None
        actual_lookup_fn(staff_code, kpi_id, period) -> Decimal | None
        period_fn(today) -> "YYYY-MM" | "YYYY-Qn"
        period_bounds_fn(period) -> (start, end) | None
        days_elapsed_fn(period, today) -> int (Mon-Fri elapsed incl today)

        Defaults read from target_cascade + bsc_engine + monthly periods.
        """
        self._active_kpis    = active_kpis_fn   or _default_active_kpis
        self._target_lookup  = target_lookup_fn or _default_target_lookup
        self._actual_lookup  = actual_lookup_fn or _default_actual_lookup
        self._period         = period_fn        or _default_period
        self._period_bounds  = period_bounds_fn or _period_bounds
        self._days_elapsed   = days_elapsed_fn  or _default_days_elapsed
        self._base_spread    = base_spread

    # ──────────────────────────────────────────────────────────────────
    # Public API — spec entry
    # ──────────────────────────────────────────────────────────────────

    def predict_achievement(
        self,
        staff_code: str,
        period_end: Optional[str] = None,
        today: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Forecast period-end achievement for every active KPI.

        Returns spec-shaped dict:
            {
              "overall_prediction": <float in [0, 1]>,
              "predictions":        {kpi_id: {predicted_value, probability, ...}},
              "meta":               {staff_code, period, today, period_end},
            }

        Returns {} for unknown / inactive staff. KPIs without sufficient
        data (no actual / zero target / day-0) are EXCLUDED from
        predictions, not given fake forecasts.

        period_end is informational only — the engine derives the real
        period bounds from period_fn / period_bounds_fn.
        """
        if today is None:
            today = date.today()
        period = self._period(today)
        bounds = self._period_bounds(period)
        if not bounds:
            return {}

        period_start, period_actual_end = bounds
        # Honor caller-supplied period_end label, but compute math from real bounds
        eff_period_end = period_end or period_actual_end.isoformat()

        kpis = self._active_kpis(staff_code) or []
        if not kpis:
            return {}

        days_elapsed   = self._days_elapsed(period, today)
        total_days     = _count_weekdays_inclusive(period_start, period_actual_end)
        days_remaining = max(total_days - days_elapsed, 0)

        if total_days <= 0:
            return {}

        predictions: Dict[str, dict] = {}
        for kpi in kpis:
            kpi_id = kpi.get("id") if isinstance(kpi, dict) else None
            if not kpi_id:
                continue
            target = self._target_lookup(staff_code, kpi_id, period)
            actual = self._actual_lookup(staff_code, kpi_id, period)
            if target is None:
                continue
            try:
                target_f = float(target)
            except (TypeError, ValueError):
                continue
            if target_f <= 0:
                continue   # misconfigured — refuse to predict
            if actual is None:
                continue   # no data — refuse to fabricate
            try:
                actual_f = float(actual)
            except (TypeError, ValueError):
                continue
            if days_elapsed <= 0:
                continue   # period hasn't started — no pace signal

            forecast = self._forecast(
                current=actual_f,
                target=target_f,
                days_elapsed=days_elapsed,
                days_remaining=days_remaining,
                total_days=total_days,
            )
            predictions[kpi_id] = asdict(KPIPrediction(
                kpi_id=          kpi_id,
                current_value=   actual_f,
                target=          target_f,
                predicted_value= forecast["predicted_value"],
                probability=     forecast["probability"],
                days_elapsed=    days_elapsed,
                days_remaining=  days_remaining,
                total_days=      total_days,
                pace_per_day=    forecast["pace_per_day"],
                model=           "linear_extrapolation",
            ))

        overall = (
            sum(p["probability"] for p in predictions.values())
            / len(predictions)
        ) if predictions else 0.0

        return {
            "overall_prediction": round(overall, 4),
            "predictions":        predictions,
            "meta": {
                "staff_code":     staff_code,
                "period":         period,
                "today":          today.isoformat(),
                "period_end":     eff_period_end,
                "total_days":     total_days,
                "days_elapsed":   days_elapsed,
                "days_remaining": days_remaining,
                "kpis_predicted": len(predictions),
                "kpis_skipped":   max(len(kpis) - len(predictions), 0),
                "model":          "linear_extrapolation",
                "base_spread":    self._base_spread,
                "tolerance_pct":  ACCURACY_TOLERANCE_PCT,
                "generated_at":   datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # The forecasting math
    # ──────────────────────────────────────────────────────────────────

    def _forecast(
        self,
        current: float,
        target: float,
        days_elapsed: int,
        days_remaining: int,
        total_days: int,
    ) -> Dict[str, float]:
        """Linear extrapolation + sigmoid calibration.

        Given:
          current:        actual achieved so far
          target:         period-end target
          days_elapsed:   working days elapsed in period (incl today)
          days_remaining: working days left in period
          total_days:     total working days in period (= elapsed + remaining)

        Returns:
          predicted_value: linear extrapolation
          probability:     P(actual ≥ target) at period_end
          pace_per_day:    current/days_elapsed (for traceability)
        """
        if days_elapsed <= 0 or total_days <= 0:
            return {
                "predicted_value": float(current),
                "probability":     0.5,
                "pace_per_day":    0.0,
            }
        pace_per_day    = current / days_elapsed
        predicted_value = pace_per_day * total_days

        # Probability of hitting target via sigmoid over relative margin.
        # Spread tightens as the period progresses (more elapsed = more
        # certainty about pace). The sqrt prevents the spread from
        # collapsing to 0 in the last days, which would produce
        # ridiculous near-binary probabilities (real data has noise).
        if target <= 0:
            return {
                "predicted_value": predicted_value,
                "probability":     0.5,
                "pace_per_day":    pace_per_day,
            }
        margin = (predicted_value - target) / target
        # spread shrinks ~ sqrt(remaining/total). Clamped to a floor so it
        # doesn't go to zero on the last day.
        spread = max(
            self._base_spread * math.sqrt(max(days_remaining / total_days, 0.0)),
            0.05,
        )
        probability = _sigmoid(margin / spread)
        return {
            "predicted_value": predicted_value,
            "probability":     probability,
            "pace_per_day":    pace_per_day,
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid bounded to [0, 1]."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _period_bounds(period: str) -> Optional[Tuple[date, date]]:
    """Return (start, end) for YYYY-MM or YYYY-Qn period."""
    if not period or not isinstance(period, str):
        return None
    try:
        if "-Q" in period:
            year_str, q_str = period.split("-Q", 1)
            year = int(year_str); q = int(q_str)
            if q not in (1, 2, 3, 4):
                return None
            start_month = 3 * (q - 1) + 1
            end_month   = start_month + 2
            start = date(year, start_month, 1)
            _, last = monthrange(year, end_month)
            return start, date(year, end_month, last)
        if period.count("-") == 1:
            year_str, m_str = period.split("-", 1)
            year = int(year_str); m = int(m_str)
            start = date(year, m, 1)
            _, last = monthrange(year, m)
            return start, date(year, m, last)
    except (ValueError, IndexError):
        return None
    return None


def _count_weekdays_inclusive(start: date, end: date) -> int:
    """Count Mon-Fri days from start to end inclusive. 0 if start > end."""
    if start > end:
        return 0
    n = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            n += 1
        cur = date.fromordinal(cur.toordinal() + 1)
    return n


def _default_period(today: date) -> str:
    return f"{today.year:04d}-{today.month:02d}"


def _default_days_elapsed(period: str, today: date) -> int:
    bounds = _period_bounds(period)
    if not bounds:
        return 0
    start, end = bounds
    if today < start:
        return 0
    eff_today = min(today, end)
    return _count_weekdays_inclusive(start, eff_today)


# ─────────────────────────────────────────────────────────────────────
# Default collaborators
# ─────────────────────────────────────────────────────────────────────

def _safe_load(path: Path, default):
    try:
        from utils.db import db
        return db.load_json(path, default=default)
    except Exception as e:
        logger.warning("predictive: could not load %s: %s", path, e)
        return default


def _default_active_kpis(staff_code: str) -> List[dict]:
    """KPIs assigned to this staff via target_cascade allocations."""
    cascade = _safe_load(DATA_DIR / "target_cascade.json", {})
    if not isinstance(cascade, dict):
        return []
    kpis: List[dict] = []
    seen: set = set()
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        kpi_id = block.get("kpi", "")
        if not kpi_id:
            continue
        for alloc in block.get("allocations", []) or []:
            if not isinstance(alloc, dict):
                continue
            if str(alloc.get("to_code", "")) == str(staff_code):
                if kpi_id not in seen:
                    kpis.append({"id": kpi_id})
                    seen.add(kpi_id)
                break
    return kpis


def _default_target_lookup(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    cascade = _safe_load(DATA_DIR / "target_cascade.json", {})
    if not isinstance(cascade, dict):
        return None
    for _, block in cascade.items():
        if not isinstance(block, dict):
            continue
        if str(block.get("kpi", "")) != kpi_id:
            continue
        for alloc in block.get("allocations", []) or []:
            if isinstance(alloc, dict) and str(alloc.get("to_code", "")) == str(staff_code):
                amount = alloc.get("amount")
                if amount is None:
                    continue
                try:
                    return Decimal(str(amount))
                except Exception:
                    return None
    return None


def _default_actual_lookup(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    try:
        from utils import bsc_engine
        return bsc_engine.get_actual(staff_code, kpi_id, period)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_predictions(staff_code: str, predictions_dict: dict) -> bool:
    """Persist a predictions snapshot keyed by (staff, period)."""
    if not predictions_dict:
        return False
    period = (predictions_dict.get("meta") or {}).get("period", "")
    if not period:
        return False
    try:
        from utils.db import db
        existing = db.load_json(PREDICTIONS_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    by_staff = existing.setdefault(str(staff_code), {})
    if not isinstance(by_staff, dict):
        by_staff = {}
        existing[str(staff_code)] = by_staff
    by_staff[period] = predictions_dict
    try:
        from utils.db import db
        db.save_json(PREDICTIONS_FILE, existing)
        return True
    except Exception as e:
        logger.error("predictive: could not save: %s", e)
        return False


def get_prediction(staff_code: str, period: str) -> Optional[dict]:
    try:
        from utils.db import db
        existing = db.load_json(PREDICTIONS_FILE, default={})
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    by_staff = existing.get(str(staff_code), {})
    if not isinstance(by_staff, dict):
        return None
    return by_staff.get(period)


# ─────────────────────────────────────────────────────────────────────
# Self-test (`python -m utils.predictive_performance`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.predictive_performance self-test")

    # Build a deterministic mock engine
    kpis_table = {
        "S001": [{"id": "DEP_GROWTH"}, {"id": "NPL_PCT"}, {"id": "AML_SLA"}],
    }
    targets = {
        ("S001", "DEP_GROWTH"): Decimal("100"),
        ("S001", "NPL_PCT"):    Decimal("100"),
        ("S001", "AML_SLA"):    Decimal("100"),
    }
    actuals = {
        # On-pace: at day 11 of 22, actual=50 → predicted=100, prob ≈ 0.5
        ("S001", "DEP_GROWTH"): Decimal("50"),
        # Behind: at day 11 of 22, actual=20 → predicted=40, prob low
        ("S001", "NPL_PCT"):    Decimal("20"),
        # Ahead: at day 11 of 22, actual=80 → predicted=160, prob high
        ("S001", "AML_SLA"):    Decimal("80"),
    }

    eng = PredictivePerformance(
        active_kpis_fn=  lambda sc: kpis_table.get(sc, []),
        target_lookup_fn=lambda sc, k, p: targets.get((sc, k)),
        actual_lookup_fn=lambda sc, k, p: actuals.get((sc, k)),
        period_fn=       lambda today: "2026-04",
        period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
        days_elapsed_fn= lambda p, t: 11,
    )

    today = date(2026, 4, 15)

    # Case 1: All three KPIs predicted
    result = eng.predict_achievement("S001", today=today)
    assert result, "expected non-empty result for valid staff"
    assert "overall_prediction" in result
    assert "predictions" in result
    assert len(result["predictions"]) == 3
    print(f"  ✅ predicted 3 KPIs: overall={result['overall_prediction']:.3f}")

    # Case 2: On-pace KPI → predicted ≈ target → prob ≈ 0.5
    on_pace = result["predictions"]["DEP_GROWTH"]
    assert abs(on_pace["predicted_value"] - 100) < 1, f"got {on_pace['predicted_value']}"
    assert 0.40 < on_pace["probability"] < 0.60, f"got {on_pace['probability']}"
    print(f"  ✅ on-pace: predicted={on_pace['predicted_value']:.1f}, "
          f"prob={on_pace['probability']:.3f}")

    # Case 3: Behind-pace KPI → predicted < target → prob < 0.5
    behind = result["predictions"]["NPL_PCT"]
    assert behind["predicted_value"] < 50, f"got {behind['predicted_value']}"
    assert behind["probability"] < 0.30, f"got {behind['probability']}"
    print(f"  ✅ behind-pace: predicted={behind['predicted_value']:.1f}, "
          f"prob={behind['probability']:.3f}")

    # Case 4: Ahead-pace KPI → predicted > target → prob > 0.5
    ahead = result["predictions"]["AML_SLA"]
    assert ahead["predicted_value"] > 100, f"got {ahead['predicted_value']}"
    assert ahead["probability"] > 0.70, f"got {ahead['probability']}"
    print(f"  ✅ ahead-pace: predicted={ahead['predicted_value']:.1f}, "
          f"prob={ahead['probability']:.3f}")

    # Case 5: Unknown staff → empty
    r2 = eng.predict_achievement("UNKNOWN", today=today)
    assert r2 == {}, f"unknown should return empty, got {r2}"
    print(f"  ✅ unknown staff → empty")

    # Case 6: KPI with no actual → skipped
    eng_skip = PredictivePerformance(
        active_kpis_fn=  lambda sc: [{"id": "K1"}, {"id": "K2"}],
        target_lookup_fn=lambda sc, k, p: Decimal("100"),
        actual_lookup_fn=lambda sc, k, p: Decimal("50") if k == "K1" else None,
        period_fn=       lambda t: "2026-04",
        period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
        days_elapsed_fn= lambda p, t: 11,
    )
    r3 = eng_skip.predict_achievement("S001", today=today)
    assert len(r3["predictions"]) == 1, f"got {list(r3['predictions'].keys())}"
    assert r3["meta"]["kpis_skipped"] == 1
    print(f"  ✅ no-actual KPI skipped: predicted={list(r3['predictions'].keys())}")

    # Case 7: Day 0 → all KPIs skipped
    eng_day0 = PredictivePerformance(
        active_kpis_fn=  lambda sc: [{"id": "K1"}],
        target_lookup_fn=lambda sc, k, p: Decimal("100"),
        actual_lookup_fn=lambda sc, k, p: Decimal("0"),
        period_fn=       lambda t: "2026-04",
        period_bounds_fn=lambda p: (date(2026, 4, 1), date(2026, 4, 30)),
        days_elapsed_fn= lambda p, t: 0,
    )
    r4 = eng_day0.predict_achievement("S001", today=today)
    assert r4["predictions"] == {}, f"got {r4['predictions']}"
    print(f"  ✅ day 0 → no predictions (no signal to extrapolate)")

    # Case 8: Sigmoid sanity
    assert abs(_sigmoid(0) - 0.5) < 1e-9
    assert _sigmoid(10) > 0.9999
    assert _sigmoid(-10) < 0.0001
    print(f"  ✅ sigmoid bounds")

    # Case 9: Period bounds
    assert _period_bounds("2026-04") == (date(2026, 4, 1), date(2026, 4, 30))
    assert _period_bounds("2026-Q2") == (date(2026, 4, 1), date(2026, 6, 30))
    assert _period_bounds("garbage") is None
    print(f"  ✅ period bounds")

    print("\n  ALL TESTS PASSED")

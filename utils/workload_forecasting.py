"""utils.workload_forecasting — Workload Forecasting & Prediction
Engine (ENH-157, v10.181).

Phase 5 Resource Optimization — second standard of the workforce
optimization arc. Forecasts workload (transaction volume, call
volume, branch footfall, RM activity, settlement load, etc.)
across configurable horizons and channels.

DESIGN CONTRACT
---------------
1. Pluggable forecaster interface — engine accepts any callable
   that maps (history, horizon) → forecast points. v1 ships two
   built-in deterministic forecasters: SeasonalNaive and
   LinearTrend. The XGBoost integration named in the standard's
   description is HONESTLY DEFERRED — engine surfaces the hook
   but does not bundle the ML model.
2. Per-channel forecasts — each forecast is scoped to a channel
   key (e.g. "BRANCH:NRB-CBD", "CALL_CENTER:RETAIL", "DIGITAL:
   USSD"). Channels do not bleed into one another.
3. Confidence intervals — forecasters return (point, lower,
   upper) for each horizon step. SeasonalNaive uses historical
   period-over-period variance; LinearTrend uses residual
   stddev. Operators see uncertainty, not just point estimates.
4. Observed-vs-forecast back-testing — engine stores forecast
   snapshots and computes MAPE / WAPE / coverage on demand when
   actuals are appended. No silent re-forecasting that erases
   the forecast history.

REGULATORY BASIS
----------------
- Internal Capacity Planning Framework
- CBK Operational Risk Guidelines §6.4 (resource adequacy)
- BSC People perspective (workload-vs-capacity ratio is a P1 KPI)

HONEST DEFERRALS
----------------
- ML_BACKBONE_XGBOOST: real XGBoost integration deferred —
  description claims "0.99 correlation" but engine ships only
  deterministic baselines (SeasonalNaive, LinearTrend); ML hook
  is open via `register_forecaster()` for the model team
- WEATHER_HOLIDAY_REGRESSORS: external regressor enrichment
  deferred — engine does not pull from external calendars
- AUTO_RETRAIN_SCHEDULE: scheduled retraining cadence deferred
  to ops; engine exposes `forecast()` and lets caller decide
  cadence
- HIERARCHICAL_RECONCILIATION: bottom-up / top-down
  reconciliation across channel hierarchies deferred — engine
  forecasts each channel independently
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Optional, Sequence, Tuple)


# Forecaster signature: takes a sequence of (date, value) and
# returns a list of (date, point, lower, upper) for each horizon
# step. Caller passes desired horizon length.
Forecaster = Callable[
    [Sequence[Tuple[date, float]], int],
    List[Tuple[date, float, float, float]],
]


class ForecastMethod(Enum):
    SEASONAL_NAIVE = "seasonal_naive"
    LINEAR_TREND = "linear_trend"
    EXTERNAL = "external"  # registered via register_forecaster()


class HorizonUnit(Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


# ─── Built-in forecasters ──────────────────────────────────────


def seasonal_naive_forecaster(
    history: Sequence[Tuple[date, float]],
    horizon: int,
    season_length: int = 7,  # weekly seasonality default
) -> List[Tuple[date, float, float, float]]:
    """Repeat the last full season ahead by `horizon` steps.

    Confidence band uses period-over-period variance from history.
    """
    if not history:
        raise ValueError("history is empty — cannot forecast")
    if season_length < 1:
        raise ValueError("season_length must be >= 1")

    sorted_hist = sorted(history, key=lambda x: x[0])
    last_date = sorted_hist[-1][0]
    values = [v for _, v in sorted_hist]

    if len(values) < season_length:
        # Fall back to simple repeat of last value
        last_val = values[-1]
        sigma = _stddev(values) if len(values) > 1 else 0.0
        out = []
        for step in range(1, horizon + 1):
            out.append((
                last_date + timedelta(days=step),
                float(last_val),
                float(last_val) - 1.96 * sigma,
                float(last_val) + 1.96 * sigma,
            ))
        return out

    # Period-over-period diffs to estimate variance
    diffs = [
        values[i] - values[i - season_length]
        for i in range(season_length, len(values))
    ]
    sigma = _stddev(diffs) if diffs else 0.0

    out = []
    for step in range(1, horizon + 1):
        # Use values from last full season cyclically
        ref_idx = -season_length + ((step - 1) % season_length)
        if abs(ref_idx) > len(values):
            ref_idx = -1
        point = values[ref_idx]
        out.append((
            last_date + timedelta(days=step),
            float(point),
            float(point) - 1.96 * sigma,
            float(point) + 1.96 * sigma,
        ))
    return out


def linear_trend_forecaster(
    history: Sequence[Tuple[date, float]],
    horizon: int,
) -> List[Tuple[date, float, float, float]]:
    """Fit y = a + b*t (OLS) on history, project ahead."""
    if not history:
        raise ValueError("history is empty — cannot forecast")
    sorted_hist = sorted(history, key=lambda x: x[0])
    n = len(sorted_hist)
    if n < 2:
        # cannot fit slope — fall back to flat
        last_date, last_val = sorted_hist[-1]
        return [
            (last_date + timedelta(days=step), float(last_val),
             float(last_val), float(last_val))
            for step in range(1, horizon + 1)
        ]

    xs = list(range(n))
    ys = [v for _, v in sorted_hist]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0.0
    intercept = mean_y - slope * mean_x

    fitted = [intercept + slope * x for x in xs]
    residuals = [y - f for y, f in zip(ys, fitted)]
    sigma = _stddev(residuals) if len(residuals) > 1 else 0.0

    last_date = sorted_hist[-1][0]
    out = []
    for step in range(1, horizon + 1):
        x = n - 1 + step
        point = intercept + slope * x
        out.append((
            last_date + timedelta(days=step),
            float(point),
            float(point) - 1.96 * sigma,
            float(point) + 1.96 * sigma,
        ))
    return out


def _stddev(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


# ─── Engine ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class ForecastSnapshot:
    """Immutable forecast snapshot — created when forecast() is
    called, never re-written. Actuals append later via
    record_actual().
    """
    snapshot_id: str
    channel_key: str
    method: ForecastMethod
    horizon_steps: int
    horizon_unit: HorizonUnit
    history_window_start: date
    history_window_end: date
    points: Tuple[Tuple[str, float, float, float], ...]
    # (date_iso, point, lower, upper)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "channel_key": self.channel_key,
            "method": self.method.value,
            "horizon_steps": self.horizon_steps,
            "horizon_unit": self.horizon_unit.value,
            "history_window_start": self.history_window_start.isoformat(),
            "history_window_end": self.history_window_end.isoformat(),
            "points": [
                {"date": p[0], "point": p[1],
                 "lower": p[2], "upper": p[3]}
                for p in self.points
            ],
            "created_at": self.created_at.isoformat(),
        }


class WorkloadForecastingEngine:
    """In-memory forecasting service.

    PERSISTENCE — in-memory at v10.181; PG migration deferred.
    ML BACKBONE — XGBoost integration explicitly deferred; the
    `register_forecaster()` hook is the swap-in point when the
    model team ships.
    """

    def __init__(self):
        self._history: Dict[str, List[Tuple[date, float]]] = {}
        self._actuals: Dict[str, List[Tuple[date, float]]] = {}
        self._snapshots: Dict[str, ForecastSnapshot] = {}
        self._counter = 0
        self._external_forecasters: Dict[str, Forecaster] = {}

    # ─── data ingestion ─────────────────────────────────────────
    def append_history(
        self, channel_key: str, observations: Sequence[Tuple[date, float]]
    ) -> int:
        """Append observed historical workload points. Returns the
        number of points stored after the append."""
        if not channel_key:
            raise ValueError("channel_key required")
        bucket = self._history.setdefault(channel_key, [])
        for d, v in observations:
            if v < 0:
                raise ValueError(
                    f"workload value cannot be negative: "
                    f"{channel_key} {d} {v}")
            bucket.append((d, float(v)))
        bucket.sort(key=lambda x: x[0])
        return len(bucket)

    def record_actual(
        self, channel_key: str, observed_date: date, value: float
    ) -> None:
        """Append a realised observation against earlier
        forecasts. Used in back-testing."""
        if value < 0:
            raise ValueError("actual value cannot be negative")
        self._actuals.setdefault(channel_key, []).append(
            (observed_date, float(value)))

    # ─── forecasters ───────────────────────────────────────────
    def register_forecaster(
        self, name: str, forecaster: Forecaster
    ) -> None:
        """Register an external forecaster (e.g. ML model
        wrapper). Use ForecastMethod.EXTERNAL with this name."""
        if not name:
            raise ValueError("forecaster name required")
        self._external_forecasters[name] = forecaster

    # ─── forecast ──────────────────────────────────────────────
    def forecast(
        self,
        channel_key: str,
        method: ForecastMethod,
        horizon_steps: int,
        horizon_unit: HorizonUnit = HorizonUnit.DAY,
        external_name: Optional[str] = None,
    ) -> ForecastSnapshot:
        """Produce + store a forecast snapshot."""
        if horizon_steps < 1:
            raise ValueError("horizon_steps must be >= 1")
        history = self._history.get(channel_key)
        if not history:
            raise ValueError(
                f"no history recorded for channel {channel_key}")

        if method == ForecastMethod.SEASONAL_NAIVE:
            points = seasonal_naive_forecaster(history, horizon_steps)
        elif method == ForecastMethod.LINEAR_TREND:
            points = linear_trend_forecaster(history, horizon_steps)
        elif method == ForecastMethod.EXTERNAL:
            if not external_name or external_name not in (
                    self._external_forecasters):
                raise ValueError(
                    f"external forecaster '{external_name}' not "
                    f"registered")
            points = self._external_forecasters[external_name](
                history, horizon_steps)
        else:
            raise ValueError(f"unknown method: {method}")

        self._counter += 1
        snap_id = f"FCS-{self._counter:06d}"
        snap = ForecastSnapshot(
            snapshot_id=snap_id,
            channel_key=channel_key,
            method=method,
            horizon_steps=horizon_steps,
            horizon_unit=horizon_unit,
            history_window_start=history[0][0],
            history_window_end=history[-1][0],
            points=tuple(
                (p[0].isoformat(), p[1], p[2], p[3]) for p in points),
        )
        self._snapshots[snap_id] = snap
        return snap

    # ─── queries ───────────────────────────────────────────────
    def get_snapshot(
        self, snapshot_id: str
    ) -> Optional[ForecastSnapshot]:
        return self._snapshots.get(snapshot_id)

    def list_snapshots(
        self, channel_key: Optional[str] = None
    ) -> List[ForecastSnapshot]:
        out = list(self._snapshots.values())
        if channel_key:
            out = [s for s in out if s.channel_key == channel_key]
        return sorted(out, key=lambda s: s.created_at)

    # ─── back-testing ──────────────────────────────────────────
    def evaluate_snapshot(
        self, snapshot_id: str
    ) -> Dict[str, Any]:
        """Compute MAPE / WAPE / coverage for a snapshot whose
        forecast period now has actuals."""
        snap = self._snapshots.get(snapshot_id)
        if snap is None:
            raise ValueError(f"snapshot not found: {snapshot_id}")
        actuals = {
            d.isoformat(): v
            for d, v in self._actuals.get(snap.channel_key, [])
        }
        evaluated_pairs = []  # (date, point, lower, upper, actual)
        for date_iso, point, lower, upper in snap.points:
            if date_iso in actuals:
                evaluated_pairs.append(
                    (date_iso, point, lower, upper,
                     actuals[date_iso]))

        n_eval = len(evaluated_pairs)
        if n_eval == 0:
            return {
                "snapshot_id": snapshot_id,
                "n_evaluated": 0,
                "mape": None,
                "wape": None,
                "coverage_pct": None,
                "note": "no actuals overlap forecast horizon",
            }

        # MAPE — mean absolute percentage error (skip zero actuals)
        ape_terms = []
        for _, point, _, _, actual in evaluated_pairs:
            if actual != 0:
                ape_terms.append(abs(point - actual) / abs(actual))
        mape = (sum(ape_terms) / len(ape_terms)) if ape_terms else None

        # WAPE — weighted absolute percentage error
        sum_abs_err = sum(
            abs(p - a) for _, p, _, _, a in evaluated_pairs)
        sum_abs_actual = sum(
            abs(a) for _, _, _, _, a in evaluated_pairs)
        wape = (sum_abs_err / sum_abs_actual
                 if sum_abs_actual else None)

        # Coverage — % of actuals inside [lower, upper]
        n_inside = sum(
            1 for _, _, lo, up, a in evaluated_pairs
            if lo <= a <= up)
        coverage_pct = n_inside / n_eval

        return {
            "snapshot_id": snapshot_id,
            "n_evaluated": n_eval,
            "mape": mape,
            "wape": wape,
            "coverage_pct": coverage_pct,
        }

    # ─── board ─────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        n_channels = len(self._history)
        n_snapshots = len(self._snapshots)
        by_method: Dict[str, int] = {}
        for s in self._snapshots.values():
            by_method[s.method.value] = (
                by_method.get(s.method.value, 0) + 1)
        return {
            "engine": "ENH-157 WorkloadForecastingEngine",
            "n_channels": n_channels,
            "n_snapshots": n_snapshots,
            "snapshots_by_method": by_method,
            "n_external_forecasters_registered": len(
                self._external_forecasters),
            "regulatory_basis": (
                "Internal Capacity Planning Framework + CBK "
                "Operational Risk Guidelines §6.4 + BSC People "
                "perspective"),
            "deferrals": {
                "ML_BACKBONE_XGBOOST": (
                    "DEFERRED — engine ships SeasonalNaive + "
                    "LinearTrend baselines only. Standard "
                    "description claims 'XGBoost 0.99 correlation' "
                    "— that integration arrives via "
                    "register_forecaster() when the model team "
                    "ships, not bundled at v10.181"),
                "WEATHER_HOLIDAY_REGRESSORS": (
                    "DEFERRED — no external regressor enrichment"),
                "AUTO_RETRAIN_SCHEDULE": (
                    "DEFERRED — caller controls retrain cadence"),
                "HIERARCHICAL_RECONCILIATION": (
                    "DEFERRED — channels forecast independently"),
            },
        }

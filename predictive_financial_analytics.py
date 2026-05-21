"""utils/predictive_financial_analytics.py — v10.63: PFA.

ENH-253 — Predictive Financial Analytics. Cat B — finance arc 5/10.

Diagnostic forecasting + variance analysis engine. Three deterministic
forecasting methods (linear trend, seasonal naive, simple exponential
smoothing); ML hook injectable per Rule 6 (ml_disabled flag surfaced
when no model supplied — engine NEVER fabricates predictions).

Per Rule 7, engine NEVER:
  - auto-rebudgets (produces forecasts; humans approve/adjust)
  - reallocates capital based on predictions
  - auto-revises forecasts on ingestion of new actuals
  - mutates inputs (frozen contract enforces this)

Per Rule 1, every Forecast surfaces method_used + horizon + confidence
band + ml_disabled flag + inputs_used + framework refs. Every Variance
surfaces actual + expected + variance_kes + variance_pct + materiality
+ direction + framework refs. Every DriverDecomposition surfaces each
contributing driver's individual contribution_kes + cumulative
explained variance + residual (unexplained).

Pure stdlib (Decimal + frozen dataclasses + statistics).
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "PredictiveFinancialAnalyticsEngine implements ENH-253. Pure "
    "stdlib (Decimal + dataclasses + statistics). Per Rule 1, "
    "every Forecast/Variance/DriverDecomposition surfaces full "
    "components + framework refs. Per Rule 6, ML-hook injectable "
    "via ml_predictor callable; ml_disabled=True surfaced with "
    "reason when no predictor provided — engine NEVER fabricates "
    "predictions. Per Rule 7, engine DIAGNOSTIC ONLY — produces "
    "forecasts/variance findings; never auto-rebudgets, never "
    "reallocates capital, never auto-revises, never mutates "
    "inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class ForecastMethod(Enum):
    LINEAR_TREND = "LINEAR_TREND"
    SEASONAL_NAIVE = "SEASONAL_NAIVE"
    EXPONENTIAL_SMOOTHING = "EXPONENTIAL_SMOOTHING"
    ML_HOOK = "ML_HOOK"


class VarianceDirection(Enum):
    FAVOURABLE = "FAVOURABLE"     # actual better than expected
    UNFAVOURABLE = "UNFAVOURABLE"  # actual worse than expected
    NEUTRAL = "NEUTRAL"           # within materiality


class VarianceMateriality(Enum):
    IMMATERIAL = "IMMATERIAL"     # below threshold
    MATERIAL = "MATERIAL"         # above threshold
    HIGHLY_MATERIAL = "HIGHLY_MATERIAL"  # ≥3× threshold


class TrendSignal(Enum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    FLAT = "FLAT"
    INFLECTION = "INFLECTION"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TimeSeriesPoint:
    period: str        # "YYYY-MM" or "YYYY-Q1"
    value_kes: Decimal

    def __post_init__(self) -> None:
        if not self.period:
            raise ValueError("period must be non-empty")


@dataclass(frozen=True)
class ActualVsExpected:
    metric_name: str
    period: str
    actual_kes: Decimal
    expected_kes: Decimal
    higher_is_better: bool = True

    def __post_init__(self) -> None:
        if not self.metric_name:
            raise ValueError("metric_name must be non-empty")


@dataclass(frozen=True)
class DriverContribution:
    """One driver's contribution to a variance."""
    driver_name: str
    base_value_kes: Decimal
    actual_value_kes: Decimal
    contribution_kes: Decimal


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ForecastPoint:
    period: str
    forecast_kes: Decimal
    confidence_low_kes: Optional[Decimal]
    confidence_high_kes: Optional[Decimal]


@dataclass(frozen=True)
class Forecast:
    metric_name: str
    method_used: ForecastMethod
    horizon_periods: int
    points: Tuple[ForecastPoint, ...]
    sample_size: int
    ml_disabled: bool
    ml_disabled_reason: str
    inputs_used: Tuple[str, ...]      # period strings used
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class VarianceFinding:
    finding_id: str
    metric_name: str
    period: str
    actual_kes: Decimal
    expected_kes: Decimal
    variance_kes: Decimal
    variance_pct: Decimal
    direction: VarianceDirection
    materiality: VarianceMateriality
    materiality_threshold_pct: Decimal
    description: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DriverDecomposition:
    """Decomposition of a composite variance into drivers."""
    metric_name: str
    period: str
    total_variance_kes: Decimal
    contributions: Tuple[DriverContribution, ...]
    explained_kes: Decimal
    residual_kes: Decimal
    residual_pct_of_total: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TrendFinding:
    metric_name: str
    signal: TrendSignal
    slope_per_period: Decimal
    sample_size: int
    inflection_period: Optional[str]
    description: str
    framework_refs: Tuple[str, ...] = ()


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class PredictiveFinancialAnalyticsEngine:
    """Diagnostic forecasting + variance analysis."""

    DEFAULT_MATERIALITY_PCT: Decimal = Decimal("0.05")   # 5%
    DEFAULT_TREND_FLAT_THRESHOLD_PCT: Decimal = Decimal("0.01")
    MIN_SAMPLE_FOR_TREND: int = 4
    MIN_SAMPLE_FOR_SEASONAL: int = 8

    # ── Forecasting ──────────────────────────────────────────────────
    def forecast(
        self,
        metric_name: str,
        history: Sequence[TimeSeriesPoint],
        horizon: int,
        method: ForecastMethod = ForecastMethod.LINEAR_TREND,
        seasonal_period: int = 12,
        smoothing_alpha: Decimal = Decimal("0.3"),
        ml_predictor: Optional[
            Callable[
                [Sequence[TimeSeriesPoint], int],
                Sequence[ForecastPoint]]] = None,
    ) -> Forecast:
        if horizon <= 0:
            raise ValueError("horizon must be > 0")
        if not history:
            raise ValueError("history must be non-empty")

        ml_disabled = False
        ml_disabled_reason = ""

        if method == ForecastMethod.ML_HOOK:
            if ml_predictor is None:
                ml_disabled = True
                ml_disabled_reason = (
                    "ML_HOOK requested but no ml_predictor "
                    "supplied — falling back to LINEAR_TREND")
                method = ForecastMethod.LINEAR_TREND
            else:
                points = tuple(ml_predictor(history, horizon))
                return Forecast(
                    metric_name=metric_name,
                    method_used=ForecastMethod.ML_HOOK,
                    horizon_periods=horizon,
                    points=points,
                    sample_size=len(history),
                    ml_disabled=False,
                    ml_disabled_reason="",
                    inputs_used=tuple(p.period for p in history),
                    framework_refs=(
                        "ENH-253 §forecast_ml",
                        "Per Rule 6 — ML-hook driven by caller-"
                        "supplied predictor"))

        if method == ForecastMethod.LINEAR_TREND:
            if len(history) < self.MIN_SAMPLE_FOR_TREND:
                ml_disabled = True
                ml_disabled_reason = (
                    f"sample size {len(history)} < required "
                    f"{self.MIN_SAMPLE_FOR_TREND} — using flat "
                    f"projection")
                last = history[-1].value_kes
                points = tuple(
                    ForecastPoint(
                        period=f"FUTURE-{i+1}",
                        forecast_kes=last,
                        confidence_low_kes=None,
                        confidence_high_kes=None)
                    for i in range(horizon))
            else:
                points = self._linear_trend(history, horizon)
        elif method == ForecastMethod.SEASONAL_NAIVE:
            if len(history) < self.MIN_SAMPLE_FOR_SEASONAL:
                ml_disabled = True
                ml_disabled_reason = (
                    f"sample size {len(history)} < required "
                    f"{self.MIN_SAMPLE_FOR_SEASONAL} for "
                    f"seasonal naive — falling back to "
                    f"LINEAR_TREND")
                method = ForecastMethod.LINEAR_TREND
                points = self._linear_trend(history, horizon)
            else:
                points = self._seasonal_naive(
                    history, horizon, seasonal_period)
        elif method == ForecastMethod.EXPONENTIAL_SMOOTHING:
            points = self._exp_smoothing(
                history, horizon, smoothing_alpha)
        else:
            raise ValueError(f"unsupported method: {method}")

        return Forecast(
            metric_name=metric_name,
            method_used=method,
            horizon_periods=horizon,
            points=points,
            sample_size=len(history),
            ml_disabled=ml_disabled,
            ml_disabled_reason=ml_disabled_reason,
            inputs_used=tuple(p.period for p in history),
            framework_refs=(
                f"ENH-253 §forecast_{method.value.lower()}",
                "Per Rule 7 — forecast surfaces uncertainty; "
                "never auto-rebudgets"))

    @staticmethod
    def _linear_trend(
        history: Sequence[TimeSeriesPoint], horizon: int,
    ) -> Tuple[ForecastPoint, ...]:
        n = len(history)
        xs = [Decimal(i) for i in range(n)]
        ys = [p.value_kes for p in history]
        x_mean = sum(xs) / n
        y_mean = sum(ys, Decimal("0")) / n
        num = sum(
            ((x - x_mean) * (y - y_mean)
             for x, y in zip(xs, ys)),
            Decimal("0"))
        den = sum(
            ((x - x_mean) ** 2 for x in xs), Decimal("0"))
        slope = num / den if den != 0 else Decimal("0")
        intercept = y_mean - slope * x_mean
        # Residual std for confidence band
        residuals = [
            y - (intercept + slope * x)
            for x, y in zip(xs, ys)]
        if n > 2:
            res_var = sum(
                (r ** 2 for r in residuals), Decimal("0")) / (
                    n - 2)
            res_std = (
                Decimal(
                    str(float(res_var) ** 0.5))).quantize(
                Decimal("0.01"))
        else:
            res_std = Decimal("0")
        points: List[ForecastPoint] = []
        for h in range(1, horizon + 1):
            x_next = Decimal(n - 1 + h)
            yhat = (intercept + slope * x_next).quantize(
                Decimal("0.01"))
            band = (Decimal("1.96") * res_std).quantize(
                Decimal("0.01"))
            points.append(ForecastPoint(
                period=f"FUTURE-{h}",
                forecast_kes=yhat,
                confidence_low_kes=yhat - band,
                confidence_high_kes=yhat + band))
        return tuple(points)

    @staticmethod
    def _seasonal_naive(
        history: Sequence[TimeSeriesPoint],
        horizon: int, season_len: int,
    ) -> Tuple[ForecastPoint, ...]:
        n = len(history)
        points: List[ForecastPoint] = []
        for h in range(1, horizon + 1):
            # Forecast h-step ahead = value from h periods ago in
            # the prior seasonal cycle: history[n - season_len + h - 1]
            idx = n - season_len + (h - 1) % season_len
            if idx < 0:
                idx = 0
            yhat = history[idx].value_kes
            points.append(ForecastPoint(
                period=f"FUTURE-{h}",
                forecast_kes=yhat,
                confidence_low_kes=None,
                confidence_high_kes=None))
        return tuple(points)

    @staticmethod
    def _exp_smoothing(
        history: Sequence[TimeSeriesPoint],
        horizon: int, alpha: Decimal,
    ) -> Tuple[ForecastPoint, ...]:
        if not (Decimal("0") < alpha <= Decimal("1")):
            raise ValueError("alpha must be in (0, 1]")
        s = history[0].value_kes
        for p in history[1:]:
            s = alpha * p.value_kes + (Decimal("1") - alpha) * s
        # Single-exponential smoothing: forecast is flat at level s
        s_q = s.quantize(Decimal("0.01"))
        points = tuple(
            ForecastPoint(
                period=f"FUTURE-{h}",
                forecast_kes=s_q,
                confidence_low_kes=None,
                confidence_high_kes=None)
            for h in range(1, horizon + 1))
        return points

    # ── Variance analysis ────────────────────────────────────────────
    def analyze_variance(
        self,
        comparisons: Sequence[ActualVsExpected],
        materiality_pct: Optional[Decimal] = None,
    ) -> Tuple[VarianceFinding, ...]:
        threshold = (
            materiality_pct
            if materiality_pct is not None
            else self.DEFAULT_MATERIALITY_PCT)
        findings: List[VarianceFinding] = []
        for c in comparisons:
            variance = c.actual_kes - c.expected_kes
            if c.expected_kes == 0:
                variance_pct = Decimal("0")
            else:
                variance_pct = (
                    variance / abs(c.expected_kes)).quantize(
                    Decimal("0.0001"))
            abs_pct = abs(variance_pct)
            if abs_pct < threshold:
                materiality = VarianceMateriality.IMMATERIAL
            elif abs_pct >= threshold * Decimal("3"):
                materiality = VarianceMateriality.HIGHLY_MATERIAL
            else:
                materiality = VarianceMateriality.MATERIAL
            # Direction (favourable/unfavourable)
            if abs_pct < threshold:
                direction = VarianceDirection.NEUTRAL
            else:
                actual_better = (
                    (c.actual_kes > c.expected_kes)
                    if c.higher_is_better
                    else (c.actual_kes < c.expected_kes))
                direction = (
                    VarianceDirection.FAVOURABLE
                    if actual_better
                    else VarianceDirection.UNFAVOURABLE)
            findings.append(VarianceFinding(
                finding_id=(
                    f"PFA-VAR-{c.metric_name}-{c.period}"),
                metric_name=c.metric_name,
                period=c.period,
                actual_kes=c.actual_kes,
                expected_kes=c.expected_kes,
                variance_kes=variance,
                variance_pct=variance_pct,
                direction=direction,
                materiality=materiality,
                materiality_threshold_pct=threshold,
                description=(
                    f"{c.metric_name} {c.period}: actual "
                    f"{c.actual_kes} vs expected "
                    f"{c.expected_kes} (variance "
                    f"{variance}, {variance_pct} pct, "
                    f"{direction.value}, {materiality.value})"),
                framework_refs=(
                    "ENH-253 §variance",
                    "Per Rule 7 — variance flagged; never "
                    "auto-explains, never auto-corrects")))
        return tuple(findings)

    # ── Driver decomposition ─────────────────────────────────────────
    def decompose_drivers(
        self,
        metric_name: str,
        period: str,
        total_variance_kes: Decimal,
        drivers: Sequence[DriverContribution],
    ) -> DriverDecomposition:
        explained = sum(
            (d.contribution_kes for d in drivers), Decimal("0"))
        residual = total_variance_kes - explained
        if total_variance_kes == 0:
            residual_pct = Decimal("0")
        else:
            residual_pct = (
                abs(residual) / abs(total_variance_kes)).quantize(
                Decimal("0.0001"))
        return DriverDecomposition(
            metric_name=metric_name,
            period=period,
            total_variance_kes=total_variance_kes,
            contributions=tuple(drivers),
            explained_kes=explained,
            residual_kes=residual,
            residual_pct_of_total=residual_pct,
            framework_refs=(
                "ENH-253 §driver_decomposition",
                "Per Rule 1 — all drivers + residual surfaced; "
                "operator can sanity-check each contribution"))

    # ── Trend signals ────────────────────────────────────────────────
    def detect_trend(
        self,
        metric_name: str,
        history: Sequence[TimeSeriesPoint],
    ) -> TrendFinding:
        if len(history) < self.MIN_SAMPLE_FOR_TREND:
            return TrendFinding(
                metric_name=metric_name,
                signal=TrendSignal.FLAT,
                slope_per_period=Decimal("0"),
                sample_size=len(history),
                inflection_period=None,
                description=(
                    f"insufficient sample size "
                    f"({len(history)} < "
                    f"{self.MIN_SAMPLE_FOR_TREND}) — defaulted "
                    f"to FLAT"),
                framework_refs=(
                    "ENH-253 §trend",))
        n = len(history)
        xs = [Decimal(i) for i in range(n)]
        ys = [p.value_kes for p in history]
        x_mean = sum(xs) / n
        y_mean = sum(ys, Decimal("0")) / n
        num = sum(
            ((x - x_mean) * (y - y_mean)
             for x, y in zip(xs, ys)), Decimal("0"))
        den = sum(
            ((x - x_mean) ** 2 for x in xs), Decimal("0"))
        slope = (num / den).quantize(Decimal("0.01")) if (
            den != 0) else Decimal("0")
        # Relative magnitude for FLAT-vs-trending classification
        if y_mean != 0:
            rel = abs(slope) / abs(y_mean)
        else:
            rel = Decimal("0")
        if rel < self.DEFAULT_TREND_FLAT_THRESHOLD_PCT:
            signal = TrendSignal.FLAT
        elif slope > 0:
            signal = TrendSignal.UPTREND
        else:
            signal = TrendSignal.DOWNTREND
        # Inflection: detect sign change in sub-trend
        inflection_period = None
        if n >= self.MIN_SAMPLE_FOR_TREND * 2:
            mid = n // 2
            first_half_slope = (
                (ys[mid - 1] - ys[0]) / Decimal(mid - 1)
                if mid > 1 else Decimal("0"))
            second_half_slope = (
                (ys[-1] - ys[mid]) / Decimal(n - mid - 1)
                if (n - mid - 1) > 0 else Decimal("0"))
            if (first_half_slope * second_half_slope) < 0:
                inflection_period = history[mid].period
                signal = TrendSignal.INFLECTION
        return TrendFinding(
            metric_name=metric_name,
            signal=signal,
            slope_per_period=slope,
            sample_size=n,
            inflection_period=inflection_period,
            description=(
                f"{metric_name}: slope {slope} per period over "
                f"{n} samples → {signal.value}"
                + (f" (inflection at {inflection_period})"
                   if inflection_period else "")),
            framework_refs=(
                "ENH-253 §trend",
                "Per Rule 7 — signals trends; never auto-acts"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _ts(period, value):
    return TimeSeriesPoint(
        period=period, value_kes=Decimal(str(value)))


def _test_forecast_validates_horizon():
    eng = PredictiveFinancialAnalyticsEngine()
    try:
        eng.forecast("M", [_ts("p1", 100)], horizon=0)
        assert False
    except ValueError:
        pass


def _test_forecast_validates_history():
    eng = PredictiveFinancialAnalyticsEngine()
    try:
        eng.forecast("M", [], horizon=3)
        assert False
    except ValueError:
        pass


def _test_linear_trend_basic():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100 + 10 * i) for i in range(6)]
    f = eng.forecast(
        "rev", history, horizon=3,
        method=ForecastMethod.LINEAR_TREND)
    assert f.method_used == ForecastMethod.LINEAR_TREND
    assert len(f.points) == 3
    # Should be roughly continuing the trend: 160, 170, 180
    assert f.points[0].forecast_kes == Decimal("160.00")
    assert f.points[2].forecast_kes == Decimal("180.00")
    assert f.ml_disabled is False


def _test_linear_trend_small_sample_fallback():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts("p0", 100), _ts("p1", 110)]
    f = eng.forecast("M", history, horizon=2)
    assert f.ml_disabled is True
    assert "sample size" in f.ml_disabled_reason.lower()
    # Flat at last value
    assert f.points[0].forecast_kes == Decimal("110")


def _test_seasonal_naive_repeats_cycle():
    eng = PredictiveFinancialAnalyticsEngine()
    # 12-month history with seasonal pattern
    pattern = [100, 110, 120, 130, 120, 110,
               100, 90, 80, 90, 100, 110]
    history = [
        _ts(f"2025-{i+1:02d}", v)
        for i, v in enumerate(pattern)]
    f = eng.forecast(
        "M", history, horizon=3,
        method=ForecastMethod.SEASONAL_NAIVE,
        seasonal_period=12)
    # Forecast h=1 = history[12-12+0] = pattern[0] = 100
    assert f.points[0].forecast_kes == Decimal("100")
    assert f.points[1].forecast_kes == Decimal("110")


def _test_seasonal_naive_small_sample_falls_back():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100 + i) for i in range(6)]
    f = eng.forecast(
        "M", history, horizon=2,
        method=ForecastMethod.SEASONAL_NAIVE,
        seasonal_period=12)
    assert f.method_used == ForecastMethod.LINEAR_TREND
    assert f.ml_disabled is True


def _test_exp_smoothing():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100) for i in range(6)]
    f = eng.forecast(
        "M", history, horizon=3,
        method=ForecastMethod.EXPONENTIAL_SMOOTHING,
        smoothing_alpha=Decimal("0.5"))
    # Stable at 100 → forecast 100
    assert f.points[0].forecast_kes == Decimal("100.00")


def _test_ml_hook_with_predictor_uses_it():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100) for i in range(6)]

    def my_pred(hist, horizon):
        return tuple(
            ForecastPoint(
                period=f"ML-{h}", forecast_kes=Decimal("999"),
                confidence_low_kes=Decimal("950"),
                confidence_high_kes=Decimal("1050"))
            for h in range(horizon))

    f = eng.forecast(
        "M", history, horizon=2,
        method=ForecastMethod.ML_HOOK, ml_predictor=my_pred)
    assert f.method_used == ForecastMethod.ML_HOOK
    assert f.ml_disabled is False
    assert f.points[0].forecast_kes == Decimal("999")


def _test_ml_hook_no_predictor_disables_with_reason():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100 + i) for i in range(6)]
    f = eng.forecast(
        "M", history, horizon=2,
        method=ForecastMethod.ML_HOOK, ml_predictor=None)
    assert f.ml_disabled is True
    assert "ML_HOOK" in f.ml_disabled_reason
    assert f.method_used == ForecastMethod.LINEAR_TREND


def _test_variance_immaterial():
    eng = PredictiveFinancialAnalyticsEngine()
    cmps = (
        ActualVsExpected(
            metric_name="rev", period="2026-04",
            actual_kes=Decimal("1010000"),
            expected_kes=Decimal("1000000")),
    )
    findings = eng.analyze_variance(cmps)
    assert len(findings) == 1
    assert findings[0].materiality == (
        VarianceMateriality.IMMATERIAL)
    assert findings[0].direction == VarianceDirection.NEUTRAL


def _test_variance_unfavourable_material():
    eng = PredictiveFinancialAnalyticsEngine()
    cmps = (
        ActualVsExpected(
            metric_name="rev", period="2026-04",
            actual_kes=Decimal("900000"),
            expected_kes=Decimal("1000000")),  # 10% short
    )
    findings = eng.analyze_variance(cmps)
    assert findings[0].materiality == (
        VarianceMateriality.MATERIAL)
    assert findings[0].direction == (
        VarianceDirection.UNFAVOURABLE)


def _test_variance_highly_material():
    eng = PredictiveFinancialAnalyticsEngine()
    cmps = (
        ActualVsExpected(
            metric_name="rev", period="2026-04",
            actual_kes=Decimal("500000"),
            expected_kes=Decimal("1000000")),  # 50% short
    )
    findings = eng.analyze_variance(cmps)
    assert findings[0].materiality == (
        VarianceMateriality.HIGHLY_MATERIAL)


def _test_variance_lower_better_metric():
    """Cost — actual < expected = FAVOURABLE."""
    eng = PredictiveFinancialAnalyticsEngine()
    cmps = (
        ActualVsExpected(
            metric_name="opex", period="2026-04",
            actual_kes=Decimal("450000"),
            expected_kes=Decimal("500000"),
            higher_is_better=False),
    )
    findings = eng.analyze_variance(cmps)
    assert findings[0].direction == VarianceDirection.FAVOURABLE


def _test_driver_decomposition():
    eng = PredictiveFinancialAnalyticsEngine()
    drivers = (
        DriverContribution(
            driver_name="price",
            base_value_kes=Decimal("100"),
            actual_value_kes=Decimal("105"),
            contribution_kes=Decimal("50000")),
        DriverContribution(
            driver_name="volume",
            base_value_kes=Decimal("1000"),
            actual_value_kes=Decimal("950"),
            contribution_kes=Decimal("-30000")),
    )
    decomp = eng.decompose_drivers(
        "rev", "2026-04",
        total_variance_kes=Decimal("25000"),
        drivers=drivers)
    # Explained = 50k - 30k = 20k; residual = 25k - 20k = 5k
    assert decomp.explained_kes == Decimal("20000")
    assert decomp.residual_kes == Decimal("5000")
    assert decomp.residual_pct_of_total == Decimal("0.20")


def _test_trend_uptrend():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [
        _ts(f"p{i}", 100 + 10 * i) for i in range(8)]
    t = eng.detect_trend("rev", history)
    assert t.signal == TrendSignal.UPTREND
    assert t.slope_per_period > 0


def _test_trend_flat():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 1000) for i in range(8)]
    t = eng.detect_trend("rev", history)
    assert t.signal == TrendSignal.FLAT


def _test_trend_inflection_detected():
    eng = PredictiveFinancialAnalyticsEngine()
    # Up then down
    values = [100, 110, 120, 130, 130, 120, 110, 100]
    history = [_ts(f"p{i}", v) for i, v in enumerate(values)]
    t = eng.detect_trend("rev", history)
    assert t.signal == TrendSignal.INFLECTION
    assert t.inflection_period is not None


def _test_trend_small_sample_flat():
    eng = PredictiveFinancialAnalyticsEngine()
    t = eng.detect_trend(
        "rev", [_ts("p0", 100), _ts("p1", 200)])
    assert t.signal == TrendSignal.FLAT


def _test_engine_does_not_mutate_inputs():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100 + i) for i in range(6)]
    eng.forecast("M", history, horizon=3)
    assert history[0].value_kes == Decimal("100")


def _test_full_provenance():
    eng = PredictiveFinancialAnalyticsEngine()
    history = [_ts(f"p{i}", 100 + i) for i in range(6)]
    f = eng.forecast("rev", history, horizon=3)
    assert f.metric_name == "rev"
    assert f.sample_size == 6
    assert len(f.inputs_used) == 6
    assert any("ENH-253" in r for r in f.framework_refs)


def self_test() -> None:
    tests = [
        _test_forecast_validates_horizon,
        _test_forecast_validates_history,
        _test_linear_trend_basic,
        _test_linear_trend_small_sample_fallback,
        _test_seasonal_naive_repeats_cycle,
        _test_seasonal_naive_small_sample_falls_back,
        _test_exp_smoothing,
        _test_ml_hook_with_predictor_uses_it,
        _test_ml_hook_no_predictor_disables_with_reason,
        _test_variance_immaterial,
        _test_variance_unfavourable_material,
        _test_variance_highly_material,
        _test_variance_lower_better_metric,
        _test_driver_decomposition,
        _test_trend_uptrend,
        _test_trend_flat,
        _test_trend_inflection_detected,
        _test_trend_small_sample_flat,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ predictive_financial_analytics self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ predictive_financial_analytics self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

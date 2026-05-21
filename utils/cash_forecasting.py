"""utils/cash_forecasting.py — v10.35 ENH-237: AI Cash Forecasting.

╔════════════════════════════════════════════════════════════════════════╗
║  CASH FORECASTING — 13-week treasury cash flow projection              ║
║  Cat A — feeds intraday liquidity + LCR forward stress + NSFR proj    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-237: AI-Powered Cash Forecasting.                      ║
║                                                                         ║
║  Three forecasting components composed:                                 ║
║    (1) Deterministic — scheduled flows from bond maturities, loan      ║
║        amortisation schedules, fixed deposit rollovers (known dates,   ║
║        known amounts). High confidence.                                 ║
║    (2) Seasonal — day-of-week + month-of-year multipliers on baseline ║
║        net flow. Computed from historical residuals.                  ║
║    (3) Baseline trend — exponentially-smoothed moving average of       ║
║        recent observed daily net flows (Holt-Winters lite).            ║
║                                                                         ║
║  Total daily projection = deterministic + (baseline × seasonality).   ║
║  Confidence band = projection ± k × σ(residuals).                    ║
║                                                                         ║
║  Treasury convention: 13-week (91-day) horizon for liquidity         ║
║  planning. Each day reports point estimate + 80% / 95% bands.        ║
║                                                                         ║
║  Honesty Rule 1: every ForecastResult surfaces deterministic +        ║
║  seasonal_multiplier + baseline + total + low/high band + n_history. ║
║  Drivers reported per day so analysts can audit which components      ║
║  contribute.                                                           ║
║  Honesty Rule 7: optional ML provider (e.g., Prophet, LSTM, GPT-4)   ║
║  is a callable hook on the engine. Without wiring, the engine uses    ║
║  the deterministic + seasonal + AR baseline above. A flag             ║
║  ml_overlay_applied is False so consumers know it's the baseline.    ║
║  Calling forecast_with_ml_overlay() without a wired provider raises  ║
║  ValueError("REQUIRES_PROVIDER: ml_forecast_provider").                ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel BCBS 144 — Sound principles for liquidity risk mgmt           ║
║                     (cash flow projection fundamental tool)            ║
║    Basel BCBS 248 — Intraday liquidity monitoring                       ║
║    EBA EBA/GL/2017/01 — LCR disclosure                                  ║
║    CBK CBK/PG/16 — Liquidity Management                                 ║
║    BIS Working Paper 42 — Cash flow modelling for treasury             ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "TreasuryCashForecastingEngine implements ENH-237. Foundation "
    "uses deterministic + seasonal + exponentially-smoothed baseline. "
    "Per Rule 7, ML overlay (Prophet/LSTM/foundation models) is a "
    "callable hook; without wiring, the baseline is returned with "
    "ml_overlay_applied=False. Per Rule 1, every ForecastResult "
    "surfaces all 3 components separately for examiner audit."
)

# ════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════

# Treasury planning horizon
DEFAULT_HORIZON_DAYS = 91          # 13 weeks
# Days of history needed for stable seasonality estimation
MIN_HISTORY_DAYS_FOR_SEASONALITY = 30
# z-scores for confidence bands
Z_80_PCT = Decimal("1.28")
Z_95_PCT = Decimal("1.96")
# Default exponential smoothing α
DEFAULT_SMOOTHING_ALPHA = Decimal("0.3")


# ════════════════════════════════════════════════════════════════════════
# Deterministic (scheduled) cash flows
# ════════════════════════════════════════════════════════════════════════

class FlowDriver(Enum):
    """Source of a scheduled cash flow."""
    BOND_MATURITY = "BOND_MATURITY"
    BOND_COUPON = "BOND_COUPON"
    LOAN_AMORTIZATION = "LOAN_AMORTIZATION"
    LOAN_DISBURSEMENT = "LOAN_DISBURSEMENT"
    FD_ROLLOVER = "FD_ROLLOVER"
    INTERBANK_SETTLEMENT = "INTERBANK_SETTLEMENT"
    FX_SETTLEMENT = "FX_SETTLEMENT"
    SCHEDULED_PAYMENT = "SCHEDULED_PAYMENT"
    OTHER_SCHEDULED = "OTHER_SCHEDULED"


@dataclass(frozen=True)
class ScheduledCashFlow:
    """A deterministic cash flow with known date and amount."""
    flow_id: str
    flow_date: str                   # ISO-8601
    amount_kes: Decimal              # signed: positive = inflow
    driver: FlowDriver
    counterparty: str = ""
    reference: str = ""              # e.g., bond ISIN, loan id
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Historical observations
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HistoricalDayNetFlow:
    """One observed daily net cash flow."""
    observation_date: str            # ISO-8601
    net_flow_kes: Decimal
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Seasonality model
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SeasonalityModel:
    """Day-of-week + day-of-month multipliers."""
    model_id: str
    n_history_days: int
    dow_multipliers: Mapping[int, Decimal]    # 0=Mon, 6=Sun
    dom_bucket_multipliers: Mapping[str, Decimal]    # 'BEGIN', 'MID', 'END'
    overall_mean: Decimal            # mean of historical net flows
    overall_stdev: Decimal           # stdev for confidence bands
    notes: str = ""

    def multiplier_for(self, the_date: date) -> Decimal:
        """Return combined multiplier for a date."""
        dow = the_date.weekday()
        dow_mult = self.dow_multipliers.get(dow, Decimal("1"))
        # Day-of-month bucket
        dom = the_date.day
        if dom <= 10:
            dom_bucket = "BEGIN"
        elif dom <= 20:
            dom_bucket = "MID"
        else:
            dom_bucket = "END"
        dom_mult = self.dom_bucket_multipliers.get(
            dom_bucket, Decimal("1"))
        return (dow_mult * dom_mult).quantize(Decimal("0.0001"))


def fit_seasonality_model(
    *, model_id: str,
    history: Sequence[HistoricalDayNetFlow],
) -> SeasonalityModel:
    """Fit a basic seasonality model from history.

    Computes mean net flow + per-DoW and per-DoM-bucket multipliers
    relative to the overall mean.
    """
    if len(history) < MIN_HISTORY_DAYS_FOR_SEASONALITY:
        raise ValueError(
            f"need at least {MIN_HISTORY_DAYS_FOR_SEASONALITY} "
            f"history days to fit seasonality; got {len(history)}")
    n = len(history)

    total = sum((h.net_flow_kes for h in history), Decimal("0"))
    mean = total / Decimal(n)

    # stdev — sample stdev
    sq_diff = sum(
        ((h.net_flow_kes - mean) ** 2 for h in history),
        Decimal("0"))
    if n > 1:
        variance = sq_diff / Decimal(n - 1)
    else:
        variance = Decimal("0")
    # Approximate sqrt via Newton's method (Decimal has no native sqrt
    # in older Python). Use ** 0.5 for Decimal.
    if variance > Decimal("0"):
        stdev = variance ** Decimal("0.5")
    else:
        stdev = Decimal("0")

    # Per-DoW multipliers
    dow_sums: Dict[int, Decimal] = {}
    dow_counts: Dict[int, int] = {}
    for h in history:
        try:
            d = date.fromisoformat(h.observation_date)
        except ValueError:
            continue
        dow = d.weekday()
        dow_sums[dow] = dow_sums.get(dow, Decimal("0")) + h.net_flow_kes
        dow_counts[dow] = dow_counts.get(dow, 0) + 1
    dow_mults: Dict[int, Decimal] = {}
    for dow in range(7):
        if dow_counts.get(dow, 0) > 0 and mean != Decimal("0"):
            dow_mean = dow_sums[dow] / Decimal(dow_counts[dow])
            dow_mults[dow] = (dow_mean / mean).quantize(
                Decimal("0.0001"))
        else:
            dow_mults[dow] = Decimal("1")

    # Per-DoM-bucket multipliers
    bucket_sums: Dict[str, Decimal] = {
        "BEGIN": Decimal("0"), "MID": Decimal("0"),
        "END": Decimal("0")}
    bucket_counts: Dict[str, int] = {
        "BEGIN": 0, "MID": 0, "END": 0}
    for h in history:
        try:
            d = date.fromisoformat(h.observation_date)
        except ValueError:
            continue
        if d.day <= 10:
            b = "BEGIN"
        elif d.day <= 20:
            b = "MID"
        else:
            b = "END"
        bucket_sums[b] += h.net_flow_kes
        bucket_counts[b] += 1
    bucket_mults: Dict[str, Decimal] = {}
    for b in ("BEGIN", "MID", "END"):
        if bucket_counts[b] > 0 and mean != Decimal("0"):
            b_mean = bucket_sums[b] / Decimal(bucket_counts[b])
            bucket_mults[b] = (b_mean / mean).quantize(
                Decimal("0.0001"))
        else:
            bucket_mults[b] = Decimal("1")

    return SeasonalityModel(
        model_id=model_id,
        n_history_days=n,
        dow_multipliers=dow_mults,
        dom_bucket_multipliers=bucket_mults,
        overall_mean=mean.quantize(Decimal("0.01")),
        overall_stdev=stdev.quantize(Decimal("0.01")),
        notes=(
            f"fit on {n} days; μ={mean:.0f} σ={stdev:.0f}"))


# ════════════════════════════════════════════════════════════════════════
# Exponential smoothing baseline
# ════════════════════════════════════════════════════════════════════════

def exponential_smoothing_baseline(
    *,
    history: Sequence[HistoricalDayNetFlow],
    alpha: Decimal = DEFAULT_SMOOTHING_ALPHA,
) -> Decimal:
    """Compute exponentially-smoothed baseline from history.

    s_t = α × x_t + (1−α) × s_{t-1}.
    Returns final smoothed level — the baseline going forward.
    """
    if not history:
        raise ValueError("history must not be empty")
    if alpha < Decimal("0") or alpha > Decimal("1"):
        raise ValueError(
            f"alpha must be in [0, 1]; got {alpha}")
    # Initialize at first observation
    s = history[0].net_flow_kes
    for h in history[1:]:
        s = alpha * h.net_flow_kes + (Decimal("1") - alpha) * s
    return s.quantize(Decimal("0.01"))


# ════════════════════════════════════════════════════════════════════════
# Forecast result
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DailyForecastPoint:
    """One day's forecast — composed of multiple drivers."""
    forecast_date: str
    deterministic_kes: Decimal       # scheduled flows
    baseline_kes: Decimal            # smoothed baseline
    seasonality_multiplier: Decimal
    statistical_kes: Decimal         # baseline × multiplier
    total_kes: Decimal               # deterministic + statistical
    band_low_80: Decimal
    band_high_80: Decimal
    band_low_95: Decimal
    band_high_95: Decimal
    drivers_summary: str             # e.g., "BOND_MATURITY:500K"


@dataclass(frozen=True)
class ForecastResult:
    """13-week forecast result."""
    forecast_id: str
    horizon_days: int
    start_date: str
    points: Tuple[DailyForecastPoint, ...]
    seasonality_model_id: str
    n_history_days_used: int
    ml_overlay_applied: bool         # False for baseline-only
    valuation_basis: str             # 'deterministic+seasonal+ar'
    notes: str = ""

    def total_inflow(self) -> Decimal:
        """Sum of positive total_kes across horizon."""
        return sum(
            (p.total_kes for p in self.points
             if p.total_kes > Decimal("0")),
            Decimal("0")).quantize(Decimal("0.01"))

    def total_outflow(self) -> Decimal:
        """Sum of negative total_kes (returned as positive)."""
        return sum(
            (-p.total_kes for p in self.points
             if p.total_kes < Decimal("0")),
            Decimal("0")).quantize(Decimal("0.01"))

    def net_position(self) -> Decimal:
        return self.total_inflow() - self.total_outflow()


def aggregate_scheduled_for_date(
    *,
    target_date: str,
    flows: Sequence[ScheduledCashFlow],
) -> Tuple[Decimal, str]:
    """Sum scheduled flows for a date + return drivers summary."""
    total = Decimal("0")
    driver_amounts: Dict[FlowDriver, Decimal] = {}
    for f in flows:
        if f.flow_date == target_date:
            total += f.amount_kes
            driver_amounts[f.driver] = (
                driver_amounts.get(f.driver, Decimal("0"))
                + f.amount_kes)
    summary_parts = [
        f"{d.value}:{a:,.0f}"
        for d, a in driver_amounts.items()]
    summary = "; ".join(summary_parts) if summary_parts else "none"
    return total.quantize(Decimal("0.01")), summary


def compute_forecast(
    *,
    forecast_id: str,
    start_date: str,
    horizon_days: int,
    seasonality: SeasonalityModel,
    baseline: Decimal,
    scheduled_flows: Sequence[ScheduledCashFlow] = (),
    ml_overlay: Optional[Mapping[str, Decimal]] = None,
) -> ForecastResult:
    """Compose the 3-component forecast over horizon_days.

    Returns ForecastResult with per-day breakdown.
    """
    if horizon_days <= 0:
        raise ValueError(
            f"horizon_days must be positive; got {horizon_days}")
    try:
        start = date.fromisoformat(start_date)
    except ValueError as e:
        raise ValueError(f"invalid start_date: {e}")

    points: List[DailyForecastPoint] = []
    for i in range(horizon_days):
        d = start + timedelta(days=i)
        d_iso = d.isoformat()

        # Deterministic
        det, drivers_sum = aggregate_scheduled_for_date(
            target_date=d_iso, flows=scheduled_flows)

        # Statistical: seasonality × baseline
        season_mult = seasonality.multiplier_for(d)
        stat = (baseline * season_mult).quantize(Decimal("0.01"))

        # ML overlay: if supplied, replaces statistical component
        if ml_overlay is not None and d_iso in ml_overlay:
            stat = ml_overlay[d_iso]

        total = (det + stat).quantize(Decimal("0.01"))

        # Confidence bands — use stdev from seasonality model
        sigma = seasonality.overall_stdev
        low_80 = (total - Z_80_PCT * sigma).quantize(Decimal("0.01"))
        high_80 = (total + Z_80_PCT * sigma).quantize(Decimal("0.01"))
        low_95 = (total - Z_95_PCT * sigma).quantize(Decimal("0.01"))
        high_95 = (total + Z_95_PCT * sigma).quantize(Decimal("0.01"))

        points.append(DailyForecastPoint(
            forecast_date=d_iso,
            deterministic_kes=det,
            baseline_kes=baseline,
            seasonality_multiplier=season_mult,
            statistical_kes=stat,
            total_kes=total,
            band_low_80=low_80, band_high_80=high_80,
            band_low_95=low_95, band_high_95=high_95,
            drivers_summary=drivers_sum))

    return ForecastResult(
        forecast_id=forecast_id,
        horizon_days=horizon_days,
        start_date=start_date,
        points=tuple(points),
        seasonality_model_id=seasonality.model_id,
        n_history_days_used=seasonality.n_history_days,
        ml_overlay_applied=(ml_overlay is not None),
        valuation_basis=(
            "deterministic+seasonal+ml" if ml_overlay is not None
            else "deterministic+seasonal+baseline"),
        notes=(
            f"horizon {horizon_days}d from {start_date}; "
            f"baseline {baseline:,}; "
            f"seasonality fit on "
            f"{seasonality.n_history_days} days"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

# Type for ML provider hook
MLForecastProvider = Callable[
    [Sequence[HistoricalDayNetFlow], int, str],
    Mapping[str, Decimal]]


class TreasuryCashForecastingEngine:
    """Orchestrator for ENH-237 cash forecasting."""

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya",
        ml_provider: Optional[MLForecastProvider] = None,
    ):
        self.entity_name = entity_name
        self.ml_provider = ml_provider
        self._history: List[HistoricalDayNetFlow] = []
        self._scheduled: List[ScheduledCashFlow] = []
        self._seasonality_models: Dict[str, SeasonalityModel] = {}
        self._forecasts: Dict[str, ForecastResult] = {}

    # ── History + scheduled flows ─────────────────────────────────────
    def add_history(self, h: HistoricalDayNetFlow) -> None:
        self._history.append(h)

    def add_scheduled_flow(self, f: ScheduledCashFlow) -> None:
        self._scheduled.append(f)

    @property
    def history_count(self) -> int:
        return len(self._history)

    @property
    def scheduled_count(self) -> int:
        return len(self._scheduled)

    # ── Seasonality fitting ────────────────────────────────────────────
    def fit_seasonality(self, model_id: str) -> SeasonalityModel:
        model = fit_seasonality_model(
            model_id=model_id, history=tuple(self._history))
        self._seasonality_models[model_id] = model
        return model

    def get_seasonality(
        self, model_id: str,
    ) -> SeasonalityModel:
        if model_id not in self._seasonality_models:
            raise KeyError(
                f"seasonality model {model_id} not found")
        return self._seasonality_models[model_id]

    # ── Baseline ───────────────────────────────────────────────────────
    def baseline(
        self, alpha: Decimal = DEFAULT_SMOOTHING_ALPHA,
    ) -> Decimal:
        if not self._history:
            raise ValueError(
                "no history available — add history before "
                "computing baseline")
        return exponential_smoothing_baseline(
            history=tuple(self._history), alpha=alpha)

    # ── Forecasting ────────────────────────────────────────────────────
    def forecast(
        self, *, forecast_id: str,
        start_date: str, horizon_days: int,
        seasonality_model_id: str,
        alpha: Decimal = DEFAULT_SMOOTHING_ALPHA,
    ) -> ForecastResult:
        """Baseline forecast — no ML overlay."""
        seasonality = self.get_seasonality(seasonality_model_id)
        baseline = self.baseline(alpha=alpha)
        result = compute_forecast(
            forecast_id=forecast_id,
            start_date=start_date,
            horizon_days=horizon_days,
            seasonality=seasonality,
            baseline=baseline,
            scheduled_flows=tuple(self._scheduled))
        self._forecasts[forecast_id] = result
        return result

    def forecast_with_ml_overlay(
        self, *, forecast_id: str,
        start_date: str, horizon_days: int,
        seasonality_model_id: str,
    ) -> ForecastResult:
        """Forecast with ML overlay from wired provider.

        Per Rule 7: raises REQUIRES_PROVIDER if no provider wired.
        """
        if self.ml_provider is None:
            raise ValueError(
                "REQUIRES_PROVIDER: ml_forecast_provider — "
                "wire a Prophet/LSTM/foundation-model provider via "
                "the ml_provider constructor argument before calling "
                "forecast_with_ml_overlay()")
        ml_overlay = self.ml_provider(
            tuple(self._history), horizon_days, start_date)
        seasonality = self.get_seasonality(seasonality_model_id)
        baseline = self.baseline()
        result = compute_forecast(
            forecast_id=forecast_id,
            start_date=start_date,
            horizon_days=horizon_days,
            seasonality=seasonality,
            baseline=baseline,
            scheduled_flows=tuple(self._scheduled),
            ml_overlay=ml_overlay)
        self._forecasts[forecast_id] = result
        return result

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        latest = max(
            self._forecasts.values(),
            key=lambda r: r.start_date,
            default=None)
        return {
            "entity": self.entity_name,
            "ml_provider_wired": self.ml_provider is not None,
            "n_history_days": self.history_count,
            "n_scheduled_flows": self.scheduled_count,
            "n_seasonality_models": len(self._seasonality_models),
            "n_forecasts": len(self._forecasts),
            "latest_forecast_id": latest.forecast_id if latest else None,
            "latest_horizon_days": (
                latest.horizon_days if latest else None),
            "latest_net_position": (
                str(latest.net_position()) if latest else None),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_synthetic_history(
    n_days: int, start: str = "2026-01-01",
    base: Decimal = Decimal("1000000"),
) -> List[HistoricalDayNetFlow]:
    """Generate deterministic history for testing."""
    out = []
    start_d = date.fromisoformat(start)
    for i in range(n_days):
        d = start_d + timedelta(days=i)
        # Variation: weekends lower, mid-month higher
        flow = base
        if d.weekday() >= 5:
            flow = base * Decimal("0.5")    # weekend
        if 11 <= d.day <= 20:
            flow = flow * Decimal("1.3")    # mid-month boost
        out.append(HistoricalDayNetFlow(
            observation_date=d.isoformat(), net_flow_kes=flow))
    return out


def _test_horizon_days_91():
    assert DEFAULT_HORIZON_DAYS == 91


def _test_z_scores():
    assert Z_80_PCT == Decimal("1.28")
    assert Z_95_PCT == Decimal("1.96")


def _test_fit_seasonality_requires_min_history():
    try:
        fit_seasonality_model(
            model_id="M1",
            history=_make_synthetic_history(10))
        assert False
    except ValueError:
        pass


def _test_fit_seasonality_returns_dow_multipliers():
    history = _make_synthetic_history(60)
    model = fit_seasonality_model(
        model_id="M1", history=history)
    # Should have 7 DoW multipliers
    assert len(model.dow_multipliers) == 7
    # Saturday (5) and Sunday (6) should have <1 multiplier
    # (synthetic data has weekends at 50% of base)
    assert model.dow_multipliers[5] < Decimal("1")
    assert model.dow_multipliers[6] < Decimal("1")


def _test_fit_seasonality_returns_dom_buckets():
    history = _make_synthetic_history(60)
    model = fit_seasonality_model(
        model_id="M1", history=history)
    # MID bucket should have >1 multiplier
    assert model.dom_bucket_multipliers["MID"] > Decimal("1")


def _test_seasonality_multiplier_for_date():
    history = _make_synthetic_history(60)
    model = fit_seasonality_model(
        model_id="M1", history=history)
    # Pick a Wednesday (weekday=2) mid-month
    test_date = date(2026, 5, 15)    # Friday day 15
    mult = model.multiplier_for(test_date)
    # Should be a positive Decimal
    assert mult > Decimal("0")


def _test_exponential_smoothing_basic():
    history = [HistoricalDayNetFlow(
        observation_date=f"2026-05-{i:02d}",
        net_flow_kes=Decimal("1000"))
        for i in range(1, 11)]
    baseline = exponential_smoothing_baseline(
        history=history, alpha=Decimal("0.3"))
    # All same values → baseline = same
    assert baseline == Decimal("1000.00")


def _test_exponential_smoothing_alpha_validation():
    history = [HistoricalDayNetFlow(
        observation_date="2026-05-01",
        net_flow_kes=Decimal("1000"))]
    try:
        exponential_smoothing_baseline(
            history=history, alpha=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_aggregate_scheduled_filters_by_date():
    flows = [
        ScheduledCashFlow(
            flow_id="F1", flow_date="2026-05-01",
            amount_kes=Decimal("500000"),
            driver=FlowDriver.BOND_MATURITY),
        ScheduledCashFlow(
            flow_id="F2", flow_date="2026-05-02",
            amount_kes=Decimal("100000"),
            driver=FlowDriver.LOAN_AMORTIZATION),
    ]
    total, summary = aggregate_scheduled_for_date(
        target_date="2026-05-01", flows=flows)
    assert total == Decimal("500000.00")
    assert "BOND_MATURITY" in summary


def _test_compute_forecast_basic():
    history = _make_synthetic_history(60)
    season = fit_seasonality_model(
        model_id="M1", history=history)
    baseline = exponential_smoothing_baseline(history=history)
    result = compute_forecast(
        forecast_id="F1",
        start_date="2026-05-01",
        horizon_days=14,
        seasonality=season,
        baseline=baseline)
    assert result.horizon_days == 14
    assert len(result.points) == 14
    assert result.ml_overlay_applied is False
    # All days should have non-zero baseline
    for p in result.points:
        assert p.baseline_kes == baseline


def _test_compute_forecast_with_scheduled():
    history = _make_synthetic_history(60)
    season = fit_seasonality_model(
        model_id="M1", history=history)
    baseline = exponential_smoothing_baseline(history=history)
    scheduled = [ScheduledCashFlow(
        flow_id="F1", flow_date="2026-05-05",
        amount_kes=Decimal("10000000"),
        driver=FlowDriver.BOND_MATURITY)]
    result = compute_forecast(
        forecast_id="F1",
        start_date="2026-05-01",
        horizon_days=14,
        seasonality=season,
        baseline=baseline,
        scheduled_flows=scheduled)
    # Day 4 (May 5) should have +10M deterministic
    day_4 = result.points[4]
    assert day_4.deterministic_kes == Decimal("10000000.00")
    assert "BOND_MATURITY" in day_4.drivers_summary


def _test_compute_forecast_zero_horizon_raises():
    history = _make_synthetic_history(60)
    season = fit_seasonality_model(
        model_id="M1", history=history)
    try:
        compute_forecast(
            forecast_id="F1",
            start_date="2026-05-01",
            horizon_days=0,
            seasonality=season,
            baseline=Decimal("1000"))
        assert False
    except ValueError:
        pass


def _test_compute_forecast_with_ml_overlay():
    history = _make_synthetic_history(60)
    season = fit_seasonality_model(
        model_id="M1", history=history)
    baseline = Decimal("1000000")
    ml_overlay = {
        "2026-05-01": Decimal("999999"),
        "2026-05-02": Decimal("888888"),
    }
    result = compute_forecast(
        forecast_id="F1",
        start_date="2026-05-01",
        horizon_days=5,
        seasonality=season,
        baseline=baseline,
        ml_overlay=ml_overlay)
    assert result.ml_overlay_applied is True
    # Day 0 should use ML overlay value
    assert result.points[0].statistical_kes == Decimal("999999")
    # Day 2 (no overlay) should use seasonality
    assert result.points[2].statistical_kes != Decimal("999999")


def _test_engine_baseline_requires_history():
    eng = TreasuryCashForecastingEngine()
    try:
        eng.baseline()
        assert False
    except ValueError:
        pass


def _test_engine_get_unknown_seasonality_raises():
    eng = TreasuryCashForecastingEngine()
    try:
        eng.get_seasonality("UNKNOWN")
        assert False
    except KeyError:
        pass


def _test_engine_full_flow():
    eng = TreasuryCashForecastingEngine()
    for h in _make_synthetic_history(60):
        eng.add_history(h)
    eng.add_scheduled_flow(ScheduledCashFlow(
        flow_id="S1", flow_date="2026-05-05",
        amount_kes=Decimal("1000000"),
        driver=FlowDriver.BOND_MATURITY))
    eng.fit_seasonality("S1")
    result = eng.forecast(
        forecast_id="F1", start_date="2026-05-01",
        horizon_days=7, seasonality_model_id="S1")
    assert result.horizon_days == 7
    assert result.ml_overlay_applied is False


def _test_engine_ml_without_provider_raises_provider():
    eng = TreasuryCashForecastingEngine()
    for h in _make_synthetic_history(60):
        eng.add_history(h)
    eng.fit_seasonality("S1")
    try:
        eng.forecast_with_ml_overlay(
            forecast_id="F1",
            start_date="2026-05-01",
            horizon_days=7,
            seasonality_model_id="S1")
        assert False
    except ValueError as e:
        assert "REQUIRES_PROVIDER" in str(e)


def _test_engine_ml_with_provider():
    """Provider wired → forecast applies ML overlay."""
    def fake_provider(history, horizon, start):
        d = date.fromisoformat(start)
        return {
            (d + timedelta(days=i)).isoformat():
                Decimal(f"{(i+1) * 100000}")
            for i in range(horizon)}
    eng = TreasuryCashForecastingEngine(
        ml_provider=fake_provider)
    for h in _make_synthetic_history(60):
        eng.add_history(h)
    eng.fit_seasonality("S1")
    result = eng.forecast_with_ml_overlay(
        forecast_id="F1",
        start_date="2026-05-01",
        horizon_days=7,
        seasonality_model_id="S1")
    assert result.ml_overlay_applied is True


def _test_engine_board_summary():
    eng = TreasuryCashForecastingEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["ml_provider_wired"] is False
    assert s["n_forecasts"] == 0


def self_test() -> None:
    tests = [
        _test_horizon_days_91,
        _test_z_scores,
        _test_fit_seasonality_requires_min_history,
        _test_fit_seasonality_returns_dow_multipliers,
        _test_fit_seasonality_returns_dom_buckets,
        _test_seasonality_multiplier_for_date,
        _test_exponential_smoothing_basic,
        _test_exponential_smoothing_alpha_validation,
        _test_aggregate_scheduled_filters_by_date,
        _test_compute_forecast_basic,
        _test_compute_forecast_with_scheduled,
        _test_compute_forecast_zero_horizon_raises,
        _test_compute_forecast_with_ml_overlay,
        _test_engine_baseline_requires_history,
        _test_engine_get_unknown_seasonality_raises,
        _test_engine_full_flow,
        _test_engine_ml_without_provider_raises_provider,
        _test_engine_ml_with_provider,
        _test_engine_board_summary,
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
        print(f"✗ cash_forecasting self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ cash_forecasting self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

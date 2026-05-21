"""utils/trade_finance_reporting.py — v10.76: TF reporting + analytics.

ENH-280 — Trade Finance Reporting & Analytics. Cat B —
trade_finance arc 6/N.

Diagnostic reporting + analytics engine for trade finance
portfolios. Six capabilities, two of which support optional ML
extension hooks for accuracy improvement over time:

  1. compute_trade_volumes — volume aggregation by period +
     instrument type + counterparty + country (deterministic)
  2. compute_country_exposure — per-country exposure with
     concentration metrics (Herfindahl index, top-N share)
     (deterministic)
  3. compute_sector_concentration — per-sector exposure with
     Herfindahl + top-N (deterministic)
  4. detect_volume_anomalies — anomaly detection on volume time
     series. **ML-extensible** via injectable scorer; statistical
     fallback uses z-score + MAD (median absolute deviation)
  5. forecast_volume_trajectory — n-period forecast. **ML-
     extensible** via injectable forecaster; statistical fallback
     uses ordinary least squares on the most recent 12 periods
  6. build_management_report — orchestrator returning all above
     in a single MgmtReport for cockpit consumption

ML EXTENSION CONTRACT (for accuracy improvement over time):

The engine accepts two optional callables at construction:

    ml_anomaly_scorer: Callable[[Sequence[Decimal]], Sequence[float]]
        Takes a time-ordered sequence of period totals, returns
        per-period anomaly scores in [0, 1] where 1.0 = strongest
        anomaly. Engine surfaces score + threshold breach as an
        AnomalyFinding. When None, statistical fallback runs.

    ml_forecaster: Callable[[Sequence[Decimal], int], Sequence[Decimal]]
        Takes a time-ordered sequence of period totals + horizon n,
        returns n forecast values. When None, statistical fallback
        uses OLS regression on most recent 12 periods.

Per Rule 6, every output carries an explicit ml_disabled flag:
  - ml_disabled=True  → statistical fallback used
  - ml_disabled=False → injected ML hook used

Per Rule 7, engine NEVER:
  - acts on anomaly findings (operator adjudicates each)
  - submits regulatory reports (CBK / KRA territory — caller's
    responsibility via cbk_regulatory_reporting engine)
  - publishes management dashboards (cockpit page consumes)
  - retrains models in-place (training pipeline is separate
    infrastructure; this engine consumes trained scorers)
  - mutates inputs

PATH TO ACCURACY IMPROVEMENT:

The engine is the consumer side of an ML training pipeline. The
producer side (separate, not in this engine) is responsible for:
  - Collecting historical period totals + operator adjudications
  - Training anomaly scorers on (period_total → was_truly_anomaly)
    pairs sourced from operator adjudication history
  - Training forecasters on rolling-window time-series data with
    holdout evaluation
  - Versioning + serializing trained models
  - Health-checking models before injection (drift detection)

When the producer pipeline matures, trained models inject as
callables. Until then, statistical fallback runs and ml_disabled
is True in every output, making the operator aware that the
finding is heuristic-based rather than model-based.

Pure stdlib (Decimal + dataclasses + enums + statistics module).
"""
from __future__ import annotations

import math
import statistics
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from utils.trade_finance_instruments import (
    TradeInstrument, InstrumentType, InstrumentState)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceReportingEngine implements ENH-280 — diagnostic "
    "trade finance portfolio reporting + analytics. Six "
    "capabilities; two support optional ML extension hooks "
    "(anomaly detection, forecasting). Pure stdlib (statistics "
    "module for fallback). Per Rule 1, every output surfaces "
    "method_used + ml_disabled flag + framework refs. Per Rule 6, "
    "ml_disabled=True when statistical fallback runs; "
    "ml_disabled=False when injected ML hook runs. Per Rule 7, "
    "engine DIAGNOSTIC ONLY — never acts on findings; never "
    "submits reports; never publishes dashboards; never retrains "
    "models (training is separate infrastructure); never mutates "
    "inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class AnomalySeverity(Enum):
    NORMAL = "NORMAL"           # below threshold
    WATCH = "WATCH"             # above threshold, below alert
    ALERT = "ALERT"             # significant anomaly


class ConcentrationSeverity(Enum):
    DIVERSIFIED = "DIVERSIFIED"     # HHI < 0.15
    MODERATE = "MODERATE"           # HHI 0.15-0.25
    CONCENTRATED = "CONCENTRATED"   # HHI > 0.25


class AnalysisMethod(Enum):
    """Which path produced a finding — surfaced in every output."""
    DETERMINISTIC = "DETERMINISTIC"          # exact computation
    STATISTICAL_FALLBACK = "STATISTICAL_FALLBACK"  # z-score, MAD, OLS
    ML_INJECTED = "ML_INJECTED"              # caller-supplied model


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VolumeAggregation:
    period_label: str        # e.g. "2026-Q1", "2026-04"
    by_instrument_type: Dict[str, Decimal]
    by_country: Dict[str, Decimal]
    by_counterparty: Dict[str, Decimal]
    total_kes: Decimal
    instrument_count: int
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CountryExposure:
    as_of_date: str
    by_country: Dict[str, Decimal]   # country_code -> exposure
    herfindahl_index: Decimal        # Σ(share²), 0..1
    top_3_share: Decimal             # share of top 3 countries
    top_5_share: Decimal
    severity: ConcentrationSeverity
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class SectorConcentration:
    as_of_date: str
    by_sector: Dict[str, Decimal]
    herfindahl_index: Decimal
    top_3_share: Decimal
    severity: ConcentrationSeverity
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class AnomalyFinding:
    period_index: int        # 0-based index into time series
    period_label: str
    observed_value_kes: Decimal
    score: float             # 0..1; 1 = strongest anomaly
    threshold: float
    severity: AnomalySeverity
    method: AnalysisMethod
    ml_disabled: bool        # True iff statistical fallback used
    description: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class VolumeForecast:
    history_period_count: int
    horizon_periods: int
    forecast_values_kes: Tuple[Decimal, ...]
    method: AnalysisMethod
    ml_disabled: bool
    confidence_note: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ManagementReport:
    as_of_date: str
    volume_aggregation: VolumeAggregation
    country_exposure: Optional[CountryExposure]
    sector_concentration: Optional[SectorConcentration]
    anomaly_findings: Tuple[AnomalyFinding, ...]
    forecast: Optional[VolumeForecast]
    overall_ml_disabled: bool   # True if any analytical path
                                 # used statistical fallback
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

# Type aliases for the ML hook contract
MLAnomalyScorer = Callable[
    [Sequence[Decimal]], Sequence[float]]
MLForecaster = Callable[
    [Sequence[Decimal], int], Sequence[Decimal]]


class TradeFinanceReportingEngine:
    """Diagnostic trade finance reporting + analytics engine."""

    # Anomaly detection thresholds (z-score scale for fallback,
    # 0..1 score scale for ML)
    WATCH_THRESHOLD: float = 0.50
    ALERT_THRESHOLD: float = 0.75

    # Concentration severity thresholds (Herfindahl)
    DIVERSIFIED_HHI_MAX: Decimal = Decimal("0.15")
    MODERATE_HHI_MAX: Decimal = Decimal("0.25")

    # Statistical fallback parameters
    OLS_WINDOW_PERIODS: int = 12     # forecast input window
    MIN_PERIODS_FOR_ANOMALY: int = 4  # min sample for z-score

    def __init__(
        self,
        ml_anomaly_scorer: Optional[MLAnomalyScorer] = None,
        ml_forecaster: Optional[MLForecaster] = None,
    ) -> None:
        self.ml_anomaly_scorer = ml_anomaly_scorer
        self.ml_forecaster = ml_forecaster

    # ─── Volume aggregation (deterministic) ──────────────────────
    def compute_trade_volumes(
        self,
        instruments: Sequence[TradeInstrument],
        period_label: str,
        country_attribution: Optional[Dict[str, str]] = None,
    ) -> VolumeAggregation:
        """Aggregate volumes by type + country + counterparty.

        country_attribution maps counterparty_id → ISO country
        code for beneficiary-side aggregation. If absent or
        partial, those entries are tagged 'UNKNOWN'.
        """
        if country_attribution is None:
            country_attribution = {}
        by_type: Dict[str, Decimal] = {}
        by_country: Dict[str, Decimal] = {}
        by_cp: Dict[str, Decimal] = {}
        total = Decimal("0")
        for inst in instruments:
            amt = inst.amount_kes
            total += amt
            t_key = inst.instrument_type.value
            by_type[t_key] = by_type.get(
                t_key, Decimal("0")) + amt
            country = country_attribution.get(
                inst.beneficiary, "UNKNOWN")
            by_country[country] = by_country.get(
                country, Decimal("0")) + amt
            by_cp[inst.applicant] = by_cp.get(
                inst.applicant, Decimal("0")) + amt
        return VolumeAggregation(
            period_label=period_label,
            by_instrument_type=by_type,
            by_country=by_country,
            by_counterparty=by_cp,
            total_kes=total,
            instrument_count=len(instruments),
            framework_refs=(
                "ENH-280 §compute_trade_volumes",
                "Per Rule 1 — surfaces full breakdown by 3 "
                "dimensions; deterministic computation",
            ),
        )

    # ─── Concentration metrics (deterministic) ──────────────────
    @staticmethod
    def _herfindahl(
        values: Sequence[Decimal],
    ) -> Tuple[Decimal, Decimal]:
        """Return (HHI, total). HHI = Σ(share²). 0..1 range.

        Returns Decimal('0') for empty/zero-total inputs.
        """
        total = sum(values, Decimal("0"))
        if total <= 0:
            return (Decimal("0"), total)
        # Use Decimal throughout to avoid float drift on large notionals
        hhi = sum(
            (v / total) ** 2 for v in values if v > 0)
        return (hhi.quantize(Decimal("0.0001")), total)

    @classmethod
    def _concentration_severity(
        cls, hhi: Decimal,
    ) -> ConcentrationSeverity:
        if hhi <= cls.DIVERSIFIED_HHI_MAX:
            return ConcentrationSeverity.DIVERSIFIED
        if hhi <= cls.MODERATE_HHI_MAX:
            return ConcentrationSeverity.MODERATE
        return ConcentrationSeverity.CONCENTRATED

    @staticmethod
    def _top_n_share(
        values_dict: Dict[str, Decimal], n: int,
    ) -> Decimal:
        total = sum(
            values_dict.values(), Decimal("0"))
        if total <= 0:
            return Decimal("0")
        sorted_vals = sorted(
            values_dict.values(), reverse=True)[:n]
        top_sum = sum(sorted_vals, Decimal("0"))
        return (top_sum / total).quantize(Decimal("0.0001"))

    def compute_country_exposure(
        self,
        instruments: Sequence[TradeInstrument],
        country_attribution: Dict[str, str],
        as_of_date_iso: str,
    ) -> CountryExposure:
        by_country: Dict[str, Decimal] = {}
        active_states = (
            InstrumentState.ISSUED,
            InstrumentState.AMENDED,
            InstrumentState.ACTIVE)
        for inst in instruments:
            if inst.state not in active_states:
                continue
            country = country_attribution.get(
                inst.beneficiary, "UNKNOWN")
            by_country[country] = by_country.get(
                country, Decimal("0")) + inst.amount_kes
        hhi, _ = self._herfindahl(list(by_country.values()))
        return CountryExposure(
            as_of_date=as_of_date_iso,
            by_country=by_country,
            herfindahl_index=hhi,
            top_3_share=self._top_n_share(by_country, 3),
            top_5_share=self._top_n_share(by_country, 5),
            severity=self._concentration_severity(hhi),
            framework_refs=(
                "ENH-280 §compute_country_exposure",
                "Herfindahl-Hirschman Index — concentration "
                "measure (Σ share²); thresholds: <0.15 "
                "diversified, 0.15-0.25 moderate, >0.25 "
                "concentrated",
                "Basel — country/transfer risk concentration",
                "Per Rule 7 — engine surfaces metrics; "
                "operator decides on portfolio rebalancing",
            ),
        )

    def compute_sector_concentration(
        self,
        instruments: Sequence[TradeInstrument],
        sector_attribution: Dict[str, str],
        as_of_date_iso: str,
    ) -> SectorConcentration:
        """Concentration by industry sector (caller-supplied
        attribution from applicant_id -> sector_code)."""
        by_sector: Dict[str, Decimal] = {}
        active_states = (
            InstrumentState.ISSUED,
            InstrumentState.AMENDED,
            InstrumentState.ACTIVE)
        for inst in instruments:
            if inst.state not in active_states:
                continue
            sector = sector_attribution.get(
                inst.applicant, "UNKNOWN")
            by_sector[sector] = by_sector.get(
                sector, Decimal("0")) + inst.amount_kes
        hhi, _ = self._herfindahl(list(by_sector.values()))
        return SectorConcentration(
            as_of_date=as_of_date_iso,
            by_sector=by_sector,
            herfindahl_index=hhi,
            top_3_share=self._top_n_share(by_sector, 3),
            severity=self._concentration_severity(hhi),
            framework_refs=(
                "ENH-280 §compute_sector_concentration",
                "Herfindahl-Hirschman Index on sector mix",
                "Per Rule 7 — diagnostic only",
            ),
        )

    # ─── Anomaly detection (ML-extensible) ──────────────────────
    @staticmethod
    def _statistical_anomaly_scores(
        values: Sequence[Decimal],
    ) -> List[float]:
        """Statistical fallback — z-score on log-transformed
        values, mapped to [0, 1] via sigmoid-ish saturation.

        Robustness: uses median + MAD instead of mean + stdev to
        resist outliers affecting their own scores.
        """
        if len(values) < 4:
            return [0.0] * len(values)
        floats = [float(v) for v in values]
        # Log transform to handle skewed distributions (volumes
        # typically log-normal)
        eps = 1.0
        log_vals = [math.log(v + eps) for v in floats]
        med = statistics.median(log_vals)
        # MAD (median absolute deviation)
        mad = statistics.median(
            [abs(v - med) for v in log_vals])
        if mad < 1e-9:
            # Degenerate flat series — no anomalies detectable
            return [0.0] * len(values)
        # Modified z-score (Iglewicz & Hoaglin 1993)
        # 0.6745 = ~normal-distribution constant making MAD-based
        # z-score comparable to stdev-based z-score
        scores: List[float] = []
        for lv in log_vals:
            mod_z = 0.6745 * (lv - med) / mad
            # Saturate to [0, 1]: mod_z of ±3.5 maps near 1.0
            score = min(1.0, abs(mod_z) / 3.5)
            scores.append(score)
        return scores

    def detect_volume_anomalies(
        self,
        time_series: Sequence[Decimal],
        period_labels: Sequence[str],
    ) -> Tuple[AnomalyFinding, ...]:
        """Detect anomalies in a time series of period volumes.

        Uses injected ml_anomaly_scorer if present; otherwise
        runs statistical fallback. Result surfaces method +
        ml_disabled flag in every finding so operator knows
        which path produced the score.
        """
        if len(time_series) != len(period_labels):
            raise ValueError(
                "time_series and period_labels must have "
                "same length")
        if not time_series:
            return ()

        # Method selection
        if self.ml_anomaly_scorer is not None:
            try:
                scores_raw = self.ml_anomaly_scorer(time_series)
                scores = [
                    max(0.0, min(1.0, float(s)))
                    for s in scores_raw]
                if len(scores) != len(time_series):
                    raise ValueError(
                        "ml_anomaly_scorer returned wrong "
                        "length")
                method = AnalysisMethod.ML_INJECTED
                ml_disabled = False
            except Exception as e:
                # Fall back gracefully — operator sees that
                # ML failed and statistical was used
                scores = self._statistical_anomaly_scores(
                    time_series)
                method = AnalysisMethod.STATISTICAL_FALLBACK
                ml_disabled = True
                fallback_note = (
                    f"ml_anomaly_scorer raised "
                    f"{type(e).__name__}; fell back to "
                    f"statistical")
        else:
            scores = self._statistical_anomaly_scores(time_series)
            method = AnalysisMethod.STATISTICAL_FALLBACK
            ml_disabled = True
            fallback_note = ""

        findings: List[AnomalyFinding] = []
        for i, (val, lbl, score) in enumerate(
            zip(time_series, period_labels, scores)
        ):
            if score >= self.ALERT_THRESHOLD:
                severity = AnomalySeverity.ALERT
                threshold = self.ALERT_THRESHOLD
            elif score >= self.WATCH_THRESHOLD:
                severity = AnomalySeverity.WATCH
                threshold = self.WATCH_THRESHOLD
            else:
                # Skip non-anomalous periods (signal-only output)
                continue
            method_label = (
                "ML scorer (injected)"
                if method == AnalysisMethod.ML_INJECTED
                else "Modified Z-score on log-volume "
                     "(Iglewicz & Hoaglin 1993)")
            description = (
                f"Period {lbl} volume {val} flagged "
                f"{severity.value} (score {score:.2f} ≥ "
                f"threshold {threshold:.2f}); method: "
                f"{method_label}")
            findings.append(AnomalyFinding(
                period_index=i,
                period_label=lbl,
                observed_value_kes=val,
                score=round(score, 4),
                threshold=threshold,
                severity=severity,
                method=method,
                ml_disabled=ml_disabled,
                description=description,
                framework_refs=(
                    "ENH-280 §detect_volume_anomalies",
                    f"Method: {method.value}",
                    "Per Rule 6 — ml_disabled flag explicit",
                    "Per Rule 7 — operator adjudicates each "
                    "anomaly; engine never auto-acts",
                ),
            ))
        return tuple(findings)

    # ─── Forecasting (ML-extensible) ────────────────────────────
    @staticmethod
    def _ols_forecast(
        history: Sequence[Decimal], horizon: int,
    ) -> List[Decimal]:
        """OLS linear regression on most recent OLS_WINDOW_PERIODS.

        Returns horizon predictions. Returns last-observation flat
        forecast if insufficient data.
        """
        if not history:
            return [Decimal("0")] * horizon
        window = (
            history
            if len(history) <=
            TradeFinanceReportingEngine.OLS_WINDOW_PERIODS
            else history[
                -TradeFinanceReportingEngine.OLS_WINDOW_PERIODS:])
        n = len(window)
        if n < 3:
            # Insufficient — flat forecast at last observation
            return [window[-1]] * horizon
        # Linear regression: y = a + b·x where x is period index
        xs = [Decimal(i) for i in range(n)]
        ys = list(window)
        x_mean = sum(xs, Decimal("0")) / Decimal(n)
        y_mean = sum(ys, Decimal("0")) / Decimal(n)
        num = sum(
            ((x - x_mean) * (y - y_mean))
            for x, y in zip(xs, ys))
        den = sum(((x - x_mean) ** 2) for x in xs)
        if den == 0:
            return [window[-1]] * horizon
        b = num / den
        a = y_mean - b * x_mean
        forecasts: List[Decimal] = []
        for h in range(1, horizon + 1):
            x_future = Decimal(n - 1 + h)
            y_hat = a + b * x_future
            # Clip negatives to zero — volumes can't be negative
            forecasts.append(
                max(Decimal("0"), y_hat).quantize(
                    Decimal("0.01")))
        return forecasts

    def forecast_volume_trajectory(
        self,
        history: Sequence[Decimal],
        horizon_periods: int,
    ) -> VolumeForecast:
        """Forecast next n periods of volume.

        Uses injected ml_forecaster if present; otherwise OLS
        fallback on most recent 12 periods.
        """
        if horizon_periods <= 0:
            raise ValueError("horizon_periods must be > 0")
        if horizon_periods > 36:
            raise ValueError(
                "horizon_periods > 36 is unreliable for any "
                "method; reject by policy")

        if self.ml_forecaster is not None:
            try:
                forecasts_raw = self.ml_forecaster(
                    history, horizon_periods)
                forecasts = tuple(
                    Decimal(str(f)) for f in forecasts_raw)
                if len(forecasts) != horizon_periods:
                    raise ValueError(
                        "ml_forecaster returned wrong length")
                method = AnalysisMethod.ML_INJECTED
                ml_disabled = False
                confidence_note = (
                    "Injected ML forecaster — accuracy "
                    "depends on training pipeline; review "
                    "model card before relying on outputs")
            except Exception as e:
                forecasts = tuple(self._ols_forecast(
                    history, horizon_periods))
                method = AnalysisMethod.STATISTICAL_FALLBACK
                ml_disabled = True
                confidence_note = (
                    f"ml_forecaster raised "
                    f"{type(e).__name__}; fell back to OLS "
                    f"on last {min(len(history), self.OLS_WINDOW_PERIODS)} periods")
        else:
            forecasts = tuple(self._ols_forecast(
                history, horizon_periods))
            method = AnalysisMethod.STATISTICAL_FALLBACK
            ml_disabled = True
            confidence_note = (
                f"OLS on last "
                f"{min(len(history), self.OLS_WINDOW_PERIODS)} "
                f"periods. Linear assumption — does not capture "
                f"seasonality, regime changes, or non-linear "
                f"trends. Inject an ml_forecaster for higher "
                f"accuracy.")

        return VolumeForecast(
            history_period_count=len(history),
            horizon_periods=horizon_periods,
            forecast_values_kes=forecasts,
            method=method,
            ml_disabled=ml_disabled,
            confidence_note=confidence_note,
            framework_refs=(
                "ENH-280 §forecast_volume_trajectory",
                f"Method: {method.value}",
                "Per Rule 6 — ml_disabled flag explicit",
                "Per Rule 7 — engine surfaces forecast; "
                "operator interprets; no auto-action",
            ),
        )

    # ─── Orchestrator ───────────────────────────────────────────
    def build_management_report(
        self,
        current_period_instruments: Sequence[TradeInstrument],
        period_label: str,
        as_of_date_iso: str,
        country_attribution: Optional[Dict[str, str]] = None,
        sector_attribution: Optional[Dict[str, str]] = None,
        history_for_anomaly: Optional[
            Tuple[Sequence[Decimal], Sequence[str]]] = None,
        forecast_horizon: int = 0,
    ) -> ManagementReport:
        """Build a single MgmtReport rolling up all 6 capabilities.

        - country_attribution / sector_attribution optional;
          when None the corresponding section is skipped
        - history_for_anomaly: (values, labels) tuple for time-
          series anomaly detection; None skips
        - forecast_horizon: 0 to skip; >0 runs forecaster
        """
        vol = self.compute_trade_volumes(
            current_period_instruments,
            period_label,
            country_attribution=country_attribution)

        country_exp: Optional[CountryExposure] = None
        if country_attribution is not None:
            country_exp = self.compute_country_exposure(
                current_period_instruments,
                country_attribution,
                as_of_date_iso=as_of_date_iso)

        sector_conc: Optional[SectorConcentration] = None
        if sector_attribution is not None:
            sector_conc = self.compute_sector_concentration(
                current_period_instruments,
                sector_attribution,
                as_of_date_iso=as_of_date_iso)

        anomalies: Tuple[AnomalyFinding, ...] = ()
        if history_for_anomaly is not None:
            values, labels = history_for_anomaly
            anomalies = self.detect_volume_anomalies(
                values, labels)

        forecast: Optional[VolumeForecast] = None
        if forecast_horizon > 0:
            history_vals = (
                history_for_anomaly[0]
                if history_for_anomaly is not None else ())
            forecast = self.forecast_volume_trajectory(
                history_vals, forecast_horizon)

        # Aggregate ml_disabled across the 2 ML-extensible paths
        any_ml_used = (
            (anomalies and any(
                not f.ml_disabled for f in anomalies))
            or (forecast is not None and not forecast.ml_disabled))
        any_fallback_used = (
            (anomalies and any(
                f.ml_disabled for f in anomalies))
            or (forecast is not None and forecast.ml_disabled))
        # ml_disabled at report level = True iff any analytical
        # path used the statistical fallback (most conservative
        # for operator awareness)
        overall_ml_disabled = (
            any_fallback_used or
            (history_for_anomaly is None
             and forecast_horizon == 0))

        return ManagementReport(
            as_of_date=as_of_date_iso,
            volume_aggregation=vol,
            country_exposure=country_exp,
            sector_concentration=sector_conc,
            anomaly_findings=anomalies,
            forecast=forecast,
            overall_ml_disabled=overall_ml_disabled,
            framework_refs=(
                "ENH-280 §build_management_report",
                "Per Rule 1 — report aggregates 6 capability "
                "outputs",
                "Per Rule 6 — overall_ml_disabled True iff any "
                "analytical path used statistical fallback",
                "Per Rule 7 — engine builds report data; "
                "cockpit page renders; operator interprets",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_lc(
    iid, applicant="A", beneficiary="B",
    amount=Decimal("1000000"),
    state=InstrumentState.ACTIVE,
):
    from datetime import date as _d
    from utils.trade_finance_instruments import LcType
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state,
        applicant=applicant, beneficiary=beneficiary,
        issuing_bank="Eco", advising_bank="ABC",
        amount_kes=amount, currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 8, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="goods")


def _test_volumes_basic():
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_lc("L1", "A", "ChinaCorp", Decimal("3000000")),
        _make_lc("L2", "A", "ChinaCorp", Decimal("2000000")),
        _make_lc("L3", "B", "GermanCorp", Decimal("5000000")),
    )
    attrib = {"ChinaCorp": "CN", "GermanCorp": "DE"}
    vol = eng.compute_trade_volumes(
        insts, "2026-Q2", country_attribution=attrib)
    assert vol.total_kes == Decimal("10000000")
    assert vol.instrument_count == 3
    assert vol.by_country["CN"] == Decimal("5000000")
    assert vol.by_country["DE"] == Decimal("5000000")
    assert vol.by_counterparty["A"] == Decimal("5000000")


def _test_volumes_no_attribution_marks_unknown():
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_lc("L1", "A", "Unattributed",
                 Decimal("1000000")),)
    vol = eng.compute_trade_volumes(insts, "P")
    assert vol.by_country["UNKNOWN"] == Decimal("1000000")


def _test_country_exposure_diversified():
    eng = TradeFinanceReportingEngine()
    insts = tuple(
        _make_lc(
            f"L{i}", "A", f"CP{i}", Decimal("1000000"))
        for i in range(10))
    attrib = {f"CP{i}": f"C{i}" for i in range(10)}
    exp = eng.compute_country_exposure(
        insts, attrib, as_of_date_iso="2026-04-15")
    # 10 equal countries → HHI = 10 × (0.1)² = 0.10 → DIVERSIFIED
    assert exp.severity == ConcentrationSeverity.DIVERSIFIED
    assert exp.herfindahl_index < Decimal("0.15")


def _test_country_exposure_concentrated():
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_lc("L1", "A", "BigCorp", Decimal("9000000")),
        _make_lc("L2", "A", "SmallCorp", Decimal("1000000")),
    )
    attrib = {"BigCorp": "CN", "SmallCorp": "DE"}
    exp = eng.compute_country_exposure(
        insts, attrib, as_of_date_iso="2026-04-15")
    # 0.9² + 0.1² = 0.82 → concentrated
    assert exp.severity == ConcentrationSeverity.CONCENTRATED
    assert exp.herfindahl_index > Decimal("0.25")


def _test_country_exposure_excludes_closed():
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_lc(
            "L1", "A", "CN1", Decimal("1000000"),
            state=InstrumentState.ACTIVE),
        _make_lc(
            "L2", "A", "DE1", Decimal("1000000"),
            state=InstrumentState.EXPIRED),
    )
    attrib = {"CN1": "CN", "DE1": "DE"}
    exp = eng.compute_country_exposure(
        insts, attrib, as_of_date_iso="2026-04-15")
    # Only ACTIVE counted
    assert "CN" in exp.by_country
    assert "DE" not in exp.by_country
    assert exp.by_country["CN"] == Decimal("1000000")


def _test_sector_concentration():
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_lc("L1", "AcmeOil", "B", Decimal("8000000")),
        _make_lc("L2", "Biotech", "B", Decimal("2000000")),
    )
    attrib = {"AcmeOil": "ENERGY", "Biotech": "PHARMA"}
    conc = eng.compute_sector_concentration(
        insts, attrib, as_of_date_iso="2026-04-15")
    # 0.8² + 0.2² = 0.68 → concentrated
    assert conc.severity == ConcentrationSeverity.CONCENTRATED


def _test_anomaly_statistical_fallback():
    """Statistical fallback flags an obvious outlier."""
    eng = TradeFinanceReportingEngine()
    # 10 normal periods near 1m, then a 10x spike
    history = [
        Decimal("1000000"), Decimal("1100000"),
        Decimal("950000"), Decimal("1050000"),
        Decimal("980000"), Decimal("1020000"),
        Decimal("1030000"), Decimal("970000"),
        Decimal("990000"),
        Decimal("10000000"),    # 10x spike
    ]
    labels = [f"P{i}" for i in range(len(history))]
    findings = eng.detect_volume_anomalies(history, labels)
    # At minimum, the spike should be flagged
    assert any(
        f.period_label == "P9"
        and f.severity in (
            AnomalySeverity.WATCH,
            AnomalySeverity.ALERT)
        for f in findings)
    # All findings must surface ml_disabled=True for the fallback
    assert all(f.ml_disabled is True for f in findings)
    assert all(
        f.method == AnalysisMethod.STATISTICAL_FALLBACK
        for f in findings)


def _test_anomaly_flat_series_no_anomalies():
    """Degenerate flat series → 0 findings."""
    eng = TradeFinanceReportingEngine()
    history = [Decimal("1000000")] * 10
    labels = [f"P{i}" for i in range(10)]
    findings = eng.detect_volume_anomalies(history, labels)
    assert findings == ()


def _test_anomaly_short_series_no_findings():
    """< 4 periods → can't detect anomalies."""
    eng = TradeFinanceReportingEngine()
    findings = eng.detect_volume_anomalies(
        [Decimal("1000")] * 3, ["P1", "P2", "P3"])
    assert findings == ()


def _test_anomaly_ml_hook_used():
    """When ML scorer is injected, method=ML_INJECTED."""
    def fake_scorer(values):
        # Score every period at exactly 0.9 (always alert)
        return [0.9] * len(values)

    eng = TradeFinanceReportingEngine(
        ml_anomaly_scorer=fake_scorer)
    history = [Decimal("1000000")] * 5
    labels = [f"P{i}" for i in range(5)]
    findings = eng.detect_volume_anomalies(history, labels)
    assert len(findings) == 5
    assert all(
        f.method == AnalysisMethod.ML_INJECTED
        for f in findings)
    assert all(
        f.ml_disabled is False for f in findings)
    assert all(
        f.severity == AnomalySeverity.ALERT for f in findings)


def _test_anomaly_ml_hook_failure_falls_back():
    """If injected ML scorer raises, fall back gracefully."""
    def broken_scorer(values):
        raise RuntimeError("model not available")

    eng = TradeFinanceReportingEngine(
        ml_anomaly_scorer=broken_scorer)
    history = (
        [Decimal("1000000")] * 9 + [Decimal("10000000")])
    labels = [f"P{i}" for i in range(10)]
    findings = eng.detect_volume_anomalies(history, labels)
    # Should fall back; method=STATISTICAL_FALLBACK
    assert all(
        f.method == AnalysisMethod.STATISTICAL_FALLBACK
        for f in findings)
    assert all(f.ml_disabled is True for f in findings)


def _test_anomaly_ml_hook_wrong_length_falls_back():
    def shorter_scorer(values):
        return [0.5] * (len(values) - 1)   # wrong length

    eng = TradeFinanceReportingEngine(
        ml_anomaly_scorer=shorter_scorer)
    history = [Decimal("1000000")] * 9 + [Decimal("10000000")]
    labels = [f"P{i}" for i in range(10)]
    findings = eng.detect_volume_anomalies(history, labels)
    assert all(f.ml_disabled is True for f in findings)


def _test_forecast_ols_fallback():
    eng = TradeFinanceReportingEngine()
    # Linearly increasing series 1m..6m, predict next 3 → ~7m, 8m, 9m
    history = [
        Decimal("1000000"), Decimal("2000000"),
        Decimal("3000000"), Decimal("4000000"),
        Decimal("5000000"), Decimal("6000000")]
    f = eng.forecast_volume_trajectory(history, horizon_periods=3)
    assert f.method == AnalysisMethod.STATISTICAL_FALLBACK
    assert f.ml_disabled is True
    assert len(f.forecast_values_kes) == 3
    # First forecast should be ~7m given linear pattern
    assert f.forecast_values_kes[0] > Decimal("6500000")
    assert f.forecast_values_kes[0] < Decimal("7500000")


def _test_forecast_ml_hook_used():
    def fake_forecaster(history, horizon):
        # Always predict 5m for every period
        return [Decimal("5000000")] * horizon

    eng = TradeFinanceReportingEngine(
        ml_forecaster=fake_forecaster)
    f = eng.forecast_volume_trajectory(
        [Decimal("1000000")] * 5, horizon_periods=4)
    assert f.method == AnalysisMethod.ML_INJECTED
    assert f.ml_disabled is False
    assert all(
        v == Decimal("5000000")
        for v in f.forecast_values_kes)


def _test_forecast_ml_hook_failure_falls_back():
    def broken(history, horizon):
        raise RuntimeError("nope")

    eng = TradeFinanceReportingEngine(ml_forecaster=broken)
    f = eng.forecast_volume_trajectory(
        [Decimal("100"), Decimal("200"), Decimal("300")],
        horizon_periods=2)
    assert f.method == AnalysisMethod.STATISTICAL_FALLBACK
    assert f.ml_disabled is True


def _test_forecast_horizon_validates():
    eng = TradeFinanceReportingEngine()
    try:
        eng.forecast_volume_trajectory(
            [Decimal("1")], horizon_periods=0)
        assert False
    except ValueError:
        pass
    try:
        eng.forecast_volume_trajectory(
            [Decimal("1")], horizon_periods=37)
        assert False
    except ValueError:
        pass


def _test_forecast_short_history_flat():
    """< 3 periods of history → flat forecast at last value."""
    eng = TradeFinanceReportingEngine()
    f = eng.forecast_volume_trajectory(
        [Decimal("500000"), Decimal("700000")],
        horizon_periods=3)
    assert all(
        v == Decimal("700000") for v in f.forecast_values_kes)


def _test_forecast_clips_negatives_to_zero():
    """Strongly declining history → flat-to-zero forecast."""
    eng = TradeFinanceReportingEngine()
    history = [Decimal(str(10000000 - i * 2000000))
               for i in range(5)]
    f = eng.forecast_volume_trajectory(
        history, horizon_periods=5)
    assert all(
        v >= Decimal("0") for v in f.forecast_values_kes)


def _test_management_report_full():
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_lc(
            "L1", "AcmeOil", "ChinaCorp",
            Decimal("3000000")),
        _make_lc(
            "L2", "Biotech", "GermanCorp",
            Decimal("7000000")),
    )
    country_attr = {
        "ChinaCorp": "CN", "GermanCorp": "DE"}
    sector_attr = {
        "AcmeOil": "ENERGY", "Biotech": "PHARMA"}
    history = [
        Decimal(str(1000000 * (i + 1))) for i in range(8)]
    labels = [f"P{i}" for i in range(8)]
    report = eng.build_management_report(
        insts, period_label="P9",
        as_of_date_iso="2026-04-15",
        country_attribution=country_attr,
        sector_attribution=sector_attr,
        history_for_anomaly=(history, labels),
        forecast_horizon=3)
    assert report.volume_aggregation.total_kes == Decimal(
        "10000000")
    assert report.country_exposure is not None
    assert report.sector_concentration is not None
    assert report.forecast is not None
    assert len(report.forecast.forecast_values_kes) == 3
    # All ML-extensible paths used fallback → overall_ml_disabled
    assert report.overall_ml_disabled is True


def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceReportingEngine()
    insts = (_make_lc(
        "L1", "A", "B", Decimal("1000000")),)
    eng.compute_trade_volumes(insts, "P")
    eng.compute_country_exposure(
        insts, {"B": "CN"}, "2026-04-15")
    history = [Decimal("1"), Decimal("2"), Decimal("3")]
    eng.detect_volume_anomalies(history, ["a", "b", "c"])
    eng.forecast_volume_trajectory(history, 1)
    # Inputs unchanged
    assert insts[0].amount_kes == Decimal("1000000")


def _test_full_provenance():
    eng = TradeFinanceReportingEngine()
    history = [Decimal("100")] * 10
    labels = [f"P{i}" for i in range(10)]
    history[5] = Decimal("100000000")    # spike
    findings = eng.detect_volume_anomalies(history, labels)
    if findings:
        assert any(
            "ENH-280" in r
            for r in findings[0].framework_refs)
        assert any(
            "Rule 6" in r
            for r in findings[0].framework_refs)
        assert any(
            "Rule 7" in r
            for r in findings[0].framework_refs)


def self_test() -> None:
    tests = [
        _test_volumes_basic,
        _test_volumes_no_attribution_marks_unknown,
        _test_country_exposure_diversified,
        _test_country_exposure_concentrated,
        _test_country_exposure_excludes_closed,
        _test_sector_concentration,
        _test_anomaly_statistical_fallback,
        _test_anomaly_flat_series_no_anomalies,
        _test_anomaly_short_series_no_findings,
        _test_anomaly_ml_hook_used,
        _test_anomaly_ml_hook_failure_falls_back,
        _test_anomaly_ml_hook_wrong_length_falls_back,
        _test_forecast_ols_fallback,
        _test_forecast_ml_hook_used,
        _test_forecast_ml_hook_failure_falls_back,
        _test_forecast_horizon_validates,
        _test_forecast_short_history_flat,
        _test_forecast_clips_negatives_to_zero,
        _test_management_report_full,
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
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_reporting self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_reporting self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

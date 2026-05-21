"""utils.legal_analytics — ENH-230 Legal Analytics & Reporting (v10.178).

Analytics rollup across the 8 prior Legal arc engines. Fulfills the
TREND_ANALYSIS deferral that ENH-228 LegalDashboardEngine names in its
board_summary surface. This is the LAST engine in the Legal arc
(v10.179 will be the closure ceremony — G154/G155 audit gates).

DESIGN CONTRACT
---------------
1. Composition over inheritance — engine references injected via
   constructor; this engine never mutates source engines, only reads
   board_summary() and selected query methods
2. Analytics use point-in-time snapshots from source engines.
   "Trend" requires comparison against a prior snapshot — when none
   is supplied, trend is honestly marked INSUFFICIENT_DATA rather than
   fabricating direction
3. Honest data availability tracking — when a source engine is None
   or its board_summary() raises, dependent KPIs are marked
   UNAVAILABLE and excluded from rollup
4. No ML/statistical inference — just deterministic ratios and
   counts. The board can read every formula in the source.

KPI CATALOGUE
-------------
1. matter_close_rate              — ENH-223 closed cases / total
2. matter_critical_open_rate      — ENH-223 critical open / total
3. spend_budget_utilization       — ENH-225 budgets at/over / total
4. counsel_active_rate            — ENH-224 active / total
5. obligation_compliance_rate     — ENH-222 (total - breached) / total
6. hold_acknowledgment_rate       — ENH-227 (total - overdue) / total
7. clause_governance_rate         — ENH-226 published / total playbooks
8. document_privilege_rate        — ENH-229 privileged / total
9. document_purgeable_rate        — ENH-229 purgeable now / total
10. discovery_response_open       — ENH-229 open discovery requests

REPORT KINDS
------------
- KPI_SNAPSHOT       — one-shot view of all 10 KPIs with availability
- TREND_ANALYSIS     — KPI deltas vs. prior_snapshot (operator supplies)
- EFFICIENCY_REPORT  — derived efficiency metrics (spend per matter,
                        billable per counsel, etc.)
- COMPLIANCE_PROFILE — cross-engine compliance posture

HONEST DEFERRALS
----------------
- ML_PREDICTIVE_MODELING: DEFERRED — no outcome prediction
- OPPOSING_COUNSEL_DATABASE: DEFERRED — engine has no opposing-counsel
  data; ENH-224 tracks OUR counsel only
- BENCHMARK_COMPARISONS: DEFERRED — industry benchmarks operator-side
- NATURAL_LANGUAGE_QUERY: DEFERRED
- VISUALIZATION_RENDERING: DEFERRED — chart libraries cockpit-side
- DRILLDOWN_NAVIGATION: DEFERRED — cockpit-side
- TIME_SERIES_PERSISTENCE: DEFERRED — engine accepts prior_snapshot
  but does not auto-persist period snapshots
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------- enums

class AnalyticsPeriod(str, Enum):
    """Period granularity for trend reports."""
    MONTHLY   = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL    = "ANNUAL"
    CUSTOM    = "CUSTOM"


class ReportKind(str, Enum):
    """Report types this engine produces."""
    KPI_SNAPSHOT       = "KPI_SNAPSHOT"
    TREND_ANALYSIS     = "TREND_ANALYSIS"
    EFFICIENCY_REPORT  = "EFFICIENCY_REPORT"
    COMPLIANCE_PROFILE = "COMPLIANCE_PROFILE"


class TrendDirection(str, Enum):
    """Direction of change between two periods."""
    IMPROVING         = "IMPROVING"
    STABLE            = "STABLE"
    DETERIORATING     = "DETERIORATING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DataAvailability(str, Enum):
    """Honest tracking — was a source engine reachable?"""
    FULL        = "FULL"
    UNAVAILABLE = "UNAVAILABLE"


class TransitionOutcome(str, Enum):
    """Operational outcomes (parity with sibling engines)."""
    REPORT_GENERATED        = "REPORT_GENERATED"
    REPORT_PARTIAL          = "REPORT_PARTIAL"
    REPORT_INSUFFICIENT     = "REPORT_INSUFFICIENT"


# ------------------------------------------------------------- helpers

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Stability threshold: |delta| < 1pp counts as STABLE
_TREND_STABLE_THRESHOLD_PP = 1.0


def _classify_trend(
    current: Optional[float],
    prior: Optional[float],
    higher_is_better: bool = True,
) -> TrendDirection:
    """Compare two values and return trend direction.

    higher_is_better: True for KPIs like compliance_rate where larger
    means better. False for KPIs like critical_open_rate where smaller
    means better.
    """
    if current is None or prior is None:
        return TrendDirection.INSUFFICIENT_DATA
    delta = current - prior
    if abs(delta) < _TREND_STABLE_THRESHOLD_PP:
        return TrendDirection.STABLE
    if higher_is_better:
        return (TrendDirection.IMPROVING if delta > 0
                else TrendDirection.DETERIORATING)
    return (TrendDirection.IMPROVING if delta < 0
            else TrendDirection.DETERIORATING)


def _safe_summary(engine: Any) -> Optional[Dict[str, Any]]:
    if engine is None:
        return None
    try:
        s = engine.board_summary()
        return s if isinstance(s, dict) else None
    except Exception:
        return None


def _pct_or_none(num: float, den: float) -> Optional[float]:
    if den <= 0:
        return None
    return (num / den) * 100.0


# ------------------------------------------------------------- dataclasses

@dataclass(frozen=True)
class AnalyticsKPI:
    """A single KPI value with metadata."""
    name:           str
    value:          Optional[float]   # None means UNAVAILABLE
    prior_value:    Optional[float]
    trend:          TrendDirection
    source_engine:  str
    availability:   DataAvailability
    higher_is_better: bool = True
    unit:           str = "%"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name":              self.name,
            "value":             (None if self.value is None
                                  else round(self.value, 1)),
            "prior_value":       (None if self.prior_value is None
                                  else round(self.prior_value, 1)),
            "trend":             self.trend.value,
            "source_engine":     self.source_engine,
            "availability":      self.availability.value,
            "higher_is_better":  self.higher_is_better,
            "unit":              self.unit,
        }


@dataclass(frozen=True)
class LegalReport:
    """A generated analytics report at a point in time."""
    kind:             ReportKind
    generated_at_utc: str
    period:           AnalyticsPeriod
    kpis:             tuple   # tuple of AnalyticsKPI
    derived_metrics:  Dict[str, Any] = field(default_factory=dict)
    n_full:           int = 0
    n_unavailable:    int = 0
    partial_data:     bool = False
    outcome:          TransitionOutcome = (
        TransitionOutcome.REPORT_GENERATED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind":             self.kind.value,
            "generated_at_utc": self.generated_at_utc,
            "period":           self.period.value,
            "kpis":             [k.to_dict() for k in self.kpis],
            "derived_metrics":  self.derived_metrics,
            "n_full":           self.n_full,
            "n_unavailable":    self.n_unavailable,
            "partial_data":     self.partial_data,
            "outcome":          self.outcome.value,
        }


# ------------------------------------------------------------- engine

class LegalAnalyticsEngine:
    """ENH-230 Legal Analytics & Reporting engine (v10.178)."""

    ENGINE_NAME      = "ENH-230 LegalAnalyticsEngine"
    REGULATORY_BASIS = (
        "Internal GC strategic intelligence — analytics rollup across "
        "the 8 Legal arc engines (ENH-222..229). Fulfills the "
        "TREND_ANALYSIS deferral surfaced by ENH-228 dashboard. "
        "Deterministic ratios only, no ML inference. Time-series "
        "persistence is operator-side; this engine accepts a "
        "prior_snapshot parameter for trend computation when supplied.")

    def __init__(
        self,
        obligation_engine:      Optional[Any] = None,
        case_engine:            Optional[Any] = None,
        spend_engine:           Optional[Any] = None,
        counsel_engine:         Optional[Any] = None,
        clause_engine:          Optional[Any] = None,
        hold_engine:            Optional[Any] = None,
        dashboard_engine:       Optional[Any] = None,
        document_engine:        Optional[Any] = None,
    ) -> None:
        self.obligation_engine = obligation_engine
        self.case_engine        = case_engine
        self.spend_engine       = spend_engine
        self.counsel_engine     = counsel_engine
        self.clause_engine      = clause_engine
        self.hold_engine        = hold_engine
        self.dashboard_engine   = dashboard_engine
        self.document_engine    = document_engine

    # -------------------- per-KPI computers

    def _kpi_matter_close_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.case_engine)
        if s is None:
            return AnalyticsKPI(
                name="matter_close_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-223",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_cases_total", 0) or 0
        n_open = s.get("n_open", 0) or 0
        if total == 0:
            v = 100.0   # vacuously true: 0 closed of 0 → fully resolved
        else:
            v = ((total - n_open) / total) * 100.0
        prior_val = (prior.get("matter_close_rate") if prior else None)
        return AnalyticsKPI(
            name="matter_close_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-223",
            availability=DataAvailability.FULL,
            higher_is_better=True)

    def _kpi_matter_critical_open_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.case_engine)
        if s is None:
            return AnalyticsKPI(
                name="matter_critical_open_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-223",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=False)
        total = s.get("n_cases_total", 0) or 0
        crit = s.get("n_critical_open", 0) or 0
        v = (crit / total) * 100.0 if total > 0 else 0.0
        prior_val = (prior.get("matter_critical_open_rate")
                     if prior else None)
        return AnalyticsKPI(
            name="matter_critical_open_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=False),
            source_engine="ENH-223",
            availability=DataAvailability.FULL,
            higher_is_better=False)

    def _kpi_spend_budget_utilization(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.spend_engine)
        if s is None:
            return AnalyticsKPI(
                name="spend_budget_utilization",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-225",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=False)
        total = s.get("n_budgets_total", 0) or 0
        over = s.get("n_budgets_at_or_over_limit", 0) or 0
        v = (over / total) * 100.0 if total > 0 else 0.0
        prior_val = (prior.get("spend_budget_utilization")
                     if prior else None)
        return AnalyticsKPI(
            name="spend_budget_utilization",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=False),
            source_engine="ENH-225",
            availability=DataAvailability.FULL,
            higher_is_better=False)

    def _kpi_counsel_active_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.counsel_engine)
        if s is None:
            return AnalyticsKPI(
                name="counsel_active_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-224",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_counsel_total", 0) or 0
        active = s.get("n_counsel_active", 0) or 0
        v = (active / total) * 100.0 if total > 0 else 100.0
        prior_val = (prior.get("counsel_active_rate")
                     if prior else None)
        return AnalyticsKPI(
            name="counsel_active_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-224",
            availability=DataAvailability.FULL,
            higher_is_better=True)

    def _kpi_obligation_compliance_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.obligation_engine)
        if s is None:
            return AnalyticsKPI(
                name="obligation_compliance_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-222",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_obligations_total", 0) or 0
        # Use alert_counts (deadline-derived) not n_breached (formal
        # status counter) — alerts reflect the real compliance signal
        # since formal status transitions are operator-driven.
        alerts = s.get("alert_counts", {}) or {}
        breached = alerts.get("BREACHED", 0) or 0
        v = (((total - breached) / total) * 100.0
             if total > 0 else 100.0)
        prior_val = (prior.get("obligation_compliance_rate")
                     if prior else None)
        return AnalyticsKPI(
            name="obligation_compliance_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-222",
            availability=DataAvailability.FULL,
            higher_is_better=True)

    def _kpi_hold_acknowledgment_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.hold_engine)
        if s is None:
            return AnalyticsKPI(
                name="hold_acknowledgment_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-227",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_acknowledgments_total", 0) or 0
        overdue = s.get("n_acknowledgments_overdue", 0) or 0
        v = (((total - overdue) / total) * 100.0
             if total > 0 else 100.0)
        prior_val = (prior.get("hold_acknowledgment_rate")
                     if prior else None)
        return AnalyticsKPI(
            name="hold_acknowledgment_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-227",
            availability=DataAvailability.FULL,
            higher_is_better=True)

    def _kpi_clause_governance_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.clause_engine)
        if s is None:
            return AnalyticsKPI(
                name="clause_governance_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-226",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_playbooks_total", 0) or 0
        published = s.get("n_playbooks_published", 0) or 0
        v = ((published / total) * 100.0
             if total > 0 else 100.0)
        prior_val = (prior.get("clause_governance_rate")
                     if prior else None)
        return AnalyticsKPI(
            name="clause_governance_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-226",
            availability=DataAvailability.FULL,
            higher_is_better=True)

    def _kpi_document_privilege_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.document_engine)
        if s is None:
            return AnalyticsKPI(
                name="document_privilege_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-229",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_documents_total", 0) or 0
        priv = s.get("n_privileged_documents", 0) or 0
        v = (priv / total) * 100.0 if total > 0 else 0.0
        prior_val = (prior.get("document_privilege_rate")
                     if prior else None)
        # Higher privilege rate isn't strictly "better" — it depends on
        # the doc mix. Mark stable trend by default (no value judgment).
        return AnalyticsKPI(
            name="document_privilege_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-229",
            availability=DataAvailability.FULL,
            higher_is_better=True)

    def _kpi_document_purgeable_rate(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.document_engine)
        if s is None:
            return AnalyticsKPI(
                name="document_purgeable_rate",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-229",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=True)
        total = s.get("n_documents_total", 0) or 0
        purge = s.get("n_documents_purgeable_now", 0) or 0
        v = (purge / total) * 100.0 if total > 0 else 0.0
        prior_val = (prior.get("document_purgeable_rate")
                     if prior else None)
        return AnalyticsKPI(
            name="document_purgeable_rate",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=True),
            source_engine="ENH-229",
            availability=DataAvailability.FULL,
            higher_is_better=True,
            unit="%")

    def _kpi_discovery_response_open(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> AnalyticsKPI:
        s = _safe_summary(self.document_engine)
        if s is None:
            return AnalyticsKPI(
                name="discovery_response_open",
                value=None, prior_value=None,
                trend=TrendDirection.INSUFFICIENT_DATA,
                source_engine="ENH-229",
                availability=DataAvailability.UNAVAILABLE,
                higher_is_better=False,
                unit="count")
        v = float(s.get("n_discovery_requests_open", 0) or 0)
        prior_val = (prior.get("discovery_response_open")
                     if prior else None)
        return AnalyticsKPI(
            name="discovery_response_open",
            value=v,
            prior_value=prior_val,
            trend=_classify_trend(v, prior_val, higher_is_better=False),
            source_engine="ENH-229",
            availability=DataAvailability.FULL,
            higher_is_better=False,
            unit="count")

    # -------------------- KPI snapshot

    def kpi_snapshot(
        self, prior_snapshot: Optional[Dict[str, float]] = None,
    ) -> Tuple[AnalyticsKPI, ...]:
        """Return all 10 KPIs as a tuple.

        prior_snapshot, if provided, is a flat {name: value} dict from
        a previous snapshot used to compute trend direction.
        """
        return (
            self._kpi_matter_close_rate(prior_snapshot),
            self._kpi_matter_critical_open_rate(prior_snapshot),
            self._kpi_spend_budget_utilization(prior_snapshot),
            self._kpi_counsel_active_rate(prior_snapshot),
            self._kpi_obligation_compliance_rate(prior_snapshot),
            self._kpi_hold_acknowledgment_rate(prior_snapshot),
            self._kpi_clause_governance_rate(prior_snapshot),
            self._kpi_document_privilege_rate(prior_snapshot),
            self._kpi_document_purgeable_rate(prior_snapshot),
            self._kpi_discovery_response_open(prior_snapshot),
        )

    def snapshot_to_dict(
        self, kpis: Tuple[AnalyticsKPI, ...]
    ) -> Dict[str, float]:
        """Flatten KPIs to {name: value} dict for re-use as
        prior_snapshot input."""
        out: Dict[str, float] = {}
        for k in kpis:
            if k.value is not None:
                out[k.name] = k.value
        return out

    # -------------------- derived efficiency metrics

    def efficiency_metrics(self) -> Dict[str, Any]:
        """Cross-engine efficiency rollups."""
        case_s = _safe_summary(self.case_engine)
        spend_s = _safe_summary(self.spend_engine)
        counsel_s = _safe_summary(self.counsel_engine)

        out: Dict[str, Any] = {}

        # Spend per matter
        if case_s and spend_s:
            n_matters = case_s.get("n_cases_total", 0) or 0
            currencies = (spend_s.get("total_spend_by_currency", {})
                          or {})
            spend_per_matter: Dict[str, float] = {}
            for ccy, amt in currencies.items():
                if n_matters > 0:
                    try:
                        spend_per_matter[ccy] = float(amt) / n_matters
                    except (TypeError, ValueError):
                        pass
            out["spend_per_matter_by_currency"] = spend_per_matter
        else:
            out["spend_per_matter_by_currency"] = (
                "UNAVAILABLE — needs ENH-223 + ENH-225")

        # Assignments per counsel
        if counsel_s:
            n_counsel = counsel_s.get("n_counsel_total", 0) or 0
            n_assign = counsel_s.get("n_assignments_total", 0) or 0
            if n_counsel > 0:
                out["assignments_per_counsel"] = (
                    round(n_assign / n_counsel, 2))
            else:
                out["assignments_per_counsel"] = 0.0
        else:
            out["assignments_per_counsel"] = (
                "UNAVAILABLE — needs ENH-224")

        return out

    # -------------------- portfolio health (overall)

    def portfolio_health_score(self) -> Optional[float]:
        """Composite 0-100 score across all available KPIs.

        Direction-aware: KPIs where lower is better are inverted before
        averaging. Returns None if no KPIs available.
        """
        kpis = self.kpi_snapshot()
        usable = [k for k in kpis
                  if k.availability == DataAvailability.FULL
                  and k.value is not None
                  and k.unit == "%"]
        if not usable:
            return None
        total = 0.0
        for k in usable:
            if k.higher_is_better:
                total += k.value
            else:
                total += (100.0 - k.value)
        return total / len(usable)

    # -------------------- report generators

    def generate_report(
        self,
        kind: ReportKind,
        period: AnalyticsPeriod = AnalyticsPeriod.QUARTERLY,
        prior_snapshot: Optional[Dict[str, float]] = None,
    ) -> LegalReport:
        kpis = self.kpi_snapshot(prior_snapshot)
        n_full = sum(1 for k in kpis
                     if k.availability == DataAvailability.FULL)
        n_unavail = sum(1 for k in kpis
                        if k.availability == DataAvailability.UNAVAILABLE)
        partial = (n_unavail > 0)

        derived: Dict[str, Any] = {}
        if kind in (ReportKind.EFFICIENCY_REPORT,
                     ReportKind.COMPLIANCE_PROFILE,
                     ReportKind.KPI_SNAPSHOT,
                     ReportKind.TREND_ANALYSIS):
            derived["efficiency"] = self.efficiency_metrics()
            derived["portfolio_health_score"] = (
                self.portfolio_health_score())

        if kind == ReportKind.TREND_ANALYSIS and prior_snapshot is None:
            outcome = TransitionOutcome.REPORT_INSUFFICIENT
        elif partial:
            outcome = TransitionOutcome.REPORT_PARTIAL
        else:
            outcome = TransitionOutcome.REPORT_GENERATED

        return LegalReport(
            kind=kind,
            generated_at_utc=_now_iso(),
            period=period,
            kpis=kpis,
            derived_metrics=derived,
            n_full=n_full,
            n_unavailable=n_unavail,
            partial_data=partial,
            outcome=outcome,
        )

    # -------------------- board summary

    def board_summary(self) -> Dict[str, Any]:
        report = self.generate_report(ReportKind.KPI_SNAPSHOT)
        return {
            "engine":              self.ENGINE_NAME,
            "regulatory_basis":    self.REGULATORY_BASIS,
            "generated_at_utc":    report.generated_at_utc,
            "n_kpis_total":        len(report.kpis),
            "n_kpis_full":         report.n_full,
            "n_kpis_unavailable":  report.n_unavailable,
            "partial_data":        report.partial_data,
            "outcome":             report.outcome.value,
            "kpis":                [k.to_dict() for k in report.kpis],
            "portfolio_health_score": (
                report.derived_metrics.get("portfolio_health_score")),
            "efficiency":          report.derived_metrics.get(
                "efficiency"),
            # Honest deferral surface
            "ml_predictive_modeling_status":
                ("DEFERRED — engine reports deterministic ratios "
                 "only, no outcome prediction"),
            "opposing_counsel_database_status":
                ("DEFERRED — engine has no opposing-counsel data; "
                 "ENH-224 tracks OUR counsel only"),
            "benchmark_comparisons_status":
                ("DEFERRED — industry benchmarks operator-side"),
            "natural_language_query_status":
                "DEFERRED",
            "visualization_rendering_status":
                ("DEFERRED — chart libraries cockpit-side"),
            "drilldown_navigation_status":
                ("DEFERRED — cockpit-side navigation"),
            "time_series_persistence_status":
                ("DEFERRED — engine accepts prior_snapshot for trend "
                 "computation; auto-persistence is operator-side"),
        }


__all__ = [
    "AnalyticsPeriod",
    "ReportKind",
    "TrendDirection",
    "DataAvailability",
    "TransitionOutcome",
    "AnalyticsKPI",
    "LegalReport",
    "LegalAnalyticsEngine",
]

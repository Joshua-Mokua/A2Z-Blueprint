"""utils/market_risk_limits.py — v10.40: Market Risk Limit Framework.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-MR-006 — Market Risk Limit Framework                              ║
║  ENH-MR-007 — Limit Breach Detection & Escalation                      ║
║  Cat A — locked behind G129 (added in this batch)                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Limits are operational constraints layered ON TOP of the v10.39       ║
║  measurement engines (VaR / ES / sensitivities). The measurement       ║
║  engines compute what COULD happen; this module defines what is        ║
║  ALLOWED to happen and surfaces alerts when reality crosses the line.  ║
║                                                                         ║
║  Three limit categories:                                                ║
║    - CONCENTRATION — exposure per RiskFactor or RiskFactorClass        ║
║    - VAR_LIMIT — daily 99% VaR ceiling per portfolio                   ║
║    - ES_LIMIT — FRTB-IMA 97.5% ES ceiling per portfolio                ║
║                                                                         ║
║  Three breach severities:                                              ║
║    - WARN — utilization ≥ 80% but < 100% (heads-up, no action)         ║
║    - BREACH — utilization ≥ 100% (alert + escalate)                    ║
║    - SEVERE_BREACH — utilization ≥ 120% (immediate escalation)         ║
║                                                                         ║
║  Per Rule 1: every BreachAlert surfaces                                ║
║    severity + limit_id + observed + threshold + utilization_pct        ║
║    + risk_factor (if applicable) + framework_refs                      ║
║    + suggested_action + escalation_target                              ║
║                                                                         ║
║  Per Rule 7: the monitor NEVER auto-executes remediation — it          ║
║  surfaces alerts that flow into existing approval workflows.           ║
║  treasury_agents.PaymentReviewAgent and the broader Recommendation     ║
║  lifecycle (PENDING → APPROVED → EXECUTED) handle the action layer.    ║
║  EU AI Act Art 14 human oversight preserved.                           ║
║                                                                         ║
║  Composes with:                                                         ║
║    - market_risk_var.VaREngine (consumes VaRResult)                    ║
║    - market_risk_sensitivities.SensitivityEngine (consumes             ║
║      SensitivityReport)                                                 ║
║    - market_risk_factors.RiskFactor / RiskFactorClass (limit scope)    ║
║    - core_audit (audit trail of every breach)                          ║
║    - treasury_agents (downstream remediation workflow)                 ║
║                                                                         ║
║  Regulatory sources:                                                    ║
║    - BCBS d352 FRTB §A.4 (trading book boundary, limit framework)      ║
║    - CBK PG/04 Market Risk §4 (board-approved limit structure)         ║
║    - EBA/GL/2018/02 (limits + breach handling)                         ║
║    - BCBS 239 §5 (data quality + risk reporting frequency)             ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import (
    Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)

from utils.market_risk_factors import (
    RISK_FACTOR_TO_CLASS, RiskFactor, RiskFactorClass)

SPEC_DEVIATION_NOTE = (
    "MarketRiskLimits implements the v10.40 limit framework. Per "
    "Rule 7, LimitMonitor never auto-executes remediation — every "
    "BreachAlert flows into the human-overseen approval workflow "
    "(treasury_agents.PaymentReviewAgent or equivalent). Per Rule 1, "
    "every BreachAlert surfaces severity + observed + threshold + "
    "utilization + risk_factor + framework_refs + suggested_action. "
    "Decimal-internal precision throughout. Limits are read-only "
    "configuration once registered — changes require a new "
    "registration with new effective_date."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class LimitType(Enum):
    """Three limit categories supported in v10.40."""
    CONCENTRATION = "CONCENTRATION"   # per-factor or per-class exposure
    VAR_LIMIT = "VAR_LIMIT"           # daily VaR ceiling
    ES_LIMIT = "ES_LIMIT"             # ES ceiling


class LimitScope(Enum):
    """What the limit applies to."""
    SINGLE_FACTOR = "SINGLE_FACTOR"   # one RiskFactor
    FACTOR_CLASS = "FACTOR_CLASS"     # one RiskFactorClass (e.g., all FX)
    PORTFOLIO = "PORTFOLIO"           # entire portfolio (VaR/ES)


class BreachSeverity(Enum):
    """Severity bands by utilization percentage."""
    WITHIN_LIMIT = "WITHIN_LIMIT"     # < 80% — informational only
    WARN = "WARN"                     # 80-99.99% — heads-up
    BREACH = "BREACH"                 # 100-119.99% — escalate
    SEVERE_BREACH = "SEVERE_BREACH"   # ≥ 120% — immediate escalation


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RiskLimit:
    """A single risk limit definition.

    Frozen — once registered, a limit is read-only. To change a
    limit, register a new one (which would have a different
    effective_date) and deactivate the old one in the registry.

    Per Rule 1, every limit carries:
      - limit_id (unique)
      - limit_type
      - scope
      - threshold_kes (positive Decimal)
      - factor / factor_class (depending on scope)
      - description
      - regulatory_source + framework_refs
      - approval_authority (board/Risk/Treasury per CBK PG/04 §4.2)
      - effective_date (ISO 8601)
    """
    limit_id: str
    limit_type: LimitType
    scope: LimitScope
    threshold_kes: Decimal
    description: str
    regulatory_source: str
    framework_refs: Tuple[str, ...]
    approval_authority: str           # "BOARD" / "ALCO" / "TREASURY"
    effective_date: str               # ISO 8601 date
    factor: Optional[RiskFactor] = None
    factor_class: Optional[RiskFactorClass] = None
    confidence: Optional[Decimal] = None  # for VAR_LIMIT / ES_LIMIT
    horizon_days: Optional[int] = None    # for VAR_LIMIT / ES_LIMIT
    notes: str = ""

    def __post_init__(self) -> None:
        # Per Rule 1: validate construction-time invariants
        if self.threshold_kes <= 0:
            raise ValueError(
                f"limit {self.limit_id}: threshold_kes must be "
                f"positive (got {self.threshold_kes})")
        if self.scope == LimitScope.SINGLE_FACTOR:
            if self.factor is None:
                raise ValueError(
                    f"limit {self.limit_id}: SINGLE_FACTOR scope "
                    f"requires factor")
            if self.factor_class is not None:
                raise ValueError(
                    f"limit {self.limit_id}: SINGLE_FACTOR scope "
                    f"must not set factor_class")
        elif self.scope == LimitScope.FACTOR_CLASS:
            if self.factor_class is None:
                raise ValueError(
                    f"limit {self.limit_id}: FACTOR_CLASS scope "
                    f"requires factor_class")
            if self.factor is not None:
                raise ValueError(
                    f"limit {self.limit_id}: FACTOR_CLASS scope "
                    f"must not set factor")
        elif self.scope == LimitScope.PORTFOLIO:
            if self.factor is not None or self.factor_class is not None:
                raise ValueError(
                    f"limit {self.limit_id}: PORTFOLIO scope must "
                    f"not set factor or factor_class")
        if self.limit_type == LimitType.CONCENTRATION:
            if self.scope == LimitScope.PORTFOLIO:
                raise ValueError(
                    f"limit {self.limit_id}: CONCENTRATION limits "
                    f"must scope to a factor or class, not portfolio")
        if self.limit_type in (LimitType.VAR_LIMIT, LimitType.ES_LIMIT):
            if self.scope != LimitScope.PORTFOLIO:
                raise ValueError(
                    f"limit {self.limit_id}: {self.limit_type.value} "
                    f"only supports PORTFOLIO scope")
            if self.confidence is None:
                raise ValueError(
                    f"limit {self.limit_id}: {self.limit_type.value} "
                    f"requires confidence")
            if self.horizon_days is None:
                raise ValueError(
                    f"limit {self.limit_id}: {self.limit_type.value} "
                    f"requires horizon_days")


@dataclass(frozen=True)
class BreachAlert:
    """A single breach observation with full triage info.

    Per Rule 1: every alert carries everything needed to act.
    """
    alert_id: str                    # deterministic from limit + obs
    severity: BreachSeverity
    limit_id: str
    limit_type: LimitType
    scope: LimitScope
    observed_kes: Decimal
    threshold_kes: Decimal
    utilization_pct: Decimal         # observed / threshold × 100
    factor: Optional[RiskFactor] = None
    factor_class: Optional[RiskFactorClass] = None
    suggested_action: str = ""
    escalation_target: str = ""      # who gets notified
    framework_refs: Tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class MonitorReport:
    """Aggregated outcome of one limit-check pass."""
    alerts: Tuple[BreachAlert, ...]
    n_limits_checked: int
    n_within: int
    n_warn: int
    n_breach: int
    n_severe: int
    summary: str

    def severe_breaches(self) -> Tuple[BreachAlert, ...]:
        return tuple(
            a for a in self.alerts
            if a.severity == BreachSeverity.SEVERE_BREACH)

    def breaches(self) -> Tuple[BreachAlert, ...]:
        return tuple(
            a for a in self.alerts
            if a.severity in (
                BreachSeverity.BREACH, BreachSeverity.SEVERE_BREACH))

    def is_clean(self) -> bool:
        """No actual breaches (WARN is acceptable)."""
        return self.n_breach == 0 and self.n_severe == 0


# ════════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════════

class LimitRegistry:
    """In-memory registry of active risk limits.

    Limits are immutable once registered. To "change" a limit, deactivate
    the old one and register a new one — preserving full audit history.
    """

    def __init__(self) -> None:
        self._limits: Dict[str, RiskLimit] = {}
        self._active: Dict[str, bool] = {}

    def register(self, limit: RiskLimit) -> None:
        if limit.limit_id in self._limits:
            raise ValueError(
                f"limit {limit.limit_id} already registered "
                f"(deactivate the existing one first)")
        self._limits[limit.limit_id] = limit
        self._active[limit.limit_id] = True

    def deactivate(self, limit_id: str) -> None:
        if limit_id not in self._limits:
            raise KeyError(f"unknown limit {limit_id}")
        self._active[limit_id] = False

    def get(self, limit_id: str) -> RiskLimit:
        if limit_id not in self._limits:
            raise KeyError(f"unknown limit {limit_id}")
        return self._limits[limit_id]

    def is_active(self, limit_id: str) -> bool:
        return self._active.get(limit_id, False)

    def all_active(self) -> Tuple[RiskLimit, ...]:
        return tuple(
            self._limits[k] for k in self._limits
            if self._active.get(k))

    def by_type(self, limit_type: LimitType) -> Tuple[RiskLimit, ...]:
        return tuple(
            limit for limit in self.all_active()
            if limit.limit_type == limit_type)

    def by_factor(
        self, factor: RiskFactor,
    ) -> Tuple[RiskLimit, ...]:
        """Limits applicable to a given factor.

        Includes both SINGLE_FACTOR limits scoped to that factor AND
        FACTOR_CLASS limits whose class contains the factor.
        """
        cls = RISK_FACTOR_TO_CLASS[factor]
        return tuple(
            limit for limit in self.all_active()
            if (limit.scope == LimitScope.SINGLE_FACTOR
                and limit.factor == factor)
            or (limit.scope == LimitScope.FACTOR_CLASS
                and limit.factor_class == cls))

    def summary(self) -> Dict[str, Any]:
        active = self.all_active()
        by_type: Dict[str, int] = {}
        for limit in active:
            by_type[limit.limit_type.value] = (
                by_type.get(limit.limit_type.value, 0) + 1)
        return {
            "n_total": len(self._limits),
            "n_active": len(active),
            "n_inactive": len(self._limits) - len(active),
            "by_type": by_type,
        }


# ════════════════════════════════════════════════════════════════════════
# Monitor
# ════════════════════════════════════════════════════════════════════════

# Severity thresholds (utilization percentage)
WARN_THRESHOLD_PCT = Decimal("80")
BREACH_THRESHOLD_PCT = Decimal("100")
SEVERE_THRESHOLD_PCT = Decimal("120")


def _classify_severity(
    utilization_pct: Decimal,
) -> BreachSeverity:
    """Classify a utilization percentage into a severity band."""
    if utilization_pct < WARN_THRESHOLD_PCT:
        return BreachSeverity.WITHIN_LIMIT
    if utilization_pct < BREACH_THRESHOLD_PCT:
        return BreachSeverity.WARN
    if utilization_pct < SEVERE_THRESHOLD_PCT:
        return BreachSeverity.BREACH
    return BreachSeverity.SEVERE_BREACH


def _suggest_action(
    severity: BreachSeverity, limit_type: LimitType,
) -> str:
    """Suggested-action text per severity × type."""
    if severity == BreachSeverity.WITHIN_LIMIT:
        return "no action; utilization < 80%"
    if severity == BreachSeverity.WARN:
        return (
            f"informational; utilization ≥ 80%; "
            f"review for trending toward limit")
    if severity == BreachSeverity.BREACH:
        if limit_type == LimitType.CONCENTRATION:
            return (
                "BREACH: reduce exposure or seek ALCO approval for "
                "temporary excess; create remediation plan within "
                "1 business day per CBK PG/04 §4.5")
        if limit_type == LimitType.VAR_LIMIT:
            return (
                "BREACH: reduce risk-bearing positions or hedge; "
                "report to CRO + ALCO same day per BCBS d352 §A.4.6")
        return (
            "BREACH: ES exceeds limit; reduce tail-risk positions; "
            "report to CRO + ALCO same day")
    return (
        "SEVERE_BREACH: immediate position reduction required; "
        "notify CRO + Board Risk Committee within hours per CBK "
        "PG/04 §4.6 + EBA/GL/2018/02")


def _escalation_target(
    severity: BreachSeverity, limit: RiskLimit,
) -> str:
    """Who gets notified."""
    if severity == BreachSeverity.WITHIN_LIMIT:
        return ""
    if severity == BreachSeverity.WARN:
        return "Treasury + Risk Operations"
    if severity == BreachSeverity.BREACH:
        if limit.approval_authority == "BOARD":
            return "ALCO + Board Risk Committee"
        return "ALCO + CRO"
    # SEVERE_BREACH always reaches Board level
    return "Board Risk Committee + CRO + Treasurer"


class LimitMonitor:
    """Checks observed exposures/VaR/ES against registered limits.

    Per Rule 7, LimitMonitor is purely diagnostic — it produces
    BreachAlert objects but never executes remediation. Action flow
    happens via treasury_agents.PaymentReviewAgent or human approval
    workflow.
    """

    def __init__(self, registry: LimitRegistry) -> None:
        self.registry = registry

    # ── Per-limit checks ──────────────────────────────────────────────

    def _build_alert(
        self,
        limit: RiskLimit,
        observed_kes: Decimal,
    ) -> BreachAlert:
        """Build a BreachAlert from observed vs threshold."""
        if limit.threshold_kes == 0:
            # Never possible after RiskLimit __post_init__, but defensive
            utilization = Decimal("0")
        else:
            utilization = (
                Decimal(str(observed_kes))
                / limit.threshold_kes * Decimal("100"))
        severity = _classify_severity(utilization)
        # Deterministic alert ID — useful for dedup in audit trails
        alert_id = (
            f"{limit.limit_id}::"
            f"{limit.effective_date}::"
            f"obs_{observed_kes}::"
            f"{severity.value}")
        return BreachAlert(
            alert_id=alert_id,
            severity=severity,
            limit_id=limit.limit_id,
            limit_type=limit.limit_type,
            scope=limit.scope,
            observed_kes=Decimal(str(observed_kes)),
            threshold_kes=limit.threshold_kes,
            utilization_pct=utilization.quantize(Decimal("0.01")),
            factor=limit.factor,
            factor_class=limit.factor_class,
            suggested_action=_suggest_action(
                severity, limit.limit_type),
            escalation_target=_escalation_target(severity, limit),
            framework_refs=limit.framework_refs)

    # ── Concentration checks ──────────────────────────────────────────

    def check_concentration(
        self, *,
        exposures_by_factor: Mapping[RiskFactor, Decimal],
    ) -> Tuple[BreachAlert, ...]:
        """Check all CONCENTRATION limits against observed exposures.

        exposures_by_factor: factor → absolute KES exposure (positive
        Decimal). Concentration limits compare the absolute exposure
        magnitude.
        """
        alerts: List[BreachAlert] = []
        # Aggregate by class for FACTOR_CLASS limits
        by_class: Dict[RiskFactorClass, Decimal] = {}
        for factor, exposure in exposures_by_factor.items():
            cls = RISK_FACTOR_TO_CLASS[factor]
            by_class[cls] = by_class.get(cls, Decimal("0")) + abs(
                Decimal(str(exposure)))
        for limit in self.registry.by_type(LimitType.CONCENTRATION):
            if limit.scope == LimitScope.SINGLE_FACTOR:
                exposure = exposures_by_factor.get(
                    limit.factor, Decimal("0"))
                observed = abs(Decimal(str(exposure)))
            else:    # FACTOR_CLASS
                observed = by_class.get(
                    limit.factor_class, Decimal("0"))
            alert = self._build_alert(limit, observed)
            alerts.append(alert)
        return tuple(alerts)

    # ── VaR / ES checks ───────────────────────────────────────────────

    def check_var(
        self, *,
        observed_var_kes: Decimal,
        confidence: Decimal,
        horizon_days: int,
    ) -> Tuple[BreachAlert, ...]:
        """Check VAR_LIMIT entries matching the (confidence, horizon)
        of the observed VaR computation.

        VAR_LIMIT applies only when confidence + horizon match the
        limit definition (a 99% / 1-day VaR limit cannot be checked
        against a 97.5% / 10-day VaR observation).
        """
        alerts: List[BreachAlert] = []
        for limit in self.registry.by_type(LimitType.VAR_LIMIT):
            if (limit.confidence != confidence
                    or limit.horizon_days != horizon_days):
                continue
            alerts.append(self._build_alert(limit, observed_var_kes))
        return tuple(alerts)

    def check_es(
        self, *,
        observed_es_kes: Decimal,
        confidence: Decimal,
        horizon_days: int,
    ) -> Tuple[BreachAlert, ...]:
        """Check ES_LIMIT entries matching the (confidence, horizon)."""
        alerts: List[BreachAlert] = []
        for limit in self.registry.by_type(LimitType.ES_LIMIT):
            if (limit.confidence != confidence
                    or limit.horizon_days != horizon_days):
                continue
            alerts.append(self._build_alert(limit, observed_es_kes))
        return tuple(alerts)

    # ── Top-level pass ────────────────────────────────────────────────

    def run_pass(
        self, *,
        exposures_by_factor: Optional[
            Mapping[RiskFactor, Decimal]] = None,
        var_observation: Optional[Tuple[Decimal, Decimal, int]] = None,
        es_observation: Optional[Tuple[Decimal, Decimal, int]] = None,
    ) -> MonitorReport:
        """Check all relevant limits given the observation set.

        Each parameter is optional — call run_pass with whichever
        observations are available.

          var_observation = (observed_var_kes, confidence, horizon_days)
          es_observation  = (observed_es_kes, confidence, horizon_days)
        """
        alerts: List[BreachAlert] = []
        if exposures_by_factor is not None:
            alerts.extend(self.check_concentration(
                exposures_by_factor=exposures_by_factor))
        if var_observation is not None:
            v, c, h = var_observation
            alerts.extend(self.check_var(
                observed_var_kes=v, confidence=c, horizon_days=h))
        if es_observation is not None:
            v, c, h = es_observation
            alerts.extend(self.check_es(
                observed_es_kes=v, confidence=c, horizon_days=h))

        # Aggregate counts
        n_within = sum(
            1 for a in alerts
            if a.severity == BreachSeverity.WITHIN_LIMIT)
        n_warn = sum(
            1 for a in alerts if a.severity == BreachSeverity.WARN)
        n_breach = sum(
            1 for a in alerts if a.severity == BreachSeverity.BREACH)
        n_severe = sum(
            1 for a in alerts
            if a.severity == BreachSeverity.SEVERE_BREACH)
        summary = (
            f"{len(alerts)} limits checked; "
            f"{n_within} within / {n_warn} warn / "
            f"{n_breach} breach / {n_severe} severe")
        return MonitorReport(
            alerts=tuple(alerts),
            n_limits_checked=len(alerts),
            n_within=n_within, n_warn=n_warn,
            n_breach=n_breach, n_severe=n_severe,
            summary=summary)


# ════════════════════════════════════════════════════════════════════════
# Pre-built example limits — illustrative defaults for Ecobank Kenya
# ════════════════════════════════════════════════════════════════════════
# These are EXAMPLE limits per CBK PG/04. In production they would be
# board-approved and stored in the database. They illustrate the data
# shape and serve as fixtures for the integration tests.

DEFAULT_VAR_LIMIT_99_1D = RiskLimit(
    limit_id="VAR_99_1D_TRADING_BOOK",
    limit_type=LimitType.VAR_LIMIT,
    scope=LimitScope.PORTFOLIO,
    threshold_kes=Decimal("50000000"),    # KES 50m daily 99% VaR
    confidence=Decimal("0.99"),
    horizon_days=1,
    description=(
        "Trading-book daily 99% VaR limit per CBK PG/04 §4.2.a"),
    regulatory_source="CBK PG/04 + BCBS d352",
    framework_refs=("CBK PG/04 §4.2", "BCBS d352 §A.4"),
    approval_authority="BOARD",
    effective_date="2026-01-01",
    notes="Illustrative limit for v10.40 — actual figure board-set")

DEFAULT_ES_LIMIT_975_10D = RiskLimit(
    limit_id="ES_975_10D_TRADING_BOOK",
    limit_type=LimitType.ES_LIMIT,
    scope=LimitScope.PORTFOLIO,
    threshold_kes=Decimal("150000000"),   # KES 150m FRTB-IMA ES
    confidence=Decimal("0.975"),
    horizon_days=10,
    description=(
        "Trading-book 10-day 97.5% Expected Shortfall limit "
        "per BCBS d352 FRTB-IMA"),
    regulatory_source="BCBS d352 FRTB-IMA",
    framework_refs=("BCBS d352 §A.6.5",),
    approval_authority="BOARD",
    effective_date="2026-01-01")

DEFAULT_FX_CONCENTRATION_USD = RiskLimit(
    limit_id="CONC_FX_USDKES_NET",
    limit_type=LimitType.CONCENTRATION,
    scope=LimitScope.SINGLE_FACTOR,
    factor=RiskFactor.FX_USDKES,
    threshold_kes=Decimal("2000000000"),  # KES 2bn net USD/KES
    description="Net USD/KES exposure ceiling per CBK PG/04 §4.3",
    regulatory_source="CBK PG/04",
    framework_refs=("CBK PG/04 §4.3",),
    approval_authority="ALCO",
    effective_date="2026-01-01")

DEFAULT_FX_CLASS_LIMIT = RiskLimit(
    limit_id="CONC_FX_TOTAL",
    limit_type=LimitType.CONCENTRATION,
    scope=LimitScope.FACTOR_CLASS,
    factor_class=RiskFactorClass.FOREIGN_EXCHANGE,
    threshold_kes=Decimal("5000000000"),   # KES 5bn total FX
    description=(
        "Aggregate foreign-exchange exposure (all currency pairs) "
        "per CBK PG/04 §4.3 net-open-position rules"),
    regulatory_source="CBK PG/04",
    framework_refs=("CBK PG/04 §4.3", "BCBS d352 §A.5.2"),
    approval_authority="ALCO",
    effective_date="2026-01-01")

DEFAULT_EQUITY_CLASS_LIMIT = RiskLimit(
    limit_id="CONC_EQUITY_TOTAL",
    limit_type=LimitType.CONCENTRATION,
    scope=LimitScope.FACTOR_CLASS,
    factor_class=RiskFactorClass.EQUITY,
    threshold_kes=Decimal("1000000000"),   # KES 1bn total equity
    description="Aggregate equity exposure across all indices",
    regulatory_source="CBK PG/04 + internal",
    framework_refs=("CBK PG/04 §4.4",),
    approval_authority="ALCO",
    effective_date="2026-01-01")

ALL_DEFAULT_LIMITS: Tuple[RiskLimit, ...] = (
    DEFAULT_VAR_LIMIT_99_1D,
    DEFAULT_ES_LIMIT_975_10D,
    DEFAULT_FX_CONCENTRATION_USD,
    DEFAULT_FX_CLASS_LIMIT,
    DEFAULT_EQUITY_CLASS_LIMIT,
)


def build_default_registry() -> LimitRegistry:
    """Build a LimitRegistry pre-populated with the example limits.

    Provided as a convenience for tests, scenarios, and demos. In
    production the registry would be loaded from the database.
    """
    reg = LimitRegistry()
    for limit in ALL_DEFAULT_LIMITS:
        reg.register(limit)
    return reg


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_riskLimit_validates_threshold_positive():
    try:
        RiskLimit(
            limit_id="bad",
            limit_type=LimitType.CONCENTRATION,
            scope=LimitScope.SINGLE_FACTOR,
            threshold_kes=Decimal("0"),
            factor=RiskFactor.FX_USDKES,
            description="x",
            regulatory_source="x",
            framework_refs=(),
            approval_authority="ALCO",
            effective_date="2026-01-01")
        assert False, "should have raised"
    except ValueError:
        pass


def _test_riskLimit_validates_scope_consistency():
    """SINGLE_FACTOR requires factor; FACTOR_CLASS requires class."""
    try:
        RiskLimit(
            limit_id="bad",
            limit_type=LimitType.CONCENTRATION,
            scope=LimitScope.SINGLE_FACTOR,
            threshold_kes=Decimal("100"),
            description="x", regulatory_source="x",
            framework_refs=(), approval_authority="ALCO",
            effective_date="2026-01-01")
        assert False
    except ValueError:
        pass


def _test_var_limit_requires_confidence_horizon():
    try:
        RiskLimit(
            limit_id="bad_var",
            limit_type=LimitType.VAR_LIMIT,
            scope=LimitScope.PORTFOLIO,
            threshold_kes=Decimal("1000000"),
            description="x", regulatory_source="x",
            framework_refs=(), approval_authority="BOARD",
            effective_date="2026-01-01",
            # missing confidence + horizon_days
        )
        assert False
    except ValueError:
        pass


def _test_concentration_cannot_be_portfolio_scope():
    try:
        RiskLimit(
            limit_id="bad_conc",
            limit_type=LimitType.CONCENTRATION,
            scope=LimitScope.PORTFOLIO,
            threshold_kes=Decimal("1000000"),
            description="x", regulatory_source="x",
            framework_refs=(), approval_authority="ALCO",
            effective_date="2026-01-01")
        assert False
    except ValueError:
        pass


def _test_registry_register_and_get():
    reg = LimitRegistry()
    reg.register(DEFAULT_VAR_LIMIT_99_1D)
    assert reg.is_active("VAR_99_1D_TRADING_BOOK")
    fetched = reg.get("VAR_99_1D_TRADING_BOOK")
    assert fetched.limit_id == "VAR_99_1D_TRADING_BOOK"


def _test_registry_double_register_raises():
    reg = LimitRegistry()
    reg.register(DEFAULT_VAR_LIMIT_99_1D)
    try:
        reg.register(DEFAULT_VAR_LIMIT_99_1D)
        assert False
    except ValueError:
        pass


def _test_registry_deactivate():
    reg = LimitRegistry()
    reg.register(DEFAULT_VAR_LIMIT_99_1D)
    reg.deactivate("VAR_99_1D_TRADING_BOOK")
    assert not reg.is_active("VAR_99_1D_TRADING_BOOK")
    # Still in storage, just not active
    assert reg.get("VAR_99_1D_TRADING_BOOK") is not None


def _test_registry_by_factor_includes_class_limits():
    reg = LimitRegistry()
    reg.register(DEFAULT_FX_CONCENTRATION_USD)    # SINGLE_FACTOR
    reg.register(DEFAULT_FX_CLASS_LIMIT)          # FACTOR_CLASS
    applicable = reg.by_factor(RiskFactor.FX_USDKES)
    assert len(applicable) == 2
    # Limits applicable to EUR/KES — only the class limit
    eur_apps = reg.by_factor(RiskFactor.FX_EURKES)
    assert len(eur_apps) == 1
    assert eur_apps[0].limit_id == "CONC_FX_TOTAL"


def _test_severity_classification():
    assert (_classify_severity(Decimal("50"))
            == BreachSeverity.WITHIN_LIMIT)
    assert (_classify_severity(Decimal("80"))
            == BreachSeverity.WARN)
    assert (_classify_severity(Decimal("99.99"))
            == BreachSeverity.WARN)
    assert (_classify_severity(Decimal("100"))
            == BreachSeverity.BREACH)
    assert (_classify_severity(Decimal("119.99"))
            == BreachSeverity.BREACH)
    assert (_classify_severity(Decimal("120"))
            == BreachSeverity.SEVERE_BREACH)
    assert (_classify_severity(Decimal("200"))
            == BreachSeverity.SEVERE_BREACH)


def _test_concentration_within_limit_emits_within_alert():
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    # USD exposure 1bn vs 2bn limit = 50%
    alerts = monitor.check_concentration(exposures_by_factor={
        RiskFactor.FX_USDKES: Decimal("1000000000"),
    })
    # We expect at least 2 alerts (single-factor + class limit)
    matching = [
        a for a in alerts
        if a.limit_id == "CONC_FX_USDKES_NET"]
    assert len(matching) == 1
    assert matching[0].severity == BreachSeverity.WITHIN_LIMIT
    assert matching[0].utilization_pct == Decimal("50.00")


def _test_concentration_breach_emits_breach_alert():
    reg = LimitRegistry()
    reg.register(DEFAULT_FX_CONCENTRATION_USD)
    monitor = LimitMonitor(reg)
    # USD exposure 2.5bn vs 2bn limit = 125% → SEVERE_BREACH
    alerts = monitor.check_concentration(exposures_by_factor={
        RiskFactor.FX_USDKES: Decimal("2500000000"),
    })
    assert len(alerts) == 1
    assert alerts[0].severity == BreachSeverity.SEVERE_BREACH
    assert alerts[0].utilization_pct == Decimal("125.00")


def _test_concentration_aggregates_across_factors_for_class_limit():
    """Sum of USD + EUR + GBP exposure should be checked against
    the FOREIGN_EXCHANGE class limit."""
    reg = LimitRegistry()
    reg.register(DEFAULT_FX_CLASS_LIMIT)    # KES 5bn class limit
    monitor = LimitMonitor(reg)
    # 3bn + 2bn + 1bn = 6bn total → 120% → SEVERE_BREACH
    alerts = monitor.check_concentration(exposures_by_factor={
        RiskFactor.FX_USDKES: Decimal("3000000000"),
        RiskFactor.FX_EURKES: Decimal("2000000000"),
        RiskFactor.FX_GBPKES: Decimal("1000000000"),
    })
    assert len(alerts) == 1
    assert alerts[0].severity == BreachSeverity.SEVERE_BREACH
    assert alerts[0].observed_kes == Decimal("6000000000")


def _test_var_limit_match_only_exact_confidence_horizon():
    reg = LimitRegistry()
    reg.register(DEFAULT_VAR_LIMIT_99_1D)    # 99%, 1-day
    monitor = LimitMonitor(reg)
    # 95% / 1-day VaR — does NOT match the 99%/1-day limit
    alerts_wrong_conf = monitor.check_var(
        observed_var_kes=Decimal("100000000"),
        confidence=Decimal("0.95"), horizon_days=1)
    assert len(alerts_wrong_conf) == 0
    # 99% / 10-day — also doesn't match the 1-day limit
    alerts_wrong_horizon = monitor.check_var(
        observed_var_kes=Decimal("100000000"),
        confidence=Decimal("0.99"), horizon_days=10)
    assert len(alerts_wrong_horizon) == 0
    # 99% / 1-day, 75m KES — matches; 75m / 50m = 150% → SEVERE
    alerts_match = monitor.check_var(
        observed_var_kes=Decimal("75000000"),
        confidence=Decimal("0.99"), horizon_days=1)
    assert len(alerts_match) == 1
    assert alerts_match[0].severity == BreachSeverity.SEVERE_BREACH


def _test_es_limit_breach():
    reg = LimitRegistry()
    reg.register(DEFAULT_ES_LIMIT_975_10D)    # 97.5%, 10-day, 150m
    monitor = LimitMonitor(reg)
    # 165m / 150m = 110% → BREACH
    alerts = monitor.check_es(
        observed_es_kes=Decimal("165000000"),
        confidence=Decimal("0.975"), horizon_days=10)
    assert len(alerts) == 1
    assert alerts[0].severity == BreachSeverity.BREACH


def _test_run_pass_aggregates_all_observations():
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    report = monitor.run_pass(
        exposures_by_factor={
            RiskFactor.FX_USDKES: Decimal("1500000000"),  # 75% of 2bn
        },
        var_observation=(
            Decimal("45000000"), Decimal("0.99"), 1),     # 90% of 50m
        es_observation=(
            Decimal("180000000"), Decimal("0.975"), 10),  # 120% → SEV
    )
    assert report.n_limits_checked >= 3
    assert report.n_severe >= 1   # ES at 120%
    assert report.n_warn >= 1     # VaR at 90%
    assert not report.is_clean()


def _test_alert_carries_full_triage_info():
    """Per Rule 1: every BreachAlert has all the fields needed."""
    reg = LimitRegistry()
    reg.register(DEFAULT_VAR_LIMIT_99_1D)
    monitor = LimitMonitor(reg)
    alerts = monitor.check_var(
        observed_var_kes=Decimal("60000000"),  # 120% → SEVERE
        confidence=Decimal("0.99"), horizon_days=1)
    assert len(alerts) == 1
    a = alerts[0]
    assert a.severity == BreachSeverity.SEVERE_BREACH
    assert a.observed_kes == Decimal("60000000")
    assert a.threshold_kes == Decimal("50000000")
    assert a.utilization_pct == Decimal("120.00")
    assert "Board" in a.escalation_target or "Board" in a.escalation_target.upper()
    assert "SEVERE" in a.suggested_action.upper()
    assert len(a.framework_refs) > 0


def _test_default_registry_has_5_limits():
    reg = build_default_registry()
    summary = reg.summary()
    assert summary["n_total"] == 5
    assert summary["n_active"] == 5
    assert summary["by_type"]["CONCENTRATION"] == 3
    assert summary["by_type"]["VAR_LIMIT"] == 1
    assert summary["by_type"]["ES_LIMIT"] == 1


def _test_alert_id_is_deterministic():
    """Same observation → same alert_id (for dedup)."""
    reg = LimitRegistry()
    reg.register(DEFAULT_VAR_LIMIT_99_1D)
    monitor = LimitMonitor(reg)
    a1 = monitor.check_var(
        observed_var_kes=Decimal("60000000"),
        confidence=Decimal("0.99"), horizon_days=1)[0]
    a2 = monitor.check_var(
        observed_var_kes=Decimal("60000000"),
        confidence=Decimal("0.99"), horizon_days=1)[0]
    assert a1.alert_id == a2.alert_id


def _test_negative_exposure_treated_as_absolute():
    """Net SHORT of 2.5bn USD = same magnitude as +2.5bn."""
    reg = LimitRegistry()
    reg.register(DEFAULT_FX_CONCENTRATION_USD)
    monitor = LimitMonitor(reg)
    alerts = monitor.check_concentration(exposures_by_factor={
        RiskFactor.FX_USDKES: Decimal("-2500000000"),
    })
    assert len(alerts) == 1
    assert alerts[0].observed_kes == Decimal("2500000000")
    assert alerts[0].severity == BreachSeverity.SEVERE_BREACH


def self_test() -> None:
    tests = [
        _test_riskLimit_validates_threshold_positive,
        _test_riskLimit_validates_scope_consistency,
        _test_var_limit_requires_confidence_horizon,
        _test_concentration_cannot_be_portfolio_scope,
        _test_registry_register_and_get,
        _test_registry_double_register_raises,
        _test_registry_deactivate,
        _test_registry_by_factor_includes_class_limits,
        _test_severity_classification,
        _test_concentration_within_limit_emits_within_alert,
        _test_concentration_breach_emits_breach_alert,
        _test_concentration_aggregates_across_factors_for_class_limit,
        _test_var_limit_match_only_exact_confidence_horizon,
        _test_es_limit_breach,
        _test_run_pass_aggregates_all_observations,
        _test_alert_carries_full_triage_info,
        _test_default_registry_has_5_limits,
        _test_alert_id_is_deterministic,
        _test_negative_exposure_treated_as_absolute,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ market_risk_limits self-test: {len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ market_risk_limits self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

"""utils/mlops_retraining_scheduler.py — v10.83: MLOps Retraining
Scheduler.

ENH-283 — MLOps Retraining Scheduler. Cat B — ml_governance arc 3/N.

Diagnostic engine that consumes three signal streams and surfaces
"retraining is due" recommendations against caller-supplied policies.
The three signal streams:

  1. Model freshness — age of the active model since training (the
     caller passes the registered active entry from ENH-281)
  2. Override rate trend — operator override rate from ENH-282 over
     a rolling window (caller passes the OverrideRateMetric)
  3. Distribution drift — PSI / KS / Wasserstein from the existing
     model_governance arc at G124 (caller passes the drift metric)

This engine is the "retraining due?" question — orthogonal to:
  - ENH-281 model registry (the "what's deployed?" question)
  - ENH-282 adjudication log (the "what did operators decide?" question)
  - model_governance arc at G124 (the "is the model SAFE?" question)

The four ml_governance arc engines + model_governance arc together
form the closed loop where production observation becomes retraining
signal becomes new candidate becomes new active. Operators trigger
every transition. Engines surface signals.

Five capabilities:

  1. evaluate_freshness — given an active model entry + caller-
     supplied FreshnessPolicy (warning_age_days, stale_age_days),
     compute current age and return FreshnessAssessment with severity
     (FRESH / WARNING / STALE / INSUFFICIENT_DATA when no training
     completion timestamp). Per Rule 1, INSUFFICIENT_DATA surfaces
     when training_completed_at_iso is missing — engine never
     fabricates an age.

  2. evaluate_override_signal — given a current override rate +
     caller-supplied OverrideThresholds (warning_rate,
     critical_rate), return OverrideSignalAssessment with severity
     (OK / WARNING / CRITICAL / INSUFFICIENT_DATA when rate is None,
     i.e. no decided records). Per Rule 1, INSUFFICIENT_DATA
     preserves the no-signal state from ENH-282 rather than
     defaulting to OK.

  3. evaluate_drift_signal — given a current drift metric (PSI / KS
     / Wasserstein) + caller-supplied DriftThresholds (warning_value,
     critical_value), return DriftSignalAssessment with severity.
     Per Rule 7, engine never decides which drift method to use — caller
     supplies the metric value computed by their preferred method
     from utils.model_governance.

  4. compute_retraining_recommendation — orchestrator. Takes all
     three signals + caller-supplied RetrainingPolicy (which signals
     are required + how to combine them). Returns
     RetrainingRecommendation with outcome (DUE / SOON / NOT_YET /
     INSUFFICIENT_DATA), contributing severity per signal,
     overall_severity, and explicit rationale. Per Rule 1, every
     contributing signal surfaces; per Rule 7, engine never auto-
     triggers retraining.

  5. build_retraining_calendar — given a fleet of (model_id,
     active_entry, signals, policy) tuples, returns a calendar of
     RetrainingCalendarEntry per model sorted by urgency (DUE first,
     then SOON, then NOT_YET, then INSUFFICIENT_DATA). Useful for
     fleet-level capacity planning across the ML team. Per Rule 7,
     calendar is a view; engine never schedules execution.

Per Rule 7, engine NEVER:
  - auto-triggers retraining (operator + ML team execute)
  - auto-promotes a candidate (ENH-281 territory)
  - auto-deprecates an active (ENH-281 territory)
  - reads ENH-281 / ENH-282 / model_governance state directly —
    caller integrates outputs
  - persists scheduler state (caller stores recommendations if
    persistence is desired)
  - decides which drift method (PSI vs KS vs Wasserstein) to use —
    caller supplies the chosen metric
  - mutates inputs

Per Rule 1, every output surfaces inputs + intermediates + outputs +
framework_refs. All result dataclasses are frozen.

Caller-supplied data discipline (matches ENH-274 / ENH-278 / ENH-271
/ ENH-276 / ENH-281 / ENH-282 pattern): registered model entry +
signal values + policies + thresholds all caller-supplied; engine
bundles no defaults except a single conservative
DEFAULT_RETRAINING_POLICY for first-use convenience (which caller
REPLACES via constructor).

Pure stdlib runtime.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import (
    Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "MLOpsRetrainingSchedulerEngine implements ENH-283 — diagnostic "
    "engine that consumes freshness + override + drift signals and "
    "surfaces retraining-due recommendations against caller-supplied "
    "policies. Sits in the ml_governance arc as the integration "
    "point that combines outputs from ENH-281 (registry — for "
    "active model age) + ENH-282 (adjudication — for override "
    "rate) + model_governance G124 (drift detection — for "
    "distribution drift). Pure stdlib. Per Rule 1, every output "
    "surfaces all contributing signals + rationale + framework_refs. "
    "Per Rule 7, engine DIAGNOSTIC ONLY — never auto-triggers "
    "retraining, never auto-promotes, never auto-deprecates, never "
    "reads other engines directly (caller integrates), never "
    "persists scheduler state, never decides drift method (PSI vs "
    "KS vs Wasserstein — caller supplies chosen metric)."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class FreshnessSeverity(Enum):
    FRESH = "FRESH"                          # age < warning
    WARNING = "WARNING"                      # warning ≤ age < stale
    STALE = "STALE"                          # age ≥ stale
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # missing timestamp


class OverrideSignalSeverity(Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # rate is None


class DriftSignalSeverity(Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RetrainingOutcome(Enum):
    DUE = "DUE"                              # at least one signal CRITICAL
    SOON = "SOON"                            # at least one WARNING
    NOT_YET = "NOT_YET"                      # all OK / FRESH
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # required signals missing


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FreshnessPolicy:
    """Caller-supplied per-model freshness thresholds."""
    warning_age_days: int   # age ≥ this triggers WARNING
    stale_age_days: int     # age ≥ this triggers STALE


@dataclass(frozen=True)
class OverrideThresholds:
    """Caller-supplied override-rate thresholds."""
    warning_rate: Decimal      # rate ≥ this triggers WARNING
    critical_rate: Decimal     # rate ≥ this triggers CRITICAL


@dataclass(frozen=True)
class DriftThresholds:
    """Caller-supplied drift-metric thresholds. Caller chooses the
    metric (PSI / KS / Wasserstein); thresholds are calibrated to
    that choice. Engine doesn't know which metric this is."""
    warning_value: Decimal
    critical_value: Decimal
    metric_name: str   # for provenance only — e.g. "PSI" / "KS" / "WASSERSTEIN"


@dataclass(frozen=True)
class RetrainingPolicy:
    """Caller-supplied policy for combining the three signals."""
    require_freshness: bool = True
    require_override_signal: bool = False
    require_drift_signal: bool = False
    # If a "required" signal returns INSUFFICIENT_DATA, the overall
    # outcome is INSUFFICIENT_DATA. If a non-required signal is
    # missing, it's silently skipped.


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FreshnessAssessment:
    model_id: str
    model_version: str
    age_days: Optional[int]            # None if INSUFFICIENT_DATA
    severity: FreshnessSeverity
    rationale: str
    policy: FreshnessPolicy
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class OverrideSignalAssessment:
    model_id: str
    current_rate: Optional[Decimal]
    severity: OverrideSignalSeverity
    rationale: str
    thresholds: OverrideThresholds
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class DriftSignalAssessment:
    model_id: str
    metric_name: str
    current_value: Optional[Decimal]
    severity: DriftSignalSeverity
    rationale: str
    thresholds: DriftThresholds
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class RetrainingRecommendation:
    model_id: str
    model_version: str
    outcome: RetrainingOutcome
    freshness: Optional[FreshnessAssessment]
    override_signal: Optional[OverrideSignalAssessment]
    drift_signal: Optional[DriftSignalAssessment]
    rationale: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class RetrainingCalendarEntry:
    model_id: str
    recommendation: RetrainingRecommendation
    urgency_rank: int   # 0=DUE, 1=SOON, 2=NOT_YET, 3=INSUFFICIENT_DATA


@dataclass(frozen=True)
class RetrainingCalendar:
    entries: Tuple[RetrainingCalendarEntry, ...]
    summary_due: int
    summary_soon: int
    summary_not_yet: int
    summary_insufficient: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class MLOpsRetrainingSchedulerEngine:
    """Diagnostic retraining scheduler. Consumes signals; surfaces
    recommendations. Never auto-triggers."""

    def __init__(
        self,
        default_policy: Optional[RetrainingPolicy] = None,
    ) -> None:
        # Single conservative default — caller REPLACES via constructor
        if default_policy is None:
            self._default_policy = RetrainingPolicy(
                require_freshness=True,
                require_override_signal=False,
                require_drift_signal=False)
        else:
            self._default_policy = default_policy

    # ─── 1. Evaluate freshness ─────────────────────────────────
    def evaluate_freshness(
        self,
        model_id: str,
        model_version: str,
        training_completed_at_iso: Optional[str],
        as_of_iso: str,
        policy: FreshnessPolicy,
    ) -> FreshnessAssessment:
        """Compute model age and classify against policy thresholds.
        Per Rule 1, INSUFFICIENT_DATA surfaces explicitly when
        training_completed_at_iso is missing — engine never
        fabricates an age."""
        if (training_completed_at_iso is None
            or not training_completed_at_iso.strip()
        ):
            return FreshnessAssessment(
                model_id=model_id,
                model_version=model_version,
                age_days=None,
                severity=(
                    FreshnessSeverity.INSUFFICIENT_DATA),
                rationale=(
                    "training_completed_at_iso is missing — "
                    "engine cannot compute age. Per Rule 1, "
                    "engine never fabricates a value; caller "
                    "must populate the timestamp at training "
                    "time. (This is the canonical case for "
                    "models registered before training "
                    "instrumentation was added.)"),
                policy=policy,
                framework_refs=self._fr_evaluate_freshness())

        try:
            train_dt = self._parse_iso(
                training_completed_at_iso)
            as_of_dt = self._parse_iso(as_of_iso)
        except ValueError as e:
            return FreshnessAssessment(
                model_id=model_id,
                model_version=model_version,
                age_days=None,
                severity=(
                    FreshnessSeverity.INSUFFICIENT_DATA),
                rationale=(
                    f"ISO 8601 parse failure: {e}. Engine "
                    f"surfaces INSUFFICIENT_DATA rather than "
                    f"fabricating an age."),
                policy=policy,
                framework_refs=self._fr_evaluate_freshness())

        age_days = (as_of_dt - train_dt).days

        if age_days >= policy.stale_age_days:
            severity = FreshnessSeverity.STALE
            rationale = (
                f"Age {age_days} days ≥ stale threshold "
                f"{policy.stale_age_days} days. Model is "
                f"STALE per caller-supplied policy.")
        elif age_days >= policy.warning_age_days:
            severity = FreshnessSeverity.WARNING
            rationale = (
                f"Age {age_days} days ≥ warning threshold "
                f"{policy.warning_age_days} days but < stale "
                f"threshold {policy.stale_age_days} days.")
        else:
            severity = FreshnessSeverity.FRESH
            rationale = (
                f"Age {age_days} days < warning threshold "
                f"{policy.warning_age_days} days. Model is "
                f"FRESH.")

        return FreshnessAssessment(
            model_id=model_id,
            model_version=model_version,
            age_days=age_days,
            severity=severity,
            rationale=rationale,
            policy=policy,
            framework_refs=self._fr_evaluate_freshness())

    # ─── 2. Evaluate override signal ───────────────────────────
    def evaluate_override_signal(
        self,
        model_id: str,
        current_rate: Optional[Decimal],
        thresholds: OverrideThresholds,
    ) -> OverrideSignalAssessment:
        """Classify override rate against caller-supplied thresholds.
        Per Rule 1, INSUFFICIENT_DATA preserves the no-signal state
        from ENH-282 (rate is None when no decided records) rather
        than defaulting to OK."""
        if current_rate is None:
            return OverrideSignalAssessment(
                model_id=model_id,
                current_rate=None,
                severity=(
                    OverrideSignalSeverity.INSUFFICIENT_DATA),
                rationale=(
                    "Override rate is None — ENH-282 surfaced "
                    "no decided records in the window. "
                    "Engine preserves the no-signal state per "
                    "Rule 1 rather than defaulting to OK "
                    "(absence of data is not absence of "
                    "concern; operator may need to investigate "
                    "why no decisions were made)."),
                thresholds=thresholds,
                framework_refs=(
                    self._fr_evaluate_override_signal()))

        if current_rate >= thresholds.critical_rate:
            severity = OverrideSignalSeverity.CRITICAL
            rationale = (
                f"Override rate {current_rate} ≥ critical "
                f"threshold {thresholds.critical_rate}. "
                f"Operator trust eroding — strong retraining "
                f"signal.")
        elif current_rate >= thresholds.warning_rate:
            severity = OverrideSignalSeverity.WARNING
            rationale = (
                f"Override rate {current_rate} ≥ warning "
                f"threshold {thresholds.warning_rate} but < "
                f"critical {thresholds.critical_rate}.")
        else:
            severity = OverrideSignalSeverity.OK
            rationale = (
                f"Override rate {current_rate} < warning "
                f"threshold {thresholds.warning_rate}. "
                f"Signal OK.")

        return OverrideSignalAssessment(
            model_id=model_id,
            current_rate=current_rate,
            severity=severity,
            rationale=rationale,
            thresholds=thresholds,
            framework_refs=self._fr_evaluate_override_signal())

    # ─── 3. Evaluate drift signal ──────────────────────────────
    def evaluate_drift_signal(
        self,
        model_id: str,
        current_value: Optional[Decimal],
        thresholds: DriftThresholds,
    ) -> DriftSignalAssessment:
        """Classify drift metric against caller-supplied thresholds.
        Per Rule 7, engine never decides which drift method to use —
        caller supplies the metric value computed by their preferred
        method (PSI / KS / Wasserstein from utils.model_governance)
        and thresholds calibrated to that choice."""
        if current_value is None:
            return DriftSignalAssessment(
                model_id=model_id,
                metric_name=thresholds.metric_name,
                current_value=None,
                severity=(
                    DriftSignalSeverity.INSUFFICIENT_DATA),
                rationale=(
                    f"Drift metric ({thresholds.metric_name}) "
                    f"is None — caller did not supply a "
                    f"current measurement. Engine surfaces "
                    f"INSUFFICIENT_DATA per Rule 1."),
                thresholds=thresholds,
                framework_refs=self._fr_evaluate_drift_signal())

        if current_value >= thresholds.critical_value:
            severity = DriftSignalSeverity.CRITICAL
            rationale = (
                f"{thresholds.metric_name} = {current_value} "
                f"≥ critical threshold "
                f"{thresholds.critical_value}. Distribution "
                f"shift severe — strong retraining signal.")
        elif current_value >= thresholds.warning_value:
            severity = DriftSignalSeverity.WARNING
            rationale = (
                f"{thresholds.metric_name} = {current_value} "
                f"≥ warning threshold "
                f"{thresholds.warning_value} but < critical "
                f"{thresholds.critical_value}.")
        else:
            severity = DriftSignalSeverity.OK
            rationale = (
                f"{thresholds.metric_name} = {current_value} "
                f"< warning threshold "
                f"{thresholds.warning_value}. Signal OK.")

        return DriftSignalAssessment(
            model_id=model_id,
            metric_name=thresholds.metric_name,
            current_value=current_value,
            severity=severity,
            rationale=rationale,
            thresholds=thresholds,
            framework_refs=self._fr_evaluate_drift_signal())

    # ─── 4. Compute retraining recommendation ──────────────────
    def compute_retraining_recommendation(
        self,
        model_id: str,
        model_version: str,
        freshness: Optional[FreshnessAssessment],
        override_signal: Optional[OverrideSignalAssessment],
        drift_signal: Optional[DriftSignalAssessment],
        policy: Optional[RetrainingPolicy] = None,
    ) -> RetrainingRecommendation:
        """Orchestrator. Combines the three signals + caller-supplied
        policy. Per Rule 1, every contributing signal surfaces.
        Per Rule 7, engine never auto-triggers retraining."""
        active_policy = policy or self._default_policy

        # Check INSUFFICIENT_DATA on required signals
        rationale_parts: list = []
        insufficient = False

        if active_policy.require_freshness:
            if freshness is None or (
                freshness.severity
                == FreshnessSeverity.INSUFFICIENT_DATA
            ):
                insufficient = True
                rationale_parts.append(
                    "freshness signal required by policy but "
                    "INSUFFICIENT_DATA")
        if active_policy.require_override_signal:
            if override_signal is None or (
                override_signal.severity
                == OverrideSignalSeverity.INSUFFICIENT_DATA
            ):
                insufficient = True
                rationale_parts.append(
                    "override signal required by policy but "
                    "INSUFFICIENT_DATA")
        if active_policy.require_drift_signal:
            if drift_signal is None or (
                drift_signal.severity
                == DriftSignalSeverity.INSUFFICIENT_DATA
            ):
                insufficient = True
                rationale_parts.append(
                    "drift signal required by policy but "
                    "INSUFFICIENT_DATA")

        if insufficient:
            return RetrainingRecommendation(
                model_id=model_id,
                model_version=model_version,
                outcome=RetrainingOutcome.INSUFFICIENT_DATA,
                freshness=freshness,
                override_signal=override_signal,
                drift_signal=drift_signal,
                rationale=(
                    "Required signal(s) missing: "
                    + "; ".join(rationale_parts)
                    + ". Per Rule 1, engine surfaces "
                    "INSUFFICIENT_DATA rather than "
                    "defaulting to NOT_YET."),
                framework_refs=(
                    self._fr_compute_recommendation()))

        # Aggregate severity across present signals
        has_critical = False
        has_warning = False
        contrib: list = []

        if freshness is not None:
            contrib.append(
                f"freshness={freshness.severity.value}")
            if freshness.severity == FreshnessSeverity.STALE:
                has_critical = True
            elif freshness.severity == FreshnessSeverity.WARNING:
                has_warning = True
        if override_signal is not None:
            contrib.append(
                f"override={override_signal.severity.value}")
            if override_signal.severity == (
                OverrideSignalSeverity.CRITICAL
            ):
                has_critical = True
            elif override_signal.severity == (
                OverrideSignalSeverity.WARNING
            ):
                has_warning = True
        if drift_signal is not None:
            contrib.append(
                f"drift={drift_signal.severity.value}")
            if drift_signal.severity == (
                DriftSignalSeverity.CRITICAL
            ):
                has_critical = True
            elif drift_signal.severity == (
                DriftSignalSeverity.WARNING
            ):
                has_warning = True

        if has_critical:
            outcome = RetrainingOutcome.DUE
            outcome_msg = (
                "Retraining DUE — at least one signal at "
                "CRITICAL/STALE severity.")
        elif has_warning:
            outcome = RetrainingOutcome.SOON
            outcome_msg = (
                "Retraining SOON — at least one signal at "
                "WARNING severity but no CRITICAL.")
        else:
            outcome = RetrainingOutcome.NOT_YET
            outcome_msg = (
                "Retraining NOT_YET — all signals OK / FRESH.")

        return RetrainingRecommendation(
            model_id=model_id,
            model_version=model_version,
            outcome=outcome,
            freshness=freshness,
            override_signal=override_signal,
            drift_signal=drift_signal,
            rationale=(
                f"{outcome_msg} Contributing signals: "
                + ", ".join(contrib) + "."),
            framework_refs=self._fr_compute_recommendation())

    # ─── 5. Build retraining calendar ──────────────────────────
    def build_retraining_calendar(
        self,
        recommendations: Sequence[RetrainingRecommendation],
    ) -> RetrainingCalendar:
        """Sort caller-supplied recommendations by urgency for
        fleet-level capacity planning. Per Rule 7, calendar is a
        view; engine never schedules execution."""
        rank_map = {
            RetrainingOutcome.DUE: 0,
            RetrainingOutcome.SOON: 1,
            RetrainingOutcome.NOT_YET: 2,
            RetrainingOutcome.INSUFFICIENT_DATA: 3,
        }
        entries = tuple(
            sorted(
                (RetrainingCalendarEntry(
                    model_id=r.model_id,
                    recommendation=r,
                    urgency_rank=rank_map[r.outcome])
                 for r in recommendations),
                key=lambda e: (e.urgency_rank, e.model_id)))

        summary_due = sum(
            1 for e in entries if e.urgency_rank == 0)
        summary_soon = sum(
            1 for e in entries if e.urgency_rank == 1)
        summary_not_yet = sum(
            1 for e in entries if e.urgency_rank == 2)
        summary_insufficient = sum(
            1 for e in entries if e.urgency_rank == 3)

        return RetrainingCalendar(
            entries=entries,
            summary_due=summary_due,
            summary_soon=summary_soon,
            summary_not_yet=summary_not_yet,
            summary_insufficient=summary_insufficient,
            framework_refs=(
                "ENH-283 §build_retraining_calendar",
                "Per Rule 7 — calendar is a view, not a "
                "schedule; engine never executes retraining. "
                "ML team uses the calendar for capacity "
                "planning; operator decides when to trigger.",
                "Per Rule 1 — summary counts surface "
                "alongside individual entries (operations "
                "sees both rollup and per-model detail)",
            ),
        )

    # ─── Helpers ───────────────────────────────────────────────
    @staticmethod
    def _parse_iso(s: str) -> datetime:
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)

    @staticmethod
    def _fr_evaluate_freshness() -> Tuple[str, ...]:
        return (
            "ENH-283 §evaluate_freshness",
            "Per Rule 1 — INSUFFICIENT_DATA surfaces "
            "explicitly when training_completed_at_iso "
            "missing or unparseable; engine never fabricates "
            "an age",
            "Per Rule 7 — engine surfaces severity; never "
            "auto-triggers retraining (operator + ML team "
            "execute)",
            "Microsoft MLOps Maturity Model (2023) — Stage 4 "
            "Continuous Training: model freshness as policy-"
            "driven trigger",
        )

    @staticmethod
    def _fr_evaluate_override_signal() -> Tuple[str, ...]:
        return (
            "ENH-283 §evaluate_override_signal",
            "Caller integrates ENH-282 OverrideRateMetric "
            "into this engine — engine bundles no override "
            "computation; per caller-supplied data discipline",
            "Per Rule 1 — INSUFFICIENT_DATA preserved when "
            "rate is None (no decided records in window) "
            "rather than defaulting to OK",
            "Per Rule 7 — engine surfaces severity; never "
            "auto-triggers retraining",
        )

    @staticmethod
    def _fr_evaluate_drift_signal() -> Tuple[str, ...]:
        return (
            "ENH-283 §evaluate_drift_signal",
            "Caller integrates utils.model_governance drift "
            "detection (PSI / KS / Wasserstein at G124) into "
            "this engine — engine never decides which method; "
            "caller supplies chosen metric + thresholds "
            "calibrated to that method",
            "Per Rule 1 — INSUFFICIENT_DATA preserved when "
            "metric is None",
            "Per Rule 7 — engine surfaces severity; never "
            "auto-triggers retraining",
            "Federal Reserve SR 11-7 §V — model performance "
            "monitoring with distribution drift as trigger",
            "Population Stability Index (Siddiqi 2017) + "
            "Kolmogorov-Smirnov (1933/1948) + Wasserstein "
            "(Vaserstein 1969) — caller chooses",
        )

    @staticmethod
    def _fr_compute_recommendation() -> Tuple[str, ...]:
        return (
            "ENH-283 §compute_retraining_recommendation",
            "Combination logic: any CRITICAL/STALE → DUE; "
            "any WARNING → SOON; all OK/FRESH → NOT_YET. "
            "Required signals missing → INSUFFICIENT_DATA.",
            "Per Rule 1 — every contributing signal surfaces "
            "in rationale + the assessment dataclasses are "
            "preserved on the recommendation (operator sees "
            "the full picture)",
            "Per Rule 7 — engine surfaces recommendation; "
            "never auto-triggers retraining (operator + ML "
            "team execute the next training run, which "
            "produces a candidate registered via ENH-281)",
            "Microsoft MLOps Maturity Model (2023) — Stage 4 "
            "trigger combination: temporal + performance + "
            "drift",
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

# ─── Freshness tests ───────────────────────────────────────────

def _test_freshness_fresh():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_freshness(
        model_id="m", model_version="1.0",
        training_completed_at_iso="2026-04-25T00:00:00Z",
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    assert a.severity == FreshnessSeverity.FRESH
    assert a.age_days == 6


def _test_freshness_warning():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_freshness(
        model_id="m", model_version="1.0",
        training_completed_at_iso="2026-03-01T00:00:00Z",
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    # ~61 days
    assert a.severity == FreshnessSeverity.WARNING


def _test_freshness_stale():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_freshness(
        model_id="m", model_version="1.0",
        training_completed_at_iso="2025-11-01T00:00:00Z",
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    # ~181 days
    assert a.severity == FreshnessSeverity.STALE


def _test_freshness_insufficient():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_freshness(
        model_id="m", model_version="1.0",
        training_completed_at_iso=None,
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    assert a.severity == (
        FreshnessSeverity.INSUFFICIENT_DATA)
    assert a.age_days is None


# ─── Override signal tests ─────────────────────────────────────

def _test_override_ok():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_override_signal(
        model_id="m",
        current_rate=Decimal("0.05"),
        thresholds=OverrideThresholds(
            warning_rate=Decimal("0.20"),
            critical_rate=Decimal("0.40")))
    assert a.severity == OverrideSignalSeverity.OK


def _test_override_warning():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_override_signal(
        model_id="m",
        current_rate=Decimal("0.25"),
        thresholds=OverrideThresholds(
            warning_rate=Decimal("0.20"),
            critical_rate=Decimal("0.40")))
    assert a.severity == OverrideSignalSeverity.WARNING


def _test_override_critical():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_override_signal(
        model_id="m",
        current_rate=Decimal("0.50"),
        thresholds=OverrideThresholds(
            warning_rate=Decimal("0.20"),
            critical_rate=Decimal("0.40")))
    assert a.severity == OverrideSignalSeverity.CRITICAL


def _test_override_insufficient():
    """Rate=None preserved as INSUFFICIENT_DATA, not OK."""
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_override_signal(
        model_id="m",
        current_rate=None,
        thresholds=OverrideThresholds(
            warning_rate=Decimal("0.20"),
            critical_rate=Decimal("0.40")))
    assert a.severity == (
        OverrideSignalSeverity.INSUFFICIENT_DATA)


# ─── Drift signal tests ────────────────────────────────────────

def _test_drift_psi_ok():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_drift_signal(
        model_id="m",
        current_value=Decimal("0.05"),  # PSI < 0.1 = stable
        thresholds=DriftThresholds(
            warning_value=Decimal("0.10"),
            critical_value=Decimal("0.25"),
            metric_name="PSI"))
    assert a.severity == DriftSignalSeverity.OK


def _test_drift_psi_critical():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_drift_signal(
        model_id="m",
        current_value=Decimal("0.30"),  # PSI > 0.25 = severe
        thresholds=DriftThresholds(
            warning_value=Decimal("0.10"),
            critical_value=Decimal("0.25"),
            metric_name="PSI"))
    assert a.severity == DriftSignalSeverity.CRITICAL


def _test_drift_metric_name_preserved():
    """Engine doesn't decide drift method; preserves caller's choice."""
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_drift_signal(
        model_id="m",
        current_value=Decimal("0.15"),
        thresholds=DriftThresholds(
            warning_value=Decimal("0.10"),
            critical_value=Decimal("0.25"),
            metric_name="WASSERSTEIN"))
    assert a.metric_name == "WASSERSTEIN"


# ─── Recommendation orchestrator tests ─────────────────────────

def _test_recommend_due_freshness_critical():
    """STALE freshness alone → DUE."""
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = FreshnessAssessment(
        model_id="m", model_version="1.0",
        age_days=200,
        severity=FreshnessSeverity.STALE,
        rationale="stale",
        policy=FreshnessPolicy(30, 90),
        framework_refs=())
    r = eng.compute_retraining_recommendation(
        model_id="m", model_version="1.0",
        freshness=fresh,
        override_signal=None,
        drift_signal=None,
        policy=RetrainingPolicy(require_freshness=True))
    assert r.outcome == RetrainingOutcome.DUE


def _test_recommend_soon_only_warning():
    """WARNING + OK → SOON."""
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = FreshnessAssessment(
        model_id="m", model_version="1.0",
        age_days=45,
        severity=FreshnessSeverity.WARNING,
        rationale="warn",
        policy=FreshnessPolicy(30, 90),
        framework_refs=())
    override = OverrideSignalAssessment(
        model_id="m", current_rate=Decimal("0.05"),
        severity=OverrideSignalSeverity.OK,
        rationale="ok",
        thresholds=OverrideThresholds(
            Decimal("0.20"), Decimal("0.40")),
        framework_refs=())
    r = eng.compute_retraining_recommendation(
        model_id="m", model_version="1.0",
        freshness=fresh,
        override_signal=override,
        drift_signal=None,
        policy=RetrainingPolicy(require_freshness=True))
    assert r.outcome == RetrainingOutcome.SOON


def _test_recommend_not_yet_all_ok():
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = FreshnessAssessment(
        model_id="m", model_version="1.0",
        age_days=10,
        severity=FreshnessSeverity.FRESH,
        rationale="ok",
        policy=FreshnessPolicy(30, 90),
        framework_refs=())
    r = eng.compute_retraining_recommendation(
        model_id="m", model_version="1.0",
        freshness=fresh,
        override_signal=None,
        drift_signal=None,
        policy=RetrainingPolicy(require_freshness=True))
    assert r.outcome == RetrainingOutcome.NOT_YET


def _test_recommend_insufficient_required_missing():
    """Required signal returns INSUFFICIENT_DATA → outcome
    INSUFFICIENT_DATA."""
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = FreshnessAssessment(
        model_id="m", model_version="1.0",
        age_days=None,
        severity=FreshnessSeverity.INSUFFICIENT_DATA,
        rationale="missing timestamp",
        policy=FreshnessPolicy(30, 90),
        framework_refs=())
    r = eng.compute_retraining_recommendation(
        model_id="m", model_version="1.0",
        freshness=fresh,
        override_signal=None,
        drift_signal=None,
        policy=RetrainingPolicy(require_freshness=True))
    assert r.outcome == (
        RetrainingOutcome.INSUFFICIENT_DATA)


def _test_recommend_combined_all_three():
    """All three signals at CRITICAL → DUE; rationale lists all."""
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = FreshnessAssessment(
        "m", "1.0", 200,
        FreshnessSeverity.STALE, "stale",
        FreshnessPolicy(30, 90), ())
    override = OverrideSignalAssessment(
        "m", Decimal("0.50"),
        OverrideSignalSeverity.CRITICAL, "high",
        OverrideThresholds(
            Decimal("0.20"), Decimal("0.40")), ())
    drift = DriftSignalAssessment(
        "m", "PSI", Decimal("0.30"),
        DriftSignalSeverity.CRITICAL, "drift",
        DriftThresholds(
            Decimal("0.10"), Decimal("0.25"), "PSI"), ())
    r = eng.compute_retraining_recommendation(
        model_id="m", model_version="1.0",
        freshness=fresh,
        override_signal=override,
        drift_signal=drift,
        policy=RetrainingPolicy(
            require_freshness=True,
            require_override_signal=True,
            require_drift_signal=True))
    assert r.outcome == RetrainingOutcome.DUE
    # Rule 1 — all three contributions surface in rationale
    assert "freshness=" in r.rationale
    assert "override=" in r.rationale
    assert "drift=" in r.rationale


def _test_recommend_non_required_missing_silently_skipped():
    """Non-required signal=None → silently skipped (only the
    required ones are evaluated for INSUFFICIENT_DATA)."""
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = FreshnessAssessment(
        "m", "1.0", 10, FreshnessSeverity.FRESH, "fresh",
        FreshnessPolicy(30, 90), ())
    r = eng.compute_retraining_recommendation(
        model_id="m", model_version="1.0",
        freshness=fresh,
        override_signal=None,
        drift_signal=None,
        policy=RetrainingPolicy(
            require_freshness=True,
            require_override_signal=False,  # not required
            require_drift_signal=False))
    assert r.outcome == RetrainingOutcome.NOT_YET


# ─── Calendar tests ────────────────────────────────────────────

def _test_calendar_sorts_by_urgency():
    eng = MLOpsRetrainingSchedulerEngine()
    fresh_ok = FreshnessAssessment(
        "ok", "1.0", 10, FreshnessSeverity.FRESH, "",
        FreshnessPolicy(30, 90), ())
    fresh_stale = FreshnessAssessment(
        "stale", "1.0", 200, FreshnessSeverity.STALE, "",
        FreshnessPolicy(30, 90), ())
    fresh_warn = FreshnessAssessment(
        "warn", "1.0", 50, FreshnessSeverity.WARNING, "",
        FreshnessPolicy(30, 90), ())
    recs = (
        eng.compute_retraining_recommendation(
            "ok", "1.0", fresh_ok, None, None,
            RetrainingPolicy(require_freshness=True)),
        eng.compute_retraining_recommendation(
            "stale", "1.0", fresh_stale, None, None,
            RetrainingPolicy(require_freshness=True)),
        eng.compute_retraining_recommendation(
            "warn", "1.0", fresh_warn, None, None,
            RetrainingPolicy(require_freshness=True)),
    )
    cal = eng.build_retraining_calendar(recs)
    # DUE first, then SOON, then NOT_YET
    assert cal.entries[0].model_id == "stale"
    assert cal.entries[1].model_id == "warn"
    assert cal.entries[2].model_id == "ok"
    assert cal.summary_due == 1
    assert cal.summary_soon == 1
    assert cal.summary_not_yet == 1


def _test_calendar_summary_counts():
    eng = MLOpsRetrainingSchedulerEngine()
    cal = eng.build_retraining_calendar(())
    assert cal.summary_due == 0
    assert cal.summary_soon == 0
    assert cal.summary_not_yet == 0
    assert cal.summary_insufficient == 0


# ─── Discipline tests ──────────────────────────────────────────

def _test_drift_caller_chooses_method():
    """Engine doesn't bundle PSI vs KS vs Wasserstein decision."""
    eng = MLOpsRetrainingSchedulerEngine()
    # Same value with different metric_name produces different
    # framework_refs but same severity
    a_psi = eng.evaluate_drift_signal(
        "m", Decimal("0.15"),
        DriftThresholds(
            Decimal("0.10"), Decimal("0.25"), "PSI"))
    a_ks = eng.evaluate_drift_signal(
        "m", Decimal("0.15"),
        DriftThresholds(
            Decimal("0.10"), Decimal("0.25"), "KS"))
    assert a_psi.metric_name == "PSI"
    assert a_ks.metric_name == "KS"
    assert a_psi.severity == a_ks.severity == (
        DriftSignalSeverity.WARNING)


def _test_full_provenance():
    eng = MLOpsRetrainingSchedulerEngine()
    a = eng.evaluate_freshness(
        "m", "1.0", "2026-04-01T00:00:00Z",
        "2026-05-01T00:00:00Z",
        FreshnessPolicy(30, 90))
    refs = " / ".join(a.framework_refs)
    assert "ENH-283" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs


def _test_caller_supplied_default_replaces():
    """Custom default policy is used when no policy passed."""
    custom = RetrainingPolicy(
        require_freshness=False,
        require_override_signal=True,
        require_drift_signal=True)
    eng = MLOpsRetrainingSchedulerEngine(
        default_policy=custom)
    fresh = FreshnessAssessment(
        "m", "1.0", 200, FreshnessSeverity.STALE, "",
        FreshnessPolicy(30, 90), ())
    # No override/drift supplied; require_freshness=False so
    # missing freshness wouldn't matter — but missing override
    # IS required → INSUFFICIENT_DATA
    r = eng.compute_retraining_recommendation(
        "m", "1.0", fresh, None, None)  # uses default
    assert r.outcome == (
        RetrainingOutcome.INSUFFICIENT_DATA)


def self_test() -> None:
    tests = [
        _test_freshness_fresh,
        _test_freshness_warning,
        _test_freshness_stale,
        _test_freshness_insufficient,
        _test_override_ok,
        _test_override_warning,
        _test_override_critical,
        _test_override_insufficient,
        _test_drift_psi_ok,
        _test_drift_psi_critical,
        _test_drift_metric_name_preserved,
        _test_recommend_due_freshness_critical,
        _test_recommend_soon_only_warning,
        _test_recommend_not_yet_all_ok,
        _test_recommend_insufficient_required_missing,
        _test_recommend_combined_all_three,
        _test_recommend_non_required_missing_silently_skipped,
        _test_calendar_sorts_by_urgency,
        _test_calendar_summary_counts,
        _test_drift_caller_chooses_method,
        _test_full_provenance,
        _test_caller_supplied_default_replaces,
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
            f"✗ mlops_retraining_scheduler self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ mlops_retraining_scheduler self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

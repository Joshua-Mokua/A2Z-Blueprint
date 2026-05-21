"""utils/mlops_adjudication_log.py — v10.82: MLOps Adjudication Log.

ENH-282 — MLOps Adjudication Log. Cat B — ml_governance arc 2/N.

Diagnostic operator-override capture engine. When a model recommends
X via the v10.76 ML hook contract and an operator picks Y instead,
this engine processes the captured override into:

  - per-model override rate over a rolling window (high override rate
    = operator trust eroding = retraining signal)
  - per-recommendation-class override patterns (uneven override rates
    across protected classes = potential bias signal feeding into the
    model_governance arc's bias monitoring at G124)
  - candidate retraining datasets composed from operator-overridden
    examples (the human-in-the-loop labeling pattern — overrides
    become labeled training data for the next model version)
  - chronological adjudication audit trails for regulatory examination

This engine sits at the integration point between the v10.76 ML hook
contract (engine-side, where models serve recommendations) and ENH-281
mlops_model_registry (which tracks model versions). The closed loop
across the ml_governance arc is:

   model serves prediction (v10.76 hook contract)
     → operator overrides or accepts (this engine captures)
       → ENH-283 retraining scheduler reads override rate trend
         → ENH-281 registry receives new candidate version
           → ENH-284 A/B harness compares shadow vs active
             → ENH-285 model card composer surfaces all of the above

Five capabilities:

  1. record_adjudication — validate caller-supplied event fields
     (model_id + version + recommendation + operator decision +
     agreement status + reason + timestamp + optional input features
     hash for retraining lineage); return AdjudicationRecord (frozen).
     Per Rule 7, engine never persists — caller appends to their
     adjudication storage.

  2. compute_override_rate — given a sequence of records + model_id
     filter + optional time window — return OverrideRateMetric (rate,
     count_total, count_overridden, count_accepted, count_pending,
     window). Surfaces rolling override rate as retraining signal.

  3. compute_class_level_override_patterns — given records + caller-
     supplied recommendation class taxonomy — return per-class
     override patterns. Per Rule 1, surfaces uneven rates across
     classes as bias indicator (this engine flags signal; bias
     decision belongs to model_governance arc — boundary preserved).

  4. build_retraining_candidate_dataset — given records + filter
     (model_id + retraining_eligible flag + minimum count threshold) —
     return RetrainingDatasetCandidate frozen tuple. Per Rule 7, engine
     selects + structures the dataset; never trains. Caller invokes the
     training pipeline.

  5. build_adjudication_audit_trail — given records + filter (model_id +
     time window) — return AdjudicationAuditTrail with chronological
     event list + summary statistics. Designed for regulatory
     examination evidence preservation.

Per Rule 7, engine NEVER:
  - auto-retrains a model (ENH-283 retraining scheduler is diagnostic
    too — it surfaces when retraining is due; operator triggers)
  - auto-modifies model recommendations (the model layer is sealed —
    this engine is observational)
  - silently records (every event is an explicit operator decision
    captured by the caller; engine processes captured events)
  - decides bias from override patterns (engine surfaces signal; bias
    decision is model_governance arc territory at G124)
  - mutates input records (returns new dataclass instances)
  - persists records (caller stores in JSON / PG / wherever)

Per Rule 1, every output surfaces inputs + intermediates + outputs +
framework_refs. All result dataclasses are frozen.

Caller-supplied data discipline (matches ENH-274 / ENH-278 / ENH-271 /
ENH-276 / ENH-281 pattern): adjudication records sequence + class
taxonomy + time windows + retraining eligibility filter all caller-
supplied; engine bundles no defaults. Caller maintains storage.

Pure stdlib runtime.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import (
    Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "MLOpsAdjudicationLogEngine implements ENH-282 — diagnostic "
    "operator-override capture engine. Sits at the integration point "
    "between the v10.76 ML hook contract (where models serve "
    "recommendations) and ENH-281 mlops_model_registry (where versions "
    "are tracked). Engine processes captured override events into "
    "rolling override rates + class-level patterns + retraining "
    "candidate datasets + audit trails. Pure stdlib. Per Rule 1, every "
    "output surfaces full provenance + framework_refs. Per Rule 7, "
    "engine DIAGNOSTIC ONLY — never auto-retrains, never modifies "
    "model recommendations, never silently records, never decides bias "
    "(bias decision is model_governance arc territory at G124), never "
    "persists records (caller stores)."
)

# ISO 8601 datetime pattern — strict UTC or offset format
_ISO_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$")


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class AgreementStatus(Enum):
    """Operator agreement with model recommendation."""
    ACCEPTED = "ACCEPTED"          # operator agreed with model
    OVERRIDDEN = "OVERRIDDEN"      # operator chose different output
    ESCALATED = "ESCALATED"        # operator deferred to senior reviewer
    PENDING = "PENDING"            # awaiting operator review


class OverrideReason(Enum):
    """Caller-supplied reason taxonomy for overrides. The 6 here cover
    canonical categories from ML governance literature; extension via
    OTHER + free-text reason field for novel cases."""
    INSUFFICIENT_CONFIDENCE = "INSUFFICIENT_CONFIDENCE"
    DOMAIN_KNOWLEDGE = "DOMAIN_KNOWLEDGE"
    POLICY_OVERRIDE = "POLICY_OVERRIDE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    REGULATORY_REQUIREMENT = "REGULATORY_REQUIREMENT"
    DATA_QUALITY_CONCERN = "DATA_QUALITY_CONCERN"
    OTHER = "OTHER"


class RecordingOutcome(Enum):
    RECORDED = "RECORDED"
    REJECTED_INVALID = "REJECTED_INVALID"


class TimeWindowUnit(Enum):
    HOURS = "HOURS"
    DAYS = "DAYS"


# ════════════════════════════════════════════════════════════════════════
# Input + intermediate dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TimeWindow:
    """Caller-supplied window for rolling-rate computations."""
    duration: int
    unit: TimeWindowUnit
    end_iso: str  # window ends at this ISO timestamp

    def total_hours(self) -> int:
        if self.unit == TimeWindowUnit.HOURS:
            return self.duration
        return self.duration * 24


@dataclass(frozen=True)
class RecommendationClassTaxonomy:
    """Caller-supplied taxonomy for recommendation classes. Used by
    compute_class_level_override_patterns to identify uneven override
    rates across protected or material classes (bias signal)."""
    class_id: str
    description: str
    is_protected_class: bool = False  # bias monitoring relevant
    minimum_sample_size: int = 30     # statistical significance floor


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AdjudicationRecord:
    """A single captured operator-vs-model adjudication event. Caller
    persists in their adjudication storage. Engine constructs via
    record_adjudication; engine never persists."""
    event_id: str
    model_id: str
    model_version: str
    recommendation: str            # what the model recommended
    recommendation_class: str      # caller-supplied class category
    operator_decision: str         # what the operator chose
    agreement_status: AgreementStatus
    operator_id: str
    decision_at_iso: str           # ISO 8601 datetime
    override_reason: Optional[OverrideReason] = None
    override_reason_text: str = ""
    input_features_hash: Optional[str] = None  # for retraining lineage
    retraining_eligible: bool = False
    notes: str = ""


@dataclass(frozen=True)
class RecordingResult:
    outcome: RecordingOutcome
    record: Optional[AdjudicationRecord]
    findings: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class OverrideRateMetric:
    model_id: str
    window: TimeWindow
    count_total: int               # records in window
    count_accepted: int
    count_overridden: int
    count_escalated: int
    count_pending: int
    override_rate: Optional[Decimal]   # None if total==0 (gap surfacing)
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ClassOverridePattern:
    class_id: str
    is_protected_class: bool
    count_total: int
    count_overridden: int
    override_rate: Optional[Decimal]
    insufficient_sample: bool      # below minimum_sample_size
    flagged_uneven: bool           # exceeds caller-supplied threshold


@dataclass(frozen=True)
class ClassLevelOverridePatterns:
    model_id: str
    patterns: Tuple[ClassOverridePattern, ...]
    overall_rate: Optional[Decimal]
    uneven_threshold_pct: Decimal      # caller-supplied
    flagged_class_count: int
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class RetrainingExample:
    """A single labeled example derived from operator override.
    input_features_hash links back to the original training data
    pipeline; recommendation + operator_decision become input + label
    for the next model version. Caller actually trains; engine just
    selects + structures."""
    event_id: str
    input_features_hash: str
    original_recommendation: str
    operator_decision: str
    decision_at_iso: str


@dataclass(frozen=True)
class RetrainingDatasetCandidate:
    model_id: str
    target_version_label: str   # caller-supplied (e.g. "2.0.0-candidate")
    examples: Tuple[RetrainingExample, ...]
    examples_excluded_no_features_hash: int
    examples_excluded_not_eligible: int
    insufficient_examples: bool   # below minimum_count threshold
    minimum_count_threshold: int
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class AdjudicationSummary:
    count_total: int
    count_accepted: int
    count_overridden: int
    count_escalated: int
    count_pending: int
    overridden_by_reason: Mapping[str, int]  # reason -> count


@dataclass(frozen=True)
class AdjudicationAuditTrail:
    model_id: str
    window: TimeWindow
    chronological_events: Tuple[AdjudicationRecord, ...]
    summary: AdjudicationSummary
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class MLOpsAdjudicationLogEngine:
    """Diagnostic operator-override capture engine."""

    # ─── 1. Record adjudication ────────────────────────────────
    def record_adjudication(
        self,
        event_id: str,
        model_id: str,
        model_version: str,
        recommendation: str,
        recommendation_class: str,
        operator_decision: str,
        agreement_status: AgreementStatus,
        operator_id: str,
        decision_at_iso: str,
        override_reason: Optional[OverrideReason] = None,
        override_reason_text: str = "",
        input_features_hash: Optional[str] = None,
        retraining_eligible: bool = False,
        notes: str = "",
    ) -> RecordingResult:
        """Validate inputs and construct AdjudicationRecord. Per Rule
        7, engine does NOT persist — caller appends to their storage.
        """
        findings: list = []

        if not event_id or not event_id.strip():
            findings.append(
                "event_id required (non-empty string)")
        if not model_id or not model_id.strip():
            findings.append(
                "model_id required (non-empty string)")
        if not model_version or not model_version.strip():
            findings.append(
                "model_version required (non-empty string)")
        if not recommendation or not recommendation.strip():
            findings.append(
                "recommendation required (non-empty string)")
        if not recommendation_class or (
            not recommendation_class.strip()
        ):
            findings.append(
                "recommendation_class required (non-empty "
                "string)")
        if not operator_decision or (
            not operator_decision.strip()
        ):
            findings.append(
                "operator_decision required (non-empty string)")
        if not operator_id or not operator_id.strip():
            findings.append(
                "operator_id required (non-empty string) — "
                "regulatory examination requires the deciding "
                "person to be identified")
        if not decision_at_iso or not decision_at_iso.strip():
            findings.append(
                "decision_at_iso required (ISO 8601 datetime)")
        elif not _ISO_PATTERN.match(decision_at_iso.strip()):
            findings.append(
                f"decision_at_iso '{decision_at_iso}' is not "
                f"a valid ISO 8601 datetime format")

        # If status is OVERRIDDEN, override_reason should be present
        # (Rule 1 — full provenance; regulatory exam requires reason)
        if agreement_status == AgreementStatus.OVERRIDDEN:
            if override_reason is None:
                findings.append(
                    "override_reason required when "
                    "agreement_status is OVERRIDDEN — "
                    "regulatory examination requires the "
                    "reason for override to be captured")

        # If retraining_eligible, input_features_hash must be present
        # (otherwise the example can't link back to training data)
        if retraining_eligible:
            if not input_features_hash or (
                not input_features_hash.strip()
            ):
                findings.append(
                    "input_features_hash required when "
                    "retraining_eligible=True — without it the "
                    "example cannot link back to training data "
                    "for the next model version")

        if findings:
            return RecordingResult(
                outcome=RecordingOutcome.REJECTED_INVALID,
                record=None,
                findings=tuple(findings),
                framework_refs=(
                    "ENH-282 §record_adjudication",
                    "Per Rule 1 — all validation findings "
                    "surfaced (not just first)",
                    "Per Rule 7 — rejection means caller must "
                    "fix inputs before retrying; engine does "
                    "not silently coerce or default",
                ))

        record = AdjudicationRecord(
            event_id=event_id.strip(),
            model_id=model_id.strip(),
            model_version=model_version.strip(),
            recommendation=recommendation.strip(),
            recommendation_class=recommendation_class.strip(),
            operator_decision=operator_decision.strip(),
            agreement_status=agreement_status,
            operator_id=operator_id.strip(),
            decision_at_iso=decision_at_iso.strip(),
            override_reason=override_reason,
            override_reason_text=override_reason_text,
            input_features_hash=(
                input_features_hash.strip()
                if input_features_hash else None),
            retraining_eligible=retraining_eligible,
            notes=notes,
        )

        return RecordingResult(
            outcome=RecordingOutcome.RECORDED,
            record=record,
            findings=(),
            framework_refs=(
                "ENH-282 §record_adjudication",
                "Captures operator override or acceptance per "
                "Microsoft MLOps Maturity Model (2023) — "
                "Stage 4 Human-in-the-Loop pattern",
                "Adjudication evidence preserved per OCC 2011-12 "
                "model risk management documentation requirements",
                "Per Rule 1 — full provenance preserved + "
                "framework_refs",
                "Per Rule 7 — engine constructs record; caller "
                "persists",
            ),
        )

    # ─── 2. Compute override rate ──────────────────────────────
    def compute_override_rate(
        self,
        records: Sequence[AdjudicationRecord],
        model_id: str,
        window: TimeWindow,
    ) -> OverrideRateMetric:
        """Rolling override rate per model over caller-supplied
        window. Per Rule 1, surfaces total / accepted / overridden /
        escalated / pending counts and the rate (None if no records
        in window — explicit gap-surfacing)."""
        in_window = self._filter_in_window(
            records, model_id, window)

        count_total = len(in_window)
        count_accepted = sum(
            1 for r in in_window
            if r.agreement_status == AgreementStatus.ACCEPTED)
        count_overridden = sum(
            1 for r in in_window
            if r.agreement_status == AgreementStatus.OVERRIDDEN)
        count_escalated = sum(
            1 for r in in_window
            if r.agreement_status == AgreementStatus.ESCALATED)
        count_pending = sum(
            1 for r in in_window
            if r.agreement_status == AgreementStatus.PENDING)

        # Override rate excludes PENDING from denominator (those
        # haven't been adjudicated yet) and excludes ESCALATED
        # (those went to a different decision-maker).
        decided = count_accepted + count_overridden
        if decided == 0:
            rate = None
        else:
            rate = (
                Decimal(count_overridden) / Decimal(decided))

        return OverrideRateMetric(
            model_id=model_id,
            window=window,
            count_total=count_total,
            count_accepted=count_accepted,
            count_overridden=count_overridden,
            count_escalated=count_escalated,
            count_pending=count_pending,
            override_rate=rate,
            framework_refs=(
                "ENH-282 §compute_override_rate",
                "Override rate denominator = ACCEPTED + "
                "OVERRIDDEN; PENDING and ESCALATED excluded "
                "(PENDING = not yet decided; ESCALATED = "
                "decided by senior reviewer outside this "
                "operator's scope)",
                "Per Rule 1 — None rate surfaced when "
                "decided==0 (no signal yet); engine never "
                "fabricates a rate from an empty denominator",
                "Per Rule 7 — engine surfaces rate; never "
                "decides 'rate too high → trigger retraining' "
                "(that is ENH-283 retraining scheduler "
                "territory, and even there engine surfaces "
                "signal; operator triggers)",
                "ML Test Score (Breck et al. 2017) — model "
                "performance over time as production-readiness "
                "indicator",
            ),
        )

    # ─── 3. Compute class-level override patterns ──────────────
    def compute_class_level_override_patterns(
        self,
        records: Sequence[AdjudicationRecord],
        model_id: str,
        class_taxonomy: Sequence[RecommendationClassTaxonomy],
        window: TimeWindow,
        uneven_threshold_pct: Decimal = Decimal("0.20"),
    ) -> ClassLevelOverridePatterns:
        """Per-class override patterns — surfaces uneven rates across
        recommendation classes as bias signal. Per Rule 1, surfaces
        signal explicitly. Per Rule 7, bias decision belongs to
        model_governance arc at G124 — this engine only flags."""
        in_window = self._filter_in_window(
            records, model_id, window)

        # Overall rate (denominator: decided records)
        total_decided = sum(
            1 for r in in_window
            if r.agreement_status in (
                AgreementStatus.ACCEPTED,
                AgreementStatus.OVERRIDDEN))
        total_overridden = sum(
            1 for r in in_window
            if r.agreement_status == AgreementStatus.OVERRIDDEN)
        overall_rate = (
            Decimal(total_overridden) / Decimal(total_decided)
            if total_decided > 0 else None)

        patterns: list = []
        flagged_count = 0

        for class_spec in class_taxonomy:
            class_records = [
                r for r in in_window
                if r.recommendation_class == class_spec.class_id]
            class_decided = sum(
                1 for r in class_records
                if r.agreement_status in (
                    AgreementStatus.ACCEPTED,
                    AgreementStatus.OVERRIDDEN))
            class_overridden = sum(
                1 for r in class_records
                if r.agreement_status == (
                    AgreementStatus.OVERRIDDEN))

            insufficient = (
                class_decided < class_spec.minimum_sample_size)
            class_rate = (
                Decimal(class_overridden) / Decimal(class_decided)
                if class_decided > 0 else None)

            # Flag uneven if class rate exceeds threshold above
            # overall rate AND sample size is sufficient
            flagged = False
            if (overall_rate is not None
                and class_rate is not None
                and not insufficient
            ):
                deviation = abs(class_rate - overall_rate)
                if deviation >= uneven_threshold_pct:
                    flagged = True
                    flagged_count += 1

            patterns.append(ClassOverridePattern(
                class_id=class_spec.class_id,
                is_protected_class=class_spec.is_protected_class,
                count_total=len(class_records),
                count_overridden=class_overridden,
                override_rate=class_rate,
                insufficient_sample=insufficient,
                flagged_uneven=flagged))

        return ClassLevelOverridePatterns(
            model_id=model_id,
            patterns=tuple(patterns),
            overall_rate=overall_rate,
            uneven_threshold_pct=uneven_threshold_pct,
            flagged_class_count=flagged_count,
            framework_refs=(
                "ENH-282 §compute_class_level_override_patterns",
                "Uneven detection: |class_rate - overall_rate| "
                "≥ uneven_threshold_pct (caller-supplied; "
                "default 0.20 = 20pp deviation). Sample "
                "sufficiency required (caller-supplied minimum "
                "via class taxonomy).",
                "Per Rule 1 — insufficient_sample surfaced "
                "explicitly when sample size below threshold "
                "(rate not statistically meaningful — engine "
                "never fabricates significance)",
                "Per Rule 7 — engine surfaces uneven rate as "
                "BIAS SIGNAL; bias DECISION belongs to "
                "model_governance arc at G124 (which uses "
                "demographic parity / equalized odds / "
                "calibration tests). Boundary preserved.",
                "Microsoft MLOps Maturity Model (2023) — "
                "fairness monitoring as continuous practice",
                "Bird et al. (2020) — Fairlearn library "
                "approach to disparity surfacing",
            ),
        )

    # ─── 4. Build retraining candidate dataset ─────────────────
    def build_retraining_candidate_dataset(
        self,
        records: Sequence[AdjudicationRecord],
        model_id: str,
        target_version_label: str,
        minimum_count_threshold: int = 100,
    ) -> RetrainingDatasetCandidate:
        """Compose retraining candidate dataset from operator-
        overridden examples flagged retraining_eligible. Per Rule 7,
        engine selects + structures; never trains. Caller invokes
        the training pipeline."""
        # Filter to model_id + OVERRIDDEN status + retraining_eligible
        candidates = [
            r for r in records
            if r.model_id == model_id
            and r.agreement_status == AgreementStatus.OVERRIDDEN
            and r.retraining_eligible]

        # Surface exclusions explicitly (Rule 1 — gap-surfacing)
        excluded_no_hash = sum(
            1 for r in candidates
            if not r.input_features_hash)
        # The caller-supplied retraining_eligible filter already
        # acted; now filter out missing hash
        usable = [r for r in candidates if r.input_features_hash]

        examples = tuple(
            RetrainingExample(
                event_id=r.event_id,
                input_features_hash=r.input_features_hash,
                original_recommendation=r.recommendation,
                operator_decision=r.operator_decision,
                decision_at_iso=r.decision_at_iso)
            for r in usable)

        # Excluded "not eligible" = total OVERRIDDEN - retraining_eligible
        all_overridden = [
            r for r in records
            if r.model_id == model_id
            and r.agreement_status == AgreementStatus.OVERRIDDEN]
        excluded_not_eligible = (
            len(all_overridden) - len(candidates))

        return RetrainingDatasetCandidate(
            model_id=model_id,
            target_version_label=target_version_label,
            examples=examples,
            examples_excluded_no_features_hash=excluded_no_hash,
            examples_excluded_not_eligible=(
                excluded_not_eligible),
            insufficient_examples=(
                len(examples) < minimum_count_threshold),
            minimum_count_threshold=minimum_count_threshold,
            framework_refs=(
                "ENH-282 §build_retraining_candidate_dataset",
                "Filters: model_id + agreement_status="
                "OVERRIDDEN + retraining_eligible=True + "
                "input_features_hash present",
                "Per Rule 1 — examples_excluded_no_features_"
                "hash and examples_excluded_not_eligible "
                "surfaced as separate explicit counts (caller "
                "sees what dropped out and why)",
                "Per Rule 7 — engine selects + structures the "
                "candidate dataset; engine never trains "
                "(training is caller infrastructure). "
                "insufficient_examples flag surfaces but does "
                "not block — caller decides whether to proceed "
                "with insufficient data or wait",
                "Human-in-the-loop labeling pattern — Settles "
                "(2009) Active Learning Survey",
                "Microsoft MLOps Maturity Model (2023) — "
                "Stage 4 Continuous Training",
            ),
        )

    # ─── 5. Build adjudication audit trail ─────────────────────
    def build_adjudication_audit_trail(
        self,
        records: Sequence[AdjudicationRecord],
        model_id: str,
        window: TimeWindow,
    ) -> AdjudicationAuditTrail:
        """Chronological event list + summary statistics for
        regulatory examination evidence preservation."""
        in_window = self._filter_in_window(
            records, model_id, window)

        # Sort chronologically
        chronological = tuple(sorted(
            in_window, key=lambda r: r.decision_at_iso))

        count_total = len(chronological)
        count_accepted = sum(
            1 for r in chronological
            if r.agreement_status == AgreementStatus.ACCEPTED)
        count_overridden = sum(
            1 for r in chronological
            if r.agreement_status == AgreementStatus.OVERRIDDEN)
        count_escalated = sum(
            1 for r in chronological
            if r.agreement_status == AgreementStatus.ESCALATED)
        count_pending = sum(
            1 for r in chronological
            if r.agreement_status == AgreementStatus.PENDING)

        # Override breakdown by reason
        by_reason: dict = {}
        for r in chronological:
            if r.agreement_status != (
                AgreementStatus.OVERRIDDEN
            ):
                continue
            reason_key = (
                r.override_reason.value
                if r.override_reason else "UNSPECIFIED")
            by_reason[reason_key] = (
                by_reason.get(reason_key, 0) + 1)

        summary = AdjudicationSummary(
            count_total=count_total,
            count_accepted=count_accepted,
            count_overridden=count_overridden,
            count_escalated=count_escalated,
            count_pending=count_pending,
            overridden_by_reason=dict(by_reason))

        return AdjudicationAuditTrail(
            model_id=model_id,
            window=window,
            chronological_events=chronological,
            summary=summary,
            framework_refs=(
                "ENH-282 §build_adjudication_audit_trail",
                "Chronological ordering by decision_at_iso "
                "preserves examination narrative",
                "Per Rule 1 — full event list + summary "
                "statistics surface together (regulator sees "
                "both the rollup and the underlying events)",
                "Per Rule 7 — engine composes audit trail; "
                "never serializes to regulator-specific "
                "schema (XBRL / iTax / CBK formats are "
                "regulatory_reporting territory). Caller "
                "decides serialization at exam time.",
                "OCC 2011-12 §V.5 — model performance "
                "monitoring documentation requirements",
                "SR 11-7 §V — model documentation and "
                "examination evidence preservation",
                "EU AI Act Article 13 — transparency and "
                "provision of information to deployers",
            ),
        )

    # ─── Helper ────────────────────────────────────────────────
    def _filter_in_window(
        self,
        records: Sequence[AdjudicationRecord],
        model_id: str,
        window: TimeWindow,
    ) -> Tuple[AdjudicationRecord, ...]:
        """Filter records to those for the given model_id within
        the time window. Window end is window.end_iso; window start
        is end - duration. Inclusive of both bounds."""
        try:
            end_dt = self._parse_iso(window.end_iso)
        except ValueError:
            return ()

        start_dt = end_dt
        # Subtract duration via UTC arithmetic
        from datetime import timedelta
        if window.unit == TimeWindowUnit.HOURS:
            start_dt = end_dt - timedelta(
                hours=window.duration)
        else:
            start_dt = end_dt - timedelta(
                days=window.duration)

        result: list = []
        for r in records:
            if r.model_id != model_id:
                continue
            try:
                r_dt = self._parse_iso(r.decision_at_iso)
            except ValueError:
                continue   # malformed timestamps excluded
            if start_dt <= r_dt <= end_dt:
                result.append(r)
        return tuple(result)

    @staticmethod
    def _parse_iso(s: str) -> datetime:
        """Parse a strict ISO 8601 datetime. Treats Z as UTC."""
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_record(
    event_id="EV-001",
    model_id="doc_classifier",
    version="1.0.0",
    recommendation="APPROVE",
    recommendation_class="APPROVE",
    operator_decision="APPROVE",
    status=AgreementStatus.ACCEPTED,
    decision_at="2026-05-01T10:00:00Z",
    override_reason=None,
    input_features_hash=None,
    retraining_eligible=False,
):
    return AdjudicationRecord(
        event_id=event_id,
        model_id=model_id,
        model_version=version,
        recommendation=recommendation,
        recommendation_class=recommendation_class,
        operator_decision=operator_decision,
        agreement_status=status,
        operator_id="op-1",
        decision_at_iso=decision_at,
        override_reason=override_reason,
        override_reason_text="",
        input_features_hash=input_features_hash,
        retraining_eligible=retraining_eligible,
        notes="")


# ─── Recording tests ───────────────────────────────────────────

def _test_record_clean_acceptance():
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-001",
        model_id="doc_classifier",
        model_version="1.0.0",
        recommendation="APPROVE",
        recommendation_class="APPROVE",
        operator_decision="APPROVE",
        agreement_status=AgreementStatus.ACCEPTED,
        operator_id="alice",
        decision_at_iso="2026-05-01T10:00:00Z")
    assert r.outcome == RecordingOutcome.RECORDED
    assert r.record is not None
    assert r.record.agreement_status == (
        AgreementStatus.ACCEPTED)


def _test_record_clean_override():
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-002",
        model_id="doc_classifier",
        model_version="1.0.0",
        recommendation="APPROVE",
        recommendation_class="APPROVE",
        operator_decision="REJECT",
        agreement_status=AgreementStatus.OVERRIDDEN,
        operator_id="alice",
        decision_at_iso="2026-05-01T11:00:00Z",
        override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
        override_reason_text="Customer is on internal watchlist")
    assert r.outcome == RecordingOutcome.RECORDED
    assert r.record.override_reason == (
        OverrideReason.DOMAIN_KNOWLEDGE)


def _test_record_overridden_without_reason():
    """OVERRIDDEN status without override_reason → REJECTED."""
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-003",
        model_id="x", model_version="1.0",
        recommendation="A", recommendation_class="A",
        operator_decision="B",
        agreement_status=AgreementStatus.OVERRIDDEN,
        operator_id="op",
        decision_at_iso="2026-05-01T10:00:00Z")
    assert r.outcome == RecordingOutcome.REJECTED_INVALID
    assert any("override_reason" in f for f in r.findings)


def _test_record_invalid_iso():
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-004",
        model_id="x", model_version="1.0",
        recommendation="A", recommendation_class="A",
        operator_decision="A",
        agreement_status=AgreementStatus.ACCEPTED,
        operator_id="op",
        decision_at_iso="May 1, 2026")  # not ISO
    assert r.outcome == RecordingOutcome.REJECTED_INVALID
    assert any("ISO 8601" in f for f in r.findings)


def _test_record_retraining_without_hash():
    """retraining_eligible=True without input_features_hash → REJECTED."""
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-005",
        model_id="x", model_version="1.0",
        recommendation="A", recommendation_class="A",
        operator_decision="B",
        agreement_status=AgreementStatus.OVERRIDDEN,
        operator_id="op",
        decision_at_iso="2026-05-01T10:00:00Z",
        override_reason=OverrideReason.OTHER,
        retraining_eligible=True)
    assert r.outcome == RecordingOutcome.REJECTED_INVALID
    assert any(
        "input_features_hash" in f for f in r.findings)


def _test_record_missing_operator_id():
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-006",
        model_id="x", model_version="1.0",
        recommendation="A", recommendation_class="A",
        operator_decision="A",
        agreement_status=AgreementStatus.ACCEPTED,
        operator_id="",
        decision_at_iso="2026-05-01T10:00:00Z")
    assert r.outcome == RecordingOutcome.REJECTED_INVALID


# ─── Override rate tests ───────────────────────────────────────

def _test_override_rate_basic():
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="E1",
            status=AgreementStatus.ACCEPTED,
            decision_at="2026-05-01T10:00:00Z"),
        _make_record(
            event_id="E2",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T11:00:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE),
        _make_record(
            event_id="E3",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T12:00:00Z"),
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    m = eng.compute_override_rate(
        records, "doc_classifier", window)
    assert m.count_total == 3
    assert m.count_accepted == 1
    assert m.count_overridden == 2
    # rate = 2/3 = 0.6667
    assert m.override_rate == (Decimal(2) / Decimal(3))


def _test_override_rate_excludes_pending():
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="E1",
            status=AgreementStatus.ACCEPTED,
            decision_at="2026-05-01T10:00:00Z"),
        _make_record(
            event_id="E2",
            status=AgreementStatus.PENDING,
            decision_at="2026-05-01T11:00:00Z"),
        _make_record(
            event_id="E3",
            status=AgreementStatus.PENDING,
            decision_at="2026-05-01T12:00:00Z"),
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    m = eng.compute_override_rate(
        records, "doc_classifier", window)
    # 1 ACCEPTED + 0 OVERRIDDEN + 2 PENDING → decided=1, rate=0
    assert m.count_pending == 2
    assert m.override_rate == Decimal(0)


def _test_override_rate_empty_returns_none():
    """No decided records → rate is None per Rule 1."""
    eng = MLOpsAdjudicationLogEngine()
    records = ()
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    m = eng.compute_override_rate(
        records, "doc_classifier", window)
    assert m.override_rate is None
    assert m.count_total == 0


def _test_override_rate_window_filters():
    """Records outside window excluded."""
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="OLD",
            status=AgreementStatus.ACCEPTED,
            decision_at="2026-04-01T10:00:00Z"),  # outside
        _make_record(
            event_id="IN",
            status=AgreementStatus.ACCEPTED,
            decision_at="2026-05-01T10:00:00Z"),  # in
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    m = eng.compute_override_rate(
        records, "doc_classifier", window)
    assert m.count_total == 1


# ─── Class-level pattern tests ─────────────────────────────────

def _test_class_patterns_uneven_flagged():
    """With imbalanced class sizes, the dominant class drives overall
    rate; the small outlier class deviates and gets flagged."""
    eng = MLOpsAdjudicationLogEngine()
    # APPROVE dominant: 50 decisions, 30% override rate → 15 overridden
    # REJECT outlier: 30 decisions, 80% override rate → 24 overridden
    # Overall (80 decided): 39/80 = 48.75%
    # APPROVE deviation: |0.30 - 0.4875| = 0.1875 < 0.20 → NOT flagged
    # REJECT deviation:  |0.80 - 0.4875| = 0.3125 ≥ 0.20 → FLAGGED
    records = []
    # APPROVE: 50 total, 15 overridden, 35 accepted
    for i in range(15):
        records.append(_make_record(
            event_id=f"AO{i}",
            recommendation_class="APPROVE",
            status=AgreementStatus.OVERRIDDEN,
            decision_at=f"2026-05-01T{(8 + i % 12):02d}:"
                        f"{(i % 60):02d}:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE))
    for i in range(35):
        records.append(_make_record(
            event_id=f"AA{i}",
            recommendation_class="APPROVE",
            status=AgreementStatus.ACCEPTED,
            decision_at=f"2026-05-01T{(8 + i % 12):02d}:"
                        f"{(i % 60):02d}:00Z"))
    # REJECT: 30 total, 24 overridden, 6 accepted
    for i in range(24):
        records.append(_make_record(
            event_id=f"RO{i}",
            recommendation_class="REJECT",
            status=AgreementStatus.OVERRIDDEN,
            decision_at=f"2026-05-01T{(8 + i % 12):02d}:"
                        f"{(i % 60):02d}:00Z",
            override_reason=OverrideReason.POLICY_OVERRIDE))
    for i in range(6):
        records.append(_make_record(
            event_id=f"RA{i}",
            recommendation_class="REJECT",
            status=AgreementStatus.ACCEPTED,
            decision_at=f"2026-05-01T{(8 + i % 12):02d}:"
                        f"{(i % 60):02d}:00Z"))

    taxonomy = (
        RecommendationClassTaxonomy(
            class_id="APPROVE",
            description="Approve recommendation",
            minimum_sample_size=20),
        RecommendationClassTaxonomy(
            class_id="REJECT",
            description="Reject recommendation",
            is_protected_class=True,
            minimum_sample_size=20),
    )
    window = TimeWindow(
        duration=48, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T23:00:00Z")
    p = eng.compute_class_level_override_patterns(
        records, "doc_classifier", taxonomy, window,
        uneven_threshold_pct=Decimal("0.20"))
    by_class = {pat.class_id: pat for pat in p.patterns}
    assert by_class["REJECT"].flagged_uneven is True, (
        f"REJECT should be flagged "
        f"(rate={by_class['REJECT'].override_rate}, "
        f"overall={p.overall_rate})")
    assert by_class["APPROVE"].flagged_uneven is False, (
        f"APPROVE should NOT be flagged "
        f"(rate={by_class['APPROVE'].override_rate}, "
        f"overall={p.overall_rate})")
    assert p.flagged_class_count == 1


def _test_class_patterns_insufficient_sample():
    """Class with sample size below minimum → not flagged."""
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="X",
            recommendation_class="RARE",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T10:00:00Z",
            override_reason=OverrideReason.OTHER),
    )
    taxonomy = (
        RecommendationClassTaxonomy(
            class_id="RARE",
            description="Rare class",
            minimum_sample_size=30),)
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    p = eng.compute_class_level_override_patterns(
        records, "doc_classifier", taxonomy, window)
    assert p.patterns[0].insufficient_sample is True
    assert p.patterns[0].flagged_uneven is False


# ─── Retraining dataset tests ──────────────────────────────────

def _test_retraining_dataset_filtering():
    eng = MLOpsAdjudicationLogEngine()
    records = (
        # Eligible + has hash → included
        _make_record(
            event_id="E1",
            status=AgreementStatus.OVERRIDDEN,
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
            input_features_hash="a" * 64,
            retraining_eligible=True),
        # Overridden but not eligible → excluded
        _make_record(
            event_id="E2",
            status=AgreementStatus.OVERRIDDEN,
            override_reason=OverrideReason.OTHER,
            input_features_hash="b" * 64,
            retraining_eligible=False),
        # Accepted → not in candidates at all
        _make_record(
            event_id="E3",
            status=AgreementStatus.ACCEPTED),
    )
    d = eng.build_retraining_candidate_dataset(
        records, "doc_classifier", "2.0.0-candidate",
        minimum_count_threshold=1)
    assert len(d.examples) == 1
    assert d.examples[0].event_id == "E1"
    assert d.examples_excluded_not_eligible == 1
    assert d.insufficient_examples is False


def _test_retraining_dataset_insufficient():
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="E1",
            status=AgreementStatus.OVERRIDDEN,
            override_reason=OverrideReason.OTHER,
            input_features_hash="a" * 64,
            retraining_eligible=True),)
    d = eng.build_retraining_candidate_dataset(
        records, "doc_classifier", "2.0.0",
        minimum_count_threshold=100)
    assert d.insufficient_examples is True
    assert len(d.examples) == 1


# ─── Audit trail tests ─────────────────────────────────────────

def _test_audit_trail_chronological():
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="LATE",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T15:00:00Z",
            override_reason=OverrideReason.OTHER),
        _make_record(
            event_id="EARLY",
            status=AgreementStatus.ACCEPTED,
            decision_at="2026-05-01T08:00:00Z"),
        _make_record(
            event_id="MID",
            status=AgreementStatus.ESCALATED,
            decision_at="2026-05-01T12:00:00Z"),
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    t = eng.build_adjudication_audit_trail(
        records, "doc_classifier", window)
    assert t.summary.count_total == 3
    assert t.summary.count_accepted == 1
    assert t.summary.count_overridden == 1
    assert t.summary.count_escalated == 1
    # Chronological ordering
    ids = [r.event_id for r in t.chronological_events]
    assert ids == ["EARLY", "MID", "LATE"]


def _test_audit_trail_reason_breakdown():
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="E1",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T10:00:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE),
        _make_record(
            event_id="E2",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T11:00:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE),
        _make_record(
            event_id="E3",
            status=AgreementStatus.OVERRIDDEN,
            decision_at="2026-05-01T12:00:00Z",
            override_reason=OverrideReason.POLICY_OVERRIDE),
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    t = eng.build_adjudication_audit_trail(
        records, "doc_classifier", window)
    assert t.summary.overridden_by_reason[
        "DOMAIN_KNOWLEDGE"] == 2
    assert t.summary.overridden_by_reason[
        "POLICY_OVERRIDE"] == 1


# ─── Discipline tests ──────────────────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = MLOpsAdjudicationLogEngine()
    records = (_make_record(),)
    eng.compute_override_rate(
        records, "doc_classifier",
        TimeWindow(
            24, TimeWindowUnit.HOURS,
            "2026-05-02T00:00:00Z"))
    # Original record should be unchanged (frozen)
    assert records[0].event_id == "EV-001"


def _test_full_provenance():
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="X", model_id="m", model_version="1",
        recommendation="A", recommendation_class="A",
        operator_decision="A",
        agreement_status=AgreementStatus.ACCEPTED,
        operator_id="op",
        decision_at_iso="2026-05-01T10:00:00Z")
    refs = " / ".join(r.framework_refs)
    assert "ENH-282" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs


def _test_caller_supplied_data_discipline():
    """Engine bundles no records; caller passes everything."""
    eng = MLOpsAdjudicationLogEngine()
    window = TimeWindow(
        24, TimeWindowUnit.HOURS, "2026-05-02T00:00:00Z")
    # Empty records → all counts zero, no fabrication
    m = eng.compute_override_rate(
        (), "doc_classifier", window)
    assert m.count_total == 0
    assert m.override_rate is None


def _test_protected_class_marker_preserved():
    """is_protected_class flag from taxonomy preserved through
    pattern computation."""
    eng = MLOpsAdjudicationLogEngine()
    records = (_make_record(
        recommendation_class="REJECT",
        status=AgreementStatus.OVERRIDDEN,
        override_reason=OverrideReason.OTHER,
        decision_at="2026-05-01T10:00:00Z"),)
    taxonomy = (
        RecommendationClassTaxonomy(
            class_id="REJECT",
            description="Reject",
            is_protected_class=True,
            minimum_sample_size=1),)
    window = TimeWindow(
        24, TimeWindowUnit.HOURS, "2026-05-02T00:00:00Z")
    p = eng.compute_class_level_override_patterns(
        records, "doc_classifier", taxonomy, window)
    assert p.patterns[0].is_protected_class is True


def _test_window_unit_days():
    """Window in DAYS unit works correctly."""
    eng = MLOpsAdjudicationLogEngine()
    records = (
        _make_record(
            event_id="OLD",
            decision_at="2026-04-25T10:00:00Z"),  # 7 days old
        _make_record(
            event_id="RECENT",
            decision_at="2026-05-01T10:00:00Z"),  # 1 day old
    )
    # 3-day window → only RECENT included
    window = TimeWindow(
        3, TimeWindowUnit.DAYS, "2026-05-02T00:00:00Z")
    m = eng.compute_override_rate(
        records, "doc_classifier", window)
    assert m.count_total == 1


def self_test() -> None:
    tests = [
        _test_record_clean_acceptance,
        _test_record_clean_override,
        _test_record_overridden_without_reason,
        _test_record_invalid_iso,
        _test_record_retraining_without_hash,
        _test_record_missing_operator_id,
        _test_override_rate_basic,
        _test_override_rate_excludes_pending,
        _test_override_rate_empty_returns_none,
        _test_override_rate_window_filters,
        _test_class_patterns_uneven_flagged,
        _test_class_patterns_insufficient_sample,
        _test_retraining_dataset_filtering,
        _test_retraining_dataset_insufficient,
        _test_audit_trail_chronological,
        _test_audit_trail_reason_breakdown,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_caller_supplied_data_discipline,
        _test_protected_class_marker_preserved,
        _test_window_unit_days,
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
            f"✗ mlops_adjudication_log self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ mlops_adjudication_log self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

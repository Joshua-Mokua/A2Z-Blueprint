"""utils/mlops_model_registry.py — v10.81: MLOps Model Registry.

ENH-281 — MLOps Model Registry. Cat B — ml_governance arc 1/N.

Diagnostic operational-lifecycle engine for tracking ML model
versions across the platform. Distinct from utils.model_governance
(closed at G124) which handles model risk classification, validation
testing, drift detection algorithms (PSI / KS / Wasserstein), and
EU AI Act / SR 11-7 compliance — that arc answers "is the model SAFE
to deploy?". This engine answers "WHICH version is deployed and what
version is the candidate?" — operational tracking not risk validation.

The boundary line is deliberate. A model can be VALIDATED (per
model_governance) but not yet PROMOTED (per this registry). The
operational status PROPOSED → SHADOW → ACTIVE → DEPRECATED → RETIRED
is orthogonal to the validation lifecycle DRAFT → REVIEW → APPROVED →
DECOMMISSIONED. Both stages must clear independently before a model
serves production traffic.

Five capabilities:

  1. register_new_model_version — input validation + entry
     construction with status=PROPOSED. Per Rule 7, engine never
     persists the entry; caller appends to their registry storage
     (JSON / PG / wherever). Engine validates required fields,
     metric value sanity, hash format, framework recognition.

  2. lookup_active_version — single ACTIVE entry per model_id (or
     None when no active version exists yet). Surfaces a violation
     if multiple ACTIVE entries exist for the same model_id (a
     governance breach — operations must remediate by demoting one).

  3. list_versions — filter the caller-supplied registry by
     model_id and optional status filter. Returns chronologically-
     ordered tuple (most recent first).

  4. compare_versions — diagnostic metric delta + framework version
     mismatch detection + training data hash diff. Per Rule 1, all
     three comparison axes surface explicitly (operator sees the
     full picture). Per Rule 7, engine never recommends one over
     the other — comparison is diagnostic.

  5. validate_promotion_readiness — caller-supplied PromotionGate
     sequence evaluated against a candidate entry (and optionally
     the current active for non-regression gates). Three gate types:
     MINIMUM_METRIC (candidate.metric ≥ threshold), NON_REGRESSION
     (candidate.metric ≥ active.metric - tolerance), and
     METADATA_REQUIRED (named field is non-empty). Surfaces all
     findings; outcome READY / BLOCKED / INSUFFICIENT_DATA. Per Rule
     7, engine never auto-promotes — operator decides.

Per Rule 7, engine NEVER:
  - persists registry entries (caller stores in JSON / PG / wherever)
  - promotes a model from PROPOSED → SHADOW → ACTIVE (operator
    decides based on validate_promotion_readiness output)
  - deploys a model artifact (deployment is separate ops territory)
  - triggers retraining (scheduled retraining is a future arc engine)
  - auto-rolls-back from ACTIVE → DEPRECATED on metric regression
    (operator decides)
  - runs models or makes predictions (the v10.76 ML hook contract is
    the engine-side; this is the lifecycle layer above it)
  - computes its own metrics (caller supplies metrics from the
    training pipeline; engine validates ranges + presence)

Per Rule 1, every output surfaces inputs + intermediates + outputs
+ framework_refs. All result dataclasses are frozen.

Caller-supplied data discipline (matches ENH-274 sanctions / ENH-278
taxonomies / ENH-271 keyword catalogues / ENH-276 protocol fields):
the registry sequence is caller-supplied. PromotionGate sequence is
caller-supplied. Engine bundles no defaults. Caller maintains storage
and persistence policy.

Pure stdlib runtime.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import (
    Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "MLOpsModelRegistryEngine implements ENH-281 — diagnostic "
    "operational-lifecycle engine for tracking ML model versions "
    "across the platform. Distinct from utils.model_governance "
    "(closed at G124) which handles model risk classification + "
    "validation testing + drift detection + bias monitoring + "
    "explainability. This engine handles operational deployment "
    "tracking — version chains, artifact hashes, training-data "
    "hashes, framework versions, promotion readiness assessment. "
    "Pure stdlib. Per Rule 1, every output surfaces validation "
    "findings + comparison rationale + framework_refs. Per Rule 7, "
    "engine DIAGNOSTIC ONLY — never persists, never promotes, never "
    "deploys, never auto-rolls-back, never runs models, never "
    "computes metrics."
)

# Recognized ML frameworks. Caller can extend via constructor for
# proprietary or research-stage frameworks.
DEFAULT_RECOGNIZED_FRAMEWORKS: Tuple[str, ...] = (
    "sklearn", "torch", "tensorflow", "onnx", "xgboost",
    "lightgbm", "statsmodels", "transformers", "custom")

# SHA-256 hex format — 64 lowercase hex chars
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class ModelStatus(Enum):
    """Operational deployment status. Distinct from
    model_governance.ModelLifecycleState (validation lifecycle).
    """
    PROPOSED = "PROPOSED"        # registered but not yet shadow-tested
    SHADOW = "SHADOW"            # running parallel to active for compare
    ACTIVE = "ACTIVE"            # serving production
    DEPRECATED = "DEPRECATED"    # superseded but kept for rollback
    RETIRED = "RETIRED"          # no longer serving anywhere


class GateType(Enum):
    MINIMUM_METRIC = "MINIMUM_METRIC"
    NON_REGRESSION = "NON_REGRESSION"
    METADATA_REQUIRED = "METADATA_REQUIRED"


class GateComparison(Enum):
    GTE = "GTE"   # candidate >= threshold (higher is better)
    LTE = "LTE"   # candidate <= threshold (lower is better, e.g. loss)


class GateFindingSeverity(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PromotionReadinessOutcome(Enum):
    READY = "READY"                          # all gates PASS
    BLOCKED = "BLOCKED"                      # at least one FAIL
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"  # at least one INSUFFICIENT


class RegistrationOutcome(Enum):
    REGISTERED = "REGISTERED"
    REJECTED_INVALID = "REJECTED_INVALID"


# ════════════════════════════════════════════════════════════════════════
# Input + intermediate dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PromotionGate:
    """Caller-supplied promotion gate specification."""
    gate_id: str
    gate_type: GateType
    description: str
    # MINIMUM_METRIC + NON_REGRESSION fields
    metric_name: Optional[str] = None
    threshold: Optional[Decimal] = None       # for MINIMUM_METRIC
    comparison: Optional[GateComparison] = None
    regression_tolerance: Optional[Decimal] = None  # for NON_REGRESSION
    # METADATA_REQUIRED field
    required_field: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ModelRegistryEntry:
    """A single version of a tracked ML model. Caller persists in
    their registry storage (JSON / PG / etc.). Engine constructs
    via register_new_model_version + emits via comparison/lookup
    methods; engine never persists.
    """
    model_id: str                       # e.g. "doc_classifier"
    version: str                         # e.g. "1.0.0" or "2026-05-baseline"
    artifact_hash: str                   # SHA-256 hex of model artifact blob
    training_data_hash: str              # SHA-256 hex of training dataset
    framework: str                       # one of recognized_frameworks
    framework_version: str               # e.g. "1.5.1"
    metrics: Mapping[str, Decimal]       # caller-supplied metrics
    owner: str
    status: ModelStatus
    created_by: str
    created_at_iso: str                  # ISO 8601 datetime
    training_completed_at_iso: Optional[str] = None
    notes: str = ""
    promoted_to_active_at_iso: Optional[str] = None
    deprecated_at_iso: Optional[str] = None


@dataclass(frozen=True)
class RegistrationResult:
    outcome: RegistrationOutcome
    entry: Optional[ModelRegistryEntry]
    findings: Tuple[str, ...]            # validation findings
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ActiveLookupResult:
    model_id: str
    active_entry: Optional[ModelRegistryEntry]
    multiple_active_violation: bool      # governance breach if True
    active_count: int
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class MetricDelta:
    metric_name: str
    version_a_value: Optional[Decimal]
    version_b_value: Optional[Decimal]
    delta: Optional[Decimal]             # b - a (None if either missing)


@dataclass(frozen=True)
class VersionComparison:
    version_a_id: str    # "{model_id}@{version}"
    version_b_id: str
    metric_deltas: Tuple[MetricDelta, ...]
    framework_match: bool
    framework_version_match: bool
    training_data_hash_match: bool
    artifact_hash_match: bool
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class GateFinding:
    gate_id: str
    gate_type: GateType
    severity: GateFindingSeverity
    description: str
    expected: str
    observed: str


@dataclass(frozen=True)
class PromotionReadinessAssessment:
    candidate_id: str
    current_active_id: Optional[str]
    outcome: PromotionReadinessOutcome
    findings: Tuple[GateFinding, ...]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class MLOpsModelRegistryEngine:
    """Diagnostic operational-lifecycle engine for ML model versions."""

    def __init__(
        self,
        recognized_frameworks: Optional[Sequence[str]] = None,
    ) -> None:
        # Caller-supplied recognized_frameworks REPLACES defaults
        # (caller-supplied data discipline — same as ENH-276
        # protocol_required_fields)
        if recognized_frameworks is None:
            self._recognized_frameworks: Tuple[str, ...] = (
                DEFAULT_RECOGNIZED_FRAMEWORKS)
        else:
            self._recognized_frameworks = tuple(
                recognized_frameworks)

    # ─── 1. Register new model version ─────────────────────────
    def register_new_model_version(
        self,
        model_id: str,
        version: str,
        artifact_hash: str,
        training_data_hash: str,
        framework: str,
        framework_version: str,
        metrics: Mapping[str, Decimal],
        owner: str,
        created_by: str,
        created_at_iso: str,
        training_completed_at_iso: Optional[str] = None,
        notes: str = "",
    ) -> RegistrationResult:
        """Validate inputs and construct a ModelRegistryEntry with
        status=PROPOSED. Per Rule 7, engine does NOT persist —
        caller appends to their registry storage.
        """
        findings = []

        if not model_id or not model_id.strip():
            findings.append(
                "model_id required (non-empty string)")
        if not version or not version.strip():
            findings.append(
                "version required (non-empty string)")
        if not _SHA256_PATTERN.match(
            artifact_hash.lower() if artifact_hash else ""
        ):
            findings.append(
                "artifact_hash must be SHA-256 hex (64 "
                "lowercase hex chars)")
        if not _SHA256_PATTERN.match(
            (training_data_hash.lower()
             if training_data_hash else "")
        ):
            findings.append(
                "training_data_hash must be SHA-256 hex (64 "
                "lowercase hex chars)")
        if framework not in self._recognized_frameworks:
            findings.append(
                f"framework '{framework}' not in recognized "
                f"list {self._recognized_frameworks} — "
                f"caller can extend via constructor")
        if not framework_version or not framework_version.strip():
            findings.append(
                "framework_version required (e.g. '1.5.1')")
        if not owner or not owner.strip():
            findings.append("owner required (non-empty string)")
        if not created_by or not created_by.strip():
            findings.append(
                "created_by required (non-empty string)")
        if not created_at_iso or not created_at_iso.strip():
            findings.append(
                "created_at_iso required (ISO 8601 datetime)")

        # Metric value sanity — must be Decimal/numeric, finite,
        # non-NaN. Caller-supplied — no range constraint per metric
        # because legitimate metrics span (loss, RMSE, AUC, etc.).
        if not metrics:
            findings.append(
                "metrics dict required (caller supplies "
                "training pipeline metrics; engine validates "
                "presence + sanity, computes nothing)")
        else:
            for metric_name, value in metrics.items():
                if not isinstance(value, Decimal):
                    findings.append(
                        f"metric '{metric_name}' value must be "
                        f"Decimal, got {type(value).__name__}")
                elif value.is_nan() or value.is_infinite():
                    findings.append(
                        f"metric '{metric_name}' value is NaN "
                        f"or infinite ({value})")

        if findings:
            return RegistrationResult(
                outcome=RegistrationOutcome.REJECTED_INVALID,
                entry=None,
                findings=tuple(findings),
                framework_refs=(
                    "ENH-281 §register_new_model_version",
                    "Per Rule 1 — all validation findings "
                    "surfaced (not just first)",
                    "Per Rule 7 — engine never persists the "
                    "entry; rejection means caller must fix "
                    "inputs before retrying",
                ))

        entry = ModelRegistryEntry(
            model_id=model_id.strip(),
            version=version.strip(),
            artifact_hash=artifact_hash.lower(),
            training_data_hash=training_data_hash.lower(),
            framework=framework,
            framework_version=framework_version.strip(),
            metrics=dict(metrics),
            owner=owner.strip(),
            status=ModelStatus.PROPOSED,
            created_by=created_by.strip(),
            created_at_iso=created_at_iso.strip(),
            training_completed_at_iso=(
                training_completed_at_iso),
            notes=notes,
        )

        return RegistrationResult(
            outcome=RegistrationOutcome.REGISTERED,
            entry=entry,
            findings=(),
            framework_refs=(
                "ENH-281 §register_new_model_version",
                "Initial status: PROPOSED — caller persists + "
                "transitions through SHADOW → ACTIVE via "
                "validate_promotion_readiness gates",
                "Google MLOps reference architecture (2020) — "
                "model registry with version + artifact hash",
                "ML Test Score (Breck et al. 2017) — "
                "production-readiness fields tracked",
                "Per Rule 1 — all metadata surfaced + "
                "framework_refs preserved",
                "Per Rule 7 — engine constructs entry; caller "
                "persists",
            ),
        )

    # ─── 2. Lookup active version ──────────────────────────────
    def lookup_active_version(
        self,
        model_id: str,
        registry: Sequence[ModelRegistryEntry],
    ) -> ActiveLookupResult:
        """Return single ACTIVE entry for model_id (or None).
        Surfaces governance breach if multiple ACTIVE entries
        exist for the same model_id.
        """
        actives = [
            e for e in registry
            if e.model_id == model_id
            and e.status == ModelStatus.ACTIVE]

        multi_violation = len(actives) > 1
        active_entry = (
            actives[0] if len(actives) == 1
            else (actives[0] if multi_violation else None))

        return ActiveLookupResult(
            model_id=model_id,
            active_entry=active_entry,
            multiple_active_violation=multi_violation,
            active_count=len(actives),
            framework_refs=(
                "ENH-281 §lookup_active_version",
                "Per Rule 1 — multiple_active_violation "
                "surfaced explicitly when active_count > 1 "
                "(governance breach — operations must "
                "demote all but one)",
                "Per Rule 7 — engine surfaces breach; never "
                "auto-demotes (operator decides which active "
                "to keep)",
            ),
        )

    # ─── 3. List versions ──────────────────────────────────────
    def list_versions(
        self,
        model_id: str,
        registry: Sequence[ModelRegistryEntry],
        status_filter: Optional[
            Sequence[ModelStatus]] = None,
    ) -> Tuple[ModelRegistryEntry, ...]:
        """Return entries for model_id, optionally filtered by
        status, sorted most-recent first by created_at_iso."""
        matches = [
            e for e in registry if e.model_id == model_id]
        if status_filter is not None:
            allowed = set(status_filter)
            matches = [
                e for e in matches if e.status in allowed]
        return tuple(sorted(
            matches,
            key=lambda e: e.created_at_iso,
            reverse=True))

    # ─── 4. Compare versions ───────────────────────────────────
    def compare_versions(
        self,
        version_a: ModelRegistryEntry,
        version_b: ModelRegistryEntry,
    ) -> VersionComparison:
        """Diagnostic delta surface — metric_deltas (per shared
        metric name) + framework match flags + hash match flags.
        Per Rule 7, engine never recommends one over the other.
        """
        all_metrics = (
            set(version_a.metrics.keys())
            | set(version_b.metrics.keys()))

        deltas: list = []
        for m in sorted(all_metrics):
            va = version_a.metrics.get(m)
            vb = version_b.metrics.get(m)
            if va is not None and vb is not None:
                delta = vb - va
            else:
                delta = None
            deltas.append(MetricDelta(
                metric_name=m,
                version_a_value=va,
                version_b_value=vb,
                delta=delta))

        return VersionComparison(
            version_a_id=(
                f"{version_a.model_id}@{version_a.version}"),
            version_b_id=(
                f"{version_b.model_id}@{version_b.version}"),
            metric_deltas=tuple(deltas),
            framework_match=(
                version_a.framework == version_b.framework),
            framework_version_match=(
                version_a.framework_version
                == version_b.framework_version),
            training_data_hash_match=(
                version_a.training_data_hash
                == version_b.training_data_hash),
            artifact_hash_match=(
                version_a.artifact_hash
                == version_b.artifact_hash),
            framework_refs=(
                "ENH-281 §compare_versions",
                "Per Rule 1 — metric deltas + framework match "
                "+ hash match all surface explicitly",
                "Per Rule 7 — engine surfaces delta; never "
                "recommends one version over the other (that "
                "is validate_promotion_readiness territory, "
                "and even there engine surfaces findings; "
                "operator decides)",
            ),
        )

    # ─── 5. Validate promotion readiness ───────────────────────
    def validate_promotion_readiness(
        self,
        candidate: ModelRegistryEntry,
        current_active: Optional[ModelRegistryEntry],
        promotion_gates: Sequence[PromotionGate],
    ) -> PromotionReadinessAssessment:
        """Evaluate caller-supplied promotion gates against
        candidate (and current_active for non-regression gates).
        """
        findings: list = []

        for gate in promotion_gates:
            f = self._evaluate_gate(
                gate, candidate, current_active)
            findings.append(f)

        # Outcome
        has_fail = any(
            f.severity == GateFindingSeverity.FAIL
            for f in findings)
        has_insufficient = any(
            f.severity == GateFindingSeverity.INSUFFICIENT_DATA
            for f in findings)
        if has_fail:
            outcome = PromotionReadinessOutcome.BLOCKED
        elif has_insufficient:
            outcome = (
                PromotionReadinessOutcome.INSUFFICIENT_DATA)
        else:
            outcome = PromotionReadinessOutcome.READY

        return PromotionReadinessAssessment(
            candidate_id=(
                f"{candidate.model_id}@{candidate.version}"),
            current_active_id=(
                f"{current_active.model_id}@{current_active.version}"
                if current_active else None),
            outcome=outcome,
            findings=tuple(findings),
            framework_refs=(
                "ENH-281 §validate_promotion_readiness",
                "Three gate types: MINIMUM_METRIC, "
                "NON_REGRESSION, METADATA_REQUIRED",
                "Per Rule 1 — every gate finding surfaced "
                "(not just first failure)",
                "Per Rule 7 — engine surfaces readiness; "
                "operator promotes (engine never auto-"
                "transitions PROPOSED → SHADOW → ACTIVE)",
                "Google MLOps reference architecture (2020) "
                "— gated promotion via metric thresholds",
                "ML Test Score (Breck et al. 2017) — "
                "non-regression discipline",
            ),
        )

    def _evaluate_gate(
        self,
        gate: PromotionGate,
        candidate: ModelRegistryEntry,
        current_active: Optional[ModelRegistryEntry],
    ) -> GateFinding:
        if gate.gate_type == GateType.MINIMUM_METRIC:
            return self._eval_minimum_metric(gate, candidate)
        if gate.gate_type == GateType.NON_REGRESSION:
            return self._eval_non_regression(
                gate, candidate, current_active)
        if gate.gate_type == GateType.METADATA_REQUIRED:
            return self._eval_metadata_required(
                gate, candidate)
        # Should never reach here given enum coverage
        return GateFinding(
            gate_id=gate.gate_id,
            gate_type=gate.gate_type,
            severity=GateFindingSeverity.INSUFFICIENT_DATA,
            description=(
                f"Unknown gate type: {gate.gate_type}"),
            expected="known gate type",
            observed=str(gate.gate_type))

    def _eval_minimum_metric(
        self, gate: PromotionGate,
        candidate: ModelRegistryEntry,
    ) -> GateFinding:
        if gate.metric_name is None or gate.threshold is None:
            return GateFinding(
                gate_id=gate.gate_id,
                gate_type=gate.gate_type,
                severity=GateFindingSeverity.INSUFFICIENT_DATA,
                description=(
                    "MINIMUM_METRIC gate missing metric_name "
                    "or threshold"),
                expected=(
                    "metric_name and threshold both populated"),
                observed=(
                    f"metric_name={gate.metric_name}, "
                    f"threshold={gate.threshold}"))
        candidate_value = candidate.metrics.get(
            gate.metric_name)
        if candidate_value is None:
            return GateFinding(
                gate_id=gate.gate_id,
                gate_type=gate.gate_type,
                severity=(
                    GateFindingSeverity.INSUFFICIENT_DATA),
                description=(
                    f"Candidate has no '{gate.metric_name}' "
                    f"metric — cannot evaluate gate"),
                expected=(
                    f"candidate.metrics['{gate.metric_name}'] "
                    f"present"),
                observed="missing")
        comparison = gate.comparison or GateComparison.GTE
        if comparison == GateComparison.GTE:
            passed = candidate_value >= gate.threshold
            cmp_str = "≥"
        else:  # LTE
            passed = candidate_value <= gate.threshold
            cmp_str = "≤"
        return GateFinding(
            gate_id=gate.gate_id,
            gate_type=gate.gate_type,
            severity=(
                GateFindingSeverity.PASS if passed
                else GateFindingSeverity.FAIL),
            description=gate.description,
            expected=(
                f"{gate.metric_name} {cmp_str} "
                f"{gate.threshold}"),
            observed=(
                f"{gate.metric_name} = {candidate_value}"))

    def _eval_non_regression(
        self, gate: PromotionGate,
        candidate: ModelRegistryEntry,
        current_active: Optional[ModelRegistryEntry],
    ) -> GateFinding:
        if gate.metric_name is None:
            return GateFinding(
                gate_id=gate.gate_id,
                gate_type=gate.gate_type,
                severity=(
                    GateFindingSeverity.INSUFFICIENT_DATA),
                description=(
                    "NON_REGRESSION gate missing metric_name"),
                expected="metric_name populated",
                observed="missing")
        if current_active is None:
            return GateFinding(
                gate_id=gate.gate_id,
                gate_type=gate.gate_type,
                severity=(
                    GateFindingSeverity.INSUFFICIENT_DATA),
                description=(
                    "No current_active to compare against — "
                    "non-regression gate skipped (this is "
                    "expected for the very first version of "
                    "a model)"),
                expected=(
                    "current_active provided for "
                    "non-regression comparison"),
                observed="None")
        candidate_value = candidate.metrics.get(
            gate.metric_name)
        active_value = current_active.metrics.get(
            gate.metric_name)
        if candidate_value is None or active_value is None:
            return GateFinding(
                gate_id=gate.gate_id,
                gate_type=gate.gate_type,
                severity=(
                    GateFindingSeverity.INSUFFICIENT_DATA),
                description=(
                    f"Cannot compare '{gate.metric_name}': "
                    f"candidate={candidate_value}, "
                    f"active={active_value}"),
                expected=(
                    "both candidate and active have the "
                    "metric"),
                observed=(
                    f"candidate={candidate_value}, "
                    f"active={active_value}"))
        tolerance = (
            gate.regression_tolerance or Decimal("0"))
        comparison = gate.comparison or GateComparison.GTE
        if comparison == GateComparison.GTE:
            # Higher-is-better; candidate must not regress
            # below active - tolerance
            min_acceptable = active_value - tolerance
            passed = candidate_value >= min_acceptable
            expected_str = (
                f"{gate.metric_name} ≥ {active_value} - "
                f"{tolerance} = {min_acceptable}")
        else:  # LTE — lower-is-better; candidate must not
            # regress above active + tolerance
            max_acceptable = active_value + tolerance
            passed = candidate_value <= max_acceptable
            expected_str = (
                f"{gate.metric_name} ≤ {active_value} + "
                f"{tolerance} = {max_acceptable}")
        return GateFinding(
            gate_id=gate.gate_id,
            gate_type=gate.gate_type,
            severity=(
                GateFindingSeverity.PASS if passed
                else GateFindingSeverity.FAIL),
            description=gate.description,
            expected=expected_str,
            observed=(
                f"{gate.metric_name} = {candidate_value}"))

    def _eval_metadata_required(
        self, gate: PromotionGate,
        candidate: ModelRegistryEntry,
    ) -> GateFinding:
        if not gate.required_field:
            return GateFinding(
                gate_id=gate.gate_id,
                gate_type=gate.gate_type,
                severity=(
                    GateFindingSeverity.INSUFFICIENT_DATA),
                description=(
                    "METADATA_REQUIRED gate missing "
                    "required_field"),
                expected="required_field populated",
                observed="empty")
        # Use getattr to read structural fields
        value = getattr(candidate, gate.required_field, None)
        present = value is not None and (
            not isinstance(value, str) or value.strip() != "")
        return GateFinding(
            gate_id=gate.gate_id,
            gate_type=gate.gate_type,
            severity=(
                GateFindingSeverity.PASS if present
                else GateFindingSeverity.FAIL),
            description=gate.description,
            expected=(
                f"{gate.required_field} present and non-empty"),
            observed=(
                f"{gate.required_field} = "
                f"{value!r}" if value is not None
                else f"{gate.required_field} missing"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

_VALID_HASH_A = "a" * 64
_VALID_HASH_B = "b" * 64


def _make_entry(
    model_id="doc_classifier",
    version="1.0.0",
    metrics=None,
    status=ModelStatus.ACTIVE,
    created_at="2026-04-01T00:00:00Z",
    framework="sklearn",
):
    return ModelRegistryEntry(
        model_id=model_id, version=version,
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework=framework,
        framework_version="1.5.1",
        metrics=metrics or {
            "accuracy": Decimal("0.85"),
            "f1": Decimal("0.82")},
        owner="ml-team@bank",
        status=status,
        created_by="trainer",
        created_at_iso=created_at,
        training_completed_at_iso="2026-04-01T00:00:00Z",
        notes="")


# ─── Registration tests ────────────────────────────────────────

def _test_register_clean():
    eng = MLOpsModelRegistryEngine()
    r = eng.register_new_model_version(
        model_id="doc_classifier",
        version="1.0.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="sklearn",
        framework_version="1.5.1",
        metrics={
            "accuracy": Decimal("0.87"),
            "f1": Decimal("0.85")},
        owner="ml-team@bank",
        created_by="trainer",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r.outcome == RegistrationOutcome.REGISTERED
    assert r.entry is not None
    assert r.entry.status == ModelStatus.PROPOSED
    assert r.entry.metrics["accuracy"] == Decimal("0.87")


def _test_register_invalid_hash():
    eng = MLOpsModelRegistryEngine()
    r = eng.register_new_model_version(
        model_id="x", version="1.0.0",
        artifact_hash="not-a-hash",
        training_data_hash=_VALID_HASH_B,
        framework="sklearn", framework_version="1.5",
        metrics={"a": Decimal("1")},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r.outcome == RegistrationOutcome.REJECTED_INVALID
    assert any(
        "artifact_hash" in f for f in r.findings)


def _test_register_unknown_framework():
    eng = MLOpsModelRegistryEngine()
    r = eng.register_new_model_version(
        model_id="x", version="1.0.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="proprietary_blackbox",
        framework_version="1.0",
        metrics={"a": Decimal("1")},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r.outcome == RegistrationOutcome.REJECTED_INVALID


def _test_register_caller_extends_frameworks():
    eng = MLOpsModelRegistryEngine(
        recognized_frameworks=("proprietary_blackbox",))
    r = eng.register_new_model_version(
        model_id="x", version="1.0.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="proprietary_blackbox",
        framework_version="1.0",
        metrics={"a": Decimal("1")},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r.outcome == RegistrationOutcome.REGISTERED
    # 'sklearn' should now be REJECTED since we replaced
    r2 = eng.register_new_model_version(
        model_id="x", version="1.0.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="sklearn",
        framework_version="1.0",
        metrics={"a": Decimal("1")},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r2.outcome == RegistrationOutcome.REJECTED_INVALID


def _test_register_nan_metric():
    eng = MLOpsModelRegistryEngine()
    nan_decimal = Decimal("NaN")
    r = eng.register_new_model_version(
        model_id="x", version="1.0.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="sklearn",
        framework_version="1.0",
        metrics={"accuracy": nan_decimal},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r.outcome == RegistrationOutcome.REJECTED_INVALID


def _test_register_empty_metrics():
    eng = MLOpsModelRegistryEngine()
    r = eng.register_new_model_version(
        model_id="x", version="1.0.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="sklearn",
        framework_version="1.0",
        metrics={},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    assert r.outcome == RegistrationOutcome.REJECTED_INVALID


# ─── Lookup tests ──────────────────────────────────────────────

def _test_lookup_active_single():
    eng = MLOpsModelRegistryEngine()
    registry = (
        _make_entry(version="1.0.0", status=ModelStatus.ACTIVE),
        _make_entry(
            version="0.9.0", status=ModelStatus.DEPRECATED),
    )
    r = eng.lookup_active_version("doc_classifier", registry)
    assert r.active_entry is not None
    assert r.active_entry.version == "1.0.0"
    assert r.multiple_active_violation is False
    assert r.active_count == 1


def _test_lookup_active_none():
    eng = MLOpsModelRegistryEngine()
    registry = (
        _make_entry(
            version="1.0.0", status=ModelStatus.PROPOSED),)
    r = eng.lookup_active_version("doc_classifier", registry)
    assert r.active_entry is None
    assert r.active_count == 0


def _test_lookup_active_multiple_violation():
    """Two ACTIVE entries for same model_id = governance breach."""
    eng = MLOpsModelRegistryEngine()
    registry = (
        _make_entry(version="1.0.0", status=ModelStatus.ACTIVE),
        _make_entry(version="2.0.0", status=ModelStatus.ACTIVE),
    )
    r = eng.lookup_active_version("doc_classifier", registry)
    assert r.multiple_active_violation is True
    assert r.active_count == 2


# ─── List versions tests ───────────────────────────────────────

def _test_list_versions_no_filter():
    eng = MLOpsModelRegistryEngine()
    registry = (
        _make_entry(
            version="1.0.0",
            created_at="2026-04-01T00:00:00Z"),
        _make_entry(
            version="2.0.0",
            created_at="2026-05-01T00:00:00Z"),
        _make_entry(
            model_id="other", version="0.5.0",
            created_at="2026-04-15T00:00:00Z"),
    )
    versions = eng.list_versions("doc_classifier", registry)
    # 2 matches, sorted most-recent first
    assert len(versions) == 2
    assert versions[0].version == "2.0.0"
    assert versions[1].version == "1.0.0"


def _test_list_versions_status_filter():
    eng = MLOpsModelRegistryEngine()
    registry = (
        _make_entry(version="1.0.0", status=ModelStatus.ACTIVE),
        _make_entry(
            version="2.0.0", status=ModelStatus.PROPOSED),
        _make_entry(
            version="0.9.0", status=ModelStatus.DEPRECATED),
    )
    versions = eng.list_versions(
        "doc_classifier", registry,
        status_filter=(ModelStatus.ACTIVE,
                       ModelStatus.PROPOSED))
    assert len(versions) == 2
    statuses = {e.status for e in versions}
    assert ModelStatus.ACTIVE in statuses
    assert ModelStatus.PROPOSED in statuses
    assert ModelStatus.DEPRECATED not in statuses


# ─── Compare versions tests ────────────────────────────────────

def _test_compare_metric_deltas():
    eng = MLOpsModelRegistryEngine()
    a = _make_entry(version="1.0.0", metrics={
        "accuracy": Decimal("0.85"),
        "f1": Decimal("0.82")})
    b = _make_entry(version="2.0.0", metrics={
        "accuracy": Decimal("0.88"),
        "f1": Decimal("0.80")})
    c = eng.compare_versions(a, b)
    assert len(c.metric_deltas) == 2
    deltas_by_name = {
        d.metric_name: d for d in c.metric_deltas}
    # accuracy: 0.88 - 0.85 = 0.03 (improvement)
    assert deltas_by_name["accuracy"].delta == Decimal("0.03")
    # f1: 0.80 - 0.82 = -0.02 (regression)
    assert deltas_by_name["f1"].delta == Decimal("-0.02")


def _test_compare_framework_mismatch():
    eng = MLOpsModelRegistryEngine()
    a = _make_entry(version="1.0", framework="sklearn")
    b = _make_entry(version="2.0", framework="torch")
    c = eng.compare_versions(a, b)
    assert c.framework_match is False


def _test_compare_metric_only_in_one():
    eng = MLOpsModelRegistryEngine()
    a = _make_entry(version="1.0", metrics={
        "accuracy": Decimal("0.85")})
    b = _make_entry(version="2.0", metrics={
        "accuracy": Decimal("0.88"),
        "auc": Decimal("0.92")})
    c = eng.compare_versions(a, b)
    deltas_by_name = {
        d.metric_name: d for d in c.metric_deltas}
    # 'auc' present only in b → delta is None
    assert deltas_by_name["auc"].delta is None
    assert deltas_by_name["auc"].version_a_value is None
    assert deltas_by_name["auc"].version_b_value == (
        Decimal("0.92"))


# ─── Promotion readiness tests ─────────────────────────────────

def _test_promotion_minimum_metric_pass():
    eng = MLOpsModelRegistryEngine()
    candidate = _make_entry(metrics={
        "accuracy": Decimal("0.87")})
    gate = PromotionGate(
        gate_id="G1",
        gate_type=GateType.MINIMUM_METRIC,
        description="Accuracy must be ≥ 0.85",
        metric_name="accuracy",
        threshold=Decimal("0.85"),
        comparison=GateComparison.GTE)
    a = eng.validate_promotion_readiness(
        candidate, None, (gate,))
    assert a.outcome == PromotionReadinessOutcome.READY


def _test_promotion_minimum_metric_fail():
    eng = MLOpsModelRegistryEngine()
    candidate = _make_entry(metrics={
        "accuracy": Decimal("0.80")})
    gate = PromotionGate(
        gate_id="G1",
        gate_type=GateType.MINIMUM_METRIC,
        description="Accuracy must be ≥ 0.85",
        metric_name="accuracy",
        threshold=Decimal("0.85"),
        comparison=GateComparison.GTE)
    a = eng.validate_promotion_readiness(
        candidate, None, (gate,))
    assert a.outcome == PromotionReadinessOutcome.BLOCKED
    assert a.findings[0].severity == GateFindingSeverity.FAIL


def _test_promotion_non_regression_pass():
    eng = MLOpsModelRegistryEngine()
    active = _make_entry(version="1.0", metrics={
        "accuracy": Decimal("0.85")})
    candidate = _make_entry(version="2.0", metrics={
        "accuracy": Decimal("0.84")})  # regression of 0.01
    gate = PromotionGate(
        gate_id="G2",
        gate_type=GateType.NON_REGRESSION,
        description="Accuracy regression ≤ 2pp",
        metric_name="accuracy",
        regression_tolerance=Decimal("0.02"),  # tol = 2pp
        comparison=GateComparison.GTE)
    a = eng.validate_promotion_readiness(
        candidate, active, (gate,))
    # 0.84 ≥ 0.85 - 0.02 = 0.83 → PASS
    assert a.outcome == PromotionReadinessOutcome.READY


def _test_promotion_non_regression_fail():
    eng = MLOpsModelRegistryEngine()
    active = _make_entry(version="1.0", metrics={
        "accuracy": Decimal("0.85")})
    candidate = _make_entry(version="2.0", metrics={
        "accuracy": Decimal("0.80")})  # 5pp regression
    gate = PromotionGate(
        gate_id="G2",
        gate_type=GateType.NON_REGRESSION,
        description="Accuracy regression ≤ 2pp",
        metric_name="accuracy",
        regression_tolerance=Decimal("0.02"),
        comparison=GateComparison.GTE)
    a = eng.validate_promotion_readiness(
        candidate, active, (gate,))
    # 0.80 ≥ 0.83? No → FAIL
    assert a.outcome == PromotionReadinessOutcome.BLOCKED


def _test_promotion_non_regression_no_active():
    """First version of a model — no active baseline — gate
    skipped with INSUFFICIENT_DATA."""
    eng = MLOpsModelRegistryEngine()
    candidate = _make_entry(version="1.0", metrics={
        "accuracy": Decimal("0.85")})
    gate = PromotionGate(
        gate_id="G2",
        gate_type=GateType.NON_REGRESSION,
        description="Non-regression",
        metric_name="accuracy",
        regression_tolerance=Decimal("0.02"))
    a = eng.validate_promotion_readiness(
        candidate, None, (gate,))
    assert a.outcome == (
        PromotionReadinessOutcome.INSUFFICIENT_DATA)


def _test_promotion_metadata_required():
    eng = MLOpsModelRegistryEngine()
    candidate = _make_entry()
    gate_pass = PromotionGate(
        gate_id="MD1",
        gate_type=GateType.METADATA_REQUIRED,
        description="Owner required",
        required_field="owner")
    gate_fail = PromotionGate(
        gate_id="MD2",
        gate_type=GateType.METADATA_REQUIRED,
        description="promoted_to_active_at_iso required",
        required_field="promoted_to_active_at_iso")
    a = eng.validate_promotion_readiness(
        candidate, None, (gate_pass, gate_fail))
    # owner='ml-team@bank' present → PASS
    # promoted_to_active_at_iso=None → FAIL
    findings_by_id = {
        f.gate_id: f for f in a.findings}
    assert findings_by_id["MD1"].severity == (
        GateFindingSeverity.PASS)
    assert findings_by_id["MD2"].severity == (
        GateFindingSeverity.FAIL)
    assert a.outcome == PromotionReadinessOutcome.BLOCKED


def _test_promotion_mixed_outcomes():
    """All 3 gate types in one assessment."""
    eng = MLOpsModelRegistryEngine()
    active = _make_entry(version="1.0", metrics={
        "accuracy": Decimal("0.85")})
    candidate = _make_entry(version="2.0", metrics={
        "accuracy": Decimal("0.87")})
    gates = (
        PromotionGate(
            gate_id="MIN",
            gate_type=GateType.MINIMUM_METRIC,
            description="≥ 0.85",
            metric_name="accuracy",
            threshold=Decimal("0.85")),
        PromotionGate(
            gate_id="REG",
            gate_type=GateType.NON_REGRESSION,
            description="No regression",
            metric_name="accuracy",
            regression_tolerance=Decimal("0.01")),
        PromotionGate(
            gate_id="META",
            gate_type=GateType.METADATA_REQUIRED,
            description="Owner present",
            required_field="owner"),
    )
    a = eng.validate_promotion_readiness(
        candidate, active, gates)
    assert a.outcome == PromotionReadinessOutcome.READY
    assert all(
        f.severity == GateFindingSeverity.PASS
        for f in a.findings)


# ─── Discipline + provenance tests ─────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = MLOpsModelRegistryEngine()
    entry = _make_entry()
    original_metrics = dict(entry.metrics)
    eng.lookup_active_version(
        "doc_classifier", (entry,))
    eng.list_versions("doc_classifier", (entry,))
    assert entry.metrics == original_metrics


def _test_full_provenance():
    eng = MLOpsModelRegistryEngine()
    r = eng.register_new_model_version(
        model_id="x", version="1.0",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        framework="sklearn",
        framework_version="1.0",
        metrics={"a": Decimal("1")},
        owner="o", created_by="c",
        created_at_iso="2026-05-01T00:00:00Z")
    refs = " / ".join(r.framework_refs)
    assert "ENH-281" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs


def _test_caller_supplied_data_discipline():
    """Engine bundles no registry data; caller passes everything."""
    eng = MLOpsModelRegistryEngine()
    # Empty registry returns no actives, no violations
    r = eng.lookup_active_version("doc_classifier", ())
    assert r.active_entry is None
    assert r.active_count == 0
    versions = eng.list_versions("doc_classifier", ())
    assert versions == ()


def self_test() -> None:
    tests = [
        _test_register_clean,
        _test_register_invalid_hash,
        _test_register_unknown_framework,
        _test_register_caller_extends_frameworks,
        _test_register_nan_metric,
        _test_register_empty_metrics,
        _test_lookup_active_single,
        _test_lookup_active_none,
        _test_lookup_active_multiple_violation,
        _test_list_versions_no_filter,
        _test_list_versions_status_filter,
        _test_compare_metric_deltas,
        _test_compare_framework_mismatch,
        _test_compare_metric_only_in_one,
        _test_promotion_minimum_metric_pass,
        _test_promotion_minimum_metric_fail,
        _test_promotion_non_regression_pass,
        _test_promotion_non_regression_fail,
        _test_promotion_non_regression_no_active,
        _test_promotion_metadata_required,
        _test_promotion_mixed_outcomes,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_caller_supplied_data_discipline,
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
            f"✗ mlops_model_registry self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ mlops_model_registry self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

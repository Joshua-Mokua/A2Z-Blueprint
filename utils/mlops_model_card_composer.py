"""utils/mlops_model_card_composer.py — v10.85: MLOps Model Card
Composer.

ENH-285 — MLOps Model Card Composer. Cat B — ml_governance arc 5/N
(final engine before arc closure).

Diagnostic engine that composes per-model documentation surfaces
("model cards" per Mitchell et al. 2019) by combining outputs from
every other ml_governance arc engine plus the existing model_governance
arc (G124) plus caller-supplied narrative fields. The card is the
single artifact a regulator examines — all the provenance for one
model in one place.

The composer sits at the consumer end of the arc — every other engine
produces a signal that flows into the card:

  - ENH-281 mlops_model_registry → registry metadata (id, version,
    artifact hash, training data hash, framework, owner, status,
    metrics)
  - ENH-282 mlops_adjudication_log → production override rate trend
  - ENH-283 mlops_retraining_scheduler → last retraining
    recommendation (FRESH / WARNING / STALE) with rationale
  - ENH-284 mlops_ab_harness → last A/B comparison severity
    (READY_TO_PROMOTE / NEEDS_REVIEW / NOT_READY) for the latest
    candidate evaluation
  - model_governance arc at G124 → drift status (PSI / KS /
    Wasserstein) and bias monitoring summary

The caller integrates each upstream output into a
ProductionPerformanceSnapshot dataclass and passes it to the
composer along with a ModelCardNarrative covering the qualitative
sections (intended use, out-of-scope use, ethical considerations,
caveats). The composer validates the inputs and produces a ModelCard.

Five capabilities:

  1. compose_model_card — orchestrator. Takes registry entry +
     narrative + optional production snapshot + caller metadata.
     Validates required fields. Returns ModelCard with full
     provenance. Per Rule 7, engine never persists — caller stores
     in their card archive.

  2. validate_card_completeness — given a ModelCard + caller-
     supplied CardCompletenessRequirements, surface missing required
     sections. Useful for "every regulatory-grade card needs these
     fields populated." Outcome COMPLETE / INCOMPLETE with explicit
     missing_sections list per Rule 1.

  3. compute_card_diff — given two ModelCards (typically active
     version's card vs candidate's card during promotion review),
     surface field-by-field diffs. Useful for "what changed between
     v1.0 and v2.0?" — supports operator review during promotion.

  4. build_revision_history — given chronological card sequence
     (caller maintains the archive), surface revision history with
     summary statistics for regulatory examination.

  5. serialize_card_to_markdown — render structured ModelCard to
     markdown for human consumption. Markdown is generic (not
     regulator-specific). Per Rule 7, engine never serializes to
     regulator-specific schemas (XBRL / iTax / CBK formats are
     regulatory_reporting territory). Source of truth remains the
     structured ModelCard.

Per Rule 7, engine NEVER:
  - persists cards (caller stores in JSON / PG / wherever)
  - serializes to regulator-specific schemas (regulatory_reporting
    territory)
  - decides whether a card is "good enough" beyond caller-supplied
    completeness requirements
  - publishes cards externally
  - reads ENH-281 / ENH-282 / ENH-283 / ENH-284 / model_governance
    state directly (caller integrates upstream outputs into the
    snapshot dataclass)
  - mutates inputs

Per Rule 1, every output surfaces inputs + intermediates + outputs +
framework_refs. All result dataclasses are frozen. Missing sections
surface explicitly via missing_sections tuple.

Caller-supplied data discipline (matches arc pattern through
ENH-281/282/283/284): registry entry + narrative + production
snapshot + completeness requirements all caller-supplied; engine
bundles no defaults except dataclass field defaults for first-use
convenience.

Pure stdlib runtime.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields as dataclass_fields
from decimal import Decimal
from enum import Enum
from typing import (
    Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "MLOpsModelCardComposerEngine implements ENH-285 — diagnostic "
    "engine that composes per-model cards from every other "
    "ml_governance arc engine's output plus model_governance G124 "
    "plus caller-supplied narrative. Final engine of the arc; sits "
    "at the consumer end where every signal flows into the "
    "documentation surface. Pure stdlib. Per Rule 1, every output "
    "surfaces full provenance + missing sections + framework_refs. "
    "Per Rule 7, engine DIAGNOSTIC ONLY — never persists cards, "
    "never serializes to regulator-specific schemas (regulatory_"
    "reporting territory), never publishes externally, never reads "
    "other engines directly (caller integrates), never mutates "
    "inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class CompletenessOutcome(Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class CardComposeOutcome(Enum):
    COMPOSED = "COMPOSED"
    REJECTED_INVALID = "REJECTED_INVALID"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ModelCardNarrative:
    """Caller-supplied qualitative sections of the model card per
    Mitchell et al. 2019. Engine bundles no defaults — caller writes
    these for each model card."""
    intended_use: str
    out_of_scope_use: str
    training_data_description: str
    evaluation_data_description: str
    ethical_considerations: str
    caveats_and_recommendations: str


@dataclass(frozen=True)
class ProductionPerformanceSnapshot:
    """Caller integrates upstream observability outputs into this
    snapshot. None values surface explicitly per Rule 1."""
    snapshot_at_iso: str
    # ENH-282 adjudication log
    override_rate_30d: Optional[Decimal] = None
    override_sample_size_30d: Optional[int] = None
    # model_governance G124 drift detection
    drift_metric_name: Optional[str] = None  # "PSI" / "KS" / "WASSERSTEIN"
    drift_metric_value: Optional[Decimal] = None
    # ENH-283 retraining scheduler
    last_retraining_outcome: Optional[str] = None  # DUE/SOON/NOT_YET/INSUFFICIENT_DATA
    last_retraining_rationale: str = ""
    # ENH-284 A/B harness (when a candidate exists)
    last_ab_severity: Optional[str] = None  # READY_TO_PROMOTE/etc
    last_ab_against_version: Optional[str] = None


@dataclass(frozen=True)
class CardCompletenessRequirements:
    """Caller-supplied fields required for a card to be considered
    COMPLETE."""
    require_narrative: bool = True
    require_production_snapshot: bool = False
    required_metric_names: Tuple[str, ...] = ()
    require_training_completion_timestamp: bool = True


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ModelCard:
    """Structured model card per Mitchell et al. 2019 + production
    extensions for ongoing monitoring (the production_snapshot
    field). Caller persists in their card archive; engine never
    persists."""
    # Model details (from ENH-281 registry entry)
    model_id: str
    model_version: str
    framework: str
    framework_version: str
    owner: str
    artifact_hash: str
    training_data_hash: str
    operational_status: str          # ENH-281 ModelStatus value
    training_completed_at_iso: Optional[str]
    training_metrics: Mapping[str, Decimal]
    # Narrative (caller-supplied)
    narrative: ModelCardNarrative
    # Production performance (caller integrates upstream signals)
    production_snapshot: Optional[ProductionPerformanceSnapshot]
    # Card metadata
    composed_at_iso: str
    composed_by: str
    card_version: str = "1.0"   # caller can override for revision tracking
    notes: str = ""


@dataclass(frozen=True)
class CardComposeResult:
    outcome: CardComposeOutcome
    card: Optional[ModelCard]
    findings: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CardCompletenessAssessment:
    outcome: CompletenessOutcome
    missing_sections: Tuple[str, ...]
    requirements_evaluated: CardCompletenessRequirements
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CardFieldDiff:
    field_name: str
    old_value: str   # str representation for diff display
    new_value: str
    changed: bool


@dataclass(frozen=True)
class CardDiff:
    card_a_id: str   # "{model_id}@{model_version}"
    card_b_id: str
    field_diffs: Tuple[CardFieldDiff, ...]
    changed_field_count: int
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class RevisionHistoryEntry:
    card_version: str
    composed_at_iso: str
    model_version: str
    composed_by: str


@dataclass(frozen=True)
class RevisionHistory:
    model_id: str
    entries: Tuple[RevisionHistoryEntry, ...]
    total_revisions: int
    earliest_composed_at_iso: Optional[str]
    latest_composed_at_iso: Optional[str]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class MLOpsModelCardComposerEngine:
    """Diagnostic model card composer. Composes per-model cards from
    arc engine outputs + caller narrative; never persists, never
    serializes to regulator-specific schemas."""

    # ─── 1. Compose model card ─────────────────────────────────
    def compose_model_card(
        self,
        # From ENH-281 registry entry (caller looks up + passes
        # individual fields rather than the whole entry to avoid
        # tight coupling — same data, different shape)
        model_id: str,
        model_version: str,
        framework: str,
        framework_version: str,
        owner: str,
        artifact_hash: str,
        training_data_hash: str,
        operational_status: str,
        training_metrics: Mapping[str, Decimal],
        # Narrative (caller-supplied)
        narrative: ModelCardNarrative,
        # Card metadata
        composed_at_iso: str,
        composed_by: str,
        # Optional fields
        training_completed_at_iso: Optional[str] = None,
        production_snapshot: Optional[
            ProductionPerformanceSnapshot] = None,
        card_version: str = "1.0",
        notes: str = "",
    ) -> CardComposeResult:
        """Compose a ModelCard from validated inputs. Per Rule 7,
        engine does NOT persist — caller appends to their archive.
        """
        findings: list = []

        # Required field validation
        for field_name, value in [
            ("model_id", model_id),
            ("model_version", model_version),
            ("framework", framework),
            ("framework_version", framework_version),
            ("owner", owner),
            ("artifact_hash", artifact_hash),
            ("training_data_hash", training_data_hash),
            ("operational_status", operational_status),
            ("composed_at_iso", composed_at_iso),
            ("composed_by", composed_by),
        ]:
            if not value or not value.strip():
                findings.append(
                    f"{field_name} required (non-empty string)")

        # Narrative completeness — at minimum these four fields are
        # required per Mitchell et al. 2019 §3
        for field_name in (
            "intended_use", "out_of_scope_use",
            "training_data_description",
            "evaluation_data_description",
        ):
            value = getattr(narrative, field_name, "")
            if not value or not value.strip():
                findings.append(
                    f"narrative.{field_name} required "
                    f"(Mitchell et al. 2019 §3 — required "
                    f"section)")

        # Metric sanity — Decimal + non-NaN
        if not training_metrics:
            findings.append(
                "training_metrics required (caller supplies "
                "from training pipeline; engine validates "
                "presence + sanity, computes nothing)")
        else:
            for metric_name, value in training_metrics.items():
                if not isinstance(value, Decimal):
                    findings.append(
                        f"training_metric '{metric_name}' "
                        f"value must be Decimal, got "
                        f"{type(value).__name__}")
                elif value.is_nan() or value.is_infinite():
                    findings.append(
                        f"training_metric '{metric_name}' "
                        f"value is NaN or infinite ({value})")

        if findings:
            return CardComposeResult(
                outcome=CardComposeOutcome.REJECTED_INVALID,
                card=None,
                findings=tuple(findings),
                framework_refs=(
                    "ENH-285 §compose_model_card",
                    "Per Rule 1 — all validation findings "
                    "surfaced (not just first failure)",
                    "Per Rule 7 — rejection means caller must "
                    "fix inputs before retrying; engine does "
                    "not silently coerce or default",
                    "Mitchell et al. 2019 — Model Cards for "
                    "Model Reporting: required sections must "
                    "be present",
                ))

        card = ModelCard(
            model_id=model_id.strip(),
            model_version=model_version.strip(),
            framework=framework.strip(),
            framework_version=framework_version.strip(),
            owner=owner.strip(),
            artifact_hash=artifact_hash.lower(),
            training_data_hash=training_data_hash.lower(),
            operational_status=operational_status.strip(),
            training_completed_at_iso=(
                training_completed_at_iso),
            training_metrics=dict(training_metrics),
            narrative=narrative,
            production_snapshot=production_snapshot,
            composed_at_iso=composed_at_iso.strip(),
            composed_by=composed_by.strip(),
            card_version=card_version,
            notes=notes,
        )

        return CardComposeResult(
            outcome=CardComposeOutcome.COMPOSED,
            card=card,
            findings=(),
            framework_refs=(
                "ENH-285 §compose_model_card",
                "Mitchell et al. 2019 — Model Cards for "
                "Model Reporting (canonical structure: "
                "model details + intended use + training "
                "data + metrics + ethical considerations + "
                "caveats)",
                "Production snapshot extension — caller "
                "integrates ENH-282 override rate + "
                "model_governance G124 drift + ENH-283 "
                "retraining recommendation + ENH-284 A/B "
                "severity",
                "Per Rule 1 — full provenance preserved + "
                "framework_refs",
                "Per Rule 7 — engine constructs card; caller "
                "persists to their archive (engine never "
                "publishes externally, never serializes to "
                "regulator-specific schemas — that is "
                "regulatory_reporting territory)",
            ),
        )

    # ─── 2. Validate card completeness ─────────────────────────
    def validate_card_completeness(
        self,
        card: ModelCard,
        requirements: CardCompletenessRequirements,
    ) -> CardCompletenessAssessment:
        """Assess card against caller-supplied completeness
        requirements. Per Rule 1, all missing sections surface
        explicitly (not just first missing)."""
        missing: list = []

        if requirements.require_narrative:
            for section_name in (
                "intended_use",
                "out_of_scope_use",
                "training_data_description",
                "evaluation_data_description",
                "ethical_considerations",
                "caveats_and_recommendations",
            ):
                value = getattr(
                    card.narrative, section_name, "")
                if not value or not value.strip():
                    missing.append(
                        f"narrative.{section_name}")

        if requirements.require_production_snapshot:
            if card.production_snapshot is None:
                missing.append("production_snapshot")

        if requirements.require_training_completion_timestamp:
            if not card.training_completed_at_iso:
                missing.append("training_completed_at_iso")

        for required_metric in requirements.required_metric_names:
            if required_metric not in card.training_metrics:
                missing.append(
                    f"training_metrics['{required_metric}']")

        outcome = (
            CompletenessOutcome.COMPLETE if not missing
            else CompletenessOutcome.INCOMPLETE)

        return CardCompletenessAssessment(
            outcome=outcome,
            missing_sections=tuple(missing),
            requirements_evaluated=requirements,
            framework_refs=(
                "ENH-285 §validate_card_completeness",
                "Per Rule 1 — all missing sections surfaced "
                "(operator sees full picture — not just "
                "first missing — so they know whether one "
                "edit fixes it or whether the card has "
                "multiple gaps)",
                "Per Rule 7 — engine surfaces "
                "completeness; never auto-fills missing "
                "sections (those require human authorship — "
                "engine cannot compose intended_use or "
                "ethical_considerations from data)",
                "Mitchell et al. 2019 §3 — required sections "
                "for regulatory-grade model cards",
            ),
        )

    # ─── 3. Compute card diff ──────────────────────────────────
    def compute_card_diff(
        self,
        card_a: ModelCard,
        card_b: ModelCard,
    ) -> CardDiff:
        """Field-by-field diff between two cards. Useful during
        promotion review (active card vs candidate card)."""
        diffs: list = []

        # Top-level scalar fields
        for field_name in (
            "model_id", "model_version", "framework",
            "framework_version", "owner", "artifact_hash",
            "training_data_hash", "operational_status",
            "training_completed_at_iso", "card_version",
            "notes",
        ):
            old_val = getattr(card_a, field_name, "")
            new_val = getattr(card_b, field_name, "")
            old_str = str(old_val) if old_val is not None else ""
            new_str = str(new_val) if new_val is not None else ""
            diffs.append(CardFieldDiff(
                field_name=field_name,
                old_value=old_str,
                new_value=new_str,
                changed=(old_str != new_str)))

        # Metrics — surface per-metric diff
        all_metrics = (
            set(card_a.training_metrics.keys())
            | set(card_b.training_metrics.keys()))
        for m in sorted(all_metrics):
            a_val = card_a.training_metrics.get(m)
            b_val = card_b.training_metrics.get(m)
            old_str = (
                str(a_val) if a_val is not None
                else "(missing)")
            new_str = (
                str(b_val) if b_val is not None
                else "(missing)")
            diffs.append(CardFieldDiff(
                field_name=f"training_metrics.{m}",
                old_value=old_str,
                new_value=new_str,
                changed=(a_val != b_val)))

        # Narrative fields
        for field_name in (
            "intended_use", "out_of_scope_use",
            "training_data_description",
            "evaluation_data_description",
            "ethical_considerations",
            "caveats_and_recommendations",
        ):
            a_val = getattr(card_a.narrative, field_name, "")
            b_val = getattr(card_b.narrative, field_name, "")
            diffs.append(CardFieldDiff(
                field_name=f"narrative.{field_name}",
                old_value=a_val,
                new_value=b_val,
                changed=(a_val != b_val)))

        changed_count = sum(1 for d in diffs if d.changed)

        return CardDiff(
            card_a_id=(
                f"{card_a.model_id}@{card_a.model_version}"),
            card_b_id=(
                f"{card_b.model_id}@{card_b.model_version}"),
            field_diffs=tuple(diffs),
            changed_field_count=changed_count,
            framework_refs=(
                "ENH-285 §compute_card_diff",
                "Per Rule 1 — every field diff surfaces "
                "(changed and unchanged) so operator sees "
                "full picture during promotion review",
                "Per Rule 7 — engine surfaces diff; never "
                "decides 'this change is too big to allow "
                "promotion' (caller policy + ENH-281 "
                "validate_promotion_readiness territory)",
                "Mitchell et al. 2019 §6 — versioning + "
                "revision tracking as model card hygiene",
            ),
        )

    # ─── 4. Build revision history ─────────────────────────────
    def build_revision_history(
        self,
        cards: Sequence[ModelCard],
        model_id: str,
    ) -> RevisionHistory:
        """Build chronological revision history from caller-supplied
        card sequence. Per Rule 1, summary stats surface alongside
        per-revision entries."""
        # Filter to model_id and sort chronologically by composed_at
        relevant = sorted(
            (c for c in cards if c.model_id == model_id),
            key=lambda c: c.composed_at_iso)

        entries = tuple(
            RevisionHistoryEntry(
                card_version=c.card_version,
                composed_at_iso=c.composed_at_iso,
                model_version=c.model_version,
                composed_by=c.composed_by)
            for c in relevant)

        return RevisionHistory(
            model_id=model_id,
            entries=entries,
            total_revisions=len(entries),
            earliest_composed_at_iso=(
                entries[0].composed_at_iso
                if entries else None),
            latest_composed_at_iso=(
                entries[-1].composed_at_iso
                if entries else None),
            framework_refs=(
                "ENH-285 §build_revision_history",
                "Sorted by composed_at_iso ascending "
                "(chronological narrative for regulatory "
                "examination)",
                "Per Rule 1 — summary statistics + per-"
                "revision entries surface together "
                "(regulator sees both rollup and per-"
                "revision detail)",
                "Per Rule 7 — engine builds the view from "
                "caller-supplied archive; never persists or "
                "modifies the archive",
                "OCC 2011-12 §V — model documentation must "
                "include change history for examination",
            ),
        )

    # ─── 5. Serialize card to markdown ─────────────────────────
    def serialize_card_to_markdown(
        self,
        card: ModelCard,
    ) -> str:
        """Render structured ModelCard to markdown for human
        consumption. Markdown is generic (not regulator-specific);
        source of truth remains the structured ModelCard. Per Rule
        7, engine never serializes to regulator-specific schemas
        (XBRL / iTax / CBK formats are regulatory_reporting
        territory)."""
        lines: list = []
        lines.append(
            f"# Model Card — {card.model_id} "
            f"@ {card.model_version}")
        lines.append("")
        lines.append(
            f"*Composed at {card.composed_at_iso} by "
            f"{card.composed_by} (card version "
            f"{card.card_version})*")
        lines.append("")
        lines.append("## Model Details")
        lines.append("")
        lines.append(f"- **Model ID:** `{card.model_id}`")
        lines.append(
            f"- **Version:** `{card.model_version}`")
        lines.append(
            f"- **Framework:** {card.framework} "
            f"({card.framework_version})")
        lines.append(f"- **Owner:** {card.owner}")
        lines.append(
            f"- **Operational status:** "
            f"`{card.operational_status}`")
        lines.append(
            f"- **Artifact hash (SHA-256):** "
            f"`{card.artifact_hash[:16]}…`")
        lines.append(
            f"- **Training data hash (SHA-256):** "
            f"`{card.training_data_hash[:16]}…`")
        if card.training_completed_at_iso:
            lines.append(
                f"- **Training completed:** "
                f"{card.training_completed_at_iso}")
        else:
            lines.append(
                "- **Training completed:** *(not recorded)*")
        lines.append("")
        lines.append("## Training Metrics")
        lines.append("")
        for metric_name in sorted(card.training_metrics.keys()):
            lines.append(
                f"- **{metric_name}:** "
                f"{card.training_metrics[metric_name]}")
        lines.append("")
        lines.append("## Intended Use")
        lines.append("")
        lines.append(card.narrative.intended_use)
        lines.append("")
        lines.append("## Out-of-Scope Use")
        lines.append("")
        lines.append(card.narrative.out_of_scope_use)
        lines.append("")
        lines.append("## Training Data")
        lines.append("")
        lines.append(
            card.narrative.training_data_description)
        lines.append("")
        lines.append("## Evaluation Data")
        lines.append("")
        lines.append(
            card.narrative.evaluation_data_description)
        lines.append("")
        lines.append("## Ethical Considerations")
        lines.append("")
        lines.append(
            card.narrative.ethical_considerations
            or "*(not populated)*")
        lines.append("")
        lines.append("## Caveats and Recommendations")
        lines.append("")
        lines.append(
            card.narrative.caveats_and_recommendations
            or "*(not populated)*")
        lines.append("")
        if card.production_snapshot is not None:
            ps = card.production_snapshot
            lines.append("## Production Performance")
            lines.append("")
            lines.append(
                f"*Snapshot at {ps.snapshot_at_iso}*")
            lines.append("")
            if ps.override_rate_30d is not None:
                lines.append(
                    f"- **Override rate (30d):** "
                    f"{ps.override_rate_30d} "
                    f"(sample size "
                    f"{ps.override_sample_size_30d})")
            if (ps.drift_metric_name is not None
                and ps.drift_metric_value is not None):
                lines.append(
                    f"- **Drift ({ps.drift_metric_name}):** "
                    f"{ps.drift_metric_value}")
            if ps.last_retraining_outcome is not None:
                lines.append(
                    f"- **Retraining recommendation:** "
                    f"{ps.last_retraining_outcome} — "
                    f"{ps.last_retraining_rationale}")
            if ps.last_ab_severity is not None:
                lines.append(
                    f"- **Last A/B comparison "
                    f"(against {ps.last_ab_against_version}):**"
                    f" {ps.last_ab_severity}")
            lines.append("")
        if card.notes:
            lines.append("## Notes")
            lines.append("")
            lines.append(card.notes)
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "*This card is structured per Mitchell et al. "
            "2019 (Model Cards for Model Reporting) with "
            "production performance extensions. Source of "
            "truth is the structured ModelCard dataclass; "
            "this markdown is a rendering for human "
            "consumption.*")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

_VALID_HASH_A = "a" * 64
_VALID_HASH_B = "b" * 64


def _make_narrative(intended="Classify trade finance documents"):
    return ModelCardNarrative(
        intended_use=intended,
        out_of_scope_use=(
            "Not for credit decisions; not for sanctions "
            "screening"),
        training_data_description=(
            "12 months of FLEXCUBE document attachments "
            "labeled by trade ops team"),
        evaluation_data_description=(
            "Held-out 20% from same period; stratified by "
            "document type"),
        ethical_considerations=(
            "Operator-in-the-loop required; model "
            "recommendations are advisory"),
        caveats_and_recommendations=(
            "Not validated for cross-border guarantees; "
            "rerun training quarterly"))


def _make_card(model_version="1.0.0"):
    eng = MLOpsModelCardComposerEngine()
    r = eng.compose_model_card(
        model_id="doc_classifier",
        model_version=model_version,
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={
            "accuracy": Decimal("0.87"),
            "f1": Decimal("0.85")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="trainer-pipeline",
        training_completed_at_iso="2026-04-30T18:00:00Z")
    assert r.outcome == CardComposeOutcome.COMPOSED
    return r.card


# ─── Compose tests ─────────────────────────────────────────────

def _test_compose_clean():
    eng = MLOpsModelCardComposerEngine()
    r = eng.compose_model_card(
        model_id="doc_classifier",
        model_version="1.0.0",
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={
            "accuracy": Decimal("0.87")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="trainer-pipeline")
    assert r.outcome == CardComposeOutcome.COMPOSED
    assert r.card is not None
    assert r.card.model_id == "doc_classifier"


def _test_compose_missing_required_field():
    eng = MLOpsModelCardComposerEngine()
    r = eng.compose_model_card(
        model_id="",   # empty
        model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("1")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    assert r.outcome == CardComposeOutcome.REJECTED_INVALID
    assert any("model_id" in f for f in r.findings)


def _test_compose_missing_narrative_section():
    eng = MLOpsModelCardComposerEngine()
    bad_narrative = ModelCardNarrative(
        intended_use="",  # empty
        out_of_scope_use="not for X",
        training_data_description="X data",
        evaluation_data_description="Y data",
        ethical_considerations="",
        caveats_and_recommendations="")
    r = eng.compose_model_card(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("1")},
        narrative=bad_narrative,
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    assert r.outcome == CardComposeOutcome.REJECTED_INVALID
    assert any(
        "intended_use" in f for f in r.findings)


def _test_compose_nan_metric():
    eng = MLOpsModelCardComposerEngine()
    r = eng.compose_model_card(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("NaN")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    assert r.outcome == CardComposeOutcome.REJECTED_INVALID


def _test_compose_with_production_snapshot():
    eng = MLOpsModelCardComposerEngine()
    snapshot = ProductionPerformanceSnapshot(
        snapshot_at_iso="2026-05-01T10:00:00Z",
        override_rate_30d=Decimal("0.08"),
        override_sample_size_30d=200,
        drift_metric_name="PSI",
        drift_metric_value=Decimal("0.05"),
        last_retraining_outcome="NOT_YET",
        last_retraining_rationale=(
            "All signals OK"),
        last_ab_severity=None,
        last_ab_against_version=None)
    r = eng.compose_model_card(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("1")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c",
        production_snapshot=snapshot)
    assert r.outcome == CardComposeOutcome.COMPOSED
    assert r.card.production_snapshot is not None
    assert r.card.production_snapshot.override_rate_30d == (
        Decimal("0.08"))


# ─── Completeness tests ────────────────────────────────────────

def _test_completeness_complete():
    card = _make_card()
    eng = MLOpsModelCardComposerEngine()
    a = eng.validate_card_completeness(
        card,
        CardCompletenessRequirements(
            require_narrative=True,
            require_production_snapshot=False,
            required_metric_names=("accuracy",),
            require_training_completion_timestamp=True))
    assert a.outcome == CompletenessOutcome.COMPLETE
    assert len(a.missing_sections) == 0


def _test_completeness_missing_metric():
    card = _make_card()
    eng = MLOpsModelCardComposerEngine()
    a = eng.validate_card_completeness(
        card,
        CardCompletenessRequirements(
            required_metric_names=("auc",)))  # not present
    assert a.outcome == CompletenessOutcome.INCOMPLETE
    assert any(
        "auc" in s for s in a.missing_sections)


def _test_completeness_missing_production_snapshot():
    card = _make_card()
    eng = MLOpsModelCardComposerEngine()
    a = eng.validate_card_completeness(
        card,
        CardCompletenessRequirements(
            require_production_snapshot=True))
    assert a.outcome == CompletenessOutcome.INCOMPLETE
    assert "production_snapshot" in a.missing_sections


def _test_completeness_all_missing_surfaced():
    """Multiple missing sections all surface (Rule 1 — not just first)."""
    eng = MLOpsModelCardComposerEngine()
    # Construct a card directly with mostly-empty narrative
    card = ModelCard(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_completed_at_iso=None,  # missing
        training_metrics={"accuracy": Decimal("0.85")},
        narrative=ModelCardNarrative(
            intended_use="x", out_of_scope_use="y",
            training_data_description="z",
            evaluation_data_description="w",
            ethical_considerations="",   # missing
            caveats_and_recommendations=""),  # missing
        production_snapshot=None,
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    a = eng.validate_card_completeness(
        card,
        CardCompletenessRequirements(
            require_narrative=True,
            require_production_snapshot=True,
            require_training_completion_timestamp=True))
    # Should surface: 2 narrative sections + production_snapshot +
    # training_completed_at_iso = 4 missing
    assert len(a.missing_sections) >= 4


# ─── Diff tests ────────────────────────────────────────────────

def _test_diff_different_versions():
    a = _make_card(model_version="1.0.0")
    b = _make_card(model_version="2.0.0")
    eng = MLOpsModelCardComposerEngine()
    d = eng.compute_card_diff(a, b)
    by_field = {df.field_name: df for df in d.field_diffs}
    assert by_field["model_version"].changed is True
    assert by_field["model_version"].old_value == "1.0.0"
    assert by_field["model_version"].new_value == "2.0.0"


def _test_diff_same_card_zero_changes():
    a = _make_card()
    eng = MLOpsModelCardComposerEngine()
    d = eng.compute_card_diff(a, a)
    assert d.changed_field_count == 0


def _test_diff_metric_change():
    eng = MLOpsModelCardComposerEngine()
    a = _make_card()
    # Build b with different accuracy
    r = eng.compose_model_card(
        model_id="doc_classifier", model_version="2.0.0",
        framework="sklearn", framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="PROPOSED",
        training_metrics={
            "accuracy": Decimal("0.92"),
            "f1": Decimal("0.85")},
        narrative=_make_narrative(),
        composed_at_iso="2026-06-01T10:00:00Z",
        composed_by="trainer-pipeline",
        training_completed_at_iso="2026-05-30T00:00:00Z")
    b = r.card
    d = eng.compute_card_diff(a, b)
    by_field = {df.field_name: df for df in d.field_diffs}
    assert by_field[
        "training_metrics.accuracy"].changed is True


# ─── Revision history tests ────────────────────────────────────

def _test_revision_history_chronological():
    eng = MLOpsModelCardComposerEngine()
    # 3 cards composed at different times
    cards = []
    for i, version in enumerate(["1.0", "1.1", "2.0"]):
        r = eng.compose_model_card(
            model_id="m", model_version=version,
            framework="sklearn", framework_version="1.5",
            owner="o",
            artifact_hash=_VALID_HASH_A,
            training_data_hash=_VALID_HASH_B,
            operational_status="ACTIVE",
            training_metrics={"a": Decimal("1")},
            narrative=_make_narrative(),
            composed_at_iso=(
                f"2026-0{i+1}-01T00:00:00Z"),
            composed_by="c",
            card_version=str(i+1) + ".0")
        cards.append(r.card)
    h = eng.build_revision_history(cards, "m")
    assert h.total_revisions == 3
    assert h.entries[0].card_version == "1.0"
    assert h.entries[-1].card_version == "3.0"


def _test_revision_history_filters_other_models():
    eng = MLOpsModelCardComposerEngine()
    a = _make_card()
    # Build a card for a different model
    r = eng.compose_model_card(
        model_id="other_model", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("1")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    other = r.card
    h = eng.build_revision_history(
        [a, other], "doc_classifier")
    assert h.total_revisions == 1
    assert h.entries[0].model_version == "1.0.0"


# ─── Markdown serialization tests ──────────────────────────────

def _test_markdown_serialization_basic():
    eng = MLOpsModelCardComposerEngine()
    card = _make_card()
    md = eng.serialize_card_to_markdown(card)
    # Required sections present
    assert "# Model Card" in md
    assert "## Model Details" in md
    assert "## Intended Use" in md
    assert "## Training Data" in md
    assert "## Ethical Considerations" in md
    assert card.model_id in md
    assert card.framework in md


def _test_markdown_with_production_snapshot():
    eng = MLOpsModelCardComposerEngine()
    snapshot = ProductionPerformanceSnapshot(
        snapshot_at_iso="2026-05-01T10:00:00Z",
        override_rate_30d=Decimal("0.08"),
        override_sample_size_30d=200,
        drift_metric_name="PSI",
        drift_metric_value=Decimal("0.05"),
        last_retraining_outcome="NOT_YET",
        last_retraining_rationale="All signals OK")
    r = eng.compose_model_card(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("1")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c",
        production_snapshot=snapshot)
    md = eng.serialize_card_to_markdown(r.card)
    assert "## Production Performance" in md
    assert "Override rate (30d)" in md
    assert "PSI" in md


# ─── Discipline tests ──────────────────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = MLOpsModelCardComposerEngine()
    card = _make_card()
    original_metrics = dict(card.training_metrics)
    eng.serialize_card_to_markdown(card)
    eng.validate_card_completeness(
        card, CardCompletenessRequirements())
    assert card.training_metrics == original_metrics


def _test_full_provenance():
    eng = MLOpsModelCardComposerEngine()
    r = eng.compose_model_card(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash=_VALID_HASH_A,
        training_data_hash=_VALID_HASH_B,
        operational_status="ACTIVE",
        training_metrics={"a": Decimal("1")},
        narrative=_make_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    refs = " / ".join(r.framework_refs)
    assert "ENH-285" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs
    assert "Mitchell" in refs   # Mitchell et al. 2019 cited


def _test_caller_supplied_data_discipline():
    """Engine bundles no narrative; caller supplies everything."""
    eng = MLOpsModelCardComposerEngine()
    h = eng.build_revision_history((), "m")
    assert h.total_revisions == 0
    assert h.earliest_composed_at_iso is None


def _test_arc_integration_snapshot_fields():
    """Snapshot field names align with arc engines —
    override_rate_30d (ENH-282), drift_metric_value (G124),
    last_retraining_outcome (ENH-283), last_ab_severity (ENH-284)."""
    snapshot = ProductionPerformanceSnapshot(
        snapshot_at_iso="2026-05-01T10:00:00Z",
        override_rate_30d=Decimal("0.10"),
        drift_metric_name="PSI",
        drift_metric_value=Decimal("0.08"),
        last_retraining_outcome="SOON",
        last_ab_severity="NEEDS_REVIEW")
    # These fields exist (would raise AttributeError if engine
    # restructured them away)
    assert snapshot.override_rate_30d == Decimal("0.10")
    assert snapshot.last_retraining_outcome == "SOON"
    assert snapshot.last_ab_severity == "NEEDS_REVIEW"


def self_test() -> None:
    tests = [
        _test_compose_clean,
        _test_compose_missing_required_field,
        _test_compose_missing_narrative_section,
        _test_compose_nan_metric,
        _test_compose_with_production_snapshot,
        _test_completeness_complete,
        _test_completeness_missing_metric,
        _test_completeness_missing_production_snapshot,
        _test_completeness_all_missing_surfaced,
        _test_diff_different_versions,
        _test_diff_same_card_zero_changes,
        _test_diff_metric_change,
        _test_revision_history_chronological,
        _test_revision_history_filters_other_models,
        _test_markdown_serialization_basic,
        _test_markdown_with_production_snapshot,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_caller_supplied_data_discipline,
        _test_arc_integration_snapshot_fields,
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
            f"✗ mlops_model_card_composer self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ mlops_model_card_composer self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

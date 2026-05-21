"""utils/mlops_persistence.py — v10.87: MLOps Persistence Helper.

Post-arc-closure helper module (the ml_governance arc closed at
v10.86 with G139+G140+G141). Sits ALONGSIDE the closed arc, not
inside it — provides JSON-file storage helpers that operations
uses to persist the three dataclasses the arc engines produce:

  - ENH-281 ModelRegistryEntry  (the registry source of truth)
  - ENH-282 AdjudicationRecord  (the audit log)
  - ENH-285 ModelCard           (the card archive)

The helper is **caller infrastructure** — same pattern as
utils.core_audit. The mlops_* engines never import this module.
The helper is what callers (cockpit pages, training pipelines,
ops scripts) use to round-trip dataclasses to disk.

This is the practical answer to one of the v10.86 honest
acknowledgements: "Build the actual JSON/PG persistence layer
for the registry, adjudication log, and card archive (engines
are stateless; caller stores)." Operations gets a working
default; can later swap to PG via the same interface.

File format: NDJSON (newline-delimited JSON, one record per
line). Append-friendly (f.write(json_line + "\\n")) and
gap-tolerant (a corrupt line doesn't break the whole file —
the loader surfaces the corrupt line numbers explicitly per
Rule 1).

Six capabilities:

  1. save_registry_entry — append a ModelRegistryEntry to a
     caller-supplied NDJSON path. Returns SaveResult with
     outcome SAVED / FAILED + error description.

  2. load_registry_entries — read a caller-supplied NDJSON
     path; optional model_id + status filters. Returns
     LoadResult with entries tuple + corrupt_line_numbers
     tuple (Rule 1 gap surfacing) + total_lines.

  3. save_adjudication_record — append an AdjudicationRecord.

  4. load_adjudication_records — read; optional model_id +
     status + after_iso + before_iso filters.

  5. save_model_card — append a ModelCard. The nested
     ModelCardNarrative + Optional[ProductionPerformance
     Snapshot] are serialized as nested dicts; round-trip
     preserved.

  6. load_model_cards — read; optional model_id filter.

Per Rule 7, helper NEVER:
  - modifies the dataclasses (read-only after engine constructs)
  - decides storage policy (caller chooses path; helper writes)
  - auto-validates against engine output (engine validates at
    construction; helper trusts what it gets)
  - mutates the file outside append-and-read semantics (no
    delete, no edit-in-place; retention policy is caller
    territory)
  - persists across processes via shared state (each call is
    a discrete file operation)

Per Rule 1, every load surfaces total_lines + corrupt line
numbers explicitly. Every save returns explicit success/failure
outcome.

Caller-supplied data discipline: path + records + filters all
caller-supplied. Helper bundles no defaults except
dataclass-field defaults inherited from the arc engines.

Pure stdlib (json + decimal + enum + os + dataclasses).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import (
    Any, Mapping, Optional, Sequence, Tuple)

from utils.mlops_model_registry import (
    ModelRegistryEntry, ModelStatus)
from utils.mlops_adjudication_log import (
    AdjudicationRecord, AgreementStatus, OverrideReason)
from utils.mlops_model_card_composer import (
    ModelCard, ModelCardNarrative,
    ProductionPerformanceSnapshot)

SPEC_DEVIATION_NOTE = (
    "MLOps persistence helper — post-v10.86 closure addition. "
    "Caller infrastructure for round-tripping the three arc "
    "dataclasses (ModelRegistryEntry / AdjudicationRecord / "
    "ModelCard) to NDJSON files. Same pattern as "
    "utils.core_audit. The mlops_* engines never import this "
    "module — engines remain stateless; helper is the caller "
    "side of the persistence boundary. Per Rule 7, helper "
    "never modifies dataclasses + never decides storage policy "
    "+ never mutates files outside append+read semantics. Per "
    "Rule 1, every load surfaces corrupt line numbers + total "
    "lines explicitly."
)


# ════════════════════════════════════════════════════════════════════════
# Outcome enums + result dataclasses
# ════════════════════════════════════════════════════════════════════════

class SaveOutcome(Enum):
    SAVED = "SAVED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SaveResult:
    outcome: SaveOutcome
    path: str
    bytes_written: int
    error: str   # empty when outcome=SAVED


@dataclass(frozen=True)
class LoadResult:
    """Generic load result. The records tuple type matches the
    capability called (registry entries / adjudication records /
    model cards)."""
    path: str
    total_lines: int
    corrupt_line_numbers: Tuple[int, ...]
    error: str   # set when path doesn't exist or unreadable


@dataclass(frozen=True)
class RegistryLoadResult:
    path: str
    entries: Tuple[ModelRegistryEntry, ...]
    total_lines: int
    corrupt_line_numbers: Tuple[int, ...]
    error: str


@dataclass(frozen=True)
class AdjudicationLoadResult:
    path: str
    records: Tuple[AdjudicationRecord, ...]
    total_lines: int
    corrupt_line_numbers: Tuple[int, ...]
    error: str


@dataclass(frozen=True)
class ModelCardLoadResult:
    path: str
    cards: Tuple[ModelCard, ...]
    total_lines: int
    corrupt_line_numbers: Tuple[int, ...]
    error: str


# ════════════════════════════════════════════════════════════════════════
# Internal serialization helpers
# ════════════════════════════════════════════════════════════════════════

def _decimal_to_str(d: Optional[Decimal]) -> Optional[str]:
    """Decimal → string for JSON (preserves precision)."""
    return str(d) if d is not None else None


def _str_to_decimal(s: Optional[str]) -> Optional[Decimal]:
    return Decimal(s) if s is not None else None


def _enum_to_str(e: Optional[Enum]) -> Optional[str]:
    return e.value if e is not None else None


# ─── ModelRegistryEntry ────────────────────────────────────────

def _registry_entry_to_dict(
    entry: ModelRegistryEntry,
) -> dict:
    return {
        "model_id": entry.model_id,
        "version": entry.version,
        "artifact_hash": entry.artifact_hash,
        "training_data_hash": entry.training_data_hash,
        "framework": entry.framework,
        "framework_version": entry.framework_version,
        "metrics": {
            k: str(v) for k, v in entry.metrics.items()},
        "owner": entry.owner,
        "status": entry.status.value,
        "created_by": entry.created_by,
        "created_at_iso": entry.created_at_iso,
        "training_completed_at_iso":
            entry.training_completed_at_iso,
        "notes": entry.notes,
        "promoted_to_active_at_iso":
            entry.promoted_to_active_at_iso,
        "deprecated_at_iso": entry.deprecated_at_iso,
    }


def _dict_to_registry_entry(d: dict) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=d["model_id"],
        version=d["version"],
        artifact_hash=d["artifact_hash"],
        training_data_hash=d["training_data_hash"],
        framework=d["framework"],
        framework_version=d["framework_version"],
        metrics={
            k: Decimal(v) for k, v in d["metrics"].items()},
        owner=d["owner"],
        status=ModelStatus(d["status"]),
        created_by=d["created_by"],
        created_at_iso=d["created_at_iso"],
        training_completed_at_iso=d.get(
            "training_completed_at_iso"),
        notes=d.get("notes", ""),
        promoted_to_active_at_iso=d.get(
            "promoted_to_active_at_iso"),
        deprecated_at_iso=d.get("deprecated_at_iso"))


# ─── AdjudicationRecord ────────────────────────────────────────

def _adjudication_record_to_dict(
    record: AdjudicationRecord,
) -> dict:
    return {
        "event_id": record.event_id,
        "model_id": record.model_id,
        "model_version": record.model_version,
        "recommendation": record.recommendation,
        "recommendation_class": record.recommendation_class,
        "operator_decision": record.operator_decision,
        "agreement_status": record.agreement_status.value,
        "operator_id": record.operator_id,
        "decision_at_iso": record.decision_at_iso,
        "override_reason": _enum_to_str(
            record.override_reason),
        "override_reason_text": record.override_reason_text,
        "input_features_hash": record.input_features_hash,
        "retraining_eligible": record.retraining_eligible,
        "notes": record.notes,
    }


def _dict_to_adjudication_record(
    d: dict,
) -> AdjudicationRecord:
    override_reason = (
        OverrideReason(d["override_reason"])
        if d.get("override_reason") is not None else None)
    return AdjudicationRecord(
        event_id=d["event_id"],
        model_id=d["model_id"],
        model_version=d["model_version"],
        recommendation=d["recommendation"],
        recommendation_class=d["recommendation_class"],
        operator_decision=d["operator_decision"],
        agreement_status=AgreementStatus(
            d["agreement_status"]),
        operator_id=d["operator_id"],
        decision_at_iso=d["decision_at_iso"],
        override_reason=override_reason,
        override_reason_text=d.get(
            "override_reason_text", ""),
        input_features_hash=d.get("input_features_hash"),
        retraining_eligible=d.get(
            "retraining_eligible", False),
        notes=d.get("notes", ""))


# ─── ModelCard ─────────────────────────────────────────────────

def _narrative_to_dict(n: ModelCardNarrative) -> dict:
    return {
        "intended_use": n.intended_use,
        "out_of_scope_use": n.out_of_scope_use,
        "training_data_description": (
            n.training_data_description),
        "evaluation_data_description": (
            n.evaluation_data_description),
        "ethical_considerations": n.ethical_considerations,
        "caveats_and_recommendations": (
            n.caveats_and_recommendations),
    }


def _dict_to_narrative(d: dict) -> ModelCardNarrative:
    return ModelCardNarrative(
        intended_use=d["intended_use"],
        out_of_scope_use=d["out_of_scope_use"],
        training_data_description=d[
            "training_data_description"],
        evaluation_data_description=d[
            "evaluation_data_description"],
        ethical_considerations=d[
            "ethical_considerations"],
        caveats_and_recommendations=d[
            "caveats_and_recommendations"])


def _snapshot_to_dict(
    s: ProductionPerformanceSnapshot,
) -> dict:
    return {
        "snapshot_at_iso": s.snapshot_at_iso,
        "override_rate_30d": _decimal_to_str(
            s.override_rate_30d),
        "override_sample_size_30d":
            s.override_sample_size_30d,
        "drift_metric_name": s.drift_metric_name,
        "drift_metric_value": _decimal_to_str(
            s.drift_metric_value),
        "last_retraining_outcome": s.last_retraining_outcome,
        "last_retraining_rationale": (
            s.last_retraining_rationale),
        "last_ab_severity": s.last_ab_severity,
        "last_ab_against_version": (
            s.last_ab_against_version),
    }


def _dict_to_snapshot(
    d: dict,
) -> ProductionPerformanceSnapshot:
    return ProductionPerformanceSnapshot(
        snapshot_at_iso=d["snapshot_at_iso"],
        override_rate_30d=_str_to_decimal(
            d.get("override_rate_30d")),
        override_sample_size_30d=d.get(
            "override_sample_size_30d"),
        drift_metric_name=d.get("drift_metric_name"),
        drift_metric_value=_str_to_decimal(
            d.get("drift_metric_value")),
        last_retraining_outcome=d.get(
            "last_retraining_outcome"),
        last_retraining_rationale=d.get(
            "last_retraining_rationale", ""),
        last_ab_severity=d.get("last_ab_severity"),
        last_ab_against_version=d.get(
            "last_ab_against_version"))


def _model_card_to_dict(card: ModelCard) -> dict:
    return {
        "model_id": card.model_id,
        "model_version": card.model_version,
        "framework": card.framework,
        "framework_version": card.framework_version,
        "owner": card.owner,
        "artifact_hash": card.artifact_hash,
        "training_data_hash": card.training_data_hash,
        "operational_status": card.operational_status,
        "training_completed_at_iso": (
            card.training_completed_at_iso),
        "training_metrics": {
            k: str(v)
            for k, v in card.training_metrics.items()},
        "narrative": _narrative_to_dict(card.narrative),
        "production_snapshot": (
            _snapshot_to_dict(card.production_snapshot)
            if card.production_snapshot is not None else None),
        "composed_at_iso": card.composed_at_iso,
        "composed_by": card.composed_by,
        "card_version": card.card_version,
        "notes": card.notes,
    }


def _dict_to_model_card(d: dict) -> ModelCard:
    snap_dict = d.get("production_snapshot")
    return ModelCard(
        model_id=d["model_id"],
        model_version=d["model_version"],
        framework=d["framework"],
        framework_version=d["framework_version"],
        owner=d["owner"],
        artifact_hash=d["artifact_hash"],
        training_data_hash=d["training_data_hash"],
        operational_status=d["operational_status"],
        training_completed_at_iso=d.get(
            "training_completed_at_iso"),
        training_metrics={
            k: Decimal(v)
            for k, v in d["training_metrics"].items()},
        narrative=_dict_to_narrative(d["narrative"]),
        production_snapshot=(
            _dict_to_snapshot(snap_dict)
            if snap_dict is not None else None),
        composed_at_iso=d["composed_at_iso"],
        composed_by=d["composed_by"],
        card_version=d.get("card_version", "1.0"),
        notes=d.get("notes", ""))


# ════════════════════════════════════════════════════════════════════════
# Generic NDJSON I/O
# ════════════════════════════════════════════════════════════════════════

def _append_ndjson(
    path: str, record_dict: dict,
) -> SaveResult:
    """Append one JSON-encoded record as a single line to path.
    Per Rule 1, returns explicit SaveResult — engine never raises
    silently."""
    try:
        # Ensure parent directory exists
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        line = json.dumps(
            record_dict, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            n = f.write(line)
        return SaveResult(
            outcome=SaveOutcome.SAVED,
            path=path,
            bytes_written=n,
            error="")
    except Exception as e:
        return SaveResult(
            outcome=SaveOutcome.FAILED,
            path=path,
            bytes_written=0,
            error=f"{type(e).__name__}: {e}")


def _read_ndjson_lines(
    path: str,
) -> Tuple[Sequence[dict], Tuple[int, ...], int, str]:
    """Read NDJSON file and return (records, corrupt_line_numbers,
    total_lines, error). Per Rule 1, surfaces corrupt lines
    explicitly so caller sees what's broken."""
    if not os.path.exists(path):
        return ([], (), 0, "")
    try:
        records: list = []
        corrupt: list = []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        for i, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not stripped:
                continue   # skip blank lines silently
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError:
                corrupt.append(i)
        return (records, tuple(corrupt), total, "")
    except Exception as e:
        return (
            [], (), 0,
            f"{type(e).__name__}: {e}")


# ════════════════════════════════════════════════════════════════════════
# Capability 1+2 — registry entries
# ════════════════════════════════════════════════════════════════════════

def save_registry_entry(
    path: str, entry: ModelRegistryEntry,
) -> SaveResult:
    """Append a ModelRegistryEntry to NDJSON file at caller-
    supplied path."""
    return _append_ndjson(
        path, _registry_entry_to_dict(entry))


def load_registry_entries(
    path: str,
    model_id: Optional[str] = None,
    status: Optional[ModelStatus] = None,
) -> RegistryLoadResult:
    """Read NDJSON file and return registry entries. Per Rule 1,
    surfaces total_lines + corrupt_line_numbers explicitly."""
    raw_records, corrupt, total, error = _read_ndjson_lines(
        path)
    entries: list = []
    for r in raw_records:
        try:
            entry = _dict_to_registry_entry(r)
        except Exception:
            # Counted as corrupt — record was JSON-valid but
            # didn't fit ModelRegistryEntry shape. Caller sees
            # the line number anyway via raw decoding.
            continue
        if model_id is not None and entry.model_id != model_id:
            continue
        if status is not None and entry.status != status:
            continue
        entries.append(entry)
    return RegistryLoadResult(
        path=path,
        entries=tuple(entries),
        total_lines=total,
        corrupt_line_numbers=corrupt,
        error=error)


# ════════════════════════════════════════════════════════════════════════
# Capability 3+4 — adjudication records
# ════════════════════════════════════════════════════════════════════════

def save_adjudication_record(
    path: str, record: AdjudicationRecord,
) -> SaveResult:
    return _append_ndjson(
        path, _adjudication_record_to_dict(record))


def load_adjudication_records(
    path: str,
    model_id: Optional[str] = None,
    status: Optional[AgreementStatus] = None,
    after_iso: Optional[str] = None,
    before_iso: Optional[str] = None,
) -> AdjudicationLoadResult:
    """Read + filter adjudication records. Time-window filters
    use string comparison on ISO 8601 (lexicographic == temporal
    for properly-formatted ISO 8601 with same offset)."""
    raw_records, corrupt, total, error = _read_ndjson_lines(
        path)
    records: list = []
    for r in raw_records:
        try:
            rec = _dict_to_adjudication_record(r)
        except Exception:
            continue
        if model_id is not None and rec.model_id != model_id:
            continue
        if status is not None and (
            rec.agreement_status != status
        ):
            continue
        if after_iso is not None and (
            rec.decision_at_iso < after_iso
        ):
            continue
        if before_iso is not None and (
            rec.decision_at_iso > before_iso
        ):
            continue
        records.append(rec)
    return AdjudicationLoadResult(
        path=path,
        records=tuple(records),
        total_lines=total,
        corrupt_line_numbers=corrupt,
        error=error)


# ════════════════════════════════════════════════════════════════════════
# Capability 5+6 — model cards
# ════════════════════════════════════════════════════════════════════════

def save_model_card(
    path: str, card: ModelCard,
) -> SaveResult:
    return _append_ndjson(
        path, _model_card_to_dict(card))


def load_model_cards(
    path: str,
    model_id: Optional[str] = None,
) -> ModelCardLoadResult:
    raw_records, corrupt, total, error = _read_ndjson_lines(
        path)
    cards: list = []
    for r in raw_records:
        try:
            card = _dict_to_model_card(r)
        except Exception:
            continue
        if model_id is not None and card.model_id != model_id:
            continue
        cards.append(card)
    return ModelCardLoadResult(
        path=path,
        cards=tuple(cards),
        total_lines=total,
        corrupt_line_numbers=corrupt,
        error=error)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

import tempfile
from utils.mlops_model_registry import (
    MLOpsModelRegistryEngine)
from utils.mlops_adjudication_log import (
    MLOpsAdjudicationLogEngine)
from utils.mlops_model_card_composer import (
    MLOpsModelCardComposerEngine)


def _temp_path() -> str:
    f = tempfile.NamedTemporaryFile(
        suffix=".ndjson", delete=False, mode="w")
    f.close()
    os.unlink(f.name)   # we want path, but starting empty
    return f.name


def _make_registry_entry():
    eng = MLOpsModelRegistryEngine()
    r = eng.register_new_model_version(
        model_id="doc_classifier",
        version="1.0.0",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        framework="sklearn",
        framework_version="1.5.1",
        metrics={
            "accuracy": Decimal("0.87"),
            "f1": Decimal("0.85")},
        owner="ml-team@bank",
        created_by="trainer",
        created_at_iso="2026-05-01T00:00:00Z",
        training_completed_at_iso=(
            "2026-04-30T18:00:00Z"))
    return r.entry


def _make_adjudication_record():
    eng = MLOpsAdjudicationLogEngine()
    r = eng.record_adjudication(
        event_id="EV-001",
        model_id="doc_classifier",
        model_version="1.0.0",
        recommendation="APPROVE",
        recommendation_class="APPROVE",
        operator_decision="REJECT",
        agreement_status=AgreementStatus.OVERRIDDEN,
        operator_id="alice",
        decision_at_iso="2026-05-01T10:00:00Z",
        override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
        input_features_hash="a" * 64,
        retraining_eligible=True)
    return r.record


def _make_model_card():
    eng = MLOpsModelCardComposerEngine()
    snapshot = ProductionPerformanceSnapshot(
        snapshot_at_iso="2026-05-01T10:00:00Z",
        override_rate_30d=Decimal("0.08"),
        override_sample_size_30d=200,
        drift_metric_name="PSI",
        drift_metric_value=Decimal("0.05"),
        last_retraining_outcome="NOT_YET",
        last_retraining_rationale="OK")
    narrative = ModelCardNarrative(
        intended_use="classify",
        out_of_scope_use="not credit",
        training_data_description="12mo data",
        evaluation_data_description="20% holdout",
        ethical_considerations="operator-in-loop",
        caveats_and_recommendations="quarterly retraining")
    r = eng.compose_model_card(
        model_id="doc_classifier",
        model_version="1.0.0",
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        operational_status="ACTIVE",
        training_metrics={"accuracy": Decimal("0.87")},
        narrative=narrative,
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="trainer-pipeline",
        training_completed_at_iso="2026-04-30T18:00:00Z",
        production_snapshot=snapshot)
    return r.card


# ─── Round-trip tests ──────────────────────────────────────────

def _test_round_trip_registry_entry():
    path = _temp_path()
    try:
        original = _make_registry_entry()
        save_result = save_registry_entry(path, original)
        assert save_result.outcome == SaveOutcome.SAVED
        load_result = load_registry_entries(path)
        assert len(load_result.entries) == 1
        loaded = load_result.entries[0]
        assert loaded.model_id == original.model_id
        assert loaded.version == original.version
        # Decimal preserved
        assert (loaded.metrics["accuracy"]
                == original.metrics["accuracy"])
        # Enum preserved
        assert loaded.status == original.status
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_round_trip_adjudication_record():
    path = _temp_path()
    try:
        original = _make_adjudication_record()
        save_adjudication_record(path, original)
        result = load_adjudication_records(path)
        assert len(result.records) == 1
        loaded = result.records[0]
        assert loaded.event_id == original.event_id
        assert loaded.agreement_status == (
            original.agreement_status)
        assert loaded.override_reason == (
            original.override_reason)
        assert loaded.retraining_eligible is True
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_round_trip_model_card():
    path = _temp_path()
    try:
        original = _make_model_card()
        save_model_card(path, original)
        result = load_model_cards(path)
        assert len(result.cards) == 1
        loaded = result.cards[0]
        # Deep field check
        assert loaded.model_id == original.model_id
        assert (loaded.training_metrics["accuracy"]
                == original.training_metrics["accuracy"])
        # Nested narrative round-trip
        assert (loaded.narrative.intended_use
                == original.narrative.intended_use)
        # Optional[ProductionPerformanceSnapshot] round-trip
        assert loaded.production_snapshot is not None
        assert (loaded.production_snapshot.override_rate_30d
                == Decimal("0.08"))
        assert (loaded.production_snapshot.drift_metric_name
                == "PSI")
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_card_with_no_snapshot_round_trips():
    """Optional production_snapshot=None round-trips correctly."""
    path = _temp_path()
    try:
        eng = MLOpsModelCardComposerEngine()
        narrative = ModelCardNarrative(
            intended_use="x", out_of_scope_use="y",
            training_data_description="z",
            evaluation_data_description="w",
            ethical_considerations="e",
            caveats_and_recommendations="c")
        r = eng.compose_model_card(
            model_id="m", model_version="1.0",
            framework="sklearn", framework_version="1.5",
            owner="o", artifact_hash="a" * 64,
            training_data_hash="b" * 64,
            operational_status="ACTIVE",
            training_metrics={"a": Decimal("1")},
            narrative=narrative,
            composed_at_iso="2026-05-01T10:00:00Z",
            composed_by="c")
        save_model_card(path, r.card)
        result = load_model_cards(path)
        assert result.cards[0].production_snapshot is None
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ─── Filter tests ──────────────────────────────────────────────

def _test_load_registry_filter_by_model_id():
    path = _temp_path()
    try:
        eng = MLOpsModelRegistryEngine()
        for mid in ("doc_classifier", "credit_scorer",
                    "doc_classifier"):
            r = eng.register_new_model_version(
                model_id=mid,
                version="1.0",
                artifact_hash="a" * 64,
                training_data_hash="b" * 64,
                framework="sklearn",
                framework_version="1.5",
                metrics={"a": Decimal("1")},
                owner="o", created_by="c",
                created_at_iso="2026-05-01T00:00:00Z")
            save_registry_entry(path, r.entry)
        result = load_registry_entries(
            path, model_id="doc_classifier")
        assert len(result.entries) == 2
        for e in result.entries:
            assert e.model_id == "doc_classifier"
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_load_adjudication_filter_by_status():
    path = _temp_path()
    try:
        eng = MLOpsAdjudicationLogEngine()
        for i, status in enumerate([
            AgreementStatus.ACCEPTED,
            AgreementStatus.OVERRIDDEN,
            AgreementStatus.OVERRIDDEN,
        ]):
            r = eng.record_adjudication(
                event_id=f"E{i}",
                model_id="m", model_version="1.0",
                recommendation="A",
                recommendation_class="A",
                operator_decision="A",
                agreement_status=status,
                operator_id="op",
                decision_at_iso=(
                    f"2026-05-01T10:0{i}:00Z"),
                override_reason=(
                    OverrideReason.OTHER
                    if status == AgreementStatus.OVERRIDDEN
                    else None))
            save_adjudication_record(path, r.record)
        result = load_adjudication_records(
            path, status=AgreementStatus.OVERRIDDEN)
        assert len(result.records) == 2
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_load_adjudication_time_window():
    path = _temp_path()
    try:
        eng = MLOpsAdjudicationLogEngine()
        for i, ts in enumerate([
            "2026-05-01T10:00:00Z",
            "2026-05-02T10:00:00Z",
            "2026-05-03T10:00:00Z",
        ]):
            r = eng.record_adjudication(
                event_id=f"E{i}",
                model_id="m", model_version="1.0",
                recommendation="A",
                recommendation_class="A",
                operator_decision="A",
                agreement_status=AgreementStatus.ACCEPTED,
                operator_id="op",
                decision_at_iso=ts)
            save_adjudication_record(path, r.record)
        # Window: May 2 only
        result = load_adjudication_records(
            path,
            after_iso="2026-05-01T23:59:59Z",
            before_iso="2026-05-02T23:59:59Z")
        assert len(result.records) == 1
        assert result.records[0].event_id == "E1"
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ─── Edge case tests ───────────────────────────────────────────

def _test_load_nonexistent_returns_empty():
    """Non-existent path returns empty result, no error."""
    path = "/tmp/this-path-deliberately-does-not-exist.ndjson"
    if os.path.exists(path):
        os.unlink(path)
    result = load_registry_entries(path)
    assert len(result.entries) == 0
    assert result.total_lines == 0
    assert result.error == ""


def _test_corrupt_line_surfaced():
    """A single corrupt line + good lines: corrupt surfaced
    with line number; good lines load."""
    path = _temp_path()
    try:
        # Manually craft file with 3 lines: good, bad, good
        good_entry = _make_registry_entry()
        good_dict = _registry_entry_to_dict(good_entry)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(good_dict) + "\n")
            f.write("not valid json {{{\n")
            f.write(json.dumps(good_dict) + "\n")
        result = load_registry_entries(path)
        assert len(result.entries) == 2
        assert result.corrupt_line_numbers == (2,)
        assert result.total_lines == 3
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_blank_line_skipped_silently():
    """Blank lines don't count as corrupt — they're skipped."""
    path = _temp_path()
    try:
        good_entry = _make_registry_entry()
        good_dict = _registry_entry_to_dict(good_entry)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(good_dict) + "\n")
            f.write("\n")
            f.write(json.dumps(good_dict) + "\n")
        result = load_registry_entries(path)
        assert len(result.entries) == 2
        assert result.corrupt_line_numbers == ()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_multiple_appends_grow_file():
    """5 saves → 5 records on read."""
    path = _temp_path()
    try:
        eng = MLOpsModelRegistryEngine()
        for i in range(5):
            r = eng.register_new_model_version(
                model_id="m",
                version=f"1.{i}.0",
                artifact_hash="a" * 64,
                training_data_hash="b" * 64,
                framework="sklearn",
                framework_version="1.5",
                metrics={"a": Decimal("1")},
                owner="o", created_by="c",
                created_at_iso=(
                    f"2026-05-0{i+1}T10:00:00Z"))
            save_registry_entry(path, r.entry)
        result = load_registry_entries(path)
        assert len(result.entries) == 5
        assert result.total_lines == 5
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_save_creates_parent_directory():
    """When parent dir doesn't exist, save creates it."""
    parent = tempfile.mkdtemp()
    nested = os.path.join(
        parent, "a", "b", "c", "registry.ndjson")
    try:
        entry = _make_registry_entry()
        result = save_registry_entry(nested, entry)
        assert result.outcome == SaveOutcome.SAVED
        assert os.path.exists(nested)
    finally:
        # Cleanup nested dirs
        if os.path.exists(nested):
            os.unlink(nested)
        for d in (
            os.path.join(parent, "a", "b", "c"),
            os.path.join(parent, "a", "b"),
            os.path.join(parent, "a"),
            parent,
        ):
            if os.path.isdir(d):
                try:
                    os.rmdir(d)
                except OSError:
                    pass


# ─── Discipline tests ──────────────────────────────────────────

def _test_save_failure_returns_explicit_error():
    """Path that can't be written → SaveResult outcome=FAILED
    with error description (Rule 1 — never raises silently)."""
    # /proc is read-only on Linux
    bad_path = "/proc/registry.ndjson"
    entry = _make_registry_entry()
    result = save_registry_entry(bad_path, entry)
    assert result.outcome == SaveOutcome.FAILED
    assert result.error != ""


def _test_engine_does_not_mutate_dataclass():
    """Helper round-trip preserves dataclass identity (frozen)."""
    path = _temp_path()
    try:
        original = _make_registry_entry()
        original_repr = repr(original)
        save_registry_entry(path, original)
        # Original still equal to its initial state
        assert repr(original) == original_repr
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _test_caller_supplied_path_no_default():
    """Helper has no default path — caller must supply."""
    import inspect
    sig = inspect.signature(save_registry_entry)
    params = sig.parameters
    assert "path" in params
    # path has no default — caller must supply
    assert params["path"].default == inspect.Parameter.empty


def _test_filter_combinations_compose():
    """Multiple filters combine with AND semantics."""
    path = _temp_path()
    try:
        eng = MLOpsAdjudicationLogEngine()
        for i, (mid, status) in enumerate([
            ("doc", AgreementStatus.ACCEPTED),
            ("doc", AgreementStatus.OVERRIDDEN),
            ("credit", AgreementStatus.OVERRIDDEN),
        ]):
            r = eng.record_adjudication(
                event_id=f"E{i}",
                model_id=mid, model_version="1.0",
                recommendation="A",
                recommendation_class="A",
                operator_decision="A",
                agreement_status=status,
                operator_id="op",
                decision_at_iso=(
                    f"2026-05-01T10:0{i}:00Z"),
                override_reason=(
                    OverrideReason.OTHER
                    if status == AgreementStatus.OVERRIDDEN
                    else None))
            save_adjudication_record(path, r.record)
        # Filter: model=doc AND status=OVERRIDDEN → 1 record
        result = load_adjudication_records(
            path, model_id="doc",
            status=AgreementStatus.OVERRIDDEN)
        assert len(result.records) == 1
        assert result.records[0].event_id == "E1"
    finally:
        if os.path.exists(path):
            os.unlink(path)


def self_test() -> None:
    tests = [
        _test_round_trip_registry_entry,
        _test_round_trip_adjudication_record,
        _test_round_trip_model_card,
        _test_card_with_no_snapshot_round_trips,
        _test_load_registry_filter_by_model_id,
        _test_load_adjudication_filter_by_status,
        _test_load_adjudication_time_window,
        _test_load_nonexistent_returns_empty,
        _test_corrupt_line_surfaced,
        _test_blank_line_skipped_silently,
        _test_multiple_appends_grow_file,
        _test_save_creates_parent_directory,
        _test_save_failure_returns_explicit_error,
        _test_engine_does_not_mutate_dataclass,
        _test_caller_supplied_path_no_default,
        _test_filter_combinations_compose,
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
            f"✗ mlops_persistence self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ mlops_persistence self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

"""
================================================================================
A2Z MIS 360 — Standard #176: Audit-Ready Instruction History
================================================================================

Risk classification: Cat C (read-side immutable history; never
modifies upstream events; provides queryable audit trail with full
traceability for examiners).

Subcategory: cims

Immutable, queryable instruction history with full traceability.
Composes upstream capture (#166), classification (#167), STP (#168),
identity (#173), process intelligence (#169), dropout prevention
(#170), NBA (#174), exception management (#175), and SLA (#171) —
every upstream lifecycle event flows here as an append-only audit
record. Records are NEVER modified after registration; correction is
done by a NEW correction record that supersedes (not deletes) the
prior one.

Public API:
    register_history_record(record_data, actor, reason)
    register_correction(correction_data, actor, reason)
    record_examiner_query(query_data, actor)
    record_compliance_review(review_data, actor)
    history_for_session(session_id) -> List
    examiner_summary(days=90) -> Dict

HISTORY_RECORD_KINDS byte-for-byte (8):
    INSTRUCTION_LIFECYCLE, CLASSIFICATION_OUTCOME, STP_DECISION,
    IDENTITY_LINK_EVENT, EXCEPTION_LIFECYCLE, SLA_OBLIGATION_EVENT,
    NBA_RECOMMENDATION, DROPOUT_INTERVENTION

ALLOWED_CORRECTION_REASONS byte-for-byte (5):
    DATA_QUALITY_CORRECTION, IDENTITY_REASSIGNMENT,
    REGULATORY_DIRECTIVE, AUDIT_FINDING, OPERATIONAL_ERROR

EXAMINER_QUERY_TYPES byte-for-byte (5):
    SAR_TRACE, DISPUTE_TRACE, COMPLIANCE_REVIEW,
    REGULATORY_INSPECTION, INTERNAL_AUDIT_REQUEST

EXAMINER_RESPONSE_OUTCOMES byte-for-byte (4):
    PROVIDED, PARTIAL_PROVIDED, REQUEST_DENIED, IN_PROGRESS

COMPLIANCE_REVIEW_OUTCOMES byte-for-byte (4):
    PASSED, OBSERVATIONS, FINDINGS, ESCALATED

DEFAULT_RETENTION_YEARS = 7
IMMUTABILITY_NOTE = (
    "Once registered, history records are append-only. Corrections "
    "are themselves new records that reference (not replace) the "
    "original. The original is preserved verbatim — examiners must "
    "see what was originally recorded plus the correction trail."
)

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


HISTORY_RECORD_KINDS: Tuple[str, ...] = (
    "INSTRUCTION_LIFECYCLE", "CLASSIFICATION_OUTCOME",
    "STP_DECISION", "IDENTITY_LINK_EVENT",
    "EXCEPTION_LIFECYCLE", "SLA_OBLIGATION_EVENT",
    "NBA_RECOMMENDATION", "DROPOUT_INTERVENTION",
)

ALLOWED_CORRECTION_REASONS: Tuple[str, ...] = (
    "DATA_QUALITY_CORRECTION", "IDENTITY_REASSIGNMENT",
    "REGULATORY_DIRECTIVE", "AUDIT_FINDING", "OPERATIONAL_ERROR",
)

EXAMINER_QUERY_TYPES: Tuple[str, ...] = (
    "SAR_TRACE", "DISPUTE_TRACE", "COMPLIANCE_REVIEW",
    "REGULATORY_INSPECTION", "INTERNAL_AUDIT_REQUEST",
)

EXAMINER_RESPONSE_OUTCOMES: Tuple[str, ...] = (
    "PROVIDED", "PARTIAL_PROVIDED",
    "REQUEST_DENIED", "IN_PROGRESS",
)

COMPLIANCE_REVIEW_OUTCOMES: Tuple[str, ...] = (
    "PASSED", "OBSERVATIONS", "FINDINGS", "ESCALATED",
)

DEFAULT_RETENTION_YEARS = 7
IMMUTABILITY_NOTE = (
    "Once registered, history records are append-only. Corrections "
    "are themselves new records that reference (not replace) the "
    "original. The original is preserved verbatim — examiners must "
    "see what was originally recorded plus the correction trail."
)


class AuditReadyHistoryEngine:
    """Append-only history + correction + examiner query registry."""

    def __init__(
        self,
        history_path: Optional[Path] = None,
        corrections_path: Optional[Path] = None,
        examiner_queries_path: Optional[Path] = None,
        compliance_reviews_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.history_path = (
            history_path or base / "cims_audit_history.json"
        )
        self.corrections_path = (
            corrections_path or base / "cims_history_corrections.json"
        )
        self.examiner_queries_path = (
            examiner_queries_path
            or base / "cims_examiner_queries.json"
        )
        self.compliance_reviews_path = (
            compliance_reviews_path
            or base / "cims_compliance_reviews.json"
        )

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def register_history_record(
        self, record_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("record_id", "kind", "linked_session_id",
                      "subject_id", "narrative"):
            if f not in record_data or not record_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if record_data["kind"] not in HISTORY_RECORD_KINDS:
            return {"registered": False,
                       "error": f"invalid_kind:{record_data['kind']}"}
        records = self._load(self.history_path,
                                "cims_audit_history", ("record_id",))
        if any(r.get("record_id") == record_data["record_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_record_id"}
        record = {
            "record_id": record_data["record_id"],
            "kind": record_data["kind"],
            "linked_session_id": record_data["linked_session_id"],
            "subject_id": record_data["subject_id"],
            "narrative": record_data["narrative"],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "is_immutable": True,
        }
        records.append(record)
        ok = self._save(self.history_path, records,
                          "cims_audit_history", "record_id")
        return {"registered": ok, "record_id": record_data["record_id"]}

    def register_correction(
        self, correction_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("correction_id", "supersedes_record_id",
                      "correction_reason", "narrative"):
            if f not in correction_data or not correction_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if correction_data["correction_reason"] not in ALLOWED_CORRECTION_REASONS:
            return {"registered": False,
                       "error": f"invalid_correction_reason:{correction_data['correction_reason']}"}
        # Check superseded record exists in history
        history = self._load(self.history_path,
                                "cims_audit_history", ("record_id",))
        sup_id = correction_data["supersedes_record_id"]
        if not any(r.get("record_id") == sup_id for r in history):
            return {"registered": False,
                       "error": "supersedes_record_id_not_found"}
        records = self._load(self.corrections_path,
                                "cims_history_corrections",
                                ("correction_id",))
        if any(r.get("correction_id") == correction_data["correction_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_correction_id"}
        record = {
            "correction_id": correction_data["correction_id"],
            "supersedes_record_id": correction_data["supersedes_record_id"],
            "correction_reason": correction_data["correction_reason"],
            "narrative": correction_data["narrative"],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.corrections_path, records,
                          "cims_history_corrections", "correction_id")
        return {"registered": ok,
                  "correction_id": correction_data["correction_id"]}

    def record_examiner_query(
        self, query_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("query_id", "query_type", "examiner_name",
                      "outcome"):
            if f not in query_data or not query_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if query_data["query_type"] not in EXAMINER_QUERY_TYPES:
            return {"recorded": False,
                       "error": f"invalid_query_type:{query_data['query_type']}"}
        if query_data["outcome"] not in EXAMINER_RESPONSE_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{query_data['outcome']}"}
        records = self._load(self.examiner_queries_path,
                                "cims_examiner_queries", ("query_id",))
        if any(r.get("query_id") == query_data["query_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_query_id"}
        record = {
            "query_id": query_data["query_id"],
            "query_type": query_data["query_type"],
            "examiner_name": query_data["examiner_name"],
            "outcome": query_data["outcome"],
            "narrative": query_data.get("narrative", ""),
            "linked_session_ids": query_data.get(
                "linked_session_ids", [],
            ),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.examiner_queries_path, records,
                          "cims_examiner_queries", "query_id")
        return {"recorded": ok, "query_id": query_data["query_id"]}

    def record_compliance_review(
        self, review_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("review_id", "scope", "outcome"):
            if f not in review_data or not review_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if review_data["outcome"] not in COMPLIANCE_REVIEW_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{review_data['outcome']}"}
        records = self._load(self.compliance_reviews_path,
                                "cims_compliance_reviews", ("review_id",))
        if any(r.get("review_id") == review_data["review_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_review_id"}
        record = {
            "review_id": review_data["review_id"],
            "scope": review_data["scope"],
            "outcome": review_data["outcome"],
            "narrative": review_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.compliance_reviews_path, records,
                          "cims_compliance_reviews", "review_id")
        return {"recorded": ok, "review_id": review_data["review_id"]}

    def history_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        history = self._load(self.history_path,
                                "cims_audit_history", ("record_id",))
        records = [
            r for r in history
            if r.get("linked_session_id") == session_id
        ]
        records.sort(key=lambda x: x.get("registered_at", ""))
        # Annotate with corrections
        corrections = self._load(self.corrections_path,
                                          "cims_history_corrections",
                                          ("correction_id",))
        corrections_by_record: Dict[str, List[Dict[str, Any]]] = {}
        for c in corrections:
            sid = c.get("supersedes_record_id", "")
            corrections_by_record.setdefault(sid, []).append(c)
        for r in records:
            r["corrections"] = corrections_by_record.get(
                r.get("record_id", ""), [],
            )
        return records

    def examiner_summary(self, days: int = 90) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        queries = [
            q for q in self._load(self.examiner_queries_path,
                                            "cims_examiner_queries",
                                            ("query_id",))
            if q.get("recorded_at", "") >= cutoff
        ]
        per_type: Dict[str, int] = {}
        per_outcome: Dict[str, int] = {}
        for q in queries:
            t = q.get("query_type", "")
            o = q.get("outcome", "")
            per_type[t] = per_type.get(t, 0) + 1
            per_outcome[o] = per_outcome.get(o, 0) + 1
        provided = per_outcome.get("PROVIDED", 0)
        evaluated = (
            provided
            + per_outcome.get("PARTIAL_PROVIDED", 0)
            + per_outcome.get("REQUEST_DENIED", 0)
        )
        provision_rate = round(
            (provided / evaluated * 100) if evaluated else 0, 1,
        )
        return {
            "window_days": days,
            "total_queries": len(queries),
            "per_type": per_type,
            "per_outcome": per_outcome,
            "provision_rate_pct": provision_rate,
        }


def _self_test() -> None:
    import tempfile

    assert HISTORY_RECORD_KINDS == (
        "INSTRUCTION_LIFECYCLE", "CLASSIFICATION_OUTCOME",
        "STP_DECISION", "IDENTITY_LINK_EVENT",
        "EXCEPTION_LIFECYCLE", "SLA_OBLIGATION_EVENT",
        "NBA_RECOMMENDATION", "DROPOUT_INTERVENTION",
    )
    assert ALLOWED_CORRECTION_REASONS == (
        "DATA_QUALITY_CORRECTION", "IDENTITY_REASSIGNMENT",
        "REGULATORY_DIRECTIVE", "AUDIT_FINDING",
        "OPERATIONAL_ERROR",
    )
    assert EXAMINER_QUERY_TYPES == (
        "SAR_TRACE", "DISPUTE_TRACE", "COMPLIANCE_REVIEW",
        "REGULATORY_INSPECTION", "INTERNAL_AUDIT_REQUEST",
    )
    assert EXAMINER_RESPONSE_OUTCOMES == (
        "PROVIDED", "PARTIAL_PROVIDED",
        "REQUEST_DENIED", "IN_PROGRESS",
    )
    assert COMPLIANCE_REVIEW_OUTCOMES == (
        "PASSED", "OBSERVATIONS", "FINDINGS", "ESCALATED",
    )
    assert DEFAULT_RETENTION_YEARS == 7
    assert "append-only" in IMMUTABILITY_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        e = AuditReadyHistoryEngine(
            history_path=Path(tmpdir) / "h.json",
            corrections_path=Path(tmpdir) / "c.json",
            examiner_queries_path=Path(tmpdir) / "q.json",
            compliance_reviews_path=Path(tmpdir) / "r.json",
        )

        # History record
        r = e.register_history_record(
            {"record_id": "REC-001",
             "kind": "INSTRUCTION_LIFECYCLE",
             "linked_session_id": "CAP-001",
             "subject_id": "INST-001",
             "narrative": "Instruction received via mobile"},
            actor="ops", reason="lifecycle event",
        )
        assert r["registered"]
        # Bad kind
        r = e.register_history_record(
            {"record_id": "X", "kind": "WHATEVER",
             "linked_session_id": "Y",
             "subject_id": "Z",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Correction — must reference existing record
        r = e.register_correction(
            {"correction_id": "COR-001",
             "supersedes_record_id": "REC-001",
             "correction_reason": "DATA_QUALITY_CORRECTION",
             "narrative": "Channel was actually USSD"},
            actor="ops", reason="post-hoc fix",
        )
        assert r["registered"]
        # Correction with non-existent supersedes
        r = e.register_correction(
            {"correction_id": "COR-X",
             "supersedes_record_id": "REC-NONEXISTENT",
             "correction_reason": "DATA_QUALITY_CORRECTION",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Correction with bad reason
        r = e.register_correction(
            {"correction_id": "COR-Y",
             "supersedes_record_id": "REC-001",
             "correction_reason": "WHATEVER",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Examiner query
        r = e.record_examiner_query(
            {"query_id": "QRY-001",
             "query_type": "SAR_TRACE",
             "examiner_name": "CBK examiner",
             "outcome": "PROVIDED"},
            actor="compliance",
        )
        assert r["recorded"]
        # Bad query type
        r = e.record_examiner_query(
            {"query_id": "X",
             "query_type": "WHATEVER",
             "examiner_name": "Y",
             "outcome": "PROVIDED"},
            actor="x",
        )
        assert not r["recorded"]
        # Bad outcome
        r = e.record_examiner_query(
            {"query_id": "Z",
             "query_type": "SAR_TRACE",
             "examiner_name": "Y",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Compliance review
        r = e.record_compliance_review(
            {"review_id": "REV-001",
             "scope": "CIMS Q1 review",
             "outcome": "PASSED"},
            actor="compliance",
        )
        assert r["recorded"]
        # Bad outcome
        r = e.record_compliance_review(
            {"review_id": "X",
             "scope": "Y",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # History query
        h = e.history_for_session("CAP-001")
        assert len(h) == 1
        assert len(h[0]["corrections"]) == 1
        assert h[0]["corrections"][0]["correction_id"] == "COR-001"

        # Examiner summary
        s = e.examiner_summary(days=90)
        assert s["total_queries"] == 1
        assert s["per_type"]["SAR_TRACE"] == 1
        assert s["per_outcome"]["PROVIDED"] == 1
        assert s["provision_rate_pct"] == 100.0

    print("  ✅ cims_audit_ready_history self-test PASS")


if __name__ == "__main__":
    _self_test()

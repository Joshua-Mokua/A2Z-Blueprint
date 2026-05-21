"""
================================================================================
A2Z MIS 360 — Standard #288: Natural Language Query (NLQ)
================================================================================

Risk classification: Cat C (read-side translation; never executes generated
SQL itself — every query goes through the platform's existing read-only
data access layer).

Subcategory: analytics_hub

Natural language → SQL translation registry. The engine itself does not
do the translation (that's an LLM call configured outside this module);
it owns the request lifecycle, the safety review, and the audit trail.

Every NLQ submission is recorded with the user's natural language input,
the proposed SQL, the safety review status, and the execution outcome.
The platform's diagnostic-only stance (Rule 7) means generated SQL is
SELECT-only against vetted views — INSERT/UPDATE/DELETE/DDL are blocked
at the data access layer and recorded as SAFETY_REJECTED.

Public API:
    register_query_request(request_data, actor)
    transition_request_state(request_id, new_state, actor, reason)
    record_safety_review(review_data, actor)
    record_execution_outcome(outcome_data, actor)
    query_metrics(days=30) -> Dict
    requests_by_state(state) -> List

QUERY_REQUEST_STATES byte-for-byte (6):
    SUBMITTED, TRANSLATED, SAFETY_REVIEW, APPROVED, EXECUTED, REJECTED

ALLOWED_REQUEST_TRANSITIONS (Rule 4):
    SUBMITTED     → TRANSLATED | REJECTED
    TRANSLATED    → SAFETY_REVIEW | REJECTED
    SAFETY_REVIEW → APPROVED | REJECTED
    APPROVED      → EXECUTED | REJECTED
    EXECUTED      → ()
    REJECTED      → ()

QUERY_DOMAINS byte-for-byte (5):
    CUSTOMERS, ACCOUNTS, TRANSACTIONS, REPORTS, AGGREGATES

SAFETY_VERDICTS byte-for-byte (4):
    SAFE, UNSAFE_DDL, UNSAFE_DML, UNSAFE_SCOPE

EXECUTION_OUTCOMES byte-for-byte (4):
    SUCCESS, EMPTY, ERROR, TIMEOUT

DEFAULT_QUERY_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ROWS_RETURNED = 10000
DEFAULT_TRANSLATION_RETRY_LIMIT = 3

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


QUERY_REQUEST_STATES: Tuple[str, ...] = (
    "SUBMITTED", "TRANSLATED", "SAFETY_REVIEW",
    "APPROVED", "EXECUTED", "REJECTED",
)

ALLOWED_REQUEST_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "SUBMITTED":     ("TRANSLATED", "REJECTED"),
    "TRANSLATED":    ("SAFETY_REVIEW", "REJECTED"),
    "SAFETY_REVIEW": ("APPROVED", "REJECTED"),
    "APPROVED":      ("EXECUTED", "REJECTED"),
    "EXECUTED":      (),
    "REJECTED":      (),
}

QUERY_DOMAINS: Tuple[str, ...] = (
    "CUSTOMERS", "ACCOUNTS", "TRANSACTIONS", "REPORTS", "AGGREGATES",
)

SAFETY_VERDICTS: Tuple[str, ...] = (
    "SAFE", "UNSAFE_DDL", "UNSAFE_DML", "UNSAFE_SCOPE",
)

EXECUTION_OUTCOMES: Tuple[str, ...] = (
    "SUCCESS", "EMPTY", "ERROR", "TIMEOUT",
)

DEFAULT_QUERY_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ROWS_RETURNED = 10000
DEFAULT_TRANSLATION_RETRY_LIMIT = 3


class NLQEngine:
    """NLQ request lifecycle: capture → translate → safety → execute."""

    def __init__(
        self,
        requests_path: Optional[Path] = None,
        reviews_path: Optional[Path] = None,
        outcomes_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.requests_path = requests_path or base / "nlq_requests.json"
        self.reviews_path = reviews_path or base / "nlq_safety_reviews.json"
        self.outcomes_path = (
            outcomes_path or base / "nlq_execution_outcomes.json"
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

    def register_query_request(
        self, request_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("request_id", "natural_language", "domain"):
            if f not in request_data or not request_data[f]:
                return {"registered": False,
                           "error": f"missing_field:{f}"}
        if request_data["domain"] not in QUERY_DOMAINS:
            return {"registered": False,
                       "error": f"invalid_domain:{request_data['domain']}"}
        records = self._load(self.requests_path,
                                "nlq_requests", ("request_id",))
        if any(r.get("request_id") == request_data["request_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_request_id"}
        record = {
            "request_id": request_data["request_id"],
            "natural_language": request_data["natural_language"],
            "domain": request_data["domain"],
            "translated_sql": "",
            "translation_attempts": 0,
            "state": "SUBMITTED",
            "submitted_by": actor,
            "submitted_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "SUBMITTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.requests_path, records,
                          "nlq_requests", "request_id")
        return {"registered": ok,
                  "request_id": request_data["request_id"]}

    def transition_request_state(
        self, request_id: str, new_state: str,
        actor: str, reason: str,
        translated_sql: str = "",
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in QUERY_REQUEST_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.requests_path,
                                "nlq_requests", ("request_id",))
        for r in records:
            if r.get("request_id") == request_id:
                current = r.get("state", "SUBMITTED")
                allowed = ALLOWED_REQUEST_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                if new_state == "TRANSLATED" and translated_sql:
                    r["translated_sql"] = translated_sql
                    r["translation_attempts"] = (
                        r.get("translation_attempts", 0) + 1
                    )
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.requests_path, records,
                                  "nlq_requests", "request_id")
                return {"transitioned": ok,
                          "from": current, "to": new_state}
        return {"transitioned": False, "error": "request_not_found"}

    def record_safety_review(
        self, review_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("review_id", "request_id", "verdict"):
            if f not in review_data or not review_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if review_data["verdict"] not in SAFETY_VERDICTS:
            return {"recorded": False,
                       "error": f"invalid_verdict:{review_data['verdict']}"}
        records = self._load(self.reviews_path,
                                "nlq_safety_reviews", ("review_id",))
        if any(r.get("review_id") == review_data["review_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_review_id"}
        record = {
            "review_id": review_data["review_id"],
            "request_id": review_data["request_id"],
            "verdict": review_data["verdict"],
            "rationale": review_data.get("rationale", ""),
            "reviewed_by": actor,
            "reviewed_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.reviews_path, records,
                          "nlq_safety_reviews", "review_id")
        return {"recorded": ok, "review_id": review_data["review_id"]}

    def record_execution_outcome(
        self, outcome_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("outcome_id", "request_id", "outcome"):
            if f not in outcome_data or not outcome_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if outcome_data["outcome"] not in EXECUTION_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{outcome_data['outcome']}"}
        records = self._load(self.outcomes_path,
                                "nlq_execution_outcomes", ("outcome_id",))
        if any(r.get("outcome_id") == outcome_data["outcome_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_outcome_id"}
        rows_returned = outcome_data.get("rows_returned")
        if rows_returned is not None:
            try:
                rows_returned = int(rows_returned)
                if rows_returned > DEFAULT_MAX_ROWS_RETURNED:
                    return {"recorded": False,
                              "error": f"rows_exceed_max:{DEFAULT_MAX_ROWS_RETURNED}"}
            except (TypeError, ValueError):
                return {"recorded": False, "error": "rows_returned_not_int"}
        record = {
            "outcome_id": outcome_data["outcome_id"],
            "request_id": outcome_data["request_id"],
            "outcome": outcome_data["outcome"],
            "rows_returned": rows_returned,
            "duration_ms": outcome_data.get("duration_ms"),
            "executed_by": actor,
            "executed_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.outcomes_path, records,
                          "nlq_execution_outcomes", "outcome_id")
        return {"recorded": ok, "outcome_id": outcome_data["outcome_id"]}

    def query_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        requests = self._load(self.requests_path,
                                  "nlq_requests", ("request_id",))
        recent = [r for r in requests
                       if r.get("submitted_at", "") >= cutoff]
        outcomes = self._load(self.outcomes_path,
                                  "nlq_execution_outcomes", ("outcome_id",))
        outcome_by_req = {o.get("request_id"): o for o in outcomes}
        executed = sum(1 for r in recent
                              if r.get("state") == "EXECUTED")
        rejected = sum(1 for r in recent
                              if r.get("state") == "REJECTED")
        success = sum(
            1 for r in recent
            if outcome_by_req.get(r.get("request_id"), {}).get("outcome")
                  == "SUCCESS"
        )
        per_domain: Dict[str, int] = {}
        for r in recent:
            d = r.get("domain", "")
            per_domain[d] = per_domain.get(d, 0) + 1
        return {
            "window_days": days,
            "total_requests": len(recent),
            "executed": executed,
            "rejected": rejected,
            "success": success,
            "success_rate_pct": round(
                (success / len(recent) * 100) if recent else 0, 1,
            ),
            "per_domain": per_domain,
        }

    def requests_by_state(self, state: str) -> List[Dict[str, Any]]:
        if state not in QUERY_REQUEST_STATES:
            return []
        records = self._load(self.requests_path,
                                "nlq_requests", ("request_id",))
        return [r for r in records if r.get("state") == state]


def _self_test() -> None:
    import tempfile

    assert QUERY_REQUEST_STATES == (
        "SUBMITTED", "TRANSLATED", "SAFETY_REVIEW",
        "APPROVED", "EXECUTED", "REJECTED",
    )
    assert ALLOWED_REQUEST_TRANSITIONS["EXECUTED"] == ()
    assert ALLOWED_REQUEST_TRANSITIONS["REJECTED"] == ()
    assert QUERY_DOMAINS == (
        "CUSTOMERS", "ACCOUNTS", "TRANSACTIONS", "REPORTS", "AGGREGATES",
    )
    assert SAFETY_VERDICTS == (
        "SAFE", "UNSAFE_DDL", "UNSAFE_DML", "UNSAFE_SCOPE",
    )
    assert EXECUTION_OUTCOMES == (
        "SUCCESS", "EMPTY", "ERROR", "TIMEOUT",
    )
    assert DEFAULT_QUERY_TIMEOUT_SECONDS == 30
    assert DEFAULT_MAX_ROWS_RETURNED == 10000
    assert DEFAULT_TRANSLATION_RETRY_LIMIT == 3

    with tempfile.TemporaryDirectory() as tmpdir:
        e = NLQEngine(
            requests_path=Path(tmpdir) / "r.json",
            reviews_path=Path(tmpdir) / "v.json",
            outcomes_path=Path(tmpdir) / "o.json",
        )
        # Request
        r = e.register_query_request(
            {"request_id": "NLQ-001",
             "natural_language": "Top 10 customers by deposit balance",
             "domain": "CUSTOMERS"},
            actor="analyst1",
        )
        assert r["registered"]
        # Invalid domain
        r = e.register_query_request(
            {"request_id": "X", "natural_language": "Y",
             "domain": "WHATEVER"},
            actor="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_request_state(
            "NLQ-001", "TRANSLATED",
            actor="llm-svc", reason="auto-translated",
            translated_sql="SELECT * FROM customers ORDER BY balance DESC LIMIT 10",
        )
        assert r["transitioned"]
        r = e.transition_request_state(
            "NLQ-001", "SAFETY_REVIEW",
            actor="reviewer", reason="review",
        )
        assert r["transitioned"]
        # Record safety review
        r = e.record_safety_review(
            {"review_id": "REV-001",
             "request_id": "NLQ-001",
             "verdict": "SAFE",
             "rationale": "SELECT-only on customers view"},
            actor="reviewer",
        )
        assert r["recorded"]
        # Invalid verdict
        r = e.record_safety_review(
            {"review_id": "X", "request_id": "Y", "verdict": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        r = e.transition_request_state(
            "NLQ-001", "APPROVED",
            actor="reviewer", reason="safe",
        )
        assert r["transitioned"]
        r = e.transition_request_state(
            "NLQ-001", "EXECUTED",
            actor="executor", reason="ran",
        )
        assert r["transitioned"]
        # EXECUTED is terminal
        r = e.transition_request_state(
            "NLQ-001", "SUBMITTED",
            actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Outcome
        r = e.record_execution_outcome(
            {"outcome_id": "OUT-001",
             "request_id": "NLQ-001",
             "outcome": "SUCCESS",
             "rows_returned": 10,
             "duration_ms": 250},
            actor="executor",
        )
        assert r["recorded"]
        # Rows exceed max
        r = e.record_execution_outcome(
            {"outcome_id": "OUT-X",
             "request_id": "NLQ-001",
             "outcome": "SUCCESS",
             "rows_returned": 999999},
            actor="executor",
        )
        assert not r["recorded"]
        # Invalid outcome
        r = e.record_execution_outcome(
            {"outcome_id": "OUT-Y",
             "request_id": "NLQ-001",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Metrics
        m = e.query_metrics(days=30)
        assert m["total_requests"] == 1
        assert m["executed"] == 1
        assert m["success"] == 1
        assert m["success_rate_pct"] == 100.0
        assert m["per_domain"]["CUSTOMERS"] == 1

        # By state
        executed = e.requests_by_state("EXECUTED")
        assert len(executed) == 1

    print("  ✅ analytics_nlq self-test PASS")


if __name__ == "__main__":
    _self_test()

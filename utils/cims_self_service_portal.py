"""
================================================================================
A2Z MIS 360 — Standard #177: Customer Self-Service Instruction Portal
================================================================================

Risk classification: Cat C (read-side portal session + tracking
registry; never modifies upstream instructions; provides self-service
status + cancellation request handles to customers).

Subcategory: cims

Real-time instruction tracking portal integrated with CIMS. Composes
upstream capture (#166), classification (#167), STP (#168), identity
(#173), process intelligence (#169), exception management (#175),
audit history (#176), and agent workspace (#178) — customers can
view their instructions, see real-time status, request cancellation
or amendment, and provide feedback. The engine never modifies the
underlying instruction; it surfaces requests that the agent
workspace (#178) picks up.

Public API:
    register_portal_session(session_data, actor, reason)
    transition_session_state(session_id, new_state, actor, reason)
    record_status_query(query_data, actor)
    register_action_request(request_data, actor, reason)
    transition_request_state(request_id, new_state, actor, reason)
    portal_metrics(days=30) -> Dict
    customer_open_requests(customer_id) -> List

PORTAL_SESSION_STATES byte-for-byte (5):
    AUTHENTICATED, ACTIVE, IDLE, EXPIRED, REVOKED

ALLOWED_SESSION_TRANSITIONS (Rule 4):
    AUTHENTICATED → ACTIVE | EXPIRED | REVOKED
    ACTIVE        → IDLE | EXPIRED | REVOKED
    IDLE          → ACTIVE | EXPIRED | REVOKED
    EXPIRED       → ()
    REVOKED       → ()

ACTION_REQUEST_TYPES byte-for-byte (5):
    CANCEL_INSTRUCTION, AMEND_INSTRUCTION, ADD_DOCUMENT,
    ESCALATE_TO_AGENT, REQUEST_REFUND

ACTION_REQUEST_STATES byte-for-byte (5):
    SUBMITTED, ACKNOWLEDGED, IN_PROGRESS, RESOLVED, REJECTED

ALLOWED_REQUEST_TRANSITIONS (Rule 4):
    SUBMITTED    → ACKNOWLEDGED | REJECTED
    ACKNOWLEDGED → IN_PROGRESS | REJECTED
    IN_PROGRESS  → RESOLVED | REJECTED
    RESOLVED     → ()
    REJECTED     → ()

STATUS_QUERY_TYPES byte-for-byte (5):
    INSTRUCTION_STATUS, DOCUMENT_STATUS, FEE_BREAKDOWN,
    EXPECTED_COMPLETION, AGENT_HANDOFF_HISTORY

PORTAL_AUTH_METHODS byte-for-byte (4):
    OTP_SMS, OTP_EMAIL, BIOMETRIC, FEDERATED_SSO

DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES = 10
DEFAULT_SESSION_HARD_TIMEOUT_MINUTES = 60
DEFAULT_REQUEST_ACK_TARGET_MINUTES = 30

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PORTAL_SESSION_STATES: Tuple[str, ...] = (
    "AUTHENTICATED", "ACTIVE", "IDLE", "EXPIRED", "REVOKED",
)

ALLOWED_SESSION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "AUTHENTICATED": ("ACTIVE", "EXPIRED", "REVOKED"),
    "ACTIVE":        ("IDLE", "EXPIRED", "REVOKED"),
    "IDLE":          ("ACTIVE", "EXPIRED", "REVOKED"),
    "EXPIRED":       (),
    "REVOKED":       (),
}

ACTION_REQUEST_TYPES: Tuple[str, ...] = (
    "CANCEL_INSTRUCTION", "AMEND_INSTRUCTION", "ADD_DOCUMENT",
    "ESCALATE_TO_AGENT", "REQUEST_REFUND",
)

ACTION_REQUEST_STATES: Tuple[str, ...] = (
    "SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS",
    "RESOLVED", "REJECTED",
)

ALLOWED_REQUEST_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "SUBMITTED":    ("ACKNOWLEDGED", "REJECTED"),
    "ACKNOWLEDGED": ("IN_PROGRESS", "REJECTED"),
    "IN_PROGRESS":  ("RESOLVED", "REJECTED"),
    "RESOLVED":     (),
    "REJECTED":     (),
}

STATUS_QUERY_TYPES: Tuple[str, ...] = (
    "INSTRUCTION_STATUS", "DOCUMENT_STATUS", "FEE_BREAKDOWN",
    "EXPECTED_COMPLETION", "AGENT_HANDOFF_HISTORY",
)

PORTAL_AUTH_METHODS: Tuple[str, ...] = (
    "OTP_SMS", "OTP_EMAIL", "BIOMETRIC", "FEDERATED_SSO",
)

DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES = 10
DEFAULT_SESSION_HARD_TIMEOUT_MINUTES = 60
DEFAULT_REQUEST_ACK_TARGET_MINUTES = 30


class SelfServicePortalEngine:
    """Portal session + status query + action request registry."""

    def __init__(
        self,
        sessions_path: Optional[Path] = None,
        queries_path: Optional[Path] = None,
        requests_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.sessions_path = (
            sessions_path or base / "cims_portal_sessions.json"
        )
        self.queries_path = (
            queries_path or base / "cims_portal_queries.json"
        )
        self.requests_path = (
            requests_path or base / "cims_portal_requests.json"
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

    def register_portal_session(
        self, session_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("session_id", "customer_id", "auth_method"):
            if f not in session_data or not session_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if session_data["auth_method"] not in PORTAL_AUTH_METHODS:
            return {"registered": False,
                       "error": f"invalid_auth_method:{session_data['auth_method']}"}
        records = self._load(self.sessions_path,
                                "cims_portal_sessions", ("session_id",))
        if any(r.get("session_id") == session_data["session_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_session_id"}
        record = {
            "session_id": session_data["session_id"],
            "customer_id": session_data["customer_id"],
            "auth_method": session_data["auth_method"],
            "device_info": session_data.get("device_info", ""),
            "state": "AUTHENTICATED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "AUTHENTICATED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.sessions_path, records,
                          "cims_portal_sessions", "session_id")
        return {"registered": ok, "session_id": session_data["session_id"]}

    def transition_session_state(
        self, session_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in PORTAL_SESSION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.sessions_path,
                                "cims_portal_sessions", ("session_id",))
        for r in records:
            if r.get("session_id") == session_id:
                current = r.get("state", "AUTHENTICATED")
                allowed = ALLOWED_SESSION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.sessions_path, records,
                                  "cims_portal_sessions", "session_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "session_not_found"}

    def record_status_query(
        self, query_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("query_id", "session_id", "query_type",
                      "subject_id"):
            if f not in query_data or not query_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if query_data["query_type"] not in STATUS_QUERY_TYPES:
            return {"recorded": False,
                       "error": f"invalid_query_type:{query_data['query_type']}"}
        records = self._load(self.queries_path,
                                "cims_portal_queries", ("query_id",))
        if any(r.get("query_id") == query_data["query_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_query_id"}
        record = {
            "query_id": query_data["query_id"],
            "session_id": query_data["session_id"],
            "query_type": query_data["query_type"],
            "subject_id": query_data["subject_id"],
            "narrative": query_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.queries_path, records,
                          "cims_portal_queries", "query_id")
        return {"recorded": ok, "query_id": query_data["query_id"]}

    def register_action_request(
        self, request_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("request_id", "customer_id",
                      "linked_session_id", "request_type", "narrative"):
            if f not in request_data or not request_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if request_data["request_type"] not in ACTION_REQUEST_TYPES:
            return {"registered": False,
                       "error": f"invalid_request_type:{request_data['request_type']}"}
        records = self._load(self.requests_path,
                                "cims_portal_requests", ("request_id",))
        if any(r.get("request_id") == request_data["request_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_request_id"}
        record = {
            "request_id": request_data["request_id"],
            "customer_id": request_data["customer_id"],
            "linked_session_id": request_data["linked_session_id"],
            "request_type": request_data["request_type"],
            "narrative": request_data["narrative"],
            "state": "SUBMITTED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "SUBMITTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.requests_path, records,
                          "cims_portal_requests", "request_id")
        return {"registered": ok, "request_id": request_data["request_id"]}

    def transition_request_state(
        self, request_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in ACTION_REQUEST_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.requests_path,
                                "cims_portal_requests", ("request_id",))
        for r in records:
            if r.get("request_id") == request_id:
                current = r.get("state", "SUBMITTED")
                allowed = ALLOWED_REQUEST_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                if new_state == "ACKNOWLEDGED":
                    r["acknowledged_at"] = datetime.utcnow().isoformat()
                if new_state == "RESOLVED":
                    r["resolved_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.requests_path, records,
                                  "cims_portal_requests", "request_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "request_not_found"}

    def portal_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        sessions = [
            s for s in self._load(self.sessions_path,
                                            "cims_portal_sessions",
                                            ("session_id",))
            if s.get("registered_at", "") >= cutoff
        ]
        queries = [
            q for q in self._load(self.queries_path,
                                            "cims_portal_queries",
                                            ("query_id",))
            if q.get("recorded_at", "") >= cutoff
        ]
        requests = [
            rq for rq in self._load(self.requests_path,
                                              "cims_portal_requests",
                                              ("request_id",))
            if rq.get("registered_at", "") >= cutoff
        ]
        per_query_type: Dict[str, int] = {}
        for q in queries:
            qt = q.get("query_type", "")
            per_query_type[qt] = per_query_type.get(qt, 0) + 1
        per_request_type: Dict[str, int] = {}
        per_request_state: Dict[str, int] = {}
        for r in requests:
            rt = r.get("request_type", "")
            per_request_type[rt] = per_request_type.get(rt, 0) + 1
            rs = r.get("state", "")
            per_request_state[rs] = per_request_state.get(rs, 0) + 1
        # ack timeliness
        ack_within_target = 0
        ack_total = 0
        for r in requests:
            ack = r.get("acknowledged_at")
            if not ack:
                continue
            try:
                reg = datetime.fromisoformat(r.get("registered_at", ""))
                ack_dt = datetime.fromisoformat(ack)
            except ValueError:
                continue
            ack_total += 1
            mins = (ack_dt - reg).total_seconds() / 60
            if mins <= DEFAULT_REQUEST_ACK_TARGET_MINUTES:
                ack_within_target += 1
        ack_rate = round(
            (ack_within_target / ack_total * 100)
            if ack_total else 0, 1,
        )
        return {
            "window_days": days,
            "sessions": len(sessions),
            "queries": len(queries),
            "requests": len(requests),
            "per_query_type": per_query_type,
            "per_request_type": per_request_type,
            "per_request_state": per_request_state,
            "ack_within_target_pct": ack_rate,
            "ack_target_minutes": DEFAULT_REQUEST_ACK_TARGET_MINUTES,
        }

    def customer_open_requests(
        self, customer_id: str,
    ) -> List[Dict[str, Any]]:
        if not customer_id:
            return []
        records = self._load(self.requests_path,
                                "cims_portal_requests", ("request_id",))
        open_states = ("SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS")
        return [
            r for r in records
            if r.get("customer_id") == customer_id
                 and r.get("state") in open_states
        ]


def _self_test() -> None:
    import tempfile

    assert PORTAL_SESSION_STATES == (
        "AUTHENTICATED", "ACTIVE", "IDLE",
        "EXPIRED", "REVOKED",
    )
    assert ALLOWED_SESSION_TRANSITIONS["EXPIRED"] == ()
    assert ALLOWED_SESSION_TRANSITIONS["REVOKED"] == ()
    assert ACTION_REQUEST_TYPES == (
        "CANCEL_INSTRUCTION", "AMEND_INSTRUCTION",
        "ADD_DOCUMENT", "ESCALATE_TO_AGENT", "REQUEST_REFUND",
    )
    assert ACTION_REQUEST_STATES == (
        "SUBMITTED", "ACKNOWLEDGED", "IN_PROGRESS",
        "RESOLVED", "REJECTED",
    )
    assert ALLOWED_REQUEST_TRANSITIONS["RESOLVED"] == ()
    assert ALLOWED_REQUEST_TRANSITIONS["REJECTED"] == ()
    assert STATUS_QUERY_TYPES == (
        "INSTRUCTION_STATUS", "DOCUMENT_STATUS", "FEE_BREAKDOWN",
        "EXPECTED_COMPLETION", "AGENT_HANDOFF_HISTORY",
    )
    assert PORTAL_AUTH_METHODS == (
        "OTP_SMS", "OTP_EMAIL", "BIOMETRIC", "FEDERATED_SSO",
    )
    assert DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES == 10
    assert DEFAULT_SESSION_HARD_TIMEOUT_MINUTES == 60
    assert DEFAULT_REQUEST_ACK_TARGET_MINUTES == 30

    with tempfile.TemporaryDirectory() as tmpdir:
        e = SelfServicePortalEngine(
            sessions_path=Path(tmpdir) / "s.json",
            queries_path=Path(tmpdir) / "q.json",
            requests_path=Path(tmpdir) / "r.json",
        )
        # Session
        r = e.register_portal_session(
            {"session_id": "PS-001",
             "customer_id": "CUST-001",
             "auth_method": "BIOMETRIC",
             "device_info": "iPhone 15"},
            actor="customer", reason="login",
        )
        assert r["registered"]
        # Bad auth method
        r = e.register_portal_session(
            {"session_id": "X", "customer_id": "Y",
             "auth_method": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Session lifecycle
        r = e.transition_session_state(
            "PS-001", "ACTIVE",
            actor="customer", reason="navigated",
        )
        assert r["transitioned"]
        r = e.transition_session_state(
            "PS-001", "IDLE",
            actor="customer", reason="paused",
        )
        assert r["transitioned"]
        r = e.transition_session_state(
            "PS-001", "EXPIRED",
            actor="system", reason="timeout",
        )
        assert r["transitioned"]
        # EXPIRED is terminal
        r = e.transition_session_state(
            "PS-001", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Query
        r = e.record_status_query(
            {"query_id": "Q-001",
             "session_id": "PS-001",
             "query_type": "INSTRUCTION_STATUS",
             "subject_id": "INST-001"},
            actor="customer",
        )
        assert r["recorded"]
        # Bad type
        r = e.record_status_query(
            {"query_id": "X", "session_id": "Y",
             "query_type": "WHATEVER", "subject_id": "Z"},
            actor="x",
        )
        assert not r["recorded"]

        # Request
        r = e.register_action_request(
            {"request_id": "REQ-001",
             "customer_id": "CUST-001",
             "linked_session_id": "PS-001",
             "request_type": "CANCEL_INSTRUCTION",
             "narrative": "Customer changed mind"},
            actor="customer", reason="self-cancel",
        )
        assert r["registered"]
        # Bad type
        r = e.register_action_request(
            {"request_id": "X", "customer_id": "Y",
             "linked_session_id": "Z",
             "request_type": "WHATEVER",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Request lifecycle
        r = e.transition_request_state(
            "REQ-001", "ACKNOWLEDGED",
            actor="agent", reason="picked up",
        )
        assert r["transitioned"]
        r = e.transition_request_state(
            "REQ-001", "IN_PROGRESS",
            actor="agent", reason="working",
        )
        assert r["transitioned"]
        r = e.transition_request_state(
            "REQ-001", "RESOLVED",
            actor="agent", reason="cancelled",
        )
        assert r["transitioned"]
        # RESOLVED is terminal
        r = e.transition_request_state(
            "REQ-001", "SUBMITTED", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Open requests for customer (should be empty after RESOLVED)
        opens = e.customer_open_requests("CUST-001")
        assert len(opens) == 0

        # Add another open request
        e.register_action_request(
            {"request_id": "REQ-002",
             "customer_id": "CUST-001",
             "linked_session_id": "PS-001",
             "request_type": "ADD_DOCUMENT",
             "narrative": "Forgot to attach"},
            actor="customer", reason="oops",
        )
        opens = e.customer_open_requests("CUST-001")
        assert len(opens) == 1

        # Metrics
        m = e.portal_metrics(days=30)
        assert m["sessions"] == 1
        assert m["queries"] == 1
        assert m["requests"] == 2
        assert m["per_request_state"].get("RESOLVED", 0) == 1
        assert m["per_request_state"].get("SUBMITTED", 0) == 1

    print("  ✅ cims_self_service_portal self-test PASS")


if __name__ == "__main__":
    _self_test()

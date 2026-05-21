"""
================================================================================
A2Z MIS 360 — Standard #286: Credit Analyst Workbench
================================================================================

Risk classification: Cat C (analytics consolidation; read-side over upstream
credit + statement + bureau engines).

Subcategory: analytics_hub

Single read-side surface for a credit analyst working on a loan
application or annual review. Composes — does NOT replace — the
existing credit decision engine, statement analyzer, bureau checks,
and affordability calculations from the credit arc (#119–#130 active).

The workbench's job is to answer one question for the analyst:
"For this customer, what does each upstream engine currently say,
and where do they conflict?"

Public API:
    register_workbench_session(session_data, actor, reason)
    transition_session_state(session_id, new_state, actor, reason)
    register_workbench_view(view_data, actor, reason)
    record_data_pull(pull_data, actor)
    record_analyst_note(note_data, actor)
    workbench_summary(session_id) -> Dict
    conflict_report(session_id) -> Dict

WORKBENCH_SESSION_STATES byte-for-byte (5):
    OPEN, IN_REVIEW, ESCALATED, COMPLETED, CANCELLED

ALLOWED_SESSION_TRANSITIONS (Rule 4):
    OPEN       → IN_REVIEW | CANCELLED
    IN_REVIEW  → ESCALATED | COMPLETED | CANCELLED
    ESCALATED  → IN_REVIEW | COMPLETED | CANCELLED
    COMPLETED  → ()
    CANCELLED  → ()

DATA_SOURCES byte-for-byte (6):
    CREDIT_DECISION_ENGINE, STATEMENT_ANALYZER, CREDIT_BUREAU,
    AFFORDABILITY_ENGINE, COLLATERAL_REGISTRY, DOCUMENT_VERIFIER

VIEW_TYPES byte-for-byte (5):
    SUMMARY, DETAIL, COMPARISON, TIMELINE, CONFLICT

NOTE_CATEGORIES byte-for-byte (5):
    OBSERVATION, CONCERN, FOLLOW_UP, RECOMMENDATION, DECISION_RATIONALE

DEFAULT_SESSION_TIMEOUT_HOURS = 24
DEFAULT_DATA_PULL_CACHE_MINUTES = 15

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


WORKBENCH_SESSION_STATES: Tuple[str, ...] = (
    "OPEN", "IN_REVIEW", "ESCALATED", "COMPLETED", "CANCELLED",
)

ALLOWED_SESSION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":       ("IN_REVIEW", "CANCELLED"),
    "IN_REVIEW":  ("ESCALATED", "COMPLETED", "CANCELLED"),
    "ESCALATED":  ("IN_REVIEW", "COMPLETED", "CANCELLED"),
    "COMPLETED":  (),
    "CANCELLED":  (),
}

DATA_SOURCES: Tuple[str, ...] = (
    "CREDIT_DECISION_ENGINE", "STATEMENT_ANALYZER", "CREDIT_BUREAU",
    "AFFORDABILITY_ENGINE", "COLLATERAL_REGISTRY", "DOCUMENT_VERIFIER",
)

VIEW_TYPES: Tuple[str, ...] = (
    "SUMMARY", "DETAIL", "COMPARISON", "TIMELINE", "CONFLICT",
)

NOTE_CATEGORIES: Tuple[str, ...] = (
    "OBSERVATION", "CONCERN", "FOLLOW_UP",
    "RECOMMENDATION", "DECISION_RATIONALE",
)

DEFAULT_SESSION_TIMEOUT_HOURS = 24
DEFAULT_DATA_PULL_CACHE_MINUTES = 15


class CreditWorkbenchEngine:
    """Read-side composition over upstream credit engines.

    Owns session + view + note state. Does NOT replicate underlying
    engine logic — every data pull is a snapshot of what the upstream
    engine returned at pull time, with a timestamp for freshness.
    """

    def __init__(
        self,
        sessions_path: Optional[Path] = None,
        views_path: Optional[Path] = None,
        pulls_path: Optional[Path] = None,
        notes_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.sessions_path = sessions_path or base / "credit_workbench_sessions.json"
        self.views_path = views_path or base / "credit_workbench_views.json"
        self.pulls_path = pulls_path or base / "credit_workbench_pulls.json"
        self.notes_path = notes_path or base / "credit_workbench_notes.json"

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

    def register_workbench_session(
        self, session_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("session_id", "customer_id", "loan_application_id",
                      "analyst_role"):
            if f not in session_data or not session_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.sessions_path,
                                "credit_workbench_sessions", ("session_id",))
        if any(r.get("session_id") == session_data["session_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_session_id"}
        record = {
            "session_id": session_data["session_id"],
            "customer_id": session_data["customer_id"],
            "loan_application_id": session_data["loan_application_id"],
            "analyst_role": session_data["analyst_role"],
            "purpose": session_data.get("purpose", ""),
            "state": "OPEN",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.sessions_path, records,
                          "credit_workbench_sessions", "session_id")
        return {"registered": ok,
                  "session_id": session_data["session_id"]}

    def transition_session_state(
        self, session_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in WORKBENCH_SESSION_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.sessions_path,
                                "credit_workbench_sessions", ("session_id",))
        for r in records:
            if r.get("session_id") == session_id:
                current = r.get("state", "OPEN")
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
                if new_state == "COMPLETED":
                    r["completed_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.sessions_path, records,
                                  "credit_workbench_sessions", "session_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "session_not_found"}

    def register_workbench_view(
        self, view_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("view_id", "session_id", "view_type"):
            if f not in view_data or not view_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if view_data["view_type"] not in VIEW_TYPES:
            return {"registered": False,
                       "error": f"invalid_view_type:{view_data['view_type']}"}
        # Verify session exists
        sessions = self._load(self.sessions_path,
                                  "credit_workbench_sessions", ("session_id",))
        if not any(s.get("session_id") == view_data["session_id"]
                       for s in sessions):
            return {"registered": False, "error": "session_not_found"}
        records = self._load(self.views_path,
                                "credit_workbench_views", ("view_id",))
        if any(r.get("view_id") == view_data["view_id"] for r in records):
            return {"registered": False, "error": "duplicate_view_id"}
        record = {
            "view_id": view_data["view_id"],
            "session_id": view_data["session_id"],
            "view_type": view_data["view_type"],
            "title": view_data.get("title", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.views_path, records,
                          "credit_workbench_views", "view_id")
        return {"registered": ok, "view_id": view_data["view_id"]}

    def record_data_pull(
        self, pull_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("pull_id", "session_id", "data_source"):
            if f not in pull_data or not pull_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if pull_data["data_source"] not in DATA_SOURCES:
            return {"recorded": False,
                       "error": f"invalid_data_source:{pull_data['data_source']}"}
        records = self._load(self.pulls_path,
                                "credit_workbench_pulls", ("pull_id",))
        if any(r.get("pull_id") == pull_data["pull_id"] for r in records):
            return {"recorded": False, "error": "duplicate_pull_id"}
        record = {
            "pull_id": pull_data["pull_id"],
            "session_id": pull_data["session_id"],
            "data_source": pull_data["data_source"],
            "snapshot_summary": pull_data.get("snapshot_summary", ""),
            "snapshot_decision": pull_data.get("snapshot_decision", ""),
            "snapshot_score": pull_data.get("snapshot_score"),
            "pulled_by": actor,
            "pulled_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.pulls_path, records,
                          "credit_workbench_pulls", "pull_id")
        return {"recorded": ok, "pull_id": pull_data["pull_id"]}

    def record_analyst_note(
        self, note_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("note_id", "session_id", "category", "body"):
            if f not in note_data or not note_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if note_data["category"] not in NOTE_CATEGORIES:
            return {"recorded": False,
                       "error": f"invalid_category:{note_data['category']}"}
        records = self._load(self.notes_path,
                                "credit_workbench_notes", ("note_id",))
        if any(r.get("note_id") == note_data["note_id"] for r in records):
            return {"recorded": False, "error": "duplicate_note_id"}
        record = {
            "note_id": note_data["note_id"],
            "session_id": note_data["session_id"],
            "category": note_data["category"],
            "body": note_data["body"],
            "linked_pull_id": note_data.get("linked_pull_id", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.notes_path, records,
                          "credit_workbench_notes", "note_id")
        return {"recorded": ok, "note_id": note_data["note_id"]}

    def workbench_summary(self, session_id: str) -> Dict[str, Any]:
        sessions = self._load(self.sessions_path,
                                  "credit_workbench_sessions", ("session_id",))
        session = next((s for s in sessions
                              if s.get("session_id") == session_id), None)
        if session is None:
            return {"found": False, "error": "session_not_found"}
        pulls = [p for p in self._load(self.pulls_path,
                                                 "credit_workbench_pulls",
                                                 ("pull_id",))
                       if p.get("session_id") == session_id]
        notes = [n for n in self._load(self.notes_path,
                                                 "credit_workbench_notes",
                                                 ("note_id",))
                       if n.get("session_id") == session_id]
        sources_pulled = sorted({p.get("data_source") for p in pulls})
        notes_by_cat = {}
        for n in notes:
            cat = n.get("category", "")
            notes_by_cat[cat] = notes_by_cat.get(cat, 0) + 1
        return {
            "found": True,
            "session_id": session_id,
            "state": session.get("state"),
            "customer_id": session.get("customer_id"),
            "loan_application_id": session.get("loan_application_id"),
            "data_pulls_count": len(pulls),
            "sources_pulled": sources_pulled,
            "sources_missing": sorted(
                [s for s in DATA_SOURCES if s not in sources_pulled],
            ),
            "notes_count": len(notes),
            "notes_by_category": notes_by_cat,
        }

    def conflict_report(self, session_id: str) -> Dict[str, Any]:
        """Surface conflicts between data pulls within the session.

        Conflict = two pulls from different sources whose
        snapshot_decision values differ for the same customer.
        """
        pulls = [p for p in self._load(self.pulls_path,
                                                 "credit_workbench_pulls",
                                                 ("pull_id",))
                       if p.get("session_id") == session_id]
        decisions: Dict[str, List[Dict[str, Any]]] = {}
        for p in pulls:
            d = p.get("snapshot_decision", "")
            if d:
                decisions.setdefault(d, []).append(p)
        conflicts = []
        if len(decisions) > 1:
            # Multiple distinct decisions across sources
            for decision, source_pulls in decisions.items():
                conflicts.append({
                    "decision": decision,
                    "sources": sorted({sp.get("data_source") for sp in source_pulls}),
                    "pull_count": len(source_pulls),
                })
        return {
            "session_id": session_id,
            "total_pulls": len(pulls),
            "distinct_decisions": len(decisions),
            "conflict_count": max(0, len(decisions) - 1),
            "conflicts": conflicts,
        }


def _self_test() -> None:
    import tempfile

    assert WORKBENCH_SESSION_STATES == (
        "OPEN", "IN_REVIEW", "ESCALATED", "COMPLETED", "CANCELLED",
    )
    assert ALLOWED_SESSION_TRANSITIONS["COMPLETED"] == ()
    assert ALLOWED_SESSION_TRANSITIONS["CANCELLED"] == ()
    assert DATA_SOURCES == (
        "CREDIT_DECISION_ENGINE", "STATEMENT_ANALYZER", "CREDIT_BUREAU",
        "AFFORDABILITY_ENGINE", "COLLATERAL_REGISTRY", "DOCUMENT_VERIFIER",
    )
    assert VIEW_TYPES == (
        "SUMMARY", "DETAIL", "COMPARISON", "TIMELINE", "CONFLICT",
    )
    assert NOTE_CATEGORIES == (
        "OBSERVATION", "CONCERN", "FOLLOW_UP",
        "RECOMMENDATION", "DECISION_RATIONALE",
    )
    assert DEFAULT_SESSION_TIMEOUT_HOURS == 24
    assert DEFAULT_DATA_PULL_CACHE_MINUTES == 15

    with tempfile.TemporaryDirectory() as tmpdir:
        e = CreditWorkbenchEngine(
            sessions_path=Path(tmpdir) / "s.json",
            views_path=Path(tmpdir) / "v.json",
            pulls_path=Path(tmpdir) / "p.json",
            notes_path=Path(tmpdir) / "n.json",
        )
        # Session
        r = e.register_workbench_session(
            {"session_id": "WB-001",
             "customer_id": "CUST-100",
             "loan_application_id": "LOAN-2026-001",
             "analyst_role": "credit_analyst",
             "purpose": "Annual review"},
            actor="analyst1", reason="annual review",
        )
        assert r["registered"]
        # Missing field
        r = e.register_workbench_session(
            {"session_id": "X", "customer_id": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # State machine
        r = e.transition_session_state("WB-001", "IN_REVIEW",
                                              actor="analyst1",
                                              reason="started review")
        assert r["transitioned"]
        r = e.transition_session_state("WB-001", "ESCALATED",
                                              actor="analyst1",
                                              reason="needs senior")
        assert r["transitioned"]
        r = e.transition_session_state("WB-001", "IN_REVIEW",
                                              actor="senior",
                                              reason="back from escalation")
        assert r["transitioned"]
        r = e.transition_session_state("WB-001", "COMPLETED",
                                              actor="senior",
                                              reason="approved")
        assert r["transitioned"]
        # COMPLETED is terminal
        r = e.transition_session_state("WB-001", "IN_REVIEW",
                                              actor="x", reason="x")
        assert not r["transitioned"]

        # New session for view/pull tests
        e.register_workbench_session(
            {"session_id": "WB-002",
             "customer_id": "CUST-200",
             "loan_application_id": "LOAN-2026-002",
             "analyst_role": "credit_analyst"},
            actor="analyst1", reason="new app",
        )

        # View
        r = e.register_workbench_view(
            {"view_id": "VIEW-001",
             "session_id": "WB-002",
             "view_type": "COMPARISON",
             "title": "Bureau vs Decision Engine"},
            actor="analyst1", reason="comparing scores",
        )
        assert r["registered"]
        # Invalid view_type
        r = e.register_workbench_view(
            {"view_id": "X", "session_id": "WB-002",
             "view_type": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Data pulls — two with different decisions = conflict
        e.record_data_pull(
            {"pull_id": "PULL-001",
             "session_id": "WB-002",
             "data_source": "CREDIT_DECISION_ENGINE",
             "snapshot_decision": "APPROVE",
             "snapshot_score": "750"},
            actor="analyst1",
        )
        e.record_data_pull(
            {"pull_id": "PULL-002",
             "session_id": "WB-002",
             "data_source": "CREDIT_BUREAU",
             "snapshot_decision": "DECLINE",
             "snapshot_score": "580"},
            actor="analyst1",
        )
        # Invalid source
        r = e.record_data_pull(
            {"pull_id": "X", "session_id": "WB-002",
             "data_source": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Conflict report
        cr = e.conflict_report("WB-002")
        assert cr["total_pulls"] == 2
        assert cr["distinct_decisions"] == 2
        assert cr["conflict_count"] == 1

        # Note
        r = e.record_analyst_note(
            {"note_id": "NOTE-001",
             "session_id": "WB-002",
             "category": "CONCERN",
             "body": "Bureau vs decision engine disagree.",
             "linked_pull_id": "PULL-002"},
            actor="analyst1",
        )
        assert r["recorded"]
        # Invalid category
        r = e.record_analyst_note(
            {"note_id": "X", "session_id": "WB-002",
             "category": "WHATEVER", "body": "Y"},
            actor="x",
        )
        assert not r["recorded"]

        # Summary
        s = e.workbench_summary("WB-002")
        assert s["found"]
        assert s["data_pulls_count"] == 2
        assert "CREDIT_DECISION_ENGINE" in s["sources_pulled"]
        assert "CREDIT_BUREAU" in s["sources_pulled"]
        assert s["notes_count"] == 1
        assert s["notes_by_category"]["CONCERN"] == 1

    print("  ✅ analytics_credit_workbench self-test PASS")


if __name__ == "__main__":
    _self_test()

"""
================================================================================
A2Z MIS 360 — Standard #178: Agent Workspace for Instruction Processing
================================================================================

Risk classification: Cat C (read-side workspace coordination; never
auto-completes instructions; provides queue + AI assistance handles
to human agents).

Subcategory: cims

Unified agent workspace with instruction queue and AI assistance.
Composes upstream capture (#166), classification (#167), STP (#168),
identity (#173), process intelligence (#169), dropout prevention
(#170), NBA (#174), exception management (#175), SLA (#171),
secure docs (#172), and audit history (#176) — agents pick up
queued items, see surfaced AI suggestions (from upstream Cat D
hooks), and record their actions which append to the audit history.

Public API:
    register_agent(agent_data, actor, reason)
    transition_agent_state(agent_id, new_state, actor, reason)
    enqueue_work_item(item_data, actor, reason)
    transition_item_state(item_id, new_state, actor, reason)
    record_assignment(assignment_data, actor)
    record_action(action_data, actor)
    queue_summary() -> Dict
    workload_by_agent() -> Dict

AGENT_STATES byte-for-byte (5):
    AVAILABLE, ASSIGNED, ON_BREAK, OFFLINE, ARCHIVED

ALLOWED_AGENT_TRANSITIONS (Rule 4):
    AVAILABLE → ASSIGNED | ON_BREAK | OFFLINE | ARCHIVED
    ASSIGNED  → AVAILABLE | ON_BREAK | OFFLINE | ARCHIVED
    ON_BREAK  → AVAILABLE | OFFLINE | ARCHIVED
    OFFLINE   → AVAILABLE | ARCHIVED
    ARCHIVED  → ()

WORK_ITEM_STATES byte-for-byte (6):
    QUEUED, ASSIGNED, IN_PROGRESS, ON_HOLD, COMPLETED, CANCELLED

ALLOWED_ITEM_TRANSITIONS (Rule 4):
    QUEUED      → ASSIGNED | CANCELLED
    ASSIGNED    → IN_PROGRESS | QUEUED | CANCELLED
    IN_PROGRESS → ON_HOLD | COMPLETED | CANCELLED
    ON_HOLD     → IN_PROGRESS | CANCELLED
    COMPLETED   → ()
    CANCELLED   → ()

WORK_ITEM_PRIORITIES byte-for-byte (4):
    URGENT, HIGH, NORMAL, LOW

WORK_ITEM_SOURCES byte-for-byte (5):
    CAPTURE_HANDOFF, EXCEPTION_RAISED, SLA_APPROACHING,
    DROPOUT_INTERVENTION, MANUAL_ESCALATION

AGENT_ACTION_KINDS byte-for-byte (8):
    ITEM_CLAIMED, ITEM_RELEASED, NOTE_ADDED, CUSTOMER_CONTACTED,
    DOCUMENT_REVIEWED, AI_SUGGESTION_ACCEPTED,
    AI_SUGGESTION_REJECTED, ITEM_RESOLVED

AGENT_SKILL_TAGS byte-for-byte (5):
    KYC_REVIEW, COMPLAINT_HANDLING, DISPUTE_RESOLUTION,
    LOAN_PROCESSING, GENERAL

DEFAULT_QUEUE_REASSIGNMENT_HOURS = 4
DEFAULT_AGENT_BREAK_LIMIT_MINUTES = 60
DEFAULT_QUEUE_DEPTH_THRESHOLD = 50

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AGENT_STATES: Tuple[str, ...] = (
    "AVAILABLE", "ASSIGNED", "ON_BREAK", "OFFLINE", "ARCHIVED",
)

ALLOWED_AGENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "AVAILABLE": ("ASSIGNED", "ON_BREAK", "OFFLINE", "ARCHIVED"),
    "ASSIGNED":  ("AVAILABLE", "ON_BREAK", "OFFLINE", "ARCHIVED"),
    "ON_BREAK":  ("AVAILABLE", "OFFLINE", "ARCHIVED"),
    "OFFLINE":   ("AVAILABLE", "ARCHIVED"),
    "ARCHIVED":  (),
}

WORK_ITEM_STATES: Tuple[str, ...] = (
    "QUEUED", "ASSIGNED", "IN_PROGRESS",
    "ON_HOLD", "COMPLETED", "CANCELLED",
)

ALLOWED_ITEM_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "QUEUED":      ("ASSIGNED", "CANCELLED"),
    "ASSIGNED":    ("IN_PROGRESS", "QUEUED", "CANCELLED"),
    "IN_PROGRESS": ("ON_HOLD", "COMPLETED", "CANCELLED"),
    "ON_HOLD":     ("IN_PROGRESS", "CANCELLED"),
    "COMPLETED":   (),
    "CANCELLED":   (),
}

WORK_ITEM_PRIORITIES: Tuple[str, ...] = (
    "URGENT", "HIGH", "NORMAL", "LOW",
)

WORK_ITEM_SOURCES: Tuple[str, ...] = (
    "CAPTURE_HANDOFF", "EXCEPTION_RAISED", "SLA_APPROACHING",
    "DROPOUT_INTERVENTION", "MANUAL_ESCALATION",
)

AGENT_ACTION_KINDS: Tuple[str, ...] = (
    "ITEM_CLAIMED", "ITEM_RELEASED", "NOTE_ADDED",
    "CUSTOMER_CONTACTED", "DOCUMENT_REVIEWED",
    "AI_SUGGESTION_ACCEPTED", "AI_SUGGESTION_REJECTED",
    "ITEM_RESOLVED",
)

AGENT_SKILL_TAGS: Tuple[str, ...] = (
    "KYC_REVIEW", "COMPLAINT_HANDLING", "DISPUTE_RESOLUTION",
    "LOAN_PROCESSING", "GENERAL",
)

DEFAULT_QUEUE_REASSIGNMENT_HOURS = 4
DEFAULT_AGENT_BREAK_LIMIT_MINUTES = 60
DEFAULT_QUEUE_DEPTH_THRESHOLD = 50


class AgentWorkspaceEngine:
    """Agent + work item + assignment + action registry."""

    def __init__(
        self,
        agents_path: Optional[Path] = None,
        items_path: Optional[Path] = None,
        assignments_path: Optional[Path] = None,
        actions_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.agents_path = (
            agents_path or base / "cims_agents.json"
        )
        self.items_path = (
            items_path or base / "cims_work_items.json"
        )
        self.assignments_path = (
            assignments_path or base / "cims_assignments.json"
        )
        self.actions_path = (
            actions_path or base / "cims_agent_actions.json"
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

    def register_agent(
        self, agent_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("agent_id", "name", "skill_tags"):
            if f not in agent_data or agent_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        skills = agent_data["skill_tags"]
        if not isinstance(skills, list) or not skills:
            return {"registered": False, "error": "skill_tags_must_be_non_empty_list"}
        for s in skills:
            if s not in AGENT_SKILL_TAGS:
                return {"registered": False,
                           "error": f"invalid_skill_tag:{s}"}
        records = self._load(self.agents_path,
                                "cims_agents", ("agent_id",))
        if any(r.get("agent_id") == agent_data["agent_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_agent_id"}
        record = {
            "agent_id": agent_data["agent_id"],
            "name": agent_data["name"],
            "skill_tags": skills,
            "state": "AVAILABLE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "AVAILABLE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.agents_path, records,
                          "cims_agents", "agent_id")
        return {"registered": ok, "agent_id": agent_data["agent_id"]}

    def transition_agent_state(
        self, agent_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in AGENT_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.agents_path,
                                "cims_agents", ("agent_id",))
        for r in records:
            if r.get("agent_id") == agent_id:
                current = r.get("state", "AVAILABLE")
                allowed = ALLOWED_AGENT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.agents_path, records,
                                  "cims_agents", "agent_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "agent_not_found"}

    def enqueue_work_item(
        self, item_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"enqueued": False, "error": "actor_and_reason_required"}
        for f in ("item_id", "linked_session_id", "source",
                      "priority", "narrative"):
            if f not in item_data or not item_data[f]:
                return {"enqueued": False, "error": f"missing_field:{f}"}
        if item_data["source"] not in WORK_ITEM_SOURCES:
            return {"enqueued": False,
                       "error": f"invalid_source:{item_data['source']}"}
        if item_data["priority"] not in WORK_ITEM_PRIORITIES:
            return {"enqueued": False,
                       "error": f"invalid_priority:{item_data['priority']}"}
        records = self._load(self.items_path,
                                "cims_work_items", ("item_id",))
        if any(r.get("item_id") == item_data["item_id"]
                 for r in records):
            return {"enqueued": False, "error": "duplicate_item_id"}
        record = {
            "item_id": item_data["item_id"],
            "linked_session_id": item_data["linked_session_id"],
            "source": item_data["source"],
            "priority": item_data["priority"],
            "narrative": item_data["narrative"],
            "required_skill": item_data.get("required_skill", "GENERAL"),
            "state": "QUEUED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "QUEUED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        if record["required_skill"] not in AGENT_SKILL_TAGS:
            return {"enqueued": False,
                       "error": f"invalid_required_skill:{record['required_skill']}"}
        records.append(record)
        ok = self._save(self.items_path, records,
                          "cims_work_items", "item_id")
        return {"enqueued": ok, "item_id": item_data["item_id"]}

    def transition_item_state(
        self, item_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in WORK_ITEM_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.items_path,
                                "cims_work_items", ("item_id",))
        for r in records:
            if r.get("item_id") == item_id:
                current = r.get("state", "QUEUED")
                allowed = ALLOWED_ITEM_TRANSITIONS.get(current, ())
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
                ok = self._save(self.items_path, records,
                                  "cims_work_items", "item_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "item_not_found"}

    def record_assignment(
        self, assignment_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("assignment_id", "agent_id", "item_id"):
            if f not in assignment_data or not assignment_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        records = self._load(self.assignments_path,
                                "cims_assignments", ("assignment_id",))
        if any(r.get("assignment_id") == assignment_data["assignment_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_assignment_id"}
        record = {
            "assignment_id": assignment_data["assignment_id"],
            "agent_id": assignment_data["agent_id"],
            "item_id": assignment_data["item_id"],
            "narrative": assignment_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.assignments_path, records,
                          "cims_assignments", "assignment_id")
        return {"recorded": ok,
                  "assignment_id": assignment_data["assignment_id"]}

    def record_action(
        self, action_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("action_id", "agent_id", "item_id", "action_kind"):
            if f not in action_data or not action_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if action_data["action_kind"] not in AGENT_ACTION_KINDS:
            return {"recorded": False,
                       "error": f"invalid_action_kind:{action_data['action_kind']}"}
        records = self._load(self.actions_path,
                                "cims_agent_actions", ("action_id",))
        if any(r.get("action_id") == action_data["action_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_action_id"}
        record = {
            "action_id": action_data["action_id"],
            "agent_id": action_data["agent_id"],
            "item_id": action_data["item_id"],
            "action_kind": action_data["action_kind"],
            "narrative": action_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.actions_path, records,
                          "cims_agent_actions", "action_id")
        return {"recorded": ok, "action_id": action_data["action_id"]}

    def queue_summary(self) -> Dict[str, Any]:
        items = self._load(self.items_path,
                              "cims_work_items", ("item_id",))
        per_state: Dict[str, int] = {}
        per_priority: Dict[str, int] = {}
        per_source: Dict[str, int] = {}
        for it in items:
            per_state[it.get("state", "")] = (
                per_state.get(it.get("state", ""), 0) + 1
            )
            per_priority[it.get("priority", "")] = (
                per_priority.get(it.get("priority", ""), 0) + 1
            )
            per_source[it.get("source", "")] = (
                per_source.get(it.get("source", ""), 0) + 1
            )
        queued = per_state.get("QUEUED", 0)
        return {
            "total_items": len(items),
            "per_state": per_state,
            "per_priority": per_priority,
            "per_source": per_source,
            "queue_depth": queued,
            "queue_depth_threshold": DEFAULT_QUEUE_DEPTH_THRESHOLD,
            "exceeds_threshold": queued > DEFAULT_QUEUE_DEPTH_THRESHOLD,
        }

    def workload_by_agent(self) -> Dict[str, Dict[str, int]]:
        actions = self._load(self.actions_path,
                                "cims_agent_actions", ("action_id",))
        per_agent: Dict[str, Dict[str, int]] = {}
        for a in actions:
            aid = a.get("agent_id", "")
            kind = a.get("action_kind", "")
            per_agent.setdefault(aid, {})
            per_agent[aid][kind] = per_agent[aid].get(kind, 0) + 1
        return per_agent


def _self_test() -> None:
    import tempfile

    assert AGENT_STATES == (
        "AVAILABLE", "ASSIGNED", "ON_BREAK",
        "OFFLINE", "ARCHIVED",
    )
    assert ALLOWED_AGENT_TRANSITIONS["ARCHIVED"] == ()
    assert WORK_ITEM_STATES == (
        "QUEUED", "ASSIGNED", "IN_PROGRESS",
        "ON_HOLD", "COMPLETED", "CANCELLED",
    )
    assert ALLOWED_ITEM_TRANSITIONS["COMPLETED"] == ()
    assert ALLOWED_ITEM_TRANSITIONS["CANCELLED"] == ()
    assert WORK_ITEM_PRIORITIES == ("URGENT", "HIGH", "NORMAL", "LOW")
    assert WORK_ITEM_SOURCES == (
        "CAPTURE_HANDOFF", "EXCEPTION_RAISED",
        "SLA_APPROACHING", "DROPOUT_INTERVENTION",
        "MANUAL_ESCALATION",
    )
    assert AGENT_ACTION_KINDS == (
        "ITEM_CLAIMED", "ITEM_RELEASED", "NOTE_ADDED",
        "CUSTOMER_CONTACTED", "DOCUMENT_REVIEWED",
        "AI_SUGGESTION_ACCEPTED", "AI_SUGGESTION_REJECTED",
        "ITEM_RESOLVED",
    )
    assert AGENT_SKILL_TAGS == (
        "KYC_REVIEW", "COMPLAINT_HANDLING",
        "DISPUTE_RESOLUTION", "LOAN_PROCESSING", "GENERAL",
    )
    assert DEFAULT_QUEUE_REASSIGNMENT_HOURS == 4
    assert DEFAULT_AGENT_BREAK_LIMIT_MINUTES == 60
    assert DEFAULT_QUEUE_DEPTH_THRESHOLD == 50

    with tempfile.TemporaryDirectory() as tmpdir:
        e = AgentWorkspaceEngine(
            agents_path=Path(tmpdir) / "a.json",
            items_path=Path(tmpdir) / "i.json",
            assignments_path=Path(tmpdir) / "s.json",
            actions_path=Path(tmpdir) / "ac.json",
        )

        # Agent
        r = e.register_agent(
            {"agent_id": "AGT-001",
             "name": "Jane Mwangi",
             "skill_tags": ["KYC_REVIEW", "COMPLAINT_HANDLING"]},
            actor="ops", reason="hired",
        )
        assert r["registered"]
        # Bad skill
        r = e.register_agent(
            {"agent_id": "X", "name": "Y",
             "skill_tags": ["WHATEVER"]},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Empty skills
        r = e.register_agent(
            {"agent_id": "Z", "name": "Y", "skill_tags": []},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Agent lifecycle
        r = e.transition_agent_state(
            "AGT-001", "ASSIGNED",
            actor="ops", reason="picked up item",
        )
        assert r["transitioned"]
        r = e.transition_agent_state(
            "AGT-001", "ON_BREAK",
            actor="ops", reason="lunch",
        )
        assert r["transitioned"]
        r = e.transition_agent_state(
            "AGT-001", "AVAILABLE",
            actor="ops", reason="back",
        )
        assert r["transitioned"]
        r = e.transition_agent_state(
            "AGT-001", "OFFLINE",
            actor="ops", reason="end of shift",
        )
        assert r["transitioned"]
        # OFFLINE → AVAILABLE | ARCHIVED only
        r = e.transition_agent_state(
            "AGT-001", "ASSIGNED", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Work item
        r = e.enqueue_work_item(
            {"item_id": "ITM-001",
             "linked_session_id": "CAP-001",
             "source": "EXCEPTION_RAISED",
             "priority": "HIGH",
             "narrative": "KYC docs missing",
             "required_skill": "KYC_REVIEW"},
            actor="ops", reason="from exception",
        )
        assert r["enqueued"]
        # Bad source
        r = e.enqueue_work_item(
            {"item_id": "X", "linked_session_id": "Y",
             "source": "WHATEVER", "priority": "HIGH",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["enqueued"]
        # Bad priority
        r = e.enqueue_work_item(
            {"item_id": "Z", "linked_session_id": "Y",
             "source": "EXCEPTION_RAISED",
             "priority": "WHATEVER",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["enqueued"]
        # Bad required skill
        r = e.enqueue_work_item(
            {"item_id": "W", "linked_session_id": "Y",
             "source": "EXCEPTION_RAISED",
             "priority": "HIGH",
             "narrative": "n",
             "required_skill": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["enqueued"]

        # Item lifecycle
        r = e.transition_item_state(
            "ITM-001", "ASSIGNED",
            actor="ops", reason="assigned to Jane",
        )
        assert r["transitioned"]
        r = e.transition_item_state(
            "ITM-001", "IN_PROGRESS",
            actor="ops", reason="started",
        )
        assert r["transitioned"]
        r = e.transition_item_state(
            "ITM-001", "ON_HOLD",
            actor="ops", reason="awaiting customer",
        )
        assert r["transitioned"]
        r = e.transition_item_state(
            "ITM-001", "IN_PROGRESS",
            actor="ops", reason="customer responded",
        )
        assert r["transitioned"]
        r = e.transition_item_state(
            "ITM-001", "COMPLETED",
            actor="ops", reason="resolved",
        )
        assert r["transitioned"]
        # COMPLETED is terminal
        r = e.transition_item_state(
            "ITM-001", "QUEUED", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Assignment
        r = e.record_assignment(
            {"assignment_id": "ASG-001",
             "agent_id": "AGT-001",
             "item_id": "ITM-001"},
            actor="ops",
        )
        assert r["recorded"]

        # Action
        r = e.record_action(
            {"action_id": "ACT-001",
             "agent_id": "AGT-001",
             "item_id": "ITM-001",
             "action_kind": "ITEM_CLAIMED",
             "narrative": "Jane picked up item"},
            actor="ops",
        )
        assert r["recorded"]
        # Bad action kind
        r = e.record_action(
            {"action_id": "X",
             "agent_id": "Y",
             "item_id": "Z",
             "action_kind": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Queue summary
        s = e.queue_summary()
        assert s["total_items"] == 1
        assert s["per_state"]["COMPLETED"] == 1
        assert s["queue_depth_threshold"] == 50

        # Workload
        w = e.workload_by_agent()
        assert "AGT-001" in w
        assert w["AGT-001"]["ITEM_CLAIMED"] == 1

    print("  ✅ cims_agent_workspace self-test PASS")


if __name__ == "__main__":
    _self_test()

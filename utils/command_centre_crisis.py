"""
================================================================================
A2Z MIS 360 — Standard #317: Crisis Playbook + Incident Command
================================================================================

Risk classification: Cat B (incident response coordination + audit trail)

Crisis playbook activation, incident command dashboard, stakeholder
notification, decision log, after-action review.

Public API:
    register_playbook(playbook_data, actor, reason)
    activate_incident(incident_data, playbook_id, actor, reason)
    transition_incident_state(incident_id, new_state, actor, reason)
    record_decision(incident_id, decision_data, actor)
    record_stakeholder_notification(incident_id, notif_data, actor)
    record_after_action_review(incident_id, aar_data, actor, reason)
    incident_status(incident_id) -> Dict
    open_incidents() -> List

INCIDENT_SEVERITIES byte-for-byte (4):
    SEV1  -- bank-wide outage / regulatory crisis
    SEV2  -- major service disruption / large customer impact
    SEV3  -- localized issue / limited impact
    SEV4  -- minor / single-customer issue

INCIDENT_STATES byte-for-byte (6):
    OPEN, IN_RESPONSE, CONTAINED, RESOLVED, IN_REVIEW, ARCHIVED

ALLOWED_INCIDENT_TRANSITIONS (Rule 4):
    OPEN        → IN_RESPONSE | RESOLVED | ARCHIVED
    IN_RESPONSE → CONTAINED | RESOLVED | ARCHIVED
    CONTAINED   → RESOLVED | ARCHIVED
    RESOLVED    → IN_REVIEW | ARCHIVED
    IN_REVIEW   → ARCHIVED
    ARCHIVED    → ()

PLAYBOOK_TYPES byte-for-byte (8):
    SYSTEM_OUTAGE, SECURITY_BREACH, REGULATORY_INVESTIGATION,
    LIQUIDITY_STRESS, FRAUD_INCIDENT, CUSTOMER_DATA_LEAK,
    OPERATIONAL_INCIDENT, REPUTATIONAL_CRISIS

DECISION_TYPES byte-for-byte (5):
    CONTAINMENT, COMMUNICATION, ESCALATION, RESOURCE_ALLOCATION, RECOVERY

STAKEHOLDER_TYPES byte-for-byte (6):
    REGULATOR, BOARD, CUSTOMERS, MEDIA, EMPLOYEES, AUDITOR

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


INCIDENT_SEVERITIES: Tuple[str, ...] = ("SEV1", "SEV2", "SEV3", "SEV4")

INCIDENT_STATES: Tuple[str, ...] = (
    "OPEN", "IN_RESPONSE", "CONTAINED", "RESOLVED", "IN_REVIEW", "ARCHIVED",
)

ALLOWED_INCIDENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":        ("IN_RESPONSE", "RESOLVED", "ARCHIVED"),
    "IN_RESPONSE": ("CONTAINED", "RESOLVED", "ARCHIVED"),
    "CONTAINED":   ("RESOLVED", "ARCHIVED"),
    "RESOLVED":    ("IN_REVIEW", "ARCHIVED"),
    "IN_REVIEW":   ("ARCHIVED",),
    "ARCHIVED":    (),
}

PLAYBOOK_TYPES: Tuple[str, ...] = (
    "SYSTEM_OUTAGE", "SECURITY_BREACH", "REGULATORY_INVESTIGATION",
    "LIQUIDITY_STRESS", "FRAUD_INCIDENT", "CUSTOMER_DATA_LEAK",
    "OPERATIONAL_INCIDENT", "REPUTATIONAL_CRISIS",
)

DECISION_TYPES: Tuple[str, ...] = (
    "CONTAINMENT", "COMMUNICATION", "ESCALATION",
    "RESOURCE_ALLOCATION", "RECOVERY",
)

STAKEHOLDER_TYPES: Tuple[str, ...] = (
    "REGULATOR", "BOARD", "CUSTOMERS", "MEDIA", "EMPLOYEES", "AUDITOR",
)


class CommandCentreCrisisEngine:
    """Crisis playbook activation + incident command + decision log + AAR."""

    def __init__(
        self,
        playbooks_path: Optional[Path] = None,
        incidents_path: Optional[Path] = None,
        decisions_path: Optional[Path] = None,
        notifications_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.playbooks_path = playbooks_path or base / "crisis_playbooks.json"
        self.incidents_path = incidents_path or base / "crisis_incidents.json"
        self.decisions_path = decisions_path or base / "crisis_decisions.json"
        self.notifications_path = notifications_path or base / "crisis_notifications.json"

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

    def register_playbook(
        self, playbook_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("playbook_id", "playbook_name", "playbook_type"):
            if f not in playbook_data or not playbook_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if playbook_data["playbook_type"] not in PLAYBOOK_TYPES:
            return {"registered": False,
                       "error": f"invalid_playbook_type:{playbook_data['playbook_type']}"}
        records = self._load(self.playbooks_path,
                                "crisis_playbooks", ("playbook_id",))
        if any(r.get("playbook_id") == playbook_data["playbook_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_playbook_id"}
        record = {
            "playbook_id": playbook_data["playbook_id"],
            "playbook_name": playbook_data["playbook_name"],
            "playbook_type": playbook_data["playbook_type"],
            "trigger_criteria": playbook_data.get("trigger_criteria", []),
            "incident_commander_role": playbook_data.get(
                "incident_commander_role", "COO",
            ),
            "response_steps": playbook_data.get("response_steps", []),
            "stakeholder_notification_targets": playbook_data.get(
                "stakeholder_notification_targets", [],
            ),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.playbooks_path, records,
                          "crisis_playbooks", "playbook_id")
        return {"registered": ok, "playbook_id": playbook_data["playbook_id"]}

    def activate_incident(
        self, incident_data: Dict[str, Any], playbook_id: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"activated": False, "error": "actor_and_reason_required"}
        for f in ("incident_id", "title", "severity"):
            if f not in incident_data or not incident_data[f]:
                return {"activated": False, "error": f"missing_field:{f}"}
        if incident_data["severity"] not in INCIDENT_SEVERITIES:
            return {"activated": False,
                       "error": f"invalid_severity:{incident_data['severity']}"}

        # Verify playbook exists
        playbooks = self._load(self.playbooks_path,
                                     "crisis_playbooks", ("playbook_id",))
        playbook = next((p for p in playbooks
                              if p.get("playbook_id") == playbook_id), None)
        if playbook is None:
            return {"activated": False, "error": "playbook_not_found"}

        records = self._load(self.incidents_path,
                                "crisis_incidents", ("incident_id",))
        if any(r.get("incident_id") == incident_data["incident_id"]
                 for r in records):
            return {"activated": False, "error": "duplicate_incident_id"}

        record = {
            "incident_id": incident_data["incident_id"],
            "title": incident_data["title"],
            "description": incident_data.get("description", ""),
            "severity": incident_data["severity"],
            "playbook_id": playbook_id,
            "playbook_name": playbook["playbook_name"],
            "playbook_type": playbook["playbook_type"],
            "incident_commander": incident_data.get(
                "incident_commander", playbook.get("incident_commander_role"),
            ),
            "state": "OPEN",
            "activated_by": actor,
            "activated_at": datetime.utcnow().isoformat(),
            "activation_reason": reason,
            "transitions": [{
                "to": "OPEN", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
            "after_action_review": None,
        }
        records.append(record)
        ok = self._save(self.incidents_path, records,
                          "crisis_incidents", "incident_id")
        return {"activated": ok, "incident_id": incident_data["incident_id"]}

    def transition_incident_state(
        self, incident_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in INCIDENT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.incidents_path,
                                "crisis_incidents", ("incident_id",))
        for r in records:
            if r.get("incident_id") == incident_id:
                current = r.get("state", "OPEN")
                allowed = ALLOWED_INCIDENT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.incidents_path, records,
                                  "crisis_incidents", "incident_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "incident_not_found"}

    def record_decision(
        self, incident_id: str, decision_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("decision_id", "decision_type", "decision_text"):
            if f not in decision_data or not decision_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if decision_data["decision_type"] not in DECISION_TYPES:
            return {"recorded": False,
                       "error": f"invalid_decision_type:{decision_data['decision_type']}"}
        # Verify incident is active (not ARCHIVED)
        incidents = self._load(self.incidents_path,
                                     "crisis_incidents", ("incident_id",))
        incident = next((i for i in incidents
                              if i.get("incident_id") == incident_id), None)
        if incident is None:
            return {"recorded": False, "error": "incident_not_found"}
        if incident["state"] == "ARCHIVED":
            return {"recorded": False, "error": "incident_archived"}

        decisions = self._load(self.decisions_path,
                                     "crisis_decisions", ("decision_id",))
        if any(d.get("decision_id") == decision_data["decision_id"]
                 for d in decisions):
            return {"recorded": False, "error": "duplicate_decision_id"}

        record = {
            "decision_id": decision_data["decision_id"],
            "incident_id": incident_id,
            "decision_type": decision_data["decision_type"],
            "decision_text": decision_data["decision_text"],
            "rationale": decision_data.get("rationale", ""),
            "decided_by": decision_data.get("decided_by", actor),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        decisions.append(record)
        ok = self._save(self.decisions_path, decisions,
                          "crisis_decisions", "decision_id")
        return {"recorded": ok, "decision_id": decision_data["decision_id"]}

    def record_stakeholder_notification(
        self, incident_id: str, notif_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("notification_id", "stakeholder_type", "message"):
            if f not in notif_data or not notif_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if notif_data["stakeholder_type"] not in STAKEHOLDER_TYPES:
            return {"recorded": False,
                       "error": f"invalid_stakeholder_type:{notif_data['stakeholder_type']}"}
        notifications = self._load(self.notifications_path,
                                            "crisis_notifications",
                                            ("notification_id",))
        if any(n.get("notification_id") == notif_data["notification_id"]
                 for n in notifications):
            return {"recorded": False, "error": "duplicate_notification_id"}
        record = {
            "notification_id": notif_data["notification_id"],
            "incident_id": incident_id,
            "stakeholder_type": notif_data["stakeholder_type"],
            "channel": notif_data.get("channel", "EMAIL"),
            "message": notif_data["message"],
            "sent_by": actor,
            "sent_at": datetime.utcnow().isoformat(),
        }
        notifications.append(record)
        ok = self._save(self.notifications_path, notifications,
                          "crisis_notifications", "notification_id")
        return {"recorded": ok,
                  "notification_id": notif_data["notification_id"]}

    def record_after_action_review(
        self, incident_id: str, aar_data: Dict[str, Any],
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"recorded": False, "error": "actor_and_reason_required"}
        for f in ("summary", "lessons_learned", "improvements"):
            if f not in aar_data or not aar_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        records = self._load(self.incidents_path,
                                "crisis_incidents", ("incident_id",))
        for r in records:
            if r.get("incident_id") == incident_id:
                if r["state"] not in ("RESOLVED", "IN_REVIEW"):
                    return {"recorded": False,
                               "error": f"AAR_requires_resolved_or_in_review:{r['state']}"}
                r["after_action_review"] = {
                    "summary": aar_data["summary"],
                    "lessons_learned": aar_data["lessons_learned"],
                    "improvements": aar_data["improvements"],
                    "completion_time_minutes": aar_data.get(
                        "completion_time_minutes",
                    ),
                    "submitted_by": actor,
                    "submitted_at": datetime.utcnow().isoformat(),
                    "reason": reason,
                }
                ok = self._save(self.incidents_path, records,
                                  "crisis_incidents", "incident_id")
                return {"recorded": ok}
        return {"recorded": False, "error": "incident_not_found"}

    def incident_status(self, incident_id: str) -> Dict[str, Any]:
        records = self._load(self.incidents_path,
                                "crisis_incidents", ("incident_id",))
        incident = next((r for r in records
                              if r.get("incident_id") == incident_id), None)
        if incident is None:
            return {"found": False, "error": "incident_not_found"}

        decisions = [d for d in self._load(self.decisions_path,
                                                  "crisis_decisions",
                                                  ("decision_id",))
                          if d.get("incident_id") == incident_id]
        notifications = [n for n in self._load(self.notifications_path,
                                                       "crisis_notifications",
                                                       ("notification_id",))
                              if n.get("incident_id") == incident_id]
        return {
            "found": True,
            "incident_id": incident_id,
            "title": incident["title"],
            "severity": incident["severity"],
            "state": incident["state"],
            "playbook_id": incident["playbook_id"],
            "incident_commander": incident.get("incident_commander"),
            "transitions": incident.get("transitions", []),
            "decision_count": len(decisions),
            "decisions": decisions,
            "notification_count": len(notifications),
            "notifications": notifications,
            "after_action_review": incident.get("after_action_review"),
        }

    def open_incidents(self) -> List[Dict[str, Any]]:
        records = self._load(self.incidents_path,
                                "crisis_incidents", ("incident_id",))
        return [r for r in records
                  if r.get("state") in ("OPEN", "IN_RESPONSE", "CONTAINED")]


def _self_test() -> None:
    import tempfile

    assert "SEV1" in INCIDENT_SEVERITIES
    assert ALLOWED_INCIDENT_TRANSITIONS["ARCHIVED"] == ()
    assert "SYSTEM_OUTAGE" in PLAYBOOK_TYPES
    assert "CONTAINMENT" in DECISION_TYPES
    assert "REGULATOR" in STAKEHOLDER_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreCrisisEngine(
            playbooks_path=Path(tmpdir) / "p.json",
            incidents_path=Path(tmpdir) / "i.json",
            decisions_path=Path(tmpdir) / "d.json",
            notifications_path=Path(tmpdir) / "n.json",
        )
        # Test 1: register playbook
        r = engine.register_playbook(
            {"playbook_id": "PB-OUTAGE",
             "playbook_name": "Core Banking Outage",
             "playbook_type": "SYSTEM_OUTAGE",
             "incident_commander_role": "COO",
             "response_steps": ["Isolate", "Failover", "Communicate"],
             "stakeholder_notification_targets": ["REGULATOR", "CUSTOMERS"]},
            actor="cro", reason="prepare for outage scenarios",
        )
        assert r["registered"]
        # Test 2: invalid playbook type
        r = engine.register_playbook(
            {"playbook_id": "X", "playbook_name": "Y",
             "playbook_type": "INVALID"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: activate incident
        r = engine.activate_incident(
            {"incident_id": "INC-001",
             "title": "FLEXCUBE Down",
             "description": "Core down",
             "severity": "SEV1"},
            "PB-OUTAGE", actor="coo", reason="outage detected",
        )
        assert r["activated"]
        # Test 4: invalid playbook
        r = engine.activate_incident(
            {"incident_id": "INC-Y", "title": "Y", "severity": "SEV1"},
            "INVALID", actor="x", reason="x",
        )
        assert not r["activated"]
        # Test 5: transitions
        r = engine.transition_incident_state(
            "INC-001", "IN_RESPONSE", actor="coo", reason="responding",
        )
        assert r["transitioned"]
        # Test 6: invalid transition
        r = engine.transition_incident_state(
            "INC-001", "ARCHIVED", actor="coo", reason="x",
        )
        assert r["transitioned"]  # IN_RESPONSE → ARCHIVED is allowed
        # Test 7: cannot record decision on archived
        r = engine.record_decision(
            "INC-001",
            {"decision_id": "DEC-1", "decision_type": "CONTAINMENT",
             "decision_text": "Activate failover"},
            actor="coo",
        )
        assert not r["recorded"]
        # Test 8: new incident, full lifecycle
        r = engine.activate_incident(
            {"incident_id": "INC-002", "title": "Breach", "severity": "SEV2"},
            "PB-OUTAGE", actor="cro", reason="breach detected",
        )
        assert r["activated"]
        r = engine.transition_incident_state(
            "INC-002", "IN_RESPONSE", actor="cro", reason="r",
        )
        # Test 9: record decision
        r = engine.record_decision(
            "INC-002",
            {"decision_id": "DEC-2", "decision_type": "ESCALATION",
             "decision_text": "Notify regulator", "rationale": "SEV2 mandates"},
            actor="cro",
        )
        assert r["recorded"]
        # Test 10: invalid decision type
        r = engine.record_decision(
            "INC-002",
            {"decision_id": "DEC-X", "decision_type": "INVALID",
             "decision_text": "x"},
            actor="x",
        )
        assert not r["recorded"]
        # Test 11: stakeholder notification
        r = engine.record_stakeholder_notification(
            "INC-002",
            {"notification_id": "N-1", "stakeholder_type": "REGULATOR",
             "message": "Notifying CBK of breach"},
            actor="cro",
        )
        assert r["recorded"]
        # Test 12: AAR requires RESOLVED/IN_REVIEW
        r = engine.record_after_action_review(
            "INC-002",
            {"summary": "x", "lessons_learned": "y", "improvements": "z"},
            actor="cro", reason="early",
        )
        assert not r["recorded"]
        # Test 13: resolve and AAR
        engine.transition_incident_state(
            "INC-002", "CONTAINED", actor="cro", reason="contained",
        )
        engine.transition_incident_state(
            "INC-002", "RESOLVED", actor="cro", reason="resolved",
        )
        r = engine.record_after_action_review(
            "INC-002",
            {"summary": "Breach contained",
             "lessons_learned": "Detection was slow",
             "improvements": "Add anomaly detection"},
            actor="cro", reason="AAR complete",
        )
        assert r["recorded"]
        # Test 14: incident status
        s = engine.incident_status("INC-002")
        assert s["found"]
        assert s["decision_count"] >= 1
        assert s["after_action_review"] is not None
        # Test 15: open incidents
        opens = engine.open_incidents()
        # INC-001 archived, INC-002 RESOLVED — neither open
        assert all(i["incident_id"] != "INC-001" for i in opens)
        assert all(i["incident_id"] != "INC-002" for i in opens)

    print("  ✅ command_centre_crisis self-test PASS")


if __name__ == "__main__":
    _self_test()

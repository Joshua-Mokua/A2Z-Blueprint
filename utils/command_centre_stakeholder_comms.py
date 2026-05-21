"""
================================================================================
A2Z MIS 360 — Standard #319: Stakeholder Communications
================================================================================

Risk classification: Cat C (templated communications + audit trail)

Centralized stakeholder communication: regulators, auditors, board members,
customers. Templated comms, audit trail, response tracking.

Public API:
    register_template(template_data, actor, reason)
    transition_template_state(template_id, new_state, actor, reason)
    send_communication(comm_data, actor)
    record_response(comm_id, response_data, actor)
    transition_comm_state(comm_id, new_state, actor, reason)
    list_outstanding(stakeholder_type=None) -> List
    comm_status(comm_id) -> Dict

STAKEHOLDER_COMM_TYPES byte-for-byte (6):
    REGULATOR, AUDITOR, BOARD, CUSTOMER, MEDIA, EMPLOYEE

COMM_CHANNELS byte-for-byte (5):
    EMAIL, LETTER, PHONE_CALL, MEETING, PORTAL_MESSAGE

COMM_STATES byte-for-byte (5):
    DRAFT, SENT, ACKNOWLEDGED, RESOLVED, ARCHIVED

ALLOWED_COMM_TRANSITIONS (Rule 4):
    DRAFT        → SENT | ARCHIVED
    SENT         → ACKNOWLEDGED | RESOLVED | ARCHIVED
    ACKNOWLEDGED → RESOLVED | ARCHIVED
    RESOLVED     → ARCHIVED
    ARCHIVED     → ()

TEMPLATE_STATES byte-for-byte (3): ACTIVE, DEPRECATED, ARCHIVED

ALLOWED_TEMPLATE_TRANSITIONS (Rule 4):
    ACTIVE     → DEPRECATED | ARCHIVED
    DEPRECATED → ACTIVE | ARCHIVED
    ARCHIVED   → ()

RESPONSE_OUTCOMES byte-for-byte (5):
    ACKNOWLEDGED, ACCEPTED, REJECTED, REQUEST_INFO, NO_RESPONSE

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


STAKEHOLDER_COMM_TYPES: Tuple[str, ...] = (
    "REGULATOR", "AUDITOR", "BOARD", "CUSTOMER", "MEDIA", "EMPLOYEE",
)

COMM_CHANNELS: Tuple[str, ...] = (
    "EMAIL", "LETTER", "PHONE_CALL", "MEETING", "PORTAL_MESSAGE",
)

COMM_STATES: Tuple[str, ...] = (
    "DRAFT", "SENT", "ACKNOWLEDGED", "RESOLVED", "ARCHIVED",
)

ALLOWED_COMM_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":        ("SENT", "ARCHIVED"),
    "SENT":         ("ACKNOWLEDGED", "RESOLVED", "ARCHIVED"),
    "ACKNOWLEDGED": ("RESOLVED", "ARCHIVED"),
    "RESOLVED":     ("ARCHIVED",),
    "ARCHIVED":     (),
}

TEMPLATE_STATES: Tuple[str, ...] = ("ACTIVE", "DEPRECATED", "ARCHIVED")

ALLOWED_TEMPLATE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":     ("DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ACTIVE", "ARCHIVED"),
    "ARCHIVED":   (),
}

RESPONSE_OUTCOMES: Tuple[str, ...] = (
    "ACKNOWLEDGED", "ACCEPTED", "REJECTED", "REQUEST_INFO", "NO_RESPONSE",
)


class CommandCentreStakeholderCommsEngine:
    """Stakeholder communications with template registry + state machine."""

    def __init__(
        self,
        templates_path: Optional[Path] = None,
        comms_path: Optional[Path] = None,
        responses_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.templates_path = templates_path or base / "stakeholder_templates.json"
        self.comms_path = comms_path or base / "stakeholder_comms.json"
        self.responses_path = responses_path or base / "stakeholder_responses.json"

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

    def register_template(
        self, template_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("template_id", "template_name", "stakeholder_type",
                      "subject_template", "body_template"):
            if f not in template_data or not template_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if template_data["stakeholder_type"] not in STAKEHOLDER_COMM_TYPES:
            return {"registered": False,
                       "error": f"invalid_stakeholder_type:{template_data['stakeholder_type']}"}
        records = self._load(self.templates_path,
                                "stakeholder_templates", ("template_id",))
        if any(r.get("template_id") == template_data["template_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_template_id"}
        record = {
            "template_id": template_data["template_id"],
            "template_name": template_data["template_name"],
            "stakeholder_type": template_data["stakeholder_type"],
            "subject_template": template_data["subject_template"],
            "body_template": template_data["body_template"],
            "default_channel": template_data.get("default_channel", "EMAIL"),
            "approval_required": template_data.get("approval_required", False),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.templates_path, records,
                          "stakeholder_templates", "template_id")
        return {"registered": ok, "template_id": template_data["template_id"]}

    def transition_template_state(
        self, template_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in TEMPLATE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.templates_path,
                                "stakeholder_templates", ("template_id",))
        for r in records:
            if r.get("template_id") == template_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_TEMPLATE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                ok = self._save(self.templates_path, records,
                                  "stakeholder_templates", "template_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "template_not_found"}

    def send_communication(
        self, comm_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"sent": False, "error": "actor_required"}
        for f in ("comm_id", "stakeholder_type", "subject", "body",
                      "channel"):
            if f not in comm_data or not comm_data[f]:
                return {"sent": False, "error": f"missing_field:{f}"}
        if comm_data["stakeholder_type"] not in STAKEHOLDER_COMM_TYPES:
            return {"sent": False,
                       "error": f"invalid_stakeholder_type:{comm_data['stakeholder_type']}"}
        if comm_data["channel"] not in COMM_CHANNELS:
            return {"sent": False,
                       "error": f"invalid_channel:{comm_data['channel']}"}

        records = self._load(self.comms_path, "stakeholder_comms",
                                ("comm_id",))
        if any(r.get("comm_id") == comm_data["comm_id"] for r in records):
            return {"sent": False, "error": "duplicate_comm_id"}

        record = {
            "comm_id": comm_data["comm_id"],
            "stakeholder_type": comm_data["stakeholder_type"],
            "stakeholder_id": comm_data.get("stakeholder_id", ""),
            "subject": comm_data["subject"],
            "body": comm_data["body"],
            "channel": comm_data["channel"],
            "template_id": comm_data.get("template_id"),
            "sent_by": actor,
            "sent_at": datetime.utcnow().isoformat(),
            "state": "SENT",
            "transitions": [{
                "to": "SENT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.comms_path, records,
                          "stakeholder_comms", "comm_id")
        return {"sent": ok, "comm_id": comm_data["comm_id"]}

    def record_response(
        self, comm_id: str, response_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("response_id", "outcome", "received_at"):
            if f not in response_data or not response_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if response_data["outcome"] not in RESPONSE_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{response_data['outcome']}"}
        # Verify comm exists + is in SENT or ACKNOWLEDGED state
        comms = self._load(self.comms_path, "stakeholder_comms",
                              ("comm_id",))
        comm = next((c for c in comms
                          if c.get("comm_id") == comm_id), None)
        if comm is None:
            return {"recorded": False, "error": "comm_not_found"}
        if comm["state"] not in ("SENT", "ACKNOWLEDGED"):
            return {"recorded": False,
                       "error": f"comm_not_open_for_response:{comm['state']}"}

        responses = self._load(self.responses_path,
                                     "stakeholder_responses", ("response_id",))
        if any(r.get("response_id") == response_data["response_id"]
                 for r in responses):
            return {"recorded": False, "error": "duplicate_response_id"}

        record = {
            "response_id": response_data["response_id"],
            "comm_id": comm_id,
            "outcome": response_data["outcome"],
            "response_text": response_data.get("response_text", ""),
            "received_at": response_data["received_at"],
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        responses.append(record)
        self._save(self.responses_path, responses,
                     "stakeholder_responses", "response_id")

        # Auto-transition comm to ACKNOWLEDGED if SENT
        if comm["state"] == "SENT":
            for c in comms:
                if c["comm_id"] == comm_id:
                    c["state"] = "ACKNOWLEDGED"
                    c.setdefault("transitions", []).append({
                        "to": "ACKNOWLEDGED", "actor": actor,
                        "at": datetime.utcnow().isoformat(),
                        "reason": "response_received",
                    })
                    break
            self._save(self.comms_path, comms,
                          "stakeholder_comms", "comm_id")

        return {"recorded": True,
                  "response_id": response_data["response_id"]}

    def transition_comm_state(
        self, comm_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in COMM_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.comms_path, "stakeholder_comms",
                                ("comm_id",))
        for r in records:
            if r.get("comm_id") == comm_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_COMM_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.comms_path, records,
                                  "stakeholder_comms", "comm_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "comm_not_found"}

    def list_outstanding(
        self, stakeholder_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.comms_path, "stakeholder_comms",
                                ("comm_id",))
        outstanding = [r for r in records
                            if r.get("state") in ("SENT", "ACKNOWLEDGED")]
        if stakeholder_type:
            outstanding = [r for r in outstanding
                                if r.get("stakeholder_type") == stakeholder_type]
        outstanding.sort(key=lambda x: x.get("sent_at", ""))
        return outstanding

    def comm_status(self, comm_id: str) -> Dict[str, Any]:
        records = self._load(self.comms_path, "stakeholder_comms",
                                ("comm_id",))
        comm = next((r for r in records
                          if r.get("comm_id") == comm_id), None)
        if comm is None:
            return {"found": False, "error": "comm_not_found"}
        responses = [r for r in self._load(self.responses_path,
                                                  "stakeholder_responses",
                                                  ("response_id",))
                          if r.get("comm_id") == comm_id]
        return {
            "found": True,
            "comm_id": comm_id,
            "stakeholder_type": comm["stakeholder_type"],
            "subject": comm["subject"],
            "state": comm["state"],
            "channel": comm["channel"],
            "sent_at": comm["sent_at"],
            "transitions": comm.get("transitions", []),
            "response_count": len(responses),
            "responses": responses,
        }


def _self_test() -> None:
    import tempfile

    assert "REGULATOR" in STAKEHOLDER_COMM_TYPES
    assert "EMAIL" in COMM_CHANNELS
    assert ALLOWED_COMM_TRANSITIONS["ARCHIVED"] == ()
    assert ALLOWED_TEMPLATE_TRANSITIONS["ARCHIVED"] == ()
    assert "ACKNOWLEDGED" in RESPONSE_OUTCOMES

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreStakeholderCommsEngine(
            templates_path=Path(tmpdir) / "t.json",
            comms_path=Path(tmpdir) / "c.json",
            responses_path=Path(tmpdir) / "r.json",
        )
        # Test 1: register template
        r = engine.register_template(
            {"template_id": "TPL-CBK-RESP",
             "template_name": "CBK enquiry response",
             "stakeholder_type": "REGULATOR",
             "subject_template": "Re: CBK enquiry {ref}",
             "body_template": "Dear CBK officer, Re: {ref}, ..."},
            actor="legal", reason="standard CBK response",
        )
        assert r["registered"]
        # Test 2: invalid stakeholder type
        r = engine.register_template(
            {"template_id": "X", "template_name": "Y",
             "stakeholder_type": "INVALID",
             "subject_template": "X", "body_template": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: send comm
        r = engine.send_communication(
            {"comm_id": "COMM-001",
             "stakeholder_type": "REGULATOR",
             "stakeholder_id": "CBK",
             "subject": "Re: CBK enquiry 2026/Q1",
             "body": "Dear CBK officer...",
             "channel": "LETTER",
             "template_id": "TPL-CBK-RESP"},
            actor="legal",
        )
        assert r["sent"]
        # Test 4: invalid channel
        r = engine.send_communication(
            {"comm_id": "X", "stakeholder_type": "REGULATOR",
             "subject": "Y", "body": "Z", "channel": "TELEGRAPH"},
            actor="x",
        )
        assert not r["sent"]
        # Test 5: invalid stakeholder type
        r = engine.send_communication(
            {"comm_id": "Y", "stakeholder_type": "INVALID",
             "subject": "Y", "body": "Z", "channel": "EMAIL"},
            actor="x",
        )
        assert not r["sent"]
        # Test 6: record response
        r = engine.record_response(
            "COMM-001",
            {"response_id": "RESP-001", "outcome": "ACKNOWLEDGED",
             "received_at": datetime.utcnow().isoformat(),
             "response_text": "Acknowledged, will review"},
            actor="legal",
        )
        assert r["recorded"]
        # Test 7: comm should auto-transition to ACKNOWLEDGED
        s = engine.comm_status("COMM-001")
        assert s["state"] == "ACKNOWLEDGED"
        # Test 8: invalid response outcome
        r = engine.record_response(
            "COMM-001",
            {"response_id": "RESP-X", "outcome": "MAYBE",
             "received_at": datetime.utcnow().isoformat()},
            actor="legal",
        )
        assert not r["recorded"]
        # Test 9: transition comm to RESOLVED
        r = engine.transition_comm_state(
            "COMM-001", "RESOLVED",
            actor="legal", reason="matter closed",
        )
        assert r["transitioned"]
        # Test 10: cannot record response on RESOLVED
        r = engine.record_response(
            "COMM-001",
            {"response_id": "RESP-Z", "outcome": "ACCEPTED",
             "received_at": datetime.utcnow().isoformat()},
            actor="x",
        )
        assert not r["recorded"]
        # Test 11: list outstanding
        engine.send_communication(
            {"comm_id": "COMM-002", "stakeholder_type": "AUDITOR",
             "subject": "Y", "body": "Z", "channel": "EMAIL"},
            actor="legal",
        )
        outstanding = engine.list_outstanding()
        # COMM-001 is RESOLVED, COMM-002 is SENT
        assert all(c["comm_id"] != "COMM-001" for c in outstanding)
        assert any(c["comm_id"] == "COMM-002" for c in outstanding)
        # Test 12: filter by stakeholder type
        outstanding = engine.list_outstanding(stakeholder_type="AUDITOR")
        assert all(c["stakeholder_type"] == "AUDITOR" for c in outstanding)
        # Test 13: template state transitions
        r = engine.transition_template_state(
            "TPL-CBK-RESP", "DEPRECATED",
            actor="legal", reason="superseded",
        )
        assert r["transitioned"]
        r = engine.transition_template_state(
            "TPL-CBK-RESP", "ACTIVE",
            actor="legal", reason="restored",
        )
        assert r["transitioned"]
        # Test 14: ARCHIVED → no transitions
        engine.transition_template_state(
            "TPL-CBK-RESP", "ARCHIVED",
            actor="legal", reason="archive",
        )
        r = engine.transition_template_state(
            "TPL-CBK-RESP", "ACTIVE",
            actor="legal", reason="x",
        )
        assert not r["transitioned"]

    print("  ✅ command_centre_stakeholder_comms self-test PASS")


if __name__ == "__main__":
    _self_test()

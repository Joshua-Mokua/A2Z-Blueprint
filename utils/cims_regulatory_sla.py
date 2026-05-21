"""
================================================================================
A2Z MIS 360 — Standard #171: Regulatory SLA Enforcement Engine
================================================================================

Risk classification: Cat C (read-side SLA tracking + breach reporting;
never auto-resolves regulatory deadlines — surfaces for action only).

Subcategory: cims

Automated SLA tracking aligned with Reg E (Electronic Fund Transfer),
Reg Z (Truth in Lending), and CBK Banking Act requirements. Composes
upstream capture (#166), STP (#168), and exception management (#175)
— surfaces breaches against per-instruction-type regulatory deadlines.

Public API:
    register_sla_definition(definition_data, actor, reason)
    transition_definition_state(definition_id, new_state, actor, reason)
    register_sla_obligation(obligation_data, actor, reason)
    record_obligation_event(event_data, actor)
    breach_report(days=30) -> Dict
    upcoming_deadlines(within_hours=24) -> List

REGULATORY_FRAMEWORKS byte-for-byte (5):
    REG_E, REG_Z, CBK_BANKING_ACT, CBK_PRUDENTIAL, DPA_KENYA_2019

SLA_DEFINITION_STATES byte-for-byte (4):
    DRAFT, ACTIVE, DEPRECATED, ARCHIVED

ALLOWED_DEFINITION_TRANSITIONS (Rule 4):
    DRAFT      → ACTIVE | ARCHIVED
    ACTIVE     → DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

OBLIGATION_STATES byte-for-byte (5):
    PENDING, IN_PROGRESS, FULFILLED, BREACHED, CANCELLED

ALLOWED_OBLIGATION_TRANSITIONS (Rule 4):
    PENDING     → IN_PROGRESS | CANCELLED
    IN_PROGRESS → FULFILLED | BREACHED | CANCELLED
    FULFILLED   → ()
    BREACHED    → ()
    CANCELLED   → ()

OBLIGATION_EVENT_TYPES byte-for-byte (5):
    DEADLINE_REGISTERED, REMINDER_SENT,
    DEADLINE_APPROACHING, DEADLINE_BREACHED, FULFILLED_RECORDED

SLA_BREACH_SEVERITIES byte-for-byte (4):
    LOW, MEDIUM, HIGH, CRITICAL

INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS byte-for-byte (defensible
defaults — Reg E §1005.11 dispute resolution: 10 business days for
provisional credit; CBK customer complaint resolution: 5 business
days; Reg Z §1026.13 billing error: 30 calendar days for response):
    DISPUTE_INVESTIGATION = 240   # 10 business days × 24 hours
    BILLING_ERROR = 720           # 30 calendar days × 24 hours
    CUSTOMER_COMPLAINT = 120      # 5 business days × 24 hours
    GENERAL_INQUIRY = 48
    REGULATORY_REPORTING = 168    # 7 days

DEFAULT_REMINDER_AT_HOURS_REMAINING = 24
DEFAULT_APPROACHING_AT_HOURS_REMAINING = 4

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REGULATORY_FRAMEWORKS: Tuple[str, ...] = (
    "REG_E", "REG_Z", "CBK_BANKING_ACT",
    "CBK_PRUDENTIAL", "DPA_KENYA_2019",
)

SLA_DEFINITION_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED",
)

ALLOWED_DEFINITION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

OBLIGATION_STATES: Tuple[str, ...] = (
    "PENDING", "IN_PROGRESS", "FULFILLED",
    "BREACHED", "CANCELLED",
)

ALLOWED_OBLIGATION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PENDING":     ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("FULFILLED", "BREACHED", "CANCELLED"),
    "FULFILLED":   (),
    "BREACHED":    (),
    "CANCELLED":   (),
}

OBLIGATION_EVENT_TYPES: Tuple[str, ...] = (
    "DEADLINE_REGISTERED", "REMINDER_SENT",
    "DEADLINE_APPROACHING", "DEADLINE_BREACHED",
    "FULFILLED_RECORDED",
)

SLA_BREACH_SEVERITIES: Tuple[str, ...] = (
    "LOW", "MEDIUM", "HIGH", "CRITICAL",
)

INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS: Dict[str, int] = {
    "DISPUTE_INVESTIGATION": 240,
    "BILLING_ERROR": 720,
    "CUSTOMER_COMPLAINT": 120,
    "GENERAL_INQUIRY": 48,
    "REGULATORY_REPORTING": 168,
}

DEFAULT_REMINDER_AT_HOURS_REMAINING = 24
DEFAULT_APPROACHING_AT_HOURS_REMAINING = 4


class RegulatorySLAEngine:
    """SLA definition + obligation + event registry. Read-side breach tracking."""

    def __init__(
        self,
        definitions_path: Optional[Path] = None,
        obligations_path: Optional[Path] = None,
        events_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.definitions_path = (
            definitions_path or base / "cims_sla_definitions.json"
        )
        self.obligations_path = (
            obligations_path or base / "cims_sla_obligations.json"
        )
        self.events_path = (
            events_path or base / "cims_sla_events.json"
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

    def register_sla_definition(
        self, definition_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("definition_id", "name", "framework",
                      "instruction_type", "deadline_hours"):
            if f not in definition_data or definition_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if definition_data["framework"] not in REGULATORY_FRAMEWORKS:
            return {"registered": False,
                       "error": f"invalid_framework:{definition_data['framework']}"}
        try:
            hours = int(definition_data["deadline_hours"])
        except (TypeError, ValueError):
            return {"registered": False, "error": "deadline_hours_not_int"}
        if hours <= 0:
            return {"registered": False, "error": "deadline_hours_must_be_positive"}
        records = self._load(self.definitions_path,
                                "cims_sla_definitions", ("definition_id",))
        if any(r.get("definition_id") == definition_data["definition_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_definition_id"}
        record = {
            "definition_id": definition_data["definition_id"],
            "name": definition_data["name"],
            "framework": definition_data["framework"],
            "instruction_type": definition_data["instruction_type"],
            "deadline_hours": hours,
            "narrative": definition_data.get("narrative", ""),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.definitions_path, records,
                          "cims_sla_definitions", "definition_id")
        return {"registered": ok,
                  "definition_id": definition_data["definition_id"]}

    def transition_definition_state(
        self, definition_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in SLA_DEFINITION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.definitions_path,
                                "cims_sla_definitions", ("definition_id",))
        for r in records:
            if r.get("definition_id") == definition_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_DEFINITION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.definitions_path, records,
                                  "cims_sla_definitions", "definition_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "definition_not_found"}

    def register_sla_obligation(
        self, obligation_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("obligation_id", "definition_id",
                      "linked_session_id", "deadline_at"):
            if f not in obligation_data or not obligation_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        # Validate deadline_at parses as ISO timestamp
        try:
            datetime.fromisoformat(obligation_data["deadline_at"])
        except ValueError:
            return {"registered": False,
                       "error": "deadline_at_not_iso_format"}
        records = self._load(self.obligations_path,
                                "cims_sla_obligations", ("obligation_id",))
        if any(r.get("obligation_id") == obligation_data["obligation_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_obligation_id"}
        record = {
            "obligation_id": obligation_data["obligation_id"],
            "definition_id": obligation_data["definition_id"],
            "linked_session_id": obligation_data["linked_session_id"],
            "deadline_at": obligation_data["deadline_at"],
            "state": "PENDING",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PENDING", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.obligations_path, records,
                          "cims_sla_obligations", "obligation_id")
        return {"registered": ok,
                  "obligation_id": obligation_data["obligation_id"]}

    def transition_obligation_state(
        self, obligation_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in OBLIGATION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.obligations_path,
                                "cims_sla_obligations", ("obligation_id",))
        for r in records:
            if r.get("obligation_id") == obligation_id:
                current = r.get("state", "PENDING")
                allowed = ALLOWED_OBLIGATION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                if new_state == "FULFILLED":
                    r["fulfilled_at"] = datetime.utcnow().isoformat()
                if new_state == "BREACHED":
                    r["breached_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.obligations_path, records,
                                  "cims_sla_obligations", "obligation_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "obligation_not_found"}

    def record_obligation_event(
        self, event_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("event_id", "obligation_id", "event_type"):
            if f not in event_data or not event_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if event_data["event_type"] not in OBLIGATION_EVENT_TYPES:
            return {"recorded": False,
                       "error": f"invalid_event_type:{event_data['event_type']}"}
        records = self._load(self.events_path,
                                "cims_sla_events", ("event_id",))
        if any(r.get("event_id") == event_data["event_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_event_id"}
        record = {
            "event_id": event_data["event_id"],
            "obligation_id": event_data["obligation_id"],
            "event_type": event_data["event_type"],
            "narrative": event_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.events_path, records,
                          "cims_sla_events", "event_id")
        return {"recorded": ok, "event_id": event_data["event_id"]}

    def breach_report(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        obligations = [
            o for o in self._load(self.obligations_path,
                                            "cims_sla_obligations",
                                            ("obligation_id",))
            if o.get("registered_at", "") >= cutoff
        ]
        breached = []
        now = datetime.utcnow()
        for o in obligations:
            try:
                deadline = datetime.fromisoformat(
                    o.get("deadline_at", ""),
                )
            except ValueError:
                continue
            state = o.get("state", "")
            if state == "BREACHED":
                breached.append({
                    "obligation_id": o.get("obligation_id"),
                    "deadline_at": o.get("deadline_at"),
                    "outcome": "EXPLICITLY_BREACHED",
                })
            elif (state in ("PENDING", "IN_PROGRESS")
                    and now > deadline):
                hours_late = (now - deadline).total_seconds() / 3600
                breached.append({
                    "obligation_id": o.get("obligation_id"),
                    "deadline_at": o.get("deadline_at"),
                    "outcome": "PAST_DEADLINE_NOT_FULFILLED",
                    "hours_late": round(hours_late, 1),
                })
        breach_pct = round(
            (len(breached) / len(obligations) * 100)
            if obligations else 0, 1,
        )
        return {
            "window_days": days,
            "obligations_in_window": len(obligations),
            "breached": breached,
            "breach_count": len(breached),
            "breach_pct": breach_pct,
        }

    def upcoming_deadlines(
        self, within_hours: int = 24,
    ) -> List[Dict[str, Any]]:
        if within_hours <= 0:
            return []
        records = self._load(self.obligations_path,
                                "cims_sla_obligations", ("obligation_id",))
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=within_hours)
        upcoming = []
        for o in records:
            if o.get("state") not in ("PENDING", "IN_PROGRESS"):
                continue
            try:
                deadline = datetime.fromisoformat(
                    o.get("deadline_at", ""),
                )
            except ValueError:
                continue
            if now <= deadline <= cutoff:
                upcoming.append({
                    "obligation_id": o.get("obligation_id"),
                    "definition_id": o.get("definition_id"),
                    "linked_session_id": o.get("linked_session_id"),
                    "deadline_at": o.get("deadline_at"),
                    "hours_remaining": round(
                        (deadline - now).total_seconds() / 3600, 1,
                    ),
                })
        upcoming.sort(key=lambda x: x["hours_remaining"])
        return upcoming


def _self_test() -> None:
    import tempfile

    assert REGULATORY_FRAMEWORKS == (
        "REG_E", "REG_Z", "CBK_BANKING_ACT",
        "CBK_PRUDENTIAL", "DPA_KENYA_2019",
    )
    assert SLA_DEFINITION_STATES == (
        "DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED",
    )
    assert ALLOWED_DEFINITION_TRANSITIONS["ARCHIVED"] == ()
    assert OBLIGATION_STATES == (
        "PENDING", "IN_PROGRESS", "FULFILLED",
        "BREACHED", "CANCELLED",
    )
    assert ALLOWED_OBLIGATION_TRANSITIONS["FULFILLED"] == ()
    assert ALLOWED_OBLIGATION_TRANSITIONS["BREACHED"] == ()
    assert ALLOWED_OBLIGATION_TRANSITIONS["CANCELLED"] == ()
    assert OBLIGATION_EVENT_TYPES == (
        "DEADLINE_REGISTERED", "REMINDER_SENT",
        "DEADLINE_APPROACHING", "DEADLINE_BREACHED",
        "FULFILLED_RECORDED",
    )
    assert SLA_BREACH_SEVERITIES == ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS["DISPUTE_INVESTIGATION"] == 240
    assert INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS["BILLING_ERROR"] == 720
    assert INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS["CUSTOMER_COMPLAINT"] == 120
    assert INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS["GENERAL_INQUIRY"] == 48
    assert INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS["REGULATORY_REPORTING"] == 168
    assert DEFAULT_REMINDER_AT_HOURS_REMAINING == 24
    assert DEFAULT_APPROACHING_AT_HOURS_REMAINING == 4

    with tempfile.TemporaryDirectory() as tmpdir:
        e = RegulatorySLAEngine(
            definitions_path=Path(tmpdir) / "d.json",
            obligations_path=Path(tmpdir) / "o.json",
            events_path=Path(tmpdir) / "e.json",
        )

        # Definition
        r = e.register_sla_definition(
            {"definition_id": "DEF-001",
             "name": "Reg E dispute",
             "framework": "REG_E",
             "instruction_type": "DISPUTE_INVESTIGATION",
             "deadline_hours": 240,
             "narrative": "10 business days under Reg E"},
            actor="ops", reason="setup",
        )
        assert r["registered"]
        # Bad framework
        r = e.register_sla_definition(
            {"definition_id": "X", "name": "Y",
             "framework": "WHATEVER",
             "instruction_type": "Z",
             "deadline_hours": 24},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Non-positive hours
        r = e.register_sla_definition(
            {"definition_id": "Z", "name": "Y",
             "framework": "REG_E",
             "instruction_type": "Z",
             "deadline_hours": 0},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Definition lifecycle
        r = e.transition_definition_state(
            "DEF-001", "ACTIVE", actor="ops", reason="ready",
        )
        assert r["transitioned"]
        r = e.transition_definition_state(
            "DEF-001", "DEPRECATED",
            actor="ops", reason="superseded",
        )
        assert r["transitioned"]
        r = e.transition_definition_state(
            "DEF-001", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]
        r = e.transition_definition_state(
            "DEF-001", "ARCHIVED",
            actor="ops", reason="closed",
        )
        assert r["transitioned"]

        # Obligation — past deadline (will show in breach report)
        past = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        r = e.register_sla_obligation(
            {"obligation_id": "OB-001",
             "definition_id": "DEF-001",
             "linked_session_id": "CAP-001",
             "deadline_at": past},
            actor="ops", reason="customer dispute",
        )
        assert r["registered"]
        # Bad deadline format
        r = e.register_sla_obligation(
            {"obligation_id": "X",
             "definition_id": "Y",
             "linked_session_id": "Z",
             "deadline_at": "yesterday"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Obligation lifecycle
        r = e.transition_obligation_state(
            "OB-001", "IN_PROGRESS",
            actor="ops", reason="working",
        )
        assert r["transitioned"]

        # Event
        r = e.record_obligation_event(
            {"event_id": "EV-001",
             "obligation_id": "OB-001",
             "event_type": "DEADLINE_BREACHED"},
            actor="ops",
        )
        assert r["recorded"]
        # Bad event type
        r = e.record_obligation_event(
            {"event_id": "X",
             "obligation_id": "Y",
             "event_type": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Breach report — past deadline + IN_PROGRESS = breached
        rep = e.breach_report(days=30)
        assert rep["obligations_in_window"] == 1
        assert rep["breach_count"] == 1
        assert rep["breached"][0]["outcome"] == "PAST_DEADLINE_NOT_FULFILLED"

        # Upcoming deadlines — register a future one
        future = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        e.register_sla_obligation(
            {"obligation_id": "OB-002",
             "definition_id": "DEF-001",
             "linked_session_id": "CAP-002",
             "deadline_at": future},
            actor="ops", reason="another",
        )
        upcoming = e.upcoming_deadlines(within_hours=24)
        assert any(u["obligation_id"] == "OB-002" for u in upcoming)

    print("  ✅ cims_regulatory_sla self-test PASS")


if __name__ == "__main__":
    _self_test()

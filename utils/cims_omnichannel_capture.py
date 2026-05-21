"""
================================================================================
A2Z MIS 360 — Standard #166: Omnichannel Instruction Capture Engine
================================================================================

Risk classification: Cat C (read-side capture; stateful handoffs across
channels; never auto-acts on instruction content).

Subcategory: cims (Customer Instructions Management System)

Unified instruction capture with cross-channel continuity. A customer
starts an instruction in one channel (mobile app), moves to another
(branch), and the engine treats them as one continuous capture session.
The handoff state is the contract: which channels touched the
instruction, in what order, with what fingerprint.

Public API:
    register_capture_session(session_data, actor, reason)
    record_channel_touch(touch_data, actor)
    transition_capture_state(session_id, new_state, actor, reason)
    register_handoff(handoff_data, actor, reason)
    capture_summary(session_id) -> Dict
    sessions_by_channel(channel) -> List

CHANNELS byte-for-byte (8):
    BRANCH, MOBILE_APP, USSD, INTERNET_BANKING,
    CONTACT_CENTRE, EMAIL, RM_PORTAL, ATM

CAPTURE_STATES byte-for-byte (5):
    INITIATED, IN_PROGRESS, HANDED_OFF, COMPLETED, ABANDONED

ALLOWED_CAPTURE_TRANSITIONS (Rule 4):
    INITIATED   → IN_PROGRESS | ABANDONED
    IN_PROGRESS → HANDED_OFF | COMPLETED | ABANDONED
    HANDED_OFF  → IN_PROGRESS | COMPLETED | ABANDONED
    COMPLETED   → ()
    ABANDONED   → ()

INSTRUCTION_TYPES byte-for-byte (8):
    ACCOUNT_OPENING, FUNDS_TRANSFER, CARD_REQUEST,
    LOAN_INQUIRY, COMPLAINT, STATEMENT_REQUEST,
    PROFILE_UPDATE, GENERAL_INQUIRY

DEFAULT_CAPTURE_TIMEOUT_MINUTES = 30
DEFAULT_ABANDONMENT_THRESHOLD_MINUTES = 60

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CHANNELS: Tuple[str, ...] = (
    "BRANCH", "MOBILE_APP", "USSD", "INTERNET_BANKING",
    "CONTACT_CENTRE", "EMAIL", "RM_PORTAL", "ATM",
)

CAPTURE_STATES: Tuple[str, ...] = (
    "INITIATED", "IN_PROGRESS", "HANDED_OFF",
    "COMPLETED", "ABANDONED",
)

ALLOWED_CAPTURE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "INITIATED":   ("IN_PROGRESS", "ABANDONED"),
    "IN_PROGRESS": ("HANDED_OFF", "COMPLETED", "ABANDONED"),
    "HANDED_OFF":  ("IN_PROGRESS", "COMPLETED", "ABANDONED"),
    "COMPLETED":   (),
    "ABANDONED":   (),
}

INSTRUCTION_TYPES: Tuple[str, ...] = (
    "ACCOUNT_OPENING", "FUNDS_TRANSFER", "CARD_REQUEST",
    "LOAN_INQUIRY", "COMPLAINT", "STATEMENT_REQUEST",
    "PROFILE_UPDATE", "GENERAL_INQUIRY",
)

DEFAULT_CAPTURE_TIMEOUT_MINUTES = 30
DEFAULT_ABANDONMENT_THRESHOLD_MINUTES = 60


class OmnichannelCaptureEngine:
    """Cross-channel instruction capture session registry."""

    def __init__(
        self,
        sessions_path: Optional[Path] = None,
        touches_path: Optional[Path] = None,
        handoffs_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.sessions_path = (
            sessions_path or base / "cims_capture_sessions.json"
        )
        self.touches_path = (
            touches_path or base / "cims_channel_touches.json"
        )
        self.handoffs_path = (
            handoffs_path or base / "cims_capture_handoffs.json"
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

    def register_capture_session(
        self, session_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("session_id", "customer_id", "instruction_type",
                      "originating_channel"):
            if f not in session_data or not session_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if session_data["instruction_type"] not in INSTRUCTION_TYPES:
            return {"registered": False,
                       "error": f"invalid_instruction_type:{session_data['instruction_type']}"}
        if session_data["originating_channel"] not in CHANNELS:
            return {"registered": False,
                       "error": f"invalid_channel:{session_data['originating_channel']}"}
        records = self._load(self.sessions_path,
                                "cims_capture_sessions", ("session_id",))
        if any(r.get("session_id") == session_data["session_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_session_id"}
        record = {
            "session_id": session_data["session_id"],
            "customer_id": session_data["customer_id"],
            "instruction_type": session_data["instruction_type"],
            "originating_channel": session_data["originating_channel"],
            "state": "INITIATED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "INITIATED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.sessions_path, records,
                          "cims_capture_sessions", "session_id")
        return {"registered": ok,
                  "session_id": session_data["session_id"]}

    def record_channel_touch(
        self, touch_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("touch_id", "session_id", "channel"):
            if f not in touch_data or not touch_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if touch_data["channel"] not in CHANNELS:
            return {"recorded": False,
                       "error": f"invalid_channel:{touch_data['channel']}"}
        records = self._load(self.touches_path,
                                "cims_channel_touches", ("touch_id",))
        if any(r.get("touch_id") == touch_data["touch_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_touch_id"}
        record = {
            "touch_id": touch_data["touch_id"],
            "session_id": touch_data["session_id"],
            "channel": touch_data["channel"],
            "fingerprint": touch_data.get("fingerprint", ""),
            "duration_seconds": touch_data.get("duration_seconds"),
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.touches_path, records,
                          "cims_channel_touches", "touch_id")
        return {"recorded": ok, "touch_id": touch_data["touch_id"]}

    def transition_capture_state(
        self, session_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in CAPTURE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.sessions_path,
                                "cims_capture_sessions", ("session_id",))
        for r in records:
            if r.get("session_id") == session_id:
                current = r.get("state", "INITIATED")
                allowed = ALLOWED_CAPTURE_TRANSITIONS.get(current, ())
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
                                  "cims_capture_sessions", "session_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "session_not_found"}

    def register_handoff(
        self, handoff_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("handoff_id", "session_id", "from_channel", "to_channel"):
            if f not in handoff_data or not handoff_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if handoff_data["from_channel"] not in CHANNELS:
            return {"registered": False,
                       "error": f"invalid_from_channel:{handoff_data['from_channel']}"}
        if handoff_data["to_channel"] not in CHANNELS:
            return {"registered": False,
                       "error": f"invalid_to_channel:{handoff_data['to_channel']}"}
        records = self._load(self.handoffs_path,
                                "cims_capture_handoffs", ("handoff_id",))
        if any(r.get("handoff_id") == handoff_data["handoff_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_handoff_id"}
        record = {
            "handoff_id": handoff_data["handoff_id"],
            "session_id": handoff_data["session_id"],
            "from_channel": handoff_data["from_channel"],
            "to_channel": handoff_data["to_channel"],
            "context_preserved": bool(
                handoff_data.get("context_preserved", True),
            ),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.handoffs_path, records,
                          "cims_capture_handoffs", "handoff_id")
        return {"registered": ok,
                  "handoff_id": handoff_data["handoff_id"]}

    def capture_summary(self, session_id: str) -> Dict[str, Any]:
        sessions = self._load(self.sessions_path,
                                  "cims_capture_sessions", ("session_id",))
        session = next((s for s in sessions
                              if s.get("session_id") == session_id), None)
        if session is None:
            return {"found": False, "error": "session_not_found"}
        touches = [t for t in self._load(self.touches_path,
                                                     "cims_channel_touches",
                                                     ("touch_id",))
                       if t.get("session_id") == session_id]
        handoffs = [h for h in self._load(self.handoffs_path,
                                                       "cims_capture_handoffs",
                                                       ("handoff_id",))
                         if h.get("session_id") == session_id]
        channels_touched = sorted({t.get("channel") for t in touches})
        return {
            "found": True,
            "session_id": session_id,
            "state": session.get("state"),
            "originating_channel": session.get("originating_channel"),
            "instruction_type": session.get("instruction_type"),
            "channels_touched": channels_touched,
            "channel_count": len(channels_touched),
            "touches_count": len(touches),
            "handoffs_count": len(handoffs),
            "is_omnichannel": len(channels_touched) > 1,
        }

    def sessions_by_channel(self, channel: str) -> List[Dict[str, Any]]:
        if channel not in CHANNELS:
            return []
        records = self._load(self.sessions_path,
                                "cims_capture_sessions", ("session_id",))
        return [r for r in records
                       if r.get("originating_channel") == channel]


def _self_test() -> None:
    import tempfile

    assert CHANNELS == (
        "BRANCH", "MOBILE_APP", "USSD", "INTERNET_BANKING",
        "CONTACT_CENTRE", "EMAIL", "RM_PORTAL", "ATM",
    )
    assert CAPTURE_STATES == (
        "INITIATED", "IN_PROGRESS", "HANDED_OFF",
        "COMPLETED", "ABANDONED",
    )
    assert ALLOWED_CAPTURE_TRANSITIONS["COMPLETED"] == ()
    assert ALLOWED_CAPTURE_TRANSITIONS["ABANDONED"] == ()
    assert INSTRUCTION_TYPES == (
        "ACCOUNT_OPENING", "FUNDS_TRANSFER", "CARD_REQUEST",
        "LOAN_INQUIRY", "COMPLAINT", "STATEMENT_REQUEST",
        "PROFILE_UPDATE", "GENERAL_INQUIRY",
    )
    assert DEFAULT_CAPTURE_TIMEOUT_MINUTES == 30
    assert DEFAULT_ABANDONMENT_THRESHOLD_MINUTES == 60

    with tempfile.TemporaryDirectory() as tmpdir:
        e = OmnichannelCaptureEngine(
            sessions_path=Path(tmpdir) / "s.json",
            touches_path=Path(tmpdir) / "t.json",
            handoffs_path=Path(tmpdir) / "h.json",
        )
        # Session
        r = e.register_capture_session(
            {"session_id": "CAP-001",
             "customer_id": "CUST-100",
             "instruction_type": "FUNDS_TRANSFER",
             "originating_channel": "MOBILE_APP"},
            actor="capture-svc", reason="customer initiated",
        )
        assert r["registered"]
        # Bad type
        r = e.register_capture_session(
            {"session_id": "X", "customer_id": "Y",
             "instruction_type": "WHATEVER",
             "originating_channel": "MOBILE_APP"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Bad channel
        r = e.register_capture_session(
            {"session_id": "Z", "customer_id": "Y",
             "instruction_type": "FUNDS_TRANSFER",
             "originating_channel": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Touches
        e.record_channel_touch(
            {"touch_id": "T-001", "session_id": "CAP-001",
             "channel": "MOBILE_APP", "duration_seconds": 120},
            actor="capture-svc",
        )
        e.record_channel_touch(
            {"touch_id": "T-002", "session_id": "CAP-001",
             "channel": "BRANCH", "duration_seconds": 600},
            actor="branch-teller",
        )
        # Bad channel
        r = e.record_channel_touch(
            {"touch_id": "T-X", "session_id": "CAP-001",
             "channel": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Lifecycle
        r = e.transition_capture_state(
            "CAP-001", "IN_PROGRESS",
            actor="capture-svc", reason="started",
        )
        assert r["transitioned"]
        r = e.transition_capture_state(
            "CAP-001", "HANDED_OFF",
            actor="branch-teller", reason="moved to branch",
        )
        assert r["transitioned"]

        # Handoff
        r = e.register_handoff(
            {"handoff_id": "H-001",
             "session_id": "CAP-001",
             "from_channel": "MOBILE_APP",
             "to_channel": "BRANCH",
             "context_preserved": True},
            actor="branch-teller", reason="customer arrived in person",
        )
        assert r["registered"]

        r = e.transition_capture_state(
            "CAP-001", "COMPLETED",
            actor="branch-teller", reason="instruction submitted",
        )
        assert r["transitioned"]
        # COMPLETED is terminal
        r = e.transition_capture_state(
            "CAP-001", "IN_PROGRESS", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Summary
        s = e.capture_summary("CAP-001")
        assert s["found"]
        assert s["state"] == "COMPLETED"
        assert s["channel_count"] == 2
        assert s["is_omnichannel"]
        assert "MOBILE_APP" in s["channels_touched"]
        assert "BRANCH" in s["channels_touched"]
        assert s["handoffs_count"] == 1

        # By channel
        mobile = e.sessions_by_channel("MOBILE_APP")
        assert len(mobile) == 1
        bad = e.sessions_by_channel("WHATEVER")
        assert bad == []

    print("  ✅ cims_omnichannel_capture self-test PASS")


if __name__ == "__main__":
    _self_test()

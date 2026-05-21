"""
================================================================================
A2Z MIS 360 — Standard #279: Trade Finance Mobile App
================================================================================

Risk classification: Cat C (UI client concern; thin wrapper over existing
trade_finance_corporate_portal engine; never replicates upstream logic).

Subcategory: trade_finance

Mobile session lifecycle for the trade finance corporate portal. The
existing TradeFinanceCorporatePortalEngine (ENH-271) handles all
validation logic across LCApplication / AmendmentRequest /
DocumentUpload / CorporateMessage shapes. This module owns the
mobile-specific concerns: session lifecycle, device registration,
push notification routing, and offline-draft tracking.

Per ENH-279's scope-resolution: mobile delivery is a UI workstream,
not an engine-architecture concern. This module provides the minimum
engine-side surface needed to track mobile-specific state without
duplicating any portal validation logic. All actual validation calls
delegate to TradeFinanceCorporatePortalEngine.

Public API:
    register_mobile_session(session_data, actor, reason)
    transition_session_state(session_id, new_state, actor, reason)
    register_device(device_data, actor, reason)
    revoke_device(device_id, actor, reason)
    record_push_notification(notification_data, actor)
    record_offline_draft(draft_data, actor)
    session_metrics(days=30) -> Dict
    active_sessions_for_user(username) -> List

MOBILE_SESSION_STATES byte-for-byte (5):
    INITIATED, AUTHENTICATED, ACTIVE, EXPIRED, REVOKED

ALLOWED_SESSION_TRANSITIONS (Rule 4):
    INITIATED     → AUTHENTICATED | EXPIRED | REVOKED
    AUTHENTICATED → ACTIVE | EXPIRED | REVOKED
    ACTIVE        → EXPIRED | REVOKED
    EXPIRED       → ()
    REVOKED       → ()

DEVICE_PLATFORMS byte-for-byte (4):
    IOS, ANDROID, REACT_NATIVE, PROGRESSIVE_WEB_APP

DEVICE_STATES byte-for-byte (3):
    REGISTERED, REVOKED, BLOCKED

PUSH_NOTIFICATION_TYPES byte-for-byte (5):
    LC_AMENDMENT_DECISION, DOCUMENT_REQUEST, MESSAGE_FROM_BANK,
    INSTRUMENT_STATUS_CHANGE, SECURITY_ALERT

PUSH_DELIVERY_OUTCOMES byte-for-byte (4):
    DELIVERED, FAILED, EXPIRED, SUPPRESSED

DRAFT_TYPES byte-for-byte (4):
    LC_APPLICATION, AMENDMENT_REQUEST, DOCUMENT_UPLOAD, CORPORATE_MESSAGE

DRAFT_STATES byte-for-byte (4):
    DRAFT, SYNCED, SUBMITTED, DISCARDED

ALLOWED_DRAFT_TRANSITIONS (Rule 4):
    DRAFT     → SYNCED | DISCARDED
    SYNCED    → SUBMITTED | DISCARDED
    SUBMITTED → ()
    DISCARDED → ()

DEFAULT_SESSION_TIMEOUT_MINUTES = 15
DEFAULT_DEVICE_REGISTRATION_TTL_DAYS = 90
DEFAULT_PUSH_DELIVERY_TIMEOUT_SECONDS = 30
DEFAULT_OFFLINE_DRAFT_TTL_HOURS = 72

CBK_MOBILE_BANKING_REFERENCE = "CBK Guidance Note on Mobile Banking"
DPA_MOBILE_REFERENCE = "Data Protection Act 2019"

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MOBILE_SESSION_STATES: Tuple[str, ...] = (
    "INITIATED", "AUTHENTICATED", "ACTIVE", "EXPIRED", "REVOKED",
)

ALLOWED_SESSION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "INITIATED":     ("AUTHENTICATED", "EXPIRED", "REVOKED"),
    "AUTHENTICATED": ("ACTIVE", "EXPIRED", "REVOKED"),
    "ACTIVE":        ("EXPIRED", "REVOKED"),
    "EXPIRED":       (),
    "REVOKED":       (),
}

DEVICE_PLATFORMS: Tuple[str, ...] = (
    "IOS", "ANDROID", "REACT_NATIVE", "PROGRESSIVE_WEB_APP",
)

DEVICE_STATES: Tuple[str, ...] = (
    "REGISTERED", "REVOKED", "BLOCKED",
)

PUSH_NOTIFICATION_TYPES: Tuple[str, ...] = (
    "LC_AMENDMENT_DECISION", "DOCUMENT_REQUEST", "MESSAGE_FROM_BANK",
    "INSTRUMENT_STATUS_CHANGE", "SECURITY_ALERT",
)

PUSH_DELIVERY_OUTCOMES: Tuple[str, ...] = (
    "DELIVERED", "FAILED", "EXPIRED", "SUPPRESSED",
)

DRAFT_TYPES: Tuple[str, ...] = (
    "LC_APPLICATION", "AMENDMENT_REQUEST",
    "DOCUMENT_UPLOAD", "CORPORATE_MESSAGE",
)

DRAFT_STATES: Tuple[str, ...] = (
    "DRAFT", "SYNCED", "SUBMITTED", "DISCARDED",
)

ALLOWED_DRAFT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":     ("SYNCED", "DISCARDED"),
    "SYNCED":    ("SUBMITTED", "DISCARDED"),
    "SUBMITTED": (),
    "DISCARDED": (),
}

DEFAULT_SESSION_TIMEOUT_MINUTES = 15
DEFAULT_DEVICE_REGISTRATION_TTL_DAYS = 90
DEFAULT_PUSH_DELIVERY_TIMEOUT_SECONDS = 30
DEFAULT_OFFLINE_DRAFT_TTL_HOURS = 72

CBK_MOBILE_BANKING_REFERENCE = "CBK Guidance Note on Mobile Banking"
DPA_MOBILE_REFERENCE = "Data Protection Act 2019"


class TradeFinanceMobileEngine:
    """Mobile session lifecycle + device + push + offline draft registry.

    Thin wrapper — never replicates portal validation logic. All
    actual application/amendment/document/message validation flows
    through TradeFinanceCorporatePortalEngine via the cockpit.
    """

    def __init__(
        self,
        sessions_path: Optional[Path] = None,
        devices_path: Optional[Path] = None,
        notifications_path: Optional[Path] = None,
        drafts_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.sessions_path = sessions_path or base / "tf_mobile_sessions.json"
        self.devices_path = devices_path or base / "tf_mobile_devices.json"
        self.notifications_path = (
            notifications_path or base / "tf_mobile_push_notifications.json"
        )
        self.drafts_path = drafts_path or base / "tf_mobile_offline_drafts.json"

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

    def register_mobile_session(
        self, session_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("session_id", "username", "device_id"):
            if f not in session_data or not session_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.sessions_path,
                                "tf_mobile_sessions", ("session_id",))
        if any(r.get("session_id") == session_data["session_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_session_id"}
        record = {
            "session_id": session_data["session_id"],
            "username": session_data["username"],
            "device_id": session_data["device_id"],
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
                          "tf_mobile_sessions", "session_id")
        return {"registered": ok,
                  "session_id": session_data["session_id"]}

    def transition_session_state(
        self, session_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in MOBILE_SESSION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.sessions_path,
                                "tf_mobile_sessions", ("session_id",))
        for r in records:
            if r.get("session_id") == session_id:
                current = r.get("state", "INITIATED")
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
                                  "tf_mobile_sessions", "session_id")
                return {"transitioned": ok,
                          "from": current, "to": new_state}
        return {"transitioned": False, "error": "session_not_found"}

    def register_device(
        self, device_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("device_id", "username", "platform", "device_fingerprint"):
            if f not in device_data or not device_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if device_data["platform"] not in DEVICE_PLATFORMS:
            return {"registered": False,
                       "error": f"invalid_platform:{device_data['platform']}"}
        records = self._load(self.devices_path,
                                "tf_mobile_devices", ("device_id",))
        if any(r.get("device_id") == device_data["device_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_device_id"}
        record = {
            "device_id": device_data["device_id"],
            "username": device_data["username"],
            "platform": device_data["platform"],
            "device_fingerprint": device_data["device_fingerprint"],
            "state": "REGISTERED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.devices_path, records,
                          "tf_mobile_devices", "device_id")
        return {"registered": ok, "device_id": device_data["device_id"]}

    def revoke_device(
        self, device_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"revoked": False, "error": "actor_and_reason_required"}
        records = self._load(self.devices_path,
                                "tf_mobile_devices", ("device_id",))
        for r in records:
            if r.get("device_id") == device_id:
                if r.get("state") == "REVOKED":
                    return {"revoked": False, "error": "already_revoked"}
                r["state"] = "REVOKED"
                r["revoked_by"] = actor
                r["revoked_at"] = datetime.utcnow().isoformat()
                r["revocation_reason"] = reason
                ok = self._save(self.devices_path, records,
                                  "tf_mobile_devices", "device_id")
                return {"revoked": ok, "device_id": device_id}
        return {"revoked": False, "error": "device_not_found"}

    def record_push_notification(
        self, notification_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("notification_id", "device_id",
                      "notification_type", "outcome"):
            if f not in notification_data or not notification_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if notification_data["notification_type"] not in PUSH_NOTIFICATION_TYPES:
            return {"recorded": False,
                       "error": f"invalid_type:{notification_data['notification_type']}"}
        if notification_data["outcome"] not in PUSH_DELIVERY_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{notification_data['outcome']}"}
        records = self._load(self.notifications_path,
                                "tf_mobile_push_notifications",
                                ("notification_id",))
        if any(r.get("notification_id") == notification_data["notification_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_notification_id"}
        record = {
            "notification_id": notification_data["notification_id"],
            "device_id": notification_data["device_id"],
            "notification_type": notification_data["notification_type"],
            "outcome": notification_data["outcome"],
            "subject_ref": notification_data.get("subject_ref", ""),
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.notifications_path, records,
                          "tf_mobile_push_notifications",
                          "notification_id")
        return {"recorded": ok,
                  "notification_id": notification_data["notification_id"]}

    def record_offline_draft(
        self, draft_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("draft_id", "session_id", "draft_type", "state"):
            if f not in draft_data or not draft_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if draft_data["draft_type"] not in DRAFT_TYPES:
            return {"recorded": False,
                       "error": f"invalid_draft_type:{draft_data['draft_type']}"}
        if draft_data["state"] not in DRAFT_STATES:
            return {"recorded": False,
                       "error": f"invalid_state:{draft_data['state']}"}
        records = self._load(self.drafts_path,
                                "tf_mobile_offline_drafts", ("draft_id",))
        if any(r.get("draft_id") == draft_data["draft_id"] for r in records):
            return {"recorded": False, "error": "duplicate_draft_id"}
        record = {
            "draft_id": draft_data["draft_id"],
            "session_id": draft_data["session_id"],
            "draft_type": draft_data["draft_type"],
            "state": draft_data["state"],
            "payload_summary": draft_data.get("payload_summary", ""),
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.drafts_path, records,
                          "tf_mobile_offline_drafts", "draft_id")
        return {"recorded": ok, "draft_id": draft_data["draft_id"]}

    def session_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        sessions = self._load(self.sessions_path,
                                  "tf_mobile_sessions", ("session_id",))
        recent = [s for s in sessions
                       if s.get("registered_at", "") >= cutoff]
        active = sum(1 for s in recent
                          if s.get("state") == "ACTIVE")
        revoked = sum(1 for s in recent
                            if s.get("state") == "REVOKED")
        expired = sum(1 for s in recent
                            if s.get("state") == "EXPIRED")
        notifications = self._load(self.notifications_path,
                                                "tf_mobile_push_notifications",
                                                ("notification_id",))
        recent_notifs = [n for n in notifications
                                if n.get("recorded_at", "") >= cutoff]
        delivered = sum(1 for n in recent_notifs
                                if n.get("outcome") == "DELIVERED")
        return {
            "window_days": days,
            "total_sessions": len(recent),
            "active": active,
            "revoked": revoked,
            "expired": expired,
            "total_notifications": len(recent_notifs),
            "notifications_delivered": delivered,
            "notification_delivery_rate_pct": round(
                (delivered / len(recent_notifs) * 100)
                if recent_notifs else 0, 1,
            ),
        }

    def active_sessions_for_user(self, username: str) -> List[Dict[str, Any]]:
        records = self._load(self.sessions_path,
                                "tf_mobile_sessions", ("session_id",))
        return [
            r for r in records
            if r.get("username") == username
                  and r.get("state") in ("AUTHENTICATED", "ACTIVE")
        ]


def _self_test() -> None:
    import tempfile

    assert MOBILE_SESSION_STATES == (
        "INITIATED", "AUTHENTICATED", "ACTIVE", "EXPIRED", "REVOKED",
    )
    assert ALLOWED_SESSION_TRANSITIONS["EXPIRED"] == ()
    assert ALLOWED_SESSION_TRANSITIONS["REVOKED"] == ()
    assert DEVICE_PLATFORMS == (
        "IOS", "ANDROID", "REACT_NATIVE", "PROGRESSIVE_WEB_APP",
    )
    assert DEVICE_STATES == ("REGISTERED", "REVOKED", "BLOCKED")
    assert PUSH_NOTIFICATION_TYPES == (
        "LC_AMENDMENT_DECISION", "DOCUMENT_REQUEST", "MESSAGE_FROM_BANK",
        "INSTRUMENT_STATUS_CHANGE", "SECURITY_ALERT",
    )
    assert PUSH_DELIVERY_OUTCOMES == (
        "DELIVERED", "FAILED", "EXPIRED", "SUPPRESSED",
    )
    assert DRAFT_TYPES == (
        "LC_APPLICATION", "AMENDMENT_REQUEST",
        "DOCUMENT_UPLOAD", "CORPORATE_MESSAGE",
    )
    assert DRAFT_STATES == ("DRAFT", "SYNCED", "SUBMITTED", "DISCARDED")
    assert ALLOWED_DRAFT_TRANSITIONS["SUBMITTED"] == ()
    assert ALLOWED_DRAFT_TRANSITIONS["DISCARDED"] == ()
    assert DEFAULT_SESSION_TIMEOUT_MINUTES == 15
    assert DEFAULT_DEVICE_REGISTRATION_TTL_DAYS == 90
    assert DEFAULT_PUSH_DELIVERY_TIMEOUT_SECONDS == 30
    assert DEFAULT_OFFLINE_DRAFT_TTL_HOURS == 72
    assert CBK_MOBILE_BANKING_REFERENCE == "CBK Guidance Note on Mobile Banking"
    assert DPA_MOBILE_REFERENCE == "Data Protection Act 2019"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = TradeFinanceMobileEngine(
            sessions_path=Path(tmpdir) / "s.json",
            devices_path=Path(tmpdir) / "d.json",
            notifications_path=Path(tmpdir) / "n.json",
            drafts_path=Path(tmpdir) / "dr.json",
        )
        # Device first
        r = e.register_device(
            {"device_id": "DEV-001",
             "username": "corporate.user",
             "platform": "IOS",
             "device_fingerprint": "abcdef123456"},
            actor="security", reason="onboarding",
        )
        assert r["registered"]
        # Bad platform
        r = e.register_device(
            {"device_id": "X", "username": "Y",
             "platform": "WHATEVER",
             "device_fingerprint": "xxx"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Session
        r = e.register_mobile_session(
            {"session_id": "SESS-001",
             "username": "corporate.user",
             "device_id": "DEV-001"},
            actor="security", reason="user login",
        )
        assert r["registered"]

        # Lifecycle
        r = e.transition_session_state(
            "SESS-001", "AUTHENTICATED",
            actor="security", reason="biometric verified",
        )
        assert r["transitioned"]
        r = e.transition_session_state(
            "SESS-001", "ACTIVE",
            actor="security", reason="MFA passed",
        )
        assert r["transitioned"]
        # Active sessions
        active = e.active_sessions_for_user("corporate.user")
        assert len(active) == 1
        # Expire
        r = e.transition_session_state(
            "SESS-001", "EXPIRED",
            actor="system", reason="inactivity timeout",
        )
        assert r["transitioned"]
        # EXPIRED is terminal
        r = e.transition_session_state(
            "SESS-001", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Notification
        r = e.record_push_notification(
            {"notification_id": "NOTIF-001",
             "device_id": "DEV-001",
             "notification_type": "LC_AMENDMENT_DECISION",
             "outcome": "DELIVERED",
             "subject_ref": "LC-2026-001"},
            actor="push-svc",
        )
        assert r["recorded"]
        # Bad type
        r = e.record_push_notification(
            {"notification_id": "X",
             "device_id": "Y",
             "notification_type": "WHATEVER",
             "outcome": "DELIVERED"},
            actor="x",
        )
        assert not r["recorded"]
        # Bad outcome
        r = e.record_push_notification(
            {"notification_id": "Y",
             "device_id": "Z",
             "notification_type": "MESSAGE_FROM_BANK",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Offline draft
        r = e.record_offline_draft(
            {"draft_id": "DRAFT-001",
             "session_id": "SESS-001",
             "draft_type": "LC_APPLICATION",
             "state": "DRAFT",
             "payload_summary": "Draft LC application for USD 50k"},
            actor="corporate.user",
        )
        assert r["recorded"]
        # Bad type
        r = e.record_offline_draft(
            {"draft_id": "X", "session_id": "Y",
             "draft_type": "WHATEVER", "state": "DRAFT"},
            actor="x",
        )
        assert not r["recorded"]

        # Revoke device
        r = e.revoke_device(
            "DEV-001", actor="security",
            reason="user reported lost phone",
        )
        assert r["revoked"]
        # Already revoked
        r = e.revoke_device(
            "DEV-001", actor="security", reason="x",
        )
        assert not r["revoked"]

        # Metrics
        m = e.session_metrics(days=30)
        assert m["total_sessions"] == 1
        assert m["expired"] == 1
        assert m["total_notifications"] == 1
        assert m["notifications_delivered"] == 1
        assert m["notification_delivery_rate_pct"] == 100.0

    print("  ✅ trade_finance_mobile self-test PASS")


if __name__ == "__main__":
    _self_test()

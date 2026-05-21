"""
================================================================================
A2Z MIS 360 — Standard #299: Digital Banking Suite (Mobile + Web)
================================================================================

Risk classification: Cat C (digital channel session + push notification registry)

React Native mobile apps, React/Next.js web. Omnichannel session continuity,
push notifications, biometric auth.

Public API:
    register_app(app_data, actor, reason)
    register_app_version(version_data, actor, reason)
    transition_version_state(version_id, new_state, actor, reason)
    register_session(session_data, actor)
    transition_session_state(session_id, new_state, actor, reason)
    record_push_notification(notification_data, actor)
    biometric_enrollment(enroll_data, actor, reason)
    session_continuity_check(customer_id) -> Dict
    notification_metrics(days=7) -> Dict

APP_PLATFORMS byte-for-byte (4): IOS, ANDROID, WEB, RESPONSIVE_WEB

APP_VERSION_STATES byte-for-byte (5):
    ALPHA, BETA, RELEASED, DEPRECATED, DISCONTINUED

ALLOWED_VERSION_TRANSITIONS (Rule 4):
    ALPHA        → BETA | DISCONTINUED
    BETA         → RELEASED | DISCONTINUED
    RELEASED     → DEPRECATED | DISCONTINUED
    DEPRECATED   → DISCONTINUED
    DISCONTINUED → ()

SESSION_STATES byte-for-byte (5):
    ACTIVE, IDLE, EXPIRED, REVOKED, SIGNED_OUT

ALLOWED_SESSION_TRANSITIONS (Rule 4):
    ACTIVE      → IDLE | EXPIRED | REVOKED | SIGNED_OUT
    IDLE        → ACTIVE | EXPIRED | SIGNED_OUT
    EXPIRED     → ()
    REVOKED     → ()
    SIGNED_OUT  → ()

NOTIFICATION_TYPES byte-for-byte (5):
    TRANSACTIONAL, ALERT, MARKETING, SECURITY, SYSTEM

NOTIFICATION_STATES byte-for-byte (4):
    PENDING, SENT, DELIVERED, FAILED

BIOMETRIC_TYPES byte-for-byte (4):
    FINGERPRINT, FACE_ID, IRIS, VOICE

DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES = 5
DEFAULT_SESSION_HARD_TIMEOUT_MINUTES = 30

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


APP_PLATFORMS: Tuple[str, ...] = (
    "IOS", "ANDROID", "WEB", "RESPONSIVE_WEB",
)

APP_VERSION_STATES: Tuple[str, ...] = (
    "ALPHA", "BETA", "RELEASED", "DEPRECATED", "DISCONTINUED",
)

ALLOWED_VERSION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ALPHA":        ("BETA", "DISCONTINUED"),
    "BETA":         ("RELEASED", "DISCONTINUED"),
    "RELEASED":     ("DEPRECATED", "DISCONTINUED"),
    "DEPRECATED":   ("DISCONTINUED",),
    "DISCONTINUED": (),
}

SESSION_STATES: Tuple[str, ...] = (
    "ACTIVE", "IDLE", "EXPIRED", "REVOKED", "SIGNED_OUT",
)

ALLOWED_SESSION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":     ("IDLE", "EXPIRED", "REVOKED", "SIGNED_OUT"),
    "IDLE":       ("ACTIVE", "EXPIRED", "SIGNED_OUT"),
    "EXPIRED":    (),
    "REVOKED":    (),
    "SIGNED_OUT": (),
}

NOTIFICATION_TYPES: Tuple[str, ...] = (
    "TRANSACTIONAL", "ALERT", "MARKETING", "SECURITY", "SYSTEM",
)

NOTIFICATION_STATES: Tuple[str, ...] = (
    "PENDING", "SENT", "DELIVERED", "FAILED",
)

BIOMETRIC_TYPES: Tuple[str, ...] = (
    "FINGERPRINT", "FACE_ID", "IRIS", "VOICE",
)

DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES = 5
DEFAULT_SESSION_HARD_TIMEOUT_MINUTES = 30


class DigitalBankingEngine:
    """Mobile + web channels — session, push, biometric registry."""

    def __init__(
        self,
        apps_path: Optional[Path] = None,
        versions_path: Optional[Path] = None,
        sessions_path: Optional[Path] = None,
        notifications_path: Optional[Path] = None,
        biometrics_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.apps_path = apps_path or base / "digital_apps.json"
        self.versions_path = versions_path or base / "digital_app_versions.json"
        self.sessions_path = sessions_path or base / "digital_sessions.json"
        self.notifications_path = (
            notifications_path or base / "digital_notifications.json"
        )
        self.biometrics_path = (
            biometrics_path or base / "digital_biometrics.json"
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

    def register_app(
        self, app_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("app_id", "app_name", "platform"):
            if f not in app_data or not app_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if app_data["platform"] not in APP_PLATFORMS:
            return {"registered": False,
                       "error": f"invalid_platform:{app_data['platform']}"}
        records = self._load(self.apps_path,
                                "digital_apps", ("app_id",))
        if any(r.get("app_id") == app_data["app_id"] for r in records):
            return {"registered": False, "error": "duplicate_app_id"}
        record = {
            "app_id": app_data["app_id"],
            "app_name": app_data["app_name"],
            "platform": app_data["platform"],
            "store_url": app_data.get("store_url", ""),
            "owner_team": app_data.get("owner_team", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.apps_path, records,
                          "digital_apps", "app_id")
        return {"registered": ok, "app_id": app_data["app_id"]}

    def register_app_version(
        self, version_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("version_id", "app_id", "version_number"):
            if f not in version_data or not version_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        # Verify app exists
        apps = self._load(self.apps_path, "digital_apps", ("app_id",))
        if not any(a.get("app_id") == version_data["app_id"] for a in apps):
            return {"registered": False, "error": "app_not_found"}
        records = self._load(self.versions_path,
                                "digital_app_versions", ("version_id",))
        if any(r.get("version_id") == version_data["version_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_version_id"}
        record = {
            "version_id": version_data["version_id"],
            "app_id": version_data["app_id"],
            "version_number": version_data["version_number"],
            "release_notes": version_data.get("release_notes", ""),
            "min_os_version": version_data.get("min_os_version", ""),
            "state": "ALPHA",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ALPHA", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.versions_path, records,
                          "digital_app_versions", "version_id")
        return {"registered": ok, "version_id": version_data["version_id"]}

    def transition_version_state(
        self, version_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in APP_VERSION_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.versions_path,
                                "digital_app_versions", ("version_id",))
        for r in records:
            if r.get("version_id") == version_id:
                current = r.get("state", "ALPHA")
                allowed = ALLOWED_VERSION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.versions_path, records,
                                  "digital_app_versions", "version_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "version_not_found"}

    def register_session(
        self, session_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("session_id", "customer_id", "app_id",
                      "device_fingerprint", "started_at"):
            if f not in session_data or not session_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.sessions_path,
                                "digital_sessions", ("session_id",))
        if any(r.get("session_id") == session_data["session_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_session_id"}
        record = {
            "session_id": session_data["session_id"],
            "customer_id": session_data["customer_id"],
            "app_id": session_data["app_id"],
            "device_fingerprint": session_data["device_fingerprint"],
            "ip_address": session_data.get("ip_address", ""),
            "started_at": session_data["started_at"],
            "last_active_at": session_data["started_at"],
            "state": "ACTIVE",
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.sessions_path, records,
                          "digital_sessions", "session_id")
        return {"registered": ok, "session_id": session_data["session_id"]}

    def transition_session_state(
        self, session_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in SESSION_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.sessions_path,
                                "digital_sessions", ("session_id",))
        for r in records:
            if r.get("session_id") == session_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_SESSION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                now = datetime.utcnow().isoformat()
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": now, "reason": reason,
                })
                if new_state == "ACTIVE":
                    r["last_active_at"] = now
                ok = self._save(self.sessions_path, records,
                                  "digital_sessions", "session_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "session_not_found"}

    def record_push_notification(
        self, notification_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("notification_id", "customer_id", "notification_type",
                      "title", "body"):
            if f not in notification_data or not notification_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if notification_data["notification_type"] not in NOTIFICATION_TYPES:
            return {"recorded": False,
                       "error": f"invalid_type:{notification_data['notification_type']}"}
        records = self._load(self.notifications_path,
                                "digital_notifications",
                                ("notification_id",))
        if any(r.get("notification_id") == notification_data["notification_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_notification_id"}
        record = {
            "notification_id": notification_data["notification_id"],
            "customer_id": notification_data["customer_id"],
            "notification_type": notification_data["notification_type"],
            "title": notification_data["title"],
            "body": notification_data["body"],
            "deep_link": notification_data.get("deep_link", ""),
            "state": "PENDING",
            "queued_at": datetime.utcnow().isoformat(),
            "queued_by": actor,
        }
        records.append(record)
        ok = self._save(self.notifications_path, records,
                          "digital_notifications", "notification_id")
        return {"recorded": ok,
                  "notification_id": notification_data["notification_id"]}

    def biometric_enrollment(
        self, enroll_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"enrolled": False, "error": "actor_and_reason_required"}
        for f in ("enrollment_id", "customer_id", "device_fingerprint",
                      "biometric_type"):
            if f not in enroll_data or not enroll_data[f]:
                return {"enrolled": False, "error": f"missing_field:{f}"}
        if enroll_data["biometric_type"] not in BIOMETRIC_TYPES:
            return {"enrolled": False,
                       "error": f"invalid_biometric_type:{enroll_data['biometric_type']}"}
        records = self._load(self.biometrics_path,
                                "digital_biometrics", ("enrollment_id",))
        if any(r.get("enrollment_id") == enroll_data["enrollment_id"]
                 for r in records):
            return {"enrolled": False, "error": "duplicate_enrollment_id"}
        record = {
            "enrollment_id": enroll_data["enrollment_id"],
            "customer_id": enroll_data["customer_id"],
            "device_fingerprint": enroll_data["device_fingerprint"],
            "biometric_type": enroll_data["biometric_type"],
            "enrolled_at": datetime.utcnow().isoformat(),
            "enrolled_by": actor,
            "enrollment_reason": reason,
            "active": True,
        }
        records.append(record)
        ok = self._save(self.biometrics_path, records,
                          "digital_biometrics", "enrollment_id")
        return {"enrolled": ok,
                  "enrollment_id": enroll_data["enrollment_id"]}

    def session_continuity_check(self, customer_id: str) -> Dict[str, Any]:
        sessions = self._load(self.sessions_path,
                                      "digital_sessions", ("session_id",))
        cust_sessions = [s for s in sessions
                                 if s.get("customer_id") == customer_id]
        active = [s for s in cust_sessions if s.get("state") == "ACTIVE"]
        idle = [s for s in cust_sessions if s.get("state") == "IDLE"]
        platforms_used = set()
        for s in cust_sessions:
            apps = self._load(self.apps_path, "digital_apps", ("app_id",))
            for a in apps:
                if a.get("app_id") == s.get("app_id"):
                    platforms_used.add(a.get("platform", ""))
        return {
            "customer_id": customer_id,
            "total_sessions": len(cust_sessions),
            "active_sessions": len(active),
            "idle_sessions": len(idle),
            "unique_platforms": len(platforms_used),
            "platforms": sorted(platforms_used),
            "omnichannel": len(platforms_used) >= 2,
        }

    def notification_metrics(self, days: int = 7) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        notifications = self._load(self.notifications_path,
                                            "digital_notifications",
                                            ("notification_id",))
        recent = [n for n in notifications
                       if n.get("queued_at", "") >= cutoff]
        delivered = sum(1 for n in recent if n.get("state") == "DELIVERED")
        failed = sum(1 for n in recent if n.get("state") == "FAILED")
        return {
            "window_days": days,
            "total_notifications": len(recent),
            "delivered": delivered,
            "failed": failed,
            "delivery_rate_pct": round(
                (delivered / len(recent) * 100) if recent else 0, 1,
            ),
        }


def _self_test() -> None:
    import tempfile

    assert "IOS" in APP_PLATFORMS
    assert ALLOWED_VERSION_TRANSITIONS["DISCONTINUED"] == ()
    assert "ACTIVE" in SESSION_STATES
    assert ALLOWED_SESSION_TRANSITIONS["EXPIRED"] == ()
    assert "TRANSACTIONAL" in NOTIFICATION_TYPES
    assert "FINGERPRINT" in BIOMETRIC_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        e = DigitalBankingEngine(
            apps_path=Path(tmpdir) / "a.json",
            versions_path=Path(tmpdir) / "v.json",
            sessions_path=Path(tmpdir) / "s.json",
            notifications_path=Path(tmpdir) / "n.json",
            biometrics_path=Path(tmpdir) / "b.json",
        )
        # App
        r = e.register_app(
            {"app_id": "APP-MOBILE-IOS",
             "app_name": "Bank Mobile iOS",
             "platform": "IOS",
             "store_url": "https://apps.apple.com/..."},
            actor="cto", reason="initial",
        )
        assert r["registered"]
        # Invalid platform
        r = e.register_app(
            {"app_id": "X", "app_name": "Y", "platform": "WP"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Version
        r = e.register_app_version(
            {"version_id": "VER-1.0",
             "app_id": "APP-MOBILE-IOS",
             "version_number": "1.0.0",
             "min_os_version": "14.0"},
            actor="cto", reason="initial",
        )
        assert r["registered"]
        # App not found
        r = e.register_app_version(
            {"version_id": "X", "app_id": "NOPE",
             "version_number": "1.0"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Version state machine
        r = e.transition_version_state("VER-1.0", "BETA",
                                              actor="cto", reason="ready")
        assert r["transitioned"]
        r = e.transition_version_state("VER-1.0", "RELEASED",
                                              actor="cto", reason="GA")
        assert r["transitioned"]
        r = e.transition_version_state("VER-1.0", "DEPRECATED",
                                              actor="cto", reason="v1.1")
        assert r["transitioned"]
        r = e.transition_version_state("VER-1.0", "DISCONTINUED",
                                              actor="cto", reason="EOL")
        assert r["transitioned"]
        # DISCONTINUED is terminal
        r = e.transition_version_state("VER-1.0", "ALPHA",
                                              actor="cto", reason="x")
        assert not r["transitioned"]

        # Session
        r = e.register_session(
            {"session_id": "SES-001",
             "customer_id": "CUST-100",
             "app_id": "APP-MOBILE-IOS",
             "device_fingerprint": "fp-abc",
             "started_at": datetime.utcnow().isoformat()},
            actor="auth-svc",
        )
        assert r["registered"]
        # Session transitions
        r = e.transition_session_state("SES-001", "IDLE",
                                              actor="auth-svc",
                                              reason="5min idle")
        assert r["transitioned"]
        r = e.transition_session_state("SES-001", "ACTIVE",
                                              actor="auth-svc",
                                              reason="user back")
        assert r["transitioned"]
        r = e.transition_session_state("SES-001", "SIGNED_OUT",
                                              actor="auth-svc",
                                              reason="logout")
        assert r["transitioned"]
        # SIGNED_OUT terminal
        r = e.transition_session_state("SES-001", "ACTIVE",
                                              actor="auth-svc", reason="x")
        assert not r["transitioned"]

        # Notification
        r = e.record_push_notification(
            {"notification_id": "NOT-001",
             "customer_id": "CUST-100",
             "notification_type": "TRANSACTIONAL",
             "title": "Payment received",
             "body": "KSh 5,000 received from John"},
            actor="notification-svc",
        )
        assert r["recorded"]
        # Invalid type
        r = e.record_push_notification(
            {"notification_id": "X", "customer_id": "Y",
             "notification_type": "WHATEVER",
             "title": "Z", "body": "T"},
            actor="x",
        )
        assert not r["recorded"]

        # Biometric
        r = e.biometric_enrollment(
            {"enrollment_id": "BIO-001",
             "customer_id": "CUST-100",
             "device_fingerprint": "fp-abc",
             "biometric_type": "FACE_ID"},
            actor="enroll-svc", reason="setup",
        )
        assert r["enrolled"]
        # Invalid biometric type
        r = e.biometric_enrollment(
            {"enrollment_id": "X", "customer_id": "Y",
             "device_fingerprint": "Z", "biometric_type": "DNA"},
            actor="x", reason="x",
        )
        assert not r["enrolled"]

        # Continuity check
        c = e.session_continuity_check("CUST-100")
        assert c["total_sessions"] == 1

        # Add web session
        e.register_app(
            {"app_id": "APP-WEB", "app_name": "Bank Web",
             "platform": "WEB"},
            actor="cto", reason="initial",
        )
        e.register_session(
            {"session_id": "SES-002", "customer_id": "CUST-100",
             "app_id": "APP-WEB", "device_fingerprint": "fp-web",
             "started_at": datetime.utcnow().isoformat()},
            actor="auth-svc",
        )
        c = e.session_continuity_check("CUST-100")
        assert c["omnichannel"]

        # Metrics
        m = e.notification_metrics(days=7)
        assert m["total_notifications"] == 1

    print("  ✅ it_digital_banking self-test PASS")


if __name__ == "__main__":
    _self_test()

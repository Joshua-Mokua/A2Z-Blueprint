"""
================================================================================
A2Z MIS 360 — Standard #296: Data Encryption & Security Hardening
================================================================================

Risk classification: Cat B (regulatory: DPA Kenya 2019 + CBK Cybersecurity)

TLS 1.3, AES-256 at rest, HSM-backed key management, field-level encryption
for PII, secrets vault (HashiCorp Vault / AWS KMS).

Public API:
    register_encryption_key(key_data, actor, reason)
    transition_key_state(key_id, new_state, actor, reason)
    register_secret(secret_data, actor, reason)
    rotate_secret(secret_id, actor, reason)
    register_pii_field(field_data, actor, reason)
    record_security_event(event_data, actor)
    encryption_compliance_status() -> Dict
    secret_rotation_due(within_days=30) -> List

ENCRYPTION_ALGORITHMS byte-for-byte (4):
    AES_256_GCM, AES_256_CBC, RSA_4096, ECDSA_P384

KEY_STATES byte-for-byte (5): PENDING, ACTIVE, ROTATING, DEPRECATED, DESTROYED

ALLOWED_KEY_TRANSITIONS (Rule 4):
    PENDING    → ACTIVE | DESTROYED
    ACTIVE     → ROTATING | DEPRECATED | DESTROYED
    ROTATING   → ACTIVE | DEPRECATED
    DEPRECATED → DESTROYED
    DESTROYED  → ()

KEY_USAGE_PURPOSES byte-for-byte (5):
    DATA_AT_REST, DATA_IN_TRANSIT, FIELD_LEVEL, SIGNING, AUTHENTICATION

SECRET_TYPES byte-for-byte (6):
    DATABASE_PASSWORD, API_KEY, SERVICE_ACCOUNT, TLS_CERTIFICATE,
    ENCRYPTION_KEY, OAUTH_CLIENT_SECRET

SECURITY_EVENT_TYPES byte-for-byte (7):
    KEY_ROTATION, SECRET_ROTATION, ACCESS_GRANT, ACCESS_REVOKE,
    POLICY_VIOLATION, SUSPICIOUS_ACCESS, AUDIT_FAILURE

PII_SENSITIVITY_LEVELS byte-for-byte (4): LOW, MEDIUM, HIGH, CRITICAL

DEFAULT_KEY_ROTATION_DAYS = 90  # CBK Cybersecurity recommended
DEFAULT_SECRET_ROTATION_DAYS = 60
DPA_KENYA_REGULATORY_REFERENCE = "Data Protection Act 2019"

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ENCRYPTION_ALGORITHMS: Tuple[str, ...] = (
    "AES_256_GCM", "AES_256_CBC", "RSA_4096", "ECDSA_P384",
)

KEY_STATES: Tuple[str, ...] = (
    "PENDING", "ACTIVE", "ROTATING", "DEPRECATED", "DESTROYED",
)

ALLOWED_KEY_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PENDING":    ("ACTIVE", "DESTROYED"),
    "ACTIVE":     ("ROTATING", "DEPRECATED", "DESTROYED"),
    "ROTATING":   ("ACTIVE", "DEPRECATED"),
    "DEPRECATED": ("DESTROYED",),
    "DESTROYED":  (),
}

KEY_USAGE_PURPOSES: Tuple[str, ...] = (
    "DATA_AT_REST", "DATA_IN_TRANSIT", "FIELD_LEVEL",
    "SIGNING", "AUTHENTICATION",
)

SECRET_TYPES: Tuple[str, ...] = (
    "DATABASE_PASSWORD", "API_KEY", "SERVICE_ACCOUNT",
    "TLS_CERTIFICATE", "ENCRYPTION_KEY", "OAUTH_CLIENT_SECRET",
)

SECURITY_EVENT_TYPES: Tuple[str, ...] = (
    "KEY_ROTATION", "SECRET_ROTATION", "ACCESS_GRANT", "ACCESS_REVOKE",
    "POLICY_VIOLATION", "SUSPICIOUS_ACCESS", "AUDIT_FAILURE",
)

PII_SENSITIVITY_LEVELS: Tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

DEFAULT_KEY_ROTATION_DAYS = 90
DEFAULT_SECRET_ROTATION_DAYS = 60
DPA_KENYA_REGULATORY_REFERENCE = "Data Protection Act 2019"


class DataEncryptionEngine:
    """Encryption + secrets + PII registry — DPA + CBK Cyber compliance."""

    def __init__(
        self,
        keys_path: Optional[Path] = None,
        secrets_path: Optional[Path] = None,
        pii_fields_path: Optional[Path] = None,
        events_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.keys_path = keys_path or base / "encryption_keys.json"
        self.secrets_path = secrets_path or base / "secrets_vault.json"
        self.pii_fields_path = pii_fields_path or base / "pii_fields.json"
        self.events_path = events_path or base / "security_events.json"

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

    def register_encryption_key(
        self, key_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("key_id", "key_name", "algorithm", "purpose"):
            if f not in key_data or not key_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if key_data["algorithm"] not in ENCRYPTION_ALGORITHMS:
            return {"registered": False,
                       "error": f"invalid_algorithm:{key_data['algorithm']}"}
        if key_data["purpose"] not in KEY_USAGE_PURPOSES:
            return {"registered": False,
                       "error": f"invalid_purpose:{key_data['purpose']}"}
        records = self._load(self.keys_path,
                                "encryption_keys", ("key_id",))
        if any(r.get("key_id") == key_data["key_id"] for r in records):
            return {"registered": False, "error": "duplicate_key_id"}
        record = {
            "key_id": key_data["key_id"],
            "key_name": key_data["key_name"],
            "algorithm": key_data["algorithm"],
            "purpose": key_data["purpose"],
            "hsm_backed": bool(key_data.get("hsm_backed", False)),
            "rotation_days": int(key_data.get(
                "rotation_days", DEFAULT_KEY_ROTATION_DAYS,
            )),
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
        ok = self._save(self.keys_path, records,
                          "encryption_keys", "key_id")
        return {"registered": ok, "key_id": key_data["key_id"]}

    def transition_key_state(
        self, key_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in KEY_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.keys_path,
                                "encryption_keys", ("key_id",))
        for r in records:
            if r.get("key_id") == key_id:
                current = r.get("state", "PENDING")
                allowed = ALLOWED_KEY_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                if new_state == "ACTIVE":
                    r["activated_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.keys_path, records,
                                  "encryption_keys", "key_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "key_not_found"}

    def register_secret(
        self, secret_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("secret_id", "secret_name", "secret_type", "vault_path"):
            if f not in secret_data or not secret_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if secret_data["secret_type"] not in SECRET_TYPES:
            return {"registered": False,
                       "error": f"invalid_secret_type:{secret_data['secret_type']}"}
        records = self._load(self.secrets_path,
                                "secrets_vault", ("secret_id",))
        if any(r.get("secret_id") == secret_data["secret_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_secret_id"}
        rotation_days = int(secret_data.get(
            "rotation_days", DEFAULT_SECRET_ROTATION_DAYS,
        ))
        next_rotation = (
            datetime.utcnow() + timedelta(days=rotation_days)
        ).isoformat()
        record = {
            "secret_id": secret_data["secret_id"],
            "secret_name": secret_data["secret_name"],
            "secret_type": secret_data["secret_type"],
            "vault_path": secret_data["vault_path"],
            "owner_team": secret_data.get("owner_team", ""),
            "rotation_days": rotation_days,
            "last_rotated_at": datetime.utcnow().isoformat(),
            "next_rotation_at": next_rotation,
            "rotation_count": 0,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.secrets_path, records,
                          "secrets_vault", "secret_id")
        return {"registered": ok, "secret_id": secret_data["secret_id"]}

    def rotate_secret(
        self, secret_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"rotated": False, "error": "actor_and_reason_required"}
        records = self._load(self.secrets_path,
                                "secrets_vault", ("secret_id",))
        for r in records:
            if r.get("secret_id") == secret_id:
                r["last_rotated_at"] = datetime.utcnow().isoformat()
                r["rotation_count"] = r.get("rotation_count", 0) + 1
                rotation_days = r.get(
                    "rotation_days", DEFAULT_SECRET_ROTATION_DAYS,
                )
                r["next_rotation_at"] = (
                    datetime.utcnow() + timedelta(days=rotation_days)
                ).isoformat()
                r.setdefault("rotation_history", []).append({
                    "at": datetime.utcnow().isoformat(),
                    "actor": actor,
                    "reason": reason,
                })
                ok = self._save(self.secrets_path, records,
                                  "secrets_vault", "secret_id")
                return {"rotated": ok, "rotation_count": r["rotation_count"]}
        return {"rotated": False, "error": "secret_not_found"}

    def register_pii_field(
        self, field_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("field_id", "table_name", "column_name",
                      "sensitivity_level"):
            if f not in field_data or not field_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if field_data["sensitivity_level"] not in PII_SENSITIVITY_LEVELS:
            return {"registered": False,
                       "error": f"invalid_sensitivity:{field_data['sensitivity_level']}"}
        records = self._load(self.pii_fields_path,
                                "pii_fields", ("field_id",))
        if any(r.get("field_id") == field_data["field_id"] for r in records):
            return {"registered": False, "error": "duplicate_field_id"}
        record = {
            "field_id": field_data["field_id"],
            "table_name": field_data["table_name"],
            "column_name": field_data["column_name"],
            "sensitivity_level": field_data["sensitivity_level"],
            "encryption_required": field_data["sensitivity_level"]
                                       in ("HIGH", "CRITICAL"),
            "encryption_key_id": field_data.get("encryption_key_id", ""),
            "regulatory_reference": DPA_KENYA_REGULATORY_REFERENCE,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.pii_fields_path, records,
                          "pii_fields", "field_id")
        return {"registered": ok, "field_id": field_data["field_id"]}

    def record_security_event(
        self, event_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("event_id", "event_type", "subject"):
            if f not in event_data or not event_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if event_data["event_type"] not in SECURITY_EVENT_TYPES:
            return {"recorded": False,
                       "error": f"invalid_event_type:{event_data['event_type']}"}
        records = self._load(self.events_path,
                                "security_events", ("event_id",))
        if any(r.get("event_id") == event_data["event_id"] for r in records):
            return {"recorded": False, "error": "duplicate_event_id"}
        record = {
            "event_id": event_data["event_id"],
            "event_type": event_data["event_type"],
            "subject": event_data["subject"],
            "details": event_data.get("details", ""),
            "severity": event_data.get("severity", "INFO"),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.events_path, records,
                          "security_events", "event_id")
        return {"recorded": ok, "event_id": event_data["event_id"]}

    def encryption_compliance_status(self) -> Dict[str, Any]:
        keys = self._load(self.keys_path,
                              "encryption_keys", ("key_id",))
        active_keys = [k for k in keys if k.get("state") == "ACTIVE"]
        hsm_backed = sum(1 for k in active_keys if k.get("hsm_backed"))
        pii = self._load(self.pii_fields_path, "pii_fields", ("field_id",))
        critical_pii = [f for f in pii
                              if f.get("sensitivity_level") == "CRITICAL"]
        encrypted_critical = sum(1 for f in critical_pii
                                          if f.get("encryption_key_id"))
        return {
            "total_keys": len(keys),
            "active_keys": len(active_keys),
            "hsm_backed_keys": hsm_backed,
            "hsm_coverage_pct": round(
                (hsm_backed / len(active_keys) * 100) if active_keys else 0,
                1,
            ),
            "pii_field_count": len(pii),
            "critical_pii_count": len(critical_pii),
            "critical_pii_encrypted_count": encrypted_critical,
            "critical_pii_coverage_pct": round(
                (encrypted_critical / len(critical_pii) * 100)
                if critical_pii else 100, 1,
            ),
            "regulatory_reference": DPA_KENYA_REGULATORY_REFERENCE,
        }

    def secret_rotation_due(self, within_days: int = 30) -> List[Dict[str, Any]]:
        records = self._load(self.secrets_path,
                                "secrets_vault", ("secret_id",))
        cutoff = (datetime.utcnow() + timedelta(days=within_days)).isoformat()
        due = [r for r in records
                  if r.get("next_rotation_at", "") <= cutoff]
        due.sort(key=lambda x: x.get("next_rotation_at", ""))
        return due


def _self_test() -> None:
    import tempfile

    assert ENCRYPTION_ALGORITHMS == ("AES_256_GCM", "AES_256_CBC",
                                            "RSA_4096", "ECDSA_P384")
    assert ALLOWED_KEY_TRANSITIONS["DESTROYED"] == ()
    assert "DATABASE_PASSWORD" in SECRET_TYPES
    assert "KEY_ROTATION" in SECURITY_EVENT_TYPES
    assert "CRITICAL" in PII_SENSITIVITY_LEVELS
    assert DEFAULT_KEY_ROTATION_DAYS == 90
    assert DEFAULT_SECRET_ROTATION_DAYS == 60
    assert DPA_KENYA_REGULATORY_REFERENCE == "Data Protection Act 2019"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = DataEncryptionEngine(
            keys_path=Path(tmpdir) / "k.json",
            secrets_path=Path(tmpdir) / "s.json",
            pii_fields_path=Path(tmpdir) / "p.json",
            events_path=Path(tmpdir) / "e.json",
        )
        # Key
        r = e.register_encryption_key(
            {"key_id": "KEY-MASTER-AES",
             "key_name": "Master AES key",
             "algorithm": "AES_256_GCM",
             "purpose": "DATA_AT_REST",
             "hsm_backed": True},
            actor="security", reason="DPA compliance",
        )
        assert r["registered"]
        # Invalid algo
        r = e.register_encryption_key(
            {"key_id": "X", "key_name": "Y", "algorithm": "DES",
             "purpose": "DATA_AT_REST"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid purpose
        r = e.register_encryption_key(
            {"key_id": "Y", "key_name": "Z",
             "algorithm": "AES_256_GCM", "purpose": "RANDOM"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Key transitions
        r = e.transition_key_state("KEY-MASTER-AES", "ACTIVE",
                                          actor="security",
                                          reason="ready")
        assert r["transitioned"]
        r = e.transition_key_state("KEY-MASTER-AES", "ROTATING",
                                          actor="security",
                                          reason="90 day")
        assert r["transitioned"]
        r = e.transition_key_state("KEY-MASTER-AES", "DEPRECATED",
                                          actor="security",
                                          reason="rotation")
        assert r["transitioned"]
        r = e.transition_key_state("KEY-MASTER-AES", "DESTROYED",
                                          actor="security",
                                          reason="zeroize")
        assert r["transitioned"]
        # DESTROYED is terminal
        r = e.transition_key_state("KEY-MASTER-AES", "ACTIVE",
                                          actor="security", reason="x")
        assert not r["transitioned"]

        # Secret
        r = e.register_secret(
            {"secret_id": "SEC-DB-PRIMARY",
             "secret_name": "Primary DB password",
             "secret_type": "DATABASE_PASSWORD",
             "vault_path": "/secrets/db/primary",
             "owner_team": "platform",
             "rotation_days": 60},
            actor="security", reason="initial",
        )
        assert r["registered"]
        # Invalid type
        r = e.register_secret(
            {"secret_id": "X", "secret_name": "Y",
             "secret_type": "WHATEVER", "vault_path": "/x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Rotate
        r = e.rotate_secret("SEC-DB-PRIMARY",
                                  actor="security", reason="quarterly")
        assert r["rotated"]
        assert r["rotation_count"] == 1

        # PII field
        r = e.register_pii_field(
            {"field_id": "PII-CUST-NIN",
             "table_name": "customers",
             "column_name": "national_id_number",
             "sensitivity_level": "CRITICAL",
             "encryption_key_id": "KEY-MASTER-AES"},
            actor="security", reason="DPA",
        )
        assert r["registered"]
        # Auto encryption_required for CRITICAL
        # Invalid sensitivity
        r = e.register_pii_field(
            {"field_id": "X", "table_name": "Y",
             "column_name": "Z", "sensitivity_level": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Security event
        r = e.record_security_event(
            {"event_id": "EVT-001", "event_type": "KEY_ROTATION",
             "subject": "KEY-MASTER-AES",
             "details": "Quarterly rotation"},
            actor="security",
        )
        assert r["recorded"]

        # Compliance status
        s = e.encryption_compliance_status()
        assert s["total_keys"] == 1
        assert s["pii_field_count"] == 1

        # Rotation due
        d = e.secret_rotation_due(within_days=120)
        assert len(d) >= 1

    print("  ✅ it_data_encryption self-test PASS")


if __name__ == "__main__":
    _self_test()

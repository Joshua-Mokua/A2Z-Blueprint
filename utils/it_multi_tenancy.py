"""
================================================================================
A2Z MIS 360 — Standard #298: Multi-Tenancy & White Labeling
================================================================================

Risk classification: Cat C (tenant isolation + branding registry)

Tenant-scoped data isolation, configurable branding, tenant-specific
feature flags. Designed-but-deferred per v10.0 plan.

Public API:
    register_tenant(tenant_data, actor, reason)
    transition_tenant_state(tenant_id, new_state, actor, reason)
    register_branding_profile(branding_data, actor, reason)
    register_feature_flag(flag_data, actor, reason)
    set_tenant_feature(tenant_id, feature_id, enabled, actor, reason)
    tenant_isolation_check(tenant_id) -> Dict
    enabled_features_for_tenant(tenant_id) -> List

TENANT_STATES byte-for-byte (5):
    PROVISIONING, ACTIVE, SUSPENDED, OFFBOARDING, ARCHIVED

ALLOWED_TENANT_TRANSITIONS (Rule 4):
    PROVISIONING → ACTIVE | ARCHIVED
    ACTIVE       → SUSPENDED | OFFBOARDING
    SUSPENDED    → ACTIVE | OFFBOARDING
    OFFBOARDING  → ARCHIVED
    ARCHIVED     → ()

ISOLATION_MODELS byte-for-byte (3):
    DEDICATED_DATABASE, SHARED_DB_DEDICATED_SCHEMA, SHARED_DB_SHARED_SCHEMA

BRANDING_ELEMENTS byte-for-byte (6):
    LOGO_URL, PRIMARY_COLOR, SECONDARY_COLOR, FAVICON_URL,
    EMAIL_SENDER, SUPPORT_PHONE

FLAG_TYPES byte-for-byte (3): BOOLEAN, PERCENTAGE_ROLLOUT, ALLOWLIST

FEATURE_FLAG_STATES byte-for-byte (3): ACTIVE, DEPRECATED, ARCHIVED

ALLOWED_FLAG_TRANSITIONS (Rule 4):
    ACTIVE     → DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TENANT_STATES: Tuple[str, ...] = (
    "PROVISIONING", "ACTIVE", "SUSPENDED", "OFFBOARDING", "ARCHIVED",
)

ALLOWED_TENANT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROVISIONING": ("ACTIVE", "ARCHIVED"),
    "ACTIVE":       ("SUSPENDED", "OFFBOARDING"),
    "SUSPENDED":    ("ACTIVE", "OFFBOARDING"),
    "OFFBOARDING":  ("ARCHIVED",),
    "ARCHIVED":     (),
}

ISOLATION_MODELS: Tuple[str, ...] = (
    "DEDICATED_DATABASE",
    "SHARED_DB_DEDICATED_SCHEMA",
    "SHARED_DB_SHARED_SCHEMA",
)

BRANDING_ELEMENTS: Tuple[str, ...] = (
    "LOGO_URL", "PRIMARY_COLOR", "SECONDARY_COLOR",
    "FAVICON_URL", "EMAIL_SENDER", "SUPPORT_PHONE",
)

FLAG_TYPES: Tuple[str, ...] = (
    "BOOLEAN", "PERCENTAGE_ROLLOUT", "ALLOWLIST",
)

FEATURE_FLAG_STATES: Tuple[str, ...] = ("ACTIVE", "DEPRECATED", "ARCHIVED")

ALLOWED_FLAG_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":     ("DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}


class MultiTenancyEngine:
    """Tenant + branding + feature flag registry — isolation enforcement."""

    def __init__(
        self,
        tenants_path: Optional[Path] = None,
        branding_path: Optional[Path] = None,
        flags_path: Optional[Path] = None,
        tenant_features_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.tenants_path = tenants_path or base / "mt_tenants.json"
        self.branding_path = branding_path or base / "mt_branding.json"
        self.flags_path = flags_path or base / "mt_feature_flags.json"
        self.tenant_features_path = (
            tenant_features_path or base / "mt_tenant_features.json"
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

    def register_tenant(
        self, tenant_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("tenant_id", "tenant_name", "isolation_model"):
            if f not in tenant_data or not tenant_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if tenant_data["isolation_model"] not in ISOLATION_MODELS:
            return {"registered": False,
                       "error": f"invalid_isolation_model:{tenant_data['isolation_model']}"}
        records = self._load(self.tenants_path,
                                "mt_tenants", ("tenant_id",))
        if any(r.get("tenant_id") == tenant_data["tenant_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_tenant_id"}
        record = {
            "tenant_id": tenant_data["tenant_id"],
            "tenant_name": tenant_data["tenant_name"],
            "isolation_model": tenant_data["isolation_model"],
            "database_url_ref": tenant_data.get("database_url_ref", ""),
            "schema_name": tenant_data.get("schema_name", ""),
            "domain": tenant_data.get("domain", ""),
            "state": "PROVISIONING",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PROVISIONING", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.tenants_path, records,
                          "mt_tenants", "tenant_id")
        return {"registered": ok, "tenant_id": tenant_data["tenant_id"]}

    def transition_tenant_state(
        self, tenant_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in TENANT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.tenants_path,
                                "mt_tenants", ("tenant_id",))
        for r in records:
            if r.get("tenant_id") == tenant_id:
                current = r.get("state", "PROVISIONING")
                allowed = ALLOWED_TENANT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.tenants_path, records,
                                  "mt_tenants", "tenant_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "tenant_not_found"}

    def register_branding_profile(
        self, branding_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("profile_id", "tenant_id", "elements"):
            if f not in branding_data or branding_data[f] in (None, "", {}):
                return {"registered": False, "error": f"missing_field:{f}"}
        elements = branding_data["elements"]
        if not isinstance(elements, dict):
            return {"registered": False, "error": "elements_must_be_dict"}
        for k in elements:
            if k not in BRANDING_ELEMENTS:
                return {"registered": False,
                           "error": f"invalid_branding_element:{k}"}
        # Verify tenant exists
        tenants = self._load(self.tenants_path,
                                  "mt_tenants", ("tenant_id",))
        if not any(t.get("tenant_id") == branding_data["tenant_id"]
                       for t in tenants):
            return {"registered": False, "error": "tenant_not_found"}
        records = self._load(self.branding_path,
                                "mt_branding", ("profile_id",))
        if any(r.get("profile_id") == branding_data["profile_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_profile_id"}
        record = {
            "profile_id": branding_data["profile_id"],
            "tenant_id": branding_data["tenant_id"],
            "elements": dict(elements),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.branding_path, records,
                          "mt_branding", "profile_id")
        return {"registered": ok, "profile_id": branding_data["profile_id"]}

    def register_feature_flag(
        self, flag_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("flag_id", "flag_name", "flag_type", "default_value"):
            if f not in flag_data or flag_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if flag_data["flag_type"] not in FLAG_TYPES:
            return {"registered": False,
                       "error": f"invalid_flag_type:{flag_data['flag_type']}"}
        records = self._load(self.flags_path,
                                "mt_feature_flags", ("flag_id",))
        if any(r.get("flag_id") == flag_data["flag_id"] for r in records):
            return {"registered": False, "error": "duplicate_flag_id"}
        record = {
            "flag_id": flag_data["flag_id"],
            "flag_name": flag_data["flag_name"],
            "flag_type": flag_data["flag_type"],
            "default_value": flag_data["default_value"],
            "description": flag_data.get("description", ""),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.flags_path, records,
                          "mt_feature_flags", "flag_id")
        return {"registered": ok, "flag_id": flag_data["flag_id"]}

    def set_tenant_feature(
        self, tenant_id: str, feature_id: str, enabled: Any,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"set": False, "error": "actor_and_reason_required"}
        # Verify tenant + flag exist
        tenants = self._load(self.tenants_path,
                                  "mt_tenants", ("tenant_id",))
        if not any(t.get("tenant_id") == tenant_id for t in tenants):
            return {"set": False, "error": "tenant_not_found"}
        flags = self._load(self.flags_path,
                                "mt_feature_flags", ("flag_id",))
        flag = next((f for f in flags if f.get("flag_id") == feature_id),
                          None)
        if flag is None:
            return {"set": False, "error": "flag_not_found"}
        if flag.get("state") == "ARCHIVED":
            return {"set": False, "error": "flag_archived"}
        records = self._load(self.tenant_features_path,
                                "mt_tenant_features",
                                ("tenant_id", "feature_id"))
        for r in records:
            if (r.get("tenant_id") == tenant_id
                  and r.get("feature_id") == feature_id):
                r["enabled"] = enabled
                r["set_by"] = actor
                r["set_at"] = datetime.utcnow().isoformat()
                r["set_reason"] = reason
                ok = self._save(self.tenant_features_path, records,
                                  "mt_tenant_features", "tenant_id")
                return {"set": ok, "updated": True}
        records.append({
            "tenant_id": tenant_id,
            "feature_id": feature_id,
            "enabled": enabled,
            "set_by": actor,
            "set_at": datetime.utcnow().isoformat(),
            "set_reason": reason,
        })
        ok = self._save(self.tenant_features_path, records,
                          "mt_tenant_features", "tenant_id")
        return {"set": ok, "created": True}

    def tenant_isolation_check(self, tenant_id: str) -> Dict[str, Any]:
        tenants = self._load(self.tenants_path,
                                  "mt_tenants", ("tenant_id",))
        tenant = next((t for t in tenants
                              if t.get("tenant_id") == tenant_id), None)
        if tenant is None:
            return {"found": False, "error": "tenant_not_found"}
        model = tenant.get("isolation_model", "")
        # Check that DB ref / schema is set per model
        violations = []
        if model == "DEDICATED_DATABASE":
            if not tenant.get("database_url_ref"):
                violations.append("missing_database_url_ref")
        elif model == "SHARED_DB_DEDICATED_SCHEMA":
            if not tenant.get("schema_name"):
                violations.append("missing_schema_name")
        return {
            "found": True,
            "tenant_id": tenant_id,
            "isolation_model": model,
            "state": tenant["state"],
            "violations": violations,
            "isolation_valid": len(violations) == 0,
        }

    def enabled_features_for_tenant(
        self, tenant_id: str,
    ) -> List[Dict[str, Any]]:
        tenant_features = self._load(self.tenant_features_path,
                                              "mt_tenant_features",
                                              ("tenant_id", "feature_id"))
        return [r for r in tenant_features
                  if r.get("tenant_id") == tenant_id
                  and r.get("enabled")]


def _self_test() -> None:
    import tempfile

    assert "PROVISIONING" in TENANT_STATES
    assert ALLOWED_TENANT_TRANSITIONS["ARCHIVED"] == ()
    assert "DEDICATED_DATABASE" in ISOLATION_MODELS
    assert "LOGO_URL" in BRANDING_ELEMENTS
    assert "BOOLEAN" in FLAG_TYPES
    assert ALLOWED_FLAG_TRANSITIONS["ARCHIVED"] == ()

    with tempfile.TemporaryDirectory() as tmpdir:
        e = MultiTenancyEngine(
            tenants_path=Path(tmpdir) / "t.json",
            branding_path=Path(tmpdir) / "b.json",
            flags_path=Path(tmpdir) / "f.json",
            tenant_features_path=Path(tmpdir) / "tf.json",
        )
        # Tenant
        r = e.register_tenant(
            {"tenant_id": "TENANT-EBK",
             "tenant_name": "Ecobank Kenya",
             "isolation_model": "DEDICATED_DATABASE",
             "database_url_ref": "vault:/tenants/ebk/db_url",
             "domain": "ebk.a2zmis.com"},
            actor="cto", reason="primary client",
        )
        assert r["registered"]
        # Invalid model
        r = e.register_tenant(
            {"tenant_id": "X", "tenant_name": "Y",
             "isolation_model": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Tenant transitions
        r = e.transition_tenant_state("TENANT-EBK", "ACTIVE",
                                            actor="cto",
                                            reason="provisioned")
        assert r["transitioned"]
        r = e.transition_tenant_state("TENANT-EBK", "SUSPENDED",
                                            actor="cto",
                                            reason="payment issue")
        assert r["transitioned"]
        r = e.transition_tenant_state("TENANT-EBK", "ACTIVE",
                                            actor="cto",
                                            reason="resolved")
        assert r["transitioned"]
        # Cannot SUSPENDED → ARCHIVED directly
        r = e.transition_tenant_state("TENANT-EBK", "SUSPENDED",
                                            actor="cto",
                                            reason="x")
        assert r["transitioned"]
        r = e.transition_tenant_state("TENANT-EBK", "ARCHIVED",
                                            actor="cto", reason="x")
        assert not r["transitioned"]

        # Branding
        r = e.register_branding_profile(
            {"profile_id": "BRD-EBK",
             "tenant_id": "TENANT-EBK",
             "elements": {
                 "LOGO_URL": "https://ebk.a2zmis.com/logo.svg",
                 "PRIMARY_COLOR": "#003F87",
             }},
            actor="cto", reason="initial branding",
        )
        assert r["registered"]
        # Invalid element
        r = e.register_branding_profile(
            {"profile_id": "X", "tenant_id": "TENANT-EBK",
             "elements": {"LOGO_URL": "x", "INVALID": "y"}},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Tenant not found
        r = e.register_branding_profile(
            {"profile_id": "Y", "tenant_id": "NOPE",
             "elements": {"LOGO_URL": "x"}},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Feature flag
        r = e.register_feature_flag(
            {"flag_id": "FLAG-NEW-DASHBOARD",
             "flag_name": "New dashboard rollout",
             "flag_type": "BOOLEAN",
             "default_value": False},
            actor="product", reason="phased rollout",
        )
        assert r["registered"]
        # Invalid type
        r = e.register_feature_flag(
            {"flag_id": "X", "flag_name": "Y",
             "flag_type": "WHATEVER", "default_value": False},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Tenant feature
        r = e.set_tenant_feature(
            "TENANT-EBK", "FLAG-NEW-DASHBOARD", True,
            actor="product", reason="opt-in",
        )
        assert r["set"]
        # Update
        r = e.set_tenant_feature(
            "TENANT-EBK", "FLAG-NEW-DASHBOARD", False,
            actor="product", reason="rollback",
        )
        assert r["set"] and r["updated"]
        # Tenant not found
        r = e.set_tenant_feature(
            "NOPE", "FLAG-NEW-DASHBOARD", True,
            actor="x", reason="x",
        )
        assert not r["set"]
        # Flag not found
        r = e.set_tenant_feature(
            "TENANT-EBK", "FLAG-NOPE", True,
            actor="x", reason="x",
        )
        assert not r["set"]

        # Isolation check
        i = e.tenant_isolation_check("TENANT-EBK")
        assert i["found"]
        assert i["isolation_valid"]

        # Schema-based tenant missing schema
        e.register_tenant(
            {"tenant_id": "T2", "tenant_name": "Other",
             "isolation_model": "SHARED_DB_DEDICATED_SCHEMA"},
            actor="cto", reason="x",
        )
        i = e.tenant_isolation_check("T2")
        assert not i["isolation_valid"]
        assert "missing_schema_name" in i["violations"]

        # Enabled features (current is False, so should be empty)
        feats = e.enabled_features_for_tenant("TENANT-EBK")
        assert len(feats) == 0

    print("  ✅ it_multi_tenancy self-test PASS")


if __name__ == "__main__":
    _self_test()

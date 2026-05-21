"""
================================================================================
A2Z MIS 360 — Standard #295: API Gateway & Developer Portal
================================================================================

Risk classification: Cat C (API gateway config + developer onboarding)

Kong/Tyk API gateway, OAuth2/OpenID Connect, rate limiting, API versioning,
developer portal with OpenAPI docs.

Public API:
    register_api(api_data, actor, reason)
    transition_api_state(api_id, new_state, actor, reason)
    register_consumer(consumer_data, actor, reason)
    issue_api_key(consumer_id, api_id, actor, reason)
    revoke_api_key(api_key_id, actor, reason)
    register_rate_limit(limit_data, actor)
    record_api_call(api_id, consumer_id, actor)
    api_usage_summary(api_id) -> Dict
    list_consumer_apis(consumer_id) -> List

API_AUTH_TYPES byte-for-byte (4):
    OAUTH2, API_KEY, JWT, MUTUAL_TLS

API_STATES byte-for-byte (5):
    DRAFT, IN_REVIEW, ACTIVE, DEPRECATED, RETIRED

ALLOWED_API_TRANSITIONS (Rule 4):
    DRAFT       → IN_REVIEW | RETIRED
    IN_REVIEW   → ACTIVE | DRAFT | RETIRED
    ACTIVE      → DEPRECATED | RETIRED
    DEPRECATED  → RETIRED
    RETIRED     → ()

API_KEY_STATES byte-for-byte (3): ACTIVE, REVOKED, EXPIRED

CONSUMER_TYPES byte-for-byte (4):
    INTERNAL, PARTNER, PUBLIC, MOBILE_APP

RATE_LIMIT_WINDOWS byte-for-byte (4):
    PER_SECOND, PER_MINUTE, PER_HOUR, PER_DAY

DEFAULT_RATE_LIMITS_PER_MINUTE byte-for-byte:
    INTERNAL=10000, PARTNER=1000, PUBLIC=100, MOBILE_APP=300

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


API_AUTH_TYPES: Tuple[str, ...] = (
    "OAUTH2", "API_KEY", "JWT", "MUTUAL_TLS",
)

API_STATES: Tuple[str, ...] = (
    "DRAFT", "IN_REVIEW", "ACTIVE", "DEPRECATED", "RETIRED",
)

ALLOWED_API_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("IN_REVIEW", "RETIRED"),
    "IN_REVIEW":  ("ACTIVE", "DRAFT", "RETIRED"),
    "ACTIVE":     ("DEPRECATED", "RETIRED"),
    "DEPRECATED": ("RETIRED",),
    "RETIRED":    (),
}

API_KEY_STATES: Tuple[str, ...] = ("ACTIVE", "REVOKED", "EXPIRED")

CONSUMER_TYPES: Tuple[str, ...] = (
    "INTERNAL", "PARTNER", "PUBLIC", "MOBILE_APP",
)

RATE_LIMIT_WINDOWS: Tuple[str, ...] = (
    "PER_SECOND", "PER_MINUTE", "PER_HOUR", "PER_DAY",
)

DEFAULT_RATE_LIMITS_PER_MINUTE: Dict[str, int] = {
    "INTERNAL": 10000,
    "PARTNER": 1000,
    "PUBLIC": 100,
    "MOBILE_APP": 300,
}


class APIGatewayDeveloperPortalEngine:
    """API gateway + consumer + rate-limit + usage tracking."""

    def __init__(
        self,
        apis_path: Optional[Path] = None,
        consumers_path: Optional[Path] = None,
        api_keys_path: Optional[Path] = None,
        rate_limits_path: Optional[Path] = None,
        usage_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.apis_path = apis_path or base / "apigw_apis.json"
        self.consumers_path = consumers_path or base / "apigw_consumers.json"
        self.api_keys_path = api_keys_path or base / "apigw_api_keys.json"
        self.rate_limits_path = rate_limits_path or base / "apigw_rate_limits.json"
        self.usage_path = usage_path or base / "apigw_usage.json"

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

    def register_api(
        self, api_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("api_id", "api_name", "version", "auth_type",
                      "openapi_uri"):
            if f not in api_data or not api_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if api_data["auth_type"] not in API_AUTH_TYPES:
            return {"registered": False,
                       "error": f"invalid_auth_type:{api_data['auth_type']}"}
        records = self._load(self.apis_path, "apigw_apis", ("api_id",))
        if any(r.get("api_id") == api_data["api_id"] for r in records):
            return {"registered": False, "error": "duplicate_api_id"}
        record = {
            "api_id": api_data["api_id"],
            "api_name": api_data["api_name"],
            "version": api_data["version"],
            "auth_type": api_data["auth_type"],
            "openapi_uri": api_data["openapi_uri"],
            "base_path": api_data.get("base_path", ""),
            "owner_team": api_data.get("owner_team", ""),
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
        ok = self._save(self.apis_path, records, "apigw_apis", "api_id")
        return {"registered": ok, "api_id": api_data["api_id"]}

    def transition_api_state(
        self, api_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in API_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.apis_path, "apigw_apis", ("api_id",))
        for r in records:
            if r.get("api_id") == api_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_API_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.apis_path, records,
                                  "apigw_apis", "api_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "api_not_found"}

    def register_consumer(
        self, consumer_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("consumer_id", "consumer_name", "consumer_type",
                      "contact_email"):
            if f not in consumer_data or not consumer_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if consumer_data["consumer_type"] not in CONSUMER_TYPES:
            return {"registered": False,
                       "error": f"invalid_consumer_type:{consumer_data['consumer_type']}"}
        records = self._load(self.consumers_path,
                                "apigw_consumers", ("consumer_id",))
        if any(r.get("consumer_id") == consumer_data["consumer_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_consumer_id"}
        record = {
            "consumer_id": consumer_data["consumer_id"],
            "consumer_name": consumer_data["consumer_name"],
            "consumer_type": consumer_data["consumer_type"],
            "contact_email": consumer_data["contact_email"],
            "default_rate_limit_per_minute": (
                DEFAULT_RATE_LIMITS_PER_MINUTE[consumer_data["consumer_type"]]
            ),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.consumers_path, records,
                          "apigw_consumers", "consumer_id")
        return {"registered": ok,
                  "consumer_id": consumer_data["consumer_id"],
                  "default_rate_limit_per_minute":
                      DEFAULT_RATE_LIMITS_PER_MINUTE[
                          consumer_data["consumer_type"]
                      ]}

    def issue_api_key(
        self, consumer_id: str, api_id: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"issued": False, "error": "actor_and_reason_required"}
        # Verify consumer + API exist
        consumers = self._load(self.consumers_path,
                                     "apigw_consumers", ("consumer_id",))
        if not any(c.get("consumer_id") == consumer_id for c in consumers):
            return {"issued": False, "error": "consumer_not_found"}
        apis = self._load(self.apis_path, "apigw_apis", ("api_id",))
        api = next((a for a in apis if a.get("api_id") == api_id), None)
        if api is None:
            return {"issued": False, "error": "api_not_found"}
        if api["state"] != "ACTIVE":
            return {"issued": False, "error": "api_not_active"}
        records = self._load(self.api_keys_path,
                                "apigw_api_keys", ("api_key_id",))
        # Check for existing active key for same consumer+api
        if any(k.get("consumer_id") == consumer_id
                  and k.get("api_id") == api_id
                  and k.get("state") == "ACTIVE"
                  for k in records):
            return {"issued": False, "error": "active_key_exists"}
        key_id = (f"AK-{consumer_id}-{api_id}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "api_key_id": key_id,
            "consumer_id": consumer_id,
            "api_id": api_id,
            "state": "ACTIVE",
            "issued_by": actor,
            "issued_at": datetime.utcnow().isoformat(),
            "issue_reason": reason,
        })
        ok = self._save(self.api_keys_path, records,
                          "apigw_api_keys", "api_key_id")
        return {"issued": ok, "api_key_id": key_id}

    def revoke_api_key(
        self, api_key_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"revoked": False, "error": "actor_and_reason_required"}
        records = self._load(self.api_keys_path,
                                "apigw_api_keys", ("api_key_id",))
        for r in records:
            if r.get("api_key_id") == api_key_id:
                if r["state"] != "ACTIVE":
                    return {"revoked": False,
                               "error": f"key_not_active:{r['state']}"}
                r["state"] = "REVOKED"
                r["revoked_by"] = actor
                r["revoked_at"] = datetime.utcnow().isoformat()
                r["revocation_reason"] = reason
                ok = self._save(self.api_keys_path, records,
                                  "apigw_api_keys", "api_key_id")
                return {"revoked": ok}
        return {"revoked": False, "error": "key_not_found"}

    def register_rate_limit(
        self, limit_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("limit_id", "consumer_id", "api_id",
                      "window", "max_requests"):
            if f not in limit_data or limit_data[f] is None or limit_data[f] == "":
                return {"registered": False, "error": f"missing_field:{f}"}
        if limit_data["window"] not in RATE_LIMIT_WINDOWS:
            return {"registered": False,
                       "error": f"invalid_window:{limit_data['window']}"}
        try:
            mr = int(limit_data["max_requests"])
        except Exception:
            return {"registered": False,
                       "error": "max_requests_not_numeric"}
        if mr <= 0:
            return {"registered": False,
                       "error": "max_requests_must_be_positive"}
        records = self._load(self.rate_limits_path,
                                "apigw_rate_limits", ("limit_id",))
        if any(r.get("limit_id") == limit_data["limit_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_limit_id"}
        record = {
            "limit_id": limit_data["limit_id"],
            "consumer_id": limit_data["consumer_id"],
            "api_id": limit_data["api_id"],
            "window": limit_data["window"],
            "max_requests": mr,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.rate_limits_path, records,
                          "apigw_rate_limits", "limit_id")
        return {"registered": ok, "limit_id": limit_data["limit_id"]}

    def record_api_call(
        self, api_id: str, consumer_id: str, actor: str,
        latency_ms: Optional[int] = None,
        status_code: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        records = self._load(self.usage_path,
                                "apigw_usage", ("call_id",))
        call_id = (f"CALL-{api_id}-{consumer_id}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "call_id": call_id,
            "api_id": api_id,
            "consumer_id": consumer_id,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.usage_path, records,
                          "apigw_usage", "call_id")
        return {"recorded": ok, "call_id": call_id}

    def api_usage_summary(self, api_id: str) -> Dict[str, Any]:
        records = self._load(self.usage_path,
                                "apigw_usage", ("call_id",))
        api_calls = [r for r in records if r.get("api_id") == api_id]
        success = sum(1 for c in api_calls
                            if c.get("status_code")
                            and 200 <= c["status_code"] < 400)
        latencies = [c["latency_ms"] for c in api_calls
                          if c.get("latency_ms") is not None]
        avg_latency = (sum(latencies) / len(latencies)) if latencies else 0
        unique_consumers = len({c["consumer_id"] for c in api_calls})
        return {
            "api_id": api_id,
            "total_calls": len(api_calls),
            "success_calls": success,
            "success_rate_pct": round(
                success / len(api_calls) * 100, 2,
            ) if api_calls else 0,
            "avg_latency_ms": round(avg_latency, 2),
            "unique_consumers": unique_consumers,
        }

    def list_consumer_apis(
        self, consumer_id: str,
    ) -> List[Dict[str, Any]]:
        keys = self._load(self.api_keys_path,
                              "apigw_api_keys", ("api_key_id",))
        consumer_keys = [k for k in keys
                                if k.get("consumer_id") == consumer_id
                                and k.get("state") == "ACTIVE"]
        apis = self._load(self.apis_path, "apigw_apis", ("api_id",))
        api_ids = {k["api_id"] for k in consumer_keys}
        return [a for a in apis if a.get("api_id") in api_ids]


def _self_test() -> None:
    import tempfile

    assert "OAUTH2" in API_AUTH_TYPES
    assert ALLOWED_API_TRANSITIONS["RETIRED"] == ()
    assert "INTERNAL" in CONSUMER_TYPES
    assert DEFAULT_RATE_LIMITS_PER_MINUTE["INTERNAL"] == 10000
    assert DEFAULT_RATE_LIMITS_PER_MINUTE["PUBLIC"] == 100

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = APIGatewayDeveloperPortalEngine(
            apis_path=Path(tmpdir) / "a.json",
            consumers_path=Path(tmpdir) / "c.json",
            api_keys_path=Path(tmpdir) / "k.json",
            rate_limits_path=Path(tmpdir) / "rl.json",
            usage_path=Path(tmpdir) / "u.json",
        )
        # Test 1: register API
        r = engine.register_api(
            {"api_id": "API-CUST-360",
             "api_name": "Customer 360 API",
             "version": "v1",
             "auth_type": "OAUTH2",
             "openapi_uri": "https://api.bank/customer-360/openapi.json",
             "base_path": "/v1/customer-360"},
            actor="api_lead", reason="customer 360 launch",
        )
        assert r["registered"]
        # Test 2: invalid auth type
        r = engine.register_api(
            {"api_id": "X", "api_name": "X", "version": "v1",
             "auth_type": "BASIC_AUTH",
             "openapi_uri": "x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: API state transitions
        r = engine.transition_api_state(
            "API-CUST-360", "IN_REVIEW",
            actor="api_lead", reason="security review",
        )
        assert r["transitioned"]
        r = engine.transition_api_state(
            "API-CUST-360", "ACTIVE",
            actor="api_lead", reason="approved + deployed",
        )
        assert r["transitioned"]
        # Test 4: invalid transition
        r = engine.transition_api_state(
            "API-CUST-360", "DRAFT",
            actor="x", reason="x",
        )
        assert not r["transitioned"]
        # Test 5: consumer
        r = engine.register_consumer(
            {"consumer_id": "CONS-MOBILE",
             "consumer_name": "Mobile Banking App",
             "consumer_type": "MOBILE_APP",
             "contact_email": "mobile-team@bank.local"},
            actor="api_lead", reason="mobile app onboarding",
        )
        assert r["registered"]
        assert r["default_rate_limit_per_minute"] == 300
        # Test 6: invalid consumer type
        r = engine.register_consumer(
            {"consumer_id": "X", "consumer_name": "X",
             "consumer_type": "GOVERNMENT", "contact_email": "x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 7: issue API key
        r = engine.issue_api_key(
            "CONS-MOBILE", "API-CUST-360",
            actor="api_lead", reason="mobile production access",
        )
        assert r["issued"]
        key_id = r["api_key_id"]
        # Test 8: duplicate active key
        r = engine.issue_api_key(
            "CONS-MOBILE", "API-CUST-360",
            actor="api_lead", reason="x",
        )
        assert not r["issued"]
        # Test 9: API not active
        engine.register_api(
            {"api_id": "API-DRAFT",
             "api_name": "Draft API",
             "version": "v1",
             "auth_type": "API_KEY",
             "openapi_uri": "x"},
            actor="api_lead", reason="r",
        )
        r = engine.issue_api_key(
            "CONS-MOBILE", "API-DRAFT",
            actor="api_lead", reason="x",
        )
        assert not r["issued"]
        # Test 10: revoke key
        r = engine.revoke_api_key(
            key_id, actor="api_lead", reason="rotation",
        )
        assert r["revoked"]
        # Test 11: cannot revoke twice
        r = engine.revoke_api_key(
            key_id, actor="api_lead", reason="x",
        )
        assert not r["revoked"]
        # Test 12: rate limit
        r = engine.register_rate_limit(
            {"limit_id": "RL-MOBILE-360",
             "consumer_id": "CONS-MOBILE",
             "api_id": "API-CUST-360",
             "window": "PER_MINUTE",
             "max_requests": 500},
            actor="api_lead",
        )
        assert r["registered"]
        # Test 13: invalid window
        r = engine.register_rate_limit(
            {"limit_id": "X", "consumer_id": "CONS-MOBILE",
             "api_id": "API-CUST-360",
             "window": "PER_LIFETIME", "max_requests": 100},
            actor="x",
        )
        assert not r["registered"]
        # Test 14: invalid max_requests
        r = engine.register_rate_limit(
            {"limit_id": "X", "consumer_id": "CONS-MOBILE",
             "api_id": "API-CUST-360",
             "window": "PER_MINUTE", "max_requests": 0},
            actor="x",
        )
        assert not r["registered"]
        # Test 15: usage tracking
        for _ in range(10):
            engine.record_api_call(
                "API-CUST-360", "CONS-MOBILE",
                actor="gateway",
                latency_ms=120, status_code=200,
            )
        engine.record_api_call(
            "API-CUST-360", "CONS-MOBILE",
            actor="gateway", latency_ms=300, status_code=500,
        )
        # Test 16: usage summary
        s = engine.api_usage_summary("API-CUST-360")
        assert s["total_calls"] == 11
        assert s["success_calls"] == 10
        assert s["unique_consumers"] == 1
        assert s["success_rate_pct"] > 90
        # Test 17: consumer-apis (after key was revoked, should be empty)
        consumer_apis = engine.list_consumer_apis("CONS-MOBILE")
        assert len(consumer_apis) == 0
        # Re-issue then check
        engine.issue_api_key(
            "CONS-MOBILE", "API-CUST-360",
            actor="api_lead", reason="re-issue",
        )
        consumer_apis = engine.list_consumer_apis("CONS-MOBILE")
        assert len(consumer_apis) == 1

    print("  ✅ api_gateway_developer_portal self-test PASS")


if __name__ == "__main__":
    _self_test()

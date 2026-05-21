"""
================================================================================
A2Z MIS 360 — Standard #295: API Gateway & Developer Portal
================================================================================

Risk classification: Cat C (API gateway management + rate limiting)

Kong/Tyk API gateway, OAuth2/OpenID Connect, rate limiting, API versioning,
developer portal with OpenAPI docs.

Public API:
    register_api(api_data, actor, reason)
    transition_api_state(api_id, new_state, actor, reason)
    register_api_key(key_data, actor, reason)
    register_rate_limit_policy(policy_data, actor, reason)
    register_developer(dev_data, actor)
    record_api_call(call_data, actor)
    rate_limit_check(api_id, key_id) -> Dict
    api_usage_summary(api_id) -> Dict

API_VERSION_STATES byte-for-byte (5):
    DEVELOPMENT, BETA, GA, DEPRECATED, RETIRED

ALLOWED_API_TRANSITIONS (Rule 4):
    DEVELOPMENT → BETA | RETIRED
    BETA        → GA | RETIRED
    GA          → DEPRECATED | RETIRED
    DEPRECATED  → RETIRED
    RETIRED     → ()

RATE_LIMIT_WINDOWS byte-for-byte (4): SECOND, MINUTE, HOUR, DAY

AUTH_SCHEMES byte-for-byte (4):
    OAUTH2_BEARER, OPENID_CONNECT, API_KEY, MUTUAL_TLS

API_KEY_STATES byte-for-byte (4): ACTIVE, REVOKED, EXPIRED, PENDING

DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_RATE_LIMIT_BURST_FACTOR = 2

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


API_VERSION_STATES: Tuple[str, ...] = (
    "DEVELOPMENT", "BETA", "GA", "DEPRECATED", "RETIRED",
)

ALLOWED_API_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DEVELOPMENT": ("BETA", "RETIRED"),
    "BETA":        ("GA", "RETIRED"),
    "GA":          ("DEPRECATED", "RETIRED"),
    "DEPRECATED":  ("RETIRED",),
    "RETIRED":     (),
}

RATE_LIMIT_WINDOWS: Tuple[str, ...] = ("SECOND", "MINUTE", "HOUR", "DAY")

AUTH_SCHEMES: Tuple[str, ...] = (
    "OAUTH2_BEARER", "OPENID_CONNECT", "API_KEY", "MUTUAL_TLS",
)

API_KEY_STATES: Tuple[str, ...] = (
    "ACTIVE", "REVOKED", "EXPIRED", "PENDING",
)

DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_RATE_LIMIT_BURST_FACTOR = 2


class APIGatewayEngine:
    """API gateway + developer portal — versioning, auth, rate limits."""

    def __init__(
        self,
        apis_path: Optional[Path] = None,
        keys_path: Optional[Path] = None,
        policies_path: Optional[Path] = None,
        developers_path: Optional[Path] = None,
        calls_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.apis_path = apis_path or base / "api_gateway_apis.json"
        self.keys_path = keys_path or base / "api_gateway_keys.json"
        self.policies_path = (
            policies_path or base / "api_gateway_policies.json"
        )
        self.developers_path = (
            developers_path or base / "api_gateway_developers.json"
        )
        self.calls_path = calls_path or base / "api_gateway_calls.json"

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
        for f in ("api_id", "api_name", "version", "auth_scheme",
                      "base_path"):
            if f not in api_data or not api_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if api_data["auth_scheme"] not in AUTH_SCHEMES:
            return {"registered": False,
                       "error": f"invalid_auth_scheme:{api_data['auth_scheme']}"}
        records = self._load(self.apis_path, "api_gateway_apis", ("api_id",))
        if any(r.get("api_id") == api_data["api_id"] for r in records):
            return {"registered": False, "error": "duplicate_api_id"}
        record = {
            "api_id": api_data["api_id"],
            "api_name": api_data["api_name"],
            "version": api_data["version"],
            "auth_scheme": api_data["auth_scheme"],
            "base_path": api_data["base_path"],
            "owner_team": api_data.get("owner_team", ""),
            "openapi_spec_url": api_data.get("openapi_spec_url", ""),
            "rate_limit_policy_id": api_data.get("rate_limit_policy_id", ""),
            "state": "DEVELOPMENT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DEVELOPMENT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.apis_path, records,
                          "api_gateway_apis", "api_id")
        return {"registered": ok, "api_id": api_data["api_id"]}

    def transition_api_state(
        self, api_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in API_VERSION_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.apis_path, "api_gateway_apis", ("api_id",))
        for r in records:
            if r.get("api_id") == api_id:
                current = r.get("state", "DEVELOPMENT")
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
                                  "api_gateway_apis", "api_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "api_not_found"}

    def register_rate_limit_policy(
        self, policy_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("policy_id", "policy_name", "limit", "window"):
            if f not in policy_data or policy_data[f] in (None, "", 0):
                return {"registered": False, "error": f"missing_field:{f}"}
        if policy_data["window"] not in RATE_LIMIT_WINDOWS:
            return {"registered": False,
                       "error": f"invalid_window:{policy_data['window']}"}
        try:
            limit = int(policy_data["limit"])
        except Exception:
            return {"registered": False, "error": "invalid_limit"}
        if limit <= 0:
            return {"registered": False, "error": "limit_must_be_positive"}
        records = self._load(self.policies_path,
                                "api_gateway_policies", ("policy_id",))
        if any(r.get("policy_id") == policy_data["policy_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_policy_id"}
        record = {
            "policy_id": policy_data["policy_id"],
            "policy_name": policy_data["policy_name"],
            "limit": limit,
            "window": policy_data["window"],
            "burst_factor": policy_data.get(
                "burst_factor", DEFAULT_RATE_LIMIT_BURST_FACTOR,
            ),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.policies_path, records,
                          "api_gateway_policies", "policy_id")
        return {"registered": ok, "policy_id": policy_data["policy_id"]}

    def register_api_key(
        self, key_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("key_id", "developer_id", "api_id"):
            if f not in key_data or not key_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        # Verify API exists
        apis = self._load(self.apis_path, "api_gateway_apis", ("api_id",))
        if not any(a.get("api_id") == key_data["api_id"] for a in apis):
            return {"registered": False, "error": "api_not_found"}
        records = self._load(self.keys_path, "api_gateway_keys", ("key_id",))
        if any(r.get("key_id") == key_data["key_id"] for r in records):
            return {"registered": False, "error": "duplicate_key_id"}
        record = {
            "key_id": key_data["key_id"],
            "developer_id": key_data["developer_id"],
            "api_id": key_data["api_id"],
            "scopes": key_data.get("scopes", []),
            "expires_at": key_data.get("expires_at", ""),
            "state": "PENDING",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.keys_path, records,
                          "api_gateway_keys", "key_id")
        return {"registered": ok, "key_id": key_data["key_id"]}

    def register_developer(
        self, dev_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("developer_id", "developer_name", "email", "organization"):
            if f not in dev_data or not dev_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.developers_path,
                                "api_gateway_developers",
                                ("developer_id",))
        if any(r.get("developer_id") == dev_data["developer_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_developer_id"}
        record = {
            "developer_id": dev_data["developer_id"],
            "developer_name": dev_data["developer_name"],
            "email": dev_data["email"],
            "organization": dev_data["organization"],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.developers_path, records,
                          "api_gateway_developers", "developer_id")
        return {"registered": ok,
                  "developer_id": dev_data["developer_id"]}

    def record_api_call(
        self, call_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("call_id", "api_id", "key_id",
                      "endpoint", "status_code", "called_at"):
            if f not in call_data or call_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        records = self._load(self.calls_path,
                                "api_gateway_calls", ("call_id",))
        if any(r.get("call_id") == call_data["call_id"] for r in records):
            return {"recorded": False, "error": "duplicate_call_id"}
        record = {
            "call_id": call_data["call_id"],
            "api_id": call_data["api_id"],
            "key_id": call_data["key_id"],
            "endpoint": call_data["endpoint"],
            "status_code": int(call_data["status_code"]),
            "called_at": call_data["called_at"],
            "latency_ms": call_data.get("latency_ms", 0),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.calls_path, records,
                          "api_gateway_calls", "call_id")
        return {"recorded": ok, "call_id": call_data["call_id"]}

    def rate_limit_check(self, api_id: str, key_id: str) -> Dict[str, Any]:
        apis = self._load(self.apis_path, "api_gateway_apis", ("api_id",))
        api = next((a for a in apis if a.get("api_id") == api_id), None)
        if api is None:
            return {"checked": False, "error": "api_not_found"}
        policy_id = api.get("rate_limit_policy_id", "")
        policies = self._load(self.policies_path,
                                  "api_gateway_policies", ("policy_id",))
        policy = next(
            (p for p in policies if p.get("policy_id") == policy_id), None,
        )
        if policy is None:
            # Default fallback
            limit = DEFAULT_RATE_LIMIT_PER_MINUTE
            window = "MINUTE"
            burst = DEFAULT_RATE_LIMIT_BURST_FACTOR
            policy_used = "DEFAULT_FALLBACK"
        else:
            limit = policy["limit"]
            window = policy["window"]
            burst = policy.get("burst_factor", DEFAULT_RATE_LIMIT_BURST_FACTOR)
            policy_used = policy["policy_id"]
        # Count calls in window
        window_seconds = {
            "SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400,
        }[window]
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        cutoff_iso = cutoff.isoformat()
        calls = self._load(self.calls_path,
                              "api_gateway_calls", ("call_id",))
        recent = [c for c in calls
                       if c.get("api_id") == api_id
                       and c.get("key_id") == key_id
                       and c.get("called_at", "") >= cutoff_iso]
        count = len(recent)
        burst_limit = int(limit) * int(burst)
        within_limit = count < int(limit)
        within_burst = count < burst_limit
        return {
            "checked": True,
            "api_id": api_id,
            "key_id": key_id,
            "policy_used": policy_used,
            "limit": limit,
            "window": window,
            "burst_limit": burst_limit,
            "current_count": count,
            "within_limit": within_limit,
            "within_burst": within_burst,
            "remaining": max(0, int(limit) - count),
        }

    def api_usage_summary(self, api_id: str) -> Dict[str, Any]:
        calls = self._load(self.calls_path,
                              "api_gateway_calls", ("call_id",))
        api_calls = [c for c in calls if c.get("api_id") == api_id]
        success = sum(1 for c in api_calls
                              if 200 <= c.get("status_code", 0) < 300)
        client_err = sum(1 for c in api_calls
                                if 400 <= c.get("status_code", 0) < 500)
        server_err = sum(1 for c in api_calls
                                if 500 <= c.get("status_code", 0) < 600)
        unique_keys = len({c.get("key_id") for c in api_calls
                                if c.get("key_id")})
        return {
            "api_id": api_id,
            "total_calls": len(api_calls),
            "success_count": success,
            "client_error_count": client_err,
            "server_error_count": server_err,
            "unique_keys_used": unique_keys,
        }


def _self_test() -> None:
    import tempfile

    assert "DEVELOPMENT" in API_VERSION_STATES
    assert ALLOWED_API_TRANSITIONS["RETIRED"] == ()
    assert "MINUTE" in RATE_LIMIT_WINDOWS
    assert "OAUTH2_BEARER" in AUTH_SCHEMES
    assert "ACTIVE" in API_KEY_STATES
    assert DEFAULT_RATE_LIMIT_PER_MINUTE == 60
    assert DEFAULT_RATE_LIMIT_BURST_FACTOR == 2

    with tempfile.TemporaryDirectory() as tmpdir:
        e = APIGatewayEngine(
            apis_path=Path(tmpdir) / "a.json",
            keys_path=Path(tmpdir) / "k.json",
            policies_path=Path(tmpdir) / "p.json",
            developers_path=Path(tmpdir) / "d.json",
            calls_path=Path(tmpdir) / "c.json",
        )
        # Rate limit policy
        r = e.register_rate_limit_policy(
            {"policy_id": "RATE-100-MIN",
             "policy_name": "100/min standard",
             "limit": 100, "window": "MINUTE",
             "burst_factor": 2},
            actor="cto", reason="standard policy",
        )
        assert r["registered"]
        # Invalid window
        r = e.register_rate_limit_policy(
            {"policy_id": "X", "policy_name": "Y",
             "limit": 10, "window": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid limit
        r = e.register_rate_limit_policy(
            {"policy_id": "Y", "policy_name": "Z",
             "limit": 0, "window": "MINUTE"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # API
        r = e.register_api(
            {"api_id": "API-LOAN-V1", "api_name": "Loan Origination",
             "version": "v1", "auth_scheme": "OAUTH2_BEARER",
             "base_path": "/loans/v1",
             "rate_limit_policy_id": "RATE-100-MIN"},
            actor="cto", reason="initial",
        )
        assert r["registered"]
        # Invalid auth scheme
        r = e.register_api(
            {"api_id": "X", "api_name": "Y", "version": "v1",
             "auth_scheme": "BASIC", "base_path": "/x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # API state machine
        r = e.transition_api_state("API-LOAN-V1", "BETA",
                                          actor="cto", reason="ready")
        assert r["transitioned"]
        r = e.transition_api_state("API-LOAN-V1", "GA",
                                          actor="cto", reason="prod")
        assert r["transitioned"]
        # Cannot go back
        r = e.transition_api_state("API-LOAN-V1", "BETA",
                                          actor="cto", reason="x")
        assert not r["transitioned"]

        # Developer
        r = e.register_developer(
            {"developer_id": "DEV-001", "developer_name": "John Doe",
             "email": "john@example.com",
             "organization": "Partner Corp"},
            actor="portal",
        )
        assert r["registered"]
        # Duplicate
        r = e.register_developer(
            {"developer_id": "DEV-001", "developer_name": "X",
             "email": "y@z.com", "organization": "X"},
            actor="x",
        )
        assert not r["registered"]

        # API key
        r = e.register_api_key(
            {"key_id": "KEY-001", "developer_id": "DEV-001",
             "api_id": "API-LOAN-V1",
             "scopes": ["loans.read", "loans.create"]},
            actor="portal", reason="dev requested",
        )
        assert r["registered"]
        # API not found
        r = e.register_api_key(
            {"key_id": "X", "developer_id": "DEV-001",
             "api_id": "NOPE"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Calls
        for i in range(5):
            r = e.record_api_call(
                {"call_id": f"CALL-{i:03d}", "api_id": "API-LOAN-V1",
                 "key_id": "KEY-001", "endpoint": "/loans",
                 "status_code": 200,
                 "called_at": datetime.utcnow().isoformat(),
                 "latency_ms": 25},
                actor="gateway",
            )
            assert r["recorded"]
        # 4xx call
        e.record_api_call(
            {"call_id": "CALL-401", "api_id": "API-LOAN-V1",
             "key_id": "KEY-001", "endpoint": "/loans",
             "status_code": 401,
             "called_at": datetime.utcnow().isoformat()},
            actor="gateway",
        )
        # 5xx call
        e.record_api_call(
            {"call_id": "CALL-500", "api_id": "API-LOAN-V1",
             "key_id": "KEY-001", "endpoint": "/loans",
             "status_code": 500,
             "called_at": datetime.utcnow().isoformat()},
            actor="gateway",
        )
        # Rate limit check
        c = e.rate_limit_check("API-LOAN-V1", "KEY-001")
        assert c["checked"]
        assert c["limit"] == 100
        assert c["current_count"] == 7
        assert c["within_limit"]
        # Usage
        u = e.api_usage_summary("API-LOAN-V1")
        assert u["total_calls"] == 7
        assert u["success_count"] == 5
        assert u["client_error_count"] == 1
        assert u["server_error_count"] == 1

    print("  ✅ it_api_gateway self-test PASS")


if __name__ == "__main__":
    _self_test()

"""
================================================================================
A2Z MIS 360 — Standard #292: Cloud-Native & Container Architecture
================================================================================

Risk classification: Cat C (deployment metadata + service mesh registry)

Kubernetes-native deployment, microservices, API-first, 12-factor app
principles. Multi-cloud (AWS/Azure/GCP) portability tracking.

Public API:
    register_microservice(service_data, actor, reason)
    transition_service_state(service_id, new_state, actor, reason)
    register_deployment(deployment_data, actor)
    transition_deployment_state(deployment_id, new_state, actor, reason)
    record_health_check(service_id, status, actor)
    list_services_by_cloud(cloud_provider) -> List
    twelve_factor_audit(service_id) -> Dict (compliance scorecard)

CLOUD_PROVIDERS byte-for-byte (4): AWS, AZURE, GCP, ON_PREMISES

DEPLOYMENT_PLATFORMS byte-for-byte (5):
    KUBERNETES, ECS, CLOUD_RUN, AKS, ON_PREMISES

SERVICE_STATES byte-for-byte (5):
    PROPOSED, IN_DEVELOPMENT, IN_PRODUCTION, DEPRECATED, RETIRED

ALLOWED_SERVICE_TRANSITIONS (Rule 4):
    PROPOSED        → IN_DEVELOPMENT | RETIRED
    IN_DEVELOPMENT  → IN_PRODUCTION | RETIRED
    IN_PRODUCTION   → DEPRECATED | RETIRED
    DEPRECATED      → RETIRED
    RETIRED         → ()

DEPLOYMENT_STATES byte-for-byte (6):
    PLANNED, BUILDING, DEPLOYING, ACTIVE, ROLLED_BACK, RETIRED

ALLOWED_DEPLOYMENT_TRANSITIONS (Rule 4):
    PLANNED      → BUILDING
    BUILDING     → DEPLOYING | ROLLED_BACK
    DEPLOYING    → ACTIVE | ROLLED_BACK
    ACTIVE       → ROLLED_BACK | RETIRED
    ROLLED_BACK  → RETIRED
    RETIRED      → ()

HEALTH_STATUSES byte-for-byte (4): HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN

TWELVE_FACTOR_DIMENSIONS byte-for-byte (12):
    CODEBASE, DEPENDENCIES, CONFIG, BACKING_SERVICES, BUILD_RELEASE_RUN,
    PROCESSES, PORT_BINDING, CONCURRENCY, DISPOSABILITY,
    DEV_PROD_PARITY, LOGS, ADMIN_PROCESSES

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CLOUD_PROVIDERS: Tuple[str, ...] = ("AWS", "AZURE", "GCP", "ON_PREMISES")

DEPLOYMENT_PLATFORMS: Tuple[str, ...] = (
    "KUBERNETES", "ECS", "CLOUD_RUN", "AKS", "ON_PREMISES",
)

SERVICE_STATES: Tuple[str, ...] = (
    "PROPOSED", "IN_DEVELOPMENT", "IN_PRODUCTION", "DEPRECATED", "RETIRED",
)

ALLOWED_SERVICE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROPOSED":       ("IN_DEVELOPMENT", "RETIRED"),
    "IN_DEVELOPMENT": ("IN_PRODUCTION", "RETIRED"),
    "IN_PRODUCTION":  ("DEPRECATED", "RETIRED"),
    "DEPRECATED":     ("RETIRED",),
    "RETIRED":        (),
}

DEPLOYMENT_STATES: Tuple[str, ...] = (
    "PLANNED", "BUILDING", "DEPLOYING", "ACTIVE", "ROLLED_BACK", "RETIRED",
)

ALLOWED_DEPLOYMENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PLANNED":     ("BUILDING",),
    "BUILDING":    ("DEPLOYING", "ROLLED_BACK"),
    "DEPLOYING":   ("ACTIVE", "ROLLED_BACK"),
    "ACTIVE":      ("ROLLED_BACK", "RETIRED"),
    "ROLLED_BACK": ("RETIRED",),
    "RETIRED":     (),
}

HEALTH_STATUSES: Tuple[str, ...] = (
    "HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN",
)

TWELVE_FACTOR_DIMENSIONS: Tuple[str, ...] = (
    "CODEBASE", "DEPENDENCIES", "CONFIG", "BACKING_SERVICES",
    "BUILD_RELEASE_RUN", "PROCESSES", "PORT_BINDING", "CONCURRENCY",
    "DISPOSABILITY", "DEV_PROD_PARITY", "LOGS", "ADMIN_PROCESSES",
)


class CloudNativeArchitectureEngine:
    """Microservices + deployment lifecycle + 12-factor audit."""

    def __init__(
        self,
        services_path: Optional[Path] = None,
        deployments_path: Optional[Path] = None,
        health_checks_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.services_path = services_path or base / "cloud_microservices.json"
        self.deployments_path = deployments_path or base / "cloud_deployments.json"
        self.health_checks_path = health_checks_path or base / "cloud_health_checks.json"

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

    def register_microservice(
        self, service_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("service_id", "service_name", "cloud_provider",
                      "deployment_platform", "owner_team"):
            if f not in service_data or not service_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if service_data["cloud_provider"] not in CLOUD_PROVIDERS:
            return {"registered": False,
                       "error": f"invalid_cloud_provider:{service_data['cloud_provider']}"}
        if service_data["deployment_platform"] not in DEPLOYMENT_PLATFORMS:
            return {"registered": False,
                       "error": f"invalid_deployment_platform:{service_data['deployment_platform']}"}
        records = self._load(self.services_path,
                                "cloud_microservices", ("service_id",))
        if any(r.get("service_id") == service_data["service_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_service_id"}
        # Initialize 12-factor compliance to all UNKNOWN
        twelve_factor = {
            d: service_data.get("twelve_factor", {}).get(d, "UNKNOWN")
            for d in TWELVE_FACTOR_DIMENSIONS
        }
        record = {
            "service_id": service_data["service_id"],
            "service_name": service_data["service_name"],
            "description": service_data.get("description", ""),
            "cloud_provider": service_data["cloud_provider"],
            "deployment_platform": service_data["deployment_platform"],
            "owner_team": service_data["owner_team"],
            "api_endpoints": service_data.get("api_endpoints", []),
            "twelve_factor": twelve_factor,
            "state": "PROPOSED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PROPOSED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.services_path, records,
                          "cloud_microservices", "service_id")
        return {"registered": ok,
                  "service_id": service_data["service_id"]}

    def transition_service_state(
        self, service_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in SERVICE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.services_path,
                                "cloud_microservices", ("service_id",))
        for r in records:
            if r.get("service_id") == service_id:
                current = r.get("state", "PROPOSED")
                allowed = ALLOWED_SERVICE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.services_path, records,
                                  "cloud_microservices", "service_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "service_not_found"}

    def register_deployment(
        self, deployment_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("deployment_id", "service_id", "version", "target_env"):
            if f not in deployment_data or not deployment_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        # Verify service exists
        services = self._load(self.services_path,
                                    "cloud_microservices", ("service_id",))
        if not any(s.get("service_id") == deployment_data["service_id"]
                       for s in services):
            return {"registered": False, "error": "service_not_found"}
        records = self._load(self.deployments_path,
                                "cloud_deployments", ("deployment_id",))
        if any(r.get("deployment_id") == deployment_data["deployment_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_deployment_id"}
        record = {
            "deployment_id": deployment_data["deployment_id"],
            "service_id": deployment_data["service_id"],
            "version": deployment_data["version"],
            "target_env": deployment_data["target_env"],
            "image_uri": deployment_data.get("image_uri", ""),
            "manifest_uri": deployment_data.get("manifest_uri", ""),
            "state": "PLANNED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "PLANNED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.deployments_path, records,
                          "cloud_deployments", "deployment_id")
        return {"registered": ok,
                  "deployment_id": deployment_data["deployment_id"]}

    def transition_deployment_state(
        self, deployment_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in DEPLOYMENT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.deployments_path,
                                "cloud_deployments", ("deployment_id",))
        for r in records:
            if r.get("deployment_id") == deployment_id:
                current = r.get("state", "PLANNED")
                allowed = ALLOWED_DEPLOYMENT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.deployments_path, records,
                                  "cloud_deployments", "deployment_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "deployment_not_found"}

    def record_health_check(
        self, service_id: str, status: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if status not in HEALTH_STATUSES:
            return {"recorded": False, "error": f"invalid_status:{status}"}
        # Verify service exists
        services = self._load(self.services_path,
                                    "cloud_microservices", ("service_id",))
        if not any(s.get("service_id") == service_id for s in services):
            return {"recorded": False, "error": "service_not_found"}
        records = self._load(self.health_checks_path,
                                "cloud_health_checks", ("check_id",))
        check_id = (f"HC-{service_id}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "check_id": check_id,
            "service_id": service_id,
            "status": status,
            "checked_by": actor,
            "checked_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.health_checks_path, records,
                          "cloud_health_checks", "check_id")
        return {"recorded": ok, "check_id": check_id, "status": status}

    def list_services_by_cloud(
        self, cloud_provider: str,
    ) -> List[Dict[str, Any]]:
        if cloud_provider not in CLOUD_PROVIDERS:
            return []
        records = self._load(self.services_path,
                                "cloud_microservices", ("service_id",))
        return [r for r in records
                    if r.get("cloud_provider") == cloud_provider]

    def twelve_factor_audit(self, service_id: str) -> Dict[str, Any]:
        records = self._load(self.services_path,
                                "cloud_microservices", ("service_id",))
        service = next((r for r in records
                              if r.get("service_id") == service_id), None)
        if service is None:
            return {"found": False, "error": "service_not_found"}
        compliance = service.get("twelve_factor", {})
        compliant_count = sum(
            1 for d in TWELVE_FACTOR_DIMENSIONS
            if compliance.get(d) == "PASS"
        )
        score_pct = (compliant_count /
                          len(TWELVE_FACTOR_DIMENSIONS) * 100)
        return {
            "found": True,
            "service_id": service_id,
            "compliant_count": compliant_count,
            "total": len(TWELVE_FACTOR_DIMENSIONS),
            "score_pct": round(score_pct, 1),
            "dimensions": compliance,
        }

    def update_twelve_factor(
        self, service_id: str, dimension: str,
        status: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"updated": False, "error": "actor_and_reason_required"}
        if dimension not in TWELVE_FACTOR_DIMENSIONS:
            return {"updated": False,
                       "error": f"invalid_dimension:{dimension}"}
        if status not in ("PASS", "FAIL", "PARTIAL", "UNKNOWN"):
            return {"updated": False, "error": f"invalid_status:{status}"}
        records = self._load(self.services_path,
                                "cloud_microservices", ("service_id",))
        for r in records:
            if r.get("service_id") == service_id:
                r.setdefault("twelve_factor", {})[dimension] = status
                r.setdefault("twelve_factor_history", []).append({
                    "dimension": dimension, "status": status,
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.services_path, records,
                                  "cloud_microservices", "service_id")
                return {"updated": ok}
        return {"updated": False, "error": "service_not_found"}


def _self_test() -> None:
    import tempfile

    assert "AWS" in CLOUD_PROVIDERS
    assert "KUBERNETES" in DEPLOYMENT_PLATFORMS
    assert ALLOWED_SERVICE_TRANSITIONS["RETIRED"] == ()
    assert ALLOWED_DEPLOYMENT_TRANSITIONS["RETIRED"] == ()
    assert len(TWELVE_FACTOR_DIMENSIONS) == 12

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CloudNativeArchitectureEngine(
            services_path=Path(tmpdir) / "s.json",
            deployments_path=Path(tmpdir) / "d.json",
            health_checks_path=Path(tmpdir) / "h.json",
        )
        # Test 1: register service
        r = engine.register_microservice(
            {"service_id": "SVC-AUTH", "service_name": "auth-service",
             "cloud_provider": "AWS",
             "deployment_platform": "KUBERNETES",
             "owner_team": "platform"},
            actor="cio", reason="new auth service",
        )
        assert r["registered"]
        # Test 2: invalid cloud provider
        r = engine.register_microservice(
            {"service_id": "X", "service_name": "X",
             "cloud_provider": "DIGITAL_OCEAN",
             "deployment_platform": "KUBERNETES",
             "owner_team": "x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: invalid platform
        r = engine.register_microservice(
            {"service_id": "X", "service_name": "X",
             "cloud_provider": "AWS",
             "deployment_platform": "DOCKER_SWARM",
             "owner_team": "x"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 4: state transitions
        r = engine.transition_service_state(
            "SVC-AUTH", "IN_DEVELOPMENT",
            actor="cio", reason="dev start",
        )
        assert r["transitioned"]
        r = engine.transition_service_state(
            "SVC-AUTH", "IN_PRODUCTION",
            actor="cio", reason="released",
        )
        assert r["transitioned"]
        # Test 5: invalid transition
        r = engine.transition_service_state(
            "SVC-AUTH", "PROPOSED",
            actor="cio", reason="x",
        )
        assert not r["transitioned"]
        # Test 6: deployment register
        r = engine.register_deployment(
            {"deployment_id": "DEP-AUTH-1.0",
             "service_id": "SVC-AUTH", "version": "1.0.0",
             "target_env": "production",
             "image_uri": "ecr.aws/auth:1.0.0"},
            actor="ops",
        )
        assert r["registered"]
        # Test 7: deployment for unknown service
        r = engine.register_deployment(
            {"deployment_id": "X",
             "service_id": "SVC-NONEXISTENT",
             "version": "1", "target_env": "x"},
            actor="x",
        )
        assert not r["registered"]
        # Test 8: deployment transitions
        engine.transition_deployment_state(
            "DEP-AUTH-1.0", "BUILDING", actor="ci", reason="build start",
        )
        r = engine.transition_deployment_state(
            "DEP-AUTH-1.0", "DEPLOYING", actor="cd", reason="deploying",
        )
        assert r["transitioned"]
        r = engine.transition_deployment_state(
            "DEP-AUTH-1.0", "ACTIVE", actor="cd", reason="live",
        )
        assert r["transitioned"]
        # Test 9: rollback
        r = engine.transition_deployment_state(
            "DEP-AUTH-1.0", "ROLLED_BACK",
            actor="ops", reason="bug found",
        )
        assert r["transitioned"]
        # Test 10: health check
        r = engine.record_health_check("SVC-AUTH", "HEALTHY", actor="probe")
        assert r["recorded"]
        # Test 11: invalid health status
        r = engine.record_health_check("SVC-AUTH", "FUBAR", actor="x")
        assert not r["recorded"]
        # Test 12: cloud filter
        services_aws = engine.list_services_by_cloud("AWS")
        assert len(services_aws) == 1
        services_gcp = engine.list_services_by_cloud("GCP")
        assert len(services_gcp) == 0
        # Test 13: 12-factor audit (initial all UNKNOWN)
        a = engine.twelve_factor_audit("SVC-AUTH")
        assert a["found"]
        assert a["compliant_count"] == 0
        # Test 14: update dimensions
        r = engine.update_twelve_factor(
            "SVC-AUTH", "CODEBASE", "PASS",
            actor="audit", reason="single repo, version controlled",
        )
        assert r["updated"]
        # Test 15: invalid dimension
        r = engine.update_twelve_factor(
            "SVC-AUTH", "INVALID_DIM", "PASS",
            actor="x", reason="x",
        )
        assert not r["updated"]
        # Test 16: re-audit
        a = engine.twelve_factor_audit("SVC-AUTH")
        assert a["compliant_count"] == 1
        assert a["score_pct"] > 0

    print("  ✅ cloud_native_architecture self-test PASS")


if __name__ == "__main__":
    _self_test()

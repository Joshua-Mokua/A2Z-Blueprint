"""
================================================================================
A2Z MIS 360 — Standard #292: Cloud-Native & Container Architecture
================================================================================

Risk classification: Cat C (deployment topology registry)

Kubernetes-native deployment, microservices, API-first, 12-factor app
principles. Multi-cloud (AWS/Azure/GCP) portability registry.

Public API:
    register_microservice(svc_data, actor, reason)
    register_deployment(deployment_data, actor, reason)
    transition_deployment_state(deployment_id, new_state, actor, reason)
    register_cloud_provider(provider_data, actor, reason)
    portability_assessment(svc_id) -> Dict
    list_active_services() -> List

CLOUD_PROVIDERS byte-for-byte (3): AWS, AZURE, GCP

CONTAINER_RUNTIMES byte-for-byte (3): KUBERNETES, DOCKER_SWARM, ECS

DEPLOYMENT_STRATEGIES byte-for-byte (5):
    BLUE_GREEN, CANARY, ROLLING, RECREATE, A_B_TEST

DEPLOYMENT_STATES byte-for-byte (5):
    PLANNED, DEPLOYED, ROLLING_BACK, ROLLED_BACK, RETIRED

ALLOWED_DEPLOYMENT_TRANSITIONS (Rule 4):
    PLANNED      → DEPLOYED | RETIRED
    DEPLOYED     → ROLLING_BACK | RETIRED
    ROLLING_BACK → ROLLED_BACK
    ROLLED_BACK  → DEPLOYED  (re-deploy after fix)
    RETIRED      → ()

TWELVE_FACTOR_CRITERIA byte-for-byte (12):
    CODEBASE, DEPENDENCIES, CONFIG, BACKING_SERVICES, BUILD_RELEASE_RUN,
    PROCESSES, PORT_BINDING, CONCURRENCY, DISPOSABILITY, DEV_PROD_PARITY,
    LOGS, ADMIN_PROCESSES

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CLOUD_PROVIDERS: Tuple[str, ...] = ("AWS", "AZURE", "GCP")

CONTAINER_RUNTIMES: Tuple[str, ...] = (
    "KUBERNETES", "DOCKER_SWARM", "ECS",
)

DEPLOYMENT_STRATEGIES: Tuple[str, ...] = (
    "BLUE_GREEN", "CANARY", "ROLLING", "RECREATE", "A_B_TEST",
)

DEPLOYMENT_STATES: Tuple[str, ...] = (
    "PLANNED", "DEPLOYED", "ROLLING_BACK", "ROLLED_BACK", "RETIRED",
)

ALLOWED_DEPLOYMENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PLANNED":      ("DEPLOYED", "RETIRED"),
    "DEPLOYED":     ("ROLLING_BACK", "RETIRED"),
    "ROLLING_BACK": ("ROLLED_BACK",),
    "ROLLED_BACK":  ("DEPLOYED",),
    "RETIRED":      (),
}

TWELVE_FACTOR_CRITERIA: Tuple[str, ...] = (
    "CODEBASE", "DEPENDENCIES", "CONFIG", "BACKING_SERVICES",
    "BUILD_RELEASE_RUN", "PROCESSES", "PORT_BINDING", "CONCURRENCY",
    "DISPOSABILITY", "DEV_PROD_PARITY", "LOGS", "ADMIN_PROCESSES",
)


class CloudArchitectureEngine:
    """Cloud-native deployment registry with portability tracking."""

    def __init__(
        self,
        services_path: Optional[Path] = None,
        deployments_path: Optional[Path] = None,
        providers_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.services_path = services_path or base / "cloud_services.json"
        self.deployments_path = deployments_path or base / "cloud_deployments.json"
        self.providers_path = providers_path or base / "cloud_providers.json"

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
        self, svc_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("service_id", "service_name", "owner_team",
                      "container_runtime"):
            if f not in svc_data or not svc_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if svc_data["container_runtime"] not in CONTAINER_RUNTIMES:
            return {"registered": False,
                       "error": f"invalid_runtime:{svc_data['container_runtime']}"}
        twelve_factor = svc_data.get("twelve_factor_compliance", {})
        for crit in twelve_factor:
            if crit not in TWELVE_FACTOR_CRITERIA:
                return {"registered": False,
                           "error": f"invalid_twelve_factor_criterion:{crit}"}
        records = self._load(self.services_path,
                                "cloud_services", ("service_id",))
        if any(r.get("service_id") == svc_data["service_id"] for r in records):
            return {"registered": False, "error": "duplicate_service_id"}
        record = {
            "service_id": svc_data["service_id"],
            "service_name": svc_data["service_name"],
            "owner_team": svc_data["owner_team"],
            "container_runtime": svc_data["container_runtime"],
            "primary_provider": svc_data.get("primary_provider", ""),
            "secondary_providers": svc_data.get("secondary_providers", []),
            "api_version": svc_data.get("api_version", "v1"),
            "twelve_factor_compliance": twelve_factor,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.services_path, records,
                          "cloud_services", "service_id")
        return {"registered": ok, "service_id": svc_data["service_id"]}

    def register_deployment(
        self, deployment_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("deployment_id", "service_id", "version",
                      "deployment_strategy", "target_provider"):
            if f not in deployment_data or not deployment_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if deployment_data["deployment_strategy"] not in DEPLOYMENT_STRATEGIES:
            return {"registered": False,
                       "error": f"invalid_strategy:{deployment_data['deployment_strategy']}"}
        if deployment_data["target_provider"] not in CLOUD_PROVIDERS:
            return {"registered": False,
                       "error": f"invalid_provider:{deployment_data['target_provider']}"}
        records = self._load(self.deployments_path,
                                "cloud_deployments", ("deployment_id",))
        if any(r.get("deployment_id") == deployment_data["deployment_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_deployment_id"}
        record = {
            "deployment_id": deployment_data["deployment_id"],
            "service_id": deployment_data["service_id"],
            "version": deployment_data["version"],
            "deployment_strategy": deployment_data["deployment_strategy"],
            "target_provider": deployment_data["target_provider"],
            "region": deployment_data.get("region", ""),
            "state": "PLANNED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
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
        self, deployment_id: str, new_state: str,
        actor: str, reason: str,
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

    def register_cloud_provider(
        self, provider_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("provider_id", "provider_name", "provider_type"):
            if f not in provider_data or not provider_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if provider_data["provider_type"] not in CLOUD_PROVIDERS:
            return {"registered": False,
                       "error": f"invalid_type:{provider_data['provider_type']}"}
        records = self._load(self.providers_path,
                                "cloud_providers", ("provider_id",))
        if any(r.get("provider_id") == provider_data["provider_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_provider_id"}
        record = {
            "provider_id": provider_data["provider_id"],
            "provider_name": provider_data["provider_name"],
            "provider_type": provider_data["provider_type"],
            "region": provider_data.get("region", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.providers_path, records,
                          "cloud_providers", "provider_id")
        return {"registered": ok, "provider_id": provider_data["provider_id"]}

    def portability_assessment(self, service_id: str) -> Dict[str, Any]:
        records = self._load(self.services_path,
                                "cloud_services", ("service_id",))
        svc = next((r for r in records
                          if r.get("service_id") == service_id), None)
        if svc is None:
            return {"found": False, "error": "service_not_found"}
        # Score based on 12-factor compliance + multi-provider readiness
        compliance = svc.get("twelve_factor_compliance", {})
        passed = sum(1 for v in compliance.values() if v is True)
        total = len(TWELVE_FACTOR_CRITERIA)
        compliance_pct = (passed / total * 100) if total > 0 else 0
        primary = svc.get("primary_provider", "")
        secondaries = svc.get("secondary_providers", [])
        portability_score = compliance_pct
        if primary and len(secondaries) >= 1:
            portability_score = min(100, portability_score + 10)
        if len(secondaries) >= 2:
            portability_score = min(100, portability_score + 5)
        return {
            "found": True,
            "service_id": service_id,
            "twelve_factor_passed": passed,
            "twelve_factor_total": total,
            "compliance_pct": round(compliance_pct, 1),
            "primary_provider": primary,
            "secondary_providers": secondaries,
            "portability_score": round(portability_score, 1),
            "portability_grade": (
                "A" if portability_score >= 90 else
                "B" if portability_score >= 75 else
                "C" if portability_score >= 60 else
                "D" if portability_score >= 40 else "F"
            ),
        }

    def list_active_services(self) -> List[Dict[str, Any]]:
        records = self._load(self.services_path,
                                "cloud_services", ("service_id",))
        return records


def _self_test() -> None:
    import tempfile

    assert CLOUD_PROVIDERS == ("AWS", "AZURE", "GCP")
    assert "KUBERNETES" in CONTAINER_RUNTIMES
    assert "BLUE_GREEN" in DEPLOYMENT_STRATEGIES
    assert ALLOWED_DEPLOYMENT_TRANSITIONS["RETIRED"] == ()
    assert len(TWELVE_FACTOR_CRITERIA) == 12

    with tempfile.TemporaryDirectory() as tmpdir:
        e = CloudArchitectureEngine(
            services_path=Path(tmpdir) / "s.json",
            deployments_path=Path(tmpdir) / "d.json",
            providers_path=Path(tmpdir) / "p.json",
        )
        # Provider
        r = e.register_cloud_provider(
            {"provider_id": "PROV-AWS-AF",
             "provider_name": "AWS Cape Town", "provider_type": "AWS",
             "region": "af-south-1"},
            actor="cto", reason="primary",
        )
        assert r["registered"]
        # Invalid provider type
        r = e.register_cloud_provider(
            {"provider_id": "X", "provider_name": "Y",
             "provider_type": "DIGITAL_OCEAN"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Microservice with full 12-factor compliance
        compliance = {c: True for c in TWELVE_FACTOR_CRITERIA}
        r = e.register_microservice(
            {"service_id": "SVC-AUTH",
             "service_name": "Auth Service",
             "owner_team": "platform",
             "container_runtime": "KUBERNETES",
             "primary_provider": "AWS",
             "secondary_providers": ["AZURE", "GCP"],
             "twelve_factor_compliance": compliance},
            actor="cto", reason="initial reg",
        )
        assert r["registered"]
        # Invalid runtime
        r = e.register_microservice(
            {"service_id": "X", "service_name": "Y",
             "owner_team": "Z", "container_runtime": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid 12-factor criterion
        r = e.register_microservice(
            {"service_id": "Y", "service_name": "Z",
             "owner_team": "T", "container_runtime": "KUBERNETES",
             "twelve_factor_compliance": {"INVALID_CRIT": True}},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Deployment
        r = e.register_deployment(
            {"deployment_id": "DEP-001", "service_id": "SVC-AUTH",
             "version": "v1.2.3", "deployment_strategy": "CANARY",
             "target_provider": "AWS"},
            actor="cto", reason="release v1.2.3",
        )
        assert r["registered"]
        # Invalid strategy
        r = e.register_deployment(
            {"deployment_id": "X", "service_id": "Y", "version": "Z",
             "deployment_strategy": "RANDOM", "target_provider": "AWS"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid provider
        r = e.register_deployment(
            {"deployment_id": "Y", "service_id": "Z", "version": "T",
             "deployment_strategy": "CANARY", "target_provider": "ORACLE"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Transitions
        r = e.transition_deployment_state("DEP-001", "DEPLOYED",
                                                actor="cto",
                                                reason="canary green")
        assert r["transitioned"]
        r = e.transition_deployment_state("DEP-001", "ROLLING_BACK",
                                                actor="cto",
                                                reason="error rate spike")
        assert r["transitioned"]
        r = e.transition_deployment_state("DEP-001", "ROLLED_BACK",
                                                actor="cto",
                                                reason="back at v1.2.2")
        assert r["transitioned"]
        # ROLLED_BACK → DEPLOYED (re-deploy)
        r = e.transition_deployment_state("DEP-001", "DEPLOYED",
                                                actor="cto",
                                                reason="hotfix v1.2.4")
        assert r["transitioned"]
        # Invalid transition
        r = e.transition_deployment_state("DEP-001", "PLANNED",
                                                actor="cto", reason="x")
        assert not r["transitioned"]

        # Portability
        a = e.portability_assessment("SVC-AUTH")
        assert a["found"]
        assert a["compliance_pct"] == 100.0
        assert a["portability_score"] == 100.0
        assert a["portability_grade"] == "A"
        # Service not found
        a = e.portability_assessment("NOPE")
        assert not a["found"]

    print("  ✅ it_cloud_architecture self-test PASS")


if __name__ == "__main__":
    _self_test()

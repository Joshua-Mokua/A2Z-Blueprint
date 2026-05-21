"""
================================================================================
A2Z MIS 360 — Standard #297: CI/CD & Release Automation
================================================================================

Risk classification: Cat C (delivery automation orchestration)

GitHub Actions / GitLab CI / Jenkins pipelines. Auto-test, auto-deploy
to staging, blue-green production deploys.

Public API:
    register_pipeline(pipeline_data, actor, reason)
    transition_pipeline_state(pipeline_id, new_state, actor, reason)
    record_pipeline_run(run_data, actor)
    transition_run_state(run_id, new_state, actor, reason)
    register_environment(env_data, actor, reason)
    pipeline_metrics(pipeline_id, days=30) -> Dict
    deployment_frequency(env_name, days=30) -> Dict

PIPELINE_TYPES byte-for-byte (4):
    GITHUB_ACTIONS, GITLAB_CI, JENKINS, ARGOCD

PIPELINE_STAGES byte-for-byte (6):
    BUILD, TEST, SECURITY_SCAN, STAGING_DEPLOY, PROD_DEPLOY, ROLLBACK

PIPELINE_STATES byte-for-byte (3): ACTIVE, PAUSED, ARCHIVED

ALLOWED_PIPELINE_TRANSITIONS (Rule 4):
    ACTIVE   → PAUSED | ARCHIVED
    PAUSED   → ACTIVE | ARCHIVED
    ARCHIVED → ()

RUN_STATES byte-for-byte (6):
    QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, TIMED_OUT

ALLOWED_RUN_TRANSITIONS (Rule 4):
    QUEUED    → RUNNING | CANCELLED
    RUNNING   → SUCCEEDED | FAILED | CANCELLED | TIMED_OUT
    SUCCEEDED → ()
    FAILED    → ()
    CANCELLED → ()
    TIMED_OUT → ()

ENVIRONMENT_TYPES byte-for-byte (5): DEV, TEST, STAGING, UAT, PRODUCTION

DEFAULT_BUILD_TIMEOUT_MINUTES = 30
DEFAULT_DEPLOY_TIMEOUT_MINUTES = 15

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PIPELINE_TYPES: Tuple[str, ...] = (
    "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS", "ARGOCD",
)

PIPELINE_STAGES: Tuple[str, ...] = (
    "BUILD", "TEST", "SECURITY_SCAN",
    "STAGING_DEPLOY", "PROD_DEPLOY", "ROLLBACK",
)

PIPELINE_STATES: Tuple[str, ...] = ("ACTIVE", "PAUSED", "ARCHIVED")

ALLOWED_PIPELINE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("PAUSED", "ARCHIVED"),
    "PAUSED":   ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}

RUN_STATES: Tuple[str, ...] = (
    "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT",
)

ALLOWED_RUN_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "QUEUED":    ("RUNNING", "CANCELLED"),
    "RUNNING":   ("SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"),
    "SUCCEEDED": (),
    "FAILED":    (),
    "CANCELLED": (),
    "TIMED_OUT": (),
}

ENVIRONMENT_TYPES: Tuple[str, ...] = (
    "DEV", "TEST", "STAGING", "UAT", "PRODUCTION",
)

DEFAULT_BUILD_TIMEOUT_MINUTES = 30
DEFAULT_DEPLOY_TIMEOUT_MINUTES = 15


class CICDEngine:
    """CI/CD pipeline registry + run tracking + DORA metrics."""

    def __init__(
        self,
        pipelines_path: Optional[Path] = None,
        runs_path: Optional[Path] = None,
        environments_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.pipelines_path = pipelines_path or base / "cicd_pipelines.json"
        self.runs_path = runs_path or base / "cicd_runs.json"
        self.environments_path = (
            environments_path or base / "cicd_environments.json"
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

    def register_pipeline(
        self, pipeline_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("pipeline_id", "pipeline_name", "pipeline_type",
                      "service_id", "stages"):
            if f not in pipeline_data or pipeline_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        if pipeline_data["pipeline_type"] not in PIPELINE_TYPES:
            return {"registered": False,
                       "error": f"invalid_pipeline_type:{pipeline_data['pipeline_type']}"}
        for s in pipeline_data["stages"]:
            if s not in PIPELINE_STAGES:
                return {"registered": False,
                           "error": f"invalid_stage:{s}"}
        records = self._load(self.pipelines_path,
                                "cicd_pipelines", ("pipeline_id",))
        if any(r.get("pipeline_id") == pipeline_data["pipeline_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_pipeline_id"}
        record = {
            "pipeline_id": pipeline_data["pipeline_id"],
            "pipeline_name": pipeline_data["pipeline_name"],
            "pipeline_type": pipeline_data["pipeline_type"],
            "service_id": pipeline_data["service_id"],
            "repository_url": pipeline_data.get("repository_url", ""),
            "stages": list(pipeline_data["stages"]),
            "build_timeout_minutes": pipeline_data.get(
                "build_timeout_minutes", DEFAULT_BUILD_TIMEOUT_MINUTES,
            ),
            "deploy_timeout_minutes": pipeline_data.get(
                "deploy_timeout_minutes", DEFAULT_DEPLOY_TIMEOUT_MINUTES,
            ),
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
        ok = self._save(self.pipelines_path, records,
                          "cicd_pipelines", "pipeline_id")
        return {"registered": ok, "pipeline_id": pipeline_data["pipeline_id"]}

    def transition_pipeline_state(
        self, pipeline_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in PIPELINE_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.pipelines_path,
                                "cicd_pipelines", ("pipeline_id",))
        for r in records:
            if r.get("pipeline_id") == pipeline_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_PIPELINE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.pipelines_path, records,
                                  "cicd_pipelines", "pipeline_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "pipeline_not_found"}

    def record_pipeline_run(
        self, run_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("run_id", "pipeline_id", "commit_sha",
                      "triggered_at"):
            if f not in run_data or not run_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        # Verify pipeline exists
        pipelines = self._load(self.pipelines_path,
                                      "cicd_pipelines", ("pipeline_id",))
        if not any(p.get("pipeline_id") == run_data["pipeline_id"]
                       for p in pipelines):
            return {"recorded": False, "error": "pipeline_not_found"}
        records = self._load(self.runs_path, "cicd_runs", ("run_id",))
        if any(r.get("run_id") == run_data["run_id"] for r in records):
            return {"recorded": False, "error": "duplicate_run_id"}
        record = {
            "run_id": run_data["run_id"],
            "pipeline_id": run_data["pipeline_id"],
            "commit_sha": run_data["commit_sha"],
            "branch": run_data.get("branch", ""),
            "triggered_by": run_data.get("triggered_by", actor),
            "triggered_at": run_data["triggered_at"],
            "target_environment": run_data.get("target_environment", ""),
            "state": "QUEUED",
            "started_at": "",
            "completed_at": "",
            "duration_seconds": 0,
            "transitions": [{
                "to": "QUEUED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.runs_path, records, "cicd_runs", "run_id")
        return {"recorded": ok, "run_id": run_data["run_id"]}

    def transition_run_state(
        self, run_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in RUN_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.runs_path, "cicd_runs", ("run_id",))
        for r in records:
            if r.get("run_id") == run_id:
                current = r.get("state", "QUEUED")
                allowed = ALLOWED_RUN_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                now = datetime.utcnow().isoformat()
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": now, "reason": reason,
                })
                if new_state == "RUNNING":
                    r["started_at"] = now
                if new_state in ("SUCCEEDED", "FAILED",
                                       "CANCELLED", "TIMED_OUT"):
                    r["completed_at"] = now
                    if r.get("started_at"):
                        try:
                            start = datetime.fromisoformat(r["started_at"])
                            end = datetime.fromisoformat(now)
                            r["duration_seconds"] = int(
                                (end - start).total_seconds(),
                            )
                        except Exception:
                            pass
                ok = self._save(self.runs_path, records,
                                  "cicd_runs", "run_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "run_not_found"}

    def register_environment(
        self, env_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("env_id", "env_name", "env_type"):
            if f not in env_data or not env_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if env_data["env_type"] not in ENVIRONMENT_TYPES:
            return {"registered": False,
                       "error": f"invalid_env_type:{env_data['env_type']}"}
        records = self._load(self.environments_path,
                                "cicd_environments", ("env_id",))
        if any(r.get("env_id") == env_data["env_id"] for r in records):
            return {"registered": False, "error": "duplicate_env_id"}
        record = {
            "env_id": env_data["env_id"],
            "env_name": env_data["env_name"],
            "env_type": env_data["env_type"],
            "deploy_targets": env_data.get("deploy_targets", []),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.environments_path, records,
                          "cicd_environments", "env_id")
        return {"registered": ok, "env_id": env_data["env_id"]}

    def pipeline_metrics(
        self, pipeline_id: str, days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        runs = self._load(self.runs_path, "cicd_runs", ("run_id",))
        recent = [r for r in runs
                       if r.get("pipeline_id") == pipeline_id
                       and r.get("triggered_at", "") >= cutoff]
        succeeded = [r for r in recent if r.get("state") == "SUCCEEDED"]
        failed = [r for r in recent if r.get("state") == "FAILED"]
        durations = [r["duration_seconds"] for r in succeeded
                          if r.get("duration_seconds", 0) > 0]
        avg_duration = (
            sum(durations) / len(durations) if durations else 0
        )
        success_rate = (
            len(succeeded) / len(recent) * 100 if recent else 0
        )
        return {
            "pipeline_id": pipeline_id,
            "window_days": days,
            "total_runs": len(recent),
            "succeeded": len(succeeded),
            "failed": len(failed),
            "success_rate_pct": round(success_rate, 1),
            "average_duration_seconds": round(avg_duration, 0),
        }

    def deployment_frequency(
        self, env_name: str, days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        runs = self._load(self.runs_path, "cicd_runs", ("run_id",))
        env_runs = [r for r in runs
                          if r.get("target_environment") == env_name
                          and r.get("state") == "SUCCEEDED"
                          and r.get("triggered_at", "") >= cutoff]
        return {
            "environment": env_name,
            "window_days": days,
            "successful_deployments": len(env_runs),
            "deployments_per_day": round(
                len(env_runs) / days, 2,
            ),
        }


def _self_test() -> None:
    import tempfile

    assert "GITHUB_ACTIONS" in PIPELINE_TYPES
    assert ALLOWED_PIPELINE_TRANSITIONS["ARCHIVED"] == ()
    assert "QUEUED" in RUN_STATES
    assert ALLOWED_RUN_TRANSITIONS["SUCCEEDED"] == ()
    assert "PRODUCTION" in ENVIRONMENT_TYPES
    assert DEFAULT_BUILD_TIMEOUT_MINUTES == 30
    assert DEFAULT_DEPLOY_TIMEOUT_MINUTES == 15

    with tempfile.TemporaryDirectory() as tmpdir:
        e = CICDEngine(
            pipelines_path=Path(tmpdir) / "p.json",
            runs_path=Path(tmpdir) / "r.json",
            environments_path=Path(tmpdir) / "e.json",
        )
        # Environment
        r = e.register_environment(
            {"env_id": "ENV-PROD", "env_name": "production",
             "env_type": "PRODUCTION"},
            actor="cto", reason="initial",
        )
        assert r["registered"]
        # Invalid type
        r = e.register_environment(
            {"env_id": "X", "env_name": "Y", "env_type": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Pipeline
        r = e.register_pipeline(
            {"pipeline_id": "PIPE-AUTH",
             "pipeline_name": "Auth pipeline",
             "pipeline_type": "GITHUB_ACTIONS",
             "service_id": "SVC-AUTH",
             "stages": ["BUILD", "TEST", "SECURITY_SCAN",
                          "STAGING_DEPLOY", "PROD_DEPLOY"]},
            actor="cto", reason="initial",
        )
        assert r["registered"]
        # Invalid stage
        r = e.register_pipeline(
            {"pipeline_id": "X", "pipeline_name": "Y",
             "pipeline_type": "GITHUB_ACTIONS", "service_id": "Z",
             "stages": ["BUILD", "WHATEVER"]},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Pipeline state
        r = e.transition_pipeline_state("PIPE-AUTH", "PAUSED",
                                              actor="cto", reason="freeze")
        assert r["transitioned"]
        r = e.transition_pipeline_state("PIPE-AUTH", "ACTIVE",
                                              actor="cto", reason="resume")
        assert r["transitioned"]

        # Pipeline run
        r = e.record_pipeline_run(
            {"run_id": "RUN-001", "pipeline_id": "PIPE-AUTH",
             "commit_sha": "abc123",
             "triggered_at": datetime.utcnow().isoformat(),
             "target_environment": "production"},
            actor="ci",
        )
        assert r["recorded"]
        # Pipeline not found
        r = e.record_pipeline_run(
            {"run_id": "X", "pipeline_id": "NOPE",
             "commit_sha": "def",
             "triggered_at": datetime.utcnow().isoformat()},
            actor="ci",
        )
        assert not r["recorded"]
        # Run state machine
        r = e.transition_run_state("RUN-001", "RUNNING",
                                          actor="ci", reason="started")
        assert r["transitioned"]
        r = e.transition_run_state("RUN-001", "SUCCEEDED",
                                          actor="ci", reason="green")
        assert r["transitioned"]
        # SUCCEEDED is terminal
        r = e.transition_run_state("RUN-001", "RUNNING",
                                          actor="ci", reason="x")
        assert not r["transitioned"]

        # Pipeline metrics
        m = e.pipeline_metrics("PIPE-AUTH", days=30)
        assert m["total_runs"] == 1
        assert m["succeeded"] == 1
        assert m["success_rate_pct"] == 100.0

        # Deployment frequency
        d = e.deployment_frequency("production", days=30)
        assert d["successful_deployments"] == 1

    print("  ✅ it_cicd self-test PASS")


if __name__ == "__main__":
    _self_test()

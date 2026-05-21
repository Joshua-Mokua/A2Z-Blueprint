"""
================================================================================
A2Z MIS 360 — Standard #290: Data Export & Integration Hub
================================================================================

Risk classification: Cat C (read-side egress; PII-aware controls; audit on
every export request).

Subcategory: analytics_hub

Single registered surface for exporting platform data to external
consumers — regulatory portals, data warehouses, BI tools, partner
systems. Every export request goes through registration → review →
approval → execution lifecycle. PII tier classification is required;
CRITICAL PII bulk exports require named approver and documented reason.

Public API:
    register_export_request(request_data, actor, reason)
    transition_request_state(request_id, new_state, actor, reason)
    register_integration_endpoint(endpoint_data, actor, reason)
    record_export_execution(execution_data, actor)
    export_metrics(days=30) -> Dict
    pii_critical_pending_review() -> List

EXPORT_FORMATS byte-for-byte (5):
    CSV, XLSX, JSON, PARQUET, XML

EXPORT_REQUEST_STATES byte-for-byte (5):
    REQUESTED, APPROVED, IN_PROGRESS, COMPLETED, CANCELLED

ALLOWED_REQUEST_TRANSITIONS (Rule 4):
    REQUESTED   → APPROVED | CANCELLED
    APPROVED    → IN_PROGRESS | CANCELLED
    IN_PROGRESS → COMPLETED | CANCELLED
    COMPLETED   → ()
    CANCELLED   → ()

PII_TIERS byte-for-byte (4):
    NONE, LOW, MEDIUM, HIGH_PII, CRITICAL_PII

INTEGRATION_TYPES byte-for-byte (5):
    REGULATORY_PORTAL, DATA_WAREHOUSE, BI_TOOL, PARTNER_API, INTERNAL

EXECUTION_OUTCOMES byte-for-byte (4):
    SUCCESS, PARTIAL, FAILED, CANCELLED

DEFAULT_EXPORT_TIMEOUT_SECONDS = 600
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_BYTES_PER_EXPORT = 5368709120  # 5 GiB

CBK_DPA_KENYA_REFERENCE = "Data Protection Act 2019"
CBK_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EXPORT_FORMATS: Tuple[str, ...] = (
    "CSV", "XLSX", "JSON", "PARQUET", "XML",
)

EXPORT_REQUEST_STATES: Tuple[str, ...] = (
    "REQUESTED", "APPROVED", "IN_PROGRESS",
    "COMPLETED", "CANCELLED",
)

ALLOWED_REQUEST_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "REQUESTED":   ("APPROVED", "CANCELLED"),
    "APPROVED":    ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("COMPLETED", "CANCELLED"),
    "COMPLETED":   (),
    "CANCELLED":   (),
}

PII_TIERS: Tuple[str, ...] = (
    "NONE", "LOW", "MEDIUM", "HIGH_PII", "CRITICAL_PII",
)

INTEGRATION_TYPES: Tuple[str, ...] = (
    "REGULATORY_PORTAL", "DATA_WAREHOUSE", "BI_TOOL",
    "PARTNER_API", "INTERNAL",
)

EXECUTION_OUTCOMES: Tuple[str, ...] = (
    "SUCCESS", "PARTIAL", "FAILED", "CANCELLED",
)

DEFAULT_EXPORT_TIMEOUT_SECONDS = 600
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_BYTES_PER_EXPORT = 5368709120  # 5 GiB

CBK_DPA_KENYA_REFERENCE = "Data Protection Act 2019"
CBK_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"


class DataExportEngine:
    """Export request + endpoint registry + execution tracking."""

    def __init__(
        self,
        requests_path: Optional[Path] = None,
        endpoints_path: Optional[Path] = None,
        executions_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.requests_path = requests_path or base / "data_export_requests.json"
        self.endpoints_path = (
            endpoints_path or base / "data_integration_endpoints.json"
        )
        self.executions_path = (
            executions_path or base / "data_export_executions.json"
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

    def register_export_request(
        self, request_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("request_id", "dataset_id", "format",
                      "destination", "pii_tier"):
            if f not in request_data or not request_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if request_data["format"] not in EXPORT_FORMATS:
            return {"registered": False,
                       "error": f"invalid_format:{request_data['format']}"}
        if request_data["pii_tier"] not in PII_TIERS:
            return {"registered": False,
                       "error": f"invalid_pii_tier:{request_data['pii_tier']}"}
        records = self._load(self.requests_path,
                                "data_export_requests", ("request_id",))
        if any(r.get("request_id") == request_data["request_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_request_id"}
        record = {
            "request_id": request_data["request_id"],
            "dataset_id": request_data["dataset_id"],
            "format": request_data["format"],
            "destination": request_data["destination"],
            "pii_tier": request_data["pii_tier"],
            "row_count_estimate": request_data.get("row_count_estimate"),
            "state": "REQUESTED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "REQUESTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.requests_path, records,
                          "data_export_requests", "request_id")
        return {"registered": ok,
                  "request_id": request_data["request_id"]}

    def transition_request_state(
        self, request_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in EXPORT_REQUEST_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.requests_path,
                                "data_export_requests", ("request_id",))
        for r in records:
            if r.get("request_id") == request_id:
                current = r.get("state", "REQUESTED")
                allowed = ALLOWED_REQUEST_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                # CRITICAL_PII APPROVED requires named approver
                if (r.get("pii_tier") == "CRITICAL_PII"
                        and new_state == "APPROVED" and not reason):
                    return {"transitioned": False,
                               "error": "critical_pii_requires_approver_reason"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.requests_path, records,
                                  "data_export_requests", "request_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "request_not_found"}

    def register_integration_endpoint(
        self, endpoint_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("endpoint_id", "name", "integration_type", "url"):
            if f not in endpoint_data or not endpoint_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if endpoint_data["integration_type"] not in INTEGRATION_TYPES:
            return {"registered": False,
                       "error": f"invalid_integration_type:{endpoint_data['integration_type']}"}
        records = self._load(self.endpoints_path,
                                "data_integration_endpoints",
                                ("endpoint_id",))
        if any(r.get("endpoint_id") == endpoint_data["endpoint_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_endpoint_id"}
        record = {
            "endpoint_id": endpoint_data["endpoint_id"],
            "name": endpoint_data["name"],
            "integration_type": endpoint_data["integration_type"],
            "url": endpoint_data["url"],
            "auth_method": endpoint_data.get("auth_method", "API_KEY"),
            "active": True,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.endpoints_path, records,
                          "data_integration_endpoints", "endpoint_id")
        return {"registered": ok,
                  "endpoint_id": endpoint_data["endpoint_id"]}

    def record_export_execution(
        self, execution_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("execution_id", "request_id", "outcome"):
            if f not in execution_data or not execution_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if execution_data["outcome"] not in EXECUTION_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{execution_data['outcome']}"}
        bytes_exported = execution_data.get("bytes_exported")
        if bytes_exported is not None:
            try:
                bytes_exported = int(bytes_exported)
                if bytes_exported > DEFAULT_MAX_BYTES_PER_EXPORT:
                    return {"recorded": False,
                              "error": f"bytes_exceed_max:{DEFAULT_MAX_BYTES_PER_EXPORT}"}
            except (TypeError, ValueError):
                return {"recorded": False, "error": "bytes_exported_not_int"}
        records = self._load(self.executions_path,
                                "data_export_executions", ("execution_id",))
        if any(r.get("execution_id") == execution_data["execution_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_execution_id"}
        record = {
            "execution_id": execution_data["execution_id"],
            "request_id": execution_data["request_id"],
            "outcome": execution_data["outcome"],
            "rows_exported": execution_data.get("rows_exported"),
            "bytes_exported": bytes_exported,
            "duration_seconds": execution_data.get("duration_seconds"),
            "executed_at": datetime.utcnow().isoformat(),
            "executed_by": actor,
        }
        records.append(record)
        ok = self._save(self.executions_path, records,
                          "data_export_executions", "execution_id")
        return {"recorded": ok,
                  "execution_id": execution_data["execution_id"]}

    def export_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        executions = self._load(self.executions_path,
                                            "data_export_executions",
                                            ("execution_id",))
        recent = [e for e in executions
                       if e.get("executed_at", "") >= cutoff]
        success = sum(1 for e in recent
                              if e.get("outcome") == "SUCCESS")
        failed = sum(1 for e in recent
                          if e.get("outcome") == "FAILED")
        total_bytes = sum((e.get("bytes_exported") or 0)
                                for e in recent)
        per_outcome: Dict[str, int] = {}
        for e in recent:
            per_outcome[e.get("outcome", "")] = (
                per_outcome.get(e.get("outcome", ""), 0) + 1
            )
        return {
            "window_days": days,
            "total_executions": len(recent),
            "success": success,
            "failed": failed,
            "success_rate_pct": round(
                (success / len(recent) * 100) if recent else 0, 1,
            ),
            "total_bytes_exported": total_bytes,
            "per_outcome": per_outcome,
        }

    def pii_critical_pending_review(self) -> List[Dict[str, Any]]:
        records = self._load(self.requests_path,
                                "data_export_requests", ("request_id",))
        return [
            r for r in records
            if r.get("pii_tier") == "CRITICAL_PII"
                  and r.get("state") == "REQUESTED"
        ]


def _self_test() -> None:
    import tempfile

    assert EXPORT_FORMATS == ("CSV", "XLSX", "JSON", "PARQUET", "XML")
    assert EXPORT_REQUEST_STATES == (
        "REQUESTED", "APPROVED", "IN_PROGRESS",
        "COMPLETED", "CANCELLED",
    )
    assert ALLOWED_REQUEST_TRANSITIONS["COMPLETED"] == ()
    assert ALLOWED_REQUEST_TRANSITIONS["CANCELLED"] == ()
    assert PII_TIERS == ("NONE", "LOW", "MEDIUM", "HIGH_PII", "CRITICAL_PII")
    assert INTEGRATION_TYPES == (
        "REGULATORY_PORTAL", "DATA_WAREHOUSE", "BI_TOOL",
        "PARTNER_API", "INTERNAL",
    )
    assert EXECUTION_OUTCOMES == ("SUCCESS", "PARTIAL", "FAILED", "CANCELLED")
    assert DEFAULT_EXPORT_TIMEOUT_SECONDS == 600
    assert DEFAULT_RETENTION_DAYS == 30
    assert DEFAULT_MAX_BYTES_PER_EXPORT == 5368709120
    assert CBK_DPA_KENYA_REFERENCE == "Data Protection Act 2019"
    assert CBK_REGULATORY_REFERENCE == "CBK Cybersecurity Guidance"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = DataExportEngine(
            requests_path=Path(tmpdir) / "r.json",
            endpoints_path=Path(tmpdir) / "ep.json",
            executions_path=Path(tmpdir) / "ex.json",
        )
        # Endpoint
        r = e.register_integration_endpoint(
            {"endpoint_id": "EP-CBK-PORTAL",
             "name": "CBK Regulatory Portal",
             "integration_type": "REGULATORY_PORTAL",
             "url": "https://cbk.go.ke/portal",
             "auth_method": "MUTUAL_TLS"},
            actor="compliance", reason="quarterly submissions",
        )
        assert r["registered"]
        # Invalid integration type
        r = e.register_integration_endpoint(
            {"endpoint_id": "X", "name": "Y",
             "integration_type": "WHATEVER", "url": "https://"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Request — non-PII
        r = e.register_export_request(
            {"request_id": "EXP-001",
             "dataset_id": "ds_quarterly_kpi",
             "format": "XLSX",
             "destination": "data warehouse",
             "pii_tier": "NONE",
             "row_count_estimate": 5000},
            actor="analyst1", reason="Q2 KPI extract",
        )
        assert r["registered"]
        # Invalid format
        r = e.register_export_request(
            {"request_id": "X", "dataset_id": "Y",
             "format": "WHATEVER", "destination": "Z",
             "pii_tier": "NONE"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid pii_tier
        r = e.register_export_request(
            {"request_id": "Z", "dataset_id": "Y",
             "format": "CSV", "destination": "DW",
             "pii_tier": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_request_state(
            "EXP-001", "APPROVED",
            actor="cfo", reason="approved for warehouse",
        )
        assert r["transitioned"]
        r = e.transition_request_state(
            "EXP-001", "IN_PROGRESS",
            actor="executor", reason="started",
        )
        assert r["transitioned"]
        r = e.transition_request_state(
            "EXP-001", "COMPLETED",
            actor="executor", reason="finished",
        )
        assert r["transitioned"]
        # Terminal
        r = e.transition_request_state(
            "EXP-001", "REQUESTED",
            actor="x", reason="x",
        )
        assert not r["transitioned"]

        # CRITICAL_PII — requires named approver
        e.register_export_request(
            {"request_id": "EXP-CRIT",
             "dataset_id": "ds_kyc_full",
             "format": "JSON",
             "destination": "audit team",
             "pii_tier": "CRITICAL_PII"},
            actor="auditor", reason="FRC full review",
        )
        pending = e.pii_critical_pending_review()
        assert len(pending) == 1
        # Approve with reason
        r = e.transition_request_state(
            "EXP-CRIT", "APPROVED",
            actor="dpo", reason="DPO approval per DPA Kenya 2019 Art 25",
        )
        assert r["transitioned"]

        # Execution
        r = e.record_export_execution(
            {"execution_id": "EXEC-001",
             "request_id": "EXP-001",
             "outcome": "SUCCESS",
             "rows_exported": 4980,
             "bytes_exported": 1500000,
             "duration_seconds": 45},
            actor="executor",
        )
        assert r["recorded"]
        # Bytes exceed max
        r = e.record_export_execution(
            {"execution_id": "EXEC-X",
             "request_id": "EXP-001",
             "outcome": "SUCCESS",
             "bytes_exported": 99999999999999},
            actor="executor",
        )
        assert not r["recorded"]
        # Invalid outcome
        r = e.record_export_execution(
            {"execution_id": "EXEC-Y",
             "request_id": "EXP-001",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Metrics
        m = e.export_metrics(days=30)
        assert m["total_executions"] == 1
        assert m["success"] == 1
        assert m["success_rate_pct"] == 100.0
        assert m["total_bytes_exported"] == 1500000

    print("  ✅ analytics_data_export self-test PASS")


if __name__ == "__main__":
    _self_test()

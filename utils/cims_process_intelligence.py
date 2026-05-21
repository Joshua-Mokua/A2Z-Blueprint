"""
================================================================================
A2Z MIS 360 — Standard #169: Process Intelligence & Digital Twin
================================================================================

Risk classification: Cat C (read-side observation; never modifies actual
process flow — produces a digital-twin representation that operations
teams query for bottleneck analysis).

Subcategory: cims (Customer Instructions Management System)

Real-time process mining with digital twin representation of every
instruction journey. Records process steps as the instruction moves
through the platform, captures step durations and outcomes, and exposes
bottleneck analytics. The digital twin is observation-only — it doesn't
control the live process; it represents it for analysis.

Public API:
    register_process_definition(definition_data, actor, reason)
    register_process_instance(instance_data, actor, reason)
    record_step_event(event_data, actor)
    transition_instance_state(instance_id, new_state, actor, reason)
    bottleneck_summary(process_id=None, days=30) -> Dict
    instances_in_state(state) -> List

PROCESS_INSTANCE_STATES byte-for-byte (5):
    PENDING, RUNNING, COMPLETED, FAILED, CANCELLED

ALLOWED_INSTANCE_TRANSITIONS (Rule 4):
    PENDING   → RUNNING | CANCELLED
    RUNNING   → COMPLETED | FAILED | CANCELLED
    COMPLETED → ()
    FAILED    → ()
    CANCELLED → ()

STEP_EVENT_TYPES byte-for-byte (5):
    STEP_STARTED, STEP_COMPLETED, STEP_FAILED,
    STEP_SKIPPED, STEP_RETRIED

STEP_OUTCOMES byte-for-byte (4):
    SUCCESS, FAILURE, TIMEOUT, SKIPPED

BOTTLENECK_TYPES byte-for-byte (4):
    DURATION_OUTLIER, RETRY_HEAVY, FAILURE_HOTSPOT, QUEUE_BUILDUP

DEFAULT_BOTTLENECK_DURATION_PERCENTILE = 95
DEFAULT_BOTTLENECK_RETRY_THRESHOLD = 3
DEFAULT_DIGITAL_TWIN_REFRESH_SECONDS = 60

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROCESS_INSTANCE_STATES: Tuple[str, ...] = (
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
)

ALLOWED_INSTANCE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PENDING":   ("RUNNING", "CANCELLED"),
    "RUNNING":   ("COMPLETED", "FAILED", "CANCELLED"),
    "COMPLETED": (),
    "FAILED":    (),
    "CANCELLED": (),
}

STEP_EVENT_TYPES: Tuple[str, ...] = (
    "STEP_STARTED", "STEP_COMPLETED", "STEP_FAILED",
    "STEP_SKIPPED", "STEP_RETRIED",
)

STEP_OUTCOMES: Tuple[str, ...] = (
    "SUCCESS", "FAILURE", "TIMEOUT", "SKIPPED",
)

BOTTLENECK_TYPES: Tuple[str, ...] = (
    "DURATION_OUTLIER", "RETRY_HEAVY",
    "FAILURE_HOTSPOT", "QUEUE_BUILDUP",
)

DEFAULT_BOTTLENECK_DURATION_PERCENTILE = 95
DEFAULT_BOTTLENECK_RETRY_THRESHOLD = 3
DEFAULT_DIGITAL_TWIN_REFRESH_SECONDS = 60


class ProcessIntelligenceEngine:
    """Process definition + instance + step-event registry."""

    def __init__(
        self,
        definitions_path: Optional[Path] = None,
        instances_path: Optional[Path] = None,
        events_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.definitions_path = (
            definitions_path or base / "cims_process_definitions.json"
        )
        self.instances_path = (
            instances_path or base / "cims_process_instances.json"
        )
        self.events_path = (
            events_path or base / "cims_process_step_events.json"
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

    def register_process_definition(
        self, definition_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("process_id", "name", "step_definitions"):
            if f not in definition_data or definition_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        if not isinstance(definition_data["step_definitions"], list):
            return {"registered": False,
                       "error": "step_definitions_must_be_list"}
        records = self._load(self.definitions_path,
                                "cims_process_definitions", ("process_id",))
        if any(r.get("process_id") == definition_data["process_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_process_id"}
        record = {
            "process_id": definition_data["process_id"],
            "name": definition_data["name"],
            "step_definitions": list(definition_data["step_definitions"]),
            "version": definition_data.get("version", "1.0"),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.definitions_path, records,
                          "cims_process_definitions", "process_id")
        return {"registered": ok,
                  "process_id": definition_data["process_id"]}

    def register_process_instance(
        self, instance_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("instance_id", "process_id", "subject_id"):
            if f not in instance_data or not instance_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        # Verify process definition exists
        defs = self._load(self.definitions_path,
                              "cims_process_definitions", ("process_id",))
        if not any(d.get("process_id") == instance_data["process_id"]
                       for d in defs):
            return {"registered": False, "error": "process_definition_not_found"}
        records = self._load(self.instances_path,
                                "cims_process_instances", ("instance_id",))
        if any(r.get("instance_id") == instance_data["instance_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_instance_id"}
        record = {
            "instance_id": instance_data["instance_id"],
            "process_id": instance_data["process_id"],
            "subject_id": instance_data["subject_id"],
            "state": "PENDING",
            "started_at": instance_data.get("started_at",
                                                          datetime.utcnow().isoformat()),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PENDING", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.instances_path, records,
                          "cims_process_instances", "instance_id")
        return {"registered": ok,
                  "instance_id": instance_data["instance_id"]}

    def record_step_event(
        self, event_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("event_id", "instance_id", "step_name", "event_type"):
            if f not in event_data or not event_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if event_data["event_type"] not in STEP_EVENT_TYPES:
            return {"recorded": False,
                       "error": f"invalid_event_type:{event_data['event_type']}"}
        outcome = event_data.get("outcome")
        if outcome and outcome not in STEP_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{outcome}"}
        records = self._load(self.events_path,
                                "cims_process_step_events", ("event_id",))
        if any(r.get("event_id") == event_data["event_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_event_id"}
        record = {
            "event_id": event_data["event_id"],
            "instance_id": event_data["instance_id"],
            "step_name": event_data["step_name"],
            "event_type": event_data["event_type"],
            "outcome": outcome or "",
            "duration_ms": event_data.get("duration_ms"),
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.events_path, records,
                          "cims_process_step_events", "event_id")
        return {"recorded": ok, "event_id": event_data["event_id"]}

    def transition_instance_state(
        self, instance_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in PROCESS_INSTANCE_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.instances_path,
                                "cims_process_instances", ("instance_id",))
        for r in records:
            if r.get("instance_id") == instance_id:
                current = r.get("state", "PENDING")
                allowed = ALLOWED_INSTANCE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                if new_state in ("COMPLETED", "FAILED", "CANCELLED"):
                    r["ended_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.instances_path, records,
                                  "cims_process_instances",
                                  "instance_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "instance_not_found"}

    def bottleneck_summary(
        self, process_id: Optional[str] = None, days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        events = self._load(self.events_path,
                                "cims_process_step_events", ("event_id",))
        recent = [e for e in events
                       if e.get("recorded_at", "") >= cutoff]

        # If process_id given, filter events whose instance belongs to it
        if process_id:
            instances = self._load(self.instances_path,
                                              "cims_process_instances",
                                              ("instance_id",))
            scoped_instances = {
                i.get("instance_id") for i in instances
                if i.get("process_id") == process_id
            }
            recent = [e for e in recent
                            if e.get("instance_id") in scoped_instances]

        # Group by step name
        per_step: Dict[str, Dict[str, Any]] = {}
        for e in recent:
            step = e.get("step_name", "")
            if step not in per_step:
                per_step[step] = {
                    "events": 0, "failures": 0, "retries": 0,
                    "durations_ms": [],
                }
            per_step[step]["events"] += 1
            if e.get("event_type") == "STEP_FAILED":
                per_step[step]["failures"] += 1
            if e.get("event_type") == "STEP_RETRIED":
                per_step[step]["retries"] += 1
            dur = e.get("duration_ms")
            if isinstance(dur, (int, float)):
                per_step[step]["durations_ms"].append(dur)

        bottlenecks: List[Dict[str, Any]] = []
        for step, stats in per_step.items():
            durations = stats["durations_ms"]
            avg_ms = (sum(durations) / len(durations)
                          if durations else 0)
            stats["avg_duration_ms"] = round(avg_ms, 1)
            stats.pop("durations_ms")
            # Flag bottleneck candidates
            if (stats["retries"]
                    >= DEFAULT_BOTTLENECK_RETRY_THRESHOLD):
                bottlenecks.append({
                    "step": step,
                    "type": "RETRY_HEAVY",
                    "value": stats["retries"],
                })
            if stats["failures"] > 0 and stats["events"] > 0:
                failure_rate = stats["failures"] / stats["events"]
                if failure_rate > 0.1:
                    bottlenecks.append({
                        "step": step,
                        "type": "FAILURE_HOTSPOT",
                        "value": round(failure_rate * 100, 1),
                    })

        return {
            "window_days": days,
            "process_id": process_id or "ALL",
            "total_events": len(recent),
            "per_step": per_step,
            "bottleneck_candidates": bottlenecks,
            "bottleneck_count": len(bottlenecks),
        }

    def instances_in_state(self, state: str) -> List[Dict[str, Any]]:
        if state not in PROCESS_INSTANCE_STATES:
            return []
        records = self._load(self.instances_path,
                                "cims_process_instances", ("instance_id",))
        return [r for r in records if r.get("state") == state]


def _self_test() -> None:
    import tempfile

    assert PROCESS_INSTANCE_STATES == (
        "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
    )
    assert ALLOWED_INSTANCE_TRANSITIONS["COMPLETED"] == ()
    assert ALLOWED_INSTANCE_TRANSITIONS["FAILED"] == ()
    assert ALLOWED_INSTANCE_TRANSITIONS["CANCELLED"] == ()
    assert STEP_EVENT_TYPES == (
        "STEP_STARTED", "STEP_COMPLETED", "STEP_FAILED",
        "STEP_SKIPPED", "STEP_RETRIED",
    )
    assert STEP_OUTCOMES == ("SUCCESS", "FAILURE", "TIMEOUT", "SKIPPED")
    assert BOTTLENECK_TYPES == (
        "DURATION_OUTLIER", "RETRY_HEAVY",
        "FAILURE_HOTSPOT", "QUEUE_BUILDUP",
    )
    assert DEFAULT_BOTTLENECK_DURATION_PERCENTILE == 95
    assert DEFAULT_BOTTLENECK_RETRY_THRESHOLD == 3
    assert DEFAULT_DIGITAL_TWIN_REFRESH_SECONDS == 60

    with tempfile.TemporaryDirectory() as tmpdir:
        e = ProcessIntelligenceEngine(
            definitions_path=Path(tmpdir) / "d.json",
            instances_path=Path(tmpdir) / "i.json",
            events_path=Path(tmpdir) / "e.json",
        )
        # Process definition
        r = e.register_process_definition(
            {"process_id": "PROC-FUNDS-TRANSFER",
             "name": "Funds Transfer Process",
             "step_definitions": [
                 "validate_input", "kyc_check", "fraud_check",
                 "balance_check", "execute_transfer", "notify_customer",
             ],
             "version": "1.0"},
            actor="ops-team", reason="initial",
        )
        assert r["registered"]
        # Bad step_definitions
        r = e.register_process_definition(
            {"process_id": "X", "name": "Y",
             "step_definitions": "not-a-list"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Instance
        r = e.register_process_instance(
            {"instance_id": "INST-001",
             "process_id": "PROC-FUNDS-TRANSFER",
             "subject_id": "INSTRUCTION-001"},
            actor="orchestrator", reason="started",
        )
        assert r["registered"]
        # Bad process
        r = e.register_process_instance(
            {"instance_id": "X", "process_id": "GHOST",
             "subject_id": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_instance_state(
            "INST-001", "RUNNING",
            actor="orchestrator", reason="step started",
        )
        assert r["transitioned"]

        # Step events
        for i, step in enumerate([
            "validate_input", "kyc_check", "fraud_check",
            "balance_check", "execute_transfer",
        ]):
            e.record_step_event(
                {"event_id": f"EVT-{i:03d}",
                 "instance_id": "INST-001",
                 "step_name": step,
                 "event_type": "STEP_COMPLETED",
                 "outcome": "SUCCESS",
                 "duration_ms": 50 + i * 100},
                actor="orchestrator",
            )
        # A retry-heavy step
        for i in range(5, 9):
            e.record_step_event(
                {"event_id": f"EVT-{i:03d}",
                 "instance_id": "INST-001",
                 "step_name": "fraud_check",
                 "event_type": "STEP_RETRIED",
                 "duration_ms": 200},
                actor="orchestrator",
            )
        # Bad event type
        r = e.record_step_event(
            {"event_id": "EVT-X", "instance_id": "INST-001",
             "step_name": "Y", "event_type": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        r = e.transition_instance_state(
            "INST-001", "COMPLETED",
            actor="orchestrator", reason="finished",
        )
        assert r["transitioned"]

        # Bottleneck summary
        bs = e.bottleneck_summary(
            process_id="PROC-FUNDS-TRANSFER", days=30,
        )
        assert bs["total_events"] >= 9
        # fraud_check should be flagged as RETRY_HEAVY
        retry_heavy = [b for b in bs["bottleneck_candidates"]
                                if b["type"] == "RETRY_HEAVY"]
        assert len(retry_heavy) == 1
        assert retry_heavy[0]["step"] == "fraud_check"

        # Instances in state
        completed = e.instances_in_state("COMPLETED")
        assert len(completed) == 1

    print("  ✅ cims_process_intelligence self-test PASS")


if __name__ == "__main__":
    _self_test()

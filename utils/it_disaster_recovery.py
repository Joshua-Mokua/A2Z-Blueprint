"""
================================================================================
A2Z MIS 360 — Standard #294: Disaster Recovery & Business Continuity
================================================================================

Risk classification: Cat B (regulatory: CBK Cybersecurity Guidance)

RTO < 4 hours, RPO < 15 minutes. Multi-region active-passive. Regular DR
drills. CBK Cybersecurity Guidance compliance.

Public API:
    register_dr_plan(plan_data, actor, reason)
    record_dr_drill(drill_data, actor)
    transition_drill_state(drill_id, new_state, actor, reason)
    register_runbook(runbook_data, actor, reason)
    measure_recovery(measurement_data, actor)
    rto_rpo_compliance(plan_id) -> Dict
    drill_history(plan_id, limit=10) -> List

DR_PLAN_TIERS byte-for-byte (4): TIER_0_REALTIME, TIER_1_NEAR_REALTIME,
                                    TIER_2_DAILY, TIER_3_BACKUP_RESTORE

DR_PLAN_STATES byte-for-byte (4): DRAFT, ACTIVE, DEPRECATED, ARCHIVED

ALLOWED_DR_PLAN_TRANSITIONS (Rule 4):
    DRAFT      → ACTIVE | ARCHIVED
    ACTIVE     → DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

DRILL_TYPES byte-for-byte (4):
    TABLETOP, WALKTHROUGH, SIMULATION, FULL_FAILOVER

DRILL_STATES byte-for-byte (5):
    SCHEDULED, IN_PROGRESS, COMPLETED, FAILED, CANCELLED

ALLOWED_DRILL_TRANSITIONS (Rule 4):
    SCHEDULED   → IN_PROGRESS | CANCELLED
    IN_PROGRESS → COMPLETED | FAILED | CANCELLED
    COMPLETED   → ()
    FAILED      → ()
    CANCELLED   → ()

DEFAULT_RTO_TARGET_HOURS = 4   # CBK Cybersecurity guidance
DEFAULT_RPO_TARGET_MINUTES = 15  # CBK Cybersecurity guidance

CBK_DR_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DR_PLAN_TIERS: Tuple[str, ...] = (
    "TIER_0_REALTIME", "TIER_1_NEAR_REALTIME",
    "TIER_2_DAILY", "TIER_3_BACKUP_RESTORE",
)

DR_PLAN_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED",
)

ALLOWED_DR_PLAN_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

DRILL_TYPES: Tuple[str, ...] = (
    "TABLETOP", "WALKTHROUGH", "SIMULATION", "FULL_FAILOVER",
)

DRILL_STATES: Tuple[str, ...] = (
    "SCHEDULED", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED",
)

ALLOWED_DRILL_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "SCHEDULED":   ("IN_PROGRESS", "CANCELLED"),
    "IN_PROGRESS": ("COMPLETED", "FAILED", "CANCELLED"),
    "COMPLETED":   (),
    "FAILED":      (),
    "CANCELLED":   (),
}

DEFAULT_RTO_TARGET_HOURS = 4
DEFAULT_RPO_TARGET_MINUTES = 15
CBK_DR_REGULATORY_REFERENCE = "CBK Cybersecurity Guidance"


class DisasterRecoveryEngine:
    """DR / BCP engine — RTO/RPO targets, drill tracking, CBK compliance."""

    def __init__(
        self,
        plans_path: Optional[Path] = None,
        drills_path: Optional[Path] = None,
        runbooks_path: Optional[Path] = None,
        measurements_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.plans_path = plans_path or base / "dr_plans.json"
        self.drills_path = drills_path or base / "dr_drills.json"
        self.runbooks_path = runbooks_path or base / "dr_runbooks.json"
        self.measurements_path = (
            measurements_path or base / "dr_measurements.json"
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

    def register_dr_plan(
        self, plan_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("plan_id", "plan_name", "service_id", "tier",
                      "rto_target_hours", "rpo_target_minutes"):
            if f not in plan_data or plan_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if plan_data["tier"] not in DR_PLAN_TIERS:
            return {"registered": False,
                       "error": f"invalid_tier:{plan_data['tier']}"}
        try:
            rto = Decimal(str(plan_data["rto_target_hours"]))
            rpo = Decimal(str(plan_data["rpo_target_minutes"]))
        except Exception:
            return {"registered": False, "error": "invalid_rto_or_rpo"}
        if rto <= Decimal("0") or rpo <= Decimal("0"):
            return {"registered": False, "error": "rto_rpo_must_be_positive"}
        records = self._load(self.plans_path, "dr_plans", ("plan_id",))
        if any(r.get("plan_id") == plan_data["plan_id"] for r in records):
            return {"registered": False, "error": "duplicate_plan_id"}
        record = {
            "plan_id": plan_data["plan_id"],
            "plan_name": plan_data["plan_name"],
            "service_id": plan_data["service_id"],
            "tier": plan_data["tier"],
            "rto_target_hours": str(rto),
            "rpo_target_minutes": str(rpo),
            "primary_region": plan_data.get("primary_region", ""),
            "dr_region": plan_data.get("dr_region", ""),
            "regulatory_reference": CBK_DR_REGULATORY_REFERENCE,
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
        ok = self._save(self.plans_path, records, "dr_plans", "plan_id")
        return {"registered": ok, "plan_id": plan_data["plan_id"]}

    def transition_plan_state(
        self, plan_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in DR_PLAN_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.plans_path, "dr_plans", ("plan_id",))
        for r in records:
            if r.get("plan_id") == plan_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_DR_PLAN_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.plans_path, records,
                                  "dr_plans", "plan_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "plan_not_found"}

    def record_dr_drill(
        self, drill_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("drill_id", "plan_id", "drill_type", "scheduled_for"):
            if f not in drill_data or not drill_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if drill_data["drill_type"] not in DRILL_TYPES:
            return {"recorded": False,
                       "error": f"invalid_drill_type:{drill_data['drill_type']}"}
        # Verify plan exists
        plans = self._load(self.plans_path, "dr_plans", ("plan_id",))
        if not any(p.get("plan_id") == drill_data["plan_id"]
                       for p in plans):
            return {"recorded": False, "error": "plan_not_found"}
        records = self._load(self.drills_path, "dr_drills", ("drill_id",))
        if any(r.get("drill_id") == drill_data["drill_id"] for r in records):
            return {"recorded": False, "error": "duplicate_drill_id"}
        record = {
            "drill_id": drill_data["drill_id"],
            "plan_id": drill_data["plan_id"],
            "drill_type": drill_data["drill_type"],
            "scheduled_for": drill_data["scheduled_for"],
            "objectives": drill_data.get("objectives", []),
            "participants": drill_data.get("participants", []),
            "state": "SCHEDULED",
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "SCHEDULED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.drills_path, records,
                          "dr_drills", "drill_id")
        return {"recorded": ok, "drill_id": drill_data["drill_id"]}

    def transition_drill_state(
        self, drill_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in DRILL_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.drills_path, "dr_drills", ("drill_id",))
        for r in records:
            if r.get("drill_id") == drill_id:
                current = r.get("state", "SCHEDULED")
                allowed = ALLOWED_DRILL_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.drills_path, records,
                                  "dr_drills", "drill_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "drill_not_found"}

    def register_runbook(
        self, runbook_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("runbook_id", "runbook_name", "plan_id", "steps"):
            if f not in runbook_data or runbook_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if not isinstance(runbook_data["steps"], list) or not runbook_data["steps"]:
            return {"registered": False, "error": "steps_must_be_non_empty_list"}
        records = self._load(self.runbooks_path,
                                "dr_runbooks", ("runbook_id",))
        if any(r.get("runbook_id") == runbook_data["runbook_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_runbook_id"}
        record = {
            "runbook_id": runbook_data["runbook_id"],
            "runbook_name": runbook_data["runbook_name"],
            "plan_id": runbook_data["plan_id"],
            "steps": runbook_data["steps"],
            "primary_owner": runbook_data.get("primary_owner", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.runbooks_path, records,
                          "dr_runbooks", "runbook_id")
        return {"registered": ok, "runbook_id": runbook_data["runbook_id"]}

    def measure_recovery(
        self, measurement_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("measurement_id", "drill_id", "actual_rto_hours",
                      "actual_rpo_minutes"):
            if f not in measurement_data or measurement_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        try:
            actual_rto = Decimal(str(measurement_data["actual_rto_hours"]))
            actual_rpo = Decimal(
                str(measurement_data["actual_rpo_minutes"]),
            )
        except Exception:
            return {"recorded": False, "error": "invalid_actual_rto_or_rpo"}
        if actual_rto < Decimal("0") or actual_rpo < Decimal("0"):
            return {"recorded": False,
                       "error": "actual_rto_rpo_cannot_be_negative"}
        # Verify drill exists
        drills = self._load(self.drills_path, "dr_drills", ("drill_id",))
        drill = next((d for d in drills
                          if d.get("drill_id") == measurement_data["drill_id"]),
                          None)
        if drill is None:
            return {"recorded": False, "error": "drill_not_found"}
        records = self._load(self.measurements_path,
                                "dr_measurements", ("measurement_id",))
        if any(r.get("measurement_id") == measurement_data["measurement_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_measurement_id"}
        record = {
            "measurement_id": measurement_data["measurement_id"],
            "drill_id": measurement_data["drill_id"],
            "plan_id": drill["plan_id"],
            "actual_rto_hours": str(actual_rto),
            "actual_rpo_minutes": str(actual_rpo),
            "notes": measurement_data.get("notes", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.measurements_path, records,
                          "dr_measurements", "measurement_id")
        return {"recorded": ok,
                  "measurement_id": measurement_data["measurement_id"]}

    def rto_rpo_compliance(self, plan_id: str) -> Dict[str, Any]:
        plans = self._load(self.plans_path, "dr_plans", ("plan_id",))
        plan = next((p for p in plans if p.get("plan_id") == plan_id), None)
        if plan is None:
            return {"found": False, "error": "plan_not_found"}
        target_rto = Decimal(plan["rto_target_hours"])
        target_rpo = Decimal(plan["rpo_target_minutes"])
        measurements = self._load(self.measurements_path,
                                          "dr_measurements",
                                          ("measurement_id",))
        plan_meas = [m for m in measurements
                          if m.get("plan_id") == plan_id]
        if not plan_meas:
            return {"found": True, "plan_id": plan_id, "no_data": True}
        rto_breaches = [m for m in plan_meas
                              if Decimal(m["actual_rto_hours"]) > target_rto]
        rpo_breaches = [m for m in plan_meas
                              if Decimal(m["actual_rpo_minutes"]) > target_rpo]
        cbk_compliant = (
            target_rto <= Decimal(str(DEFAULT_RTO_TARGET_HOURS))
            and target_rpo <= Decimal(str(DEFAULT_RPO_TARGET_MINUTES))
            and len(rto_breaches) == 0
            and len(rpo_breaches) == 0
        )
        return {
            "found": True,
            "plan_id": plan_id,
            "target_rto_hours": str(target_rto),
            "target_rpo_minutes": str(target_rpo),
            "measurement_count": len(plan_meas),
            "rto_breach_count": len(rto_breaches),
            "rpo_breach_count": len(rpo_breaches),
            "cbk_compliant": bool(cbk_compliant),
            "regulatory_reference": CBK_DR_REGULATORY_REFERENCE,
        }

    def drill_history(self, plan_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        records = self._load(self.drills_path, "dr_drills", ("drill_id",))
        plan_drills = [r for r in records if r.get("plan_id") == plan_id]
        plan_drills.sort(key=lambda x: x.get("scheduled_for", ""),
                              reverse=True)
        return plan_drills[:limit]


def _self_test() -> None:
    import tempfile

    assert "TIER_0_REALTIME" in DR_PLAN_TIERS
    assert ALLOWED_DR_PLAN_TRANSITIONS["ARCHIVED"] == ()
    assert "TABLETOP" in DRILL_TYPES
    assert ALLOWED_DRILL_TRANSITIONS["COMPLETED"] == ()
    assert DEFAULT_RTO_TARGET_HOURS == 4
    assert DEFAULT_RPO_TARGET_MINUTES == 15
    assert CBK_DR_REGULATORY_REFERENCE == "CBK Cybersecurity Guidance"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = DisasterRecoveryEngine(
            plans_path=Path(tmpdir) / "p.json",
            drills_path=Path(tmpdir) / "d.json",
            runbooks_path=Path(tmpdir) / "r.json",
            measurements_path=Path(tmpdir) / "m.json",
        )
        # Plan
        r = e.register_dr_plan(
            {"plan_id": "DR-CORE",
             "plan_name": "Core banking DR",
             "service_id": "SVC-FLEXCUBE",
             "tier": "TIER_1_NEAR_REALTIME",
             "rto_target_hours": "4",
             "rpo_target_minutes": "15",
             "primary_region": "af-south-1",
             "dr_region": "eu-west-2"},
            actor="cto", reason="CBK regulatory",
        )
        assert r["registered"]
        # Invalid tier
        r = e.register_dr_plan(
            {"plan_id": "X", "plan_name": "Y", "service_id": "Z",
             "tier": "FOO", "rto_target_hours": "1",
             "rpo_target_minutes": "5"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid RTO
        r = e.register_dr_plan(
            {"plan_id": "Y", "plan_name": "Z", "service_id": "T",
             "tier": "TIER_2_DAILY", "rto_target_hours": "-1",
             "rpo_target_minutes": "5"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Plan transitions
        r = e.transition_plan_state("DR-CORE", "ACTIVE",
                                          actor="cto", reason="approved")
        assert r["transitioned"]
        # Invalid transition (ACTIVE → DRAFT)
        r = e.transition_plan_state("DR-CORE", "DRAFT",
                                          actor="cto", reason="x")
        assert not r["transitioned"]

        # Drill
        r = e.record_dr_drill(
            {"drill_id": "DRL-001", "plan_id": "DR-CORE",
             "drill_type": "FULL_FAILOVER",
             "scheduled_for": "2026-06-01T10:00:00",
             "objectives": ["validate RTO", "validate RPO"]},
            actor="cto",
        )
        assert r["recorded"]
        # Plan not found
        r = e.record_dr_drill(
            {"drill_id": "X", "plan_id": "NOPE",
             "drill_type": "TABLETOP",
             "scheduled_for": "2026-06-01"},
            actor="x",
        )
        assert not r["recorded"]
        # Invalid drill type
        r = e.record_dr_drill(
            {"drill_id": "Y", "plan_id": "DR-CORE",
             "drill_type": "WHATEVER",
             "scheduled_for": "2026-06-01"},
            actor="x",
        )
        assert not r["recorded"]
        # Drill state machine
        r = e.transition_drill_state("DRL-001", "IN_PROGRESS",
                                            actor="cto",
                                            reason="drill started")
        assert r["transitioned"]
        r = e.transition_drill_state("DRL-001", "COMPLETED",
                                            actor="cto", reason="success")
        assert r["transitioned"]
        # COMPLETED is terminal
        r = e.transition_drill_state("DRL-001", "IN_PROGRESS",
                                            actor="cto", reason="x")
        assert not r["transitioned"]

        # Runbook
        r = e.register_runbook(
            {"runbook_id": "RB-001",
             "runbook_name": "FLEXCUBE Failover",
             "plan_id": "DR-CORE",
             "steps": ["Stop primary", "Promote DR replica",
                          "Update DNS", "Verify connectivity"]},
            actor="cto", reason="CBK request",
        )
        assert r["registered"]
        # Empty steps
        r = e.register_runbook(
            {"runbook_id": "X", "runbook_name": "Y",
             "plan_id": "DR-CORE", "steps": []},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Measurement (compliant — 3.5h RTO, 10min RPO)
        r = e.measure_recovery(
            {"measurement_id": "MEAS-001", "drill_id": "DRL-001",
             "actual_rto_hours": "3.5", "actual_rpo_minutes": "10"},
            actor="cto",
        )
        assert r["recorded"]
        c = e.rto_rpo_compliance("DR-CORE")
        assert c["found"]
        assert c["cbk_compliant"]
        assert c["rto_breach_count"] == 0
        # Breach measurement
        e.record_dr_drill(
            {"drill_id": "DRL-002", "plan_id": "DR-CORE",
             "drill_type": "SIMULATION",
             "scheduled_for": "2026-07-01"},
            actor="cto",
        )
        r = e.measure_recovery(
            {"measurement_id": "MEAS-002", "drill_id": "DRL-002",
             "actual_rto_hours": "5.0", "actual_rpo_minutes": "20"},
            actor="cto",
        )
        assert r["recorded"]
        c = e.rto_rpo_compliance("DR-CORE")
        assert not c["cbk_compliant"]
        assert c["rto_breach_count"] == 1
        assert c["rpo_breach_count"] == 1

        # Drill history
        h = e.drill_history("DR-CORE")
        assert len(h) == 2

    print("  ✅ it_disaster_recovery self-test PASS")


if __name__ == "__main__":
    _self_test()

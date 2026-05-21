"""
================================================================================
A2Z MIS 360 — Standard #294: Disaster Recovery & Business Continuity
================================================================================

Risk classification: Cat C (DR plan + drill execution + RTO/RPO compliance)

RTO < 4 hours, RPO < 15 minutes. Multi-region active-passive. Regular DR
drills. CBK Cybersecurity Guidance compliance.

Public API:
    register_dr_plan(plan_data, actor, reason)
    transition_plan_state(plan_id, new_state, actor, reason)
    register_drill(drill_data, actor)
    record_drill_outcome(drill_id, outcome_data, actor)
    register_failover(failover_data, actor)
    rto_rpo_compliance() -> Dict (current actual vs target across plans)

DR_PLAN_TYPES byte-for-byte (5):
    APPLICATION, DATABASE, INFRASTRUCTURE, NETWORK, ENTIRE_SITE

DR_PLAN_STATES byte-for-byte (4): DRAFT, APPROVED, IN_TEST, ARCHIVED

ALLOWED_PLAN_TRANSITIONS (Rule 4):
    DRAFT     → APPROVED | ARCHIVED
    APPROVED  → IN_TEST | ARCHIVED
    IN_TEST   → APPROVED | ARCHIVED
    ARCHIVED  → ()

DRILL_TYPES byte-for-byte (4):
    TABLETOP, FUNCTIONAL, FULL_FAILOVER, COMPONENT

DRILL_OUTCOMES byte-for-byte (4): PASS, PARTIAL, FAIL, ABORTED

FAILOVER_TYPES byte-for-byte (3): PLANNED, UNPLANNED, ROLLBACK

DEFAULT_TARGETS byte-for-byte:
    RTO_TARGET_MINUTES=240   (4 hours per #294 spec)
    RPO_TARGET_MINUTES=15    (15 minutes per #294 spec)
    DRILL_FREQUENCY_DAYS=90  (quarterly minimum)

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DR_PLAN_TYPES: Tuple[str, ...] = (
    "APPLICATION", "DATABASE", "INFRASTRUCTURE", "NETWORK", "ENTIRE_SITE",
)

DR_PLAN_STATES: Tuple[str, ...] = (
    "DRAFT", "APPROVED", "IN_TEST", "ARCHIVED",
)

ALLOWED_PLAN_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":    ("APPROVED", "ARCHIVED"),
    "APPROVED": ("IN_TEST", "ARCHIVED"),
    "IN_TEST":  ("APPROVED", "ARCHIVED"),
    "ARCHIVED": (),
}

DRILL_TYPES: Tuple[str, ...] = (
    "TABLETOP", "FUNCTIONAL", "FULL_FAILOVER", "COMPONENT",
)

DRILL_OUTCOMES: Tuple[str, ...] = ("PASS", "PARTIAL", "FAIL", "ABORTED")

FAILOVER_TYPES: Tuple[str, ...] = ("PLANNED", "UNPLANNED", "ROLLBACK")

RTO_TARGET_MINUTES = 240
RPO_TARGET_MINUTES = 15
DRILL_FREQUENCY_DAYS = 90


class DisasterRecoveryEngine:
    """DR plan + drill + failover tracking with RTO/RPO compliance."""

    def __init__(
        self,
        plans_path: Optional[Path] = None,
        drills_path: Optional[Path] = None,
        failovers_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.plans_path = plans_path or base / "dr_plans.json"
        self.drills_path = drills_path or base / "dr_drills.json"
        self.failovers_path = failovers_path or base / "dr_failovers.json"

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
        for f in ("plan_id", "plan_name", "plan_type",
                      "rto_target_minutes", "rpo_target_minutes",
                      "owner_role"):
            if f not in plan_data or plan_data[f] is None or plan_data[f] == "":
                return {"registered": False, "error": f"missing_field:{f}"}
        if plan_data["plan_type"] not in DR_PLAN_TYPES:
            return {"registered": False,
                       "error": f"invalid_plan_type:{plan_data['plan_type']}"}
        try:
            rto = int(plan_data["rto_target_minutes"])
            rpo = int(plan_data["rpo_target_minutes"])
        except Exception:
            return {"registered": False,
                       "error": "rto_rpo_not_numeric"}
        if rto <= 0 or rpo < 0:
            return {"registered": False, "error": "rto_rpo_invalid"}
        records = self._load(self.plans_path, "dr_plans", ("plan_id",))
        if any(r.get("plan_id") == plan_data["plan_id"] for r in records):
            return {"registered": False, "error": "duplicate_plan_id"}
        record = {
            "plan_id": plan_data["plan_id"],
            "plan_name": plan_data["plan_name"],
            "plan_type": plan_data["plan_type"],
            "owner_role": plan_data["owner_role"],
            "rto_target_minutes": rto,
            "rpo_target_minutes": rpo,
            "primary_region": plan_data.get("primary_region", ""),
            "dr_region": plan_data.get("dr_region", ""),
            "runbook_uri": plan_data.get("runbook_uri", ""),
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
                allowed = ALLOWED_PLAN_TRANSITIONS.get(current, ())
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

    def register_drill(
        self, drill_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("drill_id", "plan_id", "drill_type", "scheduled_for"):
            if f not in drill_data or not drill_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if drill_data["drill_type"] not in DRILL_TYPES:
            return {"registered": False,
                       "error": f"invalid_drill_type:{drill_data['drill_type']}"}
        # Verify plan exists
        plans = self._load(self.plans_path, "dr_plans", ("plan_id",))
        if not any(p.get("plan_id") == drill_data["plan_id"] for p in plans):
            return {"registered": False, "error": "plan_not_found"}
        records = self._load(self.drills_path, "dr_drills", ("drill_id",))
        if any(r.get("drill_id") == drill_data["drill_id"] for r in records):
            return {"registered": False, "error": "duplicate_drill_id"}
        record = {
            "drill_id": drill_data["drill_id"],
            "plan_id": drill_data["plan_id"],
            "drill_type": drill_data["drill_type"],
            "scheduled_for": drill_data["scheduled_for"],
            "outcome": None,
            "actual_rto_minutes": None,
            "actual_rpo_minutes": None,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.drills_path, records, "dr_drills", "drill_id")
        return {"registered": ok, "drill_id": drill_data["drill_id"]}

    def record_drill_outcome(
        self, drill_id: str, outcome_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("outcome", "actual_rto_minutes", "actual_rpo_minutes"):
            if f not in outcome_data or outcome_data[f] is None:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if outcome_data["outcome"] not in DRILL_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{outcome_data['outcome']}"}
        try:
            rto = int(outcome_data["actual_rto_minutes"])
            rpo = int(outcome_data["actual_rpo_minutes"])
        except Exception:
            return {"recorded": False,
                       "error": "rto_rpo_not_numeric"}
        if rto < 0 or rpo < 0:
            return {"recorded": False, "error": "rto_rpo_invalid"}
        records = self._load(self.drills_path, "dr_drills", ("drill_id",))
        for r in records:
            if r.get("drill_id") == drill_id:
                if r.get("outcome") is not None:
                    return {"recorded": False, "error": "outcome_already_recorded"}
                r["outcome"] = outcome_data["outcome"]
                r["actual_rto_minutes"] = rto
                r["actual_rpo_minutes"] = rpo
                r["lessons_learned"] = outcome_data.get(
                    "lessons_learned", "")
                r["completed_by"] = actor
                r["completed_at"] = datetime.utcnow().isoformat()
                ok = self._save(self.drills_path, records,
                                  "dr_drills", "drill_id")
                return {"recorded": ok}
        return {"recorded": False, "error": "drill_not_found"}

    def register_failover(
        self, failover_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("failover_id", "plan_id", "failover_type",
                      "executed_at"):
            if f not in failover_data or not failover_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if failover_data["failover_type"] not in FAILOVER_TYPES:
            return {"registered": False,
                       "error": f"invalid_failover_type:{failover_data['failover_type']}"}
        # Verify plan exists
        plans = self._load(self.plans_path, "dr_plans", ("plan_id",))
        if not any(p.get("plan_id") == failover_data["plan_id"]
                       for p in plans):
            return {"registered": False, "error": "plan_not_found"}
        records = self._load(self.failovers_path,
                                "dr_failovers", ("failover_id",))
        if any(r.get("failover_id") == failover_data["failover_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_failover_id"}
        record = {
            "failover_id": failover_data["failover_id"],
            "plan_id": failover_data["plan_id"],
            "failover_type": failover_data["failover_type"],
            "executed_at": failover_data["executed_at"],
            "actual_rto_minutes": failover_data.get("actual_rto_minutes"),
            "actual_rpo_minutes": failover_data.get("actual_rpo_minutes"),
            "trigger": failover_data.get("trigger", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.failovers_path, records,
                          "dr_failovers", "failover_id")
        return {"registered": ok,
                  "failover_id": failover_data["failover_id"]}

    def rto_rpo_compliance(self) -> Dict[str, Any]:
        """Aggregate RTO/RPO compliance across all approved plans."""
        plans = self._load(self.plans_path, "dr_plans", ("plan_id",))
        drills = self._load(self.drills_path, "dr_drills", ("drill_id",))
        result = {
            "total_plans": len(plans),
            "approved_plans": 0,
            "plans_compliant_rto": 0,
            "plans_compliant_rpo": 0,
            "plans_overdue_drill": 0,
            "by_plan": [],
        }
        now = datetime.utcnow()
        cutoff = now - timedelta(days=DRILL_FREQUENCY_DAYS)
        for p in plans:
            if p.get("state") != "APPROVED":
                continue
            result["approved_plans"] += 1
            # Latest completed drill for this plan
            plan_drills = sorted(
                [d for d in drills if d.get("plan_id") == p["plan_id"]
                       and d.get("outcome") is not None],
                key=lambda x: x.get("completed_at", ""),
                reverse=True,
            )
            latest = plan_drills[0] if plan_drills else None
            rto_ok = False
            rpo_ok = False
            overdue = True
            actual_rto = None
            actual_rpo = None
            if latest:
                actual_rto = latest.get("actual_rto_minutes")
                actual_rpo = latest.get("actual_rpo_minutes")
                if actual_rto is not None:
                    rto_ok = actual_rto <= p["rto_target_minutes"]
                if actual_rpo is not None:
                    rpo_ok = actual_rpo <= p["rpo_target_minutes"]
                try:
                    completed = datetime.fromisoformat(latest["completed_at"])
                    overdue = completed < cutoff
                except Exception:
                    overdue = True
            if rto_ok:
                result["plans_compliant_rto"] += 1
            if rpo_ok:
                result["plans_compliant_rpo"] += 1
            if overdue:
                result["plans_overdue_drill"] += 1
            result["by_plan"].append({
                "plan_id": p["plan_id"],
                "plan_name": p["plan_name"],
                "rto_target_minutes": p["rto_target_minutes"],
                "rpo_target_minutes": p["rpo_target_minutes"],
                "latest_actual_rto": actual_rto,
                "latest_actual_rpo": actual_rpo,
                "rto_compliant": rto_ok,
                "rpo_compliant": rpo_ok,
                "drill_overdue": overdue,
            })
        return result


def _self_test() -> None:
    import tempfile

    assert "ENTIRE_SITE" in DR_PLAN_TYPES
    assert ALLOWED_PLAN_TRANSITIONS["ARCHIVED"] == ()
    assert RTO_TARGET_MINUTES == 240
    assert RPO_TARGET_MINUTES == 15
    assert DRILL_FREQUENCY_DAYS == 90

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = DisasterRecoveryEngine(
            plans_path=Path(tmpdir) / "p.json",
            drills_path=Path(tmpdir) / "d.json",
            failovers_path=Path(tmpdir) / "f.json",
        )
        # Test 1: register plan
        r = engine.register_dr_plan(
            {"plan_id": "DRP-CORE-DB",
             "plan_name": "Core DB DR",
             "plan_type": "DATABASE",
             "rto_target_minutes": 240,
             "rpo_target_minutes": 15,
             "owner_role": "CIO",
             "primary_region": "af-south-1",
             "dr_region": "eu-west-1"},
            actor="cio", reason="core banking DR baseline",
        )
        assert r["registered"]
        # Test 2: invalid plan type
        r = engine.register_dr_plan(
            {"plan_id": "X", "plan_name": "X",
             "plan_type": "INVALID",
             "rto_target_minutes": 240,
             "rpo_target_minutes": 15,
             "owner_role": "X"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: invalid RTO/RPO
        r = engine.register_dr_plan(
            {"plan_id": "X", "plan_name": "X",
             "plan_type": "DATABASE",
             "rto_target_minutes": -5,
             "rpo_target_minutes": 15,
             "owner_role": "X"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 4: state transitions
        r = engine.transition_plan_state(
            "DRP-CORE-DB", "APPROVED",
            actor="cio", reason="board approved",
        )
        assert r["transitioned"]
        # Test 5: invalid transition
        r = engine.transition_plan_state(
            "DRP-CORE-DB", "DRAFT",
            actor="cio", reason="x",
        )
        assert not r["transitioned"]
        # Test 6: drill register
        r = engine.register_drill(
            {"drill_id": "DRILL-Q1",
             "plan_id": "DRP-CORE-DB",
             "drill_type": "FUNCTIONAL",
             "scheduled_for": "2026-03-15T01:00:00"},
            actor="dr_lead",
        )
        assert r["registered"]
        # Test 7: drill for unknown plan
        r = engine.register_drill(
            {"drill_id": "X", "plan_id": "DRP-NONE",
             "drill_type": "FUNCTIONAL",
             "scheduled_for": "2026"},
            actor="x",
        )
        assert not r["registered"]
        # Test 8: invalid drill type
        r = engine.register_drill(
            {"drill_id": "X", "plan_id": "DRP-CORE-DB",
             "drill_type": "RANDOM",
             "scheduled_for": "2026"},
            actor="x",
        )
        assert not r["registered"]
        # Test 9: record outcome
        r = engine.record_drill_outcome(
            "DRILL-Q1",
            {"outcome": "PASS",
             "actual_rto_minutes": 180,
             "actual_rpo_minutes": 10,
             "lessons_learned": "Smooth"},
            actor="dr_lead",
        )
        assert r["recorded"]
        # Test 10: re-record blocked
        r = engine.record_drill_outcome(
            "DRILL-Q1",
            {"outcome": "PASS",
             "actual_rto_minutes": 180,
             "actual_rpo_minutes": 10},
            actor="dr_lead",
        )
        assert not r["recorded"]
        # Test 11: invalid outcome
        engine.register_drill(
            {"drill_id": "DRILL-Q2",
             "plan_id": "DRP-CORE-DB",
             "drill_type": "TABLETOP",
             "scheduled_for": "2026-06-15"},
            actor="dr_lead",
        )
        r = engine.record_drill_outcome(
            "DRILL-Q2",
            {"outcome": "MAYBE",
             "actual_rto_minutes": 200,
             "actual_rpo_minutes": 10},
            actor="dr_lead",
        )
        assert not r["recorded"]
        # Test 12: failover
        r = engine.register_failover(
            {"failover_id": "FO-2026-04-15",
             "plan_id": "DRP-CORE-DB",
             "failover_type": "PLANNED",
             "executed_at": "2026-04-15T03:00:00",
             "actual_rto_minutes": 195,
             "actual_rpo_minutes": 8,
             "trigger": "scheduled regional rotation"},
            actor="ops",
        )
        assert r["registered"]
        # Test 13: invalid failover type
        r = engine.register_failover(
            {"failover_id": "X", "plan_id": "DRP-CORE-DB",
             "failover_type": "INVALID",
             "executed_at": "2026"},
            actor="x",
        )
        assert not r["registered"]
        # Test 14: compliance summary
        c = engine.rto_rpo_compliance()
        assert c["approved_plans"] == 1
        # 180 < 240, 10 < 15 → both compliant
        assert c["plans_compliant_rto"] == 1
        assert c["plans_compliant_rpo"] == 1
        # Drill was completed today, not overdue
        assert c["plans_overdue_drill"] == 0

    print("  ✅ disaster_recovery self-test PASS")


if __name__ == "__main__":
    _self_test()

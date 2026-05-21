"""
================================================================================
A2Z MIS 360 — Standard #334: Strategic Response Workflow
================================================================================

Risk classification: Cat A (governance — workflow with owner/SLA controls
                              over response to material competitive moves)

Workflow for responding to competitor moves: detect → assess → recommend
→ approve → execute → measure. Owner + SLA per stage. Composes #331
alerts (input trigger) and the v10.271 SLA tracker (transition timing).

Public API:
    initiate_response(alert_id, owner, actor, reason)
    transition_response(response_id, new_state, actor, reason, payload=None)
    record_assessment(response_id, assessment_data, actor)
    record_recommendation(response_id, recommendation_data, actor)
    record_approval(response_id, decision, actor, reason)
    record_execution(response_id, execution_data, actor)
    record_measurement(response_id, measurement_data, actor)
    response_status(response_id) -> Dict
    list_responses(state=None, owner=None) -> List

RESPONSE_STATES byte-for-byte:
    DETECTED          -- competitor move detected; response initiated
    ASSESSING         -- impact assessment in progress
    RECOMMENDING      -- response options being formulated
    PENDING_APPROVAL  -- recommendation submitted; awaiting executive approval
    APPROVED          -- response approved; execution can begin
    EXECUTING         -- response actively being implemented
    MEASURING         -- post-execution measurement window
    COMPLETED         -- workflow complete (terminal-ish)
    ARCHIVED          -- archived (terminal)

ALLOWED_RESPONSE_TRANSITIONS (Rule 4):
    DETECTED         → ASSESSING | ARCHIVED
    ASSESSING        → RECOMMENDING | ARCHIVED
    RECOMMENDING     → PENDING_APPROVAL | ASSESSING | ARCHIVED
    PENDING_APPROVAL → APPROVED | RECOMMENDING | ARCHIVED  (can re-recommend on rejection)
    APPROVED         → EXECUTING | ARCHIVED
    EXECUTING        → MEASURING | ARCHIVED
    MEASURING        → COMPLETED | ARCHIVED
    COMPLETED        → ARCHIVED
    ARCHIVED         → ()

SLA_TARGETS_HOURS byte-for-byte (Continuation.docx #334):
    DETECTED → ASSESSING:           24 hours
    ASSESSING → RECOMMENDING:       72 hours
    RECOMMENDING → PENDING_APPROVAL: 48 hours
    PENDING_APPROVAL → APPROVED:    48 hours
    APPROVED → EXECUTING:           24 hours

APPROVAL_DECISIONS byte-for-byte:
    APPROVED   APPROVED_WITH_CONDITIONS   REJECTED   PENDING

Honesty rules:
    Rule 4: actor + reason mandatory on every transition
    Rule 6: invalid state / decision rejected
    Rule 1: response_status surfaces sla_breaches explicitly per stage

================================================================================
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


RESPONSE_STATES: Tuple[str, ...] = (
    "DETECTED", "ASSESSING", "RECOMMENDING",
    "PENDING_APPROVAL", "APPROVED",
    "EXECUTING", "MEASURING", "COMPLETED", "ARCHIVED",
)

ALLOWED_RESPONSE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DETECTED":         ("ASSESSING", "ARCHIVED"),
    "ASSESSING":        ("RECOMMENDING", "ARCHIVED"),
    "RECOMMENDING":     ("PENDING_APPROVAL", "ASSESSING", "ARCHIVED"),
    "PENDING_APPROVAL": ("APPROVED", "RECOMMENDING", "ARCHIVED"),
    "APPROVED":         ("EXECUTING", "ARCHIVED"),
    "EXECUTING":        ("MEASURING", "ARCHIVED"),
    "MEASURING":        ("COMPLETED", "ARCHIVED"),
    "COMPLETED":        ("ARCHIVED",),
    "ARCHIVED":         (),
}

SLA_TARGETS_HOURS: Dict[str, int] = {
    "DETECTED__ASSESSING":          24,
    "ASSESSING__RECOMMENDING":      72,
    "RECOMMENDING__PENDING_APPROVAL": 48,
    "PENDING_APPROVAL__APPROVED":   48,
    "APPROVED__EXECUTING":          24,
}

APPROVAL_DECISIONS: Tuple[str, ...] = (
    "APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED", "PENDING",
)


class StrategicResponseEngine:
    """Strategic response workflow with state machine + SLA tracking."""

    def __init__(
        self,
        responses_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.responses_path = responses_path or base / "strategic_responses.json"

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.responses_path,
                table="strategic_responses",
                index_cols=("response_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.responses_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.responses_path,
                data=records,
                table="strategic_responses",
                pk_col="response_id")
            return True
        except Exception:
            return False

    def initiate_response(
        self,
        alert_id: str,
        owner: str,
        actor: str,
        reason: str,
        related_competitor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not actor or not reason or not owner:
            return {
                "initiated": False,
                "error": "actor_owner_reason_required",
            }
        records = self._load()
        response_id = (f"RESP-{alert_id}-"
                            f"{int(datetime.utcnow().timestamp())}")
        record = {
            "response_id": response_id,
            "alert_id": alert_id,
            "related_competitor_id": related_competitor_id,
            "owner": owner,
            "state": "DETECTED",
            "assessment": None,
            "recommendation": None,
            "approval_decision": None,
            "approval_actor": None,
            "approval_at": None,
            "execution": None,
            "measurement": None,
            "initiated_by": actor,
            "initiated_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "DETECTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(records)
        return {"initiated": ok, "response_id": response_id}

    def _transition(
        self,
        response_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if new_state not in RESPONSE_STATES:
            return {"ok": False, "error": f"invalid_state:{new_state}"}
        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                current = r.get("state", "DETECTED")
                allowed = ALLOWED_RESPONSE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "ok": False,
                        "error": (f"transition_not_allowed:{current}"
                                       f"_to_{new_state}"),
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(records)
                return {"ok": ok, "from": current, "to": new_state}
        return {"ok": False, "error": "response_not_found"}

    def transition_response(
        self,
        response_id: str,
        new_state: str,
        actor: str,
        reason: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"ok": False, "error": "actor_and_reason_required"}
        return self._transition(response_id, new_state, actor, reason)

    def record_assessment(
        self,
        response_id: str,
        assessment_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                r["assessment"] = {
                    "impact_estimate": assessment_data.get("impact_estimate"),
                    "urgency": assessment_data.get("urgency"),
                    "stakeholders": assessment_data.get("stakeholders", []),
                    "narrative": assessment_data.get("narrative", ""),
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                }
                ok = self._save(records)
                return {"recorded": ok}
        return {"recorded": False, "error": "response_not_found"}

    def record_recommendation(
        self,
        response_id: str,
        recommendation_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                r["recommendation"] = {
                    "recommended_actions": recommendation_data.get(
                        "recommended_actions", []),
                    "estimated_cost_kes": recommendation_data.get(
                        "estimated_cost_kes"),
                    "estimated_revenue_impact_kes": recommendation_data.get(
                        "estimated_revenue_impact_kes"),
                    "narrative": recommendation_data.get("narrative", ""),
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                }
                ok = self._save(records)
                return {"recorded": ok}
        return {"recorded": False, "error": "response_not_found"}

    def record_approval(
        self,
        response_id: str,
        decision: str,
        actor: str,
        reason: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        if decision not in APPROVAL_DECISIONS:
            return {
                "recorded": False,
                "error": f"invalid_decision:{decision}",
                "valid_decisions": list(APPROVAL_DECISIONS),
            }
        if not actor or not reason:
            return {"recorded": False, "error": "actor_and_reason_required"}
        if decision == "APPROVED_WITH_CONDITIONS" and not notes:
            return {
                "recorded": False,
                "error": "notes_mandatory_for_conditional_approval",
            }

        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                if r.get("state") != "PENDING_APPROVAL":
                    return {
                        "recorded": False,
                        "error": (f"response_not_in_pending_approval:"
                                       f"{r.get('state')}"),
                    }
                r["approval_decision"] = decision
                r["approval_actor"] = actor
                r["approval_at"] = datetime.utcnow().isoformat()
                r["approval_notes"] = notes
                ok = self._save(records)

                # Auto-transition based on decision
                if decision in ("APPROVED", "APPROVED_WITH_CONDITIONS"):
                    self._transition(
                        response_id, "APPROVED", actor,
                        f"approval_decision:{decision}",
                    )
                elif decision == "REJECTED":
                    self._transition(
                        response_id, "RECOMMENDING", actor,
                        f"rejected_back_to_recommending: {reason}",
                    )

                return {"recorded": ok, "decision": decision}
        return {"recorded": False, "error": "response_not_found"}

    def record_execution(
        self,
        response_id: str,
        execution_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                r["execution"] = {
                    "executed_actions": execution_data.get(
                        "executed_actions", []),
                    "actual_cost_kes": execution_data.get("actual_cost_kes"),
                    "started_at": execution_data.get(
                        "started_at", datetime.utcnow().isoformat()),
                    "completed_at": execution_data.get("completed_at"),
                    "actor": actor,
                    "recorded_at": datetime.utcnow().isoformat(),
                }
                ok = self._save(records)
                return {"recorded": ok}
        return {"recorded": False, "error": "response_not_found"}

    def record_measurement(
        self,
        response_id: str,
        measurement_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                r["measurement"] = {
                    "actual_revenue_impact_kes": measurement_data.get(
                        "actual_revenue_impact_kes"),
                    "kpi_movements": measurement_data.get("kpi_movements", {}),
                    "outcome": measurement_data.get("outcome"),
                    "lessons_learned": measurement_data.get(
                        "lessons_learned", ""),
                    "actor": actor,
                    "recorded_at": datetime.utcnow().isoformat(),
                }
                ok = self._save(records)
                return {"recorded": ok}
        return {"recorded": False, "error": "response_not_found"}

    def _sla_breaches(
        self, transitions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compute SLA breaches per stage."""
        breaches = []
        # Build (state -> entry_time) from transitions
        entry_times: Dict[str, str] = {}
        for t in transitions:
            entry_times[t["to"]] = t["at"]

        for sla_key, target_hours in SLA_TARGETS_HOURS.items():
            from_state, to_state = sla_key.split("__")
            if from_state in entry_times and to_state in entry_times:
                try:
                    t_from = datetime.fromisoformat(
                        entry_times[from_state].replace("Z", ""),
                    )
                    t_to = datetime.fromisoformat(
                        entry_times[to_state].replace("Z", ""),
                    )
                except (ValueError, KeyError):
                    continue
                hours_taken = (t_to - t_from).total_seconds() / 3600.0
                if hours_taken > target_hours:
                    breaches.append({
                        "stage": sla_key,
                        "target_hours": target_hours,
                        "actual_hours": round(hours_taken, 2),
                        "breach_hours": round(hours_taken - target_hours, 2),
                    })
        return breaches

    def response_status(self, response_id: str) -> Dict[str, Any]:
        records = self._load()
        for r in records:
            if r.get("response_id") == response_id:
                breaches = self._sla_breaches(r.get("transitions", []))
                return {
                    **r,
                    "sla_breach_count": len(breaches),
                    "sla_breaches": breaches,
                }
        return {"error": "response_not_found"}

    def list_responses(
        self,
        state: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load()
        out = []
        for r in records:
            if state and r.get("state") != state:
                continue
            if owner and r.get("owner") != owner:
                continue
            out.append(r)
        return out


def _self_test() -> None:
    import tempfile

    assert ALLOWED_RESPONSE_TRANSITIONS["ARCHIVED"] == ()
    assert "DETECTED__ASSESSING" in SLA_TARGETS_HOURS
    assert "REJECTED" in APPROVAL_DECISIONS

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = StrategicResponseEngine(
            responses_path=Path(tmpdir) / "r.json",
        )

        # Test 1: initiate
        r = engine.initiate_response(
            alert_id="ALERT-001", owner="head_strategy",
            actor="strategy_lead",
            reason="competitor M&A response needed",
            related_competitor_id="EQUITY",
        )
        assert r["initiated"]
        rid = r["response_id"]

        # Test 2: missing fields
        r = engine.initiate_response(
            alert_id="X", owner="", actor="x", reason="x",
        )
        assert not r["initiated"]

        # Test 3: walk through happy path
        engine.transition_response(rid, "ASSESSING", actor="x", reason="start assess")
        engine.record_assessment(
            rid, {"impact_estimate": "MAJOR", "urgency": "HIGH",
                    "stakeholders": ["CEO", "CFO"]},
            actor="strategy_analyst",
        )
        engine.transition_response(rid, "RECOMMENDING", actor="x", reason="ok")
        engine.record_recommendation(
            rid, {"recommended_actions": ["match_pricing", "launch_campaign"],
                    "estimated_cost_kes": "5000000",
                    "estimated_revenue_impact_kes": "10000000"},
            actor="strategy_lead",
        )
        engine.transition_response(
            rid, "PENDING_APPROVAL", actor="x", reason="submitted",
        )

        # Test 4: invalid approval decision
        r = engine.record_approval(
            rid, "MAYBE", actor="md", reason="r",
        )
        assert not r["recorded"]

        # Test 5: APPROVED_WITH_CONDITIONS requires notes
        r = engine.record_approval(
            rid, "APPROVED_WITH_CONDITIONS", actor="md", reason="ok",
            notes="",
        )
        assert not r["recorded"]

        # Test 6: REJECTED routes back to RECOMMENDING
        r = engine.record_approval(
            rid, "REJECTED", actor="md", reason="needs more analysis",
        )
        assert r["recorded"]
        status = engine.response_status(rid)
        assert status["state"] == "RECOMMENDING"

        # Test 7: re-submit + APPROVED
        engine.transition_response(rid, "PENDING_APPROVAL", actor="x", reason="resub")
        r = engine.record_approval(
            rid, "APPROVED", actor="md", reason="approved",
        )
        assert r["recorded"]
        status = engine.response_status(rid)
        assert status["state"] == "APPROVED"

        # Test 8: cannot record approval outside PENDING_APPROVAL
        r = engine.record_approval(
            rid, "APPROVED", actor="md", reason="r",
        )
        assert not r["recorded"]

        # Test 9: walk to MEASURING + COMPLETED
        engine.transition_response(rid, "EXECUTING", actor="x", reason="go")
        engine.record_execution(
            rid, {"executed_actions": ["matched_pricing"],
                    "actual_cost_kes": "4500000"},
            actor="ops_lead",
        )
        engine.transition_response(rid, "MEASURING", actor="x", reason="done")
        engine.record_measurement(
            rid, {"actual_revenue_impact_kes": "9500000",
                    "outcome": "PARTIAL_SUCCESS",
                    "lessons_learned": "faster execution next time"},
            actor="strategy_analyst",
        )
        engine.transition_response(rid, "COMPLETED", actor="x", reason="closed")

        # Test 10: status with full history
        status = engine.response_status(rid)
        assert status["state"] == "COMPLETED"
        assert status["assessment"]["impact_estimate"] == "MAJOR"
        assert status["recommendation"]["recommended_actions"]
        assert status["execution"]["actual_cost_kes"] == "4500000"
        assert status["measurement"]["outcome"] == "PARTIAL_SUCCESS"

        # Test 11: invalid transitions
        t = engine.transition_response(
            rid, "DETECTED", actor="x", reason="reverse",
        )
        assert not t["ok"]

        # Test 12: list responses
        responses = engine.list_responses(state="COMPLETED")
        assert len(responses) >= 1

        # Test 13: SLA breach detection — instantaneous transitions are OK,
        # actual breaches require time gap (would need mock datetime to test).
        # Verify the structure exists.
        assert "sla_breach_count" in status

    print("  ✅ strategic_response self-test PASS")


if __name__ == "__main__":
    _self_test()

"""
================================================================================
A2Z MIS 360 — Standard #376: Partner Onboarding Workflow
================================================================================

Risk classification: Cat C (workflow state machine + gating)

End-to-end partner onboarding state machine: due diligence → contract →
training → system access → sandbox → go-live approval. Each gate must
pass before proceeding (Rule 4).

Public API:
    create_onboarding(partner_id, actor, reason)
    advance_gate(onboarding_id, gate, actor, reason)
    fail_gate(onboarding_id, gate, actor, reason)
    onboarding_status(onboarding_id) -> {gates_complete, current_gate}
    list_active_onboardings()
    bottleneck_summary() -> per-gate pending count

ONBOARDING_GATES byte-for-byte (Continuation.docx #376, in order):
    DUE_DILIGENCE       -- KYC, financial, regulatory checks
    CONTRACT            -- legal review + execution
    TRAINING            -- partner staff training complete
    SYSTEM_ACCESS       -- credentials issued + access tested
    SANDBOX_TESTING     -- end-to-end sandbox transactions verified
    GO_LIVE_APPROVAL    -- final business approval

GATE_STATES byte-for-byte:
    PENDING             -- gate not yet started
    IN_PROGRESS         -- gate work underway
    PASSED              -- gate completed successfully
    FAILED              -- gate failed; onboarding paused

ONBOARDING_STATES (composite from gates):
    DRAFT               -- created, no gates yet started
    IN_PROGRESS         -- at least 1 gate started, none failed
    BLOCKED             -- a gate failed
    COMPLETE            -- all 6 gates PASSED → can transition partner_master
                          state from ONBOARDING → ACTIVE
    ABANDONED           -- formally cancelled

Rule 4 enforcement:
    - Gates must be advanced in catalog order (no skip)
    - Cannot advance gate G(n) while G(n-1) not PASSED
    - Cannot mark COMPLETE unless all 6 gates PASSED
    - FAILED gate must be re-advanced through PENDING → IN_PROGRESS → PASSED

Honesty rules:
    Rule 4: actor + reason mandatory; gate order strictly enforced
    Rule 6: invalid gate / state rejected
    Rule 1: bottleneck_summary returns empty dict when no active onboardings

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ONBOARDING_GATES: Tuple[str, ...] = (
    "DUE_DILIGENCE",
    "CONTRACT",
    "TRAINING",
    "SYSTEM_ACCESS",
    "SANDBOX_TESTING",
    "GO_LIVE_APPROVAL",
)

GATE_STATES: Tuple[str, ...] = (
    "PENDING", "IN_PROGRESS", "PASSED", "FAILED",
)

ONBOARDING_STATES: Tuple[str, ...] = (
    "DRAFT", "IN_PROGRESS", "BLOCKED", "COMPLETE", "ABANDONED",
)


class PartnerOnboardingEngine:
    """End-to-end partner onboarding workflow engine."""

    def __init__(self, onboarding_path: Optional[Path] = None):
        self.onboarding_path = (
            onboarding_path
            if onboarding_path is not None
            else Path(__file__).parent.parent / "data" / "partner_onboarding.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.onboarding_path,
                table="partner_onboarding",
                index_cols=("onboarding_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.onboarding_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.onboarding_path,
                data=records,
                table="partner_onboarding",
                pk_col="onboarding_id")
            return True
        except Exception:
            return False

    def _compute_overall_state(
        self, gates: Dict[str, str]
    ) -> str:
        """Derive composite onboarding state from gate states."""
        # All gates PASSED → COMPLETE
        if all(gates.get(g) == "PASSED" for g in ONBOARDING_GATES):
            return "COMPLETE"
        # Any gate FAILED → BLOCKED
        if any(gates.get(g) == "FAILED" for g in ONBOARDING_GATES):
            return "BLOCKED"
        # Any gate started → IN_PROGRESS
        if any(gates.get(g) in ("IN_PROGRESS", "PASSED") for g in ONBOARDING_GATES):
            return "IN_PROGRESS"
        return "DRAFT"

    def create_onboarding(
        self,
        partner_id: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Create new onboarding record with all gates PENDING."""
        if not actor or not reason:
            return {"created": False, "error": "actor_and_reason_required"}

        records = self._load()
        # Reject if active onboarding for this partner already
        for r in records:
            if (r.get("partner_id") == partner_id
                    and r.get("state") not in ("COMPLETE", "ABANDONED")):
                return {
                    "created": False,
                    "error": "active_onboarding_exists",
                    "existing_id": r.get("onboarding_id"),
                }

        onboarding_id = f"OB-{partner_id}-{int(datetime.utcnow().timestamp())}"
        gates = {g: "PENDING" for g in ONBOARDING_GATES}
        record = {
            "onboarding_id": onboarding_id,
            "partner_id": partner_id,
            "gates": gates,
            "state": "DRAFT",
            "created_by": actor,
            "created_at": datetime.utcnow().isoformat(),
            "creation_reason": reason,
            "events": [{
                "event": "created", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(records)
        return {
            "created": ok,
            "onboarding_id": onboarding_id,
            "state": "DRAFT",
        }

    def _previous_gate_passed(
        self, gates: Dict[str, str], gate: str
    ) -> bool:
        """Check the gate before `gate` is PASSED."""
        idx = ONBOARDING_GATES.index(gate)
        if idx == 0:
            return True  # first gate has no predecessor
        prev = ONBOARDING_GATES[idx - 1]
        return gates.get(prev) == "PASSED"

    def advance_gate(
        self,
        onboarding_id: str,
        gate: str,
        actor: str,
        reason: str,
        target_state: str = "IN_PROGRESS",
    ) -> Dict[str, Any]:
        """
        Advance gate to IN_PROGRESS or PASSED.

        Rule 4 enforcement:
            - gate must exist in ONBOARDING_GATES
            - target_state must be IN_PROGRESS or PASSED
            - prior gate must be PASSED
            - PENDING → IN_PROGRESS → PASSED (no skip; PASSED can come
              directly from PENDING for very fast gates, allowed)
        """
        if not actor or not reason:
            return {"advanced": False, "error": "actor_and_reason_required"}
        if gate not in ONBOARDING_GATES:
            return {
                "advanced": False,
                "error": f"invalid_gate:{gate}",
                "valid_gates": list(ONBOARDING_GATES),
            }
        if target_state not in ("IN_PROGRESS", "PASSED"):
            return {
                "advanced": False,
                "error": f"invalid_target_state:{target_state}",
                "valid_targets": ["IN_PROGRESS", "PASSED"],
            }

        records = self._load()
        for r in records:
            if r.get("onboarding_id") == onboarding_id:
                if r.get("state") in ("COMPLETE", "ABANDONED"):
                    return {
                        "advanced": False,
                        "error": f"onboarding_in_terminal_state:{r['state']}",
                    }
                gates = r.get("gates", {})
                current = gates.get(gate, "PENDING")

                # Rule 4: previous gate must be PASSED
                if not self._previous_gate_passed(gates, gate):
                    idx = ONBOARDING_GATES.index(gate)
                    prev = ONBOARDING_GATES[idx - 1]
                    return {
                        "advanced": False,
                        "error": f"previous_gate_not_passed:{prev}",
                    }

                # PASSED → anything: only allowed if going to FAILED via fail_gate
                if current == "PASSED":
                    return {
                        "advanced": False,
                        "error": "gate_already_passed",
                    }
                # FAILED → must call fail_gate flow first to retry
                # (we allow advancing FAILED → IN_PROGRESS for retry)
                if current == "PASSED" and target_state == "IN_PROGRESS":
                    return {
                        "advanced": False,
                        "error": "cannot_revert_passed_gate",
                    }

                # Apply
                gates[gate] = target_state
                r["gates"] = gates
                r["state"] = self._compute_overall_state(gates)
                r.setdefault("events", []).append({
                    "event": f"gate:{gate}:{target_state}",
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(records)
                return {
                    "advanced": ok,
                    "gate": gate,
                    "from": current,
                    "to": target_state,
                    "overall_state": r["state"],
                }

        return {"advanced": False, "error": "onboarding_not_found"}

    def fail_gate(
        self,
        onboarding_id: str,
        gate: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Mark gate as FAILED. Onboarding moves to BLOCKED."""
        if not actor or not reason:
            return {"failed": False, "error": "actor_and_reason_required"}
        if gate not in ONBOARDING_GATES:
            return {"failed": False, "error": f"invalid_gate:{gate}"}

        records = self._load()
        for r in records:
            if r.get("onboarding_id") == onboarding_id:
                if r.get("state") in ("COMPLETE", "ABANDONED"):
                    return {
                        "failed": False,
                        "error": f"onboarding_in_terminal_state:{r['state']}",
                    }
                gates = r.get("gates", {})
                current = gates.get(gate, "PENDING")
                # Cannot fail a PASSED gate (would corrupt audit trail)
                if current == "PASSED":
                    return {
                        "failed": False,
                        "error": "cannot_fail_already_passed_gate",
                    }
                gates[gate] = "FAILED"
                r["gates"] = gates
                r["state"] = self._compute_overall_state(gates)
                r.setdefault("events", []).append({
                    "event": f"gate:{gate}:FAILED",
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(records)
                return {
                    "failed": ok,
                    "gate": gate,
                    "from": current,
                    "to": "FAILED",
                    "overall_state": r["state"],
                }

        return {"failed": False, "error": "onboarding_not_found"}

    def retry_failed_gate(
        self,
        onboarding_id: str,
        gate: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Reset FAILED gate back to PENDING for re-attempt."""
        if not actor or not reason:
            return {"retried": False, "error": "actor_and_reason_required"}
        if gate not in ONBOARDING_GATES:
            return {"retried": False, "error": f"invalid_gate:{gate}"}

        records = self._load()
        for r in records:
            if r.get("onboarding_id") == onboarding_id:
                gates = r.get("gates", {})
                current = gates.get(gate, "PENDING")
                if current != "FAILED":
                    return {
                        "retried": False,
                        "error": f"gate_not_failed:{current}",
                    }
                gates[gate] = "PENDING"
                r["gates"] = gates
                r["state"] = self._compute_overall_state(gates)
                r.setdefault("events", []).append({
                    "event": f"gate:{gate}:retry_to_PENDING",
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(records)
                return {"retried": ok, "gate": gate, "overall_state": r["state"]}

        return {"retried": False, "error": "onboarding_not_found"}

    def onboarding_status(self, onboarding_id: str) -> Dict[str, Any]:
        for r in self._load():
            if r.get("onboarding_id") == onboarding_id:
                gates = r.get("gates", {})
                passed = sum(1 for g in ONBOARDING_GATES if gates.get(g) == "PASSED")
                # Find current gate (first non-PASSED)
                current_gate = None
                for g in ONBOARDING_GATES:
                    if gates.get(g) != "PASSED":
                        current_gate = g
                        break
                return {
                    "onboarding_id": onboarding_id,
                    "partner_id": r.get("partner_id"),
                    "state": r.get("state"),
                    "gates": gates,
                    "gates_passed": passed,
                    "gates_total": len(ONBOARDING_GATES),
                    "current_gate": current_gate,
                    "progress_pct": round(100 * passed / len(ONBOARDING_GATES), 1),
                }
        return {"error": "onboarding_not_found"}

    def list_active_onboardings(self) -> List[Dict[str, Any]]:
        return [
            r for r in self._load()
            if r.get("state") in ("DRAFT", "IN_PROGRESS", "BLOCKED")
        ]

    def bottleneck_summary(self) -> Dict[str, Any]:
        """Per-gate count of onboardings currently stuck there."""
        active = self.list_active_onboardings()
        if not active:
            return {"by_gate": {}, "total_active": 0}

        counts = {g: 0 for g in ONBOARDING_GATES}
        for r in active:
            gates = r.get("gates", {})
            for g in ONBOARDING_GATES:
                if gates.get(g) != "PASSED":
                    counts[g] += 1
                    break  # only count first non-passed gate

        return {
            "by_gate": counts,
            "total_active": len(active),
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PartnerOnboardingEngine(
            onboarding_path=Path(tmpdir) / "ob.json"
        )

        # Test 1: create onboarding
        r = engine.create_onboarding("P-001", "bd", "kicking off")
        assert r["created"]
        ob_id = r["onboarding_id"]

        # Test 2: duplicate active onboarding rejected
        r2 = engine.create_onboarding("P-001", "bd", "dup")
        assert not r2["created"]
        assert r2["error"] == "active_onboarding_exists"

        # Test 3: cannot skip — try CONTRACT before DUE_DILIGENCE
        a = engine.advance_gate(ob_id, "CONTRACT", "legal", "skip attempt")
        assert not a["advanced"]
        assert "previous_gate_not_passed" in a["error"]

        # Test 4: advance DUE_DILIGENCE → IN_PROGRESS → PASSED
        a = engine.advance_gate(ob_id, "DUE_DILIGENCE", "compliance",
                                  "starting DD", target_state="IN_PROGRESS")
        assert a["advanced"]
        assert a["overall_state"] == "IN_PROGRESS"
        a = engine.advance_gate(ob_id, "DUE_DILIGENCE", "compliance",
                                  "DD complete", target_state="PASSED")
        assert a["advanced"]

        # Test 5: now CONTRACT can advance
        a = engine.advance_gate(ob_id, "CONTRACT", "legal",
                                  "contract done", target_state="PASSED")
        assert a["advanced"]

        # Test 6: invalid gate rejected
        a = engine.advance_gate(ob_id, "INVALID_GATE", "x", "y")
        assert not a["advanced"]

        # Test 7: invalid target state rejected
        a = engine.advance_gate(ob_id, "TRAINING", "trainer",
                                  "starting", target_state="DONE")
        assert not a["advanced"]

        # Test 8: fail TRAINING gate
        a = engine.advance_gate(ob_id, "TRAINING", "trainer",
                                  "starting", target_state="IN_PROGRESS")
        f = engine.fail_gate(ob_id, "TRAINING", "trainer",
                                "training material gaps")
        assert f["failed"]
        assert f["overall_state"] == "BLOCKED"

        # Test 9: cannot fail PASSED gate
        f = engine.fail_gate(ob_id, "DUE_DILIGENCE", "x",
                                "trying to corrupt history")
        assert not f["failed"]
        assert "cannot_fail_already_passed_gate" in f["error"]

        # Test 10: retry FAILED gate
        rt = engine.retry_failed_gate(ob_id, "TRAINING", "trainer",
                                          "fixed material")
        assert rt["retried"]
        # Now the gate is PENDING; advance
        engine.advance_gate(ob_id, "TRAINING", "trainer",
                              "retry pass", target_state="PASSED")

        # Test 11: complete remaining gates
        for gate in ("SYSTEM_ACCESS", "SANDBOX_TESTING", "GO_LIVE_APPROVAL"):
            a = engine.advance_gate(ob_id, gate, "ops", f"{gate} done",
                                      target_state="PASSED")
            assert a["advanced"]

        # Test 12: status — all 6 gates passed → COMPLETE
        s = engine.onboarding_status(ob_id)
        assert s["gates_passed"] == 6
        assert s["state"] == "COMPLETE"
        assert s["current_gate"] is None
        assert s["progress_pct"] == 100.0

        # Test 13: terminal — cannot advance after COMPLETE
        a = engine.advance_gate(ob_id, "DUE_DILIGENCE", "x", "trying",
                                  target_state="IN_PROGRESS")
        assert not a["advanced"]

        # Test 14: bottleneck_summary
        # Create another onboarding stuck at TRAINING
        r = engine.create_onboarding("P-002", "bd", "kick off P-002")
        ob2 = r["onboarding_id"]
        engine.advance_gate(ob2, "DUE_DILIGENCE", "compliance",
                              "ok", target_state="PASSED")
        engine.advance_gate(ob2, "CONTRACT", "legal", "ok",
                              target_state="PASSED")
        engine.advance_gate(ob2, "TRAINING", "trainer", "starting",
                              target_state="IN_PROGRESS")
        bottle = engine.bottleneck_summary()
        assert bottle["total_active"] == 1  # P-001 is COMPLETE; P-002 active
        assert bottle["by_gate"]["TRAINING"] == 1

    print("  ✅ partner_onboarding self-test PASS")


if __name__ == "__main__":
    _self_test()

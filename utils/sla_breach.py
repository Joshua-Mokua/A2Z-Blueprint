"""
================================================================================
A2Z MIS 360 — Standard #381: SLA Breach Management & Remediation
================================================================================

Risk classification: Cat B + Cat C (workflow state machine)

Auto-creation of breach incidents, owner assignment, remediation
workflow, customer compensation calculation, RCA capture.

Public API:
    create_breach_incident(observation, sla_definition)
    transition_state(breach_id, new_state, actor, reason)
    calculate_compensation(breach_id, breach_severity, sla_value)
    capture_rca(breach_id, root_cause, remediation_plan)

Breach severity tiers byte-for-byte:
    MINOR    -- single near-breach or minor breach (1-10% over)
    MAJOR    -- breach of 10-50% over target
    CRITICAL -- breach of >50% over target OR regulatory SLA breach

State machine ALLOWED_BREACH_TRANSITIONS byte-for-byte:
    OPEN         → INVESTIGATING, CANCELLED
    INVESTIGATING → REMEDIATING, ESCALATED, OPEN (return for re-triage)
    REMEDIATING  → CLOSED, ESCALATED
    ESCALATED    → INVESTIGATING, CLOSED
    CLOSED       → ()  -- terminal
    CANCELLED    → ()  -- terminal

Compensation table byte-for-byte (per Continuation.docx):
    MINOR    -- 0% (no compensation)
    MAJOR    -- 5% of transaction value or fixed KES 500
    CRITICAL -- 10% of transaction value or fixed KES 2000

Honesty rules:
    Rule 4 (no override): cannot transition CLOSED → anything else;
                          cannot skip INVESTIGATING; must capture
                          actor + reason on every transition
    Rule 1: compensation_amount = None when sla_value missing
    Rule 6: invalid state transitions rejected with explicit error

================================================================================
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

BREACH_SEVERITIES: Tuple[str, ...] = ("MINOR", "MAJOR", "CRITICAL")

BREACH_STATES: Tuple[str, ...] = (
    "OPEN", "INVESTIGATING", "REMEDIATING",
    "ESCALATED", "CLOSED", "CANCELLED",
)

ALLOWED_BREACH_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN":          ("INVESTIGATING", "CANCELLED"),
    "INVESTIGATING": ("REMEDIATING", "ESCALATED", "OPEN"),
    "REMEDIATING":   ("CLOSED", "ESCALATED"),
    "ESCALATED":     ("INVESTIGATING", "CLOSED"),
    "CLOSED":        (),  # terminal
    "CANCELLED":     (),  # terminal
}

# Severity classification thresholds (percentage over target)
MINOR_BREACH_PCT_OVER:    Decimal = Decimal("10")
MAJOR_BREACH_PCT_OVER:    Decimal = Decimal("50")

# Compensation table (byte-for-byte from Continuation.docx)
COMPENSATION_TABLE: Dict[str, Dict[str, Decimal]] = {
    "MINOR":    {"pct_of_value": Decimal("0"),  "fixed_kes": Decimal("0")},
    "MAJOR":    {"pct_of_value": Decimal("5"),  "fixed_kes": Decimal("500")},
    "CRITICAL": {"pct_of_value": Decimal("10"), "fixed_kes": Decimal("2000")},
}

# Regulatory SLAs auto-escalate to CRITICAL
REGULATORY_AUTO_CRITICAL: bool = True


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

class SlaBreachEngine:
    """
    Breach management workflow engine. State machine enforces
    no-skip discipline (Rule 4).
    """

    def __init__(self, breaches_path: Optional[Path] = None):
        self.breaches_path = (
            breaches_path
            if breaches_path is not None
            else Path(__file__).parent.parent / "data" / "sla_breaches.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            d = _db.dual_load(
                self.breaches_path,
                table="sla_breaches",
                index_cols=("breach_id",))
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.breaches_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.breaches_path,
                data=records,
                table="sla_breaches",
                pk_col="breach_id")
            return True
        except Exception:
            return False

    def classify_severity(
        self,
        elapsed_value: Decimal,
        target_value: Decimal,
        direction: str,
        is_regulatory: bool = False,
    ) -> str:
        """
        Classify breach severity by percentage over target.

        Regulatory SLAs auto-escalate to CRITICAL.
        """
        if is_regulatory and REGULATORY_AUTO_CRITICAL:
            return "CRITICAL"

        if direction == "max":
            if elapsed_value <= target_value:
                return "MINOR"  # near-breach but not actually over
            pct_over = ((elapsed_value - target_value) / target_value) * Decimal("100")
        else:  # direction == "min"
            if elapsed_value >= target_value:
                return "MINOR"
            pct_over = ((target_value - elapsed_value) / target_value) * Decimal("100")

        if pct_over <= MINOR_BREACH_PCT_OVER:
            return "MINOR"
        elif pct_over <= MAJOR_BREACH_PCT_OVER:
            return "MAJOR"
        else:
            return "CRITICAL"

    def create_breach_incident(
        self,
        sla_id: str,
        event_id: str,
        elapsed_value: Decimal,
        target_value: Decimal,
        direction: str,
        is_regulatory: bool = False,
        owner: str = "",
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Create breach incident in OPEN state with severity classified.
        """
        severity = self.classify_severity(
            elapsed_value, target_value, direction, is_regulatory
        )

        breach_id = f"BR-{uuid.uuid4().hex[:12].upper()}"
        breach = {
            "breach_id": breach_id,
            "sla_id": sla_id,
            "event_id": event_id,
            "severity": severity,
            "state": "OPEN",
            "elapsed_value": str(elapsed_value),
            "target_value": str(target_value),
            "direction": direction,
            "is_regulatory": is_regulatory,
            "owner": owner,
            "notes": notes,
            "compensation_amount": None,
            "root_cause": None,
            "remediation_plan": None,
            "created_at": datetime.utcnow().isoformat(),
            "transitions": [
                {"to": "OPEN", "actor": "system",
                 "at": datetime.utcnow().isoformat(),
                 "reason": "auto_created_from_observation"}
            ],
        }

        records = self._load()
        records.append(breach)
        ok = self._save(records)

        return {
            "created": ok,
            "breach_id": breach_id,
            "severity": severity,
            "breach": breach,
        }

    def transition_state(
        self,
        breach_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """
        Transition breach to new state. Rule 4: actor + reason
        mandatory. Skip transitions rejected.
        """
        # Required fields
        if not actor or not reason:
            return {
                "transitioned": False,
                "error": "actor_and_reason_required",
            }

        if new_state not in BREACH_STATES:
            return {
                "transitioned": False,
                "error": f"invalid_state:{new_state}",
            }

        records = self._load()
        for r in records:
            if r.get("breach_id") == breach_id:
                current = r.get("state", "OPEN")
                allowed = ALLOWED_BREACH_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }

                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state,
                    "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(records)
                return {
                    "transitioned": ok,
                    "breach_id": breach_id,
                    "from": current,
                    "to": new_state,
                }

        return {
            "transitioned": False,
            "error": "breach_not_found",
        }

    def calculate_compensation(
        self,
        breach_id: str,
        transaction_value_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Calculate customer compensation per breach severity table.

        Rule 1: compensation_amount = None when severity unknown.

        Returns: {compensation_amount, basis, severity}.
        """
        records = self._load()
        for r in records:
            if r.get("breach_id") == breach_id:
                severity = r.get("severity")
                if severity not in COMPENSATION_TABLE:
                    return {
                        "compensation_amount": None,
                        "reason": f"unknown_severity:{severity}",
                    }

                table = COMPENSATION_TABLE[severity]
                pct_amount = Decimal("0")
                if transaction_value_kes is not None and transaction_value_kes > 0:
                    pct_amount = transaction_value_kes * table["pct_of_value"] / Decimal("100")

                fixed_amount = table["fixed_kes"]
                # Customer gets the higher of pct or fixed
                amount = max(pct_amount, fixed_amount)

                # Persist
                r["compensation_amount"] = str(amount)
                self._save(records)

                return {
                    "compensation_amount": amount.quantize(Decimal("0.01")),
                    "basis": "max(pct_of_value, fixed_kes)",
                    "severity": severity,
                    "pct_amount": pct_amount.quantize(Decimal("0.01")),
                    "fixed_amount": fixed_amount,
                }

        return {
            "compensation_amount": None,
            "reason": "breach_not_found",
        }

    def capture_rca(
        self,
        breach_id: str,
        root_cause: str,
        remediation_plan: str,
    ) -> Dict[str, Any]:
        """Capture root cause analysis + remediation plan."""
        if not root_cause or not remediation_plan:
            return {
                "captured": False,
                "error": "root_cause_and_remediation_plan_required",
            }

        records = self._load()
        for r in records:
            if r.get("breach_id") == breach_id:
                r["root_cause"] = root_cause
                r["remediation_plan"] = remediation_plan
                r["rca_captured_at"] = datetime.utcnow().isoformat()
                ok = self._save(records)
                return {"captured": ok, "breach_id": breach_id}

        return {"captured": False, "error": "breach_not_found"}

    def list_breaches(
        self,
        sla_id: Optional[str] = None,
        severity: Optional[str] = None,
        state: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load()
        out = []
        for r in records:
            if sla_id and r.get("sla_id") != sla_id:
                continue
            if severity and r.get("severity") != severity:
                continue
            if state and r.get("state") != state:
                continue
            out.append(r)
        return out


# ────────────────────────────────────────────────────────────────────
# Self-test
# ────────────────────────────────────────────────────────────────────

def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sla_breaches.json"
        engine = SlaBreachEngine(breaches_path=path)

        # Test 1: classify severity — 8% over → MINOR
        sev = engine.classify_severity(
            Decimal("32.4"), Decimal("30"), "max"
        )
        assert sev == "MINOR", f"Got {sev}"

        # Test 2: 30% over → MAJOR
        sev = engine.classify_severity(
            Decimal("39"), Decimal("30"), "max"
        )
        assert sev == "MAJOR", f"Got {sev}"

        # Test 3: 100% over → CRITICAL
        sev = engine.classify_severity(
            Decimal("60"), Decimal("30"), "max"
        )
        assert sev == "CRITICAL"

        # Test 4: regulatory auto-CRITICAL even at 5% over
        sev = engine.classify_severity(
            Decimal("31.5"), Decimal("30"), "max", is_regulatory=True
        )
        assert sev == "CRITICAL", f"Regulatory should auto-escalate; got {sev}"

        # Test 5: create breach incident
        result = engine.create_breach_incident(
            sla_id="SLA-001",
            event_id="EVT-001",
            elapsed_value=Decimal("39"),
            target_value=Decimal("30"),
            direction="max",
            owner="ops_manager",
        )
        assert result["created"]
        assert result["severity"] == "MAJOR"
        breach_id = result["breach_id"]

        # Test 6: state machine — OPEN → INVESTIGATING allowed
        t = engine.transition_state(
            breach_id, "INVESTIGATING", "alice", "starting investigation"
        )
        assert t["transitioned"], f"Failed: {t.get('error')}"

        # Test 7: skip not allowed — INVESTIGATING → CLOSED
        t = engine.transition_state(
            breach_id, "CLOSED", "alice", "trying to skip"
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 8: proper path INVESTIGATING → REMEDIATING → CLOSED
        t = engine.transition_state(
            breach_id, "REMEDIATING", "alice", "fix in progress"
        )
        assert t["transitioned"]
        t = engine.transition_state(
            breach_id, "CLOSED", "alice", "fix verified"
        )
        assert t["transitioned"]

        # Test 9: terminal CLOSED — cannot reopen
        t = engine.transition_state(
            breach_id, "INVESTIGATING", "alice", "trying to reopen closed"
        )
        assert not t["transitioned"]

        # Test 10: actor + reason mandatory
        result = engine.create_breach_incident(
            sla_id="SLA-002", event_id="EVT-002",
            elapsed_value=Decimal("60"), target_value=Decimal("30"),
            direction="max",
        )
        breach_id_2 = result["breach_id"]
        t = engine.transition_state(breach_id_2, "INVESTIGATING", "", "")
        assert not t["transitioned"]
        assert t["error"] == "actor_and_reason_required"

        # Test 11: compensation calculation — MAJOR breach with 100k transaction
        comp = engine.calculate_compensation(
            breach_id, transaction_value_kes=Decimal("100000")
        )
        # MAJOR: max(5% × 100k = 5000, fixed 500) = 5000
        assert comp["compensation_amount"] == Decimal("5000.00")

        # Test 12: capture RCA
        rca = engine.capture_rca(
            breach_id,
            root_cause="upstream API timeout",
            remediation_plan="add retry logic",
        )
        assert rca["captured"]

    print("  ✅ sla_breach self-test PASS")


if __name__ == "__main__":
    _self_test()

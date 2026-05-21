"""
================================================================================
A2Z MIS 360 — Standard #168: Straight-Through Processing (STP) Engine
================================================================================

Risk classification: Cat C (read-side decision; never auto-executes the
instruction itself — the STP decision is a routing recommendation only;
actual execution flows through the relevant downstream banking engine).

Subcategory: cims (Customer Instructions Management System)

Automated STP decision engine for standard, low-risk instructions. Takes
the classified intent (#167) plus the customer risk tier and instruction
profile, and returns a decision: APPROVED_FOR_STP (route to automated
execution), REJECTED_FOR_STP (route to manual review), or MANUAL_REVIEW
(below confidence threshold). The engine does NOT execute anything
itself — it only records the decision and routing recommendation.

Public API:
    register_stp_request(request_data, actor, reason)
    record_stp_decision(decision_data, actor, reason)
    transition_decision_state(request_id, new_state, actor, reason)
    register_eligibility_rule(rule_data, actor, reason)
    stp_metrics(days=30) -> Dict
    pending_manual_review() -> List

STP_DECISION_STATES byte-for-byte (5):
    EVALUATING, APPROVED_FOR_STP, REJECTED_FOR_STP,
    MANUAL_REVIEW, EXECUTED

ALLOWED_DECISION_TRANSITIONS (Rule 4):
    EVALUATING        → APPROVED_FOR_STP | REJECTED_FOR_STP | MANUAL_REVIEW
    APPROVED_FOR_STP  → EXECUTED | MANUAL_REVIEW
    REJECTED_FOR_STP  → MANUAL_REVIEW | EXECUTED
    MANUAL_REVIEW     → EXECUTED
    EXECUTED          → ()

RISK_TIERS byte-for-byte (4):
    LOW, MEDIUM, HIGH, ENHANCED_DUE_DILIGENCE

ELIGIBILITY_CRITERIA byte-for-byte (6):
    AMOUNT_THRESHOLD, CHANNEL_TRUST, CUSTOMER_RISK_TIER,
    INSTRUCTION_TYPE, KYC_FRESHNESS, BLACKLIST_CHECK

REJECTION_REASONS byte-for-byte (5):
    EXCEEDS_AMOUNT_LIMIT, RISK_TIER_TOO_HIGH,
    KYC_STALE, BLACKLIST_HIT, ELIGIBILITY_RULE_FAILED

DEFAULT_STP_AMOUNT_LIMIT_LOW_RISK = 100000
DEFAULT_STP_AMOUNT_LIMIT_MEDIUM_RISK = 25000
DEFAULT_STP_DECISION_TIMEOUT_SECONDS = 10
DEFAULT_KYC_FRESHNESS_DAYS = 365

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


STP_DECISION_STATES: Tuple[str, ...] = (
    "EVALUATING", "APPROVED_FOR_STP", "REJECTED_FOR_STP",
    "MANUAL_REVIEW", "EXECUTED",
)

ALLOWED_DECISION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "EVALUATING":       ("APPROVED_FOR_STP", "REJECTED_FOR_STP",
                              "MANUAL_REVIEW"),
    "APPROVED_FOR_STP": ("EXECUTED", "MANUAL_REVIEW"),
    "REJECTED_FOR_STP": ("MANUAL_REVIEW", "EXECUTED"),
    "MANUAL_REVIEW":    ("EXECUTED",),
    "EXECUTED":         (),
}

RISK_TIERS: Tuple[str, ...] = (
    "LOW", "MEDIUM", "HIGH", "ENHANCED_DUE_DILIGENCE",
)

ELIGIBILITY_CRITERIA: Tuple[str, ...] = (
    "AMOUNT_THRESHOLD", "CHANNEL_TRUST", "CUSTOMER_RISK_TIER",
    "INSTRUCTION_TYPE", "KYC_FRESHNESS", "BLACKLIST_CHECK",
)

REJECTION_REASONS: Tuple[str, ...] = (
    "EXCEEDS_AMOUNT_LIMIT", "RISK_TIER_TOO_HIGH",
    "KYC_STALE", "BLACKLIST_HIT", "ELIGIBILITY_RULE_FAILED",
)

DEFAULT_STP_AMOUNT_LIMIT_LOW_RISK = 100000
DEFAULT_STP_AMOUNT_LIMIT_MEDIUM_RISK = 25000
DEFAULT_STP_DECISION_TIMEOUT_SECONDS = 10
DEFAULT_KYC_FRESHNESS_DAYS = 365


class StraightThroughProcessingEngine:
    """STP decision registry — read-side only, never auto-executes."""

    def __init__(
        self,
        requests_path: Optional[Path] = None,
        decisions_path: Optional[Path] = None,
        rules_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.requests_path = (
            requests_path or base / "cims_stp_requests.json"
        )
        self.decisions_path = (
            decisions_path or base / "cims_stp_decisions.json"
        )
        self.rules_path = (
            rules_path or base / "cims_stp_eligibility_rules.json"
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

    def register_stp_request(
        self, request_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("request_id", "instruction_id", "instruction_type",
                      "customer_risk_tier"):
            if f not in request_data or not request_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if request_data["customer_risk_tier"] not in RISK_TIERS:
            return {"registered": False,
                       "error": f"invalid_risk_tier:{request_data['customer_risk_tier']}"}
        records = self._load(self.requests_path,
                                "cims_stp_requests", ("request_id",))
        if any(r.get("request_id") == request_data["request_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_request_id"}
        record = {
            "request_id": request_data["request_id"],
            "instruction_id": request_data["instruction_id"],
            "instruction_type": request_data["instruction_type"],
            "customer_risk_tier": request_data["customer_risk_tier"],
            "amount": request_data.get("amount"),
            "currency": request_data.get("currency", "KES"),
            "channel": request_data.get("channel", ""),
            "state": "EVALUATING",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "EVALUATING", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.requests_path, records,
                          "cims_stp_requests", "request_id")
        return {"registered": ok,
                  "request_id": request_data["request_id"]}

    def record_stp_decision(
        self, decision_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"recorded": False, "error": "actor_and_reason_required"}
        for f in ("decision_id", "request_id", "decision"):
            if f not in decision_data or not decision_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if decision_data["decision"] not in STP_DECISION_STATES:
            return {"recorded": False,
                       "error": f"invalid_decision:{decision_data['decision']}"}
        rejection_reason = decision_data.get("rejection_reason")
        if (rejection_reason
                and rejection_reason not in REJECTION_REASONS):
            return {"recorded": False,
                       "error": f"invalid_rejection_reason:{rejection_reason}"}
        records = self._load(self.decisions_path,
                                "cims_stp_decisions", ("decision_id",))
        if any(r.get("decision_id") == decision_data["decision_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_decision_id"}
        record = {
            "decision_id": decision_data["decision_id"],
            "request_id": decision_data["request_id"],
            "decision": decision_data["decision"],
            "rejection_reason": rejection_reason or "",
            "criteria_evaluated": list(
                decision_data.get("criteria_evaluated", []),
            ),
            "rationale": reason,
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.decisions_path, records,
                          "cims_stp_decisions", "decision_id")
        return {"recorded": ok, "decision_id": decision_data["decision_id"]}

    def transition_decision_state(
        self, request_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in STP_DECISION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.requests_path,
                                "cims_stp_requests", ("request_id",))
        for r in records:
            if r.get("request_id") == request_id:
                current = r.get("state", "EVALUATING")
                allowed = ALLOWED_DECISION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.requests_path, records,
                                  "cims_stp_requests", "request_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "request_not_found"}

    def register_eligibility_rule(
        self, rule_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("rule_id", "criterion", "applies_to_instruction_type"):
            if f not in rule_data or not rule_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if rule_data["criterion"] not in ELIGIBILITY_CRITERIA:
            return {"registered": False,
                       "error": f"invalid_criterion:{rule_data['criterion']}"}
        records = self._load(self.rules_path,
                                "cims_stp_eligibility_rules", ("rule_id",))
        if any(r.get("rule_id") == rule_data["rule_id"] for r in records):
            return {"registered": False, "error": "duplicate_rule_id"}
        record = {
            "rule_id": rule_data["rule_id"],
            "criterion": rule_data["criterion"],
            "applies_to_instruction_type":
                rule_data["applies_to_instruction_type"],
            "threshold_value": rule_data.get("threshold_value"),
            "active": True,
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.rules_path, records,
                          "cims_stp_eligibility_rules", "rule_id")
        return {"registered": ok, "rule_id": rule_data["rule_id"]}

    def stp_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        requests = self._load(self.requests_path,
                                  "cims_stp_requests", ("request_id",))
        recent = [r for r in requests
                       if r.get("registered_at", "") >= cutoff]
        per_state: Dict[str, int] = {}
        per_risk_tier: Dict[str, int] = {}
        for r in recent:
            per_state[r.get("state", "")] = (
                per_state.get(r.get("state", ""), 0) + 1
            )
            per_risk_tier[r.get("customer_risk_tier", "")] = (
                per_risk_tier.get(r.get("customer_risk_tier", ""), 0) + 1
            )
        approved = (per_state.get("APPROVED_FOR_STP", 0)
                          + per_state.get("EXECUTED", 0))
        # Note: EXECUTED could come from APPROVED_FOR_STP, REJECTED_FOR_STP,
        # or MANUAL_REVIEW. This metric counts STP-eligible only.
        executed = per_state.get("EXECUTED", 0)
        manual = per_state.get("MANUAL_REVIEW", 0)
        return {
            "window_days": days,
            "total_requests": len(recent),
            "per_state": per_state,
            "per_risk_tier": per_risk_tier,
            "stp_approved": approved,
            "stp_rate_pct": round(
                (approved / len(recent) * 100) if recent else 0, 1,
            ),
            "executed": executed,
            "pending_manual_review": manual,
        }

    def pending_manual_review(self) -> List[Dict[str, Any]]:
        records = self._load(self.requests_path,
                                "cims_stp_requests", ("request_id",))
        return [r for r in records
                       if r.get("state") == "MANUAL_REVIEW"]


def _self_test() -> None:
    import tempfile

    assert STP_DECISION_STATES == (
        "EVALUATING", "APPROVED_FOR_STP", "REJECTED_FOR_STP",
        "MANUAL_REVIEW", "EXECUTED",
    )
    assert ALLOWED_DECISION_TRANSITIONS["EXECUTED"] == ()
    assert RISK_TIERS == (
        "LOW", "MEDIUM", "HIGH", "ENHANCED_DUE_DILIGENCE",
    )
    assert ELIGIBILITY_CRITERIA == (
        "AMOUNT_THRESHOLD", "CHANNEL_TRUST", "CUSTOMER_RISK_TIER",
        "INSTRUCTION_TYPE", "KYC_FRESHNESS", "BLACKLIST_CHECK",
    )
    assert REJECTION_REASONS == (
        "EXCEEDS_AMOUNT_LIMIT", "RISK_TIER_TOO_HIGH",
        "KYC_STALE", "BLACKLIST_HIT", "ELIGIBILITY_RULE_FAILED",
    )
    assert DEFAULT_STP_AMOUNT_LIMIT_LOW_RISK == 100000
    assert DEFAULT_STP_AMOUNT_LIMIT_MEDIUM_RISK == 25000
    assert DEFAULT_STP_DECISION_TIMEOUT_SECONDS == 10
    assert DEFAULT_KYC_FRESHNESS_DAYS == 365

    with tempfile.TemporaryDirectory() as tmpdir:
        e = StraightThroughProcessingEngine(
            requests_path=Path(tmpdir) / "r.json",
            decisions_path=Path(tmpdir) / "d.json",
            rules_path=Path(tmpdir) / "ru.json",
        )
        # Eligibility rule
        r = e.register_eligibility_rule(
            {"rule_id": "RULE-AMT-LOW",
             "criterion": "AMOUNT_THRESHOLD",
             "applies_to_instruction_type": "FUNDS_TRANSFER",
             "threshold_value": "100000"},
            actor="risk-team", reason="LOW risk STP cap",
        )
        assert r["registered"]
        # Bad criterion
        r = e.register_eligibility_rule(
            {"rule_id": "X", "criterion": "WHATEVER",
             "applies_to_instruction_type": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Request
        r = e.register_stp_request(
            {"request_id": "STP-001",
             "instruction_id": "INS-001",
             "instruction_type": "FUNDS_TRANSFER",
             "customer_risk_tier": "LOW",
             "amount": 5000,
             "currency": "KES",
             "channel": "MOBILE_APP"},
            actor="stp-svc", reason="auto-evaluation",
        )
        assert r["registered"]
        # Bad risk tier
        r = e.register_stp_request(
            {"request_id": "X", "instruction_id": "Y",
             "instruction_type": "Z", "customer_risk_tier": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Decision: APPROVED_FOR_STP
        r = e.transition_decision_state(
            "STP-001", "APPROVED_FOR_STP",
            actor="stp-svc", reason="all criteria met",
        )
        assert r["transitioned"]
        r = e.record_stp_decision(
            {"decision_id": "DEC-001",
             "request_id": "STP-001",
             "decision": "APPROVED_FOR_STP",
             "criteria_evaluated": [
                 "AMOUNT_THRESHOLD", "CUSTOMER_RISK_TIER",
                 "KYC_FRESHNESS", "BLACKLIST_CHECK",
             ]},
            actor="stp-svc",
            reason="LOW risk + amount within threshold + KYC fresh",
        )
        assert r["recorded"]
        # Bad rejection reason
        r = e.record_stp_decision(
            {"decision_id": "DEC-X",
             "request_id": "STP-001",
             "decision": "REJECTED_FOR_STP",
             "rejection_reason": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["recorded"]

        # Execute
        r = e.transition_decision_state(
            "STP-001", "EXECUTED",
            actor="exec-svc", reason="downstream confirmed",
        )
        assert r["transitioned"]
        # EXECUTED is terminal
        r = e.transition_decision_state(
            "STP-001", "MANUAL_REVIEW", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Rejection path
        e.register_stp_request(
            {"request_id": "STP-002",
             "instruction_id": "INS-002",
             "instruction_type": "FUNDS_TRANSFER",
             "customer_risk_tier": "HIGH",
             "amount": 500000,
             "currency": "KES"},
            actor="stp-svc", reason="auto-evaluation",
        )
        r = e.transition_decision_state(
            "STP-002", "REJECTED_FOR_STP",
            actor="stp-svc", reason="risk + amount exceed",
        )
        assert r["transitioned"]
        r = e.record_stp_decision(
            {"decision_id": "DEC-002",
             "request_id": "STP-002",
             "decision": "REJECTED_FOR_STP",
             "rejection_reason": "RISK_TIER_TOO_HIGH",
             "criteria_evaluated": [
                 "CUSTOMER_RISK_TIER", "AMOUNT_THRESHOLD",
             ]},
            actor="stp-svc",
            reason="HIGH risk customer with large amount",
        )
        assert r["recorded"]
        # Move to manual review
        r = e.transition_decision_state(
            "STP-002", "MANUAL_REVIEW",
            actor="agent", reason="taking lead",
        )
        assert r["transitioned"]

        pending = e.pending_manual_review()
        assert len(pending) == 1
        assert pending[0]["request_id"] == "STP-002"

        # Metrics
        m = e.stp_metrics(days=30)
        assert m["total_requests"] == 2
        assert m["executed"] == 1
        assert m["pending_manual_review"] == 1

    print("  ✅ cims_stp_engine self-test PASS")


if __name__ == "__main__":
    _self_test()

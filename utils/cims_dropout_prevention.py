"""
================================================================================
A2Z MIS 360 — Standard #170: Predictive Dropout Prevention
================================================================================

Risk classification: Cat C (read-side prediction; diagnostic only —
recommendations never auto-trigger interventions).

Subcategory: cims

Predicts customer instruction abandonment before it happens, surfacing
proactive intervention opportunities. Composes upstream capture (#166)
and process intelligence (#169) — uses dropout-risk signals from
session timing, channel-touch patterns, and process deviation, plus
historical abandonment data.

Per Rule 7: this is a Cat D scaffolding pattern. The engine produces
deterministic rule-based scores; ML model integration is via an
optional ml_score_fn factory hook. When no model is wired, ml_score=None
and the rule_based score is used as the basis with a basis="rule_based"
flag and a reason field surfaced.

Public API:
    register_dropout_signal(signal_data, actor, reason)
    transition_signal_state(signal_id, new_state, actor, reason)
    register_intervention(intervention_data, actor, reason)
    record_intervention_outcome(outcome_data, actor)
    score_dropout_risk(session_data, ml_score_fn=None) -> Dict
    intervention_metrics(days=30) -> Dict

DROPOUT_RISK_TIERS byte-for-byte (4):
    LOW, MEDIUM, HIGH, CRITICAL

DROPOUT_RISK_TIER_THRESHOLDS byte-for-byte:
    LOW < 30
    MEDIUM 30..59
    HIGH 60..79
    CRITICAL >= 80

SIGNAL_STATES byte-for-byte (5):
    DETECTED, MONITORING, ACTIONED, RESOLVED, FALSE_POSITIVE

ALLOWED_SIGNAL_TRANSITIONS (Rule 4):
    DETECTED       → MONITORING | ACTIONED | FALSE_POSITIVE
    MONITORING     → ACTIONED | RESOLVED | FALSE_POSITIVE
    ACTIONED       → RESOLVED | FALSE_POSITIVE
    RESOLVED       → ()
    FALSE_POSITIVE → ()

INTERVENTION_TYPES byte-for-byte (6):
    OUTBOUND_CALL, SMS_NUDGE, IN_APP_PROMPT,
    EMAIL_FOLLOWUP, RM_HANDOFF, AUTO_RETRY_CHANNEL

INTERVENTION_OUTCOMES byte-for-byte (5):
    INSTRUCTION_COMPLETED, CUSTOMER_ABANDONED,
    NO_RESPONSE, ALREADY_COMPLETED, ESCALATED

DROPOUT_RISK_FACTOR_WEIGHTS_PCT byte-for-byte (sums to 100):
    SESSION_DURATION = 25
    CHANNEL_HOPS = 20
    PROCESS_DEVIATION = 20
    HISTORICAL_ABANDONMENT = 25
    INSTRUCTION_COMPLEXITY = 10

DEFAULT_PREDICTION_HORIZON_HOURS = 4
DEFAULT_INTERVENTION_COOLDOWN_HOURS = 24

SPEC_DEVIATION_NOTE = (
    "Per Rule 7 Cat D pattern: ml_score_fn is an optional factory hook. "
    "When not wired, score_dropout_risk returns basis='rule_based' with "
    "ml_score=None and a reason. When wired, ML output is surfaced "
    "alongside rule_based for comparison; deterministic rule_based "
    "score is always present."
)

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


DROPOUT_RISK_TIERS: Tuple[str, ...] = (
    "LOW", "MEDIUM", "HIGH", "CRITICAL",
)

SIGNAL_STATES: Tuple[str, ...] = (
    "DETECTED", "MONITORING", "ACTIONED",
    "RESOLVED", "FALSE_POSITIVE",
)

ALLOWED_SIGNAL_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DETECTED":       ("MONITORING", "ACTIONED", "FALSE_POSITIVE"),
    "MONITORING":     ("ACTIONED", "RESOLVED", "FALSE_POSITIVE"),
    "ACTIONED":       ("RESOLVED", "FALSE_POSITIVE"),
    "RESOLVED":       (),
    "FALSE_POSITIVE": (),
}

INTERVENTION_TYPES: Tuple[str, ...] = (
    "OUTBOUND_CALL", "SMS_NUDGE", "IN_APP_PROMPT",
    "EMAIL_FOLLOWUP", "RM_HANDOFF", "AUTO_RETRY_CHANNEL",
)

INTERVENTION_OUTCOMES: Tuple[str, ...] = (
    "INSTRUCTION_COMPLETED", "CUSTOMER_ABANDONED",
    "NO_RESPONSE", "ALREADY_COMPLETED", "ESCALATED",
)

DROPOUT_RISK_FACTOR_WEIGHTS_PCT: Dict[str, int] = {
    "SESSION_DURATION": 25,
    "CHANNEL_HOPS": 20,
    "PROCESS_DEVIATION": 20,
    "HISTORICAL_ABANDONMENT": 25,
    "INSTRUCTION_COMPLEXITY": 10,
}

DEFAULT_PREDICTION_HORIZON_HOURS = 4
DEFAULT_INTERVENTION_COOLDOWN_HOURS = 24

SPEC_DEVIATION_NOTE = (
    "Per Rule 7 Cat D pattern: ml_score_fn is an optional factory hook. "
    "When not wired, score_dropout_risk returns basis='rule_based' with "
    "ml_score=None and a reason. When wired, ML output is surfaced "
    "alongside rule_based for comparison; deterministic rule_based "
    "score is always present."
)


def _classify_tier(score: int) -> str:
    if score < 30:
        return "LOW"
    if score < 60:
        return "MEDIUM"
    if score < 80:
        return "HIGH"
    return "CRITICAL"


class DropoutPreventionEngine:
    """Dropout signal + intervention registry. Cat D scaffolded scoring."""

    def __init__(
        self,
        signals_path: Optional[Path] = None,
        interventions_path: Optional[Path] = None,
        outcomes_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.signals_path = signals_path or base / "cims_dropout_signals.json"
        self.interventions_path = (
            interventions_path or base / "cims_interventions.json"
        )
        self.outcomes_path = (
            outcomes_path or base / "cims_intervention_outcomes.json"
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

    def register_dropout_signal(
        self, signal_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("signal_id", "capture_session_id",
                      "risk_score", "risk_tier"):
            if f not in signal_data or signal_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if signal_data["risk_tier"] not in DROPOUT_RISK_TIERS:
            return {"registered": False,
                       "error": f"invalid_risk_tier:{signal_data['risk_tier']}"}
        try:
            score = int(signal_data["risk_score"])
        except (TypeError, ValueError):
            return {"registered": False, "error": "risk_score_not_int"}
        if score < 0 or score > 100:
            return {"registered": False, "error": "risk_score_out_of_range"}
        records = self._load(self.signals_path,
                                "cims_dropout_signals", ("signal_id",))
        if any(r.get("signal_id") == signal_data["signal_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_signal_id"}
        record = {
            "signal_id": signal_data["signal_id"],
            "capture_session_id": signal_data["capture_session_id"],
            "risk_score": score,
            "risk_tier": signal_data["risk_tier"],
            "narrative": signal_data.get("narrative", ""),
            "state": "DETECTED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DETECTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.signals_path, records,
                          "cims_dropout_signals", "signal_id")
        return {"registered": ok, "signal_id": signal_data["signal_id"]}

    def transition_signal_state(
        self, signal_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in SIGNAL_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.signals_path,
                                "cims_dropout_signals", ("signal_id",))
        for r in records:
            if r.get("signal_id") == signal_id:
                current = r.get("state", "DETECTED")
                allowed = ALLOWED_SIGNAL_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.signals_path, records,
                                  "cims_dropout_signals", "signal_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "signal_not_found"}

    def register_intervention(
        self, intervention_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("intervention_id", "signal_id", "intervention_type"):
            if f not in intervention_data or not intervention_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if intervention_data["intervention_type"] not in INTERVENTION_TYPES:
            return {"registered": False,
                       "error": f"invalid_intervention_type:{intervention_data['intervention_type']}"}
        records = self._load(self.interventions_path,
                                "cims_interventions", ("intervention_id",))
        if any(r.get("intervention_id") == intervention_data["intervention_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_intervention_id"}
        record = {
            "intervention_id": intervention_data["intervention_id"],
            "signal_id": intervention_data["signal_id"],
            "intervention_type": intervention_data["intervention_type"],
            "narrative": intervention_data.get("narrative", ""),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.interventions_path, records,
                          "cims_interventions", "intervention_id")
        return {"registered": ok,
                  "intervention_id": intervention_data["intervention_id"]}

    def record_intervention_outcome(
        self, outcome_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("outcome_id", "intervention_id", "outcome"):
            if f not in outcome_data or not outcome_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if outcome_data["outcome"] not in INTERVENTION_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{outcome_data['outcome']}"}
        records = self._load(self.outcomes_path,
                                "cims_intervention_outcomes", ("outcome_id",))
        if any(r.get("outcome_id") == outcome_data["outcome_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_outcome_id"}
        record = {
            "outcome_id": outcome_data["outcome_id"],
            "intervention_id": outcome_data["intervention_id"],
            "outcome": outcome_data["outcome"],
            "narrative": outcome_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.outcomes_path, records,
                          "cims_intervention_outcomes", "outcome_id")
        return {"recorded": ok, "outcome_id": outcome_data["outcome_id"]}

    def score_dropout_risk(
        self, session_data: Dict[str, Any],
        ml_score_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
    ) -> Dict[str, Any]:
        """Cat D Rule 7 scaffold: rule_based always; ml when wired."""
        # Rule-based deterministic score — weighted sum of factors
        # Each factor is expected to be a 0-100 normalised input.
        factors = {
            k: int(session_data.get(k.lower(), 0) or 0)
            for k in DROPOUT_RISK_FACTOR_WEIGHTS_PCT
        }
        rule_based = sum(
            factors[k] * w / 100
            for k, w in DROPOUT_RISK_FACTOR_WEIGHTS_PCT.items()
        )
        rule_based_int = int(round(rule_based))
        rule_based_int = max(0, min(100, rule_based_int))
        result: Dict[str, Any] = {
            "rule_based_score": rule_based_int,
            "rule_based_tier": _classify_tier(rule_based_int),
            "ml_score": None,
            "basis": "rule_based",
            "factors": factors,
            "weights": dict(DROPOUT_RISK_FACTOR_WEIGHTS_PCT),
        }
        if ml_score_fn is None:
            result["reason"] = (
                "no_ml_model_wired; rule_based deterministic score used"
            )
            result["spec_deviation"] = SPEC_DEVIATION_NOTE
            return result
        try:
            ml = int(ml_score_fn(session_data))
            ml = max(0, min(100, ml))
            result["ml_score"] = ml
            result["ml_tier"] = _classify_tier(ml)
            result["basis"] = "ml"
            result["reason"] = "ml_model_wired"
        except Exception as exc:
            result["ml_error"] = f"{type(exc).__name__}: {exc}"
            result["reason"] = (
                "ml_score_fn_raised; falling back to rule_based"
            )
        result["spec_deviation"] = SPEC_DEVIATION_NOTE
        return result

    def intervention_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        outcomes = [
            o for o in self._load(self.outcomes_path,
                                            "cims_intervention_outcomes",
                                            ("outcome_id",))
            if o.get("recorded_at", "") >= cutoff
        ]
        per_outcome: Dict[str, int] = {}
        for o in outcomes:
            oc = o.get("outcome", "")
            per_outcome[oc] = per_outcome.get(oc, 0) + 1
        completed = per_outcome.get("INSTRUCTION_COMPLETED", 0)
        abandoned = per_outcome.get("CUSTOMER_ABANDONED", 0)
        actionable = completed + abandoned
        save_rate = round(
            (completed / actionable * 100) if actionable else 0, 1,
        )
        return {
            "window_days": days,
            "total_outcomes": len(outcomes),
            "per_outcome": per_outcome,
            "save_rate_pct": save_rate,
            "save_rate_basis": (
                "INSTRUCTION_COMPLETED / "
                "(INSTRUCTION_COMPLETED + CUSTOMER_ABANDONED)"
            ),
        }


def _self_test() -> None:
    import tempfile

    assert DROPOUT_RISK_TIERS == ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert SIGNAL_STATES == (
        "DETECTED", "MONITORING", "ACTIONED",
        "RESOLVED", "FALSE_POSITIVE",
    )
    assert ALLOWED_SIGNAL_TRANSITIONS["RESOLVED"] == ()
    assert ALLOWED_SIGNAL_TRANSITIONS["FALSE_POSITIVE"] == ()
    assert INTERVENTION_TYPES == (
        "OUTBOUND_CALL", "SMS_NUDGE", "IN_APP_PROMPT",
        "EMAIL_FOLLOWUP", "RM_HANDOFF", "AUTO_RETRY_CHANNEL",
    )
    assert INTERVENTION_OUTCOMES == (
        "INSTRUCTION_COMPLETED", "CUSTOMER_ABANDONED",
        "NO_RESPONSE", "ALREADY_COMPLETED", "ESCALATED",
    )
    assert sum(DROPOUT_RISK_FACTOR_WEIGHTS_PCT.values()) == 100
    assert DEFAULT_PREDICTION_HORIZON_HOURS == 4
    assert DEFAULT_INTERVENTION_COOLDOWN_HOURS == 24
    assert _classify_tier(0) == "LOW"
    assert _classify_tier(29) == "LOW"
    assert _classify_tier(30) == "MEDIUM"
    assert _classify_tier(59) == "MEDIUM"
    assert _classify_tier(60) == "HIGH"
    assert _classify_tier(79) == "HIGH"
    assert _classify_tier(80) == "CRITICAL"
    assert _classify_tier(100) == "CRITICAL"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = DropoutPreventionEngine(
            signals_path=Path(tmpdir) / "s.json",
            interventions_path=Path(tmpdir) / "i.json",
            outcomes_path=Path(tmpdir) / "o.json",
        )

        # Rule-based scoring (no ML hook)
        r = e.score_dropout_risk({
            "session_duration": 80,
            "channel_hops": 50,
            "process_deviation": 60,
            "historical_abandonment": 70,
            "instruction_complexity": 40,
        })
        assert r["basis"] == "rule_based"
        assert r["ml_score"] is None
        assert r["rule_based_score"] >= 0
        assert r["rule_based_tier"] in DROPOUT_RISK_TIERS
        assert "spec_deviation" in r
        assert "no_ml_model_wired" in r["reason"]

        # ML hook wired
        ml_calls = []
        def ml_fn(d):
            ml_calls.append(d)
            return 75
        r = e.score_dropout_risk(
            {"session_duration": 30}, ml_score_fn=ml_fn,
        )
        assert r["basis"] == "ml"
        assert r["ml_score"] == 75
        assert r["ml_tier"] == "HIGH"
        assert len(ml_calls) == 1

        # ML hook fails → fall back gracefully
        def ml_broken(d):
            raise RuntimeError("model down")
        r = e.score_dropout_risk(
            {"session_duration": 30}, ml_score_fn=ml_broken,
        )
        assert r["basis"] == "rule_based"
        assert r["ml_score"] is None
        assert "ml_error" in r

        # Signal registration
        r = e.register_dropout_signal(
            {"signal_id": "SIG-001",
             "capture_session_id": "CAP-001",
             "risk_score": 75,
             "risk_tier": "HIGH",
             "narrative": "Customer paused mid-flow"},
            actor="ops", reason="auto-detected",
        )
        assert r["registered"]
        # Invalid tier
        r = e.register_dropout_signal(
            {"signal_id": "X", "capture_session_id": "Y",
             "risk_score": 50, "risk_tier": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Out of range
        r = e.register_dropout_signal(
            {"signal_id": "Z", "capture_session_id": "Y",
             "risk_score": 150, "risk_tier": "HIGH"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_signal_state(
            "SIG-001", "MONITORING",
            actor="ops", reason="watching",
        )
        assert r["transitioned"]
        r = e.transition_signal_state(
            "SIG-001", "ACTIONED", actor="ops", reason="called",
        )
        assert r["transitioned"]
        r = e.transition_signal_state(
            "SIG-001", "RESOLVED", actor="ops", reason="completed",
        )
        assert r["transitioned"]
        # Terminal
        r = e.transition_signal_state(
            "SIG-001", "DETECTED", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Intervention
        r = e.register_intervention(
            {"intervention_id": "INT-001",
             "signal_id": "SIG-001",
             "intervention_type": "OUTBOUND_CALL"},
            actor="ops", reason="proactive call",
        )
        assert r["registered"]
        # Invalid type
        r = e.register_intervention(
            {"intervention_id": "X", "signal_id": "Y",
             "intervention_type": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Outcome
        r = e.record_intervention_outcome(
            {"outcome_id": "OUT-001",
             "intervention_id": "INT-001",
             "outcome": "INSTRUCTION_COMPLETED"},
            actor="ops",
        )
        assert r["recorded"]
        # Invalid outcome
        r = e.record_intervention_outcome(
            {"outcome_id": "X", "intervention_id": "Y",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Metrics
        m = e.intervention_metrics(days=30)
        assert m["total_outcomes"] == 1
        assert m["per_outcome"]["INSTRUCTION_COMPLETED"] == 1
        assert m["save_rate_pct"] == 100.0

    print("  ✅ cims_dropout_prevention self-test PASS")


if __name__ == "__main__":
    _self_test()

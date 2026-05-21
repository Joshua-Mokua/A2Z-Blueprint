"""
================================================================================
A2Z MIS 360 — Standard #174: Next Best Action for Instructions
================================================================================

Risk classification: Cat C (read-side recommendation; Cat D Rule 7 ML
scaffold; never auto-executes the recommended action).

Subcategory: cims

Backbase-inspired next-best-action (NBA) for instruction workflows.
Given a capture session and its current state, propose ranked actions
the customer or staff member should take next. Composes upstream
capture (#166), classification (#167), STP (#168), identity (#173),
process intelligence (#169), and dropout prevention (#170).

Per Rule 7: this is a Cat D scaffolding pattern. Rule-based ranking
deterministic + optional ml_rank_fn factory hook. When no model is
wired, ml_rankings=None and rule_based ranking is used.

Public API:
    register_nba_rule(rule_data, actor, reason)
    transition_rule_state(rule_id, new_state, actor, reason)
    record_action_recommendation(rec_data, actor)
    record_recommendation_outcome(outcome_data, actor)
    rank_next_actions(session_data, ml_rank_fn=None) -> Dict
    nba_metrics(days=30) -> Dict

NBA_ACTION_TYPES byte-for-byte (8):
    COMPLETE_INSTRUCTION, RESUME_LATER, ESCALATE_TO_RM,
    SWITCH_CHANNEL, ADD_DOCUMENT, CONTACT_SUPPORT,
    CANCEL_INSTRUCTION, REVIEW_DETAILS

NBA_RULE_STATES byte-for-byte (4):
    ACTIVE, PAUSED, DEPRECATED, ARCHIVED

ALLOWED_RULE_TRANSITIONS (Rule 4):
    ACTIVE     → PAUSED | DEPRECATED | ARCHIVED
    PAUSED     → ACTIVE | DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

RECOMMENDATION_OUTCOMES byte-for-byte (5):
    ACCEPTED, REJECTED, IGNORED, OVERRIDDEN, EXPIRED

ACTION_PRIORITY_TIERS byte-for-byte (4):
    URGENT, HIGH, NORMAL, LOW

NBA_RULE_FACTOR_WEIGHTS_PCT byte-for-byte (sums to 100):
    INSTRUCTION_TYPE_FIT = 30
    SESSION_STATE = 20
    DROPOUT_RISK = 25
    CUSTOMER_HISTORY = 15
    CHANNEL_PREFERENCE = 10

DEFAULT_TOP_N_RECOMMENDATIONS = 3
DEFAULT_RECOMMENDATION_TTL_HOURS = 4

SPEC_DEVIATION_NOTE = (
    "Per Rule 7 Cat D pattern: ml_rank_fn is an optional factory hook. "
    "When not wired, rank_next_actions returns basis='rule_based' with "
    "ml_rankings=None and a reason field. When wired, ML output is "
    "surfaced alongside rule_based; deterministic rule_based ranking "
    "is always present."
)

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


NBA_ACTION_TYPES: Tuple[str, ...] = (
    "COMPLETE_INSTRUCTION", "RESUME_LATER", "ESCALATE_TO_RM",
    "SWITCH_CHANNEL", "ADD_DOCUMENT", "CONTACT_SUPPORT",
    "CANCEL_INSTRUCTION", "REVIEW_DETAILS",
)

NBA_RULE_STATES: Tuple[str, ...] = (
    "ACTIVE", "PAUSED", "DEPRECATED", "ARCHIVED",
)

ALLOWED_RULE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":     ("PAUSED", "DEPRECATED", "ARCHIVED"),
    "PAUSED":     ("ACTIVE", "DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

RECOMMENDATION_OUTCOMES: Tuple[str, ...] = (
    "ACCEPTED", "REJECTED", "IGNORED", "OVERRIDDEN", "EXPIRED",
)

ACTION_PRIORITY_TIERS: Tuple[str, ...] = (
    "URGENT", "HIGH", "NORMAL", "LOW",
)

NBA_RULE_FACTOR_WEIGHTS_PCT: Dict[str, int] = {
    "INSTRUCTION_TYPE_FIT": 30,
    "SESSION_STATE": 20,
    "DROPOUT_RISK": 25,
    "CUSTOMER_HISTORY": 15,
    "CHANNEL_PREFERENCE": 10,
}

DEFAULT_TOP_N_RECOMMENDATIONS = 3
DEFAULT_RECOMMENDATION_TTL_HOURS = 4

SPEC_DEVIATION_NOTE = (
    "Per Rule 7 Cat D pattern: ml_rank_fn is an optional factory hook. "
    "When not wired, rank_next_actions returns basis='rule_based' with "
    "ml_rankings=None and a reason field. When wired, ML output is "
    "surfaced alongside rule_based; deterministic rule_based ranking "
    "is always present."
)


class NextBestActionEngine:
    """NBA rule + recommendation registry. Cat D scaffolded ranking."""

    def __init__(
        self,
        rules_path: Optional[Path] = None,
        recommendations_path: Optional[Path] = None,
        outcomes_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.rules_path = rules_path or base / "cims_nba_rules.json"
        self.recommendations_path = (
            recommendations_path or base / "cims_nba_recommendations.json"
        )
        self.outcomes_path = (
            outcomes_path or base / "cims_nba_recommendation_outcomes.json"
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

    def register_nba_rule(
        self, rule_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("rule_id", "name", "action_type",
                      "instruction_type"):
            if f not in rule_data or not rule_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if rule_data["action_type"] not in NBA_ACTION_TYPES:
            return {"registered": False,
                       "error": f"invalid_action_type:{rule_data['action_type']}"}
        records = self._load(self.rules_path,
                                "cims_nba_rules", ("rule_id",))
        if any(r.get("rule_id") == rule_data["rule_id"] for r in records):
            return {"registered": False, "error": "duplicate_rule_id"}
        record = {
            "rule_id": rule_data["rule_id"],
            "name": rule_data["name"],
            "action_type": rule_data["action_type"],
            "instruction_type": rule_data["instruction_type"],
            "default_priority": rule_data.get(
                "default_priority", "NORMAL",
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
        if record["default_priority"] not in ACTION_PRIORITY_TIERS:
            return {"registered": False,
                       "error": f"invalid_priority:{record['default_priority']}"}
        records.append(record)
        ok = self._save(self.rules_path, records,
                          "cims_nba_rules", "rule_id")
        return {"registered": ok, "rule_id": rule_data["rule_id"]}

    def transition_rule_state(
        self, rule_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in NBA_RULE_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.rules_path,
                                "cims_nba_rules", ("rule_id",))
        for r in records:
            if r.get("rule_id") == rule_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_RULE_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.rules_path, records,
                                  "cims_nba_rules", "rule_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "rule_not_found"}

    def record_action_recommendation(
        self, rec_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("recommendation_id", "capture_session_id",
                      "action_type", "rank"):
            if f not in rec_data or rec_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        if rec_data["action_type"] not in NBA_ACTION_TYPES:
            return {"recorded": False,
                       "error": f"invalid_action_type:{rec_data['action_type']}"}
        try:
            rank = int(rec_data["rank"])
        except (TypeError, ValueError):
            return {"recorded": False, "error": "rank_not_int"}
        if rank < 1:
            return {"recorded": False, "error": "rank_must_be_positive"}
        records = self._load(self.recommendations_path,
                                "cims_nba_recommendations",
                                ("recommendation_id",))
        if any(r.get("recommendation_id") == rec_data["recommendation_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_recommendation_id"}
        record = {
            "recommendation_id": rec_data["recommendation_id"],
            "capture_session_id": rec_data["capture_session_id"],
            "action_type": rec_data["action_type"],
            "rank": rank,
            "score": rec_data.get("score"),
            "priority": rec_data.get("priority", "NORMAL"),
            "basis": rec_data.get("basis", "rule_based"),
            "recommended_at": datetime.utcnow().isoformat(),
            "recommended_by": actor,
        }
        if record["priority"] not in ACTION_PRIORITY_TIERS:
            return {"recorded": False,
                       "error": f"invalid_priority:{record['priority']}"}
        records.append(record)
        ok = self._save(self.recommendations_path, records,
                          "cims_nba_recommendations", "recommendation_id")
        return {"recorded": ok,
                  "recommendation_id": rec_data["recommendation_id"]}

    def record_recommendation_outcome(
        self, outcome_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("outcome_id", "recommendation_id", "outcome"):
            if f not in outcome_data or not outcome_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if outcome_data["outcome"] not in RECOMMENDATION_OUTCOMES:
            return {"recorded": False,
                       "error": f"invalid_outcome:{outcome_data['outcome']}"}
        records = self._load(self.outcomes_path,
                                "cims_nba_recommendation_outcomes",
                                ("outcome_id",))
        if any(r.get("outcome_id") == outcome_data["outcome_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_outcome_id"}
        record = {
            "outcome_id": outcome_data["outcome_id"],
            "recommendation_id": outcome_data["recommendation_id"],
            "outcome": outcome_data["outcome"],
            "narrative": outcome_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.outcomes_path, records,
                          "cims_nba_recommendation_outcomes", "outcome_id")
        return {"recorded": ok, "outcome_id": outcome_data["outcome_id"]}

    def rank_next_actions(
        self, session_data: Dict[str, Any],
        ml_rank_fn: Optional[Callable[[Dict[str, Any]],
                                                List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """Cat D Rule 7 scaffold: rule_based always; ml when wired.

        Rule-based deterministic ranking: scores each NBA_ACTION_TYPE
        with the weighted-factor formula, then sorts descending.
        Returns the top DEFAULT_TOP_N_RECOMMENDATIONS.
        """
        # Build rule-based scores per action.
        instruction_type_fit = int(
            session_data.get("instruction_type_fit", 0) or 0
        )
        session_state = int(session_data.get("session_state", 0) or 0)
        dropout_risk = int(session_data.get("dropout_risk", 0) or 0)
        customer_history = int(
            session_data.get("customer_history", 0) or 0,
        )
        channel_preference = int(
            session_data.get("channel_preference", 0) or 0,
        )
        # Per-action heuristics — different actions weight factors differently.
        # Keep the heuristics minimal and deterministic.
        rule_scored: List[Dict[str, Any]] = []
        for action in NBA_ACTION_TYPES:
            # Default weighted score
            base = (
                instruction_type_fit
                * NBA_RULE_FACTOR_WEIGHTS_PCT["INSTRUCTION_TYPE_FIT"]
                + session_state
                * NBA_RULE_FACTOR_WEIGHTS_PCT["SESSION_STATE"]
                + dropout_risk
                * NBA_RULE_FACTOR_WEIGHTS_PCT["DROPOUT_RISK"]
                + customer_history
                * NBA_RULE_FACTOR_WEIGHTS_PCT["CUSTOMER_HISTORY"]
                + channel_preference
                * NBA_RULE_FACTOR_WEIGHTS_PCT["CHANNEL_PREFERENCE"]
            ) / 100
            base = int(round(base))
            # Action-specific tilt
            if action == "COMPLETE_INSTRUCTION":
                tilt = instruction_type_fit
            elif action == "ESCALATE_TO_RM":
                tilt = dropout_risk if dropout_risk >= 60 else 0
            elif action == "SWITCH_CHANNEL":
                tilt = channel_preference - 50 if channel_preference < 50 else 0
            elif action == "RESUME_LATER":
                tilt = (50 - session_state) if session_state < 50 else 0
            else:
                tilt = 0
            score = max(0, min(100, base + tilt // 2))
            priority = (
                "URGENT" if score >= 80
                else "HIGH" if score >= 60
                else "NORMAL" if score >= 30
                else "LOW"
            )
            rule_scored.append({
                "action_type": action,
                "score": score,
                "priority": priority,
            })
        rule_scored.sort(key=lambda x: x["score"], reverse=True)
        for i, r in enumerate(rule_scored, start=1):
            r["rank"] = i
        rule_top_n = rule_scored[:DEFAULT_TOP_N_RECOMMENDATIONS]

        result: Dict[str, Any] = {
            "rule_based_rankings": rule_top_n,
            "rule_based_full": rule_scored,
            "ml_rankings": None,
            "basis": "rule_based",
            "spec_deviation": SPEC_DEVIATION_NOTE,
        }
        if ml_rank_fn is None:
            result["reason"] = (
                "no_ml_model_wired; rule_based deterministic ranking used"
            )
            return result
        try:
            ml_out = ml_rank_fn(session_data)
            if not isinstance(ml_out, list):
                raise TypeError("ml_rank_fn must return a list")
            result["ml_rankings"] = ml_out[:DEFAULT_TOP_N_RECOMMENDATIONS]
            result["basis"] = "ml"
            result["reason"] = "ml_model_wired"
        except Exception as exc:
            result["ml_error"] = f"{type(exc).__name__}: {exc}"
            result["reason"] = (
                "ml_rank_fn_raised; falling back to rule_based"
            )
        return result

    def nba_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        outcomes = [
            o for o in self._load(self.outcomes_path,
                                            "cims_nba_recommendation_outcomes",
                                            ("outcome_id",))
            if o.get("recorded_at", "") >= cutoff
        ]
        per_outcome: Dict[str, int] = {}
        for o in outcomes:
            oc = o.get("outcome", "")
            per_outcome[oc] = per_outcome.get(oc, 0) + 1
        accepted = per_outcome.get("ACCEPTED", 0)
        evaluated = (
            accepted + per_outcome.get("REJECTED", 0)
            + per_outcome.get("OVERRIDDEN", 0)
        )
        acceptance_rate = round(
            (accepted / evaluated * 100) if evaluated else 0, 1,
        )
        return {
            "window_days": days,
            "total_outcomes": len(outcomes),
            "per_outcome": per_outcome,
            "acceptance_rate_pct": acceptance_rate,
            "acceptance_rate_basis": (
                "ACCEPTED / (ACCEPTED + REJECTED + OVERRIDDEN)"
            ),
        }


def _self_test() -> None:
    import tempfile

    assert NBA_ACTION_TYPES == (
        "COMPLETE_INSTRUCTION", "RESUME_LATER", "ESCALATE_TO_RM",
        "SWITCH_CHANNEL", "ADD_DOCUMENT", "CONTACT_SUPPORT",
        "CANCEL_INSTRUCTION", "REVIEW_DETAILS",
    )
    assert ALLOWED_RULE_TRANSITIONS["ARCHIVED"] == ()
    assert RECOMMENDATION_OUTCOMES == (
        "ACCEPTED", "REJECTED", "IGNORED", "OVERRIDDEN", "EXPIRED",
    )
    assert ACTION_PRIORITY_TIERS == ("URGENT", "HIGH", "NORMAL", "LOW")
    assert sum(NBA_RULE_FACTOR_WEIGHTS_PCT.values()) == 100
    assert DEFAULT_TOP_N_RECOMMENDATIONS == 3
    assert DEFAULT_RECOMMENDATION_TTL_HOURS == 4

    with tempfile.TemporaryDirectory() as tmpdir:
        e = NextBestActionEngine(
            rules_path=Path(tmpdir) / "r.json",
            recommendations_path=Path(tmpdir) / "rc.json",
            outcomes_path=Path(tmpdir) / "o.json",
        )
        # Rule-based ranking (no ML)
        out = e.rank_next_actions({
            "instruction_type_fit": 80,
            "session_state": 70,
            "dropout_risk": 30,
            "customer_history": 60,
            "channel_preference": 50,
        })
        assert out["basis"] == "rule_based"
        assert out["ml_rankings"] is None
        assert len(out["rule_based_rankings"]) == 3
        assert out["rule_based_rankings"][0]["rank"] == 1
        assert "spec_deviation" in out

        # ML hook wired
        def ml_rank(d):
            return [
                {"action_type": "COMPLETE_INSTRUCTION",
                 "score": 95, "priority": "URGENT"},
            ]
        out = e.rank_next_actions(
            {"instruction_type_fit": 50},
            ml_rank_fn=ml_rank,
        )
        assert out["basis"] == "ml"
        assert out["ml_rankings"][0]["action_type"] == "COMPLETE_INSTRUCTION"

        # ML hook fails — fall back
        def ml_broken(d):
            raise RuntimeError("model down")
        out = e.rank_next_actions(
            {"instruction_type_fit": 50},
            ml_rank_fn=ml_broken,
        )
        assert out["basis"] == "rule_based"
        assert out["ml_rankings"] is None
        assert "ml_error" in out

        # Rule registration
        r = e.register_nba_rule(
            {"rule_id": "RULE-001",
             "name": "Mortgage doc reminder",
             "action_type": "ADD_DOCUMENT",
             "instruction_type": "LOAN_INQUIRY",
             "default_priority": "HIGH"},
            actor="ops", reason="reduce dropouts",
        )
        assert r["registered"]
        # Invalid action type
        r = e.register_nba_rule(
            {"rule_id": "X", "name": "Y",
             "action_type": "WHATEVER",
             "instruction_type": "Z"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Invalid priority
        r = e.register_nba_rule(
            {"rule_id": "Z", "name": "Y",
             "action_type": "ADD_DOCUMENT",
             "instruction_type": "LOAN",
             "default_priority": "WHATEVER"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_rule_state(
            "RULE-001", "PAUSED", actor="ops", reason="test",
        )
        assert r["transitioned"]
        r = e.transition_rule_state(
            "RULE-001", "DEPRECATED",
            actor="ops", reason="superseded",
        )
        assert r["transitioned"]
        # DEPRECATED → ARCHIVED only
        r = e.transition_rule_state(
            "RULE-001", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]
        r = e.transition_rule_state(
            "RULE-001", "ARCHIVED", actor="ops", reason="closed",
        )
        assert r["transitioned"]

        # Recommendation
        r = e.record_action_recommendation(
            {"recommendation_id": "REC-001",
             "capture_session_id": "CAP-001",
             "action_type": "COMPLETE_INSTRUCTION",
             "rank": 1,
             "score": 85,
             "priority": "URGENT",
             "basis": "rule_based"},
            actor="ops",
        )
        assert r["recorded"]
        # Bad rank
        r = e.record_action_recommendation(
            {"recommendation_id": "X",
             "capture_session_id": "Y",
             "action_type": "COMPLETE_INSTRUCTION",
             "rank": 0},
            actor="x",
        )
        assert not r["recorded"]
        # Bad action type
        r = e.record_action_recommendation(
            {"recommendation_id": "Z",
             "capture_session_id": "Y",
             "action_type": "WHATEVER",
             "rank": 1},
            actor="x",
        )
        assert not r["recorded"]

        # Outcome
        r = e.record_recommendation_outcome(
            {"outcome_id": "OUT-001",
             "recommendation_id": "REC-001",
             "outcome": "ACCEPTED"},
            actor="ops",
        )
        assert r["recorded"]
        # Bad outcome
        r = e.record_recommendation_outcome(
            {"outcome_id": "X", "recommendation_id": "Y",
             "outcome": "WHATEVER"},
            actor="x",
        )
        assert not r["recorded"]

        # Metrics
        m = e.nba_metrics(days=30)
        assert m["total_outcomes"] == 1
        assert m["per_outcome"]["ACCEPTED"] == 1
        assert m["acceptance_rate_pct"] == 100.0

    print("  ✅ cims_next_best_action self-test PASS")


if __name__ == "__main__":
    _self_test()

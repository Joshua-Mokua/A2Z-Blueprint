"""
================================================================================
A2Z MIS 360 — Standard #180: Instruction Completion Feedback Loop
================================================================================

Risk classification: Cat C (read-side feedback aggregation; Cat D
Rule 7 ML scaffold for self-learning optimization — never auto-acts
on feedback; recommendations surface to operations leads for human
review).

Subcategory: cims

Self-learning optimization based on completion data. Composes ALL
prior CIMS engines (#166-#179) — collects customer feedback after
instruction completion, correlates feedback with upstream lifecycle
events (capture channel, classification confidence, STP decision,
exception count, NBA acceptance, time to resolve), and surfaces
optimization opportunities to the operations team.

Per Rule 7: this is a Cat D scaffolding pattern. Optimization
recommendations are deterministic rule-based aggregations; an
optional ml_optimize_fn factory hook can supplement these. The
engine NEVER auto-applies optimizations — they're surfaced for
human review only.

Public API:
    register_feedback_survey(survey_data, actor, reason)
    transition_survey_state(survey_id, new_state, actor, reason)
    record_feedback_response(response_data, actor)
    register_optimization_recommendation(rec_data, actor, reason)
    transition_recommendation_state(rec_id, new_state, actor, reason)
    feedback_summary(days=30) -> Dict
    surface_optimizations(ml_optimize_fn=None) -> Dict

FEEDBACK_CHANNELS byte-for-byte (5):
    POST_COMPLETION_SMS, POST_COMPLETION_EMAIL,
    IN_APP_PROMPT, AGENT_DEBRIEF, OUTBOUND_CALL

SURVEY_STATES byte-for-byte (4):
    DRAFT, ACTIVE, PAUSED, ARCHIVED

ALLOWED_SURVEY_TRANSITIONS (Rule 4):
    DRAFT    → ACTIVE | ARCHIVED
    ACTIVE   → PAUSED | ARCHIVED
    PAUSED   → ACTIVE | ARCHIVED
    ARCHIVED → ()

FEEDBACK_DIMENSIONS byte-for-byte (6):
    OVERALL_SATISFACTION, EASE_OF_USE, SPEED,
    AGENT_HELPFULNESS, OUTCOME_MET_EXPECTATIONS, NPS

NPS_TIERS byte-for-byte (3):
    PROMOTER, PASSIVE, DETRACTOR

NPS_TIER_THRESHOLDS byte-for-byte:
    PROMOTER >= 9
    PASSIVE 7..8
    DETRACTOR <= 6

OPTIMIZATION_RECOMMENDATION_KINDS byte-for-byte (8):
    CHANNEL_REROUTE, CLASSIFICATION_RETRAIN, STP_THRESHOLD_TUNE,
    NBA_RULE_REVISION, EXCEPTION_PLAYBOOK_UPDATE,
    SLA_TARGET_REVISION, AGENT_TRAINING, COMMS_REVISION

RECOMMENDATION_STATES byte-for-byte (5):
    PROPOSED, UNDER_REVIEW, ACCEPTED, REJECTED, IMPLEMENTED

ALLOWED_RECOMMENDATION_TRANSITIONS (Rule 4):
    PROPOSED     → UNDER_REVIEW | REJECTED
    UNDER_REVIEW → ACCEPTED | REJECTED
    ACCEPTED     → IMPLEMENTED | REJECTED
    REJECTED     → ()
    IMPLEMENTED  → ()

DEFAULT_FEEDBACK_RETENTION_DAYS = 365
DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION = 30
DEFAULT_NPS_PROMOTER_THRESHOLD = 9
DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD = 7

SPEC_DEVIATION_NOTE = (
    "Per Rule 7 Cat D pattern: ml_optimize_fn is an optional factory "
    "hook. When not wired, surface_optimizations returns "
    "basis='rule_based' with ml_recommendations=None and a reason "
    "field. When wired, ML output is surfaced alongside rule_based "
    "for review; deterministic rule_based recommendations are "
    "ALWAYS present. The engine NEVER auto-applies any "
    "recommendation — they require human review and explicit "
    "transition through the recommendation state machine."
)

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


FEEDBACK_CHANNELS: Tuple[str, ...] = (
    "POST_COMPLETION_SMS", "POST_COMPLETION_EMAIL",
    "IN_APP_PROMPT", "AGENT_DEBRIEF", "OUTBOUND_CALL",
)

SURVEY_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "PAUSED", "ARCHIVED",
)

ALLOWED_SURVEY_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":    ("ACTIVE", "ARCHIVED"),
    "ACTIVE":   ("PAUSED", "ARCHIVED"),
    "PAUSED":   ("ACTIVE", "ARCHIVED"),
    "ARCHIVED": (),
}

FEEDBACK_DIMENSIONS: Tuple[str, ...] = (
    "OVERALL_SATISFACTION", "EASE_OF_USE", "SPEED",
    "AGENT_HELPFULNESS", "OUTCOME_MET_EXPECTATIONS", "NPS",
)

NPS_TIERS: Tuple[str, ...] = (
    "PROMOTER", "PASSIVE", "DETRACTOR",
)

OPTIMIZATION_RECOMMENDATION_KINDS: Tuple[str, ...] = (
    "CHANNEL_REROUTE", "CLASSIFICATION_RETRAIN",
    "STP_THRESHOLD_TUNE", "NBA_RULE_REVISION",
    "EXCEPTION_PLAYBOOK_UPDATE", "SLA_TARGET_REVISION",
    "AGENT_TRAINING", "COMMS_REVISION",
)

RECOMMENDATION_STATES: Tuple[str, ...] = (
    "PROPOSED", "UNDER_REVIEW", "ACCEPTED",
    "REJECTED", "IMPLEMENTED",
)

ALLOWED_RECOMMENDATION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "PROPOSED":     ("UNDER_REVIEW", "REJECTED"),
    "UNDER_REVIEW": ("ACCEPTED", "REJECTED"),
    "ACCEPTED":     ("IMPLEMENTED", "REJECTED"),
    "REJECTED":     (),
    "IMPLEMENTED":  (),
}

DEFAULT_FEEDBACK_RETENTION_DAYS = 365
DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION = 30
DEFAULT_NPS_PROMOTER_THRESHOLD = 9
DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD = 7

SPEC_DEVIATION_NOTE = (
    "Per Rule 7 Cat D pattern: ml_optimize_fn is an optional factory "
    "hook. When not wired, surface_optimizations returns "
    "basis='rule_based' with ml_recommendations=None and a reason "
    "field. When wired, ML output is surfaced alongside rule_based "
    "for review; deterministic rule_based recommendations are "
    "ALWAYS present. The engine NEVER auto-applies any "
    "recommendation — they require human review and explicit "
    "transition through the recommendation state machine."
)


def _classify_nps(score: int) -> str:
    if score >= DEFAULT_NPS_PROMOTER_THRESHOLD:
        return "PROMOTER"
    if score >= DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD:
        return "PASSIVE"
    return "DETRACTOR"


class CompletionFeedbackEngine:
    """Feedback survey + response + optimization recommendation registry.
    Cat D scaffolded surface_optimizations.
    """

    def __init__(
        self,
        surveys_path: Optional[Path] = None,
        responses_path: Optional[Path] = None,
        recommendations_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.surveys_path = (
            surveys_path or base / "cims_feedback_surveys.json"
        )
        self.responses_path = (
            responses_path or base / "cims_feedback_responses.json"
        )
        self.recommendations_path = (
            recommendations_path
            or base / "cims_optimization_recommendations.json"
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

    def register_feedback_survey(
        self, survey_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("survey_id", "name", "channel", "dimensions"):
            if f not in survey_data or survey_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        if survey_data["channel"] not in FEEDBACK_CHANNELS:
            return {"registered": False,
                       "error": f"invalid_channel:{survey_data['channel']}"}
        dimensions = survey_data["dimensions"]
        if not isinstance(dimensions, list) or not dimensions:
            return {"registered": False,
                       "error": "dimensions_must_be_non_empty_list"}
        for d in dimensions:
            if d not in FEEDBACK_DIMENSIONS:
                return {"registered": False,
                           "error": f"invalid_dimension:{d}"}
        records = self._load(self.surveys_path,
                                "cims_feedback_surveys", ("survey_id",))
        if any(r.get("survey_id") == survey_data["survey_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_survey_id"}
        record = {
            "survey_id": survey_data["survey_id"],
            "name": survey_data["name"],
            "channel": survey_data["channel"],
            "dimensions": dimensions,
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
        ok = self._save(self.surveys_path, records,
                          "cims_feedback_surveys", "survey_id")
        return {"registered": ok, "survey_id": survey_data["survey_id"]}

    def transition_survey_state(
        self, survey_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in SURVEY_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.surveys_path,
                                "cims_feedback_surveys", ("survey_id",))
        for r in records:
            if r.get("survey_id") == survey_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_SURVEY_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.surveys_path, records,
                                  "cims_feedback_surveys", "survey_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "survey_not_found"}

    def record_feedback_response(
        self, response_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("response_id", "survey_id",
                      "linked_session_id", "scores"):
            if f not in response_data or response_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        scores = response_data["scores"]
        if not isinstance(scores, dict) or not scores:
            return {"recorded": False,
                       "error": "scores_must_be_non_empty_dict"}
        for dim, score in scores.items():
            if dim not in FEEDBACK_DIMENSIONS:
                return {"recorded": False,
                           "error": f"invalid_dimension:{dim}"}
            try:
                s = int(score)
            except (TypeError, ValueError):
                return {"recorded": False,
                           "error": f"score_not_int:{dim}"}
            if dim == "NPS":
                if s < 0 or s > 10:
                    return {"recorded": False,
                               "error": "nps_out_of_range_0_10"}
            else:
                if s < 1 or s > 5:
                    return {"recorded": False,
                               "error": f"score_out_of_range_1_5:{dim}"}
        records = self._load(self.responses_path,
                                "cims_feedback_responses", ("response_id",))
        if any(r.get("response_id") == response_data["response_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_response_id"}
        record = {
            "response_id": response_data["response_id"],
            "survey_id": response_data["survey_id"],
            "linked_session_id": response_data["linked_session_id"],
            "scores": dict(scores),
            "narrative": response_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        # Annotate NPS tier if NPS score present
        if "NPS" in scores:
            record["nps_tier"] = _classify_nps(int(scores["NPS"]))
        records.append(record)
        ok = self._save(self.responses_path, records,
                          "cims_feedback_responses", "response_id")
        return {"recorded": ok,
                  "response_id": response_data["response_id"]}

    def register_optimization_recommendation(
        self, rec_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("recommendation_id", "kind", "narrative"):
            if f not in rec_data or not rec_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if rec_data["kind"] not in OPTIMIZATION_RECOMMENDATION_KINDS:
            return {"registered": False,
                       "error": f"invalid_kind:{rec_data['kind']}"}
        records = self._load(self.recommendations_path,
                                "cims_optimization_recommendations",
                                ("recommendation_id",))
        if any(r.get("recommendation_id") == rec_data["recommendation_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_recommendation_id"}
        record = {
            "recommendation_id": rec_data["recommendation_id"],
            "kind": rec_data["kind"],
            "narrative": rec_data["narrative"],
            "supporting_evidence":
                rec_data.get("supporting_evidence", ""),
            "basis": rec_data.get("basis", "rule_based"),
            "state": "PROPOSED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "PROPOSED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.recommendations_path, records,
                          "cims_optimization_recommendations",
                          "recommendation_id")
        return {"registered": ok,
                  "recommendation_id": rec_data["recommendation_id"]}

    def transition_recommendation_state(
        self, recommendation_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in RECOMMENDATION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.recommendations_path,
                                "cims_optimization_recommendations",
                                ("recommendation_id",))
        for r in records:
            if r.get("recommendation_id") == recommendation_id:
                current = r.get("state", "PROPOSED")
                allowed = ALLOWED_RECOMMENDATION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.recommendations_path, records,
                                  "cims_optimization_recommendations",
                                  "recommendation_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "recommendation_not_found"}

    def feedback_summary(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        responses = [
            r for r in self._load(self.responses_path,
                                            "cims_feedback_responses",
                                            ("response_id",))
            if r.get("recorded_at", "") >= cutoff
        ]
        # NPS calculation
        nps_scores = [
            r["scores"]["NPS"] for r in responses
            if isinstance(r.get("scores"), dict) and "NPS" in r["scores"]
        ]
        promoters = sum(
            1 for s in nps_scores
            if s >= DEFAULT_NPS_PROMOTER_THRESHOLD
        )
        detractors = sum(
            1 for s in nps_scores
            if s < DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD
        )
        nps = None
        if nps_scores:
            nps = round(
                ((promoters - detractors) / len(nps_scores)) * 100, 1,
            )
        # Per-dimension averages (1-5 dims only)
        per_dim_sum: Dict[str, float] = {}
        per_dim_count: Dict[str, int] = {}
        for r in responses:
            scores = r.get("scores", {})
            for dim, score in scores.items():
                if dim == "NPS":
                    continue
                per_dim_sum[dim] = (
                    per_dim_sum.get(dim, 0) + float(score)
                )
                per_dim_count[dim] = per_dim_count.get(dim, 0) + 1
        per_dim_avg = {
            d: round(per_dim_sum[d] / per_dim_count[d], 2)
            for d in per_dim_sum
        }
        return {
            "window_days": days,
            "total_responses": len(responses),
            "nps_responses": len(nps_scores),
            "nps_score": nps,
            "promoters": promoters,
            "detractors": detractors,
            "per_dimension_avg": per_dim_avg,
        }

    def surface_optimizations(
        self,
        ml_optimize_fn: Optional[
            Callable[[Dict[str, Any]], List[Dict[str, Any]]]
        ] = None,
    ) -> Dict[str, Any]:
        """Cat D Rule 7 scaffold: rule_based always; ml when wired.

        Rule-based recommendations are derived from feedback summary
        signals (low NPS, low dimension averages); when below the
        minimum response threshold, the engine surfaces "insufficient
        data" rather than guessing.
        """
        summary = self.feedback_summary(
            days=DEFAULT_FEEDBACK_RETENTION_DAYS,
        )
        rule_based: List[Dict[str, Any]] = []
        if (
            summary["total_responses"]
            < DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION
        ):
            rule_based.append({
                "kind": None,
                "narrative": "INSUFFICIENT_DATA",
                "evidence": (
                    f"Only {summary['total_responses']} responses; "
                    f"need at least "
                    f"{DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION}"
                ),
            })
        else:
            # NPS detractor signal
            if (summary["nps_score"] is not None
                    and summary["nps_score"] < 0):
                rule_based.append({
                    "kind": "AGENT_TRAINING",
                    "narrative": (
                        "NPS below 0 — agent training and "
                        "communication revision recommended"
                    ),
                    "evidence": f"NPS = {summary['nps_score']}",
                })
            # Per-dim signals
            for dim, avg in summary["per_dimension_avg"].items():
                if avg < 3.0:
                    if dim == "SPEED":
                        kind = "STP_THRESHOLD_TUNE"
                    elif dim == "EASE_OF_USE":
                        kind = "COMMS_REVISION"
                    elif dim == "AGENT_HELPFULNESS":
                        kind = "AGENT_TRAINING"
                    elif dim == "OUTCOME_MET_EXPECTATIONS":
                        kind = "EXCEPTION_PLAYBOOK_UPDATE"
                    else:
                        kind = "COMMS_REVISION"
                    rule_based.append({
                        "kind": kind,
                        "narrative": f"{dim} average {avg} below 3.0",
                        "evidence": f"avg_{dim.lower()}={avg}",
                    })
        result: Dict[str, Any] = {
            "rule_based_recommendations": rule_based,
            "ml_recommendations": None,
            "basis": "rule_based",
            "summary": summary,
            "spec_deviation": SPEC_DEVIATION_NOTE,
        }
        if ml_optimize_fn is None:
            result["reason"] = (
                "no_ml_model_wired; rule_based deterministic "
                "recommendations used"
            )
            return result
        try:
            ml_out = ml_optimize_fn(summary)
            if not isinstance(ml_out, list):
                raise TypeError("ml_optimize_fn must return a list")
            result["ml_recommendations"] = ml_out
            result["basis"] = "ml"
            result["reason"] = "ml_model_wired"
        except Exception as exc:
            result["ml_error"] = f"{type(exc).__name__}: {exc}"
            result["reason"] = (
                "ml_optimize_fn_raised; falling back to rule_based"
            )
        return result


def _self_test() -> None:
    import tempfile

    assert FEEDBACK_CHANNELS == (
        "POST_COMPLETION_SMS", "POST_COMPLETION_EMAIL",
        "IN_APP_PROMPT", "AGENT_DEBRIEF", "OUTBOUND_CALL",
    )
    assert SURVEY_STATES == ("DRAFT", "ACTIVE", "PAUSED", "ARCHIVED")
    assert ALLOWED_SURVEY_TRANSITIONS["ARCHIVED"] == ()
    assert FEEDBACK_DIMENSIONS == (
        "OVERALL_SATISFACTION", "EASE_OF_USE", "SPEED",
        "AGENT_HELPFULNESS", "OUTCOME_MET_EXPECTATIONS", "NPS",
    )
    assert NPS_TIERS == ("PROMOTER", "PASSIVE", "DETRACTOR")
    assert OPTIMIZATION_RECOMMENDATION_KINDS == (
        "CHANNEL_REROUTE", "CLASSIFICATION_RETRAIN",
        "STP_THRESHOLD_TUNE", "NBA_RULE_REVISION",
        "EXCEPTION_PLAYBOOK_UPDATE", "SLA_TARGET_REVISION",
        "AGENT_TRAINING", "COMMS_REVISION",
    )
    assert RECOMMENDATION_STATES == (
        "PROPOSED", "UNDER_REVIEW", "ACCEPTED",
        "REJECTED", "IMPLEMENTED",
    )
    assert ALLOWED_RECOMMENDATION_TRANSITIONS["REJECTED"] == ()
    assert ALLOWED_RECOMMENDATION_TRANSITIONS["IMPLEMENTED"] == ()
    assert DEFAULT_FEEDBACK_RETENTION_DAYS == 365
    assert DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION == 30
    assert DEFAULT_NPS_PROMOTER_THRESHOLD == 9
    assert DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD == 7
    assert _classify_nps(10) == "PROMOTER"
    assert _classify_nps(9) == "PROMOTER"
    assert _classify_nps(8) == "PASSIVE"
    assert _classify_nps(7) == "PASSIVE"
    assert _classify_nps(6) == "DETRACTOR"
    assert _classify_nps(0) == "DETRACTOR"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = CompletionFeedbackEngine(
            surveys_path=Path(tmpdir) / "s.json",
            responses_path=Path(tmpdir) / "r.json",
            recommendations_path=Path(tmpdir) / "rc.json",
        )
        # Survey
        r = e.register_feedback_survey(
            {"survey_id": "SV-001",
             "name": "Post-completion CSAT",
             "channel": "POST_COMPLETION_SMS",
             "dimensions": [
                 "OVERALL_SATISFACTION", "EASE_OF_USE", "NPS",
             ]},
            actor="ops", reason="weekly survey",
        )
        assert r["registered"]
        # Bad channel
        r = e.register_feedback_survey(
            {"survey_id": "X", "name": "Y",
             "channel": "WHATEVER",
             "dimensions": ["NPS"]},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Bad dimension
        r = e.register_feedback_survey(
            {"survey_id": "Z", "name": "Y",
             "channel": "POST_COMPLETION_SMS",
             "dimensions": ["WHATEVER"]},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_survey_state(
            "SV-001", "ACTIVE", actor="ops", reason="ready",
        )
        assert r["transitioned"]

        # Response — valid
        r = e.record_feedback_response(
            {"response_id": "RS-001",
             "survey_id": "SV-001",
             "linked_session_id": "CAP-001",
             "scores": {
                 "OVERALL_SATISFACTION": 4,
                 "EASE_OF_USE": 5,
                 "NPS": 9,
             }},
            actor="ops",
        )
        assert r["recorded"]

        # Response — bad NPS range
        r = e.record_feedback_response(
            {"response_id": "X",
             "survey_id": "SV-001",
             "linked_session_id": "Y",
             "scores": {"NPS": 11}},
            actor="x",
        )
        assert not r["recorded"]
        # Response — bad 1-5 range
        r = e.record_feedback_response(
            {"response_id": "Z",
             "survey_id": "SV-001",
             "linked_session_id": "Y",
             "scores": {"OVERALL_SATISFACTION": 6}},
            actor="x",
        )
        assert not r["recorded"]
        # Response — bad dimension
        r = e.record_feedback_response(
            {"response_id": "W",
             "survey_id": "SV-001",
             "linked_session_id": "Y",
             "scores": {"WHATEVER": 5}},
            actor="x",
        )
        assert not r["recorded"]

        # Recommendation
        r = e.register_optimization_recommendation(
            {"recommendation_id": "REC-001",
             "kind": "AGENT_TRAINING",
             "narrative": "Low CSAT after agent handoff"},
            actor="ops", reason="from feedback",
        )
        assert r["registered"]
        # Bad kind
        r = e.register_optimization_recommendation(
            {"recommendation_id": "X",
             "kind": "WHATEVER",
             "narrative": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_recommendation_state(
            "REC-001", "UNDER_REVIEW",
            actor="ops", reason="review",
        )
        assert r["transitioned"]
        r = e.transition_recommendation_state(
            "REC-001", "ACCEPTED",
            actor="md", reason="approved",
        )
        assert r["transitioned"]
        r = e.transition_recommendation_state(
            "REC-001", "IMPLEMENTED",
            actor="ops", reason="rolled out",
        )
        assert r["transitioned"]
        # IMPLEMENTED is terminal
        r = e.transition_recommendation_state(
            "REC-001", "PROPOSED", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Summary
        s = e.feedback_summary(days=365)
        assert s["total_responses"] == 1
        assert s["nps_score"] == 100.0  # 1 promoter / 1 = 100
        assert s["per_dimension_avg"]["OVERALL_SATISFACTION"] == 4.0

        # Surface optimizations — only 1 response, below threshold
        out = e.surface_optimizations()
        assert out["basis"] == "rule_based"
        assert out["ml_recommendations"] is None
        assert any(
            r["narrative"] == "INSUFFICIENT_DATA"
            for r in out["rule_based_recommendations"]
        )
        assert "spec_deviation" in out

        # ML hook wired
        def ml_opt(s):
            return [{"kind": "STP_THRESHOLD_TUNE",
                       "narrative": "ML says tune STP"}]
        out = e.surface_optimizations(ml_optimize_fn=ml_opt)
        assert out["basis"] == "ml"
        assert out["ml_recommendations"][0]["kind"] == "STP_THRESHOLD_TUNE"

        # ML hook fails — fall back
        def ml_broken(s):
            raise RuntimeError("model down")
        out = e.surface_optimizations(ml_optimize_fn=ml_broken)
        assert out["basis"] == "rule_based"
        assert out["ml_recommendations"] is None
        assert "ml_error" in out

    print("  ✅ cims_completion_feedback self-test PASS")


if __name__ == "__main__":
    _self_test()

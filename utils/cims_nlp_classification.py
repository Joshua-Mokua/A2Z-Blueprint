"""
================================================================================
A2Z MIS 360 — Standard #167: NLP Instruction Classification Engine
================================================================================

Risk classification: Cat C (read-side classification; never auto-acts on
classified intent — output goes to STP engine for routing decisions).

Subcategory: cims (Customer Instructions Management System)

AI-powered intent classification using a fine-tuned banking NLP model.
The model itself is a configured external service (LLM call or
specialized banking-NLP endpoint); this module owns the request
lifecycle, the confidence record, the human-in-the-loop override flow,
and the model-version tracking. Every classification has a confidence
tier; below-threshold classifications route to manual review by an
agent (handled by #178 Agent Workspace).

Public API:
    register_classification_request(request_data, actor)
    record_classification_result(result_data, actor)
    transition_classification_state(request_id, new_state, actor, reason)
    record_human_override(override_data, actor, reason)
    register_model_version(version_data, actor, reason)
    classification_metrics(days=30) -> Dict
    requests_below_confidence(threshold='HIGH') -> List

INTENT_CATEGORIES byte-for-byte (8):
    INFORMATION_REQUEST, ACCOUNT_OPERATION, COMPLAINT,
    APPLICATION_NEW, AMENDMENT_EXISTING, COMPLEX_INQUIRY,
    OUT_OF_SCOPE, AMBIGUOUS

CONFIDENCE_TIERS byte-for-byte (4):
    HIGH, MEDIUM, LOW, UNKNOWN

CLASSIFICATION_STATES byte-for-byte (5):
    SUBMITTED, CLASSIFIED, OVERRIDDEN, CONFIRMED, REJECTED

ALLOWED_CLASSIFICATION_TRANSITIONS (Rule 4):
    SUBMITTED   → CLASSIFIED | REJECTED
    CLASSIFIED  → OVERRIDDEN | CONFIRMED | REJECTED
    OVERRIDDEN  → CONFIRMED | REJECTED
    CONFIRMED   → ()
    REJECTED    → ()

MODEL_VERSION_STATES byte-for-byte (4):
    CANDIDATE, ACTIVE, DEPRECATED, ARCHIVED

ALLOWED_MODEL_TRANSITIONS (Rule 4):
    CANDIDATE  → ACTIVE | ARCHIVED
    ACTIVE     → DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

DEFAULT_CONFIDENCE_HIGH_THRESHOLD = 0.85
DEFAULT_CONFIDENCE_MEDIUM_THRESHOLD = 0.65
DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS = 5

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


INTENT_CATEGORIES: Tuple[str, ...] = (
    "INFORMATION_REQUEST", "ACCOUNT_OPERATION", "COMPLAINT",
    "APPLICATION_NEW", "AMENDMENT_EXISTING", "COMPLEX_INQUIRY",
    "OUT_OF_SCOPE", "AMBIGUOUS",
)

CONFIDENCE_TIERS: Tuple[str, ...] = (
    "HIGH", "MEDIUM", "LOW", "UNKNOWN",
)

CLASSIFICATION_STATES: Tuple[str, ...] = (
    "SUBMITTED", "CLASSIFIED", "OVERRIDDEN",
    "CONFIRMED", "REJECTED",
)

ALLOWED_CLASSIFICATION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "SUBMITTED":  ("CLASSIFIED", "REJECTED"),
    "CLASSIFIED": ("OVERRIDDEN", "CONFIRMED", "REJECTED"),
    "OVERRIDDEN": ("CONFIRMED", "REJECTED"),
    "CONFIRMED":  (),
    "REJECTED":   (),
}

MODEL_VERSION_STATES: Tuple[str, ...] = (
    "CANDIDATE", "ACTIVE", "DEPRECATED", "ARCHIVED",
)

ALLOWED_MODEL_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "CANDIDATE":  ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

DEFAULT_CONFIDENCE_HIGH_THRESHOLD = 0.85
DEFAULT_CONFIDENCE_MEDIUM_THRESHOLD = 0.65
DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS = 5


class NLPClassificationEngine:
    """NLP request → classification → override → confirm registry.

    Diagnostic only (Rule 7) — never auto-acts on classified intent.
    The classification result is consumed by the STP engine (#168) and
    Next Best Action engine (#174) for routing decisions.
    """

    def __init__(
        self,
        requests_path: Optional[Path] = None,
        results_path: Optional[Path] = None,
        overrides_path: Optional[Path] = None,
        models_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.requests_path = (
            requests_path or base / "cims_nlp_requests.json"
        )
        self.results_path = (
            results_path or base / "cims_nlp_results.json"
        )
        self.overrides_path = (
            overrides_path or base / "cims_nlp_overrides.json"
        )
        self.models_path = (
            models_path or base / "cims_nlp_model_versions.json"
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

    def register_classification_request(
        self, request_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("request_id", "capture_session_id", "raw_text"):
            if f not in request_data or not request_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.requests_path,
                                "cims_nlp_requests", ("request_id",))
        if any(r.get("request_id") == request_data["request_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_request_id"}
        record = {
            "request_id": request_data["request_id"],
            "capture_session_id": request_data["capture_session_id"],
            "raw_text": request_data["raw_text"],
            "channel_hint": request_data.get("channel_hint", ""),
            "state": "SUBMITTED",
            "submitted_by": actor,
            "submitted_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "SUBMITTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.requests_path, records,
                          "cims_nlp_requests", "request_id")
        return {"registered": ok,
                  "request_id": request_data["request_id"]}

    def record_classification_result(
        self, result_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("result_id", "request_id", "intent",
                      "confidence_tier", "model_version"):
            if f not in result_data or result_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        if result_data["intent"] not in INTENT_CATEGORIES:
            return {"recorded": False,
                       "error": f"invalid_intent:{result_data['intent']}"}
        if result_data["confidence_tier"] not in CONFIDENCE_TIERS:
            return {"recorded": False,
                       "error": f"invalid_confidence_tier:{result_data['confidence_tier']}"}
        records = self._load(self.results_path,
                                "cims_nlp_results", ("result_id",))
        if any(r.get("result_id") == result_data["result_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_result_id"}
        record = {
            "result_id": result_data["result_id"],
            "request_id": result_data["request_id"],
            "intent": result_data["intent"],
            "confidence_tier": result_data["confidence_tier"],
            "confidence_score": result_data.get("confidence_score"),
            "model_version": result_data["model_version"],
            "secondary_intents": list(
                result_data.get("secondary_intents", []),
            ),
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.results_path, records,
                          "cims_nlp_results", "result_id")
        return {"recorded": ok, "result_id": result_data["result_id"]}

    def transition_classification_state(
        self, request_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in CLASSIFICATION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.requests_path,
                                "cims_nlp_requests", ("request_id",))
        for r in records:
            if r.get("request_id") == request_id:
                current = r.get("state", "SUBMITTED")
                allowed = ALLOWED_CLASSIFICATION_TRANSITIONS.get(current, ())
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
                                  "cims_nlp_requests", "request_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "request_not_found"}

    def record_human_override(
        self, override_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"recorded": False, "error": "actor_and_reason_required"}
        for f in ("override_id", "request_id",
                      "original_intent", "corrected_intent"):
            if f not in override_data or not override_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if override_data["original_intent"] not in INTENT_CATEGORIES:
            return {"recorded": False,
                       "error": f"invalid_original_intent:{override_data['original_intent']}"}
        if override_data["corrected_intent"] not in INTENT_CATEGORIES:
            return {"recorded": False,
                       "error": f"invalid_corrected_intent:{override_data['corrected_intent']}"}
        records = self._load(self.overrides_path,
                                "cims_nlp_overrides", ("override_id",))
        if any(r.get("override_id") == override_data["override_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_override_id"}
        record = {
            "override_id": override_data["override_id"],
            "request_id": override_data["request_id"],
            "original_intent": override_data["original_intent"],
            "corrected_intent": override_data["corrected_intent"],
            "rationale": reason,
            "recorded_at": datetime.utcnow().isoformat(),
            "recorded_by": actor,
        }
        records.append(record)
        ok = self._save(self.overrides_path, records,
                          "cims_nlp_overrides", "override_id")
        return {"recorded": ok, "override_id": override_data["override_id"]}

    def register_model_version(
        self, version_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("version_id", "model_name", "model_endpoint"):
            if f not in version_data or not version_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.models_path,
                                "cims_nlp_model_versions", ("version_id",))
        if any(r.get("version_id") == version_data["version_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_version_id"}
        record = {
            "version_id": version_data["version_id"],
            "model_name": version_data["model_name"],
            "model_endpoint": version_data["model_endpoint"],
            "training_dataset": version_data.get("training_dataset", ""),
            "state": "CANDIDATE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "CANDIDATE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.models_path, records,
                          "cims_nlp_model_versions", "version_id")
        return {"registered": ok, "version_id": version_data["version_id"]}

    def classification_metrics(self, days: int = 30) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        results = self._load(self.results_path,
                                "cims_nlp_results", ("result_id",))
        recent = [r for r in results
                       if r.get("recorded_at", "") >= cutoff]
        per_tier: Dict[str, int] = {}
        per_intent: Dict[str, int] = {}
        for r in recent:
            tier = r.get("confidence_tier", "")
            per_tier[tier] = per_tier.get(tier, 0) + 1
            intent = r.get("intent", "")
            per_intent[intent] = per_intent.get(intent, 0) + 1
        overrides = self._load(self.overrides_path,
                                    "cims_nlp_overrides", ("override_id",))
        recent_overrides = [
            o for o in overrides
            if o.get("recorded_at", "") >= cutoff
        ]
        return {
            "window_days": days,
            "total_classifications": len(recent),
            "per_confidence_tier": per_tier,
            "per_intent": per_intent,
            "human_overrides": len(recent_overrides),
            "override_rate_pct": round(
                (len(recent_overrides) / len(recent) * 100)
                if recent else 0, 1,
            ),
            "high_confidence_pct": round(
                (per_tier.get("HIGH", 0) / len(recent) * 100)
                if recent else 0, 1,
            ),
        }

    def requests_below_confidence(
        self, threshold: str = "HIGH",
    ) -> List[Dict[str, Any]]:
        if threshold not in CONFIDENCE_TIERS:
            return []
        # Map tiers to ranks for "below threshold" comparison
        ranks = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
        threshold_rank = ranks[threshold]
        results = self._load(self.results_path,
                                "cims_nlp_results", ("result_id",))
        return [
            r for r in results
            if ranks.get(r.get("confidence_tier", "UNKNOWN"), 0)
                  < threshold_rank
        ]


def _self_test() -> None:
    import tempfile

    assert INTENT_CATEGORIES == (
        "INFORMATION_REQUEST", "ACCOUNT_OPERATION", "COMPLAINT",
        "APPLICATION_NEW", "AMENDMENT_EXISTING", "COMPLEX_INQUIRY",
        "OUT_OF_SCOPE", "AMBIGUOUS",
    )
    assert CONFIDENCE_TIERS == ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
    assert CLASSIFICATION_STATES == (
        "SUBMITTED", "CLASSIFIED", "OVERRIDDEN",
        "CONFIRMED", "REJECTED",
    )
    assert ALLOWED_CLASSIFICATION_TRANSITIONS["CONFIRMED"] == ()
    assert ALLOWED_CLASSIFICATION_TRANSITIONS["REJECTED"] == ()
    assert MODEL_VERSION_STATES == (
        "CANDIDATE", "ACTIVE", "DEPRECATED", "ARCHIVED",
    )
    assert ALLOWED_MODEL_TRANSITIONS["ARCHIVED"] == ()
    assert DEFAULT_CONFIDENCE_HIGH_THRESHOLD == 0.85
    assert DEFAULT_CONFIDENCE_MEDIUM_THRESHOLD == 0.65
    assert DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS == 5

    with tempfile.TemporaryDirectory() as tmpdir:
        e = NLPClassificationEngine(
            requests_path=Path(tmpdir) / "r.json",
            results_path=Path(tmpdir) / "res.json",
            overrides_path=Path(tmpdir) / "o.json",
            models_path=Path(tmpdir) / "m.json",
        )
        # Model version
        r = e.register_model_version(
            {"version_id": "MOD-v1.0",
             "model_name": "banking-nlp-finetuned",
             "model_endpoint": "https://nlp.local/v1",
             "training_dataset": "internal-2026Q1"},
            actor="ml-team", reason="initial deployment",
        )
        assert r["registered"]

        # Request
        r = e.register_classification_request(
            {"request_id": "NLP-001",
             "capture_session_id": "CAP-001",
             "raw_text": "I want to send 5000 to my mum",
             "channel_hint": "MOBILE_APP"},
            actor="capture-svc",
        )
        assert r["registered"]
        # Missing field
        r = e.register_classification_request(
            {"request_id": "X"}, actor="x",
        )
        assert not r["registered"]

        # Lifecycle
        r = e.transition_classification_state(
            "NLP-001", "CLASSIFIED",
            actor="nlp-svc", reason="model returned",
        )
        assert r["transitioned"]

        # Result
        r = e.record_classification_result(
            {"result_id": "RES-001",
             "request_id": "NLP-001",
             "intent": "ACCOUNT_OPERATION",
             "confidence_tier": "HIGH",
             "confidence_score": 0.92,
             "model_version": "MOD-v1.0",
             "secondary_intents": ["INFORMATION_REQUEST"]},
            actor="nlp-svc",
        )
        assert r["recorded"]
        # Bad intent
        r = e.record_classification_result(
            {"result_id": "X", "request_id": "Y",
             "intent": "WHATEVER", "confidence_tier": "HIGH",
             "model_version": "MOD-v1.0"},
            actor="x",
        )
        assert not r["recorded"]
        # Bad confidence tier
        r = e.record_classification_result(
            {"result_id": "Z", "request_id": "Y",
             "intent": "ACCOUNT_OPERATION",
             "confidence_tier": "WHATEVER",
             "model_version": "MOD-v1.0"},
            actor="x",
        )
        assert not r["recorded"]

        # Confirm without override
        r = e.transition_classification_state(
            "NLP-001", "CONFIRMED",
            actor="agent", reason="HIGH confidence accepted",
        )
        assert r["transitioned"]
        # CONFIRMED is terminal
        r = e.transition_classification_state(
            "NLP-001", "OVERRIDDEN", actor="x", reason="x",
        )
        assert not r["transitioned"]

        # Low confidence path with override
        e.register_classification_request(
            {"request_id": "NLP-002",
             "capture_session_id": "CAP-002",
             "raw_text": "weird unclear text"},
            actor="capture-svc",
        )
        e.transition_classification_state(
            "NLP-002", "CLASSIFIED",
            actor="nlp-svc", reason="ambiguous",
        )
        e.record_classification_result(
            {"result_id": "RES-002",
             "request_id": "NLP-002",
             "intent": "AMBIGUOUS",
             "confidence_tier": "LOW",
             "confidence_score": 0.42,
             "model_version": "MOD-v1.0"},
            actor="nlp-svc",
        )
        r = e.record_human_override(
            {"override_id": "OVR-001",
             "request_id": "NLP-002",
             "original_intent": "AMBIGUOUS",
             "corrected_intent": "COMPLAINT"},
            actor="agent1",
            reason="customer was complaining about debit fee",
        )
        assert r["recorded"]
        e.transition_classification_state(
            "NLP-002", "OVERRIDDEN",
            actor="agent1", reason="manually corrected",
        )
        e.transition_classification_state(
            "NLP-002", "CONFIRMED",
            actor="agent1", reason="now correct",
        )

        # Below confidence
        below_high = e.requests_below_confidence(threshold="HIGH")
        assert len(below_high) == 1  # The LOW one
        below_medium = e.requests_below_confidence(threshold="MEDIUM")
        assert len(below_medium) == 1

        # Metrics
        m = e.classification_metrics(days=30)
        assert m["total_classifications"] == 2
        assert m["per_confidence_tier"]["HIGH"] == 1
        assert m["per_confidence_tier"]["LOW"] == 1
        assert m["human_overrides"] == 1
        assert m["override_rate_pct"] == 50.0
        assert m["high_confidence_pct"] == 50.0

    print("  ✅ cims_nlp_classification self-test PASS")


if __name__ == "__main__":
    _self_test()

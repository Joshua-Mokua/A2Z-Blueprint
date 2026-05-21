"""
================================================================================
A2Z MIS 360 — Standard #315: Natural-Language Query Interface
================================================================================

Risk classification: Cat C (NL → structured query mapping with RAG hook)

Natural-language query interface for executives:
    "show NPL trend by segment last quarter"
    "what's our deposit growth versus market"
    "highlight branches with deposit decline > 10%"

RAG over bank's data + context-aware. Production deployments override
the deterministic fallback via set_query_fn() to wire in a real RAG
pipeline.

Public API:
    submit_query(query_text, requester_role, context=None)
        -> {answer, confidence_pct, sources, structured_query, fallback_used}
    register_query_template(template_data, actor, reason)
    record_feedback(query_id, helpful: bool, actor, comment)
    set_query_fn(query_fn)  -- Rule 7 hook
    make_query_fn() -- Rule 7 factory (deterministic fallback)
    list_query_history(requester_role=None) -> List

QUERY_INTENT_TYPES byte-for-byte (8):
    METRIC_LOOKUP    -- "what's our NPL ratio"
    TREND_ANALYSIS   -- "show NPL trend last quarter"
    COMPARISON       -- "branches above peer avg"
    DRILL_DOWN       -- "NPL by segment"
    THRESHOLD_CHECK  -- "branches with NPL > 5%"
    RANKING          -- "top 10 customers by deposits"
    ATTRIBUTION      -- "what drove revenue change"
    UNKNOWN          -- intent could not be classified

QUERY_FEEDBACK_OUTCOMES byte-for-byte (3): HELPFUL, NOT_HELPFUL, PARTIALLY

DEFAULT_FALLBACK_CONFIDENCE_PCT = 30
HIGH_CONFIDENCE_THRESHOLD_PCT = 70

SPEC_DEVIATION_NOTE: Production NL query requires RAG pipeline (vector
store + LLM grounded on bank's structured + unstructured data). Current
fallback maps queries to a small set of templates via keyword matching.

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


SPEC_DEVIATION_NOTE: str = (
    "Production NL query (#315) requires RAG pipeline (vector store + "
    "grounded LLM). Current fallback maps queries to templates via "
    "keyword matching; deferred to deployment phase per Continuation.docx."
)

QUERY_INTENT_TYPES: Tuple[str, ...] = (
    "METRIC_LOOKUP", "TREND_ANALYSIS", "COMPARISON", "DRILL_DOWN",
    "THRESHOLD_CHECK", "RANKING", "ATTRIBUTION", "UNKNOWN",
)

QUERY_FEEDBACK_OUTCOMES: Tuple[str, ...] = (
    "HELPFUL", "NOT_HELPFUL", "PARTIALLY",
)

DEFAULT_FALLBACK_CONFIDENCE_PCT: int = 30
HIGH_CONFIDENCE_THRESHOLD_PCT: int = 70


_INTENT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "TREND_ANALYSIS": ("trend", "over time", "monthly", "quarterly", "yearly"),
    "COMPARISON": ("vs", "versus", "compared", "benchmark", "peer"),
    "DRILL_DOWN": ("by segment", "by product", "by branch", "by region", "breakdown"),
    "THRESHOLD_CHECK": ("greater than", "less than", ">", "<", "above", "below"),
    "RANKING": ("top", "bottom", "rank", "best", "worst"),
    "ATTRIBUTION": ("why", "drove", "caused", "explain"),
    "METRIC_LOOKUP": ("what is", "what's", "show me"),
}


def _deterministic_query(
    query_text: str, requester_role: str,
    templates: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Keyword-based fallback. Maps query text to intent + nearest template."""
    text_lower = query_text.lower().strip()
    if not text_lower:
        return {
            "answer": "Empty query.",
            "confidence_pct": 0,
            "intent": "UNKNOWN",
            "structured_query": None,
            "matched_template": None,
            "sources": [],
        }

    # Detect intent
    intent = "UNKNOWN"
    intent_score = 0
    for candidate, kws in _INTENT_KEYWORDS.items():
        score = sum(1 for k in kws if k in text_lower)
        if score > intent_score:
            intent_score = score
            intent = candidate

    # Match template by keyword overlap with template name + description
    matched = None
    matched_score = 0
    for tpl in (templates or []):
        if tpl.get("intent") != intent:
            continue
        tpl_text = (tpl.get("template_name", "") + " " +
                       tpl.get("description", "")).lower()
        tpl_words = set(tpl_text.split())
        query_words = set(text_lower.split())
        overlap = len(tpl_words & query_words)
        if overlap > matched_score:
            matched_score = overlap
            matched = tpl

    if matched:
        confidence = min(70, 30 + matched_score * 10)
        answer = (
            f"Best-match template: {matched.get('template_name', '?')}. "
            f"Recommend running structured query: "
            f"{matched.get('structured_query', '')}"
        )
        return {
            "answer": answer,
            "confidence_pct": confidence,
            "intent": intent,
            "structured_query": matched.get("structured_query"),
            "matched_template": matched.get("template_id"),
            "sources": matched.get("data_sources", []),
        }

    return {
        "answer": (
            f"Detected intent: {intent}. No matching template — please "
            "rephrase or use the structured query builder."
        ),
        "confidence_pct": DEFAULT_FALLBACK_CONFIDENCE_PCT,
        "intent": intent,
        "structured_query": None,
        "matched_template": None,
        "sources": [],
    }


def make_query_fn() -> Callable:
    """Rule 7 factory — returns deterministic NL query Callable."""
    return _deterministic_query


class CommandCentreNLQueryEngine:
    """Natural-language query interface with template registry + Rule 7 hook."""

    def __init__(
        self,
        templates_path: Optional[Path] = None,
        history_path: Optional[Path] = None,
        feedback_path: Optional[Path] = None,
        query_fn: Optional[Callable] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.templates_path = templates_path or base / "nl_query_templates.json"
        self.history_path = history_path or base / "nl_query_history.json"
        self.feedback_path = feedback_path or base / "nl_query_feedback.json"
        self._query_fn: Callable = query_fn or _deterministic_query

    def set_query_fn(self, fn: Callable) -> None:
        self._query_fn = fn

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

    def register_query_template(
        self, template_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("template_id", "template_name", "intent", "structured_query"):
            if f not in template_data or not template_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if template_data["intent"] not in QUERY_INTENT_TYPES:
            return {"registered": False,
                       "error": f"invalid_intent:{template_data['intent']}"}

        records = self._load(self.templates_path,
                                "nl_query_templates", ("template_id",))
        if any(r.get("template_id") == template_data["template_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_template_id"}

        record = {
            "template_id": template_data["template_id"],
            "template_name": template_data["template_name"],
            "description": template_data.get("description", ""),
            "intent": template_data["intent"],
            "structured_query": template_data["structured_query"],
            "data_sources": template_data.get("data_sources", []),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.templates_path, records,
                          "nl_query_templates", "template_id")
        return {"registered": ok, "template_id": template_data["template_id"]}

    def submit_query(
        self, query_text: str, requester_role: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not query_text or not query_text.strip():
            return {"submitted": False, "error": "empty_query"}
        if not requester_role:
            return {"submitted": False, "error": "requester_role_required"}

        templates = self._load(self.templates_path,
                                     "nl_query_templates", ("template_id",))
        result = self._query_fn(query_text, requester_role, templates, context)

        # Persist to history
        history = self._load(self.history_path, "nl_query_history",
                                  ("query_id",))
        query_id = (f"NLQ-{int(datetime.utcnow().timestamp() * 1000)}-"
                          f"{requester_role}")
        history.append({
            "query_id": query_id,
            "query_text": query_text,
            "requester_role": requester_role,
            "answer": result.get("answer", ""),
            "confidence_pct": result.get("confidence_pct", 0),
            "intent": result.get("intent", "UNKNOWN"),
            "structured_query": result.get("structured_query"),
            "matched_template": result.get("matched_template"),
            "sources": result.get("sources", []),
            "fallback_used": self._query_fn == _deterministic_query,
            "submitted_at": datetime.utcnow().isoformat(),
        })
        self._save(self.history_path, history,
                     "nl_query_history", "query_id")

        return {
            "submitted": True,
            "query_id": query_id,
            "answer": result.get("answer", ""),
            "confidence_pct": result.get("confidence_pct", 0),
            "intent": result.get("intent", "UNKNOWN"),
            "structured_query": result.get("structured_query"),
            "matched_template": result.get("matched_template"),
            "sources": result.get("sources", []),
            "fallback_used": self._query_fn == _deterministic_query,
            "high_confidence": (
                result.get("confidence_pct", 0) >= HIGH_CONFIDENCE_THRESHOLD_PCT
            ),
        }

    def record_feedback(
        self, query_id: str, outcome: str, actor: str,
        comment: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if outcome not in QUERY_FEEDBACK_OUTCOMES:
            return {"recorded": False, "error": f"invalid_outcome:{outcome}"}
        feedback = self._load(self.feedback_path, "nl_query_feedback",
                                   ("feedback_id",))
        feedback_id = (f"FB-{query_id}-"
                            f"{int(datetime.utcnow().timestamp() * 1000)}")
        feedback.append({
            "feedback_id": feedback_id,
            "query_id": query_id,
            "outcome": outcome,
            "comment": comment,
            "submitted_by": actor,
            "submitted_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.feedback_path, feedback,
                          "nl_query_feedback", "feedback_id")
        return {"recorded": ok, "feedback_id": feedback_id}

    def list_query_history(
        self, requester_role: Optional[str] = None, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        history = self._load(self.history_path, "nl_query_history",
                                   ("query_id",))
        if requester_role:
            history = [h for h in history
                          if h.get("requester_role") == requester_role]
        history.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
        return history[:limit]


def _self_test() -> None:
    import tempfile

    assert "METRIC_LOOKUP" in QUERY_INTENT_TYPES
    assert "HELPFUL" in QUERY_FEEDBACK_OUTCOMES
    assert SPEC_DEVIATION_NOTE
    assert callable(make_query_fn())

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreNLQueryEngine(
            templates_path=Path(tmpdir) / "t.json",
            history_path=Path(tmpdir) / "h.json",
            feedback_path=Path(tmpdir) / "f.json",
        )
        # Test 1: register template
        r = engine.register_query_template(
            {"template_id": "TPL-NPL-TREND",
             "template_name": "NPL trend by segment",
             "description": "show npl trend segment over time quarterly",
             "intent": "TREND_ANALYSIS",
             "structured_query": (
                 "SELECT period, segment, npl_ratio FROM npl_history "
                 "WHERE period >= NOW() - INTERVAL '90 days'"
             ),
             "data_sources": ["credit_kpi_store"]},
            actor="cdo", reason="exec dashboard support",
        )
        assert r["registered"]
        # Test 2: invalid intent
        r = engine.register_query_template(
            {"template_id": "X", "template_name": "Y",
             "intent": "INVALID", "structured_query": "Z"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: submit query — should match TREND_ANALYSIS template
        r = engine.submit_query(
            "show NPL trend by segment last quarter", "MD",
        )
        assert r["submitted"]
        # The keyword "trend" should detect TREND_ANALYSIS intent
        assert r["intent"] == "TREND_ANALYSIS"
        assert r["fallback_used"] is True
        # Test 4: empty query
        r = engine.submit_query("", "MD")
        assert not r["submitted"]
        # Test 5: missing role
        r = engine.submit_query("hello", "")
        assert not r["submitted"]
        # Test 6: feedback
        first_id = r.get("query_id") or "ANY"
        history = engine.list_query_history()
        first_id = history[0]["query_id"]
        f = engine.record_feedback(first_id, "HELPFUL", actor="md")
        assert f["recorded"]
        # Test 7: invalid feedback outcome
        f = engine.record_feedback(first_id, "OK", actor="md")
        assert not f["recorded"]
        # Test 8: history filter by role
        h = engine.list_query_history(requester_role="MD")
        assert len(h) >= 1
        h = engine.list_query_history(requester_role="BRANCH_MGR")
        assert h == []
        # Test 9: Rule 7 hook
        called = []
        def custom_fn(query_text, requester_role, templates, context):
            called.append(True)
            return {
                "answer": "ML answer",
                "confidence_pct": 95,
                "intent": "METRIC_LOOKUP",
                "structured_query": "SELECT 1",
                "matched_template": None,
                "sources": ["ml_pipeline"],
            }
        engine.set_query_fn(custom_fn)
        r = engine.submit_query("what's our NPL", "CRO")
        assert r["submitted"]
        assert r["fallback_used"] is False
        assert r["high_confidence"] is True
        assert called

    print("  ✅ command_centre_nl_query self-test PASS")


if __name__ == "__main__":
    _self_test()

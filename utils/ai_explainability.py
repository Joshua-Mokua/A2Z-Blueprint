"""utils/ai_explainability.py — AI decision explainability tracking.

Per Joshua Master Prompt Phase O2:
    'AI explainability tracking' — every AI decision must be observable,
    traceable, replayable, EXPLAINABLE.

Per Phase O6 (future v10.483-484):
    'Decision explainability... hallucination resistance, drift detection,
    bias detection, adversarial prompt resistance.'

Every AI inference in the codebase (credit scoring, AI underwriting,
LLM operational assistants, fraud detection, ECL forecasting) records
a structured decision via `record_ai_decision()`. The record captures:

  - model + version
  - prompt / inputs
  - response / output
  - reasoning factors (named contributors with weights)
  - confidence score
  - latency
  - actor + entity_id

This module is the foundation that O6 will build on for drift detection,
bias auditing, and adversarial resistance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).parent.parent
EXPLAIN_FILENAME = "ai_decisions.jsonl"


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class AIDecision:
    """A single AI inference / decision with full explainability."""
    id: str
    timestamp: str
    model: str
    model_version: str
    actor: str
    entity_id: str
    module: str
    prompt: Dict[str, Any]                 # inputs (NOT redacted here)
    response: Dict[str, Any]               # outputs
    reasoning_factors: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[float] = None
    latency_ms: Optional[float] = None
    severity: str = "info"
    environment: str = "dev"
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _explain_path() -> Path:
    """Mode-aware path for AI explainability log."""
    try:
        from utils.environment import environment_paths
        data_root = environment_paths()["data_root"]
    except ImportError:
        data_root = REPO / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    return data_root / EXPLAIN_FILENAME


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def record_ai_decision(
    *,
    model: str,
    prompt: Dict[str, Any],
    response: Dict[str, Any],
    actor: str = "system",
    entity_id: str = "",
    module: str = "ai",
    reasoning_factors: Optional[List[Dict[str, Any]]] = None,
    confidence: Optional[float] = None,
    latency_ms: Optional[float] = None,
    model_version: str = "1",
    severity: str = "info",
    correlation_id: Optional[str] = None,
) -> str:
    """Record an AI decision. Returns its id.

    Args:
        model: short model name (e.g. 'credit_alt_scoring')
        prompt: structured inputs the AI saw
        response: structured outputs
        reasoning_factors: list of dicts like
            [{"factor": "income", "value": 50000, "weight": 0.3},
             {"factor": "kyc_score", "value": 0.92, "weight": 0.5}]
        confidence: 0..1 model confidence
        latency_ms: inference latency in milliseconds
        actor / entity_id / module: provenance fields
        correlation_id: links this decision to a wider request flow
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    seed = f"{model}|{actor}|{entity_id}|{timestamp}"
    decision_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    try:
        from utils.environment import get_environment
        env = get_environment().value
    except ImportError:
        env = "dev"

    decision = AIDecision(
        id=decision_id,
        timestamp=timestamp,
        model=model,
        model_version=model_version,
        actor=actor or "system",
        entity_id=str(entity_id),
        module=module,
        prompt=prompt,
        response=response,
        reasoning_factors=reasoning_factors or [],
        confidence=confidence,
        latency_ms=latency_ms,
        severity=severity,
        environment=env,
        correlation_id=correlation_id,
    )

    # 1. Persist to JSONL
    try:
        with open(_explain_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), separators=(",", ":")) + "\n")
    except Exception:
        pass  # never fail caller on telemetry

    # 2. Emit into event_bus
    try:
        from utils.event_bus import get_event_bus
        get_event_bus().emit(
            event_type="ai.inference",
            actor=actor or "system",
            entity_id=str(entity_id),
            module=module,
            payload={
                "decision_id": decision_id,
                "model": model,
                "model_version": model_version,
                "confidence": confidence,
                "latency_ms": latency_ms,
                "n_factors": len(decision.reasoning_factors),
            },
            severity=severity,
            correlation_id=correlation_id,
        )
    except Exception:
        pass

    return decision_id


def get_ai_decisions(
    *,
    entity_id: Optional[str] = None,
    model: Optional[str] = None,
    actor: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
) -> List[AIDecision]:
    """Retrieve recorded AI decisions with optional filters."""
    path = _explain_path()
    if not path.exists():
        return []
    out: List[AIDecision] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    d = json.loads(line)
                    dec = AIDecision(**d)
                except Exception:
                    continue
                if entity_id and dec.entity_id != str(entity_id): continue
                if model and dec.model != model: continue
                if actor and dec.actor != actor: continue
                if since and dec.timestamp < since: continue
                if until and dec.timestamp > until: continue
                out.append(dec)
    except Exception:
        return out
    out.sort(key=lambda d: d.timestamp, reverse=True)
    return out[:limit]


def decision_explanation_card(decision_id: str) -> Optional[Dict[str, Any]]:
    """Return a human-readable explainability card for a decision.

    Used by UI to render the "why did the AI decide this?" panel.
    """
    path = _explain_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("id") == decision_id:
                    # Format factor contributions
                    factors_sorted = sorted(
                        d.get("reasoning_factors", []),
                        key=lambda x: abs(x.get("weight", 0)),
                        reverse=True,
                    )
                    top_3 = factors_sorted[:3]
                    return {
                        "decision_id": decision_id,
                        "when": d.get("timestamp"),
                        "model": d.get("model"),
                        "model_version": d.get("model_version"),
                        "entity": d.get("entity_id"),
                        "actor": d.get("actor"),
                        "outcome": d.get("response"),
                        "confidence": d.get("confidence"),
                        "latency_ms": d.get("latency_ms"),
                        "top_drivers": [
                            {
                                "factor": f.get("factor"),
                                "value": f.get("value"),
                                "weight": f.get("weight"),
                                "direction": (
                                    "positive" if f.get("weight", 0) >= 0
                                    else "negative"
                                ),
                            }
                            for f in top_3
                        ],
                        "all_factors": d.get("reasoning_factors", []),
                        "environment": d.get("environment"),
                    }
    except Exception:
        pass
    return None


def model_stats(model: str, *, since: Optional[str] = None,
                 until: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate stats for a model: decision count, mean confidence,
    mean latency, factor frequency.

    The seed for v10.483-484 drift/bias detection in Phase O6.
    """
    decisions = get_ai_decisions(model=model, since=since, until=until,
                                  limit=10_000)
    if not decisions:
        return {"model": model, "count": 0}

    confidences = [d.confidence for d in decisions if d.confidence is not None]
    latencies = [d.latency_ms for d in decisions if d.latency_ms is not None]

    from collections import Counter
    factor_freq: Counter = Counter()
    for d in decisions:
        for f in d.reasoning_factors:
            factor_freq[f.get("factor", "?")] += 1

    return {
        "model": model,
        "count": len(decisions),
        "first_at": decisions[-1].timestamp if decisions else None,
        "last_at": decisions[0].timestamp if decisions else None,
        "mean_confidence": (
            sum(confidences) / len(confidences) if confidences else None
        ),
        "mean_latency_ms": (
            sum(latencies) / len(latencies) if latencies else None
        ),
        "top_factors": [
            {"factor": f, "count": c}
            for f, c in factor_freq.most_common(10)
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_record_returns_id():
    did = record_ai_decision(
        model="test_model",
        prompt={"q": "approve loan?"},
        response={"answer": "yes"},
        reasoning_factors=[
            {"factor": "income", "value": 100_000, "weight": 0.4},
            {"factor": "kyc_score", "value": 0.95, "weight": 0.5},
        ],
        confidence=0.91,
        latency_ms=12.4,
        actor="ai_v10476_test",
        entity_id="AI_TEST_001",
        module="credit",
    )
    assert did and len(did) == 20


def _test_retrieve_by_entity():
    record_ai_decision(
        model="retrieve_test", prompt={"q": "x"}, response={"a": "y"},
        actor="ai_test_2", entity_id="AI_TEST_002", module="credit",
    )
    found = get_ai_decisions(entity_id="AI_TEST_002", limit=5)
    assert any(d.entity_id == "AI_TEST_002" for d in found)


def _test_explanation_card_returns_top_drivers():
    did = record_ai_decision(
        model="card_test", prompt={"q": "score"}, response={"score": 0.78},
        reasoning_factors=[
            {"factor": "income", "value": 60_000, "weight": 0.30},
            {"factor": "kyc_score", "value": 0.95, "weight": 0.45},
            {"factor": "loan_history", "value": "clean", "weight": 0.25},
            {"factor": "noise", "value": 0.0, "weight": 0.01},
        ],
        actor="card_test", entity_id="AI_CARD_001",
    )
    card = decision_explanation_card(did)
    assert card is not None
    assert len(card["top_drivers"]) == 3
    # Top driver should be the highest |weight|
    assert card["top_drivers"][0]["factor"] == "kyc_score"


def _test_emits_into_event_bus():
    from utils.event_bus import get_event_bus
    record_ai_decision(
        model="bus_test", prompt={"x": 1}, response={"y": 2},
        actor="bus_emitter", entity_id="AI_BUS_001",
    )
    events = get_event_bus().query(
        event_type="ai.inference", entity_id="AI_BUS_001", limit=5
    )
    assert any(e.event_type == "ai.inference" for e in events)


def _test_model_stats_aggregates():
    for i in range(5):
        record_ai_decision(
            model="stats_test", prompt={"i": i}, response={"o": i*2},
            confidence=0.5 + i*0.1, latency_ms=10.0 + i,
            reasoning_factors=[
                {"factor": "f1", "value": i, "weight": 0.5},
                {"factor": "f2", "value": i, "weight": 0.5},
            ],
            actor="stats", entity_id=f"AI_STATS_{i:03d}",
        )
    s = model_stats("stats_test")
    assert s["count"] >= 5
    assert s["mean_confidence"] is not None
    assert s["mean_latency_ms"] is not None
    factor_names = {f["factor"] for f in s["top_factors"]}
    assert "f1" in factor_names and "f2" in factor_names


def self_test() -> None:
    _test_record_returns_id()
    _test_retrieve_by_entity()
    _test_explanation_card_returns_top_drivers()
    _test_emits_into_event_bus()
    _test_model_stats_aggregates()


__all__ = [
    "AIDecision", "record_ai_decision", "get_ai_decisions",
    "decision_explanation_card", "model_stats", "EXPLAIN_FILENAME",
]


if __name__ == "__main__":
    import sys as _sys
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("ai_explainability self-test passed")

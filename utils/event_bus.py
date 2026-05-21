"""utils/event_bus.py — Centralised event bus for observable enterprise state.

Per Joshua Master Prompt (Enterprise Banking Digital Twin) Phase O2:
    'Every transaction, workflow, approval, escalation, AI inference,
     KPI generation, integration event, anomaly, compliance breach
     must become observable, traceable, replayable, explainable,
     auditable.'

This module provides the nervous system for the body. Every state-
changing operation in the codebase can call `emit(...)` to publish a
typed event. Events are:

  - **Persistent** (JSONL append-only at events.jsonl)
  - **Typed** (event_type taxonomy)
  - **Correlated** (correlation_id chains related events)
  - **Causal** (parent_event_id traces parent→child)
  - **Replayable** (every event has timestamp + actor + entity_id)
  - **Mode-aware** (PROD writes to data/events.jsonl; SIM to data/sim/events.jsonl)

This is distinct from `utils/audit_log` — audit_log is regulatory
traceability (who did what for compliance); event_bus is operational
observability (what happened in what causal chain for engineering).
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

REPO = Path(__file__).parent.parent
EVENTS_FILENAME = "events.jsonl"


# ──────────────────────────────────────────────────────────────────────
# Canonical event type taxonomy
# ──────────────────────────────────────────────────────────────────────

# Event types — flat namespace, dot-separated convention
# Categories:
#   workflow.*  — workflow state transitions
#   actuals.*   — BSC actuals lifecycle (compute / refresh / write)
#   integration.* — Flexcube / external system calls
#   approval.*  — approval-chain events
#   ai.*        — AI inference / model decisions
#   compliance.* — regulatory checks / breaches
#   anomaly.*   — auto-detected anomalies
#   data.*      — data migration / promotion
#   chaos.*     — chaos engineering injections (v10.482)
#   system.*    — bus lifecycle / boundary events
EVENT_TYPES_KNOWN: Set[str] = {
    "workflow.transition", "workflow.rollback", "workflow.created",
    "actuals.refresh.started", "actuals.refresh.completed",
    "actuals.refresh.failed", "actuals.computed",
    "integration.flexcube.call", "integration.flexcube.success",
    "integration.flexcube.failure",
    "approval.requested", "approval.granted", "approval.rejected",
    "approval.escalated",
    "ai.inference", "ai.decision", "ai.hallucination_detected",
    "compliance.check", "compliance.breach", "compliance.cleared",
    "anomaly.detected", "anomaly.resolved",
    "data.promoted", "data.migration.started", "data.migration.completed",
    "chaos.inject", "chaos.recovered",
    "system.event_bus.started", "system.event_bus.subscriber_added",
}

SEVERITY_VALUES = {"debug", "info", "warning", "error", "critical"}


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class Event:
    """A single observable event."""
    id: str
    timestamp: str
    event_type: str
    actor: str
    module: str
    entity_id: str
    payload: Dict[str, Any]
    severity: str = "info"
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    environment: str = "dev"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


# ──────────────────────────────────────────────────────────────────────
# Event Bus
# ──────────────────────────────────────────────────────────────────────

class EventBus:
    """Singleton-style event bus with append-only JSONL persistence.

    Thread-safe via internal lock. Subscribers are in-process and run
    synchronously after persistence — keep them fast.
    """

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self) -> None:
        self._subs: List[tuple] = []  # (type_pattern, handler)
        self._write_lock = threading.Lock()
        self._buf: List[Event] = []  # in-memory buffer for query()
        self._buf_cap = 1000

    # ── Persistence path resolution ──────────────────────────────
    def _events_path(self) -> Path:
        """Return mode-appropriate events.jsonl path."""
        try:
            from utils.environment import environment_paths
            data_root = environment_paths()["data_root"]
        except ImportError:
            data_root = REPO / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        return data_root / EVENTS_FILENAME

    # ── Emit ─────────────────────────────────────────────────────
    def emit(self, *, event_type: str, actor: str,
             entity_id: str = "", module: str = "",
             payload: Optional[Dict[str, Any]] = None,
             severity: str = "info",
             correlation_id: Optional[str] = None,
             parent_event_id: Optional[str] = None) -> str:
        """Emit an event. Returns the event id."""
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type required")
        if severity not in SEVERITY_VALUES:
            severity = "info"

        # Use sim clock when active (Phase O4-A); falls through to
        # wall-clock UTC when not. Backward-compatible.
        try:
            from utils.simulation_clock import sim_now
            timestamp = sim_now().isoformat()
        except Exception:
            timestamp = datetime.now(timezone.utc).isoformat()
        seed = f"{actor}|{event_type}|{entity_id}|{timestamp}"
        event_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

        # Resolve environment for stamping
        try:
            from utils.environment import get_environment
            env_value = get_environment().value
        except ImportError:
            env_value = "dev"

        ev = Event(
            id=event_id, timestamp=timestamp,
            event_type=event_type, actor=actor or "system",
            module=module, entity_id=str(entity_id),
            payload=payload or {}, severity=severity,
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
            environment=env_value,
        )

        # 1. Persist (atomic-ish append)
        with self._write_lock:
            try:
                with open(self._events_path(), "a", encoding="utf-8") as f:
                    f.write(ev.to_jsonl() + "\n")
            except Exception:
                pass  # never fail caller on telemetry write
            # Buffer (capped)
            self._buf.append(ev)
            if len(self._buf) > self._buf_cap:
                self._buf = self._buf[-self._buf_cap:]

        # 2. Fan out to subscribers (best-effort)
        for pattern, handler in list(self._subs):
            try:
                if self._matches(pattern, event_type):
                    handler(ev)
            except Exception:
                pass

        return event_id

    # ── Subscribe ────────────────────────────────────────────────
    def subscribe(self, type_pattern: str,
                  handler: Callable[[Event], None]) -> None:
        """Register a handler for events matching type_pattern.

        Patterns support trailing wildcard: 'workflow.*' matches any
        workflow.X event. Exact strings match exactly. '*' matches all.
        """
        self._subs.append((type_pattern, handler))

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        if pattern == "*" or pattern == event_type:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type == prefix or event_type.startswith(prefix + ".")
        return False

    # ── Query ────────────────────────────────────────────────────
    def query(self, *, event_type: Optional[str] = None,
              entity_id: Optional[str] = None,
              actor: Optional[str] = None,
              correlation_id: Optional[str] = None,
              since: Optional[str] = None, until: Optional[str] = None,
              limit: int = 100,
              from_disk: bool = True) -> List[Event]:
        """Retrieve matching events.

        If from_disk=True (default), reads the events file from disk to
        catch events emitted in other processes. If False, queries the
        in-memory buffer only (faster).
        """
        candidates: List[Event] = []
        if from_disk:
            path = self._events_path()
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line: continue
                            try:
                                d = json.loads(line)
                                candidates.append(Event(**d))
                            except Exception:
                                continue
                except Exception:
                    pass
        else:
            candidates = list(self._buf)

        out: List[Event] = []
        for ev in reversed(candidates):  # newest first
            if event_type:
                if not self._matches(event_type, ev.event_type):
                    continue
            if entity_id and str(ev.entity_id) != str(entity_id):
                continue
            if actor and ev.actor != actor:
                continue
            if correlation_id and ev.correlation_id != correlation_id:
                continue
            if since and ev.timestamp < since:
                continue
            if until and ev.timestamp > until:
                continue
            out.append(ev)
            if len(out) >= limit:
                break
        return out

    # ── Utility ──────────────────────────────────────────────────
    def count_total(self) -> int:
        """Count total events on disk (cheap line-count)."""
        path = self._events_path()
        if not path.exists():
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0


def get_event_bus() -> EventBus:
    """Return the singleton EventBus."""
    return EventBus()


# Convenience top-level emit
def emit(**kwargs) -> str:
    return get_event_bus().emit(**kwargs)


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_emit_returns_id():
    bus = EventBus()
    eid = bus.emit(event_type="system.event_bus.started",
                   actor="test", module="system",
                   payload={"hello": "world"})
    assert eid and isinstance(eid, str) and len(eid) == 20


def _test_query_finds_emitted():
    bus = EventBus()
    correlation = "test-corr-v10475-1"
    bus.emit(event_type="workflow.transition", actor="test_actor_x",
             entity_id="LN_TEST_001", module="credit",
             correlation_id=correlation,
             payload={"from": "draft", "to": "submitted"})
    results = bus.query(correlation_id=correlation, limit=10)
    assert any(e.entity_id == "LN_TEST_001" for e in results), (
        f"emitted event not found in query results: {[e.entity_id for e in results]}"
    )


def _test_subscribe_pattern_matches():
    bus = EventBus()
    received: List[Event] = []
    bus.subscribe("workflow.*", lambda e: received.append(e))
    bus.emit(event_type="workflow.rollback", actor="test_sub",
             entity_id="LN_TEST_002", module="credit", payload={})
    assert any(e.entity_id == "LN_TEST_002" for e in received)


def _test_subscribe_wildcard_matches_all():
    bus = EventBus()
    received: List[Event] = []
    bus.subscribe("*", lambda e: received.append(e))
    bus.emit(event_type="approval.granted", actor="test_wild",
             entity_id="APP_TEST_001", module="credit", payload={})
    assert any(e.entity_id == "APP_TEST_001" for e in received)


def _test_parent_event_id_chain():
    bus = EventBus()
    parent_id = bus.emit(event_type="approval.requested",
                          actor="test_parent",
                          entity_id="APP_CHAIN_001", module="credit")
    child_id = bus.emit(event_type="approval.granted",
                         actor="test_parent",
                         entity_id="APP_CHAIN_001", module="credit",
                         parent_event_id=parent_id)
    children = bus.query(entity_id="APP_CHAIN_001", limit=10)
    assert any(e.parent_event_id == parent_id for e in children)


def _test_environment_stamped_on_event():
    bus = EventBus()
    eid = bus.emit(event_type="system.event_bus.started",
                   actor="test_env", payload={})
    found = bus.query(actor="test_env", limit=5)
    assert found and found[0].environment in {"dev","sim","uat","staging","prod"}


def _test_invalid_event_type_raises():
    bus = EventBus()
    try:
        bus.emit(event_type="", actor="x")
        raise AssertionError("empty event_type should raise")
    except ValueError:
        pass


def self_test() -> None:
    """Run all event_bus self-tests."""
    _test_emit_returns_id()
    _test_query_finds_emitted()
    _test_subscribe_pattern_matches()
    _test_subscribe_wildcard_matches_all()
    _test_parent_event_id_chain()
    _test_environment_stamped_on_event()
    _test_invalid_event_type_raises()


__all__ = [
    "Event", "EventBus", "get_event_bus", "emit",
    "EVENT_TYPES_KNOWN", "SEVERITY_VALUES", "EVENTS_FILENAME",
]


if __name__ == "__main__":
    import sys as _sys
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("event_bus self-test passed")

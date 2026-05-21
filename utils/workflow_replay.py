"""utils/workflow_replay.py — Workflow case replay engine.

Per Joshua Master Prompt Phase O2:
    'Workflow replay' must be observable.

Given a workflow item_id (loan application, FX deal, discipline case),
this module reconstructs the full timeline of state transitions —
when each happened, who triggered it, the reason given, and what
preceded each step.

This is the engine that powers operational walkthroughs ("how did
this loan get to APPROVED?") and post-incident reviews.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowStep:
    """One transition in a workflow's life."""
    timestamp: str
    event_id: str
    from_state: Optional[str]
    to_state: Optional[str]
    actor: str
    note: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowReplay:
    """The full ordered timeline for one workflow item."""
    item_id: str
    module: Optional[str] = None
    steps: List[WorkflowStep] = field(default_factory=list)

    def step_count(self) -> int:
        return len(self.steps)

    def current_state(self) -> Optional[str]:
        if not self.steps:
            return None
        return self.steps[-1].to_state

    def actors(self) -> List[str]:
        return sorted({s.actor for s in self.steps if s.actor})

    def reached(self, state: str) -> bool:
        return any(s.to_state == state for s in self.steps)

    def time_in_state(self, state: str) -> Optional[float]:
        """Total seconds the item spent in `state` (None if never reached)."""
        from datetime import datetime
        if not self.reached(state):
            return None
        total_s = 0.0
        in_state_since: Optional[datetime] = None
        for s in self.steps:
            ts = datetime.fromisoformat(s.timestamp.replace("Z", "+00:00"))
            if s.to_state == state:
                in_state_since = ts
            elif in_state_since is not None and s.from_state == state:
                total_s += (ts - in_state_since).total_seconds()
                in_state_since = None
        return total_s

    def summary(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "module": self.module,
            "step_count": self.step_count(),
            "current_state": self.current_state(),
            "actors": self.actors(),
            "first_at": self.steps[0].timestamp if self.steps else None,
            "last_at": self.steps[-1].timestamp if self.steps else None,
            "state_sequence": [s.to_state for s in self.steps],
        }


def replay_workflow(item_id: str,
                     *, module: Optional[str] = None,
                     limit: int = 500) -> WorkflowReplay:
    """Reconstruct the workflow history for an item_id.

    Pulls workflow.* events from event_bus for this entity. If module
    is provided, filters to that module (useful when item_ids might
    collide across modules).
    """
    from utils.event_bus import get_event_bus
    bus = get_event_bus()

    events = bus.query(entity_id=str(item_id), limit=limit, from_disk=True)
    # Filter to workflow events
    wf_events = [e for e in events if e.event_type.startswith("workflow.")]
    if module:
        wf_events = [e for e in wf_events if e.module == module]
    # Sort ascending (oldest first) for replay
    wf_events.sort(key=lambda e: e.timestamp)

    steps: List[WorkflowStep] = []
    for e in wf_events:
        payload = e.payload or {}
        steps.append(WorkflowStep(
            timestamp=e.timestamp,
            event_id=e.id,
            from_state=payload.get("from") or payload.get("from_state"),
            to_state=payload.get("to") or payload.get("to_state"),
            actor=e.actor,
            note=payload.get("note", ""),
            payload=payload,
        ))

    return WorkflowReplay(
        item_id=str(item_id),
        module=module or (wf_events[0].module if wf_events else None),
        steps=steps,
    )


def render_replay_text(replay: WorkflowReplay) -> str:
    """Render a replay as human-readable text."""
    out = [f"Workflow replay: {replay.item_id}"]
    s = replay.summary()
    out.append(f"  Module: {s['module']}")
    out.append(f"  Steps: {s['step_count']}")
    out.append(f"  Current state: {s['current_state']}")
    out.append(f"  Actors: {', '.join(s['actors'])}")
    out.append("")
    out.append("Timeline:")
    for i, step in enumerate(replay.steps):
        arrow = f"{step.from_state or 'INIT'} -> {step.to_state or '?'}"
        out.append(
            f"  {i+1:>3}. [{step.timestamp[:19]}] {arrow:<40} "
            f"by {step.actor}"
        )
        if step.note:
            out.append(f"      note: {step.note}")
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_replay_returns_steps():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    item = "REPLAY_TEST_001"
    bus.emit(event_type="workflow.created", actor="alice",
             entity_id=item, module="credit",
             payload={"from": None, "to": "draft"})
    bus.emit(event_type="workflow.transition", actor="bob",
             entity_id=item, module="credit",
             payload={"from": "draft", "to": "submitted"})
    bus.emit(event_type="workflow.transition", actor="carol",
             entity_id=item, module="credit",
             payload={"from": "submitted", "to": "approved"})
    r = replay_workflow(item)
    assert r.step_count() == 3
    assert r.current_state() == "approved"
    assert r.reached("submitted")


def _test_replay_state_sequence_ordered():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    item = "REPLAY_TEST_002"
    bus.emit(event_type="workflow.transition", actor="x",
             entity_id=item, module="credit",
             payload={"from": "draft", "to": "submitted"})
    bus.emit(event_type="workflow.transition", actor="y",
             entity_id=item, module="credit",
             payload={"from": "submitted", "to": "under_review"})
    r = replay_workflow(item)
    seq = r.summary()["state_sequence"]
    assert seq == ["submitted", "under_review"], f"got {seq}"


def _test_replay_module_filter():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    item = "REPLAY_TEST_003"
    # Same item_id in two modules
    bus.emit(event_type="workflow.created", actor="x",
             entity_id=item, module="credit",
             payload={"from": None, "to": "draft"})
    bus.emit(event_type="workflow.created", actor="y",
             entity_id=item, module="hr",
             payload={"from": None, "to": "draft"})
    r_credit = replay_workflow(item, module="credit")
    r_hr = replay_workflow(item, module="hr")
    assert r_credit.step_count() == 1 and r_credit.module == "credit"
    assert r_hr.step_count() == 1 and r_hr.module == "hr"


def _test_replay_render_text():
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    item = "REPLAY_TEST_004"
    bus.emit(event_type="workflow.transition", actor="render_test",
             entity_id=item, module="credit",
             payload={"from": "draft", "to": "submitted",
                      "note": "submitted by branch"})
    r = replay_workflow(item)
    text = render_replay_text(r)
    assert item in text and "draft -> submitted" in text


def _test_replay_empty_when_no_events():
    r = replay_workflow("DEFINITELY_NOT_A_REAL_ITEM_v10475")
    assert r.step_count() == 0
    assert r.current_state() is None


def self_test() -> None:
    _test_replay_returns_steps()
    _test_replay_state_sequence_ordered()
    _test_replay_module_filter()
    _test_replay_render_text()
    _test_replay_empty_when_no_events()


__all__ = ["WorkflowStep", "WorkflowReplay", "replay_workflow",
           "render_replay_text"]


if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _P
    REPO = _P(__file__).parent.parent
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("workflow_replay self-test passed")

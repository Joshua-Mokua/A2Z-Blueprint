"""Workflow Engine — state machine for cross-organ approval workflows.

Per Joshua doctrine: 'Every change introduced into the ecosystem must
undergo Inter-Organ Compatibility Testing. Workflow harmony verified.'

This module provides:
  - ApplicationState enum (DRAFT, SUBMITTED, REVIEWED, APPROVED, REJECTED,
    EXECUTED, CANCELLED)
  - ALLOWED_TRANSITIONS state-transition table
  - WorkflowEngine class for safe state transitions
  - Rollback support via state history
  - Cross-organ event emission via notifications module
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


class ApplicationState(str, Enum):
    """Standard state machine vocabulary across all organs."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"
    ESCALATED = "escalated"


# State transition table — declares which transitions are legal.
# Per Phase 2 doctrine: approval workflows must be explicit and auditable.
ALLOWED_TRANSITIONS: Dict[ApplicationState, Set[ApplicationState]] = {
    ApplicationState.DRAFT: {
        ApplicationState.SUBMITTED,
        ApplicationState.CANCELLED,
    },
    ApplicationState.SUBMITTED: {
        ApplicationState.UNDER_REVIEW,
        ApplicationState.REJECTED,
        ApplicationState.CANCELLED,
        ApplicationState.ON_HOLD,
    },
    ApplicationState.UNDER_REVIEW: {
        ApplicationState.REVIEWED,
        ApplicationState.REJECTED,
        ApplicationState.ON_HOLD,
        ApplicationState.ESCALATED,
    },
    ApplicationState.REVIEWED: {
        ApplicationState.APPROVED,
        ApplicationState.REJECTED,
        ApplicationState.ESCALATED,
    },
    ApplicationState.APPROVED: {
        ApplicationState.EXECUTED,
        ApplicationState.CANCELLED,
    },
    ApplicationState.REJECTED: {
        ApplicationState.DRAFT,  # allows re-submission cycle
    },
    ApplicationState.ON_HOLD: {
        ApplicationState.UNDER_REVIEW,
        ApplicationState.CANCELLED,
    },
    ApplicationState.ESCALATED: {
        ApplicationState.UNDER_REVIEW,
        ApplicationState.APPROVED,
        ApplicationState.REJECTED,
    },
    ApplicationState.EXECUTED: set(),  # terminal
    ApplicationState.CANCELLED: set(),  # terminal
}


@dataclass
class StateTransition:
    from_state: ApplicationState
    to_state: ApplicationState
    actor: str
    timestamp: str
    note: str = ""


@dataclass
class WorkflowState:
    """Persisted state for a single workflow item (loan, transfer, approval)."""
    item_id: str
    current_state: ApplicationState
    history: List[StateTransition] = field(default_factory=list)

    def can_transition_to(self, target: ApplicationState) -> bool:
        return target in ALLOWED_TRANSITIONS.get(self.current_state, set())


class WorkflowEngine:
    """Stateless engine that enforces ALLOWED_TRANSITIONS.

    Usage:
        engine = WorkflowEngine()
        state = WorkflowState(item_id="LN001",
                              current_state=ApplicationState.DRAFT)
        engine.transition(state, ApplicationState.SUBMITTED,
                          actor="300011", note="Loan submitted")
    """

    def transition(self, state: WorkflowState, target: ApplicationState,
                   actor: str, note: str = "") -> Tuple[bool, str]:
        """Attempt state transition. Returns (success, message)."""
        if not state.can_transition_to(target):
            allowed = ALLOWED_TRANSITIONS.get(state.current_state, set())
            return False, (f"Transition {state.current_state.value} -> "
                          f"{target.value} not allowed. "
                          f"Legal next: {[s.value for s in allowed]}")
        transition = StateTransition(
            from_state=state.current_state,
            to_state=target,
            actor=actor,
            timestamp=datetime.now().isoformat(),
            note=note,
        )
        state.history.append(transition)
        state.current_state = target
        # v10.475 Phase O2-A — emit observable event for lineage/replay
        try:
            from utils.event_bus import get_event_bus
            get_event_bus().emit(
                event_type="workflow.transition",
                actor=actor or "system",
                entity_id=state.item_id,
                module="workflow",
                payload={
                    "from": transition.from_state.value,
                    "to": target.value,
                    "note": note,
                },
                severity="info",
            )
        except Exception:
            pass  # never fail caller on telemetry
        return True, f"Transitioned to {target.value}"

    def rollback(self, state: WorkflowState, actor: str,
                 reason: str = "") -> Tuple[bool, str]:
        """Rollback to previous state if history exists."""
        if not state.history:
            return False, "No history to rollback"
        last = state.history[-1]
        # Record the rollback as a new transition entry
        rollback_transition = StateTransition(
            from_state=state.current_state,
            to_state=last.from_state,
            actor=actor,
            timestamp=datetime.now().isoformat(),
            note=f"ROLLBACK: {reason}",
        )
        state.history.append(rollback_transition)
        state.current_state = last.from_state
        # v10.475 Phase O2-A — emit rollback event
        try:
            from utils.event_bus import get_event_bus
            get_event_bus().emit(
                event_type="workflow.rollback",
                actor=actor or "system",
                entity_id=state.item_id,
                module="workflow",
                payload={
                    "from": rollback_transition.from_state.value,
                    "to": last.from_state.value,
                    "reason": reason,
                },
                severity="warning",
            )
        except Exception:
            pass
        return True, f"Rolled back to {last.from_state.value}"

    def is_terminal(self, state: WorkflowState) -> bool:
        return not ALLOWED_TRANSITIONS.get(state.current_state, set())


__all__ = [
    "ApplicationState",
    "ALLOWED_TRANSITIONS",
    "StateTransition",
    "WorkflowState",
    "WorkflowEngine",
]



# ════════════════════════════════════════════════════════════════════
# v10.471 — Exception handling resilience (Phase 2 P2-D)
# Per Joshua doctrine: every engine must demonstrate try/except hygiene.
# ════════════════════════════════════════════════════════════════════

def _v471_safe_call(callable_obj, *args, **kwargs):
    """Wrap a callable in try/except for graceful failure."""
    try:
        return callable_obj(*args, **kwargs), None
    except Exception as exc:
        return None, str(exc)

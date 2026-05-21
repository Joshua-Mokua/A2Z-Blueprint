"""utils/agents/base.py — agent framework base types.

Frozen dataclasses defining the agent's mental model:
  AgentTool         — a callable with typed name + description + handler
  AgentToolResult   — what a tool returns (output, latency, error)
  AgentObservation  — what the agent sees after a step (tool result + ctx)
  AgentStep         — one (tool_name, args, result) triple
  AgentTrajectory   — the full sequence of steps
  AgentBudget       — execution limits (max_steps, max_seconds)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# Tool handlers return either a dict (success) or raise an exception
ToolHandler = Callable[..., Dict[str, Any]]


@dataclass(frozen=True)
class AgentTool:
    """A typed tool the agent can call.

    name             - unique identifier within the registry
    description      - human-readable hint for the policy
    handler          - callable: handler(**kwargs) -> dict
    schema           - kwarg name -> type hint string (e.g. "str")
    category         - grouping label: channel / chaos / macro / ml / info
    requires         - list of other tool names this depends on (advisory)
    """
    name: str
    description: str
    handler: ToolHandler
    schema: Dict[str, str] = field(default_factory=dict)
    category: str = "general"
    requires: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            raise ValueError("AgentTool.name required")
        if not callable(self.handler):
            raise ValueError(
                f"AgentTool {self.name}: handler must be callable"
            )


@dataclass(frozen=True)
class AgentToolResult:
    """Result of a single tool invocation."""
    tool_name: str
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "output": dict(self.output),
            "error": self.error,
            "latency_ms": round(self.latency_ms, 3),
        }


@dataclass(frozen=True)
class AgentObservation:
    """What the agent sees after each step.

    Captures the tool result plus a snapshot of context (sim time,
    macro state, active chaos) so policies can react to environment.
    """
    step_index: int
    last_result: Optional[AgentToolResult]
    sim_time: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    history_summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStep:
    """One (decision, action, result) triple."""
    index: int
    tool_name: str
    args: Dict[str, Any]
    result: AgentToolResult
    rationale: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "tool_name": self.tool_name,
            "args": dict(self.args),
            "result": self.result.to_dict(),
            "rationale": self.rationale,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentTrajectory:
    """Sequence of steps from one agent run."""
    agent_name: str
    goal: str
    steps: List[AgentStep] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    terminated_reason: str = ""

    def add_step(self, step: AgentStep) -> None:
        self.steps.append(step)

    def step_count(self) -> int:
        return len(self.steps)

    def successful_steps(self) -> int:
        return sum(1 for s in self.steps if s.result.success)

    def tool_call_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for s in self.steps:
            summary[s.tool_name] = summary.get(s.tool_name, 0) + 1
        return summary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "goal": self.goal,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "terminated_reason": self.terminated_reason,
            "step_count": self.step_count(),
            "successful_steps": self.successful_steps(),
            "tool_call_summary": self.tool_call_summary(),
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class AgentBudget:
    """Execution limits for an agent run."""
    max_steps: int = 10
    max_seconds: float = 30.0
    started_wall: float = field(default_factory=time.time)

    def step_remaining(self, current_step: int) -> int:
        return max(0, self.max_steps - current_step)

    def time_remaining(self) -> float:
        elapsed = time.time() - self.started_wall
        return max(0.0, self.max_seconds - elapsed)

    def exhausted(self, current_step: int) -> Optional[str]:
        if current_step >= self.max_steps:
            return f"max_steps reached ({self.max_steps})"
        if self.time_remaining() <= 0:
            return f"max_seconds reached ({self.max_seconds})"
        return None


__all__ = [
    "AgentTool", "AgentToolResult", "AgentObservation",
    "AgentStep", "AgentTrajectory", "AgentBudget",
    "ToolHandler",
]

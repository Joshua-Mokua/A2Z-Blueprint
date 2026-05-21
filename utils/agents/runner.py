"""utils/agents/runner.py — the agent run loop.

AgentRunner executes one agent against a goal under a budget. The loop:

  1. Build observation from sim clock + macro + chaos + last result
  2. Ask the policy: choose next (tool_name, args, rationale)
  3. If None -> terminate (policy-decided)
  4. Otherwise invoke the tool via the registry
  5. Record the step in the trajectory
  6. Emit agent.step event to the event bus
  7. Check budget; if exhausted, terminate

Each step is bounded in latency, and budget enforces overall max_steps
and max_seconds so an infinite-loop policy still terminates safely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.agents.base import (
    AgentBudget, AgentObservation, AgentStep, AgentTool,
    AgentToolResult, AgentTrajectory,
)
from utils.agents.policies import AgentPolicy
from utils.agents.tools import ToolRegistry, get_default_tool_registry


@dataclass
class AgentResult:
    """Outcome of one agent run."""
    agent_name: str
    goal: str
    trajectory: AgentTrajectory
    success: bool
    terminated_reason: str = ""

    def step_count(self) -> int:
        return self.trajectory.step_count()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "goal": self.goal,
            "success": self.success,
            "terminated_reason": self.terminated_reason,
            "trajectory": self.trajectory.to_dict(),
        }


class AgentRunner:
    """Execute one agent run end-to-end."""

    def __init__(self, *,
                  registry: Optional[ToolRegistry] = None,
                  emit_events: bool = True):
        self.registry = registry or get_default_tool_registry()
        self.emit_events = emit_events

    def run(self, *, policy: AgentPolicy, goal: str,
              agent_name: str = "agent",
              budget: Optional[AgentBudget] = None) -> AgentResult:
        budget = budget or AgentBudget()
        try:
            from utils.simulation_clock import sim_now
            start_iso = sim_now().isoformat()
        except Exception:
            start_iso = datetime.utcnow().isoformat()

        trajectory = AgentTrajectory(
            agent_name=agent_name, goal=goal,
            started_at=start_iso,
        )
        terminated_reason = ""
        last_result: Optional[AgentToolResult] = None

        step_idx = 0
        while True:
            # 1. Budget check
            reason = budget.exhausted(step_idx)
            if reason:
                terminated_reason = reason
                break

            # 2. Observation
            observation = self._make_observation(
                step_idx, last_result, trajectory,
            )

            # 3. Policy choice
            tool_name, args, rationale = policy.choose(
                observation, self.registry.list_names(), goal,
            )
            if tool_name is None:
                terminated_reason = (rationale or
                                       "policy returned None (done)")
                break

            # 4. Invoke
            result = self.registry.call(tool_name, **(args or {}))
            try:
                from utils.simulation_clock import sim_now
                ts = sim_now().isoformat()
            except Exception:
                ts = datetime.utcnow().isoformat()

            step = AgentStep(
                index=step_idx, tool_name=tool_name,
                args=dict(args or {}), result=result,
                rationale=rationale, timestamp=ts,
            )
            trajectory.add_step(step)
            last_result = result

            if self.emit_events:
                self._emit_step(agent_name, goal, step)

            step_idx += 1

        try:
            from utils.simulation_clock import sim_now
            trajectory.ended_at = sim_now().isoformat()
        except Exception:
            trajectory.ended_at = datetime.utcnow().isoformat()
        trajectory.terminated_reason = terminated_reason

        # Run is "successful" if at least one step succeeded
        # (a clean policy-decided termination with no errors)
        any_step_succeeded = any(s.result.success
                                    for s in trajectory.steps)
        explicit_success = (
            "complete" in (terminated_reason or "").lower()
            or "done" in (terminated_reason or "").lower()
        )
        success = any_step_succeeded or explicit_success

        result = AgentResult(
            agent_name=agent_name, goal=goal,
            trajectory=trajectory,
            success=success,
            terminated_reason=terminated_reason,
        )

        if self.emit_events:
            self._emit_run_complete(result)
        return result

    # ── internals ────────────────────────────────────────────────

    def _make_observation(self, step_idx: int,
                             last_result: Optional[AgentToolResult],
                             trajectory: AgentTrajectory
                             ) -> AgentObservation:
        ctx: Dict[str, Any] = {}
        sim_time = ""
        try:
            from utils.simulation_clock import sim_now
            sim_time = sim_now().isoformat()
        except Exception:
            pass
        try:
            from utils.macro_state import get_macro_state
            ms = get_macro_state()
            ctx["cbr"] = ms.cbk_central_bank_rate
            ctx["usd_kes"] = ms.usd_kes
            ctx["npl_ratio"] = ms.npl_ratio
        except Exception:
            pass
        try:
            from utils.chaos import get_chaos_injector
            ctx["active_chaos_count"] = len(
                get_chaos_injector().active_events())
        except Exception:
            pass

        history_summary = {
            "step_count": trajectory.step_count(),
            "successful_steps": trajectory.successful_steps(),
            "tool_calls": trajectory.tool_call_summary(),
        }

        return AgentObservation(
            step_index=step_idx,
            last_result=last_result,
            sim_time=sim_time,
            context=ctx,
            history_summary=history_summary,
        )

    def _emit_step(self, agent_name: str, goal: str,
                     step: AgentStep) -> None:
        try:
            from utils.event_bus import get_event_bus
            bus = get_event_bus()
            bus.emit(
                event_type="agent.step",
                actor=agent_name, entity_id=str(step.index),
                module="agent",
                payload={
                    "agent_name": agent_name, "goal": goal,
                    "step_index": step.index,
                    "tool_name": step.tool_name,
                    "args_keys": sorted(step.args.keys()),
                    "success": step.result.success,
                    "error": step.result.error,
                    "rationale": step.rationale,
                    "latency_ms": step.result.latency_ms,
                },
            )
        except Exception:
            pass

    def _emit_run_complete(self, result: AgentResult) -> None:
        try:
            from utils.event_bus import get_event_bus
            bus = get_event_bus()
            bus.emit(
                event_type="agent.run_complete",
                actor=result.agent_name, entity_id=result.agent_name,
                module="agent",
                payload={
                    "agent_name": result.agent_name,
                    "goal": result.goal,
                    "success": result.success,
                    "terminated_reason": result.terminated_reason,
                    "step_count": result.step_count(),
                    "successful_steps":
                        result.trajectory.successful_steps(),
                    "tool_call_summary":
                        result.trajectory.tool_call_summary(),
                },
            )
        except Exception:
            pass


__all__ = ["AgentRunner", "AgentResult"]

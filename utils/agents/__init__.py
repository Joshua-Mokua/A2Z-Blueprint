"""utils.agents — Phase O6-B LLM agent infrastructure.

Tool-calling agent framework over the digital twin. Agents:
  - hold a deterministic step budget (max_steps)
  - receive a typed tool registry (channels, scenarios, chaos, macro,
    ML models, retrievers)
  - run a deliberation loop: observe -> select tool -> call -> reflect
  - emit agent.step events to the event bus
  - persist trajectories for replay and evaluation

The framework is LLM-agnostic - you can plug in a real LLM, a scripted
policy, or a learned policy. v10.484 ships with:
  - DeterministicPolicy (heuristic-based, useful for tests)
  - RandomPolicy (controlled randomness for exploration)
  - ScriptedPolicy (replay a fixed tool sequence for golden tests)

Future batches can add LLM-backed policies that call out to Claude or
local models, but the agent loop machinery is identical regardless of
where the tool choices come from.
"""

from utils.agents.base import (
    AgentTool, AgentToolResult, AgentObservation,
    AgentStep, AgentTrajectory, AgentBudget,
)
from utils.agents.tools import (
    ToolRegistry, get_default_tool_registry,
    reset_default_tool_registry,
)
from utils.agents.policies import (
    AgentPolicy, DeterministicPolicy, RandomPolicy, ScriptedPolicy,
)
from utils.agents.runner import (
    AgentRunner, AgentResult,
)

__all__ = [
    "AgentTool", "AgentToolResult", "AgentObservation",
    "AgentStep", "AgentTrajectory", "AgentBudget",
    "ToolRegistry", "get_default_tool_registry",
    "reset_default_tool_registry",
    "AgentPolicy", "DeterministicPolicy", "RandomPolicy", "ScriptedPolicy",
    "AgentRunner", "AgentResult",
]

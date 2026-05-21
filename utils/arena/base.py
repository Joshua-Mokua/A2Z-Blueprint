"""utils/arena/base.py — drill base types.

A Drill is a self-contained, reproducible exercise:

  Drill(
      name="survive_safaricom_outage_eom",
      description="...",
      category="channel_survival",
      sim_start=datetime(2026, 5, 31, 14, 0, tzinfo=NAIROBI_TZ),
      environment=[
          DrillEnvironmentEvent(
              offset=timedelta(0),
              kind="chaos:activate",
              ref="safaricom_mpesa_outage_30min",
          ),
          DrillEnvironmentEvent(
              offset=timedelta(minutes=20),
              kind="chaos:activate",
              ref="atm_dispenser_jams_eom",
          ),
      ],
      agent_goal="inspect_channels",
      oracle=DrillOracle(
          min_steps=3,
          required_tool_calls=["channel:list"],
          must_observe_chaos=True,
      ),
  )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class DrillEnvironmentEvent:
    """A pre-scripted environment event for a drill.

    Fires at ``sim_start + offset`` in the drill's TickScheduler.

      kind   : "chaos:activate" | "macro:apply_shock" | "scenario:run"
      ref    : template name (chaos template / shock name / scenario name)
      kwargs : extra kwargs passed to the action (e.g. {"pct": 0.05} for fx)
    """
    offset: timedelta
    kind: str
    ref: str
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DrillOracle:
    """Pass/fail criterion over the drill's resulting trajectory.

    Multiple fields combine: ALL conditions must hold for pass.
    Any unset field is ignored.

      min_steps             : trajectory must have at least N steps
      min_successful_steps  : at least N steps must have success=True
      required_tool_calls   : every named tool must appear at least once
      forbidden_tool_calls  : no listed tool may appear
      must_observe_chaos    : an agent step must occur while chaos active
                              for the agent's primary channel (or any channel
                              if no primary)
      max_failure_rate      : failed_steps / total_steps must be <= this
    """
    min_steps: Optional[int] = None
    min_successful_steps: Optional[int] = None
    required_tool_calls: List[str] = field(default_factory=list)
    forbidden_tool_calls: List[str] = field(default_factory=list)
    must_observe_chaos: bool = False
    max_failure_rate: Optional[float] = None
    custom_check: Optional[Callable] = None   # (drill, result) -> (bool, msg)


@dataclass
class Drill:
    """A named, reproducible exercise."""
    name: str
    description: str
    category: str
    sim_start: datetime
    environment: List[DrillEnvironmentEvent] = field(default_factory=list)
    agent_goal: str = "default"
    oracle: DrillOracle = field(default_factory=DrillOracle)
    tags: List[str] = field(default_factory=list)
    seed: int = 0

    def __post_init__(self):
        if self.sim_start.tzinfo is None:
            raise ValueError(
                f"Drill {self.name}: sim_start must be tz-aware"
            )
        if not self.name:
            raise ValueError("Drill.name required")

    def event_count(self) -> int:
        return len(self.environment)


@dataclass
class DrillResult:
    """Outcome of one drill run."""
    drill_name: str
    passed: bool
    agent_steps: int
    successful_agent_steps: int
    failure_reasons: List[str] = field(default_factory=list)
    environment_fired: List[str] = field(default_factory=list)
    trajectory: Optional[Any] = None    # AgentTrajectory if available

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "drill_name": self.drill_name,
            "passed": self.passed,
            "agent_steps": self.agent_steps,
            "successful_agent_steps": self.successful_agent_steps,
            "failure_reasons": list(self.failure_reasons),
            "environment_fired": list(self.environment_fired),
        }
        if self.trajectory is not None and hasattr(self.trajectory,
                                                       "to_dict"):
            d["trajectory"] = self.trajectory.to_dict()
        return d


__all__ = [
    "Drill", "DrillEnvironmentEvent", "DrillOracle", "DrillResult",
]

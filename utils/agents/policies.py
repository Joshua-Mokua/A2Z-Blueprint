"""utils/agents/policies.py — agent decision policies.

A policy chooses the next tool to call given the agent's observation
of the world. Three reference implementations:

  - DeterministicPolicy : heuristic rules over goal + observation,
                          useful for tests and as a baseline
  - RandomPolicy        : controlled randomness for exploration
  - ScriptedPolicy      : replay a fixed tool sequence (golden tests)

LLM-backed policies can be added later by subclassing AgentPolicy —
the agent loop and tool wiring stay identical.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.agents.base import AgentObservation


class AgentPolicy:
    """Base class: choose next (tool_name, args, rationale)."""

    name: str = "base"

    def choose(self, observation: AgentObservation,
                 available_tools: List[str],
                 goal: str) -> Tuple[Optional[str], Dict[str, Any], str]:
        """Return (tool_name, args, rationale).

        Returning (None, {}, reason) signals 'terminate now'.
        """
        raise NotImplementedError


class DeterministicPolicy(AgentPolicy):
    """Heuristic policy chosen by goal keywords.

    Recognised goals (case-insensitive substring match):
      - 'inspect_channels'   : list channels, then query events
      - 'survey_macro'       : snapshot macro, query macro.update events
      - 'survey_chaos'       : list chaos templates, check active
      - 'run_scenario'       : list scenarios, then run the first one
      - 'train_model'        : train classifier predicting success
      - default              : list channels then snapshot macro

    Each step transitions through a small state machine. After the
    plan is complete the policy returns None to terminate.
    """

    name = "deterministic"

    def __init__(self):
        self._state: int = 0

    def choose(self, observation: AgentObservation,
                 available_tools: List[str],
                 goal: str) -> Tuple[Optional[str], Dict[str, Any], str]:
        goal_l = (goal or "").lower()
        idx = self._state
        self._state += 1

        if "inspect_channels" in goal_l:
            return self._inspect_channels_step(idx, observation,
                                                  available_tools)
        if "survey_macro" in goal_l:
            return self._survey_macro_step(idx)
        if "survey_chaos" in goal_l:
            return self._survey_chaos_step(idx)
        if "run_scenario" in goal_l:
            return self._run_scenario_step(idx, observation)
        if "train_model" in goal_l:
            return self._train_model_step(idx, observation)
        # Default plan
        return self._default_step(idx)

    # ── concrete plans ──────────────────────────────────────────

    def _inspect_channels_step(self, idx, obs, tools):
        plans = [
            ("channel:list", {}, "list channels to know what's available"),
            ("events:query",
              {"event_type": "integration.mpesa.call", "limit": 5},
              "check recent mpesa traffic"),
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678", "amount": 1500,
                            "paybill": "174379"},
                "amount": 1500, "reference": "agent_probe",
                "actor": "agent", "seed": 7},
              "submit a probe transaction"),
        ]
        if idx < len(plans):
            return plans[idx]
        return (None, {}, "inspection plan complete")

    def _survey_macro_step(self, idx):
        plans = [
            ("macro:snapshot", {},
              "get current macro state"),
            ("events:query",
              {"event_type": "macro.update", "limit": 5},
              "look at recent macro updates"),
        ]
        if idx < len(plans):
            return plans[idx]
        return (None, {}, "macro survey complete")

    def _survey_chaos_step(self, idx):
        plans = [
            ("chaos:list", {}, "see what chaos templates exist"),
            ("chaos:active", {}, "any chaos currently active"),
        ]
        if idx < len(plans):
            return plans[idx]
        return (None, {}, "chaos survey complete")

    def _run_scenario_step(self, idx, obs):
        if idx == 0:
            return ("scenario:list", {},
                    "list scenarios to pick one")
        if idx == 1:
            # Try to use first scenario from previous result
            if obs.last_result and obs.last_result.success:
                names = obs.last_result.output.get("scenarios", [])
                if names:
                    return ("scenario:run", {"name": names[0]},
                              f"run scenario {names[0]}")
            return (None, {}, "no scenarios to run")
        return (None, {}, "scenario plan complete")

    def _train_model_step(self, idx, obs):
        plans = [
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678", "amount": 1500,
                            "paybill": "174379"},
                "amount": 1500, "reference": "train_seed_1",
                "actor": "agent", "seed": 1},
              "generate training data"),
            ("channel:submit",
              {"channel": "mpesa",
                "payload": {"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678", "amount": 1500,
                            "paybill": "174379"},
                "amount": 1500, "reference": "train_seed_2",
                "actor": "agent", "seed": 2},
              "generate more training data"),
            ("ml:train_classifier",
              {"name": "agent_trained_v1",
                "target_label": "success",
                "seed": 42,
                "notes": "trained by DeterministicPolicy"},
              "fit a success classifier on accumulated traffic"),
        ]
        if idx < len(plans):
            return plans[idx]
        return (None, {}, "training plan complete")

    def _default_step(self, idx):
        plans = [
            ("channel:list", {}, "default: list channels"),
            ("macro:snapshot", {}, "default: snapshot macro"),
        ]
        if idx < len(plans):
            return plans[idx]
        return (None, {}, "default plan complete")


class RandomPolicy(AgentPolicy):
    """Pick a random tool with safe default args. Seed-deterministic."""

    name = "random"

    def __init__(self, *, seed: int = 0,
                  exclude: Optional[Sequence[str]] = None):
        self.rng = random.Random(seed)
        self._exclude = set(exclude or [
            "channel:submit",         # needs args
            "scenario:run",           # destructive
            "chaos:activate",         # destructive
            "macro:apply_shock",      # destructive
            "ml:train_classifier",    # heavyweight
            "ml:predict",             # needs model
            "time:advance",           # destructive
        ])

    def choose(self, observation: AgentObservation,
                 available_tools: List[str],
                 goal: str) -> Tuple[Optional[str], Dict[str, Any], str]:
        candidates = [t for t in available_tools
                       if t not in self._exclude]
        if not candidates:
            return (None, {}, "no safe tools to choose")
        choice = self.rng.choice(candidates)
        return (choice, {}, f"random pick from {len(candidates)} tools")


class ScriptedPolicy(AgentPolicy):
    """Replay a fixed sequence of (tool_name, args) pairs."""

    name = "scripted"

    def __init__(self, script: Sequence[Tuple[str, Dict[str, Any]]]):
        self._script: List[Tuple[str, Dict[str, Any]]] = list(script)
        self._idx = 0

    def choose(self, observation: AgentObservation,
                 available_tools: List[str],
                 goal: str) -> Tuple[Optional[str], Dict[str, Any], str]:
        if self._idx >= len(self._script):
            return (None, {}, "script exhausted")
        tool, args = self._script[self._idx]
        self._idx += 1
        return (tool, args, f"script step {self._idx}/{len(self._script)}")


__all__ = [
    "AgentPolicy", "DeterministicPolicy", "RandomPolicy", "ScriptedPolicy",
]

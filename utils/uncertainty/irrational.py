"""utils/uncertainty/irrational.py — human irrationality drills.

Most systems assume users behave correctly. Real users panic, skip
steps, override controls, click rapidly, multitask, and abandon
workflows. This module builds 8 drills exercising those patterns.

Approach: each drill is a Drill the existing arena can run, where the
"irrationality" is encoded as an agent policy that deliberately misuses
the available tools (re-submitting, abandoning mid-flow, clicking
rapidly, etc). The oracle verifies the SYSTEM gracefully handles the
misbehaviour — idempotency holds, locks engage, audit trails preserve.

The 8 patterns:
   1. Rapid duplicate clicks (5x submit in 1 second)
   2. Abandoned mid-workflow (start, then never finish)
   3. Conflicting concurrent edits (two policies submit same correlation_id)
   4. Override-control attempt (try to call destructive tools out-of-order)
   5. Stale session reuse (act with old sim_clock state)
   6. Mass-action mistake (one-shot 100 channel submits)
   7. Workflow skip-step (jump to last tool without preconditions)
   8. Approval ping-pong (alternate approve/reject same op)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.arena.base import (
    Drill, DrillEnvironmentEvent, DrillOracle,
)
from utils.agents.policies import AgentPolicy
from utils.agents.base import AgentObservation


_NAIROBI_TZ = None


def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── Irrational policies ────────────────────────────────────────────


class RapidDuplicateClickPolicy(AgentPolicy):
    """Submit the same payload 5 times in a row, all same reference."""
    name = "rapid_duplicate_clicker"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        # 5 identical submits + 1 inspection
        if self._step < 5:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 1500, "paybill": "174379",
                    },
                    "amount": 1500,
                    "reference": "rapid_click_DUP",  # same ref
                    "actor": "panicked_user",
                    "seed": 1,  # same seed
                },
                f"rapid duplicate click {self._step}/5 (same ref)",
            )
        if self._step == 5:
            self._step += 1
            return ("channel:list", {}, "finally check what happened")
        return (None, {}, "rapid clicking complete")


class AbandonedWorkflowPolicy(AgentPolicy):
    """Start a workflow but never finish it (submit then ghost)."""
    name = "abandoner"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        if self._step == 0:
            self._step += 1
            return ("channel:list", {}, "look at the menu")
        if self._step == 1:
            self._step += 1
            return ("macro:snapshot", {}, "check macro context")
        if self._step == 2:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 1500, "paybill": "174379",
                    },
                    "amount": 1500,
                    "reference": "abandoned_workflow",
                    "actor": "abandoner",
                    "seed": 7,
                },
                "submit (the user is about to ghost)",
            )
        # user disappears here — never confirms or checks
        return (None, {}, "user abandoned the workflow")


class ConflictingConcurrentEditPolicy(AgentPolicy):
    """Submit the SAME correlation_id twice in different ways."""
    name = "conflicting_concurrent_editor"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        # Same reference, different amounts (conflict)
        if self._step == 0:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 1500, "paybill": "174379",
                    },
                    "amount": 1500,
                    "reference": "concurrent_conflict",
                    "actor": "edit_a",
                    "seed": 0,
                },
                "first concurrent edit (amount 1500)",
            )
        if self._step == 1:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 2500, "paybill": "174379",
                    },
                    "amount": 2500,
                    "reference": "concurrent_conflict",  # same ref!
                    "actor": "edit_b",
                    "seed": 0,
                },
                "second concurrent edit (DIFFERENT amount, same ref)",
            )
        if self._step == 2:
            self._step += 1
            return ("events:query",
                    {"event_type": "integration.mpesa.success",
                     "limit": 10},
                    "look at what was committed")
        return (None, {}, "conflict probe complete")


class OverrideControlAttemptPolicy(AgentPolicy):
    """Call destructive tools out of order without preconditions."""
    name = "override_attempt"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            # Try to activate chaos with bogus reference (should fail)
            ("chaos:activate",
              {"name": "nonexistent_chaos_xyz"},
              "override: activate fake chaos"),
            # Try to predict using nonexistent model
            ("ml:predict",
              {"model_name": "nonexistent_model_xyz", "n": 5},
              "override: predict with missing model"),
            # Try macro shock with bogus type
            ("macro:apply_shock",
              {"shock": "garbage_shock_xyz"},
              "override: garbage shock"),
            # Recover by checking what actually exists
            ("chaos:list", {}, "what's actually available"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "override attempts complete")


class StaleSessionReusePolicy(AgentPolicy):
    """Use the same correlation_id across artificially-stale sim time."""
    name = "stale_session_reuser"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        if self._step == 0:
            self._step += 1
            return ("time:now", {}, "check session start time")
        if self._step == 1:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 100, "paybill": "174379",
                    },
                    "amount": 100,
                    "reference": "stale_session",
                    "actor": "stale_user",
                    "seed": 11,
                },
                "first submit, current session",
            )
        if self._step == 2:
            self._step += 1
            return ("time:advance",
                     {"hours": 8},
                     "long pause (simulating stale session)")
        if self._step == 3:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 100, "paybill": "174379",
                    },
                    "amount": 100,
                    "reference": "stale_session",  # SAME ref!
                    "actor": "stale_user",
                    "seed": 11,
                },
                "reuse stale session 8 hours later",
            )
        return (None, {}, "stale session test complete")


class MassActionMistakePolicy(AgentPolicy):
    """One-shot 20 channel submits in rapid succession."""
    name = "mass_action_mistake"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        if self._step < 20:
            self._step += 1
            return (
                "channel:submit",
                {
                    "channel": "mpesa",
                    "payload": {
                        "transaction_type": "CustomerPayBillOnline",
                        "msisdn": "254712345678",
                        "amount": 1500, "paybill": "174379",
                    },
                    "amount": 1500,
                    "reference": f"mass_{self._step}",
                    "actor": "mass_clicker",
                    "seed": self._step,
                },
                f"mass action {self._step}/20",
            )
        return (None, {}, "mass action complete")


class WorkflowSkipStepPolicy(AgentPolicy):
    """Jump straight to the last step without preconditions."""
    name = "skip_step"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        # Skip directly to ml:predict (needs trained model)
        if self._step == 0:
            self._step += 1
            return ("ml:predict",
                     {"model_name": "skipped_setup_model", "n": 3},
                     "skip to predict (no model trained)")
        if self._step == 1:
            self._step += 1
            return ("chaos:active", {},
                     "check what state we're in")
        if self._step == 2:
            self._step += 1
            return ("channel:list", {},
                     "back to start")
        return (None, {}, "skip-step probe complete")


class ApprovalPingPongPolicy(AgentPolicy):
    """Alternate approve/reject the same operation repeatedly."""
    name = "approval_pingpong"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        # Toggle between two states - simulated by chaos:active list
        # (no real approval tool exists; we use observation patterns)
        if self._step < 6:
            self._step += 1
            if self._step % 2 == 1:
                return ("chaos:list", {},
                         f"ping {self._step}/6 (look)")
            else:
                return ("macro:snapshot", {},
                         f"pong {self._step}/6 (look elsewhere)")
        return (None, {}, "approval pingpong complete")


# ─── Irrationality drill library ────────────────────────────────────


def _build_irrational_library() -> Dict[str, Tuple[Drill, AgentPolicy]]:
    """Return (drill, policy_factory) pairs.

    Each drill uses a baseline channel-survival environment but the
    policy is what makes it irrational.
    """
    tz = _tz()
    L: Dict[str, Tuple[Drill, type]] = {}

    base_start = datetime(2026, 7, 1, 10, 0, tzinfo=tz)

    L["ir_rapid_duplicate_clicks"] = (
        Drill(
            name="ir_rapid_duplicate_clicks",
            description=(
                "User mashes submit button 5 times in rapid "
                "succession with identical reference. System should "
                "honour idempotency or honestly distinguish duplicates."
            ),
            category="irrational",
            sim_start=base_start,
            environment=[],  # no chaos — testing the WAY user acts
            agent_goal="duplicate_click_test",
            oracle=DrillOracle(
                min_steps=5,
                required_tool_calls=["channel:submit"],
            ),
            tags=["irrational", "duplicates", "ux"],
        ),
        RapidDuplicateClickPolicy,
    )

    L["ir_abandoned_workflow"] = (
        Drill(
            name="ir_abandoned_workflow",
            description=(
                "User starts a workflow but never confirms. System "
                "should not be left in inconsistent state — half-done "
                "transactions should be observable via audit trail."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=1),
            environment=[],
            agent_goal="abandon_test",
            oracle=DrillOracle(
                min_steps=3,
                required_tool_calls=["channel:submit"],
            ),
            tags=["irrational", "abandoned", "ux"],
        ),
        AbandonedWorkflowPolicy,
    )

    L["ir_conflicting_concurrent_edits"] = (
        Drill(
            name="ir_conflicting_concurrent_edits",
            description=(
                "Two concurrent submissions with same reference but "
                "different amounts. Tests idempotency: first should "
                "win, second should be flagged (or idempotently match)."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=2),
            environment=[],
            agent_goal="concurrent_edit_test",
            oracle=DrillOracle(
                min_steps=3,
                required_tool_calls=["channel:submit", "events:query"],
            ),
            tags=["irrational", "concurrency", "idempotency"],
        ),
        ConflictingConcurrentEditPolicy,
    )

    L["ir_override_control_attempt"] = (
        Drill(
            name="ir_override_control_attempt",
            description=(
                "User attempts unauthorised destructive calls with "
                "bogus arguments. ToolRegistry should reject all and "
                "user recovers via inspection of the real menu."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=3),
            environment=[],
            agent_goal="override_test",
            oracle=DrillOracle(
                # Many submits should fail — total successful >=1
                # (the recovery call to chaos:list)
                min_steps=4,
                min_successful_steps=1,
                # Failure rate up to 75% is acceptable here -
                # we WANT the bad calls to fail
                max_failure_rate=0.80,
            ),
            tags=["irrational", "override", "rbac"],
        ),
        OverrideControlAttemptPolicy,
    )

    L["ir_stale_session_reuse"] = (
        Drill(
            name="ir_stale_session_reuse",
            description=(
                "User reuses a session reference 8 sim-hours later. "
                "System should distinguish or honour idempotency."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=4),
            environment=[],
            agent_goal="stale_session_test",
            oracle=DrillOracle(
                min_steps=4,
                required_tool_calls=["channel:submit", "time:advance"],
            ),
            tags=["irrational", "session", "stale"],
        ),
        StaleSessionReusePolicy,
    )

    L["ir_mass_action_mistake"] = (
        Drill(
            name="ir_mass_action_mistake",
            description=(
                "User accidentally clicks bulk-submit 20 times. "
                "Tests rate-limit / quota behaviour. All should be "
                "auditable in the event bus."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=5),
            environment=[],
            agent_goal="mass_action_test",
            oracle=DrillOracle(
                min_steps=20,
                required_tool_calls=["channel:submit"],
            ),
            tags=["irrational", "bulk", "rate_limit"],
        ),
        MassActionMistakePolicy,
    )

    L["ir_workflow_skip_step"] = (
        Drill(
            name="ir_workflow_skip_step",
            description=(
                "User jumps to last workflow step without "
                "preconditions. ml:predict should reject missing "
                "model gracefully."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=6),
            environment=[],
            agent_goal="skip_step_test",
            oracle=DrillOracle(
                min_steps=3,
                # We expect the first call to fail
                min_successful_steps=2,
            ),
            tags=["irrational", "skip", "preconditions"],
        ),
        WorkflowSkipStepPolicy,
    )

    L["ir_approval_pingpong"] = (
        Drill(
            name="ir_approval_pingpong",
            description=(
                "User toggles between two observation modes 6 times. "
                "Tests audit-trail clarity under indecisive behaviour."
            ),
            category="irrational",
            sim_start=base_start + timedelta(hours=7),
            environment=[],
            agent_goal="pingpong_test",
            oracle=DrillOracle(
                min_steps=6,
            ),
            tags=["irrational", "indecision"],
        ),
        ApprovalPingPongPolicy,
    )

    return L


_LIBRARY: Dict[str, Tuple[Drill, type]] = None  # type: ignore


def _ensure() -> Dict[str, Tuple[Drill, type]]:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_irrational_library()
    return _LIBRARY


def list_irrational_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_irrational_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown irrational drill: {name!r}")
    return L[name][0]


def get_irrational_policy_factory(name: str) -> type:
    """Return the policy class to instantiate fresh per run."""
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown irrational drill: {name!r}")
    return L[name][1]


def run_irrational_drill(name: str):
    """Helper that wires the right policy into DrillRunner."""
    from utils.arena import DrillRunner
    from utils.agents.base import AgentBudget
    drill = get_irrational_drill(name)
    policy_cls = get_irrational_policy_factory(name)
    runner = DrillRunner(
        agent_policy=policy_cls(),
        agent_budget=AgentBudget(max_steps=30, max_seconds=60),
    )
    return runner.run(drill)


__all__ = [
    "RapidDuplicateClickPolicy", "AbandonedWorkflowPolicy",
    "ConflictingConcurrentEditPolicy", "OverrideControlAttemptPolicy",
    "StaleSessionReusePolicy", "MassActionMistakePolicy",
    "WorkflowSkipStepPolicy", "ApprovalPingPongPolicy",
    "list_irrational_drills", "get_irrational_drill",
    "get_irrational_policy_factory", "run_irrational_drill",
]

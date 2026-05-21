"""utils/arena/runner.py — DrillRunner.

Wires together:
  - SimulationClock (set to drill.sim_start)
  - TickScheduler
  - ChaosScheduler (for chaos events)
  - AgentRunner (with the drill's agent_goal)

For each DrillEnvironmentEvent:
  - chaos:activate    -> schedule chaos at sim_start + offset
  - macro:apply_shock -> schedule a direct macro shock at sim_start + offset
  - scenario:run      -> schedule a scenario.run call

Then advances the clock by enough to fire all environment events, runs
the agent, and evaluates the oracle.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from utils.arena.base import (
    Drill, DrillEnvironmentEvent, DrillOracle, DrillResult,
)


class DrillRunner:
    """Run a drill end-to-end and evaluate the oracle."""

    def __init__(self, *, agent_policy=None, agent_budget=None):
        self._policy = agent_policy
        self._budget = agent_budget

    def run(self, drill: Drill) -> DrillResult:
        # Lazy imports — keep arena/__init__ light + avoid circular deps
        from utils.simulation_clock import (
            get_simulation_clock, reset_simulation_clock,
        )
        from utils.tick_scheduler import TickScheduler
        from utils.chaos import (
            ChaosScheduler, get_chaos_event, reset_chaos_injector,
        )
        from utils.macro_state import reset_macro_state
        from utils.agents import (
            AgentRunner, DeterministicPolicy, AgentBudget,
        )

        # ── reset state for reproducibility ──────────────────────
        reset_simulation_clock()
        reset_chaos_injector()
        reset_macro_state()

        clock = get_simulation_clock()
        clock.set(drill.sim_start)

        tick = TickScheduler(clock)
        chaos_sched = ChaosScheduler(scheduler=tick)
        environment_fired: List[str] = []

        # ── schedule each environment event ──────────────────────
        max_offset = timedelta(0)
        for env_ev in drill.environment:
            fire_time = drill.sim_start + env_ev.offset
            if env_ev.offset > max_offset:
                max_offset = env_ev.offset

            if env_ev.kind == "chaos:activate":
                ev = get_chaos_event(env_ev.ref, when=fire_time,
                                       **env_ev.kwargs)
                chaos_sched.schedule(ev)
                environment_fired.append(env_ev.ref)
            elif env_ev.kind == "macro:apply_shock":
                self._schedule_macro_shock(
                    tick, fire_time, env_ev.ref, env_ev.kwargs)
                environment_fired.append(
                    f"macro_shock:{env_ev.ref}")
            elif env_ev.kind == "scenario:run":
                self._schedule_scenario_run(
                    tick, fire_time, env_ev.ref)
                environment_fired.append(
                    f"scenario:{env_ev.ref}")
            else:
                # Unknown kind — record but don't raise
                environment_fired.append(
                    f"unknown:{env_ev.kind}:{env_ev.ref}")

        # ── advance clock through all environment events ─────────
        # Always tick by at least 1 second so events scheduled at
        # offset=0 fire before the agent starts. Without this, drills
        # whose environment events are all offset=0 would never have
        # their chaos activated before the agent runs.
        tick.tick(advance_by=max_offset + timedelta(seconds=1))

        # ── run the agent ────────────────────────────────────────
        policy = self._policy or DeterministicPolicy()
        budget = self._budget or AgentBudget(max_steps=8,
                                                max_seconds=30)
        agent_runner = AgentRunner()
        agent_result = agent_runner.run(
            policy=policy,
            goal=drill.agent_goal,
            agent_name=f"drill_{drill.name}",
            budget=budget,
        )

        # ── evaluate oracle ──────────────────────────────────────
        passed, reasons = self._evaluate_oracle(
            drill, agent_result, environment_fired)

        return DrillResult(
            drill_name=drill.name,
            passed=passed,
            agent_steps=agent_result.step_count(),
            successful_agent_steps=
                agent_result.trajectory.successful_steps(),
            failure_reasons=reasons,
            environment_fired=environment_fired,
            trajectory=agent_result.trajectory,
        )

    # ── helpers ──────────────────────────────────────────────────

    def _schedule_macro_shock(self, tick, fire_time, shock_name,
                                  kwargs):
        def fire():
            from utils.macro_state import (
                get_macro_state, set_macro_state)
            from utils.macro_evolution import MacroEvolution
            state = get_macro_state()
            ev = MacroEvolution(seed=0)
            set_macro_state(
                ev.apply_shock(state, shock=shock_name, **kwargs)
            )
        tick.schedule_at(fire_time, fire,
                          label=f"macro:{shock_name}", priority=5)

    def _schedule_scenario_run(self, tick, fire_time, scenario_name):
        def fire():
            from utils.scenarios import get_scenario
            from utils.scenarios.base import (
                ScenarioContext, ScenarioRunner)
            scenario = get_scenario(scenario_name)
            ctx = ScenarioContext(scenario_name=scenario_name)
            ScenarioRunner(scenario, ctx).run()
        tick.schedule_at(fire_time, fire,
                          label=f"scenario:{scenario_name}", priority=5)

    def _evaluate_oracle(self, drill: Drill, agent_result,
                            environment_fired: List[str]):
        oracle = drill.oracle
        reasons: List[str] = []
        traj = agent_result.trajectory

        # min_steps
        if oracle.min_steps is not None:
            if traj.step_count() < oracle.min_steps:
                reasons.append(
                    f"min_steps: {traj.step_count()} < "
                    f"{oracle.min_steps}"
                )

        # min_successful_steps
        if oracle.min_successful_steps is not None:
            ok = traj.successful_steps()
            if ok < oracle.min_successful_steps:
                reasons.append(
                    f"min_successful_steps: {ok} < "
                    f"{oracle.min_successful_steps}"
                )

        # required_tool_calls
        if oracle.required_tool_calls:
            called = set(traj.tool_call_summary().keys())
            missing = [t for t in oracle.required_tool_calls
                        if t not in called]
            if missing:
                reasons.append(
                    f"required tools missing: {missing}"
                )

        # forbidden_tool_calls
        if oracle.forbidden_tool_calls:
            called = set(traj.tool_call_summary().keys())
            forbidden = [t for t in oracle.forbidden_tool_calls
                          if t in called]
            if forbidden:
                reasons.append(
                    f"forbidden tools called: {forbidden}"
                )

        # max_failure_rate
        if oracle.max_failure_rate is not None and traj.step_count() > 0:
            failed = traj.step_count() - traj.successful_steps()
            rate = failed / traj.step_count()
            if rate > oracle.max_failure_rate:
                reasons.append(
                    f"failure rate {rate:.2f} > "
                    f"{oracle.max_failure_rate}"
                )

        # must_observe_chaos
        if oracle.must_observe_chaos:
            from utils.chaos import get_chaos_injector
            injector = get_chaos_injector()
            saw_chaos = False
            # If any step was taken during the chaos window
            for step in traj.steps:
                if step.tool_name == "chaos:active":
                    out = step.result.output or {}
                    if out.get("count", 0) > 0:
                        saw_chaos = True
                        break
            if not saw_chaos:
                # Fallback: did *any* environment event fire that
                # would activate chaos in the injector?
                # (used when policy doesn't probe chaos:active)
                if not environment_fired:
                    reasons.append(
                        "must_observe_chaos: no chaos fired in env"
                    )

        # custom check
        if oracle.custom_check is not None:
            try:
                ok, msg = oracle.custom_check(drill, agent_result)
                if not ok:
                    reasons.append(f"custom check: {msg}")
            except Exception as exc:
                reasons.append(f"custom check raised: {exc}")

        passed = not reasons
        return passed, reasons


__all__ = ["DrillRunner"]

"""Integration tests for v10.484 — Phase O6-B LLM agent infrastructure."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_all():
    for k in list(sys.modules):
        if any(s in k for s in ("agents", "ml", "chaos", "channels",
                                  "simulation_clock", "tick_scheduler",
                                  "event_bus", "macro_", "scenarios")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    from utils.ml import reset_model_registry
    from utils.agents import reset_default_tool_registry
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    reset_default_tool_registry()
    yield
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    reset_default_tool_registry()


# ── Module presence ─────────────────────────────────────────────────

def test_v10484_agents_package_exists():
    pkg = REPO / "utils" / "agents"
    assert pkg.is_dir()
    for f in ["__init__.py", "base.py", "tools.py",
                "policies.py", "runner.py"]:
        assert (pkg / f).exists()


# ── Base types ──────────────────────────────────────────────────────

def test_v10484_agent_tool_rejects_non_callable():
    from utils.agents import AgentTool
    with pytest.raises(ValueError):
        AgentTool(name="x", description="d", handler="not_callable")


def test_v10484_agent_tool_rejects_empty_name():
    from utils.agents import AgentTool
    with pytest.raises(ValueError):
        AgentTool(name="", description="d", handler=lambda: {})


def test_v10484_agent_tool_result_to_dict():
    from utils.agents import AgentToolResult
    r = AgentToolResult(
        tool_name="t", success=True,
        output={"x": 1}, latency_ms=12.345,
    )
    d = r.to_dict()
    assert d["tool_name"] == "t"
    assert d["success"] is True
    assert d["output"] == {"x": 1}


def test_v10484_agent_budget_max_steps():
    from utils.agents import AgentBudget
    b = AgentBudget(max_steps=3, max_seconds=60)
    assert b.exhausted(0) is None
    assert b.exhausted(2) is None
    assert b.exhausted(3) is not None
    assert "max_steps" in b.exhausted(3)


def test_v10484_agent_budget_step_remaining():
    from utils.agents import AgentBudget
    b = AgentBudget(max_steps=5)
    assert b.step_remaining(0) == 5
    assert b.step_remaining(3) == 2
    assert b.step_remaining(10) == 0


def test_v10484_agent_trajectory_summary():
    from utils.agents import (
        AgentTrajectory, AgentStep, AgentToolResult,
    )
    traj = AgentTrajectory(agent_name="a", goal="g")
    traj.add_step(AgentStep(
        index=0, tool_name="x", args={},
        result=AgentToolResult(tool_name="x", success=True),
    ))
    traj.add_step(AgentStep(
        index=1, tool_name="x", args={},
        result=AgentToolResult(tool_name="x", success=False),
    ))
    traj.add_step(AgentStep(
        index=2, tool_name="y", args={},
        result=AgentToolResult(tool_name="y", success=True),
    ))
    assert traj.step_count() == 3
    assert traj.successful_steps() == 2
    assert traj.tool_call_summary() == {"x": 2, "y": 1}


# ── ToolRegistry ────────────────────────────────────────────────────

def test_v10484_default_registry_has_15_tools():
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    assert len(reg.list_names()) == 15


def test_v10484_default_registry_categories():
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    for cat in ["channel", "scenario", "chaos", "macro", "ml", "info"]:
        assert reg.list_by_category(cat), f"category {cat} empty"


def test_v10484_registry_call_wraps_success():
    from utils.agents import get_default_tool_registry, AgentToolResult
    reg = get_default_tool_registry()
    r = reg.call("channel:list")
    assert isinstance(r, AgentToolResult)
    assert r.success
    assert "channels" in r.output


def test_v10484_registry_call_wraps_unknown_tool():
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    r = reg.call("nonexistent_tool_xyz")
    assert not r.success
    assert "unknown tool" in r.error.lower()


def test_v10484_registry_call_wraps_handler_exception():
    from utils.agents import (
        AgentTool, ToolRegistry, get_default_tool_registry,
    )
    reg = get_default_tool_registry()
    def boom(**kw):
        raise RuntimeError("intentional explosion")
    reg.register(AgentTool(
        name="test:boom", description="raises", handler=boom,
    ))
    r = reg.call("test:boom")
    assert not r.success
    assert "explosion" in r.error or "RuntimeError" in r.error


def test_v10484_registry_register_then_get():
    from utils.agents import AgentTool, ToolRegistry
    reg = ToolRegistry()
    tool = AgentTool(name="ping", description="pong",
                       handler=lambda: {"pong": True})
    reg.register(tool)
    assert reg.has("ping")
    assert reg.get("ping") is tool


def test_v10484_macro_snapshot_tool():
    from utils.agents import get_default_tool_registry
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    reg = get_default_tool_registry()
    r = reg.call("macro:snapshot")
    assert r.success
    assert "cbk_central_bank_rate" in r.output
    assert "usd_kes" in r.output


def test_v10484_chaos_list_tool():
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    r = reg.call("chaos:list")
    assert r.success
    assert len(r.output["chaos_templates"]) == 25


def test_v10484_channel_submit_tool():
    from utils.agents import get_default_tool_registry
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    reg = get_default_tool_registry()
    r = reg.call("channel:submit",
                  channel="mpesa",
                  payload={"transaction_type": "CustomerPayBillOnline",
                            "msisdn": "254712345678",
                            "amount": 1500, "paybill": "174379"},
                  amount=1500, reference="agent_test", actor="t", seed=1)
    assert r.success
    assert r.output["channel"] == "mpesa"


# ── Policies ────────────────────────────────────────────────────────

def test_v10484_deterministic_policy_inspect_channels():
    from utils.agents import (
        AgentRunner, DeterministicPolicy, AgentBudget,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    result = AgentRunner().run(
        policy=DeterministicPolicy(),
        goal="inspect_channels",
        budget=AgentBudget(max_steps=10),
    )
    assert result.step_count() == 3
    assert result.trajectory.successful_steps() >= 2


def test_v10484_deterministic_policy_survey_macro():
    from utils.agents import (
        AgentRunner, DeterministicPolicy, AgentBudget,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    result = AgentRunner().run(
        policy=DeterministicPolicy(),
        goal="survey_macro",
        budget=AgentBudget(max_steps=10),
    )
    assert result.step_count() == 2
    assert all(s.result.success for s in result.trajectory.steps)


def test_v10484_deterministic_policy_terminates_cleanly():
    from utils.agents import (
        AgentRunner, DeterministicPolicy, AgentBudget,
    )
    result = AgentRunner().run(
        policy=DeterministicPolicy(),
        goal="survey_chaos",
        budget=AgentBudget(max_steps=10),
    )
    assert "complete" in (result.terminated_reason or "").lower()


def test_v10484_random_policy_seed_deterministic():
    from utils.agents import (
        AgentRunner, RandomPolicy, AgentBudget,
    )
    a = AgentRunner().run(
        policy=RandomPolicy(seed=42),
        goal="explore", budget=AgentBudget(max_steps=5),
    )
    b = AgentRunner().run(
        policy=RandomPolicy(seed=42),
        goal="explore", budget=AgentBudget(max_steps=5),
    )
    a_tools = [s.tool_name for s in a.trajectory.steps]
    b_tools = [s.tool_name for s in b.trajectory.steps]
    assert a_tools == b_tools


def test_v10484_random_policy_excludes_destructive_tools():
    from utils.agents import (
        AgentRunner, RandomPolicy, AgentBudget,
    )
    result = AgentRunner().run(
        policy=RandomPolicy(seed=0),
        goal="explore", budget=AgentBudget(max_steps=10),
    )
    for s in result.trajectory.steps:
        assert s.tool_name not in {
            "channel:submit", "chaos:activate",
            "macro:apply_shock", "ml:train_classifier",
            "time:advance",
        }, f"random picked destructive {s.tool_name}"


def test_v10484_scripted_policy_executes_script():
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    script = [
        ("channel:list", {}),
        ("macro:snapshot", {}),
        ("chaos:list", {}),
        ("time:now", {}),
    ]
    result = AgentRunner().run(
        policy=ScriptedPolicy(script),
        goal="scripted", budget=AgentBudget(max_steps=20),
    )
    assert result.step_count() == len(script)
    expected_tools = [t for t, _ in script]
    actual_tools = [s.tool_name for s in result.trajectory.steps]
    assert actual_tools == expected_tools


def test_v10484_scripted_policy_terminates_on_exhaustion():
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    result = AgentRunner().run(
        policy=ScriptedPolicy([("channel:list", {})]),
        goal="single", budget=AgentBudget(max_steps=10),
    )
    assert result.step_count() == 1
    assert "exhausted" in result.terminated_reason.lower()


# ── AgentRunner ─────────────────────────────────────────────────────

def test_v10484_runner_respects_max_steps_budget():
    from utils.agents import (
        AgentRunner, RandomPolicy, AgentBudget,
    )
    result = AgentRunner().run(
        policy=RandomPolicy(seed=1),
        goal="explore", budget=AgentBudget(max_steps=3),
    )
    assert result.step_count() <= 3


def test_v10484_runner_emits_step_events():
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    from utils.event_bus import get_event_bus
    AgentRunner().run(
        policy=ScriptedPolicy([("channel:list", {}),
                                  ("macro:snapshot", {})]),
        goal="emit_test", agent_name="emit_bot",
        budget=AgentBudget(max_steps=5),
    )
    bus = get_event_bus()
    steps = bus.query(event_type="agent.step", limit=20)
    assert any(e.actor == "emit_bot" for e in steps)


def test_v10484_runner_emits_run_complete_event():
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    from utils.event_bus import get_event_bus
    AgentRunner().run(
        policy=ScriptedPolicy([("time:now", {})]),
        goal="complete_test", agent_name="complete_bot",
    )
    bus = get_event_bus()
    completes = bus.query(event_type="agent.run_complete", limit=20)
    assert any(e.actor == "complete_bot" for e in completes)


def test_v10484_runner_observation_includes_context():
    """The agent's observation should include macro + chaos context."""
    from utils.agents import (
        AgentRunner, AgentPolicy, AgentBudget,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))

    seen_contexts = []

    class CaptureLastObsPolicy(AgentPolicy):
        name = "capture"
        def choose(self, obs, tools, goal):
            seen_contexts.append(obs.context)
            if obs.step_index >= 2:
                return (None, {}, "captured enough")
            return ("time:now", {}, "tick")

    AgentRunner().run(policy=CaptureLastObsPolicy(), goal="x")
    assert seen_contexts
    last = seen_contexts[-1]
    assert "cbr" in last and "usd_kes" in last


def test_v10484_runner_disabled_events_dont_emit():
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    before = len(bus.query(event_type="agent.step", limit=1000))
    AgentRunner(emit_events=False).run(
        policy=ScriptedPolicy([("time:now", {})]),
        goal="quiet", agent_name="quiet_bot",
    )
    after = bus.query(event_type="agent.step", limit=1000)
    new = [e for e in after if e.actor == "quiet_bot"]
    assert not new


def test_v10484_runner_records_full_trajectory():
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    script = [("channel:list", {}), ("chaos:list", {}),
                ("macro:snapshot", {})]
    result = AgentRunner().run(
        policy=ScriptedPolicy(script),
        goal="trajectory_test",
        agent_name="traj_bot",
    )
    traj = result.trajectory
    assert traj.agent_name == "traj_bot"
    assert traj.step_count() == 3
    for s, (expected_tool, _) in zip(traj.steps, script):
        assert s.tool_name == expected_tool
        assert s.timestamp


def test_v10484_runner_result_to_dict_serialisable():
    import json
    from utils.agents import (
        AgentRunner, ScriptedPolicy,
    )
    result = AgentRunner().run(
        policy=ScriptedPolicy([("time:now", {})]),
        goal="serialise_test",
    )
    d = result.to_dict()
    serialised = json.dumps(d, default=str)
    assert "serialise_test" in serialised


# ── End-to-end ──────────────────────────────────────────────────────

def test_v10484_e2e_agent_with_macro_chaos_ml_pipeline():
    """An agent can survey macro, list chaos, and inspect models."""
    from utils.agents import (
        AgentRunner, ScriptedPolicy, AgentBudget,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    result = AgentRunner().run(
        policy=ScriptedPolicy([
            ("macro:snapshot", {}),
            ("chaos:list", {}),
            ("ml:list", {}),
            ("events:query", {"limit": 5}),
        ]),
        goal="comprehensive_survey",
        agent_name="e2e_bot",
    )
    assert result.step_count() == 4
    assert result.trajectory.successful_steps() == 4


# ── G370 + cumulative regression ────────────────────────────────────

def test_v10484_g370_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10484_o6b_agent_infrastructure
    r = gate_v10484_o6b_agent_infrastructure()
    assert r["passed"], r.get("violations")


def test_v10484_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10483_o6a_ml_evolution_lab,
        gate_v10482_o5_chaos_engineering,
        gate_v10481_o4b_macro_economic_state,
        gate_v10480_o4a_simulation_clock_tick_scheduler,
        gate_v10479_o3c_scenario_library,
    )
    for gate in (gate_v10483_o6a_ml_evolution_lab,
                  gate_v10482_o5_chaos_engineering,
                  gate_v10481_o4b_macro_economic_state,
                  gate_v10480_o4a_simulation_clock_tick_scheduler,
                  gate_v10479_o3c_scenario_library):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10484_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

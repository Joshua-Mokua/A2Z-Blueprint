"""Integration tests for v10.485 — Phase O7-A training arena."""

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
        if any(s in k for s in ("arena", "agents", "ml", "chaos",
                                  "channels", "simulation_clock",
                                  "tick_scheduler", "event_bus",
                                  "macro_", "scenarios")):
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

def test_v10485_arena_package_exists():
    pkg = REPO / "utils" / "arena"
    assert pkg.is_dir()
    for f in ["__init__.py", "base.py", "library.py", "runner.py"]:
        assert (pkg / f).exists()


# ── Base types ──────────────────────────────────────────────────────

def test_v10485_drill_naive_sim_start_rejected():
    from utils.arena import Drill
    with pytest.raises(ValueError):
        Drill(name="x", description="d", category="c",
               sim_start=datetime(2026, 1, 1))


def test_v10485_drill_empty_name_rejected():
    from utils.arena import Drill
    from utils.simulation_clock import NAIROBI_TZ
    with pytest.raises(ValueError):
        Drill(name="", description="d", category="c",
               sim_start=datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))


def test_v10485_drill_environment_event_offset():
    from utils.arena import DrillEnvironmentEvent
    ev = DrillEnvironmentEvent(
        offset=timedelta(minutes=15),
        kind="chaos:activate",
        ref="safaricom_mpesa_outage_30min",
    )
    assert ev.offset == timedelta(minutes=15)


def test_v10485_drill_oracle_defaults():
    from utils.arena import DrillOracle
    o = DrillOracle()
    assert o.min_steps is None
    assert o.required_tool_calls == []
    assert o.forbidden_tool_calls == []
    assert o.must_observe_chaos is False


def test_v10485_drill_event_count():
    from utils.arena import Drill, DrillEnvironmentEvent
    from utils.simulation_clock import NAIROBI_TZ
    d = Drill(
        name="t", description="d", category="c",
        sim_start=datetime(2026, 1, 1, tzinfo=NAIROBI_TZ),
        environment=[
            DrillEnvironmentEvent(offset=timedelta(0),
                                    kind="chaos:activate", ref="x"),
            DrillEnvironmentEvent(offset=timedelta(minutes=10),
                                    kind="chaos:activate", ref="y"),
        ],
    )
    assert d.event_count() == 2


# ── Library ─────────────────────────────────────────────────────────

def test_v10485_library_has_12_drills():
    from utils.arena import list_drills
    assert len(list_drills()) == 12


def test_v10485_library_breakdown_by_category():
    from utils.arena import drills_by_category
    assert len(drills_by_category("channel_survival")) == 4
    assert len(drills_by_category("macro_observation")) == 3
    assert len(drills_by_category("eom_pressure")) == 2
    assert len(drills_by_category("chaos_ml")) == 2
    assert len(drills_by_category("scenario_cascade")) == 1


def test_v10485_library_total_matches_categories():
    from utils.arena import list_drills, drills_by_category
    total = (
        len(drills_by_category("channel_survival"))
        + len(drills_by_category("macro_observation"))
        + len(drills_by_category("eom_pressure"))
        + len(drills_by_category("chaos_ml"))
        + len(drills_by_category("scenario_cascade"))
    )
    assert total == len(list_drills())


def test_v10485_get_drill_unknown_raises():
    from utils.arena import get_drill
    with pytest.raises(KeyError):
        get_drill("does_not_exist_xyz")


def test_v10485_drill_library_dict_access():
    from utils.arena import DRILL_LIBRARY
    assert "survive_safaricom_outage_morning" in DRILL_LIBRARY
    assert len(DRILL_LIBRARY) == 12
    d = DRILL_LIBRARY["survive_safaricom_outage_morning"]
    assert d.category == "channel_survival"


def test_v10485_all_drills_have_tz_aware_sim_start():
    from utils.arena import list_drills, get_drill
    for name in list_drills():
        drill = get_drill(name)
        assert drill.sim_start.tzinfo is not None


def test_v10485_all_drills_have_description():
    from utils.arena import list_drills, get_drill
    for name in list_drills():
        d = get_drill(name)
        assert d.description.strip(), f"{name} has empty description"


# ── DrillRunner ─────────────────────────────────────────────────────

def test_v10485_runner_runs_safaricom_morning():
    from utils.arena import DrillRunner, get_drill
    result = DrillRunner().run(get_drill("survive_safaricom_outage_morning"))
    assert result.passed, result.failure_reasons
    assert result.agent_steps >= 2
    assert "safaricom_mpesa_outage_30min" in result.environment_fired


def test_v10485_runner_runs_kes_devaluation():
    from utils.arena import DrillRunner, get_drill
    from utils.macro_state import get_macro_state
    result = DrillRunner().run(get_drill("observe_kes_devaluation"))
    assert result.passed, result.failure_reasons
    # After the drill, USD/KES should reflect the 5% devaluation
    ms = get_macro_state()
    # Baseline 130 → 136.5 after 5% shock
    assert ms.usd_kes >= 135.0, f"USD/KES={ms.usd_kes}"


def test_v10485_runner_runs_cbr_hike():
    from utils.arena import DrillRunner, get_drill
    from utils.macro_state import get_macro_state
    result = DrillRunner().run(get_drill("observe_cbr_emergency_hike"))
    assert result.passed, result.failure_reasons
    ms = get_macro_state()
    # CBR baseline 10% → 12% after 200bp hike
    assert ms.cbk_central_bank_rate >= 0.115


def test_v10485_runner_runs_kepss_outage():
    from utils.arena import DrillRunner, get_drill
    from utils.chaos import get_chaos_injector
    result = DrillRunner().run(get_drill("kepss_outage_takes_rtgs_kic"))
    assert result.passed, result.failure_reasons
    # KEPSS takes both RTGS and KIC down
    injector = get_chaos_injector()
    assert (injector.is_channel_outage("rtgs")
            or injector.is_channel_outage("kic"))


def test_v10485_runner_cascade_drill_fires_all_three_events():
    from utils.arena import DrillRunner, get_drill
    result = DrillRunner().run(get_drill("cascade_safaricom_then_kepss"))
    assert result.passed, result.failure_reasons
    assert len(result.environment_fired) == 3


def test_v10485_runner_oracle_required_tools_enforced():
    from utils.arena import Drill, DrillOracle, DrillRunner
    from utils.simulation_clock import NAIROBI_TZ
    # Build a drill that requires a tool the agent won't call
    bad = Drill(
        name="strict_test", description="should fail",
        category="test",
        sim_start=datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ),
        agent_goal="survey_macro",
        oracle=DrillOracle(
            required_tool_calls=["definitely_never_called_xyz"],
        ),
    )
    result = DrillRunner().run(bad)
    assert not result.passed
    assert any("required tools missing" in r
                for r in result.failure_reasons)


def test_v10485_runner_oracle_min_steps_enforced():
    from utils.arena import Drill, DrillOracle, DrillRunner
    from utils.simulation_clock import NAIROBI_TZ
    strict = Drill(
        name="min_steps_test", description="impossible",
        category="test",
        sim_start=datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ),
        agent_goal="survey_macro",
        oracle=DrillOracle(min_steps=100),  # impossibly high
    )
    result = DrillRunner().run(strict)
    assert not result.passed


def test_v10485_runner_oracle_forbidden_tools_enforced():
    from utils.arena import Drill, DrillOracle, DrillRunner
    from utils.simulation_clock import NAIROBI_TZ
    forbid = Drill(
        name="forbid_test", description="forbidden",
        category="test",
        sim_start=datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ),
        agent_goal="survey_macro",
        oracle=DrillOracle(
            forbidden_tool_calls=["macro:snapshot"],
        ),
    )
    result = DrillRunner().run(forbid)
    # survey_macro calls macro:snapshot, so this should fail
    assert not result.passed
    assert any("forbidden tools" in r
                for r in result.failure_reasons)


def test_v10485_runner_custom_check():
    from utils.arena import Drill, DrillOracle, DrillRunner
    from utils.simulation_clock import NAIROBI_TZ

    def reject_all(drill, result):
        return (False, "always reject")

    drill = Drill(
        name="custom_test", description="custom check",
        category="test",
        sim_start=datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ),
        agent_goal="survey_macro",
        oracle=DrillOracle(custom_check=reject_all),
    )
    result = DrillRunner().run(drill)
    assert not result.passed
    assert any("always reject" in r for r in result.failure_reasons)


def test_v10485_runner_emits_agent_events_during_drill():
    from utils.arena import DrillRunner, get_drill
    from utils.event_bus import get_event_bus
    DrillRunner().run(get_drill("observe_kes_devaluation"))
    bus = get_event_bus()
    steps = bus.query(event_type="agent.step", limit=20)
    # Should have steps tagged with drill_observe_kes_devaluation actor
    assert any("drill_observe_kes_devaluation" in (e.actor or "")
                for e in steps)


def test_v10485_runner_reproducible_same_drill():
    """Same drill run twice should produce same environment_fired."""
    from utils.arena import DrillRunner, get_drill
    r1 = DrillRunner().run(get_drill("survive_swift_correspondent_failure"))
    r2 = DrillRunner().run(get_drill("survive_swift_correspondent_failure"))
    assert r1.environment_fired == r2.environment_fired


# ── All 12 drills pass ──────────────────────────────────────────────

def test_v10485_all_12_library_drills_pass():
    from utils.arena import DrillRunner, list_drills, get_drill
    runner = DrillRunner()
    failures = []
    for name in list_drills():
        result = runner.run(get_drill(name))
        if not result.passed:
            failures.append((name, result.failure_reasons))
    assert not failures, failures


# ── ToolRegistry.call kwarg fix ─────────────────────────────────────

def test_v10485_tool_registry_call_uses_tool_name_param():
    """Critical fix: 'name' kwarg collision."""
    import inspect
    from utils.agents.tools import ToolRegistry
    sig = inspect.signature(ToolRegistry.call)
    params = list(sig.parameters.keys())
    assert "tool_name" in params
    assert "name" not in params


def test_v10485_ml_train_classifier_tool_works_via_registry():
    """ml:train_classifier takes name kwarg - shouldn't collide."""
    from utils.agents import get_default_tool_registry
    from utils.channels import submit_channel
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    # Generate some traffic
    for i in range(10):
        submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"R{i}", actor="t", seed=i)
    reg = get_default_tool_registry()
    r = reg.call("ml:train_classifier",
                  name="kwarg_collision_test",
                  target_label="success",
                  seed=42)
    assert r.success, r.error
    assert r.output.get("name") == "kwarg_collision_test"


# ── G371 + cumulative regression ────────────────────────────────────

def test_v10485_g371_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10485_o7a_training_arena
    r = gate_v10485_o7a_training_arena()
    assert r["passed"], r.get("violations")


def test_v10485_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10484_o6b_agent_infrastructure,
        gate_v10483_o6a_ml_evolution_lab,
        gate_v10482_o5_chaos_engineering,
        gate_v10481_o4b_macro_economic_state,
    )
    for gate in (gate_v10484_o6b_agent_infrastructure,
                  gate_v10483_o6a_ml_evolution_lab,
                  gate_v10482_o5_chaos_engineering,
                  gate_v10481_o4b_macro_economic_state):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10485_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

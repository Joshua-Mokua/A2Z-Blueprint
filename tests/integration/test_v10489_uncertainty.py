"""Integration tests for v10.489 — Uncertainty exposure phase 1."""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_all():
    for k in list(sys.modules):
        if any(s in k for s in ("uncertainty", "cert", "arena", "agents",
                                  "ml", "chaos", "channels",
                                  "simulation_clock", "tick_scheduler",
                                  "event_bus", "macro_", "scenarios")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    from utils.ml import reset_model_registry
    from utils.agents import reset_default_tool_registry
    from utils.arena import reset_drill_ledger
    reset_simulation_clock(); reset_chaos_injector(); reset_macro_state()
    reset_model_registry(); reset_default_tool_registry()
    reset_drill_ledger()
    yield
    reset_simulation_clock(); reset_chaos_injector(); reset_macro_state()
    reset_model_registry(); reset_default_tool_registry()
    reset_drill_ledger()


# ── Module presence ─────────────────────────────────────────────────

def test_v10489_package_exists():
    pkg = REPO / "utils" / "uncertainty"
    assert pkg.is_dir()
    for f in ["__init__.py", "blackswan.py", "irrational.py",
                "time_corruption.py"]:
        assert (pkg / f).exists()


def test_v10489_exports_visible():
    from utils.uncertainty import (
        list_all_uncertainty_drills, list_blackswan_drills,
        list_irrational_drills, list_time_corruption_drills,
        run_irrational_drill, extreme_chaos_templates_added,
    )
    assert callable(run_irrational_drill)


# ── Counts ──────────────────────────────────────────────────────────

def test_v10489_has_15_black_swans():
    from utils.uncertainty import list_blackswan_drills
    assert len(list_blackswan_drills()) == 15


def test_v10489_has_8_irrational_drills():
    from utils.uncertainty import list_irrational_drills
    assert len(list_irrational_drills()) == 8


def test_v10489_has_10_time_corruption_drills():
    from utils.uncertainty import list_time_corruption_drills
    assert len(list_time_corruption_drills()) == 10


def test_v10489_total_33_drills():
    from utils.uncertainty import list_all_uncertainty_drills
    assert len(list_all_uncertainty_drills()) == 33


# ── CHAOS_LIBRARY extension ─────────────────────────────────────────

def test_v10489_chaos_library_extended_to_38():
    from utils.chaos import CHAOS_LIBRARY
    # Force import of blackswan to inject extras
    from utils.uncertainty import blackswan  # noqa: F401
    assert len(CHAOS_LIBRARY) >= 38


def test_v10489_extreme_chaos_templates_added():
    from utils.uncertainty import extreme_chaos_templates_added
    added = extreme_chaos_templates_added()
    assert len(added) == 13
    for name in ["cbk_emergency_hike_500bps_overnight",
                  "kes_devaluation_40pct_one_day",
                  "treasury_pricing_corruption"]:
        assert name in added


# ── Black swan drill sampling ───────────────────────────────────────

def test_v10489_black_swan_cbk_500bps_runs():
    from utils.uncertainty import get_blackswan_drill
    from utils.arena import DrillRunner
    drill = get_blackswan_drill("bs_cbk_500bps_overnight_hike")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_black_swan_kes_40pct_runs():
    from utils.uncertainty import get_blackswan_drill
    from utils.arena import DrillRunner
    drill = get_blackswan_drill("bs_kes_40pct_devaluation")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_black_swan_treasury_corruption_runs():
    from utils.uncertainty import get_blackswan_drill
    from utils.arena import DrillRunner
    drill = get_blackswan_drill("bs_treasury_pricing_corruption")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_black_swan_unknown_raises():
    from utils.uncertainty import get_blackswan_drill
    with pytest.raises(KeyError):
        get_blackswan_drill("does_not_exist")


# ── Irrational drill sampling ───────────────────────────────────────

def test_v10489_irrational_rapid_duplicate_clicks():
    from utils.uncertainty import run_irrational_drill
    result = run_irrational_drill("ir_rapid_duplicate_clicks")
    assert result.passed, result.failure_reasons
    assert result.agent_steps >= 5


def test_v10489_irrational_mass_action_20_submits():
    from utils.uncertainty import run_irrational_drill
    result = run_irrational_drill("ir_mass_action_mistake")
    assert result.passed
    summary = result.trajectory.tool_call_summary()
    assert summary.get("channel:submit", 0) == 20


def test_v10489_irrational_override_partial_success():
    """Override-attempt drill: 3 bogus calls should fail, 1 recovery should pass."""
    from utils.uncertainty import run_irrational_drill
    result = run_irrational_drill("ir_override_control_attempt")
    assert result.passed
    # The 3 bogus tools fail, the recovery chaos:list succeeds
    assert result.successful_agent_steps == 1
    assert result.agent_steps == 4


def test_v10489_irrational_concurrent_edits():
    from utils.uncertainty import run_irrational_drill
    result = run_irrational_drill("ir_conflicting_concurrent_edits")
    assert result.passed


def test_v10489_irrational_policy_factory_callable():
    from utils.uncertainty import (
        list_irrational_drills, get_irrational_policy_factory)
    for name in list_irrational_drills():
        policy_cls = get_irrational_policy_factory(name)
        assert callable(policy_cls)
        instance = policy_cls()
        assert hasattr(instance, "choose")


# ── Time corruption drill sampling ──────────────────────────────────

def test_v10489_tc_fiscal_year_crossover():
    from utils.uncertainty import get_time_corruption_drill
    from utils.arena import DrillRunner
    drill = get_time_corruption_drill("tc_fiscal_year_crossover")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_tc_leap_year():
    from utils.uncertainty import get_time_corruption_drill
    from utils.arena import DrillRunner
    drill = get_time_corruption_drill("tc_leap_year_feb29")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_tc_long_duration_90_days():
    from utils.uncertainty import get_time_corruption_drill
    from utils.arena import DrillRunner
    drill = get_time_corruption_drill("tc_long_duration_90_days")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_tc_midnight_precision():
    from utils.uncertainty import get_time_corruption_drill
    from utils.arena import DrillRunner
    drill = get_time_corruption_drill("tc_midnight_precision")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


def test_v10489_tc_triple_boundary():
    from utils.uncertainty import get_time_corruption_drill
    from utils.arena import DrillRunner
    drill = get_time_corruption_drill("tc_triple_boundary_eoq_eom")
    result = DrillRunner().run(drill)
    assert result.passed, result.failure_reasons


# ── Full battery ────────────────────────────────────────────────────

def test_v10489_full_battery_all_33_pass():
    """Run the entire v10.489 uncertainty battery (33 drills)."""
    from utils.uncertainty import (
        list_blackswan_drills, get_blackswan_drill,
        list_irrational_drills, run_irrational_drill,
        list_time_corruption_drills, get_time_corruption_drill,
    )
    from utils.arena import DrillRunner
    runner = DrillRunner()
    failures = []

    for name in list_blackswan_drills():
        r = runner.run(get_blackswan_drill(name))
        if not r.passed:
            failures.append((name, r.failure_reasons))
    for name in list_irrational_drills():
        r = run_irrational_drill(name)
        if not r.passed:
            failures.append((name, r.failure_reasons))
    for name in list_time_corruption_drills():
        r = runner.run(get_time_corruption_drill(name))
        if not r.passed:
            failures.append((name, r.failure_reasons))
    assert not failures, failures


# ── Determinism ─────────────────────────────────────────────────────

def test_v10489_black_swan_drill_reproducible():
    """Same black swan run twice → same trajectory."""
    from utils.uncertainty import get_blackswan_drill
    from utils.arena import DrillRunner
    drill = get_blackswan_drill("bs_cbk_500bps_overnight_hike")
    r1 = DrillRunner().run(drill)
    r2 = DrillRunner().run(drill)
    t1 = [(s.tool_name, s.result.success) for s in r1.trajectory.steps]
    t2 = [(s.tool_name, s.result.success) for s in r2.trajectory.steps]
    assert t1 == t2


def test_v10489_irrational_drill_reproducible():
    """Same irrational drill run twice → same trajectory."""
    from utils.uncertainty import run_irrational_drill
    r1 = run_irrational_drill("ir_mass_action_mistake")
    r2 = run_irrational_drill("ir_mass_action_mistake")
    assert r1.agent_steps == r2.agent_steps
    assert r1.successful_agent_steps == r2.successful_agent_steps


# ── G375 + cumulative regression ────────────────────────────────────

def test_v10489_g375_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10489_uncertainty_exposure_phase1
    r = gate_v10489_uncertainty_exposure_phase1()
    assert r["passed"], r.get("violations")


def test_v10489_prior_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10488_championship_readiness,
        gate_v10487_olympic_certification,
        gate_v10486_o7b_drill_scoring_replay,
        gate_v10485_o7a_training_arena,
    )
    for gate in (gate_v10488_championship_readiness,
                  gate_v10487_olympic_certification,
                  gate_v10486_o7b_drill_scoring_replay,
                  gate_v10485_o7a_training_arena):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10489_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

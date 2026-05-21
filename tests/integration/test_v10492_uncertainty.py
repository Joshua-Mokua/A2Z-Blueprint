"""Integration tests for v10.492 — Uncertainty exposure phase 4."""

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


# ── Module presence ─────────────────────────────────────────────────

def test_v10492_observability_module_exists():
    assert (REPO / "utils" / "uncertainty" / "observability.py").exists()


def test_v10492_regulator_module_exists():
    assert (REPO / "utils" / "uncertainty" / "regulator.py").exists()


def test_v10492_new_exports_visible():
    from utils.uncertainty import (
        list_observability_drills, run_observability_check,
        list_regulator_drills, run_regulator_drill,
    )
    assert callable(run_observability_check)
    assert callable(run_regulator_drill)


# ── Counts ──────────────────────────────────────────────────────────

def test_v10492_has_8_observability_checks():
    from utils.uncertainty import list_observability_drills
    assert len(list_observability_drills()) == 8


def test_v10492_has_7_regulator_drills():
    from utils.uncertainty import list_regulator_drills
    assert len(list_regulator_drills()) == 7


def test_v10492_total_81_drills():
    from utils.uncertainty import list_all_uncertainty_drills
    assert len(list_all_uncertainty_drills()) == 81


def test_v10492_cumulative_counts():
    from utils.uncertainty import list_all_uncertainty_drills
    names = list_all_uncertainty_drills()
    bs = sum(1 for n in names if n.startswith("bs_"))
    ir = sum(1 for n in names if n.startswith("ir_"))
    tc = sum(1 for n in names if n.startswith("tc_"))
    dp = sum(1 for n in names if n.startswith("dp_"))
    adv = sum(1 for n in names if n.startswith("adv_"))
    drift = sum(1 for n in names if n.startswith("drift_"))
    casc = sum(1 for n in names if n.startswith("casc_"))
    obs = sum(1 for n in names if n.startswith("obs_"))
    reg = sum(1 for n in names if n.startswith("reg_"))
    assert (bs, ir, tc, dp, adv, drift, casc, obs, reg) == (
        15, 8, 10, 10, 8, 8, 7, 8, 7
    )


# ── Observability check sampling ────────────────────────────────────

def test_v10492_obs_silent_channel_rejection():
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_silent_channel_rejection")
    assert ok, note
    assert metrics["failure_events"] >= 1


def test_v10492_obs_chaos_activation_telemetry():
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_chaos_activation_telemetry")
    assert ok, note
    assert metrics["chaos_events"] >= 3


def test_v10492_obs_macro_shock_telemetry_via_drift_path():
    """Macro events emitted through proper drift path."""
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_macro_shock_telemetry")
    assert ok, note
    # Honest finding documented
    assert metrics["direct_set_macro_state_emits"] is False
    assert metrics["blind_spot_documented"] is True


def test_v10492_obs_event_bus_saturation_zero_loss():
    """1000 events emitted, 0 dropped."""
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_event_bus_saturation_1000")
    assert ok, note
    assert metrics["loss"] == 0


def test_v10492_obs_correlation_id_propagation():
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_correlation_id_propagation")
    assert ok, note
    assert metrics["queried"] == 5


def test_v10492_obs_event_ordering_preserved():
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_event_ordering_preserved")
    assert ok, note
    assert metrics["all_present"] is True


def test_v10492_obs_tool_failure_visible():
    """Failed agent steps recorded in trajectory."""
    from utils.uncertainty import run_observability_check
    ok, note, metrics = run_observability_check(
        "obs_tool_failure_visible")
    assert ok, note
    assert metrics["failed_steps"] >= 2
    assert metrics["successful_steps"] >= 1


def test_v10492_obs_unknown_raises():
    from utils.uncertainty import run_observability_check
    with pytest.raises(KeyError):
        run_observability_check("does_not_exist")


def test_v10492_all_8_observability_checks_pass():
    from utils.uncertainty import (
        list_observability_drills, run_observability_check)
    failures = []
    for name in list_observability_drills():
        ok, note, _ = run_observability_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── Regulator drill sampling ────────────────────────────────────────

def test_v10492_reg_cbk_emergency_circular():
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_cbk_emergency_circular")
    assert r.passed, r.failure_reasons
    assert r.successful_agent_steps == 4


def test_v10492_reg_kra_audit_request():
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_kra_audit_request")
    assert r.passed, r.failure_reasons


def test_v10492_reg_aml_investigation():
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_aml_investigation")
    assert r.passed
    assert r.successful_agent_steps == 5


def test_v10492_reg_suspicious_freeze_activates_chaos():
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_suspicious_freeze")
    assert r.passed, r.failure_reasons
    summary = r.trajectory.tool_call_summary()
    assert "chaos:activate" in summary


def test_v10492_reg_cbk_inspection_6_step_extraction():
    """CBK on-site inspection requires 6 deep extraction calls."""
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_cbk_inspection")
    assert r.passed
    assert r.successful_agent_steps == 6


def test_v10492_reg_legal_hold_all_4_channels():
    """Legal hold preserves all 4 payment channel histories."""
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_legal_hold")
    assert r.passed
    summary = r.trajectory.tool_call_summary()
    assert summary.get("events:query", 0) == 5


def test_v10492_reg_ofac_sanctions_re_screening():
    from utils.uncertainty import run_regulator_drill
    r = run_regulator_drill("reg_ofac_sanctions_update")
    assert r.passed


def test_v10492_regulator_unknown_raises():
    from utils.uncertainty import get_regulator_drill
    with pytest.raises(KeyError):
        get_regulator_drill("does_not_exist")


def test_v10492_all_7_regulator_drills_pass():
    from utils.uncertainty import (
        list_regulator_drills, run_regulator_drill)
    failures = []
    for name in list_regulator_drills():
        r = run_regulator_drill(name)
        if not r.passed:
            failures.append((name, r.failure_reasons))
    assert not failures, failures


# ── Each policy callable ────────────────────────────────────────────

def test_v10492_each_regulator_policy_instantiable():
    from utils.uncertainty import (
        list_regulator_drills, get_regulator_policy_factory)
    for name in list_regulator_drills():
        pc = get_regulator_policy_factory(name)
        instance = pc()
        assert hasattr(instance, "choose")


# ── Reproducibility ─────────────────────────────────────────────────

def test_v10492_observability_check_reproducible():
    """Same observability check twice → same outcome."""
    from utils.uncertainty import run_observability_check
    ok1, _, _ = run_observability_check(
        "obs_correlation_id_propagation")
    ok2, _, _ = run_observability_check(
        "obs_correlation_id_propagation")
    assert ok1 == ok2


def test_v10492_regulator_drill_reproducible():
    from utils.uncertainty import run_regulator_drill
    r1 = run_regulator_drill("reg_cbk_inspection")
    r2 = run_regulator_drill("reg_cbk_inspection")
    assert r1.agent_steps == r2.agent_steps
    assert r1.successful_agent_steps == r2.successful_agent_steps


# ── G378 + cumulative regression ────────────────────────────────────

def test_v10492_g378_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10492_uncertainty_exposure_phase4
    r = gate_v10492_uncertainty_exposure_phase4()
    assert r["passed"], r.get("violations")


def test_v10492_prior_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10491_uncertainty_exposure_phase3,
        gate_v10490_uncertainty_exposure_phase2,
        gate_v10489_uncertainty_exposure_phase1,
        gate_v10488_championship_readiness,
    )
    for gate in (gate_v10491_uncertainty_exposure_phase3,
                  gate_v10490_uncertainty_exposure_phase2,
                  gate_v10489_uncertainty_exposure_phase1,
                  gate_v10488_championship_readiness):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10492_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

"""Integration tests for v10.491 — Uncertainty exposure phase 3."""

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

def test_v10491_drift_module_exists():
    assert (REPO / "utils" / "uncertainty" / "drift.py").exists()


def test_v10491_cascade_module_exists():
    assert (REPO / "utils" / "uncertainty" / "cascade.py").exists()


def test_v10491_new_exports_visible():
    from utils.uncertainty import (
        list_drift_drills, run_drift_check,
        list_cascade_drills, measure_blast_radius,
    )
    assert callable(run_drift_check)
    assert callable(measure_blast_radius)


# ── Counts ──────────────────────────────────────────────────────────

def test_v10491_has_8_drift_drills():
    from utils.uncertainty import list_drift_drills
    assert len(list_drift_drills()) == 8


def test_v10491_has_7_cascade_drills():
    from utils.uncertainty import list_cascade_drills
    assert len(list_cascade_drills()) == 7


def test_v10491_total_66_drills():
    from utils.uncertainty import list_all_uncertainty_drills
    assert len(list_all_uncertainty_drills()) == 66


def test_v10491_cumulative_counts():
    from utils.uncertainty import list_all_uncertainty_drills
    names = list_all_uncertainty_drills()
    bs = sum(1 for n in names if n.startswith("bs_"))
    ir = sum(1 for n in names if n.startswith("ir_"))
    tc = sum(1 for n in names if n.startswith("tc_"))
    dp = sum(1 for n in names if n.startswith("dp_"))
    adv = sum(1 for n in names if n.startswith("adv_"))
    drift = sum(1 for n in names if n.startswith("drift_"))
    casc = sum(1 for n in names if n.startswith("casc_"))
    assert (bs, ir, tc, dp, adv, drift, casc) == (15, 8, 10, 10, 8, 8, 7)


# ── Drift drill sampling ────────────────────────────────────────────

def test_v10491_drift_12mo_macro_sweep():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_macro_12mo_sweep")
    assert ok, note
    assert metrics["deterministic"] is True


def test_v10491_drift_60mo_macro_sweep():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_macro_60mo_sweep")
    assert ok, note
    assert metrics["deterministic"] is True
    # Final state must stay in plausible Kenya bounds
    assert -0.01 <= metrics["final_cbr"] <= 0.30
    assert 50 <= metrics["final_usd_kes"] <= 500


def test_v10491_drift_continuous_chaos_90d():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_continuous_chaos_90d")
    assert ok, note
    assert metrics["activations"] == 13  # weekly for 13 weeks
    assert metrics["library_growth"] == 0  # no unbounded growth


def test_v10491_drift_ledger_100_runs_single_digest():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_ledger_1000_runs")
    assert ok, note
    assert metrics["total_runs"] == 100
    assert metrics["distinct_digests"] == 1


def test_v10491_drift_digest_stability_3x():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_digest_stability_3x")
    assert ok, note
    assert metrics["runs"] == 3
    assert metrics["distinct_digests"] == 1


def test_v10491_drift_ml_staleness_6mo():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_ml_staleness_6mo")
    assert ok, note
    assert metrics["identical"] is True


def test_v10491_drift_yoy_cascade_replay():
    from utils.uncertainty import run_drift_check
    ok, note, metrics = run_drift_check("drift_yoy_cascade_replay")
    assert ok, note
    assert metrics["same_digest"] is True


def test_v10491_drift_unknown_raises():
    from utils.uncertainty import get_drift_drill, run_drift_check
    with pytest.raises(KeyError):
        get_drift_drill("does_not_exist")
    with pytest.raises(KeyError):
        run_drift_check("does_not_exist")


# ── Cascade drill sampling ──────────────────────────────────────────

def test_v10491_cascade_api_to_rtgs_to_kic():
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    r = DrillRunner().run(get_cascade_drill("casc_api_outage_to_rtgs_to_kic"))
    assert r.passed, r.failure_reasons
    assert len(r.environment_fired) == 3


def test_v10491_cascade_treasury_to_fx_to_swift():
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    r = DrillRunner().run(
        get_cascade_drill("casc_treasury_to_fx_to_swift"))
    assert r.passed, r.failure_reasons
    assert len(r.environment_fired) == 3


def test_v10491_cascade_macro_to_credit():
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    r = DrillRunner().run(
        get_cascade_drill("casc_macro_shock_to_credit_shock"))
    assert r.passed, r.failure_reasons


def test_v10491_cascade_mpesa_to_ussd_to_atm():
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    r = DrillRunner().run(get_cascade_drill("casc_mpesa_to_ussd_to_atm"))
    assert r.passed, r.failure_reasons


def test_v10491_cascade_ai_corruption_to_decision_failure():
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    r = DrillRunner().run(
        get_cascade_drill("casc_ai_corruption_to_decision_failure"))
    assert r.passed, r.failure_reasons


def test_v10491_cascade_fraud_to_outage_to_freeze():
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    r = DrillRunner().run(
        get_cascade_drill("casc_fraud_to_outage_to_freeze"))
    assert r.passed, r.failure_reasons


def test_v10491_cascade_mega_5_stages():
    """The 5-stage mega cascade fires all 5 stages in order."""
    from utils.uncertainty import (
        get_cascade_drill, measure_blast_radius)
    from utils.arena import DrillRunner
    r = DrillRunner().run(get_cascade_drill("casc_mega_5_stage_collapse"))
    assert r.passed, r.failure_reasons
    assert len(r.environment_fired) == 5
    blast = measure_blast_radius("casc_mega_5_stage_collapse")
    assert blast["stages_planned"] == 5


def test_v10491_cascade_blast_radius_for_all():
    from utils.uncertainty import (
        list_cascade_drills, measure_blast_radius)
    for name in list_cascade_drills():
        br = measure_blast_radius(name)
        assert br["stages_planned"] >= 3, name


def test_v10491_cascade_unknown_raises():
    from utils.uncertainty import get_cascade_drill, measure_blast_radius
    with pytest.raises(KeyError):
        get_cascade_drill("does_not_exist")
    with pytest.raises(KeyError):
        measure_blast_radius("does_not_exist")


# ── Reproducibility ─────────────────────────────────────────────────

def test_v10491_drift_check_reproducible():
    """Same drift check twice → same metrics."""
    from utils.uncertainty import run_drift_check
    ok1, _, m1 = run_drift_check("drift_macro_12mo_sweep")
    ok2, _, m2 = run_drift_check("drift_macro_12mo_sweep")
    assert ok1 and ok2
    assert m1["final_cbr"] == m2["final_cbr"]
    assert m1["final_usd_kes"] == m2["final_usd_kes"]


def test_v10491_cascade_drill_reproducible():
    """Same cascade drill twice → same firing sequence."""
    from utils.uncertainty import get_cascade_drill
    from utils.arena import DrillRunner
    runner = DrillRunner()
    r1 = runner.run(get_cascade_drill("casc_api_outage_to_rtgs_to_kic"))
    r2 = runner.run(get_cascade_drill("casc_api_outage_to_rtgs_to_kic"))
    assert r1.environment_fired == r2.environment_fired


# ── Full battery cumulative ─────────────────────────────────────────

def test_v10491_full_15_new_drills_pass():
    """All 8 drift + 7 cascade drills via DrillRunner."""
    from utils.uncertainty import (
        list_drift_drills, get_drift_drill,
        list_cascade_drills, get_cascade_drill,
    )
    from utils.arena import DrillRunner
    runner = DrillRunner()
    failures = []
    for n in list_drift_drills():
        if not runner.run(get_drift_drill(n)).passed:
            failures.append(n)
    for n in list_cascade_drills():
        if not runner.run(get_cascade_drill(n)).passed:
            failures.append(n)
    assert not failures, failures


def test_v10491_all_8_drift_checks_pass():
    """All 8 deeper drift check functions return ok."""
    from utils.uncertainty import list_drift_drills, run_drift_check
    failures = []
    for n in list_drift_drills():
        ok, note, _ = run_drift_check(n)
        if not ok:
            failures.append((n, note))
    assert not failures, failures


# ── G377 + cumulative regression ────────────────────────────────────

def test_v10491_g377_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10491_uncertainty_exposure_phase3
    r = gate_v10491_uncertainty_exposure_phase3()
    assert r["passed"], r.get("violations")


def test_v10491_prior_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10490_uncertainty_exposure_phase2,
        gate_v10489_uncertainty_exposure_phase1,
        gate_v10488_championship_readiness,
    )
    for gate in (gate_v10490_uncertainty_exposure_phase2,
                  gate_v10489_uncertainty_exposure_phase1,
                  gate_v10488_championship_readiness):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10491_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

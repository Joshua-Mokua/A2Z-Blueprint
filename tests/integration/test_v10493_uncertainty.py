"""Integration tests for v10.493 — Uncertainty exposure phase 5."""

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

def test_v10493_frontend_module_exists():
    assert (REPO / "utils" / "uncertainty" / "frontend.py").exists()


def test_v10493_cognitive_module_exists():
    assert (REPO / "utils" / "uncertainty" / "cognitive.py").exists()


def test_v10493_react_impact_module_exists():
    assert (REPO / "utils" / "uncertainty" / "react_impact.py").exists()


def test_v10493_new_exports_visible():
    from utils.uncertainty import (
        list_frontend_drills, run_frontend_check,
        list_cognitive_drills, run_cognitive_check,
        list_react_impact_drills, run_react_impact_check,
        cognitive_track_c_deferred,
    )
    assert callable(run_frontend_check)
    assert callable(run_cognitive_check)
    assert callable(run_react_impact_check)
    assert callable(cognitive_track_c_deferred)


# ── Counts ──────────────────────────────────────────────────────────

def test_v10493_has_8_frontend_drills():
    from utils.uncertainty import list_frontend_drills
    assert len(list_frontend_drills()) == 8


def test_v10493_has_5_cognitive_drills():
    from utils.uncertainty import list_cognitive_drills
    assert len(list_cognitive_drills()) == 5


def test_v10493_has_7_react_impact_drills():
    from utils.uncertainty import list_react_impact_drills
    assert len(list_react_impact_drills()) == 7


def test_v10493_total_101_drills():
    from utils.uncertainty import list_all_uncertainty_drills
    assert len(list_all_uncertainty_drills()) == 101


def test_v10493_cumulative_counts():
    from utils.uncertainty import list_all_uncertainty_drills
    names = list_all_uncertainty_drills()
    counts = {
        "bs_": sum(1 for n in names if n.startswith("bs_")),
        "ir_": sum(1 for n in names if n.startswith("ir_")),
        "tc_": sum(1 for n in names if n.startswith("tc_")),
        "dp_": sum(1 for n in names if n.startswith("dp_")),
        "adv_": sum(1 for n in names if n.startswith("adv_")),
        "drift_": sum(1 for n in names if n.startswith("drift_")),
        "casc_": sum(1 for n in names if n.startswith("casc_")),
        "obs_": sum(1 for n in names if n.startswith("obs_")),
        "reg_": sum(1 for n in names if n.startswith("reg_")),
        "fe_": sum(1 for n in names if n.startswith("fe_")),
        "cog_": sum(1 for n in names if n.startswith("cog_")),
        "react_": sum(1 for n in names if n.startswith("react_")),
    }
    assert counts == {
        "bs_": 15, "ir_": 8, "tc_": 10, "dp_": 10, "adv_": 8,
        "drift_": 8, "casc_": 7, "obs_": 8, "reg_": 7,
        "fe_": 8, "cog_": 5, "react_": 7,
    }


# ── Frontend pressure sampling ──────────────────────────────────────

def test_v10493_fe_concurrent_tool_invocations_100():
    from utils.uncertainty import run_frontend_check
    ok, note, metrics = run_frontend_check(
        "fe_concurrent_tool_invocations_100")
    assert ok, note
    assert metrics["successes"] == 100
    assert metrics["errors"] == 0


def test_v10493_fe_sequential_burst_500_honest_failure_rate():
    """500 sequential submits with M-Pesa realistic ~5-8% failure rate."""
    from utils.uncertainty import run_frontend_check
    ok, note, metrics = run_frontend_check(
        "fe_sequential_channel_burst_500")
    assert ok, note
    # All 500 must complete (success or labelled failure)
    assert metrics["completions"] == 500
    assert metrics["successes"] + metrics["labelled_failures"] == 500
    # Throughput must be reasonable
    assert metrics["throughput_per_sec"] > 100
    # Honest finding documented
    assert "honest_finding" in metrics


def test_v10493_fe_large_pagination_10k():
    from utils.uncertainty import run_frontend_check
    ok, note, metrics = run_frontend_check(
        "fe_large_pagination_event_query")
    assert ok, note
    assert metrics["duration_sec"] < 10


def test_v10493_fe_5_concurrent_agents():
    from utils.uncertainty import run_frontend_check
    ok, note, metrics = run_frontend_check("fe_concurrent_agents_5")
    assert ok, note
    assert metrics["completed"] == 5
    assert metrics["errors"] == 0


def test_v10493_fe_polling_overload():
    from utils.uncertainty import run_frontend_check
    ok, note, metrics = run_frontend_check(
        "fe_polling_overload_50_per_sec")
    assert ok, note
    assert metrics["successes"] == 50


def test_v10493_fe_cache_invalidation_race_no_corruption():
    """Concurrent reader/writer threads — 100% of reads consistent."""
    from utils.uncertainty import run_frontend_check
    ok, note, metrics = run_frontend_check("fe_cache_invalidation_race")
    assert ok, note
    assert metrics["reads"] > 0
    assert metrics["consistent"] == metrics["reads"]
    assert metrics["writes"] == 100


def test_v10493_all_8_frontend_checks_pass():
    from utils.uncertainty import (
        list_frontend_drills, run_frontend_check)
    failures = []
    for name in list_frontend_drills():
        ok, note, _ = run_frontend_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── Cognitive load sampling ─────────────────────────────────────────

def test_v10493_cog_alert_flood_10():
    from utils.uncertainty import run_cognitive_check
    ok, note, metrics = run_cognitive_check(
        "cog_alert_flood_10_simultaneous")
    assert ok, note
    assert metrics["active_count"] >= 10
    assert metrics["have_severity"] == metrics["active_count"]


def test_v10493_cog_kpi_conflict_signal():
    """Contradictory macro signals (CBR up + FX down) both visible."""
    from utils.uncertainty import run_cognitive_check
    ok, note, metrics = run_cognitive_check("cog_kpi_conflict_signal")
    assert ok, note
    assert metrics["cbr_rose"] is True
    assert metrics["fx_devalued"] is True
    assert metrics["both_visible_to_ui"] is True


def test_v10493_cog_dashboard_aggregation_under_2s():
    """Dashboard query latency under 2 second budget; Track-C optimisation noted."""
    from utils.uncertainty import run_cognitive_check
    ok, note, metrics = run_cognitive_check(
        "cog_dashboard_aggregation_tractability")
    assert ok, note
    assert metrics["duration_ms"] < 2000
    assert "track_c_optimization" in metrics


def test_v10493_cog_track_c_deferred_4_items():
    """4 cognitive-load items honestly deferred to Track-C."""
    from utils.uncertainty import cognitive_track_c_deferred
    deferred = cognitive_track_c_deferred()
    assert len(deferred) == 4
    for item in deferred:
        assert "item" in item
        assert "reason" in item
        assert "addresses_via" in item


def test_v10493_all_5_cognitive_checks_pass():
    from utils.uncertainty import (
        list_cognitive_drills, run_cognitive_check)
    failures = []
    for name in list_cognitive_drills():
        ok, note, _ = run_cognitive_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── React impact sampling ───────────────────────────────────────────

def test_v10493_react_api_amplification_5x():
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_api_amplification_5x")
    assert ok, note
    assert metrics["successes"] == 5


def test_v10493_react_concurrent_sessions_10():
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_concurrent_sessions_10")
    assert ok, note
    assert metrics["completed"] == 10


def test_v10493_react_polling_burst_5_tabs():
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_polling_burst_5_tabs")
    assert ok, note
    assert metrics["successes"] == 100  # 5 tabs × 20 polls


def test_v10493_react_dashboard_refresh_storm():
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_dashboard_refresh_storm")
    assert ok, note
    assert metrics["successes"] == 50


def test_v10493_react_client_retry_storm_cleanly_fails():
    """5 retries against a known-bad target all cleanly fail."""
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_client_retry_storm_5x")
    assert ok, note
    assert metrics["cleanly_failed"] == 5


def test_v10493_react_optimistic_updates_5_parallel():
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_optimistic_updates_5_parallel")
    assert ok, note
    assert metrics["completions"] == 5


def test_v10493_react_component_tree_fanout_8():
    from utils.uncertainty import run_react_impact_check
    ok, note, metrics = run_react_impact_check(
        "react_component_tree_fanout_8")
    assert ok, note
    assert metrics["successes"] == 8


def test_v10493_all_7_react_impact_checks_pass():
    from utils.uncertainty import (
        list_react_impact_drills, run_react_impact_check)
    failures = []
    for name in list_react_impact_drills():
        ok, note, _ = run_react_impact_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── Unknown name handling ───────────────────────────────────────────

def test_v10493_unknown_check_raises():
    from utils.uncertainty import (
        run_frontend_check, run_cognitive_check,
        run_react_impact_check)
    for fn in (run_frontend_check, run_cognitive_check,
                run_react_impact_check):
        with pytest.raises(KeyError):
            fn("does_not_exist")


# ── G379 + cumulative regression ────────────────────────────────────

def test_v10493_g379_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10493_uncertainty_exposure_phase5
    r = gate_v10493_uncertainty_exposure_phase5()
    assert r["passed"], r.get("violations")


def test_v10493_prior_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10492_uncertainty_exposure_phase4,
        gate_v10491_uncertainty_exposure_phase3,
        gate_v10490_uncertainty_exposure_phase2,
        gate_v10489_uncertainty_exposure_phase1,
        gate_v10488_championship_readiness,
    )
    for gate in (gate_v10492_uncertainty_exposure_phase4,
                  gate_v10491_uncertainty_exposure_phase3,
                  gate_v10490_uncertainty_exposure_phase2,
                  gate_v10489_uncertainty_exposure_phase1,
                  gate_v10488_championship_readiness):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10493_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

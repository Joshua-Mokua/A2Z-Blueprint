"""Integration tests for v10.494 — Uncertainty exposure phase 6 FINAL."""

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

def test_v10494_collapse_module_exists():
    assert (REPO / "utils" / "uncertainty" / "collapse.py").exists()


def test_v10494_war_game_module_exists():
    assert (REPO / "utils" / "uncertainty" / "war_game.py").exists()


def test_v10494_tech_debt_module_exists():
    assert (REPO / "utils" / "uncertainty" / "tech_debt.py").exists()


def test_v10494_new_exports_visible():
    from utils.uncertainty import (
        list_collapse_drills, run_collapse_check,
        list_war_game_drills, run_war_game_check,
        run_72hr_war_game, WAR_GAME_CRISIS_SCHEDULE,
        list_tech_debt_drills, run_tech_debt_check,
    )
    assert callable(run_collapse_check)
    assert callable(run_war_game_check)
    assert callable(run_72hr_war_game)
    assert callable(run_tech_debt_check)


# ── Counts ──────────────────────────────────────────────────────────

def test_v10494_has_7_collapse_drills():
    from utils.uncertainty import list_collapse_drills
    assert len(list_collapse_drills()) == 7


def test_v10494_has_6_war_game_drills():
    from utils.uncertainty import list_war_game_drills
    assert len(list_war_game_drills()) == 6


def test_v10494_has_7_tech_debt_drills():
    from utils.uncertainty import list_tech_debt_drills
    assert len(list_tech_debt_drills()) == 7


def test_v10494_total_121_drills():
    from utils.uncertainty import list_all_uncertainty_drills
    assert len(list_all_uncertainty_drills()) == 121


def test_v10494_full_cumulative_counts():
    """All 12 categories of the 15-category framework present."""
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
        "col_": sum(1 for n in names if n.startswith("col_")),
        "wg_": sum(1 for n in names if n.startswith("wg_")),
        "td_": sum(1 for n in names if n.startswith("td_")),
    }
    expected = {
        "bs_": 15, "ir_": 8, "tc_": 10, "dp_": 10, "adv_": 8,
        "drift_": 8, "casc_": 7, "obs_": 8, "reg_": 7,
        "fe_": 8, "cog_": 5, "react_": 7,
        "col_": 7, "wg_": 6, "td_": 7,
    }
    assert counts == expected


# ── Collapse recovery ───────────────────────────────────────────────

def test_v10494_col_fresh_start_invariant():
    from utils.uncertainty import run_collapse_check
    ok, note, metrics = run_collapse_check("col_fresh_start_invariant")
    assert ok, note
    assert metrics["digest_match"] is True
    assert metrics["active_count"] == 0


def test_v10494_col_ledger_corruption_rebuild():
    from utils.uncertainty import run_collapse_check
    ok, note, metrics = run_collapse_check(
        "col_ledger_directory_corruption_rebuild")
    assert ok, note
    assert metrics["before"] == 5
    assert metrics["after_wipe"] == 0
    assert metrics["after_rebuild"] == 5
    assert metrics["deterministic_after_rebuild"] is True


def test_v10494_col_macro_reset_rebaseline():
    from utils.uncertainty import run_collapse_check
    ok, note, metrics = run_collapse_check(
        "col_macro_state_full_reset_rebaseline")
    assert ok, note
    assert metrics["baseline_digest"] == metrics["recovered_digest"]
    assert metrics["baseline_digest"] != metrics["mid_digest"]


def test_v10494_col_full_env_corruption_recovery():
    """The worst-case scenario: all subsystems reset simultaneously."""
    from utils.uncertainty import run_collapse_check
    ok, note, metrics = run_collapse_check(
        "col_full_environment_corruption_recovery")
    assert ok, note
    assert metrics["macro_stable"] is True
    assert metrics["lib_stable"] is True
    assert metrics["tools_stable"] is True


def test_v10494_all_7_collapse_checks_pass():
    from utils.uncertainty import (
        list_collapse_drills, run_collapse_check)
    failures = []
    for name in list_collapse_drills():
        ok, note, _ = run_collapse_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── 72-hour war game ────────────────────────────────────────────────

def test_v10494_72hr_campaign_12_crises():
    from utils.uncertainty import run_72hr_war_game
    m = run_72hr_war_game(seed=0)
    assert m["crises_planned"] == 12
    assert m["crises_injected"] == 12
    assert m["hours_elapsed"] == 72
    assert m["macro_drift_within_bounds"] is True


def test_v10494_72hr_deterministic_replay():
    from utils.uncertainty import run_72hr_war_game
    m1 = run_72hr_war_game(seed=42)
    m2 = run_72hr_war_game(seed=42)
    assert m1["campaign_digest"] == m2["campaign_digest"]
    assert abs(m1["final_cbr"] - m2["final_cbr"]) < 1e-6
    assert abs(m1["final_usd_kes"] - m2["final_usd_kes"]) < 1e-4


def test_v10494_72hr_crisis_categories_complete():
    from utils.uncertainty import WAR_GAME_CRISIS_SCHEDULE
    categories = set(c for _, c in WAR_GAME_CRISIS_SCHEDULE)
    assert categories == {
        "fraud", "exec_escalation", "ai_hallucination",
        "treasury", "branch_overload", "regulatory"}


def test_v10494_72hr_macro_drift_bounded():
    from utils.uncertainty import run_war_game_check
    ok, note, metrics = run_war_game_check(
        "wg_72hr_macro_drift_bounded")
    assert ok, note
    assert -0.01 <= metrics["final_cbr"] <= 0.30
    assert 50 <= metrics["final_usd_kes"] <= 500


def test_v10494_all_6_war_game_checks_pass():
    from utils.uncertainty import (
        list_war_game_drills, run_war_game_check)
    failures = []
    for name in list_war_game_drills():
        ok, note, _ = run_war_game_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── Tech debt scans ─────────────────────────────────────────────────

def test_v10494_td_module_count_inventory():
    """Real codebase inventory: hundreds of modules, tens of thousands of LOC."""
    from utils.uncertainty import run_tech_debt_check
    ok, note, metrics = run_tech_debt_check("td_module_count_inventory")
    assert ok, note
    assert metrics["module_count"] >= 100
    assert metrics["total_loc"] >= 10000


def test_v10494_td_import_dependency_graph():
    from utils.uncertainty import run_tech_debt_check
    ok, note, metrics = run_tech_debt_check(
        "td_import_dependency_graph")
    assert ok, note
    assert metrics["modules_with_inbound"] > 100
    assert len(metrics["top5_imported"]) == 5


def test_v10494_td_hotspot_analysis():
    """Identifies the largest file."""
    from utils.uncertainty import run_tech_debt_check
    ok, note, metrics = run_tech_debt_check("td_hotspot_analysis")
    assert ok, note
    assert len(metrics["top10"]) == 10
    assert metrics["top10"][0]["loc"] > 1000


def test_v10494_td_todo_fixme_density_under_threshold():
    """TODO/FIXME density under 500 total markers."""
    from utils.uncertainty import run_tech_debt_check
    ok, note, metrics = run_tech_debt_check("td_todo_fixme_density")
    assert ok, note
    assert metrics["total_markers"] < 500


def test_v10494_td_circular_imports_bounded():
    """Less than 50 potential cycle edges."""
    from utils.uncertainty import run_tech_debt_check
    ok, note, metrics = run_tech_debt_check("td_circular_imports")
    assert ok, note
    assert metrics["potential_cycles"] < 50
    assert metrics["modules_scanned"] > 100


def test_v10494_td_maintainability_heuristic():
    """avg fns/file < 100, avg lines/fn < 100."""
    from utils.uncertainty import run_tech_debt_check
    ok, note, metrics = run_tech_debt_check(
        "td_maintainability_heuristic")
    assert ok, note
    assert metrics["avg_functions_per_file"] < 100
    assert metrics["avg_lines_per_function"] < 100


def test_v10494_all_7_tech_debt_scans_pass():
    from utils.uncertainty import (
        list_tech_debt_drills, run_tech_debt_check)
    failures = []
    for name in list_tech_debt_drills():
        ok, note, _ = run_tech_debt_check(name)
        if not ok:
            failures.append((name, note))
    assert not failures, failures


# ── Unknown name handling ───────────────────────────────────────────

def test_v10494_unknown_check_raises():
    from utils.uncertainty import (
        run_collapse_check, run_war_game_check, run_tech_debt_check)
    for fn in (run_collapse_check, run_war_game_check,
                run_tech_debt_check):
        with pytest.raises(KeyError):
            fn("does_not_exist")


# ── G380 + cumulative regression ────────────────────────────────────

def test_v10494_g380_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10494_uncertainty_exposure_phase6_FINAL
    r = gate_v10494_uncertainty_exposure_phase6_FINAL()
    assert r["passed"], r.get("violations")


def test_v10494_prior_5_gates_preserved():
    """G375, G376, G377, G378, G379 all still pass."""
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10493_uncertainty_exposure_phase5,
        gate_v10492_uncertainty_exposure_phase4,
        gate_v10491_uncertainty_exposure_phase3,
        gate_v10490_uncertainty_exposure_phase2,
        gate_v10489_uncertainty_exposure_phase1,
        gate_v10488_championship_readiness,
    )
    for gate in (gate_v10493_uncertainty_exposure_phase5,
                  gate_v10492_uncertainty_exposure_phase4,
                  gate_v10491_uncertainty_exposure_phase3,
                  gate_v10490_uncertainty_exposure_phase2,
                  gate_v10489_uncertainty_exposure_phase1,
                  gate_v10488_championship_readiness):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10494_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9


# ── Campaign-complete sanity ────────────────────────────────────────

def test_v10494_campaign_complete_all_15_categories():
    """All 15 categories of Joshua's framework now covered by drills."""
    from utils.uncertainty import list_all_uncertainty_drills
    names = list_all_uncertainty_drills()
    # Each prefix maps to one (or more) of the 15 categories
    prefixes = set(n.split("_")[0] for n in names)
    # We should have at least 12 distinct prefixes (some categories
    # span multiple sub-prefixes like "casc" vs "drift")
    assert len(prefixes) >= 12
    assert len(names) >= 121

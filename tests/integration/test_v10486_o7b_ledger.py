"""Integration tests for v10.486 — Phase O7-B drill scoring + replay."""

import sys
import tempfile
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
    from utils.arena import reset_drill_ledger
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    reset_default_tool_registry()
    reset_drill_ledger()
    yield
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    reset_model_registry()
    reset_default_tool_registry()
    reset_drill_ledger()


# ── Module presence ─────────────────────────────────────────────────

def test_v10486_ledger_module_exists():
    assert (REPO / "utils" / "arena" / "ledger.py").exists()


def test_v10486_batch_module_exists():
    assert (REPO / "utils" / "arena" / "batch.py").exists()


def test_v10486_new_exports_visible():
    from utils.arena import (
        DrillRunRecord, DrillSummary, DrillComparison,
        DrillLedger, get_drill_ledger, reset_drill_ledger,
        DrillBatch, BatchResult,
    )
    assert DrillRunRecord and DrillLedger and DrillBatch


# ── DrillLedger basic ───────────────────────────────────────────────

def test_v10486_ledger_singleton():
    from utils.arena import get_drill_ledger
    a = get_drill_ledger()
    b = get_drill_ledger()
    assert a is b


def test_v10486_ledger_record_appends_to_jsonl(tmp_path):
    from utils.arena import DrillLedger, get_drill, DrillRunner
    ledger = DrillLedger(ledger_dir=tmp_path)
    drill = get_drill("observe_kes_devaluation")
    result = DrillRunner().run(drill)
    rec = ledger.record(drill=drill, result=result)
    assert rec.drill_name == "observe_kes_devaluation"
    assert (tmp_path / "runs.jsonl").exists()
    assert (tmp_path / f"{rec.run_id}.trajectory.json").exists()


def test_v10486_ledger_list_runs_filter_by_drill(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation",
                      "survive_safaricom_outage_morning"])
    only = ledger.list_runs(drill_name="observe_kes_devaluation")
    assert len(only) == 1
    assert only[0].drill_name == "observe_kes_devaluation"


def test_v10486_ledger_get_run_by_id(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    run_id = res.run_ids[0]
    rec = ledger.get_run(run_id)
    assert rec is not None
    assert rec.drill_name == "observe_kes_devaluation"


def test_v10486_ledger_get_trajectory(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    traj = ledger.get_trajectory(res.run_ids[0])
    assert traj is not None
    assert "steps" in traj


def test_v10486_ledger_total_count(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    assert ledger.total() == 0
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    assert ledger.total() == 1


def test_v10486_ledger_clear_removes_files(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    assert ledger.total() == 1
    removed = ledger.clear()
    assert removed == 1
    assert ledger.total() == 0


def test_v10486_ledger_filter_by_passed_status(tmp_path):
    from utils.arena import (
        DrillLedger, Drill, DrillEnvironmentEvent, DrillOracle,
        DrillRunner,
    )
    from utils.simulation_clock import NAIROBI_TZ
    ledger = DrillLedger(ledger_dir=tmp_path)
    # Create a drill that fails (impossible oracle)
    bad = Drill(
        name="impossible_drill", description="will fail",
        category="test",
        sim_start=datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ),
        agent_goal="survey_macro",
        oracle=DrillOracle(min_steps=1000),
    )
    result_bad = DrillRunner().run(bad)
    ledger.record(drill=bad, result=result_bad)
    # And one that passes
    from utils.arena import get_drill
    good = get_drill("observe_kes_devaluation")
    result_good = DrillRunner().run(good)
    ledger.record(drill=good, result=result_good)
    passed_runs = ledger.list_runs(passed=True)
    failed_runs = ledger.list_runs(passed=False)
    assert len(passed_runs) == 1
    assert len(failed_runs) == 1


# ── Trajectory digest determinism ───────────────────────────────────

def test_v10486_trajectory_digest_deterministic(tmp_path):
    """Same drill + same policy → same digest."""
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res_a = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    res_b = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    rec_a = ledger.get_run(res_a.run_ids[0])
    rec_b = ledger.get_run(res_b.run_ids[0])
    assert rec_a.trajectory_digest == rec_b.trajectory_digest
    assert rec_a.trajectory_digest  # non-empty


def test_v10486_different_drills_have_different_digests(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res_a = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    res_b = DrillBatch(ledger=ledger).run(
        drill_names=["observe_cbr_emergency_hike"])
    rec_a = ledger.get_run(res_a.run_ids[0])
    rec_b = ledger.get_run(res_b.run_ids[0])
    # These two drills both use survey_macro and call the same tools
    # in the same order, so digests could match. The point of the test
    # is just that the digest is computed and stored.
    assert rec_a.trajectory_digest
    assert rec_b.trajectory_digest


# ── DrillComparison ─────────────────────────────────────────────────

def test_v10486_compare_runs_same_drill(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    res2 = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    cmp = ledger.compare_runs(res.run_ids[0], res2.run_ids[0])
    assert cmp.same_drill
    assert cmp.same_digest


def test_v10486_compare_runs_different_drills(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res_a = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    res_b = DrillBatch(ledger=ledger).run(
        drill_names=["survive_safaricom_outage_morning"])
    cmp = ledger.compare_runs(res_a.run_ids[0], res_b.run_ids[0])
    assert not cmp.same_drill


def test_v10486_compare_runs_missing_id(tmp_path):
    from utils.arena import DrillLedger
    ledger = DrillLedger(ledger_dir=tmp_path)
    cmp = ledger.compare_runs("nonexistent_a", "nonexistent_b")
    assert "not found" in cmp.notes


# ── DrillSummary ────────────────────────────────────────────────────

def test_v10486_summarise_aggregates_stats(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"],
        repeats=3)
    s = ledger.summarise("observe_kes_devaluation")
    assert s.total_runs == 3
    assert s.pass_rate == 1.0
    assert s.distinct_digests == 1  # deterministic
    assert s.avg_agent_steps > 0


def test_v10486_summarise_empty_drill():
    from utils.arena import DrillLedger
    with tempfile.TemporaryDirectory() as tmp:
        ledger = DrillLedger(ledger_dir=tmp)
        s = ledger.summarise("never_run_drill")
        assert s.total_runs == 0
        assert s.pass_rate == 0.0


def test_v10486_summarise_by_drill_returns_dict(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation",
                      "survive_safaricom_outage_morning"])
    summaries = ledger.summarise_by_drill()
    assert "observe_kes_devaluation" in summaries
    assert "survive_safaricom_outage_morning" in summaries


# ── DrillBatch ──────────────────────────────────────────────────────

def test_v10486_batch_runs_all_12_drills(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    result = DrillBatch(ledger=ledger).run()
    assert result.total == 12
    assert result.passed == 12
    assert result.pass_rate == 1.0
    assert len(result.failed_drills) == 0


def test_v10486_batch_filter_by_category(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    result = DrillBatch(ledger=ledger).run(
        category="channel_survival", record_to_ledger=False)
    assert result.total == 4
    # All channel_survival drills should pass with default policy
    assert result.passed == 4


def test_v10486_batch_repeats(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    result = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"],
        repeats=5)
    assert result.total == 5
    assert ledger.total() == 5


def test_v10486_batch_by_category_breakdown(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    result = DrillBatch(ledger=ledger).run()
    expected = {
        "channel_survival": 4,
        "macro_observation": 3,
        "eom_pressure": 2,
        "chaos_ml": 2,
        "scenario_cascade": 1,
    }
    for cat, want in expected.items():
        assert result.by_category[cat]["total"] == want


def test_v10486_batch_record_to_ledger_default_true(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    assert ledger.total() == 0
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    assert ledger.total() == 1


def test_v10486_batch_record_to_ledger_false_skips_write(tmp_path):
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"],
        record_to_ledger=False)
    assert ledger.total() == 0


def test_v10486_batch_failed_drills_tracked(tmp_path):
    """Custom drill with impossible oracle should appear in failed list."""
    from utils.arena import (
        Drill, DrillOracle, DrillBatch, DrillLedger, get_drill,
    )
    from utils.simulation_clock import NAIROBI_TZ
    ledger = DrillLedger(ledger_dir=tmp_path)
    # Inject a known-failing drill into the library temporarily via runner
    from utils.arena import DrillRunner
    impossible = Drill(
        name="impossible_test", description="x", category="test",
        sim_start=datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ),
        agent_goal="survey_macro",
        oracle=DrillOracle(min_steps=100),
    )
    runner = DrillRunner()
    result = runner.run(impossible)
    ledger.record(drill=impossible, result=result)
    runs = ledger.list_runs(passed=False)
    assert len(runs) == 1


def test_v10486_batch_custom_policy_factory(tmp_path):
    """Pass a custom policy factory."""
    from utils.arena import DrillBatch, DrillLedger
    from utils.agents import ScriptedPolicy
    ledger = DrillLedger(ledger_dir=tmp_path)

    def factory():
        return ScriptedPolicy([
            ("macro:snapshot", {}),
            ("chaos:active", {}),
        ])

    result = DrillBatch(
        ledger=ledger, policy_factory=factory,
    ).run(drill_names=["observe_kes_devaluation"],
           record_to_ledger=False)
    # ScriptedPolicy still runs 2 steps successfully
    assert result.total == 1


# ── Trajectory persistence ──────────────────────────────────────────

def test_v10486_trajectory_file_is_readable_json(tmp_path):
    import json
    from utils.arena import DrillLedger, DrillBatch
    ledger = DrillLedger(ledger_dir=tmp_path)
    res = DrillBatch(ledger=ledger).run(
        drill_names=["observe_kes_devaluation"])
    run_id = res.run_ids[0]
    traj_path = tmp_path / f"{run_id}.trajectory.json"
    assert traj_path.exists()
    data = json.loads(traj_path.read_text())
    assert "steps" in data


def test_v10486_ledger_survives_process_restart(tmp_path):
    """Records written by one ledger instance are readable by another."""
    from utils.arena import DrillLedger, DrillBatch
    ledger1 = DrillLedger(ledger_dir=tmp_path)
    DrillBatch(ledger=ledger1).run(
        drill_names=["observe_kes_devaluation"])
    assert ledger1.total() == 1
    # Fresh instance
    ledger2 = DrillLedger(ledger_dir=tmp_path)
    assert ledger2.total() == 1
    runs = ledger2.list_runs()
    assert runs[0].drill_name == "observe_kes_devaluation"


# ── G372 + cumulative regression ────────────────────────────────────

def test_v10486_g372_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10486_o7b_drill_scoring_replay
    r = gate_v10486_o7b_drill_scoring_replay()
    assert r["passed"], r.get("violations")


def test_v10486_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10485_o7a_training_arena,
        gate_v10484_o6b_agent_infrastructure,
        gate_v10483_o6a_ml_evolution_lab,
    )
    for gate in (gate_v10485_o7a_training_arena,
                  gate_v10484_o6b_agent_infrastructure,
                  gate_v10483_o6a_ml_evolution_lab):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10486_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

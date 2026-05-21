"""tests/test_microtask_engine.py — Standard #13 MicroTaskEngine tests
(v5.40).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - generate_daily_tasks returns the spec-shaped tasks
       - threshold math (pace < daily_req * 0.9)
       - priority bands (High <0.5, Medium [0.5, 0.9))
       - target-met / no-target / zero-target → no task
       - working-day arithmetic
       - period bounds for monthly + quarterly
       - persistence helpers (save/list/complete) with idempotent dedup

  2. Trigger-reliability harness:
       - test_trigger_reliability_meets_90_percent runs every fixture
         scenario in tests/fixtures/microtask_scenarios.json. Asserts
         ≥90% (the spec's bar). Writes microtask_reliability_results.json
         for G24 to read.

The "90% task conversion rate" the spec names is a deployed-runtime
metric (% of recommended tasks staff actually do) — that's OUT OF
SCOPE here. We measure the verifiable structural claim: trigger
reliability.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "microtask_scenarios.json"
RELIABILITY_RESULTS = ROOT / "microtask_reliability_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Unit tests — engine internals
# ═══════════════════════════════════════════════════════════════════════

class TestPeriodBounds:
    def test_monthly_bounds(self):
        from utils.microtask_engine import _period_bounds
        bounds = _period_bounds("2026-04")
        assert bounds == (date(2026, 4, 1), date(2026, 4, 30))

    def test_quarterly_bounds(self):
        from utils.microtask_engine import _period_bounds
        bounds = _period_bounds("2026-Q2")
        assert bounds == (date(2026, 4, 1), date(2026, 6, 30))

    def test_invalid_period(self):
        from utils.microtask_engine import _period_bounds
        assert _period_bounds("garbage") is None
        assert _period_bounds("") is None
        assert _period_bounds("2026-Q5") is None


class TestWorkdayCounting:
    def test_full_april_2026(self):
        # April 2026: 1=Wed; weekdays = 22
        from utils.microtask_engine import _count_weekdays_inclusive
        assert _count_weekdays_inclusive(date(2026, 4, 1), date(2026, 4, 30)) == 22

    def test_one_full_week(self):
        from utils.microtask_engine import _count_weekdays_inclusive
        # Mon Apr 6 to Fri Apr 10 = 5 weekdays
        assert _count_weekdays_inclusive(date(2026, 4, 6), date(2026, 4, 10)) == 5

    def test_weekend_only(self):
        from utils.microtask_engine import _count_weekdays_inclusive
        # Sat-Sun → 0
        assert _count_weekdays_inclusive(date(2026, 4, 11), date(2026, 4, 12)) == 0

    def test_inverted_range(self):
        from utils.microtask_engine import _count_weekdays_inclusive
        # start > end → 0 (defensive)
        assert _count_weekdays_inclusive(date(2026, 4, 30), date(2026, 4, 1)) == 0

    def test_single_weekday(self):
        from utils.microtask_engine import _count_weekdays_inclusive
        assert _count_weekdays_inclusive(date(2026, 4, 15), date(2026, 4, 15)) == 1

    def test_single_weekend_day(self):
        from utils.microtask_engine import _count_weekdays_inclusive
        assert _count_weekdays_inclusive(date(2026, 4, 11), date(2026, 4, 11)) == 0


class TestRecommendedTaskRouting:
    """_default_recommended_task picks one task per KPI class."""

    def test_deposit_kpi_gets_call_action(self):
        from utils.microtask_engine import _default_recommended_task
        t = _default_recommended_task("DEP_GROWTH")
        assert "call" in t.lower() or "prospect" in t.lower()

    def test_npl_kpi_gets_collection_action(self):
        from utils.microtask_engine import _default_recommended_task
        t = _default_recommended_task("NPL_PCT")
        assert "delinquent" in t.lower()

    def test_aml_kpi_gets_clear_action(self):
        from utils.microtask_engine import _default_recommended_task
        t = _default_recommended_task("AML_SLA")
        assert "AML" in t or "alert" in t.lower()

    def test_unknown_kpi_returns_generic(self):
        from utils.microtask_engine import _default_recommended_task
        t = _default_recommended_task("TOTALLY_NOVEL_KPI_XYZ")
        # Returns SOMETHING — never empty
        assert isinstance(t, str) and len(t) > 0


# ═══════════════════════════════════════════════════════════════════════
# Engine decision logic
# ═══════════════════════════════════════════════════════════════════════

def _make_engine(target, actual, days_remaining, days_elapsed, kpi_id="K1"):
    """Build a MicroTaskEngine with full collaborator injection.

    Overrides the static _compute_days_elapsed via a subclass."""
    from utils.microtask_engine import MicroTaskEngine

    class _E(MicroTaskEngine):
        @staticmethod
        def _compute_days_elapsed(period, today):
            return days_elapsed

    return _E(
        active_kpis_fn=lambda sc: [{"id": kpi_id}],
        target_lookup_fn=lambda sc, k, p: Decimal(str(target)) if target is not None else None,
        actual_lookup_fn=lambda sc, k, p: Decimal(str(actual)) if actual is not None else None,
        working_days_fn=lambda p, t: days_remaining,
        period_fn=lambda t: "2026-04",
    )


class TestPaceThreshold:
    """pace < daily_req * 0.9 fires task; otherwise no task."""

    def test_clearly_behind_fires_task(self):
        # target=100, actual=20, elapsed=11, remaining=12
        # remaining_target=80, daily_req=80/12=6.67
        # pace=20/11=1.82, 1.82 < 6.67*0.9=6.0 → fires
        eng = _make_engine(target=100, actual=20, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 1

    def test_on_pace_no_task(self):
        # target=100, actual=50 → exactly on pace (50/11=4.55, daily_req=50/12=4.17)
        # 4.55 >= 4.17*0.9=3.75 → no task
        eng = _make_engine(target=100, actual=50, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 0

    def test_target_met_no_task(self):
        eng = _make_engine(target=100, actual=100, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 0

    def test_target_exceeded_no_task(self):
        eng = _make_engine(target=100, actual=110, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 0

    def test_no_target_no_task(self):
        eng = _make_engine(target=None, actual=20, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 0

    def test_zero_target_no_task(self):
        eng = _make_engine(target=0, actual=0, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 0

    def test_no_working_days_no_task(self):
        # Even a behind-pace KPI gets no task on the last day
        eng = _make_engine(target=100, actual=20, days_remaining=0, days_elapsed=22)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 30))
        assert len(tasks) == 0


class TestPriorityBands:
    """gap_ratio < 0.5 → High; [0.5, 0.9) → Medium."""

    def test_very_low_pace_high_priority(self):
        # actual=5 → pace=5/11=0.45, daily_req=95/12=7.92, ratio=0.057 → High
        eng = _make_engine(target=100, actual=5, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 1 and tasks[0].priority == "High"

    def test_medium_pace_medium_priority(self):
        # actual=40 → pace=3.64, daily_req=60/12=5.0, ratio=0.73 → Medium
        eng = _make_engine(target=100, actual=40, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 1 and tasks[0].priority == "Medium"

    def test_priority_boundary(self):
        # ratio just below 0.5 → High; just above 0.5 → Medium
        # Find an actual that produces ratio close to 0.5:
        # ratio = (current/11) / ((100-current)/12) = 12*current / (11*(100-current)) ≈ 0.5
        # 12c = 0.5 · 11 · (100-c) = 5.5(100-c) = 550 - 5.5c
        # 17.5c = 550 → c ≈ 31.4
        eng_high = _make_engine(target=100, actual=30, days_remaining=12, days_elapsed=11)
        tasks_h = eng_high.generate_daily_tasks("S001", today=date(2026, 4, 15))
        # 30/11=2.73, 70/12=5.83, ratio=0.47 → High
        assert tasks_h[0].priority == "High"

        eng_med = _make_engine(target=100, actual=33, days_remaining=12, days_elapsed=11)
        tasks_m = eng_med.generate_daily_tasks("S001", today=date(2026, 4, 15))
        # 33/11=3.0, 67/12=5.58, ratio=0.54 → Medium
        assert tasks_m[0].priority == "Medium"


class TestTaskShape:
    """Each MicroTask has the spec-required keys plus traceability fields."""

    def test_task_has_required_fields(self):
        eng = _make_engine(target=100, actual=20, days_remaining=12, days_elapsed=11)
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 1
        t = tasks[0]
        # Spec-required
        assert t.task and isinstance(t.task, str)
        assert t.priority in ("High", "Medium")
        # Traceability
        assert t.staff_code == "S001"
        assert t.kpi_id == "K1"
        assert t.for_date == "2026-04-15"
        assert t.current_value == 20.0
        assert t.target_value == 100.0
        assert t.daily_req is not None and t.daily_req > 0
        assert t.current_pace is not None
        assert t.gap_pct is not None and 0 <= t.gap_pct <= 100
        assert t.days_remaining == 12

    def test_task_id_deterministic(self):
        """Re-running with same inputs produces same task IDs (idempotent
        save semantics)."""
        eng = _make_engine(target=100, actual=20, days_remaining=12, days_elapsed=11)
        t1 = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))[0]
        t2 = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))[0]
        assert t1.id == t2.id


class TestMaxTasksCap:
    """Engine never returns more than max_tasks_per_staff tasks."""

    def test_six_kpis_caps_at_5(self):
        from utils.microtask_engine import MicroTaskEngine
        kpis = [{"id": f"K{i}"} for i in range(6)]
        targets = {f"K{i}": Decimal("100") for i in range(6)}
        actuals = {f"K{i}": Decimal("5") for i in range(6)}

        class _E(MicroTaskEngine):
            @staticmethod
            def _compute_days_elapsed(period, today):
                return 11

        eng = _E(
            active_kpis_fn=lambda sc: kpis,
            target_lookup_fn=lambda sc, k, p: targets.get(k),
            actual_lookup_fn=lambda sc, k, p: actuals.get(k),
            working_days_fn=lambda p, t: 12,
            period_fn=lambda t: "2026-04",
            max_tasks_per_staff=5,
        )
        tasks = eng.generate_daily_tasks("S001", today=date(2026, 4, 15))
        assert len(tasks) == 5


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_save_and_list(self, tmp_path, monkeypatch):
        from utils import microtask_engine
        tasks_file = tmp_path / "microtasks.json"
        monkeypatch.setattr(microtask_engine, "TASKS_FILE", tasks_file)

        t = microtask_engine.MicroTask(
            id="t1", staff_code="S001", kpi_id="K1", period="2026-04",
            for_date="2026-04-15", task="Do X", priority="High",
        )
        n = microtask_engine.save_pending_tasks([t])
        assert n == 1

        active = microtask_engine.list_active_tasks("S001", date(2026, 4, 15))
        assert len(active) == 1 and active[0]["task"] == "Do X"

    def test_dedup_replaces_same_day_same_kpi(self, tmp_path, monkeypatch):
        from utils import microtask_engine
        monkeypatch.setattr(microtask_engine, "TASKS_FILE",
                            tmp_path / "microtasks.json")

        t1 = microtask_engine.MicroTask(
            id="t1", staff_code="S001", kpi_id="K1", period="2026-04",
            for_date="2026-04-15", task="Do X v1", priority="High",
        )
        microtask_engine.save_pending_tasks([t1])
        t2 = microtask_engine.MicroTask(
            id="t2", staff_code="S001", kpi_id="K1", period="2026-04",
            for_date="2026-04-15", task="Do X v2", priority="High",
        )
        microtask_engine.save_pending_tasks([t2])

        active = microtask_engine.list_active_tasks("S001", date(2026, 4, 15))
        assert len(active) == 1
        assert active[0]["task"] == "Do X v2"

    def test_complete(self, tmp_path, monkeypatch):
        from utils import microtask_engine
        monkeypatch.setattr(microtask_engine, "TASKS_FILE",
                            tmp_path / "microtasks.json")
        t = microtask_engine.MicroTask(
            id="t1", staff_code="S001", kpi_id="K1", period="2026-04",
            for_date="2026-04-15", task="Do X", priority="High",
        )
        microtask_engine.save_pending_tasks([t])
        ok = microtask_engine.complete_task("t1", "S001")
        assert ok is True

        active = microtask_engine.list_active_tasks("S001", date(2026, 4, 15))
        assert len(active) == 0   # completed → not active


# ═══════════════════════════════════════════════════════════════════════
# Trigger-reliability harness — Standard #13 spec verification
# ═══════════════════════════════════════════════════════════════════════

def _build_engine_for_scenario(scenario):
    """Build an engine wired to the scenario's mock data."""
    from utils.microtask_engine import MicroTaskEngine
    inp = scenario["input"]
    days_elapsed = inp.get("days_elapsed", 0)

    class _E(MicroTaskEngine):
        @staticmethod
        def _compute_days_elapsed(period, today):
            return days_elapsed

    return _E(
        active_kpis_fn=lambda sc: inp["kpis"],
        target_lookup_fn=lambda sc, k, p: (
            Decimal(str(inp["targets"][k])) if k in inp["targets"] else None
        ),
        actual_lookup_fn=lambda sc, k, p: (
            Decimal(str(inp["actuals"][k])) if k in inp["actuals"] else None
        ),
        working_days_fn=lambda p, t: inp["working_days_remaining"],
        period_fn=lambda t: inp["period"],
    )


def _scenario_matches(actual_tasks, scenario):
    """Compare actual tasks to expected. Returns (match, reason)."""
    if "expected_task_count" in scenario:
        if len(actual_tasks) != scenario["expected_task_count"]:
            return False, (
                f"count: actual={len(actual_tasks)} "
                f"expected={scenario['expected_task_count']}"
            )
        return True, "ok"

    expected = scenario.get("expected_tasks", [])
    if len(actual_tasks) != len(expected):
        return False, (
            f"count: actual={len(actual_tasks)} expected={len(expected)}"
        )
    actual_by_kpi = {t.kpi_id: t for t in actual_tasks}
    for exp in expected:
        kpi_id = exp.get("kpi_id")
        if kpi_id not in actual_by_kpi:
            return False, f"missing KPI {kpi_id}"
        act = actual_by_kpi[kpi_id]
        if "priority" in exp and act.priority != exp["priority"]:
            return False, (
                f"{kpi_id} priority: actual={act.priority} "
                f"expected={exp['priority']}"
            )
        if "task_must_contain" in exp:
            substr = exp["task_must_contain"].lower()
            if substr not in act.task.lower():
                return False, (
                    f"{kpi_id} task missing required substring '{substr}'"
                )
    return True, "ok"


def test_trigger_reliability_meets_90_percent():
    """Run every fixture scenario; assert ≥90% match rate; write artifact.

    This is the spec verification test. Mirrors v5.38's nudge accuracy
    harness: it's a regular pytest test AND its result feeds G24 via
    microtask_reliability_results.json.
    """
    scenarios = json.loads(FIXTURES.read_text())
    assert len(scenarios) >= 20, (
        f"Need at least 20 scenarios for a meaningful sample; got {len(scenarios)}"
    )

    results = []
    matches = 0
    for s in scenarios:
        inp = s["input"]
        today = datetime.strptime(inp["today"], "%Y-%m-%d").date()
        eng = _build_engine_for_scenario(s)
        actual = eng.generate_daily_tasks(inp["staff_code"], today=today)
        actual_brief = [
            {"kpi_id": t.kpi_id, "priority": t.priority, "task": t.task}
            for t in actual
        ]
        ok, reason = _scenario_matches(actual, s)
        if ok:
            matches += 1
        results.append({
            "id":             s["id"],
            "description":    s["description"],
            "matched":        ok,
            "reason":         reason,
            "actual_tasks":   actual_brief,
            "expected":       s.get("expected_tasks") or s.get("expected_task_count"),
        })

    reliability = matches / len(scenarios) * 100

    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "matches":         matches,
        "misses":          len(scenarios) - matches,
        "reliability_pct": round(reliability, 2),
        "spec_target_pct": 90.0,
        "all_passed":      reliability >= 90.0,
        "results":         results,
    }
    RELIABILITY_RESULTS.write_text(json.dumps(artifact, indent=2))

    assert reliability >= 90.0, (
        f"Trigger reliability {reliability:.1f}% below spec target of 90%. "
        f"Misses:\n" +
        "\n".join(
            f"  {r['id']}: {r['reason']}"
            for r in results if not r["matched"]
        )
    )

"""Integration tests for v10.480 — Phase O4-A simulation clock + tick scheduler."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_clock():
    """Each test gets a fresh sim clock."""
    for k in list(sys.modules):
        if "simulation_clock" in k: del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    reset_simulation_clock()
    yield
    reset_simulation_clock()


# ── Module presence ─────────────────────────────────────────────────

def test_v10480_simulation_clock_module_exists():
    assert (REPO / "utils" / "simulation_clock.py").exists()


def test_v10480_tick_scheduler_module_exists():
    assert (REPO / "utils" / "tick_scheduler.py").exists()


# ── SimulationClock ─────────────────────────────────────────────────

def test_v10480_clock_inactive_by_default():
    from utils.simulation_clock import get_simulation_clock
    clock = get_simulation_clock()
    assert not clock.is_active()


def test_v10480_sim_now_returns_wall_when_inactive():
    from utils.simulation_clock import sim_now
    n = sim_now()
    # Should be within a few seconds of wall time
    wall = datetime.now(timezone.utc)
    assert abs((n - wall).total_seconds()) < 5


def test_v10480_clock_set_activates_and_anchors():
    from utils.simulation_clock import (
        get_simulation_clock, sim_now, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    target = datetime(2026, 3, 1, 9, 0, tzinfo=NAIROBI_TZ)
    clock.set(target)
    assert clock.is_active()
    n = sim_now().astimezone(NAIROBI_TZ)
    assert n.hour == 9 and n.minute == 0
    assert n.year == 2026 and n.month == 3 and n.day == 1


def test_v10480_clock_advance_moves_time_forward():
    from utils.simulation_clock import (
        get_simulation_clock, sim_now, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 3, 1, 12, 0, tzinfo=NAIROBI_TZ))
    clock.advance(timedelta(hours=3, minutes=15))
    n = sim_now().astimezone(NAIROBI_TZ)
    assert n.hour == 15 and n.minute == 15


def test_v10480_clock_advance_before_set_raises():
    from utils.simulation_clock import get_simulation_clock
    clock = get_simulation_clock()
    with pytest.raises(RuntimeError):
        clock.advance(timedelta(hours=1))


def test_v10480_clock_set_requires_tz_aware():
    from utils.simulation_clock import get_simulation_clock
    clock = get_simulation_clock()
    with pytest.raises(ValueError):
        clock.set(datetime(2026, 1, 1, 12, 0))  # naive


def test_v10480_clock_deactivate_returns_to_wall_clock():
    from utils.simulation_clock import (
        get_simulation_clock, sim_now, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2030, 1, 1, 12, 0, tzinfo=NAIROBI_TZ))
    assert sim_now().year == 2030
    clock.deactivate()
    assert sim_now().year != 2030  # back to wall clock


def test_v10480_clock_now_nairobi_uses_correct_tz():
    from utils.simulation_clock import (
        get_simulation_clock, sim_now_nairobi, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 6, 15, 14, 30, tzinfo=NAIROBI_TZ))
    n = sim_now_nairobi()
    assert n.tzinfo.utcoffset(n) == timedelta(hours=3)
    assert n.hour == 14 and n.minute == 30


# ── TickScheduler ───────────────────────────────────────────────────

def test_v10480_scheduler_fires_one_shot():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    sched.schedule_at(
        datetime(2026, 1, 1, 11, 0, tzinfo=NAIROBI_TZ),
        lambda: fired.append("ok"),
    )
    assert sched.pending() == 1
    sched.tick(advance_by=timedelta(hours=2))
    assert fired == ["ok"]
    assert sched.pending() == 0


def test_v10480_scheduler_skips_future_callbacks():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    sched.schedule_at(
        datetime(2026, 1, 1, 15, 0, tzinfo=NAIROBI_TZ),
        lambda: fired.append("future"),
    )
    sched.tick(advance_by=timedelta(hours=2))  # 10:00 → 12:00
    assert fired == []
    assert sched.pending() == 1


def test_v10480_scheduler_priority_order():
    """Higher priority fires first when when ties."""
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    t = datetime(2026, 1, 1, 11, 0, tzinfo=NAIROBI_TZ)
    sched.schedule_at(t, lambda: fired.append("L"), priority=0)
    sched.schedule_at(t, lambda: fired.append("H"), priority=10)
    sched.schedule_at(t, lambda: fired.append("M"), priority=5)
    sched.tick(advance_by=timedelta(hours=2))
    assert fired == ["H", "M", "L"]


def test_v10480_scheduler_insertion_order_when_priorities_tie():
    """Same priority + same when → insertion order."""
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    t = datetime(2026, 1, 1, 11, 0, tzinfo=NAIROBI_TZ)
    sched.schedule_at(t, lambda: fired.append("first"))
    sched.schedule_at(t, lambda: fired.append("second"))
    sched.schedule_at(t, lambda: fired.append("third"))
    sched.tick(advance_by=timedelta(hours=2))
    assert fired == ["first", "second", "third"]


def test_v10480_scheduler_recurring_reschedules():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 9, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    sched.schedule_recurring(
        start_at=datetime(2026, 1, 1, 9, 30, tzinfo=NAIROBI_TZ),
        interval=timedelta(minutes=15),
        callback=lambda: fired.append("R"),
    )
    # 9:00 → 10:00, fires at 9:30, 9:45, 10:00 = 3 fires
    sched.tick(advance_by=timedelta(hours=1))
    assert len(fired) == 3
    # Pending should still be 1 (the next recurring)
    assert sched.pending() == 1


def test_v10480_scheduler_cancel_removes_callback():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    cb_id = sched.schedule_at(
        datetime(2026, 1, 1, 11, 0, tzinfo=NAIROBI_TZ),
        lambda: fired.append("x"),
    )
    assert sched.cancel(cb_id)
    sched.tick(advance_by=timedelta(hours=2))
    assert fired == []


def test_v10480_scheduler_cancel_unknown_returns_false():
    from utils.simulation_clock import get_simulation_clock
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    sched = TickScheduler(clock)
    assert not sched.cancel("nonexistent-id-123")


def test_v10480_scheduler_clear_removes_all():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    for h in range(11, 20):
        sched.schedule_at(
            datetime(2026, 1, 1, h, 0, tzinfo=NAIROBI_TZ),
            lambda: None,
        )
    assert sched.pending() == 9
    removed = sched.clear()
    assert removed == 9
    assert sched.pending() == 0


def test_v10480_scheduler_peek_next():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    assert sched.peek_next() is None
    sched.schedule_at(
        datetime(2026, 1, 1, 14, 0, tzinfo=NAIROBI_TZ),
        lambda: None,
        label="later",
    )
    sched.schedule_at(
        datetime(2026, 1, 1, 11, 0, tzinfo=NAIROBI_TZ),
        lambda: None,
        label="sooner",
    )
    nxt = sched.peek_next()
    assert nxt is not None
    assert nxt.label == "sooner"


def test_v10480_scheduler_fired_count_increments():
    from utils.simulation_clock import get_simulation_clock, NAIROBI_TZ
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, 10, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    for h in range(11, 15):
        sched.schedule_at(
            datetime(2026, 1, 1, h, 0, tzinfo=NAIROBI_TZ),
            lambda: None,
        )
    assert sched.fired_count() == 0
    sched.tick(advance_by=timedelta(hours=5))
    assert sched.fired_count() == 4


# ── KIC + sim clock integration ─────────────────────────────────────

def test_v10480_kic_morning_window_via_sim_clock():
    for k in list(sys.modules):
        if "channels" in k or "simulation_clock" in k: del sys.modules[k]
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel, ChannelStatus
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 10, 0, tzinfo=NAIROBI_TZ))
    for seed in range(30):
        r = submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                      "beneficiary_bank_code": "011"},
            amount=50_000, debit_account="x", credit_account="y",
            reference=f"V480-M-{seed}", actor="t", seed=seed)
        if r.success:
            assert r.raw_response["BatchWindow"] == "MORNING"
            return
    pytest.fail("no KIC success in 30 seeds at 10am")


def test_v10480_kic_afternoon_window_via_sim_clock():
    for k in list(sys.modules):
        if "channels" in k or "simulation_clock" in k: del sys.modules[k]
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 13, 0, tzinfo=NAIROBI_TZ))
    for seed in range(30):
        r = submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                      "beneficiary_bank_code": "011"},
            amount=50_000, debit_account="x", credit_account="y",
            reference=f"V480-A-{seed}", actor="t", seed=100+seed)
        if r.success:
            assert r.raw_response["BatchWindow"] == "AFTERNOON"
            return
    pytest.fail("no KIC success in 30 seeds at 1pm")


def test_v10480_kic_next_day_window_via_sim_clock():
    for k in list(sys.modules):
        if "channels" in k or "simulation_clock" in k: del sys.modules[k]
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 17, 0, tzinfo=NAIROBI_TZ))
    for seed in range(30):
        r = submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                      "beneficiary_bank_code": "011"},
            amount=50_000, debit_account="x", credit_account="y",
            reference=f"V480-N-{seed}", actor="t", seed=200+seed)
        if r.success:
            assert r.raw_response["BatchWindow"] == "NEXT_DAY_MORNING"
            return
    pytest.fail("no KIC success in 30 seeds at 5pm")


# ── ScenarioContext exposes clock ───────────────────────────────────

def test_v10480_scenario_context_has_clock_property():
    for k in list(sys.modules):
        if "scenarios" in k or "simulation_clock" in k: del sys.modules[k]
    from utils.scenarios.base import ScenarioContext
    from utils.simulation_clock import SimulationClock
    ctx = ScenarioContext(seed=1)
    assert hasattr(ctx, "clock")
    assert isinstance(ctx.clock, SimulationClock)


def test_v10480_scenario_can_drive_clock():
    """A scenario can set/advance clock; channels respond accordingly."""
    for k in list(sys.modules):
        if ("scenarios" in k or "channels" in k or "simulation_clock" in k
                or "event_bus" in k):
            del sys.modules[k]
    from utils.simulation_clock import NAIROBI_TZ, reset_simulation_clock
    from utils.scenarios.base import (
        Scenario, ScenarioCategory, ScenarioSeverity,
        ScenarioContext, ScenarioRunner,
    )
    reset_simulation_clock()

    def runner_fn(ctx):
        ctx.clock.set(datetime(2026, 5, 15, 11, 0, tzinfo=NAIROBI_TZ))
        before = None
        for s in range(20):
            r = ctx.submit_channel("kic",
                payload={"transaction_type": "EFT_CREDIT",
                          "beneficiary_bank_code": "011"},
                amount=50_000, debit_account="x", credit_account="y")
            if r.success:
                before = r.raw_response["BatchWindow"]
                break
        ctx.clock.advance(timedelta(hours=1))
        after = None
        for s in range(20):
            r = ctx.submit_channel("kic",
                payload={"transaction_type": "EFT_CREDIT",
                          "beneficiary_bank_code": "011"},
                amount=50_000, debit_account="x", credit_account="y")
            if r.success:
                after = r.raw_response["BatchWindow"]
                break
        return {"before": before, "after": after}

    s = Scenario(
        name="t",
        category=ScenarioCategory.OPERATIONAL,
        description="t",
        runner=runner_fn,
        severity=ScenarioSeverity.INFO,
        realistic_basis="t",
    )
    r = ScenarioRunner(detect_anomalies=False).run(s, seed=1)
    assert r.scenario_output["before"] == "MORNING"
    assert r.scenario_output["after"] == "AFTERNOON"


# ── event_bus uses sim_now ──────────────────────────────────────────

def test_v10480_event_bus_uses_sim_clock_when_active():
    for k in list(sys.modules):
        if "simulation_clock" in k or "event_bus" in k:
            del sys.modules[k]
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ, reset_simulation_clock,
    )
    from utils.event_bus import get_event_bus
    reset_simulation_clock()
    clock = get_simulation_clock()
    clock.set(datetime(2030, 7, 4, 12, 0, tzinfo=NAIROBI_TZ))
    bus = get_event_bus()
    bus.emit(event_type="test.v10480_event_ts",
              actor="t", entity_id="e", module="t")
    evs = bus.query(event_type="test.v10480_event_ts", limit=1)
    assert evs
    assert "2030" in evs[0].timestamp


# ── G366 + cumulative regression ────────────────────────────────────

def test_v10480_g366_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10480_o4a_simulation_clock_tick_scheduler
    r = gate_v10480_o4a_simulation_clock_tick_scheduler()
    assert r["passed"], r.get("violations")


def test_v10480_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10477_o3a_channel_simulators,
        gate_v10478_o3b_kic_cards_complete_7_channels,
        gate_v10479_o3c_scenario_library,
        gate_v10475_o2a_telemetry_lineage_replay,
        gate_v10476_o2b_ai_heatmap_anomaly_telemetry,
        gate_v10474_o8_environment_isolation,
    )
    assert gate_v10477_o3a_channel_simulators()["passed"]
    assert gate_v10478_o3b_kic_cards_complete_7_channels()["passed"]
    assert gate_v10479_o3c_scenario_library()["passed"]
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]
    assert gate_v10476_o2b_ai_heatmap_anomaly_telemetry()["passed"]
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10480_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

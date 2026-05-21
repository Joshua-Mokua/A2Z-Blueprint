"""Integration tests for v10.481 — Phase O4-B macro economic state."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_all():
    """Each test gets a fresh sim clock + macro state."""
    for k in list(sys.modules):
        if any(s in k for s in (
                "macro_state", "macro_evolution", "macro_calendar",
                "macro_bridge", "simulation_clock", "tick_scheduler")):
            del sys.modules[k]
    from utils.macro_state import reset_macro_state
    from utils.simulation_clock import reset_simulation_clock
    reset_macro_state()
    reset_simulation_clock()
    yield
    reset_macro_state()
    reset_simulation_clock()


# ── Module presence ─────────────────────────────────────────────────

def test_v10481_macro_state_module_exists():
    assert (REPO / "utils" / "macro_state.py").exists()


def test_v10481_macro_evolution_module_exists():
    assert (REPO / "utils" / "macro_evolution.py").exists()


def test_v10481_macro_calendar_module_exists():
    assert (REPO / "utils" / "macro_calendar.py").exists()


def test_v10481_macro_bridge_module_exists():
    assert (REPO / "utils" / "macro_bridge.py").exists()


# ── MacroState ──────────────────────────────────────────────────────

def test_v10481_macro_state_is_frozen_dataclass():
    from utils.macro_state import MacroState
    from dataclasses import is_dataclass, fields
    assert is_dataclass(MacroState)
    field_names = {f.name for f in fields(MacroState)}
    expected = {
        "as_of", "cbk_central_bank_rate", "treasury_91d",
        "treasury_182d", "treasury_364d", "interbank_rate",
        "usd_kes", "eur_kes", "gbp_kes", "inflation_yoy",
        "gdp_growth_yoy", "npl_ratio", "cash_reserve_ratio",
        "liquidity_ratio", "private_sector_credit_growth",
    }
    assert expected.issubset(field_names)


def test_v10481_macro_state_kenya_2026_baseline_realistic():
    from utils.macro_state import MacroState
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert 0.05 <= base.cbk_central_bank_rate <= 0.20
    assert 100 <= base.usd_kes <= 200
    assert 0.05 <= base.npl_ratio <= 0.25
    assert 0.0 <= base.inflation_yoy <= 0.15
    assert 0.0 <= base.gdp_growth_yoy <= 0.10


def test_v10481_macro_state_with_change_returns_new():
    from utils.macro_state import MacroState
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    new = base.with_change(cbk_central_bank_rate=0.08)
    assert new.cbk_central_bank_rate == 0.08
    assert base.cbk_central_bank_rate == 0.10  # original unchanged
    assert new is not base


def test_v10481_macro_state_to_dict_roundtrip():
    from utils.macro_state import MacroState
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    d = base.to_dict()
    assert "cbk_central_bank_rate" in d
    assert "usd_kes" in d
    assert "as_of" in d
    assert d["as_of"].startswith("2026")


def test_v10481_macro_state_naive_datetime_rejected():
    from utils.macro_state import MacroState
    with pytest.raises(ValueError):
        MacroState.kenya_2026_baseline(as_of=datetime(2026, 1, 1))


def test_v10481_global_macro_state_singleton():
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.macro_state import get_macro_state, reset_macro_state
    reset_macro_state()
    get_simulation_clock().set(
        datetime(2026, 1, 1, tzinfo=NAIROBI_TZ)
    )
    s1 = get_macro_state()
    s2 = get_macro_state()
    assert s1 is s2  # same singleton


def test_v10481_set_macro_state_overrides():
    from utils.macro_state import (
        MacroState, get_macro_state, set_macro_state,
    )
    set_macro_state(MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 6, 1, tzinfo=timezone.utc)
    ).with_change(cbk_central_bank_rate=0.12))
    assert get_macro_state().cbk_central_bank_rate == 0.12


# ── MacroEvolution ──────────────────────────────────────────────────

def test_v10481_evolution_drifts_state_forward():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ev = MacroEvolution(seed=1)
    new = ev.evolve(base, days_elapsed=30.0)
    assert new.as_of > base.as_of
    assert new.as_of - base.as_of == timedelta(days=30)


def test_v10481_evolution_is_seed_deterministic():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    a = MacroEvolution(seed=42).evolve(base, days_elapsed=90.0)
    b = MacroEvolution(seed=42).evolve(base, days_elapsed=90.0)
    assert abs(a.cbk_central_bank_rate - b.cbk_central_bank_rate) < 1e-12
    assert abs(a.usd_kes - b.usd_kes) < 1e-9
    assert abs(a.npl_ratio - b.npl_ratio) < 1e-12


def test_v10481_evolution_zero_days_is_identity():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ev = MacroEvolution(seed=1)
    new = ev.evolve(base, days_elapsed=0.0)
    assert new is base or new == base


def test_v10481_evolution_mean_reverts_over_long_horizon():
    """After a very long horizon, drift should pull CBR toward long-run."""
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    ).with_change(cbk_central_bank_rate=0.18)  # start far from 10%
    ev = MacroEvolution(seed=1)
    # Drift 5 years; result should be closer to 10% than 18%
    new = ev.evolve(base, days_elapsed=365 * 5)
    initial_gap = abs(0.18 - 0.10)
    final_gap = abs(new.cbk_central_bank_rate - 0.10)
    assert final_gap < initial_gap / 2, (
        f"after 5y, CBR {new.cbk_central_bank_rate} did not reverse "
        f"toward long-run 10% (started at 18%)"
    )


def test_v10481_apply_shock_cbr_change():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ev = MacroEvolution(seed=1)
    new = ev.apply_shock(base, shock="cbr_change", new_rate=0.075)
    assert abs(new.cbk_central_bank_rate - 0.075) < 1e-12
    # T-bill 91 should follow with same delta
    expected = base.treasury_91d + (0.075 - 0.10)
    assert abs(new.treasury_91d - expected) < 1e-9
    assert new.last_shock_name == "cbr_change"


def test_v10481_apply_shock_fx_devaluation():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ev = MacroEvolution(seed=1)
    new = ev.apply_shock(base, shock="fx_devaluation", pct=0.05)
    assert abs(new.usd_kes - base.usd_kes * 1.05) < 1e-6
    assert abs(new.eur_kes - base.eur_kes * 1.05) < 1e-6
    assert new.last_shock_name == "fx_devaluation"


def test_v10481_apply_shock_credit_shock():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ev = MacroEvolution(seed=1)
    new = ev.apply_shock(base, shock="credit_shock", delta=0.02)
    assert abs(new.npl_ratio - (base.npl_ratio + 0.02)) < 1e-9


def test_v10481_apply_shock_unknown_raises():
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    ev = MacroEvolution(seed=1)
    with pytest.raises(ValueError):
        ev.apply_shock(base, shock="unknown_shock")


# ── MacroCalendar ───────────────────────────────────────────────────

def test_v10481_kenya_2026_calendar_has_35_events():
    from utils.macro_calendar import MacroCalendar
    cal = MacroCalendar.kenya_2026_calendar()
    assert len(cal) == 35


def test_v10481_kenya_2026_calendar_has_6_mpc_meetings():
    from utils.macro_calendar import MacroCalendar
    cal = MacroCalendar.kenya_2026_calendar()
    mpc = [e for e in cal.all_events() if e.event_type == "cbk_mpc"]
    assert len(mpc) == 6


def test_v10481_kenya_2026_calendar_has_budget():
    from utils.macro_calendar import MacroCalendar
    cal = MacroCalendar.kenya_2026_calendar()
    budget = [e for e in cal.all_events() if e.event_type == "budget"]
    assert len(budget) == 1
    # Kenya budget typically June
    assert budget[0].when.month == 6


def test_v10481_events_between_window():
    from utils.macro_calendar import MacroCalendar
    cal = MacroCalendar.kenya_2026_calendar()
    may = cal.events_between(
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc),
    )
    # May has: CPI Release May 15, CBK MPC May 28, EOM May 31 = 3
    assert len(may) == 3


def test_v10481_next_event_after():
    from utils.macro_calendar import MacroCalendar
    cal = MacroCalendar.kenya_2026_calendar()
    nxt = cal.next_event_after(
        datetime(2026, 5, 16, tzinfo=timezone.utc)
    )
    assert nxt is not None
    assert nxt.event_type == "cbk_mpc"  # May 28


def test_v10481_calendar_events_naive_datetime_rejected():
    from utils.macro_calendar import MacroCalendar
    cal = MacroCalendar.kenya_2026_calendar()
    with pytest.raises(ValueError):
        cal.events_after(datetime(2026, 5, 1))


# ── MacroBridge end-to-end ──────────────────────────────────────────

def test_v10481_bridge_attach_registers_drift_and_events():
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_evolution import MacroEvolution
    from utils.macro_calendar import MacroCalendar
    from utils.macro_bridge import MacroBridge

    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    bridge = MacroBridge(
        evolution=MacroEvolution(seed=42),
        calendar=MacroCalendar.kenya_2026_calendar(),
    )
    bridge.attach_to_scheduler(sched, drift_interval_days=1.0)
    # 35 calendar events + 1 drift recurring = 36
    assert sched.pending() == 36


def test_v10481_bridge_60_day_tick_drifts_and_fires_events():
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_state import get_macro_state
    from utils.macro_evolution import MacroEvolution
    from utils.macro_calendar import MacroCalendar
    from utils.macro_bridge import MacroBridge

    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    bridge = MacroBridge(
        evolution=MacroEvolution(seed=42),
        calendar=MacroCalendar.kenya_2026_calendar(),
    )
    bridge.attach_to_scheduler(sched, drift_interval_days=1.0)
    sched.tick(advance_by=timedelta(days=60))
    # First 60 days: CPI Jan 15, MPC Jan 28, EOM Jan 31, CPI Feb 15,
    #                 EOM Feb 28 = 5 events
    assert len(bridge.events_fired()) == 5
    assert bridge.drift_count() >= 1
    state = get_macro_state()
    assert state.last_shock_name == "cbr_change"  # MPC fires CBR shock


def test_v10481_bridge_mpc_event_adjusts_cbr():
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_state import get_macro_state, MacroState, set_macro_state
    from utils.macro_evolution import MacroEvolution
    from utils.macro_calendar import MacroCalendar, MacroEvent
    from utils.macro_bridge import MacroBridge

    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    # Use a custom calendar with one MPC event specifying new_rate=0.085
    cal = MacroCalendar()
    cal.add_event(MacroEvent(
        name="Test MPC",
        when=datetime(2026, 2, 1, 9, 0, tzinfo=NAIROBI_TZ),
        event_type="cbk_mpc",
        payload={"new_rate": 0.085},
    ))
    sched = TickScheduler(clock)
    bridge = MacroBridge(
        evolution=MacroEvolution(seed=1),
        calendar=cal,
    )
    bridge.attach_to_scheduler(sched, drift_interval_days=30.0)
    sched.tick(advance_by=timedelta(days=40))
    state = get_macro_state()
    assert abs(state.cbk_central_bank_rate - 0.085) < 0.001  # close to 8.5%


def test_v10481_bridge_emits_macro_update_events():
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_evolution import MacroEvolution
    from utils.macro_calendar import MacroCalendar
    from utils.macro_bridge import MacroBridge
    from utils.event_bus import get_event_bus

    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    bridge = MacroBridge(
        evolution=MacroEvolution(seed=42),
        calendar=MacroCalendar.kenya_2026_calendar(),
    )
    bridge.attach_to_scheduler(sched, drift_interval_days=1.0)
    bus = get_event_bus()
    before_count = len(bus.query(event_type="macro.update", limit=1000))
    sched.tick(advance_by=timedelta(days=60))
    after = bus.query(event_type="macro.update", limit=1000)
    assert len(after) - before_count >= 5  # at least the 5 calendar events


def test_v10481_bridge_drift_coalesces_fast_forward():
    """A 60-day fast-forward should still apply 60 days of drift."""
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_state import get_macro_state
    from utils.macro_evolution import MacroEvolution
    from utils.macro_calendar import MacroCalendar
    from utils.macro_bridge import MacroBridge

    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    bridge = MacroBridge(
        evolution=MacroEvolution(seed=42),
        # Empty calendar to isolate drift only
        calendar=MacroCalendar(),
    )
    bridge.attach_to_scheduler(sched, drift_interval_days=1.0)
    state_before = get_macro_state()
    sched.tick(advance_by=timedelta(days=60))
    state_after = get_macro_state()
    # last_drift_at should advance by ~60 days
    assert state_after.last_drift_at is not None
    drift_delta_days = (state_after.last_drift_at
                         - state_before.as_of).days
    assert drift_delta_days >= 55  # close to 60 with float precision


# ── G367 + cumulative regression ────────────────────────────────────

def test_v10481_g367_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10481_o4b_macro_economic_state
    r = gate_v10481_o4b_macro_economic_state()
    assert r["passed"], r.get("violations")


def test_v10481_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10480_o4a_simulation_clock_tick_scheduler,
        gate_v10479_o3c_scenario_library,
        gate_v10478_o3b_kic_cards_complete_7_channels,
        gate_v10477_o3a_channel_simulators,
        gate_v10476_o2b_ai_heatmap_anomaly_telemetry,
        gate_v10475_o2a_telemetry_lineage_replay,
        gate_v10474_o8_environment_isolation,
    )
    assert gate_v10480_o4a_simulation_clock_tick_scheduler()["passed"]
    assert gate_v10479_o3c_scenario_library()["passed"]
    assert gate_v10478_o3b_kic_cards_complete_7_channels()["passed"]
    assert gate_v10477_o3a_channel_simulators()["passed"]
    assert gate_v10476_o2b_ai_heatmap_anomaly_telemetry()["passed"]
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10481_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

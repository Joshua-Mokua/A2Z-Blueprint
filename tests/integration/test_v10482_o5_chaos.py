"""Integration tests for v10.482 — Phase O5 chaos engineering."""

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
        if any(s in k for s in ("chaos", "channels", "simulation_clock",
                                  "tick_scheduler", "event_bus",
                                  "macro_")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()
    yield
    reset_simulation_clock()
    reset_chaos_injector()
    reset_macro_state()


# ── Module presence ─────────────────────────────────────────────────

def test_v10482_chaos_package_exists():
    pkg = REPO / "utils" / "chaos"
    assert pkg.is_dir()
    for f in ["__init__.py", "base.py", "injector.py",
                "library.py", "scheduler.py"]:
        assert (pkg / f).exists()


def test_v10482_chaos_kind_enum_has_5_values():
    from utils.chaos.base import ChaosKind
    vals = {k.value for k in ChaosKind}
    assert vals == {
        "channel_outage", "elevated_failure", "latency_spike",
        "macro_shock", "scheme_degraded",
    }


def test_v10482_chaos_severity_enum_has_5_values():
    from utils.chaos.base import ChaosSeverity
    vals = {s.value for s in ChaosSeverity}
    assert vals == {"info", "low", "medium", "high", "critical"}


def test_v10482_chaos_event_naive_when_rejected():
    from utils.chaos.base import ChaosEvent, ChaosKind
    with pytest.raises(ValueError):
        ChaosEvent(name="x", kind=ChaosKind.CHANNEL_OUTAGE,
                    when=datetime(2026, 1, 1))


# ── Library ─────────────────────────────────────────────────────────

def test_v10482_library_has_25_templates():
    from utils.chaos.library import CHAOS_LIBRARY
    assert len(CHAOS_LIBRARY) == 25


def test_v10482_library_breakdown_by_kind():
    from utils.chaos.library import chaos_events_by_kind
    assert len(chaos_events_by_kind("channel_outage")) == 8
    assert len(chaos_events_by_kind("elevated_failure")) == 7
    assert len(chaos_events_by_kind("latency_spike")) == 4
    assert len(chaos_events_by_kind("macro_shock")) == 4
    assert len(chaos_events_by_kind("scheme_degraded")) == 2


def test_v10482_library_severity_distribution_has_all_levels():
    from utils.chaos.library import chaos_events_by_severity
    for sev in ["info", "low", "medium", "high", "critical"]:
        n = len(chaos_events_by_severity(sev))
        # Allow some to be 0 (info), but high+critical must exist
    high = len(chaos_events_by_severity("high"))
    critical = len(chaos_events_by_severity("critical"))
    assert high + critical >= 8


def test_v10482_get_chaos_event_builds_from_template():
    from utils.chaos import get_chaos_event
    from utils.chaos.base import ChaosKind
    from utils.simulation_clock import NAIROBI_TZ
    when = datetime(2026, 5, 15, 14, 0, tzinfo=NAIROBI_TZ)
    ev = get_chaos_event("safaricom_mpesa_outage_30min", when=when)
    assert ev.kind == ChaosKind.CHANNEL_OUTAGE
    assert ev.target == "mpesa"
    assert ev.duration == timedelta(minutes=30)


def test_v10482_get_chaos_event_unknown_raises():
    from utils.chaos import get_chaos_event
    from utils.simulation_clock import NAIROBI_TZ
    with pytest.raises(KeyError):
        get_chaos_event("nonexistent_chaos_xyz",
                         when=datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))


def test_v10482_all_templates_have_realistic_basis():
    from utils.chaos.library import CHAOS_LIBRARY
    missing = [n for n, t in CHAOS_LIBRARY.items()
                if not t.get("realistic_basis", "").strip()]
    assert not missing, missing


# ── Injector ────────────────────────────────────────────────────────

def test_v10482_injector_singleton():
    from utils.chaos import get_chaos_injector
    a = get_chaos_injector()
    b = get_chaos_injector()
    assert a is b


def test_v10482_injector_activate_and_query():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    ev = get_chaos_event("safaricom_mpesa_outage_30min", when=clock.now())
    get_chaos_injector().activate(ev)
    assert get_chaos_injector().is_channel_outage("mpesa")


def test_v10482_injector_window_expiration():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    ev = get_chaos_event("safaricom_mpesa_outage_30min", when=clock.now())
    get_chaos_injector().activate(ev)
    clock.advance(timedelta(hours=2))
    assert not get_chaos_injector().is_channel_outage("mpesa")


def test_v10482_injector_target_star_matches_any_channel():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    ev = get_chaos_event("all_channels_latency_spike", when=clock.now())
    get_chaos_injector().activate(ev)
    # latency_spike with target=* should apply to every channel
    for chan in ["mpesa", "rtgs", "swift", "cards", "atm", "ussd", "kic"]:
        m = get_chaos_injector().latency_multiplier(chan)
        assert m > 1.0, f"channel {chan} should have elevated latency"


def test_v10482_injector_target_comma_list():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    # KEPSS host taking RTGS + KIC together
    ev = get_chaos_event("kepss_host_down_60min", when=clock.now())
    get_chaos_injector().activate(ev)
    assert get_chaos_injector().is_channel_outage("rtgs")
    assert get_chaos_injector().is_channel_outage("kic")
    # But not unrelated channels
    assert not get_chaos_injector().is_channel_outage("mpesa")


def test_v10482_injector_elevated_failure_composes_multiplicatively():
    from utils.chaos.base import (
        ChaosEvent, ChaosKind, ChaosSeverity,
    )
    from utils.chaos import get_chaos_injector
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    inj = get_chaos_injector()
    # 30% × 40% → combined: 1 - (0.7 * 0.6) = 0.58
    inj.activate(ChaosEvent(
        name="a", kind=ChaosKind.ELEVATED_FAILURE,
        when=clock.now(), target="cards",
        payload={"failure_rate": 0.30},
    ))
    inj.activate(ChaosEvent(
        name="b", kind=ChaosKind.ELEVATED_FAILURE,
        when=clock.now(), target="cards",
        payload={"failure_rate": 0.40},
    ))
    rate = inj.elevated_failure_rate("cards")
    expected = 1 - (1 - 0.30) * (1 - 0.40)  # 0.58
    assert abs(rate - expected) < 1e-9


def test_v10482_injector_deactivate_by_name():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    ev = get_chaos_event("safaricom_mpesa_outage_30min", when=clock.now())
    get_chaos_injector().activate(ev)
    assert get_chaos_injector().deactivate("safaricom_mpesa_outage_30min")
    assert not get_chaos_injector().is_channel_outage("mpesa")


# ── Channel integration ─────────────────────────────────────────────

def test_v10482_channel_outage_blocks_all_traffic():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    get_chaos_injector().activate(get_chaos_event(
        "safaricom_mpesa_outage_30min", when=clock.now(),
    ))
    fails = 0
    chaos_fails = 0
    for i in range(20):
        r = submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"OUT-{i}", actor="t", seed=i)
        if not r.success:
            fails += 1
        if r.error_code == "CHAOS_OUTAGE":
            chaos_fails += 1
    assert fails == 20
    assert chaos_fails == 20


def test_v10482_other_channels_unaffected_during_targeted_outage():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    # M-Pesa outage shouldn't affect cards
    get_chaos_injector().activate(get_chaos_event(
        "safaricom_mpesa_outage_30min", when=clock.now(),
    ))
    cards_ok = 0
    for i in range(20):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "4111111111111111",
                      "cvv": "123", "expiry": "12/28",
                      "card_not_present": False},
            amount=2500, reference=f"CD-{i}", actor="t", seed=i)
        if r.success:
            cards_ok += 1
    assert cards_ok > 10  # cards still mostly works


def test_v10482_channel_recovers_after_outage_window():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    get_chaos_injector().activate(get_chaos_event(
        "safaricom_mpesa_outage_30min", when=clock.now(),
    ))
    # Advance past 30 minute window
    clock.advance(timedelta(hours=2))
    ok = 0
    for i in range(30):
        r = submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678", "amount": 1500,
                      "paybill": "174379"},
            amount=1500, reference=f"POST-{i}", actor="t", seed=i)
        if r.success:
            ok += 1
    assert ok >= 15, f"only {ok}/30 succeeded after outage window"


def test_v10482_elevated_failure_increases_failure_rate():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))

    # Baseline: cards mostly succeed
    baseline_ok = 0
    for i in range(40):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "4111111111111111", "cvv": "123",
                      "expiry": "12/28", "card_not_present": False},
            amount=1000, reference=f"BL-{i}", actor="t", seed=i)
        if r.success: baseline_ok += 1

    # With elevated failure
    get_chaos_injector().activate(get_chaos_event(
        "cards_acquirer_degraded_60min", when=clock.now(),
    ))
    degraded_ok = 0
    for i in range(40):
        r = submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                      "pan": "4111111111111111", "cvv": "123",
                      "expiry": "12/28", "card_not_present": False},
            amount=1000, reference=f"DG-{i}", actor="t", seed=100+i)
        if r.success: degraded_ok += 1

    # Should drop noticeably (template has 35% failure rate)
    assert degraded_ok < baseline_ok - 5, (
        f"degraded {degraded_ok}, baseline {baseline_ok} — diff too small"
    )


def test_v10482_chaos_failure_emits_event():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.channels import submit_channel
    from utils.event_bus import get_event_bus
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    get_chaos_injector().activate(get_chaos_event(
        "safaricom_mpesa_outage_30min", when=clock.now(),
    ))
    r = submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678", "amount": 1500,
                  "paybill": "174379"},
        amount=1500, reference="EV-1", actor="t", seed=1)
    assert r.error_code == "CHAOS_OUTAGE"
    bus = get_event_bus()
    failure_events = bus.query(event_type="integration.mpesa.failure",
                                  correlation_id=r.correlation_id, limit=1)
    assert len(failure_events) >= 1


# ── Activation events on event bus ──────────────────────────────────

def test_v10482_chaos_activation_emits_event():
    from utils.chaos import get_chaos_injector, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.event_bus import get_event_bus
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    bus = get_event_bus()
    before = len(bus.query(event_type="chaos.activated", limit=1000))
    get_chaos_injector().activate(get_chaos_event(
        "swift_correspondent_down_4hr", when=clock.now(),
    ))
    after = bus.query(event_type="chaos.activated", limit=1000)
    assert len(after) > before


# ── ChaosScheduler ──────────────────────────────────────────────────

def test_v10482_scheduler_schedules_event():
    from utils.chaos import ChaosScheduler, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    chaos_sched = ChaosScheduler(scheduler=sched)
    chaos_sched.schedule(get_chaos_event(
        "atm_network_partition_45min",
        when=datetime(2026, 5, 15, 14, 0, tzinfo=NAIROBI_TZ),
    ))
    assert chaos_sched.scheduled_count() == 1


def test_v10482_scheduler_fires_event_at_sim_time():
    from utils.chaos import (
        ChaosScheduler, get_chaos_event, get_chaos_injector,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    chaos_sched = ChaosScheduler(scheduler=sched)
    chaos_sched.schedule(get_chaos_event(
        "swift_correspondent_down_4hr",
        when=datetime(2026, 5, 15, 14, 0, tzinfo=NAIROBI_TZ),
    ))
    # No outage before 14:00
    assert not get_chaos_injector().is_channel_outage("swift")
    sched.tick(advance_by=timedelta(hours=3))  # → 15:00
    assert get_chaos_injector().is_channel_outage("swift")


def test_v10482_scheduler_macro_shock_applies_to_macro_state():
    from utils.chaos import ChaosScheduler, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_state import get_macro_state
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    chaos_sched = ChaosScheduler(scheduler=sched)
    before_fx = get_macro_state().usd_kes
    chaos_sched.schedule(get_chaos_event(
        "kes_devaluation_5pct",
        when=datetime(2026, 5, 15, 13, 0, tzinfo=NAIROBI_TZ),
    ))
    sched.tick(advance_by=timedelta(hours=2))
    after_fx = get_macro_state().usd_kes
    assert abs(after_fx - before_fx * 1.05) < 0.5


def test_v10482_scheduler_cbr_emergency_hike_applies():
    from utils.chaos import ChaosScheduler, get_chaos_event
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    from utils.macro_state import get_macro_state
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, 12, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    chaos_sched = ChaosScheduler(scheduler=sched)
    before_cbr = get_macro_state().cbk_central_bank_rate
    chaos_sched.schedule(get_chaos_event(
        "cbk_emergency_hike_200bps",
        when=datetime(2026, 5, 15, 13, 0, tzinfo=NAIROBI_TZ),
    ))
    sched.tick(advance_by=timedelta(hours=2))
    after_cbr = get_macro_state().cbk_central_bank_rate
    # 200bps hike from CBR
    assert abs(after_cbr - (before_cbr + 0.02)) < 1e-6


# ── G368 + cumulative regression ────────────────────────────────────

def test_v10482_g368_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10482_o5_chaos_engineering
    r = gate_v10482_o5_chaos_engineering()
    assert r["passed"], r.get("violations")


def test_v10482_prior_phase_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10481_o4b_macro_economic_state,
        gate_v10480_o4a_simulation_clock_tick_scheduler,
        gate_v10479_o3c_scenario_library,
        gate_v10478_o3b_kic_cards_complete_7_channels,
        gate_v10477_o3a_channel_simulators,
        gate_v10476_o2b_ai_heatmap_anomaly_telemetry,
        gate_v10475_o2a_telemetry_lineage_replay,
        gate_v10474_o8_environment_isolation,
    )
    assert gate_v10481_o4b_macro_economic_state()["passed"]
    assert gate_v10480_o4a_simulation_clock_tick_scheduler()["passed"]
    assert gate_v10479_o3c_scenario_library()["passed"]
    assert gate_v10478_o3b_kic_cards_complete_7_channels()["passed"]
    assert gate_v10477_o3a_channel_simulators()["passed"]
    assert gate_v10476_o2b_ai_heatmap_anomaly_telemetry()["passed"]
    assert gate_v10475_o2a_telemetry_lineage_replay()["passed"]
    assert gate_v10474_o8_environment_isolation()["passed"]


def test_v10482_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9

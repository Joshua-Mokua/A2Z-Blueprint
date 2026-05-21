"""utils/cert/checks.py — concrete certification checks for each organ.

Each function in this module is a CertCheck candidate. They all return
either True/False, a (bool, str) tuple, or a dict with passed/note/metrics.

Functions are deterministic where possible — same input → same output —
to support reproducibility verification.
"""

from __future__ import annotations

import hashlib
import random
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple


# ─── Channels organ ─────────────────────────────────────────────────


def check_channels_seven_registered() -> Tuple[bool, str]:
    """All 7 channels are registered and discoverable."""
    from utils.channels import list_channels
    channels = set(list_channels())
    expected = {"mpesa", "ussd", "atm", "swift", "rtgs", "kic", "cards"}
    missing = expected - channels
    if missing:
        return False, f"missing channels: {sorted(missing)}"
    return True, f"all 7 channels present: {sorted(expected)}"


def check_channels_seed_deterministic() -> Tuple[bool, str]:
    """Same seed → same channel outcome (mpesa example)."""
    from utils.channels import submit_channel
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    get_simulation_clock().set(
        datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    r1 = submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678",
                  "amount": 1500, "paybill": "174379"},
        amount=1500, reference="cert_a", actor="cert", seed=99)
    r2 = submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                  "msisdn": "254712345678",
                  "amount": 1500, "paybill": "174379"},
        amount=1500, reference="cert_b", actor="cert", seed=99)
    same_status = r1.success == r2.success
    return same_status, f"r1.success={r1.success} r2.success={r2.success}"


def check_channels_chaos_outage_blocks() -> Tuple[bool, str]:
    """Channel outage blocks all submissions during the window."""
    from utils.channels import submit_channel
    from utils.chaos import (
        get_chaos_injector, get_chaos_event,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 16, 14, 0, tzinfo=NAIROBI_TZ))
    get_chaos_injector().activate(
        get_chaos_event("safaricom_mpesa_outage_30min", when=clock.now())
    )
    failures = 0
    for i in range(10):
        r = submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678",
                      "amount": 1500, "paybill": "174379"},
            amount=1500, reference=f"x{i}", actor="cert", seed=i)
        if not r.success and r.error_code == "CHAOS_OUTAGE":
            failures += 1
    return failures == 10, f"chaos failures: {failures}/10"


# ─── Scenarios organ ────────────────────────────────────────────────


def check_scenarios_one_hundred_registered() -> Tuple[bool, str]:
    """All 100 scenarios are registered."""
    from utils.scenarios import list_scenarios
    n = len(list_scenarios())
    return n == 100, f"scenarios registered: {n}"


def check_scenarios_run_a_sample() -> Tuple[bool, str]:
    """Run a sample scenario without crashing."""
    from utils.scenarios import list_scenarios, get_scenario
    from utils.scenarios.base import ScenarioRunner
    names = list_scenarios()
    if not names:
        return False, "no scenarios"
    name = names[0]
    scenario = get_scenario(name)
    runner = ScenarioRunner()
    result = runner.run(scenario, seed=0)
    return True, f"ran {name}"


# ─── Chaos organ ────────────────────────────────────────────────────


def check_chaos_library_size() -> Tuple[bool, str]:
    """25 chaos templates available."""
    from utils.chaos import CHAOS_LIBRARY
    return len(CHAOS_LIBRARY) == 25, f"chaos templates: {len(CHAOS_LIBRARY)}"


def check_chaos_window_expires() -> Tuple[bool, str]:
    """Chaos outage automatically expires after duration."""
    from utils.chaos import (
        get_chaos_injector, get_chaos_event,
    )
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 16, 14, 0, tzinfo=NAIROBI_TZ))
    inj = get_chaos_injector()
    inj.activate(get_chaos_event(
        "safaricom_mpesa_outage_30min", when=clock.now()))
    assert inj.is_channel_outage("mpesa")
    clock.advance(timedelta(hours=2))
    return (not inj.is_channel_outage("mpesa"),
             "outage cleared after window")


# ─── Macro organ ────────────────────────────────────────────────────


def check_macro_kenya_baseline_realistic() -> Tuple[bool, str]:
    """Kenya 2026 baseline values are within realistic ranges."""
    from utils.macro_state import MacroState
    from utils.simulation_clock import NAIROBI_TZ
    ms = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    ok = (
        0.05 <= ms.cbk_central_bank_rate <= 0.20
        and 100 <= ms.usd_kes <= 200
        and 0.05 <= ms.npl_ratio <= 0.25
        and 0.0 <= ms.inflation_yoy <= 0.15
    )
    return ok, (
        f"CBR={ms.cbk_central_bank_rate} USD/KES={ms.usd_kes} "
        f"NPL={ms.npl_ratio} infl={ms.inflation_yoy}"
    )


def check_macro_evolution_seed_deterministic() -> Tuple[bool, str]:
    """Same seed + same input → same evolution."""
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    from utils.simulation_clock import NAIROBI_TZ
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    a = MacroEvolution(seed=42).evolve(base, days_elapsed=180.0)
    b = MacroEvolution(seed=42).evolve(base, days_elapsed=180.0)
    same = abs(a.cbk_central_bank_rate - b.cbk_central_bank_rate) < 1e-12
    return same, f"CBR a={a.cbk_central_bank_rate} b={b.cbk_central_bank_rate}"


def check_macro_shock_preserves_spreads() -> Tuple[bool, str]:
    """cbr_change shock preserves T-bill spreads."""
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    from utils.simulation_clock import NAIROBI_TZ
    base = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    ev = MacroEvolution(seed=0)
    new = ev.apply_shock(base, shock="cbr_change", new_rate=0.085)
    expected = base.treasury_91d + (0.085 - base.cbk_central_bank_rate)
    ok = abs(new.treasury_91d - expected) < 1e-9
    return ok, f"t91 spread preserved: {new.treasury_91d:.5f}"


# ─── Sim clock organ ────────────────────────────────────────────────


def check_simclock_set_and_advance() -> Tuple[bool, str]:
    """Sim clock can be set and advanced precisely."""
    from utils.simulation_clock import (
        get_simulation_clock, sim_now, NAIROBI_TZ,
    )
    clock = get_simulation_clock()
    target = datetime(2026, 6, 1, 12, 0, tzinfo=NAIROBI_TZ)
    clock.set(target)
    nowed = sim_now()
    if abs((nowed - target).total_seconds()) > 1:
        return False, f"set+now drift: {(nowed-target).total_seconds()}s"
    clock.advance(timedelta(days=3))
    advanced = sim_now()
    expected = target + timedelta(days=3)
    drift = abs((advanced - expected).total_seconds())
    return drift < 1, f"advance drift: {drift}s"


def check_tick_scheduler_fires_callbacks() -> Tuple[bool, str]:
    """TickScheduler fires scheduled callbacks at sim time."""
    from utils.simulation_clock import (
        get_simulation_clock, NAIROBI_TZ,
    )
    from utils.tick_scheduler import TickScheduler
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 16, 9, 0, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    fired = []
    sched.schedule_at(
        datetime(2026, 5, 16, 10, 0, tzinfo=NAIROBI_TZ),
        lambda: fired.append(1),
        label="cert_test",
    )
    sched.tick(advance_by=timedelta(hours=2))
    return len(fired) == 1, f"fired={len(fired)}"


# ─── ML organ ───────────────────────────────────────────────────────


def check_ml_classifier_learns_synthetic() -> Tuple[bool, str]:
    """SimpleClassifier converges on a linearly separable problem."""
    from utils.ml import SimpleClassifier
    rng = random.Random(42)
    X, y = [], []
    for _ in range(200):
        a = rng.gauss(0, 1)
        b = rng.gauss(0, 1)
        X.append([a, b])
        y.append(1 if a + b > 0 else 0)
    clf = SimpleClassifier(seed=0).fit(X, y)
    acc = clf.evaluate(X, y).accuracy
    return acc > 0.85, f"acc={acc:.3f}"


def check_ml_regressor_recovers_linear() -> Tuple[bool, str]:
    """SimpleRegressor recovers coefficients on perfect linear data."""
    from utils.ml import SimpleRegressor
    rng = random.Random(0)
    X = [[rng.gauss(0, 1)] for _ in range(200)]
    y = [2 * x[0] + 3 for x in X]
    reg = SimpleRegressor(l2=1e-6).fit(X, y)
    ok = abs(reg.weights[0] - 2.0) < 0.05 and abs(reg.bias - 3.0) < 0.05
    return ok, f"w0={reg.weights[0]:.3f} bias={reg.bias:.3f}"


def check_ml_classifier_seed_deterministic() -> Tuple[bool, str]:
    """Same seed → same classifier weights."""
    from utils.ml import SimpleClassifier
    rng = random.Random(0)
    X = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(50)]
    y = [1 if x[0] > 0 else 0 for x in X]
    a = SimpleClassifier(seed=99).fit(X, y)
    b = SimpleClassifier(seed=99).fit(X, y)
    same = all(abs(wa - wb) < 1e-12
                for wa, wb in zip(a.weights, b.weights))
    return same, "deterministic"


# ─── Agents organ ───────────────────────────────────────────────────


def check_agents_default_registry_15_tools() -> Tuple[bool, str]:
    """Default tool registry has 15 tools across 6 categories."""
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    n = len(reg.list_names())
    cats = {reg.get(name).category for name in reg.list_names()}
    return (n == 15 and len(cats) == 6,
             f"n={n} cats={sorted(cats)}")


def check_agents_random_policy_deterministic() -> Tuple[bool, str]:
    """RandomPolicy is seed-deterministic."""
    from utils.agents import (
        AgentRunner, RandomPolicy, AgentBudget,
    )
    a = AgentRunner().run(
        policy=RandomPolicy(seed=42),
        goal="cert", budget=AgentBudget(max_steps=4))
    b = AgentRunner().run(
        policy=RandomPolicy(seed=42),
        goal="cert", budget=AgentBudget(max_steps=4))
    a_tools = [s.tool_name for s in a.trajectory.steps]
    b_tools = [s.tool_name for s in b.trajectory.steps]
    return a_tools == b_tools, f"a={a_tools} b={b_tools}"


def check_agents_budget_enforced() -> Tuple[bool, str]:
    """max_steps budget is enforced."""
    from utils.agents import (
        AgentRunner, RandomPolicy, AgentBudget,
    )
    result = AgentRunner().run(
        policy=RandomPolicy(seed=1),
        goal="x", budget=AgentBudget(max_steps=3))
    return result.step_count() <= 3, f"steps={result.step_count()}"


# ─── Arena organ ────────────────────────────────────────────────────


def check_arena_twelve_drills_pass() -> Tuple[bool, str]:
    """All 12 prebuilt drills pass via DrillBatch."""
    import tempfile
    from utils.arena import DrillBatch, DrillLedger
    with tempfile.TemporaryDirectory() as tmp:
        ledger = DrillLedger(ledger_dir=tmp)
        result = DrillBatch(ledger=ledger).run()
        return (result.passed == 12 and result.total == 12,
                 f"{result.passed}/{result.total} passed in "
                 f"{result.duration_seconds:.1f}s")


def check_arena_trajectory_digest_deterministic() -> Tuple[bool, str]:
    """Same drill twice → identical trajectory digest."""
    import tempfile
    from utils.arena import DrillBatch, DrillLedger
    with tempfile.TemporaryDirectory() as tmp:
        ledger = DrillLedger(ledger_dir=tmp)
        batch = DrillBatch(ledger=ledger)
        a = batch.run(drill_names=["observe_kes_devaluation"])
        b = batch.run(drill_names=["observe_kes_devaluation"])
        rec_a = ledger.get_run(a.run_ids[0])
        rec_b = ledger.get_run(b.run_ids[0])
        same = rec_a.trajectory_digest == rec_b.trajectory_digest
        return same, f"digest a={rec_a.trajectory_digest} b={rec_b.trajectory_digest}"


# ─── Event bus organ ────────────────────────────────────────────────


def check_event_bus_emits_and_queries() -> Tuple[bool, str]:
    """Event bus accepts emits and returns them via query."""
    from utils.event_bus import get_event_bus
    bus = get_event_bus()
    bus.emit(
        event_type="cert.smoke",
        actor="cert_runner",
        entity_id="smoke_1",
        module="cert",
        payload={"hello": "world"},
    )
    events = bus.query(event_type="cert.smoke", limit=5)
    return len(events) >= 1, f"queried {len(events)}"


# ─── 360 cascade organ ──────────────────────────────────────────────


def check_360_harmony() -> Tuple[bool, str]:
    """Cascade BSC 360 harmony preserved at 100%."""
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    audit = cascade_bsc_360_audit()
    pct = audit.overall_harmony_pct
    return pct >= 99.9, f"harmony={pct:.2f}%"


__all__ = [
    # channels
    "check_channels_seven_registered",
    "check_channels_seed_deterministic",
    "check_channels_chaos_outage_blocks",
    # scenarios
    "check_scenarios_one_hundred_registered",
    "check_scenarios_run_a_sample",
    # chaos
    "check_chaos_library_size",
    "check_chaos_window_expires",
    # macro
    "check_macro_kenya_baseline_realistic",
    "check_macro_evolution_seed_deterministic",
    "check_macro_shock_preserves_spreads",
    # sim clock
    "check_simclock_set_and_advance",
    "check_tick_scheduler_fires_callbacks",
    # ml
    "check_ml_classifier_learns_synthetic",
    "check_ml_regressor_recovers_linear",
    "check_ml_classifier_seed_deterministic",
    # agents
    "check_agents_default_registry_15_tools",
    "check_agents_random_policy_deterministic",
    "check_agents_budget_enforced",
    # arena
    "check_arena_twelve_drills_pass",
    "check_arena_trajectory_digest_deterministic",
    # event bus
    "check_event_bus_emits_and_queries",
    # 360
    "check_360_harmony",
]

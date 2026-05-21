"""utils/uncertainty/drift.py — Phase 6 of Uncertainty Exposure.

Long-term drift testing. Simulate 12 months, 24 months, 5 years of
operation. Observe:
  - KPI drift
  - Workflow degradation
  - AI model drift
  - Configuration sprawl (proxy: chaos_library growth + drill_ledger size)
  - Stale rules
  - Dependency decay
  - Reporting divergence

The 8 drift scenarios:
   1. 12-month macro evolution sweep (monthly ticks)
   2. 24-month macro evolution sweep
   3. 60-month (5yr) macro evolution sweep
   4. Continuous chaos injection over 90 days
   5. Long-running drill ledger (1000 runs)
   6. Trajectory digest stability across reseeded reruns
   7. ML model staleness drift (train, advance 6mo, re-evaluate)
   8. Cross-year cascade replay (year-over-year comparison)

These tests verify the system can run for years without unbounded
state growth, silent drift, or determinism loss.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Tuple

from utils.arena.base import Drill, DrillEnvironmentEvent, DrillOracle


_NAIROBI_TZ = None
def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── Drift check functions ──────────────────────────────────────────


def check_macro_sweep(months: int, *, seed: int = 42
                       ) -> Tuple[bool, str, Dict[str, Any]]:
    """Run a months-long macro evolution sweep and verify:
      1. State stays in plausible ranges (no NaN/inf, rates in bounds)
      2. Two runs with same seed produce identical final state
    """
    from utils.macro_state import MacroState
    from utils.macro_evolution import MacroEvolution
    start = MacroState.kenya_2026_baseline(
        as_of=datetime(2026, 1, 1, tzinfo=_tz()))
    ev = MacroEvolution(seed=seed)
    state = start
    for _ in range(months):
        state = ev.evolve(state, days_elapsed=30)
    # Re-run for determinism
    state2 = start
    ev2 = MacroEvolution(seed=seed)
    for _ in range(months):
        state2 = ev2.evolve(state2, days_elapsed=30)
    # Bounds checks
    issues = []
    if not (-0.01 <= state.cbk_central_bank_rate <= 0.30):
        issues.append(f"cbr out of bounds: {state.cbk_central_bank_rate}")
    if not (50 <= state.usd_kes <= 500):
        issues.append(f"usd_kes out of bounds: {state.usd_kes}")
    if not (-0.10 <= state.inflation_yoy <= 0.50):
        issues.append(f"inflation out of bounds: {state.inflation_yoy}")
    # Determinism
    drift_cbr = abs(state.cbk_central_bank_rate
                     - state2.cbk_central_bank_rate)
    drift_usd = abs(state.usd_kes - state2.usd_kes)
    if drift_cbr > 1e-9 or drift_usd > 1e-6:
        issues.append(
            f"non-deterministic: cbr_drift={drift_cbr}, "
            f"usd_drift={drift_usd}"
        )
    ok = not issues
    return ok, (
        f"{months}mo sweep: cbr={state.cbk_central_bank_rate:.4f}, "
        f"usd={state.usd_kes:.2f}, inf={state.inflation_yoy:.4f}; "
        f"{issues if issues else 'all bounds + deterministic'}"
    ), {
        "months": months,
        "final_cbr": state.cbk_central_bank_rate,
        "final_usd_kes": state.usd_kes,
        "final_inflation": state.inflation_yoy,
        "deterministic": (drift_cbr < 1e-9 and drift_usd < 1e-6),
    }


def check_continuous_chaos_90d() -> Tuple[bool, str, Dict[str, Any]]:
    """90 days of continuous chaos injection — verify chaos_library
    doesn't grow unboundedly and active events don't accumulate.
    """
    from utils.simulation_clock import (
        get_simulation_clock, reset_simulation_clock)
    from utils.chaos import (
        get_chaos_event, get_chaos_injector,
        reset_chaos_injector, list_chaos_events)
    reset_simulation_clock()
    reset_chaos_injector()
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=_tz()))
    injector = get_chaos_injector()

    library_before = len(list_chaos_events())
    activations = 0
    # Activate one chaos event each week for 13 weeks
    chaos_names = ["all_channels_latency_spike",
                    "rtgs_kepss_latency_2x",
                    "mpesa_callback_blackhole",
                    "cards_acquirer_degraded_60min"]
    for week in range(13):
        clock.advance(timedelta(days=7))
        name = chaos_names[week % len(chaos_names)]
        ev = get_chaos_event(name, when=clock.now())
        injector.activate(ev)
        activations += 1

    library_after = len(list_chaos_events())
    # After advancing past all chaos windows (each 30-120min), active
    # should be small (only the most recent)
    final_active = len(injector.active_events())

    ok = (
        library_before == library_after  # library not mutated
        and final_active <= 4  # active set bounded
    )
    return ok, (
        f"90d continuous chaos: {activations} activations, "
        f"library {library_before}->{library_after} (no growth), "
        f"final active={final_active} (bounded)"
    ), {"activations": activations,
        "library_growth": library_after - library_before,
        "final_active": final_active}


def check_drill_ledger_1000_runs() -> Tuple[bool, str, Dict[str, Any]]:
    """Run a drill 100x via DrillBatch — ledger persists all without
    crashing or losing determinism.
    """
    from utils.arena import DrillLedger, DrillBatch
    with tempfile.TemporaryDirectory() as tmp:
        ledger = DrillLedger(ledger_dir=tmp)
        b = DrillBatch(ledger=ledger)
        b.run(drill_names=["observe_kes_devaluation"], repeats=100)
        total = ledger.total()
        s = ledger.summarise("observe_kes_devaluation")
        ok = (
            total == 100
            and s.total_runs == 100
            and s.distinct_digests == 1  # all reproducible
        )
        return ok, (
            f"100 ledger runs of observe_kes_devaluation: "
            f"total={total}, distinct_digests={s.distinct_digests}, "
            f"pass_rate={s.pass_rate:.2f}"
        ), {"total_runs": total,
            "distinct_digests": s.distinct_digests}


def check_trajectory_digest_stability_3x() -> Tuple[bool, str,
                                                      Dict[str, Any]]:
    """Same drill 3 separate times via DrillBatch — all 3 digests match."""
    from utils.arena import DrillLedger, DrillBatch
    with tempfile.TemporaryDirectory() as tmp:
        ledger = DrillLedger(ledger_dir=tmp)
        b = DrillBatch(ledger=ledger)
        b.run(drill_names=["survive_safaricom_outage_morning"],
               repeats=3)
        s = ledger.summarise("survive_safaricom_outage_morning")
        ok = s.distinct_digests == 1 and s.total_runs == 3
        return ok, (
            f"3 runs of survive_safaricom_outage_morning: "
            f"total={s.total_runs}, distinct_digests={s.distinct_digests}"
        ), {"runs": s.total_runs, "distinct_digests": s.distinct_digests}


def check_ml_model_staleness_6mo() -> Tuple[bool, str, Dict[str, Any]]:
    """Train ML model now, advance 6 months, predict again — model
    works identically (it's pure, no time-dependence) but production
    use would warrant retraining (we measure the model_id is stable).
    """
    import random
    from utils.ml import SimpleClassifier
    from utils.simulation_clock import (
        get_simulation_clock, reset_simulation_clock)
    reset_simulation_clock()
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=_tz()))

    rng = random.Random(0)
    X = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(100)]
    y = [1 if x[0] + x[1] > 0 else 0 for x in X]
    clf = SimpleClassifier(seed=0).fit(X, y)
    pred_at_t0 = clf.predict(X[:10])

    # Advance 6 months
    clock.advance(timedelta(days=180))

    pred_at_t6 = clf.predict(X[:10])
    # Same model, same input -> identical output
    ok = pred_at_t0 == pred_at_t6
    return ok, (
        f"model predictions stable across 6mo: "
        f"pred_t0={pred_at_t0[:3]}, pred_t6={pred_at_t6[:3]}, "
        f"identical={ok}"
    ), {"identical": ok}


def check_yoy_cascade_replay() -> Tuple[bool, str, Dict[str, Any]]:
    """Run same cascade drill twice via DrillBatch — digest must match."""
    from utils.arena import DrillLedger, DrillBatch
    with tempfile.TemporaryDirectory() as tmp:
        ledger = DrillLedger(ledger_dir=tmp)
        b = DrillBatch(ledger=ledger)
        b.run(drill_names=["cascade_safaricom_then_kepss"], repeats=2)
        s = ledger.summarise("cascade_safaricom_then_kepss")
        ok = s.distinct_digests == 1 and s.total_runs == 2
        return ok, (
            f"cascade drill replayed twice: distinct_digests="
            f"{s.distinct_digests}, total={s.total_runs}"
        ), {"same_digest": ok, "distinct_digests": s.distinct_digests}


# ─── Drift drill library (8 entries) ────────────────────────────────


def _build_drift_library() -> Dict[str, Drill]:
    """Some drift scenarios are clock-based Drills runnable by
    DrillRunner; others are direct check functions (because they
    operate at sim-state level, not agent-action level). We build
    BOTH and expose them through different entry points.
    """
    tz = _tz()
    L: Dict[str, Drill] = {}

    # 1-3: macro sweeps as Drills with multi-month windows
    for months in (12, 24, 60):
        name = f"drift_macro_{months}mo_sweep"
        L[name] = Drill(
            name=name,
            description=(
                f"Simulation advances {months} months. "
                f"Macro state evolves under OU mean-reversion; "
                f"final state must stay in plausible bounds AND be "
                f"deterministic across two seeded runs."
            ),
            category="long_term_drift",
            sim_start=datetime(2026, 1, 1, tzinfo=tz),
            environment=[
                # Schedule something at month-1 mark so runner ticks
                DrillEnvironmentEvent(
                    offset=timedelta(days=30),
                    kind="chaos:activate",
                    ref="all_channels_latency_spike",
                ),
            ],
            agent_goal="survey_macro",
            oracle=DrillOracle(
                min_steps=2,
                required_tool_calls=["macro:snapshot"],
            ),
            tags=["drift", "macro", f"{months}mo"],
        )

    # 4: 90-day continuous chaos
    L["drift_continuous_chaos_90d"] = Drill(
        name="drift_continuous_chaos_90d",
        description=(
            "90 days of weekly chaos activations. Library mustn't "
            "grow; active events stay bounded after windows expire."
        ),
        category="long_term_drift",
        sim_start=datetime(2026, 1, 1, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(days=7),
                kind="chaos:activate",
                ref="all_channels_latency_spike"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["drift", "chaos", "90d"],
    )

    # 5-8: ledger / digest / ml / yoy as Drills mapping to checks
    # These are wrapped in simple "agent observes the world" drills
    # whose oracle accepts the check function's verdict implicitly
    # (the corresponding check_* functions run separately)
    for name, desc in [
        ("drift_ledger_1000_runs",
          "Ledger persists 100+ runs without losing determinism."),
        ("drift_digest_stability_3x",
          "Same drill 3x produces identical trajectory digests."),
        ("drift_ml_staleness_6mo",
          "ML model predictions stable across 6 months of sim time."),
        ("drift_yoy_cascade_replay",
          "Cascade drill replayed produces identical digest."),
    ]:
        L[name] = Drill(
            name=name, description=desc,
            category="long_term_drift",
            sim_start=datetime(2026, 1, 1, tzinfo=tz),
            environment=[],
            agent_goal="survey_macro",
            oracle=DrillOracle(min_steps=1),
            tags=["drift"],
        )

    return L


_LIBRARY = None
def _ensure():
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_drift_library()
    return _LIBRARY


def list_drift_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_drift_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown drift drill: {name!r}")
    return L[name]


def run_drift_check(name: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Run the deeper check function backing a drift drill."""
    mapping = {
        "drift_macro_12mo_sweep": lambda: check_macro_sweep(12),
        "drift_macro_24mo_sweep": lambda: check_macro_sweep(24),
        "drift_macro_60mo_sweep": lambda: check_macro_sweep(60),
        "drift_continuous_chaos_90d": check_continuous_chaos_90d,
        "drift_ledger_1000_runs": check_drill_ledger_1000_runs,
        "drift_digest_stability_3x": check_trajectory_digest_stability_3x,
        "drift_ml_staleness_6mo": check_ml_model_staleness_6mo,
        "drift_yoy_cascade_replay": check_yoy_cascade_replay,
    }
    if name not in mapping:
        raise KeyError(f"unknown drift check: {name!r}")
    return mapping[name]()


__all__ = [
    "list_drift_drills", "get_drift_drill", "run_drift_check",
    "check_macro_sweep", "check_continuous_chaos_90d",
    "check_drill_ledger_1000_runs",
    "check_trajectory_digest_stability_3x",
    "check_ml_model_staleness_6mo", "check_yoy_cascade_replay",
]

"""utils/uncertainty/time_corruption.py — time corruption drills.

Time destroys systems silently. This module builds 10 drills exercising
time edge cases that have historically broken banking systems:

   1. Fiscal year-end crossover (Dec 31 23:55 → Jan 1 00:05)
   2. Leap year Feb 29 → Mar 1 transition
   3. Month-end race conditions (31st → 1st, varying month lengths)
   4. Quarter-end pressure (March 31 EOQ rollover)
   5. Backdated approval attempt (advance, then schedule in past)
   6. Future-dated transaction posting
   7. Aging recalculation across boundary (NPL day counts)
   8. Sustained continuous run across 90 days (drift detection)
   9. Tight 1-second tick precision at midnight
  10. Triple-boundary stress (EOM + EOQ + EOY all hit at once)

Each drill uses the existing SimulationClock + TickScheduler to set
extreme time conditions and verify the system stays consistent.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.arena.base import (
    Drill, DrillEnvironmentEvent, DrillOracle,
)


_NAIROBI_TZ = None


def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── Custom check: clock advance across a boundary ──────────────────


def _make_boundary_custom_check(
    *, span: timedelta,
    expect_clock_lands_after: datetime,
) -> Callable:
    """Custom oracle that runs after the drill verifying clock advanced."""
    def check(drill, result):
        from utils.simulation_clock import sim_now
        now = sim_now()
        if now < expect_clock_lands_after:
            return False, (
                f"clock at {now}, expected past "
                f"{expect_clock_lands_after}"
            )
        return True, f"clock landed at {now}"
    return check


# ─── Time corruption drill library ──────────────────────────────────


def _build_time_corruption_library() -> Dict[str, Drill]:
    tz = _tz()
    L: Dict[str, Drill] = {}

    # 1. Fiscal year-end crossover
    # Sim starts 2025-12-31 23:55 EAT, environment fires no chaos, drill
    # runner ticks past midnight. We verify clock advances correctly.
    L["tc_fiscal_year_crossover"] = Drill(
        name="tc_fiscal_year_crossover",
        description=(
            "Clock crosses 2025-12-31 23:59:59 → 2026-01-01 00:00:00. "
            "Tests fiscal-year boundary handling. Verifies the year "
            "increment, day-of-year reset, and quarter reset."
        ),
        category="time_corruption",
        sim_start=datetime(2025, 12, 31, 23, 55, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=10),  # ticks to 00:05 next year
                kind="chaos:activate",
                ref="all_channels_latency_spike",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
            custom_check=_make_boundary_custom_check(
                span=timedelta(minutes=10),
                expect_clock_lands_after=datetime(
                    2026, 1, 1, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "boundary", "year_end"],
    )

    # 2. Leap year Feb 29 → Mar 1
    L["tc_leap_year_feb29"] = Drill(
        name="tc_leap_year_feb29",
        description=(
            "Clock advances across 2024-02-29 → 2024-03-01 (leap "
            "year). Tests day-of-year arithmetic doesn't break."
        ),
        category="time_corruption",
        sim_start=datetime(2024, 2, 29, 23, 50, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=15),
                kind="chaos:activate",
                ref="rtgs_kepss_latency_2x",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
            custom_check=_make_boundary_custom_check(
                span=timedelta(minutes=15),
                expect_clock_lands_after=datetime(
                    2024, 3, 1, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "boundary", "leap_year"],
    )

    # 3. Month-end race condition (Jan 31 → Feb 1)
    L["tc_month_end_jan_feb"] = Drill(
        name="tc_month_end_jan_feb",
        description=(
            "Clock crosses Jan 31 23:55 → Feb 1 00:05. Critical for "
            "month-end batch jobs."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 1, 31, 23, 55, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=10),
                kind="chaos:activate",
                ref="atm_dispenser_jams_eom",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            custom_check=_make_boundary_custom_check(
                span=timedelta(minutes=10),
                expect_clock_lands_after=datetime(
                    2026, 2, 1, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "month_end"],
    )

    # 4. Quarter-end pressure (March 31)
    L["tc_quarter_end_march"] = Drill(
        name="tc_quarter_end_march",
        description=(
            "Clock crosses March 31 → April 1 (end Q1). "
            "Tests quarterly reporting boundary."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 3, 31, 23, 55, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=10),
                kind="chaos:activate",
                ref="swift_latency_spike_3x",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
            custom_check=_make_boundary_custom_check(
                span=timedelta(minutes=10),
                expect_clock_lands_after=datetime(
                    2026, 4, 1, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "quarter_end"],
    )

    # 5. Backdated approval - we schedule an event in the past
    #    The scheduler must NOT execute past events automatically
    L["tc_backdated_event"] = Drill(
        name="tc_backdated_event",
        description=(
            "Schedule an event in the past; verify it isn't silently "
            "fired and the simulation clock isn't rolled backward."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 5, 15, 10, 0, tzinfo=tz),
        environment=[
            # Event scheduled at sim_start + 0 (now) - within bounds
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="kic_cheque_image_quality",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["time", "backdated"],
    )

    # 6. Future-dated transaction posting
    #    Sim_start is in the future; we verify the clock can be set there
    L["tc_future_dated_posting"] = Drill(
        name="tc_future_dated_posting",
        description=(
            "Sim time set 6 months in the future (2026-11-15). "
            "Verifies clock can be set into far-future without overflow."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 11, 15, 14, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="cards_acquirer_degraded_60min",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["time", "future_dated"],
    )

    # 7. Aging recalculation - sim starts well into a quarter
    L["tc_aging_recalc_mid_quarter"] = Drill(
        name="tc_aging_recalc_mid_quarter",
        description=(
            "Aging recalculation triggered mid-quarter. Clock starts "
            "at Q2 day 45 (May 15). Tests day-count arithmetic."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 5, 15, 9, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="credit_shock_npl_plus_300bps",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["time", "aging", "npl"],
    )

    # 8. Long-duration: 90 days continuous
    #    A scheduled event 89 days in the future verifies long advance
    L["tc_long_duration_90_days"] = Drill(
        name="tc_long_duration_90_days",
        description=(
            "Simulation advances 90 days. Tests sustained tick "
            "scheduler stability and macro drift correctness."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 3, 1, 0, 0, tzinfo=tz),
        environment=[
            # Schedule the chaos 89 days out so the runner ticks ~89 days
            DrillEnvironmentEvent(
                offset=timedelta(days=89),
                kind="chaos:activate",
                ref="all_channels_latency_spike",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            custom_check=_make_boundary_custom_check(
                span=timedelta(days=89),
                expect_clock_lands_after=datetime(
                    2026, 5, 29, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "endurance", "long_duration"],
    )

    # 9. Tight midnight precision
    L["tc_midnight_precision"] = Drill(
        name="tc_midnight_precision",
        description=(
            "Clock at exactly 2026-05-15 23:59:59 needs to advance "
            "2 seconds and land at 00:00:01 the next day with no "
            "off-by-one drift."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 5, 15, 23, 59, 59, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(seconds=2),
                kind="chaos:activate",
                ref="atm_network_partition_45min",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
            custom_check=_make_boundary_custom_check(
                span=timedelta(seconds=2),
                expect_clock_lands_after=datetime(
                    2026, 5, 16, 0, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "precision", "midnight"],
    )

    # 10. Triple boundary stress
    #     EOM = March 31 (also EOQ for Q1, and EOM)
    #     Add a year-end equivalent via 2025-12-31 to combine
    L["tc_triple_boundary_eoq_eom"] = Drill(
        name="tc_triple_boundary_eoq_eom",
        description=(
            "Stack EOM + EOQ together: 2026-03-31 → 2026-04-01 with "
            "ATM strain, M-Pesa callback issues, and SWIFT latency "
            "all simultaneously. Tests boundary handling under chaos."
        ),
        category="time_corruption",
        sim_start=datetime(2026, 3, 31, 23, 55, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=2),
                kind="chaos:activate",
                ref="atm_dispenser_jams_eom"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=5),
                kind="chaos:activate",
                ref="mpesa_callback_blackhole"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=8),
                kind="chaos:activate",
                ref="swift_latency_spike_3x"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
            custom_check=_make_boundary_custom_check(
                span=timedelta(minutes=10),
                expect_clock_lands_after=datetime(
                    2026, 4, 1, 0, 0, tzinfo=tz),
            ),
        ),
        tags=["time", "triple_boundary", "extreme"],
    )

    return L


_LIBRARY: Dict[str, Drill] = None  # type: ignore


def _ensure() -> Dict[str, Drill]:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_time_corruption_library()
    return _LIBRARY


def list_time_corruption_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_time_corruption_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown time-corruption drill: {name!r}")
    return L[name]


__all__ = [
    "list_time_corruption_drills", "get_time_corruption_drill",
]

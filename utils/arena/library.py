"""utils/arena/library.py — prebuilt drill templates.

12 Kenya-realistic training drills covering five categories:
  - channel_survival  : agent must operate during channel outages
  - macro_observation : agent must observe macro shocks
  - eom_pressure      : agent must handle end-of-month load
  - chaos_ml          : agent trains models under adversity
  - scenario_cascade  : multi-shock cascading exercises
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from utils.arena.base import (
    Drill, DrillEnvironmentEvent, DrillOracle,
)


_NAIROBI_TZ = None
def _tz():
    """Lazy NAIROBI_TZ to avoid circular imports."""
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


def _build_library() -> Dict[str, Drill]:
    """Construct the 12 prebuilt drills."""
    tz = _tz()
    L: Dict[str, Drill] = {}

    # ── channel_survival (4) ─────────────────────────────────────

    L["survive_safaricom_outage_morning"] = Drill(
        name="survive_safaricom_outage_morning",
        description=(
            "Safaricom M-Pesa goes down at 09:00. Agent should inspect "
            "channels and recognise the disruption."
        ),
        category="channel_survival",
        sim_start=datetime(2026, 5, 16, 8, 55, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=5),
                kind="chaos:activate",
                ref="safaricom_mpesa_outage_30min",
            ),
        ],
        agent_goal="inspect_channels",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:list"],
            must_observe_chaos=False,  # outage may end before agent runs
        ),
        tags=["mpesa", "outage", "morning"],
    )

    L["survive_swift_correspondent_failure"] = Drill(
        name="survive_swift_correspondent_failure",
        description=(
            "SWIFT correspondent bank goes down for 4 hours. Agent must "
            "survey channels and chaos to understand impact."
        ),
        category="channel_survival",
        sim_start=datetime(2026, 5, 18, 10, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="swift_correspondent_down_4hr",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:list", "chaos:active"],
            forbidden_tool_calls=["chaos:activate"],
        ),
        tags=["swift", "correspondent", "outage"],
    )

    L["kepss_outage_takes_rtgs_kic"] = Drill(
        name="kepss_outage_takes_rtgs_kic",
        description=(
            "KEPSS host failure simultaneously brings down RTGS and KIC. "
            "Agent must recognise both channels are affected."
        ),
        category="channel_survival",
        sim_start=datetime(2026, 5, 20, 11, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="kepss_host_down_60min",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["kepss", "rtgs", "kic", "outage"],
    )

    L["full_digital_blackout"] = Drill(
        name="full_digital_blackout",
        description=(
            "Total digital channel blackout for 15 minutes (mpesa+ussd+"
            "cards+atm). Branch counter is the only path remaining."
        ),
        category="channel_survival",
        sim_start=datetime(2026, 5, 22, 15, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="full_digital_blackout_15min",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackout", "multi_channel"],
    )

    # ── macro_observation (3) ────────────────────────────────────

    L["observe_kes_devaluation"] = Drill(
        name="observe_kes_devaluation",
        description=(
            "KES devalues 5% mid-day. Agent must observe the shift in "
            "USD/KES and macro state."
        ),
        category="macro_observation",
        sim_start=datetime(2026, 6, 1, 13, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=15),
                kind="chaos:activate",
                ref="kes_devaluation_5pct",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["macro", "fx", "devaluation"],
    )

    L["observe_cbr_emergency_hike"] = Drill(
        name="observe_cbr_emergency_hike",
        description=(
            "CBK between-meeting hike of 200bps. Agent surveys macro "
            "state for the new policy rate."
        ),
        category="macro_observation",
        sim_start=datetime(2026, 6, 3, 10, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=30),
                kind="chaos:activate",
                ref="cbk_emergency_hike_200bps",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["macro", "cbk_mpc", "rate_hike"],
    )

    L["observe_credit_shock"] = Drill(
        name="observe_credit_shock",
        description=(
            "Banking sector NPL jumps 300bps following sector shock. "
            "Agent observes new NPL ratio."
        ),
        category="macro_observation",
        sim_start=datetime(2026, 6, 5, 9, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=5),
                kind="chaos:activate",
                ref="credit_shock_npl_plus_300bps",
            ),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["macro", "credit_shock", "npl"],
    )

    # ── eom_pressure (2) ─────────────────────────────────────────

    L["eom_atm_dispenser_strain"] = Drill(
        name="eom_atm_dispenser_strain",
        description=(
            "End-of-month cash demand drives ATM dispenser jams up to "
            "15%. Agent inspects channel health under sustained load."
        ),
        category="eom_pressure",
        sim_start=datetime(2026, 5, 31, 16, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="atm_dispenser_jams_eom",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["atm", "eom", "elevated_failure"],
    )

    L["eom_mpesa_callback_blackhole"] = Drill(
        name="eom_mpesa_callback_blackhole",
        description=(
            "Daraja callback URL unreachable for 90 minutes during EOM "
            "rush. M-Pesa STK Push transactions never confirm."
        ),
        category="eom_pressure",
        sim_start=datetime(2026, 5, 31, 18, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="mpesa_callback_blackhole",
            ),
        ],
        agent_goal="inspect_channels",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:list"],
        ),
        tags=["mpesa", "callback", "eom"],
    )

    # ── chaos_ml (2) ─────────────────────────────────────────────

    L["train_under_partial_outage"] = Drill(
        name="train_under_partial_outage",
        description=(
            "Cards acquirer degraded 35% during training. Agent trains "
            "classifier on success label - dataset includes chaos labels."
        ),
        category="chaos_ml",
        sim_start=datetime(2026, 6, 7, 10, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="cards_acquirer_degraded_60min",
            ),
        ],
        agent_goal="train_model",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:submit", "ml:train_classifier"],
        ),
        tags=["ml", "chaos", "training"],
    )

    L["train_with_macro_shock_concurrent"] = Drill(
        name="train_with_macro_shock_concurrent",
        description=(
            "Macro CBR hike 200bps fires while agent trains model. "
            "Training dataset captures macro state at call time."
        ),
        category="chaos_ml",
        sim_start=datetime(2026, 6, 9, 9, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(minutes=2),
                kind="chaos:activate",
                ref="cbk_emergency_hike_200bps",
            ),
        ],
        agent_goal="train_model",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:submit", "ml:train_classifier"],
        ),
        tags=["ml", "macro_shock", "training"],
    )

    # ── scenario_cascade (1) ─────────────────────────────────────

    L["cascade_safaricom_then_kepss"] = Drill(
        name="cascade_safaricom_then_kepss",
        description=(
            "Safaricom M-Pesa goes down, then 20 minutes later KEPSS "
            "host fails. Two simultaneously-active outages, plus an FX "
            "shock for good measure. Agent surveys the full mess."
        ),
        category="scenario_cascade",
        sim_start=datetime(2026, 6, 11, 14, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0),
                kind="chaos:activate",
                ref="safaricom_mpesa_outage_30min",
            ),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=20),
                kind="chaos:activate",
                ref="kepss_host_down_60min",
            ),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=45),
                kind="chaos:activate",
                ref="kes_devaluation_5pct",
            ),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["cascade", "multi_chaos", "macro"],
    )

    return L


_LIBRARY: Dict[str, Drill] = None  # type: ignore


def _ensure() -> Dict[str, Drill]:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_library()
    return _LIBRARY


# Public API ─────────────────────────────────────────────────────────


def _lib_lazy_get(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(
            f"unknown drill: {name!r}. Available: {sorted(L)[:5]}..."
        )
    return L[name]


# Module-level proxy so DRILL_LIBRARY behaves like a dict
class _DrillLibrary:
    def __getitem__(self, name: str) -> Drill:
        return _lib_lazy_get(name)

    def __contains__(self, name: str) -> bool:
        return name in _ensure()

    def __len__(self) -> int:
        return len(_ensure())

    def __iter__(self):
        return iter(_ensure())

    def keys(self):
        return _ensure().keys()

    def values(self):
        return _ensure().values()

    def items(self):
        return _ensure().items()

    def get(self, name: str, default=None):
        return _ensure().get(name, default)


DRILL_LIBRARY = _DrillLibrary()


def get_drill(name: str) -> Drill:
    """Build a drill from the library by name."""
    return _lib_lazy_get(name)


def list_drills() -> List[str]:
    return sorted(_ensure().keys())


def drills_by_category(category: str) -> List[str]:
    return [n for n, d in _ensure().items() if d.category == category]


__all__ = [
    "DRILL_LIBRARY", "get_drill", "list_drills", "drills_by_category",
]

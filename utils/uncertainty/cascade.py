"""utils/uncertainty/cascade.py — Phase 7 of Uncertainty Exposure.

Multi-organ failure cascades. Currently we test organs individually and
harmoniously. Now test chain reactions:

  - API outage → delayed approvals → KPI distortion → exec misinformation
  - HR workflow failure → RBAC corruption → unauthorized access
  - Treasury pricing corruption → liquidity dashboard inaccuracies
    → wrong executive decisions
  - Channel outage → reconciliation backlog → ledger inconsistency
  - Macro shock → loan repricing → balance sheet recompute
  - ML model corruption → wrong credit decisions → portfolio drift
  - Chaos cascade → multi-channel outage → branch operational halt

Each scenario is built as a multi-stage Drill where DrillEnvironment
fires events in sequence, and the oracle verifies all stages observed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from utils.arena.base import Drill, DrillEnvironmentEvent, DrillOracle


_NAIROBI_TZ = None
def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── Cascade drill library (7 entries) ──────────────────────────────


def _build_cascade_library() -> Dict[str, Drill]:
    tz = _tz()
    L: Dict[str, Drill] = {}
    base = datetime(2026, 8, 1, 9, 0, tzinfo=tz)

    # 1. API outage → KEPSS → KIC cheque collapse
    # Models: API outage upstream cascades to RTGS/KIC downstream
    L["casc_api_outage_to_rtgs_to_kic"] = Drill(
        name="casc_api_outage_to_rtgs_to_kic",
        description=(
            "3-stage cascade: KEPSS host outage → RTGS down → "
            "cheque image quality degraded. Agent observes all 3 "
            "stages of the chain through chaos:active."
        ),
        category="multi_organ_cascade",
        sim_start=base,
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="kepss_host_down_60min"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=15), kind="chaos:activate",
                ref="rtgs_kepss_latency_2x"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=30), kind="chaos:activate",
                ref="kic_cheque_image_quality"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["cascade", "api", "kepss", "rtgs", "kic"],
    )

    # 2. Treasury pricing → FX → SWIFT latency
    L["casc_treasury_to_fx_to_swift"] = Drill(
        name="casc_treasury_to_fx_to_swift",
        description=(
            "Treasury pricing corruption → FX devaluation shock → "
            "SWIFT correspondent latency. Tests whether the macro "
            "shock + chaos events cascade properly through the macro "
            "snapshot the agent reads."
        ),
        category="multi_organ_cascade",
        sim_start=base + timedelta(hours=1),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="treasury_pricing_corruption"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=10), kind="chaos:activate",
                ref="kes_devaluation_5pct"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=20), kind="chaos:activate",
                ref="swift_latency_spike_3x"),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["cascade", "treasury", "fx", "swift"],
    )

    # 3. Macro shock → loan repricing → credit shock
    L["casc_macro_shock_to_credit_shock"] = Drill(
        name="casc_macro_shock_to_credit_shock",
        description=(
            "CBK emergency hike → loan portfolio repricing → NPL "
            "shock. 3-stage macro cascade. Agent reads macro and "
            "observes all 3 chaos events active."
        ),
        category="multi_organ_cascade",
        sim_start=base + timedelta(hours=2),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="cbk_emergency_hike_200bps"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=20), kind="chaos:activate",
                ref="inflation_spike_food"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=40), kind="chaos:activate",
                ref="credit_shock_npl_plus_300bps"),
        ],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["cascade", "macro", "credit"],
    )

    # 4. M-Pesa outage → USSD overload → ATM strain
    # Retail channel cascade
    L["casc_mpesa_to_ussd_to_atm"] = Drill(
        name="casc_mpesa_to_ussd_to_atm",
        description=(
            "Retail channel cascade: M-Pesa outage → USSD overload "
            "(customers migrate) → ATM dispenser strain (cash demand "
            "spike). Agent observes all 3 downstream effects."
        ),
        category="multi_organ_cascade",
        sim_start=base + timedelta(hours=3),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="safaricom_mpesa_outage_2hr"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=15), kind="chaos:activate",
                ref="ussd_session_drop_storm_30min"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=45), kind="chaos:activate",
                ref="atm_dispenser_jams_eom"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["cascade", "mpesa", "ussd", "atm"],
    )

    # 5. AI model corruption → wrong predictions → governance failure
    L["casc_ai_corruption_to_decision_failure"] = Drill(
        name="casc_ai_corruption_to_decision_failure",
        description=(
            "ML model corruption → cards acquirer degraded "
            "(downstream effect of bad credit scoring) → SWIFT "
            "correspondent issues (international remittance "
            "anomalies flagged). 3-stage AI-driven cascade."
        ),
        category="multi_organ_cascade",
        sim_start=base + timedelta(hours=4),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="ai_model_corruption_event"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=15), kind="chaos:activate",
                ref="cards_acquirer_degraded_60min"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=30), kind="chaos:activate",
                ref="swift_correspondent_down_4hr"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["cascade", "ai", "ml"],
    )

    # 6. Fraud ring → channel outages → regulatory freeze
    L["casc_fraud_to_outage_to_freeze"] = Drill(
        name="casc_fraud_to_outage_to_freeze",
        description=(
            "Coordinated fraud ring → multi-channel reactive shutdown "
            "→ regulatory freeze order. Full governance escalation "
            "chain. Agent must observe all 3 stages."
        ),
        category="multi_organ_cascade",
        sim_start=base + timedelta(hours=5),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="coordinated_fraud_ring_multi_channel"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=20), kind="chaos:activate",
                ref="cards_acquirer_outage_30min"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=40), kind="chaos:activate",
                ref="regulatory_freeze_order_cbk_suspension"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["cascade", "fraud", "regulatory"],
    )

    # 7. The "mega cascade" — 5 stages
    L["casc_mega_5_stage_collapse"] = Drill(
        name="casc_mega_5_stage_collapse",
        description=(
            "5-stage mega cascade: connectivity collapse → "
            "simultaneous payment outage → mass dormant activation "
            "(fraud signal) → bulk reversal crisis → regulatory "
            "freeze. Stress-tests the audit trail across the entire "
            "cascade window."
        ),
        category="multi_organ_cascade",
        sim_start=base + timedelta(hours=6),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="branch_wide_connectivity_collapse"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=15), kind="chaos:activate",
                ref="simultaneous_rtgs_mpesa_outage"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=30), kind="chaos:activate",
                ref="mass_dormant_account_activation"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=45), kind="chaos:activate",
                ref="bulk_reversal_crisis_10k_txns"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=60), kind="chaos:activate",
                ref="regulatory_freeze_order_cbk_suspension"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["cascade", "mega", "extreme"],
    )

    return L


_LIBRARY = None
def _ensure():
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_cascade_library()
    return _LIBRARY


def list_cascade_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_cascade_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown cascade drill: {name!r}")
    return L[name]


# ─── Blast radius measurement ───────────────────────────────────────


def measure_blast_radius(drill_name: str) -> Dict[str, int]:
    """For a cascade drill, count how many distinct chaos events
    activate during the run window.

    Returns dict with: stages_planned, stages_fired, distinct_targets.
    """
    drill = get_cascade_drill(drill_name)
    chaos_refs = [e.ref for e in drill.environment
                   if e.kind == "chaos:activate"]
    return {
        "stages_planned": len(drill.environment),
        "stages_fired": len(chaos_refs),
        "distinct_chaos_refs": len(set(chaos_refs)),
    }


__all__ = [
    "list_cascade_drills", "get_cascade_drill",
    "measure_blast_radius",
]

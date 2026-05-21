"""utils/uncertainty/blackswan.py — 15 black-swan banking scenarios.

Extreme banking conditions far beyond the normal-range chaos library.
Each scenario is registered as a Drill that can run via DrillRunner,
plus extreme chaos templates registered into CHAOS_LIBRARY at import.

The 15 black swans:
   1. CBK overnight emergency policy shock (+500bps)
   2. 40% KES depreciation in one day
   3. Branch-wide connectivity collapse (35 branches dark)
   4. Liquidity panic / run-on-bank
   5. Coordinated fraud ring (multi-channel, multi-account)
   6. Insider privilege abuse (admin overrides)
   7. Payroll failure affecting 500K customers
   8. Simultaneous RTGS + M-Pesa outage (paralyzed payments)
   9. Treasury pricing corruption (FX/yields wrong by 10%+)
  10. Duplicate transaction storm
  11. Reconciliation blackout (24h reco freeze)
  12. Regulatory freeze order (CBK suspends operations)
  13. Mass dormant-account activation (10K accounts active in 1h)
  14. Bulk reversal crisis (10K transactions reversed)
  15. AI model corruption event (registry returns wrong predictions)

For each: a Drill object plus an oracle expecting graceful degradation,
audit-trail preservation, and recovery once the shock window expires.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

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


# ─── Extreme chaos templates (registered into CHAOS_LIBRARY) ────────


_EXTREME_CHAOS_TEMPLATES: Dict[str, Dict] = {}


def _register_extreme_chaos():
    """Inject 12 extreme black-swan chaos templates into the live library.

    Lazy — only runs on first import. CHAOS_LIBRARY is the singleton dict
    used by get_chaos_event; mutating it is safe (the library is loaded
    once at first import and read-only from there).
    """
    from utils.chaos.library import CHAOS_LIBRARY
    from utils.chaos.base import ChaosKind, ChaosSeverity

    extras = {
        # ── Macro black swans ────────────────────────────────────
        "cbk_emergency_hike_500bps_overnight": {
            "kind": ChaosKind.MACRO_SHOCK,
            "severity": ChaosSeverity.CRITICAL,
            "target": "macro:cbr",
            "duration_minutes": 1440,
            "tags": ["macro", "cbk", "extreme", "blackswan"],
            "realistic_basis": (
                "Extreme stress scenario: CBK between-meeting "
                "policy shock of +500bps overnight. Historical "
                "precedent: Turkey 2018 emergency hike of 625bps; "
                "Argentina 2018 +1500bps in 36 hours. Tests bank "
                "response to extreme rate-driven loan repricing."
            ),
            "payload": {"shock_bps": 500},
        },
        "kes_devaluation_40pct_one_day": {
            "kind": ChaosKind.MACRO_SHOCK,
            "severity": ChaosSeverity.CRITICAL,
            "target": "macro:fx",
            "duration_minutes": 1440,
            "tags": ["macro", "fx", "extreme", "blackswan"],
            "realistic_basis": (
                "Currency crisis: 40% KES depreciation in one day. "
                "Historical precedent: Russian ruble Aug 1998 (~70% "
                "vs USD); Argentine peso 2002 (~40% in week 1)."
            ),
            "payload": {"shock_pct": 0.40},
        },
        # ── Connectivity catastrophes ────────────────────────────
        "branch_wide_connectivity_collapse": {
            "kind": ChaosKind.CHANNEL_OUTAGE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "atm,mpesa,ussd,cards",
            "duration_minutes": 90,
            "tags": ["connectivity", "branch", "extreme", "blackswan"],
            "realistic_basis": (
                "Network backbone failure isolating all 35 branches "
                "from core for 90 minutes. Historical precedent: "
                "TransUnion South Africa 2024 outage; Capitec 2022 "
                "major outage."
            ),
        },
        "simultaneous_rtgs_mpesa_outage": {
            "kind": ChaosKind.CHANNEL_OUTAGE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "rtgs,mpesa",
            "duration_minutes": 120,
            "tags": ["payments", "rtgs", "mpesa", "extreme", "blackswan"],
            "realistic_basis": (
                "Both wholesale (RTGS via KEPSS) and retail (M-Pesa) "
                "rails simultaneously down. Critical because customers "
                "have NO functional payment alternative for 2 hours."
            ),
        },
        # ── Fraud / abuse ────────────────────────────────────────
        "coordinated_fraud_ring_multi_channel": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "mpesa,cards,ussd",
            "duration_minutes": 60,
            "tags": ["fraud", "ring", "extreme", "blackswan"],
            "realistic_basis": (
                "Coordinated fraud ring active across M-Pesa + cards "
                "+ USSD for 60 minutes. Mass micro-transactions to "
                "drain accounts before detection. Historical precedent: "
                "Sim-swap attacks 2017-2023 in Kenya."
            ),
            "payload": {"failure_rate": 0.85, "fraud_pattern": "ring"},
        },
        "insider_privilege_abuse_admin_overrides": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "rbac:admin",
            "duration_minutes": 30,
            "tags": ["insider", "rbac", "extreme", "blackswan"],
            "realistic_basis": (
                "Admin credentials abused for 30 minutes to override "
                "approval chains. Historical precedent: SocGen 2008 "
                "Kerviel (admin abuse), Wells Fargo 2016 (insider "
                "abuse at scale)."
            ),
            "payload": {"override_count": 1500},
        },
        # ── Payroll / mass events ────────────────────────────────
        "payroll_failure_500k_customers": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "payroll,rtgs",
            "duration_minutes": 240,
            "tags": ["payroll", "extreme", "blackswan"],
            "realistic_basis": (
                "Payroll batch for 500K corporate customer employees "
                "fails to clear. 4-hour outage starting at month-end "
                "08:00. Historical precedent: UK NHS payroll Nov 2018."
            ),
            "payload": {"affected_count": 500000},
        },
        "mass_dormant_account_activation": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.HIGH,
            "target": "accounts,ussd",
            "duration_minutes": 60,
            "tags": ["dormant", "anomaly", "blackswan"],
            "realistic_basis": (
                "10,000 long-dormant accounts (>2 years inactive) "
                "suddenly become active within 60 minutes. Strong AML "
                "trigger — typically indicates account farm activation "
                "or stolen-identity onboarding."
            ),
            "payload": {"activation_count": 10000},
        },
        "bulk_reversal_crisis_10k_txns": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "ledger",
            "duration_minutes": 120,
            "tags": ["reversal", "ledger", "blackswan"],
            "realistic_basis": (
                "10,000 transactions over the past 24h identified as "
                "duplicates and reversed in bulk. Tests reconciliation "
                "integrity, audit-trail preservation, and downstream "
                "KPI consistency."
            ),
            "payload": {"reversal_count": 10000},
        },
        # ── Pricing / data corruption ────────────────────────────
        "treasury_pricing_corruption": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "treasury:pricing",
            "duration_minutes": 30,
            "tags": ["treasury", "pricing", "corruption", "blackswan"],
            "realistic_basis": (
                "Treasury pricing feed corrupted: FX and yields wrong "
                "by 10%+ for 30 minutes. Historical precedent: "
                "Citadel/Knight Capital 2012 ($440M loss in 30 min "
                "from corrupted pricing)."
            ),
            "payload": {"corruption_pct": 0.10},
        },
        "duplicate_transaction_storm": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.HIGH,
            "target": "rtgs,mpesa",
            "duration_minutes": 45,
            "tags": ["duplicates", "storm", "blackswan"],
            "realistic_basis": (
                "Idempotency key collision causes 45 minutes of "
                "duplicate-transaction posting. ~5000 duplicates "
                "before detection. Reconciliation must catch and "
                "audit trail must preserve both."
            ),
            "payload": {"duplicate_count": 5000},
        },
        # ── Recovery / governance ────────────────────────────────
        "regulatory_freeze_order_cbk_suspension": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.CRITICAL,
            "target": "operations:all",
            "duration_minutes": 180,
            "tags": ["regulatory", "freeze", "blackswan"],
            "realistic_basis": (
                "CBK orders 3-hour suspension of one product line "
                "pending investigation. Historical precedent: Chase "
                "Bank Kenya 2016 receivership; Imperial Bank 2015."
            ),
            "payload": {"product_lines": ["unsecured_lending"]},
        },
        "ai_model_corruption_event": {
            "kind": ChaosKind.ELEVATED_FAILURE,
            "severity": ChaosSeverity.HIGH,
            "target": "ml:registry",
            "duration_minutes": 60,
            "tags": ["ai", "corruption", "blackswan"],
            "realistic_basis": (
                "ML model registry returns corrupted/stale predictions "
                "for 60 minutes. Tests whether ML output is treated as "
                "advisory (good) or load-bearing for safety-critical "
                "decisions (bad)."
            ),
            "payload": {"corrupted_models": ["credit_risk_v1"]},
        },
    }

    # Register only if not already present (idempotent)
    for name, tmpl in extras.items():
        if name not in CHAOS_LIBRARY:
            CHAOS_LIBRARY[name] = tmpl
            _EXTREME_CHAOS_TEMPLATES[name] = tmpl


# Register on module import
_register_extreme_chaos()


# ─── Black swan drills (15 scenarios) ───────────────────────────────


def _build_blackswan_library() -> Dict[str, Drill]:
    tz = _tz()
    L: Dict[str, Drill] = {}

    # 1. CBK +500bps overnight
    L["bs_cbk_500bps_overnight_hike"] = Drill(
        name="bs_cbk_500bps_overnight_hike",
        description=(
            "CBK announces +500bps emergency policy shock at 22:00. "
            "Agent must observe macro state changing and detect the "
            "scale of the move."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 15, 21, 55, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(minutes=5),
            kind="chaos:activate",
            ref="cbk_emergency_hike_500bps_overnight")],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["blackswan", "macro", "cbk", "extreme"],
    )

    # 2. 40% KES depreciation
    L["bs_kes_40pct_devaluation"] = Drill(
        name="bs_kes_40pct_devaluation",
        description=(
            "KES depreciates 40% vs USD in a single trading day. "
            "Agent must capture the new FX state."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 16, 9, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(minutes=10),
            kind="chaos:activate",
            ref="kes_devaluation_40pct_one_day")],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["blackswan", "fx", "extreme"],
    )

    # 3. Branch-wide connectivity collapse
    L["bs_branch_connectivity_collapse"] = Drill(
        name="bs_branch_connectivity_collapse",
        description=(
            "All 35 branches lose backbone connectivity. ATM, M-Pesa, "
            "USSD, cards channels all go down for 90 minutes."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 17, 10, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0),
            kind="chaos:activate",
            ref="branch_wide_connectivity_collapse")],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "connectivity", "extreme"],
    )

    # 4. Liquidity panic - simulated via simultaneous channels stress
    L["bs_liquidity_panic_run_on_bank"] = Drill(
        name="bs_liquidity_panic_run_on_bank",
        description=(
            "Coordinated panic-withdraw event: simultaneous load on "
            "ATM (dispenser strain) + M-Pesa (callback blackhole). "
            "Tests detection and degradation pattern under panic."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 18, 9, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="atm_dispenser_jams_eom"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=5), kind="chaos:activate",
                ref="mpesa_callback_blackhole"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "liquidity", "panic", "extreme"],
    )

    # 5. Coordinated fraud ring
    L["bs_coordinated_fraud_ring"] = Drill(
        name="bs_coordinated_fraud_ring",
        description=(
            "Fraud ring active across M-Pesa, cards, USSD for 60 "
            "minutes. Elevated failure rate signals attack. Audit "
            "trail must preserve fraud_pattern marker."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 19, 14, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="coordinated_fraud_ring_multi_channel")],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "fraud", "ring", "extreme"],
    )

    # 6. Insider privilege abuse
    L["bs_insider_privilege_abuse"] = Drill(
        name="bs_insider_privilege_abuse",
        description=(
            "Admin credentials abused for 30 minutes; 1500 approval-"
            "chain overrides recorded. Tests whether the abuse is "
            "observable via chaos:active and event bus."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 20, 11, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="insider_privilege_abuse_admin_overrides")],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "insider", "rbac", "extreme"],
    )

    # 7. Payroll failure 500K customers
    L["bs_payroll_failure_500k"] = Drill(
        name="bs_payroll_failure_500k",
        description=(
            "Month-end payroll batch for 500K employees of corporate "
            "customers fails. 4-hour outage starting 08:00 EOM."
        ),
        category="black_swan",
        sim_start=datetime(2026, 5, 31, 7, 55, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(minutes=5), kind="chaos:activate",
            ref="payroll_failure_500k_customers")],
        agent_goal="inspect_channels",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:list"],
        ),
        tags=["blackswan", "payroll", "eom", "extreme"],
    )

    # 8. Simultaneous RTGS + M-Pesa outage
    L["bs_simultaneous_rtgs_mpesa_outage"] = Drill(
        name="bs_simultaneous_rtgs_mpesa_outage",
        description=(
            "Both wholesale (RTGS) and retail (M-Pesa) rails down for "
            "2 hours. Customers have NO functional payment channel. "
            "Tests whether agent recognises the dual-rail blackout."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 22, 11, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="simultaneous_rtgs_mpesa_outage")],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "payments", "dual_rail", "extreme"],
    )

    # 9. Treasury pricing corruption
    L["bs_treasury_pricing_corruption"] = Drill(
        name="bs_treasury_pricing_corruption",
        description=(
            "Treasury pricing feed corrupted (FX/yields wrong by 10%+) "
            "for 30 minutes. Reference Knight Capital 2012 (-$440M). "
            "Agent must detect through macro snapshot."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 23, 10, 30, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="treasury_pricing_corruption")],
        agent_goal="survey_macro",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["macro:snapshot"],
        ),
        tags=["blackswan", "treasury", "pricing", "extreme"],
    )

    # 10. Duplicate transaction storm
    L["bs_duplicate_transaction_storm"] = Drill(
        name="bs_duplicate_transaction_storm",
        description=(
            "Idempotency-key collision causes 45 minutes of duplicate "
            "transactions. ~5000 dupes before detection. Tests audit "
            "trail preservation."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 24, 13, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="duplicate_transaction_storm")],
        agent_goal="inspect_channels",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:list"],
        ),
        tags=["blackswan", "duplicates", "ledger", "extreme"],
    )

    # 11. Reconciliation blackout
    L["bs_reconciliation_blackout_24h"] = Drill(
        name="bs_reconciliation_blackout_24h",
        description=(
            "24-hour reconciliation freeze. Tests whether downstream "
            "consumers (KPI, dashboards) handle stale reco gracefully. "
            "Simulated via simultaneous KEPSS + cards degradation."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 25, 0, 0, tzinfo=tz),
        environment=[
            DrillEnvironmentEvent(
                offset=timedelta(0), kind="chaos:activate",
                ref="kepss_host_down_60min"),
            DrillEnvironmentEvent(
                offset=timedelta(minutes=5), kind="chaos:activate",
                ref="cards_acquirer_degraded_60min"),
        ],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "reconciliation", "extreme"],
    )

    # 12. Regulatory freeze order
    L["bs_regulatory_freeze_order"] = Drill(
        name="bs_regulatory_freeze_order",
        description=(
            "CBK orders 3-hour suspension of one product line "
            "(unsecured lending) pending investigation. Tests "
            "operational continuity of unaffected lines."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 26, 9, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="regulatory_freeze_order_cbk_suspension")],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "regulatory", "freeze", "extreme"],
    )

    # 13. Mass dormant activation
    L["bs_mass_dormant_activation"] = Drill(
        name="bs_mass_dormant_activation",
        description=(
            "10,000 long-dormant accounts suddenly activate in 60 "
            "minutes. Strong AML signal — agent should observe "
            "anomaly via channels."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 27, 14, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="mass_dormant_account_activation")],
        agent_goal="inspect_channels",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:list"],
        ),
        tags=["blackswan", "dormant", "aml", "extreme"],
    )

    # 14. Bulk reversal crisis
    L["bs_bulk_reversal_crisis"] = Drill(
        name="bs_bulk_reversal_crisis",
        description=(
            "10,000 transactions reversed in bulk after duplicate "
            "discovery. Tests audit trail integrity and reco recovery."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 28, 9, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="bulk_reversal_crisis_10k_txns")],
        agent_goal="inspect_channels",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["channel:list"],
        ),
        tags=["blackswan", "reversal", "ledger", "extreme"],
    )

    # 15. AI model corruption
    L["bs_ai_model_corruption"] = Drill(
        name="bs_ai_model_corruption",
        description=(
            "ML model registry returns corrupted predictions for 60 "
            "minutes. Tests whether ML output is treated as advisory "
            "(safe) vs load-bearing for safety-critical decisions."
        ),
        category="black_swan",
        sim_start=datetime(2026, 6, 29, 11, 0, tzinfo=tz),
        environment=[DrillEnvironmentEvent(
            offset=timedelta(0), kind="chaos:activate",
            ref="ai_model_corruption_event")],
        agent_goal="survey_chaos",
        oracle=DrillOracle(
            min_steps=2,
            required_tool_calls=["chaos:active"],
        ),
        tags=["blackswan", "ai", "corruption", "extreme"],
    )

    return L


_LIBRARY: Dict[str, Drill] = None  # type: ignore


def _ensure() -> Dict[str, Drill]:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_blackswan_library()
    return _LIBRARY


def list_blackswan_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_blackswan_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(
            f"unknown black-swan drill: {name!r}. "
            f"Available: {sorted(L)[:5]}..."
        )
    return L[name]


def extreme_chaos_templates_added() -> List[str]:
    """Names of the 12 extreme chaos templates we injected."""
    return sorted(_EXTREME_CHAOS_TEMPLATES.keys())


__all__ = [
    "list_blackswan_drills", "get_blackswan_drill",
    "extreme_chaos_templates_added",
]

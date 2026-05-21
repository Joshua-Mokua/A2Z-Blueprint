"""utils/chaos/library.py — prebuilt chaos event templates.

25 realistic Kenya banking chaos events. Each is a factory function
that builds a ChaosEvent at a specified ``when`` (callers pick the time)
so the same templates can be replayed across different sim moments.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from utils.chaos.base import ChaosEvent, ChaosKind, ChaosSeverity


# Each library entry is a builder function with signature:
#   build(when: datetime, **overrides) -> ChaosEvent
ChaosBuilder = Callable[..., ChaosEvent]


def _build(name: str, kind: ChaosKind, severity: ChaosSeverity,
            target: str, duration_minutes: int,
            payload: Optional[Dict] = None,
            tags: Optional[List[str]] = None,
            realistic_basis: str = "") -> ChaosBuilder:
    """Factory for builder closures."""
    def builder(when: datetime, **overrides) -> ChaosEvent:
        return ChaosEvent(
            name=overrides.get("name", name),
            kind=kind,
            when=when,
            duration=overrides.get("duration",
                                     timedelta(minutes=duration_minutes)),
            severity=overrides.get("severity", severity),
            target=overrides.get("target", target),
            payload={**(payload or {}), **overrides.get("payload", {})},
            tags=list(tags or []),
            realistic_basis=realistic_basis,
        )
    builder.__name__ = f"build_{name.replace(' ', '_')}"
    return builder


# ─── 25 chaos event templates ───────────────────────────────────────

CHAOS_LIBRARY: Dict[str, Dict] = {

    # ── Channel outages (8) ──────────────────────────────────────
    "safaricom_mpesa_outage_30min": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.HIGH,
        "target": "mpesa",
        "duration_minutes": 30,
        "tags": ["mpesa", "outage", "safaricom"],
        "realistic_basis": (
            "Safaricom M-Pesa outages of 15-90 minutes occur "
            "several times a year (e.g. systemwide outage 2024-04 "
            "and 2024-11 reported by users and Safaricom IR)."
        ),
    },
    "safaricom_mpesa_outage_2hr": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.CRITICAL,
        "target": "mpesa",
        "duration_minutes": 120,
        "tags": ["mpesa", "outage", "safaricom", "critical"],
        "realistic_basis": (
            "Extended Safaricom M-Pesa outage (~2hr) — happened "
            "during the major 2024 outage that affected millions."
        ),
    },
    "swift_correspondent_down_4hr": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.HIGH,
        "target": "swift",
        "duration_minutes": 240,
        "tags": ["swift", "outage", "correspondent"],
        "realistic_basis": (
            "Correspondent bank (e.g. JPMorgan, Deutsche) goes "
            "intermittent for several hours during APAC handoff."
        ),
    },
    "kepss_host_down_60min": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.CRITICAL,
        "target": "rtgs,kic",
        "duration_minutes": 60,
        "tags": ["kepss", "rtgs", "kic", "outage", "cbk"],
        "realistic_basis": (
            "KEPSS host maintenance / unscheduled outage takes "
            "down both RTGS and KIC simultaneously (they share "
            "infrastructure operated by CBK)."
        ),
    },
    "atm_network_partition_45min": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.HIGH,
        "target": "atm",
        "duration_minutes": 45,
        "tags": ["atm", "outage", "network"],
        "realistic_basis": (
            "Branch ATM network partition (typical 30-60min) — "
            "switch connectivity lost to issuer host."
        ),
    },
    "cards_acquirer_outage_30min": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.HIGH,
        "target": "cards",
        "duration_minutes": 30,
        "tags": ["cards", "outage", "acquirer"],
        "realistic_basis": (
            "Card acquirer outage (e.g. Pesapal, DPO) — all merchant "
            "transactions fail for half an hour."
        ),
    },
    "ussd_telco_outage_20min": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.HIGH,
        "target": "ussd",
        "duration_minutes": 20,
        "tags": ["ussd", "outage", "telco"],
        "realistic_basis": (
            "Telco USSD gateway down (Safaricom/Airtel) — "
            "feature-phone banking sessions all fail."
        ),
    },
    "full_digital_blackout_15min": {
        "kind": ChaosKind.CHANNEL_OUTAGE,
        "severity": ChaosSeverity.CRITICAL,
        "target": "mpesa,ussd,cards,atm",
        "duration_minutes": 15,
        "tags": ["blackout", "multi_channel", "critical"],
        "realistic_basis": (
            "Major upstream provider outage (KPLC region blackout "
            "or fibre cut) takes down everything except branch "
            "counter for ~15 minutes."
        ),
    },

    # ── Elevated failure (7) ─────────────────────────────────────
    "cards_acquirer_degraded_60min": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "cards",
        "duration_minutes": 60,
        "payload": {"failure_rate": 0.35},
        "tags": ["cards", "degraded", "acquirer"],
        "realistic_basis": (
            "Acquirer rerouting through slower path — 30-40% of "
            "card transactions timeout/fail for an hour."
        ),
    },
    "atm_dispenser_jams_eom": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "atm",
        "duration_minutes": 360,
        "payload": {"failure_rate": 0.15},
        "tags": ["atm", "eom", "dispenser"],
        "realistic_basis": (
            "End-of-month cash demand strains ATM cash dispensers — "
            "15% jam rate sustained across the rush window."
        ),
    },
    "ussd_session_drop_storm_30min": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "ussd",
        "duration_minutes": 30,
        "payload": {"failure_rate": 0.40},
        "tags": ["ussd", "session_drop", "telco"],
        "realistic_basis": (
            "Telco network congestion during peak traffic drops "
            "USSD sessions at ~40% rate for half an hour."
        ),
    },
    "mpesa_callback_blackhole": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "mpesa",
        "duration_minutes": 90,
        "payload": {"failure_rate": 0.25},
        "tags": ["mpesa", "callback", "daraja"],
        "realistic_basis": (
            "Daraja callback URL unreachable — 25% of STK push "
            "transactions never receive callback confirmation."
        ),
    },
    "rtgs_kepss_rate_limit": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "rtgs",
        "duration_minutes": 45,
        "payload": {"failure_rate": 0.20},
        "tags": ["rtgs", "rate_limit", "kepss"],
        "realistic_basis": (
            "KEPSS imposes rate limit during peak hour — 20% "
            "of RTGS submissions rejected with throttle."
        ),
    },
    "swift_message_queue_backlog": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "swift",
        "duration_minutes": 120,
        "payload": {"failure_rate": 0.18},
        "tags": ["swift", "queue", "backlog"],
        "realistic_basis": (
            "SWIFT Alliance message queue backs up during peak "
            "EOM nostro funding rush — ~18% timeout."
        ),
    },
    "kic_cheque_image_quality": {
        "kind": ChaosKind.ELEVATED_FAILURE,
        "severity": ChaosSeverity.LOW,
        "target": "kic",
        "duration_minutes": 240,
        "payload": {"failure_rate": 0.10},
        "tags": ["kic", "cheque", "image"],
        "realistic_basis": (
            "Branch scanner calibration drift causes 10% of "
            "cheque images to be rejected as poor quality."
        ),
    },

    # ── Latency spike (4) ────────────────────────────────────────
    "swift_latency_spike_3x": {
        "kind": ChaosKind.LATENCY_SPIKE,
        "severity": ChaosSeverity.LOW,
        "target": "swift",
        "duration_minutes": 60,
        "payload": {"multiplier": 3.0},
        "tags": ["swift", "latency"],
        "realistic_basis": (
            "SWIFT messaging latency 3x slower during APAC "
            "handoff window."
        ),
    },
    "cards_3ds_acs_slow": {
        "kind": ChaosKind.LATENCY_SPIKE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "cards",
        "duration_minutes": 90,
        "payload": {"multiplier": 5.0},
        "tags": ["cards", "3ds", "latency"],
        "realistic_basis": (
            "3DS ACS server slow — CNP card transactions take "
            "5x normal time. Some merchant timeouts."
        ),
    },
    "rtgs_kepss_latency_2x": {
        "kind": ChaosKind.LATENCY_SPIKE,
        "severity": ChaosSeverity.LOW,
        "target": "rtgs",
        "duration_minutes": 45,
        "payload": {"multiplier": 2.0},
        "tags": ["rtgs", "kepss", "latency"],
        "realistic_basis": (
            "KEPSS RTGS pacing slower during EOM cutoff rush."
        ),
    },
    "all_channels_latency_spike": {
        "kind": ChaosKind.LATENCY_SPIKE,
        "severity": ChaosSeverity.MEDIUM,
        "target": "*",
        "duration_minutes": 20,
        "payload": {"multiplier": 2.5},
        "tags": ["multi_channel", "latency"],
        "realistic_basis": (
            "Core banking system slow due to garbage collection / "
            "DB index rebuild — every channel slower for 20min."
        ),
    },

    # ── Macro shocks (4) ─────────────────────────────────────────
    "kes_devaluation_5pct": {
        "kind": ChaosKind.MACRO_SHOCK,
        "severity": ChaosSeverity.HIGH,
        "target": "macro",
        "duration_minutes": 1,
        "payload": {"shock": "fx_devaluation", "pct": 0.05},
        "tags": ["macro", "fx", "devaluation"],
        "realistic_basis": (
            "KES dropped ~20% in 2023-2024 vs USD; 5% over a "
            "single day happens during sharp confidence shocks."
        ),
    },
    "cbk_emergency_hike_200bps": {
        "kind": ChaosKind.MACRO_SHOCK,
        "severity": ChaosSeverity.HIGH,
        "target": "macro",
        "duration_minutes": 1,
        "payload": {"shock": "cbr_change", "new_rate_delta": 0.02},
        "tags": ["macro", "cbk_mpc", "rate_hike"],
        "realistic_basis": (
            "CBK hiked CBR 200bps in late 2023 to defend KES — "
            "an emergency between-meeting decision is rare but "
            "happens in stress scenarios."
        ),
    },
    "credit_shock_npl_plus_300bps": {
        "kind": ChaosKind.MACRO_SHOCK,
        "severity": ChaosSeverity.HIGH,
        "target": "macro",
        "duration_minutes": 1,
        "payload": {"shock": "credit_shock", "delta": 0.03},
        "tags": ["macro", "credit_shock", "npl"],
        "realistic_basis": (
            "Banking sector NPL jumps 300bps following a sector "
            "shock (e.g. coffee/tea export collapse, real estate "
            "downturn)."
        ),
    },
    "inflation_spike_food": {
        "kind": ChaosKind.MACRO_SHOCK,
        "severity": ChaosSeverity.MEDIUM,
        "target": "macro",
        "duration_minutes": 1,
        "payload": {"shock": "inflation_spike", "delta": 0.025},
        "tags": ["macro", "inflation"],
        "realistic_basis": (
            "Food inflation spike (drought / fuel cost passthrough) "
            "adds 2.5% to headline inflation."
        ),
    },

    # ── Scheme degraded (2) ──────────────────────────────────────
    "visa_routing_degraded_60min": {
        "kind": ChaosKind.SCHEME_DEGRADED,
        "severity": ChaosSeverity.MEDIUM,
        "target": "cards",
        "duration_minutes": 60,
        "payload": {"failure_rate": 0.40, "scheme": "VISA"},
        "tags": ["cards", "visa", "scheme"],
        "realistic_basis": (
            "VISA backend rerouting through alternate path; 40% "
            "of VISA card transactions fail or downgrade."
        ),
    },
    "mastercard_3ds_outage_30min": {
        "kind": ChaosKind.SCHEME_DEGRADED,
        "severity": ChaosSeverity.MEDIUM,
        "target": "cards",
        "duration_minutes": 30,
        "payload": {"failure_rate": 0.50, "scheme": "MASTERCARD"},
        "tags": ["cards", "mastercard", "3ds"],
        "realistic_basis": (
            "Mastercard SecureCode (3DS) infrastructure down for "
            "30min — half of CNP transactions fail."
        ),
    },
}


def get_chaos_event(name: str, when: datetime,
                     **overrides) -> ChaosEvent:
    """Build a chaos event from the library template."""
    if name not in CHAOS_LIBRARY:
        raise KeyError(f"Unknown chaos template: {name!r}. "
                        f"Available: {sorted(CHAOS_LIBRARY)[:5]}...")
    tmpl = CHAOS_LIBRARY[name]
    return ChaosEvent(
        name=overrides.get("name", name),
        kind=tmpl["kind"],
        when=when,
        duration=overrides.get(
            "duration",
            timedelta(minutes=tmpl["duration_minutes"]),
        ),
        severity=tmpl["severity"],
        target=overrides.get("target", tmpl["target"]),
        payload={**tmpl.get("payload", {}),
                  **overrides.get("payload", {})},
        tags=list(tmpl.get("tags", [])),
        realistic_basis=tmpl.get("realistic_basis", ""),
    )


def list_chaos_events() -> List[str]:
    return sorted(CHAOS_LIBRARY.keys())


def chaos_events_by_kind(kind: str) -> List[str]:
    return [name for name, tmpl in CHAOS_LIBRARY.items()
             if tmpl["kind"].value == kind]


def chaos_events_by_severity(severity: str) -> List[str]:
    return [name for name, tmpl in CHAOS_LIBRARY.items()
             if tmpl["severity"].value == severity]


__all__ = [
    "CHAOS_LIBRARY", "get_chaos_event", "list_chaos_events",
    "chaos_events_by_kind", "chaos_events_by_severity",
]

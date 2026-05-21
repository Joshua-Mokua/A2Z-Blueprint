"""utils/scenarios/operational_risk.py — Channel outages, host downs, queue formation (20)."""

from __future__ import annotations

from typing import Any, Dict

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioContext, ScenarioSeverity,
)


def _msisdn(seed: int, offset: int = 0) -> str:
    return f"2547{(seed * 12345 + 100000 + offset) % 100_000_000:08d}"


def run_safaricom_mpesa_outage(ctx: ScenarioContext) -> Dict[str, Any]:
    """M-Pesa Daraja outage: 30 customer-pay attempts during outage window."""
    n = 0; fails = 0
    for i in range(30):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                     "msisdn": _msisdn(ctx.seed, i),
                     "amount": 1_500, "paybill": "888888"},
            amount=1_500)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_swift_correspondent_down(ctx: ScenarioContext) -> Dict[str, Any]:
    """SWIFT correspondent NOSTRO unavailable: MT103 batch returns NAK."""
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "OUTBOUND",
                     "beneficiary_bic": "CHASUS33",
                     "beneficiary_name": "BEN",
                     "amount": 15_000.0},
            amount=15_000.0, currency="USD",
            debit_account="NOSTRO-1", credit_account="BEN-1")
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_atm_dispenser_jam_wave(ctx: ScenarioContext) -> Dict[str, Any]:
    """ATM dispenser jam wave at one terminal: 12 attempts."""
    n = 0; fails = 0
    for i in range(12):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": f"4111{i+100:012d}",
                     "amount": 5_000,
                     "terminal_id": "ECONA-JAM-01"},
            amount=5_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_ussd_network_drop_storm(ctx: ScenarioContext) -> Dict[str, Any]:
    """USSD network drops: 25 sessions during MNO instability."""
    n = 0; fails = 0
    for i in range(25):
        r = ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": _msisdn(ctx.seed, 2000 + i),
                     "text": "1"})
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_kepss_host_unavailable(ctx: ScenarioContext) -> Dict[str, Any]:
    """KEPSS RTGS host unavailable: high-value RTGS batch returns timeouts."""
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 2_500_000,
                     "debit_account": "MAIN-1",
                     "credit_account": "BEN-1",
                     "beneficiary_bank_bic": "BARCKENX"},
            amount=2_500_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_rtgs_cutoff_missed(ctx: ScenarioContext) -> Dict[str, Any]:
    """Submissions arrive after 4:30pm Nairobi RTGS cutoff."""
    n = 0; fails = 0
    for i in range(8):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 1_500_000,
                     "debit_account": "DELAYED-1",
                     "credit_account": "BEN-1",
                     "beneficiary_bank_bic": "BARCKENX"},
            amount=1_500_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_cards_acquirer_timeout(ctx: ScenarioContext) -> Dict[str, Any]:
    """Acquirer timeouts during peak: 30 POS auths."""
    n = 0; fails = 0
    for i in range(30):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111111111111111",
                     "card_not_present": False,
                     "cvv": "123", "expiry": "12/28",
                     "terminal_id": "POS-PEAK"},
            amount=1_500)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_kic_batch_rejected_cutoff(ctx: ScenarioContext) -> Dict[str, Any]:
    """KIC batch rejected at clearing house cutoff."""
    n = 0; fails = 0
    for i in range(20):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011",
                     "narrative": f"Cutoff test {i}"},
            amount=350_000,
            debit_account="LATE-SUBMIT",
            credit_account=f"BEN-{i:04d}")
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_atm_network_partition(ctx: ScenarioContext) -> Dict[str, Any]:
    """ATM-host network partition: 18 transactions across 6 terminals."""
    n = 0; fails = 0
    for i in range(18):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": "4111000011110000",
                     "amount": 3_000,
                     "terminal_id": f"PARTITION-{i % 6}"},
            amount=3_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_swift_message_rate_limit(ctx: ScenarioContext) -> Dict[str, Any]:
    """SWIFT FIN session approaches rate limit: 50 messages rapid-fire."""
    n = 0; fails = 0
    for i in range(50):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "BURST",
                     "beneficiary_bic": "CHASUS33",
                     "beneficiary_name": "B",
                     "amount": 100.0},
            amount=100.0, currency="USD",
            debit_account="X", credit_account="Y")
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_mpesa_callback_blackhole(ctx: ScenarioContext) -> Dict[str, Any]:
    """M-Pesa STK callbacks never arrive: 25 transactions pending."""
    n = 0; fails = 0
    for i in range(25):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                     "msisdn": _msisdn(ctx.seed, 3000 + i),
                     "amount": 2_000, "paybill": "888888"},
            amount=2_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_branch_atm_offline_full_day(ctx: ScenarioContext) -> Dict[str, Any]:
    """Single branch's ATMs all offline: 20 redirected transactions to other branches."""
    n = 0; fails = 0
    for i in range(20):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": f"4111200034{i:06d}",
                     "amount": 5_000,
                     "terminal_id": f"OFFLINE-RDIR-{i % 5:03d}"},
            amount=5_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_kepss_pacs008_format_change(ctx: ScenarioContext) -> Dict[str, Any]:
    """KEPSS pacs.008 schema change rejects 10 messages."""
    n = 0; fails = 0
    for i in range(10):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 1_200_000,
                     "debit_account": "PRE-CHANGE",
                     "credit_account": "BEN",
                     "beneficiary_bank_bic": "BARCKENX"},
            amount=1_200_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_card_scheme_degraded_routing(ctx: ScenarioContext) -> Dict[str, Any]:
    """Visa rail degraded routing: latency spike on 25 POS."""
    n = 0
    for i in range(25):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111000022223333",
                     "card_not_present": False,
                     "cvv": "111", "expiry": "12/28"},
            amount=4_500)
        n += 1
    return {"attempts": n}


def run_ussd_short_code_change(ctx: ScenarioContext) -> Dict[str, Any]:
    """USSD short-code routing change: 15 sessions hit old short code."""
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": _msisdn(ctx.seed, 4000 + i),
                     "text": "1*1"})
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_kic_cheque_image_quality_reject(ctx: ScenarioContext) -> Dict[str, Any]:
    """Image-truncation cheques rejected for low quality."""
    n = 0; fails = 0
    for i in range(12):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "CHEQUE_INWARD",
                     "beneficiary_bank_code": "011",
                     "cheque_number": f"{500000+i:06d}",
                     "debit_account": "BLURRY-IMG"},
            amount=20_000,
            credit_account="BEN-IMG")
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_swift_alliance_lite_disconnect(ctx: ScenarioContext) -> Dict[str, Any]:
    """SWIFT Alliance Lite disconnect: 10 messages queue locally."""
    n = 0; fails = 0
    for i in range(10):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "QUEUED",
                     "beneficiary_bic": "CHASUS33",
                     "beneficiary_name": "BEN",
                     "amount": 5_000.0},
            amount=5_000.0, currency="USD",
            debit_account="QUEUE-1", credit_account="BEN-Q")
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_atm_cash_replenishment_failure(ctx: ScenarioContext) -> Dict[str, Any]:
    """Cash-out ATM: insufficient-funds rejects across 15 withdrawal attempts."""
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": f"4111000088{i:06d}",
                     "amount": 100_000,
                     "terminal_id": "CASH-OUT-001"},
            amount=100_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_clearinghouse_capacity_squeeze(ctx: ScenarioContext) -> Dict[str, Any]:
    """KEPSS overall capacity squeeze: mixed RTGS + KIC slowdown."""
    n = 0; fails = 0
    for i in range(20):
        if i % 2 == 0:
            r = ctx.submit_channel("rtgs",
                payload={"amount": 1_300_000,
                         "debit_account": "STRESS",
                         "credit_account": "BEN",
                         "beneficiary_bank_bic": "BARCKENX"},
                amount=1_300_000)
        else:
            r = ctx.submit_channel("kic",
                payload={"transaction_type": "EFT_CREDIT",
                         "beneficiary_bank_code": "011"},
                amount=350_000, debit_account="STRESS",
                credit_account=f"BEN-{i}")
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_cards_3ds_acs_outage(ctx: ScenarioContext) -> Dict[str, Any]:
    """3DS ACS server outage: 15 CNP transactions trigger 3DS but can't complete."""
    n = 0; threeds_hits = 0
    for i in range(15):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111111111111111",
                     "card_not_present": True,
                     "cvv": "123", "expiry": "12/28"},
            amount=15_000)
        n += 1
        if r.error_code == "3DS_REQUIRED": threeds_hits += 1
    return {"attempts": n, "stuck_at_3ds": threeds_hits}


OPRISK_SCENARIOS = [
    Scenario(name="safaricom_mpesa_outage", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.CRITICAL,
        description="M-Pesa Daraja outage: 30 customer-pay attempts during outage",
        runner=run_safaricom_mpesa_outage, tags=["mpesa", "outage", "vendor"],
        expected_event_types=["integration.mpesa.failure"],
        realistic_basis="Safaricom M-Pesa outages are public events (multiple in 2024-25)"),
    Scenario(name="swift_correspondent_down", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="SWIFT correspondent NOSTRO unavailable: 15 MT103 NAKs",
        runner=run_swift_correspondent_down, tags=["swift", "correspondent", "nostro"],
        expected_event_types=["integration.swift.failure"],
        realistic_basis="Correspondent bank outage halts USD clearing for the day"),
    Scenario(name="atm_dispenser_jam_wave", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.MEDIUM,
        description="ATM dispenser jam: 12 withdrawals at one terminal",
        runner=run_atm_dispenser_jam_wave, tags=["atm", "dispenser", "hardware"],
        expected_event_types=["integration.atm.failure"],
        realistic_basis="Hardware jam causes successive failures at same terminal"),
    Scenario(name="ussd_network_drop_storm", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="USSD network drops: 25 sessions during MNO instability",
        runner=run_ussd_network_drop_storm, tags=["ussd", "network", "mno"],
        expected_event_types=["integration.ussd.failure"],
        realistic_basis="Mobile network operator congestion during peak"),
    Scenario(name="kepss_host_unavailable", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.CRITICAL,
        description="KEPSS RTGS host unavailable: high-value batch returns timeouts",
        runner=run_kepss_host_unavailable, tags=["rtgs", "kepss", "host-down"],
        expected_event_types=["integration.rtgs.failure"],
        realistic_basis="CBK KEPSS host downtime disrupts entire interbank market"),
    Scenario(name="rtgs_cutoff_missed", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="Submissions arrive after 4:30pm Nairobi RTGS cutoff",
        runner=run_rtgs_cutoff_missed, tags=["rtgs", "cutoff", "missed"],
        expected_event_types=["integration.rtgs.failure"],
        realistic_basis="Operational delay pushes high-value past cutoff -> next-day settlement"),
    Scenario(name="cards_acquirer_timeout", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="Acquirer timeouts during peak: 30 POS auths impacted",
        runner=run_cards_acquirer_timeout, tags=["cards", "acquirer", "timeout"],
        expected_event_types=["integration.cards.failure"],
        realistic_basis="Acquiring switch saturation during shopping peak"),
    Scenario(name="kic_batch_rejected_cutoff", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.MEDIUM,
        description="KIC batch rejected at clearing-house cutoff",
        runner=run_kic_batch_rejected_cutoff, tags=["kic", "batch", "cutoff"],
        expected_event_types=["integration.kic.failure"],
        realistic_basis="Late-arriving batches rolled to next clearing window"),
    Scenario(name="atm_network_partition", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="ATM-host network partition: 18 transactions across 6 terminals",
        runner=run_atm_network_partition, tags=["atm", "network-partition"],
        expected_event_types=["integration.atm.failure"],
        realistic_basis="Datacenter to ATM-LAN link failure affects terminal cluster"),
    Scenario(name="swift_message_rate_limit", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.MEDIUM,
        description="SWIFT FIN session rate limit: 50 messages rapid-fire",
        runner=run_swift_message_rate_limit, tags=["swift", "rate-limit"],
        expected_event_types=["integration.swift.failure"],
        realistic_basis="SWIFT session capacity exceeded during reconciliation push"),
    Scenario(name="mpesa_callback_blackhole", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="M-Pesa STK callbacks never arrive: 25 pending",
        runner=run_mpesa_callback_blackhole, tags=["mpesa", "callback-timeout"],
        expected_event_types=["integration.mpesa.failure"],
        realistic_basis="Daraja callback URL temporarily unreachable; merchant can't reconcile"),
    Scenario(name="branch_atm_offline_full_day", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.MEDIUM,
        description="Single branch's ATMs all offline: 20 redirected transactions",
        runner=run_branch_atm_offline_full_day, tags=["atm", "branch-offline"],
        expected_event_types=["integration.atm.call"],
        realistic_basis="Branch power outage takes entire ATM cluster offline"),
    Scenario(name="kepss_pacs008_format_change", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.CRITICAL,
        description="KEPSS pacs.008 schema change rejects 10 messages",
        runner=run_kepss_pacs008_format_change, tags=["rtgs", "schema", "iso-20022"],
        expected_event_types=["integration.rtgs.failure"],
        realistic_basis="ISO 20022 schema updates have rejected non-conforming messages"),
    Scenario(name="card_scheme_degraded_routing", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.MEDIUM,
        description="Visa rail degraded routing: latency spike on 25 POS",
        runner=run_card_scheme_degraded_routing, tags=["cards", "scheme", "degraded"],
        expected_event_types=["integration.cards.call"],
        realistic_basis="Visa/MC switch issues elevate end-to-end latency"),
    Scenario(name="ussd_short_code_change", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.LOW,
        description="USSD short-code routing change: 15 sessions hit old short code",
        runner=run_ussd_short_code_change, tags=["ussd", "short-code"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Customers haven't updated bookmarks; old code temporarily routes wrong"),
    Scenario(name="kic_cheque_image_quality_reject", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.LOW,
        description="Image-truncation cheques rejected for low quality",
        runner=run_kic_cheque_image_quality_reject, tags=["kic", "cheque", "image-quality"],
        expected_event_types=["integration.kic.failure"],
        realistic_basis="Branch scanners produce blurry images that fail KEPSS image-quality check"),
    Scenario(name="swift_alliance_lite_disconnect", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="SWIFT Alliance Lite disconnect: 10 messages queue locally",
        runner=run_swift_alliance_lite_disconnect, tags=["swift", "alliance-lite"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="Local SWIFT gateway loses connectivity; messages queue until reconnect"),
    Scenario(name="atm_cash_replenishment_failure", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.MEDIUM,
        description="Cash-out ATM: 15 insufficient-cash rejections",
        runner=run_atm_cash_replenishment_failure, tags=["atm", "cash-out", "logistics"],
        expected_event_types=["integration.atm.failure"],
        realistic_basis="ATM runs dry before scheduled replenishment"),
    Scenario(name="clearinghouse_capacity_squeeze", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="KEPSS overall capacity squeeze: mixed RTGS+KIC slowdown",
        runner=run_clearinghouse_capacity_squeeze, tags=["rtgs", "kic", "capacity"],
        expected_event_types=["integration.rtgs.call", "integration.kic.call"],
        realistic_basis="EOM combined volume pressure on national clearing infrastructure"),
    Scenario(name="cards_3ds_acs_outage", category=ScenarioCategory.OPERATIONAL_RISK,
        severity=ScenarioSeverity.HIGH,
        description="3DS ACS server outage: 15 CNP transactions stuck at 3DS",
        runner=run_cards_3ds_acs_outage, tags=["cards", "3ds", "acs"],
        expected_event_types=["integration.cards.failure"],
        realistic_basis="Card-scheme 3DS ACS down -> all step-ups fail to complete"),
]

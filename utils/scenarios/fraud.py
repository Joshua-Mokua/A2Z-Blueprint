"""utils/scenarios/fraud.py — Fraud and security patterns (20 scenarios)."""

from __future__ import annotations

from typing import Any, Dict

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioContext, ScenarioSeverity,
)


def _pan(prefix: str, suffix_int: int) -> str:
    return f"{prefix}{suffix_int:012d}"


def _msisdn(seed: int, offset: int = 0) -> str:
    return f"2547{(seed * 12345 + 100000 + offset) % 100_000_000:08d}"


# ─────────────────────────────────────────────────────────────────────
# Card fraud
# ─────────────────────────────────────────────────────────────────────

def run_card_testing_attack(ctx: ScenarioContext) -> Dict[str, Any]:
    """Card testing: rapid small CNP attempts against random PANs (BIN attack)."""
    n = 0; fails = 0
    for i in range(40):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH", "pan": _pan("4111", i),
                     "card_not_present": True, "cvv": f"{i % 1000:03d}",
                     "expiry": "06/27", "merchant_id": "TEST001"},
            amount=10)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_bin_attack_visa(ctx: ScenarioContext) -> Dict[str, Any]:
    """BIN attack: sequential PANs on a single Visa BIN range."""
    n = 0; fails = 0
    base = 411111110000_0000
    for i in range(30):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH", "pan": str(base + i),
                     "card_not_present": True, "cvv": "999",
                     "expiry": "12/27"},
            amount=1)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails}


def run_atm_skimming_pattern(ctx: ScenarioContext) -> Dict[str, Any]:
    """ATM skimming: same PAN cycled across multiple terminals quickly."""
    pan = "4111222233334444"
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL", "pan": pan,
                     "amount": 40_000,
                     "terminal_id": f"FAR-{i:04d}"},
            amount=40_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails, "victim_pan": pan[:6] + "***"}


def run_high_value_cnp_no_3ds(ctx: ScenarioContext) -> Dict[str, Any]:
    """20 attempts to bypass 3DS on high-value CNP (should all step-up)."""
    n = 0; threeds_hits = 0
    for i in range(20):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111111111111111",
                     "card_not_present": True,
                     "cvv": "123", "expiry": "12/28"},
            amount=20_000 + (i * 500))
        n += 1
        if r.error_code == "3DS_REQUIRED": threeds_hits += 1
    return {"attempts": n, "threeds_hits": threeds_hits,
             "bypass_successful": n - threeds_hits}


def run_refund_abuse(ctx: ScenarioContext) -> Dict[str, Any]:
    """Refund abuse: repeated REFUND ops from a single PAN."""
    n = 0
    for i in range(12):
        r = ctx.submit_channel("cards",
            payload={"operation": "REFUND",
                     "pan": "4111000011112222",
                     "card_not_present": False,
                     "cvv": "111", "expiry": "01/27"},
            amount=8_500)
        n += 1
    return {"refund_attempts": n}


# ─────────────────────────────────────────────────────────────────────
# Mobile fraud
# ─────────────────────────────────────────────────────────────────────

def run_mpesa_sim_swap(ctx: ScenarioContext) -> Dict[str, Any]:
    """SIM swap attack: rapid M-Pesa drain attempts from a fresh msisdn."""
    msisdn = _msisdn(ctx.seed, 9999)
    n = 0; fails = 0
    for i in range(10):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "BusinessPayment",
                     "msisdn": msisdn, "amount": 140_000,
                     "paybill": "999999",
                     "account_reference": "DRAIN"},
            amount=140_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "failures": fails, "victim_msisdn": msisdn[:6] + "******"}


def run_ussd_account_takeover(ctx: ScenarioContext) -> Dict[str, Any]:
    """USSD takeover: brute-force PIN attempts via repeated sessions."""
    n = 0; fails = 0
    for i in range(20):
        r = ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": _msisdn(ctx.seed, 8888),
                     "text": f"5*1*5000*{1000+i:04d}"})  # rotating PIN guesses
        n += 1
        if not r.success: fails += 1
    return {"pin_attempts": n}


def run_mpesa_structuring(ctx: ScenarioContext) -> Dict[str, Any]:
    """Structuring: 15 sub-threshold M-Pesa transactions to evade single-txn limit."""
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "BusinessPayment",
                     "msisdn": _msisdn(ctx.seed, 7777),
                     "amount": 140_000,
                     "paybill": "888888"},
            amount=140_000)
        n += 1
        if not r.success: fails += 1
    return {"sub_threshold_txns": n}


# ─────────────────────────────────────────────────────────────────────
# Mule / layering
# ─────────────────────────────────────────────────────────────────────

def run_mule_account_chain_kic(ctx: ScenarioContext) -> Dict[str, Any]:
    """Mule chain: 12 KIC EFT_CREDIT legs cycling through suspect accounts."""
    n = 0; fails = 0
    suspects = [f"MULE-{i:04d}" for i in range(6)]
    for i in range(12):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011",
                     "narrative": f"Personal transfer leg {i}"},
            amount=950_000,
            debit_account=suspects[i % 6],
            credit_account=suspects[(i + 1) % 6])
        n += 1
        if not r.success: fails += 1
    return {"layering_legs": n}


def run_rtgs_split_to_multi_beneficiaries(ctx: ScenarioContext) -> Dict[str, Any]:
    """High-value RTGS split: large amount sent to 8 beneficiaries (mule-like)."""
    n = 0; fails = 0
    for i in range(8):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 4_000_000,
                     "debit_account": "SUSPECT-MAIN-001",
                     "credit_account": f"BEN-{i:04d}",
                     "beneficiary_bank_bic": "BARCKENX"},
            amount=4_000_000)
        n += 1
        if not r.success: fails += 1
    return {"split_legs": n}


def run_round_dollar_swift_pattern(ctx: ScenarioContext) -> Dict[str, Any]:
    """SWIFT MT103 round-dollar amounts to single beneficiary (suspicious)."""
    n = 0
    for amt in [9_900, 9_950, 9_999, 9_990, 9_995, 9_900, 9_950, 9_900]:
        r = ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "ROUND DOLLAR ORIGINATOR",
                     "beneficiary_bic": "CHASUS33",
                     "beneficiary_name": "REPEAT BEN",
                     "amount": float(amt)},
            amount=float(amt), currency="USD",
            debit_account="ORIG-1", credit_account="BEN-1")
        n += 1
    return {"round_dollar_txns": n}


def run_velocity_fraud_card_burst(ctx: ScenarioContext) -> Dict[str, Any]:
    """Card velocity: 25 transactions from one PAN in tight burst (5x normal velocity)."""
    pan = "4111988877776666"
    n = 0; fails = 0
    for i in range(25):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE", "pan": pan,
                     "card_not_present": i % 2 == 0,
                     "cvv": "999", "expiry": "12/28",
                     "threeds_completed": True},  # bypass 3DS for test
            amount=3_500 + (i * 100))
        n += 1
        if not r.success: fails += 1
    return {"velocity_txns": n}


def run_geo_anomaly_card_use(ctx: ScenarioContext) -> Dict[str, Any]:
    """Same PAN used in geographically-impossible locations (Nairobi + Lagos)."""
    pan = "4111000099998888"
    n = 0; fails = 0
    for i, terminal in enumerate(["ECONA0001", "LAGOS0001",
                                    "ECONA0002", "LAGOS0002", "ECONA0003"]):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL", "pan": pan,
                     "amount": 30_000, "terminal_id": terminal},
            amount=30_000)
        n += 1
        if not r.success: fails += 1
    return {"impossible_geo_txns": n}


def run_pin_brute_force(ctx: ScenarioContext) -> Dict[str, Any]:
    """ATM PIN brute-force: 6 attempts on same PAN (should trigger lock)."""
    n = 0; fails = 0
    for i in range(6):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": "4111777766665555",
                     "amount": 1_000, "terminal_id": "ECONA0099"},
            amount=1_000)
        n += 1
        if not r.success: fails += 1
    return {"pin_attempts": n}


def run_swift_mt103_to_high_risk(ctx: ScenarioContext) -> Dict[str, Any]:
    """SWIFT MT103 to high-risk corridor."""
    n = 0
    for i in range(5):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "ORIGINATOR ONE",
                     "beneficiary_bic": "HIRSKKEN",  # synthetic high-risk
                     "beneficiary_name": "BEN HIGH RISK",
                     "amount": 24_950.00},
            amount=24_950.00, currency="USD",
            debit_account="HIGH-RISK-1",
            credit_account="BEN-HR-1")
        n += 1
    return {"high_risk_txns": n}


def run_mpesa_dormant_acc_revival_spike(ctx: ScenarioContext) -> Dict[str, Any]:
    """Long-dormant accounts suddenly active on M-Pesa: 8 events."""
    n = 0
    for i in range(8):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "BusinessPayment",
                     "msisdn": _msisdn(ctx.seed, 6000 + i),
                     "amount": 120_000,
                     "paybill": "111000"},
            amount=120_000)
        n += 1
    return {"revival_attempts": n}


def run_card_present_at_atm_after_block(ctx: ScenarioContext) -> Dict[str, Any]:
    """Blocked-card retry: same PAN keeps trying after multiple declines."""
    n = 0; fails = 0
    for i in range(8):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": "4111000088887777",
                     "amount": 50_000,
                     "terminal_id": "ECONA0001"},
            amount=50_000)
        n += 1
        if not r.success: fails += 1
    return {"blocked_retry_attempts": n}


def run_kic_to_pep_account(ctx: ScenarioContext) -> Dict[str, Any]:
    """Repeated KIC EFT_CREDIT to a politically exposed person account."""
    n = 0
    for i in range(7):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001",
                     "narrative": "Consultancy fees"},
            amount=950_000,
            debit_account="CORP-RESERVE-1",
            credit_account="PEP-ACCT-001")
        n += 1
    return {"pep_payments": n}


def run_rapid_card_in_5_countries(ctx: ScenarioContext) -> Dict[str, Any]:
    """Card-not-present from 5 different IP geos within 10 min."""
    n = 0
    for i, country in enumerate(["KE", "NG", "ZA", "GH", "UG"]):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111555566667777",
                     "card_not_present": True,
                     "cvv": "999", "expiry": "12/28",
                     "merchant_id": f"WEB-{country}",
                     "threeds_completed": True},
            amount=4_900)
        n += 1
    return {"geo_diverse_attempts": n}


def run_ussd_session_replay_attack(ctx: ScenarioContext) -> Dict[str, Any]:
    """USSD session-replay: same session-id used repeatedly."""
    msisdn = _msisdn(ctx.seed, 5555)
    sess = "REPLAY-001"
    n = 0
    for i in range(10):
        r = ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": msisdn,
                     "text": "1*1*10000*1234",
                     "session_id": sess})
        n += 1
    return {"replay_attempts": n}


FRAUD_SCENARIOS = [
    Scenario(name="card_testing_attack",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="Card testing: rapid small CNP attempts against random PANs",
        runner=run_card_testing_attack,
        tags=["cards", "cnp", "card-testing"],
        expected_event_types=["integration.cards.call", "integration.cards.failure"],
        realistic_basis="Common merchant-attack: test stolen card BINs with $1 charges"),
    Scenario(name="bin_attack_visa",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="BIN attack: sequential PANs on a single Visa BIN range",
        runner=run_bin_attack_visa, tags=["cards", "bin", "fraud"],
        expected_event_types=["integration.cards.call"],
        realistic_basis="Fraudsters enumerate PANs in known live BIN ranges"),
    Scenario(name="atm_skimming_pattern",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="ATM skimming: same PAN cycled across multiple terminals quickly",
        runner=run_atm_skimming_pattern,
        tags=["atm", "skimming"],
        expected_event_types=["integration.atm.call"],
        realistic_basis="Skimmer device captures PAN; cloned card used at multiple ATMs same day"),
    Scenario(name="high_value_cnp_no_3ds",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.MEDIUM,
        description="20 attempts to bypass 3DS on high-value CNP (should all step-up)",
        runner=run_high_value_cnp_no_3ds,
        tags=["cards", "3ds", "bypass-attempt"],
        expected_event_types=["integration.cards.failure"],
        realistic_basis="Fraudster tests whether merchant skips 3DS challenge"),
    Scenario(name="refund_abuse",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.MEDIUM,
        description="Refund abuse: repeated REFUND ops from a single PAN",
        runner=run_refund_abuse, tags=["cards", "refund-abuse"],
        expected_event_types=["integration.cards.call"],
        realistic_basis="Merchant insider scheme: process refunds on cards not used for purchase"),
    Scenario(name="mpesa_sim_swap",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="SIM swap attack: rapid M-Pesa drain attempts from a fresh msisdn",
        runner=run_mpesa_sim_swap,
        tags=["mpesa", "sim-swap"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Kenyan SIM-swap fraud: attacker drains M-Pesa minutes after swap"),
    Scenario(name="ussd_account_takeover",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="USSD takeover: brute-force PIN attempts via repeated sessions",
        runner=run_ussd_account_takeover, tags=["ussd", "takeover", "pin-brute"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Stolen handset / shoulder-surf PIN brute force via USSD menu"),
    Scenario(name="mpesa_structuring",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.CRITICAL,
        description="Structuring: 15 sub-threshold M-Pesa transactions",
        runner=run_mpesa_structuring, tags=["mpesa", "structuring", "aml"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Classic AML pattern: split amount to stay under reporting threshold"),
    Scenario(name="mule_account_chain_kic",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.CRITICAL,
        description="Mule chain: 12 KIC EFT_CREDIT legs cycling through suspect accounts",
        runner=run_mule_account_chain_kic,
        tags=["kic", "mule", "layering", "aml"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="Money-laundering layering: rapid cycling through related accounts"),
    Scenario(name="rtgs_split_to_multi_beneficiaries",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="High-value RTGS split: large amount sent to 8 beneficiaries",
        runner=run_rtgs_split_to_multi_beneficiaries,
        tags=["rtgs", "split", "smurfing"],
        expected_event_types=["integration.rtgs.call"],
        realistic_basis="Mule network distribution: single source -> many beneficiaries"),
    Scenario(name="round_dollar_swift_pattern",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="SWIFT MT103 round-dollar amounts to single beneficiary",
        runner=run_round_dollar_swift_pattern,
        tags=["swift", "round-amount", "aml"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="Just-below-$10K rounded patterns flagged by FATF AML rules"),
    Scenario(name="velocity_fraud_card_burst",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="Card velocity: 25 transactions from one PAN in tight burst",
        runner=run_velocity_fraud_card_burst,
        tags=["cards", "velocity", "fraud"],
        expected_event_types=["integration.cards.call"],
        realistic_basis="Velocity rule trigger: card scheme flags 'too many in short period'"),
    Scenario(name="geo_anomaly_card_use",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="Same PAN used in geographically-impossible locations",
        runner=run_geo_anomaly_card_use,
        tags=["cards", "geo-anomaly", "atm"],
        expected_event_types=["integration.atm.call"],
        realistic_basis="Cloned card pattern: simultaneous transactions in distant cities"),
    Scenario(name="pin_brute_force",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.MEDIUM,
        description="ATM PIN brute-force: 6 attempts on same PAN",
        runner=run_pin_brute_force, tags=["atm", "pin", "brute-force"],
        expected_event_types=["integration.atm.call", "integration.atm.failure"],
        realistic_basis="Sequential PIN guessing pattern at ATM"),
    Scenario(name="swift_mt103_to_high_risk",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="SWIFT MT103 to high-risk corridor",
        runner=run_swift_mt103_to_high_risk,
        tags=["swift", "high-risk-corridor", "aml"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="Outbound to high-risk corridor (FATF grey/blacklist exposure)"),
    Scenario(name="mpesa_dormant_acc_revival_spike",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.MEDIUM,
        description="Long-dormant accounts suddenly active on M-Pesa",
        runner=run_mpesa_dormant_acc_revival_spike,
        tags=["mpesa", "dormant-revival", "aml"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Dormant-account mule pattern: account silent for years, then active"),
    Scenario(name="card_present_at_atm_after_block",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.LOW,
        description="Blocked-card retry: same PAN keeps trying after declines",
        runner=run_card_present_at_atm_after_block,
        tags=["atm", "blocked-retry"],
        expected_event_types=["integration.atm.failure"],
        realistic_basis="Stolen card holder attempts withdrawal at multiple ATMs"),
    Scenario(name="kic_to_pep_account",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.CRITICAL,
        description="Repeated KIC EFT_CREDIT to a politically-exposed-person account",
        runner=run_kic_to_pep_account, tags=["kic", "pep", "compliance"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="PEP exposure: AML enhanced-due-diligence trigger"),
    Scenario(name="rapid_card_in_5_countries",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.HIGH,
        description="CNP from 5 different country geos within 10 min",
        runner=run_rapid_card_in_5_countries,
        tags=["cards", "cnp", "geo-velocity"],
        expected_event_types=["integration.cards.call"],
        realistic_basis="Cross-border velocity attack on CNP merchants"),
    Scenario(name="ussd_session_replay_attack",
        category=ScenarioCategory.FRAUD, severity=ScenarioSeverity.MEDIUM,
        description="USSD session-replay: same session-id used repeatedly",
        runner=run_ussd_session_replay_attack,
        tags=["ussd", "session-replay"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Network attacker tries to reuse a captured USSD session"),
]

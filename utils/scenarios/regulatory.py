"""utils/scenarios/regulatory.py — AML / sanctions / KYC / reporting (20)."""

from __future__ import annotations

from typing import Any, Dict

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioContext, ScenarioSeverity,
)


def _msisdn(seed: int, offset: int = 0) -> str:
    return f"2547{(seed * 12345 + 100000 + offset) % 100_000_000:08d}"


def run_aml_structuring_mpesa(ctx: ScenarioContext) -> Dict[str, Any]:
    """AML structuring: 12 M-Pesa sub-threshold payments same beneficiary."""
    n = 0
    for i in range(12):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "BusinessPayment",
                     "msisdn": _msisdn(ctx.seed, 5500),
                     "amount": 140_000, "paybill": "999888"},
            amount=140_000)
        n += 1
    return {"structured_txns": n}


def run_aml_structuring_kic(ctx: ScenarioContext) -> Dict[str, Any]:
    """KIC structuring: 10 sub-1M payments to single beneficiary."""
    n = 0
    for i in range(10):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011",
                     "narrative": "Personal"},
            amount=975_000,
            debit_account="STR-ORG",
            credit_account="STR-BEN-001")
        n += 1
    return {"structured_kic_txns": n}


def run_sanctioned_beneficiary_swift(ctx: ScenarioContext) -> Dict[str, Any]:
    """Outbound SWIFT to a sanctioned-list jurisdiction."""
    n = 0
    for i in range(4):
        ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "CUSTOMER",
                     "beneficiary_bic": "SANCBANK",   # sanctioned (synthetic)
                     "beneficiary_name": "SDN PARTY",
                     "amount": 50_000.0},
            amount=50_000.0, currency="USD",
            debit_account="X", credit_account="Y")
        n += 1
    return {"sanctioned_attempts": n}


def run_kyc_tier_limit_breach_mpesa(ctx: ScenarioContext) -> Dict[str, Any]:
    """M-Pesa Tier-1 customer attempts repeated transactions above tier limit."""
    n = 0; fails = 0
    for i in range(8):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "BusinessPayment",
                     "msisdn": _msisdn(ctx.seed, 6500),
                     "amount": 145_000, "paybill": "777666"},
            amount=145_000)
        n += 1
        if not r.success: fails += 1
    return {"attempts": n, "limit_blocks": fails}


def run_cbk_pep_screening_hits(ctx: ScenarioContext) -> Dict[str, Any]:
    """KIC payments where beneficiary appears on PEP list."""
    n = 0
    for i in range(5):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001",
                     "narrative": "Consulting"},
            amount=750_000,
            debit_account="ORG-A",
            credit_account="PEP-LISTED-001")
        n += 1
    return {"pep_hits": n}


def run_high_value_threshold_reporting(ctx: ScenarioContext) -> Dict[str, Any]:
    """High-value RTGS transactions requiring CBK reporting (above KES 10M)."""
    n = 0
    for i in range(6):
        ctx.submit_channel("rtgs",
            payload={"amount": 15_000_000 + (i * 1_000_000),
                     "debit_account": "MAIN",
                     "credit_account": f"BEN-{i:04d}",
                     "beneficiary_bank_bic": "BARCKENX"},
            amount=15_000_000 + (i * 1_000_000))
        n += 1
    return {"reportable_txns": n}


def run_ofac_screen_match(ctx: ScenarioContext) -> Dict[str, Any]:
    """SWIFT with OFAC-list match in ordering customer name."""
    n = 0
    for i in range(3):
        ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "OFAC LISTED PERSON",
                     "beneficiary_bic": "CHASUS33",
                     "beneficiary_name": "BEN",
                     "amount": 8_500.0},
            amount=8_500.0, currency="USD",
            debit_account="X", credit_account="Y")
        n += 1
    return {"ofac_attempts": n}


def run_round_number_threshold_evasion(ctx: ScenarioContext) -> Dict[str, Any]:
    """Round-number amounts just below USD 10,000 threshold."""
    n = 0
    for amt in [9_999, 9_990, 9_950, 9_975, 9_888]:
        ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "ROUND",
                     "beneficiary_bic": "CHASUS33",
                     "beneficiary_name": "B",
                     "amount": float(amt)},
            amount=float(amt), currency="USD",
            debit_account="X", credit_account="Y")
        n += 1
    return {"round_evasion_txns": n}


def run_eft_to_unregistered_business(ctx: ScenarioContext) -> Dict[str, Any]:
    """KIC EFT to KRA-unregistered counterparty (regulatory red flag)."""
    n = 0
    for i in range(6):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "044",
                     "narrative": "Vendor payment"},
            amount=825_000,
            debit_account="MAIN-CORP",
            credit_account="UNREG-VEND-001")
        n += 1
    return {"unregistered_txns": n}


def run_ifrs9_period_end_freeze_window(ctx: ScenarioContext) -> Dict[str, Any]:
    """IFRS9 reporting freeze: 15 KIC transactions during freeze window."""
    n = 0
    for i in range(15):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001"},
            amount=300_000, debit_account="FREEZE",
            credit_account=f"BEN-{i:04d}")
        n += 1
    return {"during_freeze_txns": n}


def run_dpa_consent_failure_logging(ctx: ScenarioContext) -> Dict[str, Any]:
    """DPA: 10 USSD logged WITHOUT consent (regulatory breach trace)."""
    n = 0
    for i in range(10):
        ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": _msisdn(ctx.seed, 7500 + i),
                     "text": "1*1"})
        n += 1
    return {"unconsented_logs": n}


def run_cross_border_above_limit(ctx: ScenarioContext) -> Dict[str, Any]:
    """5 SWIFT MT103 above Kenya cross-border declaration threshold (USD 10K)."""
    n = 0
    for i in range(5):
        ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": "CUST-INDIV",
                     "beneficiary_bic": "BARCGB22",
                     "beneficiary_name": "B",
                     "amount": 18_500.0},
            amount=18_500.0, currency="USD",
            debit_account="X", credit_account="Y")
        n += 1
    return {"reportable_x_border": n}


def run_kra_etims_invoice_breach(ctx: ScenarioContext) -> Dict[str, Any]:
    """Corporate KIC paid without ETIMS invoice number (KRA breach)."""
    n = 0
    for i in range(8):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001",
                     "narrative": "NO_ETIMS"},  # no invoice ref
            amount=320_000,
            debit_account="CORP-A",
            credit_account="SUPP-1")
        n += 1
    return {"non_etims_txns": n}


def run_aml_layering_atm_to_mpesa_kic(ctx: ScenarioContext) -> Dict[str, Any]:
    """Layering: ATM-cash-out -> M-Pesa -> KIC (multi-channel layering)."""
    legs = 0
    # 5 ATM withdrawals
    for i in range(5):
        ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": "4111000099990000",
                     "amount": 39_000,
                     "terminal_id": f"L-{i}"},
            amount=39_000)
        legs += 1
    # 5 M-Pesa
    for i in range(5):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "BusinessPayment",
                     "msisdn": _msisdn(ctx.seed, 8500 + i),
                     "amount": 130_000, "paybill": "555444"},
            amount=130_000)
        legs += 1
    # 3 KIC
    for i in range(3):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011"},
            amount=850_000, debit_account="L-CORP",
            credit_account=f"L-BEN-{i}")
        legs += 1
    return {"layering_legs": legs}


def run_cbk_cash_threshold_reporting(ctx: ScenarioContext) -> Dict[str, Any]:
    """ATM cash withdrawals exceeding CBK reporting threshold (KES 1M cumulative)."""
    n = 0
    pan = "4111000088880000"
    for i in range(25):
        ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL", "pan": pan,
                     "amount": 40_000, "terminal_id": f"T-{i:03d}"},
            amount=40_000)
        n += 1
    return {"cumulative_txns": n,
             "cumulative_amount": 25 * 40_000}


def run_cma_market_abuse_trade_pattern(ctx: ScenarioContext) -> Dict[str, Any]:
    """CMA market abuse pattern: same trader pattern across 7 RTGS legs."""
    n = 0
    for i in range(7):
        ctx.submit_channel("rtgs",
            payload={"amount": 8_500_000,
                     "debit_account": "TRADER-ALPHA",
                     "credit_account": "NSE-CLEAR",
                     "beneficiary_bank_bic": "CFCKENA"},
            amount=8_500_000)
        n += 1
    return {"market_abuse_legs": n}


def run_pra_protected_account_breach(ctx: ScenarioContext) -> Dict[str, Any]:
    """Privacy regulator: PRA-protected account fields accessed during USSD."""
    n = 0
    for i in range(12):
        ctx.submit_channel("ussd",
            payload={"ussd_code": "*334*8#",  # account-detail menu
                     "msisdn": _msisdn(ctx.seed, 9500 + i),
                     "text": "2*1"})
        n += 1
    return {"protected_accesses": n}


def run_dormancy_threshold_reactivation(ctx: ScenarioContext) -> Dict[str, Any]:
    """Reactivation pattern for dormant accounts (CBK 3-year dormancy rule)."""
    n = 0
    for i in range(8):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_DEBIT",
                     "beneficiary_bank_code": "044",
                     "narrative": "REACT-DORMANT"},
            amount=480_000,
            debit_account=f"DORMANT-{i:04d}",
            credit_account="MAIN-COLLECT")
        n += 1
    return {"reactivations": n}


def run_tax_compliance_quarterly_anomaly(ctx: ScenarioContext) -> Dict[str, Any]:
    """Quarterly tax-pattern anomaly: usual KRA payment skipped."""
    n = 0
    # Customer normally pays KES 2.5M quarterly to KRA; this quarter only 0.5M
    for i in range(3):
        ctx.submit_channel("rtgs",
            payload={"amount": 450_000,
                     "debit_account": "CORP-A",
                     "credit_account": "KRA-COLLECT",
                     "beneficiary_bank_bic": "CBKEKENX"},
            amount=450_000)
        n += 1
    return {"underpaid_quarters": n}


def run_data_breach_export_attempt(ctx: ScenarioContext) -> Dict[str, Any]:
    """5 large KIC EFTs to cloud-storage provider (data-exfil pattern)."""
    n = 0
    for i in range(5):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "044",
                     "narrative": "AWS bill"},
            amount=550_000, debit_account="IT-OPS",
            credit_account="CLOUD-PROVIDER-001")
        n += 1
    return {"cloud_payments": n}


REGULATORY_SCENARIOS = [
    Scenario(name="aml_structuring_mpesa", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.CRITICAL,
        description="AML structuring: 12 M-Pesa sub-threshold payments same beneficiary",
        runner=run_aml_structuring_mpesa, tags=["aml", "structuring", "mpesa"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Classic AML pattern: stay just below USD 10K/equivalent"),
    Scenario(name="aml_structuring_kic", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.CRITICAL,
        description="KIC structuring: 10 sub-1M payments to single beneficiary",
        runner=run_aml_structuring_kic, tags=["aml", "structuring", "kic"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="Repeated below-RTGS amounts to same beneficiary triggers SAR"),
    Scenario(name="sanctioned_beneficiary_swift", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.CRITICAL,
        description="Outbound SWIFT to a sanctioned-list jurisdiction",
        runner=run_sanctioned_beneficiary_swift, tags=["swift", "sanctions", "ofac"],
        expected_event_types=["integration.swift.failure"],
        realistic_basis="OFAC SDN / EU / UN sanctions screening hit"),
    Scenario(name="kyc_tier_limit_breach_mpesa", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="M-Pesa Tier-1 customer attempts above tier limit",
        runner=run_kyc_tier_limit_breach_mpesa, tags=["mpesa", "kyc", "tier-limit"],
        expected_event_types=["integration.mpesa.failure"],
        realistic_basis="KYC tier limit enforcement"),
    Scenario(name="cbk_pep_screening_hits", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.CRITICAL,
        description="KIC payments where beneficiary appears on PEP list",
        runner=run_cbk_pep_screening_hits, tags=["kic", "pep", "screening"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="CBK PEP/risk-based EDD requirement"),
    Scenario(name="high_value_threshold_reporting", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="High-value RTGS transactions requiring CBK reporting (above KES 10M)",
        runner=run_high_value_threshold_reporting,
        tags=["rtgs", "cbk", "reporting"],
        expected_event_types=["integration.rtgs.call"],
        realistic_basis="CBK large-cash-transaction reporting requirement"),
    Scenario(name="ofac_screen_match", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.CRITICAL,
        description="SWIFT with OFAC-list match in ordering customer name",
        runner=run_ofac_screen_match, tags=["swift", "ofac", "sanctions"],
        expected_event_types=["integration.swift.failure"],
        realistic_basis="Real-time sanctions screening on outbound SWIFT"),
    Scenario(name="round_number_threshold_evasion", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="Round-number amounts just below USD 10,000 threshold",
        runner=run_round_number_threshold_evasion,
        tags=["swift", "aml", "threshold-evasion"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="Round-amount pattern strongly suggests intentional structuring"),
    Scenario(name="eft_to_unregistered_business", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.MEDIUM,
        description="KIC EFT to KRA-unregistered counterparty",
        runner=run_eft_to_unregistered_business, tags=["kic", "kra", "unregistered"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="KRA i-Tax compliance check: counterparty must be registered"),
    Scenario(name="ifrs9_period_end_freeze_window", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.MEDIUM,
        description="IFRS9 reporting freeze: KIC transactions during freeze window",
        runner=run_ifrs9_period_end_freeze_window, tags=["kic", "ifrs9", "freeze"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="Period-end accounting freeze for IFRS9 ECL computation"),
    Scenario(name="dpa_consent_failure_logging", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="DPA: USSD interactions logged without consent",
        runner=run_dpa_consent_failure_logging, tags=["ussd", "dpa", "privacy"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Kenya Data Protection Act consent failure"),
    Scenario(name="cross_border_above_limit", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="SWIFT MT103 above Kenya cross-border declaration threshold",
        runner=run_cross_border_above_limit, tags=["swift", "cross-border", "declaration"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="CBK cross-border outflow declaration threshold"),
    Scenario(name="kra_etims_invoice_breach", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.MEDIUM,
        description="Corporate KIC paid without ETIMS invoice (KRA breach)",
        runner=run_kra_etims_invoice_breach, tags=["kic", "kra", "etims"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="KRA ETIMS e-invoicing requirement"),
    Scenario(name="aml_layering_atm_to_mpesa_kic", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.CRITICAL,
        description="Layering: ATM-cash-out -> M-Pesa -> KIC (multi-channel)",
        runner=run_aml_layering_atm_to_mpesa_kic,
        tags=["aml", "layering", "multi-channel"],
        expected_event_types=["integration.atm.call", "integration.mpesa.call", "integration.kic.call"],
        realistic_basis="Sophisticated AML layering across channels to obscure trail"),
    Scenario(name="cbk_cash_threshold_reporting", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="ATM cash withdrawals exceeding CBK reporting threshold",
        runner=run_cbk_cash_threshold_reporting,
        tags=["atm", "cbk", "cash-reporting"],
        expected_event_types=["integration.atm.call"],
        realistic_basis="CBK large-cash-transaction reporting"),
    Scenario(name="cma_market_abuse_trade_pattern", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="CMA market abuse pattern across 7 RTGS legs",
        runner=run_cma_market_abuse_trade_pattern, tags=["rtgs", "cma", "market-abuse"],
        expected_event_types=["integration.rtgs.call"],
        realistic_basis="Capital Markets Authority surveillance"),
    Scenario(name="pra_protected_account_breach", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.MEDIUM,
        description="Privacy: PRA-protected account fields accessed during USSD",
        runner=run_pra_protected_account_breach, tags=["ussd", "dpa", "protected-fields"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Excessive PII exposure in USSD response"),
    Scenario(name="dormancy_threshold_reactivation", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.MEDIUM,
        description="Reactivation pattern for dormant accounts (CBK 3-year rule)",
        runner=run_dormancy_threshold_reactivation, tags=["kic", "dormancy"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="CBK Prudential Guidelines dormancy treatment"),
    Scenario(name="tax_compliance_quarterly_anomaly", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.MEDIUM,
        description="Quarterly tax-pattern anomaly: KRA underpayment",
        runner=run_tax_compliance_quarterly_anomaly,
        tags=["rtgs", "kra", "tax-anomaly"],
        expected_event_types=["integration.rtgs.call"],
        realistic_basis="Tax avoidance pattern detection"),
    Scenario(name="data_breach_export_attempt", category=ScenarioCategory.REGULATORY,
        severity=ScenarioSeverity.HIGH,
        description="Large KIC EFTs to cloud-storage provider (data-exfil pattern)",
        runner=run_data_breach_export_attempt, tags=["kic", "data-exfil"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="Insider data-exfiltration via cloud-storage payments"),
]

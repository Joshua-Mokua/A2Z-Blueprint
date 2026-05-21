"""utils/scenarios/operational.py — Realistic operational traffic patterns.

20 scenarios covering peak loads, EOM/payroll bursts, channel-specific
surges that the body sees in normal business operation.
"""

from __future__ import annotations

from typing import Any, Dict

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioContext, ScenarioSeverity,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _mk_pan(seed: int, prefix: str = "4111") -> str:
    """Generate a 16-digit PAN with deterministic suffix from seed."""
    suffix = f"{(seed * 31415926) % (10**12):012d}"
    return f"{prefix}{suffix}"


def _mk_msisdn(seed: int) -> str:
    return f"2547{(seed * 12345 + 100000) % 100_000_000:08d}"


def _mk_account(seed: int) -> str:
    return f"ECO{(seed * 7919) % (10**10):010d}"


# ─────────────────────────────────────────────────────────────────────
# Salary / payroll patterns
# ─────────────────────────────────────────────────────────────────────

def run_payroll_kic_batch_small(ctx: ScenarioContext) -> Dict[str, Any]:
    """Branch-level payroll: 25 employees, KIC EFT batch."""
    n = 0; fails = 0
    for i in range(25):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011",
                     "narrative": f"Salary May 2026 emp{i}"},
            amount=45_000 + (i * 1500), debit_account="PAYROLL-001",
            credit_account=_mk_account(ctx.seed + i))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_payroll_kic_batch_large(ctx: ScenarioContext) -> Dict[str, Any]:
    """Bank-wide payroll: 487 employees (Ecobank staff count)."""
    n = 0; fails = 0
    for i in range(487):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011" if i % 3 == 0 else "001",
                     "narrative": "Monthly salary"},
            amount=35_000 + (i * 850), debit_account="PAYROLL-MAIN",
            credit_account=_mk_account(ctx.seed + i))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_payroll_atm_rush(ctx: ScenarioContext) -> Dict[str, Any]:
    """Salary-day ATM withdrawal rush — 50 transactions across branches."""
    n = 0; fails = 0
    for i in range(50):
        r = ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": _mk_pan(ctx.seed + i),
                     "amount": 5_000 + (i % 5) * 1_000,
                     "terminal_id": f"ECONA{(i % 35):04d}"},
            amount=5_000 + (i % 5) * 1_000)
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_salary_day_mpesa_uplift(ctx: ScenarioContext) -> Dict[str, Any]:
    """Salary day: M-Pesa send-money + bill-pay surge."""
    n = 0; fails = 0
    for i in range(40):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type":
                       "CustomerPayBillOnline" if i % 2 == 0 else "BusinessPayment",
                     "msisdn": _mk_msisdn(ctx.seed + i),
                     "amount": 1_500 + (i * 200),
                     "paybill": "888880" if i % 2 == 0 else None,
                     "account_reference": "RENT" if i % 3 == 0 else "BILL"},
            amount=1_500 + (i * 200))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


# ─────────────────────────────────────────────────────────────────────
# Peak / EOM patterns
# ─────────────────────────────────────────────────────────────────────

def run_eom_cards_spike(ctx: ScenarioContext) -> Dict[str, Any]:
    """End-of-month card spending spike: 80 POS purchases."""
    n = 0; fails = 0
    schemes = ["4111111111111111", "5500000000000004",
                "5500000000000022", "4111111111111122"]
    for i in range(80):
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": schemes[i % len(schemes)],
                     "card_not_present": False,
                     "cvv": f"{(100 + i) % 1000:03d}",
                     "expiry": "12/28",
                     "merchant_id": f"M{(i % 20):04d}"},
            amount=2_500 + (i * 100))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_black_friday_cnp_spike(ctx: ScenarioContext) -> Dict[str, Any]:
    """Black Friday e-commerce: 60 CNP transactions, mostly small (no 3DS)."""
    n = 0; fails = 0; threeds_hits = 0
    for i in range(60):
        # 30% are high-value (>= 5k) and will hit 3DS step-up
        amount = 8_000 if i % 3 == 0 else 2_500
        r = ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111111111111111",
                     "card_not_present": True,
                     "cvv": "123", "expiry": "12/28",
                     "merchant_id": "JUMIA001",
                     "threeds_completed": i % 3 != 0},
            amount=amount)
        n += 1
        if not r.success: fails += 1
        if r.error_code == "3DS_REQUIRED": threeds_hits += 1
    return {"transactions": n, "failures": fails, "threeds_hits": threeds_hits}


def run_kepss_cutoff_stampede(ctx: ScenarioContext) -> Dict[str, Any]:
    """Pre-cutoff KEPSS RTGS rush: 30 high-value transfers."""
    n = 0; fails = 0
    for i in range(30):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 1_500_000 + (i * 250_000),
                     "debit_account": _mk_account(ctx.seed + i),
                     "credit_account": _mk_account(ctx.seed + 100 + i),
                     "beneficiary_bank_bic": "BARCKENX"},
            amount=1_500_000 + (i * 250_000))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_diaspora_remittance_inflow(ctx: ScenarioContext) -> Dict[str, Any]:
    """Diaspora SWIFT MT103 inflows from 5 corridors."""
    bics = ["CHASUS33", "BOFAUS3N", "BARCGB22", "DBSSSGSG", "EBILAEAD"]
    n = 0; fails = 0
    for i in range(15):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": f"DIASPORA NAME {i}",
                     "beneficiary_bic": "ECOCKENA",
                     "beneficiary_name": f"BENEFICIARY {i}",
                     "amount": 1_200.00},
            amount=1_200.00, currency="USD",
            debit_account=bics[i % 5],
            credit_account=_mk_account(ctx.seed + i))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_corporate_treasury_sweep(ctx: ScenarioContext) -> Dict[str, Any]:
    """Corporate quarterly cash sweep: 10 RTGS legs to sister banks."""
    bics = ["KCBLKENX", "BARCKENX", "EQBLKENA", "SCBLKENX", "CFCKENA"]
    n = 0; fails = 0
    for i in range(10):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 25_000_000 + (i * 5_000_000),
                     "debit_account": "CORP-TRES-001",
                     "credit_account": _mk_account(ctx.seed + 200 + i),
                     "beneficiary_bank_bic": bics[i % 5]},
            amount=25_000_000 + (i * 5_000_000))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_supplier_payment_batch(ctx: ScenarioContext) -> Dict[str, Any]:
    """Quarterly supplier KIC EFT_CREDIT batch: 35 payments."""
    n = 0; fails = 0
    for i in range(35):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001" if i % 2 else "011",
                     "narrative": f"PO-{2026000 + i}"},
            amount=250_000 + (i * 15_000),
            debit_account="SUPP-PAY-001",
            credit_account=_mk_account(ctx.seed + 300 + i))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_utility_direct_debit_batch(ctx: ScenarioContext) -> Dict[str, Any]:
    """Utility company collection batch: 50 EFT_DEBIT."""
    n = 0; fails = 0
    for i in range(50):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_DEBIT",
                     "beneficiary_bank_code": "044",  # Collecting onto Ecobank
                     "narrative": "Electricity bill"},
            amount=2_500 + (i * 150),
            debit_account=_mk_account(ctx.seed + 400 + i),
            credit_account="KPLC-COLLECT")
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_cheque_clearing_day(ctx: ScenarioContext) -> Dict[str, Any]:
    """Daily cheque truncation batch: 40 inward + outward."""
    n = 0; fails = 0
    for i in range(40):
        ttype = "CHEQUE_INWARD" if i % 2 == 0 else "CHEQUE_OUTWARD"
        r = ctx.submit_channel("kic",
            payload={"transaction_type": ttype,
                     "beneficiary_bank_code": ["001", "011", "066"][i % 3],
                     "cheque_number": f"{200000 + i:06d}",
                     "debit_account": "CHEQUE-CLEAR-1"},
            amount=15_000 + (i * 500),
            credit_account=_mk_account(ctx.seed + 500 + i))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_school_fees_ussd_window(ctx: ScenarioContext) -> Dict[str, Any]:
    """School fees deadline: USSD bank-to-bill peak."""
    n = 0; fails = 0
    for i in range(30):
        r = ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": _mk_msisdn(ctx.seed + 600 + i),
                     "text": f"5*1*{45000 + i*100}*1234"})
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_ride_hailing_mpesa_spike(ctx: ScenarioContext) -> Dict[str, Any]:
    """Friday evening Uber/Bolt M-Pesa till spike."""
    n = 0; fails = 0
    for i in range(45):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerBuyGoodsOnline",
                     "msisdn": _mk_msisdn(ctx.seed + 700 + i),
                     "amount": 350 + (i * 50),
                     "till_number": "880100",
                     "account_reference": "Uber"},
            amount=350 + (i * 50))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_morning_branch_opening(ctx: ScenarioContext) -> Dict[str, Any]:
    """Branch opens — 30 ATM balance inquiries + 15 cheque deposits in 1 hr."""
    n = 0; fails = 0
    for i in range(30):
        r = ctx.submit_channel("atm",
            payload={"operation": "BALANCE_INQUIRY",
                     "pan": _mk_pan(ctx.seed + 800 + i),
                     "terminal_id": "BRANCH-001"})
        n += 1
        if not r.success: fails += 1
    for i in range(15):
        r = ctx.submit_channel("kic",
            payload={"transaction_type": "CHEQUE_INWARD",
                     "beneficiary_bank_code": "001",
                     "cheque_number": f"{300000 + i:06d}",
                     "debit_account": "INWARD-CLEAR"},
            amount=85_000 + (i * 1500),
            credit_account=_mk_account(ctx.seed + 900 + i))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_quarterly_tax_payment(ctx: ScenarioContext) -> Dict[str, Any]:
    """Corporate quarterly tax remittance via RTGS to KRA."""
    n = 0; fails = 0
    for i in range(8):
        r = ctx.submit_channel("rtgs",
            payload={"amount": 12_500_000 + (i * 1_500_000),
                     "debit_account": "CORP-TAX-DUE",
                     "credit_account": "KRA-COLLECT-001",
                     "beneficiary_bank_bic": "CBKEKENX"},
            amount=12_500_000 + (i * 1_500_000))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_bank_to_bank_settlement(ctx: ScenarioContext) -> Dict[str, Any]:
    """Inter-bank MT202 settlement: 12 legs across correspondents."""
    bics = ["CHASUS33", "DEUTDEFF", "BNPAFRPP", "HSBCGB2L"]
    n = 0; fails = 0
    for i in range(12):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "202",
                     "beneficiary_bic": bics[i % len(bics)],
                     "amount": 800_000.00,
                     "related_reference": f"NETTING-{2026000+i}"},
            amount=800_000.00, currency="USD",
            debit_account="NOSTRO-USD-1",
            credit_account="VOSTRO-1")
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_payroll_tier3_ussd_pull(ctx: ScenarioContext) -> Dict[str, Any]:
    """Casual workers (tier 3): USSD balance + small withdrawal pulls."""
    n = 0; fails = 0
    for i in range(60):
        r = ctx.submit_channel("ussd",
            payload={"ussd_code": "*334#",
                     "msisdn": _mk_msisdn(ctx.seed + 1000 + i),
                     "text": "1*2"})  # menu: balance check
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_mpesa_paybill_landlord_collection(ctx: ScenarioContext) -> Dict[str, Any]:
    """Month-start landlord paybill collection: 35 tenants."""
    n = 0; fails = 0
    for i in range(35):
        r = ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                     "msisdn": _mk_msisdn(ctx.seed + 1100 + i),
                     "amount": 25_000 + (i * 1_000),
                     "paybill": "808080",
                     "account_reference": f"FLAT-{i:03d}"},
            amount=25_000 + (i * 1_000))
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


def run_swift_nostro_funding(ctx: ScenarioContext) -> Dict[str, Any]:
    """NOSTRO replenishment via MT202 cover (small batch)."""
    n = 0; fails = 0
    for i in range(5):
        r = ctx.submit_channel("swift",
            payload={"mt_type": "202",
                     "beneficiary_bic": "CHASUS33",
                     "amount": 2_500_000.00},
            amount=2_500_000.00, currency="USD",
            debit_account="NOSTRO-FUND",
            credit_account="NOSTRO-USD-1")
        n += 1
        if not r.success: fails += 1
    return {"transactions": n, "failures": fails}


# ─────────────────────────────────────────────────────────────────────
# SCENARIOS list (consumed by registry)
# ─────────────────────────────────────────────────────────────────────

OPERATIONAL_SCENARIOS = [
    Scenario(name="payroll_kic_batch_small",
        category=ScenarioCategory.OPERATIONAL,
        description="Branch-level payroll: 25 employees, KIC EFT batch",
        runner=run_payroll_kic_batch_small,
        severity=ScenarioSeverity.INFO,
        tags=["payroll", "kic", "salary-day"],
        expected_event_types=["integration.kic.call", "integration.kic.success"],
        realistic_basis="A typical Kenyan bank branch processes 20-30 staff payroll via KIC monthly"),
    Scenario(name="payroll_kic_batch_large",
        category=ScenarioCategory.OPERATIONAL,
        description="Bank-wide payroll: 487 employees (Ecobank scale)",
        runner=run_payroll_kic_batch_large,
        severity=ScenarioSeverity.LOW,
        tags=["payroll", "kic", "salary-day", "high-volume"],
        expected_event_types=["integration.kic.call", "integration.kic.success"],
        realistic_basis="Ecobank Kenya has 487 staff (Joshua's memory); monthly salary batch ~480 txns"),
    Scenario(name="payroll_atm_rush",
        category=ScenarioCategory.OPERATIONAL,
        description="Salary-day ATM withdrawal rush across 35 branches",
        runner=run_payroll_atm_rush,
        severity=ScenarioSeverity.LOW,
        tags=["payroll", "atm", "salary-day"],
        expected_event_types=["integration.atm.call", "integration.atm.success"],
        realistic_basis="Salary day spike: ATMs across 35 branches see 1.5-3x normal volume"),
    Scenario(name="salary_day_mpesa_uplift",
        category=ScenarioCategory.OPERATIONAL,
        description="Salary day: M-Pesa send-money + bill-pay surge",
        runner=run_salary_day_mpesa_uplift,
        severity=ScenarioSeverity.LOW,
        tags=["payroll", "mpesa", "salary-day"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Kenyan salary day drives 4x M-Pesa till volume vs non-salary days"),
    Scenario(name="eom_cards_spike",
        category=ScenarioCategory.OPERATIONAL,
        description="End-of-month card spending spike: 80 POS purchases",
        runner=run_eom_cards_spike,
        severity=ScenarioSeverity.LOW,
        tags=["eom", "cards", "pos"],
        expected_event_types=["integration.cards.call"],
        realistic_basis="EOM consumer spending: groceries, household goods, dining"),
    Scenario(name="black_friday_cnp_spike",
        category=ScenarioCategory.OPERATIONAL,
        description="Black Friday e-commerce 60 CNP transactions, 30% trigger 3DS",
        runner=run_black_friday_cnp_spike,
        severity=ScenarioSeverity.MEDIUM,
        tags=["eom", "cards", "cnp", "3ds"],
        expected_event_types=["integration.cards.call", "integration.cards.failure"],
        realistic_basis="Jumia Black Friday: card volume 10x, ~30% trigger 3DS step-up"),
    Scenario(name="kepss_cutoff_stampede",
        category=ScenarioCategory.OPERATIONAL,
        description="Pre-cutoff KEPSS RTGS rush: 30 high-value transfers",
        runner=run_kepss_cutoff_stampede,
        severity=ScenarioSeverity.MEDIUM,
        tags=["rtgs", "kepss", "cutoff"],
        expected_event_types=["integration.rtgs.call", "integration.rtgs.success"],
        realistic_basis="RTGS volume tripled in the 30-min window before 4:30pm Nairobi cutoff"),
    Scenario(name="diaspora_remittance_inflow",
        category=ScenarioCategory.OPERATIONAL,
        description="Diaspora SWIFT MT103 inflows from 5 corridors",
        runner=run_diaspora_remittance_inflow,
        severity=ScenarioSeverity.INFO,
        tags=["swift", "diaspora", "inflow"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="Kenya receives ~$4B/yr diaspora remittances, predominantly USD/GBP corridors"),
    Scenario(name="corporate_treasury_sweep",
        category=ScenarioCategory.OPERATIONAL,
        description="Corporate quarterly cash sweep: 10 RTGS legs to sister banks",
        runner=run_corporate_treasury_sweep,
        severity=ScenarioSeverity.MEDIUM,
        tags=["rtgs", "corporate", "treasury"],
        expected_event_types=["integration.rtgs.call"],
        realistic_basis="Tier-1 corporates rebalance KES liquidity quarter-end via large RTGS legs"),
    Scenario(name="supplier_payment_batch",
        category=ScenarioCategory.OPERATIONAL,
        description="Quarterly supplier KIC EFT_CREDIT batch: 35 payments",
        runner=run_supplier_payment_batch,
        severity=ScenarioSeverity.INFO,
        tags=["kic", "supplier", "payable"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="SME treasury cycle: 30-50 supplier KIC payments quarterly"),
    Scenario(name="utility_direct_debit_batch",
        category=ScenarioCategory.OPERATIONAL,
        description="Utility company collection batch: 50 EFT_DEBIT",
        runner=run_utility_direct_debit_batch,
        severity=ScenarioSeverity.INFO,
        tags=["kic", "utility", "direct-debit"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="KPLC/Nairobi Water collect via KIC direct-debit; Ecobank acts as PSP"),
    Scenario(name="cheque_clearing_day",
        category=ScenarioCategory.OPERATIONAL,
        description="Daily cheque truncation batch: 40 inward + outward",
        runner=run_cheque_clearing_day,
        severity=ScenarioSeverity.INFO,
        tags=["kic", "cheque", "clearing"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="KEPSS cheque truncation: 30-60 cheques per branch per day"),
    Scenario(name="school_fees_ussd_window",
        category=ScenarioCategory.OPERATIONAL,
        description="School fees deadline: USSD bank-to-bill peak",
        runner=run_school_fees_ussd_window,
        severity=ScenarioSeverity.LOW,
        tags=["ussd", "school-fees", "deadline"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Term-1 January / Term-2 May school fees deadlines spike USSD payments"),
    Scenario(name="ride_hailing_mpesa_spike",
        category=ScenarioCategory.OPERATIONAL,
        description="Friday evening Uber/Bolt M-Pesa till spike",
        runner=run_ride_hailing_mpesa_spike,
        severity=ScenarioSeverity.INFO,
        tags=["mpesa", "ride-hailing", "till"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Nairobi Friday rush hour: Uber/Bolt till volume up 5x"),
    Scenario(name="morning_branch_opening",
        category=ScenarioCategory.OPERATIONAL,
        description="Branch opens: 30 ATM balance inquiries + 15 cheque deposits in 1 hr",
        runner=run_morning_branch_opening,
        severity=ScenarioSeverity.INFO,
        tags=["atm", "kic", "branch-opening"],
        expected_event_types=["integration.atm.call", "integration.kic.call"],
        realistic_basis="First-hour branch traffic: ATM queries, cheque deposits, balance checks"),
    Scenario(name="quarterly_tax_payment",
        category=ScenarioCategory.OPERATIONAL,
        description="Corporate quarterly tax remittance via RTGS to KRA",
        runner=run_quarterly_tax_payment,
        severity=ScenarioSeverity.MEDIUM,
        tags=["rtgs", "tax", "kra", "regulatory-deadline"],
        expected_event_types=["integration.rtgs.call"],
        realistic_basis="KRA quarterly corporate tax: 20th of month after quarter end"),
    Scenario(name="bank_to_bank_settlement",
        category=ScenarioCategory.OPERATIONAL,
        description="Inter-bank MT202 settlement: 12 legs across correspondents",
        runner=run_bank_to_bank_settlement,
        severity=ScenarioSeverity.MEDIUM,
        tags=["swift", "settlement", "interbank"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="End-of-day correspondent banking netting via MT202"),
    Scenario(name="payroll_tier3_ussd_pull",
        category=ScenarioCategory.OPERATIONAL,
        description="Casual workers (tier 3): USSD balance + small withdrawal pulls",
        runner=run_payroll_tier3_ussd_pull,
        severity=ScenarioSeverity.INFO,
        tags=["ussd", "balance", "tier3"],
        expected_event_types=["integration.ussd.call"],
        realistic_basis="Pay-day pattern for low-income earners: check balance, take cash"),
    Scenario(name="mpesa_paybill_landlord_collection",
        category=ScenarioCategory.OPERATIONAL,
        description="Month-start landlord paybill collection: 35 tenants",
        runner=run_mpesa_paybill_landlord_collection,
        severity=ScenarioSeverity.INFO,
        tags=["mpesa", "paybill", "rent"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Kenyan urban rent: 1st-5th of month M-Pesa paybill collections"),
    Scenario(name="swift_nostro_funding",
        category=ScenarioCategory.OPERATIONAL,
        description="NOSTRO replenishment via MT202 cover (small batch)",
        runner=run_swift_nostro_funding,
        severity=ScenarioSeverity.MEDIUM,
        tags=["swift", "nostro", "liquidity"],
        expected_event_types=["integration.swift.call"],
        realistic_basis="Daily NOSTRO funding to maintain correspondent balances"),
]

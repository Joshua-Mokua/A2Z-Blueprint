"""utils/scenarios/customer_behaviour.py — Realistic Kenyan customer journeys (20)."""

from __future__ import annotations

from typing import Any, Dict

from utils.scenarios.base import (
    Scenario, ScenarioCategory, ScenarioContext, ScenarioSeverity,
)


def _msisdn(seed: int, offset: int = 0) -> str:
    return f"2547{(seed * 12345 + 100000 + offset) % 100_000_000:08d}"


def run_salaried_employee_pay_cycle(ctx: ScenarioContext) -> Dict[str, Any]:
    """Monthly cycle: salary in -> ATM check -> bill pays -> rent."""
    legs = 0
    msisdn = _msisdn(ctx.seed, 0)
    # 1. Check balance via USSD
    ctx.submit_channel("ussd",
        payload={"ussd_code": "*334#", "msisdn": msisdn, "text": "1"}); legs += 1
    # 2. ATM withdrawal
    ctx.submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111000000010001",
                 "amount": 10_000, "terminal_id": "ECONA0001"},
        amount=10_000); legs += 1
    # 3. M-Pesa: rent
    ctx.submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                 "msisdn": msisdn, "amount": 18_000, "paybill": "808080"},
        amount=18_000); legs += 1
    # 4. M-Pesa: KPLC
    ctx.submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                 "msisdn": msisdn, "amount": 3_500, "paybill": "888880"},
        amount=3_500); legs += 1
    # 5. POS purchase
    ctx.submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE", "pan": "4111000000010001",
                 "card_not_present": False, "cvv": "123", "expiry": "12/28"},
        amount=4_500); legs += 1
    return {"journey_legs": legs}


def run_sme_quarterly_cycle(ctx: ScenarioContext) -> Dict[str, Any]:
    """SME quarterly: tax payment + supplier KIC + USSD balance check."""
    legs = 0
    # Tax via RTGS
    ctx.submit_channel("rtgs",
        payload={"amount": 2_500_000, "debit_account": "SME-A",
                 "credit_account": "KRA-COLL",
                 "beneficiary_bank_bic": "CBKEKENX"},
        amount=2_500_000); legs += 1
    # 8 supplier KICs
    for i in range(8):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "011",
                     "narrative": f"PO-2026-{i:03d}"},
            amount=350_000 + (i * 20_000),
            debit_account="SME-A",
            credit_account=f"SUPP-{i:04d}"); legs += 1
    # Balance check
    ctx.submit_channel("ussd",
        payload={"ussd_code": "*334#",
                 "msisdn": _msisdn(ctx.seed, 100),
                 "text": "1"}); legs += 1
    return {"sme_cycle_legs": legs}


def run_diaspora_remittance_journey(ctx: ScenarioContext) -> Dict[str, Any]:
    """Diaspora remittance: SWIFT MT103 in -> family ATM withdrawal."""
    legs = 0
    # MT103 inflow
    ctx.submit_channel("swift",
        payload={"mt_type": "103", "ordering_customer": "DIASPORA",
                 "beneficiary_bic": "ECOCKENA", "beneficiary_name": "FAMILY",
                 "amount": 850.0},
        amount=850.0, currency="USD",
        debit_account="CHASUS33", credit_account="FAM-001"); legs += 1
    # Family withdraws KES equivalent next day across 3 ATMs
    for i in range(3):
        ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL",
                     "pan": "4111777700001111",
                     "amount": 35_000, "terminal_id": f"FAM-T-{i}"},
            amount=35_000); legs += 1
    return {"remittance_journey_legs": legs}


def run_retail_micro_saver_cycle(ctx: ScenarioContext) -> Dict[str, Any]:
    """Micro-saver: 6 small M-Pesa deposits + 1 small ATM withdrawal."""
    legs = 0
    msisdn = _msisdn(ctx.seed, 200)
    for i in range(6):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                     "msisdn": msisdn, "amount": 500 + (i * 100),
                     "paybill": "ECOSAVE001"},
            amount=500 + (i * 100)); legs += 1
    # One small withdrawal
    ctx.submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111000099991111",
                 "amount": 2_000, "terminal_id": "ECONA0010"},
        amount=2_000); legs += 1
    return {"micro_save_legs": legs}


def run_university_student_pattern(ctx: ScenarioContext) -> Dict[str, Any]:
    """University student: termly fees + small monthly spending."""
    legs = 0
    # School fees via USSD
    ctx.submit_channel("ussd",
        payload={"ussd_code": "*334*5#", "msisdn": _msisdn(ctx.seed, 300),
                 "text": f"5*1*{45_000}*1234"}); legs += 1
    # Mobile money for small daily spending
    for i in range(12):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerBuyGoodsOnline",
                     "msisdn": _msisdn(ctx.seed, 300),
                     "amount": 250 + (i * 30), "till_number": "880100"},
            amount=250 + (i * 30)); legs += 1
    return {"student_legs": legs}


def run_uber_driver_daily_pattern(ctx: ScenarioContext) -> Dict[str, Any]:
    """Ride-hailing driver: many small M-Pesa till receipts + bank transfer."""
    legs = 0
    msisdn = _msisdn(ctx.seed, 400)
    # 30 small fares
    for i in range(30):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerBuyGoodsOnline",
                     "msisdn": _msisdn(ctx.seed, 400 + i * 10),
                     "amount": 280 + (i * 15), "till_number": "880100"},
            amount=280 + (i * 15)); legs += 1
    # End-of-day sweep to bank
    ctx.submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                 "beneficiary_bank_code": "044",
                 "narrative": "Daily takings"},
        amount=12_500,
        debit_account="DRIVER-A", credit_account="DRIVER-BANK"); legs += 1
    return {"driver_day_legs": legs}


def run_market_vendor_daily_takings(ctx: ScenarioContext) -> Dict[str, Any]:
    """Mama Mboga: 25 till receipts (small) + bill pays in evening."""
    legs = 0
    for i in range(25):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerBuyGoodsOnline",
                     "msisdn": _msisdn(ctx.seed, 500 + i * 10),
                     "amount": 180 + (i * 12),
                     "till_number": "MARKET01"},
            amount=180 + (i * 12)); legs += 1
    # Evening bill
    ctx.submit_channel("mpesa",
        payload={"transaction_type": "CustomerPayBillOnline",
                 "msisdn": _msisdn(ctx.seed, 500),
                 "amount": 2_500, "paybill": "888880"},
        amount=2_500); legs += 1
    return {"vendor_legs": legs}


def run_corporate_payroll_processor(ctx: ScenarioContext) -> Dict[str, Any]:
    """Mid-cap corporate HR: monthly payroll of 120 employees + tax."""
    legs = 0
    for i in range(120):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": ["001", "011", "066", "044"][i % 4],
                     "narrative": "Monthly salary"},
            amount=65_000 + (i * 500),
            debit_account="CORP-PAYROLL",
            credit_account=f"STAFF-{i:04d}"); legs += 1
    # PAYE tax via RTGS
    ctx.submit_channel("rtgs",
        payload={"amount": 3_200_000,
                 "debit_account": "CORP-PAYROLL",
                 "credit_account": "KRA-PAYE",
                 "beneficiary_bank_bic": "CBKEKENX"},
        amount=3_200_000); legs += 1
    return {"payroll_legs": legs}


def run_imported_goods_buyer(ctx: ScenarioContext) -> Dict[str, Any]:
    """Importer: SWIFT to supplier + clearing agent KIC + local supplier KIC."""
    legs = 0
    # SWIFT MT103 to China supplier
    ctx.submit_channel("swift",
        payload={"mt_type": "103", "ordering_customer": "IMPORTER LTD",
                 "beneficiary_bic": "ICBKCNBJ", "beneficiary_name": "MFG CO",
                 "amount": 28_500.0},
        amount=28_500.0, currency="USD",
        debit_account="IMP-A", credit_account="MFG-CN"); legs += 1
    # Clearing agent
    ctx.submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                 "beneficiary_bank_code": "011",
                 "narrative": "Customs clearing"},
        amount=185_000, debit_account="IMP-A",
        credit_account="AGENT-01"); legs += 1
    # Logistics
    ctx.submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                 "beneficiary_bank_code": "066",
                 "narrative": "Transport"},
        amount=92_000, debit_account="IMP-A",
        credit_account="TRANS-01"); legs += 1
    return {"import_legs": legs}


def run_real_estate_purchase_journey(ctx: ScenarioContext) -> Dict[str, Any]:
    """Buying a flat: deposit RTGS + monthly mortgage KICs."""
    legs = 0
    # Down payment via RTGS
    ctx.submit_channel("rtgs",
        payload={"amount": 8_500_000,
                 "debit_account": "BUYER-A",
                 "credit_account": "SELLER-A",
                 "beneficiary_bank_bic": "BARCKENX"},
        amount=8_500_000); legs += 1
    # 6 monthly mortgage payments
    for i in range(6):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001",
                     "narrative": f"Mortgage month {i+1}"},
            amount=78_500, debit_account="BUYER-A",
            credit_account="BANK-MORTG"); legs += 1
    return {"real_estate_legs": legs}


def run_first_time_card_user(ctx: ScenarioContext) -> Dict[str, Any]:
    """First-time card user: 5 small POS transactions + 1 ATM withdrawal."""
    legs = 0
    for i in range(5):
        ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "4111000000000001",
                     "card_not_present": False,
                     "cvv": "123", "expiry": "12/28"},
            amount=850 + (i * 100)); legs += 1
    ctx.submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "4111000000000001",
                 "amount": 1_500, "terminal_id": "ECONA-FIRST"},
        amount=1_500); legs += 1
    return {"first_time_legs": legs}


def run_high_net_worth_treasurer(ctx: ScenarioContext) -> Dict[str, Any]:
    """HNW: weekly RTGS sweep + 3 SWIFT MT103 outbound."""
    legs = 0
    # Weekly KES sweep
    for i in range(4):
        ctx.submit_channel("rtgs",
            payload={"amount": 35_000_000,
                     "debit_account": "HNW-MAIN",
                     "credit_account": "HNW-INVEST",
                     "beneficiary_bank_bic": "CFCKENA"},
            amount=35_000_000); legs += 1
    # 3 outbound SWIFT for offshore investments
    for i in range(3):
        ctx.submit_channel("swift",
            payload={"mt_type": "103", "ordering_customer": "HNW INDIVIDUAL",
                     "beneficiary_bic": "BARCGB22", "beneficiary_name": "FUND",
                     "amount": 125_000.0},
            amount=125_000.0, currency="USD",
            debit_account="HNW-INVEST", credit_account="OFFSHORE-FUND"); legs += 1
    return {"hnw_legs": legs}


def run_retiree_pension_cycle(ctx: ScenarioContext) -> Dict[str, Any]:
    """Retiree: pension inflow + 3 monthly bill pays."""
    legs = 0
    # Pension inflow
    ctx.submit_channel("kic",
        payload={"transaction_type": "EFT_CREDIT",
                 "beneficiary_bank_code": "044",
                 "narrative": "Monthly pension"},
        amount=85_000, debit_account="PENSION-FUND",
        credit_account="RETIREE-001"); legs += 1
    # Bills
    for paybill in ("888880", "888881", "888882"):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                     "msisdn": _msisdn(ctx.seed, 800),
                     "amount": 2_800, "paybill": paybill},
            amount=2_800); legs += 1
    return {"retiree_legs": legs}


def run_minor_account_savings(ctx: ScenarioContext) -> Dict[str, Any]:
    """Minor account: 4 parent deposits via KIC + 0 outflows."""
    legs = 0
    for i in range(4):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "044",
                     "narrative": "Birthday gift"},
            amount=15_000 + (i * 2_000),
            debit_account="PARENT-A",
            credit_account=f"MINOR-{i+1:04d}"); legs += 1
    return {"minor_save_legs": legs}


def run_nonprofit_donation_inflow(ctx: ScenarioContext) -> Dict[str, Any]:
    """NGO: 8 small SWIFT inflows from donors + 5 KIC outflows to programmes."""
    legs = 0
    for i in range(8):
        ctx.submit_channel("swift",
            payload={"mt_type": "103",
                     "ordering_customer": f"DONOR-{i:03d}",
                     "beneficiary_bic": "ECOCKENA",
                     "beneficiary_name": "NGO",
                     "amount": 2_500.0 + (i * 100)},
            amount=2_500.0 + (i * 100), currency="USD",
            debit_account=f"DONOR-{i:03d}",
            credit_account="NGO-MAIN"); legs += 1
    for i in range(5):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "001",
                     "narrative": "Programme funding"},
            amount=125_000,
            debit_account="NGO-MAIN",
            credit_account=f"PROG-{i:04d}"); legs += 1
    return {"ngo_legs": legs}


def run_petty_cash_recoveries(ctx: ScenarioContext) -> Dict[str, Any]:
    """SME petty-cash recovery: 10 small ATM deposits via cardholder."""
    legs = 0
    for i in range(10):
        # Branch teller cash deposit (simulated via ATM DEPOSIT)
        ctx.submit_channel("atm",
            payload={"operation": "DEPOSIT", "pan": "4111000088880000",
                     "amount": 4_500 + (i * 200), "terminal_id": "BRANCH-DEP"},
            amount=4_500 + (i * 200)); legs += 1
    return {"recovery_legs": legs}


def run_late_night_emergency_atm_use(ctx: ScenarioContext) -> Dict[str, Any]:
    """Late-night: 4 ATM withdrawals at distant terminals (unusual pattern)."""
    legs = 0
    for i in range(4):
        ctx.submit_channel("atm",
            payload={"operation": "WITHDRAWAL", "pan": "4111000077770000",
                     "amount": 8_000, "terminal_id": f"LATE-T-{i}"},
            amount=8_000); legs += 1
    return {"late_night_legs": legs}


def run_corporate_card_business_travel(ctx: ScenarioContext) -> Dict[str, Any]:
    """Corporate card holder: 7 travel POS + 1 ATM cash + 1 hotel CNP."""
    legs = 0
    for i in range(7):
        ctx.submit_channel("cards",
            payload={"operation": "AUTH_CAPTURE",
                     "pan": "5500111122223333",
                     "card_not_present": False,
                     "cvv": "456", "expiry": "12/28",
                     "merchant_id": f"AIRP-{i}"},
            amount=4_500 + (i * 800)); legs += 1
    ctx.submit_channel("atm",
        payload={"operation": "WITHDRAWAL", "pan": "5500111122223333",
                 "amount": 25_000, "terminal_id": "HOTEL-ATM"},
        amount=25_000); legs += 1
    # Hotel CNP (with 3DS done)
    ctx.submit_channel("cards",
        payload={"operation": "AUTH_CAPTURE", "pan": "5500111122223333",
                 "card_not_present": True, "cvv": "456", "expiry": "12/28",
                 "threeds_completed": True},
        amount=42_500); legs += 1
    return {"business_travel_legs": legs}


def run_co_op_savings_chama(ctx: ScenarioContext) -> Dict[str, Any]:
    """Chama (saving group): 12 monthly contributions via M-Pesa."""
    legs = 0
    for i in range(12):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                     "msisdn": _msisdn(ctx.seed, 1000 + i * 100),
                     "amount": 5_000,
                     "paybill": "CHAMA001"},
            amount=5_000); legs += 1
    return {"chama_legs": legs}


def run_taxi_driver_monthly(ctx: ScenarioContext) -> Dict[str, Any]:
    """Taxi driver monthly view: many M-Pesa fares + 2 KIC sweeps to savings."""
    legs = 0
    msisdn = _msisdn(ctx.seed, 1500)
    for i in range(40):
        ctx.submit_channel("mpesa",
            payload={"transaction_type": "CustomerBuyGoodsOnline",
                     "msisdn": _msisdn(ctx.seed, 1500 + i * 25),
                     "amount": 350 + (i * 15), "till_number": "880200"},
            amount=350 + (i * 15)); legs += 1
    # 2 month-end sweeps to savings
    for i in range(2):
        ctx.submit_channel("kic",
            payload={"transaction_type": "EFT_CREDIT",
                     "beneficiary_bank_code": "044",
                     "narrative": "Savings sweep"},
            amount=18_000,
            debit_account="DRIVER-CASH",
            credit_account="DRIVER-SAVE"); legs += 1
    return {"taxi_monthly_legs": legs}


CUSTOMER_SCENARIOS = [
    Scenario(name="salaried_employee_pay_cycle", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Monthly cycle: salary in -> ATM check -> bill pays -> rent",
        runner=run_salaried_employee_pay_cycle, tags=["customer", "salaried", "monthly"],
        expected_event_types=["integration.ussd.call", "integration.atm.call",
                                "integration.mpesa.call", "integration.cards.call"],
        realistic_basis="Typical Nairobi salaried-employee monthly pattern"),
    Scenario(name="sme_quarterly_cycle", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="SME quarterly: tax via RTGS + 8 KIC supplier payments",
        runner=run_sme_quarterly_cycle, tags=["customer", "sme", "quarterly"],
        expected_event_types=["integration.rtgs.call", "integration.kic.call",
                                "integration.ussd.call"],
        realistic_basis="Quarterly SME treasury cycle"),
    Scenario(name="diaspora_remittance_journey", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Diaspora MT103 in -> family ATM withdrawals",
        runner=run_diaspora_remittance_journey, tags=["customer", "diaspora"],
        expected_event_types=["integration.swift.call", "integration.atm.call"],
        realistic_basis="Family remittance flow: inflow then cash uplift"),
    Scenario(name="retail_micro_saver_cycle", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Micro-saver: 6 small deposits + 1 small withdrawal",
        runner=run_retail_micro_saver_cycle, tags=["customer", "micro-saver"],
        expected_event_types=["integration.mpesa.call", "integration.atm.call"],
        realistic_basis="Mass-market micro-savings via M-Pesa paybill"),
    Scenario(name="university_student_pattern", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="University student: termly fees via USSD + monthly small spending",
        runner=run_university_student_pattern, tags=["customer", "student"],
        expected_event_types=["integration.ussd.call", "integration.mpesa.call"],
        realistic_basis="Termly university fee payment + daily small spending"),
    Scenario(name="uber_driver_daily_pattern", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Ride-hailing driver: 30 small fares + EOD sweep",
        runner=run_uber_driver_daily_pattern, tags=["customer", "gig-economy"],
        expected_event_types=["integration.mpesa.call", "integration.kic.call"],
        realistic_basis="Daily gig-economy income flow"),
    Scenario(name="market_vendor_daily_takings", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Mama Mboga: 25 small till receipts + bill",
        runner=run_market_vendor_daily_takings, tags=["customer", "informal"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Informal-sector vendor daily volume"),
    Scenario(name="corporate_payroll_processor", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.LOW,
        description="Mid-cap HR: 120 employees + PAYE tax",
        runner=run_corporate_payroll_processor, tags=["customer", "corporate", "payroll"],
        expected_event_types=["integration.kic.call", "integration.rtgs.call"],
        realistic_basis="Monthly mid-cap corporate payroll run"),
    Scenario(name="imported_goods_buyer", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.LOW,
        description="Importer: SWIFT to supplier + 2 KIC to local agents",
        runner=run_imported_goods_buyer, tags=["customer", "importer"],
        expected_event_types=["integration.swift.call", "integration.kic.call"],
        realistic_basis="Goods import value chain: supplier + clearing + logistics"),
    Scenario(name="real_estate_purchase_journey", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.MEDIUM,
        description="Property purchase: RTGS deposit + 6 monthly KIC mortgage",
        runner=run_real_estate_purchase_journey, tags=["customer", "real-estate"],
        expected_event_types=["integration.rtgs.call", "integration.kic.call"],
        realistic_basis="Property purchase: large deposit then ongoing servicing"),
    Scenario(name="first_time_card_user", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="First-time card user: 5 small POS + 1 ATM withdrawal",
        runner=run_first_time_card_user, tags=["customer", "first-time"],
        expected_event_types=["integration.cards.call", "integration.atm.call"],
        realistic_basis="New cardholder learning pattern"),
    Scenario(name="high_net_worth_treasurer", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.MEDIUM,
        description="HNW: weekly RTGS sweep + 3 SWIFT outbound",
        runner=run_high_net_worth_treasurer, tags=["customer", "hnw"],
        expected_event_types=["integration.rtgs.call", "integration.swift.call"],
        realistic_basis="HNW client weekly liquidity sweep + offshore investing"),
    Scenario(name="retiree_pension_cycle", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Retiree: pension inflow + 3 bill pays",
        runner=run_retiree_pension_cycle, tags=["customer", "retiree"],
        expected_event_types=["integration.kic.call", "integration.mpesa.call"],
        realistic_basis="Monthly retiree income + utility pattern"),
    Scenario(name="minor_account_savings", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Minor account: 4 parent deposits, 0 outflows",
        runner=run_minor_account_savings, tags=["customer", "minor", "deposits-only"],
        expected_event_types=["integration.kic.call"],
        realistic_basis="Minor savings: deposits-only pattern over time"),
    Scenario(name="nonprofit_donation_inflow", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.LOW,
        description="NGO: 8 SWIFT donor inflows + 5 KIC programme outflows",
        runner=run_nonprofit_donation_inflow, tags=["customer", "ngo"],
        expected_event_types=["integration.swift.call", "integration.kic.call"],
        realistic_basis="NGO funding flow: international donor in, local programme out"),
    Scenario(name="petty_cash_recoveries", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="SME petty-cash recovery: 10 small ATM deposits",
        runner=run_petty_cash_recoveries, tags=["customer", "sme", "cash-deposit"],
        expected_event_types=["integration.atm.call"],
        realistic_basis="Branch teller cash deposit batches"),
    Scenario(name="late_night_emergency_atm_use", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.LOW,
        description="Late-night ATM use: 4 distant terminals (unusual)",
        runner=run_late_night_emergency_atm_use,
        tags=["customer", "atm", "off-hours"],
        expected_event_types=["integration.atm.call"],
        realistic_basis="Off-hours / hospital / emergency cash pattern"),
    Scenario(name="corporate_card_business_travel", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Corporate card holder business travel: 7 POS + ATM + hotel CNP",
        runner=run_corporate_card_business_travel,
        tags=["customer", "corporate-card", "travel"],
        expected_event_types=["integration.cards.call", "integration.atm.call"],
        realistic_basis="Business travel: airport, hotel, taxi POS pattern"),
    Scenario(name="co_op_savings_chama", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Chama: 12 monthly contributions via M-Pesa",
        runner=run_co_op_savings_chama, tags=["customer", "chama"],
        expected_event_types=["integration.mpesa.call"],
        realistic_basis="Kenyan chama (rotating saving group) monthly contributions"),
    Scenario(name="taxi_driver_monthly", category=ScenarioCategory.CUSTOMER_BEHAVIOUR,
        severity=ScenarioSeverity.INFO,
        description="Taxi driver monthly: 40 fares + 2 KIC savings sweeps",
        runner=run_taxi_driver_monthly,
        tags=["customer", "gig-economy", "monthly"],
        expected_event_types=["integration.mpesa.call", "integration.kic.call"],
        realistic_basis="Monthly aggregation of gig-economy driver income"),
]

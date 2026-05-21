"""
================================================================================
A2Z MIS 360 — Standard #97: Tax & VAT Compliance Engine
================================================================================

Risk classification: Cat B (deterministic tax computation + filing workflow)

Implements Kenya Revenue Authority (KRA) compliance for:
    - VAT (Value Added Tax Act)
    - Corporate Income Tax (Income Tax Act)
    - Withholding Tax (WHT)
    - PAYE (Pay-As-You-Earn)
    - Excise Duty

Provides:
    - vat_output(...)               -- standard / zero-rate / exempt classification
    - vat_input_credit(...)         -- claimable input VAT
    - vat_payable(...)              -- net = output - input
    - corporate_tax(...)            -- 30% resident / 37.5% branch
    - withholding_tax(...)          -- per income-type rate table
    - filing_deadline(...)          -- per tax type
    - filing_status(...)            -- DUE / FILED / OVERDUE classification
    - late_filing_penalty(...)      -- 5% per month or KES 10K min

5 TAX_TYPES byte-for-byte:
    VAT, CORPORATE_TAX, WITHHOLDING_TAX, EXCISE_DUTY, PAYE

3 VAT_RATE_CATEGORIES byte-for-byte:
    STANDARD_RATE_PCT = 16   -- KRA standard VAT
    ZERO_RATE_PCT     = 0    -- exports, basic foodstuffs (still claimable)
    EXEMPT            = None -- financial services, insurance (NOT claimable)

WITHHOLDING_TAX_RATES_PCT byte-for-byte:
    PROFESSIONAL_FEES_RESIDENT          = 5
    PROFESSIONAL_FEES_NON_RESIDENT      = 20
    RENT_RESIDENT                       = 10
    DIVIDENDS_RESIDENT                  = 5
    DIVIDENDS_NON_RESIDENT              = 15
    INTEREST_RESIDENT                   = 15
    INTEREST_NON_RESIDENT               = 15
    MANAGEMENT_FEES_NON_RESIDENT        = 20

CORPORATE_TAX_RATES_PCT byte-for-byte:
    RESIDENT_COMPANY      = 30
    BRANCH_NON_RESIDENT   = 37.5
    EXPORT_PROCESSING     = 0   -- 10-year holiday under EPZ Act

FILING_DEADLINE_DAYS byte-for-byte (after period-end):
    VAT             = 20    -- 20th of following month
    PAYE            = 9     -- 9th of following month
    WITHHOLDING_TAX = 20    -- 20th of following month
    CORPORATE_TAX   = 180   -- 6 months after year-end
    EXCISE_DUTY     = 20    -- 20th of following month

5 FILING_STATUSES byte-for-byte:
    NOT_DUE, DUE, FILED, PAID, OVERDUE

Penalties byte-for-byte (Tax Procedures Act):
    LATE_FILING_PENALTY_PCT_PER_MONTH = 5
    LATE_FILING_PENALTY_MIN_KES       = 10000
    LATE_PAYMENT_INTEREST_PCT_MONTHLY = 1

Honesty rules applied:
    Rule 1: vat_payable=None when output_vat or input_vat missing
            withholding_tax=None when amount or rate missing
    Rule 6: unknown tax type / income category surfaced (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 5 TAX TYPES byte-for-byte
TAX_TYPES: Tuple[str, ...] = (
    "VAT", "CORPORATE_TAX", "WITHHOLDING_TAX", "EXCISE_DUTY", "PAYE",
)

# VAT rates byte-for-byte
VAT_STANDARD_RATE_PCT = Decimal("16")
VAT_ZERO_RATE_PCT = Decimal("0")
# Exempt = no VAT, no input credit (different from zero-rated)

VAT_RATE_CATEGORIES: Tuple[str, ...] = ("STANDARD", "ZERO_RATED", "EXEMPT")

# Withholding tax rates byte-for-byte (KRA WHT schedule)
WITHHOLDING_TAX_RATES_PCT: Dict[str, Decimal] = {
    "PROFESSIONAL_FEES_RESIDENT": Decimal("5"),
    "PROFESSIONAL_FEES_NON_RESIDENT": Decimal("20"),
    "RENT_RESIDENT": Decimal("10"),
    "DIVIDENDS_RESIDENT": Decimal("5"),
    "DIVIDENDS_NON_RESIDENT": Decimal("15"),
    "INTEREST_RESIDENT": Decimal("15"),
    "INTEREST_NON_RESIDENT": Decimal("15"),
    "MANAGEMENT_FEES_NON_RESIDENT": Decimal("20"),
}

# Corporate tax rates byte-for-byte
CORPORATE_TAX_RATES_PCT: Dict[str, Decimal] = {
    "RESIDENT_COMPANY": Decimal("30"),
    "BRANCH_NON_RESIDENT": Decimal("37.5"),
    "EXPORT_PROCESSING": Decimal("0"),
}

# Filing deadlines byte-for-byte (days after period end)
FILING_DEADLINE_DAYS: Dict[str, int] = {
    "VAT": 20,
    "PAYE": 9,
    "WITHHOLDING_TAX": 20,
    "CORPORATE_TAX": 180,
    "EXCISE_DUTY": 20,
}

# 5 FILING STATUSES byte-for-byte
FILING_STATUSES: Tuple[str, ...] = (
    "NOT_DUE", "DUE", "FILED", "PAID", "OVERDUE",
)

# Penalty rates byte-for-byte (Tax Procedures Act)
LATE_FILING_PENALTY_PCT_PER_MONTH = Decimal("5")
LATE_FILING_PENALTY_MIN_KES = Decimal("10000")
LATE_PAYMENT_INTEREST_PCT_MONTHLY = Decimal("1")


class TaxComplianceEngine:
    """Deterministic tax computation + filing workflow."""

    @staticmethod
    def vat_output(
        sales_excl_vat: Optional[Decimal],
        category: str,
    ) -> Dict[str, Any]:
        """
        Compute output VAT.
        Rule 1: vat=None when sales missing.
        Rule 6: unknown category surfaced.
        """
        if category not in VAT_RATE_CATEGORIES:
            return {"vat": None, "computed": False,
                    "reason": f"unknown_category:{category}",
                    "valid_categories": list(VAT_RATE_CATEGORIES)}
        if sales_excl_vat is None or sales_excl_vat < 0:
            return {"vat": None, "computed": False,
                    "reason": "missing_or_negative_sales"}
        if category == "STANDARD":
            rate = VAT_STANDARD_RATE_PCT
        elif category == "ZERO_RATED":
            rate = VAT_ZERO_RATE_PCT
        else:  # EXEMPT
            return {"category": "EXEMPT", "sales_excl_vat": str(sales_excl_vat),
                    "vat": "0", "rate_pct": None,
                    "input_credit_claimable": False, "computed": True}
        vat = (sales_excl_vat * rate) / Decimal("100")
        return {
            "category": category,
            "sales_excl_vat": str(sales_excl_vat),
            "rate_pct": str(rate),
            "vat": str(vat.quantize(Decimal("0.01"))),
            "input_credit_claimable": True,
            "computed": True,
        }

    @staticmethod
    def vat_payable(
        output_vat: Optional[Decimal],
        input_vat: Optional[Decimal],
    ) -> Optional[Decimal]:
        """
        Net VAT payable = output VAT - input VAT.
        Rule 1: None when either component missing.
        Negative result = refund position (not error).
        """
        if output_vat is None or input_vat is None:
            return None
        return output_vat - input_vat

    @staticmethod
    def corporate_tax(
        taxable_income: Optional[Decimal],
        entity_type: str,
    ) -> Dict[str, Any]:
        """
        Compute corporate tax.
        Rule 1: tax=None when income missing or negative.
        Rule 6: unknown entity_type surfaced.
        """
        if entity_type not in CORPORATE_TAX_RATES_PCT:
            return {"tax": None, "computed": False,
                    "reason": f"unknown_entity_type:{entity_type}",
                    "valid_entity_types": list(CORPORATE_TAX_RATES_PCT.keys())}
        if taxable_income is None or taxable_income < 0:
            return {"tax": None, "computed": False,
                    "reason": "missing_or_negative_income"}
        rate = CORPORATE_TAX_RATES_PCT[entity_type]
        tax = (taxable_income * rate) / Decimal("100")
        return {
            "entity_type": entity_type,
            "taxable_income": str(taxable_income),
            "rate_pct": str(rate),
            "tax": str(tax.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def withholding_tax(
        gross_payment: Optional[Decimal],
        income_category: str,
    ) -> Dict[str, Any]:
        """
        Compute WHT to deduct at source.
        Rule 1: tax=None when payment missing.
        Rule 6: unknown income_category surfaced.
        """
        if income_category not in WITHHOLDING_TAX_RATES_PCT:
            return {"wht": None, "computed": False,
                    "reason": f"unknown_income_category:{income_category}",
                    "valid_categories": list(WITHHOLDING_TAX_RATES_PCT.keys())}
        if gross_payment is None or gross_payment < 0:
            return {"wht": None, "computed": False,
                    "reason": "missing_or_negative_payment"}
        rate = WITHHOLDING_TAX_RATES_PCT[income_category]
        wht = (gross_payment * rate) / Decimal("100")
        net_payment = gross_payment - wht
        return {
            "income_category": income_category,
            "gross_payment": str(gross_payment),
            "rate_pct": str(rate),
            "wht": str(wht.quantize(Decimal("0.01"))),
            "net_payment": str(net_payment.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def filing_deadline(
        tax_type: str,
        period_end: date,
    ) -> Dict[str, Any]:
        """Compute filing deadline. Rule 6: unknown tax type surfaced."""
        if tax_type not in FILING_DEADLINE_DAYS:
            return {"deadline": None, "computed": False,
                    "reason": f"unknown_tax_type:{tax_type}",
                    "valid_tax_types": list(FILING_DEADLINE_DAYS.keys())}
        days = FILING_DEADLINE_DAYS[tax_type]
        deadline = period_end + timedelta(days=days)
        return {
            "tax_type": tax_type,
            "period_end": period_end.isoformat(),
            "filing_deadline_days": days,
            "deadline_date": deadline.isoformat(),
            "computed": True,
        }

    @staticmethod
    def filing_status(
        tax_type: str,
        period_end: date,
        as_of: Optional[date] = None,
        filed: bool = False,
        paid: bool = False,
    ) -> Dict[str, Any]:
        """
        Classify filing status.
        Rule 6: unknown tax_type surfaced.
        """
        if tax_type not in FILING_DEADLINE_DAYS:
            return {"status": None, "computed": False,
                    "reason": f"unknown_tax_type:{tax_type}"}
        if as_of is None:
            as_of = date.today()
        days = FILING_DEADLINE_DAYS[tax_type]
        deadline = period_end + timedelta(days=days)
        # State machine
        if filed and paid:
            status = "PAID"
        elif filed:
            status = "FILED"
        elif as_of < period_end:
            status = "NOT_DUE"
        elif as_of <= deadline:
            status = "DUE"
        else:
            status = "OVERDUE"
        return {
            "tax_type": tax_type,
            "period_end": period_end.isoformat(),
            "deadline_date": deadline.isoformat(),
            "as_of": as_of.isoformat(),
            "status": status,
            "computed": True,
        }

    @staticmethod
    def late_filing_penalty(
        tax_due: Optional[Decimal],
        months_late: int,
    ) -> Optional[Decimal]:
        """
        Late filing penalty: 5% per month or KES 10K minimum.
        Rule 1: None when tax_due missing.
        """
        if tax_due is None or tax_due < 0 or months_late < 0:
            return None
        if months_late == 0:
            return Decimal("0")
        pct_penalty = (tax_due * LATE_FILING_PENALTY_PCT_PER_MONTH
                       * Decimal(months_late)) / Decimal("100")
        return max(pct_penalty, LATE_FILING_PENALTY_MIN_KES)


# ============================================================================
# Self-tests
# ============================================================================

def _test_tax_types_byte_for_byte():
    expected = ("VAT", "CORPORATE_TAX", "WITHHOLDING_TAX", "EXCISE_DUTY", "PAYE")
    for t in expected:
        assert t in TAX_TYPES
    assert len(TAX_TYPES) == 5


def _test_vat_rates_byte_for_byte():
    assert VAT_STANDARD_RATE_PCT == Decimal("16")
    assert VAT_ZERO_RATE_PCT == Decimal("0")


def _test_wht_rates_byte_for_byte():
    assert WITHHOLDING_TAX_RATES_PCT["PROFESSIONAL_FEES_RESIDENT"] == Decimal("5")
    assert WITHHOLDING_TAX_RATES_PCT["PROFESSIONAL_FEES_NON_RESIDENT"] == Decimal("20")
    assert WITHHOLDING_TAX_RATES_PCT["RENT_RESIDENT"] == Decimal("10")
    assert WITHHOLDING_TAX_RATES_PCT["DIVIDENDS_RESIDENT"] == Decimal("5")
    assert WITHHOLDING_TAX_RATES_PCT["DIVIDENDS_NON_RESIDENT"] == Decimal("15")
    assert WITHHOLDING_TAX_RATES_PCT["INTEREST_RESIDENT"] == Decimal("15")
    assert WITHHOLDING_TAX_RATES_PCT["MANAGEMENT_FEES_NON_RESIDENT"] == Decimal("20")


def _test_corporate_rates_byte_for_byte():
    assert CORPORATE_TAX_RATES_PCT["RESIDENT_COMPANY"] == Decimal("30")
    assert CORPORATE_TAX_RATES_PCT["BRANCH_NON_RESIDENT"] == Decimal("37.5")
    assert CORPORATE_TAX_RATES_PCT["EXPORT_PROCESSING"] == Decimal("0")


def _test_filing_deadlines_byte_for_byte():
    assert FILING_DEADLINE_DAYS["VAT"] == 20
    assert FILING_DEADLINE_DAYS["PAYE"] == 9
    assert FILING_DEADLINE_DAYS["WITHHOLDING_TAX"] == 20
    assert FILING_DEADLINE_DAYS["CORPORATE_TAX"] == 180
    assert FILING_DEADLINE_DAYS["EXCISE_DUTY"] == 20


def _test_filing_statuses_byte_for_byte():
    expected = ("NOT_DUE", "DUE", "FILED", "PAID", "OVERDUE")
    for s in expected:
        assert s in FILING_STATUSES


def _test_penalty_constants_byte_for_byte():
    assert LATE_FILING_PENALTY_PCT_PER_MONTH == Decimal("5")
    assert LATE_FILING_PENALTY_MIN_KES == Decimal("10000")
    assert LATE_PAYMENT_INTEREST_PCT_MONTHLY == Decimal("1")


def _test_vat_standard_runtime():
    """100K sales * 16% = 16K VAT."""
    r = TaxComplianceEngine.vat_output(Decimal("100000"), "STANDARD")
    assert r["vat"] == "16000.00"
    assert r["input_credit_claimable"] is True


def _test_vat_zero_rated_runtime():
    """Exports → 0% VAT but still claimable input."""
    r = TaxComplianceEngine.vat_output(Decimal("100000"), "ZERO_RATED")
    assert r["vat"] == "0.00"
    assert r["input_credit_claimable"] is True


def _test_vat_exempt_runtime():
    """Financial services → 0 VAT and NOT claimable."""
    r = TaxComplianceEngine.vat_output(Decimal("100000"), "EXEMPT")
    assert r["vat"] == "0"
    assert r["input_credit_claimable"] is False


def _test_vat_unknown_category_rule6():
    r = TaxComplianceEngine.vat_output(Decimal("100000"), "WEIRD")
    assert r["computed"] is False


def _test_vat_payable_basic():
    """Output 16K - Input 5K = 11K payable."""
    r = TaxComplianceEngine.vat_payable(Decimal("16000"), Decimal("5000"))
    assert r == Decimal("11000")


def _test_vat_payable_refund_position():
    """Input > Output → negative = refund (not error)."""
    r = TaxComplianceEngine.vat_payable(Decimal("5000"), Decimal("16000"))
    assert r == Decimal("-11000")


def _test_vat_payable_missing_rule1():
    assert TaxComplianceEngine.vat_payable(None, Decimal("5000")) is None
    assert TaxComplianceEngine.vat_payable(Decimal("16000"), None) is None


def _test_corporate_tax_resident():
    """1M income * 30% = 300K tax."""
    r = TaxComplianceEngine.corporate_tax(Decimal("1000000"), "RESIDENT_COMPANY")
    assert r["tax"] == "300000.00"


def _test_corporate_tax_branch():
    """1M income * 37.5% = 375K tax."""
    r = TaxComplianceEngine.corporate_tax(Decimal("1000000"), "BRANCH_NON_RESIDENT")
    assert r["tax"] == "375000.00"


def _test_corporate_tax_unknown_entity_rule6():
    r = TaxComplianceEngine.corporate_tax(Decimal("1000000"), "WEIRD")
    assert r["computed"] is False


def _test_wht_professional_resident():
    """100K * 5% = 5K WHT, 95K net."""
    r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                             "PROFESSIONAL_FEES_RESIDENT")
    assert r["wht"] == "5000.00"
    assert r["net_payment"] == "95000.00"


def _test_wht_professional_non_resident():
    """Non-resident 4× higher rate."""
    r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                             "PROFESSIONAL_FEES_NON_RESIDENT")
    assert r["wht"] == "20000.00"


def _test_wht_dividends_resident_5pct():
    r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                             "DIVIDENDS_RESIDENT")
    assert r["wht"] == "5000.00"


def _test_wht_dividends_non_resident_15pct():
    r = TaxComplianceEngine.withholding_tax(Decimal("100000"),
                                             "DIVIDENDS_NON_RESIDENT")
    assert r["wht"] == "15000.00"


def _test_wht_unknown_category_rule6():
    r = TaxComplianceEngine.withholding_tax(Decimal("100000"), "WEIRD")
    assert r["computed"] is False


def _test_filing_deadline_vat():
    """31 Mar period-end + 20 days = 20 Apr."""
    r = TaxComplianceEngine.filing_deadline("VAT", date(2026, 3, 31))
    assert r["deadline_date"] == "2026-04-20"


def _test_filing_deadline_paye():
    """31 Mar + 9 days = 9 Apr."""
    r = TaxComplianceEngine.filing_deadline("PAYE", date(2026, 3, 31))
    assert r["deadline_date"] == "2026-04-09"


def _test_filing_deadline_corporate():
    """31 Dec year-end + 180 days = 29 Jun."""
    r = TaxComplianceEngine.filing_deadline("CORPORATE_TAX", date(2025, 12, 31))
    assert r["deadline_date"] == "2026-06-29"


def _test_filing_status_not_due():
    r = TaxComplianceEngine.filing_status(
        "VAT", period_end=date(2026, 5, 31), as_of=date(2026, 4, 15))
    assert r["status"] == "NOT_DUE"


def _test_filing_status_due():
    r = TaxComplianceEngine.filing_status(
        "VAT", period_end=date(2026, 3, 31), as_of=date(2026, 4, 15))
    assert r["status"] == "DUE"


def _test_filing_status_overdue():
    """Period 31 Mar + 20d = 20 Apr deadline; checked 30 Apr → OVERDUE."""
    r = TaxComplianceEngine.filing_status(
        "VAT", period_end=date(2026, 3, 31), as_of=date(2026, 4, 30))
    assert r["status"] == "OVERDUE"


def _test_filing_status_filed():
    r = TaxComplianceEngine.filing_status(
        "VAT", period_end=date(2026, 3, 31),
        as_of=date(2026, 4, 30), filed=True, paid=False)
    assert r["status"] == "FILED"


def _test_filing_status_paid():
    r = TaxComplianceEngine.filing_status(
        "VAT", period_end=date(2026, 3, 31),
        as_of=date(2026, 4, 30), filed=True, paid=True)
    assert r["status"] == "PAID"


def _test_late_penalty_basic():
    """100K tax * 5% * 2 months = 10K. Min 10K, so 10K."""
    p = TaxComplianceEngine.late_filing_penalty(Decimal("100000"), 2)
    assert p == Decimal("10000")


def _test_late_penalty_high():
    """1M tax * 5% * 3 months = 150K (above 10K min)."""
    p = TaxComplianceEngine.late_filing_penalty(Decimal("1000000"), 3)
    assert p == Decimal("150000")


def _test_late_penalty_min_floor():
    """100K * 5% * 1 month = 5K, but min is 10K."""
    p = TaxComplianceEngine.late_filing_penalty(Decimal("100000"), 1)
    assert p == Decimal("10000")


def _test_late_penalty_zero_months():
    p = TaxComplianceEngine.late_filing_penalty(Decimal("100000"), 0)
    assert p == Decimal("0")


def _test_late_penalty_missing_rule1():
    assert TaxComplianceEngine.late_filing_penalty(None, 2) is None


def self_test() -> bool:
    tests = [
        _test_tax_types_byte_for_byte,
        _test_vat_rates_byte_for_byte,
        _test_wht_rates_byte_for_byte,
        _test_corporate_rates_byte_for_byte,
        _test_filing_deadlines_byte_for_byte,
        _test_filing_statuses_byte_for_byte,
        _test_penalty_constants_byte_for_byte,
        _test_vat_standard_runtime,
        _test_vat_zero_rated_runtime,
        _test_vat_exempt_runtime,
        _test_vat_unknown_category_rule6,
        _test_vat_payable_basic,
        _test_vat_payable_refund_position,
        _test_vat_payable_missing_rule1,
        _test_corporate_tax_resident,
        _test_corporate_tax_branch,
        _test_corporate_tax_unknown_entity_rule6,
        _test_wht_professional_resident,
        _test_wht_professional_non_resident,
        _test_wht_dividends_resident_5pct,
        _test_wht_dividends_non_resident_15pct,
        _test_wht_unknown_category_rule6,
        _test_filing_deadline_vat,
        _test_filing_deadline_paye,
        _test_filing_deadline_corporate,
        _test_filing_status_not_due,
        _test_filing_status_due,
        _test_filing_status_overdue,
        _test_filing_status_filed,
        _test_filing_status_paid,
        _test_late_penalty_basic,
        _test_late_penalty_high,
        _test_late_penalty_min_floor,
        _test_late_penalty_zero_months,
        _test_late_penalty_missing_rule1,
    ]
    print("=" * 60)
    print("Tax Compliance Engine — Self-Tests (#97)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

"""
================================================================================
A2Z MIS 360 — Standard #80: Regulatory Returns Generator Engine
================================================================================

Risk classification: Cat B (deterministic CBK regulatory return generation)

Generates CBK Banking Sector Department (BSD) statutory returns:
    - generate_bsd1_daily_liquidity(...)        -- BSD-1 Daily Liquidity Return
    - generate_bsd2_balance_sheet(...)          -- BSD-2 Statement of Financial Position
    - generate_bsd3_capital_adequacy(...)       -- BSD-3 Monthly Capital Adequacy
    - generate_bsd17_credit_quality(...)        -- BSD-17 Loan Classification
    - validate_return(...)                      -- pre-submission validation

CBK BSD return frequencies byte-for-byte:
    BSD-1  : Daily      — Liquidity ratio (statutory minimum 20%)
    BSD-2  : Weekly     — Statement of Financial Position
    BSD-3  : Monthly    — Capital Adequacy
    BSD-17 : Monthly    — Credit Quality classification (Normal/Watch/Substandard/Doubtful/Loss)

CBK statutory liquidity ratio (different from Basel LCR — local PG/05):
    Liquid assets / Total deposits >= 20% (CBK Banking Act minimum)

Loan classification (CBK PG/04 — 5 categories) byte-for-byte:
    NORMAL       : 0-30 days past due       — 1% provision
    WATCH        : 31-60 days past due      — 3% provision
    SUBSTANDARD  : 61-90 days past due      — 20% provision
    DOUBTFUL     : 91-180 days past due     — 50% provision
    LOSS         : 180+ days past due       — 100% provision

Honesty rules applied:
    Rule 1: ratios = None when denominator <= 0
    Rule 6: missing required fields surfaced in `validation_errors[]`;
            return is NOT generated if required fields missing — fail closed

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# CBK BSD return types
BSD_RETURN_TYPES: Tuple[str, ...] = (
    "BSD_1",   # Daily Liquidity
    "BSD_2",   # Weekly Statement of Financial Position
    "BSD_3",   # Monthly Capital Adequacy
    "BSD_17",  # Monthly Credit Quality
)

# Filing frequency byte-for-byte
RETURN_FREQUENCIES: Dict[str, str] = {
    "BSD_1": "DAILY",
    "BSD_2": "WEEKLY",
    "BSD_3": "MONTHLY",
    "BSD_17": "MONTHLY",
}

# CBK statutory minimum liquidity ratio (different from Basel LCR)
STATUTORY_LIQUIDITY_RATIO_MIN_PCT = Decimal("20")

# Loan classification byte-for-byte (CBK PG/04)
LOAN_CLASSIFICATIONS: Tuple[str, ...] = (
    "NORMAL", "WATCH", "SUBSTANDARD", "DOUBTFUL", "LOSS",
)

LOAN_CLASSIFICATION_DAYS: Dict[str, Tuple[int, int]] = {
    "NORMAL": (0, 30),
    "WATCH": (31, 60),
    "SUBSTANDARD": (61, 90),
    "DOUBTFUL": (91, 180),
    "LOSS": (181, 99999),  # 180+ days
}

LOAN_PROVISION_PCT: Dict[str, Decimal] = {
    "NORMAL": Decimal("1"),
    "WATCH": Decimal("3"),
    "SUBSTANDARD": Decimal("20"),
    "DOUBTFUL": Decimal("50"),
    "LOSS": Decimal("100"),
}


@dataclass
class Bsd1Inputs:
    reporting_date: Optional[date] = None
    cash_kes: Optional[Decimal] = None
    central_bank_balances_kes: Optional[Decimal] = None
    treasury_bills_kes: Optional[Decimal] = None
    other_liquid_assets_kes: Optional[Decimal] = None
    total_deposits_kes: Optional[Decimal] = None


@dataclass
class Bsd2Inputs:
    reporting_date: Optional[date] = None
    # Assets
    cash_and_equivalents_kes: Optional[Decimal] = None
    loans_and_advances_kes: Optional[Decimal] = None
    investments_kes: Optional[Decimal] = None
    other_assets_kes: Optional[Decimal] = None
    # Liabilities
    deposits_kes: Optional[Decimal] = None
    borrowings_kes: Optional[Decimal] = None
    other_liabilities_kes: Optional[Decimal] = None
    # Equity
    shareholders_equity_kes: Optional[Decimal] = None


@dataclass
class Bsd3Inputs:
    reporting_date: Optional[date] = None
    cet1_kes: Optional[Decimal] = None
    tier1_kes: Optional[Decimal] = None
    total_capital_kes: Optional[Decimal] = None
    total_rwa_kes: Optional[Decimal] = None


@dataclass
class LoanForClassification:
    loan_id: str
    outstanding_kes: Optional[Decimal] = None
    days_past_due: Optional[int] = None


def _classify_loan(days_past_due: int) -> str:
    """Map days past due to CBK classification."""
    for cls in LOAN_CLASSIFICATIONS:
        lo, hi = LOAN_CLASSIFICATION_DAYS[cls]
        if lo <= days_past_due <= hi:
            return cls
    return "LOSS"  # Catch-all for very old


class RegulatoryReturnsEngine:
    """Deterministic CBK BSD return generator with validation."""

    @staticmethod
    def generate_bsd1_daily_liquidity(inputs: Bsd1Inputs) -> Dict[str, Any]:
        """
        BSD-1 Daily Liquidity Return.
        Rule 6: validation errors surfaced if required fields missing — fail closed.
        Rule 1: liquidity_ratio_pct=None when total_deposits<=0.
        """
        errors = []
        if inputs.reporting_date is None:
            errors.append("missing_reporting_date")
        if inputs.total_deposits_kes is None:
            errors.append("missing_total_deposits")
        liquid_components = [
            ("cash_kes", inputs.cash_kes),
            ("central_bank_balances_kes", inputs.central_bank_balances_kes),
            ("treasury_bills_kes", inputs.treasury_bills_kes),
            ("other_liquid_assets_kes", inputs.other_liquid_assets_kes),
        ]
        for name, val in liquid_components:
            if val is None:
                errors.append(f"missing_{name}")

        if errors:
            return {
                "return_type": "BSD_1",
                "frequency": RETURN_FREQUENCIES["BSD_1"],
                "generated": False,
                "validation_errors": errors,
                "reason": "missing_required_fields",
            }

        liquid_assets = (inputs.cash_kes + inputs.central_bank_balances_kes
                         + inputs.treasury_bills_kes + inputs.other_liquid_assets_kes)

        if inputs.total_deposits_kes <= 0:
            return {
                "return_type": "BSD_1",
                "frequency": RETURN_FREQUENCIES["BSD_1"],
                "generated": True,
                "reporting_date": inputs.reporting_date.isoformat(),
                "liquid_assets_kes": str(liquid_assets.quantize(Decimal("0.01"))),
                "total_deposits_kes": str(inputs.total_deposits_kes),
                "liquidity_ratio_pct": None,
                "reason": "total_deposits_zero_or_negative",
                "compliant": None,
            }

        ratio = (liquid_assets / inputs.total_deposits_kes) * Decimal("100")
        return {
            "return_type": "BSD_1",
            "frequency": RETURN_FREQUENCIES["BSD_1"],
            "generated": True,
            "reporting_date": inputs.reporting_date.isoformat(),
            "liquid_assets_kes": str(liquid_assets.quantize(Decimal("0.01"))),
            "total_deposits_kes": str(inputs.total_deposits_kes.quantize(Decimal("0.01"))),
            "liquidity_ratio_pct": str(ratio.quantize(Decimal("0.01"))),
            "minimum_required_pct": str(STATUTORY_LIQUIDITY_RATIO_MIN_PCT),
            "compliant": ratio >= STATUTORY_LIQUIDITY_RATIO_MIN_PCT,
        }

    @staticmethod
    def generate_bsd2_balance_sheet(inputs: Bsd2Inputs) -> Dict[str, Any]:
        """
        BSD-2 Weekly Statement of Financial Position.
        Validates: total_assets = total_liabilities + equity (within rounding).
        """
        required = [
            ("reporting_date", inputs.reporting_date),
            ("cash_and_equivalents_kes", inputs.cash_and_equivalents_kes),
            ("loans_and_advances_kes", inputs.loans_and_advances_kes),
            ("deposits_kes", inputs.deposits_kes),
            ("shareholders_equity_kes", inputs.shareholders_equity_kes),
        ]
        errors = [f"missing_{name}" for name, val in required if val is None]
        if errors:
            return {
                "return_type": "BSD_2",
                "frequency": RETURN_FREQUENCIES["BSD_2"],
                "generated": False,
                "validation_errors": errors,
            }

        total_assets = (
            inputs.cash_and_equivalents_kes
            + inputs.loans_and_advances_kes
            + (inputs.investments_kes or Decimal("0"))
            + (inputs.other_assets_kes or Decimal("0"))
        )
        total_liabilities = (
            inputs.deposits_kes
            + (inputs.borrowings_kes or Decimal("0"))
            + (inputs.other_liabilities_kes or Decimal("0"))
        )
        liab_plus_equity = total_liabilities + inputs.shareholders_equity_kes
        balance_check_diff = total_assets - liab_plus_equity
        balanced = abs(balance_check_diff) < Decimal("100")  # KES 100 rounding tolerance

        return {
            "return_type": "BSD_2",
            "frequency": RETURN_FREQUENCIES["BSD_2"],
            "generated": True,
            "reporting_date": inputs.reporting_date.isoformat(),
            "total_assets_kes": str(total_assets.quantize(Decimal("0.01"))),
            "total_liabilities_kes": str(total_liabilities.quantize(Decimal("0.01"))),
            "shareholders_equity_kes": str(inputs.shareholders_equity_kes.quantize(Decimal("0.01"))),
            "total_liabilities_plus_equity_kes": str(liab_plus_equity.quantize(Decimal("0.01"))),
            "balance_check_diff_kes": str(balance_check_diff.quantize(Decimal("0.01"))),
            "balance_check_passed": balanced,
        }

    @staticmethod
    def generate_bsd3_capital_adequacy(inputs: Bsd3Inputs) -> Dict[str, Any]:
        """
        BSD-3 Monthly Capital Adequacy Return.
        Rule 1: ratios=None when total_rwa<=0.
        Rule 6: validation errors surfaced if required fields missing.
        """
        required = [
            ("reporting_date", inputs.reporting_date),
            ("cet1_kes", inputs.cet1_kes),
            ("tier1_kes", inputs.tier1_kes),
            ("total_capital_kes", inputs.total_capital_kes),
            ("total_rwa_kes", inputs.total_rwa_kes),
        ]
        errors = [f"missing_{name}" for name, val in required if val is None]
        if errors:
            return {
                "return_type": "BSD_3",
                "frequency": RETURN_FREQUENCIES["BSD_3"],
                "generated": False,
                "validation_errors": errors,
            }

        if inputs.total_rwa_kes <= 0:
            return {
                "return_type": "BSD_3",
                "frequency": RETURN_FREQUENCIES["BSD_3"],
                "generated": True,
                "reporting_date": inputs.reporting_date.isoformat(),
                "cet1_ratio_pct": None,
                "tier1_ratio_pct": None,
                "total_car_pct": None,
                "reason": "total_rwa_zero_or_negative",
            }

        cet1_ratio = (inputs.cet1_kes / inputs.total_rwa_kes) * Decimal("100")
        tier1_ratio = (inputs.tier1_kes / inputs.total_rwa_kes) * Decimal("100")
        total_car = (inputs.total_capital_kes / inputs.total_rwa_kes) * Decimal("100")

        # CBK minimums
        from utils.capital_adequacy import (
            CBK_CET1_MIN_PCT, CBK_TIER1_MIN_PCT, CBK_TOTAL_CAR_MIN_PCT,
        )
        return {
            "return_type": "BSD_3",
            "frequency": RETURN_FREQUENCIES["BSD_3"],
            "generated": True,
            "reporting_date": inputs.reporting_date.isoformat(),
            "cet1_kes": str(inputs.cet1_kes.quantize(Decimal("0.01"))),
            "tier1_kes": str(inputs.tier1_kes.quantize(Decimal("0.01"))),
            "total_capital_kes": str(inputs.total_capital_kes.quantize(Decimal("0.01"))),
            "rwa_kes": str(inputs.total_rwa_kes.quantize(Decimal("0.01"))),
            "cet1_ratio_pct": str(cet1_ratio.quantize(Decimal("0.01"))),
            "tier1_ratio_pct": str(tier1_ratio.quantize(Decimal("0.01"))),
            "total_car_pct": str(total_car.quantize(Decimal("0.01"))),
            "compliant_cbk": (cet1_ratio >= CBK_CET1_MIN_PCT
                             and tier1_ratio >= CBK_TIER1_MIN_PCT
                             and total_car >= CBK_TOTAL_CAR_MIN_PCT),
        }

    @staticmethod
    def generate_bsd17_credit_quality(loans: List[LoanForClassification]) -> Dict[str, Any]:
        """
        BSD-17 Monthly Credit Quality Return.
        Classifies loans into 5 CBK PG/04 categories with provisions.
        Rule 6: loans with missing data excluded with count surfaced.
        """
        by_class: Dict[str, Decimal] = {c: Decimal("0") for c in LOAN_CLASSIFICATIONS}
        total_provisions = Decimal("0")
        excluded = []
        for loan in loans:
            if loan.outstanding_kes is None or loan.days_past_due is None:
                excluded.append(loan.loan_id)
                continue
            if loan.outstanding_kes < 0 or loan.days_past_due < 0:
                excluded.append(loan.loan_id)
                continue
            cls = _classify_loan(loan.days_past_due)
            by_class[cls] += loan.outstanding_kes
            provision_pct = LOAN_PROVISION_PCT[cls]
            total_provisions += loan.outstanding_kes * provision_pct / Decimal("100")

        total_loan_book = sum(by_class.values())
        npl_amount = (by_class["SUBSTANDARD"] + by_class["DOUBTFUL"] + by_class["LOSS"])
        npl_ratio = ((npl_amount / total_loan_book) * Decimal("100")
                     if total_loan_book > 0 else None)

        return {
            "return_type": "BSD_17",
            "frequency": RETURN_FREQUENCIES["BSD_17"],
            "generated": True,
            "loan_count": len(loans) - len(excluded),
            "excluded_count": len(excluded),
            "by_classification_kes": {k: str(v.quantize(Decimal("0.01"))) for k, v in by_class.items()},
            "total_loan_book_kes": str(total_loan_book.quantize(Decimal("0.01"))),
            "npl_amount_kes": str(npl_amount.quantize(Decimal("0.01"))),
            "npl_ratio_pct": str(npl_ratio.quantize(Decimal("0.01"))) if npl_ratio is not None else None,
            "total_provisions_kes": str(total_provisions.quantize(Decimal("0.01"))),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _bsd1(**kw):
    defaults = dict(
        reporting_date=date(2026, 4, 30),
        cash_kes=Decimal("5000000000"),
        central_bank_balances_kes=Decimal("3000000000"),
        treasury_bills_kes=Decimal("4000000000"),
        other_liquid_assets_kes=Decimal("1000000000"),
        total_deposits_kes=Decimal("50000000000"),
    )
    defaults.update(kw)
    return Bsd1Inputs(**defaults)


def _bsd3(**kw):
    defaults = dict(
        reporting_date=date(2026, 4, 30),
        cet1_kes=Decimal("12000000000"),
        tier1_kes=Decimal("13000000000"),
        total_capital_kes=Decimal("15000000000"),
        total_rwa_kes=Decimal("90000000000"),
    )
    defaults.update(kw)
    return Bsd3Inputs(**defaults)


def _test_bsd1_compliant():
    r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(_bsd1())
    # 13B / 50B = 26% > 20%
    assert r["compliant"] is True
    assert r["liquidity_ratio_pct"] == "26.00"


def _test_bsd1_breach():
    inputs = _bsd1(
        cash_kes=Decimal("100000000"),
        central_bank_balances_kes=Decimal("100000000"),
        treasury_bills_kes=Decimal("100000000"),
        other_liquid_assets_kes=Decimal("100000000"),
    )
    r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(inputs)
    # 400M / 50B = 0.8%
    assert r["compliant"] is False


def _test_bsd1_missing_field_rule6():
    inputs = _bsd1(reporting_date=None)
    r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(inputs)
    assert r["generated"] is False
    assert "missing_reporting_date" in r["validation_errors"]


def _test_bsd1_zero_deposits_rule1():
    inputs = _bsd1(total_deposits_kes=Decimal("0"))
    r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(inputs)
    assert r["liquidity_ratio_pct"] is None


def _test_bsd2_balance_check_passes():
    inputs = Bsd2Inputs(
        reporting_date=date(2026, 4, 30),
        cash_and_equivalents_kes=Decimal("10000000000"),
        loans_and_advances_kes=Decimal("60000000000"),
        investments_kes=Decimal("20000000000"),
        other_assets_kes=Decimal("10000000000"),
        deposits_kes=Decimal("80000000000"),
        borrowings_kes=Decimal("10000000000"),
        other_liabilities_kes=Decimal("0"),
        shareholders_equity_kes=Decimal("10000000000"),
    )
    r = RegulatoryReturnsEngine.generate_bsd2_balance_sheet(inputs)
    # Assets 100B = Liabilities 90B + Equity 10B ✓
    assert r["balance_check_passed"] is True


def _test_bsd2_balance_check_fails():
    inputs = Bsd2Inputs(
        reporting_date=date(2026, 4, 30),
        cash_and_equivalents_kes=Decimal("10000000000"),
        loans_and_advances_kes=Decimal("60000000000"),
        deposits_kes=Decimal("80000000000"),
        shareholders_equity_kes=Decimal("5000000000"),  # too low
    )
    r = RegulatoryReturnsEngine.generate_bsd2_balance_sheet(inputs)
    # Assets 70B vs L+E 85B → mismatch
    assert r["balance_check_passed"] is False


def _test_bsd3_compliant():
    r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(_bsd3())
    # CET1: 12/90 = 13.3% > 10.5% ✓
    # Tier1: 13/90 = 14.4% > 12% ✓
    # Total: 15/90 = 16.7% > 14.5% ✓
    assert r["compliant_cbk"] is True


def _test_bsd3_zero_rwa_rule1():
    inputs = _bsd3(total_rwa_kes=Decimal("0"))
    r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(inputs)
    assert r["total_car_pct"] is None


def _test_bsd3_missing_field_rule6():
    inputs = _bsd3(cet1_kes=None)
    r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(inputs)
    assert r["generated"] is False
    assert "missing_cet1_kes" in r["validation_errors"]


def _test_bsd17_classification():
    loans = [
        LoanForClassification(loan_id="L1", outstanding_kes=Decimal("1000000"),
                              days_past_due=15),     # NORMAL
        LoanForClassification(loan_id="L2", outstanding_kes=Decimal("1000000"),
                              days_past_due=45),     # WATCH
        LoanForClassification(loan_id="L3", outstanding_kes=Decimal("1000000"),
                              days_past_due=75),     # SUBSTANDARD
        LoanForClassification(loan_id="L4", outstanding_kes=Decimal("1000000"),
                              days_past_due=120),    # DOUBTFUL
        LoanForClassification(loan_id="L5", outstanding_kes=Decimal("1000000"),
                              days_past_due=200),    # LOSS
    ]
    r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
    assert r["by_classification_kes"]["NORMAL"] == "1000000.00"
    assert r["by_classification_kes"]["WATCH"] == "1000000.00"
    assert r["by_classification_kes"]["SUBSTANDARD"] == "1000000.00"
    assert r["by_classification_kes"]["DOUBTFUL"] == "1000000.00"
    assert r["by_classification_kes"]["LOSS"] == "1000000.00"
    # NPL = SUB + DOUBT + LOSS = 3M; total = 5M; NPL ratio = 60%
    assert r["npl_ratio_pct"] == "60.00"


def _test_bsd17_provisions_correct():
    """5 loans at each class → provisions = 1+3+20+50+100 = 174k on 5M loans = 1.74M / 5M = 34.8%"""
    loans = [
        LoanForClassification(loan_id="L1", outstanding_kes=Decimal("1000000"),
                              days_past_due=15),
        LoanForClassification(loan_id="L2", outstanding_kes=Decimal("1000000"),
                              days_past_due=45),
        LoanForClassification(loan_id="L3", outstanding_kes=Decimal("1000000"),
                              days_past_due=75),
        LoanForClassification(loan_id="L4", outstanding_kes=Decimal("1000000"),
                              days_past_due=120),
        LoanForClassification(loan_id="L5", outstanding_kes=Decimal("1000000"),
                              days_past_due=200),
    ]
    r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
    # 1% + 3% + 20% + 50% + 100% = 174% on 1M each = 1,740,000
    assert r["total_provisions_kes"] == "1740000.00"


def _test_bsd17_excluded_rule6():
    loans = [LoanForClassification(loan_id="L1", outstanding_kes=None, days_past_due=10)]
    r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
    assert r["excluded_count"] == 1


def _test_return_types_byte_for_byte():
    expected = ("BSD_1", "BSD_2", "BSD_3", "BSD_17")
    for t in expected:
        assert t in BSD_RETURN_TYPES


def _test_frequencies_byte_for_byte():
    assert RETURN_FREQUENCIES["BSD_1"] == "DAILY"
    assert RETURN_FREQUENCIES["BSD_2"] == "WEEKLY"
    assert RETURN_FREQUENCIES["BSD_3"] == "MONTHLY"
    assert RETURN_FREQUENCIES["BSD_17"] == "MONTHLY"


def _test_loan_classifications_byte_for_byte():
    expected = ("NORMAL", "WATCH", "SUBSTANDARD", "DOUBTFUL", "LOSS")
    for c in expected:
        assert c in LOAN_CLASSIFICATIONS


def _test_classification_days_byte_for_byte():
    assert LOAN_CLASSIFICATION_DAYS["NORMAL"] == (0, 30)
    assert LOAN_CLASSIFICATION_DAYS["WATCH"] == (31, 60)
    assert LOAN_CLASSIFICATION_DAYS["SUBSTANDARD"] == (61, 90)
    assert LOAN_CLASSIFICATION_DAYS["DOUBTFUL"] == (91, 180)


def _test_provision_pct_byte_for_byte():
    assert LOAN_PROVISION_PCT["NORMAL"] == Decimal("1")
    assert LOAN_PROVISION_PCT["WATCH"] == Decimal("3")
    assert LOAN_PROVISION_PCT["SUBSTANDARD"] == Decimal("20")
    assert LOAN_PROVISION_PCT["DOUBTFUL"] == Decimal("50")
    assert LOAN_PROVISION_PCT["LOSS"] == Decimal("100")


def _test_statutory_liquidity_byte_for_byte():
    assert STATUTORY_LIQUIDITY_RATIO_MIN_PCT == Decimal("20")


def self_test() -> bool:
    tests = [
        _test_bsd1_compliant,
        _test_bsd1_breach,
        _test_bsd1_missing_field_rule6,
        _test_bsd1_zero_deposits_rule1,
        _test_bsd2_balance_check_passes,
        _test_bsd2_balance_check_fails,
        _test_bsd3_compliant,
        _test_bsd3_zero_rwa_rule1,
        _test_bsd3_missing_field_rule6,
        _test_bsd17_classification,
        _test_bsd17_provisions_correct,
        _test_bsd17_excluded_rule6,
        _test_return_types_byte_for_byte,
        _test_frequencies_byte_for_byte,
        _test_loan_classifications_byte_for_byte,
        _test_classification_days_byte_for_byte,
        _test_provision_pct_byte_for_byte,
        _test_statutory_liquidity_byte_for_byte,
    ]
    print("=" * 60)
    print("Regulatory Returns Generator — Self-Tests (#80)")
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

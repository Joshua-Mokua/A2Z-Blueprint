"""
================================================================================
A2Z MIS 360 — Standard #101: IFRS 16 Lease Accounting Engine
================================================================================

Risk classification: Cat B (deterministic ROU asset + lease liability per IFRS 16)

Provides:
    - lease_classification(...)          -- SHORT_TERM / LOW_VALUE / STANDARD
    - lease_liability_initial(...)       -- PV of lease payments at IBR
    - rou_asset_initial(...)             -- ROU = liability + initial costs - incentives
    - rou_depreciation(...)              -- straight-line over term
    - lease_liability_amortization(...)  -- effective interest method
    - validate_modification(...)         -- modification type classification

3 LEASE_CLASSIFICATIONS byte-for-byte:
    SHORT_TERM, LOW_VALUE, STANDARD

Recognition exemption thresholds byte-for-byte (IFRS 16.5):
    SHORT_TERM_MAX_MONTHS = 12       -- ≤12mo not capitalized
    LOW_VALUE_THRESHOLD_USD = 5000   -- IFRS 16 BC100: ~$5K when new

4 MODIFICATION_TYPES byte-for-byte:
    SCOPE_INCREASE, SCOPE_DECREASE, TERM_EXTENSION, RATE_CHANGE

3 ROU_DEPRECIATION_METHODS byte-for-byte:
    STRAIGHT_LINE, USAGE_BASED, DIMINISHING

Honesty rules applied:
    Rule 1: liability=None when payments empty or rate missing
            depreciation=None when ROU=0 or term=0
    Rule 6: invalid modification type / unknown classification surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 LEASE CLASSIFICATIONS byte-for-byte
LEASE_CLASSIFICATIONS: Tuple[str, ...] = (
    "SHORT_TERM", "LOW_VALUE", "STANDARD",
)

# Recognition exemption thresholds byte-for-byte (IFRS 16.5)
SHORT_TERM_MAX_MONTHS = 12
LOW_VALUE_THRESHOLD_USD = Decimal("5000")

# 4 MODIFICATION TYPES byte-for-byte
MODIFICATION_TYPES: Tuple[str, ...] = (
    "SCOPE_INCREASE", "SCOPE_DECREASE", "TERM_EXTENSION", "RATE_CHANGE",
)

# 3 ROU DEPRECIATION METHODS byte-for-byte
ROU_DEPRECIATION_METHODS: Tuple[str, ...] = (
    "STRAIGHT_LINE", "USAGE_BASED", "DIMINISHING",
)


@dataclass
class LeaseInputs:
    lease_id: str
    monthly_payment: Optional[Decimal] = None
    term_months: Optional[int] = None
    incremental_borrowing_rate_pct: Optional[Decimal] = None  # annual
    initial_direct_costs: Optional[Decimal] = None
    lease_incentives_received: Optional[Decimal] = None
    asset_value_when_new_usd: Optional[Decimal] = None


class LeaseAccountingEngine:
    """Deterministic IFRS 16 lease accounting."""

    @staticmethod
    def lease_classification(
        term_months: Optional[int],
        asset_value_when_new_usd: Optional[Decimal],
    ) -> Optional[str]:
        """
        Per IFRS 16.5: SHORT_TERM (≤12mo) or LOW_VALUE (<$5K when new) → expense.
        Otherwise STANDARD → recognise ROU + liability.
        Rule 1: None when inputs missing.
        """
        if term_months is None or term_months <= 0:
            return None
        if term_months <= SHORT_TERM_MAX_MONTHS:
            return "SHORT_TERM"
        if asset_value_when_new_usd is not None and asset_value_when_new_usd < LOW_VALUE_THRESHOLD_USD:
            return "LOW_VALUE"
        return "STANDARD"

    @staticmethod
    def lease_liability_initial(
        monthly_payment: Optional[Decimal],
        term_months: Optional[int],
        annual_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        PV of monthly lease payments at incremental borrowing rate.
        Formula: PV = PMT × [1 - (1+r)^-n] / r where r = monthly rate.
        Rule 1: None when any input missing or invalid.
        """
        if (monthly_payment is None or monthly_payment <= 0
                or term_months is None or term_months <= 0
                or annual_rate_pct is None or annual_rate_pct < 0):
            return {"pv": None, "computed": False,
                    "reason": "missing_or_invalid_inputs"}
        if annual_rate_pct == 0:
            # No discount → simple sum
            pv = monthly_payment * Decimal(term_months)
        else:
            monthly_rate = annual_rate_pct / Decimal("100") / Decimal("12")
            # PV = PMT × (1 - (1+r)^-n) / r
            one_plus_r = Decimal("1") + monthly_rate
            discount_factor = Decimal("1") - (one_plus_r ** (-term_months))
            pv = monthly_payment * (discount_factor / monthly_rate)
        return {
            "monthly_payment": str(monthly_payment),
            "term_months": term_months,
            "annual_rate_pct": str(annual_rate_pct),
            "pv": str(pv.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def rou_asset_initial(
        lease_liability: Optional[Decimal],
        initial_direct_costs: Optional[Decimal],
        lease_incentives: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        ROU = lease liability + initial direct costs - lease incentives.
        Rule 1: None when liability missing.
        """
        if lease_liability is None:
            return {"rou": None, "computed": False,
                    "reason": "missing_liability"}
        idc = initial_direct_costs if initial_direct_costs is not None else Decimal("0")
        incentives = lease_incentives if lease_incentives is not None else Decimal("0")
        rou = lease_liability + idc - incentives
        return {
            "lease_liability": str(lease_liability),
            "initial_direct_costs": str(idc),
            "lease_incentives": str(incentives),
            "rou": str(rou.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def rou_depreciation(
        rou_value: Optional[Decimal],
        term_months: Optional[int],
        method: str = "STRAIGHT_LINE",
    ) -> Optional[Decimal]:
        """
        Monthly depreciation. Rule 1: None when inputs invalid.
        Rule 6: unknown method returns None.
        """
        if method not in ROU_DEPRECIATION_METHODS:
            return None
        if rou_value is None or rou_value <= 0 or term_months is None or term_months <= 0:
            return None
        if method == "STRAIGHT_LINE":
            return (rou_value / Decimal(term_months)).quantize(Decimal("0.01"))
        # Other methods scaffolded but not used in standard ROU
        return (rou_value / Decimal(term_months)).quantize(Decimal("0.01"))

    @staticmethod
    def lease_liability_amortization(
        opening_liability: Optional[Decimal],
        monthly_payment: Optional[Decimal],
        annual_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        One-period amortization: interest + principal split.
        Rule 1: None when inputs missing.
        """
        if (opening_liability is None or monthly_payment is None
                or annual_rate_pct is None or annual_rate_pct < 0):
            return {"computed": False, "reason": "missing_inputs"}
        monthly_rate = annual_rate_pct / Decimal("100") / Decimal("12")
        interest_portion = opening_liability * monthly_rate
        principal_portion = monthly_payment - interest_portion
        closing_liability = opening_liability - principal_portion
        return {
            "opening_liability": str(opening_liability),
            "interest_portion": str(interest_portion.quantize(Decimal("0.01"))),
            "principal_portion": str(principal_portion.quantize(Decimal("0.01"))),
            "closing_liability": str(closing_liability.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def validate_modification(modification_type: str) -> Dict[str, Any]:
        """Rule 6: unknown modification type rejected."""
        if modification_type not in MODIFICATION_TYPES:
            return {"valid": False,
                    "reason": f"unknown_modification:{modification_type}",
                    "valid_types": list(MODIFICATION_TYPES)}
        return {"valid": True, "modification_type": modification_type}


# ============================================================================
# Self-tests
# ============================================================================

def _test_classifications_byte_for_byte():
    expected = ("SHORT_TERM", "LOW_VALUE", "STANDARD")
    for c in expected:
        assert c in LEASE_CLASSIFICATIONS
    assert len(LEASE_CLASSIFICATIONS) == 3


def _test_thresholds_byte_for_byte():
    assert SHORT_TERM_MAX_MONTHS == 12
    assert LOW_VALUE_THRESHOLD_USD == Decimal("5000")


def _test_modification_types_byte_for_byte():
    expected = ("SCOPE_INCREASE", "SCOPE_DECREASE", "TERM_EXTENSION", "RATE_CHANGE")
    for m in expected:
        assert m in MODIFICATION_TYPES
    assert len(MODIFICATION_TYPES) == 4


def _test_depreciation_methods_byte_for_byte():
    expected = ("STRAIGHT_LINE", "USAGE_BASED", "DIMINISHING")
    for m in expected:
        assert m in ROU_DEPRECIATION_METHODS


def _test_classification_short_term():
    """6mo lease → SHORT_TERM."""
    assert LeaseAccountingEngine.lease_classification(6, None) == "SHORT_TERM"


def _test_classification_short_term_boundary():
    """Exactly 12mo → SHORT_TERM."""
    assert LeaseAccountingEngine.lease_classification(12, None) == "SHORT_TERM"


def _test_classification_low_value():
    """36mo lease but $3K asset → LOW_VALUE."""
    assert LeaseAccountingEngine.lease_classification(36, Decimal("3000")) == "LOW_VALUE"


def _test_classification_low_value_boundary():
    """Exactly $5K → STANDARD (strict <)."""
    assert LeaseAccountingEngine.lease_classification(36, Decimal("5000")) == "STANDARD"


def _test_classification_standard():
    """36mo, $50K asset → STANDARD."""
    assert LeaseAccountingEngine.lease_classification(36, Decimal("50000")) == "STANDARD"


def _test_classification_missing_term_rule1():
    assert LeaseAccountingEngine.lease_classification(None, None) is None


def _test_liability_basic():
    """100K monthly × 36 months @ 10% annual."""
    r = LeaseAccountingEngine.lease_liability_initial(
        Decimal("100000"), 36, Decimal("10"))
    pv = Decimal(r["pv"])
    # Approximate: should be ~3.1M (sum 3.6M discounted)
    assert pv > Decimal("3000000")
    assert pv < Decimal("3200000")


def _test_liability_zero_rate():
    """100K × 36 @ 0% = 3.6M sum."""
    r = LeaseAccountingEngine.lease_liability_initial(
        Decimal("100000"), 36, Decimal("0"))
    assert r["pv"] == "3600000.00"


def _test_liability_missing_rule1():
    r = LeaseAccountingEngine.lease_liability_initial(None, 36, Decimal("10"))
    assert r["pv"] is None


def _test_rou_basic():
    """ROU = 3M liability + 50K direct costs - 100K incentives = 2.95M."""
    r = LeaseAccountingEngine.rou_asset_initial(
        Decimal("3000000"), Decimal("50000"), Decimal("100000"))
    assert r["rou"] == "2950000.00"


def _test_rou_no_costs_or_incentives():
    """ROU = liability when no other components."""
    r = LeaseAccountingEngine.rou_asset_initial(
        Decimal("3000000"), None, None)
    assert r["rou"] == "3000000.00"


def _test_rou_missing_liability_rule1():
    r = LeaseAccountingEngine.rou_asset_initial(None, Decimal("50000"), Decimal("0"))
    assert r["rou"] is None


def _test_depreciation_straight_line():
    """3.6M / 36 months = 100K/month."""
    d = LeaseAccountingEngine.rou_depreciation(Decimal("3600000"), 36)
    assert d == Decimal("100000.00")


def _test_depreciation_missing_rule1():
    assert LeaseAccountingEngine.rou_depreciation(None, 36) is None
    assert LeaseAccountingEngine.rou_depreciation(Decimal("100"), 0) is None


def _test_depreciation_unknown_method_rule6():
    assert LeaseAccountingEngine.rou_depreciation(
        Decimal("3600000"), 36, method="WEIRD") is None


def _test_amortization_basic():
    """Open 3M @ 10% annual, payment 100K → interest 25K, principal 75K, close 2.925M."""
    r = LeaseAccountingEngine.lease_liability_amortization(
        Decimal("3000000"), Decimal("100000"), Decimal("10"))
    assert r["interest_portion"] == "25000.00"
    assert r["principal_portion"] == "75000.00"
    assert r["closing_liability"] == "2925000.00"


def _test_amortization_zero_rate():
    """At 0% rate, all payment is principal."""
    r = LeaseAccountingEngine.lease_liability_amortization(
        Decimal("3000000"), Decimal("100000"), Decimal("0"))
    assert r["interest_portion"] == "0.00"
    assert r["principal_portion"] == "100000.00"


def _test_amortization_missing_rule1():
    r = LeaseAccountingEngine.lease_liability_amortization(
        None, Decimal("100000"), Decimal("10"))
    assert r["computed"] is False


def _test_validate_modification_valid():
    r = LeaseAccountingEngine.validate_modification("SCOPE_INCREASE")
    assert r["valid"] is True


def _test_validate_modification_unknown_rule6():
    r = LeaseAccountingEngine.validate_modification("WEIRD")
    assert r["valid"] is False


def self_test() -> bool:
    tests = [
        _test_classifications_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_modification_types_byte_for_byte,
        _test_depreciation_methods_byte_for_byte,
        _test_classification_short_term,
        _test_classification_short_term_boundary,
        _test_classification_low_value,
        _test_classification_low_value_boundary,
        _test_classification_standard,
        _test_classification_missing_term_rule1,
        _test_liability_basic,
        _test_liability_zero_rate,
        _test_liability_missing_rule1,
        _test_rou_basic,
        _test_rou_no_costs_or_incentives,
        _test_rou_missing_liability_rule1,
        _test_depreciation_straight_line,
        _test_depreciation_missing_rule1,
        _test_depreciation_unknown_method_rule6,
        _test_amortization_basic,
        _test_amortization_zero_rate,
        _test_amortization_missing_rule1,
        _test_validate_modification_valid,
        _test_validate_modification_unknown_rule6,
    ]
    print("=" * 60)
    print("Lease Accounting Engine — Self-Tests (#101 IFRS 16)")
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

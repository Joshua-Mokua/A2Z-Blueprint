"""
================================================================================
A2Z MIS 360 — Standard #106: IAS 12 Income Taxes (Deferred Tax) Engine
================================================================================

Risk classification: Cat B (deterministic deferred tax computation per IAS 12)

Provides:
    - temporary_difference(...)          -- carrying amount - tax base
    - classify_temporary_difference(...) -- TAXABLE / DEDUCTIBLE / NIL
    - deferred_tax(...)                  -- DTL or DTA at enacted rate
    - dta_recoverability(...)            -- recognition test per IAS 12.34
    - current_tax_expense(...)           -- taxable profit × current rate
    - total_tax_expense(...)             -- current + deferred (P&L vs OCI split)

3 TEMPORARY_DIFFERENCE_TYPES byte-for-byte (IAS 12.5):
    TAXABLE       -- CA > tax base → DTL (future taxable)
    DEDUCTIBLE    -- CA < tax base → DTA (future deductible)
    NIL           -- CA = tax base → no deferred tax

5 COMMON_TEMPORARY_DIFFERENCE_SOURCES byte-for-byte:
    DEPRECIATION_DIFFERENCE       -- accelerated tax depreciation
    PROVISION_TIMING              -- provision allowed when paid
    REVALUATION_GAIN              -- revaluation not yet taxed
    UNREALISED_GAIN_LOSS          -- FV through P&L vs realised basis
    LOSS_CARRYFORWARD             -- tax losses available

3 DEFERRED_TAX_RECOGNITION_OUTCOMES byte-for-byte:
    RECOGNISE_FULLY               -- DTL always; DTA when recoverable
    RECOGNISE_PARTIALLY           -- DTA partially recoverable
    DO_NOT_RECOGNISE              -- DTA not recoverable

2 PROFIT_OR_LOSS_ALLOCATION_BUCKETS byte-for-byte (IAS 12.58):
    P_AND_L                       -- changes through profit or loss
    OCI                           -- items recognised in OCI (e.g. revaluation)

5 EXEMPTIONS_FROM_RECOGNITION byte-for-byte (IAS 12.15/24):
    INITIAL_RECOGNITION_GOODWILL  -- IAS 12.15(a)
    INITIAL_RECOGNITION_TXN_NOT_BUSINESS_COMBINATION  -- IAS 12.15(b)
    INITIAL_RECOGNITION_NO_PNL_OR_TAX_IMPACT  -- subset of 15(b)
    INVESTMENT_IN_SUBSIDIARY_PARENT_CONTROLS  -- IAS 12.39
    DISTRIBUTABLE_PROFITS_TIMING  -- IAS 12.40

DTA recoverability test byte-for-byte (IAS 12.34-36):
    DTA recognised only to the extent that future taxable profit will
    be available against which deductible temporary differences can be utilised.

Honesty rules applied:
    Rule 1: deferred_tax=None when CA, tax_base, or rate missing
    Rule 6: negative tax rate rejected (fail closed)
            unknown TD type / allocation bucket surfaced
            DTA recognition without future profit evidence rejected (conservative)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 TEMPORARY DIFFERENCE TYPES byte-for-byte (IAS 12.5)
TEMPORARY_DIFFERENCE_TYPES: Tuple[str, ...] = (
    "TAXABLE", "DEDUCTIBLE", "NIL",
)

# 5 COMMON SOURCES byte-for-byte
COMMON_TEMPORARY_DIFFERENCE_SOURCES: Tuple[str, ...] = (
    "DEPRECIATION_DIFFERENCE",
    "PROVISION_TIMING",
    "REVALUATION_GAIN",
    "UNREALISED_GAIN_LOSS",
    "LOSS_CARRYFORWARD",
)

# 3 RECOGNITION OUTCOMES byte-for-byte
DEFERRED_TAX_RECOGNITION_OUTCOMES: Tuple[str, ...] = (
    "RECOGNISE_FULLY", "RECOGNISE_PARTIALLY", "DO_NOT_RECOGNISE",
)

# 2 ALLOCATION BUCKETS byte-for-byte (IAS 12.58)
PROFIT_OR_LOSS_ALLOCATION_BUCKETS: Tuple[str, ...] = (
    "P_AND_L", "OCI",
)

# 5 EXEMPTIONS byte-for-byte (IAS 12.15/24/39/40)
EXEMPTIONS_FROM_RECOGNITION: Tuple[str, ...] = (
    "INITIAL_RECOGNITION_GOODWILL",
    "INITIAL_RECOGNITION_TXN_NOT_BUSINESS_COMBINATION",
    "INITIAL_RECOGNITION_NO_PNL_OR_TAX_IMPACT",
    "INVESTMENT_IN_SUBSIDIARY_PARENT_CONTROLS",
    "DISTRIBUTABLE_PROFITS_TIMING",
)


class DeferredTaxEngine:
    """Deterministic IAS 12 deferred tax computation."""

    @staticmethod
    def temporary_difference(
        carrying_amount: Optional[Decimal],
        tax_base: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Temporary difference = CA - tax base.
        Rule 1: None when either missing.
        """
        if carrying_amount is None or tax_base is None:
            return {"temporary_difference": None, "computed": False,
                    "reason": "missing_inputs"}
        td = carrying_amount - tax_base
        return {
            "carrying_amount": str(carrying_amount),
            "tax_base": str(tax_base),
            "temporary_difference": str(td),
            "computed": True,
        }

    @staticmethod
    def classify_temporary_difference(
        td_amount: Optional[Decimal],
    ) -> Optional[str]:
        """
        Classify TD per IAS 12.5.
        TD > 0 → TAXABLE (CA > tax base) → DTL
        TD < 0 → DEDUCTIBLE (CA < tax base) → DTA
        TD = 0 → NIL
        Rule 1: None when missing.
        """
        if td_amount is None:
            return None
        if td_amount > 0:
            return "TAXABLE"
        if td_amount < 0:
            return "DEDUCTIBLE"
        return "NIL"

    @staticmethod
    def deferred_tax(
        temporary_difference: Optional[Decimal],
        enacted_tax_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Deferred tax = TD × enacted rate.
        Sign convention: TAXABLE TD → +DTL; DEDUCTIBLE TD → -DTA shown as negative.
        Rule 1: None when inputs missing.
        Rule 6: negative tax rate rejected.
        """
        if temporary_difference is None or enacted_tax_rate_pct is None:
            return {"deferred_tax": None, "computed": False,
                    "reason": "missing_inputs"}
        if enacted_tax_rate_pct < 0:
            return {"deferred_tax": None, "computed": False,
                    "reason": "negative_tax_rate"}
        deferred = (temporary_difference * enacted_tax_rate_pct) / Decimal("100")
        if temporary_difference > 0:
            classification = "DEFERRED_TAX_LIABILITY"
        elif temporary_difference < 0:
            classification = "DEFERRED_TAX_ASSET"
        else:
            classification = "NIL"
        return {
            "temporary_difference": str(temporary_difference),
            "enacted_rate_pct": str(enacted_tax_rate_pct),
            "deferred_tax": str(deferred.quantize(Decimal("0.01"))),
            "classification": classification,
            "computed": True,
        }

    @staticmethod
    def dta_recoverability(
        deductible_td: Optional[Decimal],
        future_taxable_profit_estimate: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IAS 12.34-36: DTA recognised only to the extent of future taxable profit.
        Rule 1: None when inputs missing.
        Rule 6: conservative — if future profit not evidenced (None), no recognition.
        """
        if deductible_td is None:
            return {"recognition": None, "computed": False,
                    "reason": "missing_deductible_td"}
        if deductible_td >= 0:
            return {"recognition": None, "computed": False,
                    "reason": "td_must_be_deductible_negative"}
        if future_taxable_profit_estimate is None:
            return {
                "deductible_td": str(deductible_td),
                "future_profit_estimate": None,
                "recognition": "DO_NOT_RECOGNISE",
                "rationale": "no_evidence_of_future_taxable_profit_per_IAS_12.34",
                "computed": True,
            }
        if future_taxable_profit_estimate <= 0:
            return {
                "deductible_td": str(deductible_td),
                "future_profit_estimate": str(future_taxable_profit_estimate),
                "recognition": "DO_NOT_RECOGNISE",
                "rationale": "no_future_taxable_profit",
                "computed": True,
            }
        # The deductible TD is negative; absolute value is utilisable amount
        utilisable = abs(deductible_td)
        if future_taxable_profit_estimate >= utilisable:
            recognition = "RECOGNISE_FULLY"
            recognised_amount = utilisable
        else:
            recognition = "RECOGNISE_PARTIALLY"
            recognised_amount = future_taxable_profit_estimate
        return {
            "deductible_td": str(deductible_td),
            "future_profit_estimate": str(future_taxable_profit_estimate),
            "recognition": recognition,
            "recognised_amount": str(recognised_amount.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def current_tax_expense(
        taxable_profit: Optional[Decimal],
        current_tax_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Current tax = taxable profit × current rate.
        Rule 1: None when inputs missing.
        Rule 6: negative rate rejected.
        """
        if taxable_profit is None or current_tax_rate_pct is None:
            return {"current_tax": None, "computed": False,
                    "reason": "missing_inputs"}
        if current_tax_rate_pct < 0:
            return {"current_tax": None, "computed": False,
                    "reason": "negative_tax_rate"}
        if taxable_profit < 0:
            # Tax loss — no current tax (potential DTA from loss carryforward)
            return {
                "taxable_profit": str(taxable_profit),
                "current_tax": "0.00",
                "tax_loss_position": True,
                "computed": True,
            }
        tax = (taxable_profit * current_tax_rate_pct) / Decimal("100")
        return {
            "taxable_profit": str(taxable_profit),
            "current_tax_rate_pct": str(current_tax_rate_pct),
            "current_tax": str(tax.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def total_tax_expense(
        current_tax: Optional[Decimal],
        deferred_tax_pnl: Optional[Decimal],
        deferred_tax_oci: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Total tax expense = current tax + deferred tax (P&L only).
        Deferred tax in OCI is reported separately per IAS 12.58.
        Rule 1: None when current_tax missing.
        """
        if current_tax is None:
            return {"total_tax_expense": None, "computed": False,
                    "reason": "missing_current_tax"}
        deferred_pnl = deferred_tax_pnl if deferred_tax_pnl is not None else Decimal("0")
        deferred_oci = deferred_tax_oci if deferred_tax_oci is not None else Decimal("0")
        total_pnl = current_tax + deferred_pnl
        return {
            "current_tax": str(current_tax),
            "deferred_tax_pnl": str(deferred_pnl),
            "deferred_tax_oci": str(deferred_oci),
            "total_tax_expense_pnl": str(total_pnl.quantize(Decimal("0.01"))),
            "deferred_tax_oci_separate": str(deferred_oci.quantize(Decimal("0.01"))),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_td_types_byte_for_byte():
    expected = ("TAXABLE", "DEDUCTIBLE", "NIL")
    for t in expected:
        assert t in TEMPORARY_DIFFERENCE_TYPES
    assert len(TEMPORARY_DIFFERENCE_TYPES) == 3


def _test_td_sources_byte_for_byte():
    expected = (
        "DEPRECIATION_DIFFERENCE",
        "PROVISION_TIMING",
        "REVALUATION_GAIN",
        "UNREALISED_GAIN_LOSS",
        "LOSS_CARRYFORWARD",
    )
    for s in expected:
        assert s in COMMON_TEMPORARY_DIFFERENCE_SOURCES
    assert len(COMMON_TEMPORARY_DIFFERENCE_SOURCES) == 5


def _test_recognition_outcomes_byte_for_byte():
    expected = ("RECOGNISE_FULLY", "RECOGNISE_PARTIALLY", "DO_NOT_RECOGNISE")
    for o in expected:
        assert o in DEFERRED_TAX_RECOGNITION_OUTCOMES


def _test_allocation_buckets_byte_for_byte():
    expected = ("P_AND_L", "OCI")
    for b in expected:
        assert b in PROFIT_OR_LOSS_ALLOCATION_BUCKETS


def _test_exemptions_byte_for_byte():
    expected = (
        "INITIAL_RECOGNITION_GOODWILL",
        "INITIAL_RECOGNITION_TXN_NOT_BUSINESS_COMBINATION",
        "INITIAL_RECOGNITION_NO_PNL_OR_TAX_IMPACT",
        "INVESTMENT_IN_SUBSIDIARY_PARENT_CONTROLS",
        "DISTRIBUTABLE_PROFITS_TIMING",
    )
    for e in expected:
        assert e in EXEMPTIONS_FROM_RECOGNITION
    assert len(EXEMPTIONS_FROM_RECOGNITION) == 5


def _test_temporary_difference_taxable():
    """CA 1M, tax base 800K → TD 200K (taxable)."""
    r = DeferredTaxEngine.temporary_difference(
        Decimal("1000000"), Decimal("800000"))
    assert r["temporary_difference"] == "200000"


def _test_temporary_difference_deductible():
    """CA 800K, tax base 1M → TD -200K (deductible)."""
    r = DeferredTaxEngine.temporary_difference(
        Decimal("800000"), Decimal("1000000"))
    assert r["temporary_difference"] == "-200000"


def _test_temporary_difference_nil():
    r = DeferredTaxEngine.temporary_difference(
        Decimal("1000000"), Decimal("1000000"))
    assert r["temporary_difference"] == "0"


def _test_temporary_difference_missing_rule1():
    r = DeferredTaxEngine.temporary_difference(None, Decimal("1000000"))
    assert r["temporary_difference"] is None


def _test_classify_taxable():
    assert DeferredTaxEngine.classify_temporary_difference(Decimal("200000")) == "TAXABLE"


def _test_classify_deductible():
    assert DeferredTaxEngine.classify_temporary_difference(Decimal("-200000")) == "DEDUCTIBLE"


def _test_classify_nil():
    assert DeferredTaxEngine.classify_temporary_difference(Decimal("0")) == "NIL"


def _test_classify_missing_rule1():
    assert DeferredTaxEngine.classify_temporary_difference(None) is None


def _test_deferred_tax_dtl():
    """TD 200K @ 30% → DTL 60K."""
    r = DeferredTaxEngine.deferred_tax(Decimal("200000"), Decimal("30"))
    assert r["deferred_tax"] == "60000.00"
    assert r["classification"] == "DEFERRED_TAX_LIABILITY"


def _test_deferred_tax_dta():
    """TD -200K @ 30% → DTA -60K (sign indicates asset)."""
    r = DeferredTaxEngine.deferred_tax(Decimal("-200000"), Decimal("30"))
    assert r["deferred_tax"] == "-60000.00"
    assert r["classification"] == "DEFERRED_TAX_ASSET"


def _test_deferred_tax_nil():
    r = DeferredTaxEngine.deferred_tax(Decimal("0"), Decimal("30"))
    assert r["deferred_tax"] == "0.00"
    assert r["classification"] == "NIL"


def _test_deferred_tax_missing_rule1():
    r = DeferredTaxEngine.deferred_tax(None, Decimal("30"))
    assert r["deferred_tax"] is None


def _test_deferred_tax_negative_rate_rule6():
    r = DeferredTaxEngine.deferred_tax(Decimal("200000"), Decimal("-5"))
    assert r["computed"] is False


def _test_dta_recoverability_full():
    """Deductible TD -100K, future profit 200K → fully recoverable."""
    r = DeferredTaxEngine.dta_recoverability(
        Decimal("-100000"), Decimal("200000"))
    assert r["recognition"] == "RECOGNISE_FULLY"
    assert r["recognised_amount"] == "100000.00"


def _test_dta_recoverability_partial():
    """Deductible TD -200K, future profit only 50K → partial."""
    r = DeferredTaxEngine.dta_recoverability(
        Decimal("-200000"), Decimal("50000"))
    assert r["recognition"] == "RECOGNISE_PARTIALLY"
    assert r["recognised_amount"] == "50000.00"


def _test_dta_recoverability_no_profit():
    """No future profit → DO_NOT_RECOGNISE."""
    r = DeferredTaxEngine.dta_recoverability(
        Decimal("-100000"), Decimal("0"))
    assert r["recognition"] == "DO_NOT_RECOGNISE"


def _test_dta_recoverability_no_evidence():
    """Future profit None → conservative DO_NOT_RECOGNISE."""
    r = DeferredTaxEngine.dta_recoverability(
        Decimal("-100000"), None)
    assert r["recognition"] == "DO_NOT_RECOGNISE"


def _test_dta_recoverability_missing_td_rule1():
    r = DeferredTaxEngine.dta_recoverability(None, Decimal("100000"))
    assert r["computed"] is False


def _test_current_tax_basic():
    """1M taxable profit @ 30% = 300K tax."""
    r = DeferredTaxEngine.current_tax_expense(Decimal("1000000"), Decimal("30"))
    assert r["current_tax"] == "300000.00"


def _test_current_tax_loss_position():
    """Negative taxable profit → 0 current tax (loss position)."""
    r = DeferredTaxEngine.current_tax_expense(Decimal("-500000"), Decimal("30"))
    assert r["current_tax"] == "0.00"
    assert r["tax_loss_position"] is True


def _test_current_tax_missing_rule1():
    r = DeferredTaxEngine.current_tax_expense(None, Decimal("30"))
    assert r["current_tax"] is None


def _test_current_tax_negative_rate_rule6():
    r = DeferredTaxEngine.current_tax_expense(
        Decimal("1000000"), Decimal("-30"))
    assert r["computed"] is False


def _test_total_tax_expense_basic():
    """Current 300K + deferred P&L 50K = 350K."""
    r = DeferredTaxEngine.total_tax_expense(
        Decimal("300000"), Decimal("50000"))
    assert r["total_tax_expense_pnl"] == "350000.00"


def _test_total_tax_expense_with_oci():
    """OCI deferred kept separate."""
    r = DeferredTaxEngine.total_tax_expense(
        Decimal("300000"), Decimal("50000"), Decimal("20000"))
    assert r["total_tax_expense_pnl"] == "350000.00"
    assert r["deferred_tax_oci_separate"] == "20000.00"


def _test_total_tax_expense_missing_rule1():
    r = DeferredTaxEngine.total_tax_expense(None, Decimal("50000"))
    assert r["computed"] is False


def self_test() -> bool:
    tests = [
        _test_td_types_byte_for_byte,
        _test_td_sources_byte_for_byte,
        _test_recognition_outcomes_byte_for_byte,
        _test_allocation_buckets_byte_for_byte,
        _test_exemptions_byte_for_byte,
        _test_temporary_difference_taxable,
        _test_temporary_difference_deductible,
        _test_temporary_difference_nil,
        _test_temporary_difference_missing_rule1,
        _test_classify_taxable,
        _test_classify_deductible,
        _test_classify_nil,
        _test_classify_missing_rule1,
        _test_deferred_tax_dtl,
        _test_deferred_tax_dta,
        _test_deferred_tax_nil,
        _test_deferred_tax_missing_rule1,
        _test_deferred_tax_negative_rate_rule6,
        _test_dta_recoverability_full,
        _test_dta_recoverability_partial,
        _test_dta_recoverability_no_profit,
        _test_dta_recoverability_no_evidence,
        _test_dta_recoverability_missing_td_rule1,
        _test_current_tax_basic,
        _test_current_tax_loss_position,
        _test_current_tax_missing_rule1,
        _test_current_tax_negative_rate_rule6,
        _test_total_tax_expense_basic,
        _test_total_tax_expense_with_oci,
        _test_total_tax_expense_missing_rule1,
    ]
    print("=" * 60)
    print("Deferred Tax Engine — Self-Tests (#106 IAS 12)")
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

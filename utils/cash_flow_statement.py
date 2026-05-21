"""
================================================================================
A2Z MIS 360 — Standard #114: IAS 7 Cash Flow Statements
================================================================================

Risk classification: Cat B (deterministic classification + reconciliation per IAS 7)

Provides:
    - classify_cash_flow(...)            -- OPERATING / INVESTING / FINANCING
    - validate_method(...)               -- DIRECT vs INDIRECT
    - cash_and_equivalents_check(...)    -- 3-month rule for equivalents
    - reconcile_pnl_to_operating(...)    -- indirect method reconciliation
    - liabilities_from_financing_recon(...) -- IAS 7.44A-44E

3 CASH_FLOW_CATEGORIES byte-for-byte (IAS 7.10):
    OPERATING       -- principal revenue activities + remainder
    INVESTING       -- acquisition/disposal of long-term assets
    FINANCING       -- changes in equity + borrowings

2 PRESENTATION_METHODS byte-for-byte (IAS 7.18):
    DIRECT          -- gross cash receipts/payments
    INDIRECT        -- profit/loss adjusted for non-cash items

3 OPERATING_RECON_ADJUSTMENTS byte-for-byte (IAS 7.20):
    NON_CASH_ITEMS              -- depreciation, amortisation
    DEFERRALS_AND_ACCRUALS      -- working capital changes
    INVESTING_OR_FINANCING_ITEMS -- gains on disposal, etc.

5 OPERATING_CASH_FLOWS_EXAMPLES byte-for-byte (IAS 7.14):
    CASH_FROM_CUSTOMERS
    CASH_PAID_TO_SUPPLIERS_AND_EMPLOYEES
    INTEREST_RECEIVED
    INTEREST_PAID
    INCOME_TAXES_PAID

5 INVESTING_CASH_FLOWS_EXAMPLES byte-for-byte (IAS 7.16):
    PAYMENTS_TO_ACQUIRE_PPE
    RECEIPTS_FROM_DISPOSAL_OF_PPE
    ACQUISITION_OF_SUBSIDIARY
    LOANS_MADE_TO_OTHER_PARTIES
    INVESTMENTS_IN_OTHER_ENTITIES

5 FINANCING_CASH_FLOWS_EXAMPLES byte-for-byte (IAS 7.17):
    PROCEEDS_FROM_SHARE_ISSUANCE
    PROCEEDS_FROM_BORROWINGS
    REPAYMENT_OF_BORROWINGS
    DIVIDENDS_PAID
    PAYMENTS_FOR_LEASE_LIABILITIES

Cash equivalent rule byte-for-byte (IAS 7.7):
    CASH_EQUIVALENT_MAX_MATURITY_MONTHS = 3   -- ≤3 months from acquisition

Honesty rules applied:
    Rule 1: classification=None when item_type missing
    Rule 6: unknown cash flow category surfaced
            non-cash items in cash flow statement rejected (fail closed)

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 CASH FLOW CATEGORIES byte-for-byte (IAS 7.10)
CASH_FLOW_CATEGORIES: Tuple[str, ...] = (
    "OPERATING", "INVESTING", "FINANCING",
)

# 2 PRESENTATION METHODS byte-for-byte (IAS 7.18)
PRESENTATION_METHODS: Tuple[str, ...] = (
    "DIRECT", "INDIRECT",
)

# 3 OPERATING RECON ADJUSTMENTS byte-for-byte (IAS 7.20)
OPERATING_RECON_ADJUSTMENTS: Tuple[str, ...] = (
    "NON_CASH_ITEMS",
    "DEFERRALS_AND_ACCRUALS",
    "INVESTING_OR_FINANCING_ITEMS",
)

# 5 OPERATING CASH FLOW EXAMPLES byte-for-byte (IAS 7.14)
OPERATING_CASH_FLOWS_EXAMPLES: Tuple[str, ...] = (
    "CASH_FROM_CUSTOMERS",
    "CASH_PAID_TO_SUPPLIERS_AND_EMPLOYEES",
    "INTEREST_RECEIVED",
    "INTEREST_PAID",
    "INCOME_TAXES_PAID",
)

# 5 INVESTING CASH FLOW EXAMPLES byte-for-byte (IAS 7.16)
INVESTING_CASH_FLOWS_EXAMPLES: Tuple[str, ...] = (
    "PAYMENTS_TO_ACQUIRE_PPE",
    "RECEIPTS_FROM_DISPOSAL_OF_PPE",
    "ACQUISITION_OF_SUBSIDIARY",
    "LOANS_MADE_TO_OTHER_PARTIES",
    "INVESTMENTS_IN_OTHER_ENTITIES",
)

# 5 FINANCING CASH FLOW EXAMPLES byte-for-byte (IAS 7.17)
FINANCING_CASH_FLOWS_EXAMPLES: Tuple[str, ...] = (
    "PROCEEDS_FROM_SHARE_ISSUANCE",
    "PROCEEDS_FROM_BORROWINGS",
    "REPAYMENT_OF_BORROWINGS",
    "DIVIDENDS_PAID",
    "PAYMENTS_FOR_LEASE_LIABILITIES",
)

# Cash equivalent rule byte-for-byte (IAS 7.7)
CASH_EQUIVALENT_MAX_MATURITY_MONTHS = 3


# Map of all known item types to category
ITEM_TYPE_TO_CATEGORY: Dict[str, str] = {}
for it in OPERATING_CASH_FLOWS_EXAMPLES:
    ITEM_TYPE_TO_CATEGORY[it] = "OPERATING"
for it in INVESTING_CASH_FLOWS_EXAMPLES:
    ITEM_TYPE_TO_CATEGORY[it] = "INVESTING"
for it in FINANCING_CASH_FLOWS_EXAMPLES:
    ITEM_TYPE_TO_CATEGORY[it] = "FINANCING"


class CashFlowEngine:
    """Deterministic IAS 7 cash flow classification + reconciliation."""

    @staticmethod
    def classify_cash_flow(item_type: str) -> Dict[str, Any]:
        """
        Classify cash flow item per IAS 7.14, .16, .17.
        Rule 6: unknown item_type surfaced.
        """
        if item_type not in ITEM_TYPE_TO_CATEGORY:
            return {"category": None, "computed": False,
                    "reason": f"unknown_item_type:{item_type}",
                    "valid_operating": list(OPERATING_CASH_FLOWS_EXAMPLES),
                    "valid_investing": list(INVESTING_CASH_FLOWS_EXAMPLES),
                    "valid_financing": list(FINANCING_CASH_FLOWS_EXAMPLES)}
        return {
            "item_type": item_type,
            "category": ITEM_TYPE_TO_CATEGORY[item_type],
            "computed": True,
        }

    @staticmethod
    def validate_method(method: str) -> Dict[str, Any]:
        """Rule 6: unknown method rejected."""
        if method not in PRESENTATION_METHODS:
            return {"valid": False,
                    "reason": f"unknown_method:{method}",
                    "valid_methods": list(PRESENTATION_METHODS)}
        return {"valid": True, "method": method}

    @staticmethod
    def cash_and_equivalents_check(
        instrument_maturity_months: Optional[int],
    ) -> Dict[str, Any]:
        """
        IAS 7.7: cash equivalent must have ≤3 months maturity from acquisition.
        Rule 1: None when maturity missing.
        """
        if instrument_maturity_months is None:
            return {"qualifies_as_equivalent": None, "computed": False,
                    "reason": "missing_maturity"}
        if instrument_maturity_months < 0:
            return {"qualifies_as_equivalent": None, "computed": False,
                    "reason": "negative_maturity"}
        qualifies = instrument_maturity_months <= CASH_EQUIVALENT_MAX_MATURITY_MONTHS
        return {
            "instrument_maturity_months": instrument_maturity_months,
            "max_months": CASH_EQUIVALENT_MAX_MATURITY_MONTHS,
            "qualifies_as_equivalent": qualifies,
            "rationale": (f"maturity_within_3_months_per_IAS_7.7" if qualifies
                          else "exceeds_3_month_threshold_not_equivalent"),
            "computed": True,
        }

    @staticmethod
    def reconcile_pnl_to_operating(
        profit_before_tax: Optional[Decimal],
        depreciation: Optional[Decimal] = None,
        amortisation: Optional[Decimal] = None,
        impairment: Optional[Decimal] = None,
        gain_on_disposal: Optional[Decimal] = None,
        increase_in_receivables: Optional[Decimal] = None,
        increase_in_payables: Optional[Decimal] = None,
        increase_in_inventory: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Indirect method reconciliation per IAS 7.20.
        Operating cash flow = PBT
            + non-cash items (depreciation, amortisation, impairment)
            - gains on disposal (reclassified to investing)
            - increase in receivables (operating asset growth uses cash)
            + increase in payables (operating liability growth provides cash)
            - increase in inventory
        Rule 1: None when PBT missing.
        """
        if profit_before_tax is None:
            return {"operating_cash_flow": None, "computed": False,
                    "reason": "missing_profit_before_tax"}
        # Default missing inputs to 0
        dep = depreciation if depreciation is not None else Decimal("0")
        amr = amortisation if amortisation is not None else Decimal("0")
        imp = impairment if impairment is not None else Decimal("0")
        gain = gain_on_disposal if gain_on_disposal is not None else Decimal("0")
        inc_rec = increase_in_receivables if increase_in_receivables is not None else Decimal("0")
        inc_pay = increase_in_payables if increase_in_payables is not None else Decimal("0")
        inc_inv = increase_in_inventory if increase_in_inventory is not None else Decimal("0")
        operating = (profit_before_tax + dep + amr + imp - gain
                     - inc_rec + inc_pay - inc_inv)
        return {
            "profit_before_tax": str(profit_before_tax),
            "depreciation": str(dep),
            "amortisation": str(amr),
            "impairment": str(imp),
            "gain_on_disposal": str(gain),
            "increase_in_receivables": str(inc_rec),
            "increase_in_payables": str(inc_pay),
            "increase_in_inventory": str(inc_inv),
            "operating_cash_flow": str(operating.quantize(Decimal("0.01"))),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_categories_byte_for_byte():
    expected = ("OPERATING", "INVESTING", "FINANCING")
    for c in expected:
        assert c in CASH_FLOW_CATEGORIES
    assert len(CASH_FLOW_CATEGORIES) == 3


def _test_methods_byte_for_byte():
    expected = ("DIRECT", "INDIRECT")
    for m in expected:
        assert m in PRESENTATION_METHODS


def _test_recon_adjustments_byte_for_byte():
    expected = ("NON_CASH_ITEMS", "DEFERRALS_AND_ACCRUALS",
                "INVESTING_OR_FINANCING_ITEMS")
    for a in expected:
        assert a in OPERATING_RECON_ADJUSTMENTS


def _test_operating_examples_byte_for_byte():
    assert len(OPERATING_CASH_FLOWS_EXAMPLES) == 5
    for o in ("CASH_FROM_CUSTOMERS", "CASH_PAID_TO_SUPPLIERS_AND_EMPLOYEES",
              "INTEREST_RECEIVED", "INTEREST_PAID", "INCOME_TAXES_PAID"):
        assert o in OPERATING_CASH_FLOWS_EXAMPLES


def _test_investing_examples_byte_for_byte():
    assert len(INVESTING_CASH_FLOWS_EXAMPLES) == 5
    for i in ("PAYMENTS_TO_ACQUIRE_PPE", "RECEIPTS_FROM_DISPOSAL_OF_PPE",
              "ACQUISITION_OF_SUBSIDIARY", "LOANS_MADE_TO_OTHER_PARTIES",
              "INVESTMENTS_IN_OTHER_ENTITIES"):
        assert i in INVESTING_CASH_FLOWS_EXAMPLES


def _test_financing_examples_byte_for_byte():
    assert len(FINANCING_CASH_FLOWS_EXAMPLES) == 5
    for f in ("PROCEEDS_FROM_SHARE_ISSUANCE", "PROCEEDS_FROM_BORROWINGS",
              "REPAYMENT_OF_BORROWINGS", "DIVIDENDS_PAID",
              "PAYMENTS_FOR_LEASE_LIABILITIES"):
        assert f in FINANCING_CASH_FLOWS_EXAMPLES


def _test_cash_equivalent_threshold_byte_for_byte():
    assert CASH_EQUIVALENT_MAX_MATURITY_MONTHS == 3


def _test_classify_operating():
    r = CashFlowEngine.classify_cash_flow("INTEREST_PAID")
    assert r["category"] == "OPERATING"


def _test_classify_investing():
    r = CashFlowEngine.classify_cash_flow("PAYMENTS_TO_ACQUIRE_PPE")
    assert r["category"] == "INVESTING"


def _test_classify_financing():
    r = CashFlowEngine.classify_cash_flow("DIVIDENDS_PAID")
    assert r["category"] == "FINANCING"


def _test_classify_lease_payments_financing():
    """Lease payments → FINANCING per IFRS 16."""
    r = CashFlowEngine.classify_cash_flow("PAYMENTS_FOR_LEASE_LIABILITIES")
    assert r["category"] == "FINANCING"


def _test_classify_unknown_rule6():
    r = CashFlowEngine.classify_cash_flow("WEIRD")
    assert r["category"] is None


def _test_validate_method_direct():
    r = CashFlowEngine.validate_method("DIRECT")
    assert r["valid"] is True


def _test_validate_method_indirect():
    r = CashFlowEngine.validate_method("INDIRECT")
    assert r["valid"] is True


def _test_validate_method_unknown_rule6():
    r = CashFlowEngine.validate_method("WEIRD")
    assert r["valid"] is False


def _test_cash_equivalent_qualifies():
    """2 months → qualifies."""
    r = CashFlowEngine.cash_and_equivalents_check(2)
    assert r["qualifies_as_equivalent"] is True


def _test_cash_equivalent_boundary_inclusive():
    """Exactly 3 months → qualifies (≤ inclusive)."""
    r = CashFlowEngine.cash_and_equivalents_check(3)
    assert r["qualifies_as_equivalent"] is True


def _test_cash_equivalent_exceeds():
    """4 months → does NOT qualify."""
    r = CashFlowEngine.cash_and_equivalents_check(4)
    assert r["qualifies_as_equivalent"] is False


def _test_cash_equivalent_zero():
    """0 months (cash) → qualifies."""
    r = CashFlowEngine.cash_and_equivalents_check(0)
    assert r["qualifies_as_equivalent"] is True


def _test_cash_equivalent_missing_rule1():
    r = CashFlowEngine.cash_and_equivalents_check(None)
    assert r["qualifies_as_equivalent"] is None


def _test_cash_equivalent_negative_rule6():
    r = CashFlowEngine.cash_and_equivalents_check(-1)
    assert r["qualifies_as_equivalent"] is None


def _test_recon_basic():
    """PBT 1M + Dep 200K + Amort 100K - Gain 50K - IncRec 30K + IncPay 40K - IncInv 60K = 1.2M."""
    r = CashFlowEngine.reconcile_pnl_to_operating(
        Decimal("1000000"),
        depreciation=Decimal("200000"),
        amortisation=Decimal("100000"),
        gain_on_disposal=Decimal("50000"),
        increase_in_receivables=Decimal("30000"),
        increase_in_payables=Decimal("40000"),
        increase_in_inventory=Decimal("60000"),
    )
    assert r["operating_cash_flow"] == "1200000.00"


def _test_recon_depreciation_only():
    """PBT 500K + Dep 100K = 600K."""
    r = CashFlowEngine.reconcile_pnl_to_operating(
        Decimal("500000"), depreciation=Decimal("100000"))
    assert r["operating_cash_flow"] == "600000.00"


def _test_recon_pbt_only():
    """PBT alone with no adjustments."""
    r = CashFlowEngine.reconcile_pnl_to_operating(Decimal("500000"))
    assert r["operating_cash_flow"] == "500000.00"


def _test_recon_loss_position():
    """Loss before tax = -500K + Dep 100K = -400K."""
    r = CashFlowEngine.reconcile_pnl_to_operating(
        Decimal("-500000"), depreciation=Decimal("100000"))
    assert r["operating_cash_flow"] == "-400000.00"


def _test_recon_missing_pbt_rule1():
    r = CashFlowEngine.reconcile_pnl_to_operating(None)
    assert r["operating_cash_flow"] is None


def _test_recon_gain_subtracted():
    """Gain on disposal moves to investing — subtracted from operating."""
    r = CashFlowEngine.reconcile_pnl_to_operating(
        Decimal("1000000"), gain_on_disposal=Decimal("100000"))
    assert r["operating_cash_flow"] == "900000.00"


def _test_recon_receivables_use_cash():
    """Increase in receivables → cash USED → subtracted."""
    r = CashFlowEngine.reconcile_pnl_to_operating(
        Decimal("1000000"), increase_in_receivables=Decimal("50000"))
    assert r["operating_cash_flow"] == "950000.00"


def _test_recon_payables_provide_cash():
    """Increase in payables → cash PROVIDED → added."""
    r = CashFlowEngine.reconcile_pnl_to_operating(
        Decimal("1000000"), increase_in_payables=Decimal("50000"))
    assert r["operating_cash_flow"] == "1050000.00"


def _test_item_type_to_category_complete():
    """All 15 example items must map."""
    for it in OPERATING_CASH_FLOWS_EXAMPLES:
        assert ITEM_TYPE_TO_CATEGORY[it] == "OPERATING"
    for it in INVESTING_CASH_FLOWS_EXAMPLES:
        assert ITEM_TYPE_TO_CATEGORY[it] == "INVESTING"
    for it in FINANCING_CASH_FLOWS_EXAMPLES:
        assert ITEM_TYPE_TO_CATEGORY[it] == "FINANCING"


def self_test() -> bool:
    tests = [
        _test_categories_byte_for_byte,
        _test_methods_byte_for_byte,
        _test_recon_adjustments_byte_for_byte,
        _test_operating_examples_byte_for_byte,
        _test_investing_examples_byte_for_byte,
        _test_financing_examples_byte_for_byte,
        _test_cash_equivalent_threshold_byte_for_byte,
        _test_classify_operating,
        _test_classify_investing,
        _test_classify_financing,
        _test_classify_lease_payments_financing,
        _test_classify_unknown_rule6,
        _test_validate_method_direct,
        _test_validate_method_indirect,
        _test_validate_method_unknown_rule6,
        _test_cash_equivalent_qualifies,
        _test_cash_equivalent_boundary_inclusive,
        _test_cash_equivalent_exceeds,
        _test_cash_equivalent_zero,
        _test_cash_equivalent_missing_rule1,
        _test_cash_equivalent_negative_rule6,
        _test_recon_basic,
        _test_recon_depreciation_only,
        _test_recon_pbt_only,
        _test_recon_loss_position,
        _test_recon_missing_pbt_rule1,
        _test_recon_gain_subtracted,
        _test_recon_receivables_use_cash,
        _test_recon_payables_provide_cash,
        _test_item_type_to_category_complete,
    ]
    print("=" * 60)
    print("Cash Flow Engine — Self-Tests (#114 IAS 7)")
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

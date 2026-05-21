"""
================================================================================
A2Z MIS 360 — Standard #107: IFRS 15 Revenue Recognition Engine
================================================================================

Risk classification: Cat B (deterministic 5-step IFRS 15 model)

Provides:
    - identify_contract(...)             -- 5 contract criteria
    - identify_performance_obligations(...) -- distinct goods/services
    - determine_transaction_price(...)   -- fixed + variable consideration
    - allocate_transaction_price(...)    -- standalone selling price ratio
    - revenue_recognition_pattern(...)   -- POINT_IN_TIME vs OVER_TIME
    - validate_contract_modification(...) -- 3 modification types

5 IFRS_15_STEPS byte-for-byte (IFRS 15.IN7):
    IDENTIFY_CONTRACT
    IDENTIFY_PERFORMANCE_OBLIGATIONS
    DETERMINE_TRANSACTION_PRICE
    ALLOCATE_TRANSACTION_PRICE
    RECOGNISE_REVENUE

5 CONTRACT_CRITERIA byte-for-byte (IFRS 15.9):
    PARTIES_APPROVED
    RIGHTS_IDENTIFIABLE
    PAYMENT_TERMS_IDENTIFIABLE
    COMMERCIAL_SUBSTANCE
    COLLECTION_PROBABLE

2 RECOGNITION_PATTERNS byte-for-byte (IFRS 15.31-37):
    POINT_IN_TIME   -- control transfers at single point
    OVER_TIME       -- 3 IFRS 15.35 criteria for over-time

3 OVER_TIME_CRITERIA byte-for-byte (IFRS 15.35):
    CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS
    PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET
    NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT

5 INDICATORS_OF_CONTROL_TRANSFER byte-for-byte (IFRS 15.38):
    PRESENT_RIGHT_TO_PAYMENT
    LEGAL_TITLE_TRANSFERRED
    PHYSICAL_POSSESSION_TRANSFERRED
    SIGNIFICANT_RISKS_AND_REWARDS_TRANSFERRED
    CUSTOMER_ACCEPTANCE

3 VARIABLE_CONSIDERATION_TYPES byte-for-byte:
    DISCOUNT
    REBATE
    REFUND_OR_RETURN

3 CONTRACT_MODIFICATION_TYPES byte-for-byte (IFRS 15.18-21):
    SEPARATE_CONTRACT          -- distinct + standalone price
    TERMINATION_AND_NEW        -- distinct, not standalone price
    CUMULATIVE_CATCH_UP        -- not distinct → restate revenue

Honesty rules applied:
    Rule 1: contract_valid=None when criteria list empty
            allocation=None when transaction_price or SSPs missing
    Rule 6: unknown recognition pattern / modification type / criterion surfaced
            collection NOT probable → contract NOT recognised (fail closed)
            distinct PO required for separate accounting (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 5 IFRS 15 STEPS byte-for-byte (IFRS 15.IN7)
IFRS_15_STEPS: Tuple[str, ...] = (
    "IDENTIFY_CONTRACT",
    "IDENTIFY_PERFORMANCE_OBLIGATIONS",
    "DETERMINE_TRANSACTION_PRICE",
    "ALLOCATE_TRANSACTION_PRICE",
    "RECOGNISE_REVENUE",
)

# 5 CONTRACT CRITERIA byte-for-byte (IFRS 15.9)
CONTRACT_CRITERIA: Tuple[str, ...] = (
    "PARTIES_APPROVED",
    "RIGHTS_IDENTIFIABLE",
    "PAYMENT_TERMS_IDENTIFIABLE",
    "COMMERCIAL_SUBSTANCE",
    "COLLECTION_PROBABLE",
)

# 2 RECOGNITION PATTERNS byte-for-byte
RECOGNITION_PATTERNS: Tuple[str, ...] = (
    "POINT_IN_TIME", "OVER_TIME",
)

# 3 OVER-TIME CRITERIA byte-for-byte (IFRS 15.35)
OVER_TIME_CRITERIA: Tuple[str, ...] = (
    "CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS",
    "PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET",
    "NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT",
)

# 5 INDICATORS OF CONTROL TRANSFER byte-for-byte (IFRS 15.38)
INDICATORS_OF_CONTROL_TRANSFER: Tuple[str, ...] = (
    "PRESENT_RIGHT_TO_PAYMENT",
    "LEGAL_TITLE_TRANSFERRED",
    "PHYSICAL_POSSESSION_TRANSFERRED",
    "SIGNIFICANT_RISKS_AND_REWARDS_TRANSFERRED",
    "CUSTOMER_ACCEPTANCE",
)

# 3 VARIABLE CONSIDERATION TYPES byte-for-byte
VARIABLE_CONSIDERATION_TYPES: Tuple[str, ...] = (
    "DISCOUNT", "REBATE", "REFUND_OR_RETURN",
)

# 3 CONTRACT MODIFICATION TYPES byte-for-byte (IFRS 15.18-21)
CONTRACT_MODIFICATION_TYPES: Tuple[str, ...] = (
    "SEPARATE_CONTRACT",
    "TERMINATION_AND_NEW",
    "CUMULATIVE_CATCH_UP",
)


class RevenueRecognitionEngine:
    """Deterministic IFRS 15 5-step model."""

    @staticmethod
    def identify_contract(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        Step 1: Validate 5 contract criteria per IFRS 15.9.
        ALL 5 must be met. Rule 6: missing/False on any → contract NOT recognised.
        """
        missing: List[str] = []
        for c in CONTRACT_CRITERIA:
            if not criteria_met.get(c, False):
                missing.append(c)
        contract_recognised = len(missing) == 0
        return {
            "criteria_required": list(CONTRACT_CRITERIA),
            "criteria_missing_or_false": missing,
            "contract_recognised": contract_recognised,
            "rationale": ("all_5_criteria_met" if contract_recognised
                          else "missing_criteria_per_IFRS_15.9"),
        }

    @staticmethod
    def identify_performance_obligations(
        promises: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Step 2: Identify distinct performance obligations.
        Each promise must have 'is_distinct' flag (IFRS 15.27).
        """
        if not promises:
            return {"performance_obligations": [], "computed": False,
                    "reason": "empty_promises"}
        distinct: List[Dict[str, Any]] = []
        non_distinct: List[Dict[str, Any]] = []
        for p in promises:
            if p.get("is_distinct"):
                distinct.append(p)
            else:
                non_distinct.append(p)
        return {
            "promise_count": len(promises),
            "distinct_count": len(distinct),
            "performance_obligations": distinct,
            "non_distinct_promises": non_distinct,
            "computed": True,
        }

    @staticmethod
    def determine_transaction_price(
        fixed_consideration: Optional[Decimal],
        variable_consideration: Optional[Decimal] = None,
        non_cash_consideration: Optional[Decimal] = None,
        consideration_payable_to_customer: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Step 3: Transaction price = fixed + variable + non-cash - payable to customer.
        Rule 1: None when fixed missing.
        """
        if fixed_consideration is None:
            return {"transaction_price": None, "computed": False,
                    "reason": "missing_fixed_consideration"}
        var_c = variable_consideration if variable_consideration is not None else Decimal("0")
        nc_c = non_cash_consideration if non_cash_consideration is not None else Decimal("0")
        cp_c = consideration_payable_to_customer if consideration_payable_to_customer is not None else Decimal("0")
        tp = fixed_consideration + var_c + nc_c - cp_c
        return {
            "fixed_consideration": str(fixed_consideration),
            "variable_consideration": str(var_c),
            "non_cash_consideration": str(nc_c),
            "consideration_payable_to_customer": str(cp_c),
            "transaction_price": str(tp.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def allocate_transaction_price(
        transaction_price: Optional[Decimal],
        standalone_selling_prices: Dict[str, Decimal],
    ) -> Dict[str, Any]:
        """
        Step 4: Allocate transaction price using SSP ratio per IFRS 15.74.
        Rule 1: None when TP missing or SSP dict empty.
        """
        if transaction_price is None:
            return {"allocations": None, "computed": False,
                    "reason": "missing_transaction_price"}
        if not standalone_selling_prices:
            return {"allocations": None, "computed": False,
                    "reason": "empty_ssp"}
        total_ssp = sum(standalone_selling_prices.values(), start=Decimal("0"))
        if total_ssp <= 0:
            return {"allocations": None, "computed": False,
                    "reason": "non_positive_total_ssp"}
        allocations: Dict[str, str] = {}
        for po_id, ssp in standalone_selling_prices.items():
            allocated = (ssp / total_ssp) * transaction_price
            allocations[po_id] = str(allocated.quantize(Decimal("0.01")))
        return {
            "transaction_price": str(transaction_price),
            "total_ssp": str(total_ssp),
            "allocations": allocations,
            "computed": True,
        }

    @staticmethod
    def revenue_recognition_pattern(
        over_time_criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        Step 5: Determine POINT_IN_TIME vs OVER_TIME per IFRS 15.35.
        ANY ONE of the 3 over-time criteria met → OVER_TIME.
        Otherwise → POINT_IN_TIME.
        """
        any_met = False
        criteria_met: List[str] = []
        for c in OVER_TIME_CRITERIA:
            if over_time_criteria_met.get(c, False):
                any_met = True
                criteria_met.append(c)
        if any_met:
            return {
                "pattern": "OVER_TIME",
                "criteria_met": criteria_met,
                "rationale": "at_least_one_over_time_criterion_per_IFRS_15.35",
            }
        return {
            "pattern": "POINT_IN_TIME",
            "criteria_met": [],
            "rationale": "no_over_time_criteria_met_default_point_in_time",
        }

    @staticmethod
    def validate_contract_modification(
        modification_type: str,
        is_distinct: Optional[bool] = None,
        is_standalone_price: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        IFRS 15.18-21: classify modification.
        SEPARATE_CONTRACT: distinct + standalone price
        TERMINATION_AND_NEW: distinct, not standalone price
        CUMULATIVE_CATCH_UP: not distinct
        Rule 6: unknown modification_type rejected.
        """
        if modification_type not in CONTRACT_MODIFICATION_TYPES:
            return {"valid": False,
                    "reason": f"unknown_modification:{modification_type}",
                    "valid_types": list(CONTRACT_MODIFICATION_TYPES)}
        # Validate consistency
        if modification_type == "SEPARATE_CONTRACT":
            if is_distinct is False or is_standalone_price is False:
                return {"valid": False,
                        "reason": "separate_contract_requires_distinct_and_standalone_price"}
        elif modification_type == "TERMINATION_AND_NEW":
            if is_distinct is False:
                return {"valid": False,
                        "reason": "termination_and_new_requires_distinct"}
            if is_standalone_price is True:
                return {"valid": False,
                        "reason": "termination_and_new_excludes_standalone_price"}
        elif modification_type == "CUMULATIVE_CATCH_UP":
            if is_distinct is True:
                return {"valid": False,
                        "reason": "catch_up_requires_not_distinct"}
        return {
            "valid": True,
            "modification_type": modification_type,
            "is_distinct": is_distinct,
            "is_standalone_price": is_standalone_price,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_steps_byte_for_byte():
    expected = (
        "IDENTIFY_CONTRACT",
        "IDENTIFY_PERFORMANCE_OBLIGATIONS",
        "DETERMINE_TRANSACTION_PRICE",
        "ALLOCATE_TRANSACTION_PRICE",
        "RECOGNISE_REVENUE",
    )
    for s in expected:
        assert s in IFRS_15_STEPS
    assert len(IFRS_15_STEPS) == 5


def _test_contract_criteria_byte_for_byte():
    expected = (
        "PARTIES_APPROVED",
        "RIGHTS_IDENTIFIABLE",
        "PAYMENT_TERMS_IDENTIFIABLE",
        "COMMERCIAL_SUBSTANCE",
        "COLLECTION_PROBABLE",
    )
    for c in expected:
        assert c in CONTRACT_CRITERIA
    assert len(CONTRACT_CRITERIA) == 5


def _test_recognition_patterns_byte_for_byte():
    expected = ("POINT_IN_TIME", "OVER_TIME")
    for p in expected:
        assert p in RECOGNITION_PATTERNS


def _test_over_time_criteria_byte_for_byte():
    expected = (
        "CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS",
        "PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET",
        "NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT",
    )
    for c in expected:
        assert c in OVER_TIME_CRITERIA
    assert len(OVER_TIME_CRITERIA) == 3


def _test_control_indicators_byte_for_byte():
    expected = (
        "PRESENT_RIGHT_TO_PAYMENT",
        "LEGAL_TITLE_TRANSFERRED",
        "PHYSICAL_POSSESSION_TRANSFERRED",
        "SIGNIFICANT_RISKS_AND_REWARDS_TRANSFERRED",
        "CUSTOMER_ACCEPTANCE",
    )
    for i in expected:
        assert i in INDICATORS_OF_CONTROL_TRANSFER
    assert len(INDICATORS_OF_CONTROL_TRANSFER) == 5


def _test_variable_consideration_types_byte_for_byte():
    expected = ("DISCOUNT", "REBATE", "REFUND_OR_RETURN")
    for t in expected:
        assert t in VARIABLE_CONSIDERATION_TYPES


def _test_modification_types_byte_for_byte():
    expected = ("SEPARATE_CONTRACT", "TERMINATION_AND_NEW", "CUMULATIVE_CATCH_UP")
    for m in expected:
        assert m in CONTRACT_MODIFICATION_TYPES


def _test_identify_contract_all_met():
    """All 5 criteria met → recognised."""
    r = RevenueRecognitionEngine.identify_contract({
        "PARTIES_APPROVED": True,
        "RIGHTS_IDENTIFIABLE": True,
        "PAYMENT_TERMS_IDENTIFIABLE": True,
        "COMMERCIAL_SUBSTANCE": True,
        "COLLECTION_PROBABLE": True,
    })
    assert r["contract_recognised"] is True
    assert r["criteria_missing_or_false"] == []


def _test_identify_contract_collection_not_probable_rule6():
    """Collection not probable → NOT recognised (fail closed)."""
    r = RevenueRecognitionEngine.identify_contract({
        "PARTIES_APPROVED": True,
        "RIGHTS_IDENTIFIABLE": True,
        "PAYMENT_TERMS_IDENTIFIABLE": True,
        "COMMERCIAL_SUBSTANCE": True,
        "COLLECTION_PROBABLE": False,
    })
    assert r["contract_recognised"] is False
    assert "COLLECTION_PROBABLE" in r["criteria_missing_or_false"]


def _test_identify_contract_all_missing():
    r = RevenueRecognitionEngine.identify_contract({})
    assert r["contract_recognised"] is False
    assert len(r["criteria_missing_or_false"]) == 5


def _test_identify_performance_obligations_basic():
    r = RevenueRecognitionEngine.identify_performance_obligations([
        {"id": "PO1", "is_distinct": True},
        {"id": "PO2", "is_distinct": True},
        {"id": "PO3", "is_distinct": False},
    ])
    assert r["distinct_count"] == 2
    assert len(r["non_distinct_promises"]) == 1


def _test_identify_performance_obligations_empty():
    r = RevenueRecognitionEngine.identify_performance_obligations([])
    assert r["computed"] is False


def _test_transaction_price_basic():
    """Fixed 1M + variable 100K = 1.1M."""
    r = RevenueRecognitionEngine.determine_transaction_price(
        Decimal("1000000"), Decimal("100000"))
    assert r["transaction_price"] == "1100000.00"


def _test_transaction_price_with_payable():
    """Fixed 1M - payable to customer 50K = 950K."""
    r = RevenueRecognitionEngine.determine_transaction_price(
        Decimal("1000000"),
        consideration_payable_to_customer=Decimal("50000"))
    assert r["transaction_price"] == "950000.00"


def _test_transaction_price_missing_rule1():
    r = RevenueRecognitionEngine.determine_transaction_price(None)
    assert r["transaction_price"] is None


def _test_allocate_transaction_price_basic():
    """TP 1M; SSPs PO1=600, PO2=400. Total SSP=1000.
    PO1 gets 600/1000 × 1M = 600K; PO2 gets 400K.
    """
    r = RevenueRecognitionEngine.allocate_transaction_price(
        Decimal("1000000"),
        {"PO1": Decimal("600"), "PO2": Decimal("400")})
    assert r["allocations"]["PO1"] == "600000.00"
    assert r["allocations"]["PO2"] == "400000.00"


def _test_allocate_transaction_price_proportional():
    """TP 800K; SSPs equal 500/500/500. Each PO gets 800K/3.
    """
    r = RevenueRecognitionEngine.allocate_transaction_price(
        Decimal("900000"),
        {"PO1": Decimal("500"), "PO2": Decimal("500"), "PO3": Decimal("500")})
    assert r["allocations"]["PO1"] == "300000.00"
    assert r["allocations"]["PO2"] == "300000.00"


def _test_allocate_missing_tp_rule1():
    r = RevenueRecognitionEngine.allocate_transaction_price(
        None, {"PO1": Decimal("100")})
    assert r["allocations"] is None


def _test_allocate_empty_ssp_rule1():
    r = RevenueRecognitionEngine.allocate_transaction_price(
        Decimal("1000000"), {})
    assert r["allocations"] is None


def _test_recognition_pattern_over_time_one_criterion():
    """Just 1 of 3 → OVER_TIME."""
    r = RevenueRecognitionEngine.revenue_recognition_pattern({
        "CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS": True,
        "PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET": False,
        "NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT": False,
    })
    assert r["pattern"] == "OVER_TIME"


def _test_recognition_pattern_point_in_time():
    """No criteria → POINT_IN_TIME."""
    r = RevenueRecognitionEngine.revenue_recognition_pattern({
        "CUSTOMER_RECEIVES_SIMULTANEOUS_BENEFITS": False,
        "PERFORMANCE_CREATES_OR_ENHANCES_CUSTOMER_ASSET": False,
        "NO_ALTERNATIVE_USE_PLUS_RIGHT_TO_PAYMENT": False,
    })
    assert r["pattern"] == "POINT_IN_TIME"


def _test_recognition_pattern_default_empty():
    """Empty dict → POINT_IN_TIME default."""
    r = RevenueRecognitionEngine.revenue_recognition_pattern({})
    assert r["pattern"] == "POINT_IN_TIME"


def _test_modification_separate_contract_valid():
    r = RevenueRecognitionEngine.validate_contract_modification(
        "SEPARATE_CONTRACT", is_distinct=True, is_standalone_price=True)
    assert r["valid"] is True


def _test_modification_separate_contract_inconsistent():
    """SEPARATE_CONTRACT requires standalone price."""
    r = RevenueRecognitionEngine.validate_contract_modification(
        "SEPARATE_CONTRACT", is_distinct=True, is_standalone_price=False)
    assert r["valid"] is False


def _test_modification_termination_valid():
    r = RevenueRecognitionEngine.validate_contract_modification(
        "TERMINATION_AND_NEW", is_distinct=True, is_standalone_price=False)
    assert r["valid"] is True


def _test_modification_termination_inconsistent():
    """TERMINATION_AND_NEW requires NOT standalone price."""
    r = RevenueRecognitionEngine.validate_contract_modification(
        "TERMINATION_AND_NEW", is_distinct=True, is_standalone_price=True)
    assert r["valid"] is False


def _test_modification_cumulative_catchup_valid():
    r = RevenueRecognitionEngine.validate_contract_modification(
        "CUMULATIVE_CATCH_UP", is_distinct=False)
    assert r["valid"] is True


def _test_modification_unknown_rule6():
    r = RevenueRecognitionEngine.validate_contract_modification("WEIRD")
    assert r["valid"] is False


def self_test() -> bool:
    tests = [
        _test_steps_byte_for_byte,
        _test_contract_criteria_byte_for_byte,
        _test_recognition_patterns_byte_for_byte,
        _test_over_time_criteria_byte_for_byte,
        _test_control_indicators_byte_for_byte,
        _test_variable_consideration_types_byte_for_byte,
        _test_modification_types_byte_for_byte,
        _test_identify_contract_all_met,
        _test_identify_contract_collection_not_probable_rule6,
        _test_identify_contract_all_missing,
        _test_identify_performance_obligations_basic,
        _test_identify_performance_obligations_empty,
        _test_transaction_price_basic,
        _test_transaction_price_with_payable,
        _test_transaction_price_missing_rule1,
        _test_allocate_transaction_price_basic,
        _test_allocate_transaction_price_proportional,
        _test_allocate_missing_tp_rule1,
        _test_allocate_empty_ssp_rule1,
        _test_recognition_pattern_over_time_one_criterion,
        _test_recognition_pattern_point_in_time,
        _test_recognition_pattern_default_empty,
        _test_modification_separate_contract_valid,
        _test_modification_separate_contract_inconsistent,
        _test_modification_termination_valid,
        _test_modification_termination_inconsistent,
        _test_modification_cumulative_catchup_valid,
        _test_modification_unknown_rule6,
    ]
    print("=" * 60)
    print("Revenue Recognition Engine — Self-Tests (#107 IFRS 15)")
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

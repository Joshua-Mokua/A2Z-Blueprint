"""
================================================================================
A2Z MIS 360 — Standard #111: IAS 1 Presentation of Financial Statements
================================================================================

Risk classification: Cat B (deterministic statement structure + classification)

Implements IAS 1 requirements for:
    - Components of a complete set of financial statements
    - Going concern assessment
    - Classification of items as current/non-current
    - Statement of comprehensive income (P&L + OCI)
    - Statement of changes in equity
    - Materiality and aggregation principles

Provides:
    - validate_complete_statements_set(...)  -- 5 required components
    - going_concern_assessment(...)          -- ASSESSED / SIGNIFICANT_UNCERTAINTY / NOT_GOING_CONCERN
    - asset_current_classification(...)      -- CURRENT vs NON_CURRENT
    - liability_current_classification(...)  -- CURRENT vs NON_CURRENT
    - oci_classification(...)                -- RECYCLABLE_TO_PNL vs NEVER_RECYCLED
    - materiality_test(...)                  -- material when > 5% of relevant base

5 COMPLETE_STATEMENTS_COMPONENTS byte-for-byte (IAS 1.10):
    STATEMENT_OF_FINANCIAL_POSITION       -- balance sheet
    STATEMENT_OF_PROFIT_OR_LOSS_AND_OCI   -- combined or two-statement format
    STATEMENT_OF_CHANGES_IN_EQUITY
    STATEMENT_OF_CASH_FLOWS
    NOTES_INCLUDING_ACCOUNTING_POLICIES

3 GOING_CONCERN_OUTCOMES byte-for-byte (IAS 1.25-26):
    GOING_CONCERN_ASSESSED                 -- standard basis, no material uncertainties
    SIGNIFICANT_UNCERTAINTY_DISCLOSED      -- disclose but continue going concern
    NOT_PREPARED_ON_GOING_CONCERN_BASIS    -- alternative basis (e.g. liquidation)

2 STATEMENT_FORMATS byte-for-byte (IAS 1.81-87):
    SINGLE_STATEMENT     -- combined P&L + OCI in one statement
    TWO_STATEMENT        -- separate income statement + statement of comprehensive income

5 CURRENT_ASSET_CRITERIA byte-for-byte (IAS 1.66):
    EXPECTED_REALISATION_IN_OPERATING_CYCLE
    HELD_PRIMARILY_FOR_TRADING
    EXPECTED_REALISATION_WITHIN_12_MONTHS
    CASH_OR_CASH_EQUIVALENT
    INVENTORY_HELD_FOR_SALE_OR_USE

5 CURRENT_LIABILITY_CRITERIA byte-for-byte (IAS 1.69):
    EXPECTED_SETTLEMENT_IN_OPERATING_CYCLE
    HELD_PRIMARILY_FOR_TRADING
    DUE_WITHIN_12_MONTHS
    NO_UNCONDITIONAL_RIGHT_TO_DEFER_BEYOND_12M
    LIABILITY_PAYABLE_ON_DEMAND

2 OCI_CLASSIFICATIONS byte-for-byte (IAS 1.7):
    RECYCLABLE_TO_PNL        -- e.g. cash flow hedge reserve, FVTOCI debt
    NEVER_RECYCLED           -- e.g. revaluation reserve, FVTOCI equity, IAS 19R remeasurement

5 OCI_LINE_ITEMS byte-for-byte (illustrative IAS 1.82A):
    REVALUATION_SURPLUS                    -- NEVER_RECYCLED (IAS 16)
    FVTOCI_DEBT_FAIR_VALUE_CHANGES         -- RECYCLABLE (IFRS 9)
    FVTOCI_EQUITY_FAIR_VALUE_CHANGES       -- NEVER_RECYCLED (IFRS 9.5.7.5)
    CASH_FLOW_HEDGE_RESERVE                -- RECYCLABLE (IFRS 9)
    DEFINED_BENEFIT_REMEASUREMENT          -- NEVER_RECYCLED (IAS 19R)

Materiality thresholds byte-for-byte (IAS 1.7 quantitative guidance):
    MATERIALITY_PCT_OF_REVENUE       = 5      -- 5% of revenue
    MATERIALITY_PCT_OF_TOTAL_ASSETS  = 1      -- 1% of total assets
    MATERIALITY_PCT_OF_EQUITY        = 5      -- 5% of equity

Honesty rules applied:
    Rule 1: classification=None when inputs missing
    Rule 6: unknown statement / classification / OCI item surfaced
            negative base for materiality rejected (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 5 COMPLETE STATEMENTS COMPONENTS byte-for-byte (IAS 1.10)
COMPLETE_STATEMENTS_COMPONENTS: Tuple[str, ...] = (
    "STATEMENT_OF_FINANCIAL_POSITION",
    "STATEMENT_OF_PROFIT_OR_LOSS_AND_OCI",
    "STATEMENT_OF_CHANGES_IN_EQUITY",
    "STATEMENT_OF_CASH_FLOWS",
    "NOTES_INCLUDING_ACCOUNTING_POLICIES",
)

# 3 GOING CONCERN OUTCOMES byte-for-byte (IAS 1.25-26)
GOING_CONCERN_OUTCOMES: Tuple[str, ...] = (
    "GOING_CONCERN_ASSESSED",
    "SIGNIFICANT_UNCERTAINTY_DISCLOSED",
    "NOT_PREPARED_ON_GOING_CONCERN_BASIS",
)

# 2 STATEMENT FORMATS byte-for-byte (IAS 1.81-87)
STATEMENT_FORMATS: Tuple[str, ...] = (
    "SINGLE_STATEMENT", "TWO_STATEMENT",
)

# 5 CURRENT ASSET CRITERIA byte-for-byte (IAS 1.66)
CURRENT_ASSET_CRITERIA: Tuple[str, ...] = (
    "EXPECTED_REALISATION_IN_OPERATING_CYCLE",
    "HELD_PRIMARILY_FOR_TRADING",
    "EXPECTED_REALISATION_WITHIN_12_MONTHS",
    "CASH_OR_CASH_EQUIVALENT",
    "INVENTORY_HELD_FOR_SALE_OR_USE",
)

# 5 CURRENT LIABILITY CRITERIA byte-for-byte (IAS 1.69)
CURRENT_LIABILITY_CRITERIA: Tuple[str, ...] = (
    "EXPECTED_SETTLEMENT_IN_OPERATING_CYCLE",
    "HELD_PRIMARILY_FOR_TRADING",
    "DUE_WITHIN_12_MONTHS",
    "NO_UNCONDITIONAL_RIGHT_TO_DEFER_BEYOND_12M",
    "LIABILITY_PAYABLE_ON_DEMAND",
)

# 2 OCI CLASSIFICATIONS byte-for-byte (IAS 1.7)
OCI_CLASSIFICATIONS: Tuple[str, ...] = (
    "RECYCLABLE_TO_PNL", "NEVER_RECYCLED",
)

# 5 OCI LINE ITEMS byte-for-byte
OCI_LINE_ITEMS: Tuple[str, ...] = (
    "REVALUATION_SURPLUS",
    "FVTOCI_DEBT_FAIR_VALUE_CHANGES",
    "FVTOCI_EQUITY_FAIR_VALUE_CHANGES",
    "CASH_FLOW_HEDGE_RESERVE",
    "DEFINED_BENEFIT_REMEASUREMENT",
)

# Mapping byte-for-byte (which OCI items recycle)
OCI_RECYCLING_MAP: Dict[str, str] = {
    "REVALUATION_SURPLUS": "NEVER_RECYCLED",
    "FVTOCI_DEBT_FAIR_VALUE_CHANGES": "RECYCLABLE_TO_PNL",
    "FVTOCI_EQUITY_FAIR_VALUE_CHANGES": "NEVER_RECYCLED",
    "CASH_FLOW_HEDGE_RESERVE": "RECYCLABLE_TO_PNL",
    "DEFINED_BENEFIT_REMEASUREMENT": "NEVER_RECYCLED",
}

# Materiality thresholds byte-for-byte
MATERIALITY_PCT_OF_REVENUE = Decimal("5")
MATERIALITY_PCT_OF_TOTAL_ASSETS = Decimal("1")
MATERIALITY_PCT_OF_EQUITY = Decimal("5")


class IAS1PresentationEngine:
    """Deterministic IAS 1 presentation framework."""

    @staticmethod
    def validate_complete_statements_set(
        provided_components: List[str],
    ) -> Dict[str, Any]:
        """
        Verify all 5 IAS 1.10 components are present.
        Rule 6: missing components surfaced.
        """
        missing = [c for c in COMPLETE_STATEMENTS_COMPONENTS
                    if c not in provided_components]
        complete = len(missing) == 0
        return {
            "required_count": len(COMPLETE_STATEMENTS_COMPONENTS),
            "provided_count": len(provided_components),
            "missing": missing,
            "complete": complete,
            "rationale": ("all_5_components_provided" if complete
                          else "missing_required_components_per_IAS_1.10"),
        }

    @staticmethod
    def going_concern_assessment(
        material_uncertainties_exist: Optional[bool],
        management_intends_to_liquidate_or_cease: Optional[bool],
    ) -> Dict[str, Any]:
        """
        Per IAS 1.25-26.
        Rule 1: None when inputs missing.
        """
        if material_uncertainties_exist is None or management_intends_to_liquidate_or_cease is None:
            return {"outcome": None, "computed": False,
                    "reason": "missing_inputs"}
        if management_intends_to_liquidate_or_cease:
            return {
                "outcome": "NOT_PREPARED_ON_GOING_CONCERN_BASIS",
                "rationale": "alternative_basis_per_IAS_1.25",
                "disclosure_required": True,
                "computed": True,
            }
        if material_uncertainties_exist:
            return {
                "outcome": "SIGNIFICANT_UNCERTAINTY_DISCLOSED",
                "rationale": "material_uncertainty_disclosed_per_IAS_1.25",
                "disclosure_required": True,
                "computed": True,
            }
        return {
            "outcome": "GOING_CONCERN_ASSESSED",
            "rationale": "no_material_uncertainties_per_IAS_1.25",
            "disclosure_required": False,
            "computed": True,
        }

    @staticmethod
    def asset_current_classification(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        IAS 1.66: asset is CURRENT if ANY of the 5 criteria are met.
        Otherwise NON_CURRENT.
        """
        met: List[str] = []
        for c in CURRENT_ASSET_CRITERIA:
            if criteria_met.get(c, False):
                met.append(c)
        is_current = len(met) > 0
        return {
            "criteria_met": met,
            "classification": "CURRENT" if is_current else "NON_CURRENT",
            "rationale": ("any_current_criterion_met_per_IAS_1.66"
                          if is_current else "no_current_criteria_default_non_current"),
        }

    @staticmethod
    def liability_current_classification(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        IAS 1.69: liability is CURRENT if ANY of the 5 criteria are met.
        """
        met: List[str] = []
        for c in CURRENT_LIABILITY_CRITERIA:
            if criteria_met.get(c, False):
                met.append(c)
        is_current = len(met) > 0
        return {
            "criteria_met": met,
            "classification": "CURRENT" if is_current else "NON_CURRENT",
            "rationale": ("any_current_criterion_met_per_IAS_1.69"
                          if is_current else "no_current_criteria_default_non_current"),
        }

    @staticmethod
    def oci_classification(line_item: str) -> Dict[str, Any]:
        """
        Classify OCI line item as RECYCLABLE or NEVER_RECYCLED.
        Rule 6: unknown line item rejected.
        """
        if line_item not in OCI_LINE_ITEMS:
            return {"classification": None, "computed": False,
                    "reason": f"unknown_oci_line:{line_item}",
                    "valid_lines": list(OCI_LINE_ITEMS)}
        classification = OCI_RECYCLING_MAP[line_item]
        return {
            "line_item": line_item,
            "classification": classification,
            "recyclable": classification == "RECYCLABLE_TO_PNL",
            "computed": True,
        }

    @staticmethod
    def materiality_test(
        item_amount: Optional[Decimal],
        base_type: str,
        base_amount: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Materiality test per IAS 1.7 (5%/1%/5% thresholds).
        Rule 1: None when inputs missing.
        Rule 6: negative base rejected; unknown base_type rejected.
        """
        if base_type == "REVENUE":
            threshold = MATERIALITY_PCT_OF_REVENUE
        elif base_type == "TOTAL_ASSETS":
            threshold = MATERIALITY_PCT_OF_TOTAL_ASSETS
        elif base_type == "EQUITY":
            threshold = MATERIALITY_PCT_OF_EQUITY
        else:
            return {"material": None, "computed": False,
                    "reason": f"unknown_base_type:{base_type}"}
        if item_amount is None or base_amount is None:
            return {"material": None, "computed": False,
                    "reason": "missing_inputs"}
        if base_amount <= 0:
            return {"material": None, "computed": False,
                    "reason": "non_positive_base"}
        pct = (abs(item_amount) / base_amount) * Decimal("100")
        # Strict > so exactly threshold is NOT material (consistent with G91 materiality)
        is_material = pct > threshold
        return {
            "item_amount": str(item_amount),
            "base_type": base_type,
            "base_amount": str(base_amount),
            "pct_of_base": str(pct.quantize(Decimal("0.0001"))),
            "threshold_pct": str(threshold),
            "material": is_material,
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_components_byte_for_byte():
    expected = (
        "STATEMENT_OF_FINANCIAL_POSITION",
        "STATEMENT_OF_PROFIT_OR_LOSS_AND_OCI",
        "STATEMENT_OF_CHANGES_IN_EQUITY",
        "STATEMENT_OF_CASH_FLOWS",
        "NOTES_INCLUDING_ACCOUNTING_POLICIES",
    )
    for c in expected:
        assert c in COMPLETE_STATEMENTS_COMPONENTS
    assert len(COMPLETE_STATEMENTS_COMPONENTS) == 5


def _test_going_concern_outcomes_byte_for_byte():
    expected = ("GOING_CONCERN_ASSESSED",
                "SIGNIFICANT_UNCERTAINTY_DISCLOSED",
                "NOT_PREPARED_ON_GOING_CONCERN_BASIS")
    for o in expected:
        assert o in GOING_CONCERN_OUTCOMES


def _test_statement_formats_byte_for_byte():
    for f in ("SINGLE_STATEMENT", "TWO_STATEMENT"):
        assert f in STATEMENT_FORMATS


def _test_current_asset_criteria_byte_for_byte():
    expected = (
        "EXPECTED_REALISATION_IN_OPERATING_CYCLE",
        "HELD_PRIMARILY_FOR_TRADING",
        "EXPECTED_REALISATION_WITHIN_12_MONTHS",
        "CASH_OR_CASH_EQUIVALENT",
        "INVENTORY_HELD_FOR_SALE_OR_USE",
    )
    for c in expected:
        assert c in CURRENT_ASSET_CRITERIA
    assert len(CURRENT_ASSET_CRITERIA) == 5


def _test_current_liability_criteria_byte_for_byte():
    expected = (
        "EXPECTED_SETTLEMENT_IN_OPERATING_CYCLE",
        "HELD_PRIMARILY_FOR_TRADING",
        "DUE_WITHIN_12_MONTHS",
        "NO_UNCONDITIONAL_RIGHT_TO_DEFER_BEYOND_12M",
        "LIABILITY_PAYABLE_ON_DEMAND",
    )
    for c in expected:
        assert c in CURRENT_LIABILITY_CRITERIA
    assert len(CURRENT_LIABILITY_CRITERIA) == 5


def _test_oci_classifications_byte_for_byte():
    for c in ("RECYCLABLE_TO_PNL", "NEVER_RECYCLED"):
        assert c in OCI_CLASSIFICATIONS


def _test_oci_line_items_byte_for_byte():
    expected = (
        "REVALUATION_SURPLUS",
        "FVTOCI_DEBT_FAIR_VALUE_CHANGES",
        "FVTOCI_EQUITY_FAIR_VALUE_CHANGES",
        "CASH_FLOW_HEDGE_RESERVE",
        "DEFINED_BENEFIT_REMEASUREMENT",
    )
    for i in expected:
        assert i in OCI_LINE_ITEMS
    assert len(OCI_LINE_ITEMS) == 5


def _test_oci_recycling_map_byte_for_byte():
    """Verify each OCI line item's recycling status — banks routinely get this wrong."""
    assert OCI_RECYCLING_MAP["REVALUATION_SURPLUS"] == "NEVER_RECYCLED"
    assert OCI_RECYCLING_MAP["FVTOCI_DEBT_FAIR_VALUE_CHANGES"] == "RECYCLABLE_TO_PNL"
    assert OCI_RECYCLING_MAP["FVTOCI_EQUITY_FAIR_VALUE_CHANGES"] == "NEVER_RECYCLED"
    assert OCI_RECYCLING_MAP["CASH_FLOW_HEDGE_RESERVE"] == "RECYCLABLE_TO_PNL"
    assert OCI_RECYCLING_MAP["DEFINED_BENEFIT_REMEASUREMENT"] == "NEVER_RECYCLED"


def _test_materiality_thresholds_byte_for_byte():
    assert MATERIALITY_PCT_OF_REVENUE == Decimal("5")
    assert MATERIALITY_PCT_OF_TOTAL_ASSETS == Decimal("1")
    assert MATERIALITY_PCT_OF_EQUITY == Decimal("5")


def _test_complete_set_all_5():
    r = IAS1PresentationEngine.validate_complete_statements_set(
        list(COMPLETE_STATEMENTS_COMPONENTS))
    assert r["complete"] is True


def _test_complete_set_missing():
    r = IAS1PresentationEngine.validate_complete_statements_set(
        ["STATEMENT_OF_FINANCIAL_POSITION",
         "STATEMENT_OF_PROFIT_OR_LOSS_AND_OCI"])
    assert r["complete"] is False
    assert "STATEMENT_OF_CASH_FLOWS" in r["missing"]


def _test_going_concern_standard():
    r = IAS1PresentationEngine.going_concern_assessment(False, False)
    assert r["outcome"] == "GOING_CONCERN_ASSESSED"


def _test_going_concern_significant_uncertainty():
    r = IAS1PresentationEngine.going_concern_assessment(True, False)
    assert r["outcome"] == "SIGNIFICANT_UNCERTAINTY_DISCLOSED"
    assert r["disclosure_required"] is True


def _test_going_concern_alternative_basis():
    """Liquidation intent → not going concern."""
    r = IAS1PresentationEngine.going_concern_assessment(True, True)
    assert r["outcome"] == "NOT_PREPARED_ON_GOING_CONCERN_BASIS"


def _test_going_concern_missing_rule1():
    r = IAS1PresentationEngine.going_concern_assessment(None, False)
    assert r["outcome"] is None


def _test_asset_current_when_any_criterion():
    r = IAS1PresentationEngine.asset_current_classification(
        {"CASH_OR_CASH_EQUIVALENT": True})
    assert r["classification"] == "CURRENT"


def _test_asset_non_current_default():
    r = IAS1PresentationEngine.asset_current_classification({})
    assert r["classification"] == "NON_CURRENT"


def _test_liability_current_when_due_in_12m():
    r = IAS1PresentationEngine.liability_current_classification(
        {"DUE_WITHIN_12_MONTHS": True})
    assert r["classification"] == "CURRENT"


def _test_liability_current_no_unconditional_right_to_defer():
    """Critical IAS 1.69(d): no unconditional right to defer → CURRENT."""
    r = IAS1PresentationEngine.liability_current_classification(
        {"NO_UNCONDITIONAL_RIGHT_TO_DEFER_BEYOND_12M": True})
    assert r["classification"] == "CURRENT"


def _test_liability_non_current_default():
    r = IAS1PresentationEngine.liability_current_classification({})
    assert r["classification"] == "NON_CURRENT"


def _test_oci_revaluation_never_recycled():
    """IAS 16 revaluation surplus is NEVER recycled to P&L."""
    r = IAS1PresentationEngine.oci_classification("REVALUATION_SURPLUS")
    assert r["classification"] == "NEVER_RECYCLED"
    assert r["recyclable"] is False


def _test_oci_fvtoci_debt_recyclable():
    """IFRS 9 FVTOCI debt: fair value changes recycle on disposal."""
    r = IAS1PresentationEngine.oci_classification("FVTOCI_DEBT_FAIR_VALUE_CHANGES")
    assert r["classification"] == "RECYCLABLE_TO_PNL"
    assert r["recyclable"] is True


def _test_oci_fvtoci_equity_never_recycled():
    """IFRS 9.5.7.5: FVTOCI equity election → NEVER recycled."""
    r = IAS1PresentationEngine.oci_classification("FVTOCI_EQUITY_FAIR_VALUE_CHANGES")
    assert r["classification"] == "NEVER_RECYCLED"


def _test_oci_cfh_recyclable():
    """Cash flow hedge reserve → recycled on hedged transaction."""
    r = IAS1PresentationEngine.oci_classification("CASH_FLOW_HEDGE_RESERVE")
    assert r["classification"] == "RECYCLABLE_TO_PNL"


def _test_oci_db_remeasurement_never_recycled():
    """IAS 19R: actuarial gains/losses NEVER recycled."""
    r = IAS1PresentationEngine.oci_classification("DEFINED_BENEFIT_REMEASUREMENT")
    assert r["classification"] == "NEVER_RECYCLED"


def _test_oci_unknown_rule6():
    r = IAS1PresentationEngine.oci_classification("WEIRD")
    assert r["computed"] is False


def _test_materiality_revenue_above():
    """Item 600K vs revenue 10M = 6% > 5% → material."""
    r = IAS1PresentationEngine.materiality_test(
        Decimal("600000"), "REVENUE", Decimal("10000000"))
    assert r["material"] is True


def _test_materiality_revenue_at_threshold():
    """Exactly 5% → NOT material (strict >)."""
    r = IAS1PresentationEngine.materiality_test(
        Decimal("500000"), "REVENUE", Decimal("10000000"))
    assert r["material"] is False


def _test_materiality_total_assets_threshold():
    """1% threshold for total assets — much stricter."""
    r = IAS1PresentationEngine.materiality_test(
        Decimal("1500000"), "TOTAL_ASSETS", Decimal("100000000"))
    # 1.5% > 1% → material
    assert r["material"] is True


def _test_materiality_total_assets_at_threshold():
    """Exactly 1% → NOT material."""
    r = IAS1PresentationEngine.materiality_test(
        Decimal("1000000"), "TOTAL_ASSETS", Decimal("100000000"))
    assert r["material"] is False


def _test_materiality_unknown_base_rule6():
    r = IAS1PresentationEngine.materiality_test(
        Decimal("100000"), "WEIRD", Decimal("1000000"))
    assert r["computed"] is False


def _test_materiality_zero_base_rule6():
    r = IAS1PresentationEngine.materiality_test(
        Decimal("100000"), "REVENUE", Decimal("0"))
    assert r["computed"] is False


def _test_materiality_missing_rule1():
    r = IAS1PresentationEngine.materiality_test(
        None, "REVENUE", Decimal("1000000"))
    assert r["computed"] is False


def self_test() -> bool:
    tests = [
        _test_components_byte_for_byte,
        _test_going_concern_outcomes_byte_for_byte,
        _test_statement_formats_byte_for_byte,
        _test_current_asset_criteria_byte_for_byte,
        _test_current_liability_criteria_byte_for_byte,
        _test_oci_classifications_byte_for_byte,
        _test_oci_line_items_byte_for_byte,
        _test_oci_recycling_map_byte_for_byte,
        _test_materiality_thresholds_byte_for_byte,
        _test_complete_set_all_5,
        _test_complete_set_missing,
        _test_going_concern_standard,
        _test_going_concern_significant_uncertainty,
        _test_going_concern_alternative_basis,
        _test_going_concern_missing_rule1,
        _test_asset_current_when_any_criterion,
        _test_asset_non_current_default,
        _test_liability_current_when_due_in_12m,
        _test_liability_current_no_unconditional_right_to_defer,
        _test_liability_non_current_default,
        _test_oci_revaluation_never_recycled,
        _test_oci_fvtoci_debt_recyclable,
        _test_oci_fvtoci_equity_never_recycled,
        _test_oci_cfh_recyclable,
        _test_oci_db_remeasurement_never_recycled,
        _test_oci_unknown_rule6,
        _test_materiality_revenue_above,
        _test_materiality_revenue_at_threshold,
        _test_materiality_total_assets_threshold,
        _test_materiality_total_assets_at_threshold,
        _test_materiality_unknown_base_rule6,
        _test_materiality_zero_base_rule6,
        _test_materiality_missing_rule1,
    ]
    print("=" * 60)
    print("IAS 1 Presentation Engine — Self-Tests (#111)")
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

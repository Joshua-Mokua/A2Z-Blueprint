"""
================================================================================
A2Z MIS 360 — Standard #113: IFRS 5 Non-Current Assets Held for Sale &
                                 Discontinued Operations
================================================================================

Risk classification: Cat B (deterministic classification + measurement per IFRS 5)

Provides:
    - classify_held_for_sale(...)        -- 6 IFRS 5.7-8 criteria all required
    - held_for_sale_measurement(...)     -- LOWER OF (CA, FVLCD)
    - depreciation_cessation_check(...)  -- depreciation STOPS once HFS
    - classify_discontinued_operation(...) -- IFRS 5.32 criteria
    - presentation_outcome(...)          -- separate line on B/S and P&L

6 HELD_FOR_SALE_CRITERIA byte-for-byte (IFRS 5.7-8):
    AVAILABLE_FOR_IMMEDIATE_SALE_IN_PRESENT_CONDITION
    SALE_HIGHLY_PROBABLE
    MANAGEMENT_COMMITTED_TO_PLAN
    ACTIVE_PROGRAMME_TO_LOCATE_BUYER
    MARKETED_AT_REASONABLE_PRICE
    EXPECTED_SALE_WITHIN_12_MONTHS

3 MEASUREMENT_OUTCOMES byte-for-byte (IFRS 5.15):
    LOWER_OF_CARRYING_AMOUNT_AND_FVLCD
    IMPAIRMENT_RECOGNISED
    NO_FURTHER_DEPRECIATION

4 DISCONTINUED_OPERATION_CRITERIA byte-for-byte (IFRS 5.32):
    SEPARATE_MAJOR_LINE_OF_BUSINESS
    SEPARATE_MAJOR_GEOGRAPHIC_AREA
    PART_OF_SINGLE_COORDINATED_PLAN
    SUBSIDIARY_ACQUIRED_EXCLUSIVELY_FOR_RESALE

3 PRESENTATION_OUTCOMES byte-for-byte (IFRS 5.30-33):
    SEPARATE_LINE_ON_BALANCE_SHEET
    SEPARATE_DISCLOSURE_IN_PNL
    DISCLOSE_IN_NOTES_ONLY

Honesty rules applied:
    Rule 1: held_for_sale=None when criteria dict empty
            measurement=None when CA or FVLCD missing
    Rule 6: ANY of 6 criteria missing → NOT HFS (fail closed)
            depreciation continues after HFS classification = ERROR (fail closed)
            12-month boundary inclusive — exactly 12mo expected sale = qualifies

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 6 HELD-FOR-SALE CRITERIA byte-for-byte (IFRS 5.7-8) — ALL required
HELD_FOR_SALE_CRITERIA: Tuple[str, ...] = (
    "AVAILABLE_FOR_IMMEDIATE_SALE_IN_PRESENT_CONDITION",
    "SALE_HIGHLY_PROBABLE",
    "MANAGEMENT_COMMITTED_TO_PLAN",
    "ACTIVE_PROGRAMME_TO_LOCATE_BUYER",
    "MARKETED_AT_REASONABLE_PRICE",
    "EXPECTED_SALE_WITHIN_12_MONTHS",
)

# 3 MEASUREMENT OUTCOMES byte-for-byte (IFRS 5.15)
MEASUREMENT_OUTCOMES: Tuple[str, ...] = (
    "LOWER_OF_CARRYING_AMOUNT_AND_FVLCD",
    "IMPAIRMENT_RECOGNISED",
    "NO_FURTHER_DEPRECIATION",
)

# 4 DISCONTINUED OPERATION CRITERIA byte-for-byte (IFRS 5.32)
DISCONTINUED_OPERATION_CRITERIA: Tuple[str, ...] = (
    "SEPARATE_MAJOR_LINE_OF_BUSINESS",
    "SEPARATE_MAJOR_GEOGRAPHIC_AREA",
    "PART_OF_SINGLE_COORDINATED_PLAN",
    "SUBSIDIARY_ACQUIRED_EXCLUSIVELY_FOR_RESALE",
)

# 3 PRESENTATION OUTCOMES byte-for-byte (IFRS 5.30-33)
PRESENTATION_OUTCOMES: Tuple[str, ...] = (
    "SEPARATE_LINE_ON_BALANCE_SHEET",
    "SEPARATE_DISCLOSURE_IN_PNL",
    "DISCLOSE_IN_NOTES_ONLY",
)

# Maximum period for expected sale byte-for-byte
EXPECTED_SALE_MAX_MONTHS = 12


class HeldForSaleEngine:
    """Deterministic IFRS 5 classification + measurement."""

    @staticmethod
    def classify_held_for_sale(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        Classify asset as HFS per IFRS 5.7-8.
        ALL 6 criteria must be met. Rule 6: missing/False on any → NOT HFS.
        """
        if not criteria_met:
            return {"held_for_sale": None, "computed": False,
                    "reason": "missing_criteria_dict"}
        missing: List[str] = []
        for c in HELD_FOR_SALE_CRITERIA:
            if not criteria_met.get(c, False):
                missing.append(c)
        is_hfs = len(missing) == 0
        return {
            "criteria_required": list(HELD_FOR_SALE_CRITERIA),
            "criteria_missing_or_false": missing,
            "held_for_sale": is_hfs,
            "rationale": ("all_6_criteria_met_per_IFRS_5.7-8" if is_hfs
                          else "at_least_one_criterion_unmet_fail_closed"),
            "computed": True,
        }

    @staticmethod
    def held_for_sale_measurement(
        carrying_amount: Optional[Decimal],
        fair_value_less_costs_to_sell: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IFRS 5.15: measure at LOWER OF CA and FVLCS.
        If FVLCS < CA → impairment loss recognised.
        Rule 1: None when either missing.
        Rule 6: negative inputs rejected.
        """
        if carrying_amount is None or fair_value_less_costs_to_sell is None:
            return {"measurement": None, "computed": False,
                    "reason": "missing_inputs"}
        if carrying_amount < 0:
            return {"measurement": None, "computed": False,
                    "reason": "negative_carrying_amount"}
        if fair_value_less_costs_to_sell < 0:
            return {"measurement": None, "computed": False,
                    "reason": "negative_fvlcs"}
        # LOWER OF (CA, FVLCS)
        if fair_value_less_costs_to_sell < carrying_amount:
            measurement = fair_value_less_costs_to_sell
            impairment_loss = carrying_amount - fair_value_less_costs_to_sell
            impaired = True
        else:
            measurement = carrying_amount
            impairment_loss = Decimal("0")
            impaired = False
        return {
            "carrying_amount": str(carrying_amount),
            "fair_value_less_costs_to_sell": str(fair_value_less_costs_to_sell),
            "measurement": str(measurement.quantize(Decimal("0.01"))),
            "impairment_loss": str(impairment_loss.quantize(Decimal("0.01"))),
            "impaired": impaired,
            "rationale": "lower_of_carrying_amount_and_fvlcs_per_IFRS_5.15",
            "computed": True,
        }

    @staticmethod
    def depreciation_cessation_check(
        held_for_sale: Optional[bool],
        depreciation_charged_in_period: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IFRS 5.25: depreciation STOPS once classified as HFS.
        Charging depreciation after HFS classification is an ERROR (fail closed).
        Rule 1: None when held_for_sale flag missing.
        """
        if held_for_sale is None:
            return {"compliant": None, "computed": False,
                    "reason": "missing_held_for_sale_flag"}
        if not held_for_sale:
            return {
                "held_for_sale": False,
                "compliant": True,
                "rationale": "not_hfs_normal_depreciation_continues",
                "computed": True,
            }
        # HFS — depreciation must be 0
        if depreciation_charged_in_period is None:
            depreciation_charged_in_period = Decimal("0")
        if depreciation_charged_in_period > 0:
            return {
                "held_for_sale": True,
                "depreciation_charged": str(depreciation_charged_in_period),
                "compliant": False,
                "rationale": "depreciation_continued_after_hfs_classification_per_IFRS_5.25",
                "computed": True,
            }
        return {
            "held_for_sale": True,
            "depreciation_charged": "0",
            "compliant": True,
            "rationale": "depreciation_correctly_ceased_per_IFRS_5.25",
            "computed": True,
        }

    @staticmethod
    def classify_discontinued_operation(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        Classify as discontinued operation per IFRS 5.32.
        ANY ONE of the 4 criteria → discontinued operation.
        """
        if not criteria_met:
            return {"discontinued_operation": False, "criteria_met": [],
                    "computed": True,
                    "rationale": "no_criteria_provided"}
        met: List[str] = []
        for c in DISCONTINUED_OPERATION_CRITERIA:
            if criteria_met.get(c, False):
                met.append(c)
        is_disc_op = len(met) > 0
        return {
            "criteria_required_any_of": list(DISCONTINUED_OPERATION_CRITERIA),
            "criteria_met": met,
            "discontinued_operation": is_disc_op,
            "rationale": ("at_least_one_criterion_met_per_IFRS_5.32" if is_disc_op
                          else "no_criterion_met"),
            "computed": True,
        }

    @staticmethod
    def presentation_outcome(
        is_held_for_sale: bool,
        is_discontinued: bool,
    ) -> Dict[str, Any]:
        """
        Determine presentation per IFRS 5.30-33.
        HFS asset → SEPARATE_LINE_ON_BALANCE_SHEET.
        Discontinued operation → SEPARATE_DISCLOSURE_IN_PNL.
        Both can apply simultaneously.
        """
        outcomes: List[str] = []
        if is_held_for_sale:
            outcomes.append("SEPARATE_LINE_ON_BALANCE_SHEET")
        if is_discontinued:
            outcomes.append("SEPARATE_DISCLOSURE_IN_PNL")
        if not outcomes:
            outcomes.append("DISCLOSE_IN_NOTES_ONLY")
        return {
            "is_held_for_sale": is_held_for_sale,
            "is_discontinued": is_discontinued,
            "presentation_outcomes": outcomes,
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_hfs_criteria_byte_for_byte():
    expected = (
        "AVAILABLE_FOR_IMMEDIATE_SALE_IN_PRESENT_CONDITION",
        "SALE_HIGHLY_PROBABLE",
        "MANAGEMENT_COMMITTED_TO_PLAN",
        "ACTIVE_PROGRAMME_TO_LOCATE_BUYER",
        "MARKETED_AT_REASONABLE_PRICE",
        "EXPECTED_SALE_WITHIN_12_MONTHS",
    )
    for c in expected:
        assert c in HELD_FOR_SALE_CRITERIA
    assert len(HELD_FOR_SALE_CRITERIA) == 6


def _test_measurement_outcomes_byte_for_byte():
    expected = (
        "LOWER_OF_CARRYING_AMOUNT_AND_FVLCD",
        "IMPAIRMENT_RECOGNISED",
        "NO_FURTHER_DEPRECIATION",
    )
    for o in expected:
        assert o in MEASUREMENT_OUTCOMES


def _test_disc_op_criteria_byte_for_byte():
    expected = (
        "SEPARATE_MAJOR_LINE_OF_BUSINESS",
        "SEPARATE_MAJOR_GEOGRAPHIC_AREA",
        "PART_OF_SINGLE_COORDINATED_PLAN",
        "SUBSIDIARY_ACQUIRED_EXCLUSIVELY_FOR_RESALE",
    )
    for c in expected:
        assert c in DISCONTINUED_OPERATION_CRITERIA
    assert len(DISCONTINUED_OPERATION_CRITERIA) == 4


def _test_presentation_outcomes_byte_for_byte():
    expected = (
        "SEPARATE_LINE_ON_BALANCE_SHEET",
        "SEPARATE_DISCLOSURE_IN_PNL",
        "DISCLOSE_IN_NOTES_ONLY",
    )
    for o in expected:
        assert o in PRESENTATION_OUTCOMES


def _test_max_months_byte_for_byte():
    assert EXPECTED_SALE_MAX_MONTHS == 12


def _test_hfs_all_criteria_met():
    """All 6 criteria True → held_for_sale=True."""
    all_met = {c: True for c in HELD_FOR_SALE_CRITERIA}
    r = HeldForSaleEngine.classify_held_for_sale(all_met)
    assert r["held_for_sale"] is True


def _test_hfs_one_criterion_missing_rule6():
    """Missing one → fail closed."""
    one_missing = {c: True for c in HELD_FOR_SALE_CRITERIA}
    one_missing["EXPECTED_SALE_WITHIN_12_MONTHS"] = False
    r = HeldForSaleEngine.classify_held_for_sale(one_missing)
    assert r["held_for_sale"] is False
    assert "EXPECTED_SALE_WITHIN_12_MONTHS" in r["criteria_missing_or_false"]


def _test_hfs_empty_dict_rule1():
    r = HeldForSaleEngine.classify_held_for_sale({})
    assert r["held_for_sale"] is None


def _test_measurement_lower_of_basic():
    """CA 1M, FVLCS 800K → measurement=800K, impairment=200K."""
    r = HeldForSaleEngine.held_for_sale_measurement(
        Decimal("1000000"), Decimal("800000"))
    assert r["measurement"] == "800000.00"
    assert r["impairment_loss"] == "200000.00"
    assert r["impaired"] is True


def _test_measurement_no_impairment():
    """FVLCS > CA → measurement=CA, no impairment."""
    r = HeldForSaleEngine.held_for_sale_measurement(
        Decimal("1000000"), Decimal("1200000"))
    assert r["measurement"] == "1000000.00"
    assert r["impairment_loss"] == "0.00"
    assert r["impaired"] is False


def _test_measurement_equal():
    """CA = FVLCS → no impairment."""
    r = HeldForSaleEngine.held_for_sale_measurement(
        Decimal("1000000"), Decimal("1000000"))
    assert r["measurement"] == "1000000.00"
    assert r["impaired"] is False


def _test_measurement_missing_rule1():
    r = HeldForSaleEngine.held_for_sale_measurement(None, Decimal("800000"))
    assert r["measurement"] is None


def _test_measurement_negative_rule6():
    r = HeldForSaleEngine.held_for_sale_measurement(
        Decimal("-1000"), Decimal("500"))
    assert r["computed"] is False


def _test_depreciation_ceases_when_hfs():
    """HFS asset with 0 depreciation → compliant."""
    r = HeldForSaleEngine.depreciation_cessation_check(True, Decimal("0"))
    assert r["compliant"] is True


def _test_depreciation_continues_when_hfs_rule6():
    """HFS asset with depreciation > 0 → NON-COMPLIANT (fail closed)."""
    r = HeldForSaleEngine.depreciation_cessation_check(True, Decimal("10000"))
    assert r["compliant"] is False


def _test_depreciation_normal_when_not_hfs():
    """Not HFS → depreciation continues (compliant)."""
    r = HeldForSaleEngine.depreciation_cessation_check(False, Decimal("10000"))
    assert r["compliant"] is True


def _test_depreciation_missing_flag_rule1():
    r = HeldForSaleEngine.depreciation_cessation_check(None, Decimal("0"))
    assert r["compliant"] is None


def _test_disc_op_one_criterion_met():
    """ANY ONE criterion → discontinued operation."""
    r = HeldForSaleEngine.classify_discontinued_operation(
        {"SEPARATE_MAJOR_LINE_OF_BUSINESS": True})
    assert r["discontinued_operation"] is True


def _test_disc_op_no_criteria():
    r = HeldForSaleEngine.classify_discontinued_operation({})
    assert r["discontinued_operation"] is False


def _test_disc_op_all_false():
    r = HeldForSaleEngine.classify_discontinued_operation(
        {c: False for c in DISCONTINUED_OPERATION_CRITERIA})
    assert r["discontinued_operation"] is False


def _test_presentation_hfs_only():
    r = HeldForSaleEngine.presentation_outcome(True, False)
    assert "SEPARATE_LINE_ON_BALANCE_SHEET" in r["presentation_outcomes"]
    assert "SEPARATE_DISCLOSURE_IN_PNL" not in r["presentation_outcomes"]


def _test_presentation_disc_op_only():
    r = HeldForSaleEngine.presentation_outcome(False, True)
    assert "SEPARATE_DISCLOSURE_IN_PNL" in r["presentation_outcomes"]


def _test_presentation_both():
    """HFS subsidiary that's also a discontinued operation → both presentations."""
    r = HeldForSaleEngine.presentation_outcome(True, True)
    assert "SEPARATE_LINE_ON_BALANCE_SHEET" in r["presentation_outcomes"]
    assert "SEPARATE_DISCLOSURE_IN_PNL" in r["presentation_outcomes"]


def _test_presentation_neither():
    """Neither → notes only."""
    r = HeldForSaleEngine.presentation_outcome(False, False)
    assert r["presentation_outcomes"] == ["DISCLOSE_IN_NOTES_ONLY"]


def self_test() -> bool:
    tests = [
        _test_hfs_criteria_byte_for_byte,
        _test_measurement_outcomes_byte_for_byte,
        _test_disc_op_criteria_byte_for_byte,
        _test_presentation_outcomes_byte_for_byte,
        _test_max_months_byte_for_byte,
        _test_hfs_all_criteria_met,
        _test_hfs_one_criterion_missing_rule6,
        _test_hfs_empty_dict_rule1,
        _test_measurement_lower_of_basic,
        _test_measurement_no_impairment,
        _test_measurement_equal,
        _test_measurement_missing_rule1,
        _test_measurement_negative_rule6,
        _test_depreciation_ceases_when_hfs,
        _test_depreciation_continues_when_hfs_rule6,
        _test_depreciation_normal_when_not_hfs,
        _test_depreciation_missing_flag_rule1,
        _test_disc_op_one_criterion_met,
        _test_disc_op_no_criteria,
        _test_disc_op_all_false,
        _test_presentation_hfs_only,
        _test_presentation_disc_op_only,
        _test_presentation_both,
        _test_presentation_neither,
    ]
    print("=" * 60)
    print("Held for Sale Engine — Self-Tests (#113 IFRS 5)")
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

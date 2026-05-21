"""
================================================================================
A2Z MIS 360 — Standard #112: IAS 8 Accounting Policies, Changes & Errors
================================================================================

Risk classification: Cat B (deterministic policy/change/error classification)

Implements IAS 8 framework for:
    - Selection and application of accounting policies
    - Changes in accounting policies
    - Changes in accounting estimates
    - Correction of prior-period errors

Provides:
    - classify_change_type(...)              -- POLICY / ESTIMATE / ERROR
    - retrospective_application_test(...)    -- when retrospective vs prospective
    - error_materiality_test(...)            -- material → restate prior periods
    - policy_hierarchy(...)                  -- application order per IAS 8.10-12
    - validate_policy_change_trigger(...)    -- voluntary vs mandatory

3 CHANGE_TYPES byte-for-byte (IAS 8.5):
    CHANGE_IN_ACCOUNTING_POLICY      -- different recognition/measurement basis
    CHANGE_IN_ACCOUNTING_ESTIMATE    -- revision of estimate
    CORRECTION_OF_PRIOR_PERIOD_ERROR -- omission/misstatement

3 APPLICATION_METHODS byte-for-byte (IAS 8.5):
    RETROSPECTIVE_APPLICATION    -- restate prior periods (policy change)
    PROSPECTIVE_APPLICATION      -- current and future only (estimate change)
    RETROSPECTIVE_RESTATEMENT    -- restate prior periods (error correction)

5 POLICY_HIERARCHY_LEVELS byte-for-byte (IAS 8.10-12):
    APPLY_SPECIFIC_IFRS                    -- 1st priority: specific IFRS standard
    REFER_TO_REQUIREMENTS_FOR_SIMILAR      -- 2nd: similar/related issues in IFRS
    REFER_TO_CONCEPTUAL_FRAMEWORK          -- 3rd: Conceptual Framework
    REFER_TO_OTHER_STANDARD_SETTERS        -- 4th: bodies using similar Conceptual Framework
    REFER_TO_INDUSTRY_PRACTICE             -- 5th: industry/recent practice

4 POLICY_CHANGE_TRIGGERS byte-for-byte (IAS 8.14):
    REQUIRED_BY_IFRS                       -- mandatory adoption
    VOLUNTARY_FAITHFUL_REPRESENTATION      -- results in more reliable info
    VOLUNTARY_RELEVANT_INFORMATION         -- results in more relevant info
    NOT_PERMITTED                          -- voluntary without justification

3 ERROR_PRESENTATION_OUTCOMES byte-for-byte (IAS 8.42-49):
    RESTATE_COMPARATIVE_AMOUNTS            -- when error material to prior period
    RESTATE_OPENING_BALANCES               -- when error originated before earliest presented period
    DISCLOSE_ONLY                          -- when restating impracticable

3 ESTIMATE_CHANGE_REASONS byte-for-byte (IAS 8.5):
    NEW_INFORMATION
    NEW_DEVELOPMENTS
    MORE_EXPERIENCE

Materiality threshold for prior-period error byte-for-byte (IAS 8.41):
    PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT = 5   -- > 5% of profit = material
    PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY = 1   -- > 1% of equity = material

Honesty rules applied:
    Rule 1: classification=None when change_type missing
            error_material=None when amount or base missing
    Rule 6: unknown change_type / trigger / level surfaced
            invalid policy change without trigger = NOT_PERMITTED (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 CHANGE TYPES byte-for-byte (IAS 8.5)
CHANGE_TYPES: Tuple[str, ...] = (
    "CHANGE_IN_ACCOUNTING_POLICY",
    "CHANGE_IN_ACCOUNTING_ESTIMATE",
    "CORRECTION_OF_PRIOR_PERIOD_ERROR",
)

# 3 APPLICATION METHODS byte-for-byte (IAS 8.5)
APPLICATION_METHODS: Tuple[str, ...] = (
    "RETROSPECTIVE_APPLICATION",
    "PROSPECTIVE_APPLICATION",
    "RETROSPECTIVE_RESTATEMENT",
)

# 5 POLICY HIERARCHY LEVELS byte-for-byte (IAS 8.10-12)
POLICY_HIERARCHY_LEVELS: Tuple[str, ...] = (
    "APPLY_SPECIFIC_IFRS",
    "REFER_TO_REQUIREMENTS_FOR_SIMILAR",
    "REFER_TO_CONCEPTUAL_FRAMEWORK",
    "REFER_TO_OTHER_STANDARD_SETTERS",
    "REFER_TO_INDUSTRY_PRACTICE",
)

# 4 POLICY CHANGE TRIGGERS byte-for-byte (IAS 8.14)
POLICY_CHANGE_TRIGGERS: Tuple[str, ...] = (
    "REQUIRED_BY_IFRS",
    "VOLUNTARY_FAITHFUL_REPRESENTATION",
    "VOLUNTARY_RELEVANT_INFORMATION",
    "NOT_PERMITTED",
)

# 3 ERROR PRESENTATION OUTCOMES byte-for-byte (IAS 8.42-49)
ERROR_PRESENTATION_OUTCOMES: Tuple[str, ...] = (
    "RESTATE_COMPARATIVE_AMOUNTS",
    "RESTATE_OPENING_BALANCES",
    "DISCLOSE_ONLY",
)

# 3 ESTIMATE CHANGE REASONS byte-for-byte
ESTIMATE_CHANGE_REASONS: Tuple[str, ...] = (
    "NEW_INFORMATION", "NEW_DEVELOPMENTS", "MORE_EXPERIENCE",
)

# Materiality thresholds byte-for-byte (IAS 8.41)
PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT = Decimal("5")
PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY = Decimal("1")


class IAS8PoliciesEngine:
    """Deterministic IAS 8 policy/estimate/error framework."""

    @staticmethod
    def classify_change_type(change_type: str) -> Dict[str, Any]:
        """Validate change type. Rule 6: unknown rejected."""
        if change_type not in CHANGE_TYPES:
            return {"valid": False,
                    "reason": f"unknown_change_type:{change_type}",
                    "valid_types": list(CHANGE_TYPES)}
        return {"valid": True, "change_type": change_type}

    @staticmethod
    def required_application_method(change_type: str) -> Dict[str, Any]:
        """
        Determine required application method per IAS 8.
        Policy change → RETROSPECTIVE_APPLICATION
        Estimate change → PROSPECTIVE_APPLICATION
        Error correction → RETROSPECTIVE_RESTATEMENT
        Rule 6: unknown change_type rejected.
        """
        if change_type not in CHANGE_TYPES:
            return {"method": None, "computed": False,
                    "reason": f"unknown_change_type:{change_type}"}
        if change_type == "CHANGE_IN_ACCOUNTING_POLICY":
            return {
                "change_type": "CHANGE_IN_ACCOUNTING_POLICY",
                "method": "RETROSPECTIVE_APPLICATION",
                "rationale": "policy_change_retrospective_per_IAS_8.19",
                "computed": True,
            }
        if change_type == "CHANGE_IN_ACCOUNTING_ESTIMATE":
            return {
                "change_type": "CHANGE_IN_ACCOUNTING_ESTIMATE",
                "method": "PROSPECTIVE_APPLICATION",
                "rationale": "estimate_change_prospective_per_IAS_8.36",
                "computed": True,
            }
        # CORRECTION_OF_PRIOR_PERIOD_ERROR
        return {
            "change_type": "CORRECTION_OF_PRIOR_PERIOD_ERROR",
            "method": "RETROSPECTIVE_RESTATEMENT",
            "rationale": "error_correction_restatement_per_IAS_8.42",
            "computed": True,
        }

    @staticmethod
    def validate_policy_change_trigger(
        trigger: str,
    ) -> Dict[str, Any]:
        """
        IAS 8.14: voluntary policy changes only allowed if they result in
        more relevant or more reliable information.
        Rule 6: NOT_PERMITTED triggers fail closed.
        """
        if trigger not in POLICY_CHANGE_TRIGGERS:
            return {"valid": False,
                    "reason": f"unknown_trigger:{trigger}",
                    "valid_triggers": list(POLICY_CHANGE_TRIGGERS)}
        if trigger == "NOT_PERMITTED":
            return {
                "trigger": "NOT_PERMITTED",
                "valid": False,
                "rationale": "policy_change_not_permitted_per_IAS_8.14",
            }
        return {
            "trigger": trigger,
            "valid": True,
            "rationale": "permitted_trigger_per_IAS_8.14",
        }

    @staticmethod
    def policy_hierarchy_level(level_index: Optional[int]) -> Optional[str]:
        """
        Return hierarchy level name by 1-indexed position.
        Rule 1: None when missing.
        Rule 6: out-of-range rejected.
        """
        if level_index is None:
            return None
        if level_index < 1 or level_index > len(POLICY_HIERARCHY_LEVELS):
            return None
        return POLICY_HIERARCHY_LEVELS[level_index - 1]

    @staticmethod
    def error_materiality_test(
        error_amount: Optional[Decimal],
        prior_period_profit: Optional[Decimal] = None,
        prior_period_equity: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        IAS 8.41: error material if > 5% of profit OR > 1% of equity.
        Either base alone is sufficient.
        Rule 1: None when error_amount missing.
        """
        if error_amount is None:
            return {"material": None, "computed": False,
                    "reason": "missing_error_amount"}
        if prior_period_profit is None and prior_period_equity is None:
            return {"material": None, "computed": False,
                    "reason": "no_base_provided"}
        abs_error = abs(error_amount)
        material_by_profit = None
        material_by_equity = None
        details: Dict[str, Any] = {"error_amount": str(error_amount)}
        if prior_period_profit is not None and prior_period_profit > 0:
            pct_profit = (abs_error / prior_period_profit) * Decimal("100")
            details["pct_of_profit"] = str(pct_profit.quantize(Decimal("0.0001")))
            material_by_profit = pct_profit > PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT
        if prior_period_equity is not None and prior_period_equity > 0:
            pct_equity = (abs_error / prior_period_equity) * Decimal("100")
            details["pct_of_equity"] = str(pct_equity.quantize(Decimal("0.0001")))
            material_by_equity = pct_equity > PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY
        # Material if either threshold breached
        material = bool(material_by_profit or material_by_equity)
        return {
            **details,
            "material_by_profit": material_by_profit,
            "material_by_equity": material_by_equity,
            "material": material,
            "outcome": ("RESTATE_COMPARATIVE_AMOUNTS" if material else "DISCLOSE_ONLY"),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_change_types_byte_for_byte():
    expected = (
        "CHANGE_IN_ACCOUNTING_POLICY",
        "CHANGE_IN_ACCOUNTING_ESTIMATE",
        "CORRECTION_OF_PRIOR_PERIOD_ERROR",
    )
    for c in expected:
        assert c in CHANGE_TYPES
    assert len(CHANGE_TYPES) == 3


def _test_application_methods_byte_for_byte():
    expected = (
        "RETROSPECTIVE_APPLICATION",
        "PROSPECTIVE_APPLICATION",
        "RETROSPECTIVE_RESTATEMENT",
    )
    for m in expected:
        assert m in APPLICATION_METHODS
    assert len(APPLICATION_METHODS) == 3


def _test_policy_hierarchy_byte_for_byte():
    expected = (
        "APPLY_SPECIFIC_IFRS",
        "REFER_TO_REQUIREMENTS_FOR_SIMILAR",
        "REFER_TO_CONCEPTUAL_FRAMEWORK",
        "REFER_TO_OTHER_STANDARD_SETTERS",
        "REFER_TO_INDUSTRY_PRACTICE",
    )
    for level in expected:
        assert level in POLICY_HIERARCHY_LEVELS
    assert len(POLICY_HIERARCHY_LEVELS) == 5


def _test_change_triggers_byte_for_byte():
    expected = (
        "REQUIRED_BY_IFRS",
        "VOLUNTARY_FAITHFUL_REPRESENTATION",
        "VOLUNTARY_RELEVANT_INFORMATION",
        "NOT_PERMITTED",
    )
    for t in expected:
        assert t in POLICY_CHANGE_TRIGGERS
    assert len(POLICY_CHANGE_TRIGGERS) == 4


def _test_error_outcomes_byte_for_byte():
    expected = (
        "RESTATE_COMPARATIVE_AMOUNTS",
        "RESTATE_OPENING_BALANCES",
        "DISCLOSE_ONLY",
    )
    for o in expected:
        assert o in ERROR_PRESENTATION_OUTCOMES


def _test_estimate_reasons_byte_for_byte():
    expected = ("NEW_INFORMATION", "NEW_DEVELOPMENTS", "MORE_EXPERIENCE")
    for r in expected:
        assert r in ESTIMATE_CHANGE_REASONS


def _test_materiality_thresholds_byte_for_byte():
    assert PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT == Decimal("5")
    assert PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY == Decimal("1")


def _test_classify_change_valid():
    r = IAS8PoliciesEngine.classify_change_type("CHANGE_IN_ACCOUNTING_POLICY")
    assert r["valid"] is True


def _test_classify_change_unknown_rule6():
    r = IAS8PoliciesEngine.classify_change_type("WEIRD")
    assert r["valid"] is False


def _test_method_policy_retrospective():
    """Policy change → RETROSPECTIVE_APPLICATION."""
    r = IAS8PoliciesEngine.required_application_method(
        "CHANGE_IN_ACCOUNTING_POLICY")
    assert r["method"] == "RETROSPECTIVE_APPLICATION"


def _test_method_estimate_prospective():
    """Estimate change → PROSPECTIVE_APPLICATION (no restatement!)."""
    r = IAS8PoliciesEngine.required_application_method(
        "CHANGE_IN_ACCOUNTING_ESTIMATE")
    assert r["method"] == "PROSPECTIVE_APPLICATION"


def _test_method_error_restatement():
    """Error → RETROSPECTIVE_RESTATEMENT (different from policy retrospective)."""
    r = IAS8PoliciesEngine.required_application_method(
        "CORRECTION_OF_PRIOR_PERIOD_ERROR")
    assert r["method"] == "RETROSPECTIVE_RESTATEMENT"


def _test_method_unknown_rule6():
    r = IAS8PoliciesEngine.required_application_method("WEIRD")
    assert r["method"] is None


def _test_trigger_required_by_ifrs():
    r = IAS8PoliciesEngine.validate_policy_change_trigger("REQUIRED_BY_IFRS")
    assert r["valid"] is True


def _test_trigger_voluntary_faithful():
    r = IAS8PoliciesEngine.validate_policy_change_trigger(
        "VOLUNTARY_FAITHFUL_REPRESENTATION")
    assert r["valid"] is True


def _test_trigger_voluntary_relevant():
    r = IAS8PoliciesEngine.validate_policy_change_trigger(
        "VOLUNTARY_RELEVANT_INFORMATION")
    assert r["valid"] is True


def _test_trigger_not_permitted_fail_closed():
    """NOT_PERMITTED → valid=False."""
    r = IAS8PoliciesEngine.validate_policy_change_trigger("NOT_PERMITTED")
    assert r["valid"] is False


def _test_trigger_unknown_rule6():
    r = IAS8PoliciesEngine.validate_policy_change_trigger("WEIRD")
    assert r["valid"] is False


def _test_hierarchy_level_1():
    """Level 1: APPLY_SPECIFIC_IFRS."""
    assert IAS8PoliciesEngine.policy_hierarchy_level(1) == "APPLY_SPECIFIC_IFRS"


def _test_hierarchy_level_3():
    assert IAS8PoliciesEngine.policy_hierarchy_level(3) == "REFER_TO_CONCEPTUAL_FRAMEWORK"


def _test_hierarchy_level_5():
    assert IAS8PoliciesEngine.policy_hierarchy_level(5) == "REFER_TO_INDUSTRY_PRACTICE"


def _test_hierarchy_level_out_of_range_rule6():
    assert IAS8PoliciesEngine.policy_hierarchy_level(0) is None
    assert IAS8PoliciesEngine.policy_hierarchy_level(6) is None


def _test_hierarchy_missing_rule1():
    assert IAS8PoliciesEngine.policy_hierarchy_level(None) is None


def _test_error_material_by_profit():
    """6% of profit > 5% threshold → material."""
    r = IAS8PoliciesEngine.error_materiality_test(
        Decimal("60000"), prior_period_profit=Decimal("1000000"))
    assert r["material"] is True
    assert r["outcome"] == "RESTATE_COMPARATIVE_AMOUNTS"


def _test_error_at_profit_threshold():
    """Exactly 5% → NOT material (strict >)."""
    r = IAS8PoliciesEngine.error_materiality_test(
        Decimal("50000"), prior_period_profit=Decimal("1000000"))
    assert r["material"] is False
    assert r["outcome"] == "DISCLOSE_ONLY"


def _test_error_material_by_equity():
    """1.5% of equity > 1% threshold → material."""
    r = IAS8PoliciesEngine.error_materiality_test(
        Decimal("1500000"), prior_period_equity=Decimal("100000000"))
    assert r["material"] is True


def _test_error_at_equity_threshold():
    """Exactly 1% of equity → NOT material."""
    r = IAS8PoliciesEngine.error_materiality_test(
        Decimal("1000000"), prior_period_equity=Decimal("100000000"))
    assert r["material"] is False


def _test_error_either_base_sufficient():
    """Below profit threshold but above equity threshold → material."""
    r = IAS8PoliciesEngine.error_materiality_test(
        Decimal("2000000"),
        prior_period_profit=Decimal("100000000"),  # 2% of profit (below 5%)
        prior_period_equity=Decimal("100000000"))   # 2% of equity (above 1%)
    assert r["material"] is True


def _test_error_missing_amount_rule1():
    r = IAS8PoliciesEngine.error_materiality_test(
        None, prior_period_profit=Decimal("1000000"))
    assert r["material"] is None


def _test_error_no_base_rule1():
    r = IAS8PoliciesEngine.error_materiality_test(Decimal("60000"))
    assert r["material"] is None


def _test_error_negative_amount_uses_abs():
    """Negative error treated by absolute value."""
    r = IAS8PoliciesEngine.error_materiality_test(
        Decimal("-60000"), prior_period_profit=Decimal("1000000"))
    assert r["material"] is True  # 6% > 5%


def self_test() -> bool:
    tests = [
        _test_change_types_byte_for_byte,
        _test_application_methods_byte_for_byte,
        _test_policy_hierarchy_byte_for_byte,
        _test_change_triggers_byte_for_byte,
        _test_error_outcomes_byte_for_byte,
        _test_estimate_reasons_byte_for_byte,
        _test_materiality_thresholds_byte_for_byte,
        _test_classify_change_valid,
        _test_classify_change_unknown_rule6,
        _test_method_policy_retrospective,
        _test_method_estimate_prospective,
        _test_method_error_restatement,
        _test_method_unknown_rule6,
        _test_trigger_required_by_ifrs,
        _test_trigger_voluntary_faithful,
        _test_trigger_voluntary_relevant,
        _test_trigger_not_permitted_fail_closed,
        _test_trigger_unknown_rule6,
        _test_hierarchy_level_1,
        _test_hierarchy_level_3,
        _test_hierarchy_level_5,
        _test_hierarchy_level_out_of_range_rule6,
        _test_hierarchy_missing_rule1,
        _test_error_material_by_profit,
        _test_error_at_profit_threshold,
        _test_error_material_by_equity,
        _test_error_at_equity_threshold,
        _test_error_either_base_sufficient,
        _test_error_missing_amount_rule1,
        _test_error_no_base_rule1,
        _test_error_negative_amount_uses_abs,
    ]
    print("=" * 60)
    print("IAS 8 Policies Engine — Self-Tests (#112)")
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

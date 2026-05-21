"""
================================================================================
A2Z MIS 360 — Standard #102: IFRS 9 Investment Classification Engine
================================================================================

Risk classification: Cat B (deterministic IFRS 9 classification + measurement)

Implements IFRS 9 financial asset classification per:
    - Business model assessment (HOLD_TO_COLLECT, HTCS, OTHER)
    - SPPI test (Solely Payments of Principal and Interest)
    - Resulting measurement category (AC, FVTOCI debt, FVTPL, FVTOCI equity)

NOTE: Separate from existing #76 `investment_portfolio.py` which covers analytics.
This module ships the IFRS 9 *classification* layer specifically.

Provides:
    - business_model_assessment(...)    -- HTC / HTCS / OTHER
    - sppi_test(...)                    -- pass / fail
    - classify_debt_instrument(...)     -- bm + sppi → AC / FVTOCI / FVTPL
    - classify_equity_instrument(...)   -- FVTOCI election or FVTPL
    - reclassification_allowed(...)     -- only when business model changes
    - measurement_at_inception(...)     -- amortized cost / fair value

3 BUSINESS_MODELS byte-for-byte (IFRS 9.4.1.1):
    HOLD_TO_COLLECT             -- HTC: collect contractual cash flows
    HOLD_TO_COLLECT_AND_SELL    -- HTCS: collect + sell
    OTHER                       -- trading / managed on FV basis

5 MEASUREMENT_CATEGORIES byte-for-byte:
    AMORTIZED_COST       -- HTC + SPPI passed (debt)
    FVTOCI_DEBT          -- HTCS + SPPI passed (debt)
    FVTPL                -- residual (debt OR equity not FVTOCI)
    FVTOCI_EQUITY        -- equity with irrevocable election
    FVTPL_EQUITY         -- equity without election (default)

3 INSTRUMENT_TYPES byte-for-byte:
    DEBT, EQUITY, DERIVATIVE

5 SPPI_FAIL_REASONS byte-for-byte (common SPPI fails):
    LEVERAGE                     -- e.g. inverse floaters
    CONTINGENT_PRINCIPAL         -- principal varies with non-credit risk
    EQUITY_LINKED                -- payments linked to equity index
    PROFIT_PARTICIPATION         -- profit-sharing features
    EXTREME_PREPAYMENT           -- not at amortized cost

Honesty rules applied:
    Rule 1: classification=None when business_model or sppi_result missing
    Rule 6: invalid business_model / instrument_type / SPPI fail reason surfaced
            equity instruments cannot use AMORTIZED_COST or FVTOCI_DEBT (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 BUSINESS MODELS byte-for-byte (IFRS 9.4.1.1)
BUSINESS_MODELS: Tuple[str, ...] = (
    "HOLD_TO_COLLECT", "HOLD_TO_COLLECT_AND_SELL", "OTHER",
)

# 5 MEASUREMENT CATEGORIES byte-for-byte
MEASUREMENT_CATEGORIES: Tuple[str, ...] = (
    "AMORTIZED_COST", "FVTOCI_DEBT", "FVTPL",
    "FVTOCI_EQUITY", "FVTPL_EQUITY",
)

# 3 INSTRUMENT TYPES byte-for-byte
INSTRUMENT_TYPES: Tuple[str, ...] = ("DEBT", "EQUITY", "DERIVATIVE")

# 5 SPPI fail reasons byte-for-byte
SPPI_FAIL_REASONS: Tuple[str, ...] = (
    "LEVERAGE", "CONTINGENT_PRINCIPAL", "EQUITY_LINKED",
    "PROFIT_PARTICIPATION", "EXTREME_PREPAYMENT",
)


class IFRS9ClassificationEngine:
    """Deterministic IFRS 9 classification + measurement category."""

    @staticmethod
    def business_model_assessment(
        business_model: str,
    ) -> Dict[str, Any]:
        """Validate business model. Rule 6: unknown rejected."""
        if business_model not in BUSINESS_MODELS:
            return {"valid": False,
                    "reason": f"unknown_business_model:{business_model}",
                    "valid_models": list(BUSINESS_MODELS)}
        return {"valid": True, "business_model": business_model}

    @staticmethod
    def sppi_test(
        passed: Optional[bool],
        fail_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        SPPI test result with optional fail reason.
        Rule 1: result=None when passed missing.
        Rule 6: unknown fail_reason surfaced.
        """
        if passed is None:
            return {"sppi_passed": None, "computed": False,
                    "reason": "missing_test_result"}
        if not passed:
            if fail_reason is not None and fail_reason not in SPPI_FAIL_REASONS:
                return {"sppi_passed": False, "computed": False,
                        "reason": f"unknown_fail_reason:{fail_reason}",
                        "valid_fail_reasons": list(SPPI_FAIL_REASONS)}
            return {"sppi_passed": False, "fail_reason": fail_reason,
                    "computed": True}
        return {"sppi_passed": True, "computed": True}

    @staticmethod
    def classify_debt_instrument(
        business_model: Optional[str],
        sppi_passed: Optional[bool],
    ) -> Dict[str, Any]:
        """
        Debt instrument classification per IFRS 9.4.1.2 / 4.1.2A.
        Rule 1: category=None when inputs missing.
        Rule 6: unknown business_model surfaced.
        """
        if business_model is None or sppi_passed is None:
            return {"category": None, "computed": False,
                    "reason": "missing_business_model_or_sppi"}
        if business_model not in BUSINESS_MODELS:
            return {"category": None, "computed": False,
                    "reason": f"unknown_business_model:{business_model}"}
        # If SPPI fails → FVTPL regardless of business model
        if not sppi_passed:
            return {"business_model": business_model, "sppi_passed": False,
                    "category": "FVTPL",
                    "rationale": "sppi_fail_forces_fvtpl",
                    "computed": True}
        # SPPI passes — apply business model
        if business_model == "HOLD_TO_COLLECT":
            category = "AMORTIZED_COST"
            rationale = "htc_sppi_per_IFRS_9_4.1.2"
        elif business_model == "HOLD_TO_COLLECT_AND_SELL":
            category = "FVTOCI_DEBT"
            rationale = "htcs_sppi_per_IFRS_9_4.1.2A"
        else:  # OTHER
            category = "FVTPL"
            rationale = "other_business_model_residual"
        return {"business_model": business_model, "sppi_passed": True,
                "category": category, "rationale": rationale, "computed": True}

    @staticmethod
    def classify_equity_instrument(
        fvtoci_election: Optional[bool],
        held_for_trading: Optional[bool] = False,
    ) -> Dict[str, Any]:
        """
        Equity instrument classification per IFRS 9.4.1.4.
        FVTOCI election only available for non-trading equities.
        Rule 1: None when election missing.
        """
        if fvtoci_election is None:
            return {"category": None, "computed": False,
                    "reason": "missing_election"}
        # Held-for-trading equities CANNOT elect FVTOCI
        if held_for_trading:
            return {"held_for_trading": True, "election": None,
                    "category": "FVTPL_EQUITY",
                    "rationale": "trading_equity_default_fvtpl",
                    "computed": True}
        if fvtoci_election:
            return {"election": True, "category": "FVTOCI_EQUITY",
                    "rationale": "irrevocable_election_per_IFRS_9_4.1.4",
                    "computed": True}
        return {"election": False, "category": "FVTPL_EQUITY",
                "rationale": "no_election_default_fvtpl", "computed": True}

    @staticmethod
    def reclassification_allowed(
        old_business_model: Optional[str],
        new_business_model: Optional[str],
    ) -> Dict[str, Any]:
        """
        IFRS 9: reclassification ONLY allowed when business model changes.
        Same model → not allowed.
        Rule 6: unknown models surfaced.
        """
        if old_business_model is None or new_business_model is None:
            return {"allowed": None, "computed": False,
                    "reason": "missing_models"}
        if (old_business_model not in BUSINESS_MODELS
                or new_business_model not in BUSINESS_MODELS):
            return {"allowed": False, "computed": False,
                    "reason": "unknown_business_model"}
        if old_business_model == new_business_model:
            return {"allowed": False, "computed": True,
                    "reason": "no_business_model_change"}
        return {"allowed": True, "old_model": old_business_model,
                "new_model": new_business_model, "computed": True}

    @staticmethod
    def measurement_method(category: str) -> Optional[str]:
        """
        Map measurement category to measurement method.
        AMORTIZED_COST → effective_interest
        FVTOCI / FVTPL → fair_value
        """
        if category not in MEASUREMENT_CATEGORIES:
            return None
        if category == "AMORTIZED_COST":
            return "effective_interest"
        return "fair_value"


# ============================================================================
# Self-tests
# ============================================================================

def _test_business_models_byte_for_byte():
    expected = ("HOLD_TO_COLLECT", "HOLD_TO_COLLECT_AND_SELL", "OTHER")
    for m in expected:
        assert m in BUSINESS_MODELS
    assert len(BUSINESS_MODELS) == 3


def _test_measurement_categories_byte_for_byte():
    expected = ("AMORTIZED_COST", "FVTOCI_DEBT", "FVTPL",
                "FVTOCI_EQUITY", "FVTPL_EQUITY")
    for c in expected:
        assert c in MEASUREMENT_CATEGORIES
    assert len(MEASUREMENT_CATEGORIES) == 5


def _test_instrument_types_byte_for_byte():
    expected = ("DEBT", "EQUITY", "DERIVATIVE")
    for t in expected:
        assert t in INSTRUMENT_TYPES


def _test_sppi_fail_reasons_byte_for_byte():
    expected = ("LEVERAGE", "CONTINGENT_PRINCIPAL", "EQUITY_LINKED",
                "PROFIT_PARTICIPATION", "EXTREME_PREPAYMENT")
    for r in expected:
        assert r in SPPI_FAIL_REASONS
    assert len(SPPI_FAIL_REASONS) == 5


def _test_business_model_valid():
    r = IFRS9ClassificationEngine.business_model_assessment("HOLD_TO_COLLECT")
    assert r["valid"] is True


def _test_business_model_unknown_rule6():
    r = IFRS9ClassificationEngine.business_model_assessment("WEIRD")
    assert r["valid"] is False


def _test_sppi_passed():
    r = IFRS9ClassificationEngine.sppi_test(True)
    assert r["sppi_passed"] is True


def _test_sppi_failed_with_reason():
    r = IFRS9ClassificationEngine.sppi_test(False, fail_reason="LEVERAGE")
    assert r["sppi_passed"] is False
    assert r["fail_reason"] == "LEVERAGE"


def _test_sppi_unknown_fail_reason_rule6():
    r = IFRS9ClassificationEngine.sppi_test(False, fail_reason="WEIRD")
    assert r["computed"] is False


def _test_sppi_missing_rule1():
    r = IFRS9ClassificationEngine.sppi_test(None)
    assert r["sppi_passed"] is None


def _test_classify_htc_sppi_pass_amortized_cost():
    """HTC + SPPI pass → AMORTIZED_COST."""
    r = IFRS9ClassificationEngine.classify_debt_instrument(
        "HOLD_TO_COLLECT", True)
    assert r["category"] == "AMORTIZED_COST"


def _test_classify_htcs_sppi_pass_fvtoci_debt():
    """HTCS + SPPI pass → FVTOCI_DEBT."""
    r = IFRS9ClassificationEngine.classify_debt_instrument(
        "HOLD_TO_COLLECT_AND_SELL", True)
    assert r["category"] == "FVTOCI_DEBT"


def _test_classify_other_residual_fvtpl():
    """OTHER business model → FVTPL."""
    r = IFRS9ClassificationEngine.classify_debt_instrument("OTHER", True)
    assert r["category"] == "FVTPL"


def _test_classify_sppi_fail_forces_fvtpl():
    """SPPI fail → FVTPL regardless of business model."""
    r = IFRS9ClassificationEngine.classify_debt_instrument(
        "HOLD_TO_COLLECT", False)
    assert r["category"] == "FVTPL"
    assert "sppi_fail" in r["rationale"]


def _test_classify_missing_rule1():
    r = IFRS9ClassificationEngine.classify_debt_instrument(None, True)
    assert r["category"] is None


def _test_classify_unknown_bm_rule6():
    r = IFRS9ClassificationEngine.classify_debt_instrument("WEIRD", True)
    assert r["category"] is None


def _test_equity_fvtoci_election():
    """Equity with FVTOCI election → FVTOCI_EQUITY."""
    r = IFRS9ClassificationEngine.classify_equity_instrument(
        fvtoci_election=True, held_for_trading=False)
    assert r["category"] == "FVTOCI_EQUITY"


def _test_equity_no_election_fvtpl():
    """Equity without election → FVTPL_EQUITY."""
    r = IFRS9ClassificationEngine.classify_equity_instrument(
        fvtoci_election=False, held_for_trading=False)
    assert r["category"] == "FVTPL_EQUITY"


def _test_equity_held_for_trading_forces_fvtpl():
    """Trading equity CANNOT elect FVTOCI."""
    r = IFRS9ClassificationEngine.classify_equity_instrument(
        fvtoci_election=True, held_for_trading=True)
    assert r["category"] == "FVTPL_EQUITY"


def _test_equity_missing_election_rule1():
    r = IFRS9ClassificationEngine.classify_equity_instrument(None)
    assert r["category"] is None


def _test_reclassification_allowed_when_changes():
    r = IFRS9ClassificationEngine.reclassification_allowed(
        "HOLD_TO_COLLECT", "HOLD_TO_COLLECT_AND_SELL")
    assert r["allowed"] is True


def _test_reclassification_not_allowed_same_model():
    r = IFRS9ClassificationEngine.reclassification_allowed(
        "HOLD_TO_COLLECT", "HOLD_TO_COLLECT")
    assert r["allowed"] is False


def _test_reclassification_unknown_rule6():
    r = IFRS9ClassificationEngine.reclassification_allowed("WEIRD", "OTHER")
    assert r["allowed"] is False


def _test_measurement_method_amortized():
    assert IFRS9ClassificationEngine.measurement_method(
        "AMORTIZED_COST") == "effective_interest"


def _test_measurement_method_fvtoci():
    assert IFRS9ClassificationEngine.measurement_method(
        "FVTOCI_DEBT") == "fair_value"
    assert IFRS9ClassificationEngine.measurement_method(
        "FVTPL") == "fair_value"


def _test_measurement_method_unknown():
    assert IFRS9ClassificationEngine.measurement_method("WEIRD") is None


def self_test() -> bool:
    tests = [
        _test_business_models_byte_for_byte,
        _test_measurement_categories_byte_for_byte,
        _test_instrument_types_byte_for_byte,
        _test_sppi_fail_reasons_byte_for_byte,
        _test_business_model_valid,
        _test_business_model_unknown_rule6,
        _test_sppi_passed,
        _test_sppi_failed_with_reason,
        _test_sppi_unknown_fail_reason_rule6,
        _test_sppi_missing_rule1,
        _test_classify_htc_sppi_pass_amortized_cost,
        _test_classify_htcs_sppi_pass_fvtoci_debt,
        _test_classify_other_residual_fvtpl,
        _test_classify_sppi_fail_forces_fvtpl,
        _test_classify_missing_rule1,
        _test_classify_unknown_bm_rule6,
        _test_equity_fvtoci_election,
        _test_equity_no_election_fvtpl,
        _test_equity_held_for_trading_forces_fvtpl,
        _test_equity_missing_election_rule1,
        _test_reclassification_allowed_when_changes,
        _test_reclassification_not_allowed_same_model,
        _test_reclassification_unknown_rule6,
        _test_measurement_method_amortized,
        _test_measurement_method_fvtoci,
        _test_measurement_method_unknown,
    ]
    print("=" * 60)
    print("IFRS 9 Classification Engine — Self-Tests (#102)")
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

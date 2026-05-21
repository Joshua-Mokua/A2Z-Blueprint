"""
================================================================================
A2Z MIS 360 — Standard #93: Strategic Planning / Budget vs Actual / Forecasting
================================================================================

Risk classification: Cat B (deterministic budget variance + forecast computation)

Provides:
    - variance(...)                     -- absolute + pct variance with classification
    - variance_tier(...)                -- GREEN/AMBER/RED tiering
    - forecast(...)                     -- 3 deterministic methods (no ML)
    - validate_budget_state(...)        -- budget cycle state machine
    - reforecast_trigger(...)           -- trigger detection

5 BUDGET_LINE_CATEGORIES byte-for-byte:
    REVENUE, OPEX, NPAT, CAPEX, BALANCE_SHEET_GROWTH

3 VARIANCE_DIRECTIONS byte-for-byte:
    FAVORABLE, UNFAVORABLE, NEUTRAL

3 VARIANCE_TIERS byte-for-byte (absolute pct deviation):
    GREEN  < 5%
    AMBER  5% to 10%
    RED    > 10%

3 FORECAST_METHODS byte-for-byte:
    STRAIGHT_LINE   -- (actual_ytd / months_elapsed) × 12
    RUN_RATE        -- last 3-month average × remaining months + ytd actual
    SEASONALLY_ADJUSTED -- apply seasonal index to remaining months

5 BUDGET_CYCLE_STATES byte-for-byte:
    DRAFT, REVIEW, BOARD_APPROVED, IN_EXECUTION, CLOSED

ALLOWED_BUDGET_TRANSITIONS byte-for-byte:
    DRAFT          → REVIEW
    REVIEW         → BOARD_APPROVED, DRAFT
    BOARD_APPROVED → IN_EXECUTION
    IN_EXECUTION   → CLOSED
    CLOSED         → ()  terminal

Reforecast trigger thresholds byte-for-byte:
    QUARTERLY_REFORECAST_MONTHS = 3
    DEVIATION_REFORECAST_PCT = 10  -- variance ≥ ±10% triggers reforecast

Variance "favorable" rule:
    REVENUE / NPAT / BALANCE_SHEET_GROWTH: actual > budget = FAVORABLE
    OPEX / CAPEX:                          actual < budget = FAVORABLE

Honesty rules applied:
    Rule 1: variance_pct=None when budget=0 (denominator zero)
    Rule 6: invalid budget state transitions REJECTED (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, Optional, Tuple, List

getcontext().prec = 28

# 5 BUDGET LINE CATEGORIES byte-for-byte
BUDGET_LINE_CATEGORIES: Tuple[str, ...] = (
    "REVENUE", "OPEX", "NPAT", "CAPEX", "BALANCE_SHEET_GROWTH",
)

# 3 VARIANCE DIRECTIONS byte-for-byte
VARIANCE_DIRECTIONS: Tuple[str, ...] = ("FAVORABLE", "UNFAVORABLE", "NEUTRAL")

# 3 VARIANCE TIERS byte-for-byte
VARIANCE_TIERS: Tuple[str, ...] = ("GREEN", "AMBER", "RED")

# Variance tier thresholds (absolute pct deviation) byte-for-byte
GREEN_VARIANCE_THRESHOLD_PCT = Decimal("5")
AMBER_VARIANCE_THRESHOLD_PCT = Decimal("10")

# 3 FORECAST METHODS byte-for-byte
FORECAST_METHODS: Tuple[str, ...] = (
    "STRAIGHT_LINE", "RUN_RATE", "SEASONALLY_ADJUSTED",
)

# 5 BUDGET CYCLE STATES byte-for-byte
BUDGET_CYCLE_STATES: Tuple[str, ...] = (
    "DRAFT", "REVIEW", "BOARD_APPROVED", "IN_EXECUTION", "CLOSED",
)

# State machine transitions byte-for-byte
ALLOWED_BUDGET_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT": ("REVIEW",),
    "REVIEW": ("BOARD_APPROVED", "DRAFT"),
    "BOARD_APPROVED": ("IN_EXECUTION",),
    "IN_EXECUTION": ("CLOSED",),
    "CLOSED": (),
}

# Categories where actual > budget = FAVORABLE
INCOME_LIKE_CATEGORIES: Tuple[str, ...] = (
    "REVENUE", "NPAT", "BALANCE_SHEET_GROWTH",
)
# Categories where actual < budget = FAVORABLE
EXPENSE_LIKE_CATEGORIES: Tuple[str, ...] = ("OPEX", "CAPEX")

# Reforecast trigger thresholds byte-for-byte
QUARTERLY_REFORECAST_MONTHS = 3
DEVIATION_REFORECAST_PCT = Decimal("10")


class StrategicPlanningEngine:
    """Deterministic budget variance + forecast computation."""

    @staticmethod
    def variance(
        category: str,
        budget: Optional[Decimal],
        actual: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Absolute + pct variance with FAVORABLE/UNFAVORABLE classification.
        Rule 1: variance_pct=None when budget is zero or missing.
        Rule 6: unknown category surfaced.
        """
        if category not in BUDGET_LINE_CATEGORIES:
            return {
                "variance": None, "variance_pct": None,
                "direction": None, "computed": False,
                "reason": f"unknown_category:{category}",
                "valid_categories": list(BUDGET_LINE_CATEGORIES),
            }
        if budget is None or actual is None:
            return {
                "category": category,
                "variance": None, "variance_pct": None,
                "direction": None, "computed": False,
                "reason": "missing_budget_or_actual",
            }

        # Absolute variance = actual - budget
        abs_var = actual - budget

        # Percent variance: Rule 1 None when budget zero
        if budget == 0:
            pct_var = None
        else:
            pct_var = (abs_var / budget) * Decimal("100")

        # Direction depends on category type
        if category in INCOME_LIKE_CATEGORIES:
            if abs_var > 0:
                direction = "FAVORABLE"
            elif abs_var < 0:
                direction = "UNFAVORABLE"
            else:
                direction = "NEUTRAL"
        else:  # EXPENSE_LIKE
            if abs_var < 0:
                direction = "FAVORABLE"  # under-spend
            elif abs_var > 0:
                direction = "UNFAVORABLE"
            else:
                direction = "NEUTRAL"

        return {
            "category": category,
            "budget": str(budget),
            "actual": str(actual),
            "variance": str(abs_var),
            "variance_pct": (None if pct_var is None
                             else str(pct_var.quantize(Decimal("0.01")))),
            "direction": direction,
            "computed": True,
        }

    @staticmethod
    def variance_tier(variance_pct: Optional[Decimal]) -> Optional[str]:
        """
        Tier the absolute variance pct.
        Rule 1: None passes through.
        """
        if variance_pct is None:
            return None
        abs_pct = abs(variance_pct)
        if abs_pct < GREEN_VARIANCE_THRESHOLD_PCT:
            return "GREEN"
        if abs_pct <= AMBER_VARIANCE_THRESHOLD_PCT:
            return "AMBER"
        return "RED"

    @staticmethod
    def forecast(
        method: str,
        actual_ytd: Optional[Decimal],
        months_elapsed: int,
        total_months: int = 12,
        last_3mo_avg: Optional[Decimal] = None,
        seasonal_indices: Optional[List[Decimal]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic full-year forecast.
        Rule 1: forecast=None when inputs incomplete.
        Rule 6: unknown method surfaced.
        """
        if method not in FORECAST_METHODS:
            return {
                "forecast": None, "method": method, "computed": False,
                "reason": f"unknown_method:{method}",
                "valid_methods": list(FORECAST_METHODS),
            }
        if actual_ytd is None or months_elapsed <= 0 or total_months <= 0:
            return {
                "forecast": None, "method": method, "computed": False,
                "reason": "invalid_inputs",
            }
        if months_elapsed > total_months:
            return {
                "forecast": None, "method": method, "computed": False,
                "reason": "months_elapsed_gt_total",
            }

        remaining_months = total_months - months_elapsed

        if method == "STRAIGHT_LINE":
            # (actual_ytd / months_elapsed) × total_months
            run_rate_per_month = actual_ytd / Decimal(months_elapsed)
            forecast_value = run_rate_per_month * Decimal(total_months)
        elif method == "RUN_RATE":
            if last_3mo_avg is None:
                return {
                    "forecast": None, "method": method, "computed": False,
                    "reason": "missing_last_3mo_avg",
                }
            forecast_value = actual_ytd + (last_3mo_avg * Decimal(remaining_months))
        else:  # SEASONALLY_ADJUSTED
            if seasonal_indices is None or len(seasonal_indices) != total_months:
                return {
                    "forecast": None, "method": method, "computed": False,
                    "reason": "missing_or_invalid_seasonal_indices",
                }
            ytd_seasonal_sum = sum(seasonal_indices[:months_elapsed])
            if ytd_seasonal_sum == 0:
                return {
                    "forecast": None, "method": method, "computed": False,
                    "reason": "zero_ytd_seasonal_sum",
                }
            full_year_seasonal_sum = sum(seasonal_indices)
            forecast_value = actual_ytd * (full_year_seasonal_sum / ytd_seasonal_sum)

        return {
            "method": method,
            "actual_ytd": str(actual_ytd),
            "months_elapsed": months_elapsed,
            "remaining_months": remaining_months,
            "forecast": str(forecast_value.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def validate_budget_state_transition(
        from_state: str,
        to_state: str,
    ) -> Dict[str, Any]:
        """Rule 6: invalid transitions rejected."""
        if from_state not in BUDGET_CYCLE_STATES:
            return {"allowed": False, "reason": f"unknown_from_state:{from_state}"}
        if to_state not in BUDGET_CYCLE_STATES:
            return {"allowed": False, "reason": f"unknown_to_state:{to_state}"}
        allowed_next = ALLOWED_BUDGET_TRANSITIONS.get(from_state, ())
        return {
            "from_state": from_state,
            "to_state": to_state,
            "allowed": to_state in allowed_next,
            "allowed_next_states": list(allowed_next),
        }

    @staticmethod
    def reforecast_trigger(
        months_since_last_forecast: int,
        max_variance_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """Detect reforecast triggers: quarterly cadence OR variance breach."""
        triggers = []
        if months_since_last_forecast >= QUARTERLY_REFORECAST_MONTHS:
            triggers.append("QUARTERLY_CADENCE")
        if max_variance_pct is not None and abs(max_variance_pct) >= DEVIATION_REFORECAST_PCT:
            triggers.append("DEVIATION_THRESHOLD")
        return {
            "months_since_last_forecast": months_since_last_forecast,
            "max_variance_pct": (None if max_variance_pct is None
                                  else str(max_variance_pct)),
            "quarterly_threshold_months": QUARTERLY_REFORECAST_MONTHS,
            "deviation_threshold_pct": str(DEVIATION_REFORECAST_PCT),
            "triggers": triggers,
            "should_reforecast": len(triggers) > 0,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_categories_byte_for_byte():
    expected = ("REVENUE", "OPEX", "NPAT", "CAPEX", "BALANCE_SHEET_GROWTH")
    for c in expected:
        assert c in BUDGET_LINE_CATEGORIES
    assert len(BUDGET_LINE_CATEGORIES) == 5


def _test_directions_byte_for_byte():
    expected = ("FAVORABLE", "UNFAVORABLE", "NEUTRAL")
    for d in expected:
        assert d in VARIANCE_DIRECTIONS


def _test_tiers_byte_for_byte():
    expected = ("GREEN", "AMBER", "RED")
    for t in expected:
        assert t in VARIANCE_TIERS


def _test_thresholds_byte_for_byte():
    assert GREEN_VARIANCE_THRESHOLD_PCT == Decimal("5")
    assert AMBER_VARIANCE_THRESHOLD_PCT == Decimal("10")


def _test_methods_byte_for_byte():
    expected = ("STRAIGHT_LINE", "RUN_RATE", "SEASONALLY_ADJUSTED")
    for m in expected:
        assert m in FORECAST_METHODS


def _test_states_byte_for_byte():
    expected = ("DRAFT", "REVIEW", "BOARD_APPROVED", "IN_EXECUTION", "CLOSED")
    for s in expected:
        assert s in BUDGET_CYCLE_STATES
    assert len(BUDGET_CYCLE_STATES) == 5


def _test_transitions_byte_for_byte():
    assert ALLOWED_BUDGET_TRANSITIONS["DRAFT"] == ("REVIEW",)
    assert "BOARD_APPROVED" in ALLOWED_BUDGET_TRANSITIONS["REVIEW"]
    assert "DRAFT" in ALLOWED_BUDGET_TRANSITIONS["REVIEW"]
    assert ALLOWED_BUDGET_TRANSITIONS["BOARD_APPROVED"] == ("IN_EXECUTION",)
    assert ALLOWED_BUDGET_TRANSITIONS["IN_EXECUTION"] == ("CLOSED",)
    assert ALLOWED_BUDGET_TRANSITIONS["CLOSED"] == ()


def _test_reforecast_constants_byte_for_byte():
    assert QUARTERLY_REFORECAST_MONTHS == 3
    assert DEVIATION_REFORECAST_PCT == Decimal("10")


def _test_revenue_favorable():
    """REVENUE actual > budget = FAVORABLE."""
    r = StrategicPlanningEngine.variance("REVENUE", Decimal("100"), Decimal("110"))
    assert r["direction"] == "FAVORABLE"
    assert r["variance"] == "10"
    assert r["variance_pct"] == "10.00"


def _test_revenue_unfavorable():
    r = StrategicPlanningEngine.variance("REVENUE", Decimal("100"), Decimal("90"))
    assert r["direction"] == "UNFAVORABLE"
    assert r["variance_pct"] == "-10.00"


def _test_opex_favorable_underspend():
    """OPEX actual < budget = FAVORABLE."""
    r = StrategicPlanningEngine.variance("OPEX", Decimal("100"), Decimal("90"))
    assert r["direction"] == "FAVORABLE"


def _test_opex_unfavorable_overspend():
    r = StrategicPlanningEngine.variance("OPEX", Decimal("100"), Decimal("110"))
    assert r["direction"] == "UNFAVORABLE"


def _test_capex_favorable_underspend():
    r = StrategicPlanningEngine.variance("CAPEX", Decimal("100"), Decimal("80"))
    assert r["direction"] == "FAVORABLE"


def _test_npat_favorable():
    r = StrategicPlanningEngine.variance("NPAT", Decimal("100"), Decimal("120"))
    assert r["direction"] == "FAVORABLE"


def _test_neutral():
    r = StrategicPlanningEngine.variance("REVENUE", Decimal("100"), Decimal("100"))
    assert r["direction"] == "NEUTRAL"
    assert r["variance"] == "0"


def _test_zero_budget_rule1():
    r = StrategicPlanningEngine.variance("REVENUE", Decimal("0"), Decimal("100"))
    assert r["variance_pct"] is None
    assert r["variance"] == "100"


def _test_unknown_category_rule6():
    r = StrategicPlanningEngine.variance("WEIRD", Decimal("100"), Decimal("110"))
    assert r["computed"] is False


def _test_missing_inputs_rule1():
    r = StrategicPlanningEngine.variance("REVENUE", None, Decimal("100"))
    assert r["computed"] is False


def _test_tier_green():
    """3% deviation < 5% → GREEN."""
    assert StrategicPlanningEngine.variance_tier(Decimal("3")) == "GREEN"
    assert StrategicPlanningEngine.variance_tier(Decimal("-3")) == "GREEN"


def _test_tier_amber():
    """7% deviation in [5%, 10%] → AMBER."""
    assert StrategicPlanningEngine.variance_tier(Decimal("7")) == "AMBER"
    assert StrategicPlanningEngine.variance_tier(Decimal("-8")) == "AMBER"
    # Boundary: exactly 5% → AMBER (not < 5%)
    assert StrategicPlanningEngine.variance_tier(Decimal("5")) == "AMBER"
    # Boundary: exactly 10% → AMBER (not > 10%)
    assert StrategicPlanningEngine.variance_tier(Decimal("10")) == "AMBER"


def _test_tier_red():
    """15% deviation > 10% → RED."""
    assert StrategicPlanningEngine.variance_tier(Decimal("15")) == "RED"
    assert StrategicPlanningEngine.variance_tier(Decimal("-20")) == "RED"


def _test_tier_none_passes_through():
    assert StrategicPlanningEngine.variance_tier(None) is None


def _test_forecast_straight_line():
    """50M YTD over 6mo → 100M full year."""
    r = StrategicPlanningEngine.forecast(
        "STRAIGHT_LINE", Decimal("50000000"), months_elapsed=6, total_months=12)
    assert r["forecast"] == "100000000.00"


def _test_forecast_run_rate():
    """30M YTD over 6mo + 5M/mo for 6 remaining = 60M."""
    r = StrategicPlanningEngine.forecast(
        "RUN_RATE", Decimal("30000000"), months_elapsed=6, total_months=12,
        last_3mo_avg=Decimal("5000000"))
    assert r["forecast"] == "60000000.00"


def _test_forecast_seasonally_adjusted():
    """Even seasonal indices = identical to straight line scaling."""
    r = StrategicPlanningEngine.forecast(
        "SEASONALLY_ADJUSTED", Decimal("50000000"),
        months_elapsed=6, total_months=12,
        seasonal_indices=[Decimal("1")] * 12)
    # 50M × (12 / 6) = 100M
    assert r["forecast"] == "100000000.00"


def _test_forecast_unknown_method():
    r = StrategicPlanningEngine.forecast(
        "WEIRD", Decimal("50000000"), 6, 12)
    assert r["computed"] is False


def _test_forecast_run_rate_missing_avg():
    r = StrategicPlanningEngine.forecast(
        "RUN_RATE", Decimal("30000000"), 6, 12, last_3mo_avg=None)
    assert r["computed"] is False


def _test_forecast_seasonal_missing_indices():
    r = StrategicPlanningEngine.forecast(
        "SEASONALLY_ADJUSTED", Decimal("50000000"), 6, 12)
    assert r["computed"] is False


def _test_forecast_invalid_months():
    r = StrategicPlanningEngine.forecast(
        "STRAIGHT_LINE", Decimal("50000000"), months_elapsed=13, total_months=12)
    assert r["computed"] is False


def _test_budget_transition_valid():
    r = StrategicPlanningEngine.validate_budget_state_transition("DRAFT", "REVIEW")
    assert r["allowed"] is True


def _test_budget_transition_invalid_skip():
    """DRAFT cannot skip directly to BOARD_APPROVED."""
    r = StrategicPlanningEngine.validate_budget_state_transition("DRAFT", "BOARD_APPROVED")
    assert r["allowed"] is False


def _test_budget_terminal_no_exit():
    """CLOSED has no allowed exits."""
    r = StrategicPlanningEngine.validate_budget_state_transition("CLOSED", "DRAFT")
    assert r["allowed"] is False
    assert r["allowed_next_states"] == []


def _test_reforecast_quarterly_trigger():
    """3 months elapsed → quarterly trigger."""
    r = StrategicPlanningEngine.reforecast_trigger(3, Decimal("2"))
    assert "QUARTERLY_CADENCE" in r["triggers"]
    assert r["should_reforecast"] is True


def _test_reforecast_deviation_trigger():
    """15% variance > 10% threshold → deviation trigger."""
    r = StrategicPlanningEngine.reforecast_trigger(1, Decimal("15"))
    assert "DEVIATION_THRESHOLD" in r["triggers"]


def _test_reforecast_no_trigger():
    """1 month elapsed + 3% variance → no triggers."""
    r = StrategicPlanningEngine.reforecast_trigger(1, Decimal("3"))
    assert r["should_reforecast"] is False
    assert len(r["triggers"]) == 0


def self_test() -> bool:
    tests = [
        _test_categories_byte_for_byte,
        _test_directions_byte_for_byte,
        _test_tiers_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_methods_byte_for_byte,
        _test_states_byte_for_byte,
        _test_transitions_byte_for_byte,
        _test_reforecast_constants_byte_for_byte,
        _test_revenue_favorable,
        _test_revenue_unfavorable,
        _test_opex_favorable_underspend,
        _test_opex_unfavorable_overspend,
        _test_capex_favorable_underspend,
        _test_npat_favorable,
        _test_neutral,
        _test_zero_budget_rule1,
        _test_unknown_category_rule6,
        _test_missing_inputs_rule1,
        _test_tier_green,
        _test_tier_amber,
        _test_tier_red,
        _test_tier_none_passes_through,
        _test_forecast_straight_line,
        _test_forecast_run_rate,
        _test_forecast_seasonally_adjusted,
        _test_forecast_unknown_method,
        _test_forecast_run_rate_missing_avg,
        _test_forecast_seasonal_missing_indices,
        _test_forecast_invalid_months,
        _test_budget_transition_valid,
        _test_budget_transition_invalid_skip,
        _test_budget_terminal_no_exit,
        _test_reforecast_quarterly_trigger,
        _test_reforecast_deviation_trigger,
        _test_reforecast_no_trigger,
    ]
    print("=" * 60)
    print("Strategic Planning Engine — Self-Tests (#93)")
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

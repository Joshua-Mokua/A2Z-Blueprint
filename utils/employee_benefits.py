"""
================================================================================
A2Z MIS 360 — Standard #104: IAS 19 Employee Benefits Engine
================================================================================

Risk classification: Cat B (deterministic IAS 19 employee benefit accounting)

Provides:
    - benefit_classification(...)        -- 5 IAS 19 categories
    - db_obligation_pv(...)              -- PV of defined benefit obligation
    - net_db_liability(...)              -- DBO - plan assets, with asset ceiling
    - net_interest(...)                  -- IAS 19R net interest formula
    - service_cost(...)                  -- current + past service cost
    - remeasurement_split(...)           -- OCI vs P&L split (IAS 19R)

5 BENEFIT_TYPES byte-for-byte (IAS 19.5):
    SHORT_TERM                          -- ≤12mo (wages, paid leave)
    POST_EMPLOYMENT_DEFINED_CONTRIBUTION -- DC plan
    POST_EMPLOYMENT_DEFINED_BENEFIT      -- DB plan
    OTHER_LONG_TERM                     -- long-service awards
    TERMINATION                         -- termination benefits

3 SERVICE_COST_COMPONENTS byte-for-byte (IAS 19R):
    CURRENT_SERVICE_COST   -- normal annual accrual (P&L)
    PAST_SERVICE_COST      -- plan amendment / curtailment (P&L)
    SETTLEMENT_GAIN_LOSS   -- settlement (P&L)

2 REMEASUREMENT_COMPONENTS byte-for-byte (IAS 19R BC):
    ACTUARIAL_GAIN_LOSS    -- OCI (no recycling)
    ASSET_RETURN_OCI       -- excess over net interest = OCI

Net interest direction byte-for-byte:
    Net DB liability × discount rate = net interest (P&L)
    -- If asset position: net interest is INCOME
    -- If liability position: net interest is EXPENSE

Discount rate guidance byte-for-byte (IAS 19.83):
    Use yield on high-quality corporate bonds at reporting date
    of currency and term consistent with obligations.

Asset ceiling byte-for-byte (IAS 19.64):
    Net DB asset capped at:
    PV of refunds available + reductions in future contributions

Honesty rules applied:
    Rule 1: dbo_pv=None when discount_rate or expected_payments missing
            net_interest=None when net_liability or rate missing
    Rule 6: unknown benefit_type / service_cost_component surfaced
            negative discount rate rejected (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 5 BENEFIT TYPES byte-for-byte (IAS 19.5)
BENEFIT_TYPES: Tuple[str, ...] = (
    "SHORT_TERM",
    "POST_EMPLOYMENT_DEFINED_CONTRIBUTION",
    "POST_EMPLOYMENT_DEFINED_BENEFIT",
    "OTHER_LONG_TERM",
    "TERMINATION",
)

# 3 SERVICE COST COMPONENTS byte-for-byte (P&L)
SERVICE_COST_COMPONENTS: Tuple[str, ...] = (
    "CURRENT_SERVICE_COST", "PAST_SERVICE_COST", "SETTLEMENT_GAIN_LOSS",
)

# 2 REMEASUREMENT COMPONENTS byte-for-byte (OCI)
REMEASUREMENT_COMPONENTS: Tuple[str, ...] = (
    "ACTUARIAL_GAIN_LOSS", "ASSET_RETURN_OCI",
)

# Short-term threshold byte-for-byte (IAS 19.5)
SHORT_TERM_MAX_MONTHS = 12


@dataclass
class DbInputs:
    plan_id: str
    discount_rate_pct: Optional[Decimal] = None  # annual
    expected_future_payments: List[Tuple[int, Decimal]] = field(default_factory=list)
    # list of (year_index, payment_amount) — year_index 1 = end of year 1
    plan_asset_fair_value: Optional[Decimal] = None
    asset_ceiling: Optional[Decimal] = None  # PV of available refunds


class EmployeeBenefitsEngine:
    """Deterministic IAS 19 employee benefit computations."""

    @staticmethod
    def benefit_classification(
        benefit_type: str,
        settlement_within_months: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Validate benefit classification.
        SHORT_TERM only valid if settlement ≤ 12 months.
        Rule 6: unknown type rejected.
        """
        if benefit_type not in BENEFIT_TYPES:
            return {"valid": False, "reason": f"unknown_type:{benefit_type}",
                    "valid_types": list(BENEFIT_TYPES)}
        if benefit_type == "SHORT_TERM":
            if settlement_within_months is None:
                return {"valid": False, "reason": "settlement_term_required",
                        "benefit_type": benefit_type}
            if settlement_within_months > SHORT_TERM_MAX_MONTHS:
                return {"valid": False,
                        "reason": "exceeds_short_term_max_months",
                        "settlement_within_months": settlement_within_months,
                        "max_months": SHORT_TERM_MAX_MONTHS}
        return {"valid": True, "benefit_type": benefit_type}

    @staticmethod
    def db_obligation_pv(
        expected_payments: List[Tuple[int, Decimal]],
        discount_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        PV of defined benefit obligation = Σ payment_t / (1 + r)^t.
        Rule 1: None when rate missing or payments empty.
        Rule 6: negative rate rejected.
        """
        if discount_rate_pct is None:
            return {"dbo_pv": None, "computed": False,
                    "reason": "missing_discount_rate"}
        if discount_rate_pct < 0:
            return {"dbo_pv": None, "computed": False,
                    "reason": "negative_discount_rate"}
        if not expected_payments:
            return {"dbo_pv": None, "computed": False,
                    "reason": "empty_payments"}
        rate_decimal = discount_rate_pct / Decimal("100")
        one_plus_r = Decimal("1") + rate_decimal
        dbo_pv = Decimal("0")
        for year_index, payment in expected_payments:
            if year_index < 0:
                return {"dbo_pv": None, "computed": False,
                        "reason": "negative_year_index"}
            if payment is None:
                return {"dbo_pv": None, "computed": False,
                        "reason": "missing_payment"}
            discount_factor = one_plus_r ** year_index
            dbo_pv += payment / discount_factor
        return {
            "discount_rate_pct": str(discount_rate_pct),
            "payment_count": len(expected_payments),
            "dbo_pv": str(dbo_pv.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def net_db_liability(
        dbo: Optional[Decimal],
        plan_assets: Optional[Decimal],
        asset_ceiling: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Net DB liability = DBO - Plan Assets.
        If net asset position (negative) and asset_ceiling provided,
        cap the net asset at the ceiling per IAS 19.64.
        Rule 1: None when DBO or plan_assets missing.
        """
        if dbo is None or plan_assets is None:
            return {"net_position": None, "computed": False,
                    "reason": "missing_dbo_or_plan_assets"}
        if dbo < 0 or plan_assets < 0:
            return {"net_position": None, "computed": False,
                    "reason": "negative_input"}
        net = dbo - plan_assets
        # If asset position (net < 0) and ceiling exists, cap absolute asset
        # value at ceiling (cap NCI principle: cannot recognize asset > ceiling)
        ceiling_applied = False
        if net < 0 and asset_ceiling is not None and asset_ceiling >= 0:
            net_asset_value = -net  # positive surplus
            if net_asset_value > asset_ceiling:
                # Cap at ceiling — net liability becomes -asset_ceiling
                net = -asset_ceiling
                ceiling_applied = True
        return {
            "dbo": str(dbo),
            "plan_assets": str(plan_assets),
            "net_position": str(net.quantize(Decimal("0.01"))),
            "is_liability": net > 0,
            "is_asset": net < 0,
            "asset_ceiling_applied": ceiling_applied,
            "computed": True,
        }

    @staticmethod
    def net_interest(
        net_db_liability: Optional[Decimal],
        discount_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IAS 19R: net interest = net DB liability × discount rate.
        Positive net liability × positive rate → expense.
        Negative net liability (asset) × positive rate → income (negative cost).
        Rule 1: None when inputs missing.
        Rule 6: negative discount rate rejected.
        """
        if net_db_liability is None or discount_rate_pct is None:
            return {"net_interest": None, "computed": False,
                    "reason": "missing_inputs"}
        if discount_rate_pct < 0:
            return {"net_interest": None, "computed": False,
                    "reason": "negative_discount_rate"}
        net_interest_value = (net_db_liability * discount_rate_pct) / Decimal("100")
        return {
            "net_db_liability": str(net_db_liability),
            "discount_rate_pct": str(discount_rate_pct),
            "net_interest": str(net_interest_value.quantize(Decimal("0.01"))),
            "is_expense": net_interest_value > 0,
            "is_income": net_interest_value < 0,
            "computed": True,
        }

    @staticmethod
    def service_cost(
        current_service_cost: Optional[Decimal],
        past_service_cost: Optional[Decimal] = None,
        settlement_gain_loss: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Total service cost per IAS 19R (P&L item).
        Rule 1: None when current_service_cost missing.
        """
        if current_service_cost is None:
            return {"total_service_cost": None, "computed": False,
                    "reason": "missing_current_service_cost"}
        psc = past_service_cost if past_service_cost is not None else Decimal("0")
        sgl = settlement_gain_loss if settlement_gain_loss is not None else Decimal("0")
        total = current_service_cost + psc + sgl
        return {
            "current_service_cost": str(current_service_cost),
            "past_service_cost": str(psc),
            "settlement_gain_loss": str(sgl),
            "total_service_cost": str(total.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def remeasurement_split(
        actuarial_gain_loss: Optional[Decimal],
        actual_asset_return: Optional[Decimal],
        net_interest_on_assets: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Remeasurement split per IAS 19R: ALL goes to OCI (no recycling).
        Asset return component = actual return - net interest on assets.
        Rule 1: None when inputs missing.
        """
        if (actuarial_gain_loss is None or actual_asset_return is None
                or net_interest_on_assets is None):
            return {"oci_total": None, "computed": False,
                    "reason": "missing_inputs"}
        asset_return_oci = actual_asset_return - net_interest_on_assets
        oci_total = actuarial_gain_loss + asset_return_oci
        return {
            "actuarial_gain_loss": str(actuarial_gain_loss),
            "actual_asset_return": str(actual_asset_return),
            "net_interest_on_assets": str(net_interest_on_assets),
            "asset_return_oci_component": str(asset_return_oci.quantize(Decimal("0.01"))),
            "oci_total": str(oci_total.quantize(Decimal("0.01"))),
            "no_recycling": True,
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_benefit_types_byte_for_byte():
    expected = (
        "SHORT_TERM",
        "POST_EMPLOYMENT_DEFINED_CONTRIBUTION",
        "POST_EMPLOYMENT_DEFINED_BENEFIT",
        "OTHER_LONG_TERM",
        "TERMINATION",
    )
    for t in expected:
        assert t in BENEFIT_TYPES
    assert len(BENEFIT_TYPES) == 5


def _test_service_cost_components_byte_for_byte():
    expected = ("CURRENT_SERVICE_COST", "PAST_SERVICE_COST",
                "SETTLEMENT_GAIN_LOSS")
    for c in expected:
        assert c in SERVICE_COST_COMPONENTS


def _test_remeasurement_components_byte_for_byte():
    expected = ("ACTUARIAL_GAIN_LOSS", "ASSET_RETURN_OCI")
    for c in expected:
        assert c in REMEASUREMENT_COMPONENTS


def _test_short_term_threshold_byte_for_byte():
    assert SHORT_TERM_MAX_MONTHS == 12


def _test_classification_short_term_valid():
    r = EmployeeBenefitsEngine.benefit_classification(
        "SHORT_TERM", settlement_within_months=6)
    assert r["valid"] is True


def _test_classification_short_term_too_long():
    r = EmployeeBenefitsEngine.benefit_classification(
        "SHORT_TERM", settlement_within_months=18)
    assert r["valid"] is False


def _test_classification_short_term_boundary():
    """12 months exactly → valid (≤12)."""
    r = EmployeeBenefitsEngine.benefit_classification(
        "SHORT_TERM", settlement_within_months=12)
    assert r["valid"] is True


def _test_classification_db_valid():
    r = EmployeeBenefitsEngine.benefit_classification(
        "POST_EMPLOYMENT_DEFINED_BENEFIT")
    assert r["valid"] is True


def _test_classification_unknown_rule6():
    r = EmployeeBenefitsEngine.benefit_classification("WEIRD")
    assert r["valid"] is False


def _test_dbo_pv_basic():
    """1M payment in year 1 @ 5% → 1M / 1.05 = 952,380.95."""
    r = EmployeeBenefitsEngine.db_obligation_pv(
        [(1, Decimal("1000000"))], Decimal("5"))
    pv = Decimal(r["dbo_pv"])
    assert pv > Decimal("952000")
    assert pv < Decimal("953000")


def _test_dbo_pv_multi_year():
    """1M in year 1, 1M in year 2 @ 5%."""
    r = EmployeeBenefitsEngine.db_obligation_pv(
        [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("5"))
    pv = Decimal(r["dbo_pv"])
    # ~1857K
    assert pv > Decimal("1850000")
    assert pv < Decimal("1865000")


def _test_dbo_pv_zero_rate():
    """At 0% discount, PV = sum."""
    r = EmployeeBenefitsEngine.db_obligation_pv(
        [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("0"))
    assert r["dbo_pv"] == "2000000.00"


def _test_dbo_pv_missing_rate_rule1():
    r = EmployeeBenefitsEngine.db_obligation_pv(
        [(1, Decimal("1000000"))], None)
    assert r["dbo_pv"] is None


def _test_dbo_pv_negative_rate_rule6():
    r = EmployeeBenefitsEngine.db_obligation_pv(
        [(1, Decimal("1000000"))], Decimal("-5"))
    assert r["computed"] is False


def _test_dbo_pv_empty_payments_rule1():
    r = EmployeeBenefitsEngine.db_obligation_pv([], Decimal("5"))
    assert r["dbo_pv"] is None


def _test_net_liability_basic():
    """DBO 10M, Assets 8M → net liability 2M."""
    r = EmployeeBenefitsEngine.net_db_liability(
        Decimal("10000000"), Decimal("8000000"))
    assert r["net_position"] == "2000000.00"
    assert r["is_liability"] is True


def _test_net_asset_position():
    """DBO 8M, Assets 10M → net asset (negative) 2M."""
    r = EmployeeBenefitsEngine.net_db_liability(
        Decimal("8000000"), Decimal("10000000"))
    assert r["net_position"] == "-2000000.00"
    assert r["is_asset"] is True


def _test_asset_ceiling_applied():
    """DBO 8M, Assets 12M → 4M surplus, but ceiling 1M → cap."""
    r = EmployeeBenefitsEngine.net_db_liability(
        Decimal("8000000"), Decimal("12000000"),
        asset_ceiling=Decimal("1000000"))
    assert r["asset_ceiling_applied"] is True
    assert r["net_position"] == "-1000000.00"


def _test_net_liability_missing_rule1():
    r = EmployeeBenefitsEngine.net_db_liability(None, Decimal("8000000"))
    assert r["net_position"] is None


def _test_net_interest_liability_expense():
    """Net liability 2M @ 5% → 100K expense."""
    r = EmployeeBenefitsEngine.net_interest(Decimal("2000000"), Decimal("5"))
    assert r["net_interest"] == "100000.00"
    assert r["is_expense"] is True


def _test_net_interest_asset_income():
    """Net asset (-2M) @ 5% → -100K income."""
    r = EmployeeBenefitsEngine.net_interest(Decimal("-2000000"), Decimal("5"))
    assert r["net_interest"] == "-100000.00"
    assert r["is_income"] is True


def _test_net_interest_missing_rule1():
    r = EmployeeBenefitsEngine.net_interest(None, Decimal("5"))
    assert r["computed"] is False


def _test_net_interest_negative_rate_rule6():
    r = EmployeeBenefitsEngine.net_interest(Decimal("2000000"), Decimal("-5"))
    assert r["computed"] is False


def _test_service_cost_current_only():
    r = EmployeeBenefitsEngine.service_cost(Decimal("500000"))
    assert r["total_service_cost"] == "500000.00"


def _test_service_cost_with_past():
    """Current 500K + past 100K → 600K."""
    r = EmployeeBenefitsEngine.service_cost(
        Decimal("500000"), past_service_cost=Decimal("100000"))
    assert r["total_service_cost"] == "600000.00"


def _test_service_cost_with_all_components():
    """500K + 100K + 50K = 650K."""
    r = EmployeeBenefitsEngine.service_cost(
        Decimal("500000"), Decimal("100000"), Decimal("50000"))
    assert r["total_service_cost"] == "650000.00"


def _test_service_cost_missing_current_rule1():
    r = EmployeeBenefitsEngine.service_cost(None, Decimal("100000"))
    assert r["computed"] is False


def _test_remeasurement_split_basic():
    """Actuarial loss 100K + (actual return 600K - net interest 500K) = 100K asset return.
    Total OCI = 100K + 100K = 200K.
    """
    r = EmployeeBenefitsEngine.remeasurement_split(
        Decimal("100000"), Decimal("600000"), Decimal("500000"))
    assert r["asset_return_oci_component"] == "100000.00"
    assert r["oci_total"] == "200000.00"
    assert r["no_recycling"] is True


def _test_remeasurement_actuarial_gain_negative():
    """Actuarial gain -50K (negative) + asset return 0 = -50K OCI."""
    r = EmployeeBenefitsEngine.remeasurement_split(
        Decimal("-50000"), Decimal("100000"), Decimal("100000"))
    assert r["asset_return_oci_component"] == "0.00"
    assert r["oci_total"] == "-50000.00"


def _test_remeasurement_missing_rule1():
    r = EmployeeBenefitsEngine.remeasurement_split(
        None, Decimal("100000"), Decimal("100000"))
    assert r["computed"] is False


def self_test() -> bool:
    tests = [
        _test_benefit_types_byte_for_byte,
        _test_service_cost_components_byte_for_byte,
        _test_remeasurement_components_byte_for_byte,
        _test_short_term_threshold_byte_for_byte,
        _test_classification_short_term_valid,
        _test_classification_short_term_too_long,
        _test_classification_short_term_boundary,
        _test_classification_db_valid,
        _test_classification_unknown_rule6,
        _test_dbo_pv_basic,
        _test_dbo_pv_multi_year,
        _test_dbo_pv_zero_rate,
        _test_dbo_pv_missing_rate_rule1,
        _test_dbo_pv_negative_rate_rule6,
        _test_dbo_pv_empty_payments_rule1,
        _test_net_liability_basic,
        _test_net_asset_position,
        _test_asset_ceiling_applied,
        _test_net_liability_missing_rule1,
        _test_net_interest_liability_expense,
        _test_net_interest_asset_income,
        _test_net_interest_missing_rule1,
        _test_net_interest_negative_rate_rule6,
        _test_service_cost_current_only,
        _test_service_cost_with_past,
        _test_service_cost_with_all_components,
        _test_service_cost_missing_current_rule1,
        _test_remeasurement_split_basic,
        _test_remeasurement_actuarial_gain_negative,
        _test_remeasurement_missing_rule1,
    ]
    print("=" * 60)
    print("Employee Benefits Engine — Self-Tests (#104 IAS 19)")
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

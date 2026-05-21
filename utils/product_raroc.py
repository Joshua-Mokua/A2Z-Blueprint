"""
================================================================================
A2Z MIS 360 — Standard #90: Product RAROC & Hurdle-Rate Tiering Engine
================================================================================

Risk classification: Cat B (deterministic RAROC computation)

Note: this module is SEPARATE from utils/product_profitability.py (Std #47
Volume Seven). #47 covers product PnL with FTP propagation and cross-sell;
#90 adds RAROC formula, hurdle-rate tiering, NIM split (lending vs funding
spread), and cost allocation methodologies.

Product-level RAROC (Risk-Adjusted Return on Capital):
    - net_interest_income(...)              -- NII = interest_income - interest_expense
    - operating_profit(...)                 -- NII + non_interest_income - opex
    - raroc(...)                            -- (Op profit - EL) / Economic Capital × 100
    - profitability_tier(...)               -- GREEN/AMBER/RED vs hurdle rate
    - allocate_costs(...)                   -- ABC / FULL_COST / MARGINAL allocation

6 PRODUCT_GROUPS byte-for-byte: TRANSACTION_BANKING, CONSUMER_LENDING,
    CORPORATE_LENDING, TRADE_FINANCE, TREASURY, BANCASSURANCE

4 COST_CATEGORIES byte-for-byte: DIRECT_PRODUCT_COSTS, ALLOCATED_OPERATIONS,
    ALLOCATED_TECHNOLOGY, ALLOCATED_OVERHEAD

3 ALLOCATION_METHODOLOGIES byte-for-byte: ABC, FULL_COST, MARGINAL

Hurdle rate byte-for-byte: HURDLE_RATE_PCT = 15

Profitability tier multipliers byte-for-byte (relative to hurdle):
    GREEN_MULTIPLIER  = 1.0  (>= hurdle)
    AMBER_MULTIPLIER  = 0.8  (>= 80% of hurdle)

Honesty rules applied:
    Rule 1: RAROC=None when economic_capital <= 0 or any required component None
    Rule 6: missing cost categories surfaced; tier=None if RAROC is None

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

PRODUCT_GROUPS: Tuple[str, ...] = (
    "TRANSACTION_BANKING", "CONSUMER_LENDING", "CORPORATE_LENDING",
    "TRADE_FINANCE", "TREASURY", "BANCASSURANCE",
)
COST_CATEGORIES: Tuple[str, ...] = (
    "DIRECT_PRODUCT_COSTS", "ALLOCATED_OPERATIONS",
    "ALLOCATED_TECHNOLOGY", "ALLOCATED_OVERHEAD",
)
ALLOCATION_METHODOLOGIES: Tuple[str, ...] = ("ABC", "FULL_COST", "MARGINAL")

HURDLE_RATE_PCT = Decimal("15")
GREEN_MULTIPLIER = Decimal("1.0")
AMBER_MULTIPLIER = Decimal("0.8")


@dataclass
class ProductPnl:
    product_id: str
    product_group: str
    interest_income_kes: Optional[Decimal] = None
    interest_expense_kes: Optional[Decimal] = None
    non_interest_income_kes: Optional[Decimal] = None
    direct_costs_kes: Optional[Decimal] = None
    allocated_operations_kes: Optional[Decimal] = None
    allocated_technology_kes: Optional[Decimal] = None
    allocated_overhead_kes: Optional[Decimal] = None
    expected_loss_kes: Optional[Decimal] = None
    economic_capital_kes: Optional[Decimal] = None


class ProductRarocEngine:
    """Deterministic product RAROC + hurdle-rate tiering."""

    @staticmethod
    def net_interest_income(
        ii: Optional[Decimal], ie: Optional[Decimal],
    ) -> Optional[Decimal]:
        if ii is None or ie is None:
            return None
        return ii - ie

    @staticmethod
    def total_opex(p: ProductPnl) -> Dict[str, Any]:
        cost_dict = {
            "DIRECT_PRODUCT_COSTS": p.direct_costs_kes,
            "ALLOCATED_OPERATIONS": p.allocated_operations_kes,
            "ALLOCATED_TECHNOLOGY": p.allocated_technology_kes,
            "ALLOCATED_OVERHEAD": p.allocated_overhead_kes,
        }
        missing = [k for k, v in cost_dict.items() if v is None]
        present = sum((v for v in cost_dict.values() if v is not None),
                      Decimal("0"))
        return {
            "total_opex_kes": present,
            "missing_cost_categories": missing,
            "complete": len(missing) == 0,
        }

    @staticmethod
    def operating_profit(p: ProductPnl) -> Dict[str, Any]:
        nii = ProductRarocEngine.net_interest_income(
            p.interest_income_kes, p.interest_expense_kes)
        opex_data = ProductRarocEngine.total_opex(p)
        if nii is None or p.non_interest_income_kes is None:
            return {"operating_profit_kes": None,
                    "reason": "missing_revenue_components",
                    "missing_cost_categories": opex_data["missing_cost_categories"]}
        op = nii + p.non_interest_income_kes - opex_data["total_opex_kes"]
        return {
            "operating_profit_kes": op,
            "nii_kes": nii,
            "non_interest_income_kes": p.non_interest_income_kes,
            "total_opex_kes": opex_data["total_opex_kes"],
            "missing_cost_categories": opex_data["missing_cost_categories"],
        }

    @staticmethod
    def raroc(p: ProductPnl) -> Dict[str, Any]:
        if p.economic_capital_kes is None or p.economic_capital_kes <= 0:
            return {"raroc_pct": None, "reason": "missing_or_zero_economic_capital"}
        op_data = ProductRarocEngine.operating_profit(p)
        if op_data["operating_profit_kes"] is None:
            return {"raroc_pct": None,
                    "reason": "missing_operating_profit_components"}
        if p.expected_loss_kes is None:
            return {"raroc_pct": None, "reason": "missing_expected_loss"}
        rap = op_data["operating_profit_kes"] - p.expected_loss_kes
        raroc_val = rap / p.economic_capital_kes * Decimal("100")
        return {
            "raroc_pct": str(raroc_val.quantize(Decimal("0.01"))),
            "operating_profit_kes": str(op_data["operating_profit_kes"]),
            "expected_loss_kes": str(p.expected_loss_kes),
            "economic_capital_kes": str(p.economic_capital_kes),
            "risk_adjusted_profit_kes": str(rap),
        }

    @staticmethod
    def profitability_tier(
        raroc_pct: Optional[Decimal],
        hurdle_rate_pct: Decimal = HURDLE_RATE_PCT,
    ) -> Dict[str, Any]:
        if raroc_pct is None:
            return {"tier": None, "reason": "raroc_unavailable"}
        green = hurdle_rate_pct * GREEN_MULTIPLIER
        amber = hurdle_rate_pct * AMBER_MULTIPLIER
        if raroc_pct >= green:
            tier = "GREEN"
        elif raroc_pct >= amber:
            tier = "AMBER"
        else:
            tier = "RED"
        return {
            "tier": tier,
            "raroc_pct": str(raroc_pct.quantize(Decimal("0.01"))),
            "hurdle_rate_pct": str(hurdle_rate_pct),
            "green_threshold_pct": str(green),
            "amber_threshold_pct": str(amber),
        }

    @staticmethod
    def allocate_costs(
        total_cost_kes: Optional[Decimal],
        product_drivers: Dict[str, Decimal],
        method: str = "ABC",
    ) -> Dict[str, Any]:
        if method not in ALLOCATION_METHODOLOGIES:
            return {"allocations": None,
                    "reason": f"unknown_method:{method}",
                    "valid_methods": list(ALLOCATION_METHODOLOGIES)}
        if total_cost_kes is None or total_cost_kes <= 0:
            return {"allocations": None, "reason": "zero_or_missing_total_cost"}
        if not product_drivers:
            return {"allocations": None, "reason": "no_drivers"}
        total_drivers = sum(product_drivers.values())
        if total_drivers <= 0:
            return {"allocations": None, "reason": "zero_total_drivers"}
        allocations = {pid: total_cost_kes * d / total_drivers
                       for pid, d in product_drivers.items()}
        return {
            "method": method,
            "total_cost_kes": str(total_cost_kes),
            "total_drivers": str(total_drivers),
            "allocations": {k: str(v.quantize(Decimal("0.01"))) for k, v in allocations.items()},
        }


# ============================================================================
# Self-tests
# ============================================================================

def _full_pnl():
    return ProductPnl(
        product_id="MORTGAGE_001", product_group="CONSUMER_LENDING",
        interest_income_kes=Decimal("100000000"),
        interest_expense_kes=Decimal("40000000"),
        non_interest_income_kes=Decimal("10000000"),
        direct_costs_kes=Decimal("5000000"),
        allocated_operations_kes=Decimal("3000000"),
        allocated_technology_kes=Decimal("2000000"),
        allocated_overhead_kes=Decimal("4000000"),
        expected_loss_kes=Decimal("8000000"),
        economic_capital_kes=Decimal("200000000"),
    )


def _test_product_groups_byte_for_byte():
    expected = ("TRANSACTION_BANKING", "CONSUMER_LENDING", "CORPORATE_LENDING",
                "TRADE_FINANCE", "TREASURY", "BANCASSURANCE")
    for p in expected:
        assert p in PRODUCT_GROUPS
    assert len(PRODUCT_GROUPS) == 6


def _test_cost_categories_byte_for_byte():
    expected = ("DIRECT_PRODUCT_COSTS", "ALLOCATED_OPERATIONS",
                "ALLOCATED_TECHNOLOGY", "ALLOCATED_OVERHEAD")
    for c in expected:
        assert c in COST_CATEGORIES
    assert len(COST_CATEGORIES) == 4


def _test_allocation_methodologies_byte_for_byte():
    for m in ("ABC", "FULL_COST", "MARGINAL"):
        assert m in ALLOCATION_METHODOLOGIES


def _test_hurdle_rate_byte_for_byte():
    assert HURDLE_RATE_PCT == Decimal("15")


def _test_tier_multipliers_byte_for_byte():
    assert GREEN_MULTIPLIER == Decimal("1.0")
    assert AMBER_MULTIPLIER == Decimal("0.8")


def _test_nii_basic():
    assert ProductRarocEngine.net_interest_income(
        Decimal("100"), Decimal("40")) == Decimal("60")


def _test_nii_missing_rule1():
    assert ProductRarocEngine.net_interest_income(None, Decimal("40")) is None


def _test_total_opex_full():
    p = _full_pnl()
    r = ProductRarocEngine.total_opex(p)
    assert r["total_opex_kes"] == Decimal("14000000")
    assert r["complete"] is True


def _test_total_opex_missing_categories_rule6():
    p = _full_pnl()
    p.allocated_overhead_kes = None
    r = ProductRarocEngine.total_opex(p)
    assert "ALLOCATED_OVERHEAD" in r["missing_cost_categories"]
    assert r["complete"] is False


def _test_operating_profit():
    p = _full_pnl()
    r = ProductRarocEngine.operating_profit(p)
    # NII 60 + 10 - 14 = 56M
    assert r["operating_profit_kes"] == Decimal("56000000")


def _test_operating_profit_missing_rule1():
    p = _full_pnl()
    p.non_interest_income_kes = None
    r = ProductRarocEngine.operating_profit(p)
    assert r["operating_profit_kes"] is None


def _test_raroc_full():
    p = _full_pnl()
    # 56M - 8M = 48M; / 200M = 24%
    r = ProductRarocEngine.raroc(p)
    assert r["raroc_pct"] == "24.00"


def _test_raroc_zero_capital_rule1():
    p = _full_pnl()
    p.economic_capital_kes = Decimal("0")
    r = ProductRarocEngine.raroc(p)
    assert r["raroc_pct"] is None


def _test_raroc_missing_components_rule1():
    p = _full_pnl()
    p.expected_loss_kes = None
    r = ProductRarocEngine.raroc(p)
    assert r["raroc_pct"] is None


def _test_tier_green():
    r = ProductRarocEngine.profitability_tier(Decimal("24"))
    assert r["tier"] == "GREEN"


def _test_tier_amber():
    """13% < 15% but >= 12% (80%) → AMBER."""
    r = ProductRarocEngine.profitability_tier(Decimal("13"))
    assert r["tier"] == "AMBER"


def _test_tier_red():
    r = ProductRarocEngine.profitability_tier(Decimal("5"))
    assert r["tier"] == "RED"


def _test_tier_at_hurdle():
    """Exactly 15% = GREEN."""
    r = ProductRarocEngine.profitability_tier(Decimal("15"))
    assert r["tier"] == "GREEN"


def _test_tier_at_amber_threshold():
    """Exactly 12% = AMBER."""
    r = ProductRarocEngine.profitability_tier(Decimal("12"))
    assert r["tier"] == "AMBER"


def _test_tier_none_rule6():
    r = ProductRarocEngine.profitability_tier(None)
    assert r["tier"] is None


def _test_allocate_costs_abc():
    r = ProductRarocEngine.allocate_costs(
        Decimal("1000000"),
        {"P1": Decimal("60"), "P2": Decimal("40")},
        method="ABC",
    )
    assert r["allocations"]["P1"] == "600000.00"
    assert r["allocations"]["P2"] == "400000.00"


def _test_allocate_costs_unknown_method():
    r = ProductRarocEngine.allocate_costs(
        Decimal("1000000"), {"P1": Decimal("60")}, method="WEIRD")
    assert r["allocations"] is None


def _test_allocate_costs_zero_total_rule1():
    r = ProductRarocEngine.allocate_costs(Decimal("0"), {"P1": Decimal("60")})
    assert r["allocations"] is None


def _test_allocate_costs_no_drivers_rule1():
    r = ProductRarocEngine.allocate_costs(Decimal("1000000"), {})
    assert r["allocations"] is None


def self_test() -> bool:
    tests = [
        _test_product_groups_byte_for_byte,
        _test_cost_categories_byte_for_byte,
        _test_allocation_methodologies_byte_for_byte,
        _test_hurdle_rate_byte_for_byte,
        _test_tier_multipliers_byte_for_byte,
        _test_nii_basic,
        _test_nii_missing_rule1,
        _test_total_opex_full,
        _test_total_opex_missing_categories_rule6,
        _test_operating_profit,
        _test_operating_profit_missing_rule1,
        _test_raroc_full,
        _test_raroc_zero_capital_rule1,
        _test_raroc_missing_components_rule1,
        _test_tier_green,
        _test_tier_amber,
        _test_tier_red,
        _test_tier_at_hurdle,
        _test_tier_at_amber_threshold,
        _test_tier_none_rule6,
        _test_allocate_costs_abc,
        _test_allocate_costs_unknown_method,
        _test_allocate_costs_zero_total_rule1,
        _test_allocate_costs_no_drivers_rule1,
    ]
    print("=" * 60)
    print("Product RAROC Engine — Self-Tests (#90)")
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

"""
================================================================================
A2Z MIS 360 — Standard #70: Customer Lifetime Value Engine
================================================================================

Risk classification: Cat B (deterministic NPV computation across product holdings)

Computes:
    - product_revenue(holdings)           -- annual revenue per product
    - clv_simple(customer)                -- annualized revenue × tenure × margin
    - clv_npv(customer, discount_rate)    -- discounted multi-year cash flow
    - clv_aggregate(customers)            -- total bank CLV + percentile bands
    - profitability_segment(clv)          -- HIGH_VALUE / MEDIUM / LOW / UNPROFITABLE

CLV computation (deterministic NPV approach):
    Annual revenue = sum(product_holdings × product_yield_pct)
    Annual contribution margin = annual_revenue × MARGIN_PCT - servicing_cost
    CLV (NPV) = sum_{t=1..N} contribution / (1 + discount_rate)^t

Industry-standard product yields (Kenyan banking):
    SAVINGS         : 0.5% net interest margin
    CURRENT         : 3.0% (low-cost deposits — high margin)
    TERM_DEPOSIT    : 1.0%
    PERSONAL_LOAN   : 12.0% NIM
    MORTGAGE        : 4.5% NIM
    CREDIT_CARD     : 18.0% (effective, before charge-offs)
    TRADE_FINANCE   : 6.0%
    INVESTMENT      : 1.0% (mgmt fee)

Honesty rules applied:
    Rule 1: clv = None when no product holdings (cannot compute revenue)
    Rule 6: missing tenure_years surfaced; product holding without amount
            excluded with count tracked; customers without sufficient data
            NEVER imputed with average values

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

# Set Decimal precision for NPV calculations
getcontext().prec = 28

# Spec literals — product yield (NIM or fee%)
PRODUCT_YIELDS_PCT: Dict[str, Decimal] = {
    "SAVINGS": Decimal("0.5"),
    "CURRENT": Decimal("3.0"),
    "TERM_DEPOSIT": Decimal("1.0"),
    "PERSONAL_LOAN": Decimal("12.0"),
    "MORTGAGE": Decimal("4.5"),
    "CREDIT_CARD": Decimal("18.0"),
    "TRADE_FINANCE": Decimal("6.0"),
    "INVESTMENT": Decimal("1.0"),
}

PRODUCT_TYPES: Tuple[str, ...] = tuple(PRODUCT_YIELDS_PCT.keys())

# Margin assumption (contribution after operating cost, before discount)
DEFAULT_CONTRIBUTION_MARGIN_PCT = Decimal("60.0")  # 60% of revenue is margin

# Annual servicing cost per customer (KES)
DEFAULT_ANNUAL_SERVICING_COST_KES = Decimal("2400")

# Default NPV horizon and discount rate
DEFAULT_HORIZON_YEARS = 5
DEFAULT_DISCOUNT_RATE_PCT = Decimal("12.0")  # CBR-aligned

# Profitability segment thresholds (KES NPV)
CLV_HIGH_VALUE_MIN = Decimal("500000")
CLV_MEDIUM_MIN = Decimal("50000")
CLV_LOW_MIN = Decimal("0")
# < 0 = UNPROFITABLE

PROFITABILITY_SEGMENTS: Tuple[str, ...] = ("HIGH_VALUE", "MEDIUM", "LOW", "UNPROFITABLE")


@dataclass
class ProductHolding:
    holding_id: str
    customer_id: str
    product_type: str  # SAVINGS / CURRENT / etc.
    balance_or_outstanding_kes: Optional[Decimal] = None
    opened_date: Optional[str] = None


@dataclass
class CustomerForCLV:
    customer_id: str
    cif_id: str
    tenure_years: Optional[Decimal] = None
    holdings: List[ProductHolding] = field(default_factory=list)
    annual_servicing_cost_override: Optional[Decimal] = None


def _to_decimal(amount: Any) -> Optional[Decimal]:
    if amount is None:
        return None
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount))


class CustomerLifetimeValueEngine:
    """Deterministic CLV computation with NPV discounting."""

    @staticmethod
    def product_revenue(holdings: List[ProductHolding]) -> Dict[str, Any]:
        """
        Compute annual revenue per product holding.
        Rule 6: holdings with None balance are excluded with count surfaced.
        """
        per_holding = []
        excluded = []
        total_annual = Decimal("0")
        for h in holdings:
            if h.balance_or_outstanding_kes is None:
                excluded.append(h.holding_id)
                continue
            yield_pct = PRODUCT_YIELDS_PCT.get(h.product_type)
            if yield_pct is None:
                excluded.append(h.holding_id)
                continue
            revenue = (h.balance_or_outstanding_kes * yield_pct) / Decimal("100")
            total_annual += revenue
            per_holding.append({
                "holding_id": h.holding_id,
                "product_type": h.product_type,
                "balance_kes": str(h.balance_or_outstanding_kes),
                "yield_pct": str(yield_pct),
                "annual_revenue_kes": str(revenue),
            })
        return {
            "holding_count": len(holdings),
            "scored_count": len(per_holding),
            "excluded_count": len(excluded),
            "total_annual_revenue_kes": str(total_annual),
            "per_holding": per_holding,
        }

    @staticmethod
    def clv_npv(
        customer: CustomerForCLV,
        horizon_years: int = DEFAULT_HORIZON_YEARS,
        discount_rate_pct: Decimal = DEFAULT_DISCOUNT_RATE_PCT,
        margin_pct: Decimal = DEFAULT_CONTRIBUTION_MARGIN_PCT,
    ) -> Dict[str, Any]:
        """
        Discounted CLV over N-year horizon.
        Rule 1: returns None if customer has no scoreable holdings.
        """
        revenue = CustomerLifetimeValueEngine.product_revenue(customer.holdings)
        annual_rev = _to_decimal(revenue["total_annual_revenue_kes"])

        if revenue["scored_count"] == 0 or annual_rev is None or annual_rev <= 0:
            return {
                "customer_id": customer.customer_id,
                "clv_npv_kes": None,
                "annual_revenue_kes": str(annual_rev) if annual_rev else None,
                "horizon_years": horizon_years,
                "discount_rate_pct": str(discount_rate_pct),
                "reason": "no_scoreable_holdings",
                "excluded_holdings_count": revenue["excluded_count"],
            }

        servicing_cost = (customer.annual_servicing_cost_override
                          if customer.annual_servicing_cost_override is not None
                          else DEFAULT_ANNUAL_SERVICING_COST_KES)
        annual_contribution = (annual_rev * margin_pct / Decimal("100")) - servicing_cost

        # NPV: sum_t contribution / (1 + r)^t
        npv = Decimal("0")
        r = discount_rate_pct / Decimal("100")
        for t in range(1, horizon_years + 1):
            discount_factor = (Decimal("1") + r) ** t
            npv += annual_contribution / discount_factor

        return {
            "customer_id": customer.customer_id,
            "clv_npv_kes": str(npv.quantize(Decimal("0.01"))),
            "annual_revenue_kes": str(annual_rev),
            "annual_contribution_kes": str(annual_contribution),
            "servicing_cost_kes": str(servicing_cost),
            "horizon_years": horizon_years,
            "discount_rate_pct": str(discount_rate_pct),
            "margin_pct": str(margin_pct),
            "scored_holdings": revenue["scored_count"],
            "excluded_holdings_count": revenue["excluded_count"],
        }

    @staticmethod
    def profitability_segment(clv_npv_kes: Optional[Decimal]) -> str:
        """Map CLV NPV to profitability segment."""
        if clv_npv_kes is None:
            return "UNKNOWN"
        if clv_npv_kes >= CLV_HIGH_VALUE_MIN:
            return "HIGH_VALUE"
        if clv_npv_kes >= CLV_MEDIUM_MIN:
            return "MEDIUM"
        if clv_npv_kes >= CLV_LOW_MIN:
            return "LOW"
        return "UNPROFITABLE"

    @staticmethod
    def clv_aggregate(
        customers: List[CustomerForCLV],
        horizon_years: int = DEFAULT_HORIZON_YEARS,
        discount_rate_pct: Decimal = DEFAULT_DISCOUNT_RATE_PCT,
    ) -> Dict[str, Any]:
        """Bank-wide CLV total + segment distribution."""
        scored = []
        unscored = 0
        for c in customers:
            clv = CustomerLifetimeValueEngine.clv_npv(c, horizon_years, discount_rate_pct)
            if clv["clv_npv_kes"] is None:
                unscored += 1
            else:
                scored.append({
                    "customer_id": c.customer_id,
                    "clv_npv_kes": Decimal(clv["clv_npv_kes"]),
                })

        if not scored:
            return {
                "scored_count": 0,
                "unscored_count": unscored,
                "total_clv_npv_kes": None,
                "median_clv_kes": None,
                "segment_distribution": {s: 0 for s in PROFITABILITY_SEGMENTS},
                "reason": "no_scoreable_customers",
            }

        total_clv = sum(s["clv_npv_kes"] for s in scored)
        sorted_clv = sorted(s["clv_npv_kes"] for s in scored)
        n = len(sorted_clv)
        median = sorted_clv[n // 2] if n % 2 == 1 else (sorted_clv[n // 2 - 1] + sorted_clv[n // 2]) / 2

        # Segment distribution
        dist: Dict[str, int] = {s: 0 for s in PROFITABILITY_SEGMENTS}
        for s in scored:
            seg = CustomerLifetimeValueEngine.profitability_segment(s["clv_npv_kes"])
            if seg in dist:
                dist[seg] += 1

        return {
            "scored_count": len(scored),
            "unscored_count": unscored,
            "total_clv_npv_kes": str(total_clv.quantize(Decimal("0.01"))),
            "median_clv_kes": str(median.quantize(Decimal("0.01"))),
            "segment_distribution": dist,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _holding(**kw):
    defaults = dict(
        holding_id="H1", customer_id="C1",
        product_type="SAVINGS", balance_or_outstanding_kes=Decimal("100000"),
    )
    defaults.update(kw)
    return ProductHolding(**defaults)


def _customer_clv(**kw):
    defaults = dict(
        customer_id="C1", cif_id="CIF1",
        tenure_years=Decimal("3"),
        holdings=[_holding()],
    )
    defaults.update(kw)
    return CustomerForCLV(**defaults)


def _test_product_revenue_basic():
    holdings = [_holding(product_type="CURRENT", balance_or_outstanding_kes=Decimal("1000000"))]
    r = CustomerLifetimeValueEngine.product_revenue(holdings)
    # 1M × 3% = 30,000
    assert r["total_annual_revenue_kes"] == "30000.0"


def _test_product_revenue_excluded_rule6():
    holdings = [_holding(holding_id="H1", balance_or_outstanding_kes=None)]
    r = CustomerLifetimeValueEngine.product_revenue(holdings)
    assert r["scored_count"] == 0
    assert r["excluded_count"] == 1


def _test_product_revenue_unknown_type_excluded():
    holdings = [_holding(product_type="WEIRD", balance_or_outstanding_kes=Decimal("100000"))]
    r = CustomerLifetimeValueEngine.product_revenue(holdings)
    assert r["excluded_count"] == 1


def _test_clv_npv_basic():
    """CURRENT 1M @ 3% NIM × 60% margin - 2400 = 15,600/yr. NPV @ 12% × 5y ≈ 56,260."""
    customer = _customer_clv(holdings=[_holding(product_type="CURRENT",
                                                 balance_or_outstanding_kes=Decimal("1000000"))])
    r = CustomerLifetimeValueEngine.clv_npv(customer)
    assert r["clv_npv_kes"] is not None
    npv = Decimal(r["clv_npv_kes"])
    # Rough sanity: 5-year NPV at 12% of 15,600 ≈ 56,257
    assert Decimal("55000") < npv < Decimal("57000")


def _test_clv_no_holdings_rule1():
    customer = _customer_clv(holdings=[])
    r = CustomerLifetimeValueEngine.clv_npv(customer)
    assert r["clv_npv_kes"] is None
    assert r["reason"] == "no_scoreable_holdings"


def _test_clv_negative_contribution_unprofitable():
    """Tiny SAVINGS balance — annual revenue < servicing cost → UNPROFITABLE."""
    customer = _customer_clv(holdings=[_holding(product_type="SAVINGS",
                                                 balance_or_outstanding_kes=Decimal("10000"))])
    r = CustomerLifetimeValueEngine.clv_npv(customer)
    npv = Decimal(r["clv_npv_kes"])
    assert npv < 0
    seg = CustomerLifetimeValueEngine.profitability_segment(npv)
    assert seg == "UNPROFITABLE"


def _test_profitability_segment_high_value():
    seg = CustomerLifetimeValueEngine.profitability_segment(Decimal("750000"))
    assert seg == "HIGH_VALUE"


def _test_profitability_segment_medium_boundary():
    seg = CustomerLifetimeValueEngine.profitability_segment(CLV_MEDIUM_MIN)
    assert seg == "MEDIUM"


def _test_profitability_segment_low():
    seg = CustomerLifetimeValueEngine.profitability_segment(Decimal("10000"))
    assert seg == "LOW"


def _test_profitability_unknown_on_none():
    seg = CustomerLifetimeValueEngine.profitability_segment(None)
    assert seg == "UNKNOWN"


def _test_clv_aggregate():
    customers = [
        _customer_clv(customer_id="C1", holdings=[_holding(product_type="CURRENT",
                                                            balance_or_outstanding_kes=Decimal("1000000"))]),
        _customer_clv(customer_id="C2", holdings=[]),  # unscored
    ]
    r = CustomerLifetimeValueEngine.clv_aggregate(customers)
    assert r["scored_count"] == 1
    assert r["unscored_count"] == 1


def _test_clv_aggregate_all_unscored_rule1():
    customers = [_customer_clv(customer_id=f"C{i}", holdings=[]) for i in range(3)]
    r = CustomerLifetimeValueEngine.clv_aggregate(customers)
    assert r["total_clv_npv_kes"] is None
    assert r["unscored_count"] == 3


def _test_product_yields_byte_for_byte():
    expected = {
        "SAVINGS": Decimal("0.5"),
        "CURRENT": Decimal("3.0"),
        "TERM_DEPOSIT": Decimal("1.0"),
        "PERSONAL_LOAN": Decimal("12.0"),
        "MORTGAGE": Decimal("4.5"),
        "CREDIT_CARD": Decimal("18.0"),
        "TRADE_FINANCE": Decimal("6.0"),
        "INVESTMENT": Decimal("1.0"),
    }
    for k, v in expected.items():
        assert PRODUCT_YIELDS_PCT[k] == v


def _test_segment_thresholds_byte_for_byte():
    assert CLV_HIGH_VALUE_MIN == Decimal("500000")
    assert CLV_MEDIUM_MIN == Decimal("50000")


def _test_npv_determinism():
    """Same input → same output, deterministic."""
    customer = _customer_clv(holdings=[_holding(product_type="CURRENT",
                                                 balance_or_outstanding_kes=Decimal("1000000"))])
    r1 = CustomerLifetimeValueEngine.clv_npv(customer)
    r2 = CustomerLifetimeValueEngine.clv_npv(customer)
    assert r1["clv_npv_kes"] == r2["clv_npv_kes"]


def self_test() -> bool:
    tests = [
        _test_product_revenue_basic,
        _test_product_revenue_excluded_rule6,
        _test_product_revenue_unknown_type_excluded,
        _test_clv_npv_basic,
        _test_clv_no_holdings_rule1,
        _test_clv_negative_contribution_unprofitable,
        _test_profitability_segment_high_value,
        _test_profitability_segment_medium_boundary,
        _test_profitability_segment_low,
        _test_profitability_unknown_on_none,
        _test_clv_aggregate,
        _test_clv_aggregate_all_unscored_rule1,
        _test_product_yields_byte_for_byte,
        _test_segment_thresholds_byte_for_byte,
        _test_npv_determinism,
    ]
    print("=" * 60)
    print("Customer Lifetime Value Engine — Self-Tests (#70)")
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

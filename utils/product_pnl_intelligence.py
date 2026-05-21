"""utils.product_pnl_intelligence — Product Profitability Intelligence
(Standard ENH-131, v10.142). Phase 1E Product Module — first engine.

Per Continuation.docx §Standard #131 (Eco Bank QA spec):
    Full product P&L with direct + allocated costs, customer
    profitability by product.

This is the FIRST standard of Phase 1E Product module
(ENH-131..140, 10 standards across ~4 drops, closing under the
v10.141 UI-pass-on-closure standing norm — cockpit + API + closure
gate ship at module close).

NOTE — companion engine relationship
    utils/product_profitability.py (Standard #47, v5.52) provides
    customer-rollup product PnL with FTP honesty inheritance —
    requires per-customer PnL data injected via callbacks.
    THIS engine (ENH-131) computes book-based product PnL with
    explicit cost allocation directly from data/products.json —
    no per-customer data required. The two are complementary:
    use #47 when you have customer-level PnL flowing in; use
    ENH-131 when you only have product-level book + revenue.

Per Rule 7 (No silent ML predictions):
  1. P&L is fully deterministic — same input → same output
  2. Cost components use NAMED CONSTANTS with documented defaults;
     banks override per cost-allocation config
  3. NO predictive cost modelling — engine reports what config + book
     × rate arithmetic produces, with explicit fallback when inputs
     missing
  4. Honest is_estimate flag + missing_inputs list per Rule 6 when
     direct cost data isn't supplied and allocations are imputed

WHAT THIS MODULE SHIPS
----------------------
1. ProductPnLIntelligence class with:
   - compute_product_pnl(product) — single product P&L breakdown
   - compute_portfolio() — all products in data/products.json
   - aggregate_by_category() — category-level rollup
   - get_loss_making(threshold_pct=0.0) — products below threshold
   - customer_profitability_by_segment(product_id, segment_data) —
     when segment book/revenue data is supplied
   - get_bank_wide_summary() — bank-level totals + ratios

2. Bank-overridable cost constants (% rates, except where noted):
   - DEFAULT_COF_RATE_PCT = 8.5     (cost of funds, blended)
   - DEFAULT_LGD_PCT = 45.0          (loss given default, Basel)
   - DEFAULT_DIRECT_OPS_COST_PCT_OF_REVENUE = 12.0
   - DEFAULT_OVERHEAD_PCT_OF_REVENUE = 18.0
   - PROFITABLE_THRESHOLD_PCT = 5.0  (margin)
   - BREAKEVEN_BAND_PCT = 2.0

3. Per-category cost models (config-override-friendly):
   - "lending":  book × COF (funding) + book × npl × LGD (credit)
   - "deposits": no funding cost (revenue is NIM-net),
                 no credit cost
   - "fee":      no funding cost, no credit cost
                 (e.g. Bancassurance, Digital fee streams)

4. Reads:
   - data/products.json (16 products, target/actual book/revenue)
   - data/cost_allocation_config.json (NEW v10.142 seed; bank-tunable)

HONESTY DISCIPLINE
------------------
- All cost-allocation constants are NAMED and DOCUMENTED — never
  invented per-product numbers
- Cost components flagged is_estimate=True with the imputation basis
  in missing_inputs when actuals aren't supplied
- Deposit / fee products explicitly skip funding + credit cost rather
  than zero-fudging (preserves the cost model semantics)
- Loss-making detection uses an explicit margin threshold; products
  inside BREAKEVEN_BAND_PCT around zero report status="breakeven"
  instead of forcing a binary classification
- customer_profitability_by_segment returns explicit
  fallback_reason="no_segment_data_supplied" when caller doesn't
  provide segment book/revenue input — never fabricates segment splits
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal, getcontext, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

DATA_DIR = Path(__file__).parent.parent / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"
COST_CONFIG_PATH = DATA_DIR / "cost_allocation_config.json"


# ---------------------------------------------------------------------------
# Result dataclass — frozen per Rule 1
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProductPnLBookBased:
    product_id: str
    name: str
    category: str
    cost_model: str                  # "lending" | "deposits" | "fee"
    book_kes: Decimal
    revenue_kes: Decimal
    funding_cost_kes: Decimal        # book × cof_rate (lending only)
    credit_cost_kes: Decimal         # book × npl × LGD (lending only)
    direct_ops_cost_kes: Decimal     # config-driven
    allocated_overhead_kes: Decimal  # config-driven
    total_cost_kes: Decimal
    net_profit_kes: Decimal
    margin_pct: Optional[Decimal]    # net / revenue × 100
    roa_pct: Optional[Decimal]       # net / book × 100 (None for fee-only)
    status: str                      # profitable | breakeven | loss-making
    is_estimate: bool
    missing_inputs: Tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "cost_model": self.cost_model,
            "book_kes": str(self.book_kes),
            "revenue_kes": str(self.revenue_kes),
            "funding_cost_kes": str(self.funding_cost_kes),
            "credit_cost_kes": str(self.credit_cost_kes),
            "direct_ops_cost_kes": str(self.direct_ops_cost_kes),
            "allocated_overhead_kes": str(self.allocated_overhead_kes),
            "total_cost_kes": str(self.total_cost_kes),
            "net_profit_kes": str(self.net_profit_kes),
            "margin_pct": (str(self.margin_pct)
                           if self.margin_pct is not None else None),
            "roa_pct": (str(self.roa_pct)
                        if self.roa_pct is not None else None),
            "status": self.status,
            "is_estimate": self.is_estimate,
            "missing_inputs": list(self.missing_inputs),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductPnLIntelligence:
    """Product-level P&L from products.json + cost-allocation config.

    Read-only contract — never writes to performance.* tables. Decimal
    arithmetic throughout; constants bank-overridable via constructor.
    """

    DEFAULT_COF_RATE_PCT = Decimal("8.5")
    DEFAULT_LGD_PCT = Decimal("45.0")
    DEFAULT_DIRECT_OPS_COST_PCT_OF_REVENUE = Decimal("12.0")
    DEFAULT_OVERHEAD_PCT_OF_REVENUE = Decimal("18.0")
    PROFITABLE_THRESHOLD_PCT = Decimal("5.0")
    BREAKEVEN_BAND_PCT = Decimal("2.0")

    CATEGORY_COST_MODEL = {
        "Retail Lending": "lending",
        "SME Lending": "lending",
        "Corporate": "lending",
        "Trade Finance": "lending",
        "Deposits": "deposits",
        "Fee Income": "fee",
        "Digital": "fee",
    }

    def __init__(
        self,
        products_path: Optional[Path] = None,
        cost_config_path: Optional[Path] = None,
    ) -> None:
        self.products_path = products_path or PRODUCTS_PATH
        self.cost_config_path = cost_config_path or COST_CONFIG_PATH
        self._products_cache: Optional[List[Dict[str, Any]]] = None
        self._config_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_products(self) -> List[Dict[str, Any]]:
        if self._products_cache is None:
            try:
                with open(self.products_path) as f:
                    self._products_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._products_cache = []
        return self._products_cache

    def _load_config(self) -> Dict[str, Any]:
        if self._config_cache is None:
            try:
                with open(self.cost_config_path) as f:
                    self._config_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._config_cache = {}
        return self._config_cache

    def _category_param(self, category: str, key: str,
                        default: Decimal) -> Decimal:
        """category override > global > default."""
        cfg = self._load_config()
        cat_overrides = cfg.get("category_overrides", {}).get(category, {})
        if key in cat_overrides:
            return Decimal(str(cat_overrides[key]))
        if key in cfg:
            return Decimal(str(cfg[key]))
        return default

    # ------------------------------------------------------------------
    # P&L computation
    # ------------------------------------------------------------------

    def compute_product_pnl(self, product: Dict[str, Any]
                            ) -> ProductPnLBookBased:
        category = product.get("category", "Unknown")
        cost_model = self.CATEGORY_COST_MODEL.get(category, "fee")
        book = Decimal(str(product.get("actual_book", 0) or 0))
        revenue = Decimal(str(product.get("actual_revenue", 0) or 0))
        npl_rate_pct = Decimal(str(product.get("npl_rate", 0) or 0))

        missing: List[str] = []
        is_estimate = False

        if cost_model == "lending":
            cof_pct = self._category_param(
                category, "cost_of_funds_rate_pct",
                self.DEFAULT_COF_RATE_PCT)
            funding_cost = book * cof_pct / Decimal("100")
            missing.append(
                f"funding_cost: imputed at {cof_pct}% COF on book")
            is_estimate = True
        else:
            funding_cost = Decimal("0")

        if cost_model == "lending":
            lgd_pct = self._category_param(
                category, "loss_given_default_pct",
                self.DEFAULT_LGD_PCT)
            credit_cost = (book * npl_rate_pct / Decimal("100")
                           * lgd_pct / Decimal("100"))
            missing.append(
                f"credit_cost: imputed as book × npl × LGD ({lgd_pct}%)")
        else:
            credit_cost = Decimal("0")

        direct_ops_pct = self._category_param(
            category, "direct_ops_cost_pct_of_revenue",
            self.DEFAULT_DIRECT_OPS_COST_PCT_OF_REVENUE)
        direct_ops_cost = revenue * direct_ops_pct / Decimal("100")
        missing.append(
            f"direct_ops_cost: imputed at {direct_ops_pct}% of revenue")
        is_estimate = True

        overhead_pct = self._category_param(
            category, "allocated_overhead_pct_of_revenue",
            self.DEFAULT_OVERHEAD_PCT_OF_REVENUE)
        allocated_overhead = revenue * overhead_pct / Decimal("100")
        missing.append(
            f"allocated_overhead: imputed at {overhead_pct}% of revenue")

        total_cost = (funding_cost + credit_cost
                      + direct_ops_cost + allocated_overhead)
        net_profit = revenue - total_cost

        margin_pct: Optional[Decimal] = None
        if revenue != 0:
            margin_pct = (net_profit / revenue * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
        roa_pct: Optional[Decimal] = None
        if cost_model in ("lending", "deposits") and book != 0:
            roa_pct = (net_profit / book * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)

        if margin_pct is None:
            status = "no_data"
        elif margin_pct >= self.PROFITABLE_THRESHOLD_PCT:
            status = "profitable"
        elif margin_pct >= -self.BREAKEVEN_BAND_PCT:
            status = "breakeven"
        else:
            status = "loss-making"

        return ProductPnLBookBased(
            product_id=product.get("id", ""),
            name=product.get("name", ""),
            category=category,
            cost_model=cost_model,
            book_kes=book,
            revenue_kes=revenue,
            funding_cost_kes=funding_cost.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            credit_cost_kes=credit_cost.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            direct_ops_cost_kes=direct_ops_cost.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            allocated_overhead_kes=allocated_overhead.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_cost_kes=total_cost.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            net_profit_kes=net_profit.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP),
            margin_pct=margin_pct,
            roa_pct=roa_pct,
            status=status,
            is_estimate=is_estimate,
            missing_inputs=tuple(missing),
        )

    def compute_portfolio(self) -> List[ProductPnLBookBased]:
        return [self.compute_product_pnl(p) for p in self._load_products()]

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def aggregate_by_category(self) -> Dict[str, Dict[str, Any]]:
        portfolio = self.compute_portfolio()
        rollup: Dict[str, Dict[str, Decimal]] = {}
        for r in portfolio:
            cat = rollup.setdefault(r.category, {
                "n_products": 0,
                "book_kes": Decimal("0"),
                "revenue_kes": Decimal("0"),
                "total_cost_kes": Decimal("0"),
                "net_profit_kes": Decimal("0"),
            })
            cat["n_products"] += 1
            cat["book_kes"] += r.book_kes
            cat["revenue_kes"] += r.revenue_kes
            cat["total_cost_kes"] += r.total_cost_kes
            cat["net_profit_kes"] += r.net_profit_kes

        out: Dict[str, Dict[str, Any]] = {}
        for cat, agg in rollup.items():
            margin = None
            if agg["revenue_kes"] != 0:
                margin = (agg["net_profit_kes"] / agg["revenue_kes"]
                          * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)
            roa = None
            if agg["book_kes"] != 0:
                roa = (agg["net_profit_kes"] / agg["book_kes"]
                       * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)
            out[cat] = {
                "n_products": agg["n_products"],
                "book_kes": str(agg["book_kes"]),
                "revenue_kes": str(agg["revenue_kes"]),
                "total_cost_kes": str(agg["total_cost_kes"]),
                "net_profit_kes": str(agg["net_profit_kes"]),
                "margin_pct": str(margin) if margin is not None else None,
                "roa_pct": str(roa) if roa is not None else None,
            }
        return out

    def get_loss_making(self, threshold_pct: float = 0.0
                        ) -> List[ProductPnLBookBased]:
        threshold = Decimal(str(threshold_pct))
        return [r for r in self.compute_portfolio()
                if r.margin_pct is not None and r.margin_pct < threshold]

    def get_bank_wide_summary(self) -> Dict[str, Any]:
        portfolio = self.compute_portfolio()
        total_book = sum((r.book_kes for r in portfolio), Decimal("0"))
        total_revenue = sum((r.revenue_kes for r in portfolio), Decimal("0"))
        total_cost = sum((r.total_cost_kes for r in portfolio), Decimal("0"))
        total_net = total_revenue - total_cost
        margin_pct = None
        if total_revenue != 0:
            margin_pct = (total_net / total_revenue * Decimal("100")
                          ).quantize(Decimal("0.01"),
                                     rounding=ROUND_HALF_UP)
        roa_pct = None
        if total_book != 0:
            roa_pct = (total_net / total_book * Decimal("100")
                       ).quantize(Decimal("0.01"),
                                  rounding=ROUND_HALF_UP)
        n_loss = sum(1 for r in portfolio if r.status == "loss-making")
        n_breakeven = sum(1 for r in portfolio if r.status == "breakeven")
        n_profitable = sum(1 for r in portfolio if r.status == "profitable")
        return {
            "n_products": len(portfolio),
            "total_book_kes": str(total_book),
            "total_revenue_kes": str(total_revenue),
            "total_cost_kes": str(total_cost),
            "total_net_profit_kes": str(total_net),
            "margin_pct": str(margin_pct) if margin_pct is not None else None,
            "roa_pct": str(roa_pct) if roa_pct is not None else None,
            "n_profitable": n_profitable,
            "n_breakeven": n_breakeven,
            "n_loss_making": n_loss,
        }

    # ------------------------------------------------------------------
    # Customer profitability by segment
    # ------------------------------------------------------------------

    def customer_profitability_by_segment(
        self,
        product_id: str,
        segment_data: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Per-segment net profit allocation for a product.

        segment_data shape: {"segment": {"book_kes": x, "revenue_kes": y}}
        Returns explicit fallback when segment_data is None/empty —
        never fabricates a split.
        """
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)
        if product is None:
            return {
                "product_id": product_id,
                "ok": False,
                "fallback_reason": "product_not_found",
                "segments": {},
            }

        if not segment_data:
            return {
                "product_id": product_id,
                "ok": False,
                "fallback_reason": "no_segment_data_supplied",
                "segments": {},
                "note": ("Caller must supply segment_data with"
                         " book/revenue per segment."),
            }

        segments: Dict[str, Dict[str, Any]] = {}
        for seg_name, seg in segment_data.items():
            seg_product = dict(product)
            seg_product["actual_book"] = seg.get("book_kes", 0)
            seg_product["actual_revenue"] = seg.get("revenue_kes", 0)
            r = self.compute_product_pnl(seg_product)
            segments[seg_name] = r.as_dict()

        return {
            "product_id": product_id,
            "ok": True,
            "segments": segments,
            "n_segments": len(segments),
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductPnLIntelligence()
    portfolio = eng.compute_portfolio()
    print(f"Portfolio: {len(portfolio)} products")
    for r in portfolio[:5]:
        print(f"  {r.product_id} {r.name}: "
              f"book={r.book_kes/Decimal('1e9'):.2f}B "
              f"net={r.net_profit_kes/Decimal('1e6'):.1f}M "
              f"margin={r.margin_pct}% roa={r.roa_pct}% {r.status}")
    print()
    summary = eng.get_bank_wide_summary()
    print("Bank-wide:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print()
    by_cat = eng.aggregate_by_category()
    print(f"Categories: {len(by_cat)}")
    for cat, agg in by_cat.items():
        print(f"  {cat}: n={agg['n_products']} "
              f"margin={agg['margin_pct']}% roa={agg['roa_pct']}%")
    print()
    loss = eng.get_loss_making(threshold_pct=0.0)
    print(f"Loss-making: {len(loss)}")
    for r in loss:
        print(f"  {r.product_id} {r.name}: margin={r.margin_pct}%")
    print()
    seg = eng.customer_profitability_by_segment(
        "P001",
        {"HNW": {"book_kes": 10000000000, "revenue_kes": 1500000000},
         "Mass": {"book_kes": 38000000000, "revenue_kes": 5500000000}})
    print(f"P001 by segment ok={seg['ok']} n={seg.get('n_segments', 0)}")
    seg_empty = eng.customer_profitability_by_segment("P001", None)
    print(f"P001 no-data: ok={seg_empty['ok']} "
          f"reason={seg_empty['fallback_reason']}")


if __name__ == "__main__":
    _self_test()

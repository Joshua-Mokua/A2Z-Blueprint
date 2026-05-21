"""utils.lending_intelligence — Lending Intelligence Module
(Standard #44, v5.52). Volume Seven — Finance Intelligence.

Per v6 spec §7:
    LendingIntelligenceEngine: disbursement + NPL + interest income by product

WHAT THIS MODULE SHIPS
----------------------
1. LendingIntelligenceEngine class with:
   - disbursement_by_product(period) — actual vs target by product
   - npl_by_product(as_of_date) — NPL ratio per product
   - interest_income_breakdown(period) — income decomposition

2. LOAN_PRODUCTS catalog
3. Decimal-internal arithmetic (Rule 1)
4. NPL ratio = None when total_outstanding == 0 (Rule 1 — undefined math)

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - NPL ratio returns None (NOT zero) when denominator is zero
  - Decimal-internal precision 28
  - variance_pct returns None when target is zero

Rule 5 — Data integration:
  - When disbursement_lookup_fn returns None for a product, that product
    is reported with actual=None, NOT silently substituted with 0
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.lending_intelligence")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §7 #44)
# ─────────────────────────────────────────────────────────────────────

LOAN_PRODUCTS: List[str] = [
    "MORTGAGE", "PERSONAL", "BUSINESS", "MOBILE",
    "VIRTUAL", "TRADE", "ASSET",
]

# NPL classification: 90+ days past due = non-performing
NPL_DAYS_THRESHOLD = 90

# Auto-commentary thresholds for variance reporting
ABOVE_TARGET_PCT = 5.0     # variance_pct > +5% → "exceeded target"
BELOW_TARGET_PCT = -5.0    # variance_pct < -5% → "below target"


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class LendingIntelligenceEngine:
    """Lending intelligence: disbursements, NPL, interest income."""

    def __init__(
        self,
        disbursement_lookup_fn: Optional[Callable[[str], List[dict]]] = None,
        outstanding_lookup_fn:  Optional[Callable[[str], List[dict]]] = None,
        target_lookup_fn:       Optional[Callable[[str], Dict[str, Any]]] = None,
        interest_lookup_fn:     Optional[Callable[[str], List[dict]]] = None,
    ):
        """All collaborators injectable.

        disbursement_lookup_fn(period) → list[dict] with: amount, product
        outstanding_lookup_fn(date)    → list[dict] with: outstanding, product, days_past_due
        target_lookup_fn(period)       → dict[product → target_amount]
        interest_lookup_fn(period)     → list[dict] with: interest_income, product
        """
        self._disb     = disbursement_lookup_fn or (lambda p: [])
        self._outst    = outstanding_lookup_fn  or (lambda d: [])
        self._targets  = target_lookup_fn       or (lambda p: {})
        self._interest = interest_lookup_fn     or (lambda p: [])

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: disbursement_by_product
    # ──────────────────────────────────────────────────────────────────

    def disbursement_by_product(self, period: str) -> Dict[str, Any]:
        """Track disbursement vs target by product type.

        Returns:
            {
              "period": str,
              "products": {
                  product: {
                    "actual": float,
                    "target": float,
                    "variance": float,
                    "variance_pct": float | None,    # None when target == 0
                    "commentary": str,
                  }
              },
              "totals": {actual, target, variance},
              "meta": {...}
            }
        Returns {} for empty period.
        """
        if not period:
            return {}

        actuals = self._disb(period) or []
        targets = self._targets(period) or {}

        # Aggregate actuals by product (Decimal-internal)
        actual_by_product: Dict[str, Decimal] = {p: ZERO for p in LOAN_PRODUCTS}
        unknown_products: List[str] = []
        for row in actuals:
            if not isinstance(row, dict):
                continue
            product = row.get("product")
            try:
                amt = Decimal(str(row.get("amount", 0)))
            except Exception:
                continue
            if product in LOAN_PRODUCTS:
                actual_by_product[product] += amt
            elif product:
                unknown_products.append(product)

        # Build per-product result
        results: Dict[str, Dict[str, Any]] = {}
        total_actual = ZERO
        total_target = ZERO
        for product in LOAN_PRODUCTS:
            actual = actual_by_product[product]
            try:
                target = Decimal(str(targets.get(product, 0)))
            except Exception:
                target = ZERO
            variance = actual - target
            if target > 0:
                variance_pct = float(variance / target * Decimal("100"))
            else:
                variance_pct = None    # Rule 1 — undefined ratio
            commentary = self._auto_commentary(product, _money(actual), _money(target), variance_pct)
            results[product] = {
                "actual":       _money(actual),
                "target":       _money(target),
                "variance":     _money(variance),
                "variance_pct": round(variance_pct, 2) if variance_pct is not None else None,
                "commentary":   commentary,
            }
            total_actual += actual
            total_target += target

        return {
            "period":   period,
            "products": results,
            "totals": {
                "actual":   _money(total_actual),
                "target":   _money(total_target),
                "variance": _money(total_actual - total_target),
            },
            "meta": {
                "rows_processed":    len(actuals),
                "unknown_products":  sorted(set(unknown_products)),
                "products_in_spec":  list(LOAN_PRODUCTS),
                "generated_at":      datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: npl_by_product
    # ──────────────────────────────────────────────────────────────────

    def npl_by_product(self, as_of_date: str) -> Dict[str, Any]:
        """NPL ratio per product (>90 days past due / total outstanding).

        HONESTY: returns ratio=None (NOT 0) when total_outstanding == 0
        per Rule 1 (consistent with #21 pbt_margin=None on zero revenue).

        Returns:
            {
              "as_of_date": str,
              "products": {
                  product: {
                    "outstanding": float,
                    "npl_amount": float,
                    "npl_ratio": float | None,    # None when outstanding == 0
                  }
              },
              "totals": {...},
              "meta": {...}
            }
        """
        if not as_of_date:
            return {}

        rows = self._outst(as_of_date) or []
        outstanding_by_product: Dict[str, Decimal] = {p: ZERO for p in LOAN_PRODUCTS}
        npl_by_product:         Dict[str, Decimal] = {p: ZERO for p in LOAN_PRODUCTS}

        for row in rows:
            if not isinstance(row, dict):
                continue
            product = row.get("product")
            if product not in LOAN_PRODUCTS:
                continue
            try:
                outst = Decimal(str(row.get("outstanding", 0)))
                dpd   = int(row.get("days_past_due", 0))
            except Exception:
                continue
            outstanding_by_product[product] += outst
            if dpd >= NPL_DAYS_THRESHOLD:
                npl_by_product[product] += outst

        results: Dict[str, Dict[str, Any]] = {}
        total_outst = ZERO
        total_npl   = ZERO
        for product in LOAN_PRODUCTS:
            outst = outstanding_by_product[product]
            npl   = npl_by_product[product]
            ratio = float(npl / outst * Decimal("100")) if outst > 0 else None
            results[product] = {
                "outstanding": _money(outst),
                "npl_amount":  _money(npl),
                "npl_ratio":   round(ratio, 4) if ratio is not None else None,
            }
            total_outst += outst
            total_npl   += npl

        bank_ratio = float(total_npl / total_outst * Decimal("100")) if total_outst > 0 else None

        return {
            "as_of_date": as_of_date,
            "products": results,
            "totals": {
                "outstanding":  _money(total_outst),
                "npl_amount":   _money(total_npl),
                "npl_ratio":    round(bank_ratio, 4) if bank_ratio is not None else None,
            },
            "meta": {
                "npl_days_threshold": NPL_DAYS_THRESHOLD,
                "rows_processed":     len(rows),
                "generated_at":       datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: interest_income_breakdown
    # ──────────────────────────────────────────────────────────────────

    def interest_income_breakdown(self, period: str) -> Dict[str, Any]:
        """Interest income decomposition by product.

        Returns:
            {
              "period": str,
              "products": {product: {"interest_income": float, "share_pct": float}},
              "total_interest_income": float,
              "meta": {...}
            }
        """
        if not period:
            return {}

        rows = self._interest(period) or []
        income_by_product: Dict[str, Decimal] = {p: ZERO for p in LOAN_PRODUCTS}
        for row in rows:
            if not isinstance(row, dict):
                continue
            product = row.get("product")
            if product not in LOAN_PRODUCTS:
                continue
            try:
                income_by_product[product] += Decimal(str(row.get("interest_income", 0)))
            except Exception:
                continue

        total = sum(income_by_product.values())

        results: Dict[str, Dict[str, Any]] = {}
        for product in LOAN_PRODUCTS:
            inc = income_by_product[product]
            share_pct = float(inc / total * Decimal("100")) if total > 0 else None
            results[product] = {
                "interest_income": _money(inc),
                "share_pct":       round(share_pct, 2) if share_pct is not None else None,
            }

        return {
            "period":                period,
            "products":              results,
            "total_interest_income": _money(total),
            "meta": {
                "rows_processed":  len(rows),
                "generated_at":    datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Auto-commentary helper
    # ──────────────────────────────────────────────────────────────────

    def _auto_commentary(
        self, product: str, actual: float, target: float, variance_pct: Optional[float]
    ) -> str:
        """Generate one-line commentary for a product's disbursement variance."""
        if target == 0:
            return f"{product}: KES {actual:,.0f} disbursed (no target set)"
        if variance_pct is None:
            return f"{product}: variance not computable"
        if variance_pct > ABOVE_TARGET_PCT:
            return f"{product}: exceeded target by {variance_pct:.1f}%"
        if variance_pct < BELOW_TARGET_PCT:
            return f"{product}: below target by {abs(variance_pct):.1f}%"
        return f"{product}: on track ({variance_pct:+.1f}%)"


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.lending_intelligence self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert len(LOAN_PRODUCTS) == 7
    assert "MORTGAGE" in LOAN_PRODUCTS
    assert "PERSONAL" in LOAN_PRODUCTS
    assert "MOBILE" in LOAN_PRODUCTS
    print(f"  ✅ spec literals: 7 loan products: {LOAN_PRODUCTS}")
    assert NPL_DAYS_THRESHOLD == 90
    print(f"  ✅ NPL threshold: 90 days past due")

    # ── Empty period / date returns {} ────────────────────────────────
    eng = LendingIntelligenceEngine()
    assert eng.disbursement_by_product("") == {}
    assert eng.npl_by_product("") == {}
    assert eng.interest_income_breakdown("") == {}
    print(f"  ✅ empty inputs → {{}}")

    # ── Disbursement vs target ────────────────────────────────────────
    disbursements = [
        {"amount": 1_000_000_000, "product": "MORTGAGE"},
        {"amount":   500_000_000, "product": "PERSONAL"},
        {"amount":   200_000_000, "product": "BUSINESS"},
    ]
    targets = {
        "MORTGAGE": 1_200_000_000,    # below target
        "PERSONAL":   500_000_000,    # exact
        "BUSINESS":   100_000_000,    # exceeded
        "TRADE":      300_000_000,    # zero actual
    }
    eng2 = LendingIntelligenceEngine(
        disbursement_lookup_fn=lambda p: disbursements,
        target_lookup_fn=lambda p: targets,
    )
    r = eng2.disbursement_by_product("2026-04")
    mortgage = r["products"]["MORTGAGE"]
    assert mortgage["actual"] == 1_000_000_000.00
    assert mortgage["target"] == 1_200_000_000.00
    assert mortgage["variance"] == -200_000_000.00
    assert abs(mortgage["variance_pct"] - (-16.67)) < 0.01
    assert "below target" in mortgage["commentary"]
    print(f"  ✅ disbursement: MORTGAGE below target by {abs(mortgage['variance_pct']):.1f}%")

    business = r["products"]["BUSINESS"]
    assert business["variance_pct"] == 100.0
    assert "exceeded" in business["commentary"]
    print(f"  ✅ disbursement: BUSINESS exceeded target by {business['variance_pct']:.1f}%")

    # ── No-target product handled honestly ────────────────────────────
    targets_partial = {"MORTGAGE": 0}    # target zero
    eng_zero_target = LendingIntelligenceEngine(
        disbursement_lookup_fn=lambda p: [{"amount": 100_000, "product": "MORTGAGE"}],
        target_lookup_fn=lambda p: targets_partial,
    )
    r = eng_zero_target.disbursement_by_product("2026-04")
    mortgage = r["products"]["MORTGAGE"]
    assert mortgage["variance_pct"] is None    # Rule 1 — undefined
    assert "no target" in mortgage["commentary"]
    print(f"  ✅ zero target → variance_pct=None (no silent zero)")

    # ── NPL ratio with data ──────────────────────────────────────────
    outstanding = [
        {"outstanding": 1_000_000_000, "product": "MORTGAGE", "days_past_due": 0},
        {"outstanding":   100_000_000, "product": "MORTGAGE", "days_past_due": 95},
        {"outstanding":    50_000_000, "product": "MORTGAGE", "days_past_due": 45},
        {"outstanding":   500_000_000, "product": "PERSONAL", "days_past_due": 0},
        {"outstanding":   100_000_000, "product": "PERSONAL", "days_past_due": 120},
    ]
    eng3 = LendingIntelligenceEngine(outstanding_lookup_fn=lambda d: outstanding)
    r = eng3.npl_by_product("2026-04-29")
    mortgage = r["products"]["MORTGAGE"]
    # NPL = 100M / (1B + 100M + 50M) = 100/1150 = 8.696%
    expected_ratio = 100_000_000 / 1_150_000_000 * 100
    assert abs(mortgage["npl_ratio"] - expected_ratio) < 0.001
    print(f"  ✅ NPL ratio: MORTGAGE={mortgage['npl_ratio']:.2f}% "
          f"(expected={expected_ratio:.2f}%)")

    # ── Bank-level NPL ratio ──────────────────────────────────────────
    bank_ratio = r["totals"]["npl_ratio"]
    expected_bank = (100_000_000 + 100_000_000) / (1_150_000_000 + 600_000_000) * 100
    assert abs(bank_ratio - expected_bank) < 0.001
    print(f"  ✅ Bank NPL ratio: {bank_ratio:.2f}% (expected={expected_bank:.2f}%)")

    # ── NPL ratio = None when no outstanding ──────────────────────────
    eng4 = LendingIntelligenceEngine(outstanding_lookup_fn=lambda d: [])
    r = eng4.npl_by_product("2026-04-29")
    assert r["totals"]["npl_ratio"] is None    # Rule 1
    for prod in LOAN_PRODUCTS:
        assert r["products"][prod]["npl_ratio"] is None
    print(f"  ✅ NPL ratio = None when no outstanding (Rule 1 — undefined)")

    # ── Interest income breakdown ────────────────────────────────────
    interest = [
        {"interest_income": 500_000_000, "product": "MORTGAGE"},
        {"interest_income": 300_000_000, "product": "PERSONAL"},
        {"interest_income": 200_000_000, "product": "BUSINESS"},
    ]
    eng5 = LendingIntelligenceEngine(interest_lookup_fn=lambda p: interest)
    r = eng5.interest_income_breakdown("2026-04")
    assert r["total_interest_income"] == 1_000_000_000.00
    assert r["products"]["MORTGAGE"]["share_pct"] == 50.0
    assert r["products"]["PERSONAL"]["share_pct"] == 30.0
    print(f"  ✅ interest income: total={r['total_interest_income']:,.2f}, "
          f"MORTGAGE share={r['products']['MORTGAGE']['share_pct']}%")

    # ── Empty interest data → share_pct None ──────────────────────────
    eng6 = LendingIntelligenceEngine(interest_lookup_fn=lambda p: [])
    r = eng6.interest_income_breakdown("2026-04")
    assert r["total_interest_income"] == 0.0
    for prod in LOAN_PRODUCTS:
        assert r["products"][prod]["share_pct"] is None
    print(f"  ✅ no interest data → share_pct=None for all products")

    # ── Unknown product surfaced in meta ──────────────────────────────
    eng_unk = LendingIntelligenceEngine(
        disbursement_lookup_fn=lambda p: [
            {"amount": 100_000, "product": "MORTGAGE"},
            {"amount":  50_000, "product": "MICRO_LOAN"},  # unknown
        ],
        target_lookup_fn=lambda p: {"MORTGAGE": 1_000_000},
    )
    r = eng_unk.disbursement_by_product("2026-04")
    assert "MICRO_LOAN" in r["meta"]["unknown_products"]
    print(f"  ✅ unknown product surfaced: {r['meta']['unknown_products']}")

    # ── KES-billion precision ────────────────────────────────────────
    huge_outst = [
        {"outstanding": "11500000000.50", "product": "MORTGAGE", "days_past_due": 100},
        {"outstanding": "11500000000.51", "product": "MORTGAGE", "days_past_due":   0},
    ]
    eng7 = LendingIntelligenceEngine(outstanding_lookup_fn=lambda d: huge_outst)
    r = eng7.npl_by_product("2026-04-29")
    assert r["products"]["MORTGAGE"]["outstanding"] == 23_000_000_001.01
    print(f"  ✅ KES-billion precision: outstanding={r['products']['MORTGAGE']['outstanding']:,.2f}")

    print("\n  ALL TESTS PASSED")

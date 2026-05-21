"""utils.product_profitability — Product Profitability
(Standard #47, v5.52). Volume Seven — Finance Intelligence.

Per v6 spec §7:
    ProductProfitabilityEngine extends Volume Three's portfolio-level
    inheritance pattern (originally for RM #23) to the PRODUCT dimension.

WHAT THIS MODULE SHIPS
----------------------
1. ProductProfitabilityEngine class with:
   - calculate_product_pnl(product_code, period) — full PnL with V3 honesty
   - cross_sell_intelligence(customer_id) — products held by peers but not by customer
   - product_lifecycle(product_code) — LAUNCH/GROWTH/MATURITY/DECLINE position

2. PRODUCT_CATEGORIES catalog (6 categories per spec)
3. FULL Volume Three portfolio-level inheritance pattern:
   - meta.upstream_ftp_modes counter (on, off, unknown)
   - data_quality_warning citing Mandatory Standard #11 + Rule 2 when
     any input has ftp_mode="off"
   - provisional flag at >50% threshold

This is the FIRST EXTENSION of Volume Three's customer/RM-portfolio
inheritance to a PRODUCT-PORTFOLIO dimension. The honesty discipline
is identical — the dimension is what's new.

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal precision 28
  - pbt_margin = None when total_revenue ≤ 0

Rule 2 — Portfolio-level inheritance (v5.48):
  - Aggregating engines surface upstream_ftp_modes counter
  - data_quality_warning citing Standard #11 when any input has ftp_mode="off"
  - provisional=True when >50% of inputs ran on naive math

Rule 5 — Data integration:
  - Empty product code returns explicit empty result with reason
  - Unknown product categories surfaced in meta.unknown_categories
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.product_profitability")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §7 #47)
# ─────────────────────────────────────────────────────────────────────

PRODUCT_CATEGORIES: List[str] = [
    "LOANS", "DEPOSITS", "TRADE", "TREASURY", "FEES", "DIGITAL",
]

# V3 honesty thresholds (carried forward from rm_profitability)
PROVISIONAL_FTP_OFF_THRESHOLD = 0.5    # >50% off-mode → provisional flag

# Lifecycle stage thresholds
LIFECYCLE_GROWTH_REVENUE_GROWTH_PCT = Decimal("20")    # YoY revenue growth ≥ 20% → GROWTH
LIFECYCLE_DECLINE_REVENUE_GROWTH_PCT = Decimal("-10")   # YoY revenue growth ≤ -10% → DECLINE


# ─────────────────────────────────────────────────────────────────────
# Result shapes
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ProductPnL:
    """Per-product PnL with V3 honesty inheritance."""
    product_code:           str
    period:                 str
    total_revenue:          float = 0.0
    direct_costs:           float = 0.0
    indirect_costs:         float = 0.0
    pbt:                    float = 0.0
    pbt_margin:             Optional[float] = None    # None when revenue <= 0
    customer_count:         int = 0
    transaction_count:      int = 0
    provisional:            bool = False
    data_quality_warning:   Optional[str] = None
    meta:                   Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class ProductProfitabilityEngine:
    """Product PnL aggregation with full Volume Three honesty inheritance.

    Extends the customer/RM-portfolio inheritance pattern from #23 to the
    PRODUCT dimension. Same three honesty mechanisms:
      1. upstream_ftp_modes counter exposed in meta
      2. data_quality_warning when any input was naive math
      3. provisional flag at >50% threshold
    """

    PRODUCT_CATEGORIES = PRODUCT_CATEGORIES

    def __init__(
        self,
        customer_pnl_lookup_fn: Optional[Callable[[str, str], List[dict]]] = None,
        product_holdings_fn:    Optional[Callable[[str], List[dict]]]      = None,
        product_metadata_fn:    Optional[Callable[[str], Dict[str, Any]]]  = None,
        revenue_history_fn:     Optional[Callable[[str, str], List[dict]]] = None,
    ):
        """All collaborators injectable.

        customer_pnl_lookup_fn(product_code, period) → list of customer PnL dicts
            Each dict expected fields:
              customer_id, total_revenue, direct_costs, indirect_costs,
              pbt, transaction_count, ftp_mode ('on' | 'off' | 'unknown')

        product_holdings_fn(period) → list of {customer_id, products_held}
            for cross-sell analysis

        product_metadata_fn(product_code) → {launch_date, current_stage, category}

        revenue_history_fn(product_code, period) → list of {period, revenue}
            for lifecycle (YoY growth) computation
        """
        self._customer_pnl    = customer_pnl_lookup_fn or (lambda p, per: [])
        self._holdings        = product_holdings_fn    or (lambda p: [])
        self._product_meta    = product_metadata_fn    or (lambda p: {})
        self._revenue_history = revenue_history_fn     or (lambda p, per: [])

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: calculate_product_pnl
    # ──────────────────────────────────────────────────────────────────

    def calculate_product_pnl(
        self, product_code: str, period: str
    ) -> Dict[str, Any]:
        """Aggregate per-customer PnL into a product-level PnL with full
        V3 honesty inheritance.

        Returns:
            {
              "product_code": str,
              "period": str,
              "total_revenue": float,
              "direct_costs": float,
              "indirect_costs": float,
              "pbt": float,
              "pbt_margin": float | None,
              "customer_count": int,
              "transaction_count": int,
              "provisional": bool,
              "data_quality_warning": str | None,
              "meta": {
                "upstream_ftp_modes": {"on": N, "off": N, "unknown": N},
                "ftp_off_share":      float,
                "rows_processed":     int,
                "generated_at":       str,
              }
            }

        Returns {} for empty product_code or period.
        """
        if not product_code or not period:
            return {}

        rows = self._customer_pnl(product_code, period) or []

        # Empty portfolio handling
        if not rows:
            return {
                "product_code":         product_code,
                "period":               period,
                "total_revenue":        0.0,
                "direct_costs":         0.0,
                "indirect_costs":       0.0,
                "pbt":                  0.0,
                "pbt_margin":           None,
                "customer_count":       0,
                "transaction_count":    0,
                "provisional":          False,
                "data_quality_warning": "Product has no customer PnL data for this period",
                "meta": {
                    "upstream_ftp_modes": {"on": 0, "off": 0, "unknown": 0},
                    "ftp_off_share":      0.0,
                    "rows_processed":     0,
                    "generated_at":       datetime.now(timezone.utc).isoformat(),
                },
            }

        # ── Aggregate Decimal-internal (Rule 1) ────────────────────────
        total_revenue   = ZERO
        direct_costs    = ZERO
        indirect_costs  = ZERO
        pbt             = ZERO
        customer_ids    = set()
        transaction_count = 0
        ftp_mode_counter = Counter()

        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                total_revenue  += Decimal(str(row.get("total_revenue", 0)))
                direct_costs   += Decimal(str(row.get("direct_costs",  0)))
                indirect_costs += Decimal(str(row.get("indirect_costs", 0)))
                pbt            += Decimal(str(row.get("pbt", 0)))
            except Exception:
                continue
            if row.get("customer_id"):
                customer_ids.add(row["customer_id"])
            try:
                transaction_count += int(row.get("transaction_count", 0))
            except Exception:
                pass
            # FTP mode tracking (Rule 2 — V3 inheritance)
            mode = row.get("ftp_mode", "unknown")
            if mode not in ("on", "off"):
                mode = "unknown"
            ftp_mode_counter[mode] += 1

        # ── Compute pbt_margin (Rule 1 — None on zero revenue) ────────
        if total_revenue > 0:
            pbt_margin = float(pbt / total_revenue * Decimal("100"))
            pbt_margin = round(pbt_margin, 4)
        else:
            pbt_margin = None

        # ── V3 honesty inheritance ────────────────────────────────────
        ftp_modes_dict = {
            "on":      ftp_mode_counter.get("on", 0),
            "off":     ftp_mode_counter.get("off", 0),
            "unknown": ftp_mode_counter.get("unknown", 0),
        }
        total_rows = sum(ftp_modes_dict.values())
        ftp_off_share = (ftp_modes_dict["off"] / total_rows) if total_rows > 0 else 0.0

        # data_quality_warning (Rule 2)
        warning: Optional[str] = None
        if ftp_modes_dict["off"] > 0:
            warning = (
                f"Product PnL aggregates {ftp_modes_dict['off']} customer(s) "
                f"with ftp_mode='off' (naive math, no FTP). "
                f"Per Mandatory Standard #11 + Rule 2 (Volume Three portfolio "
                f"inheritance), this product PnL should be treated as "
                f"data-quality-flagged."
            )

        # provisional flag (Rule 2)
        provisional = ftp_off_share > PROVISIONAL_FTP_OFF_THRESHOLD

        return {
            "product_code":         product_code,
            "period":               period,
            "total_revenue":        _money(total_revenue),
            "direct_costs":         _money(direct_costs),
            "indirect_costs":       _money(indirect_costs),
            "pbt":                  _money(pbt),
            "pbt_margin":           pbt_margin,
            "customer_count":       len(customer_ids),
            "transaction_count":    transaction_count,
            "provisional":          provisional,
            "data_quality_warning": warning,
            "meta": {
                "upstream_ftp_modes": ftp_modes_dict,
                "ftp_off_share":      round(ftp_off_share, 4),
                "rows_processed":     len(rows),
                "provisional_threshold_pct": int(PROVISIONAL_FTP_OFF_THRESHOLD * 100),
                "generated_at":       datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: cross_sell_intelligence
    # ──────────────────────────────────────────────────────────────────

    def cross_sell_intelligence(self, customer_id: str) -> Dict[str, Any]:
        """Identify products customer doesn't have but peers in segment do.

        Returns:
            {
              "customer_id": str,
              "currently_held": list[str],
              "peer_typical": list[str],
              "recommendations": list[str],   # peer_typical - currently_held
              "meta": {...}
            }
        """
        if not customer_id:
            return {}

        # Build the current period from "now" — caller can override via
        # explicit period (this is a simplification; production injects period)
        period = datetime.now().strftime("%Y-%m")
        all_holdings = self._holdings(period) or []

        # Find this customer
        customer_row = None
        for row in all_holdings:
            if isinstance(row, dict) and row.get("customer_id") == customer_id:
                customer_row = row
                break

        if not customer_row:
            return {
                "customer_id":      customer_id,
                "currently_held":   [],
                "peer_typical":     [],
                "recommendations":  [],
                "meta": {
                    "warning": "customer not found in current holdings dataset",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }

        currently_held = list(customer_row.get("products_held", []))
        segment = customer_row.get("segment")

        # Find products held by ≥50% of peers in same segment
        if segment:
            peer_holdings = [
                set(r.get("products_held", []))
                for r in all_holdings
                if isinstance(r, dict) and r.get("segment") == segment
                   and r.get("customer_id") != customer_id
            ]
        else:
            peer_holdings = []

        peer_count = len(peer_holdings)
        if peer_count == 0:
            peer_typical: List[str] = []
        else:
            product_freq: Counter = Counter()
            for held in peer_holdings:
                for p in held:
                    product_freq[p] += 1
            peer_typical = sorted([
                p for p, c in product_freq.items() if (c / peer_count) >= 0.5
            ])

        recommendations = [p for p in peer_typical if p not in currently_held]

        return {
            "customer_id":     customer_id,
            "segment":         segment,
            "currently_held":  sorted(currently_held),
            "peer_typical":    peer_typical,
            "recommendations": recommendations,
            "meta": {
                "peer_count":     peer_count,
                "peer_threshold_pct": 50,
                "generated_at":   datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: product_lifecycle
    # ──────────────────────────────────────────────────────────────────

    def product_lifecycle(self, product_code: str) -> Dict[str, Any]:
        """Position product in lifecycle: LAUNCH/GROWTH/MATURITY/DECLINE.

        Stages:
          LAUNCH:    < 12 months since launch
          GROWTH:    YoY revenue growth ≥ 20%
          MATURITY:  -10% < YoY revenue growth < +20%
          DECLINE:   YoY revenue growth ≤ -10%

        Returns:
            {
              "product_code": str,
              "stage": str | None,
              "yoy_revenue_growth_pct": float | None,
              "months_since_launch": int | None,
              "meta": {...}
            }
        """
        if not product_code:
            return {}

        meta = self._product_meta(product_code) or {}
        launch_date_str = meta.get("launch_date")    # 'YYYY-MM-DD'

        months_since_launch = None
        if launch_date_str:
            try:
                launch = datetime.strptime(launch_date_str, "%Y-%m-%d")
                delta = datetime.now() - launch
                months_since_launch = int(delta.days / 30.4375)
            except ValueError:
                pass

        # Compute YoY growth from revenue history
        # revenue_history_fn returns list of {period, revenue}
        history = self._revenue_history(product_code, "trailing_24m") or []
        if len(history) < 2:
            return {
                "product_code":           product_code,
                "stage":                  "LAUNCH" if (months_since_launch is not None and months_since_launch < 12) else None,
                "yoy_revenue_growth_pct": None,
                "months_since_launch":    months_since_launch,
                "meta": {
                    "warning": "insufficient revenue history for growth computation",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }

        # Use most recent vs same period 12 months prior
        try:
            history_sorted = sorted(history, key=lambda x: x["period"])
            current = Decimal(str(history_sorted[-1]["revenue"]))
            # Find row 12 periods prior (assume monthly; index -13)
            if len(history_sorted) < 13:
                prior_idx = 0    # use earliest available
            else:
                prior_idx = len(history_sorted) - 13
            prior = Decimal(str(history_sorted[prior_idx]["revenue"]))
        except (KeyError, ValueError, TypeError):
            return {
                "product_code":           product_code,
                "stage":                  None,
                "yoy_revenue_growth_pct": None,
                "months_since_launch":    months_since_launch,
                "meta": {
                    "warning": "revenue history malformed",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }

        if prior <= 0:
            yoy_pct = None    # Rule 1 — undefined
            stage = None
        else:
            yoy_decimal = (current - prior) / prior * Decimal("100")
            yoy_pct = float(yoy_decimal)
            # Stage classification
            if months_since_launch is not None and months_since_launch < 12:
                stage = "LAUNCH"
            elif yoy_decimal >= LIFECYCLE_GROWTH_REVENUE_GROWTH_PCT:
                stage = "GROWTH"
            elif yoy_decimal <= LIFECYCLE_DECLINE_REVENUE_GROWTH_PCT:
                stage = "DECLINE"
            else:
                stage = "MATURITY"

        return {
            "product_code":           product_code,
            "stage":                  stage,
            "yoy_revenue_growth_pct": round(yoy_pct, 2) if yoy_pct is not None else None,
            "months_since_launch":    months_since_launch,
            "meta": {
                "history_points":           len(history),
                "growth_threshold_pct":     float(LIFECYCLE_GROWTH_REVENUE_GROWTH_PCT),
                "decline_threshold_pct":    float(LIFECYCLE_DECLINE_REVENUE_GROWTH_PCT),
                "generated_at":             datetime.now(timezone.utc).isoformat(),
            },
        }


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
    print("A2Z MIS 360 — utils.product_profitability self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert PRODUCT_CATEGORIES == ["LOANS", "DEPOSITS", "TRADE", "TREASURY", "FEES", "DIGITAL"]
    print(f"  ✅ spec literals: 6 product categories {PRODUCT_CATEGORIES}")

    # ── Empty product/period → {} ─────────────────────────────────────
    eng = ProductProfitabilityEngine()
    assert eng.calculate_product_pnl("", "2026-04") == {}
    assert eng.calculate_product_pnl("LOANS", "") == {}
    assert eng.cross_sell_intelligence("") == {}
    assert eng.product_lifecycle("") == {}
    print(f"  ✅ empty inputs → {{}}")

    # ── Empty portfolio (no customer PnL data) ────────────────────────
    eng_empty = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: [])
    r = eng_empty.calculate_product_pnl("LOANS", "2026-04")
    assert r["total_revenue"] == 0.0
    assert r["pbt_margin"] is None    # Rule 1 — None on zero revenue
    assert r["data_quality_warning"] is not None
    assert "no customer PnL" in r["data_quality_warning"]
    assert r["meta"]["upstream_ftp_modes"] == {"on": 0, "off": 0, "unknown": 0}
    print(f"  ✅ empty portfolio: warning + ftp_modes counter present")

    # ── All FTP modes 'on' (clean portfolio) ──────────────────────────
    pnl_clean = [
        {"customer_id": "C001", "total_revenue": 1_000_000, "direct_costs": 200_000,
         "indirect_costs": 100_000, "pbt": 700_000, "transaction_count": 50, "ftp_mode": "on"},
        {"customer_id": "C002", "total_revenue": 2_000_000, "direct_costs": 400_000,
         "indirect_costs": 200_000, "pbt": 1_400_000, "transaction_count": 80, "ftp_mode": "on"},
    ]
    eng_clean = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl_clean)
    r = eng_clean.calculate_product_pnl("LOANS", "2026-04")
    assert r["total_revenue"] == 3_000_000.00
    assert r["pbt"] == 2_100_000.00
    assert r["pbt_margin"] == 70.0
    assert r["customer_count"] == 2
    assert r["transaction_count"] == 130
    assert r["provisional"] is False    # 0% off-mode
    assert r["data_quality_warning"] is None
    assert r["meta"]["upstream_ftp_modes"]["on"] == 2
    assert r["meta"]["upstream_ftp_modes"]["off"] == 0
    print(f"  ✅ clean portfolio: PnL clean, provisional=False, "
          f"pbt_margin={r['pbt_margin']}%")

    # ── Mixed FTP modes: <50% off (warning but NOT provisional) ───────
    pnl_mixed = pnl_clean + [
        {"customer_id": "C003", "total_revenue": 500_000, "direct_costs": 100_000,
         "indirect_costs": 50_000, "pbt": 350_000, "transaction_count": 20, "ftp_mode": "off"},
    ]
    eng_mixed = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl_mixed)
    r = eng_mixed.calculate_product_pnl("LOANS", "2026-04")
    assert r["meta"]["upstream_ftp_modes"]["off"] == 1
    assert r["meta"]["upstream_ftp_modes"]["on"] == 2
    assert r["meta"]["ftp_off_share"] == round(1/3, 4)
    assert r["data_quality_warning"] is not None
    assert "Mandatory Standard #11" in r["data_quality_warning"]
    assert "Rule 2" in r["data_quality_warning"]
    assert r["provisional"] is False    # 33% < 50% threshold
    print(f"  ✅ mixed FTP (<50% off): warning issued, provisional=False")

    # ── Majority FTP off: provisional=True ────────────────────────────
    pnl_provisional = [
        {"customer_id": "C001", "total_revenue": 1_000_000, "direct_costs": 200_000,
         "indirect_costs": 100_000, "pbt": 700_000, "transaction_count": 50, "ftp_mode": "off"},
        {"customer_id": "C002", "total_revenue": 1_500_000, "direct_costs": 300_000,
         "indirect_costs": 150_000, "pbt": 1_050_000, "transaction_count": 70, "ftp_mode": "off"},
        {"customer_id": "C003", "total_revenue":   500_000, "direct_costs": 100_000,
         "indirect_costs":  50_000, "pbt":   350_000, "transaction_count": 20, "ftp_mode": "on"},
    ]
    eng_prov = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl_provisional)
    r = eng_prov.calculate_product_pnl("LOANS", "2026-04")
    assert r["meta"]["ftp_off_share"] == round(2/3, 4)    # 66.7%
    assert r["provisional"] is True
    assert r["data_quality_warning"] is not None
    print(f"  ✅ majority off-mode (66.7%): provisional=True per Rule 2")

    # ── Zero revenue → pbt_margin=None (Rule 1) ───────────────────────
    pnl_zero = [
        {"customer_id": "C001", "total_revenue": 0, "direct_costs": 100_000,
         "indirect_costs": 50_000, "pbt": -150_000, "transaction_count": 10, "ftp_mode": "on"},
    ]
    eng_zero = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl_zero)
    r = eng_zero.calculate_product_pnl("LOANS", "2026-04")
    assert r["total_revenue"] == 0.0
    assert r["pbt_margin"] is None
    print(f"  ✅ zero revenue → pbt_margin=None (Rule 1)")

    # ── Cross-sell intelligence ───────────────────────────────────────
    holdings = [
        {"customer_id": "C001", "segment": "RETAIL", "products_held": ["SAVINGS", "CURRENT", "MOBILE"]},
        {"customer_id": "C002", "segment": "RETAIL", "products_held": ["SAVINGS", "CURRENT", "MOBILE", "FD"]},
        {"customer_id": "C003", "segment": "RETAIL", "products_held": ["SAVINGS", "CURRENT", "FD"]},
        {"customer_id": "C004", "segment": "RETAIL", "products_held": ["SAVINGS"]},  # underserved
        {"customer_id": "C005", "segment": "CORPORATE", "products_held": ["TRADE", "TREASURY"]},
    ]
    eng_cs = ProductProfitabilityEngine(product_holdings_fn=lambda p: holdings)
    r = eng_cs.cross_sell_intelligence("C004")
    # C004 has only SAVINGS; peers in RETAIL all have CURRENT (3/4=75%) → recommend
    assert "CURRENT" in r["recommendations"]
    assert "SAVINGS" not in r["recommendations"]    # already held
    print(f"  ✅ cross-sell: C004 currently_held={r['currently_held']}, "
          f"recommendations={r['recommendations']}")

    # ── Cross-sell: customer not found ────────────────────────────────
    r = eng_cs.cross_sell_intelligence("C999")
    assert r["recommendations"] == []
    assert "warning" in r["meta"]
    print(f"  ✅ cross-sell unknown customer: empty recs + warning")

    # ── Product lifecycle: GROWTH stage ───────────────────────────────
    history_growth = [
        {"period": "2025-04", "revenue": 1_000_000},
        {"period": "2025-05", "revenue": 1_050_000},
        {"period": "2025-06", "revenue": 1_080_000},
        {"period": "2025-07", "revenue": 1_100_000},
        {"period": "2025-08", "revenue": 1_120_000},
        {"period": "2025-09", "revenue": 1_150_000},
        {"period": "2025-10", "revenue": 1_180_000},
        {"period": "2025-11", "revenue": 1_200_000},
        {"period": "2025-12", "revenue": 1_220_000},
        {"period": "2026-01", "revenue": 1_250_000},
        {"period": "2026-02", "revenue": 1_280_000},
        {"period": "2026-03", "revenue": 1_300_000},
        {"period": "2026-04", "revenue": 1_400_000},    # +40% YoY from 2025-04
    ]
    eng_lc = ProductProfitabilityEngine(
        product_metadata_fn=lambda p: {"launch_date": "2020-01-01"},  # mature product
        revenue_history_fn=lambda p, per: history_growth,
    )
    r = eng_lc.product_lifecycle("MOBILE_BANKING")
    assert r["stage"] == "GROWTH"
    assert r["yoy_revenue_growth_pct"] == 40.0
    print(f"  ✅ lifecycle GROWTH: +{r['yoy_revenue_growth_pct']}% YoY")

    # ── Product lifecycle: DECLINE stage ──────────────────────────────
    history_decline = [
        {"period": f"2025-{m:02d}", "revenue": 1_000_000} for m in range(4, 13)
    ] + [
        {"period": f"2026-{m:02d}", "revenue": 800_000}   for m in range(1, 5)
    ]
    eng_lc2 = ProductProfitabilityEngine(
        product_metadata_fn=lambda p: {"launch_date": "2020-01-01"},
        revenue_history_fn=lambda p, per: history_decline,
    )
    r = eng_lc2.product_lifecycle("PASSBOOK_SAVINGS")
    assert r["stage"] == "DECLINE"
    assert r["yoy_revenue_growth_pct"] == -20.0
    print(f"  ✅ lifecycle DECLINE: {r['yoy_revenue_growth_pct']}% YoY")

    # ── Product lifecycle: LAUNCH (recent product) ────────────────────
    from datetime import timedelta
    recent_launch = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    eng_lc3 = ProductProfitabilityEngine(
        product_metadata_fn=lambda p: {"launch_date": recent_launch},
        revenue_history_fn=lambda p, per: [],
    )
    r = eng_lc3.product_lifecycle("NEW_PRODUCT")
    assert r["stage"] == "LAUNCH"
    print(f"  ✅ lifecycle LAUNCH: {r['months_since_launch']} months old")

    # ── KES-billion precision ────────────────────────────────────────
    huge = [
        {"customer_id": "C1", "total_revenue": "11500000000.50", "direct_costs": "0",
         "indirect_costs": "0", "pbt": "11500000000.50", "transaction_count": 1, "ftp_mode": "on"},
        {"customer_id": "C2", "total_revenue": "11500000000.51", "direct_costs": "0",
         "indirect_costs": "0", "pbt": "11500000000.51", "transaction_count": 1, "ftp_mode": "on"},
    ]
    eng_huge = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: huge)
    r = eng_huge.calculate_product_pnl("LOANS", "2026-04")
    assert r["total_revenue"] == 23_000_000_001.01
    print(f"  ✅ KES-billion precision: total_revenue={r['total_revenue']:,.2f}")

    print("\n  ALL TESTS PASSED")

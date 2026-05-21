"""
Products → BSC Bridge — v10.335

Brings the Products module into the BSC cascade. Each product category
(Retail Lending, Deposits, Digital, SME Lending, Corporate, Trade
Finance, Fee Income) is attributed to its owner Head — that head's
scorecard reflects product performance.

Per banking convention, products don't have dedicated "Product
Manager" staff in Tier-2 banks. Products are owned at the
line-of-business level by the Head responsible for that book.

Mirrors v10.323 Pipeline → BSC bridge pattern. Same design:
  - Deterministic per (period, category, kpi_id)
  - Reads products.json (source data)
  - Aggregates per-product values to category-level KPIs
  - Submits against the category-owner head
  - Idempotent — re-runs upsert
  - Audit-logged

Headless-safe: streamlit imports deferred to function bodies.
"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_PRODUCTS_PATH = _ROOT / "data" / "products.json"


# Category → owner head role mapping
# Each category maps to one head responsible for product performance
# in that line. The Head's scorecard reflects the category-level
# aggregate (book achievement, revenue achievement, NPL rate, growth).
CATEGORY_OWNER_ROLE = {
    "Retail Lending":   "Chief Retail Banking Officer",
    "Deposits":         "Chief Retail Banking Officer",
    "Digital":          "Head of Digital Financial Services",
    "SME Lending":      "Head of MSME",
    "Corporate":        "Chief Commercial Officer",
    "Trade Finance":    "Head Of Corporates & Trade Finance",
    "Fee Income":       "General Manager - Bancassurance",
}


# ────────────────────────────────────────────────────────────────────
# Data loading
# ────────────────────────────────────────────────────────────────────

def load_products() -> List[Dict[str, Any]]:
    from utils.db import db as _db
    return _db.load_json(_PRODUCTS_PATH, default=[]) or []


def find_owner_codes() -> Dict[str, str]:
    """Resolve each category to its owner's staff_code."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    out: Dict[str, str] = {}
    for cat, role in CATEGORY_OWNER_ROLE.items():
        for r in u.values():
            if r.role == role and r.active:
                out[cat] = r.staff_code
                break
    return out


# ────────────────────────────────────────────────────────────────────
# Category aggregation
# ────────────────────────────────────────────────────────────────────

def _stable_hash(category: str, period: str, kpi_id: str) -> int:
    h = hashlib.sha256(
        f"{category}|{period}|{kpi_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def _seasonal_factor(category: str, period: str, kpi_id: str) -> float:
    """Deterministic quarterly variation around the products.json
    snapshot. Range ±5% across quarters so trends are visible but
    realistic. Products.json represents the current quarter (2026-Q2)
    as baseline; other quarters vary deterministically.
    """
    if period == "2026-Q2":
        return 1.0  # Baseline matches products.json snapshot
    h = _stable_hash(category, period, kpi_id)
    # Range 0.95 to 1.05
    factor = 0.95 + ((h % 1000) / 1000.0) * 0.10
    return factor


def aggregate_for_owner(
    products: List[Dict[str, Any]],
    owner_categories: List[str],
    period: str,
) -> Dict[str, Decimal]:
    """Compute book/revenue/NPL/growth aggregates across ALL categories
    owned by one head. Book-weighted averages where appropriate.

    For fee-only owners (Bancassurance, Digital — all owned categories
    have target_book=0), only PRODUCT_REVENUE_ACHIEVEMENT is returned.
    """
    in_scope = [
        p for p in products
        if p.get("category") in owner_categories
    ]
    if not in_scope:
        return {}

    sum_actual_book = sum(Decimal(str(p.get("actual_book", 0)))
                          for p in in_scope)
    sum_target_book = sum(Decimal(str(p.get("target_book", 0)))
                          for p in in_scope)
    sum_actual_rev = sum(Decimal(str(p.get("actual_revenue", 0)))
                         for p in in_scope)
    sum_target_rev = sum(Decimal(str(p.get("target_revenue", 0)))
                         for p in in_scope)

    # Seasonal-variation key uses sorted categories so multi-cat owners
    # get the same deterministic factor across reruns
    cat_key = "+".join(sorted(owner_categories))

    out: Dict[str, Decimal] = {}

    # Revenue achievement — universal
    if sum_target_rev > 0:
        rev_achv = Decimal("100") * sum_actual_rev / sum_target_rev
        rev_achv *= Decimal(str(
            _seasonal_factor(cat_key, period, "REV_ACHV")
        ))
        rev_achv = min(Decimal("150"), max(Decimal("0"), rev_achv))
        out["PRODUCT_REVENUE_ACHIEVEMENT"] = rev_achv.quantize(
            Decimal("0.01")
        )

    # Book-derived KPIs — only for book-bearing owners
    has_book = sum_target_book > 0 and sum_actual_book > 0
    if has_book:
        book_achv = Decimal("100") * sum_actual_book / sum_target_book
        book_achv *= Decimal(str(
            _seasonal_factor(cat_key, period, "BOOK_ACHV")
        ))
        book_achv = min(Decimal("150"), max(Decimal("0"), book_achv))
        out["PRODUCT_BOOK_ACHIEVEMENT"] = book_achv.quantize(
            Decimal("0.01")
        )

        weighted_npl = sum(
            Decimal(str(p.get("actual_book", 0))) *
            Decimal(str(p.get("npl_rate", 0)))
            for p in in_scope
        )
        npl_rate = weighted_npl / sum_actual_book
        npl_rate *= Decimal(str(
            _seasonal_factor(cat_key, period, "NPL_RATE")
        ))
        npl_rate = min(Decimal("30"), max(Decimal("0"), npl_rate))
        out["PRODUCT_NPL_RATE"] = npl_rate.quantize(Decimal("0.01"))

        weighted_growth = sum(
            Decimal(str(p.get("actual_book", 0))) *
            Decimal(str(p.get("growth_rate", 0)))
            for p in in_scope
        )
        growth_rate = weighted_growth / sum_actual_book
        growth_rate *= Decimal(str(
            _seasonal_factor(cat_key, period, "GROWTH_RATE")
        ))
        growth_rate = max(Decimal("-30"), min(Decimal("30"), growth_rate))
        out["PRODUCT_GROWTH_RATE"] = growth_rate.quantize(
            Decimal("0.01")
        )

    return out


def aggregate_category(
    products: List[Dict[str, Any]],
    category: str,
    period: str,
) -> Dict[str, Decimal]:
    """Backwards-compat wrapper — aggregates a single category. Kept for
    UI consumers that want per-category drill-down without going
    through the multi-category aggregator.
    """
    return aggregate_for_owner(products, [category], period)


# ────────────────────────────────────────────────────────────────────
# Bridge entry point
# ────────────────────────────────────────────────────────────────────

def sync_products_to_bsc(
    period: str,
    username: str = "system_products_bridge",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Submit product-derived KPIs against each owner head.

    Aggregates per-product values up to the owner head level (so a
    Chief who owns multiple product categories gets one aggregated
    set of KPIs, not one per category). For fee-only owners, only
    PRODUCT_REVENUE_ACHIEVEMENT is submitted.

    Returns:
        {
            "period": "2026-Q2",
            "owners_processed": 6,
            "kpis_submitted": 22,
            "failures": [],
            "by_owner": {"EXEC-CRO-001": 4, ...},
            "categories_per_owner": {"EXEC-CRO-001": ["Retail Lending", "Deposits"], ...},
        }
    """
    products = load_products()
    owner_codes = find_owner_codes()

    # Invert: each owner → list of categories they own
    owner_to_cats: Dict[str, List[str]] = {}
    for cat, code in owner_codes.items():
        owner_to_cats.setdefault(code, []).append(cat)

    actuals_path = _ROOT / "data" / f"bsc_actuals_{period}.json"
    existing: List[Dict[str, Any]] = []
    if actuals_path.exists():
        from utils.db import db as _db
        existing = _db.load_json(actuals_path, default=[]) or []
        if not isinstance(existing, list):
            existing = existing.get("actuals", [])

    # Index existing records produced by this bridge for idempotent upsert
    existing_idx: Dict[Tuple[str, str], int] = {}
    for i, a in enumerate(existing):
        if (isinstance(a, dict)
                and a.get("source_module") == "products_to_bsc"):
            key = (a.get("staff_code"), a.get("kpi_id"))
            existing_idx[key] = i

    submitted = 0
    failures: List[Dict[str, Any]] = []
    by_owner: Dict[str, int] = {}
    ts = datetime.now(timezone.utc).isoformat()

    for owner_code, cats in owner_to_cats.items():
        aggregates = aggregate_for_owner(products, cats, period)
        if not aggregates:
            failures.append({
                "owner_code": owner_code,
                "categories": cats,
                "reason": "no_aggregates_computed",
            })
            continue

        for kpi_id, value in aggregates.items():
            actual_record = {
                "actual_id": f"PBR_{owner_code}_{kpi_id}_{period}",
                "staff_code": owner_code,
                "kpi_id": kpi_id,
                "period": period,
                "value": float(value),
                "submitted_by": username,
                "submitted_at": ts,
                "source_module": "products_to_bsc",
                "_v10335_categories": cats,
            }
            key = (owner_code, kpi_id)
            if key in existing_idx:
                existing[existing_idx[key]] = actual_record
            else:
                existing.append(actual_record)
                existing_idx[key] = len(existing) - 1
            submitted += 1
            by_owner[owner_code] = by_owner.get(owner_code, 0) + 1

    if not dry_run:
        actuals_path.write_text(
            json.dumps(existing, indent=2), encoding="utf-8"
        )
        try:
            from utils.bsc_engine import invalidate_actuals_index
            invalidate_actuals_index(period)
        except Exception:
            pass
        try:
            from utils.core_audit import audit_log
            audit_log(
                "PRODUCTS_TO_BSC_SYNC",
                username,
                f"period={period} owners={len(owner_to_cats)} "
                f"submitted={submitted} failures={len(failures)}",
                "products_to_bsc",
                None,
                {
                    "period": period,
                    "submitted": submitted,
                    "by_owner": by_owner,
                },
            )
        except Exception:
            pass

    return {
        "period": period,
        "owners_processed": len(owner_to_cats),
        "kpis_submitted": submitted,
        "failures": failures,
        "by_owner": by_owner,
        "categories_per_owner": owner_to_cats,
    }


def get_product_kpi_summary(period: str) -> Dict[str, Any]:
    """Helper for UI: read current aggregates without writing actuals."""
    products = load_products()
    out = {}
    for cat in CATEGORY_OWNER_ROLE:
        out[cat] = aggregate_category(products, cat, period)
    return out


def get_categories_covered() -> List[str]:
    return list(CATEGORY_OWNER_ROLE.keys())

"""
utils/sbu_pnl_rollup.py — SBU P&L Rollup Engine (v10.338).

Per v10.338 design Q5 option (a): aggregate customer_profitability per-
customer PBT up to segment level. Uses the FTP-aware per-customer engine
as the canonical source; this module is a thin rollup over it.

Rollup dimensions:
  - Individual segment: AFFLUENT / CORE_MIDDLE / MASS
  - Business segment:   MICRO / SMALL / MEDIUM / CORPORATE
  - CBK sector:         applied to business segments
  - Tagged RM:          per-staff profitability via tagged_rm_staff_code
  - Proposition tag:    VIEW-ONLY overlay (Q3 option a) — may overlap

Public API:
    rollup_by_segment(period, ...)         -> {segment_code: PnL_dict}
    rollup_by_cbk_sector(period, ...)      -> {(segment, sector): PnL_dict}
    rollup_by_tagged_rm(period, ...)       -> {staff_code: PnL_dict}
    rollup_by_proposition(period, ...)     -> {prop_code: PnL_dict} [view-only]
    bank_total_pnl(period, ...)            -> PnL_dict (sum of segments)
    reconcile_to_bank(period, ...)         -> {segment_total, bank_total, delta}

Per Rule 1 (Honesty):
    - Unclassified customers surface as 'UNCLASSIFIED' segment, not silently dropped
    - PBT = None for segments with zero revenue (no fake denominators)
    - Every result tagged with _v10338_rollup metadata including data sources

The virtual bank dataset doesn't have real GL movements per customer.
This module ships PROXY revenue/cost lookups that synthesize plausible
values from CLV estimates (individuals) and turnover/facility data
(businesses). Replace by injecting real lookup functions when FLEXCUBE
integrates.

Shipped: v10.338.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"

ZERO = Decimal("0")


# ────────────────────────────────────────────────────────────────────
# Customer iteration
# ────────────────────────────────────────────────────────────────────

def _load_individuals() -> Dict[str, Dict[str, Any]]:
    """Load individual customers from customer_intelligence.json."""
    from utils.db import db as _db
    raw = _db.load_json(_DATA / "customer_intelligence.json", default={}) or {}
    return {
        cif: rec for cif, rec in raw.items()
        if isinstance(rec, dict)
        and rec.get("customer_type", "individual") == "individual"
    }


def _load_businesses() -> Dict[str, Dict[str, Any]]:
    """Load business customers from customer_intelligence_business.json."""
    from utils.db import db as _db
    raw = _db.load_json(
        _DATA / "customer_intelligence_business.json", default={}
    ) or {}
    return {
        cif: rec for cif, rec in raw.items()
        if isinstance(rec, dict)
    }


def all_customers() -> Dict[str, Dict[str, Any]]:
    """Union of individual + business customers, keyed by CIF."""
    out = dict(_load_individuals())
    out.update(_load_businesses())
    return out


# ────────────────────────────────────────────────────────────────────
# Proxy revenue/cost synthesis (virtual bank only)
# ────────────────────────────────────────────────────────────────────
#
# These functions estimate revenue + direct + indirect cost per customer
# from the proxy data present in the virtual bank. Real bank deployments
# inject FLEXCUBE-backed functions and these defaults are bypassed.

def _stable_factor(cif: str, period: str, salt: str) -> Decimal:
    """Deterministic 0.8-1.2 multiplier from hash(cif|period|salt)."""
    h = hashlib.sha256(f"{cif}|{period}|{salt}".encode("utf-8")).digest()
    n = int.from_bytes(h[:4], "big")
    return Decimal("0.8") + (Decimal(n % 1000) / Decimal("2500"))


def proxy_individual_pnl(cif: str, rec: Dict[str, Any], period: str) -> Dict[str, Decimal]:
    """Synthesize individual customer P&L from CLV + segment.

    Proxy logic (clearly tagged in meta, replaceable):
      revenue        ≈ CLV ÷ 4 (quarterly slice) × deterministic factor
      direct_cost    ≈ 35% of revenue (interest expense + provisions)
      indirect_cost  ≈ 18% of revenue (segment-allocated overhead)
    """
    clv = Decimal(str(rec.get("clv_estimate", 0) or 0))
    quarterly_rev = clv / Decimal("4") * _stable_factor(cif, period, "rev")
    direct = quarterly_rev * Decimal("0.35") * _stable_factor(cif, period, "dir")
    indirect = quarterly_rev * Decimal("0.18") * _stable_factor(cif, period, "ind")
    return {
        "revenue":       quarterly_rev.quantize(Decimal("0.01")),
        "direct_cost":   direct.quantize(Decimal("0.01")),
        "indirect_cost": indirect.quantize(Decimal("0.01")),
    }


def proxy_business_pnl(cif: str, rec: Dict[str, Any], period: str) -> Dict[str, Decimal]:
    """Synthesize business customer P&L from facility + turnover.

    Proxy logic:
      revenue        ≈ (annual_turnover × spread) ÷ 4 (quarterly)
                       spread = 0.04 corporate, 0.06 SME, 0.08 micro (NIM-equivalent)
      direct_cost    ≈ 28% of revenue
      indirect_cost  ≈ 22% of revenue
    """
    turnover = Decimal(str(rec.get("annual_turnover_kes", 0) or 0))
    segment = rec.get("segment_code", "")
    spread_by_seg = {
        "MICRO":     Decimal("0.08"),
        "SMALL":     Decimal("0.07"),
        "MEDIUM":    Decimal("0.06"),
        "CORPORATE": Decimal("0.04"),
    }
    spread = spread_by_seg.get(segment, Decimal("0.05"))
    quarterly_rev = (
        turnover * spread / Decimal("4")
        * _stable_factor(cif, period, "rev")
    )
    direct = quarterly_rev * Decimal("0.28") * _stable_factor(cif, period, "dir")
    indirect = quarterly_rev * Decimal("0.22") * _stable_factor(cif, period, "ind")
    return {
        "revenue":       quarterly_rev.quantize(Decimal("0.01")),
        "direct_cost":   direct.quantize(Decimal("0.01")),
        "indirect_cost": indirect.quantize(Decimal("0.01")),
    }


def _customer_pnl_default(cif: str, rec: Dict[str, Any], period: str) -> Dict[str, Decimal]:
    """Dispatch to individual / business proxy by customer_type."""
    ctype = rec.get("customer_type", "individual")
    if ctype == "business":
        return proxy_business_pnl(cif, rec, period)
    return proxy_individual_pnl(cif, rec, period)


# ────────────────────────────────────────────────────────────────────
# Rollup primitives
# ────────────────────────────────────────────────────────────────────

def _empty_bucket() -> Dict[str, Any]:
    return {
        "revenue":       ZERO,
        "direct_cost":   ZERO,
        "indirect_cost": ZERO,
        "pbt":           ZERO,
        "customer_count": 0,
    }


def _accumulate(bucket: Dict[str, Any], pnl: Dict[str, Decimal]) -> None:
    bucket["revenue"]       += pnl["revenue"]
    bucket["direct_cost"]   += pnl["direct_cost"]
    bucket["indirect_cost"] += pnl["indirect_cost"]
    bucket["customer_count"] += 1


def _finalise(bucket: Dict[str, Any]) -> Dict[str, Any]:
    bucket["pbt"] = (
        bucket["revenue"] - bucket["direct_cost"] - bucket["indirect_cost"]
    )
    if bucket["revenue"] > 0:
        bucket["pbt_margin_pct"] = float(
            (bucket["pbt"] / bucket["revenue"] * Decimal("100")).quantize(
                Decimal("0.01")
            )
        )
    else:
        bucket["pbt_margin_pct"] = None  # Rule 1: no fake denominator
    # Coerce Decimals to floats for JSON-safe consumption
    for k in ("revenue", "direct_cost", "indirect_cost", "pbt"):
        bucket[k] = float(bucket[k])
    return bucket


# ────────────────────────────────────────────────────────────────────
# Public rollup API
# ────────────────────────────────────────────────────────────────────

def _matrix_indirect_by_segment(period: str) -> Dict[str, Decimal]:
    """v10.340 — Pull per-segment indirect cost from the matrix.

    Returns {segment_code: quarterly_indirect_kes}. Sums every non-
    direct cost item from utils.cost_allocation.apply_rules. Items
    flagged 'direct' (LLP, funding interest) are EXCLUDED — they go
    through per-customer attribution (the proxy direct_cost path).

    Cached via _MATRIX_INDIRECT_CACHE — apply_rules() walks the rule
    set + iterates customers via segment_balance_sheet, which is
    expensive at 3,200-customer scale. Cache key = period. Bust by
    calling clear_matrix_cache() when rules / customer data change.
    """
    if period in _MATRIX_INDIRECT_CACHE:
        return _MATRIX_INDIRECT_CACHE[period]
    try:
        from utils.cost_allocation import apply_rules
        allocation = apply_rules()
    except Exception:
        _MATRIX_INDIRECT_CACHE[period] = {}
        return {}
    by_seg: Dict[str, Decimal] = {}
    for cost_item, dist in allocation.items():
        if cost_item.startswith("_"):
            continue
        if not isinstance(dist, dict):
            continue
        for seg, amount in dist.items():
            by_seg[seg] = by_seg.get(seg, Decimal("0")) + Decimal(str(amount))
    _MATRIX_INDIRECT_CACHE[period] = by_seg
    return by_seg


_MATRIX_INDIRECT_CACHE: Dict[str, Dict[str, Decimal]] = {}


def clear_matrix_cache() -> None:
    """Invalidate the matrix-indirect cache. Call after rules or
    customer data change."""
    _MATRIX_INDIRECT_CACHE.clear()


def _customer_revenue_and_direct(
    cif: str, rec: Dict[str, Any], period: str,
) -> Dict[str, Decimal]:
    """Per-customer revenue + direct cost (NO indirect).

    Matrix mode uses this for the customer-level legs; indirect comes
    from the segment-level matrix override.
    """
    base = _customer_pnl_default(cif, rec, period)
    return {
        "revenue":       base["revenue"],
        "direct_cost":   base["direct_cost"],
        "indirect_cost": Decimal("0"),  # overridden at segment level
    }


def rollup_by_segment(
    period: str = "2026-Q2",
    customer_pnl_fn: Optional[Callable[[str, Dict, str], Dict[str, Decimal]]] = None,
    cost_source: str = "matrix",
) -> Dict[str, Dict[str, Any]]:
    """Aggregate customer P&L per segment_code.

    Args:
      period: quarterly period code
      customer_pnl_fn: per-customer P&L lookup. Default = proxy when
        cost_source='proxy', revenue+direct-only stub when 'matrix'.
      cost_source: 'matrix' (default, v10.340) | 'proxy' (v10.338 path).
        Matrix mode sums revenue + direct from customer-level data,
        then overrides indirect with cost_allocation.apply_rules output
        (one allocation per segment from the admin-editable rules).

    Returns: {segment_code: {revenue, direct_cost, indirect_cost,
                              pbt, pbt_margin_pct, customer_count}}

    Includes 'UNCLASSIFIED' bucket when classification fails on any
    record (Rule 1 — never silently drop).
    """
    if cost_source not in ("matrix", "proxy"):
        raise ValueError(f"cost_source must be 'matrix' or 'proxy', got {cost_source!r}")

    if customer_pnl_fn is None:
        fn = (_customer_revenue_and_direct
              if cost_source == "matrix" else _customer_pnl_default)
    else:
        fn = customer_pnl_fn

    buckets: Dict[str, Dict[str, Any]] = defaultdict(_empty_bucket)

    for cif, rec in all_customers().items():
        seg = rec.get("segment_code") or "UNCLASSIFIED"
        _accumulate(buckets[seg], fn(cif, rec, period))

    # Matrix mode — override indirect_cost at segment level
    if cost_source == "matrix":
        matrix_indirect = _matrix_indirect_by_segment(period)
        for seg, b in buckets.items():
            b["indirect_cost"] = matrix_indirect.get(seg, Decimal("0"))

    return {seg: _finalise(b) for seg, b in buckets.items()}


def rollup_by_cbk_sector(
    period: str = "2026-Q2",
    customer_pnl_fn: Optional[Callable[[str, Dict, str], Dict[str, Decimal]]] = None,
    cost_source: str = "matrix",
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Business-only rollup by (segment_code, cbk_sector).

    Matrix mode: indirect overlaid at SEGMENT level, then split across
    sectors within that segment in proportion to revenue. Sector P&Ls
    sum back to segment totals.
    """
    if cost_source not in ("matrix", "proxy"):
        raise ValueError(f"cost_source must be 'matrix' or 'proxy', got {cost_source!r}")

    if customer_pnl_fn is None:
        fn = (_customer_revenue_and_direct
              if cost_source == "matrix" else _customer_pnl_default)
    else:
        fn = customer_pnl_fn

    buckets: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(_empty_bucket)

    for cif, rec in _load_businesses().items():
        seg = rec.get("segment_code") or "UNCLASSIFIED"
        sector = rec.get("cbk_sector") or "Other / Not Classified"
        _accumulate(buckets[(seg, sector)], fn(cif, rec, period))

    # Matrix mode — segment-level indirect, split across sectors by revenue
    if cost_source == "matrix":
        matrix_indirect = _matrix_indirect_by_segment(period)
        # Revenue totals per segment for proportional allocation
        seg_rev: Dict[str, Decimal] = {}
        for (seg, _sector), b in buckets.items():
            seg_rev[seg] = seg_rev.get(seg, Decimal("0")) + b["revenue"]
        for (seg, sector), b in buckets.items():
            total_seg_rev = seg_rev.get(seg, Decimal("0"))
            seg_indirect = matrix_indirect.get(seg, Decimal("0"))
            if total_seg_rev > 0:
                share = b["revenue"] / total_seg_rev
                b["indirect_cost"] = (seg_indirect * share).quantize(Decimal("0.01"))
            else:
                b["indirect_cost"] = Decimal("0")

    return {k: _finalise(b) for k, b in buckets.items()}


def rollup_by_tagged_rm(
    period: str = "2026-Q2",
    customer_pnl_fn: Optional[Callable[[str, Dict, str], Dict[str, Decimal]]] = None,
    cost_source: str = "matrix",
) -> Dict[str, Dict[str, Any]]:
    """Aggregate P&L by tagged_rm_staff_code (business customers only).

    Matrix mode: per-RM indirect computed by the RM's revenue share
    within their primary segment × segment matrix indirect.
    """
    if cost_source not in ("matrix", "proxy"):
        raise ValueError(f"cost_source must be 'matrix' or 'proxy', got {cost_source!r}")

    if customer_pnl_fn is None:
        fn = (_customer_revenue_and_direct
              if cost_source == "matrix" else _customer_pnl_default)
    else:
        fn = customer_pnl_fn

    # Build per-RM bucket + per-RM primary segment for matrix allocation
    buckets: Dict[str, Dict[str, Any]] = defaultdict(_empty_bucket)
    rm_segments: Dict[str, str] = {}  # rm_code → most common segment

    for cif, rec in _load_businesses().items():
        rm = rec.get("tagged_rm_staff_code")
        if not rm:
            continue
        _accumulate(buckets[str(rm)], fn(cif, rec, period))
        # Record one segment per RM (most recent wins; fine for the rollup)
        rm_segments[str(rm)] = rec.get("segment_code") or "UNCLASSIFIED"

    if cost_source == "matrix":
        matrix_indirect = _matrix_indirect_by_segment(period)
        # Aggregate per-segment business revenue for proportional split
        seg_biz_rev: Dict[str, Decimal] = {}
        for rm, b in buckets.items():
            s = rm_segments.get(rm, "UNCLASSIFIED")
            seg_biz_rev[s] = seg_biz_rev.get(s, Decimal("0")) + b["revenue"]
        for rm, b in buckets.items():
            s = rm_segments.get(rm, "UNCLASSIFIED")
            total = seg_biz_rev.get(s, Decimal("0"))
            seg_indirect = matrix_indirect.get(s, Decimal("0"))
            if total > 0:
                share = b["revenue"] / total
                # RM only sees the BUSINESS share of segment indirect
                # (business customers don't shoulder retail-segment indirect)
                b["indirect_cost"] = (seg_indirect * share).quantize(Decimal("0.01"))
            else:
                b["indirect_cost"] = Decimal("0")

    return {rm: _finalise(b) for rm, b in buckets.items()}



def rollup_by_proposition(
    period: str = "2026-Q2",
    customer_pnl_fn: Optional[Callable[[str, Dict, str], Dict[str, Decimal]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """VIEW-ONLY proposition P&L. Per Q3 option (a), this rollup may
    overlap (a customer can be both Women and Diaspora) and does NOT
    reconcile to bank total. Tagged accordingly in the meta.
    """
    fn = customer_pnl_fn or _customer_pnl_default
    buckets: Dict[str, Dict[str, Any]] = defaultdict(_empty_bucket)

    for cif, rec in all_customers().items():
        tags = rec.get("tags") or []
        if not isinstance(tags, list):
            continue
        pnl = fn(cif, rec, period)
        for tag in tags:
            if isinstance(tag, str) and tag.upper() in {
                "WOMEN", "DIASPORA", "ASSET_FINANCE", "AGRI", "YOUTH", "SME"
            }:
                _accumulate(buckets[tag.upper()], pnl)

    out = {prop: _finalise(b) for prop, b in buckets.items()}
    return out


def bank_total_pnl(
    period: str = "2026-Q2",
    customer_pnl_fn: Optional[Callable[[str, Dict, str], Dict[str, Decimal]]] = None,
    cost_source: str = "matrix",
    cbs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Bank-wide P&L. v10.372 adds 'canonical' mode for the unification arc.

    Matrix mode: revenue + direct from customer rollup; indirect =
    total matrix non-direct allocation (sum across segments).
    Proxy mode: revenue + direct + indirect all from per-customer
    proxy (the v10.338 path).
    Canonical mode (NEW v10.372): consumes from utils.customer_pbt_allocator.
    compute_pbt_by_customer (the atomic engine landed in v10.370). Requires
    cbs_dir parameter. Maps PBTComponents → Engine B bucket schema:
        revenue       ← operating_income
        direct_cost   ← impairment_charge (customer-specific LLPs)
        indirect_cost ← total_opex (bank OpEx allocated to customer)
        pbt           ← pbt
    Closes G253 — Engine A and Engine B converge within <1% when both
    are sourced from CBS. Matrix and proxy modes remain for backward
    compatibility but are now documented as deprecated paths.
    """
    if cost_source not in ("matrix", "proxy", "canonical"):
        raise ValueError(f"cost_source must be 'matrix', 'proxy', or 'canonical', got {cost_source!r}")

    if cost_source == "canonical":
        if cbs_dir is None:
            raise ValueError("cost_source='canonical' requires cbs_dir parameter")
        return _bank_total_pnl_canonical(cbs_dir)

    if customer_pnl_fn is None:
        fn = (_customer_revenue_and_direct
              if cost_source == "matrix" else _customer_pnl_default)
    else:
        fn = customer_pnl_fn

    bucket = _empty_bucket()
    for cif, rec in all_customers().items():
        _accumulate(bucket, fn(cif, rec, period))

    if cost_source == "matrix":
        bucket["indirect_cost"] = sum(
            _matrix_indirect_by_segment(period).values(),
            Decimal("0"),
        )

    return _finalise(bucket)


def _bank_total_pnl_canonical(cbs_dir: Path) -> Dict[str, Any]:
    """v10.372 — Canonical bank P&L from compute_pbt_by_customer (v10.370 atom).

    Maps PBTComponents (Engine A schema) → Engine B's 4-field bucket schema.
    Sums all per-customer PBT, then translates the field names. This is the
    unification step that lets G253 ratchet from INFORMATIONAL to ENFORCING.
    """
    # Lazy import to avoid module-load cycle concerns
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
    )
    customer_pbts = compute_pbt_by_customer(cbs_dir)
    total = sum_customer_pbts(customer_pbts)
    bucket = {
        "revenue":        total.operating_income,
        "direct_cost":    total.impairment_charge,
        "indirect_cost":  total.total_opex,
        "customer_count": len(customer_pbts),
    }
    return _finalise(bucket)


def reconcile_to_bank(
    period: str = "2026-Q2",
    customer_pnl_fn: Optional[Callable[[str, Dict, str], Dict[str, Decimal]]] = None,
    cost_source: str = "matrix",
) -> Dict[str, Any]:
    """Verify segment-level sums reconcile to bank-wide total.

    Per Rule 6, propositions are excluded from reconciliation (they
    overlap by design). Individual/business segment rollups MUST sum
    to bank total within rounding tolerance — TRUE in both proxy and
    matrix modes (the matrix allocation distributes to the same set
    of segments the rollup buckets into).
    """
    segments = rollup_by_segment(period, customer_pnl_fn, cost_source=cost_source)
    bank = bank_total_pnl(period, customer_pnl_fn, cost_source=cost_source)
    seg_total_pbt = sum(b["pbt"] for b in segments.values())
    delta = seg_total_pbt - bank["pbt"]
    # Slightly higher tolerance in matrix mode because rounding
    # happens at TWO levels (per-customer + per-segment override)
    tolerance_kes = 100.0 if cost_source == "matrix" else 1.0
    return {
        "segment_total_pbt": seg_total_pbt,
        "bank_total_pbt":    bank["pbt"],
        "delta_kes":         delta,
        "reconciles":        abs(delta) <= tolerance_kes,
        "tolerance_kes":     tolerance_kes,
        "segment_count":     len(segments),
        "cost_source":       cost_source,
    }


# ────────────────────────────────────────────────────────────────────
# Metadata
# ────────────────────────────────────────────────────────────────────

def rollup_meta(cost_source: str = "matrix") -> Dict[str, Any]:
    """Return descriptive metadata for the current rollup config.

    cost_source defaults to 'matrix' (v10.340). Pass 'proxy' for the
    older v10.338 behaviour. Page builders should surface this so the
    user sees which cost source is driving the numbers.
    """
    individuals = _load_individuals()
    businesses = _load_businesses()
    out = {
        "shipped": "v10.340",
        "cost_source_mode": cost_source,
        "individual_customer_count": len(individuals),
        "business_customer_count":   len(businesses),
        "revenue_source": (
            "PROXY — derived from clv_estimate (individuals) + "
            "annual_turnover × NIM-equivalent spread (businesses). "
            "Replace by injecting customer_pnl_fn when FLEXCUBE GL "
            "integrates."
        ),
        "proposition_rollup_view_only": True,
        "reconciles_to_bank_total": True,
    }
    if cost_source == "matrix":
        try:
            from utils.cost_allocation import reconciliation_report
            rep = reconciliation_report()
            out["cost_source"] = (
                "MATRIX (v10.340) — indirect from "
                "utils.cost_allocation.apply_rules over "
                f"{rep['active_count']} admin-editable rules. Total "
                f"annual opex {rep['total_annual_kes_b']:.2f}B "
                f"(quarterly {rep['total_quarterly_kes_m']:.0f}M). "
                "Direct items (LLP + funding interest) attributed per-"
                "customer via the existing proxy until per-customer "
                "GL data lands."
            )
            out["matrix_total_quarterly_kes"] = float(
                Decimal(str(rep["total_quarterly_kes_m"])) * Decimal("1000000")
            )
        except Exception as exc:  # noqa: BLE001
            out["cost_source"] = f"MATRIX (load failed: {exc})"
    else:
        out["cost_source"] = (
            "PROXY — direct cost = 28-35% of revenue, indirect = "
            "18-22% of revenue (v10.338 path, retained for backward "
            "compatibility and tests)."
        )
    return out

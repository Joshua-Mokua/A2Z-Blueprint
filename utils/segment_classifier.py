"""
utils/segment_classifier.py — Canonical Segment Classification (v10.338)

Per Standard #69 + v10.338 design decisions, a customer is assigned to
EXACTLY ONE primary segment. Individual customers are tiered by TRB
(Total Relationship Balance); business customers are tiered by annual
turnover, with CBK economic sector as a second dimension.

Codes are FIXED and used by all engines (segment_balance_sheet,
segment_pnl_attribution rollup, cost matrix compute, SBU drill-down
page). Display names + thresholds are admin-editable via
data/segment_config.json — multi-tenant ready.

Public API:
    classify_individual(trb_kes)               -> 'AFFLUENT' | 'CORE_MIDDLE' | 'MASS'
    classify_business(turnover_kes)            -> 'MICRO' | 'SMALL' | 'MEDIUM' | 'CORPORATE'
    classify_customer(customer_record)         -> primary segment code
    list_tiers(customer_type='individual')     -> [tier configs]
    get_tier_config(code)                      -> tier dict | None
    list_cbk_sectors()                         -> [sector names]
    is_in_msme(business_code)                  -> bool

Per the v10.338 spec:
    - Customer type 'individual' → only AFFLUENT/CORE_MIDDLE/MASS valid
    - Customer type 'business'   → only MICRO/SMALL/MEDIUM/CORPORATE valid
    - CBK sector applies to ALL business tiers (Joshua's clarification)
    - MSME = MICRO + SMALL + MEDIUM (Large is Corporate, not MSME)
    - Propositions (WOMEN/DIASPORA/AGRI/etc.) are tags, NOT primary
      segments — they overlay this classification (view-only per Q3a)

Per Rule 1 (Honesty):
    classify_individual(trb=None)  → 'UNCLASSIFIED' (data quality issue)
    classify_business(turnover=None) → 'UNCLASSIFIED'
    classify_customer(record without type) → 'UNCLASSIFIED'

Shipped: v10.338.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "data" / "segment_config.json"

# Sentinel returned when classification cannot be determined (Rule 1)
UNCLASSIFIED = "UNCLASSIFIED"


def _load_config() -> Dict[str, Any]:
    """Load segment_config.json via the canonical db helper."""
    from utils.db import db as _db
    return _db.load_json(_CONFIG_PATH, default={}) or {}


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce to Decimal for comparison; None on failure."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


# ────────────────────────────────────────────────────────────────────
# Tier classification
# ────────────────────────────────────────────────────────────────────

def classify_individual(trb_kes: Any) -> str:
    """Classify an individual customer by Total Relationship Balance (KES).

    Returns one of the configured individual tier codes, or 'UNCLASSIFIED'
    when trb_kes is None / unparseable. Empty config → UNCLASSIFIED.
    """
    trb = _to_decimal(trb_kes)
    if trb is None:
        return UNCLASSIFIED

    config = _load_config()
    tiers = config.get("individual_tiers", [])
    if not tiers:
        return UNCLASSIFIED

    for tier in tiers:
        lo = _to_decimal(tier.get("trb_min_kes"))
        hi = _to_decimal(tier.get("trb_max_kes"))
        if lo is None:
            continue
        if trb < lo:
            continue
        if hi is not None and trb >= hi:
            continue
        return tier["code"]
    return UNCLASSIFIED


def classify_business(turnover_kes: Any) -> str:
    """Classify a business customer by annual turnover (KES).

    Returns one of MICRO / SMALL / MEDIUM / CORPORATE, or 'UNCLASSIFIED'.
    """
    turnover = _to_decimal(turnover_kes)
    if turnover is None:
        return UNCLASSIFIED

    config = _load_config()
    tiers = config.get("business_tiers", [])
    if not tiers:
        return UNCLASSIFIED

    for tier in tiers:
        lo = _to_decimal(tier.get("turnover_min_kes"))
        hi = _to_decimal(tier.get("turnover_max_kes"))
        if lo is None:
            continue
        if turnover < lo:
            continue
        if hi is not None and turnover >= hi:
            continue
        return tier["code"]
    return UNCLASSIFIED


def classify_customer(customer_record: Dict[str, Any]) -> str:
    """Classify a customer record (CIF + attributes) to a segment code.

    Looks at:
      - customer_type ('individual' | 'business' | 'INDIVIDUAL' | 'BUSINESS')
      - trb_kes / total_relationship_balance_kes / clv_estimate for individuals
      - annual_turnover_kes / turnover for businesses

    Falls back to 'UNCLASSIFIED' on any data-quality issue (Rule 1).
    """
    if not isinstance(customer_record, dict):
        return UNCLASSIFIED

    raw_type = (customer_record.get("customer_type") or "").strip().lower()
    if not raw_type:
        # Inference: legacy records flag "segment" with Affluent/Mass/etc → individual
        seg = (customer_record.get("segment") or "").strip().lower()
        if seg in ("affluent", "mass", "mass affluent", "core middle", "premium"):
            raw_type = "individual"
        elif seg in ("corporate", "sme", "micro", "small", "medium",
                     "msme", "business"):
            raw_type = "business"
        else:
            return UNCLASSIFIED

    if raw_type == "individual":
        trb = (
            customer_record.get("trb_kes")
            or customer_record.get("total_relationship_balance_kes")
            or customer_record.get("clv_estimate")
        )
        return classify_individual(trb)

    if raw_type == "business":
        turnover = (
            customer_record.get("annual_turnover_kes")
            or customer_record.get("turnover_kes")
            or customer_record.get("turnover")
        )
        return classify_business(turnover)

    return UNCLASSIFIED


# ────────────────────────────────────────────────────────────────────
# Lookup helpers
# ────────────────────────────────────────────────────────────────────

def list_tiers(customer_type: str = "individual") -> List[Dict[str, Any]]:
    """Return the configured tiers for 'individual' or 'business'."""
    config = _load_config()
    if customer_type.lower() == "individual":
        return list(config.get("individual_tiers", []))
    if customer_type.lower() == "business":
        return list(config.get("business_tiers", []))
    return []


def get_tier_config(code: str) -> Optional[Dict[str, Any]]:
    """Return the tier dict for a given canonical code, or None."""
    config = _load_config()
    for tier in config.get("individual_tiers", []):
        if tier.get("code") == code:
            return dict(tier)
    for tier in config.get("business_tiers", []):
        if tier.get("code") == code:
            return dict(tier)
    return None


def list_cbk_sectors() -> List[str]:
    """Return the configured CBK economic sector list."""
    config = _load_config()
    return list(config.get("cbk_sectors", []))


def is_in_msme(business_code: str) -> bool:
    """True if a business code is part of MSME (Micro/Small/Medium)."""
    tier = get_tier_config(business_code)
    if not tier:
        return False
    return bool(tier.get("in_msme", False))


def all_segment_codes() -> List[str]:
    """Return all valid primary segment codes (individual + business)."""
    out = []
    config = _load_config()
    for t in config.get("individual_tiers", []):
        out.append(t["code"])
    for t in config.get("business_tiers", []):
        out.append(t["code"])
    return out


def proposition_codes() -> List[str]:
    """Return the proposition codes (overlay tags, NOT primary segments)."""
    config = _load_config()
    return list(
        config.get("propositions_overlay", {}).get("propositions", [])
    )

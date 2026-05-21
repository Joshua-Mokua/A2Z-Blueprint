"""
utils/segment_balance_sheet.py — Per-SBU Balance Sheet (v10.338).

Complements sbu_pnl_rollup.py with a point-in-time view: assets,
liabilities, and equity allocated per segment.

Per BCBS standardised approach (and aligned with the existing
segment_pnl_attribution.py capital-allocation method):

  Assets       = sum of customer loan balances by segment
  Liabilities  = sum of customer deposit balances by segment
  Equity       = sum(rwa) × DEFAULT_CAPITAL_ADEQUACY_PCT (12.5%)
  Net assets   = Assets − Liabilities

The virtual bank does not have per-customer loan/deposit balance
records yet. This module ships PROXY allocations derived from:
  - Individuals: clv_estimate → asset / liability split using
                  segment-typical ratios (high-value carry more
                  loans, low-value carry mainly deposits)
  - Businesses:  max_facility_kes as the asset balance;
                  liability ≈ 35% of asset (working-capital balances)

Public API:
    balance_sheet_by_segment(period)        -> {segment: BS_dict}
    balance_sheet_by_cbk_sector(period)     -> {(seg, sector): BS_dict}
    bank_balance_sheet(period)              -> BS_dict (aggregate)
    capital_adequacy_check(period)          -> {ratio, adequate}
    bs_meta()                               -> data-source disclaimer

Per Rule 1: customers without classifiable data surface in
'UNCLASSIFIED' bucket (never silently dropped).

Shipped: v10.338.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"

DEFAULT_CAPITAL_ADEQUACY_PCT = Decimal("12.5")  # BCBS minimum
ZERO = Decimal("0")


# ────────────────────────────────────────────────────────────────────
# Segment-typical asset/liability ratios (admin-overridable in future)
# ────────────────────────────────────────────────────────────────────
# These map CLV → loan + deposit split by segment. Affluent customers
# typically carry more loans (mortgages, asset finance) AND more
# deposits (investment accounts). Mass customers carry mostly deposits
# (current/savings), less lending uptake.

_INDIVIDUAL_BS_RATIOS = {
    "AFFLUENT":     {"loan_to_clv": Decimal("8.0"),  "dep_to_clv": Decimal("12.0")},
    "CORE_MIDDLE":  {"loan_to_clv": Decimal("4.0"),  "dep_to_clv": Decimal("6.0")},
    "MASS":         {"loan_to_clv": Decimal("1.5"),  "dep_to_clv": Decimal("3.0")},
}

_BUSINESS_DEPOSIT_PCT_OF_FACILITY = Decimal("0.35")  # rough working-capital cycle


def _stable_factor(cif: str, period: str, salt: str) -> Decimal:
    """Deterministic 0.8-1.2 multiplier matching sbu_pnl_rollup."""
    h = hashlib.sha256(f"{cif}|{period}|{salt}".encode("utf-8")).digest()
    n = int.from_bytes(h[:4], "big")
    return Decimal("0.8") + (Decimal(n % 1000) / Decimal("2500"))


def _individual_bs(cif: str, rec: Dict[str, Any], period: str) -> Dict[str, Decimal]:
    """Per-individual asset/liability proxy from CLV."""
    clv = Decimal(str(rec.get("clv_estimate", 0) or 0))
    seg = rec.get("segment_code", "MASS")
    ratios = _INDIVIDUAL_BS_RATIOS.get(seg, _INDIVIDUAL_BS_RATIOS["MASS"])
    loan = clv * ratios["loan_to_clv"] * _stable_factor(cif, period, "loan")
    dep  = clv * ratios["dep_to_clv"]  * _stable_factor(cif, period, "dep")
    return {
        "loan_balance":    loan.quantize(Decimal("0.01")),
        "deposit_balance": dep.quantize(Decimal("0.01")),
    }


def _business_bs(cif: str, rec: Dict[str, Any], period: str) -> Dict[str, Decimal]:
    """Per-business asset/liability proxy from max facility."""
    facility = Decimal(str(rec.get("max_facility_kes", 0) or 0))
    asset_loan = facility * _stable_factor(cif, period, "loan")
    deposit = facility * _BUSINESS_DEPOSIT_PCT_OF_FACILITY * _stable_factor(cif, period, "dep")
    return {
        "loan_balance":    asset_loan.quantize(Decimal("0.01")),
        "deposit_balance": deposit.quantize(Decimal("0.01")),
    }


# ────────────────────────────────────────────────────────────────────
# Aggregation
# ────────────────────────────────────────────────────────────────────

def _empty_bs() -> Dict[str, Any]:
    return {
        "loan_balance":    ZERO,
        "deposit_balance": ZERO,
        "customer_count":  0,
    }


def _accumulate(bucket: Dict[str, Any], bs: Dict[str, Decimal]) -> None:
    bucket["loan_balance"]    += bs["loan_balance"]
    bucket["deposit_balance"] += bs["deposit_balance"]
    bucket["customer_count"]  += 1


def _finalise(bucket: Dict[str, Any]) -> Dict[str, Any]:
    """Compute RWA, equity, net assets. Coerce to floats for JSON."""
    # Simple RWA: loan_balance × 100% risk weight (BCBS standardised
    # for unsecured retail / commercial — production deployments
    # apply per-product weights via cost_allocation matrix + IFRS9 ECL)
    rwa = bucket["loan_balance"]
    equity = rwa * DEFAULT_CAPITAL_ADEQUACY_PCT / Decimal("100")
    net_assets = bucket["loan_balance"] - bucket["deposit_balance"]

    bucket["rwa"]          = rwa
    bucket["equity"]       = equity
    bucket["net_assets"]   = net_assets
    bucket["assets_total"] = bucket["loan_balance"]
    bucket["liabilities_total"] = bucket["deposit_balance"]

    for k in ("loan_balance", "deposit_balance", "rwa", "equity",
              "net_assets", "assets_total", "liabilities_total"):
        bucket[k] = float(bucket[k])
    return bucket


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────

def _load_all() -> Dict[str, Dict[str, Any]]:
    """Union of individual + business customers."""
    from utils.db import db as _db
    indiv = _db.load_json(_DATA / "customer_intelligence.json", default={}) or {}
    biz   = _db.load_json(_DATA / "customer_intelligence_business.json", default={}) or {}
    out = {}
    for cif, rec in indiv.items():
        if isinstance(rec, dict):
            out[cif] = rec
    for cif, rec in biz.items():
        if isinstance(rec, dict):
            out[cif] = rec
    return out


def balance_sheet_by_segment(period: str = "2026-Q2") -> Dict[str, Dict[str, Any]]:
    """Aggregate balance sheet per segment_code."""
    buckets: Dict[str, Dict[str, Any]] = defaultdict(_empty_bs)
    for cif, rec in _load_all().items():
        ctype = rec.get("customer_type", "individual")
        bs = _business_bs(cif, rec, period) if ctype == "business" \
             else _individual_bs(cif, rec, period)
        seg = rec.get("segment_code") or "UNCLASSIFIED"
        _accumulate(buckets[seg], bs)
    return {seg: _finalise(b) for seg, b in buckets.items()}


def balance_sheet_by_cbk_sector(
    period: str = "2026-Q2",
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Business-only B/S by (segment, sector)."""
    from utils.db import db as _db
    biz = _db.load_json(_DATA / "customer_intelligence_business.json", default={}) or {}
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(_empty_bs)
    for cif, rec in biz.items():
        if not isinstance(rec, dict):
            continue
        bs = _business_bs(cif, rec, period)
        seg = rec.get("segment_code") or "UNCLASSIFIED"
        sector = rec.get("cbk_sector") or "Other / Not Classified"
        _accumulate(buckets[(seg, sector)], bs)
    return {k: _finalise(b) for k, b in buckets.items()}


def bank_balance_sheet(period: str = "2026-Q2") -> Dict[str, Any]:
    """Bank-wide balance sheet aggregate."""
    bucket = _empty_bs()
    for cif, rec in _load_all().items():
        ctype = rec.get("customer_type", "individual")
        bs = _business_bs(cif, rec, period) if ctype == "business" \
             else _individual_bs(cif, rec, period)
        _accumulate(bucket, bs)
    return _finalise(bucket)


def capital_adequacy_check(period: str = "2026-Q2") -> Dict[str, Any]:
    """Bank-wide capital adequacy: actual ratio vs BCBS minimum."""
    bank = bank_balance_sheet(period)
    rwa = bank["rwa"]
    equity = bank["equity"]
    if rwa <= 0:
        return {
            "rwa":          rwa,
            "equity":       equity,
            "ratio_pct":    None,  # Rule 1
            "adequate":     None,
            "minimum_pct":  float(DEFAULT_CAPITAL_ADEQUACY_PCT),
        }
    ratio = (Decimal(str(equity)) / Decimal(str(rwa))) * Decimal("100")
    return {
        "rwa":          rwa,
        "equity":       equity,
        "ratio_pct":    float(ratio.quantize(Decimal("0.01"))),
        "adequate":     ratio >= DEFAULT_CAPITAL_ADEQUACY_PCT,
        "minimum_pct":  float(DEFAULT_CAPITAL_ADEQUACY_PCT),
    }


def bs_meta() -> Dict[str, Any]:
    return {
        "shipped": "v10.338",
        "asset_source": (
            "PROXY — individuals: clv_estimate × segment-typical loan "
            "multiplier; businesses: max_facility_kes × deterministic "
            "factor. Replace with FLEXCUBE per-customer loan balances "
            "when integrated."
        ),
        "liability_source": (
            "PROXY — individuals: clv_estimate × segment-typical "
            "deposit multiplier; businesses: 35% of facility. "
            "Replace with FLEXCUBE deposit balances when integrated."
        ),
        "equity_method": "RWA × 12.5% (BCBS standardised minimum)",
        "rwa_method": (
            "Simple — loan_balance × 100% risk weight. Production "
            "applies per-product BCBS weights + IFRS 9 ECL overlay."
        ),
    }

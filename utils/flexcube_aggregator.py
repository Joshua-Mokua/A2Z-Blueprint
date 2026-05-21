"""utils/flexcube_aggregator.py — FLEXCUBE Aggregator Layer (v7.10).

This module provides PORTFOLIO-LEVEL aggregations from FLEXCUBE for the
systems-layer stock snapshots. It complements `flexcube_adapter.py` which
operates at per-account / per-customer level.

The aggregator follows the same ACL (Anti-Corruption Layer) pattern from
Charter §7:

    A2Z domain code (system_stocks)
        ↓ (calls aggregator function)
    flexcube_aggregator
        ↓ (mode-aware: synthetic / mock / live)
    flexcube_adapter / live FLEXCUBE / demo defaults
        ↓
    Returns normalised aggregate dict with `data_source` provenance

The data_source field is the v7.10 honesty contract: every snapshot
attribution explicitly states whether the figures came from a live
FLEXCUBE call, the synthetic CBS data, or the v7.x demo defaults.

Three aggregations are surfaced today:
    - fetch_loan_portfolio_aggregate() → gross outstanding + by-segment + by-stage
    - fetch_deposit_book_aggregate()    → total deposits + by-stability tier + LDR
    - fetch_npl_aggregate()             → NPL inventory + by-stage + ratio

When mode=synthetic (the default), this reads from `cbs_data/` if it exists,
or falls back to demo defaults otherwise. When mode=live, this calls
flexcube_adapter.* aggregation endpoints (TBD — Ecobank Apigee).

Per Charter §7 Anti-Corruption Layer pattern:
    - This module does NOT leak FLEXCUBE-specific field names (e.g. ACCT_NO,
      CUST_REF) to A2Z domain code. Translates to A2Z's normalised vocabulary.
    - Returns dict with stable contract regardless of mode — calling code
      doesn't change when FLEXCUBE goes live.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from decimal import Decimal

# Reuse adapter's config + mode
from utils.flexcube_adapter import get_mode, get_config

DATA_DIR = Path(__file__).parent.parent / "data"
CBS_DIR = Path(__file__).parent.parent / "cbs_data"


# ══════════════════════════════════════════════════════════════════
# Public aggregators
# ══════════════════════════════════════════════════════════════════

def fetch_loan_portfolio_aggregate() -> Dict[str, Any]:
    """Aggregate loan portfolio snapshot for `loan_portfolio` stock.

    Per Charter §7 ACL pattern — returns A2Z's normalised dict regardless
    of upstream mode. Always includes `data_source` field for provenance.

    Returns dict with keys:
        gross_outstanding_kes, by_segment_kes, by_stage_kes, by_product_kes,
        weighted_avg_pd, average_lgd_pct, data_source, mode, computed_at
    """
    mode = get_mode()

    if mode == "live":
        result = _fetch_loan_portfolio_live()
        if result is not None:
            result["data_source"] = "flexcube_live"
            result["mode"] = "live"
            return result
        # Fall through if live call failed

    # Try CBS data first if mode is synthetic
    if mode in ("synthetic", "mock") and CBS_DIR.exists():
        result = _fetch_loan_portfolio_from_cbs()
        if result is not None:
            result["data_source"] = "cbs_synthetic"
            result["mode"] = mode
            return result

    # Demo defaults — Tier-2 Kenya bank loan book
    result = _loan_portfolio_demo_defaults()
    result["data_source"] = "demo_defaults"
    result["mode"] = mode
    return result


def fetch_deposit_book_aggregate() -> Dict[str, Any]:
    """Aggregate deposit book snapshot for `deposit_base` stock."""
    mode = get_mode()

    if mode == "live":
        result = _fetch_deposit_book_live()
        if result is not None:
            result["data_source"] = "flexcube_live"
            result["mode"] = "live"
            return result

    if mode in ("synthetic", "mock") and CBS_DIR.exists():
        result = _fetch_deposit_book_from_cbs()
        if result is not None:
            result["data_source"] = "cbs_synthetic"
            result["mode"] = mode
            return result

    result = _deposit_book_demo_defaults()
    result["data_source"] = "demo_defaults"
    result["mode"] = mode
    return result


def fetch_npl_aggregate() -> Dict[str, Any]:
    """Aggregate NPL snapshot for `npl_inventory` stock."""
    mode = get_mode()

    if mode == "live":
        result = _fetch_npl_live()
        if result is not None:
            result["data_source"] = "flexcube_live"
            result["mode"] = "live"
            return result

    if mode in ("synthetic", "mock") and CBS_DIR.exists():
        result = _fetch_npl_from_cbs()
        if result is not None:
            result["data_source"] = "cbs_synthetic"
            result["mode"] = mode
            return result

    result = _npl_demo_defaults()
    result["data_source"] = "demo_defaults"
    result["mode"] = mode
    return result


def fetch_customer_base_aggregate() -> Dict[str, Any]:
    """Aggregate customer base snapshot for `customer_base` stock (v7.11)."""
    mode = get_mode()

    if mode == "live":
        result = _fetch_customer_base_live()
        if result is not None:
            result["data_source"] = "flexcube_live"
            result["mode"] = "live"
            return result

    if mode in ("synthetic", "mock") and CBS_DIR.exists():
        result = _fetch_customer_base_from_cbs()
        if result is not None:
            result["data_source"] = "cbs_synthetic"
            result["mode"] = mode
            return result

    result = _customer_base_demo_defaults()
    result["data_source"] = "demo_defaults"
    result["mode"] = mode
    return result


def fetch_dormant_accounts_aggregate() -> Dict[str, Any]:
    """Aggregate dormant-accounts snapshot for `dormant_accounts` stock (v7.11)."""
    mode = get_mode()

    if mode == "live":
        result = _fetch_dormant_accounts_live()
        if result is not None:
            result["data_source"] = "flexcube_live"
            result["mode"] = "live"
            return result

    if mode in ("synthetic", "mock") and CBS_DIR.exists():
        result = _fetch_dormant_accounts_from_cbs()
        if result is not None:
            result["data_source"] = "cbs_synthetic"
            result["mode"] = mode
            return result

    result = _dormant_accounts_demo_defaults()
    result["data_source"] = "demo_defaults"
    result["mode"] = mode
    return result


# ══════════════════════════════════════════════════════════════════
# Live FLEXCUBE handlers (stub — wire to Apigee in v8.x)
# ══════════════════════════════════════════════════════════════════

def _fetch_loan_portfolio_live() -> Optional[Dict[str, Any]]:
    """Live FLEXCUBE loan-portfolio aggregation. v8.0 implementation.

    Calls flexcube_adapter.fetch_loan_portfolio_aggregate_live() which
    hits FLEXCUBE PortfolioService/Loans/Aggregate. Returns None on
    any failure → caller falls back to CBS synthetic / demo defaults.
    """
    try:
        from utils.flexcube_adapter import fetch_loan_portfolio_aggregate_live
        return fetch_loan_portfolio_aggregate_live()
    except Exception:
        return None


def _fetch_deposit_book_live() -> Optional[Dict[str, Any]]:
    """Live FLEXCUBE deposit-book aggregation. v8.0 implementation."""
    try:
        from utils.flexcube_adapter import fetch_deposit_book_aggregate_live
        return fetch_deposit_book_aggregate_live()
    except Exception:
        return None


def _fetch_npl_live() -> Optional[Dict[str, Any]]:
    """Live FLEXCUBE NPL aggregation. v8.0 implementation."""
    try:
        from utils.flexcube_adapter import fetch_npl_aggregate_live
        return fetch_npl_aggregate_live()
    except Exception:
        return None


def _fetch_customer_base_live() -> Optional[Dict[str, Any]]:
    """Live FLEXCUBE customer-base aggregation. v8.0 implementation."""
    try:
        from utils.flexcube_adapter import fetch_customer_base_aggregate_live
        return fetch_customer_base_aggregate_live()
    except Exception:
        return None


def _fetch_dormant_accounts_live() -> Optional[Dict[str, Any]]:
    """Live FLEXCUBE dormant-accounts aggregation. v8.0 implementation."""
    try:
        from utils.flexcube_adapter import fetch_dormant_accounts_aggregate_live
        return fetch_dormant_accounts_aggregate_live()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# CBS synthetic data handlers (read from cbs_data/)
# ══════════════════════════════════════════════════════════════════

def _fetch_loan_portfolio_from_cbs() -> Optional[Dict[str, Any]]:
    """Read aggregate loan portfolio from CBS synthetic data.

    Looks for cbs_data/loans.json or similar. Returns None if not found.
    Today returns None (CBS_DIR may not have aggregate file yet); v8.x
    can populate.
    """
    # CBS may have per-account files but not yet aggregate; future batch
    # can compute aggregates from the per-account files.
    candidates = [
        CBS_DIR / "loans_aggregate.json",
        CBS_DIR / "portfolio_aggregate.json",
    ]
    for f in candidates:
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _fetch_deposit_book_from_cbs() -> Optional[Dict[str, Any]]:
    """Read aggregate deposit book from CBS synthetic data."""
    candidates = [
        CBS_DIR / "deposits_aggregate.json",
        CBS_DIR / "deposit_book_aggregate.json",
    ]
    for f in candidates:
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _fetch_npl_from_cbs() -> Optional[Dict[str, Any]]:
    """Read aggregate NPL inventory from CBS synthetic data."""
    candidates = [
        CBS_DIR / "npl_aggregate.json",
        CBS_DIR / "stage3_aggregate.json",
    ]
    for f in candidates:
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _fetch_customer_base_from_cbs() -> Optional[Dict[str, Any]]:
    """Read aggregate customer base from CBS synthetic data (v7.11)."""
    candidates = [
        CBS_DIR / "customer_aggregate.json",
        CBS_DIR / "customers_aggregate.json",
    ]
    for f in candidates:
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _fetch_dormant_accounts_from_cbs() -> Optional[Dict[str, Any]]:
    """Read aggregate dormant accounts from CBS synthetic data (v7.11)."""
    candidates = [
        CBS_DIR / "dormant_aggregate.json",
        CBS_DIR / "dormancy_aggregate.json",
    ]
    for f in candidates:
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


# ══════════════════════════════════════════════════════════════════
# Demo defaults (Tier-2 Kenya bank typical profile)
# ══════════════════════════════════════════════════════════════════

def _loan_portfolio_demo_defaults() -> Dict[str, Any]:
    """Demo defaults representing Tier-2 Kenya bank loan book.

    Aligned with the v7.1 _loan_portfolio_snapshot demo defaults so the
    aggregator-wired version produces identical output for audit/round-trip.
    """
    return {
        "gross_outstanding_kes": "80000000000",  # 80B
        "by_segment_kes": {
            "RETAIL_INDIVIDUAL": "20000000000",   # 25%
            "SME": "18000000000",                  # 22.5%
            "CORPORATE": "32000000000",            # 40%
            "REAL_ESTATE": "8000000000",           # 10%
            "STAFF_LOANS": "2000000000",           # 2.5%
        },
        "by_stage_kes": {
            "STAGE_1": "68000000000",   # 85% performing
            "STAGE_2": "4000000000",    # 5% SICR
            "STAGE_3": "8000000000",    # 10% NPL
        },
        "weighted_avg_pd_pct": "3.2",
        "average_lgd_pct": "45.0",
    }


def _deposit_book_demo_defaults() -> Dict[str, Any]:
    """Demo defaults representing Tier-2 Kenya bank deposit book.

    Aligned with v7.3 _deposit_base_snapshot defaults.
    """
    return {
        "total_deposits_kes": "110000000000",  # 110B
        "loan_to_deposit_ratio_pct": "72.73",  # 80B / 110B
        "by_stability_tier_kes": {
            "RETAIL_STABLE": "55000000000",
            "RETAIL_LESS_STABLE": "22000000000",
            "OPERATIONAL_DEPOSITS": "16500000000",
            "NON_OPERATIONAL_CORPORATE": "11000000000",
            "FINANCIAL_INSTITUTIONS": "5500000000",
        },
        "by_product_kes": {
            "CURRENT_ACCOUNTS": "33000000000",
            "SAVINGS_ACCOUNTS": "44000000000",
            "FIXED_DEPOSITS": "27500000000",
            "CALL_DEPOSITS": "5500000000",
        },
        "by_segment_kes": {
            "RETAIL_INDIVIDUAL": "66000000000",
            "SME": "16500000000",
            "CORPORATE": "22000000000",
            "FINANCIAL_INSTITUTIONS": "5500000000",
        },
    }


def _npl_demo_defaults() -> Dict[str, Any]:
    """Demo defaults representing Tier-2 Kenya bank NPL inventory.

    Aligned with v7.1 _npl_inventory_snapshot defaults so wiring through
    the aggregator produces identical output for audit/round-trip.
    """
    return {
        "stage_3_kes": "8000000000",            # 10% of 80B loan book
        "loan_book_basis_kes": "80000000000",
        "npl_ratio_pct": "10.00",
        "by_aging_kes": {
            "DAYS_91_180": "3000000000",        # Recently delinquent
            "DAYS_181_365": "3500000000",       # Sub-standard
            "DAYS_OVER_365": "1500000000",      # Doubtful/loss
        },
    }


def _customer_base_demo_defaults() -> Dict[str, Any]:
    """Demo defaults representing Tier-2 Kenya bank customer base (v7.11).

    Aligned with v7.4 _customer_base_snapshot defaults — A2Z Blueprint
    CBS simulation profile (700K customers, 35 branches, ~232 RMs).
    """
    return {
        "total_customers": 700_000,
        "by_segment_count": {
            "RETAIL_INDIVIDUAL": 595_000,    # 85%
            "SME": 70_000,                   # 10%
            "CORPORATE": 28_000,             # 4%
            "STAFF": 7_000,                  # 1%
        },
        "by_tenure_band_count": {
            "0_TO_1_YEAR": 105_000,
            "1_TO_3_YEARS": 175_000,
            "3_TO_5_YEARS": 140_000,
            "OVER_5_YEARS": 280_000,
        },
        "by_onboarding_channel_count": {
            "BRANCH": 350_000,
            "DIGITAL_ONBOARDING": 210_000,
            "AGENT": 105_000,
            "REFERRAL": 35_000,
        },
        "by_kyc_risk_band_count": {
            "LOW": 525_000,
            "MEDIUM": 140_000,
            "HIGH": 35_000,
            "PROHIBITED": 0,
        },
        "monthly_growth_rate_pct": "0.8",
    }


def _dormant_accounts_demo_defaults() -> Dict[str, Any]:
    """Demo defaults representing Tier-2 Kenya bank dormant accounts (v7.11).

    Aligned with v7.4 _dormant_accounts_snapshot defaults (12% rate,
    50/30/20 split across 3 dormancy bands).
    """
    return {
        "total_dormant": 84_000,
        "customer_basis_count": 700_000,
        "dormancy_rate_pct": "12.00",
        "by_dormancy_band_count": {
            "DAYS_90_TO_180": 42_000,        # 50%
            "DAYS_181_TO_365": 25_200,       # 30%
            "OVER_365_DAYS": 16_800,         # 20%
        },
        "by_segment_count": {
            "RETAIL_INDIVIDUAL": 75_600,     # 90%
            "SME": 5_880,                    # 7%
            "CORPORATE": 1_680,              # 2%
            "STAFF": 840,                    # 1%
        },
        "reactivation_potential_count": 12_600,
        "avg_balance_per_dormant_kes": 8_500,
        "estimated_latent_value_kes": "714000000",
    }


# ══════════════════════════════════════════════════════════════════
# Self-test
# ══════════════════════════════════════════════════════════════════

def self_test() -> bool:
    """Smoke-test all 5 aggregators (v7.11)."""
    lp = fetch_loan_portfolio_aggregate()
    assert "data_source" in lp
    assert "gross_outstanding_kes" in lp
    assert "by_segment_kes" in lp

    dp = fetch_deposit_book_aggregate()
    assert "data_source" in dp
    assert "total_deposits_kes" in dp
    assert "by_stability_tier_kes" in dp

    npl = fetch_npl_aggregate()
    assert "data_source" in npl
    assert "stage_3_kes" in npl

    cb = fetch_customer_base_aggregate()
    assert "data_source" in cb
    assert "total_customers" in cb
    assert "by_kyc_risk_band_count" in cb

    da = fetch_dormant_accounts_aggregate()
    assert "data_source" in da
    assert "total_dormant" in da
    assert "by_dormancy_band_count" in da

    return True


if __name__ == "__main__":
    print("A2Z MIS 360 — utils.flexcube_aggregator self-test")
    print(f"Mode: {get_mode()}")
    ok = self_test()
    print(f"Result: {'PASS' if ok else 'FAIL'}")

    print("\nLoan portfolio aggregate:")
    lp = fetch_loan_portfolio_aggregate()
    print(f"  data_source: {lp['data_source']}")
    print(f"  gross_outstanding: KES {float(lp['gross_outstanding_kes'])/1e9:.1f}B")

    print("\nDeposit book aggregate:")
    dp = fetch_deposit_book_aggregate()
    print(f"  data_source: {dp['data_source']}")
    print(f"  total_deposits: KES {float(dp['total_deposits_kes'])/1e9:.1f}B")
    print(f"  LDR: {dp['loan_to_deposit_ratio_pct']}%")

    print("\nNPL aggregate:")
    npl = fetch_npl_aggregate()
    print(f"  data_source: {npl['data_source']}")
    print(f"  stage_3: KES {float(npl['stage_3_kes'])/1e9:.1f}B")
    print(f"  NPL ratio: {npl['npl_ratio_pct']}%")

"""
v10.530 Phase 5 Batch γ1 — CBS lookup routes.

5 endpoints under /api/cbs/. All require Bearer JWT. Bank-wide scope
(no cascade filter — customer lookup is intentionally bank-wide so any
RM can find any customer for deal creation). Read-only.

Endpoint inventory:
  - GET  /api/cbs/customers                       — list/search (?q=name)
  - GET  /api/cbs/customers/{cif}                 — single customer
  - GET  /api/cbs/customers/{cif}/accounts        — accounts for that CIF
  - GET  /api/cbs/branches                        — 35 branches reference
  - GET  /api/cbs/aggregates                      — bank-level rollups

Audit emission (canonical _audit pending GAP-018; using direct
audit_log for now to match α8/α9 pattern):
  - CBS_CUSTOMER_LOOKUP      on /customers/{cif}
  - CBS_ACCOUNTS_LOOKUP      on /customers/{cif}/accounts
  - (no audit on search/branches/aggregates — low-sensitivity browse)

Why no scope filter:
  Customer lookup before deal creation is intentionally global —
  Joshua's MD-level cascade includes everyone anyway, and lower-tier
  staff need to be able to find prospects whose CIF lives in another
  RM's portfolio (e.g. customer walks into the wrong branch).
  Audit log captures every purposeful lookup for accountability.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from utils.auth_jwt import get_current_user
from utils.core_audit import audit_log
from utils.cbs_manager import (
    get_customer_by_cif,
    search_customers_by_name,
    get_accounts_for_cif,
    get_branches,
    get_aggregates,
)


router = APIRouter(prefix="/api/cbs", tags=["cbs"])


# ── List / search ────────────────────────────────────────────────────────

@router.get("/customers")
def list_or_search_customers(
    q: str = Query("", description="Substring of full_name (min 3 chars to activate search)"),
    limit: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """
    Browse/search endpoint. If `q` is empty or < 3 chars, returns empty
    list (debounce safety; no full-table dump). With a query, returns up
    to `limit` matches by case-insensitive substring match on full_name.

    Not audited — interactive search produces too much noise.
    """
    results = search_customers_by_name(q, limit=limit)
    return {
        "customers": results,
        "count":     len(results),
        "query":     q,
        "source":    "cbs_manager",
    }


# ── Single customer by exact CIF ────────────────────────────────────────

@router.get("/customers/{cif}")
def fetch_customer(
    cif: str,
    user: dict = Depends(get_current_user),
):
    """
    Exact-CIF lookup. Returns 404 if not found.
    Audited (CBS_CUSTOMER_LOOKUP) — purposeful identification of a customer.
    """
    customer = get_customer_by_cif(cif)
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No customer found with CIF {cif}",
        )
    audit_log(
        "CBS_CUSTOMER_LOOKUP",
        user.get("username", "unknown"),
        detail=f"cif={cif} name={customer.get('full_name')}",
    )
    return {
        "customer": customer,
        "source":   "cbs_manager",
    }


# ── Accounts sub-resource ────────────────────────────────────────────────

@router.get("/customers/{cif}/accounts")
def fetch_customer_accounts(
    cif: str,
    user: dict = Depends(get_current_user),
):
    """
    All accounts belonging to a CIF. Empty list (not 404) if customer
    has no accounts; 404 only if the CIF itself isn't valid.
    Audited (CBS_ACCOUNTS_LOOKUP).
    """
    # Validate CIF first so unknown CIFs 404 cleanly
    customer = get_customer_by_cif(cif)
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail=f"No customer found with CIF {cif}",
        )
    accounts = get_accounts_for_cif(cif)
    audit_log(
        "CBS_ACCOUNTS_LOOKUP",
        user.get("username", "unknown"),
        detail=f"cif={cif} count={len(accounts)}",
    )
    return {
        "accounts": accounts,
        "count":    len(accounts),
        "cif":      cif,
        "source":   "cbs_manager",
    }


# ── Branches reference (35 rows; not audited) ───────────────────────────

@router.get("/branches")
def fetch_branches(
    user: dict = Depends(get_current_user),
):
    branches = get_branches()
    return {
        "branches": branches,
        "count":    len(branches),
        "source":   "cbs_manager",
    }


# ── Aggregates (bank-level rollups; not audited) ────────────────────────

@router.get("/aggregates")
def fetch_aggregates(
    user: dict = Depends(get_current_user),
):
    return {
        "aggregates": get_aggregates(),
        "source":     "cbs_manager",
    }

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

import os
import time as _time

from fastapi import APIRouter, Depends, HTTPException, Query

import logging

from utils.auth_jwt import get_current_user, require_config_admin
from utils.core_audit import audit_log
from utils.cbs_manager import (
    get_customer_by_cif,
    search_customers_by_name,
    get_accounts_for_cif,
    get_branches,
    get_aggregates,
    get_account_by_number,
    get_account_360,
)


logger = logging.getLogger(__name__)

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


# ── Portfolio owner (mapped relationship manager) ───────────────────────

def _resolve_owner_name(staff_code: str) -> str:
    """Best-effort: resolve a staff code to its display name via the pipeline
    roster, so a CBS-mapped owner surfaces as a referable person. Returns ""
    when the code isn't in the roster — logged, never silently swallowed."""
    code = str(staff_code or "").strip()
    if not code:
        return ""
    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
        hit = roster[roster["Staff Code"].astype(str).str.strip() == code]
        # ── KE0539 AND KE539 ARE THE SAME PERSON ────────────────────────────
        # FROM THE PILOT (2026-08-21): Lucy Lidahuli owns the portfolio, CBS
        # returns KE0539, the register holds KE539, and the exact match failed.
        # The screen then said "this owner isn't a recognised system user" and
        # asked an RM to confirm a recipient the system already knew.
        #
        # The padding was introduced for DSA codes, which need four digits. It
        # was never meant to make a three-digit staff code into a different
        # person - but a string comparison cannot tell the difference.
        #
        # So: compare on the DIGITS, ignoring how many zeros sit in front. KE539
        # and KE0539 and KE00539 are one person; KE5390 is not, because the
        # digits differ.
        if hit.empty:
            import re as _re

            def _digits(v):
                m = _re.match(r"^([A-Za-z]*)0*(\d+)$", str(v or "").strip())
                return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""

            _want = _digits(code)
            if _want:
                _norm = roster["Staff Code"].astype(str).map(_digits)
                hit = roster[_norm == _want]
                if not hit.empty:
                    logger.info(
                        "portfolio owner %s matched the roster as %s - the "
                        "codes differ only by leading zeros", code,
                        str(hit.iloc[0].get("Staff Code")))
        if not hit.empty:
            return str(hit.iloc[0].get("Staff Name") or "").strip()
    except Exception as exc:  # surfaced, not silent (CGR1)
        logger.warning("portfolio-owner name resolution failed for %s: %s", code, exc)
    return ""


@router.get("/customers/{cif}/portfolio-owner")
def fetch_customer_portfolio_owner(
    cif: str,
    user: dict = Depends(get_current_user),
):
    """Resolve the portfolio owner (relationship manager) mapped to a CIF.

    Ecobank maps every customer to a relationship owner. This turns the CBS
    relationship_manager_code into a referable portfolio owner (code + name)
    so the deal-create flow can route an existing-customer deal to its owner
    for a nod. is_mapped is False for unassigned customers (treat like NTB);
    owner_in_roster flags whether that owner is an addressable pipeline user.
    """
    customer = get_customer_by_cif(cif)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"No customer found with CIF {cif}")

    rm_code = str(customer.get("relationship_manager_code") or "").strip()
    is_mapped = bool(rm_code) and rm_code.upper() != "UNASSIGNED"
    owner_name = _resolve_owner_name(rm_code) if is_mapped else ""

    audit_log(
        "CBS_PORTFOLIO_OWNER_LOOKUP",
        user.get("username", "unknown"),
        detail=f"cif={cif} rm={rm_code or 'UNASSIGNED'} mapped={is_mapped}",
    )
    return {
        "cif":                       str(customer.get("cif") or cif),
        "customer_name":             str(customer.get("full_name") or ""),
        "is_mapped":                 is_mapped,
        "portfolio_owner_code":      rm_code if is_mapped else None,
        "portfolio_owner_name":      owner_name if is_mapped else None,
        "owner_in_roster":           bool(owner_name),
        "relationship_manager_code": rm_code,
        "source":                    "cbs_manager",
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


# ── Account number lookup (live FlexCube or CSV fallback) ───────────────

@router.get("/accounts/{account_number}")
def fetch_account_by_number(
    account_number: str,
    user: dict = Depends(get_current_user),
):
    """
    Exact account-number lookup.

    Live path: calls CUSTOMERACCOUNTDETAILS via FlexCube script API.
    CSV fallback: used when FLEXCUBE_SCRIPTS_URL is not configured.
    Audited (CBS_ACCOUNT_LOOKUP).
    """
    account = get_account_by_number(account_number)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail=f"Account {account_number} not found",
        )
    audit_log(
        "CBS_ACCOUNT_LOOKUP",
        user.get("username", "unknown"),
        detail=f"account={account_number} cif={account.get('f12_cif') or account.get('cif')}",
    )
    return {"account": account, "source": "flexcube"}


@router.get("/accounts/{account_number}/360")
def fetch_account_360(
    account_number: str,
    user: dict = Depends(get_current_user),
):
    """
    Combined view: account record + active loan portfolio.

    Returns account dict with active_loans[], active_loans_count,
    and total_loan_outstanding embedded. One API call for the full
    account + loans card. Audited (CBS_ACCOUNT_360_LOOKUP).
    """
    result = get_account_360(account_number)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Account {account_number} not found",
        )
    audit_log(
        "CBS_ACCOUNT_360_LOOKUP",
        user.get("username", "unknown"),
        detail=f"account={account_number} loans={result.get('active_loans_count', 0)}",
    )
    return {"account": result, "source": "flexcube"}


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

@router.get("/portfolio")
def fetch_my_portfolio(
    staff_code: str = Query(default=""),
    user: dict = Depends(get_current_user),
):
    """The logged-in person's CBS book, or — for a manager — the consolidated book
    of their whole reporting subtree, with an optional per-staff drill-down.
    Managers get a `team` list (staff in scope) for the selector."""
    my_code = str(user.get("staff_code") or "").strip()
    my_role = str(user.get("role") or "")
    if not my_code:
        try:
            from utils.core import UserManager
            u = UserManager().users.get(str(user.get("username") or ""))
            my_code = str((u or {}).get("staff_code") or "").strip()
            my_role = my_role or str((u or {}).get("role") or "")
        except Exception:
            pass
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        scope = {str(x) for x in get_visible_staff_codes(
            {"staff_code": my_code, "role": my_role, "is_admin": bool(user.get("is_admin"))})}
    except Exception:
        scope = set()
    scope = scope or ({my_code} if my_code else set())
    # team roster for the selector (names)
    team = []
    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
        seen = set()
        for _, r in roster.iterrows():
            sc = str(r.get("Staff Code") or "").strip()
            if sc in scope and sc not in seen:
                seen.add(sc)
                team.append({"staff_code": sc, "name": str(r.get("Staff Name") or sc)})
        team.sort(key=lambda x: x["name"])
    except Exception:
        team = []
    sel = str(staff_code or "").strip()
    if sel and sel in scope:
        codes, view, selected = {sel}, "individual", sel
    else:
        codes = scope
        view = "consolidated" if len(scope) > 1 else "individual"
        selected = ""
    from utils.cbs_manager import get_portfolio_for_codes
    # Two independent lenses, never summed: the managed book (accounts this scope is RM
    # for) and introduced production (accounts this scope originated, possibly now
    # managed elsewhere). pf stays the managed book for back-compat; introduced rides
    # alongside so the UI can offer a "Managing / Introduced" toggle.
    pf = get_portfolio_for_codes(codes, attribution="managed")
    introduced = get_portfolio_for_codes(codes, attribution="introduced")
    # pipeline value for the scope, split deposits vs loans by product
    try:
        from utils.core import PipelineManager
        pm = PipelineManager()
        pipe_dep = pipe_loan = 0.0
        loan_words = ("loan", "facility", "lpo", "mortgage", "advance", "overdraft", "credit")
        for c in codes:
            for dl in pm.get_deals(staff_code=c, active_only=True):
                v = float(dl.get("deal_value") or 0)
                prod = str(dl.get("product") or "").lower()
                if any(w in prod for w in loan_words):
                    pipe_loan += v
                else:
                    pipe_dep += v
        pf["summary"]["pipeline_deposits"] = round(pipe_dep, 2)
        pf["summary"]["pipeline_loans"] = round(pipe_loan, 2)
        pf["summary"]["pipeline_value"] = round(pipe_dep + pipe_loan, 2)
    except Exception:
        pf["summary"]["pipeline_deposits"] = 0.0
        pf["summary"]["pipeline_loans"] = 0.0
        pf["summary"]["pipeline_value"] = 0.0
    pf["introduced"] = {"accounts": introduced.get("accounts", []),
                        "summary": introduced.get("summary", {})}
    pf["team"] = team
    pf["view"] = view
    pf["selected"] = selected
    pf["is_manager"] = len(scope) > 1
    # branch-unallocated (orphaned accounts in the manager's branch) — consolidated view only
    pf["branch_unallocated"] = None
    if view == "consolidated" and len(scope) > 1:
        try:
            from utils.cbs_manager import branch_code_for_name, get_branch_unallocated
            from utils.api_pipeline_scope import get_staff_roster
            roster = get_staff_roster()
            reg_codes = set(roster["Staff Code"].astype(str).str.strip())
            hit = roster[roster["Staff Code"].astype(str).str.strip() == my_code]
            units = set()
            if not hit.empty:
                units.add(str(hit.iloc[0].get("Unit") or "").strip())
            bcodes = []
            for u in units:
                bcodes += branch_code_for_name(u)
            if bcodes:
                bu = get_branch_unallocated(bcodes, reg_codes)
                bu["branch_codes"] = bcodes
                pf["branch_unallocated"] = bu
        except Exception:
            pf["branch_unallocated"] = None
    return pf


@router.get("/aggregates")
def fetch_aggregates(
    user: dict = Depends(get_current_user),
):
    return {
        "aggregates": get_aggregates(),
        "source":     "cbs_manager",
    }


# ── EOD ETL endpoints (config-admin only) ────────────────────────────────

@router.get("/etl/status")
def cbs_etl_status(user: dict = Depends(require_config_admin)):
    """Last ETL run stats + total account counts in cbs_accounts table."""
    from utils.cbs_etl import etl_status
    return etl_status()


@router.post("/etl/run")
def cbs_etl_run(
    trigger: bool = Query(True, description="GET /command/export:customers first"),
    user:    dict = Depends(require_config_admin),
):
    """
    Trigger a full EOD import: export → download CORP+INDI CSVs → upsert.
    Same as running the cron script manually.
    """
    from utils.cbs_etl import run_etl
    audit_log("CBS_ETL_RUN", user.get("username", "unknown"),
              detail=f"trigger={trigger}")
    return run_etl(trigger=trigger)


# ── CBS account cache endpoints (config-admin only) ─────────────────────

@router.get("/cache/status")
def cbs_cache_status(user: dict = Depends(require_config_admin)):
    """Cache stats: total rows, stale count, oldest/newest entry, TTL."""
    from utils.cbs_cache import cache_stats
    return cache_stats()


@router.post("/cache/refresh")
def cbs_cache_refresh(
    limit: int = Query(200, ge=1, le=2000),
    user:  dict = Depends(require_config_admin),
):
    """
    Trigger a cache refresh run (same as the cron job, on-demand).
    Re-fetches up to `limit` stale accounts from FlexCube.
    """
    from utils.cbs_cache import refresh_stale_accounts
    audit_log("CBS_CACHE_REFRESH", user.get("username", "unknown"),
              detail=f"limit={limit} triggered_via=api")
    return refresh_stale_accounts(limit=limit)


@router.post("/cache/mark-stale")
def cbs_cache_mark_stale(user: dict = Depends(require_config_admin)):
    """Force-mark all cached accounts as stale (next cron run refreshes all)."""
    from utils.cbs_cache import mark_all_stale
    count = mark_all_stale()
    audit_log("CBS_CACHE_MARK_STALE", user.get("username", "unknown"),
              detail=f"marked={count}")
    return {"marked_stale": count}


# ── FlexCube connection debug (config-admin only) ────────────────────────

PROBE_SCRIPTS = [
    {"name": "CUSTOMERACCOUNTDETAILS", "params": {"ACCOUNT_NUMBER": "__PROBE__"},
     "description": "Account + customer summary by account number"},
    {"name": "CUSTOMERACTIVELOANS",    "params": {"CIF": "__PROBE__"},
     "description": "Active loan accounts by FlexCube F7 CIF"},
]


@router.get("/debug/flexcube")
def flexcube_debug_status(
    probe: bool = Query(False, description="Run a live probe call to FlexCube"),
    user: dict  = Depends(require_config_admin),
):
    """
    FlexCube connection status + optional live probe.

    Config-admin only (CEO / MD / Director / Admin). Returns:
      - configured: whether FLEXCUBE_SCRIPTS_URL is set
      - url_hint:   first 25 chars of the URL (masked — never returns full URL)
      - timeout_s:  configured timeout
      - max_retries: configured retries
      - scripts:    catalogue of available scripts
      - probe:      when ?probe=true, runs CUSTOMERACCOUNTDETAILS with a dummy
                    account number and returns status / response_ms / error
    """
    from utils.flexcube_script_client import is_configured

    raw_url  = os.getenv("FLEXCUBE_SCRIPTS_URL", "")
    timeout  = int(os.getenv("FLEXCUBE_TIMEOUT_SECONDS", "15"))
    retries  = int(os.getenv("FLEXCUBE_MAX_RETRIES", "3"))
    configured = bool(raw_url.strip())
    url_hint   = (raw_url[:25] + "…") if len(raw_url) > 25 else raw_url

    result: dict = {
        "configured":  configured,
        "url_hint":    url_hint if configured else None,
        "timeout_s":   timeout,
        "max_retries": retries,
        "scripts":     PROBE_SCRIPTS,
        "probe":       None,
    }

    if probe:
        if not configured:
            result["probe"] = {
                "status":      "skipped",
                "error":       "FLEXCUBE_SCRIPTS_URL is not set",
                "response_ms": None,
            }
        else:
            from utils.flexcube_script_client import execute_script, FlexcubeScriptError
            t0 = _time.monotonic()
            try:
                rows = execute_script(
                    "CUSTOMERACCOUNTDETAILS",
                    {"ACCOUNT_NUMBER": "__PROBE__"},
                )
                ms = int((_time.monotonic() - t0) * 1000)
                result["probe"] = {
                    "status":      "ok",
                    "rows_returned": len(rows),
                    "response_ms": ms,
                    "note": "0 rows is normal for a probe — FlexCube is reachable",
                    "error": None,
                }
            except FlexcubeScriptError as exc:
                ms = int((_time.monotonic() - t0) * 1000)
                result["probe"] = {
                    "status":      "error",
                    "error":       str(exc),
                    "response_ms": ms,
                    "rows_returned": 0,
                }
            except Exception as exc:
                ms = int((_time.monotonic() - t0) * 1000)
                result["probe"] = {
                    "status":      "error",
                    "error":       f"Unexpected: {exc}",
                    "response_ms": ms,
                    "rows_returned": 0,
                }

    audit_log(
        "CBS_FLEXCUBE_DEBUG",
        user.get("username", "unknown"),
        detail=f"probe={probe} configured={configured}",
    )
    return result

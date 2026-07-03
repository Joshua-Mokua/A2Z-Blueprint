"""
v10.530 Phase 5 Batch γ1 — CBS Manager.

Lazy-loaded singleton wrapper around cbs_data/ files. Provides typed
lookup, search, and aggregate-fetch primitives for the FastAPI CBS
routes (utils/api_cbs_routes.py).

Design decisions:
  - Lazy loading: first call to each accessor loads from disk; subsequent
    calls return cached frame/dict. API server boots fast; only domains
    actually queried pay the load cost.
  - Module-level singletons: one DataFrame per file, never reloaded.
  - cif as DataFrame index for customers — O(1) lookup by CIF.
  - Search uses pandas .str.contains() — for 700K rows, ~100-150ms is
    acceptable for an interactive debounced search.
  - Read-only: CBS is the source of truth from the MIS perspective.
    No write methods, no mutation surface.

Memory footprint after warm-up (all three CSVs loaded):
  - customers.csv (200 MB on disk) → ~400 MB DataFrame
  - accounts.csv  (287 MB on disk) → ~600 MB DataFrame
  Total ~1 GB peak; FastAPI process should be sized accordingly.

Cross-references:
  - cbs_data/ schema documented in this file's helper functions
  - PIPELINE_DOMAIN_AUDIT.md Section 21 (to be authored in γ-batch closeout)
"""

import json
import pandas as pd
from pathlib import Path
from typing import Optional


# ── Paths ────────────────────────────────────────────────────────────────

_CBS_DIR = Path(__file__).resolve().parent.parent / "cbs_data"


# ── Module-level singletons (None until first load) ─────────────────────

_customers_df:  Optional[pd.DataFrame] = None
_accounts_df:   Optional[pd.DataFrame] = None
_branches:      Optional[list]         = None
_aggregates:    Optional[dict]         = None


# ── Loaders ──────────────────────────────────────────────────────────────

def _load_customers() -> pd.DataFrame:
    global _customers_df
    if _customers_df is None:
        path = _CBS_DIR / "customers.csv"
        print(f"[cbs_manager] Loading customers.csv from {path} ...")
        _customers_df = pd.read_csv(
            path,
            dtype={
                "cif":                       str,
                "relationship_manager_code": str,
                "branch_code":               str,
                "id_number":                 str,
                "kra_pin":                   str,
                "phone":                     str,
            },
            low_memory=False,
        )
        # cif → row in O(1). drop=False keeps the column accessible too.
        _customers_df.set_index("cif", drop=False, inplace=True)
        print(f"[cbs_manager] Loaded {len(_customers_df):,} customers.")
    return _customers_df


def _load_accounts() -> pd.DataFrame:
    global _accounts_df
    if _accounts_df is None:
        path = _CBS_DIR / "accounts.csv"
        print(f"[cbs_manager] Loading accounts.csv from {path} ...")
        _accounts_df = pd.read_csv(
            path,
            dtype={
                "cif":                       str,
                "account_number":            str,
                "relationship_manager_code": str,
                "branch_code":               str,
            },
            low_memory=False,
        )
        print(f"[cbs_manager] Loaded {len(_accounts_df):,} accounts.")
    return _accounts_df


def _load_branches() -> list:
    global _branches
    if _branches is None:
        path = _CBS_DIR / "branches.json"
        _branches = json.loads(path.read_text(encoding="utf-8"))
    return _branches


def _load_aggregates() -> dict:
    """Bundle all aggregate JSONs into a single dict keyed by base filename."""
    global _aggregates
    if _aggregates is None:
        out: dict = {}
        candidates = [
            "customer_aggregate",
            "deposits_aggregate",
            "loans_aggregate",
            "npl_aggregate",
            "dormant_aggregate",
            "branch_summary",
        ]
        for name in candidates:
            path = _CBS_DIR / f"{name}.json"
            if path.exists():
                out[name] = json.loads(path.read_text(encoding="utf-8"))
        _aggregates = out
    return _aggregates


# ── Row-to-dict serializers (JSON-safe; coerces pandas dtypes) ──────────

def _safe_str(v) -> str:
    if v is None:
        return ""
    s = str(v)
    if s in ("nan", "NaN", "NaT", "None"):
        return ""
    return s


def _safe_float(v) -> float:
    try:
        f = float(v)
        # NaN → 0 (JSON-incompatible otherwise)
        if f != f:
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _safe_int(v) -> int:
    try:
        f = float(v)
        if f != f:
            return 0
        return int(f)
    except (TypeError, ValueError):
        return 0


def _safe_bool(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("true", "1", "yes", "y", "t")


def _customer_row_to_dict(row) -> dict:
    """Convert a customer DataFrame row to a JSON-safe dict."""
    return {
        "cif":                       _safe_str(row.get("cif")),
        "full_name":                 _safe_str(row.get("full_name")),
        "customer_type":             _safe_str(row.get("customer_type")),
        "segment":                   _safe_str(row.get("segment")),
        "sub_segment":               _safe_str(row.get("sub_segment")),
        "sector":                    _safe_str(row.get("sector")),
        "phone":                     _safe_str(row.get("phone")),
        "email":                     _safe_str(row.get("email")),
        "date_onboarded":            _safe_str(row.get("date_onboarded")),
        "branch_code":               _safe_str(row.get("branch_code")),
        "branch_name":               _safe_str(row.get("branch_name")),
        "region":                    _safe_str(row.get("region")),
        "county":                    _safe_str(row.get("county")),
        "relationship_manager_code": _safe_str(row.get("relationship_manager_code")),
        "kyc_status":                _safe_str(row.get("kyc_status")),
        "risk_rating":               _safe_str(row.get("risk_rating")),
        "is_dormant_customer":       _safe_bool(row.get("is_dormant_customer")),
        "preferred_currency":        _safe_str(row.get("preferred_currency")),
        "total_deposit_balance":     _safe_float(row.get("total_deposit_balance")),
        "total_loan_balance":        _safe_float(row.get("total_loan_balance")),
        "total_accounts":            _safe_int(row.get("total_accounts")),
        "aml_flag":                  _safe_bool(row.get("aml_flag")),
        "fatf_flag":                 _safe_bool(row.get("fatf_flag")),
        "pep_flag":                  _safe_bool(row.get("pep_flag")),
    }


def _account_row_to_dict(row) -> dict:
    """Convert an account DataFrame row to a JSON-safe dict."""
    return {
        "account_number":     _safe_str(row.get("account_number")),
        "cif":                _safe_str(row.get("cif")),
        "branch_code":        _safe_str(row.get("branch_code")),
        "branch_name":        _safe_str(row.get("branch_name")),
        "account_type_name":  _safe_str(row.get("account_type_name")),
        "category":           _safe_str(row.get("category")),
        "currency":           _safe_str(row.get("currency")),
        "date_opened":        _safe_str(row.get("date_opened")),
        "current_balance":    _safe_float(row.get("current_balance")),
        "available_balance":  _safe_float(row.get("available_balance")),
        "account_status":     _safe_str(row.get("account_status")),
        "dormancy_status":    _safe_str(row.get("dormancy_status")),
        "interest_rate":      _safe_float(row.get("interest_rate")),
        "loan_outstanding":   _safe_float(row.get("loan_outstanding")),
        "npl_status":         _safe_str(row.get("npl_status")),
        "npl_days":           _safe_int(row.get("npl_days")),
    }


# ── Public accessors ─────────────────────────────────────────────────────

def get_customer_by_cif(cif: str) -> Optional[dict]:
    """Lookup customer by exact CIF. Returns dict or None if not found."""
    df = _load_customers()
    cif = str(cif).strip()
    if cif not in df.index:
        return None
    row = df.loc[cif]
    # If duplicates exist (shouldn't but defensive), take first
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    return _customer_row_to_dict(row)


def search_customers_by_name(query: str, limit: int = 10) -> list[dict]:
    """
    Case-insensitive substring search on full_name.
    Returns empty list if query < 3 chars (debounce safety on server side).
    """
    df = _load_customers()
    q = query.strip().lower()
    if len(q) < 3:
        return []
    mask = df["full_name"].astype(str).str.lower().str.contains(q, na=False, regex=False)
    matches = df[mask].head(limit)
    return [_customer_row_to_dict(row) for _, row in matches.iterrows()]


def get_accounts_for_cif(cif: str) -> list[dict]:
    """Return all accounts belonging to a CIF (typically 1–5 accounts)."""
    df = _load_accounts()
    cif = str(cif).strip()
    matches = df[df["cif"] == cif]
    return [_account_row_to_dict(row) for _, row in matches.iterrows()]


def get_branches() -> list[dict]:
    return _load_branches()


def get_aggregates() -> dict:
    return _load_aggregates()


# ── FlexCube live lookups (active when FLEXCUBE_SCRIPTS_URL is set) ─────
#
# These replace the CSV path when the FlexCube script API is reachable.
# Fall back to CSV silently so dev environments without the API still work.
# Script names (CUSTOMERACCOUNTDETAILS, CUSTOMERACTIVELOANS) match the
# confirmed-working scripts wired to 10.8.32.3 — change via env var only.

from utils.flexcube_script_client import (
    execute_script,
    is_configured as _fc_configured,
    FlexcubeScriptError,
)


def get_account_by_number(account_number: str) -> Optional[dict]:
    """
    Account lookup by exact account number.

    Live path  — calls CUSTOMERACCOUNTDETAILS via the FlexCube script API
                 (requires FLEXCUBE_SCRIPTS_URL env var).
    Offline path — searches cbs_data/accounts.csv (used in dev / when
                   FlexCube is unreachable).

    Returned dict always contains the CbsAccount fields. The live path
    additionally includes:
      f7_cif    — FlexCube ext_ref_no (needed for CUSTOMERACTIVELOANS)
      f12_cif   — FlexCube internal customer_no
      customer_name, segment, kyc_status, risk_rating, aml_flag, pep_flag
    """
    num = str(account_number).strip()

    if _fc_configured():
        try:
            rows = execute_script(
                "CUSTOMERACCOUNTDETAILS",
                {"ACCOUNT_NUMBER": num},
            )
            if not rows:
                return None
            return rows[0]
        except FlexcubeScriptError:
            pass  # fall through to CSV

    # CSV fallback
    df = _load_accounts()
    matches = df[df["account_number"] == num]
    if matches.empty:
        return None
    acct = _account_row_to_dict(matches.iloc[0])
    # Embed basic customer summary from the CSV customer sheet
    cif = acct.get("cif", "")
    if cif:
        customer = get_customer_by_cif(cif)
        if customer:
            acct["customer_name"]  = customer["full_name"]
            acct["segment"]        = customer["segment"]
            acct["kyc_status"]     = customer["kyc_status"]
            acct["risk_rating"]    = customer["risk_rating"]
            acct["aml_flag"]       = customer["aml_flag"]
            acct["pep_flag"]       = customer["pep_flag"]
            acct["rm_code"]        = customer["relationship_manager_code"]
    return acct


def get_customer_active_loans(
    account_number: Optional[str] = None,
    f7_cif: Optional[str] = None,
) -> list[dict]:
    """
    Active loan accounts for a customer.

    CUSTOMERACTIVELOANS is keyed by F7 CIF (ext_ref_no), not F12.
    When called with account_number, the F7 CIF is resolved first via
    CUSTOMERACCOUNTDETAILS (one extra round-trip avoided if the caller
    already fetched the account and passes f7_cif directly).

    Returns [] when FlexCube is unreachable or no loans exist.
    """
    if not _fc_configured():
        return []

    resolved_f7 = f7_cif
    if not resolved_f7 and account_number:
        acct = get_account_by_number(account_number)
        if acct:
            resolved_f7 = acct.get("f7_cif") or acct.get("ext_ref_no")

    if not resolved_f7:
        return []

    try:
        return execute_script("CUSTOMERACTIVELOANS", {"CIF": resolved_f7})
    except FlexcubeScriptError:
        return []


def get_account_360(account_number: str) -> Optional[dict]:
    """
    Combined payload: account record + all active loans.

    The loans are attached under active_loans[], active_loans_count,
    and total_loan_outstanding so the frontend needs one API call.
    """
    account = get_account_by_number(account_number)
    if not account:
        return None

    f7_cif = account.get("f7_cif") or account.get("ext_ref_no")
    loans  = get_customer_active_loans(f7_cif=f7_cif) if f7_cif else []

    account["active_loans"]           = loans
    account["active_loans_count"]     = len(loans)
    account["total_loan_outstanding"] = sum(
        float(l.get("total_outstanding") or 0) for l in loans
    )
    return account


# ── Diagnostics (not exposed via API; usable from Python shell) ─────────

def cache_status() -> dict:
    """Inspect what's loaded. Useful for operational diagnostics."""
    return {
        "customers_loaded":  _customers_df is not None,
        "customer_count":    len(_customers_df) if _customers_df is not None else 0,
        "accounts_loaded":   _accounts_df is not None,
        "account_count":     len(_accounts_df) if _accounts_df is not None else 0,
        "branches_loaded":   _branches is not None,
        "branch_count":      len(_branches) if _branches is not None else 0,
        "aggregates_loaded": _aggregates is not None,
    }

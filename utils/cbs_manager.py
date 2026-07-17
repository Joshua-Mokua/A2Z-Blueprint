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
import logging
import pandas as pd
from pathlib import Path
from typing import Optional

logger = logging.getLogger("a2z.cbs_manager")


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
        _cols = ["cif", "full_name", "segment", "kyc_status", "risk_rating",
                 "aml_flag", "pep_flag", "relationship_manager_code",
                 "branch_code", "id_number", "kra_pin", "phone"]
        if not path.exists():
            # Live-FlexCube env (or dev without generated data): no local CSV.
            # Degrade to an empty set so lookups 404 cleanly instead of 500-ing.
            print(f"[cbs_manager] customers.csv not found at {path} — using empty set.")
            _customers_df = pd.DataFrame(columns=_cols).set_index("cif", drop=False)
            return _customers_df
        try:
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
        except Exception as exc:
            print(f"[cbs_manager] failed to load customers.csv: {exc} — using empty set.")
            _customers_df = pd.DataFrame(columns=_cols).set_index("cif", drop=False)
    return _customers_df


def _load_accounts() -> pd.DataFrame:
    global _accounts_df
    if _accounts_df is None:
        path = _CBS_DIR / "accounts.csv"
        _cols = ["cif", "account_number", "relationship_manager_code", "branch_code"]
        if not path.exists():
            print(f"[cbs_manager] accounts.csv not found at {path} — using empty set.")
            _accounts_df = pd.DataFrame(columns=_cols)
            return _accounts_df
        try:
            print(f"[cbs_manager] Loading accounts.csv from {path} ...")
            _accounts_df = pd.read_csv(
                path,
                dtype={
                    "cif":                       str,
                    "account_number":            str,
                    "relationship_manager_code": str,
                    "introducer_code":           str,
                    "branch_code":               str,
                },
                low_memory=False,
            )
            print(f"[cbs_manager] Loaded {len(_accounts_df):,} accounts.")
        except Exception as exc:
            print(f"[cbs_manager] failed to load accounts.csv: {exc} — using empty set.")
            _accounts_df = pd.DataFrame(columns=_cols)
    return _accounts_df


def _load_branches() -> list:
    global _branches
    if _branches is None:
        path = _CBS_DIR / "branches.json"
        try:
            _branches = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[cbs_manager] branches.json unavailable ({exc}) — using empty list.")
            _branches = []
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
        "introducer_code":    _safe_str(row.get("introducer_code")),
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

def _resolve_cif(identifier: str) -> str:
    """Accept either a CIF or an account number.

    Bank staff realistically know the account number, not the internal
    CIF — the frontend's "Lookup by CIF" field was built against
    synthetic data (CIF range 100000001-100700000) and doesn't
    distinguish the two. If `identifier` matches an account_number in
    cbs_accounts, resolve it to its owning F12 CIF; otherwise return it
    unchanged (it's presumably already a CIF, or unresolvable — callers
    look it up as-is and 404 naturally if it's neither).
    """
    identifier = str(identifier).strip()
    try:
        from utils.db import db
        if not db.is_postgres_ready():
            return identifier
        row = db.fetch_one(
            "SELECT f12_cif FROM cbs_accounts WHERE account_number = %s",
            (identifier,),
        )
        if row and row.get("f12_cif"):
            return str(row["f12_cif"])
    except Exception:
        pass
    return identifier


def _db_accounts_for_cif(cif: str) -> Optional[list]:
    """Raw cbs_accounts rows for this F12 CIF. None if Postgres isn't
    ready (caller should fall back); [] if ready but no rows found."""
    try:
        from utils.db import db
        if not db.is_postgres_ready():
            return None
        rows = db.fetch_all(
            "SELECT * FROM cbs_accounts WHERE f12_cif = %s ORDER BY account_number",
            (str(cif).strip(),),
        )
        for r in rows:
            r["_source"] = "db"
        return rows
    except Exception:
        return None


def _db_customer_by_cif(cif: str) -> Optional[dict]:
    """Build a customer record from cbs_accounts rows sharing this F12 CIF.

    There is no separate customer-master table — the EOD export is
    account-level. The frontend's CbsCustomer type (types/cbs.ts) requires
    every field to be present (string/bool/number, never absent) because
    the CSV-backed path (_customer_row_to_dict) always filled them in —
    returning a partial dict here crashes the UI (e.g. kycStatusTone()
    calling .toUpperCase() on an absent kyc_status). So every contract
    field gets a safe default; fields genuinely unavailable in this
    source (kyc_status, risk_rating, sector, region, ...) come back as
    "" / False / 0, which the frontend already renders as "unknown" /
    hidden badges / blank — never a crash.

    full_name is populated from AC_DESC (account_type_name) — despite
    the column name, this field holds the account holder's name on the
    individual/corporate EOD export, not a true "description".
    """
    rows = _db_accounts_for_cif(cif)
    if not rows:
        return None
    first = rows[0]
    full_name = next(
        (r.get("account_type_name") for r in rows if r.get("account_type_name")), ""
    )
    return {
        "cif":                       first.get("f12_cif") or cif,
        "full_name":                 full_name,
        "customer_type":             first.get("customer_type") or "",
        "segment":                   first.get("cust_category") or "",
        "sub_segment":               first.get("sub_segment") or "",
        "sector":                    "",
        "phone":                     first.get("phone") or "",
        "email":                     first.get("email") or "",
        "date_onboarded":            "",
        "branch_code":               first.get("branch_code") or "",
        "branch_name":               "",
        "region":                    "",
        "county":                    "",
        "relationship_manager_code": first.get("rm_code") or "",
        "kyc_status":                "",
        "risk_rating":               "",
        "is_dormant_customer":       all(bool(r.get("is_dormant")) for r in rows),
        "preferred_currency":        "",
        "total_deposit_balance":     0,
        "total_loan_balance":        0,
        "total_accounts":            len(rows),
        "aml_flag":                  False,
        "fatf_flag":                 False,
        "pep_flag":                  False,
        # Extra DB-sourced fields beyond the CbsCustomer contract — bonus
        # info the frontend can use but doesn't require.
        "cust_category":             first.get("cust_category") or "",
        "cif_class":                 first.get("cif_class") or "",
        "relationship_manager_name": first.get("rm_name") or "",
        "introducer":                first.get("introducer") or "",
        "address":                   first.get("address") or "",
        "_source":                   "db",
    }


def get_customer_by_cif(cif: str) -> Optional[dict]:
    """Lookup customer by CIF — or by account number, resolved to its
    owning CIF (see _resolve_cif). Checks cbs_accounts (Postgres, EOD
    ETL) first, falls back to customers.csv. Returns dict or None."""
    cif = _resolve_cif(cif)
    db_customer = _db_customer_by_cif(cif)
    if db_customer:
        return db_customer

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
    """Return all accounts belonging to a CIF (typically 1–5 accounts).

    Checks cbs_accounts (Postgres, EOD ETL) first; falls back to
    accounts.csv only if the DB has no rows for this CIF.

    Returns [] (never raises) if accounts.csv is missing the expected
    "cif" column or fails to load — a customer lookup should still
    succeed with an empty accounts list rather than 500.
    """
    cif = _resolve_cif(cif)
    db_rows = _db_accounts_for_cif(cif)
    if db_rows:
        return db_rows
    try:
        df = _load_accounts()
        if "cif" not in df.columns:
            logger.warning("cbs_manager: accounts.csv has no 'cif' column — columns=%s",
                            list(df.columns))
            return []
        cif = str(cif).strip()
        matches = df[df["cif"] == cif]
        return [_account_row_to_dict(row) for _, row in matches.iterrows()]
    except Exception as exc:
        logger.warning("cbs_manager: get_accounts_for_cif(%s) failed: %s", cif, exc)
        return []


def get_branches() -> list[dict]:
    return _load_branches()


def branch_code_for_name(name: str) -> list:
    """CBS branch_code(s) whose branch_name matches a (register) branch name.
    Matches on contains / stripped-'Branch' so 'Westlands' -> 'Westlands Branch'."""
    nm = str(name or "").strip().lower()
    if not nm:
        return []
    out = []
    for b in _load_branches():
        if not isinstance(b, dict):
            continue
        bn = str(b.get("branch_name") or "").strip().lower()
        if not bn:
            continue
        if nm == bn or nm == bn.replace(" branch", "").strip() or nm in bn:
            code = str(b.get("branch_code") or "").strip()
            if code:
                out.append(code)
    return out


def get_branch_unallocated(branch_codes, roster_codes) -> dict:
    """Accounts physically in the given branch_code(s) that are NOT owned by a real
    register RM (orphaned to a non-staff rm_code) — their value counts to the branch
    even though unallocated. Returns {accounts, deposits, loans}."""
    codes = {str(c).strip() for c in (branch_codes or []) if str(c).strip()}
    empty = {"accounts": 0, "deposits": 0.0, "loans": 0.0}
    if not codes:
        return empty
    df = _load_accounts()
    if df is None or df.empty or "branch_code" not in df.columns:
        return empty
    inb = df[df["branch_code"].astype(str).str.strip().isin(codes)]
    if inb.empty:
        return empty
    reg = {str(x).strip() for x in (roster_codes or set())}
    orphan = inb[~inb["relationship_manager_code"].astype(str).str.strip().isin(reg)]
    if orphan.empty:
        return {"accounts": 0, "deposits": 0.0, "loans": 0.0}
    accts = [_account_row_to_dict(r) for _, r in orphan.iterrows()]

    def _is_loan(a):
        t = str(a.get("account_type_name") or "").lower()
        return any(w in t for w in ("loan", "facility", "lpo", "mortgage", "advance"))

    dep = sum(a["current_balance"] for a in accts if not _is_loan(a))
    loan = sum(a["current_balance"] for a in accts if _is_loan(a))
    return {"accounts": len(accts), "deposits": round(dep, 2), "loans": round(loan, 2)}


def get_portfolio_for_rm(rm_code: str) -> dict:
    """Convenience wrapper: portfolio for a single RM code."""
    return get_portfolio_for_codes({str(rm_code or "").strip()})


def _staff_name_index() -> dict:
    """staff_code -> Staff Name, from the register. Cached; empty on any error."""
    global _staff_name_idx
    try:
        return _staff_name_idx  # type: ignore[name-defined]
    except NameError:
        pass
    idx = {}
    try:
        import pandas as _pd
        from pathlib import Path as _P
        p = _P(__file__).resolve().parent.parent / "data" / "staff_register.xlsx"
        if p.exists():
            dfr = _pd.read_excel(p, dtype=str).fillna("")
            for _, r in dfr.iterrows():
                cc = str(r.get("Staff Code") or "").strip()
                if cc:
                    idx[cc] = str(r.get("Staff Name") or cc).strip()
    except Exception:
        idx = {}
    globals()["_staff_name_idx"] = idx
    return idx


def get_portfolio_for_codes(codes, attribution: str = "managed") -> dict:
    """CBS accounts tagged to a set of staff codes, plus portfolio analytics.

    attribution selects the lens, and the two are kept strictly separate — never
    summed, because they answer different questions:
      "managed"    -> accounts this person is the relationship manager for (their book:
                      deposits, loans, NPL, the P&L they own)
      "introduced" -> accounts this person introduced/originated (their production),
                      which may now be managed by someone else in another segment.

    A person can appear under both, for different accounts. Deposit-movement vs the
    31-Dec baseline is only meaningful for the managed book, so it's suppressed for
    the introduced lens.
    """
    col = "introducer_code" if attribution == "introduced" else "relationship_manager_code"
    code_set = {str(x).strip() for x in (codes or set()) if str(x).strip()}
    # For the introduced lens we want ONLY accounts this scope introduced that are now
    # managed by SOMEONE ELSE — origination that sits elsewhere. Accounts they both
    # introduced and manage belong in the managed book, not here, so the two lenses
    # never overlap.
    exclude_self_managed = (attribution == "introduced")
    rm = next(iter(code_set), "") if len(code_set) == 1 else ""
    empty_summary = {"accounts": 0, "customers": 0, "total_balance": 0.0,
                     "deposits": 0.0, "loans": 0.0, "dormant_accounts": 0,
                     "dormant_pct": 0.0, "npl_accounts": 0, "by_type": [],
                     "deposit_movement": None, "baseline_date": None,
                     "attribution": attribution}
    df = _load_accounts()
    if df is None or df.empty or not code_set or col not in df.columns:
        return {"rm_code": rm, "accounts": [], "summary": empty_summary}
    mine = df[df[col].astype(str).str.strip().isin(code_set)]
    if exclude_self_managed and "relationship_manager_code" in mine.columns:
        # drop the ones this scope also manages
        mgr = mine["relationship_manager_code"].astype(str).str.strip()
        mine = mine[~mgr.isin(code_set)]
    if mine.empty:
        return {"rm_code": rm, "accounts": [], "summary": empty_summary}
    accts = [_account_row_to_dict(r) for _, r in mine.iterrows()]
    if attribution == "introduced" and accts:
        # annotate each introduced account with WHO manages it now (name + code), so the
        # UI can show the current owner alongside status / balance / loan.
        try:
            name_by_code = _staff_name_index()
        except Exception:
            name_by_code = {}
        for a in accts:
            mc = str(a.get("relationship_manager_code") or "").strip()
            a["managed_by_code"] = mc
            a["managed_by_name"] = name_by_code.get(mc, mc)

    def _is_loan(a: dict) -> bool:
        t = str(a.get("account_type_name") or "").lower()
        return "loan" in t or "facility" in t or "advance" in t or "mortgage" in t

    def _is_dormant(a: dict) -> bool:
        s = str(a.get("dormancy_status") or "").lower().strip()
        return bool(s) and s not in ("active", "regular", "none")

    def _is_npl(a: dict) -> bool:
        s = str(a.get("npl_status") or "").lower().strip()
        return s in ("npl", "non-performing", "substandard", "doubtful", "loss")

    deposits = sum(a["current_balance"] for a in accts if not _is_loan(a))
    loans = sum(a["current_balance"] for a in accts if _is_loan(a))
    dormant = sum(1 for a in accts if _is_dormant(a))
    npl = sum(1 for a in accts if _is_npl(a))
    by_type: dict = {}
    for a in accts:
        t = a.get("account_type_name") or "Other"
        e = by_type.setdefault(t, {"type": t, "count": 0, "balance": 0.0})
        e["count"] += 1
        e["balance"] += a["current_balance"]

    movement = None
    baseline_date = None
    try:
        base_path = Path(__file__).resolve().parent.parent / "data" / "cbs_baseline_2025_Dec_31.json"
        if attribution == "introduced":
            raise StopIteration  # movement is a managed-book metric only
        if base_path.exists():
            bl = json.loads(base_path.read_text(encoding="utf-8"))
            baseline_date = bl.get("snapshot_date")
            per_rm = bl.get("per_rm") or {}
            base_dep = None
            for _c in code_set:
                bd = (per_rm.get(_c) or {}).get("deposits")
                if bd is not None:
                    base_dep = (base_dep or 0) + float(bd)
            if base_dep is not None:
                movement = {"baseline": round(float(base_dep), 2), "current": round(deposits, 2),
                            "delta": round(deposits - float(base_dep), 2),
                            "pct": round((deposits - float(base_dep)) / float(base_dep) * 100, 1) if float(base_dep) else None}
    except (Exception, StopIteration):
        movement = None

    summary = {
        "accounts": len(accts), "customers": len({a["cif"] for a in accts}),
        "total_balance": round(deposits + loans, 2),
        "deposits": round(deposits, 2), "loans": round(loans, 2),
        "dormant_accounts": dormant,
        "dormant_pct": round(dormant / len(accts) * 100, 1) if accts else 0.0,
        "npl_accounts": npl,
        "by_type": sorted(({"type": k, "count": v["count"], "balance": round(v["balance"], 2)}
                           for k, v in by_type.items()), key=lambda x: -x["balance"]),
        "deposit_movement": movement, "baseline_date": baseline_date,
        "attribution": attribution,
    }
    return {"rm_code": rm, "accounts": accts, "summary": summary}


def get_aggregates() -> dict:
    return _load_aggregates()


# ── FlexCube live lookups (active when FLEXCUBE_SCRIPTS_URL is set) ─────
#
# These replace the CSV path when the FlexCube script API is reachable.
# Fall back to CSV silently so dev environments without the API still work.
# Script names (CUSTOMERACCOUNTDETAILS, CUSTOMERACTIVELOANS) match the
# confirmed-working scripts wired to 10.8.32.3 — change via env var only.

def _fc_configured() -> bool:
    try:
        from utils.flexcube_script_client import is_configured
        return is_configured()
    except Exception:
        return False


def _fc_execute(script_name: str, parameters: dict) -> list:
    from utils.flexcube_script_client import execute_script, FlexcubeScriptError
    return execute_script(script_name, parameters)


def _db_account(account_number: str) -> Optional[dict]:
    """Read from cbs_accounts (ETL table) if Postgres is ready."""
    try:
        from utils.db import db
        if not db.is_postgres_ready():
            return None
        row = db.fetch_one(
            "SELECT * FROM cbs_accounts WHERE account_number = %s",
            (str(account_number).strip(),),
        )
        if row:
            row["_source"] = "db"
        return row
    except Exception:
        return None


def get_account_by_number(account_number: str) -> Optional[dict]:
    """
    Resolution order:
      1. cbs_accounts (Postgres ETL table) — always fastest
      2. cbs_account_cache (on-demand cache) — previous FlexCube hits
      3. FlexCube live script API — writes to cache on success
      4. CSV fallback
    """
    from utils.cbs_cache import get_cached, store
    num = str(account_number).strip()

    # 1. ETL table (full nightly download)
    row = _db_account(num)
    if row:
        return row

    # 2. On-demand cache
    cached = get_cached(num)
    if cached and not cached.get("_cache_stale"):
        return cached

    # 3. FlexCube live
    if _fc_configured():
        try:
            rows = _fc_execute("CUSTOMERACCOUNTDETAILS", {"ACCOUNT_NUMBER": num})
            if rows:
                payload = rows[0]
                store(num, payload, source="flexcube")
                return payload
        except Exception:
            pass

    # 4. Stale cache beats cold CSV
    if cached:
        return cached

    # 5. CSV fallback
    df = _load_accounts()
    if "account_number" not in df.columns:
        logger.warning("cbs_manager: accounts.csv has no 'account_number' column — columns=%s",
                        list(df.columns))
        return None
    matches = df[df["account_number"] == num]
    if matches.empty:
        return None
    acct = _account_row_to_dict(matches.iloc[0])
    cif = acct.get("cif", "")
    if cif:
        customer = get_customer_by_cif(cif)
        if customer:
            acct["customer_name"] = customer["full_name"]
            acct["segment"]       = customer["segment"]
            acct["kyc_status"]    = customer["kyc_status"]
            acct["risk_rating"]   = customer["risk_rating"]
            acct["aml_flag"]      = customer["aml_flag"]
            acct["pep_flag"]      = customer["pep_flag"]
            acct["rm_code"]       = customer["relationship_manager_code"]
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
        return _fc_execute("CUSTOMERACTIVELOANS", {"CIF": resolved_f7})
    except Exception:
        return []


def get_account_360(account_number: str) -> Optional[dict]:
    """
    Combined payload: account record + all active loans.

    Caches the full combined payload (account + loans) so subsequent
    calls within the TTL window return immediately from Postgres.
    """
    from utils.cbs_cache import get_cached, store
    num = str(account_number).strip()

    # Cache hit — only serve if payload includes loans (a full 360 was stored)
    cached = get_cached(num)
    if cached and not cached.get("_cache_stale") and "active_loans" in cached:
        return cached

    # Build fresh from FlexCube or CSV
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

    # Only cache FlexCube results (CSV data is already local)
    if not account.get("_cache_hit") and _fc_configured():
        store(num, account, source="flexcube")

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

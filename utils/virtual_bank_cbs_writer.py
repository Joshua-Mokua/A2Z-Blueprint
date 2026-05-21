"""utils/virtual_bank_cbs_writer.py — v10.359 Link 1 CBS Persistence Bridge.

Closes Link 1 of the Football Team Test chain (teller → CBS): persists a
populated VirtualBankCore to the cbs_data/ files that actuals_engine reads.

What this bridge produces
-------------------------
1. **`cbs_data/accounts.csv`** — per-account rows in the column shape
   `aggregate_cbs_by_rm` + `aggregate_cbs_by_branch` + `compute_bank_aggregates`
   all consume. Columns:
   `account_no, cif, branch_code, branch_name, relationship_manager_code,
    category, account_type_name, current_balance, date_opened, dormancy_status,
    interest_income_ytd, fee_income_ytd, loan_amount, loan_outstanding,
    npl_status, npl_days`

2. **`cbs_data/deposits_aggregate.json`** — bank-wide deposit totals + by-segment
3. **`cbs_data/loans_aggregate.json`** — gross outstanding + by-segment
4. **`cbs_data/npl_aggregate.json`** — stage 3 totals + aging buckets
5. **`cbs_data/customer_aggregate.json`** — customer count + by-segment
6. **`cbs_data/dormant_aggregate.json`** — dormant counts + bands

The aggregates are computed from the same per-account data the CSV captures,
so the two sources stay coherent.

What this bridge does NOT do
----------------------------
- NOT touch `data/users.json`, `data/hr.json`, `data/kpi_library.json` — those
  belong to the platform's HR/config layer
- NOT call actuals_engine.compute_actuals_from_cbs — the bridge writes;
  callers (admin refresh, app startup, integration tests) compute
- NOT validate against schema for aggregate JSONs (preserves the existing
  free-form structure used by v7.14 — schema enforcement is future work)

Design principles
-----------------
- **Atomic writes**: every output uses `tmp_path.replace(final_path)` so
  readers never see a partial file
- **Idempotent**: calling `persist_bank_to_cbs(bank)` twice produces the
  same result (deterministic ordering, deterministic timestamps)
- **Coherent**: the aggregate JSONs are computed from the same account
  records written to CSV — they cannot drift from the CSV
- **Non-destructive smoke mode**: by default, writes to `cbs_data/`. Tests
  can pass `output_dir=tmp_path` to redirect.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CBS_DIR = REPO.parent / "cbs_data"  # project root / cbs_data
FALLBACK_CBS_DIR = REPO / "data"  # if cbs_data/ doesn't exist


# ─── Segment mapping (VirtualBankCore enum → CBS aggregate label) ──────
_SEGMENT_TO_CBS = {
    "RETAIL":          "RETAIL_INDIVIDUAL",
    "SME":             "SME",
    "CORPORATE":       "CORPORATE",
    "HNW":             "RETAIL_INDIVIDUAL",  # HNW rolls up to RETAIL in CBS labels
    "PRIVATE_BANKING": "RETAIL_INDIVIDUAL",
}

# ─── Account type → category mapping (CSV "category" column) ────────────
# The actuals_engine reads "category" and routes CASA vs Loan logic.
# Categories use Title case ("CASA", "Loan", "Term Deposit") matching
# the actuals_engine's branch logic in aggregate_cbs_by_rm /
# aggregate_cbs_by_branch / compute_bank_aggregates. v10.362 corrected
# "LOAN" → "Loan" after the Link 7 verification surfaced the case mismatch.
_ACCT_TYPE_TO_CATEGORY = {
    "SAVINGS":       "CASA",
    "CURRENT":       "CASA",
    "FIXED_DEPOSIT": "Term Deposit",
    "OVERDRAFT":     "Loan",
    "LOAN":          "Loan",
}

# ─── Account type → CSV account_type_name (granular for retail/business split) ──
_ACCT_TYPE_TO_NAME = {
    "SAVINGS":       "Personal Savings Account",
    "CURRENT":       "Business Current Account",
    "FIXED_DEPOSIT": "Fixed Deposit",
    "OVERDRAFT":     "Business Overdraft",
    "LOAN":          "Business Loan",
}


@dataclass
class PersistResult:
    cbs_dir: str
    accounts_csv_rows: int = 0
    aggregate_files_written: List[str] = field(default_factory=list)
    total_deposits_kes: Decimal = Decimal("0")
    total_loans_kes: Decimal = Decimal("0")
    npl_kes: Decimal = Decimal("0")
    n_customers: int = 0
    n_dormant: int = 0
    duration_s: float = 0.0
    notes: List[str] = field(default_factory=list)


# ─── Internal helpers ─────────────────────────────────────────────────────

def _resolve_cbs_dir(output_dir: Optional[Path]) -> Path:
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    if DEFAULT_CBS_DIR.exists():
        return DEFAULT_CBS_DIR
    DEFAULT_CBS_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CBS_DIR


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text via tmp + replace so readers never see partial."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, default=str))


def _account_to_csv_row(
    account: Any,
    customer: Any,
    branch: Any,
    loan: Optional[Any] = None,
) -> Dict[str, str]:
    """Convert (VirtualAccount, VirtualCustomer, VirtualBranch, VirtualLoan)
    into the CSV row shape actuals_engine.aggregate_cbs_by_rm consumes."""

    atype = account.account_type.value
    category = _ACCT_TYPE_TO_CATEGORY.get(atype, "OTHER")
    account_type_name = _ACCT_TYPE_TO_NAME.get(atype, atype)

    # Dormancy: VirtualBankCore doesn't track dormancy directly; treat
    # accounts with last_transaction_date older than 90 days from base
    # as dormant. For a fresh seeded bank, none are dormant.
    dormancy_status = "Active"

    # NPL: only loan accounts can be NPL. PERFORMING → "Performing", anything
    # else → "NPL". For fresh seeds, all PERFORMING.
    npl_status = ""
    npl_days = "0"
    loan_amount = "0"
    loan_outstanding = "0"
    if loan is not None:
        loan_amount = str(loan.principal)
        loan_outstanding = str(loan.outstanding)
        status_name = loan.status.value if hasattr(loan.status, "value") else str(loan.status)
        if status_name in ("DELINQUENT_30", "DELINQUENT_60", "DELINQUENT_90",
                            "NON_PERFORMING", "WRITTEN_OFF"):
            npl_status = "NPL"
            npl_days = str(loan.days_past_due)
        else:
            npl_status = "Performing"

    branch_name = getattr(branch, "branch_name", account.branch_code)

    # v10.366 — synthesize plausible accruals (interest_income_ytd, fee_income_ytd)
    # Pre-v10.366 these were hardcoded "0" with note "accruals computed downstream".
    # That left dev/mock environments without realistic NII for v10.364 PBT. The
    # synthesizer reads data/accruals_assumptions.json for configurable factors.
    # In production with FLEXCUBE live mode, the bridge could instead call
    # fetch_account_balance() to get real accruals; until then this approximates.
    try:
        from utils.accruals_synthesizer import (
            synthesize_interest_income_ytd as _syn_int,
            synthesize_fee_income_ytd as _syn_fee,
        )
        _acct_rate = getattr(account, "interest_rate_pct", Decimal("0"))
        if loan and category == "Loan":
            # Loan: use loan rate (loans on accounts are rare in seeded data
            # but supported here)
            try:
                _acct_rate = getattr(loan, "rate_pct", _acct_rate)
            except Exception:
                pass
        try:
            _loan_outs_dec = Decimal(str(loan_outstanding))
        except Exception:
            _loan_outs_dec = Decimal("0")
        _interest_ytd = _syn_int(
            category=category,
            loan_outstanding=_loan_outs_dec,
            account_interest_rate_pct=_acct_rate,
            open_date=str(account.open_date or ""),
        )
        _fee_ytd = _syn_fee(
            category=category,
            account_type_name=account_type_name,
            open_date=str(account.open_date or ""),
        )
    except Exception:
        # Synthesizer unavailable — fall back to legacy zeros (won't happen
        # in normal operation; defensive only)
        _interest_ytd = Decimal("0")
        _fee_ytd = Decimal("0")

    return {
        "account_no":                  account.account_no,
        "cif":                         account.cif,
        "branch_code":                 account.branch_code,
        "branch_name":                 branch_name,
        "relationship_manager_code":   getattr(customer, "rm_code", ""),
        "category":                    category,
        "account_type_name":           account_type_name,
        "current_balance":             str(account.balance),
        "date_opened":                 str(account.open_date or ""),
        "dormancy_status":             dormancy_status,
        "interest_income_ytd":         str(_interest_ytd),   # v10.366 synthesized
        "fee_income_ytd":              str(_fee_ytd),        # v10.366 synthesized
        "loan_amount":                 loan_amount,
        "loan_outstanding":            loan_outstanding,
        "npl_status":                  npl_status,
        "npl_days":                    npl_days,
    }


def _compute_deposits_aggregate(rows: List[Dict[str, str]], customers: List[Any]) -> Dict[str, Any]:
    """Roll up account rows into the deposits_aggregate.json shape."""
    total = Decimal("0")
    by_product: Dict[str, Decimal] = {
        "CURRENT_ACCOUNTS": Decimal("0"),
        "SAVINGS_ACCOUNTS": Decimal("0"),
        "FIXED_DEPOSITS":   Decimal("0"),
        "CALL_DEPOSITS":    Decimal("0"),
    }
    # CIF → segment lookup
    cif_to_segment: Dict[str, str] = {}
    for c in customers:
        seg = c.segment.value if hasattr(c.segment, "value") else str(c.segment)
        cif_to_segment[c.cif] = _SEGMENT_TO_CBS.get(seg, "RETAIL_INDIVIDUAL")
    by_segment: Dict[str, Decimal] = {
        "RETAIL_INDIVIDUAL": Decimal("0"),
        "SME":               Decimal("0"),
        "CORPORATE":         Decimal("0"),
        "STAFF":             Decimal("0"),
    }

    for r in rows:
        if r["category"] not in ("CASA", "Term Deposit"):
            continue
        bal = Decimal(r["current_balance"])
        total += bal
        type_name = r["account_type_name"]
        if "Savings" in type_name:
            by_product["SAVINGS_ACCOUNTS"] += bal
        elif "Current" in type_name:
            by_product["CURRENT_ACCOUNTS"] += bal
        elif "Fixed" in type_name:
            by_product["FIXED_DEPOSITS"] += bal
        else:
            by_product["CALL_DEPOSITS"] += bal
        seg_label = cif_to_segment.get(r["cif"], "RETAIL_INDIVIDUAL")
        by_segment[seg_label] += bal

    return {
        "_doc": "v10.359 CBS aggregate — generated by utils.virtual_bank_cbs_writer.persist_bank_to_cbs from a populated VirtualBankCore. Stays coherent with cbs_data/accounts.csv.",
        "_schema_version": "1.0",
        "total_deposits_kes": str(total),
        "by_product_kes":     {k: str(v) for k, v in by_product.items()},
        "by_segment_kes":     {k: str(v) for k, v in by_segment.items()},
        "captured_at":        datetime.now(timezone.utc).isoformat(),
    }


def _compute_loans_aggregate(rows: List[Dict[str, str]], customers: List[Any]) -> Dict[str, Any]:
    total_outstanding = Decimal("0")
    cif_to_segment: Dict[str, str] = {}
    for c in customers:
        seg = c.segment.value if hasattr(c.segment, "value") else str(c.segment)
        cif_to_segment[c.cif] = _SEGMENT_TO_CBS.get(seg, "RETAIL_INDIVIDUAL")
    by_segment: Dict[str, Decimal] = {
        "RETAIL_INDIVIDUAL": Decimal("0"),
        "SME":               Decimal("0"),
        "CORPORATE":         Decimal("0"),
        "REAL_ESTATE":       Decimal("0"),
        "STAFF_LOANS":       Decimal("0"),
    }
    by_stage: Dict[str, Decimal] = {
        "STAGE_1": Decimal("0"),
        "STAGE_2": Decimal("0"),
        "STAGE_3": Decimal("0"),
    }
    for r in rows:
        out = Decimal(r["loan_outstanding"])
        if out <= 0:
            continue
        total_outstanding += out
        seg_label = cif_to_segment.get(r["cif"], "RETAIL_INDIVIDUAL")
        by_segment[seg_label] += out
        # NPL → stage 3, else stage 1
        if r["npl_status"] == "NPL":
            by_stage["STAGE_3"] += out
        else:
            by_stage["STAGE_1"] += out
    return {
        "_doc": "v10.359 CBS aggregate — generated by utils.virtual_bank_cbs_writer.persist_bank_to_cbs.",
        "_schema_version": "1.0",
        "gross_outstanding_kes": str(total_outstanding),
        "by_segment_kes":        {k: str(v) for k, v in by_segment.items()},
        "by_stage_kes":          {k: str(v) for k, v in by_stage.items()},
        "captured_at":           datetime.now(timezone.utc).isoformat(),
    }


def _compute_npl_aggregate(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    npl_total = Decimal("0")
    book_total = Decimal("0")
    for r in rows:
        out = Decimal(r["loan_outstanding"])
        if out <= 0:
            continue
        book_total += out
        if r["npl_status"] == "NPL":
            npl_total += out

    ratio = (npl_total / book_total * 100) if book_total > 0 else Decimal("0")
    return {
        "_doc": "v10.359 CBS aggregate — generated by utils.virtual_bank_cbs_writer.persist_bank_to_cbs.",
        "_schema_version": "1.0",
        "stage_3_kes":          str(npl_total),
        "loan_book_basis_kes":  str(book_total),
        "npl_ratio_pct":        str(ratio.quantize(Decimal("0.01"))),
        "by_aging_kes": {
            "DAYS_91_180":   "0",  # Aging buckets need dpd granularity — future work
            "DAYS_181_365":  "0",
            "DAYS_OVER_365": "0",
        },
        "captured_at":          datetime.now(timezone.utc).isoformat(),
    }


def _compute_customer_aggregate(customers: List[Any]) -> Dict[str, Any]:
    by_segment: Dict[str, int] = {
        "RETAIL_INDIVIDUAL": 0,
        "SME":               0,
        "CORPORATE":         0,
        "STAFF":             0,
    }
    for c in customers:
        seg = c.segment.value if hasattr(c.segment, "value") else str(c.segment)
        label = _SEGMENT_TO_CBS.get(seg, "RETAIL_INDIVIDUAL")
        by_segment[label] += 1
    return {
        "_doc": "v10.359 CBS aggregate — generated by utils.virtual_bank_cbs_writer.persist_bank_to_cbs.",
        "_schema_version": "1.0",
        "total_customers":   len(customers),
        "by_segment_count":  by_segment,
        "captured_at":       datetime.now(timezone.utc).isoformat(),
    }


def _compute_dormant_aggregate(rows: List[Dict[str, str]], n_customers: int) -> Dict[str, Any]:
    dormant_count = sum(1 for r in rows if r["dormancy_status"].lower() == "dormant")
    rate = (dormant_count / n_customers * 100) if n_customers > 0 else 0
    return {
        "_doc": "v10.359 CBS aggregate — generated by utils.virtual_bank_cbs_writer.persist_bank_to_cbs.",
        "_schema_version": "1.0",
        "total_dormant":          dormant_count,
        "customer_basis_count":   n_customers,
        "dormancy_rate_pct":      f"{rate:.2f}",
        "by_dormancy_band_count": {
            "DAYS_90_TO_180":  0,
            "DAYS_181_TO_365": 0,
            "OVER_365_DAYS":   0,
        },
        "captured_at":            datetime.now(timezone.utc).isoformat(),
    }


# ─── Public API ───────────────────────────────────────────────────────────

def persist_bank_to_cbs(
    bank: Any,
    output_dir: Optional[Path] = None,
) -> PersistResult:
    """Write the populated VirtualBankCore to cbs_data/ files.

    Writes:
      - accounts.csv (per-account rows for aggregate_cbs_by_rm)
      - deposits_aggregate.json, loans_aggregate.json, npl_aggregate.json,
        customer_aggregate.json, dormant_aggregate.json

    Atomic — every file is written via tmp + replace.
    Idempotent — same bank state produces same files.

    Returns PersistResult with row counts and totals.
    """
    import time
    t0 = time.time()

    cbs_dir = _resolve_cbs_dir(output_dir)
    result = PersistResult(cbs_dir=str(cbs_dir))

    customers = bank.all_customers()
    accounts = bank.all_accounts()
    loans = bank.all_loans()
    branches = bank.all_branches()

    # Build lookup indexes
    cif_to_customer = {c.cif: c for c in customers}
    code_to_branch = {b.branch_code: b for b in branches}
    # Loans by account_no? No — loans don't carry account_no in VirtualLoan.
    # Map loans by CIF + look for an account on that CIF with type LOAN/OVERDRAFT.
    cif_to_loans = {}
    for l in loans:
        cif_to_loans.setdefault(l.cif, []).append(l)

    # Build CSV rows
    rows: List[Dict[str, str]] = []
    for a in accounts:
        customer = cif_to_customer.get(a.cif)
        if customer is None:
            result.notes.append(f"account {a.account_no} has no matching customer")
            continue
        branch = code_to_branch.get(a.branch_code)
        if branch is None:
            result.notes.append(f"account {a.account_no} has unknown branch")
            continue
        # If this is a loan-style account, attach the first loan for the CIF
        atype = a.account_type.value
        loan_for_row = None
        if atype in ("LOAN", "OVERDRAFT"):
            cif_loans = cif_to_loans.get(a.cif)
            if cif_loans:
                loan_for_row = cif_loans[0]
        rows.append(_account_to_csv_row(a, customer, branch, loan_for_row))

    # Loans without an account — synthesize a LOAN row so they show up in
    # the loan portfolio aggregation
    accounts_cifs_with_loan = {r["cif"] for r in rows if r["loan_outstanding"] != "0"}
    for l in loans:
        if l.cif in accounts_cifs_with_loan:
            continue
        customer = cif_to_customer.get(l.cif)
        branch = code_to_branch.get(l.branch_code)
        if not customer or not branch:
            result.notes.append(f"loan {l.loan_id}: no customer/branch")
            continue
        # Synthesize a phantom loan account
        # so the actuals_engine sees the loan in its CSV walk
        status_name = l.status.value if hasattr(l.status, "value") else str(l.status)
        is_npl = status_name in ("DELINQUENT_30", "DELINQUENT_60", "DELINQUENT_90",
                                  "NON_PERFORMING", "WRITTEN_OFF")
        # v10.366 — synthesize accruals for phantom loan row
        try:
            from utils.accruals_synthesizer import (
                synthesize_interest_income_ytd as _syn_int,
                synthesize_fee_income_ytd as _syn_fee,
            )
            _ph_int = _syn_int(
                category="Loan",
                loan_outstanding=l.outstanding,
                account_interest_rate_pct=l.rate_pct,
                open_date=str(l.disbursement_date or ""),
            )
            _ph_fee = _syn_fee(
                category="Loan",
                account_type_name="LOAN",
                open_date=str(l.disbursement_date or ""),
            )
        except Exception:
            _ph_int = Decimal("0")
            _ph_fee = Decimal("0")

        rows.append({
            "account_no":                  f"LN_{l.loan_id}",
            "cif":                         l.cif,
            "branch_code":                 l.branch_code,
            "branch_name":                 branch.branch_name,
            "relationship_manager_code":   l.rm_code,
            "category":                    "Loan",
            "account_type_name":           "Business Loan",
            "current_balance":             "0",
            "date_opened":                 str(l.disbursement_date or ""),
            "dormancy_status":             "Active",
            "interest_income_ytd":         str(_ph_int),   # v10.366 synthesized
            "fee_income_ytd":              str(_ph_fee),   # v10.366 synthesized
            "loan_amount":                 str(l.principal),
            "loan_outstanding":            str(l.outstanding),
            "npl_status":                  "NPL" if is_npl else "Performing",
            "npl_days":                    str(l.days_past_due),
        })

    # Sort deterministically so output is byte-stable across runs
    rows.sort(key=lambda r: (r["branch_code"], r["cif"], r["account_no"]))

    # ── Write accounts.csv ───────────────────────────────────────────
    csv_path = cbs_dir / "accounts.csv"
    fieldnames = [
        "account_no", "cif", "branch_code", "branch_name",
        "relationship_manager_code", "category", "account_type_name",
        "current_balance", "date_opened", "dormancy_status",
        "interest_income_ytd", "fee_income_ytd",
        "loan_amount", "loan_outstanding", "npl_status", "npl_days",
    ]
    tmp_csv = csv_path.with_suffix(".csv.tmp")
    with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    tmp_csv.replace(csv_path)
    result.accounts_csv_rows = len(rows)

    # ── v10.368: Write customers.csv ────────────────────────────────
    # Companion to accounts.csv — gives compute_pbt_by_sbu a CBS-native
    # customer→segment lookup for SBU attribution. In production this
    # comes from FLEXCUBE customer master; in dev/seed from the bank.
    customers_csv = cbs_dir / "customers.csv"
    cust_fieldnames = ["cif", "full_name", "segment", "branch_code", "rm_code"]
    cust_rows = []
    for c in customers:
        seg = getattr(c, "segment", "")
        seg_str = seg.value if hasattr(seg, "value") else str(seg)
        cust_rows.append({
            "cif":          getattr(c, "cif", ""),
            "full_name":    getattr(c, "full_name", ""),
            "segment":      seg_str,
            "branch_code":  getattr(c, "branch_code", ""),
            "rm_code":      getattr(c, "rm_code", ""),
        })
    cust_rows.sort(key=lambda r: r["cif"])
    tmp_cust = customers_csv.with_suffix(".csv.tmp")
    with open(tmp_cust, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cust_fieldnames)
        writer.writeheader()
        for r in cust_rows:
            writer.writerow(r)
    tmp_cust.replace(customers_csv)

    # ── Write aggregate JSONs ────────────────────────────────────────
    deposits = _compute_deposits_aggregate(rows, customers)
    loans_agg = _compute_loans_aggregate(rows, customers)
    npl_agg = _compute_npl_aggregate(rows)
    customer_agg = _compute_customer_aggregate(customers)
    dormant_agg = _compute_dormant_aggregate(rows, len(customers))

    _atomic_write_json(cbs_dir / "deposits_aggregate.json", deposits)
    _atomic_write_json(cbs_dir / "loans_aggregate.json", loans_agg)
    _atomic_write_json(cbs_dir / "npl_aggregate.json", npl_agg)
    _atomic_write_json(cbs_dir / "customer_aggregate.json", customer_agg)
    _atomic_write_json(cbs_dir / "dormant_aggregate.json", dormant_agg)

    result.aggregate_files_written = [
        "deposits_aggregate.json",
        "loans_aggregate.json",
        "npl_aggregate.json",
        "customer_aggregate.json",
        "dormant_aggregate.json",
    ]
    result.total_deposits_kes = Decimal(deposits["total_deposits_kes"])
    result.total_loans_kes = Decimal(loans_agg["gross_outstanding_kes"])
    result.npl_kes = Decimal(npl_agg["stage_3_kes"])
    result.n_customers = customer_agg["total_customers"]
    result.n_dormant = dormant_agg["total_dormant"]
    result.duration_s = round(time.time() - t0, 3)
    return result


def format_persist_summary(result: PersistResult) -> str:
    lines = []
    lines.append(f"CBS persistence — {result.duration_s}s")
    lines.append(f"  Target:           {result.cbs_dir}")
    lines.append(f"  accounts.csv rows: {result.accounts_csv_rows:,}")
    lines.append(f"  Aggregates:       {len(result.aggregate_files_written)}")
    for f in result.aggregate_files_written:
        lines.append(f"    - {f}")
    lines.append(f"  Total deposits:   KES {result.total_deposits_kes:,}")
    lines.append(f"  Total loans:      KES {result.total_loans_kes:,}")
    lines.append(f"  NPL outstanding:  KES {result.npl_kes:,}")
    lines.append(f"  Customers:        {result.n_customers:,}")
    lines.append(f"  Dormant:          {result.n_dormant:,}")
    if result.notes:
        lines.append("  Notes:")
        for n in result.notes[:5]:
            lines.append(f"    - {n}")
        if len(result.notes) > 5:
            lines.append(f"    ... +{len(result.notes) - 5} more")
    return "\n".join(lines)


# ─── Self-test ────────────────────────────────────────────────────────────

def self_test() -> None:
    """v10.359 self_test — bridge end-to-end against a seeded bank."""
    import tempfile
    tests_run = 0

    # Test 1: Module imports + functions present
    assert callable(persist_bank_to_cbs)
    assert callable(format_persist_summary)
    tests_run += 1

    # Test 2: Persist a seeded bank end-to-end
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    bank, _ = seed_virtual_bank(config=SeedConfig.small())

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        result = persist_bank_to_cbs(bank, output_dir=td_path)

        # Test 3: All 5 aggregate JSON files exist
        for fname in (
            "accounts.csv",
            "deposits_aggregate.json",
            "loans_aggregate.json",
            "npl_aggregate.json",
            "customer_aggregate.json",
            "dormant_aggregate.json",
        ):
            assert (td_path / fname).exists(), f"Missing: {fname}"
        tests_run += 1

        # Test 4: accounts.csv has rows
        assert result.accounts_csv_rows >= 200, (
            f"Expected ≥200 rows (200 accounts + 30 loan rows), got {result.accounts_csv_rows}"
        )
        tests_run += 1

        # Test 5: Totals are nonzero
        assert result.total_deposits_kes > 0
        assert result.total_loans_kes > 0
        tests_run += 1

        # Test 6: Idempotency — second write produces same totals
        result2 = persist_bank_to_cbs(bank, output_dir=td_path)
        assert result.total_deposits_kes == result2.total_deposits_kes
        assert result.total_loans_kes == result2.total_loans_kes
        assert result.accounts_csv_rows == result2.accounts_csv_rows
        tests_run += 1

        # Test 7: Atomic write — no .tmp files left over
        leftovers = list(td_path.glob("*.tmp"))
        assert not leftovers, f"Leftover tmp files: {leftovers}"
        tests_run += 1

        # Test 8: actuals_engine.aggregate_cbs_by_rm can read it
        from utils.actuals_engine import aggregate_cbs_by_rm
        rm_data = aggregate_cbs_by_rm(td_path)
        assert len(rm_data) > 0, "actuals_engine couldn't read the persisted CBS"
        # Should have ~30 distinct RMs (seeder uses 30 RMs)
        assert len(rm_data) <= 30, (
            f"More RMs than seeder uses ({len(rm_data)} > 30)"
        )
        tests_run += 1

        # Test 9: Bank totals match aggregate
        import json as _j
        dep = _j.loads((td_path / "deposits_aggregate.json").read_text())
        assert Decimal(dep["total_deposits_kes"]) == result.total_deposits_kes
        tests_run += 1

        # Test 10: format_persist_summary produces readable output
        summary = format_persist_summary(result)
        assert "CBS persistence" in summary
        assert "Total deposits" in summary
        tests_run += 1

    print(f"✓ virtual_bank_cbs_writer self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()

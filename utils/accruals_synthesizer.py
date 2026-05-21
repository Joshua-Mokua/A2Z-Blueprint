"""utils/accruals_synthesizer.py — v10.366 CBS Accruals Synthesizer.

Closes the "0 income" stub gap in the v10.359 bridge. Pre-v10.366 the
bridge wrote `interest_income_ytd = "0"` and `fee_income_ytd = "0"` for
every account ("accruals computed downstream"), because in production
FLEXCUBE/Oracle provides these values directly. In dev/mock environments
without FLEXCUBE, that left v10.364's PBT computation showing NII = 0
and Operating Income dominated by interest expense — unrealistic.

This module synthesizes plausible accruals from account properties:

- **Loans**: `interest_income_ytd = outstanding × rate_pct × elapsed_days / 365`
  (the bank earns interest income from loan customers)

- **CASA / Term Deposits**: `interest_income_ytd = 0`
  (the bank PAYS interest on deposits — that's interest expense, computed
  separately in pbt_computation via `cost_of_funds_pct × total_deposits`)

- **All accounts**: `fee_income_ytd = monthly_account_fee × months_elapsed`
  (monthly maintenance fees; configurable per account type)

All factors live in `data/accruals_assumptions.json` (Rule N1 —
configurable, not hardcoded). Defaults match Kenyan market norms:

  - default_loan_rate_pct        : 14% (used when account's own rate is 0)
  - monthly_account_fee_savings  : KES 50
  - monthly_account_fee_current  : KES 200
  - monthly_account_fee_term     : KES 0   (FDs don't carry monthly fees)
  - monthly_account_fee_loan     : KES 100 (loan service fees)
  - as_of_date                   : "2026-04-30" (date for elapsed-time
                                     calculations; configurable so dev
                                     scenarios can simulate different YTD points)
  - min_account_age_days         : 30      (skip very fresh accounts)

Determinism: same inputs → same outputs. No randomness.
Pure module: zero upward `utils.*` imports (v10.364 lesson — utility
modules must not import their consumers, even in self_test bodies).

Why "synthesize" not "compute":
The bank's true accruals come from a full loan amortization schedule,
fee-event journals, and accrual GL entries — all in FLEXCUBE/Oracle.
This module produces plausible values for development environments
where those upstream systems aren't connected. In production with
`flexcube_config.json::mode = "live"`, the bridge can call
`fetch_account_balance(...)` and similar to get real accruals from
FLEXCUBE, bypassing this synthesizer.

The synthesizer answers: "what would NII look like if this synthetic
bank had been running for X months?" — not: "what are the actual
accruals?" The configurable `as_of_date` makes the time horizon
explicit and adjustable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# Loan-eligible category strings (Title case — matches v10.362 fix)
_LOAN_CATEGORIES = ("Loan",)
_DEPOSIT_CATEGORIES = ("CASA", "Term Deposit")

# Default account-type → fee key mapping
_FEE_KEY_BY_ACCOUNT_TYPE = {
    "SAVINGS":       "monthly_account_fee_savings",
    "CURRENT":       "monthly_account_fee_current",
    "FIXED_DEPOSIT": "monthly_account_fee_term",
    "OVERDRAFT":     "monthly_account_fee_loan",
    "LOAN":          "monthly_account_fee_loan",
}


@dataclass(frozen=True)
class AccrualAssumptions:
    """All factors configurable in data/accruals_assumptions.json (Rule N1)."""
    as_of_date: str
    default_loan_rate_pct: Decimal
    monthly_account_fee_savings: Decimal
    monthly_account_fee_current: Decimal
    monthly_account_fee_term: Decimal
    monthly_account_fee_loan: Decimal
    min_account_age_days: int


def _load_accrual_assumptions() -> AccrualAssumptions:
    """Read data/accruals_assumptions.json, fall back to defaults if missing."""
    defaults = AccrualAssumptions(
        as_of_date="2026-04-30",
        default_loan_rate_pct=Decimal("14.0"),
        monthly_account_fee_savings=Decimal("50"),
        monthly_account_fee_current=Decimal("200"),
        monthly_account_fee_term=Decimal("0"),
        monthly_account_fee_loan=Decimal("100"),
        min_account_age_days=30,
    )
    path = DATA_DIR / "accruals_assumptions.json"
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AccrualAssumptions(
            as_of_date=str(data.get("as_of_date", defaults.as_of_date)),
            default_loan_rate_pct=Decimal(str(
                data.get("default_loan_rate_pct", defaults.default_loan_rate_pct))),
            monthly_account_fee_savings=Decimal(str(
                data.get("monthly_account_fee_savings",
                         defaults.monthly_account_fee_savings))),
            monthly_account_fee_current=Decimal(str(
                data.get("monthly_account_fee_current",
                         defaults.monthly_account_fee_current))),
            monthly_account_fee_term=Decimal(str(
                data.get("monthly_account_fee_term",
                         defaults.monthly_account_fee_term))),
            monthly_account_fee_loan=Decimal(str(
                data.get("monthly_account_fee_loan",
                         defaults.monthly_account_fee_loan))),
            min_account_age_days=int(
                data.get("min_account_age_days", defaults.min_account_age_days)),
        )
    except Exception:
        return defaults


def _days_between(open_date_str: str, as_of_date_str: str) -> int:
    """Days from open_date to as_of_date (inclusive). Returns 0 on error."""
    try:
        open_d = datetime.strptime(open_date_str, "%Y-%m-%d").date()
        as_of_d = datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        if as_of_d < open_d:
            return 0
        return (as_of_d - open_d).days
    except Exception:
        return 0


def synthesize_interest_income_ytd(
    category: str,
    loan_outstanding: Decimal,
    account_interest_rate_pct: Decimal,
    open_date: str,
    assumptions: Optional[AccrualAssumptions] = None,
) -> Decimal:
    """Synthesize YTD interest income for a single account row.

    Loans: outstanding × rate × elapsed_days / 365
    Deposits/CASA: 0 (bank doesn't earn interest on customer deposits —
                       that's interest expense, computed in PBT separately)

    Args:
        category: "Loan" | "CASA" | "Term Deposit" (Title case)
        loan_outstanding: from row; 0 for non-loans
        account_interest_rate_pct: rate stored on the account/loan
        open_date: ISO date string from row
        assumptions: loaded once and passed; loads defaults if None

    Returns: Decimal interest income YTD (always non-negative).
    """
    if assumptions is None:
        assumptions = _load_accrual_assumptions()
    if category not in _LOAN_CATEGORIES:
        return Decimal("0")
    if loan_outstanding <= 0:
        return Decimal("0")
    days = _days_between(open_date, assumptions.as_of_date)
    if days < assumptions.min_account_age_days:
        return Decimal("0")
    # Use the account's own rate if set; otherwise the default
    rate = account_interest_rate_pct if account_interest_rate_pct > 0 \
        else assumptions.default_loan_rate_pct
    accrued = (loan_outstanding * rate / 100 * Decimal(days) / Decimal("365"))
    return accrued.quantize(Decimal("1"))  # whole KES


def synthesize_fee_income_ytd(
    category: str,
    account_type_name: str,
    open_date: str,
    assumptions: Optional[AccrualAssumptions] = None,
) -> Decimal:
    """Synthesize YTD fee income (monthly maintenance fees).

    Args:
        category: "Loan" | "CASA" | "Term Deposit" — informational
        account_type_name: e.g. "SAVINGS", "CURRENT", "LOAN" (uppercase
                           per VirtualAccount.account_type)
        open_date: ISO date string
        assumptions: loaded once and passed

    Returns: Decimal fee income YTD (always non-negative).
    """
    if assumptions is None:
        assumptions = _load_accrual_assumptions()
    days = _days_between(open_date, assumptions.as_of_date)
    if days < assumptions.min_account_age_days:
        return Decimal("0")
    months = Decimal(days) / Decimal("30")  # approximate
    # Map account_type → fee key
    upper_type = (account_type_name or "").upper()
    # Find the best fee key by substring match (handles "SAVINGS", "savings", etc)
    fee_key = None
    for key, fee_attr in _FEE_KEY_BY_ACCOUNT_TYPE.items():
        if key in upper_type:
            fee_key = fee_attr
            break
    if fee_key is None:
        # Unknown account type — no fee
        return Decimal("0")
    monthly_fee = getattr(assumptions, fee_key, Decimal("0"))
    if monthly_fee <= 0:
        return Decimal("0")
    accrued = (monthly_fee * months).quantize(Decimal("1"))
    return accrued


def synthesize_row_accruals(
    row: Dict[str, str],
    account_interest_rate_pct: Decimal = Decimal("0"),
    assumptions: Optional[AccrualAssumptions] = None,
) -> Dict[str, str]:
    """Return a NEW row dict with interest_income_ytd and fee_income_ytd
    populated. Original row is not mutated.

    Helper for the bridge to call: takes the row dict it would write,
    returns the row dict with accruals synthesized.
    """
    if assumptions is None:
        assumptions = _load_accrual_assumptions()
    new_row = dict(row)
    try:
        loan_outstanding = Decimal(str(row.get("loan_outstanding") or "0"))
    except Exception:
        loan_outstanding = Decimal("0")
    category = row.get("category", "")
    account_type = row.get("account_type_name", "")
    open_date = row.get("date_opened", "")

    interest = synthesize_interest_income_ytd(
        category=category,
        loan_outstanding=loan_outstanding,
        account_interest_rate_pct=account_interest_rate_pct,
        open_date=open_date,
        assumptions=assumptions,
    )
    fee = synthesize_fee_income_ytd(
        category=category,
        account_type_name=account_type,
        open_date=open_date,
        assumptions=assumptions,
    )
    new_row["interest_income_ytd"] = str(interest)
    new_row["fee_income_ytd"] = str(fee)
    return new_row


def self_test() -> None:
    """v10.366 self_test — hand-rolled fixtures only.

    Deliberately does NOT import from utils.virtual_bank_seed or
    utils.virtual_bank_cbs_writer (v10.364 lesson: that creates
    circular imports because consumers import back through actuals_engine).
    """
    tests_run = 0

    # Test 1: defaults work when file missing
    a = _load_accrual_assumptions()
    assert a.default_loan_rate_pct > 0
    assert a.monthly_account_fee_current > 0
    tests_run += 1

    # Test 2: days_between
    assert _days_between("2026-01-01", "2026-01-31") == 30
    assert _days_between("2026-01-31", "2026-01-01") == 0  # past as_of
    assert _days_between("garbage", "2026-01-01") == 0
    tests_run += 1

    # Test 3: non-loan returns 0 interest
    assert synthesize_interest_income_ytd(
        category="CASA",
        loan_outstanding=Decimal("0"),
        account_interest_rate_pct=Decimal("5"),
        open_date="2025-01-01",
    ) == Decimal("0")
    tests_run += 1

    # Test 4: fresh loan (< min_account_age_days) returns 0
    a = _load_accrual_assumptions()
    fresh_date = a.as_of_date  # 0 days elapsed
    assert synthesize_interest_income_ytd(
        category="Loan",
        loan_outstanding=Decimal("1000000"),
        account_interest_rate_pct=Decimal("14"),
        open_date=fresh_date,
    ) == Decimal("0")
    tests_run += 1

    # Test 5: aged loan accrues interest correctly
    # 1M outstanding × 14% × 365/365 = 140k per year
    one_year = synthesize_interest_income_ytd(
        category="Loan",
        loan_outstanding=Decimal("1000000"),
        account_interest_rate_pct=Decimal("14"),
        open_date="2025-04-30",  # exactly 1 year before default as_of
    )
    # Allow Decimal rounding tolerance
    assert one_year > Decimal("139000") and one_year < Decimal("141000"), \
        f"Expected ~140k, got {one_year}"
    tests_run += 1

    # Test 6: loan with rate=0 uses default rate
    accrued = synthesize_interest_income_ytd(
        category="Loan",
        loan_outstanding=Decimal("1000000"),
        account_interest_rate_pct=Decimal("0"),  # falls back to default 14%
        open_date="2025-04-30",
    )
    assert accrued > Decimal("100000")  # uses default ~14%
    tests_run += 1

    # Test 7: fee income for current account, 1 year elapsed
    fee = synthesize_fee_income_ytd(
        category="CASA",
        account_type_name="CURRENT",
        open_date="2025-04-30",
    )
    # 200/month × 12 months = 2400
    assert fee > Decimal("2300") and fee < Decimal("2500"), \
        f"Expected ~2400 fee, got {fee}"
    tests_run += 1

    # Test 8: synthesize_row_accruals end-to-end
    sample_row = {
        "category": "Loan",
        "account_type_name": "LOAN",
        "loan_outstanding": "5000000",
        "date_opened": "2025-04-30",
    }
    new_row = synthesize_row_accruals(
        sample_row,
        account_interest_rate_pct=Decimal("12"),
    )
    # Original not mutated
    assert sample_row.get("interest_income_ytd") is None
    # New row has both keys populated
    assert "interest_income_ytd" in new_row
    assert "fee_income_ytd" in new_row
    interest_val = Decimal(new_row["interest_income_ytd"])
    fee_val = Decimal(new_row["fee_income_ytd"])
    assert interest_val > 0
    assert fee_val > 0  # LOAN type has 100/month fee
    tests_run += 1

    # Test 9: term deposit fee_income = 0 (default)
    fee_td = synthesize_fee_income_ytd(
        category="Term Deposit",
        account_type_name="FIXED_DEPOSIT",
        open_date="2025-04-30",
    )
    assert fee_td == Decimal("0"), f"Term deposit fee should be 0, got {fee_td}"
    tests_run += 1

    # Test 10: Determinism — same inputs produce same outputs
    args = dict(
        category="Loan",
        loan_outstanding=Decimal("3000000"),
        account_interest_rate_pct=Decimal("11.5"),
        open_date="2025-09-15",
    )
    a1 = synthesize_interest_income_ytd(**args)
    a2 = synthesize_interest_income_ytd(**args)
    assert a1 == a2, f"Non-deterministic: {a1} != {a2}"
    tests_run += 1

    print(f"✓ accruals_synthesizer self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()

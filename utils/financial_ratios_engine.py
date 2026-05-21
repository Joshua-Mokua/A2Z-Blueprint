"""utils/financial_ratios_engine.py — v10.390 Financial Ratio KPI Computations.

Tier-1 Class B KPI foundation per v10.382 KPI Implementation Plan. Computes
NIM, CIR, ROE, DEP_GROWTH from management_accounts data.

Per v10.385 body diagnosis: these 4 KPIs (plus NPS and DIGITAL_ACT in
v10.391) close the nervous-system gap that prevents MD's BSC from
presenting a complete banking story.

Module purity: leaf module — zero upward `utils.*` imports. Pure I/O +
Decimal arithmetic + result dataclasses.

Data source:
    data/mgmt_accounts.json — income_statement (interest_income,
    interest_expense, opex, total_income, pbt) + balance_sheet
    (loans_net_b, investments_b, equity_b, customer_deposits_b) +
    key_ratios (reference values for validation).

Note on units:
    income_statement fields use `_m` suffix (millions KES).
    balance_sheet fields use `_b` suffix (billions KES).
    Engine normalizes to billions internally and reports in
    DEFAULT_REPORTING_UNIT.

Note on period:
    mgmt_accounts.json contains a single period snapshot. The engine
    reports the period as-stored. Annualization is NOT applied — that's
    a separate concern (engine reports raw period ratios; consumers
    annualize if needed).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, Optional

# Use high precision for financial ratios
getcontext().prec = 28

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
MGMT_ACCOUNTS_PATH = DATA_DIR / "mgmt_accounts.json"

# Internal normalization: convert all to billions KES (matches balance_sheet)
M_TO_B = Decimal("0.001")     # 1 million KES = 0.001 billion KES
DEFAULT_REPORTING_UNIT = "billions KES"


# ────────────────────────────────────────────────────────────────────
# Result dataclasses (consumers see headline + all components)
# ────────────────────────────────────────────────────────────────────

@dataclass
class NIMResult:
    period: str
    interest_income_b:     Decimal   # billions KES
    interest_expense_b:    Decimal
    nii_b:                 Decimal   # net interest income
    avg_earning_assets_b:  Decimal   # avg(loans + investments)
    nim_pct:               Decimal   # headline: NII / avg_earning_assets * 100
    source:                str

    def to_dict(self) -> Dict[str, Any]:
        return {k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in asdict(self).items()}


@dataclass
class CIRResult:
    period:        str
    opex_b:        Decimal
    total_income_b: Decimal
    cir_pct:       Decimal   # headline: opex / total_income * 100
    source:        str

    def to_dict(self) -> Dict[str, Any]:
        return {k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in asdict(self).items()}


@dataclass
class ROEResult:
    period:       str
    pbt_b:        Decimal
    avg_equity_b: Decimal
    roe_pct:      Decimal   # headline: PBT / avg_equity * 100
    source:       str
    note:         str       # e.g. "uses PBT (not net income, no tax field)"

    def to_dict(self) -> Dict[str, Any]:
        return {k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in asdict(self).items()}


@dataclass
class DepGrowthResult:
    period:           str
    deposits_eop_b:   Decimal
    deposits_bop_b:   Decimal
    delta_b:          Decimal
    growth_pct:       Decimal   # headline: (eop - bop) / bop * 100
    source:           str

    def to_dict(self) -> Dict[str, Any]:
        return {k: (float(v) if isinstance(v, Decimal) else v)
                for k, v in asdict(self).items()}


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _safe_load_mgmt_accounts() -> Optional[Dict[str, Any]]:
    """Read mgmt_accounts.json. Return None on any failure."""
    if not MGMT_ACCOUNTS_PATH.exists():
        return None
    try:
        return json.loads(MGMT_ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Convert value to Decimal, returning default if unparseable."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _safe_divide(num: Decimal, denom: Decimal) -> Decimal:
    """num / denom * 100. Returns 0 if denom is 0."""
    if denom == 0:
        return Decimal("0")
    return (num / denom) * Decimal("100")


# ────────────────────────────────────────────────────────────────────
# Public computation API
# ────────────────────────────────────────────────────────────────────

def compute_nim(mgmt_data: Optional[Dict[str, Any]] = None) -> Optional[NIMResult]:
    """Compute Net Interest Margin from management_accounts.

    NIM = NII / avg_earning_assets * 100

    Earning assets = loans_net_b + investments_b
    Average = (current + prior) / 2

    Returns None if mgmt_accounts not available.
    """
    if mgmt_data is None:
        mgmt_data = _safe_load_mgmt_accounts()
    if mgmt_data is None:
        return None

    inc = mgmt_data.get("income_statement", {})
    bs = mgmt_data.get("balance_sheet", {})

    interest_income_m  = _to_decimal(inc.get("interest_income", {}).get("actual_m"))
    interest_expense_m = _to_decimal(inc.get("interest_expense", {}).get("actual_m"))
    nii_m = interest_income_m - interest_expense_m

    loans_curr_b       = _to_decimal(bs.get("loans_net_b", {}).get("actual"))
    loans_prior_b      = _to_decimal(bs.get("loans_net_b", {}).get("prior"))
    invest_curr_b      = _to_decimal(bs.get("investments_b", {}).get("actual"))
    invest_prior_b     = _to_decimal(bs.get("investments_b", {}).get("prior"))

    earning_curr_b = loans_curr_b + invest_curr_b
    earning_prior_b = loans_prior_b + invest_prior_b
    avg_earning_b = (earning_curr_b + earning_prior_b) / Decimal("2")

    nii_b = nii_m * M_TO_B
    nim_pct = _safe_divide(nii_b, avg_earning_b)

    return NIMResult(
        period=mgmt_data.get("period", "unknown"),
        interest_income_b=interest_income_m * M_TO_B,
        interest_expense_b=interest_expense_m * M_TO_B,
        nii_b=nii_b,
        avg_earning_assets_b=avg_earning_b,
        nim_pct=nim_pct,
        source="mgmt_accounts.income_statement + balance_sheet",
    )


def compute_cir(mgmt_data: Optional[Dict[str, Any]] = None) -> Optional[CIRResult]:
    """Compute Cost-to-Income Ratio from management_accounts.

    CIR = opex / total_income * 100. Lower is better.

    Returns None if mgmt_accounts not available.
    """
    if mgmt_data is None:
        mgmt_data = _safe_load_mgmt_accounts()
    if mgmt_data is None:
        return None

    inc = mgmt_data.get("income_statement", {})
    opex_m = _to_decimal(inc.get("opex", {}).get("actual_m"))
    total_income_m = _to_decimal(inc.get("total_income", {}).get("actual_m"))

    opex_b = opex_m * M_TO_B
    total_income_b = total_income_m * M_TO_B
    cir_pct = _safe_divide(opex_b, total_income_b)

    return CIRResult(
        period=mgmt_data.get("period", "unknown"),
        opex_b=opex_b,
        total_income_b=total_income_b,
        cir_pct=cir_pct,
        source="mgmt_accounts.income_statement",
    )


def compute_roe(mgmt_data: Optional[Dict[str, Any]] = None) -> Optional[ROEResult]:
    """Compute Return on Equity from management_accounts.

    Notes:
      - Uses PBT (Profit Before Tax) — mgmt_accounts doesn't have a
        separate tax/net-income field. Engine reports this explicitly
        in the `.note` field so consumers can adjust.
      - Avg equity = (current + prior) / 2.

    Returns None if mgmt_accounts not available.
    """
    if mgmt_data is None:
        mgmt_data = _safe_load_mgmt_accounts()
    if mgmt_data is None:
        return None

    inc = mgmt_data.get("income_statement", {})
    bs = mgmt_data.get("balance_sheet", {})

    pbt_m = _to_decimal(inc.get("pbt", {}).get("actual_m"))
    equity_curr_b = _to_decimal(bs.get("equity_b", {}).get("actual"))
    equity_prior_b = _to_decimal(bs.get("equity_b", {}).get("prior"))

    pbt_b = pbt_m * M_TO_B
    avg_equity_b = (equity_curr_b + equity_prior_b) / Decimal("2")
    roe_pct = _safe_divide(pbt_b, avg_equity_b)

    return ROEResult(
        period=mgmt_data.get("period", "unknown"),
        pbt_b=pbt_b,
        avg_equity_b=avg_equity_b,
        roe_pct=roe_pct,
        source="mgmt_accounts.income_statement + balance_sheet",
        note="uses PBT (not net income — mgmt_accounts has no tax field)",
    )


def compute_total_deposit_growth(
    mgmt_data: Optional[Dict[str, Any]] = None,
) -> Optional[DepGrowthResult]:
    """Compute total deposit growth from management_accounts.

    Growth = (eop - bop) / bop * 100. Higher is better.

    Returns None if mgmt_accounts not available.
    """
    if mgmt_data is None:
        mgmt_data = _safe_load_mgmt_accounts()
    if mgmt_data is None:
        return None

    bs = mgmt_data.get("balance_sheet", {})
    deposits_eop_b = _to_decimal(bs.get("customer_deposits_b", {}).get("actual"))
    deposits_bop_b = _to_decimal(bs.get("customer_deposits_b", {}).get("prior"))

    delta_b = deposits_eop_b - deposits_bop_b
    growth_pct = _safe_divide(delta_b, deposits_bop_b)

    return DepGrowthResult(
        period=mgmt_data.get("period", "unknown"),
        deposits_eop_b=deposits_eop_b,
        deposits_bop_b=deposits_bop_b,
        delta_b=delta_b,
        growth_pct=growth_pct,
        source="mgmt_accounts.balance_sheet",
    )


def compute_all_financial_ratios(
    mgmt_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[Any]]:
    """Compute all 4 ratios in one call. Returns dict keyed by KPI id."""
    if mgmt_data is None:
        mgmt_data = _safe_load_mgmt_accounts()
    return {
        "NIM":        compute_nim(mgmt_data),
        "CIR":        compute_cir(mgmt_data),
        "ROE":        compute_roe(mgmt_data),
        "DEP_GROWTH": compute_total_deposit_growth(mgmt_data),
    }


# ────────────────────────────────────────────────────────────────────
# Self-test
# ────────────────────────────────────────────────────────────────────

def self_test() -> None:
    """Embedded tests — run on import for fail-fast detection."""
    tests = 0

    # Test 1: mgmt_accounts.json exists and parses
    mgmt = _safe_load_mgmt_accounts()
    assert mgmt is not None, "mgmt_accounts.json missing or unparseable"
    tests += 1

    # Test 2: NIM computes a positive value
    r = compute_nim(mgmt)
    assert r is not None
    assert r.nim_pct > 0, f"NIM should be > 0, got {r.nim_pct}"
    assert r.interest_income_b > 0
    assert r.nii_b > 0
    tests += 1

    # Test 3: CIR computes a sane value (0-100%)
    r = compute_cir(mgmt)
    assert r is not None
    assert 0 < r.cir_pct < 100, f"CIR out of range: {r.cir_pct}"
    assert r.opex_b > 0
    assert r.total_income_b > 0
    tests += 1

    # Test 4: ROE computes a value (likely positive)
    r = compute_roe(mgmt)
    assert r is not None
    assert r.roe_pct != 0, f"ROE = 0 unexpected: {r}"
    assert r.pbt_b > 0
    assert r.avg_equity_b > 0
    assert "PBT" in r.note  # note explains the PBT-vs-net-income caveat
    tests += 1

    # Test 5: DEP_GROWTH computes a value
    r = compute_total_deposit_growth(mgmt)
    assert r is not None
    assert r.deposits_eop_b > 0
    assert r.deposits_bop_b > 0
    tests += 1

    # Test 6: compute_all_financial_ratios returns 4 results
    all_r = compute_all_financial_ratios(mgmt)
    assert set(all_r.keys()) == {"NIM", "CIR", "ROE", "DEP_GROWTH"}
    assert all(v is not None for v in all_r.values())
    tests += 1

    # Test 7: result dataclasses serialize cleanly to dict
    nim = compute_nim(mgmt)
    d = nim.to_dict()
    for v in d.values():
        # No Decimal values should remain in serialized form
        assert not isinstance(v, Decimal)
    tests += 1

    # Test 8: missing mgmt_data returns None gracefully
    assert compute_nim({}) is not None  # empty dict still returns (with zeros)
    # Empty data gives zero ratios — acceptable
    tests += 1

    # Test 9: divide-by-zero handled safely
    empty_inc = {"income_statement": {}, "balance_sheet": {}}
    r = compute_nim(empty_inc)
    assert r is not None
    assert r.nim_pct == 0  # not NaN, not error — just 0
    tests += 1

    print(f"✓ financial_ratios_engine self_test passed ({tests} tests)")
    print(f"  NIM = {compute_nim(mgmt).nim_pct:.2f}%")
    print(f"  CIR = {compute_cir(mgmt).cir_pct:.2f}%")
    print(f"  ROE = {compute_roe(mgmt).roe_pct:.2f}%")
    print(f"  DEP_GROWTH = {compute_total_deposit_growth(mgmt).growth_pct:.2f}%")


if __name__ == "__main__":
    import sys as _sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in _sys.path:
        _sys.path.insert(0, str(_repo))
    self_test()

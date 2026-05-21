"""utils/branch_pbt_allocator.py — v10.369 Per-Branch PBT Allocation Engine.

Second concrete unification step from the v10.367 architecture arc. Replaces
the legacy `aggregate_cbs_by_branch` naive formula (`int + fee - loans × 0.02`)
with a proper allocation engine.

The reconciliation identity that holds (locked by G255):
    Σ(Branch PBT) == Bank PBT  within KES 100 tolerance

How allocation works
--------------------
Per-branch **income** rolls up from accounts.csv directly — each account
belongs to exactly one branch (via `branch_code`). NII, fee income,
and NPL Stage 3 are all aggregations of account-level data.

Per-branch **OpEx** is allocated from `opex_data.json::bank.total_opex` by
a configurable driver. Four rules supported:

  • `fte_weighted` (default, per Q3): allocate by branch FTE share.
    Falls back to `accounts_proxy` if FTE data unavailable.
  • `revenue_weighted`: allocate by branch operating-income share.
  • `equal`: split equally across all branches with any accounts.
  • `hybrid`: 50% FTE-weighted + 50% revenue-weighted.

All factors live in `data/branch_allocation_rules.json` (Rule N1).

FTE data fallback chain
-----------------------
1. Caller-provided `branch_fte_lookup: Dict[str, int]` (highest priority —
   production gets this from a branch master / staff register)
2. `data/branch_fte.json` if it exists (admin can populate)
3. Proxy: count of accounts per branch (degraded; flagged in notes)
4. Equal: if all branches have 0 accounts, fall back to equal split

The chain ensures the allocator always produces a meaningful result, even
in development environments where per-branch FTE data isn't yet generated.

Module purity
-------------
Imports `utils.pbt_computation` (PBTComponents + assumption loaders) —
a legitimate downward import. Self-test uses hand-rolled CSV fixtures
per the v10.364 lesson — no upward consumer imports.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# Allocation rules supported
_RULE_FTE_WEIGHTED = "fte_weighted"
_RULE_REVENUE_WEIGHTED = "revenue_weighted"
_RULE_EQUAL = "equal"
_RULE_HYBRID = "hybrid"
_ALL_RULES = (_RULE_FTE_WEIGHTED, _RULE_REVENUE_WEIGHTED,
              _RULE_EQUAL, _RULE_HYBRID)


def _load_allocation_rules() -> Dict[str, Any]:
    """Load data/branch_allocation_rules.json (Rule N1).

    Returns defaults if missing. Per-admin editable.
    """
    defaults = {
        "default_rule": _RULE_FTE_WEIGHTED,
        "hybrid_fte_weight": 0.5,
        "hybrid_revenue_weight": 0.5,
    }
    path = DATA_DIR / "branch_allocation_rules.json"
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "default_rule": data.get("default_rule", defaults["default_rule"]),
            "hybrid_fte_weight": Decimal(str(
                data.get("hybrid_fte_weight", defaults["hybrid_fte_weight"]))),
            "hybrid_revenue_weight": Decimal(str(
                data.get("hybrid_revenue_weight", defaults["hybrid_revenue_weight"]))),
        }
    except Exception:
        return defaults


def _load_branch_fte_lookup() -> Dict[str, int]:
    """Load per-branch FTE counts from data/branch_fte.json if present.

    Returns empty dict if missing (caller's responsibility to fall back).
    """
    path = DATA_DIR / "branch_fte.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in data.items() if k != "_schema_version"}
    except Exception:
        return {}


def _load_bank_total_opex() -> Decimal:
    """Load bank.total_opex_kes_b from opex_data.json (converted to raw KES)."""
    path = DATA_DIR / "opex_data.json"
    if not path.exists():
        return Decimal("0")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Decimal(str(
            data.get("bank", {}).get("total_opex_kes_b", 0)
        )) * Decimal("1000000000")
    except Exception:
        return Decimal("0")


def _aggregate_branches_from_csv(cbs_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Walk accounts.csv, group by branch_code, accumulate raw figures.

    Returns dict keyed by branch_code with:
      branch_name, accounts_count, interest_income, fee_income,
      deposits, loan_outstanding, npl_outstanding
    """
    out: Dict[str, Dict[str, Any]] = {}
    acct_csv = cbs_dir / "accounts.csv"
    if not acct_csv.exists():
        return out
    with open(str(acct_csv), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            bc = row.get("branch_code", "") or "Unallocated"
            if bc not in out:
                out[bc] = {
                    "branch_name":      row.get("branch_name", bc),
                    "accounts_count":   0,
                    "interest_income":  Decimal("0"),
                    "fee_income":       Decimal("0"),
                    "deposits":         Decimal("0"),
                    "loan_outstanding": Decimal("0"),
                    "npl_outstanding":  Decimal("0"),
                }
            entry = out[bc]
            entry["accounts_count"] += 1
            try:
                entry["interest_income"] += Decimal(str(
                    row.get("interest_income_ytd") or "0"))
            except Exception:
                pass
            try:
                entry["fee_income"] += Decimal(str(
                    row.get("fee_income_ytd") or "0"))
            except Exception:
                pass
            try:
                bal = Decimal(str(row.get("current_balance") or "0"))
            except Exception:
                bal = Decimal("0")
            try:
                lo = Decimal(str(row.get("loan_outstanding") or "0"))
            except Exception:
                lo = Decimal("0")
            cat = row.get("category", "")
            if cat in ("CASA", "Term Deposit"):
                entry["deposits"] += bal
            if cat == "Loan":
                entry["loan_outstanding"] += lo
                if row.get("npl_status") == "NPL":
                    entry["npl_outstanding"] += lo
    return out


def _compute_allocation_shares(
    branches: Dict[str, Dict[str, Any]],
    rule: str,
    branch_fte_lookup: Dict[str, int],
    rules_config: Dict[str, Any],
) -> Tuple[Dict[str, Decimal], List[str]]:
    """Return {branch_code: opex_share_fraction} where shares sum to 1.

    Notes returned alongside surface any fallback behavior used.
    """
    notes: List[str] = []
    branch_codes = list(branches.keys())
    n_branches = len(branch_codes)
    if n_branches == 0:
        return {}, ["No branches found in CBS data"]

    # Compute FTE and revenue weights (used by all rules)
    fte_weights: Dict[str, Decimal] = {}
    revenue_weights: Dict[str, Decimal] = {}

    # FTE — prefer explicit lookup, fall back to accounts proxy
    fte_total = Decimal("0")
    for bc in branch_codes:
        explicit_fte = branch_fte_lookup.get(bc, 0)
        if explicit_fte > 0:
            fte_weights[bc] = Decimal(str(explicit_fte))
        else:
            # Proxy: account count as FTE proxy
            proxy = Decimal(str(branches[bc]["accounts_count"]))
            if proxy > 0:
                fte_weights[bc] = proxy
            else:
                fte_weights[bc] = Decimal("0")
        fte_total += fte_weights[bc]

    if fte_total == 0:
        # All branches have 0 FTE/accounts — degenerate; fall to equal
        for bc in branch_codes:
            fte_weights[bc] = Decimal("1")
        fte_total = Decimal(str(n_branches))

    # If we used accounts proxy (no explicit FTE), flag it
    if not branch_fte_lookup:
        notes.append(
            "FTE data unavailable — used 'accounts per branch' as proxy "
            "(degraded). Provide branch_fte_lookup or populate "
            "data/branch_fte.json for proper FTE-weighted allocation."
        )

    # Revenue (operating income) — use interest_income + fee_income as proxy
    revenue_total = Decimal("0")
    for bc in branch_codes:
        rev = (branches[bc]["interest_income"] +
               branches[bc]["fee_income"])
        revenue_weights[bc] = rev
        revenue_total += rev

    if revenue_total <= 0:
        # All branches have 0 revenue — fall to equal for revenue-driven rules
        for bc in branch_codes:
            revenue_weights[bc] = Decimal("1")
        revenue_total = Decimal(str(n_branches))
        if rule in (_RULE_REVENUE_WEIGHTED, _RULE_HYBRID):
            notes.append(
                "Revenue all zero (no synthesized accruals?) — falling back "
                "to equal split for revenue-weighted component"
            )

    # Apply the selected rule
    shares: Dict[str, Decimal] = {}
    if rule == _RULE_EQUAL:
        share = Decimal("1") / Decimal(str(n_branches))
        for bc in branch_codes:
            shares[bc] = share
    elif rule == _RULE_FTE_WEIGHTED:
        for bc in branch_codes:
            shares[bc] = fte_weights[bc] / fte_total
    elif rule == _RULE_REVENUE_WEIGHTED:
        for bc in branch_codes:
            shares[bc] = revenue_weights[bc] / revenue_total
    elif rule == _RULE_HYBRID:
        fw = rules_config.get("hybrid_fte_weight", Decimal("0.5"))
        rw = rules_config.get("hybrid_revenue_weight", Decimal("0.5"))
        for bc in branch_codes:
            shares[bc] = (
                (fte_weights[bc] / fte_total) * fw +
                (revenue_weights[bc] / revenue_total) * rw
            )
    else:
        notes.append(f"Unknown rule '{rule}', falling back to equal")
        share = Decimal("1") / Decimal(str(n_branches))
        for bc in branch_codes:
            shares[bc] = share

    return shares, notes


def compute_pbt_by_branch(
    cbs_dir: Path,
    allocation_rule: Optional[str] = None,
    branch_fte_lookup: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """v10.369 — Per-branch PBT computation. Second unification step.

    Returns dict keyed by branch_code with `PBTComponents` per branch.
    Sum of all per-branch PBTs equals bank PBT within KES 100 (G255 locks).

    Args:
        cbs_dir: directory with accounts.csv
        allocation_rule: 'fte_weighted' (default) | 'revenue_weighted' |
                         'equal' | 'hybrid'. If None, reads from
                         branch_allocation_rules.json.
        branch_fte_lookup: optional {branch_code: fte_count} override.
                           If None and rule=fte_weighted, falls back to
                           accounts-per-branch proxy then equal split.

    Returns: {branch_code: PBTComponents} dict.
    """
    # Lazy import to keep this module's import surface minimal
    from utils.pbt_computation import PBTComponents, _load_pbt_assumptions

    assumptions = _load_pbt_assumptions()
    rules_config = _load_allocation_rules()
    rule = allocation_rule or rules_config["default_rule"]
    if branch_fte_lookup is None:
        branch_fte_lookup = _load_branch_fte_lookup()

    branches = _aggregate_branches_from_csv(cbs_dir)
    bank_total_opex = _load_bank_total_opex()

    if not branches:
        return {}

    # Compute allocation shares
    shares, alloc_notes = _compute_allocation_shares(
        branches, rule, branch_fte_lookup, rules_config
    )

    # Build per-branch PBTComponents
    result: Dict[str, PBTComponents] = {}
    for bc, data in branches.items():
        c = PBTComponents(
            cost_of_funds_pct=assumptions["cost_of_funds_pct"],
            lgd_pct=assumptions["lgd_pct"],
            non_interest_other_pct=assumptions["non_interest_other_pct"],
        )
        # Income side
        c.interest_income = data["interest_income"]
        c.fee_income = data["fee_income"]
        c.interest_expense = (
            data["deposits"] * c.cost_of_funds_pct / 100
        ).quantize(Decimal("1"))
        c.nii = c.interest_income - c.interest_expense
        c.non_interest_other = (
            c.fee_income * c.non_interest_other_pct / 100
        ).quantize(Decimal("1"))
        c.non_interest_income = c.fee_income + c.non_interest_other
        c.operating_income = c.nii + c.non_interest_income
        # OpEx allocation
        c.total_opex = (
            bank_total_opex * shares.get(bc, Decimal("0"))
        ).quantize(Decimal("1"))
        c.other_opex = c.total_opex
        c.opex_source = f"branch_allocator[{rule}]"
        # Impairment
        c.npl_stage_3 = data["npl_outstanding"]
        c.impairment_charge = (
            c.npl_stage_3 * c.lgd_pct / 100
        ).quantize(Decimal("1"))
        # PBT
        c.pbt = c.operating_income - c.total_opex - c.impairment_charge
        c.notes = [f"Branch: {data['branch_name']}",
                   f"Accounts: {data['accounts_count']}",
                   f"FTE: {branch_fte_lookup.get(bc, 'proxy')}"] + alloc_notes
        result[bc] = c

    # Fix rounding drift: if Σ(shares) doesn't exactly equal 1 due to
    # Decimal rounding, the last branch absorbs the rounding remainder.
    if result:
        total_allocated = sum((c.total_opex for c in result.values()), Decimal("0"))
        drift = bank_total_opex - total_allocated
        if abs(drift) > 0:
            # Apply drift to the branch with largest OpEx (absorbs cleanly)
            largest_branch = max(result.keys(), key=lambda k: result[k].total_opex)
            result[largest_branch].total_opex += drift
            result[largest_branch].other_opex += drift
            # Recompute PBT for that branch
            c = result[largest_branch]
            c.pbt = c.operating_income - c.total_opex - c.impairment_charge

    return result


def sum_branch_pbts(branch_pbts: Dict[str, Any]) -> Any:
    """Sum all branch PBTComponents into a bank-total view.

    Used by G255 to verify Σ(Branch PBT) == Bank PBT.
    """
    from utils.pbt_computation import PBTComponents
    total = PBTComponents()
    for c in branch_pbts.values():
        total.interest_income += c.interest_income
        total.interest_expense += c.interest_expense
        total.fee_income += c.fee_income
        total.non_interest_other += c.non_interest_other
        total.total_opex += c.total_opex
        total.other_opex += c.other_opex
        total.npl_stage_3 += c.npl_stage_3
        total.impairment_charge += c.impairment_charge
    total.nii = total.interest_income - total.interest_expense
    total.non_interest_income = total.fee_income + total.non_interest_other
    total.operating_income = total.nii + total.non_interest_income
    total.pbt = total.operating_income - total.total_opex - total.impairment_charge
    total.opex_source = "Σ(Branch OpEx)"
    if branch_pbts:
        any_c = next(iter(branch_pbts.values()))
        total.cost_of_funds_pct = any_c.cost_of_funds_pct
        total.lgd_pct = any_c.lgd_pct
        total.non_interest_other_pct = any_c.non_interest_other_pct
    return total


def format_branch_breakdown(
    branch_pbts: Dict[str, Any], top_n: int = 10
) -> str:
    """Human-readable per-branch P&L (top N + summary)."""
    def fmt(v) -> str:
        try: return f"KES {float(v):>16,.0f}"
        except Exception: return str(v)

    lines = []
    lines.append("Per-Branch PBT Breakdown")
    lines.append("=" * 88)
    lines.append(f"{'Branch':<10} {'OpIncome':>20} {'OpEx':>20} {'PBT':>20}")
    lines.append("-" * 88)

    # Sort by absolute PBT (most extreme first), show top N
    sorted_branches = sorted(
        branch_pbts.items(),
        key=lambda x: abs(float(x[1].pbt)),
        reverse=True,
    )
    for bc, c in sorted_branches[:top_n]:
        lines.append(
            f"{bc:<10} {fmt(c.operating_income)} {fmt(-c.total_opex)} {fmt(c.pbt)}"
        )
    if len(sorted_branches) > top_n:
        lines.append(f"  ... and {len(sorted_branches) - top_n} more branches")

    lines.append("-" * 88)
    total = sum_branch_pbts(branch_pbts)
    lines.append(
        f"{'Σ TOTAL':<10} {fmt(total.operating_income)} {fmt(-total.total_opex)} {fmt(total.pbt)}"
    )
    lines.append(f"({len(branch_pbts)} branches)")
    return "\n".join(lines)


def self_test() -> None:
    """v10.369 self_test — hand-rolled CSV fixture (v10.364 lesson).

    Builds a minimal accounts.csv with 3 branches, runs the allocator,
    verifies the identity Σ(Branch OpEx) == bank_total_opex.
    """
    import tempfile
    tests_run = 0

    # Test 1: defaults load
    rules = _load_allocation_rules()
    assert "default_rule" in rules
    assert rules["default_rule"] in _ALL_RULES
    tests_run += 1

    # Test 2: empty cbs_dir → empty result
    with tempfile.TemporaryDirectory() as td:
        result = compute_pbt_by_branch(Path(td))
    assert result == {}
    tests_run += 1

    # Test 3: minimal hand-rolled CSV — 3 branches, equal accounts
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = []
    # Branch BR001: 2 accounts, total interest 1M
    rows.append("A001,C1,BR001,Br One,RM1,CASA,SAVINGS,1000000,2025-01-01,Active,500000,10000,0,0,,0\n")
    rows.append("A002,C2,BR001,Br One,RM1,Loan,LOAN,0,2025-01-01,Active,500000,5000,1000000,800000,,0\n")
    # Branch BR002: 1 account, smaller
    rows.append("A003,C3,BR002,Br Two,RM2,CASA,CURRENT,500000,2025-01-01,Active,200000,3000,0,0,,0\n")
    # Branch BR003: 1 NPL account
    rows.append("A004,C4,BR003,Br Three,RM3,Loan,LOAN,0,2025-01-01,Active,100000,1000,500000,400000,NPL,90\n")

    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "accounts.csv"
        csv_path.write_text(csv_header + "".join(rows))
        # Equal allocation — predictable shares
        result = compute_pbt_by_branch(
            Path(td), allocation_rule=_RULE_EQUAL
        )
    assert set(result.keys()) == {"BR001", "BR002", "BR003"}
    tests_run += 1

    # Test 4: equal allocation — each branch gets ~1/3 of bank OpEx
    bank_opex = _load_bank_total_opex()
    expected_per_branch = bank_opex / 3
    # Allow for the drift-absorption logic: largest branch absorbs rounding,
    # others should be very close to 1/3
    for bc, c in result.items():
        delta = abs(c.total_opex - expected_per_branch)
        assert delta < bank_opex * Decimal("0.01"), (
            f"{bc}: opex {c.total_opex} != 1/3 of {bank_opex}"
        )
    tests_run += 1

    # Test 5: sum identity holds
    total = sum_branch_pbts(result)
    assert total.total_opex == bank_opex, (
        f"Σ(Branch OpEx) {total.total_opex} != bank_total {bank_opex}"
    )
    tests_run += 1

    # Test 6: revenue_weighted gives larger OpEx to BR001 (most income)
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "accounts.csv"
        csv_path.write_text(csv_header + "".join(rows))
        result_rev = compute_pbt_by_branch(
            Path(td), allocation_rule=_RULE_REVENUE_WEIGHTED
        )
    # BR001 has 1M income, BR002 has 200k, BR003 has 100k → BR001 should
    # get most OpEx (about 1M / 1.3M = 77%)
    br001_share = result_rev["BR001"].total_opex / bank_opex
    assert br001_share > Decimal("0.5"), (
        f"BR001 should get >50% of opex by revenue, got {float(br001_share)*100:.1f}%"
    )
    tests_run += 1

    # Test 7: explicit FTE lookup overrides proxy
    fte_lookup = {"BR001": 1, "BR002": 10, "BR003": 1}
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "accounts.csv"
        csv_path.write_text(csv_header + "".join(rows))
        result_fte = compute_pbt_by_branch(
            Path(td),
            allocation_rule=_RULE_FTE_WEIGHTED,
            branch_fte_lookup=fte_lookup,
        )
    # BR002 has 10 FTE out of 12 → should get ~83% of opex
    br002_share = result_fte["BR002"].total_opex / bank_opex
    assert br002_share > Decimal("0.7"), (
        f"BR002 with 10/12 FTE should get >70% of opex, got {float(br002_share)*100:.1f}%"
    )
    tests_run += 1

    # Test 8: hybrid rule produces in-between values
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "accounts.csv"
        csv_path.write_text(csv_header + "".join(rows))
        result_hybrid = compute_pbt_by_branch(
            Path(td),
            allocation_rule=_RULE_HYBRID,
            branch_fte_lookup=fte_lookup,
        )
    # Sum still equals bank total
    total_hybrid = sum_branch_pbts(result_hybrid)
    assert total_hybrid.total_opex == bank_opex
    tests_run += 1

    # Test 9: format_branch_breakdown produces readable output
    s = format_branch_breakdown(result)
    assert "Per-Branch PBT Breakdown" in s
    assert "BR001" in s
    assert "Σ TOTAL" in s
    tests_run += 1

    print(f"✓ branch_pbt_allocator self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()

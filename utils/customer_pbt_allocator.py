"""utils/customer_pbt_allocator.py — v10.370 Per-Customer + Per-Staff PBT.

Third concrete unification step from the v10.367 architecture arc. Establishes
the **atomic profitability unit**: per-customer PBT. All other rollups (Bank,
SBU, Branch, Staff) become derivable from this single ground truth.

The reconciliation tree (now four-deep):

    Per-customer PBT (ATOMIC — this module)
       │
       ├─ Σ over all customers              = Bank PBT       (v10.364, G250)
       ├─ Σ over customers in SBU           = SBU PBT        (v10.368, G254)
       ├─ Σ over customers in branch        = Branch PBT     (v10.369, G255)
       └─ Σ over customers tagged to staff  = Staff PBT      (v10.370, G257)

Reconciliation identities (locked):
    Σ(customer PBT) == Bank PBT  within KES 100  (G256)
    Σ(staff PBT including Unassigned) == Bank PBT within KES 100  (G257)

Allocation rules (Rule N1, admin-configurable)
----------------------------------------------
Per-customer OpEx allocation by configurable driver:

    • revenue_weighted (default): customer's OpEx share = their revenue
      share. Standard activity-based costing.
    • balance_weighted: share = (deposits + loans) share. Reflects
      footprint / capital tied up.
    • equal: split evenly across customers with activity.
    • hybrid: 50% revenue + 50% balance, weights configurable.

Per-customer income (NII + Non-Interest Income) and impairment roll up
directly from accounts.csv — no allocation needed there, just aggregation
by CIF.

Drift-absorption: rounding remainder lands on the largest-revenue customer
so Σ(customer OpEx) == bank.total_opex EXACTLY.

Per-staff aggregation
---------------------
compute_pbt_by_staff() groups customers by their rm_code from customers.csv
and sums per-customer PBTComponents. Returns Dict[rm_code, PBTComponents].

IMPORTANT note on staff roles (Joshua, v10.370):
The `rm_code` field in customers.csv contains WHOEVER is tagged in CBS —
which in a real bank includes both:
  • Portfolio-owning roles (BRM, SRO, RO) who are sales / profit-responsible
  • Service roles (Tellers, CSOs, BOS) who transact but don't "own" the
    customer relationship

This function returns ALL tagged staff — it doesn't filter by role.
Filtering by profit-responsibility (e.g., "show only BRM/SRO/RO PBT") is a
UI/reporting concern handled downstream by joining staff_code → role from
data/users.json or hr.json. The data engine remains neutral.

This separation matters because:
  • For relationship management / sales attribution → filter to portfolio
    owners only (BRM/SRO/RO)
  • For service-cost attribution (tellers transact on accounts) → use the
    raw rm_code field, or move to cost_allocation_rules.json matrix mode
    once we have per-transaction staff tags

Module purity
-------------
Imports utils.pbt_computation (PBTComponents + assumption loaders) — a
legitimate downward dependency. Self-test uses hand-rolled CSV fixtures
per the v10.364 lesson. Zero upward consumer imports.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

_RULE_REVENUE_WEIGHTED = "revenue_weighted"
_RULE_BALANCE_WEIGHTED = "balance_weighted"
_RULE_EQUAL = "equal"
_RULE_HYBRID = "hybrid"
_ALL_RULES = (_RULE_REVENUE_WEIGHTED, _RULE_BALANCE_WEIGHTED,
              _RULE_EQUAL, _RULE_HYBRID)

UNASSIGNED_STAFF_BUCKET = "Unassigned"


def _load_allocation_rules() -> Dict[str, Any]:
    """Load data/customer_allocation_rules.json (Rule N1).

    Returns defaults if missing.
    """
    defaults = {
        "default_rule": _RULE_REVENUE_WEIGHTED,
        "hybrid_revenue_weight": Decimal("0.5"),
        "hybrid_balance_weight": Decimal("0.5"),
    }
    path = DATA_DIR / "customer_allocation_rules.json"
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "default_rule": data.get("default_rule", defaults["default_rule"]),
            "hybrid_revenue_weight": Decimal(str(
                data.get("hybrid_revenue_weight", defaults["hybrid_revenue_weight"]))),
            "hybrid_balance_weight": Decimal(str(
                data.get("hybrid_balance_weight", defaults["hybrid_balance_weight"]))),
        }
    except Exception:
        return defaults


def _load_bank_total_opex() -> Decimal:
    """Load bank.total_opex_kes_b → raw KES."""
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


def _aggregate_customers_from_csv(cbs_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Walk accounts.csv, group by CIF, accumulate raw figures.

    Returns dict keyed by CIF with:
      accounts_count, interest_income, fee_income,
      deposits, loan_outstanding, npl_outstanding
    """
    out: Dict[str, Dict[str, Any]] = {}
    acct_csv = cbs_dir / "accounts.csv"
    if not acct_csv.exists():
        return out
    with open(str(acct_csv), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cif = row.get("cif", "")
            if not cif:
                continue
            if cif not in out:
                out[cif] = {
                    "accounts_count":   0,
                    "interest_income":  Decimal("0"),
                    "fee_income":       Decimal("0"),
                    "deposits":         Decimal("0"),
                    "loan_outstanding": Decimal("0"),
                    "npl_outstanding":  Decimal("0"),
                }
            entry = out[cif]
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


def _load_customer_rm_lookup(cbs_dir: Path) -> Dict[str, str]:
    """Read customers.csv → {cif: rm_code}.

    Returns empty dict if customers.csv missing.
    """
    p = cbs_dir / "customers.csv"
    if not p.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        with open(str(p), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cif = row.get("cif", "")
                rm = row.get("rm_code", "")
                if cif:
                    out[cif] = rm
    except Exception:
        pass
    return out


def _compute_customer_allocation_shares(
    customers: Dict[str, Dict[str, Any]],
    rule: str,
    rules_config: Dict[str, Any],
) -> Tuple[Dict[str, Decimal], List[str]]:
    """Per-customer OpEx allocation shares. Sums to 1.0.

    Returns ({cif: share_fraction}, notes_about_fallbacks).
    """
    notes: List[str] = []
    cifs = list(customers.keys())
    n = len(cifs)
    if n == 0:
        return {}, ["No customers found in CBS data"]

    # Revenue weights
    revenue_weights: Dict[str, Decimal] = {}
    revenue_total = Decimal("0")
    for cif in cifs:
        rev = customers[cif]["interest_income"] + customers[cif]["fee_income"]
        revenue_weights[cif] = rev
        revenue_total += rev
    if revenue_total <= 0:
        for cif in cifs:
            revenue_weights[cif] = Decimal("1")
        revenue_total = Decimal(str(n))
        if rule in (_RULE_REVENUE_WEIGHTED, _RULE_HYBRID):
            notes.append(
                "Revenue all zero (no synthesized accruals?) — fell back to "
                "equal weighting for revenue-weighted component"
            )

    # Balance weights (deposits + loan_outstanding)
    balance_weights: Dict[str, Decimal] = {}
    balance_total = Decimal("0")
    for cif in cifs:
        bal = customers[cif]["deposits"] + customers[cif]["loan_outstanding"]
        balance_weights[cif] = bal
        balance_total += bal
    if balance_total <= 0:
        for cif in cifs:
            balance_weights[cif] = Decimal("1")
        balance_total = Decimal(str(n))
        if rule in (_RULE_BALANCE_WEIGHTED, _RULE_HYBRID):
            notes.append(
                "Balances all zero — fell back to equal weighting for "
                "balance-weighted component"
            )

    # Apply selected rule
    shares: Dict[str, Decimal] = {}
    if rule == _RULE_EQUAL:
        s = Decimal("1") / Decimal(str(n))
        for cif in cifs:
            shares[cif] = s
    elif rule == _RULE_REVENUE_WEIGHTED:
        for cif in cifs:
            shares[cif] = revenue_weights[cif] / revenue_total
    elif rule == _RULE_BALANCE_WEIGHTED:
        for cif in cifs:
            shares[cif] = balance_weights[cif] / balance_total
    elif rule == _RULE_HYBRID:
        rw = rules_config.get("hybrid_revenue_weight", Decimal("0.5"))
        bw = rules_config.get("hybrid_balance_weight", Decimal("0.5"))
        for cif in cifs:
            shares[cif] = (
                (revenue_weights[cif] / revenue_total) * rw +
                (balance_weights[cif] / balance_total) * bw
            )
    else:
        notes.append(f"Unknown rule '{rule}', fell back to equal")
        s = Decimal("1") / Decimal(str(n))
        for cif in cifs:
            shares[cif] = s

    return shares, notes


def compute_pbt_by_customer(
    cbs_dir: Path,
    allocation_rule: Optional[str] = None,
) -> Dict[str, Any]:
    """v10.370 — Per-customer PBT (the atomic unit).

    All other rollups (Bank, SBU, Branch, Staff) reconcile to Σ over this.

    Args:
        cbs_dir: directory with accounts.csv
        allocation_rule: 'revenue_weighted' (default) | 'balance_weighted' |
                         'equal' | 'hybrid'. If None, reads from
                         customer_allocation_rules.json.

    Returns: {cif: PBTComponents} dict.
    """
    from utils.pbt_computation import PBTComponents, _load_pbt_assumptions

    assumptions = _load_pbt_assumptions()
    rules_config = _load_allocation_rules()
    rule = allocation_rule or rules_config["default_rule"]

    customers = _aggregate_customers_from_csv(cbs_dir)
    bank_total_opex = _load_bank_total_opex()

    if not customers:
        return {}

    shares, alloc_notes = _compute_customer_allocation_shares(
        customers, rule, rules_config
    )

    result: Dict[str, Any] = {}
    for cif, data in customers.items():
        c = PBTComponents(
            cost_of_funds_pct=assumptions["cost_of_funds_pct"],
            lgd_pct=assumptions["lgd_pct"],
            non_interest_other_pct=assumptions["non_interest_other_pct"],
        )
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
        c.total_opex = (
            bank_total_opex * shares.get(cif, Decimal("0"))
        ).quantize(Decimal("1"))
        c.other_opex = c.total_opex
        c.opex_source = f"customer_allocator[{rule}]"
        c.npl_stage_3 = data["npl_outstanding"]
        c.impairment_charge = (
            c.npl_stage_3 * c.lgd_pct / 100
        ).quantize(Decimal("1"))
        c.pbt = c.operating_income - c.total_opex - c.impairment_charge
        c.notes = [f"Accounts: {data['accounts_count']}"] + alloc_notes
        result[cif] = c

    # Drift absorption: largest-revenue customer absorbs OpEx rounding
    if result:
        total_allocated = sum((c.total_opex for c in result.values()), Decimal("0"))
        drift = bank_total_opex - total_allocated
        if abs(drift) > 0:
            largest = max(result.keys(),
                          key=lambda k: result[k].operating_income)
            result[largest].total_opex += drift
            result[largest].other_opex += drift
            c = result[largest]
            c.pbt = c.operating_income - c.total_opex - c.impairment_charge

    return result


def sum_customer_pbts(customer_pbts: Dict[str, Any]) -> Any:
    """Sum all per-customer PBTComponents into bank-total view."""
    from utils.pbt_computation import PBTComponents
    total = PBTComponents()
    for c in customer_pbts.values():
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
    total.opex_source = "Σ(Customer OpEx)"
    if customer_pbts:
        any_c = next(iter(customer_pbts.values()))
        total.cost_of_funds_pct = any_c.cost_of_funds_pct
        total.lgd_pct = any_c.lgd_pct
        total.non_interest_other_pct = any_c.non_interest_other_pct
    return total


def compute_pbt_by_staff(
    cbs_dir: Path,
    allocation_rule: Optional[str] = None,
    customer_pbts: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """v10.370 — Per-staff PBT = Σ over customers in their portfolio.

    Groups per-customer PBTComponents by rm_code from customers.csv,
    sums them.

    Returns Dict[rm_code, PBTComponents]. An "Unassigned" bucket
    catches customers without a tagged staff (rm_code empty).

    IMPORTANT: rm_code from customers.csv contains WHOEVER is tagged in
    CBS — both portfolio owners (BRM/SRO/RO) and service staff
    (tellers, CSOs). This function returns ALL tagged staff without
    filtering by role. Role-based filtering is a UI concern (join with
    users.json::role downstream).
    """
    from utils.pbt_computation import PBTComponents

    if customer_pbts is None:
        customer_pbts = compute_pbt_by_customer(cbs_dir, allocation_rule)

    rm_lookup = _load_customer_rm_lookup(cbs_dir)

    # Group customers by their rm_code
    by_staff: Dict[str, List[str]] = {}
    for cif in customer_pbts.keys():
        rm = rm_lookup.get(cif, "") or UNASSIGNED_STAFF_BUCKET
        by_staff.setdefault(rm, []).append(cif)

    # Sum PBTComponents per staff
    result: Dict[str, Any] = {}
    for staff_code, cifs in by_staff.items():
        agg = PBTComponents()
        for cif in cifs:
            c = customer_pbts[cif]
            agg.interest_income += c.interest_income
            agg.interest_expense += c.interest_expense
            agg.fee_income += c.fee_income
            agg.non_interest_other += c.non_interest_other
            agg.total_opex += c.total_opex
            agg.other_opex += c.other_opex
            agg.npl_stage_3 += c.npl_stage_3
            agg.impairment_charge += c.impairment_charge
        agg.nii = agg.interest_income - agg.interest_expense
        agg.non_interest_income = agg.fee_income + agg.non_interest_other
        agg.operating_income = agg.nii + agg.non_interest_income
        agg.pbt = agg.operating_income - agg.total_opex - agg.impairment_charge
        agg.opex_source = f"staff_aggregator[from customer rollup]"
        if customer_pbts:
            any_c = next(iter(customer_pbts.values()))
            agg.cost_of_funds_pct = any_c.cost_of_funds_pct
            agg.lgd_pct = any_c.lgd_pct
            agg.non_interest_other_pct = any_c.non_interest_other_pct
        agg.notes = [
            f"Portfolio: {len(cifs)} customers",
            "Tagged in CBS — role-agnostic. Filter by portfolio-owning "
            "roles (BRM/SRO/RO) downstream for sales attribution.",
        ]
        result[staff_code] = agg
    return result


def sum_staff_pbts(staff_pbts: Dict[str, Any]) -> Any:
    """Sum all per-staff PBTComponents (including Unassigned) → bank total."""
    from utils.pbt_computation import PBTComponents
    total = PBTComponents()
    for c in staff_pbts.values():
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
    total.opex_source = "Σ(Staff OpEx)"
    if staff_pbts:
        any_c = next(iter(staff_pbts.values()))
        total.cost_of_funds_pct = any_c.cost_of_funds_pct
        total.lgd_pct = any_c.lgd_pct
        total.non_interest_other_pct = any_c.non_interest_other_pct
    return total


def format_top_customers(customer_pbts: Dict[str, Any], top_n: int = 10) -> str:
    """Top N most profitable + bottom N least profitable customers."""
    def fmt(v) -> str:
        try: return f"KES {float(v):>16,.0f}"
        except Exception: return str(v)
    lines = []
    lines.append("Top Customers by PBT")
    lines.append("=" * 88)
    lines.append(f"{'CIF':<14} {'OpIncome':>18} {'OpEx':>18} {'PBT':>18}")
    lines.append("-" * 88)
    sorted_c = sorted(customer_pbts.items(),
                      key=lambda x: float(x[1].pbt), reverse=True)
    for cif, c in sorted_c[:top_n]:
        lines.append(f"{cif:<14} {fmt(c.operating_income)} {fmt(-c.total_opex)} {fmt(c.pbt)}")
    if len(sorted_c) > top_n * 2:
        lines.append(f"  ... and {len(sorted_c) - top_n*2} mid-range customers ...")
        lines.append("Bottom customers by PBT:")
        for cif, c in sorted_c[-top_n:]:
            lines.append(f"{cif:<14} {fmt(c.operating_income)} {fmt(-c.total_opex)} {fmt(c.pbt)}")
    lines.append("-" * 88)
    total = sum_customer_pbts(customer_pbts)
    lines.append(f"{'Σ ALL':<14} {fmt(total.operating_income)} {fmt(-total.total_opex)} {fmt(total.pbt)}")
    lines.append(f"({len(customer_pbts)} customers)")
    return "\n".join(lines)


def format_staff_breakdown(staff_pbts: Dict[str, Any], top_n: int = 10) -> str:
    """Top N staff by PBT contribution."""
    def fmt(v) -> str:
        try: return f"KES {float(v):>16,.0f}"
        except Exception: return str(v)
    lines = []
    lines.append("Top Staff by PBT Contribution")
    lines.append("=" * 88)
    lines.append(f"{'Staff Code':<14} {'OpIncome':>18} {'OpEx':>18} {'PBT':>18}")
    lines.append("-" * 88)
    sorted_s = sorted(staff_pbts.items(),
                      key=lambda x: float(x[1].pbt), reverse=True)
    for staff, c in sorted_s[:top_n]:
        lines.append(f"{staff:<14} {fmt(c.operating_income)} {fmt(-c.total_opex)} {fmt(c.pbt)}")
    if len(sorted_s) > top_n:
        lines.append(f"  ... and {len(sorted_s) - top_n} more staff")
    lines.append("-" * 88)
    total = sum_staff_pbts(staff_pbts)
    lines.append(f"{'Σ TOTAL':<14} {fmt(total.operating_income)} {fmt(-total.total_opex)} {fmt(total.pbt)}")
    lines.append(f"({len(staff_pbts)} staff)")
    return "\n".join(lines)


def self_test() -> None:
    """v10.370 self_test — hand-rolled CSV fixtures (v10.364 lesson)."""
    import tempfile
    tests_run = 0

    rules = _load_allocation_rules()
    assert "default_rule" in rules
    assert rules["default_rule"] in _ALL_RULES
    tests_run += 1

    # Empty cbs_dir → empty result
    with tempfile.TemporaryDirectory() as td:
        result = compute_pbt_by_customer(Path(td))
    assert result == {}
    tests_run += 1

    # Hand-rolled minimal CSVs — 3 customers, varied revenue
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        "A1,CUST_A,BR001,Br One,STAFF1,CASA,SAVINGS,1000000,2025-01-01,Active,1000000,10000,0,0,,0\n",
        "A2,CUST_A,BR001,Br One,STAFF1,Loan,LOAN,0,2025-01-01,Active,200000,5000,500000,400000,,0\n",
        "A3,CUST_B,BR002,Br Two,STAFF2,CASA,SAVINGS,500000,2025-01-01,Active,300000,3000,0,0,,0\n",
        "A4,CUST_C,BR003,Br Three,STAFF1,Loan,LOAN,0,2025-01-01,Active,50000,1000,300000,250000,NPL,90\n",
    ]
    cust_header = "cif,full_name,segment,branch_code,rm_code\n"
    cust_rows = [
        "CUST_A,Alice,RETAIL,BR001,STAFF1\n",
        "CUST_B,Bob,SME,BR002,STAFF2\n",
        "CUST_C,Charlie,RETAIL,BR003,STAFF1\n",
    ]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        (td_path / "accounts.csv").write_text(csv_header + "".join(rows))
        (td_path / "customers.csv").write_text(cust_header + "".join(cust_rows))

        # Per-customer
        cust_pbts = compute_pbt_by_customer(td_path, allocation_rule=_RULE_EQUAL)
        assert set(cust_pbts.keys()) == {"CUST_A", "CUST_B", "CUST_C"}
        tests_run += 1

        # Per-customer identity holds
        total = sum_customer_pbts(cust_pbts)
        bank_opex = _load_bank_total_opex()
        assert total.total_opex == bank_opex
        tests_run += 1

        # Per-staff aggregation: STAFF1 has CUST_A + CUST_C, STAFF2 has CUST_B
        staff_pbts = compute_pbt_by_staff(td_path, allocation_rule=_RULE_EQUAL)
        assert "STAFF1" in staff_pbts
        assert "STAFF2" in staff_pbts
        tests_run += 1

        # Per-staff identity = bank total
        staff_total = sum_staff_pbts(staff_pbts)
        assert staff_total.total_opex == bank_opex
        tests_run += 1

        # Per-staff = Σ over customers in portfolio (verify STAFF1 = CUST_A + CUST_C)
        staff1 = staff_pbts["STAFF1"]
        expected_income = cust_pbts["CUST_A"].operating_income + cust_pbts["CUST_C"].operating_income
        assert staff1.operating_income == expected_income
        tests_run += 1

        # revenue_weighted: high-revenue customer (CUST_A with 1.2M income) gets more opex
        cust_pbts_rev = compute_pbt_by_customer(td_path, allocation_rule=_RULE_REVENUE_WEIGHTED)
        # CUST_A revenue = 1M + 200k = 1.2M; CUST_B = 303k; CUST_C = 51k
        # → CUST_A gets ~77% of OpEx
        a_share = cust_pbts_rev["CUST_A"].total_opex / bank_opex
        assert a_share > Decimal("0.6"), f"CUST_A revenue share {float(a_share):.2%} should dominate"
        tests_run += 1

        # balance_weighted: high-balance customer gets more opex
        # CUST_A balance = 1M deposits + 400k loan_outstanding = 1.4M
        # CUST_B = 500k; CUST_C = 250k → CUST_A dominates
        cust_pbts_bal = compute_pbt_by_customer(td_path, allocation_rule=_RULE_BALANCE_WEIGHTED)
        a_share_bal = cust_pbts_bal["CUST_A"].total_opex / bank_opex
        assert a_share_bal > Decimal("0.5"), f"CUST_A balance share {float(a_share_bal):.2%} should dominate"
        tests_run += 1

        # hybrid
        cust_pbts_hybrid = compute_pbt_by_customer(td_path, allocation_rule=_RULE_HYBRID)
        total_hybrid = sum_customer_pbts(cust_pbts_hybrid)
        assert total_hybrid.total_opex == bank_opex
        tests_run += 1

        # format functions don't crash
        s1 = format_top_customers(cust_pbts, top_n=2)
        assert "Top Customers" in s1 and "CUST_A" in s1
        s2 = format_staff_breakdown(staff_pbts, top_n=2)
        assert "Top Staff" in s2 and "STAFF1" in s2
        tests_run += 1

    print(f"✓ customer_pbt_allocator self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()

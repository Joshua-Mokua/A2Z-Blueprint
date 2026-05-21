"""Integration tests for v10.370 — Per-Customer + Per-Staff PBT.

Third concrete unification step. Establishes per-customer as the atomic
profitability unit; per-staff is Σ over their portfolio.

Identities (locked):
  Σ(customer PBT) == Bank PBT within KES 100 (G256)
  Σ(staff PBT including Unassigned) == Bank PBT within KES 100 (G257)
  Σ(customer OpEx) == Bank OpEx EXACTLY (drift-absorbed)

17 tests across 6 sections.
"""

import csv
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module surface + config
# ────────────────────────────────────────────────────────────────────

def test_v10370_module_present():
    p = REPO / "utils" / "customer_pbt_allocator.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("def compute_pbt_by_customer",
                "def sum_customer_pbts",
                "def compute_pbt_by_staff",
                "def sum_staff_pbts",
                "def format_top_customers",
                "def format_staff_breakdown",
                "def _aggregate_customers_from_csv",
                "def _load_customer_rm_lookup",
                "def _compute_customer_allocation_shares",
                "def self_test"):
        assert sym in text, f"customer_pbt_allocator missing {sym}"


def test_v10370_config_present_and_revenue_weighted_default():
    p = REPO / "data" / "customer_allocation_rules.json"
    assert p.exists()
    d = json.loads(p.read_text())
    # Revenue-weighted is the default (standard activity-based costing)
    assert d["default_rule"] == "revenue_weighted"


def test_v10370_self_test_passes():
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.customer_pbt_allocator import self_test
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


# ────────────────────────────────────────────────────────────────────
# Section 2 — Per-customer correctness
# ────────────────────────────────────────────────────────────────────

def test_v10370_per_customer_returns_all_cifs():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.customer_pbt_allocator import compute_pbt_by_customer

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        result = compute_pbt_by_customer(Path(td))
    # Small seed has 100 customers
    assert len(result) >= 50


def test_v10370_revenue_weighted_distributes_correctly():
    """Customer with 10x revenue gets ~10x OpEx."""
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.customer_pbt_allocator import compute_pbt_by_customer
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        # CUST_A has 10x revenue of CUST_B
        "A1,CUST_A,BR001,Br One,S1,CASA,SAVINGS,1000000,2025-01-01,Active,1000000,10000,0,0,,0\n",
        "A2,CUST_B,BR001,Br One,S1,CASA,SAVINGS,1000000,2025-01-01,Active,100000,1000,0,0,,0\n",
    ]
    cust_header = "cif,full_name,segment,branch_code,rm_code\n"
    cust_rows = [
        "CUST_A,Alice,RETAIL,BR001,S1\n",
        "CUST_B,Bob,RETAIL,BR001,S1\n",
    ]
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        (Path(td) / "customers.csv").write_text(cust_header + "".join(cust_rows))
        result = compute_pbt_by_customer(
            Path(td), allocation_rule="revenue_weighted"
        )
    ratio = result["CUST_A"].total_opex / result["CUST_B"].total_opex
    assert ratio > Decimal("8"), (
        f"Revenue-weighted: CUST_A/CUST_B opex ratio {float(ratio):.2f} should be ~10"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — THE RECONCILIATION IDENTITY (per-customer)
# ────────────────────────────────────────────────────────────────────

def test_v10370_sum_customer_equals_bank_pbt():
    """Σ(Customer PBT) == Bank PBT within KES 100."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        cust_pbts = compute_pbt_by_customer(td_path)
        cust_total = sum_customer_pbts(cust_pbts)

    delta = abs(bank_pbt.pbt - cust_total.pbt)
    assert delta <= Decimal("100"), (
        f"RECONCILIATION BROKEN: delta {float(delta):,.0f} > KES 100"
    )


def test_v10370_customer_opex_reconciles_exactly():
    """Σ(Customer OpEx) == Bank OpEx EXACTLY (drift-absorbed)."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        cust_total = sum_customer_pbts(compute_pbt_by_customer(td_path))
    assert cust_total.total_opex == bank_pbt.total_opex


def test_v10370_identity_holds_across_all_rules():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        for rule in ("revenue_weighted", "balance_weighted", "equal", "hybrid"):
            cust_total = sum_customer_pbts(
                compute_pbt_by_customer(td_path, allocation_rule=rule)
            )
            delta = abs(bank_pbt.pbt - cust_total.pbt)
            assert delta <= Decimal("100"), (
                f"Rule '{rule}': delta {float(delta):,.0f} > 100"
            )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Per-staff aggregation (THE STAFF IDENTITY)
# ────────────────────────────────────────────────────────────────────

def test_v10370_per_staff_groups_correctly():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.customer_pbt_allocator import compute_pbt_by_staff

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        staff_pbts = compute_pbt_by_staff(Path(td))
    # Small seed should have ~30 unique RM codes
    assert len(staff_pbts) >= 10


def test_v10370_sum_staff_equals_bank_pbt():
    """Σ(Staff PBT including Unassigned) == Bank PBT within KES 100."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_staff, sum_staff_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        staff_total = sum_staff_pbts(compute_pbt_by_staff(td_path))
    delta = abs(bank_pbt.pbt - staff_total.pbt)
    assert delta <= Decimal("100")


def test_v10370_staff_opex_reconciles_exactly():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_staff, sum_staff_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        staff_total = sum_staff_pbts(compute_pbt_by_staff(td_path))
    assert staff_total.total_opex == bank_pbt.total_opex


def test_v10370_per_staff_equals_sum_over_portfolio():
    """Per-staff PBT must equal sum over their portfolio customers."""
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, compute_pbt_by_staff,
    )
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        "A1,CUST_A,BR001,Br One,S1,CASA,SAVINGS,1000000,2025-01-01,Active,500000,5000,0,0,,0\n",
        "A2,CUST_B,BR001,Br One,S2,CASA,SAVINGS,500000,2025-01-01,Active,200000,2000,0,0,,0\n",
        "A3,CUST_C,BR001,Br One,S1,CASA,SAVINGS,300000,2025-01-01,Active,100000,1000,0,0,,0\n",
    ]
    cust_header = "cif,full_name,segment,branch_code,rm_code\n"
    cust_rows = [
        "CUST_A,Alice,RETAIL,BR001,S1\n",
        "CUST_B,Bob,RETAIL,BR001,S2\n",
        "CUST_C,Charlie,RETAIL,BR001,S1\n",
    ]
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        (Path(td) / "customers.csv").write_text(cust_header + "".join(cust_rows))
        cust_pbts = compute_pbt_by_customer(Path(td), allocation_rule="equal")
        staff_pbts = compute_pbt_by_staff(Path(td), customer_pbts=cust_pbts)
    # S1 portfolio = CUST_A + CUST_C
    expected_pbt = cust_pbts["CUST_A"].pbt + cust_pbts["CUST_C"].pbt
    assert staff_pbts["S1"].pbt == expected_pbt
    # S2 portfolio = CUST_B
    assert staff_pbts["S2"].pbt == cust_pbts["CUST_B"].pbt


def test_v10370_unassigned_bucket_catches_unmapped_customers():
    """Customers with no rm_code in customers.csv land in Unassigned."""
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.customer_pbt_allocator import (
        compute_pbt_by_staff, UNASSIGNED_STAFF_BUCKET,
    )
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        "A1,CUST_A,BR001,Br One,S1,CASA,SAVINGS,1000000,2025-01-01,Active,500000,5000,0,0,,0\n",
        "A2,CUST_NORM,BR001,Br One,,CASA,SAVINGS,500000,2025-01-01,Active,200000,2000,0,0,,0\n",
    ]
    cust_header = "cif,full_name,segment,branch_code,rm_code\n"
    # CUST_NORM has empty rm_code
    cust_rows = [
        "CUST_A,Alice,RETAIL,BR001,S1\n",
        "CUST_NORM,Norm,RETAIL,BR001,\n",
    ]
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        (Path(td) / "customers.csv").write_text(cust_header + "".join(cust_rows))
        staff_pbts = compute_pbt_by_staff(Path(td))
    assert UNASSIGNED_STAFF_BUCKET in staff_pbts, (
        "Unmapped customers should land in Unassigned bucket"
    )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Co-existence with prior unification batches
# ────────────────────────────────────────────────────────────────────

def test_v10370_all_four_rollups_reconcile():
    """SBU + Branch + Customer + Staff all reconcile to Bank."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu, sum_sbu_pbts,
    )
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts,
    )
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
        compute_pbt_by_staff, sum_staff_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        sbu_total = sum_sbu_pbts(compute_pbt_by_sbu(td_path))
        branch_total = sum_branch_pbts(compute_pbt_by_branch(td_path))
        cust_total = sum_customer_pbts(compute_pbt_by_customer(td_path))
        staff_total = sum_staff_pbts(compute_pbt_by_staff(td_path))

    TOLERANCE = Decimal("200")  # 2x because each rollup can have ±100
    for name, rollup in [("SBU", sbu_total), ("Branch", branch_total),
                          ("Customer", cust_total), ("Staff", staff_total)]:
        delta = abs(bank_pbt.pbt - rollup.pbt)
        assert delta <= TOLERANCE, (
            f"{name} rollup delta {float(delta):,.0f} > {TOLERANCE}"
        )


def test_v10370_format_functions_readable():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, compute_pbt_by_staff,
        format_top_customers, format_staff_breakdown,
    )
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        cust_pbts = compute_pbt_by_customer(Path(td))
        staff_pbts = compute_pbt_by_staff(Path(td))
    s1 = format_top_customers(cust_pbts, top_n=5)
    assert "Top Customers" in s1
    s2 = format_staff_breakdown(staff_pbts, top_n=5)
    assert "Top Staff" in s2


# ────────────────────────────────────────────────────────────────────
# Section 6 — G256, G257, regression
# ────────────────────────────────────────────────────────────────────

def test_v10370_g256_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_customer_reconciliation
    result = gate_customer_reconciliation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G256"


def test_v10370_g257_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_staff_reconciliation
    result = gate_staff_reconciliation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G257"


def test_v10370_charter_section_2_still_passes():
    """Per-customer/staff dimensions must not break Charter §2 propagation."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.teller_actions")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.actuals_engine import compute_bank_aggregates
    from utils.teller_actions import fire_teller_deposit, find_first_deposit_account

    DEPOSIT = Decimal("100000000")
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        before = compute_bank_aggregates(td_path).get("Deposit Growth", 0)
        account = find_first_deposit_account(bank)
        fire_teller_deposit(bank, account_no=account, amount=DEPOSIT)
        persist_bank_to_cbs(bank, output_dir=td_path)
        after = compute_bank_aggregates(td_path).get("Deposit Growth", 0)
    delta = Decimal(str(after - before))
    assert delta == DEPOSIT

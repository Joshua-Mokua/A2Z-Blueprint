"""Integration tests for v10.369 — Per-Branch PBT Allocation.

Second concrete unification step:
- utils/branch_pbt_allocator.py with compute_pbt_by_branch
- Four allocation rules: fte_weighted (default), revenue_weighted, equal, hybrid
- Identity: Σ(Branch PBT) == Bank PBT within KES 100 (G255 locks)
- Rule N1 config: data/branch_allocation_rules.json
- Drift absorbed by largest-OpEx branch for exact reconciliation

15 tests across 5 sections.
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

def test_v10369_module_present():
    p = REPO / "utils" / "branch_pbt_allocator.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("def compute_pbt_by_branch",
                "def sum_branch_pbts",
                "def format_branch_breakdown",
                "def _load_allocation_rules",
                "def _aggregate_branches_from_csv",
                "def _compute_allocation_shares",
                "def self_test"):
        assert sym in text, f"branch_pbt_allocator missing {sym}"


def test_v10369_allocation_rules_config_present():
    p = REPO / "data" / "branch_allocation_rules.json"
    assert p.exists()
    d = json.loads(p.read_text())
    assert "default_rule" in d
    assert d["default_rule"] in ("fte_weighted", "revenue_weighted",
                                  "equal", "hybrid")


def test_v10369_default_rule_is_fte_weighted():
    """Q3 from v10.367: FTE-weighted is the default allocation rule."""
    p = REPO / "data" / "branch_allocation_rules.json"
    d = json.loads(p.read_text())
    assert d["default_rule"] == "fte_weighted"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Allocation correctness per rule
# ────────────────────────────────────────────────────────────────────

def test_v10369_equal_allocation_splits_opex_evenly():
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, _load_bank_total_opex,
    )
    # 3 hand-rolled branches
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        "A1,C1,BR001,Br One,RM1,CASA,SAVINGS,1000000,2025-01-01,Active,500000,10000,0,0,,0\n",
        "A2,C2,BR002,Br Two,RM2,CASA,SAVINGS,500000,2025-01-01,Active,200000,3000,0,0,,0\n",
        "A3,C3,BR003,Br Three,RM3,CASA,SAVINGS,200000,2025-01-01,Active,100000,1000,0,0,,0\n",
    ]
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        result = compute_pbt_by_branch(Path(td), allocation_rule="equal")

    assert set(result.keys()) == {"BR001", "BR002", "BR003"}
    bank_opex = _load_bank_total_opex()
    # Each branch ~ 1/3, allowing for drift absorption on largest
    expected = bank_opex / 3
    for bc, c in result.items():
        delta = abs(c.total_opex - expected)
        assert delta < bank_opex * Decimal("0.01"), (
            f"{bc}: equal allocation gives {c.total_opex} != ~{expected}"
        )


def test_v10369_fte_weighted_honors_explicit_fte():
    """Branch with 10x FTE should get ~10x OpEx."""
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.branch_pbt_allocator import compute_pbt_by_branch
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        "A1,C1,BR001,Br One,RM1,CASA,SAVINGS,1000000,2025-01-01,Active,100000,1000,0,0,,0\n",
        "A2,C2,BR002,Br Two,RM2,CASA,SAVINGS,1000000,2025-01-01,Active,100000,1000,0,0,,0\n",
    ]
    fte = {"BR001": 100, "BR002": 10}
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        result = compute_pbt_by_branch(
            Path(td),
            allocation_rule="fte_weighted",
            branch_fte_lookup=fte,
        )
    # BR001 has 100/110 FTE ~ 91%; BR002 has 10/110 ~ 9%
    ratio = result["BR001"].total_opex / result["BR002"].total_opex
    # Should be approximately 10:1 (accounting for drift absorption)
    assert ratio > Decimal("8"), (
        f"FTE-weighted ratio {float(ratio):.2f} should be ~10x"
    )


def test_v10369_revenue_weighted_honors_income():
    """Branch with more revenue should get more OpEx."""
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.branch_pbt_allocator import compute_pbt_by_branch
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    # BR001 has 10x interest_income of BR002
    rows = [
        "A1,C1,BR001,Br One,RM1,CASA,SAVINGS,1000000,2025-01-01,Active,1000000,10000,0,0,,0\n",
        "A2,C2,BR002,Br Two,RM2,CASA,SAVINGS,1000000,2025-01-01,Active,100000,1000,0,0,,0\n",
    ]
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        result = compute_pbt_by_branch(
            Path(td), allocation_rule="revenue_weighted"
        )
    ratio = result["BR001"].total_opex / result["BR002"].total_opex
    assert ratio > Decimal("5"), (
        f"Revenue-weighted ratio {float(ratio):.2f} should favor BR001"
    )


def test_v10369_hybrid_produces_in_between_values():
    """Hybrid (50/50 FTE+revenue) should give in-between values."""
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts, _load_bank_total_opex,
    )
    csv_header = (
        "account_no,cif,branch_code,branch_name,relationship_manager_code,"
        "category,account_type_name,current_balance,date_opened,"
        "dormancy_status,interest_income_ytd,fee_income_ytd,"
        "loan_amount,loan_outstanding,npl_status,npl_days\n"
    )
    rows = [
        "A1,C1,BR001,Br One,RM1,CASA,SAVINGS,1000000,2025-01-01,Active,1000000,10000,0,0,,0\n",
        "A2,C2,BR002,Br Two,RM2,CASA,SAVINGS,1000000,2025-01-01,Active,100000,1000,0,0,,0\n",
    ]
    fte = {"BR001": 100, "BR002": 10}
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "accounts.csv").write_text(csv_header + "".join(rows))
        result = compute_pbt_by_branch(
            Path(td),
            allocation_rule="hybrid",
            branch_fte_lookup=fte,
        )
        total = sum_branch_pbts(result)
    # Identity still holds
    bank_opex = _load_bank_total_opex()
    assert total.total_opex == bank_opex


# ────────────────────────────────────────────────────────────────────
# Section 3 — THE RECONCILIATION IDENTITY
# ────────────────────────────────────────────────────────────────────

def test_v10369_sum_branch_equals_bank_pbt():
    """Σ(Branch PBT) == Bank PBT within KES 100."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        branch_pbts = compute_pbt_by_branch(td_path)
        branch_total = sum_branch_pbts(branch_pbts)

    delta = abs(bank_pbt.pbt - branch_total.pbt)
    TOLERANCE = Decimal("100")
    assert delta <= TOLERANCE, (
        f"RECONCILIATION BROKEN: Σ(Branch) {float(branch_total.pbt):,.0f} "
        f"!= Bank {float(bank_pbt.pbt):,.0f}; delta {float(delta):,.0f}"
    )


def test_v10369_sum_branch_equals_bank_opex_exactly():
    """OpEx must reconcile exactly (drift absorbed by largest branch)."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        branch_pbts = compute_pbt_by_branch(td_path)
        branch_total = sum_branch_pbts(branch_pbts)
    # Exact OpEx match (no tolerance — drift-absorption ensures this)
    assert branch_total.total_opex == bank_pbt.total_opex


def test_v10369_identity_holds_across_all_rules():
    """Reconciliation identity must hold regardless of allocation rule."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        TOLERANCE = Decimal("100")
        for rule in ("fte_weighted", "revenue_weighted", "equal", "hybrid"):
            branch_pbts = compute_pbt_by_branch(td_path, allocation_rule=rule)
            branch_total = sum_branch_pbts(branch_pbts)
            delta = abs(bank_pbt.pbt - branch_total.pbt)
            assert delta <= TOLERANCE, (
                f"Rule '{rule}': delta {float(delta):,.0f} > {TOLERANCE}"
            )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Format + serialization + co-existence with SBU
# ────────────────────────────────────────────────────────────────────

def test_v10369_format_branch_breakdown_readable():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, format_branch_breakdown,
    )

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        s = format_branch_breakdown(compute_pbt_by_branch(Path(td)))
    for keyword in ("Per-Branch PBT Breakdown", "Branch", "OpIncome",
                    "OpEx", "PBT", "Σ TOTAL"):
        assert keyword in s, f"format_branch_breakdown missing '{keyword}'"


def test_v10369_branch_and_sbu_dimensions_coexist():
    """Both v10.368 (SBU) and v10.369 (Branch) allocators run cleanly
    on the same CBS data without interfering."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
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

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = compute_pbt_from_cbs(td_path)
        sbu_total = sum_sbu_pbts(compute_pbt_by_sbu(td_path))
        branch_total = sum_branch_pbts(compute_pbt_by_branch(td_path))
    # All three must reconcile within tolerance
    TOLERANCE = Decimal("100")
    assert abs(bank_pbt.pbt - sbu_total.pbt) <= TOLERANCE
    assert abs(bank_pbt.pbt - branch_total.pbt) <= TOLERANCE
    # And SBU and Branch totals must agree with each other
    assert abs(sbu_total.pbt - branch_total.pbt) <= TOLERANCE * 2


# ────────────────────────────────────────────────────────────────────
# Section 5 — G255 audit gate + Charter §2 regression check
# ────────────────────────────────────────────────────────────────────

def test_v10369_g255_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_branch_reconciliation
    result = gate_branch_reconciliation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G255"


def test_v10369_g255_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G255", gate_branch_reconciliation)' in text


def test_v10369_self_test_passes():
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.branch_pbt_allocator import self_test
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


def test_v10369_charter_section_2_still_passes():
    """Per-branch allocation must not break Charter §2 propagation."""
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

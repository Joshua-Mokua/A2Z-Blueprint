"""Integration tests for v10.372 — Engine B refactor (CONVERGED).

Fifth and final concrete unification step from the v10.367 architecture arc.
Adds 'canonical' mode to utils.sbu_pnl_rollup.bank_total_pnl that consumes
from compute_pbt_by_customer (v10.370 atomic engine). Engine A and Engine
B converge within <1%. G253 ratchets from INFORMATIONAL to ENFORCING.

13 tests across 4 sections.
"""

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
# Section 1 — Module surface: canonical mode + helper
# ────────────────────────────────────────────────────────────────────

def test_v10372_canonical_mode_present_in_engine_b():
    """bank_total_pnl must accept cost_source='canonical' + cbs_dir param."""
    text = (REPO / "utils" / "sbu_pnl_rollup.py").read_text()
    assert 'cost_source == "canonical"' in text or "cost_source='canonical'" in text
    assert "_bank_total_pnl_canonical" in text
    assert "cbs_dir" in text


def test_v10372_canonical_mode_documented():
    """The canonical mode behavior should be explained in the docstring."""
    text = (REPO / "utils" / "sbu_pnl_rollup.py").read_text()
    assert "v10.372" in text
    assert "compute_pbt_by_customer" in text
    assert "operating_income" in text  # mapping documented
    assert "impairment_charge" in text


def test_v10372_canonical_mode_rejects_missing_cbs_dir():
    _reimport("utils.sbu_pnl_rollup")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.sbu_pnl_rollup import bank_total_pnl
    try:
        bank_total_pnl(cost_source="canonical")  # no cbs_dir → must raise
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "cbs_dir" in str(e)


def test_v10372_invalid_cost_source_still_rejected():
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import bank_total_pnl
    try:
        bank_total_pnl(cost_source="bogus")
        assert False, "should have raised"
    except ValueError as e:
        assert "canonical" in str(e)  # error msg now mentions all 3 modes


# ────────────────────────────────────────────────────────────────────
# Section 2 — Engine convergence (THE UNIFICATION IDENTITY)
# ────────────────────────────────────────────────────────────────────

def test_v10372_engines_converge_within_1pct():
    """Engine A (compute_pbt_from_cbs) vs Engine B canonical: ΔPBT < 1%."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.sbu_pnl_rollup")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.sbu_pnl_rollup import bank_total_pnl

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        engine_a_pbt = float(compute_pbt_from_cbs(td_path).pbt)
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)

    delta = abs(engine_a_pbt - engine_b["pbt"])
    denom = max(abs(engine_a_pbt), 1.0)
    pct = delta / denom * 100
    assert pct < 1.0, f"Engines diverged: ΔPBT KES {delta:,.0f} ({pct:.4f}%)"


def test_v10372_canonical_pbt_components_map_correctly():
    """Engine B bucket fields must come from PBTComponents correctly."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.sbu_pnl_rollup")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
    )
    from utils.sbu_pnl_rollup import bank_total_pnl

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        canonical = sum_customer_pbts(compute_pbt_by_customer(td_path))
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)

    # revenue ← operating_income
    assert engine_b["revenue"] == float(canonical.operating_income)
    # indirect_cost ← total_opex
    assert engine_b["indirect_cost"] == float(canonical.total_opex)
    # direct_cost ← impairment_charge
    assert engine_b["direct_cost"] == float(canonical.impairment_charge)


def test_v10372_canonical_customer_count_correct():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.sbu_pnl_rollup")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.customer_pbt_allocator import compute_pbt_by_customer
    from utils.sbu_pnl_rollup import bank_total_pnl

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        n_customers = len(compute_pbt_by_customer(td_path))
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)

    assert engine_b["customer_count"] == n_customers


# ────────────────────────────────────────────────────────────────────
# Section 3 — Backward compatibility (matrix/proxy still work)
# ────────────────────────────────────────────────────────────────────

def test_v10372_matrix_mode_still_works():
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import bank_total_pnl
    result = bank_total_pnl(cost_source="matrix")
    assert "pbt" in result
    assert "revenue" in result
    assert "customer_count" in result


def test_v10372_proxy_mode_still_works():
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import bank_total_pnl
    result = bank_total_pnl(cost_source="proxy")
    assert "pbt" in result
    assert result["customer_count"] > 0


def test_v10372_legacy_modes_diverge_from_canonical_as_expected():
    """matrix/proxy walk customer_intelligence.json — DIFFERENT data than CBS.
    They will diverge from canonical. This is expected and documented."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.sbu_pnl_rollup")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.sbu_pnl_rollup import bank_total_pnl

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        canonical = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)
        matrix = bank_total_pnl(cost_source="matrix")

    # Both produce numbers; they're allowed to differ (different data sources)
    assert canonical["pbt"] != 0
    assert matrix["pbt"] != 0
    # No assertion on the gap — legacy is by design walking different data


# ────────────────────────────────────────────────────────────────────
# Section 4 — G253 ratchet + co-existence with all prior identities
# ────────────────────────────────────────────────────────────────────

def test_v10372_g253_ratcheted_and_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_profitability_reconciliation
    result = gate_profitability_reconciliation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G253"
    # Summary should reflect the ratchet
    assert "ENFORCING" in result["summary"]
    assert "CONVERGED" in result["summary"] or "converge" in result["summary"].lower()


def test_v10372_all_five_unification_identities_hold():
    """All five identities from the unification arc must hold simultaneously."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    _reimport("utils.sbu_pnl_rollup")
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
    from utils.sbu_pnl_rollup import bank_total_pnl

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bank_pbt = float(compute_pbt_from_cbs(td_path).pbt)
        sbu = float(sum_sbu_pbts(compute_pbt_by_sbu(td_path)).pbt)
        branch = float(sum_branch_pbts(compute_pbt_by_branch(td_path)).pbt)
        cust = float(sum_customer_pbts(compute_pbt_by_customer(td_path)).pbt)
        staff = float(sum_staff_pbts(compute_pbt_by_staff(td_path)).pbt)
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)["pbt"]

    denom = max(abs(bank_pbt), 1.0)
    # Atomic-level identities: all within KES 100
    for name, val in [("SBU", sbu), ("Branch", branch),
                       ("Customer", cust), ("Staff", staff)]:
        assert abs(bank_pbt - val) <= 100, f"{name}: Δ {abs(bank_pbt-val):,.0f}"
    # Engine convergence: within 1%
    pct = abs(bank_pbt - engine_b) / denom * 100
    assert pct < 1.0, f"Engine B canonical: Δ {pct:.4f}% > 1%"


def test_v10372_charter_section_2_still_passes():
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
    assert Decimal(str(after - before)) == DEPOSIT

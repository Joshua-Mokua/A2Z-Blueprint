"""Integration tests for v10.373 — System State Review.

v10.373 is a strategic review batch — no engine changes. It ships
docs/SYSTEM_STATE_REVIEW_v10.373.md mapping the system and identifying
where unification + simulation work apply next. Tests verify the
document remains present and the prior unification arc still holds
(no engine regressions from this strategic batch).

8 tests across 3 sections.
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
# Section 1 — Document presence + key sections
# ────────────────────────────────────────────────────────────────────

def test_v10373_review_document_present():
    p = REPO / "docs" / "SYSTEM_STATE_REVIEW_v10.373.md"
    assert p.exists()
    assert p.stat().st_size > 5000, "Review document seems too small to be substantive"


def test_v10373_review_document_has_required_sections():
    p = REPO / "docs" / "SYSTEM_STATE_REVIEW_v10.373.md"
    text = p.read_text()
    for section in (
        "## Part 1 — System scale",
        "## Part 2 — The simulation gap",
        "## Part 3 — Parallel engines remaining",
        "## Part 4 — Other modules needing unification",
        "## Part 5 — Strategic roadmap",
        "## Part 6 — Recommended next concrete batch",
        "## Part 7 — Decisions awaiting Joshua",
        "## Part 8 — What this review is NOT proposing",
    ):
        assert section in text, f"missing section: {section}"


def test_v10373_review_identifies_simulation_gap():
    """The teller-only simulation gap must be documented for v10.374+ work."""
    p = REPO / "docs" / "SYSTEM_STATE_REVIEW_v10.373.md"
    text = p.read_text()
    assert "teller_actions.py" in text
    assert "live action interface" in text.lower() or "live actions" in text.lower()
    # Must list multiple roles that need actions
    for role in ("RM Retail", "Branch Manager", "Treasury", "Compliance", "MD"):
        assert role in text, f"role missing from coverage table: {role}"


def test_v10373_review_identifies_parallel_engines():
    """Parallel engines (customer_profitability, rm_profitability) must be flagged."""
    p = REPO / "docs" / "SYSTEM_STATE_REVIEW_v10.373.md"
    text = p.read_text()
    assert "customer_profitability.py" in text
    assert "rm_profitability.py" in text
    # The v10.370 atom must be referenced as the canonical
    assert "customer_pbt_allocator" in text


def test_v10373_review_proposes_phased_roadmap():
    """Phase A-E roadmap must be documented."""
    p = REPO / "docs" / "SYSTEM_STATE_REVIEW_v10.373.md"
    text = p.read_text()
    for phase in ("Phase A", "Phase B", "Phase C", "Phase D", "Phase E"):
        assert phase in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — G259 + no engine regression
# ────────────────────────────────────────────────────────────────────

def test_v10373_g259_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_system_state_review
    result = gate_system_state_review()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G259"


def test_v10373_all_prior_unification_identities_still_hold():
    """v10.373 changed no engine code. All prior identities must still hold."""
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

    for name, val in [("SBU", sbu), ("Branch", branch),
                       ("Customer", cust), ("Staff", staff)]:
        assert abs(bank_pbt - val) <= 100, f"{name}: Δ {abs(bank_pbt-val):,.0f}"
    pct = abs(bank_pbt - engine_b) / max(abs(bank_pbt), 1.0) * 100
    assert pct < 1.0, f"Engine convergence: Δ {pct:.4f}% > 1%"


def test_v10373_charter_section_2_still_passes():
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

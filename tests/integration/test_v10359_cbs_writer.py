"""Integration tests for v10.359 — Link 1 CBS Persistence Bridge.

Closes Link 1 of the Football Team Test chain. Bridge takes a populated
VirtualBankCore and writes:
- cbs_data/accounts.csv (per-account rows for actuals_engine)
- 5 aggregate JSONs (deposits, loans, npl, customer, dormant)

15 tests across 5 sections:
  Section 1 — Module + imports (2 tests)
  Section 2 — Persist mechanics (4 tests)
  Section 3 — Coherence (aggregates match CSV) (3 tests)
  Section 4 — actuals_engine integration (3 tests)
  Section 5 — Readiness audit + audit gate (3 tests)
"""

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
# Section 1 — Module
# ────────────────────────────────────────────────────────────────────

def test_v10359_module_present():
    path = REPO / "utils" / "virtual_bank_cbs_writer.py"
    assert path.exists()
    text = path.read_text()
    for sym in (
        "def persist_bank_to_cbs",
        "def format_persist_summary",
        "def self_test",
        "class PersistResult",
        "_atomic_write_text",
        "_atomic_write_json",
    ):
        assert sym in text, f"Missing: {sym}"


def test_v10359_self_test_passes():
    _reimport("utils.virtual_bank_cbs_writer")
    from utils.virtual_bank_cbs_writer import self_test
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


# ────────────────────────────────────────────────────────────────────
# Section 2 — Persist mechanics
# ────────────────────────────────────────────────────────────────────

def test_v10359_persist_writes_all_files(tmp_path):
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    result = persist_bank_to_cbs(bank, output_dir=tmp_path)
    for fname in (
        "accounts.csv",
        "deposits_aggregate.json",
        "loans_aggregate.json",
        "npl_aggregate.json",
        "customer_aggregate.json",
        "dormant_aggregate.json",
    ):
        assert (tmp_path / fname).exists(), f"Missing: {fname}"
    # accounts.csv should have ≥200 rows (accounts) plus loan-only rows
    assert result.accounts_csv_rows >= 200


def test_v10359_accounts_csv_has_right_columns(tmp_path):
    import csv
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)

    with open(tmp_path / "accounts.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        first_row = next(reader)
        required_cols = {
            "account_no", "cif", "branch_code", "branch_name",
            "relationship_manager_code", "category", "account_type_name",
            "current_balance", "date_opened", "dormancy_status",
            "interest_income_ytd", "fee_income_ytd",
            "loan_amount", "loan_outstanding", "npl_status", "npl_days",
        }
        missing = required_cols - set(first_row.keys())
        assert not missing, f"Missing CSV columns: {missing}"


def test_v10359_persist_idempotent(tmp_path):
    """Same bank state → same totals on repeated persist."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    r1 = persist_bank_to_cbs(bank, output_dir=tmp_path)
    r2 = persist_bank_to_cbs(bank, output_dir=tmp_path)
    assert r1.total_deposits_kes == r2.total_deposits_kes
    assert r1.total_loans_kes == r2.total_loans_kes
    assert r1.accounts_csv_rows == r2.accounts_csv_rows


def test_v10359_no_leftover_tmp_files(tmp_path):
    """Atomic-write contract: no .tmp files left after a write."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert not leftovers, f"Atomic-write leak: {leftovers}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Coherence (aggregates match CSV)
# ────────────────────────────────────────────────────────────────────

def test_v10359_deposits_aggregate_matches_csv(tmp_path):
    """The deposits_aggregate.json total_deposits_kes equals the sum of
    CASA + TERM account balances in accounts.csv."""
    import csv
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)

    # Walk the CSV
    total_from_csv = Decimal("0")
    with open(tmp_path / "accounts.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["category"] in ("CASA", "Term Deposit"):
                total_from_csv += Decimal(row["current_balance"])

    # Read the aggregate
    agg = json.loads((tmp_path / "deposits_aggregate.json").read_text())
    assert Decimal(agg["total_deposits_kes"]) == total_from_csv


def test_v10359_loans_aggregate_matches_csv(tmp_path):
    import csv
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)
    total_loans = Decimal("0")
    with open(tmp_path / "accounts.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total_loans += Decimal(row["loan_outstanding"])
    agg = json.loads((tmp_path / "loans_aggregate.json").read_text())
    assert Decimal(agg["gross_outstanding_kes"]) == total_loans


def test_v10359_customer_count_matches_seed(tmp_path):
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    bank, seed_result = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)
    agg = json.loads((tmp_path / "customer_aggregate.json").read_text())
    assert agg["total_customers"] == seed_result.n_customers


# ────────────────────────────────────────────────────────────────────
# Section 4 — actuals_engine integration
# ────────────────────────────────────────────────────────────────────

def test_v10359_actuals_engine_reads_back_rms(tmp_path):
    """actuals_engine.aggregate_cbs_by_rm sees the persisted bank."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.actuals_engine import aggregate_cbs_by_rm
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)
    rm_data = aggregate_cbs_by_rm(tmp_path)
    assert len(rm_data) > 0, "actuals_engine couldn't read persisted CBS"
    # Should see ~30 RMs (seeder uses 30) — possibly fewer if some have no
    # accounts under deterministic assignment
    assert len(rm_data) <= 30


def test_v10359_actuals_engine_reads_branches(tmp_path):
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig, ECOBANK_BRANCHES
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.actuals_engine import aggregate_cbs_by_branch
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)
    branch_data = aggregate_cbs_by_branch(tmp_path)
    # v10.360: branches now come from org_config (≤94). With 100 customers
    # distributed across all available branches, deterministic assignment
    # gives most branches at least one account.
    n_branches_total = len(ECOBANK_BRANCHES)
    # Some branches may end up with 0 accounts under deterministic
    # assignment — be tolerant to that
    assert 1 <= len(branch_data) <= n_branches_total, (
        f"Branches seen: {len(branch_data)} (total available: {n_branches_total})"
    )


def test_v10359_rm_aggregates_have_deposits(tmp_path):
    """At least one RM should have nonzero total_deposits."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.actuals_engine import aggregate_cbs_by_rm
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    persist_bank_to_cbs(bank, output_dir=tmp_path)
    rm_data = aggregate_cbs_by_rm(tmp_path)
    rms_with_deposits = [r for r in rm_data.values()
                          if r.get("total_deposits", 0) > 0]
    assert len(rms_with_deposits) > 0, "No RM has deposits — bridge broken"


# ────────────────────────────────────────────────────────────────────
# Section 5 — Readiness audit chain + G245 gate
# ────────────────────────────────────────────────────────────────────

def test_v10359_readiness_chain_link1_wired():
    """The readiness audit now reports Link 1 as WIRED."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_chain
    chain = _probe_chain()
    assert chain.teller_action_to_cbs == "WIRED", (
        f"Link 1 should be WIRED, got {chain.teller_action_to_cbs}"
    )


def test_v10359_g245_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_cbs_writer_integrity
    result = gate_cbs_writer_integrity()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G245"


def test_v10359_g245_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G245", gate_cbs_writer_integrity)' in text

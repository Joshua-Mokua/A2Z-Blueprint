"""Integration tests for v10.366 — CBS accruals synthesizer.

Closes the "0 income" stub gap: pre-v10.366 the bridge wrote
interest_income_ytd=0 and fee_income_ytd=0 for all accounts, leaving
v10.364 PBT computation showing NII=0 from synthetic data.

v10.366 adds utils/accruals_synthesizer.py that produces plausible
accruals from account properties (outstanding × rate × elapsed for
loans, monthly_fee × months for accounts) using configurable factors
in data/accruals_assumptions.json (Rule N1). Bridge calls it for every
row written.

13 tests across 4 sections.
"""

import json
import re
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

def test_v10366_synthesizer_module_present():
    p = REPO / "utils" / "accruals_synthesizer.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("def synthesize_interest_income_ytd",
                "def synthesize_fee_income_ytd",
                "def synthesize_row_accruals",
                "def _load_accrual_assumptions",
                "class AccrualAssumptions"):
        assert sym in text, f"accruals_synthesizer missing {sym}"


def test_v10366_synthesizer_has_no_upward_imports():
    """v10.364 lesson — utility modules must not import their consumers,
    even in self_test bodies."""
    import ast
    text = (REPO / "utils" / "accruals_synthesizer.py").read_text()
    tree = ast.parse(text)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("utils"):
                bad.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("utils"):
                    bad.append(alias.name)
    assert not bad, f"accruals_synthesizer has upward imports: {bad}"


def test_v10366_assumptions_json_present():
    p = REPO / "data" / "accruals_assumptions.json"
    assert p.exists()
    d = json.loads(p.read_text())
    for k in ("as_of_date", "default_loan_rate_pct",
              "monthly_account_fee_savings", "monthly_account_fee_current",
              "monthly_account_fee_loan", "min_account_age_days"):
        assert k in d, f"accruals_assumptions.json missing {k}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Synthesizer correctness (unit-level)
# ────────────────────────────────────────────────────────────────────

def test_v10366_loan_interest_accrues():
    _reimport("utils.accruals_synthesizer")
    from utils.accruals_synthesizer import synthesize_interest_income_ytd
    # 1M loan at 14% for 1 year → ~140k
    r = synthesize_interest_income_ytd(
        category="Loan",
        loan_outstanding=Decimal("1000000"),
        account_interest_rate_pct=Decimal("14"),
        open_date="2025-04-30",
    )
    assert Decimal("139000") < r < Decimal("141000"), \
        f"Expected ~140k, got {r}"


def test_v10366_deposit_returns_zero_interest():
    """CASA/Term Deposit accounts shouldn't accrue interest_income from
    the bank's POV — that's interest expense, handled separately in PBT."""
    _reimport("utils.accruals_synthesizer")
    from utils.accruals_synthesizer import synthesize_interest_income_ytd
    for cat in ("CASA", "Term Deposit"):
        r = synthesize_interest_income_ytd(
            category=cat,
            loan_outstanding=Decimal("0"),
            account_interest_rate_pct=Decimal("5"),
            open_date="2025-01-01",
        )
        assert r == Decimal("0"), f"{cat} should return 0, got {r}"


def test_v10366_fresh_loan_returns_zero():
    """Loans younger than min_account_age_days don't accrue."""
    _reimport("utils.accruals_synthesizer")
    from utils.accruals_synthesizer import (
        synthesize_interest_income_ytd, _load_accrual_assumptions
    )
    a = _load_accrual_assumptions()
    # Open date = as_of date → 0 days elapsed
    r = synthesize_interest_income_ytd(
        category="Loan",
        loan_outstanding=Decimal("1000000"),
        account_interest_rate_pct=Decimal("14"),
        open_date=a.as_of_date,
    )
    assert r == Decimal("0")


def test_v10366_fee_income_for_current_account():
    _reimport("utils.accruals_synthesizer")
    from utils.accruals_synthesizer import synthesize_fee_income_ytd
    # CURRENT account for 1 year → ~200 × 12 = 2400
    r = synthesize_fee_income_ytd(
        category="CASA",
        account_type_name="CURRENT",
        open_date="2025-04-30",
    )
    assert Decimal("2300") < r < Decimal("2500"), f"Expected ~2400, got {r}"


def test_v10366_determinism():
    """Same inputs → same outputs (G244 extends to accruals)."""
    _reimport("utils.accruals_synthesizer")
    from utils.accruals_synthesizer import synthesize_interest_income_ytd
    args = dict(
        category="Loan",
        loan_outstanding=Decimal("2500000"),
        account_interest_rate_pct=Decimal("11.5"),
        open_date="2025-08-15",
    )
    r1 = synthesize_interest_income_ytd(**args)
    r2 = synthesize_interest_income_ytd(**args)
    assert r1 == r2 and r1 > 0


# ────────────────────────────────────────────────────────────────────
# Section 3 — Bridge integration (end-to-end)
# ────────────────────────────────────────────────────────────────────

def test_v10366_bridge_writes_nonzero_accruals():
    """The bridge now writes non-zero interest_income_ytd and fee_income_ytd
    for aged accounts (was hardcoded "0" pre-v10.366)."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.accruals_synthesizer")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        import csv
        nonzero_interest = 0
        nonzero_fees = 0
        with open(td_path / "accounts.csv") as f:
            for row in csv.DictReader(f):
                if Decimal(row.get("interest_income_ytd") or "0") > 0:
                    nonzero_interest += 1
                if Decimal(row.get("fee_income_ytd") or "0") > 0:
                    nonzero_fees += 1
    assert nonzero_interest > 0, "No accounts have nonzero interest_income_ytd"
    assert nonzero_fees > 0, "No accounts have nonzero fee_income_ytd"


def test_v10366_pbt_now_includes_synthesized_income():
    """v10.364's compute_pbt_from_cbs now sees nonzero Interest Income and
    Fee Income — closes the 0-income gap acknowledged in v10.364."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.accruals_synthesizer")
    _reimport("utils.pbt_computation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        c = compute_pbt_from_cbs(Path(td))
    assert c.interest_income > 0, \
        f"Interest Income still 0 after v10.366 — synthesizer not wired"
    assert c.fee_income > 0, \
        f"Fee Income still 0 after v10.366"


def test_v10366_charter_section_2_still_passes():
    """The teller-deposit propagation test (G249) must still pass with
    synthesized accruals layered on. The deposit goes to current_balance,
    not interest_income_ytd, so the Deposit Growth delta should still
    equal the deposit amount exactly."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.accruals_synthesizer")
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
    assert delta == DEPOSIT, (
        f"Charter §2 broken: delta {delta} != fired {DEPOSIT}"
    )


def test_v10366_v10359_coherence_still_holds():
    """The v10.359 coherence check (deposits_aggregate matches CSV sum)
    must still pass with synthesized accruals — accruals don't affect
    the balance fields that the aggregate sums."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.accruals_synthesizer")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    import csv

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        result = persist_bank_to_cbs(bank, output_dir=td_path)
        csv_sum = Decimal("0")
        with open(td_path / "accounts.csv") as f:
            for row in csv.DictReader(f):
                if row["category"] in ("CASA", "Term Deposit"):
                    csv_sum += Decimal(row["current_balance"])
        agg = json.loads((td_path / "deposits_aggregate.json").read_text())
        assert Decimal(agg["total_deposits_kes"]) == csv_sum, (
            f"v10.359 coherence broken: agg={agg['total_deposits_kes']} != csv_sum={csv_sum}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — G252 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10366_g252_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_accruals_synthesizer
    result = gate_accruals_synthesizer()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G252"


def test_v10366_g252_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G252", gate_accruals_synthesizer)' in text

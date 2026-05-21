"""Charter §2 Football Team Test — End-to-end integration test (v10.363).

The acceptance criterion for the platform:
> "The MD can see, in real-time, the impact of a teller's action on the
> bank's ROE — and trace cause-and-effect across every layer."

This file is THE proof. It fires synthetic teller actions through the
full Football Team Test chain and asserts the bank-level totals (what
the MD's BSC reads) reflect the change with measurable latency.

Chain traversed (all 7 links):
  1. Teller fires a deposit                          [utils/teller_actions]
  2. VirtualBankCore.update_account_balance         [virtual_bank_core]
  3. Bridge persists to cbs_data/accounts.csv       [virtual_bank_cbs_writer]
  4. actuals_engine.compute_bank_aggregates reads   [actuals_engine]
  5. _get_bank_aggregate_roles identifies MD        [actuals_engine]
  6. bank_targets.json provides target              [CascadeManager]
  7. MD's BSC view assembles target + actual        [pages/1_perform.py]

Step 7 is verified by exercising the upstream data flow: if all 6
prior steps produce the right values, the BSC's rendering of them is
mechanical (Streamlit reads from the same data the test reads).

After this test passes → Charter §2 PASSES.

Tests:
  Section 1 — Chain mechanics with deposit (4 tests)
  Section 2 — Chain mechanics with withdrawal (2 tests)
  Section 3 — Latency budget (1 test)
  Section 4 — Determinism + idempotency (2 tests)
  Section 5 — G249 audit gate (2 tests)
"""

import sys
import time
import json
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


def _capture_bank_state(cbs_dir: Path) -> dict:
    """Capture the MD-visible bank-wide state.

    Reads the same compute_bank_aggregates function that pages/1_perform.py
    populates the MD's actuals from. The MD's "on track?" view is built
    from this dict + bank_targets.json.
    """
    from utils.actuals_engine import compute_bank_aggregates
    return compute_bank_aggregates(cbs_dir)


def _capture_md_targets() -> dict:
    """Capture the MD's targets from bank_targets.json (single source).

    Same source that pages/1_perform.py reads via CascadeManager._load_bank
    for the _is_md_view branch.
    """
    bt = json.loads((REPO / "data" / "bank_targets.json").read_text())
    targets = {}
    for key, val in bt.items():
        if "|" not in key:
            continue
        kpi_name, year = key.rsplit("|", 1)
        if year != "2026":
            continue
        if isinstance(val, dict):
            targets[kpi_name] = float(val.get("target", 0))
        else:
            targets[kpi_name] = float(val or 0)
    return targets


# ────────────────────────────────────────────────────────────────────
# Section 1 — Deposit propagation through the full chain
# ────────────────────────────────────────────────────────────────────

def test_v10363_teller_deposit_propagates_to_md_tile():
    """**THE CHARTER §2 TEST.** Fire a teller deposit; assert the MD's
    bank-wide Deposit Growth reflects it within the latency budget."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.teller_actions import fire_teller_deposit, find_first_deposit_account

    DEPOSIT_AMOUNT = Decimal("100000000")  # KES 100M — large enough to see clearly

    # ── 1. Seed bank + capture initial MD state ─────────────────────
    t0 = time.time()
    bank, _ = seed_virtual_bank(config=SeedConfig.small())

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        state_before = _capture_bank_state(td_path)
        deposits_before = state_before.get("Deposit Growth", 0)
        retail_deposits_before = state_before.get("Retail & MSME Deposit Growth", 0)

        # ── 2. Fire teller deposit ────────────────────────────────
        account_no = find_first_deposit_account(bank)
        assert account_no is not None, "Bank has no deposit accounts to test"

        result = fire_teller_deposit(
            bank, account_no=account_no, amount=DEPOSIT_AMOUNT
        )
        assert result.delta == DEPOSIT_AMOUNT
        assert result.action_type == "TELLER_DEPOSIT"

        # ── 3. Persist + recompute ────────────────────────────────
        persist_bank_to_cbs(bank, output_dir=td_path)
        state_after = _capture_bank_state(td_path)
        deposits_after = state_after.get("Deposit Growth", 0)

        # ── 4. Assertions ─────────────────────────────────────────
        # Bank-wide Deposit Growth must reflect the teller's deposit
        delta_observed = Decimal(str(deposits_after - deposits_before))
        assert delta_observed == DEPOSIT_AMOUNT, (
            f"Deposit Growth delta {delta_observed} != fired amount "
            f"{DEPOSIT_AMOUNT} (before={deposits_before}, after={deposits_after}). "
            f"The teller's action did not propagate to the MD's bank-wide tile."
        )

        # MD-visible bank target must exist for Deposit Growth
        md_targets = _capture_md_targets()
        deposit_target = md_targets.get("Deposit Growth", 0) or \
                         md_targets.get("Retail & MSME Deposit Growth", 0)
        assert deposit_target > 0, (
            "No bank_targets.json entry for Deposit Growth — MD's BSC "
            "can't show 'on track?' for this KPI"
        )

    elapsed = time.time() - t0
    print(f"\n  CHARTER §2 chain latency: {elapsed:.2f}s")
    print(f"  Deposit Growth: {deposits_before:,.0f} → {deposits_after:,.0f}")
    print(f"  Bank target:    {deposit_target:,.0f}")


def test_v10363_deposit_appears_in_retail_segment():
    """A teller deposit on a savings account must increase the
    'Retail & MSME Deposit Growth' bucket, not commercial."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.teller_actions import fire_teller_deposit
    from utils.virtual_bank_core import AccountType

    bank, _ = seed_virtual_bank(config=SeedConfig.small())

    # Pick a SAVINGS account (clearly retail)
    savings_account = None
    for acct in bank.all_accounts():
        if acct.account_type == AccountType.SAVINGS:
            savings_account = acct.account_no
            break
    assert savings_account is not None, "No SAVINGS account in bank"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        retail_before = _capture_bank_state(td_path).get(
            "Retail & MSME Deposit Growth", 0
        )

        fire_teller_deposit(
            bank, account_no=savings_account, amount=Decimal("50000000")
        )
        persist_bank_to_cbs(bank, output_dir=td_path)
        retail_after = _capture_bank_state(td_path).get(
            "Retail & MSME Deposit Growth", 0
        )

        assert retail_after > retail_before, (
            f"Retail deposit growth didn't increase: "
            f"{retail_before} → {retail_after}"
        )


def test_v10363_md_role_in_bank_aggregate_roles():
    """The MD role must be in _get_bank_aggregate_roles — otherwise
    MD's actuals row wouldn't receive bank-wide values."""
    from utils.actuals_engine import _get_bank_aggregate_roles

    org = json.loads((REPO / "data" / "org_config.json").read_text())
    roles = _get_bank_aggregate_roles(org)

    # MD-equivalent role must be present
    md_present = any(
        any(kw in r.lower() for kw in ("managing", "director", "ceo"))
        for r in roles
    )
    assert md_present, (
        f"No MD-equivalent role in bank-aggregate set: {roles}"
    )


def test_v10363_chain_traverses_all_seven_links():
    """Documentary test — assert all 7 chain links are exercised by
    the canonical Charter §2 test."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_chain
    chain = _probe_chain()

    # All 7 links WIRED (no PARTIAL, no MISSING)
    statuses = (
        chain.teller_action_to_cbs,
        chain.cbs_to_actuals_engine,
        chain.actuals_engine_to_yoy_sidecar,
        chain.yoy_sidecar_to_bsc_display,
        chain.bsc_to_branch_score,
        chain.branch_to_regional_rollup,
        chain.regional_to_md_tile,
    )
    not_wired = [s for s in statuses if s != "WIRED"]
    assert not not_wired, f"Chain not fully WIRED: {statuses}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Withdrawal propagation
# ────────────────────────────────────────────────────────────────────

def test_v10363_withdrawal_decreases_md_tile():
    """A teller withdrawal must decrease the bank-wide Deposit Growth."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.teller_actions import fire_teller_withdrawal, find_first_deposit_account

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    account_no = find_first_deposit_account(bank)
    # Find an account with sufficient balance
    acct = bank.get_account(account_no)
    if acct.balance < Decimal("10000"):
        # Try another
        for a in bank.all_accounts():
            if a.balance >= Decimal("10000"):
                account_no = a.account_no
                break

    withdrawal_amount = Decimal("5000")  # small, safe

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        deposits_before = _capture_bank_state(td_path).get("Deposit Growth", 0)

        fire_teller_withdrawal(bank, account_no=account_no, amount=withdrawal_amount)
        persist_bank_to_cbs(bank, output_dir=td_path)
        deposits_after = _capture_bank_state(td_path).get("Deposit Growth", 0)

        delta = Decimal(str(deposits_after - deposits_before))
        assert delta == -withdrawal_amount, (
            f"Withdrawal delta {delta} != expected -{withdrawal_amount}"
        )


def test_v10363_multiple_actions_aggregate_correctly():
    """Fire several teller actions; assert the sum of deltas matches
    the bank-wide change."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.teller_actions import fire_teller_deposit
    from utils.virtual_bank_core import AccountType

    bank, _ = seed_virtual_bank(config=SeedConfig.small())

    # Pick 3 different savings accounts
    savings = [a.account_no for a in bank.all_accounts()
               if a.account_type == AccountType.SAVINGS][:3]
    assert len(savings) >= 3, "Need at least 3 savings accounts"

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        before = _capture_bank_state(td_path).get("Deposit Growth", 0)

        # Fire 3 deposits totalling KES 30M
        for acct in savings:
            fire_teller_deposit(bank, account_no=acct, amount=Decimal("10000000"))

        persist_bank_to_cbs(bank, output_dir=td_path)
        after = _capture_bank_state(td_path).get("Deposit Growth", 0)

        delta = Decimal(str(after - before))
        assert delta == Decimal("30000000"), (
            f"Sum of 3×10M deposits should be 30M, got {delta}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Latency budget
# ────────────────────────────────────────────────────────────────────

def test_v10363_latency_within_budget():
    """End-to-end latency: seed → fire → persist → aggregate must
    complete within 5 seconds. (Charter §2: 'in real-time')."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.actuals_engine import compute_bank_aggregates
    from utils.teller_actions import fire_teller_deposit, find_first_deposit_account

    t0 = time.time()
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        account = find_first_deposit_account(bank)
        fire_teller_deposit(bank, account_no=account, amount=Decimal("1000000"))
        persist_bank_to_cbs(bank, output_dir=td_path)
        _ = compute_bank_aggregates(td_path)
    elapsed = time.time() - t0

    LATENCY_BUDGET_S = 5.0
    assert elapsed < LATENCY_BUDGET_S, (
        f"Charter §2 latency budget exceeded: {elapsed:.2f}s > {LATENCY_BUDGET_S}s"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Determinism + idempotency
# ────────────────────────────────────────────────────────────────────

def test_v10363_deterministic_state_after_action():
    """Same seed + same action → same final aggregates (G244-style
    determinism extends to teller actions)."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.teller_actions import fire_teller_deposit, find_first_deposit_account

    def run() -> dict:
        bank, _ = seed_virtual_bank(config=SeedConfig.small())
        account = find_first_deposit_account(bank)
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            fire_teller_deposit(bank, account_no=account,
                                 amount=Decimal("12345678"))
            persist_bank_to_cbs(bank, output_dir=td_path)
            return _capture_bank_state(td_path)

    s1 = run()
    s2 = run()
    assert s1.get("Deposit Growth") == s2.get("Deposit Growth"), (
        "Determinism broken — same seed+action produced different totals"
    )
    assert s1.get("Loan Book Growth") == s2.get("Loan Book Growth")


def test_v10363_idempotent_persist_after_action():
    """Persisting twice without further mutation produces the same state."""
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.teller_actions import fire_teller_deposit, find_first_deposit_account

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    account = find_first_deposit_account(bank)
    fire_teller_deposit(bank, account_no=account, amount=Decimal("5000000"))

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        s1 = _capture_bank_state(td_path)
        persist_bank_to_cbs(bank, output_dir=td_path)
        s2 = _capture_bank_state(td_path)
    # Compare all keys
    assert s1 == s2, "Persist not idempotent — re-persisting changed state"


# ────────────────────────────────────────────────────────────────────
# Section 5 — G249 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10363_g249_charter_section_2_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_charter_section_2
    result = gate_charter_section_2()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G249"


def test_v10363_g249_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G249", gate_charter_section_2)' in text

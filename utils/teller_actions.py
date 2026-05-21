"""utils/teller_actions.py — v10.363 Teller Action Primitives.

Discrete teller-action helpers for testing the Football Team Test chain
end-to-end. These are the entry points of Charter §2: a teller fires an
action on the virtual bank; the chain propagates the impact through CBS
persistence → actuals → MD's BSC tile.

Each helper:
  - Takes a VirtualBankCore + the action parameters
  - Mutates the bank via VirtualBankCore.update_account_balance (the
    production-grade primitive — preserves frozen-dataclass semantics
    by replacing rather than mutating in place)
  - Returns a result dict for assertion (account_no, old_balance,
    new_balance, delta, timestamp)

Why this module exists
----------------------
The v10.358 seeder populates a bank. The v10.359 bridge persists it. The
v10.362 binding wires the MD's BSC to bank_targets + bank aggregates.
But there was no clean way to ask: "fire a single, observable teller
action and assert the bank-wide totals reflect it." This module provides
that primitive. v10.363's Charter §2 integration test uses it.

Future batches can layer more action types on top (transfers, loan
disbursements, FX conversions) following the same fire_X(bank, ...) →
result-dict pattern. Each action becomes a clean assertion seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional


@dataclass
class TellerActionResult:
    """Structured result of a teller action — used for assertions."""
    action_type: str
    account_no: str
    old_balance: Decimal
    new_balance: Decimal
    delta: Decimal
    timestamp: str
    notes: str = ""


def fire_teller_deposit(
    bank: Any,
    account_no: str,
    amount: Decimal,
    transaction_date: Optional[str] = None,
) -> TellerActionResult:
    """Simulate a teller-channel deposit: increase the named account's
    balance by `amount` and update last_transaction_date.

    This is the Charter §2 entry point — the action a teller takes that
    the MD must see propagate to the bank's ROE tile in real-time.

    Parameters
    ----------
    bank : VirtualBankCore
        The populated bank (typically from utils.virtual_bank_seed)
    account_no : str
        e.g. "ECO0000000001"
    amount : Decimal
        Deposit amount in the account's currency. Must be positive.
    transaction_date : str, optional
        ISO date. Defaults to today's date.

    Returns
    -------
    TellerActionResult with old/new balance and delta.

    Raises
    ------
    KeyError if account_no doesn't exist
    ValueError if amount is not positive
    """
    if amount <= 0:
        raise ValueError(
            f"Deposit amount must be positive, got {amount}"
        )
    existing = bank.get_account(account_no)  # raises KeyError if missing
    old_balance = existing.balance
    new_balance = old_balance + Decimal(str(amount))
    ts = transaction_date or datetime.now(timezone.utc).date().isoformat()

    bank.update_account_balance(
        account_no=account_no,
        new_balance=new_balance,
        last_transaction_date=ts,
    )

    return TellerActionResult(
        action_type="TELLER_DEPOSIT",
        account_no=account_no,
        old_balance=old_balance,
        new_balance=new_balance,
        delta=Decimal(str(amount)),
        timestamp=ts,
        notes=f"Deposit of {amount} to {account_no} on {ts}",
    )


def fire_teller_withdrawal(
    bank: Any,
    account_no: str,
    amount: Decimal,
    transaction_date: Optional[str] = None,
    allow_overdraft: bool = False,
) -> TellerActionResult:
    """Simulate a teller-channel withdrawal: decrease the named account's
    balance by `amount`.

    Parameters
    ----------
    bank : VirtualBankCore
    account_no : str
    amount : Decimal — positive
    transaction_date : ISO date, defaults to today
    allow_overdraft : if False (default), raises if amount > balance.
                      Set True for OVERDRAFT accounts.

    Raises
    ------
    KeyError if account_no doesn't exist
    ValueError if amount is not positive, or if amount > balance
               (when allow_overdraft=False)
    """
    if amount <= 0:
        raise ValueError(f"Withdrawal amount must be positive, got {amount}")
    existing = bank.get_account(account_no)
    old_balance = existing.balance
    delta = Decimal(str(amount))
    if not allow_overdraft and delta > old_balance:
        raise ValueError(
            f"Insufficient balance: account {account_no} has {old_balance}, "
            f"cannot withdraw {amount}"
        )
    new_balance = old_balance - delta
    ts = transaction_date or datetime.now(timezone.utc).date().isoformat()

    bank.update_account_balance(
        account_no=account_no,
        new_balance=new_balance,
        last_transaction_date=ts,
    )

    return TellerActionResult(
        action_type="TELLER_WITHDRAWAL",
        account_no=account_no,
        old_balance=old_balance,
        new_balance=new_balance,
        delta=-delta,  # negative delta for withdrawal
        timestamp=ts,
        notes=f"Withdrawal of {amount} from {account_no} on {ts}",
    )


def find_first_deposit_account(bank: Any) -> Optional[str]:
    """Helper: return the account_no of the first CASA (current/savings)
    account in the bank, or None if none exists. Useful for tests that
    need any-deposit-account-will-do."""
    from utils.virtual_bank_core import AccountType
    for acct in bank.all_accounts():
        if acct.account_type in (AccountType.SAVINGS, AccountType.CURRENT):
            return acct.account_no
    return None


# ─── Self-test ────────────────────────────────────────────────────────────

def self_test() -> None:
    """v10.363 self_test — teller action primitives."""
    tests_run = 0

    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig

    # Seed a small bank
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    tests_run += 1

    # Find a deposit account
    account_no = find_first_deposit_account(bank)
    assert account_no is not None, "No deposit account found in seeded bank"
    tests_run += 1

    # Get its current balance
    acct = bank.get_account(account_no)
    initial_balance = acct.balance

    # Fire a deposit
    result = fire_teller_deposit(
        bank, account_no=account_no, amount=Decimal("1000000")
    )
    assert result.action_type == "TELLER_DEPOSIT"
    assert result.delta == Decimal("1000000")
    assert result.old_balance == initial_balance
    assert result.new_balance == initial_balance + Decimal("1000000")
    tests_run += 1

    # Verify bank state actually changed
    acct_after = bank.get_account(account_no)
    assert acct_after.balance == initial_balance + Decimal("1000000")
    tests_run += 1

    # Fire a withdrawal that succeeds
    result2 = fire_teller_withdrawal(
        bank, account_no=account_no, amount=Decimal("500000")
    )
    assert result2.action_type == "TELLER_WITHDRAWAL"
    assert result2.delta == -Decimal("500000")
    tests_run += 1

    # Verify
    acct_after2 = bank.get_account(account_no)
    assert acct_after2.balance == initial_balance + Decimal("500000")
    tests_run += 1

    # Withdrawal exceeding balance fails
    raised = False
    try:
        fire_teller_withdrawal(
            bank, account_no=account_no,
            amount=acct_after2.balance + Decimal("1"),
        )
    except ValueError:
        raised = True
    assert raised, "Expected ValueError for over-withdrawal"
    tests_run += 1

    # Bad inputs
    raised = False
    try:
        fire_teller_deposit(bank, account_no=account_no, amount=Decimal("-1"))
    except ValueError:
        raised = True
    assert raised, "Negative deposit should raise"
    tests_run += 1

    raised = False
    try:
        fire_teller_deposit(bank, account_no="NONEXISTENT", amount=Decimal("1"))
    except KeyError:
        raised = True
    assert raised, "Unknown account should raise KeyError"
    tests_run += 1

    print(f"✓ teller_actions self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()

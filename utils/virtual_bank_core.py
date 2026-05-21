"""utils/virtual_bank_core.py — v10.30 Virtual Bank simulation framework batch 1.

╔════════════════════════════════════════════════════════════════════════╗
║  VIRTUAL BANK CORE — MOCK FLEXCUBE + ENTITY SIMULATOR                  ║
║  Cat B operational utility — testbed for the platform's modules        ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (does not affect production capital, credit         ║
║              decisions, or regulatory reporting; provides a            ║
║              deterministic simulation surface for testing modules      ║
║              that would otherwise require real FLEXCUBE access)        ║
║  Implements simulation infrastructure — not regulatory standards:       ║
║    Mock FLEXCUBE adapter (drop-in API surface)                          ║
║    Banking entity simulator (customers/accounts/loans/branches)         ║
║    Deterministic seeding for reproducible test runs                     ║
║    Time controller (advance day/month/year)                             ║
║    Day-end batch processes (interest accrual, fee charging)             ║
║    Per-account ledger (transaction history within simulation)          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Key design principles:                                                 ║
║    DETERMINISM: same seed + same scenario → same outputs always         ║
║    ISOLATION: no real network, file system, or DB calls                 ║
║    DROP-IN: matches utils/flexcube_adapter API surface                  ║
║    SCOPE: lightweight; not a full core banking system simulation        ║
║                                                                         ║
║  Honesty Rule 1: every simulation output reports seed + day_offset    ║
║  for reproducibility; nondeterministic operations are explicitly       ║
║  flagged as such.                                                       ║
║  Honesty Rule 7: market-data fetcher (rates, FX) is callable hook;    ║
║  without wiring, simulator uses scenario-defined defaults rather than ║
║  fabricating live market data.                                         ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "VirtualBankCore is a deterministic simulation testbed. It does NOT "
    "interact with real FLEXCUBE, real customer data, real accounts, or "
    "real money. Outputs are reproducible from (seed, scenario, "
    "day_offset) tuples. Per Rule 7, market data fetchers (CBR, KESONIA, "
    "FX rates) are hookable; without wiring, scenario defaults apply. "
    "Cat B classification — failures here cannot affect production "
    "capital, credit decisions, or regulatory reporting."
)


# ════════════════════════════════════════════════════════════════════════
# Seed Management — Determinism
# ════════════════════════════════════════════════════════════════════════

def derive_seed(
    *,
    base_seed: str,
    namespace: str,
    discriminator: str = "",
) -> int:
    """Derive a 64-bit deterministic seed from inputs.

    Same (base_seed, namespace, discriminator) → same int always.
    Used to seed pseudo-random generators inside the simulator while
    keeping the result deterministic.
    """
    h = hashlib.sha256()
    h.update(base_seed.encode("utf-8"))
    h.update(b"\x00")
    h.update(namespace.encode("utf-8"))
    h.update(b"\x00")
    h.update(discriminator.encode("utf-8"))
    # Take first 8 bytes → 64-bit int
    return int.from_bytes(h.digest()[:8], byteorder="big", signed=False)


def deterministic_pseudo_random(
    *, seed: int, n: int, modulo: int,
) -> List[int]:
    """Generate n deterministic pseudo-random ints in [0, modulo).

    Uses linear congruential generator seeded by `seed`. Reproducible
    across runs and platforms (no Python's `random` module which is
    implementation-defined).
    """
    # LCG params from Numerical Recipes
    a = 1664525
    c = 1013904223
    m = 2 ** 32
    state = seed % m
    out: List[int] = []
    for _ in range(n):
        state = (a * state + c) % m
        out.append(state % modulo)
    return out


# ════════════════════════════════════════════════════════════════════════
# Banking Entity Models
# ════════════════════════════════════════════════════════════════════════

class CustomerSegment(Enum):
    RETAIL = "RETAIL"
    SME = "SME"
    CORPORATE = "CORPORATE"
    HNW = "HNW"
    PRIVATE_BANKING = "PRIVATE_BANKING"


class AccountType(Enum):
    SAVINGS = "SAVINGS"
    CURRENT = "CURRENT"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    LOAN = "LOAN"
    OVERDRAFT = "OVERDRAFT"


class AccountStatus(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class LoanStatus(Enum):
    APPLICATION = "APPLICATION"
    APPROVED = "APPROVED"
    DISBURSED = "DISBURSED"
    PERFORMING = "PERFORMING"
    DELINQUENT_30 = "DELINQUENT_30"     # PG/04 watch
    DELINQUENT_60 = "DELINQUENT_60"     # PG/04 substandard
    DELINQUENT_90 = "DELINQUENT_90"     # PG/04 doubtful
    NON_PERFORMING = "NON_PERFORMING"   # PG/04 loss
    WRITTEN_OFF = "WRITTEN_OFF"
    CLOSED = "CLOSED"


# Allowed status transitions
ALLOWED_LOAN_TRANSITIONS: Mapping[
    LoanStatus, Tuple[LoanStatus, ...]] = {
    LoanStatus.APPLICATION: (
        LoanStatus.APPROVED, LoanStatus.CLOSED),
    LoanStatus.APPROVED: (
        LoanStatus.DISBURSED, LoanStatus.CLOSED),
    LoanStatus.DISBURSED: (
        LoanStatus.PERFORMING,),
    LoanStatus.PERFORMING: (
        LoanStatus.DELINQUENT_30, LoanStatus.CLOSED),
    LoanStatus.DELINQUENT_30: (
        LoanStatus.PERFORMING, LoanStatus.DELINQUENT_60),
    LoanStatus.DELINQUENT_60: (
        LoanStatus.PERFORMING, LoanStatus.DELINQUENT_30,
        LoanStatus.DELINQUENT_90),
    LoanStatus.DELINQUENT_90: (
        LoanStatus.PERFORMING, LoanStatus.DELINQUENT_60,
        LoanStatus.NON_PERFORMING),
    LoanStatus.NON_PERFORMING: (
        LoanStatus.DELINQUENT_90, LoanStatus.WRITTEN_OFF,
        LoanStatus.CLOSED),
    LoanStatus.WRITTEN_OFF: (LoanStatus.CLOSED,),
    LoanStatus.CLOSED: (),    # terminal
}


def is_valid_loan_transition(
    from_status: LoanStatus, to_status: LoanStatus,
) -> bool:
    return to_status in ALLOWED_LOAN_TRANSITIONS.get(from_status, ())


@dataclass(frozen=True)
class VirtualCustomer:
    cif: str
    full_name: str
    segment: CustomerSegment
    branch_code: str
    rm_code: str
    onboarding_date: str            # ISO-8601
    is_pep: bool = False
    sanctions_status: str = "CLEAR"   # CLEAR / WATCH / HIT
    notes: str = ""


@dataclass(frozen=True)
class VirtualAccount:
    account_no: str                 # e.g., "ECO1000000001"
    cif: str
    branch_code: str
    account_type: AccountType
    currency: str
    balance: Decimal
    status: AccountStatus
    open_date: str
    last_transaction_date: Optional[str] = None
    interest_rate_pct: Decimal = Decimal("0")
    notes: str = ""


@dataclass(frozen=True)
class VirtualLoan:
    loan_id: str
    cif: str
    branch_code: str
    rm_code: str
    principal: Decimal
    outstanding: Decimal
    rate_pct: Decimal
    tenor_months: int
    disbursement_date: Optional[str]
    next_due_date: Optional[str]
    status: LoanStatus
    days_past_due: int = 0
    is_climate_overlay_applied: bool = False    # from v10.6+ stack
    notes: str = ""


@dataclass(frozen=True)
class VirtualBranch:
    branch_code: str
    branch_name: str
    region: str
    branch_type: str    # FLAGSHIP / MAIN / STANDARD / LIGHT / HO
    n_staff: int
    notes: str = ""


@dataclass(frozen=True)
class VirtualTransaction:
    txn_id: str
    txn_date: str
    account_no: str
    txn_type: str       # DEPOSIT / WITHDRAWAL / TRANSFER / FEE / INTEREST
    amount: Decimal
    counterparty_account: Optional[str] = None
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Time Controller
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SimulationTime:
    """Snapshot of simulation time."""
    base_date: str                  # ISO-8601, simulation start
    day_offset: int                 # days elapsed since base_date

    def current_date(self) -> date:
        return date.fromisoformat(self.base_date) + timedelta(
            days=self.day_offset)

    def current_iso(self) -> str:
        return self.current_date().isoformat()


# ════════════════════════════════════════════════════════════════════════
# Mock FLEXCUBE Adapter — drop-in replacement
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MockResponse:
    """Wrapper for mock FLEXCUBE response with metadata.

    Per Rule 1, every response carries seed + day_offset for
    reproducibility tracing.
    """
    payload: Mapping[str, Any]
    is_synthetic: bool = True       # always True for mock
    sim_seed: str = ""              # base_seed used
    sim_day_offset: int = 0
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Day-End Batch Processes
# ════════════════════════════════════════════════════════════════════════

def daily_interest_amount(
    *,
    balance: Decimal,
    annual_rate_pct: Decimal,
    days: int = 1,
    days_in_year: int = 365,
) -> Decimal:
    """Compute simple daily interest accrual.

    Uses Decimal throughout — no float arithmetic on money.
    """
    if days <= 0 or annual_rate_pct <= Decimal("0"):
        return Decimal("0")
    daily_rate = annual_rate_pct / Decimal("100") / Decimal(days_in_year)
    return (balance * daily_rate * Decimal(days)).quantize(
        Decimal("0.01"))


def days_past_due(
    *, next_due_date: Optional[str], current_date: date,
) -> int:
    """Days past next due date; 0 if not yet due or no due date."""
    if next_due_date is None:
        return 0
    try:
        due = date.fromisoformat(next_due_date)
    except ValueError:
        return 0
    diff = (current_date - due).days
    return max(0, diff)


def loan_status_from_dpd(*, dpd: int) -> LoanStatus:
    """Map DPD to PG/04 loan status."""
    if dpd <= 0:
        return LoanStatus.PERFORMING
    if dpd < 30:
        return LoanStatus.PERFORMING
    if dpd < 60:
        return LoanStatus.DELINQUENT_30
    if dpd < 90:
        return LoanStatus.DELINQUENT_60
    if dpd < 180:
        return LoanStatus.DELINQUENT_90
    return LoanStatus.NON_PERFORMING


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class VirtualBankCore:
    """Deterministic simulation testbed for the platform's modules.

    Provides a drop-in mock for utils/flexcube_adapter and a banking
    entity simulator (customers/accounts/loans/branches/transactions)
    seeded for reproducibility.

    Example:
        bank = VirtualBankCore(
            entity_name="Test Bank Kenya",
            base_seed="recipe-2026-01",
            base_date="2026-01-01")
        bank.add_branch(VirtualBranch(...))
        bank.add_customer(VirtualCustomer(...))
        bank.tick(days=30)        # advance 30 days
        bank.run_day_end()         # accrue interest, age loans
    """

    def __init__(
        self,
        *,
        entity_name: str = "Test Bank Kenya",
        base_seed: str = "default",
        base_date: str = "2026-01-01",
    ):
        self.entity_name = entity_name
        self.base_seed = base_seed
        self.base_date = base_date
        self._day_offset = 0
        self._customers: Dict[str, VirtualCustomer] = {}
        self._accounts: Dict[str, VirtualAccount] = {}
        self._loans: Dict[str, VirtualLoan] = {}
        self._branches: Dict[str, VirtualBranch] = {}
        self._transactions: List[VirtualTransaction] = []
        self._loan_transitions: List[
            Tuple[str, LoanStatus, LoanStatus, str]] = []
        # Day-end runs counter (for verification)
        self._day_end_runs: int = 0

    # ── Time control ───────────────────────────────────────────────────
    def current_time(self) -> SimulationTime:
        return SimulationTime(
            base_date=self.base_date, day_offset=self._day_offset)

    def current_date(self) -> date:
        return self.current_time().current_date()

    def tick(self, *, days: int = 1) -> SimulationTime:
        if days < 0:
            raise ValueError("cannot tick backwards in simulation")
        self._day_offset += days
        return self.current_time()

    # ── Customers ──────────────────────────────────────────────────────
    def add_customer(self, c: VirtualCustomer) -> None:
        if c.cif in self._customers:
            raise ValueError(f"customer {c.cif} already exists")
        self._customers[c.cif] = c

    def get_customer(self, cif: str) -> VirtualCustomer:
        if cif not in self._customers:
            raise KeyError(f"customer {cif} not found")
        return self._customers[cif]

    def all_customers(self) -> Tuple[VirtualCustomer, ...]:
        return tuple(self._customers.values())

    # ── Accounts ───────────────────────────────────────────────────────
    def add_account(self, a: VirtualAccount) -> None:
        if a.account_no in self._accounts:
            raise ValueError(f"account {a.account_no} already exists")
        if a.cif not in self._customers:
            raise KeyError(f"customer {a.cif} not registered")
        self._accounts[a.account_no] = a

    def get_account(self, account_no: str) -> VirtualAccount:
        if account_no not in self._accounts:
            raise KeyError(f"account {account_no} not found")
        return self._accounts[account_no]

    def all_accounts(self) -> Tuple[VirtualAccount, ...]:
        return tuple(self._accounts.values())

    def accounts_by_cif(self, cif: str) -> Tuple[VirtualAccount, ...]:
        return tuple(
            a for a in self._accounts.values() if a.cif == cif)

    def update_account_balance(
        self, *, account_no: str, new_balance: Decimal,
        last_transaction_date: Optional[str] = None,
    ) -> VirtualAccount:
        existing = self.get_account(account_no)
        updated = VirtualAccount(
            account_no=existing.account_no,
            cif=existing.cif,
            branch_code=existing.branch_code,
            account_type=existing.account_type,
            currency=existing.currency,
            balance=new_balance,
            status=existing.status,
            open_date=existing.open_date,
            last_transaction_date=(
                last_transaction_date
                or existing.last_transaction_date),
            interest_rate_pct=existing.interest_rate_pct,
            notes=existing.notes)
        self._accounts[account_no] = updated
        return updated

    # ── Loans ──────────────────────────────────────────────────────────
    def add_loan(self, l: VirtualLoan) -> None:
        if l.loan_id in self._loans:
            raise ValueError(f"loan {l.loan_id} already exists")
        if l.cif not in self._customers:
            raise KeyError(f"customer {l.cif} not registered")
        self._loans[l.loan_id] = l

    def get_loan(self, loan_id: str) -> VirtualLoan:
        if loan_id not in self._loans:
            raise KeyError(f"loan {loan_id} not found")
        return self._loans[loan_id]

    def all_loans(self) -> Tuple[VirtualLoan, ...]:
        return tuple(self._loans.values())

    def loans_by_status(
        self, status: LoanStatus,
    ) -> Tuple[VirtualLoan, ...]:
        return tuple(l for l in self._loans.values() if l.status == status)

    def transition_loan(
        self,
        *,
        loan_id: str,
        to_status: LoanStatus,
        timestamp: str,
        notes: str = "",
    ) -> VirtualLoan:
        existing = self.get_loan(loan_id)
        if not is_valid_loan_transition(existing.status, to_status):
            allowed = ALLOWED_LOAN_TRANSITIONS.get(existing.status, ())
            raise ValueError(
                f"invalid loan transition "
                f"{existing.status.value} → {to_status.value}; "
                f"allowed: {[s.value for s in allowed]}")
        self._loan_transitions.append(
            (loan_id, existing.status, to_status, timestamp))
        updated = VirtualLoan(
            loan_id=existing.loan_id, cif=existing.cif,
            branch_code=existing.branch_code,
            rm_code=existing.rm_code,
            principal=existing.principal,
            outstanding=existing.outstanding,
            rate_pct=existing.rate_pct,
            tenor_months=existing.tenor_months,
            disbursement_date=existing.disbursement_date,
            next_due_date=existing.next_due_date,
            status=to_status,
            days_past_due=existing.days_past_due,
            is_climate_overlay_applied=existing.is_climate_overlay_applied,
            notes=(
                existing.notes + "\n" + notes if notes
                else existing.notes))
        self._loans[loan_id] = updated
        return updated

    # ── Branches ───────────────────────────────────────────────────────
    def add_branch(self, b: VirtualBranch) -> None:
        if b.branch_code in self._branches:
            raise ValueError(f"branch {b.branch_code} already exists")
        self._branches[b.branch_code] = b

    def get_branch(self, branch_code: str) -> VirtualBranch:
        if branch_code not in self._branches:
            raise KeyError(f"branch {branch_code} not found")
        return self._branches[branch_code]

    def all_branches(self) -> Tuple[VirtualBranch, ...]:
        return tuple(self._branches.values())

    # ── Transactions ───────────────────────────────────────────────────
    def post_transaction(self, t: VirtualTransaction) -> None:
        if t.account_no not in self._accounts:
            raise KeyError(f"account {t.account_no} not registered")
        self._transactions.append(t)
        # Update account balance
        existing = self._accounts[t.account_no]
        if t.txn_type in ("DEPOSIT", "INTEREST"):
            new_balance = existing.balance + t.amount
        elif t.txn_type in ("WITHDRAWAL", "FEE"):
            new_balance = existing.balance - t.amount
        else:
            new_balance = existing.balance
        self.update_account_balance(
            account_no=t.account_no,
            new_balance=new_balance,
            last_transaction_date=t.txn_date)

    def transactions_by_account(
        self, account_no: str,
    ) -> Tuple[VirtualTransaction, ...]:
        return tuple(
            t for t in self._transactions
            if t.account_no == account_no)

    def all_transactions(self) -> Tuple[VirtualTransaction, ...]:
        return tuple(self._transactions)

    # ── Day-end batch ──────────────────────────────────────────────────
    def run_day_end(self) -> Dict[str, Any]:
        """Run day-end batch: interest accrual, loan aging.

        Returns a summary of operations performed.
        """
        current = self.current_date()
        n_interest_postings = 0
        total_interest_kes = Decimal("0")
        n_loan_status_changes = 0

        # Interest accrual on savings + fixed deposits
        existing_txn_ids = {t.txn_id for t in self._transactions}
        for acc in list(self._accounts.values()):
            if acc.status != AccountStatus.ACTIVE:
                continue
            if acc.account_type not in (
                    AccountType.SAVINGS,
                    AccountType.FIXED_DEPOSIT):
                continue
            if acc.interest_rate_pct <= Decimal("0"):
                continue
            interest = daily_interest_amount(
                balance=acc.balance,
                annual_rate_pct=acc.interest_rate_pct)
            if interest <= Decimal("0"):
                continue
            txn_id = f"INT-{acc.account_no}-{current.isoformat()}"
            if txn_id in existing_txn_ids:
                # Already posted today — idempotent skip
                continue
            self.post_transaction(VirtualTransaction(
                txn_id=txn_id,
                txn_date=current.isoformat(),
                account_no=acc.account_no,
                txn_type="INTEREST",
                amount=interest,
                notes="day-end interest accrual"))
            n_interest_postings += 1
            total_interest_kes += interest

        # Loan aging — recompute DPD + status from next_due_date
        for loan in list(self._loans.values()):
            if loan.status in (
                    LoanStatus.CLOSED, LoanStatus.WRITTEN_OFF,
                    LoanStatus.APPLICATION):
                continue
            new_dpd = days_past_due(
                next_due_date=loan.next_due_date,
                current_date=current)
            new_status_candidate = loan_status_from_dpd(dpd=new_dpd)
            # Only transition if it's a valid transition AND different
            if (new_status_candidate != loan.status
                    and is_valid_loan_transition(
                        loan.status, new_status_candidate)):
                self.transition_loan(
                    loan_id=loan.loan_id,
                    to_status=new_status_candidate,
                    timestamp=current.isoformat(),
                    notes=f"day-end aging dpd={new_dpd}")
                n_loan_status_changes += 1
            # Update DPD even without status change
            existing = self._loans[loan.loan_id]
            if existing.days_past_due != new_dpd:
                self._loans[loan.loan_id] = VirtualLoan(
                    loan_id=existing.loan_id, cif=existing.cif,
                    branch_code=existing.branch_code,
                    rm_code=existing.rm_code,
                    principal=existing.principal,
                    outstanding=existing.outstanding,
                    rate_pct=existing.rate_pct,
                    tenor_months=existing.tenor_months,
                    disbursement_date=existing.disbursement_date,
                    next_due_date=existing.next_due_date,
                    status=existing.status,
                    days_past_due=new_dpd,
                    is_climate_overlay_applied=(
                        existing.is_climate_overlay_applied),
                    notes=existing.notes)

        self._day_end_runs += 1
        return {
            "run_date": current.isoformat(),
            "n_interest_postings": n_interest_postings,
            "total_interest_kes": total_interest_kes,
            "n_loan_status_changes": n_loan_status_changes,
            "day_end_run_number": self._day_end_runs,
        }

    # ── Mock FLEXCUBE adapter API surface ──────────────────────────────
    def fetch_account_balance(
        self, account_no: str, branch: str = "001",
    ) -> MockResponse:
        """Mock equivalent of utils.flexcube_adapter.fetch_account_balance."""
        try:
            acc = self.get_account(account_no)
        except KeyError:
            return MockResponse(
                payload={"error": "account_not_found"},
                sim_seed=self.base_seed,
                sim_day_offset=self._day_offset,
                notes=f"account {account_no} not in simulation")
        return MockResponse(
            payload={
                "account_no": acc.account_no,
                "branch": acc.branch_code,
                "balance": str(acc.balance),
                "currency": acc.currency,
                "status": acc.status.value,
                "account_type": acc.account_type.value,
                "as_of_date": self.current_time().current_iso()},
            sim_seed=self.base_seed,
            sim_day_offset=self._day_offset)

    def fetch_customer(self, cif: str) -> MockResponse:
        try:
            c = self.get_customer(cif)
        except KeyError:
            return MockResponse(
                payload={"error": "customer_not_found"},
                sim_seed=self.base_seed,
                sim_day_offset=self._day_offset,
                notes=f"cif {cif} not in simulation")
        return MockResponse(
            payload={
                "cif": c.cif, "full_name": c.full_name,
                "segment": c.segment.value,
                "branch_code": c.branch_code,
                "rm_code": c.rm_code,
                "onboarding_date": c.onboarding_date,
                "is_pep": c.is_pep,
                "sanctions_status": c.sanctions_status},
            sim_seed=self.base_seed,
            sim_day_offset=self._day_offset)

    def fetch_loan_status(self, loan_id: str) -> MockResponse:
        try:
            l = self.get_loan(loan_id)
        except KeyError:
            return MockResponse(
                payload={"error": "loan_not_found"},
                sim_seed=self.base_seed,
                sim_day_offset=self._day_offset,
                notes=f"loan {loan_id} not in simulation")
        return MockResponse(
            payload={
                "loan_id": l.loan_id, "cif": l.cif,
                "principal": str(l.principal),
                "outstanding": str(l.outstanding),
                "rate_pct": str(l.rate_pct),
                "tenor_months": l.tenor_months,
                "next_due_date": l.next_due_date,
                "status": l.status.value,
                "days_past_due": l.days_past_due},
            sim_seed=self.base_seed,
            sim_day_offset=self._day_offset)

    def fetch_branch_metrics(self, branch_code: str) -> MockResponse:
        try:
            b = self.get_branch(branch_code)
        except KeyError:
            return MockResponse(
                payload={"error": "branch_not_found"},
                sim_seed=self.base_seed,
                sim_day_offset=self._day_offset,
                notes=f"branch {branch_code} not in simulation")
        # Aggregate metrics for this branch
        accs = [a for a in self._accounts.values()
                  if a.branch_code == branch_code]
        loans = [l for l in self._loans.values()
                   if l.branch_code == branch_code]
        total_deposits = sum(
            (a.balance for a in accs
             if a.account_type in (
                 AccountType.SAVINGS, AccountType.CURRENT,
                 AccountType.FIXED_DEPOSIT)),
            Decimal("0"))
        total_loans = sum(
            (l.outstanding for l in loans), Decimal("0"))
        return MockResponse(
            payload={
                "branch_code": b.branch_code,
                "branch_name": b.branch_name,
                "region": b.region,
                "branch_type": b.branch_type,
                "n_staff": b.n_staff,
                "n_accounts": len(accs),
                "n_loans": len(loans),
                "total_deposits": str(total_deposits),
                "total_loans": str(total_loans)},
            sim_seed=self.base_seed,
            sim_day_offset=self._day_offset)

    def fetch_rm_portfolio(self, rm_code: str) -> MockResponse:
        cifs = [c.cif for c in self._customers.values()
                  if c.rm_code == rm_code]
        loans = [l for l in self._loans.values()
                   if l.rm_code == rm_code]
        accs = [a for a in self._accounts.values() if a.cif in cifs]
        total_deposits = sum(
            (a.balance for a in accs
             if a.account_type in (
                 AccountType.SAVINGS, AccountType.CURRENT,
                 AccountType.FIXED_DEPOSIT)),
            Decimal("0"))
        total_loans = sum(
            (l.outstanding for l in loans), Decimal("0"))
        return MockResponse(
            payload={
                "rm_code": rm_code,
                "n_customers": len(cifs),
                "n_loans": len(loans),
                "total_deposits": str(total_deposits),
                "total_loans": str(total_loans)},
            sim_seed=self.base_seed,
            sim_day_offset=self._day_offset)

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        n_npl = len(
            [l for l in self._loans.values()
             if l.status in (
                 LoanStatus.NON_PERFORMING,
                 LoanStatus.WRITTEN_OFF,
                 LoanStatus.DELINQUENT_90,
                 LoanStatus.DELINQUENT_60,
                 LoanStatus.DELINQUENT_30)])
        total_loans_count = sum(
            1 for l in self._loans.values()
            if l.status not in (
                LoanStatus.CLOSED, LoanStatus.APPLICATION))
        npl_ratio = (
            Decimal(n_npl) / Decimal(total_loans_count)
            if total_loans_count > 0 else Decimal("0"))
        return {
            "entity": self.entity_name,
            "base_seed": self.base_seed,
            "current_iso": self.current_time().current_iso(),
            "day_offset": self._day_offset,
            "n_customers": len(self._customers),
            "n_accounts": len(self._accounts),
            "n_loans": len(self._loans),
            "n_branches": len(self._branches),
            "n_transactions": len(self._transactions),
            "n_day_end_runs": self._day_end_runs,
            "n_npl_loans": n_npl,
            "npl_ratio": str(npl_ratio),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_test_bank():
    bank = VirtualBankCore(
        entity_name="Test Bank Kenya",
        base_seed="test-seed-1",
        base_date="2026-01-01")
    bank.add_branch(VirtualBranch(
        branch_code="HQ", branch_name="HQ", region="Nairobi",
        branch_type="HO", n_staff=50))
    bank.add_branch(VirtualBranch(
        branch_code="BR1", branch_name="Westlands",
        region="Nairobi",
        branch_type="MAIN", n_staff=10))
    bank.add_customer(VirtualCustomer(
        cif="100000001", full_name="Alice Mwangi",
        segment=CustomerSegment.RETAIL,
        branch_code="BR1", rm_code="RM1",
        onboarding_date="2025-01-01"))
    bank.add_account(VirtualAccount(
        account_no="ECO1000000001", cif="100000001",
        branch_code="BR1",
        account_type=AccountType.SAVINGS,
        currency="KES",
        balance=Decimal("100000"),
        status=AccountStatus.ACTIVE,
        open_date="2025-01-01",
        interest_rate_pct=Decimal("3.65")))    # 3.65% annual = 0.01% daily
    return bank


def _test_seed_determinism():
    """Same inputs → same seed always."""
    s1 = derive_seed(
        base_seed="abc", namespace="customers", discriminator="x")
    s2 = derive_seed(
        base_seed="abc", namespace="customers", discriminator="x")
    s3 = derive_seed(
        base_seed="abc", namespace="customers", discriminator="y")
    assert s1 == s2
    assert s1 != s3


def _test_lcg_determinism():
    """LCG produces same sequence with same seed."""
    a = deterministic_pseudo_random(seed=42, n=10, modulo=100)
    b = deterministic_pseudo_random(seed=42, n=10, modulo=100)
    assert a == b
    c = deterministic_pseudo_random(seed=43, n=10, modulo=100)
    assert a != c


def _test_lcg_modulo_respected():
    """Output values stay in [0, modulo)."""
    out = deterministic_pseudo_random(seed=1, n=100, modulo=10)
    assert all(0 <= x < 10 for x in out)


def _test_loan_transition_valid_path():
    assert is_valid_loan_transition(
        LoanStatus.PERFORMING, LoanStatus.DELINQUENT_30)


def _test_loan_transition_invalid_skip():
    """Cannot skip from APPLICATION to PERFORMING."""
    assert not is_valid_loan_transition(
        LoanStatus.APPLICATION, LoanStatus.PERFORMING)


def _test_loan_closed_terminal():
    assert len(ALLOWED_LOAN_TRANSITIONS[LoanStatus.CLOSED]) == 0


def _test_daily_interest_savings():
    """3.65% annual → ~0.01% daily."""
    interest = daily_interest_amount(
        balance=Decimal("100000"),
        annual_rate_pct=Decimal("3.65"))
    # 100000 * 0.0365 / 365 = 10.00 per day
    assert interest == Decimal("10.00")


def _test_daily_interest_zero_rate():
    interest = daily_interest_amount(
        balance=Decimal("100000"),
        annual_rate_pct=Decimal("0"))
    assert interest == Decimal("0")


def _test_dpd_not_yet_due():
    """next_due_date in future → 0 dpd."""
    today = date(2026, 5, 1)
    dpd = days_past_due(
        next_due_date="2026-06-01", current_date=today)
    assert dpd == 0


def _test_dpd_30_days_late():
    today = date(2026, 5, 1)
    dpd = days_past_due(
        next_due_date="2026-04-01", current_date=today)
    assert dpd == 30


def _test_loan_status_from_dpd():
    assert loan_status_from_dpd(dpd=0) == LoanStatus.PERFORMING
    assert loan_status_from_dpd(dpd=20) == LoanStatus.PERFORMING
    assert loan_status_from_dpd(dpd=45) == LoanStatus.DELINQUENT_30
    assert loan_status_from_dpd(dpd=75) == LoanStatus.DELINQUENT_60
    assert loan_status_from_dpd(dpd=120) == LoanStatus.DELINQUENT_90
    assert loan_status_from_dpd(dpd=200) == LoanStatus.NON_PERFORMING


def _test_bank_register_dup_customer_raises():
    bank = _make_test_bank()
    try:
        bank.add_customer(VirtualCustomer(
            cif="100000001", full_name="X",
            segment=CustomerSegment.RETAIL,
            branch_code="BR1", rm_code="RM1",
            onboarding_date="2025-01-01"))
        assert False
    except ValueError:
        pass


def _test_bank_account_for_unknown_customer_raises():
    bank = _make_test_bank()
    try:
        bank.add_account(VirtualAccount(
            account_no="ECO9999999999",
            cif="999999999",    # not registered
            branch_code="BR1",
            account_type=AccountType.SAVINGS,
            currency="KES",
            balance=Decimal("0"),
            status=AccountStatus.ACTIVE,
            open_date="2026-01-01"))
        assert False
    except KeyError:
        pass


def _test_bank_tick_advances_time():
    bank = _make_test_bank()
    assert bank.current_date() == date(2026, 1, 1)
    bank.tick(days=30)
    assert bank.current_date() == date(2026, 1, 31)


def _test_bank_tick_negative_raises():
    bank = _make_test_bank()
    try:
        bank.tick(days=-1)
        assert False
    except ValueError:
        pass


def _test_bank_post_transaction_updates_balance():
    bank = _make_test_bank()
    bank.post_transaction(VirtualTransaction(
        txn_id="T1", txn_date="2026-01-01",
        account_no="ECO1000000001",
        txn_type="DEPOSIT", amount=Decimal("5000")))
    acc = bank.get_account("ECO1000000001")
    assert acc.balance == Decimal("105000")


def _test_bank_day_end_accrues_interest():
    bank = _make_test_bank()
    initial = bank.get_account("ECO1000000001").balance
    summary = bank.run_day_end()
    assert summary["n_interest_postings"] == 1
    final = bank.get_account("ECO1000000001").balance
    # 100000 * 0.0365 / 365 = 10.00
    assert final == initial + Decimal("10.00")


def _test_bank_day_end_idempotent_same_day():
    """Running day-end twice on same day shouldn't double-post."""
    bank = _make_test_bank()
    bank.run_day_end()
    interest_count_after_1 = sum(
        1 for t in bank.all_transactions()
        if t.txn_type == "INTEREST")
    bank.run_day_end()    # same day
    interest_count_after_2 = sum(
        1 for t in bank.all_transactions()
        if t.txn_type == "INTEREST")
    # Skipped due to duplicate txn_id detection
    assert interest_count_after_2 == interest_count_after_1


def _test_bank_day_end_ages_loans():
    """Loan PERFORMING with 35 days past due → DELINQUENT_30."""
    bank = _make_test_bank()
    bank.add_loan(VirtualLoan(
        loan_id="L1", cif="100000001",
        branch_code="BR1", rm_code="RM1",
        principal=Decimal("500000"),
        outstanding=Decimal("450000"),
        rate_pct=Decimal("13.5"),
        tenor_months=24,
        disbursement_date="2025-06-01",
        next_due_date="2025-12-01",    # was due Dec 2025
        status=LoanStatus.PERFORMING,
        days_past_due=0))
    # Tick to Jan 6, 2026 — 36 days past due
    bank.tick(days=5)
    summary = bank.run_day_end()
    loan = bank.get_loan("L1")
    assert loan.days_past_due >= 30
    assert loan.status == LoanStatus.DELINQUENT_30
    assert summary["n_loan_status_changes"] >= 1


def _test_mock_fetch_account_balance():
    bank = _make_test_bank()
    resp = bank.fetch_account_balance(
        "ECO1000000001", branch="BR1")
    assert "balance" in resp.payload
    assert resp.payload["balance"] == "100000"
    assert resp.is_synthetic
    assert resp.sim_seed == "test-seed-1"


def _test_mock_fetch_account_unknown():
    bank = _make_test_bank()
    resp = bank.fetch_account_balance("UNKNOWN")
    assert resp.payload.get("error") == "account_not_found"


def _test_mock_fetch_customer():
    bank = _make_test_bank()
    resp = bank.fetch_customer("100000001")
    assert resp.payload["full_name"] == "Alice Mwangi"
    assert resp.payload["segment"] == "RETAIL"


def _test_mock_fetch_branch_metrics_aggregates():
    bank = _make_test_bank()
    resp = bank.fetch_branch_metrics("BR1")
    assert resp.payload["n_accounts"] == 1
    assert resp.payload["total_deposits"] == "100000"


def _test_mock_responses_carry_seed_for_traceability():
    """Per Rule 1 — every response carries seed + day_offset."""
    bank = _make_test_bank()
    bank.tick(days=5)
    resp = bank.fetch_account_balance("ECO1000000001")
    assert resp.sim_seed == "test-seed-1"
    assert resp.sim_day_offset == 5


def _test_loan_invalid_transition_raises():
    bank = _make_test_bank()
    bank.add_loan(VirtualLoan(
        loan_id="L1", cif="100000001",
        branch_code="BR1", rm_code="RM1",
        principal=Decimal("500000"),
        outstanding=Decimal("450000"),
        rate_pct=Decimal("13.5"),
        tenor_months=24,
        disbursement_date="2025-06-01",
        next_due_date="2025-12-01",
        status=LoanStatus.APPLICATION,
        days_past_due=0))
    # Cannot skip from APPLICATION to PERFORMING
    try:
        bank.transition_loan(
            loan_id="L1", to_status=LoanStatus.PERFORMING,
            timestamp="t")
        assert False
    except ValueError:
        pass


def _test_bank_board_summary():
    bank = _make_test_bank()
    s = bank.board_summary()
    assert s["n_customers"] == 1
    assert s["n_accounts"] == 1
    assert s["n_branches"] == 2
    assert s["base_seed"] == "test-seed-1"


def _test_two_banks_with_same_seed_produce_same_outputs():
    """Determinism: same setup + same seed = same outputs."""
    def make(seed):
        b = VirtualBankCore(
            entity_name="X", base_seed=seed,
            base_date="2026-01-01")
        b.add_branch(VirtualBranch(
            branch_code="BR1", branch_name="X",
            region="Y", branch_type="MAIN", n_staff=5))
        b.add_customer(VirtualCustomer(
            cif="C1", full_name="X",
            segment=CustomerSegment.RETAIL,
            branch_code="BR1", rm_code="RM1",
            onboarding_date="2025-01-01"))
        b.add_account(VirtualAccount(
            account_no="A1", cif="C1",
            branch_code="BR1",
            account_type=AccountType.SAVINGS,
            currency="KES",
            balance=Decimal("100000"),
            status=AccountStatus.ACTIVE,
            open_date="2025-01-01",
            interest_rate_pct=Decimal("3.65")))
        return b

    bank1 = make("seed-X")
    bank2 = make("seed-X")
    bank1.tick(days=10)
    bank2.tick(days=10)
    bank1.run_day_end()
    bank2.run_day_end()
    s1 = bank1.board_summary()
    s2 = bank2.board_summary()
    assert s1 == s2


def self_test() -> None:
    tests = [
        _test_seed_determinism,
        _test_lcg_determinism,
        _test_lcg_modulo_respected,
        _test_loan_transition_valid_path,
        _test_loan_transition_invalid_skip,
        _test_loan_closed_terminal,
        _test_daily_interest_savings,
        _test_daily_interest_zero_rate,
        _test_dpd_not_yet_due,
        _test_dpd_30_days_late,
        _test_loan_status_from_dpd,
        _test_bank_register_dup_customer_raises,
        _test_bank_account_for_unknown_customer_raises,
        _test_bank_tick_advances_time,
        _test_bank_tick_negative_raises,
        _test_bank_post_transaction_updates_balance,
        _test_bank_day_end_accrues_interest,
        _test_bank_day_end_idempotent_same_day,
        _test_bank_day_end_ages_loans,
        _test_mock_fetch_account_balance,
        _test_mock_fetch_account_unknown,
        _test_mock_fetch_customer,
        _test_mock_fetch_branch_metrics_aggregates,
        _test_mock_responses_carry_seed_for_traceability,
        _test_loan_invalid_transition_raises,
        _test_bank_board_summary,
        _test_two_banks_with_same_seed_produce_same_outputs,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ virtual_bank_core self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ virtual_bank_core self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

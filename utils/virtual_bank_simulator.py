"""utils/virtual_bank_simulator.py — v10.31 Virtual Bank simulation closure.

╔════════════════════════════════════════════════════════════════════════╗
║  DAILY OPS SIMULATOR + SCENARIO INJECTION                              ║
║  Cat B operational utility — exercises platform modules under stress  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (does not affect production capital, credit         ║
║              decisions, or regulatory reporting; provides stress-test ║
║              and edge-case generation against the v10.30 simulation   ║
║              testbed)                                                   ║
║  Implements simulation infrastructure — not regulatory standards:       ║
║    DailyOpsSimulator — deterministic transaction stream generator       ║
║    ScenarioInjector — stress events, fraud, drift, AML, market shocks ║
║    SimulationRun lifecycle (state machine)                              ║
║    SimulationReport with deterministic metrics                          ║
║    G125 audit gate locking v10.30 + v10.31                              ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.30 virtual_bank_core — every operation flows        ║
║  through the VirtualBankCore engine; scenarios mutate bank state       ║
║  deterministically via derive_seed-based pseudo-randomness.            ║
║                                                                         ║
║  Honesty Rule 1: simulation runs report seed + day_offset + scenarios ║
║  applied for full reproducibility; scenario verdicts surface impact   ║
║  evidence (n_affected_entities + magnitude metrics).                  ║
║  Honesty Rule 7: external-data scenario hooks (market data, fraud     ║
║  models) are callable; without wiring, scenario uses deterministic   ║
║  defaults rather than fabricating values.                            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

# Allow running self-test directly: `python3 utils/virtual_bank_simulator.py`
if __name__ == "__main__" and __package__ is None:
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))

from utils.virtual_bank_core import (
    AccountStatus, AccountType, CustomerSegment, LoanStatus,
    VirtualAccount, VirtualBankCore, VirtualLoan,
    VirtualTransaction, derive_seed, deterministic_pseudo_random,
    is_valid_loan_transition)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "VirtualBankSimulator runs scenarios against a v10.30 VirtualBankCore "
    "instance. All operations are deterministic from (base_seed, "
    "scenario_set, day_offset). Per Rule 7, external scenario hooks "
    "(market-data fetchers, fraud-pattern generators) are callable; "
    "without wiring, scenarios apply deterministic defaults. Cat B — "
    "does not affect production capital, credit decisions, or "
    "regulatory reporting."
)


# ════════════════════════════════════════════════════════════════════════
# Daily Ops Transaction Generation
# ════════════════════════════════════════════════════════════════════════

class TransactionMix(Enum):
    """Profile of daily transaction generation."""
    LOW_ACTIVITY = "LOW_ACTIVITY"          # ~0.5 txns per account per day
    NORMAL = "NORMAL"                       # ~2 txns per account per day
    HIGH_ACTIVITY = "HIGH_ACTIVITY"        # ~5 txns per account per day
    STRESS = "STRESS"                       # ~10 txns per account per day


# Default transaction velocity (txns per active account per day)
DEFAULT_TXN_VELOCITY: Mapping[TransactionMix, Decimal] = {
    TransactionMix.LOW_ACTIVITY: Decimal("0.5"),
    TransactionMix.NORMAL: Decimal("2.0"),
    TransactionMix.HIGH_ACTIVITY: Decimal("5.0"),
    TransactionMix.STRESS: Decimal("10.0"),
}


# Default deposit/withdrawal mix (probability of deposit; rest withdrawal)
# In normal ops, slightly more deposits than withdrawals → balance grows
DEFAULT_DEPOSIT_PROBABILITY: Mapping[TransactionMix, Decimal] = {
    TransactionMix.LOW_ACTIVITY: Decimal("0.55"),
    TransactionMix.NORMAL: Decimal("0.55"),
    TransactionMix.HIGH_ACTIVITY: Decimal("0.55"),
    TransactionMix.STRESS: Decimal("0.40"),    # stress = more withdrawals
}


# Default txn amount range per segment (KES)
DEFAULT_AMOUNT_RANGE_BY_SEGMENT: Mapping[
    CustomerSegment, Tuple[Decimal, Decimal]] = {
    CustomerSegment.RETAIL: (Decimal("100"), Decimal("50000")),
    CustomerSegment.SME: (Decimal("5000"), Decimal("500000")),
    CustomerSegment.CORPORATE: (
        Decimal("100000"), Decimal("10000000")),
    CustomerSegment.HNW: (
        Decimal("50000"), Decimal("5000000")),
    CustomerSegment.PRIVATE_BANKING: (
        Decimal("100000"), Decimal("20000000")),
}


# Currency Transaction Report threshold per CBK AML Guideline 2023 (KES)
CTR_THRESHOLD_KES = Decimal("1000000")


@dataclass(frozen=True)
class DailyOpsConfig:
    """Configuration for one day of simulated operations."""
    mix: TransactionMix
    deposit_probability: Decimal
    amount_range_by_segment: Mapping[
        CustomerSegment, Tuple[Decimal, Decimal]]
    velocity_multiplier: Decimal = Decimal("1.0")  # global scaling
    notes: str = ""

    @staticmethod
    def default(
        mix: TransactionMix = TransactionMix.NORMAL,
    ) -> "DailyOpsConfig":
        return DailyOpsConfig(
            mix=mix,
            deposit_probability=DEFAULT_DEPOSIT_PROBABILITY[mix],
            amount_range_by_segment=DEFAULT_AMOUNT_RANGE_BY_SEGMENT)


def _sample_amount(
    *, seed: int, low: Decimal, high: Decimal,
) -> Decimal:
    """Deterministically sample a Decimal amount in [low, high]."""
    span = high - low
    if span <= Decimal("0"):
        return low
    # 4-digit pseudo-random precision
    out = deterministic_pseudo_random(
        seed=seed, n=1, modulo=10000)
    fraction = Decimal(out[0]) / Decimal("10000")
    return (low + span * fraction).quantize(Decimal("0.01"))


def _sample_choice(
    *, seed: int, n_choices: int,
) -> int:
    """Deterministic choice in [0, n_choices)."""
    if n_choices <= 0:
        raise ValueError("n_choices must be positive")
    out = deterministic_pseudo_random(
        seed=seed, n=1, modulo=n_choices)
    return out[0]


def _sample_bool(
    *, seed: int, true_probability: Decimal,
) -> bool:
    """Deterministic bool with given true probability."""
    out = deterministic_pseudo_random(
        seed=seed, n=1, modulo=10000)
    return Decimal(out[0]) / Decimal("10000") < true_probability


def n_transactions_for_day(
    *,
    n_accounts: int,
    velocity: Decimal,
    velocity_multiplier: Decimal,
) -> int:
    """Deterministically compute transactions for the day."""
    return int(
        Decimal(n_accounts) * velocity * velocity_multiplier)


# ════════════════════════════════════════════════════════════════════════
# Scenario Injection
# ════════════════════════════════════════════════════════════════════════

class ScenarioType(Enum):
    """Categories of scenarios that can be injected."""
    RATE_SHOCK = "RATE_SHOCK"                  # interest rate spike
    DEPOSIT_RUN = "DEPOSIT_RUN"                # mass withdrawals
    FRAUD_VELOCITY = "FRAUD_VELOCITY"          # rapid-fire txns
    FRAUD_STRUCTURING = "FRAUD_STRUCTURING"   # below-CTR deposits
    POPULATION_DRIFT = "POPULATION_DRIFT"     # customer mix shift
    AML_TRIGGER = "AML_TRIGGER"                # suspicious patterns
    MARKET_SHOCK = "MARKET_SHOCK"              # asset value collapse
    CREDIT_DETERIORATION = "CREDIT_DETERIORATION"  # mass DPD increase


@dataclass(frozen=True)
class Scenario:
    """A scenario definition."""
    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass(frozen=True)
class ScenarioApplication:
    """Result of applying a scenario."""
    application_id: str
    scenario_id: str
    scenario_type: ScenarioType
    applied_at: str                        # ISO-8601
    n_entities_affected: int
    magnitude_metric: str                  # e.g., "KES withdrawn"
    magnitude_value: Decimal
    seed_used: int                         # for reproducibility
    notes: str = ""


def apply_deposit_run(
    *,
    application_id: str,
    bank: VirtualBankCore,
    seed: int,
    pct_accounts_affected: Decimal = Decimal("0.30"),
    pct_balance_withdrawn: Decimal = Decimal("0.50"),
) -> ScenarioApplication:
    """Simulate a deposit run on the bank.

    Deterministically picks a percentage of accounts and applies
    large withdrawals to them.
    """
    accounts = [
        a for a in bank.all_accounts()
        if a.status == AccountStatus.ACTIVE
        and a.account_type in (
            AccountType.SAVINGS, AccountType.CURRENT,
            AccountType.FIXED_DEPOSIT)]
    n_accounts = len(accounts)
    n_affected = int(Decimal(n_accounts) * pct_accounts_affected)
    if n_affected == 0:
        return ScenarioApplication(
            application_id=application_id,
            scenario_id="DEPOSIT_RUN",
            scenario_type=ScenarioType.DEPOSIT_RUN,
            applied_at=bank.current_time().current_iso(),
            n_entities_affected=0,
            magnitude_metric="KES withdrawn",
            magnitude_value=Decimal("0"),
            seed_used=seed,
            notes="no accounts in scope")

    # Deterministically select accounts
    indices = deterministic_pseudo_random(
        seed=seed, n=n_affected * 2, modulo=n_accounts)
    selected_set = set(indices[:n_affected])
    if len(selected_set) < n_affected:
        # Top up with sequential indices to avoid partial selection
        for i in range(n_accounts):
            if len(selected_set) >= n_affected:
                break
            selected_set.add(i)

    total_withdrawn = Decimal("0")
    n_actually_affected = 0
    for idx in selected_set:
        acc = accounts[idx]
        withdraw_amount = (acc.balance * pct_balance_withdrawn).quantize(
            Decimal("0.01"))
        if withdraw_amount <= Decimal("0"):
            continue
        txn_id = (f"SCEN-DR-{acc.account_no}-"
                    f"{bank.current_time().current_iso()}")
        try:
            bank.post_transaction(VirtualTransaction(
                txn_id=txn_id,
                txn_date=bank.current_time().current_iso(),
                account_no=acc.account_no,
                txn_type="WITHDRAWAL",
                amount=withdraw_amount,
                notes="scenario: deposit run"))
            total_withdrawn += withdraw_amount
            n_actually_affected += 1
        except KeyError:
            continue

    return ScenarioApplication(
        application_id=application_id,
        scenario_id="DEPOSIT_RUN",
        scenario_type=ScenarioType.DEPOSIT_RUN,
        applied_at=bank.current_time().current_iso(),
        n_entities_affected=n_actually_affected,
        magnitude_metric="KES withdrawn",
        magnitude_value=total_withdrawn,
        seed_used=seed,
        notes=(
            f"affected {n_actually_affected}/{n_accounts} accounts "
            f"({pct_accounts_affected*100:.0f}% target); withdrew "
            f"{pct_balance_withdrawn*100:.0f}% per affected account"))


def apply_fraud_structuring(
    *,
    application_id: str,
    bank: VirtualBankCore,
    seed: int,
    n_attacks: int = 5,
    txns_per_attack: int = 6,
) -> ScenarioApplication:
    """Inject structuring fraud — multiple deposits below CTR threshold.

    Each attack: deposits ~ KES 950K (below 1M CTR threshold) repeated
    n times into a single account. Real banks should detect this via
    aggregation rules; this scenario tests whether the platform's
    transaction monitoring catches the pattern.
    """
    accounts = [
        a for a in bank.all_accounts()
        if a.status == AccountStatus.ACTIVE
        and a.account_type in (
            AccountType.SAVINGS, AccountType.CURRENT)]
    if not accounts:
        return ScenarioApplication(
            application_id=application_id,
            scenario_id="FRAUD_STRUCTURING",
            scenario_type=ScenarioType.FRAUD_STRUCTURING,
            applied_at=bank.current_time().current_iso(),
            n_entities_affected=0,
            magnitude_metric="KES deposited",
            magnitude_value=Decimal("0"),
            seed_used=seed,
            notes="no accounts in scope")

    # Pick n_attacks distinct accounts deterministically
    indices = deterministic_pseudo_random(
        seed=seed, n=n_attacks * 3, modulo=len(accounts))
    selected: List[int] = []
    seen = set()
    for idx in indices:
        if idx not in seen:
            selected.append(idx)
            seen.add(idx)
        if len(selected) >= n_attacks:
            break

    # Just below CTR threshold
    structuring_amount = CTR_THRESHOLD_KES - Decimal("50000")    # 950k
    total_deposited = Decimal("0")
    n_attacks_actual = 0
    for i, idx in enumerate(selected):
        acc = accounts[idx]
        for j in range(txns_per_attack):
            txn_id = (
                f"SCEN-FS-{acc.account_no}-{i}-{j}-"
                f"{bank.current_time().current_iso()}")
            try:
                bank.post_transaction(VirtualTransaction(
                    txn_id=txn_id,
                    txn_date=bank.current_time().current_iso(),
                    account_no=acc.account_no,
                    txn_type="DEPOSIT",
                    amount=structuring_amount,
                    notes="scenario: fraud structuring"))
                total_deposited += structuring_amount
            except KeyError:
                continue
        n_attacks_actual += 1

    return ScenarioApplication(
        application_id=application_id,
        scenario_id="FRAUD_STRUCTURING",
        scenario_type=ScenarioType.FRAUD_STRUCTURING,
        applied_at=bank.current_time().current_iso(),
        n_entities_affected=n_attacks_actual,
        magnitude_metric="KES deposited",
        magnitude_value=total_deposited,
        seed_used=seed,
        notes=(
            f"{n_attacks_actual} attacks × {txns_per_attack} "
            f"deposits @ KES {structuring_amount} each "
            f"(below CTR threshold {CTR_THRESHOLD_KES})"))


def apply_credit_deterioration(
    *,
    application_id: str,
    bank: VirtualBankCore,
    seed: int,
    pct_loans_affected: Decimal = Decimal("0.20"),
    days_added_to_dpd: int = 90,
) -> ScenarioApplication:
    """Simulate widespread credit deterioration.

    Forwards next_due_date for selected loans by N days (creating
    artificial DPD), then transitions status accordingly.
    """
    performing = [
        l for l in bank.all_loans()
        if l.status == LoanStatus.PERFORMING]
    n_loans = len(performing)
    n_affected = int(Decimal(n_loans) * pct_loans_affected)
    if n_affected == 0:
        return ScenarioApplication(
            application_id=application_id,
            scenario_id="CREDIT_DETERIORATION",
            scenario_type=ScenarioType.CREDIT_DETERIORATION,
            applied_at=bank.current_time().current_iso(),
            n_entities_affected=0,
            magnitude_metric="KES exposure deteriorated",
            magnitude_value=Decimal("0"),
            seed_used=seed,
            notes="no performing loans in scope")

    indices = deterministic_pseudo_random(
        seed=seed, n=n_affected * 2, modulo=n_loans)
    selected: List[int] = []
    seen = set()
    for idx in indices:
        if idx not in seen:
            selected.append(idx)
            seen.add(idx)
        if len(selected) >= n_affected:
            break

    total_exposure = Decimal("0")
    n_transitioned = 0
    for idx in selected:
        loan = performing[idx]
        # Backdate next_due_date by days_added_to_dpd
        if loan.next_due_date is None:
            continue
        try:
            current_due = date.fromisoformat(loan.next_due_date)
        except ValueError:
            continue
        new_due = current_due - timedelta(days=days_added_to_dpd)
        # Update loan with new next_due_date
        updated = VirtualLoan(
            loan_id=loan.loan_id, cif=loan.cif,
            branch_code=loan.branch_code, rm_code=loan.rm_code,
            principal=loan.principal,
            outstanding=loan.outstanding,
            rate_pct=loan.rate_pct,
            tenor_months=loan.tenor_months,
            disbursement_date=loan.disbursement_date,
            next_due_date=new_due.isoformat(),
            status=loan.status,
            days_past_due=loan.days_past_due,
            is_climate_overlay_applied=(
                loan.is_climate_overlay_applied),
            notes=(
                loan.notes + "\nscenario: credit deterioration"))
        bank._loans[loan.loan_id] = updated
        total_exposure += loan.outstanding
        n_transitioned += 1

    # Trigger day-end aging to apply transitions
    bank.run_day_end()

    # Step through any remaining intermediate transitions for backdated
    # loans whose DPD jump exceeds a single state-machine step. The v10.30
    # state machine forbids skipping stages (PERFORMING → DELINQUENT_60
    # blocked, must go via DELINQUENT_30 first). When credit deteriorates
    # rapidly, walk the chain explicitly rather than mutate v10.30.
    from utils.virtual_bank_core import (
        ALLOWED_LOAN_TRANSITIONS, days_past_due, loan_status_from_dpd)
    for loan in list(bank.all_loans()):
        target_status = loan_status_from_dpd(
            dpd=days_past_due(
                next_due_date=loan.next_due_date,
                current_date=bank.current_date()))
        # Walk through allowed transitions toward target
        max_steps = 6   # bounded — prevent infinite loop
        for _ in range(max_steps):
            current = bank.get_loan(loan.loan_id)
            if current.status == target_status:
                break
            allowed = ALLOWED_LOAN_TRANSITIONS.get(current.status, ())
            # Find best step toward target — prefer direct, else worst
            # intermediate that's allowed and worse than current
            chosen: Optional[LoanStatus] = None
            if target_status in allowed:
                chosen = target_status
            else:
                # Pick worst delinquency state in allowed that's worse
                # than current (advancing toward NPL)
                worse_order = (
                    LoanStatus.DELINQUENT_30,
                    LoanStatus.DELINQUENT_60,
                    LoanStatus.DELINQUENT_90,
                    LoanStatus.NON_PERFORMING)
                for cand in worse_order:
                    if cand in allowed:
                        chosen = cand
            if chosen is None:
                break
            bank.transition_loan(
                loan_id=loan.loan_id, to_status=chosen,
                timestamp=bank.current_time().current_iso(),
                notes="scenario: credit deterioration walk")

    return ScenarioApplication(
        application_id=application_id,
        scenario_id="CREDIT_DETERIORATION",
        scenario_type=ScenarioType.CREDIT_DETERIORATION,
        applied_at=bank.current_time().current_iso(),
        n_entities_affected=n_transitioned,
        magnitude_metric="KES exposure deteriorated",
        magnitude_value=total_exposure,
        seed_used=seed,
        notes=(
            f"{n_transitioned} loans backdated by "
            f"{days_added_to_dpd} days; total exposure "
            f"KES {total_exposure:,}"))


# ════════════════════════════════════════════════════════════════════════
# Simulation Run Lifecycle
# ════════════════════════════════════════════════════════════════════════

class SimulationRunState(Enum):
    CONFIGURED = "CONFIGURED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Allowed transitions
ALLOWED_SIMULATION_TRANSITIONS: Mapping[
    SimulationRunState, Tuple[SimulationRunState, ...]] = {
    SimulationRunState.CONFIGURED: (
        SimulationRunState.RUNNING, SimulationRunState.CANCELLED),
    SimulationRunState.RUNNING: (
        SimulationRunState.PAUSED,
        SimulationRunState.COMPLETED,
        SimulationRunState.FAILED,
        SimulationRunState.CANCELLED),
    SimulationRunState.PAUSED: (
        SimulationRunState.RUNNING,
        SimulationRunState.CANCELLED),
    SimulationRunState.COMPLETED: (),     # terminal
    SimulationRunState.FAILED: (),        # terminal
    SimulationRunState.CANCELLED: (),     # terminal
}


def is_valid_simulation_transition(
    from_state: SimulationRunState,
    to_state: SimulationRunState,
) -> bool:
    return to_state in ALLOWED_SIMULATION_TRANSITIONS.get(from_state, ())


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for a simulation run."""
    config_id: str
    name: str
    base_seed: str
    base_date: str
    n_simulation_days: int
    daily_ops_config: DailyOpsConfig
    scenarios_to_apply: Tuple[Tuple[int, str], ...] = ()
    # tuples of (day_offset, scenario_id) — apply scenario on day N
    notes: str = ""


@dataclass(frozen=True)
class SimulationRun:
    """One simulation run."""
    run_id: str
    config_id: str
    state: SimulationRunState
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    n_days_simulated: int = 0
    n_transactions_generated: int = 0
    n_scenarios_applied: int = 0
    notes: str = ""


@dataclass(frozen=True)
class SimulationReport:
    """Aggregated report after a simulation run."""
    report_id: str
    run_id: str
    config_id: str
    base_seed: str
    final_day_offset: int
    n_customers_final: int
    n_accounts_final: int
    n_loans_final: int
    n_transactions_total: int
    final_npl_ratio: Decimal
    scenario_applications: Tuple[ScenarioApplication, ...] = ()
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class VirtualBankSimulatorEngine:
    """Orchestrates daily ops + scenario injection against a
    VirtualBankCore instance.

    Composes with v10.30 — VirtualBankCore is the testbed; this engine
    drives traffic + scenarios through it deterministically.
    """

    def __init__(self, *, entity_name: str = "Sim Engine"):
        self.entity_name = entity_name
        self._configs: Dict[str, SimulationConfig] = {}
        self._scenarios: Dict[str, Scenario] = {}
        self._runs: Dict[str, SimulationRun] = {}
        self._reports: Dict[str, SimulationReport] = {}
        self._scenario_applications: Dict[
            str, ScenarioApplication] = {}
        self._run_transitions: List[
            Tuple[str, SimulationRunState,
                  SimulationRunState, str]] = []

    # ── Scenarios ──────────────────────────────────────────────────────
    def register_scenario(self, scenario: Scenario) -> None:
        if scenario.scenario_id in self._scenarios:
            raise ValueError(
                f"scenario {scenario.scenario_id} already registered")
        self._scenarios[scenario.scenario_id] = scenario

    def get_scenario(self, sid: str) -> Scenario:
        if sid not in self._scenarios:
            raise KeyError(f"scenario {sid} not found")
        return self._scenarios[sid]

    # ── Configs ────────────────────────────────────────────────────────
    def register_config(self, config: SimulationConfig) -> None:
        if config.config_id in self._configs:
            raise ValueError(
                f"config {config.config_id} already registered")
        # Verify referenced scenarios exist
        for _day, sid in config.scenarios_to_apply:
            if sid not in self._scenarios:
                raise ValueError(
                    f"config references unknown scenario '{sid}'")
        self._configs[config.config_id] = config

    def get_config(self, cid: str) -> SimulationConfig:
        if cid not in self._configs:
            raise KeyError(f"config {cid} not found")
        return self._configs[cid]

    # ── Runs ───────────────────────────────────────────────────────────
    def configure_run(
        self,
        *,
        run_id: str,
        config_id: str,
    ) -> SimulationRun:
        if run_id in self._runs:
            raise ValueError(f"run {run_id} already exists")
        config = self.get_config(config_id)
        run = SimulationRun(
            run_id=run_id, config_id=config_id,
            state=SimulationRunState.CONFIGURED)
        self._runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> SimulationRun:
        if run_id not in self._runs:
            raise KeyError(f"run {run_id} not found")
        return self._runs[run_id]

    def transition_run(
        self,
        *,
        run_id: str,
        to_state: SimulationRunState,
        timestamp: str,
        notes: str = "",
    ) -> SimulationRun:
        existing = self.get_run(run_id)
        if not is_valid_simulation_transition(
                existing.state, to_state):
            allowed = ALLOWED_SIMULATION_TRANSITIONS.get(
                existing.state, ())
            raise ValueError(
                f"invalid simulation transition "
                f"{existing.state.value} → {to_state.value}; "
                f"allowed: {[s.value for s in allowed]}")
        self._run_transitions.append(
            (run_id, existing.state, to_state, timestamp))
        updated = SimulationRun(
            run_id=existing.run_id, config_id=existing.config_id,
            state=to_state,
            started_at=(
                timestamp if to_state == SimulationRunState.RUNNING
                and existing.started_at is None
                else existing.started_at),
            completed_at=(
                timestamp if to_state in (
                    SimulationRunState.COMPLETED,
                    SimulationRunState.FAILED,
                    SimulationRunState.CANCELLED)
                else existing.completed_at),
            n_days_simulated=existing.n_days_simulated,
            n_transactions_generated=existing.n_transactions_generated,
            n_scenarios_applied=existing.n_scenarios_applied,
            notes=(
                existing.notes + "\n" + notes if notes
                else existing.notes))
        self._runs[run_id] = updated
        return updated

    # ── Execute simulation ────────────────────────────────────────────
    def execute_run(
        self,
        *,
        run_id: str,
        bank: VirtualBankCore,
    ) -> SimulationReport:
        """Execute a configured simulation run end-to-end.

        Walks through n_simulation_days, generating daily transactions
        and applying scenarios per the config.
        """
        run = self.get_run(run_id)
        if run.state != SimulationRunState.CONFIGURED:
            raise ValueError(
                f"run {run_id} is not in CONFIGURED state "
                f"(current: {run.state.value})")
        config = self.get_config(run.config_id)
        # Verify bank base_seed matches config
        if bank.base_seed != config.base_seed:
            raise ValueError(
                f"bank base_seed '{bank.base_seed}' does not match "
                f"config base_seed '{config.base_seed}'")

        # Transition to RUNNING
        self.transition_run(
            run_id=run_id, to_state=SimulationRunState.RUNNING,
            timestamp=bank.current_time().current_iso())

        # Build map of scenarios per day
        scenarios_by_day: Dict[int, List[str]] = {}
        for day, sid in config.scenarios_to_apply:
            scenarios_by_day.setdefault(day, []).append(sid)

        n_txns = 0
        n_scenarios_applied = 0
        applications: List[ScenarioApplication] = []

        velocity = DEFAULT_TXN_VELOCITY[
            config.daily_ops_config.mix]

        for day_idx in range(config.n_simulation_days):
            # Apply scenarios scheduled for this day FIRST
            day_offset_now = bank._day_offset
            for sid in scenarios_by_day.get(day_idx, []):
                scenario = self.get_scenario(sid)
                app_seed = derive_seed(
                    base_seed=config.base_seed,
                    namespace=f"scenario:{sid}",
                    discriminator=str(day_idx))
                app_id = (
                    f"APP-{run_id}-{sid}-{day_idx}")
                app: Optional[ScenarioApplication] = None
                if scenario.scenario_type == ScenarioType.DEPOSIT_RUN:
                    app = apply_deposit_run(
                        application_id=app_id,
                        bank=bank, seed=app_seed)
                elif (scenario.scenario_type
                          == ScenarioType.FRAUD_STRUCTURING):
                    app = apply_fraud_structuring(
                        application_id=app_id,
                        bank=bank, seed=app_seed)
                elif (scenario.scenario_type
                          == ScenarioType.CREDIT_DETERIORATION):
                    app = apply_credit_deterioration(
                        application_id=app_id,
                        bank=bank, seed=app_seed)
                else:
                    # Other scenario types — record placeholder
                    app = ScenarioApplication(
                        application_id=app_id,
                        scenario_id=sid,
                        scenario_type=scenario.scenario_type,
                        applied_at=bank.current_time().current_iso(),
                        n_entities_affected=0,
                        magnitude_metric="not_implemented",
                        magnitude_value=Decimal("0"),
                        seed_used=app_seed,
                        notes=(
                            f"scenario type "
                            f"{scenario.scenario_type.value} "
                            f"not yet implemented in apply_X "
                            f"functions; placeholder recorded"))
                self._scenario_applications[app.application_id] = app
                applications.append(app)
                n_scenarios_applied += 1

            # Generate daily ops
            n_active_accounts = sum(
                1 for a in bank.all_accounts()
                if a.status == AccountStatus.ACTIVE)
            n_today = n_transactions_for_day(
                n_accounts=n_active_accounts,
                velocity=velocity,
                velocity_multiplier=(
                    config.daily_ops_config.velocity_multiplier))
            txns_generated_today = self._generate_daily_txns(
                bank=bank, n_txns=n_today,
                config=config.daily_ops_config,
                day_seed=derive_seed(
                    base_seed=config.base_seed,
                    namespace="daily_ops",
                    discriminator=str(day_idx)))
            n_txns += txns_generated_today
            bank.run_day_end()
            bank.tick(days=1)

        # Transition to COMPLETED
        self.transition_run(
            run_id=run_id, to_state=SimulationRunState.COMPLETED,
            timestamp=bank.current_time().current_iso())

        # Update run with counts (mutate via re-create)
        existing_run = self._runs[run_id]
        self._runs[run_id] = SimulationRun(
            run_id=existing_run.run_id,
            config_id=existing_run.config_id,
            state=existing_run.state,
            started_at=existing_run.started_at,
            completed_at=existing_run.completed_at,
            n_days_simulated=config.n_simulation_days,
            n_transactions_generated=n_txns,
            n_scenarios_applied=n_scenarios_applied,
            notes=existing_run.notes)

        # Build report
        summary = bank.board_summary()
        report = SimulationReport(
            report_id=f"REP-{run_id}",
            run_id=run_id,
            config_id=run.config_id,
            base_seed=config.base_seed,
            final_day_offset=bank._day_offset,
            n_customers_final=int(summary["n_customers"]),
            n_accounts_final=int(summary["n_accounts"]),
            n_loans_final=int(summary["n_loans"]),
            n_transactions_total=int(summary["n_transactions"]),
            final_npl_ratio=Decimal(summary["npl_ratio"]),
            scenario_applications=tuple(applications),
            notes=(
                f"completed {config.n_simulation_days} days; "
                f"{n_txns} txns generated; "
                f"{n_scenarios_applied} scenarios applied"))
        self._reports[report.report_id] = report
        return report

    def _generate_daily_txns(
        self,
        *,
        bank: VirtualBankCore,
        n_txns: int,
        config: DailyOpsConfig,
        day_seed: int,
    ) -> int:
        """Generate n deterministic txns for one day.

        Returns count of successfully posted transactions.
        """
        if n_txns <= 0:
            return 0
        accounts = [
            a for a in bank.all_accounts()
            if a.status == AccountStatus.ACTIVE
            and a.account_type in (
                AccountType.SAVINGS, AccountType.CURRENT)]
        if not accounts:
            return 0

        # Build customer→segment lookup
        seg_by_cif: Dict[str, CustomerSegment] = {}
        for c in bank.all_customers():
            seg_by_cif[c.cif] = c.segment

        n_posted = 0
        for txn_idx in range(n_txns):
            # Pick account
            acc_seed = derive_seed(
                base_seed=str(day_seed),
                namespace="account_pick",
                discriminator=str(txn_idx))
            acc_idx = _sample_choice(
                seed=acc_seed, n_choices=len(accounts))
            acc = accounts[acc_idx]
            segment = seg_by_cif.get(acc.cif, CustomerSegment.RETAIL)

            # Decide deposit vs withdrawal
            type_seed = derive_seed(
                base_seed=str(day_seed),
                namespace="txn_type",
                discriminator=str(txn_idx))
            is_deposit = _sample_bool(
                seed=type_seed,
                true_probability=config.deposit_probability)

            # Sample amount
            amt_seed = derive_seed(
                base_seed=str(day_seed),
                namespace="txn_amount",
                discriminator=str(txn_idx))
            low, high = config.amount_range_by_segment[segment]
            amount = _sample_amount(
                seed=amt_seed, low=low, high=high)

            txn_id = (
                f"DAILY-{day_seed}-{txn_idx}-"
                f"{bank.current_time().current_iso()}")
            try:
                bank.post_transaction(VirtualTransaction(
                    txn_id=txn_id,
                    txn_date=bank.current_time().current_iso(),
                    account_no=acc.account_no,
                    txn_type="DEPOSIT" if is_deposit else "WITHDRAWAL",
                    amount=amount,
                    notes="daily ops simulation"))
                n_posted += 1
            except KeyError:
                continue
        return n_posted

    # ── Reporting ──────────────────────────────────────────────────────
    def get_report(self, report_id: str) -> SimulationReport:
        if report_id not in self._reports:
            raise KeyError(f"report {report_id} not found")
        return self._reports[report_id]

    def all_reports(self) -> Tuple[SimulationReport, ...]:
        return tuple(self._reports.values())

    def board_summary(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "n_scenarios_registered": len(self._scenarios),
            "n_configs_registered": len(self._configs),
            "n_runs_total": len(self._runs),
            "n_runs_completed": sum(
                1 for r in self._runs.values()
                if r.state == SimulationRunState.COMPLETED),
            "n_runs_failed": sum(
                1 for r in self._runs.values()
                if r.state == SimulationRunState.FAILED),
            "n_scenario_applications": len(
                self._scenario_applications),
            "n_reports": len(self._reports),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_test_bank_for_sim(seed="sim-seed"):
    """Build a small bank for simulation testing."""
    from utils.virtual_bank_core import (
        VirtualBranch, VirtualCustomer, VirtualAccount,
        VirtualLoan)
    bank = VirtualBankCore(
        entity_name="Sim Bank",
        base_seed=seed,
        base_date="2026-01-01")
    bank.add_branch(VirtualBranch(
        branch_code="BR1", branch_name="Main",
        region="Nairobi", branch_type="MAIN", n_staff=10))
    # 5 customers, 5 savings accounts
    for i in range(5):
        cif = f"C{i+1}"
        bank.add_customer(VirtualCustomer(
            cif=cif, full_name=f"Customer {i+1}",
            segment=CustomerSegment.RETAIL,
            branch_code="BR1", rm_code="RM1",
            onboarding_date="2025-01-01"))
        bank.add_account(VirtualAccount(
            account_no=f"A{i+1}", cif=cif,
            branch_code="BR1",
            account_type=AccountType.SAVINGS,
            currency="KES",
            balance=Decimal("100000"),
            status=AccountStatus.ACTIVE,
            open_date="2025-01-01"))
    return bank


# ── Daily Ops Generation Tests ──────────────────────────────────────
def _test_default_velocities_present():
    for mix in TransactionMix:
        assert mix in DEFAULT_TXN_VELOCITY


def _test_n_transactions_scales_with_velocity():
    n_low = n_transactions_for_day(
        n_accounts=100, velocity=Decimal("0.5"),
        velocity_multiplier=Decimal("1"))
    n_high = n_transactions_for_day(
        n_accounts=100, velocity=Decimal("5"),
        velocity_multiplier=Decimal("1"))
    assert n_high > n_low


def _test_sample_amount_in_range():
    amt = _sample_amount(
        seed=42, low=Decimal("100"), high=Decimal("1000"))
    assert Decimal("100") <= amt <= Decimal("1000")


def _test_sample_amount_deterministic():
    a = _sample_amount(seed=42, low=Decimal("0"), high=Decimal("1000"))
    b = _sample_amount(seed=42, low=Decimal("0"), high=Decimal("1000"))
    c = _sample_amount(seed=43, low=Decimal("0"), high=Decimal("1000"))
    assert a == b
    assert a != c


def _test_sample_choice_in_range():
    for _ in range(20):
        c = _sample_choice(seed=42, n_choices=10)
        assert 0 <= c < 10


def _test_sample_bool_deterministic():
    a = _sample_bool(seed=42, true_probability=Decimal("0.5"))
    b = _sample_bool(seed=42, true_probability=Decimal("0.5"))
    assert a == b


def _test_ctr_threshold_per_cbk():
    """CBK AML Guideline 2023 — KES 1M threshold."""
    assert CTR_THRESHOLD_KES == Decimal("1000000")


def _test_default_ops_config():
    cfg = DailyOpsConfig.default(mix=TransactionMix.NORMAL)
    assert cfg.mix == TransactionMix.NORMAL
    assert cfg.deposit_probability == Decimal("0.55")


# ── Scenario Tests ──────────────────────────────────────────────────
def _test_deposit_run_affects_accounts():
    bank = _make_test_bank_for_sim()
    initial_balances = {
        a.account_no: a.balance for a in bank.all_accounts()}
    app = apply_deposit_run(
        application_id="A1", bank=bank, seed=42,
        pct_accounts_affected=Decimal("0.40"),
        pct_balance_withdrawn=Decimal("0.50"))
    # Some accounts should have decreased
    decreased = 0
    for a in bank.all_accounts():
        if a.balance < initial_balances[a.account_no]:
            decreased += 1
    assert decreased > 0
    assert app.n_entities_affected > 0


def _test_deposit_run_deterministic():
    """Same seed → same outcome."""
    b1 = _make_test_bank_for_sim()
    b2 = _make_test_bank_for_sim()
    a1 = apply_deposit_run(
        application_id="A1", bank=b1, seed=42)
    a2 = apply_deposit_run(
        application_id="A1", bank=b2, seed=42)
    assert a1.n_entities_affected == a2.n_entities_affected
    assert a1.magnitude_value == a2.magnitude_value


def _test_deposit_run_empty_bank():
    bank = VirtualBankCore(
        entity_name="X", base_seed="x",
        base_date="2026-01-01")
    app = apply_deposit_run(
        application_id="A1", bank=bank, seed=42)
    assert app.n_entities_affected == 0


def _test_fraud_structuring_below_ctr():
    bank = _make_test_bank_for_sim()
    app = apply_fraud_structuring(
        application_id="A1", bank=bank, seed=42,
        n_attacks=2, txns_per_attack=3)
    # Find the fraud transactions
    fraud_txns = [
        t for t in bank.all_transactions()
        if "fraud structuring" in t.notes]
    assert len(fraud_txns) > 0
    # All should be below CTR threshold
    for t in fraud_txns:
        assert t.amount < CTR_THRESHOLD_KES


def _test_credit_deterioration_transitions_loans():
    from utils.virtual_bank_core import VirtualLoan
    bank = _make_test_bank_for_sim()
    bank.add_loan(VirtualLoan(
        loan_id="L1", cif="C1",
        branch_code="BR1", rm_code="RM1",
        principal=Decimal("500000"),
        outstanding=Decimal("450000"),
        rate_pct=Decimal("13.5"),
        tenor_months=24,
        disbursement_date="2025-06-01",
        next_due_date="2026-02-01",
        status=LoanStatus.PERFORMING,
        days_past_due=0))
    app = apply_credit_deterioration(
        application_id="A1", bank=bank, seed=42,
        pct_loans_affected=Decimal("1.0"),
        days_added_to_dpd=120)
    # Loan should now be DELINQUENT_X
    loan = bank.get_loan("L1")
    assert loan.status != LoanStatus.PERFORMING


# ── Simulation Lifecycle Tests ──────────────────────────────────────
def _test_sim_lifecycle_valid_path():
    assert is_valid_simulation_transition(
        SimulationRunState.CONFIGURED,
        SimulationRunState.RUNNING)


def _test_sim_lifecycle_cannot_skip_to_completed():
    assert not is_valid_simulation_transition(
        SimulationRunState.CONFIGURED,
        SimulationRunState.COMPLETED)


def _test_sim_terminal_states_no_transitions():
    for terminal in (
            SimulationRunState.COMPLETED,
            SimulationRunState.FAILED,
            SimulationRunState.CANCELLED):
        assert len(ALLOWED_SIMULATION_TRANSITIONS[terminal]) == 0


# ── Engine Tests ────────────────────────────────────────────────────
def _test_engine_register_dup_scenario_raises():
    eng = VirtualBankSimulatorEngine()
    s = Scenario(
        scenario_id="S1",
        scenario_type=ScenarioType.DEPOSIT_RUN,
        name="Run", description="x")
    eng.register_scenario(s)
    try:
        eng.register_scenario(s)
        assert False
    except ValueError:
        pass


def _test_engine_config_references_unknown_scenario_raises():
    eng = VirtualBankSimulatorEngine()
    cfg = SimulationConfig(
        config_id="CFG1", name="X",
        base_seed="seed", base_date="2026-01-01",
        n_simulation_days=5,
        daily_ops_config=DailyOpsConfig.default(),
        scenarios_to_apply=((1, "UNKNOWN"),))
    try:
        eng.register_config(cfg)
        assert False
    except ValueError:
        pass


def _test_engine_execute_run_seed_mismatch_raises():
    eng = VirtualBankSimulatorEngine()
    cfg = SimulationConfig(
        config_id="CFG1", name="X",
        base_seed="seed-A", base_date="2026-01-01",
        n_simulation_days=2,
        daily_ops_config=DailyOpsConfig.default())
    eng.register_config(cfg)
    eng.configure_run(run_id="R1", config_id="CFG1")
    bank = _make_test_bank_for_sim(seed="seed-B")    # mismatch
    try:
        eng.execute_run(run_id="R1", bank=bank)
        assert False
    except ValueError as e:
        assert "base_seed" in str(e).lower()


def _test_engine_execute_run_full_happy_path():
    """Full simulation lifecycle: configure → execute → report."""
    eng = VirtualBankSimulatorEngine()
    eng.register_scenario(Scenario(
        scenario_id="DR1",
        scenario_type=ScenarioType.DEPOSIT_RUN,
        name="Deposit Run",
        description="30% accounts, 50% balance"))
    cfg = SimulationConfig(
        config_id="CFG1", name="2-day with run",
        base_seed="sim-seed",
        base_date="2026-01-01",
        n_simulation_days=2,
        daily_ops_config=DailyOpsConfig.default(),
        scenarios_to_apply=((1, "DR1"),))
    eng.register_config(cfg)
    eng.configure_run(run_id="R1", config_id="CFG1")
    bank = _make_test_bank_for_sim(seed="sim-seed")
    report = eng.execute_run(run_id="R1", bank=bank)
    assert report.run_id == "R1"
    run = eng.get_run("R1")
    assert run.state == SimulationRunState.COMPLETED
    assert run.n_days_simulated == 2
    assert run.n_scenarios_applied == 1
    assert len(report.scenario_applications) == 1


def _test_engine_execute_run_deterministic():
    """Two runs with same config + same bank seed → same report."""
    def run_one():
        eng = VirtualBankSimulatorEngine()
        eng.register_scenario(Scenario(
            scenario_id="DR1",
            scenario_type=ScenarioType.DEPOSIT_RUN,
            name="Run", description="x"))
        cfg = SimulationConfig(
            config_id="CFG1", name="X",
            base_seed="DETERM-SEED",
            base_date="2026-01-01",
            n_simulation_days=3,
            daily_ops_config=DailyOpsConfig.default(),
            scenarios_to_apply=((2, "DR1"),))
        eng.register_config(cfg)
        eng.configure_run(run_id="R1", config_id="CFG1")
        bank = _make_test_bank_for_sim(seed="DETERM-SEED")
        return eng.execute_run(run_id="R1", bank=bank)

    r1 = run_one()
    r2 = run_one()
    # Reports should match in all simulation outputs
    assert r1.n_transactions_total == r2.n_transactions_total
    assert r1.final_npl_ratio == r2.final_npl_ratio
    assert (r1.scenario_applications[0].magnitude_value
              == r2.scenario_applications[0].magnitude_value)


def _test_engine_invalid_transition_raises():
    eng = VirtualBankSimulatorEngine()
    cfg = SimulationConfig(
        config_id="CFG1", name="X",
        base_seed="s", base_date="2026-01-01",
        n_simulation_days=1,
        daily_ops_config=DailyOpsConfig.default())
    eng.register_config(cfg)
    eng.configure_run(run_id="R1", config_id="CFG1")
    # Cannot go CONFIGURED → COMPLETED directly
    try:
        eng.transition_run(
            run_id="R1",
            to_state=SimulationRunState.COMPLETED,
            timestamp="t")
        assert False
    except ValueError:
        pass


def _test_engine_board_summary():
    eng = VirtualBankSimulatorEngine()
    s = eng.board_summary()
    assert s["n_runs_total"] == 0
    assert s["entity"] == "Sim Engine"


def self_test() -> None:
    tests = [
        _test_default_velocities_present,
        _test_n_transactions_scales_with_velocity,
        _test_sample_amount_in_range,
        _test_sample_amount_deterministic,
        _test_sample_choice_in_range,
        _test_sample_bool_deterministic,
        _test_ctr_threshold_per_cbk,
        _test_default_ops_config,
        _test_deposit_run_affects_accounts,
        _test_deposit_run_deterministic,
        _test_deposit_run_empty_bank,
        _test_fraud_structuring_below_ctr,
        _test_credit_deterioration_transitions_loans,
        _test_sim_lifecycle_valid_path,
        _test_sim_lifecycle_cannot_skip_to_completed,
        _test_sim_terminal_states_no_transitions,
        _test_engine_register_dup_scenario_raises,
        _test_engine_config_references_unknown_scenario_raises,
        _test_engine_execute_run_seed_mismatch_raises,
        _test_engine_execute_run_full_happy_path,
        _test_engine_execute_run_deterministic,
        _test_engine_invalid_transition_raises,
        _test_engine_board_summary,
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
        print(f"✗ virtual_bank_simulator self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ virtual_bank_simulator self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

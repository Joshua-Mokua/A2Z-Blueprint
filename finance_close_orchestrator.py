"""utils/finance_close_orchestrator.py — v10.59: Continuous Close.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-249 — Continuous Close Orchestration Engine                        ║
║  Cat B — finance arc opening (13th arc opened on platform)              ║
╠════════════════════════════════════════════════════════════════════════╣
║  Diagnostic close-readiness engine. Targets <3 day close per Gartner    ║
║  research; does NOT itself close the period. Surfaces what would need   ║
║  to be done — recurring accruals not yet booked, prepayments due for    ║
║  amortization, intercompany entries with no offsetting side,            ║
║  uncleared suspense balances, transactions posted in the wrong period.  ║
║                                                                          ║
║  Five detection capabilities:                                            ║
║    1. MISSING RECURRING ACCRUALS — schedule says monthly amount X       ║
║       hits account Y; current period has no posting matching that       ║
║       schedule → recommend accrual journal                              ║
║    2. PREPAYMENT AMORTIZATION DUE — prepayment schedule says            ║
║       periodic amount Y in current period not yet booked →              ║
║       recommend amortization journal                                    ║
║    3. INTERCOMPANY PENDING — IC entry posted on one entity's books     ║
║       with no offsetting side on counter-entity (intra-group flag)      ║
║    4. SUSPENSE BALANCE — accounts flagged is_suspense=True with         ║
║       non-zero net at period end → must be cleared before close         ║
║    5. CUTOFF TIMING — entries with posting_date inside period N        ║
║       but reference invoice/receipt dates significantly outside it      ║
║       → potential period misallocation                                  ║
║                                                                          ║
║  Per Rule 7, engine is purely DIAGNOSTIC. It NEVER:                    ║
║    - posts journals (recommends them; humans approve and post)         ║
║    - closes the period                                                  ║
║    - auto-clears suspense balances                                      ║
║    - reverses entries                                                   ║
║    - mutates GL records (frozen dataclasses)                            ║
║                                                                          ║
║  Per Rule 1, every CloseTask surfaces task_id + task_type + severity + ║
║  period + account_code + recommended_debit + recommended_credit +       ║
║  description + related_ids + framework_refs.                            ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - intercompany_matching (ENH-250 — to-be-built; orchestrator can    ║
║      consume IC matching engine output if available)                    ║
║    - group_consolidation (ENH-251 — to-be-built; close_report           ║
║      indicates readiness state for consolidation step)                  ║
║    - regulatory_revenue_reporting (ENH-248) — close completeness is    ║
║      a precondition to statutory reporting                              ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "FinanceCloseOrchestrator implements ENH-249 — opens the "
    "finance arc (13th arc opened). Pure stdlib (Decimal + "
    "dataclasses + enums). Per Rule 1, every CloseTask surfaces "
    "task_id + type + severity + period + account_code + "
    "recommended D/C + description + related_ids + framework "
    "refs. Per Rule 7, engine is DIAGNOSTIC ONLY — recommends "
    "journals, never posts; flags close gaps, never closes "
    "period; flags suspense balances, never clears them. "
    "Targets <3 day close per Gartner finance research but "
    "leaves all execution to operator review."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class CloseTaskType(Enum):
    """The five detection capabilities."""
    MISSING_RECURRING_ACCRUAL = "MISSING_RECURRING_ACCRUAL"
    PREPAYMENT_AMORTIZATION_DUE = "PREPAYMENT_AMORTIZATION_DUE"
    INTERCOMPANY_PENDING = "INTERCOMPANY_PENDING"
    SUSPENSE_BALANCE = "SUSPENSE_BALANCE"
    CUTOFF_TIMING = "CUTOFF_TIMING"


class CloseTaskSeverity(Enum):
    CRITICAL = "CRITICAL"   # blocks close
    HIGH = "HIGH"           # likely blocks close, needs review
    MEDIUM = "MEDIUM"       # should be addressed but not blocker
    LOW = "LOW"             # informational


class CloseTaskStatus(Enum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    BLOCKED = "BLOCKED"     # engine can't recommend without more data


class AccountType(Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class AccrualFrequency(Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CloseAccount:
    """Chart of accounts entry with close-relevant flags."""
    account_code: str
    account_name: str
    account_type: AccountType
    is_suspense: bool = False
    is_intercompany: bool = False
    requires_period_reconciliation: bool = False
    entity_id: str = ""    # entity owning the account (for IC pairing)

    def __post_init__(self) -> None:
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if not self.account_name:
            raise ValueError("account_name must be non-empty")


@dataclass(frozen=True)
class GLEntry:
    """One general ledger posting."""
    entry_id: str
    account_code: str
    debit_kes: Decimal
    credit_kes: Decimal
    posting_date: date
    period: str               # "YYYY-MM"
    reference: str = ""       # e.g. invoice ID, receipt ID
    counterparty_entity_id: str = ""   # for IC entries
    schedule_id: str = ""     # links to recurring/prepayment

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not self.account_code:
            raise ValueError("account_code must be non-empty")
        if self.debit_kes < 0 or self.credit_kes < 0:
            raise ValueError("D/C amounts must be ≥ 0")
        if self.debit_kes > 0 and self.credit_kes > 0:
            raise ValueError(
                "GLEntry must be debit OR credit, not both")
        if self.debit_kes == 0 and self.credit_kes == 0:
            raise ValueError(
                "GLEntry must have a non-zero amount")


@dataclass(frozen=True)
class RecurringAccrualSchedule:
    """Defines an expected recurring accrual."""
    schedule_id: str
    account_code: str
    periodic_amount_kes: Decimal
    frequency: AccrualFrequency
    contra_account_code: str
    description: str = ""
    effective_from_period: str = ""   # "YYYY-MM"
    effective_to_period: str = ""     # "YYYY-MM" or empty for open

    def __post_init__(self) -> None:
        if not self.schedule_id:
            raise ValueError("schedule_id must be non-empty")
        if self.periodic_amount_kes <= 0:
            raise ValueError(
                "periodic_amount_kes must be > 0")


@dataclass(frozen=True)
class PrepaymentSchedule:
    """Defines a prepaid expense amortization schedule."""
    schedule_id: str
    prepaid_account_code: str
    expense_account_code: str
    total_amount_kes: Decimal
    periodic_amount_kes: Decimal
    start_period: str        # "YYYY-MM"
    end_period: str          # "YYYY-MM"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.schedule_id:
            raise ValueError("schedule_id must be non-empty")
        if self.periodic_amount_kes <= 0:
            raise ValueError(
                "periodic_amount_kes must be > 0")
        if self.total_amount_kes <= 0:
            raise ValueError(
                "total_amount_kes must be > 0")
        if self.end_period < self.start_period:
            raise ValueError(
                "end_period must be ≥ start_period")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CloseTask:
    """One close-readiness gap or recommendation."""
    task_id: str
    task_type: CloseTaskType
    severity: CloseTaskSeverity
    status: CloseTaskStatus
    period: str
    account_code: str
    recommended_debit_kes: Optional[Decimal]
    recommended_credit_kes: Optional[Decimal]
    contra_account_code: Optional[str]
    description: str
    related_ids: Tuple[str, ...]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CloseReadinessReport:
    period: str
    target_close_days: int
    tasks: Tuple[CloseTask, ...]
    by_task_type: Dict[str, int]
    by_severity: Dict[str, int]
    ready_for_review_count: int
    blocked_count: int
    accounts_scanned: int
    entries_scanned: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class FinanceCloseOrchestrator:
    """Diagnostic continuous-close orchestrator.

    Per Rule 7, engine NEVER:
      - posts journals (recommends only)
      - closes the period
      - auto-clears suspense
      - reverses entries
      - mutates GL records (frozen dataclasses prevent this)

    Per Rule 1, every CloseTask carries enough context for an
    operator to action — period + account + recommended D/C +
    related IDs + framework refs.
    """

    DEFAULT_TARGET_CLOSE_DAYS: int = 3
    DEFAULT_CUTOFF_LAG_DAYS_THRESHOLD: int = 7

    # ── Capability 1: missing recurring accruals ─────────────────────
    def detect_missing_recurring_accruals(
        self,
        schedules: Sequence[RecurringAccrualSchedule],
        entries: Sequence[GLEntry],
        period: str,
    ) -> Tuple[CloseTask, ...]:
        """For each schedule active in `period`, check whether at
        least one matching entry exists in `period` for that
        schedule_id. Missing → recommend accrual."""
        # Index entries by (schedule_id, period)
        schedule_periods: Dict[Tuple[str, str], bool] = {}
        for e in entries:
            if not e.schedule_id:
                continue
            schedule_periods[(e.schedule_id, e.period)] = True

        tasks: List[CloseTask] = []
        for sched in schedules:
            if sched.effective_from_period and (
                    period < sched.effective_from_period):
                continue
            if sched.effective_to_period and (
                    period > sched.effective_to_period):
                continue
            if not self._is_period_due(period, sched.frequency):
                continue
            if (sched.schedule_id, period) in schedule_periods:
                continue
            # Missing — recommend accrual.
            tasks.append(CloseTask(
                task_id=(
                    f"FCO-ACC-{sched.schedule_id}-{period}"),
                task_type=(
                    CloseTaskType.MISSING_RECURRING_ACCRUAL),
                severity=CloseTaskSeverity.HIGH,
                status=CloseTaskStatus.READY_FOR_REVIEW,
                period=period,
                account_code=sched.account_code,
                recommended_debit_kes=sched.periodic_amount_kes,
                recommended_credit_kes=None,
                contra_account_code=sched.contra_account_code,
                description=(
                    f"recurring accrual {sched.schedule_id} "
                    f"({sched.frequency.value}) not posted for "
                    f"{period} — recommend "
                    f"{sched.periodic_amount_kes} to "
                    f"{sched.account_code} / "
                    f"{sched.contra_account_code}"),
                related_ids=(sched.schedule_id,),
                framework_refs=(
                    "ENH-249 §missing_accrual",
                    "Gartner continuous close — recurring "
                    "accruals automated via schedule library")))
        return tuple(tasks)

    @staticmethod
    def _is_period_due(
        period: str, frequency: AccrualFrequency,
    ) -> bool:
        """Cheap check on whether the period matches frequency.
        Treats period strings as YYYY-MM. Quarterly → months
        3/6/9/12; annual → month 12."""
        if frequency == AccrualFrequency.MONTHLY:
            return True
        if "-" not in period:
            return True
        try:
            month = int(period.split("-")[1])
        except (ValueError, IndexError):
            return True
        if frequency == AccrualFrequency.QUARTERLY:
            return month in (3, 6, 9, 12)
        if frequency == AccrualFrequency.ANNUAL:
            return month == 12
        return True

    # ── Capability 2: prepayment amortization due ────────────────────
    def detect_prepayment_amortization_due(
        self,
        schedules: Sequence[PrepaymentSchedule],
        entries: Sequence[GLEntry],
        period: str,
    ) -> Tuple[CloseTask, ...]:
        """For each prepayment schedule active in `period`, check
        whether amortization for `period` has been booked.
        Missing → recommend amortization journal."""
        booked: Dict[Tuple[str, str], bool] = {}
        for e in entries:
            if not e.schedule_id:
                continue
            booked[(e.schedule_id, e.period)] = True

        tasks: List[CloseTask] = []
        for sched in schedules:
            if period < sched.start_period:
                continue
            if period > sched.end_period:
                continue
            if (sched.schedule_id, period) in booked:
                continue
            tasks.append(CloseTask(
                task_id=(
                    f"FCO-PRE-{sched.schedule_id}-{period}"),
                task_type=(
                    CloseTaskType.PREPAYMENT_AMORTIZATION_DUE),
                severity=CloseTaskSeverity.HIGH,
                status=CloseTaskStatus.READY_FOR_REVIEW,
                period=period,
                account_code=sched.expense_account_code,
                recommended_debit_kes=sched.periodic_amount_kes,
                recommended_credit_kes=None,
                contra_account_code=sched.prepaid_account_code,
                description=(
                    f"prepayment {sched.schedule_id} "
                    f"amortization due for {period} — "
                    f"recommend Dr {sched.expense_account_code} "
                    f"/ Cr {sched.prepaid_account_code} for "
                    f"{sched.periodic_amount_kes}"),
                related_ids=(sched.schedule_id,),
                framework_refs=(
                    "ENH-249 §prepayment_amortization",
                    "IFRS — prepaid expense recognition over "
                    "service period")))
        return tuple(tasks)

    # ── Capability 3: intercompany pending ───────────────────────────
    def detect_intercompany_pending(
        self,
        accounts: Sequence[CloseAccount],
        entries: Sequence[GLEntry],
        period: str,
    ) -> Tuple[CloseTask, ...]:
        """Surface IC entries posted on one entity's books with no
        offsetting side on the counter-entity for the same period.
        Engine recognises pairs by (account_code, period,
        reference) — same reference but no offsetting side."""
        ic_accounts = {
            a.account_code for a in accounts if a.is_intercompany}

        # Index entries by (reference, period, side)
        # side determined by debit/credit
        by_ref: Dict[
            Tuple[str, str], Dict[str, List[GLEntry]]] = {}
        for e in entries:
            if e.account_code not in ic_accounts:
                continue
            if e.period != period:
                continue
            if not e.reference:
                continue   # cannot pair without reference
            key = (e.reference, e.period)
            side = "Dr" if e.debit_kes > 0 else "Cr"
            by_ref.setdefault(
                key, {"Dr": [], "Cr": []})[side].append(e)

        tasks: List[CloseTask] = []
        for (ref, p), sides in by_ref.items():
            dr_total = sum(
                (e.debit_kes for e in sides["Dr"]),
                Decimal("0"))
            cr_total = sum(
                (e.credit_kes for e in sides["Cr"]),
                Decimal("0"))
            if dr_total == 0 and cr_total == 0:
                continue   # impossible by construction
            if dr_total == cr_total:
                continue   # paired ✓
            # Net imbalance → pending.
            unpaired_side_entries = (
                sides["Dr"] if dr_total > cr_total
                else sides["Cr"])
            unpaired_account = (
                unpaired_side_entries[0].account_code
                if unpaired_side_entries else "")
            counterparty = (
                unpaired_side_entries[0].counterparty_entity_id
                if unpaired_side_entries else "")
            tasks.append(CloseTask(
                task_id=f"FCO-ICP-{ref}-{p}",
                task_type=CloseTaskType.INTERCOMPANY_PENDING,
                severity=CloseTaskSeverity.HIGH,
                status=CloseTaskStatus.READY_FOR_REVIEW,
                period=p,
                account_code=unpaired_account,
                recommended_debit_kes=None,
                recommended_credit_kes=None,
                contra_account_code=None,
                description=(
                    f"IC reference {ref} unbalanced for {p}: "
                    f"Dr {dr_total} vs Cr {cr_total} "
                    f"(counterparty {counterparty or 'unknown'}) "
                    f"— offsetting side missing on counter-entity"),
                related_ids=tuple(
                    e.entry_id for e in
                    sides["Dr"] + sides["Cr"]),
                framework_refs=(
                    "ENH-249 §intercompany_pending",
                    "IFRS 10 — intra-group balances eliminate at "
                    "consolidation; both sides must exist first")))
        return tuple(tasks)

    # ── Capability 4: suspense balances ──────────────────────────────
    def detect_suspense_balances(
        self,
        accounts: Sequence[CloseAccount],
        entries: Sequence[GLEntry],
        period: str,
    ) -> Tuple[CloseTask, ...]:
        """Surface suspense accounts with non-zero net balance at
        period end."""
        suspense_codes = {
            a.account_code for a in accounts if a.is_suspense}
        by_account: Dict[str, Decimal] = {}
        for e in entries:
            if e.account_code not in suspense_codes:
                continue
            if e.period > period:
                continue   # haven't happened yet
            net = (
                by_account.get(e.account_code, Decimal("0"))
                + e.debit_kes - e.credit_kes)
            by_account[e.account_code] = net

        tasks: List[CloseTask] = []
        for account_code, net in by_account.items():
            if net == 0:
                continue
            account = next(
                a for a in accounts
                if a.account_code == account_code)
            tasks.append(CloseTask(
                task_id=f"FCO-SUS-{account_code}-{period}",
                task_type=CloseTaskType.SUSPENSE_BALANCE,
                severity=CloseTaskSeverity.CRITICAL,
                status=CloseTaskStatus.READY_FOR_REVIEW,
                period=period,
                account_code=account_code,
                recommended_debit_kes=None,
                recommended_credit_kes=None,
                contra_account_code=None,
                description=(
                    f"suspense account {account_code} "
                    f"({account.account_name}) net balance "
                    f"{net} at end of {period} — must clear "
                    f"before close"),
                related_ids=(account_code,),
                framework_refs=(
                    "ENH-249 §suspense_balance",
                    "Period close — all suspense accounts must "
                    "be at zero before close certification")))
        return tuple(tasks)

    # ── Capability 5: cutoff timing ──────────────────────────────────
    def detect_cutoff_timing(
        self,
        entries: Sequence[GLEntry],
        period: str,
        period_start_date: date,
        period_end_date: date,
        lag_days_threshold: int = DEFAULT_CUTOFF_LAG_DAYS_THRESHOLD,
        reference_dates: Optional[Dict[str, date]] = None,
    ) -> Tuple[CloseTask, ...]:
        """Flag entries with `posting_date` inside [period_start,
        period_end] but reference_date significantly outside.
        Caller supplies reference_dates dict (entry's invoice/
        receipt date) since GLEntry only carries posting date.
        Rule 7: engine flags timing — humans decide whether to
        reverse/repost."""
        ref_map = reference_dates or {}
        tasks: List[CloseTask] = []
        for e in entries:
            if e.period != period:
                continue
            ref_d = ref_map.get(e.entry_id)
            if ref_d is None:
                continue
            # Significantly before period start?
            lag_before = (
                period_start_date.toordinal()
                - ref_d.toordinal())
            lag_after = (
                ref_d.toordinal()
                - period_end_date.toordinal())
            if (lag_before <= lag_days_threshold
                    and lag_after <= lag_days_threshold):
                continue
            severity = (
                CloseTaskSeverity.HIGH
                if max(lag_before, lag_after) > 30
                else CloseTaskSeverity.MEDIUM)
            tasks.append(CloseTask(
                task_id=f"FCO-CUT-{e.entry_id}",
                task_type=CloseTaskType.CUTOFF_TIMING,
                severity=severity,
                status=CloseTaskStatus.READY_FOR_REVIEW,
                period=period,
                account_code=e.account_code,
                recommended_debit_kes=None,
                recommended_credit_kes=None,
                contra_account_code=None,
                description=(
                    f"entry {e.entry_id} posted in {period} but "
                    f"reference date {ref_d.isoformat()} is "
                    f"{max(lag_before, lag_after)} day(s) "
                    f"outside the period window — potential "
                    f"period misallocation"),
                related_ids=(e.entry_id,),
                framework_refs=(
                    "ENH-249 §cutoff_timing",
                    "IAS 1 — accrual basis: transactions "
                    "recognised in period to which they relate")))
        return tuple(tasks)

    # ── Public API: generate_close_report ────────────────────────────
    def generate_close_report(
        self,
        period: str,
        accounts: Sequence[CloseAccount] = (),
        entries: Sequence[GLEntry] = (),
        recurring_schedules: Sequence[
            RecurringAccrualSchedule] = (),
        prepayment_schedules: Sequence[PrepaymentSchedule] = (),
        period_start_date: Optional[date] = None,
        period_end_date: Optional[date] = None,
        reference_dates: Optional[Dict[str, date]] = None,
        target_close_days: int = DEFAULT_TARGET_CLOSE_DAYS,
    ) -> CloseReadinessReport:
        """Orchestrate all five capabilities, return unified report."""
        accrual_tasks = self.detect_missing_recurring_accruals(
            recurring_schedules, entries, period)
        prep_tasks = self.detect_prepayment_amortization_due(
            prepayment_schedules, entries, period)
        ic_tasks = self.detect_intercompany_pending(
            accounts, entries, period)
        susp_tasks = self.detect_suspense_balances(
            accounts, entries, period)
        cutoff_tasks: Tuple[CloseTask, ...] = ()
        if (period_start_date is not None
                and period_end_date is not None):
            cutoff_tasks = self.detect_cutoff_timing(
                entries, period,
                period_start_date, period_end_date,
                reference_dates=reference_dates)

        all_tasks = (
            accrual_tasks + prep_tasks + ic_tasks
            + susp_tasks + cutoff_tasks)

        by_type: Dict[str, int] = {
            t.value: 0 for t in CloseTaskType}
        for t in all_tasks:
            by_type[t.task_type.value] += 1
        by_sev: Dict[str, int] = {
            s.value: 0 for s in CloseTaskSeverity}
        for t in all_tasks:
            by_sev[t.severity.value] += 1

        ready = sum(
            1 for t in all_tasks
            if t.status == CloseTaskStatus.READY_FOR_REVIEW)
        blocked = sum(
            1 for t in all_tasks
            if t.status == CloseTaskStatus.BLOCKED)

        return CloseReadinessReport(
            period=period,
            target_close_days=target_close_days,
            tasks=all_tasks,
            by_task_type=by_type,
            by_severity=by_sev,
            ready_for_review_count=ready,
            blocked_count=blocked,
            accounts_scanned=len(accounts),
            entries_scanned=len(entries),
            framework_refs=(
                "ENH-249 §close_orchestrator",
                "Gartner continuous close — <3 day target",
                "Per Rule 7 — recommends only; never posts, "
                "never closes period, never auto-clears",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _account(code, name="Test Acc",
             atype=AccountType.EXPENSE,
             suspense=False, ic=False):
    return CloseAccount(
        account_code=code, account_name=name,
        account_type=atype,
        is_suspense=suspense, is_intercompany=ic)


def _entry(eid, code, dr=0, cr=0,
           pdate=date(2026, 4, 15),
           period="2026-04", ref="", sched=""):
    return GLEntry(
        entry_id=eid, account_code=code,
        debit_kes=Decimal(str(dr)),
        credit_kes=Decimal(str(cr)),
        posting_date=pdate, period=period,
        reference=ref, schedule_id=sched)


def _test_account_validates_code_nonempty():
    try:
        _account("")
        assert False
    except ValueError:
        pass


def _test_glentry_validates_dr_cr_exclusive():
    try:
        _entry("e1", "1000", dr=100, cr=100)
        assert False
    except ValueError:
        pass


def _test_glentry_validates_nonzero():
    try:
        _entry("e1", "1000", dr=0, cr=0)
        assert False
    except ValueError:
        pass


def _test_glentry_validates_negative():
    try:
        _entry("e1", "1000", dr=-100, cr=0)
        assert False
    except ValueError:
        pass


def _test_recurring_schedule_validates():
    try:
        RecurringAccrualSchedule(
            schedule_id="s1", account_code="6000",
            periodic_amount_kes=Decimal("0"),
            frequency=AccrualFrequency.MONTHLY,
            contra_account_code="2100")
        assert False
    except ValueError:
        pass


def _test_prepayment_schedule_validates_period_order():
    try:
        PrepaymentSchedule(
            schedule_id="p1",
            prepaid_account_code="1500",
            expense_account_code="6500",
            total_amount_kes=Decimal("12000"),
            periodic_amount_kes=Decimal("1000"),
            start_period="2026-12",
            end_period="2026-01")
        assert False
    except ValueError:
        pass


def _test_missing_recurring_accrual_flagged():
    eng = FinanceCloseOrchestrator()
    sched = RecurringAccrualSchedule(
        schedule_id="RENT-MONTHLY",
        account_code="6100",
        periodic_amount_kes=Decimal("500000"),
        frequency=AccrualFrequency.MONTHLY,
        contra_account_code="2100")
    # No entries for this schedule
    tasks = eng.detect_missing_recurring_accruals(
        (sched,), (), "2026-04")
    assert len(tasks) == 1
    assert tasks[0].task_type == (
        CloseTaskType.MISSING_RECURRING_ACCRUAL)
    assert tasks[0].recommended_debit_kes == Decimal("500000")
    assert tasks[0].account_code == "6100"
    assert tasks[0].contra_account_code == "2100"


def _test_recurring_accrual_present_no_finding():
    eng = FinanceCloseOrchestrator()
    sched = RecurringAccrualSchedule(
        schedule_id="RENT-MONTHLY",
        account_code="6100",
        periodic_amount_kes=Decimal("500000"),
        frequency=AccrualFrequency.MONTHLY,
        contra_account_code="2100")
    entry = _entry("e1", "6100", dr=500000,
                   sched="RENT-MONTHLY")
    tasks = eng.detect_missing_recurring_accruals(
        (sched,), (entry,), "2026-04")
    assert len(tasks) == 0


def _test_quarterly_only_due_in_quarter_months():
    eng = FinanceCloseOrchestrator()
    sched = RecurringAccrualSchedule(
        schedule_id="QTR-BONUS",
        account_code="6200",
        periodic_amount_kes=Decimal("100000"),
        frequency=AccrualFrequency.QUARTERLY,
        contra_account_code="2200")
    # April is not a quarter-end month → no missing-accrual flag
    tasks_april = eng.detect_missing_recurring_accruals(
        (sched,), (), "2026-04")
    assert len(tasks_april) == 0
    # June is → missing-accrual flagged
    tasks_june = eng.detect_missing_recurring_accruals(
        (sched,), (), "2026-06")
    assert len(tasks_june) == 1


def _test_prepayment_amortization_due_flagged():
    eng = FinanceCloseOrchestrator()
    sched = PrepaymentSchedule(
        schedule_id="INSURANCE-2026",
        prepaid_account_code="1500",
        expense_account_code="6500",
        total_amount_kes=Decimal("120000"),
        periodic_amount_kes=Decimal("10000"),
        start_period="2026-01",
        end_period="2026-12")
    tasks = eng.detect_prepayment_amortization_due(
        (sched,), (), "2026-04")
    assert len(tasks) == 1
    assert tasks[0].recommended_debit_kes == Decimal("10000")
    assert tasks[0].account_code == "6500"
    assert tasks[0].contra_account_code == "1500"


def _test_prepayment_outside_window_skipped():
    eng = FinanceCloseOrchestrator()
    sched = PrepaymentSchedule(
        schedule_id="INSURANCE-2026",
        prepaid_account_code="1500",
        expense_account_code="6500",
        total_amount_kes=Decimal("120000"),
        periodic_amount_kes=Decimal("10000"),
        start_period="2026-01",
        end_period="2026-12")
    # 2025-12 is before start_period → skip
    tasks = eng.detect_prepayment_amortization_due(
        (sched,), (), "2025-12")
    assert len(tasks) == 0


def _test_intercompany_pending_flagged():
    eng = FinanceCloseOrchestrator()
    accounts = (
        _account("IC-1500", "Due from Subsidiary A", ic=True),
    )
    # Only Dr posted, no offsetting Cr on counter-entity
    e = GLEntry(
        entry_id="e1", account_code="IC-1500",
        debit_kes=Decimal("100000"),
        credit_kes=Decimal("0"),
        posting_date=date(2026, 4, 15),
        period="2026-04", reference="IC-INV-001",
        counterparty_entity_id="SUBA")
    tasks = eng.detect_intercompany_pending(
        accounts, (e,), "2026-04")
    assert len(tasks) == 1
    assert tasks[0].task_type == (
        CloseTaskType.INTERCOMPANY_PENDING)


def _test_intercompany_paired_no_finding():
    eng = FinanceCloseOrchestrator()
    accounts = (
        _account("IC-1500", "Due from", ic=True),
        _account("IC-2500", "Due to", ic=True),
    )
    # Same reference, both sides → paired
    dr = GLEntry(
        entry_id="e1", account_code="IC-1500",
        debit_kes=Decimal("100000"),
        credit_kes=Decimal("0"),
        posting_date=date(2026, 4, 15),
        period="2026-04", reference="IC-001",
        counterparty_entity_id="SUBA")
    cr = GLEntry(
        entry_id="e2", account_code="IC-2500",
        debit_kes=Decimal("0"),
        credit_kes=Decimal("100000"),
        posting_date=date(2026, 4, 15),
        period="2026-04", reference="IC-001",
        counterparty_entity_id="SUBB")
    tasks = eng.detect_intercompany_pending(
        accounts, (dr, cr), "2026-04")
    assert len(tasks) == 0


def _test_suspense_balance_critical():
    eng = FinanceCloseOrchestrator()
    accounts = (
        _account("9999", "Suspense", suspense=True),
    )
    e = _entry("e1", "9999", dr=50000)
    tasks = eng.detect_suspense_balances(
        accounts, (e,), "2026-04")
    assert len(tasks) == 1
    assert tasks[0].severity == CloseTaskSeverity.CRITICAL


def _test_suspense_zero_balance_no_finding():
    eng = FinanceCloseOrchestrator()
    accounts = (
        _account("9999", "Suspense", suspense=True),
    )
    dr = _entry("e1", "9999", dr=50000)
    cr = _entry("e2", "9999", cr=50000)
    tasks = eng.detect_suspense_balances(
        accounts, (dr, cr), "2026-04")
    assert len(tasks) == 0


def _test_cutoff_timing_flagged():
    eng = FinanceCloseOrchestrator()
    e = _entry("e1", "6100", dr=10000,
               pdate=date(2026, 4, 15))
    # Reference date Feb 1 — 60 days before April → flagged
    tasks = eng.detect_cutoff_timing(
        (e,), "2026-04",
        date(2026, 4, 1), date(2026, 4, 30),
        reference_dates={"e1": date(2026, 2, 1)})
    assert len(tasks) == 1
    # >30 days lag → HIGH severity
    assert tasks[0].severity == CloseTaskSeverity.HIGH


def _test_cutoff_timing_within_threshold_no_finding():
    eng = FinanceCloseOrchestrator()
    e = _entry("e1", "6100", dr=10000,
               pdate=date(2026, 4, 15))
    # Reference date Mar 28 — within 7-day threshold
    tasks = eng.detect_cutoff_timing(
        (e,), "2026-04",
        date(2026, 4, 1), date(2026, 4, 30),
        reference_dates={"e1": date(2026, 3, 28)})
    assert len(tasks) == 0


def _test_generate_close_report_orchestrates():
    eng = FinanceCloseOrchestrator()
    accounts = (
        _account("9999", "Suspense", suspense=True),
        _account("IC-1500", "Due from", ic=True),
    )
    sched = RecurringAccrualSchedule(
        schedule_id="RENT", account_code="6100",
        periodic_amount_kes=Decimal("500000"),
        frequency=AccrualFrequency.MONTHLY,
        contra_account_code="2100")
    susp_entry = _entry("s1", "9999", dr=10000)
    report = eng.generate_close_report(
        period="2026-04",
        accounts=accounts,
        entries=(susp_entry,),
        recurring_schedules=(sched,),
        period_start_date=date(2026, 4, 1),
        period_end_date=date(2026, 4, 30))
    assert isinstance(report, CloseReadinessReport)
    assert report.period == "2026-04"
    assert report.target_close_days == 3
    # 1 missing accrual + 1 suspense balance = 2
    assert len(report.tasks) == 2
    assert report.ready_for_review_count == 2


def _test_close_task_has_full_provenance():
    eng = FinanceCloseOrchestrator()
    sched = RecurringAccrualSchedule(
        schedule_id="RENT", account_code="6100",
        periodic_amount_kes=Decimal("500000"),
        frequency=AccrualFrequency.MONTHLY,
        contra_account_code="2100")
    tasks = eng.detect_missing_recurring_accruals(
        (sched,), (), "2026-04")
    t = tasks[0]
    assert t.task_id
    assert t.account_code == "6100"
    assert t.contra_account_code == "2100"
    assert t.description
    assert "RENT" in t.related_ids
    assert any("ENH-249" in r for r in t.framework_refs)


def _test_engine_does_not_mutate_inputs():
    """Per Rule 7 — frozen contract enforced."""
    eng = FinanceCloseOrchestrator()
    accounts = (_account("9999", suspense=True),)
    e = _entry("e1", "9999", dr=10000)
    eng.detect_suspense_balances(accounts, (e,), "2026-04")
    # Inputs unchanged
    assert e.debit_kes == Decimal("10000")
    assert accounts[0].is_suspense is True


def self_test() -> None:
    tests = [
        _test_account_validates_code_nonempty,
        _test_glentry_validates_dr_cr_exclusive,
        _test_glentry_validates_nonzero,
        _test_glentry_validates_negative,
        _test_recurring_schedule_validates,
        _test_prepayment_schedule_validates_period_order,
        _test_missing_recurring_accrual_flagged,
        _test_recurring_accrual_present_no_finding,
        _test_quarterly_only_due_in_quarter_months,
        _test_prepayment_amortization_due_flagged,
        _test_prepayment_outside_window_skipped,
        _test_intercompany_pending_flagged,
        _test_intercompany_paired_no_finding,
        _test_suspense_balance_critical,
        _test_suspense_zero_balance_no_finding,
        _test_cutoff_timing_flagged,
        _test_cutoff_timing_within_threshold_no_finding,
        _test_generate_close_report_orchestrates,
        _test_close_task_has_full_provenance,
        _test_engine_does_not_mutate_inputs,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ finance_close_orchestrator self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ finance_close_orchestrator self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

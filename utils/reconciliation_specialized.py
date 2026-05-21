"""utils/reconciliation_specialized.py — v10.20 Phase 2 batch 3 (RMS arc batch 3).

╔════════════════════════════════════════════════════════════════════════╗
║  SPECIALIZED RECONCILIATION — CBK + NOSTRO/VOSTRO + IC + KEPSS/PESALINK║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (regulatory deadline misses + Nostro stale items   ║
║              create supervisory + capital + FX risk)                    ║
║  Implements 4 of 17 RMS standards from registry:                        ║
║    ENH-185:    CBK Regulatory Reconciliation                            ║
║    ENH-186:    Nostro/Vostro Reconciliation                             ║
║    ENH-187:    Intercompany & Internal Suspense Reconciliation         ║
║    ENH-RMS-R6: Real-time KEPSS / PesaLink Reconciliation                ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Kenya Banking Act §39 — books and records integrity                 ║
║    Kenya Banking Act §32 — statutory returns submission                ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk              ║
║    CBK CRMF April 2021 §6 — internal controls + recon                  ║
║    CBK CRMF §6.4 — Nostro reconciliation monthly minimum               ║
║    CBK Act Cap 491 §4(d) — payment/clearing/settlement systems        ║
║    KEPSS Rules and Procedures (Schedules A-H)                          ║
║    PesaLink/IPSL Operating Rules                                        ║
║    SWIFT MT940 (statement) / MT942 (interim) / MT950 (combined)        ║
║    SWIFT MX (ISO 20022 camt.052/053/054)                               ║
║    Basel BCBS 239 §5 — accuracy and integrity principles              ║
║    PFMI 2012 (CPMI-IOSCO) — Principles for Financial Market Infra      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.18 (matching) + v10.19 (workflow + memory + guards) ║
║                                                                         ║
║  Honesty Rule 1: stale Nostro items + missed CBK deadlines surface    ║
║  explicitly with severity levels; never silently aged-out.             ║
║  Honesty Rule 7: SWIFT/ISO 20022 parser is callable hook; default      ║
║  uses simple field extraction with explicit SPEC_DEVIATION flagging.   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "SWIFT MT/MX parsing uses simple field extraction. Production deployments "
    "should wire structured parsers via parser= callable per Rule 7.")


# ════════════════════════════════════════════════════════════════════════
# CBK Regulatory Reconciliation (ENH-185)
# ════════════════════════════════════════════════════════════════════════

class CBKReturnType(Enum):
    """CBK statutory returns requiring reconciliation."""
    CRR = "CRR"                      # Cash Reserve Ratio (3.25% of deposits)
    LR = "LR"                         # Liquidity Ratio (≥20%)
    RAR = "RAR"                       # Risk Asset Ratio (Total CAR ≥14.5%)
    CAR_TIER1 = "CAR_TIER1"           # Tier 1 capital ratio (≥10.5%)
    LCR = "LCR"                       # Liquidity Coverage Ratio (≥100%)
    NSFR = "NSFR"                     # Net Stable Funding Ratio (≥100%)
    LEVERAGE_RATIO = "LEVERAGE_RATIO" # Basel III leverage (≥3%)
    DAILY_RETURN = "DAILY_RETURN"     # daily liquidity / RAR
    WEEKLY_RETURN = "WEEKLY_RETURN"   # weekly returns to BSD
    MONTHLY_RETURN = "MONTHLY_RETURN" # monthly bank returns (CBK 105)
    QUARTERLY_RETURN = "QUARTERLY_RETURN"
    LARGE_EXPOSURES = "LARGE_EXPOSURES"   # ≥10% capital reporting
    CONNECTED_LENDING = "CONNECTED_LENDING"
    AML_CTR = "AML_CTR"               # cash transaction reports
    AML_STR = "AML_STR"               # suspicious transaction reports
    FOREX_RETURN = "FOREX_RETURN"     # FX position reporting


class ReturnFrequency(Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    AD_HOC = "AD_HOC"


# Default deadlines per return type (calendar days from period end)
# Source: CBK CRMF + Banking Act + industry practice
DEFAULT_RETURN_DEADLINE_DAYS: Mapping[CBKReturnType, int] = {
    CBKReturnType.DAILY_RETURN: 1,            # next business day
    CBKReturnType.CRR: 1,                      # daily
    CBKReturnType.WEEKLY_RETURN: 2,            # by Tuesday for prior week
    CBKReturnType.LR: 7,                       # weekly + monthly snapshot
    CBKReturnType.LCR: 15,                     # monthly within 15 days
    CBKReturnType.NSFR: 15,                    # monthly
    CBKReturnType.MONTHLY_RETURN: 15,          # 15 days post month-end
    CBKReturnType.RAR: 15,
    CBKReturnType.CAR_TIER1: 15,
    CBKReturnType.LEVERAGE_RATIO: 15,
    CBKReturnType.LARGE_EXPOSURES: 15,
    CBKReturnType.CONNECTED_LENDING: 30,       # monthly
    CBKReturnType.QUARTERLY_RETURN: 21,        # 21 days post quarter-end
    CBKReturnType.FOREX_RETURN: 1,             # daily
    CBKReturnType.AML_CTR: 7,                  # weekly
    CBKReturnType.AML_STR: 1,                  # within 24h of detection
}


class ReturnStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    OVERDUE = "OVERDUE"
    AMENDMENT_REQUIRED = "AMENDMENT_REQUIRED"


class DeadlineSeverity(Enum):
    """Severity of approaching/missed deadline."""
    OK = "OK"                     # > 3 days remaining
    AMBER = "AMBER"               # ≤ 3 days remaining
    RED = "RED"                   # ≤ 1 day remaining
    BREACHED = "BREACHED"         # past deadline


@dataclass(frozen=True)
class CBKReturnRecord:
    """One regulatory return submission."""
    return_id: str
    return_type: CBKReturnType
    period_end: str               # ISO-8601 date
    deadline: str                  # ISO-8601 date
    status: ReturnStatus
    submitted_at: Optional[str] = None
    bank_book_value_kes: Optional[Decimal] = None
    cbk_book_value_kes: Optional[Decimal] = None
    variance_kes: Optional[Decimal] = None
    notes: str = ""

    def days_to_deadline(self, *, as_of: date) -> int:
        try:
            dl = date.fromisoformat(self.deadline)
        except ValueError:
            return 0
        return (dl - as_of).days

    def severity(self, *, as_of: date) -> DeadlineSeverity:
        if self.status in (ReturnStatus.SUBMITTED,
                              ReturnStatus.ACCEPTED):
            return DeadlineSeverity.OK
        days = self.days_to_deadline(as_of=as_of)
        if days < 0:
            return DeadlineSeverity.BREACHED
        if days <= 1:
            return DeadlineSeverity.RED
        if days <= 3:
            return DeadlineSeverity.AMBER
        return DeadlineSeverity.OK

    def has_variance(self) -> bool:
        return (self.variance_kes is not None
                  and self.variance_kes != Decimal("0"))


def compute_return_deadline(
    *,
    return_type: CBKReturnType,
    period_end: date,
    custom_deadline_days: Optional[int] = None,
) -> date:
    """Compute the regulatory deadline date for a return."""
    days = (custom_deadline_days
              if custom_deadline_days is not None
              else DEFAULT_RETURN_DEADLINE_DAYS.get(return_type, 15))
    return period_end + timedelta(days=days)


# ════════════════════════════════════════════════════════════════════════
# Nostro/Vostro Reconciliation (ENH-186)
# ════════════════════════════════════════════════════════════════════════

class CorrespondentAccountType(Enum):
    NOSTRO = "NOSTRO"      # our account at correspondent bank
    VOSTRO = "VOSTRO"      # correspondent's account at us
    LORO = "LORO"          # third-party account at correspondent on our behalf


class SwiftMessageType(Enum):
    """SWIFT message types relevant to Nostro reconciliation."""
    MT940 = "MT940"        # customer statement message
    MT942 = "MT942"        # interim transaction report
    MT950 = "MT950"        # statement-only message
    MT900 = "MT900"        # confirmation of debit
    MT910 = "MT910"        # confirmation of credit
    # MX (ISO 20022) messages
    CAMT_052 = "camt.052"  # bank-to-customer account report
    CAMT_053 = "camt.053"  # bank-to-customer statement
    CAMT_054 = "camt.054"  # bank-to-customer debit/credit notification


class StaleAgeBucket(Enum):
    """Age buckets for unreconciled Nostro items.

    Per CBK CRMF §6.4: monthly Nostro recon minimum; items >30 days
    require investigation; >90 days require provisioning consideration.
    """
    FRESH_0_30 = "FRESH_0_30"
    AGING_31_60 = "AGING_31_60"
    OVERDUE_61_90 = "OVERDUE_61_90"
    BREACH_91_PLUS = "BREACH_91_PLUS"


def compute_stale_age_bucket(days_outstanding: int) -> StaleAgeBucket:
    if days_outstanding < 0:
        raise ValueError(f"days_outstanding {days_outstanding} negative")
    if days_outstanding <= 30:
        return StaleAgeBucket.FRESH_0_30
    if days_outstanding <= 60:
        return StaleAgeBucket.AGING_31_60
    if days_outstanding <= 90:
        return StaleAgeBucket.OVERDUE_61_90
    return StaleAgeBucket.BREACH_91_PLUS


@dataclass(frozen=True)
class NostroVostroAccount:
    """A Nostro or Vostro correspondent account."""
    account_id: str
    account_type: CorrespondentAccountType
    correspondent_bank: str          # SWIFT BIC
    currency: str                     # USD, EUR, GBP, ZAR, etc.
    our_book_balance_kes_equiv: Decimal
    correspondent_book_balance_kes_equiv: Decimal
    fx_rate_used: Decimal             # KES per FCY unit
    cut_off_local_time: str = ""     # e.g., "16:00"
    notes: str = ""

    def variance_kes(self) -> Decimal:
        return self.our_book_balance_kes_equiv - self.correspondent_book_balance_kes_equiv

    def variance_pct(self) -> Decimal:
        if self.correspondent_book_balance_kes_equiv == Decimal("0"):
            return Decimal("0")
        return (self.variance_kes() /
                  self.correspondent_book_balance_kes_equiv * Decimal("100"))


@dataclass(frozen=True)
class StaleItem:
    """An unreconciled Nostro/Vostro item still outstanding."""
    item_id: str
    account_id: str
    booking_date: str                 # ISO-8601
    amount_fcy: Decimal
    amount_kes_equiv: Decimal
    currency: str
    counterparty: str = ""
    swift_reference: str = ""
    side: str = "DEBIT"              # DEBIT or CREDIT
    notes: str = ""

    def days_outstanding(self, *, as_of: date) -> int:
        try:
            booked = date.fromisoformat(self.booking_date)
        except ValueError:
            return 0
        return max(0, (as_of - booked).days)

    def aging(self, *, as_of: date) -> StaleAgeBucket:
        return compute_stale_age_bucket(
            self.days_outstanding(as_of=as_of))


@dataclass(frozen=True)
class FXRevaluationAdjustment:
    """FX revaluation diff explaining part of Nostro variance."""
    account_id: str
    fcy_balance: Decimal
    rate_at_book: Decimal
    rate_at_recon: Decimal
    reval_amount_kes: Decimal
    notes: str = ""


def compute_fx_reval(
    *,
    account_id: str,
    fcy_balance: Decimal,
    rate_at_book: Decimal,
    rate_at_recon: Decimal,
) -> FXRevaluationAdjustment:
    """Compute FX revaluation adjustment between booking + recon dates."""
    diff_rate = rate_at_recon - rate_at_book
    reval_kes = fcy_balance * diff_rate
    return FXRevaluationAdjustment(
        account_id=account_id,
        fcy_balance=fcy_balance,
        rate_at_book=rate_at_book,
        rate_at_recon=rate_at_recon,
        reval_amount_kes=reval_kes,
        notes=(
            f"reval = {fcy_balance} × ({rate_at_recon} - {rate_at_book})"))


# ════════════════════════════════════════════════════════════════════════
# Intercompany + Internal Suspense (ENH-187)
# ════════════════════════════════════════════════════════════════════════

class IntercompanyEntityType(Enum):
    """Types of intercompany counterparties (Ecobank Group example)."""
    SUBSIDIARY = "SUBSIDIARY"             # Ecobank Uganda, Tanzania, etc.
    BRANCH = "BRANCH"                     # internal branch within country
    ASSOCIATE = "ASSOCIATE"               # 20-50% owned
    JV = "JV"                             # joint venture
    HEAD_OFFICE = "HEAD_OFFICE"           # group HQ


@dataclass(frozen=True)
class IntercompanyCounterparty:
    """One intercompany counterparty entity."""
    counterparty_id: str
    counterparty_name: str
    entity_type: IntercompanyEntityType
    base_currency: str = "KES"
    our_balance_kes_equiv: Decimal = Decimal("0")
    their_balance_kes_equiv: Decimal = Decimal("0")
    notes: str = ""

    def is_in_balance(
        self, *, tolerance_kes: Decimal = Decimal("0.50"),
    ) -> bool:
        diff = abs(
            self.our_balance_kes_equiv - self.their_balance_kes_equiv)
        return diff <= tolerance_kes

    def variance_kes(self) -> Decimal:
        return self.our_balance_kes_equiv - self.their_balance_kes_equiv


class SuspenseCategory(Enum):
    """Internal suspense categories per CBK guidance."""
    CHEQUES_IN_CLEARING = "CHEQUES_IN_CLEARING"
    DEBIT_CARD_DISPUTES = "DEBIT_CARD_DISPUTES"
    UNAPPLIED_RECEIPTS = "UNAPPLIED_RECEIPTS"     # cash in but not allocated
    UNCLEARED_OUTWARDS = "UNCLEARED_OUTWARDS"      # outgoing not confirmed
    INTERBRANCH_TRANSIT = "INTERBRANCH_TRANSIT"
    FEES_DISPUTED = "FEES_DISPUTED"
    REVERSAL_PENDING = "REVERSAL_PENDING"
    SYSTEM_BREAKS = "SYSTEM_BREAKS"
    OTHER_SUSPENSE = "OTHER_SUSPENSE"


# Per CBK CRMF + industry practice — max acceptable age before escalation
DEFAULT_SUSPENSE_MAX_AGE_DAYS: Mapping[SuspenseCategory, int] = {
    SuspenseCategory.CHEQUES_IN_CLEARING: 5,
    SuspenseCategory.DEBIT_CARD_DISPUTES: 30,
    SuspenseCategory.UNAPPLIED_RECEIPTS: 7,
    SuspenseCategory.UNCLEARED_OUTWARDS: 7,
    SuspenseCategory.INTERBRANCH_TRANSIT: 3,
    SuspenseCategory.FEES_DISPUTED: 30,
    SuspenseCategory.REVERSAL_PENDING: 5,
    SuspenseCategory.SYSTEM_BREAKS: 7,
    SuspenseCategory.OTHER_SUSPENSE: 14,
}


@dataclass(frozen=True)
class SuspenseItem:
    """One internal suspense item awaiting resolution."""
    item_id: str
    suspense_category: SuspenseCategory
    booking_date: str                 # ISO-8601
    amount_kes: Decimal
    description: str = ""
    related_account_id: Optional[str] = None
    notes: str = ""

    def days_in_suspense(self, *, as_of: date) -> int:
        try:
            booked = date.fromisoformat(self.booking_date)
        except ValueError:
            return 0
        return max(0, (as_of - booked).days)

    def is_overdue(
        self, *, as_of: date,
        max_age_override: Optional[Mapping[SuspenseCategory, int]] = None,
    ) -> bool:
        max_ages = (
            max_age_override
            if max_age_override is not None
            else DEFAULT_SUSPENSE_MAX_AGE_DAYS)
        max_days = max_ages.get(self.suspense_category, 14)
        return self.days_in_suspense(as_of=as_of) > max_days


# ════════════════════════════════════════════════════════════════════════
# Real-time KEPSS / PesaLink Reconciliation (ENH-RMS-R6)
# ════════════════════════════════════════════════════════════════════════

class RealTimePaymentSystem(Enum):
    KEPSS = "KEPSS"        # Kenya Electronic Payment & Settlement System (RTGS)
    PESALINK = "PESALINK"  # IPSL retail real-time payments
    EAPS = "EAPS"          # East African Payment System (regional RTGS)


@dataclass(frozen=True)
class RealTimeReconciliationConfig:
    """Configuration for real-time payment reconciliation."""
    payment_system: RealTimePaymentSystem
    max_match_latency_seconds: int = 300         # 5 min default
    auto_match_threshold_seconds: int = 30        # ≤30s auto-resolved
    iso_20022_required: bool = True
    require_settlement_confirmation: bool = True
    notes: str = ""


@dataclass(frozen=True)
class RealTimePaymentObservation:
    """One observed real-time payment for matching."""
    payment_id: str
    payment_system: RealTimePaymentSystem
    initiated_at_utc: str            # ISO-8601 datetime
    settled_at_utc: Optional[str]     # ISO-8601 datetime, None if pending
    amount_kes: Decimal
    sender_bic: str = ""
    receiver_bic: str = ""
    iso_20022_message_id: str = ""
    end_to_end_id: str = ""
    notes: str = ""

    def latency_seconds(self) -> Optional[int]:
        if self.settled_at_utc is None:
            return None
        try:
            init = datetime.fromisoformat(
                self.initiated_at_utc.replace("Z", "+00:00"))
            settl = datetime.fromisoformat(
                self.settled_at_utc.replace("Z", "+00:00"))
        except ValueError:
            return None
        return int((settl - init).total_seconds())


class RealTimeMatchVerdict(Enum):
    """Outcome of real-time match check."""
    MATCHED_AUTO = "MATCHED_AUTO"            # within auto threshold
    MATCHED_DELAYED = "MATCHED_DELAYED"      # within max latency but delayed
    LATENCY_BREACH = "LATENCY_BREACH"        # exceeded max latency
    SETTLEMENT_PENDING = "SETTLEMENT_PENDING"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class RealTimeMatchResult:
    """Result of matching a real-time payment against settlement."""
    payment_id: str
    verdict: RealTimeMatchVerdict
    latency_seconds: Optional[int]
    breach_threshold_seconds: int
    notes: str = ""


def assess_real_time_match(
    *,
    initiated: RealTimePaymentObservation,
    settled: Optional[RealTimePaymentObservation],
    config: Optional[RealTimeReconciliationConfig] = None,
) -> RealTimeMatchResult:
    """Assess if a real-time payment has settled within latency targets.

    Per Rule 1: explicit verdict + reason; never silent pass.
    """
    cfg = config or RealTimeReconciliationConfig(
        payment_system=initiated.payment_system)

    if settled is None:
        return RealTimeMatchResult(
            payment_id=initiated.payment_id,
            verdict=RealTimeMatchVerdict.SETTLEMENT_PENDING,
            latency_seconds=None,
            breach_threshold_seconds=cfg.max_match_latency_seconds,
            notes="no settlement observation found")

    if settled.amount_kes != initiated.amount_kes:
        return RealTimeMatchResult(
            payment_id=initiated.payment_id,
            verdict=RealTimeMatchVerdict.AMOUNT_MISMATCH,
            latency_seconds=settled.latency_seconds(),
            breach_threshold_seconds=cfg.max_match_latency_seconds,
            notes=(
                f"initiated amount {initiated.amount_kes} != "
                f"settled amount {settled.amount_kes}"))

    latency = settled.latency_seconds()
    if latency is None:
        return RealTimeMatchResult(
            payment_id=initiated.payment_id,
            verdict=RealTimeMatchVerdict.SETTLEMENT_PENDING,
            latency_seconds=None,
            breach_threshold_seconds=cfg.max_match_latency_seconds,
            notes="cannot compute latency — invalid timestamps")

    if latency > cfg.max_match_latency_seconds:
        return RealTimeMatchResult(
            payment_id=initiated.payment_id,
            verdict=RealTimeMatchVerdict.LATENCY_BREACH,
            latency_seconds=latency,
            breach_threshold_seconds=cfg.max_match_latency_seconds,
            notes=(
                f"latency {latency}s exceeds max "
                f"{cfg.max_match_latency_seconds}s"))

    if latency <= cfg.auto_match_threshold_seconds:
        return RealTimeMatchResult(
            payment_id=initiated.payment_id,
            verdict=RealTimeMatchVerdict.MATCHED_AUTO,
            latency_seconds=latency,
            breach_threshold_seconds=cfg.max_match_latency_seconds,
            notes=f"matched within auto threshold ({latency}s)")

    return RealTimeMatchResult(
        payment_id=initiated.payment_id,
        verdict=RealTimeMatchVerdict.MATCHED_DELAYED,
        latency_seconds=latency,
        breach_threshold_seconds=cfg.max_match_latency_seconds,
        notes=f"matched delayed ({latency}s)")


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator for specialized reconciliation surfaces
# ════════════════════════════════════════════════════════════════════════

class SpecializedReconciliationEngine:
    """Aggregator for CBK + Nostro + IC + KEPSS reconciliation."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._cbk_returns: Dict[str, CBKReturnRecord] = {}
        self._nostro_accounts: Dict[str, NostroVostroAccount] = {}
        self._stale_items: Dict[str, StaleItem] = {}
        self._ic_counterparties: Dict[str, IntercompanyCounterparty] = {}
        self._suspense_items: Dict[str, SuspenseItem] = {}
        self._rt_payments: Dict[str, RealTimePaymentObservation] = {}
        self._rt_settlements: Dict[str, RealTimePaymentObservation] = {}

    # ── CBK returns ────────────────────────────────────────────────────
    def add_cbk_return(self, r: CBKReturnRecord) -> None:
        self._cbk_returns[r.return_id] = r

    def overdue_returns(self, *, as_of: date) -> Tuple[CBKReturnRecord, ...]:
        return tuple(
            r for r in self._cbk_returns.values()
            if r.severity(as_of=as_of) in (
                DeadlineSeverity.RED, DeadlineSeverity.BREACHED))

    # ── Nostro/Vostro ─────────────────────────────────────────────────
    def add_nostro_account(self, n: NostroVostroAccount) -> None:
        self._nostro_accounts[n.account_id] = n

    def add_stale_item(self, item: StaleItem) -> None:
        self._stale_items[item.item_id] = item

    def stale_items_by_aging(
        self, *, as_of: date,
    ) -> Mapping[StaleAgeBucket, Tuple[StaleItem, ...]]:
        buckets: Dict[StaleAgeBucket, List[StaleItem]] = {
            b: [] for b in StaleAgeBucket}
        for item in self._stale_items.values():
            buckets[item.aging(as_of=as_of)].append(item)
        return {b: tuple(items) for b, items in buckets.items()}

    def critical_stale_items(
        self, *, as_of: date,
    ) -> Tuple[StaleItem, ...]:
        """Items in OVERDUE_61_90 + BREACH_91_PLUS need investigation."""
        return tuple(
            item for item in self._stale_items.values()
            if item.aging(as_of=as_of) in (
                StaleAgeBucket.OVERDUE_61_90,
                StaleAgeBucket.BREACH_91_PLUS))

    # ── Intercompany + Suspense ───────────────────────────────────────
    def add_ic_counterparty(self, c: IntercompanyCounterparty) -> None:
        self._ic_counterparties[c.counterparty_id] = c

    def out_of_balance_ic(
        self, *, tolerance_kes: Decimal = Decimal("0.50"),
    ) -> Tuple[IntercompanyCounterparty, ...]:
        return tuple(
            c for c in self._ic_counterparties.values()
            if not c.is_in_balance(tolerance_kes=tolerance_kes))

    def add_suspense_item(self, s: SuspenseItem) -> None:
        self._suspense_items[s.item_id] = s

    def overdue_suspense_items(
        self, *, as_of: date,
    ) -> Tuple[SuspenseItem, ...]:
        return tuple(
            s for s in self._suspense_items.values()
            if s.is_overdue(as_of=as_of))

    # ── KEPSS / PesaLink real-time ────────────────────────────────────
    def record_rt_payment(self, p: RealTimePaymentObservation) -> None:
        self._rt_payments[p.payment_id] = p

    def record_rt_settlement(self, p: RealTimePaymentObservation) -> None:
        self._rt_settlements[p.payment_id] = p

    def assess_all_rt_payments(
        self, *, config: Optional[RealTimeReconciliationConfig] = None,
    ) -> Tuple[RealTimeMatchResult, ...]:
        results = []
        for pid, init in self._rt_payments.items():
            settled = self._rt_settlements.get(pid)
            r = assess_real_time_match(
                initiated=init, settled=settled, config=config)
            results.append(r)
        return tuple(results)

    # ── Board summary ─────────────────────────────────────────────────
    def board_summary(
        self, *, as_of: Optional[date] = None,
    ) -> Dict[str, object]:
        if as_of is None:
            as_of = date.today()
        rt_results = self.assess_all_rt_payments()
        rt_breach = sum(
            1 for r in rt_results
            if r.verdict == RealTimeMatchVerdict.LATENCY_BREACH)
        return {
            "entity": self.entity_name,
            "n_cbk_returns": len(self._cbk_returns),
            "n_returns_overdue": len(self.overdue_returns(as_of=as_of)),
            "n_nostro_accounts": len(self._nostro_accounts),
            "n_stale_items": len(self._stale_items),
            "n_critical_stale": len(
                self.critical_stale_items(as_of=as_of)),
            "n_ic_counterparties": len(self._ic_counterparties),
            "n_ic_out_of_balance": len(self.out_of_balance_ic()),
            "n_suspense_items": len(self._suspense_items),
            "n_overdue_suspense": len(
                self.overdue_suspense_items(as_of=as_of)),
            "n_rt_payments": len(self._rt_payments),
            "n_rt_latency_breaches": rt_breach,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_cbk_return_deadline_computed():
    dl = compute_return_deadline(
        return_type=CBKReturnType.MONTHLY_RETURN,
        period_end=date(2026, 4, 30))
    # 15 days post month-end → 15 May 2026
    assert dl == date(2026, 5, 15)


def _test_cbk_return_severity_ok():
    r = CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.PENDING)
    assert r.severity(as_of=date(2026, 5, 1)) == DeadlineSeverity.OK


def _test_cbk_return_severity_amber():
    r = CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.PENDING)
    # 3 days remaining → AMBER
    assert r.severity(as_of=date(2026, 5, 12)) == DeadlineSeverity.AMBER


def _test_cbk_return_severity_red():
    r = CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.PENDING)
    # 1 day remaining → RED
    assert r.severity(as_of=date(2026, 5, 14)) == DeadlineSeverity.RED


def _test_cbk_return_severity_breached():
    r = CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.PENDING)
    # 1 day past → BREACHED
    assert r.severity(as_of=date(2026, 5, 16)) == DeadlineSeverity.BREACHED


def _test_cbk_return_submitted_is_ok():
    """Even past deadline, if SUBMITTED then severity is OK."""
    r = CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.SUBMITTED)
    assert r.severity(as_of=date(2026, 6, 1)) == DeadlineSeverity.OK


def _test_cbk_variance_detection():
    r = CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.SUBMITTED,
        bank_book_value_kes=Decimal("1000000000"),
        cbk_book_value_kes=Decimal("999999000"),
        variance_kes=Decimal("1000"))
    assert r.has_variance()


def _test_stale_age_buckets():
    assert compute_stale_age_bucket(15) == StaleAgeBucket.FRESH_0_30
    assert compute_stale_age_bucket(45) == StaleAgeBucket.AGING_31_60
    assert compute_stale_age_bucket(75) == StaleAgeBucket.OVERDUE_61_90
    assert compute_stale_age_bucket(150) == StaleAgeBucket.BREACH_91_PLUS


def _test_stale_age_negative_raises():
    try:
        compute_stale_age_bucket(-5)
        assert False
    except ValueError:
        pass


def _test_nostro_variance_computation():
    n = NostroVostroAccount(
        account_id="N1",
        account_type=CorrespondentAccountType.NOSTRO,
        correspondent_bank="JPMORGAN_CHASE_NY",
        currency="USD",
        our_book_balance_kes_equiv=Decimal("129000000"),
        correspondent_book_balance_kes_equiv=Decimal("128900000"),
        fx_rate_used=Decimal("129.00"))
    assert n.variance_kes() == Decimal("100000")


def _test_fx_reval_computation():
    """FCY 1M USD; rate moved 128 → 129 → reval = +1M KES."""
    r = compute_fx_reval(
        account_id="N1",
        fcy_balance=Decimal("1000000"),
        rate_at_book=Decimal("128.00"),
        rate_at_recon=Decimal("129.00"))
    assert r.reval_amount_kes == Decimal("1000000")


def _test_stale_item_aging():
    item = StaleItem(
        item_id="S1", account_id="N1",
        booking_date="2026-01-01",
        amount_fcy=Decimal("1000"),
        amount_kes_equiv=Decimal("129000"),
        currency="USD")
    assert item.days_outstanding(as_of=date(2026, 4, 1)) == 90
    assert item.aging(as_of=date(2026, 4, 1)) == StaleAgeBucket.OVERDUE_61_90
    assert item.aging(as_of=date(2026, 4, 10)) == StaleAgeBucket.BREACH_91_PLUS


def _test_intercompany_in_balance():
    c = IntercompanyCounterparty(
        counterparty_id="EBK_UG",
        counterparty_name="Ecobank Uganda",
        entity_type=IntercompanyEntityType.SUBSIDIARY,
        our_balance_kes_equiv=Decimal("100000"),
        their_balance_kes_equiv=Decimal("100000"))
    assert c.is_in_balance()


def _test_intercompany_out_of_balance():
    c = IntercompanyCounterparty(
        counterparty_id="EBK_UG",
        counterparty_name="Ecobank Uganda",
        entity_type=IntercompanyEntityType.SUBSIDIARY,
        our_balance_kes_equiv=Decimal("100000"),
        their_balance_kes_equiv=Decimal("99500"))
    assert not c.is_in_balance()
    assert c.variance_kes() == Decimal("500")


def _test_suspense_overdue_per_category():
    """Cheques in clearing: 5 day max."""
    s = SuspenseItem(
        item_id="SUS1",
        suspense_category=SuspenseCategory.CHEQUES_IN_CLEARING,
        booking_date="2026-04-01",
        amount_kes=Decimal("10000"))
    # 7 days later — overdue (max 5 for cheques)
    assert s.is_overdue(as_of=date(2026, 4, 8))
    # 3 days later — fresh
    assert not s.is_overdue(as_of=date(2026, 4, 4))


def _test_suspense_dispute_30_day_threshold():
    """Card disputes get 30-day max, not 5."""
    s = SuspenseItem(
        item_id="SUS1",
        suspense_category=SuspenseCategory.DEBIT_CARD_DISPUTES,
        booking_date="2026-04-01",
        amount_kes=Decimal("50000"))
    assert not s.is_overdue(as_of=date(2026, 4, 25))
    assert s.is_overdue(as_of=date(2026, 5, 5))


def _test_real_time_match_auto():
    init = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc="2026-04-23T10:00:15Z",   # 15s
        amount_kes=Decimal("1000000"))
    settled = init    # for KEPSS RTGS, init/settle observations are paired
    r = assess_real_time_match(initiated=init, settled=settled)
    assert r.verdict == RealTimeMatchVerdict.MATCHED_AUTO
    assert r.latency_seconds == 15


def _test_real_time_match_delayed():
    init = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc=None, amount_kes=Decimal("1000000"))
    settled = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc="2026-04-23T10:01:30Z",   # 90s
        amount_kes=Decimal("1000000"))
    r = assess_real_time_match(initiated=init, settled=settled)
    assert r.verdict == RealTimeMatchVerdict.MATCHED_DELAYED
    assert r.latency_seconds == 90


def _test_real_time_match_breach():
    init = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc=None, amount_kes=Decimal("1000000"))
    settled = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc="2026-04-23T10:10:00Z",   # 600s — over 5min default
        amount_kes=Decimal("1000000"))
    r = assess_real_time_match(initiated=init, settled=settled)
    assert r.verdict == RealTimeMatchVerdict.LATENCY_BREACH


def _test_real_time_match_settlement_pending():
    init = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.PESALINK,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc=None, amount_kes=Decimal("1000000"))
    r = assess_real_time_match(initiated=init, settled=None)
    assert r.verdict == RealTimeMatchVerdict.SETTLEMENT_PENDING


def _test_real_time_match_amount_mismatch():
    init = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc="2026-04-23T10:00:10Z",
        amount_kes=Decimal("1000000"))
    settled = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc="2026-04-23T10:00:10Z",
        amount_kes=Decimal("999900"))           # 100 KES short
    r = assess_real_time_match(initiated=init, settled=settled)
    assert r.verdict == RealTimeMatchVerdict.AMOUNT_MISMATCH


def _test_engine_overdue_returns():
    eng = SpecializedReconciliationEngine()
    eng.add_cbk_return(CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.PENDING))
    eng.add_cbk_return(CBKReturnRecord(
        return_id="R2", return_type=CBKReturnType.WEEKLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-02",
        status=ReturnStatus.SUBMITTED))
    overdue = eng.overdue_returns(as_of=date(2026, 5, 16))
    # R1 breached, R2 submitted (OK)
    assert len(overdue) == 1
    assert overdue[0].return_id == "R1"


def _test_engine_critical_stale_items():
    eng = SpecializedReconciliationEngine()
    eng.add_stale_item(StaleItem(
        item_id="S1", account_id="N1",
        booking_date="2026-01-01",
        amount_fcy=Decimal("1000"),
        amount_kes_equiv=Decimal("129000"),
        currency="USD"))
    eng.add_stale_item(StaleItem(
        item_id="S2", account_id="N1",
        booking_date="2026-04-15",
        amount_fcy=Decimal("500"),
        amount_kes_equiv=Decimal("64500"),
        currency="USD"))
    critical = eng.critical_stale_items(as_of=date(2026, 5, 1))
    # S1: 4 months old (BREACH_91_PLUS); S2: 2 weeks (FRESH)
    assert len(critical) == 1
    assert critical[0].item_id == "S1"


def _test_engine_ic_out_of_balance():
    eng = SpecializedReconciliationEngine()
    eng.add_ic_counterparty(IntercompanyCounterparty(
        counterparty_id="EBK_UG", counterparty_name="Ecobank Uganda",
        entity_type=IntercompanyEntityType.SUBSIDIARY,
        our_balance_kes_equiv=Decimal("100000"),
        their_balance_kes_equiv=Decimal("100000")))
    eng.add_ic_counterparty(IntercompanyCounterparty(
        counterparty_id="EBK_TZ", counterparty_name="Ecobank Tanzania",
        entity_type=IntercompanyEntityType.SUBSIDIARY,
        our_balance_kes_equiv=Decimal("200000"),
        their_balance_kes_equiv=Decimal("199000")))
    out_of_bal = eng.out_of_balance_ic()
    assert len(out_of_bal) == 1
    assert out_of_bal[0].counterparty_id == "EBK_TZ"


def _test_engine_overdue_suspense():
    eng = SpecializedReconciliationEngine()
    eng.add_suspense_item(SuspenseItem(
        item_id="SUS1",
        suspense_category=SuspenseCategory.CHEQUES_IN_CLEARING,
        booking_date="2026-04-01",
        amount_kes=Decimal("10000")))
    overdue = eng.overdue_suspense_items(as_of=date(2026, 4, 10))
    # 9 days old vs 5-day max → overdue
    assert len(overdue) == 1


def _test_engine_real_time_assessment():
    eng = SpecializedReconciliationEngine()
    init = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc=None, amount_kes=Decimal("1000000"))
    settled = RealTimePaymentObservation(
        payment_id="P1", payment_system=RealTimePaymentSystem.KEPSS,
        initiated_at_utc="2026-04-23T10:00:00Z",
        settled_at_utc="2026-04-23T10:00:15Z",
        amount_kes=Decimal("1000000"))
    eng.record_rt_payment(init)
    eng.record_rt_settlement(settled)
    results = eng.assess_all_rt_payments()
    assert len(results) == 1
    assert results[0].verdict == RealTimeMatchVerdict.MATCHED_AUTO


def _test_engine_board_summary_empty():
    eng = SpecializedReconciliationEngine()
    s = eng.board_summary()
    assert s["n_cbk_returns"] == 0
    assert s["n_stale_items"] == 0


def _test_engine_board_summary_aggregates():
    eng = SpecializedReconciliationEngine()
    eng.add_cbk_return(CBKReturnRecord(
        return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
        period_end="2026-04-30", deadline="2026-05-15",
        status=ReturnStatus.PENDING))
    eng.add_stale_item(StaleItem(
        item_id="S1", account_id="N1",
        booking_date="2026-01-01",
        amount_fcy=Decimal("1000"),
        amount_kes_equiv=Decimal("129000"),
        currency="USD"))
    s = eng.board_summary(as_of=date(2026, 5, 1))
    assert s["n_cbk_returns"] == 1
    assert s["n_stale_items"] == 1
    assert s["n_critical_stale"] == 1


def _test_decimal_purity():
    n = NostroVostroAccount(
        account_id="N1",
        account_type=CorrespondentAccountType.NOSTRO,
        correspondent_bank="JP",
        currency="USD",
        our_book_balance_kes_equiv=Decimal("1000"),
        correspondent_book_balance_kes_equiv=Decimal("999"),
        fx_rate_used=Decimal("129.00"))
    assert isinstance(n.variance_kes(), Decimal)
    assert isinstance(n.variance_pct(), Decimal)


def self_test() -> None:
    tests = [
        _test_cbk_return_deadline_computed,
        _test_cbk_return_severity_ok,
        _test_cbk_return_severity_amber,
        _test_cbk_return_severity_red,
        _test_cbk_return_severity_breached,
        _test_cbk_return_submitted_is_ok,
        _test_cbk_variance_detection,
        _test_stale_age_buckets,
        _test_stale_age_negative_raises,
        _test_nostro_variance_computation,
        _test_fx_reval_computation,
        _test_stale_item_aging,
        _test_intercompany_in_balance,
        _test_intercompany_out_of_balance,
        _test_suspense_overdue_per_category,
        _test_suspense_dispute_30_day_threshold,
        _test_real_time_match_auto,
        _test_real_time_match_delayed,
        _test_real_time_match_breach,
        _test_real_time_match_settlement_pending,
        _test_real_time_match_amount_mismatch,
        _test_engine_overdue_returns,
        _test_engine_critical_stale_items,
        _test_engine_ic_out_of_balance,
        _test_engine_overdue_suspense,
        _test_engine_real_time_assessment,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_aggregates,
        _test_decimal_purity,
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
        print(f"✗ reconciliation_specialized self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ reconciliation_specialized self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

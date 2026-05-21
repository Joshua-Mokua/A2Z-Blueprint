"""utils/trade_finance_accounting.py — v10.75: TF accounting.

ENH-275 — Trade Finance Accounting & Integration. Cat B —
trade_finance arc 5/N.

Diagnostic accounting + capital integration engine for trade
finance instruments. Consumes TradeInstrument from ENH-269 and
produces:

  1. Basel III CCF lookup per instrument type + tenor bucket
  2. Capital impact computation (notional × CCF × risk_weight)
  3. IFRS 9 / IAS 37 journal entry templates per lifecycle event
     (ISSUE, DRAWDOWN, EXPIRE, CANCEL, AMEND_INCREASE,
     AMEND_DECREASE)
  4. Journal balance validation (DR == CR per posting cycle)
  5. IAS 37 off-balance-sheet disclosure helper (notional +
     contingent liability + risk-weighted exposure rollup)

Per Rule 7, engine NEVER:
  - posts journals to the general ledger (operator approves +
    posts via core banking workflow)
  - updates capital ratios in the GL
  - modifies risk weights (operator-set per CBK / Basel
    discretion)
  - submits regulatory capital returns (CBK BSD-1/2 territory,
    handled by ENH-280 + the cbk_regulatory_reporting engine)
  - mutates inputs

Per Rule 1, every output surfaces instrument_id +
journal_event + Decimal amounts + framework_refs (IFRS 9 §5.5
+ IAS 37 §10 + Basel III CRE 22.20-30 + CBK PG/04 risk weights).

Pure stdlib (Decimal + dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.trade_finance_instruments import (
    TradeInstrument, InstrumentType, InstrumentState, LcType)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceAccountingEngine implements ENH-275 — diagnostic "
    "IFRS 9 + IAS 37 + Basel III accounting and capital "
    "integration for trade finance instruments. Consumes "
    "TradeInstrument from ENH-269. Pure stdlib. Per Rule 1, every "
    "output surfaces full provenance. Per Rule 7, engine "
    "DIAGNOSTIC ONLY — never posts journals to GL; never updates "
    "capital ratios; never modifies risk weights (operator-set); "
    "never submits regulatory returns; never mutates inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class JournalEvent(Enum):
    """Lifecycle events that trigger accounting entries."""
    ISSUE = "ISSUE"                   # initial booking
    DRAWDOWN = "DRAWDOWN"             # beneficiary draws
    EXPIRE = "EXPIRE"                 # instrument expires unused
    CANCEL = "CANCEL"                 # cancelled before expiry
    AMEND_INCREASE = "AMEND_INCREASE"  # amount increase
    AMEND_DECREASE = "AMEND_DECREASE"  # amount decrease
    FEE_RECOGNITION = "FEE_RECOGNITION"  # fee accrual


class AccountClass(Enum):
    """Account classes used in trade finance accounting."""
    CONTINGENT_LIABILITY = "CONTINGENT_LIABILITY"  # off-BS
    RECEIVABLE = "RECEIVABLE"                       # on-BS asset
    PAYABLE = "PAYABLE"                             # on-BS liability
    FEE_INCOME = "FEE_INCOME"                       # P&L
    FX_REVALUATION = "FX_REVALUATION"               # OCI/P&L
    CASH = "CASH"                                   # on-BS asset


class JournalSide(Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class BaselCcfBucket(Enum):
    """Basel III CCF buckets for off-balance-sheet exposures.

    Per Basel III CRE 22.20-30, CCFs are applied to the notional
    amount to derive credit equivalent for capital purposes.
    Values used here are CBK PG/04-aligned (Kenya).
    """
    DOCUMENTARY_LC_SHORT = "DOCUMENTARY_LC_SHORT"     # ≤ 1y
    DOCUMENTARY_LC_LONG = "DOCUMENTARY_LC_LONG"       # > 1y
    SBLC_GUARANTEE = "SBLC_GUARANTEE"                 # SBLC + BG
    PERFORMANCE_BG = "PERFORMANCE_BG"                 # perf BG
    DOC_COLLECTION = "DOC_COLLECTION"
    CLEAN_COLLECTION = "CLEAN_COLLECTION"


class BalanceCheckOutcome(Enum):
    BALANCED = "BALANCED"           # DR sum == CR sum
    UNBALANCED = "UNBALANCED"       # DR sum != CR sum
    EMPTY = "EMPTY"


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CcfMeasurement:
    instrument_id: str
    instrument_type: InstrumentType
    bucket: BaselCcfBucket
    notional_kes: Decimal
    ccf: Decimal             # 0 ≤ ccf ≤ 1
    credit_equivalent_kes: Decimal   # notional × ccf
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CapitalImpact:
    instrument_id: str
    instrument_type: InstrumentType
    notional_kes: Decimal
    ccf: Decimal
    credit_equivalent_kes: Decimal
    risk_weight: Decimal     # caller-supplied per counterparty
    risk_weighted_exposure_kes: Decimal   # CE × RW
    capital_required_kes: Decimal         # RWA × 8% (Basel min)
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class JournalLine:
    account_class: AccountClass
    account_label: str
    side: JournalSide
    amount_kes: Decimal
    description: str

    def __post_init__(self) -> None:
        if self.amount_kes < 0:
            raise ValueError(
                "amount_kes must be non-negative (sign is "
                "carried by side)")


@dataclass(frozen=True)
class JournalTemplate:
    instrument_id: str
    instrument_type: InstrumentType
    event: JournalEvent
    lines: Tuple[JournalLine, ...]
    notional_kes: Decimal
    posting_date: str       # ISO date string (caller supplies)
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class BalanceCheck:
    template_count: int
    total_debit_kes: Decimal
    total_credit_kes: Decimal
    difference_kes: Decimal
    outcome: BalanceCheckOutcome
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class OffBalanceSheetDisclosure:
    as_of_date: str
    instrument_count: int
    total_notional_kes: Decimal
    total_contingent_liability_kes: Decimal
    total_credit_equivalent_kes: Decimal
    by_instrument_type: Dict[str, Decimal]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceAccountingEngine:
    """Diagnostic trade finance accounting + capital engine."""

    # CBK PG/04 CCF table (aligned to Basel III CRE 22.20-30)
    CCF_BY_BUCKET: Dict[BaselCcfBucket, Decimal] = {
        BaselCcfBucket.DOCUMENTARY_LC_SHORT: Decimal("0.20"),
        BaselCcfBucket.DOCUMENTARY_LC_LONG: Decimal("0.50"),
        BaselCcfBucket.SBLC_GUARANTEE: Decimal("1.00"),
        BaselCcfBucket.PERFORMANCE_BG: Decimal("0.50"),
        BaselCcfBucket.DOC_COLLECTION: Decimal("0.20"),
        BaselCcfBucket.CLEAN_COLLECTION: Decimal("0.00"),
    }

    # Basel III minimum capital ratio (8%)
    MIN_CAPITAL_RATIO: Decimal = Decimal("0.08")

    # Tenor split for documentary LCs
    LONG_TENOR_DAYS: int = 365

    @classmethod
    def _classify_bucket(
        cls, instrument: TradeInstrument,
    ) -> BaselCcfBucket:
        if instrument.instrument_type == InstrumentType.LC:
            tenor = (
                instrument.expiry_date - instrument.issue_date
            ).days
            return (
                BaselCcfBucket.DOCUMENTARY_LC_LONG
                if tenor > cls.LONG_TENOR_DAYS
                else BaselCcfBucket.DOCUMENTARY_LC_SHORT)
        if instrument.instrument_type == InstrumentType.SBLC:
            return BaselCcfBucket.SBLC_GUARANTEE
        if instrument.instrument_type == InstrumentType.BG:
            # All BG types receive PERFORMANCE_BG bucket here.
            # CBK PG/04 distinguishes payment guarantees (1.00)
            # from performance (0.50). Caller can override by
            # passing bucket explicitly to compute_ccf.
            return BaselCcfBucket.PERFORMANCE_BG
        if (
            instrument.instrument_type
            == InstrumentType.DOC_COLLECTION
        ):
            return BaselCcfBucket.DOC_COLLECTION
        if (
            instrument.instrument_type
            == InstrumentType.CLEAN_COLLECTION
        ):
            return BaselCcfBucket.CLEAN_COLLECTION
        raise ValueError(
            f"unrecognized instrument_type: "
            f"{instrument.instrument_type}")

    def compute_ccf(
        self,
        instrument: TradeInstrument,
        bucket_override: Optional[BaselCcfBucket] = None,
    ) -> CcfMeasurement:
        """Apply Basel III CCF to derive credit equivalent."""
        bucket = (
            bucket_override
            if bucket_override is not None
            else self._classify_bucket(instrument))
        ccf = self.CCF_BY_BUCKET[bucket]
        notional = instrument.amount_kes
        # For partially drawn LCs, drawn portion is on-BS
        # receivable (CCF = 1 effectively); undrawn applies CCF.
        # We surface the undrawn-CCF computation here; on-BS
        # portion handled in capital impact orchestrator.
        if instrument.instrument_type in (
            InstrumentType.LC,
            InstrumentType.DOC_COLLECTION,
        ):
            undrawn = notional - instrument.drawn_amount_kes
            credit_equivalent = (undrawn * ccf).quantize(
                Decimal("0.01"))
        else:
            credit_equivalent = (notional * ccf).quantize(
                Decimal("0.01"))
        return CcfMeasurement(
            instrument_id=instrument.instrument_id,
            instrument_type=instrument.instrument_type,
            bucket=bucket,
            notional_kes=notional,
            ccf=ccf,
            credit_equivalent_kes=credit_equivalent,
            framework_refs=(
                "ENH-275 §compute_ccf",
                "Basel III CRE 22.20-30 — Credit Conversion "
                "Factor for off-balance-sheet exposures",
                "CBK PG/04 §3.4 — capital adequacy on "
                "contingent liabilities",
                "Per Rule 7 — never modifies CCF table; "
                "operator confirms classification",
            ),
        )

    def compute_capital_impact(
        self,
        instrument: TradeInstrument,
        risk_weight: Decimal,
        bucket_override: Optional[BaselCcfBucket] = None,
    ) -> CapitalImpact:
        """Apply CCF + risk weight to derive RWA + capital req."""
        if risk_weight < 0 or risk_weight > Decimal("1.5"):
            raise ValueError(
                f"risk_weight must be 0..1.5; got {risk_weight}")
        ccf_m = self.compute_ccf(
            instrument, bucket_override=bucket_override)
        rwa = (
            ccf_m.credit_equivalent_kes * risk_weight
        ).quantize(Decimal("0.01"))
        capital_required = (
            rwa * self.MIN_CAPITAL_RATIO
        ).quantize(Decimal("0.01"))
        return CapitalImpact(
            instrument_id=instrument.instrument_id,
            instrument_type=instrument.instrument_type,
            notional_kes=ccf_m.notional_kes,
            ccf=ccf_m.ccf,
            credit_equivalent_kes=ccf_m.credit_equivalent_kes,
            risk_weight=risk_weight,
            risk_weighted_exposure_kes=rwa,
            capital_required_kes=capital_required,
            framework_refs=(
                "ENH-275 §compute_capital_impact",
                "Basel III §52-58 — risk-weighted assets "
                "computation",
                "CBK PG/02 — minimum capital ratio "
                "(currently 8% Tier 1+2 baseline; CBK can "
                "set higher per institution)",
                "Per Rule 7 — risk_weight is operator-supplied; "
                "engine never derives risk weights",
            ),
        )

    def generate_journal_template(
        self,
        instrument: TradeInstrument,
        event: JournalEvent,
        posting_date_iso: str,
        amount_override_kes: Optional[Decimal] = None,
        fee_kes: Decimal = Decimal("0"),
    ) -> JournalTemplate:
        """Generate an IFRS 9 / IAS 37 journal template.

        Returns paired DR/CR lines per the event type. Operator
        reviews + posts via core banking workflow; this engine
        never touches the GL.
        """
        notional = (
            amount_override_kes
            if amount_override_kes is not None
            else instrument.amount_kes)
        if notional < 0:
            raise ValueError(
                "notional cannot be negative")
        if fee_kes < 0:
            raise ValueError("fee_kes cannot be negative")

        lines: List[JournalLine] = []

        if event == JournalEvent.ISSUE:
            # Off-balance-sheet booking + fee recognition
            # IFRS 9 §5.5 — financial guarantee contract recognized
            # initially at fair value (typically the fee received)
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    f"Contingent Liability — "
                    f"{instrument.instrument_type.value} "
                    f"Issued"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    f"Recognize contingent liability for "
                    f"{instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    "Contra — Contingent Liability Offset"),
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description=(
                    "Memo entry for off-BS contingent "
                    "exposure (IAS 37 §10)")))
            if fee_kes > 0:
                lines.append(JournalLine(
                    account_class=AccountClass.CASH,
                    account_label="Cash / Bank — Fee Received",
                    side=JournalSide.DEBIT,
                    amount_kes=fee_kes,
                    description=(
                        f"Fee receipt on issuance of "
                        f"{instrument.instrument_id}")))
                lines.append(JournalLine(
                    account_class=AccountClass.FEE_INCOME,
                    account_label=(
                        "Trade Finance Fee Income"),
                    side=JournalSide.CREDIT,
                    amount_kes=fee_kes,
                    description=(
                        f"Fee income recognized "
                        f"(IFRS 15 — performance "
                        f"obligation satisfied at "
                        f"issuance)")))

        elif event == JournalEvent.DRAWDOWN:
            # Beneficiary drawdown — bank pays beneficiary,
            # creates receivable from applicant. Contingent
            # liability reverses for the drawn portion.
            lines.append(JournalLine(
                account_class=AccountClass.RECEIVABLE,
                account_label=(
                    f"Receivable — {instrument.applicant} "
                    f"({instrument.instrument_id})"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    f"Receivable from applicant on "
                    f"drawdown of "
                    f"{instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.CASH,
                account_label="Cash / Bank — Beneficiary Payment",
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description=(
                    f"Payment to {instrument.beneficiary}")))
            # Reverse contingent liability for drawn portion
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    "Contra — Contingent Liability Offset"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    "Reverse contingent liability for "
                    "drawn portion")))
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    f"Contingent Liability — "
                    f"{instrument.instrument_type.value} "
                    f"Issued"),
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description=(
                    "Reduce contingent liability balance")))

        elif event == JournalEvent.EXPIRE:
            # Reverse contingent liability — instrument expired unused
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    "Contra — Contingent Liability Offset"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    f"Reverse contingent liability for "
                    f"expired {instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    f"Contingent Liability — "
                    f"{instrument.instrument_type.value} "
                    f"Issued"),
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description=(
                    "Reduce contingent liability balance")))

        elif event == JournalEvent.CANCEL:
            # Same accounting as expire — reverse the contingent
            # liability. The cancellation circumstance differs
            # (negotiated cancellation vs natural expiry) but
            # the journal is identical.
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    "Contra — Contingent Liability Offset"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    f"Reverse contingent liability for "
                    f"cancelled "
                    f"{instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    f"Contingent Liability — "
                    f"{instrument.instrument_type.value} "
                    f"Issued"),
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description="Reduce balance"))

        elif event == JournalEvent.AMEND_INCREASE:
            # Increase contingent liability for the delta
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    f"Contingent Liability — "
                    f"{instrument.instrument_type.value} "
                    f"Issued"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    f"Increase contingent liability — "
                    f"amendment delta "
                    f"{instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    "Contra — Contingent Liability Offset"),
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description="Increase contra"))

        elif event == JournalEvent.AMEND_DECREASE:
            # Decrease contingent liability
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    "Contra — Contingent Liability Offset"),
                side=JournalSide.DEBIT,
                amount_kes=notional,
                description=(
                    f"Decrease contra for amendment "
                    f"{instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label=(
                    f"Contingent Liability — "
                    f"{instrument.instrument_type.value} "
                    f"Issued"),
                side=JournalSide.CREDIT,
                amount_kes=notional,
                description="Decrease balance"))

        elif event == JournalEvent.FEE_RECOGNITION:
            # Standalone fee accrual (e.g. period-end recurring fee)
            if fee_kes <= 0:
                raise ValueError(
                    "FEE_RECOGNITION requires fee_kes > 0")
            lines.append(JournalLine(
                account_class=AccountClass.RECEIVABLE,
                account_label="Fee Receivable",
                side=JournalSide.DEBIT,
                amount_kes=fee_kes,
                description=(
                    f"Accrue fee for "
                    f"{instrument.instrument_id}")))
            lines.append(JournalLine(
                account_class=AccountClass.FEE_INCOME,
                account_label="Trade Finance Fee Income",
                side=JournalSide.CREDIT,
                amount_kes=fee_kes,
                description="Recognize fee income"))

        else:
            raise ValueError(f"unsupported event {event}")

        return JournalTemplate(
            instrument_id=instrument.instrument_id,
            instrument_type=instrument.instrument_type,
            event=event,
            lines=tuple(lines),
            notional_kes=notional,
            posting_date=posting_date_iso,
            framework_refs=(
                "ENH-275 §generate_journal_template",
                "IFRS 9 §5.5 — financial guarantee contracts",
                "IAS 37 §10 — contingent liability disclosure",
                "IFRS 15 — fee revenue recognition",
                "Per Rule 7 — engine generates template only; "
                "operator reviews + posts via core banking "
                "workflow; never touches GL",
            ),
        )

    def validate_journal_balance(
        self, templates: Sequence[JournalTemplate],
    ) -> BalanceCheck:
        """Verify DR sum == CR sum across a posting cycle."""
        total_dr = Decimal("0")
        total_cr = Decimal("0")
        line_count = 0
        for t in templates:
            for line in t.lines:
                line_count += 1
                if line.side == JournalSide.DEBIT:
                    total_dr += line.amount_kes
                else:
                    total_cr += line.amount_kes
        diff = total_dr - total_cr
        if line_count == 0:
            outcome = BalanceCheckOutcome.EMPTY
        elif diff == 0:
            outcome = BalanceCheckOutcome.BALANCED
        else:
            outcome = BalanceCheckOutcome.UNBALANCED
        return BalanceCheck(
            template_count=len(templates),
            total_debit_kes=total_dr,
            total_credit_kes=total_cr,
            difference_kes=diff,
            outcome=outcome,
            framework_refs=(
                "ENH-275 §validate_journal_balance",
                "Double-entry bookkeeping invariant — DR == CR",
                "Per Rule 7 — surfaces imbalance; never "
                "auto-corrects",
            ),
        )

    def build_off_balance_sheet_disclosure(
        self,
        instruments: Sequence[TradeInstrument],
        as_of_date_iso: str,
    ) -> OffBalanceSheetDisclosure:
        """IAS 37 disclosure helper — totals + by-type breakdown."""
        total_notional = Decimal("0")
        total_contingent = Decimal("0")
        total_credit_equiv = Decimal("0")
        by_type: Dict[str, Decimal] = {}
        # Only count instruments still presenting contingent risk
        active_states = (
            InstrumentState.ISSUED,
            InstrumentState.AMENDED,
            InstrumentState.ACTIVE)
        for inst in instruments:
            if inst.state not in active_states:
                continue
            notional = inst.amount_kes
            undrawn = notional - inst.drawn_amount_kes
            ccf_m = self.compute_ccf(inst)
            total_notional += notional
            total_contingent += undrawn
            total_credit_equiv += ccf_m.credit_equivalent_kes
            key = inst.instrument_type.value
            by_type[key] = (
                by_type.get(key, Decimal("0")) + undrawn)
        return OffBalanceSheetDisclosure(
            as_of_date=as_of_date_iso,
            instrument_count=len([
                i for i in instruments
                if i.state in active_states]),
            total_notional_kes=total_notional,
            total_contingent_liability_kes=total_contingent,
            total_credit_equivalent_kes=total_credit_equiv,
            by_instrument_type=by_type,
            framework_refs=(
                "ENH-275 §build_off_balance_sheet_disclosure",
                "IAS 37 §10 — contingent liability disclosure",
                "IFRS 7 §31-42 — credit risk disclosure for "
                "financial guarantee contracts",
                "Basel III Pillar 3 — off-balance-sheet "
                "exposure disclosure",
                "Per Rule 7 — engine produces disclosure data; "
                "operator publishes financial statements",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_lc(
    iid="LC-001", state=InstrumentState.ISSUED,
    amount=Decimal("1000000"), drawn=Decimal("0"),
    issue_iso="2026-04-01", expiry_iso="2026-07-01",
):
    from datetime import date as _d
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state,
        applicant="Acme Imports",
        beneficiary="Shanghai Steel",
        issuing_bank="Ecobank",
        advising_bank="ABC",
        amount_kes=amount,
        drawn_amount_kes=drawn,
        currency="KES",
        issue_date=_d.fromisoformat(issue_iso),
        expiry_date=_d.fromisoformat(expiry_iso),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="goods")


def _make_bg(amount=Decimal("5000000")):
    from datetime import date as _d
    from utils.trade_finance_instruments import BgType
    return TradeInstrument(
        instrument_id="BG-001",
        instrument_type=InstrumentType.BG,
        state=InstrumentState.ISSUED,
        applicant="Acme Contractors",
        beneficiary="KRA",
        issuing_bank="Ecobank",
        advising_bank=None,
        amount_kes=amount,
        currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 10, 1),
        tenor_days=0, bg_type=BgType.PERFORMANCE)


def _test_ccf_short_lc():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(
        amount=Decimal("1000000"),
        issue_iso="2026-04-01", expiry_iso="2026-07-01")
    m = eng.compute_ccf(inst)
    assert m.bucket == BaselCcfBucket.DOCUMENTARY_LC_SHORT
    assert m.ccf == Decimal("0.20")
    assert m.credit_equivalent_kes == Decimal("200000.00")


def _test_ccf_long_lc():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(
        amount=Decimal("1000000"),
        issue_iso="2026-04-01",
        expiry_iso="2027-07-01")    # 456d > 365d
    m = eng.compute_ccf(inst)
    assert m.bucket == BaselCcfBucket.DOCUMENTARY_LC_LONG
    assert m.ccf == Decimal("0.50")
    assert m.credit_equivalent_kes == Decimal("500000.00")


def _test_ccf_partially_drawn_lc():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(
        amount=Decimal("1000000"),
        drawn=Decimal("400000"))
    m = eng.compute_ccf(inst)
    # Undrawn 600000 × 0.20 = 120000
    assert m.credit_equivalent_kes == Decimal("120000.00")


def _test_ccf_bg_full_notional():
    eng = TradeFinanceAccountingEngine()
    inst = _make_bg(amount=Decimal("5000000"))
    m = eng.compute_ccf(inst)
    assert m.bucket == BaselCcfBucket.PERFORMANCE_BG
    assert m.ccf == Decimal("0.50")
    assert m.credit_equivalent_kes == Decimal("2500000.00")


def _test_ccf_bucket_override():
    eng = TradeFinanceAccountingEngine()
    inst = _make_bg()
    # Override to SBLC_GUARANTEE (1.00) for a payment guarantee
    m = eng.compute_ccf(
        inst,
        bucket_override=BaselCcfBucket.SBLC_GUARANTEE)
    assert m.bucket == BaselCcfBucket.SBLC_GUARANTEE
    assert m.ccf == Decimal("1.00")


def _test_capital_impact():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(amount=Decimal("1000000"))
    impact = eng.compute_capital_impact(
        inst, risk_weight=Decimal("1.00"))
    # CCF 0.20 × 1m = 200k credit equiv
    # × 100% RW = 200k RWA
    # × 8% = 16k capital required
    assert impact.credit_equivalent_kes == Decimal("200000.00")
    assert impact.risk_weighted_exposure_kes == Decimal(
        "200000.00")
    assert impact.capital_required_kes == Decimal("16000.00")


def _test_capital_impact_lower_risk_weight():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(amount=Decimal("1000000"))
    impact = eng.compute_capital_impact(
        inst, risk_weight=Decimal("0.20"))
    # Sovereign-quality counterparty
    assert impact.capital_required_kes == Decimal("3200.00")


def _test_capital_impact_validates_risk_weight():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc()
    try:
        eng.compute_capital_impact(
            inst, risk_weight=Decimal("-0.1"))
        assert False
    except ValueError:
        pass
    try:
        eng.compute_capital_impact(
            inst, risk_weight=Decimal("2.0"))
        assert False
    except ValueError:
        pass


def _test_journal_issue_balanced():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(amount=Decimal("1000000"))
    template = eng.generate_journal_template(
        inst, JournalEvent.ISSUE,
        posting_date_iso="2026-04-01",
        fee_kes=Decimal("5000"))
    assert template.event == JournalEvent.ISSUE
    # 4 lines: contingent DR/CR + fee DR/CR
    assert len(template.lines) == 4
    bal = eng.validate_journal_balance((template,))
    assert bal.outcome == BalanceCheckOutcome.BALANCED


def _test_journal_drawdown_balanced():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(amount=Decimal("1000000"))
    template = eng.generate_journal_template(
        inst, JournalEvent.DRAWDOWN,
        posting_date_iso="2026-05-15")
    # 4 lines: receivable DR + cash CR + contingent reversal DR/CR
    assert len(template.lines) == 4
    bal = eng.validate_journal_balance((template,))
    assert bal.outcome == BalanceCheckOutcome.BALANCED


def _test_journal_expire_balanced():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc()
    template = eng.generate_journal_template(
        inst, JournalEvent.EXPIRE,
        posting_date_iso="2026-07-01")
    assert len(template.lines) == 2
    bal = eng.validate_journal_balance((template,))
    assert bal.outcome == BalanceCheckOutcome.BALANCED


def _test_journal_amend_increase():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc()
    template = eng.generate_journal_template(
        inst, JournalEvent.AMEND_INCREASE,
        posting_date_iso="2026-05-01",
        amount_override_kes=Decimal("200000"))
    assert template.notional_kes == Decimal("200000")
    bal = eng.validate_journal_balance((template,))
    assert bal.outcome == BalanceCheckOutcome.BALANCED


def _test_journal_fee_recognition():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc()
    template = eng.generate_journal_template(
        inst, JournalEvent.FEE_RECOGNITION,
        posting_date_iso="2026-05-01",
        fee_kes=Decimal("2500"))
    assert len(template.lines) == 2
    assert template.lines[0].account_class == (
        AccountClass.RECEIVABLE)
    assert template.lines[1].account_class == (
        AccountClass.FEE_INCOME)


def _test_journal_fee_recognition_requires_fee():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc()
    try:
        eng.generate_journal_template(
            inst, JournalEvent.FEE_RECOGNITION,
            posting_date_iso="2026-05-01",
            fee_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_journal_line_negative_amount_rejected():
    try:
        JournalLine(
            account_class=AccountClass.CASH,
            account_label="x", side=JournalSide.DEBIT,
            amount_kes=Decimal("-1"),
            description="x")
        assert False
    except ValueError:
        pass


def _test_balance_check_unbalanced_detected():
    # Manually craft an unbalanced template
    inst = _make_lc()
    bad_template = JournalTemplate(
        instrument_id=inst.instrument_id,
        instrument_type=inst.instrument_type,
        event=JournalEvent.ISSUE,
        lines=(
            JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label="x", side=JournalSide.DEBIT,
                amount_kes=Decimal("100"), description="x"),
            JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label="y", side=JournalSide.CREDIT,
                amount_kes=Decimal("90"), description="y"),
        ),
        notional_kes=Decimal("100"),
        posting_date="2026-01-01",
        framework_refs=())
    eng = TradeFinanceAccountingEngine()
    bal = eng.validate_journal_balance((bad_template,))
    assert bal.outcome == BalanceCheckOutcome.UNBALANCED
    assert bal.difference_kes == Decimal("10")


def _test_balance_check_empty():
    eng = TradeFinanceAccountingEngine()
    bal = eng.validate_journal_balance(())
    assert bal.outcome == BalanceCheckOutcome.EMPTY


def _test_off_balance_sheet_disclosure():
    eng = TradeFinanceAccountingEngine()
    instruments = (
        _make_lc(
            iid="L1", state=InstrumentState.ISSUED,
            amount=Decimal("1000000")),
        _make_lc(
            iid="L2", state=InstrumentState.EXPIRED,
            amount=Decimal("500000")),
        _make_bg(amount=Decimal("2000000")),
    )
    disclosure = eng.build_off_balance_sheet_disclosure(
        instruments, as_of_date_iso="2026-04-15")
    # Only ISSUED + ACTIVE counted; EXPIRED excluded
    assert disclosure.instrument_count == 2
    # 1m LC + 2m BG = 3m notional active
    assert disclosure.total_notional_kes == Decimal("3000000")
    # Contingent: 1m LC undrawn + 2m BG = 3m
    assert disclosure.total_contingent_liability_kes == (
        Decimal("3000000"))
    # Credit equivalent: 1m × 0.20 + 2m × 0.50 = 200k + 1m = 1.2m
    assert disclosure.total_credit_equivalent_kes == (
        Decimal("1200000.00"))
    assert "LC" in disclosure.by_instrument_type
    assert "BG" in disclosure.by_instrument_type


def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc(amount=Decimal("1000000"))
    eng.compute_ccf(inst)
    eng.compute_capital_impact(inst, risk_weight=Decimal("1.0"))
    eng.generate_journal_template(
        inst, JournalEvent.ISSUE,
        posting_date_iso="2026-04-01",
        fee_kes=Decimal("100"))
    assert inst.amount_kes == Decimal("1000000")
    assert inst.drawn_amount_kes == Decimal("0")


def _test_full_provenance():
    eng = TradeFinanceAccountingEngine()
    inst = _make_lc()
    m = eng.compute_ccf(inst)
    assert any("ENH-275" in r for r in m.framework_refs)
    assert any("Basel III" in r for r in m.framework_refs)
    assert any("CBK PG" in r for r in m.framework_refs)
    assert any("Rule 7" in r for r in m.framework_refs)


def self_test() -> None:
    tests = [
        _test_ccf_short_lc,
        _test_ccf_long_lc,
        _test_ccf_partially_drawn_lc,
        _test_ccf_bg_full_notional,
        _test_ccf_bucket_override,
        _test_capital_impact,
        _test_capital_impact_lower_risk_weight,
        _test_capital_impact_validates_risk_weight,
        _test_journal_issue_balanced,
        _test_journal_drawdown_balanced,
        _test_journal_expire_balanced,
        _test_journal_amend_increase,
        _test_journal_fee_recognition,
        _test_journal_fee_recognition_requires_fee,
        _test_journal_line_negative_amount_rejected,
        _test_balance_check_unbalanced_detected,
        _test_balance_check_empty,
        _test_off_balance_sheet_disclosure,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
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
        print(
            f"✗ trade_finance_accounting self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_accounting self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

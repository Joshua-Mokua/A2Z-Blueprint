"""utils/trade_finance_instruments.py — v10.70: TFI core.

ENH-269 — Trade Finance Core Instruments Engine. Cat B —
trade_finance arc 1/N (arc opening batch).

Diagnostic trade finance instrument lifecycle + validation engine.
Five capabilities:

  1. validate_issuance — pre-issuance field-level + business-rule
     validation per instrument type (LC, SBLC, BG, Doc Collection,
     Clean Collection); applicable framework varies by type
  2. validate_state_transition — enforces InstrumentState machine
     per UCP 600 / ISP98 / URDG 758 / URC 522 conventions
  3. validate_amendment — amendments only allowed in specific
     states; surfaces beneficiary-consent requirement for
     LC/SBLC per UCP 600 §10
  4. compute_exposure — funded vs unfunded contingent liability
     measurement per IFRS 9 + IAS 37 disclosure framework
  5. age_pending_actions — surface DRAFT/APPROVED instruments
     not yet issued, ISSUED instruments approaching expiry,
     EXPIRED instruments not yet closed

Per Rule 7, engine NEVER:
  - issues instruments (operator approval workflow)
  - amends instruments
  - honors drawdowns or pays beneficiaries
  - books accounting entries
  - sends SWIFT messages (ENH-272 territory)
  - mutates inputs

Per Rule 1, every output surfaces instrument_id + type +
state + reasons + framework refs.

Pure stdlib (Decimal + frozen dataclasses + enums + date).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "TradeFinanceInstrumentsEngine implements ENH-269 — UCP "
    "600 / ISP98 / URDG 758 / URC 522 instrument lifecycle. "
    "Pure stdlib. Per Rule 1, every output surfaces full "
    "provenance. Per Rule 7, engine DIAGNOSTIC ONLY — never "
    "issues instruments, never amends, never honors drawdowns, "
    "never pays beneficiaries, never books accounting, never "
    "sends SWIFT messages, never mutates inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class InstrumentType(Enum):
    LC = "LC"                              # Documentary Letter of Credit
    SBLC = "SBLC"                          # Standby Letter of Credit
    BG = "BG"                              # Bank Guarantee
    DOC_COLLECTION = "DOC_COLLECTION"      # Documentary Collection (URC 522)
    CLEAN_COLLECTION = "CLEAN_COLLECTION"  # Clean Collection


class InstrumentState(Enum):
    DRAFT = "DRAFT"           # being prepared
    APPROVED = "APPROVED"     # approved internally, not yet issued
    ISSUED = "ISSUED"         # issued to beneficiary
    AMENDED = "AMENDED"       # amendment posted but not yet activated
    ACTIVE = "ACTIVE"         # live
    DRAWN = "DRAWN"           # wholly drawn
    EXPIRED = "EXPIRED"       # past expiry date, not drawn
    CANCELLED = "CANCELLED"   # cancelled before expiry
    REJECTED = "REJECTED"     # rejected at validation


class LcType(Enum):
    SIGHT = "SIGHT"
    USANCE = "USANCE"             # deferred payment
    RED_CLAUSE = "RED_CLAUSE"     # advance to beneficiary
    GREEN_CLAUSE = "GREEN_CLAUSE"
    TRANSFERABLE = "TRANSFERABLE"
    BACK_TO_BACK = "BACK_TO_BACK"
    REVOLVING = "REVOLVING"


class BgType(Enum):
    PAYMENT = "PAYMENT"
    PERFORMANCE = "PERFORMANCE"
    BID_BOND = "BID_BOND"
    ADVANCE_PAYMENT = "ADVANCE_PAYMENT"
    RETENTION_MONEY = "RETENTION_MONEY"
    WARRANTY = "WARRANTY"


class ExposureClassification(Enum):
    FUNDED = "FUNDED"
    UNFUNDED = "UNFUNDED"


class ValidationOutcome(Enum):
    VALID = "VALID"           # passes all rules
    WARNING = "WARNING"       # passes hard rules, soft concern raised
    INVALID = "INVALID"       # blocks issuance


class AgingBucket(Enum):
    """Pending-action buckets for portfolio review."""
    DRAFT_STALE = "DRAFT_STALE"               # DRAFT > 7 days
    APPROVED_NOT_ISSUED = "APPROVED_NOT_ISSUED"  # APPROVED > 3 days
    EXPIRY_IMMINENT = "EXPIRY_IMMINENT"       # expires in ≤ 7 days
    EXPIRED_OPEN = "EXPIRED_OPEN"             # past expiry, not closed
    NORMAL = "NORMAL"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TradeInstrument:
    instrument_id: str
    instrument_type: InstrumentType
    state: InstrumentState
    applicant: str         # importer / principal
    beneficiary: str
    issuing_bank: str
    advising_bank: Optional[str]   # may be None for BG
    amount_kes: Decimal
    currency: str
    issue_date: date
    expiry_date: date
    tenor_days: int        # for usance LCs: deferred payment days
    lc_type: Optional[LcType] = None      # required for LC
    bg_type: Optional[BgType] = None      # required for BG
    drawn_amount_kes: Decimal = field(default=Decimal("0"))
    has_partial_shipments: bool = False
    has_transhipment_allowed: bool = False
    incoterms: str = ""    # e.g. "FOB", "CIF" — may be empty for SBLC
    description_of_goods: str = ""

    def __post_init__(self) -> None:
        if not self.instrument_id:
            raise ValueError("instrument_id must be non-empty")
        if not self.applicant:
            raise ValueError("applicant must be non-empty")
        if not self.beneficiary:
            raise ValueError("beneficiary must be non-empty")
        if self.applicant == self.beneficiary:
            raise ValueError(
                "applicant must differ from beneficiary")
        if self.amount_kes <= 0:
            raise ValueError("amount_kes must be > 0")
        if self.drawn_amount_kes < 0:
            raise ValueError("drawn_amount_kes must be ≥ 0")
        if self.drawn_amount_kes > self.amount_kes:
            raise ValueError(
                "drawn_amount_kes cannot exceed amount_kes")
        if not self.currency:
            raise ValueError("currency must be non-empty")
        if self.expiry_date < self.issue_date:
            raise ValueError(
                "expiry_date cannot be before issue_date")
        if self.tenor_days < 0:
            raise ValueError("tenor_days must be ≥ 0")
        # Type-specific validation
        if self.instrument_type == InstrumentType.LC:
            if self.lc_type is None:
                raise ValueError(
                    "LC instrument requires lc_type")
        if self.instrument_type == InstrumentType.BG:
            if self.bg_type is None:
                raise ValueError(
                    "BG instrument requires bg_type")


@dataclass(frozen=True)
class AmendmentRequest:
    amendment_id: str
    instrument_id: str
    amendment_date: date
    new_amount_kes: Optional[Decimal]
    new_expiry_date: Optional[date]
    new_description: Optional[str]
    beneficiary_consent: bool   # required for LC/SBLC per UCP 600 §10
    reason: str

    def __post_init__(self) -> None:
        if not self.amendment_id:
            raise ValueError("amendment_id must be non-empty")
        if not self.instrument_id:
            raise ValueError("instrument_id must be non-empty")
        if not self.reason:
            raise ValueError("reason must be non-empty")
        if (
            self.new_amount_kes is None
            and self.new_expiry_date is None
            and self.new_description is None
        ):
            raise ValueError(
                "amendment must change at least one field")
        if (
            self.new_amount_kes is not None
            and self.new_amount_kes <= 0
        ):
            raise ValueError(
                "new_amount_kes must be > 0 if specified")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IssuanceValidation:
    instrument_id: str
    instrument_type: InstrumentType
    outcome: ValidationOutcome
    reasons: Tuple[str, ...]
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TransitionValidation:
    instrument_id: str
    from_state: InstrumentState
    to_state: InstrumentState
    is_allowed: bool
    reason: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AmendmentValidation:
    amendment_id: str
    instrument_id: str
    instrument_type: InstrumentType
    outcome: ValidationOutcome
    reasons: Tuple[str, ...]
    requires_beneficiary_consent: bool
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExposureMeasurement:
    instrument_id: str
    instrument_type: InstrumentType
    classification: ExposureClassification
    notional_kes: Decimal
    drawn_kes: Decimal
    undrawn_kes: Decimal
    contingent_liability_kes: Decimal   # for unfunded
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AgingFinding:
    instrument_id: str
    instrument_type: InstrumentType
    state: InstrumentState
    bucket: AgingBucket
    days_in_bucket: int
    description: str
    framework_refs: Tuple[str, ...] = ()


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceInstrumentsEngine:
    """Diagnostic trade finance instrument lifecycle engine."""

    # State transition matrix (from_state -> set of allowed to_states)
    STATE_TRANSITIONS: Dict[
        InstrumentState, Tuple[InstrumentState, ...]] = {
        InstrumentState.DRAFT: (
            InstrumentState.APPROVED,
            InstrumentState.REJECTED,
            InstrumentState.CANCELLED),
        InstrumentState.APPROVED: (
            InstrumentState.ISSUED,
            InstrumentState.CANCELLED),
        InstrumentState.ISSUED: (
            InstrumentState.ACTIVE,
            InstrumentState.AMENDED,
            InstrumentState.CANCELLED,
            InstrumentState.EXPIRED),
        InstrumentState.ACTIVE: (
            InstrumentState.AMENDED,
            InstrumentState.DRAWN,
            InstrumentState.EXPIRED,
            InstrumentState.CANCELLED),
        InstrumentState.AMENDED: (
            InstrumentState.ACTIVE,
            InstrumentState.CANCELLED,
            InstrumentState.EXPIRED),
        InstrumentState.DRAWN: (),       # terminal
        InstrumentState.EXPIRED: (),     # terminal
        InstrumentState.CANCELLED: (),   # terminal
        InstrumentState.REJECTED: (),    # terminal
    }

    # Maximum allowed tenor for LC issuance (days)
    MAX_LC_TENOR_DAYS: int = 365
    MAX_LC_USANCE_DAYS: int = 180

    # Soft warning thresholds for tenor (long-tenor concern)
    LONG_TENOR_WARNING_DAYS: int = 270
    LONG_USANCE_WARNING_DAYS: int = 120

    # Aging thresholds
    DRAFT_STALE_DAYS: int = 7
    APPROVED_NOT_ISSUED_DAYS: int = 3
    EXPIRY_IMMINENT_DAYS: int = 7

    # Framework reference per instrument type
    FRAMEWORK_REFS: Dict[InstrumentType, Tuple[str, ...]] = {
        InstrumentType.LC: (
            "UCP 600 — Uniform Customs and Practice for "
            "Documentary Credits (ICC Pub. 600)",
            "ISBP 745 — International Standard Banking "
            "Practice"),
        InstrumentType.SBLC: (
            "ISP98 — International Standby Practices (ICC "
            "Pub. 590)",
            "UCP 600 (alternative governing rules permitted)"),
        InstrumentType.BG: (
            "URDG 758 — Uniform Rules for Demand Guarantees "
            "(ICC Pub. 758)",),
        InstrumentType.DOC_COLLECTION: (
            "URC 522 — Uniform Rules for Collections (ICC "
            "Pub. 522)",),
        InstrumentType.CLEAN_COLLECTION: (
            "URC 522 — Uniform Rules for Collections (ICC "
            "Pub. 522)",),
    }

    def validate_issuance(
        self, instrument: TradeInstrument,
    ) -> IssuanceValidation:
        reasons: List[str] = []
        outcome = ValidationOutcome.VALID

        # State check — only DRAFT or APPROVED can be issuance-validated
        if instrument.state not in (
            InstrumentState.DRAFT,
            InstrumentState.APPROVED,
        ):
            reasons.append(
                f"instrument state {instrument.state.value} — "
                f"only DRAFT or APPROVED can be validated for "
                f"issuance")
            outcome = ValidationOutcome.INVALID

        # Tenor — issue to expiry
        tenor = (
            instrument.expiry_date - instrument.issue_date).days
        if instrument.instrument_type == InstrumentType.LC:
            if tenor > self.MAX_LC_TENOR_DAYS:
                reasons.append(
                    f"LC issue→expiry {tenor}d exceeds policy "
                    f"max {self.MAX_LC_TENOR_DAYS}d")
                outcome = ValidationOutcome.INVALID
            elif tenor > self.LONG_TENOR_WARNING_DAYS:
                reasons.append(
                    f"LC issue→expiry {tenor}d exceeds "
                    f"warning threshold "
                    f"{self.LONG_TENOR_WARNING_DAYS}d — "
                    f"review counterparty exposure")
                if outcome == ValidationOutcome.VALID:
                    outcome = ValidationOutcome.WARNING
            # Usance LCs — tenor_days is deferred payment period
            if (
                instrument.lc_type == LcType.USANCE
                and instrument.tenor_days
                > self.MAX_LC_USANCE_DAYS
            ):
                reasons.append(
                    f"USANCE LC tenor {instrument.tenor_days}d "
                    f"exceeds max {self.MAX_LC_USANCE_DAYS}d")
                outcome = ValidationOutcome.INVALID

        # LC requires advising bank for cross-border (best practice)
        if instrument.instrument_type == InstrumentType.LC:
            if not instrument.advising_bank:
                reasons.append(
                    "LC issued without advising bank — "
                    "review per UCP 600 §9 advising "
                    "discipline")
                if outcome == ValidationOutcome.VALID:
                    outcome = ValidationOutcome.WARNING

        # Description of goods required for LC + Doc Collection
        if instrument.instrument_type in (
            InstrumentType.LC,
            InstrumentType.DOC_COLLECTION,
        ):
            if not instrument.description_of_goods.strip():
                reasons.append(
                    f"{instrument.instrument_type.value} "
                    f"requires description_of_goods")
                outcome = ValidationOutcome.INVALID

        # Incoterms required for LC and Doc Collection
        if instrument.instrument_type in (
            InstrumentType.LC,
            InstrumentType.DOC_COLLECTION,
        ):
            if not instrument.incoterms.strip():
                reasons.append(
                    "incoterms required (e.g. FOB, CIF, EXW) "
                    "for shipped-goods instruments")
                outcome = ValidationOutcome.INVALID

        # SBLC + BG do not require incoterms or goods description
        # — financial / standby instruments

        # Issue date not in past beyond reasonable window
        # (we don't fail on past dates — caller's clock)
        # but flag if expiry is already past
        if instrument.expiry_date < instrument.issue_date:
            # caught at construction, but defensive
            reasons.append("expiry before issue date")
            outcome = ValidationOutcome.INVALID

        if outcome == ValidationOutcome.VALID and not reasons:
            reasons.append(
                "all field-level + business-rule checks passed")

        framework = (
            "ENH-269 §validate_issuance",
        ) + self.FRAMEWORK_REFS[instrument.instrument_type] + (
            "Per Rule 7 — never issues; surfaces validation "
            "outcome for operator approval",)

        return IssuanceValidation(
            instrument_id=instrument.instrument_id,
            instrument_type=instrument.instrument_type,
            outcome=outcome,
            reasons=tuple(reasons),
            framework_refs=framework,
        )

    def validate_state_transition(
        self,
        instrument_id: str,
        from_state: InstrumentState,
        to_state: InstrumentState,
        instrument_type: InstrumentType,
    ) -> TransitionValidation:
        allowed = self.STATE_TRANSITIONS.get(from_state, ())
        is_allowed = to_state in allowed
        if is_allowed:
            reason = (
                f"transition {from_state.value} → "
                f"{to_state.value} is permitted per state "
                f"machine")
        else:
            allowed_str = (
                ", ".join(s.value for s in allowed)
                if allowed
                else "<none — terminal state>")
            reason = (
                f"transition {from_state.value} → "
                f"{to_state.value} not permitted; allowed "
                f"transitions from {from_state.value}: "
                f"{allowed_str}")
        return TransitionValidation(
            instrument_id=instrument_id,
            from_state=from_state,
            to_state=to_state,
            is_allowed=is_allowed,
            reason=reason,
            framework_refs=(
                "ENH-269 §validate_state_transition",
            ) + self.FRAMEWORK_REFS[instrument_type] + (
                "Per Rule 7 — never executes the transition",),
        )

    def validate_amendment(
        self,
        instrument: TradeInstrument,
        amendment: AmendmentRequest,
    ) -> AmendmentValidation:
        reasons: List[str] = []
        outcome = ValidationOutcome.VALID

        if instrument.instrument_id != amendment.instrument_id:
            reasons.append(
                f"amendment {amendment.amendment_id} references "
                f"{amendment.instrument_id} but instrument is "
                f"{instrument.instrument_id}")
            outcome = ValidationOutcome.INVALID

        # Amendments only allowed in ISSUED, AMENDED, or ACTIVE states
        amendable_states = (
            InstrumentState.ISSUED,
            InstrumentState.AMENDED,
            InstrumentState.ACTIVE,
        )
        if instrument.state not in amendable_states:
            reasons.append(
                f"instrument state {instrument.state.value} not "
                f"amendable; amendments allowed only from "
                f"{', '.join(s.value for s in amendable_states)}")
            outcome = ValidationOutcome.INVALID

        # Beneficiary consent — required for LC and SBLC per UCP 600 §10
        # Operator must capture this; engine surfaces requirement
        requires_consent = instrument.instrument_type in (
            InstrumentType.LC,
            InstrumentType.SBLC,
        )
        if requires_consent and not amendment.beneficiary_consent:
            reasons.append(
                f"{instrument.instrument_type.value} amendment "
                f"requires beneficiary consent per UCP 600 §10 "
                f"/ ISP98 §2.06 — beneficiary_consent flag is "
                f"False")
            outcome = ValidationOutcome.INVALID

        # New amount must not exceed regulatory ceiling check —
        # delegated to ENH-273 limits engine (this engine doesn't
        # know about counterparty/country/product limits)
        # We surface a soft note when amount increases > 25%
        if (
            amendment.new_amount_kes is not None
            and amendment.new_amount_kes
            > instrument.amount_kes * Decimal("1.25")
        ):
            reasons.append(
                f"amendment increases amount > 25% (from "
                f"{instrument.amount_kes} to "
                f"{amendment.new_amount_kes}) — review "
                f"counterparty exposure (delegate to limits "
                f"engine)")
            if outcome == ValidationOutcome.VALID:
                outcome = ValidationOutcome.WARNING

        # New expiry must be after issue date and not before today
        if (
            amendment.new_expiry_date is not None
            and amendment.new_expiry_date < instrument.issue_date
        ):
            reasons.append(
                "amendment expiry cannot precede instrument "
                "issue date")
            outcome = ValidationOutcome.INVALID

        if outcome == ValidationOutcome.VALID and not reasons:
            reasons.append(
                "amendment validation passed all checks")

        framework = (
            "ENH-269 §validate_amendment",
        ) + self.FRAMEWORK_REFS[instrument.instrument_type] + (
            "UCP 600 §10 — amendments require beneficiary "
            "consent for documentary credits",
            "Per Rule 7 — never applies the amendment",
        )

        return AmendmentValidation(
            amendment_id=amendment.amendment_id,
            instrument_id=amendment.instrument_id,
            instrument_type=instrument.instrument_type,
            outcome=outcome,
            reasons=tuple(reasons),
            requires_beneficiary_consent=requires_consent,
            framework_refs=framework,
        )

    def compute_exposure(
        self, instrument: TradeInstrument,
    ) -> ExposureMeasurement:
        """Funded vs unfunded contingent liability per IFRS 9 +
        IAS 37 disclosure. SBLC, BG, undrawn LC are unfunded
        contingent liabilities. DRAWN portion of LC becomes
        funded receivable from applicant."""
        notional = instrument.amount_kes
        drawn = instrument.drawn_amount_kes
        undrawn = notional - drawn

        if instrument.instrument_type in (
            InstrumentType.LC,
            InstrumentType.DOC_COLLECTION,
        ):
            # Drawn portion = funded receivable from applicant
            # Undrawn portion = unfunded contingent liability
            classification = (
                ExposureClassification.UNFUNDED
                if drawn == 0
                else ExposureClassification.FUNDED
                if drawn == notional
                else ExposureClassification.UNFUNDED)
            contingent = undrawn
        elif instrument.instrument_type in (
            InstrumentType.SBLC,
            InstrumentType.BG,
        ):
            # SBLC + BG: unfunded contingent liability for
            # the entire notional until drawn
            classification = (
                ExposureClassification.UNFUNDED
                if drawn == 0
                else ExposureClassification.FUNDED)
            contingent = undrawn
        else:
            # Clean collection — bank handles documents only,
            # no exposure to bank
            classification = ExposureClassification.UNFUNDED
            contingent = Decimal("0")

        return ExposureMeasurement(
            instrument_id=instrument.instrument_id,
            instrument_type=instrument.instrument_type,
            classification=classification,
            notional_kes=notional,
            drawn_kes=drawn,
            undrawn_kes=undrawn,
            contingent_liability_kes=contingent,
            framework_refs=(
                "ENH-269 §compute_exposure",
                "IFRS 9 §5.5 — credit risk on financial "
                "guarantee contracts",
                "IAS 37 §10 — contingent liability disclosure",
                "Basel III CCF — credit conversion factor for "
                "off-balance-sheet exposure (caller applies)",
            ),
        )

    def age_pending_actions(
        self,
        instruments: Sequence[TradeInstrument],
        as_of_date: date,
    ) -> Tuple[AgingFinding, ...]:
        findings: List[AgingFinding] = []
        for inst in instruments:
            bucket = AgingBucket.NORMAL
            description = ""
            days = 0
            if inst.state == InstrumentState.DRAFT:
                days = (as_of_date - inst.issue_date).days
                if days >= self.DRAFT_STALE_DAYS:
                    bucket = AgingBucket.DRAFT_STALE
                    description = (
                        f"DRAFT for {days}d (≥ "
                        f"{self.DRAFT_STALE_DAYS}d threshold) — "
                        f"abandon or progress to APPROVED")
            elif inst.state == InstrumentState.APPROVED:
                days = (as_of_date - inst.issue_date).days
                if days >= self.APPROVED_NOT_ISSUED_DAYS:
                    bucket = AgingBucket.APPROVED_NOT_ISSUED
                    description = (
                        f"APPROVED but not ISSUED for {days}d "
                        f"(≥ {self.APPROVED_NOT_ISSUED_DAYS}d "
                        f"threshold) — operator action "
                        f"required")
            elif inst.state in (
                InstrumentState.ISSUED,
                InstrumentState.ACTIVE,
                InstrumentState.AMENDED,
            ):
                days_to_expiry = (
                    inst.expiry_date - as_of_date).days
                if days_to_expiry < 0:
                    bucket = AgingBucket.EXPIRED_OPEN
                    days = -days_to_expiry
                    description = (
                        f"past expiry by {days}d but state "
                        f"still {inst.state.value} — close to "
                        f"EXPIRED")
                elif days_to_expiry <= self.EXPIRY_IMMINENT_DAYS:
                    bucket = AgingBucket.EXPIRY_IMMINENT
                    days = days_to_expiry
                    description = (
                        f"expires in {days}d (≤ "
                        f"{self.EXPIRY_IMMINENT_DAYS}d) — "
                        f"prepare drawdown or amendment")
            if bucket != AgingBucket.NORMAL:
                findings.append(AgingFinding(
                    instrument_id=inst.instrument_id,
                    instrument_type=inst.instrument_type,
                    state=inst.state,
                    bucket=bucket,
                    days_in_bucket=days,
                    description=description,
                    framework_refs=(
                        "ENH-269 §age_pending_actions",
                        "Per Rule 7 — surfaces aging only; "
                        "never auto-cancels or auto-expires",
                    ),
                ))
        return tuple(findings)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_lc(
    iid="LC-001", state=InstrumentState.DRAFT,
    issue=date(2026, 4, 1), expiry=date(2026, 6, 1),
    tenor_days=0, lc_type=LcType.SIGHT,
    amount=Decimal("1000000"), drawn=Decimal("0"),
    advising_bank="ABC Bank UK",
    incoterms="FOB Mombasa", goods="Cement bags 1000MT",
):
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state,
        applicant="Acme Imports Ltd",
        beneficiary="Beta Exports Ltd",
        issuing_bank="Ecobank Kenya",
        advising_bank=advising_bank,
        amount_kes=amount,
        currency="KES",
        issue_date=issue,
        expiry_date=expiry,
        tenor_days=tenor_days,
        lc_type=lc_type,
        drawn_amount_kes=drawn,
        incoterms=incoterms,
        description_of_goods=goods,
    )


def _make_bg(
    iid="BG-001", state=InstrumentState.DRAFT,
    bg_type=BgType.PERFORMANCE,
    amount=Decimal("5000000"),
):
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.BG,
        state=state,
        applicant="Acme Contractors",
        beneficiary="Kenya Roads Authority",
        issuing_bank="Ecobank Kenya",
        advising_bank=None,
        amount_kes=amount,
        currency="KES",
        issue_date=date(2026, 4, 1),
        expiry_date=date(2026, 10, 1),
        tenor_days=0,
        bg_type=bg_type,
    )


def _test_instrument_validates_required_fields():
    try:
        TradeInstrument(
            instrument_id="", instrument_type=InstrumentType.LC,
            state=InstrumentState.DRAFT,
            applicant="A", beneficiary="B",
            issuing_bank="X", advising_bank=None,
            amount_kes=Decimal("1000"), currency="KES",
            issue_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), tenor_days=0,
            lc_type=LcType.SIGHT)
        assert False
    except ValueError:
        pass


def _test_instrument_rejects_same_applicant_beneficiary():
    try:
        TradeInstrument(
            instrument_id="X", instrument_type=InstrumentType.LC,
            state=InstrumentState.DRAFT,
            applicant="A", beneficiary="A",
            issuing_bank="X", advising_bank=None,
            amount_kes=Decimal("1000"), currency="KES",
            issue_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), tenor_days=0,
            lc_type=LcType.SIGHT)
        assert False
    except ValueError:
        pass


def _test_instrument_rejects_drawn_exceeds_notional():
    try:
        _make_lc(
            amount=Decimal("100"), drawn=Decimal("200"))
        assert False
    except ValueError:
        pass


def _test_lc_requires_lc_type():
    try:
        TradeInstrument(
            instrument_id="X", instrument_type=InstrumentType.LC,
            state=InstrumentState.DRAFT,
            applicant="A", beneficiary="B",
            issuing_bank="X", advising_bank=None,
            amount_kes=Decimal("1000"), currency="KES",
            issue_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), tenor_days=0,
            lc_type=None)
        assert False
    except ValueError:
        pass


def _test_bg_requires_bg_type():
    try:
        TradeInstrument(
            instrument_id="X", instrument_type=InstrumentType.BG,
            state=InstrumentState.DRAFT,
            applicant="A", beneficiary="B",
            issuing_bank="X", advising_bank=None,
            amount_kes=Decimal("1000"), currency="KES",
            issue_date=date(2026, 1, 1),
            expiry_date=date(2026, 2, 1), tenor_days=0,
            bg_type=None)
        assert False
    except ValueError:
        pass


def _test_validate_clean_lc_passes():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc()
    v = eng.validate_issuance(inst)
    assert v.outcome == ValidationOutcome.VALID
    assert any(
        "ENH-269" in r for r in v.framework_refs)
    assert any(
        "UCP 600" in r for r in v.framework_refs)


def _test_lc_missing_goods_invalid():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(goods="")
    v = eng.validate_issuance(inst)
    assert v.outcome == ValidationOutcome.INVALID
    assert any(
        "description_of_goods" in r for r in v.reasons)


def _test_lc_missing_incoterms_invalid():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(incoterms="")
    v = eng.validate_issuance(inst)
    assert v.outcome == ValidationOutcome.INVALID
    assert any("incoterms" in r for r in v.reasons)


def _test_lc_long_tenor_warning():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        issue=date(2026, 1, 1),
        expiry=date(2026, 11, 1))   # 304d > 270d warning
    v = eng.validate_issuance(inst)
    assert v.outcome == ValidationOutcome.WARNING


def _test_lc_excessive_tenor_invalid():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        issue=date(2026, 1, 1),
        expiry=date(2027, 6, 1))   # > 365d max
    v = eng.validate_issuance(inst)
    assert v.outcome == ValidationOutcome.INVALID
    assert any("365d" in r for r in v.reasons)


def _test_usance_lc_excessive_tenor_invalid():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        lc_type=LcType.USANCE, tenor_days=200)
    v = eng.validate_issuance(inst)
    assert v.outcome == ValidationOutcome.INVALID
    assert any("USANCE" in r for r in v.reasons)


def _test_lc_no_advising_bank_warning():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(advising_bank=None)
    v = eng.validate_issuance(inst)
    # Still warning even with all other fields populated
    assert v.outcome == ValidationOutcome.WARNING
    assert any("advising bank" in r for r in v.reasons)


def _test_bg_does_not_require_goods_or_incoterms():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_bg()
    v = eng.validate_issuance(inst)
    # Should not fail just because BG has no goods/incoterms
    assert v.outcome != ValidationOutcome.INVALID


def _test_validate_state_transition_allowed():
    eng = TradeFinanceInstrumentsEngine()
    t = eng.validate_state_transition(
        "X",
        InstrumentState.DRAFT, InstrumentState.APPROVED,
        InstrumentType.LC)
    assert t.is_allowed is True


def _test_validate_state_transition_disallowed():
    eng = TradeFinanceInstrumentsEngine()
    # DRAWN is terminal
    t = eng.validate_state_transition(
        "X",
        InstrumentState.DRAWN, InstrumentState.ACTIVE,
        InstrumentType.LC)
    assert t.is_allowed is False
    assert "not permitted" in t.reason


def _test_validate_state_transition_skip_states_disallowed():
    eng = TradeFinanceInstrumentsEngine()
    # Can't go directly DRAFT → ISSUED (must approve first)
    t = eng.validate_state_transition(
        "X",
        InstrumentState.DRAFT, InstrumentState.ISSUED,
        InstrumentType.LC)
    assert t.is_allowed is False


def _test_amendment_requires_beneficiary_consent_for_lc():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(state=InstrumentState.ACTIVE)
    amd = AmendmentRequest(
        amendment_id="A1", instrument_id=inst.instrument_id,
        amendment_date=date(2026, 4, 15),
        new_amount_kes=Decimal("1500000"),
        new_expiry_date=None, new_description=None,
        beneficiary_consent=False,
        reason="amount uplift")
    v = eng.validate_amendment(inst, amd)
    assert v.outcome == ValidationOutcome.INVALID
    assert v.requires_beneficiary_consent is True
    assert any(
        "beneficiary consent" in r for r in v.reasons)


def _test_amendment_with_consent_passes_for_lc():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(state=InstrumentState.ACTIVE)
    amd = AmendmentRequest(
        amendment_id="A1", instrument_id=inst.instrument_id,
        amendment_date=date(2026, 4, 15),
        new_amount_kes=Decimal("1100000"),
        new_expiry_date=None, new_description=None,
        beneficiary_consent=True,
        reason="amount uplift")
    v = eng.validate_amendment(inst, amd)
    assert v.outcome == ValidationOutcome.VALID


def _test_amendment_in_draft_state_invalid():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(state=InstrumentState.DRAFT)
    amd = AmendmentRequest(
        amendment_id="A1", instrument_id=inst.instrument_id,
        amendment_date=date(2026, 4, 15),
        new_amount_kes=None,
        new_expiry_date=date(2026, 8, 1),
        new_description=None,
        beneficiary_consent=True,
        reason="extend expiry")
    v = eng.validate_amendment(inst, amd)
    assert v.outcome == ValidationOutcome.INVALID


def _test_amendment_id_mismatch_invalid():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        iid="LC-001", state=InstrumentState.ACTIVE)
    amd = AmendmentRequest(
        amendment_id="A1", instrument_id="LC-OTHER",
        amendment_date=date(2026, 4, 15),
        new_amount_kes=None,
        new_expiry_date=date(2026, 8, 1),
        new_description=None,
        beneficiary_consent=True, reason="x")
    v = eng.validate_amendment(inst, amd)
    assert v.outcome == ValidationOutcome.INVALID


def _test_bg_amendment_does_not_require_consent():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_bg(state=InstrumentState.ACTIVE)
    amd = AmendmentRequest(
        amendment_id="A1", instrument_id=inst.instrument_id,
        amendment_date=date(2026, 4, 15),
        new_amount_kes=None,
        new_expiry_date=date(2026, 12, 1),
        new_description=None,
        beneficiary_consent=False,   # not required for BG
        reason="extend")
    v = eng.validate_amendment(inst, amd)
    assert v.requires_beneficiary_consent is False
    # No consent issue flagged
    assert not any(
        "beneficiary consent" in r for r in v.reasons)


def _test_compute_exposure_undrawn_lc():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        amount=Decimal("1000000"), drawn=Decimal("0"))
    e = eng.compute_exposure(inst)
    assert e.classification == ExposureClassification.UNFUNDED
    assert e.contingent_liability_kes == Decimal("1000000")
    assert e.drawn_kes == Decimal("0")


def _test_compute_exposure_partially_drawn_lc():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        amount=Decimal("1000000"), drawn=Decimal("400000"))
    e = eng.compute_exposure(inst)
    assert e.drawn_kes == Decimal("400000")
    assert e.undrawn_kes == Decimal("600000")
    assert e.contingent_liability_kes == Decimal("600000")


def _test_compute_exposure_bg_full_unfunded():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_bg(amount=Decimal("5000000"))
    e = eng.compute_exposure(inst)
    assert e.classification == ExposureClassification.UNFUNDED
    assert e.contingent_liability_kes == Decimal("5000000")


def _test_aging_draft_stale():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        state=InstrumentState.DRAFT,
        issue=date(2026, 4, 1))
    findings = eng.age_pending_actions(
        (inst,), as_of_date=date(2026, 4, 15))   # 14d
    assert len(findings) == 1
    assert findings[0].bucket == AgingBucket.DRAFT_STALE


def _test_aging_expiry_imminent():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        state=InstrumentState.ACTIVE,
        issue=date(2026, 1, 1),
        expiry=date(2026, 4, 20))
    findings = eng.age_pending_actions(
        (inst,), as_of_date=date(2026, 4, 15))   # 5d to expiry
    assert len(findings) == 1
    assert findings[0].bucket == AgingBucket.EXPIRY_IMMINENT


def _test_aging_expired_open():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        state=InstrumentState.ACTIVE,
        issue=date(2026, 1, 1),
        expiry=date(2026, 4, 1))
    findings = eng.age_pending_actions(
        (inst,), as_of_date=date(2026, 4, 15))
    assert findings[0].bucket == AgingBucket.EXPIRED_OPEN


def _test_aging_normal_state_no_finding():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(
        state=InstrumentState.ACTIVE,
        issue=date(2026, 1, 1),
        expiry=date(2026, 12, 1))
    findings = eng.age_pending_actions(
        (inst,), as_of_date=date(2026, 4, 15))
    assert len(findings) == 0


def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc(amount=Decimal("1000000"))
    eng.validate_issuance(inst)
    eng.compute_exposure(inst)
    eng.age_pending_actions(
        (inst,), as_of_date=date(2026, 4, 15))
    assert inst.amount_kes == Decimal("1000000")
    assert inst.state == InstrumentState.DRAFT


def _test_full_provenance():
    eng = TradeFinanceInstrumentsEngine()
    inst = _make_lc()
    v = eng.validate_issuance(inst)
    assert any(
        "ENH-269" in r for r in v.framework_refs)
    assert any(
        "UCP 600" in r for r in v.framework_refs)
    assert any(
        "Rule 7" in r for r in v.framework_refs)


def self_test() -> None:
    tests = [
        _test_instrument_validates_required_fields,
        _test_instrument_rejects_same_applicant_beneficiary,
        _test_instrument_rejects_drawn_exceeds_notional,
        _test_lc_requires_lc_type,
        _test_bg_requires_bg_type,
        _test_validate_clean_lc_passes,
        _test_lc_missing_goods_invalid,
        _test_lc_missing_incoterms_invalid,
        _test_lc_long_tenor_warning,
        _test_lc_excessive_tenor_invalid,
        _test_usance_lc_excessive_tenor_invalid,
        _test_lc_no_advising_bank_warning,
        _test_bg_does_not_require_goods_or_incoterms,
        _test_validate_state_transition_allowed,
        _test_validate_state_transition_disallowed,
        _test_validate_state_transition_skip_states_disallowed,
        _test_amendment_requires_beneficiary_consent_for_lc,
        _test_amendment_with_consent_passes_for_lc,
        _test_amendment_in_draft_state_invalid,
        _test_amendment_id_mismatch_invalid,
        _test_bg_amendment_does_not_require_consent,
        _test_compute_exposure_undrawn_lc,
        _test_compute_exposure_partially_drawn_lc,
        _test_compute_exposure_bg_full_unfunded,
        _test_aging_draft_stale,
        _test_aging_expiry_imminent,
        _test_aging_expired_open,
        _test_aging_normal_state_no_finding,
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
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_instruments self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_instruments self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

"""utils/trading_book_boundary.py — v10.41: Trading Book Boundary.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-MR-008 — Trading Book Boundary Classification                     ║
║  ENH-MR-009 — Trading Desk Definition & Risk Factor Mapping            ║
║  ENH-MR-010 — Boundary Crossing Approval Workflow                      ║
║  Cat A — composes with market_risk_factors / market_risk_limits        ║
╠════════════════════════════════════════════════════════════════════════╣
║  The Trading Book / Banking Book boundary determines which capital     ║
║  framework applies to which position:                                   ║
║    - TRADING BOOK → market risk capital (BCBS d352 FRTB)               ║
║    - BANKING BOOK → credit risk capital (BCBS d424 IRB) + IRRBB        ║
║                                                                         ║
║  Per BCBS d352 §A.4, the boundary is STRICT — instruments cannot be    ║
║  freely reclassified. Reclassification requires:                       ║
║    - Documented justification                                          ║
║    - Senior management approval                                        ║
║    - Capital surcharge if reclassification benefits the bank           ║
║    - Annual review of overall boundary policy                          ║
║                                                                         ║
║  The module implements three concerns in one file because they are    ║
║  inseparable in practice — you cannot classify without a desk to       ║
║  assign to, and you cannot reclassify without invoking the approval    ║
║  workflow. Splitting would introduce circular imports between three    ║
║  modules.                                                               ║
║                                                                         ║
║  Per Rule 7: the engine NEVER auto-approves reclassifications. Every  ║
║  request enters PENDING and requires explicit approve_reclassification ║
║  call with an approver_id. Capital surcharge is computed but never    ║
║  applied without approval. EU AI Act Art 14 oversight preserved.       ║
║                                                                         ║
║  Per Rule 1: every BookAssignment carries classification +             ║
║  instrument_type + trading_desk_id + justification + approved_by +     ║
║  effective_date + framework_refs. Every ReclassificationRequest +      ║
║  Approval carries full provenance.                                     ║
║                                                                         ║
║  Composes with:                                                         ║
║    - market_risk_factors.RiskFactorClass (TradingDesk.risk_classes)    ║
║    - market_risk_limits (TB-scope VaR/ES limits via classification)    ║
║    - core_audit (audit trail of every reclassification approval)       ║
║                                                                         ║
║  Regulatory sources:                                                    ║
║    - BCBS d352 §A.4 (FRTB boundary + trading desk concept)             ║
║    - BCBS d352 §A.4.5 (reclassification approval requirements)         ║
║    - BCBS d352 §A.4.2 (trading desk attributes)                        ║
║    - CBK PG/04 §3 (boundary policy, annual review)                     ║
║    - EBA/RTS/2017/06 (boundary technical standards)                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import (
    Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)

from utils.market_risk_factors import RiskFactorClass

SPEC_DEVIATION_NOTE = (
    "TradingBookBoundary implements the v10.41 BCBS d352 §A.4 "
    "boundary framework. Per Rule 7, BoundaryEngine never auto-"
    "approves reclassifications — every request enters PENDING and "
    "requires explicit approve_reclassification with approver_id "
    "(senior management per §A.4.5). Capital surcharge is COMPUTED "
    "for every benefit-side reclassification but never APPLIED "
    "without approval. Per Rule 1, every BookAssignment + "
    "ReclassificationRequest + ApprovalDecision carries full "
    "provenance. Boundary is documented as STRICT — presumptive "
    "lists per BCBS d352 §A.4 are non-overrideable without explicit "
    "request + approval cycle. Decimal-internal precision throughout."
)


# ════════════════════════════════════════════════════════════════════════
# Enums — book classification + instrument types
# ════════════════════════════════════════════════════════════════════════

class BookClassification(Enum):
    """The two regulatory books in the BCBS d352 framework."""
    TRADING_BOOK = "TRADING_BOOK"     # market risk capital (FRTB)
    BANKING_BOOK = "BANKING_BOOK"     # credit risk capital + IRRBB


class InstrumentType(Enum):
    """Instrument categories per BCBS d352 §A.4 presumptive lists.

    Each instrument type has a presumptive classification.
    Reclassification away from presumption requires senior management
    approval per §A.4.5.
    """
    # Presumptive trading book
    LISTED_EQUITY = "LISTED_EQUITY"
    EQUITY_FUND = "EQUITY_FUND"
    LISTED_DERIVATIVE = "LISTED_DERIVATIVE"
    OTC_DERIVATIVE_TRADING = "OTC_DERIVATIVE_TRADING"
    SECURITY_HELD_FOR_RESALE = "SECURITY_HELD_FOR_RESALE"
    REPO_REVERSE_REPO = "REPO_REVERSE_REPO"
    MARKET_MAKING_INVENTORY = "MARKET_MAKING_INVENTORY"
    COMMODITY_TRADING = "COMMODITY_TRADING"
    FX_TRADING = "FX_TRADING"
    # Presumptive banking book
    LOAN_RECEIVABLE = "LOAN_RECEIVABLE"
    DEPOSIT_LIABILITY = "DEPOSIT_LIABILITY"
    BANKING_BOOK_HEDGE = "BANKING_BOOK_HEDGE"
    SECURITISATION_BB = "SECURITISATION_BB"
    EQUITY_INVESTMENT_NON_TRADING = "EQUITY_INVESTMENT_NON_TRADING"
    REAL_ESTATE = "REAL_ESTATE"
    LIQUIDITY_BUFFER_HOLD = "LIQUIDITY_BUFFER_HOLD"
    # Edge cases — explicit per-position decision required
    UNCLASSIFIED = "UNCLASSIFIED"


# ════════════════════════════════════════════════════════════════════════
# Presumptive classification mapping
# ════════════════════════════════════════════════════════════════════════
# These are PRESUMPTIONS per BCBS d352 §A.4 — actual classification can
# be different but only via the approval workflow with documented
# justification.

PRESUMPTIVE_TRADING_BOOK: FrozenSet[InstrumentType] = frozenset({
    InstrumentType.LISTED_EQUITY,
    InstrumentType.EQUITY_FUND,
    InstrumentType.LISTED_DERIVATIVE,
    InstrumentType.OTC_DERIVATIVE_TRADING,
    InstrumentType.SECURITY_HELD_FOR_RESALE,
    InstrumentType.REPO_REVERSE_REPO,
    InstrumentType.MARKET_MAKING_INVENTORY,
    InstrumentType.COMMODITY_TRADING,
    InstrumentType.FX_TRADING,
})

PRESUMPTIVE_BANKING_BOOK: FrozenSet[InstrumentType] = frozenset({
    InstrumentType.LOAN_RECEIVABLE,
    InstrumentType.DEPOSIT_LIABILITY,
    InstrumentType.BANKING_BOOK_HEDGE,
    InstrumentType.SECURITISATION_BB,
    InstrumentType.EQUITY_INVESTMENT_NON_TRADING,
    InstrumentType.REAL_ESTATE,
    InstrumentType.LIQUIDITY_BUFFER_HOLD,
})


def presumptive_classification(
    instrument_type: InstrumentType,
) -> Optional[BookClassification]:
    """Return the presumptive book per BCBS d352 §A.4.

    UNCLASSIFIED returns None — explicit per-position decision needed.
    """
    if instrument_type in PRESUMPTIVE_TRADING_BOOK:
        return BookClassification.TRADING_BOOK
    if instrument_type in PRESUMPTIVE_BANKING_BOOK:
        return BookClassification.BANKING_BOOK
    return None    # UNCLASSIFIED


# ════════════════════════════════════════════════════════════════════════
# Trading desk
# ════════════════════════════════════════════════════════════════════════

class DeskValidationIssue(Enum):
    """What can be wrong with a TradingDesk per BCBS d352 §A.4.2."""
    MISSING_HEAD_TRADER = "MISSING_HEAD_TRADER"
    NO_RISK_CLASSES = "NO_RISK_CLASSES"
    INVALID_HOLDING_PERIOD = "INVALID_HOLDING_PERIOD"
    NO_MANDATE = "NO_MANDATE"
    OK = "OK"


@dataclass(frozen=True)
class TradingDesk:
    """A trading desk per BCBS d352 §A.4.2.

    Required attributes:
      - desk_id (unique)
      - name
      - head_trader (responsible person)
      - mandate (what the desk is allowed to trade)
      - risk_classes (which RiskFactorClass values it covers)
      - default_holding_period_days
      - parent_business_unit
    """
    desk_id: str
    name: str
    head_trader: str
    mandate: str
    risk_classes: FrozenSet[RiskFactorClass]
    default_holding_period_days: int
    parent_business_unit: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.desk_id:
            raise ValueError("desk_id required")
        if self.default_holding_period_days <= 0:
            raise ValueError(
                f"default_holding_period_days must be positive "
                f"(got {self.default_holding_period_days})")
        if not self.risk_classes:
            raise ValueError(
                f"desk {self.desk_id}: risk_classes must not be "
                f"empty per BCBS d352 §A.4.2")

    def validate(self) -> Tuple[DeskValidationIssue, ...]:
        """Self-check returning all issues found.

        Used by BoundaryEngine.validate_trading_desk_completeness.
        """
        issues: List[DeskValidationIssue] = []
        if not self.head_trader.strip():
            issues.append(DeskValidationIssue.MISSING_HEAD_TRADER)
        if not self.risk_classes:
            issues.append(DeskValidationIssue.NO_RISK_CLASSES)
        if self.default_holding_period_days <= 0:
            issues.append(DeskValidationIssue.INVALID_HOLDING_PERIOD)
        if not self.mandate.strip():
            issues.append(DeskValidationIssue.NO_MANDATE)
        if not issues:
            issues.append(DeskValidationIssue.OK)
        return tuple(issues)


# ════════════════════════════════════════════════════════════════════════
# Book assignment
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BookAssignment:
    """A position's book classification with full provenance.

    Per Rule 1, every assignment surfaces:
      - position_id
      - instrument_type (drives presumption)
      - classification (the actual book)
      - is_presumptive (True if classification == presumption)
      - trading_desk_id (required if TRADING_BOOK)
      - justification (required if non-presumptive)
      - approved_by (required if non-presumptive)
      - effective_date
      - framework_refs
    """
    position_id: str
    instrument_type: InstrumentType
    classification: BookClassification
    is_presumptive: bool
    effective_date: str
    trading_desk_id: Optional[str] = None
    justification: str = ""
    approved_by: str = ""
    framework_refs: Tuple[str, ...] = (
        "BCBS d352 §A.4", "CBK PG/04 §3")
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Reclassification workflow
# ════════════════════════════════════════════════════════════════════════

class ApprovalStatus(Enum):
    """States in the reclassification approval lifecycle.

    Mirrors treasury_agents.ApprovalStatus pattern for consistency.
    Per Rule 7, EXECUTED requires explicit approve + execute steps —
    the engine never moves PENDING → APPROVED autonomously.
    """
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class ReclassificationRequest:
    """A request to move a position between books.

    BCBS d352 §A.4.5: any reclassification requires
      - documented justification
      - senior management approval
      - capital surcharge if benefits the bank
      - cannot be reversed within same supervisory cycle
    """
    request_id: str
    position_id: str
    from_book: BookClassification
    to_book: BookClassification
    reason: str
    expected_capital_impact_kes: Decimal   # signed: positive = bank benefits
    requested_by: str
    request_date: str
    framework_refs: Tuple[str, ...] = (
        "BCBS d352 §A.4.5", "EBA/RTS/2017/06")

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError(
                f"request {self.request_id}: reason required per "
                f"BCBS d352 §A.4.5")
        if self.from_book == self.to_book:
            raise ValueError(
                f"request {self.request_id}: from_book == to_book "
                f"({self.from_book.value}) — no reclassification "
                f"needed")

    @property
    def benefits_bank_capitally(self) -> bool:
        """Triggers capital surcharge per §A.4.5 if True."""
        return self.expected_capital_impact_kes > 0


@dataclass(frozen=True)
class ApprovalDecision:
    """The outcome of a reclassification approval cycle.

    Per Rule 7, an ApprovalDecision is NEVER constructed
    autonomously by the engine — it requires explicit
    BoundaryEngine.approve_reclassification or
    reject_reclassification call by a human.
    """
    decision_id: str
    request_id: str
    status: ApprovalStatus
    decision_date: str
    approver: str
    capital_surcharge_kes: Decimal
    comments: str = ""
    framework_refs: Tuple[str, ...] = (
        "BCBS d352 §A.4.5",)


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

# Minimum capital surcharge per §A.4.5 — applied to reclassifications
# that benefit the bank's capital position. The Basel framework leaves
# the rate to supervisory discretion; CBK PG/04 §3 has not yet
# specified a number — using 100% of expected_capital_impact_kes as
# a conservative default that is overrideable in the engine.
DEFAULT_SURCHARGE_RATE = Decimal("1.0")


class BoundaryEngine:
    """The trading book boundary engine.

    Stateless aside from a desk registry — every operation is
    parametric. Composes with market_risk_factors for risk class
    validation when assigning positions to desks.

    Per Rule 7, the engine NEVER auto-approves reclassifications.
    All approval decisions require explicit caller action via
    approve_reclassification / reject_reclassification.
    """

    def __init__(
        self, *,
        surcharge_rate: Decimal = DEFAULT_SURCHARGE_RATE,
    ) -> None:
        if surcharge_rate < 0:
            raise ValueError(
                f"surcharge_rate must be non-negative "
                f"(got {surcharge_rate})")
        self.surcharge_rate = surcharge_rate
        self._desks: Dict[str, TradingDesk] = {}
        self._assignments: Dict[str, BookAssignment] = {}

    # ── Desk management ──────────────────────────────────────────────

    def register_desk(self, desk: TradingDesk) -> None:
        if desk.desk_id in self._desks:
            raise ValueError(
                f"desk {desk.desk_id} already registered")
        self._desks[desk.desk_id] = desk

    def get_desk(self, desk_id: str) -> TradingDesk:
        if desk_id not in self._desks:
            raise KeyError(f"unknown desk {desk_id}")
        return self._desks[desk_id]

    def all_desks(self) -> Tuple[TradingDesk, ...]:
        return tuple(self._desks.values())

    def validate_trading_desk_completeness(
        self,
    ) -> Mapping[str, Tuple[DeskValidationIssue, ...]]:
        """Per BCBS d352 §A.4.2: every desk must have all attributes.

        Returns desk_id → tuple of issues. Desks where the only issue
        is OK pass validation.
        """
        out: Dict[str, Tuple[DeskValidationIssue, ...]] = {}
        for desk_id, desk in self._desks.items():
            out[desk_id] = desk.validate()
        return out

    # ── Classification ───────────────────────────────────────────────

    def classify(
        self, *,
        position_id: str,
        instrument_type: InstrumentType,
        effective_date: str,
        trading_desk_id: Optional[str] = None,
        override_to: Optional[BookClassification] = None,
        justification: str = "",
        approved_by: str = "",
    ) -> BookAssignment:
        """Assign a position to a book per BCBS d352 §A.4.

        Defaults to presumptive classification. To override the
        presumption, set override_to + justification + approved_by
        (senior management). Per §A.4.5, the override pathway here
        is for INITIAL classification — moving an already-assigned
        position requires the reclassification workflow.

        Trading book assignments must specify trading_desk_id per
        §A.4.2.
        """
        presumption = presumptive_classification(instrument_type)
        if override_to is None:
            if presumption is None:
                raise ValueError(
                    f"instrument_type {instrument_type.value} has "
                    f"no presumptive classification — supply "
                    f"override_to + justification + approved_by")
            classification = presumption
            is_presumptive = True
        else:
            if not justification.strip():
                raise ValueError(
                    f"override requires justification per "
                    f"BCBS d352 §A.4")
            if not approved_by.strip():
                raise ValueError(
                    f"override requires approved_by per "
                    f"BCBS d352 §A.4.5 (senior management)")
            classification = override_to
            is_presumptive = (
                presumption is not None
                and override_to == presumption)
        if classification == BookClassification.TRADING_BOOK:
            if trading_desk_id is None:
                raise ValueError(
                    f"TRADING_BOOK assignment requires "
                    f"trading_desk_id per BCBS d352 §A.4.2")
            if trading_desk_id not in self._desks:
                raise ValueError(
                    f"unknown trading desk {trading_desk_id}")
        else:
            if trading_desk_id is not None:
                raise ValueError(
                    f"BANKING_BOOK assignment must not have "
                    f"trading_desk_id")
        assignment = BookAssignment(
            position_id=position_id,
            instrument_type=instrument_type,
            classification=classification,
            is_presumptive=is_presumptive,
            trading_desk_id=trading_desk_id,
            effective_date=effective_date,
            justification=justification,
            approved_by=approved_by)
        self._assignments[position_id] = assignment
        return assignment

    def get_assignment(
        self, position_id: str,
    ) -> BookAssignment:
        if position_id not in self._assignments:
            raise KeyError(
                f"no assignment for position {position_id}")
        return self._assignments[position_id]

    def positions_in_book(
        self, classification: BookClassification,
    ) -> Tuple[str, ...]:
        return tuple(
            pid for pid, a in self._assignments.items()
            if a.classification == classification)

    def positions_on_desk(
        self, desk_id: str,
    ) -> Tuple[str, ...]:
        return tuple(
            pid for pid, a in self._assignments.items()
            if a.trading_desk_id == desk_id)

    # ── Reclassification workflow ────────────────────────────────────

    def request_reclassification(
        self, *,
        request_id: str,
        position_id: str,
        to_book: BookClassification,
        reason: str,
        expected_capital_impact_kes: Decimal,
        requested_by: str,
        request_date: str,
    ) -> ReclassificationRequest:
        """Create a PENDING reclassification request.

        Per Rule 7, this method NEVER changes the assignment — it
        only records the request. The actual book change requires
        a subsequent approve_reclassification call.
        """
        current = self.get_assignment(position_id)
        return ReclassificationRequest(
            request_id=request_id,
            position_id=position_id,
            from_book=current.classification,
            to_book=to_book,
            reason=reason,
            expected_capital_impact_kes=Decimal(
                str(expected_capital_impact_kes)),
            requested_by=requested_by,
            request_date=request_date)

    def compute_capital_surcharge(
        self, request: ReclassificationRequest,
    ) -> Decimal:
        """Surcharge per BCBS d352 §A.4.5.

        Applied only when the reclassification benefits the bank
        capitally (positive expected_capital_impact_kes). Floor at 0.
        """
        if not request.benefits_bank_capitally:
            return Decimal("0")
        return (
            request.expected_capital_impact_kes
            * self.surcharge_rate)

    def approve_reclassification(
        self, *,
        request: ReclassificationRequest,
        approver: str,
        decision_date: str,
        decision_id: str,
        comments: str = "",
        new_trading_desk_id: Optional[str] = None,
    ) -> Tuple[ApprovalDecision, BookAssignment]:
        """Approve a reclassification — explicit human action.

        Per Rule 7, this method is the ONLY path from PENDING to
        APPROVED. It requires an explicit approver_id (senior
        management per BCBS d352 §A.4.5).

        Side effects:
          - Updates the assignment to the new classification
          - Computes and records the capital surcharge
          - Returns the ApprovalDecision + updated BookAssignment

        Caller is responsible for actually applying the surcharge
        to capital — this engine surfaces it as a Decimal but does
        not reach into capital_adequacy.
        """
        if not approver.strip():
            raise ValueError(
                "approver required (senior management per "
                "BCBS d352 §A.4.5)")
        if (request.to_book == BookClassification.TRADING_BOOK
                and new_trading_desk_id is None):
            raise ValueError(
                "approval to TRADING_BOOK requires "
                "new_trading_desk_id")
        if (request.to_book == BookClassification.TRADING_BOOK
                and new_trading_desk_id not in self._desks):
            raise ValueError(
                f"unknown trading desk {new_trading_desk_id}")
        surcharge = self.compute_capital_surcharge(request)
        decision = ApprovalDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            status=ApprovalStatus.APPROVED,
            decision_date=decision_date,
            approver=approver,
            capital_surcharge_kes=surcharge,
            comments=comments)
        # Update the assignment
        existing = self._assignments[request.position_id]
        new_assignment = BookAssignment(
            position_id=existing.position_id,
            instrument_type=existing.instrument_type,
            classification=request.to_book,
            is_presumptive=False,    # reclassified is never presumptive
            trading_desk_id=(
                new_trading_desk_id
                if request.to_book == BookClassification.TRADING_BOOK
                else None),
            effective_date=decision_date,
            justification=request.reason,
            approved_by=approver,
            notes=(
                f"reclassified from {request.from_book.value}; "
                f"surcharge KES {surcharge}; "
                f"decision_id={decision_id}"))
        self._assignments[request.position_id] = new_assignment
        return (decision, new_assignment)

    def reject_reclassification(
        self, *,
        request: ReclassificationRequest,
        approver: str,
        decision_date: str,
        decision_id: str,
        comments: str = "",
    ) -> ApprovalDecision:
        """Reject a reclassification — assignment unchanged."""
        if not approver.strip():
            raise ValueError("approver required")
        return ApprovalDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            status=ApprovalStatus.REJECTED,
            decision_date=decision_date,
            approver=approver,
            capital_surcharge_kes=Decimal("0"),
            comments=comments)

    # ── Reporting ────────────────────────────────────────────────────

    def summary(self) -> Mapping[str, Any]:
        n_total = len(self._assignments)
        n_tb = len(self.positions_in_book(
            BookClassification.TRADING_BOOK))
        n_bb = len(self.positions_in_book(
            BookClassification.BANKING_BOOK))
        n_non_presumptive = sum(
            1 for a in self._assignments.values()
            if not a.is_presumptive)
        return {
            "n_positions": n_total,
            "n_trading_book": n_tb,
            "n_banking_book": n_bb,
            "n_non_presumptive": n_non_presumptive,
            "n_desks": len(self._desks),
        }


# ════════════════════════════════════════════════════════════════════════
# Default illustrative trading desks for Ecobank Kenya
# ════════════════════════════════════════════════════════════════════════

DEFAULT_DESK_FX = TradingDesk(
    desk_id="DESK-FX-NAIROBI",
    name="FX Trading Desk Nairobi",
    head_trader="<head trader name>",
    mandate=(
        "Make markets in USD/KES, EUR/KES, GBP/KES; manage net "
        "open position within CBK PG/04 §4.3 limits"),
    risk_classes=frozenset({RiskFactorClass.FOREIGN_EXCHANGE}),
    default_holding_period_days=1,
    parent_business_unit="Treasury & Markets")

DEFAULT_DESK_FIXED_INCOME = TradingDesk(
    desk_id="DESK-FI-NAIROBI",
    name="Fixed Income Trading Desk",
    head_trader="<head trader name>",
    mandate=(
        "Trade KES-denominated GoK paper, T-bills, T-bonds, "
        "corporate bonds; market-making in NSE-listed bonds"),
    risk_classes=frozenset({
        RiskFactorClass.INTEREST_RATE,
        RiskFactorClass.CREDIT_SPREAD}),
    default_holding_period_days=10,
    parent_business_unit="Treasury & Markets")

DEFAULT_DESK_EQUITY = TradingDesk(
    desk_id="DESK-EQ-NAIROBI",
    name="Equity Trading Desk",
    head_trader="<head trader name>",
    mandate=(
        "Trade NSE-listed equities for proprietary book and "
        "client facilitation; equity derivatives as available"),
    risk_classes=frozenset({RiskFactorClass.EQUITY}),
    default_holding_period_days=5,
    parent_business_unit="Treasury & Markets")

ALL_DEFAULT_DESKS: Tuple[TradingDesk, ...] = (
    DEFAULT_DESK_FX,
    DEFAULT_DESK_FIXED_INCOME,
    DEFAULT_DESK_EQUITY,
)


def build_default_engine() -> BoundaryEngine:
    """Build a BoundaryEngine pre-populated with default desks.

    Provided for tests, scenarios, demos. Production wiring would
    load desks from the database.
    """
    engine = BoundaryEngine()
    for desk in ALL_DEFAULT_DESKS:
        engine.register_desk(desk)
    return engine


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_presumptive_classification_basic():
    assert (
        presumptive_classification(InstrumentType.LISTED_EQUITY)
        == BookClassification.TRADING_BOOK)
    assert (
        presumptive_classification(InstrumentType.LOAN_RECEIVABLE)
        == BookClassification.BANKING_BOOK)
    assert (
        presumptive_classification(InstrumentType.UNCLASSIFIED)
        is None)


def _test_presumptive_lists_disjoint():
    """No instrument can be in both presumption sets."""
    intersection = (
        PRESUMPTIVE_TRADING_BOOK & PRESUMPTIVE_BANKING_BOOK)
    assert len(intersection) == 0


def _test_trading_desk_validation_complete():
    desk = TradingDesk(
        desk_id="D1", name="Test", head_trader="Alice",
        mandate="Test mandate",
        risk_classes=frozenset({RiskFactorClass.FOREIGN_EXCHANGE}),
        default_holding_period_days=1,
        parent_business_unit="Treasury")
    issues = desk.validate()
    assert issues == (DeskValidationIssue.OK,)


def _test_trading_desk_rejects_zero_holding_period():
    try:
        TradingDesk(
            desk_id="D1", name="Test", head_trader="Alice",
            mandate="x",
            risk_classes=frozenset({RiskFactorClass.EQUITY}),
            default_holding_period_days=0,
            parent_business_unit="Treasury")
        assert False
    except ValueError:
        pass


def _test_trading_desk_requires_risk_classes():
    try:
        TradingDesk(
            desk_id="D1", name="Test", head_trader="Alice",
            mandate="x",
            risk_classes=frozenset(),
            default_holding_period_days=1,
            parent_business_unit="Treasury")
        assert False
    except ValueError:
        pass


def _test_classify_listed_equity_to_trading_book():
    engine = build_default_engine()
    a = engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    assert a.classification == BookClassification.TRADING_BOOK
    assert a.is_presumptive
    assert a.trading_desk_id == "DESK-EQ-NAIROBI"


def _test_classify_loan_to_banking_book():
    engine = build_default_engine()
    a = engine.classify(
        position_id="L1",
        instrument_type=InstrumentType.LOAN_RECEIVABLE,
        effective_date="2026-01-15")
    assert a.classification == BookClassification.BANKING_BOOK
    assert a.is_presumptive
    assert a.trading_desk_id is None


def _test_trading_book_requires_desk():
    engine = build_default_engine()
    try:
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15")  # no desk
        assert False
    except ValueError:
        pass


def _test_banking_book_must_not_have_desk():
    engine = build_default_engine()
    try:
        engine.classify(
            position_id="L1",
            instrument_type=InstrumentType.LOAN_RECEIVABLE,
            effective_date="2026-01-15",
            trading_desk_id="DESK-FI-NAIROBI")
        assert False
    except ValueError:
        pass


def _test_unknown_desk_rejected():
    engine = build_default_engine()
    try:
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-NONEXISTENT")
        assert False
    except ValueError:
        pass


def _test_unclassified_requires_explicit_override():
    engine = build_default_engine()
    try:
        engine.classify(
            position_id="X1",
            instrument_type=InstrumentType.UNCLASSIFIED,
            effective_date="2026-01-15")
        assert False
    except ValueError:
        pass


def _test_override_requires_justification_and_approver():
    engine = build_default_engine()
    # Listed equity → BANKING_BOOK requires override path
    try:
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            override_to=BookClassification.BANKING_BOOK)
        assert False, "should require justification"
    except ValueError:
        pass
    try:
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            override_to=BookClassification.BANKING_BOOK,
            justification="hedging banking book exposure")
        assert False, "should require approver"
    except ValueError:
        pass


def _test_reclassification_request_validates_reason():
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    try:
        engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="",  # empty
            expected_capital_impact_kes=Decimal("0"),
            requested_by="trader1",
            request_date="2026-02-01")
        assert False
    except ValueError:
        pass


def _test_reclassification_no_op_rejected():
    """from_book == to_book is a no-op → reject."""
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    try:
        engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.TRADING_BOOK,  # same
            reason="reason",
            expected_capital_impact_kes=Decimal("0"),
            requested_by="trader1",
            request_date="2026-02-01")
        assert False
    except ValueError:
        pass


def _test_capital_surcharge_only_when_benefits_bank():
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    # Beneficial reclassification (positive impact) — surcharge applies
    req_benefit = engine.request_reclassification(
        request_id="R1", position_id="P1",
        to_book=BookClassification.BANKING_BOOK,
        reason="hedging strategy change",
        expected_capital_impact_kes=Decimal("10000000"),
        requested_by="trader1",
        request_date="2026-02-01")
    surcharge = engine.compute_capital_surcharge(req_benefit)
    assert surcharge == Decimal("10000000")
    # Non-beneficial (negative impact) — no surcharge
    req_no_benefit = engine.request_reclassification(
        request_id="R2", position_id="P1",
        to_book=BookClassification.BANKING_BOOK,
        reason="risk reduction",
        expected_capital_impact_kes=Decimal("-5000000"),
        requested_by="trader1",
        request_date="2026-02-01")
    assert engine.compute_capital_surcharge(req_no_benefit) == Decimal("0")


def _test_approve_reclassification_requires_approver():
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    req = engine.request_reclassification(
        request_id="R1", position_id="P1",
        to_book=BookClassification.BANKING_BOOK,
        reason="reason",
        expected_capital_impact_kes=Decimal("0"),
        requested_by="trader1",
        request_date="2026-02-01")
    try:
        engine.approve_reclassification(
            request=req,
            approver="",  # blank
            decision_date="2026-02-05",
            decision_id="D1")
        assert False
    except ValueError:
        pass


def _test_approve_reclassification_updates_assignment():
    """Per Rule 7: approval is the only path that mutates."""
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    req = engine.request_reclassification(
        request_id="R1", position_id="P1",
        to_book=BookClassification.BANKING_BOOK,
        reason="reason",
        expected_capital_impact_kes=Decimal("0"),
        requested_by="trader1",
        request_date="2026-02-01")
    decision, new_assignment = engine.approve_reclassification(
        request=req,
        approver="senior_mgmt_id",
        decision_date="2026-02-05",
        decision_id="D1")
    assert decision.status == ApprovalStatus.APPROVED
    assert (new_assignment.classification
            == BookClassification.BANKING_BOOK)
    assert not new_assignment.is_presumptive
    assert new_assignment.trading_desk_id is None


def _test_approve_to_trading_book_requires_desk():
    engine = build_default_engine()
    engine.classify(
        position_id="L1",
        instrument_type=InstrumentType.LOAN_RECEIVABLE,
        effective_date="2026-01-15")
    req = engine.request_reclassification(
        request_id="R1", position_id="L1",
        to_book=BookClassification.TRADING_BOOK,
        reason="repurpose for market-making",
        expected_capital_impact_kes=Decimal("0"),
        requested_by="trader1",
        request_date="2026-02-01")
    try:
        engine.approve_reclassification(
            request=req,
            approver="senior_mgmt_id",
            decision_date="2026-02-05",
            decision_id="D1")
        assert False, "should require new_trading_desk_id"
    except ValueError:
        pass


def _test_reject_reclassification_does_not_mutate():
    """Per Rule 7: REJECTED leaves the assignment unchanged."""
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    req = engine.request_reclassification(
        request_id="R1", position_id="P1",
        to_book=BookClassification.BANKING_BOOK,
        reason="reason",
        expected_capital_impact_kes=Decimal("0"),
        requested_by="trader1",
        request_date="2026-02-01")
    decision = engine.reject_reclassification(
        request=req,
        approver="senior_mgmt_id",
        decision_date="2026-02-05",
        decision_id="D1")
    assert decision.status == ApprovalStatus.REJECTED
    # Assignment still TB
    assert (engine.get_assignment("P1").classification
            == BookClassification.TRADING_BOOK)


def _test_summary_counts_correct():
    engine = build_default_engine()
    engine.classify(
        position_id="P1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    engine.classify(
        position_id="P2",
        instrument_type=InstrumentType.FX_TRADING,
        effective_date="2026-01-15",
        trading_desk_id="DESK-FX-NAIROBI")
    engine.classify(
        position_id="L1",
        instrument_type=InstrumentType.LOAN_RECEIVABLE,
        effective_date="2026-01-15")
    s = engine.summary()
    assert s["n_positions"] == 3
    assert s["n_trading_book"] == 2
    assert s["n_banking_book"] == 1
    assert s["n_non_presumptive"] == 0


def _test_default_engine_has_3_desks():
    engine = build_default_engine()
    assert len(engine.all_desks()) == 3
    issues = engine.validate_trading_desk_completeness()
    # All desks complete (only OK issue)
    for desk_id, issue_tuple in issues.items():
        assert issue_tuple == (DeskValidationIssue.OK,), (
            f"desk {desk_id} has issues: {issue_tuple}")


def _test_positions_on_desk_filters_correctly():
    engine = build_default_engine()
    engine.classify(
        position_id="EQ1",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    engine.classify(
        position_id="FX1",
        instrument_type=InstrumentType.FX_TRADING,
        effective_date="2026-01-15",
        trading_desk_id="DESK-FX-NAIROBI")
    eq_positions = engine.positions_on_desk("DESK-EQ-NAIROBI")
    fx_positions = engine.positions_on_desk("DESK-FX-NAIROBI")
    assert eq_positions == ("EQ1",)
    assert fx_positions == ("FX1",)


def self_test() -> None:
    tests = [
        _test_presumptive_classification_basic,
        _test_presumptive_lists_disjoint,
        _test_trading_desk_validation_complete,
        _test_trading_desk_rejects_zero_holding_period,
        _test_trading_desk_requires_risk_classes,
        _test_classify_listed_equity_to_trading_book,
        _test_classify_loan_to_banking_book,
        _test_trading_book_requires_desk,
        _test_banking_book_must_not_have_desk,
        _test_unknown_desk_rejected,
        _test_unclassified_requires_explicit_override,
        _test_override_requires_justification_and_approver,
        _test_reclassification_request_validates_reason,
        _test_reclassification_no_op_rejected,
        _test_capital_surcharge_only_when_benefits_bank,
        _test_approve_reclassification_requires_approver,
        _test_approve_reclassification_updates_assignment,
        _test_approve_to_trading_book_requires_desk,
        _test_reject_reclassification_does_not_mutate,
        _test_summary_counts_correct,
        _test_default_engine_has_3_desks,
        _test_positions_on_desk_filters_correctly,
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
            f"✗ trading_book_boundary self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trading_book_boundary self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

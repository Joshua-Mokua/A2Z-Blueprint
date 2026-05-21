"""utils/group_exposure.py — v10.15 Phase 2 deep impl batch 9 (Credit batch 5 part 2).

╔════════════════════════════════════════════════════════════════════════╗
║  GROUP EXPOSURE — SINGLE OBLIGOR + GROUP + CONNECTED LENDING LIMITS    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (regulatory limit breaches trigger CBK supervisory  ║
║              action and capital impact)                                  ║
║  Implements 1 of 19 Credit standards from registry:                     ║
║    ENH-CRD-R4: Multi-Product Portfolio Underwriting (Group Exposure)    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Kenya Banking Act §10A — Single obligor limit (25% of core capital) ║
║    Kenya Banking Act §11 — Insider lending (20% of core capital aggreg)║
║    Kenya Banking Act §11(1) — Single insider 5% of core capital        ║
║    CBK Prudential Guideline CBK/PG/05 — connected/insider lending      ║
║    CBK Prudential Guideline CBK/PG/06 — large exposures                ║
║    Basel BCBS Large Exposures Framework (2014, BCBS 283) — 25% LE cap  ║
║    EU CRR Art 395 — 25% Tier 1 capital large-exposure limit            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.11-v10.14 — group exposure check at decision time   ║
║  (v10.11 underwriting), at limit assignment (v10.13 pricing), and       ║
║  during portfolio monitoring (v10.14).                                  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

# ════════════════════════════════════════════════════════════════════════
# CBK Banking Act / PG limits (% of core capital)
# ════════════════════════════════════════════════════════════════════════

# Banking Act §10A — Single Obligor Limit
SINGLE_OBLIGOR_LIMIT_PCT = Decimal("25.0")

# Banking Act §11 + CBK PG/05 — Connected lending limits
SINGLE_INSIDER_LIMIT_PCT = Decimal("5.0")          # one insider
AGGREGATE_INSIDER_LIMIT_PCT = Decimal("20.0")      # all insiders combined

# Group/related-party limit (large exposures framework)
SINGLE_GROUP_LIMIT_PCT = Decimal("25.0")           # same as single obligor
LARGE_EXPOSURE_REPORTING_THRESHOLD_PCT = Decimal("10.0")   # report to CBK

# Headroom warning thresholds (% of limit at which to flag)
HEADROOM_WARNING_PCT = Decimal("80.0")     # 80% of limit → AMBER
HEADROOM_CRITICAL_PCT = Decimal("95.0")    # 95% of limit → RED


# ════════════════════════════════════════════════════════════════════════
# Exposure types
# ════════════════════════════════════════════════════════════════════════

class ExposureType(Enum):
    """Types of credit exposure that aggregate to total."""
    LOAN_TERM = "LOAN_TERM"
    LOAN_OVERDRAFT = "LOAN_OVERDRAFT"
    LOAN_REVOLVING = "LOAN_REVOLVING"
    CARD = "CARD"
    LETTER_OF_CREDIT = "LETTER_OF_CREDIT"
    GUARANTEE = "GUARANTEE"
    DERIVATIVE_PFE = "DERIVATIVE_PFE"          # potential future exposure
    UNDRAWN_COMMITMENT = "UNDRAWN_COMMITMENT"


# Credit Conversion Factors (CCF) per Basel — convert off-BS to on-BS equivalent
EXPOSURE_CCF: Mapping[ExposureType, Decimal] = {
    ExposureType.LOAN_TERM: Decimal("1.0"),
    ExposureType.LOAN_OVERDRAFT: Decimal("1.0"),
    ExposureType.LOAN_REVOLVING: Decimal("1.0"),
    ExposureType.CARD: Decimal("1.0"),
    ExposureType.LETTER_OF_CREDIT: Decimal("0.5"),     # 50% — short-term LC
    ExposureType.GUARANTEE: Decimal("1.0"),             # 100% — substitution
    ExposureType.DERIVATIVE_PFE: Decimal("0.4"),
    ExposureType.UNDRAWN_COMMITMENT: Decimal("0.4"),    # original maturity ≤1y
}


class RelationshipType(Enum):
    """How an obligor relates to others."""
    NONE = "NONE"
    GROUP_PARENT = "GROUP_PARENT"
    GROUP_SUBSIDIARY = "GROUP_SUBSIDIARY"
    GROUP_AFFILIATE = "GROUP_AFFILIATE"
    INSIDER_DIRECTOR = "INSIDER_DIRECTOR"
    INSIDER_OFFICER = "INSIDER_OFFICER"
    INSIDER_SHAREHOLDER = "INSIDER_SHAREHOLDER"          # ≥10% shareholding
    INSIDER_RELATED_TO_INSIDER = "INSIDER_RELATED_TO_INSIDER"


# ════════════════════════════════════════════════════════════════════════
# Limit verdicts
# ════════════════════════════════════════════════════════════════════════

class LimitVerdict(Enum):
    """Outcome of a limit check."""
    WITHIN_LIMIT = "WITHIN_LIMIT"
    APPROACHING = "APPROACHING"            # 80-95% of limit
    NEAR_BREACH = "NEAR_BREACH"            # 95-100% of limit
    BREACHED = "BREACHED"                   # > 100% of limit


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Exposure:
    """A single exposure to one obligor."""
    exposure_id: str
    obligor_id: str
    exposure_type: ExposureType
    outstanding_kes: Decimal             # currently drawn / utilized
    limit_kes: Decimal                    # facility limit (incl undrawn)
    ccf_override: Optional[Decimal] = None
    notes: str = ""

    def credit_equivalent_kes(self) -> Decimal:
        """Compute Basel credit-equivalent exposure for limit aggregation.

        For drawn amounts: outstanding × 1.0
        For undrawn portion: undrawn × CCF
        """
        ccf = (
            self.ccf_override if self.ccf_override is not None
            else EXPOSURE_CCF.get(self.exposure_type, Decimal("1.0")))
        drawn = self.outstanding_kes
        undrawn = max(Decimal("0"), self.limit_kes - self.outstanding_kes)
        return drawn + undrawn * ccf


@dataclass(frozen=True)
class Obligor:
    """A borrowing entity (individual or corporate)."""
    obligor_id: str
    name: str
    is_individual: bool
    group_id: Optional[str] = None
    relationship_to_bank: RelationshipType = RelationshipType.NONE
    notes: str = ""

    def is_insider(self) -> bool:
        return self.relationship_to_bank in (
            RelationshipType.INSIDER_DIRECTOR,
            RelationshipType.INSIDER_OFFICER,
            RelationshipType.INSIDER_SHAREHOLDER,
            RelationshipType.INSIDER_RELATED_TO_INSIDER)

    def is_in_group(self) -> bool:
        return self.relationship_to_bank in (
            RelationshipType.GROUP_PARENT,
            RelationshipType.GROUP_SUBSIDIARY,
            RelationshipType.GROUP_AFFILIATE)


@dataclass(frozen=True)
class LimitCheckResult:
    """Result of one limit check."""
    limit_name: str
    limit_pct_of_capital: Decimal
    limit_amount_kes: Decimal
    current_exposure_kes: Decimal
    headroom_kes: Decimal
    utilization_pct: Decimal           # current / limit × 100
    verdict: LimitVerdict
    notes: str = ""


@dataclass(frozen=True)
class GroupExposureReport:
    """Comprehensive exposure assessment for a group / obligor."""
    obligor_id: str
    group_id: Optional[str]
    core_capital_kes: Decimal
    single_obligor_check: LimitCheckResult
    group_check: Optional[LimitCheckResult]
    insider_check: Optional[LimitCheckResult]
    aggregate_insider_check: Optional[LimitCheckResult]
    total_credit_equivalent_kes: Decimal
    is_large_exposure: bool             # ≥ 10% of core capital → CBK report
    breaches: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Functions
# ════════════════════════════════════════════════════════════════════════

def aggregate_obligor_exposure(
    obligor_id: str,
    exposures: Sequence[Exposure],
) -> Decimal:
    """Sum credit-equivalent exposure for one obligor."""
    return sum(
        (e.credit_equivalent_kes() for e in exposures
          if e.obligor_id == obligor_id),
        Decimal("0"))


def aggregate_group_exposure(
    group_id: str,
    obligors: Sequence[Obligor],
    exposures: Sequence[Exposure],
) -> Decimal:
    """Sum credit-equivalent exposure across all obligors in a group."""
    group_obligor_ids = {
        o.obligor_id for o in obligors if o.group_id == group_id}
    return sum(
        (e.credit_equivalent_kes() for e in exposures
          if e.obligor_id in group_obligor_ids),
        Decimal("0"))


def aggregate_insider_exposure(
    obligors: Sequence[Obligor],
    exposures: Sequence[Exposure],
) -> Decimal:
    """Sum credit-equivalent exposure across all insiders combined."""
    insider_ids = {o.obligor_id for o in obligors if o.is_insider()}
    return sum(
        (e.credit_equivalent_kes() for e in exposures
          if e.obligor_id in insider_ids),
        Decimal("0"))


def determine_verdict(
    *,
    utilization_pct: Decimal,
) -> LimitVerdict:
    """Map utilization % to verdict."""
    if utilization_pct > Decimal("100"):
        return LimitVerdict.BREACHED
    if utilization_pct >= HEADROOM_CRITICAL_PCT:
        return LimitVerdict.NEAR_BREACH
    if utilization_pct >= HEADROOM_WARNING_PCT:
        return LimitVerdict.APPROACHING
    return LimitVerdict.WITHIN_LIMIT


def check_single_obligor_limit(
    *,
    current_exposure_kes: Decimal,
    core_capital_kes: Decimal,
    limit_pct: Decimal = SINGLE_OBLIGOR_LIMIT_PCT,
) -> LimitCheckResult:
    """Banking Act §10A — single obligor must not exceed 25% of core capital."""
    if core_capital_kes <= Decimal("0"):
        raise ValueError("core_capital_kes must be positive")

    limit_amount = core_capital_kes * limit_pct / Decimal("100")
    headroom = limit_amount - current_exposure_kes
    util_pct = (
        current_exposure_kes / limit_amount * Decimal("100")
        if limit_amount > Decimal("0") else Decimal("0"))

    return LimitCheckResult(
        limit_name="SINGLE_OBLIGOR (Banking Act §10A)",
        limit_pct_of_capital=limit_pct,
        limit_amount_kes=limit_amount,
        current_exposure_kes=current_exposure_kes,
        headroom_kes=headroom,
        utilization_pct=util_pct,
        verdict=determine_verdict(utilization_pct=util_pct),
        notes=f"limit = {limit_pct}% of core capital")


def check_group_limit(
    *,
    current_exposure_kes: Decimal,
    core_capital_kes: Decimal,
    limit_pct: Decimal = SINGLE_GROUP_LIMIT_PCT,
) -> LimitCheckResult:
    """Group/related-party aggregate must not exceed limit (default 25%)."""
    if core_capital_kes <= Decimal("0"):
        raise ValueError("core_capital_kes must be positive")

    limit_amount = core_capital_kes * limit_pct / Decimal("100")
    headroom = limit_amount - current_exposure_kes
    util_pct = (
        current_exposure_kes / limit_amount * Decimal("100")
        if limit_amount > Decimal("0") else Decimal("0"))

    return LimitCheckResult(
        limit_name="GROUP / LARGE EXPOSURE (Banking Act + Basel LE)",
        limit_pct_of_capital=limit_pct,
        limit_amount_kes=limit_amount,
        current_exposure_kes=current_exposure_kes,
        headroom_kes=headroom,
        utilization_pct=util_pct,
        verdict=determine_verdict(utilization_pct=util_pct),
        notes=f"limit = {limit_pct}% of core capital")


def check_insider_limit(
    *,
    insider_exposure_kes: Decimal,
    core_capital_kes: Decimal,
    is_aggregate: bool = False,
) -> LimitCheckResult:
    """Banking Act §11 — single insider 5% / aggregate 20% of core capital."""
    if core_capital_kes <= Decimal("0"):
        raise ValueError("core_capital_kes must be positive")

    limit_pct = (
        AGGREGATE_INSIDER_LIMIT_PCT if is_aggregate
        else SINGLE_INSIDER_LIMIT_PCT)
    limit_amount = core_capital_kes * limit_pct / Decimal("100")
    headroom = limit_amount - insider_exposure_kes
    util_pct = (
        insider_exposure_kes / limit_amount * Decimal("100")
        if limit_amount > Decimal("0") else Decimal("0"))

    label = (
        "AGGREGATE_INSIDER (Banking Act §11 — 20%)"
        if is_aggregate
        else "SINGLE_INSIDER (Banking Act §11(1) — 5%)")

    return LimitCheckResult(
        limit_name=label,
        limit_pct_of_capital=limit_pct,
        limit_amount_kes=limit_amount,
        current_exposure_kes=insider_exposure_kes,
        headroom_kes=headroom,
        utilization_pct=util_pct,
        verdict=determine_verdict(utilization_pct=util_pct),
        notes=f"limit = {limit_pct}% of core capital")


def assess_group_exposure(
    *,
    obligor_id: str,
    obligors: Sequence[Obligor],
    exposures: Sequence[Exposure],
    core_capital_kes: Decimal,
) -> GroupExposureReport:
    """End-to-end exposure assessment for an obligor + their group + insiders.

    Returns a unified report with all relevant limit checks.
    """
    # Find the obligor record
    obligor = next(
        (o for o in obligors if o.obligor_id == obligor_id), None)
    if obligor is None:
        raise ValueError(f"obligor {obligor_id} not found")

    # Single obligor exposure
    single_exposure = aggregate_obligor_exposure(obligor_id, exposures)
    single_check = check_single_obligor_limit(
        current_exposure_kes=single_exposure,
        core_capital_kes=core_capital_kes)

    # Group exposure (if applicable)
    group_check: Optional[LimitCheckResult] = None
    if obligor.group_id:
        group_exp = aggregate_group_exposure(
            obligor.group_id, obligors, exposures)
        group_check = check_group_limit(
            current_exposure_kes=group_exp,
            core_capital_kes=core_capital_kes)

    # Insider checks (if applicable)
    insider_check: Optional[LimitCheckResult] = None
    aggregate_insider_check: Optional[LimitCheckResult] = None
    if obligor.is_insider():
        insider_check = check_insider_limit(
            insider_exposure_kes=single_exposure,
            core_capital_kes=core_capital_kes,
            is_aggregate=False)
        agg_exp = aggregate_insider_exposure(obligors, exposures)
        aggregate_insider_check = check_insider_limit(
            insider_exposure_kes=agg_exp,
            core_capital_kes=core_capital_kes,
            is_aggregate=True)

    # Large exposure flag (≥10% of core capital is reportable)
    largest_exposure = single_exposure
    if group_check is not None:
        largest_exposure = max(
            largest_exposure, group_check.current_exposure_kes)
    is_large = (
        largest_exposure >= core_capital_kes
        * LARGE_EXPOSURE_REPORTING_THRESHOLD_PCT / Decimal("100"))

    # Compile breaches list
    breaches: List[str] = []
    for chk in (single_check, group_check, insider_check,
                  aggregate_insider_check):
        if chk is not None and chk.verdict in (
                LimitVerdict.BREACHED, LimitVerdict.NEAR_BREACH):
            breaches.append(
                f"{chk.limit_name}: {chk.verdict.value} "
                f"({chk.utilization_pct:.1f}%)")

    return GroupExposureReport(
        obligor_id=obligor_id,
        group_id=obligor.group_id,
        core_capital_kes=core_capital_kes,
        single_obligor_check=single_check,
        group_check=group_check,
        insider_check=insider_check,
        aggregate_insider_check=aggregate_insider_check,
        total_credit_equivalent_kes=single_exposure,
        is_large_exposure=is_large,
        breaches=tuple(breaches))


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class GroupExposureEngine:
    """Tracks obligors + exposures + runs limit checks portfolio-wide."""

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya",
        core_capital_kes: Optional[Decimal] = None,
    ):
        self.entity_name = entity_name
        self._core_capital_kes = core_capital_kes
        self._obligors: Dict[str, Obligor] = {}
        self._exposures: List[Exposure] = []

    def set_core_capital(self, amount_kes: Decimal) -> None:
        if amount_kes <= Decimal("0"):
            raise ValueError("core_capital must be positive")
        self._core_capital_kes = amount_kes

    def add_obligor(self, o: Obligor) -> None:
        if o.obligor_id in self._obligors:
            raise ValueError(f"obligor {o.obligor_id} already added")
        self._obligors[o.obligor_id] = o

    def add_exposure(self, e: Exposure) -> None:
        if e.obligor_id not in self._obligors:
            raise ValueError(
                f"obligor {e.obligor_id} must be added before exposures")
        self._exposures.append(e)

    def assess(self, obligor_id: str) -> GroupExposureReport:
        if self._core_capital_kes is None:
            raise ValueError("core_capital not set")
        return assess_group_exposure(
            obligor_id=obligor_id,
            obligors=list(self._obligors.values()),
            exposures=self._exposures,
            core_capital_kes=self._core_capital_kes)

    def board_summary(self) -> Dict[str, object]:
        if not self._obligors or self._core_capital_kes is None:
            return {
                "entity": self.entity_name,
                "n_obligors": 0,
                "n_exposures": 0,
                "n_breaches": 0,
                "n_large_exposures": 0,
                "core_capital_kes": Decimal("0"),
                "total_book_kes": Decimal("0"),
            }

        breaches = 0
        large = 0
        for oid in self._obligors:
            r = self.assess(oid)
            if r.breaches:
                breaches += 1
            if r.is_large_exposure:
                large += 1

        total_book = sum(
            (e.credit_equivalent_kes() for e in self._exposures),
            Decimal("0"))

        return {
            "entity": self.entity_name,
            "n_obligors": len(self._obligors),
            "n_exposures": len(self._exposures),
            "n_breaches": breaches,
            "n_large_exposures": large,
            "core_capital_kes": self._core_capital_kes,
            "total_book_kes": total_book,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_constants_per_banking_act():
    """Limits match Kenya Banking Act values."""
    assert SINGLE_OBLIGOR_LIMIT_PCT == Decimal("25.0")
    assert SINGLE_INSIDER_LIMIT_PCT == Decimal("5.0")
    assert AGGREGATE_INSIDER_LIMIT_PCT == Decimal("20.0")


def _test_credit_equivalent_loan_full():
    """Term loan: drawn = outstanding × 1.0; undrawn × CCF."""
    e = Exposure(
        exposure_id="E1", obligor_id="O1",
        exposure_type=ExposureType.LOAN_TERM,
        outstanding_kes=Decimal("1000000"),
        limit_kes=Decimal("1000000"))
    assert e.credit_equivalent_kes() == Decimal("1000000")


def _test_credit_equivalent_undrawn_ccf():
    """Undrawn portion gets CCF applied."""
    e = Exposure(
        exposure_id="E1", obligor_id="O1",
        exposure_type=ExposureType.LOAN_REVOLVING,
        outstanding_kes=Decimal("400000"),
        limit_kes=Decimal("1000000"))    # 600K undrawn
    # CCF for revolving = 1.0 → 400K + 600K × 1.0 = 1M
    assert e.credit_equivalent_kes() == Decimal("1000000")


def _test_credit_equivalent_lc_half_ccf():
    """LC: outstanding × 1 + undrawn × 0.5."""
    e = Exposure(
        exposure_id="E1", obligor_id="O1",
        exposure_type=ExposureType.LETTER_OF_CREDIT,
        outstanding_kes=Decimal("500000"),
        limit_kes=Decimal("1000000"))    # 500K undrawn
    # 500K + 500K × 0.5 = 750K
    assert e.credit_equivalent_kes() == Decimal("750000")


def _test_aggregate_obligor_exposure_multi_facility():
    """Multiple facilities to one obligor sum together."""
    es = [
        Exposure(
            exposure_id=f"E{i}", obligor_id="O1",
            exposure_type=ExposureType.LOAN_TERM,
            outstanding_kes=Decimal("1000000"),
            limit_kes=Decimal("1000000"))
        for i in range(3)]
    total = aggregate_obligor_exposure("O1", es)
    assert total == Decimal("3000000")


def _test_aggregate_group_exposure():
    """Group aggregation includes all members."""
    obligors = [
        Obligor(obligor_id="A", name="Parent Co", is_individual=False,
                  group_id="GRP1",
                  relationship_to_bank=RelationshipType.GROUP_PARENT),
        Obligor(obligor_id="B", name="Sub Co", is_individual=False,
                  group_id="GRP1",
                  relationship_to_bank=RelationshipType.GROUP_SUBSIDIARY),
        Obligor(obligor_id="C", name="Outsider", is_individual=False),
    ]
    exposures = [
        Exposure(exposure_id="E1", obligor_id="A",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("1000000"),
                  limit_kes=Decimal("1000000")),
        Exposure(exposure_id="E2", obligor_id="B",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("500000"),
                  limit_kes=Decimal("500000")),
        Exposure(exposure_id="E3", obligor_id="C",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("9999999"),
                  limit_kes=Decimal("9999999")),
    ]
    grp = aggregate_group_exposure("GRP1", obligors, exposures)
    assert grp == Decimal("1500000")    # only A + B, not C


def _test_single_obligor_limit_within():
    """Exposure 10% of capital with 25% limit → WITHIN."""
    r = check_single_obligor_limit(
        current_exposure_kes=Decimal("100000000"),
        core_capital_kes=Decimal("1000000000"))
    assert r.verdict == LimitVerdict.WITHIN_LIMIT


def _test_single_obligor_limit_breached():
    """Exposure exceeds 25% → BREACHED."""
    r = check_single_obligor_limit(
        current_exposure_kes=Decimal("300000000"),
        core_capital_kes=Decimal("1000000000"))
    assert r.verdict == LimitVerdict.BREACHED
    assert r.headroom_kes < Decimal("0")


def _test_single_obligor_limit_approaching():
    """20% of capital = 80% of 25% limit → APPROACHING."""
    r = check_single_obligor_limit(
        current_exposure_kes=Decimal("200000000"),
        core_capital_kes=Decimal("1000000000"))
    # 200M / 250M = 80% utilization
    assert r.verdict == LimitVerdict.APPROACHING


def _test_insider_limit_single():
    """Single insider limit = 5% of core capital."""
    r = check_insider_limit(
        insider_exposure_kes=Decimal("60000000"),
        core_capital_kes=Decimal("1000000000"),
        is_aggregate=False)
    # 60M / 50M (5% of 1B) = 120% → BREACHED
    assert r.verdict == LimitVerdict.BREACHED


def _test_insider_limit_aggregate():
    """Aggregate insider limit = 20% of core capital."""
    r = check_insider_limit(
        insider_exposure_kes=Decimal("100000000"),
        core_capital_kes=Decimal("1000000000"),
        is_aggregate=True)
    # 100M / 200M (20% of 1B) = 50% → WITHIN
    assert r.verdict == LimitVerdict.WITHIN_LIMIT


def _test_zero_capital_raises():
    try:
        check_single_obligor_limit(
            current_exposure_kes=Decimal("100"),
            core_capital_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_assess_group_full_report():
    """End-to-end group assessment includes all relevant checks."""
    obligors = [
        Obligor(obligor_id="A", name="Parent", is_individual=False,
                  group_id="G1",
                  relationship_to_bank=RelationshipType.GROUP_PARENT),
        Obligor(obligor_id="B", name="Sub", is_individual=False,
                  group_id="G1",
                  relationship_to_bank=RelationshipType.GROUP_SUBSIDIARY),
    ]
    exposures = [
        Exposure(exposure_id="E1", obligor_id="A",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("100000000"),
                  limit_kes=Decimal("100000000")),
        Exposure(exposure_id="E2", obligor_id="B",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("50000000"),
                  limit_kes=Decimal("50000000")),
    ]
    r = assess_group_exposure(
        obligor_id="A",
        obligors=obligors, exposures=exposures,
        core_capital_kes=Decimal("1000000000"))
    assert r.single_obligor_check is not None
    assert r.group_check is not None
    assert r.group_check.current_exposure_kes == Decimal("150000000")


def _test_assess_group_insider_includes_insider_checks():
    obligors = [
        Obligor(obligor_id="DIR1", name="Director X", is_individual=True,
                  relationship_to_bank=RelationshipType.INSIDER_DIRECTOR),
    ]
    exposures = [
        Exposure(exposure_id="E1", obligor_id="DIR1",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("10000000"),
                  limit_kes=Decimal("10000000")),
    ]
    r = assess_group_exposure(
        obligor_id="DIR1",
        obligors=obligors, exposures=exposures,
        core_capital_kes=Decimal("1000000000"))
    assert r.insider_check is not None
    assert r.aggregate_insider_check is not None


def _test_large_exposure_flag():
    """Exposure ≥ 10% of core capital → is_large_exposure=True."""
    obligors = [Obligor(obligor_id="A", name="X", is_individual=False)]
    exposures = [
        Exposure(exposure_id="E1", obligor_id="A",
                  exposure_type=ExposureType.LOAN_TERM,
                  outstanding_kes=Decimal("150000000"),
                  limit_kes=Decimal("150000000")),
    ]
    r = assess_group_exposure(
        obligor_id="A", obligors=obligors, exposures=exposures,
        core_capital_kes=Decimal("1000000000"))    # 1B → 10% = 100M
    assert r.is_large_exposure


def _test_engine_basic_flow():
    eng = GroupExposureEngine(core_capital_kes=Decimal("1000000000"))
    eng.add_obligor(Obligor(
        obligor_id="X", name="Test", is_individual=False))
    eng.add_exposure(Exposure(
        exposure_id="E1", obligor_id="X",
        exposure_type=ExposureType.LOAN_TERM,
        outstanding_kes=Decimal("50000000"),
        limit_kes=Decimal("50000000")))
    r = eng.assess("X")
    assert r.single_obligor_check.verdict == LimitVerdict.WITHIN_LIMIT


def _test_engine_exposure_without_obligor_raises():
    eng = GroupExposureEngine(core_capital_kes=Decimal("1000000000"))
    try:
        eng.add_exposure(Exposure(
            exposure_id="E1", obligor_id="NONEXISTENT",
            exposure_type=ExposureType.LOAN_TERM,
            outstanding_kes=Decimal("100"),
            limit_kes=Decimal("100")))
        assert False
    except ValueError as e:
        assert "must be added before" in str(e)


def _test_engine_board_summary_empty():
    eng = GroupExposureEngine()
    s = eng.board_summary()
    assert s["n_obligors"] == 0


def _test_engine_board_summary_with_breach():
    eng = GroupExposureEngine(core_capital_kes=Decimal("1000000000"))
    eng.add_obligor(Obligor(obligor_id="X", name="X", is_individual=False))
    eng.add_exposure(Exposure(
        exposure_id="E1", obligor_id="X",
        exposure_type=ExposureType.LOAN_TERM,
        outstanding_kes=Decimal("300000000"),    # > 25%
        limit_kes=Decimal("300000000")))
    s = eng.board_summary()
    assert s["n_breaches"] == 1
    assert s["n_large_exposures"] == 1


def _test_decimal_purity():
    r = check_single_obligor_limit(
        current_exposure_kes=Decimal("100"),
        core_capital_kes=Decimal("1000"))
    assert isinstance(r.utilization_pct, Decimal)
    assert isinstance(r.headroom_kes, Decimal)


def self_test() -> None:
    tests = [
        _test_constants_per_banking_act,
        _test_credit_equivalent_loan_full,
        _test_credit_equivalent_undrawn_ccf,
        _test_credit_equivalent_lc_half_ccf,
        _test_aggregate_obligor_exposure_multi_facility,
        _test_aggregate_group_exposure,
        _test_single_obligor_limit_within,
        _test_single_obligor_limit_breached,
        _test_single_obligor_limit_approaching,
        _test_insider_limit_single,
        _test_insider_limit_aggregate,
        _test_zero_capital_raises,
        _test_assess_group_full_report,
        _test_assess_group_insider_includes_insider_checks,
        _test_large_exposure_flag,
        _test_engine_basic_flow,
        _test_engine_exposure_without_obligor_raises,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_with_breach,
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
        print(f"✗ group_exposure self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ group_exposure self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

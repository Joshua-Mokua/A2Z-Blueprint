"""utils/commission_assurance.py — v10.56: Commission & Incentive Assurance.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-247 — Commission & Incentive Assurance                             ║
║  Cat B — revenue_assurance arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Plan-based commission recomputation engine. Where ENH-242's            ║
║  detect_commission_anomalies takes (paid, expected) as inputs and       ║
║  flags mismatches, ENH-247 computes the EXPECTED itself from a          ║
║  tiered IncentivePlan + actual revenue. Closes the loop:                ║
║                                                                          ║
║    revenue → IncentivePlan → expected_commission → ENH-242 anomaly      ║
║              ↑ ENH-247 ↑                            screen              ║
║                                                                          ║
║  Capabilities:                                                          ║
║    1. compute_expected_commission(plan, revenue) → CommissionCalc       ║
║    2. validate_paid_vs_computed(calc, paid_records) → flag mismatches   ║
║    3. validate_overrides(overrides) → ensure approval_id present        ║
║    4. summarize_disputes(disputes) → counts by status (engine never     ║
║       resolves disputes; tracks them for transparency)                  ║
║                                                                          ║
║  Per Rule 7, engine is computational — never pays out commissions,      ║
║  never auto-approves overrides, never closes disputes. The output       ║
║  feeds payroll workflow (which pays) and ENH-243 orchestrator (which    ║
║  routes findings to HR_PAYROLL team).                                   ║
║                                                                          ║
║  Per Rule 1, every CommissionCalculation surfaces the tier breakdown    ║
║  (which tiers fired, how much each contributed) so RMs disputing        ║
║  their commission can see exactly how it was computed.                  ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_anomaly_patterns (ENH-242 — produces CommissionRecord     ║
║      from this engine's expected_commission output)                    ║
║    - rm_profitability (existing — which RM earned which revenue)       ║
║    - revenue_orchestrator (ENH-243 — routes commission findings to     ║
║      HR_PAYROLL team)                                                  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.revenue_validation import ValidationSeverity

SPEC_DEVIATION_NOTE = (
    "CommissionAssuranceEngine implements ENH-247 plan-based "
    "commission recomputation. Pure stdlib (Decimal + "
    "dataclasses). Per Rule 1, every CommissionCalculation "
    "surfaces tier-by-tier breakdown so disputing RMs can see "
    "exactly how the figure was computed. Per Rule 7, engine is "
    "computational — never pays out commissions, never auto-"
    "approves overrides, never closes disputes. Composes with "
    "ENH-242 by producing the expected_commission field that "
    "ENH-242's detect_commission_anomalies consumes."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class TierBasis(Enum):
    """How the tier rate is applied."""
    MARGINAL = "MARGINAL"      # rate applies only to amount above tier_min
    CUMULATIVE = "CUMULATIVE"  # whole amount uses the tier matching total


class OverrideStatus(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DisputeStatus(Enum):
    OPEN = "OPEN"
    UPHELD = "UPHELD"        # RM was right
    REJECTED = "REJECTED"    # original calc stands
    WITHDRAWN = "WITHDRAWN"


class CommissionFinding(Enum):
    """Issue surfaced by validate_paid_vs_computed."""
    OVERPAID = "OVERPAID"
    UNDERPAID = "UNDERPAID"
    MISSING_PAYMENT = "MISSING_PAYMENT"
    MULTIPLE_PAYMENTS = "MULTIPLE_PAYMENTS"


# ════════════════════════════════════════════════════════════════════════
# Plan dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CommissionTier:
    """One tier of an incentive plan."""
    tier_min_kes: Decimal
    tier_max_kes: Optional[Decimal]   # None = no upper limit
    rate_pct: Decimal                 # 0..1

    def __post_init__(self) -> None:
        if self.tier_min_kes < 0:
            raise ValueError("tier_min_kes must be ≥ 0")
        if (self.tier_max_kes is not None
                and self.tier_max_kes <= self.tier_min_kes):
            raise ValueError(
                "tier_max_kes must be > tier_min_kes")
        if not (Decimal("0") <= self.rate_pct <= Decimal("1")):
            raise ValueError("rate_pct must be in [0, 1]")


@dataclass(frozen=True)
class IncentivePlan:
    """One incentive plan with tiered commission structure."""
    plan_id: str
    rm_role: str
    tiers: Tuple[CommissionTier, ...]
    basis: TierBasis = TierBasis.MARGINAL
    effective_from: date = date(2026, 1, 1)
    effective_to: date = date(2026, 12, 31)

    def __post_init__(self) -> None:
        if not self.plan_id:
            raise ValueError("plan_id must be non-empty")
        if not self.tiers:
            raise ValueError("at least one tier required")
        # Tiers must be sorted ascending by tier_min_kes and not
        # overlap.
        prev_max: Optional[Decimal] = None
        for t in self.tiers:
            if prev_max is not None and t.tier_min_kes < prev_max:
                raise ValueError(
                    f"tier ordering broken at "
                    f"tier_min={t.tier_min_kes}; previous "
                    f"tier ended at {prev_max}")
            prev_max = (
                t.tier_max_kes if t.tier_max_kes is not None
                else Decimal("Infinity"))
        if self.effective_to < self.effective_from:
            raise ValueError(
                "effective_to must be ≥ effective_from")


@dataclass(frozen=True)
class CommissionContribution:
    """One tier's contribution to the total expected commission."""
    tier_min_kes: Decimal
    tier_max_kes: Optional[Decimal]
    rate_pct: Decimal
    amount_in_tier_kes: Decimal
    contribution_kes: Decimal


@dataclass(frozen=True)
class CommissionCalculation:
    """Output of plan-based recomputation. Per Rule 1, full
    breakdown."""
    rm_code: str
    plan_id: str
    period: str
    underlying_revenue_kes: Decimal
    expected_commission_kes: Decimal
    contributions: Tuple[CommissionContribution, ...]
    basis: TierBasis
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class PaidCommissionRecord:
    """An actually-paid commission entry against an RM/period."""
    payment_id: str
    rm_code: str
    period: str
    paid_kes: Decimal
    payment_date: date

    def __post_init__(self) -> None:
        if not self.payment_id:
            raise ValueError("payment_id must be non-empty")
        if self.paid_kes < 0:
            raise ValueError("paid_kes must be ≥ 0")


@dataclass(frozen=True)
class CommissionOverride:
    override_id: str
    rm_code: str
    period: str
    delta_kes: Decimal           # positive = bonus, negative = clawback
    reason: str
    status: OverrideStatus
    approval_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.override_id:
            raise ValueError("override_id must be non-empty")
        if not self.reason:
            raise ValueError("reason must be non-empty")


@dataclass(frozen=True)
class CommissionDispute:
    dispute_id: str
    rm_code: str
    period: str
    status: DisputeStatus
    raised_date: date
    resolved_date: Optional[date] = None

    def __post_init__(self) -> None:
        if not self.dispute_id:
            raise ValueError("dispute_id must be non-empty")
        if (self.status != DisputeStatus.OPEN
                and self.resolved_date is None):
            raise ValueError(
                "non-OPEN disputes require resolved_date")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CommissionAssuranceFinding:
    finding_id: str
    finding_type: CommissionFinding
    severity: ValidationSeverity
    rm_code: str
    period: str
    expected_kes: Decimal
    paid_kes: Decimal
    variance_kes: Decimal
    related_payment_ids: Tuple[str, ...]
    description: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class OverrideValidationResult:
    override_id: str
    valid: bool
    issue: str   # "" if valid


@dataclass(frozen=True)
class DisputeSummary:
    open_count: int
    upheld_count: int
    rejected_count: int
    withdrawn_count: int
    avg_resolution_days: Optional[Decimal]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class CommissionAssuranceEngine:
    """Plan-based commission recomputation + assurance.

    Per Rule 7, engine never:
      - pays out a commission
      - auto-approves an override
      - closes a dispute
      - mutates inputs (frozen contract)
    """

    PAYMENT_TOLERANCE_KES: Decimal = Decimal("1.00")

    # ── Compute expected commission from plan + revenue ─────────────
    def compute_expected_commission(
        self,
        plan: IncentivePlan,
        rm_code: str,
        period: str,
        revenue_kes: Decimal,
    ) -> CommissionCalculation:
        """Walk the plan's tiers given revenue. Returns a
        CommissionCalculation with per-tier contribution detail."""
        if revenue_kes < 0:
            raise ValueError("revenue_kes must be ≥ 0")

        contributions: List[CommissionContribution] = []
        total = Decimal("0")

        if plan.basis == TierBasis.CUMULATIVE:
            # Find the single tier the total revenue falls into;
            # that tier's rate applies to the WHOLE revenue.
            applicable: Optional[CommissionTier] = None
            for t in plan.tiers:
                top = (
                    t.tier_max_kes if t.tier_max_kes is not None
                    else Decimal("Infinity"))
                if t.tier_min_kes <= revenue_kes <= top:
                    applicable = t
                    break
            if applicable is None:
                # Revenue is below the lowest tier_min — no
                # commission. Surface that as a single zero
                # contribution for transparency.
                applicable = plan.tiers[0]
                contrib = Decimal("0")
                contributions.append(CommissionContribution(
                    tier_min_kes=applicable.tier_min_kes,
                    tier_max_kes=applicable.tier_max_kes,
                    rate_pct=applicable.rate_pct,
                    amount_in_tier_kes=Decimal("0"),
                    contribution_kes=Decimal("0")))
            else:
                contrib = revenue_kes * applicable.rate_pct
                contributions.append(CommissionContribution(
                    tier_min_kes=applicable.tier_min_kes,
                    tier_max_kes=applicable.tier_max_kes,
                    rate_pct=applicable.rate_pct,
                    amount_in_tier_kes=revenue_kes,
                    contribution_kes=contrib))
                total += contrib
        else:
            # MARGINAL: each tier earns its rate on the slice of
            # revenue that falls within the tier's bounds. Per
            # Rule 1, surface ALL tiers even if zero contribution —
            # an RM disputing should see the full plan structure.
            for t in plan.tiers:
                top = (
                    t.tier_max_kes if t.tier_max_kes is not None
                    else Decimal("Infinity"))
                if revenue_kes <= t.tier_min_kes:
                    contributions.append(CommissionContribution(
                        tier_min_kes=t.tier_min_kes,
                        tier_max_kes=t.tier_max_kes,
                        rate_pct=t.rate_pct,
                        amount_in_tier_kes=Decimal("0"),
                        contribution_kes=Decimal("0")))
                    continue
                amt_in = min(revenue_kes, top) - t.tier_min_kes
                contrib = amt_in * t.rate_pct
                contributions.append(CommissionContribution(
                    tier_min_kes=t.tier_min_kes,
                    tier_max_kes=t.tier_max_kes,
                    rate_pct=t.rate_pct,
                    amount_in_tier_kes=amt_in,
                    contribution_kes=contrib))
                total += contrib
                # Don't break — continue iterating so the higher
                # tiers surface as zero-contribution entries for
                # transparency.

        return CommissionCalculation(
            rm_code=rm_code, plan_id=plan.plan_id,
            period=period, underlying_revenue_kes=revenue_kes,
            expected_commission_kes=total.quantize(Decimal("0.01")),
            contributions=tuple(contributions),
            basis=plan.basis,
            framework_refs=(
                "ENH-247 §plan_recompute",
                f"Plan basis: {plan.basis.value}",
            ))

    # ── Validate paid vs computed ───────────────────────────────────
    def validate_paid_vs_computed(
        self,
        calculation: CommissionCalculation,
        payments: Sequence[PaidCommissionRecord],
    ) -> Tuple[CommissionAssuranceFinding, ...]:
        """Match payments to a single calculation by (rm_code,
        period)."""
        relevant = [
            p for p in payments
            if p.rm_code == calculation.rm_code
            and p.period == calculation.period]
        findings: List[CommissionAssuranceFinding] = []

        if not relevant:
            findings.append(CommissionAssuranceFinding(
                finding_id=(
                    f"COMM-MISSING-{calculation.rm_code}-"
                    f"{calculation.period}"),
                finding_type=CommissionFinding.MISSING_PAYMENT,
                severity=ValidationSeverity.HIGH,
                rm_code=calculation.rm_code,
                period=calculation.period,
                expected_kes=(
                    calculation.expected_commission_kes),
                paid_kes=Decimal("0"),
                variance_kes=(
                    -calculation.expected_commission_kes),
                related_payment_ids=(),
                description=(
                    f"no commission payment for {calculation.rm_code} "
                    f"in {calculation.period}; expected "
                    f"{calculation.expected_commission_kes}"),
                framework_refs=("ENH-247 §payment_validation",)))
            return tuple(findings)

        if len(relevant) > 1:
            findings.append(CommissionAssuranceFinding(
                finding_id=(
                    f"COMM-MULTI-{calculation.rm_code}-"
                    f"{calculation.period}"),
                finding_type=CommissionFinding.MULTIPLE_PAYMENTS,
                severity=ValidationSeverity.MEDIUM,
                rm_code=calculation.rm_code,
                period=calculation.period,
                expected_kes=(
                    calculation.expected_commission_kes),
                paid_kes=sum(
                    (p.paid_kes for p in relevant), Decimal("0")),
                variance_kes=Decimal("0"),
                related_payment_ids=tuple(
                    p.payment_id for p in relevant),
                description=(
                    f"{len(relevant)} payments for one "
                    f"(rm, period); investigate duplication"),
                framework_refs=("ENH-247 §payment_validation",)))

        total_paid = sum(
            (p.paid_kes for p in relevant), Decimal("0"))
        variance = total_paid - calculation.expected_commission_kes
        if abs(variance) > self.PAYMENT_TOLERANCE_KES:
            ftype = (
                CommissionFinding.OVERPAID if variance > 0
                else CommissionFinding.UNDERPAID)
            findings.append(CommissionAssuranceFinding(
                finding_id=(
                    f"COMM-{ftype.value}-{calculation.rm_code}-"
                    f"{calculation.period}"),
                finding_type=ftype,
                severity=ValidationSeverity.MEDIUM,
                rm_code=calculation.rm_code,
                period=calculation.period,
                expected_kes=(
                    calculation.expected_commission_kes),
                paid_kes=total_paid,
                variance_kes=variance,
                related_payment_ids=tuple(
                    p.payment_id for p in relevant),
                description=(
                    f"variance {variance} between paid "
                    f"{total_paid} and expected "
                    f"{calculation.expected_commission_kes}"),
                framework_refs=(
                    "ENH-247 §payment_validation",
                    "Composes ENH-242 §commission_miscalc")))
        return tuple(findings)

    # ── Override authorization check ────────────────────────────────
    def validate_overrides(
        self,
        overrides: Sequence[CommissionOverride],
    ) -> Tuple[OverrideValidationResult, ...]:
        results: List[OverrideValidationResult] = []
        for o in overrides:
            if o.status == OverrideStatus.APPROVED:
                if not o.approval_id:
                    results.append(OverrideValidationResult(
                        override_id=o.override_id,
                        valid=False,
                        issue=(
                            "APPROVED status requires "
                            "approval_id")))
                    continue
                results.append(OverrideValidationResult(
                    override_id=o.override_id,
                    valid=True, issue=""))
            elif o.status == OverrideStatus.PENDING:
                results.append(OverrideValidationResult(
                    override_id=o.override_id,
                    valid=True, issue="pending review"))
            else:  # REJECTED
                results.append(OverrideValidationResult(
                    override_id=o.override_id,
                    valid=True, issue=""))
        return tuple(results)

    # ── Dispute summary ─────────────────────────────────────────────
    def summarize_disputes(
        self,
        disputes: Sequence[CommissionDispute],
    ) -> DisputeSummary:
        open_c = upheld_c = rejected_c = withdrawn_c = 0
        durations: List[int] = []
        for d in disputes:
            if d.status == DisputeStatus.OPEN:
                open_c += 1
            elif d.status == DisputeStatus.UPHELD:
                upheld_c += 1
            elif d.status == DisputeStatus.REJECTED:
                rejected_c += 1
            else:
                withdrawn_c += 1
            if d.resolved_date is not None:
                days = (
                    d.resolved_date.toordinal()
                    - d.raised_date.toordinal())
                if days >= 0:
                    durations.append(days)
        avg = None
        if durations:
            avg = (
                Decimal(sum(durations))
                / Decimal(len(durations))).quantize(
                    Decimal("0.01"))
        return DisputeSummary(
            open_count=open_c, upheld_count=upheld_c,
            rejected_count=rejected_c,
            withdrawn_count=withdrawn_c,
            avg_resolution_days=avg)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _simple_plan():
    return IncentivePlan(
        plan_id="P-001", rm_role="RM-Tier-1",
        tiers=(
            CommissionTier(
                tier_min_kes=Decimal("0"),
                tier_max_kes=Decimal("100000"),
                rate_pct=Decimal("0.02")),     # 2%
            CommissionTier(
                tier_min_kes=Decimal("100000"),
                tier_max_kes=Decimal("500000"),
                rate_pct=Decimal("0.03")),     # 3%
            CommissionTier(
                tier_min_kes=Decimal("500000"),
                tier_max_kes=None,
                rate_pct=Decimal("0.05")),     # 5%
        ))


def _test_tier_validates_min_below_max():
    try:
        CommissionTier(
            tier_min_kes=Decimal("100"),
            tier_max_kes=Decimal("50"),
            rate_pct=Decimal("0.01"))
        assert False
    except ValueError:
        pass


def _test_tier_validates_rate_range():
    try:
        CommissionTier(
            tier_min_kes=Decimal("0"),
            tier_max_kes=None,
            rate_pct=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_plan_validates_non_empty_tiers():
    try:
        IncentivePlan(
            plan_id="P", rm_role="r", tiers=())
        assert False
    except ValueError:
        pass


def _test_plan_validates_tier_ordering():
    try:
        IncentivePlan(
            plan_id="P", rm_role="r",
            tiers=(
                CommissionTier(
                    tier_min_kes=Decimal("100"),
                    tier_max_kes=Decimal("200"),
                    rate_pct=Decimal("0.01")),
                CommissionTier(
                    tier_min_kes=Decimal("50"),  # out of order
                    tier_max_kes=Decimal("300"),
                    rate_pct=Decimal("0.02")),
            ))
        assert False
    except ValueError:
        pass


def _test_marginal_below_first_tier():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    # Revenue 0 → all tiers contribute 0
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("0"))
    assert calc.expected_commission_kes == Decimal("0.00")


def _test_marginal_within_first_tier():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    # 50,000 × 2% = 1,000
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("50000"))
    assert calc.expected_commission_kes == Decimal("1000.00")


def _test_marginal_spans_tiers():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    # 200,000 → 100k × 2% + 100k × 3% = 2,000 + 3,000 = 5,000
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))
    assert calc.expected_commission_kes == Decimal("5000.00")


def _test_marginal_top_tier_unbounded():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    # 1,000,000 → 100k × 2% + 400k × 3% + 500k × 5%
    # = 2,000 + 12,000 + 25,000 = 39,000
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("1000000"))
    assert calc.expected_commission_kes == Decimal("39000.00")


def _test_cumulative_basis_uses_single_tier():
    eng = CommissionAssuranceEngine()
    plan = IncentivePlan(
        plan_id="P-CUM", rm_role="r",
        tiers=_simple_plan().tiers,
        basis=TierBasis.CUMULATIVE)
    # 200,000 in 2nd tier → whole 200,000 × 3% = 6,000
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))
    assert calc.expected_commission_kes == Decimal("6000.00")
    # Only one contribution under CUMULATIVE
    assert len(calc.contributions) == 1


def _test_contributions_surface_per_tier():
    """Per Rule 1 — RM disputing should see exactly which tier
    fired and how much."""
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))
    assert len(calc.contributions) == 3
    assert calc.contributions[0].contribution_kes == Decimal("2000")
    assert calc.contributions[1].contribution_kes == Decimal("3000")
    assert calc.contributions[2].amount_in_tier_kes == Decimal("0")


def _test_compute_validates_negative_revenue():
    eng = CommissionAssuranceEngine()
    try:
        eng.compute_expected_commission(
            _simple_plan(), "rm1", "2026-04", Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_payment_match_no_findings():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))   # exp 5000
    payments = (
        PaidCommissionRecord(
            payment_id="PAY-1", rm_code="rm1",
            period="2026-04",
            paid_kes=Decimal("5000"),
            payment_date=date(2026, 5, 1)),
    )
    findings = eng.validate_paid_vs_computed(calc, payments)
    assert len(findings) == 0


def _test_payment_underpaid_finding():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))   # exp 5000
    payments = (
        PaidCommissionRecord(
            payment_id="PAY-1", rm_code="rm1",
            period="2026-04",
            paid_kes=Decimal("4000"),
            payment_date=date(2026, 5, 1)),
    )
    findings = eng.validate_paid_vs_computed(calc, payments)
    assert len(findings) == 1
    assert findings[0].finding_type == CommissionFinding.UNDERPAID


def _test_payment_missing_finding():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))
    findings = eng.validate_paid_vs_computed(calc, ())
    assert len(findings) == 1
    assert (
        findings[0].finding_type
        == CommissionFinding.MISSING_PAYMENT)
    assert findings[0].severity == ValidationSeverity.HIGH


def _test_payment_multiple_finding():
    eng = CommissionAssuranceEngine()
    plan = _simple_plan()
    calc = eng.compute_expected_commission(
        plan, "rm1", "2026-04", Decimal("200000"))
    payments = (
        PaidCommissionRecord(
            payment_id="PAY-1", rm_code="rm1",
            period="2026-04",
            paid_kes=Decimal("2500"),
            payment_date=date(2026, 5, 1)),
        PaidCommissionRecord(
            payment_id="PAY-2", rm_code="rm1",
            period="2026-04",
            paid_kes=Decimal("2500"),
            payment_date=date(2026, 5, 2)),
    )
    findings = eng.validate_paid_vs_computed(calc, payments)
    assert any(
        f.finding_type == CommissionFinding.MULTIPLE_PAYMENTS
        for f in findings)


def _test_override_approved_needs_approval_id():
    eng = CommissionAssuranceEngine()
    overrides = (
        CommissionOverride(
            override_id="O-1", rm_code="rm1", period="2026-04",
            delta_kes=Decimal("1000"), reason="performance bonus",
            status=OverrideStatus.APPROVED, approval_id=None),
    )
    results = eng.validate_overrides(overrides)
    assert results[0].valid is False
    assert "approval_id" in results[0].issue


def _test_override_approved_with_id_valid():
    eng = CommissionAssuranceEngine()
    overrides = (
        CommissionOverride(
            override_id="O-1", rm_code="rm1", period="2026-04",
            delta_kes=Decimal("1000"), reason="performance bonus",
            status=OverrideStatus.APPROVED,
            approval_id="APP-001"),
    )
    results = eng.validate_overrides(overrides)
    assert results[0].valid is True


def _test_override_validates_reason_non_empty():
    try:
        CommissionOverride(
            override_id="O-1", rm_code="rm1", period="2026-04",
            delta_kes=Decimal("1000"), reason="",
            status=OverrideStatus.PENDING)
        assert False
    except ValueError:
        pass


def _test_dispute_validates_resolved_date():
    try:
        CommissionDispute(
            dispute_id="D-1", rm_code="rm1", period="2026-04",
            status=DisputeStatus.UPHELD,
            raised_date=date(2026, 5, 1),
            resolved_date=None)
        assert False
    except ValueError:
        pass


def _test_dispute_summary_aggregates():
    eng = CommissionAssuranceEngine()
    disputes = (
        CommissionDispute(
            dispute_id="D-1", rm_code="rm1", period="2026-04",
            status=DisputeStatus.UPHELD,
            raised_date=date(2026, 5, 1),
            resolved_date=date(2026, 5, 11)),
        CommissionDispute(
            dispute_id="D-2", rm_code="rm2", period="2026-04",
            status=DisputeStatus.OPEN,
            raised_date=date(2026, 5, 5)),
        CommissionDispute(
            dispute_id="D-3", rm_code="rm3", period="2026-04",
            status=DisputeStatus.REJECTED,
            raised_date=date(2026, 5, 1),
            resolved_date=date(2026, 5, 6)),
    )
    summary = eng.summarize_disputes(disputes)
    assert summary.open_count == 1
    assert summary.upheld_count == 1
    assert summary.rejected_count == 1
    # Avg of 10 and 5 = 7.5
    assert summary.avg_resolution_days == Decimal("7.50")


def self_test() -> None:
    tests = [
        _test_tier_validates_min_below_max,
        _test_tier_validates_rate_range,
        _test_plan_validates_non_empty_tiers,
        _test_plan_validates_tier_ordering,
        _test_marginal_below_first_tier,
        _test_marginal_within_first_tier,
        _test_marginal_spans_tiers,
        _test_marginal_top_tier_unbounded,
        _test_cumulative_basis_uses_single_tier,
        _test_contributions_surface_per_tier,
        _test_compute_validates_negative_revenue,
        _test_payment_match_no_findings,
        _test_payment_underpaid_finding,
        _test_payment_missing_finding,
        _test_payment_multiple_finding,
        _test_override_approved_needs_approval_id,
        _test_override_approved_with_id_valid,
        _test_override_validates_reason_non_empty,
        _test_dispute_validates_resolved_date,
        _test_dispute_summary_aggregates,
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
            f"✗ commission_assurance self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ commission_assurance self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

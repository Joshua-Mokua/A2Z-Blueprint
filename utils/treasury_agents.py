"""utils/treasury_agents.py — v10.37 ENH-240: Agentic Treasury.

╔════════════════════════════════════════════════════════════════════════╗
║  AGENTIC TREASURY ORCHESTRATION (Kyriba TAI-class)                     ║
║  Cat A — autonomous-with-human-approval treasury workflows            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-240: agentic treasury orchestration patterned after  ║
║  Kyriba Treasury AI (TAI). Each TreasuryAgent is a deterministic     ║
║  policy that:                                                          ║
║    1. Reads one or more upstream Treasury engines                     ║
║    2. Detects a condition (e.g., LCR < buffer, idle cash > threshold)║
║    3. Generates a Recommendation with rationale + suggested action  ║
║    4. Optionally requires human approval before execution             ║
║                                                                         ║
║  Five concrete agents ship:                                            ║
║    CashShortfallAgent — reads cash_forecasting; flags days where     ║
║      projected balance < min_buffer; suggests funding sources        ║
║      (interbank borrow, MMF redemption, repo).                       ║
║    LiquidityBufferAgent — reads treasury_alm; flags LCR ≤ buffer    ║
║      (e.g., 110%); suggests increasing HQLA allocation.              ║
║    HedgingAgent — reads treasury_alm; flags IRRBB EVE outliers;      ║
║      suggests interest rate swap to reduce gap.                      ║
║    PaymentReviewAgent — reads pending payments queue; flags          ║
║      suspicious patterns (round-number large amounts, off-hours,    ║
║      new beneficiaries) per ENH-TRS-R5 stop-fraud requirements.    ║
║    SweepingAgent — reads cash positions across accounts; suggests   ║
║      consolidation moves to MMF for excess cash.                    ║
║                                                                         ║
║  Orchestration pattern:                                                ║
║    AgentOrchestrator runs all registered agents in priority order.   ║
║    Recommendations are queued by ApprovalStatus.PENDING.             ║
║    Human treasurer approves/rejects → status changes.                ║
║    Approved recommendations can be marked EXECUTED (action recording ║
║    happens via downstream engines; this engine doesn't execute).    ║
║                                                                         ║
║  Honesty Rule 1: every Recommendation surfaces detected_condition + ║
║  rationale + suggested_action + estimated_impact + agent_name +     ║
║  upstream_engines_consulted + framework_refs.                       ║
║  Honesty Rule 7: agents never autonomously execute. They produce   ║
║  recommendations; human approval is structural.                     ║
║                                                                         ║
║  Coexists with: treasury_alm (v10.33), cash_forecasting (v10.35),   ║
║  treasury_dashboard (v10.35). Composes; never mutates upstream.    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel BCBS 144 — sound principles for liquidity mgmt              ║
║    Basel BCBS 248 — intraday liquidity monitoring                     ║
║    Basel BCBS 368 — IRRBB                                             ║
║    EU AI Act — Art 14 human oversight for high-risk AI               ║
║    CBK CBK/PG/16 — liquidity management                               ║
║    Kyriba Treasury AI (TAI) reference architecture                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "Five concrete TreasuryAgent classes implement ENH-240 patterned "
    "after Kyriba TAI. Per Rule 7, agents NEVER autonomously execute; "
    "every recommendation requires human approval (ApprovalStatus). "
    "Per Rule 1, every Recommendation surfaces detected_condition + "
    "rationale + suggested_action + estimated_impact + framework_refs."
)


# ════════════════════════════════════════════════════════════════════════
# Recommendation taxonomy
# ════════════════════════════════════════════════════════════════════════

class RecommendationPriority(Enum):
    """Priority ordering for recommendations."""
    URGENT = "URGENT"                     # immediate action needed
    HIGH = "HIGH"                         # within 24 hours
    MEDIUM = "MEDIUM"                     # within 1 week
    LOW = "LOW"                           # advisory


class RecommendationCategory(Enum):
    """Type of recommendation."""
    LIQUIDITY = "LIQUIDITY"
    HEDGING = "HEDGING"
    INVESTMENT = "INVESTMENT"
    PAYMENT_REVIEW = "PAYMENT_REVIEW"
    SWEEPING = "SWEEPING"
    OTHER = "OTHER"


class ApprovalStatus(Enum):
    """Lifecycle of a recommendation."""
    PENDING = "PENDING"                   # awaiting human review
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class Recommendation:
    """One treasury action recommendation from an agent."""
    recommendation_id: str
    agent_name: str
    category: RecommendationCategory
    priority: RecommendationPriority
    detected_condition: str
    rationale: str
    suggested_action: str
    estimated_impact_kes: Decimal
    upstream_engines_consulted: Tuple[str, ...]
    framework_refs: Tuple[str, ...]
    created_at: str                       # ISO-8601
    expires_at: Optional[str] = None
    notes: str = ""


@dataclass
class RecommendationLifecycle:
    """Mutable approval state — separate from Recommendation."""
    recommendation_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    executed_at: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# Agent base class
# ════════════════════════════════════════════════════════════════════════

class TreasuryAgent(ABC):
    """Abstract base for treasury agents.

    Each agent reads upstream engines (passed in `engines` mapping)
    and produces zero or more Recommendations.
    """

    @property
    @abstractmethod
    def agent_name(self) -> str:
        ...

    @property
    @abstractmethod
    def required_engines(self) -> Tuple[str, ...]:
        ...

    @abstractmethod
    def evaluate(
        self, engines: Mapping[str, Any], as_of_date: str,
    ) -> Sequence[Recommendation]:
        ...

    def can_run(
        self, engines: Mapping[str, Any],
    ) -> Tuple[bool, str]:
        """Check if all required engines are present + non-None."""
        for name in self.required_engines:
            if name not in engines or engines[name] is None:
                return False, f"missing engine: {name}"
        return True, ""


# ════════════════════════════════════════════════════════════════════════
# Concrete agents
# ════════════════════════════════════════════════════════════════════════

class LiquidityBufferAgent(TreasuryAgent):
    """Reads treasury_alm; flags LCR within buffer of 100% threshold."""

    def __init__(
        self, *, lcr_warning_buffer_pct: Decimal = Decimal("110"),
        recommendation_id_prefix: str = "lba",
    ):
        self.buffer = lcr_warning_buffer_pct
        self.id_prefix = recommendation_id_prefix
        self._counter = 0

    @property
    def agent_name(self) -> str:
        return "LiquidityBufferAgent"

    @property
    def required_engines(self) -> Tuple[str, ...]:
        return ("treasury_alm",)

    def evaluate(
        self, engines: Mapping[str, Any], as_of_date: str,
    ) -> Sequence[Recommendation]:
        alm = engines["treasury_alm"]
        summary = alm.board_summary()
        if summary.get("latest_lcr_pct") is None:
            return ()
        lcr_pct = Decimal(summary["latest_lcr_pct"])
        recs: List[Recommendation] = []
        if lcr_pct < Decimal("100"):
            self._counter += 1
            recs.append(Recommendation(
                recommendation_id=(
                    f"{self.id_prefix}-{self._counter:04d}"),
                agent_name=self.agent_name,
                category=RecommendationCategory.LIQUIDITY,
                priority=RecommendationPriority.URGENT,
                detected_condition=(
                    f"LCR breach: {lcr_pct}% < Basel BCBS 188 "
                    f"100% minimum"),
                rationale=(
                    f"Bank is below the Basel LCR floor; immediate "
                    f"action required to restore compliance and "
                    f"avoid CBK supervisory action"),
                suggested_action=(
                    "Increase Level-1 HQLA buffer (sovereign bills, "
                    "CBK reserves) and/or reduce 30-day net cash "
                    "outflows via interbank borrowing or repo"),
                estimated_impact_kes=Decimal("0"),
                upstream_engines_consulted=("treasury_alm",),
                framework_refs=(
                    "Basel BCBS 188", "CBK CBK/PG/16"),
                created_at=as_of_date,
                expires_at=None))
        elif lcr_pct < self.buffer:
            self._counter += 1
            recs.append(Recommendation(
                recommendation_id=(
                    f"{self.id_prefix}-{self._counter:04d}"),
                agent_name=self.agent_name,
                category=RecommendationCategory.LIQUIDITY,
                priority=RecommendationPriority.HIGH,
                detected_condition=(
                    f"LCR within buffer: {lcr_pct}% ≤ "
                    f"{self.buffer}% warning threshold"),
                rationale=(
                    f"LCR is compliant but within "
                    f"{self.buffer - Decimal('100')}pp of the "
                    f"Basel minimum; replenish buffer before next "
                    f"reporting cycle"),
                suggested_action=(
                    "Add HQLA Level-1 ahead of month-end reporting"),
                estimated_impact_kes=Decimal("0"),
                upstream_engines_consulted=("treasury_alm",),
                framework_refs=(
                    "Basel BCBS 188", "CBK CBK/PG/16"),
                created_at=as_of_date))
        return tuple(recs)


class HedgingAgent(TreasuryAgent):
    """Reads treasury_alm; flags IRRBB outliers."""

    def __init__(
        self, *, recommendation_id_prefix: str = "hda",
    ):
        self.id_prefix = recommendation_id_prefix
        self._counter = 0

    @property
    def agent_name(self) -> str:
        return "HedgingAgent"

    @property
    def required_engines(self) -> Tuple[str, ...]:
        return ("treasury_alm",)

    def evaluate(
        self, engines: Mapping[str, Any], as_of_date: str,
    ) -> Sequence[Recommendation]:
        alm = engines["treasury_alm"]
        summary = alm.board_summary()
        n_outliers = summary.get("n_eve_outliers", 0)
        if n_outliers == 0:
            return ()
        self._counter += 1
        return (Recommendation(
            recommendation_id=(
                f"{self.id_prefix}-{self._counter:04d}"),
            agent_name=self.agent_name,
            category=RecommendationCategory.HEDGING,
            priority=RecommendationPriority.HIGH,
            detected_condition=(
                f"IRRBB: {n_outliers} BCBS 368 scenario(s) flagged "
                f"outlier (ΔEVE > 15% Tier 1)"),
            rationale=(
                "Asset-liability rate-sensitivity gap exceeds "
                "regulatory outlier threshold; hedging required to "
                "reduce interest rate risk capital impact"),
            suggested_action=(
                "Execute pay-fixed receive-floating IRS at the "
                "longest gap bucket; size to neutralize at least "
                "50% of EVE delta"),
            estimated_impact_kes=Decimal("0"),
            upstream_engines_consulted=("treasury_alm",),
            framework_refs=(
                "Basel BCBS 368", "EBA EBA/GL/2022/14"),
            created_at=as_of_date),)


class CashShortfallAgent(TreasuryAgent):
    """Reads cash_forecasting; flags projected shortfall days."""

    def __init__(
        self, *,
        min_buffer_kes: Decimal = Decimal("100000000"),
        recommendation_id_prefix: str = "csa",
    ):
        self.min_buffer = min_buffer_kes
        self.id_prefix = recommendation_id_prefix
        self._counter = 0

    @property
    def agent_name(self) -> str:
        return "CashShortfallAgent"

    @property
    def required_engines(self) -> Tuple[str, ...]:
        return ("cash_forecasting",)

    def evaluate(
        self, engines: Mapping[str, Any], as_of_date: str,
    ) -> Sequence[Recommendation]:
        forecast_eng = engines["cash_forecasting"]
        if not hasattr(forecast_eng, "_forecasts"):
            return ()
        forecasts = forecast_eng._forecasts
        recs: List[Recommendation] = []
        for fid, result in forecasts.items():
            running_balance = self.min_buffer
            for point in result.points:
                running_balance += point.total_kes
                if running_balance < Decimal("0"):
                    self._counter += 1
                    recs.append(Recommendation(
                        recommendation_id=(
                            f"{self.id_prefix}-"
                            f"{self._counter:04d}"),
                        agent_name=self.agent_name,
                        category=RecommendationCategory.LIQUIDITY,
                        priority=RecommendationPriority.HIGH,
                        detected_condition=(
                            f"Projected shortfall on "
                            f"{point.forecast_date}: running "
                            f"balance {running_balance:,.0f} KES"),
                        rationale=(
                            f"Forecast {fid} projects net cash "
                            f"position falling below zero; "
                            f"funding gap requires action"),
                        suggested_action=(
                            "Pre-arrange interbank credit line, "
                            "redeem MMF positions, or schedule "
                            "repo against HQLA L1 collateral"),
                        estimated_impact_kes=abs(running_balance),
                        upstream_engines_consulted=(
                            "cash_forecasting",),
                        framework_refs=(
                            "Basel BCBS 144", "Basel BCBS 248"),
                        created_at=as_of_date))
                    break    # one rec per forecast
        return tuple(recs)


class PaymentReviewAgent(TreasuryAgent):
    """Reviews pending payments for suspicious patterns.

    Per ENH-TRS-R5, real-time payment review is essential to stop
    fraud BEFORE batch processing. This agent emits a recommendation
    for each suspicious payment.
    """

    SUSPICIOUS_THRESHOLD_KES = Decimal("10000000")

    def __init__(
        self, *, recommendation_id_prefix: str = "pra",
    ):
        self.id_prefix = recommendation_id_prefix
        self._counter = 0

    @property
    def agent_name(self) -> str:
        return "PaymentReviewAgent"

    @property
    def required_engines(self) -> Tuple[str, ...]:
        return ()    # works on payment list passed in directly

    def evaluate(
        self, engines: Mapping[str, Any], as_of_date: str,
    ) -> Sequence[Recommendation]:
        # PaymentReviewAgent works on a payments queue passed via
        # engines["pending_payments"] = list of payment dicts
        payments = engines.get("pending_payments", ())
        recs: List[Recommendation] = []
        for pmt in payments:
            amount = pmt.get("amount_kes", Decimal("0"))
            if not isinstance(amount, Decimal):
                amount = Decimal(str(amount))
            beneficiary = pmt.get("beneficiary", "")
            is_new_beneficiary = pmt.get(
                "is_new_beneficiary", False)
            is_off_hours = pmt.get("is_off_hours", False)
            is_round = (
                amount % Decimal("1000000") == Decimal("0")
                and amount >= self.SUSPICIOUS_THRESHOLD_KES)
            risk_factors: List[str] = []
            if is_round:
                risk_factors.append("round-number large amount")
            if is_new_beneficiary:
                risk_factors.append("new beneficiary")
            if is_off_hours:
                risk_factors.append("off-hours submission")
            if amount > Decimal("100000000"):
                risk_factors.append("> 100M threshold")
            if len(risk_factors) >= 2:
                self._counter += 1
                recs.append(Recommendation(
                    recommendation_id=(
                        f"{self.id_prefix}-{self._counter:04d}"),
                    agent_name=self.agent_name,
                    category=RecommendationCategory.PAYMENT_REVIEW,
                    priority=RecommendationPriority.URGENT,
                    detected_condition=(
                        f"Suspicious payment: {amount:,.0f} KES to "
                        f"{beneficiary} — risk factors: "
                        f"{', '.join(risk_factors)}"),
                    rationale=(
                        f"{len(risk_factors)} risk factors trigger "
                        f"manual review per ENH-TRS-R5 real-time "
                        f"payment fraud control"),
                    suggested_action=(
                        "Hold payment; require dual treasurer "
                        "approval before release"),
                    estimated_impact_kes=amount,
                    upstream_engines_consulted=(),
                    framework_refs=(
                        "ENH-TRS-R5", "CBK Banking Act §35"),
                    created_at=as_of_date,
                    notes=f"payment_id={pmt.get('payment_id', '?')}"))
        return tuple(recs)


class SweepingAgent(TreasuryAgent):
    """Detects idle cash above threshold; suggests MMF placement."""

    def __init__(
        self, *,
        idle_cash_threshold_kes: Decimal = Decimal("500000000"),
        recommendation_id_prefix: str = "swa",
    ):
        self.threshold = idle_cash_threshold_kes
        self.id_prefix = recommendation_id_prefix
        self._counter = 0

    @property
    def agent_name(self) -> str:
        return "SweepingAgent"

    @property
    def required_engines(self) -> Tuple[str, ...]:
        return ()    # works on context input

    def evaluate(
        self, engines: Mapping[str, Any], as_of_date: str,
    ) -> Sequence[Recommendation]:
        # Cash positions passed via engines["cash_positions"]
        # = list of {"account_id", "balance_kes"}
        positions = engines.get("cash_positions", ())
        recs: List[Recommendation] = []
        for pos in positions:
            balance = pos.get("balance_kes", Decimal("0"))
            if not isinstance(balance, Decimal):
                balance = Decimal(str(balance))
            if balance > self.threshold:
                self._counter += 1
                excess = balance - self.threshold
                recs.append(Recommendation(
                    recommendation_id=(
                        f"{self.id_prefix}-{self._counter:04d}"),
                    agent_name=self.agent_name,
                    category=RecommendationCategory.SWEEPING,
                    priority=RecommendationPriority.MEDIUM,
                    detected_condition=(
                        f"Idle cash: account "
                        f"{pos.get('account_id', '?')} holds "
                        f"{balance:,.0f} KES > threshold "
                        f"{self.threshold:,.0f} KES"),
                    rationale=(
                        "Idle cash earns minimal/no return; sweeping "
                        "to a money market fund (ENH-TRS-R3) "
                        "improves treasury yield without sacrificing "
                        "next-day liquidity"),
                    suggested_action=(
                        f"Sweep {excess:,.0f} KES excess to "
                        f"approved MMF counterparty"),
                    estimated_impact_kes=excess,
                    upstream_engines_consulted=(),
                    framework_refs=("ENH-TRS-R3",),
                    created_at=as_of_date))
        return tuple(recs)


# ════════════════════════════════════════════════════════════════════════
# Orchestrator
# ════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """Runs registered agents; tracks recommendation lifecycles."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._agents: List[TreasuryAgent] = []
        self._recommendations: Dict[str, Recommendation] = {}
        self._lifecycles: Dict[str, RecommendationLifecycle] = {}

    def register_agent(self, agent: TreasuryAgent) -> None:
        for existing in self._agents:
            if existing.agent_name == agent.agent_name:
                raise ValueError(
                    f"agent {agent.agent_name} already registered")
        self._agents.append(agent)

    def run_all(
        self, *, engines: Mapping[str, Any], as_of_date: str,
    ) -> Tuple[Recommendation, ...]:
        """Run every registered agent; collect recommendations."""
        recs: List[Recommendation] = []
        for agent in self._agents:
            ok, reason = agent.can_run(engines)
            if not ok:
                continue    # skip silently
            agent_recs = agent.evaluate(engines, as_of_date)
            for r in agent_recs:
                if r.recommendation_id in self._recommendations:
                    raise ValueError(
                        f"duplicate recommendation_id: "
                        f"{r.recommendation_id}")
                self._recommendations[r.recommendation_id] = r
                self._lifecycles[r.recommendation_id] = (
                    RecommendationLifecycle(
                        recommendation_id=r.recommendation_id))
                recs.append(r)
        # Sort by priority (URGENT first)
        priority_order = {
            RecommendationPriority.URGENT: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3}
        recs.sort(key=lambda r: priority_order[r.priority])
        return tuple(recs)

    # ── Approval workflow ─────────────────────────────────────────────
    def approve(
        self, recommendation_id: str, *,
        approver: str, approved_at: str,
    ) -> RecommendationLifecycle:
        if recommendation_id not in self._lifecycles:
            raise KeyError(
                f"recommendation {recommendation_id} not found")
        lc = self._lifecycles[recommendation_id]
        if lc.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"cannot approve recommendation in state "
                f"{lc.status.value}; must be PENDING")
        lc.status = ApprovalStatus.APPROVED
        lc.approved_by = approver
        lc.approved_at = approved_at
        return lc

    def reject(
        self, recommendation_id: str, *,
        approver: str, rejection_reason: str, at: str,
    ) -> RecommendationLifecycle:
        if recommendation_id not in self._lifecycles:
            raise KeyError(
                f"recommendation {recommendation_id} not found")
        lc = self._lifecycles[recommendation_id]
        if lc.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"cannot reject recommendation in state "
                f"{lc.status.value}")
        lc.status = ApprovalStatus.REJECTED
        lc.approved_by = approver
        lc.approved_at = at
        lc.rejection_reason = rejection_reason
        return lc

    def mark_executed(
        self, recommendation_id: str, *, at: str,
    ) -> RecommendationLifecycle:
        if recommendation_id not in self._lifecycles:
            raise KeyError(
                f"recommendation {recommendation_id} not found")
        lc = self._lifecycles[recommendation_id]
        if lc.status != ApprovalStatus.APPROVED:
            raise ValueError(
                f"can only execute APPROVED recommendation; "
                f"current state {lc.status.value}")
        lc.status = ApprovalStatus.EXECUTED
        lc.executed_at = at
        return lc

    # ── Reporting ──────────────────────────────────────────────────────
    @property
    def n_agents(self) -> int:
        return len(self._agents)

    @property
    def n_recommendations(self) -> int:
        return len(self._recommendations)

    def by_status(
        self, status: ApprovalStatus,
    ) -> Tuple[Recommendation, ...]:
        return tuple(
            self._recommendations[lid]
            for lid, lc in self._lifecycles.items()
            if lc.status == status)

    def board_summary(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "n_agents": self.n_agents,
            "n_recommendations": self.n_recommendations,
            "n_pending": len(self.by_status(ApprovalStatus.PENDING)),
            "n_approved": len(
                self.by_status(ApprovalStatus.APPROVED)),
            "n_rejected": len(
                self.by_status(ApprovalStatus.REJECTED)),
            "n_executed": len(
                self.by_status(ApprovalStatus.EXECUTED)),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

class _StubALM:
    """Minimal stub for ALM with configurable summary."""
    def __init__(self, summary):
        self._s = summary

    def board_summary(self):
        return self._s


def _test_liquidity_agent_no_data():
    agent = LiquidityBufferAgent()
    alm = _StubALM({"latest_lcr_pct": None})
    recs = agent.evaluate(
        {"treasury_alm": alm}, as_of_date="2026-05-01")
    assert recs == ()


def _test_liquidity_agent_compliant_no_rec():
    agent = LiquidityBufferAgent(
        lcr_warning_buffer_pct=Decimal("110"))
    alm = _StubALM({
        "latest_lcr_pct": "150.00",
        "latest_lcr_compliant": True})
    recs = agent.evaluate(
        {"treasury_alm": alm}, as_of_date="2026-05-01")
    assert recs == ()


def _test_liquidity_agent_warning_buffer():
    agent = LiquidityBufferAgent(
        lcr_warning_buffer_pct=Decimal("110"))
    alm = _StubALM({
        "latest_lcr_pct": "105.00",
        "latest_lcr_compliant": True})
    recs = agent.evaluate(
        {"treasury_alm": alm}, as_of_date="2026-05-01")
    assert len(recs) == 1
    assert recs[0].priority == RecommendationPriority.HIGH


def _test_liquidity_agent_breach_urgent():
    agent = LiquidityBufferAgent()
    alm = _StubALM({
        "latest_lcr_pct": "85.00",
        "latest_lcr_compliant": False})
    recs = agent.evaluate(
        {"treasury_alm": alm}, as_of_date="2026-05-01")
    assert len(recs) == 1
    assert recs[0].priority == RecommendationPriority.URGENT


def _test_hedging_agent_no_outliers():
    agent = HedgingAgent()
    alm = _StubALM({"n_eve_outliers": 0})
    recs = agent.evaluate(
        {"treasury_alm": alm}, as_of_date="2026-05-01")
    assert recs == ()


def _test_hedging_agent_with_outliers():
    agent = HedgingAgent()
    alm = _StubALM({"n_eve_outliers": 2})
    recs = agent.evaluate(
        {"treasury_alm": alm}, as_of_date="2026-05-01")
    assert len(recs) == 1
    assert "BCBS 368" in recs[0].framework_refs[0]


def _test_payment_review_clean_no_rec():
    agent = PaymentReviewAgent()
    payments = [
        {"payment_id": "P1", "amount_kes": Decimal("500000"),
         "beneficiary": "Trusted Co", "is_new_beneficiary": False,
         "is_off_hours": False}]
    recs = agent.evaluate(
        {"pending_payments": payments}, as_of_date="2026-05-01")
    assert recs == ()


def _test_payment_review_suspicious_pattern():
    agent = PaymentReviewAgent()
    payments = [{
        "payment_id": "P1",
        "amount_kes": Decimal("50000000"),    # round + large
        "beneficiary": "New Co",
        "is_new_beneficiary": True,           # new
        "is_off_hours": True}]                # off-hours
    recs = agent.evaluate(
        {"pending_payments": payments}, as_of_date="2026-05-01")
    assert len(recs) == 1
    assert recs[0].priority == RecommendationPriority.URGENT


def _test_sweeping_agent_idle_cash():
    agent = SweepingAgent(
        idle_cash_threshold_kes=Decimal("100000000"))
    positions = [
        {"account_id": "ACC-1", "balance_kes": Decimal("500000000")}]
    recs = agent.evaluate(
        {"cash_positions": positions}, as_of_date="2026-05-01")
    assert len(recs) == 1
    assert recs[0].category == RecommendationCategory.SWEEPING
    assert recs[0].estimated_impact_kes == Decimal("400000000")


def _test_orchestrator_dup_agent_raises():
    o = AgentOrchestrator()
    o.register_agent(LiquidityBufferAgent())
    try:
        o.register_agent(LiquidityBufferAgent())
        assert False
    except ValueError:
        pass


def _test_orchestrator_run_all_sorts_by_priority():
    o = AgentOrchestrator()
    o.register_agent(LiquidityBufferAgent())
    o.register_agent(HedgingAgent())
    alm = _StubALM({
        "latest_lcr_pct": "85.00",
        "latest_lcr_compliant": False,
        "n_eve_outliers": 1})
    recs = o.run_all(
        engines={"treasury_alm": alm},
        as_of_date="2026-05-01")
    assert len(recs) == 2
    # URGENT first
    assert recs[0].priority == RecommendationPriority.URGENT


def _test_approval_workflow():
    o = AgentOrchestrator()
    o.register_agent(LiquidityBufferAgent())
    alm = _StubALM({
        "latest_lcr_pct": "105.00",
        "latest_lcr_compliant": True})
    recs = o.run_all(
        engines={"treasury_alm": alm},
        as_of_date="2026-05-01")
    rid = recs[0].recommendation_id
    lc = o.approve(
        rid, approver="treasurer", approved_at="2026-05-01T10:00:00Z")
    assert lc.status == ApprovalStatus.APPROVED
    o.mark_executed(rid, at="2026-05-01T11:00:00Z")
    assert o.board_summary()["n_executed"] == 1


def _test_cannot_approve_already_approved():
    o = AgentOrchestrator()
    o.register_agent(LiquidityBufferAgent())
    alm = _StubALM({
        "latest_lcr_pct": "105.00",
        "latest_lcr_compliant": True})
    recs = o.run_all(
        engines={"treasury_alm": alm},
        as_of_date="2026-05-01")
    rid = recs[0].recommendation_id
    o.approve(rid, approver="t", approved_at="2026-05-01T10:00:00Z")
    try:
        o.approve(rid, approver="t",
                  approved_at="2026-05-01T11:00:00Z")
        assert False
    except ValueError:
        pass


def _test_can_run_skips_missing_engine():
    agent = LiquidityBufferAgent()
    ok, reason = agent.can_run({})
    assert ok is False
    assert "treasury_alm" in reason


def _test_orchestrator_skips_agent_with_missing_engine():
    """LiquidityBufferAgent silently skipped if no ALM."""
    o = AgentOrchestrator()
    o.register_agent(LiquidityBufferAgent())
    recs = o.run_all(engines={}, as_of_date="2026-05-01")
    assert recs == ()


def self_test() -> None:
    tests = [
        _test_liquidity_agent_no_data,
        _test_liquidity_agent_compliant_no_rec,
        _test_liquidity_agent_warning_buffer,
        _test_liquidity_agent_breach_urgent,
        _test_hedging_agent_no_outliers,
        _test_hedging_agent_with_outliers,
        _test_payment_review_clean_no_rec,
        _test_payment_review_suspicious_pattern,
        _test_sweeping_agent_idle_cash,
        _test_orchestrator_dup_agent_raises,
        _test_orchestrator_run_all_sorts_by_priority,
        _test_approval_workflow,
        _test_cannot_approve_already_approved,
        _test_can_run_skips_missing_engine,
        _test_orchestrator_skips_agent_with_missing_engine,
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
        print(f"✗ treasury_agents self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ treasury_agents self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

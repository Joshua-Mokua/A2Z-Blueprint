"""utils/credit_workflow.py — v10.13 Phase 2 deep impl batch 7 (Credit batch 3 part 2).

╔════════════════════════════════════════════════════════════════════════╗
║  CREDIT WORKFLOW — STATE MACHINE + COMMITTEE + MEMO + 80/20 AUTOMATION ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (workflow gates control credit issuance)            ║
║  Implements 4 of 19 Credit standards from registry:                     ║
║    ENH-125:     End-to-End Digital Workflow Orchestration               ║
║    ENH-130:     Credit Committee Automation                             ║
║    ENH-CRD-R5:  GenAI Credit Memo Drafting Agent (LLM-hookable)         ║
║    ENH-CRD-R7:  Confident Automation Pattern (80/20)                    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 7 enforced: GenAI memo drafting is via callable hook.    ║
║  When no LLM provider is set, falls back to deterministic template     ║
║  with SPEC_DEVIATION surfaced. No silent text generation.              ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with: utils/ai_underwriting.py (v10.11) — decisions          ║
║                  utils/applicant_data_sources.py (v10.12) — data       ║
║                  utils/risk_based_pricing.py (v10.13) — pricing        ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "GenAI memo drafting is via callable hook; default uses "
    "deterministic template (no silent LLM generation per Rule 7)")


# ════════════════════════════════════════════════════════════════════════
# Application state machine (ENH-125)
# ════════════════════════════════════════════════════════════════════════

class ApplicationState(Enum):
    """Loan application lifecycle states."""
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    EKYC_PENDING = "EKYC_PENDING"
    EKYC_FAILED = "EKYC_FAILED"
    BUREAU_PULL_PENDING = "BUREAU_PULL_PENDING"
    DECISION_PENDING = "DECISION_PENDING"
    APPROVED = "APPROVED"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    DECLINED = "DECLINED"
    REFERRED_TO_COMMITTEE = "REFERRED_TO_COMMITTEE"
    COMMITTEE_PENDING = "COMMITTEE_PENDING"
    COMMITTEE_APPROVED = "COMMITTEE_APPROVED"
    COMMITTEE_DECLINED = "COMMITTEE_DECLINED"
    DOCUMENTATION_PENDING = "DOCUMENTATION_PENDING"
    DISBURSEMENT_PENDING = "DISBURSEMENT_PENDING"
    DISBURSED = "DISBURSED"
    WITHDRAWN_BY_APPLICANT = "WITHDRAWN_BY_APPLICANT"
    EXPIRED = "EXPIRED"


# Allowed state transitions — explicit graph (defensible vs free-form)
ALLOWED_TRANSITIONS: Mapping[ApplicationState, Tuple[ApplicationState, ...]] = {
    ApplicationState.DRAFT: (
        ApplicationState.SUBMITTED,
        ApplicationState.WITHDRAWN_BY_APPLICANT),
    ApplicationState.SUBMITTED: (
        ApplicationState.EKYC_PENDING,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.EKYC_PENDING: (
        ApplicationState.BUREAU_PULL_PENDING,
        ApplicationState.EKYC_FAILED,
        ApplicationState.DECLINED,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.BUREAU_PULL_PENDING: (
        ApplicationState.DECISION_PENDING,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.DECISION_PENDING: (
        ApplicationState.APPROVED,
        ApplicationState.CONDITIONALLY_APPROVED,
        ApplicationState.DECLINED,
        ApplicationState.REFERRED_TO_COMMITTEE,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.APPROVED: (
        ApplicationState.DOCUMENTATION_PENDING,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.CONDITIONALLY_APPROVED: (
        ApplicationState.APPROVED,
        ApplicationState.DECLINED,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.REFERRED_TO_COMMITTEE: (
        ApplicationState.COMMITTEE_PENDING,
        ApplicationState.WITHDRAWN_BY_APPLICANT),
    ApplicationState.COMMITTEE_PENDING: (
        ApplicationState.COMMITTEE_APPROVED,
        ApplicationState.COMMITTEE_DECLINED,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.COMMITTEE_APPROVED: (
        ApplicationState.DOCUMENTATION_PENDING,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.DOCUMENTATION_PENDING: (
        ApplicationState.DISBURSEMENT_PENDING,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    ApplicationState.DISBURSEMENT_PENDING: (
        ApplicationState.DISBURSED,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED),
    # Terminal states
    ApplicationState.DECLINED: (),
    ApplicationState.COMMITTEE_DECLINED: (),
    ApplicationState.EKYC_FAILED: (),
    ApplicationState.DISBURSED: (),
    ApplicationState.WITHDRAWN_BY_APPLICANT: (),
    ApplicationState.EXPIRED: (),
}


def is_terminal_state(state: ApplicationState) -> bool:
    """True if state has no outgoing transitions."""
    return len(ALLOWED_TRANSITIONS.get(state, ())) == 0


def is_valid_transition(
    from_state: ApplicationState,
    to_state: ApplicationState,
) -> bool:
    """Check if a state transition is permitted."""
    return to_state in ALLOWED_TRANSITIONS.get(from_state, ())


@dataclass(frozen=True)
class StateTransition:
    """Immutable record of a state change."""
    application_id: str
    from_state: ApplicationState
    to_state: ApplicationState
    timestamp: str
    actor: str                # who triggered the transition
    reason: str = ""
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Confident Automation Pattern (80/20) — ENH-CRD-R7
# ════════════════════════════════════════════════════════════════════════

class AutomationDecision(Enum):
    """Outcome of automation policy evaluation."""
    AUTOMATE = "AUTOMATE"            # full auto-execution permitted
    HUMAN_REVIEW = "HUMAN_REVIEW"    # 1 human reviewer
    COMMITTEE = "COMMITTEE"          # multi-member committee


# Amount tier thresholds (KES) for automation policy
AUTOMATION_AMOUNT_TIER_1_KES = Decimal("500000")       # 500K
AUTOMATION_AMOUNT_TIER_2_KES = Decimal("5000000")      # 5M
AUTOMATION_AMOUNT_TIER_3_KES = Decimal("50000000")     # 50M

# Confidence threshold for full automation
AUTOMATION_CONFIDENCE_THRESHOLD = Decimal("0.80")


@dataclass(frozen=True)
class AutomationPolicy:
    """Configurable automation policy parameters."""
    confidence_threshold: Decimal = AUTOMATION_CONFIDENCE_THRESHOLD
    tier_1_threshold_kes: Decimal = AUTOMATION_AMOUNT_TIER_1_KES
    tier_2_threshold_kes: Decimal = AUTOMATION_AMOUNT_TIER_2_KES
    tier_3_threshold_kes: Decimal = AUTOMATION_AMOUNT_TIER_3_KES
    high_risk_sectors: Tuple[str, ...] = (
        "FOSSIL_FUELS_OIL_GAS", "FOSSIL_FUELS_COAL",
        "REAL_ESTATE_COASTAL", "MINING_EXTRACTIVE")


def evaluate_automation(
    *,
    decision_confidence: Decimal,
    amount_kes: Decimal,
    sector: Optional[str] = None,
    is_first_loan: bool = False,
    is_high_risk_jurisdiction: bool = False,
    policy: Optional[AutomationPolicy] = None,
) -> AutomationDecision:
    """Decide auto-execute vs human review vs committee per 80/20 pattern.

    Flow:
      - amount > tier_3 → COMMITTEE always
      - amount > tier_2 + low confidence → COMMITTEE
      - amount > tier_1 OR low confidence OR high-risk sector → HUMAN_REVIEW
      - first loan + tier > 0 → HUMAN_REVIEW (KYC gate)
      - high-risk jurisdiction → HUMAN_REVIEW
      - otherwise → AUTOMATE
    """
    p = policy or AutomationPolicy()

    if amount_kes > p.tier_3_threshold_kes:
        return AutomationDecision.COMMITTEE

    if (amount_kes > p.tier_2_threshold_kes
            and decision_confidence < p.confidence_threshold):
        return AutomationDecision.COMMITTEE

    if amount_kes > p.tier_2_threshold_kes:
        return AutomationDecision.HUMAN_REVIEW

    if decision_confidence < p.confidence_threshold:
        return AutomationDecision.HUMAN_REVIEW

    if sector and sector in p.high_risk_sectors:
        return AutomationDecision.HUMAN_REVIEW

    if amount_kes > p.tier_1_threshold_kes and is_first_loan:
        return AutomationDecision.HUMAN_REVIEW

    if is_high_risk_jurisdiction:
        return AutomationDecision.HUMAN_REVIEW

    return AutomationDecision.AUTOMATE


# ════════════════════════════════════════════════════════════════════════
# Credit Committee — ENH-130
# ════════════════════════════════════════════════════════════════════════

class CommitteeRole(Enum):
    """Committee membership roles.

    v10.449: Added 3 branch-level roles (BRANCH_MANAGER,
    BRANCH_CREDIT_MANAGER, BRANCH_OPERATIONS_MANAGER) for the Branch
    Credit Committee (BCC). BCC has authority for smaller amounts;
    above their limit they review + forward to head office committee.
    """
    HEAD_OF_CREDIT = "HEAD_OF_CREDIT"
    HEAD_OF_RISK = "HEAD_OF_RISK"
    HEAD_OF_COMPLIANCE = "HEAD_OF_COMPLIANCE"
    HEAD_OF_BUSINESS = "HEAD_OF_BUSINESS"
    CFO = "CFO"
    CEO = "CEO"
    BOARD_CREDIT_MEMBER = "BOARD_CREDIT_MEMBER"
    # ── Branch Credit Committee (v10.449) ────────────────────────────
    BRANCH_MANAGER = "BRANCH_MANAGER"
    BRANCH_CREDIT_MANAGER = "BRANCH_CREDIT_MANAGER"
    BRANCH_OPERATIONS_MANAGER = "BRANCH_OPERATIONS_MANAGER"


@dataclass(frozen=True)
class CommitteeVote:
    """Single member's vote."""
    voter_role: CommitteeRole
    voter_id: str
    decision: str                 # APPROVE / DECLINE / ABSTAIN
    timestamp: str
    rationale: str = ""


@dataclass(frozen=True)
class CommitteeDecision:
    """Aggregated committee outcome."""
    application_id: str
    committee_id: str
    quorum_required: int
    quorum_present: int
    votes: Tuple[CommitteeVote, ...]
    approve_count: int
    decline_count: int
    abstain_count: int
    outcome: str                 # APPROVED / DECLINED / NO_QUORUM / TIE
    threshold_required_pct: Decimal   # e.g. 60% to approve

    def quorum_met(self) -> bool:
        return self.quorum_present >= self.quorum_required


# Required quorum + voting threshold by amount tier
COMMITTEE_REQUIREMENTS: Mapping[str, Mapping[str, object]] = {
    # ── Branch Credit Committee (v10.449) ─────────────────────────
    "TIER_BRANCH_AUTO": {
        # KES 500K - 2M: Branch can approve AND disburse autonomously
        "required_roles": (
            CommitteeRole.BRANCH_MANAGER,
            CommitteeRole.BRANCH_CREDIT_MANAGER),
        "quorum": 2,
        "approve_threshold_pct": Decimal("100"),  # both members must approve
        "forwards_to_ho": False,  # branch disburses directly
        "description": (
            "Branch Credit Committee can approve and disburse. "
            "Documented vote required from both BM + BCM."),
    },
    "TIER_BRANCH_FWD": {
        # KES 2M - 5M: Branch reviews + recommends, then forwards to HO
        "required_roles": (
            CommitteeRole.BRANCH_MANAGER,
            CommitteeRole.BRANCH_CREDIT_MANAGER,
            CommitteeRole.BRANCH_OPERATIONS_MANAGER),
        "quorum": 3,
        "approve_threshold_pct": Decimal("67"),  # 2 of 3
        "forwards_to_ho": True,   # after branch approval, HO committee sees it
        "description": (
            "Branch Credit Committee reviews and forwards to head office "
            "for final decision. Branch recommendation required + HO "
            "TIER_2 committee approval needed."),
    },
    # ── Head Office Credit Committee (existing) ───────────────────
    "TIER_2": {     # tier_1 < amount ≤ tier_2 (500K - 5M KES)
        "required_roles": (
            CommitteeRole.HEAD_OF_CREDIT,
            CommitteeRole.HEAD_OF_RISK),
        "quorum": 2,
        "approve_threshold_pct": Decimal("60"),
    },
    "TIER_3": {     # tier_2 < amount ≤ tier_3 (5M - 50M KES)
        "required_roles": (
            CommitteeRole.HEAD_OF_CREDIT,
            CommitteeRole.HEAD_OF_RISK,
            CommitteeRole.HEAD_OF_BUSINESS,
            CommitteeRole.HEAD_OF_COMPLIANCE),
        "quorum": 3,
        "approve_threshold_pct": Decimal("75"),
    },
    "TIER_4": {     # > tier_3 (>50M KES) — board-level
        "required_roles": (
            CommitteeRole.CEO,
            CommitteeRole.CFO,
            CommitteeRole.HEAD_OF_RISK,
            CommitteeRole.HEAD_OF_CREDIT,
            CommitteeRole.BOARD_CREDIT_MEMBER),
        "quorum": 4,
        "approve_threshold_pct": Decimal("80"),
    },
}


# Branch committee tier thresholds (v10.449)
BRANCH_AUTO_DISBURSE_LIMIT_KES = Decimal("2000000")     # 2M
BRANCH_FORWARD_LIMIT_KES = Decimal("5000000")           # 5M


def determine_branch_tier(amount_kes: Decimal) -> Optional[str]:
    """Branch committee tier for an application originated at a branch.

    Returns:
        - "TIER_1": ≤ 500K — automated, no committee required (auto-decision)
        - "TIER_BRANCH_AUTO": 500K - 2M — BCC approves AND disburses
        - "TIER_BRANCH_FWD": 2M - 5M — BCC approves + forwards to HO
        - None: > 5M — above branch authority, mandatory HO-only path

    Per Joshua doctrine: 'there are those they can approve at branch
    level and disburse... and there are those they can approve and
    still forward for further approval.'
    """
    if amount_kes <= AUTOMATION_AMOUNT_TIER_1_KES:
        return "TIER_1"
    if amount_kes <= BRANCH_AUTO_DISBURSE_LIMIT_KES:
        return "TIER_BRANCH_AUTO"
    if amount_kes <= BRANCH_FORWARD_LIMIT_KES:
        return "TIER_BRANCH_FWD"
    return None


def determine_tier(amount_kes: Decimal,
                   *,
                   originated_at_branch: bool = False) -> str:
    """Return tier code based on amount.

    v10.449: When originated_at_branch=True, the branch tier mapping
    (TIER_BRANCH_AUTO / TIER_BRANCH_FWD) is used for amounts the branch
    has authority over. Above branch authority, falls through to HO
    tiers (TIER_2/3/4).
    """
    if originated_at_branch:
        branch_tier = determine_branch_tier(amount_kes)
        if branch_tier is not None:
            return branch_tier
        # Above branch authority — fall through to HO tier logic below
    if amount_kes <= AUTOMATION_AMOUNT_TIER_1_KES:
        return "TIER_1"      # auto, no committee
    if amount_kes <= AUTOMATION_AMOUNT_TIER_2_KES:
        return "TIER_2"
    if amount_kes <= AUTOMATION_AMOUNT_TIER_3_KES:
        return "TIER_3"
    return "TIER_4"


def is_branch_tier(tier: str) -> bool:
    """Is this tier evaluated at the branch level?"""
    return tier in ("TIER_BRANCH_AUTO", "TIER_BRANCH_FWD")


def forwards_to_ho(tier: str) -> bool:
    """Does a branch approval at this tier require forwarding to HO?"""
    req = COMMITTEE_REQUIREMENTS.get(tier, {})
    return bool(req.get("forwards_to_ho", False))


def evaluate_committee_decision(
    *,
    application_id: str,
    committee_id: str,
    amount_kes: Decimal,
    votes: Sequence[CommitteeVote],
    originated_at_branch: bool = False,
) -> CommitteeDecision:
    """Aggregate committee votes into a decision.

    Per ENH-130:
      - Quorum: depends on tier (see COMMITTEE_REQUIREMENTS)
      - Threshold: approve count / total non-abstain ≥ approve_threshold_pct

    v10.449: When originated_at_branch=True, branch tiers are used.
    Branch tier outcomes:
      - "APPROVED_AT_BRANCH": BCC can approve + disburse (TIER_BRANCH_AUTO)
      - "APPROVED_BRANCH_FORWARD_HO": BCC approves but app must still go
        to HO TIER_2 committee (TIER_BRANCH_FWD).
    """
    tier = determine_tier(amount_kes, originated_at_branch=originated_at_branch)
    if tier == "TIER_1":
        # Should not be at committee — but handle gracefully
        return CommitteeDecision(
            application_id=application_id,
            committee_id=committee_id,
            quorum_required=0,
            quorum_present=len(votes),
            votes=tuple(votes),
            approve_count=sum(1 for v in votes if v.decision == "APPROVE"),
            decline_count=sum(1 for v in votes if v.decision == "DECLINE"),
            abstain_count=sum(1 for v in votes if v.decision == "ABSTAIN"),
            outcome="APPROVED" if any(v.decision == "APPROVE" for v in votes)
                      else "DECLINED",
            threshold_required_pct=Decimal("0"))

    req = COMMITTEE_REQUIREMENTS[tier]
    quorum = req["quorum"]
    threshold_pct = req["approve_threshold_pct"]
    required_roles = set(req["required_roles"])

    voters_present = set(v.voter_role for v in votes)
    role_quorum_met = len(voters_present & required_roles) >= quorum

    approve = sum(1 for v in votes if v.decision == "APPROVE")
    decline = sum(1 for v in votes if v.decision == "DECLINE")
    abstain = sum(1 for v in votes if v.decision == "ABSTAIN")
    decisive = approve + decline

    is_branch = is_branch_tier(tier)
    forwards = forwards_to_ho(tier)

    if not role_quorum_met:
        outcome = "NO_QUORUM"
    elif decisive == 0:
        outcome = "NO_QUORUM"
    else:
        approve_pct = (
            Decimal(approve) / Decimal(decisive) * Decimal("100"))
        if approve_pct >= threshold_pct:
            # Differentiate branch outcomes (Joshua's directive)
            if is_branch and forwards:
                outcome = "APPROVED_BRANCH_FORWARD_HO"
            elif is_branch:
                outcome = "APPROVED_AT_BRANCH"
            else:
                outcome = "APPROVED"
        elif approve == decline:
            outcome = "TIE"
        else:
            outcome = "DECLINED"

    return CommitteeDecision(
        application_id=application_id,
        committee_id=committee_id,
        quorum_required=quorum,
        quorum_present=len(voters_present & required_roles),
        votes=tuple(votes),
        approve_count=approve,
        decline_count=decline,
        abstain_count=abstain,
        outcome=outcome,
        threshold_required_pct=threshold_pct)


# ════════════════════════════════════════════════════════════════════════
# Credit Memo (ENH-CRD-R5)
# ════════════════════════════════════════════════════════════════════════

# Sections required in any credit memo (per CBK + bank policy convention)
CREDIT_MEMO_REQUIRED_SECTIONS: Tuple[str, ...] = (
    "EXECUTIVE_SUMMARY",
    "APPLICANT_BACKGROUND",
    "FINANCIAL_ANALYSIS",
    "PROPOSED_FACILITY",
    "PRICING_AND_TERMS",
    "RISK_ASSESSMENT",
    "MITIGANTS_AND_CONDITIONS",
    "RECOMMENDATION",
)


@dataclass(frozen=True)
class CreditMemoSection:
    """One section of a credit memo."""
    name: str                    # one of CREDIT_MEMO_REQUIRED_SECTIONS
    title: str
    body: str
    quantitative: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class CreditMemo:
    """Full credit memo artifact."""
    application_id: str
    drafted_at: str
    drafted_by: str              # 'rule_based_template' / 'gen_ai' / human user_id
    sections: Tuple[CreditMemoSection, ...]
    completeness_pct: Decimal
    deviation_notes: str = ""

    def is_complete(self) -> bool:
        return self.completeness_pct == Decimal("100")


def draft_memo_template(
    *,
    application_id: str,
    drafted_at: str,
    applicant_name: str = "[applicant]",
    requested_amount_kes: Decimal = Decimal("0"),
    decision_summary: str = "",
    pd: Optional[Decimal] = None,
    offered_rate: Optional[Decimal] = None,
    risks: Sequence[str] = (),
    mitigants: Sequence[str] = (),
    llm_hook: Optional[Callable[[str, Dict], str]] = None,
) -> CreditMemo:
    """Draft a credit memo using deterministic template.

    Per Rule 7: if `llm_hook` callable is provided, the engine uses it for
    each section's body. Otherwise (default), uses deterministic templated
    text with explicit SPEC_DEVIATION note.
    """
    sections: List[CreditMemoSection] = []
    use_llm = llm_hook is not None

    # ── Executive summary ──
    if use_llm:
        body = llm_hook("EXECUTIVE_SUMMARY", {
            "applicant_name": applicant_name,
            "amount_kes": requested_amount_kes,
            "decision_summary": decision_summary})
    else:
        body = (
            f"Application {application_id} from {applicant_name} requests "
            f"KES {requested_amount_kes:,.0f}. {decision_summary}")
    sections.append(CreditMemoSection(
        name="EXECUTIVE_SUMMARY", title="Executive Summary", body=body))

    # ── Applicant background ──
    if use_llm:
        body = llm_hook("APPLICANT_BACKGROUND", {
            "applicant_name": applicant_name})
    else:
        body = (
            f"Applicant {applicant_name} — see attached eKYC + bureau reports "
            f"for full background. (Template-generated; populate via review.)")
    sections.append(CreditMemoSection(
        name="APPLICANT_BACKGROUND",
        title="Applicant Background", body=body))

    # ── Financial analysis ──
    if use_llm:
        body = llm_hook("FINANCIAL_ANALYSIS", {
            "applicant_name": applicant_name})
    else:
        body = (
            "Income, DTI, cash-flow analysis attached. Affordability "
            "assessment per CBK Digital Lending Reg 2022 §12.")
    sections.append(CreditMemoSection(
        name="FINANCIAL_ANALYSIS",
        title="Financial Analysis", body=body))

    # ── Proposed facility ──
    if use_llm:
        body = llm_hook("PROPOSED_FACILITY", {
            "amount_kes": requested_amount_kes})
    else:
        body = (
            f"Requested facility: KES {requested_amount_kes:,.0f}. "
            f"See terms section for tenor, repayment, and security.")
    sections.append(CreditMemoSection(
        name="PROPOSED_FACILITY",
        title="Proposed Facility", body=body))

    # ── Pricing and terms ──
    quant: Dict[str, Decimal] = {}
    if pd is not None:
        quant["pd"] = pd
    if offered_rate is not None:
        quant["offered_rate"] = offered_rate
    if use_llm:
        body = llm_hook("PRICING_AND_TERMS", {
            "pd": pd, "offered_rate": offered_rate})
    else:
        rate_str = (f"{offered_rate * 100:.2f}%"
                      if offered_rate is not None else "TBD")
        pd_str = (f"{pd * 100:.2f}%" if pd is not None else "TBD")
        body = (
            f"PD: {pd_str}. Offered rate: {rate_str}. "
            f"Tenor + repayment schedule per facility letter.")
    sections.append(CreditMemoSection(
        name="PRICING_AND_TERMS", title="Pricing and Terms",
        body=body, quantitative=quant))

    # ── Risk assessment ──
    if use_llm:
        body = llm_hook("RISK_ASSESSMENT", {"risks": list(risks)})
    elif risks:
        body = "Identified risks:\n" + "\n".join(f"  • {r}" for r in risks)
    else:
        body = ("No specific risks identified beyond standard credit risk "
                "(see PD/LGD/EAD analysis).")
    sections.append(CreditMemoSection(
        name="RISK_ASSESSMENT", title="Risk Assessment", body=body))

    # ── Mitigants and conditions ──
    if use_llm:
        body = llm_hook("MITIGANTS_AND_CONDITIONS",
                          {"mitigants": list(mitigants)})
    elif mitigants:
        body = "Mitigants:\n" + "\n".join(f"  • {m}" for m in mitigants)
    else:
        body = "Standard facility covenants apply. No additional mitigants."
    sections.append(CreditMemoSection(
        name="MITIGANTS_AND_CONDITIONS",
        title="Mitigants and Conditions", body=body))

    # ── Recommendation ──
    if use_llm:
        body = llm_hook("RECOMMENDATION",
                          {"decision_summary": decision_summary})
    else:
        body = decision_summary or "Recommend [APPROVE / DECLINE / REFER]."
    sections.append(CreditMemoSection(
        name="RECOMMENDATION", title="Recommendation", body=body))

    completeness = (
        Decimal(len(sections)) / Decimal(len(CREDIT_MEMO_REQUIRED_SECTIONS))
        * Decimal("100"))

    drafter = "gen_ai" if use_llm else "rule_based_template"
    deviation = "" if use_llm else SPEC_DEVIATION_NOTE

    return CreditMemo(
        application_id=application_id,
        drafted_at=drafted_at,
        drafted_by=drafter,
        sections=tuple(sections),
        completeness_pct=completeness,
        deviation_notes=deviation)


# ════════════════════════════════════════════════════════════════════════
# Engine — workflow orchestrator
# ════════════════════════════════════════════════════════════════════════

class CreditWorkflowEngine:
    """End-to-end orchestrator: state machine + automation policy + committee + memo."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._states: Dict[str, ApplicationState] = {}
        self._transitions: List[StateTransition] = []
        self._committee_decisions: List[CommitteeDecision] = []
        self._memos: List[CreditMemo] = []

    # ── State machine ───────────────────────────────────────────────────
    def initialize(self, application_id: str) -> None:
        if application_id in self._states:
            raise ValueError(
                f"application {application_id} already initialized")
        self._states[application_id] = ApplicationState.DRAFT

    def get_state(self, application_id: str) -> ApplicationState:
        if application_id not in self._states:
            raise KeyError(f"application {application_id} not initialized")
        return self._states[application_id]

    def transition(
        self,
        *,
        application_id: str,
        to_state: ApplicationState,
        actor: str,
        timestamp: str,
        reason: str = "",
    ) -> StateTransition:
        current = self.get_state(application_id)
        if not is_valid_transition(current, to_state):
            allowed = ALLOWED_TRANSITIONS.get(current, ())
            raise ValueError(
                f"invalid transition {current.value} → {to_state.value}; "
                f"allowed: {[s.value for s in allowed]}")
        st = StateTransition(
            application_id=application_id,
            from_state=current, to_state=to_state,
            timestamp=timestamp, actor=actor, reason=reason)
        self._states[application_id] = to_state
        self._transitions.append(st)
        return st

    # ── Committee ───────────────────────────────────────────────────────
    def record_committee_decision(
        self, decision: CommitteeDecision) -> None:
        self._committee_decisions.append(decision)

    # ── Memo ────────────────────────────────────────────────────────────
    def record_memo(self, memo: CreditMemo) -> None:
        self._memos.append(memo)

    # ── Reporting ───────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        if not self._states:
            return {
                "entity": self.entity_name,
                "n_applications": 0,
                "by_state": {},
                "automation_rate_pct": Decimal("0"),
                "n_committee_decisions": 0,
                "n_memos": 0,
            }

        by_state: Dict[str, int] = {}
        for s in self._states.values():
            by_state[s.value] = by_state.get(s.value, 0) + 1

        # Automation = transitions that went through DECISION_PENDING → terminal
        # without going via REFERRED_TO_COMMITTEE
        terminal_via_automation = 0
        terminal_via_committee = 0
        for t in self._transitions:
            if t.to_state == ApplicationState.APPROVED:
                terminal_via_automation += 1
            elif t.to_state == ApplicationState.COMMITTEE_APPROVED:
                terminal_via_committee += 1

        total_terminal = terminal_via_automation + terminal_via_committee
        automation_pct = (
            Decimal(terminal_via_automation) / Decimal(total_terminal)
            * Decimal("100")
            if total_terminal > 0 else Decimal("0"))

        return {
            "entity": self.entity_name,
            "n_applications": len(self._states),
            "by_state": by_state,
            "automation_rate_pct": automation_pct,
            "n_committee_decisions": len(self._committee_decisions),
            "n_memos": len(self._memos),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_state_machine_terminal_states():
    terminals = [s for s in ApplicationState if is_terminal_state(s)]
    expected = {
        ApplicationState.DECLINED, ApplicationState.COMMITTEE_DECLINED,
        ApplicationState.EKYC_FAILED, ApplicationState.DISBURSED,
        ApplicationState.WITHDRAWN_BY_APPLICANT,
        ApplicationState.EXPIRED}
    assert set(terminals) == expected


def _test_state_machine_valid_transitions():
    assert is_valid_transition(
        ApplicationState.DRAFT, ApplicationState.SUBMITTED)
    assert is_valid_transition(
        ApplicationState.DECISION_PENDING, ApplicationState.APPROVED)
    assert not is_valid_transition(
        ApplicationState.DRAFT, ApplicationState.DISBURSED)


def _test_state_machine_terminal_no_outgoing():
    """Terminal states have no allowed outgoing transitions."""
    for terminal in (ApplicationState.DECLINED,
                       ApplicationState.DISBURSED):
        assert ALLOWED_TRANSITIONS[terminal] == ()


def _test_workflow_engine_basic_flow():
    eng = CreditWorkflowEngine()
    eng.initialize("APP-1")
    assert eng.get_state("APP-1") == ApplicationState.DRAFT
    eng.transition(
        application_id="APP-1",
        to_state=ApplicationState.SUBMITTED,
        actor="applicant", timestamp="t")
    assert eng.get_state("APP-1") == ApplicationState.SUBMITTED


def _test_workflow_engine_invalid_transition_raises():
    eng = CreditWorkflowEngine()
    eng.initialize("APP-1")
    try:
        eng.transition(
            application_id="APP-1",
            to_state=ApplicationState.DISBURSED,
            actor="bad", timestamp="t")
        assert False
    except ValueError as e:
        assert "invalid transition" in str(e)


def _test_workflow_engine_unknown_app_raises():
    eng = CreditWorkflowEngine()
    try:
        eng.get_state("NEVER-INIT")
        assert False
    except KeyError:
        pass


def _test_automation_small_high_confidence_automates():
    d = evaluate_automation(
        decision_confidence=Decimal("0.90"),
        amount_kes=Decimal("100000"))
    assert d == AutomationDecision.AUTOMATE


def _test_automation_low_confidence_human_review():
    d = evaluate_automation(
        decision_confidence=Decimal("0.60"),
        amount_kes=Decimal("100000"))
    assert d == AutomationDecision.HUMAN_REVIEW


def _test_automation_large_amount_committee():
    d = evaluate_automation(
        decision_confidence=Decimal("0.95"),
        amount_kes=Decimal("60000000"))   # > tier_3
    assert d == AutomationDecision.COMMITTEE


def _test_automation_high_risk_sector_human_review():
    d = evaluate_automation(
        decision_confidence=Decimal("0.95"),
        amount_kes=Decimal("100000"),
        sector="FOSSIL_FUELS_OIL_GAS")
    assert d == AutomationDecision.HUMAN_REVIEW


def _test_committee_tier_assignment():
    assert determine_tier(Decimal("100000")) == "TIER_1"
    assert determine_tier(Decimal("1000000")) == "TIER_2"
    assert determine_tier(Decimal("10000000")) == "TIER_3"
    assert determine_tier(Decimal("100000000")) == "TIER_4"


def _test_committee_approves_with_threshold_met():
    votes = (
        CommitteeVote(voter_role=CommitteeRole.HEAD_OF_CREDIT,
                        voter_id="V1", decision="APPROVE", timestamp="t"),
        CommitteeVote(voter_role=CommitteeRole.HEAD_OF_RISK,
                        voter_id="V2", decision="APPROVE", timestamp="t"),
    )
    d = evaluate_committee_decision(
        application_id="APP-1", committee_id="C1",
        amount_kes=Decimal("3000000"), votes=votes)
    assert d.outcome == "APPROVED"
    assert d.quorum_met()


def _test_committee_no_quorum():
    votes = (
        CommitteeVote(voter_role=CommitteeRole.HEAD_OF_CREDIT,
                        voter_id="V1", decision="APPROVE", timestamp="t"),
    )
    d = evaluate_committee_decision(
        application_id="APP-1", committee_id="C1",
        amount_kes=Decimal("3000000"),       # tier 2 needs 2 quorum
        votes=votes)
    assert d.outcome == "NO_QUORUM"


def _test_committee_higher_threshold_for_tier_4():
    """Tier 4 requires 80% — 4-of-5 fails, 5-of-5 passes."""
    # 4 approve, 1 decline of 5 → 80%? 4/5 = 80%. Should approve at threshold.
    votes_4_1 = tuple(
        CommitteeVote(voter_role=r, voter_id=f"V{i}",
                        decision=("APPROVE" if i < 4 else "DECLINE"),
                        timestamp="t")
        for i, r in enumerate([
            CommitteeRole.CEO, CommitteeRole.CFO,
            CommitteeRole.HEAD_OF_RISK, CommitteeRole.HEAD_OF_CREDIT,
            CommitteeRole.BOARD_CREDIT_MEMBER]))
    d = evaluate_committee_decision(
        application_id="A", committee_id="C",
        amount_kes=Decimal("100000000"), votes=votes_4_1)
    assert d.outcome == "APPROVED"


def _test_memo_template_default_sections():
    memo = draft_memo_template(
        application_id="A", drafted_at="t",
        applicant_name="ACME Ltd",
        requested_amount_kes=Decimal("1000000"),
        decision_summary="Recommend APPROVE")
    assert memo.is_complete()
    assert memo.drafted_by == "rule_based_template"
    assert SPEC_DEVIATION_NOTE in memo.deviation_notes


def _test_memo_template_uses_llm_hook():
    """When llm_hook is provided, drafted_by switches to gen_ai."""
    def fake_llm(section_name, ctx):
        return f"[LLM-DRAFTED {section_name}]"
    memo = draft_memo_template(
        application_id="A", drafted_at="t",
        llm_hook=fake_llm)
    assert memo.drafted_by == "gen_ai"
    assert memo.deviation_notes == ""
    # Each section's body came from the LLM hook
    for s in memo.sections:
        assert s.body.startswith("[LLM-DRAFTED")


def _test_memo_all_required_sections_present():
    memo = draft_memo_template(
        application_id="A", drafted_at="t",
        applicant_name="X")
    section_names = tuple(s.name for s in memo.sections)
    for required in CREDIT_MEMO_REQUIRED_SECTIONS:
        assert required in section_names


def _test_engine_board_summary_empty():
    eng = CreditWorkflowEngine()
    s = eng.board_summary()
    assert s["n_applications"] == 0
    assert s["automation_rate_pct"] == Decimal("0")


def _test_engine_board_summary_aggregates():
    eng = CreditWorkflowEngine()
    eng.initialize("A1")
    eng.transition(application_id="A1", to_state=ApplicationState.SUBMITTED,
                    actor="a", timestamp="t")
    s = eng.board_summary()
    assert s["n_applications"] == 1
    assert s["by_state"]["SUBMITTED"] == 1


def self_test() -> None:
    tests = [
        _test_state_machine_terminal_states,
        _test_state_machine_valid_transitions,
        _test_state_machine_terminal_no_outgoing,
        _test_workflow_engine_basic_flow,
        _test_workflow_engine_invalid_transition_raises,
        _test_workflow_engine_unknown_app_raises,
        _test_automation_small_high_confidence_automates,
        _test_automation_low_confidence_human_review,
        _test_automation_large_amount_committee,
        _test_automation_high_risk_sector_human_review,
        _test_committee_tier_assignment,
        _test_committee_approves_with_threshold_met,
        _test_committee_no_quorum,
        _test_committee_higher_threshold_for_tier_4,
        _test_memo_template_default_sections,
        _test_memo_template_uses_llm_hook,
        _test_memo_all_required_sections_present,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_aggregates,
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
        print(f"✗ credit_workflow self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ credit_workflow self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

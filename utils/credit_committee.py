"""utils/credit_committee.py — v10.48: Credit Committee Governance.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-268 — Credit Committee Governance                                  ║
║  Cat A — credit_model_risk arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Diagnostic governance engine for credit committee decisions per        ║
║  CBK PG/03 §6 + sound-credit-governance practice. Validates that:       ║
║                                                                          ║
║    1. QUORUM is met — both headcount minimum AND required-role          ║
║       presence (CRO or CCO must attend per CBK PG/03 §6.4).             ║
║    2. AUTHORITY LIMIT respected — facilities above the committee's      ║
║       sanctioned limit must be ESCALATED, not decided in-room.          ║
║    3. VOTING RULE applied correctly — simple majority / two-thirds /    ║
║       unanimous / chair-tiebreaker per the committee charter.           ║
║    4. POLICY OVERRIDES captured with rationale + escalation flag.       ║
║                                                                          ║
║  Per Rule 1, every DecisionResult surfaces:                             ║
║    members_present + quorum_status + quorum_reason + vote_tally         ║
║    + outcome + rationale + conditions + is_policy_override              ║
║    + escalation_required + escalation_target + framework_refs           ║
║                                                                          ║
║  Per Rule 7, engine is computational only — never auto-approves a       ║
║  facility, never auto-disburses funds, never modifies the committee     ║
║  charter at runtime. Outputs feed minute-recording + downstream         ║
║  workflow (disbursement, monitoring, audit trail).                      ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - credit_alt_scoring (ENH-260 thin-file PD output flows into the     ║
║      committee packet; engine itself does not pull — caller assembles)  ║
║    - credit_risk_irb (ENH-CR-001 — capital impact of approved deals     ║
║      computed downstream)                                               ║
║    - audit_grc (decision rationale capture for audit trail)             ║
║    - core_audit (audit_log() called by callers, not by engine itself)   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple

SPEC_DEVIATION_NOTE = (
    "CreditCommitteeEngine implements ENH-268 governance engine. "
    "Pure stdlib via Decimal + frozen dataclasses. Per Rule 1, "
    "every DecisionResult surfaces all inputs (members present + "
    "votes + request) + intermediates (quorum status + tally) + "
    "outputs (outcome + escalation + override flags) + framework "
    "refs. Per Rule 7, engine is diagnostic only — never auto-"
    "approves, never auto-disburses, never modifies charter at "
    "runtime. Decimal-internal for monetary thresholds. Voting "
    "ties under SIMPLE_MAJORITY are REJECTED (defensive default); "
    "CHAIR_TIEBREAKER rule must be explicitly chosen if chair "
    "should break ties."
)

# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class CommitteeRole(Enum):
    """Standard credit committee roles per CBK PG/03 §6."""
    CHAIR = "CHAIR"
    CRO = "CRO"                          # Chief Risk Officer
    CCO = "CCO"                          # Chief Credit Officer
    CFO = "CFO"
    HEAD_OF_CREDIT = "HEAD_OF_CREDIT"
    INDEPENDENT_MEMBER = "INDEPENDENT_MEMBER"
    EXECUTIVE_MEMBER = "EXECUTIVE_MEMBER"


class VotingRule(Enum):
    """Voting rules supported by the engine."""
    SIMPLE_MAJORITY = "SIMPLE_MAJORITY"            # > 50% of present
    SUPERMAJORITY_TWO_THIRDS = "SUPERMAJORITY_TWO_THIRDS"  # ≥ 66.67%
    UNANIMOUS = "UNANIMOUS"                        # 100% of present
    CHAIR_TIEBREAKER = "CHAIR_TIEBREAKER"          # majority + chair tiebreak
    # Requested for the DEPARTMENT committee (2026-09-04): "the option of
    # having at least one approving". One YES carries it - but a NO is still
    # recorded, and the reason names the dissent, so a single approval never
    # quietly erases an objection.
    #
    # This is a real reduction in control and belongs on a screening committee
    # that is one step in a longer chain - not on the body that grants final
    # authority.
    SINGLE_APPROVER = "SINGLE_APPROVER"            # one YES is enough


class VoteValue(Enum):
    """Possible votes recorded against a decision."""
    YES = "YES"
    NO = "NO"
    ABSTAIN = "ABSTAIN"
    RECUSED = "RECUSED"   # conflict of interest — counts toward neither


class QuorumStatus(Enum):
    """Quorum check outcomes."""
    MET = "MET"
    NOT_MET_HEADCOUNT = "NOT_MET_HEADCOUNT"
    NOT_MET_REQUIRED_ROLE = "NOT_MET_REQUIRED_ROLE"
    NOT_MET_INDEPENDENT_MIN = "NOT_MET_INDEPENDENT_MIN"


class DecisionOutcome(Enum):
    """Possible decision outcomes."""
    APPROVED = "APPROVED"
    APPROVED_WITH_CONDITIONS = "APPROVED_WITH_CONDITIONS"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    ESCALATED = "ESCALATED"          # exceeds committee authority
    QUORUM_FAILED = "QUORUM_FAILED"  # cannot decide validly


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CommitteeMember:
    """One member of a credit committee."""
    member_id: str
    name: str
    role: CommitteeRole
    is_independent: bool = False

    def __post_init__(self) -> None:
        if not self.member_id:
            raise ValueError("member_id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")


@dataclass(frozen=True)
class CommitteeCharter:
    """Static committee charter — composition + rules + authority."""
    committee_id: str
    name: str
    members: Tuple[CommitteeMember, ...]
    voting_rule: VotingRule
    min_quorum_count: int
    required_roles: FrozenSet[CommitteeRole]   # roles that MUST be present
    authority_limit_kes: Decimal               # deals above → escalate
    independent_member_min: int = 0            # min independents in quorum
    escalation_target: str = "BOARD_RISK_COMMITTEE"

    def __post_init__(self) -> None:
        if not self.committee_id:
            raise ValueError("committee_id must be non-empty")
        if self.min_quorum_count < 1:
            raise ValueError("min_quorum_count must be ≥ 1")
        if self.min_quorum_count > len(self.members):
            raise ValueError(
                f"min_quorum_count {self.min_quorum_count} exceeds "
                f"member count {len(self.members)}")
        if self.authority_limit_kes < 0:
            raise ValueError("authority_limit_kes must be ≥ 0")
        if self.independent_member_min < 0:
            raise ValueError("independent_member_min must be ≥ 0")
        # Member IDs must be unique
        ids = [m.member_id for m in self.members]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate member_id in charter")


@dataclass(frozen=True)
class Vote:
    """One member's vote on a decision."""
    member_id: str
    vote: VoteValue
    rationale: str = ""


@dataclass(frozen=True)
class CreditDecisionRequest:
    """A facility request brought to the committee."""
    request_id: str
    borrower_id: str
    facility_kes: Decimal
    proposed_rationale: str
    is_policy_override: bool = False
    override_rationale: str = ""
    requested_conditions: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id must be non-empty")
        if self.facility_kes <= 0:
            raise ValueError("facility_kes must be > 0")
        if self.is_policy_override and not self.override_rationale:
            raise ValueError(
                "policy override flagged but override_rationale empty "
                "— rationale is mandatory per CBK PG/03 §6.7")


@dataclass(frozen=True)
class VoteTally:
    """Tally of votes recorded for one decision."""
    yes_count: int
    no_count: int
    abstain_count: int
    recused_count: int
    total_voting: int            # yes + no (excludes abstain + recused)
    total_present: int           # all members in the room


@dataclass(frozen=True)
class DecisionResult:
    """Output of a committee decision evaluation. Per Rule 1, surfaces
    all inputs + intermediates + outputs."""
    request_id: str
    committee_id: str
    members_present_ids: Tuple[str, ...]
    members_present_roles: Tuple[CommitteeRole, ...]
    quorum_status: QuorumStatus
    quorum_reason: str
    vote_tally: VoteTally
    voting_rule: VotingRule
    outcome: DecisionOutcome
    rationale: str
    conditions: Tuple[str, ...]
    is_policy_override: bool
    escalation_required: bool
    escalation_target: Optional[str]
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class CreditCommitteeEngine:
    """Diagnostic credit-committee governance engine.

    Per Rule 7, the engine never:
      - auto-approves a facility
      - auto-disburses funds
      - mutates committee charter, member list, or voting rule
      - publishes decisions to downstream systems

    Caller flow: build CommitteeCharter (typically per-meeting from
    static config), gather attending member IDs, collect Vote objects,
    submit the CreditDecisionRequest. Engine returns a DecisionResult
    that the caller can then minute, audit-log, and route to
    downstream disbursement / escalation workflows.
    """

    def __init__(self, charter: CommitteeCharter) -> None:
        self._charter = charter

    # ── Quorum ────────────────────────────────────────────────────────
    def _check_quorum(
        self, attending_ids: Tuple[str, ...],
    ) -> Tuple[QuorumStatus, str, Tuple[CommitteeMember, ...]]:
        """Validate quorum. Returns (status, reason, attending_members)."""
        member_by_id = {m.member_id: m for m in self._charter.members}
        attending = tuple(
            member_by_id[mid] for mid in attending_ids
            if mid in member_by_id)
        unknown = [mid for mid in attending_ids if mid not in member_by_id]
        if unknown:
            # Unknown attendees aren't part of the committee — log but
            # exclude from quorum count.
            pass

        if len(attending) < self._charter.min_quorum_count:
            return (
                QuorumStatus.NOT_MET_HEADCOUNT,
                (f"Headcount {len(attending)} below minimum "
                 f"{self._charter.min_quorum_count}"),
                attending)

        roles_present = {m.role for m in attending}
        missing_required = (
            self._charter.required_roles - roles_present)
        if missing_required:
            missing_str = ", ".join(
                sorted(r.value for r in missing_required))
            return (
                QuorumStatus.NOT_MET_REQUIRED_ROLE,
                f"Required role(s) absent: {missing_str}",
                attending)

        independents = sum(1 for m in attending if m.is_independent)
        if independents < self._charter.independent_member_min:
            return (
                QuorumStatus.NOT_MET_INDEPENDENT_MIN,
                (f"Only {independents} independent member(s); "
                 f"need ≥ {self._charter.independent_member_min}"),
                attending)

        return (QuorumStatus.MET, "Quorum met", attending)

    # ── Vote tally ────────────────────────────────────────────────────
    def _tally_votes(
        self, votes: Tuple[Vote, ...],
        attending_ids: Tuple[str, ...],
    ) -> VoteTally:
        # Only count votes from members who are actually present.
        attending_set = set(attending_ids)
        yes = no = abstain = recused = 0
        seen: set = set()
        for v in votes:
            if v.member_id not in attending_set:
                continue   # vote from an absent member is invalid
            if v.member_id in seen:
                continue   # duplicate votes from the same member ignored
            seen.add(v.member_id)
            if v.vote == VoteValue.YES:
                yes += 1
            elif v.vote == VoteValue.NO:
                no += 1
            elif v.vote == VoteValue.ABSTAIN:
                abstain += 1
            elif v.vote == VoteValue.RECUSED:
                recused += 1
        return VoteTally(
            yes_count=yes, no_count=no,
            abstain_count=abstain, recused_count=recused,
            total_voting=yes + no,
            total_present=len(attending_set))

    # ── Outcome under voting rule ─────────────────────────────────────
    def _outcome_from_tally(
        self, tally: VoteTally,
        attending_members: Tuple[CommitteeMember, ...],
        votes: Tuple[Vote, ...],
    ) -> Tuple[DecisionOutcome, str]:
        """Apply the charter's voting rule to the tally."""
        rule = self._charter.voting_rule

        if tally.total_voting == 0:
            return (
                DecisionOutcome.DEFERRED,
                "No YES/NO votes cast (all abstained or recused)")

        if rule == VotingRule.SINGLE_APPROVER:
            if tally.yes_count > 0:
                _why = "One approval is sufficient for this committee"
                if tally.no_count:
                    # A dissent is not lost because somebody else approved.
                    _why += (" (%d YES, %d NO - the objection is recorded)"
                             % (tally.yes_count, tally.no_count))
                else:
                    _why += " (%d YES)" % tally.yes_count
                return (DecisionOutcome.APPROVED, _why)
            return (
                DecisionOutcome.REJECTED,
                "No member approved (%d NO)" % tally.no_count)

        if rule == VotingRule.UNANIMOUS:
            if tally.no_count == 0 and tally.yes_count > 0:
                return (
                    DecisionOutcome.APPROVED,
                    f"Unanimous approval ({tally.yes_count} YES, "
                    f"0 NO)")
            return (
                DecisionOutcome.REJECTED,
                f"Unanimous rule failed ({tally.yes_count} YES, "
                f"{tally.no_count} NO)")

        if rule == VotingRule.SUPERMAJORITY_TWO_THIRDS:
            ratio = tally.yes_count / tally.total_voting
            if ratio >= (2.0 / 3.0):
                return (
                    DecisionOutcome.APPROVED,
                    f"Two-thirds supermajority met "
                    f"({tally.yes_count}/{tally.total_voting} = "
                    f"{ratio:.1%})")
            return (
                DecisionOutcome.REJECTED,
                f"Two-thirds supermajority failed "
                f"({tally.yes_count}/{tally.total_voting} = "
                f"{ratio:.1%}); need ≥ 66.67%")

        if rule == VotingRule.CHAIR_TIEBREAKER:
            if tally.yes_count > tally.no_count:
                return (
                    DecisionOutcome.APPROVED,
                    f"Majority approval "
                    f"({tally.yes_count}-{tally.no_count})")
            if tally.yes_count < tally.no_count:
                return (
                    DecisionOutcome.REJECTED,
                    f"Majority rejection "
                    f"({tally.no_count}-{tally.yes_count})")
            # Tie — chair breaks
            chair = next(
                (m for m in attending_members
                 if m.role == CommitteeRole.CHAIR), None)
            if chair is None:
                return (
                    DecisionOutcome.DEFERRED,
                    "Tie vote; CHAIR_TIEBREAKER rule but chair absent")
            chair_vote = next(
                (v for v in votes
                 if v.member_id == chair.member_id), None)
            if chair_vote is None or chair_vote.vote not in (
                    VoteValue.YES, VoteValue.NO):
                return (
                    DecisionOutcome.DEFERRED,
                    "Tie vote; chair did not cast a YES/NO vote")
            if chair_vote.vote == VoteValue.YES:
                return (
                    DecisionOutcome.APPROVED,
                    f"Tie {tally.yes_count}-{tally.no_count}; "
                    f"chair tiebreaker → APPROVED")
            return (
                DecisionOutcome.REJECTED,
                f"Tie {tally.yes_count}-{tally.no_count}; "
                f"chair tiebreaker → REJECTED")

        # SIMPLE_MAJORITY (default): strictly > 50%; ties REJECTED
        # defensively (caller chooses CHAIR_TIEBREAKER if ties should
        # be broken).
        if tally.yes_count > tally.no_count:
            return (
                DecisionOutcome.APPROVED,
                f"Simple majority ({tally.yes_count}-"
                f"{tally.no_count})")
        if tally.yes_count == tally.no_count:
            return (
                DecisionOutcome.REJECTED,
                f"Tie {tally.yes_count}-{tally.no_count} under "
                f"SIMPLE_MAJORITY rule defaults to REJECTED — "
                f"use CHAIR_TIEBREAKER rule if ties should pass")
        return (
            DecisionOutcome.REJECTED,
            f"Majority NO ({tally.no_count}-{tally.yes_count})")

    # ── Public API ────────────────────────────────────────────────────
    def evaluate(
        self,
        request: CreditDecisionRequest,
        attending_member_ids: Tuple[str, ...],
        votes: Tuple[Vote, ...],
        applied_conditions: Tuple[str, ...] = (),
        notes: str = "",
    ) -> DecisionResult:
        """Evaluate one committee decision end-to-end."""
        # Step 1: authority check — facility above limit must escalate
        # *before* any vote is counted (a committee cannot decide
        # something outside its sanction).
        if request.facility_kes > self._charter.authority_limit_kes:
            tally = self._tally_votes(votes, attending_member_ids)
            return DecisionResult(
                request_id=request.request_id,
                committee_id=self._charter.committee_id,
                members_present_ids=attending_member_ids,
                members_present_roles=tuple(
                    m.role for m in self._charter.members
                    if m.member_id in attending_member_ids),
                quorum_status=QuorumStatus.MET,
                quorum_reason="Authority check supersedes",
                vote_tally=tally,
                voting_rule=self._charter.voting_rule,
                outcome=DecisionOutcome.ESCALATED,
                rationale=(
                    f"Facility KES {request.facility_kes:,.2f} "
                    f"exceeds committee authority "
                    f"KES {self._charter.authority_limit_kes:,.2f} "
                    f"— escalated to "
                    f"{self._charter.escalation_target}"),
                conditions=(),
                is_policy_override=request.is_policy_override,
                escalation_required=True,
                escalation_target=self._charter.escalation_target,
                framework_refs=(
                    "CBK PG/03 §6 Credit Risk Governance",
                    "CBK PG/03 §6.4 Required Officer Attendance",
                    "CBK PG/03 §6.7 Policy Override Documentation",
                ),
                notes=notes)

        # Step 2: quorum
        quorum_status, quorum_reason, attending = self._check_quorum(
            attending_member_ids)
        tally = self._tally_votes(votes, attending_member_ids)

        if quorum_status != QuorumStatus.MET:
            return DecisionResult(
                request_id=request.request_id,
                committee_id=self._charter.committee_id,
                members_present_ids=attending_member_ids,
                members_present_roles=tuple(
                    m.role for m in attending),
                quorum_status=quorum_status,
                quorum_reason=quorum_reason,
                vote_tally=tally,
                voting_rule=self._charter.voting_rule,
                outcome=DecisionOutcome.QUORUM_FAILED,
                rationale=(
                    f"Quorum failed: {quorum_reason}. Decision "
                    f"cannot be recorded."),
                conditions=(),
                is_policy_override=request.is_policy_override,
                escalation_required=False,
                escalation_target=None,
                framework_refs=(
                    "CBK PG/03 §6 Credit Risk Governance",
                    "CBK PG/03 §6.4 Quorum Requirements",
                ),
                notes=notes)

        # Step 3: voting outcome
        outcome, vote_rationale = self._outcome_from_tally(
            tally, attending, votes)

        # Step 4: condition handling — APPROVED + conditions →
        # APPROVED_WITH_CONDITIONS
        if (outcome == DecisionOutcome.APPROVED
                and applied_conditions):
            outcome = DecisionOutcome.APPROVED_WITH_CONDITIONS

        # Step 5: policy override governance — if override flag set,
        # we DO NOT change outcome (the committee can still approve
        # an override) but we surface the escalation requirement
        # per CBK PG/03 §6.7. The override must also be reported to
        # the next level.
        escalate_for_override = (
            request.is_policy_override
            and outcome in (
                DecisionOutcome.APPROVED,
                DecisionOutcome.APPROVED_WITH_CONDITIONS))

        rationale_parts = [vote_rationale]
        if request.is_policy_override:
            rationale_parts.append(
                f"POLICY OVERRIDE: {request.override_rationale}")
        if escalate_for_override:
            rationale_parts.append(
                "Policy-override approval reported to "
                f"{self._charter.escalation_target} per CBK "
                f"PG/03 §6.7")

        return DecisionResult(
            request_id=request.request_id,
            committee_id=self._charter.committee_id,
            members_present_ids=attending_member_ids,
            members_present_roles=tuple(m.role for m in attending),
            quorum_status=quorum_status,
            quorum_reason=quorum_reason,
            vote_tally=tally,
            voting_rule=self._charter.voting_rule,
            outcome=outcome,
            rationale=" | ".join(rationale_parts),
            conditions=applied_conditions,
            is_policy_override=request.is_policy_override,
            escalation_required=escalate_for_override,
            escalation_target=(
                self._charter.escalation_target
                if escalate_for_override else None),
            framework_refs=(
                "CBK PG/03 §6 Credit Risk Governance",
                "CBK PG/03 §6.4 Required Officer Attendance",
                "CBK PG/03 §6.6 Voting + Decision Recording",
                "CBK PG/03 §6.7 Policy Override Documentation",
            ),
            notes=notes)


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _build_default_charter() -> CommitteeCharter:
    """5-member committee with chair, CRO, CCO + 2 independents."""
    members = (
        CommitteeMember(
            member_id="m1", name="Alice (Chair)",
            role=CommitteeRole.CHAIR),
        CommitteeMember(
            member_id="m2", name="Bob (CRO)",
            role=CommitteeRole.CRO),
        CommitteeMember(
            member_id="m3", name="Carol (CCO)",
            role=CommitteeRole.CCO),
        CommitteeMember(
            member_id="m4", name="Dave (Indep)",
            role=CommitteeRole.INDEPENDENT_MEMBER,
            is_independent=True),
        CommitteeMember(
            member_id="m5", name="Eve (Indep)",
            role=CommitteeRole.INDEPENDENT_MEMBER,
            is_independent=True),
    )
    return CommitteeCharter(
        committee_id="MCC",
        name="Management Credit Committee",
        members=members,
        voting_rule=VotingRule.SIMPLE_MAJORITY,
        min_quorum_count=3,
        required_roles=frozenset({CommitteeRole.CRO}),
        authority_limit_kes=Decimal("100000000"),  # KES 100m
        independent_member_min=1)


def _test_member_validates_non_empty():
    try:
        CommitteeMember(
            member_id="", name="x", role=CommitteeRole.CHAIR)
        assert False
    except ValueError:
        pass


def _test_charter_validates_quorum_count_below_members():
    members = (CommitteeMember(
        member_id="m1", name="x", role=CommitteeRole.CHAIR),)
    try:
        CommitteeCharter(
            committee_id="C", name="C", members=members,
            voting_rule=VotingRule.SIMPLE_MAJORITY,
            min_quorum_count=5,
            required_roles=frozenset(),
            authority_limit_kes=Decimal("1000"))
        assert False
    except ValueError:
        pass


def _test_request_requires_override_rationale():
    try:
        CreditDecisionRequest(
            request_id="r1", borrower_id="b1",
            facility_kes=Decimal("1000000"),
            proposed_rationale="x",
            is_policy_override=True,
            override_rationale="")
        assert False
    except ValueError:
        pass


def _test_quorum_failed_when_cro_absent():
    """Required role CRO absent → QUORUM_FAILED."""
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="working capital")
    # m2 (CRO) not in attending list
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES)))
    assert result.outcome == DecisionOutcome.QUORUM_FAILED
    assert result.quorum_status == QuorumStatus.NOT_MET_REQUIRED_ROLE
    assert "CRO" in result.quorum_reason


def _test_quorum_failed_when_below_headcount():
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2"),    # only 2 of 3
        votes=())
    assert result.outcome == DecisionOutcome.QUORUM_FAILED
    assert result.quorum_status == QuorumStatus.NOT_MET_HEADCOUNT


def _test_authority_limit_exceeded_escalates():
    """Facility above authority → ESCALATED, not voted on."""
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r-big", borrower_id="b1",
        facility_kes=Decimal("200000000"),    # > 100m limit
        proposed_rationale="acquisition financing")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES)))
    assert result.outcome == DecisionOutcome.ESCALATED
    assert result.escalation_required is True
    assert result.escalation_target == "BOARD_RISK_COMMITTEE"


def _test_simple_majority_approves():
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="working capital")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.NO)))
    assert result.outcome == DecisionOutcome.APPROVED
    assert result.vote_tally.yes_count == 3
    assert result.vote_tally.no_count == 1


def _test_simple_majority_tie_rejects():
    """SIMPLE_MAJORITY rule defaults to REJECT on a tie."""
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.NO),
            Vote(member_id="m4", vote=VoteValue.NO)))
    assert result.outcome == DecisionOutcome.REJECTED


def _test_chair_tiebreaker_breaks_tie():
    """CHAIR_TIEBREAKER rule resolves ties via chair's vote."""
    charter = _build_default_charter()
    charter = CommitteeCharter(
        committee_id=charter.committee_id, name=charter.name,
        members=charter.members,
        voting_rule=VotingRule.CHAIR_TIEBREAKER,
        min_quorum_count=charter.min_quorum_count,
        required_roles=charter.required_roles,
        authority_limit_kes=charter.authority_limit_kes,
        independent_member_min=charter.independent_member_min)
    eng = CreditCommitteeEngine(charter)
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),  # chair
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.NO),
            Vote(member_id="m4", vote=VoteValue.NO)))
    assert result.outcome == DecisionOutcome.APPROVED


def _test_supermajority_two_thirds():
    charter = _build_default_charter()
    charter = CommitteeCharter(
        committee_id=charter.committee_id, name=charter.name,
        members=charter.members,
        voting_rule=VotingRule.SUPERMAJORITY_TWO_THIRDS,
        min_quorum_count=charter.min_quorum_count,
        required_roles=charter.required_roles,
        authority_limit_kes=charter.authority_limit_kes,
        independent_member_min=charter.independent_member_min)
    eng = CreditCommitteeEngine(charter)
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    # 4 of 5 = 80% → ≥ 66.67% → APPROVED
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4", "m5"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES),
            Vote(member_id="m5", vote=VoteValue.NO)))
    assert result.outcome == DecisionOutcome.APPROVED
    # 3 of 5 = 60% → REJECTED
    result2 = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4", "m5"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.NO),
            Vote(member_id="m5", vote=VoteValue.NO)))
    assert result2.outcome == DecisionOutcome.REJECTED


def _test_unanimous_requires_no_NO():
    charter = _build_default_charter()
    charter = CommitteeCharter(
        committee_id=charter.committee_id, name=charter.name,
        members=charter.members,
        voting_rule=VotingRule.UNANIMOUS,
        min_quorum_count=charter.min_quorum_count,
        required_roles=charter.required_roles,
        authority_limit_kes=charter.authority_limit_kes,
        independent_member_min=charter.independent_member_min)
    eng = CreditCommitteeEngine(charter)
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    # 1 NO vote → REJECTED under UNANIMOUS
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.NO)))
    assert result.outcome == DecisionOutcome.REJECTED


def _test_approved_with_conditions():
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES)),
        applied_conditions=(
            "Personal guarantee from director",
            "Quarterly compliance covenant"))
    assert result.outcome == DecisionOutcome.APPROVED_WITH_CONDITIONS
    assert len(result.conditions) == 2


def _test_policy_override_approval_escalates():
    """Policy override approved → escalation required per §6.7."""
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x",
        is_policy_override=True,
        override_rationale="Strategic relationship with anchor "
                           "client; LTV 92% vs policy max 80%")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES)))
    assert result.outcome == DecisionOutcome.APPROVED
    assert result.is_policy_override is True
    assert result.escalation_required is True
    assert result.escalation_target == "BOARD_RISK_COMMITTEE"
    assert "POLICY OVERRIDE" in result.rationale


def _test_recused_votes_excluded_from_tally():
    """Recused members count as present but not as YES/NO."""
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.RECUSED,
                 rationale="conflict — borrower is RM's family"),
            Vote(member_id="m4", vote=VoteValue.NO)))
    assert result.vote_tally.recused_count == 1
    assert result.vote_tally.total_voting == 3   # YES YES NO
    assert result.outcome == DecisionOutcome.APPROVED


def _test_all_abstain_defers_decision():
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    # m4 is independent — needed for quorum (independent_member_min=1)
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.ABSTAIN),
            Vote(member_id="m2", vote=VoteValue.ABSTAIN),
            Vote(member_id="m4", vote=VoteValue.ABSTAIN)))
    assert result.outcome == DecisionOutcome.DEFERRED


def _test_result_has_full_provenance():
    """Per Rule 1 — result surfaces full state."""
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="prov-test", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES)),
        notes="provenance-check")
    assert result.request_id == "prov-test"
    assert result.committee_id == "MCC"
    assert len(result.members_present_ids) == 4
    assert result.quorum_status == QuorumStatus.MET
    assert result.vote_tally.yes_count == 4
    assert result.voting_rule == VotingRule.SIMPLE_MAJORITY
    assert any("CBK PG/03" in r for r in result.framework_refs)
    assert result.notes == "provenance-check"


def _test_duplicate_vote_from_same_member_ignored():
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m1", vote=VoteValue.NO),  # dup
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES)))
    # First vote wins; duplicate ignored → 3 YES, 0 NO
    assert result.vote_tally.yes_count == 3
    assert result.vote_tally.no_count == 0


def _test_vote_from_absent_member_ignored():
    eng = CreditCommitteeEngine(_build_default_charter())
    request = CreditDecisionRequest(
        request_id="r1", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="x")
    result = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m5", vote=VoteValue.NO)))   # absent
    assert result.vote_tally.yes_count == 3
    assert result.vote_tally.no_count == 0


def self_test() -> None:
    tests = [
        _test_member_validates_non_empty,
        _test_charter_validates_quorum_count_below_members,
        _test_request_requires_override_rationale,
        _test_quorum_failed_when_cro_absent,
        _test_quorum_failed_when_below_headcount,
        _test_authority_limit_exceeded_escalates,
        _test_simple_majority_approves,
        _test_simple_majority_tie_rejects,
        _test_chair_tiebreaker_breaks_tie,
        _test_supermajority_two_thirds,
        _test_unanimous_requires_no_NO,
        _test_approved_with_conditions,
        _test_policy_override_approval_escalates,
        _test_recused_votes_excluded_from_tally,
        _test_all_abstain_defers_decision,
        _test_result_has_full_provenance,
        _test_duplicate_vote_from_same_member_ignored,
        _test_vote_from_absent_member_ignored,
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
            f"✗ credit_committee self-test: {len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ credit_committee self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

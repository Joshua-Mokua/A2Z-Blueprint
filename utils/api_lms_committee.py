"""utils/api_lms_committee.py — v10.586

Thin adapter that wires the EXISTING CreditCommitteeEngine
(utils/credit_committee.py) into the live LMS decision flow when the bank's
policy is committee_mode == "committee_voting". No committee logic is
duplicated here — this only:

  1. Builds a CommitteeCharter from admin config (credit_workflow.committee),
     falling back to the engine's default charter.
  2. Decides whether an application must go to committee (amount threshold).
  3. Converts stored votes -> engine types, runs engine.evaluate(), and maps
     the DecisionResult back to the live string-status flow.

Config (lms_config.json -> credit_workflow.committee):
  refer_above_kes, voting_rule, min_quorum_count, authority_limit_kes,
  independent_member_min, required_roles[], members[{member_id,name,role,
  is_independent}]
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Tuple

from utils.credit_committee import (
    CommitteeMember, CommitteeCharter, Vote, CreditDecisionRequest,
    CreditCommitteeEngine, CommitteeRole, VotingRule, VoteValue,
    DecisionOutcome, _build_default_charter,
)
from utils.api_lms_mutations import get_credit_workflow_config


def _committee_cfg() -> Dict[str, Any]:
    return dict((get_credit_workflow_config().get("committee") or {}))


def committee_mode_on() -> bool:
    return str(get_credit_workflow_config().get(
        "committee_mode", "authority_tier")) == "committee_voting"


def committee_required(amount: float) -> bool:
    """True if committee voting is on AND the facility is at/above the
    configured referral threshold."""
    if not committee_mode_on():
        return False
    try:
        threshold = float(_committee_cfg().get("refer_above_kes", 100_000_000))
    except Exception:
        threshold = 100_000_000.0
    try:
        return float(amount or 0) >= threshold
    except Exception:
        return False


def charter_from_config() -> CommitteeCharter:
    """Build a CommitteeCharter from admin config; fall back to the engine's
    default charter if members aren't configured or config is malformed."""
    cfg = _committee_cfg()
    members_cfg = cfg.get("members") or []
    if not members_cfg:
        return _build_default_charter()
    try:
        members = tuple(
            CommitteeMember(
                member_id=str(m["member_id"]),
                name=str(m.get("name", m["member_id"])),
                role=CommitteeRole[str(m.get("role", "EXECUTIVE_MEMBER"))],
                is_independent=bool(m.get("is_independent", False)),
            )
            for m in members_cfg
        )
        required_roles = frozenset(
            CommitteeRole[str(r)] for r in (cfg.get("required_roles") or [])
        )
        return CommitteeCharter(
            committee_id=str(cfg.get("committee_id", "MCC")),
            name=str(cfg.get("name", "Management Credit Committee")),
            members=members,
            voting_rule=VotingRule[str(cfg.get("voting_rule", "SIMPLE_MAJORITY"))],
            min_quorum_count=int(cfg.get("min_quorum_count", 3)),
            required_roles=required_roles,
            authority_limit_kes=Decimal(str(cfg.get("authority_limit_kes", "500000000"))),
            independent_member_min=int(cfg.get("independent_member_min", 0)),
            escalation_target=str(cfg.get("escalation_target", "BOARD_RISK_COMMITTEE")),
        )
    except Exception:
        # Any malformed config -> safe default charter (never crash a decision).
        return _build_default_charter()


def committee_member_ids() -> List[str]:
    return [m.member_id for m in charter_from_config().members]


def evaluate_committee(app: Dict[str, Any],
                       attending_member_ids: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """Run the committee engine over the votes stored on the application.

    Returns a plain dict the route can act on:
      { outcome, approved, rejected, escalated, quorum_failed,
        quorum_status, conditions, rationale, tally, escalation_required }
    """
    charter = charter_from_config()
    engine = CreditCommitteeEngine(charter)

    committee = app.get("committee") or {}
    raw_votes = committee.get("votes") or []
    votes = tuple(
        Vote(
            member_id=str(v["member_id"]),
            vote=VoteValue[str(v["vote"]).upper()],
            rationale=str(v.get("rationale", "")),
        )
        for v in raw_votes
        if v.get("member_id") and v.get("vote")
    )
    # Attending = explicit list, else everyone who cast a vote.
    attending = tuple(attending_member_ids) or tuple(
        dict.fromkeys(v.member_id for v in votes))

    amount = float(app.get("amount", 0) or 0)
    request = CreditDecisionRequest(
        request_id=str(app.get("id", "APP")),
        borrower_id=str(app.get("client_cif", "") or app.get("client_name", "") or "NA"),
        facility_kes=Decimal(str(amount if amount > 0 else 1)),
        proposed_rationale=str(committee.get("rationale", "Credit committee review")),
    )
    applied = tuple(committee.get("applied_conditions") or [])
    result = engine.evaluate(request, attending, votes, applied_conditions=applied)

    outcome = result.outcome
    approved = outcome in (DecisionOutcome.APPROVED,
                           DecisionOutcome.APPROVED_WITH_CONDITIONS)
    return {
        "outcome": outcome.value,
        "approved": approved,
        "rejected": outcome == DecisionOutcome.REJECTED,
        "escalated": outcome == DecisionOutcome.ESCALATED,
        "quorum_failed": outcome == DecisionOutcome.QUORUM_FAILED,
        "deferred": outcome == DecisionOutcome.DEFERRED,
        "quorum_status": result.quorum_status.value,
        "quorum_reason": result.quorum_reason,
        "conditions": list(result.conditions),
        "rationale": result.rationale,
        "escalation_required": bool(result.escalation_required),
        "escalation_target": result.escalation_target,
        "tally": {
            "yes": result.vote_tally.yes_count,
            "no": result.vote_tally.no_count,
            "abstain": result.vote_tally.abstain_count,
            "recused": result.vote_tally.recused_count,
            "present": result.vote_tally.total_present,
        },
    }

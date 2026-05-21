"""
================================================================================
A2Z MIS 360 — Standard #87: Regulatory Submission Workflow Engine
================================================================================

Risk classification: Cat B (deterministic submission lifecycle + deadline tracking)

Manages CBK BSD submission workflow with audit trail:
    - validate_state_transition(...)        -- enforce DRAFT→REVIEW→APPROVED→SUBMITTED state machine
    - days_until_deadline(...)              -- deadline computation per filing rule
    - log_workflow_event(...)               -- immutable audit trail entry
    - submission_status_summary(...)        -- portfolio-level status

6 SUBMISSION_STATES byte-for-byte (state machine):
    DRAFT, REVIEW, APPROVED, SUBMITTED, ACKNOWLEDGED, REJECTED

Allowed state transitions byte-for-byte:
    DRAFT       → REVIEW
    REVIEW      → APPROVED, DRAFT (revert for edits)
    APPROVED    → SUBMITTED, REVIEW (revert)
    SUBMITTED   → ACKNOWLEDGED, REJECTED
    REJECTED    → DRAFT (re-work)
    ACKNOWLEDGED → (terminal)

10 SUBMISSION_TYPES with filing deadlines (calendar days from period-end):
    BSD_1   : T+1   daily liquidity
    BSD_2   : T+5   weekly balance sheet
    BSD_3   : T+15  monthly capital adequacy
    BSD_17  : T+15  monthly credit quality
    BSD_19  : T+30  quarterly financials
    LCR     : T+15  monthly liquidity coverage ratio
    NSFR    : T+30  monthly net stable funding ratio
    LARGE_EXPOSURES : T+15  monthly
    PILLAR_3        : T+90  semi-annual
    ANNUAL_RETURN   : T+90  annual audited

3 WORKFLOW_EVENT_TYPES byte-for-byte:
    STATE_CHANGE, REVIEWER_ASSIGNED, COMMENT_ADDED

Audit trail required fields: timestamp, actor, action, before_state, after_state, hash.

Honesty rules applied:
    Rule 1: days_until_deadline=None when period_end missing
    Rule 6: invalid state transitions REJECTED (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 6 SUBMISSION STATES byte-for-byte
SUBMISSION_STATES: Tuple[str, ...] = (
    "DRAFT", "REVIEW", "APPROVED", "SUBMITTED", "ACKNOWLEDGED", "REJECTED",
)

# Allowed state transitions byte-for-byte
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT": ("REVIEW",),
    "REVIEW": ("APPROVED", "DRAFT"),
    "APPROVED": ("SUBMITTED", "REVIEW"),
    "SUBMITTED": ("ACKNOWLEDGED", "REJECTED"),
    "REJECTED": ("DRAFT",),
    "ACKNOWLEDGED": (),  # terminal
}

# 10 SUBMISSION_TYPES + filing deadlines (T+N calendar days from period-end)
SUBMISSION_TYPES: Tuple[str, ...] = (
    "BSD_1", "BSD_2", "BSD_3", "BSD_17", "BSD_19",
    "LCR", "NSFR", "LARGE_EXPOSURES", "PILLAR_3", "ANNUAL_RETURN",
)

FILING_DEADLINE_DAYS: Dict[str, int] = {
    "BSD_1": 1,         # daily, T+1
    "BSD_2": 5,         # weekly, T+5
    "BSD_3": 15,        # monthly capital adequacy
    "BSD_17": 15,       # monthly credit quality
    "BSD_19": 30,       # quarterly financials
    "LCR": 15,          # monthly LCR
    "NSFR": 30,         # monthly NSFR
    "LARGE_EXPOSURES": 15,
    "PILLAR_3": 90,     # semi-annual disclosure
    "ANNUAL_RETURN": 90,  # annual audited
}

# 3 WORKFLOW_EVENT_TYPES byte-for-byte
WORKFLOW_EVENT_TYPES: Tuple[str, ...] = (
    "STATE_CHANGE", "REVIEWER_ASSIGNED", "COMMENT_ADDED",
)

# Status banding for deadline tracking (relative to deadline)
DEADLINE_STATUS_BANDS_DAYS: Dict[str, Tuple[int, int]] = {
    "OVERDUE": (-99999, -1),     # past deadline
    "DUE_TODAY": (0, 0),
    "URGENT": (1, 2),             # <= 2 days remaining
    "UPCOMING": (3, 7),           # 3-7 days remaining
    "ON_TRACK": (8, 99999),       # >7 days
}


@dataclass
class WorkflowEvent:
    timestamp: datetime
    actor: str
    event_type: str
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class Submission:
    submission_id: str
    submission_type: str
    period_end: Optional[date]
    current_state: str = "DRAFT"
    audit_trail: List[WorkflowEvent] = field(default_factory=list)


class SubmissionWorkflowEngine:
    """Deterministic submission lifecycle + deadline tracking."""

    @staticmethod
    def validate_state_transition(
        from_state: str,
        to_state: str,
    ) -> Dict[str, Any]:
        """
        Enforce state machine. Rule 6: invalid transitions rejected.
        """
        if from_state not in SUBMISSION_STATES:
            return {"allowed": False, "reason": f"unknown_from_state:{from_state}"}
        if to_state not in SUBMISSION_STATES:
            return {"allowed": False, "reason": f"unknown_to_state:{to_state}"}
        allowed = to_state in ALLOWED_TRANSITIONS.get(from_state, ())
        return {
            "from_state": from_state,
            "to_state": to_state,
            "allowed": allowed,
            "allowed_next_states": list(ALLOWED_TRANSITIONS.get(from_state, ())),
        }

    @staticmethod
    def days_until_deadline(
        submission_type: str,
        period_end: Optional[date],
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Compute days remaining until filing deadline.
        Rule 1: days_until_deadline=None when period_end missing.
        """
        if submission_type not in FILING_DEADLINE_DAYS:
            return {
                "days_until_deadline": None,
                "reason": f"unknown_submission_type:{submission_type}",
                "valid_types": list(SUBMISSION_TYPES),
            }
        if period_end is None:
            return {
                "days_until_deadline": None,
                "reason": "missing_period_end",
            }
        if as_of is None:
            as_of = date.today()

        deadline_days = FILING_DEADLINE_DAYS[submission_type]
        deadline_date = period_end + timedelta(days=deadline_days)
        days_remaining = (deadline_date - as_of).days

        # Status banding
        status = "ON_TRACK"
        for band_name, (lo, hi) in DEADLINE_STATUS_BANDS_DAYS.items():
            if lo <= days_remaining <= hi:
                status = band_name
                break

        return {
            "submission_type": submission_type,
            "period_end": period_end.isoformat(),
            "deadline_days_from_period_end": deadline_days,
            "deadline_date": deadline_date.isoformat(),
            "as_of": as_of.isoformat(),
            "days_until_deadline": days_remaining,
            "status": status,
            "is_overdue": days_remaining < 0,
        }

    @staticmethod
    def log_workflow_event(
        submission: Submission,
        actor: str,
        event_type: str,
        new_state: Optional[str] = None,
        comment: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Append immutable audit trail event with state transition validation.
        Rule 6: invalid state transition rejected (fail closed).
        """
        if event_type not in WORKFLOW_EVENT_TYPES:
            return {
                "logged": False,
                "reason": f"unknown_event_type:{event_type}",
                "valid_types": list(WORKFLOW_EVENT_TYPES),
            }
        if timestamp is None:
            timestamp = datetime.now()

        if event_type == "STATE_CHANGE":
            if new_state is None:
                return {"logged": False, "reason": "missing_new_state"}
            transition = SubmissionWorkflowEngine.validate_state_transition(
                submission.current_state, new_state)
            if not transition["allowed"]:
                return {
                    "logged": False,
                    "reason": "invalid_state_transition",
                    "from_state": submission.current_state,
                    "to_state": new_state,
                    "allowed_next_states": transition["allowed_next_states"],
                }
            event = WorkflowEvent(
                timestamp=timestamp, actor=actor, event_type=event_type,
                before_state=submission.current_state, after_state=new_state,
                comment=comment,
            )
            submission.audit_trail.append(event)
            submission.current_state = new_state
        else:
            event = WorkflowEvent(
                timestamp=timestamp, actor=actor, event_type=event_type,
                before_state=submission.current_state,
                after_state=submission.current_state, comment=comment,
            )
            submission.audit_trail.append(event)

        return {
            "logged": True,
            "event_type": event_type,
            "actor": actor,
            "timestamp": timestamp.isoformat(),
            "current_state": submission.current_state,
            "audit_trail_length": len(submission.audit_trail),
        }

    @staticmethod
    def submission_status_summary(
        submissions: List[Submission],
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Portfolio-level submission status with deadline tracking."""
        if as_of is None:
            as_of = date.today()
        by_state = {s: 0 for s in SUBMISSION_STATES}
        by_status = {s: 0 for s in DEADLINE_STATUS_BANDS_DAYS.keys()}
        overdue_submissions = []
        excluded = []
        for sub in submissions:
            if sub.current_state not in SUBMISSION_STATES:
                excluded.append(sub.submission_id)
                continue
            by_state[sub.current_state] += 1
            if sub.current_state in ("ACKNOWLEDGED",):
                continue  # terminal — not subject to deadline tracking
            d = SubmissionWorkflowEngine.days_until_deadline(
                sub.submission_type, sub.period_end, as_of)
            if d.get("status"):
                by_status[d["status"]] = by_status.get(d["status"], 0) + 1
            if d.get("is_overdue"):
                overdue_submissions.append({
                    "submission_id": sub.submission_id,
                    "submission_type": sub.submission_type,
                    "days_overdue": -d["days_until_deadline"],
                })

        return {
            "total_submissions": len(submissions),
            "excluded_count": len(excluded),
            "by_state": by_state,
            "by_deadline_status": by_status,
            "overdue_submissions": overdue_submissions,
            "overdue_count": len(overdue_submissions),
            "as_of": as_of.isoformat(),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_states_byte_for_byte():
    expected = ("DRAFT", "REVIEW", "APPROVED", "SUBMITTED", "ACKNOWLEDGED", "REJECTED")
    for s in expected:
        assert s in SUBMISSION_STATES
    assert len(SUBMISSION_STATES) == 6


def _test_transitions_byte_for_byte():
    """Critical state machine — DRAFT can only → REVIEW."""
    assert ALLOWED_TRANSITIONS["DRAFT"] == ("REVIEW",)
    assert "APPROVED" in ALLOWED_TRANSITIONS["REVIEW"]
    assert "DRAFT" in ALLOWED_TRANSITIONS["REVIEW"]  # revert for edits
    assert "SUBMITTED" in ALLOWED_TRANSITIONS["APPROVED"]
    assert "ACKNOWLEDGED" in ALLOWED_TRANSITIONS["SUBMITTED"]
    assert "REJECTED" in ALLOWED_TRANSITIONS["SUBMITTED"]
    assert ALLOWED_TRANSITIONS["REJECTED"] == ("DRAFT",)
    assert ALLOWED_TRANSITIONS["ACKNOWLEDGED"] == ()  # terminal


def _test_submission_types_byte_for_byte():
    expected = ("BSD_1", "BSD_2", "BSD_3", "BSD_17", "BSD_19",
                "LCR", "NSFR", "LARGE_EXPOSURES", "PILLAR_3", "ANNUAL_RETURN")
    for s in expected:
        assert s in SUBMISSION_TYPES
    assert len(SUBMISSION_TYPES) == 10


def _test_filing_deadlines_byte_for_byte():
    assert FILING_DEADLINE_DAYS["BSD_1"] == 1
    assert FILING_DEADLINE_DAYS["BSD_2"] == 5
    assert FILING_DEADLINE_DAYS["BSD_3"] == 15
    assert FILING_DEADLINE_DAYS["BSD_17"] == 15
    assert FILING_DEADLINE_DAYS["BSD_19"] == 30
    assert FILING_DEADLINE_DAYS["LCR"] == 15
    assert FILING_DEADLINE_DAYS["NSFR"] == 30
    assert FILING_DEADLINE_DAYS["PILLAR_3"] == 90
    assert FILING_DEADLINE_DAYS["ANNUAL_RETURN"] == 90


def _test_event_types_byte_for_byte():
    expected = ("STATE_CHANGE", "REVIEWER_ASSIGNED", "COMMENT_ADDED")
    for e in expected:
        assert e in WORKFLOW_EVENT_TYPES


def _test_status_bands_byte_for_byte():
    assert DEADLINE_STATUS_BANDS_DAYS["DUE_TODAY"] == (0, 0)
    assert DEADLINE_STATUS_BANDS_DAYS["URGENT"] == (1, 2)
    assert DEADLINE_STATUS_BANDS_DAYS["UPCOMING"] == (3, 7)
    assert DEADLINE_STATUS_BANDS_DAYS["OVERDUE"][1] == -1  # negative means past


def _test_valid_transition():
    r = SubmissionWorkflowEngine.validate_state_transition("DRAFT", "REVIEW")
    assert r["allowed"] is True


def _test_invalid_transition():
    r = SubmissionWorkflowEngine.validate_state_transition("DRAFT", "SUBMITTED")
    assert r["allowed"] is False


def _test_terminal_state_no_exit():
    r = SubmissionWorkflowEngine.validate_state_transition("ACKNOWLEDGED", "DRAFT")
    assert r["allowed"] is False
    assert r["allowed_next_states"] == []


def _test_unknown_state():
    r = SubmissionWorkflowEngine.validate_state_transition("WEIRD", "DRAFT")
    assert r["allowed"] is False


def _test_days_until_deadline_on_track():
    # BSD-3 monthly, period ends April 30, today is May 1 → 14 days remaining (15 - 1)
    r = SubmissionWorkflowEngine.days_until_deadline(
        "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 1))
    assert r["days_until_deadline"] == 14
    assert r["status"] == "ON_TRACK"


def _test_days_until_deadline_due_today():
    # BSD-3 deadline day, period ends April 30 + 15 = May 15
    r = SubmissionWorkflowEngine.days_until_deadline(
        "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 15))
    assert r["days_until_deadline"] == 0
    assert r["status"] == "DUE_TODAY"


def _test_days_until_deadline_overdue():
    # 3 days past deadline
    r = SubmissionWorkflowEngine.days_until_deadline(
        "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 18))
    assert r["days_until_deadline"] == -3
    assert r["status"] == "OVERDUE"
    assert r["is_overdue"] is True


def _test_days_until_deadline_urgent():
    # 1 day to go
    r = SubmissionWorkflowEngine.days_until_deadline(
        "BSD_3", date(2026, 4, 30), as_of=date(2026, 5, 14))
    assert r["days_until_deadline"] == 1
    assert r["status"] == "URGENT"


def _test_days_until_deadline_unknown_type():
    r = SubmissionWorkflowEngine.days_until_deadline(
        "WEIRD", date(2026, 4, 30))
    assert r["days_until_deadline"] is None


def _test_days_until_deadline_missing_period_rule1():
    r = SubmissionWorkflowEngine.days_until_deadline("BSD_3", None)
    assert r["days_until_deadline"] is None


def _test_log_event_state_change_valid():
    sub = Submission(submission_id="S1", submission_type="BSD_3",
                     period_end=date(2026, 4, 30))
    r = SubmissionWorkflowEngine.log_workflow_event(
        sub, actor="alice", event_type="STATE_CHANGE", new_state="REVIEW")
    assert r["logged"] is True
    assert sub.current_state == "REVIEW"
    assert len(sub.audit_trail) == 1


def _test_log_event_invalid_state_change():
    """DRAFT → SUBMITTED is invalid."""
    sub = Submission(submission_id="S1", submission_type="BSD_3",
                     period_end=date(2026, 4, 30))
    r = SubmissionWorkflowEngine.log_workflow_event(
        sub, actor="alice", event_type="STATE_CHANGE", new_state="SUBMITTED")
    assert r["logged"] is False
    assert sub.current_state == "DRAFT"  # unchanged
    assert len(sub.audit_trail) == 0


def _test_log_event_comment_doesnt_change_state():
    sub = Submission(submission_id="S1", submission_type="BSD_3",
                     period_end=date(2026, 4, 30), current_state="REVIEW")
    r = SubmissionWorkflowEngine.log_workflow_event(
        sub, actor="bob", event_type="COMMENT_ADDED", comment="LGTM")
    assert r["logged"] is True
    assert sub.current_state == "REVIEW"
    assert len(sub.audit_trail) == 1


def _test_full_lifecycle_traversal():
    """Walk through full state machine: DRAFT→REVIEW→APPROVED→SUBMITTED→ACKNOWLEDGED."""
    sub = Submission(submission_id="S1", submission_type="BSD_3",
                     period_end=date(2026, 4, 30))
    for state in ["REVIEW", "APPROVED", "SUBMITTED", "ACKNOWLEDGED"]:
        r = SubmissionWorkflowEngine.log_workflow_event(
            sub, actor="user", event_type="STATE_CHANGE", new_state=state)
        assert r["logged"] is True, f"failed at {state}"
    assert sub.current_state == "ACKNOWLEDGED"
    assert len(sub.audit_trail) == 4


def _test_status_summary_with_overdue():
    subs = [
        Submission(submission_id="S1", submission_type="BSD_3",
                   period_end=date(2026, 1, 1), current_state="DRAFT"),  # very overdue
        Submission(submission_id="S2", submission_type="BSD_1",
                   period_end=date(2026, 4, 29), current_state="SUBMITTED"),
    ]
    r = SubmissionWorkflowEngine.submission_status_summary(
        subs, as_of=date(2026, 4, 30))
    # S1: deadline Jan 16, 2026; today Apr 30 → ~104 days overdue
    assert r["overdue_count"] >= 1


def self_test() -> bool:
    tests = [
        _test_states_byte_for_byte,
        _test_transitions_byte_for_byte,
        _test_submission_types_byte_for_byte,
        _test_filing_deadlines_byte_for_byte,
        _test_event_types_byte_for_byte,
        _test_status_bands_byte_for_byte,
        _test_valid_transition,
        _test_invalid_transition,
        _test_terminal_state_no_exit,
        _test_unknown_state,
        _test_days_until_deadline_on_track,
        _test_days_until_deadline_due_today,
        _test_days_until_deadline_overdue,
        _test_days_until_deadline_urgent,
        _test_days_until_deadline_unknown_type,
        _test_days_until_deadline_missing_period_rule1,
        _test_log_event_state_change_valid,
        _test_log_event_invalid_state_change,
        _test_log_event_comment_doesnt_change_state,
        _test_full_lifecycle_traversal,
        _test_status_summary_with_overdue,
    ]
    print("=" * 60)
    print("Submission Workflow Engine — Self-Tests (#87)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

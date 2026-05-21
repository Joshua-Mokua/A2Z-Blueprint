"""utils/outside_counsel_portal.py — ENH-224 Outside Counsel Portal.

Third engine of Legal arc. Self-service portal for external lawyers.
Tracks counsel firms, matter assignments, document exchange refs,
billing submissions with UTBMS codes, and status updates.

UTBMS (Uniform Task-Based Management System) — industry standard
billing code taxonomy (L100, L200, etc. for litigation; A100 for
case admin; etc.). v10.172 ships a subset relevant to Kenya banking.

LIFECYCLE — Counsel
    PENDING_VERIFICATION → ACTIVE → SUSPENDED/RETIRED

LIFECYCLE — Matter Assignment
    ASSIGNED → IN_PROGRESS → DELIVERED → ACCEPTED/REJECTED

LIFECYCLE — Billing Submission
    SUBMITTED → UNDER_REVIEW → APPROVED/DISPUTED/REJECTED

HONEST DEFERRALS
- PORTAL UI: engine API only; actual self-service portal UI is
  operator-side
- AUTHENTICATION: external counsel auth is operator-side (e.g.
  vendor portal SSO)
- BILLING TRANSMISSION: engine tracks submissions; AP integration
  for actual payment dispatch is operator-side
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


class CounselStatus(str, Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class AssignmentStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    DELIVERED = "DELIVERED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class BillingStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    DISPUTED = "DISPUTED"
    REJECTED = "REJECTED"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"
    REJECTED_COUNSEL_NOT_ACTIVE = "REJECTED_COUNSEL_NOT_ACTIVE"


# UTBMS codes subset relevant to banking-sector litigation
UTBMS_CODES_LITIGATION = {
    "L100": "Case Assessment, Development, and Administration",
    "L110": "Fact Investigation/Development",
    "L120": "Analysis/Strategy",
    "L130": "Experts/Consultants",
    "L140": "Document/File Management",
    "L150": "Budgeting",
    "L160": "Settlement/Non-Binding ADR",
    "L200": "Pre-Trial Pleadings and Motions",
    "L210": "Pleadings",
    "L240": "Dispositive Motions",
    "L300": "Discovery",
    "L400": "Trial Preparation and Trial",
    "L450": "Trial and Hearing Attendance",
    "A101": "Plan and prepare for",
    "A102": "Research",
    "A103": "Draft/revise",
    "A104": "Review/analyze",
    "A105": "Communicate (in firm)",
    "A106": "Communicate (with client)",
    "A107": "Communicate (other counsel)",
    "A108": "Communicate (other external)",
    "A109": "Appear for/attend",
    "A110": "Manage data/files",
    "A111": "Other",
}


COUNSEL_TRANSITIONS: Mapping[CounselStatus,
                              Tuple[CounselStatus, ...]] = {
    CounselStatus.PENDING_VERIFICATION: (
        CounselStatus.ACTIVE, CounselStatus.RETIRED),
    CounselStatus.ACTIVE: (
        CounselStatus.SUSPENDED, CounselStatus.RETIRED),
    CounselStatus.SUSPENDED: (
        CounselStatus.ACTIVE, CounselStatus.RETIRED),
    CounselStatus.RETIRED: (),
}


ASSIGNMENT_TRANSITIONS: Mapping[AssignmentStatus,
                                  Tuple[AssignmentStatus, ...]] = {
    AssignmentStatus.ASSIGNED: (AssignmentStatus.IN_PROGRESS,
                                  AssignmentStatus.REJECTED),
    AssignmentStatus.IN_PROGRESS: (AssignmentStatus.DELIVERED,),
    AssignmentStatus.DELIVERED: (AssignmentStatus.ACCEPTED,
                                  AssignmentStatus.REJECTED),
    AssignmentStatus.ACCEPTED: (),
    AssignmentStatus.REJECTED: (),
}


BILLING_TRANSITIONS: Mapping[BillingStatus, Tuple[BillingStatus, ...]] = {
    BillingStatus.SUBMITTED: (BillingStatus.UNDER_REVIEW,),
    BillingStatus.UNDER_REVIEW: (
        BillingStatus.APPROVED, BillingStatus.DISPUTED,
        BillingStatus.REJECTED),
    BillingStatus.DISPUTED: (
        BillingStatus.APPROVED, BillingStatus.REJECTED),
    BillingStatus.APPROVED: (),
    BillingStatus.REJECTED: (),
}


@dataclass(frozen=True)
class Counsel:
    counsel_id: str
    firm_name: str
    primary_contact_name: str
    primary_contact_email: str
    bar_number: str           # Kenya advocate registration
    rate_card_currency: str   # KES, USD
    status: CounselStatus
    onboarded_at_utc: str
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    suspension_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"counsel_id": self.counsel_id,
                "firm_name": self.firm_name,
                "primary_contact_name": self.primary_contact_name,
                "primary_contact_email": self.primary_contact_email,
                "bar_number": self.bar_number,
                "rate_card_currency": self.rate_card_currency,
                "status": self.status.value,
                "onboarded_at_utc": self.onboarded_at_utc,
                "transition_log": [dict(t)
                                     for t in self.transition_log],
                "suspension_reason": self.suspension_reason}


@dataclass(frozen=True)
class MatterAssignment:
    assignment_id: str
    counsel_id: str
    matter_id: str            # links to legal_case_management case_id
    title: str
    scope_of_work: str
    fee_arrangement: str      # hourly/fixed/contingent/retainer
    estimated_amount: Decimal
    estimated_currency: str
    status: AssignmentStatus
    assigned_at_utc: str
    delivered_at_utc: str = ""
    deliverable_refs: Tuple[str, ...] = ()
    transition_log: Tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"assignment_id": self.assignment_id,
                "counsel_id": self.counsel_id,
                "matter_id": self.matter_id, "title": self.title,
                "scope_of_work": self.scope_of_work,
                "fee_arrangement": self.fee_arrangement,
                "estimated_amount": str(self.estimated_amount),
                "estimated_currency": self.estimated_currency,
                "status": self.status.value,
                "assigned_at_utc": self.assigned_at_utc,
                "delivered_at_utc": self.delivered_at_utc,
                "deliverable_refs": list(self.deliverable_refs),
                "transition_log": [dict(t)
                                     for t in self.transition_log]}


@dataclass(frozen=True)
class BillingLine:
    utbms_task_code: str       # L120, A102 etc.
    description: str
    hours: Decimal
    rate: Decimal
    currency: str

    @property
    def amount(self) -> Decimal:
        return self.hours * self.rate

    def to_dict(self) -> Dict[str, Any]:
        return {"utbms_task_code": self.utbms_task_code,
                "description": self.description,
                "hours": str(self.hours), "rate": str(self.rate),
                "currency": self.currency,
                "amount": str(self.amount)}


@dataclass(frozen=True)
class BillingSubmission:
    submission_id: str
    counsel_id: str
    assignment_id: str
    invoice_number: str
    period_start: str          # YYYY-MM-DD
    period_end: str
    lines: Tuple[BillingLine, ...]
    total_amount: Decimal
    currency: str
    status: BillingStatus
    submitted_at_utc: str
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    review_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"submission_id": self.submission_id,
                "counsel_id": self.counsel_id,
                "assignment_id": self.assignment_id,
                "invoice_number": self.invoice_number,
                "period_start": self.period_start,
                "period_end": self.period_end,
                "lines": [l.to_dict() for l in self.lines],
                "total_amount": str(self.total_amount),
                "currency": self.currency,
                "status": self.status.value,
                "submitted_at_utc": self.submitted_at_utc,
                "transition_log": [dict(t)
                                     for t in self.transition_log],
                "review_notes": self.review_notes}


class OutsideCounselPortalEngine:
    """ENH-224 Outside Counsel Portal Engine."""

    PORTAL_UI_STATUS = (
        "DEFERRED — engine ships API; actual self-service portal UI "
        "(login, document drop-zone, billing submission form) is "
        "operator-side. v10.172 ships engine + API surface; UI "
        "wiring future increment.")

    AUTHENTICATION_STATUS = (
        "DEFERRED — external counsel authentication is operator-"
        "side (vendor portal SSO, OAuth, or manual credential "
        "issue). Engine accepts counsel_id refs assuming auth is "
        "established upstream.")

    AP_INTEGRATION_STATUS = (
        "DEFERRED — engine tracks billing submissions through "
        "approval lifecycle; actual payment dispatch via AP/AR "
        "system (FLEXCUBE Payments, M-Pesa, SWIFT) is operator-"
        "side. v10.172 ships approval ledger; payment wiring "
        "future work.")

    def __init__(self) -> None:
        self._counsel: Dict[str, Counsel] = {}
        self._assignments: Dict[str, MatterAssignment] = {}
        self._submissions: Dict[str, BillingSubmission] = {}
        self._next_counsel = 1
        self._next_assignment = 1
        self._next_submission = 1

    # Counsel onboarding
    def onboard_counsel(
        self, firm_name: str, primary_contact_name: str,
        primary_contact_email: str, bar_number: str,
        rate_card_currency: str = "KES",
    ) -> Counsel:
        if not firm_name.strip():
            raise ValueError("firm_name required")
        if not bar_number.strip():
            raise ValueError(
                "bar_number required — Kenya advocate registration "
                "must be verified before any matter assignment")
        cid = f"CSL-{self._next_counsel:06d}"
        self._next_counsel += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        counsel = Counsel(
            counsel_id=cid, firm_name=firm_name.strip(),
            primary_contact_name=primary_contact_name.strip(),
            primary_contact_email=primary_contact_email.strip(),
            bar_number=bar_number.strip(),
            rate_card_currency=rate_card_currency.strip(),
            status=CounselStatus.PENDING_VERIFICATION,
            onboarded_at_utc=now_utc,
            transition_log=(
                {"to_status": "PENDING_VERIFICATION",
                 "at_utc": now_utc, "user": "system",
                 "reason": "initial onboarding"},))
        self._counsel[cid] = counsel
        return counsel

    def transition_counsel(
        self, counsel_id: str, new_status: CounselStatus,
        user: str, reason: str = "",
    ) -> Tuple[TransitionOutcome, Optional[Counsel]]:
        if counsel_id not in self._counsel:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._counsel[counsel_id]
        if new_status not in COUNSEL_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        if (new_status == CounselStatus.SUSPENDED and
                not reason.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": new_status.value, "at_utc": now_utc,
              "user": user, "reason": reason},))
        if new_status == CounselStatus.SUSPENDED:
            kwargs["suspension_reason"] = reason.strip()
        updated = Counsel(**kwargs)
        self._counsel[counsel_id] = updated
        return (TransitionOutcome.OK, updated)

    # Matter assignment
    def assign_matter(
        self, counsel_id: str, matter_id: str, title: str,
        scope_of_work: str, fee_arrangement: str,
        estimated_amount: Decimal, estimated_currency: str = "KES",
    ) -> Tuple[TransitionOutcome, Optional[MatterAssignment]]:
        if counsel_id not in self._counsel:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        if self._counsel[counsel_id].status != CounselStatus.ACTIVE:
            return (TransitionOutcome.REJECTED_COUNSEL_NOT_ACTIVE,
                    None)
        if estimated_amount <= Decimal("0"):
            raise ValueError("estimated_amount must be positive")
        aid = f"ASN-{self._next_assignment:06d}"
        self._next_assignment += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        assignment = MatterAssignment(
            assignment_id=aid, counsel_id=counsel_id,
            matter_id=matter_id, title=title.strip(),
            scope_of_work=scope_of_work.strip(),
            fee_arrangement=fee_arrangement.strip(),
            estimated_amount=estimated_amount,
            estimated_currency=estimated_currency,
            status=AssignmentStatus.ASSIGNED,
            assigned_at_utc=now_utc,
            transition_log=(
                {"to_status": "ASSIGNED", "at_utc": now_utc,
                 "user": "system",
                 "reason": "matter assigned to counsel"},))
        self._assignments[aid] = assignment
        return (TransitionOutcome.OK, assignment)

    def transition_assignment(
        self, assignment_id: str, new_status: AssignmentStatus,
        user: str, reason: str = "",
    ) -> Tuple[TransitionOutcome, Optional[MatterAssignment]]:
        if assignment_id not in self._assignments:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._assignments[assignment_id]
        if new_status not in ASSIGNMENT_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        if (new_status == AssignmentStatus.REJECTED and
                not reason.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": new_status.value, "at_utc": now_utc,
              "user": user, "reason": reason},))
        if new_status == AssignmentStatus.DELIVERED:
            kwargs["delivered_at_utc"] = now_utc
        updated = MatterAssignment(**kwargs)
        self._assignments[assignment_id] = updated
        return (TransitionOutcome.OK, updated)

    # Billing submission
    def submit_billing(
        self, counsel_id: str, assignment_id: str,
        invoice_number: str, period_start: str, period_end: str,
        lines: List[BillingLine],
    ) -> Tuple[TransitionOutcome, Optional[BillingSubmission]]:
        if counsel_id not in self._counsel:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        if assignment_id not in self._assignments:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        if not lines:
            raise ValueError("at least one billing line required")
        # Validate UTBMS codes
        for line in lines:
            if line.utbms_task_code not in UTBMS_CODES_LITIGATION:
                raise ValueError(
                    f"unknown UTBMS task code: "
                    f"{line.utbms_task_code}; valid codes are "
                    f"{sorted(UTBMS_CODES_LITIGATION.keys())[:5]}...")
        # Compute total
        total = sum(
            (l.amount for l in lines), Decimal("0"))
        currency = lines[0].currency
        for l in lines:
            if l.currency != currency:
                raise ValueError(
                    "all billing lines must be in the same currency; "
                    f"got {currency} and {l.currency}")
        sid = f"BIL-{self._next_submission:06d}"
        self._next_submission += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        submission = BillingSubmission(
            submission_id=sid, counsel_id=counsel_id,
            assignment_id=assignment_id,
            invoice_number=invoice_number.strip(),
            period_start=period_start, period_end=period_end,
            lines=tuple(lines), total_amount=total,
            currency=currency,
            status=BillingStatus.SUBMITTED,
            submitted_at_utc=now_utc,
            transition_log=(
                {"to_status": "SUBMITTED", "at_utc": now_utc,
                 "user": "counsel",
                 "reason": f"invoice {invoice_number} submitted"},))
        self._submissions[sid] = submission
        return (TransitionOutcome.OK, submission)

    def transition_billing(
        self, submission_id: str, new_status: BillingStatus,
        user: str, review_notes: str = "",
    ) -> Tuple[TransitionOutcome, Optional[BillingSubmission]]:
        if submission_id not in self._submissions:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._submissions[submission_id]
        if new_status not in BILLING_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        if (new_status in (BillingStatus.DISPUTED,
                             BillingStatus.REJECTED) and
                not review_notes.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": new_status.value, "at_utc": now_utc,
              "user": user, "reason": review_notes},))
        if review_notes.strip():
            kwargs["review_notes"] = review_notes.strip()
        updated = BillingSubmission(**kwargs)
        self._submissions[submission_id] = updated
        return (TransitionOutcome.OK, updated)

    # Queries
    def counsel_by_id(self, counsel_id: str) -> Counsel:
        if counsel_id not in self._counsel:
            raise KeyError(f"not found: {counsel_id}")
        return self._counsel[counsel_id]

    def all_counsel(self) -> Tuple[Counsel, ...]:
        return tuple(self._counsel.values())

    def active_counsel(self) -> Tuple[Counsel, ...]:
        return tuple(c for c in self._counsel.values()
                       if c.status == CounselStatus.ACTIVE)

    def assignments_for_counsel(
            self, counsel_id: str) -> Tuple[MatterAssignment, ...]:
        return tuple(a for a in self._assignments.values()
                       if a.counsel_id == counsel_id)

    def assignments_for_matter(
            self, matter_id: str) -> Tuple[MatterAssignment, ...]:
        return tuple(a for a in self._assignments.values()
                       if a.matter_id == matter_id)

    def submissions_for_counsel(
            self, counsel_id: str) -> Tuple[BillingSubmission, ...]:
        return tuple(s for s in self._submissions.values()
                       if s.counsel_id == counsel_id)

    def submissions_under_review(self) -> Tuple[BillingSubmission, ...]:
        return tuple(s for s in self._submissions.values()
                       if s.status in (BillingStatus.SUBMITTED,
                                         BillingStatus.UNDER_REVIEW,
                                         BillingStatus.DISPUTED))

    def board_summary(self) -> Dict[str, Any]:
        all_subs = list(self._submissions.values())
        approved_total: Dict[str, Decimal] = {}
        for s in all_subs:
            if s.status == BillingStatus.APPROVED:
                approved_total[s.currency] = (
                    approved_total.get(s.currency, Decimal("0"))
                    + s.total_amount)
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-224 OutsideCounselPortalEngine",
            "n_counsel_total": len(self._counsel),
            "n_counsel_active": len(self.active_counsel()),
            "n_assignments_total": len(self._assignments),
            "n_submissions_total": len(self._submissions),
            "n_submissions_under_review": len(
                self.submissions_under_review()),
            "approved_billing_totals_by_currency": {
                k: str(v) for k, v in approved_total.items()},
            "n_utbms_codes_supported": len(
                UTBMS_CODES_LITIGATION),
            "portal_ui_status": self.PORTAL_UI_STATUS,
            "authentication_status": self.AUTHENTICATION_STATUS,
            "ap_integration_status": self.AP_INTEGRATION_STATUS,
            "regulatory_basis": (
                "Advocates Act §35 (Kenya), CBK procurement + vendor "
                "management guidelines, internal cost control "
                "discipline per Companies Act §145"),
        }

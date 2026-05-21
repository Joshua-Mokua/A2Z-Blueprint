"""utils/compliance_training.py — ENH-197 Compliance Training
Management.

================================================================================
A2Z MIS 360 — ENH-197 Compliance Training Management Engine
================================================================================

LAST standard of the AML/Compliance cluster (9th of 9). After v10.168
ships ENH-197, v10.169 closes the cluster with G152 + G153 gates
(module cockpit + module API + admin Tier 4C marker — same pattern as
Treasury G150/G151).

Engine tracks compliance training assignments per role/employee,
course catalogues, completion records, expiry dates, certifications.
Wires into FFIEC examination Training module (currently DEFERRED in
ENH-199's ExaminerReportingEngine — operators will be able to wire it
post-v10.168).

REGULATORY ALIGNMENT
--------------------
- CBK Prudential Guideline CBK/PG/15 §7 — institution must train
  staff on AML/CFT obligations on a regular basis
- POCAMLA §47 — reporting institution must implement adequate
  training program for officers and employees
- FATF Recommendation 18 — internal control + audit + ongoing
  training functions
- FFIEC BSA/AML Examination Manual — Training pillar (the 5th
  pillar; institution must demonstrate ongoing training)

LIFECYCLE — Course
------------------

    DRAFT          (course created; not yet assignable)
        →  PUBLISHED  (assignable to employees)
            →  RETIRED  (no longer assignable; existing assignments
                         remain valid until they expire)

LIFECYCLE — Assignment
----------------------

    ASSIGNED       (course assigned to employee with due_date)
        →  COMPLETED       (employee finished + scored ≥ pass mark)
        →  FAILED          (employee did not score ≥ pass mark)
        →  WITHDRAWN       (assignment cancelled before completion)

Each completed assignment produces a CertificationRecord with
expiry_date = completed_at + validity_days. Recurring training (annual
AML refresher) needs new assignment after expiry.

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CourseStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class AssignmentStatus(str, Enum):
    ASSIGNED = "ASSIGNED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WITHDRAWN = "WITHDRAWN"


class CourseLifecycleOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"


class AssignmentOutcome(str, Enum):
    OK = "OK"
    REJECTED_COURSE_NOT_PUBLISHED = "REJECTED_COURSE_NOT_PUBLISHED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"
    REJECTED_ALREADY_TERMINAL = "REJECTED_ALREADY_TERMINAL"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"


# Allowed course lifecycle transitions
ALLOWED_COURSE_TRANSITIONS: Mapping[
        CourseStatus, Tuple[CourseStatus, ...]] = {
    CourseStatus.DRAFT: (CourseStatus.PUBLISHED, CourseStatus.RETIRED),
    CourseStatus.PUBLISHED: (CourseStatus.RETIRED,),
    CourseStatus.RETIRED: (),
}


DEFAULT_VALIDITY_DAYS = 365         # annual refresher cadence
DEFAULT_PASS_SCORE = 70             # percentage


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CertificationRecord:
    """Issued on COMPLETED assignment. Has an expiry_date computed
    from course.validity_days."""
    employee_id: str
    course_id: str
    course_version: str
    completed_at_utc: str
    expiry_date: str       # YYYY-MM-DD
    score: int             # percentage
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "course_id": self.course_id,
            "course_version": self.course_version,
            "completed_at_utc": self.completed_at_utc,
            "expiry_date": self.expiry_date,
            "score": self.score,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Course:
    """Compliance course definition."""
    course_id: str
    version: str
    title: str
    description: str
    owner_role: str               # who owns the course (e.g. "head_of_compliance")
    mandatory_for_roles: Tuple[str, ...]   # roles required to take this course
    validity_days: int             # certification validity post-completion
    pass_score: int                # 0-100
    status: CourseStatus
    related_policy_ids: Tuple[str, ...]    # links to ENH-196 policies
    related_regulatory_change_ids: Tuple[str, ...]   # links to ENH-195 changes
    registered_at_utc: str
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "course_id": self.course_id,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "owner_role": self.owner_role,
            "mandatory_for_roles": list(self.mandatory_for_roles),
            "validity_days": self.validity_days,
            "pass_score": self.pass_score,
            "status": self.status.value,
            "related_policy_ids": list(self.related_policy_ids),
            "related_regulatory_change_ids": list(
                self.related_regulatory_change_ids),
            "registered_at_utc": self.registered_at_utc,
            "transition_log": [dict(t) for t in self.transition_log],
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class Assignment:
    """Course assignment to an employee."""
    assignment_id: str
    course_id: str
    course_version: str
    employee_id: str
    employee_role: str
    due_date_utc: str
    status: AssignmentStatus
    assigned_at_utc: str
    completed_at_utc: str           # set when status=COMPLETED/FAILED
    score: int                      # set when terminal; -1 if not yet
    evidence: str
    withdrawal_reason: str
    certification: Optional[CertificationRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "course_id": self.course_id,
            "course_version": self.course_version,
            "employee_id": self.employee_id,
            "employee_role": self.employee_role,
            "due_date_utc": self.due_date_utc,
            "status": self.status.value,
            "assigned_at_utc": self.assigned_at_utc,
            "completed_at_utc": self.completed_at_utc,
            "score": self.score,
            "evidence": self.evidence,
            "withdrawal_reason": self.withdrawal_reason,
            "certification": (self.certification.to_dict()
                              if self.certification else None),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ComplianceTrainingEngine:
    """ENH-197 Compliance Training Management Engine.

    Two distinct entities tracked:
    1. Course (course_id, version) — course catalogue
    2. Assignment (assignment_id) — employee × course pairing

    Use:
        engine = ComplianceTrainingEngine()

        # Create + publish a course
        course = engine.register_course(
            course_id="CBT-AML-101", version="v2.0",
            title="AML Fundamentals — Annual Refresher",
            description="...",
            owner_role="head_of_compliance",
            mandatory_for_roles=("teller", "branch_manager",
                                  "compliance_officer"),
            validity_days=365,  # annual
            related_policy_ids=("POL-AML-001",))
        engine.publish_course(course.course_id, course.version,
                                user="head_of_compliance")

        # Assign + complete
        a = engine.assign(course_id, version, employee_id, role,
                          due_date_utc)
        engine.complete(a.assignment_id, score=85, evidence="...")
        # → Issues CertificationRecord with expiry_date 365d out
    """

    LMS_INTEGRATION_STATUS = (
        "DEFERRED — engine does NOT integrate with Learning "
        "Management Systems (Moodle, Cornerstone, Workday Learning, "
        "SuccessFactors). Operators record completions via "
        "complete() API. Future increment can wire LMS webhooks; "
        "out of scope for v10.168.")

    COURSE_CONTENT_STATUS = (
        "META_ONLY — engine tracks course metadata (title, "
        "description, validity, pass_score) and assignment lifecycle. "
        "Actual course content (videos, slides, quiz questions) is "
        "operator-side, hosted in an LMS or document repository. "
        "v10.168 ships meta-only.")

    def __init__(self) -> None:
        self._courses: Dict[Tuple[str, str], Course] = {}
        self._assignments: Dict[str, Assignment] = {}
        self._next_assignment_id = 1

    # ------------------------------------------------------------------
    # Course catalogue
    # ------------------------------------------------------------------

    def register_course(
        self,
        course_id: str,
        version: str,
        title: str,
        description: str,
        owner_role: str,
        mandatory_for_roles: Tuple[str, ...] = (),
        validity_days: int = DEFAULT_VALIDITY_DAYS,
        pass_score: int = DEFAULT_PASS_SCORE,
        related_policy_ids: Tuple[str, ...] = (),
        related_regulatory_change_ids: Tuple[str, ...] = (),
    ) -> Course:
        if not course_id.strip():
            raise ValueError("course_id required")
        if not version.strip():
            raise ValueError("version required")
        if not title.strip():
            raise ValueError("title required")
        if not owner_role.strip():
            raise ValueError("owner_role required")
        if validity_days < 1:
            raise ValueError("validity_days must be >= 1")
        if not (0 <= pass_score <= 100):
            raise ValueError(
                "pass_score must be 0-100 (percentage)")

        key = (course_id, version)
        if key in self._courses:
            raise ValueError(
                f"course version already registered: {course_id} "
                f"{version}")

        now_utc = datetime.now(timezone.utc).isoformat()
        course = Course(
            course_id=course_id, version=version,
            title=title.strip(), description=description.strip(),
            owner_role=owner_role.strip(),
            mandatory_for_roles=tuple(mandatory_for_roles),
            validity_days=validity_days, pass_score=pass_score,
            status=CourseStatus.DRAFT,
            related_policy_ids=tuple(related_policy_ids),
            related_regulatory_change_ids=tuple(
                related_regulatory_change_ids),
            registered_at_utc=now_utc,
            transition_log=(
                {"to_status": "DRAFT", "at_utc": now_utc,
                 "user": "system",
                 "reason": "initial registration"},),
            meta={"engine_version": "ENH-197-v10.168"},
        )
        self._courses[key] = course
        return course

    def transition_course(
        self,
        course_id: str,
        version: str,
        new_status: CourseStatus,
        user: str,
        reason: str = "",
    ) -> Tuple[CourseLifecycleOutcome, Optional[Course]]:
        key = (course_id, version)
        if key not in self._courses:
            return (CourseLifecycleOutcome.REJECTED_NOT_FOUND, None)
        current = self._courses[key]
        if new_status not in ALLOWED_COURSE_TRANSITIONS.get(
                current.status, ()):
            return (CourseLifecycleOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        new_log = {"to_status": new_status.value, "at_utc": now_utc,
                    "user": user, "reason": reason}
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = current.transition_log + (new_log,)
        updated = Course(**kwargs)
        self._courses[key] = updated
        return (CourseLifecycleOutcome.OK, updated)

    def publish_course(self, course_id: str, version: str,
                          user: str) -> Tuple[
            CourseLifecycleOutcome, Optional[Course]]:
        return self.transition_course(
            course_id, version, CourseStatus.PUBLISHED, user,
            reason="course content reviewed; ready for assignment")

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    def assign(
        self,
        course_id: str,
        version: str,
        employee_id: str,
        employee_role: str,
        due_date_utc: str,
    ) -> Tuple[AssignmentOutcome, Optional[Assignment]]:
        key = (course_id, version)
        if key not in self._courses:
            return (AssignmentOutcome.REJECTED_NOT_FOUND, None)
        course = self._courses[key]
        if course.status != CourseStatus.PUBLISHED:
            return (AssignmentOutcome.REJECTED_COURSE_NOT_PUBLISHED,
                    None)

        now_utc = datetime.now(timezone.utc).isoformat()
        assignment_id = f"ASN-{self._next_assignment_id:06d}"
        self._next_assignment_id += 1
        assignment = Assignment(
            assignment_id=assignment_id,
            course_id=course_id, course_version=version,
            employee_id=employee_id, employee_role=employee_role,
            due_date_utc=due_date_utc,
            status=AssignmentStatus.ASSIGNED,
            assigned_at_utc=now_utc,
            completed_at_utc="", score=-1, evidence="",
            withdrawal_reason="", certification=None,
        )
        self._assignments[assignment_id] = assignment
        return (AssignmentOutcome.OK, assignment)

    def complete(
        self,
        assignment_id: str,
        score: int,
        evidence: str,
    ) -> Tuple[AssignmentOutcome, Optional[Assignment]]:
        if assignment_id not in self._assignments:
            return (AssignmentOutcome.REJECTED_NOT_FOUND, None)
        current = self._assignments[assignment_id]
        if current.status != AssignmentStatus.ASSIGNED:
            return (AssignmentOutcome.REJECTED_ALREADY_TERMINAL,
                    current)
        if not evidence.strip():
            return (AssignmentOutcome.REJECTED_REASON_REQUIRED,
                    current)

        course_key = (current.course_id, current.course_version)
        course = self._courses[course_key]

        now_dt = datetime.now(timezone.utc)
        passed = score >= course.pass_score
        cert: Optional[CertificationRecord] = None
        if passed:
            expiry_dt = now_dt + timedelta(
                days=course.validity_days)
            cert = CertificationRecord(
                employee_id=current.employee_id,
                course_id=current.course_id,
                course_version=current.course_version,
                completed_at_utc=now_dt.isoformat(),
                expiry_date=expiry_dt.strftime("%Y-%m-%d"),
                score=score, evidence=evidence.strip())

        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = (AssignmentStatus.COMPLETED if passed
                              else AssignmentStatus.FAILED)
        kwargs["completed_at_utc"] = now_dt.isoformat()
        kwargs["score"] = score
        kwargs["evidence"] = evidence.strip()
        kwargs["certification"] = cert

        updated = Assignment(**kwargs)
        self._assignments[assignment_id] = updated
        return (AssignmentOutcome.OK, updated)

    def withdraw(
        self,
        assignment_id: str,
        reason: str,
    ) -> Tuple[AssignmentOutcome, Optional[Assignment]]:
        if assignment_id not in self._assignments:
            return (AssignmentOutcome.REJECTED_NOT_FOUND, None)
        current = self._assignments[assignment_id]
        if current.status != AssignmentStatus.ASSIGNED:
            return (AssignmentOutcome.REJECTED_ALREADY_TERMINAL,
                    current)
        if not reason.strip():
            return (AssignmentOutcome.REJECTED_REASON_REQUIRED,
                    current)

        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = AssignmentStatus.WITHDRAWN
        kwargs["withdrawal_reason"] = reason.strip()
        updated = Assignment(**kwargs)
        self._assignments[assignment_id] = updated
        return (AssignmentOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_courses(self) -> Tuple[Course, ...]:
        return tuple(self._courses.values())

    def published_courses(self) -> Tuple[Course, ...]:
        return tuple(c for c in self._courses.values()
                       if c.status == CourseStatus.PUBLISHED)

    def all_assignments(self) -> Tuple[Assignment, ...]:
        return tuple(self._assignments.values())

    def assignments_for_employee(
            self, employee_id: str) -> Tuple[Assignment, ...]:
        return tuple(a for a in self._assignments.values()
                       if a.employee_id == employee_id)

    def assignments_for_role(
            self, role: str) -> Tuple[Assignment, ...]:
        return tuple(a for a in self._assignments.values()
                       if a.employee_role == role)

    def overdue_assignments(self) -> Tuple[Assignment, ...]:
        """ASSIGNED assignments past their due_date."""
        now_utc = datetime.now(timezone.utc).isoformat()
        return tuple(
            a for a in self._assignments.values()
            if a.status == AssignmentStatus.ASSIGNED
            and a.due_date_utc < now_utc)

    def expiring_certifications(
            self, window_days: int = 30) -> Tuple[Assignment, ...]:
        """Certifications expiring within `window_days`."""
        cutoff_dt = datetime.now(timezone.utc) + timedelta(
            days=window_days)
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return tuple(
            a for a in self._assignments.values()
            if a.certification is not None
            and today_str <= a.certification.expiry_date <= cutoff_str)

    def courses_for_change(
            self, change_id: str) -> Tuple[Course, ...]:
        """Reverse-lookup: which courses link to this regulatory
        change? Completes ENH-195 ↔ ENH-197 linkage."""
        return tuple(
            c for c in self._courses.values()
            if change_id in c.related_regulatory_change_ids)

    def courses_for_policy(
            self, policy_id: str) -> Tuple[Course, ...]:
        """Reverse-lookup: which courses train on this policy?
        Completes ENH-196 ↔ ENH-197 linkage."""
        return tuple(
            c for c in self._courses.values()
            if policy_id in c.related_policy_ids)

    def board_summary(self) -> Dict[str, Any]:
        courses = list(self._courses.values())
        assignments = list(self._assignments.values())
        n_published = sum(1 for c in courses
                            if c.status == CourseStatus.PUBLISHED)
        n_completed = sum(
            1 for a in assignments
            if a.status == AssignmentStatus.COMPLETED)
        n_failed = sum(1 for a in assignments
                        if a.status == AssignmentStatus.FAILED)
        n_overdue = len(self.overdue_assignments())
        n_expiring = len(self.expiring_certifications(30))
        n_active_certs = sum(
            1 for a in assignments
            if a.certification is not None
            and a.certification.expiry_date >=
                datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-197 ComplianceTrainingEngine",
            "n_courses_total": len(courses),
            "n_courses_published": n_published,
            "n_assignments_total": len(assignments),
            "n_assignments_completed": n_completed,
            "n_assignments_failed": n_failed,
            "n_assignments_overdue": n_overdue,
            "n_certifications_expiring_30d": n_expiring,
            "n_active_certifications": n_active_certs,
            "lms_integration_status": self.LMS_INTEGRATION_STATUS,
            "course_content_status": self.COURSE_CONTENT_STATUS,
            "regulatory_basis": (
                "CBK PG/15 §7 (staff training), POCAMLA §47 (training "
                "program), FATF Recommendation 18 (ongoing training), "
                "FFIEC BSA/AML Examination Manual Training pillar"),
        }

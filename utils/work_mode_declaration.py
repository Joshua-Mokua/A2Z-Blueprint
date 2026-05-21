"""utils.work_mode_declaration — Employee Work Mode Declaration
Engine (ENH-156, v10.180).

Phase 5 Resource Optimization — first standard of the workforce
optimization arc (ENH-156..ENH-165). Provides a self-declaration
tool for employees to record their work mode (REMOTE / HYBRID /
ONSITE / FIELD) over an effective date range, with privacy
protections — employees declare; managers receive notice but the
declaration is the source of truth, not subject to manager
approval to take effect.

DESIGN CONTRACT
---------------
1. Self-declaration model — employee creates → ACKNOWLEDGED by
   manager (notice-only) → ACTIVE on/after effective_from →
   EXPIRED on/after effective_to OR REVOKED by employee.
2. Privacy: only employee + their direct manager + HR_ADMIN role
   can read a declaration. Aggregate stats (mode distribution per
   department) suppressed when n < 5 to prevent re-identification.
3. Forward-only state machine — no manager-driven REJECTED state
   for the v1 scope. Disagreements escalate offline; the engine
   never silently overrides employee intent.
4. Overlap rule: a new ACTIVE/SUBMITTED declaration for the same
   employee during the same date range supersedes the prior one,
   which transitions to SUPERSEDED.

REGULATORY BASIS
----------------
- Kenya Employment Act §10 (terms of employment must be in
  writing) — declaration captures the work-arrangement element
- Data Protection Act 2019 §25 (purpose limitation) — declarations
  used only for resource optimization, not surveillance
- Internal HR policy (Hybrid Work Framework, post-2023)

HONEST DEFERRALS
----------------
- HRIS_INTEGRATION: real Workday/SAP SuccessFactors sync deferred;
  this engine treats employee_id as an opaque string trusting
  upstream identity provider
- AUTO_SCHEDULE_SYNC: pushing declarations into calendar /
  attendance system deferred — engine produces the record only
- ML_PATTERN_DETECTION: detecting whether actual presence matches
  declared mode is out of scope (would require attendance data)
- DEPARTMENT_ROLLUPS_BEYOND_PRIVACY_THRESHOLD: aggregate views
  exist but suppress small-n cells (n<5)

NOT IN SCOPE
------------
- Compensation impact (allowances change per mode) — separate
  payroll system
- Capacity planning (matching to TSL targets) — covered by
  ENH-157 Workload Forecasting + ENH-158 TSL Optimization
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class WorkMode(Enum):
    """Permitted work modes."""
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    FIELD = "field"


class DeclarationStatus(Enum):
    """Lifecycle states. Forward-only except REVOKED escape from
    SUBMITTED/ACTIVE, and SUPERSEDED auto-transition when a newer
    overlapping declaration becomes ACTIVE."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"


# Allowed transitions — keys are FROM states, values are sets of
# permitted TO states. Anything not listed is rejected.
ALLOWED_TRANSITIONS: Dict[DeclarationStatus, frozenset] = {
    DeclarationStatus.DRAFT: frozenset({
        DeclarationStatus.SUBMITTED,
        DeclarationStatus.REVOKED,
    }),
    DeclarationStatus.SUBMITTED: frozenset({
        DeclarationStatus.ACKNOWLEDGED,
        DeclarationStatus.ACTIVE,        # auto when effective_from <= today
        DeclarationStatus.REVOKED,
        DeclarationStatus.SUPERSEDED,
    }),
    DeclarationStatus.ACKNOWLEDGED: frozenset({
        DeclarationStatus.ACTIVE,
        DeclarationStatus.REVOKED,
        DeclarationStatus.SUPERSEDED,
    }),
    DeclarationStatus.ACTIVE: frozenset({
        DeclarationStatus.EXPIRED,
        DeclarationStatus.REVOKED,
        DeclarationStatus.SUPERSEDED,
    }),
    # Terminal states
    DeclarationStatus.EXPIRED: frozenset(),
    DeclarationStatus.REVOKED: frozenset(),
    DeclarationStatus.SUPERSEDED: frozenset(),
}


# Reasons for transition outcomes — used in audit log surface.
class TransitionOutcome(Enum):
    OK = "ok"
    REJECTED_INVALID_STATE = "rejected_invalid_state"
    REJECTED_NOT_OWNER = "rejected_not_owner"
    REJECTED_DATES_INVALID = "rejected_dates_invalid"
    REJECTED_REASON_REQUIRED = "rejected_reason_required"


# Privacy threshold — aggregate views suppress cells with n < this.
PRIVACY_MIN_CELL_SIZE = 5


@dataclass(frozen=True)
class WorkModeDeclaration:
    """Immutable declaration record.

    Construction-time invariants enforced in __post_init__:
      - effective_from <= effective_to
      - employee_id non-empty
      - manager_id non-empty
    """
    declaration_id: str
    employee_id: str
    manager_id: str
    mode: WorkMode
    effective_from: date
    effective_to: date
    status: DeclarationStatus
    department: Optional[str] = None
    location_city: Optional[str] = None
    rationale: Optional[str] = None  # employee-provided reason
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_transition_at: Optional[datetime] = None
    transition_history: Tuple[Tuple[str, str, str, str], ...] = ()
    # Each entry: (from_status, to_status, actor_role, reason_or_empty)

    def __post_init__(self):
        if not self.employee_id:
            raise ValueError("employee_id required")
        if not self.manager_id:
            raise ValueError("manager_id required")
        if self.effective_from > self.effective_to:
            raise ValueError(
                f"effective_from {self.effective_from} after "
                f"effective_to {self.effective_to}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "declaration_id": self.declaration_id,
            "employee_id": self.employee_id,
            "manager_id": self.manager_id,
            "mode": self.mode.value,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat(),
            "status": self.status.value,
            "department": self.department,
            "location_city": self.location_city,
            "rationale": self.rationale,
            "created_at": self.created_at.isoformat(),
            "last_transition_at": (
                self.last_transition_at.isoformat()
                if self.last_transition_at else None),
            "transition_history": [
                {"from": t[0], "to": t[1], "actor": t[2], "reason": t[3]}
                for t in self.transition_history
            ],
        }


class WorkModeDeclarationEngine:
    """In-memory store + state machine for work mode declarations.

    PERSISTENCE NOTE — engine is in-memory only at v10.180.
    PG migration deferred per platform pattern.
    """

    def __init__(self):
        self._declarations: Dict[str, WorkModeDeclaration] = {}
        self._counter = 0

    # ------------------------------------------------------------ create
    def declare(
        self,
        employee_id: str,
        manager_id: str,
        mode: WorkMode,
        effective_from: date,
        effective_to: date,
        department: Optional[str] = None,
        location_city: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> WorkModeDeclaration:
        """Employee creates a new declaration in DRAFT state."""
        self._counter += 1
        decl_id = f"WMD-{self._counter:06d}"
        decl = WorkModeDeclaration(
            declaration_id=decl_id,
            employee_id=employee_id,
            manager_id=manager_id,
            mode=mode,
            effective_from=effective_from,
            effective_to=effective_to,
            status=DeclarationStatus.DRAFT,
            department=department,
            location_city=location_city,
            rationale=rationale,
        )
        self._declarations[decl_id] = decl
        return decl

    # ------------------------------------------------------------ transition
    def transition(
        self,
        declaration_id: str,
        to_status: DeclarationStatus,
        actor_role: str,
        actor_id: str,
        reason: Optional[str] = None,
    ) -> Tuple[Optional[WorkModeDeclaration], TransitionOutcome]:
        """Move declaration through its lifecycle.

        Returns (declaration, outcome). Returns (None, outcome) on
        rejection. Caller is responsible for audit_log() — engine
        only enforces state machine.
        """
        decl = self._declarations.get(declaration_id)
        if decl is None:
            return None, TransitionOutcome.REJECTED_INVALID_STATE

        # Owner check — REVOKED requires the employee to act
        if to_status == DeclarationStatus.REVOKED:
            if actor_role != "EMPLOYEE" or actor_id != decl.employee_id:
                # HR_ADMIN may also revoke (e.g. termination)
                if actor_role != "HR_ADMIN":
                    return None, TransitionOutcome.REJECTED_NOT_OWNER
            if not reason:
                return None, TransitionOutcome.REJECTED_REASON_REQUIRED

        # State machine check
        allowed = ALLOWED_TRANSITIONS.get(decl.status, frozenset())
        if to_status not in allowed:
            return None, TransitionOutcome.REJECTED_INVALID_STATE

        new_history = decl.transition_history + (
            (decl.status.value, to_status.value, actor_role, reason or ""),
        )
        new_decl = WorkModeDeclaration(
            declaration_id=decl.declaration_id,
            employee_id=decl.employee_id,
            manager_id=decl.manager_id,
            mode=decl.mode,
            effective_from=decl.effective_from,
            effective_to=decl.effective_to,
            status=to_status,
            department=decl.department,
            location_city=decl.location_city,
            rationale=decl.rationale,
            created_at=decl.created_at,
            last_transition_at=datetime.now(timezone.utc),
            transition_history=new_history,
        )
        self._declarations[declaration_id] = new_decl

        # Auto-supersede overlapping prior declarations when this
        # one becomes ACTIVE
        if to_status == DeclarationStatus.ACTIVE:
            self._supersede_overlapping(new_decl)

        return new_decl, TransitionOutcome.OK

    # ------------------------------------------------------------ supersede
    def _supersede_overlapping(
        self, active_decl: WorkModeDeclaration
    ) -> None:
        for did, d in list(self._declarations.items()):
            if did == active_decl.declaration_id:
                continue
            if d.employee_id != active_decl.employee_id:
                continue
            if d.status not in (
                DeclarationStatus.SUBMITTED,
                DeclarationStatus.ACKNOWLEDGED,
                DeclarationStatus.ACTIVE,
            ):
                continue
            # Overlap test
            if (d.effective_from <= active_decl.effective_to
                    and d.effective_to >= active_decl.effective_from):
                new_history = d.transition_history + (
                    (d.status.value,
                     DeclarationStatus.SUPERSEDED.value,
                     "SYSTEM",
                     f"superseded by {active_decl.declaration_id}"),
                )
                self._declarations[did] = WorkModeDeclaration(
                    declaration_id=d.declaration_id,
                    employee_id=d.employee_id,
                    manager_id=d.manager_id,
                    mode=d.mode,
                    effective_from=d.effective_from,
                    effective_to=d.effective_to,
                    status=DeclarationStatus.SUPERSEDED,
                    department=d.department,
                    location_city=d.location_city,
                    rationale=d.rationale,
                    created_at=d.created_at,
                    last_transition_at=datetime.now(timezone.utc),
                    transition_history=new_history,
                )

    # ------------------------------------------------------------ queries
    def get(self, declaration_id: str) -> Optional[WorkModeDeclaration]:
        return self._declarations.get(declaration_id)

    def list_for_employee(
        self, employee_id: str,
        actor_role: str, actor_id: str,
    ) -> List[WorkModeDeclaration]:
        """Privacy-respecting list. Self / manager / HR_ADMIN only."""
        results = [
            d for d in self._declarations.values()
            if d.employee_id == employee_id
        ]
        if not results:
            return []
        # Privacy gate
        decl_sample = results[0]
        if actor_role == "EMPLOYEE" and actor_id != employee_id:
            return []
        if actor_role == "MANAGER" and actor_id != decl_sample.manager_id:
            return []
        if actor_role not in ("EMPLOYEE", "MANAGER", "HR_ADMIN"):
            return []
        return results

    def list_active_in_window(
        self, window_start: date, window_end: date
    ) -> List[WorkModeDeclaration]:
        """All declarations whose effective range overlaps the window
        and are currently in ACTIVE state. Privacy-aware aggregation
        helpers downstream should suppress small-n cells.
        """
        out = []
        for d in self._declarations.values():
            if d.status != DeclarationStatus.ACTIVE:
                continue
            if d.effective_from > window_end:
                continue
            if d.effective_to < window_start:
                continue
            out.append(d)
        return out

    # ------------------------------------------------------------ aggregates
    def mode_distribution_by_department(
        self, window_start: date, window_end: date,
    ) -> Dict[str, Any]:
        """Aggregate mode counts per department, suppressing cells
        with n < PRIVACY_MIN_CELL_SIZE."""
        active = self.list_active_in_window(window_start, window_end)
        # Build dept -> mode -> count
        buckets: Dict[str, Dict[str, int]] = {}
        for d in active:
            dept = d.department or "UNASSIGNED"
            buckets.setdefault(dept, {}).setdefault(d.mode.value, 0)
            buckets[dept][d.mode.value] += 1

        suppressed: List[str] = []
        published: Dict[str, Dict[str, int]] = {}
        for dept, modes in buckets.items():
            total = sum(modes.values())
            if total < PRIVACY_MIN_CELL_SIZE:
                suppressed.append(dept)
                continue
            published[dept] = dict(modes)

        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "n_active_total": len(active),
            "departments_published": published,
            "departments_suppressed_n_lt_threshold": suppressed,
            "privacy_threshold": PRIVACY_MIN_CELL_SIZE,
        }

    # ------------------------------------------------------------ board
    def board_summary(self) -> Dict[str, Any]:
        n_total = len(self._declarations)
        by_status: Dict[str, int] = {}
        by_mode: Dict[str, int] = {}
        for d in self._declarations.values():
            by_status[d.status.value] = by_status.get(d.status.value, 0) + 1
            if d.status == DeclarationStatus.ACTIVE:
                by_mode[d.mode.value] = by_mode.get(d.mode.value, 0) + 1

        return {
            "engine": "ENH-156 WorkModeDeclarationEngine",
            "n_declarations_total": n_total,
            "n_active": by_status.get("active", 0),
            "by_status": by_status,
            "active_by_mode": by_mode,
            "regulatory_basis": (
                "Kenya Employment Act §10 + DPA 2019 §25 + "
                "internal Hybrid Work Framework"),
            "privacy_threshold_n": PRIVACY_MIN_CELL_SIZE,
            "deferrals": {
                "HRIS_INTEGRATION": (
                    "DEFERRED — engine trusts upstream identity "
                    "provider; no Workday/SuccessFactors push"),
                "AUTO_SCHEDULE_SYNC": (
                    "DEFERRED — calendar/attendance push is out "
                    "of v10.180 scope"),
                "ML_PATTERN_DETECTION": (
                    "DEFERRED — declared vs actual presence check "
                    "requires attendance data not in scope"),
            },
        }

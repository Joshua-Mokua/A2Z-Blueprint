"""utils/obligation_tracking.py — ENH-222 Obligation & Renewal Tracking.

================================================================================
A2Z MIS 360 — ENH-222 Obligation & Renewal Tracking Engine (Legal Arc)
================================================================================

First greenfield engine of the Legal arc (ENH-222..230). Tracks contract
obligations + renewal dates with T-90/60/30/7 alert thresholds and
ownership + escalation paths.

REGULATORY ALIGNMENT
--------------------
- Companies Act §145 — director responsibility for contract performance
- CBK Risk Management Guidelines — operational risk from contract breach
- Kenya Contracts Act — notice periods + obligation discharge

LIFECYCLE
---------
    ACTIVE         (obligation in force)
        →  COMPLETED       (obligation discharged on time)
        →  BREACHED        (obligation passed deadline without discharge)
        →  CANCELLED       (contract cancelled before deadline)

Alert thresholds applied to ACTIVE obligations approaching deadline:
    T-90: ALERT_NOTICE      (long-lead notice; renewal planning)
    T-60: ALERT_PLANNING    (action plan required)
    T-30: ALERT_ACTION      (operator action required)
    T-7:  ALERT_CRITICAL    (deadline imminent)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta, date
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ObligationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BREACHED = "BREACHED"
    CANCELLED = "CANCELLED"


class ObligationKind(str, Enum):
    CONTRACT_RENEWAL = "CONTRACT_RENEWAL"
    PAYMENT_DUE = "PAYMENT_DUE"
    DELIVERABLE = "DELIVERABLE"
    NOTICE_PERIOD = "NOTICE_PERIOD"
    REGULATORY_FILING = "REGULATORY_FILING"
    OTHER = "OTHER"


class AlertLevel(str, Enum):
    NONE = "NONE"
    NOTICE = "NOTICE"          # T-90
    PLANNING = "PLANNING"      # T-60
    ACTION = "ACTION"           # T-30
    CRITICAL = "CRITICAL"       # T-7
    BREACHED = "BREACHED"       # past deadline


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"


ALLOWED_TRANSITIONS: Mapping[
        ObligationStatus, Tuple[ObligationStatus, ...]] = {
    ObligationStatus.ACTIVE: (
        ObligationStatus.COMPLETED, ObligationStatus.BREACHED,
        ObligationStatus.CANCELLED),
    ObligationStatus.COMPLETED: (),
    ObligationStatus.BREACHED: (),
    ObligationStatus.CANCELLED: (),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    contract_id: str             # parent contract reference
    counterparty: str
    title: str
    description: str
    kind: ObligationKind
    deadline_date: str           # YYYY-MM-DD
    notice_period_days: int      # contractual notice period
    owner_role: str              # accountable role
    escalation_role: str         # who's escalated to if breached
    status: ObligationStatus
    registered_at_utc: str
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    discharge_evidence: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "contract_id": self.contract_id,
            "counterparty": self.counterparty,
            "title": self.title,
            "description": self.description,
            "kind": self.kind.value,
            "deadline_date": self.deadline_date,
            "notice_period_days": self.notice_period_days,
            "owner_role": self.owner_role,
            "escalation_role": self.escalation_role,
            "status": self.status.value,
            "registered_at_utc": self.registered_at_utc,
            "transition_log": [dict(t) for t in self.transition_log],
            "discharge_evidence": self.discharge_evidence,
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ObligationTrackingEngine:
    """ENH-222 Obligation & Renewal Tracking Engine."""

    AUTOMATED_ALERTING_STATUS = (
        "DEFERRED — engine computes alert_level for each obligation "
        "based on days-to-deadline, but actual notification dispatch "
        "(email, SMS, Slack) is operator-side. v10.170 ships alert "
        "computation; notification wiring is future increment.")

    CONTRACT_TEXT_INTEGRATION_STATUS = (
        "META_ONLY — engine tracks obligation metadata + parent "
        "contract_id reference. Actual contract text storage + "
        "clause-level extraction is operator-side via existing "
        "utils/document_management.py + ENH-221 AI-powered contract "
        "review. v10.170 references contract_id; full integration "
        "with contract_review engine is future work.")

    def __init__(self) -> None:
        self._obligations: Dict[str, Obligation] = {}
        self._next_id = 1

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    def register_obligation(
        self,
        contract_id: str,
        counterparty: str,
        title: str,
        description: str,
        kind: ObligationKind,
        deadline_date: str,
        owner_role: str,
        escalation_role: str = "",
        notice_period_days: int = 0,
    ) -> Obligation:
        if not contract_id.strip():
            raise ValueError("contract_id required")
        if not title.strip():
            raise ValueError("title required")
        if not deadline_date.strip():
            raise ValueError("deadline_date required (YYYY-MM-DD)")
        if not owner_role.strip():
            raise ValueError(
                "owner_role required — every obligation needs a "
                "named accountable owner")
        # Validate date format
        try:
            datetime.strptime(deadline_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                f"deadline_date must be YYYY-MM-DD, got "
                f"{deadline_date!r}")

        obligation_id = f"OBL-{self._next_id:06d}"
        self._next_id += 1
        now_utc = datetime.now(timezone.utc).isoformat()

        obligation = Obligation(
            obligation_id=obligation_id,
            contract_id=contract_id.strip(),
            counterparty=counterparty.strip(),
            title=title.strip(), description=description.strip(),
            kind=kind, deadline_date=deadline_date,
            notice_period_days=notice_period_days,
            owner_role=owner_role.strip(),
            escalation_role=escalation_role.strip(),
            status=ObligationStatus.ACTIVE,
            registered_at_utc=now_utc,
            transition_log=(
                {"to_status": "ACTIVE", "at_utc": now_utc,
                 "user": "system",
                 "reason": "initial registration"},),
            meta={"engine_version": "ENH-222-v10.170"},
        )
        self._obligations[obligation_id] = obligation
        return obligation

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def transition(
        self,
        obligation_id: str,
        new_status: ObligationStatus,
        user: str,
        reason: str = "",
        discharge_evidence: str = "",
    ) -> Tuple[TransitionOutcome, Optional[Obligation]]:
        if obligation_id not in self._obligations:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._obligations[obligation_id]
        if new_status not in ALLOWED_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        # COMPLETED needs discharge_evidence
        if (new_status == ObligationStatus.COMPLETED and
                not discharge_evidence.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        # CANCELLED + BREACHED need reason
        if (new_status in (ObligationStatus.CANCELLED,
                             ObligationStatus.BREACHED) and
                not reason.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)

        now_utc = datetime.now(timezone.utc).isoformat()
        new_log = {"to_status": new_status.value, "at_utc": now_utc,
                    "user": user, "reason": reason}
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = current.transition_log + (new_log,)
        if new_status == ObligationStatus.COMPLETED:
            kwargs["discharge_evidence"] = discharge_evidence.strip()
        updated = Obligation(**kwargs)
        self._obligations[obligation_id] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Alert computation
    # ------------------------------------------------------------------

    def alert_level(self, obligation: Obligation,
                      as_of_date: Optional[str] = None) -> AlertLevel:
        """Compute alert level for an obligation based on
        days-to-deadline. Only ACTIVE obligations get alerts."""
        if obligation.status != ObligationStatus.ACTIVE:
            return AlertLevel.NONE
        if as_of_date is None:
            as_of_date = datetime.now(
                timezone.utc).strftime("%Y-%m-%d")
        try:
            deadline = datetime.strptime(
                obligation.deadline_date, "%Y-%m-%d").date()
            today = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        except ValueError:
            return AlertLevel.NONE
        delta_days = (deadline - today).days
        if delta_days < 0:
            return AlertLevel.BREACHED
        if delta_days <= 7:
            return AlertLevel.CRITICAL
        if delta_days <= 30:
            return AlertLevel.ACTION
        if delta_days <= 60:
            return AlertLevel.PLANNING
        if delta_days <= 90:
            return AlertLevel.NOTICE
        return AlertLevel.NONE

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def all_obligations(self) -> Tuple[Obligation, ...]:
        return tuple(self._obligations.values())

    def obligation_by_id(self, obligation_id: str) -> Obligation:
        if obligation_id not in self._obligations:
            raise KeyError(f"not found: {obligation_id}")
        return self._obligations[obligation_id]

    def obligations_by_alert_level(
            self, level: AlertLevel) -> Tuple[Obligation, ...]:
        return tuple(
            o for o in self._obligations.values()
            if self.alert_level(o) == level)

    def overdue_breaches(self) -> Tuple[Obligation, ...]:
        """ACTIVE obligations whose deadline has passed."""
        return self.obligations_by_alert_level(AlertLevel.BREACHED)

    def critical_alerts(self) -> Tuple[Obligation, ...]:
        return self.obligations_by_alert_level(AlertLevel.CRITICAL)

    def obligations_for_contract(
            self, contract_id: str) -> Tuple[Obligation, ...]:
        return tuple(
            o for o in self._obligations.values()
            if o.contract_id == contract_id)

    def board_summary(self) -> Dict[str, Any]:
        obs = list(self._obligations.values())
        n_total = len(obs)
        n_active = sum(1 for o in obs
                        if o.status == ObligationStatus.ACTIVE)
        n_breached = sum(1 for o in obs
                          if o.status == ObligationStatus.BREACHED)
        n_completed = sum(1 for o in obs
                            if o.status == ObligationStatus.COMPLETED)
        # Alert distribution among ACTIVE
        alert_counts: Dict[str, int] = {}
        for o in obs:
            level = self.alert_level(o)
            alert_counts[level.value] = (
                alert_counts.get(level.value, 0) + 1)
        kind_counts: Dict[str, int] = {}
        for o in obs:
            kind_counts[o.kind.value] = (
                kind_counts.get(o.kind.value, 0) + 1)

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-222 ObligationTrackingEngine",
            "n_obligations_total": n_total,
            "n_active": n_active,
            "n_breached": n_breached,
            "n_completed": n_completed,
            "alert_counts": alert_counts,
            "kind_counts": kind_counts,
            "automated_alerting_status": (
                self.AUTOMATED_ALERTING_STATUS),
            "contract_text_integration_status": (
                self.CONTRACT_TEXT_INTEGRATION_STATUS),
            "regulatory_basis": (
                "Companies Act §145 (director responsibility), CBK "
                "Risk Management Guidelines (operational risk from "
                "contract breach), Kenya Contracts Act (notice "
                "periods + obligation discharge)"),
        }

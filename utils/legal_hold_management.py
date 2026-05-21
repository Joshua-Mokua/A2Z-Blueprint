"""utils/legal_hold_management.py — ENH-227 Legal Hold Management.

Sixth Legal arc engine. Litigation hold notices, custodian
acknowledgment tracking, document preservation enforcement, release
workflow when hold lifted.

A legal hold is issued when a bank reasonably anticipates litigation
or regulatory action. It freezes destruction of relevant documents
and obligates named custodians to preserve materials. Failure to
preserve can result in spoliation sanctions or adverse inference at
trial.

DESIGN
------
Two-entity engine: Hold (the formal preservation directive with
scope and trigger event) and CustodianAcknowledgment (per-custodian
receipt + acknowledgment of obligations).

LIFECYCLE — Hold
    DRAFT → ISSUED → ACKNOWLEDGED → RELEASED
    (REVOKED is escape from any pre-RELEASED state if the trigger
     event resolves without litigation)

LIFECYCLE — CustodianAcknowledgment
    PENDING → ACKNOWLEDGED → ESCALATED (if pending past deadline)

REGULATORY ALIGNMENT
- Kenya Civil Procedure Rules — duty to preserve evidence
- CBK Risk Management Guidelines — operational risk from spoliation
- Companies Act §145 — director duty re material litigation
- Common-law spoliation doctrine — adverse inference for failure to
  preserve

HONEST DEFERRALS
- AUTOMATED_PRESERVATION_HOLDS DEFERRED — engine ships notice +
  acknowledgment ledger; actual technical hold on document stores
  (M365 retention labels, Box, network share locks) is operator-
  side via IT/IS coordination
- ESCALATION_NOTIFICATION DEFERRED — engine flags non-acknowledged
  custodians past deadline; actual escalation dispatch (email to
  manager + HR) operator-side
- CHAIN_OF_CUSTODY_AUDIT META_ONLY — engine tracks acknowledgment
  events; full chain-of-custody ledger for produced documents
  (timestamps, accessors, copies made) is operator-side
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


class HoldStatus(str, Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ACKNOWLEDGED = "ACKNOWLEDGED"   # all custodians acknowledged
    RELEASED = "RELEASED"
    REVOKED = "REVOKED"


class AcknowledgmentStatus(str, Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATED = "ESCALATED"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"
    REJECTED_NOT_ALL_ACKNOWLEDGED = "REJECTED_NOT_ALL_ACKNOWLEDGED"


HOLD_TRANSITIONS: Mapping[HoldStatus, Tuple[HoldStatus, ...]] = {
    HoldStatus.DRAFT: (HoldStatus.ISSUED, HoldStatus.REVOKED),
    HoldStatus.ISSUED: (HoldStatus.ACKNOWLEDGED, HoldStatus.RELEASED,
                          HoldStatus.REVOKED),
    HoldStatus.ACKNOWLEDGED: (HoldStatus.RELEASED,
                                  HoldStatus.REVOKED),
    HoldStatus.RELEASED: (),
    HoldStatus.REVOKED: (),
}


@dataclass(frozen=True)
class CustodianAcknowledgment:
    acknowledgment_id: str
    hold_id: str
    custodian_employee_id: str
    custodian_name: str
    custodian_role: str
    issued_at_utc: str
    acknowledgment_deadline: str    # YYYY-MM-DD
    status: AcknowledgmentStatus
    acknowledged_at_utc: str = ""
    escalated_at_utc: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"acknowledgment_id": self.acknowledgment_id,
                "hold_id": self.hold_id,
                "custodian_employee_id": self.custodian_employee_id,
                "custodian_name": self.custodian_name,
                "custodian_role": self.custodian_role,
                "issued_at_utc": self.issued_at_utc,
                "acknowledgment_deadline": (
                    self.acknowledgment_deadline),
                "status": self.status.value,
                "acknowledged_at_utc": self.acknowledged_at_utc,
                "escalated_at_utc": self.escalated_at_utc,
                "notes": self.notes}


@dataclass(frozen=True)
class Hold:
    hold_id: str
    matter_reference: str         # e.g. CASE-000001 or "Anticipated CBK Inquiry"
    title: str
    trigger_event: str            # what created the duty to preserve
    scope_description: str        # what documents are covered
    document_categories: Tuple[str, ...]   # e.g. emails, contracts, KYC
    date_range_start: str          # YYYY-MM-DD
    date_range_end: str            # may be empty if open-ended
    issuer_role: str
    issued_at_utc: str
    status: HoldStatus
    custodian_ids: Tuple[str, ...] = ()
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    release_reason: str = ""
    release_at_utc: str = ""
    revocation_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"hold_id": self.hold_id,
                "matter_reference": self.matter_reference,
                "title": self.title,
                "trigger_event": self.trigger_event,
                "scope_description": self.scope_description,
                "document_categories": list(self.document_categories),
                "date_range_start": self.date_range_start,
                "date_range_end": self.date_range_end,
                "issuer_role": self.issuer_role,
                "issued_at_utc": self.issued_at_utc,
                "status": self.status.value,
                "custodian_ids": list(self.custodian_ids),
                "transition_log": [dict(t)
                                     for t in self.transition_log],
                "release_reason": self.release_reason,
                "release_at_utc": self.release_at_utc,
                "revocation_reason": self.revocation_reason}


class LegalHoldManagementEngine:
    """ENH-227 Legal Hold Management Engine."""

    AUTOMATED_PRESERVATION_HOLDS_STATUS = (
        "DEFERRED — engine ships notice + acknowledgment ledger; "
        "actual technical hold on document stores (M365 retention "
        "labels, Box, network share locks, FLEXCUBE archive locks) "
        "is operator-side via IT/IS coordination. v10.175 ships "
        "human-process orchestration; technical wiring future "
        "increment.")

    ESCALATION_NOTIFICATION_STATUS = (
        "DEFERRED — engine flags non-acknowledged custodians past "
        "deadline via mark_escalated(); actual escalation dispatch "
        "(email to manager + HR) is operator-side. Engine surfaces "
        "the watch list; notification wiring future work.")

    CHAIN_OF_CUSTODY_AUDIT_STATUS = (
        "META_ONLY — engine tracks hold + acknowledgment events; "
        "full chain-of-custody ledger for produced documents "
        "(timestamps, accessors, copies made, hashes) is operator-"
        "side. Engine surfaces hold scope; actual document chain-of-"
        "custody is a separate operator-side process.")

    DEFAULT_ACK_DEADLINE_DAYS = 7

    def __init__(self) -> None:
        self._holds: Dict[str, Hold] = {}
        self._acks: Dict[str, CustodianAcknowledgment] = {}
        self._next_hold = 1
        self._next_ack = 1

    # ------------------------------------------------------------------
    # Hold creation
    # ------------------------------------------------------------------

    def create_hold(
        self, matter_reference: str, title: str,
        trigger_event: str, scope_description: str,
        document_categories: Tuple[str, ...],
        date_range_start: str, date_range_end: str,
        issuer_role: str,
    ) -> Hold:
        if not title.strip():
            raise ValueError("title required")
        if not trigger_event.strip():
            raise ValueError(
                "trigger_event required — every hold must specify "
                "the event creating the preservation duty")
        if not document_categories:
            raise ValueError(
                "document_categories required — at least one category "
                "must be specified for scope clarity")
        try:
            datetime.strptime(date_range_start, "%Y-%m-%d")
            if date_range_end.strip():
                datetime.strptime(date_range_end, "%Y-%m-%d")
        except ValueError:
            raise ValueError(
                "date_range_start/end must be YYYY-MM-DD")
        hid = f"HLD-{self._next_hold:06d}"
        self._next_hold += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        hold = Hold(
            hold_id=hid, matter_reference=matter_reference.strip(),
            title=title.strip(),
            trigger_event=trigger_event.strip(),
            scope_description=scope_description.strip(),
            document_categories=tuple(document_categories),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            issuer_role=issuer_role.strip(),
            issued_at_utc=now_utc,
            status=HoldStatus.DRAFT,
            transition_log=(
                {"to_status": "DRAFT", "at_utc": now_utc,
                 "user": issuer_role,
                 "reason": "hold drafted"},))
        self._holds[hid] = hold
        return hold

    # ------------------------------------------------------------------
    # Add custodians + issue
    # ------------------------------------------------------------------

    def add_custodian(
        self, hold_id: str, employee_id: str, name: str,
        role: str, ack_deadline_days: int = DEFAULT_ACK_DEADLINE_DAYS,
    ) -> CustodianAcknowledgment:
        """Add a custodian to a DRAFT or ISSUED hold."""
        if hold_id not in self._holds:
            raise KeyError(f"not found: {hold_id}")
        hold = self._holds[hold_id]
        if hold.status not in (HoldStatus.DRAFT, HoldStatus.ISSUED):
            raise ValueError(
                f"cannot add custodian to hold in status "
                f"{hold.status.value}")
        # idempotent: don't duplicate
        for ack in self._acks.values():
            if (ack.hold_id == hold_id and
                    ack.custodian_employee_id == employee_id):
                return ack
        aid = f"ACK-{self._next_ack:06d}"
        self._next_ack += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        deadline = (datetime.now(timezone.utc) +
                       timedelta(days=ack_deadline_days)).strftime(
                           "%Y-%m-%d")
        ack = CustodianAcknowledgment(
            acknowledgment_id=aid, hold_id=hold_id,
            custodian_employee_id=employee_id.strip(),
            custodian_name=name.strip(), custodian_role=role.strip(),
            issued_at_utc=now_utc,
            acknowledgment_deadline=deadline,
            status=AcknowledgmentStatus.PENDING)
        self._acks[aid] = ack
        # Add to hold's custodian_ids list
        kwargs = {f: getattr(hold, f)
                    for f in hold.__dataclass_fields__}
        if employee_id not in hold.custodian_ids:
            kwargs["custodian_ids"] = (
                hold.custodian_ids + (employee_id,))
        self._holds[hold_id] = Hold(**kwargs)
        return ack

    def transition_hold(
        self, hold_id: str, new_status: HoldStatus,
        user: str, reason: str = "",
    ) -> Tuple[TransitionOutcome, Optional[Hold]]:
        if hold_id not in self._holds:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._holds[hold_id]
        if new_status not in HOLD_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        # ISSUED requires at least one custodian
        if (new_status == HoldStatus.ISSUED and
                not current.custodian_ids):
            return (
                TransitionOutcome.REJECTED_INVALID_TRANSITION,
                current)
        # ACKNOWLEDGED requires all custodians acknowledged
        if new_status == HoldStatus.ACKNOWLEDGED:
            acks = [a for a in self._acks.values()
                     if a.hold_id == hold_id]
            if not acks:
                return (
                    TransitionOutcome.REJECTED_NOT_ALL_ACKNOWLEDGED,
                    current)
            if any(a.status != AcknowledgmentStatus.ACKNOWLEDGED
                    for a in acks):
                return (
                    TransitionOutcome.REJECTED_NOT_ALL_ACKNOWLEDGED,
                    current)
        # RELEASED + REVOKED require reason
        if (new_status in (HoldStatus.RELEASED, HoldStatus.REVOKED)
                and not reason.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f)
                    for f in current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": new_status.value, "at_utc": now_utc,
              "user": user, "reason": reason},))
        if new_status == HoldStatus.RELEASED:
            kwargs["release_reason"] = reason.strip()
            kwargs["release_at_utc"] = now_utc
        elif new_status == HoldStatus.REVOKED:
            kwargs["revocation_reason"] = reason.strip()
        updated = Hold(**kwargs)
        self._holds[hold_id] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Custodian acknowledgment
    # ------------------------------------------------------------------

    def record_acknowledgment(
        self, acknowledgment_id: str, notes: str = "",
    ) -> Tuple[TransitionOutcome,
                  Optional[CustodianAcknowledgment]]:
        if acknowledgment_id not in self._acks:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._acks[acknowledgment_id]
        if current.status != AcknowledgmentStatus.PENDING:
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f)
                    for f in current.__dataclass_fields__}
        kwargs["status"] = AcknowledgmentStatus.ACKNOWLEDGED
        kwargs["acknowledged_at_utc"] = now_utc
        if notes.strip():
            kwargs["notes"] = notes.strip()
        updated = CustodianAcknowledgment(**kwargs)
        self._acks[acknowledgment_id] = updated
        return (TransitionOutcome.OK, updated)

    def mark_escalated(
        self, acknowledgment_id: str, reason: str,
    ) -> Tuple[TransitionOutcome,
                  Optional[CustodianAcknowledgment]]:
        if acknowledgment_id not in self._acks:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        if not reason.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    self._acks[acknowledgment_id])
        current = self._acks[acknowledgment_id]
        if current.status != AcknowledgmentStatus.PENDING:
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f)
                    for f in current.__dataclass_fields__}
        kwargs["status"] = AcknowledgmentStatus.ESCALATED
        kwargs["escalated_at_utc"] = now_utc
        kwargs["notes"] = reason.strip()
        updated = CustodianAcknowledgment(**kwargs)
        self._acks[acknowledgment_id] = updated
        return (TransitionOutcome.OK, updated)

    def overdue_acknowledgments(
            self, as_of_date: Optional[str] = None,
            ) -> Tuple[CustodianAcknowledgment, ...]:
        """PENDING acknowledgments past their deadline."""
        if as_of_date is None:
            as_of_date = datetime.now(
                timezone.utc).strftime("%Y-%m-%d")
        out = []
        for ack in self._acks.values():
            if ack.status != AcknowledgmentStatus.PENDING:
                continue
            try:
                deadline = datetime.strptime(
                    ack.acknowledgment_deadline, "%Y-%m-%d").date()
                today = datetime.strptime(
                    as_of_date, "%Y-%m-%d").date()
                if deadline < today:
                    out.append(ack)
            except ValueError:
                continue
        return tuple(out)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def hold_by_id(self, hold_id: str) -> Hold:
        if hold_id not in self._holds:
            raise KeyError(f"not found: {hold_id}")
        return self._holds[hold_id]

    def acknowledgments_for_hold(
            self, hold_id: str
            ) -> Tuple[CustodianAcknowledgment, ...]:
        return tuple(a for a in self._acks.values()
                       if a.hold_id == hold_id)

    def active_holds(self) -> Tuple[Hold, ...]:
        return tuple(
            h for h in self._holds.values()
            if h.status in (HoldStatus.ISSUED,
                              HoldStatus.ACKNOWLEDGED))

    def board_summary(self) -> Dict[str, Any]:
        hold_status_counts: Dict[str, int] = {}
        for h in self._holds.values():
            hold_status_counts[h.status.value] = (
                hold_status_counts.get(h.status.value, 0) + 1)
        ack_status_counts: Dict[str, int] = {}
        for a in self._acks.values():
            ack_status_counts[a.status.value] = (
                ack_status_counts.get(a.status.value, 0) + 1)
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-227 LegalHoldManagementEngine",
            "n_holds_total": len(self._holds),
            "n_holds_active": len(self.active_holds()),
            "n_acknowledgments_total": len(self._acks),
            "n_acknowledgments_overdue": len(
                self.overdue_acknowledgments()),
            "hold_status_counts": hold_status_counts,
            "ack_status_counts": ack_status_counts,
            "default_ack_deadline_days": (
                self.DEFAULT_ACK_DEADLINE_DAYS),
            "automated_preservation_holds_status": (
                self.AUTOMATED_PRESERVATION_HOLDS_STATUS),
            "escalation_notification_status": (
                self.ESCALATION_NOTIFICATION_STATUS),
            "chain_of_custody_audit_status": (
                self.CHAIN_OF_CUSTODY_AUDIT_STATUS),
            "regulatory_basis": (
                "Kenya Civil Procedure Rules duty to preserve, "
                "CBK Risk Management Guidelines re spoliation, "
                "Companies Act §145 director duty re material "
                "litigation, common-law spoliation doctrine"),
        }

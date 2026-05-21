"""utils/legal_case_management.py — ENH-223 Legal Case Management.

Second engine of the Legal arc. Tracks legal case lifecycle:
intake → analysis → strategy → execution → resolution.

5-stage state machine, with WITHDRAWN allowed before resolution.
Tracks documents (linked refs), communications (log), billable hours
+ outcome.

REGULATORY ALIGNMENT
- Advocates Act §35 (Kenya) — file management requirements
- CBK Operational Risk Mgmt — material litigation disclosure
- Companies Act §145 — director duty re material litigation

HONEST DEFERRALS
- DOCUMENT STORAGE: meta-only references; integration with
  utils/document_management.py future work
- BILLABLE HOURS BILLING: engine tracks hours but doesn't compute
  invoices — operator-side
- COMMUNICATIONS: text log only; no email/Slack integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


class CaseStage(str, Enum):
    INTAKE = "INTAKE"
    ANALYSIS = "ANALYSIS"
    STRATEGY = "STRATEGY"
    EXECUTION = "EXECUTION"
    RESOLUTION = "RESOLUTION"
    WITHDRAWN = "WITHDRAWN"


class CaseOutcome(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    SETTLED = "SETTLED"
    WON = "WON"
    LOST = "LOST"
    PARTIALLY_WON = "PARTIALLY_WON"
    DISMISSED = "DISMISSED"
    WITHDRAWN = "WITHDRAWN"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"


# Forward-only stage progression with WITHDRAWN escape from any
# pre-RESOLUTION state.
ALLOWED_TRANSITIONS: Mapping[CaseStage, Tuple[CaseStage, ...]] = {
    CaseStage.INTAKE: (CaseStage.ANALYSIS, CaseStage.WITHDRAWN),
    CaseStage.ANALYSIS: (CaseStage.STRATEGY, CaseStage.WITHDRAWN),
    CaseStage.STRATEGY: (CaseStage.EXECUTION, CaseStage.WITHDRAWN),
    CaseStage.EXECUTION: (CaseStage.RESOLUTION, CaseStage.WITHDRAWN),
    CaseStage.RESOLUTION: (),
    CaseStage.WITHDRAWN: (),
}


@dataclass(frozen=True)
class CommunicationEntry:
    timestamp_utc: str
    author: str
    channel: str           # email, meeting, court, phone
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {"timestamp_utc": self.timestamp_utc,
                "author": self.author,
                "channel": self.channel, "summary": self.summary}


@dataclass(frozen=True)
class BillableEntry:
    timestamp_utc: str
    role: str                    # internal_counsel / external_counsel
    timekeeper: str
    hours: Decimal
    matter_description: str

    def to_dict(self) -> Dict[str, Any]:
        return {"timestamp_utc": self.timestamp_utc,
                "role": self.role, "timekeeper": self.timekeeper,
                "hours": str(self.hours),
                "matter_description": self.matter_description}


@dataclass(frozen=True)
class LegalCase:
    case_id: str
    matter_name: str
    counterparty: str
    case_type: str               # litigation/arbitration/regulatory
    materiality: str             # LOW/MEDIUM/HIGH/CRITICAL
    lead_counsel: str
    opened_at_utc: str
    stage: CaseStage
    outcome: CaseOutcome
    document_refs: Tuple[str, ...] = ()
    communications: Tuple[CommunicationEntry, ...] = ()
    billable_entries: Tuple[BillableEntry, ...] = ()
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    resolution_notes: str = ""
    closed_at_utc: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def total_hours(self) -> Decimal:
        return sum(
            (b.hours for b in self.billable_entries),
            Decimal("0"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "matter_name": self.matter_name,
            "counterparty": self.counterparty,
            "case_type": self.case_type,
            "materiality": self.materiality,
            "lead_counsel": self.lead_counsel,
            "opened_at_utc": self.opened_at_utc,
            "stage": self.stage.value,
            "outcome": self.outcome.value,
            "document_refs": list(self.document_refs),
            "communications": [c.to_dict()
                                 for c in self.communications],
            "billable_entries": [b.to_dict()
                                   for b in self.billable_entries],
            "total_hours": str(self.total_hours()),
            "transition_log": [dict(t) for t in self.transition_log],
            "resolution_notes": self.resolution_notes,
            "closed_at_utc": self.closed_at_utc,
            "meta": dict(self.meta),
        }


class LegalCaseManagementEngine:
    """ENH-223 Legal Case Management Engine."""

    DOCUMENT_STORAGE_STATUS = (
        "META_ONLY — engine tracks document_refs (string IDs); "
        "actual document storage operator-side via utils/"
        "document_management.py. Bidirectional integration future "
        "work.")

    BILLING_INTEGRATION_STATUS = (
        "DEFERRED — engine accumulates billable hours per timekeeper; "
        "invoice generation, rate cards, and AP/AR integration are "
        "operator-side. v10.171 ships hour-tracking; billing wiring "
        "future work.")

    def __init__(self) -> None:
        self._cases: Dict[str, LegalCase] = {}
        self._next_id = 1

    def open_case(
        self,
        matter_name: str,
        counterparty: str,
        case_type: str,
        materiality: str,
        lead_counsel: str,
    ) -> LegalCase:
        if not matter_name.strip():
            raise ValueError("matter_name required")
        if not lead_counsel.strip():
            raise ValueError(
                "lead_counsel required — every case needs a "
                "named lead counsel for accountability")
        if materiality.upper() not in (
                "LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise ValueError(
                "materiality must be LOW/MEDIUM/HIGH/CRITICAL")

        case_id = f"CASE-{self._next_id:06d}"
        self._next_id += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        case = LegalCase(
            case_id=case_id, matter_name=matter_name.strip(),
            counterparty=counterparty.strip(),
            case_type=case_type.strip(),
            materiality=materiality.upper(),
            lead_counsel=lead_counsel.strip(),
            opened_at_utc=now_utc,
            stage=CaseStage.INTAKE,
            outcome=CaseOutcome.UNRESOLVED,
            transition_log=(
                {"to_stage": "INTAKE", "at_utc": now_utc,
                 "user": "system", "reason": "case opened"},),
            meta={"engine_version": "ENH-223-v10.171"},
        )
        self._cases[case_id] = case
        return case

    def transition(
        self,
        case_id: str,
        new_stage: CaseStage,
        user: str,
        reason: str = "",
        outcome: Optional[CaseOutcome] = None,
        resolution_notes: str = "",
    ) -> Tuple[TransitionOutcome, Optional[LegalCase]]:
        if case_id not in self._cases:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._cases[case_id]
        if new_stage not in ALLOWED_TRANSITIONS.get(
                current.stage, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        # WITHDRAWN requires reason
        if new_stage == CaseStage.WITHDRAWN and not reason.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        # RESOLUTION requires outcome + resolution_notes
        if new_stage == CaseStage.RESOLUTION:
            if outcome is None:
                return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                        current)
            if not resolution_notes.strip():
                return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                        current)

        now_utc = datetime.now(timezone.utc).isoformat()
        new_log = {"to_stage": new_stage.value, "at_utc": now_utc,
                    "user": user, "reason": reason}
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["stage"] = new_stage
        kwargs["transition_log"] = current.transition_log + (new_log,)
        if new_stage == CaseStage.RESOLUTION:
            kwargs["outcome"] = outcome
            kwargs["resolution_notes"] = resolution_notes.strip()
            kwargs["closed_at_utc"] = now_utc
        elif new_stage == CaseStage.WITHDRAWN:
            kwargs["outcome"] = CaseOutcome.WITHDRAWN
            kwargs["closed_at_utc"] = now_utc
        updated = LegalCase(**kwargs)
        self._cases[case_id] = updated
        return (TransitionOutcome.OK, updated)

    def add_communication(
        self, case_id: str, author: str,
        channel: str, summary: str,
    ) -> LegalCase:
        if case_id not in self._cases:
            raise KeyError(f"not found: {case_id}")
        if not summary.strip():
            raise ValueError("communication summary required")
        current = self._cases[case_id]
        entry = CommunicationEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            author=author.strip(), channel=channel.strip(),
            summary=summary.strip())
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["communications"] = (current.communications + (entry,))
        updated = LegalCase(**kwargs)
        self._cases[case_id] = updated
        return updated

    def add_billable_entry(
        self, case_id: str, role: str, timekeeper: str,
        hours: Decimal, matter_description: str,
    ) -> LegalCase:
        if case_id not in self._cases:
            raise KeyError(f"not found: {case_id}")
        if hours <= Decimal("0"):
            raise ValueError("hours must be positive")
        if not timekeeper.strip():
            raise ValueError("timekeeper required")
        current = self._cases[case_id]
        entry = BillableEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            role=role.strip(), timekeeper=timekeeper.strip(),
            hours=hours,
            matter_description=matter_description.strip())
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["billable_entries"] = (
            current.billable_entries + (entry,))
        updated = LegalCase(**kwargs)
        self._cases[case_id] = updated
        return updated

    def link_document(self, case_id: str,
                         document_ref: str) -> LegalCase:
        if case_id not in self._cases:
            raise KeyError(f"not found: {case_id}")
        if not document_ref.strip():
            raise ValueError("document_ref required")
        current = self._cases[case_id]
        if document_ref in current.document_refs:
            return current  # idempotent
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["document_refs"] = (
            current.document_refs + (document_ref.strip(),))
        updated = LegalCase(**kwargs)
        self._cases[case_id] = updated
        return updated

    # Queries
    def case_by_id(self, case_id: str) -> LegalCase:
        if case_id not in self._cases:
            raise KeyError(f"not found: {case_id}")
        return self._cases[case_id]

    def all_cases(self) -> Tuple[LegalCase, ...]:
        return tuple(self._cases.values())

    def open_cases(self) -> Tuple[LegalCase, ...]:
        return tuple(c for c in self._cases.values()
                       if c.stage not in (CaseStage.RESOLUTION,
                                            CaseStage.WITHDRAWN))

    def critical_open_cases(self) -> Tuple[LegalCase, ...]:
        return tuple(c for c in self.open_cases()
                       if c.materiality == "CRITICAL")

    def board_summary(self) -> Dict[str, Any]:
        cases = list(self._cases.values())
        n_total = len(cases)
        stage_counts: Dict[str, int] = {}
        materiality_counts: Dict[str, int] = {}
        outcome_counts: Dict[str, int] = {}
        total_hours = Decimal("0")
        for c in cases:
            stage_counts[c.stage.value] = (
                stage_counts.get(c.stage.value, 0) + 1)
            materiality_counts[c.materiality] = (
                materiality_counts.get(c.materiality, 0) + 1)
            outcome_counts[c.outcome.value] = (
                outcome_counts.get(c.outcome.value, 0) + 1)
            total_hours += c.total_hours()
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-223 LegalCaseManagementEngine",
            "n_cases_total": n_total,
            "n_open": len(self.open_cases()),
            "n_critical_open": len(self.critical_open_cases()),
            "stage_counts": stage_counts,
            "materiality_counts": materiality_counts,
            "outcome_counts": outcome_counts,
            "total_billable_hours": str(total_hours),
            "document_storage_status": self.DOCUMENT_STORAGE_STATUS,
            "billing_integration_status": (
                self.BILLING_INTEGRATION_STATUS),
            "regulatory_basis": (
                "Advocates Act §35 (Kenya) file management, CBK "
                "Operational Risk Mgmt material litigation "
                "disclosure, Companies Act §145 director duty"),
        }

"""utils/regulatory_change.py — ENH-195 Regulatory Change Management.

================================================================================
A2Z MIS 360 — ENH-195 Regulatory Change Management Engine
================================================================================

INBOUND complement to v10.164 (outbound enterprise rollup) and v10.165
(outbound examination package). Tracks regulatory changes from sources
that affect bank operations, drives gap analysis, schedules attestation.

CRITICAL DESIGN DECISION
------------------------
This engine ingests STRUCTURED change records supplied by operators.
It does NOT scrape regulator websites or parse PDFs — CBK doesn't
publish a programmatic API for circulars; operator-side scraping/
parsing is out of scope for v10.166. Engine accepts manual entries
through a clean API.

The honest deferral surface (`automated_feed_status`) reads:
    AUTOMATED_FEED — DEFERRED. CBK / KRA / FRC publish circulars and
    amendments via PDF, web pages, and email subscriptions. There is
    no programmatic API. v10.166 accepts manual operator entries via
    register_change(). Future increment can add per-source PDF
    parsers + web scrapers; out of scope for this drop.

REGULATORY ALIGNMENT
--------------------
Sources tracked (subset of regulators relevant to Ecobank Kenya):
- CBK (Central Bank of Kenya) — Prudential Guidelines, circulars
- POCAMLA — Proceeds of Crime and AML Act amendments
- Banking Act — primary banking statute amendments
- KRA (Kenya Revenue Authority) — tax-related circulars affecting
  financial institutions
- FRC (Financial Reporting Centre) — AML reporting amendments
- DPC (Data Protection Commissioner) — Kenya Data Protection Act 2019

CHANGE LIFECYCLE
----------------
A regulatory change moves through this state machine:

    DRAFT       (operator entered initial record)
        →  OPEN              (validated, assigned to policy area)
            →  IN_PROGRESS    (impact analysis underway, action plan)
                →  CLOSED     (compliance verified, attestation done)

Backwards transitions rejected. WITHDRAWN allowed only from DRAFT
(operator entered erroneous change → can withdraw before assignment).

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


class RegulatorySource(str, Enum):
    """Regulatory source taxonomy for Kenya banking."""
    CBK = "CBK"
    POCAMLA = "POCAMLA"
    BANKING_ACT = "BANKING_ACT"
    KRA = "KRA"
    FRC = "FRC"
    DPC = "DPC"
    OTHER = "OTHER"


class ChangeStatus(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    WITHDRAWN = "WITHDRAWN"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"


class ImpactSeverity(str, Enum):
    """Impact severity per change record."""
    LOW = "LOW"          # informational, no policy update needed
    MEDIUM = "MEDIUM"    # policy update advisable
    HIGH = "HIGH"        # policy update required
    CRITICAL = "CRITICAL"  # immediate action; potential breach exposure


# Allowed transitions
ALLOWED_TRANSITIONS: Mapping[ChangeStatus, Tuple[ChangeStatus, ...]] = {
    ChangeStatus.DRAFT: (ChangeStatus.OPEN, ChangeStatus.WITHDRAWN),
    ChangeStatus.OPEN: (ChangeStatus.IN_PROGRESS,),
    ChangeStatus.IN_PROGRESS: (ChangeStatus.CLOSED,),
    ChangeStatus.CLOSED: (),
    ChangeStatus.WITHDRAWN: (),
}

# Default attestation deadline window per severity
DEFAULT_ATTESTATION_DAYS: Mapping[ImpactSeverity, int] = {
    ImpactSeverity.LOW: 90,
    ImpactSeverity.MEDIUM: 60,
    ImpactSeverity.HIGH: 30,
    ImpactSeverity.CRITICAL: 7,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegulatoryChange:
    """A single regulatory change record + its lifecycle state."""
    change_id: str
    source: RegulatorySource
    citation: str               # e.g. "CBK PG/15 Amendment 3 of 2026"
    title: str
    summary: str                # operator-written short narrative
    effective_date: str         # YYYY-MM-DD when change takes effect
    severity: ImpactSeverity
    affected_policies: Tuple[str, ...]   # operator-supplied policy IDs
    affected_engines: Tuple[str, ...]    # internal engines impacted
    attestation_deadline_utc: str
    attestation_owner: str       # role/user_id responsible
    status: ChangeStatus
    registered_at_utc: str
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    closure_evidence: str = ""   # operator-supplied evidence on close
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "source": self.source.value,
            "citation": self.citation,
            "title": self.title,
            "summary": self.summary,
            "effective_date": self.effective_date,
            "severity": self.severity.value,
            "affected_policies": list(self.affected_policies),
            "affected_engines": list(self.affected_engines),
            "attestation_deadline_utc": (
                self.attestation_deadline_utc),
            "attestation_owner": self.attestation_owner,
            "status": self.status.value,
            "registered_at_utc": self.registered_at_utc,
            "transition_log": [dict(t) for t in self.transition_log],
            "closure_evidence": self.closure_evidence,
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RegulatoryChangeEngine:
    """ENH-195 Regulatory Change Management Engine.

    Tracks inbound regulatory changes through the
    DRAFT → OPEN → IN_PROGRESS → CLOSED lifecycle. Schedules
    attestation deadlines per severity. Surfaces overdue attestations.

    Use:
        engine = RegulatoryChangeEngine()
        change = engine.register_change(
            source=RegulatorySource.CBK,
            citation="CBK PG/15 Amendment 3 of 2026",
            title="...",
            summary="...",
            effective_date="2026-07-01",
            severity=ImpactSeverity.HIGH,
            affected_policies=("POL-001", "POL-002"),
            affected_engines=("kyc_onboarding",),
            attestation_owner="head_of_compliance",
        )
        # Returns DRAFT change with auto-computed deadline.

        engine.transition(change.change_id, ChangeStatus.OPEN,
                            user="compliance_lead")
        # ... lifecycle progression
    """

    AUTOMATED_FEED_STATUS = (
        "DEFERRED — CBK / KRA / FRC publish circulars and amendments "
        "via PDF, web pages, and email subscriptions. There is no "
        "programmatic API. v10.166 accepts manual operator entries "
        "via register_change(). Future increment can add per-source "
        "PDF parsers + web scrapers; out of scope for this drop.")

    POLICY_LINKAGE_STATUS = (
        "PARTIAL — affected_policies field accepts string IDs but "
        "bidirectional linkage to a Policy Management engine "
        "requires ENH-196 (Policy Management & Attestation) to be "
        "active. v10.166 ships uni-directional reference (change → "
        "list of policy_id strings). Full bidirectional linkage in "
        "ENH-196+ increment.")

    def __init__(self) -> None:
        self._changes: Dict[str, RegulatoryChange] = {}
        self._next_id = 1

    # ------------------------------------------------------------------
    # Register a new change (DRAFT)
    # ------------------------------------------------------------------

    def register_change(
        self,
        source: RegulatorySource,
        citation: str,
        title: str,
        summary: str,
        effective_date: str,
        severity: ImpactSeverity,
        affected_policies: Tuple[str, ...] = (),
        affected_engines: Tuple[str, ...] = (),
        attestation_owner: str = "",
        attestation_deadline_utc: Optional[str] = None,
    ) -> RegulatoryChange:
        """Register a new regulatory change as DRAFT."""
        if not citation.strip():
            raise ValueError("citation required")
        if not title.strip():
            raise ValueError("title required")
        if not summary.strip():
            raise ValueError("summary required")
        if not effective_date.strip():
            raise ValueError("effective_date required (YYYY-MM-DD)")
        if not attestation_owner.strip():
            raise ValueError(
                "attestation_owner required — every regulatory change "
                "needs a named owner per CBK governance expectations")

        # Auto-compute attestation deadline from severity if not given
        if attestation_deadline_utc is None:
            days = DEFAULT_ATTESTATION_DAYS.get(severity, 60)
            deadline_dt = datetime.now(timezone.utc) + timedelta(
                days=days)
            attestation_deadline_utc = deadline_dt.isoformat()

        change_id = f"REG-{self._next_id:06d}"
        self._next_id += 1
        now_utc = datetime.now(timezone.utc).isoformat()

        change = RegulatoryChange(
            change_id=change_id,
            source=source,
            citation=citation.strip(),
            title=title.strip(),
            summary=summary.strip(),
            effective_date=effective_date,
            severity=severity,
            affected_policies=tuple(affected_policies),
            affected_engines=tuple(affected_engines),
            attestation_deadline_utc=attestation_deadline_utc,
            attestation_owner=attestation_owner.strip(),
            status=ChangeStatus.DRAFT,
            registered_at_utc=now_utc,
            transition_log=(
                {"to_status": "DRAFT",
                 "at_utc": now_utc,
                 "user": "system",
                 "reason": "initial registration"},),
            meta={
                "engine_version": "ENH-195-v10.166",
                "auto_deadline_days": DEFAULT_ATTESTATION_DAYS.get(
                    severity, 60),
            },
        )
        self._changes[change_id] = change
        return change

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        change_id: str,
        new_status: ChangeStatus,
        user: str,
        reason: str = "",
        closure_evidence: str = "",
    ) -> Tuple[TransitionOutcome, Optional[RegulatoryChange]]:
        """Move change through lifecycle."""
        if change_id not in self._changes:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)

        current = self._changes[change_id]
        if new_status not in ALLOWED_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)

        # WITHDRAWN requires reason
        if new_status == ChangeStatus.WITHDRAWN and not reason.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)

        # CLOSED requires closure_evidence (audit-trail)
        if new_status == ChangeStatus.CLOSED and \
                not closure_evidence.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)

        now_utc = datetime.now(timezone.utc).isoformat()
        new_log = {
            "to_status": new_status.value,
            "at_utc": now_utc,
            "user": user,
            "reason": reason,
        }

        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = current.transition_log + (new_log,)
        if new_status == ChangeStatus.CLOSED:
            kwargs["closure_evidence"] = closure_evidence.strip()

        updated = RegulatoryChange(**kwargs)
        self._changes[change_id] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Retrieval / portfolio
    # ------------------------------------------------------------------

    def change_by_id(self, change_id: str) -> RegulatoryChange:
        if change_id not in self._changes:
            raise KeyError(f"not found: {change_id}")
        return self._changes[change_id]

    def all_changes(self) -> Tuple[RegulatoryChange, ...]:
        return tuple(self._changes.values())

    def overdue_attestations(self) -> Tuple[RegulatoryChange, ...]:
        """Changes whose attestation_deadline has passed but are not
        yet CLOSED — operator-actionable regulatory exposure."""
        now_utc = datetime.now(timezone.utc).isoformat()
        return tuple(
            c for c in self._changes.values()
            if c.status not in (ChangeStatus.CLOSED,
                                  ChangeStatus.WITHDRAWN)
            and c.attestation_deadline_utc < now_utc)

    def changes_by_source(
            self, source: RegulatorySource
    ) -> Tuple[RegulatoryChange, ...]:
        return tuple(
            c for c in self._changes.values()
            if c.source == source)

    def changes_by_severity(
            self, severity: ImpactSeverity
    ) -> Tuple[RegulatoryChange, ...]:
        return tuple(
            c for c in self._changes.values()
            if c.severity == severity)

    def board_summary(self) -> Dict[str, Any]:
        changes = list(self._changes.values())
        n_total = len(changes)
        status_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        for c in changes:
            status_counts[c.status.value] = (
                status_counts.get(c.status.value, 0) + 1)
            severity_counts[c.severity.value] = (
                severity_counts.get(c.severity.value, 0) + 1)
            source_counts[c.source.value] = (
                source_counts.get(c.source.value, 0) + 1)

        n_overdue = len(self.overdue_attestations())
        n_critical_open = sum(
            1 for c in changes
            if c.severity == ImpactSeverity.CRITICAL and
            c.status not in (ChangeStatus.CLOSED,
                                ChangeStatus.WITHDRAWN))

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-195 RegulatoryChangeEngine",
            "n_changes_total": n_total,
            "n_overdue_attestations": n_overdue,
            "n_critical_open": n_critical_open,
            "status_counts": status_counts,
            "severity_counts": severity_counts,
            "source_counts": source_counts,
            "automated_feed_status": self.AUTOMATED_FEED_STATUS,
            "policy_linkage_status": self.POLICY_LINKAGE_STATUS,
            "regulatory_basis": (
                "CBK Prudential Guidelines + circulars, POCAMLA + "
                "amendments, Banking Act + amendments, KRA + FRC + "
                "DPC notices applicable to Kenya banking institutions"),
        }

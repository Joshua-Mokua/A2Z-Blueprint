"""utils/audit_trail_certification.py — v10.27 Audit/GRC arc final standard.

╔════════════════════════════════════════════════════════════════════════╗
║  AUDIT TRAIL INTEGRITY + COMPLIANCE CERTIFICATION                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (period-end attestation drives external audit       ║
║              opinion + regulator filings; chain integrity verifies     ║
║              that audit history hasn't been tampered with)             ║
║  Implements 1 of 17 Audit/GRC standards from registry — final batch:    ║
║    ENH-210: Audit Trail & Compliance Certification                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IIA IPPF Standard 2400 — communicating results                       ║
║    IIA IPPF Standard 2410 — criteria for communicating                  ║
║    IIA IPPF Standard 2450 — overall opinions                            ║
║    Sarbanes-Oxley §302 — corporate responsibility certification        ║
║    Sarbanes-Oxley §404 — internal controls assessment                  ║
║    Sarbanes-Oxley §906 — corporate responsibility for financial reports║
║    PCAOB AS 2201 — audit of internal control over financial reporting ║
║    CBK CRMF April 2021 §7.8 — period-end attestations                  ║
║    CBK Banking Act §32 — annual statutory returns                      ║
║    Basel BCBS 239 §11/§12 — accuracy + integrity                        ║
║    ISO 27001:2022 §A.12.4 — logging + monitoring                       ║
║    NIST SP 800-92 — log management                                      ║
║    Kenya Data Protection Act 2019 §28 — retention                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.23 + v10.24 + v10.25 + v10.26 (full Audit/GRC stack).║
║                                                                         ║
║  Honesty Rule 1: every chain integrity break surfaces with the         ║
║  specific entry that broke + reason; certification requires explicit   ║
║  multi-role sign-off — no silent attestation.                           ║
║  Honesty Rule 7: external attestation submission (CBK portal, SEC      ║
║  filings) is callable hook; without wiring, certification record       ║
║  preserved internally.                                                  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "External attestation submission (CBK supervisory portals, SEC EDGAR, "
    "etc.) is callable hook per Rule 7. Without wired submitter, "
    "certification records remain internal. Hash chain uses SHA-256 — "
    "production deployments may upgrade to BLAKE3 or SHA-3 for higher "
    "performance/security."
)


# ════════════════════════════════════════════════════════════════════════
# Audit Trail Integrity (Hash Chain)
# ════════════════════════════════════════════════════════════════════════

class AuditTrailEventType(Enum):
    """Types of events that flow into the audit trail."""
    CONTROL_TEST_EXECUTED = "CONTROL_TEST_EXECUTED"
    ISSUE_RAISED = "ISSUE_RAISED"
    ISSUE_TRANSITIONED = "ISSUE_TRANSITIONED"
    WORKING_PAPER_FILED = "WORKING_PAPER_FILED"
    WORKING_PAPER_REVIEWED = "WORKING_PAPER_REVIEWED"
    VENDOR_ASSESSED = "VENDOR_ASSESSED"
    ALERT_RAISED = "ALERT_RAISED"
    ALERT_ACKNOWLEDGED = "ALERT_ACKNOWLEDGED"
    EXTERNAL_AUDITOR_ACCESS = "EXTERNAL_AUDITOR_ACCESS"
    COMMITTEE_REPORT_FILED = "COMMITTEE_REPORT_FILED"
    BOARD_DASHBOARD_FILED = "BOARD_DASHBOARD_FILED"
    CERTIFICATION_SIGNED = "CERTIFICATION_SIGNED"
    PERIOD_SEALED = "PERIOD_SEALED"


@dataclass(frozen=True)
class AuditTrailEntry:
    """One immutable entry in the audit trail hash chain.

    Each entry's hash includes previous_hash → if any entry is tampered,
    all subsequent entries fail integrity check.
    """
    entry_id: str
    sequence_number: int                  # 1-indexed, monotonic
    event_type: AuditTrailEventType
    timestamp_utc: str
    actor_user_id: str
    source_engine: str                     # which engine produced the event
    target_object_type: str
    target_object_id: str
    payload_json: str                      # canonical JSON of event details
    previous_hash: str                     # hash of previous entry (or empty for genesis)
    entry_hash: str                        # SHA-256 of all above fields
    notes: str = ""


def compute_entry_hash(
    *,
    sequence_number: int,
    event_type: AuditTrailEventType,
    timestamp_utc: str,
    actor_user_id: str,
    source_engine: str,
    target_object_type: str,
    target_object_id: str,
    payload_json: str,
    previous_hash: str,
) -> str:
    """Compute SHA-256 hash for a new audit trail entry.

    The hash includes ALL identifying fields + previous_hash, creating
    the chain. Tampering with any field breaks the chain.
    """
    h = hashlib.sha256()
    h.update(str(sequence_number).encode("utf-8"))
    h.update(b"\x00")
    h.update(event_type.value.encode("utf-8"))
    h.update(b"\x00")
    h.update(timestamp_utc.encode("utf-8"))
    h.update(b"\x00")
    h.update(actor_user_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(source_engine.encode("utf-8"))
    h.update(b"\x00")
    h.update(target_object_type.encode("utf-8"))
    h.update(b"\x00")
    h.update(target_object_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(payload_json.encode("utf-8"))
    h.update(b"\x00")
    h.update(previous_hash.encode("utf-8"))
    return h.hexdigest()


def append_entry(
    *,
    chain: Sequence[AuditTrailEntry],
    entry_id: str,
    event_type: AuditTrailEventType,
    timestamp_utc: str,
    actor_user_id: str,
    source_engine: str,
    target_object_type: str,
    target_object_id: str,
    payload: Mapping[str, object],
    notes: str = "",
) -> AuditTrailEntry:
    """Append a new entry to the chain, computing hash + sequence."""
    sequence = len(chain) + 1    # 1-indexed
    previous_hash = chain[-1].entry_hash if chain else ""
    payload_json = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"))
    entry_hash = compute_entry_hash(
        sequence_number=sequence,
        event_type=event_type,
        timestamp_utc=timestamp_utc,
        actor_user_id=actor_user_id,
        source_engine=source_engine,
        target_object_type=target_object_type,
        target_object_id=target_object_id,
        payload_json=payload_json,
        previous_hash=previous_hash)
    return AuditTrailEntry(
        entry_id=entry_id,
        sequence_number=sequence,
        event_type=event_type,
        timestamp_utc=timestamp_utc,
        actor_user_id=actor_user_id,
        source_engine=source_engine,
        target_object_type=target_object_type,
        target_object_id=target_object_id,
        payload_json=payload_json,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        notes=notes)


@dataclass(frozen=True)
class ChainIntegrityResult:
    """Result of verifying audit trail chain integrity."""
    is_intact: bool
    n_entries_checked: int
    first_break_sequence: Optional[int] = None
    first_break_reason: Optional[str] = None
    notes: str = ""


def verify_chain_integrity(
    *, chain: Sequence[AuditTrailEntry],
) -> ChainIntegrityResult:
    """Walk the chain, verify each entry's hash + previous_hash linkage.

    Returns the FIRST break with explicit reason. Per Rule 1 — never
    silently passes; if no break, returns is_intact=True.
    """
    expected_previous = ""
    for i, entry in enumerate(chain):
        # Verify sequence number
        if entry.sequence_number != i + 1:
            return ChainIntegrityResult(
                is_intact=False, n_entries_checked=i + 1,
                first_break_sequence=entry.sequence_number,
                first_break_reason=(
                    f"sequence number {entry.sequence_number} "
                    f"does not match expected {i + 1}"))
        # Verify previous_hash linkage
        if entry.previous_hash != expected_previous:
            return ChainIntegrityResult(
                is_intact=False, n_entries_checked=i + 1,
                first_break_sequence=entry.sequence_number,
                first_break_reason=(
                    f"previous_hash mismatch at sequence "
                    f"{entry.sequence_number}: expected "
                    f"'{expected_previous}', got "
                    f"'{entry.previous_hash}'"))
        # Verify entry's own hash
        recomputed = compute_entry_hash(
            sequence_number=entry.sequence_number,
            event_type=entry.event_type,
            timestamp_utc=entry.timestamp_utc,
            actor_user_id=entry.actor_user_id,
            source_engine=entry.source_engine,
            target_object_type=entry.target_object_type,
            target_object_id=entry.target_object_id,
            payload_json=entry.payload_json,
            previous_hash=entry.previous_hash)
        if recomputed != entry.entry_hash:
            return ChainIntegrityResult(
                is_intact=False, n_entries_checked=i + 1,
                first_break_sequence=entry.sequence_number,
                first_break_reason=(
                    f"entry hash mismatch at sequence "
                    f"{entry.sequence_number}: stored hash does not "
                    f"match recomputed hash — entry may be tampered"))
        expected_previous = entry.entry_hash

    return ChainIntegrityResult(
        is_intact=True,
        n_entries_checked=len(chain),
        notes=f"chain verified ({len(chain)} entries)")


# ════════════════════════════════════════════════════════════════════════
# Period Sealing
# ════════════════════════════════════════════════════════════════════════

class PeriodSealStatus(Enum):
    OPEN = "OPEN"
    SEALED = "SEALED"
    SUPERSEDED = "SUPERSEDED"   # re-sealed due to amendment


@dataclass(frozen=True)
class PeriodSeal:
    """Cryptographic seal of an audit period.

    A seal is a snapshot of the chain at a specific entry — for period-end
    attestation. The sealed_chain_hash is the hash of the entry at that
    point, anchoring the period.
    """
    seal_id: str
    period_label: str                      # e.g., "2026-Q1", "2026-FY"
    period_start: str                      # ISO-8601
    period_end: str
    sealed_at_utc: str
    sealed_at_sequence: int                # last entry included
    sealed_chain_hash: str                 # hash anchoring the period
    n_entries_in_period: int
    status: PeriodSealStatus = PeriodSealStatus.SEALED
    sealed_by_user_id: str = ""
    notes: str = ""


def seal_period(
    *,
    seal_id: str,
    period_label: str,
    period_start: str,
    period_end: str,
    sealed_at_utc: str,
    sealed_by_user_id: str,
    chain: Sequence[AuditTrailEntry],
) -> PeriodSeal:
    """Seal a period at the end of the current chain.

    Verifies chain integrity first; raises if chain is broken.
    """
    integrity = verify_chain_integrity(chain=chain)
    if not integrity.is_intact:
        raise ValueError(
            f"cannot seal period — chain integrity broken at "
            f"sequence {integrity.first_break_sequence}: "
            f"{integrity.first_break_reason}")

    if not chain:
        return PeriodSeal(
            seal_id=seal_id, period_label=period_label,
            period_start=period_start, period_end=period_end,
            sealed_at_utc=sealed_at_utc,
            sealed_at_sequence=0,
            sealed_chain_hash="",
            n_entries_in_period=0,
            sealed_by_user_id=sealed_by_user_id,
            notes="empty chain — sealed empty period")

    # Count entries within the period
    n_in_period = 0
    for entry in chain:
        if (entry.timestamp_utc >= period_start
                and entry.timestamp_utc <= period_end + "T23:59:59Z"):
            n_in_period += 1

    last_entry = chain[-1]
    return PeriodSeal(
        seal_id=seal_id, period_label=period_label,
        period_start=period_start, period_end=period_end,
        sealed_at_utc=sealed_at_utc,
        sealed_at_sequence=last_entry.sequence_number,
        sealed_chain_hash=last_entry.entry_hash,
        n_entries_in_period=n_in_period,
        sealed_by_user_id=sealed_by_user_id,
        notes=(
            f"sealed at sequence {last_entry.sequence_number}; "
            f"{n_in_period} entries within period"))


# ════════════════════════════════════════════════════════════════════════
# Compliance Certification
# ════════════════════════════════════════════════════════════════════════

class ComplianceFramework(Enum):
    """Frameworks against which compliance is attested."""
    SOX_302 = "SOX_302"               # CEO/CFO certification
    SOX_404 = "SOX_404"               # ICFR assessment
    SOX_906 = "SOX_906"               # corporate responsibility
    CBK_CRMF = "CBK_CRMF"             # CBK risk mgmt framework
    CBK_BANKING_ACT = "CBK_BANKING_ACT"   # statutory returns
    BASEL_BCBS_239 = "BASEL_BCBS_239" # data accuracy
    ISO_27001 = "ISO_27001"           # ISMS attestation
    PCI_DSS = "PCI_DSS"
    GDPR_ART_30 = "GDPR_ART_30"        # records of processing
    KENYA_DPA = "KENYA_DPA"
    INTERNAL_GOVERNANCE = "INTERNAL_GOVERNANCE"


class CertifierAttestationRole(Enum):
    """Roles required to sign a compliance certification."""
    CEO = "CEO"
    CFO = "CFO"
    CRO = "CRO"
    CCO = "CCO"                            # Chief Compliance Officer
    CAE = "CAE"                            # Chief Audit Executive
    CISO = "CISO"
    BOARD_CHAIR = "BOARD_CHAIR"
    AUDIT_COMMITTEE_CHAIR = "AUDIT_COMMITTEE_CHAIR"
    EXTERNAL_AUDITOR_PARTNER = "EXTERNAL_AUDITOR_PARTNER"


# Required signatures per framework
DEFAULT_REQUIRED_SIGNATURES: Mapping[
    ComplianceFramework, Tuple[CertifierAttestationRole, ...]] = {
    ComplianceFramework.SOX_302: (
        CertifierAttestationRole.CEO,
        CertifierAttestationRole.CFO),
    ComplianceFramework.SOX_404: (
        CertifierAttestationRole.CEO,
        CertifierAttestationRole.CFO,
        CertifierAttestationRole.CAE),
    ComplianceFramework.SOX_906: (
        CertifierAttestationRole.CEO,
        CertifierAttestationRole.CFO),
    ComplianceFramework.CBK_CRMF: (
        CertifierAttestationRole.CEO,
        CertifierAttestationRole.CRO,
        CertifierAttestationRole.CCO,
        CertifierAttestationRole.CAE),
    ComplianceFramework.CBK_BANKING_ACT: (
        CertifierAttestationRole.CEO,
        CertifierAttestationRole.CFO,
        CertifierAttestationRole.AUDIT_COMMITTEE_CHAIR),
    ComplianceFramework.BASEL_BCBS_239: (
        CertifierAttestationRole.CRO,
        CertifierAttestationRole.CFO,
        CertifierAttestationRole.CAE),
    ComplianceFramework.ISO_27001: (
        CertifierAttestationRole.CISO,
        CertifierAttestationRole.CCO),
    ComplianceFramework.PCI_DSS: (
        CertifierAttestationRole.CISO,),
    ComplianceFramework.GDPR_ART_30: (
        CertifierAttestationRole.CCO,),
    ComplianceFramework.KENYA_DPA: (
        CertifierAttestationRole.CCO,),
    ComplianceFramework.INTERNAL_GOVERNANCE: (
        CertifierAttestationRole.CEO,
        CertifierAttestationRole.BOARD_CHAIR),
}


class AttestationStatus(Enum):
    """Lifecycle of a compliance attestation."""
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    REVIEWED = "REVIEWED"
    SIGNATURES_PENDING = "SIGNATURES_PENDING"
    ATTESTED = "ATTESTED"                  # all required signatures collected
    REJECTED = "REJECTED"
    SUBMITTED = "SUBMITTED"                # filed with regulator
    AMENDED = "AMENDED"


# Allowed transitions
ALLOWED_ATTESTATION_TRANSITIONS: Mapping[
    AttestationStatus, Tuple[AttestationStatus, ...]] = {
    AttestationStatus.DRAFT: (
        AttestationStatus.PREPARED, AttestationStatus.REJECTED),
    AttestationStatus.PREPARED: (
        AttestationStatus.REVIEWED, AttestationStatus.REJECTED),
    AttestationStatus.REVIEWED: (
        AttestationStatus.SIGNATURES_PENDING,
        AttestationStatus.REJECTED),
    AttestationStatus.SIGNATURES_PENDING: (
        AttestationStatus.ATTESTED,
        AttestationStatus.REJECTED),
    AttestationStatus.ATTESTED: (
        AttestationStatus.SUBMITTED, AttestationStatus.AMENDED),
    AttestationStatus.SUBMITTED: (AttestationStatus.AMENDED,),
    AttestationStatus.REJECTED: (AttestationStatus.AMENDED,),
    AttestationStatus.AMENDED: (AttestationStatus.PREPARED,),
}


def is_valid_attestation_transition(
    from_status: AttestationStatus,
    to_status: AttestationStatus,
) -> bool:
    return to_status in ALLOWED_ATTESTATION_TRANSITIONS.get(
        from_status, ())


@dataclass(frozen=True)
class AttestationSignature:
    """One signature on a compliance attestation."""
    signature_id: str
    role: CertifierAttestationRole
    user_id: str
    signed_at_utc: str
    signature_hash: str                    # cryptographic signature digest
    notes: str = ""


@dataclass(frozen=True)
class ComplianceAttestation:
    """Period-end compliance attestation against a framework."""
    attestation_id: str
    framework: ComplianceFramework
    period_label: str
    period_start: str
    period_end: str
    status: AttestationStatus
    period_seal_id: Optional[str]          # links to PeriodSeal
    chain_hash_at_attestation: str         # snapshot of audit chain
    signatures: Tuple[AttestationSignature, ...] = ()
    n_findings_open: int = 0
    n_findings_resolved: int = 0
    n_critical_findings: int = 0
    attestation_text: str = ""             # the certified statement
    notes: str = ""

    def required_roles(self) -> Tuple[CertifierAttestationRole, ...]:
        return DEFAULT_REQUIRED_SIGNATURES.get(self.framework, ())

    def signed_roles(self) -> Tuple[CertifierAttestationRole, ...]:
        return tuple(s.role for s in self.signatures)

    def missing_signatures(
        self) -> Tuple[CertifierAttestationRole, ...]:
        signed = set(self.signed_roles())
        return tuple(
            role for role in self.required_roles()
            if role not in signed)

    def is_fully_signed(self) -> bool:
        """All required signatures present."""
        return len(self.missing_signatures()) == 0

    def has_distinct_signers(self) -> bool:
        """No single user can sign multiple required roles."""
        users = [s.user_id for s in self.signatures]
        return len(users) == len(set(users))


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class AuditTrailCertificationEngine:
    """End-to-end orchestrator for audit trail + compliance certification."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._chain: List[AuditTrailEntry] = []
        self._seals: Dict[str, PeriodSeal] = {}
        self._attestations: Dict[str, ComplianceAttestation] = {}
        self._attestation_transitions: List[
            Tuple[str, AttestationStatus, AttestationStatus, str]] = []

    # ── Audit trail ───────────────────────────────────────────────────
    def append_event(
        self,
        *,
        entry_id: str,
        event_type: AuditTrailEventType,
        timestamp_utc: str,
        actor_user_id: str,
        source_engine: str,
        target_object_type: str,
        target_object_id: str,
        payload: Mapping[str, object],
        notes: str = "",
    ) -> AuditTrailEntry:
        entry = append_entry(
            chain=self._chain, entry_id=entry_id,
            event_type=event_type, timestamp_utc=timestamp_utc,
            actor_user_id=actor_user_id,
            source_engine=source_engine,
            target_object_type=target_object_type,
            target_object_id=target_object_id,
            payload=payload, notes=notes)
        self._chain.append(entry)
        return entry

    def chain(self) -> Tuple[AuditTrailEntry, ...]:
        return tuple(self._chain)

    def verify_chain(self) -> ChainIntegrityResult:
        return verify_chain_integrity(chain=self._chain)

    # ── Period sealing ────────────────────────────────────────────────
    def seal_period(
        self,
        *,
        seal_id: str,
        period_label: str,
        period_start: str,
        period_end: str,
        sealed_at_utc: str,
        sealed_by_user_id: str,
    ) -> PeriodSeal:
        if seal_id in self._seals:
            raise ValueError(f"seal {seal_id} already exists")
        seal = seal_period(
            seal_id=seal_id, period_label=period_label,
            period_start=period_start, period_end=period_end,
            sealed_at_utc=sealed_at_utc,
            sealed_by_user_id=sealed_by_user_id,
            chain=self._chain)
        self._seals[seal_id] = seal
        # Append a PERIOD_SEALED event to the chain
        self.append_event(
            entry_id=f"AT-SEAL-{seal_id}",
            event_type=AuditTrailEventType.PERIOD_SEALED,
            timestamp_utc=sealed_at_utc,
            actor_user_id=sealed_by_user_id,
            source_engine="audit_trail_certification",
            target_object_type="PeriodSeal",
            target_object_id=seal_id,
            payload={
                "period_label": period_label,
                "n_entries": seal.n_entries_in_period,
                "chain_hash": seal.sealed_chain_hash})
        return seal

    def get_seal(self, seal_id: str) -> PeriodSeal:
        if seal_id not in self._seals:
            raise KeyError(f"seal {seal_id} not found")
        return self._seals[seal_id]

    # ── Compliance attestation ────────────────────────────────────────
    def file_attestation(
        self, attestation: ComplianceAttestation,
    ) -> None:
        if attestation.attestation_id in self._attestations:
            raise ValueError(
                f"attestation {attestation.attestation_id} "
                f"already filed")
        self._attestations[attestation.attestation_id] = attestation

    def get_attestation(
        self, attestation_id: str,
    ) -> ComplianceAttestation:
        if attestation_id not in self._attestations:
            raise KeyError(
                f"attestation {attestation_id} not found")
        return self._attestations[attestation_id]

    def transition_attestation(
        self,
        *,
        attestation_id: str,
        to_status: AttestationStatus,
        actor_user_id: str,
        timestamp: str,
        notes: str = "",
    ) -> ComplianceAttestation:
        existing = self.get_attestation(attestation_id)
        if not is_valid_attestation_transition(
                existing.status, to_status):
            allowed = ALLOWED_ATTESTATION_TRANSITIONS.get(
                existing.status, ())
            raise ValueError(
                f"invalid attestation transition "
                f"{existing.status.value} → {to_status.value}; "
                f"allowed: {[s.value for s in allowed]}")

        # Special rule: ATTESTED requires fully_signed + distinct_signers
        if to_status == AttestationStatus.ATTESTED:
            if not existing.is_fully_signed():
                missing = existing.missing_signatures()
                raise ValueError(
                    f"cannot transition to ATTESTED — missing "
                    f"signatures: {[r.value for r in missing]}")
            if not existing.has_distinct_signers():
                raise ValueError(
                    "cannot transition to ATTESTED — same user "
                    "signed multiple required roles "
                    "(segregation of duties violation)")

        self._attestation_transitions.append((
            attestation_id, existing.status, to_status,
            actor_user_id))

        updated = ComplianceAttestation(
            attestation_id=existing.attestation_id,
            framework=existing.framework,
            period_label=existing.period_label,
            period_start=existing.period_start,
            period_end=existing.period_end,
            status=to_status,
            period_seal_id=existing.period_seal_id,
            chain_hash_at_attestation=existing.chain_hash_at_attestation,
            signatures=existing.signatures,
            n_findings_open=existing.n_findings_open,
            n_findings_resolved=existing.n_findings_resolved,
            n_critical_findings=existing.n_critical_findings,
            attestation_text=existing.attestation_text,
            notes=(
                existing.notes + "\n" + notes if notes
                else existing.notes))
        self._attestations[attestation_id] = updated

        # Append CERTIFICATION_SIGNED audit event for ATTESTED status
        if to_status == AttestationStatus.ATTESTED:
            self.append_event(
                entry_id=f"AT-CERT-{attestation_id}",
                event_type=AuditTrailEventType.CERTIFICATION_SIGNED,
                timestamp_utc=timestamp,
                actor_user_id=actor_user_id,
                source_engine="audit_trail_certification",
                target_object_type="ComplianceAttestation",
                target_object_id=attestation_id,
                payload={
                    "framework": existing.framework.value,
                    "period": existing.period_label,
                    "n_signatures": len(existing.signatures)})
        return updated

    def add_signature(
        self,
        *,
        attestation_id: str,
        signature: AttestationSignature,
    ) -> ComplianceAttestation:
        existing = self.get_attestation(attestation_id)
        if signature.role not in existing.required_roles():
            raise ValueError(
                f"role {signature.role.value} not required for "
                f"framework {existing.framework.value}")
        # Check if role already signed
        if signature.role in existing.signed_roles():
            raise ValueError(
                f"role {signature.role.value} already signed")
        updated = ComplianceAttestation(
            attestation_id=existing.attestation_id,
            framework=existing.framework,
            period_label=existing.period_label,
            period_start=existing.period_start,
            period_end=existing.period_end,
            status=existing.status,
            period_seal_id=existing.period_seal_id,
            chain_hash_at_attestation=existing.chain_hash_at_attestation,
            signatures=existing.signatures + (signature,),
            n_findings_open=existing.n_findings_open,
            n_findings_resolved=existing.n_findings_resolved,
            n_critical_findings=existing.n_critical_findings,
            attestation_text=existing.attestation_text,
            notes=existing.notes)
        self._attestations[attestation_id] = updated
        return updated

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        n_attested = sum(
            1 for a in self._attestations.values()
            if a.status == AttestationStatus.ATTESTED
            or a.status == AttestationStatus.SUBMITTED)
        n_pending = sum(
            1 for a in self._attestations.values()
            if a.status in (
                AttestationStatus.SIGNATURES_PENDING,
                AttestationStatus.PREPARED,
                AttestationStatus.REVIEWED))
        integrity = self.verify_chain()
        return {
            "entity": self.entity_name,
            "n_chain_entries": len(self._chain),
            "chain_integrity_intact": integrity.is_intact,
            "n_period_seals": len(self._seals),
            "n_attestations_total": len(self._attestations),
            "n_attestations_attested_or_submitted": n_attested,
            "n_attestations_pending": n_pending,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_chain_3_entries() -> List[AuditTrailEntry]:
    chain: List[AuditTrailEntry] = []
    for i in range(3):
        e = append_entry(
            chain=chain, entry_id=f"E{i+1}",
            event_type=AuditTrailEventType.CONTROL_TEST_EXECUTED,
            timestamp_utc=f"2026-01-{i+1:02d}T10:00:00Z",
            actor_user_id="alice",
            source_engine="audit_core",
            target_object_type="ControlTestResult",
            target_object_id=f"T{i+1}",
            payload={"verdict": "EFFECTIVE"})
        chain.append(e)
    return chain


def _test_chain_genesis_has_empty_previous():
    chain = _make_chain_3_entries()
    assert chain[0].previous_hash == ""
    assert chain[0].sequence_number == 1


def _test_chain_links_via_previous_hash():
    chain = _make_chain_3_entries()
    assert chain[1].previous_hash == chain[0].entry_hash
    assert chain[2].previous_hash == chain[1].entry_hash


def _test_chain_sequence_monotonic():
    chain = _make_chain_3_entries()
    for i, entry in enumerate(chain):
        assert entry.sequence_number == i + 1


def _test_verify_intact_chain():
    chain = _make_chain_3_entries()
    result = verify_chain_integrity(chain=chain)
    assert result.is_intact
    assert result.n_entries_checked == 3


def _test_verify_empty_chain():
    result = verify_chain_integrity(chain=[])
    assert result.is_intact
    assert result.n_entries_checked == 0


def _test_verify_detects_tampered_payload():
    chain = _make_chain_3_entries()
    # Tamper with middle entry's payload
    tampered = AuditTrailEntry(
        entry_id=chain[1].entry_id,
        sequence_number=chain[1].sequence_number,
        event_type=chain[1].event_type,
        timestamp_utc=chain[1].timestamp_utc,
        actor_user_id="MALICIOUS",    # changed
        source_engine=chain[1].source_engine,
        target_object_type=chain[1].target_object_type,
        target_object_id=chain[1].target_object_id,
        payload_json=chain[1].payload_json,
        previous_hash=chain[1].previous_hash,
        entry_hash=chain[1].entry_hash)    # original hash, won't match
    chain[1] = tampered
    result = verify_chain_integrity(chain=chain)
    assert not result.is_intact
    assert result.first_break_sequence == 2
    assert "tamper" in result.first_break_reason.lower()


def _test_verify_detects_broken_sequence():
    chain = _make_chain_3_entries()
    # Skip sequence 2 — chain has 1, 3
    chain.pop(1)
    result = verify_chain_integrity(chain=chain)
    assert not result.is_intact


def _test_seal_period_basic():
    chain = _make_chain_3_entries()
    seal = seal_period(
        seal_id="S1", period_label="2026-Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        sealed_at_utc="2026-04-15T00:00:00Z",
        sealed_by_user_id="cae",
        chain=chain)
    assert seal.sealed_at_sequence == 3
    assert seal.sealed_chain_hash == chain[-1].entry_hash
    assert seal.n_entries_in_period == 3


def _test_seal_period_outside_period():
    chain = _make_chain_3_entries()    # Jan 1, 2, 3
    seal = seal_period(
        seal_id="S1", period_label="2026-Q4",
        period_start="2026-10-01", period_end="2026-12-31",
        sealed_at_utc="2027-01-15T00:00:00Z",
        sealed_by_user_id="cae",
        chain=chain)
    assert seal.n_entries_in_period == 0


def _test_seal_period_broken_chain_raises():
    chain = _make_chain_3_entries()
    chain.pop(1)    # break chain
    try:
        seal_period(
            seal_id="S1", period_label="2026-Q1",
            period_start="2026-01-01", period_end="2026-03-31",
            sealed_at_utc="2026-04-15T00:00:00Z",
            sealed_by_user_id="cae",
            chain=chain)
        assert False
    except ValueError as e:
        assert "chain integrity broken" in str(e)


def _test_seal_period_empty_chain():
    seal = seal_period(
        seal_id="S1", period_label="2026-Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        sealed_at_utc="2026-04-15T00:00:00Z",
        sealed_by_user_id="cae",
        chain=[])
    assert seal.n_entries_in_period == 0


def _test_required_signatures_sox_404():
    roles = DEFAULT_REQUIRED_SIGNATURES[ComplianceFramework.SOX_404]
    assert CertifierAttestationRole.CEO in roles
    assert CertifierAttestationRole.CFO in roles
    assert CertifierAttestationRole.CAE in roles


def _test_required_signatures_cbk_crmf():
    roles = DEFAULT_REQUIRED_SIGNATURES[ComplianceFramework.CBK_CRMF]
    assert CertifierAttestationRole.CEO in roles
    assert CertifierAttestationRole.CRO in roles
    assert CertifierAttestationRole.CCO in roles
    assert CertifierAttestationRole.CAE in roles


def _test_attestation_required_vs_signed():
    a = ComplianceAttestation(
        attestation_id="A1", framework=ComplianceFramework.SOX_302,
        period_label="2026-Q1", period_start="2026-01-01",
        period_end="2026-03-31",
        status=AttestationStatus.SIGNATURES_PENDING,
        period_seal_id="S1",
        chain_hash_at_attestation="abc")
    required = a.required_roles()
    assert len(required) == 2    # CEO + CFO for SOX 302
    missing = a.missing_signatures()
    assert len(missing) == 2


def _test_attestation_distinct_signers():
    a = ComplianceAttestation(
        attestation_id="A1", framework=ComplianceFramework.SOX_302,
        period_label="2026-Q1", period_start="2026-01-01",
        period_end="2026-03-31",
        status=AttestationStatus.SIGNATURES_PENDING,
        period_seal_id="S1",
        chain_hash_at_attestation="abc",
        signatures=(
            AttestationSignature(
                signature_id="SG1",
                role=CertifierAttestationRole.CEO,
                user_id="alice", signed_at_utc="t",
                signature_hash="h1"),
            AttestationSignature(
                signature_id="SG2",
                role=CertifierAttestationRole.CFO,
                user_id="alice",    # same user — duplicate
                signed_at_utc="t",
                signature_hash="h2"),
        ))
    assert not a.has_distinct_signers()


def _test_attestation_transition_valid():
    assert is_valid_attestation_transition(
        AttestationStatus.DRAFT, AttestationStatus.PREPARED)


def _test_attestation_transition_invalid_skip():
    """Cannot skip from DRAFT to ATTESTED."""
    assert not is_valid_attestation_transition(
        AttestationStatus.DRAFT, AttestationStatus.ATTESTED)


def _test_engine_full_certification_flow():
    eng = AuditTrailCertificationEngine()
    # Build chain
    eng.append_event(
        entry_id="E1",
        event_type=AuditTrailEventType.CONTROL_TEST_EXECUTED,
        timestamp_utc="2026-01-15T10:00:00Z",
        actor_user_id="alice", source_engine="audit_core",
        target_object_type="Test", target_object_id="T1",
        payload={"verdict": "EFFECTIVE"})
    # Seal period
    seal = eng.seal_period(
        seal_id="SEAL-Q1", period_label="2026-Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        sealed_at_utc="2026-04-15T00:00:00Z",
        sealed_by_user_id="cae")
    assert seal.n_entries_in_period == 1    # the test event
    # The PERIOD_SEALED event is added afterwards, so chain has 2 entries
    assert len(eng.chain()) == 2
    # File attestation
    attestation = ComplianceAttestation(
        attestation_id="A-Q1-SOX302",
        framework=ComplianceFramework.SOX_302,
        period_label="2026-Q1", period_start="2026-01-01",
        period_end="2026-03-31",
        status=AttestationStatus.DRAFT,
        period_seal_id="SEAL-Q1",
        chain_hash_at_attestation=seal.sealed_chain_hash,
        attestation_text="ICFR effective for Q1 2026")
    eng.file_attestation(attestation)
    # Walk through transitions
    for to_status in (
            AttestationStatus.PREPARED,
            AttestationStatus.REVIEWED,
            AttestationStatus.SIGNATURES_PENDING):
        eng.transition_attestation(
            attestation_id="A-Q1-SOX302",
            to_status=to_status,
            actor_user_id="cae",
            timestamp="t")
    # Add signatures (CEO + CFO required for SOX 302)
    eng.add_signature(
        attestation_id="A-Q1-SOX302",
        signature=AttestationSignature(
            signature_id="SG1",
            role=CertifierAttestationRole.CEO,
            user_id="ceo_user", signed_at_utc="t",
            signature_hash="h1"))
    eng.add_signature(
        attestation_id="A-Q1-SOX302",
        signature=AttestationSignature(
            signature_id="SG2",
            role=CertifierAttestationRole.CFO,
            user_id="cfo_user", signed_at_utc="t",
            signature_hash="h2"))
    # Now ATTEST
    eng.transition_attestation(
        attestation_id="A-Q1-SOX302",
        to_status=AttestationStatus.ATTESTED,
        actor_user_id="cae",
        timestamp="2026-04-20T00:00:00Z")
    final = eng.get_attestation("A-Q1-SOX302")
    assert final.status == AttestationStatus.ATTESTED
    assert final.is_fully_signed()
    assert final.has_distinct_signers()


def _test_engine_attest_without_signatures_blocked():
    eng = AuditTrailCertificationEngine()
    eng.file_attestation(ComplianceAttestation(
        attestation_id="A1",
        framework=ComplianceFramework.SOX_302,
        period_label="x", period_start="2026-01-01",
        period_end="2026-03-31",
        status=AttestationStatus.SIGNATURES_PENDING,
        period_seal_id="S1",
        chain_hash_at_attestation="abc"))
    try:
        eng.transition_attestation(
            attestation_id="A1",
            to_status=AttestationStatus.ATTESTED,
            actor_user_id="x", timestamp="t")
        assert False
    except ValueError as e:
        assert "missing signatures" in str(e)


def _test_engine_same_user_two_roles_blocked():
    eng = AuditTrailCertificationEngine()
    eng.file_attestation(ComplianceAttestation(
        attestation_id="A1",
        framework=ComplianceFramework.SOX_302,
        period_label="x", period_start="2026-01-01",
        period_end="2026-03-31",
        status=AttestationStatus.SIGNATURES_PENDING,
        period_seal_id="S1",
        chain_hash_at_attestation="abc",
        signatures=(
            AttestationSignature(
                signature_id="SG1",
                role=CertifierAttestationRole.CEO,
                user_id="dual_role_user", signed_at_utc="t",
                signature_hash="h1"),
            AttestationSignature(
                signature_id="SG2",
                role=CertifierAttestationRole.CFO,
                user_id="dual_role_user",    # SAME USER
                signed_at_utc="t", signature_hash="h2"),
        )))
    try:
        eng.transition_attestation(
            attestation_id="A1",
            to_status=AttestationStatus.ATTESTED,
            actor_user_id="x", timestamp="t")
        assert False
    except ValueError as e:
        assert "segregation of duties" in str(e).lower()


def _test_engine_add_unrequired_role_raises():
    eng = AuditTrailCertificationEngine()
    eng.file_attestation(ComplianceAttestation(
        attestation_id="A1",
        framework=ComplianceFramework.SOX_302,    # only CEO + CFO
        period_label="x", period_start="2026-01-01",
        period_end="2026-03-31",
        status=AttestationStatus.SIGNATURES_PENDING,
        period_seal_id="S1",
        chain_hash_at_attestation="abc"))
    try:
        eng.add_signature(
            attestation_id="A1",
            signature=AttestationSignature(
                signature_id="SG1",
                role=CertifierAttestationRole.CISO,    # not required for SOX 302
                user_id="ciso", signed_at_utc="t",
                signature_hash="h1"))
        assert False
    except ValueError as e:
        assert "not required" in str(e)


def _test_engine_board_summary_aggregates():
    eng = AuditTrailCertificationEngine()
    eng.append_event(
        entry_id="E1",
        event_type=AuditTrailEventType.CONTROL_TEST_EXECUTED,
        timestamp_utc="2026-01-01T00:00:00Z",
        actor_user_id="alice", source_engine="audit_core",
        target_object_type="Test", target_object_id="T1",
        payload={})
    s = eng.board_summary()
    assert s["n_chain_entries"] == 1
    assert s["chain_integrity_intact"]


def self_test() -> None:
    tests = [
        _test_chain_genesis_has_empty_previous,
        _test_chain_links_via_previous_hash,
        _test_chain_sequence_monotonic,
        _test_verify_intact_chain,
        _test_verify_empty_chain,
        _test_verify_detects_tampered_payload,
        _test_verify_detects_broken_sequence,
        _test_seal_period_basic,
        _test_seal_period_outside_period,
        _test_seal_period_broken_chain_raises,
        _test_seal_period_empty_chain,
        _test_required_signatures_sox_404,
        _test_required_signatures_cbk_crmf,
        _test_attestation_required_vs_signed,
        _test_attestation_distinct_signers,
        _test_attestation_transition_valid,
        _test_attestation_transition_invalid_skip,
        _test_engine_full_certification_flow,
        _test_engine_attest_without_signatures_blocked,
        _test_engine_same_user_two_roles_blocked,
        _test_engine_add_unrequired_role_raises,
        _test_engine_board_summary_aggregates,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ audit_trail_certification self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ audit_trail_certification self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

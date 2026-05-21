"""utils/audit_trail_cert.py — v10.27 Phase 2 batch 4 (Audit/GRC arc closure).

╔════════════════════════════════════════════════════════════════════════╗
║  HASH-CHAINED AUDIT TRAIL + MULTI-FRAMEWORK COMPLIANCE ATTESTATION    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (period-close attestation drives statutory          ║
║              filings + external audit reliance + capital adequacy     ║
║              certification; tampered audit trail = SOX §404 breach)   ║
║  Implements 1 of 17 Audit/GRC standards from registry:                  ║
║    ENH-210: Audit Trail & Compliance Certification                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Sarbanes-Oxley §302 — corporate responsibility (CEO/CFO sign-off)  ║
║    Sarbanes-Oxley §404 — internal control over financial reporting    ║
║    Sarbanes-Oxley §906 — corporate criminal certification             ║
║    PCAOB AS 2201 — audit of internal control over financial reporting║
║    IIA IPPF Standard 2440 — disseminating results                      ║
║    IIA IPPF Standard 2500 — monitoring progress                        ║
║    COSO Internal Control Integrated Framework — monitoring activities ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk              ║
║    CBK CRMF April 2021 §7.7 — audit committee + board reporting       ║
║    CBK Banking Act §43 — annual financial statements certification    ║
║    CBK Banking Act §44 — internal audit reporting                      ║
║    Basel BCBS 239 §11/§12 — accuracy + integrity                      ║
║    ISO 27001:2022 A.5.34 — privacy and protection of PII              ║
║    NIST SP 800-92 — log management (hash chain integrity)             ║
║    Federal Information Security Modernization Act (FISMA)              ║
║    Kenya Banking Act CAP 488 — books and records integrity            ║
║    Kenya Data Protection Act 2019 §41 — security of processing        ║
║    eIDAS Regulation (EU) — qualified electronic signatures            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.23 + v10.24 + v10.25 + v10.26 — full Audit/GRC stack║
║                                                                         ║
║  Honesty Rule 1: every trail entry surfaces actor + before/after;     ║
║  hash chain is verifiable post-hoc; broken chain raises explicitly.    ║
║  Honesty Rule 7: e-signature integrations (DocuSign, eIDAS QES) are   ║
║  callable hooks; without wiring, signatures are recorded as internal. ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "External e-signature integration (DocuSign, Adobe Sign, eIDAS QES) "
    "is via callable hook per Rule 7. Without wiring, signatures are "
    "recorded as internal sign-offs with cryptographic hash binding."
)

# Genesis hash for the start of any chain
GENESIS_HASH = "0" * 64


# ════════════════════════════════════════════════════════════════════════
# Hash-chained audit trail (ENH-210)
# ════════════════════════════════════════════════════════════════════════

class GRCEventType(Enum):
    """Types of GRC events recorded in the cumulative audit trail."""
    # From v10.23 audit_core
    ENTITY_REGISTERED = "ENTITY_REGISTERED"
    CONTROL_REGISTERED = "CONTROL_REGISTERED"
    CONTROL_TEST_EXECUTED = "CONTROL_TEST_EXECUTED"
    CONTROL_TEST_FAILED = "CONTROL_TEST_FAILED"
    WORKING_PAPER_FILED = "WORKING_PAPER_FILED"
    WORKING_PAPER_REVIEWED = "WORKING_PAPER_REVIEWED"
    CVR_RUN_COMPLETED = "CVR_RUN_COMPLETED"
    AUDIT_PLAN_BUILT = "AUDIT_PLAN_BUILT"
    # From v10.24
    ISSUE_RAISED = "ISSUE_RAISED"
    ISSUE_TRANSITIONED = "ISSUE_TRANSITIONED"
    ISSUE_CLOSED = "ISSUE_CLOSED"
    TICKET_CREATED = "TICKET_CREATED"
    FRAMEWORK_MAPPING_REGISTERED = "FRAMEWORK_MAPPING_REGISTERED"
    # From v10.25
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    BENFORD_TEST_RUN = "BENFORD_TEST_RUN"
    VENDOR_ASSESSED = "VENDOR_ASSESSED"
    CONCENTRATION_BREACH_DETECTED = "CONCENTRATION_BREACH_DETECTED"
    ALERT_RAISED = "ALERT_RAISED"
    ALERT_ACKNOWLEDGED = "ALERT_ACKNOWLEDGED"
    # From v10.26
    ENGAGEMENT_REGISTERED = "ENGAGEMENT_REGISTERED"
    EXTERNAL_ACCESS_GRANTED = "EXTERNAL_ACCESS_GRANTED"
    EXTERNAL_ACCESS_DENIED = "EXTERNAL_ACCESS_DENIED"
    COMMITTEE_REPORT_FILED = "COMMITTEE_REPORT_FILED"
    BOARD_DASHBOARD_GENERATED = "BOARD_DASHBOARD_GENERATED"
    # v10.27 period-close events
    PERIOD_CLOSE_INITIATED = "PERIOD_CLOSE_INITIATED"
    PERIOD_CLOSE_FINALIZED = "PERIOD_CLOSE_FINALIZED"
    ATTESTATION_PREPARED = "ATTESTATION_PREPARED"
    ATTESTATION_REVIEWED = "ATTESTATION_REVIEWED"
    ATTESTATION_APPROVED = "ATTESTATION_APPROVED"
    ATTESTATION_SIGNED = "ATTESTATION_SIGNED"
    EVIDENCE_PACK_ASSEMBLED = "EVIDENCE_PACK_ASSEMBLED"


def _canonical_payload(
    *,
    sequence_number: int,
    event_type: str,
    timestamp_utc: str,
    actor_user_id: str,
    actor_role: str,
    source_engine: str,
    target_object_type: str,
    target_object_id: str,
    before_state: str,
    after_state: str,
    previous_entry_hash: str,
    notes: str,
) -> str:
    """Canonical JSON serialization for hash computation.

    Sorted keys + no whitespace → deterministic bytes for SHA-256.
    """
    payload = {
        "seq": sequence_number,
        "type": event_type,
        "ts": timestamp_utc,
        "actor": actor_user_id,
        "role": actor_role,
        "engine": source_engine,
        "obj_type": target_object_type,
        "obj_id": target_object_id,
        "before": before_state,
        "after": after_state,
        "prev_hash": previous_entry_hash,
        "notes": notes,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_entry_hash(canonical_payload: str) -> str:
    """SHA-256 hex digest of canonical payload."""
    return hashlib.sha256(
        canonical_payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GRCAuditTrailEntry:
    """One immutable hash-chained audit trail entry.

    Per NIST SP 800-92 + Basel BCBS 239 — each entry's hash includes the
    previous entry's hash, creating a tamper-evident chain. Mutation of
    any earlier entry breaks the chain at every subsequent entry.
    """
    entry_id: str
    sequence_number: int                # monotonic, starts at 1
    event_type: GRCEventType
    timestamp_utc: str                   # ISO-8601
    actor_user_id: str
    actor_role: str
    source_engine: str                   # e.g., "audit_core", "audit_controls_issues"
    target_object_type: str              # e.g., "Control", "Issue", "Vendor"
    target_object_id: str
    before_state: str = ""
    after_state: str = ""
    previous_entry_hash: str = GENESIS_HASH
    this_entry_hash: str = ""
    notes: str = ""

    def canonical_payload(self) -> str:
        return _canonical_payload(
            sequence_number=self.sequence_number,
            event_type=self.event_type.value,
            timestamp_utc=self.timestamp_utc,
            actor_user_id=self.actor_user_id,
            actor_role=self.actor_role,
            source_engine=self.source_engine,
            target_object_type=self.target_object_type,
            target_object_id=self.target_object_id,
            before_state=self.before_state,
            after_state=self.after_state,
            previous_entry_hash=self.previous_entry_hash,
            notes=self.notes)

    def verify_self_hash(self) -> bool:
        """Verify that this entry's stored hash matches its content."""
        expected = compute_entry_hash(self.canonical_payload())
        return expected == self.this_entry_hash


def build_entry(
    *,
    entry_id: str,
    sequence_number: int,
    event_type: GRCEventType,
    timestamp_utc: str,
    actor_user_id: str,
    actor_role: str,
    source_engine: str,
    target_object_type: str,
    target_object_id: str,
    before_state: str = "",
    after_state: str = "",
    previous_entry_hash: str = GENESIS_HASH,
    notes: str = "",
) -> GRCAuditTrailEntry:
    """Build a fully-populated, hash-chained audit trail entry."""
    payload = _canonical_payload(
        sequence_number=sequence_number,
        event_type=event_type.value,
        timestamp_utc=timestamp_utc,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source_engine=source_engine,
        target_object_type=target_object_type,
        target_object_id=target_object_id,
        before_state=before_state,
        after_state=after_state,
        previous_entry_hash=previous_entry_hash,
        notes=notes)
    this_hash = compute_entry_hash(payload)
    return GRCAuditTrailEntry(
        entry_id=entry_id,
        sequence_number=sequence_number,
        event_type=event_type,
        timestamp_utc=timestamp_utc,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source_engine=source_engine,
        target_object_type=target_object_type,
        target_object_id=target_object_id,
        before_state=before_state,
        after_state=after_state,
        previous_entry_hash=previous_entry_hash,
        this_entry_hash=this_hash,
        notes=notes)


@dataclass(frozen=True)
class ChainIntegrityResult:
    """Result of verifying audit trail chain integrity."""
    is_intact: bool
    n_entries_checked: int
    first_broken_sequence: Optional[int] = None
    broken_reason: Optional[str] = None
    notes: str = ""


def verify_chain_integrity(
    entries: Sequence[GRCAuditTrailEntry],
) -> ChainIntegrityResult:
    """Walk the chain; verify each entry's hash + previous_hash linkage.

    Returns explicit ChainIntegrityResult — broken-where + broken-why
    surfaced. Per Rule 1, never silently passes a broken chain.
    """
    if not entries:
        return ChainIntegrityResult(
            is_intact=True, n_entries_checked=0,
            notes="empty trail (vacuously intact)")

    # Verify monotonic sequence + chain linkage
    expected_prev_hash = GENESIS_HASH
    for i, entry in enumerate(entries):
        # Sequence must be 1, 2, 3, ...
        if entry.sequence_number != i + 1:
            return ChainIntegrityResult(
                is_intact=False, n_entries_checked=i + 1,
                first_broken_sequence=entry.sequence_number,
                broken_reason=(
                    f"non-monotonic sequence: expected {i + 1}, "
                    f"got {entry.sequence_number}"))
        # Previous hash must match preceding entry's hash
        if entry.previous_entry_hash != expected_prev_hash:
            return ChainIntegrityResult(
                is_intact=False, n_entries_checked=i + 1,
                first_broken_sequence=entry.sequence_number,
                broken_reason=(
                    f"previous_entry_hash mismatch at seq "
                    f"{entry.sequence_number}: expected "
                    f"{expected_prev_hash[:8]}…, got "
                    f"{entry.previous_entry_hash[:8]}…"))
        # This entry's stored hash must match its computed hash
        if not entry.verify_self_hash():
            return ChainIntegrityResult(
                is_intact=False, n_entries_checked=i + 1,
                first_broken_sequence=entry.sequence_number,
                broken_reason=(
                    f"self-hash verification failed at seq "
                    f"{entry.sequence_number} — content tampered"))
        expected_prev_hash = entry.this_entry_hash

    return ChainIntegrityResult(
        is_intact=True, n_entries_checked=len(entries),
        notes=f"chain of {len(entries)} entries verified")


def compute_trail_seal_hash(
    entries: Sequence[GRCAuditTrailEntry],
) -> str:
    """Hash sealing the trail at a point in time.

    The seal hash = hash of (last_entry_hash + n_entries). Provides
    tamper-evident snapshot for period-end attestation.
    """
    if not entries:
        return GENESIS_HASH
    last = entries[-1]
    seal_input = f"{last.this_entry_hash}|{len(entries)}"
    return hashlib.sha256(seal_input.encode("utf-8")).hexdigest()


# ════════════════════════════════════════════════════════════════════════
# Multi-framework compliance attestation (ENH-210)
# ════════════════════════════════════════════════════════════════════════

class ComplianceFramework(Enum):
    """Frameworks against which periods may be attested."""
    SOX_404 = "SOX_404"
    SOX_302 = "SOX_302"
    SOX_906 = "SOX_906"
    COSO_IC = "COSO_IC"
    COSO_ERM = "COSO_ERM"
    PCAOB_AS_2201 = "PCAOB_AS_2201"
    ISO_27001 = "ISO_27001"
    ISO_27002 = "ISO_27002"
    NIST_CSF = "NIST_CSF"
    NIST_800_53 = "NIST_800_53"
    PCI_DSS = "PCI_DSS"
    CBK_CRMF = "CBK_CRMF"
    CBK_PG_02 = "CBK_PG_02"
    CBK_BANKING_ACT = "CBK_BANKING_ACT"
    BASEL_BCBS_239 = "BASEL_BCBS_239"
    GDPR = "GDPR"
    KENYA_DPA = "KENYA_DPA"
    EIDAS = "EIDAS"


class GRCCertifierRole(Enum):
    """Roles authorized to sign attestations.

    Per SOX §302 + §906, CEO + CFO must personally certify ICFR.
    Per CBK CRMF §7.7, audit committee chair signs off committee reports.
    Per IIA IPPF, CAE (Chief Audit Executive) signs internal audit work.
    """
    PREPARER = "PREPARER"                       # operations user
    REVIEWER = "REVIEWER"                       # team lead / audit manager
    APPROVER = "APPROVER"                       # senior audit manager
    CAE = "CAE"                                  # Chief Audit Executive
    CFO = "CFO"                                  # required for SOX §302/§906
    CEO = "CEO"                                  # required for SOX §302/§906
    CHAIR_AUDIT_COMMITTEE = "CHAIR_AUDIT_COMMITTEE"
    INTERNAL_AUDIT = "INTERNAL_AUDIT"
    EXTERNAL_AUDIT = "EXTERNAL_AUDIT"
    REGULATOR = "REGULATOR"                     # CBK supervisor


class AttestationStatus(Enum):
    """Lifecycle states for a period compliance attestation."""
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    SIGNED_BY_CFO = "SIGNED_BY_CFO"
    SIGNED_BY_CEO = "SIGNED_BY_CEO"
    EXTERNAL_AUDIT_VALIDATED = "EXTERNAL_AUDIT_VALIDATED"
    REJECTED = "REJECTED"
    REOPENED = "REOPENED"


# Allowed transitions for attestations
ALLOWED_ATTESTATION_TRANSITIONS: Mapping[
    AttestationStatus, Tuple[AttestationStatus, ...]] = {
    AttestationStatus.DRAFT: (
        AttestationStatus.PREPARED, AttestationStatus.REJECTED),
    AttestationStatus.PREPARED: (
        AttestationStatus.REVIEWED, AttestationStatus.REJECTED),
    AttestationStatus.REVIEWED: (
        AttestationStatus.APPROVED, AttestationStatus.REJECTED),
    AttestationStatus.APPROVED: (
        AttestationStatus.SIGNED_BY_CFO, AttestationStatus.REJECTED),
    AttestationStatus.SIGNED_BY_CFO: (
        AttestationStatus.SIGNED_BY_CEO, AttestationStatus.REJECTED),
    AttestationStatus.SIGNED_BY_CEO: (
        AttestationStatus.EXTERNAL_AUDIT_VALIDATED,),
    AttestationStatus.REJECTED: (AttestationStatus.REOPENED,),
    AttestationStatus.REOPENED: (AttestationStatus.PREPARED,),
    AttestationStatus.EXTERNAL_AUDIT_VALIDATED: (),  # terminal
}


def is_valid_attestation_transition(
    from_status: AttestationStatus,
    to_status: AttestationStatus,
) -> bool:
    return to_status in ALLOWED_ATTESTATION_TRANSITIONS.get(from_status, ())


@dataclass(frozen=True)
class AttestationSignoff:
    """One signature on a period attestation."""
    signoff_id: str
    attestation_id: str
    signer_user_id: str
    signer_role: GRCCertifierRole
    signed_at_utc: str
    decision: str                            # SIGNED / REJECTED / WITHHELD
    e_signature_provider: str = "INTERNAL"  # DOCUSIGN / ADOBE_SIGN / EIDAS_QES / INTERNAL
    e_signature_id: str = ""                 # external provider's signature ID
    signature_hash: str = ""                  # cryptographic binding
    notes: str = ""


@dataclass(frozen=True)
class PeriodComplianceAttestation:
    """Period-end attestation across one or more frameworks.

    Per SOX §404 + CBK CRMF §7.7 — periodic attestation with explicit:
      - period covered
      - frameworks attested
      - audit trail seal hash (cryptographic period-close)
      - sign-off chain (preparer → reviewer → approver → CFO → CEO)
      - findings count + unresolved-criticals count
    """
    attestation_id: str
    period_label: str                        # e.g., "Q1 2026"
    period_start: str                        # ISO-8601
    period_end: str
    frameworks_attested: Tuple[ComplianceFramework, ...]
    status: AttestationStatus
    audit_trail_seal_hash: str               # hash of trail at attestation
    n_trail_entries_at_seal: int
    signoffs: Tuple[AttestationSignoff, ...] = ()
    n_findings_in_period: int = 0
    n_unresolved_critical: int = 0
    n_unresolved_high: int = 0
    n_overdue_remediations: int = 0
    notes: str = ""

    def is_terminal(self) -> bool:
        return self.status == AttestationStatus.EXTERNAL_AUDIT_VALIDATED

    def has_role_signoff(self, role: GRCCertifierRole) -> bool:
        return any(
            s.signer_role == role and s.decision == "SIGNED"
            for s in self.signoffs)

    def is_sox_404_compliant(self) -> bool:
        """SOX §404 requires CEO + CFO sign-off."""
        return (self.has_role_signoff(GRCCertifierRole.CEO)
                  and self.has_role_signoff(GRCCertifierRole.CFO)
                  and ComplianceFramework.SOX_404 in self.frameworks_attested)

    def has_critical_findings_open(self) -> bool:
        return self.n_unresolved_critical > 0


def compute_signature_binding_hash(
    *,
    attestation_id: str,
    signer_user_id: str,
    signer_role: GRCCertifierRole,
    signed_at_utc: str,
    audit_trail_seal_hash: str,
) -> str:
    """Cryptographic binding of signature to attestation + trail seal.

    The signature_hash binds (signer + time + trail seal) so a signature
    can't be replayed against a different attestation or different trail
    state.
    """
    payload = (
        f"{attestation_id}|{signer_user_id}|{signer_role.value}"
        f"|{signed_at_utc}|{audit_trail_seal_hash}")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_signoff(
    *,
    signoff_id: str,
    attestation: PeriodComplianceAttestation,
    signer_user_id: str,
    signer_role: GRCCertifierRole,
    signed_at_utc: str,
    decision: str = "SIGNED",
    e_signature_provider: str = "INTERNAL",
    e_signature_callable: Optional[
        Callable[[str, str, str], Tuple[str, str]]] = None,
    notes: str = "",
) -> AttestationSignoff:
    """Create a signoff, optionally calling external e-sig provider.

    Per Rule 7 — without `e_signature_callable`, internal sign-off is
    recorded with cryptographic binding hash. Never fabricates a
    DocuSign envelope ID.
    """
    binding_hash = compute_signature_binding_hash(
        attestation_id=attestation.attestation_id,
        signer_user_id=signer_user_id,
        signer_role=signer_role,
        signed_at_utc=signed_at_utc,
        audit_trail_seal_hash=attestation.audit_trail_seal_hash)

    if e_signature_callable is None:
        return AttestationSignoff(
            signoff_id=signoff_id,
            attestation_id=attestation.attestation_id,
            signer_user_id=signer_user_id,
            signer_role=signer_role,
            signed_at_utc=signed_at_utc,
            decision=decision,
            e_signature_provider="INTERNAL",
            e_signature_id="",
            signature_hash=binding_hash,
            notes=(
                "internal sign-off — Rule 7: no external "
                "e-signature provider wired; cryptographic binding "
                "via hash only" if not notes else notes))

    try:
        ext_id, _provider_meta = e_signature_callable(
            attestation.attestation_id, signer_user_id, binding_hash)
    except Exception as e:
        return AttestationSignoff(
            signoff_id=signoff_id,
            attestation_id=attestation.attestation_id,
            signer_user_id=signer_user_id,
            signer_role=signer_role,
            signed_at_utc=signed_at_utc,
            decision="WITHHELD",
            e_signature_provider=e_signature_provider,
            e_signature_id="",
            signature_hash=binding_hash,
            notes=(
                f"external sig provider failed: "
                f"{type(e).__name__}: {e}"))

    return AttestationSignoff(
        signoff_id=signoff_id,
        attestation_id=attestation.attestation_id,
        signer_user_id=signer_user_id,
        signer_role=signer_role,
        signed_at_utc=signed_at_utc,
        decision=decision,
        e_signature_provider=e_signature_provider,
        e_signature_id=ext_id,
        signature_hash=binding_hash,
        notes=notes)


# ════════════════════════════════════════════════════════════════════════
# Evidence pack assembly
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EvidencePack:
    """A bundled evidence pack for regulatory submission or external audit.

    Per PCAOB AS 2201 + IIA IPPF — auditors must be able to retrieve
    period-specific evidence with cryptographic integrity proof.
    """
    pack_id: str
    period_label: str
    framework: ComplianceFramework
    pack_assembled_at_utc: str
    pack_assembled_by_user_id: str
    audit_trail_seal_hash: str
    n_trail_entries: int
    n_working_papers_referenced: int = 0
    n_test_results_referenced: int = 0
    n_issues_referenced: int = 0
    n_attestation_signoffs: int = 0
    pack_content_hash: str = ""              # hash of pack manifest
    notes: str = ""


def assemble_pack_content_hash(
    *,
    pack_id: str,
    period_label: str,
    framework: ComplianceFramework,
    audit_trail_seal_hash: str,
    n_trail_entries: int,
    n_working_papers: int,
    n_test_results: int,
    n_issues: int,
) -> str:
    """Compute SHA-256 of pack manifest for integrity verification."""
    manifest = (
        f"{pack_id}|{period_label}|{framework.value}|"
        f"{audit_trail_seal_hash}|{n_trail_entries}|"
        f"{n_working_papers}|{n_test_results}|{n_issues}")
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class AuditTrailCertEngine:
    """End-to-end orchestrator for hash-chained audit trail + attestation.

    Composes with v10.23/24/25/26 — receives events from any audit/GRC
    engine and appends to the cumulative chain. Provides period-end
    attestation surface with multi-framework certification.
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._trail: List[GRCAuditTrailEntry] = []
        self._attestations: Dict[str, PeriodComplianceAttestation] = {}
        self._packs: Dict[str, EvidencePack] = {}

    # ── Audit trail ────────────────────────────────────────────────────
    def append_event(
        self,
        *,
        event_type: GRCEventType,
        timestamp_utc: str,
        actor_user_id: str,
        actor_role: str,
        source_engine: str,
        target_object_type: str,
        target_object_id: str,
        before_state: str = "",
        after_state: str = "",
        notes: str = "",
    ) -> GRCAuditTrailEntry:
        """Append event to chain — maintains hash linkage automatically."""
        prev_hash = (
            self._trail[-1].this_entry_hash
            if self._trail else GENESIS_HASH)
        sequence = len(self._trail) + 1
        entry = build_entry(
            entry_id=f"AT-{sequence:08d}",
            sequence_number=sequence,
            event_type=event_type,
            timestamp_utc=timestamp_utc,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source_engine=source_engine,
            target_object_type=target_object_type,
            target_object_id=target_object_id,
            before_state=before_state,
            after_state=after_state,
            previous_entry_hash=prev_hash,
            notes=notes)
        self._trail.append(entry)
        return entry

    def trail_length(self) -> int:
        return len(self._trail)

    def verify_integrity(self) -> ChainIntegrityResult:
        return verify_chain_integrity(self._trail)

    def trail_seal_hash(self) -> str:
        return compute_trail_seal_hash(self._trail)

    def entries_in_period(
        self, *, period_start: str, period_end: str,
    ) -> Tuple[GRCAuditTrailEntry, ...]:
        """Return entries with timestamp in [period_start, period_end]."""
        return tuple(
            e for e in self._trail
            if period_start <= e.timestamp_utc <= period_end + "T23:59:59Z")

    # ── Attestation lifecycle ─────────────────────────────────────────
    def create_attestation(
        self,
        *,
        attestation_id: str,
        period_label: str,
        period_start: str,
        period_end: str,
        frameworks_attested: Sequence[ComplianceFramework],
        n_findings_in_period: int = 0,
        n_unresolved_critical: int = 0,
        n_unresolved_high: int = 0,
        n_overdue_remediations: int = 0,
    ) -> PeriodComplianceAttestation:
        """Create a new period attestation — seals trail at this moment."""
        if attestation_id in self._attestations:
            raise ValueError(
                f"attestation {attestation_id} already exists")
        seal = self.trail_seal_hash()
        att = PeriodComplianceAttestation(
            attestation_id=attestation_id,
            period_label=period_label,
            period_start=period_start, period_end=period_end,
            frameworks_attested=tuple(frameworks_attested),
            status=AttestationStatus.DRAFT,
            audit_trail_seal_hash=seal,
            n_trail_entries_at_seal=len(self._trail),
            n_findings_in_period=n_findings_in_period,
            n_unresolved_critical=n_unresolved_critical,
            n_unresolved_high=n_unresolved_high,
            n_overdue_remediations=n_overdue_remediations)
        self._attestations[attestation_id] = att

        # Log creation in chain
        self.append_event(
            event_type=GRCEventType.ATTESTATION_PREPARED,
            timestamp_utc=period_end + "T23:59:59Z",
            actor_user_id="system", actor_role="system",
            source_engine="audit_trail_cert",
            target_object_type="PeriodComplianceAttestation",
            target_object_id=attestation_id,
            before_state="(none)",
            after_state=AttestationStatus.DRAFT.value,
            notes=f"sealed at {seal[:16]}…")
        return att

    def transition_attestation(
        self,
        *,
        attestation_id: str,
        to_status: AttestationStatus,
        actor_user_id: str,
        actor_role: GRCCertifierRole,
        timestamp_utc: str,
        notes: str = "",
    ) -> PeriodComplianceAttestation:
        if attestation_id not in self._attestations:
            raise KeyError(
                f"attestation {attestation_id} not found")
        existing = self._attestations[attestation_id]
        if not is_valid_attestation_transition(
                existing.status, to_status):
            allowed = ALLOWED_ATTESTATION_TRANSITIONS.get(
                existing.status, ())
            raise ValueError(
                f"invalid attestation transition "
                f"{existing.status.value} → {to_status.value}; "
                f"allowed: {[s.value for s in allowed]}")

        # Record signoff for SIGNED_BY_* transitions
        new_signoffs = existing.signoffs
        if to_status in (
                AttestationStatus.SIGNED_BY_CFO,
                AttestationStatus.SIGNED_BY_CEO,
                AttestationStatus.EXTERNAL_AUDIT_VALIDATED):
            signoff = create_signoff(
                signoff_id=f"SO-{len(existing.signoffs) + 1:06d}",
                attestation=existing,
                signer_user_id=actor_user_id,
                signer_role=actor_role,
                signed_at_utc=timestamp_utc,
                decision="SIGNED", notes=notes)
            new_signoffs = existing.signoffs + (signoff,)

        updated = PeriodComplianceAttestation(
            attestation_id=existing.attestation_id,
            period_label=existing.period_label,
            period_start=existing.period_start,
            period_end=existing.period_end,
            frameworks_attested=existing.frameworks_attested,
            status=to_status,
            audit_trail_seal_hash=existing.audit_trail_seal_hash,
            n_trail_entries_at_seal=existing.n_trail_entries_at_seal,
            signoffs=new_signoffs,
            n_findings_in_period=existing.n_findings_in_period,
            n_unresolved_critical=existing.n_unresolved_critical,
            n_unresolved_high=existing.n_unresolved_high,
            n_overdue_remediations=existing.n_overdue_remediations,
            notes=existing.notes)
        self._attestations[attestation_id] = updated

        # Log transition in chain
        self.append_event(
            event_type=GRCEventType.ATTESTATION_SIGNED,
            timestamp_utc=timestamp_utc,
            actor_user_id=actor_user_id,
            actor_role=actor_role.value,
            source_engine="audit_trail_cert",
            target_object_type="PeriodComplianceAttestation",
            target_object_id=attestation_id,
            before_state=existing.status.value,
            after_state=to_status.value,
            notes=notes)
        return updated

    def get_attestation(
        self, attestation_id: str,
    ) -> PeriodComplianceAttestation:
        if attestation_id not in self._attestations:
            raise KeyError(
                f"attestation {attestation_id} not found")
        return self._attestations[attestation_id]

    def sox_404_compliant_attestations(
        self,
    ) -> Tuple[PeriodComplianceAttestation, ...]:
        return tuple(
            a for a in self._attestations.values()
            if a.is_sox_404_compliant())

    # ── Evidence packs ─────────────────────────────────────────────────
    def assemble_evidence_pack(
        self,
        *,
        pack_id: str,
        period_label: str,
        framework: ComplianceFramework,
        assembled_at_utc: str,
        assembled_by_user_id: str,
        n_working_papers: int = 0,
        n_test_results: int = 0,
        n_issues: int = 0,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> EvidencePack:
        """Assemble an evidence pack with cryptographic manifest hash."""
        if pack_id in self._packs:
            raise ValueError(f"pack {pack_id} already exists")
        # Count trail entries in period if specified
        if period_start and period_end:
            period_entries = self.entries_in_period(
                period_start=period_start, period_end=period_end)
            n_trail = len(period_entries)
        else:
            n_trail = len(self._trail)
        seal = self.trail_seal_hash()
        content_hash = assemble_pack_content_hash(
            pack_id=pack_id, period_label=period_label,
            framework=framework,
            audit_trail_seal_hash=seal,
            n_trail_entries=n_trail,
            n_working_papers=n_working_papers,
            n_test_results=n_test_results,
            n_issues=n_issues)
        pack = EvidencePack(
            pack_id=pack_id, period_label=period_label,
            framework=framework,
            pack_assembled_at_utc=assembled_at_utc,
            pack_assembled_by_user_id=assembled_by_user_id,
            audit_trail_seal_hash=seal,
            n_trail_entries=n_trail,
            n_working_papers_referenced=n_working_papers,
            n_test_results_referenced=n_test_results,
            n_issues_referenced=n_issues,
            pack_content_hash=content_hash,
            notes=f"sealed at trail length {n_trail}")
        self._packs[pack_id] = pack

        # Log in chain
        self.append_event(
            event_type=GRCEventType.EVIDENCE_PACK_ASSEMBLED,
            timestamp_utc=assembled_at_utc,
            actor_user_id=assembled_by_user_id,
            actor_role="auditor",
            source_engine="audit_trail_cert",
            target_object_type="EvidencePack",
            target_object_id=pack_id,
            before_state="(none)",
            after_state=f"sealed:{content_hash[:16]}…",
            notes=f"framework={framework.value}")
        return pack

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        integrity = self.verify_integrity()
        n_sox_compliant = len(self.sox_404_compliant_attestations())
        return {
            "entity": self.entity_name,
            "n_trail_entries": len(self._trail),
            "trail_intact": integrity.is_intact,
            "trail_seal_hash": self.trail_seal_hash(),
            "n_attestations": len(self._attestations),
            "n_sox_404_compliant_attestations": n_sox_compliant,
            "n_evidence_packs": len(self._packs),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_entry_inputs(seq=1, prev=GENESIS_HASH):
    return dict(
        entry_id=f"AT-{seq:08d}", sequence_number=seq,
        event_type=GRCEventType.CONTROL_REGISTERED,
        timestamp_utc=f"2026-04-23T10:00:{seq:02d}Z",
        actor_user_id="alice", actor_role="auditor",
        source_engine="audit_core",
        target_object_type="Control", target_object_id=f"CTRL-{seq}",
        before_state="(new)", after_state="active",
        previous_entry_hash=prev)


def _test_canonical_payload_deterministic():
    """Same inputs → identical canonical payload."""
    p1 = _canonical_payload(
        sequence_number=1, event_type="X",
        timestamp_utc="t", actor_user_id="a", actor_role="r",
        source_engine="e", target_object_type="T",
        target_object_id="ID", before_state="b",
        after_state="a", previous_entry_hash="P", notes="n")
    p2 = _canonical_payload(
        sequence_number=1, event_type="X",
        timestamp_utc="t", actor_user_id="a", actor_role="r",
        source_engine="e", target_object_type="T",
        target_object_id="ID", before_state="b",
        after_state="a", previous_entry_hash="P", notes="n")
    assert p1 == p2


def _test_compute_entry_hash_changes_with_content():
    h1 = compute_entry_hash("payload1")
    h2 = compute_entry_hash("payload2")
    assert h1 != h2
    assert len(h1) == 64    # SHA-256 hex


def _test_build_entry_self_hash_verifies():
    entry = build_entry(**_make_entry_inputs(seq=1))
    assert entry.verify_self_hash()


def _test_build_entry_includes_prev_hash():
    e1 = build_entry(**_make_entry_inputs(seq=1))
    e2 = build_entry(**_make_entry_inputs(
        seq=2, prev=e1.this_entry_hash))
    assert e2.previous_entry_hash == e1.this_entry_hash


def _test_chain_integrity_empty_passes():
    result = verify_chain_integrity([])
    assert result.is_intact
    assert result.n_entries_checked == 0


def _test_chain_integrity_valid_chain_passes():
    e1 = build_entry(**_make_entry_inputs(seq=1))
    e2 = build_entry(**_make_entry_inputs(
        seq=2, prev=e1.this_entry_hash))
    e3 = build_entry(**_make_entry_inputs(
        seq=3, prev=e2.this_entry_hash))
    result = verify_chain_integrity([e1, e2, e3])
    assert result.is_intact
    assert result.n_entries_checked == 3


def _test_chain_integrity_broken_seq_detected():
    """Non-monotonic sequence → broken."""
    e1 = build_entry(**_make_entry_inputs(seq=1))
    # Skip seq 2, jump to 3 (gap)
    e3 = build_entry(**_make_entry_inputs(
        seq=3, prev=e1.this_entry_hash))
    result = verify_chain_integrity([e1, e3])
    assert not result.is_intact
    assert "non-monotonic" in (result.broken_reason or "").lower()


def _test_chain_integrity_broken_link_detected():
    """previous_hash mismatch → broken."""
    e1 = build_entry(**_make_entry_inputs(seq=1))
    # e2 references wrong prev_hash
    e2 = build_entry(**_make_entry_inputs(
        seq=2, prev="wrong_hash_value"))
    result = verify_chain_integrity([e1, e2])
    assert not result.is_intact
    assert "previous_entry_hash mismatch" in (result.broken_reason or "")


def _test_chain_integrity_tampered_content_detected():
    """Modify entry content → self-hash mismatch."""
    e1 = build_entry(**_make_entry_inputs(seq=1))
    # Tamper: replace this_entry_hash with junk
    tampered = GRCAuditTrailEntry(
        entry_id=e1.entry_id,
        sequence_number=e1.sequence_number,
        event_type=e1.event_type,
        timestamp_utc=e1.timestamp_utc,
        actor_user_id="EVIL",    # tampered
        actor_role=e1.actor_role,
        source_engine=e1.source_engine,
        target_object_type=e1.target_object_type,
        target_object_id=e1.target_object_id,
        before_state=e1.before_state,
        after_state=e1.after_state,
        previous_entry_hash=e1.previous_entry_hash,
        this_entry_hash=e1.this_entry_hash)    # but kept original hash
    result = verify_chain_integrity([tampered])
    assert not result.is_intact
    assert "self-hash" in (result.broken_reason or "").lower()


def _test_trail_seal_empty_is_genesis():
    seal = compute_trail_seal_hash([])
    assert seal == GENESIS_HASH


def _test_trail_seal_changes_with_entries():
    e1 = build_entry(**_make_entry_inputs(seq=1))
    e2 = build_entry(**_make_entry_inputs(
        seq=2, prev=e1.this_entry_hash))
    seal1 = compute_trail_seal_hash([e1])
    seal2 = compute_trail_seal_hash([e1, e2])
    assert seal1 != seal2


def _test_attestation_transitions_terminal():
    assert (
        ALLOWED_ATTESTATION_TRANSITIONS[
            AttestationStatus.EXTERNAL_AUDIT_VALIDATED] == ())


def _test_attestation_valid_path():
    """DRAFT → PREPARED → REVIEWED → APPROVED → CFO → CEO → EXTERNAL."""
    path = [
        (AttestationStatus.DRAFT, AttestationStatus.PREPARED),
        (AttestationStatus.PREPARED, AttestationStatus.REVIEWED),
        (AttestationStatus.REVIEWED, AttestationStatus.APPROVED),
        (AttestationStatus.APPROVED, AttestationStatus.SIGNED_BY_CFO),
        (AttestationStatus.SIGNED_BY_CFO, AttestationStatus.SIGNED_BY_CEO),
        (AttestationStatus.SIGNED_BY_CEO,
              AttestationStatus.EXTERNAL_AUDIT_VALIDATED),
    ]
    for f, t in path:
        assert is_valid_attestation_transition(f, t)


def _test_attestation_invalid_skip():
    assert not is_valid_attestation_transition(
        AttestationStatus.DRAFT,
        AttestationStatus.SIGNED_BY_CEO)


def _test_signature_binding_hash_stable():
    h1 = compute_signature_binding_hash(
        attestation_id="A1", signer_user_id="ceo",
        signer_role=GRCCertifierRole.CEO,
        signed_at_utc="t1", audit_trail_seal_hash="seal_X")
    h2 = compute_signature_binding_hash(
        attestation_id="A1", signer_user_id="ceo",
        signer_role=GRCCertifierRole.CEO,
        signed_at_utc="t1", audit_trail_seal_hash="seal_X")
    assert h1 == h2


def _test_signature_binding_changes_with_seal():
    """Different trail seals → different signature bindings."""
    h1 = compute_signature_binding_hash(
        attestation_id="A1", signer_user_id="ceo",
        signer_role=GRCCertifierRole.CEO,
        signed_at_utc="t1", audit_trail_seal_hash="seal_A")
    h2 = compute_signature_binding_hash(
        attestation_id="A1", signer_user_id="ceo",
        signer_role=GRCCertifierRole.CEO,
        signed_at_utc="t1", audit_trail_seal_hash="seal_B")
    assert h1 != h2


def _test_create_signoff_no_callable_internal():
    """Rule 7 — without e_signature_callable, internal-only signoff."""
    att = PeriodComplianceAttestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,),
        status=AttestationStatus.APPROVED,
        audit_trail_seal_hash="seal_X",
        n_trail_entries_at_seal=10)
    so = create_signoff(
        signoff_id="SO1", attestation=att,
        signer_user_id="cfo", signer_role=GRCCertifierRole.CFO,
        signed_at_utc="t")
    assert so.e_signature_provider == "INTERNAL"
    assert so.e_signature_id == ""
    assert so.signature_hash != ""
    assert "Rule 7" in so.notes


def _test_create_signoff_with_callable():
    att = PeriodComplianceAttestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,),
        status=AttestationStatus.APPROVED,
        audit_trail_seal_hash="seal_X",
        n_trail_entries_at_seal=10)
    def fake_sig(att_id, signer, binding):
        return ("ENV-12345", "DocuSign envelope")
    so = create_signoff(
        signoff_id="SO1", attestation=att,
        signer_user_id="cfo", signer_role=GRCCertifierRole.CFO,
        signed_at_utc="t", e_signature_provider="DOCUSIGN",
        e_signature_callable=fake_sig)
    assert so.e_signature_id == "ENV-12345"
    assert so.e_signature_provider == "DOCUSIGN"


def _test_create_signoff_callable_failure():
    att = PeriodComplianceAttestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,),
        status=AttestationStatus.APPROVED,
        audit_trail_seal_hash="seal_X",
        n_trail_entries_at_seal=10)
    def failing(*args):
        raise ConnectionError("DocuSign API down")
    so = create_signoff(
        signoff_id="SO1", attestation=att,
        signer_user_id="cfo", signer_role=GRCCertifierRole.CFO,
        signed_at_utc="t", e_signature_provider="DOCUSIGN",
        e_signature_callable=failing)
    assert so.decision == "WITHHELD"
    assert "ConnectionError" in so.notes


def _test_attestation_sox_404_compliance_requires_ceo_cfo():
    att = PeriodComplianceAttestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,),
        status=AttestationStatus.SIGNED_BY_CFO,
        audit_trail_seal_hash="seal_X",
        n_trail_entries_at_seal=10,
        signoffs=(
            AttestationSignoff(
                signoff_id="SO1", attestation_id="A1",
                signer_user_id="cfo",
                signer_role=GRCCertifierRole.CFO,
                signed_at_utc="t", decision="SIGNED"),
        ))
    # Only CFO signed → not yet SOX 404 compliant
    assert not att.is_sox_404_compliant()


def _test_attestation_sox_404_compliant_when_both_signed():
    att = PeriodComplianceAttestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,),
        status=AttestationStatus.SIGNED_BY_CEO,
        audit_trail_seal_hash="seal_X",
        n_trail_entries_at_seal=10,
        signoffs=(
            AttestationSignoff(
                signoff_id="SO1", attestation_id="A1",
                signer_user_id="cfo",
                signer_role=GRCCertifierRole.CFO,
                signed_at_utc="t1", decision="SIGNED"),
            AttestationSignoff(
                signoff_id="SO2", attestation_id="A1",
                signer_user_id="ceo",
                signer_role=GRCCertifierRole.CEO,
                signed_at_utc="t2", decision="SIGNED"),
        ))
    assert att.is_sox_404_compliant()


def _test_attestation_critical_findings_blocked():
    att = PeriodComplianceAttestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,),
        status=AttestationStatus.DRAFT,
        audit_trail_seal_hash="seal",
        n_trail_entries_at_seal=10,
        n_unresolved_critical=3)
    assert att.has_critical_findings_open()


def _test_engine_append_chains_correctly():
    eng = AuditTrailCertEngine()
    e1 = eng.append_event(
        event_type=GRCEventType.CONTROL_REGISTERED,
        timestamp_utc="2026-01-01T10:00:00Z",
        actor_user_id="alice", actor_role="auditor",
        source_engine="audit_core",
        target_object_type="Control", target_object_id="C1")
    e2 = eng.append_event(
        event_type=GRCEventType.CONTROL_TEST_EXECUTED,
        timestamp_utc="2026-01-01T11:00:00Z",
        actor_user_id="alice", actor_role="auditor",
        source_engine="audit_core",
        target_object_type="ControlTestResult", target_object_id="T1")
    assert e1.sequence_number == 1
    assert e2.sequence_number == 2
    assert e2.previous_entry_hash == e1.this_entry_hash


def _test_engine_integrity_check():
    eng = AuditTrailCertEngine()
    for i in range(5):
        eng.append_event(
            event_type=GRCEventType.CONTROL_REGISTERED,
            timestamp_utc=f"2026-01-{i+1:02d}T10:00:00Z",
            actor_user_id="alice", actor_role="auditor",
            source_engine="audit_core",
            target_object_type="Control",
            target_object_id=f"C{i}")
    integrity = eng.verify_integrity()
    assert integrity.is_intact
    assert integrity.n_entries_checked == 5


def _test_engine_create_attestation():
    eng = AuditTrailCertEngine()
    eng.append_event(
        event_type=GRCEventType.CONTROL_REGISTERED,
        timestamp_utc="2026-01-15T10:00:00Z",
        actor_user_id="alice", actor_role="auditor",
        source_engine="audit_core",
        target_object_type="Control", target_object_id="C1")
    att = eng.create_attestation(
        attestation_id="ATT-2026-Q1",
        period_label="Q1 2026",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(
            ComplianceFramework.SOX_404,
            ComplianceFramework.CBK_CRMF))
    assert att.status == AttestationStatus.DRAFT
    assert att.n_trail_entries_at_seal == 1
    # Trail should have grown by 1 (the ATTESTATION_PREPARED log)
    assert eng.trail_length() == 2


def _test_engine_attestation_full_signoff_path():
    eng = AuditTrailCertEngine()
    eng.create_attestation(
        attestation_id="ATT-2026-Q1",
        period_label="Q1 2026",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,))
    # Walk through full path
    eng.transition_attestation(
        attestation_id="ATT-2026-Q1",
        to_status=AttestationStatus.PREPARED,
        actor_user_id="cae", actor_role=GRCCertifierRole.PREPARER,
        timestamp_utc="t1")
    eng.transition_attestation(
        attestation_id="ATT-2026-Q1",
        to_status=AttestationStatus.REVIEWED,
        actor_user_id="senior_audit",
        actor_role=GRCCertifierRole.REVIEWER, timestamp_utc="t2")
    eng.transition_attestation(
        attestation_id="ATT-2026-Q1",
        to_status=AttestationStatus.APPROVED,
        actor_user_id="cae", actor_role=GRCCertifierRole.CAE,
        timestamp_utc="t3")
    eng.transition_attestation(
        attestation_id="ATT-2026-Q1",
        to_status=AttestationStatus.SIGNED_BY_CFO,
        actor_user_id="cfo_user", actor_role=GRCCertifierRole.CFO,
        timestamp_utc="t4")
    eng.transition_attestation(
        attestation_id="ATT-2026-Q1",
        to_status=AttestationStatus.SIGNED_BY_CEO,
        actor_user_id="ceo_user", actor_role=GRCCertifierRole.CEO,
        timestamp_utc="t5")
    att = eng.get_attestation("ATT-2026-Q1")
    assert att.status == AttestationStatus.SIGNED_BY_CEO
    assert att.is_sox_404_compliant()


def _test_engine_invalid_skip_raises():
    eng = AuditTrailCertEngine()
    eng.create_attestation(
        attestation_id="A1", period_label="Q1",
        period_start="2026-01-01", period_end="2026-03-31",
        frameworks_attested=(ComplianceFramework.SOX_404,))
    try:
        # DRAFT → SIGNED_BY_CEO is invalid
        eng.transition_attestation(
            attestation_id="A1",
            to_status=AttestationStatus.SIGNED_BY_CEO,
            actor_user_id="x", actor_role=GRCCertifierRole.CEO,
            timestamp_utc="t")
        assert False
    except ValueError:
        pass


def _test_engine_evidence_pack_assembly():
    eng = AuditTrailCertEngine()
    eng.append_event(
        event_type=GRCEventType.CONTROL_TEST_EXECUTED,
        timestamp_utc="2026-01-15T10:00:00Z",
        actor_user_id="alice", actor_role="auditor",
        source_engine="audit_core",
        target_object_type="ControlTestResult",
        target_object_id="T1")
    pack = eng.assemble_evidence_pack(
        pack_id="PACK-001", period_label="Q1 2026",
        framework=ComplianceFramework.SOX_404,
        assembled_at_utc="2026-04-01T10:00:00Z",
        assembled_by_user_id="alice",
        n_test_results=1)
    assert pack.n_trail_entries == 1
    assert len(pack.pack_content_hash) == 64    # SHA-256


def _test_engine_board_summary_intact_chain():
    eng = AuditTrailCertEngine()
    for i in range(3):
        eng.append_event(
            event_type=GRCEventType.CONTROL_REGISTERED,
            timestamp_utc=f"2026-01-{i+1:02d}T10:00:00Z",
            actor_user_id="alice", actor_role="auditor",
            source_engine="audit_core",
            target_object_type="Control", target_object_id=f"C{i}")
    s = eng.board_summary()
    assert s["n_trail_entries"] == 3
    assert s["trail_intact"] is True


def _test_pack_content_hash_changes_with_inputs():
    h1 = assemble_pack_content_hash(
        pack_id="P1", period_label="Q1",
        framework=ComplianceFramework.SOX_404,
        audit_trail_seal_hash="seal", n_trail_entries=10,
        n_working_papers=5, n_test_results=3, n_issues=1)
    h2 = assemble_pack_content_hash(
        pack_id="P1", period_label="Q1",
        framework=ComplianceFramework.SOX_404,
        audit_trail_seal_hash="seal", n_trail_entries=10,
        n_working_papers=5, n_test_results=3, n_issues=2)   # changed
    assert h1 != h2


def self_test() -> None:
    tests = [
        _test_canonical_payload_deterministic,
        _test_compute_entry_hash_changes_with_content,
        _test_build_entry_self_hash_verifies,
        _test_build_entry_includes_prev_hash,
        _test_chain_integrity_empty_passes,
        _test_chain_integrity_valid_chain_passes,
        _test_chain_integrity_broken_seq_detected,
        _test_chain_integrity_broken_link_detected,
        _test_chain_integrity_tampered_content_detected,
        _test_trail_seal_empty_is_genesis,
        _test_trail_seal_changes_with_entries,
        _test_attestation_transitions_terminal,
        _test_attestation_valid_path,
        _test_attestation_invalid_skip,
        _test_signature_binding_hash_stable,
        _test_signature_binding_changes_with_seal,
        _test_create_signoff_no_callable_internal,
        _test_create_signoff_with_callable,
        _test_create_signoff_callable_failure,
        _test_attestation_sox_404_compliance_requires_ceo_cfo,
        _test_attestation_sox_404_compliant_when_both_signed,
        _test_attestation_critical_findings_blocked,
        _test_engine_append_chains_correctly,
        _test_engine_integrity_check,
        _test_engine_create_attestation,
        _test_engine_attestation_full_signoff_path,
        _test_engine_invalid_skip_raises,
        _test_engine_evidence_pack_assembly,
        _test_engine_board_summary_intact_chain,
        _test_pack_content_hash_changes_with_inputs,
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
        print(f"✗ audit_trail_cert self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ audit_trail_cert self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

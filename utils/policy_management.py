"""utils/policy_management.py — ENH-196 Policy Management & Attestation.

================================================================================
A2Z MIS 360 — ENH-196 Policy Management & Attestation Engine
================================================================================

Centralized policy repository with version control + attestation
tracking. Bridges regulatory drivers (ENH-195) and institution's
actual policy implementation.

CRITICAL DESIGN DECISION
------------------------
This engine tracks POLICY METADATA — title, version, owner, content
hash, attestation cycles. It does NOT store the actual policy PDF/Doc
content. That's operator-side document management (existing
`utils/document_management.py` engine handles document lifecycle for
loan docs etc.). v10.167 wires meta-only — operators can integrate
document_management later.

LIFECYCLE
---------
A policy moves through:

    DRAFT          (operator drafted; not yet circulated for review)
        →  IN_REVIEW    (committee reviewing; comments collected)
            →  ACTIVE   (approved + published; attestation cycle starts)
                →  SUPERSEDED  (newer version replaces; old kept for audit)
                →  RETIRED     (policy formally withdrawn; not replaced)

Backwards transitions rejected. SUPERSEDED + RETIRED are terminal
(once a policy version is superseded, that VERSION is closed; a NEW
version starts the lifecycle fresh).

ATTESTATION CYCLES
------------------
Every ACTIVE policy needs periodic attestation by its assigned
attestor(s). Default cycle 365 days (annual); operator can override
per policy. Engine surfaces overdue attestations.

Each attestation is recorded with:
- attestor_id (who)
- attested_at_utc (when)
- evidence (free-text or signature method label — actual e-signature
  verification is honestly deferred)

REGULATORY ALIGNMENT
--------------------
- CBK Prudential Guideline CBK/PG/01 — Corporate Governance §3
  (board-approved policies, periodic review)
- CBK PG/15 — AML/CFT policy attestation
- Companies Act §145 — board responsibility for compliance policies
- FATF Recommendation 18 — internal control + audit functions

BIDIRECTIONAL LINKAGE WITH ENH-195
-----------------------------------
ENH-195 references policies via affected_policies tuple of strings.
ENH-196 lets operators query: "what regulatory changes drove this
policy version?" via the related_change_ids field on each policy
version. Currently UNI-DIRECTIONAL via change_ids — operators wire
the link at policy-update time. Full reverse-lookup (ENH-195 query
"which policies are linked to this regulatory change") is left to
operator joins because the engines are independent.

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


class PolicyStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"


class AttestationOutcome(str, Enum):
    OK = "OK"
    REJECTED_POLICY_NOT_ACTIVE = "REJECTED_POLICY_NOT_ACTIVE"
    REJECTED_EVIDENCE_REQUIRED = "REJECTED_EVIDENCE_REQUIRED"
    REJECTED_POLICY_NOT_FOUND = "REJECTED_POLICY_NOT_FOUND"


# Allowed lifecycle transitions
ALLOWED_TRANSITIONS: Mapping[PolicyStatus, Tuple[PolicyStatus, ...]] = {
    PolicyStatus.DRAFT: (PolicyStatus.IN_REVIEW, PolicyStatus.RETIRED),
    PolicyStatus.IN_REVIEW: (PolicyStatus.ACTIVE,
                                PolicyStatus.DRAFT,  # back to draft on rejection
                                PolicyStatus.RETIRED),
    PolicyStatus.ACTIVE: (PolicyStatus.SUPERSEDED, PolicyStatus.RETIRED),
    PolicyStatus.SUPERSEDED: (),
    PolicyStatus.RETIRED: (),
}

DEFAULT_ATTESTATION_CYCLE_DAYS = 365


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttestationRecord:
    """A single attestation event recorded against an ACTIVE policy."""
    attestor_id: str
    attested_at_utc: str
    evidence: str          # signature method, signed-by-method, etc.
    next_attestation_due_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attestor_id": self.attestor_id,
            "attested_at_utc": self.attested_at_utc,
            "evidence": self.evidence,
            "next_attestation_due_utc": self.next_attestation_due_utc,
        }


@dataclass(frozen=True)
class Policy:
    """A policy artifact — metadata + version + attestation history.

    A new "version" of a policy is registered as a SEPARATE Policy
    record with the same policy_id but different version_id. The
    engine maintains the chain via supersedes_version_id field.
    """
    policy_id: str           # logical policy identifier (e.g. POL-KYC-001)
    version_id: str          # version label (e.g. "v3.2", "2026-Q2")
    title: str
    summary: str
    owner_role: str          # responsible role (e.g. "head_of_compliance")
    content_hash: str        # operator-supplied SHA-256 of policy doc
    effective_date: str      # YYYY-MM-DD
    status: PolicyStatus
    attestor_ids: Tuple[str, ...]   # who must attest
    attestation_cycle_days: int     # default 365
    related_change_ids: Tuple[str, ...]  # links to ENH-195 changes
    supersedes_version_id: str       # "" if first version
    registered_at_utc: str
    activated_at_utc: str            # set when status→ACTIVE
    superseded_at_utc: str           # set when superseded
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    attestations: Tuple[AttestationRecord, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version_id": self.version_id,
            "title": self.title,
            "summary": self.summary,
            "owner_role": self.owner_role,
            "content_hash": self.content_hash,
            "effective_date": self.effective_date,
            "status": self.status.value,
            "attestor_ids": list(self.attestor_ids),
            "attestation_cycle_days": self.attestation_cycle_days,
            "related_change_ids": list(self.related_change_ids),
            "supersedes_version_id": self.supersedes_version_id,
            "registered_at_utc": self.registered_at_utc,
            "activated_at_utc": self.activated_at_utc,
            "superseded_at_utc": self.superseded_at_utc,
            "transition_log": [dict(t) for t in self.transition_log],
            "attestations": [a.to_dict() for a in self.attestations],
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PolicyManagementEngine:
    """ENH-196 Policy Management & Attestation Engine.

    Each (policy_id, version_id) pair is a unique Policy record.

    Use:
        engine = PolicyManagementEngine()
        policy = engine.register_policy(
            policy_id="POL-KYC-001",
            version_id="v3.0",
            title="...",
            owner_role="head_of_compliance",
            content_hash="abc123...",
            effective_date="2026-07-01",
            attestor_ids=("head_of_compliance", "head_of_risk"),
            related_change_ids=("REG-000001",),  # links to ENH-195
        )
        engine.transition(policy_id, version_id, PolicyStatus.IN_REVIEW, ...)
        engine.transition(policy_id, version_id, PolicyStatus.ACTIVE, ...)
        engine.record_attestation(policy_id, version_id,
                                       attestor_id="head_of_compliance",
                                       evidence="DocuSign envelope #ABC")
    """

    DOCUMENT_STORAGE_STATUS = (
        "META_ONLY — engine tracks policy metadata (title, version, "
        "owner, content_hash for tamper detection). Actual policy "
        "PDF/document storage is operator-side via existing "
        "utils/document_management.py engine. v10.167 ships meta-only; "
        "wiring document_management bidirectional is future work.")

    ESIGNATURE_VERIFICATION_STATUS = (
        "DEFERRED — attestation evidence field accepts free-text "
        "(signature method label, signed-by-method). Actual digital "
        "signature verification (DocuSign API, X.509 certificate "
        "validation, ZetaWord) is operator-side. v10.167 ships "
        "evidence capture; signature verification is future work.")

    def __init__(self) -> None:
        # Key: (policy_id, version_id) → Policy
        self._policies: Dict[Tuple[str, str], Policy] = {}

    # ------------------------------------------------------------------
    # Register a new policy version
    # ------------------------------------------------------------------

    def register_policy(
        self,
        policy_id: str,
        version_id: str,
        title: str,
        summary: str,
        owner_role: str,
        content_hash: str,
        effective_date: str,
        attestor_ids: Tuple[str, ...] = (),
        attestation_cycle_days: int = DEFAULT_ATTESTATION_CYCLE_DAYS,
        related_change_ids: Tuple[str, ...] = (),
        supersedes_version_id: str = "",
    ) -> Policy:
        if not policy_id.strip():
            raise ValueError("policy_id required")
        if not version_id.strip():
            raise ValueError("version_id required")
        if not title.strip():
            raise ValueError("title required")
        if not owner_role.strip():
            raise ValueError("owner_role required")
        if not content_hash.strip():
            raise ValueError(
                "content_hash required — tamper-detection hash of "
                "the actual policy document")
        if not attestor_ids:
            raise ValueError(
                "at least one attestor_id required per CBK PG/01 §3 "
                "policy ownership requirements")
        if attestation_cycle_days < 1:
            raise ValueError(
                "attestation_cycle_days must be >= 1 day")

        key = (policy_id, version_id)
        if key in self._policies:
            raise ValueError(
                f"policy version already registered: {policy_id} "
                f"{version_id}")

        now_utc = datetime.now(timezone.utc).isoformat()

        policy = Policy(
            policy_id=policy_id, version_id=version_id,
            title=title.strip(), summary=summary.strip(),
            owner_role=owner_role.strip(),
            content_hash=content_hash.strip(),
            effective_date=effective_date,
            status=PolicyStatus.DRAFT,
            attestor_ids=tuple(attestor_ids),
            attestation_cycle_days=attestation_cycle_days,
            related_change_ids=tuple(related_change_ids),
            supersedes_version_id=supersedes_version_id,
            registered_at_utc=now_utc,
            activated_at_utc="",
            superseded_at_utc="",
            transition_log=(
                {"to_status": "DRAFT", "at_utc": now_utc,
                 "user": "system",
                 "reason": "initial registration"},),
            meta={"engine_version": "ENH-196-v10.167"},
        )
        self._policies[key] = policy
        return policy

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        policy_id: str,
        version_id: str,
        new_status: PolicyStatus,
        user: str,
        reason: str = "",
    ) -> Tuple[TransitionOutcome, Optional[Policy]]:
        key = (policy_id, version_id)
        if key not in self._policies:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)

        current = self._policies[key]
        if new_status not in ALLOWED_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)

        # RETIRED requires reason; SUPERSEDED is from new-version flow
        if new_status == PolicyStatus.RETIRED and not reason.strip():
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
        if new_status == PolicyStatus.ACTIVE:
            kwargs["activated_at_utc"] = now_utc
        elif new_status == PolicyStatus.SUPERSEDED:
            kwargs["superseded_at_utc"] = now_utc

        updated = Policy(**kwargs)
        self._policies[key] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Attestation recording
    # ------------------------------------------------------------------

    def record_attestation(
        self,
        policy_id: str,
        version_id: str,
        attestor_id: str,
        evidence: str,
    ) -> Tuple[AttestationOutcome, Optional[Policy]]:
        key = (policy_id, version_id)
        if key not in self._policies:
            return (AttestationOutcome.REJECTED_POLICY_NOT_FOUND, None)

        current = self._policies[key]
        if current.status != PolicyStatus.ACTIVE:
            return (AttestationOutcome.REJECTED_POLICY_NOT_ACTIVE,
                    current)
        if not evidence.strip():
            return (AttestationOutcome.REJECTED_EVIDENCE_REQUIRED,
                    current)

        now_dt = datetime.now(timezone.utc)
        next_due = now_dt + timedelta(
            days=current.attestation_cycle_days)
        record = AttestationRecord(
            attestor_id=attestor_id,
            attested_at_utc=now_dt.isoformat(),
            evidence=evidence.strip(),
            next_attestation_due_utc=next_due.isoformat(),
        )

        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["attestations"] = current.attestations + (record,)
        updated = Policy(**kwargs)
        self._policies[key] = updated
        return (AttestationOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Retrieval / portfolio
    # ------------------------------------------------------------------

    def policy_by_version(self, policy_id: str,
                            version_id: str) -> Policy:
        key = (policy_id, version_id)
        if key not in self._policies:
            raise KeyError(f"not found: {policy_id} {version_id}")
        return self._policies[key]

    def all_policies(self) -> Tuple[Policy, ...]:
        return tuple(self._policies.values())

    def active_policies(self) -> Tuple[Policy, ...]:
        return tuple(
            p for p in self._policies.values()
            if p.status == PolicyStatus.ACTIVE)

    def overdue_attestations(self) -> Tuple[Policy, ...]:
        """ACTIVE policies past their next_attestation_due deadline.

        Considers the latest attestation record per (policy, attestor).
        If no attestation exists yet, the deadline is
        activated_at_utc + cycle_days.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        overdue: List[Policy] = []
        for p in self._policies.values():
            if p.status != PolicyStatus.ACTIVE:
                continue
            if not p.attestor_ids:
                continue
            # Compute deadline per attestor; if any attestor's latest
            # attestation is overdue, the policy is overdue
            latest_per_attestor: Dict[str, str] = {}
            for a in p.attestations:
                latest_per_attestor[a.attestor_id] = (
                    a.next_attestation_due_utc)
            for attestor in p.attestor_ids:
                if attestor not in latest_per_attestor:
                    # Never attested → deadline = activated_at +
                    # cycle_days
                    if p.activated_at_utc:
                        try:
                            act_dt = datetime.fromisoformat(
                                p.activated_at_utc.replace(
                                    "Z", "+00:00"))
                            deadline = (act_dt + timedelta(
                                days=p.attestation_cycle_days)
                                          ).isoformat()
                            if deadline < now_utc:
                                overdue.append(p)
                                break
                        except (ValueError, AttributeError):
                            pass
                else:
                    if latest_per_attestor[attestor] < now_utc:
                        overdue.append(p)
                        break
        return tuple(overdue)

    def policies_for_change(
            self, change_id: str) -> Tuple[Policy, ...]:
        """Reverse-lookup: which policies link to this regulatory
        change? Provides the bidirectional linkage with ENH-195."""
        return tuple(
            p for p in self._policies.values()
            if change_id in p.related_change_ids)

    def board_summary(self) -> Dict[str, Any]:
        policies = list(self._policies.values())
        n_total = len(policies)
        n_active = sum(1 for p in policies
                        if p.status == PolicyStatus.ACTIVE)
        n_draft = sum(1 for p in policies
                       if p.status == PolicyStatus.DRAFT)
        n_review = sum(1 for p in policies
                        if p.status == PolicyStatus.IN_REVIEW)
        n_overdue = len(self.overdue_attestations())

        # Total attestations recorded
        n_attestations = sum(len(p.attestations) for p in policies)

        # Unique policy_ids (vs versions)
        unique_policy_ids = {p.policy_id for p in policies}

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-196 PolicyManagementEngine",
            "n_unique_policies": len(unique_policy_ids),
            "n_total_versions": n_total,
            "n_active_versions": n_active,
            "n_draft_versions": n_draft,
            "n_in_review_versions": n_review,
            "n_overdue_attestations": n_overdue,
            "n_attestations_recorded": n_attestations,
            "document_storage_status": self.DOCUMENT_STORAGE_STATUS,
            "esignature_verification_status": (
                self.ESIGNATURE_VERIFICATION_STATUS),
            "regulatory_basis": (
                "CBK PG/01 §3 (Corporate Governance — board-approved "
                "policies, periodic review), CBK PG/15 (AML/CFT "
                "policy attestation), Companies Act §145 (board "
                "responsibility), FATF Recommendation 18 (internal "
                "control + audit functions)"),
        }

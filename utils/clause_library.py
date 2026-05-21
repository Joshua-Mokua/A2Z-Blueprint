"""utils/clause_library.py — ENH-226 Clause Library & Playbooks.

Fifth Legal arc engine. Approved clauses library, position playbooks
per agreement type, fallback positions, prohibited clauses. Version-
controlled, change-managed.

DESIGN
------
Three-entity engine: Clause (an individual approved drafting
position), Playbook (a curated bundle of clauses for a specific
agreement type with negotiation guidance), and ClauseRevision
(immutable history per clause).

LIFECYCLE — Clause version
    DRAFT → UNDER_REVIEW → APPROVED → RETIRED
    (FALLBACK and PROHIBITED are clause classifications, not
     statuses — they live alongside APPROVED in the library)

ClauseClassification:
    APPROVED       — preferred drafting position
    FALLBACK       — acceptable negotiated alternative
    PROHIBITED     — must never appear in our agreements

REGULATORY ALIGNMENT
- CBK Risk Management Guidelines — operational risk from inconsistent
  contract drafting
- Companies Act §145 — director duty re material contractual exposure
- Internal procurement / contract management standards

HONEST DEFERRALS
- AI_DRAFT_ASSISTANCE DEFERRED — engine stores clauses; AI-powered
  drafting suggestions or contract markup integration with ENH-221
  contract review engine future work
- DOCUMENT_GENERATION META_ONLY — engine surfaces clause text; actual
  document assembly (Word merge, DocAssemble, etc.) operator-side
- CLAUSE_USAGE_TELEMETRY DEFERRED — engine ships clause library; usage
  tracking (which clauses are pulled into actual drafted contracts)
  is a future increment requiring contract_management integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


class ClauseStatus(str, Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class ClauseClassification(str, Enum):
    APPROVED = "APPROVED"            # preferred drafting position
    FALLBACK = "FALLBACK"            # acceptable alternative
    PROHIBITED = "PROHIBITED"        # never use


class PlaybookStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_NOT_FOUND = "REJECTED_NOT_FOUND"
    REJECTED_PROHIBITED_IN_PLAYBOOK = "REJECTED_PROHIBITED_IN_PLAYBOOK"


CLAUSE_TRANSITIONS: Mapping[ClauseStatus, Tuple[ClauseStatus, ...]] = {
    ClauseStatus.DRAFT: (ClauseStatus.UNDER_REVIEW,
                            ClauseStatus.RETIRED),
    ClauseStatus.UNDER_REVIEW: (ClauseStatus.APPROVED,
                                  ClauseStatus.DRAFT,
                                  ClauseStatus.RETIRED),
    ClauseStatus.APPROVED: (ClauseStatus.RETIRED,),
    ClauseStatus.RETIRED: (),
}


PLAYBOOK_TRANSITIONS: Mapping[PlaybookStatus,
                                Tuple[PlaybookStatus, ...]] = {
    PlaybookStatus.DRAFT: (PlaybookStatus.PUBLISHED,
                              PlaybookStatus.RETIRED),
    PlaybookStatus.PUBLISHED: (PlaybookStatus.RETIRED,
                                  PlaybookStatus.DRAFT),
    PlaybookStatus.RETIRED: (),
}


@dataclass(frozen=True)
class ClauseRevision:
    revision_id: str
    version_number: int
    clause_text: str
    drafting_notes: str
    classification: ClauseClassification
    status: ClauseStatus
    author: str
    created_at_utc: str
    approved_by: str = ""
    approved_at_utc: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"revision_id": self.revision_id,
                "version_number": self.version_number,
                "clause_text": self.clause_text,
                "drafting_notes": self.drafting_notes,
                "classification": self.classification.value,
                "status": self.status.value,
                "author": self.author,
                "created_at_utc": self.created_at_utc,
                "approved_by": self.approved_by,
                "approved_at_utc": self.approved_at_utc}


@dataclass(frozen=True)
class Clause:
    clause_id: str
    name: str
    category: str             # e.g. "indemnity", "limitation_of_liability"
    agreement_types: Tuple[str, ...]   # which agreements this fits
    current_revision_id: str
    classification: ClauseClassification
    status: ClauseStatus
    revisions: Tuple[ClauseRevision, ...]
    created_at_utc: str
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    retirement_reason: str = ""

    def current_revision(self) -> ClauseRevision:
        for r in self.revisions:
            if r.revision_id == self.current_revision_id:
                return r
        # safety fallback
        return self.revisions[-1]

    def to_dict(self) -> Dict[str, Any]:
        return {"clause_id": self.clause_id, "name": self.name,
                "category": self.category,
                "agreement_types": list(self.agreement_types),
                "current_revision_id": self.current_revision_id,
                "classification": self.classification.value,
                "status": self.status.value,
                "revisions": [r.to_dict() for r in self.revisions],
                "created_at_utc": self.created_at_utc,
                "transition_log": [dict(t)
                                     for t in self.transition_log],
                "retirement_reason": self.retirement_reason}


@dataclass(frozen=True)
class PlaybookEntry:
    """Reference to a clause within a playbook, with negotiation
    guidance (e.g., 'this is our preferred position; if push-back,
    fall back to clause X')."""
    sequence: int
    clause_id: str
    role_in_playbook: str       # PREFERRED / FALLBACK / RED_LINE
    negotiation_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {"sequence": self.sequence,
                "clause_id": self.clause_id,
                "role_in_playbook": self.role_in_playbook,
                "negotiation_notes": self.negotiation_notes}


@dataclass(frozen=True)
class Playbook:
    playbook_id: str
    name: str
    agreement_type: str          # e.g. "vendor_msa", "loan_agreement"
    description: str
    entries: Tuple[PlaybookEntry, ...]
    status: PlaybookStatus
    owner_role: str
    created_at_utc: str
    published_at_utc: str = ""
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    retirement_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"playbook_id": self.playbook_id,
                "name": self.name,
                "agreement_type": self.agreement_type,
                "description": self.description,
                "entries": [e.to_dict() for e in self.entries],
                "status": self.status.value,
                "owner_role": self.owner_role,
                "created_at_utc": self.created_at_utc,
                "published_at_utc": self.published_at_utc,
                "transition_log": [dict(t)
                                     for t in self.transition_log],
                "retirement_reason": self.retirement_reason}


class ClauseLibraryEngine:
    """ENH-226 Clause Library & Playbooks Engine."""

    AI_DRAFT_ASSISTANCE_STATUS = (
        "DEFERRED — engine stores approved clauses + playbooks; AI-"
        "powered drafting suggestions, ENH-221 contract review "
        "integration for clause-level markup, and rule-based "
        "negotiation advisors are future work.")

    DOCUMENT_GENERATION_STATUS = (
        "META_ONLY — engine surfaces clause text + playbook order; "
        "actual document assembly (Word merge, DocAssemble template "
        "engine, PDF generation) is operator-side.")

    CLAUSE_USAGE_TELEMETRY_STATUS = (
        "DEFERRED — engine ships clause library; usage telemetry "
        "(which clauses pulled into which actual contracts, with "
        "what frequency) requires contract_management integration "
        "and is a future increment.")

    def __init__(self) -> None:
        self._clauses: Dict[str, Clause] = {}
        self._playbooks: Dict[str, Playbook] = {}
        self._next_clause = 1
        self._next_playbook = 1
        self._next_revision = 1

    # ------------------------------------------------------------------
    # Clauses
    # ------------------------------------------------------------------

    def register_clause(
        self, name: str, category: str,
        agreement_types: Tuple[str, ...],
        clause_text: str, drafting_notes: str,
        classification: ClauseClassification, author: str,
    ) -> Clause:
        if not name.strip():
            raise ValueError("clause name required")
        if not clause_text.strip():
            raise ValueError("clause_text required")
        if not agreement_types:
            raise ValueError(
                "agreement_types required — clause must apply to "
                "at least one agreement type")
        cid = f"CLS-{self._next_clause:06d}"
        self._next_clause += 1
        rid = f"CLR-{self._next_revision:06d}"
        self._next_revision += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        rev = ClauseRevision(
            revision_id=rid, version_number=1,
            clause_text=clause_text.strip(),
            drafting_notes=drafting_notes.strip(),
            classification=classification,
            status=ClauseStatus.DRAFT,
            author=author.strip(),
            created_at_utc=now_utc)
        clause = Clause(
            clause_id=cid, name=name.strip(),
            category=category.strip(),
            agreement_types=tuple(agreement_types),
            current_revision_id=rid,
            classification=classification,
            status=ClauseStatus.DRAFT,
            revisions=(rev,),
            created_at_utc=now_utc,
            transition_log=(
                {"to_status": "DRAFT", "at_utc": now_utc,
                 "user": author,
                 "reason": "clause registered"},))
        self._clauses[cid] = clause
        return clause

    def transition_clause(
        self, clause_id: str, new_status: ClauseStatus,
        user: str, reason: str = "",
    ) -> Tuple[TransitionOutcome, Optional[Clause]]:
        if clause_id not in self._clauses:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._clauses[clause_id]
        if new_status not in CLAUSE_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        if new_status == ClauseStatus.RETIRED and not reason.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["status"] = new_status
        # Update current revision's status to match
        new_revisions = []
        for r in current.revisions:
            if r.revision_id == current.current_revision_id:
                r_kwargs = {f: getattr(r, f)
                              for f in r.__dataclass_fields__}
                r_kwargs["status"] = new_status
                if new_status == ClauseStatus.APPROVED:
                    r_kwargs["approved_by"] = user
                    r_kwargs["approved_at_utc"] = now_utc
                new_revisions.append(ClauseRevision(**r_kwargs))
            else:
                new_revisions.append(r)
        kwargs["revisions"] = tuple(new_revisions)
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": new_status.value, "at_utc": now_utc,
              "user": user, "reason": reason},))
        if new_status == ClauseStatus.RETIRED:
            kwargs["retirement_reason"] = reason.strip()
        updated = Clause(**kwargs)
        self._clauses[clause_id] = updated
        return (TransitionOutcome.OK, updated)

    def revise_clause(
        self, clause_id: str, new_text: str, new_drafting_notes: str,
        author: str,
    ) -> Clause:
        """Add a new revision (creating draft v2, v3, ...)."""
        if clause_id not in self._clauses:
            raise KeyError(f"not found: {clause_id}")
        if not new_text.strip():
            raise ValueError("new_text required")
        current = self._clauses[clause_id]
        new_version = max(r.version_number
                            for r in current.revisions) + 1
        rid = f"CLR-{self._next_revision:06d}"
        self._next_revision += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        rev = ClauseRevision(
            revision_id=rid, version_number=new_version,
            clause_text=new_text.strip(),
            drafting_notes=new_drafting_notes.strip(),
            classification=current.classification,
            status=ClauseStatus.DRAFT,
            author=author.strip(),
            created_at_utc=now_utc)
        kwargs = {f: getattr(current, f)
                    for f in current.__dataclass_fields__}
        kwargs["revisions"] = current.revisions + (rev,)
        kwargs["current_revision_id"] = rid
        kwargs["status"] = ClauseStatus.DRAFT  # new draft pending
        updated = Clause(**kwargs)
        self._clauses[clause_id] = updated
        return updated

    # ------------------------------------------------------------------
    # Playbooks
    # ------------------------------------------------------------------

    def create_playbook(
        self, name: str, agreement_type: str,
        description: str, owner_role: str,
        entries: List[PlaybookEntry],
    ) -> Tuple[TransitionOutcome, Optional[Playbook]]:
        if not name.strip():
            raise ValueError("name required")
        # All referenced clauses must exist + none can be PROHIBITED
        for e in entries:
            if e.clause_id not in self._clauses:
                return (TransitionOutcome.REJECTED_NOT_FOUND, None)
            c = self._clauses[e.clause_id]
            if c.classification == ClauseClassification.PROHIBITED:
                return (TransitionOutcome.REJECTED_PROHIBITED_IN_PLAYBOOK,
                        None)
        pid = f"PBK-{self._next_playbook:06d}"
        self._next_playbook += 1
        now_utc = datetime.now(timezone.utc).isoformat()
        pb = Playbook(
            playbook_id=pid, name=name.strip(),
            agreement_type=agreement_type.strip(),
            description=description.strip(),
            entries=tuple(entries),
            status=PlaybookStatus.DRAFT,
            owner_role=owner_role.strip(),
            created_at_utc=now_utc,
            transition_log=(
                {"to_status": "DRAFT", "at_utc": now_utc,
                 "user": "system",
                 "reason": "playbook created"},))
        self._playbooks[pid] = pb
        return (TransitionOutcome.OK, pb)

    def transition_playbook(
        self, playbook_id: str, new_status: PlaybookStatus,
        user: str, reason: str = "",
    ) -> Tuple[TransitionOutcome, Optional[Playbook]]:
        if playbook_id not in self._playbooks:
            return (TransitionOutcome.REJECTED_NOT_FOUND, None)
        current = self._playbooks[playbook_id]
        if new_status not in PLAYBOOK_TRANSITIONS.get(
                current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)
        if (new_status == PlaybookStatus.RETIRED and
                not reason.strip()):
            return (TransitionOutcome.REJECTED_REASON_REQUIRED,
                    current)
        # PUBLISHED requires all referenced clauses are APPROVED + non-prohibited
        if new_status == PlaybookStatus.PUBLISHED:
            for e in current.entries:
                c = self._clauses.get(e.clause_id)
                if c is None:
                    return (TransitionOutcome.REJECTED_NOT_FOUND,
                            current)
                if c.status != ClauseStatus.APPROVED:
                    return (
                        TransitionOutcome.REJECTED_INVALID_TRANSITION,
                        current)
        now_utc = datetime.now(timezone.utc).isoformat()
        kwargs = {f: getattr(current, f)
                    for f in current.__dataclass_fields__}
        kwargs["status"] = new_status
        kwargs["transition_log"] = (
            current.transition_log +
            ({"to_status": new_status.value, "at_utc": now_utc,
              "user": user, "reason": reason},))
        if new_status == PlaybookStatus.PUBLISHED:
            kwargs["published_at_utc"] = now_utc
        if new_status == PlaybookStatus.RETIRED:
            kwargs["retirement_reason"] = reason.strip()
        updated = Playbook(**kwargs)
        self._playbooks[playbook_id] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def clause_by_id(self, clause_id: str) -> Clause:
        if clause_id not in self._clauses:
            raise KeyError(f"not found: {clause_id}")
        return self._clauses[clause_id]

    def playbook_by_id(self, playbook_id: str) -> Playbook:
        if playbook_id not in self._playbooks:
            raise KeyError(f"not found: {playbook_id}")
        return self._playbooks[playbook_id]

    def clauses_for_agreement_type(
            self, agreement_type: str) -> Tuple[Clause, ...]:
        return tuple(c for c in self._clauses.values()
                       if agreement_type in c.agreement_types
                          and c.status == ClauseStatus.APPROVED)

    def prohibited_clauses(self) -> Tuple[Clause, ...]:
        return tuple(
            c for c in self._clauses.values()
            if c.classification == ClauseClassification.PROHIBITED)

    def published_playbooks(self) -> Tuple[Playbook, ...]:
        return tuple(p for p in self._playbooks.values()
                       if p.status == PlaybookStatus.PUBLISHED)

    def playbooks_for_agreement_type(
            self, agreement_type: str) -> Tuple[Playbook, ...]:
        return tuple(p for p in self._playbooks.values()
                       if p.agreement_type == agreement_type)

    def board_summary(self) -> Dict[str, Any]:
        n_clauses = len(self._clauses)
        clause_status_counts: Dict[str, int] = {}
        clause_class_counts: Dict[str, int] = {}
        for c in self._clauses.values():
            clause_status_counts[c.status.value] = (
                clause_status_counts.get(c.status.value, 0) + 1)
            clause_class_counts[c.classification.value] = (
                clause_class_counts.get(c.classification.value, 0)
                + 1)
        playbook_status_counts: Dict[str, int] = {}
        for p in self._playbooks.values():
            playbook_status_counts[p.status.value] = (
                playbook_status_counts.get(p.status.value, 0) + 1)
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-226 ClauseLibraryEngine",
            "n_clauses_total": n_clauses,
            "n_clauses_approved": clause_status_counts.get(
                "APPROVED", 0),
            "n_prohibited_clauses": len(self.prohibited_clauses()),
            "n_playbooks_total": len(self._playbooks),
            "n_playbooks_published": len(self.published_playbooks()),
            "clause_status_counts": clause_status_counts,
            "clause_classification_counts": clause_class_counts,
            "playbook_status_counts": playbook_status_counts,
            "ai_draft_assistance_status": (
                self.AI_DRAFT_ASSISTANCE_STATUS),
            "document_generation_status": (
                self.DOCUMENT_GENERATION_STATUS),
            "clause_usage_telemetry_status": (
                self.CLAUSE_USAGE_TELEMETRY_STATUS),
            "regulatory_basis": (
                "CBK Risk Management Guidelines (operational risk "
                "from inconsistent contract drafting), Companies "
                "Act §145 director duty re material contractual "
                "exposure, internal procurement standards"),
        }

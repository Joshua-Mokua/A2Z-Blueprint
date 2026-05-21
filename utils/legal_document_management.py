"""utils.legal_document_management — ENH-229 Legal Document Management
(v10.177).

Centralized repository for legal documents (agreements, court filings,
regulatory submissions, policies, legal opinions, corporate records).
Distinct from utils/document_management.py which handles loan/customer
KYC documents (IDs, payslips, bank statements). Different problem
domain, different lifecycle, different retention rules.

DESIGN CONTRACT
---------------
1. Two-entity engine:
   - LegalDocument with DRAFT→UNDER_REVIEW→APPROVED→ARCHIVED→PURGED
   - DiscoveryRequest with REQUESTED→IN_PROGRESS→FULFILLED→CLOSED
2. Cross-engine linkage via matter_id (legal_case_management) and
   hold_ids (legal_hold_management) — these are recorded but not
   verified against the source engines (composition layer responsible
   for resolution; this engine stores references only)
3. Retention class is selected at registration; the engine surfaces
   when the retention window has elapsed but does NOT auto-purge
   (operator-side policy decision)
4. Confidentiality classification (PUBLIC/INTERNAL/CONFIDENTIAL/
   PRIVILEGED) tags each doc; PRIVILEGED docs are flagged for special
   handling but the engine does NOT enforce access control —
   that's the cockpit's role via require_access()
5. E-discovery requests can be scoped by matter/hold/date-range; the
   engine answers "which docs match the scope" but does not produce
   the actual export bundle (deferred — operator-side packaging)

LIFECYCLE — LegalDocument (5 states)
------------------------------------
    DRAFT ─→ UNDER_REVIEW ─→ APPROVED ─→ ARCHIVED ─→ PURGED
              │
              └─→ DRAFT  (rejected back for revision)

PURGED is terminal and only valid after retention period elapsed.

LIFECYCLE — DiscoveryRequest (4 states)
---------------------------------------
    REQUESTED ─→ IN_PROGRESS ─→ FULFILLED ─→ CLOSED
                                  └─→ CLOSED  (closed without fulfillment)

RETENTION CLASSES (Kenya statutory defaults)
--------------------------------------------
    INDEFINITE     — corporate records (CR12, certificates)
    LITIGATION_HOLD— preserved while any active hold references the doc
    SEVEN_YEAR     — Companies Act §147 / Tax Procedures Act §59 default
    TEN_YEAR       — Banking Act §17 records
    TWENTY_YEAR    — Land/title documents (Limitations of Actions Act)

HONEST DEFERRALS
----------------
- ACTUAL_BLOB_STORAGE: DEFERRED — filesystem/S3 storage operator-side
- VERSION_CONTROL_BINARY_DIFF: DEFERRED — engine tracks version_no
  scalar; binary diff/merge is operator-side
- AUTOMATED_RETENTION_PURGE: DEFERRED — engine flags eligibility,
  operator decides
- FULL_TEXT_SEARCH_INDEX: DEFERRED — requires OCR + search infrastructure
- E_DISCOVERY_BUNDLE_EXPORT: DEFERRED — packaging/redaction operator-side
- ACCESS_CONTROL_ENFORCEMENT: META_ONLY — confidentiality tag set here,
  enforcement at cockpit via require_access()
- ENH-221 CONTRACT_REVIEW LINKAGE: META_ONLY — engine accepts
  contract_review_id reference but does not validate against ENH-221
  engine (which is currently META_ONLY itself)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------- enums

class LegalDocumentKind(str, Enum):
    """Categories of legal documents — distinct from KYC docs."""
    AGREEMENT             = "AGREEMENT"
    COURT_FILING          = "COURT_FILING"
    REGULATORY_SUBMISSION = "REGULATORY_SUBMISSION"
    POLICY                = "POLICY"
    LITIGATION_PLEADING   = "LITIGATION_PLEADING"
    LEGAL_OPINION         = "LEGAL_OPINION"
    CORRESPONDENCE        = "CORRESPONDENCE"
    CORPORATE_RECORD      = "CORPORATE_RECORD"
    IP_DOCUMENT           = "IP_DOCUMENT"
    OTHER                 = "OTHER"


class LegalDocumentState(str, Enum):
    """Lifecycle states for legal documents."""
    DRAFT        = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED     = "APPROVED"
    ARCHIVED     = "ARCHIVED"
    PURGED       = "PURGED"


class Confidentiality(str, Enum):
    """Confidentiality classification for handling discipline."""
    PUBLIC       = "PUBLIC"
    INTERNAL     = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PRIVILEGED   = "PRIVILEGED"   # attorney-client / work product


class RetentionClass(str, Enum):
    """Statutory retention windows aligned to Kenya law."""
    INDEFINITE      = "INDEFINITE"
    LITIGATION_HOLD = "LITIGATION_HOLD"
    SEVEN_YEAR      = "SEVEN_YEAR"
    TEN_YEAR        = "TEN_YEAR"
    TWENTY_YEAR     = "TWENTY_YEAR"


class DiscoveryStatus(str, Enum):
    """E-discovery request lifecycle."""
    REQUESTED   = "REQUESTED"
    IN_PROGRESS = "IN_PROGRESS"
    FULFILLED   = "FULFILLED"
    CLOSED      = "CLOSED"


class TransitionOutcome(str, Enum):
    OK                          = "OK"
    REJECTED_BAD_TRANSITION     = "REJECTED_BAD_TRANSITION"
    REJECTED_RETENTION_NOT_DUE  = "REJECTED_RETENTION_NOT_DUE"
    REJECTED_REASON_REQUIRED    = "REJECTED_REASON_REQUIRED"
    REJECTED_DOC_NOT_FOUND      = "REJECTED_DOC_NOT_FOUND"


# ---------------------------------------------------------------- helpers

# Retention windows in days (approximate calendar days)
_RETENTION_DAYS: Dict[RetentionClass, Optional[int]] = {
    RetentionClass.INDEFINITE:      None,         # never purgeable
    RetentionClass.LITIGATION_HOLD: None,         # gated by hold release
    RetentionClass.SEVEN_YEAR:      365 * 7,
    RetentionClass.TEN_YEAR:        365 * 10,
    RetentionClass.TWENTY_YEAR:     365 * 20,
}

_LEGAL_DOC_TRANSITIONS: Dict[
    LegalDocumentState, Tuple[LegalDocumentState, ...]
] = {
    LegalDocumentState.DRAFT:        (LegalDocumentState.UNDER_REVIEW,),
    LegalDocumentState.UNDER_REVIEW: (
        LegalDocumentState.APPROVED, LegalDocumentState.DRAFT,
    ),
    LegalDocumentState.APPROVED:     (LegalDocumentState.ARCHIVED,),
    LegalDocumentState.ARCHIVED:     (LegalDocumentState.PURGED,),
    LegalDocumentState.PURGED:       (),
}

_DISCOVERY_TRANSITIONS: Dict[
    DiscoveryStatus, Tuple[DiscoveryStatus, ...]
] = {
    DiscoveryStatus.REQUESTED:   (DiscoveryStatus.IN_PROGRESS,
                                    DiscoveryStatus.CLOSED),
    DiscoveryStatus.IN_PROGRESS: (DiscoveryStatus.FULFILLED,
                                    DiscoveryStatus.CLOSED),
    DiscoveryStatus.FULFILLED:   (DiscoveryStatus.CLOSED,),
    DiscoveryStatus.CLOSED:      (),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return datetime.now(timezone.utc).date()


# ------------------------------------------------------------- dataclasses

@dataclass(frozen=True)
class LegalDocument:
    """A single legal document record."""
    doc_id:               str
    doc_kind:             LegalDocumentKind
    title:                str
    description:          str
    version_no:           int
    state:                LegalDocumentState
    confidentiality:      Confidentiality
    retention_class:      RetentionClass
    registered_at_utc:    str
    matter_id:            Optional[str] = None       # → legal_case_management
    hold_ids:             tuple = ()                 # → legal_hold_management
    contract_review_id:   Optional[str] = None       # → ENH-221 (META_ONLY)
    state_history:        tuple = field(default_factory=tuple)
    purgeable_after:      Optional[str] = None       # ISO date or None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id":             self.doc_id,
            "doc_kind":           self.doc_kind.value,
            "title":              self.title,
            "description":        self.description,
            "version_no":         self.version_no,
            "state":              self.state.value,
            "confidentiality":    self.confidentiality.value,
            "retention_class":    self.retention_class.value,
            "registered_at_utc":  self.registered_at_utc,
            "matter_id":          self.matter_id,
            "hold_ids":           list(self.hold_ids),
            "contract_review_id": self.contract_review_id,
            "state_history":      list(self.state_history),
            "purgeable_after":    self.purgeable_after,
        }


@dataclass(frozen=True)
class DiscoveryRequest:
    """An e-discovery request scoped by matter/hold/date-range."""
    request_id:        str
    requested_by:      str
    requested_at_utc:  str
    matter_id:         Optional[str] = None
    hold_id:           Optional[str] = None
    date_from:         Optional[str] = None    # ISO date
    date_to:           Optional[str] = None    # ISO date
    status:            DiscoveryStatus = DiscoveryStatus.REQUESTED
    matched_doc_ids:   tuple = ()
    fulfilled_at_utc:  Optional[str] = None
    closure_reason:    Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id":        self.request_id,
            "requested_by":      self.requested_by,
            "requested_at_utc":  self.requested_at_utc,
            "matter_id":         self.matter_id,
            "hold_id":           self.hold_id,
            "date_from":         self.date_from,
            "date_to":           self.date_to,
            "status":            self.status.value,
            "matched_doc_ids":   list(self.matched_doc_ids),
            "fulfilled_at_utc":  self.fulfilled_at_utc,
            "closure_reason":    self.closure_reason,
        }


# ------------------------------------------------------------- engine

class LegalDocumentManagementEngine:
    """ENH-229 Legal Document Management engine (v10.177)."""

    ENGINE_NAME      = "ENH-229 LegalDocumentManagementEngine"
    REGULATORY_BASIS = (
        "Kenya Companies Act §147 (corporate records); Tax Procedures "
        "Act §59 (7-year retention default); Banking Act §17 "
        "(10-year banking records); Limitations of Actions Act "
        "(20-year land/title docs); Civil Procedure Rules (e-discovery "
        "duty during litigation hold). Distinct from utils/document_"
        "management.py which handles KYC/loan documents.")

    def __init__(self) -> None:
        self._docs: Dict[str, LegalDocument] = {}
        self._discovery: Dict[str, DiscoveryRequest] = {}

    # ------------------- LegalDocument operations

    def register_document(
        self,
        doc_id: str,
        doc_kind: LegalDocumentKind,
        title: str,
        description: str,
        confidentiality: Confidentiality,
        retention_class: RetentionClass,
        matter_id: Optional[str] = None,
        hold_ids: Optional[List[str]] = None,
        contract_review_id: Optional[str] = None,
    ) -> LegalDocument:
        if doc_id in self._docs:
            raise ValueError(f"document {doc_id} already registered")
        if not title or not title.strip():
            raise ValueError("title required")

        purgeable = self._compute_purgeable(retention_class)

        doc = LegalDocument(
            doc_id=doc_id,
            doc_kind=doc_kind,
            title=title.strip(),
            description=description,
            version_no=1,
            state=LegalDocumentState.DRAFT,
            confidentiality=confidentiality,
            retention_class=retention_class,
            registered_at_utc=_now_iso(),
            matter_id=matter_id,
            hold_ids=tuple(hold_ids or ()),
            contract_review_id=contract_review_id,
            state_history=(("DRAFT", _now_iso(), "registered"),),
            purgeable_after=purgeable,
        )
        self._docs[doc_id] = doc
        return doc

    def transition_document(
        self,
        doc_id: str,
        target_state: LegalDocumentState,
        reason: str = "",
    ) -> Tuple[LegalDocument, TransitionOutcome]:
        doc = self._docs.get(doc_id)
        if doc is None:
            raise ValueError(f"document {doc_id} not found")

        allowed = _LEGAL_DOC_TRANSITIONS.get(doc.state, ())
        if target_state not in allowed:
            return (doc, TransitionOutcome.REJECTED_BAD_TRANSITION)

        # PURGED requires retention window elapsed for time-bound classes
        if target_state == LegalDocumentState.PURGED:
            if not self._is_purgeable(doc):
                return (doc, TransitionOutcome.REJECTED_RETENTION_NOT_DUE)

        # Transitions back to DRAFT or to PURGED require reason
        if target_state in (LegalDocumentState.DRAFT,
                              LegalDocumentState.PURGED):
            if not reason or not reason.strip():
                return (doc, TransitionOutcome.REJECTED_REASON_REQUIRED)

        new_history = doc.state_history + (
            (target_state.value, _now_iso(), reason or "ok"),)
        new_doc = LegalDocument(
            doc_id=doc.doc_id,
            doc_kind=doc.doc_kind,
            title=doc.title,
            description=doc.description,
            version_no=doc.version_no,
            state=target_state,
            confidentiality=doc.confidentiality,
            retention_class=doc.retention_class,
            registered_at_utc=doc.registered_at_utc,
            matter_id=doc.matter_id,
            hold_ids=doc.hold_ids,
            contract_review_id=doc.contract_review_id,
            state_history=new_history,
            purgeable_after=doc.purgeable_after,
        )
        self._docs[doc_id] = new_doc
        return (new_doc, TransitionOutcome.OK)

    def bump_version(self, doc_id: str) -> LegalDocument:
        doc = self._docs.get(doc_id)
        if doc is None:
            raise ValueError(f"document {doc_id} not found")
        if doc.state != LegalDocumentState.DRAFT:
            raise ValueError(
                "version bump only valid in DRAFT state")
        new_doc = LegalDocument(
            doc_id=doc.doc_id,
            doc_kind=doc.doc_kind,
            title=doc.title,
            description=doc.description,
            version_no=doc.version_no + 1,
            state=doc.state,
            confidentiality=doc.confidentiality,
            retention_class=doc.retention_class,
            registered_at_utc=doc.registered_at_utc,
            matter_id=doc.matter_id,
            hold_ids=doc.hold_ids,
            contract_review_id=doc.contract_review_id,
            state_history=doc.state_history + (
                (f"version_bumped_to_{doc.version_no + 1}",
                 _now_iso(), "version bump"),),
            purgeable_after=doc.purgeable_after,
        )
        self._docs[doc_id] = new_doc
        return new_doc

    def link_to_hold(self, doc_id: str, hold_id: str) -> LegalDocument:
        doc = self._docs.get(doc_id)
        if doc is None:
            raise ValueError(f"document {doc_id} not found")
        if hold_id in doc.hold_ids:
            return doc  # idempotent
        new_doc = LegalDocument(
            doc_id=doc.doc_id,
            doc_kind=doc.doc_kind,
            title=doc.title,
            description=doc.description,
            version_no=doc.version_no,
            state=doc.state,
            confidentiality=doc.confidentiality,
            retention_class=doc.retention_class,
            registered_at_utc=doc.registered_at_utc,
            matter_id=doc.matter_id,
            hold_ids=doc.hold_ids + (hold_id,),
            contract_review_id=doc.contract_review_id,
            state_history=doc.state_history,
            purgeable_after=doc.purgeable_after,
        )
        self._docs[doc_id] = new_doc
        return new_doc

    # ------------------- queries

    def document_by_id(self, doc_id: str) -> Optional[LegalDocument]:
        return self._docs.get(doc_id)

    def all_documents(self) -> Tuple[LegalDocument, ...]:
        return tuple(self._docs.values())

    def documents_for_matter(
        self, matter_id: str
    ) -> Tuple[LegalDocument, ...]:
        return tuple(d for d in self._docs.values()
                      if d.matter_id == matter_id)

    def documents_for_hold(
        self, hold_id: str
    ) -> Tuple[LegalDocument, ...]:
        return tuple(d for d in self._docs.values()
                      if hold_id in d.hold_ids)

    def documents_by_kind(
        self, kind: LegalDocumentKind
    ) -> Tuple[LegalDocument, ...]:
        return tuple(d for d in self._docs.values()
                      if d.doc_kind == kind)

    def privileged_documents(self) -> Tuple[LegalDocument, ...]:
        return tuple(d for d in self._docs.values()
                      if d.confidentiality == Confidentiality.PRIVILEGED)

    def purgeable_now(self) -> Tuple[LegalDocument, ...]:
        return tuple(d for d in self._docs.values()
                      if self._is_purgeable(d))

    # ------------------- retention helpers

    def _compute_purgeable(
        self, rc: RetentionClass
    ) -> Optional[str]:
        days = _RETENTION_DAYS.get(rc)
        if days is None:
            return None
        from datetime import timedelta
        return (_today() + timedelta(days=days)).isoformat()

    def _is_purgeable(self, doc: LegalDocument) -> bool:
        if doc.state != LegalDocumentState.ARCHIVED:
            return False
        if doc.purgeable_after is None:
            # INDEFINITE or LITIGATION_HOLD — never auto-eligible
            return False
        try:
            return date.fromisoformat(
                doc.purgeable_after) <= _today()
        except (ValueError, TypeError):
            return False

    # ------------------- DiscoveryRequest operations

    def create_discovery_request(
        self,
        request_id: str,
        requested_by: str,
        matter_id: Optional[str] = None,
        hold_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> DiscoveryRequest:
        if request_id in self._discovery:
            raise ValueError(
                f"discovery request {request_id} already exists")
        if not (matter_id or hold_id or date_from or date_to):
            raise ValueError(
                "discovery request needs at least one scope filter "
                "(matter_id, hold_id, or date range)")

        # Compute matched docs at request time (snapshot)
        matched = self._match_docs_for_scope(
            matter_id=matter_id, hold_id=hold_id,
            date_from=date_from, date_to=date_to)

        req = DiscoveryRequest(
            request_id=request_id,
            requested_by=requested_by,
            requested_at_utc=_now_iso(),
            matter_id=matter_id,
            hold_id=hold_id,
            date_from=date_from,
            date_to=date_to,
            matched_doc_ids=matched,
            status=DiscoveryStatus.REQUESTED,
        )
        self._discovery[request_id] = req
        return req

    def _match_docs_for_scope(
        self,
        matter_id: Optional[str] = None,
        hold_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Tuple[str, ...]:
        out = []
        for d in self._docs.values():
            if matter_id is not None and d.matter_id != matter_id:
                continue
            if hold_id is not None and hold_id not in d.hold_ids:
                continue
            if date_from is not None:
                if d.registered_at_utc[:10] < date_from:
                    continue
            if date_to is not None:
                if d.registered_at_utc[:10] > date_to:
                    continue
            out.append(d.doc_id)
        return tuple(out)

    def transition_discovery(
        self,
        request_id: str,
        target_status: DiscoveryStatus,
        reason: str = "",
    ) -> Tuple[DiscoveryRequest, TransitionOutcome]:
        req = self._discovery.get(request_id)
        if req is None:
            raise ValueError(
                f"discovery request {request_id} not found")
        allowed = _DISCOVERY_TRANSITIONS.get(req.status, ())
        if target_status not in allowed:
            return (req, TransitionOutcome.REJECTED_BAD_TRANSITION)

        # CLOSED requires reason if not coming from FULFILLED
        if (target_status == DiscoveryStatus.CLOSED and
                req.status != DiscoveryStatus.FULFILLED):
            if not reason or not reason.strip():
                return (req, TransitionOutcome.REJECTED_REASON_REQUIRED)

        fulfilled_at = (_now_iso()
                        if target_status == DiscoveryStatus.FULFILLED
                        else req.fulfilled_at_utc)
        closure = (reason if target_status == DiscoveryStatus.CLOSED
                    else req.closure_reason)

        new_req = DiscoveryRequest(
            request_id=req.request_id,
            requested_by=req.requested_by,
            requested_at_utc=req.requested_at_utc,
            matter_id=req.matter_id,
            hold_id=req.hold_id,
            date_from=req.date_from,
            date_to=req.date_to,
            status=target_status,
            matched_doc_ids=req.matched_doc_ids,
            fulfilled_at_utc=fulfilled_at,
            closure_reason=closure,
        )
        self._discovery[request_id] = new_req
        return (new_req, TransitionOutcome.OK)

    def discovery_by_id(
        self, request_id: str
    ) -> Optional[DiscoveryRequest]:
        return self._discovery.get(request_id)

    def all_discovery_requests(
        self
    ) -> Tuple[DiscoveryRequest, ...]:
        return tuple(self._discovery.values())

    def open_discovery_requests(
        self
    ) -> Tuple[DiscoveryRequest, ...]:
        return tuple(r for r in self._discovery.values()
                      if r.status not in (DiscoveryStatus.CLOSED,
                                          DiscoveryStatus.FULFILLED))

    # ------------------- board summary

    def board_summary(self) -> Dict[str, Any]:
        docs = list(self._docs.values())
        n_total = len(docs)
        by_state: Dict[str, int] = {}
        by_kind:  Dict[str, int] = {}
        by_conf:  Dict[str, int] = {}
        by_retention: Dict[str, int] = {}
        for d in docs:
            by_state[d.state.value] = by_state.get(d.state.value, 0) + 1
            by_kind[d.doc_kind.value] = by_kind.get(
                d.doc_kind.value, 0) + 1
            by_conf[d.confidentiality.value] = by_conf.get(
                d.confidentiality.value, 0) + 1
            by_retention[d.retention_class.value] = by_retention.get(
                d.retention_class.value, 0) + 1

        n_purgeable = len(self.purgeable_now())
        n_privileged = len(self.privileged_documents())

        discoveries = list(self._discovery.values())
        n_discoveries = len(discoveries)
        n_disc_open = len(self.open_discovery_requests())

        return {
            "entity":              "Ecobank Kenya",
            "engine":              self.ENGINE_NAME,
            "regulatory_basis":    self.REGULATORY_BASIS,
            "n_documents_total":   n_total,
            "n_documents_purgeable_now": n_purgeable,
            "n_privileged_documents":    n_privileged,
            "by_state":            by_state,
            "by_kind":             by_kind,
            "by_confidentiality":  by_conf,
            "by_retention_class":  by_retention,
            "n_discovery_requests_total":  n_discoveries,
            "n_discovery_requests_open":   n_disc_open,
            # Honest deferral surface
            "blob_storage_status":
                ("DEFERRED — engine tracks metadata + version_no; "
                 "actual filesystem/S3 blob storage is operator-side"),
            "version_control_diff_status":
                ("DEFERRED — engine tracks scalar version_no; "
                 "binary diff/merge is operator-side"),
            "automated_retention_purge_status":
                ("DEFERRED — engine surfaces purgeable_now() list; "
                 "operator decides whether to PURGE"),
            "full_text_search_status":
                ("DEFERRED — requires OCR + search infrastructure"),
            "ediscovery_bundle_export_status":
                ("DEFERRED — engine answers scope queries; actual "
                 "export packaging + redaction is operator-side"),
            "access_control_enforcement_status":
                ("META_ONLY — confidentiality tag set here, "
                 "enforcement at cockpit via require_access()"),
            "contract_review_linkage_status":
                ("META_ONLY — contract_review_id stored as scalar; "
                 "ENH-221 contract review engine is itself META_ONLY"),
        }


__all__ = [
    "LegalDocumentKind",
    "LegalDocumentState",
    "Confidentiality",
    "RetentionClass",
    "DiscoveryStatus",
    "TransitionOutcome",
    "LegalDocument",
    "DiscoveryRequest",
    "LegalDocumentManagementEngine",
]

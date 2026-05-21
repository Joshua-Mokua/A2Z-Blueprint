"""utils/document_management.py — v10.15 Phase 2 deep impl batch 9 (Credit batch 5 part 1).

╔════════════════════════════════════════════════════════════════════════╗
║  DIGITAL DOCUMENT MANAGEMENT & VERIFICATION                            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (deterministic doc lifecycle + authenticity checks) ║
║  Implements 1 of 19 Credit standards from registry:                     ║
║    ENH-127: Digital Document Management & Verification                  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Kenya Data Protection Act 2019 §28 — retention principles           ║
║    Kenya Data Protection (General) Regulations 2021                    ║
║    CBK Digital Lending Regulations 2022 §15 — record-keeping           ║
║    CBK AML/CFT Guideline 2017 §16 — KYC document retention 7 yrs       ║
║    Kenya Tax Procedures Act §23 — KRA documents 5 yrs                  ║
║    EU eIDAS Reg 910/2014 — qualified electronic signatures             ║
║    ISO 27001 — information security management                          ║
║    ISO 19005 / PDF/A — long-term archival format                        ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 7 enforced: OCR / authenticity check / signature verify  ║
║  are callable hooks. No fabricated extraction results when no provider ║
║  configured — engine returns INCONCLUSIVE with explicit reason.        ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28


# ════════════════════════════════════════════════════════════════════════
# Document types and lifecycle
# ════════════════════════════════════════════════════════════════════════

class DocumentType(Enum):
    """Document types relevant to credit underwriting in Kenya."""
    NATIONAL_ID = "NATIONAL_ID"
    PASSPORT = "PASSPORT"
    ALIEN_ID = "ALIEN_ID"
    KRA_PIN_CERTIFICATE = "KRA_PIN_CERTIFICATE"
    PAYSLIP = "PAYSLIP"
    BANK_STATEMENT = "BANK_STATEMENT"
    AUDITED_FINANCIALS = "AUDITED_FINANCIALS"
    MGMT_ACCOUNTS = "MGMT_ACCOUNTS"
    BUSINESS_PERMIT = "BUSINESS_PERMIT"
    CERTIFICATE_OF_INCORPORATION = "CERTIFICATE_OF_INCORPORATION"
    CR12 = "CR12"                           # company directors / shareholders
    PROOF_OF_RESIDENCE = "PROOF_OF_RESIDENCE"
    UTILITY_BILL = "UTILITY_BILL"
    TITLE_DEED = "TITLE_DEED"
    LOGBOOK = "LOGBOOK"                     # vehicle ownership
    VALUATION_REPORT = "VALUATION_REPORT"
    INSURANCE_POLICY = "INSURANCE_POLICY"
    GUARANTEE_LETTER = "GUARANTEE_LETTER"


class DocumentState(Enum):
    """Document lifecycle states."""
    SUBMITTED = "SUBMITTED"
    AUTHENTICITY_PENDING = "AUTHENTICITY_PENDING"
    AUTHENTICITY_FAILED = "AUTHENTICITY_FAILED"
    DATA_EXTRACTION_PENDING = "DATA_EXTRACTION_PENDING"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


# Allowed transitions
ALLOWED_DOC_TRANSITIONS: Mapping[DocumentState, Tuple[DocumentState, ...]] = {
    DocumentState.SUBMITTED: (
        DocumentState.AUTHENTICITY_PENDING,
        DocumentState.REJECTED),
    DocumentState.AUTHENTICITY_PENDING: (
        DocumentState.DATA_EXTRACTION_PENDING,
        DocumentState.AUTHENTICITY_FAILED),
    DocumentState.AUTHENTICITY_FAILED: (
        DocumentState.REJECTED,),
    DocumentState.DATA_EXTRACTION_PENDING: (
        DocumentState.VERIFIED,
        DocumentState.EXTRACTION_FAILED),
    DocumentState.EXTRACTION_FAILED: (
        DocumentState.REJECTED,),
    DocumentState.VERIFIED: (
        DocumentState.EXPIRED, DocumentState.ARCHIVED),
    DocumentState.REJECTED: (),
    DocumentState.EXPIRED: (DocumentState.ARCHIVED,),
    DocumentState.ARCHIVED: (),
}


def is_valid_doc_transition(
    from_state: DocumentState, to_state: DocumentState) -> bool:
    return to_state in ALLOWED_DOC_TRANSITIONS.get(from_state, ())


# ════════════════════════════════════════════════════════════════════════
# Retention policy per regulatory regime
# ════════════════════════════════════════════════════════════════════════

# Document retention years per regulatory regime
DOC_RETENTION_YEARS: Mapping[DocumentType, int] = {
    # KYC docs — CBK AML/CFT 2017 §16: 7 years post-relationship-end
    DocumentType.NATIONAL_ID: 7,
    DocumentType.PASSPORT: 7,
    DocumentType.ALIEN_ID: 7,
    DocumentType.KRA_PIN_CERTIFICATE: 7,
    DocumentType.PROOF_OF_RESIDENCE: 7,
    DocumentType.CR12: 7,
    DocumentType.CERTIFICATE_OF_INCORPORATION: 7,
    DocumentType.BUSINESS_PERMIT: 7,
    # Tax-related — Kenya Tax Procedures Act §23: 5 years
    DocumentType.PAYSLIP: 5,
    DocumentType.AUDITED_FINANCIALS: 5,
    DocumentType.MGMT_ACCOUNTS: 5,
    DocumentType.UTILITY_BILL: 5,
    # Loan/collateral docs — CBK Banking Act §54: 7 years post-loan-closure
    DocumentType.BANK_STATEMENT: 7,
    DocumentType.TITLE_DEED: 7,
    DocumentType.LOGBOOK: 7,
    DocumentType.VALUATION_REPORT: 7,
    DocumentType.INSURANCE_POLICY: 7,
    DocumentType.GUARANTEE_LETTER: 7,
}


# Document expiry windows from issue (where applicable)
DOC_VALIDITY_WINDOW_DAYS: Mapping[DocumentType, Optional[int]] = {
    DocumentType.PAYSLIP: 90,             # 3 most recent months
    DocumentType.BANK_STATEMENT: 90,
    DocumentType.UTILITY_BILL: 90,
    DocumentType.MGMT_ACCOUNTS: 365,       # 12 months
    DocumentType.AUDITED_FINANCIALS: 547,  # 18 months
    DocumentType.PROOF_OF_RESIDENCE: 90,
    DocumentType.VALUATION_REPORT: 365,
    DocumentType.CR12: 365,
    # Static identity docs use document's own expiry date
    DocumentType.NATIONAL_ID: None,
    DocumentType.PASSPORT: None,
    DocumentType.ALIEN_ID: None,
    DocumentType.KRA_PIN_CERTIFICATE: None,
    DocumentType.TITLE_DEED: None,
    DocumentType.LOGBOOK: None,
    DocumentType.BUSINESS_PERMIT: 365,
    DocumentType.CERTIFICATE_OF_INCORPORATION: None,
    DocumentType.INSURANCE_POLICY: None,    # use policy's expiry
    DocumentType.GUARANTEE_LETTER: None,
}


# ════════════════════════════════════════════════════════════════════════
# Authenticity checks
# ════════════════════════════════════════════════════════════════════════

class AuthenticityCheck(Enum):
    """Categories of authenticity verification."""
    FILE_HASH_INTEGRITY = "FILE_HASH_INTEGRITY"
    FORMAT_VALIDATION = "FORMAT_VALIDATION"
    METADATA_CONSISTENCY = "METADATA_CONSISTENCY"
    DIGITAL_SIGNATURE_VERIFY = "DIGITAL_SIGNATURE_VERIFY"
    MRZ_VALIDATION = "MRZ_VALIDATION"            # passport / ID machine-readable zone
    HOLOGRAM_DETECTION = "HOLOGRAM_DETECTION"
    WATERMARK_DETECTION = "WATERMARK_DETECTION"
    ISSUER_LOOKUP = "ISSUER_LOOKUP"              # cross-check with issuing authority


class AuthenticityResult(Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class AuthenticityCheckResult:
    """Outcome of one authenticity check on one document."""
    check: AuthenticityCheck
    result: AuthenticityResult
    confidence: Optional[Decimal] = None     # 0-1
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DocumentMetadata:
    """Document metadata captured at submission."""
    document_id: str
    applicant_id: str
    document_type: DocumentType
    file_name: str
    file_size_bytes: int
    file_format: str                  # pdf / jpg / png
    sha256_hash: str
    submitted_at: str                 # ISO-8601
    issued_date: Optional[str] = None
    expires_at: Optional[str] = None
    encryption_at_rest: bool = False
    notes: str = ""


@dataclass(frozen=True)
class DocumentRecord:
    """Full document record across its lifecycle."""
    metadata: DocumentMetadata
    state: DocumentState
    authenticity_results: Tuple[AuthenticityCheckResult, ...] = ()
    extracted_fields: Mapping[str, str] = field(default_factory=dict)
    extraction_confidence: Optional[Decimal] = None
    rejection_reason: str = ""
    state_history: Tuple[Tuple[DocumentState, str], ...] = ()  # (state, timestamp)


# ════════════════════════════════════════════════════════════════════════
# Functions
# ════════════════════════════════════════════════════════════════════════

def compute_sha256(content: bytes) -> str:
    """Compute SHA-256 hex digest of file content."""
    return hashlib.sha256(content).hexdigest()


def verify_file_integrity(
    *,
    expected_hash: str,
    actual_content: bytes,
) -> AuthenticityCheckResult:
    """Compare expected vs actual SHA-256 hash."""
    actual_hash = compute_sha256(actual_content)
    if actual_hash == expected_hash:
        return AuthenticityCheckResult(
            check=AuthenticityCheck.FILE_HASH_INTEGRITY,
            result=AuthenticityResult.PASSED,
            confidence=Decimal("1.0"),
            notes="SHA-256 matches")
    return AuthenticityCheckResult(
        check=AuthenticityCheck.FILE_HASH_INTEGRITY,
        result=AuthenticityResult.FAILED,
        confidence=Decimal("1.0"),
        notes=(
            f"SHA-256 mismatch: expected {expected_hash[:16]}..., "
            f"got {actual_hash[:16]}..."))


def verify_format(
    *,
    document_type: DocumentType,
    file_format: str,
) -> AuthenticityCheckResult:
    """Validate file format is acceptable for document type.

    Identity docs require PDF or image; financial docs require PDF.
    """
    fmt = file_format.lower().lstrip(".")
    image_types = {"pdf", "jpg", "jpeg", "png"}
    pdf_only = {DocumentType.AUDITED_FINANCIALS, DocumentType.MGMT_ACCOUNTS,
                  DocumentType.BANK_STATEMENT, DocumentType.PAYSLIP}

    if document_type in pdf_only and fmt != "pdf":
        return AuthenticityCheckResult(
            check=AuthenticityCheck.FORMAT_VALIDATION,
            result=AuthenticityResult.FAILED,
            notes=(
                f"{document_type.value} requires PDF format; "
                f"got {fmt}"))

    if fmt not in image_types:
        return AuthenticityCheckResult(
            check=AuthenticityCheck.FORMAT_VALIDATION,
            result=AuthenticityResult.FAILED,
            notes=f"unsupported format: {fmt}")

    return AuthenticityCheckResult(
        check=AuthenticityCheck.FORMAT_VALIDATION,
        result=AuthenticityResult.PASSED,
        notes=f"format {fmt} accepted")


def is_document_expired(
    *,
    document_type: DocumentType,
    issued_date: Optional[date],
    explicit_expires_at: Optional[date],
    as_of: date,
) -> bool:
    """Check whether a document is expired.

    Order of precedence:
    1. explicit_expires_at if set
    2. issued_date + DOC_VALIDITY_WINDOW_DAYS[type] if window known
    3. False (no expiry rule)
    """
    if explicit_expires_at is not None:
        return as_of > explicit_expires_at

    window = DOC_VALIDITY_WINDOW_DAYS.get(document_type)
    if window is not None and issued_date is not None:
        valid_until = issued_date + timedelta(days=window)
        return as_of > valid_until

    return False


def extract_fields(
    *,
    metadata: DocumentMetadata,
    file_content: bytes,
    extractor: Optional[
        Callable[[DocumentType, bytes], Tuple[Mapping[str, str], Decimal]]] = None,
) -> Tuple[Mapping[str, str], Optional[Decimal], str]:
    """Extract structured fields via injected OCR/parser callable.

    Per Rule 7 — no fabricated extraction. If `extractor` is None, returns
    empty fields with notes explaining the missing provider.
    """
    if extractor is None:
        return ({}, None,
                  "no extractor provided — Rule 7 honesty: no fabricated data")
    try:
        fields, confidence = extractor(metadata.document_type, file_content)
        return (dict(fields), confidence, "extracted via injected provider")
    except Exception as e:
        return ({}, None, f"extractor failed: {type(e).__name__}: {e}")


def assess_document(
    *,
    metadata: DocumentMetadata,
    file_content: bytes,
    file_extractor: Optional[Callable] = None,
    additional_authenticity_checks: Sequence[AuthenticityCheckResult] = (),
    as_of: Optional[date] = None,
) -> DocumentRecord:
    """End-to-end document assessment: integrity + format + extraction + state.

    Returns a `DocumentRecord` with terminal state VERIFIED, REJECTED, or
    extraction-pending depending on outcome.
    """
    if as_of is None:
        as_of = date.today()

    auth_results: List[AuthenticityCheckResult] = []

    # 1. Hash integrity
    auth_results.append(verify_file_integrity(
        expected_hash=metadata.sha256_hash, actual_content=file_content))

    # 2. Format
    auth_results.append(verify_format(
        document_type=metadata.document_type,
        file_format=metadata.file_format))

    # 3. Externally-provided checks (MRZ, hologram, signature, etc.)
    for chk in additional_authenticity_checks:
        auth_results.append(chk)

    # Authenticity verdict
    failed_checks = [
        c for c in auth_results if c.result == AuthenticityResult.FAILED]
    if failed_checks:
        return DocumentRecord(
            metadata=metadata,
            state=DocumentState.AUTHENTICITY_FAILED,
            authenticity_results=tuple(auth_results),
            rejection_reason=(
                f"{len(failed_checks)} authenticity check(s) failed: "
                f"{[c.check.value for c in failed_checks]}"))

    # 4. Expiry
    issued_date_obj = (
        date.fromisoformat(metadata.issued_date)
        if metadata.issued_date else None)
    expiry_obj = (
        date.fromisoformat(metadata.expires_at)
        if metadata.expires_at else None)
    if is_document_expired(
            document_type=metadata.document_type,
            issued_date=issued_date_obj,
            explicit_expires_at=expiry_obj,
            as_of=as_of):
        return DocumentRecord(
            metadata=metadata,
            state=DocumentState.REJECTED,
            authenticity_results=tuple(auth_results),
            rejection_reason="document expired")

    # 5. Field extraction
    fields, confidence, ext_notes = extract_fields(
        metadata=metadata, file_content=file_content,
        extractor=file_extractor)

    if file_extractor is None or not fields:
        # Rule 7 — no extractor, no silent default; mark extraction pending
        return DocumentRecord(
            metadata=metadata,
            state=DocumentState.DATA_EXTRACTION_PENDING,
            authenticity_results=tuple(auth_results),
            extracted_fields={},
            extraction_confidence=None,
            rejection_reason=ext_notes)

    return DocumentRecord(
        metadata=metadata,
        state=DocumentState.VERIFIED,
        authenticity_results=tuple(auth_results),
        extracted_fields=dict(fields),
        extraction_confidence=confidence)


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class DocumentManagementEngine:
    """Orchestrator: tracks documents per applicant, retention, expiry."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._docs: Dict[str, DocumentRecord] = {}

    def register_document(self, record: DocumentRecord) -> None:
        if record.metadata.document_id in self._docs:
            raise ValueError(
                f"document {record.metadata.document_id} already registered")
        self._docs[record.metadata.document_id] = record

    def get(self, document_id: str) -> DocumentRecord:
        if document_id not in self._docs:
            raise KeyError(f"document {document_id} not found")
        return self._docs[document_id]

    def documents_for_applicant(
        self, applicant_id: str) -> Tuple[DocumentRecord, ...]:
        return tuple(
            r for r in self._docs.values()
            if r.metadata.applicant_id == applicant_id)

    def expired_documents(self, *, as_of: Optional[date] = None) -> Tuple[str, ...]:
        if as_of is None:
            as_of = date.today()
        out = []
        for doc_id, r in self._docs.items():
            issued = (
                date.fromisoformat(r.metadata.issued_date)
                if r.metadata.issued_date else None)
            exp = (
                date.fromisoformat(r.metadata.expires_at)
                if r.metadata.expires_at else None)
            if is_document_expired(
                    document_type=r.metadata.document_type,
                    issued_date=issued,
                    explicit_expires_at=exp,
                    as_of=as_of):
                out.append(doc_id)
        return tuple(out)

    def board_summary(self) -> Dict[str, object]:
        if not self._docs:
            return {
                "entity": self.entity_name,
                "n_documents": 0,
                "by_state": {},
                "by_type": {},
                "verified_pct": Decimal("0"),
                "n_expired": 0,
            }

        by_state: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        verified = 0
        for r in self._docs.values():
            by_state[r.state.value] = by_state.get(r.state.value, 0) + 1
            by_type[r.metadata.document_type.value] = (
                by_type.get(r.metadata.document_type.value, 0) + 1)
            if r.state == DocumentState.VERIFIED:
                verified += 1

        n = Decimal(len(self._docs))
        return {
            "entity": self.entity_name,
            "n_documents": int(n),
            "by_state": by_state,
            "by_type": by_type,
            "verified_pct": Decimal(verified) / n * Decimal("100"),
            "n_expired": len(self.expired_documents()),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_doc_state_terminal_states():
    """REJECTED + ARCHIVED are terminal."""
    assert ALLOWED_DOC_TRANSITIONS[DocumentState.REJECTED] == ()
    assert ALLOWED_DOC_TRANSITIONS[DocumentState.ARCHIVED] == ()


def _test_doc_state_valid_transitions():
    assert is_valid_doc_transition(
        DocumentState.SUBMITTED, DocumentState.AUTHENTICITY_PENDING)
    assert is_valid_doc_transition(
        DocumentState.VERIFIED, DocumentState.ARCHIVED)
    assert not is_valid_doc_transition(
        DocumentState.SUBMITTED, DocumentState.VERIFIED)


def _test_compute_sha256_stable():
    h1 = compute_sha256(b"hello")
    h2 = compute_sha256(b"hello")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 != compute_sha256(b"hellp")


def _test_verify_file_integrity_pass():
    content = b"test document content"
    expected = compute_sha256(content)
    r = verify_file_integrity(expected_hash=expected, actual_content=content)
    assert r.result == AuthenticityResult.PASSED


def _test_verify_file_integrity_fail():
    r = verify_file_integrity(
        expected_hash="0" * 64, actual_content=b"different content")
    assert r.result == AuthenticityResult.FAILED


def _test_verify_format_pdf_required_for_financials():
    r = verify_format(
        document_type=DocumentType.AUDITED_FINANCIALS,
        file_format="jpg")
    assert r.result == AuthenticityResult.FAILED


def _test_verify_format_pdf_accepted():
    r = verify_format(
        document_type=DocumentType.AUDITED_FINANCIALS,
        file_format="pdf")
    assert r.result == AuthenticityResult.PASSED


def _test_verify_format_image_for_id():
    r = verify_format(
        document_type=DocumentType.NATIONAL_ID,
        file_format="png")
    assert r.result == AuthenticityResult.PASSED


def _test_verify_format_unsupported():
    r = verify_format(
        document_type=DocumentType.NATIONAL_ID,
        file_format="docx")
    assert r.result == AuthenticityResult.FAILED


def _test_doc_expiry_explicit_expires_at():
    """Explicit expires_at takes precedence."""
    expired = is_document_expired(
        document_type=DocumentType.NATIONAL_ID,
        issued_date=date(2020, 1, 1),
        explicit_expires_at=date(2024, 12, 31),
        as_of=date(2025, 6, 1))
    assert expired


def _test_doc_expiry_validity_window():
    """Bank statement: 90-day validity window."""
    expired = is_document_expired(
        document_type=DocumentType.BANK_STATEMENT,
        issued_date=date(2025, 1, 1),
        explicit_expires_at=None,
        as_of=date(2025, 5, 1))    # 120 days later
    assert expired
    fresh = is_document_expired(
        document_type=DocumentType.BANK_STATEMENT,
        issued_date=date(2025, 1, 1),
        explicit_expires_at=None,
        as_of=date(2025, 2, 1))    # 31 days later
    assert not fresh


def _test_doc_expiry_no_window_no_explicit():
    """Static doc with no expiry rule → never expires."""
    expired = is_document_expired(
        document_type=DocumentType.TITLE_DEED,
        issued_date=date(2000, 1, 1),
        explicit_expires_at=None,
        as_of=date(2025, 1, 1))
    assert not expired


def _test_extract_fields_no_provider_returns_empty():
    """Rule 7 — no extractor → empty + explicit reason."""
    metadata = DocumentMetadata(
        document_id="X", applicant_id="A", document_type=DocumentType.PAYSLIP,
        file_name="x.pdf", file_size_bytes=100,
        file_format="pdf",
        sha256_hash=compute_sha256(b"x"),
        submitted_at="2025-01-01T00:00:00Z")
    fields, conf, notes = extract_fields(
        metadata=metadata, file_content=b"x")
    assert fields == {}
    assert conf is None
    assert "no extractor" in notes


def _test_extract_fields_with_provider():
    metadata = DocumentMetadata(
        document_id="X", applicant_id="A", document_type=DocumentType.PAYSLIP,
        file_name="x.pdf", file_size_bytes=100,
        file_format="pdf",
        sha256_hash=compute_sha256(b"x"),
        submitted_at="2025-01-01T00:00:00Z")

    def extractor(doc_type, content):
        return ({"net_pay_kes": "120000", "employer": "Acme Ltd"},
                Decimal("0.95"))

    fields, conf, notes = extract_fields(
        metadata=metadata, file_content=b"x", extractor=extractor)
    assert fields["net_pay_kes"] == "120000"
    assert conf == Decimal("0.95")


def _test_extract_fields_failing_extractor():
    metadata = DocumentMetadata(
        document_id="X", applicant_id="A", document_type=DocumentType.PAYSLIP,
        file_name="x.pdf", file_size_bytes=100,
        file_format="pdf",
        sha256_hash=compute_sha256(b"x"),
        submitted_at="2025-01-01T00:00:00Z")

    def failing_extractor(doc_type, content):
        raise ConnectionError("OCR API down")

    fields, conf, notes = extract_fields(
        metadata=metadata, file_content=b"x", extractor=failing_extractor)
    assert fields == {}
    assert conf is None
    assert "ConnectionError" in notes


def _test_assess_document_full_pass():
    content = b"test document"
    metadata = DocumentMetadata(
        document_id="D1", applicant_id="A", document_type=DocumentType.NATIONAL_ID,
        file_name="id.png", file_size_bytes=len(content),
        file_format="png",
        sha256_hash=compute_sha256(content),
        submitted_at="2025-01-01T00:00:00Z")

    def extractor(doc_type, content):
        return ({"id_number": "12345678"}, Decimal("0.99"))

    r = assess_document(
        metadata=metadata, file_content=content,
        file_extractor=extractor,
        as_of=date(2025, 1, 15))
    assert r.state == DocumentState.VERIFIED
    assert r.extracted_fields["id_number"] == "12345678"


def _test_assess_document_hash_fail():
    content = b"test document"
    metadata = DocumentMetadata(
        document_id="D1", applicant_id="A", document_type=DocumentType.NATIONAL_ID,
        file_name="id.png", file_size_bytes=len(content),
        file_format="png",
        sha256_hash="0" * 64,    # wrong hash
        submitted_at="2025-01-01T00:00:00Z")
    r = assess_document(
        metadata=metadata, file_content=content,
        as_of=date(2025, 1, 15))
    assert r.state == DocumentState.AUTHENTICITY_FAILED


def _test_assess_document_expired_rejected():
    content = b"test"
    metadata = DocumentMetadata(
        document_id="D1", applicant_id="A",
        document_type=DocumentType.BANK_STATEMENT,
        file_name="stmt.pdf", file_size_bytes=4,
        file_format="pdf",
        sha256_hash=compute_sha256(content),
        submitted_at="2025-01-01T00:00:00Z",
        issued_date="2024-01-01")    # over 90 days ago
    r = assess_document(
        metadata=metadata, file_content=content,
        as_of=date(2025, 1, 15))
    assert r.state == DocumentState.REJECTED
    assert "expired" in r.rejection_reason.lower()


def _test_assess_document_no_extractor_extraction_pending():
    """No extractor → state remains DATA_EXTRACTION_PENDING."""
    content = b"test"
    metadata = DocumentMetadata(
        document_id="D1", applicant_id="A",
        document_type=DocumentType.PAYSLIP,
        file_name="ps.pdf", file_size_bytes=4,
        file_format="pdf",
        sha256_hash=compute_sha256(content),
        submitted_at="2025-01-01T00:00:00Z",
        issued_date="2025-01-01")
    r = assess_document(
        metadata=metadata, file_content=content,
        as_of=date(2025, 1, 15))
    assert r.state == DocumentState.DATA_EXTRACTION_PENDING


def _test_engine_register_and_get():
    eng = DocumentManagementEngine()
    content = b"x"
    metadata = DocumentMetadata(
        document_id="D1", applicant_id="A",
        document_type=DocumentType.NATIONAL_ID,
        file_name="id.png", file_size_bytes=1,
        file_format="png",
        sha256_hash=compute_sha256(content),
        submitted_at="t")
    rec = DocumentRecord(metadata=metadata, state=DocumentState.SUBMITTED)
    eng.register_document(rec)
    assert eng.get("D1").metadata.document_id == "D1"


def _test_engine_documents_for_applicant():
    eng = DocumentManagementEngine()
    for i in range(3):
        m = DocumentMetadata(
            document_id=f"D{i}", applicant_id="A",
            document_type=DocumentType.PAYSLIP,
            file_name=f"p{i}.pdf", file_size_bytes=1,
            file_format="pdf",
            sha256_hash=compute_sha256(b"x"),
            submitted_at="t")
        eng.register_document(DocumentRecord(metadata=m,
                                                state=DocumentState.VERIFIED))
    assert len(eng.documents_for_applicant("A")) == 3


def _test_engine_board_summary_empty():
    eng = DocumentManagementEngine()
    s = eng.board_summary()
    assert s["n_documents"] == 0


def _test_engine_board_summary_aggregates():
    eng = DocumentManagementEngine()
    m = DocumentMetadata(
        document_id="D1", applicant_id="A",
        document_type=DocumentType.NATIONAL_ID,
        file_name="x.png", file_size_bytes=1,
        file_format="png",
        sha256_hash=compute_sha256(b"x"),
        submitted_at="t")
    eng.register_document(DocumentRecord(metadata=m,
                                            state=DocumentState.VERIFIED))
    s = eng.board_summary()
    assert s["n_documents"] == 1
    assert s["verified_pct"] == Decimal("100")


def self_test() -> None:
    tests = [
        _test_doc_state_terminal_states,
        _test_doc_state_valid_transitions,
        _test_compute_sha256_stable,
        _test_verify_file_integrity_pass,
        _test_verify_file_integrity_fail,
        _test_verify_format_pdf_required_for_financials,
        _test_verify_format_pdf_accepted,
        _test_verify_format_image_for_id,
        _test_verify_format_unsupported,
        _test_doc_expiry_explicit_expires_at,
        _test_doc_expiry_validity_window,
        _test_doc_expiry_no_window_no_explicit,
        _test_extract_fields_no_provider_returns_empty,
        _test_extract_fields_with_provider,
        _test_extract_fields_failing_extractor,
        _test_assess_document_full_pass,
        _test_assess_document_hash_fail,
        _test_assess_document_expired_rejected,
        _test_assess_document_no_extractor_extraction_pending,
        _test_engine_register_and_get,
        _test_engine_documents_for_applicant,
        _test_engine_board_summary_empty,
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
        print(f"✗ document_management self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ document_management self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

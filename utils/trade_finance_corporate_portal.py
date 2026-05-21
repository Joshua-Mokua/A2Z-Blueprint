"""utils/trade_finance_corporate_portal.py — v10.79: TF portal.

ENH-271 — Corporate Trade Portal (data layer). Cat B —
trade_finance arc 9/N.

Front-office data-validation + routing engine for the corporate
self-service trade portal. Engine validates structures, classifies
intent, and surfaces routing decisions; the actual LC issuance,
amendment processing, document storage, message dispatch, and
fee posting happen in the operations layer downstream. Engine is
DIAGNOSTIC + ROUTING ONLY.

Five capabilities:

  1. validate_lc_application — corporate LC application submission
     structural validation. Field-level findings on required
     fields missing, format violations, amount sanity, date
     ordering. 3-tier ApplicationCompleteness outcome (COMPLETE
     / INCOMPLETE / INVALID).

  2. classify_amendment_request — amendment request type
     classification (7 categories: expiry extension, amount
     increase/decrease, beneficiary change, goods description
     change, terms change, withdrawal) + 3-tier impact
     classification (LOW/MEDIUM/HIGH) + required-approval
     surfacing.

  3. track_instrument_status — given TradeInstrument from
     ENH-269, build a status snapshot with milestones (days to
     expiry, days to latest shipment, presentation deadline if
     shipped). Pure read; engine never mutates instrument state.

  4. validate_document_upload — structural validation of upload
     metadata (filename, declared type, size, declared
     document_type). 4-tier DocumentValidationOutcome ladder
     (ACCEPTED / REJECTED_TYPE / REJECTED_SIZE /
     REJECTED_METADATA). Does NOT touch file contents (upstream
     extraction territory — that's ENH-270's CONSUMER's
     territory).

  5. classify_message_routing — corporate-message routing
     classification. 4-tier MessageRoutingDestination ladder
     (OPS_QUEUE / RM_QUEUE / ESCALATION_QUEUE / INFO_ONLY)
     driven by caller-supplied keyword catalogues (operationally
     maintained per bank routing policy — same discipline as
     ENH-274 sanctions lists, ENH-278 taxonomies).

Per Rule 7, engine NEVER:
  - issues LCs (operations layer territory after corporate
    submits + bank approves)
  - amends LCs (operations layer)
  - stores documents (document management system territory)
  - sends messages or notifications (messaging system territory)
  - posts fees or accounting entries (ENH-275 territory)
  - decides accept/reject on applications (RM + Credit decide
    based on engine output)
  - mutates inputs

Per Rule 1, every output surfaces validation findings + routing
rationale + framework_refs.

Pure stdlib runtime.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import (
    Dict, List, Mapping, Optional, Sequence, Tuple)

from utils.trade_finance_instruments import (
    TradeInstrument, InstrumentState, InstrumentType)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceCorporatePortalEngine implements ENH-271 — "
    "data-layer validation and routing for the corporate self-"
    "service trade portal. UI lives in the closure cockpit page "
    "at v10.80. Engine validates structures + classifies intent "
    "+ surfaces routing; never issues LCs, never amends LCs, "
    "never stores documents, never sends messages, never posts "
    "fees, never decides accept/reject on applications "
    "(operations + RM + Credit decide based on engine output). "
    "Pure stdlib. Per Rule 1, every output surfaces validation "
    "findings + routing rationale + framework_refs. Per Rule 7, "
    "engine DIAGNOSTIC + ROUTING ONLY — never mutates inputs."
)

# Sensible upper bound for a single LC application amount —
# rejects obvious data-entry errors. Caller can override per
# bank policy.
DEFAULT_MAX_LC_AMOUNT_KES: Decimal = Decimal("10000000000")  # 10b

# Allowed file types for document uploads (caller can override)
DEFAULT_ALLOWED_FILE_EXTENSIONS: Tuple[str, ...] = (
    ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif")

# Default max upload size in bytes (10MB). Caller overrides.
DEFAULT_MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class ApplicationCompleteness(Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"   # missing optional but expected fields
    INVALID = "INVALID"         # required fields missing / malformed


class FieldFindingSeverity(Enum):
    CRITICAL = "CRITICAL"       # required field missing or malformed
    HIGH = "HIGH"               # business rule violation
    MEDIUM = "MEDIUM"           # data sanity concern
    LOW = "LOW"                 # advisory


class AmendmentType(Enum):
    EXPIRY_EXTENSION = "EXPIRY_EXTENSION"
    AMOUNT_INCREASE = "AMOUNT_INCREASE"
    AMOUNT_DECREASE = "AMOUNT_DECREASE"
    BENEFICIARY_CHANGE = "BENEFICIARY_CHANGE"
    GOODS_DESCRIPTION_CHANGE = "GOODS_DESCRIPTION_CHANGE"
    TERMS_CHANGE = "TERMS_CHANGE"
    WITHDRAW = "WITHDRAW"
    UNKNOWN = "UNKNOWN"


class AmendmentImpact(Enum):
    LOW = "LOW"      # routine, may be auto-routed
    MEDIUM = "MEDIUM"  # ops review
    HIGH = "HIGH"    # credit committee approval typically required


class DocumentValidationOutcome(Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED_TYPE = "REJECTED_TYPE"
    REJECTED_SIZE = "REJECTED_SIZE"
    REJECTED_METADATA = "REJECTED_METADATA"


class MessageRoutingDestination(Enum):
    OPS_QUEUE = "OPS_QUEUE"
    RM_QUEUE = "RM_QUEUE"
    ESCALATION_QUEUE = "ESCALATION_QUEUE"
    INFO_ONLY = "INFO_ONLY"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LCApplication:
    """Corporate-submitted LC application — distinct from
    LCTerms (which represents an issued LC). Application is a
    request; Terms is what gets approved.
    """
    application_id: str
    applicant: str
    beneficiary: str
    requested_amount_kes: Optional[Decimal]
    currency: Optional[str]
    requested_expiry_date: Optional[date]
    requested_latest_shipment_date: Optional[date]
    description_of_goods: Optional[str]
    incoterms: Optional[str]
    instrument_type: Optional[InstrumentType] = None
    submission_date: Optional[date] = None
    raw_fields: Mapping[str, str] = field(
        default_factory=dict)


@dataclass(frozen=True)
class AmendmentRequest:
    """Corporate-submitted amendment against an existing LC."""
    amendment_id: str
    lc_reference: str
    requested_at: date
    new_amount_kes: Optional[Decimal] = None
    new_expiry_date: Optional[date] = None
    new_beneficiary: Optional[str] = None
    new_description_of_goods: Optional[str] = None
    new_incoterms: Optional[str] = None
    free_text_request: Optional[str] = None
    withdraw: bool = False


@dataclass(frozen=True)
class DocumentUpload:
    upload_id: str
    filename: str
    declared_document_type: str
    declared_size_bytes: int
    raw_metadata: Mapping[str, str] = field(
        default_factory=dict)


@dataclass(frozen=True)
class CorporateMessage:
    message_id: str
    sender: str
    body: str
    lc_reference: Optional[str] = None
    sent_at: Optional[date] = None


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FieldFinding:
    field_name: str
    severity: FieldFindingSeverity
    description: str
    expected: str
    observed: str


@dataclass(frozen=True)
class LCApplicationValidation:
    application_id: str
    completeness: ApplicationCompleteness
    findings: Tuple[FieldFinding, ...]
    estimated_fees_kes: Optional[Decimal]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class AmendmentClassification:
    amendment_id: str
    lc_reference: str
    detected_types: Tuple[AmendmentType, ...]
    primary_type: AmendmentType
    impact: AmendmentImpact
    required_approvals: Tuple[str, ...]
    reasoning: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class InstrumentStatusSnapshot:
    instrument_id: str
    state: InstrumentState
    days_until_expiry: Optional[int]
    days_until_latest_shipment: Optional[int]
    is_within_presentation_period: Optional[bool]
    milestones: Tuple[Tuple[str, str], ...]   # (label, value)
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class DocumentUploadValidation:
    upload_id: str
    outcome: DocumentValidationOutcome
    rejection_reasons: Tuple[str, ...]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class MessageRoutingClassification:
    message_id: str
    destination: MessageRoutingDestination
    matched_keywords: Tuple[Tuple[str, str], ...]   # (kw, dest)
    reasoning: str
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceCorporatePortalEngine:
    """Front-office data validation + routing engine."""

    def __init__(
        self,
        max_lc_amount_kes: Decimal = DEFAULT_MAX_LC_AMOUNT_KES,
        allowed_file_extensions: Tuple[str, ...] = (
            DEFAULT_ALLOWED_FILE_EXTENSIONS),
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ) -> None:
        self.max_lc_amount_kes = max_lc_amount_kes
        # Lowercased + leading-dot extensions
        self.allowed_file_extensions = tuple(
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in allowed_file_extensions)
        self.max_upload_bytes = max_upload_bytes

    # ─── 1. LC application validation ──────────────────────────
    def validate_lc_application(
        self,
        application: LCApplication,
    ) -> LCApplicationValidation:
        findings: List[FieldFinding] = []

        # Required fields
        if not application.applicant:
            findings.append(FieldFinding(
                field_name="applicant",
                severity=FieldFindingSeverity.CRITICAL,
                description="Applicant name required",
                expected="non-empty string",
                observed="empty"))
        if not application.beneficiary:
            findings.append(FieldFinding(
                field_name="beneficiary",
                severity=FieldFindingSeverity.CRITICAL,
                description="Beneficiary name required",
                expected="non-empty string",
                observed="empty"))
        if application.requested_amount_kes is None:
            findings.append(FieldFinding(
                field_name="requested_amount_kes",
                severity=FieldFindingSeverity.CRITICAL,
                description="Amount required",
                expected="positive Decimal",
                observed="None"))
        elif application.requested_amount_kes <= 0:
            findings.append(FieldFinding(
                field_name="requested_amount_kes",
                severity=FieldFindingSeverity.CRITICAL,
                description="Amount must be positive",
                expected="> 0",
                observed=str(
                    application.requested_amount_kes)))
        elif (
            application.requested_amount_kes
            > self.max_lc_amount_kes
        ):
            findings.append(FieldFinding(
                field_name="requested_amount_kes",
                severity=FieldFindingSeverity.HIGH,
                description=(
                    "Amount exceeds bank policy upper bound — "
                    "likely data-entry error or requires "
                    "special approval"),
                expected=f"≤ {self.max_lc_amount_kes}",
                observed=str(
                    application.requested_amount_kes)))
        if not application.currency:
            findings.append(FieldFinding(
                field_name="currency",
                severity=FieldFindingSeverity.CRITICAL,
                description="Currency required",
                expected="3-letter ISO 4217 code",
                observed="empty"))
        elif (
            len(application.currency) != 3
            or not application.currency.isalpha()
        ):
            findings.append(FieldFinding(
                field_name="currency",
                severity=FieldFindingSeverity.HIGH,
                description=(
                    "Currency must be 3-letter ISO 4217 code"),
                expected="e.g. USD, KES, EUR",
                observed=application.currency))

        if application.requested_expiry_date is None:
            findings.append(FieldFinding(
                field_name="requested_expiry_date",
                severity=FieldFindingSeverity.CRITICAL,
                description="Expiry date required",
                expected="date",
                observed="None"))

        # Date ordering — only check when both present
        if (
            application.requested_expiry_date is not None
            and application.requested_latest_shipment_date
            is not None
        ):
            if (
                application.requested_latest_shipment_date
                > application.requested_expiry_date
            ):
                findings.append(FieldFinding(
                    field_name=(
                        "requested_latest_shipment_date"),
                    severity=FieldFindingSeverity.HIGH,
                    description=(
                        "Latest shipment date after expiry "
                        "date — invalid ordering"),
                    expected=(
                        "latest_shipment ≤ expiry"),
                    observed=(
                        f"shipment="
                        f"{application.requested_latest_shipment_date.isoformat()} "
                        f"vs expiry="
                        f"{application.requested_expiry_date.isoformat()}")))

        # Submission date forward-dated check
        if (
            application.submission_date is not None
            and application.requested_expiry_date is not None
            and application.requested_expiry_date
            <= application.submission_date
        ):
            findings.append(FieldFinding(
                field_name="requested_expiry_date",
                severity=FieldFindingSeverity.HIGH,
                description=(
                    "Expiry date on or before submission "
                    "date — LC would be expired at issuance"),
                expected="expiry > submission",
                observed=(
                    f"expiry="
                    f"{application.requested_expiry_date.isoformat()} "
                    f"vs submission="
                    f"{application.submission_date.isoformat()}")))

        # Optional but expected fields
        if not application.description_of_goods:
            findings.append(FieldFinding(
                field_name="description_of_goods",
                severity=FieldFindingSeverity.MEDIUM,
                description=(
                    "Description of goods missing — required "
                    "for UCP 600 §14(e) examination"),
                expected="non-empty description",
                observed="empty"))

        if not application.incoterms:
            findings.append(FieldFinding(
                field_name="incoterms",
                severity=FieldFindingSeverity.LOW,
                description=(
                    "Incoterms not specified — operations "
                    "team will follow up"),
                expected="e.g. CIF / FOB / EXW + named place",
                observed="empty"))

        # Outcome
        has_critical = any(
            f.severity == FieldFindingSeverity.CRITICAL
            for f in findings)
        has_high = any(
            f.severity == FieldFindingSeverity.HIGH
            for f in findings)
        if has_critical:
            completeness = ApplicationCompleteness.INVALID
        elif has_high or any(
            f.severity == FieldFindingSeverity.MEDIUM
            for f in findings
        ):
            completeness = ApplicationCompleteness.INCOMPLETE
        else:
            completeness = ApplicationCompleteness.COMPLETE

        # Estimated fees: simple 0.5% issuance fee preliminary
        # estimate. NOT a posted fee (Rule 7). Caller can apply
        # bank fee schedule downstream.
        est_fees: Optional[Decimal] = None
        if (
            application.requested_amount_kes is not None
            and application.requested_amount_kes > 0
        ):
            est_fees = (
                application.requested_amount_kes
                * Decimal("0.005")
            ).quantize(Decimal("0.01"))

        return LCApplicationValidation(
            application_id=application.application_id,
            completeness=completeness,
            findings=tuple(findings),
            estimated_fees_kes=est_fees,
            framework_refs=(
                "ENH-271 §validate_lc_application",
                "UCP 600 §14(e) — description of goods "
                "examination requires non-empty description",
                "ISO 4217 — currency code format",
                "Per Rule 1 — field-level findings surfaced",
                "Per Rule 7 — engine never accepts/rejects "
                "the application; RM + Credit decide based on "
                "validation output; estimated_fees_kes is "
                "preliminary estimate, not a posted fee",
            ),
        )

    # ─── 2. Amendment classification ───────────────────────────
    def classify_amendment_request(
        self,
        amendment: AmendmentRequest,
        existing_lc_amount_kes: Optional[Decimal] = None,
        existing_lc_expiry: Optional[date] = None,
    ) -> AmendmentClassification:
        """Classify amendment type, impact, and required approvals.

        existing_lc_amount_kes / existing_lc_expiry are caller-
        supplied for comparison against the requested values.
        When None, comparisons skipped.
        """
        types: List[AmendmentType] = []

        if amendment.withdraw:
            types.append(AmendmentType.WITHDRAW)
        if amendment.new_expiry_date is not None:
            types.append(AmendmentType.EXPIRY_EXTENSION)
        if amendment.new_amount_kes is not None:
            if (
                existing_lc_amount_kes is not None
                and amendment.new_amount_kes
                > existing_lc_amount_kes
            ):
                types.append(AmendmentType.AMOUNT_INCREASE)
            elif (
                existing_lc_amount_kes is not None
                and amendment.new_amount_kes
                < existing_lc_amount_kes
            ):
                types.append(AmendmentType.AMOUNT_DECREASE)
            else:
                # No baseline — tentative classification as
                # increase pending operations confirmation
                types.append(AmendmentType.AMOUNT_INCREASE)
        if amendment.new_beneficiary is not None:
            types.append(AmendmentType.BENEFICIARY_CHANGE)
        if amendment.new_description_of_goods is not None:
            types.append(AmendmentType.GOODS_DESCRIPTION_CHANGE)
        if amendment.new_incoterms is not None:
            types.append(AmendmentType.TERMS_CHANGE)

        if not types:
            types.append(AmendmentType.UNKNOWN)
            primary = AmendmentType.UNKNOWN
        else:
            # Primary type — most-impactful in the list
            primary = self._most_impactful(types)

        impact = self._classify_amendment_impact(types)
        approvals = self._required_approvals(types, impact)
        reasoning = self._amendment_reasoning(
            amendment, types, primary)

        return AmendmentClassification(
            amendment_id=amendment.amendment_id,
            lc_reference=amendment.lc_reference,
            detected_types=tuple(types),
            primary_type=primary,
            impact=impact,
            required_approvals=approvals,
            reasoning=reasoning,
            framework_refs=(
                "ENH-271 §classify_amendment_request",
                "UCP 600 §10 — amendments require "
                "issuing/confirming bank consent + "
                "beneficiary acceptance",
                "Per Rule 1 — all detected amendment types "
                "surfaced (operator sees full picture, not "
                "just the primary)",
                "Per Rule 7 — engine classifies; operations "
                "+ Credit decide; engine never amends the "
                "actual LC",
            ),
        )

    @staticmethod
    def _most_impactful(
        types: Sequence[AmendmentType],
    ) -> AmendmentType:
        """Order types by typical impact, return the highest."""
        impact_order = (
            AmendmentType.WITHDRAW,
            AmendmentType.AMOUNT_INCREASE,
            AmendmentType.BENEFICIARY_CHANGE,
            AmendmentType.GOODS_DESCRIPTION_CHANGE,
            AmendmentType.TERMS_CHANGE,
            AmendmentType.AMOUNT_DECREASE,
            AmendmentType.EXPIRY_EXTENSION,
            AmendmentType.UNKNOWN)
        for t in impact_order:
            if t in types:
                return t
        return AmendmentType.UNKNOWN

    @staticmethod
    def _classify_amendment_impact(
        types: Sequence[AmendmentType],
    ) -> AmendmentImpact:
        # HIGH-impact types
        if any(t in types for t in (
            AmendmentType.AMOUNT_INCREASE,
            AmendmentType.BENEFICIARY_CHANGE,
        )):
            return AmendmentImpact.HIGH
        # MEDIUM-impact types
        if any(t in types for t in (
            AmendmentType.GOODS_DESCRIPTION_CHANGE,
            AmendmentType.TERMS_CHANGE,
            AmendmentType.WITHDRAW,
        )):
            return AmendmentImpact.MEDIUM
        # LOW-impact types — expiry extensions, amount
        # decreases (releases exposure)
        return AmendmentImpact.LOW

    @staticmethod
    def _required_approvals(
        types: Sequence[AmendmentType],
        impact: AmendmentImpact,
    ) -> Tuple[str, ...]:
        approvals: List[str] = ["operations"]
        if impact == AmendmentImpact.HIGH:
            approvals.append("credit_committee")
        if AmendmentType.AMOUNT_INCREASE in types:
            approvals.append("limit_review")
        if AmendmentType.BENEFICIARY_CHANGE in types:
            approvals.append("compliance_screening")
        if AmendmentType.WITHDRAW in types:
            approvals.append("rm_approval")
        return tuple(approvals)

    @staticmethod
    def _amendment_reasoning(
        amendment: AmendmentRequest,
        types: Sequence[AmendmentType],
        primary: AmendmentType,
    ) -> str:
        parts = [
            f"Detected {len(types)} amendment type(s); "
            f"primary={primary.value}"]
        if amendment.new_amount_kes is not None:
            parts.append(
                f"new amount: {amendment.new_amount_kes}")
        if amendment.new_expiry_date is not None:
            parts.append(
                f"new expiry: "
                f"{amendment.new_expiry_date.isoformat()}")
        if amendment.new_beneficiary is not None:
            parts.append(
                f"new beneficiary: "
                f"{amendment.new_beneficiary}")
        return "; ".join(parts)

    # ─── 3. Instrument status tracking ─────────────────────────
    def track_instrument_status(
        self,
        instrument: TradeInstrument,
        as_of: date,
    ) -> InstrumentStatusSnapshot:
        days_to_expiry = (
            instrument.expiry_date - as_of).days
        days_to_shipment: Optional[int] = None
        # TradeInstrument from ENH-269 may not always carry
        # latest_shipment_date — guard with raw_fields lookup
        latest_shipment_str = (
            getattr(instrument, "latest_shipment_date", None))
        if isinstance(latest_shipment_str, date):
            days_to_shipment = (
                latest_shipment_str - as_of).days

        # Presentation-period evaluation requires actual shipment
        # which the instrument record may not carry. Surface as
        # None to indicate "not determinable from this snapshot
        # alone" rather than fabricating a value.
        within_presentation_period: Optional[bool] = None

        milestones: List[Tuple[str, str]] = []
        milestones.append(
            ("Issue date", instrument.issue_date.isoformat()))
        milestones.append(
            ("Expiry date",
             instrument.expiry_date.isoformat()))
        if isinstance(latest_shipment_str, date):
            milestones.append(
                ("Latest shipment date",
                 latest_shipment_str.isoformat()))
        milestones.append(
            ("Current state", instrument.state.value))
        milestones.append(
            ("As-of date", as_of.isoformat()))

        return InstrumentStatusSnapshot(
            instrument_id=instrument.instrument_id,
            state=instrument.state,
            days_until_expiry=days_to_expiry,
            days_until_latest_shipment=days_to_shipment,
            is_within_presentation_period=(
                within_presentation_period),
            milestones=tuple(milestones),
            framework_refs=(
                "ENH-271 §track_instrument_status",
                "UCP 600 §6 — expiry awareness for "
                "drawdown windows",
                "UCP 600 §29 — latest shipment date "
                "(when present in instrument record)",
                "Per Rule 1 — surface None for "
                "is_within_presentation_period when actual "
                "shipment date not in instrument record "
                "rather than fabricate a value",
                "Per Rule 7 — read-only snapshot; engine "
                "never mutates instrument state",
            ),
        )

    # ─── 4. Document upload validation ─────────────────────────
    def validate_document_upload(
        self,
        upload: DocumentUpload,
        required_metadata_keys: Sequence[str] = (),
    ) -> DocumentUploadValidation:
        """Structural validation of upload metadata only —
        does NOT touch file contents (upstream extraction
        territory).
        """
        rejection_reasons: List[str] = []

        # File extension
        filename_lower = upload.filename.lower()
        ext = ""
        for allowed in self.allowed_file_extensions:
            if filename_lower.endswith(allowed):
                ext = allowed
                break
        if not ext:
            rejection_reasons.append(
                f"File extension not in allowed list: "
                f"{self.allowed_file_extensions}")
        # Size
        if upload.declared_size_bytes < 0:
            rejection_reasons.append(
                "Declared size negative — malformed metadata")
        elif (
            upload.declared_size_bytes > self.max_upload_bytes
        ):
            rejection_reasons.append(
                f"File size {upload.declared_size_bytes} "
                f"exceeds limit {self.max_upload_bytes} bytes")
        # Document type declared
        if not upload.declared_document_type:
            rejection_reasons.append(
                "declared_document_type field missing or "
                "empty")
        # Required metadata keys
        for k in required_metadata_keys:
            if k not in upload.raw_metadata:
                rejection_reasons.append(
                    f"Required metadata key missing: '{k}'")

        # Outcome — order matters: type rejection before size
        # before metadata, so the first surfaced reason is the
        # most-fundamental
        if not ext:
            outcome = (
                DocumentValidationOutcome.REJECTED_TYPE)
        elif (
            upload.declared_size_bytes < 0
            or upload.declared_size_bytes
            > self.max_upload_bytes
        ):
            outcome = (
                DocumentValidationOutcome.REJECTED_SIZE)
        elif rejection_reasons:
            outcome = (
                DocumentValidationOutcome.REJECTED_METADATA)
        else:
            outcome = DocumentValidationOutcome.ACCEPTED

        return DocumentUploadValidation(
            upload_id=upload.upload_id,
            outcome=outcome,
            rejection_reasons=tuple(rejection_reasons),
            framework_refs=(
                "ENH-271 §validate_document_upload",
                f"Allowed extensions: "
                f"{self.allowed_file_extensions}",
                f"Max upload size: "
                f"{self.max_upload_bytes} bytes",
                "Per Rule 1 — all rejection reasons surfaced "
                "(not just first)",
                "Per Rule 7 — engine validates metadata only; "
                "never opens / parses / stores the file "
                "(document management system territory)",
            ),
        )

    # ─── 5. Message routing classification ─────────────────────
    def classify_message_routing(
        self,
        message: CorporateMessage,
        keyword_routing: Mapping[
            str, MessageRoutingDestination],
    ) -> MessageRoutingClassification:
        """Classify routing destination based on caller-supplied
        keyword catalogue.

        keyword_routing is a mapping from keyword → destination.
        Operationally maintained per bank routing policy — same
        discipline as ENH-274 sanctions lists, ENH-278
        taxonomies. Engine bundles no keywords.
        """
        body_lower = message.body.lower() if message.body else ""
        matched: List[
            Tuple[str, MessageRoutingDestination]] = []
        for kw, dest in keyword_routing.items():
            if not kw:
                continue
            if len(kw) < 3:
                # Same 3-char floor as ENH-278 — prevent
                # substring false positives
                continue
            pattern = (
                r"\b" + re.escape(kw.lower()) + r"\b")
            if re.search(pattern, body_lower):
                matched.append((kw, dest))

        if not matched:
            destination = MessageRoutingDestination.OPS_QUEUE
            reasoning = (
                "No keyword matches → default to OPS_QUEUE "
                "for triage")
        else:
            # Select most-escalated destination among matches
            order = (
                MessageRoutingDestination.ESCALATION_QUEUE,
                MessageRoutingDestination.RM_QUEUE,
                MessageRoutingDestination.OPS_QUEUE,
                MessageRoutingDestination.INFO_ONLY)
            destinations_seen = {d for _, d in matched}
            destination = next(
                (d for d in order
                 if d in destinations_seen),
                MessageRoutingDestination.OPS_QUEUE)
            reasoning = (
                f"Matched {len(matched)} keyword(s) → "
                f"most-escalated destination "
                f"{destination.value}")

        return MessageRoutingClassification(
            message_id=message.message_id,
            destination=destination,
            matched_keywords=tuple(
                (kw, d.value) for kw, d in matched),
            reasoning=reasoning,
            framework_refs=(
                "ENH-271 §classify_message_routing",
                "Caller-supplied keyword routing catalogue — "
                "operationally maintained per bank routing "
                "policy",
                "Word-boundary regex (\\b) — same 3-char floor "
                "as ENH-278 to prevent substring false "
                "positives",
                "Per Rule 1 — all matched keywords surfaced",
                "Per Rule 7 — engine classifies routing; "
                "never sends the message to the queue (that's "
                "the messaging system's territory)",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_application(
    aid="APP-1", applicant="Acme Imports",
    beneficiary="RiceCo", amount=Decimal("1000000"),
    currency="USD",
    expiry=date(2026, 8, 1),
    shipment=date(2026, 7, 15),
    desc="50 metric tons milled rice",
    incoterms="CIF Mombasa",
    submission=date(2026, 5, 1),
):
    return LCApplication(
        application_id=aid, applicant=applicant,
        beneficiary=beneficiary,
        requested_amount_kes=amount,
        currency=currency,
        requested_expiry_date=expiry,
        requested_latest_shipment_date=shipment,
        description_of_goods=desc,
        incoterms=incoterms,
        submission_date=submission)


# ─── Application validation tests ──────────────────────────────

def _test_app_complete():
    eng = TradeFinanceCorporatePortalEngine()
    v = eng.validate_lc_application(_make_application())
    assert v.completeness == (
        ApplicationCompleteness.COMPLETE)
    assert v.findings == ()
    # Estimated fees: 0.5% × 1m = 5000
    assert v.estimated_fees_kes == Decimal("5000.00")


def _test_app_missing_applicant():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(applicant="")
    v = eng.validate_lc_application(app)
    assert v.completeness == (
        ApplicationCompleteness.INVALID)
    assert any(
        f.field_name == "applicant"
        and f.severity == FieldFindingSeverity.CRITICAL
        for f in v.findings)


def _test_app_negative_amount():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(amount=Decimal("-100"))
    v = eng.validate_lc_application(app)
    assert v.completeness == (
        ApplicationCompleteness.INVALID)
    assert any(
        f.field_name == "requested_amount_kes"
        and f.severity == FieldFindingSeverity.CRITICAL
        for f in v.findings)


def _test_app_amount_exceeds_policy():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(
        amount=Decimal("100000000000"))  # 100b, way above 10b
    v = eng.validate_lc_application(app)
    assert v.completeness != (
        ApplicationCompleteness.COMPLETE)
    assert any(
        f.severity == FieldFindingSeverity.HIGH
        for f in v.findings)


def _test_app_invalid_currency():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(currency="USDX")    # 4 chars
    v = eng.validate_lc_application(app)
    assert any(
        f.field_name == "currency"
        for f in v.findings)


def _test_app_expiry_before_shipment():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(
        expiry=date(2026, 7, 1),
        shipment=date(2026, 7, 15))  # after expiry
    v = eng.validate_lc_application(app)
    assert any(
        "shipment date after expiry" in f.description.lower()
        for f in v.findings)


def _test_app_expired_at_issuance():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(
        submission=date(2026, 7, 1),
        expiry=date(2026, 6, 30))    # expiry before submission
    v = eng.validate_lc_application(app)
    assert any(
        "expired at issuance" in f.description.lower()
        for f in v.findings)


def _test_app_missing_description():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application(desc="")
    v = eng.validate_lc_application(app)
    # MEDIUM severity — INCOMPLETE not INVALID
    assert v.completeness == (
        ApplicationCompleteness.INCOMPLETE)


# ─── Amendment classification tests ────────────────────────────

def _test_amendment_expiry_extension():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-1", lc_reference="LC-1",
        requested_at=date(2026, 5, 1),
        new_expiry_date=date(2026, 9, 1))
    c = eng.classify_amendment_request(amend)
    assert AmendmentType.EXPIRY_EXTENSION in c.detected_types
    assert c.impact == AmendmentImpact.LOW


def _test_amendment_amount_increase():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-2", lc_reference="LC-1",
        requested_at=date(2026, 5, 1),
        new_amount_kes=Decimal("2000000"))
    c = eng.classify_amendment_request(
        amend,
        existing_lc_amount_kes=Decimal("1000000"))
    assert AmendmentType.AMOUNT_INCREASE in c.detected_types
    assert c.impact == AmendmentImpact.HIGH
    assert "credit_committee" in c.required_approvals
    assert "limit_review" in c.required_approvals


def _test_amendment_amount_decrease():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-3", lc_reference="LC-1",
        requested_at=date(2026, 5, 1),
        new_amount_kes=Decimal("500000"))
    c = eng.classify_amendment_request(
        amend,
        existing_lc_amount_kes=Decimal("1000000"))
    assert AmendmentType.AMOUNT_DECREASE in c.detected_types
    assert c.impact == AmendmentImpact.LOW


def _test_amendment_beneficiary_change_high_impact():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-4", lc_reference="LC-1",
        requested_at=date(2026, 5, 1),
        new_beneficiary="OtherCo")
    c = eng.classify_amendment_request(amend)
    assert (
        AmendmentType.BENEFICIARY_CHANGE in c.detected_types)
    assert c.impact == AmendmentImpact.HIGH
    assert (
        "compliance_screening" in c.required_approvals)


def _test_amendment_withdraw():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-5", lc_reference="LC-1",
        requested_at=date(2026, 5, 1),
        withdraw=True)
    c = eng.classify_amendment_request(amend)
    assert AmendmentType.WITHDRAW in c.detected_types
    assert "rm_approval" in c.required_approvals


def _test_amendment_unknown_when_empty():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-6", lc_reference="LC-1",
        requested_at=date(2026, 5, 1))
    c = eng.classify_amendment_request(amend)
    assert c.primary_type == AmendmentType.UNKNOWN


def _test_amendment_multi_type_primary_is_most_impactful():
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-7", lc_reference="LC-1",
        requested_at=date(2026, 5, 1),
        new_amount_kes=Decimal("2000000"),    # increase
        new_expiry_date=date(2026, 12, 31))   # extension
    c = eng.classify_amendment_request(
        amend,
        existing_lc_amount_kes=Decimal("1000000"))
    assert (
        AmendmentType.AMOUNT_INCREASE in c.detected_types)
    assert (
        AmendmentType.EXPIRY_EXTENSION in c.detected_types)
    # Primary is the most-impactful (AMOUNT_INCREASE)
    assert c.primary_type == AmendmentType.AMOUNT_INCREASE


# ─── Status tracking tests ─────────────────────────────────────

def _test_status_active_lc():
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    eng = TradeFinanceCorporatePortalEngine()
    inst = TradeInstrument(
        instrument_id="LC-1",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.ACTIVE,
        applicant="A", beneficiary="B",
        issuing_bank="X", advising_bank="Y",
        amount_kes=Decimal("1000000"), currency="USD",
        issue_date=date(2026, 5, 1),
        expiry_date=date(2026, 8, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF",
        description_of_goods="test")
    snap = eng.track_instrument_status(
        inst, as_of=date(2026, 6, 1))
    # 2026-08-01 - 2026-06-01 = 61 days
    assert snap.days_until_expiry == 61
    assert snap.state == InstrumentState.ACTIVE
    assert len(snap.milestones) >= 4


# ─── Document upload validation tests ──────────────────────────

def _test_upload_accepted():
    eng = TradeFinanceCorporatePortalEngine()
    upload = DocumentUpload(
        upload_id="UP-1",
        filename="invoice.pdf",
        declared_document_type="COMMERCIAL_INVOICE",
        declared_size_bytes=500_000)
    r = eng.validate_document_upload(upload)
    assert r.outcome == DocumentValidationOutcome.ACCEPTED
    assert r.rejection_reasons == ()


def _test_upload_rejected_type():
    eng = TradeFinanceCorporatePortalEngine()
    upload = DocumentUpload(
        upload_id="UP-2",
        filename="malware.exe",
        declared_document_type="OTHER",
        declared_size_bytes=100)
    r = eng.validate_document_upload(upload)
    assert r.outcome == (
        DocumentValidationOutcome.REJECTED_TYPE)


def _test_upload_rejected_size():
    eng = TradeFinanceCorporatePortalEngine()
    upload = DocumentUpload(
        upload_id="UP-3",
        filename="huge.pdf",
        declared_document_type="OTHER",
        declared_size_bytes=100 * 1024 * 1024)   # 100MB > 10MB
    r = eng.validate_document_upload(upload)
    assert r.outcome == (
        DocumentValidationOutcome.REJECTED_SIZE)


def _test_upload_missing_metadata():
    eng = TradeFinanceCorporatePortalEngine()
    upload = DocumentUpload(
        upload_id="UP-4",
        filename="ok.pdf",
        declared_document_type="COMMERCIAL_INVOICE",
        declared_size_bytes=1000,
        raw_metadata={})
    r = eng.validate_document_upload(
        upload,
        required_metadata_keys=("uploader_id",))
    assert r.outcome == (
        DocumentValidationOutcome.REJECTED_METADATA)
    assert any(
        "uploader_id" in reason
        for reason in r.rejection_reasons)


# ─── Message routing tests ─────────────────────────────────────

def _test_routing_default_ops_queue():
    eng = TradeFinanceCorporatePortalEngine()
    msg = CorporateMessage(
        message_id="MSG-1", sender="acme",
        body="general status query")
    r = eng.classify_message_routing(msg, keyword_routing={})
    assert r.destination == (
        MessageRoutingDestination.OPS_QUEUE)
    assert r.matched_keywords == ()


def _test_routing_keyword_match_rm():
    eng = TradeFinanceCorporatePortalEngine()
    msg = CorporateMessage(
        message_id="MSG-2", sender="acme",
        body="want to discuss new credit facility limit")
    routing = {
        "credit": MessageRoutingDestination.RM_QUEUE,
        "facility": MessageRoutingDestination.RM_QUEUE}
    r = eng.classify_message_routing(msg, routing)
    assert r.destination == (
        MessageRoutingDestination.RM_QUEUE)
    assert len(r.matched_keywords) >= 1


def _test_routing_escalation_wins():
    """Multi-keyword match: escalation wins over rm wins
    over ops."""
    eng = TradeFinanceCorporatePortalEngine()
    msg = CorporateMessage(
        message_id="MSG-3", sender="acme",
        body="urgent fraud suspected — need credit team")
    routing = {
        "fraud": MessageRoutingDestination.ESCALATION_QUEUE,
        "credit": MessageRoutingDestination.RM_QUEUE}
    r = eng.classify_message_routing(msg, routing)
    assert r.destination == (
        MessageRoutingDestination.ESCALATION_QUEUE)


def _test_routing_word_boundary_no_substring_fp():
    """'card' must not match 'discarded' via substring."""
    eng = TradeFinanceCorporatePortalEngine()
    msg = CorporateMessage(
        message_id="MSG-4", sender="acme",
        body="all old documents discarded yesterday")
    routing = {
        "card": MessageRoutingDestination.RM_QUEUE}
    r = eng.classify_message_routing(msg, routing)
    # Must NOT match — no escalation
    assert r.destination == (
        MessageRoutingDestination.OPS_QUEUE)
    assert r.matched_keywords == ()


def _test_routing_short_keyword_floor():
    """Keywords shorter than 3 chars rejected silently."""
    eng = TradeFinanceCorporatePortalEngine()
    msg = CorporateMessage(
        message_id="MSG-5", sender="acme",
        body="we need help")
    routing = {
        "we": MessageRoutingDestination.RM_QUEUE,    # < 3 chars
        "help": MessageRoutingDestination.RM_QUEUE}
    r = eng.classify_message_routing(msg, routing)
    # 'we' silently dropped; only 'help' matches
    assert any(
        kw == "help" for kw, _ in r.matched_keywords)
    assert not any(
        kw == "we" for kw, _ in r.matched_keywords)


# ─── Discipline + provenance tests ─────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceCorporatePortalEngine()
    app = _make_application()
    eng.validate_lc_application(app)
    assert app.applicant == "Acme Imports"
    assert app.requested_amount_kes == Decimal("1000000")


def _test_full_provenance():
    eng = TradeFinanceCorporatePortalEngine()
    v = eng.validate_lc_application(_make_application())
    refs = " / ".join(v.framework_refs)
    assert "ENH-271" in refs
    assert "Rule 1" in refs
    assert "Rule 7" in refs


def self_test() -> None:
    tests = [
        _test_app_complete,
        _test_app_missing_applicant,
        _test_app_negative_amount,
        _test_app_amount_exceeds_policy,
        _test_app_invalid_currency,
        _test_app_expiry_before_shipment,
        _test_app_expired_at_issuance,
        _test_app_missing_description,
        _test_amendment_expiry_extension,
        _test_amendment_amount_increase,
        _test_amendment_amount_decrease,
        _test_amendment_beneficiary_change_high_impact,
        _test_amendment_withdraw,
        _test_amendment_unknown_when_empty,
        _test_amendment_multi_type_primary_is_most_impactful,
        _test_status_active_lc,
        _test_upload_accepted,
        _test_upload_rejected_type,
        _test_upload_rejected_size,
        _test_upload_missing_metadata,
        _test_routing_default_ops_queue,
        _test_routing_keyword_match_rm,
        _test_routing_escalation_wins,
        _test_routing_word_boundary_no_substring_fp,
        _test_routing_short_keyword_floor,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_corporate_portal self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_corporate_portal self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

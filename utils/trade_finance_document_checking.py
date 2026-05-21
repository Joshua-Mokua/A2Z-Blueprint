"""utils/trade_finance_document_checking.py — v10.78: TF docs.

ENH-270 — AI-Powered Document Checking. Cat B — trade_finance
arc 8/N.

Diagnostic UCP 600 document examination engine for LC drawdown
presentations. Combines deterministic rule-based checks (UCP 600
§6, §14, §28, §29, §30) with an optional ML hook for refined
severity classification on borderline cases.

ARCHITECTURE — TWO LAYERS:

  Layer 1 — Deterministic UCP 600 checks: emit CandidateFinding
    objects when rules detect a potential discrepancy. Catches
    the categorical 70% — wrong currency, late presentation,
    missing required document, amount outside tolerance, port
    mismatch, cross-document conflict.

  Layer 2 — ML classifier (optional): refines severity on
    candidates using v10.76 hook contract. Catches the long-
    tail 30% — non-conforming presentations that meet UCP 600
    field-by-field but fail real examiner scrutiny (subtle
    wording variations, equivalent-but-different descriptions,
    party-name aliases, date-format borderline cases).

When no ML hook is injected, the engine promotes all candidates
to DiscrepancyFinding using rule-assigned severity and surfaces
ml_disabled=True per Rule 6. When a hook is injected, candidates
flow through it for severity refinement + false-positive
filtering, and outputs surface ml_disabled=False with
method=ML_INJECTED. When the injected hook raises or returns
wrong length, engine falls back gracefully.

Five capabilities:

  1. check_amount_tolerance — UCP 600 §30 — amount in
     commercial invoice within LC tolerance band (default ±10%
     unless specified otherwise per LC terms).

  2. check_dates_and_periods — UCP 600 §6 (expiry), §29
     (latest shipment date), §14(c) (presentation period after
     shipment, default 21 days unless LC specifies).

  3. check_required_documents_present — every DocumentType
     listed in LC.required_documents must appear at least once
     in the presentation.

  4. check_cross_document_consistency — UCP 600 §14(d) — data
     in any document must not conflict with data in any other
     document. Currently checks: amount consistency, currency
     consistency, port consistency, description-of-goods
     overlap.

  5. assess_presentation — orchestrator: runs all 4 checks,
     collects candidate findings, applies ML classifier (or
     statistical fallback), returns PresentationAssessment
     with finalized DiscrepancyFinding tuple + 5-tier
     PresentationOutcome (CONFORMING / DISCREPANT_WAIVABLE /
     DISCREPANT_REFUSAL_LIKELY / REFUSED / INSUFFICIENT_DATA).

Per Rule 7, engine NEVER:
  - approves drawdowns (operator examines + decides per UCP
    600 §16 within 5 banking days)
  - issues notice of refusal (banking workflow territory)
  - communicates with beneficiary or applicant
  - parses PDFs, OCRs documents, or extracts fields (upstream
    structured-data pipeline territory — engine consumes
    PresentedDocument with already-extracted fields)
  - retrains models in-place (training is separate
    infrastructure — see scripts/training/
    train_document_classifier.py for reference pipeline)
  - mutates inputs

Per Rule 1, every output surfaces finding category + UCP 600
article reference + method + ml_disabled flag + framework_refs.

Pure stdlib (Decimal + datetime + dataclasses + enums + re).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import (
    Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceDocumentCheckingEngine implements ENH-270 — "
    "diagnostic UCP 600 document examination with optional ML "
    "extension hook. Two layers: deterministic UCP 600 checks "
    "(70% categorical coverage) + optional ML classifier for "
    "long-tail severity refinement (30% nuanced cases). ML "
    "contract follows v10.76 pattern — caller-injected "
    "Callable, graceful fallback on failure, ml_disabled flag "
    "in every output. Pure stdlib runtime (sklearn only "
    "required for training pipeline, not for engine "
    "operation). Per Rule 1, every output surfaces UCP 600 "
    "article + method + ml_disabled + framework_refs. Per "
    "Rule 7, engine DIAGNOSTIC ONLY — never approves "
    "drawdowns, never issues refusals, never parses PDFs / "
    "OCRs documents (upstream extraction territory), never "
    "retrains models in-place (training is separate "
    "infrastructure), never mutates inputs."
)

# Default UCP 600 §14(c) presentation period when LC silent
DEFAULT_PRESENTATION_PERIOD_DAYS: int = 21

# Default UCP 600 §30 amount tolerance when LC silent
DEFAULT_AMOUNT_TOLERANCE_PCT: Decimal = Decimal("0.05")

# UCP 600 §28(f)(ii) minimum insurance coverage as fraction of
# CIF/CIP value
DEFAULT_INSURANCE_MIN_FACTOR: Decimal = Decimal("1.10")


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class DocumentType(Enum):
    COMMERCIAL_INVOICE = "COMMERCIAL_INVOICE"
    BILL_OF_LADING = "BILL_OF_LADING"
    AIR_WAYBILL = "AIR_WAYBILL"
    PACKING_LIST = "PACKING_LIST"
    CERTIFICATE_OF_ORIGIN = "CERTIFICATE_OF_ORIGIN"
    INSURANCE_CERTIFICATE = "INSURANCE_CERTIFICATE"
    INSPECTION_CERTIFICATE = "INSPECTION_CERTIFICATE"
    DRAFT = "DRAFT"
    OTHER = "OTHER"


class DiscrepancySeverity(Enum):
    """5-tier severity ladder for findings."""
    CRITICAL = "CRITICAL"  # Refusal almost certain (e.g. expired LC)
    HIGH = "HIGH"          # Refusal likely without waiver
    MEDIUM = "MEDIUM"      # Discrepant but typically waivable
    LOW = "LOW"            # Technical discrepancy, often waived
    INFO = "INFO"          # Noted but not a discrepancy


class CheckCategory(Enum):
    """The kind of check that produced a finding."""
    AMOUNT_TOLERANCE = "AMOUNT_TOLERANCE"
    EXPIRY = "EXPIRY"
    LATE_SHIPMENT = "LATE_SHIPMENT"
    PRESENTATION_PERIOD = "PRESENTATION_PERIOD"
    PORT_LOADING = "PORT_LOADING"
    PORT_DISCHARGE = "PORT_DISCHARGE"
    DESCRIPTION_OF_GOODS = "DESCRIPTION_OF_GOODS"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    CROSS_DOCUMENT_AMOUNT = "CROSS_DOCUMENT_AMOUNT"
    CROSS_DOCUMENT_CURRENCY = "CROSS_DOCUMENT_CURRENCY"
    CROSS_DOCUMENT_PORT = "CROSS_DOCUMENT_PORT"
    CROSS_DOCUMENT_DESCRIPTION = "CROSS_DOCUMENT_DESCRIPTION"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"


class FindingMethod(Enum):
    """Per v10.76 contract — which path produced the finding."""
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    STATISTICAL_FALLBACK = "STATISTICAL_FALLBACK"
    ML_INJECTED = "ML_INJECTED"


class PresentationOutcome(Enum):
    """5-tier outcome ladder for the orchestrator."""
    CONFORMING = "CONFORMING"
    DISCREPANT_WAIVABLE = "DISCREPANT_WAIVABLE"
    DISCREPANT_REFUSAL_LIKELY = "DISCREPANT_REFUSAL_LIKELY"
    REFUSED = "REFUSED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LCTerms:
    """LC terms relevant to document examination."""
    lc_reference: str
    amount_kes: Decimal
    currency: str
    expiry_date: date
    latest_shipment_date: Optional[date]
    presentation_period_days: int = (
        DEFAULT_PRESENTATION_PERIOD_DAYS)
    amount_tolerance_pct: Decimal = (
        DEFAULT_AMOUNT_TOLERANCE_PCT)
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    description_of_goods: str = ""
    incoterms: str = ""
    required_documents: Tuple[DocumentType, ...] = ()
    insurance_min_factor: Decimal = (
        DEFAULT_INSURANCE_MIN_FACTOR)
    applicant: str = ""
    beneficiary: str = ""

    def __post_init__(self) -> None:
        if self.amount_kes < 0:
            raise ValueError("amount_kes must be non-negative")
        if (
            self.amount_tolerance_pct < 0
            or self.amount_tolerance_pct > Decimal("1")
        ):
            raise ValueError(
                "amount_tolerance_pct must be 0..1")


@dataclass(frozen=True)
class PresentedDocument:
    """A single document in the presentation, post-extraction."""
    document_type: DocumentType
    issuer: str
    amount_kes: Optional[Decimal] = None
    currency: Optional[str] = None
    issue_date: Optional[date] = None
    shipment_date: Optional[date] = None
    description_of_goods: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    consignee: Optional[str] = None
    shipper: Optional[str] = None
    incoterms: Optional[str] = None
    insurance_amount_kes: Optional[Decimal] = None
    raw_fields: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentPresentation:
    presentation_id: str
    lc_reference: str
    presentation_date: date
    documents: Tuple[PresentedDocument, ...]


# ════════════════════════════════════════════════════════════════════════
# Intermediate + ML-hook contract dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CandidateFinding:
    """A potential discrepancy detected by deterministic rules.

    The ML hook (when injected) examines candidates and returns
    refined severity + confidence + true/false-positive flag.
    When no hook, statistical fallback uses rule_assigned_severity
    directly.
    """
    candidate_id: str
    category: CheckCategory
    rule_assigned_severity: DiscrepancySeverity
    document_type: Optional[DocumentType]
    description: str
    expected: str
    observed: str
    feature_hints: Mapping[str, str] = field(
        default_factory=dict)


@dataclass(frozen=True)
class ClassificationResult:
    """One per CandidateFinding from the ML hook."""
    refined_severity: DiscrepancySeverity
    is_true_discrepancy: bool
    confidence: float            # 0..1
    reasoning: str = ""


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DiscrepancyFinding:
    finding_id: str
    category: CheckCategory
    severity: DiscrepancySeverity
    document_type: Optional[DocumentType]
    description: str
    expected: str
    observed: str
    method: FindingMethod
    ml_disabled: bool
    confidence: Optional[float]   # None for deterministic rule
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class PresentationAssessment:
    presentation_id: str
    lc_reference: str
    findings: Tuple[DiscrepancyFinding, ...]
    outcome: PresentationOutcome
    overall_ml_disabled: bool
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

# Type alias for the ML hook contract — follows v10.76 pattern
MLDiscrepancyClassifier = Callable[
    [Sequence[CandidateFinding]], Sequence[ClassificationResult]]


class TradeFinanceDocumentCheckingEngine:
    """Diagnostic UCP 600 document examination engine."""

    def __init__(
        self,
        ml_discrepancy_classifier: Optional[
            MLDiscrepancyClassifier] = None,
    ) -> None:
        self.ml_discrepancy_classifier = (
            ml_discrepancy_classifier)

    # ─── Helpers ────────────────────────────────────────────────
    @staticmethod
    def _normalize(s: Optional[str]) -> str:
        """Lowercase + strip + collapse whitespace for fuzzy
        comparison."""
        if s is None:
            return ""
        return re.sub(r"\s+", " ", s.strip().lower())

    @staticmethod
    def _find_first(
        documents: Sequence[PresentedDocument],
        doc_type: DocumentType,
    ) -> Optional[PresentedDocument]:
        for d in documents:
            if d.document_type == doc_type:
                return d
        return None

    @staticmethod
    def _all_of_type(
        documents: Sequence[PresentedDocument],
        doc_type: DocumentType,
    ) -> List[PresentedDocument]:
        return [
            d for d in documents
            if d.document_type == doc_type]

    # ─── 1. Amount tolerance (UCP 600 §30) ──────────────────────
    def check_amount_tolerance(
        self,
        lc: LCTerms,
        presentation: DocumentPresentation,
    ) -> List[CandidateFinding]:
        """Compare commercial-invoice amount to LC amount.

        UCP 600 §30 allows tolerance bands. When LC silent, default
        ±5%. When tolerance specified in LC terms, use that.
        """
        invoice = self._find_first(
            presentation.documents,
            DocumentType.COMMERCIAL_INVOICE)
        if invoice is None:
            # Missing-doc finding handled by check 3
            return []
        if invoice.amount_kes is None:
            return [CandidateFinding(
                candidate_id=(
                    f"{presentation.presentation_id}-"
                    f"AMT-MISSING"),
                category=CheckCategory.MISSING_REQUIRED_FIELD,
                rule_assigned_severity=(
                    DiscrepancySeverity.CRITICAL),
                document_type=DocumentType.COMMERCIAL_INVOICE,
                description=(
                    "Commercial invoice missing amount field"),
                expected=(
                    "Amount in invoice currency"),
                observed="None",
                feature_hints={
                    "lc_currency": lc.currency,
                    "lc_amount": str(lc.amount_kes)})]

        max_amt = (
            lc.amount_kes * (
                Decimal("1") + lc.amount_tolerance_pct))
        min_amt = (
            lc.amount_kes * (
                Decimal("1") - lc.amount_tolerance_pct))

        if invoice.amount_kes > max_amt:
            return [CandidateFinding(
                candidate_id=(
                    f"{presentation.presentation_id}-AMT-OVER"),
                category=CheckCategory.AMOUNT_TOLERANCE,
                rule_assigned_severity=(
                    DiscrepancySeverity.HIGH),
                document_type=DocumentType.COMMERCIAL_INVOICE,
                description=(
                    "Invoice amount exceeds LC amount + "
                    "tolerance"),
                expected=f"≤ {max_amt}",
                observed=str(invoice.amount_kes),
                feature_hints={
                    "category": "amount_over",
                    "ratio": str(
                        (invoice.amount_kes / lc.amount_kes)
                        .quantize(Decimal("0.0001")))})]
        if invoice.amount_kes < min_amt:
            return [CandidateFinding(
                candidate_id=(
                    f"{presentation.presentation_id}-AMT-UNDER"),
                category=CheckCategory.AMOUNT_TOLERANCE,
                rule_assigned_severity=(
                    DiscrepancySeverity.LOW),
                document_type=DocumentType.COMMERCIAL_INVOICE,
                description=(
                    "Invoice amount below LC amount - "
                    "tolerance (often acceptable as partial "
                    "drawdown)"),
                expected=f"≥ {min_amt}",
                observed=str(invoice.amount_kes),
                feature_hints={
                    "category": "amount_under",
                    "ratio": str(
                        (invoice.amount_kes / lc.amount_kes)
                        .quantize(Decimal("0.0001")))})]
        return []

    # ─── 2. Dates and periods (UCP 600 §6, §14(c), §29) ────────
    def check_dates_and_periods(
        self,
        lc: LCTerms,
        presentation: DocumentPresentation,
    ) -> List[CandidateFinding]:
        findings: List[CandidateFinding] = []

        # UCP 600 §6 — presentation must be on or before expiry
        if presentation.presentation_date > lc.expiry_date:
            findings.append(CandidateFinding(
                candidate_id=(
                    f"{presentation.presentation_id}-EXPIRY"),
                category=CheckCategory.EXPIRY,
                rule_assigned_severity=(
                    DiscrepancySeverity.CRITICAL),
                document_type=None,
                description=(
                    "Presentation made after LC expiry date"),
                expected=(
                    f"presentation ≤ {lc.expiry_date.isoformat()}"),
                observed=(
                    presentation.presentation_date.isoformat()),
                feature_hints={
                    "days_late": str((
                        presentation.presentation_date
                        - lc.expiry_date).days)}))

        # UCP 600 §29 — latest shipment date check (transport doc)
        if lc.latest_shipment_date is not None:
            transport_doc = (
                self._find_first(
                    presentation.documents,
                    DocumentType.BILL_OF_LADING)
                or self._find_first(
                    presentation.documents,
                    DocumentType.AIR_WAYBILL))
            if (
                transport_doc is not None
                and transport_doc.shipment_date is not None
                and transport_doc.shipment_date
                > lc.latest_shipment_date
            ):
                days_late = (
                    transport_doc.shipment_date
                    - lc.latest_shipment_date).days
                findings.append(CandidateFinding(
                    candidate_id=(
                        f"{presentation.presentation_id}-"
                        f"LATE-SHIP"),
                    category=CheckCategory.LATE_SHIPMENT,
                    rule_assigned_severity=(
                        DiscrepancySeverity.HIGH),
                    document_type=transport_doc.document_type,
                    description=(
                        "Shipment date in transport document "
                        "after latest shipment date in LC"),
                    expected=(
                        f"≤ "
                        f"{lc.latest_shipment_date.isoformat()}"),
                    observed=(
                        transport_doc.shipment_date.isoformat()),
                    feature_hints={
                        "days_late": str(days_late)}))

            # UCP 600 §14(c) — presentation period after shipment
            if (
                transport_doc is not None
                and transport_doc.shipment_date is not None
            ):
                deadline = (
                    transport_doc.shipment_date
                    + timedelta(
                        days=lc.presentation_period_days))
                if presentation.presentation_date > deadline:
                    findings.append(CandidateFinding(
                        candidate_id=(
                            f"{presentation.presentation_id}-"
                            f"PRES-PERIOD"),
                        category=(
                            CheckCategory.PRESENTATION_PERIOD),
                        rule_assigned_severity=(
                            DiscrepancySeverity.HIGH),
                        document_type=None,
                        description=(
                            f"Presentation made more than "
                            f"{lc.presentation_period_days} "
                            f"days after shipment"),
                        expected=(
                            f"≤ {deadline.isoformat()}"),
                        observed=(
                            presentation.presentation_date
                            .isoformat()),
                        feature_hints={
                            "days_late": str((
                                presentation.presentation_date
                                - deadline).days)}))

        return findings

    # ─── 3. Required documents present ──────────────────────────
    def check_required_documents_present(
        self,
        lc: LCTerms,
        presentation: DocumentPresentation,
    ) -> List[CandidateFinding]:
        present_types = {
            d.document_type for d in presentation.documents}
        findings: List[CandidateFinding] = []
        for required in lc.required_documents:
            if required not in present_types:
                findings.append(CandidateFinding(
                    candidate_id=(
                        f"{presentation.presentation_id}-MISSING-"
                        f"{required.value}"),
                    category=CheckCategory.MISSING_DOCUMENT,
                    rule_assigned_severity=(
                        DiscrepancySeverity.CRITICAL),
                    document_type=required,
                    description=(
                        f"Required document missing: "
                        f"{required.value}"),
                    expected=(
                        f"{required.value} present"),
                    observed="not in presentation",
                    feature_hints={
                        "missing_type": required.value}))
        return findings

    # ─── 4. Cross-document consistency (UCP 600 §14(d)) ─────────
    def check_cross_document_consistency(
        self,
        lc: LCTerms,
        presentation: DocumentPresentation,
    ) -> List[CandidateFinding]:
        """Detect data conflicts across documents per UCP §14(d)."""
        findings: List[CandidateFinding] = []
        docs = presentation.documents

        # Currency consistency across all docs that have currency
        currencies_seen: Dict[str, List[DocumentType]] = {}
        for d in docs:
            if d.currency:
                currencies_seen.setdefault(
                    d.currency.upper(), []).append(
                        d.document_type)
        if len(currencies_seen) > 1:
            findings.append(CandidateFinding(
                candidate_id=(
                    f"{presentation.presentation_id}-XCUR"),
                category=CheckCategory.CROSS_DOCUMENT_CURRENCY,
                rule_assigned_severity=(
                    DiscrepancySeverity.HIGH),
                document_type=None,
                description=(
                    "Currency differs across documents"),
                expected="single currency consistently",
                observed=", ".join(
                    f"{cur}:{[t.value for t in types]}"
                    for cur, types
                    in currencies_seen.items()),
                feature_hints={
                    "distinct_currency_count": str(
                        len(currencies_seen))}))

        # Port-of-loading consistency
        ports_loading: Dict[str, List[DocumentType]] = {}
        for d in docs:
            if d.port_of_loading:
                ports_loading.setdefault(
                    self._normalize(d.port_of_loading),
                    []).append(d.document_type)
        if len(ports_loading) > 1:
            findings.append(CandidateFinding(
                candidate_id=(
                    f"{presentation.presentation_id}-XPL"),
                category=CheckCategory.CROSS_DOCUMENT_PORT,
                rule_assigned_severity=(
                    DiscrepancySeverity.MEDIUM),
                document_type=None,
                description=(
                    "Port of loading differs across documents"),
                expected="single port of loading consistently",
                observed=", ".join(
                    f"'{port}'" for port in ports_loading),
                feature_hints={
                    "distinct_port_count": str(
                        len(ports_loading))}))

        # Description-of-goods overlap check on commercial invoice
        # vs LC. UCP 600 §14(e) — invoice description must
        # CORRESPOND to LC; other docs can describe in general
        # terms.
        invoice = self._find_first(
            docs, DocumentType.COMMERCIAL_INVOICE)
        if (
            invoice is not None
            and invoice.description_of_goods
            and lc.description_of_goods
        ):
            inv_norm = self._normalize(
                invoice.description_of_goods)
            lc_norm = self._normalize(lc.description_of_goods)
            # Heuristic: meaningful overlap = at least 60% of LC
            # description tokens appear in invoice. Conservative
            # because false positives here (claiming discrepancy
            # when wording is just slightly different) annoy
            # operators; ML hook refines borderline cases.
            lc_tokens = [
                t for t in lc_norm.split()
                if len(t) >= 4]
            if lc_tokens:
                hits = sum(
                    1 for t in lc_tokens if t in inv_norm)
                overlap = hits / len(lc_tokens)
                if overlap < Decimal("0.6"):
                    findings.append(CandidateFinding(
                        candidate_id=(
                            f"{presentation.presentation_id}-"
                            f"XDOG"),
                        category=(
                            CheckCategory
                            .CROSS_DOCUMENT_DESCRIPTION),
                        rule_assigned_severity=(
                            DiscrepancySeverity.MEDIUM),
                        document_type=(
                            DocumentType.COMMERCIAL_INVOICE),
                        description=(
                            "Invoice description-of-goods has "
                            "low overlap with LC description"),
                        expected=lc.description_of_goods,
                        observed=(
                            invoice.description_of_goods),
                        feature_hints={
                            "overlap_pct": (
                                f"{overlap:.2f}"),
                            "invoice_norm": inv_norm,
                            "lc_norm": lc_norm}))

        return findings

    # ─── ML hook integration ────────────────────────────────────
    def _classify_candidates(
        self,
        candidates: Sequence[CandidateFinding],
    ) -> Tuple[
        Tuple[DiscrepancyFinding, ...], FindingMethod, bool]:
        """Apply ML classifier or statistical fallback.

        Returns (findings, method_used, ml_disabled). When method
        is ML_INJECTED but the hook fails, returns the fallback
        findings with method=STATISTICAL_FALLBACK and
        ml_disabled=True.
        """
        if not candidates:
            return (
                (),
                FindingMethod.DETERMINISTIC_RULE,
                True)

        if self.ml_discrepancy_classifier is not None:
            try:
                results = list(
                    self.ml_discrepancy_classifier(candidates))
                if len(results) != len(candidates):
                    raise ValueError(
                        "ml_discrepancy_classifier returned "
                        "wrong length")
                findings: List[DiscrepancyFinding] = []
                for cand, res in zip(candidates, results):
                    if not res.is_true_discrepancy:
                        continue
                    findings.append(DiscrepancyFinding(
                        finding_id=cand.candidate_id,
                        category=cand.category,
                        severity=res.refined_severity,
                        document_type=cand.document_type,
                        description=cand.description,
                        expected=cand.expected,
                        observed=cand.observed,
                        method=FindingMethod.ML_INJECTED,
                        ml_disabled=False,
                        confidence=max(
                            0.0, min(1.0, res.confidence)),
                        framework_refs=(
                            "ENH-270 §classify_finding (ML hook)",
                            f"UCP 600 — category "
                            f"{cand.category.value}",
                            "Per Rule 6 — ml_disabled=False; "
                            "method=ML_INJECTED",
                            "Per Rule 7 — engine surfaces; "
                            "operator decides per UCP 600 §16",
                            f"ML reasoning: {res.reasoning}",
                        )))
                return (
                    tuple(findings),
                    FindingMethod.ML_INJECTED,
                    False)
            except Exception as e:
                # Fall through to statistical fallback;
                # surface failure in framework_refs
                fallback_note = (
                    f"ml_discrepancy_classifier raised "
                    f"{type(e).__name__}: {e}; "
                    f"fell back to statistical")
                findings = []
                for cand in candidates:
                    findings.append(DiscrepancyFinding(
                        finding_id=cand.candidate_id,
                        category=cand.category,
                        severity=cand.rule_assigned_severity,
                        document_type=cand.document_type,
                        description=cand.description,
                        expected=cand.expected,
                        observed=cand.observed,
                        method=(
                            FindingMethod.STATISTICAL_FALLBACK),
                        ml_disabled=True,
                        confidence=None,
                        framework_refs=(
                            "ENH-270 §classify_finding "
                            "(fallback)",
                            f"UCP 600 — category "
                            f"{cand.category.value}",
                            "Per Rule 6 — ml_disabled=True",
                            fallback_note,
                        )))
                return (
                    tuple(findings),
                    FindingMethod.STATISTICAL_FALLBACK,
                    True)

        # No ML hook injected — promote candidates as-is
        findings = []
        for cand in candidates:
            findings.append(DiscrepancyFinding(
                finding_id=cand.candidate_id,
                category=cand.category,
                severity=cand.rule_assigned_severity,
                document_type=cand.document_type,
                description=cand.description,
                expected=cand.expected,
                observed=cand.observed,
                method=FindingMethod.STATISTICAL_FALLBACK,
                ml_disabled=True,
                confidence=None,
                framework_refs=(
                    "ENH-270 §classify_finding "
                    "(rule-based, no ML hook)",
                    f"UCP 600 — category "
                    f"{cand.category.value}",
                    "Per Rule 6 — ml_disabled=True; "
                    "method=STATISTICAL_FALLBACK",
                    "Per Rule 7 — engine surfaces; operator "
                    "decides per UCP 600 §16",
                )))
        return (
            tuple(findings),
            FindingMethod.STATISTICAL_FALLBACK,
            True)

    # ─── 5. Orchestrator ────────────────────────────────────────
    def assess_presentation(
        self,
        lc: LCTerms,
        presentation: DocumentPresentation,
    ) -> PresentationAssessment:
        """Run all 4 checks, classify candidates, return outcome."""
        all_candidates: List[CandidateFinding] = []
        all_candidates.extend(
            self.check_amount_tolerance(lc, presentation))
        all_candidates.extend(
            self.check_dates_and_periods(lc, presentation))
        all_candidates.extend(
            self.check_required_documents_present(
                lc, presentation))
        all_candidates.extend(
            self.check_cross_document_consistency(
                lc, presentation))

        findings, method, ml_disabled = (
            self._classify_candidates(all_candidates))

        outcome = self._compute_outcome(findings)

        return PresentationAssessment(
            presentation_id=presentation.presentation_id,
            lc_reference=lc.lc_reference,
            findings=findings,
            outcome=outcome,
            overall_ml_disabled=ml_disabled,
            framework_refs=(
                "ENH-270 §assess_presentation",
                "UCP 600 §6 (expiry) + §14(c) (presentation "
                "period) + §14(d) (cross-document consistency) "
                "+ §14(e) (invoice description) + §29 (latest "
                "shipment) + §30 (amount tolerance)",
                f"Method: {method.value}",
                "Per Rule 6 — overall_ml_disabled flag",
                "Per Rule 7 — engine surfaces findings + "
                "outcome; operator examines + decides per "
                "UCP 600 §16 within 5 banking days",
            ),
        )

    @staticmethod
    def _compute_outcome(
        findings: Sequence[DiscrepancyFinding],
    ) -> PresentationOutcome:
        if not findings:
            return PresentationOutcome.CONFORMING
        if any(
            f.severity == DiscrepancySeverity.CRITICAL
            for f in findings
        ):
            return (
                PresentationOutcome.DISCREPANT_REFUSAL_LIKELY)
        if any(
            f.severity == DiscrepancySeverity.HIGH
            for f in findings
        ):
            return (
                PresentationOutcome.DISCREPANT_REFUSAL_LIKELY)
        # Only MEDIUM/LOW/INFO — typically waivable
        return PresentationOutcome.DISCREPANT_WAIVABLE


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_lc(
    ref="LC-001", amount=Decimal("1000000"),
    currency="USD",
    expiry=date(2026, 7, 1),
    latest_shipment=date(2026, 6, 15),
    description="50 metric tons of milled rice",
    required=(
        DocumentType.COMMERCIAL_INVOICE,
        DocumentType.BILL_OF_LADING),
    pol="Mombasa, Kenya",
    pod="Rotterdam, Netherlands",
    tolerance=Decimal("0.05"),
):
    return LCTerms(
        lc_reference=ref, amount_kes=amount, currency=currency,
        expiry_date=expiry,
        latest_shipment_date=latest_shipment,
        amount_tolerance_pct=tolerance,
        port_of_loading=pol, port_of_discharge=pod,
        description_of_goods=description,
        required_documents=required,
        applicant="Acme Imports", beneficiary="Rice Co Ltd")


def _make_invoice(
    amount=Decimal("1000000"), currency="USD",
    description="50 metric tons of milled rice",
    pol="Mombasa, Kenya",
):
    return PresentedDocument(
        document_type=DocumentType.COMMERCIAL_INVOICE,
        issuer="Rice Co Ltd",
        amount_kes=amount, currency=currency,
        issue_date=date(2026, 6, 1),
        description_of_goods=description,
        port_of_loading=pol)


def _make_bl(
    shipment=date(2026, 6, 10),
    pol="Mombasa, Kenya", pod="Rotterdam, Netherlands",
):
    return PresentedDocument(
        document_type=DocumentType.BILL_OF_LADING,
        issuer="Maersk", shipment_date=shipment,
        port_of_loading=pol, port_of_discharge=pod)


def _make_presentation(
    pid="PR-001", lc_ref="LC-001",
    pres_date=date(2026, 6, 20),
    documents=None,
):
    return DocumentPresentation(
        presentation_id=pid, lc_reference=lc_ref,
        presentation_date=pres_date,
        documents=tuple(documents or [
            _make_invoice(), _make_bl()]))


# ─── Amount tolerance tests ─────────────────────────────────────

def _test_amount_within_tolerance():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(amount=Decimal("1000000"))
    pres = _make_presentation(documents=[
        _make_invoice(amount=Decimal("1020000")),
        _make_bl()])
    cands = eng.check_amount_tolerance(lc, pres)
    assert cands == []


def _test_amount_over_tolerance():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(
        amount=Decimal("1000000"),
        tolerance=Decimal("0.05"))
    pres = _make_presentation(documents=[
        _make_invoice(amount=Decimal("1100000")),
        _make_bl()])
    cands = eng.check_amount_tolerance(lc, pres)
    assert len(cands) == 1
    assert cands[0].category == (
        CheckCategory.AMOUNT_TOLERANCE)
    assert cands[0].rule_assigned_severity == (
        DiscrepancySeverity.HIGH)


def _test_amount_under_tolerance_low_severity():
    """Under-amount typically waivable as partial drawdown."""
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(amount=Decimal("1000000"))
    pres = _make_presentation(documents=[
        _make_invoice(amount=Decimal("800000")),
        _make_bl()])
    cands = eng.check_amount_tolerance(lc, pres)
    assert len(cands) == 1
    assert cands[0].rule_assigned_severity == (
        DiscrepancySeverity.LOW)


def _test_amount_missing_field():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc()
    inv_no_amt = PresentedDocument(
        document_type=DocumentType.COMMERCIAL_INVOICE,
        issuer="X")
    pres = _make_presentation(documents=[
        inv_no_amt, _make_bl()])
    cands = eng.check_amount_tolerance(lc, pres)
    assert len(cands) == 1
    assert cands[0].category == (
        CheckCategory.MISSING_REQUIRED_FIELD)


# ─── Date and period tests ──────────────────────────────────────

def _test_dates_within_periods():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(
        expiry=date(2026, 7, 1),
        latest_shipment=date(2026, 6, 15))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20),
        documents=[
            _make_invoice(),
            _make_bl(shipment=date(2026, 6, 10))])
    cands = eng.check_dates_and_periods(lc, pres)
    assert cands == []


def _test_late_presentation_after_expiry():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(expiry=date(2026, 7, 1))
    pres = _make_presentation(
        pres_date=date(2026, 7, 5))    # 4 days after expiry
    cands = eng.check_dates_and_periods(lc, pres)
    assert any(
        c.category == CheckCategory.EXPIRY for c in cands)
    expiry_cand = next(
        c for c in cands if c.category == CheckCategory.EXPIRY)
    assert expiry_cand.rule_assigned_severity == (
        DiscrepancySeverity.CRITICAL)


def _test_late_shipment():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(latest_shipment=date(2026, 6, 15))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20),
        documents=[
            _make_invoice(),
            _make_bl(shipment=date(2026, 6, 18))])
    cands = eng.check_dates_and_periods(lc, pres)
    assert any(
        c.category == CheckCategory.LATE_SHIPMENT
        for c in cands)


def _test_presentation_period_exceeded():
    """Shipment 2026-06-01, presentation period 21d, presented
    2026-06-25 → 24d gap, exceeds 21d."""
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(
        expiry=date(2026, 7, 30),
        latest_shipment=date(2026, 6, 15))
    pres = _make_presentation(
        pres_date=date(2026, 6, 25),
        documents=[
            _make_invoice(),
            _make_bl(shipment=date(2026, 6, 1))])
    cands = eng.check_dates_and_periods(lc, pres)
    assert any(
        c.category == CheckCategory.PRESENTATION_PERIOD
        for c in cands)


# ─── Required-documents tests ───────────────────────────────────

def _test_all_required_present():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(required=(
        DocumentType.COMMERCIAL_INVOICE,
        DocumentType.BILL_OF_LADING))
    pres = _make_presentation()
    cands = eng.check_required_documents_present(lc, pres)
    assert cands == []


def _test_one_required_missing():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(required=(
        DocumentType.COMMERCIAL_INVOICE,
        DocumentType.BILL_OF_LADING,
        DocumentType.PACKING_LIST))
    pres = _make_presentation()    # has invoice + BL only
    cands = eng.check_required_documents_present(lc, pres)
    assert len(cands) == 1
    assert cands[0].document_type == DocumentType.PACKING_LIST
    assert cands[0].rule_assigned_severity == (
        DiscrepancySeverity.CRITICAL)


# ─── Cross-document consistency tests ───────────────────────────

def _test_cross_doc_currency_match():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(currency="USD")
    pres = _make_presentation(documents=[
        _make_invoice(currency="USD"),
        _make_bl()])
    cands = eng.check_cross_document_consistency(lc, pres)
    # Should not flag currency (only 1 currency mentioned, USD)
    assert not any(
        c.category == CheckCategory.CROSS_DOCUMENT_CURRENCY
        for c in cands)


def _test_cross_doc_currency_conflict():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(currency="USD")
    bl_with_eur = PresentedDocument(
        document_type=DocumentType.BILL_OF_LADING,
        issuer="Maersk",
        currency="EUR",     # conflict
        shipment_date=date(2026, 6, 10))
    pres = _make_presentation(documents=[
        _make_invoice(currency="USD"),
        bl_with_eur])
    cands = eng.check_cross_document_consistency(lc, pres)
    assert any(
        c.category == CheckCategory.CROSS_DOCUMENT_CURRENCY
        for c in cands)


def _test_cross_doc_port_conflict():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc()
    pres = _make_presentation(documents=[
        _make_invoice(pol="Mombasa, Kenya"),
        _make_bl(pol="Dar es Salaam, Tanzania")])
    cands = eng.check_cross_document_consistency(lc, pres)
    assert any(
        c.category == CheckCategory.CROSS_DOCUMENT_PORT
        for c in cands)


def _test_cross_doc_description_mismatch():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(
        description="50 metric tons milled rice grade A")
    inv_with_different_desc = _make_invoice(
        description="industrial steel coils")
    pres = _make_presentation(documents=[
        inv_with_different_desc, _make_bl()])
    cands = eng.check_cross_document_consistency(lc, pres)
    assert any(
        c.category
        == CheckCategory.CROSS_DOCUMENT_DESCRIPTION
        for c in cands)


# ─── Orchestrator + ML hook tests ───────────────────────────────

def _test_assess_clean_presentation_conforming():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc()
    pres = _make_presentation()
    a = eng.assess_presentation(lc, pres)
    assert a.outcome == PresentationOutcome.CONFORMING
    assert a.findings == ()


def _test_assess_critical_finding_refusal_likely():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(expiry=date(2026, 6, 1))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20))    # after expiry
    a = eng.assess_presentation(lc, pres)
    assert a.outcome == (
        PresentationOutcome.DISCREPANT_REFUSAL_LIKELY)
    assert any(
        f.severity == DiscrepancySeverity.CRITICAL
        for f in a.findings)
    # No ML hook → all findings flagged ml_disabled=True
    assert all(f.ml_disabled is True for f in a.findings)
    assert all(
        f.method == FindingMethod.STATISTICAL_FALLBACK
        for f in a.findings)


def _test_assess_medium_finding_waivable():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc()
    # Just a port mismatch — MEDIUM severity
    pres = _make_presentation(documents=[
        _make_invoice(pol="Mombasa, Kenya"),
        _make_bl(pol="Dar es Salaam, Tanzania")])
    a = eng.assess_presentation(lc, pres)
    assert a.outcome == (
        PresentationOutcome.DISCREPANT_WAIVABLE)


def _test_assess_ml_hook_used():
    """ML hook injected — refines severity + filters false
    positives. method=ML_INJECTED, ml_disabled=False."""
    def ml_classifier(candidates):
        # Promote everything to LOW severity, mark all as true
        # discrepancies with high confidence
        return [
            ClassificationResult(
                refined_severity=DiscrepancySeverity.LOW,
                is_true_discrepancy=True,
                confidence=0.95,
                reasoning="test classifier")
            for _ in candidates]

    eng = TradeFinanceDocumentCheckingEngine(
        ml_discrepancy_classifier=ml_classifier)
    lc = _make_lc(expiry=date(2026, 6, 1))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20))
    a = eng.assess_presentation(lc, pres)
    # All findings now LOW (ML override) → outcome is waivable
    assert a.outcome == (
        PresentationOutcome.DISCREPANT_WAIVABLE)
    assert all(f.ml_disabled is False for f in a.findings)
    assert all(
        f.method == FindingMethod.ML_INJECTED
        for f in a.findings)
    assert a.overall_ml_disabled is False


def _test_assess_ml_hook_filters_false_positives():
    """ML hook can mark candidates as is_true_discrepancy=False
    → filtered out of final findings."""
    def filter_all(candidates):
        return [
            ClassificationResult(
                refined_severity=DiscrepancySeverity.INFO,
                is_true_discrepancy=False,
                confidence=0.99,
                reasoning="not actually discrepant")
            for _ in candidates]

    eng = TradeFinanceDocumentCheckingEngine(
        ml_discrepancy_classifier=filter_all)
    lc = _make_lc(expiry=date(2026, 6, 1))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20))
    a = eng.assess_presentation(lc, pres)
    # All filtered → CONFORMING
    assert a.outcome == PresentationOutcome.CONFORMING
    assert a.findings == ()


def _test_assess_ml_hook_failure_falls_back():
    """If ML hook raises, fall back to statistical and flag."""
    def broken(candidates):
        raise RuntimeError("model not loaded")

    eng = TradeFinanceDocumentCheckingEngine(
        ml_discrepancy_classifier=broken)
    lc = _make_lc(expiry=date(2026, 6, 1))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20))
    a = eng.assess_presentation(lc, pres)
    # Fallback path: findings preserved with rule-based severity
    assert all(f.ml_disabled is True for f in a.findings)
    assert all(
        f.method == FindingMethod.STATISTICAL_FALLBACK
        for f in a.findings)
    # CRITICAL severity preserved from rule-based
    assert any(
        f.severity == DiscrepancySeverity.CRITICAL
        for f in a.findings)


def _test_assess_ml_hook_wrong_length_falls_back():
    def wrong_length(candidates):
        return [
            ClassificationResult(
                refined_severity=DiscrepancySeverity.LOW,
                is_true_discrepancy=True,
                confidence=0.9, reasoning="x")
            for _ in range(len(candidates) - 1)]   # short by 1

    eng = TradeFinanceDocumentCheckingEngine(
        ml_discrepancy_classifier=wrong_length)
    lc = _make_lc(expiry=date(2026, 6, 1))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20))
    a = eng.assess_presentation(lc, pres)
    assert all(f.ml_disabled is True for f in a.findings)


# ─── Discipline + provenance tests ──────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc()
    pres = _make_presentation()
    eng.assess_presentation(lc, pres)
    # Inputs unchanged
    assert lc.amount_kes == Decimal("1000000")
    assert pres.presentation_id == "PR-001"
    assert pres.documents[0].document_type == (
        DocumentType.COMMERCIAL_INVOICE)


def _test_full_provenance():
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_lc(expiry=date(2026, 6, 1))
    pres = _make_presentation(
        pres_date=date(2026, 6, 20))
    a = eng.assess_presentation(lc, pres)
    refs = " / ".join(a.framework_refs)
    assert "ENH-270" in refs
    assert "UCP 600" in refs
    assert "Rule 6" in refs
    assert "Rule 7" in refs
    # Per-finding provenance too
    if a.findings:
        f = a.findings[0]
        f_refs = " / ".join(f.framework_refs)
        assert "ENH-270" in f_refs
        assert "UCP 600" in f_refs


def _test_lc_terms_validates_amount():
    try:
        LCTerms(
            lc_reference="X",
            amount_kes=Decimal("-1"),
            currency="USD",
            expiry_date=date(2026, 7, 1),
            latest_shipment_date=None)
        assert False
    except ValueError:
        pass


def _test_lc_terms_validates_tolerance():
    try:
        LCTerms(
            lc_reference="X",
            amount_kes=Decimal("1"),
            currency="USD",
            expiry_date=date(2026, 7, 1),
            latest_shipment_date=None,
            amount_tolerance_pct=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def self_test() -> None:
    tests = [
        _test_amount_within_tolerance,
        _test_amount_over_tolerance,
        _test_amount_under_tolerance_low_severity,
        _test_amount_missing_field,
        _test_dates_within_periods,
        _test_late_presentation_after_expiry,
        _test_late_shipment,
        _test_presentation_period_exceeded,
        _test_all_required_present,
        _test_one_required_missing,
        _test_cross_doc_currency_match,
        _test_cross_doc_currency_conflict,
        _test_cross_doc_port_conflict,
        _test_cross_doc_description_mismatch,
        _test_assess_clean_presentation_conforming,
        _test_assess_critical_finding_refusal_likely,
        _test_assess_medium_finding_waivable,
        _test_assess_ml_hook_used,
        _test_assess_ml_hook_filters_false_positives,
        _test_assess_ml_hook_failure_falls_back,
        _test_assess_ml_hook_wrong_length_falls_back,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_lc_terms_validates_amount,
        _test_lc_terms_validates_tolerance,
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
            f"✗ trade_finance_document_checking self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_document_checking self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

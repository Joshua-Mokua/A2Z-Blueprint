"""utils/partner_supplier_recon.py — v10.53: Partner & Supplier Reconciliation.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-244 — Partner & Supplier Reconciliation                            ║
║  Cat B — revenue_assurance arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Multi-party reconciliation engine. Where ENH-241 reconciles internal   ║
║  totals between two sources (CBS vs GL), ENH-244 handles the more       ║
║  structured cross-counterparty cases:                                   ║
║                                                                          ║
║    A) PARTNER REVENUE SHARE                                              ║
║       — partner agreements specify share_pct of gross revenue           ║
║       — bank books gross revenue with partner_id + agreement_id         ║
║       — periodic settlements pay partner expected_share                 ║
║       — engine validates: actual_settlement ≈ Σ(revenue × share_pct)   ║
║       — discrepancy types: SHARE_UNDERPAID / OVERPAID / MISSING         ║
║                                                                          ║
║    B) SUPPLIER 3-WAY MATCH                                               ║
║       — Purchase Order specifies ordered amount                         ║
║       — Goods Receipt Note (GRN) specifies received amount              ║
║       — Supplier Invoice specifies invoiced amount                      ║
║       — Payment specifies paid amount                                   ║
║       — engine validates the chain PO → GRN → Invoice → Payment with    ║
║         per-step tolerance; flags mismatches at each transition         ║
║       — discrepancy types: PO_GRN_MISMATCH, GRN_INVOICE_MISMATCH,       ║
║         INVOICE_PAYMENT_MISMATCH, PO_WITHOUT_INVOICE,                   ║
║         INVOICE_WITHOUT_PO, INVOICE_BEFORE_DELIVERY                     ║
║                                                                          ║
║  Per Rule 7, engine is diagnostic only — never auto-creates             ║
║  settlements, never auto-issues payment instructions, never auto-       ║
║  reverses an invoice. Output feeds ENH-243 orchestrator (which          ║
║  composes with ENH-241 + ENH-242 findings already).                     ║
║                                                                          ║
║  Per Rule 1, every ReconciliationFinding surfaces:                      ║
║    finding_id + discrepancy_type + party_side + party_id + severity +  ║
║    related_ids (the records involved) + expected + observed +           ║
║    variance_kes + description + framework_refs                          ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_validation (ENH-241 — internal-source recon foundation)   ║
║    - revenue_orchestrator (ENH-243 — orchestrator already accepts       ║
║      ValidationSeverity, so callers wrap ReconciliationFinding into     ║
║      their workflow next to ENH-241/242 findings)                       ║
║    - regulatory_revenue_reporting (ENH-248 — partner totals must        ║
║      reconcile to statutory return)                                     ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from utils.revenue_validation import ValidationSeverity

SPEC_DEVIATION_NOTE = (
    "PartnerSupplierReconciliationEngine implements ENH-244. "
    "Pure stdlib (Decimal + dataclasses). Per Rule 1, every "
    "ReconciliationFinding surfaces all related_ids + expected + "
    "observed + variance_kes + framework refs. Per Rule 7, engine "
    "is diagnostic only — never auto-creates settlements, never "
    "auto-issues payment, never auto-reverses invoices. Reuses "
    "ValidationSeverity enum from utils.revenue_validation for "
    "consistency with ENH-241/242/243 across the arc — single "
    "severity vocabulary across all revenue_assurance engines."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class DiscrepancyType(Enum):
    """All discrepancy types the engine can surface."""
    # Partner revenue share
    SHARE_UNDERPAID = "SHARE_UNDERPAID"
    SHARE_OVERPAID = "SHARE_OVERPAID"
    SHARE_MISSING = "SHARE_MISSING"
    # Supplier 3-way match
    PO_GRN_MISMATCH = "PO_GRN_MISMATCH"
    GRN_INVOICE_MISMATCH = "GRN_INVOICE_MISMATCH"
    INVOICE_PAYMENT_MISMATCH = "INVOICE_PAYMENT_MISMATCH"
    PO_WITHOUT_INVOICE = "PO_WITHOUT_INVOICE"
    INVOICE_WITHOUT_PO = "INVOICE_WITHOUT_PO"
    INVOICE_BEFORE_DELIVERY = "INVOICE_BEFORE_DELIVERY"


class PartySide(Enum):
    """Which side of the bank's books this finding is on."""
    PARTNER = "PARTNER"     # bank pays out a share of revenue
    SUPPLIER = "SUPPLIER"   # bank pays for goods/services received


# ════════════════════════════════════════════════════════════════════════
# Partner-side dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PartnerAgreement:
    """One partner agreement specifying revenue share terms."""
    agreement_id: str
    partner_id: str
    revenue_category: str       # FEE_INCOME / COMMISSION_INCOME / etc.
    share_pct: Decimal          # 0..1 (e.g. Decimal("0.30") = 30%)
    effective_from: date
    effective_to: date
    min_settlement_kes: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.agreement_id:
            raise ValueError("agreement_id must be non-empty")
        if not (Decimal("0") <= self.share_pct <= Decimal("1")):
            raise ValueError(
                "share_pct must be in [0, 1] "
                f"(got {self.share_pct})")
        if self.effective_to < self.effective_from:
            raise ValueError(
                "effective_to must be ≥ effective_from")
        if self.min_settlement_kes < 0:
            raise ValueError("min_settlement_kes must be ≥ 0")


@dataclass(frozen=True)
class PartnerRevenueRecord:
    """One revenue posting attributable to a partner agreement."""
    record_id: str
    partner_id: str
    agreement_id: str
    revenue_category: str
    gross_revenue_kes: Decimal
    posting_date: date

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id must be non-empty")
        if self.gross_revenue_kes < 0:
            raise ValueError("gross_revenue_kes must be ≥ 0")


@dataclass(frozen=True)
class PartnerSettlement:
    """One actual settlement payment to a partner."""
    settlement_id: str
    partner_id: str
    agreement_id: str
    period: str                   # e.g. "2026-Q1", "2026-04"
    settled_kes: Decimal
    settlement_date: date

    def __post_init__(self) -> None:
        if not self.settlement_id:
            raise ValueError("settlement_id must be non-empty")
        if self.settled_kes < 0:
            raise ValueError("settled_kes must be ≥ 0")


# ════════════════════════════════════════════════════════════════════════
# Supplier-side dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PurchaseOrder:
    po_id: str
    supplier_id: str
    ordered_amount_kes: Decimal
    ordered_date: date
    expected_delivery_date: date

    def __post_init__(self) -> None:
        if not self.po_id:
            raise ValueError("po_id must be non-empty")
        if self.ordered_amount_kes < 0:
            raise ValueError("ordered_amount_kes must be ≥ 0")


@dataclass(frozen=True)
class GoodsReceiptNote:
    """GRN — confirms goods/services received."""
    grn_id: str
    po_id: str
    received_amount_kes: Decimal
    received_date: date

    def __post_init__(self) -> None:
        if not self.grn_id:
            raise ValueError("grn_id must be non-empty")
        if self.received_amount_kes < 0:
            raise ValueError("received_amount_kes must be ≥ 0")


@dataclass(frozen=True)
class SupplierInvoice:
    invoice_id: str
    supplier_id: str
    po_id: Optional[str]          # None for PO-less invoices
    invoiced_amount_kes: Decimal
    invoice_date: date

    def __post_init__(self) -> None:
        if not self.invoice_id:
            raise ValueError("invoice_id must be non-empty")
        if self.invoiced_amount_kes < 0:
            raise ValueError("invoiced_amount_kes must be ≥ 0")


@dataclass(frozen=True)
class SupplierPayment:
    payment_id: str
    invoice_id: str
    paid_amount_kes: Decimal
    paid_date: date

    def __post_init__(self) -> None:
        if not self.payment_id:
            raise ValueError("payment_id must be non-empty")
        if self.paid_amount_kes < 0:
            raise ValueError("paid_amount_kes must be ≥ 0")


# ════════════════════════════════════════════════════════════════════════
# Result dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReconciliationFinding:
    """One reconciliation discrepancy. Per Rule 1, full provenance."""
    finding_id: str
    discrepancy_type: DiscrepancyType
    party_side: PartySide
    party_id: str
    severity: ValidationSeverity
    related_ids: Tuple[str, ...]
    expected: str
    observed: str
    variance_kes: Optional[Decimal]
    description: str
    framework_refs: Tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ReconciliationReport:
    findings: Tuple[ReconciliationFinding, ...]
    partner_findings_count: int
    supplier_findings_count: int
    by_discrepancy_type: Dict[str, int]
    by_severity: Dict[str, int]
    partner_revenues_scanned: int
    supplier_pos_scanned: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class PartnerSupplierReconciliationEngine:
    """Diagnostic multi-party reconciliation engine.

    Per Rule 7, the engine never:
      - auto-creates partner settlements
      - auto-issues payments to suppliers
      - auto-reverses invoices
      - auto-resolves discrepancies
      - mutates source records (frozen dataclasses prevent this)

    Per Rule 1, every ReconciliationFinding carries enough context
    for a human investigator to reproduce — related IDs, expected,
    observed, variance in KES, framework refs.
    """

    # Default tolerance for partner share match (1% of expected)
    PARTNER_TOLERANCE_PCT: Decimal = Decimal("0.01")
    # Floor tolerance — for very small expected shares, KES 100
    # absolute is more reasonable than 1% of a small number
    PARTNER_TOLERANCE_FLOOR_KES: Decimal = Decimal("100")

    # Default tolerance for supplier 3-way match (KES 100 absolute)
    SUPPLIER_TOLERANCE_KES: Decimal = Decimal("100")

    # ── Partner: revenue share validation ─────────────────────────────
    def validate_partner_share(
        self,
        agreements: Sequence[PartnerAgreement],
        revenues: Sequence[PartnerRevenueRecord],
        settlements: Sequence[PartnerSettlement],
        period_extractor=None,
    ) -> Tuple[ReconciliationFinding, ...]:
        """For each (agreement, period), compute expected share from
        revenues, compare to actual settlement, flag mismatches.

        period_extractor: callable(date) -> period_str. Default
        YYYY-MM from posting_date.
        """
        if period_extractor is None:
            period_extractor = lambda d: d.strftime("%Y-%m")

        agreement_index = {a.agreement_id: a for a in agreements}

        # Aggregate revenue by (agreement_id, period)
        revenue_by_key: Dict[Tuple[str, str], Decimal] = {}
        for r in revenues:
            period = period_extractor(r.posting_date)
            key = (r.agreement_id, period)
            revenue_by_key[key] = (
                revenue_by_key.get(key, Decimal("0"))
                + r.gross_revenue_kes)

        # Index settlements by (agreement_id, period)
        settlement_index: Dict[
            Tuple[str, str], PartnerSettlement] = {}
        for s in settlements:
            settlement_index[(s.agreement_id, s.period)] = s

        findings: List[ReconciliationFinding] = []
        for (agreement_id, period), gross in revenue_by_key.items():
            agreement = agreement_index.get(agreement_id)
            if agreement is None:
                # Agreement not in master — flag as missing context.
                # Caller should ensure agreement set is comprehensive.
                continue
            expected_share = gross * agreement.share_pct
            settlement = settlement_index.get(
                (agreement_id, period))

            if settlement is None:
                if expected_share < agreement.min_settlement_kes:
                    # Below settlement floor — legitimate deferral
                    # (carried forward to next period). Skip.
                    continue
                findings.append(ReconciliationFinding(
                    finding_id=(
                        f"PSR-MISSING-{agreement_id}-{period}"),
                    discrepancy_type=DiscrepancyType.SHARE_MISSING,
                    party_side=PartySide.PARTNER,
                    party_id=agreement.partner_id,
                    severity=ValidationSeverity.HIGH,
                    related_ids=(agreement_id,),
                    expected=(
                        f"settlement of {expected_share} for "
                        f"period {period}"),
                    observed=f"no settlement record for {period}",
                    variance_kes=expected_share,
                    description=(
                        f"partner {agreement.partner_id} earned "
                        f"share {expected_share} for {period} but "
                        f"no settlement was recorded"),
                    framework_refs=(
                        "ENH-244 §partner_share",
                        "Partner agreement §settlement_terms")))
                continue

            tolerance = max(
                self.PARTNER_TOLERANCE_FLOOR_KES,
                expected_share * self.PARTNER_TOLERANCE_PCT)
            variance = settlement.settled_kes - expected_share

            if abs(variance) <= tolerance:
                continue

            if variance < 0:
                # Settlement is short of expected → underpaid
                findings.append(ReconciliationFinding(
                    finding_id=(
                        f"PSR-UNDER-{agreement_id}-{period}"),
                    discrepancy_type=(
                        DiscrepancyType.SHARE_UNDERPAID),
                    party_side=PartySide.PARTNER,
                    party_id=agreement.partner_id,
                    severity=ValidationSeverity.MEDIUM,
                    related_ids=(
                        agreement_id, settlement.settlement_id),
                    expected=(
                        f"≈ {expected_share} (gross "
                        f"{gross} × {agreement.share_pct})"),
                    observed=(
                        f"settled {settlement.settled_kes}"),
                    variance_kes=variance,
                    description=(
                        f"partner {agreement.partner_id} "
                        f"underpaid by {abs(variance)} for "
                        f"period {period}"),
                    framework_refs=(
                        "ENH-244 §partner_share",)))
            else:
                # Settlement exceeds expected → overpaid
                findings.append(ReconciliationFinding(
                    finding_id=(
                        f"PSR-OVER-{agreement_id}-{period}"),
                    discrepancy_type=(
                        DiscrepancyType.SHARE_OVERPAID),
                    party_side=PartySide.PARTNER,
                    party_id=agreement.partner_id,
                    severity=ValidationSeverity.MEDIUM,
                    related_ids=(
                        agreement_id, settlement.settlement_id),
                    expected=(
                        f"≈ {expected_share} (gross "
                        f"{gross} × {agreement.share_pct})"),
                    observed=(
                        f"settled {settlement.settled_kes}"),
                    variance_kes=variance,
                    description=(
                        f"partner {agreement.partner_id} "
                        f"overpaid by {variance} for "
                        f"period {period}"),
                    framework_refs=(
                        "ENH-244 §partner_share",
                        "Revenue assurance — overpayment is "
                        "leakage")))

        return tuple(findings)

    # ── Supplier: 3-way match ─────────────────────────────────────────
    def match_supplier_three_way(
        self,
        purchase_orders: Sequence[PurchaseOrder],
        grns: Sequence[GoodsReceiptNote],
        invoices: Sequence[SupplierInvoice],
        payments: Sequence[SupplierPayment],
    ) -> Tuple[ReconciliationFinding, ...]:
        """Walk the chain PO → GRN → Invoice → Payment with
        per-step tolerance. Each transition can produce at most
        one finding."""
        po_index: Dict[str, PurchaseOrder] = {
            p.po_id: p for p in purchase_orders}

        # Aggregate GRNs by po_id (one PO can have multiple
        # partial deliveries)
        grn_total_by_po: Dict[str, Decimal] = {}
        grn_earliest_date_by_po: Dict[str, date] = {}
        for g in grns:
            grn_total_by_po[g.po_id] = (
                grn_total_by_po.get(g.po_id, Decimal("0"))
                + g.received_amount_kes)
            existing = grn_earliest_date_by_po.get(g.po_id)
            if existing is None or g.received_date < existing:
                grn_earliest_date_by_po[g.po_id] = g.received_date

        # Aggregate invoices by po_id (where set)
        invoice_total_by_po: Dict[str, Decimal] = {}
        invoices_with_po: List[SupplierInvoice] = []
        invoices_without_po: List[SupplierInvoice] = []
        for inv in invoices:
            if inv.po_id is None:
                invoices_without_po.append(inv)
                continue
            invoices_with_po.append(inv)
            invoice_total_by_po[inv.po_id] = (
                invoice_total_by_po.get(inv.po_id, Decimal("0"))
                + inv.invoiced_amount_kes)

        # Aggregate payments by invoice_id
        payment_total_by_invoice: Dict[str, Decimal] = {}
        for p in payments:
            payment_total_by_invoice[p.invoice_id] = (
                payment_total_by_invoice.get(
                    p.invoice_id, Decimal("0"))
                + p.paid_amount_kes)

        findings: List[ReconciliationFinding] = []

        # ── Step 1: PO vs GRN totals ─────────────────────────────
        for po in purchase_orders:
            grn_total = grn_total_by_po.get(po.po_id, Decimal("0"))
            if abs(grn_total - po.ordered_amount_kes) > (
                    self.SUPPLIER_TOLERANCE_KES):
                findings.append(ReconciliationFinding(
                    finding_id=f"PSR-PO-GRN-{po.po_id}",
                    discrepancy_type=(
                        DiscrepancyType.PO_GRN_MISMATCH),
                    party_side=PartySide.SUPPLIER,
                    party_id=po.supplier_id,
                    severity=ValidationSeverity.MEDIUM,
                    related_ids=(po.po_id,),
                    expected=f"GRN total ≈ {po.ordered_amount_kes}",
                    observed=f"GRN total = {grn_total}",
                    variance_kes=grn_total - po.ordered_amount_kes,
                    description=(
                        f"PO {po.po_id} ordered "
                        f"{po.ordered_amount_kes} but received "
                        f"{grn_total} (variance "
                        f"{grn_total - po.ordered_amount_kes})"),
                    framework_refs=(
                        "ENH-244 §supplier_3way",
                        "Procurement controls §goods_receipt")))

        # ── Step 2: GRN vs Invoice totals ────────────────────────
        for po in purchase_orders:
            grn_total = grn_total_by_po.get(po.po_id, Decimal("0"))
            inv_total = invoice_total_by_po.get(
                po.po_id, Decimal("0"))
            # Skip if no invoices at all — handled separately as
            # PO_WITHOUT_INVOICE
            if inv_total == 0:
                continue
            if abs(inv_total - grn_total) > (
                    self.SUPPLIER_TOLERANCE_KES):
                findings.append(ReconciliationFinding(
                    finding_id=f"PSR-GRN-INV-{po.po_id}",
                    discrepancy_type=(
                        DiscrepancyType.GRN_INVOICE_MISMATCH),
                    party_side=PartySide.SUPPLIER,
                    party_id=po.supplier_id,
                    severity=ValidationSeverity.HIGH,
                    related_ids=(po.po_id,),
                    expected=f"invoice total ≈ {grn_total}",
                    observed=f"invoice total = {inv_total}",
                    variance_kes=inv_total - grn_total,
                    description=(
                        f"PO {po.po_id} received {grn_total} "
                        f"but invoiced {inv_total} (variance "
                        f"{inv_total - grn_total})"),
                    framework_refs=(
                        "ENH-244 §supplier_3way",
                        "Procurement controls §invoice_match")))

        # ── Step 3: PO without invoice ───────────────────────────
        for po in purchase_orders:
            grn_total = grn_total_by_po.get(po.po_id, Decimal("0"))
            inv_total = invoice_total_by_po.get(
                po.po_id, Decimal("0"))
            if grn_total > 0 and inv_total == 0:
                findings.append(ReconciliationFinding(
                    finding_id=f"PSR-PO-NOINV-{po.po_id}",
                    discrepancy_type=(
                        DiscrepancyType.PO_WITHOUT_INVOICE),
                    party_side=PartySide.SUPPLIER,
                    party_id=po.supplier_id,
                    severity=ValidationSeverity.MEDIUM,
                    related_ids=(po.po_id,),
                    expected="invoice received against GRN",
                    observed="no invoice booked against this PO",
                    variance_kes=grn_total,
                    description=(
                        f"PO {po.po_id} has GRN value "
                        f"{grn_total} but no invoice booked — "
                        f"unrecognised liability"),
                    framework_refs=(
                        "ENH-244 §supplier_3way",
                        "Accruals discipline")))

        # ── Step 4: Invoice without PO ───────────────────────────
        for inv in invoices_without_po:
            findings.append(ReconciliationFinding(
                finding_id=f"PSR-INV-NOPO-{inv.invoice_id}",
                discrepancy_type=(
                    DiscrepancyType.INVOICE_WITHOUT_PO),
                party_side=PartySide.SUPPLIER,
                party_id=inv.supplier_id,
                severity=ValidationSeverity.MEDIUM,
                related_ids=(inv.invoice_id,),
                expected="invoice references a PO",
                observed="invoice has no po_id",
                variance_kes=inv.invoiced_amount_kes,
                description=(
                    f"invoice {inv.invoice_id} from supplier "
                    f"{inv.supplier_id} has no PO reference — "
                    f"investigate authorisation chain"),
                framework_refs=(
                    "ENH-244 §supplier_3way",
                    "Procurement controls §authorisation")))

        # ── Step 5: Invoice before delivery ──────────────────────
        for inv in invoices_with_po:
            grn_date = grn_earliest_date_by_po.get(inv.po_id)
            if grn_date is None:
                # No GRN yet — flagged elsewhere as
                # PO_WITHOUT_INVOICE inverse won't help, but the
                # invoice_before_delivery check needs a GRN to
                # compare. Skip.
                continue
            if inv.invoice_date < grn_date:
                days_early = (
                    grn_date.toordinal()
                    - inv.invoice_date.toordinal())
                findings.append(ReconciliationFinding(
                    finding_id=(
                        f"PSR-INV-EARLY-{inv.invoice_id}"),
                    discrepancy_type=(
                        DiscrepancyType.INVOICE_BEFORE_DELIVERY),
                    party_side=PartySide.SUPPLIER,
                    party_id=inv.supplier_id,
                    severity=ValidationSeverity.MEDIUM,
                    related_ids=(inv.invoice_id, inv.po_id or ""),
                    expected=(
                        f"invoice_date ≥ earliest GRN date "
                        f"({grn_date.isoformat()})"),
                    observed=(
                        f"invoice_date = "
                        f"{inv.invoice_date.isoformat()} "
                        f"({days_early} day(s) before)"),
                    variance_kes=None,
                    description=(
                        f"invoice {inv.invoice_id} dated before "
                        f"goods receipt — potential premature "
                        f"billing"),
                    framework_refs=(
                        "ENH-244 §supplier_3way",
                        "Procurement controls §timing")))

        # ── Step 6: Invoice vs Payment ───────────────────────────
        invoice_index: Dict[str, SupplierInvoice] = {
            inv.invoice_id: inv for inv in invoices}
        for inv in invoices:
            paid = payment_total_by_invoice.get(
                inv.invoice_id, Decimal("0"))
            # Zero-paid invoices may simply not be due yet — only
            # flag clear discrepancies (paid > invoiced or paid
            # within tolerance but ≠ invoiced)
            if paid == 0:
                continue
            if abs(paid - inv.invoiced_amount_kes) <= (
                    self.SUPPLIER_TOLERANCE_KES):
                continue
            findings.append(ReconciliationFinding(
                finding_id=f"PSR-INV-PAY-{inv.invoice_id}",
                discrepancy_type=(
                    DiscrepancyType.INVOICE_PAYMENT_MISMATCH),
                party_side=PartySide.SUPPLIER,
                party_id=inv.supplier_id,
                severity=(
                    ValidationSeverity.HIGH
                    if paid > inv.invoiced_amount_kes
                    else ValidationSeverity.MEDIUM),
                related_ids=(inv.invoice_id,),
                expected=(
                    f"paid ≈ {inv.invoiced_amount_kes}"),
                observed=f"paid = {paid}",
                variance_kes=paid - inv.invoiced_amount_kes,
                description=(
                    f"invoice {inv.invoice_id} invoiced "
                    f"{inv.invoiced_amount_kes} but paid "
                    f"{paid} (variance "
                    f"{paid - inv.invoiced_amount_kes})"),
                framework_refs=(
                    "ENH-244 §supplier_3way",
                    "Procurement controls §payment_match")))

        return tuple(findings)

    # ── Public API: orchestrator ──────────────────────────────────────
    def reconcile_all(
        self,
        agreements: Sequence[PartnerAgreement] = (),
        partner_revenues: Sequence[PartnerRevenueRecord] = (),
        settlements: Sequence[PartnerSettlement] = (),
        purchase_orders: Sequence[PurchaseOrder] = (),
        grns: Sequence[GoodsReceiptNote] = (),
        invoices: Sequence[SupplierInvoice] = (),
        payments: Sequence[SupplierPayment] = (),
    ) -> ReconciliationReport:
        """Run partner + supplier reconciliation, return unified
        report."""
        partner_findings = self.validate_partner_share(
            agreements, partner_revenues, settlements)
        supplier_findings = self.match_supplier_three_way(
            purchase_orders, grns, invoices, payments)
        all_findings = partner_findings + supplier_findings

        by_type: Dict[str, int] = {
            d.value: 0 for d in DiscrepancyType}
        for f in all_findings:
            by_type[f.discrepancy_type.value] += 1
        by_sev: Dict[str, int] = {
            s.value: 0 for s in ValidationSeverity}
        for f in all_findings:
            by_sev[f.severity.value] += 1

        return ReconciliationReport(
            findings=all_findings,
            partner_findings_count=len(partner_findings),
            supplier_findings_count=len(supplier_findings),
            by_discrepancy_type=by_type,
            by_severity=by_sev,
            partner_revenues_scanned=len(partner_revenues),
            supplier_pos_scanned=len(purchase_orders),
            framework_refs=(
                "ENH-244 §partner_share + §supplier_3way",
                "Composes with ENH-241 (revenue_validation) "
                "internal-source recon",
                "Output flows to ENH-243 orchestrator via "
                "ValidationSeverity reuse",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_agreement_validates_share_pct_range():
    try:
        PartnerAgreement(
            agreement_id="A1", partner_id="P", revenue_category="X",
            share_pct=Decimal("1.5"),
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31))
        assert False
    except ValueError:
        pass


def _test_agreement_validates_dates():
    try:
        PartnerAgreement(
            agreement_id="A1", partner_id="P", revenue_category="X",
            share_pct=Decimal("0.3"),
            effective_from=date(2026, 12, 31),
            effective_to=date(2026, 1, 1))
        assert False
    except ValueError:
        pass


def _test_supplier_dataclasses_validate_negative_amounts():
    try:
        PurchaseOrder(
            po_id="PO1", supplier_id="S1",
            ordered_amount_kes=Decimal("-1"),
            ordered_date=date(2026, 4, 1),
            expected_delivery_date=date(2026, 4, 30))
        assert False
    except ValueError:
        pass


def _test_partner_share_clean_match_no_findings():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
        PartnerRevenueRecord(
            record_id="r2", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("500000"),
            posting_date=date(2026, 4, 20)),
    )
    # Expected share = 1,500,000 × 0.30 = 450,000
    settlements = (
        PartnerSettlement(
            settlement_id="S1", partner_id="MTN",
            agreement_id="A1", period="2026-04",
            settled_kes=Decimal("450000"),
            settlement_date=date(2026, 5, 5)),
    )
    findings = eng.validate_partner_share(
        (agreement,), revenues, settlements)
    assert len(findings) == 0


def _test_partner_share_underpaid_flagged():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
    )
    # Expected 300k, settled 250k → 50k under
    settlements = (
        PartnerSettlement(
            settlement_id="S1", partner_id="MTN",
            agreement_id="A1", period="2026-04",
            settled_kes=Decimal("250000"),
            settlement_date=date(2026, 5, 5)),
    )
    findings = eng.validate_partner_share(
        (agreement,), revenues, settlements)
    assert len(findings) == 1
    assert (
        findings[0].discrepancy_type
        == DiscrepancyType.SHARE_UNDERPAID)
    assert findings[0].variance_kes == Decimal("-50000")


def _test_partner_share_overpaid_flagged():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
    )
    # Expected 300k, settled 350k → 50k over
    settlements = (
        PartnerSettlement(
            settlement_id="S1", partner_id="MTN",
            agreement_id="A1", period="2026-04",
            settled_kes=Decimal("350000"),
            settlement_date=date(2026, 5, 5)),
    )
    findings = eng.validate_partner_share(
        (agreement,), revenues, settlements)
    assert len(findings) == 1
    assert (
        findings[0].discrepancy_type
        == DiscrepancyType.SHARE_OVERPAID)


def _test_partner_share_missing_settlement_flagged():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
    )
    findings = eng.validate_partner_share(
        (agreement,), revenues, ())
    assert len(findings) == 1
    assert (
        findings[0].discrepancy_type
        == DiscrepancyType.SHARE_MISSING)
    assert findings[0].severity == ValidationSeverity.HIGH


def _test_partner_share_below_min_settlement_skipped():
    """Expected share below min_settlement → carried forward, no
    finding."""
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        min_settlement_kes=Decimal("10000"))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("10000"),
            posting_date=date(2026, 4, 5)),
    )
    # Expected 3,000 < min 10,000 → skip
    findings = eng.validate_partner_share(
        (agreement,), revenues, ())
    assert len(findings) == 0


def _test_partner_share_within_tolerance_no_finding():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
    )
    # Expected 300,000; settled 300,500 → diff 500, tolerance
    # max(100, 300,000 × 0.01 = 3,000) = 3,000 → OK
    settlements = (
        PartnerSettlement(
            settlement_id="S1", partner_id="MTN",
            agreement_id="A1", period="2026-04",
            settled_kes=Decimal("300500"),
            settlement_date=date(2026, 5, 5)),
    )
    findings = eng.validate_partner_share(
        (agreement,), revenues, settlements)
    assert len(findings) == 0


def _test_supplier_3way_clean_match_no_findings():
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO1", supplier_id="S1",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=date(2026, 4, 1),
        expected_delivery_date=date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN1", po_id="PO1",
        received_amount_kes=Decimal("100000"),
        received_date=date(2026, 4, 14))
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id="PO1",
        invoiced_amount_kes=Decimal("100000"),
        invoice_date=date(2026, 4, 16))
    payment = SupplierPayment(
        payment_id="PAY1", invoice_id="INV1",
        paid_amount_kes=Decimal("100000"),
        paid_date=date(2026, 4, 30))
    findings = eng.match_supplier_three_way(
        (po,), (grn,), (invoice,), (payment,))
    assert len(findings) == 0


def _test_supplier_po_grn_mismatch():
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO1", supplier_id="S1",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=date(2026, 4, 1),
        expected_delivery_date=date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN1", po_id="PO1",
        received_amount_kes=Decimal("85000"),
        received_date=date(2026, 4, 14))
    findings = eng.match_supplier_three_way(
        (po,), (grn,), (), ())
    assert any(
        f.discrepancy_type == DiscrepancyType.PO_GRN_MISMATCH
        for f in findings)


def _test_supplier_grn_invoice_mismatch_high():
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO1", supplier_id="S1",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=date(2026, 4, 1),
        expected_delivery_date=date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN1", po_id="PO1",
        received_amount_kes=Decimal("100000"),
        received_date=date(2026, 4, 14))
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id="PO1",
        invoiced_amount_kes=Decimal("120000"),  # 20k over GRN
        invoice_date=date(2026, 4, 16))
    findings = eng.match_supplier_three_way(
        (po,), (grn,), (invoice,), ())
    grn_inv = [
        f for f in findings
        if f.discrepancy_type
        == DiscrepancyType.GRN_INVOICE_MISMATCH]
    assert len(grn_inv) == 1
    assert grn_inv[0].severity == ValidationSeverity.HIGH


def _test_supplier_po_without_invoice():
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO1", supplier_id="S1",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=date(2026, 4, 1),
        expected_delivery_date=date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN1", po_id="PO1",
        received_amount_kes=Decimal("100000"),
        received_date=date(2026, 4, 14))
    findings = eng.match_supplier_three_way(
        (po,), (grn,), (), ())
    assert any(
        f.discrepancy_type == DiscrepancyType.PO_WITHOUT_INVOICE
        for f in findings)


def _test_supplier_invoice_without_po():
    eng = PartnerSupplierReconciliationEngine()
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id=None,
        invoiced_amount_kes=Decimal("50000"),
        invoice_date=date(2026, 4, 5))
    findings = eng.match_supplier_three_way(
        (), (), (invoice,), ())
    assert any(
        f.discrepancy_type == DiscrepancyType.INVOICE_WITHOUT_PO
        for f in findings)


def _test_supplier_invoice_before_delivery():
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO1", supplier_id="S1",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=date(2026, 4, 1),
        expected_delivery_date=date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN1", po_id="PO1",
        received_amount_kes=Decimal("100000"),
        received_date=date(2026, 4, 14))
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id="PO1",
        invoiced_amount_kes=Decimal("100000"),
        invoice_date=date(2026, 4, 5))   # before delivery!
    findings = eng.match_supplier_three_way(
        (po,), (grn,), (invoice,), ())
    assert any(
        f.discrepancy_type
        == DiscrepancyType.INVOICE_BEFORE_DELIVERY
        for f in findings)


def _test_supplier_invoice_payment_mismatch_overpay_high():
    eng = PartnerSupplierReconciliationEngine()
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id="PO1",
        invoiced_amount_kes=Decimal("100000"),
        invoice_date=date(2026, 4, 16))
    # Paid more than invoiced — overpayment
    payment = SupplierPayment(
        payment_id="PAY1", invoice_id="INV1",
        paid_amount_kes=Decimal("110000"),
        paid_date=date(2026, 4, 30))
    findings = eng.match_supplier_three_way(
        (), (), (invoice,), (payment,))
    inv_pay = [
        f for f in findings
        if f.discrepancy_type
        == DiscrepancyType.INVOICE_PAYMENT_MISMATCH]
    assert len(inv_pay) == 1
    assert inv_pay[0].severity == ValidationSeverity.HIGH


def _test_supplier_zero_payment_not_flagged():
    """Invoice booked but unpaid → not an issue (may not be due
    yet); only flag clear discrepancies."""
    eng = PartnerSupplierReconciliationEngine()
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id="PO1",
        invoiced_amount_kes=Decimal("100000"),
        invoice_date=date(2026, 4, 16))
    findings = eng.match_supplier_three_way(
        (), (), (invoice,), ())
    inv_pay = [
        f for f in findings
        if f.discrepancy_type
        == DiscrepancyType.INVOICE_PAYMENT_MISMATCH]
    assert len(inv_pay) == 0


def _test_partial_grns_aggregate():
    """Multiple GRNs for one PO sum together."""
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO1", supplier_id="S1",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=date(2026, 4, 1),
        expected_delivery_date=date(2026, 4, 15))
    grn1 = GoodsReceiptNote(
        grn_id="GRN1", po_id="PO1",
        received_amount_kes=Decimal("60000"),
        received_date=date(2026, 4, 10))
    grn2 = GoodsReceiptNote(
        grn_id="GRN2", po_id="PO1",
        received_amount_kes=Decimal("40000"),
        received_date=date(2026, 4, 14))
    findings = eng.match_supplier_three_way(
        (po,), (grn1, grn2), (), ())
    # GRN total = 100,000 = PO total → no PO_GRN mismatch
    po_grn = [
        f for f in findings
        if f.discrepancy_type == DiscrepancyType.PO_GRN_MISMATCH]
    assert len(po_grn) == 0


def _test_reconcile_all_orchestrates():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
    )
    invoice = SupplierInvoice(
        invoice_id="INV1", supplier_id="S1", po_id=None,
        invoiced_amount_kes=Decimal("50000"),
        invoice_date=date(2026, 4, 5))
    report = eng.reconcile_all(
        agreements=(agreement,), partner_revenues=revenues,
        settlements=(), invoices=(invoice,))
    assert isinstance(report, ReconciliationReport)
    assert report.partner_findings_count == 1   # missing settlement
    assert report.supplier_findings_count == 1  # invoice without PO
    assert report.partner_revenues_scanned == 1


def _test_finding_has_full_provenance():
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="A1", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="A1",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=date(2026, 4, 5)),
    )
    settlements = (
        PartnerSettlement(
            settlement_id="S1", partner_id="MTN",
            agreement_id="A1", period="2026-04",
            settled_kes=Decimal("250000"),
            settlement_date=date(2026, 5, 5)),
    )
    findings = eng.validate_partner_share(
        (agreement,), revenues, settlements)
    f = findings[0]
    assert f.finding_id
    assert f.party_id == "MTN"
    assert f.party_side == PartySide.PARTNER
    assert f.expected
    assert f.observed
    assert f.variance_kes is not None
    assert len(f.framework_refs) >= 1
    assert "A1" in f.related_ids


def self_test() -> None:
    tests = [
        _test_agreement_validates_share_pct_range,
        _test_agreement_validates_dates,
        _test_supplier_dataclasses_validate_negative_amounts,
        _test_partner_share_clean_match_no_findings,
        _test_partner_share_underpaid_flagged,
        _test_partner_share_overpaid_flagged,
        _test_partner_share_missing_settlement_flagged,
        _test_partner_share_below_min_settlement_skipped,
        _test_partner_share_within_tolerance_no_finding,
        _test_supplier_3way_clean_match_no_findings,
        _test_supplier_po_grn_mismatch,
        _test_supplier_grn_invoice_mismatch_high,
        _test_supplier_po_without_invoice,
        _test_supplier_invoice_without_po,
        _test_supplier_invoice_before_delivery,
        _test_supplier_invoice_payment_mismatch_overpay_high,
        _test_supplier_zero_payment_not_flagged,
        _test_partial_grns_aggregate,
        _test_reconcile_all_orchestrates,
        _test_finding_has_full_provenance,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ partner_supplier_recon self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ partner_supplier_recon self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

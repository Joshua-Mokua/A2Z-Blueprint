"""utils/regulatory_revenue_reporting.py — v10.57: Regulatory Revenue Reporting.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-248 — Regulatory Revenue Reporting                                 ║
║  Cat B — revenue_assurance arc final engine                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Auto-generation of revenue-side regulatory report data, plus           ║
║  reconciliation between management figures and statutory figures.       ║
║                                                                          ║
║  The engine produces report DATA STRUCTURES — never submits anything    ║
║  to CBK / KRA / any regulator. Per Rule 7, submission is a human        ║
║  workflow concern with regulator-specific rails (CBK BSD portal, KRA    ║
║  iTax). Engine output is a structured ReportPackage that the caller    ║
║  serializes (XBRL / XML / CSV) per regulator's spec.                   ║
║                                                                          ║
║  Three capabilities:                                                    ║
║    1. generate_report(template, records) → ReportPackage                ║
║       — aggregate revenue records into the line items the template     ║
║         specifies; surface unmapped categories rather than dropping    ║
║    2. reconcile_management_vs_statutory(...) → MgmtStatReconResult     ║
║       — compare management ledger figures to statutory return          ║
║         figures; classify differences as TIMING / CLASSIFICATION /     ║
║         GENUINE                                                          ║
║    3. validate_completeness(report) → CompletenessReport                ║
║       — check no required line item is missing or zero                  ║
║                                                                          ║
║  Per Rule 1, every ReportLineItem surfaces source records + value +    ║
║  computation, every ReconciliationDifference surfaces both figures +   ║
║  classification + suggested explanation type.                           ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_validation (ENH-241 — RevenueRecord shape reused)         ║
║    - regulatory_reporting (existing — XBRL serialization layer)        ║
║    - revenue_orchestrator (ENH-243 — completeness findings flow)       ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from utils.revenue_validation import (
    RevenueRecord, ValidationSeverity)

SPEC_DEVIATION_NOTE = (
    "RegulatoryRevenueReportingEngine implements ENH-248. Pure "
    "stdlib (Decimal + dataclasses). Per Rule 1, every line item "
    "surfaces sourcing detail + computation; every reconciliation "
    "difference surfaces both figures + classification. Per Rule "
    "7, engine NEVER submits reports to regulators — it produces "
    "structured ReportPackage data; caller's submission workflow "
    "handles serialization (XBRL/XML/CSV) and submission rails."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class Regulator(Enum):
    CBK = "CBK"          # Central Bank of Kenya
    KRA = "KRA"          # Kenya Revenue Authority
    INTERNAL = "INTERNAL"  # management-only report


class DifferenceType(Enum):
    """How a mgmt-vs-statutory difference should be classified."""
    TIMING = "TIMING"                # cut-off difference, will reverse
    CLASSIFICATION = "CLASSIFICATION"  # different category mapping
    GENUINE = "GENUINE"              # actual mismatch needs investigation
    UNCLASSIFIED = "UNCLASSIFIED"


class CompletenessIssue(Enum):
    MISSING_LINE_ITEM = "MISSING_LINE_ITEM"
    ZERO_AMOUNT_REQUIRED_LINE = "ZERO_AMOUNT_REQUIRED_LINE"
    UNMAPPED_CATEGORY = "UNMAPPED_CATEGORY"


# ════════════════════════════════════════════════════════════════════════
# Template + input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReportLineSpec:
    """One line item the template requires."""
    line_code: str
    line_name: str
    revenue_categories: FrozenSet[str]   # which RevenueRecord categories
    required: bool = True

    def __post_init__(self) -> None:
        if not self.line_code:
            raise ValueError("line_code must be non-empty")
        if not self.revenue_categories:
            raise ValueError(
                "revenue_categories must be non-empty")


@dataclass(frozen=True)
class ReportTemplate:
    """A regulator's revenue report structure."""
    template_id: str
    regulator: Regulator
    period_label: str        # e.g. "2026-Q1"
    period_start: date
    period_end: date
    line_specs: Tuple[ReportLineSpec, ...]

    def __post_init__(self) -> None:
        if not self.template_id:
            raise ValueError("template_id must be non-empty")
        if not self.line_specs:
            raise ValueError("line_specs must be non-empty")
        if self.period_end < self.period_start:
            raise ValueError(
                "period_end must be ≥ period_start")
        # Line codes must be unique
        codes = [s.line_code for s in self.line_specs]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate line_code in template")


@dataclass(frozen=True)
class StatutoryReportRecord:
    """A line item from the actual statutory return submitted to
    regulator (e.g., what KRA received). Used for mgmt-vs-statutory
    reconciliation."""
    line_code: str
    period_label: str
    amount_kes: Decimal
    submitted_date: date

    def __post_init__(self) -> None:
        if not self.line_code:
            raise ValueError("line_code must be non-empty")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReportLineItem:
    """One generated line of a report."""
    line_code: str
    line_name: str
    amount_kes: Decimal
    record_count: int
    contributing_record_ids: Tuple[str, ...]
    revenue_categories: Tuple[str, ...]


@dataclass(frozen=True)
class ReportPackage:
    """A complete generated report. Caller serializes per regulator
    spec; engine produces only the structured data."""
    template_id: str
    regulator: Regulator
    period_label: str
    period_start: date
    period_end: date
    line_items: Tuple[ReportLineItem, ...]
    total_kes: Decimal
    unmapped_categories: Tuple[str, ...]
    unmapped_record_count: int
    framework_refs: Tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class ReconciliationDifference:
    line_code: str
    period_label: str
    management_kes: Decimal
    statutory_kes: Decimal
    variance_kes: Decimal
    classification: DifferenceType
    severity: ValidationSeverity
    description: str
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class MgmtStatReconResult:
    differences: Tuple[ReconciliationDifference, ...]
    matched_count: int
    by_classification: Dict[str, int]
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class CompletenessFinding:
    issue: CompletenessIssue
    line_code: str
    description: str
    severity: ValidationSeverity


@dataclass(frozen=True)
class CompletenessReport:
    findings: Tuple[CompletenessFinding, ...]
    required_lines: int
    populated_lines: int
    unmapped_categories_count: int


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class RegulatoryRevenueReportingEngine:
    """Diagnostic engine for regulatory revenue report generation +
    mgmt-statutory reconciliation.

    Per Rule 7, engine never:
      - submits a report to any regulator
      - serializes to XBRL/XML/CSV (that's caller's choice based on
        regulator format)
      - mutates inputs
      - persists output
      - calls external systems
    """

    # Default reconciliation tolerance — CBK and KRA returns are
    # rounded to KES 1; tighter than that creates false positives.
    RECON_TOLERANCE_KES: Decimal = Decimal("1.00")

    # Cut-off-window heuristic: differences ≤ this many days outside
    # the period boundary are likely TIMING differences (records
    # straddling the cut-off). Beyond this, more likely GENUINE.
    TIMING_DAYS_HEURISTIC: int = 5

    # ── Capability 1: generate report ───────────────────────────────
    def generate_report(
        self,
        template: ReportTemplate,
        records: Sequence[RevenueRecord],
        notes: str = "",
    ) -> ReportPackage:
        """Aggregate records into the line items the template
        specifies. Records outside the period are excluded.
        Categories not mapped to any line are surfaced as
        unmapped_categories rather than silently dropped."""
        # Filter to period
        in_period = [
            r for r in records
            if (template.period_start
                <= r.posting_date
                <= template.period_end)]

        # Build line items
        line_items: List[ReportLineItem] = []
        used_record_ids: set = set()
        total = Decimal("0")
        for spec in template.line_specs:
            matching = [
                r for r in in_period
                if r.revenue_category in spec.revenue_categories]
            amount = sum(
                (r.amount_kes for r in matching), Decimal("0"))
            line_items.append(ReportLineItem(
                line_code=spec.line_code,
                line_name=spec.line_name,
                amount_kes=amount,
                record_count=len(matching),
                contributing_record_ids=tuple(
                    r.record_id for r in matching),
                revenue_categories=tuple(
                    sorted(spec.revenue_categories))))
            for r in matching:
                used_record_ids.add(r.record_id)
            total += amount

        # Find unmapped categories
        all_mapped = set()
        for spec in template.line_specs:
            all_mapped.update(spec.revenue_categories)
        unmapped_records = [
            r for r in in_period
            if r.revenue_category not in all_mapped]
        unmapped_cats = tuple(sorted(set(
            r.revenue_category for r in unmapped_records)))

        return ReportPackage(
            template_id=template.template_id,
            regulator=template.regulator,
            period_label=template.period_label,
            period_start=template.period_start,
            period_end=template.period_end,
            line_items=tuple(line_items),
            total_kes=total,
            unmapped_categories=unmapped_cats,
            unmapped_record_count=len(unmapped_records),
            framework_refs=(
                "ENH-248 §generate_report",
                f"Regulator: {template.regulator.value}",
                "Per Rule 7 — engine produces data, never submits",
            ),
            notes=notes)

    # ── Capability 2: mgmt-vs-statutory reconciliation ──────────────
    def reconcile_management_vs_statutory(
        self,
        management_package: ReportPackage,
        statutory_records: Sequence[StatutoryReportRecord],
    ) -> MgmtStatReconResult:
        """Compare each management line item to the statutory record
        for the same (line_code, period_label). Differences classified
        by simple heuristic — TIMING if amount-level small relative
        to size, CLASSIFICATION if a different line code has the
        complementary amount, GENUINE otherwise."""
        stat_index: Dict[
            Tuple[str, str], StatutoryReportRecord] = {
            (s.line_code, s.period_label): s
            for s in statutory_records}

        differences: List[ReconciliationDifference] = []
        matched = 0
        for line in management_package.line_items:
            key = (line.line_code, management_package.period_label)
            stat = stat_index.get(key)
            if stat is None:
                # No statutory entry for this line — could be GENUINE
                # (line missing from return) or CLASSIFICATION (mapped
                # to different line). Default to UNCLASSIFIED for
                # human review.
                if line.amount_kes != 0:
                    differences.append(ReconciliationDifference(
                        line_code=line.line_code,
                        period_label=management_package.period_label,
                        management_kes=line.amount_kes,
                        statutory_kes=Decimal("0"),
                        variance_kes=line.amount_kes,
                        classification=DifferenceType.UNCLASSIFIED,
                        severity=ValidationSeverity.HIGH,
                        description=(
                            f"line {line.line_code} present in "
                            f"management ({line.amount_kes}) but "
                            f"absent from statutory return"),
                        framework_refs=("ENH-248 §recon",)))
                continue
            variance = line.amount_kes - stat.amount_kes
            if abs(variance) <= self.RECON_TOLERANCE_KES:
                matched += 1
                continue

            # Classify the variance. Simple heuristic: if the
            # variance is < 5% of the larger figure, lean TIMING;
            # otherwise GENUINE. CLASSIFICATION needs cross-line
            # analysis which we don't do here — flag as
            # UNCLASSIFIED and let the cockpit's human user decide.
            larger = max(
                abs(line.amount_kes), abs(stat.amount_kes))
            if (larger > 0
                    and abs(variance) / larger < Decimal("0.05")):
                cls = DifferenceType.TIMING
                sev = ValidationSeverity.LOW
            else:
                cls = DifferenceType.GENUINE
                sev = ValidationSeverity.MEDIUM
            differences.append(ReconciliationDifference(
                line_code=line.line_code,
                period_label=management_package.period_label,
                management_kes=line.amount_kes,
                statutory_kes=stat.amount_kes,
                variance_kes=variance,
                classification=cls,
                severity=sev,
                description=(
                    f"line {line.line_code} variance {variance} "
                    f"between management and statutory"),
                framework_refs=("ENH-248 §recon",)))

        # Statutory lines without management counterpart — also
        # surface
        mgmt_codes = {
            l.line_code for l in management_package.line_items}
        for s in statutory_records:
            if (s.line_code in mgmt_codes
                    or s.period_label
                    != management_package.period_label):
                continue
            if s.amount_kes == 0:
                continue
            differences.append(ReconciliationDifference(
                line_code=s.line_code,
                period_label=s.period_label,
                management_kes=Decimal("0"),
                statutory_kes=s.amount_kes,
                variance_kes=-s.amount_kes,
                classification=DifferenceType.UNCLASSIFIED,
                severity=ValidationSeverity.HIGH,
                description=(
                    f"line {s.line_code} present in statutory "
                    f"({s.amount_kes}) but absent from "
                    f"management"),
                framework_refs=("ENH-248 §recon",)))

        by_class: Dict[str, int] = {
            d.value: 0 for d in DifferenceType}
        for diff in differences:
            by_class[diff.classification.value] += 1

        return MgmtStatReconResult(
            differences=tuple(differences),
            matched_count=matched,
            by_classification=by_class,
            framework_refs=(
                "ENH-248 §recon",
                "Tolerance: KES 1.00 absolute",
                "Classification: TIMING (< 5% of larger), "
                "GENUINE (≥ 5%), UNCLASSIFIED (missing one side)",
            ))

    # ── Capability 3: completeness ──────────────────────────────────
    def validate_completeness(
        self,
        package: ReportPackage,
        template: ReportTemplate,
    ) -> CompletenessReport:
        """Check no required line missing or zero, no unmapped
        categories."""
        if package.template_id != template.template_id:
            raise ValueError(
                "package and template must reference same "
                "template_id")
        findings: List[CompletenessFinding] = []
        package_lines = {
            l.line_code: l for l in package.line_items}
        required_count = 0
        populated_count = 0
        for spec in template.line_specs:
            if spec.required:
                required_count += 1
            line = package_lines.get(spec.line_code)
            if line is None:
                findings.append(CompletenessFinding(
                    issue=CompletenessIssue.MISSING_LINE_ITEM,
                    line_code=spec.line_code,
                    description=(
                        f"required line {spec.line_code} "
                        f"({spec.line_name}) missing from package"),
                    severity=ValidationSeverity.HIGH))
                continue
            if line.amount_kes != 0:
                populated_count += 1
            elif spec.required:
                findings.append(CompletenessFinding(
                    issue=(
                        CompletenessIssue
                        .ZERO_AMOUNT_REQUIRED_LINE),
                    line_code=spec.line_code,
                    description=(
                        f"required line {spec.line_code} populated "
                        f"with zero amount — verify this is "
                        f"intentional"),
                    severity=ValidationSeverity.MEDIUM))
        if package.unmapped_record_count > 0:
            findings.append(CompletenessFinding(
                issue=CompletenessIssue.UNMAPPED_CATEGORY,
                line_code="<unmapped>",
                description=(
                    f"{package.unmapped_record_count} records "
                    f"with categories "
                    f"{list(package.unmapped_categories)} not "
                    f"mapped to any line — extend template or "
                    f"investigate vocabulary drift"),
                severity=ValidationSeverity.HIGH))

        return CompletenessReport(
            findings=tuple(findings),
            required_lines=required_count,
            populated_lines=populated_count,
            unmapped_categories_count=len(
                package.unmapped_categories))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _default_template():
    return ReportTemplate(
        template_id="CBK-REV-Q1-2026",
        regulator=Regulator.CBK,
        period_label="2026-Q1",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        line_specs=(
            ReportLineSpec(
                line_code="L-INT",
                line_name="Interest income",
                revenue_categories=frozenset({"INTEREST_INCOME"}),
                required=True),
            ReportLineSpec(
                line_code="L-FEE",
                line_name="Fee income",
                revenue_categories=frozenset(
                    {"FEE_INCOME", "COMMISSION_INCOME"}),
                required=True),
            ReportLineSpec(
                line_code="L-FX",
                line_name="FX trading income",
                revenue_categories=frozenset(
                    {"FX_INCOME", "TRADING_INCOME"}),
                required=False),
        ))


def _r(rid, day, amt, cat, month=2):
    return RevenueRecord(
        record_id=rid, source_system="CBS",
        posting_date=date(2026, month, day),
        amount_kes=Decimal(str(amt)),
        revenue_category=cat,
        branch_code="NRB-01")


def _test_line_spec_validates_non_empty_categories():
    try:
        ReportLineSpec(
            line_code="L1", line_name="x",
            revenue_categories=frozenset())
        assert False
    except ValueError:
        pass


def _test_template_validates_unique_codes():
    try:
        ReportTemplate(
            template_id="T", regulator=Regulator.CBK,
            period_label="P", period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            line_specs=(
                ReportLineSpec(
                    line_code="DUP", line_name="x",
                    revenue_categories=frozenset({"A"})),
                ReportLineSpec(
                    line_code="DUP", line_name="y",
                    revenue_categories=frozenset({"B"})),
            ))
        assert False
    except ValueError:
        pass


def _test_template_validates_period_order():
    try:
        ReportTemplate(
            template_id="T", regulator=Regulator.CBK,
            period_label="P",
            period_start=date(2026, 3, 31),
            period_end=date(2026, 1, 1),
            line_specs=(
                ReportLineSpec(
                    line_code="L1", line_name="x",
                    revenue_categories=frozenset({"A"})),))
        assert False
    except ValueError:
        pass


def _test_generate_report_aggregates_correctly():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 100000, "INTEREST_INCOME"),
        _r("r2", 10, 200000, "INTEREST_INCOME"),
        _r("r3", 15, 50000, "FEE_INCOME"),
        _r("r4", 20, 25000, "COMMISSION_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    int_line = next(
        l for l in pkg.line_items if l.line_code == "L-INT")
    fee_line = next(
        l for l in pkg.line_items if l.line_code == "L-FEE")
    assert int_line.amount_kes == Decimal("300000")
    assert fee_line.amount_kes == Decimal("75000")
    assert pkg.total_kes == Decimal("375000")


def _test_generate_excludes_outside_period():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 100000, "INTEREST_INCOME"),  # Feb — in
        _r("r2", 5, 200000, "INTEREST_INCOME", month=4),  # Apr — out
    )
    pkg = eng.generate_report(template, records)
    int_line = next(
        l for l in pkg.line_items if l.line_code == "L-INT")
    assert int_line.amount_kes == Decimal("100000")


def _test_unmapped_categories_surfaced():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 100000, "INTEREST_INCOME"),
        _r("r2", 10, 50000, "OTHER_INCOME"),  # not mapped
    )
    pkg = eng.generate_report(template, records)
    assert "OTHER_INCOME" in pkg.unmapped_categories
    assert pkg.unmapped_record_count == 1


def _test_recon_clean_match():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 100000, "INTEREST_INCOME"),
        _r("r2", 10, 50000, "FEE_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    statutory = (
        StatutoryReportRecord(
            line_code="L-INT", period_label="2026-Q1",
            amount_kes=Decimal("100000"),
            submitted_date=date(2026, 4, 30)),
        StatutoryReportRecord(
            line_code="L-FEE", period_label="2026-Q1",
            amount_kes=Decimal("50000"),
            submitted_date=date(2026, 4, 30)),
        StatutoryReportRecord(
            line_code="L-FX", period_label="2026-Q1",
            amount_kes=Decimal("0"),
            submitted_date=date(2026, 4, 30)),
    )
    result = eng.reconcile_management_vs_statutory(pkg, statutory)
    assert result.matched_count == 3
    assert len(result.differences) == 0


def _test_recon_timing_classified():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 1000000, "INTEREST_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    # Statutory off by 0.5% — within 5% TIMING heuristic
    statutory = (
        StatutoryReportRecord(
            line_code="L-INT", period_label="2026-Q1",
            amount_kes=Decimal("1005000"),
            submitted_date=date(2026, 4, 30)),
    )
    result = eng.reconcile_management_vs_statutory(pkg, statutory)
    int_diff = next(
        d for d in result.differences if d.line_code == "L-INT")
    assert int_diff.classification == DifferenceType.TIMING


def _test_recon_genuine_classified():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 1000000, "INTEREST_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    # Statutory off by 50% — well above 5% TIMING heuristic
    statutory = (
        StatutoryReportRecord(
            line_code="L-INT", period_label="2026-Q1",
            amount_kes=Decimal("500000"),
            submitted_date=date(2026, 4, 30)),
    )
    result = eng.reconcile_management_vs_statutory(pkg, statutory)
    int_diff = next(
        d for d in result.differences if d.line_code == "L-INT")
    assert int_diff.classification == DifferenceType.GENUINE
    assert int_diff.severity == ValidationSeverity.MEDIUM


def _test_recon_missing_in_statutory():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 1000000, "INTEREST_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    result = eng.reconcile_management_vs_statutory(pkg, ())
    int_diff = next(
        d for d in result.differences if d.line_code == "L-INT")
    assert int_diff.classification == DifferenceType.UNCLASSIFIED
    assert int_diff.severity == ValidationSeverity.HIGH


def _test_recon_extra_in_statutory():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = ()
    pkg = eng.generate_report(template, records)
    statutory = (
        StatutoryReportRecord(
            line_code="L-EXTRA", period_label="2026-Q1",
            amount_kes=Decimal("500000"),
            submitted_date=date(2026, 4, 30)),
    )
    result = eng.reconcile_management_vs_statutory(
        pkg, statutory)
    extra = next(
        (d for d in result.differences
         if d.line_code == "L-EXTRA"), None)
    assert extra is not None
    assert extra.management_kes == Decimal("0")
    assert extra.statutory_kes == Decimal("500000")


def _test_completeness_required_lines():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    # Only fill INT, leave FEE empty
    records = (
        _r("r1", 5, 100000, "INTEREST_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    rep = eng.validate_completeness(pkg, template)
    # FEE is required and zero → finding
    fee_findings = [
        f for f in rep.findings
        if f.line_code == "L-FEE"]
    assert len(fee_findings) == 1


def _test_completeness_unmapped_finding():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r1", 5, 100000, "INTEREST_INCOME"),
        _r("r2", 10, 50000, "FEE_INCOME"),
        _r("r3", 15, 25000, "OTHER_INCOME"),  # unmapped
    )
    pkg = eng.generate_report(template, records)
    rep = eng.validate_completeness(pkg, template)
    unmapped = [
        f for f in rep.findings
        if f.issue == CompletenessIssue.UNMAPPED_CATEGORY]
    assert len(unmapped) == 1


def _test_completeness_template_id_mismatch():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    other_template = ReportTemplate(
        template_id="OTHER",
        regulator=Regulator.CBK,
        period_label="2026-Q1",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        line_specs=template.line_specs)
    pkg = eng.generate_report(template, ())
    try:
        eng.validate_completeness(pkg, other_template)
        assert False
    except ValueError:
        pass


def _test_full_provenance_on_line_item():
    eng = RegulatoryRevenueReportingEngine()
    template = _default_template()
    records = (
        _r("r-a", 5, 100000, "INTEREST_INCOME"),
        _r("r-b", 10, 200000, "INTEREST_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    int_line = next(
        l for l in pkg.line_items if l.line_code == "L-INT")
    assert int_line.record_count == 2
    assert "r-a" in int_line.contributing_record_ids
    assert "r-b" in int_line.contributing_record_ids
    assert "INTEREST_INCOME" in int_line.revenue_categories


def self_test() -> None:
    tests = [
        _test_line_spec_validates_non_empty_categories,
        _test_template_validates_unique_codes,
        _test_template_validates_period_order,
        _test_generate_report_aggregates_correctly,
        _test_generate_excludes_outside_period,
        _test_unmapped_categories_surfaced,
        _test_recon_clean_match,
        _test_recon_timing_classified,
        _test_recon_genuine_classified,
        _test_recon_missing_in_statutory,
        _test_recon_extra_in_statutory,
        _test_completeness_required_lines,
        _test_completeness_unmapped_finding,
        _test_completeness_template_id_mismatch,
        _test_full_provenance_on_line_item,
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
            f"✗ regulatory_revenue_reporting self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ regulatory_revenue_reporting self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

"""utils/revenue_validation.py — v10.50: Validation Agents (Data Integrity).

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-241 — Validation Agents (Data Integrity)                           ║
║  Cat B — revenue_assurance arc opens                                    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Foundational diagnostic engine for revenue-data integrity. Four        ║
║  agent-style validation routines run independently or via the           ║
║  orchestrator method:                                                    ║
║                                                                          ║
║    1. SCHEMA validation       — does each record match canonical        ║
║                                  schema? (types, required fields,       ║
║                                  monetary positivity, date sanity)      ║
║    2. COMPLETENESS check      — are all expected records present in     ║
║                                  the period? (missing branches,         ║
║                                  missing days, missing product lines)   ║
║    3. CROSS-SOURCE reconciliation — do source-A and source-B totals     ║
║                                  match within a tolerance band?         ║
║                                  (CBS vs GL, GL vs regulatory return)   ║
║    4. STATISTICAL anomaly     — z-score outliers on amount within a     ║
║                                  series, surfaced for investigation     ║
║                                  (NOT auto-flagged as fraud — that is   ║
║                                  ENH-242's job; this is the upstream    ║
║                                  data-quality screen)                   ║
║                                                                          ║
║  Per Rule 1, every ValidationFinding surfaces:                          ║
║    finding_id + severity + category + record_id_or_batch_id +           ║
║    description + expected + observed + framework_refs                   ║
║                                                                          ║
║  Per Rule 7, engine is computational only — never auto-corrects         ║
║  records, never auto-writes to source systems, never auto-closes        ║
║  findings, never silently drops invalid records. Output feeds the       ║
║  ENH-243 Revenue Agentic Orchestrator (future) and downstream           ║
║  investigation workflow.                                                 ║
║                                                                          ║
║  The four "agents" are class methods, not autonomous threads — the      ║
║  design pattern matches treasury_agents.py (ENH-240), where             ║
║  Recommendation objects are produced but human approval gates           ║
║  every action. This module produces ValidationFindings; humans          ║
║  triage them.                                                            ║
║                                                                          ║
║  Pure stdlib (Decimal + statistics + frozen dataclasses + enums).       ║
║                                                                          ║
║  Composes with:                                                          ║
║    - reconciliation_realtime (Standard #181-#190 — multi-source         ║
║      ingestion; this engine is the integrity-validation layer above)    ║
║    - regulatory_reporting (revenue figures must reconcile end-to-end)   ║
║    - ENH-242 anomaly_agents (downstream — ML-based pattern detection)   ║
║    - ENH-243 revenue_orchestrator (downstream — orchestration layer)    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "RevenueValidationEngine implements ENH-241 data integrity "
    "agents. Pure stdlib (Decimal + statistics + dataclasses). "
    "Per Rule 1, every ValidationFinding surfaces all inputs + "
    "intermediates + outputs + framework refs. Per Rule 7, engine "
    "is diagnostic only — never auto-corrects, never auto-writes "
    "to source systems, never auto-closes findings. The four "
    "validation routines (schema / completeness / reconciliation / "
    "anomaly) are class methods, not autonomous threads — same "
    "design pattern as treasury_agents.py (ENH-240) where "
    "Recommendation objects are produced but human approval "
    "gates every action."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class ValidationSeverity(Enum):
    """Finding severity for triage prioritisation."""
    CRITICAL = "CRITICAL"   # data corruption — block downstream
    HIGH = "HIGH"           # material discrepancy — investigate now
    MEDIUM = "MEDIUM"       # potential issue — investigate soon
    LOW = "LOW"             # minor / advisory
    INFO = "INFO"           # passed checks — surfaced for audit trail


class ValidationCategory(Enum):
    """The four validation-agent families."""
    SCHEMA = "SCHEMA"
    COMPLETENESS = "COMPLETENESS"
    RECONCILIATION = "RECONCILIATION"
    ANOMALY = "ANOMALY"


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RevenueRecord:
    """Canonical revenue record schema. Sources translate to this
    shape before the validation engine runs."""
    record_id: str
    source_system: str               # "CBS", "GL", "BILLING", etc.
    posting_date: date
    amount_kes: Decimal
    revenue_category: str            # "FEE_INCOME", "INTEREST", etc.
    branch_code: str = ""
    product_code: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("record_id must be non-empty")
        if not self.source_system:
            raise ValueError("source_system must be non-empty")


@dataclass(frozen=True)
class CrossSourceTotal:
    """Aggregate from one source for cross-source reconciliation."""
    source_system: str
    period: str                      # e.g. "2026-04" / "2026-Q1"
    revenue_category: str
    total_kes: Decimal
    record_count: int
    notes: str = ""


@dataclass(frozen=True)
class ExpectedCount:
    """Expected record count for a (period, dimension) cell —
    drives completeness checks. E.g. "branch X should post 30 days
    of fee income in April 2026"."""
    period: str
    dimension_key: str               # e.g. "branch=NRB-01"
    revenue_category: str
    expected_count: int

    def __post_init__(self) -> None:
        if self.expected_count < 0:
            raise ValueError("expected_count must be ≥ 0")


@dataclass(frozen=True)
class ValidationFinding:
    """One finding from the engine. Per Rule 1, full provenance."""
    finding_id: str
    severity: ValidationSeverity
    category: ValidationCategory
    record_id_or_batch_id: str
    description: str
    expected: str
    observed: str
    source_system: str = ""
    posting_date: Optional[date] = None
    framework_refs: Tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ValidationReport:
    """Summary of findings across all four agent runs."""
    findings: Tuple[ValidationFinding, ...]
    schema_count: int
    completeness_count: int
    reconciliation_count: int
    anomaly_count: int
    by_severity: Dict[str, int]
    records_validated: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class RevenueValidationEngine:
    """Diagnostic data-integrity engine for revenue records.

    Per Rule 7, the engine never:
      - mutates input records
      - writes to source systems
      - auto-closes findings
      - silently drops records

    Per Rule 1, every finding carries enough provenance for a human
    investigator to reproduce the issue: the record IDs involved,
    the expected vs observed values, the source systems, the
    framework refs.

    The four "agents" are independent methods; callers may invoke
    them in any combination. `validate_all` orchestrates the four
    in sequence and produces a unified ValidationReport.
    """

    # Allowed revenue categories — typed enum would be too rigid for
    # a multi-bank platform; a tuple constant is the contract.
    ALLOWED_REVENUE_CATEGORIES: Tuple[str, ...] = (
        "INTEREST_INCOME", "FEE_INCOME", "COMMISSION_INCOME",
        "FX_INCOME", "TRADING_INCOME", "OTHER_INCOME")

    # Default tolerance for cross-source reconciliation (5 bp).
    DEFAULT_TOLERANCE_PCT: Decimal = Decimal("0.05")

    # Default z-score threshold for statistical anomaly screening.
    DEFAULT_Z_THRESHOLD: float = 3.0

    # Future date threshold — postings dated more than this many days
    # ahead are flagged.
    FUTURE_DATE_TOLERANCE_DAYS: int = 1

    # ── Agent 1: SCHEMA validation ────────────────────────────────────
    def validate_schema(
        self,
        records: Sequence[RevenueRecord],
        as_of: Optional[date] = None,
    ) -> Tuple[ValidationFinding, ...]:
        """Schema-level checks per record:
          - amount_kes must be > 0 (revenue is positive — refunds /
            reversals belong in a separate "REVERSAL" feed)
          - revenue_category must be in ALLOWED_REVENUE_CATEGORIES
          - posting_date must not be in the future beyond tolerance
        """
        findings: List[ValidationFinding] = []
        as_of = as_of or date.today()
        future_cutoff_ord = (
            as_of.toordinal() + self.FUTURE_DATE_TOLERANCE_DAYS)

        for r in records:
            # Amount positivity
            if r.amount_kes <= 0:
                findings.append(ValidationFinding(
                    finding_id=f"SCHEMA-AMT-{r.record_id}",
                    severity=ValidationSeverity.CRITICAL,
                    category=ValidationCategory.SCHEMA,
                    record_id_or_batch_id=r.record_id,
                    description=(
                        "amount_kes must be positive for revenue "
                        "records (refunds/reversals belong in "
                        "REVERSAL feed)"),
                    expected="amount_kes > 0",
                    observed=str(r.amount_kes),
                    source_system=r.source_system,
                    posting_date=r.posting_date,
                    framework_refs=(
                        "ENH-241 §schema",
                        "Reconciliation discipline §completeness")))

            # Revenue category vocabulary
            if r.revenue_category not in (
                    self.ALLOWED_REVENUE_CATEGORIES):
                findings.append(ValidationFinding(
                    finding_id=f"SCHEMA-CAT-{r.record_id}",
                    severity=ValidationSeverity.HIGH,
                    category=ValidationCategory.SCHEMA,
                    record_id_or_batch_id=r.record_id,
                    description=(
                        "revenue_category not in canonical "
                        "vocabulary — record cannot be aggregated"),
                    expected=" / ".join(
                        self.ALLOWED_REVENUE_CATEGORIES),
                    observed=r.revenue_category,
                    source_system=r.source_system,
                    posting_date=r.posting_date,
                    framework_refs=(
                        "ENH-241 §schema",)))

            # Future-date sanity
            if r.posting_date.toordinal() > future_cutoff_ord:
                days_ahead = (
                    r.posting_date.toordinal() - as_of.toordinal())
                findings.append(ValidationFinding(
                    finding_id=f"SCHEMA-DATE-{r.record_id}",
                    severity=ValidationSeverity.HIGH,
                    category=ValidationCategory.SCHEMA,
                    record_id_or_batch_id=r.record_id,
                    description=(
                        "posting_date is in the future beyond "
                        "tolerance — likely data entry error"),
                    expected=(
                        f"≤ {self.FUTURE_DATE_TOLERANCE_DAYS} day "
                        f"ahead of {as_of.isoformat()}"),
                    observed=(
                        f"{r.posting_date.isoformat()} "
                        f"(+{days_ahead} days)"),
                    source_system=r.source_system,
                    posting_date=r.posting_date,
                    framework_refs=(
                        "ENH-241 §schema",)))

        return tuple(findings)

    # ── Agent 2: COMPLETENESS check ───────────────────────────────────
    def check_completeness(
        self,
        records: Sequence[RevenueRecord],
        expected_counts: Sequence[ExpectedCount],
        period_extractor=None,
    ) -> Tuple[ValidationFinding, ...]:
        """Completeness checks against an expected-counts manifest.

        For each ExpectedCount, count actual records matching the
        (period, dimension_key, revenue_category) tuple and compare.
        Missing or excess records both surface as findings.

        period_extractor: callable(record) -> period_str. Default is
        YYYY-MM from posting_date.
        """
        if period_extractor is None:
            period_extractor = lambda r: r.posting_date.strftime("%Y-%m")

        # Index actual records
        actual: Dict[Tuple[str, str, str], int] = {}
        for r in records:
            period = period_extractor(r)
            # The dimension_key in ExpectedCount is something like
            # "branch=X" or "product=Y". We support both.
            for key in (
                    f"branch={r.branch_code}",
                    f"product={r.product_code}"):
                bucket = (period, key, r.revenue_category)
                actual[bucket] = actual.get(bucket, 0) + 1

        findings: List[ValidationFinding] = []
        for ec in expected_counts:
            bucket = (
                ec.period, ec.dimension_key, ec.revenue_category)
            obs = actual.get(bucket, 0)
            if obs == ec.expected_count:
                continue
            severity = (
                ValidationSeverity.HIGH if obs == 0
                else ValidationSeverity.MEDIUM)
            description = (
                "no records found — completeness gap"
                if obs == 0
                else "record count mismatch")
            findings.append(ValidationFinding(
                finding_id=(
                    f"COMPLETE-{ec.period}-"
                    f"{ec.dimension_key.replace('=','-')}-"
                    f"{ec.revenue_category}"),
                severity=severity,
                category=ValidationCategory.COMPLETENESS,
                record_id_or_batch_id=(
                    f"{ec.period}|{ec.dimension_key}|"
                    f"{ec.revenue_category}"),
                description=description,
                expected=f"count = {ec.expected_count}",
                observed=f"count = {obs}",
                framework_refs=(
                    "ENH-241 §completeness",
                    "CBK PG/03 revenue completeness")))

        return tuple(findings)

    # ── Agent 3: CROSS-SOURCE reconciliation ──────────────────────────
    def reconcile_sources(
        self,
        totals_a: Sequence[CrossSourceTotal],
        totals_b: Sequence[CrossSourceTotal],
        tolerance_pct: Optional[Decimal] = None,
    ) -> Tuple[ValidationFinding, ...]:
        """Pairwise reconcile totals on (period, revenue_category)
        between two sources. Tolerance band is `tolerance_pct` of the
        larger total. Findings:
          - matched: both sides present, within tolerance → no finding
          - mismatch_amount: both present, outside tolerance → MEDIUM
          - mismatch_count: same total but different record counts
            → LOW (could indicate netting or grouping difference)
          - missing_a: present in B but not A → HIGH
          - missing_b: present in A but not B → HIGH
        """
        tol = (
            tolerance_pct
            if tolerance_pct is not None
            else self.DEFAULT_TOLERANCE_PCT)
        if tol < 0:
            raise ValueError("tolerance_pct must be ≥ 0")

        idx_a: Dict[Tuple[str, str], CrossSourceTotal] = {
            (t.period, t.revenue_category): t for t in totals_a}
        idx_b: Dict[Tuple[str, str], CrossSourceTotal] = {
            (t.period, t.revenue_category): t for t in totals_b}

        findings: List[ValidationFinding] = []
        all_keys = set(idx_a.keys()) | set(idx_b.keys())
        for key in sorted(all_keys):
            a = idx_a.get(key)
            b = idx_b.get(key)
            period, cat = key
            if a is None and b is not None:
                findings.append(ValidationFinding(
                    finding_id=f"RECON-MISS-A-{period}-{cat}",
                    severity=ValidationSeverity.HIGH,
                    category=ValidationCategory.RECONCILIATION,
                    record_id_or_batch_id=f"{period}|{cat}",
                    description=(
                        f"{cat} present in {b.source_system} but "
                        f"missing from source A"),
                    expected=f"{b.source_system} total reflected",
                    observed=(
                        f"{b.source_system} = "
                        f"{b.total_kes}; A = absent"),
                    framework_refs=(
                        "ENH-241 §reconciliation",
                        "Reconciliation discipline §closure")))
                continue
            if b is None and a is not None:
                findings.append(ValidationFinding(
                    finding_id=f"RECON-MISS-B-{period}-{cat}",
                    severity=ValidationSeverity.HIGH,
                    category=ValidationCategory.RECONCILIATION,
                    record_id_or_batch_id=f"{period}|{cat}",
                    description=(
                        f"{cat} present in {a.source_system} but "
                        f"missing from source B"),
                    expected=f"{a.source_system} total reflected",
                    observed=(
                        f"{a.source_system} = "
                        f"{a.total_kes}; B = absent"),
                    framework_refs=(
                        "ENH-241 §reconciliation",)))
                continue
            # Both present
            assert a is not None and b is not None
            larger = max(a.total_kes, b.total_kes)
            diff = abs(a.total_kes - b.total_kes)
            tol_kes = larger * tol
            if diff > tol_kes:
                findings.append(ValidationFinding(
                    finding_id=f"RECON-AMT-{period}-{cat}",
                    severity=ValidationSeverity.MEDIUM,
                    category=ValidationCategory.RECONCILIATION,
                    record_id_or_batch_id=f"{period}|{cat}",
                    description=(
                        f"{a.source_system} vs {b.source_system} "
                        f"reconciliation outside tolerance"),
                    expected=(
                        f"|A - B| ≤ {tol_kes} "
                        f"({float(tol) * 100:.2f}% of larger)"),
                    observed=(
                        f"A = {a.total_kes}; B = {b.total_kes}; "
                        f"|diff| = {diff}"),
                    framework_refs=(
                        "ENH-241 §reconciliation",
                        "Reconciliation discipline §closure")))
            elif a.record_count != b.record_count:
                findings.append(ValidationFinding(
                    finding_id=f"RECON-COUNT-{period}-{cat}",
                    severity=ValidationSeverity.LOW,
                    category=ValidationCategory.RECONCILIATION,
                    record_id_or_batch_id=f"{period}|{cat}",
                    description=(
                        "totals match within tolerance but record "
                        "counts differ — possible netting or "
                        "grouping difference"),
                    expected=(
                        f"counts equal across "
                        f"{a.source_system} and {b.source_system}"),
                    observed=(
                        f"{a.source_system} count = "
                        f"{a.record_count}; "
                        f"{b.source_system} count = "
                        f"{b.record_count}"),
                    framework_refs=(
                        "ENH-241 §reconciliation",)))

        return tuple(findings)

    # ── Agent 4: ANOMALY (statistical screen) ─────────────────────────
    def detect_anomalies(
        self,
        records: Sequence[RevenueRecord],
        z_threshold: Optional[float] = None,
        min_sample_size: int = 10,
    ) -> Tuple[ValidationFinding, ...]:
        """Z-score outlier screen on amount within (revenue_category,
        branch_code) groups. Outliers above ``z_threshold`` standard
        deviations from the group mean are surfaced as findings.

        This is the upstream data-quality screen; ENH-242 will add
        ML-based pattern detection downstream. Sample groups smaller
        than ``min_sample_size`` are skipped (z-score is not
        meaningful below this threshold).
        """
        z = (
            z_threshold
            if z_threshold is not None
            else self.DEFAULT_Z_THRESHOLD)
        if z <= 0:
            raise ValueError("z_threshold must be > 0")
        if min_sample_size < 3:
            raise ValueError("min_sample_size must be ≥ 3")

        # Group by (revenue_category, branch_code)
        groups: Dict[
            Tuple[str, str], List[RevenueRecord]] = {}
        for r in records:
            key = (r.revenue_category, r.branch_code)
            groups.setdefault(key, []).append(r)

        findings: List[ValidationFinding] = []
        for (cat, branch), group in sorted(groups.items()):
            if len(group) < min_sample_size:
                continue
            amounts = [float(r.amount_kes) for r in group]
            mean = statistics.fmean(amounts)
            try:
                stdev = statistics.stdev(amounts)
            except statistics.StatisticsError:
                continue
            if stdev == 0:
                continue
            for r in group:
                z_score = (float(r.amount_kes) - mean) / stdev
                if abs(z_score) >= z:
                    findings.append(ValidationFinding(
                        finding_id=(
                            f"ANOMALY-{cat}-{branch}-"
                            f"{r.record_id}"),
                        severity=(
                            ValidationSeverity.MEDIUM
                            if abs(z_score) < z + 2
                            else ValidationSeverity.HIGH),
                        category=ValidationCategory.ANOMALY,
                        record_id_or_batch_id=r.record_id,
                        description=(
                            f"amount {r.amount_kes} is "
                            f"{z_score:+.2f}σ from group mean "
                            f"(category={cat}, "
                            f"branch={branch or 'n/a'}, "
                            f"n={len(group)})"),
                        expected=(
                            f"|z| < {z}; mean = {mean:,.2f}, "
                            f"stdev = {stdev:,.2f}"),
                        observed=(
                            f"amount = {r.amount_kes}; "
                            f"z = {z_score:+.2f}"),
                        source_system=r.source_system,
                        posting_date=r.posting_date,
                        framework_refs=(
                            "ENH-241 §anomaly",
                            "Statistical screening — z-score")))

        return tuple(findings)

    # ── Public API: orchestrator ──────────────────────────────────────
    def validate_all(
        self,
        records: Sequence[RevenueRecord],
        expected_counts: Sequence[ExpectedCount] = (),
        totals_a: Sequence[CrossSourceTotal] = (),
        totals_b: Sequence[CrossSourceTotal] = (),
        tolerance_pct: Optional[Decimal] = None,
        z_threshold: Optional[float] = None,
        as_of: Optional[date] = None,
    ) -> ValidationReport:
        """Run all four agents and produce a unified report. Inputs
        for any agent may be empty — the corresponding finding count
        will be 0."""
        schema = self.validate_schema(records, as_of=as_of)
        completeness = (
            self.check_completeness(records, expected_counts)
            if expected_counts else ())
        recon = (
            self.reconcile_sources(
                totals_a, totals_b, tolerance_pct=tolerance_pct)
            if (totals_a or totals_b) else ())
        anomaly = (
            self.detect_anomalies(records, z_threshold=z_threshold)
            if records else ())
        all_findings = schema + completeness + recon + anomaly

        sev_counts: Dict[str, int] = {
            s.value: 0 for s in ValidationSeverity}
        for f in all_findings:
            sev_counts[f.severity.value] += 1

        return ValidationReport(
            findings=all_findings,
            schema_count=len(schema),
            completeness_count=len(completeness),
            reconciliation_count=len(recon),
            anomaly_count=len(anomaly),
            by_severity=sev_counts,
            records_validated=len(records),
            framework_refs=(
                "ENH-241 §schema + §completeness + §reconciliation + "
                "§anomaly",
                "CBK PG/03 revenue completeness",
                "Reconciliation discipline §closure",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_record_validates_non_empty_id():
    try:
        RevenueRecord(
            record_id="", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("100"),
            revenue_category="FEE_INCOME")
        assert False
    except ValueError:
        pass


def _test_expected_count_validates_non_negative():
    try:
        ExpectedCount(
            period="2026-04", dimension_key="branch=X",
            revenue_category="FEE_INCOME", expected_count=-1)
        assert False
    except ValueError:
        pass


def _test_schema_clean_records_no_findings():
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r1", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("1000"),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01"),
        RevenueRecord(
            record_id="r2", source_system="CBS",
            posting_date=date(2026, 4, 2),
            amount_kes=Decimal("2000"),
            revenue_category="INTEREST_INCOME",
            branch_code="NRB-01"),
    )
    findings = eng.validate_schema(records, as_of=date(2026, 4, 30))
    assert len(findings) == 0


def _test_schema_negative_amount_critical_finding():
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r-neg", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("-500"),
            revenue_category="FEE_INCOME"),
    )
    findings = eng.validate_schema(records, as_of=date(2026, 4, 30))
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.CRITICAL
    assert findings[0].category == ValidationCategory.SCHEMA


def _test_schema_unknown_category_high_finding():
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r1", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("1000"),
            revenue_category="MYSTERY_REVENUE"),
    )
    findings = eng.validate_schema(records, as_of=date(2026, 4, 30))
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.HIGH
    assert "vocabulary" in findings[0].description


def _test_schema_future_date_flagged():
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r-future", source_system="CBS",
            posting_date=date(2027, 1, 1),
            amount_kes=Decimal("1000"),
            revenue_category="FEE_INCOME"),
    )
    findings = eng.validate_schema(records, as_of=date(2026, 5, 1))
    assert len(findings) == 1
    assert findings[0].category == ValidationCategory.SCHEMA
    assert "future" in findings[0].description.lower()


def _test_completeness_missing_period_flagged():
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r1", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("1000"),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01"),
    )
    expected = (
        ExpectedCount(
            period="2026-04", dimension_key="branch=NRB-02",
            revenue_category="FEE_INCOME", expected_count=30),
    )
    findings = eng.check_completeness(records, expected)
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.HIGH
    assert "no records" in findings[0].description


def _test_completeness_count_mismatch_medium():
    eng = RevenueValidationEngine()
    records = tuple(
        RevenueRecord(
            record_id=f"r{i}", source_system="CBS",
            posting_date=date(2026, 4, i),
            amount_kes=Decimal("1000"),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01")
        for i in range(1, 11))
    expected = (
        ExpectedCount(
            period="2026-04", dimension_key="branch=NRB-01",
            revenue_category="FEE_INCOME", expected_count=30),
    )
    findings = eng.check_completeness(records, expected)
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.MEDIUM
    assert "mismatch" in findings[0].description


def _test_reconciliation_within_tolerance_no_finding():
    eng = RevenueValidationEngine()
    a = (CrossSourceTotal(
        source_system="CBS", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1000000"), record_count=100),)
    b = (CrossSourceTotal(
        source_system="GL", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1000400"), record_count=100),)
    # Default tolerance 5% — well within
    findings = eng.reconcile_sources(a, b)
    assert len(findings) == 0


def _test_reconciliation_outside_tolerance_medium():
    eng = RevenueValidationEngine()
    a = (CrossSourceTotal(
        source_system="CBS", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1000000"), record_count=100),)
    b = (CrossSourceTotal(
        source_system="GL", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1500000"), record_count=100),)
    # 50% diff — well outside default 5% tolerance
    findings = eng.reconcile_sources(a, b)
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.MEDIUM
    assert findings[0].category == ValidationCategory.RECONCILIATION


def _test_reconciliation_missing_in_one_source_high():
    eng = RevenueValidationEngine()
    a = (CrossSourceTotal(
        source_system="CBS", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1000000"), record_count=100),)
    b = ()
    findings = eng.reconcile_sources(a, b)
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.HIGH


def _test_reconciliation_count_mismatch_low_when_amount_matches():
    eng = RevenueValidationEngine()
    a = (CrossSourceTotal(
        source_system="CBS", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1000000"), record_count=100),)
    b = (CrossSourceTotal(
        source_system="GL", period="2026-04",
        revenue_category="FEE_INCOME",
        total_kes=Decimal("1000000"), record_count=80),)
    findings = eng.reconcile_sources(a, b)
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.LOW
    assert "netting" in findings[0].description.lower() or (
        "grouping" in findings[0].description.lower())


def _test_reconciliation_negative_tolerance_rejected():
    eng = RevenueValidationEngine()
    try:
        eng.reconcile_sources(
            (), (), tolerance_pct=Decimal("-0.01"))
        assert False
    except ValueError:
        pass


def _test_anomaly_skips_small_groups():
    eng = RevenueValidationEngine()
    # Only 3 records — below min_sample_size=10
    records = tuple(
        RevenueRecord(
            record_id=f"r{i}", source_system="CBS",
            posting_date=date(2026, 4, i),
            amount_kes=Decimal("1000") if i < 3 else Decimal("100000"),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01")
        for i in range(1, 4))
    findings = eng.detect_anomalies(records)
    assert len(findings) == 0


def _test_anomaly_detects_outlier():
    eng = RevenueValidationEngine()
    # 10 normal records around 1000, 1 outlier at 100000
    normal = [
        RevenueRecord(
            record_id=f"r{i}", source_system="CBS",
            posting_date=date(2026, 4, i),
            amount_kes=Decimal(str(1000 + i * 10)),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01")
        for i in range(1, 11)]
    outlier = RevenueRecord(
        record_id="r-out", source_system="CBS",
        posting_date=date(2026, 4, 11),
        amount_kes=Decimal("100000"),
        revenue_category="FEE_INCOME",
        branch_code="NRB-01")
    findings = eng.detect_anomalies(tuple(normal + [outlier]))
    outlier_findings = [
        f for f in findings if f.record_id_or_batch_id == "r-out"]
    assert len(outlier_findings) == 1
    assert outlier_findings[0].category == ValidationCategory.ANOMALY


def _test_anomaly_zero_threshold_rejected():
    eng = RevenueValidationEngine()
    try:
        eng.detect_anomalies((), z_threshold=0.0)
        assert False
    except ValueError:
        pass


def _test_validate_all_orchestrates_and_summarises():
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r-bad", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("-500"),
            revenue_category="FEE_INCOME"),
    )
    report = eng.validate_all(
        records, expected_counts=(), totals_a=(), totals_b=(),
        as_of=date(2026, 4, 30))
    assert isinstance(report, ValidationReport)
    assert report.records_validated == 1
    assert report.schema_count == 1
    assert report.by_severity["CRITICAL"] == 1


def _test_finding_carries_full_provenance():
    """Per Rule 1 — every finding has expected + observed +
    framework refs + record context."""
    eng = RevenueValidationEngine()
    records = (
        RevenueRecord(
            record_id="r-prov", source_system="CBS",
            posting_date=date(2026, 4, 1),
            amount_kes=Decimal("-500"),
            revenue_category="FEE_INCOME"),
    )
    findings = eng.validate_schema(records, as_of=date(2026, 4, 30))
    f = findings[0]
    assert f.finding_id
    assert f.expected
    assert f.observed
    assert len(f.framework_refs) >= 1
    assert f.source_system == "CBS"
    assert f.posting_date == date(2026, 4, 1)


def _test_engine_does_not_mutate_records():
    """Per Rule 7 — engine is diagnostic; never mutates inputs."""
    eng = RevenueValidationEngine()
    r = RevenueRecord(
        record_id="r1", source_system="CBS",
        posting_date=date(2026, 4, 1),
        amount_kes=Decimal("-500"),
        revenue_category="FEE_INCOME")
    eng.validate_schema((r,), as_of=date(2026, 4, 30))
    # Frozen dataclass would raise if mutated — confirm value is
    # unchanged (frozen guarantees this, but we double-check the
    # contract by inspecting the field).
    assert r.amount_kes == Decimal("-500")
    assert r.record_id == "r1"


def self_test() -> None:
    tests = [
        _test_record_validates_non_empty_id,
        _test_expected_count_validates_non_negative,
        _test_schema_clean_records_no_findings,
        _test_schema_negative_amount_critical_finding,
        _test_schema_unknown_category_high_finding,
        _test_schema_future_date_flagged,
        _test_completeness_missing_period_flagged,
        _test_completeness_count_mismatch_medium,
        _test_reconciliation_within_tolerance_no_finding,
        _test_reconciliation_outside_tolerance_medium,
        _test_reconciliation_missing_in_one_source_high,
        _test_reconciliation_count_mismatch_low_when_amount_matches,
        _test_reconciliation_negative_tolerance_rejected,
        _test_anomaly_skips_small_groups,
        _test_anomaly_detects_outlier,
        _test_anomaly_zero_threshold_rejected,
        _test_validate_all_orchestrates_and_summarises,
        _test_finding_carries_full_provenance,
        _test_engine_does_not_mutate_records,
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
            f"✗ revenue_validation self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ revenue_validation self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

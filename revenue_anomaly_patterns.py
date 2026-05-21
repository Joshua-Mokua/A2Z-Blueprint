"""utils/revenue_anomaly_patterns.py — v10.51: Anomaly Agents.

╔════════════════════════════════════════════════════════════════════════╗
║  ENH-242 — Anomaly Agents (Pattern Detection)                           ║
║  Cat B — revenue_assurance arc continuation                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Pattern-detection layer over ENH-241's data-integrity foundation.      ║
║  Where ENH-241 catches "data looks weird" (z-score outliers, schema     ║
║  violations), ENH-242 catches "data follows known revenue-leakage       ║
║  patterns" — duplicate billings, rate-card breaches, commission         ║
║  miscalculation, expired-contract postings, unauthorized fee waivers.   ║
║                                                                          ║
║  Four pattern families (PatternFamily enum):                            ║
║    1. LEAKAGE            — revenue lost through process gaps            ║
║                            (unauthorized waivers, missing recurring     ║
║                            fees, expired-contract billing reversed)     ║
║    2. BILLING_ERROR      — duplicates, missing tax, wrong rate          ║
║    3. COMMISSION_MISCALC — tier-table mismatches, double-commissioning  ║
║    4. RATE_CARD_BREACH   — rate outside contract floor/ceiling band     ║
║                                                                          ║
║  ML-hook pattern (matches utils.credit_risk_scoring discipline):        ║
║    The engine ships deterministic rule-based detectors that work        ║
║    without any model. An optional ml_score_fn callable can be           ║
║    injected; when present, each candidate gets an ML score that         ║
║    surfaces in the finding's meta. When absent, ml_disabled=True is     ║
║    surfaced explicitly per Rule 6 — no silent fallback.                 ║
║                                                                          ║
║  Per Rule 1, every PatternFinding surfaces:                             ║
║    pattern_id + family + severity + record_ids (involved records)       ║
║    + evidence (rule firings) + confidence + ml_score (if ML used)       ║
║    + framework_refs                                                      ║
║                                                                          ║
║  Per Rule 7, engine is computational only — never auto-recovers         ║
║  leaked revenue, never auto-reverses duplicate billings, never          ║
║  auto-corrects rates, never auto-closes findings. Output feeds          ║
║  ENH-243 Revenue Orchestrator (next batch) and downstream               ║
║  investigation workflow.                                                 ║
║                                                                          ║
║  Pure stdlib (Decimal + frozen dataclasses + enums).                    ║
║                                                                          ║
║  Composes with:                                                          ║
║    - revenue_validation (ENH-241 — schema/completeness/recon/anomaly    ║
║      foundation; this engine consumes the same RevenueRecord shape)     ║
║    - ENH-243 revenue_orchestrator (downstream — orchestration)          ║
║    - ENH-244 partner_supplier_reconciliation (parallel — multi-party)   ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from utils.revenue_validation import RevenueRecord, ValidationSeverity

SPEC_DEVIATION_NOTE = (
    "RevenueAnomalyPatternEngine implements ENH-242 pattern "
    "detection. Pure stdlib (Decimal + dataclasses). Per Rule 1, "
    "every PatternFinding surfaces all inputs (record_ids + "
    "evidence) + intermediates (rule firings) + outputs + "
    "framework refs. Per Rule 7, engine is diagnostic only — "
    "never auto-reverses, never auto-corrects rates, never "
    "auto-closes findings. Composes with utils.revenue_validation "
    "(ENH-241) by consuming the same RevenueRecord dataclass. "
    "ML-hook pattern matches utils.credit_risk_scoring (Standard "
    "#53): optional ml_score_fn injectable, surfaces ml_disabled "
    "explicitly when absent — no silent fallback."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class PatternFamily(Enum):
    """High-level pattern families."""
    LEAKAGE = "LEAKAGE"
    BILLING_ERROR = "BILLING_ERROR"
    COMMISSION_MISCALC = "COMMISSION_MISCALC"
    RATE_CARD_BREACH = "RATE_CARD_BREACH"


class PatternId(Enum):
    """Specific patterns the engine detects deterministically."""
    # LEAKAGE family
    UNAUTHORIZED_FEE_WAIVER = "UNAUTHORIZED_FEE_WAIVER"
    EXPIRED_CONTRACT_BILLING = "EXPIRED_CONTRACT_BILLING"
    # BILLING_ERROR family
    DUPLICATE_BILLING = "DUPLICATE_BILLING"
    MISSING_TAX_COMPONENT = "MISSING_TAX_COMPONENT"
    # COMMISSION_MISCALC family
    COMMISSION_OVERPAYMENT = "COMMISSION_OVERPAYMENT"
    COMMISSION_UNDERPAYMENT = "COMMISSION_UNDERPAYMENT"
    # RATE_CARD_BREACH family
    RATE_BELOW_FLOOR = "RATE_BELOW_FLOOR"
    RATE_ABOVE_CEILING = "RATE_ABOVE_CEILING"
    # ML-only — surfaced when ml_score_fn fires above threshold
    ML_FLAGGED_PATTERN = "ML_FLAGGED_PATTERN"


# ════════════════════════════════════════════════════════════════════════
# Auxiliary dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ContractRate:
    """Rate-card contract for a (customer × product) cell. Used by
    rate-card breach detector."""
    contract_id: str
    customer_id: str
    product_code: str
    floor_rate_pct: Decimal      # e.g. Decimal("1.5") = 1.50%
    ceiling_rate_pct: Decimal
    effective_from: date
    effective_to: date

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("contract_id must be non-empty")
        if self.floor_rate_pct < 0:
            raise ValueError("floor_rate_pct must be ≥ 0")
        if self.ceiling_rate_pct < self.floor_rate_pct:
            raise ValueError(
                "ceiling_rate_pct must be ≥ floor_rate_pct")
        if self.effective_to < self.effective_from:
            raise ValueError(
                "effective_to must be ≥ effective_from")


@dataclass(frozen=True)
class RevenueRecordWithContext:
    """Wraps a RevenueRecord with the context needed for pattern
    detection. Caller assembles this from CBS + CRM + commission
    systems before feeding the engine. Optional fields are None
    when the source system does not supply them; detectors skip
    rules that need missing context rather than firing false
    positives."""
    record: RevenueRecord
    customer_id: str = ""
    contract_id: Optional[str] = None
    waiver_flag: bool = False
    waiver_authorization_id: Optional[str] = None
    applied_rate_pct: Optional[Decimal] = None
    expected_tax_kes: Optional[Decimal] = None
    actual_tax_kes: Optional[Decimal] = None


@dataclass(frozen=True)
class CommissionRecord:
    """One commission posting. Used by commission-miscalc detector."""
    commission_id: str
    rm_code: str
    underlying_revenue_kes: Decimal
    paid_commission_kes: Decimal
    expected_commission_kes: Decimal
    posting_date: date
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.commission_id:
            raise ValueError("commission_id must be non-empty")
        if self.underlying_revenue_kes < 0:
            raise ValueError("underlying_revenue_kes must be ≥ 0")
        if self.paid_commission_kes < 0:
            raise ValueError("paid_commission_kes must be ≥ 0")
        if self.expected_commission_kes < 0:
            raise ValueError("expected_commission_kes must be ≥ 0")


@dataclass(frozen=True)
class PatternFinding:
    """One pattern-detection finding. Per Rule 1, full provenance."""
    finding_id: str
    pattern_id: PatternId
    family: PatternFamily
    severity: ValidationSeverity        # reuses ENH-241 enum
    record_ids: Tuple[str, ...]         # the records involved
    description: str
    evidence: str                       # human-readable rule firing
    confidence: Decimal                 # 0..1 — rule-based finds = 1.0
    ml_score: Optional[Decimal] = None  # populated when ML hook fired
    framework_refs: Tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class AnomalyReport:
    """Summary of pattern findings."""
    findings: Tuple[PatternFinding, ...]
    by_family: Dict[str, int]
    by_severity: Dict[str, int]
    records_scanned: int
    contracts_used: int
    commissions_scanned: int
    ml_disabled: bool
    ml_disabled_reason: str
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

# Type alias for the ML score callable (kept loose — the engine just
# expects it returns a Decimal in [0, 1] given a record + context).
MLScoreFn = Callable[
    [RevenueRecordWithContext], Optional[Decimal]]


class RevenueAnomalyPatternEngine:
    """Diagnostic pattern-detection engine for revenue records.

    Per Rule 7, the engine never:
      - auto-recovers leaked revenue
      - auto-reverses duplicate billings
      - auto-corrects rates outside band
      - auto-closes findings
      - silently drops records with insufficient context

    Per Rule 1, every PatternFinding surfaces enough provenance for
    a human investigator to reproduce the finding from the record
    inputs alone.

    Per Rule 6 (honesty / no silent fallback), when the optional
    ML hook is absent, the report's `ml_disabled` flag is True and
    `ml_disabled_reason` is populated — callers cannot mistake
    rule-only output for ML-augmented output.
    """

    # Default ML threshold above which the engine surfaces a finding.
    DEFAULT_ML_THRESHOLD: Decimal = Decimal("0.80")

    # Tolerance for commission match (KES 1 by default — tighter than
    # currency rounding noise but not zero).
    COMMISSION_TOLERANCE_KES: Decimal = Decimal("1.00")

    # Tolerance for tax matching (1% of expected, capped at KES 100).
    TAX_TOLERANCE_PCT: Decimal = Decimal("0.01")
    TAX_TOLERANCE_FLOOR_KES: Decimal = Decimal("100")

    # ── Detector 1: DUPLICATE_BILLING ────────────────────────────────
    def detect_duplicate_billings(
        self,
        records: Sequence[RevenueRecordWithContext],
    ) -> Tuple[PatternFinding, ...]:
        """Group records by (customer_id, amount_kes, posting_date).
        Two or more records sharing all three are flagged as
        duplicate-billing candidates.

        Real production records may legitimately have multiple fees
        on one day; this detector surfaces candidates for human
        triage rather than auto-reversing anything.
        """
        if not records:
            return ()
        buckets: Dict[
            Tuple[str, Decimal, date],
            List[RevenueRecordWithContext]] = {}
        for r in records:
            cust = r.customer_id or "_UNKNOWN_"
            key = (cust, r.record.amount_kes, r.record.posting_date)
            buckets.setdefault(key, []).append(r)

        findings: List[PatternFinding] = []
        for (cust, amt, dt), group in buckets.items():
            if len(group) < 2:
                continue
            ids = tuple(g.record.record_id for g in group)
            findings.append(PatternFinding(
                finding_id=(
                    f"DUP-{cust}-{dt.isoformat()}-"
                    f"{ids[0]}"),
                pattern_id=PatternId.DUPLICATE_BILLING,
                family=PatternFamily.BILLING_ERROR,
                severity=(
                    ValidationSeverity.HIGH if len(group) >= 3
                    else ValidationSeverity.MEDIUM),
                record_ids=ids,
                description=(
                    f"{len(group)} records share customer "
                    f"{cust}, amount {amt}, date "
                    f"{dt.isoformat()} — duplicate-billing "
                    f"candidate"),
                evidence=(
                    f"matched key (customer_id, amount_kes, "
                    f"posting_date) — {len(group)} records"),
                confidence=Decimal("1.0"),
                framework_refs=(
                    "ENH-242 §billing_error",
                    "Revenue assurance — duplicate detection")))
        return tuple(findings)

    # ── Detector 2: UNAUTHORIZED_FEE_WAIVER ──────────────────────────
    def detect_unauthorized_waivers(
        self,
        records: Sequence[RevenueRecordWithContext],
    ) -> Tuple[PatternFinding, ...]:
        """Records flagged as waived must carry an
        authorization_id. Missing → leakage finding."""
        findings: List[PatternFinding] = []
        for r in records:
            if not r.waiver_flag:
                continue
            if r.waiver_authorization_id:
                continue
            findings.append(PatternFinding(
                finding_id=f"WAIVER-{r.record.record_id}",
                pattern_id=PatternId.UNAUTHORIZED_FEE_WAIVER,
                family=PatternFamily.LEAKAGE,
                severity=ValidationSeverity.HIGH,
                record_ids=(r.record.record_id,),
                description=(
                    "fee waiver applied without authorization_id "
                    "— revenue leakage candidate"),
                evidence=(
                    f"waiver_flag=True, "
                    f"waiver_authorization_id=None"),
                confidence=Decimal("1.0"),
                framework_refs=(
                    "ENH-242 §leakage",
                    "CBK PG/03 §revenue authorization")))
        return tuple(findings)

    # ── Detector 3: EXPIRED_CONTRACT_BILLING ─────────────────────────
    def detect_expired_contract_billing(
        self,
        records: Sequence[RevenueRecordWithContext],
        contracts: Sequence[ContractRate],
    ) -> Tuple[PatternFinding, ...]:
        """Records posted under a contract whose effective_to date
        precedes the posting_date are flagged."""
        if not contracts:
            return ()
        contract_index: Dict[str, ContractRate] = {
            c.contract_id: c for c in contracts}
        findings: List[PatternFinding] = []
        for r in records:
            if r.contract_id is None:
                continue
            c = contract_index.get(r.contract_id)
            if c is None:
                continue
            if r.record.posting_date <= c.effective_to:
                continue
            days_late = (
                r.record.posting_date.toordinal()
                - c.effective_to.toordinal())
            findings.append(PatternFinding(
                finding_id=f"EXPIRED-{r.record.record_id}",
                pattern_id=PatternId.EXPIRED_CONTRACT_BILLING,
                family=PatternFamily.LEAKAGE,
                severity=(
                    ValidationSeverity.HIGH if days_late > 30
                    else ValidationSeverity.MEDIUM),
                record_ids=(r.record.record_id,),
                description=(
                    f"posting under contract {r.contract_id} but "
                    f"contract expired {days_late} day(s) prior — "
                    f"verify renewal and rate"),
                evidence=(
                    f"posting_date={r.record.posting_date.isoformat()}, "
                    f"effective_to={c.effective_to.isoformat()}"),
                confidence=Decimal("1.0"),
                framework_refs=(
                    "ENH-242 §leakage",
                    "Contract lifecycle discipline")))
        return tuple(findings)

    # ── Detector 4: RATE_CARD_BREACH ─────────────────────────────────
    def detect_rate_card_breaches(
        self,
        records: Sequence[RevenueRecordWithContext],
        contracts: Sequence[ContractRate],
    ) -> Tuple[PatternFinding, ...]:
        """Records with applied_rate_pct outside the contract band
        are flagged. Below floor → revenue leakage; above ceiling →
        compliance breach (overcharging)."""
        if not contracts:
            return ()
        contract_index: Dict[str, ContractRate] = {
            c.contract_id: c for c in contracts}
        findings: List[PatternFinding] = []
        for r in records:
            if r.contract_id is None or r.applied_rate_pct is None:
                continue
            c = contract_index.get(r.contract_id)
            if c is None:
                continue
            applied = r.applied_rate_pct
            if applied < c.floor_rate_pct:
                findings.append(PatternFinding(
                    finding_id=f"RATE-FLOOR-{r.record.record_id}",
                    pattern_id=PatternId.RATE_BELOW_FLOOR,
                    family=PatternFamily.RATE_CARD_BREACH,
                    severity=ValidationSeverity.MEDIUM,
                    record_ids=(r.record.record_id,),
                    description=(
                        f"applied rate {applied}% below contract "
                        f"floor {c.floor_rate_pct}% — revenue "
                        f"leakage candidate"),
                    evidence=(
                        f"contract={c.contract_id}, "
                        f"applied={applied}, "
                        f"floor={c.floor_rate_pct}, "
                        f"ceiling={c.ceiling_rate_pct}"),
                    confidence=Decimal("1.0"),
                    framework_refs=(
                        "ENH-242 §rate_card_breach",
                        "ENH-242 §leakage")))
            elif applied > c.ceiling_rate_pct:
                findings.append(PatternFinding(
                    finding_id=f"RATE-CEIL-{r.record.record_id}",
                    pattern_id=PatternId.RATE_ABOVE_CEILING,
                    family=PatternFamily.RATE_CARD_BREACH,
                    severity=ValidationSeverity.HIGH,
                    record_ids=(r.record.record_id,),
                    description=(
                        f"applied rate {applied}% above contract "
                        f"ceiling {c.ceiling_rate_pct}% — "
                        f"compliance breach (overcharging)"),
                    evidence=(
                        f"contract={c.contract_id}, "
                        f"applied={applied}, "
                        f"floor={c.floor_rate_pct}, "
                        f"ceiling={c.ceiling_rate_pct}"),
                    confidence=Decimal("1.0"),
                    framework_refs=(
                        "ENH-242 §rate_card_breach",
                        "Consumer protection — fair pricing")))
        return tuple(findings)

    # ── Detector 5: MISSING_TAX_COMPONENT ────────────────────────────
    def detect_missing_tax(
        self,
        records: Sequence[RevenueRecordWithContext],
    ) -> Tuple[PatternFinding, ...]:
        """Records with expected_tax_kes specified but actual_tax_kes
        missing or materially below expected are flagged."""
        findings: List[PatternFinding] = []
        for r in records:
            if r.expected_tax_kes is None:
                continue
            actual = r.actual_tax_kes
            if actual is None:
                findings.append(PatternFinding(
                    finding_id=f"TAX-MISSING-{r.record.record_id}",
                    pattern_id=PatternId.MISSING_TAX_COMPONENT,
                    family=PatternFamily.BILLING_ERROR,
                    severity=ValidationSeverity.HIGH,
                    record_ids=(r.record.record_id,),
                    description=(
                        f"expected tax {r.expected_tax_kes} but "
                        f"no actual tax recorded"),
                    evidence=(
                        f"expected_tax_kes="
                        f"{r.expected_tax_kes}, "
                        f"actual_tax_kes=None"),
                    confidence=Decimal("1.0"),
                    framework_refs=(
                        "ENH-242 §billing_error",
                        "KRA tax compliance")))
                continue
            tolerance = max(
                self.TAX_TOLERANCE_FLOOR_KES,
                r.expected_tax_kes * self.TAX_TOLERANCE_PCT)
            if abs(actual - r.expected_tax_kes) <= tolerance:
                continue
            findings.append(PatternFinding(
                finding_id=f"TAX-MISMATCH-{r.record.record_id}",
                pattern_id=PatternId.MISSING_TAX_COMPONENT,
                family=PatternFamily.BILLING_ERROR,
                severity=ValidationSeverity.MEDIUM,
                record_ids=(r.record.record_id,),
                description=(
                    f"tax mismatch: expected {r.expected_tax_kes}, "
                    f"actual {actual} — outside tolerance "
                    f"{tolerance}"),
                evidence=(
                    f"|expected - actual| = "
                    f"{abs(r.expected_tax_kes - actual)} > "
                    f"tolerance {tolerance}"),
                confidence=Decimal("1.0"),
                framework_refs=(
                    "ENH-242 §billing_error",
                    "KRA tax compliance")))
        return tuple(findings)

    # ── Detector 6: COMMISSION_MISCALC ───────────────────────────────
    def detect_commission_anomalies(
        self,
        commissions: Sequence[CommissionRecord],
    ) -> Tuple[PatternFinding, ...]:
        """Compare paid vs expected commission per record."""
        findings: List[PatternFinding] = []
        for c in commissions:
            diff = c.paid_commission_kes - c.expected_commission_kes
            if abs(diff) <= self.COMMISSION_TOLERANCE_KES:
                continue
            if diff > 0:
                pid = PatternId.COMMISSION_OVERPAYMENT
                desc = (
                    f"commission overpayment: paid "
                    f"{c.paid_commission_kes}, expected "
                    f"{c.expected_commission_kes}, excess "
                    f"{diff}")
                sev = ValidationSeverity.MEDIUM
            else:
                pid = PatternId.COMMISSION_UNDERPAYMENT
                desc = (
                    f"commission underpayment: paid "
                    f"{c.paid_commission_kes}, expected "
                    f"{c.expected_commission_kes}, shortfall "
                    f"{abs(diff)}")
                sev = ValidationSeverity.MEDIUM
            findings.append(PatternFinding(
                finding_id=f"COMM-{c.commission_id}",
                pattern_id=pid,
                family=PatternFamily.COMMISSION_MISCALC,
                severity=sev,
                record_ids=(c.commission_id,),
                description=desc,
                evidence=(
                    f"rm_code={c.rm_code}, "
                    f"underlying_revenue={c.underlying_revenue_kes}, "
                    f"paid={c.paid_commission_kes}, "
                    f"expected={c.expected_commission_kes}, "
                    f"diff={diff}"),
                confidence=Decimal("1.0"),
                framework_refs=(
                    "ENH-242 §commission_miscalc",
                    "ENH-247 commission assurance")))
        return tuple(findings)

    # ── Detector 7: ML hook ──────────────────────────────────────────
    def detect_with_ml(
        self,
        records: Sequence[RevenueRecordWithContext],
        ml_score_fn: Optional[MLScoreFn] = None,
        ml_threshold: Optional[Decimal] = None,
    ) -> Tuple[Tuple[PatternFinding, ...], bool, str]:
        """Run an injected ML scoring function over each record.
        Returns (findings, ml_disabled, ml_disabled_reason).

        Per Rule 6, when no model is supplied, ml_disabled=True and
        the reason is populated — callers cannot mistake rule-only
        output for ML-augmented output.

        Per Rule 7, the engine never trains a model; the model is
        always external and injected via callable.
        """
        if ml_score_fn is None:
            return ((), True, "no ml_score_fn supplied")
        thresh = ml_threshold or self.DEFAULT_ML_THRESHOLD
        if thresh <= 0 or thresh > 1:
            raise ValueError(
                f"ml_threshold must be in (0, 1]; got {thresh}")
        findings: List[PatternFinding] = []
        for r in records:
            try:
                score = ml_score_fn(r)
            except Exception as exc:
                # Per Rule 6 — don't silently swallow ML errors;
                # surface them as an INFO finding so the caller knows
                # the ML hook was attempted but failed for this
                # record.
                findings.append(PatternFinding(
                    finding_id=f"ML-ERR-{r.record.record_id}",
                    pattern_id=PatternId.ML_FLAGGED_PATTERN,
                    family=PatternFamily.LEAKAGE,
                    severity=ValidationSeverity.INFO,
                    record_ids=(r.record.record_id,),
                    description=(
                        f"ML scoring raised "
                        f"{type(exc).__name__}: {exc}"),
                    evidence="ml_score_fn raised exception",
                    confidence=Decimal("0"),
                    framework_refs=(
                        "ENH-242 §ml_hook",)))
                continue
            if score is None:
                continue
            if score < thresh:
                continue
            findings.append(PatternFinding(
                finding_id=f"ML-{r.record.record_id}",
                pattern_id=PatternId.ML_FLAGGED_PATTERN,
                family=PatternFamily.LEAKAGE,
                severity=(
                    ValidationSeverity.HIGH
                    if score >= Decimal("0.95")
                    else ValidationSeverity.MEDIUM),
                record_ids=(r.record.record_id,),
                description=(
                    f"ML model flagged record with score "
                    f"{score} ≥ threshold {thresh}"),
                evidence=(
                    f"ml_score={score}, ml_threshold={thresh}"),
                confidence=score,
                ml_score=score,
                framework_refs=(
                    "ENH-242 §ml_hook",
                    "ENH-242 §pattern_detection")))
        return (tuple(findings), False, "")

    # ── Public API: orchestrator ─────────────────────────────────────
    def detect_all(
        self,
        records: Sequence[RevenueRecordWithContext] = (),
        contracts: Sequence[ContractRate] = (),
        commissions: Sequence[CommissionRecord] = (),
        ml_score_fn: Optional[MLScoreFn] = None,
        ml_threshold: Optional[Decimal] = None,
    ) -> AnomalyReport:
        """Run all 6 deterministic detectors plus optional ML hook."""
        dup = self.detect_duplicate_billings(records)
        wai = self.detect_unauthorized_waivers(records)
        exp = self.detect_expired_contract_billing(records, contracts)
        rate = self.detect_rate_card_breaches(records, contracts)
        tax = self.detect_missing_tax(records)
        comm = self.detect_commission_anomalies(commissions)
        ml_findings, ml_disabled, ml_reason = self.detect_with_ml(
            records, ml_score_fn=ml_score_fn,
            ml_threshold=ml_threshold)
        all_findings = (
            dup + wai + exp + rate + tax + comm + ml_findings)

        by_family: Dict[str, int] = {f.value: 0 for f in PatternFamily}
        for f in all_findings:
            by_family[f.family.value] += 1
        by_sev: Dict[str, int] = {s.value: 0 for s in ValidationSeverity}
        for f in all_findings:
            by_sev[f.severity.value] += 1

        return AnomalyReport(
            findings=all_findings,
            by_family=by_family,
            by_severity=by_sev,
            records_scanned=len(records),
            contracts_used=len(contracts),
            commissions_scanned=len(commissions),
            ml_disabled=ml_disabled,
            ml_disabled_reason=ml_reason,
            framework_refs=(
                "ENH-242 §leakage + §billing_error + "
                "§commission_miscalc + §rate_card_breach",
                "ENH-242 §ml_hook",
                "Composes with ENH-241 (revenue_validation)",
            ))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _r(rid: str, day: int, amt: str = "1000") -> RevenueRecord:
    return RevenueRecord(
        record_id=rid, source_system="CBS",
        posting_date=date(2026, 4, day),
        amount_kes=Decimal(amt),
        revenue_category="FEE_INCOME",
        branch_code="NRB-01")


def _ctx(rid: str, day: int, amt: str = "1000",
         **kw) -> RevenueRecordWithContext:
    return RevenueRecordWithContext(
        record=_r(rid, day, amt), **kw)


def _test_contract_validates_ceiling_above_floor():
    try:
        ContractRate(
            contract_id="C1", customer_id="X", product_code="P",
            floor_rate_pct=Decimal("3"),
            ceiling_rate_pct=Decimal("1"),
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31))
        assert False
    except ValueError:
        pass


def _test_commission_validates_non_negative():
    try:
        CommissionRecord(
            commission_id="C1", rm_code="rm1",
            underlying_revenue_kes=Decimal("-1"),
            paid_commission_kes=Decimal("0"),
            expected_commission_kes=Decimal("0"),
            posting_date=date(2026, 4, 1))
        assert False
    except ValueError:
        pass


def _test_duplicate_billing_detected():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1, "1000", customer_id="cust-A"),
        _ctx("r2", 1, "1000", customer_id="cust-A"),
        _ctx("r3", 1, "2000", customer_id="cust-A"),
        _ctx("r4", 1, "1000", customer_id="cust-B"),
    )
    findings = eng.detect_duplicate_billings(records)
    assert len(findings) == 1
    assert findings[0].pattern_id == PatternId.DUPLICATE_BILLING
    assert set(findings[0].record_ids) == {"r1", "r2"}


def _test_duplicate_billing_three_or_more_high():
    eng = RevenueAnomalyPatternEngine()
    records = tuple(
        _ctx(f"r{i}", 1, "1000", customer_id="cust-A")
        for i in range(3))
    findings = eng.detect_duplicate_billings(records)
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.HIGH


def _test_no_duplicate_when_amounts_differ():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1, "1000", customer_id="cust-A"),
        _ctx("r2", 1, "1500", customer_id="cust-A"),
    )
    findings = eng.detect_duplicate_billings(records)
    assert len(findings) == 0


def _test_unauthorized_waiver_detected():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1, customer_id="A",
             waiver_flag=True, waiver_authorization_id=None),
        _ctx("r2", 2, customer_id="A",
             waiver_flag=True,
             waiver_authorization_id="AUTH-001"),
        _ctx("r3", 3, customer_id="A", waiver_flag=False),
    )
    findings = eng.detect_unauthorized_waivers(records)
    assert len(findings) == 1
    assert findings[0].pattern_id == (
        PatternId.UNAUTHORIZED_FEE_WAIVER)
    assert findings[0].record_ids == ("r1",)


def _test_expired_contract_billing():
    eng = RevenueAnomalyPatternEngine()
    contract = ContractRate(
        contract_id="C-001", customer_id="A",
        product_code="P", floor_rate_pct=Decimal("1"),
        ceiling_rate_pct=Decimal("3"),
        effective_from=date(2025, 1, 1),
        effective_to=date(2026, 3, 31))
    records = (
        _ctx("r1", 1, customer_id="A", contract_id="C-001"),
    )
    findings = eng.detect_expired_contract_billing(
        records, (contract,))
    assert len(findings) == 1
    assert findings[0].family == PatternFamily.LEAKAGE


def _test_rate_below_floor_flagged():
    eng = RevenueAnomalyPatternEngine()
    contract = ContractRate(
        contract_id="C", customer_id="A", product_code="P",
        floor_rate_pct=Decimal("2.0"),
        ceiling_rate_pct=Decimal("4.0"),
        effective_from=date(2025, 1, 1),
        effective_to=date(2027, 12, 31))
    records = (
        _ctx("r1", 1, customer_id="A", contract_id="C",
             applied_rate_pct=Decimal("1.5")),
    )
    findings = eng.detect_rate_card_breaches(records, (contract,))
    assert len(findings) == 1
    assert findings[0].pattern_id == PatternId.RATE_BELOW_FLOOR


def _test_rate_above_ceiling_flagged_high():
    eng = RevenueAnomalyPatternEngine()
    contract = ContractRate(
        contract_id="C", customer_id="A", product_code="P",
        floor_rate_pct=Decimal("2.0"),
        ceiling_rate_pct=Decimal("4.0"),
        effective_from=date(2025, 1, 1),
        effective_to=date(2027, 12, 31))
    records = (
        _ctx("r1", 1, customer_id="A", contract_id="C",
             applied_rate_pct=Decimal("5.5")),
    )
    findings = eng.detect_rate_card_breaches(records, (contract,))
    assert len(findings) == 1
    assert findings[0].pattern_id == PatternId.RATE_ABOVE_CEILING
    assert findings[0].severity == ValidationSeverity.HIGH


def _test_rate_within_band_no_finding():
    eng = RevenueAnomalyPatternEngine()
    contract = ContractRate(
        contract_id="C", customer_id="A", product_code="P",
        floor_rate_pct=Decimal("2.0"),
        ceiling_rate_pct=Decimal("4.0"),
        effective_from=date(2025, 1, 1),
        effective_to=date(2027, 12, 31))
    records = (
        _ctx("r1", 1, customer_id="A", contract_id="C",
             applied_rate_pct=Decimal("3.0")),
    )
    findings = eng.detect_rate_card_breaches(records, (contract,))
    assert len(findings) == 0


def _test_missing_tax_detected():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1,
             expected_tax_kes=Decimal("160"),
             actual_tax_kes=None),
        _ctx("r2", 2,
             expected_tax_kes=Decimal("160"),
             actual_tax_kes=Decimal("160")),
    )
    findings = eng.detect_missing_tax(records)
    assert len(findings) == 1
    assert findings[0].record_ids == ("r1",)


def _test_tax_mismatch_outside_tolerance():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1,
             expected_tax_kes=Decimal("1000"),
             actual_tax_kes=Decimal("800")),  # 200 diff vs ~100 tol
    )
    findings = eng.detect_missing_tax(records)
    assert len(findings) == 1


def _test_commission_overpayment_flagged():
    eng = RevenueAnomalyPatternEngine()
    commissions = (
        CommissionRecord(
            commission_id="C1", rm_code="rm1",
            underlying_revenue_kes=Decimal("100000"),
            paid_commission_kes=Decimal("6000"),
            expected_commission_kes=Decimal("5000"),
            posting_date=date(2026, 4, 1)),
    )
    findings = eng.detect_commission_anomalies(commissions)
    assert len(findings) == 1
    assert findings[0].pattern_id == (
        PatternId.COMMISSION_OVERPAYMENT)


def _test_commission_underpayment_flagged():
    eng = RevenueAnomalyPatternEngine()
    commissions = (
        CommissionRecord(
            commission_id="C1", rm_code="rm1",
            underlying_revenue_kes=Decimal("100000"),
            paid_commission_kes=Decimal("4000"),
            expected_commission_kes=Decimal("5000"),
            posting_date=date(2026, 4, 1)),
    )
    findings = eng.detect_commission_anomalies(commissions)
    assert len(findings) == 1
    assert findings[0].pattern_id == (
        PatternId.COMMISSION_UNDERPAYMENT)


def _test_commission_within_tolerance_no_finding():
    eng = RevenueAnomalyPatternEngine()
    commissions = (
        CommissionRecord(
            commission_id="C1", rm_code="rm1",
            underlying_revenue_kes=Decimal("100000"),
            paid_commission_kes=Decimal("5000.50"),
            expected_commission_kes=Decimal("5000"),
            posting_date=date(2026, 4, 1)),
    )
    findings = eng.detect_commission_anomalies(commissions)
    assert len(findings) == 0


def _test_ml_disabled_when_no_hook():
    eng = RevenueAnomalyPatternEngine()
    records = (_ctx("r1", 1),)
    findings, disabled, reason = eng.detect_with_ml(records, None)
    assert disabled is True
    assert "no ml_score_fn" in reason
    assert findings == ()


def _test_ml_hook_fires_above_threshold():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r-low", 1),
        _ctx("r-high", 2),
    )
    def model(ctx):
        return (
            Decimal("0.95") if ctx.record.record_id == "r-high"
            else Decimal("0.30"))
    findings, disabled, _ = eng.detect_with_ml(records, model)
    assert disabled is False
    assert len(findings) == 1
    assert findings[0].record_ids == ("r-high",)
    assert findings[0].ml_score == Decimal("0.95")


def _test_ml_hook_threshold_validated():
    eng = RevenueAnomalyPatternEngine()
    try:
        eng.detect_with_ml(
            (), lambda r: Decimal("0.5"),
            ml_threshold=Decimal("1.5"))
        assert False
    except ValueError:
        pass


def _test_ml_exception_surfaced_as_info_finding():
    eng = RevenueAnomalyPatternEngine()
    def model(ctx):
        raise RuntimeError("boom")
    findings, disabled, _ = eng.detect_with_ml(
        (_ctx("r1", 1),), model)
    assert disabled is False
    assert len(findings) == 1
    assert findings[0].severity == ValidationSeverity.INFO
    assert "RuntimeError" in findings[0].description


def _test_detect_all_orchestrates():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1, "1000", customer_id="A"),
        _ctx("r2", 1, "1000", customer_id="A"),
        _ctx("r3", 5, customer_id="A",
             waiver_flag=True, waiver_authorization_id=None),
    )
    report = eng.detect_all(records)
    assert isinstance(report, AnomalyReport)
    assert report.records_scanned == 3
    assert report.ml_disabled is True
    assert report.by_family["BILLING_ERROR"] == 1
    assert report.by_family["LEAKAGE"] == 1


def _test_finding_has_full_provenance():
    eng = RevenueAnomalyPatternEngine()
    records = (
        _ctx("r1", 1, "1000", customer_id="A"),
        _ctx("r2", 1, "1000", customer_id="A"),
    )
    findings = eng.detect_duplicate_billings(records)
    f = findings[0]
    assert f.finding_id
    assert f.evidence
    assert f.confidence == Decimal("1.0")
    assert len(f.framework_refs) >= 1
    assert "r1" in f.record_ids and "r2" in f.record_ids


def self_test() -> None:
    tests = [
        _test_contract_validates_ceiling_above_floor,
        _test_commission_validates_non_negative,
        _test_duplicate_billing_detected,
        _test_duplicate_billing_three_or_more_high,
        _test_no_duplicate_when_amounts_differ,
        _test_unauthorized_waiver_detected,
        _test_expired_contract_billing,
        _test_rate_below_floor_flagged,
        _test_rate_above_ceiling_flagged_high,
        _test_rate_within_band_no_finding,
        _test_missing_tax_detected,
        _test_tax_mismatch_outside_tolerance,
        _test_commission_overpayment_flagged,
        _test_commission_underpayment_flagged,
        _test_commission_within_tolerance_no_finding,
        _test_ml_disabled_when_no_hook,
        _test_ml_hook_fires_above_threshold,
        _test_ml_hook_threshold_validated,
        _test_ml_exception_surfaced_as_info_finding,
        _test_detect_all_orchestrates,
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
            f"✗ revenue_anomaly_patterns self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ revenue_anomaly_patterns self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

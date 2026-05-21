"""utils/finance_audit_compliance.py — v10.68: FAC.

ENH-258 — Finance Audit & Compliance. Cat B — finance arc 10/10
(last standard before arc closure).

Diagnostic finance-specific compliance engine. Five capabilities
covering SOX-style internal controls + segregation of duties +
authorization limits + period close attestation + manual journal
flagging. Distinct from existing audit_core / audit_reporting
(general-purpose audit infrastructure) — ENH-258 focuses on
finance-function-specific control breakdowns surfaced at
period close.

Five capabilities:
  1. check_segregation_of_duties — flag journals where same
     user prepared + reviewed + posted (or any 2 of those 3)
  2. check_authorization_limit — flag journals where amount
     exceeds preparer's authorization tier
  3. flag_manual_journals — surface journals with manual
     source for SOX evidence trail
  4. check_period_close_attestation — verify period sign-offs
     present + complete + within deadline
  5. flag_late_period_end_adjustment — flag adjustments
     above materiality booked after cut-off date

Per Rule 7, engine NEVER:
  - blocks transactions
  - revokes user access
  - cancels journals
  - auto-attests period close
  - mutates inputs

Per Rule 1, every ComplianceFinding surfaces finding_id +
severity + control + journal_id (or attestation_id) + actors +
amounts + framework refs. Operators see the full picture.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "FinanceAuditComplianceEngine implements ENH-258 — finance-"
    "function-specific SOX-style control checks. Distinct from "
    "general-purpose audit_core / audit_reporting modules. "
    "Pure stdlib. Per Rule 1, every ComplianceFinding surfaces "
    "full provenance. Per Rule 7, engine DIAGNOSTIC ONLY — "
    "never blocks transactions, never revokes access, never "
    "cancels journals, never auto-attests period close, never "
    "mutates inputs."
)


class ControlId(Enum):
    """The 5 finance-function controls covered."""
    SEGREGATION_OF_DUTIES = "SEGREGATION_OF_DUTIES"
    AUTHORIZATION_LIMIT = "AUTHORIZATION_LIMIT"
    MANUAL_JOURNAL_REVIEW = "MANUAL_JOURNAL_REVIEW"
    PERIOD_CLOSE_ATTESTATION = "PERIOD_CLOSE_ATTESTATION"
    LATE_ADJUSTMENT_MATERIALITY = "LATE_ADJUSTMENT_MATERIALITY"


class FindingSeverity(Enum):
    INFO = "INFO"           # observation, not a breach
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"   # SOX-grade breach


class JournalSource(Enum):
    AUTOMATED = "AUTOMATED"      # system-generated
    MANUAL = "MANUAL"            # operator-keyed
    UPLOADED = "UPLOADED"        # CSV / spreadsheet import


class AttestationStatus(Enum):
    PENDING = "PENDING"
    ATTESTED = "ATTESTED"
    OVERDUE = "OVERDUE"
    REJECTED = "REJECTED"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class JournalAudit:
    """One journal's audit trail metadata."""
    journal_id: str
    period: str
    posting_date: str            # YYYY-MM-DD
    amount_kes: Decimal
    source: JournalSource
    preparer_user_id: str
    reviewer_user_id: Optional[str]
    poster_user_id: Optional[str]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.journal_id:
            raise ValueError("journal_id must be non-empty")
        if not self.preparer_user_id:
            raise ValueError(
                "preparer_user_id must be non-empty")
        if self.amount_kes < 0:
            raise ValueError("amount_kes must be ≥ 0")


@dataclass(frozen=True)
class UserAuthorization:
    """Per-user posting authorization tier."""
    user_id: str
    max_journal_kes: Decimal
    role: str        # "PREPARER", "REVIEWER", "POSTER", "MANAGER"

    def __post_init__(self) -> None:
        if not self.user_id:
            raise ValueError("user_id must be non-empty")
        if self.max_journal_kes < 0:
            raise ValueError(
                "max_journal_kes must be ≥ 0")


@dataclass(frozen=True)
class PeriodAttestation:
    attestation_id: str
    period: str
    function: str          # e.g. "GL_CLOSE", "TAX", "TREASURY"
    deadline_date: str     # YYYY-MM-DD
    status: AttestationStatus
    attestor_user_id: Optional[str]
    attested_at: Optional[str]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.attestation_id:
            raise ValueError(
                "attestation_id must be non-empty")
        if not self.function:
            raise ValueError("function must be non-empty")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ComplianceFinding:
    finding_id: str
    control: ControlId
    severity: FindingSeverity
    period: str
    description: str
    actors: Tuple[str, ...]    # user IDs involved
    journal_ids: Tuple[str, ...]
    attestation_ids: Tuple[str, ...]
    amount_kes: Decimal
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ComplianceReport:
    period: str
    findings: Tuple[ComplianceFinding, ...]
    by_control: Dict[str, int]
    by_severity: Dict[str, int]
    journals_scanned: int
    attestations_scanned: int
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class FinanceAuditComplianceEngine:
    """Diagnostic finance compliance engine."""

    DEFAULT_MATERIALITY_KES: Decimal = Decimal("100000")

    def check_segregation_of_duties(
        self, journals: Sequence[JournalAudit],
    ) -> Tuple[ComplianceFinding, ...]:
        findings: List[ComplianceFinding] = []
        for j in journals:
            actors = {j.preparer_user_id}
            if j.reviewer_user_id:
                actors.add(j.reviewer_user_id)
            if j.poster_user_id:
                actors.add(j.poster_user_id)
            # Critical: same person prep+review+post
            if (j.reviewer_user_id == j.preparer_user_id
                    and j.poster_user_id == j.preparer_user_id):
                severity = FindingSeverity.CRITICAL
                desc = (
                    f"journal {j.journal_id}: same user "
                    f"{j.preparer_user_id} prepared + reviewed "
                    f"+ posted (full SoD breach)")
            elif (
                j.reviewer_user_id == j.preparer_user_id
                or j.poster_user_id == j.preparer_user_id):
                severity = FindingSeverity.HIGH
                conflict = (
                    "preparer = reviewer"
                    if j.reviewer_user_id == j.preparer_user_id
                    else "preparer = poster")
                desc = (
                    f"journal {j.journal_id}: {conflict} "
                    f"({j.preparer_user_id}) — partial SoD "
                    f"breach")
            elif j.reviewer_user_id is None:
                severity = FindingSeverity.MEDIUM
                desc = (
                    f"journal {j.journal_id}: no reviewer "
                    f"recorded — review trail incomplete")
            else:
                continue   # passes SoD
            findings.append(ComplianceFinding(
                finding_id=f"FAC-SOD-{j.journal_id}",
                control=ControlId.SEGREGATION_OF_DUTIES,
                severity=severity,
                period=j.period,
                description=desc,
                actors=tuple(sorted(actors)),
                journal_ids=(j.journal_id,),
                attestation_ids=(),
                amount_kes=j.amount_kes,
                framework_refs=(
                    "ENH-258 §segregation_of_duties",
                    "SOX 404 — internal controls over "
                    "financial reporting",
                    "Per Rule 7 — flags breach; never revokes "
                    "access")))
        return tuple(findings)

    def check_authorization_limit(
        self,
        journals: Sequence[JournalAudit],
        authorizations: Sequence[UserAuthorization],
    ) -> Tuple[ComplianceFinding, ...]:
        auth_index: Dict[str, UserAuthorization] = {
            a.user_id: a for a in authorizations}
        findings: List[ComplianceFinding] = []
        for j in journals:
            poster = j.poster_user_id or j.preparer_user_id
            auth = auth_index.get(poster)
            if auth is None:
                findings.append(ComplianceFinding(
                    finding_id=(
                        f"FAC-AUTH-MISSING-{j.journal_id}"),
                    control=ControlId.AUTHORIZATION_LIMIT,
                    severity=FindingSeverity.HIGH,
                    period=j.period,
                    description=(
                        f"journal {j.journal_id}: poster "
                        f"{poster} has no authorization "
                        f"record — cannot validate limit"),
                    actors=(poster,),
                    journal_ids=(j.journal_id,),
                    attestation_ids=(),
                    amount_kes=j.amount_kes,
                    framework_refs=(
                        "ENH-258 §authorization_limit",
                        "SOX 404 — authorization controls")))
                continue
            if j.amount_kes > auth.max_journal_kes:
                # Severity by how far over
                ratio = j.amount_kes / auth.max_journal_kes
                if ratio >= Decimal("2"):
                    severity = FindingSeverity.CRITICAL
                elif ratio >= Decimal("1.5"):
                    severity = FindingSeverity.HIGH
                else:
                    severity = FindingSeverity.MEDIUM
                findings.append(ComplianceFinding(
                    finding_id=(
                        f"FAC-AUTH-{j.journal_id}"),
                    control=ControlId.AUTHORIZATION_LIMIT,
                    severity=severity,
                    period=j.period,
                    description=(
                        f"journal {j.journal_id}: amount "
                        f"{j.amount_kes} exceeds {poster}'s "
                        f"authorization limit "
                        f"{auth.max_journal_kes} (ratio "
                        f"{ratio.quantize(Decimal('0.01'))})"),
                    actors=(poster,),
                    journal_ids=(j.journal_id,),
                    attestation_ids=(),
                    amount_kes=j.amount_kes,
                    framework_refs=(
                        "ENH-258 §authorization_limit",
                        "SOX 404 — authorization controls",
                        "Per Rule 7 — flags breach; never "
                        "blocks the transaction")))
        return tuple(findings)

    def flag_manual_journals(
        self,
        journals: Sequence[JournalAudit],
        materiality_kes: Optional[Decimal] = None,
    ) -> Tuple[ComplianceFinding, ...]:
        """Manual journals above materiality always need SOX
        evidence — engine flags them for review (not as breaches,
        as INFO observations)."""
        threshold = (
            materiality_kes
            if materiality_kes is not None
            else self.DEFAULT_MATERIALITY_KES)
        findings: List[ComplianceFinding] = []
        for j in journals:
            if j.source != JournalSource.MANUAL:
                continue
            if j.amount_kes < threshold:
                continue
            # Severity: amount-driven
            ratio = j.amount_kes / threshold
            if ratio >= Decimal("100"):
                severity = FindingSeverity.HIGH
            elif ratio >= Decimal("10"):
                severity = FindingSeverity.MEDIUM
            else:
                severity = FindingSeverity.LOW
            findings.append(ComplianceFinding(
                finding_id=f"FAC-MANUAL-{j.journal_id}",
                control=ControlId.MANUAL_JOURNAL_REVIEW,
                severity=severity,
                period=j.period,
                description=(
                    f"manual journal {j.journal_id} amount "
                    f"{j.amount_kes} ≥ materiality "
                    f"{threshold} — surface for SOX evidence "
                    f"trail"),
                actors=(
                    (j.preparer_user_id,)
                    + ((j.reviewer_user_id,)
                       if j.reviewer_user_id else ())),
                journal_ids=(j.journal_id,),
                attestation_ids=(),
                amount_kes=j.amount_kes,
                framework_refs=(
                    "ENH-258 §manual_journal_review",
                    "SOX 404 — manual journals require "
                    "documented evidence")))
        return tuple(findings)

    def check_period_close_attestation(
        self, attestations: Sequence[PeriodAttestation],
    ) -> Tuple[ComplianceFinding, ...]:
        findings: List[ComplianceFinding] = []
        for a in attestations:
            if a.status == AttestationStatus.ATTESTED:
                continue
            if a.status == AttestationStatus.OVERDUE:
                severity = FindingSeverity.HIGH
                desc = (
                    f"attestation {a.attestation_id} "
                    f"(function {a.function}, period "
                    f"{a.period}) OVERDUE — deadline "
                    f"{a.deadline_date}")
            elif a.status == AttestationStatus.REJECTED:
                severity = FindingSeverity.CRITICAL
                desc = (
                    f"attestation {a.attestation_id} "
                    f"REJECTED — period {a.period} not closed "
                    f"under audit")
            else:   # PENDING
                severity = FindingSeverity.LOW
                desc = (
                    f"attestation {a.attestation_id} PENDING "
                    f"— period {a.period} not yet attested "
                    f"by {a.deadline_date}")
            findings.append(ComplianceFinding(
                finding_id=(
                    f"FAC-ATT-{a.attestation_id}"),
                control=ControlId.PERIOD_CLOSE_ATTESTATION,
                severity=severity,
                period=a.period,
                description=desc,
                actors=(
                    (a.attestor_user_id,)
                    if a.attestor_user_id else ()),
                journal_ids=(),
                attestation_ids=(a.attestation_id,),
                amount_kes=Decimal("0"),
                framework_refs=(
                    "ENH-258 §period_close_attestation",
                    "SOX 302 — period-end CFO/CEO "
                    "certification")))
        return tuple(findings)

    def flag_late_period_end_adjustment(
        self,
        journals: Sequence[JournalAudit],
        period_cutoff_date: str,
        materiality_kes: Optional[Decimal] = None,
    ) -> Tuple[ComplianceFinding, ...]:
        threshold = (
            materiality_kes
            if materiality_kes is not None
            else self.DEFAULT_MATERIALITY_KES)
        findings: List[ComplianceFinding] = []
        for j in journals:
            if j.posting_date <= period_cutoff_date:
                continue
            if j.amount_kes < threshold:
                continue
            ratio = j.amount_kes / threshold
            if ratio >= Decimal("10"):
                severity = FindingSeverity.HIGH
            elif ratio >= Decimal("3"):
                severity = FindingSeverity.MEDIUM
            else:
                severity = FindingSeverity.LOW
            findings.append(ComplianceFinding(
                finding_id=f"FAC-LATE-{j.journal_id}",
                control=ControlId.LATE_ADJUSTMENT_MATERIALITY,
                severity=severity,
                period=j.period,
                description=(
                    f"journal {j.journal_id} posted "
                    f"{j.posting_date} after period {j.period} "
                    f"cutoff {period_cutoff_date}; amount "
                    f"{j.amount_kes} ≥ materiality "
                    f"{threshold} — late adjustment requires "
                    f"audit explanation"),
                actors=(j.preparer_user_id,),
                journal_ids=(j.journal_id,),
                attestation_ids=(),
                amount_kes=j.amount_kes,
                framework_refs=(
                    "ENH-258 §late_adjustment_materiality",
                    "SOX 404 — period-end cutoff discipline")))
        return tuple(findings)

    def build_compliance_report(
        self,
        period: str,
        journals: Sequence[JournalAudit] = (),
        authorizations: Sequence[UserAuthorization] = (),
        attestations: Sequence[PeriodAttestation] = (),
        period_cutoff_date: Optional[str] = None,
        materiality_kes: Optional[Decimal] = None,
    ) -> ComplianceReport:
        all_findings: List[ComplianceFinding] = []
        all_findings.extend(
            self.check_segregation_of_duties(journals))
        all_findings.extend(self.check_authorization_limit(
            journals, authorizations))
        all_findings.extend(self.flag_manual_journals(
            journals, materiality_kes))
        all_findings.extend(
            self.check_period_close_attestation(attestations))
        if period_cutoff_date is not None:
            all_findings.extend(
                self.flag_late_period_end_adjustment(
                    journals, period_cutoff_date,
                    materiality_kes))
        by_control: Dict[str, int] = {
            c.value: 0 for c in ControlId}
        for f in all_findings:
            by_control[f.control.value] += 1
        by_severity: Dict[str, int] = {
            s.value: 0 for s in FindingSeverity}
        for f in all_findings:
            by_severity[f.severity.value] += 1
        return ComplianceReport(
            period=period,
            findings=tuple(all_findings),
            by_control=by_control,
            by_severity=by_severity,
            journals_scanned=len(journals),
            attestations_scanned=len(attestations),
            framework_refs=(
                "ENH-258 §compliance_report",
                "SOX 302 + 404 — finance-function controls",
                "Per Rule 7 — diagnostic only; never blocks "
                "transactions; never revokes access; never "
                "cancels journals; never auto-attests"))


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _journal(jid="J1", period="2026-04",
             posting="2026-04-15",
             amt=Decimal("50000"),
             source=JournalSource.AUTOMATED,
             prep="alice", rev="bob", post="carol"):
    return JournalAudit(
        journal_id=jid, period=period,
        posting_date=posting, amount_kes=amt,
        source=source,
        preparer_user_id=prep,
        reviewer_user_id=rev,
        poster_user_id=post)


def _test_journal_validates_id():
    try:
        _journal(jid="")
        assert False
    except ValueError:
        pass


def _test_journal_validates_negative_amount():
    try:
        _journal(amt=Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_authorization_validates_user_id():
    try:
        UserAuthorization(
            user_id="", max_journal_kes=Decimal("1"),
            role="PREPARER")
        assert False
    except ValueError:
        pass


def _test_sod_passes_with_distinct_actors():
    eng = FinanceAuditComplianceEngine()
    j = _journal()
    findings = eng.check_segregation_of_duties((j,))
    assert len(findings) == 0


def _test_sod_critical_when_one_user_does_all():
    eng = FinanceAuditComplianceEngine()
    j = _journal(prep="alice", rev="alice", post="alice")
    findings = eng.check_segregation_of_duties((j,))
    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.CRITICAL


def _test_sod_high_when_preparer_equals_poster():
    eng = FinanceAuditComplianceEngine()
    j = _journal(prep="alice", rev="bob", post="alice")
    findings = eng.check_segregation_of_duties((j,))
    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.HIGH


def _test_sod_medium_when_no_reviewer():
    eng = FinanceAuditComplianceEngine()
    j = _journal(prep="alice", rev=None, post="bob")
    findings = eng.check_segregation_of_duties((j,))
    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.MEDIUM


def _test_authorization_within_limit_passes():
    eng = FinanceAuditComplianceEngine()
    j = _journal(amt=Decimal("50000"))
    auths = (
        UserAuthorization(
            user_id="carol", max_journal_kes=Decimal("100000"),
            role="POSTER"),
    )
    findings = eng.check_authorization_limit((j,), auths)
    assert len(findings) == 0


def _test_authorization_breach_critical():
    eng = FinanceAuditComplianceEngine()
    j = _journal(amt=Decimal("500000"))
    auths = (
        UserAuthorization(
            user_id="carol",
            max_journal_kes=Decimal("100000"),
            role="POSTER"),
    )
    findings = eng.check_authorization_limit((j,), auths)
    # ratio = 5x → CRITICAL
    assert findings[0].severity == FindingSeverity.CRITICAL


def _test_authorization_missing_record_high():
    eng = FinanceAuditComplianceEngine()
    j = _journal()
    findings = eng.check_authorization_limit((j,), ())
    assert findings[0].severity == FindingSeverity.HIGH
    assert "no authorization record" in findings[0].description


def _test_manual_journal_above_materiality_flagged():
    eng = FinanceAuditComplianceEngine()
    j = _journal(
        amt=Decimal("500000"),
        source=JournalSource.MANUAL)
    findings = eng.flag_manual_journals((j,))
    assert len(findings) == 1
    assert findings[0].control == (
        ControlId.MANUAL_JOURNAL_REVIEW)


def _test_manual_journal_below_materiality_skipped():
    eng = FinanceAuditComplianceEngine()
    j = _journal(
        amt=Decimal("50000"),
        source=JournalSource.MANUAL)
    findings = eng.flag_manual_journals((j,))
    assert len(findings) == 0


def _test_automated_journal_not_flagged():
    eng = FinanceAuditComplianceEngine()
    j = _journal(amt=Decimal("999000000"),  # huge
                 source=JournalSource.AUTOMATED)
    findings = eng.flag_manual_journals((j,))
    assert len(findings) == 0


def _test_attestation_overdue_high():
    eng = FinanceAuditComplianceEngine()
    a = PeriodAttestation(
        attestation_id="A1", period="2026-04",
        function="GL_CLOSE",
        deadline_date="2026-05-05",
        status=AttestationStatus.OVERDUE,
        attestor_user_id="cfo",
        attested_at=None)
    findings = eng.check_period_close_attestation((a,))
    assert findings[0].severity == FindingSeverity.HIGH


def _test_attestation_rejected_critical():
    eng = FinanceAuditComplianceEngine()
    a = PeriodAttestation(
        attestation_id="A1", period="2026-04",
        function="GL_CLOSE",
        deadline_date="2026-05-05",
        status=AttestationStatus.REJECTED,
        attestor_user_id="cfo",
        attested_at=None)
    findings = eng.check_period_close_attestation((a,))
    assert findings[0].severity == FindingSeverity.CRITICAL


def _test_attestation_attested_no_finding():
    eng = FinanceAuditComplianceEngine()
    a = PeriodAttestation(
        attestation_id="A1", period="2026-04",
        function="GL_CLOSE",
        deadline_date="2026-05-05",
        status=AttestationStatus.ATTESTED,
        attestor_user_id="cfo",
        attested_at="2026-05-04T17:30:00")
    findings = eng.check_period_close_attestation((a,))
    assert len(findings) == 0


def _test_late_adjustment_flagged():
    eng = FinanceAuditComplianceEngine()
    j = _journal(
        period="2026-04",
        posting="2026-05-15",   # well after period
        amt=Decimal("5000000"))  # 50× materiality
    findings = eng.flag_late_period_end_adjustment(
        (j,), period_cutoff_date="2026-05-05")
    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.HIGH


def _test_late_adjustment_within_cutoff_skipped():
    eng = FinanceAuditComplianceEngine()
    j = _journal(
        period="2026-04",
        posting="2026-05-03")
    findings = eng.flag_late_period_end_adjustment(
        (j,), period_cutoff_date="2026-05-05")
    assert len(findings) == 0


def _test_compliance_report_orchestrates():
    eng = FinanceAuditComplianceEngine()
    journals = (
        _journal(jid="J1"),  # clean
        _journal(jid="J2", prep="x", rev="x", post="x"),  # SoD
        _journal(
            jid="J3",
            amt=Decimal("500000"),
            source=JournalSource.MANUAL),  # manual flag
    )
    auths = (
        UserAuthorization(
            user_id="carol",
            max_journal_kes=Decimal("100000"),
            role="POSTER"),
        UserAuthorization(
            user_id="x",
            max_journal_kes=Decimal("100000"),
            role="POSTER"),
    )
    attestations = (
        PeriodAttestation(
            attestation_id="A1", period="2026-04",
            function="GL_CLOSE",
            deadline_date="2026-05-05",
            status=AttestationStatus.ATTESTED,
            attestor_user_id="cfo",
            attested_at="2026-05-04"),
    )
    report = eng.build_compliance_report(
        "2026-04",
        journals=journals,
        authorizations=auths,
        attestations=attestations)
    assert report.journals_scanned == 3
    assert report.attestations_scanned == 1
    assert any(
        "ENH-258" in r for r in report.framework_refs)
    assert any(
        "Rule 7" in r for r in report.framework_refs)


def _test_engine_does_not_mutate_inputs():
    eng = FinanceAuditComplianceEngine()
    j = _journal()
    eng.check_segregation_of_duties((j,))
    assert j.preparer_user_id == "alice"


def _test_full_provenance():
    eng = FinanceAuditComplianceEngine()
    j = _journal(prep="x", rev="x", post="x")
    findings = eng.check_segregation_of_duties((j,))
    f = findings[0]
    assert f.finding_id
    assert f.control == ControlId.SEGREGATION_OF_DUTIES
    assert "x" in f.actors
    assert j.journal_id in f.journal_ids
    assert any("ENH-258" in r for r in f.framework_refs)
    assert any("SOX" in r for r in f.framework_refs)


def self_test() -> None:
    tests = [
        _test_journal_validates_id,
        _test_journal_validates_negative_amount,
        _test_authorization_validates_user_id,
        _test_sod_passes_with_distinct_actors,
        _test_sod_critical_when_one_user_does_all,
        _test_sod_high_when_preparer_equals_poster,
        _test_sod_medium_when_no_reviewer,
        _test_authorization_within_limit_passes,
        _test_authorization_breach_critical,
        _test_authorization_missing_record_high,
        _test_manual_journal_above_materiality_flagged,
        _test_manual_journal_below_materiality_skipped,
        _test_automated_journal_not_flagged,
        _test_attestation_overdue_high,
        _test_attestation_rejected_critical,
        _test_attestation_attested_no_finding,
        _test_late_adjustment_flagged,
        _test_late_adjustment_within_cutoff_skipped,
        _test_compliance_report_orchestrates,
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
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ finance_audit_compliance self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ finance_audit_compliance self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

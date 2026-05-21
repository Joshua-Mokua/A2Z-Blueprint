"""utils/audit_core.py — v10.23 Phase 2 batch 4 (Audit/GRC arc batch 1).

╔════════════════════════════════════════════════════════════════════════╗
║  CORE AUDIT ENGINE — UNIVERSE + RISK PLAN + MONITORING + WORKING PAPERS║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (audit findings drive remediation + regulatory     ║
║              attestation; control failures impact financial close)    ║
║  Implements 4 of 17 Audit/GRC standards from registry:                  ║
║    ENH-201:    Audit Universe & Risk-Based Planning                     ║
║    ENH-202:    Continuous Control Monitoring Engine                     ║
║    ENH-203:    Electronic Working Papers                                ║
║    ENH-AUD-R7: Connect-Validate-Respond Architecture                    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IIA International Standards for Internal Auditing (IPPF)             ║
║    IPPF Standard 1100 — independence and objectivity                   ║
║    IPPF Standard 2010 — risk-based planning                            ║
║    IPPF Standard 2120 — risk management                                ║
║    IPPF Standard 2330 — documenting information (working papers)       ║
║    COSO Internal Control Integrated Framework (2013)                   ║
║    COSO ERM Framework (2017)                                            ║
║    Basel Principles for the Assessment of Bank Internal Audit (2012)   ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk              ║
║    CBK CRMF April 2021 §7 — internal audit function                    ║
║    CBK Banking Act §44 — internal audit independence                   ║
║    Sarbanes-Oxley §302 + §404 — internal control reporting            ║
║    ISO 31000:2018 — Risk Management                                    ║
║    ISO 27001 §A.18 — internal audit (information security)            ║
║    ISACA COBIT 2019 — IT governance + audit                            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 1: control test results never silently passed; failures  ║
║  surface explicitly with severity + remediation deadline.               ║
║  Honesty Rule 7: data-source connectors + automated testers are        ║
║  callable hooks; engine surfaces SPEC_DEVIATION when no provider wired.║
║                                                                         ║
║  Composes with all v10.6-v10.22 engines — audit can monitor controls   ║
║  across Climate, Credit, KESONIA, RMS without modifying them.          ║
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

SPEC_DEVIATION_NOTE = (
    "Automated control testing requires injected data-source connectors + "
    "test executors per Rule 7. Without wired providers, engine records "
    "tests as REQUIRES_PROVIDER and surfaces this state explicitly.")


# ════════════════════════════════════════════════════════════════════════
# Audit universe (ENH-201)
# ════════════════════════════════════════════════════════════════════════

class AuditableEntityType(Enum):
    """Categories of auditable entities per IPPF + COSO."""
    BUSINESS_LINE = "BUSINESS_LINE"            # Retail / SME / Corporate / Treasury
    LEGAL_ENTITY = "LEGAL_ENTITY"              # Subsidiary / branch / SPV
    PROCESS = "PROCESS"                         # KYC / Onboarding / Loan Origination
    SYSTEM = "SYSTEM"                           # FLEXCUBE / ATM Network / Mobile
    GEOGRAPHY = "GEOGRAPHY"                    # Region / branch cluster
    SUPPORT_FUNCTION = "SUPPORT_FUNCTION"      # HR / Finance / IT / Compliance
    THIRD_PARTY = "THIRD_PARTY"                # Vendor / outsourcer
    REGULATORY_DOMAIN = "REGULATORY_DOMAIN"    # CBK supervisory area


class RiskRating(Enum):
    """5-point inherent + residual risk scale (IPPF + Basel aligned)."""
    VERY_LOW = "VERY_LOW"      # 1
    LOW = "LOW"                # 2
    MEDIUM = "MEDIUM"          # 3
    HIGH = "HIGH"              # 4
    CRITICAL = "CRITICAL"      # 5


# Numeric mapping for sorting + score arithmetic
RISK_RATING_VALUE: Mapping[RiskRating, int] = {
    RiskRating.VERY_LOW: 1,
    RiskRating.LOW: 2,
    RiskRating.MEDIUM: 3,
    RiskRating.HIGH: 4,
    RiskRating.CRITICAL: 5,
}


@dataclass(frozen=True)
class AuditableEntity:
    """An entity within the audit universe."""
    entity_id: str
    entity_name: str
    entity_type: AuditableEntityType
    inherent_risk: RiskRating
    residual_risk: RiskRating               # post-controls
    last_audit_date: Optional[str] = None    # ISO-8601
    parent_entity_id: Optional[str] = None
    notes: str = ""

    def risk_score(self) -> int:
        """Combined risk score for prioritization (inherent + residual)."""
        return (RISK_RATING_VALUE[self.inherent_risk]
                  + RISK_RATING_VALUE[self.residual_risk])


# ════════════════════════════════════════════════════════════════════════
# Risk-based planning (ENH-201)
# ════════════════════════════════════════════════════════════════════════

class AuditFrequency(Enum):
    """Audit cycle frequency per risk rating + IPPF Standard 2010."""
    ANNUAL = "ANNUAL"               # CRITICAL / HIGH residual risk
    BIENNIAL = "BIENNIAL"           # MEDIUM residual risk
    TRIENNIAL = "TRIENNIAL"          # LOW residual risk
    AS_REQUIRED = "AS_REQUIRED"     # VERY_LOW residual risk


# Per IPPF + Basel BCBS guidelines — recommended frequency by residual risk
DEFAULT_FREQUENCY_BY_RISK: Mapping[RiskRating, AuditFrequency] = {
    RiskRating.CRITICAL: AuditFrequency.ANNUAL,
    RiskRating.HIGH: AuditFrequency.ANNUAL,
    RiskRating.MEDIUM: AuditFrequency.BIENNIAL,
    RiskRating.LOW: AuditFrequency.TRIENNIAL,
    RiskRating.VERY_LOW: AuditFrequency.AS_REQUIRED,
}


# Months between audits per frequency (used to compute "due" status)
FREQUENCY_MONTHS: Mapping[AuditFrequency, Optional[int]] = {
    AuditFrequency.ANNUAL: 12,
    AuditFrequency.BIENNIAL: 24,
    AuditFrequency.TRIENNIAL: 36,
    AuditFrequency.AS_REQUIRED: None,    # no fixed cycle
}


@dataclass(frozen=True)
class AuditPlanItem:
    """An entity scheduled for audit within a given annual plan."""
    plan_item_id: str
    entity_id: str
    entity_name: str
    planned_quarter: str              # e.g., "2026-Q1"
    estimated_hours: int
    lead_auditor_id: Optional[str] = None
    frequency: AuditFrequency = AuditFrequency.ANNUAL
    notes: str = ""


def determine_frequency(residual_risk: RiskRating) -> AuditFrequency:
    """Map residual risk → recommended audit frequency."""
    return DEFAULT_FREQUENCY_BY_RISK[residual_risk]


def is_audit_due(
    *,
    entity: AuditableEntity,
    frequency: AuditFrequency,
    as_of: date,
) -> bool:
    """Check if the entity is due/overdue for an audit."""
    months = FREQUENCY_MONTHS.get(frequency)
    if months is None:
        return False    # AS_REQUIRED — no fixed cycle
    if entity.last_audit_date is None:
        return True     # never audited
    try:
        last = date.fromisoformat(entity.last_audit_date)
    except ValueError:
        return False
    days_since = (as_of - last).days
    cycle_days = months * 30   # approximation
    return days_since >= cycle_days


def build_annual_audit_plan(
    *,
    entities: Sequence[AuditableEntity],
    fiscal_year: int,
    as_of: date,
) -> Tuple[AuditPlanItem, ...]:
    """Build a risk-based annual audit plan.

    Selects entities that are due (or overdue) in priority order by
    risk_score(). Critical/high-risk entities go to Q1; medium to Q2;
    lower-risk to Q3/Q4.
    """
    candidates: List[Tuple[AuditableEntity, AuditFrequency]] = []
    for ent in entities:
        freq = determine_frequency(ent.residual_risk)
        if is_audit_due(
                entity=ent, frequency=freq, as_of=as_of):
            candidates.append((ent, freq))

    # Sort by risk score descending (highest risk first)
    candidates.sort(key=lambda x: x[0].risk_score(), reverse=True)

    plan: List[AuditPlanItem] = []
    for i, (ent, freq) in enumerate(candidates):
        # Quarterly bucketing by risk
        if ent.residual_risk in (
                RiskRating.CRITICAL, RiskRating.HIGH):
            quarter = f"{fiscal_year}-Q1"
            hours = 200    # higher effort
        elif ent.residual_risk == RiskRating.MEDIUM:
            quarter = f"{fiscal_year}-Q2"
            hours = 120
        elif ent.residual_risk == RiskRating.LOW:
            quarter = (
                f"{fiscal_year}-Q3" if i % 2 == 0
                else f"{fiscal_year}-Q4")
            hours = 80
        else:
            quarter = f"{fiscal_year}-Q4"
            hours = 40
        plan.append(AuditPlanItem(
            plan_item_id=f"AP-{fiscal_year}-{i + 1:04d}",
            entity_id=ent.entity_id,
            entity_name=ent.entity_name,
            planned_quarter=quarter,
            estimated_hours=hours,
            frequency=freq))
    return tuple(plan)


# ════════════════════════════════════════════════════════════════════════
# Control monitoring (ENH-202)
# ════════════════════════════════════════════════════════════════════════

class ControlType(Enum):
    """Control taxonomy per COSO + COBIT."""
    PREVENTIVE = "PREVENTIVE"            # blocks errors before they occur
    DETECTIVE = "DETECTIVE"              # detects errors after the fact
    CORRECTIVE = "CORRECTIVE"            # fixes detected errors
    DIRECTIVE = "DIRECTIVE"              # policy/standard guidance


class ControlNature(Enum):
    """Manual vs automated."""
    MANUAL = "MANUAL"
    SEMI_AUTOMATED = "SEMI_AUTOMATED"
    AUTOMATED = "AUTOMATED"


class ControlFrequency(Enum):
    REAL_TIME = "REAL_TIME"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    AD_HOC = "AD_HOC"


@dataclass(frozen=True)
class Control:
    """A single internal control."""
    control_id: str
    control_name: str
    control_description: str
    entity_id: str                       # what this control protects
    control_type: ControlType
    control_nature: ControlNature
    control_frequency: ControlFrequency
    owner_role: str = ""
    framework_refs: Tuple[str, ...] = ()  # e.g., ("COSO-CC1.1", "COBIT-DSS01")
    notes: str = ""


class ControlTestVerdict(Enum):
    """Outcome of a control test."""
    EFFECTIVE = "EFFECTIVE"                # operating as designed
    DEFICIENT_DESIGN = "DEFICIENT_DESIGN"  # control design flaw
    DEFICIENT_OPERATING = "DEFICIENT_OPERATING"   # not operating
    PARTIAL = "PARTIAL"                    # works inconsistently
    REQUIRES_PROVIDER = "REQUIRES_PROVIDER"  # Rule 7 — no automated tester
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_TESTED = "NOT_TESTED"


class ControlSeverity(Enum):
    """Severity of identified control failure."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Default remediation deadline by severity (calendar days)
DEFAULT_REMEDIATION_DAYS: Mapping[ControlSeverity, int] = {
    ControlSeverity.CRITICAL: 7,
    ControlSeverity.HIGH: 30,
    ControlSeverity.MEDIUM: 60,
    ControlSeverity.LOW: 90,
}


@dataclass(frozen=True)
class ControlTestResult:
    """Outcome of executing a control test."""
    test_id: str
    control_id: str
    test_date: str                       # ISO-8601
    verdict: ControlTestVerdict
    severity: Optional[ControlSeverity] = None
    sample_size: int = 0
    exceptions_found: int = 0
    remediation_due: Optional[str] = None  # ISO-8601 date
    notes: str = ""

    def is_failure(self) -> bool:
        return self.verdict in (
            ControlTestVerdict.DEFICIENT_DESIGN,
            ControlTestVerdict.DEFICIENT_OPERATING,
            ControlTestVerdict.PARTIAL)

    def is_actionable_now(self) -> bool:
        """Failure that requires remediation tracking."""
        return self.is_failure() and self.severity is not None


def execute_control_test(
    *,
    control: Control,
    test_id: str,
    test_date: str,
    automated_tester: Optional[
        Callable[[Control], Tuple[ControlTestVerdict, int, int]]] = None,
) -> ControlTestResult:
    """Run a control test, optionally via injected automated tester.

    Per Rule 7 — when no automated_tester is provided, the test result
    is REQUIRES_PROVIDER (not silently EFFECTIVE).
    """
    if automated_tester is None:
        return ControlTestResult(
            test_id=test_id, control_id=control.control_id,
            test_date=test_date,
            verdict=ControlTestVerdict.REQUIRES_PROVIDER,
            notes=("no automated_tester wired — Rule 7 honesty: no test "
                     "performed; result not fabricated"))

    try:
        verdict, sample, exceptions = automated_tester(control)
    except Exception as e:
        return ControlTestResult(
            test_id=test_id, control_id=control.control_id,
            test_date=test_date,
            verdict=ControlTestVerdict.INCONCLUSIVE,
            notes=f"tester failed: {type(e).__name__}: {e}")

    severity: Optional[ControlSeverity] = None
    remediation_due: Optional[str] = None
    if verdict in (
            ControlTestVerdict.DEFICIENT_DESIGN,
            ControlTestVerdict.DEFICIENT_OPERATING,
            ControlTestVerdict.PARTIAL):
        # Severity inferred from exception rate vs sample size
        if sample > 0:
            exception_rate = exceptions / sample
            if exception_rate >= 0.50:
                severity = ControlSeverity.CRITICAL
            elif exception_rate >= 0.20:
                severity = ControlSeverity.HIGH
            elif exception_rate >= 0.05:
                severity = ControlSeverity.MEDIUM
            else:
                severity = ControlSeverity.LOW
        else:
            severity = ControlSeverity.MEDIUM    # default if no sampling
        try:
            test_dt = date.fromisoformat(test_date)
            days = DEFAULT_REMEDIATION_DAYS[severity]
            remediation_due = (
                test_dt + timedelta(days=days)).isoformat()
        except ValueError:
            pass

    return ControlTestResult(
        test_id=test_id, control_id=control.control_id,
        test_date=test_date, verdict=verdict, severity=severity,
        sample_size=sample, exceptions_found=exceptions,
        remediation_due=remediation_due,
        notes=(
            f"sample={sample} exceptions={exceptions}"
            if sample else "no sampling performed"))


# ════════════════════════════════════════════════════════════════════════
# Electronic working papers (ENH-203)
# ════════════════════════════════════════════════════════════════════════

class WorkingPaperType(Enum):
    """Types of audit evidence per IPPF Standard 2330."""
    PLANNING_MEMO = "PLANNING_MEMO"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    CONTROL_NARRATIVE = "CONTROL_NARRATIVE"
    WALKTHROUGH = "WALKTHROUGH"
    TEST_RESULTS = "TEST_RESULTS"
    EXCEPTION_ANALYSIS = "EXCEPTION_ANALYSIS"
    INTERVIEW_NOTES = "INTERVIEW_NOTES"
    EVIDENCE_DOCUMENT = "EVIDENCE_DOCUMENT"
    MANAGEMENT_RESPONSE = "MANAGEMENT_RESPONSE"
    AUDIT_REPORT = "AUDIT_REPORT"
    QUALITY_REVIEW = "QUALITY_REVIEW"


class WorkingPaperStatus(Enum):
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


# IPPF Standard 2330.A2 — retention period for working papers
# CBK CRMF + IIA: retain audit working papers for 7 years post-archive
DEFAULT_WORKING_PAPER_RETENTION_YEARS = 7


@dataclass(frozen=True)
class WorkingPaper:
    """One audit working paper with cryptographic integrity."""
    paper_id: str
    paper_type: WorkingPaperType
    audit_engagement_id: str
    title: str
    prepared_by_user_id: str
    prepared_at: str                      # ISO-8601
    sha256_content_hash: str               # for integrity verification
    status: WorkingPaperStatus = WorkingPaperStatus.DRAFT
    reviewed_by_user_id: Optional[str] = None
    reviewed_at: Optional[str] = None
    file_path: Optional[str] = None
    related_control_ids: Tuple[str, ...] = ()
    notes: str = ""

    def integrity_check(self, *, current_content: bytes) -> bool:
        """Verify content hasn't been tampered with."""
        actual_hash = hashlib.sha256(current_content).hexdigest()
        return actual_hash == self.sha256_content_hash


def compute_paper_hash(content: bytes) -> str:
    """Compute SHA-256 hex hash for working paper content."""
    return hashlib.sha256(content).hexdigest()


# ════════════════════════════════════════════════════════════════════════
# Connect-Validate-Respond architecture (ENH-AUD-R7)
# ════════════════════════════════════════════════════════════════════════

class CVRStage(Enum):
    """The 3 stages of the CVR pattern."""
    CONNECT = "CONNECT"      # connect to data source
    VALIDATE = "VALIDATE"    # validate against control criteria
    RESPOND = "RESPOND"      # respond to detected issue


class CVRConnectorType(Enum):
    """Types of data source connectors."""
    DATABASE = "DATABASE"
    API = "API"
    FILE_SYSTEM = "FILE_SYSTEM"
    SWIFT_FEED = "SWIFT_FEED"
    GL_FEED = "GL_FEED"
    CBS_FEED = "CBS_FEED"
    LDAP_DIRECTORY = "LDAP_DIRECTORY"
    SIEM_LOG = "SIEM_LOG"


class CVRResponseAction(Enum):
    """Standard responses to validation failure."""
    LOG_FINDING = "LOG_FINDING"
    OPEN_TICKET = "OPEN_TICKET"
    NOTIFY_OWNER = "NOTIFY_OWNER"
    ESCALATE_TO_AUDIT_COMMITTEE = "ESCALATE_TO_AUDIT_COMMITTEE"
    BLOCK_TRANSACTION = "BLOCK_TRANSACTION"     # only for preventive controls
    REQUIRE_DUAL_APPROVAL = "REQUIRE_DUAL_APPROVAL"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"


@dataclass(frozen=True)
class CVRRunResult:
    """Outcome of one CVR cycle."""
    run_id: str
    control_id: str
    stage_completed: CVRStage              # how far the cycle got
    connect_success: bool
    validate_success: bool
    n_validations_passed: int
    n_validations_failed: int
    response_actions_taken: Tuple[CVRResponseAction, ...]
    notes: str = ""

    def fully_completed(self) -> bool:
        return self.stage_completed == CVRStage.RESPOND


def run_connect_validate_respond(
    *,
    run_id: str,
    control: Control,
    connector: Optional[
        Callable[[Control], Tuple[bool, Sequence[Mapping[str, object]]]]] = None,
    validator: Optional[
        Callable[[Control, Sequence[Mapping[str, object]]],
                  Tuple[int, int]]] = None,
    responder: Optional[
        Callable[[Control, int, int],
                  Tuple[CVRResponseAction, ...]]] = None,
) -> CVRRunResult:
    """Execute the Connect-Validate-Respond cycle for one control.

    Per Rule 7 — all 3 stages are callable hooks. Without them, the run
    surfaces what stage was reached and why.
    """
    # CONNECT
    if connector is None:
        return CVRRunResult(
            run_id=run_id, control_id=control.control_id,
            stage_completed=CVRStage.CONNECT,
            connect_success=False, validate_success=False,
            n_validations_passed=0, n_validations_failed=0,
            response_actions_taken=(),
            notes="no connector wired — Rule 7: no fab")

    try:
        connect_ok, data = connector(control)
    except Exception as e:
        return CVRRunResult(
            run_id=run_id, control_id=control.control_id,
            stage_completed=CVRStage.CONNECT,
            connect_success=False, validate_success=False,
            n_validations_passed=0, n_validations_failed=0,
            response_actions_taken=(),
            notes=f"connector failed: {type(e).__name__}: {e}")

    if not connect_ok:
        return CVRRunResult(
            run_id=run_id, control_id=control.control_id,
            stage_completed=CVRStage.CONNECT,
            connect_success=False, validate_success=False,
            n_validations_passed=0, n_validations_failed=0,
            response_actions_taken=(),
            notes="connector returned not-ok")

    # VALIDATE
    if validator is None:
        return CVRRunResult(
            run_id=run_id, control_id=control.control_id,
            stage_completed=CVRStage.CONNECT,
            connect_success=True, validate_success=False,
            n_validations_passed=0, n_validations_failed=0,
            response_actions_taken=(),
            notes="connected but no validator wired")

    try:
        n_passed, n_failed = validator(control, data)
    except Exception as e:
        return CVRRunResult(
            run_id=run_id, control_id=control.control_id,
            stage_completed=CVRStage.CONNECT,
            connect_success=True, validate_success=False,
            n_validations_passed=0, n_validations_failed=0,
            response_actions_taken=(),
            notes=f"validator failed: {type(e).__name__}: {e}")

    # RESPOND (only if there are failures to respond to)
    actions: Tuple[CVRResponseAction, ...] = ()
    if n_failed > 0 and responder is not None:
        try:
            actions = responder(control, n_passed, n_failed)
        except Exception:
            actions = ()
    elif n_failed == 0:
        actions = (CVRResponseAction.NO_ACTION_REQUIRED,)

    return CVRRunResult(
        run_id=run_id, control_id=control.control_id,
        stage_completed=CVRStage.RESPOND,
        connect_success=True, validate_success=True,
        n_validations_passed=n_passed,
        n_validations_failed=n_failed,
        response_actions_taken=actions,
        notes=(
            f"complete: {n_passed} passed, {n_failed} failed, "
            f"{len(actions)} actions"))


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class AuditCoreEngine:
    """End-to-end orchestrator for audit universe + planning + monitoring."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._entities: Dict[str, AuditableEntity] = {}
        self._controls: Dict[str, Control] = {}
        self._test_results: List[ControlTestResult] = []
        self._working_papers: Dict[str, WorkingPaper] = {}
        self._cvr_runs: List[CVRRunResult] = []

    # ── Universe ───────────────────────────────────────────────────────
    def register_entity(self, e: AuditableEntity) -> None:
        if e.entity_id in self._entities:
            raise ValueError(f"entity {e.entity_id} already registered")
        self._entities[e.entity_id] = e

    def get_entity(self, entity_id: str) -> AuditableEntity:
        if entity_id not in self._entities:
            raise KeyError(f"entity {entity_id} not found")
        return self._entities[entity_id]

    def critical_entities(self) -> Tuple[AuditableEntity, ...]:
        return tuple(
            e for e in self._entities.values()
            if e.residual_risk == RiskRating.CRITICAL)

    # ── Risk-based planning ───────────────────────────────────────────
    def build_annual_plan(
        self, *, fiscal_year: int, as_of: Optional[date] = None,
    ) -> Tuple[AuditPlanItem, ...]:
        return build_annual_audit_plan(
            entities=list(self._entities.values()),
            fiscal_year=fiscal_year,
            as_of=as_of or date.today())

    # ── Controls ───────────────────────────────────────────────────────
    def register_control(self, c: Control) -> None:
        if c.control_id in self._controls:
            raise ValueError(f"control {c.control_id} already registered")
        if c.entity_id not in self._entities:
            raise ValueError(
                f"control {c.control_id} references missing entity "
                f"{c.entity_id}")
        self._controls[c.control_id] = c

    def get_control(self, control_id: str) -> Control:
        if control_id not in self._controls:
            raise KeyError(f"control {control_id} not found")
        return self._controls[control_id]

    def controls_for_entity(
        self, entity_id: str) -> Tuple[Control, ...]:
        return tuple(
            c for c in self._controls.values()
            if c.entity_id == entity_id)

    # ── Continuous monitoring ─────────────────────────────────────────
    def execute_test(
        self,
        *,
        control_id: str,
        test_id: str,
        test_date: str,
        automated_tester: Optional[Callable] = None,
    ) -> ControlTestResult:
        control = self.get_control(control_id)
        result = execute_control_test(
            control=control, test_id=test_id, test_date=test_date,
            automated_tester=automated_tester)
        self._test_results.append(result)
        return result

    def failed_tests(self) -> Tuple[ControlTestResult, ...]:
        return tuple(r for r in self._test_results if r.is_failure())

    def overdue_remediations(
        self, *, as_of: Optional[date] = None,
    ) -> Tuple[ControlTestResult, ...]:
        if as_of is None:
            as_of = date.today()
        out = []
        for r in self._test_results:
            if not r.is_actionable_now():
                continue
            if r.remediation_due is None:
                continue
            try:
                due = date.fromisoformat(r.remediation_due)
            except ValueError:
                continue
            if as_of > due:
                out.append(r)
        return tuple(out)

    # ── Working papers ─────────────────────────────────────────────────
    def file_paper(self, p: WorkingPaper) -> None:
        if p.paper_id in self._working_papers:
            raise ValueError(f"paper {p.paper_id} already filed")
        self._working_papers[p.paper_id] = p

    def get_paper(self, paper_id: str) -> WorkingPaper:
        if paper_id not in self._working_papers:
            raise KeyError(f"paper {paper_id} not found")
        return self._working_papers[paper_id]

    def papers_for_engagement(
        self, engagement_id: str) -> Tuple[WorkingPaper, ...]:
        return tuple(
            p for p in self._working_papers.values()
            if p.audit_engagement_id == engagement_id)

    # ── Connect-Validate-Respond ──────────────────────────────────────
    def run_cvr(
        self,
        *,
        run_id: str,
        control_id: str,
        connector: Optional[Callable] = None,
        validator: Optional[Callable] = None,
        responder: Optional[Callable] = None,
    ) -> CVRRunResult:
        control = self.get_control(control_id)
        result = run_connect_validate_respond(
            run_id=run_id, control=control,
            connector=connector, validator=validator,
            responder=responder)
        self._cvr_runs.append(result)
        return result

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(
        self, *, as_of: Optional[date] = None,
    ) -> Dict[str, object]:
        return {
            "entity": self.entity_name,
            "n_entities": len(self._entities),
            "n_critical_entities": len(self.critical_entities()),
            "n_controls": len(self._controls),
            "n_tests_executed": len(self._test_results),
            "n_tests_failed": len(self.failed_tests()),
            "n_overdue_remediations": len(
                self.overdue_remediations(as_of=as_of)),
            "n_working_papers": len(self._working_papers),
            "n_cvr_runs": len(self._cvr_runs),
            "n_cvr_complete": sum(
                1 for r in self._cvr_runs if r.fully_completed()),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_entity(eid="E1", risk=RiskRating.MEDIUM,
                    last="2025-01-15"):
    return AuditableEntity(
        entity_id=eid, entity_name=f"Entity {eid}",
        entity_type=AuditableEntityType.PROCESS,
        inherent_risk=RiskRating.HIGH,
        residual_risk=risk, last_audit_date=last)


def _make_control(cid="C1", eid="E1"):
    return Control(
        control_id=cid, control_name=f"Control {cid}",
        control_description="test control",
        entity_id=eid,
        control_type=ControlType.PREVENTIVE,
        control_nature=ControlNature.AUTOMATED,
        control_frequency=ControlFrequency.DAILY)


def _test_risk_rating_values():
    assert RISK_RATING_VALUE[RiskRating.CRITICAL] == 5
    assert RISK_RATING_VALUE[RiskRating.VERY_LOW] == 1


def _test_entity_risk_score():
    e = AuditableEntity(
        entity_id="E", entity_name="X",
        entity_type=AuditableEntityType.PROCESS,
        inherent_risk=RiskRating.HIGH,
        residual_risk=RiskRating.MEDIUM)
    assert e.risk_score() == 7   # 4 + 3


def _test_frequency_critical_annual():
    assert determine_frequency(RiskRating.CRITICAL) == AuditFrequency.ANNUAL


def _test_frequency_very_low_as_required():
    assert (determine_frequency(RiskRating.VERY_LOW)
              == AuditFrequency.AS_REQUIRED)


def _test_audit_due_never_audited():
    e = _make_entity(last=None)
    assert is_audit_due(
        entity=e, frequency=AuditFrequency.ANNUAL,
        as_of=date(2026, 1, 1))


def _test_audit_due_within_cycle():
    e = _make_entity(last="2025-06-01")
    # 8 months later — within annual cycle
    assert not is_audit_due(
        entity=e, frequency=AuditFrequency.ANNUAL,
        as_of=date(2026, 2, 1))


def _test_audit_due_past_cycle():
    e = _make_entity(last="2024-06-01")
    # 18 months later — past annual cycle
    assert is_audit_due(
        entity=e, frequency=AuditFrequency.ANNUAL,
        as_of=date(2025, 12, 1))


def _test_audit_due_as_required_never():
    e = _make_entity(last="2020-01-01")
    # AS_REQUIRED never auto-due
    assert not is_audit_due(
        entity=e, frequency=AuditFrequency.AS_REQUIRED,
        as_of=date(2026, 1, 1))


def _test_build_plan_prioritizes_critical():
    entities = [
        AuditableEntity(
            entity_id="LOW", entity_name="Low risk",
            entity_type=AuditableEntityType.PROCESS,
            inherent_risk=RiskRating.LOW,
            residual_risk=RiskRating.LOW,
            last_audit_date=None),
        AuditableEntity(
            entity_id="CRIT", entity_name="Critical",
            entity_type=AuditableEntityType.PROCESS,
            inherent_risk=RiskRating.CRITICAL,
            residual_risk=RiskRating.CRITICAL,
            last_audit_date=None),
    ]
    plan = build_annual_audit_plan(
        entities=entities, fiscal_year=2026,
        as_of=date(2026, 1, 1))
    # CRITICAL entity should appear first (higher risk_score)
    assert plan[0].entity_id == "CRIT"
    assert plan[0].planned_quarter == "2026-Q1"
    # LOW goes to Q3/Q4
    assert plan[1].planned_quarter in ("2026-Q3", "2026-Q4")


def _test_build_plan_excludes_recently_audited():
    """Recently audited entities are NOT in the plan (still within cycle)."""
    entities = [
        AuditableEntity(
            entity_id="RECENT", entity_name="Just audited",
            entity_type=AuditableEntityType.PROCESS,
            inherent_risk=RiskRating.HIGH,
            residual_risk=RiskRating.HIGH,
            last_audit_date="2025-12-01"),    # 1 month ago
    ]
    plan = build_annual_audit_plan(
        entities=entities, fiscal_year=2026,
        as_of=date(2026, 1, 1))
    assert len(plan) == 0


def _test_execute_test_no_provider_returns_requires_provider():
    """Rule 7 — no automated_tester → REQUIRES_PROVIDER, not silent EFFECTIVE."""
    c = _make_control()
    r = execute_control_test(
        control=c, test_id="T1", test_date="2026-01-15")
    assert r.verdict == ControlTestVerdict.REQUIRES_PROVIDER
    assert "no automated_tester" in r.notes


def _test_execute_test_with_provider_effective():
    c = _make_control()
    def tester(control):
        return (ControlTestVerdict.EFFECTIVE, 100, 0)
    r = execute_control_test(
        control=c, test_id="T1", test_date="2026-01-15",
        automated_tester=tester)
    assert r.verdict == ControlTestVerdict.EFFECTIVE
    assert r.sample_size == 100


def _test_execute_test_high_failure_rate_critical():
    """50%+ exception rate → CRITICAL severity."""
    c = _make_control()
    def tester(control):
        return (ControlTestVerdict.DEFICIENT_OPERATING, 100, 60)
    r = execute_control_test(
        control=c, test_id="T1", test_date="2026-01-15",
        automated_tester=tester)
    assert r.severity == ControlSeverity.CRITICAL
    # Remediation deadline = test_date + 7 days
    assert r.remediation_due == "2026-01-22"


def _test_execute_test_low_exception_rate_low_severity():
    """1% exception rate → LOW severity."""
    c = _make_control()
    def tester(control):
        return (ControlTestVerdict.PARTIAL, 100, 1)
    r = execute_control_test(
        control=c, test_id="T1", test_date="2026-01-15",
        automated_tester=tester)
    assert r.severity == ControlSeverity.LOW
    # 90 day remediation
    assert r.remediation_due == "2026-04-15"


def _test_execute_test_failure_returns_inconclusive():
    """Tester exception → INCONCLUSIVE, not crash."""
    c = _make_control()
    def failing_tester(control):
        raise ConnectionError("API down")
    r = execute_control_test(
        control=c, test_id="T1", test_date="2026-01-15",
        automated_tester=failing_tester)
    assert r.verdict == ControlTestVerdict.INCONCLUSIVE


def _test_test_result_is_failure_classifier():
    eff = ControlTestResult(
        test_id="T", control_id="C", test_date="t",
        verdict=ControlTestVerdict.EFFECTIVE)
    assert not eff.is_failure()
    fail = ControlTestResult(
        test_id="T", control_id="C", test_date="t",
        verdict=ControlTestVerdict.DEFICIENT_OPERATING,
        severity=ControlSeverity.HIGH)
    assert fail.is_failure()
    assert fail.is_actionable_now()


def _test_paper_hash_integrity():
    content = b"audit working paper content"
    h = compute_paper_hash(content)
    p = WorkingPaper(
        paper_id="WP1",
        paper_type=WorkingPaperType.TEST_RESULTS,
        audit_engagement_id="ENG1",
        title="Test Results", prepared_by_user_id="alice",
        prepared_at="2026-01-15T10:00:00Z",
        sha256_content_hash=h)
    assert p.integrity_check(current_content=content)
    # Tampered content fails
    assert not p.integrity_check(
        current_content=b"tampered content")


def _test_paper_retention_policy_seven_years():
    assert DEFAULT_WORKING_PAPER_RETENTION_YEARS == 7


def _test_cvr_no_connector_stops_at_connect():
    c = _make_control()
    r = run_connect_validate_respond(
        run_id="R1", control=c)
    assert r.stage_completed == CVRStage.CONNECT
    assert not r.connect_success


def _test_cvr_full_success_path():
    c = _make_control()
    def connector(control):
        return (True, [{"id": 1}, {"id": 2}, {"id": 3}])
    def validator(control, data):
        return (3, 0)
    def responder(control, passed, failed):
        return ()
    r = run_connect_validate_respond(
        run_id="R1", control=c,
        connector=connector, validator=validator,
        responder=responder)
    assert r.stage_completed == CVRStage.RESPOND
    assert r.fully_completed()
    assert r.n_validations_passed == 3
    assert CVRResponseAction.NO_ACTION_REQUIRED in r.response_actions_taken


def _test_cvr_validation_failures_trigger_response():
    c = _make_control()
    def connector(control):
        return (True, [{"id": 1}, {"id": 2}])
    def validator(control, data):
        return (0, 2)    # all fail
    def responder(control, passed, failed):
        return (CVRResponseAction.LOG_FINDING,
                  CVRResponseAction.OPEN_TICKET,
                  CVRResponseAction.NOTIFY_OWNER)
    r = run_connect_validate_respond(
        run_id="R1", control=c,
        connector=connector, validator=validator, responder=responder)
    assert r.fully_completed()
    assert r.n_validations_failed == 2
    assert len(r.response_actions_taken) == 3


def _test_cvr_connector_failure_handled():
    c = _make_control()
    def failing_conn(control):
        raise ConnectionError("DB down")
    r = run_connect_validate_respond(
        run_id="R1", control=c, connector=failing_conn)
    assert r.stage_completed == CVRStage.CONNECT
    assert not r.connect_success
    assert "ConnectionError" in r.notes


def _test_engine_register_entity_dup_raises():
    eng = AuditCoreEngine()
    eng.register_entity(_make_entity())
    try:
        eng.register_entity(_make_entity())
        assert False
    except ValueError:
        pass


def _test_engine_control_requires_entity():
    eng = AuditCoreEngine()
    try:
        eng.register_control(_make_control(eid="MISSING"))
        assert False
    except ValueError:
        pass


def _test_engine_critical_entities():
    eng = AuditCoreEngine()
    eng.register_entity(_make_entity(eid="A", risk=RiskRating.CRITICAL))
    eng.register_entity(_make_entity(eid="B", risk=RiskRating.LOW))
    crits = eng.critical_entities()
    assert len(crits) == 1
    assert crits[0].entity_id == "A"


def _test_engine_overdue_remediations():
    eng = AuditCoreEngine()
    eng.register_entity(_make_entity())
    eng.register_control(_make_control())

    def critical_tester(control):
        return (ControlTestVerdict.DEFICIENT_OPERATING, 10, 8)

    eng.execute_test(
        control_id="C1", test_id="T1",
        test_date="2026-01-01",    # CRITICAL → 7-day deadline
        automated_tester=critical_tester)
    overdue = eng.overdue_remediations(as_of=date(2026, 1, 15))
    assert len(overdue) == 1


def _test_engine_board_summary_empty():
    eng = AuditCoreEngine()
    s = eng.board_summary()
    assert s["n_entities"] == 0


def _test_engine_board_summary_aggregates():
    eng = AuditCoreEngine()
    eng.register_entity(_make_entity(eid="E1",
                                          risk=RiskRating.CRITICAL))
    eng.register_control(_make_control(cid="C1", eid="E1"))
    s = eng.board_summary()
    assert s["n_entities"] == 1
    assert s["n_critical_entities"] == 1
    assert s["n_controls"] == 1


def self_test() -> None:
    tests = [
        _test_risk_rating_values,
        _test_entity_risk_score,
        _test_frequency_critical_annual,
        _test_frequency_very_low_as_required,
        _test_audit_due_never_audited,
        _test_audit_due_within_cycle,
        _test_audit_due_past_cycle,
        _test_audit_due_as_required_never,
        _test_build_plan_prioritizes_critical,
        _test_build_plan_excludes_recently_audited,
        _test_execute_test_no_provider_returns_requires_provider,
        _test_execute_test_with_provider_effective,
        _test_execute_test_high_failure_rate_critical,
        _test_execute_test_low_exception_rate_low_severity,
        _test_execute_test_failure_returns_inconclusive,
        _test_test_result_is_failure_classifier,
        _test_paper_hash_integrity,
        _test_paper_retention_policy_seven_years,
        _test_cvr_no_connector_stops_at_connect,
        _test_cvr_full_success_path,
        _test_cvr_validation_failures_trigger_response,
        _test_cvr_connector_failure_handled,
        _test_engine_register_entity_dup_raises,
        _test_engine_control_requires_entity,
        _test_engine_critical_entities,
        _test_engine_overdue_remediations,
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
        print(f"✗ audit_core self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ audit_core self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

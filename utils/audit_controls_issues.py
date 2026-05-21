"""utils/audit_controls_issues.py — v10.24 Phase 2 batch 4 (Audit/GRC arc batch 2).

╔════════════════════════════════════════════════════════════════════════╗
║  CONTROL TESTING LIBRARY + ISSUE TRACKING + CONTROL GRAPH + TICKETING  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (issue mismanagement = open audit findings to       ║
║              regulators; un-tested controls = false assurance)         ║
║  Implements 4 of 17 Audit/GRC standards from registry:                  ║
║    ENH-204:    Issue Tracking & Remediation                             ║
║    ENH-206:    Automated Control Testing                                ║
║    ENH-AUD-R1: Control-Graph Cross-Framework Mapping                    ║
║    ENH-AUD-R4: Automated Remediation Ticketing Integration              ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IIA IPPF Standard 2500 — monitoring progress (issue tracking)       ║
║    IIA IPPF Standard 2600 — communicating risk acceptance              ║
║    COSO IC + ERM frameworks                                             ║
║    COBIT 2019 — IT governance + audit framework                        ║
║    ISO 27001:2022 — information security controls                      ║
║    NIST Cybersecurity Framework (CSF) v2.0                              ║
║    PCI DSS v4.0 — payment card industry                                ║
║    SOX §404 — internal control reporting + remediation                ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk controls     ║
║    CBK CRMF April 2021 §7.5 — issue management                         ║
║    Basel BCBS 239 §11 — completeness, timeliness                       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.23 audit_core:                                       ║
║    ControlTestResult.is_failure() → triggers Issue creation            ║
║    Control.framework_refs → indexes into ControlGraph                   ║
║                                                                         ║
║  Honesty Rule 1: every issue lifecycle transition is logged with       ║
║  before/after state; explicit OVERDUE detection vs CLOSED.              ║
║  Honesty Rule 7: ticketing integration is callable hook; without       ║
║  external system wired, internal ticket records still preserved.       ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import (
    Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)


SPEC_DEVIATION_NOTE = (
    "Ticketing integration is via callable hook (Rule 7). Without injected "
    "ticket_creator, engine creates internal-only TicketStub records. "
    "Cross-framework mappings are seed values; production deployments "
    "extend per their applicable framework set.")


# ════════════════════════════════════════════════════════════════════════
# Issue Tracking & Remediation (ENH-204)
# ════════════════════════════════════════════════════════════════════════

class IssueSource(Enum):
    """Origin of an audit issue."""
    INTERNAL_AUDIT_FINDING = "INTERNAL_AUDIT_FINDING"
    CONTROL_TEST_FAILURE = "CONTROL_TEST_FAILURE"      # from v10.23
    EXTERNAL_AUDIT_FINDING = "EXTERNAL_AUDIT_FINDING"
    REGULATOR_LETTER = "REGULATOR_LETTER"               # CBK supervisory
    WHISTLEBLOWER = "WHISTLEBLOWER"
    SELF_IDENTIFIED = "SELF_IDENTIFIED"                 # management
    INCIDENT_INVESTIGATION = "INCIDENT_INVESTIGATION"


class IssueStatus(Enum):
    """Lifecycle states for an issue."""
    OPEN = "OPEN"                          # logged, not yet assigned
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"   # remediation done, awaiting verification
    CLOSED = "CLOSED"
    DEFERRED = "DEFERRED"                   # accepted by management with sign-off
    REJECTED = "REJECTED"                    # not a valid issue
    REOPENED = "REOPENED"                    # closed but recurred


# Allowed transitions per IPPF Std 2500
ALLOWED_ISSUE_TRANSITIONS: Mapping[
    IssueStatus, Tuple[IssueStatus, ...]] = {
    IssueStatus.OPEN: (
        IssueStatus.ASSIGNED, IssueStatus.REJECTED,
        IssueStatus.DEFERRED),
    IssueStatus.ASSIGNED: (
        IssueStatus.IN_PROGRESS, IssueStatus.DEFERRED,
        IssueStatus.REJECTED),
    IssueStatus.IN_PROGRESS: (
        IssueStatus.PENDING_VERIFICATION, IssueStatus.DEFERRED),
    IssueStatus.PENDING_VERIFICATION: (
        IssueStatus.CLOSED, IssueStatus.IN_PROGRESS),    # verification fail → back
    IssueStatus.CLOSED: (IssueStatus.REOPENED,),
    IssueStatus.REOPENED: (
        IssueStatus.ASSIGNED, IssueStatus.IN_PROGRESS),
    IssueStatus.DEFERRED: (
        IssueStatus.ASSIGNED, IssueStatus.CLOSED),
    IssueStatus.REJECTED: (),    # terminal
}


def is_valid_issue_transition(
    from_status: IssueStatus, to_status: IssueStatus,
) -> bool:
    return to_status in ALLOWED_ISSUE_TRANSITIONS.get(from_status, ())


def is_terminal_issue_status(status: IssueStatus) -> bool:
    """Issues that don't accept further transitions."""
    return status == IssueStatus.REJECTED


class IssueSeverity(Enum):
    """Severity tied to control framework."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Per CBK CRMF §7.5 + IPPF Std 2500 — remediation deadlines by severity
DEFAULT_ISSUE_REMEDIATION_DAYS: Mapping[IssueSeverity, int] = {
    IssueSeverity.CRITICAL: 7,
    IssueSeverity.HIGH: 30,
    IssueSeverity.MEDIUM: 60,
    IssueSeverity.LOW: 90,
}


class IssueAgingBucket(Enum):
    """Aging buckets for open issues."""
    FRESH = "FRESH"                # within remediation deadline
    APPROACHING = "APPROACHING"    # ≤ 25% of deadline remaining
    OVERDUE = "OVERDUE"            # past deadline
    AGED = "AGED"                   # > 30 days past deadline


def compute_issue_aging(
    *,
    days_past_deadline: int,
    days_remaining: int,
    sla_days: int,
) -> IssueAgingBucket:
    """Aging classification for an open issue."""
    if days_past_deadline > 30:
        return IssueAgingBucket.AGED
    if days_past_deadline > 0:
        return IssueAgingBucket.OVERDUE
    # Approaching: ≤ 25% of original deadline remaining
    if days_remaining <= max(1, sla_days // 4):
        return IssueAgingBucket.APPROACHING
    return IssueAgingBucket.FRESH


@dataclass(frozen=True)
class Issue:
    """An audit finding requiring remediation."""
    issue_id: str
    source: IssueSource
    severity: IssueSeverity
    status: IssueStatus
    description: str
    raised_date: str                       # ISO-8601
    raised_by_user_id: str
    target_control_id: Optional[str] = None
    target_entity_id: Optional[str] = None
    related_test_id: Optional[str] = None    # links to v10.23 ControlTestResult
    assigned_to_user_id: Optional[str] = None
    deadline_date: Optional[str] = None
    closed_date: Optional[str] = None
    remediation_plan: str = ""
    notes: str = ""

    def days_open(self, *, as_of: date) -> int:
        try:
            raised = date.fromisoformat(self.raised_date)
        except ValueError:
            return 0
        return max(0, (as_of - raised).days)

    def days_to_deadline(self, *, as_of: date) -> Optional[int]:
        if self.deadline_date is None:
            return None
        try:
            dl = date.fromisoformat(self.deadline_date)
        except ValueError:
            return None
        return (dl - as_of).days

    def is_overdue(self, *, as_of: date) -> bool:
        if self.status in (IssueStatus.CLOSED, IssueStatus.REJECTED):
            return False
        days = self.days_to_deadline(as_of=as_of)
        return days is not None and days < 0

    def aging(self, *, as_of: date) -> IssueAgingBucket:
        if self.deadline_date is None:
            # No deadline set — treat as FRESH if open
            return IssueAgingBucket.FRESH
        days_to_dl = self.days_to_deadline(as_of=as_of)
        if days_to_dl is None:
            return IssueAgingBucket.FRESH
        sla_days = DEFAULT_ISSUE_REMEDIATION_DAYS.get(self.severity, 60)
        return compute_issue_aging(
            days_past_deadline=max(0, -days_to_dl),
            days_remaining=max(0, days_to_dl),
            sla_days=sla_days)


def compute_issue_deadline(
    *, raised_date: date, severity: IssueSeverity,
) -> date:
    """Compute remediation deadline from raised date + severity."""
    days = DEFAULT_ISSUE_REMEDIATION_DAYS[severity]
    return raised_date + timedelta(days=days)


# ════════════════════════════════════════════════════════════════════════
# Automated Control Testing (ENH-206)
# ════════════════════════════════════════════════════════════════════════

class TestScriptLanguage(Enum):
    """Test script source language (for documentation only)."""
    SQL = "SQL"
    PYTHON = "PYTHON"
    SPL = "SPL"                       # Splunk Search Processing Language
    KQL = "KQL"                       # Microsoft Kusto
    SHELL = "SHELL"
    REGEX = "REGEX"
    DECLARATIVE = "DECLARATIVE"       # YAML-based, parsed at runtime


class TestScheduleStatus(Enum):
    SCHEDULED = "SCHEDULED"
    DUE = "DUE"
    OVERDUE = "OVERDUE"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class TestScript:
    """A test script for automated control testing."""
    script_id: str
    target_control_id: str
    script_language: TestScriptLanguage
    script_description: str
    expected_sample_size: int = 0
    expected_max_exceptions: int = 0       # > this triggers failure
    framework_refs: Tuple[str, ...] = ()    # which frameworks this evidences
    notes: str = ""


@dataclass(frozen=True)
class TestSchedule:
    """When to run a test script."""
    schedule_id: str
    script_id: str
    next_run_date: str                  # ISO-8601
    cadence_days: int                    # e.g., 1 daily, 7 weekly
    last_run_date: Optional[str] = None
    status: TestScheduleStatus = TestScheduleStatus.SCHEDULED
    notes: str = ""

    def is_due(self, *, as_of: date) -> bool:
        if self.status == TestScheduleStatus.DISABLED:
            return False
        try:
            next_run = date.fromisoformat(self.next_run_date)
        except ValueError:
            return False
        return as_of >= next_run

    def is_overdue(self, *, as_of: date,
                       overdue_days: int = 1) -> bool:
        if self.status == TestScheduleStatus.DISABLED:
            return False
        try:
            next_run = date.fromisoformat(self.next_run_date)
        except ValueError:
            return False
        return (as_of - next_run).days >= overdue_days


@dataclass(frozen=True)
class TestCoverageReport:
    """Coverage of automated tests across the control universe."""
    n_controls_total: int
    n_controls_with_automated_test: int
    n_controls_without_test: int
    coverage_pct: float
    by_framework: Mapping[str, Tuple[int, int]]    # framework → (covered, total)
    notes: str = ""

    def coverage_passes_threshold(
        self, *, threshold_pct: float = 80.0,
    ) -> bool:
        return self.coverage_pct >= threshold_pct


# ════════════════════════════════════════════════════════════════════════
# Control-Graph Cross-Framework Mapping (ENH-AUD-R1)
# ════════════════════════════════════════════════════════════════════════

class ControlFramework(Enum):
    """Major control frameworks for cross-mapping."""
    COSO_IC = "COSO_IC"                # COSO Internal Control
    COSO_ERM = "COSO_ERM"              # COSO Enterprise Risk Management
    COBIT_2019 = "COBIT_2019"          # ISACA COBIT
    ISO_27001 = "ISO_27001"            # information security
    ISO_27002 = "ISO_27002"            # information security controls
    NIST_CSF = "NIST_CSF"              # cybersecurity framework
    NIST_800_53 = "NIST_800_53"        # security controls
    PCI_DSS = "PCI_DSS"                # payment card industry
    SOX_404 = "SOX_404"                # Sarbanes-Oxley
    CBK_PG_02 = "CBK_PG_02"            # CBK operational risk
    CBK_CRMF = "CBK_CRMF"              # CBK risk mgmt framework
    BASEL_BCBS_239 = "BASEL_BCBS_239"  # data risk
    GDPR = "GDPR"                       # EU data protection
    KENYA_DPA = "KENYA_DPA"            # Kenya Data Protection Act 2019


# Seed cross-framework mappings — common controls that map across frameworks
# Format: (canonical control concept) → ((framework, framework_ref), ...)
DEFAULT_CROSS_FRAMEWORK_MAPPINGS: Mapping[
    str, Tuple[Tuple[ControlFramework, str], ...]] = {
    "ACCESS_CONTROL_LOGICAL": (
        (ControlFramework.COSO_IC, "CC6.1"),
        (ControlFramework.ISO_27001, "A.9.1"),
        (ControlFramework.ISO_27002, "A.9.4"),
        (ControlFramework.NIST_CSF, "PR.AC-1"),
        (ControlFramework.NIST_800_53, "AC-2"),
        (ControlFramework.PCI_DSS, "7.1"),
        (ControlFramework.COBIT_2019, "DSS05.04"),
    ),
    "SEGREGATION_OF_DUTIES": (
        (ControlFramework.COSO_IC, "CC5.3"),
        (ControlFramework.SOX_404, "ICFR-SOD"),
        (ControlFramework.NIST_800_53, "AC-5"),
        (ControlFramework.COBIT_2019, "APO13.02"),
        (ControlFramework.CBK_PG_02, "PG02-SOD"),
    ),
    "CHANGE_MANAGEMENT": (
        (ControlFramework.COSO_IC, "CC8.1"),
        (ControlFramework.COBIT_2019, "BAI06"),
        (ControlFramework.ISO_27001, "A.12.1"),
        (ControlFramework.NIST_CSF, "PR.IP-3"),
        (ControlFramework.PCI_DSS, "6.4"),
    ),
    "INCIDENT_RESPONSE": (
        (ControlFramework.COSO_IC, "CC7.4"),
        (ControlFramework.ISO_27001, "A.16.1"),
        (ControlFramework.NIST_CSF, "RS.RP-1"),
        (ControlFramework.NIST_800_53, "IR-4"),
        (ControlFramework.GDPR, "Art.33"),
        (ControlFramework.KENYA_DPA, "S.43"),
    ),
    "DATA_BACKUP_RECOVERY": (
        (ControlFramework.COSO_IC, "CC9.1"),
        (ControlFramework.ISO_27001, "A.12.3"),
        (ControlFramework.NIST_CSF, "PR.IP-4"),
        (ControlFramework.NIST_800_53, "CP-9"),
        (ControlFramework.BASEL_BCBS_239, "P11"),
    ),
    "ENCRYPTION_DATA_AT_REST": (
        (ControlFramework.ISO_27001, "A.10.1"),
        (ControlFramework.NIST_CSF, "PR.DS-1"),
        (ControlFramework.NIST_800_53, "SC-28"),
        (ControlFramework.PCI_DSS, "3.4"),
        (ControlFramework.GDPR, "Art.32"),
        (ControlFramework.KENYA_DPA, "S.41"),
    ),
    "AUDIT_LOGGING": (
        (ControlFramework.COSO_IC, "CC4.1"),
        (ControlFramework.ISO_27001, "A.12.4"),
        (ControlFramework.NIST_CSF, "DE.CM-1"),
        (ControlFramework.NIST_800_53, "AU-2"),
        (ControlFramework.PCI_DSS, "10.1"),
        (ControlFramework.SOX_404, "ICFR-LOG"),
    ),
    "VENDOR_RISK_MANAGEMENT": (
        (ControlFramework.COSO_ERM, "Risk.4"),
        (ControlFramework.NIST_CSF, "ID.SC-1"),
        (ControlFramework.NIST_800_53, "SR-2"),
        (ControlFramework.COBIT_2019, "APO10"),
        (ControlFramework.CBK_PG_02, "PG02-VENDOR"),
    ),
    "RECONCILIATION_INTEGRITY": (
        (ControlFramework.COSO_IC, "CC4.2"),
        (ControlFramework.SOX_404, "ICFR-RECON"),
        (ControlFramework.BASEL_BCBS_239, "P12"),
        (ControlFramework.CBK_CRMF, "S6.5"),
    ),
    "ACCESS_REVIEW_PERIODIC": (
        (ControlFramework.COSO_IC, "CC6.2"),
        (ControlFramework.ISO_27001, "A.9.2.5"),
        (ControlFramework.NIST_800_53, "AC-2(3)"),
        (ControlFramework.PCI_DSS, "7.2.4"),
        (ControlFramework.SOX_404, "ICFR-ACCESS"),
    ),
}


@dataclass(frozen=True)
class FrameworkMapping:
    """Cross-framework mapping for a single control."""
    control_id: str
    canonical_concept: str               # e.g., "ACCESS_CONTROL_LOGICAL"
    framework_refs: Tuple[Tuple[ControlFramework, str], ...]
    notes: str = ""


def get_canonical_concepts() -> FrozenSet[str]:
    """All known canonical concepts in the seed registry."""
    return frozenset(DEFAULT_CROSS_FRAMEWORK_MAPPINGS.keys())


def get_frameworks_covered_by_concept(
    concept: str,
) -> Tuple[ControlFramework, ...]:
    """Frameworks satisfied by mapping a control to a canonical concept."""
    refs = DEFAULT_CROSS_FRAMEWORK_MAPPINGS.get(concept, ())
    return tuple(fw for fw, _ in refs)


def coverage_by_framework(
    *, mappings: Sequence[FrameworkMapping],
) -> Mapping[ControlFramework, int]:
    """Count of controls mapped to each framework."""
    counts: Dict[ControlFramework, int] = {}
    for m in mappings:
        for fw, _ in m.framework_refs:
            counts[fw] = counts.get(fw, 0) + 1
    return counts


# ════════════════════════════════════════════════════════════════════════
# Automated Remediation Ticketing (ENH-AUD-R4)
# ════════════════════════════════════════════════════════════════════════

class TicketingSystem(Enum):
    """External ticketing systems supported."""
    JIRA = "JIRA"
    SERVICENOW = "SERVICENOW"
    GITHUB_ISSUES = "GITHUB_ISSUES"
    AZURE_DEVOPS = "AZURE_DEVOPS"
    INTERNAL_ONLY = "INTERNAL_ONLY"      # no external system


class TicketStatus(Enum):
    """Ticket lifecycle status (synced from external system)."""
    DRAFT = "DRAFT"
    CREATED = "CREATED"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    SYNC_FAILED = "SYNC_FAILED"          # external system unreachable


@dataclass(frozen=True)
class TicketStub:
    """A ticket reference — internal record + optional external link."""
    ticket_stub_id: str
    issue_id: str                          # links back to Issue
    ticketing_system: TicketingSystem
    external_ticket_id: Optional[str]      # set after successful creation
    external_url: Optional[str]
    status: TicketStatus
    created_at: str
    last_synced_at: Optional[str] = None
    notes: str = ""


def create_ticket_stub(
    *,
    issue: Issue,
    ticketing_system: TicketingSystem,
    stub_id: str,
    timestamp: str,
    ticket_creator: Optional[
        Callable[[Issue], Tuple[str, str]]] = None,
) -> TicketStub:
    """Create a ticket stub, optionally calling external ticketing.

    Per Rule 7 — without `ticket_creator` callable, the stub is created
    as INTERNAL_ONLY with status=DRAFT. No fabricated external ticket ID.
    """
    if ticket_creator is None or ticketing_system == TicketingSystem.INTERNAL_ONLY:
        return TicketStub(
            ticket_stub_id=stub_id, issue_id=issue.issue_id,
            ticketing_system=TicketingSystem.INTERNAL_ONLY,
            external_ticket_id=None, external_url=None,
            status=TicketStatus.DRAFT,
            created_at=timestamp,
            notes=(
                "no ticket_creator wired — Rule 7: internal-only stub, "
                "no external ticket created"
                if ticket_creator is None
                else "INTERNAL_ONLY system selected"))

    try:
        ext_id, ext_url = ticket_creator(issue)
    except Exception as e:
        return TicketStub(
            ticket_stub_id=stub_id, issue_id=issue.issue_id,
            ticketing_system=ticketing_system,
            external_ticket_id=None, external_url=None,
            status=TicketStatus.SYNC_FAILED,
            created_at=timestamp,
            notes=f"creation failed: {type(e).__name__}: {e}")

    return TicketStub(
        ticket_stub_id=stub_id, issue_id=issue.issue_id,
        ticketing_system=ticketing_system,
        external_ticket_id=ext_id, external_url=ext_url,
        status=TicketStatus.CREATED,
        created_at=timestamp, last_synced_at=timestamp,
        notes="external ticket created successfully")


def sync_ticket_status(
    *,
    stub: TicketStub,
    timestamp: str,
    status_fetcher: Optional[
        Callable[[TicketStub], TicketStatus]] = None,
) -> TicketStub:
    """Refresh ticket status from external system."""
    if status_fetcher is None or stub.external_ticket_id is None:
        return stub    # nothing to sync

    try:
        new_status = status_fetcher(stub)
    except Exception as e:
        return TicketStub(
            ticket_stub_id=stub.ticket_stub_id,
            issue_id=stub.issue_id,
            ticketing_system=stub.ticketing_system,
            external_ticket_id=stub.external_ticket_id,
            external_url=stub.external_url,
            status=TicketStatus.SYNC_FAILED,
            created_at=stub.created_at, last_synced_at=timestamp,
            notes=f"sync failed: {type(e).__name__}: {e}")

    return TicketStub(
        ticket_stub_id=stub.ticket_stub_id,
        issue_id=stub.issue_id,
        ticketing_system=stub.ticketing_system,
        external_ticket_id=stub.external_ticket_id,
        external_url=stub.external_url,
        status=new_status,
        created_at=stub.created_at, last_synced_at=timestamp,
        notes=f"synced status={new_status.value}")


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class AuditControlsIssuesEngine:
    """End-to-end orchestrator for issue tracking + testing + framework
    + ticketing.

    Composes with v10.23 audit_core: takes failed ControlTestResults
    and converts them to Issues; provides framework cross-mapping for
    Controls; manages the Issue lifecycle through ticketing integration.
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._issues: Dict[str, Issue] = {}
        self._test_scripts: Dict[str, TestScript] = {}
        self._test_schedules: Dict[str, TestSchedule] = {}
        self._mappings: Dict[str, FrameworkMapping] = {}
        self._ticket_stubs: Dict[str, TicketStub] = {}
        self._issue_transitions: List[
            Tuple[str, IssueStatus, IssueStatus, str]] = []

    # ── Issues (ENH-204) ───────────────────────────────────────────────
    def register_issue(self, issue: Issue) -> None:
        if issue.issue_id in self._issues:
            raise ValueError(
                f"issue {issue.issue_id} already registered")
        self._issues[issue.issue_id] = issue

    def get_issue(self, issue_id: str) -> Issue:
        if issue_id not in self._issues:
            raise KeyError(f"issue {issue_id} not found")
        return self._issues[issue_id]

    def transition_issue(
        self,
        *,
        issue_id: str,
        to_status: IssueStatus,
        actor: str,
        timestamp: str,
        notes: str = "",
    ) -> Issue:
        existing = self.get_issue(issue_id)
        if not is_valid_issue_transition(existing.status, to_status):
            allowed = ALLOWED_ISSUE_TRANSITIONS.get(existing.status, ())
            raise ValueError(
                f"invalid issue transition {existing.status.value} → "
                f"{to_status.value}; allowed: "
                f"{[s.value for s in allowed]}")

        self._issue_transitions.append(
            (issue_id, existing.status, to_status, actor))

        closed_date = (
            timestamp[:10] if to_status == IssueStatus.CLOSED
            else existing.closed_date)

        updated = Issue(
            issue_id=existing.issue_id,
            source=existing.source,
            severity=existing.severity,
            status=to_status,
            description=existing.description,
            raised_date=existing.raised_date,
            raised_by_user_id=existing.raised_by_user_id,
            target_control_id=existing.target_control_id,
            target_entity_id=existing.target_entity_id,
            related_test_id=existing.related_test_id,
            assigned_to_user_id=existing.assigned_to_user_id,
            deadline_date=existing.deadline_date,
            closed_date=closed_date,
            remediation_plan=existing.remediation_plan,
            notes=(
                existing.notes + "\n" + notes if notes
                else existing.notes))
        self._issues[issue_id] = updated
        return updated

    def overdue_issues(
        self, *, as_of: Optional[date] = None,
    ) -> Tuple[Issue, ...]:
        if as_of is None:
            as_of = date.today()
        return tuple(
            i for i in self._issues.values()
            if i.is_overdue(as_of=as_of))

    def issues_by_aging(
        self, *, as_of: Optional[date] = None,
    ) -> Mapping[IssueAgingBucket, Tuple[Issue, ...]]:
        if as_of is None:
            as_of = date.today()
        buckets: Dict[IssueAgingBucket, List[Issue]] = {
            b: [] for b in IssueAgingBucket}
        for issue in self._issues.values():
            if issue.status in (
                    IssueStatus.CLOSED, IssueStatus.REJECTED):
                continue
            buckets[issue.aging(as_of=as_of)].append(issue)
        return {b: tuple(items) for b, items in buckets.items()}

    # ── Test scripts (ENH-206) ────────────────────────────────────────
    def register_test_script(self, s: TestScript) -> None:
        self._test_scripts[s.script_id] = s

    def register_test_schedule(self, sch: TestSchedule) -> None:
        self._test_schedules[sch.schedule_id] = sch

    def due_test_schedules(
        self, *, as_of: Optional[date] = None,
    ) -> Tuple[TestSchedule, ...]:
        if as_of is None:
            as_of = date.today()
        return tuple(
            sch for sch in self._test_schedules.values()
            if sch.is_due(as_of=as_of))

    def compute_coverage(
        self, *, all_control_ids: Sequence[str],
        framework_filter: Optional[ControlFramework] = None,
    ) -> TestCoverageReport:
        """Compute test coverage across the control universe."""
        controls_with_tests = {
            s.target_control_id for s in self._test_scripts.values()}
        n_total = len(set(all_control_ids))
        n_covered = sum(
            1 for cid in set(all_control_ids)
            if cid in controls_with_tests)
        n_missing = n_total - n_covered

        # Per-framework coverage from mappings
        by_fw: Dict[str, Tuple[int, int]] = {}
        for mapping in self._mappings.values():
            for fw, _ in mapping.framework_refs:
                fw_name = fw.value
                covered, total = by_fw.get(fw_name, (0, 0))
                if mapping.control_id in controls_with_tests:
                    covered += 1
                total += 1
                by_fw[fw_name] = (covered, total)

        coverage_pct = (
            (n_covered / n_total * 100.0) if n_total > 0 else 0.0)

        return TestCoverageReport(
            n_controls_total=n_total,
            n_controls_with_automated_test=n_covered,
            n_controls_without_test=n_missing,
            coverage_pct=coverage_pct,
            by_framework=by_fw,
            notes=f"coverage computed across {n_total} controls")

    # ── Framework mapping (ENH-AUD-R1) ────────────────────────────────
    def register_mapping(self, m: FrameworkMapping) -> None:
        self._mappings[m.control_id] = m

    def map_control_by_concept(
        self, *, control_id: str, canonical_concept: str,
    ) -> FrameworkMapping:
        """Auto-create mapping using seed canonical concept."""
        if canonical_concept not in DEFAULT_CROSS_FRAMEWORK_MAPPINGS:
            raise ValueError(
                f"unknown canonical concept '{canonical_concept}'; "
                f"known: {sorted(get_canonical_concepts())}")
        refs = DEFAULT_CROSS_FRAMEWORK_MAPPINGS[canonical_concept]
        mapping = FrameworkMapping(
            control_id=control_id,
            canonical_concept=canonical_concept,
            framework_refs=refs,
            notes=f"auto-mapped via seed '{canonical_concept}'")
        self.register_mapping(mapping)
        return mapping

    def coverage_for_framework(
        self, framework: ControlFramework,
    ) -> int:
        """How many controls reference this framework."""
        return sum(
            1 for m in self._mappings.values()
            if any(fw == framework for fw, _ in m.framework_refs))

    # ── Ticketing (ENH-AUD-R4) ────────────────────────────────────────
    def open_ticket_for_issue(
        self,
        *,
        issue_id: str,
        ticketing_system: TicketingSystem,
        stub_id: str,
        timestamp: str,
        ticket_creator: Optional[Callable] = None,
    ) -> TicketStub:
        issue = self.get_issue(issue_id)
        stub = create_ticket_stub(
            issue=issue, ticketing_system=ticketing_system,
            stub_id=stub_id, timestamp=timestamp,
            ticket_creator=ticket_creator)
        self._ticket_stubs[stub_id] = stub
        return stub

    def sync_all_ticket_statuses(
        self, *, timestamp: str,
        status_fetcher: Optional[Callable] = None,
    ) -> Tuple[TicketStub, ...]:
        synced = []
        for stub_id, stub in list(self._ticket_stubs.items()):
            updated = sync_ticket_status(
                stub=stub, timestamp=timestamp,
                status_fetcher=status_fetcher)
            self._ticket_stubs[stub_id] = updated
            synced.append(updated)
        return tuple(synced)

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(
        self, *, as_of: Optional[date] = None,
    ) -> Dict[str, object]:
        if as_of is None:
            as_of = date.today()
        by_aging = self.issues_by_aging(as_of=as_of)
        n_open = sum(
            1 for i in self._issues.values()
            if i.status not in (
                IssueStatus.CLOSED, IssueStatus.REJECTED))
        return {
            "entity": self.entity_name,
            "n_issues_total": len(self._issues),
            "n_issues_open": n_open,
            "n_issues_overdue": len(self.overdue_issues(as_of=as_of)),
            "n_issues_aged": len(by_aging.get(IssueAgingBucket.AGED, ())),
            "n_test_scripts": len(self._test_scripts),
            "n_test_schedules": len(self._test_schedules),
            "n_due_test_schedules": len(
                self.due_test_schedules(as_of=as_of)),
            "n_framework_mappings": len(self._mappings),
            "n_ticket_stubs": len(self._ticket_stubs),
            "n_external_tickets": sum(
                1 for s in self._ticket_stubs.values()
                if s.external_ticket_id is not None),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_issue(iid="I1", status=IssueStatus.OPEN,
                  severity=IssueSeverity.HIGH, raised="2026-01-01",
                  deadline="2026-01-31"):
    return Issue(
        issue_id=iid, source=IssueSource.CONTROL_TEST_FAILURE,
        severity=severity, status=status,
        description="test issue", raised_date=raised,
        raised_by_user_id="alice",
        deadline_date=deadline)


def _test_issue_transitions_terminal_states():
    terminals = [
        s for s in IssueStatus
        if is_terminal_issue_status(s)]
    assert IssueStatus.REJECTED in terminals


def _test_valid_issue_transition_open_to_assigned():
    assert is_valid_issue_transition(
        IssueStatus.OPEN, IssueStatus.ASSIGNED)


def _test_invalid_issue_transition_open_to_closed():
    """Cannot skip directly from OPEN to CLOSED."""
    assert not is_valid_issue_transition(
        IssueStatus.OPEN, IssueStatus.CLOSED)


def _test_issue_deadline_critical_seven_days():
    dl = compute_issue_deadline(
        raised_date=date(2026, 1, 1),
        severity=IssueSeverity.CRITICAL)
    assert dl == date(2026, 1, 8)


def _test_issue_deadline_low_ninety_days():
    dl = compute_issue_deadline(
        raised_date=date(2026, 1, 1),
        severity=IssueSeverity.LOW)
    assert dl == date(2026, 4, 1)


def _test_issue_aging_fresh():
    bucket = compute_issue_aging(
        days_past_deadline=0, days_remaining=20, sla_days=30)
    assert bucket == IssueAgingBucket.FRESH


def _test_issue_aging_approaching():
    """Days remaining ≤ 25% of SLA → APPROACHING."""
    bucket = compute_issue_aging(
        days_past_deadline=0, days_remaining=5, sla_days=30)
    assert bucket == IssueAgingBucket.APPROACHING


def _test_issue_aging_overdue():
    bucket = compute_issue_aging(
        days_past_deadline=15, days_remaining=0, sla_days=30)
    assert bucket == IssueAgingBucket.OVERDUE


def _test_issue_aging_aged():
    """> 30 days past deadline → AGED."""
    bucket = compute_issue_aging(
        days_past_deadline=45, days_remaining=0, sla_days=30)
    assert bucket == IssueAgingBucket.AGED


def _test_issue_overdue_detected():
    issue = _make_issue(deadline="2026-01-15")
    assert issue.is_overdue(as_of=date(2026, 2, 1))


def _test_issue_closed_not_overdue():
    issue = _make_issue(
        status=IssueStatus.CLOSED, deadline="2026-01-15")
    assert not issue.is_overdue(as_of=date(2026, 2, 1))


def _test_canonical_concepts_loaded():
    concepts = get_canonical_concepts()
    assert "ACCESS_CONTROL_LOGICAL" in concepts
    assert "SEGREGATION_OF_DUTIES" in concepts
    assert "INCIDENT_RESPONSE" in concepts


def _test_framework_coverage_for_concept():
    fws = get_frameworks_covered_by_concept("ACCESS_CONTROL_LOGICAL")
    assert ControlFramework.ISO_27001 in fws
    assert ControlFramework.NIST_CSF in fws
    assert ControlFramework.PCI_DSS in fws


def _test_unknown_concept_returns_empty():
    fws = get_frameworks_covered_by_concept("UNKNOWN_CONCEPT")
    assert len(fws) == 0


def _test_test_schedule_due_detection():
    sch = TestSchedule(
        schedule_id="S1", script_id="X",
        next_run_date="2026-01-15", cadence_days=7)
    assert sch.is_due(as_of=date(2026, 1, 16))
    assert not sch.is_due(as_of=date(2026, 1, 14))


def _test_test_schedule_disabled_never_due():
    sch = TestSchedule(
        schedule_id="S1", script_id="X",
        next_run_date="2026-01-15", cadence_days=7,
        status=TestScheduleStatus.DISABLED)
    assert not sch.is_due(as_of=date(2026, 1, 16))


def _test_ticket_stub_no_creator_internal_only():
    """Rule 7 — without ticket_creator, stub is INTERNAL_ONLY draft."""
    issue = _make_issue()
    stub = create_ticket_stub(
        issue=issue, ticketing_system=TicketingSystem.JIRA,
        stub_id="TS1", timestamp="t")
    assert stub.ticketing_system == TicketingSystem.INTERNAL_ONLY
    assert stub.external_ticket_id is None
    assert stub.status == TicketStatus.DRAFT
    assert "Rule 7" in stub.notes


def _test_ticket_stub_with_creator_external_id_set():
    issue = _make_issue()
    def fake_creator(i):
        return ("PROJ-1234", "https://jira/PROJ-1234")
    stub = create_ticket_stub(
        issue=issue, ticketing_system=TicketingSystem.JIRA,
        stub_id="TS1", timestamp="t",
        ticket_creator=fake_creator)
    assert stub.external_ticket_id == "PROJ-1234"
    assert stub.status == TicketStatus.CREATED


def _test_ticket_stub_creator_failure_handled():
    """Creator exception → SYNC_FAILED, not crash."""
    issue = _make_issue()
    def failing_creator(i):
        raise ConnectionError("Jira API down")
    stub = create_ticket_stub(
        issue=issue, ticketing_system=TicketingSystem.JIRA,
        stub_id="TS1", timestamp="t",
        ticket_creator=failing_creator)
    assert stub.status == TicketStatus.SYNC_FAILED
    assert "ConnectionError" in stub.notes


def _test_ticket_status_sync():
    stub = TicketStub(
        ticket_stub_id="TS1", issue_id="I1",
        ticketing_system=TicketingSystem.JIRA,
        external_ticket_id="PROJ-1234",
        external_url="https://x/y", status=TicketStatus.OPEN,
        created_at="t1")

    def fetcher(s):
        return TicketStatus.RESOLVED
    updated = sync_ticket_status(
        stub=stub, timestamp="t2", status_fetcher=fetcher)
    assert updated.status == TicketStatus.RESOLVED
    assert updated.last_synced_at == "t2"


def _test_engine_register_issue():
    eng = AuditControlsIssuesEngine()
    eng.register_issue(_make_issue())
    assert eng.get_issue("I1").severity == IssueSeverity.HIGH


def _test_engine_invalid_transition_raises():
    eng = AuditControlsIssuesEngine()
    eng.register_issue(_make_issue())
    try:
        # OPEN → CLOSED is invalid
        eng.transition_issue(
            issue_id="I1", to_status=IssueStatus.CLOSED,
            actor="x", timestamp="t")
        assert False
    except ValueError as e:
        assert "invalid issue transition" in str(e)


def _test_engine_valid_transition_path():
    eng = AuditControlsIssuesEngine()
    eng.register_issue(_make_issue())
    eng.transition_issue(
        issue_id="I1", to_status=IssueStatus.ASSIGNED,
        actor="x", timestamp="t1")
    eng.transition_issue(
        issue_id="I1", to_status=IssueStatus.IN_PROGRESS,
        actor="y", timestamp="t2")
    eng.transition_issue(
        issue_id="I1", to_status=IssueStatus.PENDING_VERIFICATION,
        actor="z", timestamp="t3")
    eng.transition_issue(
        issue_id="I1", to_status=IssueStatus.CLOSED,
        actor="w", timestamp="2026-01-30T00:00:00Z")
    issue = eng.get_issue("I1")
    assert issue.status == IssueStatus.CLOSED
    assert issue.closed_date == "2026-01-30"


def _test_engine_overdue_detection():
    eng = AuditControlsIssuesEngine()
    eng.register_issue(_make_issue(deadline="2026-01-15"))
    overdue = eng.overdue_issues(as_of=date(2026, 2, 1))
    assert len(overdue) == 1


def _test_engine_map_control_by_concept():
    eng = AuditControlsIssuesEngine()
    mapping = eng.map_control_by_concept(
        control_id="CTRL-001",
        canonical_concept="ACCESS_CONTROL_LOGICAL")
    assert mapping.control_id == "CTRL-001"
    assert ControlFramework.ISO_27001 in (
        fw for fw, _ in mapping.framework_refs)


def _test_engine_unknown_concept_raises():
    eng = AuditControlsIssuesEngine()
    try:
        eng.map_control_by_concept(
            control_id="CTRL-001", canonical_concept="MYTHICAL")
        assert False
    except ValueError:
        pass


def _test_engine_compute_coverage():
    eng = AuditControlsIssuesEngine()
    eng.register_test_script(TestScript(
        script_id="TS1", target_control_id="CTRL-001",
        script_language=TestScriptLanguage.SQL,
        script_description="x"))
    report = eng.compute_coverage(
        all_control_ids=["CTRL-001", "CTRL-002", "CTRL-003"])
    assert report.n_controls_total == 3
    assert report.n_controls_with_automated_test == 1
    assert report.coverage_pct < 50.0
    assert not report.coverage_passes_threshold(threshold_pct=80.0)


def _test_engine_open_ticket_for_issue():
    eng = AuditControlsIssuesEngine()
    eng.register_issue(_make_issue())
    stub = eng.open_ticket_for_issue(
        issue_id="I1",
        ticketing_system=TicketingSystem.INTERNAL_ONLY,
        stub_id="TS1", timestamp="t")
    assert stub.issue_id == "I1"


def _test_engine_board_summary_empty():
    eng = AuditControlsIssuesEngine()
    s = eng.board_summary()
    assert s["n_issues_total"] == 0


def _test_engine_board_summary_aggregates():
    eng = AuditControlsIssuesEngine()
    eng.register_issue(_make_issue(iid="I1", deadline="2026-01-15"))
    eng.register_issue(_make_issue(
        iid="I2", status=IssueStatus.CLOSED,
        deadline="2026-01-15"))
    eng.register_test_script(TestScript(
        script_id="TS1", target_control_id="CTRL-001",
        script_language=TestScriptLanguage.SQL,
        script_description="x"))
    s = eng.board_summary(as_of=date(2026, 2, 1))
    assert s["n_issues_total"] == 2
    assert s["n_issues_open"] == 1    # I2 closed


def self_test() -> None:
    tests = [
        _test_issue_transitions_terminal_states,
        _test_valid_issue_transition_open_to_assigned,
        _test_invalid_issue_transition_open_to_closed,
        _test_issue_deadline_critical_seven_days,
        _test_issue_deadline_low_ninety_days,
        _test_issue_aging_fresh,
        _test_issue_aging_approaching,
        _test_issue_aging_overdue,
        _test_issue_aging_aged,
        _test_issue_overdue_detected,
        _test_issue_closed_not_overdue,
        _test_canonical_concepts_loaded,
        _test_framework_coverage_for_concept,
        _test_unknown_concept_returns_empty,
        _test_test_schedule_due_detection,
        _test_test_schedule_disabled_never_due,
        _test_ticket_stub_no_creator_internal_only,
        _test_ticket_stub_with_creator_external_id_set,
        _test_ticket_stub_creator_failure_handled,
        _test_ticket_status_sync,
        _test_engine_register_issue,
        _test_engine_invalid_transition_raises,
        _test_engine_valid_transition_path,
        _test_engine_overdue_detection,
        _test_engine_map_control_by_concept,
        _test_engine_unknown_concept_raises,
        _test_engine_compute_coverage,
        _test_engine_open_ticket_for_issue,
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
        print(f"✗ audit_controls_issues self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ audit_controls_issues self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

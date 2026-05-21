"""utils/audit_dashboards_portal.py — v10.26 Phase 2 batch 4 (Audit/GRC arc batch 4).

╔════════════════════════════════════════════════════════════════════════╗
║  AUDITOR DASHBOARD + EXTERNAL PORTAL + COMMITTEE REPORTING + BOARD RISK║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (board reporting drives capital + strategy          ║
║              decisions; external auditor portal handles privileged    ║
║              audit data; engagement scope leaks → privacy breach)     ║
║  Implements 4 of 17 Audit/GRC standards from registry:                  ║
║    ENH-207:    Auditor Dashboard & Mobile Access                        ║
║    ENH-208:    External Auditor Portal                                  ║
║    ENH-209:    Audit Committee Reporting                                ║
║    ENH-AUD-R3: Board-Ready Risk-Quantified Dashboards                   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IIA IPPF Standard 2440 — disseminating results                       ║
║    IIA IPPF Standard 2450 — overall opinions                            ║
║    IIA IPPF Standard 2500 — monitoring progress                         ║
║    COSO ERM — board reporting                                            ║
║    CBK CRMF April 2021 §7.7 — audit committee reporting                ║
║    CBK Banking Act §44 — internal audit reporting to board             ║
║    Sarbanes-Oxley §301 — audit committee responsibilities             ║
║    PCAOB AS 1301 — communications with audit committees               ║
║    Basel BCBS — internal audit principles (2012)                        ║
║    UK Corporate Governance Code — audit committee provisions           ║
║    NACD Risk Oversight — board responsibility framework                ║
║    NIST SP 800-30 Rev. 1 — quantitative risk metrics                   ║
║    Kenya Data Protection Act 2019 §28-§31 — controller obligations    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.23 + v10.24 + v10.25 (full Audit/GRC stack).        ║
║                                                                         ║
║  Honesty Rule 1: every dashboard metric shows source + freshness;      ║
║  external auditor portal sessions log every accessed object;           ║
║  board risk metrics surface confidence levels + assumptions.           ║
║  Honesty Rule 7: external system integrations (mobile push, audit    ║
║  committee email) are callable hooks; without wiring, in-memory only. ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "Dashboard rendering, mobile push notifications, and external auditor "
    "portal authentication are per-deployment integrations. The framework "
    "produces structured data + audit logs; the rendering and external "
    "communication wires through callable hooks per Rule 7."
)


# ════════════════════════════════════════════════════════════════════════
# Auditor Dashboard & Mobile Access (ENH-207)
# ════════════════════════════════════════════════════════════════════════

class DashboardViewMode(Enum):
    """Viewport density modes for the auditor dashboard."""
    DESKTOP_FULL = "DESKTOP_FULL"        # ≥1280px, all KPIs + drill-down
    TABLET = "TABLET"                     # 768-1279px
    MOBILE_DENSE = "MOBILE_DENSE"         # <768px, 6-8 KPIs visible
    MOBILE_SUMMARY = "MOBILE_SUMMARY"    # <768px, top 3-4 KPIs only


class KPIDirection(Enum):
    """Whether higher or lower values are better for a KPI."""
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    TARGET_RANGE = "TARGET_RANGE"        # within a band is good


class KPIStatus(Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AuditorDashboardKPI:
    """One KPI metric with G/A/R thresholds + direction awareness."""
    kpi_name: str
    current_value: Decimal
    target_value: Optional[Decimal] = None
    threshold_amber: Optional[Decimal] = None
    threshold_red: Optional[Decimal] = None
    direction: KPIDirection = KPIDirection.LOWER_IS_BETTER
    target_range_low: Optional[Decimal] = None
    target_range_high: Optional[Decimal] = None
    unit: str = ""
    source_engine: str = ""               # e.g., "audit_core"
    last_refreshed_at_utc: str = ""
    notes: str = ""

    def status(self) -> KPIStatus:
        """Derive G/A/R status with direction awareness."""
        if (self.threshold_amber is None and self.threshold_red is None
                and self.target_range_low is None
                and self.target_range_high is None):
            return KPIStatus.UNKNOWN

        if self.direction == KPIDirection.TARGET_RANGE:
            if (self.target_range_low is not None
                    and self.target_range_high is not None):
                if (self.current_value < self.target_range_low
                        or self.current_value > self.target_range_high):
                    return KPIStatus.RED
                return KPIStatus.GREEN
            return KPIStatus.UNKNOWN

        if self.direction == KPIDirection.HIGHER_IS_BETTER:
            if (self.threshold_red is not None
                    and self.current_value < self.threshold_red):
                return KPIStatus.RED
            if (self.threshold_amber is not None
                    and self.current_value < self.threshold_amber):
                return KPIStatus.AMBER
            return KPIStatus.GREEN

        # LOWER_IS_BETTER
        if (self.threshold_red is not None
                and self.current_value > self.threshold_red):
            return KPIStatus.RED
        if (self.threshold_amber is not None
                and self.current_value > self.threshold_amber):
            return KPIStatus.AMBER
        return KPIStatus.GREEN


# Default KPI catalog for the auditor dashboard
def build_default_kpi_catalog(
    *,
    n_open_issues: int,
    n_overdue_issues: int,
    n_failed_tests: int,
    n_overdue_remediations: int,
    n_overdue_alerts: int,
    n_critical_anomalies: int,
    n_concentration_breaches: int,
    n_overdue_assessments: int,
    refreshed_at_utc: str = "",
) -> Tuple[AuditorDashboardKPI, ...]:
    """Build default KPI catalog from v10.23/24/25 board summaries."""
    return (
        AuditorDashboardKPI(
            kpi_name="Open Issues",
            current_value=Decimal(n_open_issues),
            threshold_amber=Decimal("50"),
            threshold_red=Decimal("100"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_controls_issues",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Overdue Issues",
            current_value=Decimal(n_overdue_issues),
            threshold_amber=Decimal("5"),
            threshold_red=Decimal("20"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_controls_issues",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Failed Control Tests",
            current_value=Decimal(n_failed_tests),
            threshold_amber=Decimal("10"),
            threshold_red=Decimal("30"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_core",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Overdue Remediations",
            current_value=Decimal(n_overdue_remediations),
            threshold_amber=Decimal("0"),
            threshold_red=Decimal("5"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_core",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Overdue Assurance Alerts",
            current_value=Decimal(n_overdue_alerts),
            threshold_amber=Decimal("0"),
            threshold_red=Decimal("3"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_analytics_vendor",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Critical Anomalies",
            current_value=Decimal(n_critical_anomalies),
            threshold_amber=Decimal("3"),
            threshold_red=Decimal("10"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_analytics_vendor",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Vendor Concentration Breaches",
            current_value=Decimal(n_concentration_breaches),
            threshold_amber=Decimal("0"),
            threshold_red=Decimal("3"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_analytics_vendor",
            last_refreshed_at_utc=refreshed_at_utc),
        AuditorDashboardKPI(
            kpi_name="Overdue Vendor Assessments",
            current_value=Decimal(n_overdue_assessments),
            threshold_amber=Decimal("3"),
            threshold_red=Decimal("10"),
            direction=KPIDirection.LOWER_IS_BETTER, unit="count",
            source_engine="audit_analytics_vendor",
            last_refreshed_at_utc=refreshed_at_utc),
    )


@dataclass(frozen=True)
class AuditorDashboardSnapshot:
    """Complete dashboard snapshot."""
    snapshot_id: str
    generated_at_utc: str
    view_mode: DashboardViewMode
    kpis: Tuple[AuditorDashboardKPI, ...]
    notes: str = ""

    def red_kpis(self) -> Tuple[AuditorDashboardKPI, ...]:
        return tuple(k for k in self.kpis if k.status() == KPIStatus.RED)

    def amber_kpis(self) -> Tuple[AuditorDashboardKPI, ...]:
        return tuple(
            k for k in self.kpis if k.status() == KPIStatus.AMBER)

    def overall_health(self) -> KPIStatus:
        """Worst KPI status determines overall dashboard health."""
        if any(k.status() == KPIStatus.RED for k in self.kpis):
            return KPIStatus.RED
        if any(k.status() == KPIStatus.AMBER for k in self.kpis):
            return KPIStatus.AMBER
        return KPIStatus.GREEN

    def for_mobile(
        self, *, mode: DashboardViewMode = DashboardViewMode.MOBILE_SUMMARY,
    ) -> "AuditorDashboardSnapshot":
        """Filter KPIs for mobile view (top RED + AMBER first)."""
        if mode == DashboardViewMode.MOBILE_SUMMARY:
            n_show = 4
        elif mode == DashboardViewMode.MOBILE_DENSE:
            n_show = 8
        else:
            n_show = len(self.kpis)
        # Sort: RED first, then AMBER, then GREEN
        priority = {KPIStatus.RED: 0, KPIStatus.AMBER: 1,
                      KPIStatus.GREEN: 2, KPIStatus.UNKNOWN: 3}
        sorted_kpis = sorted(
            self.kpis, key=lambda k: priority[k.status()])
        return AuditorDashboardSnapshot(
            snapshot_id=self.snapshot_id,
            generated_at_utc=self.generated_at_utc,
            view_mode=mode,
            kpis=tuple(sorted_kpis[:n_show]),
            notes=f"mobile view ({mode.value}) — {n_show} KPIs shown")


# ════════════════════════════════════════════════════════════════════════
# External Auditor Portal (ENH-208)
# ════════════════════════════════════════════════════════════════════════

class ExternalAuditorAccessLevel(Enum):
    """Access levels for external auditors."""
    READ_ONLY = "READ_ONLY"               # view only
    READ_WITH_NOTES = "READ_WITH_NOTES"   # view + add observations
    EXPORT_ALLOWED = "EXPORT_ALLOWED"     # download permitted


class ExternalAuditorRequestType(Enum):
    """Types of audit document requests."""
    PLANNING_MEMO = "PLANNING_MEMO"
    CONTROL_NARRATIVES = "CONTROL_NARRATIVES"
    TEST_RESULTS = "TEST_RESULTS"
    ISSUE_TRACKING = "ISSUE_TRACKING"
    POLICIES_PROCEDURES = "POLICIES_PROCEDURES"
    EVIDENCE_DOCUMENTS = "EVIDENCE_DOCUMENTS"
    BOARD_MINUTES = "BOARD_MINUTES"
    REGULATORY_CORRESPONDENCE = "REGULATORY_CORRESPONDENCE"
    PRIOR_AUDIT_REPORTS = "PRIOR_AUDIT_REPORTS"


@dataclass(frozen=True)
class EngagementScope:
    """What an external auditor can access during their engagement.

    Per PCAOB AS 1301 + IIA IPPF Std 2440, external auditor access must
    be scoped to their specific engagement. This dataclass codifies the
    scope.
    """
    engagement_id: str
    external_audit_firm: str               # e.g., "PwC Kenya"
    engagement_name: str                   # e.g., "FY2026 Statutory Audit"
    fiscal_period_start: str               # ISO-8601 date
    fiscal_period_end: str
    in_scope_entity_ids: Tuple[str, ...]   # which AuditableEntity IDs
    in_scope_request_types: Tuple[ExternalAuditorRequestType, ...]
    access_level: ExternalAuditorAccessLevel
    engagement_partner_email: str = ""
    valid_from: str = ""
    valid_until: str = ""
    notes: str = ""

    def is_active(self, *, as_of: date) -> bool:
        try:
            start = (
                date.fromisoformat(self.valid_from)
                if self.valid_from
                else date.fromisoformat(self.fiscal_period_start))
            end = (
                date.fromisoformat(self.valid_until)
                if self.valid_until
                else date.fromisoformat(self.fiscal_period_end)
                + timedelta(days=180))    # +6 months for completion
        except ValueError:
            return False
        return start <= as_of <= end

    def covers_request_type(
        self, request_type: ExternalAuditorRequestType,
    ) -> bool:
        return request_type in self.in_scope_request_types

    def covers_entity(self, entity_id: str) -> bool:
        return entity_id in self.in_scope_entity_ids


@dataclass(frozen=True)
class ExternalAuditorAccessLog:
    """Immutable log entry for every external auditor access."""
    log_id: str
    engagement_id: str
    auditor_user_id: str
    accessed_at_utc: str
    object_type: str                       # e.g., "WorkingPaper", "ControlTestResult"
    object_id: str
    action: str                            # "VIEW", "ANNOTATE", "DOWNLOAD"
    access_granted: bool
    denial_reason: Optional[str] = None
    notes: str = ""


def authorize_external_access(
    *,
    scope: EngagementScope,
    requested_object_type: str,
    requested_object_id: str,
    request_type: ExternalAuditorRequestType,
    requested_action: str,
    as_of: date,
) -> Tuple[bool, str]:
    """Authorize one external auditor access request.

    Returns (granted, reason). Per Rule 1 — denial reasons are explicit.
    """
    if not scope.is_active(as_of=as_of):
        return (False, "engagement scope not active for current date")
    if not scope.covers_request_type(request_type):
        return (
            False,
            f"request type {request_type.value} not in engagement scope")
    if requested_action.upper() == "DOWNLOAD":
        if scope.access_level != ExternalAuditorAccessLevel.EXPORT_ALLOWED:
            return (
                False,
                f"access level {scope.access_level.value} does not "
                f"permit download")
    if requested_action.upper() == "ANNOTATE":
        if scope.access_level == ExternalAuditorAccessLevel.READ_ONLY:
            return (
                False,
                "READ_ONLY access does not permit annotation")
    return (True, "authorized within engagement scope")


# ════════════════════════════════════════════════════════════════════════
# Audit Committee Reporting (ENH-209)
# ════════════════════════════════════════════════════════════════════════

class ReportingFrequency(Enum):
    """Audit committee reporting cadence."""
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    SEMI_ANNUAL = "SEMI_ANNUAL"
    ANNUAL = "ANNUAL"
    AD_HOC = "AD_HOC"


# CBK CRMF §7.7 + SOX §301 — minimum reporting cadence
MINIMUM_AUDIT_COMMITTEE_REPORTING = ReportingFrequency.QUARTERLY


@dataclass(frozen=True)
class RiskHeatmapCell:
    """One cell in the 5×5 likelihood × impact matrix."""
    likelihood: int                        # 1-5
    impact: int                             # 1-5
    n_risks: int
    risk_score: int                         # likelihood × impact
    risks_in_cell: Tuple[str, ...] = ()    # risk identifiers


def compute_risk_heatmap_cell(
    *, likelihood: int, impact: int,
    risk_ids: Sequence[str],
) -> RiskHeatmapCell:
    """One cell in the 5×5 risk heatmap."""
    if not (1 <= likelihood <= 5 and 1 <= impact <= 5):
        raise ValueError(
            f"likelihood and impact must be 1-5; got {likelihood}, {impact}")
    return RiskHeatmapCell(
        likelihood=likelihood, impact=impact,
        n_risks=len(risk_ids),
        risk_score=likelihood * impact,
        risks_in_cell=tuple(risk_ids))


@dataclass(frozen=True)
class PlanVsActual:
    """Annual audit plan progress vs actual."""
    fiscal_year: int
    planned_engagements: int
    completed_engagements: int
    in_progress_engagements: int
    cancelled_engagements: int
    planned_hours: int
    actual_hours_to_date: int

    def completion_pct(self) -> Decimal:
        if self.planned_engagements == 0:
            return Decimal("0")
        return (Decimal(self.completed_engagements)
                  / Decimal(self.planned_engagements)
                  * Decimal("100"))

    def hours_variance_pct(self) -> Decimal:
        if self.planned_hours == 0:
            return Decimal("0")
        return (Decimal(self.actual_hours_to_date - self.planned_hours)
                  / Decimal(self.planned_hours)
                  * Decimal("100"))


@dataclass(frozen=True)
class AuditCommitteeReport:
    """Period-end audit committee report."""
    report_id: str
    period_label: str                      # e.g., "Q1 2026"
    frequency: ReportingFrequency
    period_start: str                      # ISO-8601
    period_end: str
    generated_at_utc: str
    plan_vs_actual: PlanVsActual
    n_critical_findings: int
    n_high_findings: int
    n_overdue_remediations: int
    n_concentration_breaches: int
    risk_heatmap: Tuple[RiskHeatmapCell, ...]
    executive_summary: str = ""
    notes: str = ""


def build_risk_heatmap_summary(
    *, cells: Sequence[RiskHeatmapCell],
) -> Mapping[str, int]:
    """Categorize risks into Low/Medium/High/Critical zones."""
    summary: Dict[str, int] = {
        "low": 0,        # score 1-4
        "medium": 0,     # score 5-10
        "high": 0,       # score 11-15
        "critical": 0,   # score 16-25
    }
    for cell in cells:
        if cell.risk_score >= 16:
            summary["critical"] += cell.n_risks
        elif cell.risk_score >= 11:
            summary["high"] += cell.n_risks
        elif cell.risk_score >= 5:
            summary["medium"] += cell.n_risks
        else:
            summary["low"] += cell.n_risks
    return summary


# ════════════════════════════════════════════════════════════════════════
# Board-Ready Risk-Quantified Dashboards (ENH-AUD-R3)
# ════════════════════════════════════════════════════════════════════════

class RiskCategory(Enum):
    """Top-level risk categories for board reporting (per Basel + COSO ERM)."""
    CREDIT = "CREDIT"
    MARKET = "MARKET"
    OPERATIONAL = "OPERATIONAL"
    LIQUIDITY = "LIQUIDITY"
    STRATEGIC = "STRATEGIC"
    REPUTATIONAL = "REPUTATIONAL"
    REGULATORY = "REGULATORY"
    CYBERSECURITY = "CYBERSECURITY"
    CLIMATE = "CLIMATE"
    THIRD_PARTY = "THIRD_PARTY"


class RiskAppetiteStatus(Enum):
    """Position relative to risk appetite limits."""
    WITHIN_APPETITE = "WITHIN_APPETITE"
    APPROACHING_LIMIT = "APPROACHING_LIMIT"   # 80-99% of limit
    LIMIT_BREACH = "LIMIT_BREACH"               # ≥100% of limit
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class QuantifiedRiskMetric:
    """A board-level risk metric with quantified impact."""
    metric_name: str
    risk_category: RiskCategory
    current_value_kes: Decimal              # current exposure / loss
    appetite_limit_kes: Decimal             # board-approved limit
    expected_loss_kes: Optional[Decimal] = None     # EL = PD × LGD × EAD
    var_95_kes: Optional[Decimal] = None              # Value at Risk 95%
    confidence_level: Decimal = Decimal("0.95")
    last_calculated_at_utc: str = ""
    notes: str = ""

    def utilization_pct(self) -> Decimal:
        if self.appetite_limit_kes == Decimal("0"):
            return Decimal("0")
        return (self.current_value_kes
                  / self.appetite_limit_kes
                  * Decimal("100"))

    def appetite_status(self) -> RiskAppetiteStatus:
        if self.appetite_limit_kes == Decimal("0"):
            return RiskAppetiteStatus.UNKNOWN
        utilization = self.utilization_pct()
        if utilization >= Decimal("100"):
            return RiskAppetiteStatus.LIMIT_BREACH
        if utilization >= Decimal("80"):
            return RiskAppetiteStatus.APPROACHING_LIMIT
        return RiskAppetiteStatus.WITHIN_APPETITE


@dataclass(frozen=True)
class BoardRiskDashboard:
    """Board-level risk dashboard with all categories."""
    dashboard_id: str
    fiscal_period: str
    generated_at_utc: str
    risk_metrics: Tuple[QuantifiedRiskMetric, ...]
    notes: str = ""

    def metrics_in_breach(
        self) -> Tuple[QuantifiedRiskMetric, ...]:
        return tuple(
            m for m in self.risk_metrics
            if m.appetite_status() == RiskAppetiteStatus.LIMIT_BREACH)

    def metrics_approaching_limit(
        self) -> Tuple[QuantifiedRiskMetric, ...]:
        return tuple(
            m for m in self.risk_metrics
            if m.appetite_status()
            == RiskAppetiteStatus.APPROACHING_LIMIT)

    def metrics_by_category(
        self, category: RiskCategory,
    ) -> Tuple[QuantifiedRiskMetric, ...]:
        return tuple(
            m for m in self.risk_metrics
            if m.risk_category == category)

    def total_exposure_by_category(
        self) -> Mapping[RiskCategory, Decimal]:
        out: Dict[RiskCategory, Decimal] = {}
        for m in self.risk_metrics:
            out[m.risk_category] = (
                out.get(m.risk_category, Decimal("0"))
                + m.current_value_kes)
        return out


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator
# ════════════════════════════════════════════════════════════════════════

class AuditDashboardsPortalEngine:
    """End-to-end orchestrator for dashboards + portal + reporting."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._snapshots: Dict[str, AuditorDashboardSnapshot] = {}
        self._engagements: Dict[str, EngagementScope] = {}
        self._access_logs: List[ExternalAuditorAccessLog] = []
        self._committee_reports: Dict[str, AuditCommitteeReport] = {}
        self._board_dashboards: Dict[str, BoardRiskDashboard] = {}

    # ── Auditor dashboard (ENH-207) ───────────────────────────────────
    def build_dashboard_snapshot(
        self,
        *,
        snapshot_id: str,
        generated_at_utc: str,
        n_open_issues: int = 0,
        n_overdue_issues: int = 0,
        n_failed_tests: int = 0,
        n_overdue_remediations: int = 0,
        n_overdue_alerts: int = 0,
        n_critical_anomalies: int = 0,
        n_concentration_breaches: int = 0,
        n_overdue_assessments: int = 0,
        view_mode: DashboardViewMode = DashboardViewMode.DESKTOP_FULL,
    ) -> AuditorDashboardSnapshot:
        kpis = build_default_kpi_catalog(
            n_open_issues=n_open_issues,
            n_overdue_issues=n_overdue_issues,
            n_failed_tests=n_failed_tests,
            n_overdue_remediations=n_overdue_remediations,
            n_overdue_alerts=n_overdue_alerts,
            n_critical_anomalies=n_critical_anomalies,
            n_concentration_breaches=n_concentration_breaches,
            n_overdue_assessments=n_overdue_assessments,
            refreshed_at_utc=generated_at_utc)
        snap = AuditorDashboardSnapshot(
            snapshot_id=snapshot_id,
            generated_at_utc=generated_at_utc,
            view_mode=view_mode,
            kpis=kpis)
        self._snapshots[snapshot_id] = snap
        return snap

    def latest_snapshot(self) -> Optional[AuditorDashboardSnapshot]:
        if not self._snapshots:
            return None
        # Return by latest generated_at_utc
        return max(
            self._snapshots.values(),
            key=lambda s: s.generated_at_utc)

    # ── External auditor portal (ENH-208) ─────────────────────────────
    def register_engagement(self, e: EngagementScope) -> None:
        if e.engagement_id in self._engagements:
            raise ValueError(
                f"engagement {e.engagement_id} already registered")
        self._engagements[e.engagement_id] = e

    def get_engagement(self, engagement_id: str) -> EngagementScope:
        if engagement_id not in self._engagements:
            raise KeyError(f"engagement {engagement_id} not found")
        return self._engagements[engagement_id]

    def request_access(
        self,
        *,
        engagement_id: str,
        auditor_user_id: str,
        object_type: str,
        object_id: str,
        request_type: ExternalAuditorRequestType,
        action: str,
        timestamp: str,
        as_of: date,
    ) -> ExternalAuditorAccessLog:
        """Authorize + log an external auditor access request."""
        scope = self.get_engagement(engagement_id)
        granted, reason = authorize_external_access(
            scope=scope,
            requested_object_type=object_type,
            requested_object_id=object_id,
            request_type=request_type,
            requested_action=action,
            as_of=as_of)
        log = ExternalAuditorAccessLog(
            log_id=f"AAL-{len(self._access_logs) + 1:06d}",
            engagement_id=engagement_id,
            auditor_user_id=auditor_user_id,
            accessed_at_utc=timestamp,
            object_type=object_type,
            object_id=object_id,
            action=action,
            access_granted=granted,
            denial_reason=None if granted else reason,
            notes=reason)
        self._access_logs.append(log)
        return log

    def access_logs_for_engagement(
        self, engagement_id: str,
    ) -> Tuple[ExternalAuditorAccessLog, ...]:
        return tuple(
            log for log in self._access_logs
            if log.engagement_id == engagement_id)

    def denied_access_attempts(
        self, *, engagement_id: Optional[str] = None,
    ) -> Tuple[ExternalAuditorAccessLog, ...]:
        return tuple(
            log for log in self._access_logs
            if not log.access_granted
            and (engagement_id is None
                   or log.engagement_id == engagement_id))

    # ── Audit committee reporting (ENH-209) ───────────────────────────
    def file_committee_report(self, r: AuditCommitteeReport) -> None:
        if r.report_id in self._committee_reports:
            raise ValueError(f"report {r.report_id} already filed")
        self._committee_reports[r.report_id] = r

    def reports_for_period(
        self, *, period_start: str, period_end: str,
    ) -> Tuple[AuditCommitteeReport, ...]:
        return tuple(
            r for r in self._committee_reports.values()
            if (r.period_start >= period_start
                and r.period_end <= period_end))

    # ── Board risk dashboard (ENH-AUD-R3) ─────────────────────────────
    def file_board_dashboard(self, d: BoardRiskDashboard) -> None:
        if d.dashboard_id in self._board_dashboards:
            raise ValueError(
                f"board dashboard {d.dashboard_id} already filed")
        self._board_dashboards[d.dashboard_id] = d

    def latest_board_dashboard(
        self) -> Optional[BoardRiskDashboard]:
        if not self._board_dashboards:
            return None
        return max(
            self._board_dashboards.values(),
            key=lambda d: d.generated_at_utc)

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        latest_snap = self.latest_snapshot()
        latest_board = self.latest_board_dashboard()
        return {
            "entity": self.entity_name,
            "n_dashboard_snapshots": len(self._snapshots),
            "latest_snapshot_health": (
                latest_snap.overall_health().value
                if latest_snap else None),
            "n_engagements": len(self._engagements),
            "n_access_logs": len(self._access_logs),
            "n_denied_access_attempts": len(
                self.denied_access_attempts()),
            "n_committee_reports": len(self._committee_reports),
            "n_board_dashboards": len(self._board_dashboards),
            "n_metrics_in_breach": (
                len(latest_board.metrics_in_breach())
                if latest_board else 0),
            "n_metrics_approaching": (
                len(latest_board.metrics_approaching_limit())
                if latest_board else 0),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_kpi_status_higher_better_red():
    k = AuditorDashboardKPI(
        kpi_name="Auto-Match", current_value=Decimal("65"),
        threshold_amber=Decimal("80"),
        threshold_red=Decimal("70"),
        direction=KPIDirection.HIGHER_IS_BETTER, unit="%")
    assert k.status() == KPIStatus.RED


def _test_kpi_status_lower_better_amber():
    k = AuditorDashboardKPI(
        kpi_name="SLA Breaches", current_value=Decimal("8"),
        threshold_amber=Decimal("5"),
        threshold_red=Decimal("20"),
        direction=KPIDirection.LOWER_IS_BETTER, unit="count")
    assert k.status() == KPIStatus.AMBER


def _test_kpi_status_lower_better_green():
    k = AuditorDashboardKPI(
        kpi_name="SLA Breaches", current_value=Decimal("2"),
        threshold_amber=Decimal("5"),
        threshold_red=Decimal("20"),
        direction=KPIDirection.LOWER_IS_BETTER, unit="count")
    assert k.status() == KPIStatus.GREEN


def _test_kpi_target_range_within():
    k = AuditorDashboardKPI(
        kpi_name="Capital Ratio", current_value=Decimal("18"),
        direction=KPIDirection.TARGET_RANGE,
        target_range_low=Decimal("14.5"),
        target_range_high=Decimal("22"),
        unit="%")
    assert k.status() == KPIStatus.GREEN


def _test_kpi_target_range_below():
    k = AuditorDashboardKPI(
        kpi_name="Capital Ratio", current_value=Decimal("12"),
        direction=KPIDirection.TARGET_RANGE,
        target_range_low=Decimal("14.5"),
        target_range_high=Decimal("22"),
        unit="%")
    assert k.status() == KPIStatus.RED


def _test_kpi_no_thresholds_unknown():
    k = AuditorDashboardKPI(
        kpi_name="Coverage", current_value=Decimal("80"))
    assert k.status() == KPIStatus.UNKNOWN


def _test_default_kpi_catalog_returns_8():
    kpis = build_default_kpi_catalog(
        n_open_issues=10, n_overdue_issues=2, n_failed_tests=5,
        n_overdue_remediations=1, n_overdue_alerts=0,
        n_critical_anomalies=0, n_concentration_breaches=0,
        n_overdue_assessments=0)
    assert len(kpis) == 8


def _test_dashboard_snapshot_overall_health_red():
    snap = AuditorDashboardSnapshot(
        snapshot_id="S1", generated_at_utc="t",
        view_mode=DashboardViewMode.DESKTOP_FULL,
        kpis=(
            AuditorDashboardKPI(
                kpi_name="A", current_value=Decimal("100"),
                threshold_amber=Decimal("5"),
                threshold_red=Decimal("20"),
                direction=KPIDirection.LOWER_IS_BETTER),
            AuditorDashboardKPI(
                kpi_name="B", current_value=Decimal("1"),
                threshold_amber=Decimal("5"),
                threshold_red=Decimal("20"),
                direction=KPIDirection.LOWER_IS_BETTER),
        ))
    assert snap.overall_health() == KPIStatus.RED
    assert len(snap.red_kpis()) == 1


def _test_mobile_view_filters_to_top_4():
    snap = AuditorDashboardSnapshot(
        snapshot_id="S1", generated_at_utc="t",
        view_mode=DashboardViewMode.DESKTOP_FULL,
        kpis=tuple(
            AuditorDashboardKPI(
                kpi_name=f"K{i}",
                current_value=Decimal(str(i)),
                threshold_amber=Decimal("3"),
                threshold_red=Decimal("8"),
                direction=KPIDirection.LOWER_IS_BETTER)
            for i in range(10)))
    mobile = snap.for_mobile(
        mode=DashboardViewMode.MOBILE_SUMMARY)
    assert len(mobile.kpis) == 4
    # First should be RED (highest priority)
    assert mobile.kpis[0].status() == KPIStatus.RED


def _test_engagement_scope_active_within_period():
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="FY2026 Audit",
        fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=("E1",),
        in_scope_request_types=(
            ExternalAuditorRequestType.TEST_RESULTS,),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    assert scope.is_active(as_of=date(2026, 6, 1))
    # 6 months after period end is still active (default tolerance)
    assert scope.is_active(as_of=date(2027, 5, 1))
    # 1 year after period end is not active
    assert not scope.is_active(as_of=date(2028, 1, 1))


def _test_engagement_covers_request_type():
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="x",
        fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=("E1",),
        in_scope_request_types=(
            ExternalAuditorRequestType.TEST_RESULTS,
            ExternalAuditorRequestType.CONTROL_NARRATIVES),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    assert scope.covers_request_type(
        ExternalAuditorRequestType.TEST_RESULTS)
    assert not scope.covers_request_type(
        ExternalAuditorRequestType.BOARD_MINUTES)


def _test_authorize_outside_scope_denied():
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="x",
        fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=("E1",),
        in_scope_request_types=(
            ExternalAuditorRequestType.TEST_RESULTS,),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    granted, reason = authorize_external_access(
        scope=scope, requested_object_type="BoardMinute",
        requested_object_id="BM1",
        request_type=ExternalAuditorRequestType.BOARD_MINUTES,
        requested_action="VIEW", as_of=date(2026, 6, 1))
    assert not granted
    assert "not in engagement scope" in reason


def _test_authorize_download_without_permission_denied():
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="x",
        fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=("E1",),
        in_scope_request_types=(
            ExternalAuditorRequestType.TEST_RESULTS,),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    granted, reason = authorize_external_access(
        scope=scope, requested_object_type="TestResult",
        requested_object_id="T1",
        request_type=ExternalAuditorRequestType.TEST_RESULTS,
        requested_action="DOWNLOAD", as_of=date(2026, 6, 1))
    assert not granted
    assert "does not permit download" in reason


def _test_authorize_view_within_scope_granted():
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="x",
        fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=("E1",),
        in_scope_request_types=(
            ExternalAuditorRequestType.TEST_RESULTS,),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    granted, _ = authorize_external_access(
        scope=scope, requested_object_type="TestResult",
        requested_object_id="T1",
        request_type=ExternalAuditorRequestType.TEST_RESULTS,
        requested_action="VIEW", as_of=date(2026, 6, 1))
    assert granted


def _test_risk_heatmap_invalid_inputs_raise():
    try:
        compute_risk_heatmap_cell(
            likelihood=6, impact=3, risk_ids=("R1",))
        assert False
    except ValueError:
        pass


def _test_risk_heatmap_score_calculation():
    cell = compute_risk_heatmap_cell(
        likelihood=4, impact=5, risk_ids=("R1", "R2", "R3"))
    assert cell.risk_score == 20
    assert cell.n_risks == 3


def _test_heatmap_summary_categorizes():
    cells = (
        RiskHeatmapCell(
            likelihood=1, impact=1, n_risks=2, risk_score=1),    # low
        RiskHeatmapCell(
            likelihood=2, impact=3, n_risks=3, risk_score=6),    # medium
        RiskHeatmapCell(
            likelihood=3, impact=4, n_risks=1, risk_score=12),   # high
        RiskHeatmapCell(
            likelihood=5, impact=5, n_risks=1, risk_score=25),   # critical
    )
    summary = build_risk_heatmap_summary(cells=cells)
    assert summary["low"] == 2
    assert summary["medium"] == 3
    assert summary["high"] == 1
    assert summary["critical"] == 1


def _test_plan_vs_actual_completion():
    pva = PlanVsActual(
        fiscal_year=2026, planned_engagements=10,
        completed_engagements=4, in_progress_engagements=3,
        cancelled_engagements=1,
        planned_hours=2000, actual_hours_to_date=900)
    assert pva.completion_pct() == Decimal("40")


def _test_plan_vs_actual_hours_variance():
    pva = PlanVsActual(
        fiscal_year=2026, planned_engagements=10,
        completed_engagements=10, in_progress_engagements=0,
        cancelled_engagements=0,
        planned_hours=2000, actual_hours_to_date=2400)
    assert pva.hours_variance_pct() == Decimal("20")


def _test_quantified_risk_within_appetite():
    m = QuantifiedRiskMetric(
        metric_name="Credit VaR", risk_category=RiskCategory.CREDIT,
        current_value_kes=Decimal("50000000"),
        appetite_limit_kes=Decimal("100000000"))
    assert m.appetite_status() == RiskAppetiteStatus.WITHIN_APPETITE
    assert m.utilization_pct() == Decimal("50")


def _test_quantified_risk_approaching_limit():
    m = QuantifiedRiskMetric(
        metric_name="Op Risk", risk_category=RiskCategory.OPERATIONAL,
        current_value_kes=Decimal("85000000"),
        appetite_limit_kes=Decimal("100000000"))
    assert m.appetite_status() == RiskAppetiteStatus.APPROACHING_LIMIT


def _test_quantified_risk_breach():
    m = QuantifiedRiskMetric(
        metric_name="Cyber", risk_category=RiskCategory.CYBERSECURITY,
        current_value_kes=Decimal("105000000"),
        appetite_limit_kes=Decimal("100000000"))
    assert m.appetite_status() == RiskAppetiteStatus.LIMIT_BREACH


def _test_quantified_risk_zero_limit_unknown():
    m = QuantifiedRiskMetric(
        metric_name="Unbounded", risk_category=RiskCategory.STRATEGIC,
        current_value_kes=Decimal("100"),
        appetite_limit_kes=Decimal("0"))
    assert m.appetite_status() == RiskAppetiteStatus.UNKNOWN


def _test_board_dashboard_breaches():
    dash = BoardRiskDashboard(
        dashboard_id="BD1", fiscal_period="Q1-2026",
        generated_at_utc="t",
        risk_metrics=(
            QuantifiedRiskMetric(
                metric_name="Credit",
                risk_category=RiskCategory.CREDIT,
                current_value_kes=Decimal("50"),
                appetite_limit_kes=Decimal("100")),
            QuantifiedRiskMetric(
                metric_name="Cyber",
                risk_category=RiskCategory.CYBERSECURITY,
                current_value_kes=Decimal("110"),
                appetite_limit_kes=Decimal("100")),
        ))
    breaches = dash.metrics_in_breach()
    assert len(breaches) == 1
    assert breaches[0].metric_name == "Cyber"


def _test_board_dashboard_total_by_category():
    dash = BoardRiskDashboard(
        dashboard_id="BD1", fiscal_period="Q1-2026",
        generated_at_utc="t",
        risk_metrics=(
            QuantifiedRiskMetric(
                metric_name="Credit-1",
                risk_category=RiskCategory.CREDIT,
                current_value_kes=Decimal("100"),
                appetite_limit_kes=Decimal("200")),
            QuantifiedRiskMetric(
                metric_name="Credit-2",
                risk_category=RiskCategory.CREDIT,
                current_value_kes=Decimal("50"),
                appetite_limit_kes=Decimal("100")),
        ))
    totals = dash.total_exposure_by_category()
    assert totals[RiskCategory.CREDIT] == Decimal("150")


def _test_engine_register_engagement_dup_raises():
    eng = AuditDashboardsPortalEngine()
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="x", fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=(), in_scope_request_types=(),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    eng.register_engagement(scope)
    try:
        eng.register_engagement(scope)
        assert False
    except ValueError:
        pass


def _test_engine_request_access_logs_denied():
    eng = AuditDashboardsPortalEngine()
    scope = EngagementScope(
        engagement_id="ENG1", external_audit_firm="PwC",
        engagement_name="x", fiscal_period_start="2026-01-01",
        fiscal_period_end="2026-12-31",
        in_scope_entity_ids=("E1",),
        in_scope_request_types=(
            ExternalAuditorRequestType.TEST_RESULTS,),
        access_level=ExternalAuditorAccessLevel.READ_ONLY)
    eng.register_engagement(scope)
    log = eng.request_access(
        engagement_id="ENG1", auditor_user_id="ext_auditor_1",
        object_type="BoardMinute", object_id="BM1",
        request_type=ExternalAuditorRequestType.BOARD_MINUTES,
        action="VIEW", timestamp="t",
        as_of=date(2026, 6, 1))
    assert not log.access_granted
    assert log.denial_reason is not None
    # Should be in denied_access_attempts
    denied = eng.denied_access_attempts()
    assert len(denied) == 1


def _test_engine_dashboard_snapshot_health():
    eng = AuditDashboardsPortalEngine()
    snap = eng.build_dashboard_snapshot(
        snapshot_id="S1", generated_at_utc="t",
        n_open_issues=200,    # over threshold (100 RED)
        n_overdue_issues=2)
    assert snap.overall_health() == KPIStatus.RED


def _test_engine_board_summary_aggregates():
    eng = AuditDashboardsPortalEngine()
    eng.build_dashboard_snapshot(
        snapshot_id="S1", generated_at_utc="2026-04-01T00:00:00Z",
        n_open_issues=10)
    s = eng.board_summary()
    assert s["n_dashboard_snapshots"] == 1
    assert s["latest_snapshot_health"] == KPIStatus.GREEN.value


def _test_decimal_purity():
    m = QuantifiedRiskMetric(
        metric_name="X", risk_category=RiskCategory.CREDIT,
        current_value_kes=Decimal("100"),
        appetite_limit_kes=Decimal("200"))
    assert isinstance(m.utilization_pct(), Decimal)


def self_test() -> None:
    tests = [
        _test_kpi_status_higher_better_red,
        _test_kpi_status_lower_better_amber,
        _test_kpi_status_lower_better_green,
        _test_kpi_target_range_within,
        _test_kpi_target_range_below,
        _test_kpi_no_thresholds_unknown,
        _test_default_kpi_catalog_returns_8,
        _test_dashboard_snapshot_overall_health_red,
        _test_mobile_view_filters_to_top_4,
        _test_engagement_scope_active_within_period,
        _test_engagement_covers_request_type,
        _test_authorize_outside_scope_denied,
        _test_authorize_download_without_permission_denied,
        _test_authorize_view_within_scope_granted,
        _test_risk_heatmap_invalid_inputs_raise,
        _test_risk_heatmap_score_calculation,
        _test_heatmap_summary_categorizes,
        _test_plan_vs_actual_completion,
        _test_plan_vs_actual_hours_variance,
        _test_quantified_risk_within_appetite,
        _test_quantified_risk_approaching_limit,
        _test_quantified_risk_breach,
        _test_quantified_risk_zero_limit_unknown,
        _test_board_dashboard_breaches,
        _test_board_dashboard_total_by_category,
        _test_engine_register_engagement_dup_raises,
        _test_engine_request_access_logs_denied,
        _test_engine_dashboard_snapshot_health,
        _test_engine_board_summary_aggregates,
        _test_decimal_purity,
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
        print(f"✗ audit_dashboards_portal self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ audit_dashboards_portal self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

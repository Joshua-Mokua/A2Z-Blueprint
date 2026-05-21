"""
================================================================================
A2Z MIS 360 — Standard #83: Issue Management & Remediation Tracking Engine
================================================================================

Risk classification: Cat B (deterministic issue lifecycle and SLA management)

Computes audit/control issue management metrics:
    - classify_issue_severity(...)          -- by financial + reputational impact
    - aging_bucket(...)                     -- categorise days open
    - sla_breach_check(...)                 -- vs target remediation timeline
    - escalation_required(...)              -- escalation rules
    - kri_summary(...)                      -- KRIs (closure rate, MTTR, etc.)

Issue severities byte-for-byte:
    CRITICAL : material weakness, regulatory finding, fraud — 30 day SLA
    HIGH     : significant control gap, high financial risk — 60 day SLA
    MEDIUM   : moderate control gap, process inefficiency — 90 day SLA
    LOW      : minor observation, best practice — 180 day SLA

Aging buckets byte-for-byte:
    CURRENT     : 0-30 days
    EARLY_AGED  : 31-60 days
    AGED        : 61-90 days
    PROLONGED   : 91-180 days
    OVERDUE     : 181+ days

Issue statuses:
    OPEN, IN_PROGRESS, REMEDIATED, CLOSED, OVERDUE, ESCALATED

Escalation rules:
    - Any CRITICAL >= 30 days → Board Audit Committee
    - Any HIGH >= 60 days → Risk Committee
    - Any MEDIUM >= 90 days → Management Audit Committee
    - >= 5 issues OVERDUE in same business unit → escalate to Board

Honesty rules applied:
    Rule 1: kri ratios = None when denominators <= 0
    Rule 6: issues with missing dates excluded with count surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Issue severities byte-for-byte
ISSUE_SEVERITIES: Tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

# SLA targets in days byte-for-byte
SLA_TARGET_DAYS: Dict[str, int] = {
    "CRITICAL": 30,
    "HIGH": 60,
    "MEDIUM": 90,
    "LOW": 180,
}

# Aging bucket boundaries byte-for-byte
AGING_BUCKETS: Tuple[str, ...] = (
    "CURRENT", "EARLY_AGED", "AGED", "PROLONGED", "OVERDUE",
)

AGING_BUCKET_DAYS: Dict[str, Tuple[int, int]] = {
    "CURRENT": (0, 30),
    "EARLY_AGED": (31, 60),
    "AGED": (61, 90),
    "PROLONGED": (91, 180),
    "OVERDUE": (181, 99999),
}

# Issue statuses
ISSUE_STATUSES: Tuple[str, ...] = (
    "OPEN", "IN_PROGRESS", "REMEDIATED", "CLOSED", "OVERDUE", "ESCALATED",
)

# Escalation rules byte-for-byte (days threshold per severity)
ESCALATION_THRESHOLD_DAYS: Dict[str, int] = {
    "CRITICAL": 30,
    "HIGH": 60,
    "MEDIUM": 90,
    "LOW": 365,  # very rare for LOW
}

# Cluster escalation: N+ overdue issues in same unit triggers Board escalation
CLUSTER_ESCALATION_THRESHOLD = 5

# Severity classification thresholds (financial impact KES)
CRITICAL_IMPACT_KES = Decimal("100000000")    # 100M+
HIGH_IMPACT_KES = Decimal("10000000")          # 10M-100M
MEDIUM_IMPACT_KES = Decimal("1000000")         # 1M-10M
# LOW for anything below


@dataclass
class AuditIssue:
    issue_id: str
    description: str
    business_unit: str
    severity: Optional[str] = None  # if None, classify from impact
    status: str = "OPEN"
    raised_date: Optional[date] = None
    target_remediation_date: Optional[date] = None
    closed_date: Optional[date] = None
    estimated_financial_impact_kes: Optional[Decimal] = None
    is_regulatory_finding: bool = False
    is_fraud_related: bool = False


def _days_open(raised: date, ref: date) -> int:
    """Days between raised date and reference date (negative if future)."""
    return (ref - raised).days


def _aging_bucket(days: int) -> str:
    if days < 0:
        return "CURRENT"
    for bucket in AGING_BUCKETS:
        lo, hi = AGING_BUCKET_DAYS[bucket]
        if lo <= days <= hi:
            return bucket
    return "OVERDUE"


class IssueManagementEngine:
    """Deterministic audit issue lifecycle management."""

    @staticmethod
    def classify_issue_severity(issue: AuditIssue) -> Dict[str, Any]:
        """
        Classify severity from financial impact + flags.
        Regulatory findings or fraud → escalate to CRITICAL minimum.
        """
        if issue.estimated_financial_impact_kes is None:
            # Rule 6: cannot classify without impact
            return {
                "issue_id": issue.issue_id,
                "severity": None,
                "reason": "missing_financial_impact",
            }
        impact = issue.estimated_financial_impact_kes
        # Default classification by impact amount
        if impact >= CRITICAL_IMPACT_KES:
            severity = "CRITICAL"
        elif impact >= HIGH_IMPACT_KES:
            severity = "HIGH"
        elif impact >= MEDIUM_IMPACT_KES:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        # Escalation: regulatory finding or fraud → at least CRITICAL
        if issue.is_regulatory_finding or issue.is_fraud_related:
            severity = "CRITICAL"

        return {
            "issue_id": issue.issue_id,
            "severity": severity,
            "estimated_financial_impact_kes": str(impact.quantize(Decimal("0.01"))),
            "regulatory_escalation": issue.is_regulatory_finding,
            "fraud_escalation": issue.is_fraud_related,
            "sla_target_days": SLA_TARGET_DAYS[severity],
        }

    @staticmethod
    def aging_bucket(issue: AuditIssue, ref_date: date) -> Dict[str, Any]:
        """Compute aging bucket and days open."""
        if issue.raised_date is None:
            return {
                "issue_id": issue.issue_id,
                "aging_bucket": None,
                "days_open": None,
                "reason": "missing_raised_date",
            }
        if issue.status in ("CLOSED", "REMEDIATED") and issue.closed_date is not None:
            days = _days_open(issue.raised_date, issue.closed_date)
        else:
            days = _days_open(issue.raised_date, ref_date)
        return {
            "issue_id": issue.issue_id,
            "raised_date": issue.raised_date.isoformat(),
            "ref_date": ref_date.isoformat(),
            "days_open": days,
            "aging_bucket": _aging_bucket(days),
            "status": issue.status,
        }

    @classmethod
    def sla_breach_check(
        cls,
        issue: AuditIssue,
        ref_date: date,
    ) -> Dict[str, Any]:
        """Check if issue has breached SLA based on severity + days open."""
        if issue.raised_date is None:
            return {
                "issue_id": issue.issue_id,
                "sla_breach": None,
                "reason": "missing_raised_date",
            }
        # Resolve severity
        severity = issue.severity
        if severity is None:
            scl = cls.classify_issue_severity(issue)
            severity = scl.get("severity")
        if severity not in SLA_TARGET_DAYS:
            return {
                "issue_id": issue.issue_id,
                "sla_breach": None,
                "reason": "severity_unresolved",
            }
        sla_days = SLA_TARGET_DAYS[severity]

        # If still open, check days open
        if issue.status in ("CLOSED", "REMEDIATED"):
            if issue.closed_date is None:
                return {
                    "issue_id": issue.issue_id,
                    "sla_breach": None,
                    "reason": "missing_closed_date",
                }
            days_to_close = _days_open(issue.raised_date, issue.closed_date)
            return {
                "issue_id": issue.issue_id,
                "severity": severity,
                "sla_target_days": sla_days,
                "days_to_close": days_to_close,
                "sla_breach": days_to_close > sla_days,
                "status": issue.status,
            }
        # Open issue
        days_open = _days_open(issue.raised_date, ref_date)
        return {
            "issue_id": issue.issue_id,
            "severity": severity,
            "sla_target_days": sla_days,
            "days_open": days_open,
            "sla_breach": days_open > sla_days,
            "status": issue.status,
        }

    @classmethod
    def escalation_required(
        cls,
        issue: AuditIssue,
        ref_date: date,
    ) -> Dict[str, Any]:
        """Determine if issue requires committee escalation."""
        if issue.raised_date is None:
            return {
                "issue_id": issue.issue_id,
                "escalation_required": None,
                "reason": "missing_raised_date",
            }
        severity = issue.severity
        if severity is None:
            scl = cls.classify_issue_severity(issue)
            severity = scl.get("severity")
        if severity not in ESCALATION_THRESHOLD_DAYS:
            return {
                "issue_id": issue.issue_id,
                "escalation_required": None,
                "reason": "severity_unresolved",
            }

        # Skip closed
        if issue.status in ("CLOSED", "REMEDIATED"):
            return {
                "issue_id": issue.issue_id,
                "escalation_required": False,
                "reason": "issue_closed",
            }

        threshold = ESCALATION_THRESHOLD_DAYS[severity]
        days_open = _days_open(issue.raised_date, ref_date)
        if days_open >= threshold:
            # Determine escalation target
            if severity == "CRITICAL":
                target = "BOARD_AUDIT_COMMITTEE"
            elif severity == "HIGH":
                target = "RISK_COMMITTEE"
            elif severity == "MEDIUM":
                target = "MANAGEMENT_AUDIT_COMMITTEE"
            else:
                target = "DEPARTMENT_HEAD"
            return {
                "issue_id": issue.issue_id,
                "severity": severity,
                "days_open": days_open,
                "threshold_days": threshold,
                "escalation_required": True,
                "escalation_target": target,
            }
        return {
            "issue_id": issue.issue_id,
            "severity": severity,
            "days_open": days_open,
            "threshold_days": threshold,
            "escalation_required": False,
        }

    @classmethod
    def kri_summary(
        cls,
        issues: List[AuditIssue],
        ref_date: date,
    ) -> Dict[str, Any]:
        """
        Compute KRIs: total issues, status counts, aging distribution,
        closure rate %, mean time to remediation.
        Rule 1: ratios=None when denominators<=0.
        Rule 6: issues with missing dates excluded.
        """
        excluded = []
        status_counts = {s: 0 for s in ISSUE_STATUSES}
        aging_counts = {b: 0 for b in AGING_BUCKETS}
        severity_counts = {s: 0 for s in ISSUE_SEVERITIES}
        cluster_overdue = {}  # business_unit -> count
        ttr_samples = []  # for closed issues

        # Initial: all severities present
        for issue in issues:
            if issue.raised_date is None:
                excluded.append(issue.issue_id)
                continue
            # Resolve severity
            sev = issue.severity
            if sev is None:
                scl = cls.classify_issue_severity(issue)
                sev = scl.get("severity")
            if sev is None:
                excluded.append(issue.issue_id)
                continue
            severity_counts[sev] += 1

            status = issue.status if issue.status in ISSUE_STATUSES else "OPEN"
            status_counts[status] += 1

            ag = cls.aging_bucket(issue, ref_date)
            ab = ag.get("aging_bucket")
            if ab in aging_counts:
                aging_counts[ab] += 1

            # Cluster
            if ab == "OVERDUE":
                cluster_overdue[issue.business_unit] = cluster_overdue.get(issue.business_unit, 0) + 1

            # TTR
            if issue.status in ("CLOSED", "REMEDIATED") and issue.closed_date is not None:
                ttr = _days_open(issue.raised_date, issue.closed_date)
                ttr_samples.append(ttr)

        total = sum(status_counts.values())
        closed_count = status_counts["CLOSED"] + status_counts["REMEDIATED"]
        closure_rate = (Decimal(closed_count) / Decimal(total) * Decimal("100")
                        if total > 0 else None)
        mttr_days = (sum(ttr_samples) / len(ttr_samples)
                     if ttr_samples else None)

        # Cluster escalations
        cluster_escalations = [
            {"business_unit": bu, "overdue_count": ct}
            for bu, ct in cluster_overdue.items()
            if ct >= CLUSTER_ESCALATION_THRESHOLD
        ]

        return {
            "total_issues": total,
            "by_status": status_counts,
            "by_aging": aging_counts,
            "by_severity": severity_counts,
            "closure_rate_pct": (str(closure_rate.quantize(Decimal("0.01")))
                                 if closure_rate is not None else None),
            "mttr_days": mttr_days,
            "cluster_escalations": cluster_escalations,
            "excluded_count": len(excluded),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _issue(**kw):
    defaults = dict(
        issue_id="I1", description="Test issue",
        business_unit="RETAIL_BANKING",
        status="OPEN",
        raised_date=date(2026, 1, 1),
        estimated_financial_impact_kes=Decimal("5000000"),
    )
    defaults.update(kw)
    return AuditIssue(**defaults)


def _test_severity_classification_critical():
    i = _issue(estimated_financial_impact_kes=Decimal("200000000"))
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] == "CRITICAL"


def _test_severity_classification_high():
    i = _issue(estimated_financial_impact_kes=Decimal("50000000"))
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] == "HIGH"


def _test_severity_classification_medium():
    i = _issue(estimated_financial_impact_kes=Decimal("5000000"))
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] == "MEDIUM"


def _test_severity_classification_low():
    i = _issue(estimated_financial_impact_kes=Decimal("100000"))
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] == "LOW"


def _test_severity_regulatory_escalates_to_critical():
    """Even a small impact, if regulatory finding → CRITICAL."""
    i = _issue(estimated_financial_impact_kes=Decimal("100000"),
               is_regulatory_finding=True)
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] == "CRITICAL"


def _test_severity_fraud_escalates_to_critical():
    i = _issue(estimated_financial_impact_kes=Decimal("100000"),
               is_fraud_related=True)
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] == "CRITICAL"


def _test_severity_missing_impact_rule6():
    i = _issue(estimated_financial_impact_kes=None)
    r = IssueManagementEngine.classify_issue_severity(i)
    assert r["severity"] is None


def _test_aging_bucket_current():
    i = _issue(raised_date=date(2026, 4, 15))
    r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
    assert r["aging_bucket"] == "CURRENT"
    assert r["days_open"] == 15


def _test_aging_bucket_overdue():
    i = _issue(raised_date=date(2025, 10, 1))
    r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
    # ~211 days
    assert r["aging_bucket"] == "OVERDUE"


def _test_aging_bucket_uses_closed_date_for_closed():
    i = _issue(raised_date=date(2026, 1, 1), status="CLOSED",
               closed_date=date(2026, 2, 1))
    r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
    # Uses closed_date, not ref_date
    assert r["days_open"] == 31


def _test_aging_bucket_missing_date_rule6():
    i = _issue(raised_date=None)
    r = IssueManagementEngine.aging_bucket(i, date(2026, 4, 30))
    assert r["aging_bucket"] is None


def _test_sla_breach_high_severity():
    """HIGH severity 60 day SLA, raised 90 days ago → breach."""
    i = _issue(raised_date=date(2026, 1, 30),
               severity="HIGH", status="OPEN")
    r = IssueManagementEngine.sla_breach_check(i, date(2026, 4, 30))
    assert r["sla_breach"] is True


def _test_sla_no_breach_within_target():
    i = _issue(raised_date=date(2026, 4, 1),
               severity="HIGH", status="OPEN")
    r = IssueManagementEngine.sla_breach_check(i, date(2026, 4, 30))
    assert r["sla_breach"] is False


def _test_sla_breach_for_closed_issue_late():
    """Closed but took longer than SLA."""
    i = _issue(raised_date=date(2026, 1, 1),
               severity="HIGH", status="CLOSED",
               closed_date=date(2026, 4, 30))
    r = IssueManagementEngine.sla_breach_check(i, date(2026, 4, 30))
    # 119 days vs 60 day SLA → breach
    assert r["sla_breach"] is True


def _test_escalation_required_critical_30days():
    """CRITICAL + 30 days open → escalate to Board."""
    i = _issue(raised_date=date(2026, 3, 31),
               severity="CRITICAL", status="OPEN")
    r = IssueManagementEngine.escalation_required(i, date(2026, 4, 30))
    assert r["escalation_required"] is True
    assert r["escalation_target"] == "BOARD_AUDIT_COMMITTEE"


def _test_escalation_not_required_within_threshold():
    i = _issue(raised_date=date(2026, 4, 25),
               severity="CRITICAL", status="OPEN")
    r = IssueManagementEngine.escalation_required(i, date(2026, 4, 30))
    assert r["escalation_required"] is False


def _test_escalation_skipped_for_closed():
    i = _issue(raised_date=date(2026, 1, 1),
               severity="CRITICAL", status="CLOSED",
               closed_date=date(2026, 2, 1))
    r = IssueManagementEngine.escalation_required(i, date(2026, 4, 30))
    assert r["escalation_required"] is False
    assert r["reason"] == "issue_closed"


def _test_kri_summary_basic():
    issues = [
        _issue(issue_id="I1", severity="HIGH", status="OPEN",
               raised_date=date(2026, 4, 1)),
        _issue(issue_id="I2", severity="MEDIUM", status="CLOSED",
               raised_date=date(2026, 3, 1), closed_date=date(2026, 3, 20)),
    ]
    r = IssueManagementEngine.kri_summary(issues, date(2026, 4, 30))
    assert r["total_issues"] == 2
    assert r["closure_rate_pct"] == "50.00"


def _test_kri_summary_empty_rule1():
    r = IssueManagementEngine.kri_summary([], date(2026, 4, 30))
    assert r["closure_rate_pct"] is None


def _test_kri_summary_cluster_escalation():
    """5+ overdue issues in same unit → escalation."""
    issues = [
        _issue(issue_id=f"I{i}", business_unit="RETAIL",
               raised_date=date(2025, 8, 1), severity="HIGH",
               status="OPEN")
        for i in range(6)
    ]
    r = IssueManagementEngine.kri_summary(issues, date(2026, 4, 30))
    assert len(r["cluster_escalations"]) == 1
    assert r["cluster_escalations"][0]["business_unit"] == "RETAIL"


def _test_severities_byte_for_byte():
    expected = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    for s in expected:
        assert s in ISSUE_SEVERITIES


def _test_sla_targets_byte_for_byte():
    assert SLA_TARGET_DAYS["CRITICAL"] == 30
    assert SLA_TARGET_DAYS["HIGH"] == 60
    assert SLA_TARGET_DAYS["MEDIUM"] == 90
    assert SLA_TARGET_DAYS["LOW"] == 180


def _test_aging_buckets_byte_for_byte():
    expected = ("CURRENT", "EARLY_AGED", "AGED", "PROLONGED", "OVERDUE")
    for b in expected:
        assert b in AGING_BUCKETS


def _test_aging_bucket_days_byte_for_byte():
    assert AGING_BUCKET_DAYS["CURRENT"] == (0, 30)
    assert AGING_BUCKET_DAYS["EARLY_AGED"] == (31, 60)
    assert AGING_BUCKET_DAYS["AGED"] == (61, 90)
    assert AGING_BUCKET_DAYS["PROLONGED"] == (91, 180)


def _test_escalation_thresholds_byte_for_byte():
    assert ESCALATION_THRESHOLD_DAYS["CRITICAL"] == 30
    assert ESCALATION_THRESHOLD_DAYS["HIGH"] == 60
    assert ESCALATION_THRESHOLD_DAYS["MEDIUM"] == 90


def _test_cluster_threshold_byte_for_byte():
    assert CLUSTER_ESCALATION_THRESHOLD == 5


def self_test() -> bool:
    tests = [
        _test_severity_classification_critical,
        _test_severity_classification_high,
        _test_severity_classification_medium,
        _test_severity_classification_low,
        _test_severity_regulatory_escalates_to_critical,
        _test_severity_fraud_escalates_to_critical,
        _test_severity_missing_impact_rule6,
        _test_aging_bucket_current,
        _test_aging_bucket_overdue,
        _test_aging_bucket_uses_closed_date_for_closed,
        _test_aging_bucket_missing_date_rule6,
        _test_sla_breach_high_severity,
        _test_sla_no_breach_within_target,
        _test_sla_breach_for_closed_issue_late,
        _test_escalation_required_critical_30days,
        _test_escalation_not_required_within_threshold,
        _test_escalation_skipped_for_closed,
        _test_kri_summary_basic,
        _test_kri_summary_empty_rule1,
        _test_kri_summary_cluster_escalation,
        _test_severities_byte_for_byte,
        _test_sla_targets_byte_for_byte,
        _test_aging_buckets_byte_for_byte,
        _test_aging_bucket_days_byte_for_byte,
        _test_escalation_thresholds_byte_for_byte,
        _test_cluster_threshold_byte_for_byte,
    ]
    print("=" * 60)
    print("Issue Management Engine — Self-Tests (#83)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

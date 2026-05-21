"""
================================================================================
A2Z MIS 360 — Standard #84: Audit Reporting & Audit Committee Dashboard Engine
================================================================================

Risk classification: Cat B (deterministic audit reporting + dashboard payload)

Generates audit committee reporting per IIA Practice Advisory + ISA 700:
    - validate_audit_opinion(...)              -- ISA 700 opinion type validation
    - audit_universe_coverage(...)             -- % of universe audited in period
    - outstanding_recommendations_summary(...) -- aging of open recommendations
    - generate_audit_committee_dashboard(...)  -- quarterly dashboard payload

ISA 700 audit opinions byte-for-byte:
    UNQUALIFIED        : clean opinion — financials fairly presented
    QUALIFIED          : exception(s) but otherwise clean
    ADVERSE            : financials NOT fairly presented (severe)
    DISCLAIMER         : unable to obtain sufficient evidence

Coverage thresholds byte-for-byte:
    EXCELLENT  : >= 90% of HIGH-risk audit universe covered in period
    GOOD       : 75-89%
    ADEQUATE   : 60-74%
    INADEQUATE : < 60% — flag to Board

Audit report required sections (ISA 700):
    EXECUTIVE_SUMMARY, SCOPE_AND_OBJECTIVES, METHODOLOGY,
    DETAILED_FINDINGS, MANAGEMENT_RESPONSE, RECOMMENDATIONS,
    OPINION, APPENDICES

Honesty rules applied:
    Rule 1: coverage_pct = None when total_universe <= 0
    Rule 6: reports/recommendations with missing fields excluded with count

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# ISA 700 audit opinion types byte-for-byte
AUDIT_OPINIONS: Tuple[str, ...] = (
    "UNQUALIFIED",
    "QUALIFIED",
    "ADVERSE",
    "DISCLAIMER",
)

# Required audit report sections (ISA 700)
REQUIRED_REPORT_SECTIONS: Tuple[str, ...] = (
    "EXECUTIVE_SUMMARY",
    "SCOPE_AND_OBJECTIVES",
    "METHODOLOGY",
    "DETAILED_FINDINGS",
    "MANAGEMENT_RESPONSE",
    "RECOMMENDATIONS",
    "OPINION",
    "APPENDICES",
)

# Coverage rating thresholds byte-for-byte
COVERAGE_THRESHOLDS_PCT: Dict[str, Decimal] = {
    "EXCELLENT": Decimal("90"),
    "GOOD": Decimal("75"),
    "ADEQUATE": Decimal("60"),
    # below 60% = INADEQUATE
}

COVERAGE_RATINGS: Tuple[str, ...] = (
    "EXCELLENT", "GOOD", "ADEQUATE", "INADEQUATE",
)

# Recommendation aging buckets (months)
RECOMMENDATION_AGING_MONTHS: Dict[str, Tuple[int, int]] = {
    "RECENT": (0, 6),
    "AGED": (7, 12),
    "PROLONGED": (13, 24),
    "STALE": (25, 9999),
}

RECOMMENDATION_AGING_BUCKETS: Tuple[str, ...] = (
    "RECENT", "AGED", "PROLONGED", "STALE",
)


@dataclass
class AuditReport:
    report_id: str
    entity_audited: str
    audit_period_start: Optional[date] = None
    audit_period_end: Optional[date] = None
    opinion: Optional[str] = None  # uses AUDIT_OPINIONS
    sections_present: Optional[List[str]] = None
    issued_date: Optional[date] = None


@dataclass
class AuditRecommendation:
    recommendation_id: str
    report_id: str
    description: str
    raised_date: Optional[date] = None
    due_date: Optional[date] = None
    closed_date: Optional[date] = None
    is_open: bool = True
    severity: Optional[str] = None  # CRITICAL/HIGH/MEDIUM/LOW


def _months_between(d1: date, d2: date) -> int:
    """Approximate months between two dates."""
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def _coverage_rating(coverage_pct: Decimal) -> str:
    if coverage_pct >= COVERAGE_THRESHOLDS_PCT["EXCELLENT"]:
        return "EXCELLENT"
    if coverage_pct >= COVERAGE_THRESHOLDS_PCT["GOOD"]:
        return "GOOD"
    if coverage_pct >= COVERAGE_THRESHOLDS_PCT["ADEQUATE"]:
        return "ADEQUATE"
    return "INADEQUATE"


def _recommendation_aging_bucket(months: int) -> str:
    if months < 0:
        return "RECENT"
    for bucket in RECOMMENDATION_AGING_BUCKETS:
        lo, hi = RECOMMENDATION_AGING_MONTHS[bucket]
        if lo <= months <= hi:
            return bucket
    return "STALE"


class AuditReportingEngine:
    """Deterministic audit reporting + AC dashboard generator."""

    @staticmethod
    def validate_audit_opinion(report: AuditReport) -> Dict[str, Any]:
        """Validate report opinion + section completeness per ISA 700."""
        errors = []
        if report.opinion is None:
            errors.append("missing_opinion")
        elif report.opinion not in AUDIT_OPINIONS:
            errors.append(f"unknown_opinion:{report.opinion}")
        if report.audit_period_start is None or report.audit_period_end is None:
            errors.append("missing_audit_period")
        if report.issued_date is None:
            errors.append("missing_issued_date")

        # Required sections check
        sections_present = report.sections_present or []
        missing_sections = [s for s in REQUIRED_REPORT_SECTIONS
                           if s not in sections_present]
        if missing_sections:
            errors.append(f"missing_sections:{','.join(missing_sections)}")

        if errors:
            return {
                "report_id": report.report_id,
                "valid": False,
                "errors": errors,
            }
        return {
            "report_id": report.report_id,
            "valid": True,
            "opinion": report.opinion,
            "audit_period": [
                report.audit_period_start.isoformat(),
                report.audit_period_end.isoformat(),
            ],
            "sections_complete": True,
        }

    @staticmethod
    def audit_universe_coverage(
        total_universe_count: int,
        audited_in_period_count: int,
    ) -> Dict[str, Any]:
        """
        Coverage % = audited / total × 100. Rule 1: None when total<=0.
        """
        if total_universe_count <= 0:
            return {
                "coverage_pct": None,
                "rating": None,
                "reason": "total_universe_zero_or_negative",
            }
        if audited_in_period_count < 0:
            return {
                "coverage_pct": None,
                "rating": None,
                "reason": "negative_audited_count",
            }
        coverage = (Decimal(audited_in_period_count) / Decimal(total_universe_count)
                    * Decimal("100"))
        rating = _coverage_rating(coverage)
        return {
            "total_universe_count": total_universe_count,
            "audited_in_period_count": audited_in_period_count,
            "coverage_pct": str(coverage.quantize(Decimal("0.01"))),
            "rating": rating,
            "thresholds": {k: str(v) for k, v in COVERAGE_THRESHOLDS_PCT.items()},
        }

    @staticmethod
    def outstanding_recommendations_summary(
        recommendations: List[AuditRecommendation],
        ref_date: date,
    ) -> Dict[str, Any]:
        """
        Summary of open recommendations by aging bucket.
        Rule 6: recommendations with missing dates excluded.
        """
        bucket_counts = {b: 0 for b in RECOMMENDATION_AGING_BUCKETS}
        excluded = []
        open_count = 0
        closed_count = 0

        for r in recommendations:
            if r.raised_date is None:
                excluded.append(r.recommendation_id)
                continue
            if not r.is_open or r.closed_date is not None:
                closed_count += 1
                continue
            open_count += 1
            months_open = _months_between(r.raised_date, ref_date)
            bucket = _recommendation_aging_bucket(months_open)
            bucket_counts[bucket] += 1

        total = open_count + closed_count
        open_pct = ((Decimal(open_count) / Decimal(total) * Decimal("100"))
                    if total > 0 else None)

        return {
            "total_recommendations": total,
            "open_count": open_count,
            "closed_count": closed_count,
            "open_pct": (str(open_pct.quantize(Decimal("0.01")))
                         if open_pct is not None else None),
            "by_aging_bucket": bucket_counts,
            "excluded_count": len(excluded),
        }

    @classmethod
    def generate_audit_committee_dashboard(
        cls,
        reports: List[AuditReport],
        recommendations: List[AuditRecommendation],
        total_universe_count: int,
        ref_date: date,
    ) -> Dict[str, Any]:
        """
        Quarterly Audit Committee dashboard payload.
        Rule 6: invalid reports surfaced separately.
        """
        # Validate each report
        valid_reports = []
        invalid_reports = []
        opinion_counts = {o: 0 for o in AUDIT_OPINIONS}
        for r in reports:
            v = cls.validate_audit_opinion(r)
            if v["valid"]:
                valid_reports.append(r)
                if r.opinion in AUDIT_OPINIONS:
                    opinion_counts[r.opinion] += 1
            else:
                invalid_reports.append({"report_id": r.report_id,
                                        "errors": v.get("errors", [])})

        # Coverage
        coverage = cls.audit_universe_coverage(
            total_universe_count, len(valid_reports)
        )

        # Recommendations
        recs = cls.outstanding_recommendations_summary(recommendations, ref_date)

        return {
            "ref_date": ref_date.isoformat(),
            "total_reports": len(reports),
            "valid_reports": len(valid_reports),
            "invalid_reports": invalid_reports,
            "by_opinion": opinion_counts,
            "coverage": coverage,
            "recommendations": recs,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _report(**kw):
    defaults = dict(
        report_id="R1", entity_audited="Branch Nairobi",
        audit_period_start=date(2026, 1, 1),
        audit_period_end=date(2026, 3, 31),
        opinion="UNQUALIFIED",
        sections_present=list(REQUIRED_REPORT_SECTIONS),
        issued_date=date(2026, 4, 15),
    )
    defaults.update(kw)
    return AuditReport(**defaults)


def _rec(**kw):
    defaults = dict(
        recommendation_id="REC1", report_id="R1",
        description="Test recommendation",
        raised_date=date(2026, 1, 1),
        is_open=True,
        severity="MEDIUM",
    )
    defaults.update(kw)
    return AuditRecommendation(**defaults)


def _test_opinion_validation_clean():
    r = AuditReportingEngine.validate_audit_opinion(_report())
    assert r["valid"] is True


def _test_opinion_unknown():
    r = AuditReportingEngine.validate_audit_opinion(_report(opinion="WEIRD"))
    assert r["valid"] is False
    assert any("unknown_opinion" in e for e in r["errors"])


def _test_opinion_missing_sections():
    r = AuditReportingEngine.validate_audit_opinion(
        _report(sections_present=["EXECUTIVE_SUMMARY"]))
    assert r["valid"] is False
    assert any("missing_sections" in e for e in r["errors"])


def _test_opinion_missing_period():
    r = AuditReportingEngine.validate_audit_opinion(
        _report(audit_period_start=None))
    assert r["valid"] is False


def _test_coverage_excellent():
    r = AuditReportingEngine.audit_universe_coverage(100, 95)
    assert r["rating"] == "EXCELLENT"
    assert r["coverage_pct"] == "95.00"


def _test_coverage_good():
    r = AuditReportingEngine.audit_universe_coverage(100, 80)
    assert r["rating"] == "GOOD"


def _test_coverage_adequate():
    r = AuditReportingEngine.audit_universe_coverage(100, 65)
    assert r["rating"] == "ADEQUATE"


def _test_coverage_inadequate():
    r = AuditReportingEngine.audit_universe_coverage(100, 30)
    assert r["rating"] == "INADEQUATE"


def _test_coverage_zero_universe_rule1():
    r = AuditReportingEngine.audit_universe_coverage(0, 5)
    assert r["coverage_pct"] is None


def _test_recommendations_summary_basic():
    recs = [
        _rec(recommendation_id="R1", raised_date=date(2026, 4, 1), is_open=True),  # RECENT
        _rec(recommendation_id="R2", raised_date=date(2025, 9, 1), is_open=True),  # AGED
        _rec(recommendation_id="R3", raised_date=date(2024, 6, 1), is_open=True),  # PROLONGED
        _rec(recommendation_id="R4", raised_date=date(2026, 1, 1),
             is_open=False, closed_date=date(2026, 2, 1)),
    ]
    r = AuditReportingEngine.outstanding_recommendations_summary(
        recs, date(2026, 4, 30)
    )
    assert r["open_count"] == 3
    assert r["closed_count"] == 1
    assert r["by_aging_bucket"]["RECENT"] >= 1
    assert r["by_aging_bucket"]["PROLONGED"] >= 1


def _test_recommendations_excluded_rule6():
    recs = [_rec(raised_date=None)]
    r = AuditReportingEngine.outstanding_recommendations_summary(
        recs, date(2026, 4, 30)
    )
    assert r["excluded_count"] == 1


def _test_dashboard_basic():
    reports = [_report(report_id=f"R{i}") for i in range(3)]
    recs = [_rec(recommendation_id=f"REC{i}",
                 raised_date=date(2026, 1, 1), is_open=True)
            for i in range(5)]
    r = AuditReportingEngine.generate_audit_committee_dashboard(
        reports, recs, total_universe_count=10, ref_date=date(2026, 4, 30)
    )
    assert r["valid_reports"] == 3
    assert r["coverage"]["coverage_pct"] == "30.00"


def _test_dashboard_invalid_reports_surfaced():
    reports = [_report(report_id="R1"),
               _report(report_id="R2", opinion="WEIRD")]
    r = AuditReportingEngine.generate_audit_committee_dashboard(
        reports, [], total_universe_count=10, ref_date=date(2026, 4, 30)
    )
    assert len(r["invalid_reports"]) == 1


def _test_audit_opinions_byte_for_byte():
    expected = ("UNQUALIFIED", "QUALIFIED", "ADVERSE", "DISCLAIMER")
    for o in expected:
        assert o in AUDIT_OPINIONS


def _test_required_sections_byte_for_byte():
    expected = ("EXECUTIVE_SUMMARY", "SCOPE_AND_OBJECTIVES", "METHODOLOGY",
                "DETAILED_FINDINGS", "MANAGEMENT_RESPONSE", "RECOMMENDATIONS",
                "OPINION", "APPENDICES")
    for s in expected:
        assert s in REQUIRED_REPORT_SECTIONS


def _test_coverage_thresholds_byte_for_byte():
    assert COVERAGE_THRESHOLDS_PCT["EXCELLENT"] == Decimal("90")
    assert COVERAGE_THRESHOLDS_PCT["GOOD"] == Decimal("75")
    assert COVERAGE_THRESHOLDS_PCT["ADEQUATE"] == Decimal("60")


def _test_recommendation_aging_byte_for_byte():
    assert RECOMMENDATION_AGING_MONTHS["RECENT"] == (0, 6)
    assert RECOMMENDATION_AGING_MONTHS["AGED"] == (7, 12)
    assert RECOMMENDATION_AGING_MONTHS["PROLONGED"] == (13, 24)


def _test_coverage_ratings_byte_for_byte():
    expected = ("EXCELLENT", "GOOD", "ADEQUATE", "INADEQUATE")
    for r in expected:
        assert r in COVERAGE_RATINGS


def self_test() -> bool:
    tests = [
        _test_opinion_validation_clean,
        _test_opinion_unknown,
        _test_opinion_missing_sections,
        _test_opinion_missing_period,
        _test_coverage_excellent,
        _test_coverage_good,
        _test_coverage_adequate,
        _test_coverage_inadequate,
        _test_coverage_zero_universe_rule1,
        _test_recommendations_summary_basic,
        _test_recommendations_excluded_rule6,
        _test_dashboard_basic,
        _test_dashboard_invalid_reports_surfaced,
        _test_audit_opinions_byte_for_byte,
        _test_required_sections_byte_for_byte,
        _test_coverage_thresholds_byte_for_byte,
        _test_recommendation_aging_byte_for_byte,
        _test_coverage_ratings_byte_for_byte,
    ]
    print("=" * 60)
    print("Audit Reporting Engine — Self-Tests (#84)")
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

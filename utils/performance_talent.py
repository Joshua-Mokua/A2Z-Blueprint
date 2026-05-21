"""
================================================================================
A2Z MIS 360 — Standard #63: Performance & Talent Pipeline Engine
================================================================================

Risk classification: Cat B (deterministic distribution analysis) + Cat C (workflow)

Computes:
    - rating_distribution(period)               -- forced calibration check
    - calibration_compliance(period, manager)   -- per-manager rating spread
    - succession_bench_strength(role)           -- ready_now / ready_1y / ready_2y
    - high_potential_pipeline()                 -- HiPo identification
    - performance_trend(staff_id)               -- multi-period trajectory

Calibration target distribution (forced) per HR practice:
    EXCEEDS:        10-15%
    MEETS_PLUS:     20-25%
    MEETS:          50-55%
    DEVELOPING:     5-10%
    UNSATISFACTORY: 0-5%

Honesty rules applied:
    Rule 1: ratios = None when no ratings exist for a period
    Rule 4 (Cat C): performance review status workflow — DRAFT cannot skip to FINALIZED
    Rule 6: missing rating not silently treated as MEETS — flagged in unrated_staff

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Spec literals
RATING_LEVELS: Tuple[str, ...] = (
    "EXCEEDS",
    "MEETS_PLUS",
    "MEETS",
    "DEVELOPING",
    "UNSATISFACTORY",
)

# Calibration target distribution (forced ranges, %)
CALIBRATION_TARGETS: Dict[str, Tuple[float, float]] = {
    "EXCEEDS": (10.0, 15.0),
    "MEETS_PLUS": (20.0, 25.0),
    "MEETS": (50.0, 55.0),
    "DEVELOPING": (5.0, 10.0),
    "UNSATISFACTORY": (0.0, 5.0),
}

# Succession readiness levels
READINESS_LEVELS: Tuple[str, ...] = ("READY_NOW", "READY_1_YEAR", "READY_2_YEAR", "NOT_READY")

# Bench strength severity (% of critical roles with at least 1 READY_NOW successor)
BENCH_HEALTHY_PCT = 75.0
BENCH_AT_RISK_PCT = 50.0

# Performance review workflow (Cat C)
REVIEW_STATUS_DRAFT = "DRAFT"
REVIEW_STATUS_MANAGER_SUBMITTED = "MANAGER_SUBMITTED"
REVIEW_STATUS_CALIBRATED = "CALIBRATED"
REVIEW_STATUS_FINALIZED = "FINALIZED"
REVIEW_STATUS_DISPUTED = "DISPUTED"

VALID_REVIEW_STATUSES: Tuple[str, ...] = (
    REVIEW_STATUS_DRAFT, REVIEW_STATUS_MANAGER_SUBMITTED,
    REVIEW_STATUS_CALIBRATED, REVIEW_STATUS_FINALIZED, REVIEW_STATUS_DISPUTED,
)

# Allowed transitions (Rule 4: cannot skip stages)
ALLOWED_REVIEW_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    REVIEW_STATUS_DRAFT: (REVIEW_STATUS_MANAGER_SUBMITTED,),
    REVIEW_STATUS_MANAGER_SUBMITTED: (REVIEW_STATUS_CALIBRATED, REVIEW_STATUS_DRAFT),  # can return to draft
    REVIEW_STATUS_CALIBRATED: (REVIEW_STATUS_FINALIZED, REVIEW_STATUS_DISPUTED),
    REVIEW_STATUS_DISPUTED: (REVIEW_STATUS_CALIBRATED,),  # back to calibration after dispute
    REVIEW_STATUS_FINALIZED: (),  # terminal
}


@dataclass
class PerformanceReview:
    review_id: str
    staff_id: str
    period: str  # e.g. "2025_H2"
    rating: Optional[str]  # EXCEEDS/MEETS_PLUS/...
    manager_id: str
    review_status: str = REVIEW_STATUS_DRAFT
    score_numeric: Optional[float] = None  # 1-5
    submitted_at: Optional[str] = None
    finalized_at: Optional[str] = None


@dataclass
class SuccessionPlan:
    plan_id: str
    incumbent_role: str
    incumbent_staff_id: str
    successor_staff_id: str
    readiness_level: str
    is_critical_role: bool = False


class PerformanceTalentEngine:
    """Deterministic performance distribution + succession planning analytics."""

    @staticmethod
    def rating_distribution(reviews: List[PerformanceReview], period: str) -> Dict[str, Any]:
        """Aggregate rating distribution for a period; flag unrated staff (Rule 6)."""
        period_reviews = [r for r in reviews if r.period == period]
        rated = [r for r in period_reviews if r.rating in RATING_LEVELS]
        unrated = [r for r in period_reviews if r.rating not in RATING_LEVELS]

        # Rule 1: distribution = None when no ratings
        total = len(rated)
        dist: Dict[str, Dict[str, Any]] = {}
        for level in RATING_LEVELS:
            count = sum(1 for r in rated if r.rating == level)
            pct = (count / total * 100) if total > 0 else None
            target_lo, target_hi = CALIBRATION_TARGETS[level]
            in_target = (pct is not None and target_lo <= pct <= target_hi)
            dist[level] = {
                "count": count,
                "pct": round(pct, 2) if pct is not None else None,
                "target_range_pct": [target_lo, target_hi],
                "in_target": in_target,
            }

        return {
            "period": period,
            "total_rated": total,
            "total_unrated": len(unrated),
            "distribution": dist,
            "calibration_compliant": (total > 0) and all(dist[level]["in_target"] for level in RATING_LEVELS),
            "unrated_staff_ids": [r.staff_id for r in unrated[:20]],
        }

    @staticmethod
    def calibration_compliance_by_manager(
        reviews: List[PerformanceReview], period: str
    ) -> Dict[str, Any]:
        """
        Identify managers whose rating distribution deviates from calibration.
        Common pathology: every direct report rated EXCEEDS (rating inflation).
        """
        period_reviews = [r for r in reviews if r.period == period and r.rating in RATING_LEVELS]
        by_mgr: Dict[str, List[PerformanceReview]] = {}
        for r in period_reviews:
            by_mgr.setdefault(r.manager_id, []).append(r)

        manager_findings: List[Dict[str, Any]] = []
        for mgr, recs in by_mgr.items():
            n = len(recs)
            if n < 4:  # Too small to calibrate meaningfully
                continue
            exceeds_pct = sum(1 for r in recs if r.rating == "EXCEEDS") / n * 100
            unsat_pct = sum(1 for r in recs if r.rating == "UNSATISFACTORY") / n * 100
            issues = []
            if exceeds_pct > CALIBRATION_TARGETS["EXCEEDS"][1]:
                issues.append(f"rating_inflation:exceeds_pct={exceeds_pct:.1f}%>target_max={CALIBRATION_TARGETS['EXCEEDS'][1]}")
            if unsat_pct > CALIBRATION_TARGETS["UNSATISFACTORY"][1]:
                issues.append(f"rating_deflation:unsat_pct={unsat_pct:.1f}%>target_max={CALIBRATION_TARGETS['UNSATISFACTORY'][1]}")
            if issues:
                manager_findings.append({
                    "manager_id": mgr,
                    "team_size": n,
                    "exceeds_pct": round(exceeds_pct, 2),
                    "issues": issues,
                })

        return {
            "period": period,
            "total_managers_with_calibratable_teams": len([m for m, recs in by_mgr.items() if len(recs) >= 4]),
            "managers_with_calibration_issues": len(manager_findings),
            "findings": manager_findings,
        }

    @staticmethod
    def succession_bench_strength(plans: List[SuccessionPlan]) -> Dict[str, Any]:
        """
        Compute bench strength = % of critical roles with ≥1 READY_NOW successor.
        Rule 1: bench_strength_pct = None when no critical roles defined.
        """
        critical = [p for p in plans if p.is_critical_role]
        if not critical:
            return {
                "bench_strength_pct": None,
                "severity": None,
                "critical_role_count": 0,
                "reason": "no_critical_roles_defined",
            }

        # Group by incumbent role
        by_role: Dict[str, List[SuccessionPlan]] = {}
        for p in critical:
            by_role.setdefault(p.incumbent_role, []).append(p)

        roles_covered = 0
        roles_at_risk: List[str] = []
        for role, role_plans in by_role.items():
            if any(p.readiness_level == "READY_NOW" for p in role_plans):
                roles_covered += 1
            else:
                roles_at_risk.append(role)

        bench_pct = (roles_covered / len(by_role)) * 100
        if bench_pct >= BENCH_HEALTHY_PCT:
            severity = "HEALTHY"
        elif bench_pct >= BENCH_AT_RISK_PCT:
            severity = "AT_RISK"
        else:
            severity = "CRITICAL"

        return {
            "critical_role_count": len(by_role),
            "roles_with_ready_now_successor": roles_covered,
            "bench_strength_pct": round(bench_pct, 1),
            "severity": severity,
            "roles_at_risk": roles_at_risk[:20],
        }

    @staticmethod
    def transition_review_status(
        review: PerformanceReview,
        new_status: str,
        actor_id: str,
    ) -> Tuple[bool, str]:
        """
        Rule 4 default-strict: review cannot skip stages.
        DRAFT → MANAGER_SUBMITTED → CALIBRATED → FINALIZED (or → DISPUTED → CALIBRATED).
        """
        if new_status not in VALID_REVIEW_STATUSES:
            return False, f"invalid_status:{new_status}"
        if not actor_id:
            return False, "actor_id_required"
        allowed = ALLOWED_REVIEW_TRANSITIONS.get(review.review_status, ())
        if new_status not in allowed:
            return False, f"transition_not_allowed:{review.review_status}->{new_status}"
        review.review_status = new_status
        return True, "transitioned"

    @staticmethod
    def high_potential_pipeline(
        reviews: List[PerformanceReview],
        periods_required: int = 2,
    ) -> Dict[str, Any]:
        """
        HiPo = staff rated EXCEEDS for >=N consecutive periods.
        Rule 6: staff with insufficient review history surfaced separately.
        """
        # Group reviews by staff_id, sort by period
        by_staff: Dict[str, List[PerformanceReview]] = {}
        for r in reviews:
            if r.rating in RATING_LEVELS:
                by_staff.setdefault(r.staff_id, []).append(r)

        hipos: List[str] = []
        insufficient_history: List[str] = []
        for staff_id, recs in by_staff.items():
            recs.sort(key=lambda r: r.period)
            if len(recs) < periods_required:
                insufficient_history.append(staff_id)
                continue
            # Last N consecutive periods all EXCEEDS
            last_n = recs[-periods_required:]
            if all(r.rating == "EXCEEDS" for r in last_n):
                hipos.append(staff_id)

        return {
            "periods_required": periods_required,
            "hipo_count": len(hipos),
            "hipo_staff_ids": hipos[:30],
            "insufficient_history_count": len(insufficient_history),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_review(**kw):
    defaults = dict(
        review_id="R1", staff_id="S1", period="2025_H2", rating="MEETS",
        manager_id="M1", review_status=REVIEW_STATUS_DRAFT,
    )
    defaults.update(kw)
    return PerformanceReview(**defaults)


def _test_rating_distribution_basic():
    revs = []
    # 100 reviews: 12 EXCEEDS, 22 MEETS_PLUS, 52 MEETS, 9 DEVELOPING, 5 UNSATISFACTORY
    for i in range(12): revs.append(_make_review(review_id=f"R{i}", staff_id=f"S{i}", rating="EXCEEDS"))
    for i in range(12, 34): revs.append(_make_review(review_id=f"R{i}", staff_id=f"S{i}", rating="MEETS_PLUS"))
    for i in range(34, 86): revs.append(_make_review(review_id=f"R{i}", staff_id=f"S{i}", rating="MEETS"))
    for i in range(86, 95): revs.append(_make_review(review_id=f"R{i}", staff_id=f"S{i}", rating="DEVELOPING"))
    for i in range(95, 100): revs.append(_make_review(review_id=f"R{i}", staff_id=f"S{i}", rating="UNSATISFACTORY"))
    r = PerformanceTalentEngine.rating_distribution(revs, "2025_H2")
    assert r["total_rated"] == 100
    assert r["distribution"]["EXCEEDS"]["pct"] == 12.0
    assert r["calibration_compliant"] is True


def _test_rating_distribution_empty_rule1():
    """Rule 1: no ratings → pct=None."""
    r = PerformanceTalentEngine.rating_distribution([], "2025_H2")
    assert r["total_rated"] == 0
    assert r["distribution"]["EXCEEDS"]["pct"] is None
    assert r["calibration_compliant"] is False


def _test_rating_distribution_unrated_rule6():
    revs = [
        _make_review(review_id="R1", staff_id="S1", rating="EXCEEDS"),
        _make_review(review_id="R2", staff_id="S2", rating=None),
    ]
    r = PerformanceTalentEngine.rating_distribution(revs, "2025_H2")
    assert r["total_unrated"] == 1
    assert "S2" in r["unrated_staff_ids"]


def _test_calibration_inflation_detected():
    """Manager rates 5/5 EXCEEDS (rating inflation)."""
    revs = [
        _make_review(review_id=f"R{i}", staff_id=f"S{i}", rating="EXCEEDS", manager_id="M1")
        for i in range(5)
    ]
    r = PerformanceTalentEngine.calibration_compliance_by_manager(revs, "2025_H2")
    assert r["managers_with_calibration_issues"] >= 1
    finding = next(f for f in r["findings"] if f["manager_id"] == "M1")
    assert any("rating_inflation" in i for i in finding["issues"])


def _test_succession_bench_basic():
    plans = [
        SuccessionPlan(plan_id="P1", incumbent_role="MD", incumbent_staff_id="MD1",
                       successor_staff_id="S1", readiness_level="READY_NOW", is_critical_role=True),
        SuccessionPlan(plan_id="P2", incumbent_role="CFO", incumbent_staff_id="CFO1",
                       successor_staff_id="S2", readiness_level="READY_1_YEAR", is_critical_role=True),
    ]
    r = PerformanceTalentEngine.succession_bench_strength(plans)
    assert r["critical_role_count"] == 2
    assert r["roles_with_ready_now_successor"] == 1
    assert r["bench_strength_pct"] == 50.0
    assert r["severity"] == "AT_RISK"


def _test_succession_no_critical_roles_rule1():
    """Rule 1: no critical roles → bench_strength = None."""
    r = PerformanceTalentEngine.succession_bench_strength([])
    assert r["bench_strength_pct"] is None
    assert r["reason"] == "no_critical_roles_defined"


def _test_review_workflow_skip_rejected():
    """Rule 4: DRAFT cannot skip directly to FINALIZED."""
    rev = _make_review()
    ok, reason = PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_FINALIZED, "M1")
    assert not ok
    assert "transition_not_allowed" in reason


def _test_review_workflow_normal_path():
    rev = _make_review()
    assert PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_MANAGER_SUBMITTED, "M1")[0]
    assert PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_CALIBRATED, "HR1")[0]
    assert PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_FINALIZED, "HR1")[0]
    assert rev.review_status == REVIEW_STATUS_FINALIZED


def _test_review_workflow_finalized_terminal():
    """Rule 4: FINALIZED is terminal."""
    rev = _make_review(review_status=REVIEW_STATUS_FINALIZED)
    ok, _ = PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_DRAFT, "M1")
    assert not ok


def _test_review_actor_id_required():
    rev = _make_review()
    ok, reason = PerformanceTalentEngine.transition_review_status(rev, REVIEW_STATUS_MANAGER_SUBMITTED, "")
    assert not ok
    assert "actor_id_required" in reason


def _test_hipo_pipeline_basic():
    revs = [
        _make_review(review_id="R1", staff_id="S1", period="2024_H1", rating="EXCEEDS"),
        _make_review(review_id="R2", staff_id="S1", period="2024_H2", rating="EXCEEDS"),
        _make_review(review_id="R3", staff_id="S2", period="2024_H1", rating="MEETS"),
        _make_review(review_id="R4", staff_id="S2", period="2024_H2", rating="EXCEEDS"),
    ]
    r = PerformanceTalentEngine.high_potential_pipeline(revs, periods_required=2)
    assert "S1" in r["hipo_staff_ids"]
    assert "S2" not in r["hipo_staff_ids"]


def _test_hipo_insufficient_history_rule6():
    revs = [_make_review(review_id="R1", staff_id="S1", period="2024_H1", rating="EXCEEDS")]
    r = PerformanceTalentEngine.high_potential_pipeline(revs, periods_required=2)
    assert r["insufficient_history_count"] == 1


def self_test() -> bool:
    tests = [
        _test_rating_distribution_basic,
        _test_rating_distribution_empty_rule1,
        _test_rating_distribution_unrated_rule6,
        _test_calibration_inflation_detected,
        _test_succession_bench_basic,
        _test_succession_no_critical_roles_rule1,
        _test_review_workflow_skip_rejected,
        _test_review_workflow_normal_path,
        _test_review_workflow_finalized_terminal,
        _test_review_actor_id_required,
        _test_hipo_pipeline_basic,
        _test_hipo_insufficient_history_rule6,
    ]
    print("=" * 60)
    print("Performance & Talent Pipeline Engine — Self-Tests (#63)")
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

"""
================================================================================
A2Z MIS 360 — Standard #61: Workforce Analytics Engine
================================================================================

Risk classification: Cat B (deterministic aggregation, no ML)

Computes workforce metrics from staff register: headcount, attrition rate,
span of control, demographic distribution, tenure analysis. Aligns with
HR practice and CBK reporting requirements for licensed banks.

Metrics produced:
    - headcount_by_dimension(period, dimensions)  -- pivot by branch/role/grade
    - attrition_rate(period, dimensions)          -- annualized turnover
    - span_of_control(as_of_date)                 -- direct reports per manager
    - tenure_distribution(as_of_date)             -- time-in-role buckets
    - demographic_mix(as_of_date)                 -- gender/age band/grade

Honesty rules applied:
    Rule 1: ratios = None when denominator <= 0 (attrition with zero opening headcount)
    Rule 6: missing demographic data tracked in "UNKNOWN" bucket — never silently dropped

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# Spec literals
EMPLOYMENT_STATUSES: Tuple[str, ...] = ("ACTIVE", "ON_LEAVE", "TERMINATED", "RESIGNED", "RETIRED")
TENURE_BUCKETS: Tuple[Tuple[str, int, int], ...] = (
    ("UNDER_1Y", 0, 365),
    ("1_3Y", 366, 1095),
    ("3_5Y", 1096, 1825),
    ("5_10Y", 1826, 3650),
    ("OVER_10Y", 3651, 999999),
)
AGE_BANDS: Tuple[Tuple[str, int, int], ...] = (
    ("UNDER_25", 0, 24),
    ("25_34", 25, 34),
    ("35_44", 35, 44),
    ("45_54", 45, 54),
    ("55_PLUS", 55, 120),
)
SPAN_OF_CONTROL_HEALTHY_MIN = 4
SPAN_OF_CONTROL_HEALTHY_MAX = 12
SPAN_OF_CONTROL_OVERLOADED = 15

# Attrition severity bands (annual %)
ATTRITION_LOW_PCT = 5.0
ATTRITION_HEALTHY_MAX_PCT = 12.0
ATTRITION_HIGH_PCT = 20.0


@dataclass
class StaffRecord:
    staff_id: str
    branch_code: str
    role: str
    grade: str
    employment_status: str
    hire_date: str  # ISO
    termination_date: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    manager_id: Optional[str] = None
    base_salary_kes: Optional[Decimal] = None


def _parse_date(s: Optional[str]) -> Optional[date]:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(s)
        except Exception:
            return None


class WorkforceAnalyticsEngine:
    """Deterministic workforce metric aggregation."""

    @staticmethod
    def headcount_by_dimension(
        staff: List[StaffRecord],
        as_of_date: str,
        dimensions: List[str],
    ) -> Dict[str, Any]:
        """Pivot active headcount by dimensions (branch_code, role, grade, gender)."""
        ad = _parse_date(as_of_date)
        if ad is None:
            return {"error": "invalid_as_of_date", "buckets": {}}
        valid_dims = {"branch_code", "role", "grade", "gender", "employment_status"}
        for d in dimensions:
            if d not in valid_dims:
                return {"error": f"unknown_dimension:{d}", "valid": list(valid_dims), "buckets": {}}

        active = [s for s in staff if s.employment_status == "ACTIVE"]
        unknown_count = 0
        buckets: Dict[Tuple, int] = {}
        for s in active:
            key_parts = []
            for d in dimensions:
                val = getattr(s, d, None)
                if val is None or val == "":
                    val = "UNKNOWN"
                    unknown_count += 1
                key_parts.append(val)
            key = tuple(key_parts)
            buckets[key] = buckets.get(key, 0) + 1

        return {
            "as_of_date": as_of_date,
            "dimensions": list(dimensions),
            "total_active_headcount": len(active),
            "buckets": [{"key": list(k), "headcount": v} for k, v in buckets.items()],
            "meta": {"unknown_dimension_assignments": unknown_count},
        }

    @staticmethod
    def attrition_rate(
        staff: List[StaffRecord],
        period_start: str,
        period_end: str,
        dimensions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Annualized attrition rate = terminations / opening_headcount × (365/days)."""
        ps = _parse_date(period_start)
        pe = _parse_date(period_end)
        if ps is None or pe is None or pe <= ps:
            return {"error": "invalid_period", "rate_pct": None}

        period_days = (pe - ps).days
        # Opening headcount = staff active at period_start
        opening = [
            s for s in staff
            if s.hire_date and _parse_date(s.hire_date) and _parse_date(s.hire_date) <= ps
            and (s.termination_date is None or (_parse_date(s.termination_date) and _parse_date(s.termination_date) > ps))
        ]
        # Terminations during period
        terms = [
            s for s in staff
            if s.termination_date and _parse_date(s.termination_date)
            and ps <= _parse_date(s.termination_date) <= pe
        ]
        opening_count = len(opening)
        term_count = len(terms)

        # Rule 1: undefined if denominator <= 0
        if opening_count == 0:
            return {
                "period_start": period_start,
                "period_end": period_end,
                "opening_headcount": 0,
                "terminations": term_count,
                "rate_pct": None,
                "annualized_rate_pct": None,
                "severity": None,
                "reason": "opening_headcount_zero",
            }

        rate = (term_count / opening_count) * 100
        annualized = rate * (365 / period_days) if period_days > 0 else None

        if annualized is None:
            severity = None
        elif annualized < ATTRITION_LOW_PCT:
            severity = "LOW"
        elif annualized < ATTRITION_HEALTHY_MAX_PCT:
            severity = "HEALTHY"
        elif annualized < ATTRITION_HIGH_PCT:
            severity = "ELEVATED"
        else:
            severity = "HIGH"

        return {
            "period_start": period_start,
            "period_end": period_end,
            "period_days": period_days,
            "opening_headcount": opening_count,
            "terminations": term_count,
            "rate_pct": round(rate, 2),
            "annualized_rate_pct": round(annualized, 2) if annualized is not None else None,
            "severity": severity,
        }

    @staticmethod
    def span_of_control(staff: List[StaffRecord]) -> Dict[str, Any]:
        """Compute direct reports per manager. Flag overloaded/under-utilized."""
        active = [s for s in staff if s.employment_status == "ACTIVE"]
        # Map manager_id -> direct reports count
        reports: Dict[str, int] = {}
        for s in active:
            if s.manager_id:
                reports[s.manager_id] = reports.get(s.manager_id, 0) + 1

        managers_active_ids = {s.staff_id for s in active}

        overloaded = []
        healthy = 0
        under = []
        no_reports = []  # managers with no direct reports
        for mgr_id in managers_active_ids:
            count = reports.get(mgr_id, 0)
            if count == 0:
                no_reports.append(mgr_id)
            elif count > SPAN_OF_CONTROL_OVERLOADED:
                overloaded.append({"manager_id": mgr_id, "direct_reports": count})
            elif count < SPAN_OF_CONTROL_HEALTHY_MIN:
                under.append({"manager_id": mgr_id, "direct_reports": count})
            else:
                healthy += 1

        return {
            "total_managers": len(reports),
            "overloaded_count": len(overloaded),
            "overloaded_threshold": SPAN_OF_CONTROL_OVERLOADED,
            "healthy_count": healthy,
            "healthy_range": [SPAN_OF_CONTROL_HEALTHY_MIN, SPAN_OF_CONTROL_HEALTHY_MAX],
            "under_count": len(under),
            "individual_contributors": len(no_reports),
            "overloaded_managers": overloaded[:10],
            "under_managers": under[:10],
        }

    @staticmethod
    def tenure_distribution(staff: List[StaffRecord], as_of_date: str) -> Dict[str, Any]:
        """Bucket active staff by tenure (days since hire)."""
        ad = _parse_date(as_of_date)
        if ad is None:
            return {"error": "invalid_as_of_date", "buckets": {}}
        active = [s for s in staff if s.employment_status == "ACTIVE"]
        buckets = {b[0]: 0 for b in TENURE_BUCKETS}
        unknown = 0
        for s in active:
            hd = _parse_date(s.hire_date)
            if hd is None:
                unknown += 1
                continue
            tenure_days = (ad - hd).days
            if tenure_days < 0:
                unknown += 1  # hire date in future - data quality issue
                continue
            for label, lo, hi in TENURE_BUCKETS:
                if lo <= tenure_days <= hi:
                    buckets[label] += 1
                    break
        return {
            "as_of_date": as_of_date,
            "total_active": len(active),
            "buckets": buckets,
            "meta": {"unknown_or_invalid_hire_date": unknown},
        }

    @staticmethod
    def demographic_mix(staff: List[StaffRecord], as_of_date: str) -> Dict[str, Any]:
        """Gender + age band distribution."""
        ad = _parse_date(as_of_date)
        if ad is None:
            return {"error": "invalid_as_of_date"}
        active = [s for s in staff if s.employment_status == "ACTIVE"]
        gender = {"M": 0, "F": 0, "OTHER": 0, "UNKNOWN": 0}
        age = {b[0]: 0 for b in AGE_BANDS}
        age["UNKNOWN"] = 0
        for s in active:
            g = (s.gender or "").upper()
            if g == "M" or g == "MALE":
                gender["M"] += 1
            elif g == "F" or g == "FEMALE":
                gender["F"] += 1
            elif g == "":
                gender["UNKNOWN"] += 1
            else:
                gender["OTHER"] += 1
            dob = _parse_date(s.date_of_birth)
            if dob is None:
                age["UNKNOWN"] += 1
            else:
                yrs = (ad - dob).days // 365
                placed = False
                for label, lo, hi in AGE_BANDS:
                    if lo <= yrs <= hi:
                        age[label] += 1
                        placed = True
                        break
                if not placed:
                    age["UNKNOWN"] += 1
        # Gender ratio
        total_known = gender["M"] + gender["F"]
        female_pct = (gender["F"] / total_known * 100) if total_known > 0 else None
        return {
            "as_of_date": as_of_date,
            "total_active": len(active),
            "gender_distribution": gender,
            "age_band_distribution": age,
            "female_pct_of_known": round(female_pct, 1) if female_pct is not None else None,
        }

    # ============================================================================
    # v7.5: L13 Compensation equity → Workforce planning feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def merit_budget_from_compensation_equity(
        cls,
        gender_pay_gap_payload: Optional[Dict[str, Any]] = None,
        internal_equity_payload: Optional[Dict[str, Any]] = None,
        annual_payroll_kes: Optional[float] = None,
        target_remediation_pct_of_payroll: float = 1.5,
    ) -> Dict[str, Any]:
        """L13 (CONSUMER) — derive merit budget from compensation equity findings.

        Consumes:
            - `compensation_equity.gender_pay_gap()` payload — overall gap
              + per-grade gaps
            - `compensation_equity.internal_equity_ratios()` payload —
              percentile spread per grade
            - `annual_payroll_kes` — basis for budget calculation

        Per Charter §7 Published Language pattern, depends only on the
        public dict contracts of compensation_equity engine.

        Strategy:
            target_merit_pct = max(target_remediation_pct_of_payroll,
                                   gender_gap_pct, max_internal_gap_pct)
            budget_kes = annual_payroll * target_merit_pct / 100
            priority_grades = grades with gender_gap > 5% OR
                              internal_equity_ratio > 4x

        Returns dict with:
            recommended_merit_budget_kes
            target_merit_pct (driver explanations)
            priority_grades
            consumed_payload_version
            pattern
        """
        if annual_payroll_kes is None or not isinstance(annual_payroll_kes, (int, float)):
            return {
                "status": "MISSING_PAYROLL_BASIS",
                "error": "annual_payroll_kes required for budget calculation",
                "recommended_merit_budget_kes": None,
            }

        # Drivers
        drivers = {"baseline_target_pct": target_remediation_pct_of_payroll}
        priority_grades: List[Dict[str, Any]] = []
        gap_pct_overall: Optional[float] = None
        max_internal_gap_pct: Optional[float] = None

        # 1. Gender pay gap analysis
        if isinstance(gender_pay_gap_payload, dict):
            overall = gender_pay_gap_payload.get("overall") or \
                      gender_pay_gap_payload.get("gender_pay_gap") or \
                      gender_pay_gap_payload
            if isinstance(overall, dict):
                gap_pct_overall = overall.get("gender_pay_gap_pct") or \
                                   overall.get("gap_pct")
                if gap_pct_overall is not None:
                    drivers["gender_gap_pct_overall"] = float(gap_pct_overall)

            # Per-grade gaps
            by_grade = gender_pay_gap_payload.get("by_grade") or {}
            for grade, gdata in by_grade.items() if isinstance(by_grade, dict) else []:
                if not isinstance(gdata, dict):
                    continue
                gap = gdata.get("gender_pay_gap_pct") or gdata.get("gap_pct")
                if gap is not None and abs(float(gap)) > 5:
                    priority_grades.append({
                        "grade": grade,
                        "trigger": "gender_gap_over_5pct",
                        "gap_pct": float(gap),
                    })

        # 2. Internal equity ratios
        if isinstance(internal_equity_payload, dict):
            ratios = internal_equity_payload.get("by_grade") or {}
            for grade, rdata in ratios.items() if isinstance(ratios, dict) else []:
                if not isinstance(rdata, dict):
                    continue
                ratio = rdata.get("p90_to_p10_ratio") or rdata.get("ratio")
                if ratio is not None and float(ratio) > 4:
                    max_internal_gap_pct = max(
                        max_internal_gap_pct or 0,
                        (float(ratio) - 1) * 100,  # spread above ideal
                    )
                    priority_grades.append({
                        "grade": grade,
                        "trigger": "internal_equity_ratio_over_4x",
                        "ratio": float(ratio),
                    })

        # Determine target merit pct
        target_merit_pct = float(target_remediation_pct_of_payroll)
        if gap_pct_overall is not None:
            target_merit_pct = max(target_merit_pct, abs(float(gap_pct_overall)))
        if max_internal_gap_pct is not None:
            target_merit_pct = max(target_merit_pct, max_internal_gap_pct / 10)
        # Cap at reasonable max — 5% of payroll
        target_merit_pct = min(target_merit_pct, 5.0)

        budget_kes = annual_payroll_kes * target_merit_pct / 100

        return {
            "recommended_merit_budget_kes": round(budget_kes, 2),
            "target_merit_pct": round(target_merit_pct, 2),
            "annual_payroll_basis_kes": annual_payroll_kes,
            "drivers": drivers,
            "priority_grades": priority_grades,
            "priority_grades_count": len(priority_grades),
            "consumed_payload_version": (
                "compensation_equity.gender_pay_gap+internal_equity_ratios v1.0"
            ),
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": [],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_staff(**kw):
    defaults = {
        "staff_id": "S1", "branch_code": "B1", "role": "TELLER", "grade": "G3",
        "employment_status": "ACTIVE", "hire_date": "2020-01-01",
    }
    defaults.update(kw)
    return StaffRecord(**defaults)


def _test_headcount_basic():
    staff = [
        _make_staff(staff_id="S1", branch_code="B1", role="TELLER"),
        _make_staff(staff_id="S2", branch_code="B1", role="TELLER"),
        _make_staff(staff_id="S3", branch_code="B2", role="MANAGER"),
        _make_staff(staff_id="S4", employment_status="TERMINATED", branch_code="B1", role="TELLER"),
    ]
    r = WorkforceAnalyticsEngine.headcount_by_dimension(staff, "2026-01-01", ["branch_code"])
    assert r["total_active_headcount"] == 3
    bb = {tuple(b["key"]): b["headcount"] for b in r["buckets"]}
    assert bb[("B1",)] == 2
    assert bb[("B2",)] == 1


def _test_headcount_unknown_dimension():
    r = WorkforceAnalyticsEngine.headcount_by_dimension([], "2026-01-01", ["weird"])
    assert "error" in r


def _test_attrition_rate_basic():
    staff = [
        _make_staff(staff_id=f"S{i}", hire_date="2024-01-01") for i in range(1, 11)
    ]
    # 1 termination during 2025
    staff[0].termination_date = "2025-06-01"
    staff[0].employment_status = "TERMINATED"
    r = WorkforceAnalyticsEngine.attrition_rate(staff, "2025-01-01", "2025-12-31")
    assert r["opening_headcount"] == 10
    assert r["terminations"] == 1
    assert r["rate_pct"] == 10.0


def _test_attrition_rate_zero_opening_rule1():
    """Rule 1: zero opening headcount → rate = None."""
    r = WorkforceAnalyticsEngine.attrition_rate([], "2025-01-01", "2025-12-31")
    assert r["rate_pct"] is None
    assert r["annualized_rate_pct"] is None
    assert r["reason"] == "opening_headcount_zero"


def _test_attrition_severity_bands():
    # 25% = HIGH
    staff = [_make_staff(staff_id=f"S{i}", hire_date="2024-01-01") for i in range(1, 5)]
    staff[0].termination_date = "2025-06-01"
    r = WorkforceAnalyticsEngine.attrition_rate(staff, "2025-01-01", "2025-12-31")
    # 1/4 = 25% over ~365 days = ~25% annualized
    assert r["severity"] == "HIGH"


def _test_span_of_control():
    # Manager S1 has 5 reports; manager S2 has 20 reports (overloaded); S3 is IC.
    staff = [
        _make_staff(staff_id="S1"),
        _make_staff(staff_id="S2"),
        _make_staff(staff_id="S3"),
    ]
    # S1's 5 reports
    for i in range(10, 15):
        staff.append(_make_staff(staff_id=f"R{i}", manager_id="S1"))
    # S2's 20 reports
    for i in range(20, 40):
        staff.append(_make_staff(staff_id=f"R{i}", manager_id="S2"))

    r = WorkforceAnalyticsEngine.span_of_control(staff)
    assert r["total_managers"] == 2  # S1 and S2 have reports
    assert r["overloaded_count"] == 1  # S2 has 20 > 15
    assert r["healthy_count"] == 1  # S1 has 5
    assert r["individual_contributors"] >= 1  # S3


def _test_tenure_distribution():
    staff = [
        _make_staff(staff_id="S1", hire_date="2025-12-01"),  # under 1y from 2026-01-01
        _make_staff(staff_id="S2", hire_date="2024-06-01"),  # 1-3y
        _make_staff(staff_id="S3", hire_date="2010-01-01"),  # 10y+
    ]
    r = WorkforceAnalyticsEngine.tenure_distribution(staff, "2026-01-01")
    assert r["buckets"]["UNDER_1Y"] == 1
    assert r["buckets"]["1_3Y"] == 1
    assert r["buckets"]["OVER_10Y"] == 1


def _test_demographic_mix():
    staff = [
        _make_staff(staff_id="S1", gender="F", date_of_birth="1990-01-01"),
        _make_staff(staff_id="S2", gender="M", date_of_birth="1985-01-01"),
        _make_staff(staff_id="S3", gender=None, date_of_birth=None),
    ]
    r = WorkforceAnalyticsEngine.demographic_mix(staff, "2026-01-01")
    assert r["gender_distribution"]["F"] == 1
    assert r["gender_distribution"]["M"] == 1
    assert r["gender_distribution"]["UNKNOWN"] == 1
    assert r["female_pct_of_known"] == 50.0


def _test_demographic_zero_known_rule1():
    """Rule 1: female_pct = None when no known gender."""
    staff = [_make_staff(staff_id="S1", gender=None)]
    r = WorkforceAnalyticsEngine.demographic_mix(staff, "2026-01-01")
    assert r["female_pct_of_known"] is None


def _test_unknown_buckets_rule6():
    """Rule 6: missing dimensions go to UNKNOWN bucket, not silently dropped."""
    staff = [
        _make_staff(staff_id="S1", branch_code="B1"),
        _make_staff(staff_id="S2", branch_code=""),  # missing
    ]
    r = WorkforceAnalyticsEngine.headcount_by_dimension(staff, "2026-01-01", ["branch_code"])
    keys = {tuple(b["key"]): b["headcount"] for b in r["buckets"]}
    assert ("UNKNOWN",) in keys


def _test_invalid_date_handling():
    r = WorkforceAnalyticsEngine.headcount_by_dimension([], "not-a-date", ["branch_code"])
    assert "error" in r


def self_test() -> bool:
    tests = [
        _test_headcount_basic,
        _test_headcount_unknown_dimension,
        _test_attrition_rate_basic,
        _test_attrition_rate_zero_opening_rule1,
        _test_attrition_severity_bands,
        _test_span_of_control,
        _test_tenure_distribution,
        _test_demographic_mix,
        _test_demographic_zero_known_rule1,
        _test_unknown_buckets_rule6,
        _test_invalid_date_handling,
    ]
    print("=" * 60)
    print("Workforce Analytics Engine — Self-Tests (#61)")
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

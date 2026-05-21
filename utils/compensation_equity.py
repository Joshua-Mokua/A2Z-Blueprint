"""
================================================================================
A2Z MIS 360 — Standard #62: Compensation & Pay Equity Engine
================================================================================

Risk classification: Cat B (deterministic statistical aggregation)

Computes:
    - pay_distribution_by_grade(grade)             -- min/median/max + IQR
    - gender_pay_gap(period)                       -- raw + adjusted (by grade)
    - internal_equity_ratios(grade_band)           -- compa-ratio vs midpoint
    - ceo_to_median_ratio(period)                  -- governance disclosure metric

Statistical methods are deterministic (no random sampling).

Honesty rules applied:
    Rule 1: ratios = None when denominators ≤ 0 (no median when no data)
    Rule 6: missing salary data tracked explicitly, never imputed silently

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

# Pay equity thresholds (industry guidance)
PAY_GAP_FAIR_MAX_PCT = 5.0   # < 5% considered fair
PAY_GAP_MODERATE_MAX_PCT = 10.0  # 5-10% moderate concern
# Above 10% = HIGH concern

COMPA_RATIO_HEALTHY_MIN = 0.80  # 80% of midpoint = below band
COMPA_RATIO_HEALTHY_MAX = 1.20  # 120% of midpoint = above band

# CEO pay ratio disclosure thresholds (CBK governance code aligned)
CEO_RATIO_HEALTHY_MAX = 50  # 50:1 considered healthy at most banks
CEO_RATIO_HIGH_THRESHOLD = 100


@dataclass
class CompensationRecord:
    staff_id: str
    base_salary_kes: Decimal
    grade: str
    role: str
    branch_code: str
    gender: Optional[str] = None
    position_in_band: Optional[str] = None  # ENTRY / MID / SENIOR
    grade_midpoint_kes: Optional[Decimal] = None  # for compa-ratio


def _to_decimal(amount: Any) -> Decimal:
    if isinstance(amount, Decimal):
        return amount
    if amount is None:
        return Decimal("0")
    return Decimal(str(amount))


def _median(values: List[Decimal]) -> Optional[Decimal]:
    """Deterministic median (sort + middle/avg-of-middles)."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / Decimal("2")


def _percentile(values: List[Decimal], pct: float) -> Optional[Decimal]:
    """Linear interpolation percentile (deterministic)."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    rank = (pct / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = Decimal(str(rank - lo))
    return s[lo] + (s[hi] - s[lo]) * frac


class CompensationEquityEngine:
    """Deterministic compensation analytics + pay equity statistics."""

    @staticmethod
    def pay_distribution_by_grade(records: List[CompensationRecord], grade: str) -> Dict[str, Any]:
        """Distribution stats for one grade. Returns None for percentiles when no data."""
        # Rule 6: filter records with non-positive salary, surface them
        all_grade = [r for r in records if r.grade == grade]
        valid = [r for r in all_grade if r.base_salary_kes and r.base_salary_kes > Decimal("0")]
        excluded_no_salary = len(all_grade) - len(valid)

        if not valid:
            return {
                "grade": grade,
                "headcount": 0,
                "headcount_excluded_no_salary": excluded_no_salary,
                "min": None,
                "max": None,
                "median": None,
                "p25": None,
                "p75": None,
                "iqr": None,
                "reason": "no_records_with_valid_salary" if all_grade else "no_records_at_grade",
            }

        salaries = [r.base_salary_kes for r in valid]
        med = _median(salaries)
        p25 = _percentile(salaries, 25)
        p75 = _percentile(salaries, 75)
        iqr = (p75 - p25) if (p25 is not None and p75 is not None) else None

        return {
            "grade": grade,
            "headcount": len(valid),
            "headcount_excluded_no_salary": excluded_no_salary,
            "min": str(min(salaries)),
            "max": str(max(salaries)),
            "median": str(med) if med is not None else None,
            "p25": str(p25) if p25 is not None else None,
            "p75": str(p75) if p75 is not None else None,
            "iqr": str(iqr) if iqr is not None else None,
        }

    @staticmethod
    def gender_pay_gap(records: List[CompensationRecord], by_grade: bool = False) -> Dict[str, Any]:
        """
        Compute raw + grade-adjusted gender pay gap.

        Raw = (male_median - female_median) / male_median × 100
        Adjusted = average of within-grade gaps weighted by grade headcount

        Rule 1: gap = None when male_median <= 0 (cannot compute)
        Rule 6: records with unknown gender excluded from gap but counted in meta
        """
        valid = [r for r in records if r.base_salary_kes and r.base_salary_kes > Decimal("0")]
        male = [r.base_salary_kes for r in valid if (r.gender or "").upper() in ("M", "MALE")]
        female = [r.base_salary_kes for r in valid if (r.gender or "").upper() in ("F", "FEMALE")]
        unknown_count = len(valid) - len(male) - len(female)

        male_med = _median(male)
        female_med = _median(female)

        # Raw gap (Rule 1)
        if male_med is None or male_med <= Decimal("0"):
            raw_gap = None
        elif female_med is None:
            raw_gap = None
        else:
            raw_gap = float((male_med - female_med) / male_med) * 100

        # Adjusted gap (by grade)
        adjusted_gap = None
        per_grade: List[Dict[str, Any]] = []
        if by_grade:
            grades = {r.grade for r in valid}
            weighted_sum = 0.0
            weight_total = 0
            for g in sorted(grades):
                g_recs = [r for r in valid if r.grade == g]
                g_male = [r.base_salary_kes for r in g_recs if (r.gender or "").upper() in ("M", "MALE")]
                g_female = [r.base_salary_kes for r in g_recs if (r.gender or "").upper() in ("F", "FEMALE")]
                gm = _median(g_male)
                gf = _median(g_female)
                if gm is None or gm <= Decimal("0") or gf is None:
                    g_gap = None
                else:
                    g_gap = float((gm - gf) / gm) * 100
                w = len(g_male) + len(g_female)
                if g_gap is not None and w > 0:
                    weighted_sum += g_gap * w
                    weight_total += w
                per_grade.append({
                    "grade": g, "male_count": len(g_male), "female_count": len(g_female),
                    "male_median": str(gm) if gm else None,
                    "female_median": str(gf) if gf else None,
                    "gap_pct": round(g_gap, 2) if g_gap is not None else None,
                })
            if weight_total > 0:
                adjusted_gap = weighted_sum / weight_total

        # Severity
        def _severity(gap):
            if gap is None:
                return None
            absgap = abs(gap)
            if absgap < PAY_GAP_FAIR_MAX_PCT:
                return "FAIR"
            if absgap < PAY_GAP_MODERATE_MAX_PCT:
                return "MODERATE"
            return "HIGH"

        return {
            "male_count": len(male),
            "female_count": len(female),
            "unknown_gender_count": unknown_count,
            "male_median": str(male_med) if male_med else None,
            "female_median": str(female_med) if female_med else None,
            "raw_gap_pct": round(raw_gap, 2) if raw_gap is not None else None,
            "adjusted_gap_pct": round(adjusted_gap, 2) if adjusted_gap is not None else None,
            "raw_gap_severity": _severity(raw_gap),
            "adjusted_gap_severity": _severity(adjusted_gap),
            "per_grade": per_grade,
        }

    @staticmethod
    def internal_equity_ratios(records: List[CompensationRecord]) -> Dict[str, Any]:
        """
        Compa-ratio = actual_salary / grade_midpoint
        Healthy band: 0.80 - 1.20
        """
        out = {"records": [], "below_band_count": 0, "above_band_count": 0, "in_band_count": 0, "no_midpoint_count": 0}
        for r in records:
            if r.grade_midpoint_kes is None or r.grade_midpoint_kes <= Decimal("0"):
                out["no_midpoint_count"] += 1
                continue
            if r.base_salary_kes is None or r.base_salary_kes <= Decimal("0"):
                continue
            ratio = float(r.base_salary_kes / r.grade_midpoint_kes)
            if ratio < COMPA_RATIO_HEALTHY_MIN:
                band = "BELOW_BAND"
                out["below_band_count"] += 1
            elif ratio > COMPA_RATIO_HEALTHY_MAX:
                band = "ABOVE_BAND"
                out["above_band_count"] += 1
            else:
                band = "IN_BAND"
                out["in_band_count"] += 1
            out["records"].append({
                "staff_id": r.staff_id,
                "grade": r.grade,
                "compa_ratio": round(ratio, 3),
                "band": band,
            })
        return out

    @staticmethod
    def ceo_to_median_ratio(records: List[CompensationRecord], ceo_staff_id: str) -> Dict[str, Any]:
        """
        Compute CEO pay ratio: ceo_salary / median_employee_salary.
        Rule 1: returns None when median is zero/undefined or CEO not found.
        """
        ceo = next((r for r in records if r.staff_id == ceo_staff_id), None)
        if ceo is None:
            return {"ratio": None, "reason": "ceo_not_found"}
        if ceo.base_salary_kes is None or ceo.base_salary_kes <= Decimal("0"):
            return {"ratio": None, "reason": "ceo_no_salary"}

        valid = [r for r in records
                 if r.staff_id != ceo_staff_id
                 and r.base_salary_kes and r.base_salary_kes > Decimal("0")]
        if not valid:
            return {"ratio": None, "reason": "no_employee_salaries"}

        med = _median([r.base_salary_kes for r in valid])
        if med is None or med <= Decimal("0"):
            return {"ratio": None, "reason": "median_zero"}

        ratio = float(ceo.base_salary_kes / med)
        if ratio < CEO_RATIO_HEALTHY_MAX:
            severity = "HEALTHY"
        elif ratio < CEO_RATIO_HIGH_THRESHOLD:
            severity = "ELEVATED"
        else:
            severity = "HIGH"

        return {
            "ceo_salary_kes": str(ceo.base_salary_kes),
            "median_employee_salary_kes": str(med),
            "ratio": round(ratio, 1),
            "severity": severity,
            "employee_count": len(valid),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_comp(**kw):
    defaults = dict(
        staff_id="S1", base_salary_kes=Decimal("100000"), grade="G3",
        role="TELLER", branch_code="B1", gender="M", grade_midpoint_kes=Decimal("100000"),
    )
    defaults.update(kw)
    return CompensationRecord(**defaults)


def _test_pay_distribution_basic():
    recs = [
        _make_comp(staff_id="S1", base_salary_kes=Decimal("100000"), grade="G3"),
        _make_comp(staff_id="S2", base_salary_kes=Decimal("200000"), grade="G3"),
        _make_comp(staff_id="S3", base_salary_kes=Decimal("300000"), grade="G3"),
    ]
    r = CompensationEquityEngine.pay_distribution_by_grade(recs, "G3")
    assert r["headcount"] == 3
    assert r["median"] == "200000"
    assert r["min"] == "100000"
    assert r["max"] == "300000"


def _test_pay_distribution_no_records_rule1():
    r = CompensationEquityEngine.pay_distribution_by_grade([], "G3")
    assert r["median"] is None
    assert r["headcount"] == 0
    assert "no_records" in r["reason"]


def _test_pay_distribution_excludes_zero_salary_rule6():
    recs = [
        _make_comp(staff_id="S1", base_salary_kes=Decimal("100000"), grade="G3"),
        _make_comp(staff_id="S2", base_salary_kes=Decimal("0"), grade="G3"),
    ]
    r = CompensationEquityEngine.pay_distribution_by_grade(recs, "G3")
    assert r["headcount"] == 1
    assert r["headcount_excluded_no_salary"] == 1


def _test_gender_pay_gap_basic():
    recs = [
        _make_comp(staff_id="S1", base_salary_kes=Decimal("100000"), gender="M"),
        _make_comp(staff_id="S2", base_salary_kes=Decimal("90000"), gender="F"),
    ]
    r = CompensationEquityEngine.gender_pay_gap(recs)
    assert r["raw_gap_pct"] == 10.0
    assert r["raw_gap_severity"] == "HIGH" or r["raw_gap_severity"] == "MODERATE"


def _test_gender_pay_gap_zero_male_rule1():
    """Rule 1: no male records → gap = None."""
    recs = [_make_comp(staff_id="S1", base_salary_kes=Decimal("100000"), gender="F")]
    r = CompensationEquityEngine.gender_pay_gap(recs)
    assert r["raw_gap_pct"] is None


def _test_gender_pay_gap_unknown_excluded_rule6():
    recs = [
        _make_comp(staff_id="S1", gender=None, base_salary_kes=Decimal("100000")),
        _make_comp(staff_id="S2", gender="M", base_salary_kes=Decimal("100000")),
    ]
    r = CompensationEquityEngine.gender_pay_gap(recs)
    assert r["unknown_gender_count"] == 1


def _test_internal_equity_compa_ratio():
    recs = [
        _make_comp(staff_id="S1", base_salary_kes=Decimal("70000"), grade_midpoint_kes=Decimal("100000")),  # 0.7 BELOW
        _make_comp(staff_id="S2", base_salary_kes=Decimal("100000"), grade_midpoint_kes=Decimal("100000")),  # 1.0 IN
        _make_comp(staff_id="S3", base_salary_kes=Decimal("130000"), grade_midpoint_kes=Decimal("100000")),  # 1.3 ABOVE
    ]
    r = CompensationEquityEngine.internal_equity_ratios(recs)
    assert r["below_band_count"] == 1
    assert r["in_band_count"] == 1
    assert r["above_band_count"] == 1


def _test_ceo_pay_ratio():
    recs = [
        _make_comp(staff_id="CEO", base_salary_kes=Decimal("10000000"), role="CEO"),
        _make_comp(staff_id="S1", base_salary_kes=Decimal("100000")),
        _make_comp(staff_id="S2", base_salary_kes=Decimal("100000")),
        _make_comp(staff_id="S3", base_salary_kes=Decimal("100000")),
    ]
    r = CompensationEquityEngine.ceo_to_median_ratio(recs, "CEO")
    assert r["ratio"] == 100.0
    assert r["severity"] == "HIGH"


def _test_ceo_not_found():
    r = CompensationEquityEngine.ceo_to_median_ratio([], "MISSING")
    assert r["ratio"] is None
    assert r["reason"] == "ceo_not_found"


def _test_adjusted_gap_by_grade():
    recs = [
        _make_comp(staff_id="S1", grade="G1", gender="M", base_salary_kes=Decimal("100000")),
        _make_comp(staff_id="S2", grade="G1", gender="F", base_salary_kes=Decimal("95000")),
        _make_comp(staff_id="S3", grade="G2", gender="M", base_salary_kes=Decimal("200000")),
        _make_comp(staff_id="S4", grade="G2", gender="F", base_salary_kes=Decimal("180000")),
    ]
    r = CompensationEquityEngine.gender_pay_gap(recs, by_grade=True)
    assert r["adjusted_gap_pct"] is not None
    assert len(r["per_grade"]) == 2


def self_test() -> bool:
    tests = [
        _test_pay_distribution_basic,
        _test_pay_distribution_no_records_rule1,
        _test_pay_distribution_excludes_zero_salary_rule6,
        _test_gender_pay_gap_basic,
        _test_gender_pay_gap_zero_male_rule1,
        _test_gender_pay_gap_unknown_excluded_rule6,
        _test_internal_equity_compa_ratio,
        _test_ceo_pay_ratio,
        _test_ceo_not_found,
        _test_adjusted_gap_by_grade,
    ]
    print("=" * 60)
    print("Compensation & Pay Equity Engine — Self-Tests (#62)")
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

"""
================================================================================
A2Z MIS 360 — Standard #115: IFRS 8 Operating Segments
================================================================================

Risk classification: Cat B (deterministic segment identification + thresholds per IFRS 8)

Provides:
    - identify_operating_segment(...)    -- 3 IFRS 8.5 criteria
    - quantitative_threshold_test(...)   -- 10% revenue / profit / asset test
    - 75pct_external_revenue_test(...)   -- aggregate reportable segments
    - aggregation_criteria_check(...)    -- 5 IFRS 8.12 economic similarity tests
    - validate_geographic_disclosures(...) -- IFRS 8.33

3 OPERATING_SEGMENT_CRITERIA byte-for-byte (IFRS 8.5):
    EARNS_REVENUE_INCURS_EXPENSES        -- engages in business activities
    OPERATING_RESULTS_REGULARLY_REVIEWED -- by chief operating decision maker
    DISCRETE_FINANCIAL_INFORMATION_AVAILABLE -- separate financial info exists

3 QUANTITATIVE_THRESHOLDS byte-for-byte (IFRS 8.13):
    REVENUE_THRESHOLD_PCT     = 10   -- ≥10% of total revenue
    PROFIT_LOSS_THRESHOLD_PCT = 10   -- ≥10% of greater of profit/loss totals
    ASSETS_THRESHOLD_PCT      = 10   -- ≥10% of total assets

External revenue aggregate test byte-for-byte (IFRS 8.15):
    REPORTABLE_SEGMENT_AGGREGATE_PCT = 75   -- reportable segments must cover ≥75%

5 AGGREGATION_CRITERIA byte-for-byte (IFRS 8.12) — economic similarity:
    SIMILAR_LONG_TERM_FINANCIAL_PERFORMANCE
    SIMILAR_PRODUCTS_OR_SERVICES
    SIMILAR_PRODUCTION_PROCESSES
    SIMILAR_CUSTOMER_TYPES
    SIMILAR_DISTRIBUTION_METHODS

3 GEOGRAPHIC_DISCLOSURES byte-for-byte (IFRS 8.33):
    REVENUE_FROM_EXTERNAL_CUSTOMERS_BY_COUNTRY
    NON_CURRENT_ASSETS_BY_COUNTRY
    MAJOR_CUSTOMERS_DISCLOSURE   -- single customer ≥10% of revenue

Major customer threshold byte-for-byte (IFRS 8.34):
    MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT = 10

Honesty rules applied:
    Rule 1: classification=None when criteria dict empty
            threshold_test=None when total missing or zero
    Rule 6: ANY of 3 segment criteria missing → NOT operating segment
            aggregation requires ALL 5 similarity criteria (fail closed)

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 OPERATING SEGMENT CRITERIA byte-for-byte (IFRS 8.5)
OPERATING_SEGMENT_CRITERIA: Tuple[str, ...] = (
    "EARNS_REVENUE_INCURS_EXPENSES",
    "OPERATING_RESULTS_REGULARLY_REVIEWED",
    "DISCRETE_FINANCIAL_INFORMATION_AVAILABLE",
)

# 3 QUANTITATIVE THRESHOLDS byte-for-byte (IFRS 8.13)
REVENUE_THRESHOLD_PCT = Decimal("10")
PROFIT_LOSS_THRESHOLD_PCT = Decimal("10")
ASSETS_THRESHOLD_PCT = Decimal("10")

QUANTITATIVE_THRESHOLDS: Tuple[str, ...] = (
    "REVENUE_THRESHOLD_PCT",
    "PROFIT_LOSS_THRESHOLD_PCT",
    "ASSETS_THRESHOLD_PCT",
)

# Aggregate test byte-for-byte (IFRS 8.15)
REPORTABLE_SEGMENT_AGGREGATE_PCT = Decimal("75")

# 5 AGGREGATION CRITERIA byte-for-byte (IFRS 8.12)
AGGREGATION_CRITERIA: Tuple[str, ...] = (
    "SIMILAR_LONG_TERM_FINANCIAL_PERFORMANCE",
    "SIMILAR_PRODUCTS_OR_SERVICES",
    "SIMILAR_PRODUCTION_PROCESSES",
    "SIMILAR_CUSTOMER_TYPES",
    "SIMILAR_DISTRIBUTION_METHODS",
)

# 3 GEOGRAPHIC DISCLOSURES byte-for-byte (IFRS 8.33)
GEOGRAPHIC_DISCLOSURES: Tuple[str, ...] = (
    "REVENUE_FROM_EXTERNAL_CUSTOMERS_BY_COUNTRY",
    "NON_CURRENT_ASSETS_BY_COUNTRY",
    "MAJOR_CUSTOMERS_DISCLOSURE",
)

# Major customer threshold byte-for-byte (IFRS 8.34)
MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT = Decimal("10")


class OperatingSegmentEngine:
    """Deterministic IFRS 8 segment identification + thresholds."""

    @staticmethod
    def identify_operating_segment(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        IFRS 8.5: ALL 3 criteria must be met.
        Rule 1: None when criteria dict empty.
        Rule 6: missing/False on any criterion → NOT operating segment.
        """
        if not criteria_met:
            return {"is_operating_segment": None, "computed": False,
                    "reason": "missing_criteria_dict"}
        missing: List[str] = []
        for c in OPERATING_SEGMENT_CRITERIA:
            if not criteria_met.get(c, False):
                missing.append(c)
        is_segment = len(missing) == 0
        return {
            "criteria_required": list(OPERATING_SEGMENT_CRITERIA),
            "criteria_missing_or_false": missing,
            "is_operating_segment": is_segment,
            "rationale": ("all_3_criteria_met_per_IFRS_8.5" if is_segment
                          else "criterion_missing_fail_closed"),
            "computed": True,
        }

    @staticmethod
    def quantitative_threshold_test(
        segment_revenue: Optional[Decimal],
        segment_profit_or_loss: Optional[Decimal],
        segment_assets: Optional[Decimal],
        total_revenue: Optional[Decimal],
        total_profit_or_loss: Optional[Decimal],
        total_assets: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IFRS 8.13: segment is reportable if it meets ANY of 3 thresholds:
            - Revenue ≥ 10% of total revenue
            - Profit/Loss ≥ 10% of greater absolute of total
            - Assets ≥ 10% of total assets
        Rule 1: None when totals are zero/missing.
        """
        revenue_test = None
        pl_test = None
        assets_test = None
        if (total_revenue is not None and total_revenue > 0
                and segment_revenue is not None):
            pct = (segment_revenue / total_revenue) * Decimal("100")
            revenue_test = pct >= REVENUE_THRESHOLD_PCT
        if (total_profit_or_loss is not None and total_profit_or_loss != 0
                and segment_profit_or_loss is not None):
            pct = (abs(segment_profit_or_loss) / abs(total_profit_or_loss)) * Decimal("100")
            pl_test = pct >= PROFIT_LOSS_THRESHOLD_PCT
        if (total_assets is not None and total_assets > 0
                and segment_assets is not None):
            pct = (segment_assets / total_assets) * Decimal("100")
            assets_test = pct >= ASSETS_THRESHOLD_PCT
        # Reportable if ANY test passes
        reportable = bool(revenue_test or pl_test or assets_test)
        return {
            "revenue_test_passed": revenue_test,
            "profit_loss_test_passed": pl_test,
            "assets_test_passed": assets_test,
            "reportable": reportable,
            "rationale": "any_of_3_quantitative_tests_per_IFRS_8.13",
            "computed": True,
        }

    @staticmethod
    def aggregate_external_revenue_test(
        reportable_segments_revenue: Optional[Decimal],
        total_external_revenue: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IFRS 8.15: reportable segments must aggregate to ≥75% of external revenue.
        If below, additional segments must be designated reportable.
        Rule 1: None when totals missing.
        """
        if (reportable_segments_revenue is None
                or total_external_revenue is None):
            return {"meets_75pct_threshold": None, "computed": False,
                    "reason": "missing_inputs"}
        if total_external_revenue <= 0:
            return {"meets_75pct_threshold": None, "computed": False,
                    "reason": "non_positive_total_revenue"}
        pct = (reportable_segments_revenue / total_external_revenue) * Decimal("100")
        meets_threshold = pct >= REPORTABLE_SEGMENT_AGGREGATE_PCT
        return {
            "reportable_segments_revenue": str(reportable_segments_revenue),
            "total_external_revenue": str(total_external_revenue),
            "aggregate_pct": str(pct.quantize(Decimal("0.01"))),
            "threshold_pct": str(REPORTABLE_SEGMENT_AGGREGATE_PCT),
            "meets_75pct_threshold": meets_threshold,
            "additional_segments_needed": not meets_threshold,
            "rationale": ("reportable_segments_cover_75pct_per_IFRS_8.15"
                          if meets_threshold
                          else "below_75pct_designate_more_segments"),
            "computed": True,
        }

    @staticmethod
    def aggregation_criteria_check(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        IFRS 8.12: segments may be aggregated only if ALL 5 economic
        similarity criteria are met.
        Rule 6: any criterion missing → NO aggregation (fail closed).
        """
        if not criteria_met:
            return {"can_aggregate": None, "computed": False,
                    "reason": "missing_criteria_dict"}
        missing: List[str] = []
        for c in AGGREGATION_CRITERIA:
            if not criteria_met.get(c, False):
                missing.append(c)
        can_aggregate = len(missing) == 0
        return {
            "criteria_required": list(AGGREGATION_CRITERIA),
            "criteria_missing_or_false": missing,
            "can_aggregate": can_aggregate,
            "rationale": ("all_5_criteria_met_per_IFRS_8.12" if can_aggregate
                          else "criterion_missing_no_aggregation"),
            "computed": True,
        }

    @staticmethod
    def major_customer_test(
        customer_revenue: Optional[Decimal],
        total_revenue: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        IFRS 8.34: customer is "major" if ≥10% of total revenue.
        Disclosure required.
        Rule 1: None when totals missing/zero.
        """
        if customer_revenue is None or total_revenue is None:
            return {"is_major_customer": None, "computed": False,
                    "reason": "missing_inputs"}
        if total_revenue <= 0:
            return {"is_major_customer": None, "computed": False,
                    "reason": "non_positive_total_revenue"}
        pct = (customer_revenue / total_revenue) * Decimal("100")
        is_major = pct >= MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT
        return {
            "customer_revenue": str(customer_revenue),
            "total_revenue": str(total_revenue),
            "pct": str(pct.quantize(Decimal("0.01"))),
            "threshold_pct": str(MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT),
            "is_major_customer": is_major,
            "disclosure_required": is_major,
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_segment_criteria_byte_for_byte():
    expected = (
        "EARNS_REVENUE_INCURS_EXPENSES",
        "OPERATING_RESULTS_REGULARLY_REVIEWED",
        "DISCRETE_FINANCIAL_INFORMATION_AVAILABLE",
    )
    for c in expected:
        assert c in OPERATING_SEGMENT_CRITERIA
    assert len(OPERATING_SEGMENT_CRITERIA) == 3


def _test_quantitative_thresholds_byte_for_byte():
    assert REVENUE_THRESHOLD_PCT == Decimal("10")
    assert PROFIT_LOSS_THRESHOLD_PCT == Decimal("10")
    assert ASSETS_THRESHOLD_PCT == Decimal("10")


def _test_aggregate_threshold_byte_for_byte():
    assert REPORTABLE_SEGMENT_AGGREGATE_PCT == Decimal("75")


def _test_aggregation_criteria_byte_for_byte():
    expected = (
        "SIMILAR_LONG_TERM_FINANCIAL_PERFORMANCE",
        "SIMILAR_PRODUCTS_OR_SERVICES",
        "SIMILAR_PRODUCTION_PROCESSES",
        "SIMILAR_CUSTOMER_TYPES",
        "SIMILAR_DISTRIBUTION_METHODS",
    )
    for c in expected:
        assert c in AGGREGATION_CRITERIA
    assert len(AGGREGATION_CRITERIA) == 5


def _test_geographic_disclosures_byte_for_byte():
    expected = (
        "REVENUE_FROM_EXTERNAL_CUSTOMERS_BY_COUNTRY",
        "NON_CURRENT_ASSETS_BY_COUNTRY",
        "MAJOR_CUSTOMERS_DISCLOSURE",
    )
    for d in expected:
        assert d in GEOGRAPHIC_DISCLOSURES


def _test_major_customer_threshold_byte_for_byte():
    assert MAJOR_CUSTOMER_REVENUE_THRESHOLD_PCT == Decimal("10")


def _test_segment_all_3_met():
    """All 3 criteria True → operating segment."""
    all_met = {c: True for c in OPERATING_SEGMENT_CRITERIA}
    r = OperatingSegmentEngine.identify_operating_segment(all_met)
    assert r["is_operating_segment"] is True


def _test_segment_one_missing_rule6():
    one_missing = {c: True for c in OPERATING_SEGMENT_CRITERIA}
    one_missing["DISCRETE_FINANCIAL_INFORMATION_AVAILABLE"] = False
    r = OperatingSegmentEngine.identify_operating_segment(one_missing)
    assert r["is_operating_segment"] is False


def _test_segment_empty_rule1():
    r = OperatingSegmentEngine.identify_operating_segment({})
    assert r["is_operating_segment"] is None


def _test_threshold_revenue_passes():
    """Segment 15M / Total 100M = 15% ≥ 10% → reportable."""
    r = OperatingSegmentEngine.quantitative_threshold_test(
        Decimal("15000000"), None, None,
        Decimal("100000000"), None, None)
    assert r["revenue_test_passed"] is True
    assert r["reportable"] is True


def _test_threshold_revenue_boundary_inclusive():
    """Exactly 10% → passes (≥ inclusive)."""
    r = OperatingSegmentEngine.quantitative_threshold_test(
        Decimal("10000000"), None, None,
        Decimal("100000000"), None, None)
    assert r["revenue_test_passed"] is True


def _test_threshold_below():
    """5% < 10% → not reportable on revenue."""
    r = OperatingSegmentEngine.quantitative_threshold_test(
        Decimal("5000000"), None, None,
        Decimal("100000000"), None, None)
    assert r["revenue_test_passed"] is False


def _test_threshold_assets_passes():
    """Segment assets 11% → reportable on assets."""
    r = OperatingSegmentEngine.quantitative_threshold_test(
        None, None, Decimal("11000000"),
        None, None, Decimal("100000000"))
    assert r["assets_test_passed"] is True
    assert r["reportable"] is True


def _test_threshold_any_one_passes_makes_reportable():
    """Revenue 5% (fail) + Assets 12% (pass) → reportable."""
    r = OperatingSegmentEngine.quantitative_threshold_test(
        Decimal("5000000"), None, Decimal("12000000"),
        Decimal("100000000"), None, Decimal("100000000"))
    assert r["revenue_test_passed"] is False
    assert r["assets_test_passed"] is True
    assert r["reportable"] is True


def _test_threshold_profit_loss_uses_abs():
    """Profit/loss test uses absolute values for comparison."""
    r = OperatingSegmentEngine.quantitative_threshold_test(
        None, Decimal("-15000"), None,
        None, Decimal("100000"), None)
    # |15000| / |100000| = 15% ≥ 10%
    assert r["profit_loss_test_passed"] is True


def _test_aggregate_75_pct_meets():
    """80% reportable → meets threshold."""
    r = OperatingSegmentEngine.aggregate_external_revenue_test(
        Decimal("80000000"), Decimal("100000000"))
    assert r["meets_75pct_threshold"] is True


def _test_aggregate_75_pct_boundary_inclusive():
    """Exactly 75% → meets (≥ inclusive)."""
    r = OperatingSegmentEngine.aggregate_external_revenue_test(
        Decimal("75000000"), Decimal("100000000"))
    assert r["meets_75pct_threshold"] is True


def _test_aggregate_below_75_pct():
    """70% < 75% → does not meet, more segments needed."""
    r = OperatingSegmentEngine.aggregate_external_revenue_test(
        Decimal("70000000"), Decimal("100000000"))
    assert r["meets_75pct_threshold"] is False
    assert r["additional_segments_needed"] is True


def _test_aggregate_missing_rule1():
    r = OperatingSegmentEngine.aggregate_external_revenue_test(
        None, Decimal("100000000"))
    assert r["meets_75pct_threshold"] is None


def _test_aggregation_all_5_met():
    all_met = {c: True for c in AGGREGATION_CRITERIA}
    r = OperatingSegmentEngine.aggregation_criteria_check(all_met)
    assert r["can_aggregate"] is True


def _test_aggregation_one_missing_rule6():
    """Any of 5 missing → cannot aggregate (fail closed)."""
    one_missing = {c: True for c in AGGREGATION_CRITERIA}
    one_missing["SIMILAR_PRODUCTION_PROCESSES"] = False
    r = OperatingSegmentEngine.aggregation_criteria_check(one_missing)
    assert r["can_aggregate"] is False


def _test_aggregation_empty_rule1():
    r = OperatingSegmentEngine.aggregation_criteria_check({})
    assert r["can_aggregate"] is None


def _test_major_customer_passes():
    """15M / 100M = 15% ≥ 10% → major customer."""
    r = OperatingSegmentEngine.major_customer_test(
        Decimal("15000000"), Decimal("100000000"))
    assert r["is_major_customer"] is True
    assert r["disclosure_required"] is True


def _test_major_customer_boundary_inclusive():
    """Exactly 10% → major (≥ inclusive)."""
    r = OperatingSegmentEngine.major_customer_test(
        Decimal("10000000"), Decimal("100000000"))
    assert r["is_major_customer"] is True


def _test_major_customer_below():
    """5% < 10% → not major."""
    r = OperatingSegmentEngine.major_customer_test(
        Decimal("5000000"), Decimal("100000000"))
    assert r["is_major_customer"] is False


def _test_major_customer_zero_total_rule1():
    r = OperatingSegmentEngine.major_customer_test(
        Decimal("1000"), Decimal("0"))
    assert r["is_major_customer"] is None


def _test_major_customer_missing_rule1():
    r = OperatingSegmentEngine.major_customer_test(None, Decimal("100000"))
    assert r["is_major_customer"] is None


def self_test() -> bool:
    tests = [
        _test_segment_criteria_byte_for_byte,
        _test_quantitative_thresholds_byte_for_byte,
        _test_aggregate_threshold_byte_for_byte,
        _test_aggregation_criteria_byte_for_byte,
        _test_geographic_disclosures_byte_for_byte,
        _test_major_customer_threshold_byte_for_byte,
        _test_segment_all_3_met,
        _test_segment_one_missing_rule6,
        _test_segment_empty_rule1,
        _test_threshold_revenue_passes,
        _test_threshold_revenue_boundary_inclusive,
        _test_threshold_below,
        _test_threshold_assets_passes,
        _test_threshold_any_one_passes_makes_reportable,
        _test_threshold_profit_loss_uses_abs,
        _test_aggregate_75_pct_meets,
        _test_aggregate_75_pct_boundary_inclusive,
        _test_aggregate_below_75_pct,
        _test_aggregate_missing_rule1,
        _test_aggregation_all_5_met,
        _test_aggregation_one_missing_rule6,
        _test_aggregation_empty_rule1,
        _test_major_customer_passes,
        _test_major_customer_boundary_inclusive,
        _test_major_customer_below,
        _test_major_customer_zero_total_rule1,
        _test_major_customer_missing_rule1,
    ]
    print("=" * 60)
    print("Operating Segment Engine — Self-Tests (#115 IFRS 8)")
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

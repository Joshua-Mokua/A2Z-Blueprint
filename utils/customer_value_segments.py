"""
================================================================================
A2Z MIS 360 — Standard #95: Customer Lifetime Value & Segment Profitability
================================================================================

Risk classification: Cat B (deterministic NPV-based CLV computation)

Provides:
    - clv(...)                          -- present value of expected cash flows
    - segment_classification(...)       -- by annual contribution
    - tenure_band(...)                  -- NEW / DEVELOPING / ESTABLISHED / LOYAL
    - activity_status(...)              -- ACTIVE / DORMANT / ATTRITED
    - segment_profitability_aggregate(...)  -- per-segment P&L roll-up

NOTE: This module is separate from `customer_lifetime_value.py` (Standard #70).
#70 covers a different CLV facet — this module (#95) ships the value-tiered
segment profitability engine with annual-contribution-based tier classification
(PLATINUM/GOLD/SILVER/BRONZE), tenure-based bands, and explicit cost-of-capital
discounting.

6 CUSTOMER_SEGMENTS byte-for-byte:
    MASS, AFFLUENT, HNW, SME, CORPORATE, GOVERNMENT

4 SEGMENT_TIERS byte-for-byte (annual contribution KES):
    PLATINUM (≥1M)
    GOLD     (250K-1M)
    SILVER   (50K-250K)
    BRONZE   (<50K)

SEGMENT_TIER_BANDS_KES byte-for-byte:
    PLATINUM : (1000000, 999999999999)
    GOLD     : (250000, 999999)
    SILVER   : (50000, 249999)
    BRONZE   : (0, 49999)

4 TENURE_BANDS byte-for-byte:
    NEW          (<1yr)
    DEVELOPING   (1-3yr)
    ESTABLISHED  (3-7yr)
    LOYAL        (7+yr)

3 ACTIVITY_STATUSES byte-for-byte:
    ACTIVE, DORMANT, ATTRITED

Activity thresholds byte-for-byte:
    DORMANT_THRESHOLD_DAYS = 90
    ATTRITED_THRESHOLD_DAYS = 180

CLV formula:
    CLV = Σ (annual_contribution × retention_rate^t) / (1 + r)^t
          for t = 0..tenure-1

Default discount rate byte-for-byte (cost of capital):
    DEFAULT_DISCOUNT_RATE_PCT = 15

Honesty rules applied:
    Rule 1: clv=None when annual_contribution<=0 or expected_tenure<=0
    Rule 6: unknown segment / activity status surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 6 CUSTOMER SEGMENTS byte-for-byte
CUSTOMER_SEGMENTS: Tuple[str, ...] = (
    "MASS", "AFFLUENT", "HNW", "SME", "CORPORATE", "GOVERNMENT",
)

# 4 SEGMENT TIERS byte-for-byte
SEGMENT_TIERS: Tuple[str, ...] = ("PLATINUM", "GOLD", "SILVER", "BRONZE")

# Segment tier bands (annual contribution KES) byte-for-byte
SEGMENT_TIER_BANDS_KES: Dict[str, Tuple[int, int]] = {
    "PLATINUM": (1000000, 999999999999),
    "GOLD": (250000, 999999),
    "SILVER": (50000, 249999),
    "BRONZE": (0, 49999),
}

# 4 TENURE BANDS byte-for-byte
TENURE_BANDS: Tuple[str, ...] = (
    "NEW", "DEVELOPING", "ESTABLISHED", "LOYAL",
)

TENURE_BAND_YEARS: Dict[str, Tuple[float, float]] = {
    "NEW": (0, 1),
    "DEVELOPING": (1, 3),
    "ESTABLISHED": (3, 7),
    "LOYAL": (7, 999),
}

# 3 ACTIVITY STATUSES byte-for-byte
ACTIVITY_STATUSES: Tuple[str, ...] = ("ACTIVE", "DORMANT", "ATTRITED")

# Activity thresholds byte-for-byte
DORMANT_THRESHOLD_DAYS = 90
ATTRITED_THRESHOLD_DAYS = 180

# Default cost-of-capital discount rate byte-for-byte
DEFAULT_DISCOUNT_RATE_PCT = Decimal("15")


@dataclass
class ClvInputs:
    customer_id: str
    annual_contribution_kes: Optional[Decimal] = None
    expected_tenure_years: Optional[int] = None
    retention_rate_pct: Optional[Decimal] = None  # e.g. 90 = 90% YoY retention
    discount_rate_pct: Optional[Decimal] = None


class CustomerValueEngine:
    """Deterministic CLV + segment profitability computation."""

    @staticmethod
    def clv(inputs: ClvInputs) -> Dict[str, Any]:
        """
        Compute customer lifetime value as discounted sum of expected cash flows.
        Rule 1: clv=None when annual_contribution<=0 or tenure<=0.
        """
        ac = inputs.annual_contribution_kes
        tenure = inputs.expected_tenure_years
        retention = inputs.retention_rate_pct
        discount = inputs.discount_rate_pct if inputs.discount_rate_pct is not None else DEFAULT_DISCOUNT_RATE_PCT
        if ac is None or ac <= 0 or tenure is None or tenure <= 0:
            return {
                "customer_id": inputs.customer_id,
                "clv_kes": None,
                "computed": False,
                "reason": "invalid_contribution_or_tenure",
            }
        if retention is None or retention <= 0:
            return {
                "customer_id": inputs.customer_id,
                "clv_kes": None,
                "computed": False,
                "reason": "invalid_retention_rate",
            }
        retention_mult = retention / Decimal("100")
        discount_mult = discount / Decimal("100")
        clv_value = Decimal("0")
        for t in range(tenure):
            survival_prob = retention_mult ** t
            discount_factor = (Decimal("1") + discount_mult) ** t
            period_pv = (ac * survival_prob) / discount_factor
            clv_value += period_pv
        return {
            "customer_id": inputs.customer_id,
            "annual_contribution_kes": str(ac),
            "expected_tenure_years": tenure,
            "retention_rate_pct": str(retention),
            "discount_rate_pct": str(discount),
            "clv_kes": str(clv_value.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def segment_classification(
        annual_contribution_kes: Optional[Decimal],
    ) -> Optional[str]:
        """
        Classify into PLATINUM/GOLD/SILVER/BRONZE by annual contribution.
        Rule 1: None when contribution missing.
        """
        if annual_contribution_kes is None:
            return None
        ac = int(annual_contribution_kes)
        for tier in SEGMENT_TIERS:
            lo, hi = SEGMENT_TIER_BANDS_KES[tier]
            if lo <= ac <= hi:
                return tier
        return None

    @staticmethod
    def tenure_band(years_open: Optional[float]) -> Optional[str]:
        """Rule 1: None when years_open missing or invalid."""
        if years_open is None or years_open < 0:
            return None
        for band in TENURE_BANDS:
            lo, hi = TENURE_BAND_YEARS[band]
            if lo <= years_open < hi:
                return band
        return None

    @staticmethod
    def activity_status(days_since_last_txn: Optional[int]) -> Optional[str]:
        """
        Classify customer activity.
        Rule 1: None when days_since_last_txn missing or negative.
        """
        if days_since_last_txn is None or days_since_last_txn < 0:
            return None
        if days_since_last_txn >= ATTRITED_THRESHOLD_DAYS:
            return "ATTRITED"
        if days_since_last_txn >= DORMANT_THRESHOLD_DAYS:
            return "DORMANT"
        return "ACTIVE"

    @staticmethod
    def segment_profitability_aggregate(
        customers: List[Dict[str, Any]],
        segment: str,
    ) -> Dict[str, Any]:
        """
        Aggregate annual contribution across customers in a segment.
        Rule 1: avg_contribution=None when no customers.
        Rule 6: unknown segment surfaced.
        """
        if segment not in CUSTOMER_SEGMENTS:
            return {
                "segment": segment, "computed": False,
                "reason": f"unknown_segment:{segment}",
                "valid_segments": list(CUSTOMER_SEGMENTS),
            }
        in_segment = [c for c in customers if c.get("segment") == segment]
        n = len(in_segment)
        if n == 0:
            return {
                "segment": segment,
                "n": 0,
                "total_contribution_kes": "0",
                "avg_contribution_kes": None,
                "computed": True,
            }
        total = sum(Decimal(str(c.get("annual_contribution_kes", 0)))
                    for c in in_segment)
        avg = total / Decimal(n)
        return {
            "segment": segment,
            "n": n,
            "total_contribution_kes": str(total.quantize(Decimal("0.01"))),
            "avg_contribution_kes": str(avg.quantize(Decimal("0.01"))),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_segments_byte_for_byte():
    expected = ("MASS", "AFFLUENT", "HNW", "SME", "CORPORATE", "GOVERNMENT")
    for s in expected:
        assert s in CUSTOMER_SEGMENTS
    assert len(CUSTOMER_SEGMENTS) == 6


def _test_segment_tiers_byte_for_byte():
    expected = ("PLATINUM", "GOLD", "SILVER", "BRONZE")
    for t in expected:
        assert t in SEGMENT_TIERS
    assert len(SEGMENT_TIERS) == 4


def _test_segment_tier_bands_byte_for_byte():
    assert SEGMENT_TIER_BANDS_KES["PLATINUM"][0] == 1000000
    assert SEGMENT_TIER_BANDS_KES["GOLD"] == (250000, 999999)
    assert SEGMENT_TIER_BANDS_KES["SILVER"] == (50000, 249999)
    assert SEGMENT_TIER_BANDS_KES["BRONZE"] == (0, 49999)


def _test_tenure_bands_byte_for_byte():
    expected = ("NEW", "DEVELOPING", "ESTABLISHED", "LOYAL")
    for b in expected:
        assert b in TENURE_BANDS
    assert TENURE_BAND_YEARS["NEW"] == (0, 1)
    assert TENURE_BAND_YEARS["DEVELOPING"] == (1, 3)
    assert TENURE_BAND_YEARS["ESTABLISHED"] == (3, 7)
    assert TENURE_BAND_YEARS["LOYAL"] == (7, 999)


def _test_activity_statuses_byte_for_byte():
    expected = ("ACTIVE", "DORMANT", "ATTRITED")
    for s in expected:
        assert s in ACTIVITY_STATUSES


def _test_thresholds_byte_for_byte():
    assert DORMANT_THRESHOLD_DAYS == 90
    assert ATTRITED_THRESHOLD_DAYS == 180


def _test_discount_rate_byte_for_byte():
    assert DEFAULT_DISCOUNT_RATE_PCT == Decimal("15")


def _test_clv_basic():
    """1yr tenure, 100K, 100% retention, 0% discount → CLV = 100K."""
    r = CustomerValueEngine.clv(ClvInputs(
        customer_id="C1",
        annual_contribution_kes=Decimal("100000"),
        expected_tenure_years=1,
        retention_rate_pct=Decimal("100"),
        discount_rate_pct=Decimal("0"),
    ))
    assert r["clv_kes"] == "100000.00"


def _test_clv_with_retention_and_discount():
    """3yr, 100K, 80% retention, 10% discount → ≈225K."""
    r = CustomerValueEngine.clv(ClvInputs(
        customer_id="C2",
        annual_contribution_kes=Decimal("100000"),
        expected_tenure_years=3,
        retention_rate_pct=Decimal("80"),
        discount_rate_pct=Decimal("10"),
    ))
    assert r["computed"] is True
    clv = Decimal(r["clv_kes"])
    assert clv > Decimal("220000") and clv < Decimal("230000")


def _test_clv_zero_contribution_rule1():
    r = CustomerValueEngine.clv(ClvInputs(
        customer_id="C1", annual_contribution_kes=Decimal("0"),
        expected_tenure_years=5, retention_rate_pct=Decimal("90")))
    assert r["clv_kes"] is None


def _test_clv_zero_tenure_rule1():
    r = CustomerValueEngine.clv(ClvInputs(
        customer_id="C1", annual_contribution_kes=Decimal("100000"),
        expected_tenure_years=0, retention_rate_pct=Decimal("90")))
    assert r["clv_kes"] is None


def _test_clv_default_discount_rate_used():
    r = CustomerValueEngine.clv(ClvInputs(
        customer_id="C1", annual_contribution_kes=Decimal("100000"),
        expected_tenure_years=2, retention_rate_pct=Decimal("90")))
    assert r["discount_rate_pct"] == "15"


def _test_segment_platinum():
    assert CustomerValueEngine.segment_classification(Decimal("1500000")) == "PLATINUM"


def _test_segment_gold():
    assert CustomerValueEngine.segment_classification(Decimal("500000")) == "GOLD"


def _test_segment_silver():
    assert CustomerValueEngine.segment_classification(Decimal("100000")) == "SILVER"


def _test_segment_bronze():
    assert CustomerValueEngine.segment_classification(Decimal("10000")) == "BRONZE"


def _test_segment_boundary_platinum():
    assert CustomerValueEngine.segment_classification(Decimal("1000000")) == "PLATINUM"


def _test_segment_missing_rule1():
    assert CustomerValueEngine.segment_classification(None) is None


def _test_tenure_new():
    assert CustomerValueEngine.tenure_band(0.5) == "NEW"


def _test_tenure_developing():
    assert CustomerValueEngine.tenure_band(2.0) == "DEVELOPING"


def _test_tenure_established():
    assert CustomerValueEngine.tenure_band(5.0) == "ESTABLISHED"


def _test_tenure_loyal():
    assert CustomerValueEngine.tenure_band(10.0) == "LOYAL"


def _test_tenure_missing_rule1():
    assert CustomerValueEngine.tenure_band(None) is None
    assert CustomerValueEngine.tenure_band(-1) is None


def _test_activity_active():
    assert CustomerValueEngine.activity_status(30) == "ACTIVE"


def _test_activity_dormant():
    assert CustomerValueEngine.activity_status(120) == "DORMANT"


def _test_activity_attrited():
    assert CustomerValueEngine.activity_status(200) == "ATTRITED"


def _test_activity_boundary_dormant():
    assert CustomerValueEngine.activity_status(90) == "DORMANT"


def _test_activity_boundary_attrited():
    assert CustomerValueEngine.activity_status(180) == "ATTRITED"


def _test_activity_missing_rule1():
    assert CustomerValueEngine.activity_status(None) is None
    assert CustomerValueEngine.activity_status(-1) is None


def _test_segment_aggregate_basic():
    customers = [
        {"customer_id": "C1", "segment": "MASS", "annual_contribution_kes": 50000},
        {"customer_id": "C2", "segment": "MASS", "annual_contribution_kes": 100000},
        {"customer_id": "C3", "segment": "AFFLUENT", "annual_contribution_kes": 500000},
    ]
    r = CustomerValueEngine.segment_profitability_aggregate(customers, "MASS")
    assert r["n"] == 2
    assert r["total_contribution_kes"] == "150000.00"
    assert r["avg_contribution_kes"] == "75000.00"


def _test_segment_aggregate_empty_rule1():
    r = CustomerValueEngine.segment_profitability_aggregate([], "MASS")
    assert r["n"] == 0
    assert r["avg_contribution_kes"] is None


def _test_segment_aggregate_unknown_rule6():
    r = CustomerValueEngine.segment_profitability_aggregate([], "WEIRD")
    assert r["computed"] is False


def self_test() -> bool:
    tests = [
        _test_segments_byte_for_byte,
        _test_segment_tiers_byte_for_byte,
        _test_segment_tier_bands_byte_for_byte,
        _test_tenure_bands_byte_for_byte,
        _test_activity_statuses_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_discount_rate_byte_for_byte,
        _test_clv_basic,
        _test_clv_with_retention_and_discount,
        _test_clv_zero_contribution_rule1,
        _test_clv_zero_tenure_rule1,
        _test_clv_default_discount_rate_used,
        _test_segment_platinum,
        _test_segment_gold,
        _test_segment_silver,
        _test_segment_bronze,
        _test_segment_boundary_platinum,
        _test_segment_missing_rule1,
        _test_tenure_new,
        _test_tenure_developing,
        _test_tenure_established,
        _test_tenure_loyal,
        _test_tenure_missing_rule1,
        _test_activity_active,
        _test_activity_dormant,
        _test_activity_attrited,
        _test_activity_boundary_dormant,
        _test_activity_boundary_attrited,
        _test_activity_missing_rule1,
        _test_segment_aggregate_basic,
        _test_segment_aggregate_empty_rule1,
        _test_segment_aggregate_unknown_rule6,
    ]
    print("=" * 60)
    print("Customer Value & Segment Engine — Self-Tests (#95)")
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

"""
================================================================================
A2Z MIS 360 — Standard #74: Interest Rate Risk in Banking Book (IRRBB) Engine
================================================================================

Risk classification: Cat B (deterministic Basel/CBK regulatory metrics)

Computes IRRBB metrics per Basel Committee BCBS 368 (April 2016) and CBK:
    - repricing_gap(buckets)            -- cumulative gap by tenor
    - nii_sensitivity_200bps(...)       -- 12-month NII impact under 200bps shock
    - eve_sensitivity(buckets, shock)   -- EVE change under standardised shocks
    - basis_risk_exposure(...)          -- spread between admin rates and market rates

Standardised interest rate shock scenarios (BCBS 368 + CBK):
    PARALLEL_UP        : +200 bps
    PARALLEL_DOWN      : -200 bps
    STEEPENER          : short -65bps, long +90bps
    FLATTENER          : short +90bps, long -65bps
    SHORT_RATE_UP      : short +300 bps
    SHORT_RATE_DOWN    : short -300 bps

Outlier thresholds (Basel BCBS 368 + CBK supervisory):
    EVE / Tier 1 capital change >= 15% under any scenario = OUTLIER
    NII / Tier 1 capital change >= 5%  under +/- 200bps    = OUTLIER

Repricing buckets (standard tenor ladder):
    O/N, 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 10Y+

Honesty rules applied:
    Rule 1: ratios = None when capital base <= 0
    Rule 6: missing balance/rate data surfaced in `excluded_count`

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Repricing tenor buckets (in days, midpoint of bucket used for discounting)
REPRICING_BUCKETS: Tuple[str, ...] = (
    "ON_DEMAND", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "10Y_PLUS",
)

# Bucket midpoint days (for discounting cash flows)
BUCKET_MIDPOINT_DAYS: Dict[str, int] = {
    "ON_DEMAND": 1,
    "1M": 15,
    "3M": 60,
    "6M": 135,
    "1Y": 270,
    "2Y": 540,
    "3Y": 900,
    "5Y": 1440,
    "7Y": 2160,
    "10Y": 3240,
    "10Y_PLUS": 4320,  # midpoint at 12 years
}

# Standardised IRRBB shock scenarios (basis points)
SHOCK_SCENARIOS: Dict[str, Dict[str, int]] = {
    "PARALLEL_UP": {"all": 200},
    "PARALLEL_DOWN": {"all": -200},
    "STEEPENER": {"short": -65, "long": 90},
    "FLATTENER": {"short": 90, "long": -65},
    "SHORT_RATE_UP": {"short": 300},
    "SHORT_RATE_DOWN": {"short": -300},
}

VALID_SCENARIOS: Tuple[str, ...] = tuple(SHOCK_SCENARIOS.keys())

# Outlier thresholds (% of Tier 1 capital)
EVE_OUTLIER_THRESHOLD_PCT = Decimal("15")
NII_OUTLIER_THRESHOLD_PCT = Decimal("5")

# Standard parallel shock for NII analysis
NII_STANDARD_SHOCK_BPS = 200


@dataclass
class RepricingBucket:
    bucket: str
    rate_sensitive_assets_kes: Optional[Decimal] = None
    rate_sensitive_liabilities_kes: Optional[Decimal] = None
    weighted_avg_rate_pct: Optional[Decimal] = None  # for NII calc


@dataclass
class IrrbbInputs:
    buckets: List[RepricingBucket]
    tier_1_capital_kes: Optional[Decimal] = None


def _to_decimal(amount: Any) -> Optional[Decimal]:
    if amount is None:
        return None
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount))


class IrrbbEngine:
    """Deterministic IRRBB computation per BCBS 368."""

    @staticmethod
    def repricing_gap(buckets: List[RepricingBucket]) -> Dict[str, Any]:
        """
        Compute repricing gap (RSA - RSL) per bucket and cumulative.
        Rule 6: buckets with None RSA or None RSL excluded with count surfaced.
        """
        gaps = []
        cumulative = Decimal("0")
        excluded = []
        for b in buckets:
            if b.bucket not in REPRICING_BUCKETS:
                excluded.append(b.bucket)
                continue
            if b.rate_sensitive_assets_kes is None or b.rate_sensitive_liabilities_kes is None:
                excluded.append(b.bucket)
                continue
            gap = b.rate_sensitive_assets_kes - b.rate_sensitive_liabilities_kes
            cumulative += gap
            gaps.append({
                "bucket": b.bucket,
                "rsa_kes": str(b.rate_sensitive_assets_kes.quantize(Decimal("0.01"))),
                "rsl_kes": str(b.rate_sensitive_liabilities_kes.quantize(Decimal("0.01"))),
                "gap_kes": str(gap.quantize(Decimal("0.01"))),
                "cumulative_gap_kes": str(cumulative.quantize(Decimal("0.01"))),
            })
        return {
            "bucket_count": len(gaps),
            "excluded_count": len(excluded),
            "buckets": gaps,
            "total_cumulative_gap_kes": str(cumulative.quantize(Decimal("0.01"))),
        }

    @staticmethod
    def nii_sensitivity_200bps(
        buckets: List[RepricingBucket],
        tier_1_capital_kes: Optional[Decimal],
        shock_direction: str = "UP",  # UP or DOWN
    ) -> Dict[str, Any]:
        """
        12-month NII impact under +/- 200bps parallel shock.

        Approach: only buckets repricing within 1 year contribute. NII impact
        per bucket = gap × shock × (months_remaining_in_year / 12).

        Rule 1: outlier_pct = None when tier_1_capital <= 0.
        Rule 6: buckets with missing data excluded.
        """
        shock_bps = NII_STANDARD_SHOCK_BPS if shock_direction == "UP" else -NII_STANDARD_SHOCK_BPS
        shock_decimal = Decimal(shock_bps) / Decimal("10000")

        # Buckets repricing within 1 year (12 months)
        within_year = ("ON_DEMAND", "1M", "3M", "6M", "1Y")
        impact = Decimal("0")
        excluded = []
        contributors = []
        for b in buckets:
            if b.bucket not in within_year:
                continue
            if b.rate_sensitive_assets_kes is None or b.rate_sensitive_liabilities_kes is None:
                excluded.append(b.bucket)
                continue
            gap = b.rate_sensitive_assets_kes - b.rate_sensitive_liabilities_kes
            mid_days = BUCKET_MIDPOINT_DAYS[b.bucket]
            # Time-weight for 12-month window
            weight_days = max(0, 365 - mid_days)
            weight = Decimal(weight_days) / Decimal("365")
            bucket_impact = gap * shock_decimal * weight
            impact += bucket_impact
            contributors.append({
                "bucket": b.bucket,
                "gap_kes": str(gap.quantize(Decimal("0.01"))),
                "weight": str(weight.quantize(Decimal("0.0001"))),
                "impact_kes": str(bucket_impact.quantize(Decimal("0.01"))),
            })

        if tier_1_capital_kes is None or tier_1_capital_kes <= 0:
            return {
                "shock_bps": shock_bps,
                "nii_impact_kes": str(impact.quantize(Decimal("0.01"))),
                "tier_1_capital_kes": str(tier_1_capital_kes) if tier_1_capital_kes else None,
                "outlier_pct": None,
                "is_outlier": None,
                "reason": "tier_1_capital_zero_or_negative",
                "excluded_count": len(excluded),
            }

        outlier_pct = abs(impact) / tier_1_capital_kes * Decimal("100")
        is_outlier = outlier_pct >= NII_OUTLIER_THRESHOLD_PCT

        return {
            "shock_bps": shock_bps,
            "nii_impact_kes": str(impact.quantize(Decimal("0.01"))),
            "tier_1_capital_kes": str(tier_1_capital_kes.quantize(Decimal("0.01"))),
            "outlier_pct": str(outlier_pct.quantize(Decimal("0.01"))),
            "outlier_threshold_pct": str(NII_OUTLIER_THRESHOLD_PCT),
            "is_outlier": is_outlier,
            "contributors": contributors,
            "excluded_count": len(excluded),
        }

    @staticmethod
    def eve_sensitivity(
        buckets: List[RepricingBucket],
        scenario: str,
        tier_1_capital_kes: Optional[Decimal],
        discount_rate_pct: Decimal = Decimal("10.0"),  # base discount rate
    ) -> Dict[str, Any]:
        """
        Economic Value of Equity sensitivity under a shock scenario.

        Approach: For each bucket, compute PV of net position before and after
        applying the shock to the discount rate. EVE change = sum of differences.

        Rule 1: outlier_pct = None when tier_1_capital <= 0.
        """
        if scenario not in SHOCK_SCENARIOS:
            return {"scenario": scenario, "error": f"unknown_scenario:{scenario}"}

        shock_def = SHOCK_SCENARIOS[scenario]

        eve_change = Decimal("0")
        excluded = []
        details = []
        for b in buckets:
            if b.bucket not in REPRICING_BUCKETS:
                excluded.append(b.bucket)
                continue
            if b.rate_sensitive_assets_kes is None or b.rate_sensitive_liabilities_kes is None:
                excluded.append(b.bucket)
                continue
            net = b.rate_sensitive_assets_kes - b.rate_sensitive_liabilities_kes
            mid_days = BUCKET_MIDPOINT_DAYS[b.bucket]
            mid_years = Decimal(mid_days) / Decimal("365")

            # Determine shock applied
            # short = up to 1Y, long = 5Y+, others = blended
            if "all" in shock_def:
                bps = shock_def["all"]
            elif b.bucket in ("ON_DEMAND", "1M", "3M", "6M", "1Y"):
                bps = shock_def.get("short", 0)
            elif b.bucket in ("5Y", "7Y", "10Y", "10Y_PLUS"):
                bps = shock_def.get("long", 0)
            else:  # 2Y, 3Y - blended midpoint
                bps = (shock_def.get("short", 0) + shock_def.get("long", 0)) // 2

            # EVE change = -duration × shock × position
            # Use simple approximation: effective duration ≈ midpoint years
            shock_decimal = Decimal(bps) / Decimal("10000")
            bucket_eve_change = -net * mid_years * shock_decimal
            eve_change += bucket_eve_change
            details.append({
                "bucket": b.bucket,
                "net_position_kes": str(net.quantize(Decimal("0.01"))),
                "applied_bps": bps,
                "duration_years": str(mid_years.quantize(Decimal("0.01"))),
                "eve_impact_kes": str(bucket_eve_change.quantize(Decimal("0.01"))),
            })

        if tier_1_capital_kes is None or tier_1_capital_kes <= 0:
            return {
                "scenario": scenario,
                "eve_change_kes": str(eve_change.quantize(Decimal("0.01"))),
                "tier_1_capital_kes": None,
                "outlier_pct": None,
                "is_outlier": None,
                "reason": "tier_1_capital_zero_or_negative",
                "excluded_count": len(excluded),
            }

        outlier_pct = abs(eve_change) / tier_1_capital_kes * Decimal("100")
        is_outlier = outlier_pct >= EVE_OUTLIER_THRESHOLD_PCT

        return {
            "scenario": scenario,
            "eve_change_kes": str(eve_change.quantize(Decimal("0.01"))),
            "tier_1_capital_kes": str(tier_1_capital_kes.quantize(Decimal("0.01"))),
            "outlier_pct": str(outlier_pct.quantize(Decimal("0.01"))),
            "outlier_threshold_pct": str(EVE_OUTLIER_THRESHOLD_PCT),
            "is_outlier": is_outlier,
            "buckets_applied": details,
            "excluded_count": len(excluded),
        }

    @classmethod
    def all_scenarios_summary(
        cls,
        inputs: IrrbbInputs,
    ) -> Dict[str, Any]:
        """Run all 6 standardised scenarios + NII +/- 200bps."""
        eve_results = []
        worst_pct = Decimal("0")
        worst_scenario = None
        for sc in VALID_SCENARIOS:
            r = cls.eve_sensitivity(inputs.buckets, sc, inputs.tier_1_capital_kes)
            eve_results.append(r)
            if r.get("outlier_pct") is not None:
                p = Decimal(r["outlier_pct"])
                if p > worst_pct:
                    worst_pct = p
                    worst_scenario = sc

        nii_up = cls.nii_sensitivity_200bps(inputs.buckets, inputs.tier_1_capital_kes, "UP")
        nii_down = cls.nii_sensitivity_200bps(inputs.buckets, inputs.tier_1_capital_kes, "DOWN")

        return {
            "eve_scenarios": eve_results,
            "worst_eve_scenario": worst_scenario,
            "worst_eve_outlier_pct": str(worst_pct) if worst_scenario else None,
            "nii_200bps_up": nii_up,
            "nii_200bps_down": nii_down,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _bucket(**kw):
    defaults = dict(bucket="1Y",
                    rate_sensitive_assets_kes=Decimal("1000000000"),
                    rate_sensitive_liabilities_kes=Decimal("800000000"))
    defaults.update(kw)
    return RepricingBucket(**defaults)


def _test_repricing_gap_basic():
    bs = [_bucket(bucket="3M",
                  rate_sensitive_assets_kes=Decimal("500000000"),
                  rate_sensitive_liabilities_kes=Decimal("300000000")),
          _bucket(bucket="1Y",
                  rate_sensitive_assets_kes=Decimal("400000000"),
                  rate_sensitive_liabilities_kes=Decimal("600000000"))]
    r = IrrbbEngine.repricing_gap(bs)
    assert r["bucket_count"] == 2
    # 3M gap = +200M; 1Y gap = -200M; cumulative = 0
    assert r["total_cumulative_gap_kes"] == "0.00"


def _test_repricing_gap_excluded_rule6():
    bs = [_bucket(rate_sensitive_assets_kes=None)]
    r = IrrbbEngine.repricing_gap(bs)
    assert r["excluded_count"] == 1


def _test_repricing_gap_unknown_bucket():
    bs = [_bucket(bucket="WEIRD")]
    r = IrrbbEngine.repricing_gap(bs)
    assert r["excluded_count"] == 1


def _test_nii_sensitivity_up_shock():
    """Positive gap + shock up = positive NII impact."""
    bs = [_bucket(bucket="3M",
                  rate_sensitive_assets_kes=Decimal("1000000000"),
                  rate_sensitive_liabilities_kes=Decimal("500000000"))]
    r = IrrbbEngine.nii_sensitivity_200bps(bs, Decimal("100000000"), "UP")
    assert r["shock_bps"] == 200
    impact = Decimal(r["nii_impact_kes"])
    assert impact > 0


def _test_nii_outlier():
    """Big gap + shock vs small T1 = outlier."""
    bs = [_bucket(bucket="3M",
                  rate_sensitive_assets_kes=Decimal("10000000000"),
                  rate_sensitive_liabilities_kes=Decimal("1000000000"))]
    r = IrrbbEngine.nii_sensitivity_200bps(bs, Decimal("100000000"), "UP")
    assert r["is_outlier"] is True


def _test_nii_no_capital_rule1():
    bs = [_bucket()]
    r = IrrbbEngine.nii_sensitivity_200bps(bs, None, "UP")
    assert r["outlier_pct"] is None


def _test_eve_parallel_up():
    bs = [_bucket(bucket="5Y",
                  rate_sensitive_assets_kes=Decimal("1000000000"),
                  rate_sensitive_liabilities_kes=Decimal("500000000"))]
    r = IrrbbEngine.eve_sensitivity(bs, "PARALLEL_UP", Decimal("100000000"))
    eve_change = Decimal(r["eve_change_kes"])
    # Positive net position + up shock = negative EVE impact
    assert eve_change < 0


def _test_eve_unknown_scenario():
    bs = [_bucket()]
    r = IrrbbEngine.eve_sensitivity(bs, "WEIRD", Decimal("100000000"))
    assert "error" in r


def _test_eve_no_capital_rule1():
    bs = [_bucket()]
    r = IrrbbEngine.eve_sensitivity(bs, "PARALLEL_UP", None)
    assert r["outlier_pct"] is None


def _test_eve_outlier():
    """Massive duration mismatch → EVE outlier."""
    bs = [_bucket(bucket="10Y_PLUS",
                  rate_sensitive_assets_kes=Decimal("10000000000"),
                  rate_sensitive_liabilities_kes=Decimal("0"))]
    r = IrrbbEngine.eve_sensitivity(bs, "PARALLEL_UP", Decimal("100000000"))
    assert r["is_outlier"] is True


def _test_buckets_byte_for_byte():
    expected = ("ON_DEMAND", "1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "10Y_PLUS")
    for b in expected:
        assert b in REPRICING_BUCKETS


def _test_shock_scenarios_byte_for_byte():
    assert SHOCK_SCENARIOS["PARALLEL_UP"]["all"] == 200
    assert SHOCK_SCENARIOS["PARALLEL_DOWN"]["all"] == -200
    assert SHOCK_SCENARIOS["STEEPENER"]["short"] == -65
    assert SHOCK_SCENARIOS["STEEPENER"]["long"] == 90


def _test_outlier_thresholds_byte_for_byte():
    assert EVE_OUTLIER_THRESHOLD_PCT == Decimal("15")
    assert NII_OUTLIER_THRESHOLD_PCT == Decimal("5")


def _test_all_scenarios_summary():
    bs = [_bucket(bucket="5Y",
                  rate_sensitive_assets_kes=Decimal("1000000000"),
                  rate_sensitive_liabilities_kes=Decimal("500000000"))]
    inputs = IrrbbInputs(buckets=bs, tier_1_capital_kes=Decimal("100000000"))
    r = IrrbbEngine.all_scenarios_summary(inputs)
    assert len(r["eve_scenarios"]) == len(VALID_SCENARIOS)
    assert r["worst_eve_scenario"] is not None


def self_test() -> bool:
    tests = [
        _test_repricing_gap_basic,
        _test_repricing_gap_excluded_rule6,
        _test_repricing_gap_unknown_bucket,
        _test_nii_sensitivity_up_shock,
        _test_nii_outlier,
        _test_nii_no_capital_rule1,
        _test_eve_parallel_up,
        _test_eve_unknown_scenario,
        _test_eve_no_capital_rule1,
        _test_eve_outlier,
        _test_buckets_byte_for_byte,
        _test_shock_scenarios_byte_for_byte,
        _test_outlier_thresholds_byte_for_byte,
        _test_all_scenarios_summary,
    ]
    print("=" * 60)
    print("IRRBB Engine — Self-Tests (#74)")
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

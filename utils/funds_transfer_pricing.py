"""
================================================================================
A2Z MIS 360 — Standard #89: Funds Transfer Pricing (FTP) Engine
================================================================================

Risk classification: Cat B (deterministic FTP rate computation)

Internal funds transfer pricing for asset and liability product profitability:
    - matched_maturity_ftp_rate(...)        -- MMFTP curve interpolation
    - single_pool_ftp_rate(...)             -- weighted-average pool method
    - liquidity_premium(...)                -- liquidity premium add-on
    - net_interest_margin_split(...)        -- split spread into lending/funding
    - product_ftp_assignment(...)           -- assign FTP to product

2 FTP_METHODOLOGIES byte-for-byte: SINGLE_POOL, MATCHED_MATURITY

11 FTP_CURVE_TENORS_MONTHS byte-for-byte: 1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360

5 LIQUIDITY_PREMIUM_TIERS byte-for-byte (basis points):
    SHORT_TERM (<=12mo)         : 10 bps
    MEDIUM_TERM (13-60mo)       : 25 bps
    LONG_TERM (61-120mo)        : 50 bps
    VERY_LONG_TERM (121-240mo)  : 100 bps
    EXTRA_LONG_TERM (>240mo)    : 150 bps

Honesty rules applied:
    Rule 1: ftp_rate=None when curve missing or zero principal
    Rule 6: missing tenor → result=None with explanation surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 2 FTP METHODOLOGIES byte-for-byte
FTP_METHODOLOGIES: Tuple[str, ...] = ("SINGLE_POOL", "MATCHED_MATURITY")

# 11 FTP CURVE TENORS (months) byte-for-byte
FTP_CURVE_TENORS_MONTHS: Tuple[int, ...] = (
    1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360,
)

# 5 LIQUIDITY PREMIUM TIERS byte-for-byte (basis points)
LIQUIDITY_PREMIUM_TIERS_BPS: Dict[str, int] = {
    "SHORT_TERM": 10,
    "MEDIUM_TERM": 25,
    "LONG_TERM": 50,
    "VERY_LONG_TERM": 100,
    "EXTRA_LONG_TERM": 150,
}

# Tenor band thresholds (months)
LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS: Dict[str, Tuple[int, int]] = {
    "SHORT_TERM": (0, 12),
    "MEDIUM_TERM": (13, 60),
    "LONG_TERM": (61, 120),
    "VERY_LONG_TERM": (121, 240),
    "EXTRA_LONG_TERM": (241, 9999),
}


@dataclass
class FtpCurvePoint:
    tenor_months: int
    rate_pct: Decimal


class FtpEngine:
    """Deterministic Funds Transfer Pricing engine."""

    @staticmethod
    def matched_maturity_ftp_rate(
        tenor_months: Optional[int],
        curve: List[FtpCurvePoint],
    ) -> Dict[str, Any]:
        """
        Linear interpolation on the FTP curve for a given tenor.
        Rule 1: rate=None when curve empty or tenor missing.
        """
        if tenor_months is None:
            return {"ftp_rate_pct": None, "reason": "missing_tenor"}
        if not curve:
            return {"ftp_rate_pct": None, "reason": "empty_curve"}

        # Sort curve by tenor
        sorted_curve = sorted(curve, key=lambda p: p.tenor_months)
        tenors = [p.tenor_months for p in sorted_curve]
        rates = [p.rate_pct for p in sorted_curve]

        # Exact match
        if tenor_months in tenors:
            idx = tenors.index(tenor_months)
            return {
                "ftp_rate_pct": str(rates[idx].quantize(Decimal("0.0001"))),
                "method": "exact_match",
                "tenor_months": tenor_months,
            }

        # Below shortest tenor → use shortest
        if tenor_months < tenors[0]:
            return {
                "ftp_rate_pct": str(rates[0].quantize(Decimal("0.0001"))),
                "method": "below_shortest_curve_point",
                "tenor_months": tenor_months,
                "curve_point_used": tenors[0],
            }
        # Above longest tenor → use longest
        if tenor_months > tenors[-1]:
            return {
                "ftp_rate_pct": str(rates[-1].quantize(Decimal("0.0001"))),
                "method": "above_longest_curve_point",
                "tenor_months": tenor_months,
                "curve_point_used": tenors[-1],
            }

        # Linear interpolation
        for i in range(len(tenors) - 1):
            if tenors[i] < tenor_months < tenors[i+1]:
                t1, t2 = Decimal(tenors[i]), Decimal(tenors[i+1])
                r1, r2 = rates[i], rates[i+1]
                t = Decimal(tenor_months)
                interpolated = r1 + (r2 - r1) * (t - t1) / (t2 - t1)
                return {
                    "ftp_rate_pct": str(interpolated.quantize(Decimal("0.0001"))),
                    "method": "linear_interpolation",
                    "tenor_months": tenor_months,
                    "between_points": (tenors[i], tenors[i+1]),
                }
        # shouldn't reach
        return {"ftp_rate_pct": None, "reason": "interpolation_failed"}

    @staticmethod
    def single_pool_ftp_rate(
        pool_balances_kes: List[Decimal],
        pool_rates_pct: List[Decimal],
    ) -> Dict[str, Any]:
        """
        Weighted-average rate across a pool of balances.
        Rule 1: rate=None when total balance is zero or inputs mismatched.
        """
        if not pool_balances_kes or not pool_rates_pct:
            return {"ftp_rate_pct": None, "reason": "empty_pool"}
        if len(pool_balances_kes) != len(pool_rates_pct):
            return {"ftp_rate_pct": None, "reason": "mismatched_lengths"}
        total_balance = sum(pool_balances_kes)
        if total_balance <= 0:
            return {"ftp_rate_pct": None, "reason": "zero_total_balance"}
        weighted_sum = sum(b * r for b, r in zip(pool_balances_kes, pool_rates_pct))
        wavg = weighted_sum / total_balance
        return {
            "ftp_rate_pct": str(wavg.quantize(Decimal("0.0001"))),
            "method": "weighted_average",
            "total_balance_kes": str(total_balance),
            "pool_size": len(pool_balances_kes),
        }

    @staticmethod
    def liquidity_premium(tenor_months: Optional[int]) -> Dict[str, Any]:
        """
        Return liquidity premium add-on in bps for a given tenor.
        Rule 1: bps=None when tenor missing.
        """
        if tenor_months is None:
            return {"liquidity_premium_bps": None, "reason": "missing_tenor"}
        for tier_name, (lo, hi) in LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS.items():
            if lo <= tenor_months <= hi:
                return {
                    "tenor_months": tenor_months,
                    "tier": tier_name,
                    "liquidity_premium_bps": LIQUIDITY_PREMIUM_TIERS_BPS[tier_name],
                }
        return {"liquidity_premium_bps": None, "reason": "tenor_out_of_bands"}

    @staticmethod
    def net_interest_margin_split(
        customer_rate_pct: Optional[Decimal],
        ftp_rate_pct: Optional[Decimal],
        is_asset: bool,
    ) -> Dict[str, Any]:
        """
        Split product NIM into lending and funding spreads using FTP rate as
        the transfer price.
        For ASSET: lending_spread = customer_rate - ftp_rate
        For LIABILITY: funding_spread = ftp_rate - customer_rate
        Rule 1: spread=None when either rate missing.
        """
        if customer_rate_pct is None or ftp_rate_pct is None:
            return {"spread_pct": None, "reason": "missing_rate"}
        if is_asset:
            spread = customer_rate_pct - ftp_rate_pct
            label = "lending_spread_pct"
        else:
            spread = ftp_rate_pct - customer_rate_pct
            label = "funding_spread_pct"
        return {
            label: str(spread.quantize(Decimal("0.0001"))),
            "is_asset": is_asset,
            "customer_rate_pct": str(customer_rate_pct.quantize(Decimal("0.0001"))),
            "ftp_rate_pct": str(ftp_rate_pct.quantize(Decimal("0.0001"))),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _curve():
    return [
        FtpCurvePoint(tenor_months=t, rate_pct=Decimal(r))
        for t, r in [(1, "8.0"), (3, "8.5"), (6, "9.0"), (12, "9.5"),
                     (24, "10.0"), (36, "10.5"), (60, "11.0"), (120, "12.0")]
    ]


def _test_methodologies_byte_for_byte():
    assert "SINGLE_POOL" in FTP_METHODOLOGIES
    assert "MATCHED_MATURITY" in FTP_METHODOLOGIES
    assert len(FTP_METHODOLOGIES) == 2


def _test_curve_tenors_byte_for_byte():
    expected = (1, 3, 6, 12, 24, 36, 60, 84, 120, 240, 360)
    for t in expected:
        assert t in FTP_CURVE_TENORS_MONTHS
    assert len(FTP_CURVE_TENORS_MONTHS) == 11


def _test_liquidity_premium_tiers_byte_for_byte():
    assert LIQUIDITY_PREMIUM_TIERS_BPS["SHORT_TERM"] == 10
    assert LIQUIDITY_PREMIUM_TIERS_BPS["MEDIUM_TERM"] == 25
    assert LIQUIDITY_PREMIUM_TIERS_BPS["LONG_TERM"] == 50
    assert LIQUIDITY_PREMIUM_TIERS_BPS["VERY_LONG_TERM"] == 100
    assert LIQUIDITY_PREMIUM_TIERS_BPS["EXTRA_LONG_TERM"] == 150


def _test_liquidity_premium_bands_byte_for_byte():
    assert LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS["SHORT_TERM"] == (0, 12)
    assert LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS["MEDIUM_TERM"] == (13, 60)
    assert LIQUIDITY_PREMIUM_TIER_BANDS_MONTHS["LONG_TERM"] == (61, 120)


def _test_mmftp_exact_match():
    r = FtpEngine.matched_maturity_ftp_rate(12, _curve())
    assert r["ftp_rate_pct"] == "9.5000"
    assert r["method"] == "exact_match"


def _test_mmftp_interpolation():
    """Tenor 18 months: between 12 (9.5%) and 24 (10.0%) → 9.75%."""
    r = FtpEngine.matched_maturity_ftp_rate(18, _curve())
    assert r["ftp_rate_pct"] == "9.7500"
    assert r["method"] == "linear_interpolation"


def _test_mmftp_below_shortest():
    r = FtpEngine.matched_maturity_ftp_rate(0, _curve())
    assert r["method"] == "below_shortest_curve_point"


def _test_mmftp_above_longest():
    r = FtpEngine.matched_maturity_ftp_rate(360, _curve())
    assert r["method"] == "above_longest_curve_point"


def _test_mmftp_empty_curve_rule1():
    r = FtpEngine.matched_maturity_ftp_rate(12, [])
    assert r["ftp_rate_pct"] is None


def _test_mmftp_missing_tenor_rule1():
    r = FtpEngine.matched_maturity_ftp_rate(None, _curve())
    assert r["ftp_rate_pct"] is None


def _test_single_pool_weighted():
    """50M @ 8% + 50M @ 12% → 10% weighted average."""
    r = FtpEngine.single_pool_ftp_rate(
        [Decimal("50000000"), Decimal("50000000")],
        [Decimal("8.0"), Decimal("12.0")],
    )
    assert r["ftp_rate_pct"] == "10.0000"


def _test_single_pool_zero_balance_rule1():
    r = FtpEngine.single_pool_ftp_rate(
        [Decimal("0")], [Decimal("10.0")])
    assert r["ftp_rate_pct"] is None


def _test_single_pool_mismatched_rule1():
    r = FtpEngine.single_pool_ftp_rate(
        [Decimal("100")], [Decimal("8.0"), Decimal("9.0")])
    assert r["ftp_rate_pct"] is None


def _test_liquidity_premium_short():
    r = FtpEngine.liquidity_premium(6)
    assert r["liquidity_premium_bps"] == 10
    assert r["tier"] == "SHORT_TERM"


def _test_liquidity_premium_long():
    r = FtpEngine.liquidity_premium(84)
    assert r["liquidity_premium_bps"] == 50
    assert r["tier"] == "LONG_TERM"


def _test_liquidity_premium_extra_long():
    r = FtpEngine.liquidity_premium(360)
    assert r["liquidity_premium_bps"] == 150


def _test_liquidity_premium_missing_rule1():
    r = FtpEngine.liquidity_premium(None)
    assert r["liquidity_premium_bps"] is None


def _test_nim_split_asset():
    """Loan @ 14% with FTP 9% → lending spread = 5%."""
    r = FtpEngine.net_interest_margin_split(
        Decimal("14.0"), Decimal("9.0"), is_asset=True)
    assert r["lending_spread_pct"] == "5.0000"


def _test_nim_split_liability():
    """Deposit @ 5% with FTP 9% → funding spread = 4%."""
    r = FtpEngine.net_interest_margin_split(
        Decimal("5.0"), Decimal("9.0"), is_asset=False)
    assert r["funding_spread_pct"] == "4.0000"


def _test_nim_split_missing_rule1():
    r = FtpEngine.net_interest_margin_split(None, Decimal("9.0"), is_asset=True)
    assert r["spread_pct"] is None


def self_test() -> bool:
    tests = [
        _test_methodologies_byte_for_byte,
        _test_curve_tenors_byte_for_byte,
        _test_liquidity_premium_tiers_byte_for_byte,
        _test_liquidity_premium_bands_byte_for_byte,
        _test_mmftp_exact_match,
        _test_mmftp_interpolation,
        _test_mmftp_below_shortest,
        _test_mmftp_above_longest,
        _test_mmftp_empty_curve_rule1,
        _test_mmftp_missing_tenor_rule1,
        _test_single_pool_weighted,
        _test_single_pool_zero_balance_rule1,
        _test_single_pool_mismatched_rule1,
        _test_liquidity_premium_short,
        _test_liquidity_premium_long,
        _test_liquidity_premium_extra_long,
        _test_liquidity_premium_missing_rule1,
        _test_nim_split_asset,
        _test_nim_split_liability,
        _test_nim_split_missing_rule1,
    ]
    print("=" * 60)
    print("Funds Transfer Pricing Engine — Self-Tests (#89)")
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

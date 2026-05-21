"""
================================================================================
A2Z MIS 360 — Standard #75: FX Position Monitoring Engine
================================================================================

Risk classification: Cat B (deterministic CBK regulatory FX position monitoring)

Computes FX position metrics per CBK Banking Act + Prudential Guideline:
    - net_open_position_per_currency(...)   -- FX assets minus FX liabilities
    - aggregate_net_open_position(...)      -- shorthand or sum-of-absolute method
    - fx_exposure_limit_check(...)          -- vs CBK 10% core capital limit
    - fx_pnl_attribution(...)               -- FX gains/losses by currency

CBK Banking Act / CBK Prudential Guideline CBK/PG/03 limits:
    Single currency limit       : <= 10% of core capital per currency
    Aggregate FX position limit : <= 20% of core capital (overall)
    Reporting frequency         : Daily for trading book; weekly otherwise

Aggregate position methods (Basel II/III standardised):
    SHORTHAND_METHOD : max(sum_long, sum_short)
    SUM_ABSOLUTE     : sum of absolute values (more conservative)

Major currencies tracked (Kenya banking context):
    USD, EUR, GBP, JPY, CHF, CNY, INR, ZAR, UGX, TZS, RWF, ETB

Honesty rules applied:
    Rule 1: limit_pct = None when core_capital <= 0
    Rule 6: positions with missing balance excluded with count surfaced;
            unknown currency codes surfaced as `unknown_currencies[]`

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# ISO 4217 currency codes — major currencies for Kenyan banking
SUPPORTED_CURRENCIES: Tuple[str, ...] = (
    "USD", "EUR", "GBP", "JPY", "CHF", "CNY", "INR", "ZAR",
    "UGX", "TZS", "RWF", "ETB", "AED", "ZMW",
)

# CBK regulatory limits (% of core capital)
SINGLE_CURRENCY_LIMIT_PCT = Decimal("10")
AGGREGATE_FX_LIMIT_PCT = Decimal("20")

# Aggregation methods
AGGREGATION_METHODS: Tuple[str, ...] = ("SHORTHAND_METHOD", "SUM_ABSOLUTE")


@dataclass
class FxPosition:
    position_id: str
    currency: str  # ISO 4217 code
    fx_assets_kes_equivalent: Optional[Decimal] = None      # KES-equivalent of FX assets
    fx_liabilities_kes_equivalent: Optional[Decimal] = None  # KES-equivalent of FX liabilities
    spot_rate_to_kes: Optional[Decimal] = None  # for context


class FxPositionMonitoringEngine:
    """Deterministic FX position computation per CBK PG/03."""

    @staticmethod
    def net_open_position_per_currency(positions: List[FxPosition]) -> Dict[str, Any]:
        """
        Net open position = FX_assets - FX_liabilities per currency.
        Positive = LONG, Negative = SHORT.
        Rule 6: positions with missing values excluded.
        """
        by_ccy: Dict[str, Dict[str, Decimal]] = {}
        excluded = []
        unknown_ccy = []
        for p in positions:
            if p.currency not in SUPPORTED_CURRENCIES:
                unknown_ccy.append(p.currency)
                continue
            if (p.fx_assets_kes_equivalent is None
                    or p.fx_liabilities_kes_equivalent is None):
                excluded.append(p.position_id)
                continue
            if p.currency not in by_ccy:
                by_ccy[p.currency] = {"assets": Decimal("0"), "liabilities": Decimal("0")}
            by_ccy[p.currency]["assets"] += p.fx_assets_kes_equivalent
            by_ccy[p.currency]["liabilities"] += p.fx_liabilities_kes_equivalent

        results = []
        for ccy, totals in sorted(by_ccy.items()):
            net = totals["assets"] - totals["liabilities"]
            position_type = "LONG" if net > 0 else ("SHORT" if net < 0 else "FLAT")
            results.append({
                "currency": ccy,
                "fx_assets_kes": str(totals["assets"].quantize(Decimal("0.01"))),
                "fx_liabilities_kes": str(totals["liabilities"].quantize(Decimal("0.01"))),
                "net_open_position_kes": str(net.quantize(Decimal("0.01"))),
                "position_type": position_type,
            })
        return {
            "currency_count": len(results),
            "positions": results,
            "excluded_count": len(excluded),
            "unknown_currencies": list(set(unknown_ccy)),
        }

    @staticmethod
    def aggregate_net_open_position(
        positions: List[FxPosition],
        method: str = "SHORTHAND_METHOD",
    ) -> Dict[str, Any]:
        """
        Aggregate FX position across currencies.
        SHORTHAND_METHOD: max(sum_long, sum_short)  [Basel standardised]
        SUM_ABSOLUTE:    sum_long + sum_short      [more conservative]
        """
        if method not in AGGREGATION_METHODS:
            return {"error": f"unknown_method:{method}", "valid_methods": list(AGGREGATION_METHODS)}

        per_ccy = FxPositionMonitoringEngine.net_open_position_per_currency(positions)
        sum_long = Decimal("0")
        sum_short = Decimal("0")
        for p in per_ccy["positions"]:
            net = Decimal(p["net_open_position_kes"])
            if net > 0:
                sum_long += net
            elif net < 0:
                sum_short += abs(net)

        if method == "SHORTHAND_METHOD":
            aggregate = max(sum_long, sum_short)
        else:  # SUM_ABSOLUTE
            aggregate = sum_long + sum_short

        return {
            "method": method,
            "sum_long_kes": str(sum_long.quantize(Decimal("0.01"))),
            "sum_short_kes": str(sum_short.quantize(Decimal("0.01"))),
            "aggregate_net_open_position_kes": str(aggregate.quantize(Decimal("0.01"))),
            "currency_count": per_ccy["currency_count"],
        }

    @classmethod
    def fx_exposure_limit_check(
        cls,
        positions: List[FxPosition],
        core_capital_kes: Optional[Decimal],
        method: str = "SHORTHAND_METHOD",
    ) -> Dict[str, Any]:
        """
        Check single-currency and aggregate FX positions against CBK limits.
        Rule 1: ratios=None when core_capital<=0.
        """
        per_ccy = cls.net_open_position_per_currency(positions)
        agg = cls.aggregate_net_open_position(positions, method)

        if core_capital_kes is None or core_capital_kes <= 0:
            return {
                "single_currency_limit_pct": str(SINGLE_CURRENCY_LIMIT_PCT),
                "aggregate_limit_pct": str(AGGREGATE_FX_LIMIT_PCT),
                "single_currency_breaches": [],
                "aggregate_breach": None,
                "core_capital_kes": str(core_capital_kes) if core_capital_kes else None,
                "reason": "core_capital_zero_or_negative",
                "per_currency": per_ccy,
                "aggregate": agg,
            }

        # Single currency check
        breaches = []
        per_ccy_with_pct = []
        for p in per_ccy["positions"]:
            net = Decimal(p["net_open_position_kes"])
            pct = abs(net) / core_capital_kes * Decimal("100")
            entry = {
                **p,
                "limit_pct": str(pct.quantize(Decimal("0.01"))),
                "breach": pct > SINGLE_CURRENCY_LIMIT_PCT,
            }
            per_ccy_with_pct.append(entry)
            if pct > SINGLE_CURRENCY_LIMIT_PCT:
                breaches.append(entry)

        # Aggregate check
        agg_amt = Decimal(agg["aggregate_net_open_position_kes"])
        agg_pct = agg_amt / core_capital_kes * Decimal("100")
        agg_breach = agg_pct > AGGREGATE_FX_LIMIT_PCT

        # Status
        if breaches or agg_breach:
            status = "RED"
        elif agg_pct >= AGGREGATE_FX_LIMIT_PCT * Decimal("0.8"):
            status = "AMBER"  # within 20% of limit
        else:
            status = "GREEN"

        return {
            "core_capital_kes": str(core_capital_kes.quantize(Decimal("0.01"))),
            "single_currency_limit_pct": str(SINGLE_CURRENCY_LIMIT_PCT),
            "aggregate_limit_pct": str(AGGREGATE_FX_LIMIT_PCT),
            "single_currency_breaches": breaches,
            "aggregate_pct": str(agg_pct.quantize(Decimal("0.01"))),
            "aggregate_breach": agg_breach,
            "status": status,
            "per_currency": per_ccy_with_pct,
            "method": method,
            "aggregate_amount_kes": str(agg_amt.quantize(Decimal("0.01"))),
        }

    @staticmethod
    def fx_pnl_attribution(
        positions: List[FxPosition],
        prior_rates_to_kes: Dict[str, Decimal],
    ) -> Dict[str, Any]:
        """
        Attribute FX P&L by currency (mark-to-market move).
        Returns gains/losses per currency since prior rate.
        """
        results = []
        excluded = []
        for p in positions:
            if p.currency not in SUPPORTED_CURRENCIES:
                excluded.append(p.position_id)
                continue
            if (p.fx_assets_kes_equivalent is None
                    or p.fx_liabilities_kes_equivalent is None
                    or p.spot_rate_to_kes is None):
                excluded.append(p.position_id)
                continue
            prior_rate = prior_rates_to_kes.get(p.currency)
            if prior_rate is None or prior_rate <= 0:
                excluded.append(p.position_id)
                continue
            net = p.fx_assets_kes_equivalent - p.fx_liabilities_kes_equivalent
            # Convert net back to FX
            fx_amount = net / p.spot_rate_to_kes
            # Recompute net at prior rate
            old_net = fx_amount * prior_rate
            pnl = net - old_net
            results.append({
                "currency": p.currency,
                "current_rate": str(p.spot_rate_to_kes),
                "prior_rate": str(prior_rate),
                "net_position_kes": str(net.quantize(Decimal("0.01"))),
                "pnl_kes": str(pnl.quantize(Decimal("0.01"))),
            })
        total_pnl = sum(Decimal(r["pnl_kes"]) for r in results)
        return {
            "total_pnl_kes": str(total_pnl.quantize(Decimal("0.01"))),
            "by_currency": results,
            "excluded_count": len(excluded),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _pos(**kw):
    defaults = dict(position_id="P1", currency="USD",
                    fx_assets_kes_equivalent=Decimal("100000000"),
                    fx_liabilities_kes_equivalent=Decimal("80000000"),
                    spot_rate_to_kes=Decimal("130"))
    defaults.update(kw)
    return FxPosition(**defaults)


def _test_net_position_long():
    r = FxPositionMonitoringEngine.net_open_position_per_currency([_pos()])
    assert r["positions"][0]["position_type"] == "LONG"
    assert r["positions"][0]["net_open_position_kes"] == "20000000.00"


def _test_net_position_short():
    p = _pos(fx_assets_kes_equivalent=Decimal("50000000"),
             fx_liabilities_kes_equivalent=Decimal("100000000"))
    r = FxPositionMonitoringEngine.net_open_position_per_currency([p])
    assert r["positions"][0]["position_type"] == "SHORT"


def _test_unknown_currency_surfaced_rule6():
    p = _pos(currency="XYZ")
    r = FxPositionMonitoringEngine.net_open_position_per_currency([p])
    assert "XYZ" in r["unknown_currencies"]


def _test_excluded_missing_value_rule6():
    p = _pos(fx_assets_kes_equivalent=None)
    r = FxPositionMonitoringEngine.net_open_position_per_currency([p])
    assert r["excluded_count"] == 1


def _test_aggregate_shorthand():
    """USD long 20M, EUR short 30M → shorthand = 30M."""
    positions = [
        _pos(position_id="P1", currency="USD",
             fx_assets_kes_equivalent=Decimal("100000000"),
             fx_liabilities_kes_equivalent=Decimal("80000000")),  # +20M
        _pos(position_id="P2", currency="EUR",
             fx_assets_kes_equivalent=Decimal("50000000"),
             fx_liabilities_kes_equivalent=Decimal("80000000")),  # -30M
    ]
    r = FxPositionMonitoringEngine.aggregate_net_open_position(positions)
    assert r["aggregate_net_open_position_kes"] == "30000000.00"


def _test_aggregate_sum_absolute():
    """USD long 20M, EUR short 30M → sum_absolute = 50M."""
    positions = [
        _pos(position_id="P1", currency="USD",
             fx_assets_kes_equivalent=Decimal("100000000"),
             fx_liabilities_kes_equivalent=Decimal("80000000")),
        _pos(position_id="P2", currency="EUR",
             fx_assets_kes_equivalent=Decimal("50000000"),
             fx_liabilities_kes_equivalent=Decimal("80000000")),
    ]
    r = FxPositionMonitoringEngine.aggregate_net_open_position(positions, "SUM_ABSOLUTE")
    assert r["aggregate_net_open_position_kes"] == "50000000.00"


def _test_aggregate_unknown_method():
    r = FxPositionMonitoringEngine.aggregate_net_open_position([_pos()], "WEIRD")
    assert "error" in r


def _test_limit_check_compliant():
    # Core capital 1B, USD position 20M = 2% < 10%
    r = FxPositionMonitoringEngine.fx_exposure_limit_check(
        [_pos()], Decimal("1000000000")
    )
    assert r["status"] == "GREEN"
    assert len(r["single_currency_breaches"]) == 0


def _test_limit_check_single_currency_breach():
    # Core capital 100M, USD position 20M = 20% > 10%
    p = _pos(fx_assets_kes_equivalent=Decimal("30000000"),
             fx_liabilities_kes_equivalent=Decimal("0"))
    r = FxPositionMonitoringEngine.fx_exposure_limit_check(
        [p], Decimal("100000000")
    )
    assert r["status"] == "RED"
    assert len(r["single_currency_breaches"]) == 1


def _test_limit_check_aggregate_breach():
    # Core capital 100M; long 15M + short 15M → shorthand = 15M = 15% > aggregate 20%? No, 15% < 20%.
    # Need bigger: long 25M (25%) → single + aggregate breach
    p = _pos(fx_assets_kes_equivalent=Decimal("25000000"),
             fx_liabilities_kes_equivalent=Decimal("0"))
    r = FxPositionMonitoringEngine.fx_exposure_limit_check(
        [p], Decimal("100000000")
    )
    assert r["aggregate_breach"] is True


def _test_limit_check_no_capital_rule1():
    r = FxPositionMonitoringEngine.fx_exposure_limit_check([_pos()], None)
    assert r.get("aggregate_pct") is None
    assert r.get("aggregate_breach") is None


def _test_limits_byte_for_byte():
    assert SINGLE_CURRENCY_LIMIT_PCT == Decimal("10")
    assert AGGREGATE_FX_LIMIT_PCT == Decimal("20")


def _test_currencies_byte_for_byte():
    for ccy in ("USD", "EUR", "GBP", "JPY", "UGX", "TZS"):
        assert ccy in SUPPORTED_CURRENCIES


def _test_methods_byte_for_byte():
    assert "SHORTHAND_METHOD" in AGGREGATION_METHODS
    assert "SUM_ABSOLUTE" in AGGREGATION_METHODS


def _test_pnl_attribution():
    p = _pos(fx_assets_kes_equivalent=Decimal("130000000"),
             fx_liabilities_kes_equivalent=Decimal("0"),
             spot_rate_to_kes=Decimal("130"))
    # 1M USD long. Prior rate 125 → old position = 125M. PnL = 130M - 125M = 5M
    r = FxPositionMonitoringEngine.fx_pnl_attribution(
        [p], {"USD": Decimal("125")}
    )
    assert Decimal(r["total_pnl_kes"]) == Decimal("5000000.00")


def self_test() -> bool:
    tests = [
        _test_net_position_long,
        _test_net_position_short,
        _test_unknown_currency_surfaced_rule6,
        _test_excluded_missing_value_rule6,
        _test_aggregate_shorthand,
        _test_aggregate_sum_absolute,
        _test_aggregate_unknown_method,
        _test_limit_check_compliant,
        _test_limit_check_single_currency_breach,
        _test_limit_check_aggregate_breach,
        _test_limit_check_no_capital_rule1,
        _test_limits_byte_for_byte,
        _test_currencies_byte_for_byte,
        _test_methods_byte_for_byte,
        _test_pnl_attribution,
    ]
    print("=" * 60)
    print("FX Position Monitoring Engine — Self-Tests (#75)")
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

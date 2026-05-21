"""
================================================================================
A2Z MIS 360 — Standard #76: Investment Portfolio Analytics Engine
================================================================================

Risk classification: Cat B (deterministic fixed income analytics)

Computes investment portfolio metrics:
    - portfolio_market_value(holdings)        -- mark-to-market
    - bond_modified_duration(...)             -- Macaulay/Modified duration per bond
    - portfolio_weighted_duration(...)        -- value-weighted portfolio duration
    - yield_to_maturity(...)                  -- YTM via Newton-Raphson
    - hqla_classification(holdings)           -- Basel III LCR Level 1/2A/2B
    - concentration_risk(...)                 -- single-name + sector limits

Bond mathematics (deterministic):
    Macaulay Duration  = sum(t × CF_t / (1+y)^t) / PV
    Modified Duration  = Macaulay / (1 + y/k) where k = compounding frequency
    Convexity          = sum(t² × CF_t / (1+y)^t) / PV
    YTM                = solve P = sum(CF_t / (1+YTM)^t) for YTM via Newton-Raphson

HQLA classification per Basel III LCR:
    LEVEL_1   : Sovereign govt securities (0% risk weight) — 0% haircut
    LEVEL_2A  : 20% risk-weighted sovereign/PSE — 15% haircut
    LEVEL_2B  : Corporate debt rated >= BBB- — 50% haircut
    NON_HQLA  : Below investment grade or equity — does not count

Concentration limits (CBK Banking Act PG/04):
    Single counterparty issuer    : <= 25% of core capital
    Single sector concentration    : <= 35% of investment book

Honesty rules applied:
    Rule 1: YTM = None when Newton-Raphson fails to converge or PV<=0
    Rule 6: holdings with missing market price/coupon/maturity excluded with count surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Investment instrument types
INSTRUMENT_TYPES: Tuple[str, ...] = (
    "GOVERNMENT_BOND",
    "TREASURY_BILL",
    "CORPORATE_BOND",
    "MUNICIPAL_BOND",
    "EQUITY",
    "MUTUAL_FUND",
    "STRUCTURED_NOTE",
)

# HQLA classifications (Basel III)
HQLA_CLASS: Tuple[str, ...] = ("LEVEL_1", "LEVEL_2A", "LEVEL_2B", "NON_HQLA")

# Credit rating to HQLA mapping
RATING_TO_HQLA_LEVEL: Dict[str, str] = {
    # Sovereigns (any of these = LEVEL_1)
    "AAA": "LEVEL_1",
    "AA+": "LEVEL_1",
    "AA": "LEVEL_1",
    "AA-": "LEVEL_1",
    "A+": "LEVEL_2A",
    "A": "LEVEL_2A",
    "A-": "LEVEL_2A",
    "BBB+": "LEVEL_2B",
    "BBB": "LEVEL_2B",
    "BBB-": "LEVEL_2B",
}

# Concentration limits (CBK PG/04)
SINGLE_ISSUER_LIMIT_PCT = Decimal("25")    # of core capital
SINGLE_SECTOR_LIMIT_PCT = Decimal("35")    # of investment book

# YTM solver parameters
YTM_MAX_ITERATIONS = 100
YTM_TOLERANCE = Decimal("0.0001")


@dataclass
class BondHolding:
    holding_id: str
    instrument_type: str
    issuer: str
    sector: str  # SOVEREIGN / FINANCIAL / INDUSTRIAL / etc.
    par_value_kes: Optional[Decimal] = None
    market_price_pct: Optional[Decimal] = None  # % of par (e.g. 98.5)
    coupon_rate_pct: Optional[Decimal] = None
    coupon_frequency_per_year: int = 2  # semi-annual default
    maturity_date: Optional[date] = None
    settlement_date: Optional[date] = None
    credit_rating: Optional[str] = None
    is_sovereign: bool = False


def _years_to_maturity(holding: BondHolding) -> Optional[Decimal]:
    if holding.maturity_date is None or holding.settlement_date is None:
        return None
    days = (holding.maturity_date - holding.settlement_date).days
    if days <= 0:
        return Decimal("0")
    return Decimal(days) / Decimal("365")


def _market_value_kes(holding: BondHolding) -> Optional[Decimal]:
    if holding.par_value_kes is None or holding.market_price_pct is None:
        return None
    return holding.par_value_kes * holding.market_price_pct / Decimal("100")


class InvestmentPortfolioEngine:
    """Deterministic fixed income analytics."""

    @staticmethod
    def portfolio_market_value(holdings: List[BondHolding]) -> Dict[str, Any]:
        """Mark-to-market portfolio value. Rule 6: missing prices excluded."""
        total = Decimal("0")
        excluded = []
        results = []
        for h in holdings:
            mv = _market_value_kes(h)
            if mv is None:
                excluded.append(h.holding_id)
                continue
            total += mv
            results.append({
                "holding_id": h.holding_id,
                "issuer": h.issuer,
                "instrument_type": h.instrument_type,
                "market_value_kes": str(mv.quantize(Decimal("0.01"))),
            })
        return {
            "total_market_value_kes": str(total.quantize(Decimal("0.01"))),
            "holding_count": len(results),
            "excluded_count": len(excluded),
            "holdings": results,
        }

    @staticmethod
    def bond_modified_duration(holding: BondHolding, ytm_pct: Decimal) -> Dict[str, Any]:
        """
        Macaulay & Modified Duration of one bond.
        Rule 6: missing data → returns reason.
        """
        if (holding.par_value_kes is None or holding.coupon_rate_pct is None
                or holding.market_price_pct is None
                or holding.maturity_date is None or holding.settlement_date is None):
            return {
                "holding_id": holding.holding_id,
                "macaulay_duration": None,
                "modified_duration": None,
                "reason": "missing_required_fields",
            }

        years = _years_to_maturity(holding)
        if years is None or years <= 0:
            return {
                "holding_id": holding.holding_id,
                "macaulay_duration": None,
                "modified_duration": None,
                "reason": "matured_or_invalid_dates",
            }

        freq = Decimal(holding.coupon_frequency_per_year)
        n_periods = int(years * freq)
        if n_periods < 1:
            n_periods = 1
        coupon_cf = (holding.par_value_kes * holding.coupon_rate_pct / Decimal("100")) / freq
        period_yield = ytm_pct / Decimal("100") / freq
        pv = Decimal("0")
        weighted_t = Decimal("0")
        for t in range(1, n_periods + 1):
            cf = coupon_cf
            if t == n_periods:
                cf += holding.par_value_kes  # principal back at maturity
            disc = (Decimal("1") + period_yield) ** t
            pv_cf = cf / disc
            pv += pv_cf
            weighted_t += Decimal(t) * pv_cf
        if pv <= 0:
            return {
                "holding_id": holding.holding_id,
                "macaulay_duration": None,
                "modified_duration": None,
                "reason": "pv_zero",
            }

        macaulay = (weighted_t / pv) / freq  # in years
        modified = macaulay / (Decimal("1") + period_yield)
        return {
            "holding_id": holding.holding_id,
            "years_to_maturity": str(years.quantize(Decimal("0.01"))),
            "n_periods": n_periods,
            "macaulay_duration": str(macaulay.quantize(Decimal("0.0001"))),
            "modified_duration": str(modified.quantize(Decimal("0.0001"))),
            "ytm_pct": str(ytm_pct),
        }

    @classmethod
    def portfolio_weighted_duration(
        cls,
        holdings: List[BondHolding],
        ytm_pct: Decimal,
    ) -> Dict[str, Any]:
        """Market-value weighted portfolio duration. Rule 1: None on zero MV."""
        total_mv = Decimal("0")
        weighted = Decimal("0")
        excluded = 0
        for h in holdings:
            d = cls.bond_modified_duration(h, ytm_pct)
            mv = _market_value_kes(h)
            if d.get("modified_duration") is None or mv is None:
                excluded += 1
                continue
            total_mv += mv
            weighted += Decimal(d["modified_duration"]) * mv
        if total_mv <= 0:
            return {
                "portfolio_modified_duration": None,
                "total_mv_kes": "0",
                "excluded_count": excluded,
                "reason": "zero_market_value",
            }
        return {
            "portfolio_modified_duration": str((weighted / total_mv).quantize(Decimal("0.0001"))),
            "total_mv_kes": str(total_mv.quantize(Decimal("0.01"))),
            "excluded_count": excluded,
        }

    @staticmethod
    def yield_to_maturity(
        holding: BondHolding,
        max_iterations: int = YTM_MAX_ITERATIONS,
        tolerance: Decimal = YTM_TOLERANCE,
    ) -> Dict[str, Any]:
        """
        Solve YTM via Newton-Raphson.
        Rule 1: returns None if doesn't converge or PV<=0.
        """
        if (holding.par_value_kes is None or holding.coupon_rate_pct is None
                or holding.market_price_pct is None
                or holding.maturity_date is None or holding.settlement_date is None):
            return {
                "holding_id": holding.holding_id,
                "ytm_pct": None,
                "reason": "missing_required_fields",
            }

        years = _years_to_maturity(holding)
        if years is None or years <= 0:
            return {
                "holding_id": holding.holding_id,
                "ytm_pct": None,
                "reason": "matured_or_invalid_dates",
            }

        freq = Decimal(holding.coupon_frequency_per_year)
        n = int(years * freq)
        if n < 1:
            n = 1
        coupon_cf = (holding.par_value_kes * holding.coupon_rate_pct / Decimal("100")) / freq
        market_value = holding.par_value_kes * holding.market_price_pct / Decimal("100")

        # Initial guess: coupon rate
        y = holding.coupon_rate_pct / Decimal("100") / freq
        if y <= 0:
            y = Decimal("0.05") / freq

        for _ in range(max_iterations):
            pv = Decimal("0")
            dpv_dy = Decimal("0")
            for t in range(1, n + 1):
                cf = coupon_cf
                if t == n:
                    cf += holding.par_value_kes
                disc = (Decimal("1") + y) ** t
                pv_cf = cf / disc
                pv += pv_cf
                # derivative w.r.t. y: -t × cf / (1+y)^(t+1)
                dpv_dy += -Decimal(t) * cf / ((Decimal("1") + y) ** (t + 1))
            f = pv - market_value
            if abs(f) < tolerance:
                annual_ytm = y * freq * Decimal("100")
                return {
                    "holding_id": holding.holding_id,
                    "ytm_pct": str(annual_ytm.quantize(Decimal("0.0001"))),
                    "iterations": _ + 1,
                }
            if dpv_dy == 0:
                break
            y = y - f / dpv_dy
            if y <= -1:  # blow up
                break

        return {
            "holding_id": holding.holding_id,
            "ytm_pct": None,
            "reason": "newton_raphson_did_not_converge",
        }

    @staticmethod
    def hqla_classification(holdings: List[BondHolding]) -> Dict[str, Any]:
        """Classify holdings by HQLA level per Basel III."""
        levels = {lv: Decimal("0") for lv in HQLA_CLASS}
        per_holding = []
        excluded = []
        for h in holdings:
            mv = _market_value_kes(h)
            if mv is None:
                excluded.append(h.holding_id)
                continue
            level = "NON_HQLA"
            if h.is_sovereign:
                level = "LEVEL_1"
            elif h.instrument_type == "TREASURY_BILL":
                level = "LEVEL_1"
            elif h.instrument_type == "EQUITY":
                level = "NON_HQLA"
            elif h.credit_rating in RATING_TO_HQLA_LEVEL:
                level = RATING_TO_HQLA_LEVEL[h.credit_rating]
            else:
                level = "NON_HQLA"
            levels[level] += mv
            per_holding.append({
                "holding_id": h.holding_id,
                "issuer": h.issuer,
                "level": level,
                "market_value_kes": str(mv.quantize(Decimal("0.01"))),
            })
        return {
            "by_level": {k: str(v.quantize(Decimal("0.01"))) for k, v in levels.items()},
            "excluded_count": len(excluded),
            "holdings": per_holding,
        }

    @staticmethod
    def concentration_risk(
        holdings: List[BondHolding],
        core_capital_kes: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Single-issuer concentration vs CBK 25% of core capital limit.
        Sector concentration vs 35% of investment book.
        Rule 1: limit_pct=None when core_capital<=0.
        """
        # Per-issuer
        by_issuer: Dict[str, Decimal] = {}
        by_sector: Dict[str, Decimal] = {}
        total_book = Decimal("0")
        excluded = []
        for h in holdings:
            mv = _market_value_kes(h)
            if mv is None:
                excluded.append(h.holding_id)
                continue
            by_issuer[h.issuer] = by_issuer.get(h.issuer, Decimal("0")) + mv
            by_sector[h.sector] = by_sector.get(h.sector, Decimal("0")) + mv
            total_book += mv

        # Issuer breaches
        issuer_breaches = []
        if core_capital_kes is not None and core_capital_kes > 0:
            for iss, amt in by_issuer.items():
                pct = amt / core_capital_kes * Decimal("100")
                if pct > SINGLE_ISSUER_LIMIT_PCT:
                    issuer_breaches.append({
                        "issuer": iss,
                        "amount_kes": str(amt.quantize(Decimal("0.01"))),
                        "limit_pct": str(pct.quantize(Decimal("0.01"))),
                        "breach": True,
                    })

        # Sector breaches
        sector_breaches = []
        if total_book > 0:
            for sec, amt in by_sector.items():
                pct = amt / total_book * Decimal("100")
                if pct > SINGLE_SECTOR_LIMIT_PCT:
                    sector_breaches.append({
                        "sector": sec,
                        "amount_kes": str(amt.quantize(Decimal("0.01"))),
                        "concentration_pct": str(pct.quantize(Decimal("0.01"))),
                        "breach": True,
                    })

        if core_capital_kes is None or core_capital_kes <= 0:
            return {
                "issuer_breaches": [],
                "sector_breaches": sector_breaches,
                "core_capital_kes": str(core_capital_kes) if core_capital_kes else None,
                "reason": "core_capital_zero_or_negative",
                "excluded_count": len(excluded),
            }

        return {
            "core_capital_kes": str(core_capital_kes.quantize(Decimal("0.01"))),
            "single_issuer_limit_pct": str(SINGLE_ISSUER_LIMIT_PCT),
            "single_sector_limit_pct": str(SINGLE_SECTOR_LIMIT_PCT),
            "issuer_count": len(by_issuer),
            "sector_count": len(by_sector),
            "issuer_breaches": issuer_breaches,
            "sector_breaches": sector_breaches,
            "total_book_kes": str(total_book.quantize(Decimal("0.01"))),
            "excluded_count": len(excluded),
        }


# ============================================================================
# Self-tests
# ============================================================================

def _bond(**kw):
    defaults = dict(
        holding_id="B1", instrument_type="GOVERNMENT_BOND",
        issuer="KENYA_GOK", sector="SOVEREIGN",
        par_value_kes=Decimal("100000000"),
        market_price_pct=Decimal("98.5"),
        coupon_rate_pct=Decimal("12.0"),
        coupon_frequency_per_year=2,
        maturity_date=date(2030, 6, 30),
        settlement_date=date(2026, 6, 30),
        credit_rating="AA",
        is_sovereign=True,
    )
    defaults.update(kw)
    return BondHolding(**defaults)


def _test_market_value_basic():
    r = InvestmentPortfolioEngine.portfolio_market_value([_bond()])
    assert r["total_market_value_kes"] == "98500000.00"


def _test_market_value_excluded_rule6():
    b = _bond(market_price_pct=None)
    r = InvestmentPortfolioEngine.portfolio_market_value([b])
    assert r["excluded_count"] == 1


def _test_modified_duration_basic():
    r = InvestmentPortfolioEngine.bond_modified_duration(_bond(), Decimal("12"))
    assert r["modified_duration"] is not None
    md = Decimal(r["modified_duration"])
    # 4-year bond, 12% coupon, 12% YTM → modified duration roughly 3.0-3.3 years
    assert Decimal("2.5") < md < Decimal("3.5")


def _test_modified_duration_missing_data_rule6():
    b = _bond(coupon_rate_pct=None)
    r = InvestmentPortfolioEngine.bond_modified_duration(b, Decimal("12"))
    assert r["modified_duration"] is None
    assert r["reason"] == "missing_required_fields"


def _test_modified_duration_matured_bond():
    b = _bond(maturity_date=date(2025, 1, 1))  # in past
    r = InvestmentPortfolioEngine.bond_modified_duration(b, Decimal("12"))
    assert r["modified_duration"] is None


def _test_portfolio_duration():
    r = InvestmentPortfolioEngine.portfolio_weighted_duration(
        [_bond()], Decimal("12")
    )
    assert r["portfolio_modified_duration"] is not None


def _test_portfolio_duration_zero_mv_rule1():
    b = _bond(market_price_pct=None)
    r = InvestmentPortfolioEngine.portfolio_weighted_duration([b], Decimal("12"))
    assert r["portfolio_modified_duration"] is None


def _test_ytm_basic():
    """A 4-year 12% coupon bond at 98.5 should yield ~12.5%."""
    r = InvestmentPortfolioEngine.yield_to_maturity(_bond())
    assert r["ytm_pct"] is not None
    ytm = Decimal(r["ytm_pct"])
    assert Decimal("12.0") < ytm < Decimal("13.0")


def _test_ytm_at_par_equals_coupon():
    b = _bond(market_price_pct=Decimal("100.0"), coupon_rate_pct=Decimal("12.0"))
    r = InvestmentPortfolioEngine.yield_to_maturity(b)
    ytm = Decimal(r["ytm_pct"])
    # When at par, YTM should equal coupon
    assert abs(ytm - Decimal("12.0")) < Decimal("0.05")


def _test_ytm_missing_data_rule6():
    b = _bond(par_value_kes=None)
    r = InvestmentPortfolioEngine.yield_to_maturity(b)
    assert r["ytm_pct"] is None


def _test_hqla_sovereign_level1():
    r = InvestmentPortfolioEngine.hqla_classification([_bond()])
    assert Decimal(r["by_level"]["LEVEL_1"]) > Decimal("0")


def _test_hqla_corporate_level2b():
    b = _bond(issuer="ACME_CORP", sector="INDUSTRIAL", is_sovereign=False,
             credit_rating="BBB", instrument_type="CORPORATE_BOND")
    r = InvestmentPortfolioEngine.hqla_classification([b])
    assert Decimal(r["by_level"]["LEVEL_2B"]) > Decimal("0")


def _test_hqla_equity_non_hqla():
    b = _bond(instrument_type="EQUITY", is_sovereign=False, credit_rating=None)
    r = InvestmentPortfolioEngine.hqla_classification([b])
    assert Decimal(r["by_level"]["NON_HQLA"]) > Decimal("0")


def _test_concentration_issuer_breach():
    # Core capital 100M, single issuer 50M = 50% > 25% limit
    b = _bond(par_value_kes=Decimal("60000000"), market_price_pct=Decimal("100"))
    r = InvestmentPortfolioEngine.concentration_risk([b], Decimal("100000000"))
    assert len(r["issuer_breaches"]) == 1


def _test_concentration_sector_breach():
    # All sovereign sector → 100% concentration > 35% limit
    bonds = [_bond(holding_id=f"B{i}", issuer=f"GOV{i}") for i in range(3)]
    r = InvestmentPortfolioEngine.concentration_risk(bonds, Decimal("10000000000"))
    assert len(r["sector_breaches"]) == 1


def _test_concentration_no_capital_rule1():
    r = InvestmentPortfolioEngine.concentration_risk([_bond()], None)
    assert "issuer_breaches" in r
    assert r.get("issuer_breaches") == []


def _test_limits_byte_for_byte():
    assert SINGLE_ISSUER_LIMIT_PCT == Decimal("25")
    assert SINGLE_SECTOR_LIMIT_PCT == Decimal("35")


def _test_hqla_class_byte_for_byte():
    for c in ("LEVEL_1", "LEVEL_2A", "LEVEL_2B", "NON_HQLA"):
        assert c in HQLA_CLASS


def _test_rating_mapping_byte_for_byte():
    assert RATING_TO_HQLA_LEVEL["AAA"] == "LEVEL_1"
    assert RATING_TO_HQLA_LEVEL["A"] == "LEVEL_2A"
    assert RATING_TO_HQLA_LEVEL["BBB-"] == "LEVEL_2B"


def self_test() -> bool:
    tests = [
        _test_market_value_basic,
        _test_market_value_excluded_rule6,
        _test_modified_duration_basic,
        _test_modified_duration_missing_data_rule6,
        _test_modified_duration_matured_bond,
        _test_portfolio_duration,
        _test_portfolio_duration_zero_mv_rule1,
        _test_ytm_basic,
        _test_ytm_at_par_equals_coupon,
        _test_ytm_missing_data_rule6,
        _test_hqla_sovereign_level1,
        _test_hqla_corporate_level2b,
        _test_hqla_equity_non_hqla,
        _test_concentration_issuer_breach,
        _test_concentration_sector_breach,
        _test_concentration_no_capital_rule1,
        _test_limits_byte_for_byte,
        _test_hqla_class_byte_for_byte,
        _test_rating_mapping_byte_for_byte,
    ]
    print("=" * 60)
    print("Investment Portfolio Engine — Self-Tests (#76)")
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

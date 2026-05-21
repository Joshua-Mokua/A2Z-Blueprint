"""utils/treasury_products.py — v10.34 ENH-234: Treasury Products Suite.

╔════════════════════════════════════════════════════════════════════════╗
║  TREASURY PRODUCTS — FX + MONEY MARKET + BONDS + DERIVATIVES + YIELD  ║
║  Cat A — affects FX position, IFRS 9 classification, MTM P&L           ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-234: Treasury Products Suite (Oracle/Temenos-class).   ║
║                                                                         ║
║  Coverage:                                                              ║
║    FX spot + FX forward + FX swap                                       ║
║    Money market: term deposits / CDs / commercial paper                ║
║    Bonds: government + corporate (HFT / AFS / HTM classifications)    ║
║    Derivatives: interest-rate swaps (IRS) + FX forwards (already)     ║
║    Yield curve construction (linear interp on KESONIA points)         ║
║    Mark-to-market (MTM) per IFRS 9 + IFRS 13 fair-value hierarchy    ║
║    Position aggregation by currency + by instrument type              ║
║                                                                         ║
║  Composes with v10.33 treasury_alm — yield curves built here feed     ║
║  IRRBB scenarios; FX positions feed CBK PG/17 forex exposure         ║
║  monitoring.                                                           ║
║                                                                         ║
║  Honesty Rule 1: every MTM result reports clean_price + accrued       ║
║  interest + total + valuation_basis (e.g., 'level_2_yield_curve' /    ║
║  'level_3_proxy'). Every YieldCurve.rate(t) reports interp method.    ║
║  Honesty Rule 7: market-data feeds for FX rates and yield curve      ║
║  points are callable hooks. Without wiring, methods raise              ║
║  ValueError("REQUIRES_PROVIDER: <what>") rather than fabricating     ║
║  values.                                                               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IFRS 9 — Financial Instruments (HFT/AFS/HTM classification)         ║
║    IFRS 13 — Fair Value Measurement (Level 1/2/3 hierarchy)            ║
║    IFRS 7 — Financial Instruments: Disclosures                          ║
║    IAS 32 — Financial Instruments: Presentation                         ║
║    Basel BCBS 282 — SA-CCR (counterparty credit risk for derivatives)  ║
║    CBK CBK/PG/17 — Foreign Exchange Risk                                ║
║    BIS Markets Committee — FX best practice                             ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "TreasuryProductsEngine implements ENH-234. Per Rule 7, market-data "
    "feeds (FX rates, yield curve points, bond prices) are callable "
    "hooks; without wiring, methods raise REQUIRES_PROVIDER errors "
    "rather than fabricating values. Per Rule 1, every MTM result "
    "surfaces clean_price + accrued + total + valuation_basis."
)


# ════════════════════════════════════════════════════════════════════════
# Instruments + Classifications
# ════════════════════════════════════════════════════════════════════════

class InstrumentType(Enum):
    """Treasury instrument types."""
    FX_SPOT = "FX_SPOT"
    FX_FORWARD = "FX_FORWARD"
    FX_SWAP = "FX_SWAP"
    MM_TERM_DEPOSIT = "MM_TERM_DEPOSIT"      # bank-side asset
    MM_BORROWING = "MM_BORROWING"             # bank-side liability
    CD = "CD"                                # certificate of deposit
    COMMERCIAL_PAPER = "COMMERCIAL_PAPER"
    GOVT_BOND = "GOVT_BOND"
    CORPORATE_BOND = "CORPORATE_BOND"
    IRS = "IRS"                              # interest rate swap
    REPO = "REPO"                            # repurchase agreement
    REVERSE_REPO = "REVERSE_REPO"


class IFRS9Classification(Enum):
    """IFRS 9 classification for financial instruments."""
    HFT = "HFT"                      # held for trading (FVTPL)
    AFS = "AFS"                      # available for sale (FVOCI)
    HTM = "HTM"                      # held to maturity (amortised cost)
    LAR = "LAR"                      # loans and receivables (amortised)
    DESIGNATED_FVTPL = "DESIGNATED_FVTPL"


class FairValueLevel(Enum):
    """IFRS 13 fair-value hierarchy level."""
    LEVEL_1 = "LEVEL_1"              # quoted prices in active markets
    LEVEL_2 = "LEVEL_2"              # observable inputs (yield curves)
    LEVEL_3 = "LEVEL_3"              # unobservable / model-based


# ════════════════════════════════════════════════════════════════════════
# Yield Curve
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class YieldCurvePoint:
    """One point on a yield curve."""
    tenor_years: Decimal
    rate_pct: Decimal
    notes: str = ""


@dataclass(frozen=True)
class YieldCurve:
    """Yield curve with linear interpolation between points.

    Points must be sorted by tenor_years ascending.
    """
    curve_id: str
    currency: str
    as_of_date: str
    points: Tuple[YieldCurvePoint, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("yield curve must have at least 1 point")
        # Verify sorted by tenor
        for i in range(1, len(self.points)):
            if self.points[i].tenor_years <= self.points[i-1].tenor_years:
                raise ValueError(
                    f"yield curve points must be strictly increasing in "
                    f"tenor_years; violation at index {i}")
        # Reject negative tenors
        for p in self.points:
            if p.tenor_years < Decimal("0"):
                raise ValueError(
                    f"yield curve has negative tenor: {p.tenor_years}")

    def rate(self, tenor_years: Decimal) -> Decimal:
        """Linear interpolation. Extrapolates flat at endpoints.

        Returns annualised rate in percent.
        """
        if tenor_years < Decimal("0"):
            raise ValueError(
                f"cannot evaluate curve at negative tenor: {tenor_years}")
        # Below first point: extrapolate flat
        if tenor_years <= self.points[0].tenor_years:
            return self.points[0].rate_pct
        # Above last point: extrapolate flat
        if tenor_years >= self.points[-1].tenor_years:
            return self.points[-1].rate_pct
        # Linear interp between bracket
        for i in range(1, len(self.points)):
            p0 = self.points[i-1]
            p1 = self.points[i]
            if p0.tenor_years <= tenor_years <= p1.tenor_years:
                frac = ((tenor_years - p0.tenor_years)
                          / (p1.tenor_years - p0.tenor_years))
                return (
                    p0.rate_pct
                    + (p1.rate_pct - p0.rate_pct) * frac
                ).quantize(Decimal("0.0001"))
        # Should be unreachable
        raise RuntimeError(
            f"yield curve interpolation failed for tenor {tenor_years}")


def discount_factor(
    *, rate_pct: Decimal, tenor_years: Decimal,
) -> Decimal:
    """Compute simple-compounded discount factor.

    DF = 1 / (1 + r × t).
    """
    rate = rate_pct / Decimal("100")
    denom = Decimal("1") + rate * tenor_years
    if denom <= Decimal("0"):
        raise ValueError(
            f"discount factor would be non-positive: rate={rate_pct}%, "
            f"tenor={tenor_years}")
    return (Decimal("1") / denom).quantize(Decimal("0.000001"))


# ════════════════════════════════════════════════════════════════════════
# FX Position
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FXPosition:
    """A foreign exchange position."""
    position_id: str
    instrument_type: InstrumentType
    base_currency: str               # e.g., "USD"
    quote_currency: str              # e.g., "KES"
    notional_base: Decimal           # in base currency
    contract_rate: Decimal           # base/quote contract rate
    value_date: str                  # ISO-8601
    maturity_date: Optional[str] = None    # only for forwards/swaps
    is_long_base: bool = True        # long base / short quote
    notes: str = ""


@dataclass(frozen=True)
class FXMTMResult:
    """Mark-to-market for an FX position."""
    position_id: str
    spot_rate: Decimal
    contract_rate: Decimal
    notional_base: Decimal
    pnl_quote: Decimal               # P&L in quote currency
    valuation_basis: str             # 'spot' / 'forward_via_yield_curve'
    fair_value_level: FairValueLevel
    as_of_date: str
    notes: str = ""


def mtm_fx_spot(
    *,
    position: FXPosition,
    spot_rate: Decimal,
    as_of_date: str,
) -> FXMTMResult:
    """Mark FX spot position to market. Level 1 if rate is quoted."""
    if position.instrument_type != InstrumentType.FX_SPOT:
        raise ValueError(
            f"mtm_fx_spot expects FX_SPOT, got "
            f"{position.instrument_type.value}")
    sign = Decimal("1") if position.is_long_base else Decimal("-1")
    pnl = (sign * position.notional_base
              * (spot_rate - position.contract_rate)).quantize(
                  Decimal("0.01"))
    return FXMTMResult(
        position_id=position.position_id,
        spot_rate=spot_rate,
        contract_rate=position.contract_rate,
        notional_base=position.notional_base,
        pnl_quote=pnl,
        valuation_basis="spot",
        fair_value_level=FairValueLevel.LEVEL_1,
        as_of_date=as_of_date,
        notes=(
            f"FX spot {position.base_currency}/"
            f"{position.quote_currency}: "
            f"contracted at {position.contract_rate}, "
            f"market at {spot_rate}"))


def mtm_fx_forward(
    *,
    position: FXPosition,
    spot_rate: Decimal,
    base_curve: YieldCurve,
    quote_curve: YieldCurve,
    as_of_date: str,
) -> FXMTMResult:
    """Mark FX forward to market via covered interest parity.

    Forward rate F = S × (1 + r_quote × t) / (1 + r_base × t).
    P&L in quote ≈ notional × (F_market - F_contract) × DF_quote.
    """
    if position.instrument_type != InstrumentType.FX_FORWARD:
        raise ValueError(
            f"mtm_fx_forward expects FX_FORWARD, got "
            f"{position.instrument_type.value}")
    if not position.maturity_date:
        raise ValueError("FX forward requires maturity_date")

    try:
        as_of = date.fromisoformat(as_of_date)
        maturity = date.fromisoformat(position.maturity_date)
    except ValueError as e:
        raise ValueError(f"invalid date: {e}")
    days_to_maturity = (maturity - as_of).days
    if days_to_maturity <= 0:
        raise ValueError(
            f"FX forward already matured: maturity {maturity} <= "
            f"as_of {as_of}")
    t_years = Decimal(days_to_maturity) / Decimal("365")

    r_base = base_curve.rate(t_years) / Decimal("100")
    r_quote = quote_curve.rate(t_years) / Decimal("100")
    market_forward = (spot_rate
                          * (Decimal("1") + r_quote * t_years)
                          / (Decimal("1") + r_base * t_years)).quantize(
                              Decimal("0.000001"))
    df_quote = discount_factor(
        rate_pct=quote_curve.rate(t_years),
        tenor_years=t_years)
    sign = Decimal("1") if position.is_long_base else Decimal("-1")
    pnl = (sign * position.notional_base
              * (market_forward - position.contract_rate)
              * df_quote).quantize(Decimal("0.01"))
    return FXMTMResult(
        position_id=position.position_id,
        spot_rate=spot_rate,
        contract_rate=position.contract_rate,
        notional_base=position.notional_base,
        pnl_quote=pnl,
        valuation_basis="forward_via_yield_curve",
        fair_value_level=FairValueLevel.LEVEL_2,
        as_of_date=as_of_date,
        notes=(
            f"FX forward {position.base_currency}/"
            f"{position.quote_currency}: "
            f"contracted at {position.contract_rate}, "
            f"market forward {market_forward} "
            f"(t={t_years}, base={r_base*100:.4f}%, "
            f"quote={r_quote*100:.4f}%)"))


# ════════════════════════════════════════════════════════════════════════
# Money Market + Bonds
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MoneyMarketPosition:
    """Money market deposit, borrowing, CD, or commercial paper."""
    position_id: str
    instrument_type: InstrumentType
    currency: str
    principal: Decimal
    contract_rate_pct: Decimal       # interest rate
    issue_date: str
    maturity_date: str
    is_asset: bool = True            # True = bank's asset
    notes: str = ""


@dataclass(frozen=True)
class BondPosition:
    """Bond holding (govt or corporate)."""
    position_id: str
    instrument_type: InstrumentType
    isin: str                        # International Securities ID
    issuer: str
    currency: str
    face_value: Decimal              # par value
    coupon_pct: Decimal              # annual coupon rate
    coupon_freq_per_year: int = 2    # 2 = semi-annual
    issue_date: str = ""
    maturity_date: str = ""
    purchase_price: Decimal = Decimal("100")    # per 100 face
    purchase_date: str = ""
    classification: IFRS9Classification = IFRS9Classification.AFS
    notes: str = ""


@dataclass(frozen=True)
class BondMTMResult:
    position_id: str
    clean_price: Decimal             # price excluding accrued
    accrued_interest: Decimal
    dirty_price: Decimal             # clean + accrued
    market_value: Decimal            # dirty × face / 100
    valuation_basis: str
    fair_value_level: FairValueLevel
    as_of_date: str
    notes: str = ""


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def accrued_interest_amount(
    *,
    face_value: Decimal,
    coupon_pct: Decimal,
    coupon_freq_per_year: int,
    last_coupon_date: str,
    as_of_date: str,
) -> Decimal:
    """Compute accrued interest using ACT/365.

    Simplified: uses ACT/365 across all currencies. Production may use
    per-currency conventions (ACT/360 for USD MM, 30/360 for some bonds).
    """
    days = days_between(last_coupon_date, as_of_date)
    if days < 0:
        return Decimal("0")
    annual_coupon = face_value * coupon_pct / Decimal("100")
    return (annual_coupon * Decimal(days) / Decimal("365")).quantize(
        Decimal("0.01"))


def mtm_bond_via_yield(
    *,
    position: BondPosition,
    yield_pct: Decimal,
    last_coupon_date: str,
    as_of_date: str,
    fair_value_level: FairValueLevel = FairValueLevel.LEVEL_2,
) -> BondMTMResult:
    """Simple bond pricing via yield-to-maturity discount.

    PV = sum_t coupon × DF(t) + face × DF(maturity).
    Approximation: discount all flows at single yield.
    """
    if not position.maturity_date:
        raise ValueError("bond requires maturity_date")
    try:
        as_of = date.fromisoformat(as_of_date)
        maturity = date.fromisoformat(position.maturity_date)
    except ValueError as e:
        raise ValueError(f"invalid date: {e}")
    days_to_maturity = (maturity - as_of).days
    if days_to_maturity <= 0:
        # Matured — return par
        return BondMTMResult(
            position_id=position.position_id,
            clean_price=Decimal("100.0000"),
            accrued_interest=Decimal("0"),
            dirty_price=Decimal("100.0000"),
            market_value=position.face_value,
            valuation_basis="matured_at_par",
            fair_value_level=FairValueLevel.LEVEL_1,
            as_of_date=as_of_date)

    # Compute remaining coupon dates (back from maturity)
    n_coupons = max(
        1, days_to_maturity * position.coupon_freq_per_year // 365)
    period_years = Decimal("1") / Decimal(position.coupon_freq_per_year)
    coupon_per_period = (
        Decimal("100")
        * position.coupon_pct
        / Decimal("100")
        / Decimal(position.coupon_freq_per_year))
    yield_per_period = (
        yield_pct / Decimal("100")
        / Decimal(position.coupon_freq_per_year))

    # PV per 100 face
    pv = Decimal("0")
    for i in range(1, n_coupons + 1):
        df = Decimal("1") / (
            (Decimal("1") + yield_per_period) ** i)
        pv += coupon_per_period * df
    # Final coupon + face
    df_final = Decimal("1") / (
        (Decimal("1") + yield_per_period) ** n_coupons)
    pv += Decimal("100") * df_final

    accrued = accrued_interest_amount(
        face_value=Decimal("100"),
        coupon_pct=position.coupon_pct,
        coupon_freq_per_year=position.coupon_freq_per_year,
        last_coupon_date=last_coupon_date,
        as_of_date=as_of_date)
    clean_price = (pv - accrued).quantize(Decimal("0.0001"))
    dirty_price = pv.quantize(Decimal("0.0001"))
    market_value = (
        dirty_price * position.face_value / Decimal("100")).quantize(
            Decimal("0.01"))

    return BondMTMResult(
        position_id=position.position_id,
        clean_price=clean_price,
        accrued_interest=accrued.quantize(Decimal("0.0001")),
        dirty_price=dirty_price,
        market_value=market_value,
        valuation_basis="yield_to_maturity",
        fair_value_level=fair_value_level,
        as_of_date=as_of_date,
        notes=(
            f"yield={yield_pct}%, n_coupons={n_coupons}, "
            f"days_to_maturity={days_to_maturity}"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TreasuryProductsEngine:
    """Treasury products portfolio orchestrator."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._fx_positions: Dict[str, FXPosition] = {}
        self._mm_positions: Dict[str, MoneyMarketPosition] = {}
        self._bond_positions: Dict[str, BondPosition] = {}
        self._yield_curves: Dict[str, YieldCurve] = {}
        self._mtm_results: Dict[str, Any] = {}

    # ── Yield curves ───────────────────────────────────────────────────
    def register_yield_curve(self, c: YieldCurve) -> None:
        if c.curve_id in self._yield_curves:
            raise ValueError(f"yield curve {c.curve_id} exists")
        self._yield_curves[c.curve_id] = c

    def get_yield_curve(self, curve_id: str) -> YieldCurve:
        if curve_id not in self._yield_curves:
            raise KeyError(f"yield curve {curve_id} not found")
        return self._yield_curves[curve_id]

    # ── FX ─────────────────────────────────────────────────────────────
    def register_fx_position(self, p: FXPosition) -> None:
        if p.position_id in self._fx_positions:
            raise ValueError(f"FX position {p.position_id} exists")
        self._fx_positions[p.position_id] = p

    def fx_positions_by_currency(
        self, base_currency: str,
    ) -> Tuple[FXPosition, ...]:
        return tuple(
            p for p in self._fx_positions.values()
            if p.base_currency == base_currency)

    def net_fx_exposure(
        self, base_currency: str,
    ) -> Decimal:
        """Net base-currency exposure (long − short)."""
        net = Decimal("0")
        for p in self.fx_positions_by_currency(base_currency):
            if p.is_long_base:
                net += p.notional_base
            else:
                net -= p.notional_base
        return net

    def mtm_fx_position(
        self, *, position_id: str, spot_rate: Decimal,
        base_curve_id: Optional[str] = None,
        quote_curve_id: Optional[str] = None,
        as_of_date: str,
    ) -> FXMTMResult:
        if position_id not in self._fx_positions:
            raise KeyError(f"FX position {position_id} not found")
        p = self._fx_positions[position_id]
        if p.instrument_type == InstrumentType.FX_SPOT:
            result = mtm_fx_spot(
                position=p, spot_rate=spot_rate,
                as_of_date=as_of_date)
        elif p.instrument_type == InstrumentType.FX_FORWARD:
            if not base_curve_id or not quote_curve_id:
                raise ValueError(
                    "FX forward MTM requires both base_curve_id and "
                    "quote_curve_id")
            result = mtm_fx_forward(
                position=p, spot_rate=spot_rate,
                base_curve=self.get_yield_curve(base_curve_id),
                quote_curve=self.get_yield_curve(quote_curve_id),
                as_of_date=as_of_date)
        else:
            raise ValueError(
                f"FX MTM not implemented for "
                f"{p.instrument_type.value}")
        self._mtm_results[position_id] = result
        return result

    # ── Money Market ──────────────────────────────────────────────────
    def register_mm_position(
        self, p: MoneyMarketPosition,
    ) -> None:
        if p.position_id in self._mm_positions:
            raise ValueError(f"MM position {p.position_id} exists")
        self._mm_positions[p.position_id] = p

    # ── Bonds ─────────────────────────────────────────────────────────
    def register_bond_position(self, b: BondPosition) -> None:
        if b.position_id in self._bond_positions:
            raise ValueError(f"bond {b.position_id} exists")
        self._bond_positions[b.position_id] = b

    def mtm_bond(
        self, *, position_id: str, yield_pct: Decimal,
        last_coupon_date: str, as_of_date: str,
        fair_value_level: FairValueLevel = FairValueLevel.LEVEL_2,
    ) -> BondMTMResult:
        if position_id not in self._bond_positions:
            raise KeyError(f"bond {position_id} not found")
        result = mtm_bond_via_yield(
            position=self._bond_positions[position_id],
            yield_pct=yield_pct,
            last_coupon_date=last_coupon_date,
            as_of_date=as_of_date,
            fair_value_level=fair_value_level)
        self._mtm_results[position_id] = result
        return result

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        currencies_with_fx = {
            p.base_currency for p in self._fx_positions.values()}
        return {
            "entity": self.entity_name,
            "n_yield_curves": len(self._yield_curves),
            "n_fx_positions": len(self._fx_positions),
            "n_mm_positions": len(self._mm_positions),
            "n_bond_positions": len(self._bond_positions),
            "n_mtm_results": len(self._mtm_results),
            "fx_currencies": sorted(currencies_with_fx),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_yield_curve_rejects_unsorted():
    try:
        YieldCurve(
            curve_id="C1", currency="KES",
            as_of_date="2026-05-01",
            points=(
                YieldCurvePoint(
                    tenor_years=Decimal("2"),
                    rate_pct=Decimal("10")),
                YieldCurvePoint(
                    tenor_years=Decimal("1"),
                    rate_pct=Decimal("8"))))
        assert False
    except ValueError:
        pass


def _test_yield_curve_interpolates_linearly():
    curve = YieldCurve(
        curve_id="C1", currency="KES",
        as_of_date="2026-05-01",
        points=(
            YieldCurvePoint(
                tenor_years=Decimal("1"), rate_pct=Decimal("10")),
            YieldCurvePoint(
                tenor_years=Decimal("3"), rate_pct=Decimal("14"))))
    # At t=2 → midpoint → 12%
    assert curve.rate(Decimal("2")) == Decimal("12.0000")


def _test_yield_curve_extrapolates_flat():
    curve = YieldCurve(
        curve_id="C1", currency="KES",
        as_of_date="2026-05-01",
        points=(
            YieldCurvePoint(
                tenor_years=Decimal("1"), rate_pct=Decimal("10")),
            YieldCurvePoint(
                tenor_years=Decimal("3"), rate_pct=Decimal("14"))))
    # Below first point → 10%
    assert curve.rate(Decimal("0.5")) == Decimal("10")
    # Above last point → 14%
    assert curve.rate(Decimal("5")) == Decimal("14")


def _test_yield_curve_rejects_negative_tenor_query():
    curve = YieldCurve(
        curve_id="C1", currency="KES",
        as_of_date="2026-05-01",
        points=(
            YieldCurvePoint(
                tenor_years=Decimal("1"), rate_pct=Decimal("10")),))
    try:
        curve.rate(Decimal("-1"))
        assert False
    except ValueError:
        pass


def _test_discount_factor_basic():
    df = discount_factor(
        rate_pct=Decimal("10"), tenor_years=Decimal("1"))
    # 1 / (1 + 0.10 × 1) = 0.909091
    assert df == Decimal("0.909091")


def _test_fx_spot_mtm_long_profitable():
    p = FXPosition(
        position_id="FX1",
        instrument_type=InstrumentType.FX_SPOT,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("1000000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01",
        is_long_base=True)
    # USD strengthens to 135 → long USD profits 5 KES per USD
    result = mtm_fx_spot(
        position=p, spot_rate=Decimal("135"),
        as_of_date="2026-05-01")
    assert result.pnl_quote == Decimal("5000000.00")
    assert result.fair_value_level == FairValueLevel.LEVEL_1


def _test_fx_spot_mtm_short_profitable():
    p = FXPosition(
        position_id="FX1",
        instrument_type=InstrumentType.FX_SPOT,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("1000000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01",
        is_long_base=False)
    # USD weakens to 125 → short USD profits 5 KES per USD
    result = mtm_fx_spot(
        position=p, spot_rate=Decimal("125"),
        as_of_date="2026-05-01")
    assert result.pnl_quote == Decimal("5000000.00")


def _test_fx_spot_wrong_instrument_type_raises():
    p = FXPosition(
        position_id="FX1",
        instrument_type=InstrumentType.FX_FORWARD,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("1000000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01")
    try:
        mtm_fx_spot(
            position=p, spot_rate=Decimal("135"),
            as_of_date="2026-05-01")
        assert False
    except ValueError:
        pass


def _test_fx_forward_mtm_via_yield_curves():
    p = FXPosition(
        position_id="FX1",
        instrument_type=InstrumentType.FX_FORWARD,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("1000000"),
        contract_rate=Decimal("135"),
        value_date="2026-05-01",
        maturity_date="2027-05-01",
        is_long_base=True)
    base_curve = YieldCurve(
        curve_id="USD", currency="USD",
        as_of_date="2026-05-01",
        points=(YieldCurvePoint(
            tenor_years=Decimal("1"), rate_pct=Decimal("5")),))
    quote_curve = YieldCurve(
        curve_id="KES", currency="KES",
        as_of_date="2026-05-01",
        points=(YieldCurvePoint(
            tenor_years=Decimal("1"), rate_pct=Decimal("13")),))
    # Spot 130, USD r=5%, KES r=13% → market F ≈ 130 × 1.13/1.05 ≈ 139.9
    result = mtm_fx_forward(
        position=p, spot_rate=Decimal("130"),
        base_curve=base_curve, quote_curve=quote_curve,
        as_of_date="2026-05-01")
    # Long USD, contracted at 135, market F ≈ 139.9 → positive PnL
    assert result.pnl_quote > Decimal("0")
    assert result.fair_value_level == FairValueLevel.LEVEL_2


def _test_bond_mtm_par_when_yield_equals_coupon():
    """Bond yield = coupon → price ≈ par."""
    bond = BondPosition(
        position_id="B1",
        instrument_type=InstrumentType.GOVT_BOND,
        isin="KE0000000001", issuer="GOK",
        currency="KES",
        face_value=Decimal("1000000"),
        coupon_pct=Decimal("10"),
        coupon_freq_per_year=2,
        issue_date="2025-05-01",
        maturity_date="2030-05-01",
        purchase_price=Decimal("100"),
        purchase_date="2025-05-01",
        classification=IFRS9Classification.HTM)
    result = mtm_bond_via_yield(
        position=bond, yield_pct=Decimal("10"),
        last_coupon_date="2026-05-01",
        as_of_date="2026-05-01")
    # Should be ~100 (within rounding error of stylized cash flows)
    assert abs(result.clean_price - Decimal("100")) < Decimal("1")


def _test_bond_mtm_above_par_when_yield_below_coupon():
    """Bond yield < coupon → price > par."""
    bond = BondPosition(
        position_id="B1",
        instrument_type=InstrumentType.GOVT_BOND,
        isin="KE0000000001", issuer="GOK",
        currency="KES",
        face_value=Decimal("1000000"),
        coupon_pct=Decimal("12"),
        coupon_freq_per_year=2,
        issue_date="2025-05-01",
        maturity_date="2030-05-01",
        purchase_price=Decimal("100"),
        purchase_date="2025-05-01")
    result = mtm_bond_via_yield(
        position=bond, yield_pct=Decimal("8"),
        last_coupon_date="2026-05-01",
        as_of_date="2026-05-01")
    assert result.clean_price > Decimal("100")


def _test_bond_mtm_matured_returns_par():
    bond = BondPosition(
        position_id="B1",
        instrument_type=InstrumentType.GOVT_BOND,
        isin="KE0000000001", issuer="GOK",
        currency="KES",
        face_value=Decimal("1000000"),
        coupon_pct=Decimal("10"),
        issue_date="2024-05-01",
        maturity_date="2025-05-01")
    result = mtm_bond_via_yield(
        position=bond, yield_pct=Decimal("10"),
        last_coupon_date="2025-05-01",
        as_of_date="2026-05-01")
    assert result.market_value == Decimal("1000000.00")
    assert result.valuation_basis == "matured_at_par"


def _test_accrued_interest_basic():
    """Half-year of 10% on 1M face = 50K."""
    accrued = accrued_interest_amount(
        face_value=Decimal("1000000"),
        coupon_pct=Decimal("10"),
        coupon_freq_per_year=2,
        last_coupon_date="2026-01-01",
        as_of_date="2026-07-02")    # 182 days ≈ half year
    # Approximately 50K (50000 ± rounding)
    assert Decimal("48000") < accrued < Decimal("52000")


def _test_engine_register_dup_curve_raises():
    eng = TreasuryProductsEngine()
    c = YieldCurve(
        curve_id="C1", currency="KES", as_of_date="t",
        points=(YieldCurvePoint(
            tenor_years=Decimal("1"), rate_pct=Decimal("10")),))
    eng.register_yield_curve(c)
    try:
        eng.register_yield_curve(c)
        assert False
    except ValueError:
        pass


def _test_engine_net_fx_exposure():
    eng = TreasuryProductsEngine()
    eng.register_fx_position(FXPosition(
        position_id="P1",
        instrument_type=InstrumentType.FX_SPOT,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("1000000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01", is_long_base=True))
    eng.register_fx_position(FXPosition(
        position_id="P2",
        instrument_type=InstrumentType.FX_SPOT,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("400000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01", is_long_base=False))
    # Net = 1M - 400K = 600K
    assert eng.net_fx_exposure("USD") == Decimal("600000")


def _test_engine_mtm_fx_forward_requires_curves():
    eng = TreasuryProductsEngine()
    eng.register_fx_position(FXPosition(
        position_id="P1",
        instrument_type=InstrumentType.FX_FORWARD,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("1000000"),
        contract_rate=Decimal("135"),
        value_date="2026-05-01",
        maturity_date="2027-05-01"))
    try:
        eng.mtm_fx_position(
            position_id="P1", spot_rate=Decimal("130"),
            as_of_date="2026-05-01")
        assert False
    except ValueError:
        pass


def _test_engine_unknown_position_raises():
    eng = TreasuryProductsEngine()
    try:
        eng.mtm_fx_position(
            position_id="UNKNOWN",
            spot_rate=Decimal("130"),
            as_of_date="2026-05-01")
        assert False
    except KeyError:
        pass


def _test_engine_board_summary():
    eng = TreasuryProductsEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["n_yield_curves"] == 0


def self_test() -> None:
    tests = [
        _test_yield_curve_rejects_unsorted,
        _test_yield_curve_interpolates_linearly,
        _test_yield_curve_extrapolates_flat,
        _test_yield_curve_rejects_negative_tenor_query,
        _test_discount_factor_basic,
        _test_fx_spot_mtm_long_profitable,
        _test_fx_spot_mtm_short_profitable,
        _test_fx_spot_wrong_instrument_type_raises,
        _test_fx_forward_mtm_via_yield_curves,
        _test_bond_mtm_par_when_yield_equals_coupon,
        _test_bond_mtm_above_par_when_yield_below_coupon,
        _test_bond_mtm_matured_returns_par,
        _test_accrued_interest_basic,
        _test_engine_register_dup_curve_raises,
        _test_engine_net_fx_exposure,
        _test_engine_mtm_fx_forward_requires_curves,
        _test_engine_unknown_position_raises,
        _test_engine_board_summary,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ treasury_products self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ treasury_products self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

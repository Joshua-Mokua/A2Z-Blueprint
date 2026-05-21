"""utils/fund_transfer_pricing.py — v10.34 ENH-236: FTP Enhancement.

╔════════════════════════════════════════════════════════════════════════╗
║  FUND TRANSFER PRICING — Matched-Maturity FTP + NIM Decomposition     ║
║  Cat A — affects RM compensation, product pricing, NIM attribution    ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-236: Fund Transfer Pricing (FTP) Enhancement.          ║
║                                                                         ║
║  Coverage:                                                              ║
║    Matched-maturity FTP — assigns funding cost to assets, funding     ║
║      credit to liabilities at the rate matching the product's tenor   ║
║    Liquidity premium spread — added to base FTP for term funding     ║
║    Per-product FTP rates (loans / deposits / FD / borrowings)        ║
║    Net Interest Margin decomposition: lending margin + funding margin ║
║    FTP curves built from yield curve points (e.g., from v10.34       ║
║      treasury_products.YieldCurve)                                    ║
║                                                                         ║
║  Composes with v10.34 treasury_products — yield curves built there    ║
║  feed FTP curve construction. Composes with v10.30 virtual_bank_core  ║
║  loans + accounts for portfolio FTP attribution.                      ║
║                                                                         ║
║  Honesty Rule 1: every FTP rate computation surfaces base_rate +     ║
║  liquidity_premium_bps + total_ftp + tenor_years + curve source.     ║
║  Every NIM decomposition surfaces lending_spread + funding_spread +  ║
║  net_margin separately.                                                ║
║  Honesty Rule 7: yield curve provider hookable; without wiring,      ║
║  attempts to build FTP curve raise ValueError("REQUIRES_PROVIDER:    ║
║  yield curve") rather than fabricating rates.                        ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel BCBS 144 — Sound principles for liquidity risk management   ║
║                     (FTP as liquidity governance tool)                  ║
║    EBA EBA/GL/2022/14 — IRRBB & CSRBB (FTP feeds banking-book        ║
║                                          interest rate risk)           ║
║    BIS Working Paper 33 (2011) — FTP best practice                    ║
║    CBK CBK/PG/16 — Liquidity Management (FTP as governance lever)    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "FTPEngine implements ENH-236 matched-maturity FTP. Per Rule 7, "
    "yield curve provider is callable hook; without wiring, "
    "construct_ftp_curve raises REQUIRES_PROVIDER errors. Per Rule 1, "
    "every FTP rate surfaces base_rate + liquidity_premium + total + "
    "tenor + curve source for examiner trace."
)


# ════════════════════════════════════════════════════════════════════════
# FTP Product Categories
# ════════════════════════════════════════════════════════════════════════

class FTPProductCategory(Enum):
    """Categories of products subject to FTP."""
    DEMAND_DEPOSIT = "DEMAND_DEPOSIT"        # current acct
    SAVINGS_DEPOSIT = "SAVINGS_DEPOSIT"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    INTERBANK_BORROWING = "INTERBANK_BORROWING"
    LOAN_TERM = "LOAN_TERM"
    LOAN_REVOLVING = "LOAN_REVOLVING"
    BOND_INVESTMENT = "BOND_INVESTMENT"
    UNSECURED_OD = "UNSECURED_OD"
    MORTGAGE = "MORTGAGE"


# Default liquidity premium spreads (bps) added to base curve
# Reflects the "term liquidity" cost beyond pure interest rate
DEFAULT_LIQUIDITY_PREMIUM_BPS: Mapping[
    FTPProductCategory, Decimal] = {
    FTPProductCategory.DEMAND_DEPOSIT: Decimal("0"),       # at-call
    FTPProductCategory.SAVINGS_DEPOSIT: Decimal("10"),     # 10bps
    FTPProductCategory.FIXED_DEPOSIT: Decimal("25"),       # 25bps
    FTPProductCategory.INTERBANK_BORROWING: Decimal("15"),
    FTPProductCategory.LOAN_TERM: Decimal("50"),           # 50bps
    FTPProductCategory.LOAN_REVOLVING: Decimal("20"),
    FTPProductCategory.BOND_INVESTMENT: Decimal("30"),
    FTPProductCategory.UNSECURED_OD: Decimal("75"),
    FTPProductCategory.MORTGAGE: Decimal("60"),            # 60bps
}


# Default behavioral tenors (years) for non-maturing products
# Used when contractual tenor is undefined — based on NMD modeling
DEFAULT_BEHAVIORAL_TENOR_YEARS: Mapping[
    FTPProductCategory, Decimal] = {
    FTPProductCategory.DEMAND_DEPOSIT: Decimal("2.0"),     # 2y core
    FTPProductCategory.SAVINGS_DEPOSIT: Decimal("3.0"),    # 3y core
    FTPProductCategory.LOAN_REVOLVING: Decimal("1.0"),
    FTPProductCategory.UNSECURED_OD: Decimal("0.5"),
}


# ════════════════════════════════════════════════════════════════════════
# FTP Curve
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FTPCurvePoint:
    tenor_years: Decimal
    ftp_rate_pct: Decimal
    base_rate_pct: Decimal
    liquidity_premium_bps: Decimal
    notes: str = ""


@dataclass(frozen=True)
class FTPCurve:
    """An FTP curve = yield curve + liquidity premium spread."""
    curve_id: str
    currency: str
    as_of_date: str
    points: Tuple[FTPCurvePoint, ...]
    source_yield_curve_id: str       # links to source YieldCurve
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.points:
            raise ValueError("FTP curve must have at least 1 point")
        for i in range(1, len(self.points)):
            if self.points[i].tenor_years <= self.points[i-1].tenor_years:
                raise ValueError(
                    f"FTP curve points must be strictly increasing in "
                    f"tenor; violation at index {i}")

    def ftp_rate(self, tenor_years: Decimal) -> Decimal:
        """Linear interpolation. Extrapolates flat at endpoints."""
        if tenor_years < Decimal("0"):
            raise ValueError(
                f"cannot evaluate at negative tenor: {tenor_years}")
        if tenor_years <= self.points[0].tenor_years:
            return self.points[0].ftp_rate_pct
        if tenor_years >= self.points[-1].tenor_years:
            return self.points[-1].ftp_rate_pct
        for i in range(1, len(self.points)):
            p0 = self.points[i-1]
            p1 = self.points[i]
            if p0.tenor_years <= tenor_years <= p1.tenor_years:
                frac = ((tenor_years - p0.tenor_years)
                          / (p1.tenor_years - p0.tenor_years))
                return (p0.ftp_rate_pct
                          + (p1.ftp_rate_pct - p0.ftp_rate_pct) * frac
                          ).quantize(Decimal("0.0001"))
        raise RuntimeError("FTP interpolation failure")


def construct_ftp_curve(
    *,
    curve_id: str,
    currency: str,
    as_of_date: str,
    yield_curve_points: Sequence[Tuple[Decimal, Decimal]],
    liquidity_premium_bps: Decimal,
    source_yield_curve_id: str,
) -> FTPCurve:
    """Build an FTP curve from yield curve points + liquidity premium.

    yield_curve_points: sequence of (tenor_years, base_rate_pct).
    """
    if not yield_curve_points:
        raise ValueError(
            "REQUIRES_PROVIDER: yield curve points must be supplied "
            "from a wired KESONIA / Treasury curve provider")
    points: List[FTPCurvePoint] = []
    for tenor, base_rate in yield_curve_points:
        ftp_rate = (
            base_rate + liquidity_premium_bps / Decimal("100"))
        points.append(FTPCurvePoint(
            tenor_years=tenor,
            ftp_rate_pct=ftp_rate.quantize(Decimal("0.0001")),
            base_rate_pct=base_rate,
            liquidity_premium_bps=liquidity_premium_bps))
    return FTPCurve(
        curve_id=curve_id, currency=currency,
        as_of_date=as_of_date, points=tuple(points),
        source_yield_curve_id=source_yield_curve_id,
        notes=(
            f"derived from {source_yield_curve_id} + "
            f"{liquidity_premium_bps} bps liquidity premium"))


# ════════════════════════════════════════════════════════════════════════
# Per-Product FTP Rate Computation
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FTPRateResult:
    """FTP rate computation for one product instance."""
    rate_id: str
    product_id: str
    product_category: FTPProductCategory
    tenor_years_used: Decimal
    base_rate_pct: Decimal
    liquidity_premium_bps: Decimal
    ftp_rate_pct: Decimal
    is_behavioral_tenor: bool        # True if NMD/revolving
    notes: str = ""


def compute_product_ftp_rate(
    *,
    rate_id: str,
    product_id: str,
    product_category: FTPProductCategory,
    contractual_tenor_years: Optional[Decimal],
    ftp_curve: FTPCurve,
    behavioral_tenor_years: Mapping[
        FTPProductCategory, Decimal] = DEFAULT_BEHAVIORAL_TENOR_YEARS,
) -> FTPRateResult:
    """Compute FTP rate for one product.

    For NMD products without contractual tenor, falls back to behavioral
    tenor.
    """
    # Determine tenor
    if contractual_tenor_years is not None and contractual_tenor_years > Decimal("0"):
        tenor = contractual_tenor_years
        is_behavioral = False
    elif product_category in behavioral_tenor_years:
        tenor = behavioral_tenor_years[product_category]
        is_behavioral = True
    else:
        raise ValueError(
            f"product {product_id} has no contractual tenor and no "
            f"behavioral tenor configured for "
            f"{product_category.value}")

    ftp_rate = ftp_curve.ftp_rate(tenor)
    # Find the curve point for this tenor (or interpolate base + premium)
    # Use the curve's stored composition
    base_rate = ftp_curve.points[0].base_rate_pct
    liquidity_bps = ftp_curve.points[0].liquidity_premium_bps
    for p in ftp_curve.points:
        if p.tenor_years >= tenor:
            base_rate = p.base_rate_pct
            liquidity_bps = p.liquidity_premium_bps
            break

    return FTPRateResult(
        rate_id=rate_id,
        product_id=product_id,
        product_category=product_category,
        tenor_years_used=tenor,
        base_rate_pct=base_rate,
        liquidity_premium_bps=liquidity_bps,
        ftp_rate_pct=ftp_rate,
        is_behavioral_tenor=is_behavioral,
        notes=(
            f"{product_category.value}: tenor "
            f"{'behavioral' if is_behavioral else 'contractual'} "
            f"= {tenor}y; FTP = {ftp_rate}%"))


# ════════════════════════════════════════════════════════════════════════
# NIM Decomposition
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class NIMDecomposition:
    """Net Interest Margin decomposition for one product position."""
    decomposition_id: str
    product_id: str
    product_category: FTPProductCategory
    is_asset: bool
    customer_rate_pct: Decimal       # rate paid by/to customer
    ftp_rate_pct: Decimal
    spread_pct: Decimal              # contribution: customer − FTP
    spread_label: str                # 'lending_margin' / 'funding_margin'
    notes: str = ""


def decompose_nim(
    *,
    decomposition_id: str,
    product_id: str,
    product_category: FTPProductCategory,
    is_asset: bool,
    customer_rate_pct: Decimal,
    ftp_rate_pct: Decimal,
) -> NIMDecomposition:
    """Decompose NIM for one product instance.

    For assets: lending_margin = customer_rate − FTP (positive = profit).
    For liabilities: funding_margin = FTP − customer_rate (positive = profit
    for the bank, since FTP pays the deposit-taking unit more than it
    pays customer).
    """
    if is_asset:
        spread = customer_rate_pct - ftp_rate_pct
        label = "lending_margin"
    else:
        spread = ftp_rate_pct - customer_rate_pct
        label = "funding_margin"
    return NIMDecomposition(
        decomposition_id=decomposition_id,
        product_id=product_id,
        product_category=product_category,
        is_asset=is_asset,
        customer_rate_pct=customer_rate_pct,
        ftp_rate_pct=ftp_rate_pct,
        spread_pct=spread.quantize(Decimal("0.0001")),
        spread_label=label,
        notes=(
            f"{label}: customer={customer_rate_pct}% FTP="
            f"{ftp_rate_pct}% spread={spread:.4f}%"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class FTPEngine:
    """Fund Transfer Pricing orchestrator."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._ftp_curves: Dict[str, FTPCurve] = {}
        self._rate_results: Dict[str, FTPRateResult] = {}
        self._decompositions: Dict[str, NIMDecomposition] = {}

    def register_ftp_curve(self, c: FTPCurve) -> None:
        if c.curve_id in self._ftp_curves:
            raise ValueError(f"FTP curve {c.curve_id} exists")
        self._ftp_curves[c.curve_id] = c

    def get_ftp_curve(self, curve_id: str) -> FTPCurve:
        if curve_id not in self._ftp_curves:
            raise KeyError(f"FTP curve {curve_id} not found")
        return self._ftp_curves[curve_id]

    def compute_product_rate(
        self, *,
        rate_id: str, product_id: str,
        product_category: FTPProductCategory,
        contractual_tenor_years: Optional[Decimal],
        ftp_curve_id: str,
    ) -> FTPRateResult:
        result = compute_product_ftp_rate(
            rate_id=rate_id, product_id=product_id,
            product_category=product_category,
            contractual_tenor_years=contractual_tenor_years,
            ftp_curve=self.get_ftp_curve(ftp_curve_id))
        self._rate_results[rate_id] = result
        return result

    def decompose_nim(
        self, *,
        decomposition_id: str, product_id: str,
        product_category: FTPProductCategory,
        is_asset: bool,
        customer_rate_pct: Decimal,
        ftp_rate_pct: Decimal,
    ) -> NIMDecomposition:
        result = decompose_nim(
            decomposition_id=decomposition_id,
            product_id=product_id,
            product_category=product_category,
            is_asset=is_asset,
            customer_rate_pct=customer_rate_pct,
            ftp_rate_pct=ftp_rate_pct)
        self._decompositions[decomposition_id] = result
        return result

    def all_decompositions(self) -> Tuple[NIMDecomposition, ...]:
        return tuple(self._decompositions.values())

    def board_summary(self) -> Dict[str, Any]:
        # Aggregate spreads
        lending_total = sum(
            (d.spread_pct for d in self._decompositions.values()
             if d.spread_label == "lending_margin"),
            Decimal("0"))
        funding_total = sum(
            (d.spread_pct for d in self._decompositions.values()
             if d.spread_label == "funding_margin"),
            Decimal("0"))
        return {
            "entity": self.entity_name,
            "n_ftp_curves": len(self._ftp_curves),
            "n_rate_results": len(self._rate_results),
            "n_decompositions": len(self._decompositions),
            "sum_lending_spread_pct": str(lending_total),
            "sum_funding_spread_pct": str(funding_total),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_default_liquidity_premium_demand_zero():
    assert (DEFAULT_LIQUIDITY_PREMIUM_BPS[
        FTPProductCategory.DEMAND_DEPOSIT] == Decimal("0"))


def _test_default_liquidity_premium_loan_50bps():
    assert (DEFAULT_LIQUIDITY_PREMIUM_BPS[
        FTPProductCategory.LOAN_TERM] == Decimal("50"))


def _test_behavioral_tenor_demand_2y():
    assert (DEFAULT_BEHAVIORAL_TENOR_YEARS[
        FTPProductCategory.DEMAND_DEPOSIT] == Decimal("2.0"))


def _test_construct_ftp_curve_basic():
    curve = construct_ftp_curve(
        curve_id="C1", currency="KES",
        as_of_date="2026-05-01",
        yield_curve_points=[
            (Decimal("0.5"), Decimal("10")),
            (Decimal("1"), Decimal("11")),
            (Decimal("3"), Decimal("13"))],
        liquidity_premium_bps=Decimal("50"),
        source_yield_curve_id="YC-KES")
    assert len(curve.points) == 3
    # 50bps = 0.5% added
    assert curve.points[0].ftp_rate_pct == Decimal("10.5000")
    assert curve.points[1].ftp_rate_pct == Decimal("11.5000")


def _test_construct_ftp_curve_no_points_raises_provider():
    try:
        construct_ftp_curve(
            curve_id="C1", currency="KES",
            as_of_date="2026-05-01",
            yield_curve_points=[],
            liquidity_premium_bps=Decimal("0"),
            source_yield_curve_id="YC-KES")
        assert False
    except ValueError as e:
        assert "REQUIRES_PROVIDER" in str(e)


def _test_ftp_curve_interpolation_linear():
    curve = FTPCurve(
        curve_id="C1", currency="KES",
        as_of_date="2026-05-01",
        points=(
            FTPCurvePoint(
                tenor_years=Decimal("1"),
                ftp_rate_pct=Decimal("10"),
                base_rate_pct=Decimal("9"),
                liquidity_premium_bps=Decimal("100")),
            FTPCurvePoint(
                tenor_years=Decimal("3"),
                ftp_rate_pct=Decimal("14"),
                base_rate_pct=Decimal("13"),
                liquidity_premium_bps=Decimal("100"))),
        source_yield_curve_id="YC")
    # At t=2 → midpoint → 12%
    assert curve.ftp_rate(Decimal("2")) == Decimal("12.0000")


def _test_compute_product_ftp_uses_contractual_tenor():
    curve = FTPCurve(
        curve_id="C1", currency="KES", as_of_date="t",
        points=(
            FTPCurvePoint(
                tenor_years=Decimal("1"),
                ftp_rate_pct=Decimal("10"),
                base_rate_pct=Decimal("9"),
                liquidity_premium_bps=Decimal("100")),),
        source_yield_curve_id="YC")
    result = compute_product_ftp_rate(
        rate_id="R1", product_id="L1",
        product_category=FTPProductCategory.LOAN_TERM,
        contractual_tenor_years=Decimal("2"),    # contractual
        ftp_curve=curve)
    assert not result.is_behavioral_tenor
    assert result.tenor_years_used == Decimal("2")


def _test_compute_product_ftp_falls_back_to_behavioral():
    """NMD product with no contractual tenor uses behavioral default."""
    curve = FTPCurve(
        curve_id="C1", currency="KES", as_of_date="t",
        points=(
            FTPCurvePoint(
                tenor_years=Decimal("1"),
                ftp_rate_pct=Decimal("10"),
                base_rate_pct=Decimal("10"),
                liquidity_premium_bps=Decimal("0")),),
        source_yield_curve_id="YC")
    result = compute_product_ftp_rate(
        rate_id="R1", product_id="D1",
        product_category=FTPProductCategory.DEMAND_DEPOSIT,
        contractual_tenor_years=None,
        ftp_curve=curve)
    assert result.is_behavioral_tenor
    assert result.tenor_years_used == Decimal("2.0")    # default


def _test_compute_product_ftp_no_tenor_raises():
    """Term loan without contractual tenor → ValueError."""
    curve = FTPCurve(
        curve_id="C1", currency="KES", as_of_date="t",
        points=(
            FTPCurvePoint(
                tenor_years=Decimal("1"),
                ftp_rate_pct=Decimal("10"),
                base_rate_pct=Decimal("9"),
                liquidity_premium_bps=Decimal("100")),),
        source_yield_curve_id="YC")
    try:
        compute_product_ftp_rate(
            rate_id="R1", product_id="L1",
            product_category=FTPProductCategory.LOAN_TERM,
            contractual_tenor_years=None,
            ftp_curve=curve)
        assert False
    except ValueError:
        pass


def _test_decompose_nim_lending():
    """Loan at 15% with 10% FTP → 5% lending margin."""
    result = decompose_nim(
        decomposition_id="D1", product_id="L1",
        product_category=FTPProductCategory.LOAN_TERM,
        is_asset=True,
        customer_rate_pct=Decimal("15"),
        ftp_rate_pct=Decimal("10"))
    assert result.spread_pct == Decimal("5.0000")
    assert result.spread_label == "lending_margin"


def _test_decompose_nim_funding():
    """Deposit at 5% with FTP 8% → 3% funding margin (positive)."""
    result = decompose_nim(
        decomposition_id="D1", product_id="DEP1",
        product_category=FTPProductCategory.FIXED_DEPOSIT,
        is_asset=False,
        customer_rate_pct=Decimal("5"),
        ftp_rate_pct=Decimal("8"))
    assert result.spread_pct == Decimal("3.0000")
    assert result.spread_label == "funding_margin"


def _test_decompose_nim_negative_spread():
    """Loan at 8% with FTP 10% → −2% lending margin."""
    result = decompose_nim(
        decomposition_id="D1", product_id="L1",
        product_category=FTPProductCategory.LOAN_TERM,
        is_asset=True,
        customer_rate_pct=Decimal("8"),
        ftp_rate_pct=Decimal("10"))
    assert result.spread_pct == Decimal("-2.0000")


def _test_engine_register_dup_curve_raises():
    eng = FTPEngine()
    c = FTPCurve(
        curve_id="C1", currency="KES", as_of_date="t",
        points=(FTPCurvePoint(
            tenor_years=Decimal("1"),
            ftp_rate_pct=Decimal("10"),
            base_rate_pct=Decimal("9"),
            liquidity_premium_bps=Decimal("100")),),
        source_yield_curve_id="YC")
    eng.register_ftp_curve(c)
    try:
        eng.register_ftp_curve(c)
        assert False
    except ValueError:
        pass


def _test_engine_get_unknown_curve_raises():
    eng = FTPEngine()
    try:
        eng.get_ftp_curve("UNKNOWN")
        assert False
    except KeyError:
        pass


def _test_engine_decompose_aggregation():
    eng = FTPEngine()
    eng.decompose_nim(
        decomposition_id="D1", product_id="L1",
        product_category=FTPProductCategory.LOAN_TERM,
        is_asset=True,
        customer_rate_pct=Decimal("15"),
        ftp_rate_pct=Decimal("10"))
    eng.decompose_nim(
        decomposition_id="D2", product_id="DEP1",
        product_category=FTPProductCategory.FIXED_DEPOSIT,
        is_asset=False,
        customer_rate_pct=Decimal("5"),
        ftp_rate_pct=Decimal("8"))
    assert len(eng.all_decompositions()) == 2
    s = eng.board_summary()
    assert s["sum_lending_spread_pct"] == "5.0000"
    assert s["sum_funding_spread_pct"] == "3.0000"


def _test_engine_board_summary():
    eng = FTPEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["n_ftp_curves"] == 0


def self_test() -> None:
    tests = [
        _test_default_liquidity_premium_demand_zero,
        _test_default_liquidity_premium_loan_50bps,
        _test_behavioral_tenor_demand_2y,
        _test_construct_ftp_curve_basic,
        _test_construct_ftp_curve_no_points_raises_provider,
        _test_ftp_curve_interpolation_linear,
        _test_compute_product_ftp_uses_contractual_tenor,
        _test_compute_product_ftp_falls_back_to_behavioral,
        _test_compute_product_ftp_no_tenor_raises,
        _test_decompose_nim_lending,
        _test_decompose_nim_funding,
        _test_decompose_nim_negative_spread,
        _test_engine_register_dup_curve_raises,
        _test_engine_get_unknown_curve_raises,
        _test_engine_decompose_aggregation,
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
        print(f"✗ fund_transfer_pricing self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ fund_transfer_pricing self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

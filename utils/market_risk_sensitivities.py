"""utils/market_risk_sensitivities.py — v10.39: Sensitivity Measures.

╔════════════════════════════════════════════════════════════════════════╗
║  MARKET RISK — SENSITIVITY-BASED MEASURES                              ║
║  Cat A — Standard ENH-MR-003                                           ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements sensitivity computation for the FRTB Sensitivity-          ║
║  Based Method (BCBS d352 §A.5) plus standalone DV01 / FX delta /        ║
║  equity delta / vega measures used in everyday market-risk             ║
║  reporting.                                                             ║
║                                                                         ║
║  Honesty Rule 1: every Sensitivity record carries factor +             ║
║  delta + curvature + units + framework refs. Aggregate                  ║
║  reports surface the per-factor breakdown, never just a                ║
║  scalar total.                                                          ║
║                                                                         ║
║  Honesty Rule 7: live yield curves, FX spot rates, vol surfaces        ║
║  are EXTERNAL. Methods that need live data raise                        ║
║  REQUIRES_PROVIDER:market_data_provider when no provider is             ║
║  wired. Callers either pass curves / rates explicitly or                ║
║  register a provider for the engine.                                    ║
║                                                                         ║
║  Composes with: market_risk_factors (RiskFactor taxonomy),             ║
║  market_risk_var (factor-decomposed VaR via sensitivities +             ║
║  covariance), treasury_alm (DV01 of banking-book bonds                 ║
║  reuses this engine).                                                  ║
║                                                                         ║
║  Regulatory anchors: BCBS d352 FRTB SBM §A.5, BCBS d368 IRRBB          ║
║  EVE/NII sensitivities, IFRS 7 §40 sensitivity disclosures.            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

from utils.market_risk_factors import (
    RISK_FACTOR_TO_CLASS, RiskFactor, RiskFactorClass)

# Rule 6: Decimal precision for monetary numbers
getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "SensitivityEngine implements ENH-MR-003 per BCBS d352 §A.5 "
    "Sensitivity-Based Method + IFRS 7 §40 disclosures. DV01 uses "
    "the +1bp parallel shift convention; reported as a positive "
    "number for long positions (loss when rates rise). FX delta "
    "uses domestic-currency value approach (KES home). Curvature "
    "is the second-order term per FRTB. Per Rule 7, live curves "
    "and rates are an external provider."
)


# ════════════════════════════════════════════════════════════════════════
# Sensitivity dataclass
# ════════════════════════════════════════════════════════════════════════

class SensitivityType(Enum):
    """The kind of sensitivity recorded."""
    DELTA = "DELTA"           # first-order, linear
    VEGA = "VEGA"             # vol sensitivity
    CURVATURE = "CURVATURE"   # FRTB second-order
    DV01 = "DV01"             # standalone IR convention


@dataclass(frozen=True)
class Sensitivity:
    """A position's exposure to a single risk factor.

    Per Rule 1, every Sensitivity carries explicit:
      - factor (which factor)
      - sensitivity_type (DELTA / VEGA / CURVATURE / DV01)
      - delta (first-order signed)
      - curvature (second-order; None if not measured)
      - units ("KES per bp" / "KES per 1% FX move" / etc.)
    """
    factor: RiskFactor
    sensitivity_type: SensitivityType
    delta: Decimal
    units: str = ""
    curvature: Optional[Decimal] = None
    notes: str = ""
    framework_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.delta, Decimal):
            raise TypeError("delta must be Decimal")
        if (self.curvature is not None
                and not isinstance(self.curvature, Decimal)):
            raise TypeError("curvature must be Decimal or None")


# ════════════════════════════════════════════════════════════════════════
# Position abstractions
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BondPosition:
    """A fixed-income position for DV01 / curvature computation.

    notional_kes: present value at base curve
    modified_duration: years (annualized)
    convexity: years² (positive for plain bonds)
    factor: which IR factor drives the position (e.g.
        IR_KES_GOVT for government bonds)
    """
    position_id: str
    factor: RiskFactor
    notional_kes: Decimal
    modified_duration: Decimal
    convexity: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if RISK_FACTOR_TO_CLASS[self.factor] != (
                RiskFactorClass.INTEREST_RATE):
            raise ValueError(
                f"BondPosition.factor must be an IR factor; "
                f"got {self.factor.value}")
        if self.modified_duration < 0:
            raise ValueError(
                "modified_duration must be non-negative")


@dataclass(frozen=True)
class FXPosition:
    """An FX position for delta computation.

    foreign_amount: amount held in the foreign currency
    spot_to_kes: spot exchange rate (units of KES per 1 unit
        foreign — provided by caller, not fetched)
    factor: the FX factor (e.g., FX_USDKES)
    """
    position_id: str
    factor: RiskFactor
    foreign_amount: Decimal
    spot_to_kes: Decimal

    def __post_init__(self) -> None:
        if RISK_FACTOR_TO_CLASS[self.factor] != (
                RiskFactorClass.FOREIGN_EXCHANGE):
            raise ValueError(
                f"FXPosition.factor must be an FX factor; "
                f"got {self.factor.value}")
        if self.spot_to_kes <= 0:
            raise ValueError("spot_to_kes must be positive")


@dataclass(frozen=True)
class EquityPosition:
    """An equity position for delta computation."""
    position_id: str
    factor: RiskFactor
    market_value_kes: Decimal
    beta: Decimal = Decimal("1.0")

    def __post_init__(self) -> None:
        if RISK_FACTOR_TO_CLASS[self.factor] != (
                RiskFactorClass.EQUITY):
            raise ValueError(
                f"EquityPosition.factor must be an equity factor; "
                f"got {self.factor.value}")


# ════════════════════════════════════════════════════════════════════════
# Aggregated report
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SensitivityReport:
    """Per Rule 1: full per-factor + per-class breakdown."""
    sensitivities: Tuple[Sensitivity, ...]
    by_factor: Mapping[RiskFactor, Decimal]
    by_class: Mapping[RiskFactorClass, Decimal]
    total_delta_kes: Decimal
    framework_refs: Tuple[str, ...]
    n_positions: int


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

ONE_BP = Decimal("0.0001")     # 1 basis point as fraction
ONE_PCT = Decimal("0.01")      # 1 percent as fraction


class SensitivityEngine:
    """Computes sensitivity-based measures.

    Per Rule 7, all market data inputs (curves, rates, vols) are
    passed in by the caller. The engine never fetches.
    """

    def __init__(self) -> None:
        pass

    # ── DV01 ──────────────────────────────────────────────────────────
    def compute_dv01(
        self, position: BondPosition,
    ) -> Sensitivity:
        """DV01 = − dP/dy × 1bp.

        Using modified duration approximation:
          ΔP ≈ − D_mod × P × Δy
        With Δy = 1bp = 0.0001:
          DV01 = D_mod × P × 0.0001

        Reported as positive: a long bond loses value when rates
        rise, so DV01 is the magnitude of that loss for a +1bp
        shift. Apply a negative sign to the position to denote
        short exposure.
        """
        delta = (
            position.modified_duration *
            position.notional_kes * ONE_BP)
        # Curvature ≈ 0.5 × Convexity × P × (Δy)²
        delta_y_squared = ONE_BP * ONE_BP
        curvature: Optional[Decimal] = None
        if position.convexity != 0:
            curvature = (
                Decimal("0.5") *
                position.convexity *
                position.notional_kes *
                delta_y_squared)
        return Sensitivity(
            factor=position.factor,
            sensitivity_type=SensitivityType.DV01,
            delta=delta,
            units="KES per +1bp parallel shift",
            curvature=curvature,
            notes=(
                f"position={position.position_id}, "
                f"D_mod={position.modified_duration}, "
                f"convexity={position.convexity}"),
            framework_refs=(
                "BCBS d368 IRRBB EVE",
                "Modified duration / convexity"),
        )

    # ── FX delta ──────────────────────────────────────────────────────
    def compute_fx_delta(
        self, position: FXPosition,
    ) -> Sensitivity:
        """Delta for a 1% relative shift in the FX rate.

        ΔV_KES ≈ foreign_amount × spot × 1% relative
              = foreign_amount × spot × 0.01

        Reported as signed (positive when long foreign currency).
        """
        kes_value = position.foreign_amount * position.spot_to_kes
        delta = kes_value * ONE_PCT
        return Sensitivity(
            factor=position.factor,
            sensitivity_type=SensitivityType.DELTA,
            delta=delta,
            units="KES per +1% FX move (long convention)",
            notes=(
                f"position={position.position_id}, "
                f"foreign={position.foreign_amount}, "
                f"spot={position.spot_to_kes}, "
                f"kes_value={kes_value}"),
            framework_refs=(
                "BCBS d352 FRTB SBM FX",
                "IFRS 7 §40 sensitivity disclosure"),
        )

    # ── Equity delta ──────────────────────────────────────────────────
    def compute_equity_delta(
        self, position: EquityPosition,
    ) -> Sensitivity:
        """Equity delta for a 1% factor move.

        Beta-adjusted: Δ ≈ market_value × beta × 1%.
        """
        delta = position.market_value_kes * position.beta * ONE_PCT
        return Sensitivity(
            factor=position.factor,
            sensitivity_type=SensitivityType.DELTA,
            delta=delta,
            units="KES per +1% equity factor move (beta-adjusted)",
            notes=(
                f"position={position.position_id}, "
                f"mv={position.market_value_kes}, "
                f"beta={position.beta}"),
            framework_refs=(
                "BCBS d352 FRTB SBM Equity",
                "IFRS 7 §40 sensitivity disclosure"),
        )

    # ── Aggregation ───────────────────────────────────────────────────
    def aggregate(
        self,
        sensitivities: Sequence[Sensitivity],
    ) -> SensitivityReport:
        """Aggregate by factor and class.

        Per Rule 1: the report carries both the per-factor sums
        and the per-class sums plus the total. No information is
        collapsed away.

        Note: simple linear aggregation. Correlation-aware
        aggregation (FRTB SBM with prescribed correlation rho) is
        a separate method (aggregate_with_correlations) — not
        included in this batch.
        """
        by_factor: Dict[RiskFactor, Decimal] = {}
        by_class: Dict[RiskFactorClass, Decimal] = {}
        total = Decimal("0")
        framework_refs: set = set()

        for s in sensitivities:
            by_factor[s.factor] = (
                by_factor.get(s.factor, Decimal("0")) + s.delta)
            cls = RISK_FACTOR_TO_CLASS[s.factor]
            by_class[cls] = (
                by_class.get(cls, Decimal("0")) + s.delta)
            total += s.delta
            framework_refs.update(s.framework_refs)

        return SensitivityReport(
            sensitivities=tuple(sensitivities),
            by_factor=dict(by_factor),
            by_class=dict(by_class),
            total_delta_kes=total,
            framework_refs=tuple(sorted(framework_refs)),
            n_positions=len(sensitivities),
        )

    # ── Scenario application ──────────────────────────────────────────
    def apply_scenario_pnl(
        self,
        sensitivities: Sequence[Sensitivity],
        shocks: Mapping[RiskFactor, Tuple[Decimal, str]],
    ) -> Decimal:
        """Estimate PnL impact under a scenario using sensitivities.

        For each sensitivity, the PnL contribution is:
          - DV01: delta × shock_in_bps  (if shock is in bps)
          - DELTA (FX): delta × (shock_pct / 1) for relative shocks
                         in percent
          - DELTA (Equity): delta × (shock_pct / 1)
          - DELTA (other): delta × (shock_pct / 1)

        shocks: factor → (magnitude, shock_type_string) where
            shock_type_string is one of "ABSOLUTE_BPS" /
            "RELATIVE_PCT" / "ABSOLUTE_PCT" matching ShockType.

        Per Rule 1, returns a single Decimal but the per-factor
        contributions are reproducible by calling
        per_factor_pnl_contribution() with the same inputs.
        """
        return sum(
            self._single_pnl(s, shocks.get(s.factor)) or Decimal("0")
            for s in sensitivities) or Decimal("0")

    def per_factor_pnl_contribution(
        self,
        sensitivities: Sequence[Sensitivity],
        shocks: Mapping[RiskFactor, Tuple[Decimal, str]],
    ) -> Mapping[RiskFactor, Decimal]:
        """Per Rule 1: factor-level PnL contribution map.

        Useful for diagnostic reports — see exactly which factor
        drove the headline number.
        """
        contributions: Dict[RiskFactor, Decimal] = {}
        for s in sensitivities:
            shock = shocks.get(s.factor)
            if shock is None:
                continue
            pnl = self._single_pnl(s, shock)
            if pnl is None:
                continue
            contributions[s.factor] = (
                contributions.get(s.factor, Decimal("0")) + pnl)
        return dict(contributions)

    @staticmethod
    def _single_pnl(
        s: Sensitivity,
        shock: Optional[Tuple[Decimal, str]],
    ) -> Optional[Decimal]:
        if shock is None:
            return None
        magnitude, shock_type = shock

        if s.sensitivity_type == SensitivityType.DV01:
            # delta is per +1bp; PnL of +N bps = delta × N (with
            # sign convention: long bond loses if rates rise)
            if shock_type == "ABSOLUTE_BPS":
                # PnL = − delta × shock_in_bps (negative because
                # DV01 stored as magnitude of loss for +1bp on
                # long position)
                return -s.delta * magnitude
            return None
        # DELTA-type for FX and equity
        if s.sensitivity_type == SensitivityType.DELTA:
            if shock_type in ("RELATIVE_PCT", "ABSOLUTE_PCT"):
                # delta is per +1% move; multiply by shock %
                return s.delta * magnitude
            return None
        return None


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_dv01_simple_long_bond():
    eng = SensitivityEngine()
    p = BondPosition(
        position_id="GOV-10Y-1",
        factor=RiskFactor.IR_KES_GOVT,
        notional_kes=Decimal("1000000"),     # 1m KES
        modified_duration=Decimal("7.0"))
    s = eng.compute_dv01(p)
    # DV01 = 7.0 × 1,000,000 × 0.0001 = 700 KES per +1bp
    assert s.delta == Decimal("700.0000")
    assert s.factor == RiskFactor.IR_KES_GOVT
    assert s.sensitivity_type == SensitivityType.DV01


def _test_dv01_with_convexity():
    eng = SensitivityEngine()
    p = BondPosition(
        position_id="GOV-10Y-2",
        factor=RiskFactor.IR_KES_GOVT,
        notional_kes=Decimal("1000000"),
        modified_duration=Decimal("7.0"),
        convexity=Decimal("60.0"))
    s = eng.compute_dv01(p)
    # Curvature = 0.5 × 60 × 1,000,000 × 1e-8 = 0.3
    assert s.curvature is not None
    assert s.curvature == Decimal("0.300000000")


def _test_dv01_zero_duration_zero_delta():
    eng = SensitivityEngine()
    p = BondPosition(
        position_id="CASH",
        factor=RiskFactor.IR_KES_GENERIC,
        notional_kes=Decimal("1000000"),
        modified_duration=Decimal("0"))
    s = eng.compute_dv01(p)
    assert s.delta == Decimal("0.0000")


def _test_dv01_rejects_non_ir_factor():
    eng = SensitivityEngine()
    try:
        BondPosition(
            position_id="bad",
            factor=RiskFactor.FX_USDKES,    # FX, not IR
            notional_kes=Decimal("1000"),
            modified_duration=Decimal("5"))
        assert False
    except ValueError:
        pass


def _test_fx_delta_long_position():
    eng = SensitivityEngine()
    p = FXPosition(
        position_id="USD-LONG-1",
        factor=RiskFactor.FX_USDKES,
        foreign_amount=Decimal("100000"),     # USD 100k long
        spot_to_kes=Decimal("130.0"))
    s = eng.compute_fx_delta(p)
    # KES value = 100,000 × 130 = 13,000,000
    # Delta @ +1% = 13,000,000 × 0.01 = 130,000
    assert s.delta == Decimal("130000.00")
    assert s.sensitivity_type == SensitivityType.DELTA


def _test_fx_delta_short_position():
    eng = SensitivityEngine()
    p = FXPosition(
        position_id="USD-SHORT-1",
        factor=RiskFactor.FX_USDKES,
        foreign_amount=Decimal("-50000"),     # USD 50k short
        spot_to_kes=Decimal("130.0"))
    s = eng.compute_fx_delta(p)
    # Delta = -50,000 × 130 × 0.01 = -65,000
    assert s.delta == Decimal("-65000.00")


def _test_fx_delta_rejects_non_fx_factor():
    try:
        FXPosition(
            position_id="bad",
            factor=RiskFactor.IR_KES_GENERIC,   # IR, not FX
            foreign_amount=Decimal("1000"),
            spot_to_kes=Decimal("130"))
        assert False
    except ValueError:
        pass


def _test_fx_delta_rejects_non_positive_spot():
    try:
        FXPosition(
            position_id="bad",
            factor=RiskFactor.FX_USDKES,
            foreign_amount=Decimal("1000"),
            spot_to_kes=Decimal("0"))
        assert False
    except ValueError:
        pass


def _test_equity_delta_with_beta():
    eng = SensitivityEngine()
    p = EquityPosition(
        position_id="NSE-PORT-1",
        factor=RiskFactor.EQUITY_NSE_GENERIC,
        market_value_kes=Decimal("5000000"),
        beta=Decimal("1.2"))
    s = eng.compute_equity_delta(p)
    # 5m × 1.2 × 0.01 = 60,000
    assert s.delta == Decimal("60000.000")


def _test_aggregate_by_factor_and_class():
    eng = SensitivityEngine()
    sens = (
        Sensitivity(
            RiskFactor.IR_KES_GOVT,
            SensitivityType.DV01,
            Decimal("700"), units="KES/bp"),
        Sensitivity(
            RiskFactor.IR_KES_GOVT,
            SensitivityType.DV01,
            Decimal("300"), units="KES/bp"),
        Sensitivity(
            RiskFactor.FX_USDKES,
            SensitivityType.DELTA,
            Decimal("130000"), units="KES/1%"),
    )
    rep = eng.aggregate(sens)
    assert rep.by_factor[RiskFactor.IR_KES_GOVT] == Decimal("1000")
    assert rep.by_factor[RiskFactor.FX_USDKES] == Decimal("130000")
    assert rep.by_class[
        RiskFactorClass.INTEREST_RATE] == Decimal("1000")
    assert rep.by_class[
        RiskFactorClass.FOREIGN_EXCHANGE] == Decimal("130000")
    assert rep.total_delta_kes == Decimal("131000")


def _test_apply_scenario_pnl_dv01_loss_on_rate_up():
    eng = SensitivityEngine()
    sens = (
        Sensitivity(
            RiskFactor.IR_KES_GENERIC,
            SensitivityType.DV01,
            Decimal("700"), units="KES/bp"),
    )
    shocks = {
        RiskFactor.IR_KES_GENERIC: (
            Decimal("200"), "ABSOLUTE_BPS"),
    }
    pnl = eng.apply_scenario_pnl(sens, shocks)
    # PnL = -700 × 200 = -140,000 (loss when rates rise)
    assert pnl == Decimal("-140000")


def _test_apply_scenario_pnl_fx_gain_on_appreciation():
    eng = SensitivityEngine()
    sens = (
        Sensitivity(
            RiskFactor.FX_USDKES,
            SensitivityType.DELTA,
            Decimal("130000"), units="KES/1%"),
    )
    shocks = {
        RiskFactor.FX_USDKES: (Decimal("15"), "RELATIVE_PCT"),
    }
    pnl = eng.apply_scenario_pnl(sens, shocks)
    # PnL = 130,000 × 15 = 1,950,000 (long USD, KES weakens)
    assert pnl == Decimal("1950000")


def _test_per_factor_contribution_breakdown():
    eng = SensitivityEngine()
    sens = (
        Sensitivity(
            RiskFactor.IR_KES_GENERIC,
            SensitivityType.DV01,
            Decimal("700"), units="KES/bp"),
        Sensitivity(
            RiskFactor.FX_USDKES,
            SensitivityType.DELTA,
            Decimal("130000"), units="KES/1%"),
    )
    shocks = {
        RiskFactor.IR_KES_GENERIC: (
            Decimal("200"), "ABSOLUTE_BPS"),
        RiskFactor.FX_USDKES: (Decimal("15"), "RELATIVE_PCT"),
    }
    contrib = eng.per_factor_pnl_contribution(sens, shocks)
    assert contrib[RiskFactor.IR_KES_GENERIC] == Decimal("-140000")
    assert contrib[RiskFactor.FX_USDKES] == Decimal("1950000")


def _test_apply_scenario_skips_unmatched_factors():
    eng = SensitivityEngine()
    sens = (
        Sensitivity(
            RiskFactor.IR_KES_GENERIC,
            SensitivityType.DV01,
            Decimal("700"), units="KES/bp"),
    )
    shocks = {
        RiskFactor.FX_USDKES: (Decimal("15"), "RELATIVE_PCT"),
    }
    pnl = eng.apply_scenario_pnl(sens, shocks)
    assert pnl == Decimal("0")


def self_test() -> None:
    import sys
    tests = [
        _test_dv01_simple_long_bond,
        _test_dv01_with_convexity,
        _test_dv01_zero_duration_zero_delta,
        _test_dv01_rejects_non_ir_factor,
        _test_fx_delta_long_position,
        _test_fx_delta_short_position,
        _test_fx_delta_rejects_non_fx_factor,
        _test_fx_delta_rejects_non_positive_spot,
        _test_equity_delta_with_beta,
        _test_aggregate_by_factor_and_class,
        _test_apply_scenario_pnl_dv01_loss_on_rate_up,
        _test_apply_scenario_pnl_fx_gain_on_appreciation,
        _test_per_factor_contribution_breakdown,
        _test_apply_scenario_skips_unmatched_factors,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ market_risk_sensitivities self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for n, m in failed:
            print(f"  - {n}: {m}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ market_risk_sensitivities self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

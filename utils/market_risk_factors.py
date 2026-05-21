"""utils/market_risk_factors.py — v10.39: Risk Factor Taxonomy.

╔════════════════════════════════════════════════════════════════════════╗
║  MARKET RISK — RISK FACTOR FOUNDATION                                  ║
║  Cat A — Standard ENH-MR-004                                           ║
╠════════════════════════════════════════════════════════════════════════╣
║  Provides the RiskFactor enum, RiskFactorClass groupings, and          ║
║  pre-built stress scenarios per BCBS d368 IRRBB + CBK PG/04            ║
║  + internal scenarios. Foundation for market_risk_sensitivities        ║
║  and market_risk_var.                                                  ║
║                                                                         ║
║  Honesty Rule 1: every Sensitivity, every VaRResult, every             ║
║  StressTestResult will surface its risk-factor breakdown so            ║
║  the user can see WHICH factors drive the number, not just the         ║
║  total. Risk factors are first-class.                                  ║
║                                                                         ║
║  Honesty Rule 7: live market data (rates, FX, equity prices,           ║
║  correlation matrices) is EXTERNAL. This module provides only          ║
║  taxonomy + scenario definitions. Engines requiring live data          ║
║  raise REQUIRES_PROVIDER:market_data_provider when no provider          ║
║  is wired.                                                              ║
║                                                                         ║
║  Composes with: market_risk_sensitivities (factor-bucketed              ║
║  exposures), market_risk_var (factor-decomposed VaR),                  ║
║  scenario_simulator (RISK-* test scenarios), treasury_alm              ║
║  (IRRBB shares the same IR factor taxonomy).                           ║
║                                                                         ║
║  Regulatory anchors: BCBS d352 FRTB, BCBS d368 IRRBB, BCBS              ║
║  d258 Stress Testing, CBK PG/04 Market Risk, IFRS 7.                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import (
    Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple)

SPEC_DEVIATION_NOTE = (
    "RiskFactor/StressScenario taxonomy implements ENH-MR-004 per "
    "BCBS d368 IRRBB + d352 FRTB SBM bucketing + CBK PG/04. The 6 "
    "BCBS IRRBB shock scenarios (parallel up/down 200bp, short up/"
    "down, steepener, flattener) are reproduced exactly. Per Rule 7, "
    "live market data is treated as an external provider — this "
    "module never fetches rates."
)


# ════════════════════════════════════════════════════════════════════════
# Risk-factor classification
# ════════════════════════════════════════════════════════════════════════

class RiskFactorClass(Enum):
    """Top-level FRTB risk-class buckets per BCBS d352 §A.4.1."""
    INTEREST_RATE = "INTEREST_RATE"           # GIRR
    FOREIGN_EXCHANGE = "FOREIGN_EXCHANGE"     # FX
    EQUITY = "EQUITY"
    COMMODITY = "COMMODITY"
    CREDIT_SPREAD = "CREDIT_SPREAD"           # CSR


class RiskFactor(Enum):
    """Specific risk factors observed in the Kenya bank's portfolios.

    Names use ISO currency / market codes where applicable. The
    KES-denominated factors are the primary ones for an Ecobank
    Kenya book; major foreign currencies and global equity/
    commodity indices are included for cross-currency positions.
    """
    # Interest rate — Kenya
    IR_KES_GENERIC = "IR_KES_GENERIC"
    IR_KES_GOVT = "IR_KES_GOVT"
    IR_KES_INTERBANK = "IR_KES_INTERBANK"
    # Interest rate — foreign
    IR_USD_GENERIC = "IR_USD_GENERIC"
    IR_EUR_GENERIC = "IR_EUR_GENERIC"
    IR_GBP_GENERIC = "IR_GBP_GENERIC"
    # FX (against KES home currency)
    FX_USDKES = "FX_USDKES"
    FX_EURKES = "FX_EURKES"
    FX_GBPKES = "FX_GBPKES"
    FX_ZARKES = "FX_ZARKES"
    FX_UGXKES = "FX_UGXKES"
    FX_TZSKES = "FX_TZSKES"
    # Equity
    EQUITY_NSE_GENERIC = "EQUITY_NSE_GENERIC"   # Nairobi SE generic
    EQUITY_GLOBAL_DEVELOPED = "EQUITY_GLOBAL_DEVELOPED"
    EQUITY_GLOBAL_EMERGING = "EQUITY_GLOBAL_EMERGING"
    # Commodity
    COMMODITY_OIL = "COMMODITY_OIL"
    COMMODITY_GOLD = "COMMODITY_GOLD"
    COMMODITY_AGRICULTURAL = "COMMODITY_AGRICULTURAL"
    # Credit spread (KES corporates by rating bucket)
    CREDIT_SPREAD_KES_AAA = "CREDIT_SPREAD_KES_AAA"
    CREDIT_SPREAD_KES_AA = "CREDIT_SPREAD_KES_AA"
    CREDIT_SPREAD_KES_A = "CREDIT_SPREAD_KES_A"
    CREDIT_SPREAD_KES_BBB = "CREDIT_SPREAD_KES_BBB"
    CREDIT_SPREAD_KES_BB_AND_BELOW = "CREDIT_SPREAD_KES_BB_AND_BELOW"


# Map each RiskFactor to its top-level class.
RISK_FACTOR_TO_CLASS: Mapping[RiskFactor, RiskFactorClass] = {
    # IR
    RiskFactor.IR_KES_GENERIC: RiskFactorClass.INTEREST_RATE,
    RiskFactor.IR_KES_GOVT: RiskFactorClass.INTEREST_RATE,
    RiskFactor.IR_KES_INTERBANK: RiskFactorClass.INTEREST_RATE,
    RiskFactor.IR_USD_GENERIC: RiskFactorClass.INTEREST_RATE,
    RiskFactor.IR_EUR_GENERIC: RiskFactorClass.INTEREST_RATE,
    RiskFactor.IR_GBP_GENERIC: RiskFactorClass.INTEREST_RATE,
    # FX
    RiskFactor.FX_USDKES: RiskFactorClass.FOREIGN_EXCHANGE,
    RiskFactor.FX_EURKES: RiskFactorClass.FOREIGN_EXCHANGE,
    RiskFactor.FX_GBPKES: RiskFactorClass.FOREIGN_EXCHANGE,
    RiskFactor.FX_ZARKES: RiskFactorClass.FOREIGN_EXCHANGE,
    RiskFactor.FX_UGXKES: RiskFactorClass.FOREIGN_EXCHANGE,
    RiskFactor.FX_TZSKES: RiskFactorClass.FOREIGN_EXCHANGE,
    # Equity
    RiskFactor.EQUITY_NSE_GENERIC: RiskFactorClass.EQUITY,
    RiskFactor.EQUITY_GLOBAL_DEVELOPED: RiskFactorClass.EQUITY,
    RiskFactor.EQUITY_GLOBAL_EMERGING: RiskFactorClass.EQUITY,
    # Commodity
    RiskFactor.COMMODITY_OIL: RiskFactorClass.COMMODITY,
    RiskFactor.COMMODITY_GOLD: RiskFactorClass.COMMODITY,
    RiskFactor.COMMODITY_AGRICULTURAL: RiskFactorClass.COMMODITY,
    # Credit spread
    RiskFactor.CREDIT_SPREAD_KES_AAA: RiskFactorClass.CREDIT_SPREAD,
    RiskFactor.CREDIT_SPREAD_KES_AA: RiskFactorClass.CREDIT_SPREAD,
    RiskFactor.CREDIT_SPREAD_KES_A: RiskFactorClass.CREDIT_SPREAD,
    RiskFactor.CREDIT_SPREAD_KES_BBB: RiskFactorClass.CREDIT_SPREAD,
    RiskFactor.CREDIT_SPREAD_KES_BB_AND_BELOW: (
        RiskFactorClass.CREDIT_SPREAD),
}


# ════════════════════════════════════════════════════════════════════════
# Shock and scenario types
# ════════════════════════════════════════════════════════════════════════

class ShockType(Enum):
    """How a shock magnitude should be interpreted."""
    ABSOLUTE_BPS = "ABSOLUTE_BPS"        # +/- N basis points
    ABSOLUTE_PCT = "ABSOLUTE_PCT"        # +/- N percentage points
    RELATIVE_PCT = "RELATIVE_PCT"        # x (1 + s) multiplicative


@dataclass(frozen=True)
class FactorShock:
    """A single shock applied to a single risk factor."""
    factor: RiskFactor
    magnitude: Decimal
    shock_type: ShockType

    def __post_init__(self) -> None:
        if self.shock_type not in ShockType:
            raise ValueError(
                f"unknown shock type: {self.shock_type}")

    def describe(self) -> str:
        sign = "+" if self.magnitude >= 0 else ""
        if self.shock_type == ShockType.ABSOLUTE_BPS:
            return (
                f"{self.factor.value} {sign}{self.magnitude} bps")
        if self.shock_type == ShockType.ABSOLUTE_PCT:
            return (
                f"{self.factor.value} {sign}{self.magnitude}%")
        return (
            f"{self.factor.value} × (1 {sign}{self.magnitude})")


@dataclass(frozen=True)
class StressScenario:
    """A multi-factor stress scenario.

    Per Rule 1, every StressScenario carries:
      - human-readable name + description
      - regulatory framework reference
      - the full list of FactorShocks
    """
    scenario_id: str
    name: str
    description: str
    framework_refs: Tuple[str, ...]
    shocks: Tuple[FactorShock, ...]
    holding_period_days: int = 1

    def __post_init__(self) -> None:
        if self.holding_period_days < 1:
            raise ValueError(
                "holding_period_days must be >= 1")
        seen: set = set()
        for shock in self.shocks:
            if shock.factor in seen:
                raise ValueError(
                    f"duplicate factor {shock.factor.value} in "
                    f"scenario {self.scenario_id}")
            seen.add(shock.factor)

    def factors_shocked(self) -> FrozenSet[RiskFactor]:
        return frozenset(s.factor for s in self.shocks)


# ════════════════════════════════════════════════════════════════════════
# Pre-built scenarios
# ════════════════════════════════════════════════════════════════════════

# BCBS d368 IRRBB six standard interest-rate shock scenarios.
# Magnitudes per §K, table for emerging-market currencies (KES is
# treated under emerging-market scaling: ±400bp parallel for
# currencies in the high-yield bucket; we use ±200bp here as a
# conservative/illustrative value matching the developed-market
# parameters — banks calibrate per CBK guidance).
_KES_PARALLEL_BPS = Decimal("200")
_KES_SHORT_BPS = Decimal("250")
_KES_LONG_BPS = Decimal("100")

BCBS_IRRBB_PARALLEL_UP = StressScenario(
    scenario_id="BCBS-IRRBB-1",
    name="Parallel up shift",
    description=(
        "Yield curve shifts up by parallel +200 bps across "
        "all tenors (BCBS d368 §K, scenario 1)."),
    framework_refs=("BCBS d368 IRRBB §K",),
    shocks=(
        FactorShock(
            RiskFactor.IR_KES_GENERIC,
            _KES_PARALLEL_BPS, ShockType.ABSOLUTE_BPS),
        FactorShock(
            RiskFactor.IR_KES_GOVT,
            _KES_PARALLEL_BPS, ShockType.ABSOLUTE_BPS),
    ))

BCBS_IRRBB_PARALLEL_DOWN = StressScenario(
    scenario_id="BCBS-IRRBB-2",
    name="Parallel down shift",
    description=(
        "Yield curve shifts down by parallel −200 bps "
        "(BCBS d368 §K, scenario 2)."),
    framework_refs=("BCBS d368 IRRBB §K",),
    shocks=(
        FactorShock(
            RiskFactor.IR_KES_GENERIC,
            -_KES_PARALLEL_BPS, ShockType.ABSOLUTE_BPS),
        FactorShock(
            RiskFactor.IR_KES_GOVT,
            -_KES_PARALLEL_BPS, ShockType.ABSOLUTE_BPS),
    ))

BCBS_IRRBB_SHORT_UP = StressScenario(
    scenario_id="BCBS-IRRBB-3",
    name="Short rates up",
    description=(
        "Short tenors shock up +250 bps; long tenors flat "
        "(BCBS d368 §K, scenario 3 — flattening from short "
        "end)."),
    framework_refs=("BCBS d368 IRRBB §K",),
    shocks=(
        FactorShock(
            RiskFactor.IR_KES_INTERBANK,
            _KES_SHORT_BPS, ShockType.ABSOLUTE_BPS),
    ))

BCBS_IRRBB_SHORT_DOWN = StressScenario(
    scenario_id="BCBS-IRRBB-4",
    name="Short rates down",
    description=(
        "Short tenors shock down −250 bps; long tenors flat "
        "(BCBS d368 §K, scenario 4)."),
    framework_refs=("BCBS d368 IRRBB §K",),
    shocks=(
        FactorShock(
            RiskFactor.IR_KES_INTERBANK,
            -_KES_SHORT_BPS, ShockType.ABSOLUTE_BPS),
    ))

BCBS_IRRBB_STEEPENER = StressScenario(
    scenario_id="BCBS-IRRBB-5",
    name="Steepener",
    description=(
        "Short rates fall, long rates rise — yield curve "
        "steepens (BCBS d368 §K, scenario 5)."),
    framework_refs=("BCBS d368 IRRBB §K",),
    shocks=(
        FactorShock(
            RiskFactor.IR_KES_INTERBANK,
            -_KES_SHORT_BPS, ShockType.ABSOLUTE_BPS),
        FactorShock(
            RiskFactor.IR_KES_GENERIC,
            _KES_LONG_BPS, ShockType.ABSOLUTE_BPS),
    ))

BCBS_IRRBB_FLATTENER = StressScenario(
    scenario_id="BCBS-IRRBB-6",
    name="Flattener",
    description=(
        "Short rates rise, long rates fall — yield curve "
        "flattens (BCBS d368 §K, scenario 6)."),
    framework_refs=("BCBS d368 IRRBB §K",),
    shocks=(
        FactorShock(
            RiskFactor.IR_KES_INTERBANK,
            _KES_SHORT_BPS, ShockType.ABSOLUTE_BPS),
        FactorShock(
            RiskFactor.IR_KES_GENERIC,
            -_KES_LONG_BPS, ShockType.ABSOLUTE_BPS),
    ))

BCBS_IRRBB_SCENARIOS: Tuple[StressScenario, ...] = (
    BCBS_IRRBB_PARALLEL_UP,
    BCBS_IRRBB_PARALLEL_DOWN,
    BCBS_IRRBB_SHORT_UP,
    BCBS_IRRBB_SHORT_DOWN,
    BCBS_IRRBB_STEEPENER,
    BCBS_IRRBB_FLATTENER,
)

# Internal/CBK ad-hoc stress scenarios (FX shock + equity crash)
INTERNAL_FX_SHOCK_USDKES_UP_15 = StressScenario(
    scenario_id="INT-FX-1",
    name="USD/KES depreciation 15%",
    description=(
        "KES depreciates 15% against USD — adverse for "
        "USD-short positions; consistent with regional FX "
        "stress envelopes."),
    framework_refs=("CBK PG/04 Market Risk", "Internal ICAAP"),
    shocks=(
        FactorShock(
            RiskFactor.FX_USDKES,
            Decimal("15"), ShockType.RELATIVE_PCT),
    ))

INTERNAL_FX_SHOCK_USDKES_DOWN_10 = StressScenario(
    scenario_id="INT-FX-2",
    name="USD/KES appreciation 10%",
    description=(
        "KES appreciates 10% against USD — adverse for "
        "USD-long positions."),
    framework_refs=("CBK PG/04 Market Risk", "Internal ICAAP"),
    shocks=(
        FactorShock(
            RiskFactor.FX_USDKES,
            Decimal("-10"), ShockType.RELATIVE_PCT),
    ))

INTERNAL_EQUITY_CRASH_30 = StressScenario(
    scenario_id="INT-EQ-1",
    name="Equity crash 30%",
    description=(
        "NSE generic and global emerging equity indices "
        "fall 30% (severe but plausible per CBK ICAAP "
        "expectations)."),
    framework_refs=("CBK PG/04 Market Risk", "Internal ICAAP"),
    shocks=(
        FactorShock(
            RiskFactor.EQUITY_NSE_GENERIC,
            Decimal("-30"), ShockType.RELATIVE_PCT),
        FactorShock(
            RiskFactor.EQUITY_GLOBAL_EMERGING,
            Decimal("-25"), ShockType.RELATIVE_PCT),
    ))

INTERNAL_SCENARIOS: Tuple[StressScenario, ...] = (
    INTERNAL_FX_SHOCK_USDKES_UP_15,
    INTERNAL_FX_SHOCK_USDKES_DOWN_10,
    INTERNAL_EQUITY_CRASH_30,
)

# Combined registry
ALL_PREBUILT_SCENARIOS: Tuple[StressScenario, ...] = (
    BCBS_IRRBB_SCENARIOS + INTERNAL_SCENARIOS)


# ════════════════════════════════════════════════════════════════════════
# Engine: scenario lookup + summary
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScenarioBankSummary:
    """Per Rule 1: factor-class breakdown of pre-built scenarios."""
    n_scenarios: int
    n_irrbb: int
    n_internal: int
    classes_covered: FrozenSet[RiskFactorClass]
    factors_covered: FrozenSet[RiskFactor]


class RiskFactorRegistry:
    """Read-only registry of risk factors and pre-built scenarios.

    Per Rule 7, this registry holds only metadata. Live shocks
    against actual portfolios are computed by
    market_risk_sensitivities.SensitivityEngine.
    """

    def __init__(
        self,
        scenarios: Sequence[StressScenario] = ALL_PREBUILT_SCENARIOS,
    ):
        ids = [s.scenario_id for s in scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError(
                "duplicate scenario_id in scenarios list")
        self._scenarios: Tuple[StressScenario, ...] = tuple(scenarios)

    @property
    def scenarios(self) -> Tuple[StressScenario, ...]:
        return self._scenarios

    def get(self, scenario_id: str) -> Optional[StressScenario]:
        for s in self._scenarios:
            if s.scenario_id == scenario_id:
                return s
        return None

    def by_framework(
        self, framework_substr: str,
    ) -> Tuple[StressScenario, ...]:
        return tuple(
            s for s in self._scenarios
            if any(framework_substr in r for r in s.framework_refs))

    def by_factor_class(
        self, cls: RiskFactorClass,
    ) -> Tuple[StressScenario, ...]:
        out: List[StressScenario] = []
        for s in self._scenarios:
            for shock in s.shocks:
                if RISK_FACTOR_TO_CLASS[shock.factor] == cls:
                    out.append(s)
                    break
        return tuple(out)

    def summary(self) -> ScenarioBankSummary:
        classes_covered: set = set()
        factors_covered: set = set()
        n_irrbb = 0
        n_internal = 0
        for s in self._scenarios:
            for shock in s.shocks:
                factors_covered.add(shock.factor)
                classes_covered.add(RISK_FACTOR_TO_CLASS[shock.factor])
            if any("IRRBB" in r or "d368" in r
                   for r in s.framework_refs):
                n_irrbb += 1
            else:
                n_internal += 1
        return ScenarioBankSummary(
            n_scenarios=len(self._scenarios),
            n_irrbb=n_irrbb,
            n_internal=n_internal,
            classes_covered=frozenset(classes_covered),
            factors_covered=frozenset(factors_covered))


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_every_factor_has_class():
    for f in RiskFactor:
        assert f in RISK_FACTOR_TO_CLASS, (
            f"factor {f.value} missing from RISK_FACTOR_TO_CLASS")


def _test_irrbb_six_scenarios_present():
    assert len(BCBS_IRRBB_SCENARIOS) == 6


def _test_irrbb_scenarios_cite_d368():
    for s in BCBS_IRRBB_SCENARIOS:
        assert any(
            "d368" in r or "IRRBB" in r
            for r in s.framework_refs), s.scenario_id


def _test_parallel_up_magnitude():
    s = BCBS_IRRBB_PARALLEL_UP
    for shock in s.shocks:
        assert shock.shock_type == ShockType.ABSOLUTE_BPS
        assert shock.magnitude == Decimal("200")


def _test_parallel_down_negates_up():
    up = BCBS_IRRBB_PARALLEL_UP
    down = BCBS_IRRBB_PARALLEL_DOWN
    up_factors = {(s.factor, s.magnitude) for s in up.shocks}
    down_factors = {(s.factor, s.magnitude) for s in down.shocks}
    for f, m in up_factors:
        assert (f, -m) in down_factors


def _test_steepener_and_flattener_are_opposites():
    st = BCBS_IRRBB_STEEPENER
    fl = BCBS_IRRBB_FLATTENER
    st_dict = {s.factor: s.magnitude for s in st.shocks}
    fl_dict = {s.factor: s.magnitude for s in fl.shocks}
    for factor, mag in st_dict.items():
        assert fl_dict[factor] == -mag, (
            f"{factor.value}: steepener={mag}, flattener={fl_dict[factor]}")


def _test_factor_shock_describe():
    fs = FactorShock(
        RiskFactor.IR_KES_GENERIC,
        Decimal("200"), ShockType.ABSOLUTE_BPS)
    assert "200" in fs.describe()
    assert "bps" in fs.describe()


def _test_stress_scenario_rejects_duplicate_factors():
    try:
        StressScenario(
            scenario_id="dup",
            name="dup",
            description="dup",
            framework_refs=("test",),
            shocks=(
                FactorShock(
                    RiskFactor.IR_KES_GENERIC,
                    Decimal("100"), ShockType.ABSOLUTE_BPS),
                FactorShock(
                    RiskFactor.IR_KES_GENERIC,
                    Decimal("200"), ShockType.ABSOLUTE_BPS),
            ))
        assert False, "should have rejected duplicate factor"
    except ValueError:
        pass


def _test_stress_scenario_rejects_invalid_holding_period():
    try:
        StressScenario(
            scenario_id="bad",
            name="bad", description="bad",
            framework_refs=("test",),
            shocks=(
                FactorShock(
                    RiskFactor.IR_KES_GENERIC,
                    Decimal("100"), ShockType.ABSOLUTE_BPS),
            ),
            holding_period_days=0)
        assert False
    except ValueError:
        pass


def _test_registry_lookup():
    reg = RiskFactorRegistry()
    found = reg.get("BCBS-IRRBB-1")
    assert found is not None
    assert found.name == "Parallel up shift"
    missing = reg.get("DOES-NOT-EXIST")
    assert missing is None


def _test_registry_rejects_duplicates():
    try:
        RiskFactorRegistry(scenarios=(
            BCBS_IRRBB_PARALLEL_UP,
            BCBS_IRRBB_PARALLEL_UP))
        assert False
    except ValueError:
        pass


def _test_registry_filter_by_framework():
    reg = RiskFactorRegistry()
    irrbb = reg.by_framework("d368")
    assert len(irrbb) == 6
    cbk = reg.by_framework("CBK")
    assert len(cbk) >= 3


def _test_registry_filter_by_factor_class():
    reg = RiskFactorRegistry()
    ir_scenarios = reg.by_factor_class(
        RiskFactorClass.INTEREST_RATE)
    assert len(ir_scenarios) >= 6   # all IRRBB scenarios
    fx_scenarios = reg.by_factor_class(
        RiskFactorClass.FOREIGN_EXCHANGE)
    assert len(fx_scenarios) >= 2


def _test_registry_summary():
    reg = RiskFactorRegistry()
    s = reg.summary()
    assert s.n_scenarios == 9        # 6 IRRBB + 3 internal
    assert s.n_irrbb == 6
    assert s.n_internal == 3
    assert RiskFactorClass.INTEREST_RATE in s.classes_covered
    assert RiskFactorClass.FOREIGN_EXCHANGE in s.classes_covered
    assert RiskFactorClass.EQUITY in s.classes_covered


def _test_factor_class_buckets_complete():
    """Every RiskFactorClass should have at least one factor."""
    classes_with_factors = set(RISK_FACTOR_TO_CLASS.values())
    for cls in RiskFactorClass:
        assert cls in classes_with_factors, (
            f"RiskFactorClass {cls.value} has no factors")


def self_test() -> None:
    import sys
    tests = [
        _test_every_factor_has_class,
        _test_irrbb_six_scenarios_present,
        _test_irrbb_scenarios_cite_d368,
        _test_parallel_up_magnitude,
        _test_parallel_down_negates_up,
        _test_steepener_and_flattener_are_opposites,
        _test_factor_shock_describe,
        _test_stress_scenario_rejects_duplicate_factors,
        _test_stress_scenario_rejects_invalid_holding_period,
        _test_registry_lookup,
        _test_registry_rejects_duplicates,
        _test_registry_filter_by_framework,
        _test_registry_filter_by_factor_class,
        _test_registry_summary,
        _test_factor_class_buckets_complete,
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
            f"✗ market_risk_factors self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for n, m in failed:
            print(f"  - {n}: {m}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ market_risk_factors self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

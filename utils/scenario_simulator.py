"""utils/scenario_simulator.py — v10.36: Scenario Simulation Harness.

╔════════════════════════════════════════════════════════════════════════╗
║  SCENARIO SIMULATION HARNESS — Cross-arc executable scenarios          ║
║  Cat A — feeds regression coverage + ML training signals               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements the scenario-simulation foundation requested in the        ║
║  Comprehensive Scenario Simulation & Safe Learning Framework.          ║
║                                                                         ║
║  Each Scenario carries:                                                 ║
║    - id + category + description                                       ║
║    - setup() — initialize the engines under test                       ║
║    - actions() — drive the engines through events                       ║
║    - expectations — what the system should produce                    ║
║                                                                         ║
║  ScenarioRunner orchestrates: setup → actions → assertion → result.    ║
║  Results are deterministic (PASS / WARNING / FAIL / NO_DATA).         ║
║                                                                         ║
║  Scenarios compose with all v10.18+ engines without mutating them.     ║
║  Every scenario invocation produces a ScenarioResult that can be       ║
║  hashed into the audit log via v10.23-27 audit_core.                   ║
║                                                                         ║
║  Honesty Rule 1: every ScenarioResult surfaces observed vs expected   ║
║  + which assertion fired + scenario notes. Failures surface specific  ║
║  numbers, not just bool.                                               ║
║  Honesty Rule 7: scenarios with external dependencies (market feeds, ║
║  ML providers) declare them in `requires_providers`. Runner skips    ║
║  scenarios whose requires_providers aren't satisfied rather than      ║
║  fabricating provider responses.                                       ║
║                                                                         ║
║  Composes with: model_governance (every ML decision in a scenario     ║
║  registers with the governance engine), audit_core (every breach     ║
║  emits an audit entry), virtual_bank_core (deterministic synthetic    ║
║  data for scenarios that need a bank fixture).                       ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "ScenarioSimulator implements the v10.36 scenario harness "
    "foundation. Each scenario is a deterministic test of platform "
    "behavior — setup→actions→assertion. Per Rule 7, scenarios "
    "needing external providers declare them in requires_providers; "
    "runner skips unsatisfied scenarios cleanly. Per Rule 1, every "
    "ScenarioResult surfaces observed + expected + status + notes."
)


# ════════════════════════════════════════════════════════════════════════
# Taxonomy
# ════════════════════════════════════════════════════════════════════════

class ScenarioCategory(Enum):
    """Per the v10.36 framework taxonomy."""
    CUSTOMER_LIFECYCLE = "CUSTOMER_LIFECYCLE"
    CREDIT_LENDING = "CREDIT_LENDING"
    DEPOSIT_LIQUIDITY = "DEPOSIT_LIQUIDITY"
    PERFORMANCE_MGMT = "PERFORMANCE_MGMT"
    RISK_COMPLIANCE = "RISK_COMPLIANCE"
    OPERATIONS_TREASURY = "OPERATIONS_TREASURY"
    STRATEGY_CAMPAIGNS = "STRATEGY_CAMPAIGNS"
    FRAUD_SECURITY = "FRAUD_SECURITY"
    RECOVERY_DISASTER = "RECOVERY_DISASTER"
    COMPETITOR_MARKET = "COMPETITOR_MARKET"


class ScenarioStatus(Enum):
    """Outcome of running one scenario."""
    PASS = "PASS"                    # all assertions met
    WARNING = "WARNING"              # within tolerance bands
    FAIL = "FAIL"                    # assertion violated
    SKIPPED = "SKIPPED"              # requires_providers unsatisfied
    ERROR = "ERROR"                  # exception in setup/actions


# ════════════════════════════════════════════════════════════════════════
# Result types
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class AssertionResult:
    """One named assertion outcome within a scenario."""
    assertion_id: str
    description: str
    expected: Any
    observed: Any
    matched: bool
    notes: str = ""


@dataclass(frozen=True)
class ScenarioResult:
    """Aggregated outcome of one scenario invocation."""
    scenario_id: str
    category: ScenarioCategory
    status: ScenarioStatus
    assertions: Tuple[AssertionResult, ...]
    n_passed: int
    n_failed: int
    notes: str = ""
    runtime_summary: str = ""

    def first_failure(self) -> Optional[AssertionResult]:
        for a in self.assertions:
            if not a.matched:
                return a
        return None


# ════════════════════════════════════════════════════════════════════════
# Scenario contract
# ════════════════════════════════════════════════════════════════════════

# Engine bundle passed to scenario callbacks
EngineBundle = Mapping[str, Any]

# Setup callback: receives bundle, returns nothing (mutates engines)
SetupFn = Callable[[EngineBundle], None]

# Actions callback: receives bundle, returns nothing
ActionsFn = Callable[[EngineBundle], None]

# Assertion callback: receives bundle, returns tuple of AssertionResult
AssertionsFn = Callable[[EngineBundle], Sequence[AssertionResult]]


@dataclass(frozen=True)
class Scenario:
    """A single executable scenario.

    Pure-function callbacks; the runner provides the engine bundle.
    """
    scenario_id: str
    category: ScenarioCategory
    description: str
    setup: SetupFn
    actions: ActionsFn
    assertions: AssertionsFn
    requires_engines: Tuple[str, ...]    # e.g., ("treasury_alm",)
    requires_providers: Tuple[str, ...] = ()    # e.g., ("ml_forecast",)
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Runner
# ════════════════════════════════════════════════════════════════════════

class ScenarioRunner:
    """Orchestrates scenario execution against a bundle of engines.

    Two modes:
      - shared: pass `engines=` dict; same engines reused across runs
        (state accumulates — useful for cross-scenario interactions).
      - isolated: pass `bundle_factory=` callable; called per
        scenario for fresh state (default for regression suites).
    """

    def __init__(
        self, *,
        engines: Optional[EngineBundle] = None,
        bundle_factory: Optional[Callable[[], EngineBundle]] = None,
    ):
        if engines is None and bundle_factory is None:
            raise ValueError(
                "ScenarioRunner requires either engines= or "
                "bundle_factory=")
        if engines is not None and bundle_factory is not None:
            raise ValueError(
                "ScenarioRunner takes engines OR bundle_factory, "
                "not both")
        self._factory = bundle_factory
        self.engines: EngineBundle = (
            engines if engines is not None else bundle_factory())
        self._results: Dict[str, ScenarioResult] = {}

    @property
    def results(self) -> Mapping[str, ScenarioResult]:
        return dict(self._results)

    def _check_requirements(
        self, scenario: Scenario,
    ) -> Optional[str]:
        """Returns an unsatisfied-reason string, or None if ready."""
        for engine_name in scenario.requires_engines:
            if engine_name not in self.engines:
                return f"missing engine: {engine_name}"
            if self.engines[engine_name] is None:
                return f"engine {engine_name} is None"
        for provider_name in scenario.requires_providers:
            # Providers are optional features on engines (e.g., the
            # ml_provider on TreasuryCashForecastingEngine)
            engine = self.engines.get("cash_forecasting")
            if (provider_name == "ml_forecast" and (
                engine is None
                or getattr(engine, "ml_provider", None) is None)):
                return f"missing provider: {provider_name}"
        return None

    def run(self, scenario: Scenario) -> ScenarioResult:
        """Execute one scenario; record result.

        In factory mode, a fresh engine bundle is created for this
        scenario — state from prior scenarios doesn't leak in.
        """
        if scenario.scenario_id in self._results:
            raise ValueError(
                f"scenario {scenario.scenario_id} already run")

        # Fresh bundle per scenario in factory mode
        if self._factory is not None:
            self.engines = self._factory()

        # Check requirements
        unmet = self._check_requirements(scenario)
        if unmet is not None:
            result = ScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                status=ScenarioStatus.SKIPPED,
                assertions=(),
                n_passed=0, n_failed=0,
                notes=f"skipped: {unmet}")
            self._results[scenario.scenario_id] = result
            return result

        # Run lifecycle with error capture
        try:
            scenario.setup(self.engines)
            scenario.actions(self.engines)
            asserts = tuple(scenario.assertions(self.engines))
        except Exception as e:
            result = ScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                status=ScenarioStatus.ERROR,
                assertions=(),
                n_passed=0, n_failed=0,
                notes=f"error: {type(e).__name__}: {e}")
            self._results[scenario.scenario_id] = result
            return result

        n_passed = sum(1 for a in asserts if a.matched)
        n_failed = len(asserts) - n_passed
        if n_failed == 0 and n_passed > 0:
            status = ScenarioStatus.PASS
        elif n_failed == 0 and n_passed == 0:
            status = ScenarioStatus.WARNING
        else:
            status = ScenarioStatus.FAIL

        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            category=scenario.category,
            status=status,
            assertions=asserts,
            n_passed=n_passed,
            n_failed=n_failed,
            notes=(
                f"{n_passed}/{len(asserts)} assertions passed"
                if asserts else "no assertions defined"))
        self._results[scenario.scenario_id] = result
        return result

    def run_all(
        self, scenarios: Sequence[Scenario],
    ) -> Tuple[ScenarioResult, ...]:
        """Run a list of scenarios. Order preserved."""
        out: List[ScenarioResult] = []
        for s in scenarios:
            if s.scenario_id in self._results:
                out.append(self._results[s.scenario_id])
            else:
                out.append(self.run(s))
        return tuple(out)

    # ── Reporting ──────────────────────────────────────────────────────
    def summary(self) -> Dict[str, Any]:
        """Roll-up across all run scenarios."""
        n_total = len(self._results)
        by_status: Dict[str, int] = {
            s.value: 0 for s in ScenarioStatus}
        by_category: Dict[str, Dict[str, int]] = {}
        for r in self._results.values():
            by_status[r.status.value] += 1
            cat = r.category.value
            if cat not in by_category:
                by_category[cat] = {
                    s.value: 0 for s in ScenarioStatus}
            by_category[cat][r.status.value] += 1
        return {
            "n_total": n_total,
            "by_status": by_status,
            "by_category": by_category,
            "n_failures": by_status.get("FAIL", 0),
        }

    def failures(self) -> Tuple[ScenarioResult, ...]:
        return tuple(
            r for r in self._results.values()
            if r.status == ScenarioStatus.FAIL)


# ════════════════════════════════════════════════════════════════════════
# Initial Treasury scenario library — exercises v10.33-v10.35 engines
# ════════════════════════════════════════════════════════════════════════

# Scenario LI‑01: LCR compliance under normal conditions
def _setup_lcr_compliant(engines: EngineBundle) -> None:
    from utils.treasury_alm import (HQLAPosition, HQLALevel, CashFlow)
    alm = engines["treasury_alm"]
    alm.register_hqla(HQLAPosition(
        position_id="lcr01-h1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("200000000"),
        currency="KES"))
    alm.add_outflow(CashFlow(
        flow_id="lcr01-o1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30))


def _actions_lcr_compute(engines: EngineBundle) -> None:
    engines["treasury_alm"].run_lcr(
        result_id="lcr01-r1", as_of_date="2026-05-01")


def _assertions_lcr_compliant(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    summary = engines["treasury_alm"].board_summary()
    lcr_pct = Decimal(summary["latest_lcr_pct"])
    return (
        AssertionResult(
            assertion_id="lcr01-a1",
            description="LCR ≥ 100% per Basel BCBS 188",
            expected=">= 100",
            observed=str(lcr_pct),
            matched=lcr_pct >= Decimal("100")),
        AssertionResult(
            assertion_id="lcr01-a2",
            description="LCR compliance flag is True",
            expected=True,
            observed=summary["latest_lcr_compliant"],
            matched=summary["latest_lcr_compliant"] is True),
    )


SCENARIO_LI_01_LCR_COMPLIANT = Scenario(
    scenario_id="LI-01",
    category=ScenarioCategory.DEPOSIT_LIQUIDITY,
    description=(
        "LCR compliance under normal conditions: 200M HQLA L1 + "
        "100M 30-day outflows → LCR 200% ≥ 100%."),
    setup=_setup_lcr_compliant,
    actions=_actions_lcr_compute,
    assertions=_assertions_lcr_compliant,
    requires_engines=("treasury_alm",))


# Scenario LI‑02: LCR breach when HQLA insufficient
def _setup_lcr_breach(engines: EngineBundle) -> None:
    from utils.treasury_alm import (HQLAPosition, HQLALevel, CashFlow)
    alm = engines["treasury_alm"]
    alm.register_hqla(HQLAPosition(
        position_id="lcr02-h1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("50000000"),       # insufficient
        currency="KES"))
    alm.add_outflow(CashFlow(
        flow_id="lcr02-o1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30))


def _actions_lcr_compute2(engines: EngineBundle) -> None:
    engines["treasury_alm"].run_lcr(
        result_id="lcr02-r1", as_of_date="2026-05-01")


def _assertions_lcr_breach(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    summary = engines["treasury_alm"].board_summary()
    return (
        AssertionResult(
            assertion_id="lcr02-a1",
            description="System detects LCR breach (compliant=False)",
            expected=False,
            observed=summary["latest_lcr_compliant"],
            matched=summary["latest_lcr_compliant"] is False),
    )


SCENARIO_LI_02_LCR_BREACH = Scenario(
    scenario_id="LI-02",
    category=ScenarioCategory.DEPOSIT_LIQUIDITY,
    description=(
        "LCR breach detection: 50M HQLA + 100M outflows → LCR 50% < "
        "100% → system must flag non-compliant."),
    setup=_setup_lcr_breach,
    actions=_actions_lcr_compute2,
    assertions=_assertions_lcr_breach,
    requires_engines=("treasury_alm",))


# Scenario IRRBB‑01: outlier detection on extreme position
def _setup_irrbb_outlier(engines: EngineBundle) -> None:
    from utils.treasury_alm import RatesGapPosition, MaturityBucket
    alm = engines["treasury_alm"]
    alm.register_rates_position(RatesGapPosition(
        position_id="irrbb01-p1",
        bucket=MaturityBucket.YEARS_5_PLUS,
        is_asset=True,
        notional=Decimal("10000000000"),    # 10B at 5y+
        currency="KES"))


def _actions_irrbb(engines: EngineBundle) -> None:
    alm = engines["treasury_alm"]
    alm.run_repricing_gap(
        result_id="irrbb01-g1", as_of_date="2026-05-01")
    alm.run_all_irrbb_scenarios(
        result_id_prefix="irrbb01",
        gap_result_id="irrbb01-g1",
        base_nii_kes=Decimal("100000000"),
        base_eve_kes=Decimal("0"),
        tier_1_capital_kes=Decimal("1000000000"),
        as_of_date="2026-05-01")


def _assertions_irrbb_outlier(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    outliers = engines["treasury_alm"].outlier_scenarios()
    return (
        AssertionResult(
            assertion_id="irrbb01-a1",
            description=(
                "Extreme 5y+ position triggers ≥1 BCBS 368 EVE "
                "outlier (>15% Tier 1)"),
            expected=">=1",
            observed=str(len(outliers)),
            matched=len(outliers) >= 1),
    )


SCENARIO_IRRBB_01 = Scenario(
    scenario_id="IRRBB-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "IRRBB outlier detection: 10B unhedged 5y+ asset vs 1B Tier 1 "
        "→ at least one Basel BCBS 368 scenario must flag outlier "
        "(ΔEVE > 15% Tier 1)."),
    setup=_setup_irrbb_outlier,
    actions=_actions_irrbb,
    assertions=_assertions_irrbb_outlier,
    requires_engines=("treasury_alm",))


# Scenario CAP‑01: CBK breach when Basel-compliant
def _setup_cap_cbk_breach(engines: EngineBundle) -> None:
    from utils.rwa_optimization import Exposure, AssetClass
    rwa = engines["rwa_optimization"]
    rwa.register_exposure(Exposure(
        exposure_id="cap01-e1", counterparty="A",
        asset_class=AssetClass.CORPORATE_UNRATED,
        on_bs_amount=Decimal("10000000000")))    # 10B RWA
    rwa.compute_all_rwa()


def _actions_cap(engines: EngineBundle) -> None:
    from utils.rwa_optimization import CapitalComponents
    rwa = engines["rwa_optimization"]
    capital = CapitalComponents(
        cet1_capital=Decimal("800000000"),    # 8% of 10B
        additional_t1_capital=Decimal("0"),
        tier_2_capital=Decimal("0"))
    rwa.compute_capital_ratios(
        result_id="cap01-c1", capital=capital,
        as_of_date="2026-05-01")


def _assertions_cap(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    summary = engines["rwa_optimization"].board_summary()
    cet1_pct = Decimal(summary["latest_cet1_pct"])
    return (
        AssertionResult(
            assertion_id="cap01-a1",
            description="CET1 8% passes Basel 4.5% min",
            expected=">= 4.5",
            observed=str(cet1_pct),
            matched=cet1_pct >= Decimal("4.5")),
        AssertionResult(
            assertion_id="cap01-a2",
            description="CET1 8% fails CBK PG/03 10.5% min",
            expected="< 10.5",
            observed=str(cet1_pct),
            matched=cet1_pct < Decimal("10.5")),
        AssertionResult(
            assertion_id="cap01-a3",
            description="System flags CBK non-compliance",
            expected=False,
            observed=summary["latest_cbk_compliant"],
            matched=summary["latest_cbk_compliant"] is False),
    )


SCENARIO_CAP_01_CBK_DUAL_THRESHOLD = Scenario(
    scenario_id="CAP-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "Dual capital threshold: 8% CET1 passes Basel 4.5% but fails "
        "CBK PG/03 10.5%. Dashboard must flag CBK breach even when "
        "Basel-compliant."),
    setup=_setup_cap_cbk_breach,
    actions=_actions_cap,
    assertions=_assertions_cap,
    requires_engines=("rwa_optimization",))


# Scenario FX‑01: net FX exposure aggregation
def _setup_fx_exposure(engines: EngineBundle) -> None:
    from utils.treasury_products import FXPosition, InstrumentType
    products = engines["treasury_products"]
    products.register_fx_position(FXPosition(
        position_id="fx01-p1",
        instrument_type=InstrumentType.FX_SPOT,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("5000000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01", is_long_base=True))
    products.register_fx_position(FXPosition(
        position_id="fx01-p2",
        instrument_type=InstrumentType.FX_SPOT,
        base_currency="USD", quote_currency="KES",
        notional_base=Decimal("2000000"),
        contract_rate=Decimal("130"),
        value_date="2026-05-01", is_long_base=False))


def _actions_fx_noop(engines: EngineBundle) -> None:
    pass


def _assertions_fx(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    net = engines["treasury_products"].net_fx_exposure("USD")
    return (
        AssertionResult(
            assertion_id="fx01-a1",
            description=(
                "Net USD = 5M long − 2M short = 3M long"),
            expected="3000000",
            observed=str(net),
            matched=net == Decimal("3000000")),
    )


SCENARIO_FX_01_NET_EXPOSURE = Scenario(
    scenario_id="FX-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "FX net exposure: 5M USD long + 2M USD short → 3M USD net "
        "long (CBK PG/17 forex limit reporting input)."),
    setup=_setup_fx_exposure,
    actions=_actions_fx_noop,
    assertions=_assertions_fx,
    requires_engines=("treasury_products",))


# Scenario NIM‑01: NIM decomposition correctness
def _setup_nim(engines: EngineBundle) -> None:
    pass    # FTPEngine starts empty


def _actions_nim(engines: EngineBundle) -> None:
    from utils.fund_transfer_pricing import FTPProductCategory
    ftp = engines["fund_transfer_pricing"]
    ftp.decompose_nim(
        decomposition_id="nim01-d1", product_id="L1",
        product_category=FTPProductCategory.LOAN_TERM,
        is_asset=True,
        customer_rate_pct=Decimal("15"),
        ftp_rate_pct=Decimal("10"))
    ftp.decompose_nim(
        decomposition_id="nim01-d2", product_id="DEP1",
        product_category=FTPProductCategory.FIXED_DEPOSIT,
        is_asset=False,
        customer_rate_pct=Decimal("5"),
        ftp_rate_pct=Decimal("8"))


def _assertions_nim(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    summary = engines["fund_transfer_pricing"].board_summary()
    return (
        AssertionResult(
            assertion_id="nim01-a1",
            description=(
                "Lending margin = customer 15% − FTP 10% = 5%"),
            expected="5.0000",
            observed=summary["sum_lending_spread_pct"],
            matched=(
                summary["sum_lending_spread_pct"] == "5.0000")),
        AssertionResult(
            assertion_id="nim01-a2",
            description=(
                "Funding margin = FTP 8% − customer 5% = 3%"),
            expected="3.0000",
            observed=summary["sum_funding_spread_pct"],
            matched=(
                summary["sum_funding_spread_pct"] == "3.0000")),
    )


SCENARIO_NIM_01_DECOMPOSITION = Scenario(
    scenario_id="NIM-01",
    category=ScenarioCategory.PERFORMANCE_MGMT,
    description=(
        "NIM decomposition: loan 15% − FTP 10% = 5% lending margin; "
        "deposit FTP 8% − customer 5% = 3% funding margin."),
    setup=_setup_nim,
    actions=_actions_nim,
    assertions=_assertions_nim,
    requires_engines=("fund_transfer_pricing",))


# Scenario DASH‑01: dashboard breach roll-up
def _setup_dash_breach(engines: EngineBundle) -> None:
    from utils.treasury_alm import (HQLAPosition, HQLALevel, CashFlow)
    alm = engines["treasury_alm"]
    alm.register_hqla(HQLAPosition(
        position_id="dash01-h1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("50000000"),
        currency="KES"))
    alm.add_outflow(CashFlow(
        flow_id="dash01-o1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30))
    alm.run_lcr(result_id="dash01-l1", as_of_date="2026-05-01")


def _actions_dash(engines: EngineBundle) -> None:
    dashboard = engines["treasury_dashboard"]
    dashboard.generate_daily_treasury(
        report_id="dash01-r1", as_of_date="2026-05-01")


def _assertions_dash(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.treasury_dashboard import SectionStatus
    dashboard = engines["treasury_dashboard"]
    report = dashboard._reports["dash01-r1"]
    return (
        AssertionResult(
            assertion_id="dash01-a1",
            description=(
                "LCR breach in upstream → dashboard overall_status = "
                "BREACH"),
            expected="BREACH",
            observed=report.overall_status.value,
            matched=(
                report.overall_status == SectionStatus.BREACH)),
    )


SCENARIO_DASH_01_BREACH_ROLLUP = Scenario(
    scenario_id="DASH-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "Dashboard breach roll-up: ALM has LCR breach → dashboard "
        "must surface overall_status BREACH."),
    setup=_setup_dash_breach,
    actions=_actions_dash,
    assertions=_assertions_dash,
    requires_engines=("treasury_alm", "treasury_dashboard"))


# Scenario CF‑01: cash forecast applies seasonality
def _setup_cf(engines: EngineBundle) -> None:
    from datetime import date, timedelta
    from utils.cash_forecasting import HistoricalDayNetFlow
    forecast = engines["cash_forecasting"]
    d = date(2026, 1, 1)
    for i in range(60):
        day = d + timedelta(days=i)
        base = Decimal("1000000")
        if day.weekday() >= 5:
            base = base * Decimal("0.5")    # weekend lower
        forecast.add_history(HistoricalDayNetFlow(
            observation_date=day.isoformat(),
            net_flow_kes=base))


def _actions_cf(engines: EngineBundle) -> None:
    forecast = engines["cash_forecasting"]
    forecast.fit_seasonality("cf01-s1")
    forecast.forecast(
        forecast_id="cf01-f1",
        start_date="2026-05-01",
        horizon_days=14,
        seasonality_model_id="cf01-s1")


def _assertions_cf(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    summary = engines["cash_forecasting"].board_summary()
    return (
        AssertionResult(
            assertion_id="cf01-a1",
            description=(
                "Forecast generated; ml_overlay_applied is False"),
            expected=1,
            observed=summary["n_forecasts"],
            matched=summary["n_forecasts"] == 1),
        AssertionResult(
            assertion_id="cf01-a2",
            description=(
                "ML provider not wired → ml_provider_wired=False"),
            expected=False,
            observed=summary["ml_provider_wired"],
            matched=summary["ml_provider_wired"] is False),
    )


SCENARIO_CF_01_FORECAST = Scenario(
    scenario_id="CF-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "Cash forecast generates 14-day projection from 60-day "
        "history; without ML provider, baseline forecast applies."),
    setup=_setup_cf,
    actions=_actions_cf,
    assertions=_assertions_cf,
    requires_engines=("cash_forecasting",))


# Scenario CF‑02: ML provider unwired raises REQUIRES_PROVIDER
def _setup_cf_ml(engines: EngineBundle) -> None:
    from datetime import date, timedelta
    from utils.cash_forecasting import HistoricalDayNetFlow
    forecast = engines["cash_forecasting"]
    d = date(2026, 1, 1)
    for i in range(60):
        day = d + timedelta(days=i)
        forecast.add_history(HistoricalDayNetFlow(
            observation_date=day.isoformat(),
            net_flow_kes=Decimal("1000000")))
    forecast.fit_seasonality("cf02-s1")


def _actions_cf_ml(engines: EngineBundle) -> None:
    """Try to use ML overlay without provider — expect ValueError."""
    pass    # actions deferred to assertions


def _assertions_cf_ml(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    forecast = engines["cash_forecasting"]
    raised = False
    msg = ""
    try:
        forecast.forecast_with_ml_overlay(
            forecast_id="cf02-f1",
            start_date="2026-05-01",
            horizon_days=7,
            seasonality_model_id="cf02-s1")
    except ValueError as e:
        raised = True
        msg = str(e)
    return (
        AssertionResult(
            assertion_id="cf02-a1",
            description=(
                "ML overlay without provider raises ValueError"),
            expected=True,
            observed=raised,
            matched=raised),
        AssertionResult(
            assertion_id="cf02-a2",
            description="Error mentions REQUIRES_PROVIDER",
            expected="contains 'REQUIRES_PROVIDER'",
            observed=msg,
            matched="REQUIRES_PROVIDER" in msg),
    )


SCENARIO_CF_02_ML_REQUIRES_PROVIDER = Scenario(
    scenario_id="CF-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "Per Rule 7: ML overlay forecast without wired provider "
        "raises REQUIRES_PROVIDER rather than fabricating."),
    setup=_setup_cf_ml,
    actions=_actions_cf_ml,
    assertions=_assertions_cf_ml,
    requires_engines=("cash_forecasting",))


# Scenario MODGOV‑01: model registration enforces governance
def _setup_modgov(engines: EngineBundle) -> None:
    pass


def _actions_modgov(engines: EngineBundle) -> None:
    from utils.model_governance import (
        Model, ModelTier, ModelType, ModelLifecycleState,
        EUAIActRiskCategory)
    gov = engines["model_governance"]
    gov.register_model(Model(
        model_id="mg01-m1",
        model_name="Test Tier 1 model",
        model_type=ModelType.OTHER,
        model_tier=ModelTier.TIER_1_HIGH,
        eu_ai_act_category=EUAIActRiskCategory.LIMITED_RISK,
        current_state=ModelLifecycleState.DEVELOPMENT,
        owner_business_unit="treasury",
        owner_user_id="test_user",
        development_date="2026-05-01"))


def _assertions_modgov(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    gov = engines["model_governance"]
    # Try common attr names; fall back to 0
    n_models = 0
    for attr_name in ("_models", "_registry", "models"):
        if hasattr(gov, attr_name):
            d = getattr(gov, attr_name)
            if isinstance(d, dict):
                n_models = len(d)
                break
    return (
        AssertionResult(
            assertion_id="mg01-a1",
            description="Model registered in governance engine",
            expected=">= 1",
            observed=str(n_models),
            matched=n_models >= 1),
    )


SCENARIO_MODGOV_01_REGISTRATION = Scenario(
    scenario_id="MODGOV-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "Tier 1 model registration enters governance registry "
        "(precondition for promotion to production)."),
    setup=_setup_modgov,
    actions=_actions_modgov,
    assertions=_assertions_modgov,
    requires_engines=("model_governance",))


# NOTE: an event-log-style scenario was originally planned here but
# v10.23-27 audit_core is structured around BCBS 239 / GRC controls +
# working papers (Control / WorkingPaper / ControlTestResult), not
# discrete event logging. Per Rule 7, the simulator does not invent
# an event-log API on top of the controls engine; the audit_core
# scenarios will be added when the controls/working-paper paths are
# exercised by future batches that produce control evidence.


# Cross-arc scenario: LCR breach propagates through ALM AND dashboard
def _setup_cross1(engines: EngineBundle) -> None:
    from utils.treasury_alm import (HQLAPosition, HQLALevel, CashFlow)
    alm = engines["treasury_alm"]
    alm.register_hqla(HQLAPosition(
        position_id="x01-h1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("50000000"),    # insufficient
        currency="KES"))
    alm.add_outflow(CashFlow(
        flow_id="x01-o1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30))


def _actions_cross1(engines: EngineBundle) -> None:
    alm = engines["treasury_alm"]
    dashboard = engines["treasury_dashboard"]
    # Detection
    alm.run_lcr(
        result_id="x01-l1", as_of_date="2026-05-01")
    # Reporting
    dashboard.generate_daily_treasury(
        report_id="x01-d1", as_of_date="2026-05-01")


def _assertions_cross1(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.treasury_dashboard import SectionStatus
    alm = engines["treasury_alm"]
    dashboard = engines["treasury_dashboard"]
    summary = alm.board_summary()
    report = dashboard._reports.get("x01-d1")
    return (
        AssertionResult(
            assertion_id="x01-a1",
            description="LCR breach detected in ALM",
            expected=False,
            observed=summary["latest_lcr_compliant"],
            matched=summary["latest_lcr_compliant"] is False),
        AssertionResult(
            assertion_id="x01-a2",
            description="Dashboard surfaces breach status",
            expected="BREACH",
            observed=(
                report.overall_status.value if report else "MISSING"),
            matched=(
                report is not None
                and report.overall_status == SectionStatus.BREACH)),
    )


SCENARIO_CROSS_01_LCR_FULL_PROPAGATION = Scenario(
    scenario_id="CROSS-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "End-to-end LCR breach propagation: ALM detects → dashboard "
        "rolls up. Tests that the v10.33-35 engine stack composes "
        "correctly under stress."),
    setup=_setup_cross1,
    actions=_actions_cross1,
    assertions=_assertions_cross1,
    requires_engines=(
        "treasury_alm", "treasury_dashboard"))


# Default initial library — focused on what's been built (v10.33-v10.35)
TREASURY_SCENARIO_LIBRARY: Tuple[Scenario, ...] = (
    SCENARIO_LI_01_LCR_COMPLIANT,
    SCENARIO_LI_02_LCR_BREACH,
    SCENARIO_IRRBB_01,
    SCENARIO_CAP_01_CBK_DUAL_THRESHOLD,
    SCENARIO_FX_01_NET_EXPOSURE,
    SCENARIO_NIM_01_DECOMPOSITION,
    SCENARIO_DASH_01_BREACH_ROLLUP,
    SCENARIO_CF_01_FORECAST,
    SCENARIO_CF_02_ML_REQUIRES_PROVIDER,
    SCENARIO_MODGOV_01_REGISTRATION,
    SCENARIO_CROSS_01_LCR_FULL_PROPAGATION,
)


# ════════════════════════════════════════════════════════════════════════
# v10.37 closure scenarios — exercise the 8 new Treasury standards
# ════════════════════════════════════════════════════════════════════════

# ISLAMIC-01: Murabaha Sharia compliance (ENH-239)
def _setup_islamic_compliant(engines: EngineBundle) -> None:
    from utils.islamic_treasury import (
        IslamicProduct, IslamicProductType)
    eng = engines["islamic_treasury"]
    eng.register_product(IslamicProduct(
        product_id="IT-MUR-01",
        product_type=IslamicProductType.MURABAHA,
        counterparty="Trade Co Ltd",
        principal_kes=Decimal("10000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("8"),
        underlying_asset_description="100 MT steel inventory",
        sharia_board_approval_date="2026-04-15",
        sharia_board_reference="SSB-2026-042",
        counterparty_business_sector="manufacturing"))


def _actions_islamic(engines: EngineBundle) -> None:
    engines["islamic_treasury"].value_all()


def _assertions_islamic_compliant(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.islamic_treasury import ShariaComplianceStatus
    eng = engines["islamic_treasury"]
    valuations = eng.value_all()
    return (
        AssertionResult(
            assertion_id="islam01-a1",
            description=(
                "Murabaha with disclosed markup + tangible asset + "
                "Sharia board approval → COMPLIANT"),
            expected="COMPLIANT",
            observed=valuations[0].sharia_compliance.value,
            matched=(
                valuations[0].sharia_compliance
                == ShariaComplianceStatus.COMPLIANT)),
        AssertionResult(
            assertion_id="islam01-a2",
            description=(
                "Markup 8% × 10M = 800K expected return"),
            expected="800000.00",
            observed=str(valuations[0].expected_return_kes),
            matched=(
                valuations[0].expected_return_kes
                == Decimal("800000.00"))),
    )


SCENARIO_ISLAMIC_01_COMPLIANT_MURABAHA = Scenario(
    scenario_id="ISLAMIC-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-239: Sharia-compliant Murabaha with disclosed cost-plus "
        "markup, tangible underlying asset, and Sharia Supervisory "
        "Board approval → COMPLIANT per AAOIFI Sharia Std 8."),
    setup=_setup_islamic_compliant,
    actions=_actions_islamic,
    assertions=_assertions_islamic_compliant,
    requires_engines=("islamic_treasury",))


# ISLAMIC-02: Haram industry detection (ENH-239)
def _setup_islamic_haram(engines: EngineBundle) -> None:
    from utils.islamic_treasury import (
        IslamicProduct, IslamicProductType)
    eng = engines["islamic_treasury"]
    eng.register_product(IslamicProduct(
        product_id="IT-MUR-02",
        product_type=IslamicProductType.MURABAHA,
        counterparty="Casino Co",
        principal_kes=Decimal("1000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("5"),
        underlying_asset_description="slot machines",
        counterparty_business_sector="gambling"))


def _assertions_islamic_haram(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.islamic_treasury import ShariaComplianceStatus
    eng = engines["islamic_treasury"]
    valuations = eng.value_all()
    return (
        AssertionResult(
            assertion_id="islam02-a1",
            description=(
                "Gambling counterparty → NON_COMPLIANT per "
                "PROHIBITED_INDUSTRIES"),
            expected="NON_COMPLIANT",
            observed=valuations[0].sharia_compliance.value,
            matched=(
                valuations[0].sharia_compliance
                == ShariaComplianceStatus.NON_COMPLIANT)),
    )


SCENARIO_ISLAMIC_02_HARAM_REJECTED = Scenario(
    scenario_id="ISLAMIC-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-239: Haram-industry counterparty (gambling) → "
        "NON_COMPLIANT, blocking funding. Sharia compliance is "
        "structurally enforced."),
    setup=_setup_islamic_haram,
    actions=_actions_islamic,
    assertions=_assertions_islamic_haram,
    requires_engines=("islamic_treasury",))


# AGENT-01: LiquidityBufferAgent generates URGENT on LCR breach (ENH-240)
def _setup_agent_lcr_breach(engines: EngineBundle) -> None:
    from utils.treasury_alm import (
        HQLAPosition, HQLALevel, CashFlow)
    alm = engines["treasury_alm"]
    alm.register_hqla(HQLAPosition(
        position_id="ag01-h1", asset_class="cash",
        level=HQLALevel.LEVEL_1,
        notional=Decimal("50000000"), currency="KES"))
    alm.add_outflow(CashFlow(
        flow_id="ag01-o1", direction="OUTFLOW",
        amount=Decimal("100000000"), bucket_days=30))
    alm.run_lcr(result_id="ag01-l1", as_of_date="2026-05-01")


def _actions_agent(engines: EngineBundle) -> None:
    from utils.treasury_agents import (
        AgentOrchestrator, LiquidityBufferAgent)
    o = AgentOrchestrator()
    o.register_agent(LiquidityBufferAgent())
    recs = o.run_all(
        engines={"treasury_alm": engines["treasury_alm"]},
        as_of_date="2026-05-01")
    engines["__agent_recs__"] = recs
    engines["__agent_orchestrator__"] = o


def _assertions_agent_urgent(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.treasury_agents import (
        RecommendationPriority, ApprovalStatus)
    recs = engines.get("__agent_recs__", ())
    o = engines.get("__agent_orchestrator__")
    return (
        AssertionResult(
            assertion_id="ag01-a1",
            description=(
                "LiquidityBufferAgent emits URGENT recommendation "
                "on LCR breach"),
            expected=">= 1 URGENT",
            observed=str(len([
                r for r in recs
                if r.priority == RecommendationPriority.URGENT])),
            matched=any(
                r.priority == RecommendationPriority.URGENT
                for r in recs)),
        AssertionResult(
            assertion_id="ag01-a2",
            description=(
                "Per Rule 7: recommendation lifecycle starts "
                "PENDING (human approval required)"),
            expected="PENDING",
            observed=(
                o.board_summary()["n_pending"] if o else 0),
            matched=(
                o is not None
                and o.board_summary()["n_pending"] >= 1)),
    )


SCENARIO_AGENT_01_LIQUIDITY_URGENT = Scenario(
    scenario_id="AGENT-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "ENH-240: LCR breach → LiquidityBufferAgent emits URGENT "
        "recommendation; lifecycle starts PENDING per Rule 7 "
        "human-approval requirement."),
    setup=_setup_agent_lcr_breach,
    actions=_actions_agent,
    assertions=_assertions_agent_urgent,
    requires_engines=("treasury_alm",))


# AGENT-02: Approval workflow PENDING → APPROVED → EXECUTED (ENH-240)
def _setup_agent_workflow(engines: EngineBundle) -> None:
    _setup_agent_lcr_breach(engines)


def _actions_agent_workflow(engines: EngineBundle) -> None:
    _actions_agent(engines)
    o = engines["__agent_orchestrator__"]
    recs = engines["__agent_recs__"]
    if recs:
        rid = recs[0].recommendation_id
        o.approve(
            rid, approver="treasurer",
            approved_at="2026-05-01T10:00:00Z")
        o.mark_executed(rid, at="2026-05-01T11:00:00Z")


def _assertions_agent_workflow(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.treasury_agents import ApprovalStatus
    o = engines.get("__agent_orchestrator__")
    return (
        AssertionResult(
            assertion_id="ag02-a1",
            description=(
                "After approve+execute, n_executed >= 1"),
            expected=">= 1",
            observed=(
                o.board_summary()["n_executed"] if o else 0),
            matched=(
                o is not None
                and o.board_summary()["n_executed"] >= 1)),
    )


SCENARIO_AGENT_02_APPROVAL_WORKFLOW = Scenario(
    scenario_id="AGENT-02",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "ENH-240: full approval workflow — agent emits PENDING → "
        "treasurer approves → marked EXECUTED. Per Rule 7, "
        "approval is structural; can't skip."),
    setup=_setup_agent_workflow,
    actions=_actions_agent_workflow,
    assertions=_assertions_agent_workflow,
    requires_engines=("treasury_alm",))


# CONN-01: KEPSS routing for KES domestic (ENH-TRS-R1+R5)
def _setup_conn(engines: EngineBundle) -> None:
    from utils.treasury_connectivity import (
        Connector, ConnectorType, MessageFormat)
    eng = engines["treasury_connectivity"]
    eng.register_connector(Connector(
        connector_id="conn-kepss",
        connector_type=ConnectorType.CENTRAL_BANK,
        counterparty_name="CBK KEPSS",
        region="KE",
        supported_formats=frozenset({MessageFormat.KEPSS})))
    eng.activate_connector(
        "conn-kepss", at="2026-05-01T10:00:00Z")


def _actions_conn(engines: EngineBundle) -> None:
    from utils.treasury_connectivity import (
        Message, MessageDirection, MessageFormat)
    eng = engines["treasury_connectivity"]
    msg = Message(
        message_id="msg-kepss-1",
        connector_id="conn-kepss",
        direction=MessageDirection.OUTBOUND,
        format=MessageFormat.KEPSS,
        payload_summary="payment 1M KES → counterparty",
        amount_kes=Decimal("1000000"))
    eng.send_message(message=msg)


def _assertions_conn(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    eng = engines["treasury_connectivity"]
    summary = eng.board_summary()
    return (
        AssertionResult(
            assertion_id="conn01-a1",
            description=(
                "KEPSS message routes successfully through CBK "
                "central-bank connector"),
            expected=1,
            observed=summary["n_messages_routed"],
            matched=summary["n_messages_routed"] == 1),
    )


SCENARIO_CONN_01_KEPSS_ROUTING = Scenario(
    scenario_id="CONN-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "ENH-TRS-R1+R5: domestic KES payment routes via KEPSS "
        "connector (Kenya Electronic Payment & Settlement System) "
        "per CBK NPS Act 2011."),
    setup=_setup_conn,
    actions=_actions_conn,
    assertions=_assertions_conn,
    requires_engines=("treasury_connectivity",))


# DIGITAL-01: Stablecoin de-peg detection (ENH-TRS-R2)
def _setup_digital_de_peg(engines: EngineBundle) -> None:
    from utils.treasury_digital_assets import (
        DigitalWallet, DigitalHolding, SpotRate, DigitalAssetType)
    eng = engines["treasury_digital_assets"]
    eng.register_wallet(DigitalWallet(
        wallet_id="W-USDC", blockchain="ETH",
        address="0xabc...", label="USDC custody"))
    eng.add_holding(DigitalHolding(
        holding_id="H-USDC-1", wallet_id="W-USDC",
        asset_type=DigitalAssetType.USDC,
        quantity=Decimal("100000"),
        acquired_at="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.USDC,
        kes_per_unit=Decimal("125.00"),    # 5% off 130 peg
        source="manual",
        timestamp="2026-05-01"))


def _actions_digital(engines: EngineBundle) -> None:
    from utils.treasury_digital_assets import DigitalAssetType
    eng = engines["treasury_digital_assets"]
    eng.value_holding(
        holding_id="H-USDC-1",
        peg_kes_for_stablecoins={
            DigitalAssetType.USDC: Decimal("130.00")})


def _assertions_digital(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.treasury_digital_assets import DePegStatus
    eng = engines["treasury_digital_assets"]
    summary = eng.board_summary()
    return (
        AssertionResult(
            assertion_id="dig01-a1",
            description=(
                "USDC at 125 vs 130 peg = 385 bps deviation → "
                "DE_PEGGED status"),
            expected=">= 1 de_pegged",
            observed=str(summary["n_de_pegged"]),
            matched=summary["n_de_pegged"] >= 1),
    )


SCENARIO_DIGITAL_01_DE_PEG_DETECTED = Scenario(
    scenario_id="DIGITAL-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "ENH-TRS-R2: USDC trading 5% off USD peg → de-peg "
        "detection triggers (>300bps threshold). Per CBK VASP "
        "Regs 2026 + BCBS Crypto Asset Std 2022."),
    setup=_setup_digital_de_peg,
    actions=_actions_digital,
    assertions=_assertions_digital,
    requires_engines=("treasury_digital_assets",))


# UNIFIED-01: Cross-asset rollup composes Islamic + Digital (ENH-TRS-R4)
def _setup_unified(engines: EngineBundle) -> None:
    from utils.islamic_treasury import (
        IslamicProduct, IslamicProductType)
    from utils.treasury_digital_assets import (
        DigitalWallet, DigitalHolding, SpotRate, DigitalAssetType)
    islamic = engines["islamic_treasury"]
    islamic.register_product(IslamicProduct(
        product_id="UN-MUR-1",
        product_type=IslamicProductType.MURABAHA,
        counterparty="Trade Co",
        principal_kes=Decimal("10000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("8"),
        underlying_asset_description="steel",
        sharia_board_approval_date="2026-04-15",
        counterparty_business_sector="manufacturing"))
    islamic.value_all()
    digital = engines["treasury_digital_assets"]
    digital.register_wallet(DigitalWallet(
        wallet_id="UN-W-1", blockchain="ETH",
        address="0x", label="USDC"))
    digital.add_holding(DigitalHolding(
        holding_id="UN-H-1", wallet_id="UN-W-1",
        asset_type=DigitalAssetType.USDC,
        quantity=Decimal("10000"),
        acquired_at="2026-05-01"))
    digital.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.USDC,
        kes_per_unit=Decimal("130"),
        source="manual",
        timestamp="2026-05-01"))
    digital.value_holding(holding_id="UN-H-1")


def _actions_unified(engines: EngineBundle) -> None:
    from utils.treasury_unified_platform import (
        UnifiedTreasuryPlatform)
    plat = UnifiedTreasuryPlatform(
        islamic_engine=engines["islamic_treasury"],
        digital_engine=engines["treasury_digital_assets"])
    rollup = plat.cross_asset_rollup(
        rollup_id="UN-R1", as_of_date="2026-05-01")
    engines["__unified_rollup__"] = rollup


def _assertions_unified(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    rollup = engines.get("__unified_rollup__")
    return (
        AssertionResult(
            assertion_id="un01-a1",
            description=(
                "Cross-asset rollup includes both ISLAMIC and "
                "DIGITAL"),
            expected=2,
            observed=(
                len(rollup.n_positions_by_class)
                if rollup else 0),
            matched=(
                rollup is not None
                and "ISLAMIC" in rollup.n_positions_by_class
                and "DIGITAL" in rollup.n_positions_by_class)),
        AssertionResult(
            assertion_id="un01-a2",
            description=(
                "Rollup consults 2 source engines"),
            expected=2,
            observed=(
                rollup.n_engines_consulted if rollup else 0),
            matched=(
                rollup is not None
                and rollup.n_engines_consulted == 2)),
    )


SCENARIO_UNIFIED_01_CROSS_ASSET_ROLLUP = Scenario(
    scenario_id="UNIFIED-01",
    category=ScenarioCategory.OPERATIONS_TREASURY,
    description=(
        "ENH-TRS-R4: MX.3-style facade aggregates Islamic + Digital "
        "positions into single cross-asset rollup. Per Rule 7, "
        "facade is READ-ONLY — never mutates upstream engines."),
    setup=_setup_unified,
    actions=_actions_unified,
    assertions=_assertions_unified,
    requires_engines=(
        "islamic_treasury", "treasury_digital_assets"))


# CLIMATE-01: Climate-adjusted limit tightens fossil concentration
# (ENH-TRS-R6)
def _setup_climate_limit(engines: EngineBundle) -> None:
    pass


def _actions_climate_limit(engines: EngineBundle) -> None:
    from utils.climate_treasury_limits import (
        ClimateTreasuryLimitsEngine, TreasuryAssetClass)
    # Mock climate engine with high transition risk for fossil
    class _MockAssess:
        def __init__(self, sector, score):
            self.sector = sector
            self.risk_score = Decimal(str(score))

    class _MockClimate:
        def __init__(self):
            self._physical_assessments = {}
            self._transition_assessments = {
                "t1": _MockAssess("oil_and_gas", 80),
                "t2": _MockAssess("coal_mining", 80)}

        def board_summary(self):
            return {"n_transition": 2}

    eng = ClimateTreasuryLimitsEngine(
        climate_engine=_MockClimate())
    limit = eng.compute_adjusted_limit(
        TreasuryAssetClass.CORPORATE_FOSSIL)
    engines["__climate_limit__"] = limit


def _assertions_climate_limit(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    limit = engines.get("__climate_limit__")
    return (
        AssertionResult(
            assertion_id="cl01-a1",
            description=(
                "High transition risk (score 80) → 30% haircut"),
            expected="30",
            observed=str(
                limit.transition_haircut_pct
                if limit else "MISSING"),
            matched=(
                limit is not None
                and limit.transition_haircut_pct
                == Decimal("30"))),
        AssertionResult(
            assertion_id="cl01-a2",
            description=(
                "Adjusted limit < base: 5% × (1-0.3) = 3.5%"),
            expected="3.5000",
            observed=str(
                limit.adjusted_limit_pct
                if limit else "MISSING"),
            matched=(
                limit is not None
                and limit.adjusted_limit_pct
                == Decimal("3.5000"))),
    )


SCENARIO_CLIMATE_01_FOSSIL_HAIRCUT = Scenario(
    scenario_id="CLIMATE-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-TRS-R6: high transition risk (oil & gas, coal) → "
        "30% climate haircut applied to fossil concentration "
        "limit (5% base → 3.5% adjusted) per BCBS Climate "
        "Principles 2022 + IFRS S2 + CBK CRDF."),
    setup=_setup_climate_limit,
    actions=_actions_climate_limit,
    assertions=_assertions_climate_limit,
    requires_engines=())


# ════════════════════════════════════════════════════════════════════════
# v10.39 — Risk arc opening (Market Risk foundation)
# ════════════════════════════════════════════════════════════════════════

# RISK-01: Parametric VaR on normal returns — sanity bounds
def _setup_risk_var_parametric(engines: EngineBundle) -> None:
    pass


def _actions_risk_var_parametric(engines: EngineBundle) -> None:
    import random as _r
    from utils.market_risk_var import VaREngine
    rng = _r.Random(42)
    returns = [rng.gauss(0.0, 0.01) for _ in range(1000)]
    eng = VaREngine()
    res = eng.parametric_var(
        returns=returns,
        portfolio_value_kes=Decimal("1000000"),
        confidence=Decimal("0.99"),
        horizon_days=1)
    engines["__risk01__"] = res


def _assertions_risk_var_parametric(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    res = engines.get("__risk01__")
    if res is None:
        return (AssertionResult(
            assertion_id="risk01-a0",
            description="VaR result populated",
            expected="present", observed="MISSING",
            matched=False),)
    # 99% z=2.326 × σ=0.01 × PV=1m ≈ 23,260 (with mean ≈ 0)
    return (
        AssertionResult(
            assertion_id="risk01-a1",
            description=(
                "Parametric 99% 1-day VaR within sanity range "
                "20k-28k for σ≈1% portfolio of 1m KES"),
            expected="VaR ∈ [20000, 28000]",
            observed=str(res.var_kes),
            matched=(
                Decimal("20000") <= res.var_kes
                <= Decimal("28000"))),
        AssertionResult(
            assertion_id="risk01-a2",
            description=(
                "Expected Shortfall ≥ VaR by construction"),
            expected="ES >= VaR",
            observed=(
                f"VaR={res.var_kes}, ES={res.expected_shortfall_kes}"),
            matched=(
                res.expected_shortfall_kes >= res.var_kes)),
        AssertionResult(
            assertion_id="risk01-a3",
            description="Methodology preserved",
            expected="PARAMETRIC",
            observed=res.methodology.value,
            matched=res.methodology.value == "PARAMETRIC"),
    )


SCENARIO_RISK_01_PARAMETRIC_VAR = Scenario(
    scenario_id="RISK-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-001/002: parametric VaR on Normal(0, 1%) "
        "returns produces sane 99% VaR; ES ≥ VaR by "
        "construction; methodology metadata preserved."),
    setup=_setup_risk_var_parametric,
    actions=_actions_risk_var_parametric,
    assertions=_assertions_risk_var_parametric,
    requires_engines=("market_risk_var",))


# RISK-02: BCBS IRRBB parallel-up shock applied to bond DV01
def _setup_risk_dv01(engines: EngineBundle) -> None:
    pass


def _actions_risk_dv01(engines: EngineBundle) -> None:
    from utils.market_risk_factors import (
        RiskFactor, BCBS_IRRBB_PARALLEL_UP, ShockType)
    from utils.market_risk_sensitivities import (
        BondPosition, SensitivityEngine)
    eng = SensitivityEngine()
    # 1m KES gov bond, modified duration 7y
    pos = BondPosition(
        position_id="GOV-10Y-1",
        factor=RiskFactor.IR_KES_GOVT,
        notional_kes=Decimal("1000000"),
        modified_duration=Decimal("7.0"))
    sens = eng.compute_dv01(pos)
    # Apply BCBS parallel-up 200bp shock
    shocks = {
        s.factor: (s.magnitude, s.shock_type.value)
        for s in BCBS_IRRBB_PARALLEL_UP.shocks}
    pnl = eng.apply_scenario_pnl((sens,), shocks)
    engines["__risk02_pnl__"] = pnl
    engines["__risk02_dv01__"] = sens.delta


def _assertions_risk_dv01(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    pnl = engines.get("__risk02_pnl__")
    dv01 = engines.get("__risk02_dv01__")
    return (
        AssertionResult(
            assertion_id="risk02-a1",
            description=(
                "DV01 = 7 × 1,000,000 × 0.0001 = 700 KES/bp"),
            expected="700",
            observed=str(dv01),
            matched=dv01 == Decimal("700.0000")),
        AssertionResult(
            assertion_id="risk02-a2",
            description=(
                "+200bp shock on 700 DV01 long bond = "
                "−140,000 KES PnL (loss when rates rise)"),
            expected="-140000",
            observed=str(pnl),
            matched=pnl == Decimal("-140000")),
    )


SCENARIO_RISK_02_BCBS_IRRBB_PNL = Scenario(
    scenario_id="RISK-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-003/004: BCBS d368 IRRBB parallel-up 200bp "
        "shock applied to bond DV01 — long bond loses "
        "140k KES per 1m principal at duration 7y."),
    setup=_setup_risk_dv01,
    actions=_actions_risk_dv01,
    assertions=_assertions_risk_dv01,
    requires_engines=(
        "market_risk_sensitivities", "market_risk_factors"))


# RISK-03: Historical and parametric VaR converge for normal returns
def _setup_risk_var_convergence(engines: EngineBundle) -> None:
    pass


def _actions_risk_var_convergence(engines: EngineBundle) -> None:
    import random as _r
    from utils.market_risk_var import VaREngine
    rng = _r.Random(42)
    returns = [rng.gauss(0.0, 0.01) for _ in range(2000)]
    eng = VaREngine()
    para = eng.parametric_var(
        returns, Decimal("1000000"), Decimal("0.99"))
    hist = eng.historical_var(
        returns, Decimal("1000000"), Decimal("0.99"))
    engines["__risk03_para__"] = para.var_kes
    engines["__risk03_hist__"] = hist.var_kes


def _assertions_risk_var_convergence(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    para = engines.get("__risk03_para__")
    hist = engines.get("__risk03_hist__")
    if para is None or hist is None:
        return (AssertionResult(
            assertion_id="risk03-a0", description="results present",
            expected="both", observed="missing", matched=False),)
    # Expect within 30% of each other for n=2000 normal samples
    ratio = float(hist / para) if para else 0.0
    return (
        AssertionResult(
            assertion_id="risk03-a1",
            description=(
                "Historical / parametric VaR ratio between "
                "0.7 and 1.3 for n=2000 normal returns"),
            expected="ratio in [0.7, 1.3]",
            observed=f"{ratio:.3f}",
            matched=0.7 <= ratio <= 1.3),
    )


SCENARIO_RISK_03_VAR_CONVERGENCE = Scenario(
    scenario_id="RISK-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-001: historical and parametric 99% VaR "
        "converge within 30% on n=2000 Normal(0,1%) returns "
        "— sanity check of both algorithms agreeing on "
        "well-behaved data."),
    setup=_setup_risk_var_convergence,
    actions=_actions_risk_var_convergence,
    assertions=_assertions_risk_var_convergence,
    requires_engines=("market_risk_var",))


# RISK-04: Kupiec backtest fails when too many VaR breaches observed
def _setup_risk_kupiec(engines: EngineBundle) -> None:
    pass


def _actions_risk_kupiec(engines: EngineBundle) -> None:
    from utils.market_risk_var import VaREngine, BacktestVerdict
    eng = VaREngine()
    # 25 breaches in 250 days at 99% conf — 10× expected (2.5)
    seq = [True] * 25 + [False] * 225
    res = eng.kupiec_pof_test(seq, Decimal("0.99"))
    engines["__risk04_verdict__"] = res.verdict
    engines["__risk04_stat__"] = res.test_statistic


def _assertions_risk_kupiec(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    verdict = engines.get("__risk04_verdict__")
    stat = engines.get("__risk04_stat__")
    return (
        AssertionResult(
            assertion_id="risk04-a1",
            description=(
                "Kupiec POF FAIL when 25 breaches in 250 days "
                "at 99% (10× expected)"),
            expected="FAIL",
            observed=verdict.value if verdict else "MISSING",
            matched=(
                verdict is not None
                and verdict.value == "FAIL")),
        AssertionResult(
            assertion_id="risk04-a2",
            description=(
                "LR test statistic exceeds χ²(1) 5% critical "
                "value of 3.841"),
            expected=">3.841",
            observed=str(stat),
            matched=(
                stat is not None and stat > Decimal("3.841"))),
    )


SCENARIO_RISK_04_KUPIEC_FAIL = Scenario(
    scenario_id="RISK-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-005: Kupiec POF backtest correctly FAILs "
        "when observed breach rate is 10× the expected rate "
        "— verifies regulatory backtesting catches "
        "model-failure mode."),
    setup=_setup_risk_kupiec,
    actions=_actions_risk_kupiec,
    assertions=_assertions_risk_kupiec,
    requires_engines=("market_risk_var",))


# RISK-05: Sensitivity aggregation across factor classes
def _setup_risk_sens_agg(engines: EngineBundle) -> None:
    pass


def _actions_risk_sens_agg(engines: EngineBundle) -> None:
    from utils.market_risk_factors import RiskFactor
    from utils.market_risk_sensitivities import (
        BondPosition, FXPosition, EquityPosition, SensitivityEngine)
    eng = SensitivityEngine()
    s_bond = eng.compute_dv01(BondPosition(
        position_id="b1", factor=RiskFactor.IR_KES_GOVT,
        notional_kes=Decimal("1000000"),
        modified_duration=Decimal("5.0")))
    s_fx = eng.compute_fx_delta(FXPosition(
        position_id="f1", factor=RiskFactor.FX_USDKES,
        foreign_amount=Decimal("100000"),
        spot_to_kes=Decimal("130")))
    s_eq = eng.compute_equity_delta(EquityPosition(
        position_id="e1", factor=RiskFactor.EQUITY_NSE_GENERIC,
        market_value_kes=Decimal("5000000"),
        beta=Decimal("1.0")))
    rep = eng.aggregate((s_bond, s_fx, s_eq))
    engines["__risk05_rep__"] = rep


def _assertions_risk_sens_agg(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    rep = engines.get("__risk05_rep__")
    if rep is None:
        return (AssertionResult(
            assertion_id="risk05-a0",
            description="report present",
            expected="present", observed="MISSING", matched=False),)
    # IR class total = 5*1m*0.0001 = 500
    # FX class total = 100k*130*0.01 = 130,000
    # Equity class total = 5m*1.0*0.01 = 50,000
    from utils.market_risk_factors import RiskFactorClass
    return (
        AssertionResult(
            assertion_id="risk05-a1",
            description="IR class total 500 KES/bp",
            expected="500",
            observed=str(rep.by_class.get(
                RiskFactorClass.INTEREST_RATE)),
            matched=rep.by_class.get(
                RiskFactorClass.INTEREST_RATE) == Decimal(
                    "500.0000")),
        AssertionResult(
            assertion_id="risk05-a2",
            description="FX class total 130,000 KES/1%",
            expected="130000",
            observed=str(rep.by_class.get(
                RiskFactorClass.FOREIGN_EXCHANGE)),
            matched=rep.by_class.get(
                RiskFactorClass.FOREIGN_EXCHANGE) == Decimal(
                    "130000.00")),
        AssertionResult(
            assertion_id="risk05-a3",
            description=(
                "Equity class total 50,000 KES/1% (beta=1)"),
            expected="50000",
            observed=str(rep.by_class.get(
                RiskFactorClass.EQUITY)),
            matched=rep.by_class.get(
                RiskFactorClass.EQUITY) == Decimal(
                    "50000.000")),
        AssertionResult(
            assertion_id="risk05-a4",
            description="3 positions aggregated",
            expected="3",
            observed=str(rep.n_positions),
            matched=rep.n_positions == 3),
    )


SCENARIO_RISK_05_SENS_AGGREGATION = Scenario(
    scenario_id="RISK-05",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-003: sensitivity aggregation across IR + FX "
        "+ Equity factor classes — verifies factor-class "
        "totals and per-position counts roll up correctly."),
    setup=_setup_risk_sens_agg,
    actions=_actions_risk_sens_agg,
    assertions=_assertions_risk_sens_agg,
    requires_engines=(
        "market_risk_sensitivities", "market_risk_factors"))


# ════════════════════════════════════════════════════════════════════════
# LIMITS-* — v10.40 Market Risk Limits & Breach Management
# ════════════════════════════════════════════════════════════════════════

# LIMITS-01: Concentration limit within bounds — no breach
def _setup_limits_within(engines: EngineBundle) -> None:
    pass


def _actions_limits_within(engines: EngineBundle) -> None:
    from utils.market_risk_factors import RiskFactor
    from utils.market_risk_limits import build_default_registry, LimitMonitor
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    # 1bn USD vs 2bn limit = 50% utilization
    report = monitor.run_pass(exposures_by_factor={
        RiskFactor.FX_USDKES: Decimal("1000000000"),
    })
    engines["__limits01__"] = report


def _assertions_limits_within(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    rep = engines.get("__limits01__")
    if rep is None:
        return (AssertionResult(
            assertion_id="limits01-a0",
            description="Report present",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="limits01-a1",
            description="Within-limit exposure produces no breaches",
            expected="n_breach == 0 AND n_severe == 0",
            observed=(
                f"n_breach={rep.n_breach}, "
                f"n_severe={rep.n_severe}"),
            matched=rep.is_clean()),
        AssertionResult(
            assertion_id="limits01-a2",
            description=(
                "Single-factor utilization at 50% emits "
                "WITHIN_LIMIT alert"),
            expected="alert at 50%",
            observed=str([
                str(a.utilization_pct) for a in rep.alerts
                if a.limit_id == "CONC_FX_USDKES_NET"]),
            matched=any(
                a.limit_id == "CONC_FX_USDKES_NET"
                and a.utilization_pct == Decimal("50.00")
                for a in rep.alerts)),
    )


SCENARIO_LIMITS_01_WITHIN = Scenario(
    scenario_id="LIMITS-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-006/007: USD/KES exposure of 1bn against 2bn "
        "limit (50% utilization) produces WITHIN_LIMIT alert "
        "with no breaches."),
    setup=_setup_limits_within,
    actions=_actions_limits_within,
    assertions=_assertions_limits_within,
    requires_engines=(
        "market_risk_limits", "market_risk_factors"))


# LIMITS-02: VaR limit BREACH at 110% utilization
def _setup_limits_var_breach(engines: EngineBundle) -> None:
    pass


def _actions_limits_var_breach(engines: EngineBundle) -> None:
    from utils.market_risk_limits import (
        build_default_registry, LimitMonitor, BreachSeverity)
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    # 55m vs 50m limit = 110% → BREACH (not SEVERE — that's >=120%)
    alerts = monitor.check_var(
        observed_var_kes=Decimal("55000000"),
        confidence=Decimal("0.99"), horizon_days=1)
    engines["__limits02__"] = alerts


def _assertions_limits_var_breach(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    alerts = engines.get("__limits02__")
    if alerts is None or not alerts:
        return (AssertionResult(
            assertion_id="limits02-a0",
            description="Alerts present",
            expected="present", observed="MISSING",
            matched=False),)
    a = alerts[0]
    return (
        AssertionResult(
            assertion_id="limits02-a1",
            description="VaR limit BREACH severity",
            expected="BREACH",
            observed=a.severity.value,
            matched=a.severity.value == "BREACH"),
        AssertionResult(
            assertion_id="limits02-a2",
            description="Utilization at 110%",
            expected="110.00",
            observed=str(a.utilization_pct),
            matched=a.utilization_pct == Decimal("110.00")),
        AssertionResult(
            assertion_id="limits02-a3",
            description=(
                "Escalation target reaches ALCO + CRO at BREACH"),
            expected="ALCO + CRO",
            observed=a.escalation_target,
            matched="ALCO" in a.escalation_target),
    )


SCENARIO_LIMITS_02_VAR_BREACH = Scenario(
    scenario_id="LIMITS-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-007: 55m KES VaR observation against 50m limit "
        "(110% utilization) emits BREACH severity with ALCO + "
        "CRO escalation."),
    setup=_setup_limits_var_breach,
    actions=_actions_limits_var_breach,
    assertions=_assertions_limits_var_breach,
    requires_engines=("market_risk_limits",))


# LIMITS-03: ES limit SEVERE_BREACH at 120%+ utilization
def _setup_limits_es_severe(engines: EngineBundle) -> None:
    pass


def _actions_limits_es_severe(engines: EngineBundle) -> None:
    from utils.market_risk_limits import (
        build_default_registry, LimitMonitor)
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    # 195m vs 150m limit = 130% → SEVERE_BREACH
    alerts = monitor.check_es(
        observed_es_kes=Decimal("195000000"),
        confidence=Decimal("0.975"), horizon_days=10)
    engines["__limits03__"] = alerts


def _assertions_limits_es_severe(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    alerts = engines.get("__limits03__")
    if alerts is None or not alerts:
        return (AssertionResult(
            assertion_id="limits03-a0",
            description="Alerts present",
            expected="present", observed="MISSING",
            matched=False),)
    a = alerts[0]
    return (
        AssertionResult(
            assertion_id="limits03-a1",
            description="ES limit SEVERE_BREACH severity",
            expected="SEVERE_BREACH",
            observed=a.severity.value,
            matched=a.severity.value == "SEVERE_BREACH"),
        AssertionResult(
            assertion_id="limits03-a2",
            description="Utilization at 130%",
            expected="130.00",
            observed=str(a.utilization_pct),
            matched=a.utilization_pct == Decimal("130.00")),
        AssertionResult(
            assertion_id="limits03-a3",
            description="Board-level escalation at SEVERE_BREACH",
            expected="Board Risk Committee",
            observed=a.escalation_target,
            matched="Board" in a.escalation_target),
    )


SCENARIO_LIMITS_03_ES_SEVERE = Scenario(
    scenario_id="LIMITS-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-007: 195m KES ES observation against 150m FRTB-IMA "
        "ES limit (130% utilization) emits SEVERE_BREACH with "
        "Board Risk Committee escalation."),
    setup=_setup_limits_es_severe,
    actions=_actions_limits_es_severe,
    assertions=_assertions_limits_es_severe,
    requires_engines=("market_risk_limits",))


# LIMITS-04: FX class limit aggregates across pairs
def _setup_limits_class_agg(engines: EngineBundle) -> None:
    pass


def _actions_limits_class_agg(engines: EngineBundle) -> None:
    from utils.market_risk_factors import RiskFactor
    from utils.market_risk_limits import (
        build_default_registry, LimitMonitor)
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    # USD 3bn + EUR 2bn + GBP 1bn = 6bn total vs 5bn FX class limit
    # = 120% → SEVERE_BREACH for class limit
    # AND USD 3bn vs 2bn single-factor limit = 150% → SEVERE_BREACH
    report = monitor.run_pass(exposures_by_factor={
        RiskFactor.FX_USDKES: Decimal("3000000000"),
        RiskFactor.FX_EURKES: Decimal("2000000000"),
        RiskFactor.FX_GBPKES: Decimal("1000000000"),
    })
    engines["__limits04__"] = report


def _assertions_limits_class_agg(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    rep = engines.get("__limits04__")
    if rep is None:
        return (AssertionResult(
            assertion_id="limits04-a0",
            description="Report present",
            expected="present", observed="MISSING",
            matched=False),)
    class_alerts = [
        a for a in rep.alerts if a.limit_id == "CONC_FX_TOTAL"]
    factor_alerts = [
        a for a in rep.alerts if a.limit_id == "CONC_FX_USDKES_NET"]
    return (
        AssertionResult(
            assertion_id="limits04-a1",
            description=(
                "Class limit aggregates USD+EUR+GBP = 6bn"),
            expected="observed=6000000000",
            observed=str(
                class_alerts[0].observed_kes
                if class_alerts else "NONE"),
            matched=(
                bool(class_alerts)
                and class_alerts[0].observed_kes
                == Decimal("6000000000"))),
        AssertionResult(
            assertion_id="limits04-a2",
            description=(
                "Class-level SEVERE_BREACH at 120%"),
            expected="SEVERE_BREACH",
            observed=(
                class_alerts[0].severity.value
                if class_alerts else "NONE"),
            matched=(
                bool(class_alerts)
                and class_alerts[0].severity.value
                == "SEVERE_BREACH")),
        AssertionResult(
            assertion_id="limits04-a3",
            description=(
                "Single-factor USD limit also SEVERE_BREACH "
                "at 150% (3bn / 2bn)"),
            expected="SEVERE_BREACH",
            observed=(
                factor_alerts[0].severity.value
                if factor_alerts else "NONE"),
            matched=(
                bool(factor_alerts)
                and factor_alerts[0].severity.value
                == "SEVERE_BREACH")),
    )


SCENARIO_LIMITS_04_CLASS_AGG = Scenario(
    scenario_id="LIMITS-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-006: FX class limit aggregates across 3 currency "
        "pairs (USD 3bn + EUR 2bn + GBP 1bn = 6bn vs 5bn limit) "
        "AND single-factor USD limit at 3bn vs 2bn — both "
        "produce SEVERE_BREACH simultaneously."),
    setup=_setup_limits_class_agg,
    actions=_actions_limits_class_agg,
    assertions=_assertions_limits_class_agg,
    requires_engines=(
        "market_risk_limits", "market_risk_factors"))


# LIMITS-05: Limit metadata preservation (Per Rule 1)
def _setup_limits_metadata(engines: EngineBundle) -> None:
    pass


def _actions_limits_metadata(engines: EngineBundle) -> None:
    from utils.market_risk_limits import (
        build_default_registry, LimitMonitor)
    reg = build_default_registry()
    monitor = LimitMonitor(reg)
    # Trigger a SEVERE_BREACH to inspect the alert payload
    alerts = monitor.check_var(
        observed_var_kes=Decimal("65000000"),
        confidence=Decimal("0.99"), horizon_days=1)
    engines["__limits05__"] = alerts


def _assertions_limits_metadata(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    alerts = engines.get("__limits05__")
    if not alerts:
        return (AssertionResult(
            assertion_id="limits05-a0",
            description="Alerts present",
            expected="present", observed="MISSING",
            matched=False),)
    a = alerts[0]
    return (
        AssertionResult(
            assertion_id="limits05-a1",
            description="Alert carries observed_kes",
            expected="65000000",
            observed=str(a.observed_kes),
            matched=a.observed_kes == Decimal("65000000")),
        AssertionResult(
            assertion_id="limits05-a2",
            description="Alert carries threshold_kes",
            expected="50000000",
            observed=str(a.threshold_kes),
            matched=a.threshold_kes == Decimal("50000000")),
        AssertionResult(
            assertion_id="limits05-a3",
            description="Alert carries framework_refs",
            expected="non-empty",
            observed=str(len(a.framework_refs)),
            matched=len(a.framework_refs) > 0),
        AssertionResult(
            assertion_id="limits05-a4",
            description="Alert ID is deterministic + non-empty",
            expected="non-empty string",
            observed=a.alert_id[:50] + "...",
            matched=isinstance(a.alert_id, str) and len(
                a.alert_id) > 0),
    )


SCENARIO_LIMITS_05_METADATA = Scenario(
    scenario_id="LIMITS-05",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-007 + Rule 1: every BreachAlert surfaces "
        "observed + threshold + utilization + framework_refs "
        "+ deterministic alert_id for audit-trail dedup."),
    setup=_setup_limits_metadata,
    actions=_actions_limits_metadata,
    assertions=_assertions_limits_metadata,
    requires_engines=("market_risk_limits",))


# ════════════════════════════════════════════════════════════════════════
# BOUNDARY-* — v10.41 Trading Book Boundary (BCBS d352 §A.4)
# ════════════════════════════════════════════════════════════════════════

# BOUNDARY-01: Listed equity → presumptive TRADING_BOOK
def _setup_boundary_eq(engines: EngineBundle) -> None:
    pass


def _actions_boundary_eq(engines: EngineBundle) -> None:
    from utils.trading_book_boundary import (
        InstrumentType, build_default_engine)
    eng = build_default_engine()
    a = eng.classify(
        position_id="EQ-001",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    engines["__boundary01__"] = a


def _assertions_boundary_eq(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    a = engines.get("__boundary01__")
    if a is None:
        return (AssertionResult(
            assertion_id="boundary01-a0",
            description="assignment present",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="boundary01-a1",
            description="Listed equity → TRADING_BOOK",
            expected="TRADING_BOOK",
            observed=a.classification.value,
            matched=a.classification.value == "TRADING_BOOK"),
        AssertionResult(
            assertion_id="boundary01-a2",
            description="Presumptive classification (no override)",
            expected="True",
            observed=str(a.is_presumptive),
            matched=a.is_presumptive),
        AssertionResult(
            assertion_id="boundary01-a3",
            description="Trading desk assigned",
            expected="DESK-EQ-NAIROBI",
            observed=str(a.trading_desk_id),
            matched=a.trading_desk_id == "DESK-EQ-NAIROBI"),
    )


SCENARIO_BOUNDARY_01_LISTED_EQUITY = Scenario(
    scenario_id="BOUNDARY-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-008/009: Listed equity classifies presumptively "
        "to TRADING_BOOK with desk DESK-EQ-NAIROBI per BCBS "
        "d352 §A.4."),
    setup=_setup_boundary_eq,
    actions=_actions_boundary_eq,
    assertions=_assertions_boundary_eq,
    requires_engines=("trading_book_boundary",))


# BOUNDARY-02: Banking book hedge → presumptive BANKING_BOOK
def _setup_boundary_hedge(engines: EngineBundle) -> None:
    pass


def _actions_boundary_hedge(engines: EngineBundle) -> None:
    from utils.trading_book_boundary import (
        InstrumentType, build_default_engine)
    eng = build_default_engine()
    a = eng.classify(
        position_id="HEDGE-001",
        instrument_type=InstrumentType.BANKING_BOOK_HEDGE,
        effective_date="2026-01-15")
    engines["__boundary02__"] = a


def _assertions_boundary_hedge(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    a = engines.get("__boundary02__")
    if a is None:
        return (AssertionResult(
            assertion_id="boundary02-a0",
            description="assignment present",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="boundary02-a1",
            description="Banking book hedge → BANKING_BOOK",
            expected="BANKING_BOOK",
            observed=a.classification.value,
            matched=a.classification.value == "BANKING_BOOK"),
        AssertionResult(
            assertion_id="boundary02-a2",
            description="No trading desk assigned (BB)",
            expected="None",
            observed=str(a.trading_desk_id),
            matched=a.trading_desk_id is None),
    )


SCENARIO_BOUNDARY_02_BANKING_HEDGE = Scenario(
    scenario_id="BOUNDARY-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-008: Banking book hedge classifies presumptively "
        "to BANKING_BOOK with no trading desk per BCBS d352 "
        "§A.4."),
    setup=_setup_boundary_hedge,
    actions=_actions_boundary_hedge,
    assertions=_assertions_boundary_hedge,
    requires_engines=("trading_book_boundary",))


# BOUNDARY-03: Reclassification request → PENDING; no mutation
def _setup_boundary_pending(engines: EngineBundle) -> None:
    pass


def _actions_boundary_pending(engines: EngineBundle) -> None:
    from utils.trading_book_boundary import (
        BookClassification, InstrumentType, build_default_engine)
    eng = build_default_engine()
    eng.classify(
        position_id="P-001",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    req = eng.request_reclassification(
        request_id="REQ-001",
        position_id="P-001",
        to_book=BookClassification.BANKING_BOOK,
        reason="strategic shift to long-term hold",
        expected_capital_impact_kes=Decimal("8000000"),
        requested_by="trader_id",
        request_date="2026-02-01")
    surcharge = eng.compute_capital_surcharge(req)
    # Confirm assignment NOT YET changed (Rule 7 — no auto-approve)
    current = eng.get_assignment("P-001")
    engines["__boundary03__"] = {
        "request": req,
        "surcharge": surcharge,
        "current_classification": current.classification,
    }


def _assertions_boundary_pending(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    d = engines.get("__boundary03__")
    if d is None:
        return (AssertionResult(
            assertion_id="boundary03-a0",
            description="state present",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="boundary03-a1",
            description=(
                "Surcharge computed (positive impact = surcharge)"),
            expected="8000000",
            observed=str(d["surcharge"]),
            matched=d["surcharge"] == Decimal("8000000")),
        AssertionResult(
            assertion_id="boundary03-a2",
            description=(
                "Per Rule 7: assignment NOT mutated by request"),
            expected="TRADING_BOOK",
            observed=d["current_classification"].value,
            matched=(
                d["current_classification"].value
                == "TRADING_BOOK")),
        AssertionResult(
            assertion_id="boundary03-a3",
            description="Request carries from/to provenance",
            expected="TRADING→BANKING",
            observed=(
                f"{d['request'].from_book.value}→"
                f"{d['request'].to_book.value}"),
            matched=(
                d["request"].from_book.value == "TRADING_BOOK"
                and d["request"].to_book.value == "BANKING_BOOK")),
    )


SCENARIO_BOUNDARY_03_PENDING = Scenario(
    scenario_id="BOUNDARY-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-010 + Rule 7: reclassification request with "
        "positive capital impact computes surcharge but does "
        "NOT mutate the assignment — per BCBS d352 §A.4.5 + "
        "EU AI Act Art 14 human oversight."),
    setup=_setup_boundary_pending,
    actions=_actions_boundary_pending,
    assertions=_assertions_boundary_pending,
    requires_engines=("trading_book_boundary",))


# BOUNDARY-04: Approval mutates; rejection does not
def _setup_boundary_approval(engines: EngineBundle) -> None:
    pass


def _actions_boundary_approval(engines: EngineBundle) -> None:
    from utils.trading_book_boundary import (
        BookClassification, InstrumentType, build_default_engine)
    eng = build_default_engine()
    eng.classify(
        position_id="P-A",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")
    eng.classify(
        position_id="P-R",
        instrument_type=InstrumentType.LISTED_EQUITY,
        effective_date="2026-01-15",
        trading_desk_id="DESK-EQ-NAIROBI")

    req_a = eng.request_reclassification(
        request_id="REQ-A", position_id="P-A",
        to_book=BookClassification.BANKING_BOOK,
        reason="strategic hold",
        expected_capital_impact_kes=Decimal("5000000"),
        requested_by="trader1", request_date="2026-02-01")
    decision_a, new_a = eng.approve_reclassification(
        request=req_a,
        approver="senior_mgmt_id",
        decision_date="2026-02-05",
        decision_id="DEC-A")

    req_r = eng.request_reclassification(
        request_id="REQ-R", position_id="P-R",
        to_book=BookClassification.BANKING_BOOK,
        reason="speculative reclassification",
        expected_capital_impact_kes=Decimal("0"),
        requested_by="trader2", request_date="2026-02-01")
    decision_r = eng.reject_reclassification(
        request=req_r,
        approver="senior_mgmt_id",
        decision_date="2026-02-05",
        decision_id="DEC-R",
        comments="insufficient justification")

    engines["__boundary04__"] = {
        "decision_a": decision_a,
        "new_a": new_a,
        "decision_r": decision_r,
        "post_approve_classification": eng.get_assignment(
            "P-A").classification,
        "post_reject_classification": eng.get_assignment(
            "P-R").classification,
    }


def _assertions_boundary_approval(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    d = engines.get("__boundary04__")
    if d is None:
        return (AssertionResult(
            assertion_id="boundary04-a0",
            description="state present",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="boundary04-a1",
            description="APPROVED status",
            expected="APPROVED",
            observed=d["decision_a"].status.value,
            matched=d["decision_a"].status.value == "APPROVED"),
        AssertionResult(
            assertion_id="boundary04-a2",
            description=(
                "Approval surcharge applied "
                "(5m × 1.0 = 5m)"),
            expected="5000000",
            observed=str(d["decision_a"].capital_surcharge_kes),
            matched=(
                d["decision_a"].capital_surcharge_kes
                == Decimal("5000000"))),
        AssertionResult(
            assertion_id="boundary04-a3",
            description="P-A reclassified to BANKING_BOOK",
            expected="BANKING_BOOK",
            observed=d["post_approve_classification"].value,
            matched=(
                d["post_approve_classification"].value
                == "BANKING_BOOK")),
        AssertionResult(
            assertion_id="boundary04-a4",
            description="REJECTED status",
            expected="REJECTED",
            observed=d["decision_r"].status.value,
            matched=d["decision_r"].status.value == "REJECTED"),
        AssertionResult(
            assertion_id="boundary04-a5",
            description=(
                "P-R unchanged (TRADING_BOOK) after rejection"),
            expected="TRADING_BOOK",
            observed=d["post_reject_classification"].value,
            matched=(
                d["post_reject_classification"].value
                == "TRADING_BOOK")),
    )


SCENARIO_BOUNDARY_04_APPROVAL = Scenario(
    scenario_id="BOUNDARY-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-010: APPROVED reclassification updates "
        "assignment + applies capital surcharge per BCBS d352 "
        "§A.4.5; REJECTED reclassification leaves assignment "
        "unchanged."),
    setup=_setup_boundary_approval,
    actions=_actions_boundary_approval,
    assertions=_assertions_boundary_approval,
    requires_engines=("trading_book_boundary",))


# BOUNDARY-05: Trading desk completeness validation
def _setup_boundary_desk_validation(
    engines: EngineBundle,
) -> None:
    pass


def _actions_boundary_desk_validation(
    engines: EngineBundle,
) -> None:
    from utils.trading_book_boundary import build_default_engine
    eng = build_default_engine()
    issues = eng.validate_trading_desk_completeness()
    engines["__boundary05__"] = issues


def _assertions_boundary_desk_validation(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    issues = engines.get("__boundary05__")
    if issues is None:
        return (AssertionResult(
            assertion_id="boundary05-a0",
            description="issues map present",
            expected="present", observed="MISSING",
            matched=False),)
    all_ok = all(
        list(v) == ["OK"]
        if all(hasattr(x, "value") for x in v)
        else False
        for v in issues.values())
    return (
        AssertionResult(
            assertion_id="boundary05-a1",
            description="3 default desks registered",
            expected="3",
            observed=str(len(issues)),
            matched=len(issues) == 3),
        AssertionResult(
            assertion_id="boundary05-a2",
            description=(
                "All default desks pass validation per "
                "BCBS d352 §A.4.2"),
            expected="all OK",
            observed=str({
                k: tuple(i.value for i in v)
                for k, v in issues.items()}),
            matched=all(
                tuple(i.value for i in v) == ("OK",)
                for v in issues.values())),
    )


SCENARIO_BOUNDARY_05_DESK_VALIDATION = Scenario(
    scenario_id="BOUNDARY-05",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-MR-009: 3 default trading desks (FX / Fixed Income "
        "/ Equity) all pass BCBS d352 §A.4.2 completeness "
        "validation — head_trader, mandate, risk_classes, "
        "holding_period all present."),
    setup=_setup_boundary_desk_validation,
    actions=_actions_boundary_desk_validation,
    assertions=_assertions_boundary_desk_validation,
    requires_engines=("trading_book_boundary",))


# ════════════════════════════════════════════════════════════════════════
# IRB-* — v10.42 Credit Risk IRB Capital Framework
# ════════════════════════════════════════════════════════════════════════

# IRB-01: typical corporate exposure produces sensible K (4-12%)
def _setup_irb_typical(engines: EngineBundle) -> None:
    pass


def _actions_irb_typical(engines: EngineBundle) -> None:
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass)
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="typical-corp",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=0.01, lgd=0.45,
        ead_kes=Decimal("10000000"),
        maturity_years=2.5)
    engines["__irb01__"] = engine.compute(exp)


def _assertions_irb_typical(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__irb01__")
    if r is None:
        return (AssertionResult(
            assertion_id="irb01-a0",
            description="Result populated",
            expected="present", observed="MISSING",
            matched=False),)
    k = float(r.capital_requirement_pct)
    return (
        AssertionResult(
            assertion_id="irb01-a1",
            description="K in [4%, 12%] for typical corporate",
            expected="0.04 < K < 0.12",
            observed=str(k),
            matched=0.04 < k < 0.12),
        AssertionResult(
            assertion_id="irb01-a2",
            description="EL = PD×LGD×EAD = 1% × 45% × 10m = 45,000",
            expected="45000.00",
            observed=str(r.expected_loss_kes),
            matched=r.expected_loss_kes == Decimal("45000.00")),
        AssertionResult(
            assertion_id="irb01-a3",
            description="Correlation R in [0.12, 0.24]",
            expected="0.12 ≤ R ≤ 0.24",
            observed=str(r.correlation_R),
            matched=0.12 <= r.correlation_R <= 0.24),
    )


SCENARIO_IRB_01_TYPICAL_CORP = Scenario(
    scenario_id="IRB-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-CR-001: typical corporate exposure (PD=1%, LGD=45%, "
        "M=2.5y, EAD=10m) produces K in 4-12% range, EL=45k, "
        "R in Basel range [0.12, 0.24]."),
    setup=_setup_irb_typical,
    actions=_actions_irb_typical,
    assertions=_assertions_irb_typical,
    requires_engines=("credit_risk_irb",))


# IRB-02: defaulted exposure → K=0 above EL per §RBC25.16
def _setup_irb_defaulted(engines: EngineBundle) -> None:
    pass


def _actions_irb_defaulted(engines: EngineBundle) -> None:
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass)
    engine = IRBCapitalEngine()
    exp = IRBExposure(
        exposure_id="defaulted",
        exposure_class=ExposureClass.LARGE_CORPORATE,
        pd=1.0, lgd=0.45,
        ead_kes=Decimal("5000000"),
        maturity_years=2.5)
    engines["__irb02__"] = engine.compute(exp)


def _assertions_irb_defaulted(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__irb02__")
    if r is None:
        return (AssertionResult(
            assertion_id="irb02-a0",
            description="Result populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="irb02-a1",
            description="Defaulted PD=1 → K=0 per §RBC25.16",
            expected="0",
            observed=str(r.capital_requirement_pct),
            matched=r.capital_requirement_pct == Decimal("0")),
        AssertionResult(
            assertion_id="irb02-a2",
            description="EL = 1.0 × 45% × 5m = 2,250,000",
            expected="2250000.00",
            observed=str(r.expected_loss_kes),
            matched=r.expected_loss_kes == Decimal("2250000.00")),
    )


SCENARIO_IRB_02_DEFAULTED = Scenario(
    scenario_id="IRB-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-CR-001 / BCBS d424 §RBC25.16: defaulted exposure "
        "(PD=1.0) produces K=0 above EL — capital coverage "
        "comes entirely through expected-loss provisioning."),
    setup=_setup_irb_defaulted,
    actions=_actions_irb_defaulted,
    assertions=_assertions_irb_defaulted,
    requires_engines=("credit_risk_irb",))


# IRB-03: K monotonic in PD (holding LGD/EAD/M constant)
def _setup_irb_monotonic(engines: EngineBundle) -> None:
    pass


def _actions_irb_monotonic(engines: EngineBundle) -> None:
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass)
    engine = IRBCapitalEngine()
    base = dict(
        exposure_class=ExposureClass.LARGE_CORPORATE,
        lgd=0.45, ead_kes=Decimal("1000000"), maturity_years=2.5)
    results = []
    for i, pd in enumerate([0.005, 0.02, 0.10]):
        results.append(engine.compute(IRBExposure(
            exposure_id=f"mono-{i}", pd=pd, **base)))
    engines["__irb03__"] = results


def _assertions_irb_monotonic(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    results = engines.get("__irb03__")
    if not results or len(results) != 3:
        return (AssertionResult(
            assertion_id="irb03-a0",
            description="Three results populated",
            expected="3", observed=str(len(results) if results else 0),
            matched=False),)
    k_low = results[0].capital_requirement_pct
    k_med = results[1].capital_requirement_pct
    k_high = results[2].capital_requirement_pct
    return (
        AssertionResult(
            assertion_id="irb03-a1",
            description="K(PD=0.5%) < K(PD=2%) < K(PD=10%)",
            expected="monotonic",
            observed=f"{k_low} < {k_med} < {k_high}",
            matched=k_low < k_med < k_high),
    )


SCENARIO_IRB_03_PD_MONOTONIC = Scenario(
    scenario_id="IRB-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-CR-001: capital requirement K monotonic in PD "
        "holding LGD, EAD, M constant — basic Basel ASRF "
        "sanity check."),
    setup=_setup_irb_monotonic,
    actions=_actions_irb_monotonic,
    assertions=_assertions_irb_monotonic,
    requires_engines=("credit_risk_irb",))


# IRB-04: portfolio aggregation
def _setup_irb_portfolio(engines: EngineBundle) -> None:
    pass


def _actions_irb_portfolio(engines: EngineBundle) -> None:
    from utils.credit_risk_irb import (
        IRBCapitalEngine, IRBExposure, ExposureClass)
    engine = IRBCapitalEngine()
    exposures = [
        IRBExposure(
            exposure_id=f"port-{i}",
            exposure_class=ExposureClass.LARGE_CORPORATE,
            pd=0.01 * (i + 1), lgd=0.45,
            ead_kes=Decimal("1000000"),
            maturity_years=2.5)
        for i in range(5)
    ]
    results, total_rwa, total_el = (
        engine.compute_portfolio(exposures))
    engines["__irb04__"] = (results, total_rwa, total_el)


def _assertions_irb_portfolio(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    payload = engines.get("__irb04__")
    if not payload:
        return (AssertionResult(
            assertion_id="irb04-a0",
            description="Portfolio result populated",
            expected="present", observed="MISSING",
            matched=False),)
    results, total_rwa, total_el = payload
    sum_rwa = sum(
        (r.rwa_kes for r in results), Decimal("0"))
    return (
        AssertionResult(
            assertion_id="irb04-a1",
            description="5 exposures processed",
            expected="5",
            observed=str(len(results)),
            matched=len(results) == 5),
        AssertionResult(
            assertion_id="irb04-a2",
            description=(
                "total RWA equals sum of per-exposure RWAs"),
            expected=str(sum_rwa.quantize(Decimal("0.01"))),
            observed=str(total_rwa),
            matched=(
                total_rwa == sum_rwa.quantize(Decimal("0.01")))),
        AssertionResult(
            assertion_id="irb04-a3",
            description="EL grows monotonically with PD",
            expected="EL[0] < EL[4]",
            observed=(
                f"{results[0].expected_loss_kes} < "
                f"{results[4].expected_loss_kes}"),
            matched=(
                results[0].expected_loss_kes
                < results[4].expected_loss_kes)),
    )


SCENARIO_IRB_04_PORTFOLIO = Scenario(
    scenario_id="IRB-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-CR-001: portfolio aggregation — 5 exposures with "
        "ascending PD, RWA totals match per-exposure sum, EL "
        "monotonic in PD."),
    setup=_setup_irb_portfolio,
    actions=_actions_irb_portfolio,
    assertions=_assertions_irb_portfolio,
    requires_engines=("credit_risk_irb",))


# ════════════════════════════════════════════════════════════════════════
# v10.43 — Operational Risk SMA (ENH-OR-001)
# ════════════════════════════════════════════════════════════════════════

def _or_bi_default_kwargs():
    return dict(
        interest_income_kes=Decimal("12000000000"),
        interest_expense_kes=Decimal("6000000000"),
        interest_earning_assets_kes=Decimal("400000000000"),
        dividend_income_kes=Decimal("100000000"),
        other_operating_income_kes=Decimal("500000000"),
        other_operating_expense_kes=Decimal("400000000"),
        fee_income_kes=Decimal("3000000000"),
        fee_expense_kes=Decimal("500000000"),
        net_pnl_trading_book_kes=Decimal("200000000"),
        net_pnl_banking_book_kes=Decimal("100000000"))


def _or_bi_large_kwargs():
    return dict(
        interest_income_kes=Decimal("700000000000"),
        interest_expense_kes=Decimal("300000000000"),
        interest_earning_assets_kes=Decimal("20000000000000"),
        dividend_income_kes=Decimal("100000000"),
        other_operating_income_kes=Decimal("500000000"),
        other_operating_expense_kes=Decimal("400000000"),
        fee_income_kes=Decimal("80000000000"),
        fee_expense_kes=Decimal("500000000"),
        net_pnl_trading_book_kes=Decimal("200000000"),
        net_pnl_banking_book_kes=Decimal("100000000"))


# OR-01: Bucket 1 small bank, ILM=1 by national discretion → ORC = BIC
def _setup_or_bucket1(engines: EngineBundle) -> None:
    pass


def _actions_or_bucket1(engines: EngineBundle) -> None:
    from utils.op_risk import (
        OperationalRiskSMA, SMAInputs, BusinessIndicatorInputs,
        OperationalLossEvent)
    kw = _or_bi_default_kwargs()
    bi = tuple(
        BusinessIndicatorInputs(fiscal_year=y, **kw)
        for y in (2021, 2022, 2023))
    losses = tuple(
        OperationalLossEvent(
            fiscal_year=y, gross_loss_kes=Decimal("50000000"))
        for y in range(2014, 2024))
    inp = SMAInputs(
        bi_inputs=bi, loss_events=losses,
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=True)
    engines["__or01__"] = OperationalRiskSMA().compute(inp)


def _assertions_or_bucket1(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.op_risk import Bucket, ILMSource
    r = engines.get("__or01__")
    if r is None:
        return (AssertionResult(
            assertion_id="or01-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="or01-a1",
            description="Small bank → Bucket 1",
            expected=str(Bucket.BUCKET_1.value),
            observed=str(r.bucket.value),
            matched=r.bucket == Bucket.BUCKET_1),
        AssertionResult(
            assertion_id="or01-a2",
            description="Bucket 1 discretion → ILM=1",
            expected="1.000000",
            observed=str(r.ilm),
            matched=r.ilm == Decimal("1.000000")),
        AssertionResult(
            assertion_id="or01-a3",
            description="ILM source = BUCKET_1_DISCRETION",
            expected=ILMSource.BUCKET_1_DISCRETION.value,
            observed=r.ilm_source.value,
            matched=r.ilm_source == ILMSource.BUCKET_1_DISCRETION),
        AssertionResult(
            assertion_id="or01-a4",
            description="ORC = BIC when ILM=1",
            expected=str(r.bic_kes),
            observed=str(r.orc_kes),
            matched=r.orc_kes == r.bic_kes),
        AssertionResult(
            assertion_id="or01-a5",
            description="RWA = ORC × 12.5",
            expected=str(
                (r.orc_kes * Decimal("12.5")).quantize(Decimal("0.01"))),
            observed=str(r.rwa_op_kes),
            matched=r.rwa_op_kes == (
                r.orc_kes * Decimal("12.5")).quantize(Decimal("0.01"))),
    )


SCENARIO_OR_01_BUCKET1_DISCRETION = Scenario(
    scenario_id="OR-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-OR-001 / BCBS d457 §RBC30.41: small Kenyan bank in "
        "Bucket 1 with national discretion → ILM=1, ORC=BIC, "
        "RWA = ORC × 12.5."),
    setup=_setup_or_bucket1,
    actions=_actions_or_bucket1,
    assertions=_assertions_or_bucket1,
    requires_engines=("op_risk",))


# OR-02: Bucket 2 insufficient loss history → ILM=1 by fallback
def _setup_or_insufficient(engines: EngineBundle) -> None:
    pass


def _actions_or_insufficient(engines: EngineBundle) -> None:
    from utils.op_risk import (
        OperationalRiskSMA, SMAInputs, BusinessIndicatorInputs,
        OperationalLossEvent)
    kw = _or_bi_large_kwargs()
    bi = tuple(
        BusinessIndicatorInputs(fiscal_year=y, **kw)
        for y in (2021, 2022, 2023))
    # Only 2 years of losses → below 5y minimum
    losses = tuple(
        OperationalLossEvent(
            fiscal_year=y, gross_loss_kes=Decimal("1000000000"))
        for y in (2022, 2023))
    inp = SMAInputs(
        bi_inputs=bi, loss_events=losses,
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=False)
    engines["__or02__"] = OperationalRiskSMA().compute(inp)


def _assertions_or_insufficient(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.op_risk import Bucket, ILMSource
    r = engines.get("__or02__")
    if r is None:
        return (AssertionResult(
            assertion_id="or02-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="or02-a1",
            description="Large bank lifted to Bucket 2 or 3",
            expected="BUCKET_2 or BUCKET_3",
            observed=r.bucket.value,
            matched=r.bucket in (Bucket.BUCKET_2, Bucket.BUCKET_3)),
        AssertionResult(
            assertion_id="or02-a2",
            description="<5y history → ILM = 1 fallback",
            expected="1.000000",
            observed=str(r.ilm),
            matched=r.ilm == Decimal("1.000000")),
        AssertionResult(
            assertion_id="or02-a3",
            description="ILM source = INSUFFICIENT_HISTORY",
            expected=ILMSource.INSUFFICIENT_HISTORY.value,
            observed=r.ilm_source.value,
            matched=r.ilm_source == ILMSource.INSUFFICIENT_HISTORY),
    )


SCENARIO_OR_02_INSUFFICIENT_HISTORY = Scenario(
    scenario_id="OR-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-OR-001: bucket 2 bank with <5y of loss data → ILM "
        "fallback to 1.0, source surfaced as INSUFFICIENT_HISTORY."),
    setup=_setup_or_insufficient,
    actions=_actions_or_insufficient,
    assertions=_assertions_or_insufficient,
    requires_engines=("op_risk",))


# OR-03: ILM monotonic in loss size (bucket 2, full history)
def _setup_or_monotonic(engines: EngineBundle) -> None:
    pass


def _actions_or_monotonic(engines: EngineBundle) -> None:
    from utils.op_risk import (
        OperationalRiskSMA, SMAInputs, BusinessIndicatorInputs,
        OperationalLossEvent)
    kw = _or_bi_large_kwargs()
    bi = tuple(
        BusinessIndicatorInputs(fiscal_year=y, **kw)
        for y in (2021, 2022, 2023))
    eng = OperationalRiskSMA()

    def with_loss(per_year: Decimal):
        losses = tuple(
            OperationalLossEvent(
                fiscal_year=y, gross_loss_kes=per_year)
            for y in range(2014, 2024))
        return eng.compute(SMAInputs(
            bi_inputs=bi, loss_events=losses,
            eur_to_kes_rate=Decimal("145"),
            apply_bucket_1_discretion=False))

    engines["__or03_low__"] = with_loss(Decimal("1000000000"))
    engines["__or03_high__"] = with_loss(Decimal("10000000000"))


def _assertions_or_monotonic(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.op_risk import ILMSource
    low = engines.get("__or03_low__")
    high = engines.get("__or03_high__")
    if low is None or high is None:
        return (AssertionResult(
            assertion_id="or03-a0", description="Both results populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="or03-a1",
            description="Low-loss ILM source = COMPUTED",
            expected=ILMSource.COMPUTED.value,
            observed=low.ilm_source.value,
            matched=low.ilm_source == ILMSource.COMPUTED),
        AssertionResult(
            assertion_id="or03-a2",
            description="High-loss ILM > low-loss ILM",
            expected="ILM_high > ILM_low",
            observed=f"low={low.ilm}, high={high.ilm}",
            matched=high.ilm > low.ilm),
        AssertionResult(
            assertion_id="or03-a3",
            description="High-loss ORC > low-loss ORC (same BIC)",
            expected="ORC_high > ORC_low",
            observed=f"low={low.orc_kes}, high={high.orc_kes}",
            matched=high.orc_kes > low.orc_kes),
    )


SCENARIO_OR_03_ILM_MONOTONIC = Scenario(
    scenario_id="OR-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-OR-001: holding BIC constant, larger annual losses "
        "produce a larger ILM and a larger ORC — monotonicity "
        "property of ln(e−1 + (LC/BIC)^0.8)."),
    setup=_setup_or_monotonic,
    actions=_actions_or_monotonic,
    assertions=_assertions_or_monotonic,
    requires_engines=("op_risk",))


# OR-04: Provenance — full SMAResult surfaces all Rule 1 fields
def _setup_or_provenance(engines: EngineBundle) -> None:
    pass


def _actions_or_provenance(engines: EngineBundle) -> None:
    from utils.op_risk import (
        OperationalRiskSMA, SMAInputs, BusinessIndicatorInputs)
    kw = _or_bi_default_kwargs()
    bi = tuple(
        BusinessIndicatorInputs(fiscal_year=y, **kw)
        for y in (2021, 2022, 2023))
    inp = SMAInputs(
        bi_inputs=bi, loss_events=(),
        eur_to_kes_rate=Decimal("145"),
        apply_bucket_1_discretion=True)
    engines["__or04__"] = OperationalRiskSMA().compute(inp)


def _assertions_or_provenance(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__or04__")
    if r is None:
        return (AssertionResult(
            assertion_id="or04-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="or04-a1",
            description="BI surfaced for all 3 years",
            expected="3 years",
            observed=str(len(r.bi_per_year_kes)),
            matched=len(r.bi_per_year_kes) == 3),
        AssertionResult(
            assertion_id="or04-a2",
            description="BI 3y avg in both KES and EUR",
            expected="both > 0",
            observed=(f"kes={r.bi_three_year_avg_kes}, "
                      f"eur={r.bi_three_year_avg_eur}"),
            matched=(r.bi_three_year_avg_kes > 0
                     and r.bi_three_year_avg_eur > 0)),
        AssertionResult(
            assertion_id="or04-a3",
            description="Framework refs cite BCBS d457",
            expected="BCBS d457 in refs",
            observed=", ".join(r.framework_refs),
            matched=any(
                "BCBS d457" in ref for ref in r.framework_refs)),
        AssertionResult(
            assertion_id="or04-a4",
            description="ILM source enum surfaced",
            expected="non-empty enum value",
            observed=r.ilm_source.value,
            matched=bool(r.ilm_source.value)),
    )


SCENARIO_OR_04_PROVENANCE = Scenario(
    scenario_id="OR-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-OR-001 Rule 1 cross-check: SMAResult surfaces BI per "
        "year, 3y avg in KES + EUR, bucket, BIC, LC, ILM, ilm_source, "
        "ORC, RWA, and framework refs."),
    setup=_setup_or_provenance,
    actions=_actions_or_provenance,
    assertions=_assertions_or_provenance,
    requires_engines=("op_risk",))


# ════════════════════════════════════════════════════════════════════════
# v10.44 — Stressed LCR (ENH-LR-001)
# ════════════════════════════════════════════════════════════════════════

def _lr_default_holdings():
    from utils.liquidity_stress import HQLAHolding, HQLALevel
    return (
        HQLAHolding(
            holding_id="cb_reserves", level=HQLALevel.LEVEL_1,
            market_value_kes=Decimal("80000000000")),
        HQLAHolding(
            holding_id="govt_bonds", level=HQLALevel.LEVEL_2A,
            market_value_kes=Decimal("20000000000")),
    )


def _lr_default_outflows():
    from utils.liquidity_stress import OutflowCategory
    return (
        OutflowCategory(
            category_id="retail_stable", label="Retail stable",
            balance_kes=Decimal("100000000000"),
            base_run_off_rate=Decimal("0.05")),
        OutflowCategory(
            category_id="wholesale_unsec",
            label="Unsecured wholesale (non-financial)",
            balance_kes=Decimal("30000000000"),
            base_run_off_rate=Decimal("0.40")),
    )


def _lr_default_inflows():
    from utils.liquidity_stress import InflowCategory
    return (
        InflowCategory(
            category_id="performing_loans", label="Performing loans",
            balance_kes=Decimal("8000000000"),
            base_run_in_rate=Decimal("0.50")),
    )


# LR-01: BASELINE → COMPLIANT
def _setup_lr_baseline(engines: EngineBundle) -> None:
    pass


def _actions_lr_baseline(engines: EngineBundle) -> None:
    from utils.liquidity_stress import (
        LiquidityStressEngine, StressSeverity)
    engines["__lr01__"] = LiquidityStressEngine().compute(
        holdings=_lr_default_holdings(),
        outflows=_lr_default_outflows(),
        inflows=_lr_default_inflows(),
        severity=StressSeverity.BASELINE)


def _assertions_lr_baseline(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.liquidity_stress import BreachSeverity, StressSeverity
    r = engines.get("__lr01__")
    if r is None:
        return (AssertionResult(
            assertion_id="lr01-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="lr01-a1",
            description="Severity = BASELINE recorded",
            expected=StressSeverity.BASELINE.value,
            observed=r.severity.value,
            matched=r.severity == StressSeverity.BASELINE),
        AssertionResult(
            assertion_id="lr01-a2",
            description="LCR ≥ 100% at baseline → COMPLIANT",
            expected=BreachSeverity.COMPLIANT.value,
            observed=r.breach_severity.value,
            matched=r.breach_severity == BreachSeverity.COMPLIANT),
        AssertionResult(
            assertion_id="lr01-a3",
            description="No survival horizon when compliant",
            expected="None",
            observed=str(r.survival_days),
            matched=r.survival_days is None),
        AssertionResult(
            assertion_id="lr01-a4",
            description="HQLA breakdown surfaces all 3 levels",
            expected="3",
            observed=str(len(r.hqla_breakdown)),
            matched=len(r.hqla_breakdown) == 3),
    )


SCENARIO_LR_01_BASELINE_COMPLIANT = Scenario(
    scenario_id="LR-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-LR-001 BASELINE: well-capitalised Kenyan bank with "
        "100bn HQLA L1 + 20bn L2A and modest unsecured wholesale "
        "exposure → LCR ≥ 100%, COMPLIANT, no survival horizon."),
    setup=_setup_lr_baseline,
    actions=_actions_lr_baseline,
    assertions=_assertions_lr_baseline,
    requires_engines=("liquidity_stress",))


# LR-02: SEVERE multiplier escalates breach severity vs baseline
def _setup_lr_severe(engines: EngineBundle) -> None:
    pass


def _actions_lr_severe(engines: EngineBundle) -> None:
    from utils.liquidity_stress import (
        LiquidityStressEngine, StressSeverity, HQLAHolding,
        HQLALevel, OutflowCategory, InflowCategory)
    # Thinner HQLA + heavier outflows so SEVERE pushes into breach
    holdings = (
        HQLAHolding(
            holding_id="cb", level=HQLALevel.LEVEL_1,
            market_value_kes=Decimal("12000000000")),)
    out = (
        OutflowCategory(
            category_id="retail", label="Retail",
            balance_kes=Decimal("100000000000"),
            base_run_off_rate=Decimal("0.10")),
        OutflowCategory(
            category_id="wholesale", label="Wholesale",
            balance_kes=Decimal("30000000000"),
            base_run_off_rate=Decimal("0.40")),
    )
    inf = (
        InflowCategory(
            category_id="loans", label="Performing loans",
            balance_kes=Decimal("4000000000"),
            base_run_in_rate=Decimal("0.50")),)
    eng = LiquidityStressEngine()
    engines["__lr02_base__"] = eng.compute(
        holdings=holdings, outflows=out, inflows=inf,
        severity=StressSeverity.BASELINE)
    engines["__lr02_sev__"] = eng.compute(
        holdings=holdings, outflows=out, inflows=inf,
        severity=StressSeverity.SEVERE)


def _assertions_lr_severe(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    base = engines.get("__lr02_base__")
    sev = engines.get("__lr02_sev__")
    if base is None or sev is None:
        return (AssertionResult(
            assertion_id="lr02-a0",
            description="Both results populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="lr02-a1",
            description="SEVERE outflows > BASELINE outflows",
            expected="sev > base",
            observed=(f"base={base.total_outflows_kes}, "
                      f"sev={sev.total_outflows_kes}"),
            matched=sev.total_outflows_kes > base.total_outflows_kes),
        AssertionResult(
            assertion_id="lr02-a2",
            description="SEVERE inflows < BASELINE inflows",
            expected="sev < base",
            observed=(f"base={base.total_inflows_kes}, "
                      f"sev={sev.total_inflows_kes}"),
            matched=sev.total_inflows_kes < base.total_inflows_kes),
        AssertionResult(
            assertion_id="lr02-a3",
            description="SEVERE LCR strictly worse than BASELINE",
            expected="sev_lcr < base_lcr",
            observed=(f"base={base.lcr_ratio}, sev={sev.lcr_ratio}"),
            matched=(
                base.lcr_ratio is not None
                and sev.lcr_ratio is not None
                and sev.lcr_ratio < base.lcr_ratio)),
    )


SCENARIO_LR_02_SEVERE_ESCALATION = Scenario(
    scenario_id="LR-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-LR-001: SEVERE severity tier produces strictly worse "
        "LCR than BASELINE (higher outflows, lower inflows). Tests "
        "the BCBS d295 stress overlay monotonicity in severity."),
    setup=_setup_lr_severe,
    actions=_actions_lr_severe,
    assertions=_assertions_lr_severe,
    requires_engines=("liquidity_stress",))


# LR-03: BANK_RUN scenario classifies breach + computes survival
def _setup_lr_bankrun(engines: EngineBundle) -> None:
    pass


def _actions_lr_bankrun(engines: EngineBundle) -> None:
    from utils.liquidity_stress import (
        LiquidityStressEngine, StressSeverity, HQLAHolding,
        HQLALevel, OutflowCategory)
    holdings = (
        HQLAHolding(
            holding_id="cb", level=HQLALevel.LEVEL_1,
            market_value_kes=Decimal("5000000000")),)
    out = (
        OutflowCategory(
            category_id="retail_run", label="Retail (under run)",
            balance_kes=Decimal("80000000000"),
            base_run_off_rate=Decimal("0.10")),)
    engines["__lr03__"] = LiquidityStressEngine().compute(
        holdings=holdings, outflows=out, inflows=(),
        severity=StressSeverity.BANK_RUN)


def _assertions_lr_bankrun(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.liquidity_stress import BreachSeverity
    r = engines.get("__lr03__")
    if r is None:
        return (AssertionResult(
            assertion_id="lr03-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="lr03-a1",
            description="Bank run scenario → breach classified",
            expected="non-COMPLIANT",
            observed=r.breach_severity.value,
            matched=r.breach_severity != BreachSeverity.COMPLIANT),
        AssertionResult(
            assertion_id="lr03-a2",
            description="Survival horizon populated when breaching",
            expected="not None",
            observed=str(r.survival_days),
            matched=r.survival_days is not None),
        AssertionResult(
            assertion_id="lr03-a3",
            description="Stressed retail rate capped at 100%",
            expected="≤ 1.0",
            observed=str(r.outflows[0].stressed_rate),
            matched=r.outflows[0].stressed_rate <= Decimal("1.0")),
        AssertionResult(
            assertion_id="lr03-a4",
            description="LCR < 100% under bank run",
            expected="lcr < 1.0",
            observed=str(r.lcr_ratio),
            matched=(r.lcr_ratio is not None
                     and r.lcr_ratio < Decimal("1.0"))),
    )


SCENARIO_LR_03_BANK_RUN = Scenario(
    scenario_id="LR-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-LR-001 BANK_RUN: idiosyncratic-run scenario with thin "
        "HQLA → breach classified, survival horizon computed, "
        "stressed run-off rate capped at 100%."),
    setup=_setup_lr_bankrun,
    actions=_actions_lr_bankrun,
    assertions=_assertions_lr_bankrun,
    requires_engines=("liquidity_stress",))


# LR-04: Provenance — full StressedLCRResult surfaces all Rule 1 fields
def _setup_lr_provenance(engines: EngineBundle) -> None:
    pass


def _actions_lr_provenance(engines: EngineBundle) -> None:
    from utils.liquidity_stress import (
        LiquidityStressEngine, StressSeverity)
    engines["__lr04__"] = LiquidityStressEngine().compute(
        holdings=_lr_default_holdings(),
        outflows=_lr_default_outflows(),
        inflows=_lr_default_inflows(),
        severity=StressSeverity.MODERATE,
        notes="provenance-check")


def _assertions_lr_provenance(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__lr04__")
    if r is None:
        return (AssertionResult(
            assertion_id="lr04-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="lr04-a1",
            description="Per-category outflows surfaced",
            expected="2 categories",
            observed=str(len(r.outflows)),
            matched=len(r.outflows) == 2),
        AssertionResult(
            assertion_id="lr04-a2",
            description="HQLA pre-cap & post-cap totals both surfaced",
            expected="both > 0",
            observed=(f"pre={r.hqla_total_pre_cap_kes}, "
                      f"post={r.hqla_total_after_caps_kes}"),
            matched=(r.hqla_total_pre_cap_kes > 0
                     and r.hqla_total_after_caps_kes > 0)),
        AssertionResult(
            assertion_id="lr04-a3",
            description="Inflows-capped value surfaced",
            expected="≤ 75% of outflows",
            observed=(f"capped={r.inflows_capped_kes}, "
                      f"out={r.total_outflows_kes}"),
            matched=(
                r.inflows_capped_kes
                <= Decimal("0.75") * r.total_outflows_kes
                + Decimal("0.01"))),
        AssertionResult(
            assertion_id="lr04-a4",
            description="Framework refs cite BCBS d295",
            expected="BCBS d295 in refs",
            observed=", ".join(r.framework_refs),
            matched=any(
                "BCBS d295" in ref for ref in r.framework_refs)),
        AssertionResult(
            assertion_id="lr04-a5",
            description="Notes preserved",
            expected="provenance-check",
            observed=r.notes,
            matched=r.notes == "provenance-check"),
    )


SCENARIO_LR_04_PROVENANCE = Scenario(
    scenario_id="LR-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-LR-001 Rule 1 cross-check: StressedLCRResult surfaces "
        "per-category outflows, HQLA pre/post-cap totals, capped "
        "inflows, framework refs (BCBS d295), and caller notes."),
    setup=_setup_lr_provenance,
    actions=_actions_lr_provenance,
    assertions=_assertions_lr_provenance,
    requires_engines=("liquidity_stress",))


# ════════════════════════════════════════════════════════════════════════
# v10.47 — Alternative Credit Scoring (ENH-260) · credit_model_risk arc
# ════════════════════════════════════════════════════════════════════════

# ALT-01: Healthy thin-file applicant → low PD, HIGH confidence
def _setup_alt_healthy(engines: EngineBundle) -> None:
    pass


def _actions_alt_healthy(engines: EngineBundle) -> None:
    from utils.credit_alt_scoring import (
        AlternativeCreditScoringEngine, ThinFileApplicant,
        TransactionMetrics, BehavioralMetrics, PsychometricMetrics)
    applicant = ThinFileApplicant(
        applicant_id="alt-01-healthy",
        transaction=TransactionMetrics(
            months_observed=12,
            monthly_deposit_cv=0.10,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.55,
            bills_on_time_pct=0.95),
        behavioral=BehavioralMetrics(
            tenure_months=24,
            mobile_active_days_per_month=22,
            current_facility_delinquency_days=0),
        psychometric=PsychometricMetrics(
            risk_tolerance_score=0.30,
            time_horizon_score=0.80))
    engines["__alt01__"] = (
        AlternativeCreditScoringEngine().compute(applicant))


def _assertions_alt_healthy(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.credit_alt_scoring import ConfidenceBand
    r = engines.get("__alt01__")
    if r is None:
        return (AssertionResult(
            assertion_id="alt01-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="alt01-a1",
            description="Healthy thin-file PD < 5%",
            expected="< 0.05",
            observed=str(r.composite_pd),
            matched=(
                r.composite_pd is not None
                and r.composite_pd < 0.05)),
        AssertionResult(
            assertion_id="alt01-a2",
            description="Confidence band = HIGH",
            expected=ConfidenceBand.HIGH.value,
            observed=r.confidence_band.value,
            matched=r.confidence_band == ConfidenceBand.HIGH),
        AssertionResult(
            assertion_id="alt01-a3",
            description="No bureau-check escalation needed",
            expected="False",
            observed=str(r.recommend_bureau_check),
            matched=r.recommend_bureau_check is False),
        AssertionResult(
            assertion_id="alt01-a4",
            description="Grade assigned from PD",
            expected="non-empty",
            observed=str(r.grade),
            matched=bool(r.grade)),
    )


SCENARIO_ALT_01_HEALTHY = Scenario(
    scenario_id="ALT-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-260: thin-file applicant with strong signals across "
        "all 3 pillars (12mo of stable deposits + salary cycle + "
        "24mo tenure + zero delinquency + low risk tolerance) → "
        "low PD < 5%, HIGH confidence, no bureau escalation."),
    setup=_setup_alt_healthy,
    actions=_actions_alt_healthy,
    assertions=_assertions_alt_healthy,
    requires_engines=("credit_alt_scoring",))


# ALT-02: Risky thin-file → high PD
def _setup_alt_risky(engines: EngineBundle) -> None:
    pass


def _actions_alt_risky(engines: EngineBundle) -> None:
    from utils.credit_alt_scoring import (
        AlternativeCreditScoringEngine, ThinFileApplicant,
        TransactionMetrics, BehavioralMetrics)
    applicant = ThinFileApplicant(
        applicant_id="alt-02-risky",
        transaction=TransactionMetrics(
            months_observed=6,
            monthly_deposit_cv=0.90,
            salary_cycle_signal=False,
            expense_to_deposit_ratio=1.05,
            bills_on_time_pct=0.40),
        behavioral=BehavioralMetrics(
            tenure_months=4,
            mobile_active_days_per_month=3,
            current_facility_delinquency_days=45))
    engines["__alt02__"] = (
        AlternativeCreditScoringEngine().compute(applicant))


def _assertions_alt_risky(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__alt02__")
    if r is None:
        return (AssertionResult(
            assertion_id="alt02-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="alt02-a1",
            description="Risky thin-file PD > 10%",
            expected="> 0.10",
            observed=str(r.composite_pd),
            matched=(
                r.composite_pd is not None
                and r.composite_pd > 0.10)),
        AssertionResult(
            assertion_id="alt02-a2",
            description="Psychometric pillar missing surfaced",
            expected="PSYCHOMETRIC in missing",
            observed=str(r.missing_pillars),
            matched="PSYCHOMETRIC" in r.missing_pillars),
        AssertionResult(
            assertion_id="alt02-a3",
            description="Grade reflects elevated risk (BB or worse)",
            expected="BB / B / CCC / CC / C / D",
            observed=str(r.grade),
            matched=r.grade in (
                "BB", "B", "CCC", "CC", "C", "D")),
    )


SCENARIO_ALT_02_RISKY = Scenario(
    scenario_id="ALT-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-260: thin-file applicant with weak signals (irregular "
        "deposits + bills missed + 45-day delinquency on existing "
        "facility) → PD > 10%, grade BB or worse, psychometric "
        "pillar surfaced as missing per Rule 1."),
    setup=_setup_alt_risky,
    actions=_actions_alt_risky,
    assertions=_assertions_alt_risky,
    requires_engines=("credit_alt_scoring",))


# ALT-03: Insufficient data → recommend bureau check
def _setup_alt_insufficient(engines: EngineBundle) -> None:
    pass


def _actions_alt_insufficient(engines: EngineBundle) -> None:
    from utils.credit_alt_scoring import (
        AlternativeCreditScoringEngine, ThinFileApplicant,
        PsychometricMetrics)
    # Only psychometric data — weakest pillar standalone
    applicant = ThinFileApplicant(
        applicant_id="alt-03-insufficient",
        psychometric=PsychometricMetrics(
            risk_tolerance_score=0.5, time_horizon_score=None))
    engines["__alt03__"] = (
        AlternativeCreditScoringEngine().compute(applicant))


def _assertions_alt_insufficient(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.credit_alt_scoring import ConfidenceBand
    r = engines.get("__alt03__")
    if r is None:
        return (AssertionResult(
            assertion_id="alt03-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="alt03-a1",
            description="Confidence = LOW with only weak pillar",
            expected=ConfidenceBand.LOW.value,
            observed=r.confidence_band.value,
            matched=r.confidence_band == ConfidenceBand.LOW),
        AssertionResult(
            assertion_id="alt03-a2",
            description="Recommend bureau check escalation",
            expected="True",
            observed=str(r.recommend_bureau_check),
            matched=r.recommend_bureau_check is True),
        AssertionResult(
            assertion_id="alt03-a3",
            description="Two pillars surfaced as missing",
            expected="TRANSACTION + BEHAVIORAL missing",
            observed=str(r.missing_pillars),
            matched=(
                "TRANSACTION" in r.missing_pillars
                and "BEHAVIORAL" in r.missing_pillars)),
    )


SCENARIO_ALT_03_INSUFFICIENT = Scenario(
    scenario_id="ALT-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-260: applicant with only partial psychometric data → "
        "ConfidenceBand.LOW, recommend_bureau_check=True, missing "
        "pillars surfaced explicitly per Rule 1 (no false-precision "
        "thin-file decision)."),
    setup=_setup_alt_insufficient,
    actions=_actions_alt_insufficient,
    assertions=_assertions_alt_insufficient,
    requires_engines=("credit_alt_scoring",))


# ALT-04: Provenance Rule 1 cross-check
def _setup_alt_provenance(engines: EngineBundle) -> None:
    pass


def _actions_alt_provenance(engines: EngineBundle) -> None:
    from utils.credit_alt_scoring import (
        AlternativeCreditScoringEngine, ThinFileApplicant,
        TransactionMetrics, BehavioralMetrics)
    applicant = ThinFileApplicant(
        applicant_id="alt-04-provenance",
        transaction=TransactionMetrics(
            months_observed=8, monthly_deposit_cv=0.25,
            salary_cycle_signal=True,
            expense_to_deposit_ratio=0.65,
            bills_on_time_pct=0.88),
        behavioral=BehavioralMetrics(
            tenure_months=14,
            mobile_active_days_per_month=18,
            current_facility_delinquency_days=0),
        notes="provenance-check")
    engines["__alt04__"] = (
        AlternativeCreditScoringEngine().compute(applicant))


def _assertions_alt_provenance(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__alt04__")
    if r is None:
        return (AssertionResult(
            assertion_id="alt04-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    txn = next(
        (s for s in r.pillar_scores
         if s.pillar_name == "TRANSACTION"), None)
    return (
        AssertionResult(
            assertion_id="alt04-a1",
            description="3 pillar scores returned (one may be empty)",
            expected="3",
            observed=str(len(r.pillar_scores)),
            matched=len(r.pillar_scores) == 3),
        AssertionResult(
            assertion_id="alt04-a2",
            description="Transaction features surfaced",
            expected="non-empty features list",
            observed=str(txn.features_used if txn else None),
            matched=(
                txn is not None and len(txn.features_used) >= 3)),
        AssertionResult(
            assertion_id="alt04-a3",
            description="Framework refs cite CGAP",
            expected="CGAP in refs",
            observed=", ".join(r.framework_refs),
            matched=any(
                "CGAP" in ref for ref in r.framework_refs)),
        AssertionResult(
            assertion_id="alt04-a4",
            description="Notes preserved",
            expected="provenance-check",
            observed=r.notes,
            matched=r.notes == "provenance-check"),
    )


SCENARIO_ALT_04_PROVENANCE = Scenario(
    scenario_id="ALT-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-260 Rule 1 cross-check: AltScoringResult surfaces all "
        "3 PillarScore objects with features_used + skip reasons, "
        "framework refs cite CGAP, and caller notes are preserved."),
    setup=_setup_alt_provenance,
    actions=_actions_alt_provenance,
    assertions=_assertions_alt_provenance,
    requires_engines=("credit_alt_scoring",))


# ════════════════════════════════════════════════════════════════════════
# v10.48 — Credit Committee Governance (ENH-268)
# ════════════════════════════════════════════════════════════════════════

def _build_default_committee_charter():
    from utils.credit_committee import (
        CommitteeMember, CommitteeRole, CommitteeCharter, VotingRule)
    members = (
        CommitteeMember(
            member_id="m1", name="Chair", role=CommitteeRole.CHAIR),
        CommitteeMember(
            member_id="m2", name="CRO", role=CommitteeRole.CRO),
        CommitteeMember(
            member_id="m3", name="CCO", role=CommitteeRole.CCO),
        CommitteeMember(
            member_id="m4", name="Indep1",
            role=CommitteeRole.INDEPENDENT_MEMBER,
            is_independent=True),
        CommitteeMember(
            member_id="m5", name="Indep2",
            role=CommitteeRole.INDEPENDENT_MEMBER,
            is_independent=True),
    )
    return CommitteeCharter(
        committee_id="MCC",
        name="Management Credit Committee",
        members=members,
        voting_rule=VotingRule.SIMPLE_MAJORITY,
        min_quorum_count=3,
        required_roles=frozenset({CommitteeRole.CRO}),
        authority_limit_kes=Decimal("100000000"),
        independent_member_min=1)


# COM-01: Quorum met + simple majority approves
def _setup_com_approve(engines: EngineBundle) -> None:
    pass


def _actions_com_approve(engines: EngineBundle) -> None:
    from utils.credit_committee import (
        CreditCommitteeEngine, CreditDecisionRequest, Vote, VoteValue)
    eng = CreditCommitteeEngine(_build_default_committee_charter())
    request = CreditDecisionRequest(
        request_id="req-001", borrower_id="b1",
        facility_kes=Decimal("50000000"),
        proposed_rationale="Trade finance LC for established importer")
    engines["__com01__"] = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.NO)))


def _assertions_com_approve(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.credit_committee import DecisionOutcome, QuorumStatus
    r = engines.get("__com01__")
    if r is None:
        return (AssertionResult(
            assertion_id="com01-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="com01-a1",
            description="Quorum met (CRO + 1 independent + headcount)",
            expected=QuorumStatus.MET.value,
            observed=r.quorum_status.value,
            matched=r.quorum_status == QuorumStatus.MET),
        AssertionResult(
            assertion_id="com01-a2",
            description="Simple majority approves (3 YES, 1 NO)",
            expected=DecisionOutcome.APPROVED.value,
            observed=r.outcome.value,
            matched=r.outcome == DecisionOutcome.APPROVED),
        AssertionResult(
            assertion_id="com01-a3",
            description="Vote tally surfaced correctly",
            expected="3 YES / 1 NO",
            observed=(f"{r.vote_tally.yes_count} YES / "
                      f"{r.vote_tally.no_count} NO"),
            matched=(r.vote_tally.yes_count == 3
                     and r.vote_tally.no_count == 1)),
        AssertionResult(
            assertion_id="com01-a4",
            description="No escalation needed (within authority)",
            expected="False",
            observed=str(r.escalation_required),
            matched=r.escalation_required is False),
    )


SCENARIO_COM_01_APPROVE = Scenario(
    scenario_id="COM-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-268: 4 members attend (chair + CRO + CCO + 1 indep) → "
        "quorum met; 3 YES / 1 NO under SIMPLE_MAJORITY → APPROVED; "
        "facility within authority → no escalation."),
    setup=_setup_com_approve,
    actions=_actions_com_approve,
    assertions=_assertions_com_approve,
    requires_engines=("credit_committee",))


# COM-02: Required role absent → QUORUM_FAILED
def _setup_com_quorum_fail(engines: EngineBundle) -> None:
    pass


def _actions_com_quorum_fail(engines: EngineBundle) -> None:
    from utils.credit_committee import (
        CreditCommitteeEngine, CreditDecisionRequest, Vote, VoteValue)
    eng = CreditCommitteeEngine(_build_default_committee_charter())
    request = CreditDecisionRequest(
        request_id="req-002", borrower_id="b2",
        facility_kes=Decimal("30000000"),
        proposed_rationale="x")
    # m2 (CRO) absent — required role missing
    engines["__com02__"] = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m3", "m4", "m5"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES),
            Vote(member_id="m5", vote=VoteValue.YES)))


def _assertions_com_quorum_fail(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.credit_committee import DecisionOutcome, QuorumStatus
    r = engines.get("__com02__")
    if r is None:
        return (AssertionResult(
            assertion_id="com02-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="com02-a1",
            description="Quorum failed: required role CRO absent",
            expected=QuorumStatus.NOT_MET_REQUIRED_ROLE.value,
            observed=r.quorum_status.value,
            matched=(
                r.quorum_status
                == QuorumStatus.NOT_MET_REQUIRED_ROLE)),
        AssertionResult(
            assertion_id="com02-a2",
            description="Outcome = QUORUM_FAILED",
            expected=DecisionOutcome.QUORUM_FAILED.value,
            observed=r.outcome.value,
            matched=r.outcome == DecisionOutcome.QUORUM_FAILED),
        AssertionResult(
            assertion_id="com02-a3",
            description="Quorum reason surfaces CRO absence",
            expected="contains 'CRO'",
            observed=r.quorum_reason,
            matched="CRO" in r.quorum_reason),
    )


SCENARIO_COM_02_QUORUM_FAILED = Scenario(
    scenario_id="COM-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-268: 4 members attend but CRO absent → "
        "NOT_MET_REQUIRED_ROLE per CBK PG/03 §6.4 → "
        "QUORUM_FAILED outcome, vote tally not consulted."),
    setup=_setup_com_quorum_fail,
    actions=_actions_com_quorum_fail,
    assertions=_assertions_com_quorum_fail,
    requires_engines=("credit_committee",))


# COM-03: Authority limit exceeded → ESCALATED
def _setup_com_escalate(engines: EngineBundle) -> None:
    pass


def _actions_com_escalate(engines: EngineBundle) -> None:
    from utils.credit_committee import (
        CreditCommitteeEngine, CreditDecisionRequest, Vote, VoteValue)
    eng = CreditCommitteeEngine(_build_default_committee_charter())
    request = CreditDecisionRequest(
        request_id="req-003-big", borrower_id="b3",
        facility_kes=Decimal("250000000"),    # > 100m authority
        proposed_rationale="Acquisition financing")
    engines["__com03__"] = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4", "m5"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES),
            Vote(member_id="m5", vote=VoteValue.YES)))


def _assertions_com_escalate(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.credit_committee import DecisionOutcome
    r = engines.get("__com03__")
    if r is None:
        return (AssertionResult(
            assertion_id="com03-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="com03-a1",
            description="Authority exceeded → ESCALATED outcome",
            expected=DecisionOutcome.ESCALATED.value,
            observed=r.outcome.value,
            matched=r.outcome == DecisionOutcome.ESCALATED),
        AssertionResult(
            assertion_id="com03-a2",
            description="Escalation required + target set",
            expected="True / BOARD_RISK_COMMITTEE",
            observed=(f"{r.escalation_required} / "
                      f"{r.escalation_target}"),
            matched=(
                r.escalation_required is True
                and r.escalation_target == "BOARD_RISK_COMMITTEE")),
        AssertionResult(
            assertion_id="com03-a3",
            description="Rationale cites authority limit",
            expected="contains 'authority'",
            observed=r.rationale,
            matched="authority" in r.rationale.lower()),
    )


SCENARIO_COM_03_ESCALATED = Scenario(
    scenario_id="COM-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-268: facility KES 250m exceeds committee authority "
        "limit KES 100m — ESCALATED to BOARD_RISK_COMMITTEE without "
        "in-room vote (5 unanimous YES votes ignored; authority "
        "check supersedes)."),
    setup=_setup_com_escalate,
    actions=_actions_com_escalate,
    assertions=_assertions_com_escalate,
    requires_engines=("credit_committee",))


# COM-04: Policy override approval triggers escalation per §6.7
def _setup_com_override(engines: EngineBundle) -> None:
    pass


def _actions_com_override(engines: EngineBundle) -> None:
    from utils.credit_committee import (
        CreditCommitteeEngine, CreditDecisionRequest, Vote, VoteValue)
    eng = CreditCommitteeEngine(_build_default_committee_charter())
    request = CreditDecisionRequest(
        request_id="req-004-override", borrower_id="b4",
        facility_kes=Decimal("80000000"),
        proposed_rationale="Strategic anchor client renewal",
        is_policy_override=True,
        override_rationale="LTV 92% vs policy max 80%; "
                           "secured by additional personal guarantee "
                           "from director")
    engines["__com04__"] = eng.evaluate(
        request=request,
        attending_member_ids=("m1", "m2", "m3", "m4"),
        votes=(
            Vote(member_id="m1", vote=VoteValue.YES),
            Vote(member_id="m2", vote=VoteValue.YES),
            Vote(member_id="m3", vote=VoteValue.YES),
            Vote(member_id="m4", vote=VoteValue.YES)),
        notes="provenance-check")


def _assertions_com_override(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.credit_committee import DecisionOutcome
    r = engines.get("__com04__")
    if r is None:
        return (AssertionResult(
            assertion_id="com04-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="com04-a1",
            description="Override approval = APPROVED outcome",
            expected=DecisionOutcome.APPROVED.value,
            observed=r.outcome.value,
            matched=r.outcome == DecisionOutcome.APPROVED),
        AssertionResult(
            assertion_id="com04-a2",
            description="Policy override flag preserved",
            expected="True",
            observed=str(r.is_policy_override),
            matched=r.is_policy_override is True),
        AssertionResult(
            assertion_id="com04-a3",
            description="Override → escalation required per §6.7",
            expected="True / BOARD_RISK_COMMITTEE",
            observed=(f"{r.escalation_required} / "
                      f"{r.escalation_target}"),
            matched=(
                r.escalation_required is True
                and r.escalation_target == "BOARD_RISK_COMMITTEE")),
        AssertionResult(
            assertion_id="com04-a4",
            description="Rationale embeds override text",
            expected="contains 'POLICY OVERRIDE'",
            observed=r.rationale,
            matched="POLICY OVERRIDE" in r.rationale),
        AssertionResult(
            assertion_id="com04-a5",
            description="Framework refs cite §6.7",
            expected="§6.7 in refs",
            observed=", ".join(r.framework_refs),
            matched=any("§6.7" in ref for ref in r.framework_refs)),
    )


SCENARIO_COM_04_POLICY_OVERRIDE = Scenario(
    scenario_id="COM-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-268: policy override (LTV 92% vs 80% max) approved by "
        "unanimous committee → APPROVED + escalation_required=True "
        "per CBK PG/03 §6.7 (override approvals must be reported "
        "upward); rationale embeds override text + Rule 1 "
        "framework refs cite §6.7."),
    setup=_setup_com_override,
    actions=_actions_com_override,
    assertions=_assertions_com_override,
    requires_engines=("credit_committee",))


# ════════════════════════════════════════════════════════════════════════
# v10.50 — Validation Agents (ENH-241) · revenue_assurance arc opens
# ════════════════════════════════════════════════════════════════════════

# RA-01: Clean records → schema agent reports zero findings
def _setup_ra_clean(engines: EngineBundle) -> None:
    pass


def _actions_ra_clean(engines: EngineBundle) -> None:
    from utils.revenue_validation import (
        RevenueValidationEngine, RevenueRecord)
    from datetime import date as _date
    eng = RevenueValidationEngine()
    records = tuple(
        RevenueRecord(
            record_id=f"r{i}", source_system="CBS",
            posting_date=_date(2026, 4, i),
            amount_kes=Decimal(str(1000 + i * 50)),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01")
        for i in range(1, 11))
    engines["__ra01__"] = eng.validate_all(
        records, as_of=_date(2026, 4, 30))


def _assertions_ra_clean(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__ra01__")
    if r is None:
        return (AssertionResult(
            assertion_id="ra01-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="ra01-a1",
            description="Schema agent: zero findings on clean records",
            expected="0",
            observed=str(r.schema_count),
            matched=r.schema_count == 0),
        AssertionResult(
            assertion_id="ra01-a2",
            description="No CRITICAL findings",
            expected="0",
            observed=str(r.by_severity["CRITICAL"]),
            matched=r.by_severity["CRITICAL"] == 0),
        AssertionResult(
            assertion_id="ra01-a3",
            description="All 10 records validated",
            expected="10",
            observed=str(r.records_validated),
            matched=r.records_validated == 10),
    )


SCENARIO_RA_01_CLEAN = Scenario(
    scenario_id="RA-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-241: 10 clean revenue records (positive amounts, "
        "valid category, past-dated) → 0 schema findings, 0 "
        "CRITICAL, all records validated. Baseline happy path."),
    setup=_setup_ra_clean,
    actions=_actions_ra_clean,
    assertions=_assertions_ra_clean,
    requires_engines=("revenue_validation",))


# RA-02: Schema violations surfaced
def _setup_ra_schema_violations(engines: EngineBundle) -> None:
    pass


def _actions_ra_schema_violations(engines: EngineBundle) -> None:
    from utils.revenue_validation import (
        RevenueValidationEngine, RevenueRecord)
    from datetime import date as _date
    eng = RevenueValidationEngine()
    # 3 violations: negative amount, unknown category, future date
    records = (
        RevenueRecord(
            record_id="r-neg", source_system="CBS",
            posting_date=_date(2026, 4, 1),
            amount_kes=Decimal("-500"),
            revenue_category="FEE_INCOME"),
        RevenueRecord(
            record_id="r-unknown-cat", source_system="CBS",
            posting_date=_date(2026, 4, 2),
            amount_kes=Decimal("1000"),
            revenue_category="MYSTERY_REVENUE"),
        RevenueRecord(
            record_id="r-future", source_system="CBS",
            posting_date=_date(2027, 1, 1),
            amount_kes=Decimal("1000"),
            revenue_category="FEE_INCOME"),
    )
    engines["__ra02__"] = eng.validate_schema(
        records, as_of=_date(2026, 5, 1))


def _assertions_ra_schema_violations(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_validation import (
        ValidationSeverity, ValidationCategory)
    findings = engines.get("__ra02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="ra02-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    crit = [
        f for f in findings
        if f.severity == ValidationSeverity.CRITICAL]
    high = [
        f for f in findings
        if f.severity == ValidationSeverity.HIGH]
    return (
        AssertionResult(
            assertion_id="ra02-a1",
            description="3 schema findings (one per violation)",
            expected="3",
            observed=str(len(findings)),
            matched=len(findings) == 3),
        AssertionResult(
            assertion_id="ra02-a2",
            description="Negative-amount → CRITICAL severity",
            expected="1 CRITICAL",
            observed=str(len(crit)),
            matched=len(crit) == 1),
        AssertionResult(
            assertion_id="ra02-a3",
            description=(
                "Unknown category + future date → 2 HIGH "
                "severity"),
            expected="2 HIGH",
            observed=str(len(high)),
            matched=len(high) == 2),
        AssertionResult(
            assertion_id="ra02-a4",
            description="All findings are SCHEMA category",
            expected="all SCHEMA",
            observed=", ".join(
                f.category.value for f in findings),
            matched=all(
                f.category == ValidationCategory.SCHEMA
                for f in findings)),
    )


SCENARIO_RA_02_SCHEMA_VIOLATIONS = Scenario(
    scenario_id="RA-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-241: 3 schema violations (negative amount → CRITICAL, "
        "unknown revenue_category → HIGH, future posting_date → "
        "HIGH) → 3 SCHEMA findings, 1 CRITICAL + 2 HIGH, no "
        "silent dropping per Rule 7."),
    setup=_setup_ra_schema_violations,
    actions=_actions_ra_schema_violations,
    assertions=_assertions_ra_schema_violations,
    requires_engines=("revenue_validation",))


# RA-03: Cross-source reconciliation mismatch
def _setup_ra_recon(engines: EngineBundle) -> None:
    pass


def _actions_ra_recon(engines: EngineBundle) -> None:
    from utils.revenue_validation import (
        RevenueValidationEngine, CrossSourceTotal)
    eng = RevenueValidationEngine()
    cbs_totals = (
        CrossSourceTotal(
            source_system="CBS", period="2026-04",
            revenue_category="FEE_INCOME",
            total_kes=Decimal("10000000"), record_count=500),
        CrossSourceTotal(
            source_system="CBS", period="2026-04",
            revenue_category="INTEREST_INCOME",
            total_kes=Decimal("50000000"), record_count=1000),
    )
    gl_totals = (
        # Within tolerance — should match
        CrossSourceTotal(
            source_system="GL", period="2026-04",
            revenue_category="FEE_INCOME",
            total_kes=Decimal("10003000"), record_count=500),
        # Outside tolerance (10% diff) — should mismatch
        CrossSourceTotal(
            source_system="GL", period="2026-04",
            revenue_category="INTEREST_INCOME",
            total_kes=Decimal("55000000"), record_count=1000),
        # Missing in CBS
        CrossSourceTotal(
            source_system="GL", period="2026-04",
            revenue_category="FX_INCOME",
            total_kes=Decimal("2000000"), record_count=80),
    )
    engines["__ra03__"] = eng.reconcile_sources(
        cbs_totals, gl_totals)


def _assertions_ra_recon(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_validation import (
        ValidationSeverity, ValidationCategory)
    findings = engines.get("__ra03__")
    if findings is None:
        return (AssertionResult(
            assertion_id="ra03-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="ra03-a1",
            description=(
                "2 reconciliation findings (1 amount mismatch + 1 "
                "missing-in-CBS); FEE_INCOME within tolerance → "
                "no finding"),
            expected="2",
            observed=str(len(findings)),
            matched=len(findings) == 2),
        AssertionResult(
            assertion_id="ra03-a2",
            description=(
                "Amount-mismatch finding is MEDIUM severity"),
            expected="1 MEDIUM",
            observed=str(sum(
                1 for f in findings
                if f.severity == ValidationSeverity.MEDIUM)),
            matched=sum(
                1 for f in findings
                if f.severity == ValidationSeverity.MEDIUM) == 1),
        AssertionResult(
            assertion_id="ra03-a3",
            description=(
                "Missing-in-source finding is HIGH severity"),
            expected="1 HIGH",
            observed=str(sum(
                1 for f in findings
                if f.severity == ValidationSeverity.HIGH)),
            matched=sum(
                1 for f in findings
                if f.severity == ValidationSeverity.HIGH) == 1),
        AssertionResult(
            assertion_id="ra03-a4",
            description=(
                "All findings are RECONCILIATION category"),
            expected="all RECONCILIATION",
            observed=", ".join(
                f.category.value for f in findings),
            matched=all(
                f.category == ValidationCategory.RECONCILIATION
                for f in findings)),
    )


SCENARIO_RA_03_RECON_MISMATCH = Scenario(
    scenario_id="RA-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-241: CBS vs GL reconciliation across 3 categories. "
        "FEE_INCOME within 5bp tolerance → no finding; "
        "INTEREST_INCOME 10% diff → MEDIUM amount-mismatch; "
        "FX_INCOME present in GL only → HIGH missing-in-CBS. "
        "Total: 2 RECONCILIATION findings (Rule 1 — both sources' "
        "totals surfaced in observed field)."),
    setup=_setup_ra_recon,
    actions=_actions_ra_recon,
    assertions=_assertions_ra_recon,
    requires_engines=("revenue_validation",))


# RA-04: Statistical anomaly detection
def _setup_ra_anomaly(engines: EngineBundle) -> None:
    pass


def _actions_ra_anomaly(engines: EngineBundle) -> None:
    from utils.revenue_validation import (
        RevenueValidationEngine, RevenueRecord)
    from datetime import date as _date
    eng = RevenueValidationEngine()
    # 12 normal records around 1000-1200, plus 1 outlier at 100000
    normal = [
        RevenueRecord(
            record_id=f"r{i}", source_system="CBS",
            posting_date=_date(2026, 4, i),
            amount_kes=Decimal(str(1000 + i * 15)),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01")
        for i in range(1, 13)]
    outlier = RevenueRecord(
        record_id="r-outlier", source_system="CBS",
        posting_date=_date(2026, 4, 13),
        amount_kes=Decimal("100000"),
        revenue_category="FEE_INCOME",
        branch_code="NRB-01")
    records = tuple(normal + [outlier])
    engines["__ra04__"] = eng.detect_anomalies(records)


def _assertions_ra_anomaly(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_validation import ValidationCategory
    findings = engines.get("__ra04__")
    if findings is None:
        return (AssertionResult(
            assertion_id="ra04-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    outlier_findings = [
        f for f in findings
        if f.record_id_or_batch_id == "r-outlier"]
    return (
        AssertionResult(
            assertion_id="ra04-a1",
            description="Outlier record surfaced",
            expected="≥ 1 finding for r-outlier",
            observed=str(len(outlier_findings)),
            matched=len(outlier_findings) >= 1),
        AssertionResult(
            assertion_id="ra04-a2",
            description=(
                "Anomaly finding is ANOMALY category"),
            expected="ANOMALY",
            observed=(
                outlier_findings[0].category.value
                if outlier_findings else "n/a"),
            matched=(
                len(outlier_findings) >= 1
                and outlier_findings[0].category
                == ValidationCategory.ANOMALY)),
        AssertionResult(
            assertion_id="ra04-a3",
            description=(
                "Finding observed field surfaces z-score"),
            expected="contains 'z ='",
            observed=(
                outlier_findings[0].observed
                if outlier_findings else "n/a"),
            matched=(
                len(outlier_findings) >= 1
                and "z =" in outlier_findings[0].observed)),
        AssertionResult(
            assertion_id="ra04-a4",
            description=(
                "Framework refs cite z-score screening"),
            expected="z-score in refs",
            observed=(
                ", ".join(outlier_findings[0].framework_refs)
                if outlier_findings else "n/a"),
            matched=(
                len(outlier_findings) >= 1
                and any(
                    "z-score" in ref.lower()
                    for ref in outlier_findings[0].framework_refs))),
    )


SCENARIO_RA_04_ANOMALY = Scenario(
    scenario_id="RA-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-241: 12 normal records around 1000-1200 + 1 outlier "
        "at 100000 (FEE_INCOME / NRB-01) → anomaly agent flags "
        "the outlier with z-score in observed field; framework "
        "refs cite z-score screening per Rule 1."),
    setup=_setup_ra_anomaly,
    actions=_actions_ra_anomaly,
    assertions=_assertions_ra_anomaly,
    requires_engines=("revenue_validation",))


# ════════════════════════════════════════════════════════════════════════
# v10.51 — Anomaly Pattern Detection (ENH-242)
# ════════════════════════════════════════════════════════════════════════

# PAT-01: Duplicate billing detection
def _setup_pat_duplicates(engines: EngineBundle) -> None:
    pass


def _actions_pat_duplicates(engines: EngineBundle) -> None:
    from utils.revenue_anomaly_patterns import (
        RevenueAnomalyPatternEngine, RevenueRecordWithContext)
    from utils.revenue_validation import RevenueRecord
    from datetime import date as _date
    eng = RevenueAnomalyPatternEngine()
    def mk(rid, day, amt, cust):
        return RevenueRecordWithContext(
            record=RevenueRecord(
                record_id=rid, source_system="CBS",
                posting_date=_date(2026, 4, day),
                amount_kes=Decimal(str(amt)),
                revenue_category="FEE_INCOME",
                branch_code="NRB-01"),
            customer_id=cust)
    records = (
        mk("r1", 1, 1500, "cust-A"),
        mk("r2", 1, 1500, "cust-A"),  # duplicate
        mk("r3", 1, 1500, "cust-A"),  # triplicate → HIGH
        mk("r4", 2, 2000, "cust-B"),
    )
    engines["__pat01__"] = eng.detect_duplicate_billings(records)


def _assertions_pat_duplicates(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_anomaly_patterns import (
        PatternId, PatternFamily)
    from utils.revenue_validation import ValidationSeverity
    findings = engines.get("__pat01__")
    if findings is None:
        return (AssertionResult(
            assertion_id="pat01-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="pat01-a1",
            description="Triplicate detected",
            expected="1 finding",
            observed=str(len(findings)),
            matched=len(findings) == 1),
        AssertionResult(
            assertion_id="pat01-a2",
            description="Triplicate severity = HIGH",
            expected=ValidationSeverity.HIGH.value,
            observed=(
                findings[0].severity.value if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].severity == ValidationSeverity.HIGH)),
        AssertionResult(
            assertion_id="pat01-a3",
            description="Pattern = DUPLICATE_BILLING",
            expected=PatternId.DUPLICATE_BILLING.value,
            observed=(
                findings[0].pattern_id.value
                if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].pattern_id == PatternId.DUPLICATE_BILLING)),
        AssertionResult(
            assertion_id="pat01-a4",
            description="All 3 duplicate record_ids surfaced",
            expected="r1, r2, r3 in record_ids",
            observed=(
                str(findings[0].record_ids)
                if findings else "n/a"),
            matched=(
                len(findings) == 1
                and set(findings[0].record_ids) == {"r1", "r2", "r3"})),
    )


SCENARIO_PAT_01_DUPLICATES = Scenario(
    scenario_id="PAT-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-242: 3 records share (cust-A, KES 1500, 2026-04-01) "
        "→ 1 DUPLICATE_BILLING finding with HIGH severity (3+ "
        "records = HIGH per detector); record_ids tuple surfaces "
        "all 3 involved IDs per Rule 1."),
    setup=_setup_pat_duplicates,
    actions=_actions_pat_duplicates,
    assertions=_assertions_pat_duplicates,
    requires_engines=("revenue_anomaly_patterns",))


# PAT-02: Rate-card breach detection (both floor + ceiling)
def _setup_pat_rate_breach(engines: EngineBundle) -> None:
    pass


def _actions_pat_rate_breach(engines: EngineBundle) -> None:
    from utils.revenue_anomaly_patterns import (
        RevenueAnomalyPatternEngine, ContractRate,
        RevenueRecordWithContext)
    from utils.revenue_validation import RevenueRecord
    from datetime import date as _date
    eng = RevenueAnomalyPatternEngine()
    contract = ContractRate(
        contract_id="C-001", customer_id="cust-A",
        product_code="LOAN", floor_rate_pct=Decimal("3.0"),
        ceiling_rate_pct=Decimal("8.0"),
        effective_from=_date(2025, 1, 1),
        effective_to=_date(2027, 12, 31))
    def mk(rid, applied):
        return RevenueRecordWithContext(
            record=RevenueRecord(
                record_id=rid, source_system="CBS",
                posting_date=_date(2026, 4, 15),
                amount_kes=Decimal("10000"),
                revenue_category="INTEREST_INCOME",
                branch_code="NRB-01"),
            customer_id="cust-A", contract_id="C-001",
            applied_rate_pct=Decimal(str(applied)))
    records = (
        mk("r-low", "2.0"),       # below floor
        mk("r-mid", "5.0"),       # within band
        mk("r-high", "9.5"),      # above ceiling
    )
    engines["__pat02__"] = eng.detect_rate_card_breaches(
        records, (contract,))


def _assertions_pat_rate_breach(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_anomaly_patterns import PatternId
    from utils.revenue_validation import ValidationSeverity
    findings = engines.get("__pat02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="pat02-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    by_pid = {f.pattern_id for f in findings}
    sev_ceil = next(
        (f.severity for f in findings
         if f.pattern_id == PatternId.RATE_ABOVE_CEILING), None)
    return (
        AssertionResult(
            assertion_id="pat02-a1",
            description="2 findings (floor breach + ceiling breach)",
            expected="2",
            observed=str(len(findings)),
            matched=len(findings) == 2),
        AssertionResult(
            assertion_id="pat02-a2",
            description="Both RATE_BELOW_FLOOR + RATE_ABOVE_CEILING",
            expected="both pattern_ids present",
            observed=str(by_pid),
            matched=(
                PatternId.RATE_BELOW_FLOOR in by_pid
                and PatternId.RATE_ABOVE_CEILING in by_pid)),
        AssertionResult(
            assertion_id="pat02-a3",
            description="Ceiling breach = HIGH severity",
            expected=ValidationSeverity.HIGH.value,
            observed=(
                sev_ceil.value if sev_ceil else "n/a"),
            matched=sev_ceil == ValidationSeverity.HIGH),
    )


SCENARIO_PAT_02_RATE_BREACH = Scenario(
    scenario_id="PAT-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-242: 3 records under contract C-001 [3.0%, 8.0%]: "
        "2.0% applied → RATE_BELOW_FLOOR (MEDIUM leakage); "
        "5.0% → no finding (within band); 9.5% → RATE_ABOVE_"
        "CEILING (HIGH compliance breach). 2 findings total."),
    setup=_setup_pat_rate_breach,
    actions=_actions_pat_rate_breach,
    assertions=_assertions_pat_rate_breach,
    requires_engines=("revenue_anomaly_patterns",))


# PAT-03: Commission anomalies (both over + under)
def _setup_pat_commission(engines: EngineBundle) -> None:
    pass


def _actions_pat_commission(engines: EngineBundle) -> None:
    from utils.revenue_anomaly_patterns import (
        RevenueAnomalyPatternEngine, CommissionRecord)
    from datetime import date as _date
    eng = RevenueAnomalyPatternEngine()
    commissions = (
        CommissionRecord(
            commission_id="C1", rm_code="rm1",
            underlying_revenue_kes=Decimal("100000"),
            paid_commission_kes=Decimal("6000"),
            expected_commission_kes=Decimal("5000"),
            posting_date=_date(2026, 4, 1)),    # over by 1000
        CommissionRecord(
            commission_id="C2", rm_code="rm2",
            underlying_revenue_kes=Decimal("80000"),
            paid_commission_kes=Decimal("3500"),
            expected_commission_kes=Decimal("4000"),
            posting_date=_date(2026, 4, 1)),    # under by 500
        CommissionRecord(
            commission_id="C3", rm_code="rm3",
            underlying_revenue_kes=Decimal("50000"),
            paid_commission_kes=Decimal("2500.50"),
            expected_commission_kes=Decimal("2500"),
            posting_date=_date(2026, 4, 1)),    # within tolerance
    )
    engines["__pat03__"] = eng.detect_commission_anomalies(
        commissions)


def _assertions_pat_commission(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_anomaly_patterns import (
        PatternId, PatternFamily)
    findings = engines.get("__pat03__")
    if findings is None:
        return (AssertionResult(
            assertion_id="pat03-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    pids = {f.pattern_id for f in findings}
    return (
        AssertionResult(
            assertion_id="pat03-a1",
            description="2 commission findings (within-tolerance skipped)",
            expected="2",
            observed=str(len(findings)),
            matched=len(findings) == 2),
        AssertionResult(
            assertion_id="pat03-a2",
            description="Both OVERPAYMENT + UNDERPAYMENT surfaced",
            expected="both pattern_ids present",
            observed=str(pids),
            matched=(
                PatternId.COMMISSION_OVERPAYMENT in pids
                and PatternId.COMMISSION_UNDERPAYMENT in pids)),
        AssertionResult(
            assertion_id="pat03-a3",
            description="All findings in COMMISSION_MISCALC family",
            expected="all COMMISSION_MISCALC",
            observed=", ".join(f.family.value for f in findings),
            matched=all(
                f.family == PatternFamily.COMMISSION_MISCALC
                for f in findings)),
    )


SCENARIO_PAT_03_COMMISSION = Scenario(
    scenario_id="PAT-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-242: 3 commissions: C1 paid 6000 vs expected 5000 → "
        "OVERPAYMENT MEDIUM; C2 paid 3500 vs expected 4000 → "
        "UNDERPAYMENT MEDIUM; C3 within KES 1 tolerance → no "
        "finding. Both halves of the miscalc spectrum surface."),
    setup=_setup_pat_commission,
    actions=_actions_pat_commission,
    assertions=_assertions_pat_commission,
    requires_engines=("revenue_anomaly_patterns",))


# PAT-04: ML hook disabled by default + Rule 1 provenance
def _setup_pat_ml_disabled(engines: EngineBundle) -> None:
    pass


def _actions_pat_ml_disabled(engines: EngineBundle) -> None:
    from utils.revenue_anomaly_patterns import (
        RevenueAnomalyPatternEngine, RevenueRecordWithContext)
    from utils.revenue_validation import RevenueRecord
    from datetime import date as _date
    eng = RevenueAnomalyPatternEngine()
    records = (
        RevenueRecordWithContext(
            record=RevenueRecord(
                record_id="r1", source_system="CBS",
                posting_date=_date(2026, 4, 1),
                amount_kes=Decimal("1000"),
                revenue_category="FEE_INCOME",
                branch_code="NRB-01"),
            customer_id="cust-A",
            waiver_flag=True,
            waiver_authorization_id=None),  # leakage finding
    )
    engines["__pat04__"] = eng.detect_all(records)


def _assertions_pat_ml_disabled(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__pat04__")
    if r is None:
        return (AssertionResult(
            assertion_id="pat04-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="pat04-a1",
            description=(
                "ML disabled flag True per Rule 6 (no silent "
                "fallback)"),
            expected="True",
            observed=str(r.ml_disabled),
            matched=r.ml_disabled is True),
        AssertionResult(
            assertion_id="pat04-a2",
            description="ml_disabled_reason populated",
            expected="non-empty",
            observed=r.ml_disabled_reason,
            matched=bool(r.ml_disabled_reason)),
        AssertionResult(
            assertion_id="pat04-a3",
            description=(
                "Rule-based leakage finding still surfaced "
                "(unauthorized waiver)"),
            expected="1 LEAKAGE finding",
            observed=str(r.by_family["LEAKAGE"]),
            matched=r.by_family["LEAKAGE"] == 1),
        AssertionResult(
            assertion_id="pat04-a4",
            description="records_scanned reflected in report",
            expected="1",
            observed=str(r.records_scanned),
            matched=r.records_scanned == 1),
    )


SCENARIO_PAT_04_ML_DISABLED = Scenario(
    scenario_id="PAT-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-242 Rule 6 cross-check: detect_all without ml_score_fn "
        "returns ml_disabled=True with non-empty reason; rule-based "
        "detectors still fire (unauthorized waiver flagged); "
        "records_scanned count surfaced. No silent fallback to "
        "rule-only output without disclosing it."),
    setup=_setup_pat_ml_disabled,
    actions=_actions_pat_ml_disabled,
    assertions=_assertions_pat_ml_disabled,
    requires_engines=("revenue_anomaly_patterns",))


# ════════════════════════════════════════════════════════════════════════
# v10.52 — Revenue Agentic Orchestrator (ENH-243)
# ════════════════════════════════════════════════════════════════════════

def _build_default_orchestrator_config():
    from utils.revenue_orchestrator import (
        OrchestratorConfig, TriageRule, InvestigatorTeam)
    from utils.revenue_validation import ValidationSeverity
    rules = (
        TriageRule(
            family_or_category="LEAKAGE",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.REVENUE_RECOVERY,
            sla_days=7),
        TriageRule(
            family_or_category="LEAKAGE",
            severity=ValidationSeverity.MEDIUM,
            team=InvestigatorTeam.REVENUE_RECOVERY,
            sla_days=14),
        TriageRule(
            family_or_category="BILLING_ERROR",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.OPERATIONS, sla_days=14),
        TriageRule(
            family_or_category="RATE_CARD_BREACH",
            severity=ValidationSeverity.HIGH,
            team=InvestigatorTeam.COMPLIANCE, sla_days=7),
        TriageRule(
            family_or_category="COMMISSION_MISCALC",
            severity=ValidationSeverity.MEDIUM,
            team=InvestigatorTeam.HR_PAYROLL, sla_days=21),
        TriageRule(
            family_or_category="SCHEMA",
            severity=ValidationSeverity.CRITICAL,
            team=InvestigatorTeam.DATA_QUALITY, sla_days=3),
        TriageRule(
            family_or_category="RECONCILIATION",
            severity=ValidationSeverity.MEDIUM,
            team=InvestigatorTeam.FINANCE, sla_days=14),
    )
    return OrchestratorConfig(triage_rules=rules)


def _make_pattern_finding(fid, sev, family):
    from utils.revenue_anomaly_patterns import (
        PatternFinding, PatternId)
    return PatternFinding(
        finding_id=fid,
        pattern_id=PatternId.DUPLICATE_BILLING,
        family=family, severity=sev,
        record_ids=(f"rec-{fid}",),
        description=f"pattern {fid}",
        evidence="rule fired",
        confidence=Decimal("1"),
        framework_refs=("ENH-242",))


def _make_validation_finding(fid, sev, cat):
    from utils.revenue_validation import ValidationFinding
    return ValidationFinding(
        finding_id=fid, severity=sev, category=cat,
        record_id_or_batch_id=f"rec-{fid}",
        description=f"validation {fid}",
        expected="x", observed="y",
        framework_refs=("ENH-241",))


# ORC-01: Cross-engine routing — VALIDATION via category, PATTERN via family
def _setup_orc_routing(engines: EngineBundle) -> None:
    pass


def _actions_orc_routing(engines: EngineBundle) -> None:
    from utils.revenue_orchestrator import RevenueOrchestrator
    from utils.revenue_validation import (
        ValidationSeverity, ValidationCategory)
    from utils.revenue_anomaly_patterns import PatternFamily
    from datetime import date as _date
    eng = RevenueOrchestrator(_build_default_orchestrator_config())
    findings = (
        _make_validation_finding(
            "v1", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
        _make_pattern_finding(
            "p1", ValidationSeverity.HIGH,
            PatternFamily.LEAKAGE),
        _make_pattern_finding(
            "p2", ValidationSeverity.HIGH,
            PatternFamily.RATE_CARD_BREACH),
    )
    engines["__orc01__"] = eng.orchestrate(
        findings=findings,
        raised_dates={
            "v1": _date(2026, 4, 1),
            "p1": _date(2026, 4, 1),
            "p2": _date(2026, 4, 1)},
        as_of=_date(2026, 4, 5))


def _assertions_orc_routing(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_orchestrator import (
        InvestigatorTeam, FindingType)
    r = engines.get("__orc01__")
    if r is None:
        return (AssertionResult(
            assertion_id="orc01-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    by_id = {w.source_finding_id: w for w in r.work_items}
    return (
        AssertionResult(
            assertion_id="orc01-a1",
            description=(
                "VALIDATION SCHEMA CRITICAL → DATA_QUALITY"),
            expected=InvestigatorTeam.DATA_QUALITY.value,
            observed=(
                by_id["v1"].assigned_team.value
                if "v1" in by_id else "MISSING"),
            matched=(
                "v1" in by_id
                and by_id["v1"].assigned_team
                == InvestigatorTeam.DATA_QUALITY)),
        AssertionResult(
            assertion_id="orc01-a2",
            description=(
                "PATTERN LEAKAGE HIGH → REVENUE_RECOVERY"),
            expected=InvestigatorTeam.REVENUE_RECOVERY.value,
            observed=(
                by_id["p1"].assigned_team.value
                if "p1" in by_id else "MISSING"),
            matched=(
                "p1" in by_id
                and by_id["p1"].assigned_team
                == InvestigatorTeam.REVENUE_RECOVERY)),
        AssertionResult(
            assertion_id="orc01-a3",
            description=(
                "PATTERN RATE_CARD_BREACH HIGH → COMPLIANCE"),
            expected=InvestigatorTeam.COMPLIANCE.value,
            observed=(
                by_id["p2"].assigned_team.value
                if "p2" in by_id else "MISSING"),
            matched=(
                "p2" in by_id
                and by_id["p2"].assigned_team
                == InvestigatorTeam.COMPLIANCE)),
        AssertionResult(
            assertion_id="orc01-a4",
            description=(
                "Source-finding-type tag preserved per Rule 1"),
            expected="VALIDATION + PATTERN tags present",
            observed=", ".join(
                f"{w.source_finding_id}:"
                f"{w.source_finding_type.value}"
                for w in r.work_items),
            matched=(
                by_id.get("v1") is not None
                and by_id["v1"].source_finding_type
                == FindingType.VALIDATION
                and by_id.get("p1") is not None
                and by_id["p1"].source_finding_type
                == FindingType.PATTERN)),
    )


SCENARIO_ORC_01_CROSS_ENGINE_ROUTING = Scenario(
    scenario_id="ORC-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-243: heterogeneous findings (1 ValidationFinding + 2 "
        "PatternFinding) routed to 3 different teams via category "
        "+ family extraction; FindingType tag preserved per Rule "
        "1 source provenance."),
    setup=_setup_orc_routing,
    actions=_actions_orc_routing,
    assertions=_assertions_orc_routing,
    requires_engines=("revenue_orchestrator",))


# ORC-02: Past-SLA flagging
def _setup_orc_sla(engines: EngineBundle) -> None:
    pass


def _actions_orc_sla(engines: EngineBundle) -> None:
    from utils.revenue_orchestrator import RevenueOrchestrator
    from utils.revenue_validation import ValidationSeverity
    from utils.revenue_anomaly_patterns import PatternFamily
    from datetime import date as _date
    eng = RevenueOrchestrator(_build_default_orchestrator_config())
    # LEAKAGE HIGH SLA = 7 days
    findings = (
        _make_pattern_finding(
            "stale", ValidationSeverity.HIGH,
            PatternFamily.LEAKAGE),
        _make_pattern_finding(
            "fresh", ValidationSeverity.HIGH,
            PatternFamily.LEAKAGE),
    )
    engines["__orc02__"] = eng.orchestrate(
        findings=findings,
        raised_dates={
            "stale": _date(2026, 3, 1),     # ~45 days old
            "fresh": _date(2026, 4, 14)},   # 1 day old
        as_of=_date(2026, 4, 15))


def _assertions_orc_sla(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__orc02__")
    if r is None:
        return (AssertionResult(
            assertion_id="orc02-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    by_id = {w.source_finding_id: w for w in r.work_items}
    stale = by_id.get("stale")
    fresh = by_id.get("fresh")
    return (
        AssertionResult(
            assertion_id="orc02-a1",
            description="Stale finding flagged past_sla",
            expected="True",
            observed=str(stale.past_sla) if stale else "MISSING",
            matched=stale is not None and stale.past_sla is True),
        AssertionResult(
            assertion_id="orc02-a2",
            description="Fresh finding within SLA",
            expected="False",
            observed=str(fresh.past_sla) if fresh else "MISSING",
            matched=fresh is not None and fresh.past_sla is False),
        AssertionResult(
            assertion_id="orc02-a3",
            description="Report past_sla_count = 1",
            expected="1",
            observed=str(r.past_sla_count),
            matched=r.past_sla_count == 1),
        AssertionResult(
            assertion_id="orc02-a4",
            description=(
                "age_days computed correctly for stale (~45 days)"),
            expected="≥ 40",
            observed=str(stale.age_days) if stale else "MISSING",
            matched=stale is not None and stale.age_days >= 40),
    )


SCENARIO_ORC_02_PAST_SLA = Scenario(
    scenario_id="ORC-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-243: 2 LEAKAGE HIGH findings (7-day SLA): one raised "
        "45 days ago → past_sla=True; one raised yesterday → "
        "past_sla=False. Report past_sla_count=1. Engine flags "
        "but never auto-escalates per Rule 7 — caller workflow "
        "drives state transitions."),
    setup=_setup_orc_sla,
    actions=_actions_orc_sla,
    assertions=_assertions_orc_sla,
    requires_engines=("revenue_orchestrator",))


# ORC-03: Priority sort order
def _setup_orc_priority(engines: EngineBundle) -> None:
    pass


def _actions_orc_priority(engines: EngineBundle) -> None:
    from utils.revenue_orchestrator import RevenueOrchestrator
    from utils.revenue_validation import (
        ValidationSeverity, ValidationCategory)
    from utils.revenue_anomaly_patterns import PatternFamily
    from datetime import date as _date
    eng = RevenueOrchestrator(_build_default_orchestrator_config())
    findings = (
        _make_pattern_finding(
            "low", ValidationSeverity.LOW,
            PatternFamily.BILLING_ERROR),
        _make_validation_finding(
            "crit", ValidationSeverity.CRITICAL,
            ValidationCategory.SCHEMA),
        _make_pattern_finding(
            "med", ValidationSeverity.MEDIUM,
            PatternFamily.LEAKAGE),
        _make_pattern_finding(
            "high", ValidationSeverity.HIGH,
            PatternFamily.LEAKAGE),
    )
    engines["__orc03__"] = eng.orchestrate(
        findings=findings,
        raised_dates={
            "low": _date(2026, 4, 1),
            "crit": _date(2026, 4, 1),
            "med": _date(2026, 4, 1),
            "high": _date(2026, 4, 1)},
        as_of=_date(2026, 4, 2))


def _assertions_orc_priority(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__orc03__")
    if r is None:
        return (AssertionResult(
            assertion_id="orc03-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    ids = [w.source_finding_id for w in r.work_items]
    return (
        AssertionResult(
            assertion_id="orc03-a1",
            description=(
                "All 4 work items present, sorted desc by priority"),
            expected="4 items",
            observed=str(len(ids)),
            matched=len(ids) == 4),
        AssertionResult(
            assertion_id="orc03-a2",
            description=(
                "First item highest severity (CRITICAL or HIGH "
                "depending on family weight)"),
            expected="crit or high",
            observed=ids[0] if ids else "MISSING",
            matched=ids[0] in ("crit", "high")),
        AssertionResult(
            assertion_id="orc03-a3",
            description="LOW item is last",
            expected="low",
            observed=ids[-1] if ids else "MISSING",
            matched=ids[-1] == "low"),
        AssertionResult(
            assertion_id="orc03-a4",
            description=(
                "priority_components dict populated for first item "
                "(Rule 1 transparency)"),
            expected="≥ 5 components",
            observed=str(
                len(r.work_items[0].priority_components)
                if r.work_items else 0),
            matched=(
                r.work_items
                and len(r.work_items[0].priority_components) >= 5)),
    )


SCENARIO_ORC_03_PRIORITY_SORT = Scenario(
    scenario_id="ORC-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-243: 4 findings spanning LOW/MEDIUM/HIGH/CRITICAL → "
        "sorted descending by priority_score; LOW is last; "
        "priority_components dict surfaced with all 5 contributors "
        "(severity_weight, family_weight, base, age_contribution, "
        "impact_contribution, total) per Rule 1."),
    setup=_setup_orc_priority,
    actions=_actions_orc_priority,
    assertions=_assertions_orc_priority,
    requires_engines=("revenue_orchestrator",))


# ORC-04: Stateless verification per Rule 7
def _setup_orc_stateless(engines: EngineBundle) -> None:
    pass


def _actions_orc_stateless(engines: EngineBundle) -> None:
    """Call orchestrate twice on the same finding. First call
    supplies state=RESOLVED; second call does not. Engine must
    NOT memoise the first call's state — per Rule 7, engine is
    stateless. Second call must yield RAISED, not RESOLVED."""
    from utils.revenue_orchestrator import (
        RevenueOrchestrator, WorkItemState)
    from utils.revenue_validation import ValidationSeverity
    from utils.revenue_anomaly_patterns import PatternFamily
    from datetime import date as _date
    eng = RevenueOrchestrator(_build_default_orchestrator_config())
    findings = (
        _make_pattern_finding(
            "p1", ValidationSeverity.HIGH,
            PatternFamily.LEAKAGE),
    )
    raised = {"p1": _date(2026, 4, 1)}
    as_of = _date(2026, 4, 5)
    r1 = eng.orchestrate(
        findings=findings, raised_dates=raised, as_of=as_of,
        current_states={"p1": WorkItemState.RESOLVED})
    r2 = eng.orchestrate(
        findings=findings, raised_dates=raised, as_of=as_of)
    engines["__orc04__"] = (r1, r2)


def _assertions_orc_stateless(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_orchestrator import WorkItemState
    payload = engines.get("__orc04__")
    if payload is None:
        return (AssertionResult(
            assertion_id="orc04-a0", description="Reports populated",
            expected="present", observed="MISSING", matched=False),)
    r1, r2 = payload
    return (
        AssertionResult(
            assertion_id="orc04-a1",
            description=(
                "First call (with supplied state) → RESOLVED"),
            expected=WorkItemState.RESOLVED.value,
            observed=r1.work_items[0].current_state.value,
            matched=(
                r1.work_items[0].current_state
                == WorkItemState.RESOLVED)),
        AssertionResult(
            assertion_id="orc04-a2",
            description=(
                "Second call (no supplied state) → RAISED — "
                "engine did NOT memoise; Rule 7 stateless"),
            expected=WorkItemState.RAISED.value,
            observed=r2.work_items[0].current_state.value,
            matched=(
                r2.work_items[0].current_state
                == WorkItemState.RAISED)),
        AssertionResult(
            assertion_id="orc04-a3",
            description=(
                "Same finding produces same routing in both calls"),
            expected="same team both calls",
            observed=(
                f"{r1.work_items[0].assigned_team.value} vs "
                f"{r2.work_items[0].assigned_team.value}"),
            matched=(
                r1.work_items[0].assigned_team
                == r2.work_items[0].assigned_team)),
    )


SCENARIO_ORC_04_STATELESS = Scenario(
    scenario_id="ORC-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-243 Rule 7 cross-check: orchestrate() called twice on "
        "same finding. First call supplies current_states={p1: "
        "RESOLVED}; second call doesn't. Second call must yield "
        "RAISED — engine MUST NOT memoise state across calls. "
        "Routing remains deterministic (same team) given same "
        "inputs."),
    setup=_setup_orc_stateless,
    actions=_actions_orc_stateless,
    assertions=_assertions_orc_stateless,
    requires_engines=("revenue_orchestrator",))


# ════════════════════════════════════════════════════════════════════════
# v10.53 — Partner & Supplier Reconciliation (ENH-244)
# ════════════════════════════════════════════════════════════════════════

# PSR-01: Partner share underpaid + supplier 3-way clean
def _setup_psr_partner_underpay(engines: EngineBundle) -> None:
    pass


def _actions_psr_partner_underpay(engines: EngineBundle) -> None:
    from utils.partner_supplier_recon import (
        PartnerSupplierReconciliationEngine,
        PartnerAgreement, PartnerRevenueRecord,
        PartnerSettlement)
    from datetime import date as _date
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="MTN-2026", partner_id="MTN",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.30"),
        effective_from=_date(2026, 1, 1),
        effective_to=_date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="MTN",
            agreement_id="MTN-2026",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("2000000"),
            posting_date=_date(2026, 4, 5)),
        PartnerRevenueRecord(
            record_id="r2", partner_id="MTN",
            agreement_id="MTN-2026",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("1000000"),
            posting_date=_date(2026, 4, 20)),
    )
    # Expected = 3,000,000 × 0.30 = 900,000; settled 800,000 →
    # short 100,000
    settlements = (
        PartnerSettlement(
            settlement_id="ST-001", partner_id="MTN",
            agreement_id="MTN-2026", period="2026-04",
            settled_kes=Decimal("800000"),
            settlement_date=_date(2026, 5, 5)),
    )
    engines["__psr01__"] = eng.validate_partner_share(
        (agreement,), revenues, settlements)


def _assertions_psr_partner_underpay(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.partner_supplier_recon import (
        DiscrepancyType, PartySide)
    findings = engines.get("__psr01__")
    if findings is None:
        return (AssertionResult(
            assertion_id="psr01-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="psr01-a1",
            description="Single underpaid finding",
            expected="1",
            observed=str(len(findings)),
            matched=len(findings) == 1),
        AssertionResult(
            assertion_id="psr01-a2",
            description="Discrepancy type SHARE_UNDERPAID",
            expected=DiscrepancyType.SHARE_UNDERPAID.value,
            observed=(
                findings[0].discrepancy_type.value
                if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].discrepancy_type
                == DiscrepancyType.SHARE_UNDERPAID)),
        AssertionResult(
            assertion_id="psr01-a3",
            description="Variance = -100,000 KES",
            expected="-100000",
            observed=(
                str(findings[0].variance_kes) if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].variance_kes == Decimal("-100000"))),
        AssertionResult(
            assertion_id="psr01-a4",
            description="party_side = PARTNER",
            expected=PartySide.PARTNER.value,
            observed=(
                findings[0].party_side.value if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].party_side == PartySide.PARTNER)),
    )


SCENARIO_PSR_01_PARTNER_UNDERPAY = Scenario(
    scenario_id="PSR-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-244: partner MTN earns KES 3m gross commission income "
        "in 2026-04 at 30% share = expected KES 900k; actual "
        "settlement KES 800k → SHARE_UNDERPAID with variance "
        "-100k. PARTNER party_side surfaced per Rule 1."),
    setup=_setup_psr_partner_underpay,
    actions=_actions_psr_partner_underpay,
    assertions=_assertions_psr_partner_underpay,
    requires_engines=("partner_supplier_recon",))


# PSR-02: Missing settlement (revenue earned, no settlement)
def _setup_psr_missing(engines: EngineBundle) -> None:
    pass


def _actions_psr_missing(engines: EngineBundle) -> None:
    from utils.partner_supplier_recon import (
        PartnerSupplierReconciliationEngine,
        PartnerAgreement, PartnerRevenueRecord)
    from datetime import date as _date
    eng = PartnerSupplierReconciliationEngine()
    agreement = PartnerAgreement(
        agreement_id="SAFCOM-2026", partner_id="SAFCOM",
        revenue_category="COMMISSION_INCOME",
        share_pct=Decimal("0.25"),
        effective_from=_date(2026, 1, 1),
        effective_to=_date(2026, 12, 31),
        min_settlement_kes=Decimal("10000"))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="SAFCOM",
            agreement_id="SAFCOM-2026",
            revenue_category="COMMISSION_INCOME",
            gross_revenue_kes=Decimal("500000"),
            posting_date=_date(2026, 4, 10)),
    )
    # Expected = 125,000 (above min 10k) → must be settled. None
    # supplied → MISSING.
    engines["__psr02__"] = eng.validate_partner_share(
        (agreement,), revenues, ())


def _assertions_psr_missing(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.partner_supplier_recon import DiscrepancyType
    from utils.revenue_validation import ValidationSeverity
    findings = engines.get("__psr02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="psr02-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="psr02-a1",
            description="One SHARE_MISSING finding",
            expected="1",
            observed=str(len(findings)),
            matched=len(findings) == 1),
        AssertionResult(
            assertion_id="psr02-a2",
            description="Severity HIGH (missing settlement)",
            expected=ValidationSeverity.HIGH.value,
            observed=(
                findings[0].severity.value if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].severity == ValidationSeverity.HIGH)),
        AssertionResult(
            assertion_id="psr02-a3",
            description="Discrepancy = SHARE_MISSING",
            expected=DiscrepancyType.SHARE_MISSING.value,
            observed=(
                findings[0].discrepancy_type.value
                if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].discrepancy_type
                == DiscrepancyType.SHARE_MISSING)),
    )


SCENARIO_PSR_02_MISSING_SETTLEMENT = Scenario(
    scenario_id="PSR-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-244: partner SAFCOM earns KES 500k gross at 25% = "
        "KES 125k expected (above min 10k floor); no settlement "
        "recorded → SHARE_MISSING HIGH severity. Below-min "
        "settlements legitimately carry forward; this one is "
        "above-min so flagged."),
    setup=_setup_psr_missing,
    actions=_actions_psr_missing,
    assertions=_assertions_psr_missing,
    requires_engines=("partner_supplier_recon",))


# PSR-03: Supplier 3-way mismatch (GRN_INVOICE)
def _setup_psr_supplier_mismatch(engines: EngineBundle) -> None:
    pass


def _actions_psr_supplier_mismatch(engines: EngineBundle) -> None:
    from utils.partner_supplier_recon import (
        PartnerSupplierReconciliationEngine, PurchaseOrder,
        GoodsReceiptNote, SupplierInvoice, SupplierPayment)
    from datetime import date as _date
    eng = PartnerSupplierReconciliationEngine()
    po = PurchaseOrder(
        po_id="PO-2026-001", supplier_id="ACME-IT",
        ordered_amount_kes=Decimal("500000"),
        ordered_date=_date(2026, 4, 1),
        expected_delivery_date=_date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN-001", po_id="PO-2026-001",
        received_amount_kes=Decimal("500000"),
        received_date=_date(2026, 4, 14))
    # Invoice 600k vs GRN 500k → 100k overbilling
    invoice = SupplierInvoice(
        invoice_id="INV-001", supplier_id="ACME-IT",
        po_id="PO-2026-001",
        invoiced_amount_kes=Decimal("600000"),
        invoice_date=_date(2026, 4, 16))
    # Payment 600k = invoice → no INV-PAY mismatch
    payment = SupplierPayment(
        payment_id="PAY-001", invoice_id="INV-001",
        paid_amount_kes=Decimal("600000"),
        paid_date=_date(2026, 4, 30))
    engines["__psr03__"] = eng.match_supplier_three_way(
        (po,), (grn,), (invoice,), (payment,))


def _assertions_psr_supplier_mismatch(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.partner_supplier_recon import DiscrepancyType
    from utils.revenue_validation import ValidationSeverity
    findings = engines.get("__psr03__")
    if findings is None:
        return (AssertionResult(
            assertion_id="psr03-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    grn_inv = [
        f for f in findings
        if f.discrepancy_type
        == DiscrepancyType.GRN_INVOICE_MISMATCH]
    return (
        AssertionResult(
            assertion_id="psr03-a1",
            description="One GRN_INVOICE_MISMATCH finding",
            expected="1",
            observed=str(len(grn_inv)),
            matched=len(grn_inv) == 1),
        AssertionResult(
            assertion_id="psr03-a2",
            description="GRN_INVOICE_MISMATCH severity HIGH",
            expected=ValidationSeverity.HIGH.value,
            observed=(
                grn_inv[0].severity.value if grn_inv else "n/a"),
            matched=(
                len(grn_inv) == 1
                and grn_inv[0].severity == ValidationSeverity.HIGH)),
        AssertionResult(
            assertion_id="psr03-a3",
            description="Variance +100,000 KES (invoice over GRN)",
            expected="100000",
            observed=(
                str(grn_inv[0].variance_kes)
                if grn_inv else "n/a"),
            matched=(
                len(grn_inv) == 1
                and grn_inv[0].variance_kes == Decimal("100000"))),
        AssertionResult(
            assertion_id="psr03-a4",
            description=(
                "Related PO surfaced in related_ids"),
            expected="PO-2026-001 in related_ids",
            observed=(
                str(grn_inv[0].related_ids) if grn_inv else "n/a"),
            matched=(
                len(grn_inv) == 1
                and "PO-2026-001" in grn_inv[0].related_ids)),
    )


SCENARIO_PSR_03_SUPPLIER_OVERBILL = Scenario(
    scenario_id="PSR-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-244 supplier 3-way: ACME-IT PO ordered 500k, GRN 500k "
        "received, invoice 600k → GRN_INVOICE_MISMATCH HIGH "
        "severity (overbilling 100k); INV-PAY chain matches → no "
        "additional finding from that step."),
    setup=_setup_psr_supplier_mismatch,
    actions=_actions_psr_supplier_mismatch,
    assertions=_assertions_psr_supplier_mismatch,
    requires_engines=("partner_supplier_recon",))


# PSR-04: Multiple discrepancies via reconcile_all orchestrator
def _setup_psr_orchestrator(engines: EngineBundle) -> None:
    pass


def _actions_psr_orchestrator(engines: EngineBundle) -> None:
    from utils.partner_supplier_recon import (
        PartnerSupplierReconciliationEngine,
        PartnerAgreement, PartnerRevenueRecord,
        PartnerSettlement, PurchaseOrder,
        GoodsReceiptNote, SupplierInvoice)
    from datetime import date as _date
    eng = PartnerSupplierReconciliationEngine()
    # Partner side: missing settlement
    agreement = PartnerAgreement(
        agreement_id="PA1", partner_id="VISA",
        revenue_category="FEE_INCOME",
        share_pct=Decimal("0.20"),
        effective_from=_date(2026, 1, 1),
        effective_to=_date(2026, 12, 31))
    revenues = (
        PartnerRevenueRecord(
            record_id="r1", partner_id="VISA",
            agreement_id="PA1", revenue_category="FEE_INCOME",
            gross_revenue_kes=Decimal("3000000"),
            posting_date=_date(2026, 4, 10)),
    )
    # Supplier side: invoice without PO + invoice before delivery
    po = PurchaseOrder(
        po_id="PO-A", supplier_id="VENDOR-X",
        ordered_amount_kes=Decimal("100000"),
        ordered_date=_date(2026, 4, 1),
        expected_delivery_date=_date(2026, 4, 15))
    grn = GoodsReceiptNote(
        grn_id="GRN-A", po_id="PO-A",
        received_amount_kes=Decimal("100000"),
        received_date=_date(2026, 4, 14))
    early_inv = SupplierInvoice(
        invoice_id="INV-EARLY", supplier_id="VENDOR-X",
        po_id="PO-A", invoiced_amount_kes=Decimal("100000"),
        invoice_date=_date(2026, 4, 5))   # before GRN!
    rogue_inv = SupplierInvoice(
        invoice_id="INV-NOPO", supplier_id="VENDOR-Y",
        po_id=None, invoiced_amount_kes=Decimal("50000"),
        invoice_date=_date(2026, 4, 20))
    engines["__psr04__"] = eng.reconcile_all(
        agreements=(agreement,),
        partner_revenues=revenues,
        settlements=(),
        purchase_orders=(po,),
        grns=(grn,),
        invoices=(early_inv, rogue_inv),
        payments=())


def _assertions_psr_orchestrator(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.partner_supplier_recon import DiscrepancyType
    r = engines.get("__psr04__")
    if r is None:
        return (AssertionResult(
            assertion_id="psr04-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    types = {f.discrepancy_type for f in r.findings}
    return (
        AssertionResult(
            assertion_id="psr04-a1",
            description="Partner findings = 1 (missing settlement)",
            expected="1",
            observed=str(r.partner_findings_count),
            matched=r.partner_findings_count == 1),
        AssertionResult(
            assertion_id="psr04-a2",
            description=(
                "SHARE_MISSING + INVOICE_BEFORE_DELIVERY + "
                "INVOICE_WITHOUT_PO all surfaced"),
            expected="3 distinct discrepancy types present",
            observed=str([t.value for t in types]),
            matched=(
                DiscrepancyType.SHARE_MISSING in types
                and DiscrepancyType.INVOICE_BEFORE_DELIVERY in types
                and DiscrepancyType.INVOICE_WITHOUT_PO in types)),
        AssertionResult(
            assertion_id="psr04-a3",
            description="Aggregates surfaced per Rule 1",
            expected="non-empty by_severity dict",
            observed=str(r.by_severity),
            matched=any(
                v > 0 for v in r.by_severity.values())),
        AssertionResult(
            assertion_id="psr04-a4",
            description="Framework refs cite both blocks",
            expected="ENH-244 §partner_share + §supplier_3way",
            observed=", ".join(r.framework_refs[:1]),
            matched=any(
                "§partner_share" in ref
                and "§supplier_3way" in ref
                for ref in r.framework_refs)),
    )


SCENARIO_PSR_04_ORCHESTRATOR = Scenario(
    scenario_id="PSR-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-244 reconcile_all: VISA partner missing settlement "
        "(KES 600k expected) + VENDOR-X invoice dated before GRN "
        "+ VENDOR-Y invoice without PO. 3 discrepancy types "
        "across both PartySide values; aggregates populated; "
        "framework refs cite both blocks per Rule 1."),
    setup=_setup_psr_orchestrator,
    actions=_actions_psr_orchestrator,
    assertions=_assertions_psr_orchestrator,
    requires_engines=("partner_supplier_recon",))


# ════════════════════════════════════════════════════════════════════════
# v10.54 — Revenue Dashboard Metrics (ENH-245)
# ════════════════════════════════════════════════════════════════════════

def _make_work_item(
    wid, raised, family,
    severity=None, state=None, team=None,
    impact=None, past_sla=False,
):
    from utils.revenue_orchestrator import (
        WorkItem, WorkItemState, InvestigatorTeam, FindingType)
    from utils.revenue_validation import ValidationSeverity
    return WorkItem(
        work_item_id=wid,
        source_finding_id=f"f-{wid}",
        source_finding_type=FindingType.PATTERN,
        severity=severity or ValidationSeverity.HIGH,
        family_or_category=family,
        description=f"item {wid}",
        affected_record_ids=(f"r-{wid}",),
        raised_date=raised,
        age_days=0,
        sla_deadline=raised,
        past_sla=past_sla,
        assigned_team=team or InvestigatorTeam.OPERATIONS,
        priority_score=Decimal("100"),
        priority_components={},
        monetary_impact_kes=impact,
        current_state=state or WorkItemState.RAISED,
        framework_refs=("ENH-243",))


# DSH-01: Leakage trend over 3 months
def _setup_dsh_trend(engines: EngineBundle) -> None:
    pass


def _actions_dsh_trend(engines: EngineBundle) -> None:
    from utils.revenue_dashboard_metrics import (
        RevenueDashboardMetrics, DashboardWindow)
    from datetime import date as _date
    eng = RevenueDashboardMetrics()
    items = (
        _make_work_item("a", _date(2026, 1, 5), "LEAKAGE",
                        impact=Decimal("1000")),
        _make_work_item("b", _date(2026, 1, 20), "LEAKAGE",
                        impact=Decimal("2000")),
        _make_work_item("c", _date(2026, 2, 10), "LEAKAGE",
                        impact=Decimal("5000")),
        _make_work_item("d", _date(2026, 3, 1), "LEAKAGE",
                        impact=Decimal("3000")),
        _make_work_item("outside", _date(2025, 12, 1),
                        "LEAKAGE", impact=Decimal("99999")),
    )
    window = DashboardWindow(
        period_start=_date(2026, 1, 1),
        period_end=_date(2026, 12, 31))
    engines["__dsh01__"] = eng.compute_leakage_trend(items, window)


def _assertions_dsh_trend(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    trend = engines.get("__dsh01__")
    if trend is None:
        return (AssertionResult(
            assertion_id="dsh01-a0", description="Trend populated",
            expected="present", observed="MISSING", matched=False),)
    by_period = {p.period: p for p in trend}
    return (
        AssertionResult(
            assertion_id="dsh01-a1",
            description="3 monthly buckets in window",
            expected="3",
            observed=str(len(trend)),
            matched=len(trend) == 3),
        AssertionResult(
            assertion_id="dsh01-a2",
            description="2026-01 has 2 findings + KES 3000 impact",
            expected="2 / 3000",
            observed=(
                f"{by_period['2026-01'].finding_count} / "
                f"{by_period['2026-01'].monetary_impact_kes}"
                if "2026-01" in by_period else "MISSING"),
            matched=(
                "2026-01" in by_period
                and by_period["2026-01"].finding_count == 2
                and by_period["2026-01"].monetary_impact_kes
                == Decimal("3000"))),
        AssertionResult(
            assertion_id="dsh01-a3",
            description="Pre-window 2025-12 record excluded",
            expected="no 2025-12 bucket",
            observed=str(list(by_period.keys())),
            matched="2025-12" not in by_period),
        AssertionResult(
            assertion_id="dsh01-a4",
            description="Trend sorted ascending by period",
            expected="2026-01 / 2026-02 / 2026-03",
            observed=", ".join(p.period for p in trend),
            matched=[p.period for p in trend]
            == ["2026-01", "2026-02", "2026-03"]),
    )


SCENARIO_DSH_01_LEAKAGE_TREND = Scenario(
    scenario_id="DSH-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-245: 5 work items spanning Dec 2025 + Jan-Mar 2026 → "
        "trend produces 3 buckets (Dec excluded as outside "
        "window); 2026-01 aggregates 2 findings + KES 3,000 "
        "impact; sorted ascending by period."),
    setup=_setup_dsh_trend,
    actions=_actions_dsh_trend,
    assertions=_assertions_dsh_trend,
    requires_engines=("revenue_dashboard_metrics",))


# DSH-02: Top categories diverge by count vs impact
def _setup_dsh_categories(engines: EngineBundle) -> None:
    pass


def _actions_dsh_categories(engines: EngineBundle) -> None:
    from utils.revenue_dashboard_metrics import (
        RevenueDashboardMetrics)
    from datetime import date as _date
    eng = RevenueDashboardMetrics()
    items = tuple(
        _make_work_item(f"l{i}", _date(2026, 4, i), "LEAKAGE",
                        impact=Decimal("500"))
        for i in range(1, 11)
    ) + (
        _make_work_item("big", _date(2026, 4, 11),
                        "BILLING_ERROR",
                        impact=Decimal("50000000")),
    )
    by_count, by_impact = eng.compute_top_categories(items)
    engines["__dsh02__"] = (by_count, by_impact)


def _assertions_dsh_categories(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    payload = engines.get("__dsh02__")
    if payload is None:
        return (AssertionResult(
            assertion_id="dsh02-a0", description="Rankings populated",
            expected="present", observed="MISSING", matched=False),)
    by_count, by_impact = payload
    return (
        AssertionResult(
            assertion_id="dsh02-a1",
            description="By-count top is LEAKAGE (10 items)",
            expected="LEAKAGE",
            observed=by_count[0].category if by_count else "MISSING",
            matched=(
                by_count
                and by_count[0].category == "LEAKAGE"
                and by_count[0].count == 10)),
        AssertionResult(
            assertion_id="dsh02-a2",
            description=(
                "By-impact top is BILLING_ERROR (huge single item)"),
            expected="BILLING_ERROR",
            observed=(
                by_impact[0].category
                if by_impact else "MISSING"),
            matched=(
                by_impact
                and by_impact[0].category == "BILLING_ERROR"
                and by_impact[0].monetary_impact_kes
                == Decimal("50000000"))),
        AssertionResult(
            assertion_id="dsh02-a3",
            description=(
                "pct_of_total_count for LEAKAGE ≈ 10/11 = 0.909"),
            expected="≈ 0.909",
            observed=(
                str(by_count[0].pct_of_total_count)
                if by_count else "MISSING"),
            matched=(
                by_count
                and abs(
                    by_count[0].pct_of_total_count
                    - Decimal("0.9091")) < Decimal("0.001"))),
        AssertionResult(
            assertion_id="dsh02-a4",
            description=(
                "Rankings deliberately diverge — Rule 1 surfacing "
                "high-frequency-low-impact vs low-frequency-"
                "high-impact"),
            expected="diff top categories",
            observed=(
                f"{by_count[0].category} vs "
                f"{by_impact[0].category}"
                if by_count and by_impact else "MISSING"),
            matched=(
                by_count and by_impact
                and by_count[0].category != by_impact[0].category)),
    )


SCENARIO_DSH_02_TOP_CATEGORIES = Scenario(
    scenario_id="DSH-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-245: 10 small LEAKAGE findings + 1 huge "
        "BILLING_ERROR → by_count ranks LEAKAGE first (10 vs 1), "
        "by_impact ranks BILLING_ERROR first (50m vs 5k). The "
        "two rankings deliberately diverge per Rule 1 — "
        "high-frequency-low-impact and low-frequency-high-impact "
        "patterns warrant different responses."),
    setup=_setup_dsh_categories,
    actions=_actions_dsh_categories,
    assertions=_assertions_dsh_categories,
    requires_engines=("revenue_dashboard_metrics",))


# DSH-03: Recovery distinguishes RESOLVED from DISMISSED
def _setup_dsh_recovery(engines: EngineBundle) -> None:
    pass


def _actions_dsh_recovery(engines: EngineBundle) -> None:
    from utils.revenue_dashboard_metrics import (
        RevenueDashboardMetrics, DashboardWindow)
    from utils.revenue_orchestrator import WorkItemState
    from datetime import date as _date
    eng = RevenueDashboardMetrics()
    items = (
        _make_work_item("r1", _date(2026, 4, 1), "LEAKAGE",
                        state=WorkItemState.RESOLVED,
                        impact=Decimal("10000")),
        _make_work_item("r2", _date(2026, 4, 5), "LEAKAGE",
                        state=WorkItemState.RESOLVED,
                        impact=Decimal("5000")),
        _make_work_item("d1", _date(2026, 4, 10), "LEAKAGE",
                        state=WorkItemState.DISMISSED,
                        impact=Decimal("999999")),
        _make_work_item("o1", _date(2026, 4, 15), "LEAKAGE",
                        state=WorkItemState.IN_PROGRESS,
                        impact=Decimal("3000")),
        _make_work_item("o2", _date(2026, 4, 20), "LEAKAGE",
                        state=WorkItemState.RAISED,
                        impact=Decimal("2000")),
    )
    window = DashboardWindow(
        period_start=_date(2026, 1, 1),
        period_end=_date(2026, 12, 31))
    engines["__dsh03__"] = eng.compute_recovery(items, window)


def _assertions_dsh_recovery(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__dsh03__")
    if r is None:
        return (AssertionResult(
            assertion_id="dsh03-a0", description="Recovery populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="dsh03-a1",
            description=(
                "Recovered = 15,000 (only RESOLVED, NOT DISMISSED)"),
            expected="15000",
            observed=str(r.recovered_kes),
            matched=r.recovered_kes == Decimal("15000")),
        AssertionResult(
            assertion_id="dsh03-a2",
            description=(
                "Dismissed counted separately, not as recovery"),
            expected="1 dismissed",
            observed=str(r.dismissed_count),
            matched=r.dismissed_count == 1),
        AssertionResult(
            assertion_id="dsh03-a3",
            description="Open count = 2 (RAISED + IN_PROGRESS)",
            expected="2",
            observed=str(r.open_count),
            matched=r.open_count == 2),
        AssertionResult(
            assertion_id="dsh03-a4",
            description="Open estimated impact = 5,000 (3k + 2k)",
            expected="5000",
            observed=str(r.open_estimated_impact_kes),
            matched=r.open_estimated_impact_kes == Decimal("5000")),
    )


SCENARIO_DSH_03_RECOVERY = Scenario(
    scenario_id="DSH-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-245: 5 work items mixing RESOLVED + DISMISSED + open "
        "states. Recovery = 15k (only RESOLVED items count). "
        "Dismissed item's KES 999,999 is NOT counted as recovery "
        "because dismissed = determined-not-an-issue. Open count "
        "+ open estimated impact surfaced separately for triage."),
    setup=_setup_dsh_recovery,
    actions=_actions_dsh_recovery,
    assertions=_assertions_dsh_recovery,
    requires_engines=("revenue_dashboard_metrics",))


# DSH-04: compute_all orchestrates + Rule 1 provenance
def _setup_dsh_all(engines: EngineBundle) -> None:
    pass


def _actions_dsh_all(engines: EngineBundle) -> None:
    from utils.revenue_dashboard_metrics import (
        RevenueDashboardMetrics, DashboardWindow,
        StateTransition)
    from utils.revenue_orchestrator import (
        WorkItemState, InvestigatorTeam)
    from datetime import date as _date
    eng = RevenueDashboardMetrics()
    items = (
        _make_work_item("a", _date(2026, 4, 1), "LEAKAGE",
                        state=WorkItemState.RESOLVED,
                        team=InvestigatorTeam.REVENUE_RECOVERY,
                        impact=Decimal("5000")),
        _make_work_item("b", _date(2026, 4, 2), "BILLING_ERROR",
                        state=WorkItemState.IN_PROGRESS,
                        team=InvestigatorTeam.OPERATIONS,
                        impact=Decimal("2000"),
                        past_sla=True),
    )
    transitions = (
        StateTransition(
            work_item_id="a",
            from_state=WorkItemState.RAISED,
            to_state=WorkItemState.RESOLVED,
            transition_date=_date(2026, 4, 8)),
    )
    window = DashboardWindow(
        period_start=_date(2026, 1, 1),
        period_end=_date(2026, 12, 31))
    engines["__dsh04__"] = eng.compute_all(
        items, window, transitions)


def _assertions_dsh_all(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.revenue_dashboard_metrics import CycleStage
    m = engines.get("__dsh04__")
    if m is None:
        return (AssertionResult(
            assertion_id="dsh04-a0", description="Metrics populated",
            expected="present", observed="MISSING", matched=False),)
    raised_to_resolved = next(
        (c for c in m.cycle_times
         if c.stage == CycleStage.RAISED_TO_RESOLVED), None)
    return (
        AssertionResult(
            assertion_id="dsh04-a1",
            description="All 6 metric blocks populated",
            expected=(
                "leakage_trend, top_*, recovery, team_activities, "
                "cycle_times all present"),
            observed=(
                f"trend={len(m.leakage_trend)}, "
                f"by_count={len(m.top_categories_by_count)}, "
                f"by_impact={len(m.top_categories_by_impact)}, "
                f"recovery_resolved="
                f"{m.recovery.resolved_count}, "
                f"teams={len(m.team_activities)}, "
                f"cycles={len(m.cycle_times)}"),
            matched=(
                m.leakage_trend
                and m.top_categories_by_count
                and m.team_activities
                and m.cycle_times)),
        AssertionResult(
            assertion_id="dsh04-a2",
            description=(
                "Cycle time computed for RAISED_TO_RESOLVED "
                "(7 days)"),
            expected="7",
            observed=(
                str(raised_to_resolved.mean_days)
                if raised_to_resolved
                and raised_to_resolved.mean_days
                else "n/a"),
            matched=(
                raised_to_resolved is not None
                and raised_to_resolved.sample_size == 1
                and raised_to_resolved.mean_days == Decimal("7"))),
        AssertionResult(
            assertion_id="dsh04-a3",
            description=(
                "Past_sla aggregated into team activity"),
            expected="≥ 1 past-SLA across teams",
            observed=str(sum(
                t.past_sla_count for t in m.team_activities)),
            matched=sum(
                t.past_sla_count for t in m.team_activities) >= 1),
        AssertionResult(
            assertion_id="dsh04-a4",
            description=(
                "Framework refs cite ENH-245 + Rule 7 read-only "
                "stance"),
            expected=(
                "ENH-245 in refs + Rule 7 mentioned"),
            observed=" / ".join(m.framework_refs),
            matched=(
                any("ENH-245" in r for r in m.framework_refs)
                and any("Rule 7" in r for r in m.framework_refs))),
    )


SCENARIO_DSH_04_COMPUTE_ALL = Scenario(
    scenario_id="DSH-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-245 compute_all: 2 work items + 1 RAISED→RESOLVED "
        "transition (7 days). All 6 metric blocks populated; "
        "cycle time mean = 7 days; past_sla count surfaced via "
        "team activity; framework refs cite ENH-245 + Rule 7 "
        "read-only stance per Rule 1."),
    setup=_setup_dsh_all,
    actions=_actions_dsh_all,
    assertions=_assertions_dsh_all,
    requires_engines=("revenue_dashboard_metrics",))


# ════════════════════════════════════════════════════════════════════════
# v10.55 — Continuous Billing Verification (ENH-246)
# ════════════════════════════════════════════════════════════════════════

def _make_default_contract():
    from utils.revenue_anomaly_patterns import ContractRate
    from datetime import date as _date
    return ContractRate(
        contract_id="C-001", customer_id="cust-A",
        product_code="LOAN", floor_rate_pct=Decimal("3.0"),
        ceiling_rate_pct=Decimal("8.0"),
        effective_from=_date(2026, 1, 1),
        effective_to=_date(2026, 12, 31))


def _setup_cbv(engines: EngineBundle) -> None:
    pass


def _actions_cbv_pass(engines: EngineBundle) -> None:
    from utils.continuous_billing_verification import (
        ContinuousBillingVerificationEngine, BillingDraft)
    from datetime import date as _date
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="D-001", customer_id="cust-A",
        product_code="LOAN", contract_id="C-001",
        proposed_amount_kes=Decimal("100000"),
        draft_date=_date(2026, 4, 15),
        applied_rate_pct=Decimal("5.0"),
        tax_rate_pct=Decimal("0.16"),
        computed_tax_kes=Decimal("16000"))
    engines["__cbv01__"] = eng.verify(
        draft, contracts=(_make_default_contract(),))


def _assertions_cbv_pass(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.continuous_billing_verification import Verdict
    r = engines.get("__cbv01__")
    if r is None:
        return (AssertionResult(
            assertion_id="cbv01-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cbv01-a1",
            description="Verdict = PASS for clean draft",
            expected=Verdict.PASS.value,
            observed=r.verdict.value,
            matched=r.verdict == Verdict.PASS),
        AssertionResult(
            assertion_id="cbv01-a2",
            description="No fail or warn checks",
            expected="0 fail / 0 warn",
            observed=f"{r.fail_count} fail / {r.warn_count} warn",
            matched=r.fail_count == 0 and r.warn_count == 0),
        AssertionResult(
            assertion_id="cbv01-a3",
            description="All 5 check results returned",
            expected="5",
            observed=str(len(r.check_results)),
            matched=len(r.check_results) == 5),
    )


SCENARIO_CBV_01_PASS = Scenario(
    scenario_id="CBV-01", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-246: clean draft with valid contract + rate in band + "
        "correct tax computation → PASS verdict, 0 fails, 0 warns, "
        "all 5 check results returned per Rule 1."),
    setup=_setup_cbv, actions=_actions_cbv_pass,
    assertions=_assertions_cbv_pass,
    requires_engines=("continuous_billing_verification",))


def _actions_cbv_hold(engines: EngineBundle) -> None:
    from utils.continuous_billing_verification import (
        ContinuousBillingVerificationEngine, BillingDraft)
    from datetime import date as _date
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="D-002", customer_id="cust-A",
        product_code="LOAN", contract_id="C-001",
        proposed_amount_kes=Decimal("100000"),
        draft_date=_date(2026, 4, 15),
        applied_rate_pct=Decimal("2.5"))   # below floor
    engines["__cbv02__"] = eng.verify(
        draft, contracts=(_make_default_contract(),))


def _assertions_cbv_hold(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.continuous_billing_verification import (
        Verdict, CheckName, CheckStatus)
    r = engines.get("__cbv02__")
    if r is None:
        return (AssertionResult(
            assertion_id="cbv02-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    rate = next(
        (x for x in r.check_results
         if x.check_name == CheckName.RATE_BAND), None)
    return (
        AssertionResult(
            assertion_id="cbv02-a1",
            description=(
                "Below-floor rate → HOLD verdict (warn, not "
                "reject)"),
            expected=Verdict.HOLD_PENDING_REVIEW.value,
            observed=r.verdict.value,
            matched=r.verdict == Verdict.HOLD_PENDING_REVIEW),
        AssertionResult(
            assertion_id="cbv02-a2",
            description="RATE_BAND check returns WARN",
            expected=CheckStatus.WARN.value,
            observed=rate.status.value if rate else "MISSING",
            matched=rate is not None
            and rate.status == CheckStatus.WARN),
    )


SCENARIO_CBV_02_HOLD = Scenario(
    scenario_id="CBV-02", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-246: applied rate 2.5% below contract floor 3.0% → "
        "WARN (leakage but not compliance breach) → "
        "HOLD_PENDING_REVIEW verdict. WARN ≠ FAIL by design."),
    setup=_setup_cbv, actions=_actions_cbv_hold,
    assertions=_assertions_cbv_hold,
    requires_engines=("continuous_billing_verification",))


def _actions_cbv_reject_unauth(engines: EngineBundle) -> None:
    from utils.continuous_billing_verification import (
        ContinuousBillingVerificationEngine, BillingDraft)
    from datetime import date as _date
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="D-003", customer_id="cust-A",
        product_code="FEE", contract_id=None,
        proposed_amount_kes=Decimal("5000"),
        draft_date=_date(2026, 4, 15),
        discount_pct=Decimal("0.20"),
        discount_authorization_id=None)
    engines["__cbv03__"] = eng.verify(draft)


def _assertions_cbv_reject_unauth(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.continuous_billing_verification import (
        Verdict, CheckName, CheckStatus)
    r = engines.get("__cbv03__")
    if r is None:
        return (AssertionResult(
            assertion_id="cbv03-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    auth = next(
        (x for x in r.check_results
         if x.check_name == CheckName.DISCOUNT_AUTH), None)
    return (
        AssertionResult(
            assertion_id="cbv03-a1",
            description="Verdict = REJECT_RECOMMENDED",
            expected=Verdict.REJECT_RECOMMENDED.value,
            observed=r.verdict.value,
            matched=r.verdict == Verdict.REJECT_RECOMMENDED),
        AssertionResult(
            assertion_id="cbv03-a2",
            description="DISCOUNT_AUTH check returns FAIL",
            expected=CheckStatus.FAIL.value,
            observed=auth.status.value if auth else "MISSING",
            matched=auth is not None
            and auth.status == CheckStatus.FAIL),
        AssertionResult(
            assertion_id="cbv03-a3",
            description="Framework refs cite §discount_auth",
            expected="§discount_auth in refs",
            observed=", ".join(auth.framework_refs) if auth else "n/a",
            matched=auth is not None
            and any("§discount_auth" in ref
                    for ref in auth.framework_refs)),
    )


SCENARIO_CBV_03_REJECT_UNAUTHORIZED = Scenario(
    scenario_id="CBV-03", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-246: 20% discount applied without authorization_id "
        "→ DISCOUNT_AUTH FAIL → REJECT_RECOMMENDED verdict; "
        "framework refs cite §discount_auth per Rule 1."),
    setup=_setup_cbv, actions=_actions_cbv_reject_unauth,
    assertions=_assertions_cbv_reject_unauth,
    requires_engines=("continuous_billing_verification",))


def _actions_cbv_tax_with_discount(engines: EngineBundle) -> None:
    """Tax base = amount × (1 - discount); engine should compute
    correctly and pass when actual tax matches."""
    from utils.continuous_billing_verification import (
        ContinuousBillingVerificationEngine, BillingDraft)
    from datetime import date as _date
    eng = ContinuousBillingVerificationEngine()
    draft = BillingDraft(
        draft_id="D-004", customer_id="cust-A",
        product_code="LOAN", contract_id="C-001",
        proposed_amount_kes=Decimal("10000"),
        draft_date=_date(2026, 4, 15),
        applied_rate_pct=Decimal("5.0"),
        discount_pct=Decimal("0.10"),
        discount_authorization_id="AUTH-099",
        tax_rate_pct=Decimal("0.16"),
        # Net = 9000; tax = 1440
        computed_tax_kes=Decimal("1440"))
    engines["__cbv04__"] = eng.verify(
        draft, contracts=(_make_default_contract(),))


def _assertions_cbv_tax_with_discount(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.continuous_billing_verification import (
        Verdict, CheckName, CheckStatus)
    r = engines.get("__cbv04__")
    if r is None:
        return (AssertionResult(
            assertion_id="cbv04-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    tax = next(
        (x for x in r.check_results
         if x.check_name == CheckName.TAX_COMPUTATION), None)
    return (
        AssertionResult(
            assertion_id="cbv04-a1",
            description=(
                "Tax-on-net-of-discount computation passes"),
            expected=CheckStatus.PASS.value,
            observed=tax.status.value if tax else "MISSING",
            matched=tax is not None
            and tax.status == CheckStatus.PASS),
        AssertionResult(
            assertion_id="cbv04-a2",
            description=(
                "Authorized discount + correct tax + in-band rate "
                "→ overall PASS"),
            expected=Verdict.PASS.value,
            observed=r.verdict.value,
            matched=r.verdict == Verdict.PASS),
    )


SCENARIO_CBV_04_TAX_DISCOUNT = Scenario(
    scenario_id="CBV-04", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-246: amount 10k × (1-0.10) discount = 9k net; tax at "
        "16% = KES 1440 matches computed_tax_kes; authorization "
        "present → all 5 checks PASS, verdict PASS. Tax base "
        "discipline: tax computed on amount AFTER discount."),
    setup=_setup_cbv, actions=_actions_cbv_tax_with_discount,
    assertions=_assertions_cbv_tax_with_discount,
    requires_engines=("continuous_billing_verification",))


# ════════════════════════════════════════════════════════════════════════
# v10.56 — Commission & Incentive Assurance (ENH-247)
# ════════════════════════════════════════════════════════════════════════

def _make_default_plan():
    from utils.commission_assurance import (
        IncentivePlan, CommissionTier, TierBasis)
    from datetime import date as _date
    return IncentivePlan(
        plan_id="P-RM-2026", rm_role="RM-Tier-1",
        tiers=(
            CommissionTier(
                tier_min_kes=Decimal("0"),
                tier_max_kes=Decimal("100000"),
                rate_pct=Decimal("0.02")),
            CommissionTier(
                tier_min_kes=Decimal("100000"),
                tier_max_kes=Decimal("500000"),
                rate_pct=Decimal("0.03")),
            CommissionTier(
                tier_min_kes=Decimal("500000"),
                tier_max_kes=None,
                rate_pct=Decimal("0.05")),
        ),
        basis=TierBasis.MARGINAL,
        effective_from=_date(2026, 1, 1),
        effective_to=_date(2026, 12, 31))


def _setup_cma(engines: EngineBundle) -> None:
    pass


def _actions_cma_tier_walk(engines: EngineBundle) -> None:
    from utils.commission_assurance import (
        CommissionAssuranceEngine)
    eng = CommissionAssuranceEngine()
    plan = _make_default_plan()
    # Revenue 1m → 2k + 12k + 25k = 39k
    engines["__cma01__"] = eng.compute_expected_commission(
        plan, "rm-101", "2026-04", Decimal("1000000"))


def _assertions_cma_tier_walk(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    calc = engines.get("__cma01__")
    if calc is None:
        return (AssertionResult(
            assertion_id="cma01-a0", description="Calc populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cma01-a1",
            description="Marginal tier walk: 1m → 39k",
            expected="39000.00",
            observed=str(calc.expected_commission_kes),
            matched=(
                calc.expected_commission_kes
                == Decimal("39000.00"))),
        AssertionResult(
            assertion_id="cma01-a2",
            description=(
                "All 3 tiers surfaced as contributions per Rule 1"),
            expected="3 contributions",
            observed=str(len(calc.contributions)),
            matched=len(calc.contributions) == 3),
        AssertionResult(
            assertion_id="cma01-a3",
            description="Tier 1 contribution = 2000 (100k @ 2%)",
            expected="2000",
            observed=(
                str(calc.contributions[0].contribution_kes)
                if calc.contributions else "n/a"),
            matched=(
                len(calc.contributions) == 3
                and calc.contributions[0].contribution_kes
                == Decimal("2000"))),
        AssertionResult(
            assertion_id="cma01-a4",
            description="Tier 3 contribution = 25000 (500k @ 5%)",
            expected="25000",
            observed=(
                str(calc.contributions[2].contribution_kes)
                if len(calc.contributions) == 3 else "n/a"),
            matched=(
                len(calc.contributions) == 3
                and calc.contributions[2].contribution_kes
                == Decimal("25000"))),
    )


SCENARIO_CMA_01_TIER_WALK = Scenario(
    scenario_id="CMA-01", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-247: 3-tier marginal plan; revenue KES 1m → 100k×2% + "
        "400k×3% + 500k×5% = 39k expected; all 3 tiers surfaced "
        "in contributions tuple per Rule 1 transparency."),
    setup=_setup_cma, actions=_actions_cma_tier_walk,
    assertions=_assertions_cma_tier_walk,
    requires_engines=("commission_assurance",))


def _actions_cma_underpaid(engines: EngineBundle) -> None:
    from utils.commission_assurance import (
        CommissionAssuranceEngine, PaidCommissionRecord)
    from datetime import date as _date
    eng = CommissionAssuranceEngine()
    plan = _make_default_plan()
    calc = eng.compute_expected_commission(
        plan, "rm-101", "2026-04", Decimal("200000"))   # exp 5000
    payments = (
        PaidCommissionRecord(
            payment_id="PAY-101", rm_code="rm-101",
            period="2026-04", paid_kes=Decimal("4000"),
            payment_date=_date(2026, 5, 5)),
    )
    engines["__cma02__"] = eng.validate_paid_vs_computed(
        calc, payments)


def _assertions_cma_underpaid(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.commission_assurance import CommissionFinding
    findings = engines.get("__cma02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="cma02-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cma02-a1",
            description="One UNDERPAID finding surfaced",
            expected="1 UNDERPAID",
            observed=(
                f"{len(findings)} / {findings[0].finding_type.value}"
                if findings else "0"),
            matched=(
                len(findings) == 1
                and findings[0].finding_type
                == CommissionFinding.UNDERPAID)),
        AssertionResult(
            assertion_id="cma02-a2",
            description="Variance -1000 KES (paid 4k, expected 5k)",
            expected="-1000",
            observed=(
                str(findings[0].variance_kes)
                if findings else "n/a"),
            matched=(
                len(findings) == 1
                and findings[0].variance_kes == Decimal("-1000"))),
    )


SCENARIO_CMA_02_UNDERPAID = Scenario(
    scenario_id="CMA-02", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-247: revenue 200k → expected 5k commission; paid 4k "
        "→ UNDERPAID finding with variance -1000. Composes with "
        "ENH-242 §commission_miscalc."),
    setup=_setup_cma, actions=_actions_cma_underpaid,
    assertions=_assertions_cma_underpaid,
    requires_engines=("commission_assurance",))


def _actions_cma_override(engines: EngineBundle) -> None:
    from utils.commission_assurance import (
        CommissionAssuranceEngine, CommissionOverride,
        OverrideStatus)
    eng = CommissionAssuranceEngine()
    overrides = (
        CommissionOverride(
            override_id="O-1", rm_code="rm-101",
            period="2026-04",
            delta_kes=Decimal("5000"),
            reason="Q1 performance bonus",
            status=OverrideStatus.APPROVED,
            approval_id=None),     # APPROVED but no approval_id
        CommissionOverride(
            override_id="O-2", rm_code="rm-102",
            period="2026-04",
            delta_kes=Decimal("3000"),
            reason="strategic deal close",
            status=OverrideStatus.APPROVED,
            approval_id="APP-2026-007"),
    )
    engines["__cma03__"] = eng.validate_overrides(overrides)


def _assertions_cma_override(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    results = engines.get("__cma03__")
    if results is None:
        return (AssertionResult(
            assertion_id="cma03-a0", description="Results populated",
            expected="present", observed="MISSING", matched=False),)
    by_id = {r.override_id: r for r in results}
    return (
        AssertionResult(
            assertion_id="cma03-a1",
            description=(
                "O-1 invalid (APPROVED without approval_id)"),
            expected="False",
            observed=(
                str(by_id["O-1"].valid)
                if "O-1" in by_id else "MISSING"),
            matched=(
                "O-1" in by_id and by_id["O-1"].valid is False)),
        AssertionResult(
            assertion_id="cma03-a2",
            description="O-2 valid (has approval_id)",
            expected="True",
            observed=(
                str(by_id["O-2"].valid)
                if "O-2" in by_id else "MISSING"),
            matched=(
                "O-2" in by_id and by_id["O-2"].valid is True)),
    )


SCENARIO_CMA_03_OVERRIDE = Scenario(
    scenario_id="CMA-03", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-247: 2 APPROVED overrides — one missing approval_id "
        "(invalid), one with approval_id (valid). Engine flags "
        "the missing-id case but never auto-approves anything."),
    setup=_setup_cma, actions=_actions_cma_override,
    assertions=_assertions_cma_override,
    requires_engines=("commission_assurance",))


def _actions_cma_disputes(engines: EngineBundle) -> None:
    from utils.commission_assurance import (
        CommissionAssuranceEngine, CommissionDispute,
        DisputeStatus)
    from datetime import date as _date
    eng = CommissionAssuranceEngine()
    disputes = (
        CommissionDispute(
            dispute_id="D-1", rm_code="rm-101",
            period="2026-03", status=DisputeStatus.UPHELD,
            raised_date=_date(2026, 4, 1),
            resolved_date=_date(2026, 4, 15)),    # 14 days
        CommissionDispute(
            dispute_id="D-2", rm_code="rm-102",
            period="2026-03", status=DisputeStatus.REJECTED,
            raised_date=_date(2026, 4, 5),
            resolved_date=_date(2026, 4, 12)),    # 7 days
        CommissionDispute(
            dispute_id="D-3", rm_code="rm-103",
            period="2026-04", status=DisputeStatus.OPEN,
            raised_date=_date(2026, 5, 1)),
    )
    engines["__cma04__"] = eng.summarize_disputes(disputes)


def _assertions_cma_disputes(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    s = engines.get("__cma04__")
    if s is None:
        return (AssertionResult(
            assertion_id="cma04-a0", description="Summary populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cma04-a1",
            description="1 OPEN, 1 UPHELD, 1 REJECTED",
            expected="1/1/1",
            observed=(
                f"{s.open_count}/{s.upheld_count}/"
                f"{s.rejected_count}"),
            matched=(
                s.open_count == 1
                and s.upheld_count == 1
                and s.rejected_count == 1)),
        AssertionResult(
            assertion_id="cma04-a2",
            description=(
                "Average resolution days = 10.5 (avg of 14 + 7)"),
            expected="10.50",
            observed=str(s.avg_resolution_days),
            matched=s.avg_resolution_days == Decimal("10.50")),
    )


SCENARIO_CMA_04_DISPUTES = Scenario(
    scenario_id="CMA-04", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-247: 3 disputes (1 UPHELD 14d, 1 REJECTED 7d, 1 "
        "OPEN). Summary aggregates counts + avg resolution = "
        "10.5d. Engine summarises but never auto-resolves "
        "disputes per Rule 7."),
    setup=_setup_cma, actions=_actions_cma_disputes,
    assertions=_assertions_cma_disputes,
    requires_engines=("commission_assurance",))


# ════════════════════════════════════════════════════════════════════════
# v10.57 — Regulatory Revenue Reporting (ENH-248)
# ════════════════════════════════════════════════════════════════════════

def _make_default_template():
    from utils.regulatory_revenue_reporting import (
        ReportTemplate, ReportLineSpec, Regulator)
    from datetime import date as _date
    return ReportTemplate(
        template_id="CBK-REV-Q1-2026",
        regulator=Regulator.CBK,
        period_label="2026-Q1",
        period_start=_date(2026, 1, 1),
        period_end=_date(2026, 3, 31),
        line_specs=(
            ReportLineSpec(
                line_code="L-INT", line_name="Interest income",
                revenue_categories=frozenset({"INTEREST_INCOME"}),
                required=True),
            ReportLineSpec(
                line_code="L-FEE", line_name="Fee income",
                revenue_categories=frozenset(
                    {"FEE_INCOME", "COMMISSION_INCOME"}),
                required=True),
            ReportLineSpec(
                line_code="L-FX", line_name="FX income",
                revenue_categories=frozenset(
                    {"FX_INCOME", "TRADING_INCOME"}),
                required=False),
        ))


def _make_revenue_record(rid, day, amt, cat, month=2):
    from utils.revenue_validation import RevenueRecord
    from datetime import date as _date
    return RevenueRecord(
        record_id=rid, source_system="CBS",
        posting_date=_date(2026, month, day),
        amount_kes=Decimal(str(amt)),
        revenue_category=cat, branch_code="NRB-01")


def _setup_orr(engines: EngineBundle) -> None:
    pass


def _actions_orr_generate(engines: EngineBundle) -> None:
    from utils.regulatory_revenue_reporting import (
        RegulatoryRevenueReportingEngine)
    eng = RegulatoryRevenueReportingEngine()
    template = _make_default_template()
    records = (
        _make_revenue_record("r1", 5, 500000, "INTEREST_INCOME"),
        _make_revenue_record(
            "r2", 15, 300000, "INTEREST_INCOME"),
        _make_revenue_record("r3", 20, 100000, "FEE_INCOME"),
        _make_revenue_record(
            "r4", 25, 50000, "COMMISSION_INCOME"),
    )
    engines["__orr01__"] = eng.generate_report(template, records)


def _assertions_orr_generate(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    pkg = engines.get("__orr01__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="orr01-a0", description="Package populated",
            expected="present", observed="MISSING", matched=False),)
    int_line = next(
        (l for l in pkg.line_items if l.line_code == "L-INT"),
        None)
    fee_line = next(
        (l for l in pkg.line_items if l.line_code == "L-FEE"),
        None)
    return (
        AssertionResult(
            assertion_id="orr01-a1",
            description="Interest line aggregated to 800k",
            expected="800000",
            observed=str(int_line.amount_kes) if int_line else "n/a",
            matched=int_line is not None
            and int_line.amount_kes == Decimal("800000")),
        AssertionResult(
            assertion_id="orr01-a2",
            description=(
                "Fee line aggregates FEE + COMMISSION = 150k"),
            expected="150000",
            observed=str(fee_line.amount_kes) if fee_line else "n/a",
            matched=fee_line is not None
            and fee_line.amount_kes == Decimal("150000")),
        AssertionResult(
            assertion_id="orr01-a3",
            description="Total = 950k; 4 contributing record IDs",
            expected="950000",
            observed=str(pkg.total_kes),
            matched=pkg.total_kes == Decimal("950000")),
        AssertionResult(
            assertion_id="orr01-a4",
            description="Per Rule 1: contributing record IDs surfaced",
            expected="r1+r2 in INT, r3+r4 in FEE",
            observed=(
                f"INT={list(int_line.contributing_record_ids) if int_line else []}, "
                f"FEE={list(fee_line.contributing_record_ids) if fee_line else []}"),
            matched=(
                int_line is not None and fee_line is not None
                and "r1" in int_line.contributing_record_ids
                and "r2" in int_line.contributing_record_ids
                and "r3" in fee_line.contributing_record_ids)),
    )


SCENARIO_ORR_01_GENERATE = Scenario(
    scenario_id="ORR-01", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-248: 4 records mapped via 2 line specs (INT 800k, "
        "FEE+COMMISSION 150k). Per Rule 1, contributing record "
        "IDs surface in each line item so a CBK reviewer can "
        "trace any line back to source records."),
    setup=_setup_orr, actions=_actions_orr_generate,
    assertions=_assertions_orr_generate,
    requires_engines=("regulatory_revenue_reporting",))


def _actions_orr_recon(engines: EngineBundle) -> None:
    from utils.regulatory_revenue_reporting import (
        RegulatoryRevenueReportingEngine, StatutoryReportRecord)
    from datetime import date as _date
    eng = RegulatoryRevenueReportingEngine()
    template = _make_default_template()
    records = (
        _make_revenue_record(
            "r1", 5, 1000000, "INTEREST_INCOME"),
        _make_revenue_record("r2", 10, 500000, "FEE_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    statutory = (
        # Within 5% of mgmt — TIMING
        StatutoryReportRecord(
            line_code="L-INT", period_label="2026-Q1",
            amount_kes=Decimal("1020000"),
            submitted_date=_date(2026, 4, 30)),
        # 50% off — GENUINE
        StatutoryReportRecord(
            line_code="L-FEE", period_label="2026-Q1",
            amount_kes=Decimal("250000"),
            submitted_date=_date(2026, 4, 30)),
    )
    engines["__orr02__"] = (
        eng.reconcile_management_vs_statutory(pkg, statutory))


def _assertions_orr_recon(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.regulatory_revenue_reporting import (
        DifferenceType)
    result = engines.get("__orr02__")
    if result is None:
        return (AssertionResult(
            assertion_id="orr02-a0", description="Result populated",
            expected="present", observed="MISSING", matched=False),)
    by_line = {d.line_code: d for d in result.differences}
    return (
        AssertionResult(
            assertion_id="orr02-a1",
            description="L-INT classified TIMING (within 5%)",
            expected=DifferenceType.TIMING.value,
            observed=(
                by_line["L-INT"].classification.value
                if "L-INT" in by_line else "MISSING"),
            matched=(
                "L-INT" in by_line
                and by_line["L-INT"].classification
                == DifferenceType.TIMING)),
        AssertionResult(
            assertion_id="orr02-a2",
            description=(
                "L-FEE classified GENUINE (>5% variance)"),
            expected=DifferenceType.GENUINE.value,
            observed=(
                by_line["L-FEE"].classification.value
                if "L-FEE" in by_line else "MISSING"),
            matched=(
                "L-FEE" in by_line
                and by_line["L-FEE"].classification
                == DifferenceType.GENUINE)),
        AssertionResult(
            assertion_id="orr02-a3",
            description=(
                "Aggregates by_classification populated"),
            expected="TIMING≥1, GENUINE≥1",
            observed=str(result.by_classification),
            matched=(
                result.by_classification.get("TIMING", 0) >= 1
                and result.by_classification
                .get("GENUINE", 0) >= 1)),
    )


SCENARIO_ORR_02_RECON = Scenario(
    scenario_id="ORR-02", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-248: management vs statutory recon — L-INT 1m vs "
        "1.02m (2% variance → TIMING), L-FEE 500k vs 250k (50% "
        "variance → GENUINE). 5% threshold separates routine "
        "cut-off differences from items needing investigation."),
    setup=_setup_orr, actions=_actions_orr_recon,
    assertions=_assertions_orr_recon,
    requires_engines=("regulatory_revenue_reporting",))


def _actions_orr_unmapped(engines: EngineBundle) -> None:
    from utils.regulatory_revenue_reporting import (
        RegulatoryRevenueReportingEngine)
    eng = RegulatoryRevenueReportingEngine()
    template = _make_default_template()
    records = (
        _make_revenue_record("r1", 5, 100000, "INTEREST_INCOME"),
        # Unmapped category — must surface, not silently drop
        _make_revenue_record("r2", 10, 50000, "OTHER_INCOME"),
        _make_revenue_record(
            "r3", 15, 30000, "GAINS_ON_SECURITIES"),
    )
    pkg = eng.generate_report(template, records)
    rep = eng.validate_completeness(pkg, template)
    engines["__orr03__"] = (pkg, rep)


def _assertions_orr_unmapped(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.regulatory_revenue_reporting import (
        CompletenessIssue)
    payload = engines.get("__orr03__")
    if payload is None:
        return (AssertionResult(
            assertion_id="orr03-a0", description="Payload populated",
            expected="present", observed="MISSING", matched=False),)
    pkg, rep = payload
    return (
        AssertionResult(
            assertion_id="orr03-a1",
            description=(
                "2 unmapped categories surfaced rather than "
                "dropped"),
            expected=(
                "OTHER_INCOME + GAINS_ON_SECURITIES in "
                "unmapped_categories"),
            observed=str(pkg.unmapped_categories),
            matched=(
                "OTHER_INCOME" in pkg.unmapped_categories
                and "GAINS_ON_SECURITIES"
                in pkg.unmapped_categories)),
        AssertionResult(
            assertion_id="orr03-a2",
            description=(
                "Completeness flags UNMAPPED_CATEGORY finding"),
            expected="≥1 UNMAPPED_CATEGORY finding",
            observed=str([
                f.issue.value for f in rep.findings]),
            matched=any(
                f.issue == CompletenessIssue.UNMAPPED_CATEGORY
                for f in rep.findings)),
    )


SCENARIO_ORR_03_UNMAPPED = Scenario(
    scenario_id="ORR-03", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-248: 2 records with categories not in any "
        "ReportLineSpec — surfaced as unmapped_categories per "
        "Rule 1 (silent dropping would risk under-reporting). "
        "Completeness validation flags UNMAPPED_CATEGORY for "
        "human follow-up."),
    setup=_setup_orr, actions=_actions_orr_unmapped,
    assertions=_assertions_orr_unmapped,
    requires_engines=("regulatory_revenue_reporting",))


def _actions_orr_completeness(engines: EngineBundle) -> None:
    from utils.regulatory_revenue_reporting import (
        RegulatoryRevenueReportingEngine)
    eng = RegulatoryRevenueReportingEngine()
    template = _make_default_template()
    # Only INTEREST records — FEE line stays at zero (required!)
    records = (
        _make_revenue_record("r1", 5, 1000000, "INTEREST_INCOME"),
    )
    pkg = eng.generate_report(template, records)
    engines["__orr04__"] = (
        pkg, eng.validate_completeness(pkg, template))


def _assertions_orr_completeness(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.regulatory_revenue_reporting import (
        CompletenessIssue)
    payload = engines.get("__orr04__")
    if payload is None:
        return (AssertionResult(
            assertion_id="orr04-a0", description="Payload populated",
            expected="present", observed="MISSING", matched=False),)
    pkg, rep = payload
    fee_findings = [
        f for f in rep.findings if f.line_code == "L-FEE"]
    return (
        AssertionResult(
            assertion_id="orr04-a1",
            description=(
                "L-FEE flagged ZERO_AMOUNT_REQUIRED_LINE"),
            expected=(
                CompletenessIssue
                .ZERO_AMOUNT_REQUIRED_LINE.value),
            observed=(
                fee_findings[0].issue.value
                if fee_findings else "MISSING"),
            matched=(
                len(fee_findings) == 1
                and fee_findings[0].issue
                == CompletenessIssue
                .ZERO_AMOUNT_REQUIRED_LINE)),
        AssertionResult(
            assertion_id="orr04-a2",
            description=(
                "L-FX (not required) NOT flagged when zero"),
            expected="no findings for L-FX",
            observed=(
                str([f.line_code for f in rep.findings])),
            matched=not any(
                f.line_code == "L-FX" for f in rep.findings)),
        AssertionResult(
            assertion_id="orr04-a3",
            description=(
                "Required lines count tracked"),
            expected="2 required lines",
            observed=str(rep.required_lines),
            matched=rep.required_lines == 2),
    )


SCENARIO_ORR_04_COMPLETENESS = Scenario(
    scenario_id="ORR-04", category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-248: required L-FEE line populated with zero → "
        "ZERO_AMOUNT_REQUIRED_LINE finding (verify intentional). "
        "Optional L-FX zero NOT flagged. Required-vs-optional "
        "distinction prevents noise on lines that legitimately "
        "have no activity."),
    setup=_setup_orr, actions=_actions_orr_completeness,
    assertions=_assertions_orr_completeness,
    requires_engines=("regulatory_revenue_reporting",))


# ════════════════════════════════════════════════════════════════════════
# v10.59 — Continuous Close Orchestration (ENH-249) — finance arc opens
# ════════════════════════════════════════════════════════════════════════

# FCO-01: Missing recurring monthly accrual flagged
def _setup_fco(engines: EngineBundle) -> None:
    pass


def _actions_fco_missing_accrual(engines: EngineBundle) -> None:
    from utils.finance_close_orchestrator import (
        FinanceCloseOrchestrator, RecurringAccrualSchedule,
        AccrualFrequency)
    eng = FinanceCloseOrchestrator()
    sched = RecurringAccrualSchedule(
        schedule_id="RENT-MONTHLY",
        account_code="6100",
        periodic_amount_kes=Decimal("500000"),
        frequency=AccrualFrequency.MONTHLY,
        contra_account_code="2100",
        description="HQ rent monthly accrual")
    engines["__fco01__"] = eng.detect_missing_recurring_accruals(
        (sched,), (), "2026-04")


def _assertions_fco_missing_accrual(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_close_orchestrator import (
        CloseTaskType, CloseTaskSeverity)
    tasks = engines.get("__fco01__")
    if tasks is None:
        return (AssertionResult(
            assertion_id="fco01-a0", description="Tasks populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fco01-a1",
            description="One MISSING_RECURRING_ACCRUAL task",
            expected="1",
            observed=str(len(tasks)),
            matched=len(tasks) == 1),
        AssertionResult(
            assertion_id="fco01-a2",
            description="Severity HIGH",
            expected=CloseTaskSeverity.HIGH.value,
            observed=(
                tasks[0].severity.value if tasks else "n/a"),
            matched=(
                len(tasks) == 1
                and tasks[0].severity == CloseTaskSeverity.HIGH)),
        AssertionResult(
            assertion_id="fco01-a3",
            description="Recommended Dr 500k to 6100",
            expected="Dr 500000 / 6100",
            observed=(
                f"Dr {tasks[0].recommended_debit_kes} / "
                f"{tasks[0].account_code}"
                if tasks else "n/a"),
            matched=(
                len(tasks) == 1
                and tasks[0].recommended_debit_kes
                == Decimal("500000")
                and tasks[0].account_code == "6100")),
        AssertionResult(
            assertion_id="fco01-a4",
            description="Contra 2100 surfaced for Rule 1",
            expected="2100",
            observed=(
                tasks[0].contra_account_code or "n/a"),
            matched=(
                len(tasks) == 1
                and tasks[0].contra_account_code == "2100")),
    )


SCENARIO_FCO_01_MISSING_ACCRUAL = Scenario(
    scenario_id="FCO-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-249: monthly rent accrual schedule defined but no "
        "GLEntry posted for 2026-04 → HIGH severity "
        "MISSING_RECURRING_ACCRUAL task with Dr 500k / Cr 2100 "
        "recommendation. Rule 1 surfaces both account codes."),
    setup=_setup_fco,
    actions=_actions_fco_missing_accrual,
    assertions=_assertions_fco_missing_accrual,
    requires_engines=("finance_close_orchestrator",))


# FCO-02: Suspense balance critical
def _actions_fco_suspense(engines: EngineBundle) -> None:
    from utils.finance_close_orchestrator import (
        FinanceCloseOrchestrator, CloseAccount, GLEntry,
        AccountType)
    from datetime import date as _date
    eng = FinanceCloseOrchestrator()
    accounts = (
        CloseAccount(
            account_code="9999",
            account_name="Suspense — Cash Receipts",
            account_type=AccountType.ASSET,
            is_suspense=True),
    )
    e1 = GLEntry(
        entry_id="e1", account_code="9999",
        debit_kes=Decimal("250000"),
        credit_kes=Decimal("0"),
        posting_date=_date(2026, 4, 10), period="2026-04")
    e2 = GLEntry(
        entry_id="e2", account_code="9999",
        debit_kes=Decimal("0"),
        credit_kes=Decimal("100000"),
        posting_date=_date(2026, 4, 25), period="2026-04")
    engines["__fco02__"] = eng.detect_suspense_balances(
        accounts, (e1, e2), "2026-04")


def _assertions_fco_suspense(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_close_orchestrator import (
        CloseTaskSeverity, CloseTaskType)
    tasks = engines.get("__fco02__")
    if tasks is None:
        return (AssertionResult(
            assertion_id="fco02-a0", description="Tasks populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fco02-a1",
            description="One SUSPENSE_BALANCE task",
            expected="1",
            observed=str(len(tasks)),
            matched=len(tasks) == 1),
        AssertionResult(
            assertion_id="fco02-a2",
            description="CRITICAL severity (blocks close)",
            expected=CloseTaskSeverity.CRITICAL.value,
            observed=(
                tasks[0].severity.value if tasks else "n/a"),
            matched=(
                len(tasks) == 1
                and tasks[0].severity
                == CloseTaskSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="fco02-a3",
            description="Net balance 150k surfaced in description",
            expected="150000 in description",
            observed=tasks[0].description if tasks else "n/a",
            matched=(
                len(tasks) == 1
                and "150000" in tasks[0].description)),
    )


SCENARIO_FCO_02_SUSPENSE_CRITICAL = Scenario(
    scenario_id="FCO-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-249: suspense account 9999 has Dr 250k + Cr 100k = "
        "Dr 150k net at 2026-04 close → CRITICAL "
        "SUSPENSE_BALANCE task. Severity is CRITICAL because all "
        "suspense must clear before close certification."),
    setup=_setup_fco,
    actions=_actions_fco_suspense,
    assertions=_assertions_fco_suspense,
    requires_engines=("finance_close_orchestrator",))


# FCO-03: Intercompany pending — one-sided posting
def _actions_fco_ic(engines: EngineBundle) -> None:
    from utils.finance_close_orchestrator import (
        FinanceCloseOrchestrator, CloseAccount, GLEntry,
        AccountType)
    from datetime import date as _date
    eng = FinanceCloseOrchestrator()
    accounts = (
        CloseAccount(
            account_code="IC-1500",
            account_name="Due from SubA",
            account_type=AccountType.ASSET,
            is_intercompany=True,
            entity_id="PARENT"),
    )
    # Only Dr posted, no offsetting Cr
    e = GLEntry(
        entry_id="e1", account_code="IC-1500",
        debit_kes=Decimal("750000"),
        credit_kes=Decimal("0"),
        posting_date=_date(2026, 4, 15), period="2026-04",
        reference="IC-INV-Q2-001",
        counterparty_entity_id="SUBA")
    engines["__fco03__"] = eng.detect_intercompany_pending(
        accounts, (e,), "2026-04")


def _assertions_fco_ic(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_close_orchestrator import (
        CloseTaskType)
    tasks = engines.get("__fco03__")
    if tasks is None:
        return (AssertionResult(
            assertion_id="fco03-a0", description="Tasks populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fco03-a1",
            description="One INTERCOMPANY_PENDING task",
            expected="1",
            observed=str(len(tasks)),
            matched=len(tasks) == 1),
        AssertionResult(
            assertion_id="fco03-a2",
            description="task_type INTERCOMPANY_PENDING",
            expected=CloseTaskType.INTERCOMPANY_PENDING.value,
            observed=(
                tasks[0].task_type.value if tasks else "n/a"),
            matched=(
                len(tasks) == 1
                and tasks[0].task_type
                == CloseTaskType.INTERCOMPANY_PENDING)),
        AssertionResult(
            assertion_id="fco03-a3",
            description="Counterparty SUBA in description",
            expected="SUBA",
            observed=tasks[0].description if tasks else "n/a",
            matched=(
                len(tasks) == 1
                and "SUBA" in tasks[0].description)),
        AssertionResult(
            assertion_id="fco03-a4",
            description="Source entry e1 in related_ids",
            expected="e1 in related_ids",
            observed=str(tasks[0].related_ids) if tasks else "n/a",
            matched=(
                len(tasks) == 1
                and "e1" in tasks[0].related_ids)),
    )


SCENARIO_FCO_03_IC_PENDING = Scenario(
    scenario_id="FCO-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-249: parent posted Dr IC-1500 750k vs SUBA but no "
        "offsetting Cr posted on SUBA's books → "
        "INTERCOMPANY_PENDING task; counterparty SUBA surfaced "
        "in description; source entry e1 surfaced in "
        "related_ids per Rule 1."),
    setup=_setup_fco,
    actions=_actions_fco_ic,
    assertions=_assertions_fco_ic,
    requires_engines=("finance_close_orchestrator",))


# FCO-04: generate_close_report orchestrator
def _actions_fco_orchestrator(engines: EngineBundle) -> None:
    from utils.finance_close_orchestrator import (
        FinanceCloseOrchestrator, CloseAccount, GLEntry,
        AccountType, RecurringAccrualSchedule, AccrualFrequency,
        PrepaymentSchedule)
    from datetime import date as _date
    eng = FinanceCloseOrchestrator()
    accounts = (
        CloseAccount(
            account_code="9999", account_name="Suspense",
            account_type=AccountType.ASSET,
            is_suspense=True),
    )
    schedule = RecurringAccrualSchedule(
        schedule_id="RENT", account_code="6100",
        periodic_amount_kes=Decimal("500000"),
        frequency=AccrualFrequency.MONTHLY,
        contra_account_code="2100")
    prep = PrepaymentSchedule(
        schedule_id="INSURANCE-2026",
        prepaid_account_code="1500",
        expense_account_code="6500",
        total_amount_kes=Decimal("120000"),
        periodic_amount_kes=Decimal("10000"),
        start_period="2026-01",
        end_period="2026-12")
    susp_entry = GLEntry(
        entry_id="susp1", account_code="9999",
        debit_kes=Decimal("75000"),
        credit_kes=Decimal("0"),
        posting_date=_date(2026, 4, 20), period="2026-04")
    engines["__fco04__"] = eng.generate_close_report(
        period="2026-04",
        accounts=accounts,
        entries=(susp_entry,),
        recurring_schedules=(schedule,),
        prepayment_schedules=(prep,),
        period_start_date=_date(2026, 4, 1),
        period_end_date=_date(2026, 4, 30))


def _assertions_fco_orchestrator(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_close_orchestrator import (
        CloseTaskType, CloseTaskSeverity, CloseReadinessReport)
    r = engines.get("__fco04__")
    if r is None:
        return (AssertionResult(
            assertion_id="fco04-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    types = {t.task_type for t in r.tasks}
    return (
        AssertionResult(
            assertion_id="fco04-a1",
            description=(
                "Report has all 3 expected task types "
                "(missing_accrual + prepayment + suspense)"),
            expected="3 distinct task types",
            observed=str([t.value for t in types]),
            matched=(
                CloseTaskType.MISSING_RECURRING_ACCRUAL in types
                and CloseTaskType.PREPAYMENT_AMORTIZATION_DUE
                in types
                and CloseTaskType.SUSPENSE_BALANCE in types)),
        AssertionResult(
            assertion_id="fco04-a2",
            description="Target close days = 3 (Gartner default)",
            expected="3",
            observed=str(r.target_close_days),
            matched=r.target_close_days == 3),
        AssertionResult(
            assertion_id="fco04-a3",
            description=(
                "by_severity surfaces CRITICAL ≥1 (suspense)"),
            expected="≥ 1 CRITICAL",
            observed=str(r.by_severity),
            matched=r.by_severity.get(
                CloseTaskSeverity.CRITICAL.value, 0) >= 1),
        AssertionResult(
            assertion_id="fco04-a4",
            description=(
                "Framework refs cite ENH-249 + Rule 7 "
                "diagnostic-only stance"),
            expected="ENH-249 + Rule 7 in refs",
            observed=" / ".join(r.framework_refs),
            matched=(
                any("ENH-249" in ref for ref in r.framework_refs)
                and any(
                    "Rule 7" in ref for ref in r.framework_refs))),
    )


SCENARIO_FCO_04_ORCHESTRATOR = Scenario(
    scenario_id="FCO-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-249 generate_close_report: monthly rent missing + "
        "monthly insurance prepayment due + KES 75k suspense "
        "balance → 3 distinct task types; CRITICAL severity "
        "from suspense; target_close_days=3 (Gartner default); "
        "framework refs cite ENH-249 + Rule 7 diagnostic-only "
        "stance per Rule 1."),
    setup=_setup_fco,
    actions=_actions_fco_orchestrator,
    assertions=_assertions_fco_orchestrator,
    requires_engines=("finance_close_orchestrator",))


# ════════════════════════════════════════════════════════════════════════
# v10.60 — Intercompany Matching & Elimination (ENH-250)
# ════════════════════════════════════════════════════════════════════════

def _setup_icm(engines: EngineBundle) -> None:
    pass


# ICM-01 EXACT MATCH
def _actions_icm_exact(engines: EngineBundle) -> None:
    from utils.intercompany_matching import (
        IntercompanyMatchingEngine, IcEntry, EliminationType)
    eng = IntercompanyMatchingEngine()
    a = IcEntry(
        entry_id="a", entity_id="PARENT",
        counterparty_entity_id="SUBA",
        account_code="IC-1500",
        debit_kes=Decimal("100000"),
        credit_kes=Decimal("0"),
        period="2026-04", reference="IC-INV-001",
        elimination_type=EliminationType.REVENUE_EXPENSE)
    b = IcEntry(
        entry_id="b", entity_id="SUBA",
        counterparty_entity_id="PARENT",
        account_code="IC-2500",
        debit_kes=Decimal("0"),
        credit_kes=Decimal("100000"),
        period="2026-04", reference="IC-INV-001",
        elimination_type=EliminationType.REVENUE_EXPENSE)
    engines["__icm01__"] = eng.match_pairs((a, b), "2026-04")


def _assertions_icm_exact(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.intercompany_matching import (
        MatchStatus, IcSeverity)
    matches = engines.get("__icm01__")
    if matches is None:
        return (AssertionResult(
            assertion_id="icm01-a0", description="Matches populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="icm01-a1",
            description="Single EXACT match",
            expected="1 EXACT",
            observed=(
                f"{len(matches)} {matches[0].status.value}"
                if matches else "n/a"),
            matched=(
                len(matches) == 1
                and matches[0].status == MatchStatus.EXACT)),
        AssertionResult(
            assertion_id="icm01-a2",
            description="Severity LOW (within tolerance)",
            expected=IcSeverity.LOW.value,
            observed=(
                matches[0].severity.value if matches else "n/a"),
            matched=(
                matches and matches[0].severity == IcSeverity.LOW)),
        AssertionResult(
            assertion_id="icm01-a3",
            description="Elimination recommendation produced",
            expected="non-None",
            observed=str(
                matches[0].recommended_elimination is not None
                if matches else False),
            matched=(
                matches
                and matches[0].recommended_elimination
                is not None)),
        AssertionResult(
            assertion_id="icm01-a4",
            description="Elimination amount = 100,000 KES",
            expected="100000",
            observed=(
                str(matches[0].recommended_elimination.amount_kes)
                if matches
                and matches[0].recommended_elimination
                else "n/a"),
            matched=(
                matches
                and matches[0].recommended_elimination
                and matches[0].recommended_elimination.amount_kes
                == Decimal("100000"))),
    )


SCENARIO_ICM_01_EXACT = Scenario(
    scenario_id="ICM-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-250: PARENT books Dr 100k IC-1500 vs SUBA, SUBA "
        "books Cr 100k IC-2500 vs PARENT, both ref IC-INV-001 → "
        "EXACT match (LOW severity, within tolerance) with "
        "elimination recommendation populated; amount 100k "
        "surfaced for the consolidation entry."),
    setup=_setup_icm,
    actions=_actions_icm_exact,
    assertions=_assertions_icm_exact,
    requires_engines=("intercompany_matching",))


# ICM-02 AMOUNT MISMATCH
def _actions_icm_mismatch(engines: EngineBundle) -> None:
    from utils.intercompany_matching import (
        IntercompanyMatchingEngine, IcEntry, EliminationType)
    eng = IntercompanyMatchingEngine()
    a = IcEntry(
        entry_id="a", entity_id="PARENT",
        counterparty_entity_id="SUBB",
        account_code="IC-1500",
        debit_kes=Decimal("500000"),
        credit_kes=Decimal("0"),
        period="2026-04", reference="IC-INV-Q2-005",
        elimination_type=EliminationType.RECEIVABLE_PAYABLE)
    b = IcEntry(
        entry_id="b", entity_id="SUBB",
        counterparty_entity_id="PARENT",
        account_code="IC-2500",
        debit_kes=Decimal("0"),
        credit_kes=Decimal("475000"),
        period="2026-04", reference="IC-INV-Q2-005",
        elimination_type=EliminationType.RECEIVABLE_PAYABLE)
    engines["__icm02__"] = eng.match_pairs((a, b), "2026-04")


def _assertions_icm_mismatch(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.intercompany_matching import (
        MatchStatus, IcSeverity)
    matches = engines.get("__icm02__")
    if matches is None:
        return (AssertionResult(
            assertion_id="icm02-a0", description="Matches populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="icm02-a1",
            description="One AMOUNT_MISMATCH",
            expected=MatchStatus.AMOUNT_MISMATCH.value,
            observed=(
                matches[0].status.value if matches else "n/a"),
            matched=(
                len(matches) == 1
                and matches[0].status
                == MatchStatus.AMOUNT_MISMATCH)),
        AssertionResult(
            assertion_id="icm02-a2",
            description="Severity HIGH",
            expected=IcSeverity.HIGH.value,
            observed=(
                matches[0].severity.value if matches else "n/a"),
            matched=(
                matches
                and matches[0].severity == IcSeverity.HIGH)),
        AssertionResult(
            assertion_id="icm02-a3",
            description="Variance = 25,000",
            expected="25000",
            observed=(
                str(matches[0].variance_kes) if matches else "n/a"),
            matched=(
                matches
                and matches[0].variance_kes == Decimal("25000"))),
        AssertionResult(
            assertion_id="icm02-a4",
            description=(
                "No elimination — humans must reconcile first"),
            expected="None",
            observed=str(
                matches[0].recommended_elimination
                if matches else "n/a"),
            matched=(
                matches
                and matches[0].recommended_elimination is None)),
    )


SCENARIO_ICM_02_MISMATCH = Scenario(
    scenario_id="ICM-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-250: PARENT books Dr 500k vs SUBB, SUBB books Cr "
        "475k vs PARENT (variance 25k, exceeds default 100 "
        "tolerance) → AMOUNT_MISMATCH HIGH severity; no "
        "elimination recommended (operator must reconcile first "
        "per Rule 7 — engine doesn't decide which side is "
        "correct)."),
    setup=_setup_icm,
    actions=_actions_icm_mismatch,
    assertions=_assertions_icm_mismatch,
    requires_engines=("intercompany_matching",))


# ICM-03 UNMATCHED
def _actions_icm_unmatched(engines: EngineBundle) -> None:
    from utils.intercompany_matching import (
        IntercompanyMatchingEngine, IcEntry, EliminationType)
    eng = IntercompanyMatchingEngine()
    e = IcEntry(
        entry_id="solo", entity_id="PARENT",
        counterparty_entity_id="SUBC",
        account_code="IC-1500",
        debit_kes=Decimal("250000"),
        credit_kes=Decimal("0"),
        period="2026-04", reference="IC-LOAN-2026-Q2",
        elimination_type=EliminationType.LOAN)
    engines["__icm03__"] = eng.match_pairs((e,), "2026-04")


def _assertions_icm_unmatched(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.intercompany_matching import (
        MatchStatus, IcSeverity)
    matches = engines.get("__icm03__")
    if matches is None:
        return (AssertionResult(
            assertion_id="icm03-a0", description="Matches populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="icm03-a1",
            description="UNMATCHED status",
            expected=MatchStatus.UNMATCHED.value,
            observed=(
                matches[0].status.value if matches else "n/a"),
            matched=(
                len(matches) == 1
                and matches[0].status == MatchStatus.UNMATCHED)),
        AssertionResult(
            assertion_id="icm03-a2",
            description="HIGH severity",
            expected=IcSeverity.HIGH.value,
            observed=(
                matches[0].severity.value if matches else "n/a"),
            matched=(
                matches
                and matches[0].severity == IcSeverity.HIGH)),
        AssertionResult(
            assertion_id="icm03-a3",
            description="entity_b = SUBC (counterparty)",
            expected="SUBC",
            observed=matches[0].entity_b if matches else "n/a",
            matched=(
                matches and matches[0].entity_b == "SUBC")),
    )


SCENARIO_ICM_03_UNMATCHED = Scenario(
    scenario_id="ICM-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-250: PARENT books Dr 250k IC-LOAN vs SUBC but no "
        "offsetting Cr from SUBC → UNMATCHED HIGH severity; "
        "counterparty surfaced as entity_b for triage."),
    setup=_setup_icm,
    actions=_actions_icm_unmatched,
    assertions=_assertions_icm_unmatched,
    requires_engines=("intercompany_matching",))


# ICM-04 match_all orchestrator
def _actions_icm_orchestrator(engines: EngineBundle) -> None:
    from utils.intercompany_matching import (
        IntercompanyMatchingEngine, IcEntry, EliminationType)
    eng = IntercompanyMatchingEngine()
    a = IcEntry(
        entry_id="a", entity_id="PARENT",
        counterparty_entity_id="SUBA",
        account_code="IC-1500",
        debit_kes=Decimal("100000"),
        credit_kes=Decimal("0"),
        period="2026-04", reference="R1",
        elimination_type=EliminationType.REVENUE_EXPENSE)
    b = IcEntry(
        entry_id="b", entity_id="SUBA",
        counterparty_entity_id="PARENT",
        account_code="IC-2500",
        debit_kes=Decimal("0"),
        credit_kes=Decimal("100000"),
        period="2026-04", reference="R1",
        elimination_type=EliminationType.REVENUE_EXPENSE)
    solo = IcEntry(
        entry_id="solo", entity_id="PARENT",
        counterparty_entity_id="SUBD",
        account_code="IC-1500",
        debit_kes=Decimal("75000"),
        credit_kes=Decimal("0"),
        period="2026-04", reference="R2",
        elimination_type=EliminationType.LOAN)
    chain1 = IcEntry(
        entry_id="ch1", entity_id="P",
        counterparty_entity_id="S1",
        account_code="IC-1500",
        debit_kes=Decimal("200000"),
        credit_kes=Decimal("0"),
        period="2026-04", reference="CHAIN-A",
        elimination_type=EliminationType.LOAN,
        chain_id="CHAIN-A")
    chain2 = IcEntry(
        entry_id="ch2", entity_id="S1",
        counterparty_entity_id="P",
        account_code="IC-2500",
        debit_kes=Decimal("0"),
        credit_kes=Decimal("200000"),
        period="2026-04", reference="CHAIN-A",
        elimination_type=EliminationType.LOAN,
        chain_id="CHAIN-A")
    engines["__icm04__"] = eng.match_all(
        (a, b, solo, chain1, chain2), "2026-04")


def _assertions_icm_orchestrator(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.intercompany_matching import (
        MatchStatus, IcMatchReport)
    r = engines.get("__icm04__")
    if r is None:
        return (AssertionResult(
            assertion_id="icm04-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    statuses = {m.status for m in r.matches}
    return (
        AssertionResult(
            assertion_id="icm04-a1",
            description="3 status types: EXACT/UNMATCHED/CHAIN",
            expected="3 distinct",
            observed=str([s.value for s in statuses]),
            matched=(
                MatchStatus.EXACT in statuses
                and MatchStatus.UNMATCHED in statuses
                and MatchStatus.MULTI_LEG_CHAIN in statuses)),
        AssertionResult(
            assertion_id="icm04-a2",
            description="1 elimination recommended (only EXACT)",
            expected="1",
            observed=str(r.total_eliminations_recommended),
            matched=r.total_eliminations_recommended == 1),
        AssertionResult(
            assertion_id="icm04-a3",
            description="≥4 entities scanned",
            expected="≥ 4",
            observed=str(r.entities_scanned),
            matched=r.entities_scanned >= 4),
        AssertionResult(
            assertion_id="icm04-a4",
            description="Framework refs cite ENH-250 + Rule 7",
            expected="ENH-250 + Rule 7 in refs",
            observed=" / ".join(r.framework_refs),
            matched=(
                any("ENH-250" in ref for ref in r.framework_refs)
                and any(
                    "Rule 7" in ref for ref in r.framework_refs))),
    )


SCENARIO_ICM_04_ORCHESTRATOR = Scenario(
    scenario_id="ICM-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-250 match_all: 1 paired EXACT match + 1 unmatched "
        "solo + 1 balanced 2-leg chain → 3 status types in "
        "report; only the EXACT match triggers an elimination "
        "recommendation; framework refs cite ENH-250 + Rule 7 "
        "diagnostic-only stance per Rule 1."),
    setup=_setup_icm,
    actions=_actions_icm_orchestrator,
    assertions=_assertions_icm_orchestrator,
    requires_engines=("intercompany_matching",))


# ════════════════════════════════════════════════════════════════════════
# v10.61 — Group Consolidation operational TB (ENH-251)
# ════════════════════════════════════════════════════════════════════════

def _setup_gcs(engines: EngineBundle) -> None:
    pass


# GCS-01 simple aggregation
def _actions_gcs_aggregation(engines: EngineBundle) -> None:
    from utils.consolidated_tb_engine import (
        ConsolidatedTrialBalanceEngine, EntityProfile,
        TrialBalanceLine)
    from utils.finance_close_orchestrator import AccountType
    eng = ConsolidatedTrialBalanceEngine()
    p = EntityProfile(
        entity_id="PARENT", entity_name="Parent",
        parent_ownership_pct=Decimal("1"),
        functional_currency="KES", is_parent=True)
    s = EntityProfile(
        entity_id="SUBA", entity_name="Sub A",
        parent_ownership_pct=Decimal("1"),
        functional_currency="KES")
    tb = (
        TrialBalanceLine(
            entity_id="PARENT", account_code="1000",
            account_type=AccountType.ASSET,
            debit_kes=Decimal("5000000"),
            credit_kes=Decimal("0"), period="2026-04"),
        TrialBalanceLine(
            entity_id="SUBA", account_code="1000",
            account_type=AccountType.ASSET,
            debit_kes=Decimal("2000000"),
            credit_kes=Decimal("0"), period="2026-04"),
    )
    engines["__gcs01__"] = eng.consolidate(
        "2026-04", (p, s), tb)


def _assertions_gcs_aggregation(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__gcs01__")
    if r is None:
        return (AssertionResult(
            assertion_id="gcs01-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    line = r.lines[0] if r.lines else None
    return (
        AssertionResult(
            assertion_id="gcs01-a1",
            description="Single consolidated line",
            expected="1",
            observed=str(len(r.lines)),
            matched=len(r.lines) == 1),
        AssertionResult(
            assertion_id="gcs01-a2",
            description="Aggregated Dr = 7,000,000",
            expected="7000000",
            observed=(
                str(line.pre_elimination_dr)
                if line else "n/a"),
            matched=(
                line and line.pre_elimination_dr
                == Decimal("7000000"))),
        AssertionResult(
            assertion_id="gcs01-a3",
            description="2 entity contributions surfaced",
            expected="2",
            observed=(
                str(len(line.entity_contributions))
                if line else "n/a"),
            matched=(
                line and len(line.entity_contributions) == 2)),
        AssertionResult(
            assertion_id="gcs01-a4",
            description="Both entities at FX rate 1.0 (KES)",
            expected="all rates = 1",
            observed=str([
                str(c.fx_rate_used)
                for c in line.entity_contributions])
            if line else "n/a",
            matched=(
                line and all(
                    c.fx_rate_used == Decimal("1")
                    for c in line.entity_contributions))),
    )


SCENARIO_GCS_01_AGGREGATION = Scenario(
    scenario_id="GCS-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-251: PARENT KES 5m + SUBA KES 2m on account 1000 → "
        "single consolidated line Dr 7,000,000; both entity "
        "contributions surfaced; FX rates both 1.0 (same "
        "presentation currency)."),
    setup=_setup_gcs,
    actions=_actions_gcs_aggregation,
    assertions=_assertions_gcs_aggregation,
    requires_engines=("consolidated_tb_engine",))


# GCS-02 NCI allocation for 70% owned sub
def _actions_gcs_nci(engines: EngineBundle) -> None:
    from utils.consolidated_tb_engine import (
        ConsolidatedTrialBalanceEngine, EntityProfile,
        TrialBalanceLine)
    from utils.finance_close_orchestrator import AccountType
    eng = ConsolidatedTrialBalanceEngine()
    p = EntityProfile(
        entity_id="PARENT", entity_name="P",
        parent_ownership_pct=Decimal("1"),
        functional_currency="KES", is_parent=True)
    s = EntityProfile(
        entity_id="SUBPARTIAL", entity_name="70% Sub",
        parent_ownership_pct=Decimal("0.70"),
        functional_currency="KES")
    tb = (
        TrialBalanceLine(
            entity_id="SUBPARTIAL", account_code="3000",
            account_type=AccountType.EQUITY,
            debit_kes=Decimal("0"),
            credit_kes=Decimal("10000000"),
            period="2026-04"),
    )
    engines["__gcs02__"] = eng.consolidate(
        "2026-04", (p, s), tb)


def _assertions_gcs_nci(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__gcs02__")
    if r is None:
        return (AssertionResult(
            assertion_id="gcs02-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    line = r.lines[0] if r.lines else None
    return (
        AssertionResult(
            assertion_id="gcs02-a1",
            description=(
                "NCI Cr = 30% × 10m = 3,000,000"),
            expected="3000000.00",
            observed=(
                str(line.nci_share_cr) if line else "n/a"),
            matched=(
                line and line.nci_share_cr
                == Decimal("3000000.00"))),
        AssertionResult(
            assertion_id="gcs02-a2",
            description=(
                "Parent share Cr = 70% × 10m = 7,000,000"),
            expected="7000000.00",
            observed=(
                str(line.parent_share_cr) if line else "n/a"),
            matched=(
                line and line.parent_share_cr
                == Decimal("7000000.00"))),
        AssertionResult(
            assertion_id="gcs02-a3",
            description=(
                "NCI + parent share = post-elimination total "
                "(invariant)"),
            expected="balanced",
            observed=(
                f"{line.nci_share_cr + line.parent_share_cr} vs "
                f"{line.post_elimination_cr}"
                if line else "n/a"),
            matched=(
                line and line.nci_share_cr
                + line.parent_share_cr
                == line.post_elimination_cr)),
    )


SCENARIO_GCS_02_NCI = Scenario(
    scenario_id="GCS-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-251: 70%-owned subsidiary with KES 10m equity → "
        "NCI Cr 3,000,000 (30%) + parent share Cr 7,000,000 "
        "(70%); invariant: NCI + parent = post-elimination "
        "total. IFRS 10 — control-based consolidation with "
        "minority interests separately presented."),
    setup=_setup_gcs,
    actions=_actions_gcs_nci,
    assertions=_assertions_gcs_nci,
    requires_engines=("consolidated_tb_engine",))


# GCS-03 FX translation IAS 21
def _actions_gcs_fx(engines: EngineBundle) -> None:
    from utils.consolidated_tb_engine import (
        ConsolidatedTrialBalanceEngine, EntityProfile,
        TrialBalanceLine, FxRate, FxRateType)
    from utils.finance_close_orchestrator import AccountType
    eng = ConsolidatedTrialBalanceEngine()
    p = EntityProfile(
        entity_id="PARENT", entity_name="P",
        parent_ownership_pct=Decimal("1"),
        functional_currency="KES", is_parent=True)
    f = EntityProfile(
        entity_id="USDSUB", entity_name="USD Sub",
        parent_ownership_pct=Decimal("1"),
        functional_currency="USD")
    tb = (
        TrialBalanceLine(
            entity_id="USDSUB", account_code="1000",
            account_type=AccountType.ASSET,
            debit_kes=Decimal("100000"),    # USD 100k
            credit_kes=Decimal("0"), period="2026-04"),
        TrialBalanceLine(
            entity_id="USDSUB", account_code="4000",
            account_type=AccountType.REVENUE,
            debit_kes=Decimal("0"),
            credit_kes=Decimal("50000"),   # USD 50k revenue
            period="2026-04"),
    )
    rates = (
        FxRate(currency="USD", rate_type=FxRateType.CLOSING,
               rate_to_kes=Decimal("130"), period="2026-04"),
        FxRate(currency="USD", rate_type=FxRateType.AVERAGE,
               rate_to_kes=Decimal("128"), period="2026-04"),
    )
    engines["__gcs03__"] = eng.consolidate(
        "2026-04", (p, f), tb, fx_rates=rates)


def _assertions_gcs_fx(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.consolidated_tb_engine import FxRateType
    r = engines.get("__gcs03__")
    if r is None:
        return (AssertionResult(
            assertion_id="gcs03-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    asset = next(
        (l for l in r.lines if l.account_code == "1000"), None)
    rev = next(
        (l for l in r.lines if l.account_code == "4000"), None)
    return (
        AssertionResult(
            assertion_id="gcs03-a1",
            description=(
                "Asset 100k USD × CLOSING 130 = KES 13,000,000"),
            expected="13000000.00",
            observed=(
                str(asset.pre_elimination_dr)
                if asset else "n/a"),
            matched=(
                asset and asset.pre_elimination_dr
                == Decimal("13000000.00"))),
        AssertionResult(
            assertion_id="gcs03-a2",
            description=(
                "Revenue 50k USD × AVERAGE 128 = KES 6,400,000"),
            expected="6400000.00",
            observed=(
                str(rev.pre_elimination_cr) if rev else "n/a"),
            matched=(
                rev and rev.pre_elimination_cr
                == Decimal("6400000.00"))),
        AssertionResult(
            assertion_id="gcs03-a3",
            description=(
                "Asset uses CLOSING rate type per IAS 21 B/S"),
            expected=FxRateType.CLOSING.value,
            observed=(
                asset.entity_contributions[0].fx_rate_type.value
                if asset and asset.entity_contributions
                else "n/a"),
            matched=(
                asset and asset.entity_contributions
                and asset.entity_contributions[0].fx_rate_type
                == FxRateType.CLOSING)),
        AssertionResult(
            assertion_id="gcs03-a4",
            description=(
                "Revenue uses AVERAGE rate type per IAS 21 P&L"),
            expected=FxRateType.AVERAGE.value,
            observed=(
                rev.entity_contributions[0].fx_rate_type.value
                if rev and rev.entity_contributions else "n/a"),
            matched=(
                rev and rev.entity_contributions
                and rev.entity_contributions[0].fx_rate_type
                == FxRateType.AVERAGE)),
    )


SCENARIO_GCS_03_FX = Scenario(
    scenario_id="GCS-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-251 IAS 21 FX translation: USD subsidiary B/S asset "
        "100k @ CLOSING 130 = KES 13m; P&L revenue 50k @ "
        "AVERAGE 128 = KES 6.4m. Different rate types per IAS 21 "
        "discipline (closing for B/S, average for P&L) — surfaced "
        "explicitly via fx_rate_type per Rule 1."),
    setup=_setup_gcs,
    actions=_actions_gcs_fx,
    assertions=_assertions_gcs_fx,
    requires_engines=("consolidated_tb_engine",))


# GCS-04 elimination + provenance
def _actions_gcs_elimination(engines: EngineBundle) -> None:
    from utils.consolidated_tb_engine import (
        ConsolidatedTrialBalanceEngine, EntityProfile,
        TrialBalanceLine)
    from utils.intercompany_matching import (
        EliminationRecommendation)
    from utils.finance_close_orchestrator import AccountType
    eng = ConsolidatedTrialBalanceEngine()
    p = EntityProfile(
        entity_id="PARENT", entity_name="P",
        parent_ownership_pct=Decimal("1"),
        functional_currency="KES", is_parent=True)
    s = EntityProfile(
        entity_id="SUBA", entity_name="A",
        parent_ownership_pct=Decimal("1"),
        functional_currency="KES")
    tb = (
        TrialBalanceLine(
            entity_id="PARENT", account_code="IC-REC",
            account_type=AccountType.ASSET,
            debit_kes=Decimal("500000"),
            credit_kes=Decimal("0"), period="2026-04"),
        TrialBalanceLine(
            entity_id="SUBA", account_code="IC-PAY",
            account_type=AccountType.LIABILITY,
            debit_kes=Decimal("0"),
            credit_kes=Decimal("500000"), period="2026-04"),
    )
    elim = EliminationRecommendation(
        rec_id="ELIM-1",
        elimination_type=None,
        entity_a="PARENT", entity_b="SUBA",
        reference="IC-INV-001", period="2026-04",
        debit_account="IC-PAY",
        credit_account="IC-REC",
        amount_kes=Decimal("500000"),
        description="elim IC AR/AP")
    engines["__gcs04__"] = eng.consolidate(
        "2026-04", (p, s), tb, eliminations=(elim,))


def _assertions_gcs_elimination(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__gcs04__")
    if r is None:
        return (AssertionResult(
            assertion_id="gcs04-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    rec_line = next(
        (l for l in r.lines if l.account_code == "IC-REC"), None)
    pay_line = next(
        (l for l in r.lines if l.account_code == "IC-PAY"), None)
    return (
        AssertionResult(
            assertion_id="gcs04-a1",
            description="IC-REC eliminated Cr 500k",
            expected="500000",
            observed=(
                str(rec_line.eliminations_applied_cr)
                if rec_line else "n/a"),
            matched=(
                rec_line and rec_line.eliminations_applied_cr
                == Decimal("500000"))),
        AssertionResult(
            assertion_id="gcs04-a2",
            description="IC-PAY eliminated Dr 500k",
            expected="500000",
            observed=(
                str(pay_line.eliminations_applied_dr)
                if pay_line else "n/a"),
            matched=(
                pay_line and pay_line.eliminations_applied_dr
                == Decimal("500000"))),
        AssertionResult(
            assertion_id="gcs04-a3",
            description=(
                "eliminations_applied_count = 1"),
            expected="1",
            observed=str(r.eliminations_applied_count),
            matched=r.eliminations_applied_count == 1),
        AssertionResult(
            assertion_id="gcs04-a4",
            description=(
                "Framework refs cite ENH-251 + Rule 7"),
            expected="ENH-251 + Rule 7 in refs",
            observed=" / ".join(r.framework_refs),
            matched=(
                any("ENH-251" in x for x in r.framework_refs)
                and any(
                    "Rule 7" in x for x in r.framework_refs))),
    )


SCENARIO_GCS_04_ELIMINATION = Scenario(
    scenario_id="GCS-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-251 elimination application: PARENT IC-REC Dr 500k "
        "+ SUBA IC-PAY Cr 500k + 1 EliminationRecommendation → "
        "both lines show eliminations_applied; "
        "eliminations_applied_count=1; framework refs cite "
        "ENH-251 + Rule 7 diagnostic-only stance per Rule 1."),
    setup=_setup_gcs,
    actions=_actions_gcs_elimination,
    assertions=_assertions_gcs_elimination,
    requires_engines=("consolidated_tb_engine",))


# ════════════════════════════════════════════════════════════════════════
# v10.62 — CBK Regulatory Reporting Enhanced (ENH-252)
# ════════════════════════════════════════════════════════════════════════

def _setup_cbk(engines: EngineBundle) -> None:
    pass


# CBK-01 CAR passing
def _actions_cbk_car(engines: EngineBundle) -> None:
    from utils.cbk_regulatory_reporting import (
        CBKRegulatoryReportingEngine, CapitalComponents)
    eng = CBKRegulatoryReportingEngine()
    comp = CapitalComponents(
        period="2026-04",
        tier1_capital_kes=Decimal("1500000000"),
        tier2_capital_kes=Decimal("300000000"),
        deductions_kes=Decimal("100000000"),
        risk_weighted_assets_kes=Decimal("10000000000"))
    engines["__cbk01__"] = eng.generate_car(comp)


def _assertions_cbk_car(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.cbk_regulatory_reporting import (
        BreachSeverity, CbkReturnCode)
    pkg = engines.get("__cbk01__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="cbk01-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cbk01-a1",
            description="return_code = CAR",
            expected=CbkReturnCode.CAR.value,
            observed=pkg.return_code.value,
            matched=pkg.return_code == CbkReturnCode.CAR),
        AssertionResult(
            assertion_id="cbk01-a2",
            description=(
                "CAR ratio = (1.5b+0.3b-0.1b)/10b = 0.17"),
            expected="0.17",
            observed=str(pkg.computed_metrics["car_ratio"]),
            matched=pkg.computed_metrics["car_ratio"]
            == Decimal("0.17")),
        AssertionResult(
            assertion_id="cbk01-a3",
            description=(
                "17% > 14.5% threshold → NONE breach"),
            expected=BreachSeverity.NONE.value,
            observed=pkg.breach_severity.value,
            matched=pkg.breach_severity == BreachSeverity.NONE),
        AssertionResult(
            assertion_id="cbk01-a4",
            description="Inputs surfaced for Rule 1",
            expected="all 4 inputs in inputs_used",
            observed=str(sorted(pkg.inputs_used.keys())),
            matched=(
                "tier1" in pkg.inputs_used
                and "tier2" in pkg.inputs_used
                and "deductions" in pkg.inputs_used
                and "rwa" in pkg.inputs_used)),
    )


SCENARIO_CBK_01_CAR_PASS = Scenario(
    scenario_id="CBK-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-252 CAR PG 03: Tier1 KES 1.5b + Tier2 0.3b "
        "- deductions 0.1b = total cap 1.7b; RWA 10b → "
        "CAR 17% (above 14.5% minimum) → NONE breach; "
        "all 4 inputs surfaced per Rule 1."),
    setup=_setup_cbk,
    actions=_actions_cbk_car,
    assertions=_assertions_cbk_car,
    requires_engines=("cbk_regulatory_reporting",))


# CBK-02 LIQ severe breach
def _actions_cbk_liq(engines: EngineBundle) -> None:
    from utils.cbk_regulatory_reporting import (
        CBKRegulatoryReportingEngine, LiquidityComponents)
    eng = CBKRegulatoryReportingEngine()
    comp = LiquidityComponents(
        period="2026-04",
        liquid_assets_kes=Decimal("1000000000"),
        total_deposits_kes=Decimal("10000000000"))
    engines["__cbk02__"] = eng.generate_liq(comp)


def _assertions_cbk_liq(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.cbk_regulatory_reporting import (
        BreachSeverity, CbkReturnCode)
    pkg = engines.get("__cbk02__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="cbk02-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cbk02-a1",
            description="return_code = LIQ",
            expected=CbkReturnCode.LIQ.value,
            observed=pkg.return_code.value,
            matched=pkg.return_code == CbkReturnCode.LIQ),
        AssertionResult(
            assertion_id="cbk02-a2",
            description="LIQ ratio = 0.10 (10%)",
            expected="0.10",
            observed=str(pkg.computed_metrics["liq_ratio"]),
            matched=(
                pkg.computed_metrics["liq_ratio"]
                == Decimal("0.10"))),
        AssertionResult(
            assertion_id="cbk02-a3",
            description=(
                "10% vs 20% threshold → 50% shortfall → SEVERE"),
            expected=BreachSeverity.SEVERE_BREACH.value,
            observed=pkg.breach_severity.value,
            matched=(
                pkg.breach_severity
                == BreachSeverity.SEVERE_BREACH)),
        AssertionResult(
            assertion_id="cbk02-a4",
            description=(
                "Framework refs cite CBK PG 04"),
            expected="PG 04 in refs",
            observed=" / ".join(pkg.framework_refs),
            matched=any(
                "PG 04" in r for r in pkg.framework_refs)),
    )


SCENARIO_CBK_02_LIQ_BREACH = Scenario(
    scenario_id="CBK-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-252 LIQ PG 04: liquid 1b / deposits 10b = 10% "
        "(50% shortfall vs 20% min) → SEVERE_BREACH; framework "
        "refs cite CBK PG 04 per Rule 1."),
    setup=_setup_cbk,
    actions=_actions_cbk_liq,
    assertions=_assertions_cbk_liq,
    requires_engines=("cbk_regulatory_reporting",))


# CBK-03 SBL single borrower in breach
def _actions_cbk_sbl(engines: EngineBundle) -> None:
    from utils.cbk_regulatory_reporting import (
        CBKRegulatoryReportingEngine, BorrowerExposure)
    eng = CBKRegulatoryReportingEngine()
    exposures = (
        BorrowerExposure(
            borrower_id="MEGA-CORP",
            borrower_name="Mega Corporation",
            funded_kes=Decimal("350000000"),
            unfunded_kes=Decimal("50000000")),
        BorrowerExposure(
            borrower_id="BORROWER-A",
            borrower_name="Borrower A",
            funded_kes=Decimal("100000000"),
            unfunded_kes=Decimal("0")),
    )
    engines["__cbk03__"] = eng.generate_sbl(
        "2026-04", Decimal("1000000000"), exposures)


def _assertions_cbk_sbl(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.cbk_regulatory_reporting import (
        BreachSeverity, CbkReturnCode)
    pkg = engines.get("__cbk03__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="cbk03-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cbk03-a1",
            description="return_code = SBL",
            expected=CbkReturnCode.SBL.value,
            observed=pkg.return_code.value,
            matched=pkg.return_code == CbkReturnCode.SBL),
        AssertionResult(
            assertion_id="cbk03-a2",
            description=(
                "Top borrower MEGA-CORP at 40% of core"),
            expected="0.40",
            observed=str(
                pkg.computed_metrics[
                    "top_borrower_pct_of_core"]),
            matched=(
                pkg.computed_metrics["top_borrower_pct_of_core"]
                == Decimal("0.40"))),
        AssertionResult(
            assertion_id="cbk03-a3",
            description=(
                "1 borrower in breach (40% > 25%)"),
            expected="1",
            observed=str(
                pkg.computed_metrics["borrowers_in_breach"]),
            matched=(
                pkg.computed_metrics["borrowers_in_breach"]
                == Decimal("1"))),
        AssertionResult(
            assertion_id="cbk03-a4",
            description=(
                "40% / 25% = 60% over → SEVERE"),
            expected=BreachSeverity.SEVERE_BREACH.value,
            observed=pkg.breach_severity.value,
            matched=(
                pkg.breach_severity
                == BreachSeverity.SEVERE_BREACH)),
    )


SCENARIO_CBK_03_SBL_BREACH = Scenario(
    scenario_id="CBK-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-252 SBL PG 05: MEGA-CORP funded 350m + unfunded "
        "50m = 400m vs core 1b = 40% > 25% threshold; 60% over "
        "threshold → SEVERE_BREACH; 1 borrower in breach."),
    setup=_setup_cbk,
    actions=_actions_cbk_sbl,
    assertions=_assertions_cbk_sbl,
    requires_engines=("cbk_regulatory_reporting",))


# CBK-04 FXE multi-currency
def _actions_cbk_fxe(engines: EngineBundle) -> None:
    from utils.cbk_regulatory_reporting import (
        CBKRegulatoryReportingEngine, CurrencyPosition)
    eng = CBKRegulatoryReportingEngine()
    positions = (
        CurrencyPosition(
            currency="USD",
            long_kes_equivalent=Decimal("180000000"),
            short_kes_equivalent=Decimal("20000000")),  # net 160m
        CurrencyPosition(
            currency="EUR",
            long_kes_equivalent=Decimal("50000000"),
            short_kes_equivalent=Decimal("0")),         # net 50m
        CurrencyPosition(
            currency="GBP",
            long_kes_equivalent=Decimal("30000000"),
            short_kes_equivalent=Decimal("25000000")),  # net 5m
    )
    engines["__cbk04__"] = eng.generate_fxe(
        "2026-04", Decimal("1000000000"), positions)


def _assertions_cbk_fxe(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.cbk_regulatory_reporting import (
        BreachSeverity, CbkReturnCode)
    pkg = engines.get("__cbk04__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="cbk04-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="cbk04-a1",
            description="3 currencies scanned",
            expected="3",
            observed=str(
                pkg.computed_metrics["currency_count"]),
            matched=(
                pkg.computed_metrics["currency_count"]
                == Decimal("3"))),
        AssertionResult(
            assertion_id="cbk04-a2",
            description=(
                "Worst USD net 160m / 1b = 16%"),
            expected="0.16",
            observed=str(
                pkg.computed_metrics["worst_pct_of_core"]),
            matched=(
                pkg.computed_metrics["worst_pct_of_core"]
                == Decimal("0.16"))),
        AssertionResult(
            assertion_id="cbk04-a3",
            description=(
                "2 currencies in breach (USD 16% + EUR 5%? "
                "no — 5% is < 10%, only USD breaches; "
                "expected 1)"),
            expected="1",
            observed=str(
                pkg.computed_metrics["currencies_in_breach"]),
            matched=(
                pkg.computed_metrics["currencies_in_breach"]
                == Decimal("1"))),
        AssertionResult(
            assertion_id="cbk04-a4",
            description=(
                "16% / 10% = 60% over → SEVERE"),
            expected=BreachSeverity.SEVERE_BREACH.value,
            observed=pkg.breach_severity.value,
            matched=(
                pkg.breach_severity
                == BreachSeverity.SEVERE_BREACH)),
    )


SCENARIO_CBK_04_FXE = Scenario(
    scenario_id="CBK-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-252 FXE PG 06: USD net 160m / core 1b = 16% (worst, "
        "60% over 10% threshold → SEVERE), EUR 5% within limit, "
        "GBP 0.5% within limit; 1 currency in breach; per-"
        "currency pcts surfaced in inputs_used per Rule 1."),
    setup=_setup_cbk,
    actions=_actions_cbk_fxe,
    assertions=_assertions_cbk_fxe,
    requires_engines=("cbk_regulatory_reporting",))


# ════════════════════════════════════════════════════════════════════════
# v10.63 — Predictive Financial Analytics (ENH-253)
# ════════════════════════════════════════════════════════════════════════

def _setup_pfa(engines: EngineBundle) -> None:
    pass


# PFA-01 linear trend forecast
def _actions_pfa_forecast(engines: EngineBundle) -> None:
    from utils.predictive_financial_analytics import (
        PredictiveFinancialAnalyticsEngine,
        TimeSeriesPoint, ForecastMethod)
    eng = PredictiveFinancialAnalyticsEngine()
    history = tuple(
        TimeSeriesPoint(
            period=f"2025-{m:02d}",
            value_kes=Decimal(str(1000000 + 50000 * m)))
        for m in range(1, 13))
    engines["__pfa01__"] = eng.forecast(
        "monthly_revenue", history, horizon=3,
        method=ForecastMethod.LINEAR_TREND)


def _assertions_pfa_forecast(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.predictive_financial_analytics import (
        ForecastMethod)
    f = engines.get("__pfa01__")
    if f is None:
        return (AssertionResult(
            assertion_id="pfa01-a0", description="Forecast populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="pfa01-a1",
            description="Method = LINEAR_TREND",
            expected=ForecastMethod.LINEAR_TREND.value,
            observed=f.method_used.value,
            matched=f.method_used == ForecastMethod.LINEAR_TREND),
        AssertionResult(
            assertion_id="pfa01-a2",
            description="3 forecast points produced",
            expected="3", observed=str(len(f.points)),
            matched=len(f.points) == 3),
        AssertionResult(
            assertion_id="pfa01-a3",
            description=(
                "Forecast continues upward trend (next > last)"),
            expected="forecast > last_actual",
            observed=str(f.points[0].forecast_kes),
            matched=(
                f.points[0].forecast_kes
                > Decimal("1600000"))),
        AssertionResult(
            assertion_id="pfa01-a4",
            description="ml_disabled=False (sample sufficient)",
            expected="False",
            observed=str(f.ml_disabled),
            matched=f.ml_disabled is False),
    )


SCENARIO_PFA_01_FORECAST = Scenario(
    scenario_id="PFA-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-253 LINEAR_TREND forecast: 12-month revenue "
        "history with KES 50k/month upward trend → 3-period "
        "horizon forecast continues upward (next > last "
        "actual); ml_disabled=False; sample sufficient for "
        "OLS regression."),
    setup=_setup_pfa,
    actions=_actions_pfa_forecast,
    assertions=_assertions_pfa_forecast,
    requires_engines=("predictive_financial_analytics",))


# PFA-02 variance analysis multi-direction
def _actions_pfa_variance(engines: EngineBundle) -> None:
    from utils.predictive_financial_analytics import (
        PredictiveFinancialAnalyticsEngine, ActualVsExpected)
    eng = PredictiveFinancialAnalyticsEngine()
    cmps = (
        ActualVsExpected(
            metric_name="rev", period="2026-04",
            actual_kes=Decimal("950000"),
            expected_kes=Decimal("1000000")),         # -5%
        ActualVsExpected(
            metric_name="opex", period="2026-04",
            actual_kes=Decimal("450000"),
            expected_kes=Decimal("500000"),
            higher_is_better=False),                    # 10% under = good
        ActualVsExpected(
            metric_name="provisions", period="2026-04",
            actual_kes=Decimal("300000"),
            expected_kes=Decimal("100000"),
            higher_is_better=False),                    # 200% over = HIGHLY
    )
    engines["__pfa02__"] = eng.analyze_variance(cmps)


def _assertions_pfa_variance(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.predictive_financial_analytics import (
        VarianceDirection, VarianceMateriality)
    findings = engines.get("__pfa02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="pfa02-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    by_metric = {f.metric_name: f for f in findings}
    return (
        AssertionResult(
            assertion_id="pfa02-a1",
            description="3 variance findings",
            expected="3", observed=str(len(findings)),
            matched=len(findings) == 3),
        AssertionResult(
            assertion_id="pfa02-a2",
            description=(
                "Revenue 5% short = MATERIAL UNFAVOURABLE"),
            expected="MATERIAL/UNFAVOURABLE",
            observed=(
                f"{by_metric['rev'].materiality.value}/"
                f"{by_metric['rev'].direction.value}"
                if "rev" in by_metric else "n/a"),
            matched=(
                "rev" in by_metric
                and by_metric["rev"].materiality
                == VarianceMateriality.MATERIAL
                and by_metric["rev"].direction
                == VarianceDirection.UNFAVOURABLE)),
        AssertionResult(
            assertion_id="pfa02-a3",
            description=(
                "OPEX 10% under (higher_is_better=False) = "
                "FAVOURABLE"),
            expected="FAVOURABLE",
            observed=(
                by_metric["opex"].direction.value
                if "opex" in by_metric else "n/a"),
            matched=(
                "opex" in by_metric
                and by_metric["opex"].direction
                == VarianceDirection.FAVOURABLE)),
        AssertionResult(
            assertion_id="pfa02-a4",
            description=(
                "Provisions 200% over = HIGHLY_MATERIAL"),
            expected=VarianceMateriality.HIGHLY_MATERIAL.value,
            observed=(
                by_metric["provisions"].materiality.value
                if "provisions" in by_metric else "n/a"),
            matched=(
                "provisions" in by_metric
                and by_metric["provisions"].materiality
                == VarianceMateriality.HIGHLY_MATERIAL)),
    )


SCENARIO_PFA_02_VARIANCE = Scenario(
    scenario_id="PFA-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-253 variance: revenue -5% MATERIAL UNFAVOURABLE; "
        "opex -10% with higher_is_better=False = FAVOURABLE "
        "(cost discipline); provisions +200% HIGHLY_MATERIAL "
        "(>3× materiality threshold). Direction semantics "
        "correctly inverted for cost metrics per Rule 1."),
    setup=_setup_pfa,
    actions=_actions_pfa_variance,
    assertions=_assertions_pfa_variance,
    requires_engines=("predictive_financial_analytics",))


# PFA-03 driver decomposition
def _actions_pfa_decomposition(engines: EngineBundle) -> None:
    from utils.predictive_financial_analytics import (
        PredictiveFinancialAnalyticsEngine, DriverContribution)
    eng = PredictiveFinancialAnalyticsEngine()
    drivers = (
        DriverContribution(
            driver_name="price_increase",
            base_value_kes=Decimal("100"),
            actual_value_kes=Decimal("108"),
            contribution_kes=Decimal("80000")),
        DriverContribution(
            driver_name="volume_decline",
            base_value_kes=Decimal("1000"),
            actual_value_kes=Decimal("950"),
            contribution_kes=Decimal("-40000")),
        DriverContribution(
            driver_name="mix_shift",
            base_value_kes=Decimal("0"),
            actual_value_kes=Decimal("0"),
            contribution_kes=Decimal("10000")),
    )
    engines["__pfa03__"] = eng.decompose_drivers(
        "rev", "2026-04",
        total_variance_kes=Decimal("60000"),
        drivers=drivers)


def _assertions_pfa_decomposition(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    decomp = engines.get("__pfa03__")
    if decomp is None:
        return (AssertionResult(
            assertion_id="pfa03-a0", description="Decomp populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="pfa03-a1",
            description="3 driver contributions",
            expected="3",
            observed=str(len(decomp.contributions)),
            matched=len(decomp.contributions) == 3),
        AssertionResult(
            assertion_id="pfa03-a2",
            description="Explained = 80k - 40k + 10k = 50k",
            expected="50000",
            observed=str(decomp.explained_kes),
            matched=decomp.explained_kes == Decimal("50000")),
        AssertionResult(
            assertion_id="pfa03-a3",
            description="Residual = 60k - 50k = 10k",
            expected="10000",
            observed=str(decomp.residual_kes),
            matched=decomp.residual_kes == Decimal("10000")),
        AssertionResult(
            assertion_id="pfa03-a4",
            description="Residual = 16.67% of total variance",
            expected="0.1667",
            observed=str(decomp.residual_pct_of_total),
            matched=(
                decomp.residual_pct_of_total
                == Decimal("0.1667"))),
    )


SCENARIO_PFA_03_DECOMPOSITION = Scenario(
    scenario_id="PFA-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-253 driver decomposition: total revenue variance "
        "60k = price 80k + volume -40k + mix 10k = 50k "
        "explained, 10k unexplained residual (16.67%). All "
        "drivers + residual surfaced for operator sanity-check "
        "per Rule 1."),
    setup=_setup_pfa,
    actions=_actions_pfa_decomposition,
    assertions=_assertions_pfa_decomposition,
    requires_engines=("predictive_financial_analytics",))


# PFA-04 ml_disabled fallback discipline
def _actions_pfa_ml_disabled(engines: EngineBundle) -> None:
    from utils.predictive_financial_analytics import (
        PredictiveFinancialAnalyticsEngine,
        TimeSeriesPoint, ForecastMethod)
    eng = PredictiveFinancialAnalyticsEngine()
    history = tuple(
        TimeSeriesPoint(
            period=f"2025-{m:02d}",
            value_kes=Decimal(str(1000000 + 25000 * m)))
        for m in range(1, 13))
    # Request ML_HOOK with NO predictor → must surface
    # ml_disabled=True with reason
    engines["__pfa04__"] = eng.forecast(
        "monthly_revenue", history, horizon=3,
        method=ForecastMethod.ML_HOOK, ml_predictor=None)


def _assertions_pfa_ml_disabled(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.predictive_financial_analytics import (
        ForecastMethod)
    f = engines.get("__pfa04__")
    if f is None:
        return (AssertionResult(
            assertion_id="pfa04-a0", description="Forecast populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="pfa04-a1",
            description="ml_disabled=True (Rule 6)",
            expected="True",
            observed=str(f.ml_disabled),
            matched=f.ml_disabled is True),
        AssertionResult(
            assertion_id="pfa04-a2",
            description="Reason mentions ML_HOOK + fallback",
            expected="ML_HOOK reason populated",
            observed=f.ml_disabled_reason,
            matched=(
                "ML_HOOK" in f.ml_disabled_reason
                and "LINEAR_TREND" in f.ml_disabled_reason)),
        AssertionResult(
            assertion_id="pfa04-a3",
            description=(
                "Method falls back to LINEAR_TREND (deterministic)"),
            expected=ForecastMethod.LINEAR_TREND.value,
            observed=f.method_used.value,
            matched=(
                f.method_used == ForecastMethod.LINEAR_TREND)),
        AssertionResult(
            assertion_id="pfa04-a4",
            description=(
                "Forecasts produced (engine never returns "
                "empty due to ML unavailability)"),
            expected="3 points",
            observed=str(len(f.points)),
            matched=len(f.points) == 3),
    )


SCENARIO_PFA_04_ML_DISABLED = Scenario(
    scenario_id="PFA-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-253 Rule 6 cross-check: ML_HOOK requested without "
        "ml_predictor → ml_disabled=True with reason; engine "
        "falls back to LINEAR_TREND deterministic method (NOT "
        "fabricated ML predictions); 3 forecast points still "
        "produced. Rule 6 — ml_disabled flag explicit per Rule 1."),
    setup=_setup_pfa,
    actions=_actions_pfa_ml_disabled,
    assertions=_assertions_pfa_ml_disabled,
    requires_engines=("predictive_financial_analytics",))


# ════════════════════════════════════════════════════════════════════════
# v10.64 — Finance Intelligence Dashboard CFO View (ENH-254)
# ════════════════════════════════════════════════════════════════════════

def _setup_cfo(engines: EngineBundle) -> None:
    pass


def _make_financials(period="2026-04", **overrides):
    from utils.finance_intelligence_dashboard import (
        PeriodFinancials)
    defaults = dict(
        net_interest_income_kes=Decimal("4000000000"),
        non_interest_income_kes=Decimal("1000000000"),
        operating_expenses_kes=Decimal("2500000000"),
        impairment_kes=Decimal("300000000"),
        tax_kes=Decimal("600000000"),
        avg_total_assets_kes=Decimal("100000000000"),
        avg_equity_kes=Decimal("10000000000"),  # ROE 16% > 15% min
        avg_earning_assets_kes=Decimal("80000000000"),
        closing_total_loans_kes=Decimal("60000000000"),
        closing_total_deposits_kes=Decimal("80000000000"),
        closing_npl_kes=Decimal("2400000000"),
        closing_provision_kes=Decimal("1800000000"),
        customer_count=500000,
        branch_count=50,
        transaction_count=10000000,
        transaction_processing_cost_kes=Decimal("300000000"),
        car_ratio=Decimal("0.18"),
        liq_ratio=Decimal("0.25"))
    defaults.update(overrides)
    return PeriodFinancials(period=period, **defaults)


# CFO-01 healthy bank — most KPIs OK
def _actions_cfo_healthy(engines: EngineBundle) -> None:
    from utils.finance_intelligence_dashboard import (
        FinanceIntelligenceDashboardEngine)
    eng = FinanceIntelligenceDashboardEngine()
    engines["__cfo01__"] = eng.build_dashboard(
        _make_financials())


def _assertions_cfo_healthy(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_intelligence_dashboard import (
        ThresholdStatus, MetricFamily)
    dash = engines.get("__cfo01__")
    if dash is None:
        return (AssertionResult(
            assertion_id="cfo01-a0", description="Dashboard populated",
            expected="present", observed="MISSING", matched=False),)
    breach_count = sum(
        1 for k in dash.kpis
        if k.threshold_status == ThresholdStatus.BREACH)
    families_present = {k.family for k in dash.kpis}
    return (
        AssertionResult(
            assertion_id="cfo01-a1",
            description=(
                "5+ KPIs in 5 families (no growth without prior)"),
            expected="≥ 5 KPIs",
            observed=str(len(dash.kpis)),
            matched=len(dash.kpis) >= 5),
        AssertionResult(
            assertion_id="cfo01-a2",
            description=(
                "PROFITABILITY + CAPITAL + LIQUIDITY + "
                "EFFICIENCY + ASSET_QUALITY families present"),
            expected="5 families",
            observed=str([f.value for f in families_present]),
            matched=(
                MetricFamily.PROFITABILITY in families_present
                and MetricFamily.CAPITAL in families_present
                and MetricFamily.LIQUIDITY in families_present
                and MetricFamily.EFFICIENCY in families_present
                and MetricFamily.ASSET_QUALITY
                in families_present)),
        AssertionResult(
            assertion_id="cfo01-a3",
            description="No breaches in healthy state",
            expected="0",
            observed=str(breach_count),
            matched=breach_count == 0),
        AssertionResult(
            assertion_id="cfo01-a4",
            description="No alerts when no breaches",
            expected="0 alerts",
            observed=str(len(dash.alerts)),
            matched=len(dash.alerts) == 0),
    )


SCENARIO_CFO_01_HEALTHY = Scenario(
    scenario_id="CFO-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-254 healthy state: 5 KPI families populated "
        "(profitability + capital + liquidity + efficiency + "
        "asset quality; growth needs prior period); no "
        "thresholds breached → no executive alerts fired. "
        "Engine reports the steady state cleanly per Rule 1."),
    setup=_setup_cfo,
    actions=_actions_cfo_healthy,
    assertions=_assertions_cfo_healthy,
    requires_engines=("finance_intelligence_dashboard",))


# CFO-02 capital breach → CRITICAL alert
def _actions_cfo_capital_breach(engines: EngineBundle) -> None:
    from utils.finance_intelligence_dashboard import (
        FinanceIntelligenceDashboardEngine)
    eng = FinanceIntelligenceDashboardEngine()
    engines["__cfo02__"] = eng.build_dashboard(
        _make_financials(car_ratio=Decimal("0.10")))


def _assertions_cfo_capital_breach(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_intelligence_dashboard import (
        ThresholdStatus, AlertSeverity, MetricFamily)
    dash = engines.get("__cfo02__")
    if dash is None:
        return (AssertionResult(
            assertion_id="cfo02-a0", description="Dashboard populated",
            expected="present", observed="MISSING", matched=False),)
    car_kpi = next(
        (k for k in dash.kpis if k.metric_name == "CAR"), None)
    car_alert = next(
        (a for a in dash.alerts if a.kpi_metric == "CAR"), None)
    return (
        AssertionResult(
            assertion_id="cfo02-a1",
            description="CAR threshold_status = BREACH",
            expected=ThresholdStatus.BREACH.value,
            observed=(
                car_kpi.threshold_status.value
                if car_kpi else "n/a"),
            matched=(
                car_kpi
                and car_kpi.threshold_status
                == ThresholdStatus.BREACH)),
        AssertionResult(
            assertion_id="cfo02-a2",
            description="CRITICAL alert fired for CAR breach",
            expected=AlertSeverity.CRITICAL.value,
            observed=(
                car_alert.severity.value
                if car_alert else "MISSING"),
            matched=(
                car_alert
                and car_alert.severity
                == AlertSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="cfo02-a3",
            description="Alert family = CAPITAL",
            expected=MetricFamily.CAPITAL.value,
            observed=(
                car_alert.family.value
                if car_alert else "n/a"),
            matched=(
                car_alert
                and car_alert.family == MetricFamily.CAPITAL)),
        AssertionResult(
            assertion_id="cfo02-a4",
            description=(
                "Action category mentions capital plan / RWA"),
            expected="capital plan / RWA in action category",
            observed=(
                car_alert.recommended_action_category
                if car_alert else "n/a"),
            matched=(
                car_alert
                and "capital"
                in car_alert.recommended_action_category)),
    )


SCENARIO_CFO_02_CAPITAL_BREACH = Scenario(
    scenario_id="CFO-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-254 capital breach: CAR 10% < 14.5% threshold → "
        "BREACH status + CRITICAL alert (regulatory-grade "
        "severity). Action category surfaces 'review capital "
        "plan / RWA optimisation' — engine recommends category, "
        "not specific action per Rule 7."),
    setup=_setup_cfo,
    actions=_actions_cfo_capital_breach,
    assertions=_assertions_cfo_capital_breach,
    requires_engines=("finance_intelligence_dashboard",))


# CFO-03 NPL breach → asset quality WARNING
def _actions_cfo_npl_breach(engines: EngineBundle) -> None:
    from utils.finance_intelligence_dashboard import (
        FinanceIntelligenceDashboardEngine)
    eng = FinanceIntelligenceDashboardEngine()
    engines["__cfo03__"] = eng.build_dashboard(
        _make_financials(
            closing_npl_kes=Decimal("5000000000")))   # 8.3%


def _assertions_cfo_npl_breach(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_intelligence_dashboard import (
        ThresholdStatus, AlertSeverity, MetricFamily)
    dash = engines.get("__cfo03__")
    if dash is None:
        return (AssertionResult(
            assertion_id="cfo03-a0", description="Dashboard populated",
            expected="present", observed="MISSING", matched=False),)
    npl_kpi = next(
        (k for k in dash.kpis if k.metric_name == "NPL_RATIO"),
        None)
    npl_alert = next(
        (a for a in dash.alerts if a.kpi_metric == "NPL_RATIO"),
        None)
    return (
        AssertionResult(
            assertion_id="cfo03-a1",
            description="NPL_RATIO BREACH (8.3% > 6%)",
            expected=ThresholdStatus.BREACH.value,
            observed=(
                npl_kpi.threshold_status.value
                if npl_kpi else "n/a"),
            matched=(
                npl_kpi
                and npl_kpi.threshold_status
                == ThresholdStatus.BREACH)),
        AssertionResult(
            assertion_id="cfo03-a2",
            description=(
                "Asset quality breach = WARNING (not CRITICAL "
                "— credit issue, not regulatory-grade)"),
            expected=AlertSeverity.WARNING.value,
            observed=(
                npl_alert.severity.value
                if npl_alert else "MISSING"),
            matched=(
                npl_alert
                and npl_alert.severity
                == AlertSeverity.WARNING)),
        AssertionResult(
            assertion_id="cfo03-a3",
            description="Family = ASSET_QUALITY",
            expected=MetricFamily.ASSET_QUALITY.value,
            observed=(
                npl_alert.family.value
                if npl_alert else "n/a"),
            matched=(
                npl_alert
                and npl_alert.family
                == MetricFamily.ASSET_QUALITY)),
        AssertionResult(
            assertion_id="cfo03-a4",
            description="Inputs surfaced for Rule 1",
            expected="npl + loans in inputs_used",
            observed=str(
                sorted(npl_kpi.inputs_used.keys())
                if npl_kpi else "n/a"),
            matched=(
                npl_kpi
                and "npl" in npl_kpi.inputs_used
                and "loans" in npl_kpi.inputs_used)),
    )


SCENARIO_CFO_03_NPL_BREACH = Scenario(
    scenario_id="CFO-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-254 asset quality: NPL 5b / loans 60b = 8.3% > 6% "
        "threshold → BREACH; alert is WARNING severity (not "
        "CRITICAL — credit/collections issue, not regulatory-"
        "grade); inputs_used surfaces npl + loans for Rule 1 "
        "drill-down."),
    setup=_setup_cfo,
    actions=_actions_cfo_npl_breach,
    assertions=_assertions_cfo_npl_breach,
    requires_engines=("finance_intelligence_dashboard",))


# CFO-04 with prior — growth + trend
def _actions_cfo_with_prior(engines: EngineBundle) -> None:
    from utils.finance_intelligence_dashboard import (
        FinanceIntelligenceDashboardEngine)
    eng = FinanceIntelligenceDashboardEngine()
    prior = _make_financials(
        period="2026-03",
        net_interest_income_kes=Decimal("3500000000"),
        closing_total_loans_kes=Decimal("55000000000"),
        closing_total_deposits_kes=Decimal("75000000000"),
        customer_count=480000)
    current = _make_financials()
    engines["__cfo04__"] = eng.build_dashboard(
        current, prior=prior)


def _assertions_cfo_with_prior(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_intelligence_dashboard import (
        TrendDirection, MetricFamily)
    dash = engines.get("__cfo04__")
    if dash is None:
        return (AssertionResult(
            assertion_id="cfo04-a0", description="Dashboard populated",
            expected="present", observed="MISSING", matched=False),)
    growth_kpis = [
        k for k in dash.kpis
        if k.family == MetricFamily.GROWTH]
    nim = next(
        (k for k in dash.kpis if k.metric_name == "NIM"), None)
    return (
        AssertionResult(
            assertion_id="cfo04-a1",
            description=(
                "Growth KPIs produced (loan + deposit + "
                "customer)"),
            expected="3 growth KPIs",
            observed=str(len(growth_kpis)),
            matched=len(growth_kpis) == 3),
        AssertionResult(
            assertion_id="cfo04-a2",
            description="NIM trend = UP (improved vs prior)",
            expected=TrendDirection.UP.value,
            observed=(
                nim.trend.value if nim else "n/a"),
            matched=(
                nim and nim.trend == TrendDirection.UP)),
        AssertionResult(
            assertion_id="cfo04-a3",
            description=(
                "NIM prior_value populated for context"),
            expected="prior_value not None",
            observed=(
                str(nim.prior_value)
                if nim and nim.prior_value else "None"),
            matched=(
                nim and nim.prior_value is not None)),
        AssertionResult(
            assertion_id="cfo04-a4",
            description=(
                "Loan growth = (60b - 55b) / 55b ≈ 9.09%"),
            expected="0.0909",
            observed=str(next(
                k.value for k in growth_kpis
                if k.metric_name == "LOAN_GROWTH")) if any(
                k.metric_name == "LOAN_GROWTH"
                for k in growth_kpis) else "n/a",
            matched=any(
                k.metric_name == "LOAN_GROWTH"
                and k.value == Decimal("0.0909")
                for k in growth_kpis)),
    )


SCENARIO_CFO_04_WITH_PRIOR = Scenario(
    scenario_id="CFO-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-254 with prior period supplied: 3 growth KPIs "
        "produced (loan + deposit + customer); NIM trend UP "
        "(NII rose from 3.5b to 4b); prior_value surfaced for "
        "context; loan growth 9.09% computed correctly."),
    setup=_setup_cfo,
    actions=_actions_cfo_with_prior,
    assertions=_assertions_cfo_with_prior,
    requires_engines=("finance_intelligence_dashboard",))


# ════════════════════════════════════════════════════════════════════════
# v10.65 — Financial Statement Generator (ENH-255)
# ════════════════════════════════════════════════════════════════════════

def _setup_fsg(engines: EngineBundle) -> None:
    pass


def _make_fsg_tb(lines, period="2026-04",
                 pres_curr="KES", cta=Decimal("0")):
    from utils.consolidated_tb_engine import (
        ConsolidatedTrialBalance)
    total_dr = sum(
        (l.post_elimination_dr for l in lines), Decimal("0"))
    total_cr = sum(
        (l.post_elimination_cr for l in lines), Decimal("0"))
    return ConsolidatedTrialBalance(
        period=period, presentation_currency=pres_curr,
        lines=tuple(lines), findings=(),
        entities_consolidated=1, eliminations_applied_count=0,
        total_dr=total_dr, total_cr=total_cr,
        cumulative_translation_adjustment_kes=cta,
        framework_refs=("ENH-251",))


def _make_fsg_line(code, atype, dr=Decimal("0"),
                   cr=Decimal("0"),
                   parent_dr=None, parent_cr=None,
                   nci_dr=Decimal("0"), nci_cr=Decimal("0")):
    from utils.consolidated_tb_engine import ConsolidatedLine
    if parent_dr is None:
        parent_dr = dr - nci_dr
    if parent_cr is None:
        parent_cr = cr - nci_cr
    return ConsolidatedLine(
        account_code=code, account_type=atype,
        entity_contributions=(),
        pre_elimination_dr=dr, pre_elimination_cr=cr,
        eliminations_applied_dr=Decimal("0"),
        eliminations_applied_cr=Decimal("0"),
        post_elimination_dr=dr, post_elimination_cr=cr,
        nci_share_dr=nci_dr, nci_share_cr=nci_cr,
        parent_share_dr=parent_dr, parent_share_cr=parent_cr,
        framework_refs=("ENH-251",))


# FSG-01 simple balanced BS
def _actions_fsg_balance_sheet(engines: EngineBundle) -> None:
    from utils.financial_statement_generator import (
        FinancialStatementGenerator,
        AccountClassification, BsClassification)
    from utils.finance_close_orchestrator import AccountType
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_fsg_line(
            "1010", AccountType.ASSET,
            dr=Decimal("5000000")),
        _make_fsg_line(
            "1500", AccountType.ASSET,
            dr=Decimal("15000000")),
        _make_fsg_line(
            "2010", AccountType.LIABILITY,
            cr=Decimal("3000000")),
        _make_fsg_line(
            "2500", AccountType.LIABILITY,
            cr=Decimal("8000000")),
        _make_fsg_line(
            "3000", AccountType.EQUITY,
            cr=Decimal("9000000")),
    ]
    tb = _make_fsg_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="1010",
            bs_classification=BsClassification.CURRENT_ASSET,
            line_label="Cash"),
        AccountClassification(
            account_code="1500",
            bs_classification=(
                BsClassification.NON_CURRENT_ASSET),
            line_label="PPE"),
        AccountClassification(
            account_code="2010",
            bs_classification=(
                BsClassification.CURRENT_LIABILITY),
            line_label="Trade Payables"),
        AccountClassification(
            account_code="2500",
            bs_classification=(
                BsClassification.NON_CURRENT_LIABILITY),
            line_label="Long-term Debt"),
        AccountClassification(
            account_code="3000",
            bs_classification=BsClassification.EQUITY_PARENT,
            line_label="Share Capital"),
    )
    engines["__fsg01__"] = eng.generate_package(tb, cls)


def _assertions_fsg_balance_sheet(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    pkg = engines.get("__fsg01__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="fsg01-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    bs = pkg.balance_sheet
    return (
        AssertionResult(
            assertion_id="fsg01-a1",
            description="Total assets = 20m",
            expected="20000000",
            observed=str(bs.total_assets_kes),
            matched=bs.total_assets_kes == Decimal("20000000")),
        AssertionResult(
            assertion_id="fsg01-a2",
            description="Total liabilities = 11m",
            expected="11000000",
            observed=str(bs.total_liabilities_kes),
            matched=(
                bs.total_liabilities_kes
                == Decimal("11000000"))),
        AssertionResult(
            assertion_id="fsg01-a3",
            description="Total equity = 9m",
            expected="9000000",
            observed=str(bs.total_equity_kes),
            matched=bs.total_equity_kes == Decimal("9000000")),
        AssertionResult(
            assertion_id="fsg01-a4",
            description=(
                "Balanced: assets = liabilities + equity"),
            expected="balanced",
            observed=(
                f"{bs.total_assets_kes} vs "
                f"{bs.total_liabilities_kes + bs.total_equity_kes}"),
            matched=(
                bs.total_assets_kes
                == bs.total_liabilities_kes
                + bs.total_equity_kes)),
    )


SCENARIO_FSG_01_BALANCE_SHEET = Scenario(
    scenario_id="FSG-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-255: 5 classified accounts (cash + PPE + payables + "
        "long-term debt + equity) → BS with split current/non-"
        "current; assets 20m = liab 11m + equity 9m balanced; "
        "credit-natured lines flipped to positive presentation."),
    setup=_setup_fsg,
    actions=_actions_fsg_balance_sheet,
    assertions=_assertions_fsg_balance_sheet,
    requires_engines=("financial_statement_generator",))


# FSG-02 income statement
def _actions_fsg_income(engines: EngineBundle) -> None:
    from utils.financial_statement_generator import (
        FinancialStatementGenerator, AccountClassification)
    from utils.finance_close_orchestrator import AccountType
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_fsg_line(
            "4010", AccountType.REVENUE,
            cr=Decimal("8000000")),
        _make_fsg_line(
            "4020", AccountType.REVENUE,
            cr=Decimal("2000000")),
        _make_fsg_line(
            "5010", AccountType.EXPENSE,
            dr=Decimal("4500000")),
        _make_fsg_line(
            "5020", AccountType.EXPENSE,
            dr=Decimal("2000000")),
    ]
    tb = _make_fsg_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="4010", is_revenue=True,
            line_label="Net Interest Income"),
        AccountClassification(
            account_code="4020", is_revenue=True,
            line_label="Fee Income"),
        AccountClassification(
            account_code="5010", is_expense=True,
            line_label="Operating Expenses"),
        AccountClassification(
            account_code="5020", is_expense=True,
            line_label="Impairment Charge"),
    )
    engines["__fsg02__"] = eng.generate_package(tb, cls)


def _assertions_fsg_income(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    pkg = engines.get("__fsg02__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="fsg02-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    is_stmt = pkg.income_statement
    return (
        AssertionResult(
            assertion_id="fsg02-a1",
            description="Total revenue = 10m",
            expected="10000000",
            observed=str(is_stmt.total_revenue_kes),
            matched=(
                is_stmt.total_revenue_kes
                == Decimal("10000000"))),
        AssertionResult(
            assertion_id="fsg02-a2",
            description="Total expenses = 6.5m",
            expected="6500000",
            observed=str(is_stmt.total_expenses_kes),
            matched=(
                is_stmt.total_expenses_kes
                == Decimal("6500000"))),
        AssertionResult(
            assertion_id="fsg02-a3",
            description="PBT = 3.5m",
            expected="3500000",
            observed=str(is_stmt.profit_before_tax_kes),
            matched=(
                is_stmt.profit_before_tax_kes
                == Decimal("3500000"))),
        AssertionResult(
            assertion_id="fsg02-a4",
            description="2 revenue lines + 2 expense lines",
            expected="2+2",
            observed=(
                f"{len(is_stmt.revenue_lines)}+"
                f"{len(is_stmt.expense_lines)}"),
            matched=(
                len(is_stmt.revenue_lines) == 2
                and len(is_stmt.expense_lines) == 2)),
    )


SCENARIO_FSG_02_INCOME = Scenario(
    scenario_id="FSG-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-255: 2 revenue lines (NII + fees, total 10m) + "
        "2 expense lines (opex + impairment, total 6.5m) → "
        "PBT 3.5m; revenue lines flipped from credit-natured "
        "to positive presentation."),
    setup=_setup_fsg,
    actions=_actions_fsg_income,
    assertions=_assertions_fsg_income,
    requires_engines=("financial_statement_generator",))


# FSG-03 OCI with CTA from consolidation
def _actions_fsg_oci(engines: EngineBundle) -> None:
    from utils.financial_statement_generator import (
        FinancialStatementGenerator,
        AccountClassification, OciClassification)
    from utils.finance_close_orchestrator import AccountType
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_fsg_line(
            "OCI-REVAL", AccountType.EQUITY,
            cr=Decimal("500000")),
        _make_fsg_line(
            "OCI-CFH", AccountType.EQUITY,
            cr=Decimal("200000")),
    ]
    # CTA 250k from ENH-251 consolidation
    tb = _make_fsg_tb(tb_lines, cta=Decimal("250000"))
    cls = (
        AccountClassification(
            account_code="OCI-REVAL", is_oci=True,
            oci_classification=(
                OciClassification.NEVER_RECYCLED),
            line_label="Property Revaluation"),
        AccountClassification(
            account_code="OCI-CFH", is_oci=True,
            oci_classification=(
                OciClassification.RECYCLABLE_TO_PNL),
            line_label="CF Hedge Reserve"),
    )
    engines["__fsg03__"] = eng.generate_package(tb, cls)


def _assertions_fsg_oci(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    pkg = engines.get("__fsg03__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="fsg03-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    oci = pkg.oci_statement
    return (
        AssertionResult(
            assertion_id="fsg03-a1",
            description="1 NEVER_RECYCLED line",
            expected="1",
            observed=str(len(oci.never_recycled_lines)),
            matched=len(oci.never_recycled_lines) == 1),
        AssertionResult(
            assertion_id="fsg03-a2",
            description="1 RECYCLABLE line",
            expected="1",
            observed=str(len(oci.recyclable_lines)),
            matched=len(oci.recyclable_lines) == 1),
        AssertionResult(
            assertion_id="fsg03-a3",
            description=(
                "CTA 250k from ENH-251 consumed"),
            expected="250000",
            observed=str(
                oci.cumulative_translation_adjustment_kes),
            matched=(
                oci.cumulative_translation_adjustment_kes
                == Decimal("250000"))),
        AssertionResult(
            assertion_id="fsg03-a4",
            description=(
                "Total OCI = 500k + 200k + 250k CTA = 950k"),
            expected="950000",
            observed=str(oci.total_oci_kes),
            matched=oci.total_oci_kes == Decimal("950000")),
    )


SCENARIO_FSG_03_OCI = Scenario(
    scenario_id="FSG-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-255 IAS 1 §82A: revaluation 500k (NEVER_RECYCLED) "
        "+ CF hedge 200k (RECYCLABLE) + CTA 250k from ENH-251 → "
        "total OCI 950k. CTA correctly flows from consolidation "
        "to OCI cumulative translation reserve per IAS 21."),
    setup=_setup_fsg,
    actions=_actions_fsg_oci,
    assertions=_assertions_fsg_oci,
    requires_engines=("financial_statement_generator",))


# FSG-04 full package with cash flow
def _actions_fsg_full(engines: EngineBundle) -> None:
    from utils.financial_statement_generator import (
        FinancialStatementGenerator,
        AccountClassification, BsClassification,
        CashFlowInput, CashFlowSection, EquityMovement)
    from utils.finance_close_orchestrator import AccountType
    eng = FinancialStatementGenerator()
    tb_lines = [
        _make_fsg_line(
            "1010", AccountType.ASSET,
            dr=Decimal("1000000")),
        _make_fsg_line(
            "3000", AccountType.EQUITY,
            cr=Decimal("1000000")),
    ]
    tb = _make_fsg_tb(tb_lines)
    cls = (
        AccountClassification(
            account_code="1010",
            bs_classification=BsClassification.CURRENT_ASSET,
            line_label="Cash"),
        AccountClassification(
            account_code="3000",
            bs_classification=BsClassification.EQUITY_PARENT,
            line_label="Share Capital"),
    )
    cf = (
        CashFlowInput(
            section=CashFlowSection.OPERATING,
            description="PBT", amount_kes=Decimal("500000")),
        CashFlowInput(
            section=CashFlowSection.INVESTING,
            description="PPE additions",
            amount_kes=Decimal("-200000")),
        CashFlowInput(
            section=CashFlowSection.FINANCING,
            description="Dividends",
            amount_kes=Decimal("-100000")),
    )
    eq = (
        EquityMovement(
            component="Retained Earnings",
            description="Profit",
            amount_kes=Decimal("400000")),
    )
    engines["__fsg04__"] = eng.generate_package(
        tb, cls,
        cash_flow_inputs=cf, equity_movements=eq,
        opening_cash_balance_kes=Decimal("800000"))


def _assertions_fsg_full(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    pkg = engines.get("__fsg04__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="fsg04-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fsg04-a1",
            description="Cash flow statement produced",
            expected="non-None",
            observed=str(
                pkg.cash_flow_statement is not None),
            matched=pkg.cash_flow_statement is not None),
        AssertionResult(
            assertion_id="fsg04-a2",
            description=(
                "CF closing = 800k + 500k - 200k - 100k = 1m"),
            expected="1000000",
            observed=(
                str(pkg.cash_flow_statement.closing_cash_kes)
                if pkg.cash_flow_statement else "n/a"),
            matched=(
                pkg.cash_flow_statement is not None
                and pkg.cash_flow_statement.closing_cash_kes
                == Decimal("1000000"))),
        AssertionResult(
            assertion_id="fsg04-a3",
            description="Equity changes produced",
            expected="non-None",
            observed=str(pkg.equity_changes is not None),
            matched=pkg.equity_changes is not None),
        AssertionResult(
            assertion_id="fsg04-a4",
            description=(
                "Framework refs cite ENH-255 + Rule 7"),
            expected="ENH-255 + Rule 7 in refs",
            observed=" / ".join(pkg.framework_refs),
            matched=(
                any(
                    "ENH-255" in r
                    for r in pkg.framework_refs)
                and any(
                    "Rule 7" in r
                    for r in pkg.framework_refs))),
    )


SCENARIO_FSG_04_FULL_PACKAGE = Scenario(
    scenario_id="FSG-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-255 full package: minimal BS + caller-supplied CF "
        "inputs (operating PBT 500k, investing -200k, financing "
        "-100k, opening 800k) → CF closing 1m; equity movement "
        "produced; framework refs cite ENH-255 + Rule 7 "
        "diagnostic-only stance per Rule 1."),
    setup=_setup_fsg,
    actions=_actions_fsg_full,
    assertions=_assertions_fsg_full,
    requires_engines=("financial_statement_generator",))


# ════════════════════════════════════════════════════════════════════════
# v10.66 — KRA Tax Compliance (ENH-256)
# ════════════════════════════════════════════════════════════════════════

def _setup_tax(engines: EngineBundle) -> None:
    pass


# TAX-01 corporation tax computation
def _actions_tax_corp(engines: EngineBundle) -> None:
    from utils.kra_tax_compliance import (
        KRATaxComplianceEngine, CorpTaxInput, CorpTaxRegime)
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026",
        accounting_profit_kes=Decimal("100000000"),
        permanent_addbacks_kes=Decimal("5000000"),
        permanent_deductions_kes=Decimal("2000000"),
        timing_differences_net_kes=Decimal("3000000"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    engines["__tax01__"] = eng.compute_corp_tax(ci)


def _assertions_tax_corp(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.kra_tax_compliance import TaxType
    c = engines.get("__tax01__")
    if c is None:
        return (AssertionResult(
            assertion_id="tax01-a0", description="Comp populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="tax01-a1",
            description="tax_type = CORPORATION_TAX",
            expected=TaxType.CORPORATION_TAX.value,
            observed=c.tax_type.value,
            matched=c.tax_type == TaxType.CORPORATION_TAX),
        AssertionResult(
            assertion_id="tax01-a2",
            description=(
                "Taxable basis = 100m + 5m - 2m - 3m = 100m"),
            expected="100000000",
            observed=str(c.taxable_basis_kes),
            matched=c.taxable_basis_kes == Decimal("100000000")),
        AssertionResult(
            assertion_id="tax01-a3",
            description="Rate 30% (STANDARD_RESIDENT)",
            expected="0.30",
            observed=str(c.rate_applied),
            matched=c.rate_applied == Decimal("0.30")),
        AssertionResult(
            assertion_id="tax01-a4",
            description=(
                "Tax = 100m × 30% = 30m"),
            expected="30000000.00",
            observed=str(c.computed_tax_kes),
            matched=(
                c.computed_tax_kes == Decimal("30000000.00"))),
    )


SCENARIO_TAX_01_CORP = Scenario(
    scenario_id="TAX-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-256 corporation tax: accounting profit 100m + "
        "addbacks 5m - exempt income 2m - timing diff 3m = "
        "taxable 100m × 30% (STANDARD_RESIDENT regime) = "
        "tax 30m. All inputs surfaced for Rule 1 audit trail."),
    setup=_setup_tax,
    actions=_actions_tax_corp,
    assertions=_assertions_tax_corp,
    requires_engines=("kra_tax_compliance",))


# TAX-02 VAT multi-status
def _actions_tax_vat(engines: EngineBundle) -> None:
    from utils.kra_tax_compliance import (
        KRATaxComplianceEngine, VatTransaction, VatStatus)
    eng = KRATaxComplianceEngine()
    txns = (
        VatTransaction(
            transaction_id="v1", period="2026-04",
            base_amount_kes=Decimal("5000000"),
            status=VatStatus.STANDARD),
        VatTransaction(
            transaction_id="v2", period="2026-04",
            base_amount_kes=Decimal("3000000"),
            status=VatStatus.STANDARD),
        VatTransaction(
            transaction_id="v3", period="2026-04",
            base_amount_kes=Decimal("1000000"),
            status=VatStatus.ZERO_RATED),
        VatTransaction(
            transaction_id="v4", period="2026-04",
            base_amount_kes=Decimal("500000"),
            status=VatStatus.EXEMPT),
    )
    engines["__tax02__"] = eng.compute_vat(txns)


def _assertions_tax_vat(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    comps = engines.get("__tax02__")
    if comps is None:
        return (AssertionResult(
            assertion_id="tax02-a0", description="Comps populated",
            expected="present", observed="MISSING", matched=False),)
    std = next(
        (c for c in comps
         if c.applicable_rule.endswith("16%")), None)
    return (
        AssertionResult(
            assertion_id="tax02-a1",
            description="3 buckets (standard/zero/exempt)",
            expected="3", observed=str(len(comps)),
            matched=len(comps) == 3),
        AssertionResult(
            assertion_id="tax02-a2",
            description="Standard base 8m × 16% = 1.28m",
            expected="1280000.00",
            observed=(
                str(std.computed_tax_kes) if std else "n/a"),
            matched=(
                std and std.computed_tax_kes
                == Decimal("1280000.00"))),
        AssertionResult(
            assertion_id="tax02-a3",
            description="Zero-rated and exempt both produce 0",
            expected="2 zero-tax buckets",
            observed=str(sum(
                1 for c in comps
                if c.computed_tax_kes == Decimal("0.00"))),
            matched=sum(
                1 for c in comps
                if c.computed_tax_kes == Decimal("0.00")) == 2),
        AssertionResult(
            assertion_id="tax02-a4",
            description=(
                "Standard rule string includes 'standard 16%'"),
            expected="'standard 16%' in rule",
            observed=(
                std.applicable_rule if std else "n/a"),
            matched=(
                std and "standard 16%" in std.applicable_rule)),
    )


SCENARIO_TAX_02_VAT = Scenario(
    scenario_id="TAX-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-256 VAT 3-status: 8m STANDARD × 16% = 1.28m; "
        "1m ZERO_RATED → 0; 500k EXEMPT → 0. 3 buckets "
        "produced. Distinct rules per status preserved for "
        "Rule 1 transparency."),
    setup=_setup_tax,
    actions=_actions_tax_vat,
    assertions=_assertions_tax_vat,
    requires_engines=("kra_tax_compliance",))


# TAX-03 WHT residency-driven rate selection
def _actions_tax_wht(engines: EngineBundle) -> None:
    from utils.kra_tax_compliance import (
        KRATaxComplianceEngine, WhtPayment,
        WhtIncomeType, ResidencyStatus)
    eng = KRATaxComplianceEngine()
    payments = (
        WhtPayment(
            payment_id="w1", period="2026-04",
            income_type=WhtIncomeType.DIVIDEND,
            gross_amount_kes=Decimal("1000000"),
            payee_residency=ResidencyStatus.RESIDENT),
        WhtPayment(
            payment_id="w2", period="2026-04",
            income_type=WhtIncomeType.ROYALTY,
            gross_amount_kes=Decimal("500000"),
            payee_residency=ResidencyStatus.NON_RESIDENT),
        WhtPayment(
            payment_id="w3", period="2026-04",
            income_type=WhtIncomeType.RENT,
            gross_amount_kes=Decimal("200000"),
            payee_residency=ResidencyStatus.NON_RESIDENT),
    )
    engines["__tax03__"] = eng.compute_wht(payments)


def _assertions_tax_wht(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    comps = engines.get("__tax03__")
    if comps is None:
        return (AssertionResult(
            assertion_id="tax03-a0", description="Comps populated",
            expected="present", observed="MISSING", matched=False),)
    by_id = {c.computation_id: c for c in comps}
    return (
        AssertionResult(
            assertion_id="tax03-a1",
            description=(
                "Resident dividend 5%: 1m × 5% = 50k"),
            expected="50000.00",
            observed=str(by_id["TAX-WHT-w1"].computed_tax_kes),
            matched=(
                by_id["TAX-WHT-w1"].computed_tax_kes
                == Decimal("50000.00"))),
        AssertionResult(
            assertion_id="tax03-a2",
            description=(
                "Non-resident royalty 20%: 500k × 20% = 100k"),
            expected="100000.00",
            observed=str(by_id["TAX-WHT-w2"].computed_tax_kes),
            matched=(
                by_id["TAX-WHT-w2"].computed_tax_kes
                == Decimal("100000.00"))),
        AssertionResult(
            assertion_id="tax03-a3",
            description=(
                "Non-resident rent 30%: 200k × 30% = 60k"),
            expected="60000.00",
            observed=str(by_id["TAX-WHT-w3"].computed_tax_kes),
            matched=(
                by_id["TAX-WHT-w3"].computed_tax_kes
                == Decimal("60000.00"))),
        AssertionResult(
            assertion_id="tax03-a4",
            description=(
                "All 3 surface income_type + residency in "
                "inputs_used"),
            expected="3 with both fields",
            observed=str(sum(
                1 for c in comps
                if "income_type" in c.inputs_used
                and "residency" in c.inputs_used)),
            matched=sum(
                1 for c in comps
                if "income_type" in c.inputs_used
                and "residency" in c.inputs_used) == 3),
    )


SCENARIO_TAX_03_WHT = Scenario(
    scenario_id="TAX-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-256 WHT residency-driven rates: resident dividend "
        "5% (50k on 1m); non-resident royalty 20% (100k on "
        "500k); non-resident rent 30% (60k on 200k). All 3 "
        "income_type + residency surfaced in inputs_used per "
        "Rule 1 audit trail."),
    setup=_setup_tax,
    actions=_actions_tax_wht,
    assertions=_assertions_tax_wht,
    requires_engines=("kra_tax_compliance",))


# TAX-04 deferred tax + return package orchestrator
def _actions_tax_deferred_pkg(engines: EngineBundle) -> None:
    from utils.kra_tax_compliance import (
        KRATaxComplianceEngine, CorpTaxInput, CorpTaxRegime,
        TemporaryDifference, TemporaryDifferenceType,
        ExciseTransaction)
    eng = KRATaxComplianceEngine()
    ci = CorpTaxInput(
        period="2026",
        accounting_profit_kes=Decimal("50000000"),
        permanent_addbacks_kes=Decimal("0"),
        permanent_deductions_kes=Decimal("0"),
        timing_differences_net_kes=Decimal("0"),
        regime=CorpTaxRegime.STANDARD_RESIDENT)
    excise = (
        ExciseTransaction(
            transaction_id="ex1", period="2026-04",
            fee_amount_kes=Decimal("1000000")),
    )
    diffs = (
        TemporaryDifference(
            description="Accelerated tax depreciation",
            period="2026-04",
            amount_kes=Decimal("5000000"),
            diff_type=TemporaryDifferenceType.TAXABLE),
        TemporaryDifference(
            description="Provisions deductible only when paid",
            period="2026-04",
            amount_kes=Decimal("2000000"),
            diff_type=TemporaryDifferenceType.DEDUCTIBLE),
    )
    engines["__tax04__"] = eng.build_return_package(
        "2026-04", corp_tax_input=ci,
        excise_transactions=excise,
        temp_differences=diffs)


def _assertions_tax_deferred_pkg(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.kra_tax_compliance import TaxType
    pkg = engines.get("__tax04__")
    if pkg is None:
        return (AssertionResult(
            assertion_id="tax04-a0", description="Pkg populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="tax04-a1",
            description="Corp tax 50m × 30% = 15m",
            expected="15000000.00",
            observed=str(
                pkg.by_tax_type[TaxType.CORPORATION_TAX.value]),
            matched=(
                pkg.by_tax_type[
                    TaxType.CORPORATION_TAX.value]
                == Decimal("15000000.00"))),
        AssertionResult(
            assertion_id="tax04-a2",
            description=(
                "Excise 1m × 20% = 200k"),
            expected="200000.00",
            observed=str(
                pkg.by_tax_type[TaxType.EXCISE_DUTY.value]),
            matched=(
                pkg.by_tax_type[TaxType.EXCISE_DUTY.value]
                == Decimal("200000.00"))),
        AssertionResult(
            assertion_id="tax04-a3",
            description=(
                "Deferred tax populated; net DTL = "
                "(5m × 30%) - (2m × 30%) = 1.5m - 600k = 900k"),
            expected="900000.00",
            observed=(
                str(pkg.deferred_tax.net_dt_kes)
                if pkg.deferred_tax else "n/a"),
            matched=(
                pkg.deferred_tax
                and pkg.deferred_tax.net_dt_kes
                == Decimal("900000.00"))),
        AssertionResult(
            assertion_id="tax04-a4",
            description=(
                "Framework refs cite ENH-256 + Rule 7"),
            expected="ENH-256 + Rule 7 in refs",
            observed=" / ".join(pkg.framework_refs),
            matched=(
                any("ENH-256" in r for r in pkg.framework_refs)
                and any(
                    "Rule 7" in r for r in pkg.framework_refs))),
    )


SCENARIO_TAX_04_DEFERRED_PKG = Scenario(
    scenario_id="TAX-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-256 build_return_package: corp tax 15m + excise "
        "200k + deferred tax (DTL 1.5m on accel dep, DTA 600k "
        "on provisions, net 900k DTL per IAS 12). All "
        "computations + by_tax_type aggregates + framework "
        "refs cite ENH-256 + Rule 7 diagnostic-only stance."),
    setup=_setup_tax,
    actions=_actions_tax_deferred_pkg,
    assertions=_assertions_tax_deferred_pkg,
    requires_engines=("kra_tax_compliance",))


# ════════════════════════════════════════════════════════════════════════
# v10.67 — Multi-Entity & Multi-Currency Accounting (ENH-257)
# ════════════════════════════════════════════════════════════════════════

def _setup_mec(engines: EngineBundle) -> None:
    pass


# MEC-01 USD journal validation + KES translation
def _actions_mec_journal(engines: EngineBundle) -> None:
    from utils.multi_entity_currency import (
        MultiEntityCurrencyEngine, JournalLine, FxSpotRate)
    eng = MultiEntityCurrencyEngine()
    lines = (
        JournalLine(
            line_id="l1", entity_id="P",
            account_code="1500",
            debit_txn_currency=Decimal("10000"),
            credit_txn_currency=Decimal("0"),
            transaction_currency="USD"),
        JournalLine(
            line_id="l2", entity_id="P",
            account_code="2500",
            debit_txn_currency=Decimal("0"),
            credit_txn_currency=Decimal("10000"),
            transaction_currency="USD"),
    )
    rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"), rate_date="2026-04-15"),
    )
    engines["__mec01__"] = (
        eng.validate_multi_currency_journal(
            "J-USD-001", lines, "2026-04-15", rates=rates))


def _assertions_mec_journal(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    v = engines.get("__mec01__")
    if v is None:
        return (AssertionResult(
            assertion_id="mec01-a0", description="Validation populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="mec01-a1",
            description="Journal valid (no issues)",
            expected="True",
            observed=str(v.is_valid),
            matched=v.is_valid is True),
        AssertionResult(
            assertion_id="mec01-a2",
            description=(
                "USD txn currency surfaced"),
            expected="USD",
            observed=v.transaction_currency,
            matched=v.transaction_currency == "USD"),
        AssertionResult(
            assertion_id="mec01-a3",
            description=(
                "Functional Dr = 10k × 130 = 1.3m KES"),
            expected="1300000.00",
            observed=str(v.functional_dr),
            matched=v.functional_dr == Decimal("1300000.00")),
        AssertionResult(
            assertion_id="mec01-a4",
            description="FX rate 130 surfaced for Rule 1",
            expected="130",
            observed=str(v.fx_rate_used),
            matched=v.fx_rate_used == Decimal("130")),
    )


SCENARIO_MEC_01_JOURNAL = Scenario(
    scenario_id="MEC-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-257: balanced 2-line USD journal (Dr 10k Cr 10k) "
        "+ caller-supplied USD→KES spot 130 → valid; functional "
        "Dr/Cr 1.3m KES; FX rate surfaced for Rule 1 "
        "transparency."),
    setup=_setup_mec,
    actions=_actions_mec_journal,
    assertions=_assertions_mec_journal,
    requires_engines=("multi_entity_currency",))


# MEC-02 mixed currency journal flagged
def _actions_mec_mixed(engines: EngineBundle) -> None:
    from utils.multi_entity_currency import (
        MultiEntityCurrencyEngine, JournalLine)
    eng = MultiEntityCurrencyEngine()
    lines = (
        JournalLine(
            line_id="l1", entity_id="P",
            account_code="1500",
            debit_txn_currency=Decimal("100"),
            credit_txn_currency=Decimal("0"),
            transaction_currency="USD"),
        JournalLine(
            line_id="l2", entity_id="P",
            account_code="2500",
            debit_txn_currency=Decimal("0"),
            credit_txn_currency=Decimal("100"),
            transaction_currency="EUR"),
    )
    engines["__mec02__"] = (
        eng.validate_multi_currency_journal(
            "J-MIX", lines, "2026-04-15", rates=()))


def _assertions_mec_mixed(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.multi_entity_currency import JournalIssue
    v = engines.get("__mec02__")
    if v is None:
        return (AssertionResult(
            assertion_id="mec02-a0", description="Validation populated",
            expected="present", observed="MISSING", matched=False),)
    issue_kinds = {i[0] for i in v.issues}
    return (
        AssertionResult(
            assertion_id="mec02-a1",
            description="Journal invalid",
            expected="False",
            observed=str(v.is_valid),
            matched=v.is_valid is False),
        AssertionResult(
            assertion_id="mec02-a2",
            description="MIXED_CURRENCY_LINES issue raised",
            expected=JournalIssue.MIXED_CURRENCY_LINES.value,
            observed=str([i.value for i in issue_kinds]),
            matched=(
                JournalIssue.MIXED_CURRENCY_LINES
                in issue_kinds)),
        AssertionResult(
            assertion_id="mec02-a3",
            description=(
                "Issue description suggests split per currency"),
            expected="'split into per-currency' in description",
            observed=" / ".join(i[1] for i in v.issues),
            matched=any(
                "split" in i[1] for i in v.issues)),
    )


SCENARIO_MEC_02_MIXED = Scenario(
    scenario_id="MEC-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-257: 2-line journal mixing USD + EUR → invalid; "
        "MIXED_CURRENCY_LINES issue raised; description "
        "suggests splitting into per-currency journals per "
        "IAS 21 one-journal-one-currency rule."),
    setup=_setup_mec,
    actions=_actions_mec_mixed,
    assertions=_assertions_mec_mixed,
    requires_engines=("multi_entity_currency",))


# MEC-03 IAS 21 §23 monetary item revaluation
def _actions_mec_revaluation(engines: EngineBundle) -> None:
    from utils.multi_entity_currency import (
        MultiEntityCurrencyEngine, MonetaryBalance, FxSpotRate)
    eng = MultiEntityCurrencyEngine()
    balances = (
        MonetaryBalance(
            balance_id="B-USD-RCV-001",
            entity_id="PARENT",
            account_code="1500",
            currency="USD",
            txn_currency_balance=Decimal("100000"),
            historical_functional_balance=(
                Decimal("12500000"))),  # at 125
        MonetaryBalance(
            balance_id="B-EUR-PAY-001",
            entity_id="PARENT",
            account_code="2500",
            currency="EUR",
            txn_currency_balance=Decimal("-50000"),  # liab
            historical_functional_balance=(
                Decimal("-6800000"))),  # at 136
    )
    closing_rates = (
        FxSpotRate(
            transaction_currency="USD",
            functional_currency="KES",
            rate=Decimal("130"),
            rate_date="2026-04-30"),
        FxSpotRate(
            transaction_currency="EUR",
            functional_currency="KES",
            rate=Decimal("140"),
            rate_date="2026-04-30"),
    )
    engines["__mec03__"] = eng.revalue_monetary_balances(
        "2026-04-30", balances, closing_rates)


def _assertions_mec_revaluation(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.multi_entity_currency import RevalSeverity
    findings = engines.get("__mec03__")
    if findings is None:
        return (AssertionResult(
            assertion_id="mec03-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    by_id = {f.balance_id: f for f in findings}
    usd = by_id.get("B-USD-RCV-001")
    eur = by_id.get("B-EUR-PAY-001")
    return (
        AssertionResult(
            assertion_id="mec03-a1",
            description=(
                "USD asset gain: 100k × 130 = 13m vs hist "
                "12.5m → +500k gain"),
            expected="500000.00",
            observed=(
                str(usd.fx_gain_loss_kes) if usd else "n/a"),
            matched=(
                usd and usd.fx_gain_loss_kes
                == Decimal("500000.00"))),
        AssertionResult(
            assertion_id="mec03-a2",
            description=(
                "EUR liability loss: -50k × 140 = -7m vs "
                "hist -6.8m → -200k loss"),
            expected="-200000.00",
            observed=(
                str(eur.fx_gain_loss_kes) if eur else "n/a"),
            matched=(
                eur and eur.fx_gain_loss_kes
                == Decimal("-200000.00"))),
        AssertionResult(
            assertion_id="mec03-a3",
            description=(
                "USD severity = MEDIUM (4% relative)"),
            expected=RevalSeverity.MEDIUM.value,
            observed=(
                usd.severity.value if usd else "n/a"),
            matched=(
                usd and usd.severity == RevalSeverity.MEDIUM)),
        AssertionResult(
            assertion_id="mec03-a4",
            description=(
                "Framework refs cite IAS 21 §23 + Rule 7"),
            expected="IAS 21 §23 + Rule 7 in refs",
            observed=(
                " / ".join(usd.framework_refs)
                if usd else "n/a"),
            matched=(
                usd and any("IAS 21" in r for r in usd.framework_refs)
                and any("Rule 7" in r for r in usd.framework_refs))),
    )


SCENARIO_MEC_03_REVALUATION = Scenario(
    scenario_id="MEC-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-257 IAS 21 §23 period-end revaluation: USD "
        "receivable 100k (hist 12.5m at 125, closing 130 → "
        "13m, gain 500k = 4% MEDIUM); EUR payable -50k (hist "
        "-6.8m at 136, closing 140 → -7m, loss -200k). "
        "Framework refs cite IAS 21 + Rule 7 — caller posts "
        "the revaluation journal, engine never auto-posts."),
    setup=_setup_mec,
    actions=_actions_mec_revaluation,
    assertions=_assertions_mec_revaluation,
    requires_engines=("multi_entity_currency",))


# MEC-04 inter-entity transfer recommendation
def _actions_mec_transfer(engines: EngineBundle) -> None:
    from utils.multi_entity_currency import (
        MultiEntityCurrencyEngine,
        InterEntityTransferRequest)
    eng = MultiEntityCurrencyEngine()
    req = InterEntityTransferRequest(
        request_id="REQ-Q2-2026-001",
        from_entity="PARENT",
        to_entity="SUBA",
        amount_kes=Decimal("10000000"),
        purpose="working_capital_loan")
    engines["__mec04__"] = (
        eng.recommend_inter_entity_transfer(req))


def _assertions_mec_transfer(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    rec = engines.get("__mec04__")
    if rec is None:
        return (AssertionResult(
            assertion_id="mec04-a0", description="Rec populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="mec04-a1",
            description="Mirror legs: Dr at PARENT, Cr at SUBA",
            expected="PARENT/SUBA",
            observed=(
                f"{rec.debit_leg_entity}/"
                f"{rec.credit_leg_entity}"),
            matched=(
                rec.debit_leg_entity == "PARENT"
                and rec.credit_leg_entity == "SUBA")),
        AssertionResult(
            assertion_id="mec04-a2",
            description="Amount 10m KES preserved",
            expected="10000000",
            observed=str(rec.amount_kes),
            matched=rec.amount_kes == Decimal("10000000")),
        AssertionResult(
            assertion_id="mec04-a3",
            description="IC-RCV / IC-PAY accounts assigned",
            expected="IC-RCV / IC-PAY",
            observed=(
                f"{rec.debit_leg_account} / "
                f"{rec.credit_leg_account}"),
            matched=(
                "IC-RCV" in rec.debit_leg_account
                and "IC-PAY" in rec.credit_leg_account)),
        AssertionResult(
            assertion_id="mec04-a4",
            description=(
                "Description states operator approval required"),
            expected="'approval required' in description",
            observed=rec.description,
            matched=(
                "approval required" in rec.description)),
    )


SCENARIO_MEC_04_TRANSFER = Scenario(
    scenario_id="MEC-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-257 inter-entity transfer: PARENT → SUBA 10m KES "
        "for working capital loan → mirror legs (Dr IC-RCV at "
        "PARENT, Cr IC-PAY at SUBA); description states "
        "operator approval required before posting per Rule 7."),
    setup=_setup_mec,
    actions=_actions_mec_transfer,
    assertions=_assertions_mec_transfer,
    requires_engines=("multi_entity_currency",))


# ════════════════════════════════════════════════════════════════════════
# v10.68 — Finance Audit & Compliance (ENH-258)
# ════════════════════════════════════════════════════════════════════════

def _setup_fac(engines: EngineBundle) -> None:
    pass


# FAC-01 SoD breach (full)
def _actions_fac_sod(engines: EngineBundle) -> None:
    from utils.finance_audit_compliance import (
        FinanceAuditComplianceEngine, JournalAudit,
        JournalSource)
    eng = FinanceAuditComplianceEngine()
    journals = (
        JournalAudit(
            journal_id="J-CLEAN-001",
            period="2026-04",
            posting_date="2026-04-15",
            amount_kes=Decimal("50000"),
            source=JournalSource.AUTOMATED,
            preparer_user_id="alice",
            reviewer_user_id="bob",
            poster_user_id="carol"),
        JournalAudit(
            journal_id="J-SOD-002",
            period="2026-04",
            posting_date="2026-04-20",
            amount_kes=Decimal("100000"),
            source=JournalSource.MANUAL,
            preparer_user_id="rogue",
            reviewer_user_id="rogue",
            poster_user_id="rogue"),
    )
    engines["__fac01__"] = (
        eng.check_segregation_of_duties(journals))


def _assertions_fac_sod(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_audit_compliance import (
        FindingSeverity, ControlId)
    findings = engines.get("__fac01__")
    if findings is None:
        return (AssertionResult(
            assertion_id="fac01-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fac01-a1",
            description=(
                "Only the SoD-breach journal flagged "
                "(clean journal passes)"),
            expected="1",
            observed=str(len(findings)),
            matched=len(findings) == 1),
        AssertionResult(
            assertion_id="fac01-a2",
            description="CRITICAL severity (full SoD breach)",
            expected=FindingSeverity.CRITICAL.value,
            observed=(
                findings[0].severity.value
                if findings else "n/a"),
            matched=(
                findings
                and findings[0].severity
                == FindingSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="fac01-a3",
            description="control = SEGREGATION_OF_DUTIES",
            expected=ControlId.SEGREGATION_OF_DUTIES.value,
            observed=(
                findings[0].control.value
                if findings else "n/a"),
            matched=(
                findings
                and findings[0].control
                == ControlId.SEGREGATION_OF_DUTIES)),
        AssertionResult(
            assertion_id="fac01-a4",
            description=(
                "Actor 'rogue' surfaced for triage"),
            expected="rogue in actors",
            observed=(
                str(findings[0].actors)
                if findings else "n/a"),
            matched=(
                findings and "rogue" in findings[0].actors)),
    )


SCENARIO_FAC_01_SOD = Scenario(
    scenario_id="FAC-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-258 SoD: clean journal (alice/bob/carol) passes; "
        "SoD-breach journal (rogue/rogue/rogue) flagged "
        "CRITICAL (full breach); only 1 finding produced; "
        "actor surfaced for triage per Rule 1."),
    setup=_setup_fac,
    actions=_actions_fac_sod,
    assertions=_assertions_fac_sod,
    requires_engines=("finance_audit_compliance",))


# FAC-02 authorization limit breach
def _actions_fac_auth(engines: EngineBundle) -> None:
    from utils.finance_audit_compliance import (
        FinanceAuditComplianceEngine, JournalAudit,
        JournalSource, UserAuthorization)
    eng = FinanceAuditComplianceEngine()
    journals = (
        JournalAudit(
            journal_id="J-BIG",
            period="2026-04",
            posting_date="2026-04-15",
            amount_kes=Decimal("5000000"),  # 5m
            source=JournalSource.MANUAL,
            preparer_user_id="alice",
            reviewer_user_id="bob",
            poster_user_id="carol"),
    )
    auths = (
        UserAuthorization(
            user_id="carol",
            max_journal_kes=Decimal("1000000"),  # 1m limit
            role="POSTER"),
    )
    engines["__fac02__"] = eng.check_authorization_limit(
        journals, auths)


def _assertions_fac_auth(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_audit_compliance import FindingSeverity
    findings = engines.get("__fac02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="fac02-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fac02-a1",
            description="Authorization breach finding",
            expected="1",
            observed=str(len(findings)),
            matched=len(findings) == 1),
        AssertionResult(
            assertion_id="fac02-a2",
            description=(
                "Severity CRITICAL (5× over limit, ≥2× → "
                "CRITICAL)"),
            expected=FindingSeverity.CRITICAL.value,
            observed=(
                findings[0].severity.value
                if findings else "n/a"),
            matched=(
                findings
                and findings[0].severity
                == FindingSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="fac02-a3",
            description="Amount preserved in finding",
            expected="5000000",
            observed=(
                str(findings[0].amount_kes)
                if findings else "n/a"),
            matched=(
                findings
                and findings[0].amount_kes
                == Decimal("5000000"))),
        AssertionResult(
            assertion_id="fac02-a4",
            description=(
                "Carol (poster) surfaced as actor"),
            expected="carol in actors",
            observed=(
                str(findings[0].actors)
                if findings else "n/a"),
            matched=(
                findings and "carol" in findings[0].actors)),
    )


SCENARIO_FAC_02_AUTH = Scenario(
    scenario_id="FAC-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-258 authorization limit: Carol authorized 1m KES, "
        "posts 5m KES journal → CRITICAL severity (5× over "
        "limit, ratio ≥2×). Amount + actor preserved in "
        "finding for SOX evidence."),
    setup=_setup_fac,
    actions=_actions_fac_auth,
    assertions=_assertions_fac_auth,
    requires_engines=("finance_audit_compliance",))


# FAC-03 attestation states
def _actions_fac_attestation(engines: EngineBundle) -> None:
    from utils.finance_audit_compliance import (
        FinanceAuditComplianceEngine, PeriodAttestation,
        AttestationStatus)
    eng = FinanceAuditComplianceEngine()
    attestations = (
        PeriodAttestation(
            attestation_id="GL-2026-04",
            period="2026-04", function="GL_CLOSE",
            deadline_date="2026-05-05",
            status=AttestationStatus.ATTESTED,
            attestor_user_id="cfo",
            attested_at="2026-05-04"),
        PeriodAttestation(
            attestation_id="TAX-2026-04",
            period="2026-04", function="TAX_FILING",
            deadline_date="2026-05-20",
            status=AttestationStatus.OVERDUE,
            attestor_user_id="tax_head",
            attested_at=None),
        PeriodAttestation(
            attestation_id="TR-2026-04",
            period="2026-04", function="TREASURY_CLOSE",
            deadline_date="2026-05-05",
            status=AttestationStatus.REJECTED,
            attestor_user_id="treasurer",
            attested_at=None,
            notes="liquidity reconciliation incomplete"),
    )
    engines["__fac03__"] = (
        eng.check_period_close_attestation(attestations))


def _assertions_fac_attestation(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_audit_compliance import FindingSeverity
    findings = engines.get("__fac03__")
    if findings is None:
        return (AssertionResult(
            assertion_id="fac03-a0", description="Findings populated",
            expected="present", observed="MISSING", matched=False),)
    by_id = {f.attestation_ids[0]: f for f in findings if f.attestation_ids}
    return (
        AssertionResult(
            assertion_id="fac03-a1",
            description=(
                "ATTESTED produces no finding (only OVERDUE "
                "+ REJECTED)"),
            expected="2",
            observed=str(len(findings)),
            matched=len(findings) == 2),
        AssertionResult(
            assertion_id="fac03-a2",
            description="OVERDUE = HIGH severity",
            expected=FindingSeverity.HIGH.value,
            observed=(
                by_id["TAX-2026-04"].severity.value
                if "TAX-2026-04" in by_id else "n/a"),
            matched=(
                "TAX-2026-04" in by_id
                and by_id["TAX-2026-04"].severity
                == FindingSeverity.HIGH)),
        AssertionResult(
            assertion_id="fac03-a3",
            description="REJECTED = CRITICAL severity",
            expected=FindingSeverity.CRITICAL.value,
            observed=(
                by_id["TR-2026-04"].severity.value
                if "TR-2026-04" in by_id else "n/a"),
            matched=(
                "TR-2026-04" in by_id
                and by_id["TR-2026-04"].severity
                == FindingSeverity.CRITICAL)),
    )


SCENARIO_FAC_03_ATTESTATION = Scenario(
    scenario_id="FAC-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-258 attestations: GL_CLOSE ATTESTED → no finding; "
        "TAX_FILING OVERDUE → HIGH severity; TREASURY_CLOSE "
        "REJECTED → CRITICAL severity. SOX 302 period-end "
        "certification discipline."),
    setup=_setup_fac,
    actions=_actions_fac_attestation,
    assertions=_assertions_fac_attestation,
    requires_engines=("finance_audit_compliance",))


# FAC-04 build_compliance_report orchestrator
def _actions_fac_orchestrator(engines: EngineBundle) -> None:
    from utils.finance_audit_compliance import (
        FinanceAuditComplianceEngine, JournalAudit,
        JournalSource, UserAuthorization,
        PeriodAttestation, AttestationStatus)
    eng = FinanceAuditComplianceEngine()
    journals = (
        # SoD breach
        JournalAudit(
            journal_id="J-SOD",
            period="2026-04",
            posting_date="2026-04-20",
            amount_kes=Decimal("200000"),
            source=JournalSource.MANUAL,
            preparer_user_id="rogue",
            reviewer_user_id="rogue",
            poster_user_id="rogue"),
        # Late adjustment
        JournalAudit(
            journal_id="J-LATE",
            period="2026-04",
            posting_date="2026-05-15",   # post-cutoff
            amount_kes=Decimal("3000000"),
            source=JournalSource.MANUAL,
            preparer_user_id="alice",
            reviewer_user_id="bob",
            poster_user_id="carol"),
    )
    auths = (
        UserAuthorization(
            user_id="rogue",
            max_journal_kes=Decimal("500000"),
            role="POSTER"),
        UserAuthorization(
            user_id="carol",
            max_journal_kes=Decimal("10000000"),
            role="POSTER"),
    )
    attestations = (
        PeriodAttestation(
            attestation_id="GL-2026-04",
            period="2026-04",
            function="GL_CLOSE",
            deadline_date="2026-05-05",
            status=AttestationStatus.OVERDUE,
            attestor_user_id="cfo",
            attested_at=None),
    )
    engines["__fac04__"] = eng.build_compliance_report(
        "2026-04",
        journals=journals,
        authorizations=auths,
        attestations=attestations,
        period_cutoff_date="2026-05-05",
        materiality_kes=Decimal("100000"))


def _assertions_fac_orchestrator(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.finance_audit_compliance import (
        ControlId, FindingSeverity)
    report = engines.get("__fac04__")
    if report is None:
        return (AssertionResult(
            assertion_id="fac04-a0", description="Report populated",
            expected="present", observed="MISSING", matched=False),)
    return (
        AssertionResult(
            assertion_id="fac04-a1",
            description="Multiple controls fired",
            expected=(
                "≥3 controls (SoD + manual + late + "
                "attestation)"),
            observed=str(
                sum(1 for c, n in report.by_control.items()
                    if n > 0)),
            matched=sum(
                1 for c, n in report.by_control.items()
                if n > 0) >= 3),
        AssertionResult(
            assertion_id="fac04-a2",
            description="2 journals scanned + 1 attestation",
            expected="2/1",
            observed=(
                f"{report.journals_scanned}/"
                f"{report.attestations_scanned}"),
            matched=(
                report.journals_scanned == 2
                and report.attestations_scanned == 1)),
        AssertionResult(
            assertion_id="fac04-a3",
            description=(
                "≥1 CRITICAL finding (full SoD breach)"),
            expected=(
                "≥1 CRITICAL"),
            observed=str(
                report.by_severity[
                    FindingSeverity.CRITICAL.value]),
            matched=(
                report.by_severity[
                    FindingSeverity.CRITICAL.value] >= 1)),
        AssertionResult(
            assertion_id="fac04-a4",
            description=(
                "Framework refs cite ENH-258 + Rule 7"),
            expected="ENH-258 + Rule 7 in refs",
            observed=" / ".join(report.framework_refs),
            matched=(
                any("ENH-258" in r for r in report.framework_refs)
                and any(
                    "Rule 7" in r
                    for r in report.framework_refs))),
    )


SCENARIO_FAC_04_ORCHESTRATOR = Scenario(
    scenario_id="FAC-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-258 build_compliance_report: 2 journals (SoD-"
        "breach manual + late adjustment) + 1 OVERDUE "
        "attestation → multiple controls fired (SoD + "
        "authorization + manual + late + attestation); ≥1 "
        "CRITICAL finding from full SoD breach; framework "
        "refs cite ENH-258 + Rule 7 diagnostic-only stance."),
    setup=_setup_fac,
    actions=_actions_fac_orchestrator,
    assertions=_assertions_fac_orchestrator,
    requires_engines=("finance_audit_compliance",))


# ════════════════════════════════════════════════════════════════════════
# v10.70 — Trade Finance Core Instruments (ENH-269)
# ════════════════════════════════════════════════════════════════════════

def _setup_tfi(engines: EngineBundle) -> None:
    pass


# TFI-01 LC issuance validation — clean path
def _actions_tfi_lc_clean(engines: EngineBundle) -> None:
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeFinanceInstrumentsEngine, TradeInstrument,
        InstrumentType, InstrumentState, LcType)
    eng = TradeFinanceInstrumentsEngine()
    inst = TradeInstrument(
        instrument_id="LC-2026-001",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.DRAFT,
        applicant="Acme Imports Ltd",
        beneficiary="Shanghai Steel Co",
        issuing_bank="Ecobank Kenya",
        advising_bank="Bank of China Shanghai",
        amount_kes=Decimal("50000000"),
        currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 7, 1),
        tenor_days=0,
        lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="500MT cold-rolled steel coils")
    engines["__tfi01__"] = eng.validate_issuance(inst)


def _assertions_tfi_lc_clean(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_instruments import (
        ValidationOutcome, InstrumentType)
    v = engines.get("__tfi01__")
    if v is None:
        return (AssertionResult(
            assertion_id="tfi01-a0",
            description="Validation populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfi01-a1",
            description="Outcome VALID",
            expected=ValidationOutcome.VALID.value,
            observed=v.outcome.value,
            matched=v.outcome == ValidationOutcome.VALID),
        AssertionResult(
            assertion_id="tfi01-a2",
            description="Type LC",
            expected=InstrumentType.LC.value,
            observed=v.instrument_type.value,
            matched=v.instrument_type == InstrumentType.LC),
        AssertionResult(
            assertion_id="tfi01-a3",
            description="UCP 600 cited in framework refs",
            expected="UCP 600 in refs",
            observed=" / ".join(v.framework_refs),
            matched=any(
                "UCP 600" in r for r in v.framework_refs)),
        AssertionResult(
            assertion_id="tfi01-a4",
            description="ENH-269 cited per Rule 1",
            expected="ENH-269 in refs",
            observed=" / ".join(v.framework_refs),
            matched=any(
                "ENH-269" in r for r in v.framework_refs)),
    )


SCENARIO_TFI_01_LC_CLEAN = Scenario(
    scenario_id="TFI-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-269: clean SIGHT LC issuance (Acme→Shanghai "
        "Steel, 50m KES, 90d tenor, advising bank present, "
        "incoterms CIF Mombasa, description populated) → "
        "VALID outcome; UCP 600 + ENH-269 cited in framework "
        "refs per Rule 1."),
    setup=_setup_tfi,
    actions=_actions_tfi_lc_clean,
    assertions=_assertions_tfi_lc_clean,
    requires_engines=("trade_finance_instruments",))


# TFI-02 LC issuance — multiple violations
def _actions_tfi_lc_invalid(engines: EngineBundle) -> None:
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeFinanceInstrumentsEngine, TradeInstrument,
        InstrumentType, InstrumentState, LcType)
    eng = TradeFinanceInstrumentsEngine()
    inst = TradeInstrument(
        instrument_id="LC-BAD-001",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.DRAFT,
        applicant="Acme",
        beneficiary="Beta",
        issuing_bank="Ecobank",
        advising_bank=None,    # missing → warning
        amount_kes=Decimal("1000000"),
        currency="KES",
        issue_date=_d(2026, 1, 1),
        expiry_date=_d(2027, 6, 1),   # > 365d → INVALID
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="",       # missing → INVALID
        description_of_goods="")   # missing → INVALID
    engines["__tfi02__"] = eng.validate_issuance(inst)


def _assertions_tfi_lc_invalid(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_instruments import (
        ValidationOutcome)
    v = engines.get("__tfi02__")
    if v is None:
        return (AssertionResult(
            assertion_id="tfi02-a0",
            description="Validation populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfi02-a1",
            description=(
                "Outcome INVALID (hard rules dominate over "
                "warnings)"),
            expected=ValidationOutcome.INVALID.value,
            observed=v.outcome.value,
            matched=v.outcome == ValidationOutcome.INVALID),
        AssertionResult(
            assertion_id="tfi02-a2",
            description="Tenor breach reason raised",
            expected="365d in reason",
            observed=" / ".join(v.reasons),
            matched=any(
                "365d" in r for r in v.reasons)),
        AssertionResult(
            assertion_id="tfi02-a3",
            description="Missing incoterms reason raised",
            expected="incoterms in reason",
            observed=" / ".join(v.reasons),
            matched=any(
                "incoterms" in r for r in v.reasons)),
        AssertionResult(
            assertion_id="tfi02-a4",
            description="Missing goods reason raised",
            expected="description_of_goods in reason",
            observed=" / ".join(v.reasons),
            matched=any(
                "description_of_goods" in r
                for r in v.reasons)),
    )


SCENARIO_TFI_02_LC_INVALID = Scenario(
    scenario_id="TFI-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-269: LC with multiple violations (517d tenor > "
        "365d hard max + missing incoterms + missing "
        "description of goods) → INVALID outcome; all 3 hard "
        "violations surfaced as separate reasons per Rule 1; "
        "advising bank warning subordinate to hard violations."),
    setup=_setup_tfi,
    actions=_actions_tfi_lc_invalid,
    assertions=_assertions_tfi_lc_invalid,
    requires_engines=("trade_finance_instruments",))


# TFI-03 amendment requires beneficiary consent (UCP 600 §10)
def _actions_tfi_amendment(engines: EngineBundle) -> None:
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeFinanceInstrumentsEngine, TradeInstrument,
        AmendmentRequest, InstrumentType, InstrumentState,
        LcType)
    eng = TradeFinanceInstrumentsEngine()
    inst = TradeInstrument(
        instrument_id="LC-2026-100",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.ACTIVE,
        applicant="Acme Imports Ltd",
        beneficiary="Shanghai Steel Co",
        issuing_bank="Ecobank Kenya",
        advising_bank="Bank of China Shanghai",
        amount_kes=Decimal("10000000"),
        currency="KES",
        issue_date=_d(2026, 1, 1),
        expiry_date=_d(2026, 6, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="500MT steel")
    # Amendment without beneficiary consent
    amd_no_consent = AmendmentRequest(
        amendment_id="A-2026-100-1",
        instrument_id="LC-2026-100",
        amendment_date=_d(2026, 4, 1),
        new_amount_kes=Decimal("12000000"),  # 20% uplift
        new_expiry_date=None, new_description=None,
        beneficiary_consent=False,
        reason="customer requested amount uplift")
    # Amendment with beneficiary consent
    amd_with_consent = AmendmentRequest(
        amendment_id="A-2026-100-2",
        instrument_id="LC-2026-100",
        amendment_date=_d(2026, 4, 5),
        new_amount_kes=Decimal("12000000"),
        new_expiry_date=None, new_description=None,
        beneficiary_consent=True,
        reason="customer requested amount uplift")
    engines["__tfi03_no_consent__"] = (
        eng.validate_amendment(inst, amd_no_consent))
    engines["__tfi03_with_consent__"] = (
        eng.validate_amendment(inst, amd_with_consent))


def _assertions_tfi_amendment(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_instruments import (
        ValidationOutcome)
    no_c = engines.get("__tfi03_no_consent__")
    with_c = engines.get("__tfi03_with_consent__")
    if no_c is None or with_c is None:
        return (AssertionResult(
            assertion_id="tfi03-a0",
            description="Validations populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfi03-a1",
            description=(
                "Without consent → INVALID per UCP 600 §10"),
            expected=ValidationOutcome.INVALID.value,
            observed=no_c.outcome.value,
            matched=no_c.outcome == ValidationOutcome.INVALID),
        AssertionResult(
            assertion_id="tfi03-a2",
            description=(
                "Beneficiary consent flagged as required for LC"),
            expected="True",
            observed=str(no_c.requires_beneficiary_consent),
            matched=(
                no_c.requires_beneficiary_consent is True)),
        AssertionResult(
            assertion_id="tfi03-a3",
            description=(
                "With consent → VALID (20% uplift below 25% "
                "warning threshold)"),
            expected=ValidationOutcome.VALID.value,
            observed=with_c.outcome.value,
            matched=with_c.outcome == ValidationOutcome.VALID),
        AssertionResult(
            assertion_id="tfi03-a4",
            description=(
                "UCP 600 §10 cited in reasons for "
                "no-consent rejection"),
            expected="UCP 600 §10 in reason",
            observed=" / ".join(no_c.reasons),
            matched=any(
                "UCP 600 §10" in r for r in no_c.reasons)),
    )


SCENARIO_TFI_03_AMENDMENT = Scenario(
    scenario_id="TFI-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-269 LC amendment: 20% amount uplift on ACTIVE "
        "LC. Without beneficiary consent → INVALID per UCP "
        "600 §10. With consent → VALID. requires_"
        "beneficiary_consent=True flagged per Rule 1 audit "
        "trail. Engine never auto-applies amendment per Rule "
        "7 — operator confirms consent before posting."),
    setup=_setup_tfi,
    actions=_actions_tfi_amendment,
    assertions=_assertions_tfi_amendment,
    requires_engines=("trade_finance_instruments",))


# TFI-04 exposure measurement + aging
def _actions_tfi_exposure_aging(engines: EngineBundle) -> None:
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeFinanceInstrumentsEngine, TradeInstrument,
        InstrumentType, InstrumentState, LcType, BgType)
    eng = TradeFinanceInstrumentsEngine()
    # Partially drawn LC (40% drawn)
    lc_drawn = TradeInstrument(
        instrument_id="LC-DRAWN",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.ACTIVE,
        applicant="Acme", beneficiary="Beta",
        issuing_bank="Ecobank",
        advising_bank="ABC",
        amount_kes=Decimal("10000000"),
        drawn_amount_kes=Decimal("4000000"),
        currency="KES",
        issue_date=_d(2026, 1, 1),
        expiry_date=_d(2026, 6, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="goods")
    # Performance BG, fully unfunded
    bg = TradeInstrument(
        instrument_id="BG-PERF",
        instrument_type=InstrumentType.BG,
        state=InstrumentState.ACTIVE,
        applicant="Acme", beneficiary="KRA",
        issuing_bank="Ecobank",
        advising_bank=None,
        amount_kes=Decimal("5000000"),
        currency="KES",
        issue_date=_d(2026, 1, 1),
        expiry_date=_d(2026, 4, 18),    # 3d to expiry on 4/15
        tenor_days=0, bg_type=BgType.PERFORMANCE)
    engines["__tfi04_lc_exposure__"] = (
        eng.compute_exposure(lc_drawn))
    engines["__tfi04_bg_exposure__"] = (
        eng.compute_exposure(bg))
    engines["__tfi04_aging__"] = eng.age_pending_actions(
        (lc_drawn, bg), as_of_date=_d(2026, 4, 15))


def _assertions_tfi_exposure_aging(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_instruments import (
        ExposureClassification, AgingBucket)
    lc = engines.get("__tfi04_lc_exposure__")
    bg = engines.get("__tfi04_bg_exposure__")
    findings = engines.get("__tfi04_aging__")
    if lc is None or bg is None or findings is None:
        return (AssertionResult(
            assertion_id="tfi04-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    bg_finding = next(
        (f for f in findings
         if f.instrument_id == "BG-PERF"), None)
    return (
        AssertionResult(
            assertion_id="tfi04-a1",
            description=(
                "LC partially drawn: drawn 4m, undrawn 6m, "
                "contingent 6m"),
            expected="4m/6m/6m",
            observed=(
                f"{lc.drawn_kes}/{lc.undrawn_kes}/"
                f"{lc.contingent_liability_kes}"),
            matched=(
                lc.drawn_kes == Decimal("4000000")
                and lc.undrawn_kes == Decimal("6000000")
                and lc.contingent_liability_kes
                == Decimal("6000000"))),
        AssertionResult(
            assertion_id="tfi04-a2",
            description=(
                "BG fully unfunded: 5m contingent liability"),
            expected="5000000",
            observed=str(bg.contingent_liability_kes),
            matched=(
                bg.contingent_liability_kes
                == Decimal("5000000")
                and bg.classification
                == ExposureClassification.UNFUNDED)),
        AssertionResult(
            assertion_id="tfi04-a3",
            description=(
                "BG aging: EXPIRY_IMMINENT (3d to expiry, "
                "≤ 7d threshold)"),
            expected=AgingBucket.EXPIRY_IMMINENT.value,
            observed=(
                bg_finding.bucket.value
                if bg_finding else "n/a"),
            matched=(
                bg_finding is not None
                and bg_finding.bucket
                == AgingBucket.EXPIRY_IMMINENT)),
        AssertionResult(
            assertion_id="tfi04-a4",
            description=(
                "IFRS 9 + IAS 37 cited per Rule 1"),
            expected="IFRS 9 + IAS 37 in refs",
            observed=" / ".join(lc.framework_refs),
            matched=(
                any("IFRS 9" in r for r in lc.framework_refs)
                and any(
                    "IAS 37" in r
                    for r in lc.framework_refs))),
    )


SCENARIO_TFI_04_EXPOSURE_AGING = Scenario(
    scenario_id="TFI-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-269 portfolio measurement: partially-drawn LC "
        "(10m notional, 4m drawn → 6m undrawn = 6m contingent "
        "liability per IFRS 9); fully-unfunded performance BG "
        "(5m contingent); BG with 3d to expiry → "
        "EXPIRY_IMMINENT aging bucket (≤ 7d threshold). IFRS "
        "9 + IAS 37 cited in framework refs."),
    setup=_setup_tfi,
    actions=_actions_tfi_exposure_aging,
    assertions=_assertions_tfi_exposure_aging,
    requires_engines=("trade_finance_instruments",))


# ════════════════════════════════════════════════════════════════════════
# v10.71 — Trade Finance Limits & Risk Management (ENH-273)
# ════════════════════════════════════════════════════════════════════════

def _setup_tfl(engines: EngineBundle) -> None:
    pass


def _make_tfl_lc(
    iid, applicant="Acme Imports Ltd",
    beneficiary="Shanghai Steel",
    amount=Decimal("5000000"),
    expiry_iso="2026-08-01",
):
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=InstrumentState.ACTIVE,
        applicant=applicant, beneficiary=beneficiary,
        issuing_bank="Ecobank Kenya",
        advising_bank="Bank of China",
        amount_kes=amount, currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d.fromisoformat(expiry_iso),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="goods")


# TFL-01 country + counterparty utilization
def _actions_tfl_country_counterparty(
    engines: EngineBundle,
) -> None:
    from utils.trade_finance_limits import (
        TradeFinanceLimitsEngine, CountryLimit,
        CounterpartyLimit, CountryAttribution)
    eng = TradeFinanceLimitsEngine()
    insts = (
        _make_tfl_lc(
            "L1", applicant="MegaCorp",
            beneficiary="ChinaCorp",
            amount=Decimal("3000000")),
        _make_tfl_lc(
            "L2", applicant="MegaCorp",
            beneficiary="ChinaCorp",
            amount=Decimal("2000000")),
        _make_tfl_lc(
            "L3", applicant="SmallCorp",
            beneficiary="GermanCorp",
            amount=Decimal("8000000")),
    )
    country_limits = (
        CountryLimit(
            country_code="CN",
            limit_kes=Decimal("10000000")),
        CountryLimit(
            country_code="DE",
            limit_kes=Decimal("10000000")),
    )
    cp_limits = (
        CounterpartyLimit(
            counterparty_id="MegaCorp",
            counterparty_name="MegaCorp Ltd",
            limit_kes=Decimal("10000000")),
        CounterpartyLimit(
            counterparty_id="SmallCorp",
            counterparty_name="SmallCorp Ltd",
            limit_kes=Decimal("10000000")),
    )
    attrs = (
        CountryAttribution(
            counterparty_id="ChinaCorp",
            country_code="CN"),
        CountryAttribution(
            counterparty_id="GermanCorp",
            country_code="DE"),
    )
    engines["__tfl01_country__"] = (
        eng.compute_country_utilization(
            insts, country_limits, attrs))
    engines["__tfl01_cp__"] = (
        eng.compute_counterparty_utilization(
            insts, cp_limits))


def _assertions_tfl_country_counterparty(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    country_utils = engines.get("__tfl01_country__")
    cp_utils = engines.get("__tfl01_cp__")
    if country_utils is None or cp_utils is None:
        return (AssertionResult(
            assertion_id="tfl01-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    by_country = {u.bucket_key: u for u in country_utils}
    by_cp = {u.bucket_key: u for u in cp_utils}
    return (
        AssertionResult(
            assertion_id="tfl01-a1",
            description=(
                "CN exposure 5m / 10m limit = 50% (HEALTHY)"),
            expected="5000000",
            observed=str(by_country["CN"].exposure_kes),
            matched=(
                by_country["CN"].exposure_kes
                == Decimal("5000000")
                and by_country["CN"].utilization_pct
                == Decimal("0.5"))),
        AssertionResult(
            assertion_id="tfl01-a2",
            description=(
                "DE exposure 8m / 10m limit = 80% (ELEVATED)"),
            expected="ELEVATED",
            observed=by_country["DE"].severity.value,
            matched=(
                by_country["DE"].severity.value
                == "ELEVATED")),
        AssertionResult(
            assertion_id="tfl01-a3",
            description=(
                "MegaCorp aggregated by applicant: 5m exposure"),
            expected="5000000",
            observed=str(by_cp["MegaCorp"].exposure_kes),
            matched=(
                by_cp["MegaCorp"].exposure_kes
                == Decimal("5000000"))),
        AssertionResult(
            assertion_id="tfl01-a4",
            description=(
                "SmallCorp 8m / 10m = 80% (ELEVATED)"),
            expected="ELEVATED",
            observed=by_cp["SmallCorp"].severity.value,
            matched=(
                by_cp["SmallCorp"].severity.value
                == "ELEVATED")),
    )


SCENARIO_TFL_01_COUNTRY_CP = Scenario(
    scenario_id="TFL-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-273 country + counterparty utilization across 3 "
        "LCs. CN exposure 5m/10m = 50% HEALTHY; DE exposure "
        "8m/10m = 80% ELEVATED; counterparty MegaCorp "
        "aggregated by APPLICANT (5m across 2 LCs); "
        "SmallCorp 8m/10m = 80% ELEVATED. Demonstrates "
        "applicant-side aggregation discipline + 4-tier "
        "severity calibration."),
    setup=_setup_tfl,
    actions=_actions_tfl_country_counterparty,
    assertions=_assertions_tfl_country_counterparty,
    requires_engines=("trade_finance_limits",))


# TFL-02 severity threshold boundaries
def _actions_tfl_severity(engines: EngineBundle) -> None:
    from utils.trade_finance_limits import (
        TradeFinanceLimitsEngine, UtilizationSeverity)
    from decimal import Decimal as D
    eng = TradeFinanceLimitsEngine()
    cases = (
        (D("0.5"), UtilizationSeverity.HEALTHY),
        (D("0.70"), UtilizationSeverity.HEALTHY),
        (D("0.71"), UtilizationSeverity.ELEVATED),
        (D("0.85"), UtilizationSeverity.ELEVATED),
        (D("0.86"), UtilizationSeverity.HIGH),
        (D("1.00"), UtilizationSeverity.HIGH),
        (D("1.01"), UtilizationSeverity.BREACH),
    )
    engines["__tfl02__"] = tuple(
        (pct, eng._severity(pct), expected)
        for pct, expected in cases)


def _assertions_tfl_severity(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    cases = engines.get("__tfl02__")
    if not cases:
        return (AssertionResult(
            assertion_id="tfl02-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    pairs = []
    all_match = True
    for i, (pct, sev, expected) in enumerate(cases):
        match = sev == expected
        all_match = all_match and match
        pairs.append(
            f"{pct}→{sev.value}/{expected.value}={match}")
    return (
        AssertionResult(
            assertion_id="tfl02-a1",
            description=(
                "All 7 severity threshold boundary cases match"),
            expected="all True",
            observed=" | ".join(pairs),
            matched=all_match),
        AssertionResult(
            assertion_id="tfl02-a2",
            description=(
                "Boundary discipline: 0.70 HEALTHY (not "
                "ELEVATED), 1.00 HIGH (not BREACH)"),
            expected="strict > comparison",
            observed=(
                f"0.70→{cases[1][1].value}, "
                f"1.00→{cases[5][1].value}"),
            matched=(
                cases[1][1].name == "HEALTHY"
                and cases[5][1].name == "HIGH")),
    )


SCENARIO_TFL_02_SEVERITY = Scenario(
    scenario_id="TFL-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-273 4-tier UtilizationSeverity boundary "
        "verification across 7 cases. HEALTHY ≤70%, ELEVATED "
        "70-85%, HIGH 85-100%, BREACH >100%. Boundary "
        "discipline: 0.70 stays HEALTHY (strict > "
        "comparison), 1.00 stays HIGH (BREACH only above "
        "100%). Validates threshold calibration matches "
        "documented contract."),
    setup=_setup_tfl,
    actions=_actions_tfl_severity,
    assertions=_assertions_tfl_severity,
    requires_engines=("trade_finance_limits",))


# TFL-03 pre-deal check — block when breached
def _actions_tfl_pre_deal_block(
    engines: EngineBundle,
) -> None:
    from utils.trade_finance_limits import (
        TradeFinanceLimitsEngine, CounterpartyLimit)
    eng = TradeFinanceLimitsEngine()
    proposed = _make_tfl_lc(
        "PROPOSED", applicant="MegaCorp",
        amount=Decimal("5000000"))
    existing = (
        _make_tfl_lc(
            "EX1", applicant="MegaCorp",
            amount=Decimal("8000000")),
    )
    cp_limits = (
        CounterpartyLimit(
            counterparty_id="MegaCorp",
            counterparty_name="MegaCorp",
            limit_kes=Decimal("10000000")),
    )
    engines["__tfl03__"] = eng.check_pre_deal(
        proposed, existing,
        counterparty_limits=cp_limits)


def _assertions_tfl_pre_deal_block(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_limits import (
        PreDealOutcome, LimitDimension)
    check = engines.get("__tfl03__")
    if check is None:
        return (AssertionResult(
            assertion_id="tfl03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfl03-a1",
            description=(
                "Pre-deal 8m+5m=13m vs 10m limit → "
                "BLOCK_RECOMMENDED"),
            expected=PreDealOutcome.BLOCK_RECOMMENDED.value,
            observed=check.outcome.value,
            matched=(
                check.outcome
                == PreDealOutcome.BLOCK_RECOMMENDED)),
        AssertionResult(
            assertion_id="tfl03-a2",
            description=(
                "Binding dimension is COUNTERPARTY"),
            expected=LimitDimension.COUNTERPARTY.value,
            observed=(
                check.binding_dimension.value
                if check.binding_dimension else "n/a"),
            matched=(
                check.binding_dimension
                == LimitDimension.COUNTERPARTY)),
        AssertionResult(
            assertion_id="tfl03-a3",
            description=(
                "Engine never blocks deals — Rule 7 cited"),
            expected="Rule 7 in framework_refs",
            observed=" | ".join(check.framework_refs),
            matched=any(
                "Rule 7" in r
                for r in check.framework_refs)),
        AssertionResult(
            assertion_id="tfl03-a4",
            description=(
                "Description includes binding dimension"),
            expected="COUNTERPARTY in description",
            observed=check.description,
            matched=(
                "COUNTERPARTY" in check.description)),
    )


SCENARIO_TFL_03_PRE_DEAL_BLOCK = Scenario(
    scenario_id="TFL-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-273 pre-deal check: existing 8m + proposed 5m = "
        "13m post-deal vs 10m counterparty limit → BREACH → "
        "BLOCK_RECOMMENDED outcome; binding_dimension "
        "COUNTERPARTY identified. Per Rule 7, engine surfaces "
        "outcome recommendation; operator approves or "
        "rejects; engine never auto-blocks deals."),
    setup=_setup_tfl,
    actions=_actions_tfl_pre_deal_block,
    assertions=_assertions_tfl_pre_deal_block,
    requires_engines=("trade_finance_limits",))


# TFL-04 portfolio report orchestrator
def _actions_tfl_portfolio_report(
    engines: EngineBundle,
) -> None:
    from utils.trade_finance_limits import (
        TradeFinanceLimitsEngine, ProductLimit, TenorLimit,
        TenorBucket, CounterpartyLimit)
    from utils.trade_finance_instruments import InstrumentType
    eng = TradeFinanceLimitsEngine()
    insts = (
        _make_tfl_lc(
            "L1", applicant="A",
            amount=Decimal("5000000"),
            expiry_iso="2026-06-01"),   # SHORT 47d
        _make_tfl_lc(
            "L2", applicant="A",
            amount=Decimal("6000000"),
            expiry_iso="2026-08-01"),   # MEDIUM 108d
    )
    cp_limits = (
        CounterpartyLimit(
            counterparty_id="A", counterparty_name="A Ltd",
            limit_kes=Decimal("10000000")),
    )
    product_limits = (
        ProductLimit(
            instrument_type=InstrumentType.LC,
            limit_kes=Decimal("100000000")),
    )
    tenor_limits = (
        TenorLimit(
            bucket=TenorBucket.SHORT,
            limit_kes=Decimal("20000000")),
        TenorLimit(
            bucket=TenorBucket.MEDIUM,
            limit_kes=Decimal("20000000")),
    )
    engines["__tfl04__"] = eng.build_portfolio_report(
        insts,
        counterparty_limits=cp_limits,
        product_limits=product_limits,
        tenor_limits=tenor_limits,
        as_of_date_iso="2026-04-15")


def _assertions_tfl_portfolio_report(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    report = engines.get("__tfl04__")
    if report is None:
        return (AssertionResult(
            assertion_id="tfl04-a0",
            description="Report populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfl04-a1",
            description=(
                "11m / 10m counterparty limit → 1 BREACH"),
            expected="≥ 1",
            observed=str(report.breached_count),
            matched=report.breached_count >= 1),
        AssertionResult(
            assertion_id="tfl04-a2",
            description=(
                "by_dimension counts populated for all 4 "
                "dimensions"),
            expected="all 4 populated",
            observed=str(report.by_dimension),
            matched=(
                report.by_dimension.get(
                    "COUNTERPARTY", 0) >= 1
                and report.by_dimension.get(
                    "PRODUCT", 0) >= 1
                and report.by_dimension.get(
                    "TENOR", 0) >= 2)),
        AssertionResult(
            assertion_id="tfl04-a3",
            description=(
                "by_severity breakdown includes BREACH count"),
            expected="BREACH ≥ 1",
            observed=str(report.by_severity),
            matched=(
                report.by_severity.get("BREACH", 0) >= 1)),
        AssertionResult(
            assertion_id="tfl04-a4",
            description=(
                "ENH-273 cited per Rule 1; Rule 7 boundary "
                "documented"),
            expected="ENH-273 + Rule 7 in refs",
            observed=" | ".join(report.framework_refs),
            matched=(
                any("ENH-273" in r
                    for r in report.framework_refs)
                and any("Rule 7" in r
                        for r in report.framework_refs))),
    )


SCENARIO_TFL_04_PORTFOLIO_REPORT = Scenario(
    scenario_id="TFL-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-273 build_portfolio_report orchestrator: 2 LCs "
        "(11m total) for applicant A across SHORT + MEDIUM "
        "tenor buckets. Counterparty limit 10m → BREACH; "
        "product limit 100m → HEALTHY; tenor limits 20m each "
        "→ HEALTHY. Validates 4-dimensional aggregation + "
        "by_severity / by_dimension breakdowns + "
        "breached_count + framework refs include ENH-273 + "
        "Rule 7."),
    setup=_setup_tfl,
    actions=_actions_tfl_portfolio_report,
    assertions=_assertions_tfl_portfolio_report,
    requires_engines=("trade_finance_limits",))


# ════════════════════════════════════════════════════════════════════════
# v10.72 — SWIFT MT validation (ENH-272)
# ════════════════════════════════════════════════════════════════════════

def _setup_swi(engines: EngineBundle) -> None:
    pass


# SWI-01 parse + validate clean MT700
def _actions_swi_clean_mt700(engines: EngineBundle) -> None:
    from utils.trade_finance_swift import (
        TradeFinanceSwiftEngine, SwiftMessageType,
        SAMPLE_MT700)
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    engines["__swi01_parsed__"] = parsed
    engines["__swi01_validation__"] = (
        eng.validate_mt700_structure(parsed))


def _assertions_swi_clean_mt700(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_swift import (
        MessageValidationOutcome)
    parsed = engines.get("__swi01_parsed__")
    v = engines.get("__swi01_validation__")
    if parsed is None or v is None:
        return (AssertionResult(
            assertion_id="swi01-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    tags = {f.tag for f in parsed.fields}
    return (
        AssertionResult(
            assertion_id="swi01-a1",
            description="Outcome VALID for clean MT700",
            expected=MessageValidationOutcome.VALID.value,
            observed=v.outcome.value,
            matched=(
                v.outcome
                == MessageValidationOutcome.VALID)),
        AssertionResult(
            assertion_id="swi01-a2",
            description=(
                "All key tags parsed (:27: :40A: :20: "
                ":31C: :31D: :32B: :45A: :46A: :49:)"),
            expected="all key tags",
            observed=", ".join(sorted(tags))[:80],
            matched=(
                {"27", "40A", "20", "31C", "31D", "32B",
                 "45A", "46A", "49"}.issubset(tags))),
        AssertionResult(
            assertion_id="swi01-a3",
            description="completeness_pct = 1.0",
            expected="1",
            observed=str(v.completeness_pct),
            matched=v.completeness_pct == Decimal("1")),
        AssertionResult(
            assertion_id="swi01-a4",
            description=(
                "SWIFT MT 700 + UCP 600 cited in "
                "framework refs"),
            expected="SWIFT + UCP 600",
            observed=" / ".join(v.framework_refs),
            matched=(
                any("SWIFT" in r for r in v.framework_refs)
                and any(
                    "UCP 600" in r
                    for r in v.framework_refs))),
    )


SCENARIO_SWI_01_MT700_CLEAN = Scenario(
    scenario_id="SWI-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-272: parse + validate clean MT700 sample with "
        "all mandatory fields. Outcome VALID, all key tags "
        "present (27/40A/20/31C/31D/32B/45A/46A/49), "
        "completeness_pct=1.0, framework refs cite SWIFT MT "
        "700 + ICC UCP 600."),
    setup=_setup_swi,
    actions=_actions_swi_clean_mt700,
    assertions=_assertions_swi_clean_mt700,
    requires_engines=("trade_finance_swift",))


# SWI-02 missing mandatory + malformed format
def _actions_swi_invalid_mt700(engines: EngineBundle) -> None:
    from utils.trade_finance_swift import (
        TradeFinanceSwiftEngine, SwiftMessageType)
    eng = TradeFinanceSwiftEngine()
    body = """{4:
:27:1/1
:20:THIS REFERENCE IS WAY TOO LONG
:31C:260601
:31D:260401 NAIROBI
:50:A
:59:B
:32B:USD100,00
:46A:DOCS
:49:WITHOUT
-}"""
    parsed = eng.parse_message(SwiftMessageType.MT700, body)
    engines["__swi02__"] = (
        eng.validate_mt700_structure(parsed))


def _assertions_swi_invalid_mt700(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_swift import (
        MessageValidationOutcome, FieldStatus)
    v = engines.get("__swi02__")
    if v is None:
        return (AssertionResult(
            assertion_id="swi02-a0",
            description="Validation populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="swi02-a1",
            description="Outcome INVALID",
            expected=MessageValidationOutcome.INVALID.value,
            observed=v.outcome.value,
            matched=(
                v.outcome
                == MessageValidationOutcome.INVALID)),
        AssertionResult(
            assertion_id="swi02-a2",
            description=":40A: missing flagged",
            expected="40A MISSING_MANDATORY",
            observed=" / ".join(
                f"{f.tag}:{f.status.value}" for f in v.findings),
            matched=any(
                f.tag == "40A"
                and f.status == FieldStatus.MISSING_MANDATORY
                for f in v.findings)),
        AssertionResult(
            assertion_id="swi02-a3",
            description=":20: malformed (>16 chars)",
            expected="20 MALFORMED",
            observed=" / ".join(
                f"{f.tag}:{f.status.value}" for f in v.findings),
            matched=any(
                f.tag == "20"
                and f.status == FieldStatus.MALFORMED
                for f in v.findings)),
        AssertionResult(
            assertion_id="swi02-a4",
            description=(
                ":31C/:31D: expiry-before-issue cross-field "
                "violation flagged"),
            expected="31C/31D MALFORMED",
            observed=" / ".join(
                f.tag for f in v.findings),
            matched=any(
                f.tag == "31C/31D" for f in v.findings)),
    )


SCENARIO_SWI_02_MT700_INVALID = Scenario(
    scenario_id="SWI-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-272 MT700 with multiple violations: missing "
        ":40A: + malformed :20: (>16 chars) + missing "
        ":45A: + expiry (260401) before issue (260601) "
        "cross-field violation. Outcome INVALID with each "
        "violation surfaced as separate FieldFinding per "
        "Rule 1."),
    setup=_setup_swi,
    actions=_actions_swi_invalid_mt700,
    assertions=_assertions_swi_invalid_mt700,
    requires_engines=("trade_finance_swift",))


# SWI-03 cross-check MT700 against TradeInstrument
def _actions_swi_cross_check(engines: EngineBundle) -> None:
    from datetime import date as _d
    from utils.trade_finance_swift import (
        TradeFinanceSwiftEngine, SwiftMessageType,
        SAMPLE_MT700)
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    inst_aligned = TradeInstrument(
        instrument_id="LC-2026-001",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.DRAFT,
        applicant="ACME IMPORTS LTD",
        beneficiary="SHANGHAI STEEL CO",
        issuing_bank="Eco", advising_bank="ABC",
        amount_kes=Decimal("500000"),
        currency="USD",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 7, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="Steel coils")
    inst_divergent = TradeInstrument(
        instrument_id="LC-2026-001",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.DRAFT,
        applicant="ACME IMPORTS LTD",
        beneficiary="SHANGHAI STEEL CO",
        issuing_bank="Eco", advising_bank="ABC",
        amount_kes=Decimal("500000"),
        currency="EUR",   # diverges from MT700's USD
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 7, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="Steel coils")
    engines["__swi03_aligned__"] = (
        eng.cross_check_mt700_against_instrument(
            parsed, inst_aligned))
    engines["__swi03_divergent__"] = (
        eng.cross_check_mt700_against_instrument(
            parsed, inst_divergent))


def _assertions_swi_cross_check(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_swift import CrossCheckOutcome
    aligned = engines.get("__swi03_aligned__")
    divergent = engines.get("__swi03_divergent__")
    if aligned is None or divergent is None:
        return (AssertionResult(
            assertion_id="swi03-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="swi03-a1",
            description=(
                "Aligned instrument → ALIGNED overall"),
            expected=CrossCheckOutcome.ALIGNED.value,
            observed=aligned.overall_outcome.value,
            matched=(
                aligned.overall_outcome
                == CrossCheckOutcome.ALIGNED)),
        AssertionResult(
            assertion_id="swi03-a2",
            description=(
                "EUR-vs-USD instrument → DIVERGENT overall"),
            expected=CrossCheckOutcome.DIVERGENT.value,
            observed=divergent.overall_outcome.value,
            matched=(
                divergent.overall_outcome
                == CrossCheckOutcome.DIVERGENT)),
        AssertionResult(
            assertion_id="swi03-a3",
            description=(
                "Currency divergence specifically flagged"),
            expected="32B-currency DIVERGENT",
            observed=", ".join(
                f"{f.field_tag}:{f.outcome.value}"
                for f in divergent.findings),
            matched=any(
                f.field_tag == "32B-currency"
                and f.outcome == CrossCheckOutcome.DIVERGENT
                for f in divergent.findings)),
        AssertionResult(
            assertion_id="swi03-a4",
            description=(
                "Engine never modifies routing — Rule 7 cited"),
            expected="Rule 7 in framework_refs",
            observed=" / ".join(divergent.framework_refs),
            matched=any(
                "Rule 7" in r
                for r in divergent.framework_refs)),
    )


SCENARIO_SWI_03_CROSS_CHECK = Scenario(
    scenario_id="SWI-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-272 cross_check_mt700_against_instrument: same "
        "MT700 message cross-checked against two "
        "TradeInstruments — one aligned (ALIGNED outcome) + "
        "one with EUR currency vs MT700's USD (DIVERGENT "
        "outcome with :32B-currency: specifically flagged). "
        "Per Rule 7, engine surfaces alignment findings "
        "for operator reconciliation; never modifies the "
        "MT700 or the instrument record."),
    setup=_setup_swi,
    actions=_actions_swi_cross_check,
    assertions=_assertions_swi_cross_check,
    requires_engines=("trade_finance_swift",))


# SWI-04 MT103 payment validation
def _actions_swi_mt103(engines: EngineBundle) -> None:
    from utils.trade_finance_swift import (
        TradeFinanceSwiftEngine, SwiftMessageType,
        SAMPLE_MT103)
    eng = TradeFinanceSwiftEngine()
    parsed_clean = eng.parse_message(
        SwiftMessageType.MT103, SAMPLE_MT103)
    body_invalid = """{4:
:20:PAY-001
:23B:CRED
:32A:260415USD500,00
:59:BENE
-}"""
    parsed_invalid = eng.parse_message(
        SwiftMessageType.MT103, body_invalid)
    engines["__swi04_clean__"] = (
        eng.validate_mt103_structure(parsed_clean))
    engines["__swi04_invalid__"] = (
        eng.validate_mt103_structure(parsed_invalid))


def _assertions_swi_mt103(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_swift import (
        MessageValidationOutcome, FieldStatus)
    clean = engines.get("__swi04_clean__")
    invalid = engines.get("__swi04_invalid__")
    if clean is None or invalid is None:
        return (AssertionResult(
            assertion_id="swi04-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="swi04-a1",
            description="Clean MT103 → VALID",
            expected=MessageValidationOutcome.VALID.value,
            observed=clean.outcome.value,
            matched=(
                clean.outcome
                == MessageValidationOutcome.VALID)),
        AssertionResult(
            assertion_id="swi04-a2",
            description=(
                "MT103 missing :71A: charges → INVALID"),
            expected=MessageValidationOutcome.INVALID.value,
            observed=invalid.outcome.value,
            matched=(
                invalid.outcome
                == MessageValidationOutcome.INVALID)),
        AssertionResult(
            assertion_id="swi04-a3",
            description=":71A: missing flagged",
            expected="71A MISSING_MANDATORY",
            observed=" / ".join(
                f"{f.tag}:{f.status.value}"
                for f in invalid.findings),
            matched=any(
                f.tag == "71A"
                and f.status == FieldStatus.MISSING_MANDATORY
                for f in invalid.findings)),
        AssertionResult(
            assertion_id="swi04-a4",
            description=(
                "SWIFT Cat 1 cited in framework refs"),
            expected="Category 1 in refs",
            observed=" / ".join(clean.framework_refs),
            matched=any(
                "Category 1" in r
                for r in clean.framework_refs)),
    )


SCENARIO_SWI_04_MT103 = Scenario(
    scenario_id="SWI-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-272 validate_mt103_structure: clean MT103 "
        "sample with mandatory :20: :23B: :32A: :59: :71A: "
        "→ VALID. MT103 missing :71A: details of charges "
        "→ INVALID. Framework refs include SWIFT MT 103 + "
        "SWIFT Category 1 (Customer Payments)."),
    setup=_setup_swi,
    actions=_actions_swi_mt103,
    assertions=_assertions_swi_mt103,
    requires_engines=("trade_finance_swift",))


# ════════════════════════════════════════════════════════════════════════
# v10.73 — Trade Finance Compliance (ENH-274)
# ════════════════════════════════════════════════════════════════════════

def _setup_scr(engines: EngineBundle) -> None:
    pass


# SCR-01 OFAC SDN exact party match
def _actions_scr_party_match(engines: EngineBundle) -> None:
    from utils.trade_finance_compliance import (
        TradeFinanceComplianceEngine, TradeFinanceParty,
        SanctionsListEntry, HitSeverity)
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="Sanctioned Holdings Ltd")
    sanctions = (
        SanctionsListEntry(
            list_id="OFAC_SDN",
            list_authority="U.S. Treasury OFAC",
            entry_id="SDN-001",
            entity_type="ENTITY",
            name="Sanctioned Holdings Ltd",
            severity=HitSeverity.CRITICAL),
    )
    engines["__scr01__"] = eng.screen_party(party, sanctions)


def _assertions_scr_party_match(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_compliance import (
        HitSeverity, ScreeningDimension, MatchType)
    hits = engines.get("__scr01__")
    if hits is None or len(hits) == 0:
        return (AssertionResult(
            assertion_id="scr01-a0",
            description="Hits populated",
            expected="≥ 1", observed="0",
            matched=False),)
    h = hits[0]
    return (
        AssertionResult(
            assertion_id="scr01-a1",
            description="Hit dimension PARTY",
            expected=ScreeningDimension.PARTY.value,
            observed=h.dimension.value,
            matched=h.dimension == ScreeningDimension.PARTY),
        AssertionResult(
            assertion_id="scr01-a2",
            description="Hit severity CRITICAL (OFAC)",
            expected=HitSeverity.CRITICAL.value,
            observed=h.severity.value,
            matched=h.severity == HitSeverity.CRITICAL),
        AssertionResult(
            assertion_id="scr01-a3",
            description="match_type NORMALIZED",
            expected=MatchType.NORMALIZED.value,
            observed=h.match_type.value,
            matched=h.match_type == MatchType.NORMALIZED),
        AssertionResult(
            assertion_id="scr01-a4",
            description=(
                "OFAC source authority cited in "
                "framework refs"),
            expected="OFAC in refs",
            observed=" / ".join(h.framework_refs),
            matched=any(
                "OFAC" in r for r in h.framework_refs)),
    )


SCENARIO_SCR_01_PARTY = Scenario(
    scenario_id="SCR-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-274 screen_party: exact-name match against OFAC "
        "SDN sanctions list. Hit dimension PARTY, severity "
        "CRITICAL, match_type NORMALIZED, source authority "
        "cited per Rule 1. Per Rule 7, hit surfaced for "
        "operator adjudication — engine never blocks."),
    setup=_setup_scr,
    actions=_actions_scr_party_match,
    assertions=_assertions_scr_party_match,
    requires_engines=("trade_finance_compliance",))


# SCR-02 country embargo + transit
def _actions_scr_country(engines: EngineBundle) -> None:
    from utils.trade_finance_compliance import (
        TradeFinanceComplianceEngine, CountryEmbargo,
        HitSeverity)
    eng = TradeFinanceComplianceEngine()
    embargoes = (
        CountryEmbargo(
            country_code="ZZ", list_id="UN_CONS",
            list_authority="UN Security Council",
            severity=HitSeverity.CRITICAL,
            notes="comprehensive embargo"),
        CountryEmbargo(
            country_code="YY", list_id="EU_RM",
            list_authority="EU Restrictive Measures",
            severity=HitSeverity.HIGH),
    )
    engines["__scr02_un__"] = eng.screen_country(
        "ZZ", "applicant.country", embargoes)
    engines["__scr02_eu__"] = eng.screen_country(
        "YY", "transit_country", embargoes)
    engines["__scr02_clean__"] = eng.screen_country(
        "KE", "applicant.country", embargoes)


def _assertions_scr_country(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_compliance import HitSeverity
    un = engines.get("__scr02_un__")
    eu = engines.get("__scr02_eu__")
    clean = engines.get("__scr02_clean__")
    if un is None or eu is None or clean is None:
        return (AssertionResult(
            assertion_id="scr02-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="scr02-a1",
            description=(
                "ZZ on UN list → 1 CRITICAL hit"),
            expected="1 CRITICAL",
            observed=str(len(un)),
            matched=(
                len(un) == 1
                and un[0].severity == HitSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="scr02-a2",
            description=(
                "YY on EU list → 1 HIGH hit"),
            expected="1 HIGH",
            observed=str(len(eu)),
            matched=(
                len(eu) == 1
                and eu[0].severity == HitSeverity.HIGH)),
        AssertionResult(
            assertion_id="scr02-a3",
            description=(
                "KE on no list → 0 hits (clean)"),
            expected="0 hits",
            observed=str(len(clean)),
            matched=len(clean) == 0),
        AssertionResult(
            assertion_id="scr02-a4",
            description=(
                "List authority differentiates UN-CRITICAL "
                "from EU-HIGH per source-list ratchet"),
            expected="distinct authorities",
            observed=(
                f"UN={un[0].source_list_authority}, "
                f"EU={eu[0].source_list_authority}"),
            matched=(
                "UN" in un[0].source_list_authority
                and "EU" in eu[0].source_list_authority)),
    )


SCENARIO_SCR_02_COUNTRY = Scenario(
    scenario_id="SCR-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-274 screen_country: 3 cases — country on UN "
        "Consolidated → CRITICAL; country on EU Restrictive "
        "→ HIGH; country on no list → no hits. Source-list "
        "authority drives severity per Rule 1; engine "
        "surfaces hits, never autonomously blocks."),
    setup=_setup_scr,
    actions=_actions_scr_country,
    assertions=_assertions_scr_country,
    requires_engines=("trade_finance_compliance",))


# SCR-03 dual-use goods + word boundary discipline
def _actions_scr_goods(engines: EngineBundle) -> None:
    from utils.trade_finance_compliance import (
        TradeFinanceComplianceEngine, ProhibitedGoodsKeyword,
        HitSeverity)
    eng = TradeFinanceComplianceEngine()
    keywords = (
        ProhibitedGoodsKeyword(
            keyword="centrifuge",
            category="DUAL_USE_NUCLEAR",
            list_id="WASSENAAR",
            list_authority="Wassenaar Arrangement",
            severity=HitSeverity.HIGH),
        ProhibitedGoodsKeyword(
            keyword="ant",
            category="TEST", list_id="X",
            list_authority="X",
            severity=HitSeverity.MEDIUM),
    )
    engines["__scr03_match__"] = eng.screen_goods(
        "10 industrial centrifuge units laboratory grade",
        keywords)
    engines["__scr03_no_match__"] = eng.screen_goods(
        "antibiotic medication 500mg blister pack",
        keywords)


def _assertions_scr_goods(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    match = engines.get("__scr03_match__")
    no_match = engines.get("__scr03_no_match__")
    if match is None or no_match is None:
        return (AssertionResult(
            assertion_id="scr03-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="scr03-a1",
            description=(
                "'centrifuge' keyword match → 1 hit"),
            expected="1 hit",
            observed=str(len(match)),
            matched=len(match) == 1),
        AssertionResult(
            assertion_id="scr03-a2",
            description=(
                "Wassenaar source authority cited"),
            expected="Wassenaar in source",
            observed=(
                match[0].source_list_authority
                if match else "n/a"),
            matched=(
                len(match) == 1
                and "Wassenaar"
                in match[0].source_list_authority)),
        AssertionResult(
            assertion_id="scr03-a3",
            description=(
                "Word-boundary discipline: 'antibiotic' "
                "does NOT match 'ant' keyword"),
            expected="0 hits",
            observed=str(len(no_match)),
            matched=len(no_match) == 0),
        AssertionResult(
            assertion_id="scr03-a4",
            description=(
                "Category tagged in finding for "
                "operator routing"),
            expected="DUAL_USE_NUCLEAR in description",
            observed=(
                match[0].description
                if match else "n/a"),
            matched=(
                len(match) == 1
                and "DUAL_USE_NUCLEAR"
                in match[0].description)),
    )


SCENARIO_SCR_03_GOODS = Scenario(
    scenario_id="SCR-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-274 screen_goods: 'centrifuge' keyword from "
        "Wassenaar Arrangement matches 'industrial "
        "centrifuge units' → 1 HIGH hit; 'ant' keyword "
        "DOES NOT match 'antibiotic' (word-boundary regex "
        "discipline). Category tagging routes hit to "
        "appropriate review team. Per Rule 7, engine never "
        "decides true vs false positive."),
    setup=_setup_scr,
    actions=_actions_scr_goods,
    assertions=_assertions_scr_goods,
    requires_engines=("trade_finance_compliance",))


# SCR-04 instrument-level orchestrator + outcome ladder
def _actions_scr_instrument(engines: EngineBundle) -> None:
    from utils.trade_finance_compliance import (
        TradeFinanceComplianceEngine, TradeFinanceParty,
        TradeFinanceShipment, SanctionsListEntry,
        CountryEmbargo, HitSeverity)
    eng = TradeFinanceComplianceEngine()
    sanctions = (
        SanctionsListEntry(
            list_id="OFAC_SDN", list_authority="OFAC",
            entry_id="X", entity_type="ENTITY",
            name="Bad Corp",
            severity=HitSeverity.CRITICAL),
    )
    embargoes = (
        CountryEmbargo(
            country_code="ZZ", list_id="UN",
            list_authority="UN",
            severity=HitSeverity.CRITICAL),
    )
    # Block scenario: party Bad Corp + transit ZZ
    parties_block = (
        TradeFinanceParty(
            party_id="P1", party_role="BENEFICIARY",
            name="Bad Corp"),
    )
    shipment_block = TradeFinanceShipment(
        transit_countries=("ZZ",))
    # Clean scenario
    parties_clean = (
        TradeFinanceParty(
            party_id="P1", party_role="APPLICANT",
            name="Clean Co", country="KE"),
    )
    shipment_clean = TradeFinanceShipment(
        port_of_loading="KEMBA",
        description_of_goods="cement bags 100MT")
    engines["__scr04_block__"] = eng.screen_instrument(
        "INST-BLOCK",
        parties=parties_block, shipment=shipment_block,
        sanctions_list=sanctions,
        country_embargoes=embargoes)
    engines["__scr04_clean__"] = eng.screen_instrument(
        "INST-CLEAN",
        parties=parties_clean, shipment=shipment_clean,
        sanctions_list=sanctions,
        country_embargoes=embargoes)


def _assertions_scr_instrument(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_compliance import (
        ScreeningOutcome)
    block = engines.get("__scr04_block__")
    clean = engines.get("__scr04_clean__")
    if block is None or clean is None:
        return (AssertionResult(
            assertion_id="scr04-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="scr04-a1",
            description=(
                "Block scenario → BLOCK_RECOMMENDED outcome"),
            expected=(
                ScreeningOutcome.BLOCK_RECOMMENDED.value),
            observed=block.outcome.value,
            matched=(
                block.outcome
                == ScreeningOutcome.BLOCK_RECOMMENDED)),
        AssertionResult(
            assertion_id="scr04-a2",
            description=(
                "Clean scenario → CLEAR outcome (0 hits)"),
            expected=ScreeningOutcome.CLEAR.value,
            observed=clean.outcome.value,
            matched=(
                clean.outcome == ScreeningOutcome.CLEAR
                and len(clean.hits) == 0)),
        AssertionResult(
            assertion_id="scr04-a3",
            description=(
                "Block by_dimension shows hits across "
                "PARTY + COUNTRY"),
            expected="PARTY + COUNTRY ≥ 1 each",
            observed=str(block.by_dimension),
            matched=(
                block.by_dimension.get("PARTY", 0) >= 1
                and block.by_dimension.get(
                    "COUNTRY", 0) >= 1)),
        AssertionResult(
            assertion_id="scr04-a4",
            description=(
                "Engine never reports SARs — Rule 7 cited "
                "in framework refs"),
            expected="Rule 7 in refs",
            observed=" / ".join(block.framework_refs),
            matched=any(
                "Rule 7" in r
                for r in block.framework_refs)),
    )


SCENARIO_SCR_04_INSTRUMENT = Scenario(
    scenario_id="SCR-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-274 screen_instrument orchestrator: 2 cases — "
        "block (party 'Bad Corp' on OFAC SDN + transit "
        "country 'ZZ' on UN list → BLOCK_RECOMMENDED with "
        "hits across PARTY + COUNTRY dimensions); clean "
        "(KE applicant + KEMBA port + cement goods → CLEAR "
        "with 0 hits). Validates outcome ladder + by_"
        "dimension aggregation + Rule 7 documentation."),
    setup=_setup_scr,
    actions=_actions_scr_instrument,
    assertions=_assertions_scr_instrument,
    requires_engines=("trade_finance_compliance",))


# ════════════════════════════════════════════════════════════════════════
# v10.75 — Trade Finance Accounting & Integration (ENH-275)
# ════════════════════════════════════════════════════════════════════════

def _setup_tfa(engines: EngineBundle) -> None:
    pass


def _make_tfa_lc(
    iid="LC-A1", amount=Decimal("1000000"),
    drawn=Decimal("0"), state=None,
    issue_iso="2026-04-01", expiry_iso="2026-07-01",
):
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state or InstrumentState.ISSUED,
        applicant="Acme Imports", beneficiary="Shanghai Steel",
        issuing_bank="Eco", advising_bank="ABC",
        amount_kes=amount, drawn_amount_kes=drawn,
        currency="KES",
        issue_date=_d.fromisoformat(issue_iso),
        expiry_date=_d.fromisoformat(expiry_iso),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="Steel coils")


# TFA-01 CCF + capital impact
def _actions_tfa_capital(engines: EngineBundle) -> None:
    from utils.trade_finance_accounting import (
        TradeFinanceAccountingEngine)
    eng = TradeFinanceAccountingEngine()
    inst = _make_tfa_lc(amount=Decimal("1000000"))
    engines["__tfa01_ccf__"] = eng.compute_ccf(inst)
    engines["__tfa01_impact__"] = eng.compute_capital_impact(
        inst, risk_weight=Decimal("1.00"))


def _assertions_tfa_capital(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_accounting import (
        BaselCcfBucket)
    ccf = engines.get("__tfa01_ccf__")
    impact = engines.get("__tfa01_impact__")
    if ccf is None or impact is None:
        return (AssertionResult(
            assertion_id="tfa01-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfa01-a1",
            description=(
                "Short-tenor LC: CCF 0.20 per Basel III"),
            expected="0.20",
            observed=str(ccf.ccf),
            matched=ccf.ccf == Decimal("0.20")),
        AssertionResult(
            assertion_id="tfa01-a2",
            description=(
                "Bucket = DOCUMENTARY_LC_SHORT (≤365d)"),
            expected=BaselCcfBucket.DOCUMENTARY_LC_SHORT.value,
            observed=ccf.bucket.value,
            matched=(
                ccf.bucket
                == BaselCcfBucket.DOCUMENTARY_LC_SHORT)),
        AssertionResult(
            assertion_id="tfa01-a3",
            description=(
                "Credit equivalent: 1m × 0.20 = 200k"),
            expected="200000.00",
            observed=str(ccf.credit_equivalent_kes),
            matched=(
                ccf.credit_equivalent_kes
                == Decimal("200000.00"))),
        AssertionResult(
            assertion_id="tfa01-a4",
            description=(
                "Capital required: 200k × 100% RW × 8% = 16k"),
            expected="16000.00",
            observed=str(impact.capital_required_kes),
            matched=(
                impact.capital_required_kes
                == Decimal("16000.00"))),
    )


SCENARIO_TFA_01_CAPITAL = Scenario(
    scenario_id="TFA-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-275 capital impact for short-tenor LC: 1m "
        "notional × CCF 0.20 = 200k credit equivalent; × "
        "100% risk weight = 200k RWA; × 8% Basel minimum = "
        "16k capital required. Per Rule 7, risk_weight is "
        "operator-supplied; engine never derives risk weights."),
    setup=_setup_tfa,
    actions=_actions_tfa_capital,
    assertions=_assertions_tfa_capital,
    requires_engines=("trade_finance_accounting",))


# TFA-02 journal templates lifecycle
def _actions_tfa_journals(engines: EngineBundle) -> None:
    from utils.trade_finance_accounting import (
        TradeFinanceAccountingEngine, JournalEvent)
    eng = TradeFinanceAccountingEngine()
    inst = _make_tfa_lc(amount=Decimal("1000000"))
    engines["__tfa02_issue__"] = (
        eng.generate_journal_template(
            inst, JournalEvent.ISSUE,
            posting_date_iso="2026-04-01",
            fee_kes=Decimal("5000")))
    engines["__tfa02_drawdown__"] = (
        eng.generate_journal_template(
            inst, JournalEvent.DRAWDOWN,
            posting_date_iso="2026-05-15"))
    engines["__tfa02_expire__"] = (
        eng.generate_journal_template(
            inst, JournalEvent.EXPIRE,
            posting_date_iso="2026-07-01"))


def _assertions_tfa_journals(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_accounting import (
        TradeFinanceAccountingEngine, BalanceCheckOutcome)
    issue = engines.get("__tfa02_issue__")
    draw = engines.get("__tfa02_drawdown__")
    expire = engines.get("__tfa02_expire__")
    if issue is None or draw is None or expire is None:
        return (AssertionResult(
            assertion_id="tfa02-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    eng_chk = TradeFinanceAccountingEngine()
    bal_all = eng_chk.validate_journal_balance(
        (issue, draw, expire))
    return (
        AssertionResult(
            assertion_id="tfa02-a1",
            description=(
                "ISSUE has 4 lines (contingent DR/CR + "
                "fee DR/CR)"),
            expected="4",
            observed=str(len(issue.lines)),
            matched=len(issue.lines) == 4),
        AssertionResult(
            assertion_id="tfa02-a2",
            description=(
                "DRAWDOWN has 4 lines (receivable + cash "
                "+ contingent reversal)"),
            expected="4",
            observed=str(len(draw.lines)),
            matched=len(draw.lines) == 4),
        AssertionResult(
            assertion_id="tfa02-a3",
            description=(
                "EXPIRE has 2 lines (contingent reversal "
                "DR/CR only)"),
            expected="2",
            observed=str(len(expire.lines)),
            matched=len(expire.lines) == 2),
        AssertionResult(
            assertion_id="tfa02-a4",
            description=(
                "All 3 templates balance — DR sum == CR sum"),
            expected=BalanceCheckOutcome.BALANCED.value,
            observed=bal_all.outcome.value,
            matched=(
                bal_all.outcome == BalanceCheckOutcome.BALANCED)),
    )


SCENARIO_TFA_02_JOURNALS = Scenario(
    scenario_id="TFA-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-275 journal lifecycle: ISSUE (4 lines: "
        "contingent + fee) → DRAWDOWN (4 lines: receivable "
        "+ cash + contingent reversal) → EXPIRE (2 lines: "
        "contingent reversal). All 3 templates balance per "
        "double-entry invariant. Per Rule 7, engine "
        "generates templates only — operator reviews + "
        "posts via core banking."),
    setup=_setup_tfa,
    actions=_actions_tfa_journals,
    assertions=_assertions_tfa_journals,
    requires_engines=("trade_finance_accounting",))


# TFA-03 unbalanced detection
def _actions_tfa_unbalanced(engines: EngineBundle) -> None:
    from utils.trade_finance_accounting import (
        TradeFinanceAccountingEngine, JournalTemplate,
        JournalLine, JournalEvent, JournalSide,
        AccountClass)
    from utils.trade_finance_instruments import InstrumentType
    bad = JournalTemplate(
        instrument_id="X", instrument_type=InstrumentType.LC,
        event=JournalEvent.ISSUE,
        lines=(
            JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label="x", side=JournalSide.DEBIT,
                amount_kes=Decimal("1000"), description="x"),
            JournalLine(
                account_class=AccountClass.CONTINGENT_LIABILITY,
                account_label="y", side=JournalSide.CREDIT,
                amount_kes=Decimal("900"), description="y"),
        ),
        notional_kes=Decimal("1000"),
        posting_date="2026-01-01",
        framework_refs=())
    eng = TradeFinanceAccountingEngine()
    engines["__tfa03__"] = eng.validate_journal_balance((bad,))


def _assertions_tfa_unbalanced(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_accounting import (
        BalanceCheckOutcome)
    bal = engines.get("__tfa03__")
    if bal is None:
        return (AssertionResult(
            assertion_id="tfa03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfa03-a1",
            description=(
                "Unbalanced template: outcome UNBALANCED"),
            expected=BalanceCheckOutcome.UNBALANCED.value,
            observed=bal.outcome.value,
            matched=(
                bal.outcome
                == BalanceCheckOutcome.UNBALANCED)),
        AssertionResult(
            assertion_id="tfa03-a2",
            description=(
                "Difference 100 KES surfaced exactly"),
            expected="100",
            observed=str(bal.difference_kes),
            matched=bal.difference_kes == Decimal("100")),
        AssertionResult(
            assertion_id="tfa03-a3",
            description="Per Rule 7 — never auto-corrects",
            expected="Rule 7 in framework_refs",
            observed=" / ".join(bal.framework_refs),
            matched=any(
                "Rule 7" in r for r in bal.framework_refs)),
        AssertionResult(
            assertion_id="tfa03-a4",
            description=(
                "DR + CR totals surfaced for triage"),
            expected="DR=1000 CR=900",
            observed=(
                f"DR={bal.total_debit_kes} "
                f"CR={bal.total_credit_kes}"),
            matched=(
                bal.total_debit_kes == Decimal("1000")
                and bal.total_credit_kes == Decimal("900"))),
    )


SCENARIO_TFA_03_UNBALANCED = Scenario(
    scenario_id="TFA-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-275 validate_journal_balance on deliberately "
        "unbalanced template (DR 1000, CR 900) → outcome "
        "UNBALANCED, difference 100 KES surfaced exactly. "
        "Per Rule 7, engine never auto-corrects; surfaces "
        "imbalance for operator triage."),
    setup=_setup_tfa,
    actions=_actions_tfa_unbalanced,
    assertions=_assertions_tfa_unbalanced,
    requires_engines=("trade_finance_accounting",))


# TFA-04 off-balance-sheet disclosure
def _actions_tfa_disclosure(engines: EngineBundle) -> None:
    from utils.trade_finance_accounting import (
        TradeFinanceAccountingEngine)
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        BgType)
    from datetime import date as _d
    eng = TradeFinanceAccountingEngine()
    insts = (
        _make_tfa_lc(
            iid="L1", state=InstrumentState.ISSUED,
            amount=Decimal("1000000")),
        _make_tfa_lc(
            iid="L2", state=InstrumentState.EXPIRED,
            amount=Decimal("500000")),    # excluded
        TradeInstrument(
            instrument_id="BG1",
            instrument_type=InstrumentType.BG,
            state=InstrumentState.ISSUED,
            applicant="A", beneficiary="KRA",
            issuing_bank="Eco", advising_bank=None,
            amount_kes=Decimal("2000000"), currency="KES",
            issue_date=_d(2026, 4, 1),
            expiry_date=_d(2026, 10, 1),
            tenor_days=0, bg_type=BgType.PERFORMANCE),
    )
    engines["__tfa04__"] = (
        eng.build_off_balance_sheet_disclosure(
            insts, as_of_date_iso="2026-04-15"))


def _assertions_tfa_disclosure(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    d = engines.get("__tfa04__")
    if d is None:
        return (AssertionResult(
            assertion_id="tfa04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="tfa04-a1",
            description=(
                "EXPIRED instrument excluded from "
                "disclosure (only ISSUED/AMENDED/ACTIVE "
                "counted)"),
            expected="2 instruments counted",
            observed=str(d.instrument_count),
            matched=d.instrument_count == 2),
        AssertionResult(
            assertion_id="tfa04-a2",
            description=(
                "Total notional: 1m LC + 2m BG = 3m "
                "(EXPIRED 500k excluded)"),
            expected="3000000",
            observed=str(d.total_notional_kes),
            matched=(
                d.total_notional_kes == Decimal("3000000"))),
        AssertionResult(
            assertion_id="tfa04-a3",
            description=(
                "Credit equivalent: 1m × 0.20 + 2m × "
                "0.50 = 1.2m"),
            expected="1200000.00",
            observed=str(d.total_credit_equivalent_kes),
            matched=(
                d.total_credit_equivalent_kes
                == Decimal("1200000.00"))),
        AssertionResult(
            assertion_id="tfa04-a4",
            description=(
                "IAS 37 + IFRS 7 cited in framework refs"),
            expected="IAS 37 + IFRS 7",
            observed=" / ".join(d.framework_refs),
            matched=(
                any("IAS 37" in r for r in d.framework_refs)
                and any(
                    "IFRS 7" in r for r in d.framework_refs))),
    )


SCENARIO_TFA_04_DISCLOSURE = Scenario(
    scenario_id="TFA-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-275 IAS 37 off-balance-sheet disclosure for 3 "
        "instruments (1m ISSUED LC + 500k EXPIRED LC + 2m "
        "ISSUED BG): EXPIRED excluded, total notional 3m, "
        "credit equivalent 1.2m (1m×0.20 + 2m×0.50). IAS "
        "37 + IFRS 7 cited per Rule 1."),
    setup=_setup_tfa,
    actions=_actions_tfa_disclosure,
    assertions=_assertions_tfa_disclosure,
    requires_engines=("trade_finance_accounting",))


# ════════════════════════════════════════════════════════════════════════
# v10.76 — Trade Finance Reporting & Analytics (ENH-280) — ML-extensible
# ════════════════════════════════════════════════════════════════════════

def _setup_rpt(engines: EngineBundle) -> None:
    pass


def _make_rpt_lc(
    iid, applicant="A", beneficiary="B",
    amount=Decimal("1000000"),
    state=None,
):
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state or InstrumentState.ACTIVE,
        applicant=applicant, beneficiary=beneficiary,
        issuing_bank="Eco", advising_bank="ABC",
        amount_kes=amount, currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 8, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="goods")


# RPT-01 volumes + country exposure
def _actions_rpt_volumes(engines: EngineBundle) -> None:
    from utils.trade_finance_reporting import (
        TradeFinanceReportingEngine)
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_rpt_lc(
            "L1", "A", "ChinaCorp", Decimal("3000000")),
        _make_rpt_lc(
            "L2", "A", "ChinaCorp", Decimal("2000000")),
        _make_rpt_lc(
            "L3", "B", "GermanCorp", Decimal("5000000")),
    )
    attrib = {"ChinaCorp": "CN", "GermanCorp": "DE"}
    engines["__rpt01_vol__"] = eng.compute_trade_volumes(
        insts, "2026-Q2", country_attribution=attrib)
    engines["__rpt01_country__"] = (
        eng.compute_country_exposure(
            insts, attrib, as_of_date_iso="2026-04-15"))


def _assertions_rpt_volumes(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_reporting import (
        ConcentrationSeverity)
    vol = engines.get("__rpt01_vol__")
    exp = engines.get("__rpt01_country__")
    if vol is None or exp is None:
        return (AssertionResult(
            assertion_id="rpt01-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rpt01-a1",
            description="Total volume 10m KES",
            expected="10000000",
            observed=str(vol.total_kes),
            matched=vol.total_kes == Decimal("10000000")),
        AssertionResult(
            assertion_id="rpt01-a2",
            description=(
                "By country: CN 5m, DE 5m"),
            expected="CN=5m DE=5m",
            observed=str(dict(vol.by_country)),
            matched=(
                vol.by_country.get("CN") == Decimal("5000000")
                and vol.by_country.get("DE") == Decimal(
                    "5000000"))),
        AssertionResult(
            assertion_id="rpt01-a3",
            description=(
                "Country HHI: 2 equal countries → 0.5 → "
                "CONCENTRATED"),
            expected=(
                ConcentrationSeverity.CONCENTRATED.value),
            observed=exp.severity.value,
            matched=(
                exp.severity
                == ConcentrationSeverity.CONCENTRATED)),
        AssertionResult(
            assertion_id="rpt01-a4",
            description=(
                "HHI numeric value 0.5"),
            expected="0.5",
            observed=str(exp.herfindahl_index),
            matched=(
                abs(exp.herfindahl_index - Decimal("0.5"))
                < Decimal("0.001"))),
    )


SCENARIO_RPT_01_VOLUMES = Scenario(
    scenario_id="RPT-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-280 volumes + country exposure: 3 LCs totaling "
        "10m KES across 2 countries (CN 5m, DE 5m). HHI = "
        "0.5² + 0.5² = 0.5 → CONCENTRATED severity (>0.25 "
        "threshold). Validates HHI computation + 3-tier "
        "ConcentrationSeverity ladder."),
    setup=_setup_rpt,
    actions=_actions_rpt_volumes,
    assertions=_assertions_rpt_volumes,
    requires_engines=("trade_finance_reporting",))


# RPT-02 anomaly detection statistical fallback (ml_disabled=True)
def _actions_rpt_anomaly_fallback(
    engines: EngineBundle,
) -> None:
    from utils.trade_finance_reporting import (
        TradeFinanceReportingEngine)
    eng = TradeFinanceReportingEngine()    # no ML hook
    history = [
        Decimal("1000000"), Decimal("1100000"),
        Decimal("950000"), Decimal("1050000"),
        Decimal("980000"), Decimal("1020000"),
        Decimal("1030000"), Decimal("970000"),
        Decimal("990000"),
        Decimal("10000000"),    # 10x spike
    ]
    labels = [f"P{i}" for i in range(len(history))]
    engines["__rpt02__"] = eng.detect_volume_anomalies(
        history, labels)


def _assertions_rpt_anomaly_fallback(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_reporting import (
        AnalysisMethod, AnomalySeverity)
    findings = engines.get("__rpt02__")
    if findings is None:
        return (AssertionResult(
            assertion_id="rpt02-a0",
            description="Findings populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rpt02-a1",
            description=(
                "Spike at P9 detected (≥1 finding)"),
            expected="≥ 1 finding",
            observed=str(len(findings)),
            matched=len(findings) >= 1),
        AssertionResult(
            assertion_id="rpt02-a2",
            description=(
                "Per Rule 6 — ml_disabled=True for fallback"),
            expected="all True",
            observed=str(
                [f.ml_disabled for f in findings]),
            matched=all(
                f.ml_disabled is True for f in findings)),
        AssertionResult(
            assertion_id="rpt02-a3",
            description=(
                "Method = STATISTICAL_FALLBACK"),
            expected=(
                AnalysisMethod.STATISTICAL_FALLBACK.value),
            observed=(
                findings[0].method.value
                if findings else "n/a"),
            matched=(
                len(findings) > 0
                and findings[0].method
                == AnalysisMethod.STATISTICAL_FALLBACK)),
        AssertionResult(
            assertion_id="rpt02-a4",
            description=(
                "Spike P9 flagged WATCH or ALERT severity"),
            expected="WATCH or ALERT",
            observed=", ".join(
                f"{f.period_label}:{f.severity.value}"
                for f in findings),
            matched=any(
                f.period_label == "P9"
                and f.severity in (
                    AnomalySeverity.WATCH,
                    AnomalySeverity.ALERT)
                for f in findings)),
    )


SCENARIO_RPT_02_ANOMALY_FALLBACK = Scenario(
    scenario_id="RPT-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-280 detect_volume_anomalies WITHOUT ML hook "
        "(no scorer injected): 10x spike at P9 against 9 "
        "normal periods → flagged via Modified Z-score on "
        "log-volume statistical fallback. Per Rule 6, every "
        "finding carries ml_disabled=True; method = "
        "STATISTICAL_FALLBACK. Per Rule 7, surfaces for "
        "operator adjudication only."),
    setup=_setup_rpt,
    actions=_actions_rpt_anomaly_fallback,
    assertions=_assertions_rpt_anomaly_fallback,
    requires_engines=("trade_finance_reporting",))


# RPT-03 ML hook injected — anomaly path
def _actions_rpt_ml_hook(engines: EngineBundle) -> None:
    from utils.trade_finance_reporting import (
        TradeFinanceReportingEngine)

    # Fake "trained" ML scorer always flags everything as ALERT
    def fake_ml_scorer(values):
        return [0.95] * len(values)

    eng = TradeFinanceReportingEngine(
        ml_anomaly_scorer=fake_ml_scorer)
    history = [Decimal("1000000")] * 5
    labels = [f"P{i}" for i in range(5)]
    engines["__rpt03__"] = eng.detect_volume_anomalies(
        history, labels)


def _assertions_rpt_ml_hook(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_reporting import (
        AnalysisMethod, AnomalySeverity)
    findings = engines.get("__rpt03__")
    if findings is None:
        return (AssertionResult(
            assertion_id="rpt03-a0",
            description="Findings populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rpt03-a1",
            description=(
                "ML hook used → 5 ALERT findings (every "
                "period scored 0.95 ≥ 0.75 threshold)"),
            expected="5 ALERT",
            observed=f"{len(findings)} findings",
            matched=(
                len(findings) == 5
                and all(
                    f.severity == AnomalySeverity.ALERT
                    for f in findings))),
        AssertionResult(
            assertion_id="rpt03-a2",
            description=(
                "Per Rule 6 — ml_disabled=False when hook "
                "succeeds"),
            expected="all False",
            observed=str(
                [f.ml_disabled for f in findings]),
            matched=all(
                f.ml_disabled is False for f in findings)),
        AssertionResult(
            assertion_id="rpt03-a3",
            description=(
                "Method = ML_INJECTED"),
            expected=AnalysisMethod.ML_INJECTED.value,
            observed=(
                findings[0].method.value
                if findings else "n/a"),
            matched=(
                len(findings) > 0
                and findings[0].method
                == AnalysisMethod.ML_INJECTED)),
        AssertionResult(
            assertion_id="rpt03-a4",
            description=(
                "Score 0.95 surfaced exactly per Rule 1"),
            expected="0.95",
            observed=(
                str(findings[0].score) if findings else "n/a"),
            matched=(
                len(findings) > 0
                and abs(findings[0].score - 0.95) < 0.001)),
    )


SCENARIO_RPT_03_ML_HOOK = Scenario(
    scenario_id="RPT-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-280 detect_volume_anomalies WITH injected ML "
        "scorer: every period scored 0.95 → 5 ALERT findings "
        "(0.95 ≥ 0.75 threshold). Per Rule 6, ml_disabled = "
        "False when hook succeeds; method = ML_INJECTED. "
        "Demonstrates the accuracy-improvement path: when "
        "trained ML model is injected, engine consumes its "
        "scores and surfaces them with full provenance."),
    setup=_setup_rpt,
    actions=_actions_rpt_ml_hook,
    assertions=_assertions_rpt_ml_hook,
    requires_engines=("trade_finance_reporting",))


# RPT-04 forecasting fallback + management report orchestrator
def _actions_rpt_forecast(engines: EngineBundle) -> None:
    from utils.trade_finance_reporting import (
        TradeFinanceReportingEngine)
    eng = TradeFinanceReportingEngine()
    insts = (
        _make_rpt_lc(
            "L1", "AcmeOil", "ChinaCorp", Decimal("3000000")),
        _make_rpt_lc(
            "L2", "Biotech", "GermanCorp",
            Decimal("7000000")),
    )
    country_attr = {
        "ChinaCorp": "CN", "GermanCorp": "DE"}
    sector_attr = {
        "AcmeOil": "ENERGY", "Biotech": "PHARMA"}
    history = [
        Decimal(str(1000000 * (i + 1))) for i in range(8)]
    labels = [f"P{i}" for i in range(8)]
    engines["__rpt04__"] = eng.build_management_report(
        insts, period_label="P9",
        as_of_date_iso="2026-04-15",
        country_attribution=country_attr,
        sector_attribution=sector_attr,
        history_for_anomaly=(history, labels),
        forecast_horizon=3)


def _assertions_rpt_forecast(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_reporting import AnalysisMethod
    report = engines.get("__rpt04__")
    if report is None:
        return (AssertionResult(
            assertion_id="rpt04-a0",
            description="Report populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rpt04-a1",
            description=(
                "Volume aggregation + country exposure + "
                "sector concentration + forecast all "
                "populated"),
            expected="all 4 sections present",
            observed=(
                f"vol={report.volume_aggregation is not None} "
                f"country={report.country_exposure is not None} "
                f"sector={report.sector_concentration is not None} "
                f"fcst={report.forecast is not None}"),
            matched=(
                report.volume_aggregation is not None
                and report.country_exposure is not None
                and report.sector_concentration is not None
                and report.forecast is not None)),
        AssertionResult(
            assertion_id="rpt04-a2",
            description=(
                "Forecast linear-extrapolated: 8 increasing "
                "periods → ~9m next"),
            expected="forecast[0] ≈ 9m",
            observed=(
                str(report.forecast.forecast_values_kes[0])
                if report.forecast else "n/a"),
            matched=(
                report.forecast is not None
                and report.forecast.forecast_values_kes[0]
                > Decimal("8000000")
                and report.forecast.forecast_values_kes[0]
                < Decimal("10000000"))),
        AssertionResult(
            assertion_id="rpt04-a3",
            description=(
                "Forecast method = STATISTICAL_FALLBACK; "
                "ml_disabled=True"),
            expected="fallback + ml_disabled",
            observed=(
                f"{report.forecast.method.value} "
                f"ml_disabled={report.forecast.ml_disabled}"
                if report.forecast else "n/a"),
            matched=(
                report.forecast is not None
                and report.forecast.method
                == AnalysisMethod.STATISTICAL_FALLBACK
                and report.forecast.ml_disabled is True)),
        AssertionResult(
            assertion_id="rpt04-a4",
            description=(
                "Overall ml_disabled=True (no ML hooks "
                "injected)"),
            expected="True",
            observed=str(report.overall_ml_disabled),
            matched=report.overall_ml_disabled is True),
    )


SCENARIO_RPT_04_MGMT_REPORT = Scenario(
    scenario_id="RPT-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-280 build_management_report orchestrator: 2 "
        "LCs (10m total) + 8-period history (1m..8m linear) "
        "+ 3-period forecast horizon. All 4 sections "
        "populated (volumes, country, sector, forecast). "
        "OLS forecast on linearly-increasing history → next "
        "period ~9m. overall_ml_disabled=True since no ML "
        "hooks injected."),
    setup=_setup_rpt,
    actions=_actions_rpt_forecast,
    assertions=_assertions_rpt_forecast,
    requires_engines=("trade_finance_reporting",))


# ════════════════════════════════════════════════════════════════════════
# v10.77 — Sustainable Trade Finance (ENH-278)
# ════════════════════════════════════════════════════════════════════════

def _setup_sus(engines: EngineBundle) -> None:
    pass


def _make_sus_inst(
    iid="LC-S1", goods="goods", applicant="A", beneficiary="B",
    amount=Decimal("1000000"), state=None,
):
    from datetime import date as _d
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state or InstrumentState.ACTIVE,
        applicant=applicant, beneficiary=beneficiary,
        issuing_bank="Eco", advising_bank="ABC",
        amount_kes=amount, currency="KES",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 8, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods=goods)


def _sus_taxonomy():
    from utils.trade_finance_sustainability import (
        TaxonomyEntry, SustainabilityTier)
    return (
        TaxonomyEntry(
            keyword="solar",
            tier=SustainabilityTier.GREEN,
            source="KGFT 2025 §3.2",
            justification="Renewable energy"),
        TaxonomyEntry(
            keyword="natural gas",
            tier=SustainabilityTier.TRANSITION,
            source="EU Taxonomy",
            justification="Transition fuel"),
        TaxonomyEntry(
            keyword="thermal coal",
            tier=SustainabilityTier.BROWN,
            source="KBA SFI",
            justification="Phase-out"),
        TaxonomyEntry(
            keyword="coal",
            tier=SustainabilityTier.BROWN,
            source="KGFT",
            justification="Misaligned"),
    )


def _sus_exclusion():
    from utils.trade_finance_sustainability import (
        ExclusionEntry, ExclusionSeverity)
    return (
        ExclusionEntry(
            keyword="thermal coal",
            severity=ExclusionSeverity.HIGH,
            source="KBA SFI 2024",
            justification="Coal phase-out"),
        ExclusionEntry(
            keyword="weapons",
            severity=ExclusionSeverity.CRITICAL,
            source="Internal policy",
            justification="Absolute prohibition"),
    )


# SUS-01 — green classification
def _actions_sus_green(engines: EngineBundle) -> None:
    from utils.trade_finance_sustainability import (
        TradeFinanceSustainabilityEngine)
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_sus_inst(
        goods="50 megawatt solar farm panels and inverters")
    engines["__sus01__"] = (
        eng.classify_instrument_sustainability(
            inst, _sus_taxonomy()))


def _assertions_sus_green(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_sustainability import (
        SustainabilityTier)
    cls = engines.get("__sus01__")
    if cls is None:
        return (AssertionResult(
            assertion_id="sus01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="sus01-a1",
            description=(
                "Solar PV equipment → primary_tier GREEN"),
            expected=SustainabilityTier.GREEN.value,
            observed=cls.primary_tier.value,
            matched=(
                cls.primary_tier
                == SustainabilityTier.GREEN)),
        AssertionResult(
            assertion_id="sus01-a2",
            description=(
                "Single match: 'solar' keyword"),
            expected="1 match",
            observed=f"{len(cls.all_matches)} matches",
            matched=len(cls.all_matches) == 1),
        AssertionResult(
            assertion_id="sus01-a3",
            description=(
                "Not conflicting (only GREEN signals)"),
            expected="False",
            observed=str(cls.conflicting),
            matched=cls.conflicting is False),
        AssertionResult(
            assertion_id="sus01-a4",
            description=(
                "KGFT cited in framework_refs per Rule 1"),
            expected="KGFT in refs",
            observed=" / ".join(cls.framework_refs),
            matched=any(
                "KGFT" in r for r in cls.framework_refs)),
    )


SCENARIO_SUS_01_GREEN = Scenario(
    scenario_id="SUS-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-278 classify_instrument_sustainability on solar "
        "PV equipment LC against KGFT 2025 §3.2 taxonomy → "
        "primary_tier GREEN, single 'solar' match, no "
        "conflict. KGFT cited in framework_refs per Rule 1."),
    setup=_setup_sus,
    actions=_actions_sus_green,
    assertions=_assertions_sus_green,
    requires_engines=("trade_finance_sustainability",))


# SUS-02 — brown + exclusion hit
def _actions_sus_brown(engines: EngineBundle) -> None:
    from utils.trade_finance_sustainability import (
        TradeFinanceSustainabilityEngine)
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_sus_inst(goods="thermal coal cargo shipment")
    engines["__sus02_cls__"] = (
        eng.classify_instrument_sustainability(
            inst, _sus_taxonomy()))
    engines["__sus02_exc__"] = (
        eng.screen_exclusion_list(inst, _sus_exclusion()))


def _assertions_sus_brown(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_sustainability import (
        SustainabilityTier, ExclusionSeverity,
        SustainabilityScreeningOutcome)
    cls = engines.get("__sus02_cls__")
    exc = engines.get("__sus02_exc__")
    if cls is None or exc is None:
        return (AssertionResult(
            assertion_id="sus02-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="sus02-a1",
            description=(
                "Thermal coal → primary_tier BROWN"),
            expected=SustainabilityTier.BROWN.value,
            observed=cls.primary_tier.value,
            matched=(
                cls.primary_tier
                == SustainabilityTier.BROWN)),
        AssertionResult(
            assertion_id="sus02-a2",
            description=(
                "Two BROWN matches: 'thermal coal' + 'coal'"),
            expected="2 matches",
            observed=f"{len(cls.all_matches)} matches",
            matched=len(cls.all_matches) == 2),
        AssertionResult(
            assertion_id="sus02-a3",
            description=(
                "Exclusion HIGH severity hit on thermal coal"),
            expected="HIGH severity hit",
            observed=", ".join(
                f"{h.matched_keyword}:{h.severity.value}"
                for h in exc.hits),
            matched=any(
                h.severity == ExclusionSeverity.HIGH
                for h in exc.hits)),
        AssertionResult(
            assertion_id="sus02-a4",
            description=(
                "Outcome SENIOR_APPROVAL (HIGH not CRITICAL)"),
            expected=(
                SustainabilityScreeningOutcome.SENIOR_APPROVAL
                .value),
            observed=exc.outcome.value,
            matched=(
                exc.outcome
                == SustainabilityScreeningOutcome
                .SENIOR_APPROVAL)),
    )


SCENARIO_SUS_02_BROWN = Scenario(
    scenario_id="SUS-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-278 thermal coal LC: classify → BROWN with 2 "
        "matches ('thermal coal' + 'coal' both BROWN, no "
        "conflict); screen → HIGH-severity exclusion hit → "
        "outcome SENIOR_APPROVAL. Per Rule 7, engine "
        "surfaces hit + outcome; operator decides whether "
        "to proceed."),
    setup=_setup_sus,
    actions=_actions_sus_brown,
    assertions=_assertions_sus_brown,
    requires_engines=("trade_finance_sustainability",))


# SUS-03 — GHG attribution
def _actions_sus_ghg(engines: EngineBundle) -> None:
    from utils.trade_finance_sustainability import (
        TradeFinanceSustainabilityEngine)
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_sus_inst(
        applicant="EnergyCo",
        amount=Decimal("10000000"))
    sector_map = {"EnergyCo": "ENERGY_FOSSIL"}
    factors = {"ENERGY_FOSSIL": Decimal("0.50")}
    engines["__sus03_attr__"] = eng.compute_ghg_attribution(
        inst, sector_map, factors)
    # Also test FACTOR_UNKNOWN path
    engines["__sus03_unknown__"] = eng.compute_ghg_attribution(
        inst, {"EnergyCo": "OBSCURE"}, factors)


def _assertions_sus_ghg(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_sustainability import (
        GhgAttributionStatus)
    attr = engines.get("__sus03_attr__")
    unk = engines.get("__sus03_unknown__")
    if attr is None or unk is None:
        return (AssertionResult(
            assertion_id="sus03-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="sus03-a1",
            description=(
                "PCAF attribution: 10m KES × 0.50 kg CO2e/KES "
                "= 5m kg CO2e"),
            expected="5000000.00",
            observed=str(
                attr.attributed_emissions_kgco2e),
            matched=(
                attr.attributed_emissions_kgco2e
                == Decimal("5000000.00"))),
        AssertionResult(
            assertion_id="sus03-a2",
            description=(
                "Status ATTRIBUTED for known sector + "
                "factor"),
            expected=(
                GhgAttributionStatus.ATTRIBUTED.value),
            observed=attr.status.value,
            matched=(
                attr.status
                == GhgAttributionStatus.ATTRIBUTED)),
        AssertionResult(
            assertion_id="sus03-a3",
            description=(
                "FACTOR_UNKNOWN surfaces gap rather than "
                "fabricating zero (Rule 1)"),
            expected=(
                GhgAttributionStatus.FACTOR_UNKNOWN.value),
            observed=unk.status.value,
            matched=(
                unk.status
                == GhgAttributionStatus.FACTOR_UNKNOWN
                and unk.attributed_emissions_kgco2e is None)),
        AssertionResult(
            assertion_id="sus03-a4",
            description=(
                "PCAF + TCFD cited in framework_refs"),
            expected="PCAF + TCFD",
            observed=" / ".join(attr.framework_refs),
            matched=(
                any("PCAF" in r for r in attr.framework_refs)
                and any(
                    "TCFD" in r for r in attr.framework_refs))),
    )


SCENARIO_SUS_03_GHG = Scenario(
    scenario_id="SUS-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-278 compute_ghg_attribution: 10m KES energy "
        "fossil sector × 0.50 kg CO2e/KES emission factor → "
        "5m kg CO2e attributed. Pair test for FACTOR_UNKNOWN: "
        "engine surfaces gap (status FACTOR_UNKNOWN, "
        "emissions None) rather than fabricating zero. PCAF + "
        "TCFD framework_refs per Rule 1."),
    setup=_setup_sus,
    actions=_actions_sus_ghg,
    assertions=_assertions_sus_ghg,
    requires_engines=("trade_finance_sustainability",))


# SUS-04 — portfolio sustainability report
def _actions_sus_report(engines: EngineBundle) -> None:
    from utils.trade_finance_sustainability import (
        TradeFinanceSustainabilityEngine, EsgRiskTier)
    eng = TradeFinanceSustainabilityEngine()
    insts = (
        _make_sus_inst(
            iid="L1", goods="solar farm equipment",
            applicant="GreenCo",
            amount=Decimal("5000000")),
        _make_sus_inst(
            iid="L2", goods="thermal coal cargo",
            applicant="CoalCo",
            amount=Decimal("3000000")),
        _make_sus_inst(
            iid="L3", goods="bulk cement",
            applicant="CementCo",
            amount=Decimal("2000000")),
    )
    sector_map = {
        "GreenCo": "ENERGY_RENEWABLE",
        "CoalCo": "ENERGY_FOSSIL",
        "CementCo": "INDUSTRIAL"}
    factors = {
        "ENERGY_RENEWABLE": Decimal("0.05"),
        "ENERGY_FOSSIL": Decimal("0.50"),
        "INDUSTRIAL": Decimal("0.20")}
    esg = {
        "GreenCo": EsgRiskTier.LOW,
        "CoalCo": EsgRiskTier.HIGH,
        "CementCo": EsgRiskTier.MEDIUM,
        "B": EsgRiskTier.LOW}
    engines["__sus04__"] = (
        eng.build_sustainability_report(
            insts, as_of_date_iso="2026-04-15",
            taxonomy=_sus_taxonomy(),
            exclusion_list=_sus_exclusion(),
            sector_attribution=sector_map,
            emission_factors=factors,
            esg_attribution=esg))


def _assertions_sus_report(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_sustainability import (
        SustainabilityTier)
    r = engines.get("__sus04__")
    if r is None:
        return (AssertionResult(
            assertion_id="sus04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="sus04-a1",
            description=(
                "Tier shares: GREEN 0.5 (5m/10m), BROWN 0.3, "
                "UNCLASSIFIED 0.2"),
            expected="green=0.5 brown=0.3 unc=0.2",
            observed=(
                f"green={r.by_tier_share[SustainabilityTier.GREEN.value]} "
                f"brown={r.by_tier_share[SustainabilityTier.BROWN.value]} "
                f"unc={r.by_tier_share[SustainabilityTier.UNCLASSIFIED.value]}"),
            matched=(
                r.by_tier_share[SustainabilityTier.GREEN.value]
                == Decimal("0.5000")
                and r.by_tier_share[SustainabilityTier.BROWN.value]
                == Decimal("0.3000")
                and r.by_tier_share[SustainabilityTier.UNCLASSIFIED.value]
                == Decimal("0.2000"))),
        AssertionResult(
            assertion_id="sus04-a2",
            description=(
                "Total emissions: 5m×0.05 + 3m×0.50 + "
                "2m×0.20 = 250k + 1.5m + 400k = 2.15m"),
            expected="2150000.00",
            observed=str(
                r.total_attributed_emissions_kgco2e),
            matched=(
                r.total_attributed_emissions_kgco2e
                == Decimal("2150000.00"))),
        AssertionResult(
            assertion_id="sus04-a3",
            description=(
                "Top emitting sector ENERGY_FOSSIL "
                "(1.5m kg CO2e)"),
            expected="ENERGY_FOSSIL",
            observed=str(r.top_emitting_sectors),
            matched=(
                len(r.top_emitting_sectors) > 0
                and r.top_emitting_sectors[0][0]
                == "ENERGY_FOSSIL")),
        AssertionResult(
            assertion_id="sus04-a4",
            description=(
                "Exclusion: 1 HIGH hit (thermal coal); 0 "
                "CRITICAL"),
            expected=(
                "exclusion_hits>=1 critical=0"),
            observed=(
                f"hits={r.exclusion_hit_count} "
                f"critical={r.exclusion_critical_count}"),
            matched=(
                r.exclusion_hit_count >= 1
                and r.exclusion_critical_count == 0)),
    )


SCENARIO_SUS_04_REPORT = Scenario(
    scenario_id="SUS-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-278 build_sustainability_report on 3-LC "
        "portfolio (5m green solar + 3m brown coal + 2m "
        "unclassified cement): tier shares 0.5/0.3/0.2, "
        "total PCAF emissions 2.15m kg CO2e (250k + 1.5m + "
        "400k), top emitting sector ENERGY_FOSSIL, 1 HIGH "
        "exclusion hit + 0 CRITICAL. Mixed-portfolio "
        "orchestrator validation."),
    setup=_setup_sus,
    actions=_actions_sus_report,
    assertions=_assertions_sus_report,
    requires_engines=("trade_finance_sustainability",))


# ════════════════════════════════════════════════════════════════════════
# v10.78 — AI-Powered Document Checking (ENH-270) — ML-extensible
# ════════════════════════════════════════════════════════════════════════

def _setup_doc(engines: EngineBundle) -> None:
    pass


def _make_doc_lc(
    ref="LC-DOC-1", amount=Decimal("1000000"),
    expiry=None, latest_shipment=None,
    tolerance=Decimal("0.05"),
    description="50 metric tons milled rice grade A",
):
    from datetime import date as _d
    from utils.trade_finance_document_checking import (
        LCTerms, DocumentType)
    return LCTerms(
        lc_reference=ref, amount_kes=amount, currency="USD",
        expiry_date=expiry or _d(2026, 7, 1),
        latest_shipment_date=(
            latest_shipment or _d(2026, 6, 15)),
        amount_tolerance_pct=tolerance,
        description_of_goods=description,
        port_of_loading="Mombasa, Kenya",
        port_of_discharge="Rotterdam, Netherlands",
        required_documents=(
            DocumentType.COMMERCIAL_INVOICE,
            DocumentType.BILL_OF_LADING),
        applicant="Acme Imports", beneficiary="Rice Co Ltd")


def _make_doc_invoice(
    amount=Decimal("1000000"),
    description="50 metric tons milled rice grade A",
    pol="Mombasa, Kenya",
):
    from datetime import date as _d
    from utils.trade_finance_document_checking import (
        PresentedDocument, DocumentType)
    return PresentedDocument(
        document_type=DocumentType.COMMERCIAL_INVOICE,
        issuer="Rice Co Ltd",
        amount_kes=amount, currency="USD",
        issue_date=_d(2026, 6, 1),
        description_of_goods=description,
        port_of_loading=pol)


def _make_doc_bl(shipment=None, pol="Mombasa, Kenya"):
    from datetime import date as _d
    from utils.trade_finance_document_checking import (
        PresentedDocument, DocumentType)
    return PresentedDocument(
        document_type=DocumentType.BILL_OF_LADING,
        issuer="Maersk",
        shipment_date=shipment or _d(2026, 6, 10),
        port_of_loading=pol,
        port_of_discharge="Rotterdam, Netherlands")


def _make_doc_presentation(
    pid="PR-DOC-1", lc_ref="LC-DOC-1",
    pres_date=None, documents=None,
):
    from datetime import date as _d
    from utils.trade_finance_document_checking import (
        DocumentPresentation)
    return DocumentPresentation(
        presentation_id=pid, lc_reference=lc_ref,
        presentation_date=pres_date or _d(2026, 6, 20),
        documents=tuple(
            documents or [
                _make_doc_invoice(), _make_doc_bl()]))


# DOC-01 — clean conforming presentation, no hooks injected
def _actions_doc_clean(engines: EngineBundle) -> None:
    from utils.trade_finance_document_checking import (
        TradeFinanceDocumentCheckingEngine)
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_doc_lc()
    pres = _make_doc_presentation()
    engines["__doc01__"] = eng.assess_presentation(lc, pres)


def _assertions_doc_clean(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_document_checking import (
        PresentationOutcome)
    a = engines.get("__doc01__")
    if a is None:
        return (AssertionResult(
            assertion_id="doc01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="doc01-a1",
            description=(
                "Clean presentation → CONFORMING outcome"),
            expected=PresentationOutcome.CONFORMING.value,
            observed=a.outcome.value,
            matched=(
                a.outcome == PresentationOutcome.CONFORMING)),
        AssertionResult(
            assertion_id="doc01-a2",
            description="Zero findings",
            expected="0 findings",
            observed=f"{len(a.findings)} findings",
            matched=len(a.findings) == 0),
        AssertionResult(
            assertion_id="doc01-a3",
            description=(
                "overall_ml_disabled=True (no hook injected, "
                "no findings to classify either way)"),
            expected="True",
            observed=str(a.overall_ml_disabled),
            matched=a.overall_ml_disabled is True),
        AssertionResult(
            assertion_id="doc01-a4",
            description=(
                "UCP 600 cited in framework_refs per Rule 1"),
            expected="UCP 600 in refs",
            observed=" / ".join(a.framework_refs),
            matched=any(
                "UCP 600" in r for r in a.framework_refs)),
    )


SCENARIO_DOC_01_CONFORMING = Scenario(
    scenario_id="DOC-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-270 assess_presentation on clean LC drawdown "
        "(invoice + BL match LC terms, all dates within "
        "limits, all required docs present, no cross-doc "
        "conflicts). Outcome CONFORMING, zero findings, "
        "UCP 600 cited per Rule 1."),
    setup=_setup_doc,
    actions=_actions_doc_clean,
    assertions=_assertions_doc_clean,
    requires_engines=("trade_finance_document_checking",))


# DOC-02 — late presentation (after expiry) → CRITICAL → REFUSAL_LIKELY
def _actions_doc_expired(engines: EngineBundle) -> None:
    from utils.trade_finance_document_checking import (
        TradeFinanceDocumentCheckingEngine)
    from datetime import date as _d
    eng = TradeFinanceDocumentCheckingEngine()
    lc = _make_doc_lc(expiry=_d(2026, 6, 1))
    pres = _make_doc_presentation(
        pres_date=_d(2026, 6, 20))    # 19 days late
    engines["__doc02__"] = eng.assess_presentation(lc, pres)


def _assertions_doc_expired(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_document_checking import (
        PresentationOutcome, DiscrepancySeverity,
        CheckCategory, FindingMethod)
    a = engines.get("__doc02__")
    if a is None:
        return (AssertionResult(
            assertion_id="doc02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="doc02-a1",
            description=(
                "Late presentation → DISCREPANT_REFUSAL_"
                "LIKELY"),
            expected=(
                PresentationOutcome.DISCREPANT_REFUSAL_LIKELY
                .value),
            observed=a.outcome.value,
            matched=(
                a.outcome == PresentationOutcome
                .DISCREPANT_REFUSAL_LIKELY)),
        AssertionResult(
            assertion_id="doc02-a2",
            description=(
                "EXPIRY finding present with CRITICAL "
                "severity"),
            expected="EXPIRY + CRITICAL",
            observed=", ".join(
                f"{f.category.value}:{f.severity.value}"
                for f in a.findings),
            matched=any(
                f.category == CheckCategory.EXPIRY
                and f.severity == DiscrepancySeverity.CRITICAL
                for f in a.findings)),
        AssertionResult(
            assertion_id="doc02-a3",
            description=(
                "Per Rule 6 — ml_disabled=True for all "
                "findings (no hook)"),
            expected="all True",
            observed=str(
                [f.ml_disabled for f in a.findings]),
            matched=all(
                f.ml_disabled is True for f in a.findings)),
        AssertionResult(
            assertion_id="doc02-a4",
            description=(
                "Method = STATISTICAL_FALLBACK"),
            expected=(
                FindingMethod.STATISTICAL_FALLBACK.value),
            observed=(
                a.findings[0].method.value
                if a.findings else "n/a"),
            matched=(
                len(a.findings) > 0
                and a.findings[0].method
                == FindingMethod.STATISTICAL_FALLBACK)),
    )


SCENARIO_DOC_02_EXPIRED = Scenario(
    scenario_id="DOC-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-270 late presentation: LC expired 2026-06-01, "
        "presentation made 2026-06-20 → CRITICAL EXPIRY "
        "finding (UCP 600 §6) → outcome DISCREPANT_REFUSAL_"
        "LIKELY. No ML hook → ml_disabled=True, method = "
        "STATISTICAL_FALLBACK per Rule 6."),
    setup=_setup_doc,
    actions=_actions_doc_expired,
    assertions=_assertions_doc_expired,
    requires_engines=("trade_finance_document_checking",))


# DOC-03 — ML hook injected, refines severity downward + filters FPs
def _actions_doc_ml_refines(engines: EngineBundle) -> None:
    from utils.trade_finance_document_checking import (
        TradeFinanceDocumentCheckingEngine,
        ClassificationResult, DiscrepancySeverity)
    from datetime import date as _d

    # Trained-style classifier: filters EXPIRY/MISSING_DOC as
    # actually-discrepant CRITICAL, but downgrades AMOUNT_TOLERANCE
    # and CROSS_DOCUMENT_PORT findings to LOW (typically
    # acceptable in practice per local tolerance)
    def fake_trained_classifier(candidates):
        results = []
        for c in candidates:
            if c.category.value in (
                "EXPIRY", "MISSING_DOCUMENT",
                "MISSING_REQUIRED_FIELD",
            ):
                results.append(ClassificationResult(
                    refined_severity=(
                        DiscrepancySeverity.CRITICAL),
                    is_true_discrepancy=True,
                    confidence=0.97,
                    reasoning=(
                        "Categorical UCP 600 violation — "
                        "high confidence true discrepancy")))
            else:
                # Borderline → downgrade to LOW
                results.append(ClassificationResult(
                    refined_severity=DiscrepancySeverity.LOW,
                    is_true_discrepancy=True,
                    confidence=0.72,
                    reasoning=(
                        "Likely waivable per training data — "
                        "downgraded from rule severity")))
        return results

    eng = TradeFinanceDocumentCheckingEngine(
        ml_discrepancy_classifier=fake_trained_classifier)
    lc = _make_doc_lc(amount=Decimal("1000000"))
    # Amount over tolerance — rule says HIGH, ML downgrades to LOW
    pres = _make_doc_presentation(documents=[
        _make_doc_invoice(amount=Decimal("1100000")),
        _make_doc_bl()])
    engines["__doc03__"] = eng.assess_presentation(lc, pres)


def _assertions_doc_ml_refines(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_document_checking import (
        PresentationOutcome, DiscrepancySeverity,
        FindingMethod)
    a = engines.get("__doc03__")
    if a is None:
        return (AssertionResult(
            assertion_id="doc03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="doc03-a1",
            description=(
                "ML downgraded HIGH amount-tolerance to LOW → "
                "outcome DISCREPANT_WAIVABLE (not REFUSAL_"
                "LIKELY)"),
            expected=(
                PresentationOutcome.DISCREPANT_WAIVABLE.value),
            observed=a.outcome.value,
            matched=(
                a.outcome
                == PresentationOutcome.DISCREPANT_WAIVABLE)),
        AssertionResult(
            assertion_id="doc03-a2",
            description=(
                "All findings via ML hook: method=ML_INJECTED"),
            expected="all ML_INJECTED",
            observed=", ".join(
                f.method.value for f in a.findings),
            matched=(
                len(a.findings) > 0
                and all(
                    f.method == FindingMethod.ML_INJECTED
                    for f in a.findings))),
        AssertionResult(
            assertion_id="doc03-a3",
            description=(
                "Per Rule 6 — ml_disabled=False; "
                "overall_ml_disabled=False"),
            expected="False (with ML hook injected)",
            observed=str(a.overall_ml_disabled),
            matched=a.overall_ml_disabled is False),
        AssertionResult(
            assertion_id="doc03-a4",
            description=(
                "Confidence 0.72 surfaced exactly per Rule 1"),
            expected="0.72",
            observed=str(
                a.findings[0].confidence
                if a.findings else "n/a"),
            matched=(
                len(a.findings) > 0
                and a.findings[0].confidence is not None
                and abs(
                    a.findings[0].confidence - 0.72) < 0.001)),
    )


SCENARIO_DOC_03_ML_REFINES = Scenario(
    scenario_id="DOC-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-270 with injected ML classifier — over-tolerance "
        "amount candidate (rule says HIGH severity) gets "
        "downgraded by ML to LOW (training data says these "
        "are typically waivable). Outcome shifts from "
        "DISCREPANT_REFUSAL_LIKELY to DISCREPANT_WAIVABLE. "
        "method=ML_INJECTED, ml_disabled=False, confidence "
        "0.72 surfaced. Demonstrates the v10.76 ML hook "
        "contract working in production-realistic shape."),
    setup=_setup_doc,
    actions=_actions_doc_ml_refines,
    assertions=_assertions_doc_ml_refines,
    requires_engines=("trade_finance_document_checking",))


# DOC-04 — ML hook fails → graceful fallback preserves CRITICAL
def _actions_doc_ml_failure(engines: EngineBundle) -> None:
    from utils.trade_finance_document_checking import (
        TradeFinanceDocumentCheckingEngine)
    from datetime import date as _d

    def broken_classifier(candidates):
        raise RuntimeError(
            "model artifact corrupt or sklearn version "
            "mismatch")

    eng = TradeFinanceDocumentCheckingEngine(
        ml_discrepancy_classifier=broken_classifier)
    lc = _make_doc_lc(expiry=_d(2026, 6, 1))
    pres = _make_doc_presentation(
        pres_date=_d(2026, 6, 20))    # late
    engines["__doc04__"] = eng.assess_presentation(lc, pres)


def _assertions_doc_ml_failure(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_document_checking import (
        PresentationOutcome, DiscrepancySeverity,
        CheckCategory, FindingMethod)
    a = engines.get("__doc04__")
    if a is None:
        return (AssertionResult(
            assertion_id="doc04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="doc04-a1",
            description=(
                "Failed ML hook — graceful fallback "
                "preserves CRITICAL severity"),
            expected="CRITICAL EXPIRY preserved",
            observed=", ".join(
                f"{f.category.value}:{f.severity.value}"
                for f in a.findings),
            matched=any(
                f.category == CheckCategory.EXPIRY
                and f.severity == DiscrepancySeverity.CRITICAL
                for f in a.findings)),
        AssertionResult(
            assertion_id="doc04-a2",
            description=(
                "method=STATISTICAL_FALLBACK after hook "
                "failure"),
            expected=(
                FindingMethod.STATISTICAL_FALLBACK.value),
            observed=(
                a.findings[0].method.value
                if a.findings else "n/a"),
            matched=(
                len(a.findings) > 0
                and a.findings[0].method
                == FindingMethod.STATISTICAL_FALLBACK)),
        AssertionResult(
            assertion_id="doc04-a3",
            description=(
                "Per Rule 6 — ml_disabled=True after hook "
                "failure"),
            expected="True",
            observed=str(
                [f.ml_disabled for f in a.findings]),
            matched=all(
                f.ml_disabled is True for f in a.findings)),
        AssertionResult(
            assertion_id="doc04-a4",
            description=(
                "Outcome still DISCREPANT_REFUSAL_LIKELY "
                "(CRITICAL preserved through fallback)"),
            expected=(
                PresentationOutcome.DISCREPANT_REFUSAL_LIKELY
                .value),
            observed=a.outcome.value,
            matched=(
                a.outcome
                == PresentationOutcome
                .DISCREPANT_REFUSAL_LIKELY)),
    )


SCENARIO_DOC_04_ML_FAILURE = Scenario(
    scenario_id="DOC-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-270 graceful failure: ML classifier raises "
        "RuntimeError (e.g. model artifact corrupt, sklearn "
        "version mismatch). Engine falls back to "
        "deterministic rule severity preserving CRITICAL "
        "EXPIRY finding; ml_disabled=True; method=STATISTICAL_"
        "FALLBACK. Production never crashes because of ML "
        "failure — the v10.76 contract guarantee."),
    setup=_setup_doc,
    actions=_actions_doc_ml_failure,
    assertions=_assertions_doc_ml_failure,
    requires_engines=("trade_finance_document_checking",))


# ════════════════════════════════════════════════════════════════════════
# v10.79 — Corporate Trade Portal (ENH-271)
# ════════════════════════════════════════════════════════════════════════

def _setup_prt(engines: EngineBundle) -> None:
    pass


# PRT-01 — clean LC application validates as COMPLETE
def _actions_prt_clean_app(engines: EngineBundle) -> None:
    from utils.trade_finance_corporate_portal import (
        TradeFinanceCorporatePortalEngine, LCApplication)
    from datetime import date as _d
    eng = TradeFinanceCorporatePortalEngine()
    app = LCApplication(
        application_id="APP-CLEAN",
        applicant="Acme Imports",
        beneficiary="RiceCo Ltd",
        requested_amount_kes=Decimal("2000000"),
        currency="USD",
        requested_expiry_date=_d(2026, 8, 1),
        requested_latest_shipment_date=_d(2026, 7, 15),
        description_of_goods="50 metric tons milled rice grade A",
        incoterms="CIF Mombasa",
        submission_date=_d(2026, 5, 1))
    engines["__prt01__"] = eng.validate_lc_application(app)


def _assertions_prt_clean_app(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_corporate_portal import (
        ApplicationCompleteness)
    v = engines.get("__prt01__")
    if v is None:
        return (AssertionResult(
            assertion_id="prt01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="prt01-a1",
            description="Clean application → COMPLETE",
            expected=(
                ApplicationCompleteness.COMPLETE.value),
            observed=v.completeness.value,
            matched=(
                v.completeness
                == ApplicationCompleteness.COMPLETE)),
        AssertionResult(
            assertion_id="prt01-a2",
            description="Zero field findings",
            expected="0",
            observed=str(len(v.findings)),
            matched=len(v.findings) == 0),
        AssertionResult(
            assertion_id="prt01-a3",
            description=(
                "Estimated fees: 0.5% × 2m = 10,000.00"),
            expected="10000.00",
            observed=str(v.estimated_fees_kes),
            matched=(
                v.estimated_fees_kes == Decimal("10000.00"))),
        AssertionResult(
            assertion_id="prt01-a4",
            description=(
                "ENH-271 cited in framework_refs per Rule 1"),
            expected="ENH-271",
            observed=" / ".join(v.framework_refs),
            matched=any(
                "ENH-271" in r for r in v.framework_refs)),
    )


SCENARIO_PRT_01_CLEAN_APP = Scenario(
    scenario_id="PRT-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-271 validate_lc_application on clean corporate "
        "submission: applicant + beneficiary + amount + "
        "currency + expiry + shipment + description + "
        "incoterms all present and valid. Outcome COMPLETE, "
        "zero findings, preliminary fee estimate 10,000.00 "
        "KES (0.5% of 2m). ENH-271 cited per Rule 1."),
    setup=_setup_prt,
    actions=_actions_prt_clean_app,
    assertions=_assertions_prt_clean_app,
    requires_engines=("trade_finance_corporate_portal",))


# PRT-02 — amendment with multiple types, beneficiary change
# triggers HIGH impact + compliance_screening
def _actions_prt_amendment(engines: EngineBundle) -> None:
    from utils.trade_finance_corporate_portal import (
        TradeFinanceCorporatePortalEngine, AmendmentRequest)
    from datetime import date as _d
    eng = TradeFinanceCorporatePortalEngine()
    amend = AmendmentRequest(
        amendment_id="AM-PRT2",
        lc_reference="LC-EXISTING",
        requested_at=_d(2026, 5, 1),
        new_amount_kes=Decimal("3000000"),
        new_expiry_date=_d(2026, 12, 31),
        new_beneficiary="DifferentSupplierCo")
    engines["__prt02__"] = (
        eng.classify_amendment_request(
            amend,
            existing_lc_amount_kes=Decimal("2000000")))


def _assertions_prt_amendment(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_corporate_portal import (
        AmendmentType, AmendmentImpact)
    c = engines.get("__prt02__")
    if c is None:
        return (AssertionResult(
            assertion_id="prt02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="prt02-a1",
            description=(
                "Three types detected: AMOUNT_INCREASE + "
                "EXPIRY_EXTENSION + BENEFICIARY_CHANGE"),
            expected="3 types",
            observed=", ".join(
                t.value for t in c.detected_types),
            matched=(
                AmendmentType.AMOUNT_INCREASE
                in c.detected_types
                and AmendmentType.EXPIRY_EXTENSION
                in c.detected_types
                and AmendmentType.BENEFICIARY_CHANGE
                in c.detected_types)),
        AssertionResult(
            assertion_id="prt02-a2",
            description=(
                "Primary type AMOUNT_INCREASE (most "
                "impactful in conservatism order)"),
            expected=AmendmentType.AMOUNT_INCREASE.value,
            observed=c.primary_type.value,
            matched=(
                c.primary_type
                == AmendmentType.AMOUNT_INCREASE)),
        AssertionResult(
            assertion_id="prt02-a3",
            description=(
                "Impact HIGH (amount increase OR beneficiary "
                "change)"),
            expected=AmendmentImpact.HIGH.value,
            observed=c.impact.value,
            matched=c.impact == AmendmentImpact.HIGH),
        AssertionResult(
            assertion_id="prt02-a4",
            description=(
                "Required approvals include compliance_"
                "screening (BENEFICIARY_CHANGE) + limit_"
                "review (AMOUNT_INCREASE) + credit_committee "
                "(HIGH impact)"),
            expected=(
                "compliance_screening + limit_review + "
                "credit_committee"),
            observed=", ".join(c.required_approvals),
            matched=(
                "compliance_screening" in c.required_approvals
                and "limit_review" in c.required_approvals
                and "credit_committee" in c.required_approvals)),
    )


SCENARIO_PRT_02_AMENDMENT = Scenario(
    scenario_id="PRT-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-271 classify_amendment_request on multi-type "
        "amendment (amount 2m→3m + expiry extension + "
        "beneficiary change). Detected types include all 3; "
        "primary type AMOUNT_INCREASE per impact ordering; "
        "impact HIGH; required_approvals span "
        "compliance_screening + limit_review + "
        "credit_committee. Demonstrates Rule 1 (full picture "
        "surfaced not just primary) + Rule 7 (engine "
        "classifies; operations + Credit decide)."),
    setup=_setup_prt,
    actions=_actions_prt_amendment,
    assertions=_assertions_prt_amendment,
    requires_engines=("trade_finance_corporate_portal",))


# ════════════════════════════════════════════════════════════════════════
# v10.79 — Multi-Bank Connectivity (ENH-276)
# ════════════════════════════════════════════════════════════════════════

def _setup_con(engines: EngineBundle) -> None:
    pass


# CON-01 — valid we.trade message validates + maps + routes cleanly
def _actions_con_clean(engines: EngineBundle) -> None:
    from utils.trade_finance_connectivity import (
        TradeFinanceConnectivityEngine,
        InboundMessage, FieldMapping, TradeNetwork,
        RoutingAction)
    from datetime import date as _d
    eng = TradeFinanceConnectivityEngine()
    msg = InboundMessage(
        message_id="WT-CON1",
        network=TradeNetwork.WE_TRADE,
        received_at=_d(2026, 5, 1),
        body={
            "message_id": "WT-CON1",
            "message_type": "ISSUE_LC",
            "sender_bin": "BIN-A",
            "receiver_bin": "BIN-B",
            "lc_reference": "LC-W1",
            "amount": "5000000",
            "currency": "USD",
            "version": "2.0"},
        sequence_number=1)
    engines["__con01_v__"] = (
        eng.validate_inbound_message_structure(msg))
    engines["__con01_m__"] = (
        eng.map_to_internal_schema(
            msg,
            (FieldMapping("lc_reference", "lc_id"),
             FieldMapping("amount", "amount_kes"),
             FieldMapping("currency", "currency")),
            required_internal_fields=(
                "lc_id", "amount_kes", "currency")))
    engines["__con01_r__"] = (
        eng.classify_routing_action(
            msg, "message_type",
            {"ISSUE_LC": RoutingAction.NEW_LC_ISSUANCE}))


def _assertions_con_clean(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_connectivity import (
        MessageValidationStatus, RoutingAction)
    v = engines.get("__con01_v__")
    m = engines.get("__con01_m__")
    r = engines.get("__con01_r__")
    if v is None or m is None or r is None:
        return (AssertionResult(
            assertion_id="con01-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="con01-a1",
            description=(
                "we.trade message structure VALID"),
            expected=MessageValidationStatus.VALID.value,
            observed=v.status.value,
            matched=v.status == MessageValidationStatus.VALID),
        AssertionResult(
            assertion_id="con01-a2",
            description=(
                "Mapped 3 fields (lc_id + amount_kes + "
                "currency); no missing internal"),
            expected="3 mapped, 0 missing",
            observed=(
                f"mapped={len(m.mapped_fields)}, "
                f"missing="
                f"{len(m.missing_required_internal_fields)}"),
            matched=(
                len(m.mapped_fields) == 3
                and len(m.missing_required_internal_fields)
                == 0)),
        AssertionResult(
            assertion_id="con01-a3",
            description=(
                "Unmapped inbound: message_id, message_type, "
                "sender_bin, receiver_bin, version (5 "
                "remaining)"),
            expected="5 unmapped surfaced",
            observed=str(m.unmapped_inbound_fields),
            matched=len(m.unmapped_inbound_fields) == 5),
        AssertionResult(
            assertion_id="con01-a4",
            description=(
                "Routing classified as NEW_LC_ISSUANCE"),
            expected=(
                RoutingAction.NEW_LC_ISSUANCE.value),
            observed=r.action.value,
            matched=(
                r.action == RoutingAction.NEW_LC_ISSUANCE)),
    )


SCENARIO_CON_01_CLEAN = Scenario(
    scenario_id="CON-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-276 we.trade ISSUE_LC message — validates VALID "
        "(all 8 required fields present), maps 3 internal "
        "fields (lc_id + amount_kes + currency) with 0 "
        "missing required, surfaces 5 unmapped inbound "
        "fields per Rule 1 (Rule 7 — engine never silently "
        "drops or fabricates), routes to NEW_LC_ISSUANCE."),
    setup=_setup_con,
    actions=_actions_con_clean,
    assertions=_assertions_con_clean,
    requires_engines=("trade_finance_connectivity",))


# CON-02 — anomaly detection: duplicate ID + version mismatch
def _actions_con_anomalies(engines: EngineBundle) -> None:
    from utils.trade_finance_connectivity import (
        TradeFinanceConnectivityEngine,
        InboundMessage, TradeNetwork)
    from datetime import date as _d
    eng = TradeFinanceConnectivityEngine(
        supported_versions={"WE_TRADE": ("2.0", "2.1")},
        known_senders={"BANK-A", "BANK-B"})
    base_body = {
        "message_id": "DUP-CON",
        "message_type": "ISSUE_LC",
        "sender_bin": "BIN-A",
        "receiver_bin": "BIN-B",
        "lc_reference": "LC-DUP",
        "amount": "100000",
        "currency": "USD",
        "version": "2.0"}
    msgs = (
        InboundMessage(
            message_id="DUP-CON",
            network=TradeNetwork.WE_TRADE,
            received_at=_d(2026, 5, 1),
            body=base_body,
            sequence_number=1,
            protocol_version="2.0",
            sender_id="BANK-A"),
        InboundMessage(
            message_id="DUP-CON",   # DUPLICATE ID
            network=TradeNetwork.WE_TRADE,
            received_at=_d(2026, 5, 2),
            body={**base_body, "version": "3.5"},
            sequence_number=2,
            protocol_version="3.5",   # VERSION MISMATCH
            sender_id="BANK-A"),
        InboundMessage(
            message_id="UNIQUE-1",
            network=TradeNetwork.WE_TRADE,
            received_at=_d(2026, 5, 3),
            body=base_body,
            sequence_number=3,
            protocol_version="2.0",
            sender_id="ROGUE"),       # UNKNOWN SENDER
    )
    engines["__con02__"] = (
        eng.detect_protocol_anomalies(msgs))


def _assertions_con_anomalies(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_connectivity import (
        AnomalyType, AnomalySeverity)
    a = engines.get("__con02__")
    if a is None:
        return (AssertionResult(
            assertion_id="con02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    types_seen = {x.anomaly_type for x in a}
    return (
        AssertionResult(
            assertion_id="con02-a1",
            description=(
                "Duplicate message_id detected (HIGH "
                "severity)"),
            expected="DUPLICATE_MESSAGE_ID + HIGH",
            observed=", ".join(
                f"{x.anomaly_type.value}:{x.severity.value}"
                for x in a),
            matched=(
                AnomalyType.DUPLICATE_MESSAGE_ID
                in types_seen
                and any(
                    x.anomaly_type
                    == AnomalyType.DUPLICATE_MESSAGE_ID
                    and x.severity == AnomalySeverity.HIGH
                    for x in a))),
        AssertionResult(
            assertion_id="con02-a2",
            description=(
                "Version mismatch (3.5 vs supported 2.0/2.1)"),
            expected="VERSION_MISMATCH detected",
            observed=str(types_seen),
            matched=(
                AnomalyType.VERSION_MISMATCH in types_seen)),
        AssertionResult(
            assertion_id="con02-a3",
            description=(
                "Unknown sender 'ROGUE' detected"),
            expected="UNKNOWN_SENDER detected",
            observed=str(types_seen),
            matched=(
                AnomalyType.UNKNOWN_SENDER in types_seen)),
        AssertionResult(
            assertion_id="con02-a4",
            description=(
                "All 3 anomaly types surfaced (no silent "
                "drops per Rule 1)"),
            expected="3 distinct anomaly types",
            observed=f"{len(types_seen)} distinct types",
            matched=len(types_seen) == 3),
    )


SCENARIO_CON_02_ANOMALIES = Scenario(
    scenario_id="CON-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-276 detect_protocol_anomalies on 3-message "
        "stream with embedded issues: duplicate message_id "
        "(HIGH severity), version 3.5 not in supported "
        "(2.0, 2.1), sender 'ROGUE' not in known_senders "
        "({BANK-A, BANK-B}). All 3 anomaly types surfaced "
        "with appropriate severity per Rule 1 + Rule 7 "
        "(operator examines + decides)."),
    setup=_setup_con,
    actions=_actions_con_anomalies,
    assertions=_assertions_con_anomalies,
    requires_engines=("trade_finance_connectivity",))


# PRT-03 — instrument status snapshot from active LC
def _actions_prt_status(engines: EngineBundle) -> None:
    from utils.trade_finance_corporate_portal import (
        TradeFinanceCorporatePortalEngine)
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    from datetime import date as _d
    eng = TradeFinanceCorporatePortalEngine()
    inst = TradeInstrument(
        instrument_id="LC-PRT3",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.ACTIVE,
        applicant="A", beneficiary="B",
        issuing_bank="X", advising_bank="Y",
        amount_kes=Decimal("1500000"), currency="USD",
        issue_date=_d(2026, 5, 1),
        expiry_date=_d(2026, 8, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF",
        description_of_goods="test goods")
    engines["__prt03__"] = eng.track_instrument_status(
        inst, as_of=_d(2026, 6, 1))


def _assertions_prt_status(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_instruments import (
        InstrumentState)
    snap = engines.get("__prt03__")
    if snap is None:
        return (AssertionResult(
            assertion_id="prt03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="prt03-a1",
            description=(
                "Days until expiry computed: "
                "2026-08-01 - 2026-06-01 = 61"),
            expected="61",
            observed=str(snap.days_until_expiry),
            matched=snap.days_until_expiry == 61),
        AssertionResult(
            assertion_id="prt03-a2",
            description="State preserved as ACTIVE",
            expected=InstrumentState.ACTIVE.value,
            observed=snap.state.value,
            matched=snap.state == InstrumentState.ACTIVE),
        AssertionResult(
            assertion_id="prt03-a3",
            description=(
                "Per Rule 1 — surface None for is_within_"
                "presentation_period when shipment date not "
                "in instrument record"),
            expected="None",
            observed=str(snap.is_within_presentation_period),
            matched=(
                snap.is_within_presentation_period is None)),
        AssertionResult(
            assertion_id="prt03-a4",
            description=(
                "Milestones tuple populated (≥4 entries)"),
            expected="≥4",
            observed=str(len(snap.milestones)),
            matched=len(snap.milestones) >= 4),
    )


SCENARIO_PRT_03_STATUS = Scenario(
    scenario_id="PRT-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-271 track_instrument_status on active LC: "
        "61 days until expiry, state ACTIVE preserved, "
        "is_within_presentation_period surfaces None per "
        "Rule 1 (shipment date not in instrument record — "
        "engine never fabricates), milestones tuple "
        "populated."),
    setup=_setup_prt,
    actions=_actions_prt_status,
    assertions=_assertions_prt_status,
    requires_engines=("trade_finance_corporate_portal",))


# PRT-04 — document upload validation: clean PDF + oversized + bad ext
def _actions_prt_uploads(engines: EngineBundle) -> None:
    from utils.trade_finance_corporate_portal import (
        TradeFinanceCorporatePortalEngine, DocumentUpload)
    eng = TradeFinanceCorporatePortalEngine()
    clean = DocumentUpload(
        upload_id="UP-CLEAN",
        filename="invoice.pdf",
        declared_document_type="COMMERCIAL_INVOICE",
        declared_size_bytes=500_000)
    huge = DocumentUpload(
        upload_id="UP-HUGE",
        filename="huge.pdf",
        declared_document_type="OTHER",
        declared_size_bytes=100 * 1024 * 1024)
    bad_ext = DocumentUpload(
        upload_id="UP-BAD",
        filename="malware.exe",
        declared_document_type="OTHER",
        declared_size_bytes=100)
    engines["__prt04_clean__"] = (
        eng.validate_document_upload(clean))
    engines["__prt04_huge__"] = (
        eng.validate_document_upload(huge))
    engines["__prt04_bad__"] = (
        eng.validate_document_upload(bad_ext))


def _assertions_prt_uploads(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_corporate_portal import (
        DocumentValidationOutcome)
    c = engines.get("__prt04_clean__")
    h = engines.get("__prt04_huge__")
    b = engines.get("__prt04_bad__")
    if c is None or h is None or b is None:
        return (AssertionResult(
            assertion_id="prt04-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="prt04-a1",
            description="Clean PDF accepted",
            expected=(
                DocumentValidationOutcome.ACCEPTED.value),
            observed=c.outcome.value,
            matched=(
                c.outcome
                == DocumentValidationOutcome.ACCEPTED)),
        AssertionResult(
            assertion_id="prt04-a2",
            description=(
                "100MB upload rejected for size "
                "(default 10MB cap)"),
            expected=(
                DocumentValidationOutcome.REJECTED_SIZE.value),
            observed=h.outcome.value,
            matched=(
                h.outcome
                == DocumentValidationOutcome.REJECTED_SIZE)),
        AssertionResult(
            assertion_id="prt04-a3",
            description=(
                ".exe rejected for type before size "
                "(type-rejection has precedence)"),
            expected=(
                DocumentValidationOutcome.REJECTED_TYPE.value),
            observed=b.outcome.value,
            matched=(
                b.outcome
                == DocumentValidationOutcome.REJECTED_TYPE)),
        AssertionResult(
            assertion_id="prt04-a4",
            description=(
                "Per Rule 7 — engine never opens / parses / "
                "stores file (DMS territory)"),
            expected="DMS territory cited in refs",
            observed=" / ".join(c.framework_refs),
            matched=any(
                "document management" in r.lower()
                for r in c.framework_refs)),
    )


SCENARIO_PRT_04_UPLOADS = Scenario(
    scenario_id="PRT-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-271 validate_document_upload across 3 cases: "
        "clean 500KB PDF (ACCEPTED), 100MB PDF "
        "(REJECTED_SIZE — default 10MB cap), .exe "
        "(REJECTED_TYPE — type rejection has precedence over "
        "size). Rule 7 boundary cited (engine never opens / "
        "parses / stores files; DMS territory)."),
    setup=_setup_prt,
    actions=_actions_prt_uploads,
    assertions=_assertions_prt_uploads,
    requires_engines=("trade_finance_corporate_portal",))


# CON-03 — mapping surfaces unmapped + missing internal explicitly
def _actions_con_mapping(engines: EngineBundle) -> None:
    from utils.trade_finance_connectivity import (
        TradeFinanceConnectivityEngine,
        InboundMessage, FieldMapping, TradeNetwork)
    from datetime import date as _d
    eng = TradeFinanceConnectivityEngine()
    msg = InboundMessage(
        message_id="MP-CON3",
        network=TradeNetwork.MARCO_POLO,
        received_at=_d(2026, 5, 1),
        body={
            "message_id": "MP-CON3",
            "msg_type": "TRADE_INIT",
            "originator": "OriginatorBank",
            "destination": "DestBank",
            "trade_id": "T-9001",
            "amount": "750000",
            "currency": "EUR",
            "protocol_version": "3.1",
            "vendor_field_a": "extra1",
            "vendor_field_b": "extra2"})
    # Map only 2 of the 9 inbound fields
    mappings = (
        FieldMapping("trade_id", "lc_id"),
        FieldMapping("amount", "amount_kes"))
    engines["__con03__"] = eng.map_to_internal_schema(
        msg, mappings,
        required_internal_fields=(
            "lc_id", "amount_kes", "currency",
            "issuing_bank_bic"))


def _assertions_con_mapping(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__con03__")
    if r is None:
        return (AssertionResult(
            assertion_id="con03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="con03-a1",
            description="Mapped 2 internal fields",
            expected="2",
            observed=str(len(r.mapped_fields)),
            matched=len(r.mapped_fields) == 2),
        AssertionResult(
            assertion_id="con03-a2",
            description=(
                "Surfaced 8 unmapped inbound fields "
                "(10 inbound - 2 mapped = 8)"),
            expected="8",
            observed=str(len(r.unmapped_inbound_fields)),
            matched=(
                len(r.unmapped_inbound_fields) == 8)),
        AssertionResult(
            assertion_id="con03-a3",
            description=(
                "Surfaced 2 missing internal fields "
                "(currency + issuing_bank_bic) per Rule 1"),
            expected="2",
            observed=str(
                len(r.missing_required_internal_fields)),
            matched=(
                "currency"
                in r.missing_required_internal_fields
                and "issuing_bank_bic"
                in r.missing_required_internal_fields)),
        AssertionResult(
            assertion_id="con03-a4",
            description=(
                "lc_id IS mapped — not in missing list"),
            expected="lc_id mapped",
            observed=str(
                r.missing_required_internal_fields),
            matched=(
                "lc_id"
                not in r.missing_required_internal_fields)),
    )


SCENARIO_CON_03_MAPPING = Scenario(
    scenario_id="CON-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-276 map_to_internal_schema on Marco Polo "
        "TRADE_INIT message with 10 inbound fields + 2 "
        "FieldMapping entries + 4 required_internal_fields. "
        "Engine maps 2, surfaces 8 unmapped inbound, "
        "surfaces 2 missing internal (currency + "
        "issuing_bank_bic) per Rule 1 — engine never "
        "fabricates values, never silently drops."),
    setup=_setup_con,
    actions=_actions_con_mapping,
    assertions=_assertions_con_mapping,
    requires_engines=("trade_finance_connectivity",))


# CON-04 — full connectivity report orchestrator with mixed batch
def _actions_con_report(engines: EngineBundle) -> None:
    from utils.trade_finance_connectivity import (
        TradeFinanceConnectivityEngine,
        InboundMessage, TradeNetwork, RoutingAction)
    from datetime import date as _d
    eng = TradeFinanceConnectivityEngine()
    base_we_trade = {
        "message_id": "WT-1",
        "message_type": "ISSUE_LC",
        "sender_bin": "BIN-A",
        "receiver_bin": "BIN-B",
        "lc_reference": "LC-1",
        "amount": "100000",
        "currency": "USD",
        "version": "2.0"}
    msgs = (
        InboundMessage(
            message_id="WT-1",
            network=TradeNetwork.WE_TRADE,
            received_at=_d(2026, 5, 1),
            body=base_we_trade,
            sequence_number=1),
        InboundMessage(
            message_id="WT-2",
            network=TradeNetwork.WE_TRADE,
            received_at=_d(2026, 5, 2),
            body={**base_we_trade,
                  "message_id": "WT-2",
                  "message_type": "AMEND_LC"},
            sequence_number=2),
        InboundMessage(
            message_id="MP-1",
            network=TradeNetwork.MARCO_POLO,
            received_at=_d(2026, 5, 2),
            body={
                "message_id": "MP-1",
                "msg_type": "TRADE_INIT",
                "originator": "X",
                "destination": "Y",
                "trade_id": "T-1",
                # missing required: amount, currency, version
            }),
    )
    action_map = {
        TradeNetwork.WE_TRADE: (
            "message_type",
            {"ISSUE_LC": RoutingAction.NEW_LC_ISSUANCE,
             "AMEND_LC": (
                 RoutingAction.AMENDMENT_NOTIFICATION)}),
        TradeNetwork.MARCO_POLO: (
            "msg_type",
            {"TRADE_INIT":
             RoutingAction.NEW_LC_ISSUANCE})}
    engines["__con04__"] = (
        eng.build_connectivity_report(
            msgs,
            as_of_date_iso="2026-05-03",
            action_map_by_network=action_map))


def _assertions_con_report(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.trade_finance_connectivity import (
        MessageValidationStatus, RoutingAction)
    r = engines.get("__con04__")
    if r is None:
        return (AssertionResult(
            assertion_id="con04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="con04-a1",
            description="3 messages total",
            expected="3",
            observed=str(r.total_messages),
            matched=r.total_messages == 3),
        AssertionResult(
            assertion_id="con04-a2",
            description=(
                "By-network: WE_TRADE=2, MARCO_POLO=1"),
            expected="WE_TRADE:2, MARCO_POLO:1",
            observed=str(dict(r.by_network_count)),
            matched=(
                r.by_network_count.get("WE_TRADE") == 2
                and r.by_network_count.get("MARCO_POLO")
                == 1)),
        AssertionResult(
            assertion_id="con04-a3",
            description=(
                "By-status: 2 VALID, 1 MISSING_REQUIRED_"
                "FIELDS"),
            expected="2 VALID, 1 MISSING",
            observed=str(dict(r.by_status_count)),
            matched=(
                r.by_status_count.get(
                    MessageValidationStatus.VALID.value) == 2
                and r.by_status_count.get(
                    MessageValidationStatus
                    .MISSING_REQUIRED_FIELDS.value) == 1)),
        AssertionResult(
            assertion_id="con04-a4",
            description=(
                "By-action: 2 NEW_LC_ISSUANCE + 1 "
                "AMENDMENT_NOTIFICATION"),
            expected="2 NEW + 1 AMEND",
            observed=str(dict(r.by_action_count)),
            matched=(
                r.by_action_count.get(
                    RoutingAction.NEW_LC_ISSUANCE.value) == 2
                and r.by_action_count.get(
                    RoutingAction.AMENDMENT_NOTIFICATION
                    .value) == 1)),
    )


SCENARIO_CON_04_REPORT = Scenario(
    scenario_id="CON-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-276 build_connectivity_report on mixed 3-message "
        "batch (2 we.trade + 1 Marco Polo with missing "
        "required fields). Orchestrator surfaces "
        "by_network_count, by_status_count "
        "(2 VALID + 1 MISSING_REQUIRED_FIELDS), "
        "by_action_count (2 NEW_LC_ISSUANCE + 1 "
        "AMENDMENT_NOTIFICATION). Rollup pattern for arc "
        "closure cockpit dashboard."),
    setup=_setup_con,
    actions=_actions_con_report,
    assertions=_assertions_con_report,
    requires_engines=("trade_finance_connectivity",))


# ════════════════════════════════════════════════════════════════════════
# v10.81 — ENH-281 MLOps Model Registry (ml_governance arc 1/N)
# ════════════════════════════════════════════════════════════════════════

def _setup_mrg(engines: EngineBundle) -> None:
    pass


# MRG-01 — clean registration with all required fields
def _actions_mrg_register(engines: EngineBundle) -> None:
    from utils.mlops_model_registry import (
        MLOpsModelRegistryEngine)
    eng = MLOpsModelRegistryEngine()
    result = eng.register_new_model_version(
        model_id="doc_classifier",
        version="2.0.0",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        framework="sklearn",
        framework_version="1.5.1",
        metrics={
            "accuracy": Decimal("0.87"),
            "f1": Decimal("0.85")},
        owner="ml-team@bank",
        created_by="trainer-pipeline",
        created_at_iso="2026-05-01T00:00:00Z",
        training_completed_at_iso="2026-05-01T00:00:00Z",
        notes="Baseline LogisticRegression model")
    engines["__mrg01__"] = result


def _assertions_mrg_register(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_model_registry import (
        RegistrationOutcome, ModelStatus)
    r = engines.get("__mrg01__")
    if r is None:
        return (AssertionResult(
            assertion_id="mrg01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="mrg01-a1",
            description="Outcome REGISTERED",
            expected=RegistrationOutcome.REGISTERED.value,
            observed=r.outcome.value,
            matched=(
                r.outcome == RegistrationOutcome.REGISTERED)),
        AssertionResult(
            assertion_id="mrg01-a2",
            description="Initial status PROPOSED",
            expected=ModelStatus.PROPOSED.value,
            observed=(
                r.entry.status.value if r.entry else "None"),
            matched=(
                r.entry is not None
                and r.entry.status == ModelStatus.PROPOSED)),
        AssertionResult(
            assertion_id="mrg01-a3",
            description="Zero validation findings",
            expected="0",
            observed=str(len(r.findings)),
            matched=len(r.findings) == 0),
        AssertionResult(
            assertion_id="mrg01-a4",
            description=(
                "Per Rule 7 — engine never persists "
                "(REGISTERED outcome surfaces entry; caller "
                "appends to their storage)"),
            expected="ENH-281 + Rule 7 in framework_refs",
            observed=" / ".join(r.framework_refs),
            matched=(
                any("ENH-281" in x for x in r.framework_refs)
                and any(
                    "Rule 7" in x for x in r.framework_refs))),
    )


SCENARIO_MRG_01_REGISTER = Scenario(
    scenario_id="MRG-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-281 register_new_model_version on clean inputs: "
        "all required fields present + valid SHA-256 hashes + "
        "recognized framework + Decimal metrics. Outcome "
        "REGISTERED, status PROPOSED, zero validation findings, "
        "ENH-281 + Rule 7 cited per Rule 1."),
    setup=_setup_mrg,
    actions=_actions_mrg_register,
    assertions=_assertions_mrg_register,
    requires_engines=("mlops_model_registry",))


# MRG-02 — multiple ACTIVE governance breach surfaced
def _actions_mrg_multi_active(engines: EngineBundle) -> None:
    from utils.mlops_model_registry import (
        MLOpsModelRegistryEngine, ModelRegistryEntry,
        ModelStatus)
    eng = MLOpsModelRegistryEngine()
    registry = (
        ModelRegistryEntry(
            model_id="credit_scorer", version="1.0.0",
            artifact_hash="c" * 64,
            training_data_hash="d" * 64,
            framework="sklearn", framework_version="1.5",
            metrics={"auc": Decimal("0.88")},
            owner="o", status=ModelStatus.ACTIVE,
            created_by="c",
            created_at_iso="2026-04-01T00:00:00Z"),
        ModelRegistryEntry(
            model_id="credit_scorer", version="2.0.0",
            artifact_hash="e" * 64,
            training_data_hash="f" * 64,
            framework="sklearn", framework_version="1.5",
            metrics={"auc": Decimal("0.90")},
            owner="o", status=ModelStatus.ACTIVE,
            created_by="c",
            created_at_iso="2026-05-01T00:00:00Z"),
    )
    engines["__mrg02__"] = eng.lookup_active_version(
        "credit_scorer", registry)


def _assertions_mrg_multi_active(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__mrg02__")
    if r is None:
        return (AssertionResult(
            assertion_id="mrg02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="mrg02-a1",
            description=(
                "multiple_active_violation surfaced as True"),
            expected="True",
            observed=str(r.multiple_active_violation),
            matched=r.multiple_active_violation is True),
        AssertionResult(
            assertion_id="mrg02-a2",
            description="active_count == 2",
            expected="2",
            observed=str(r.active_count),
            matched=r.active_count == 2),
        AssertionResult(
            assertion_id="mrg02-a3",
            description=(
                "Per Rule 7 — engine surfaces breach; never "
                "auto-demotes (operator decides which to "
                "keep)"),
            expected="auto-demote forbidden",
            observed=" / ".join(r.framework_refs),
            matched=any(
                "never auto-demotes" in x.lower()
                or "operator decides which active" in x.lower()
                for x in r.framework_refs)),
        AssertionResult(
            assertion_id="mrg02-a4",
            description="active_entry returned (not None)",
            expected="not None",
            observed=(
                "present" if r.active_entry else "None"),
            matched=r.active_entry is not None),
    )


SCENARIO_MRG_02_MULTI_ACTIVE = Scenario(
    scenario_id="MRG-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-281 lookup_active_version surfaces governance "
        "breach when registry contains 2 ACTIVE entries for "
        "the same model_id. multiple_active_violation=True, "
        "active_count=2. Per Rule 7, engine surfaces breach + "
        "operator decides which to demote (engine never auto-"
        "demotes)."),
    setup=_setup_mrg,
    actions=_actions_mrg_multi_active,
    assertions=_assertions_mrg_multi_active,
    requires_engines=("mlops_model_registry",))


# MRG-03 — compare_versions surfaces metric regression
def _actions_mrg_compare(engines: EngineBundle) -> None:
    from utils.mlops_model_registry import (
        MLOpsModelRegistryEngine, ModelRegistryEntry,
        ModelStatus)
    eng = MLOpsModelRegistryEngine()
    a = ModelRegistryEntry(
        model_id="m", version="1.0",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        framework="sklearn", framework_version="1.5",
        metrics={
            "accuracy": Decimal("0.85"),
            "f1": Decimal("0.82")},
        owner="o", status=ModelStatus.ACTIVE,
        created_by="c", created_at_iso="2026-04-01T00:00:00Z")
    b = ModelRegistryEntry(
        model_id="m", version="2.0",
        artifact_hash="c" * 64,
        training_data_hash="d" * 64,    # different data
        framework="sklearn",
        framework_version="2.0",   # different framework version
        metrics={
            "accuracy": Decimal("0.88"),
            "f1": Decimal("0.78")},   # f1 regression
        owner="o", status=ModelStatus.PROPOSED,
        created_by="c", created_at_iso="2026-05-01T00:00:00Z")
    engines["__mrg03__"] = eng.compare_versions(a, b)


def _assertions_mrg_compare(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    c = engines.get("__mrg03__")
    if c is None:
        return (AssertionResult(
            assertion_id="mrg03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    deltas = {d.metric_name: d for d in c.metric_deltas}
    return (
        AssertionResult(
            assertion_id="mrg03-a1",
            description=(
                "Accuracy delta +0.03 (improvement)"),
            expected="0.03",
            observed=str(deltas["accuracy"].delta),
            matched=(
                deltas["accuracy"].delta == Decimal("0.03"))),
        AssertionResult(
            assertion_id="mrg03-a2",
            description=(
                "F1 delta -0.04 (regression — Rule 1 surfaces "
                "the regression for operator review, not just "
                "the improvement)"),
            expected="-0.04",
            observed=str(deltas["f1"].delta),
            matched=(
                deltas["f1"].delta == Decimal("-0.04"))),
        AssertionResult(
            assertion_id="mrg03-a3",
            description=(
                "framework_version_match=False "
                "(1.5 vs 2.0)"),
            expected="False",
            observed=str(c.framework_version_match),
            matched=c.framework_version_match is False),
        AssertionResult(
            assertion_id="mrg03-a4",
            description=(
                "training_data_hash_match=False (different "
                "training data — flag surfaces explicitly per "
                "Rule 1)"),
            expected="False",
            observed=str(c.training_data_hash_match),
            matched=c.training_data_hash_match is False),
    )


SCENARIO_MRG_03_COMPARE = Scenario(
    scenario_id="MRG-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-281 compare_versions on baseline v1.0 vs "
        "candidate v2.0: accuracy improves +0.03, but f1 "
        "regresses -0.04, framework version differs (1.5→2.0), "
        "training_data_hash differs. All four axes surface "
        "explicitly per Rule 1 — operator sees the full "
        "picture, not just the improvement. Per Rule 7, engine "
        "never recommends one over the other."),
    setup=_setup_mrg,
    actions=_actions_mrg_compare,
    assertions=_assertions_mrg_compare,
    requires_engines=("mlops_model_registry",))


# MRG-04 — promotion readiness with mixed gates
def _actions_mrg_promotion(engines: EngineBundle) -> None:
    from utils.mlops_model_registry import (
        MLOpsModelRegistryEngine, ModelRegistryEntry,
        ModelStatus, PromotionGate, GateType, GateComparison)
    eng = MLOpsModelRegistryEngine()
    active = ModelRegistryEntry(
        model_id="m", version="1.0",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        framework="sklearn", framework_version="1.5",
        metrics={"accuracy": Decimal("0.85")},
        owner="o", status=ModelStatus.ACTIVE,
        created_by="c", created_at_iso="2026-04-01T00:00:00Z")
    candidate = ModelRegistryEntry(
        model_id="m", version="2.0",
        artifact_hash="c" * 64,
        training_data_hash="d" * 64,
        framework="sklearn", framework_version="1.5",
        metrics={"accuracy": Decimal("0.82")},  # 3pp regression
        owner="o", status=ModelStatus.PROPOSED,
        created_by="c", created_at_iso="2026-05-01T00:00:00Z")
    gates = (
        PromotionGate(
            gate_id="MIN",
            gate_type=GateType.MINIMUM_METRIC,
            description="Accuracy must be ≥ 0.80",
            metric_name="accuracy",
            threshold=Decimal("0.80"),
            comparison=GateComparison.GTE),
        PromotionGate(
            gate_id="REG",
            gate_type=GateType.NON_REGRESSION,
            description=(
                "Accuracy regression ≤ 1pp vs active"),
            metric_name="accuracy",
            regression_tolerance=Decimal("0.01"),
            comparison=GateComparison.GTE),
        PromotionGate(
            gate_id="META",
            gate_type=GateType.METADATA_REQUIRED,
            description="Owner must be present",
            required_field="owner"),
    )
    engines["__mrg04__"] = (
        eng.validate_promotion_readiness(
            candidate, active, gates))


def _assertions_mrg_promotion(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_model_registry import (
        PromotionReadinessOutcome, GateFindingSeverity)
    a = engines.get("__mrg04__")
    if a is None:
        return (AssertionResult(
            assertion_id="mrg04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    findings_by_id = {f.gate_id: f for f in a.findings}
    return (
        AssertionResult(
            assertion_id="mrg04-a1",
            description=(
                "Outcome BLOCKED (NON_REGRESSION fails)"),
            expected=(
                PromotionReadinessOutcome.BLOCKED.value),
            observed=a.outcome.value,
            matched=(
                a.outcome
                == PromotionReadinessOutcome.BLOCKED)),
        AssertionResult(
            assertion_id="mrg04-a2",
            description=(
                "MIN gate PASS (0.82 ≥ 0.80)"),
            expected=GateFindingSeverity.PASS.value,
            observed=findings_by_id["MIN"].severity.value,
            matched=(
                findings_by_id["MIN"].severity
                == GateFindingSeverity.PASS)),
        AssertionResult(
            assertion_id="mrg04-a3",
            description=(
                "REG gate FAIL (0.82 < 0.85 - 0.01 = 0.84)"),
            expected=GateFindingSeverity.FAIL.value,
            observed=findings_by_id["REG"].severity.value,
            matched=(
                findings_by_id["REG"].severity
                == GateFindingSeverity.FAIL)),
        AssertionResult(
            assertion_id="mrg04-a4",
            description=(
                "All 3 findings surfaced per Rule 1 "
                "(not just first failure)"),
            expected="3",
            observed=str(len(a.findings)),
            matched=len(a.findings) == 3),
    )


SCENARIO_MRG_04_PROMOTION = Scenario(
    scenario_id="MRG-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-281 validate_promotion_readiness with three gate "
        "types — MINIMUM_METRIC + NON_REGRESSION + "
        "METADATA_REQUIRED. Candidate accuracy 0.82 vs active "
        "0.85 with 1pp tolerance: passes minimum (0.80) but "
        "fails non-regression (0.82 < 0.84). Outcome BLOCKED. "
        "All 3 gate findings surfaced per Rule 1. Per Rule 7, "
        "engine surfaces blocking; operator decides whether to "
        "rerun training, raise tolerance, or override."),
    setup=_setup_mrg,
    actions=_actions_mrg_promotion,
    assertions=_assertions_mrg_promotion,
    requires_engines=("mlops_model_registry",))


# ════════════════════════════════════════════════════════════════════════
# v10.82 — ENH-282 MLOps Adjudication Log (ml_governance arc 2/N)
# ════════════════════════════════════════════════════════════════════════

def _setup_adj(engines: EngineBundle) -> None:
    pass


# ADJ-01 — clean override capture with reason + retraining lineage
def _actions_adj_record(engines: EngineBundle) -> None:
    from utils.mlops_adjudication_log import (
        MLOpsAdjudicationLogEngine, AgreementStatus,
        OverrideReason)
    eng = MLOpsAdjudicationLogEngine()
    result = eng.record_adjudication(
        event_id="EV-ADJ01",
        model_id="doc_classifier",
        model_version="2.0.0",
        recommendation="APPROVE",
        recommendation_class="APPROVE",
        operator_decision="REJECT",
        agreement_status=AgreementStatus.OVERRIDDEN,
        operator_id="alice@bank",
        decision_at_iso="2026-05-01T10:30:00Z",
        override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
        override_reason_text=(
            "Customer is on internal watchlist not yet "
            "reflected in training data"),
        input_features_hash="a" * 64,
        retraining_eligible=True,
        notes="Retraining-eligible operator override")
    engines["__adj01__"] = result


def _assertions_adj_record(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_adjudication_log import (
        RecordingOutcome, AgreementStatus, OverrideReason)
    r = engines.get("__adj01__")
    if r is None:
        return (AssertionResult(
            assertion_id="adj01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="adj01-a1",
            description="Outcome RECORDED",
            expected=RecordingOutcome.RECORDED.value,
            observed=r.outcome.value,
            matched=(
                r.outcome == RecordingOutcome.RECORDED)),
        AssertionResult(
            assertion_id="adj01-a2",
            description="Agreement status OVERRIDDEN",
            expected=AgreementStatus.OVERRIDDEN.value,
            observed=(
                r.record.agreement_status.value
                if r.record else "None"),
            matched=(
                r.record is not None
                and r.record.agreement_status
                == AgreementStatus.OVERRIDDEN)),
        AssertionResult(
            assertion_id="adj01-a3",
            description=(
                "Override reason DOMAIN_KNOWLEDGE preserved"),
            expected=(
                OverrideReason.DOMAIN_KNOWLEDGE.value),
            observed=(
                r.record.override_reason.value
                if r.record and r.record.override_reason
                else "None"),
            matched=(
                r.record is not None
                and r.record.override_reason
                == OverrideReason.DOMAIN_KNOWLEDGE)),
        AssertionResult(
            assertion_id="adj01-a4",
            description=(
                "retraining_eligible=True with input_features_"
                "hash present (lineage preserved per Rule 1)"),
            expected="True + 64-hex hash",
            observed=(
                f"eligible={r.record.retraining_eligible}, "
                f"hash_len={len(r.record.input_features_hash)}"
                if r.record and r.record.input_features_hash
                else "None"),
            matched=(
                r.record is not None
                and r.record.retraining_eligible is True
                and r.record.input_features_hash is not None
                and len(r.record.input_features_hash) == 64)),
    )


SCENARIO_ADJ_01_RECORD = Scenario(
    scenario_id="ADJ-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-282 record_adjudication captures clean operator "
        "override: model recommends APPROVE, operator chose "
        "REJECT with DOMAIN_KNOWLEDGE reason, "
        "retraining_eligible=True with input_features_hash "
        "present. Per Rule 1, full provenance preserved + "
        "lineage to training data. Per Rule 7, engine returns "
        "RecordingOutcome.RECORDED — caller appends to their "
        "adjudication storage."),
    setup=_setup_adj,
    actions=_actions_adj_record,
    assertions=_assertions_adj_record,
    requires_engines=("mlops_adjudication_log",))


# ADJ-02 — override rate computation excludes PENDING + ESCALATED
def _actions_adj_rate(engines: EngineBundle) -> None:
    from utils.mlops_adjudication_log import (
        MLOpsAdjudicationLogEngine, AdjudicationRecord,
        AgreementStatus, OverrideReason, TimeWindow,
        TimeWindowUnit)
    eng = MLOpsAdjudicationLogEngine()
    # 4 records: 1 ACCEPTED, 2 OVERRIDDEN, 1 PENDING
    # decided = 3, overridden = 2 → rate = 2/3
    base = dict(
        model_id="doc_classifier",
        model_version="1.0",
        recommendation="A",
        recommendation_class="APPROVE",
        operator_decision="A",
        operator_id="op",
        override_reason_text="",
        input_features_hash=None,
        retraining_eligible=False,
        notes="")
    records = (
        AdjudicationRecord(
            event_id="E1",
            agreement_status=AgreementStatus.ACCEPTED,
            decision_at_iso="2026-05-01T10:00:00Z",
            override_reason=None, **base),
        AdjudicationRecord(
            event_id="E2",
            agreement_status=AgreementStatus.OVERRIDDEN,
            decision_at_iso="2026-05-01T11:00:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
            **base),
        AdjudicationRecord(
            event_id="E3",
            agreement_status=AgreementStatus.OVERRIDDEN,
            decision_at_iso="2026-05-01T12:00:00Z",
            override_reason=OverrideReason.POLICY_OVERRIDE,
            **base),
        AdjudicationRecord(
            event_id="E4",
            agreement_status=AgreementStatus.PENDING,
            decision_at_iso="2026-05-01T13:00:00Z",
            override_reason=None, **base),
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")
    engines["__adj02__"] = eng.compute_override_rate(
        records, "doc_classifier", window)


def _assertions_adj_rate(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    m = engines.get("__adj02__")
    if m is None:
        return (AssertionResult(
            assertion_id="adj02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    expected_rate = Decimal(2) / Decimal(3)
    return (
        AssertionResult(
            assertion_id="adj02-a1",
            description=(
                "Total count 4 (all records in window)"),
            expected="4",
            observed=str(m.count_total),
            matched=m.count_total == 4),
        AssertionResult(
            assertion_id="adj02-a2",
            description=(
                "Override rate = 2/3 (PENDING excluded from "
                "denominator)"),
            expected=str(expected_rate),
            observed=str(m.override_rate),
            matched=m.override_rate == expected_rate),
        AssertionResult(
            assertion_id="adj02-a3",
            description="PENDING count surfaced separately",
            expected="1",
            observed=str(m.count_pending),
            matched=m.count_pending == 1),
        AssertionResult(
            assertion_id="adj02-a4",
            description=(
                "Per Rule 7 — engine never decides 'rate too "
                "high → trigger retraining' (ENH-283 territory)"),
            expected=(
                "ENH-283 retraining scheduler boundary cited"),
            observed=" / ".join(m.framework_refs),
            matched=any(
                "ENH-283" in r and "retraining" in r.lower()
                for r in m.framework_refs)),
    )


SCENARIO_ADJ_02_RATE = Scenario(
    scenario_id="ADJ-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-282 compute_override_rate over 24-hour window with "
        "4 records (1 ACCEPTED + 2 OVERRIDDEN + 1 PENDING). "
        "Override rate = 2/3 (PENDING excluded from denominator "
        "since not yet decided). PENDING count surfaced "
        "separately per Rule 1. Per Rule 7, engine never "
        "decides 'rate too high → trigger retraining' (that is "
        "ENH-283 retraining scheduler territory — boundary "
        "cited in framework_refs)."),
    setup=_setup_adj,
    actions=_actions_adj_rate,
    assertions=_assertions_adj_rate,
    requires_engines=("mlops_adjudication_log",))


# ADJ-03 — class-level uneven detection surfaces bias signal
def _actions_adj_class_patterns(engines: EngineBundle) -> None:
    from utils.mlops_adjudication_log import (
        MLOpsAdjudicationLogEngine, AdjudicationRecord,
        AgreementStatus, OverrideReason, TimeWindow,
        TimeWindowUnit, RecommendationClassTaxonomy)
    eng = MLOpsAdjudicationLogEngine()
    # Build imbalanced distribution:
    # APPROVE: 50 decisions, 15 OVERRIDDEN (30%)
    # REJECT: 30 decisions, 24 OVERRIDDEN (80%)
    # Overall: 39/80 = 48.75%
    # APPROVE deviation: 18.75pp (below 20pp threshold)
    # REJECT deviation: 31.25pp (above threshold) → flagged
    records = []
    base = dict(
        model_id="doc_classifier",
        model_version="1.0",
        operator_decision="X",
        operator_id="op",
        override_reason_text="",
        input_features_hash=None,
        retraining_eligible=False,
        notes="")
    for i in range(15):
        records.append(AdjudicationRecord(
            event_id=f"AO{i}",
            recommendation="A", recommendation_class="APPROVE",
            agreement_status=AgreementStatus.OVERRIDDEN,
            decision_at_iso=(
                f"2026-05-01T{(8 + i % 12):02d}:"
                f"{(i % 60):02d}:00Z"),
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
            **base))
    for i in range(35):
        records.append(AdjudicationRecord(
            event_id=f"AA{i}",
            recommendation="A", recommendation_class="APPROVE",
            agreement_status=AgreementStatus.ACCEPTED,
            decision_at_iso=(
                f"2026-05-01T{(8 + i % 12):02d}:"
                f"{(i % 60):02d}:00Z"),
            override_reason=None,
            **base))
    for i in range(24):
        records.append(AdjudicationRecord(
            event_id=f"RO{i}",
            recommendation="R", recommendation_class="REJECT",
            agreement_status=AgreementStatus.OVERRIDDEN,
            decision_at_iso=(
                f"2026-05-01T{(8 + i % 12):02d}:"
                f"{(i % 60):02d}:00Z"),
            override_reason=OverrideReason.POLICY_OVERRIDE,
            **base))
    for i in range(6):
        records.append(AdjudicationRecord(
            event_id=f"RA{i}",
            recommendation="R", recommendation_class="REJECT",
            agreement_status=AgreementStatus.ACCEPTED,
            decision_at_iso=(
                f"2026-05-01T{(8 + i % 12):02d}:"
                f"{(i % 60):02d}:00Z"),
            override_reason=None,
            **base))

    taxonomy = (
        RecommendationClassTaxonomy(
            class_id="APPROVE",
            description="Approve recommendation",
            minimum_sample_size=20),
        RecommendationClassTaxonomy(
            class_id="REJECT",
            description="Reject recommendation",
            is_protected_class=True,
            minimum_sample_size=20),
    )
    window = TimeWindow(
        duration=48, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T23:59:00Z")
    engines["__adj03__"] = (
        eng.compute_class_level_override_patterns(
            records, "doc_classifier", taxonomy, window,
            uneven_threshold_pct=Decimal("0.20")))


def _assertions_adj_class_patterns(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    p = engines.get("__adj03__")
    if p is None:
        return (AssertionResult(
            assertion_id="adj03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    by_class = {pat.class_id: pat for pat in p.patterns}
    return (
        AssertionResult(
            assertion_id="adj03-a1",
            description=(
                "REJECT flagged_uneven=True (31.25pp deviation"
                " from 48.75% overall ≥ 20pp threshold)"),
            expected="True",
            observed=str(by_class["REJECT"].flagged_uneven),
            matched=(
                by_class["REJECT"].flagged_uneven is True)),
        AssertionResult(
            assertion_id="adj03-a2",
            description=(
                "APPROVE flagged_uneven=False (18.75pp "
                "deviation < 20pp threshold)"),
            expected="False",
            observed=str(by_class["APPROVE"].flagged_uneven),
            matched=(
                by_class["APPROVE"].flagged_uneven is False)),
        AssertionResult(
            assertion_id="adj03-a3",
            description=(
                "is_protected_class flag preserved through "
                "pattern computation"),
            expected="True",
            observed=str(
                by_class["REJECT"].is_protected_class),
            matched=(
                by_class["REJECT"].is_protected_class is True)),
        AssertionResult(
            assertion_id="adj03-a4",
            description=(
                "Per Rule 7 — engine surfaces uneven rate as "
                "BIAS SIGNAL; bias DECISION belongs to "
                "model_governance arc at G124 (boundary cited "
                "in framework_refs)"),
            expected=(
                "model_governance + G124 boundary cited"),
            observed=" / ".join(p.framework_refs),
            matched=any(
                "G124" in r or "model_governance" in r
                for r in p.framework_refs)),
    )


SCENARIO_ADJ_03_CLASS_PATTERNS = Scenario(
    scenario_id="ADJ-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-282 compute_class_level_override_patterns on "
        "imbalanced distribution: APPROVE 50 decisions / 30% "
        "override rate (deviation 18.75pp), REJECT 30 decisions "
        "/ 80% override rate (deviation 31.25pp). With 20pp "
        "threshold and 20-record minimum sample, REJECT flags "
        "as uneven; APPROVE does not. Per Rule 7, engine "
        "surfaces uneven rate as BIAS SIGNAL — bias DECISION "
        "belongs to model_governance arc at G124. Boundary "
        "preserved."),
    setup=_setup_adj,
    actions=_actions_adj_class_patterns,
    assertions=_assertions_adj_class_patterns,
    requires_engines=("mlops_adjudication_log",))


# ADJ-04 — retraining dataset filters with explicit exclusion counts
def _actions_adj_retraining(engines: EngineBundle) -> None:
    from utils.mlops_adjudication_log import (
        MLOpsAdjudicationLogEngine, AdjudicationRecord,
        AgreementStatus, OverrideReason)
    eng = MLOpsAdjudicationLogEngine()
    base = dict(
        model_id="doc_classifier",
        model_version="1.0",
        recommendation="APPROVE",
        recommendation_class="APPROVE",
        operator_decision="REJECT",
        operator_id="op",
        override_reason_text="",
        notes="")
    records = (
        # Eligible + hash → included (1 example)
        AdjudicationRecord(
            event_id="E1",
            agreement_status=AgreementStatus.OVERRIDDEN,
            decision_at_iso="2026-05-01T10:00:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
            input_features_hash="a" * 64,
            retraining_eligible=True, **base),
        # Overridden but not eligible → excluded
        AdjudicationRecord(
            event_id="E2",
            agreement_status=AgreementStatus.OVERRIDDEN,
            decision_at_iso="2026-05-01T11:00:00Z",
            override_reason=OverrideReason.OTHER,
            input_features_hash="b" * 64,
            retraining_eligible=False, **base),
        # Accepted → not in candidates at all
        AdjudicationRecord(
            event_id="E3",
            agreement_status=AgreementStatus.ACCEPTED,
            decision_at_iso="2026-05-01T12:00:00Z",
            override_reason=None,
            input_features_hash=None,
            retraining_eligible=False, **base),
    )
    engines["__adj04__"] = (
        eng.build_retraining_candidate_dataset(
            records, "doc_classifier",
            "2.0.0-candidate",
            minimum_count_threshold=10))


def _assertions_adj_retraining(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    d = engines.get("__adj04__")
    if d is None:
        return (AssertionResult(
            assertion_id="adj04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="adj04-a1",
            description=(
                "1 example included (eligible + has hash)"),
            expected="1",
            observed=str(len(d.examples)),
            matched=len(d.examples) == 1),
        AssertionResult(
            assertion_id="adj04-a2",
            description=(
                "1 excluded as not-eligible (overridden but "
                "retraining_eligible=False — surfaced "
                "explicitly per Rule 1)"),
            expected="1",
            observed=str(d.examples_excluded_not_eligible),
            matched=(
                d.examples_excluded_not_eligible == 1)),
        AssertionResult(
            assertion_id="adj04-a3",
            description=(
                "insufficient_examples=True (1 < 10 threshold)"),
            expected="True",
            observed=str(d.insufficient_examples),
            matched=d.insufficient_examples is True),
        AssertionResult(
            assertion_id="adj04-a4",
            description=(
                "Per Rule 7 — insufficient flag surfaces but "
                "does not block; engine selects + structures "
                "(never trains; caller invokes pipeline)"),
            expected="ENH-282 + Rule 7 + selects/structures",
            observed=" / ".join(d.framework_refs),
            matched=(
                any("ENH-282" in r for r in d.framework_refs)
                and any(
                    "Rule 7" in r and "never trains" in r
                    for r in d.framework_refs))),
    )


SCENARIO_ADJ_04_RETRAINING = Scenario(
    scenario_id="ADJ-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-282 build_retraining_candidate_dataset filters 3 "
        "records (1 eligible+hash → INCLUDED, 1 overridden but "
        "not eligible → EXCLUDED, 1 ACCEPTED → not in "
        "candidates). examples_excluded_not_eligible=1 surfaced "
        "explicitly per Rule 1. insufficient_examples=True "
        "since 1 < 10 threshold. Per Rule 7, engine selects + "
        "structures dataset; never trains (caller invokes "
        "training pipeline). Surfaces what dropped out and why."),
    setup=_setup_adj,
    actions=_actions_adj_retraining,
    assertions=_assertions_adj_retraining,
    requires_engines=("mlops_adjudication_log",))


# ════════════════════════════════════════════════════════════════════════
# v10.83 — ENH-283 MLOps Retraining Scheduler (ml_governance arc 3/N)
# ════════════════════════════════════════════════════════════════════════

def _setup_rtr(engines: EngineBundle) -> None:
    pass


# RTR-01 — freshness STALE drives DUE outcome
def _actions_rtr_freshness_stale(engines: EngineBundle) -> None:
    from utils.mlops_retraining_scheduler import (
        MLOpsRetrainingSchedulerEngine, FreshnessPolicy,
        RetrainingPolicy)
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = eng.evaluate_freshness(
        model_id="doc_classifier",
        model_version="1.0.0",
        training_completed_at_iso="2025-09-01T00:00:00Z",
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    rec = eng.compute_retraining_recommendation(
        model_id="doc_classifier",
        model_version="1.0.0",
        freshness=fresh,
        override_signal=None,
        drift_signal=None,
        policy=RetrainingPolicy(require_freshness=True))
    engines["__rtr01_fresh__"] = fresh
    engines["__rtr01_rec__"] = rec


def _assertions_rtr_freshness_stale(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_retraining_scheduler import (
        FreshnessSeverity, RetrainingOutcome)
    fresh = engines.get("__rtr01_fresh__")
    rec = engines.get("__rtr01_rec__")
    if fresh is None or rec is None:
        return (AssertionResult(
            assertion_id="rtr01-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rtr01-a1",
            description=(
                "Age ~242 days computed (Sep 2025 → May 2026)"),
            expected="≥240 days",
            observed=str(fresh.age_days),
            matched=(
                fresh.age_days is not None
                and fresh.age_days >= 240)),
        AssertionResult(
            assertion_id="rtr01-a2",
            description=(
                "Severity STALE (age ≥ 90 days threshold)"),
            expected=FreshnessSeverity.STALE.value,
            observed=fresh.severity.value,
            matched=fresh.severity == FreshnessSeverity.STALE),
        AssertionResult(
            assertion_id="rtr01-a3",
            description=(
                "Recommendation DUE (any CRITICAL/STALE → DUE)"),
            expected=RetrainingOutcome.DUE.value,
            observed=rec.outcome.value,
            matched=rec.outcome == RetrainingOutcome.DUE),
        AssertionResult(
            assertion_id="rtr01-a4",
            description=(
                "Per Rule 7 — engine never auto-triggers "
                "retraining (operator + ML team execute)"),
            expected=(
                "auto-triggers retraining boundary cited"),
            observed=" / ".join(rec.framework_refs),
            matched=any(
                "never auto-triggers" in r.lower()
                or "operator + ML team execute" in r
                for r in rec.framework_refs)),
    )


SCENARIO_RTR_01_FRESHNESS_STALE = Scenario(
    scenario_id="RTR-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-283 evaluate_freshness on 8-month-old model with "
        "30/90 day warning/stale thresholds: age ≥ 240 days, "
        "severity STALE. Recommendation DUE. Per Rule 7, "
        "engine surfaces severity but never auto-triggers — "
        "operator + ML team execute the next training run."),
    setup=_setup_rtr,
    actions=_actions_rtr_freshness_stale,
    assertions=_assertions_rtr_freshness_stale,
    requires_engines=("mlops_retraining_scheduler",))


# RTR-02 — INSUFFICIENT_DATA preserved when timestamp missing
def _actions_rtr_insufficient(engines: EngineBundle) -> None:
    from utils.mlops_retraining_scheduler import (
        MLOpsRetrainingSchedulerEngine, FreshnessPolicy,
        RetrainingPolicy)
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = eng.evaluate_freshness(
        model_id="legacy_model",
        model_version="1.0.0",
        training_completed_at_iso=None,
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    rec = eng.compute_retraining_recommendation(
        model_id="legacy_model",
        model_version="1.0.0",
        freshness=fresh,
        override_signal=None,
        drift_signal=None,
        policy=RetrainingPolicy(require_freshness=True))
    engines["__rtr02_fresh__"] = fresh
    engines["__rtr02_rec__"] = rec


def _assertions_rtr_insufficient(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_retraining_scheduler import (
        FreshnessSeverity, RetrainingOutcome)
    fresh = engines.get("__rtr02_fresh__")
    rec = engines.get("__rtr02_rec__")
    if fresh is None or rec is None:
        return (AssertionResult(
            assertion_id="rtr02-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rtr02-a1",
            description=(
                "age_days=None when timestamp missing "
                "(Rule 1 — engine never fabricates)"),
            expected="None",
            observed=str(fresh.age_days),
            matched=fresh.age_days is None),
        AssertionResult(
            assertion_id="rtr02-a2",
            description=(
                "Severity INSUFFICIENT_DATA preserved"),
            expected=(
                FreshnessSeverity.INSUFFICIENT_DATA.value),
            observed=fresh.severity.value,
            matched=(
                fresh.severity
                == FreshnessSeverity.INSUFFICIENT_DATA)),
        AssertionResult(
            assertion_id="rtr02-a3",
            description=(
                "Recommendation INSUFFICIENT_DATA — required "
                "signal missing, engine doesn't default to "
                "NOT_YET"),
            expected=(
                RetrainingOutcome.INSUFFICIENT_DATA.value),
            observed=rec.outcome.value,
            matched=(
                rec.outcome
                == RetrainingOutcome.INSUFFICIENT_DATA)),
        AssertionResult(
            assertion_id="rtr02-a4",
            description=(
                "Rationale cites missing required signal"),
            expected=(
                "freshness signal required by policy but "
                "INSUFFICIENT_DATA"),
            observed=rec.rationale,
            matched=(
                "freshness signal required" in rec.rationale)),
    )


SCENARIO_RTR_02_INSUFFICIENT = Scenario(
    scenario_id="RTR-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-283 INSUFFICIENT_DATA propagation: legacy model "
        "with no training_completed_at_iso → freshness "
        "INSUFFICIENT_DATA → recommendation "
        "INSUFFICIENT_DATA when require_freshness=True. Per "
        "Rule 1, engine surfaces missing signal explicitly "
        "rather than defaulting to NOT_YET (the canonical "
        "case is models registered before training "
        "instrumentation was added — operator must investigate)."),
    setup=_setup_rtr,
    actions=_actions_rtr_insufficient,
    assertions=_assertions_rtr_insufficient,
    requires_engines=("mlops_retraining_scheduler",))


# RTR-03 — three-signal combination drives DUE
def _actions_rtr_combined(engines: EngineBundle) -> None:
    from utils.mlops_retraining_scheduler import (
        MLOpsRetrainingSchedulerEngine, FreshnessPolicy,
        OverrideThresholds, DriftThresholds,
        RetrainingPolicy)
    eng = MLOpsRetrainingSchedulerEngine()
    fresh = eng.evaluate_freshness(
        model_id="credit_scorer",
        model_version="2.0.0",
        training_completed_at_iso="2026-04-15T00:00:00Z",
        as_of_iso="2026-05-01T00:00:00Z",
        policy=FreshnessPolicy(
            warning_age_days=30, stale_age_days=90))
    override = eng.evaluate_override_signal(
        model_id="credit_scorer",
        current_rate=Decimal("0.45"),  # high
        thresholds=OverrideThresholds(
            warning_rate=Decimal("0.20"),
            critical_rate=Decimal("0.40")))
    drift = eng.evaluate_drift_signal(
        model_id="credit_scorer",
        current_value=Decimal("0.30"),  # PSI severe
        thresholds=DriftThresholds(
            warning_value=Decimal("0.10"),
            critical_value=Decimal("0.25"),
            metric_name="PSI"))
    rec = eng.compute_retraining_recommendation(
        model_id="credit_scorer",
        model_version="2.0.0",
        freshness=fresh,
        override_signal=override,
        drift_signal=drift,
        policy=RetrainingPolicy(
            require_freshness=True,
            require_override_signal=True,
            require_drift_signal=True))
    engines["__rtr03_rec__"] = rec


def _assertions_rtr_combined(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_retraining_scheduler import (
        FreshnessSeverity, OverrideSignalSeverity,
        DriftSignalSeverity, RetrainingOutcome)
    rec = engines.get("__rtr03_rec__")
    if rec is None:
        return (AssertionResult(
            assertion_id="rtr03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rtr03-a1",
            description=(
                "Outcome DUE (override CRITICAL + drift "
                "CRITICAL drive DUE even with FRESH freshness)"),
            expected=RetrainingOutcome.DUE.value,
            observed=rec.outcome.value,
            matched=rec.outcome == RetrainingOutcome.DUE),
        AssertionResult(
            assertion_id="rtr03-a2",
            description=(
                "Override severity CRITICAL (0.45 ≥ 0.40 "
                "threshold)"),
            expected=(
                OverrideSignalSeverity.CRITICAL.value),
            observed=(
                rec.override_signal.severity.value
                if rec.override_signal else "None"),
            matched=(
                rec.override_signal is not None
                and rec.override_signal.severity
                == OverrideSignalSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="rtr03-a3",
            description=(
                "Drift severity CRITICAL (PSI 0.30 ≥ 0.25 "
                "threshold)"),
            expected=DriftSignalSeverity.CRITICAL.value,
            observed=(
                rec.drift_signal.severity.value
                if rec.drift_signal else "None"),
            matched=(
                rec.drift_signal is not None
                and rec.drift_signal.severity
                == DriftSignalSeverity.CRITICAL)),
        AssertionResult(
            assertion_id="rtr03-a4",
            description=(
                "Per Rule 1 — all three contributions surface "
                "in rationale (operator sees full picture)"),
            expected=(
                "freshness=, override=, drift= all in "
                "rationale"),
            observed=rec.rationale,
            matched=(
                "freshness=" in rec.rationale
                and "override=" in rec.rationale
                and "drift=" in rec.rationale)),
    )


SCENARIO_RTR_03_COMBINED = Scenario(
    scenario_id="RTR-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-283 three-signal combination: FRESH freshness "
        "(16 days old) + CRITICAL override (0.45 vs 0.40 "
        "threshold) + CRITICAL drift (PSI 0.30 vs 0.25 "
        "threshold). Outcome DUE — any CRITICAL drives DUE. "
        "Per Rule 1, all three contributions surface in "
        "rationale. Demonstrates that production observation "
        "(override + drift) overrides freshness signal alone."),
    setup=_setup_rtr,
    actions=_actions_rtr_combined,
    assertions=_assertions_rtr_combined,
    requires_engines=("mlops_retraining_scheduler",))


# RTR-04 — fleet calendar sorts by urgency
def _actions_rtr_calendar(engines: EngineBundle) -> None:
    from utils.mlops_retraining_scheduler import (
        MLOpsRetrainingSchedulerEngine, FreshnessPolicy,
        RetrainingPolicy)
    eng = MLOpsRetrainingSchedulerEngine()

    def _build_rec(model_id, age_iso):
        fresh = eng.evaluate_freshness(
            model_id=model_id,
            model_version="1.0",
            training_completed_at_iso=age_iso,
            as_of_iso="2026-05-01T00:00:00Z",
            policy=FreshnessPolicy(30, 90))
        return eng.compute_retraining_recommendation(
            model_id=model_id,
            model_version="1.0",
            freshness=fresh,
            override_signal=None,
            drift_signal=None,
            policy=RetrainingPolicy(require_freshness=True))

    recs = (
        _build_rec(
            "ok_model", "2026-04-25T00:00:00Z"),     # FRESH
        _build_rec(
            "stale_model", "2025-09-01T00:00:00Z"),  # STALE → DUE
        _build_rec(
            "warn_model", "2026-03-01T00:00:00Z"),   # WARNING → SOON
    )
    engines["__rtr04__"] = (
        eng.build_retraining_calendar(recs))


def _assertions_rtr_calendar(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    cal = engines.get("__rtr04__")
    if cal is None:
        return (AssertionResult(
            assertion_id="rtr04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="rtr04-a1",
            description=(
                "First entry is DUE (stale_model)"),
            expected="stale_model",
            observed=(
                cal.entries[0].model_id
                if cal.entries else "empty"),
            matched=(
                len(cal.entries) > 0
                and cal.entries[0].model_id == "stale_model")),
        AssertionResult(
            assertion_id="rtr04-a2",
            description="Second entry is SOON (warn_model)",
            expected="warn_model",
            observed=(
                cal.entries[1].model_id
                if len(cal.entries) > 1 else "missing"),
            matched=(
                len(cal.entries) > 1
                and cal.entries[1].model_id == "warn_model")),
        AssertionResult(
            assertion_id="rtr04-a3",
            description=(
                "Summary counts: 1 DUE + 1 SOON + 1 NOT_YET"),
            expected="DUE=1, SOON=1, NOT_YET=1",
            observed=(
                f"DUE={cal.summary_due}, "
                f"SOON={cal.summary_soon}, "
                f"NOT_YET={cal.summary_not_yet}"),
            matched=(
                cal.summary_due == 1
                and cal.summary_soon == 1
                and cal.summary_not_yet == 1)),
        AssertionResult(
            assertion_id="rtr04-a4",
            description=(
                "Per Rule 7 — calendar is a view, not a "
                "schedule (engine never executes retraining)"),
            expected=(
                "calendar is a view boundary cited"),
            observed=" / ".join(cal.framework_refs),
            matched=any(
                "view" in r.lower()
                and "never executes" in r.lower()
                for r in cal.framework_refs)),
    )


SCENARIO_RTR_04_CALENDAR = Scenario(
    scenario_id="RTR-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-283 build_retraining_calendar across 3 models "
        "(stale=DUE, warn=SOON, ok=NOT_YET). Calendar sorts "
        "by urgency: DUE first, then SOON, then NOT_YET. "
        "Summary counts surface alongside per-model entries "
        "per Rule 1. Per Rule 7, calendar is a view for ML "
        "team capacity planning; engine never executes "
        "retraining."),
    setup=_setup_rtr,
    actions=_actions_rtr_calendar,
    assertions=_assertions_rtr_calendar,
    requires_engines=("mlops_retraining_scheduler",))


# ════════════════════════════════════════════════════════════════════════
# v10.84 — ENH-284 MLOps A/B Comparison Harness (ml_governance arc 4/N)
# ════════════════════════════════════════════════════════════════════════

def _setup_abt(engines: EngineBundle) -> None:
    pass


def _make_abt_event(
    event_id, input_hash, version, role, predicted_class,
    latency=Decimal("100"),
):
    from utils.mlops_ab_harness import (
        PredictionEvent, PredictionRole)
    return PredictionEvent(
        event_id=event_id,
        input_features_hash=input_hash,
        model_id="doc_classifier",
        model_version=version,
        role=role,
        predicted_class=predicted_class,
        predicted_at_iso="2026-05-01T10:00:00Z",
        latency_ms=latency)


# ABT-01 — pairing surfaces unpaired events explicitly
def _actions_abt_pairing(engines: EngineBundle) -> None:
    from utils.mlops_ab_harness import (
        MLOpsABHarnessEngine, PredictionRole)
    eng = MLOpsABHarnessEngine()
    events = (
        # 2 paired
        _make_abt_event(
            "A1", "h1", "1.0", PredictionRole.ACTIVE,
            "APPROVE"),
        _make_abt_event(
            "S1", "h1", "2.0", PredictionRole.SHADOW,
            "APPROVE"),
        _make_abt_event(
            "A2", "h2", "1.0", PredictionRole.ACTIVE,
            "REJECT"),
        _make_abt_event(
            "S2", "h2", "2.0", PredictionRole.SHADOW,
            "APPROVE"),
        # 1 active-only (shadow not deployed for h3)
        _make_abt_event(
            "A3", "h3", "1.0", PredictionRole.ACTIVE,
            "APPROVE"),
        # 1 shadow-only (active didn't see h4 for some reason)
        _make_abt_event(
            "S3", "h4", "2.0", PredictionRole.SHADOW,
            "APPROVE"),
    )
    engines["__abt01__"] = eng.pair_predictions(
        events, "1.0", "2.0")


def _assertions_abt_pairing(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    r = engines.get("__abt01__")
    if r is None:
        return (AssertionResult(
            assertion_id="abt01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="abt01-a1",
            description="2 paired comparisons",
            expected="2",
            observed=str(len(r.paired)),
            matched=len(r.paired) == 2),
        AssertionResult(
            assertion_id="abt01-a2",
            description=(
                "h3 surfaces in unpaired_active_only "
                "(shadow not deployed for that input — "
                "deployment skew diagnosed per Rule 1)"),
            expected="('h3',)",
            observed=str(r.unpaired_active_only),
            matched=r.unpaired_active_only == ("h3",)),
        AssertionResult(
            assertion_id="abt01-a3",
            description=(
                "h4 surfaces in unpaired_shadow_only "
                "(active didn't see that input)"),
            expected="('h4',)",
            observed=str(r.unpaired_shadow_only),
            matched=r.unpaired_shadow_only == ("h4",)),
        AssertionResult(
            assertion_id="abt01-a4",
            description=(
                "Per pair, agreement flag preserved (h1 "
                "agree=True, h2 agree=False)"),
            expected="h1=True, h2=False",
            observed=", ".join(
                f"{p.input_features_hash}="
                f"{p.agreement}" for p in r.paired),
            matched=all(
                (p.input_features_hash == "h1"
                 and p.agreement is True)
                or (p.input_features_hash == "h2"
                    and p.agreement is False)
                for p in r.paired)),
    )


SCENARIO_ABT_01_PAIRING = Scenario(
    scenario_id="ABT-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-284 pair_predictions on mixed events: 2 paired "
        "(h1 agree, h2 disagree), 1 active-only (h3 — shadow "
        "not deployed), 1 shadow-only (h4 — active didn't "
        "see). Per Rule 1, unpaired events surface as "
        "separate explicit lists for deployment-skew "
        "diagnosis. Per Rule 7, engine pairs and surfaces; "
        "caller decides what to do with unpaired."),
    setup=_setup_abt,
    actions=_actions_abt_pairing,
    assertions=_assertions_abt_pairing,
    requires_engines=("mlops_ab_harness",))


# ABT-02 — class distribution shift surfaces novel classes
def _actions_abt_dist_shift(engines: EngineBundle) -> None:
    from utils.mlops_ab_harness import (
        MLOpsABHarnessEngine, PredictionRole)
    eng = MLOpsABHarnessEngine()
    events = []
    # Active: 70% APPROVE, 30% REJECT (no HOLD)
    for i in range(70):
        events.append(_make_abt_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE, "APPROVE"))
    for i in range(30):
        events.append(_make_abt_event(
            f"AR{i}", f"hr{i}", "1.0",
            PredictionRole.ACTIVE, "REJECT"))
    # Shadow: 50% APPROVE, 30% REJECT, 20% HOLD (novel class!)
    for i in range(50):
        events.append(_make_abt_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW, "APPROVE"))
    for i in range(30):
        events.append(_make_abt_event(
            f"SR{i}", f"hr{i}", "2.0",
            PredictionRole.SHADOW, "REJECT"))
    for i in range(20):
        events.append(_make_abt_event(
            f"SH{i}", f"hh{i}", "2.0",
            PredictionRole.SHADOW, "HOLD"))

    engines["__abt02__"] = (
        eng.compute_class_distribution_shift(
            events, "1.0", "2.0"))


def _assertions_abt_dist_shift(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    s = engines.get("__abt02__")
    if s is None:
        return (AssertionResult(
            assertion_id="abt02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    by_class = {d.class_label: d for d in s.deltas}
    return (
        AssertionResult(
            assertion_id="abt02-a1",
            description=(
                "Active: 70 APPROVE / 30 REJECT (total 100); "
                "Shadow: 50 APPROVE / 30 REJECT / 20 HOLD "
                "(total 100)"),
            expected="A=100, S=100",
            observed=(
                f"A={s.total_active_predictions}, "
                f"S={s.total_shadow_predictions}"),
            matched=(
                s.total_active_predictions == 100
                and s.total_shadow_predictions == 100)),
        AssertionResult(
            assertion_id="abt02-a2",
            description=(
                "APPROVE share delta -0.20 (shadow predicts "
                "fewer APPROVEs)"),
            expected="-0.20",
            observed=str(by_class["APPROVE"].share_delta),
            matched=(
                by_class["APPROVE"].share_delta
                == Decimal("-0.20"))),
        AssertionResult(
            assertion_id="abt02-a3",
            description=(
                "HOLD class surfaces with active_count=0 "
                "(novel class shadow predicts that active "
                "never did — Rule 1 surfaces explicitly)"),
            expected="active=0, shadow=20",
            observed=(
                f"active={by_class['HOLD'].active_count}, "
                f"shadow={by_class['HOLD'].shadow_count}"),
            matched=(
                by_class["HOLD"].active_count == 0
                and by_class["HOLD"].shadow_count == 20)),
        AssertionResult(
            assertion_id="abt02-a4",
            description=(
                "All 3 classes (APPROVE, REJECT, HOLD) "
                "surface — engine never silently drops"),
            expected="3",
            observed=str(len(s.deltas)),
            matched=len(s.deltas) == 3),
    )


SCENARIO_ABT_02_DIST_SHIFT = Scenario(
    scenario_id="ABT-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-284 compute_class_distribution_shift on active "
        "(70% APPROVE / 30% REJECT) vs shadow (50% APPROVE / "
        "30% REJECT / 20% HOLD — novel class). APPROVE share "
        "delta -0.20. HOLD class surfaces with active_count=0 "
        "per Rule 1 (engine never silently drops; operator "
        "sees novel classes shadow predicts that active never "
        "did). Per Rule 7, engine surfaces shift; never "
        "decides 'shift too large → block promotion'."),
    setup=_setup_abt,
    actions=_actions_abt_dist_shift,
    assertions=_assertions_abt_dist_shift,
    requires_engines=("mlops_ab_harness",))


# ABT-03 — composite report NOT_READY on low agreement
def _actions_abt_not_ready(engines: EngineBundle) -> None:
    from utils.mlops_ab_harness import (
        MLOpsABHarnessEngine, PredictionRole, ABThresholds)
    eng = MLOpsABHarnessEngine()
    events = []
    # 100 paired, 50% agreement → below critical 0.70
    for i in range(100):
        events.append(_make_abt_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE, "APPROVE"))
        # First 50 agree, next 50 disagree
        sclass = "APPROVE" if i < 50 else "REJECT"
        events.append(_make_abt_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW, sclass))
    engines["__abt03__"] = (
        eng.build_ab_comparison_report(
            events, "1.0", "2.0",
            thresholds=ABThresholds(
                minimum_paired_sample=50,
                agreement_warning_rate=Decimal("0.85"),
                agreement_critical_rate=Decimal("0.70"))))


def _assertions_abt_not_ready(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_ab_harness import ABReportSeverity
    r = engines.get("__abt03__")
    if r is None:
        return (AssertionResult(
            assertion_id="abt03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="abt03-a1",
            description=(
                "Composite severity NOT_READY (agreement "
                "0.50 < critical 0.70)"),
            expected=ABReportSeverity.NOT_READY.value,
            observed=r.composite_severity.value,
            matched=(
                r.composite_severity
                == ABReportSeverity.NOT_READY)),
        AssertionResult(
            assertion_id="abt03-a2",
            description=(
                "agreement_rate exactly 0.50 (50/100)"),
            expected="0.5",
            observed=str(r.agreement.agreement_rate),
            matched=(
                r.agreement.agreement_rate
                == Decimal("0.5"))),
        AssertionResult(
            assertion_id="abt03-a3",
            description=(
                "Rationale cites agreement_rate breach "
                "(operator sees specific reason)"),
            expected="agreement_rate breach in rationale",
            observed=r.rationale,
            matched=(
                "agreement_rate" in r.rationale
                and "critical" in r.rationale)),
        AssertionResult(
            assertion_id="abt03-a4",
            description=(
                "Per Rule 7 — rationale cites ENH-281 "
                "validate_promotion_readiness as the actual "
                "promotion gate (composite severity is a "
                "summary view, not the gate)"),
            expected=(
                "ENH-281 validate_promotion_readiness "
                "boundary cited"),
            observed=" / ".join(r.framework_refs),
            matched=any(
                "ENH-281" in ref
                and "validate_promotion_readiness" in ref
                for ref in r.framework_refs)),
    )


SCENARIO_ABT_03_NOT_READY = Scenario(
    scenario_id="ABT-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-284 build_ab_comparison_report on 100 paired "
        "predictions with 50% agreement — below critical "
        "threshold 0.70. Composite severity NOT_READY. "
        "Rationale cites the specific breach. Per Rule 7, "
        "rationale cites ENH-281 validate_promotion_readiness "
        "as the actual promotion gate (composite severity is "
        "a summary view; ENH-281 is the gate). Demonstrates "
        "the boundary between A/B comparison (this engine) "
        "and promotion gating (ENH-281)."),
    setup=_setup_abt,
    actions=_actions_abt_not_ready,
    assertions=_assertions_abt_not_ready,
    requires_engines=("mlops_ab_harness",))


# ABT-04 — composite report READY_TO_PROMOTE with cost comparison
def _actions_abt_ready_with_cost(
    engines: EngineBundle,
) -> None:
    from utils.mlops_ab_harness import (
        MLOpsABHarnessEngine, PredictionRole, ABThresholds,
        CostEstimate)
    eng = MLOpsABHarnessEngine()
    events = []
    # 100 paired, 95% agreement, equal latency
    for i in range(100):
        events.append(_make_abt_event(
            f"A{i}", f"h{i}", "1.0",
            PredictionRole.ACTIVE, "APPROVE",
            latency=Decimal("100")))
        # 5% disagreement
        sclass = "REJECT" if i < 5 else "APPROVE"
        events.append(_make_abt_event(
            f"S{i}", f"h{i}", "2.0",
            PredictionRole.SHADOW, sclass,
            latency=Decimal("110")))   # 10% latency increase
    cost_estimates = (
        CostEstimate("1.0", Decimal("0.001")),
        CostEstimate("2.0", Decimal("0.002")),
    )
    engines["__abt04__"] = (
        eng.build_ab_comparison_report(
            events, "1.0", "2.0",
            thresholds=ABThresholds(
                minimum_paired_sample=50,
                agreement_warning_rate=Decimal("0.85"),
                agreement_critical_rate=Decimal("0.70"),
                latency_regression_warning_pct=Decimal("0.20"),
                latency_regression_critical_pct=Decimal("0.50")),
            cost_estimates=cost_estimates))


def _assertions_abt_ready_with_cost(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_ab_harness import ABReportSeverity
    r = engines.get("__abt04__")
    if r is None:
        return (AssertionResult(
            assertion_id="abt04-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="abt04-a1",
            description=(
                "Composite severity READY_TO_PROMOTE "
                "(agreement 0.95 ≥ warning 0.85; latency "
                "regression 10% < warning 20%)"),
            expected=(
                ABReportSeverity.READY_TO_PROMOTE.value),
            observed=r.composite_severity.value,
            matched=(
                r.composite_severity
                == ABReportSeverity.READY_TO_PROMOTE)),
        AssertionResult(
            assertion_id="abt04-a2",
            description=(
                "Cost comparison present with delta +0.1 "
                "(active 100*0.001=0.1, shadow 100*0.002=0.2 "
                "→ delta +0.1)"),
            expected="0.1",
            observed=(
                str(r.cost.cost_delta_kes)
                if r.cost else "None"),
            matched=(
                r.cost is not None
                and r.cost.cost_delta_kes == Decimal("0.1"))),
        AssertionResult(
            assertion_id="abt04-a3",
            description=(
                "Latency regression 0.10 (10%) — present but "
                "below warning threshold 0.20"),
            expected="0.1",
            observed=str(r.latency.median_delta_pct),
            matched=(
                r.latency.median_delta_pct == Decimal("0.1"))),
        AssertionResult(
            assertion_id="abt04-a4",
            description=(
                "Rationale cites operator should still run "
                "ENH-281 promotion gates before final "
                "promotion (Rule 7 — composite severity is "
                "summary view; ENH-281 is the gate)"),
            expected=(
                "ENH-281 validate_promotion_readiness in "
                "rationale"),
            observed=r.rationale,
            matched=(
                "ENH-281" in r.rationale
                and "validate_promotion_readiness"
                in r.rationale)),
    )


SCENARIO_ABT_04_READY_WITH_COST = Scenario(
    scenario_id="ABT-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-284 build_ab_comparison_report on 100 paired "
        "predictions with 95% agreement, 10% latency "
        "regression (within tolerance), and cost estimates. "
        "Composite severity READY_TO_PROMOTE. Cost delta "
        "surfaces (+KES 0.1 over the 100-call window). "
        "Rationale cites that operator should still run "
        "ENH-281 promotion gates before final promotion — "
        "demonstrates the Rule 7 boundary that composite "
        "severity is a summary view, not the actual gate."),
    setup=_setup_abt,
    actions=_actions_abt_ready_with_cost,
    assertions=_assertions_abt_ready_with_cost,
    requires_engines=("mlops_ab_harness",))


# ════════════════════════════════════════════════════════════════════════
# v10.85 — ENH-285 MLOps Model Card Composer (ml_governance arc 5/N)
# ════════════════════════════════════════════════════════════════════════

def _setup_mcd(engines: EngineBundle) -> None:
    pass


def _make_mcd_narrative():
    from utils.mlops_model_card_composer import (
        ModelCardNarrative)
    return ModelCardNarrative(
        intended_use=(
            "Classify trade finance documents into "
            "DISCREPANT vs CLEAN buckets to focus operator "
            "review"),
        out_of_scope_use=(
            "Not for credit decisions; not for sanctions "
            "screening; advisory only"),
        training_data_description=(
            "12 months of FLEXCUBE document attachments "
            "labeled by trade ops team"),
        evaluation_data_description=(
            "Held-out 20% from same period, stratified by "
            "document type"),
        ethical_considerations=(
            "Operator-in-the-loop required; model "
            "recommendations advisory only — final decision "
            "rests with trade ops officer"),
        caveats_and_recommendations=(
            "Not validated for cross-border guarantees; "
            "rerun training quarterly per ENH-283 freshness "
            "policy"))


# MCD-01 — clean composition
def _actions_mcd_compose(engines: EngineBundle) -> None:
    from utils.mlops_model_card_composer import (
        MLOpsModelCardComposerEngine)
    eng = MLOpsModelCardComposerEngine()
    result = eng.compose_model_card(
        model_id="doc_classifier",
        model_version="2.0.0",
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        operational_status="ACTIVE",
        training_metrics={
            "accuracy": Decimal("0.87"),
            "f1": Decimal("0.85")},
        narrative=_make_mcd_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="trainer-pipeline",
        training_completed_at_iso="2026-04-30T18:00:00Z",
        notes="Quarterly retraining per ENH-283 cadence")
    engines["__mcd01__"] = result


def _assertions_mcd_compose(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_model_card_composer import (
        CardComposeOutcome)
    r = engines.get("__mcd01__")
    if r is None:
        return (AssertionResult(
            assertion_id="mcd01-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="mcd01-a1",
            description="Outcome COMPOSED",
            expected=CardComposeOutcome.COMPOSED.value,
            observed=r.outcome.value,
            matched=(
                r.outcome == CardComposeOutcome.COMPOSED)),
        AssertionResult(
            assertion_id="mcd01-a2",
            description=(
                "Card preserves model_id + version + "
                "training metrics"),
            expected=(
                "doc_classifier@2.0.0 with accuracy + f1"),
            observed=(
                f"{r.card.model_id}@{r.card.model_version} "
                f"metrics={list(r.card.training_metrics.keys())}"
                if r.card else "None"),
            matched=(
                r.card is not None
                and r.card.model_id == "doc_classifier"
                and r.card.model_version == "2.0.0"
                and "accuracy" in r.card.training_metrics
                and "f1" in r.card.training_metrics)),
        AssertionResult(
            assertion_id="mcd01-a3",
            description=(
                "Mitchell et al. 2019 cited in framework_refs"),
            expected="Mitchell + 2019",
            observed=" / ".join(r.framework_refs),
            matched=any(
                "Mitchell" in ref and "2019" in ref
                for ref in r.framework_refs)),
        AssertionResult(
            assertion_id="mcd01-a4",
            description=(
                "Per Rule 7 — engine never persists, never "
                "publishes externally"),
            expected=(
                "never persists / never publishes externally"),
            observed=" / ".join(r.framework_refs),
            matched=any(
                "never publishes" in ref.lower()
                or "regulatory_reporting territory" in ref
                for ref in r.framework_refs)),
    )


SCENARIO_MCD_01_COMPOSE = Scenario(
    scenario_id="MCD-01",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-285 compose_model_card on clean inputs: doc_"
        "classifier@2.0.0 with full narrative + training "
        "metrics. Outcome COMPOSED. Card structure follows "
        "Mitchell et al. 2019. Per Rule 7, engine constructs "
        "card; caller persists to archive (engine never "
        "publishes externally, never serializes to regulator-"
        "specific schemas — that is regulatory_reporting "
        "territory)."),
    setup=_setup_mcd,
    actions=_actions_mcd_compose,
    assertions=_assertions_mcd_compose,
    requires_engines=("mlops_model_card_composer",))


# MCD-02 — completeness gate surfaces missing sections
def _actions_mcd_completeness(engines: EngineBundle) -> None:
    from utils.mlops_model_card_composer import (
        MLOpsModelCardComposerEngine, ModelCard,
        ModelCardNarrative,
        CardCompletenessRequirements)
    eng = MLOpsModelCardComposerEngine()
    # Card with mostly-empty narrative + missing snapshot +
    # missing training timestamp
    card = ModelCard(
        model_id="m", model_version="1.0",
        framework="sklearn", framework_version="1.5",
        owner="o",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        operational_status="ACTIVE",
        training_completed_at_iso=None,
        training_metrics={"accuracy": Decimal("0.85")},
        narrative=ModelCardNarrative(
            intended_use="x", out_of_scope_use="y",
            training_data_description="z",
            evaluation_data_description="w",
            ethical_considerations="",       # missing
            caveats_and_recommendations=""),  # missing
        production_snapshot=None,
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="c")
    engines["__mcd02__"] = (
        eng.validate_card_completeness(
            card,
            CardCompletenessRequirements(
                require_narrative=True,
                require_production_snapshot=True,
                require_training_completion_timestamp=True,
                required_metric_names=("accuracy",))))


def _assertions_mcd_completeness(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    from utils.mlops_model_card_composer import (
        CompletenessOutcome)
    a = engines.get("__mcd02__")
    if a is None:
        return (AssertionResult(
            assertion_id="mcd02-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="mcd02-a1",
            description="Outcome INCOMPLETE",
            expected=(
                CompletenessOutcome.INCOMPLETE.value),
            observed=a.outcome.value,
            matched=(
                a.outcome == CompletenessOutcome.INCOMPLETE)),
        AssertionResult(
            assertion_id="mcd02-a2",
            description=(
                "ethical_considerations + "
                "caveats_and_recommendations both surface "
                "as missing per Rule 1 (not just first "
                "missing)"),
            expected=(
                "narrative.ethical_considerations and "
                "narrative.caveats_and_recommendations both "
                "in missing_sections"),
            observed=str(a.missing_sections),
            matched=(
                any("ethical_considerations" in s
                    for s in a.missing_sections)
                and any("caveats_and_recommendations" in s
                       for s in a.missing_sections))),
        AssertionResult(
            assertion_id="mcd02-a3",
            description=(
                "production_snapshot surfaces as missing"),
            expected="production_snapshot in missing",
            observed=str(a.missing_sections),
            matched=(
                "production_snapshot" in a.missing_sections)),
        AssertionResult(
            assertion_id="mcd02-a4",
            description=(
                "training_completed_at_iso surfaces as "
                "missing"),
            expected=(
                "training_completed_at_iso in missing"),
            observed=str(a.missing_sections),
            matched=(
                "training_completed_at_iso" in (
                    a.missing_sections))),
    )


SCENARIO_MCD_02_COMPLETENESS = Scenario(
    scenario_id="MCD-02",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-285 validate_card_completeness on a card with "
        "multiple gaps: missing ethical_considerations, "
        "missing caveats_and_recommendations, missing "
        "production_snapshot, missing training_completed_at_"
        "iso. Outcome INCOMPLETE. All 4 missing sections "
        "surface explicitly per Rule 1 (operator sees full "
        "picture — knows whether one edit fixes it or "
        "whether the card has multiple gaps). Per Rule 7, "
        "engine surfaces completeness; never auto-fills "
        "missing sections (those require human authorship)."),
    setup=_setup_mcd,
    actions=_actions_mcd_completeness,
    assertions=_assertions_mcd_completeness,
    requires_engines=("mlops_model_card_composer",))


# MCD-03 — diff between active and candidate cards
def _actions_mcd_diff(engines: EngineBundle) -> None:
    from utils.mlops_model_card_composer import (
        MLOpsModelCardComposerEngine)
    eng = MLOpsModelCardComposerEngine()
    # Active card v1.0
    r1 = eng.compose_model_card(
        model_id="doc_classifier",
        model_version="1.0.0",
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        operational_status="ACTIVE",
        training_metrics={
            "accuracy": Decimal("0.85"),
            "f1": Decimal("0.82")},
        narrative=_make_mcd_narrative(),
        composed_at_iso="2026-04-01T10:00:00Z",
        composed_by="trainer",
        training_completed_at_iso="2026-03-30T00:00:00Z")
    # Candidate card v2.0 with improved metrics + different status
    r2 = eng.compose_model_card(
        model_id="doc_classifier",
        model_version="2.0.0",
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash="c" * 64,
        training_data_hash="d" * 64,
        operational_status="PROPOSED",
        training_metrics={
            "accuracy": Decimal("0.91"),
            "f1": Decimal("0.88")},
        narrative=_make_mcd_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="trainer",
        training_completed_at_iso="2026-04-29T00:00:00Z")
    engines["__mcd03__"] = eng.compute_card_diff(
        r1.card, r2.card)


def _assertions_mcd_diff(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    d = engines.get("__mcd03__")
    if d is None:
        return (AssertionResult(
            assertion_id="mcd03-a0",
            description="Output populated",
            expected="present", observed="MISSING",
            matched=False),)
    by_field = {df.field_name: df for df in d.field_diffs}
    return (
        AssertionResult(
            assertion_id="mcd03-a1",
            description=(
                "model_version changed (1.0.0 → 2.0.0)"),
            expected="changed=True",
            observed=str(by_field["model_version"].changed),
            matched=(
                by_field["model_version"].changed is True)),
        AssertionResult(
            assertion_id="mcd03-a2",
            description=(
                "operational_status changed (ACTIVE → "
                "PROPOSED — typical for shadow candidate)"),
            expected="ACTIVE → PROPOSED",
            observed=(
                f"{by_field['operational_status'].old_value}"
                f" → "
                f"{by_field['operational_status'].new_value}"),
            matched=(
                by_field["operational_status"].old_value
                == "ACTIVE"
                and by_field["operational_status"].new_value
                == "PROPOSED")),
        AssertionResult(
            assertion_id="mcd03-a3",
            description=(
                "training_metrics.accuracy changed "
                "(0.85 → 0.91 improvement)"),
            expected="0.85 → 0.91",
            observed=(
                f"{by_field['training_metrics.accuracy'].old_value}"
                f" → "
                f"{by_field['training_metrics.accuracy'].new_value}"),
            matched=(
                by_field[
                    "training_metrics.accuracy"
                ].changed is True)),
        AssertionResult(
            assertion_id="mcd03-a4",
            description=(
                "Per Rule 7 — engine surfaces diff but "
                "ENH-281 validate_promotion_readiness is "
                "the actual promotion gate (cited)"),
            expected=(
                "ENH-281 validate_promotion_readiness "
                "boundary cited"),
            observed=" / ".join(d.framework_refs),
            matched=any(
                "ENH-281" in r and "validate_promotion" in r
                for r in d.framework_refs)),
    )


SCENARIO_MCD_03_DIFF = Scenario(
    scenario_id="MCD-03",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-285 compute_card_diff between active card v1.0.0 "
        "(accuracy 0.85, status ACTIVE) and candidate card "
        "v2.0.0 (accuracy 0.91, status PROPOSED). Surfaces "
        "every changed field per Rule 1 — supports operator "
        "review during promotion. Per Rule 7, engine surfaces "
        "diff; never decides 'this change is too big to "
        "allow promotion' (caller policy + ENH-281 "
        "validate_promotion_readiness territory)."),
    setup=_setup_mcd,
    actions=_actions_mcd_diff,
    assertions=_assertions_mcd_diff,
    requires_engines=("mlops_model_card_composer",))


# MCD-04 — full arc integration: card with production snapshot
def _actions_mcd_full_integration(
    engines: EngineBundle,
) -> None:
    from utils.mlops_model_card_composer import (
        MLOpsModelCardComposerEngine,
        ProductionPerformanceSnapshot)
    eng = MLOpsModelCardComposerEngine()
    # Production snapshot composed from upstream signals
    # (caller integrates ENH-282 + G124 + ENH-283 + ENH-284
    # outputs)
    snapshot = ProductionPerformanceSnapshot(
        snapshot_at_iso="2026-05-01T10:00:00Z",
        # ENH-282 output
        override_rate_30d=Decimal("0.08"),
        override_sample_size_30d=347,
        # model_governance G124 output
        drift_metric_name="PSI",
        drift_metric_value=Decimal("0.06"),
        # ENH-283 output
        last_retraining_outcome="NOT_YET",
        last_retraining_rationale=(
            "Freshness FRESH (16 days), override OK, drift OK"),
        # ENH-284 output
        last_ab_severity="READY_TO_PROMOTE",
        last_ab_against_version="2.0.0-shadow")
    result = eng.compose_model_card(
        model_id="doc_classifier",
        model_version="1.0.0",
        framework="sklearn",
        framework_version="1.5.1",
        owner="ml-team@bank",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        operational_status="ACTIVE",
        training_metrics={
            "accuracy": Decimal("0.87"),
            "f1": Decimal("0.85")},
        narrative=_make_mcd_narrative(),
        composed_at_iso="2026-05-01T10:00:00Z",
        composed_by="cockpit-page",
        training_completed_at_iso="2026-04-15T00:00:00Z",
        production_snapshot=snapshot)
    md = eng.serialize_card_to_markdown(result.card)
    engines["__mcd04_card__"] = result.card
    engines["__mcd04_md__"] = md


def _assertions_mcd_full_integration(
    engines: EngineBundle,
) -> Sequence[AssertionResult]:
    card = engines.get("__mcd04_card__")
    md = engines.get("__mcd04_md__")
    if card is None or md is None:
        return (AssertionResult(
            assertion_id="mcd04-a0",
            description="Outputs populated",
            expected="present", observed="MISSING",
            matched=False),)
    return (
        AssertionResult(
            assertion_id="mcd04-a1",
            description=(
                "ENH-282 output (override_rate_30d) preserved "
                "in production_snapshot"),
            expected="0.08",
            observed=str(
                card.production_snapshot.override_rate_30d),
            matched=(
                card.production_snapshot.override_rate_30d
                == Decimal("0.08"))),
        AssertionResult(
            assertion_id="mcd04-a2",
            description=(
                "G124 output (drift PSI 0.06) preserved"),
            expected="PSI=0.06",
            observed=(
                f"{card.production_snapshot.drift_metric_name}"
                f"="
                f"{card.production_snapshot.drift_metric_value}"),
            matched=(
                card.production_snapshot.drift_metric_name
                == "PSI"
                and card.production_snapshot.drift_metric_value
                == Decimal("0.06"))),
        AssertionResult(
            assertion_id="mcd04-a3",
            description=(
                "ENH-283 + ENH-284 outcomes preserved "
                "(NOT_YET retraining + READY_TO_PROMOTE A/B)"),
            expected=(
                "NOT_YET + READY_TO_PROMOTE"),
            observed=(
                f"{card.production_snapshot.last_retraining_outcome}"
                f" + "
                f"{card.production_snapshot.last_ab_severity}"),
            matched=(
                card.production_snapshot.last_retraining_outcome
                == "NOT_YET"
                and card.production_snapshot.last_ab_severity
                == "READY_TO_PROMOTE")),
        AssertionResult(
            assertion_id="mcd04-a4",
            description=(
                "Markdown serialization includes Production "
                "Performance section + cites all upstream "
                "signals (override / PSI / retraining / A/B)"),
            expected=(
                "Production Performance + Override rate + "
                "PSI + retraining + A/B in markdown"),
            observed=(
                "all signals present"
                if all(s in md for s in (
                    "Production Performance",
                    "Override rate",
                    "PSI",
                    "Retraining recommendation",
                    "A/B comparison"))
                else "some missing"),
            matched=all(s in md for s in (
                "Production Performance",
                "Override rate",
                "PSI",
                "Retraining recommendation",
                "A/B comparison"))),
    )


SCENARIO_MCD_04_FULL_INTEGRATION = Scenario(
    scenario_id="MCD-04",
    category=ScenarioCategory.RISK_COMPLIANCE,
    description=(
        "ENH-285 full ml_governance arc integration: "
        "compose_model_card with ProductionPerformanceSnapshot "
        "composed from ENH-282 (override 0.08) + G124 (PSI "
        "0.06) + ENH-283 (NOT_YET retraining) + ENH-284 "
        "(READY_TO_PROMOTE A/B). Markdown serialization "
        "includes all upstream signals — single documentation "
        "surface a regulator examines, all provenance for one "
        "model in one place. Demonstrates the arc closure "
        "story: every engine produces a signal that flows "
        "into the card."),
    setup=_setup_mcd,
    actions=_actions_mcd_full_integration,
    assertions=_assertions_mcd_full_integration,
    requires_engines=("mlops_model_card_composer",))


# ════════════════════════════════════════════════════════════════════════
# v10.37 closure library — appends to TREASURY_SCENARIO_LIBRARY
# ════════════════════════════════════════════════════════════════════════

# Replace the library tuple with the extended version
TREASURY_SCENARIO_LIBRARY = TREASURY_SCENARIO_LIBRARY + (
    SCENARIO_ISLAMIC_01_COMPLIANT_MURABAHA,
    SCENARIO_ISLAMIC_02_HARAM_REJECTED,
    SCENARIO_AGENT_01_LIQUIDITY_URGENT,
    SCENARIO_AGENT_02_APPROVAL_WORKFLOW,
    SCENARIO_CONN_01_KEPSS_ROUTING,
    SCENARIO_DIGITAL_01_DE_PEG_DETECTED,
    SCENARIO_UNIFIED_01_CROSS_ASSET_ROLLUP,
    SCENARIO_CLIMATE_01_FOSSIL_HAIRCUT,
    # v10.39 — Risk arc opening (Market Risk foundation)
    SCENARIO_RISK_01_PARAMETRIC_VAR,
    SCENARIO_RISK_02_BCBS_IRRBB_PNL,
    SCENARIO_RISK_03_VAR_CONVERGENCE,
    SCENARIO_RISK_04_KUPIEC_FAIL,
    SCENARIO_RISK_05_SENS_AGGREGATION,
    # v10.40 — Market Risk Limits & Breach Management
    SCENARIO_LIMITS_01_WITHIN,
    SCENARIO_LIMITS_02_VAR_BREACH,
    SCENARIO_LIMITS_03_ES_SEVERE,
    SCENARIO_LIMITS_04_CLASS_AGG,
    SCENARIO_LIMITS_05_METADATA,
    # v10.41 — Trading Book Boundary
    SCENARIO_BOUNDARY_01_LISTED_EQUITY,
    SCENARIO_BOUNDARY_02_BANKING_HEDGE,
    SCENARIO_BOUNDARY_03_PENDING,
    SCENARIO_BOUNDARY_04_APPROVAL,
    SCENARIO_BOUNDARY_05_DESK_VALIDATION,
    # v10.42 — Credit Risk IRB
    SCENARIO_IRB_01_TYPICAL_CORP,
    SCENARIO_IRB_02_DEFAULTED,
    SCENARIO_IRB_03_PD_MONOTONIC,
    SCENARIO_IRB_04_PORTFOLIO,
    # v10.43 — Operational Risk SMA
    SCENARIO_OR_01_BUCKET1_DISCRETION,
    SCENARIO_OR_02_INSUFFICIENT_HISTORY,
    SCENARIO_OR_03_ILM_MONOTONIC,
    SCENARIO_OR_04_PROVENANCE,
    # v10.44 — Stressed LCR
    SCENARIO_LR_01_BASELINE_COMPLIANT,
    SCENARIO_LR_02_SEVERE_ESCALATION,
    SCENARIO_LR_03_BANK_RUN,
    SCENARIO_LR_04_PROVENANCE,
    # v10.47 — Alternative Credit Scoring (credit_model_risk arc opens)
    SCENARIO_ALT_01_HEALTHY,
    SCENARIO_ALT_02_RISKY,
    SCENARIO_ALT_03_INSUFFICIENT,
    SCENARIO_ALT_04_PROVENANCE,
    # v10.48 — Credit Committee Governance
    SCENARIO_COM_01_APPROVE,
    SCENARIO_COM_02_QUORUM_FAILED,
    SCENARIO_COM_03_ESCALATED,
    SCENARIO_COM_04_POLICY_OVERRIDE,
    # v10.50 — Validation Agents (revenue_assurance arc opens)
    SCENARIO_RA_01_CLEAN,
    SCENARIO_RA_02_SCHEMA_VIOLATIONS,
    SCENARIO_RA_03_RECON_MISMATCH,
    SCENARIO_RA_04_ANOMALY,
    # v10.51 — Anomaly Pattern Detection
    SCENARIO_PAT_01_DUPLICATES,
    SCENARIO_PAT_02_RATE_BREACH,
    SCENARIO_PAT_03_COMMISSION,
    SCENARIO_PAT_04_ML_DISABLED,
    # v10.52 — Revenue Agentic Orchestrator
    SCENARIO_ORC_01_CROSS_ENGINE_ROUTING,
    SCENARIO_ORC_02_PAST_SLA,
    SCENARIO_ORC_03_PRIORITY_SORT,
    SCENARIO_ORC_04_STATELESS,
    # v10.53 — Partner & Supplier Reconciliation
    SCENARIO_PSR_01_PARTNER_UNDERPAY,
    SCENARIO_PSR_02_MISSING_SETTLEMENT,
    SCENARIO_PSR_03_SUPPLIER_OVERBILL,
    SCENARIO_PSR_04_ORCHESTRATOR,
    # v10.54 — Revenue Dashboard Metrics
    SCENARIO_DSH_01_LEAKAGE_TREND,
    SCENARIO_DSH_02_TOP_CATEGORIES,
    SCENARIO_DSH_03_RECOVERY,
    SCENARIO_DSH_04_COMPUTE_ALL,
    # v10.55 — Continuous Billing Verification
    SCENARIO_CBV_01_PASS,
    SCENARIO_CBV_02_HOLD,
    SCENARIO_CBV_03_REJECT_UNAUTHORIZED,
    SCENARIO_CBV_04_TAX_DISCOUNT,
    # v10.56 — Commission & Incentive Assurance
    SCENARIO_CMA_01_TIER_WALK,
    SCENARIO_CMA_02_UNDERPAID,
    SCENARIO_CMA_03_OVERRIDE,
    SCENARIO_CMA_04_DISPUTES,
    # v10.57 — Regulatory Revenue Reporting
    SCENARIO_ORR_01_GENERATE,
    SCENARIO_ORR_02_RECON,
    SCENARIO_ORR_03_UNMAPPED,
    SCENARIO_ORR_04_COMPLETENESS,
    # v10.59 — finance arc opens (ENH-249 close orchestration)
    SCENARIO_FCO_01_MISSING_ACCRUAL,
    SCENARIO_FCO_02_SUSPENSE_CRITICAL,
    SCENARIO_FCO_03_IC_PENDING,
    SCENARIO_FCO_04_ORCHESTRATOR,
    # v10.60 — ENH-250 Intercompany Matching & Elimination
    SCENARIO_ICM_01_EXACT,
    SCENARIO_ICM_02_MISMATCH,
    SCENARIO_ICM_03_UNMATCHED,
    SCENARIO_ICM_04_ORCHESTRATOR,
    # v10.61 — ENH-251 Group Consolidation operational TB
    SCENARIO_GCS_01_AGGREGATION,
    SCENARIO_GCS_02_NCI,
    SCENARIO_GCS_03_FX,
    SCENARIO_GCS_04_ELIMINATION,
    # v10.62 — ENH-252 CBK Regulatory Reporting (Enhanced)
    SCENARIO_CBK_01_CAR_PASS,
    SCENARIO_CBK_02_LIQ_BREACH,
    SCENARIO_CBK_03_SBL_BREACH,
    SCENARIO_CBK_04_FXE,
    # v10.63 — ENH-253 Predictive Financial Analytics
    SCENARIO_PFA_01_FORECAST,
    SCENARIO_PFA_02_VARIANCE,
    SCENARIO_PFA_03_DECOMPOSITION,
    SCENARIO_PFA_04_ML_DISABLED,
    # v10.64 — ENH-254 Finance Intelligence Dashboard CFO View
    SCENARIO_CFO_01_HEALTHY,
    SCENARIO_CFO_02_CAPITAL_BREACH,
    SCENARIO_CFO_03_NPL_BREACH,
    SCENARIO_CFO_04_WITH_PRIOR,
    # v10.65 — ENH-255 Financial Statement Generator
    SCENARIO_FSG_01_BALANCE_SHEET,
    SCENARIO_FSG_02_INCOME,
    SCENARIO_FSG_03_OCI,
    SCENARIO_FSG_04_FULL_PACKAGE,
    # v10.66 — ENH-256 KRA Tax Compliance
    SCENARIO_TAX_01_CORP,
    SCENARIO_TAX_02_VAT,
    SCENARIO_TAX_03_WHT,
    SCENARIO_TAX_04_DEFERRED_PKG,
    # v10.67 — ENH-257 Multi-Entity & Multi-Currency Accounting
    SCENARIO_MEC_01_JOURNAL,
    SCENARIO_MEC_02_MIXED,
    SCENARIO_MEC_03_REVALUATION,
    SCENARIO_MEC_04_TRANSFER,
    # v10.68 — ENH-258 Finance Audit & Compliance
    SCENARIO_FAC_01_SOD,
    SCENARIO_FAC_02_AUTH,
    SCENARIO_FAC_03_ATTESTATION,
    SCENARIO_FAC_04_ORCHESTRATOR,
    # v10.70 — ENH-269 Trade Finance Core Instruments (arc opening)
    SCENARIO_TFI_01_LC_CLEAN,
    SCENARIO_TFI_02_LC_INVALID,
    SCENARIO_TFI_03_AMENDMENT,
    SCENARIO_TFI_04_EXPOSURE_AGING,
    # v10.71 — ENH-273 Trade Finance Limits & Risk Management
    SCENARIO_TFL_01_COUNTRY_CP,
    SCENARIO_TFL_02_SEVERITY,
    SCENARIO_TFL_03_PRE_DEAL_BLOCK,
    SCENARIO_TFL_04_PORTFOLIO_REPORT,
    # v10.72 — ENH-272 SWIFT MT Validation
    SCENARIO_SWI_01_MT700_CLEAN,
    SCENARIO_SWI_02_MT700_INVALID,
    SCENARIO_SWI_03_CROSS_CHECK,
    SCENARIO_SWI_04_MT103,
    # v10.73 — ENH-274 Trade Finance Compliance
    SCENARIO_SCR_01_PARTY,
    SCENARIO_SCR_02_COUNTRY,
    SCENARIO_SCR_03_GOODS,
    SCENARIO_SCR_04_INSTRUMENT,
    # v10.75 — ENH-275 Trade Finance Accounting & Integration
    SCENARIO_TFA_01_CAPITAL,
    SCENARIO_TFA_02_JOURNALS,
    SCENARIO_TFA_03_UNBALANCED,
    SCENARIO_TFA_04_DISCLOSURE,
    # v10.76 — ENH-280 Trade Finance Reporting & Analytics (ML-extensible)
    SCENARIO_RPT_01_VOLUMES,
    SCENARIO_RPT_02_ANOMALY_FALLBACK,
    SCENARIO_RPT_03_ML_HOOK,
    SCENARIO_RPT_04_MGMT_REPORT,
    # v10.77 — ENH-278 Sustainable Trade Finance
    SCENARIO_SUS_01_GREEN,
    SCENARIO_SUS_02_BROWN,
    SCENARIO_SUS_03_GHG,
    SCENARIO_SUS_04_REPORT,
    # v10.78 — ENH-270 AI-Powered Document Checking (ML-extensible)
    SCENARIO_DOC_01_CONFORMING,
    SCENARIO_DOC_02_EXPIRED,
    SCENARIO_DOC_03_ML_REFINES,
    SCENARIO_DOC_04_ML_FAILURE,
    # v10.79 — ENH-271 Corporate Trade Portal
    SCENARIO_PRT_01_CLEAN_APP,
    SCENARIO_PRT_02_AMENDMENT,
    # v10.79 — ENH-276 Multi-Bank Connectivity
    SCENARIO_CON_01_CLEAN,
    SCENARIO_CON_02_ANOMALIES,
    # v10.80 — closure batch additions to bring TF arc to 40 scenarios
    SCENARIO_PRT_03_STATUS,
    SCENARIO_PRT_04_UPLOADS,
    SCENARIO_CON_03_MAPPING,
    SCENARIO_CON_04_REPORT,
    # v10.81 — ENH-281 MLOps Model Registry (ml_governance arc 1/N)
    SCENARIO_MRG_01_REGISTER,
    SCENARIO_MRG_02_MULTI_ACTIVE,
    SCENARIO_MRG_03_COMPARE,
    SCENARIO_MRG_04_PROMOTION,
    # v10.82 — ENH-282 MLOps Adjudication Log (ml_governance arc 2/N)
    SCENARIO_ADJ_01_RECORD,
    SCENARIO_ADJ_02_RATE,
    SCENARIO_ADJ_03_CLASS_PATTERNS,
    SCENARIO_ADJ_04_RETRAINING,
    # v10.83 — ENH-283 MLOps Retraining Scheduler (ml_governance arc 3/N)
    SCENARIO_RTR_01_FRESHNESS_STALE,
    SCENARIO_RTR_02_INSUFFICIENT,
    SCENARIO_RTR_03_COMBINED,
    SCENARIO_RTR_04_CALENDAR,
    # v10.84 — ENH-284 MLOps A/B Comparison Harness (ml_governance arc 4/N)
    SCENARIO_ABT_01_PAIRING,
    SCENARIO_ABT_02_DIST_SHIFT,
    SCENARIO_ABT_03_NOT_READY,
    SCENARIO_ABT_04_READY_WITH_COST,
    # v10.85 — ENH-285 MLOps Model Card Composer (ml_governance arc 5/N)
    SCENARIO_MCD_01_COMPOSE,
    SCENARIO_MCD_02_COMPLETENESS,
    SCENARIO_MCD_03_DIFF,
    SCENARIO_MCD_04_FULL_INTEGRATION,
)


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _build_test_engine_bundle() -> EngineBundle:
    """Build a fresh bundle of all engines used by Treasury scenarios."""
    from utils.treasury_alm import TreasuryALMEngine
    from utils.treasury_products import TreasuryProductsEngine
    from utils.rwa_optimization import RWAOptimizationEngine
    from utils.fund_transfer_pricing import FTPEngine
    from utils.cash_forecasting import (
        TreasuryCashForecastingEngine)
    from utils.treasury_dashboard import TreasuryDashboardEngine
    from utils.audit_core import AuditCoreEngine
    from utils.model_governance import ModelGovernanceEngine
    # v10.37 closure engines
    from utils.islamic_treasury import IslamicTreasuryEngine
    from utils.treasury_connectivity import (
        TreasuryConnectivityEngine)
    from utils.treasury_digital_assets import (
        DigitalAssetTreasuryEngine)
    # v10.39 — Risk arc opens
    from utils.market_risk_var import VaREngine
    from utils.market_risk_sensitivities import SensitivityEngine
    from utils.market_risk_factors import RiskFactorRegistry
    alm = TreasuryALMEngine()
    products = TreasuryProductsEngine()
    rwa = RWAOptimizationEngine()
    ftp = FTPEngine()
    forecast = TreasuryCashForecastingEngine()
    audit = AuditCoreEngine()
    model_gov = ModelGovernanceEngine()
    dashboard = TreasuryDashboardEngine(
        alm_engine=alm, products_engine=products,
        rwa_engine=rwa, ftp_engine=ftp,
        forecast_engine=forecast)
    islamic = IslamicTreasuryEngine()
    connectivity = TreasuryConnectivityEngine()
    digital = DigitalAssetTreasuryEngine()
    var_eng = VaREngine()
    sens_eng = SensitivityEngine()
    factor_reg = RiskFactorRegistry()
    return {
        "treasury_alm": alm,
        "treasury_products": products,
        "rwa_optimization": rwa,
        "fund_transfer_pricing": ftp,
        "cash_forecasting": forecast,
        "treasury_dashboard": dashboard,
        "audit_core": audit,
        "model_governance": model_gov,
        # v10.37
        "islamic_treasury": islamic,
        "treasury_connectivity": connectivity,
        "treasury_digital_assets": digital,
        # v10.39 — Market Risk
        "market_risk_var": var_eng,
        "market_risk_sensitivities": sens_eng,
        "market_risk_factors": factor_reg,
    }


def _test_runner_skips_when_engine_missing():
    runner = ScenarioRunner(engines={})
    result = runner.run(SCENARIO_LI_01_LCR_COMPLIANT)
    assert result.status == ScenarioStatus.SKIPPED
    assert "missing engine" in result.notes


def _test_runner_dup_scenario_raises():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    runner.run(SCENARIO_FX_01_NET_EXPOSURE)
    try:
        runner.run(SCENARIO_FX_01_NET_EXPOSURE)
        assert False
    except ValueError:
        pass


def _test_runner_requires_engines_or_factory():
    """Either engines= or bundle_factory= must be supplied."""
    try:
        ScenarioRunner()
        assert False
    except ValueError:
        pass


def _test_runner_rejects_both_modes():
    try:
        ScenarioRunner(
            engines={},
            bundle_factory=_build_test_engine_bundle)
        assert False
    except ValueError:
        pass


def _test_lcr_compliant_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_LI_01_LCR_COMPLIANT)
    assert result.status == ScenarioStatus.PASS, (
        f"unexpected status {result.status.value}; "
        f"first failure: {result.first_failure()}")
    assert result.n_failed == 0


def _test_lcr_breach_scenario_correctly_detects():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_LI_02_LCR_BREACH)
    assert result.status == ScenarioStatus.PASS, (
        f"unexpected status {result.status.value}; "
        f"first failure: {result.first_failure()}")


def _test_irrbb_outlier_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_IRRBB_01)
    assert result.status == ScenarioStatus.PASS


def _test_cap_dual_threshold_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_CAP_01_CBK_DUAL_THRESHOLD)
    assert result.status == ScenarioStatus.PASS
    assert result.n_passed == 3


def _test_fx_exposure_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_FX_01_NET_EXPOSURE)
    assert result.status == ScenarioStatus.PASS


def _test_nim_decomposition_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_NIM_01_DECOMPOSITION)
    assert result.status == ScenarioStatus.PASS


def _test_dashboard_breach_rollup_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_DASH_01_BREACH_ROLLUP)
    assert result.status == ScenarioStatus.PASS


def _test_cf_forecast_scenario_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_CF_01_FORECAST)
    assert result.status == ScenarioStatus.PASS


def _test_cf_ml_requires_provider_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_CF_02_ML_REQUIRES_PROVIDER)
    assert result.status == ScenarioStatus.PASS


def _test_modgov_registration_passes():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_MODGOV_01_REGISTRATION)
    assert result.status == ScenarioStatus.PASS, (
        f"unexpected status {result.status.value}; "
        f"first failure: {result.first_failure()}")


def _test_cross_arc_lcr_propagation_passes():
    """The cross-arc scenario tests engine composition end-to-end."""
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    result = runner.run(SCENARIO_CROSS_01_LCR_FULL_PROPAGATION)
    assert result.status == ScenarioStatus.PASS, (
        f"unexpected status {result.status.value}; "
        f"first failure: {result.first_failure()}")
    assert result.n_passed == 2


def _test_run_all_runs_full_library():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    results = runner.run_all(TREASURY_SCENARIO_LIBRARY)
    assert len(results) == len(TREASURY_SCENARIO_LIBRARY)
    failures = [
        r for r in results
        if r.status not in (
            ScenarioStatus.PASS, ScenarioStatus.SKIPPED)]
    assert len(failures) == 0, (
        f"unexpected failures: "
        f"{[(r.scenario_id, r.status.value, str(r.first_failure())) for r in failures]}")


def _test_summary_aggregates_by_category():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    runner.run_all(TREASURY_SCENARIO_LIBRARY)
    summary = runner.summary()
    assert summary["n_total"] == len(TREASURY_SCENARIO_LIBRARY)
    assert "by_category" in summary
    populated_cats = [
        cat for cat, statuses in summary["by_category"].items()
        if sum(statuses.values()) > 0]
    assert len(populated_cats) >= 4


def _test_failure_filtering():
    runner = ScenarioRunner(
        bundle_factory=_build_test_engine_bundle)
    runner.run_all(TREASURY_SCENARIO_LIBRARY)
    assert len(runner.failures()) == 0


def self_test() -> None:
    # When run directly as `python3 utils/scenario_simulator.py`,
    # the project root isn't on sys.path. Add it so engine imports
    # work the same as in integration tests.
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(_here)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    tests = [
        _test_runner_skips_when_engine_missing,
        _test_runner_dup_scenario_raises,
        _test_runner_requires_engines_or_factory,
        _test_runner_rejects_both_modes,
        _test_lcr_compliant_scenario_passes,
        _test_lcr_breach_scenario_correctly_detects,
        _test_irrbb_outlier_scenario_passes,
        _test_cap_dual_threshold_scenario_passes,
        _test_fx_exposure_scenario_passes,
        _test_nim_decomposition_scenario_passes,
        _test_dashboard_breach_rollup_scenario_passes,
        _test_cf_forecast_scenario_passes,
        _test_cf_ml_requires_provider_passes,
        _test_modgov_registration_passes,
        _test_cross_arc_lcr_propagation_passes,
        _test_run_all_runs_full_library,
        _test_summary_aggregates_by_category,
        _test_failure_filtering,
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
        print(f"✗ scenario_simulator self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ scenario_simulator self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

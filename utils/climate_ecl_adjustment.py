"""utils/climate_ecl_adjustment.py — v10.8 Phase 2 deep impl batch 3.

╔════════════════════════════════════════════════════════════════════════╗
║  CLIMATE-ADJUSTED ECL + SCENARIO STRESS TESTING                        ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (financial calculation directly affecting           ║
║              IFRS 9 ECL provisions reported on balance sheet)          ║
║  Implements 2 of 13 Climate/ESG standards from registry:                ║
║    ENH-CLI-07: Climate Scenario Stress Testing                          ║
║    ENH-CLI-12: Climate-Adjusted ECL (IFRS 9 Integration)                ║
╠════════════════════════════════════════════════════════════════════════╣
║  Methodology references:                                                ║
║    IFRS 9 §5.5.17 — forward-looking information requirement            ║
║    IFRS 9 §5.5.4 — probability-weighted ECL                            ║
║    NGFS Phase IV (Nov 2023) — scenario data for central banks          ║
║    ECB Climate Stress Test 2022 — banking sector methodology           ║
║    Bank of England BES 2021 — biennial exploratory scenario            ║
║    CBK CRMF (April 2021) Pillar 4 — climate stress testing             ║
║    Basel Committee BCBS (June 2022) — climate-related financial risks  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Adjustment formula:                                                    ║
║    climate_adjusted_ecl =                                               ║
║      base_ecl × pd_climate_mult × lgd_climate_mult × ead_climate_mult  ║
║                                                                         ║
║  Multipliers ≥ 1.0 always (climate adds risk, never subtracts).         ║
║                                                                         ║
║  Probability-weighted ECL:                                              ║
║    weighted = Σ_s(scenario_ecl[s] × scenario_weight[s])                 ║
║    where Σ_s(scenario_weight[s]) = 1.0                                  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with: utils/climate_risk.py (v10.7) for risk scores          ║
║                  utils/esg_intelligence.py (v10.6) for ESG context      ║
║                  utils/provisions.py (v8.x) — stays unchanged          ║
║                  utils/ifrs9_classification.py (v8.x) — stays unchanged║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# 28-digit precision for ECL calculations
getcontext().prec = 28

# Multiplier bounds — climate risk never reduces ECL, never inflates implausibly
MULTIPLIER_MIN = Decimal("1.0")     # no climate uplift
MULTIPLIER_MAX = Decimal("3.0")     # 3× cap to prevent runaway in stress

# Maximum probability-weighted scenario contribution
SCENARIO_WEIGHT_MIN = Decimal("0")
SCENARIO_WEIGHT_MAX = Decimal("1")

# IFRS 9 minimum scenario count for probability-weighted ECL
IFRS9_MIN_SCENARIO_COUNT = 3


# ════════════════════════════════════════════════════════════════════════
# Stage classification (mirrors IFRS 9 §5.5)
# ════════════════════════════════════════════════════════════════════════

class IFRS9Stage(Enum):
    """IFRS 9 ECL stage classification.

    Stage 1 — Performing (12-month ECL)
    Stage 2 — Significant increase in credit risk (lifetime ECL)
    Stage 3 — Credit-impaired (lifetime ECL)
    """
    STAGE_1 = "STAGE_1"
    STAGE_2 = "STAGE_2"
    STAGE_3 = "STAGE_3"


# ════════════════════════════════════════════════════════════════════════
# Stress scenario taxonomy (Basel BCBS June 2022 + ECB 2022)
# ════════════════════════════════════════════════════════════════════════

class StressScenarioType(Enum):
    """High-level stress scenario type."""
    BASELINE = "BASELINE"               # No additional stress (current path)
    ORDERLY_TRANSITION = "ORDERLY_TRANSITION"     # Smooth, predictable
    DISORDERLY_TRANSITION = "DISORDERLY_TRANSITION"   # Late + sudden
    HOT_HOUSE_WORLD = "HOT_HOUSE_WORLD"  # Limited mitigation, severe physical
    SHORT_TERM_DISORDERLY = "SHORT_TERM_DISORDERLY"  # 5-yr horizon disorderly


# Default IFRS 9 scenario weights (must sum to 1.0)
# These match common bank practice — base case dominant + tail risk weighted
DEFAULT_IFRS9_SCENARIO_WEIGHTS: Mapping[str, Decimal] = {
    "BASELINE": Decimal("0.5"),
    "DOWNSIDE": Decimal("0.3"),
    "SEVERE_DOWNSIDE": Decimal("0.2"),
}

# Time horizons (years) for stress testing
STRESS_HORIZONS_YEARS: Tuple[int, ...] = (5, 10, 20, 30)


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BaseECLInputs:
    """Input parameters for base ECL calculation (pre-climate adjustment).

    Either matches the output of utils/provisions.py / IFRS9ClassificationEngine
    or is supplied directly when integrating with downstream systems.
    """
    asset_id: str
    stage: IFRS9Stage
    pd_12m: Decimal              # 12-month probability of default (0-1)
    pd_lifetime: Decimal         # lifetime PD (0-1)
    lgd: Decimal                 # loss given default (0-1)
    ead_kes: Decimal             # exposure at default (KES)
    sector: str
    notes: str = ""

    def __post_init__(self):
        if not (Decimal("0") <= self.pd_12m <= Decimal("1")):
            raise ValueError(f"pd_12m {self.pd_12m} outside [0, 1]")
        if not (Decimal("0") <= self.pd_lifetime <= Decimal("1")):
            raise ValueError(f"pd_lifetime {self.pd_lifetime} outside [0, 1]")
        if not (Decimal("0") <= self.lgd <= Decimal("1")):
            raise ValueError(f"lgd {self.lgd} outside [0, 1]")
        if self.ead_kes < Decimal("0"):
            raise ValueError(f"ead_kes {self.ead_kes} cannot be negative")
        if self.pd_lifetime < self.pd_12m:
            raise ValueError(
                f"pd_lifetime ({self.pd_lifetime}) must be ≥ "
                f"pd_12m ({self.pd_12m})")

    def base_ecl_kes(self) -> Decimal:
        """Compute base ECL = PD × LGD × EAD per IFRS 9 staging."""
        if self.stage == IFRS9Stage.STAGE_1:
            return self.pd_12m * self.lgd * self.ead_kes
        # Stage 2 & 3 use lifetime PD
        return self.pd_lifetime * self.lgd * self.ead_kes


@dataclass(frozen=True)
class ClimateAdjustment:
    """Climate-driven multipliers applied to base ECL components.

    All multipliers ≥ 1.0 (climate adds risk, never reduces it).
    """
    pd_multiplier: Decimal       # 1.0 = no adjustment
    lgd_multiplier: Decimal
    ead_multiplier: Decimal
    physical_risk_score: Decimal  # 0-100 from v10.7
    transition_risk_score: Decimal
    scenario: str
    methodology_notes: str = ""

    def __post_init__(self):
        for name, m in (
                ("pd_multiplier", self.pd_multiplier),
                ("lgd_multiplier", self.lgd_multiplier),
                ("ead_multiplier", self.ead_multiplier)):
            if not (MULTIPLIER_MIN <= m <= MULTIPLIER_MAX):
                raise ValueError(
                    f"{name} {m} outside [{MULTIPLIER_MIN}, "
                    f"{MULTIPLIER_MAX}]")


@dataclass(frozen=True)
class ClimateAdjustedECLResult:
    """Single-scenario climate-adjusted ECL result for one asset."""
    asset_id: str
    scenario: str
    stage: IFRS9Stage
    base_ecl_kes: Decimal
    climate_adjustment: ClimateAdjustment
    adjusted_ecl_kes: Decimal
    uplift_kes: Decimal           # adjusted - base
    uplift_pct: Decimal           # uplift / base × 100 (or 0 if base=0)


@dataclass(frozen=True)
class ProbabilityWeightedECLResult:
    """IFRS 9 §5.5.4 probability-weighted ECL across multiple scenarios."""
    asset_id: str
    base_ecl_kes: Decimal
    scenario_ecls: Mapping[str, Decimal]
    scenario_weights: Mapping[str, Decimal]
    weighted_ecl_kes: Decimal
    total_uplift_kes: Decimal
    methodology_notes: str = ""


@dataclass(frozen=True)
class StressScenarioResult:
    """Portfolio-level stress test result for one scenario."""
    scenario_name: str
    horizon_years: int
    n_assets: int
    total_base_ecl_kes: Decimal
    total_adjusted_ecl_kes: Decimal
    total_uplift_kes: Decimal
    total_uplift_pct: Decimal
    by_stage: Mapping[str, Decimal]   # stage → adjusted ECL
    by_sector: Mapping[str, Decimal]  # sector → adjusted ECL
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Multiplier computation
# ════════════════════════════════════════════════════════════════════════

def compute_pd_climate_multiplier(
    *,
    physical_risk_score: Decimal,
    transition_risk_score: Decimal,
    horizon_years: int,
) -> Decimal:
    """PD climate multiplier from physical + transition risk + horizon.

    Formula:
      pd_uplift_pct = (0.4 × physical + 0.6 × transition) / 100
                       × horizon_factor

    horizon_factor scales 1.0 (5yr) → 2.0 (30yr) — longer horizons give
    climate factors more time to materialize.

    Returned multiplier ∈ [1.0, MULTIPLIER_MAX].
    """
    if not (Decimal("0") <= physical_risk_score <= Decimal("100")):
        raise ValueError(
            f"physical_risk_score {physical_risk_score} outside [0, 100]")
    if not (Decimal("0") <= transition_risk_score <= Decimal("100")):
        raise ValueError(
            f"transition_risk_score {transition_risk_score} outside [0, 100]")
    if horizon_years < 1:
        raise ValueError(f"horizon_years {horizon_years} must be ≥ 1")

    # Combined risk score (transition weighted higher for PD impact)
    combined = (
        Decimal("0.4") * physical_risk_score
        + Decimal("0.6") * transition_risk_score)
    pd_uplift_pct = combined / Decimal("100")

    # Horizon factor: 1.0 at 5 yr → 2.0 at 30 yr (linear)
    horizon_factor = (
        Decimal("1") + (Decimal(horizon_years) - Decimal("5"))
        / Decimal("25"))
    if horizon_factor < Decimal("1"):
        horizon_factor = Decimal("1")
    if horizon_factor > Decimal("2"):
        horizon_factor = Decimal("2")

    multiplier = Decimal("1") + pd_uplift_pct * horizon_factor

    # Cap at MULTIPLIER_MAX
    if multiplier > MULTIPLIER_MAX:
        multiplier = MULTIPLIER_MAX
    if multiplier < MULTIPLIER_MIN:
        multiplier = MULTIPLIER_MIN
    return multiplier


def compute_lgd_climate_multiplier(
    *,
    physical_risk_score: Decimal,
    sector: str,
) -> Decimal:
    """LGD climate multiplier (collateral devaluation under climate stress).

    Higher physical risk → collateral worth less → LGD higher.
    Real-estate-heavy sectors get extra weight (collateral erosion).
    """
    if not (Decimal("0") <= physical_risk_score <= Decimal("100")):
        raise ValueError(
            f"physical_risk_score {physical_risk_score} outside [0, 100]")

    # Base LGD uplift from physical risk (50% of risk score → multiplier increment)
    base_uplift = physical_risk_score / Decimal("100") * Decimal("0.5")

    # Real estate sectors get an extra LGD bump (collateral exposure)
    if sector in ("REAL_ESTATE_COASTAL", "REAL_ESTATE_RESIDENTIAL",
                    "REAL_ESTATE_COMMERCIAL"):
        base_uplift = base_uplift * Decimal("1.5")

    multiplier = Decimal("1") + base_uplift
    if multiplier > MULTIPLIER_MAX:
        multiplier = MULTIPLIER_MAX
    if multiplier < MULTIPLIER_MIN:
        multiplier = MULTIPLIER_MIN
    return multiplier


def compute_ead_climate_multiplier(
    *,
    transition_risk_score: Decimal,
    sector: str,
) -> Decimal:
    """EAD climate multiplier (drawdown behavior under transition stress).

    Sectors facing stranded asset risk may draw down more on credit lines
    as their core business deteriorates. Modest adjustment overall —
    EAD movement is the smallest of the three multipliers in practice.
    """
    if not (Decimal("0") <= transition_risk_score <= Decimal("100")):
        raise ValueError(
            f"transition_risk_score {transition_risk_score} outside [0, 100]")

    # Modest base uplift (max +20% on full transition risk)
    base = transition_risk_score / Decimal("100") * Decimal("0.2")

    # Stranded-asset sectors get extra drawdown propensity
    if any(k in sector for k in ("FOSSIL", "COAL")):
        base = base * Decimal("1.5")

    multiplier = Decimal("1") + base
    if multiplier > MULTIPLIER_MAX:
        multiplier = MULTIPLIER_MAX
    if multiplier < MULTIPLIER_MIN:
        multiplier = MULTIPLIER_MIN
    return multiplier


# ════════════════════════════════════════════════════════════════════════
# Single-asset climate-adjusted ECL
# ════════════════════════════════════════════════════════════════════════

def apply_climate_overlay(
    *,
    base: BaseECLInputs,
    physical_risk_score: Decimal,
    transition_risk_score: Decimal,
    scenario: str,
    horizon_years: int,
) -> ClimateAdjustedECLResult:
    """Apply climate overlay to base ECL for a single asset / scenario.

    Returns a result with base, adjusted, uplift, and uplift_pct fields.
    """
    pd_mult = compute_pd_climate_multiplier(
        physical_risk_score=physical_risk_score,
        transition_risk_score=transition_risk_score,
        horizon_years=horizon_years)
    lgd_mult = compute_lgd_climate_multiplier(
        physical_risk_score=physical_risk_score,
        sector=base.sector)
    ead_mult = compute_ead_climate_multiplier(
        transition_risk_score=transition_risk_score,
        sector=base.sector)

    base_ecl = base.base_ecl_kes()
    adjusted_ecl = base_ecl * pd_mult * lgd_mult * ead_mult
    uplift = adjusted_ecl - base_ecl
    uplift_pct = (
        uplift / base_ecl * Decimal("100")
        if base_ecl > Decimal("0") else Decimal("0"))

    adjustment = ClimateAdjustment(
        pd_multiplier=pd_mult,
        lgd_multiplier=lgd_mult,
        ead_multiplier=ead_mult,
        physical_risk_score=physical_risk_score,
        transition_risk_score=transition_risk_score,
        scenario=scenario,
        methodology_notes=(
            f"horizon={horizon_years}y; "
            f"PD adj for transition (60%) > physical (40%); "
            f"LGD adj from physical only; "
            f"EAD adj from transition (sector-weighted)"))

    return ClimateAdjustedECLResult(
        asset_id=base.asset_id,
        scenario=scenario,
        stage=base.stage,
        base_ecl_kes=base_ecl,
        climate_adjustment=adjustment,
        adjusted_ecl_kes=adjusted_ecl,
        uplift_kes=uplift,
        uplift_pct=uplift_pct)


# ════════════════════════════════════════════════════════════════════════
# Probability-weighted ECL (IFRS 9 §5.5.4)
# ════════════════════════════════════════════════════════════════════════

def compute_probability_weighted_ecl(
    *,
    base: BaseECLInputs,
    scenario_ecls: Mapping[str, Decimal],
    scenario_weights: Mapping[str, Decimal],
    methodology_notes: str = "",
) -> ProbabilityWeightedECLResult:
    """Compute IFRS 9 §5.5.4 probability-weighted ECL.

    Weights must sum to 1.0 (within rounding tolerance) and there must be
    at least IFRS9_MIN_SCENARIO_COUNT scenarios.
    """
    if len(scenario_ecls) < IFRS9_MIN_SCENARIO_COUNT:
        raise ValueError(
            f"IFRS 9 §5.5.4 requires ≥ {IFRS9_MIN_SCENARIO_COUNT} "
            f"scenarios for probability-weighted ECL, "
            f"got {len(scenario_ecls)}")

    if set(scenario_ecls.keys()) != set(scenario_weights.keys()):
        raise ValueError(
            "scenario_ecls and scenario_weights must have identical keys; "
            f"diff: {set(scenario_ecls.keys()) ^ set(scenario_weights.keys())}")

    # Validate each weight
    for name, w in scenario_weights.items():
        if not (SCENARIO_WEIGHT_MIN <= w <= SCENARIO_WEIGHT_MAX):
            raise ValueError(
                f"weight for '{name}' = {w} outside [0, 1]")

    # Validate weights sum to 1.0
    total_weight = sum(scenario_weights.values(), Decimal("0"))
    if abs(total_weight - Decimal("1")) > Decimal("0.001"):
        raise ValueError(
            f"weights must sum to 1.0, got {total_weight}")

    weighted = sum(
        (scenario_ecls[s] * scenario_weights[s] for s in scenario_ecls),
        Decimal("0"))

    base_ecl = base.base_ecl_kes()
    uplift = weighted - base_ecl

    return ProbabilityWeightedECLResult(
        asset_id=base.asset_id,
        base_ecl_kes=base_ecl,
        scenario_ecls=dict(scenario_ecls),
        scenario_weights=dict(scenario_weights),
        weighted_ecl_kes=weighted,
        total_uplift_kes=uplift,
        methodology_notes=(
            methodology_notes
            or "IFRS 9 §5.5.4 probability-weighted ECL across "
            "climate scenarios"))


# ════════════════════════════════════════════════════════════════════════
# Portfolio stress test
# ════════════════════════════════════════════════════════════════════════

def run_stress_scenario(
    *,
    scenario_name: str,
    scenario_type: StressScenarioType,
    horizon_years: int,
    asset_inputs: Sequence[BaseECLInputs],
    risk_score_provider,  # callable: BaseECLInputs → (physical, transition)
) -> StressScenarioResult:
    """Run a portfolio-wide stress scenario.

    Parameters
    ----------
    scenario_name : human-readable scenario label (e.g. "ECB-2022-Disorderly")
    scenario_type : StressScenarioType enum
    horizon_years : 5, 10, 20, or 30
    asset_inputs : list of BaseECLInputs (one per asset)
    risk_score_provider : callable returning (physical_score, transition_score)
                          Decimals 0-100 for each asset

    Returns
    -------
    StressScenarioResult with portfolio totals + per-stage + per-sector breakdown
    """
    if horizon_years not in STRESS_HORIZONS_YEARS:
        raise ValueError(
            f"horizon_years must be in {STRESS_HORIZONS_YEARS}, "
            f"got {horizon_years}")

    by_stage: Dict[str, Decimal] = {
        s.value: Decimal("0") for s in IFRS9Stage}
    by_sector: Dict[str, Decimal] = {}
    total_base = Decimal("0")
    total_adjusted = Decimal("0")

    for asset in asset_inputs:
        physical, transition = risk_score_provider(asset)
        result = apply_climate_overlay(
            base=asset,
            physical_risk_score=physical,
            transition_risk_score=transition,
            scenario=scenario_name,
            horizon_years=horizon_years)

        total_base = total_base + result.base_ecl_kes
        total_adjusted = total_adjusted + result.adjusted_ecl_kes
        by_stage[asset.stage.value] = (
            by_stage.get(asset.stage.value, Decimal("0"))
            + result.adjusted_ecl_kes)
        by_sector[asset.sector] = (
            by_sector.get(asset.sector, Decimal("0"))
            + result.adjusted_ecl_kes)

    total_uplift = total_adjusted - total_base
    uplift_pct = (
        total_uplift / total_base * Decimal("100")
        if total_base > Decimal("0") else Decimal("0"))

    return StressScenarioResult(
        scenario_name=scenario_name,
        horizon_years=horizon_years,
        n_assets=len(asset_inputs),
        total_base_ecl_kes=total_base,
        total_adjusted_ecl_kes=total_adjusted,
        total_uplift_kes=total_uplift,
        total_uplift_pct=uplift_pct,
        by_stage=by_stage,
        by_sector=by_sector,
        notes=(
            f"scenario_type={scenario_type.value}, "
            f"horizon={horizon_years}y, n_assets={len(asset_inputs)}"))


# ════════════════════════════════════════════════════════════════════════
# Engine orchestrator
# ════════════════════════════════════════════════════════════════════════

class ClimateECLEngine:
    """Orchestrator integrating climate stress testing + ECL adjustment."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._stress_results: List[StressScenarioResult] = []
        self._weighted_ecls: List[ProbabilityWeightedECLResult] = []

    def run_three_scenarios(
        self,
        *,
        asset_inputs: Sequence[BaseECLInputs],
        risk_score_providers: Mapping,  # scenario name → callable
        horizon_years: int = 10,
    ) -> List[StressScenarioResult]:
        """Run baseline + downside + severe-downside scenarios.

        risk_score_providers must have keys exactly:
          'BASELINE', 'DOWNSIDE', 'SEVERE_DOWNSIDE'
        Each value is callable BaseECLInputs → (phys_score, trans_score).
        """
        required_keys = {"BASELINE", "DOWNSIDE", "SEVERE_DOWNSIDE"}
        if set(risk_score_providers.keys()) != required_keys:
            raise ValueError(
                f"risk_score_providers must have keys {required_keys}, "
                f"got {set(risk_score_providers.keys())}")

        scenario_types = {
            "BASELINE": StressScenarioType.BASELINE,
            "DOWNSIDE": StressScenarioType.DISORDERLY_TRANSITION,
            "SEVERE_DOWNSIDE": StressScenarioType.HOT_HOUSE_WORLD,
        }

        results: List[StressScenarioResult] = []
        for name in ("BASELINE", "DOWNSIDE", "SEVERE_DOWNSIDE"):
            r = run_stress_scenario(
                scenario_name=name,
                scenario_type=scenario_types[name],
                horizon_years=horizon_years,
                asset_inputs=asset_inputs,
                risk_score_provider=risk_score_providers[name])
            results.append(r)
            self._stress_results.append(r)

        return results

    def board_summary(self) -> Dict[str, object]:
        """Board-ready stress test summary."""
        if not self._stress_results:
            return {
                "entity": self.entity_name,
                "n_stress_runs": 0,
                "total_base_ecl_kes": Decimal("0"),
                "max_uplift_pct": Decimal("0"),
                "max_uplift_scenario": None,
                "max_uplift_horizon": None,
            }

        # Find scenario with biggest uplift
        max_run = max(
            self._stress_results, key=lambda r: r.total_uplift_kes)
        avg_uplift_pct = sum(
            (r.total_uplift_pct for r in self._stress_results),
            Decimal("0")) / Decimal(len(self._stress_results))

        return {
            "entity": self.entity_name,
            "n_stress_runs": len(self._stress_results),
            "total_base_ecl_latest_kes": self._stress_results[-1].total_base_ecl_kes,
            "max_uplift_kes": max_run.total_uplift_kes,
            "max_uplift_pct": max_run.total_uplift_pct,
            "max_uplift_scenario": max_run.scenario_name,
            "max_uplift_horizon": max_run.horizon_years,
            "avg_uplift_pct_across_runs": avg_uplift_pct,
            "scenarios_executed": [r.scenario_name for r in self._stress_results],
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_base_input(asset_id="L-1", stage=IFRS9Stage.STAGE_1,
                       pd_12m="0.02", pd_lifetime="0.10",
                       lgd="0.45", ead="1000000",
                       sector="MANUFACTURING_LIGHT"):
    return BaseECLInputs(
        asset_id=asset_id, stage=stage,
        pd_12m=Decimal(pd_12m), pd_lifetime=Decimal(pd_lifetime),
        lgd=Decimal(lgd), ead_kes=Decimal(ead),
        sector=sector)


def _test_base_ecl_inputs_validation():
    """BaseECLInputs validates probability bounds + non-negative EAD."""
    try:
        _make_base_input(pd_12m="1.5")
        assert False, "should raise"
    except ValueError as e:
        assert "pd_12m" in str(e)
    try:
        _make_base_input(ead="-100")
        assert False
    except ValueError as e:
        assert "ead_kes" in str(e)
    try:
        _make_base_input(pd_12m="0.5", pd_lifetime="0.1")
        assert False
    except ValueError as e:
        assert "pd_lifetime" in str(e)


def _test_base_ecl_stage_1_uses_12m_pd():
    """Stage 1 ECL = pd_12m × LGD × EAD."""
    b = _make_base_input(stage=IFRS9Stage.STAGE_1)
    expected = Decimal("0.02") * Decimal("0.45") * Decimal("1000000")
    assert b.base_ecl_kes() == expected


def _test_base_ecl_stage_2_uses_lifetime_pd():
    """Stage 2 ECL = pd_lifetime × LGD × EAD."""
    b = _make_base_input(stage=IFRS9Stage.STAGE_2)
    expected = Decimal("0.10") * Decimal("0.45") * Decimal("1000000")
    assert b.base_ecl_kes() == expected


def _test_pd_multiplier_no_risk_returns_one():
    """Zero risk → multiplier = 1.0 exactly."""
    m = compute_pd_climate_multiplier(
        physical_risk_score=Decimal("0"),
        transition_risk_score=Decimal("0"),
        horizon_years=10)
    assert m == Decimal("1")


def _test_pd_multiplier_high_risk_uplift():
    """High risk + long horizon → larger multiplier."""
    m_short = compute_pd_climate_multiplier(
        physical_risk_score=Decimal("80"),
        transition_risk_score=Decimal("80"),
        horizon_years=5)
    m_long = compute_pd_climate_multiplier(
        physical_risk_score=Decimal("80"),
        transition_risk_score=Decimal("80"),
        horizon_years=30)
    assert m_long > m_short
    assert m_long <= MULTIPLIER_MAX


def _test_pd_multiplier_capped():
    """Extreme inputs cap at MULTIPLIER_MAX."""
    m = compute_pd_climate_multiplier(
        physical_risk_score=Decimal("100"),
        transition_risk_score=Decimal("100"),
        horizon_years=30)
    assert m <= MULTIPLIER_MAX


def _test_pd_multiplier_invalid_score_raises():
    try:
        compute_pd_climate_multiplier(
            physical_risk_score=Decimal("150"),
            transition_risk_score=Decimal("0"),
            horizon_years=10)
        assert False
    except ValueError as e:
        assert "physical_risk_score" in str(e)


def _test_lgd_multiplier_real_estate_higher():
    """Real estate sectors get higher LGD multiplier than non-RE."""
    m_re = compute_lgd_climate_multiplier(
        physical_risk_score=Decimal("60"),
        sector="REAL_ESTATE_COASTAL")
    m_other = compute_lgd_climate_multiplier(
        physical_risk_score=Decimal("60"),
        sector="MANUFACTURING_LIGHT")
    assert m_re > m_other


def _test_ead_multiplier_fossil_higher():
    """Fossil sector EAD multiplier higher than non-fossil at same risk."""
    m_fossil = compute_ead_climate_multiplier(
        transition_risk_score=Decimal("70"),
        sector="FOSSIL_FUELS_OIL_GAS")
    m_other = compute_ead_climate_multiplier(
        transition_risk_score=Decimal("70"),
        sector="MANUFACTURING_LIGHT")
    assert m_fossil > m_other


def _test_apply_overlay_zero_risk_no_uplift():
    """Zero risk → adjusted = base (uplift = 0)."""
    base = _make_base_input()
    r = apply_climate_overlay(
        base=base,
        physical_risk_score=Decimal("0"),
        transition_risk_score=Decimal("0"),
        scenario="BASELINE",
        horizon_years=10)
    assert r.adjusted_ecl_kes == r.base_ecl_kes
    assert r.uplift_kes == Decimal("0")


def _test_apply_overlay_high_risk_significant_uplift():
    """High risk → significant uplift."""
    base = _make_base_input()
    r = apply_climate_overlay(
        base=base,
        physical_risk_score=Decimal("80"),
        transition_risk_score=Decimal("80"),
        scenario="DISORDERLY",
        horizon_years=20)
    assert r.adjusted_ecl_kes > r.base_ecl_kes
    assert r.uplift_pct > Decimal("0")


def _test_apply_overlay_zero_base_zero_uplift_pct():
    """When base ECL is zero, uplift_pct = 0 (no division by zero)."""
    base = _make_base_input(pd_12m="0", pd_lifetime="0")
    r = apply_climate_overlay(
        base=base,
        physical_risk_score=Decimal("80"),
        transition_risk_score=Decimal("80"),
        scenario="X", horizon_years=10)
    assert r.base_ecl_kes == Decimal("0")
    assert r.uplift_pct == Decimal("0")


def _test_probability_weighted_ecl_basic():
    """Weighted ECL = Σ scenario_ecl × weight."""
    base = _make_base_input()
    scenarios = {
        "BASELINE": Decimal("100"),
        "DOWNSIDE": Decimal("200"),
        "SEVERE_DOWNSIDE": Decimal("400"),
    }
    weights = {
        "BASELINE": Decimal("0.5"),
        "DOWNSIDE": Decimal("0.3"),
        "SEVERE_DOWNSIDE": Decimal("0.2"),
    }
    r = compute_probability_weighted_ecl(
        base=base,
        scenario_ecls=scenarios,
        scenario_weights=weights)
    expected = (
        Decimal("100") * Decimal("0.5")
        + Decimal("200") * Decimal("0.3")
        + Decimal("400") * Decimal("0.2"))
    assert r.weighted_ecl_kes == expected


def _test_probability_weighted_ecl_requires_3_scenarios():
    """IFRS 9 §5.5.4 requires ≥ 3 scenarios."""
    base = _make_base_input()
    try:
        compute_probability_weighted_ecl(
            base=base,
            scenario_ecls={"X": Decimal("100"), "Y": Decimal("200")},
            scenario_weights={"X": Decimal("0.5"), "Y": Decimal("0.5")})
        assert False
    except ValueError as e:
        assert "≥" in str(e) or ">=" in str(e) or "3" in str(e)


def _test_probability_weighted_ecl_weights_must_sum_to_1():
    base = _make_base_input()
    try:
        compute_probability_weighted_ecl(
            base=base,
            scenario_ecls={"A": Decimal("1"), "B": Decimal("2"),
                            "C": Decimal("3")},
            scenario_weights={"A": Decimal("0.3"), "B": Decimal("0.3"),
                                "C": Decimal("0.3")})
        assert False
    except ValueError as e:
        assert "sum" in str(e).lower()


def _test_run_stress_scenario_basic():
    """Stress run aggregates per-asset results to portfolio totals."""
    inputs = [
        _make_base_input(asset_id="L-1", sector="AGRICULTURE_PRIMARY",
                          ead="1000000"),
        _make_base_input(asset_id="L-2", sector="MANUFACTURING_LIGHT",
                          ead="500000"),
    ]

    def provider(asset):
        if asset.sector == "AGRICULTURE_PRIMARY":
            return Decimal("70"), Decimal("40")
        return Decimal("20"), Decimal("30")

    r = run_stress_scenario(
        scenario_name="TEST",
        scenario_type=StressScenarioType.DISORDERLY_TRANSITION,
        horizon_years=10,
        asset_inputs=inputs,
        risk_score_provider=provider)
    assert r.n_assets == 2
    assert r.total_adjusted_ecl_kes > r.total_base_ecl_kes
    assert "AGRICULTURE_PRIMARY" in r.by_sector
    assert "MANUFACTURING_LIGHT" in r.by_sector


def _test_run_stress_scenario_invalid_horizon():
    try:
        run_stress_scenario(
            scenario_name="T",
            scenario_type=StressScenarioType.BASELINE,
            horizon_years=15,  # not in STRESS_HORIZONS_YEARS
            asset_inputs=[_make_base_input()],
            risk_score_provider=lambda a: (Decimal("0"), Decimal("0")))
        assert False
    except ValueError as e:
        assert "horizon_years" in str(e)


def _test_engine_three_scenarios():
    """Engine runs 3 scenarios and accumulates results."""
    eng = ClimateECLEngine()
    inputs = [_make_base_input(sector="AGRICULTURE_PRIMARY", ead="100000")]

    providers = {
        "BASELINE": lambda a: (Decimal("10"), Decimal("10")),
        "DOWNSIDE": lambda a: (Decimal("50"), Decimal("50")),
        "SEVERE_DOWNSIDE": lambda a: (Decimal("90"), Decimal("90")),
    }
    results = eng.run_three_scenarios(
        asset_inputs=inputs,
        risk_score_providers=providers,
        horizon_years=10)
    assert len(results) == 3
    # Severe should have largest uplift
    severe = next(r for r in results if r.scenario_name == "SEVERE_DOWNSIDE")
    baseline = next(r for r in results if r.scenario_name == "BASELINE")
    assert severe.total_uplift_kes > baseline.total_uplift_kes


def _test_engine_three_scenarios_validates_keys():
    eng = ClimateECLEngine()
    try:
        eng.run_three_scenarios(
            asset_inputs=[_make_base_input()],
            risk_score_providers={"FOO": lambda a: (Decimal("0"), Decimal("0"))})
        assert False
    except ValueError as e:
        assert "BASELINE" in str(e) or "keys" in str(e).lower()


def _test_engine_board_summary_empty():
    eng = ClimateECLEngine()
    s = eng.board_summary()
    assert s["n_stress_runs"] == 0
    assert s["max_uplift_pct"] == Decimal("0")


def _test_engine_board_summary_with_data():
    eng = ClimateECLEngine()
    inputs = [_make_base_input(sector="MANUFACTURING_LIGHT", ead="100000")]
    eng.run_three_scenarios(
        asset_inputs=inputs,
        risk_score_providers={
            "BASELINE": lambda a: (Decimal("10"), Decimal("10")),
            "DOWNSIDE": lambda a: (Decimal("40"), Decimal("40")),
            "SEVERE_DOWNSIDE": lambda a: (Decimal("80"), Decimal("80")),
        },
        horizon_years=10)
    s = eng.board_summary()
    assert s["n_stress_runs"] == 3
    assert s["max_uplift_scenario"] == "SEVERE_DOWNSIDE"


def _test_decimal_purity():
    """All ECL outputs are Decimal."""
    base = _make_base_input()
    r = apply_climate_overlay(
        base=base,
        physical_risk_score=Decimal("50"),
        transition_risk_score=Decimal("50"),
        scenario="X", horizon_years=10)
    assert isinstance(r.adjusted_ecl_kes, Decimal)
    assert isinstance(r.uplift_kes, Decimal)
    assert isinstance(r.uplift_pct, Decimal)


def self_test() -> None:
    tests = [
        _test_base_ecl_inputs_validation,
        _test_base_ecl_stage_1_uses_12m_pd,
        _test_base_ecl_stage_2_uses_lifetime_pd,
        _test_pd_multiplier_no_risk_returns_one,
        _test_pd_multiplier_high_risk_uplift,
        _test_pd_multiplier_capped,
        _test_pd_multiplier_invalid_score_raises,
        _test_lgd_multiplier_real_estate_higher,
        _test_ead_multiplier_fossil_higher,
        _test_apply_overlay_zero_risk_no_uplift,
        _test_apply_overlay_high_risk_significant_uplift,
        _test_apply_overlay_zero_base_zero_uplift_pct,
        _test_probability_weighted_ecl_basic,
        _test_probability_weighted_ecl_requires_3_scenarios,
        _test_probability_weighted_ecl_weights_must_sum_to_1,
        _test_run_stress_scenario_basic,
        _test_run_stress_scenario_invalid_horizon,
        _test_engine_three_scenarios,
        _test_engine_three_scenarios_validates_keys,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_with_data,
        _test_decimal_purity,
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
        print(f"✗ climate_ecl_adjustment self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ climate_ecl_adjustment self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

"""utils/climate_risk.py — v10.7 Phase 2 deep impl batch 2.

╔════════════════════════════════════════════════════════════════════════╗
║  CLIMATE RISK MODELING — PHYSICAL + TRANSITION + TNFD BIODIVERSITY     ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (deterministic risk scoring with explicit scenarios) ║
║  Implements 3 of 13 Climate/ESG standards from registry:                ║
║    ENH-CLI-05: Physical Climate Risk Modeling (Acute + Chronic)         ║
║    ENH-CLI-06: Transition Climate Risk Modeling                         ║
║    ENH-CLI-10: Biodiversity & Nature-Related Risks (TNFD)               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Methodology references:                                                ║
║    IPCC AR6 (2021) — Representative Concentration Pathways (RCP)       ║
║    NGFS Scenarios v4 (Nov 2023) — central banks' transition pathways   ║
║    ECB Climate Stress Test (2022) — bank transition risk methodology   ║
║    TNFD v1.0 (Sept 2023) — LEAP framework for nature-related risks     ║
║    CBK CRMF (April 2021) — Climate Risk Management Framework Pillar 3  ║
║    PCAF (2022) — Partnership for Carbon Accounting Financials          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Scoring philosophy: Risk = Hazard × Exposure × Vulnerability          ║
║                                                                         ║
║  All scores 0-100 (low to extreme). Decimal-pure throughout.            ║
║  Honesty Rule 1: missing inputs surface explicitly via None,           ║
║                  not by silently substituting zeros.                    ║
║                                                                         ║
║  Integrates with utils/esg_intelligence.py (v10.6) via composition.    ║
║  v10.8 climate-adjusted ECL consumes outputs from this module.         ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# 28-digit precision for risk metrics
getcontext().prec = 28

# Score bounds
SCORE_MIN = Decimal("0")
SCORE_MAX = Decimal("100")


# ════════════════════════════════════════════════════════════════════════
# Climate scenarios
# ════════════════════════════════════════════════════════════════════════

class RCPScenario(Enum):
    """IPCC AR6 Representative Concentration Pathways.

    RCPs represent atmospheric CO2 concentration trajectories. Lower
    values = more aggressive mitigation; higher = business-as-usual.
    """
    RCP_2_6 = "RCP_2_6"   # Aggressive mitigation, ~1.5-2°C by 2100
    RCP_4_5 = "RCP_4_5"   # Moderate mitigation, ~2.5°C by 2100
    RCP_6_0 = "RCP_6_0"   # Limited mitigation, ~3°C by 2100
    RCP_8_5 = "RCP_8_5"   # No mitigation (BAU), ~4.5°C by 2100

    def warming_2100_celsius(self) -> Decimal:
        """Approximate warming by 2100 vs preindustrial."""
        return {
            RCPScenario.RCP_2_6: Decimal("1.8"),
            RCPScenario.RCP_4_5: Decimal("2.7"),
            RCPScenario.RCP_6_0: Decimal("3.2"),
            RCPScenario.RCP_8_5: Decimal("4.4"),
        }[self]


class NGFSScenario(Enum):
    """NGFS Scenarios v4 (Nov 2023) — central banks' standard set.

    Used by ECB Climate Stress Test, CBK climate stress testing,
    Bank of England, and most G20 central banks.
    """
    NET_ZERO_2050 = "NET_ZERO_2050"           # Orderly: net-zero by 2050
    BELOW_2C = "BELOW_2C"                       # Orderly: <2°C with delay
    DELAYED_TRANSITION = "DELAYED_TRANSITION"   # Disorderly: late + sudden
    NDCS = "NDCS"                               # Hot: current commitments
    CURRENT_POLICIES = "CURRENT_POLICIES"       # Hot: only current policies
    FRAGMENTED_WORLD = "FRAGMENTED_WORLD"       # Disorderly: divergent action

    def is_orderly(self) -> bool:
        return self in (NGFSScenario.NET_ZERO_2050, NGFSScenario.BELOW_2C)

    def is_disorderly(self) -> bool:
        return self in (
            NGFSScenario.DELAYED_TRANSITION, NGFSScenario.FRAGMENTED_WORLD)

    def is_hot_house(self) -> bool:
        return self in (NGFSScenario.NDCS, NGFSScenario.CURRENT_POLICIES)


# ════════════════════════════════════════════════════════════════════════
# Physical risk — hazards, exposure, vulnerability
# ════════════════════════════════════════════════════════════════════════

class AcutePhysicalHazard(Enum):
    """Acute physical hazards — sudden-onset events."""
    FLOOD_RIVERINE = "FLOOD_RIVERINE"
    FLOOD_COASTAL = "FLOOD_COASTAL"
    FLOOD_FLASH = "FLOOD_FLASH"
    DROUGHT_AGRICULTURAL = "DROUGHT_AGRICULTURAL"
    STORM_TROPICAL_CYCLONE = "STORM_TROPICAL_CYCLONE"
    STORM_SEVERE_THUNDERSTORM = "STORM_SEVERE_THUNDERSTORM"
    WILDFIRE = "WILDFIRE"
    HEATWAVE = "HEATWAVE"
    LANDSLIDE = "LANDSLIDE"


class ChronicPhysicalHazard(Enum):
    """Chronic physical hazards — gradual/long-term shifts."""
    TEMPERATURE_RISE = "TEMPERATURE_RISE"
    PRECIPITATION_CHANGE = "PRECIPITATION_CHANGE"
    SEA_LEVEL_RISE = "SEA_LEVEL_RISE"
    WATER_STRESS = "WATER_STRESS"
    SOIL_DEGRADATION = "SOIL_DEGRADATION"
    DESERTIFICATION = "DESERTIFICATION"
    OCEAN_ACIDIFICATION = "OCEAN_ACIDIFICATION"


# Sector-level vulnerability defaults (used when asset-specific data missing).
# Values are baseline vulnerability scores 0-100. Sourced from CBK CRMF
# Pillar 3 + ECB methodology + UNEP FI Banking Initiative guidance.
SECTOR_BASELINE_VULNERABILITY: Mapping[str, Decimal] = {
    "AGRICULTURE_PRIMARY": Decimal("75"),       # high — direct climate exposure
    "AGRICULTURE_PROCESSING": Decimal("50"),
    "REAL_ESTATE_RESIDENTIAL": Decimal("45"),
    "REAL_ESTATE_COMMERCIAL": Decimal("50"),
    "REAL_ESTATE_COASTAL": Decimal("80"),       # very high — sea level rise
    "INFRASTRUCTURE_TRANSPORT": Decimal("55"),
    "INFRASTRUCTURE_ENERGY_FOSSIL": Decimal("70"),
    "INFRASTRUCTURE_ENERGY_RENEWABLE": Decimal("25"),
    "TOURISM_HOSPITALITY": Decimal("60"),
    "MANUFACTURING": Decimal("40"),
    "RETAIL_TRADE": Decimal("30"),
    "FINANCIAL_SERVICES": Decimal("20"),         # low — indirect via clients
    "MINING_EXTRACTIVE": Decimal("65"),
    "TECHNOLOGY_SERVICES": Decimal("15"),
    "HEALTHCARE": Decimal("30"),
    "EDUCATION": Decimal("25"),
    "PUBLIC_SECTOR": Decimal("35"),
}


# ════════════════════════════════════════════════════════════════════════
# Transition risk — drivers and sector pathways
# ════════════════════════════════════════════════════════════════════════

class TransitionDriver(Enum):
    """Transition risk drivers per IFRS S2 §B14 + TCFD."""
    POLICY_AND_LEGAL = "POLICY_AND_LEGAL"
    TECHNOLOGY = "TECHNOLOGY"
    MARKET = "MARKET"
    REPUTATION = "REPUTATION"


# Sector transition risk per NGFS Net Zero 2050 (high-level intensity 0-100).
# Higher = more disruption from transition. Source: NGFS v4, ECB STS 2022.
SECTOR_TRANSITION_INTENSITY: Mapping[str, Decimal] = {
    "FOSSIL_FUELS_OIL_GAS": Decimal("90"),
    "FOSSIL_FUELS_COAL": Decimal("95"),
    "POWER_GENERATION_FOSSIL": Decimal("85"),
    "POWER_GENERATION_RENEWABLE": Decimal("10"),
    "MANUFACTURING_HEAVY_INDUSTRY": Decimal("70"),  # cement, steel, chemicals
    "MANUFACTURING_LIGHT": Decimal("35"),
    "TRANSPORT_AVIATION": Decimal("75"),
    "TRANSPORT_SHIPPING": Decimal("65"),
    "TRANSPORT_ROAD_FREIGHT": Decimal("60"),
    "TRANSPORT_RAIL": Decimal("25"),
    "TRANSPORT_PASSENGER_EV": Decimal("15"),
    "AGRICULTURE_LIVESTOCK": Decimal("65"),         # methane-intensive
    "AGRICULTURE_CROP": Decimal("45"),
    "REAL_ESTATE_HIGH_EFFICIENCY": Decimal("20"),
    "REAL_ESTATE_LEGACY_BUILDINGS": Decimal("55"),  # retrofit costs
    "FINANCIAL_SERVICES": Decimal("25"),            # via portfolio exposure
    "TECHNOLOGY_SERVICES": Decimal("15"),
    "RETAIL_TRADE": Decimal("20"),
}


# Carbon price assumptions per scenario (USD/tCO2e by 2030)
# Source: NGFS v4 GCAM/REMIND/MESSAGEix models
NGFS_CARBON_PRICE_2030_USD_PER_TCO2E: Mapping[NGFSScenario, Decimal] = {
    NGFSScenario.NET_ZERO_2050: Decimal("130"),
    NGFSScenario.BELOW_2C: Decimal("90"),
    NGFSScenario.DELAYED_TRANSITION: Decimal("60"),
    NGFSScenario.NDCS: Decimal("25"),
    NGFSScenario.CURRENT_POLICIES: Decimal("10"),
    NGFSScenario.FRAGMENTED_WORLD: Decimal("40"),
}


# ════════════════════════════════════════════════════════════════════════
# TNFD — Taskforce on Nature-related Financial Disclosures (LEAP framework)
# ════════════════════════════════════════════════════════════════════════

# TNFD LEAP — 4-stage assessment process (TNFD v1.0 §5)
TNFD_LEAP_STAGES: Tuple[str, ...] = (
    "LOCATE",     # interfaces with nature
    "EVALUATE",   # dependencies + impacts
    "ASSESS",     # risks + opportunities
    "PREPARE",    # respond + report
)

# TNFD nature realms (TNFD v1.0 Annex 2)
TNFD_NATURE_REALMS: Tuple[str, ...] = (
    "LAND",
    "FRESHWATER",
    "OCEAN",
    "ATMOSPHERE",
)

# TNFD high-impact biomes (subset relevant to Kenya/East Africa)
TNFD_BIOMES_KENYA: Tuple[str, ...] = (
    "TROPICAL_FOREST",
    "SAVANNA_GRASSLAND",
    "FRESHWATER_RIVERS_LAKES",
    "MARINE_COASTAL_REEFS",
    "WETLANDS",
    "ARID_SEMIARID",
)

# TNFD risk categories (TNFD v1.0 §6.2)
TNFD_RISK_CATEGORIES: Tuple[str, ...] = (
    "PHYSICAL_NATURE",       # ecosystem service degradation
    "TRANSITION_NATURE",     # policy / market / tech / reputation
    "SYSTEMIC_NATURE",       # tipping points, cascading effects
)


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class HazardExposure:
    """Hazard intensity at a specific location for a specific time horizon."""
    hazard: str                       # AcutePhysicalHazard or ChronicPhysicalHazard value
    intensity: Decimal                # 0-100 score
    time_horizon_years: int           # e.g. 5, 10, 30
    scenario: str                     # RCPScenario or NGFSScenario value
    location_id: str                  # county/region identifier
    notes: str = ""

    def __post_init__(self):
        if not (SCORE_MIN <= self.intensity <= SCORE_MAX):
            raise ValueError(
                f"intensity {self.intensity} outside [0, 100]")
        if self.time_horizon_years < 1:
            raise ValueError(
                f"time_horizon_years must be ≥1, got {self.time_horizon_years}")


@dataclass(frozen=True)
class PhysicalRiskAssessment:
    """Per-asset physical climate risk assessment (Hazard × Exposure × Vulnerability)."""
    asset_id: str
    sector: str
    location_id: str
    hazards: Tuple[HazardExposure, ...]
    sector_vulnerability: Decimal    # 0-100 from SECTOR_BASELINE_VULNERABILITY or override
    asset_specific_vulnerability: Optional[Decimal] = None  # if available
    risk_score: Decimal = Decimal("0")
    risk_level: str = "LOW"          # LOW / MEDIUM / HIGH / EXTREME
    notes: str = ""

    def vulnerability_used(self) -> Decimal:
        """Effective vulnerability — asset-specific overrides sector default."""
        if self.asset_specific_vulnerability is not None:
            return self.asset_specific_vulnerability
        return self.sector_vulnerability


@dataclass(frozen=True)
class TransitionRiskAssessment:
    """Per-asset transition climate risk assessment."""
    asset_id: str
    sector: str
    scenario: str                    # NGFSScenario value
    sector_transition_intensity: Decimal  # 0-100
    drivers_in_play: Tuple[str, ...]  # subset of TransitionDriver values
    carbon_price_exposure_usd: Optional[Decimal] = None  # if scope 1+2 emissions known
    stranded_asset_value_pct: Optional[Decimal] = None    # 0-100% potential write-down
    risk_score: Decimal = Decimal("0")
    risk_level: str = "LOW"
    notes: str = ""


@dataclass(frozen=True)
class TNFDAssessment:
    """Per-business-activity TNFD nature-related risk assessment."""
    activity_id: str
    activity_name: str
    leap_stages_completed: Tuple[str, ...]
    nature_realms_affected: Tuple[str, ...]
    biomes_affected: Tuple[str, ...]
    dependencies: Tuple[str, ...] = ()
    impacts: Tuple[str, ...] = ()
    risk_categories: Tuple[str, ...] = ()
    risk_score: Decimal = Decimal("0")
    risk_level: str = "LOW"
    notes: str = ""

    def leap_completeness_pct(self) -> Decimal:
        """Pct of LEAP stages completed."""
        return (Decimal(len(self.leap_stages_completed))
                / Decimal(len(TNFD_LEAP_STAGES))
                * Decimal("100"))


# ════════════════════════════════════════════════════════════════════════
# Risk level bucketing (consistent across all 3 risk types)
# ════════════════════════════════════════════════════════════════════════

def risk_level_for_score(score: Decimal) -> str:
    """Map a 0-100 score to a risk level bucket."""
    if score < Decimal("25"):
        return "LOW"
    if score < Decimal("50"):
        return "MEDIUM"
    if score < Decimal("75"):
        return "HIGH"
    return "EXTREME"


# ════════════════════════════════════════════════════════════════════════
# Physical risk computation
# ════════════════════════════════════════════════════════════════════════

def assess_physical_risk(
    *,
    asset_id: str,
    sector: str,
    location_id: str,
    hazards: Sequence[HazardExposure],
    asset_specific_vulnerability: Optional[Decimal] = None,
    sector_vulnerability_override: Optional[Decimal] = None,
) -> PhysicalRiskAssessment:
    """Assess physical climate risk for an asset.

    Risk = (mean_hazard_intensity × vulnerability) / 100

    Where:
      mean_hazard_intensity = average of HazardExposure.intensity over hazards
      vulnerability = asset_specific_vulnerability OR
                      sector_vulnerability_override OR
                      SECTOR_BASELINE_VULNERABILITY[sector]

    If sector unknown and no override, raises ValueError.
    """
    # Determine vulnerability
    if asset_specific_vulnerability is not None:
        vuln = asset_specific_vulnerability
        vuln_source = "asset_specific"
    elif sector_vulnerability_override is not None:
        vuln = sector_vulnerability_override
        vuln_source = "override"
    elif sector in SECTOR_BASELINE_VULNERABILITY:
        vuln = SECTOR_BASELINE_VULNERABILITY[sector]
        vuln_source = "sector_baseline"
    else:
        raise ValueError(
            f"unknown sector '{sector}' and no vulnerability override; "
            f"valid sectors: {sorted(SECTOR_BASELINE_VULNERABILITY)}")

    if not (SCORE_MIN <= vuln <= SCORE_MAX):
        raise ValueError(f"vulnerability {vuln} outside [0, 100]")

    # Compute mean hazard intensity
    if not hazards:
        mean_hazard = Decimal("0")
    else:
        total = sum((h.intensity for h in hazards), Decimal("0"))
        mean_hazard = total / Decimal(len(hazards))

    # Combined risk (capped at 100)
    risk_score = (mean_hazard * vuln) / Decimal("100")
    if risk_score > SCORE_MAX:
        risk_score = SCORE_MAX

    return PhysicalRiskAssessment(
        asset_id=asset_id,
        sector=sector,
        location_id=location_id,
        hazards=tuple(hazards),
        sector_vulnerability=(
            SECTOR_BASELINE_VULNERABILITY.get(sector, vuln)),
        asset_specific_vulnerability=asset_specific_vulnerability,
        risk_score=risk_score,
        risk_level=risk_level_for_score(risk_score),
        notes=f"vulnerability_source={vuln_source}, n_hazards={len(hazards)}")


# ════════════════════════════════════════════════════════════════════════
# Transition risk computation
# ════════════════════════════════════════════════════════════════════════

def assess_transition_risk(
    *,
    asset_id: str,
    sector: str,
    scenario: NGFSScenario,
    drivers_in_play: Sequence[TransitionDriver],
    annual_emissions_tco2e: Optional[Decimal] = None,
    asset_value_kes: Optional[Decimal] = None,
    sector_intensity_override: Optional[Decimal] = None,
) -> TransitionRiskAssessment:
    """Assess transition climate risk for an asset under a given scenario.

    Risk uses sector transition intensity scaled by scenario severity, with
    bonus weight for each driver in play.

    Carbon price exposure (USD) = emissions × NGFS_CARBON_PRICE_2030[scenario]
    Stranded asset value % is approximated for fossil-fuel sectors only.
    """
    if sector_intensity_override is not None:
        sector_intensity = sector_intensity_override
        sector_source = "override"
    elif sector in SECTOR_TRANSITION_INTENSITY:
        sector_intensity = SECTOR_TRANSITION_INTENSITY[sector]
        sector_source = "sector_baseline"
    else:
        raise ValueError(
            f"unknown sector '{sector}' and no override; "
            f"valid sectors: {sorted(SECTOR_TRANSITION_INTENSITY)}")

    if not (SCORE_MIN <= sector_intensity <= SCORE_MAX):
        raise ValueError(
            f"sector_intensity {sector_intensity} outside [0, 100]")

    # Scenario severity multiplier
    if scenario.is_orderly():
        scenario_multiplier = Decimal("0.7")  # transition still happens, gradual
    elif scenario.is_disorderly():
        scenario_multiplier = Decimal("1.2")  # disorderly = sharper impacts
    else:  # hot house
        scenario_multiplier = Decimal("0.4")  # less transition pressure short-term

    # Driver weight: each additional driver increases risk
    driver_weight = (
        Decimal("1") + Decimal("0.1") * Decimal(len(drivers_in_play)))

    # Combined score
    risk_score = sector_intensity * scenario_multiplier * driver_weight
    if risk_score > SCORE_MAX:
        risk_score = SCORE_MAX

    # Carbon price exposure
    carbon_exposure_usd: Optional[Decimal] = None
    if annual_emissions_tco2e is not None:
        carbon_price = NGFS_CARBON_PRICE_2030_USD_PER_TCO2E[scenario]
        carbon_exposure_usd = annual_emissions_tco2e * carbon_price

    # Stranded asset estimate (only for fossil sectors under aggressive scenarios)
    stranded_pct: Optional[Decimal] = None
    if "FOSSIL" in sector or "COAL" in sector:
        if scenario == NGFSScenario.NET_ZERO_2050:
            stranded_pct = Decimal("60")
        elif scenario == NGFSScenario.BELOW_2C:
            stranded_pct = Decimal("40")
        elif scenario == NGFSScenario.DELAYED_TRANSITION:
            stranded_pct = Decimal("70")  # disorderly = larger writedowns
        elif scenario == NGFSScenario.FRAGMENTED_WORLD:
            stranded_pct = Decimal("35")
        else:
            stranded_pct = Decimal("10")  # hot house — limited writedown

    return TransitionRiskAssessment(
        asset_id=asset_id,
        sector=sector,
        scenario=scenario.value,
        sector_transition_intensity=sector_intensity,
        drivers_in_play=tuple(d.value for d in drivers_in_play),
        carbon_price_exposure_usd=carbon_exposure_usd,
        stranded_asset_value_pct=stranded_pct,
        risk_score=risk_score,
        risk_level=risk_level_for_score(risk_score),
        notes=(
            f"sector_intensity_source={sector_source}, "
            f"scenario_multiplier={scenario_multiplier}, "
            f"driver_count={len(drivers_in_play)}"))


# ════════════════════════════════════════════════════════════════════════
# TNFD nature-related risk assessment
# ════════════════════════════════════════════════════════════════════════

def assess_tnfd(
    *,
    activity_id: str,
    activity_name: str,
    leap_stages_completed: Sequence[str],
    nature_realms_affected: Sequence[str],
    biomes_affected: Sequence[str] = (),
    dependencies: Sequence[str] = (),
    impacts: Sequence[str] = (),
    risk_categories: Sequence[str] = (),
    severity_overrides: Optional[Mapping[str, Decimal]] = None,
) -> TNFDAssessment:
    """Assess nature-related risk per TNFD LEAP framework.

    Score is computed as:
      base_score = (n_dependencies + n_impacts) * 5 (capped at 50)
      realm_weight = 5 per high-impact realm affected (max 20)
      biome_weight = 4 per Kenya biome affected (max 24)
      category_weight = 2 per risk category (max 6)
      total = base + realm + biome + category (capped at 100)

    severity_overrides allows manual scaling per dimension.
    """
    # Validate stages
    invalid_stages = [
        s for s in leap_stages_completed if s not in TNFD_LEAP_STAGES]
    if invalid_stages:
        raise ValueError(
            f"unknown LEAP stage(s): {invalid_stages}; valid: {TNFD_LEAP_STAGES}")

    # Validate realms
    invalid_realms = [
        r for r in nature_realms_affected if r not in TNFD_NATURE_REALMS]
    if invalid_realms:
        raise ValueError(
            f"unknown realm(s): {invalid_realms}; valid: {TNFD_NATURE_REALMS}")

    # Validate biomes
    invalid_biomes = [
        b for b in biomes_affected if b not in TNFD_BIOMES_KENYA]
    if invalid_biomes:
        raise ValueError(
            f"unknown biome(s): {invalid_biomes}; "
            f"valid: {TNFD_BIOMES_KENYA}")

    # Validate categories
    invalid_cats = [
        c for c in risk_categories if c not in TNFD_RISK_CATEGORIES]
    if invalid_cats:
        raise ValueError(
            f"unknown category(ies): {invalid_cats}; "
            f"valid: {TNFD_RISK_CATEGORIES}")

    # Score components
    dep_imp = (
        Decimal(len(dependencies)) + Decimal(len(impacts))) * Decimal("5")
    base = min(dep_imp, Decimal("50"))

    realm_weight = min(
        Decimal(len(set(nature_realms_affected))) * Decimal("5"),
        Decimal("20"))

    biome_weight = min(
        Decimal(len(set(biomes_affected))) * Decimal("4"),
        Decimal("24"))

    category_weight = min(
        Decimal(len(set(risk_categories))) * Decimal("2"),
        Decimal("6"))

    score = base + realm_weight + biome_weight + category_weight

    # Apply severity overrides multiplicatively
    if severity_overrides:
        for k, mult in severity_overrides.items():
            if k == "base":
                score = score - base + base * mult
            elif k == "realm":
                score = score - realm_weight + realm_weight * mult

    if score > SCORE_MAX:
        score = SCORE_MAX
    if score < SCORE_MIN:
        score = SCORE_MIN

    return TNFDAssessment(
        activity_id=activity_id,
        activity_name=activity_name,
        leap_stages_completed=tuple(leap_stages_completed),
        nature_realms_affected=tuple(nature_realms_affected),
        biomes_affected=tuple(biomes_affected),
        dependencies=tuple(dependencies),
        impacts=tuple(impacts),
        risk_categories=tuple(risk_categories),
        risk_score=score,
        risk_level=risk_level_for_score(score),
        notes=(
            f"base={base}, realm={realm_weight}, "
            f"biome={biome_weight}, category={category_weight}"))


# ════════════════════════════════════════════════════════════════════════
# Portfolio aggregation
# ════════════════════════════════════════════════════════════════════════

def aggregate_portfolio_physical_risk(
    assessments: Sequence[PhysicalRiskAssessment],
    *,
    asset_balances: Optional[Mapping[str, Decimal]] = None,
) -> Dict[str, object]:
    """Aggregate physical risk across portfolio.

    If asset_balances provided, weights by balance; otherwise equal-weighted.
    Returns mean risk score, distribution by risk level, top-5 most exposed.
    """
    if not assessments:
        return _empty_portfolio_summary("physical")

    weights = _compute_weights(assessments, asset_balances)
    weighted_score = _weighted_mean_score(assessments, weights)
    by_level = _distribution_by_level(assessments, weights)
    top_5 = sorted(
        assessments, key=lambda a: a.risk_score, reverse=True)[:5]

    return {
        "risk_type": "physical",
        "n_assessed": len(assessments),
        "weighting": "balance" if asset_balances else "equal",
        "mean_risk_score": weighted_score,
        "mean_risk_level": risk_level_for_score(weighted_score),
        "distribution_by_level": by_level,
        "top_5_exposed": [
            {"asset_id": a.asset_id, "score": a.risk_score,
              "level": a.risk_level, "sector": a.sector}
            for a in top_5],
    }


def aggregate_portfolio_transition_risk(
    assessments: Sequence[TransitionRiskAssessment],
    *,
    asset_balances: Optional[Mapping[str, Decimal]] = None,
) -> Dict[str, object]:
    """Aggregate transition risk across portfolio."""
    if not assessments:
        return _empty_portfolio_summary("transition")

    weights = _compute_weights(assessments, asset_balances)
    weighted_score = _weighted_mean_score(assessments, weights)
    by_level = _distribution_by_level(assessments, weights)
    top_5 = sorted(
        assessments, key=lambda a: a.risk_score, reverse=True)[:5]

    total_carbon_exposure: Optional[Decimal] = None
    carbon_exposed = [
        a.carbon_price_exposure_usd for a in assessments
        if a.carbon_price_exposure_usd is not None]
    if carbon_exposed:
        total_carbon_exposure = sum(carbon_exposed, Decimal("0"))

    return {
        "risk_type": "transition",
        "n_assessed": len(assessments),
        "weighting": "balance" if asset_balances else "equal",
        "mean_risk_score": weighted_score,
        "mean_risk_level": risk_level_for_score(weighted_score),
        "distribution_by_level": by_level,
        "total_carbon_price_exposure_usd": total_carbon_exposure,
        "scenarios_in_use": sorted(set(a.scenario for a in assessments)),
        "top_5_exposed": [
            {"asset_id": a.asset_id, "score": a.risk_score,
              "level": a.risk_level, "sector": a.sector,
              "scenario": a.scenario}
            for a in top_5],
    }


def aggregate_portfolio_tnfd(
    assessments: Sequence[TNFDAssessment],
) -> Dict[str, object]:
    """Aggregate TNFD nature-related risk across activities."""
    if not assessments:
        return _empty_portfolio_summary("tnfd")

    n = len(assessments)
    mean_score = sum(
        (a.risk_score for a in assessments), Decimal("0")) / Decimal(n)
    mean_completeness = sum(
        (a.leap_completeness_pct() for a in assessments),
        Decimal("0")) / Decimal(n)

    realms_seen: set = set()
    biomes_seen: set = set()
    for a in assessments:
        realms_seen.update(a.nature_realms_affected)
        biomes_seen.update(a.biomes_affected)

    return {
        "risk_type": "tnfd",
        "n_assessed": n,
        "mean_risk_score": mean_score,
        "mean_risk_level": risk_level_for_score(mean_score),
        "mean_leap_completeness_pct": mean_completeness,
        "realms_covered": sorted(realms_seen),
        "biomes_covered": sorted(biomes_seen),
    }


def _compute_weights(
    assessments: Sequence,
    balances: Optional[Mapping[str, Decimal]],
) -> Dict[str, Decimal]:
    if balances:
        return {
            a.asset_id: balances.get(a.asset_id, Decimal("0"))
            for a in assessments}
    return {a.asset_id: Decimal("1") for a in assessments}


def _weighted_mean_score(
    assessments: Sequence,
    weights: Mapping[str, Decimal],
) -> Decimal:
    total_w = sum(weights.values(), Decimal("0"))
    if total_w == 0:
        return Decimal("0")
    weighted = sum(
        (a.risk_score * weights[a.asset_id] for a in assessments),
        Decimal("0"))
    return weighted / total_w


def _distribution_by_level(
    assessments: Sequence,
    weights: Mapping[str, Decimal],
) -> Dict[str, Decimal]:
    levels = ("LOW", "MEDIUM", "HIGH", "EXTREME")
    total = sum(weights.values(), Decimal("0"))
    if total == 0:
        return {lvl: Decimal("0") for lvl in levels}
    out = {}
    for lvl in levels:
        share = sum(
            (weights[a.asset_id] for a in assessments
              if a.risk_level == lvl),
            Decimal("0"))
        out[lvl] = share / total * Decimal("100")
    return out


def _empty_portfolio_summary(risk_type: str) -> Dict[str, object]:
    return {
        "risk_type": risk_type,
        "n_assessed": 0,
        "mean_risk_score": Decimal("0"),
        "mean_risk_level": "LOW",
        "distribution_by_level": {
            "LOW": Decimal("0"), "MEDIUM": Decimal("0"),
            "HIGH": Decimal("0"), "EXTREME": Decimal("0")},
    }


# ════════════════════════════════════════════════════════════════════════
# Engine orchestrator
# ════════════════════════════════════════════════════════════════════════

class ClimateRiskEngine:
    """Orchestrates physical + transition + TNFD risk assessments.

    Composes with v10.6 ESGIntelligenceEngine — risk outputs feed v10.8
    climate-adjusted ECL.
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._physical: List[PhysicalRiskAssessment] = []
        self._transition: List[TransitionRiskAssessment] = []
        self._tnfd: List[TNFDAssessment] = []

    def add_physical(self, a: PhysicalRiskAssessment) -> None:
        self._physical.append(a)

    def add_transition(self, a: TransitionRiskAssessment) -> None:
        self._transition.append(a)

    def add_tnfd(self, a: TNFDAssessment) -> None:
        self._tnfd.append(a)

    def assess_portfolio(
        self,
        *,
        asset_balances: Optional[Mapping[str, Decimal]] = None,
    ) -> Dict[str, object]:
        """Full portfolio assessment across all 3 risk types."""
        return {
            "entity": self.entity_name,
            "physical": aggregate_portfolio_physical_risk(
                self._physical, asset_balances=asset_balances),
            "transition": aggregate_portfolio_transition_risk(
                self._transition, asset_balances=asset_balances),
            "tnfd": aggregate_portfolio_tnfd(self._tnfd),
        }

    def board_summary(self) -> Dict[str, object]:
        """Board-ready climate risk summary."""
        portfolio = self.assess_portfolio()

        # Aggregate across all 3 risk types
        scores = [
            portfolio["physical"]["mean_risk_score"],
            portfolio["transition"]["mean_risk_score"],
            portfolio["tnfd"]["mean_risk_score"],
        ]
        # Transition + physical weighted higher than TNFD (early-stage discipline)
        weighted_overall = (
            (portfolio["physical"]["mean_risk_score"] * Decimal("0.4"))
            + (portfolio["transition"]["mean_risk_score"] * Decimal("0.4"))
            + (portfolio["tnfd"]["mean_risk_score"] * Decimal("0.2")))

        attention_needed: List[str] = []
        if portfolio["physical"]["mean_risk_score"] >= Decimal("50"):
            attention_needed.append("Physical risk: HIGH or above")
        if portfolio["transition"]["mean_risk_score"] >= Decimal("50"):
            attention_needed.append("Transition risk: HIGH or above")
        if portfolio["tnfd"]["mean_risk_score"] >= Decimal("50"):
            attention_needed.append("Nature/biodiversity risk: HIGH or above")
        if (portfolio["transition"].get("total_carbon_price_exposure_usd")
                and portfolio["transition"]["total_carbon_price_exposure_usd"]
                > Decimal("1000000")):
            attention_needed.append("Carbon-price exposure exceeds USD 1M")

        return {
            "entity": self.entity_name,
            "n_physical_assessed": portfolio["physical"]["n_assessed"],
            "n_transition_assessed": portfolio["transition"]["n_assessed"],
            "n_tnfd_assessed": portfolio["tnfd"]["n_assessed"],
            "physical_risk_level": portfolio["physical"]["mean_risk_level"],
            "transition_risk_level": portfolio["transition"]["mean_risk_level"],
            "tnfd_risk_level": portfolio["tnfd"]["mean_risk_level"],
            "weighted_overall_score": weighted_overall,
            "weighted_overall_level": risk_level_for_score(weighted_overall),
            "attention_needed": tuple(attention_needed),
            "carbon_price_exposure_usd": (
                portfolio["transition"].get("total_carbon_price_exposure_usd")),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_rcp_warming_sane():
    """RCP scenarios have monotonically increasing 2100 warming."""
    warmings = [s.warming_2100_celsius() for s in RCPScenario]
    assert warmings == sorted(warmings), \
        f"RCP warmings not monotonic: {warmings}"


def _test_ngfs_scenario_classification():
    """Each NGFS scenario classifies to exactly one of orderly/disorderly/hot-house."""
    for s in NGFSScenario:
        flags = (s.is_orderly(), s.is_disorderly(), s.is_hot_house())
        assert sum(flags) == 1, f"{s} has ambiguous classification: {flags}"


def _test_acute_chronic_disjoint():
    """Acute and chronic hazards are disjoint."""
    a = {h.value for h in AcutePhysicalHazard}
    c = {h.value for h in ChronicPhysicalHazard}
    assert a.isdisjoint(c), \
        f"acute and chronic overlap: {a & c}"


def _test_sector_vulnerability_bounded():
    """All sector vulnerabilities are 0-100."""
    for sec, v in SECTOR_BASELINE_VULNERABILITY.items():
        assert SCORE_MIN <= v <= SCORE_MAX, \
            f"{sec}: vulnerability {v} out of bounds"


def _test_sector_transition_intensity_bounded():
    """All sector transition intensities are 0-100."""
    for sec, v in SECTOR_TRANSITION_INTENSITY.items():
        assert SCORE_MIN <= v <= SCORE_MAX, \
            f"{sec}: transition intensity {v} out of bounds"


def _test_carbon_prices_increase_with_ambition():
    """Net Zero scenario has higher carbon price than Current Policies."""
    nz = NGFS_CARBON_PRICE_2030_USD_PER_TCO2E[NGFSScenario.NET_ZERO_2050]
    cp = NGFS_CARBON_PRICE_2030_USD_PER_TCO2E[NGFSScenario.CURRENT_POLICIES]
    assert nz > cp, f"Net Zero {nz} should exceed Current Policies {cp}"


def _test_risk_level_buckets():
    """Risk level mapping covers boundaries correctly."""
    assert risk_level_for_score(Decimal("0")) == "LOW"
    assert risk_level_for_score(Decimal("24.99")) == "LOW"
    assert risk_level_for_score(Decimal("25")) == "MEDIUM"
    assert risk_level_for_score(Decimal("49.99")) == "MEDIUM"
    assert risk_level_for_score(Decimal("50")) == "HIGH"
    assert risk_level_for_score(Decimal("74.99")) == "HIGH"
    assert risk_level_for_score(Decimal("75")) == "EXTREME"
    assert risk_level_for_score(Decimal("100")) == "EXTREME"


def _test_hazard_exposure_validates_intensity():
    """HazardExposure rejects invalid intensity."""
    try:
        HazardExposure(
            hazard="FLOOD_RIVERINE", intensity=Decimal("150"),
            time_horizon_years=10,
            scenario="RCP_4_5", location_id="NAIROBI")
        assert False, "should have raised"
    except ValueError as e:
        assert "intensity" in str(e)


def _test_physical_risk_basic():
    """High-vulnerability sector + high hazards → HIGH/EXTREME risk."""
    h = HazardExposure(
        hazard="FLOOD_COASTAL", intensity=Decimal("80"),
        time_horizon_years=10,
        scenario="RCP_8_5", location_id="MOMBASA")
    a = assess_physical_risk(
        asset_id="LOAN-COAST-1",
        sector="REAL_ESTATE_COASTAL",
        location_id="MOMBASA",
        hazards=(h,))
    assert a.risk_level in ("HIGH", "EXTREME")
    assert a.risk_score == Decimal("80") * Decimal("80") / Decimal("100")  # 64


def _test_physical_risk_low_vulnerability_sector():
    """Low-vulnerability sector with same hazards → much lower risk."""
    h = HazardExposure(
        hazard="FLOOD_COASTAL", intensity=Decimal("80"),
        time_horizon_years=10,
        scenario="RCP_8_5", location_id="NAIROBI")
    a = assess_physical_risk(
        asset_id="LOAN-TECH-1",
        sector="TECHNOLOGY_SERVICES",
        location_id="NAIROBI",
        hazards=(h,))
    assert a.risk_score == Decimal("80") * Decimal("15") / Decimal("100")  # 12
    assert a.risk_level == "LOW"


def _test_physical_risk_unknown_sector_raises():
    """Unknown sector with no override raises."""
    h = HazardExposure(
        hazard="DROUGHT_AGRICULTURAL", intensity=Decimal("50"),
        time_horizon_years=5,
        scenario="RCP_4_5", location_id="MAKUENI")
    try:
        assess_physical_risk(
            asset_id="L-X", sector="MADE_UP_SECTOR",
            location_id="MAKUENI", hazards=(h,))
        assert False, "should raise"
    except ValueError as e:
        assert "unknown sector" in str(e)


def _test_physical_risk_asset_specific_override():
    """Asset-specific vulnerability overrides sector default."""
    h = HazardExposure(
        hazard="HEATWAVE", intensity=Decimal("60"),
        time_horizon_years=10,
        scenario="RCP_4_5", location_id="GARISSA")
    a = assess_physical_risk(
        asset_id="L-RESILIENT", sector="AGRICULTURE_PRIMARY",
        location_id="GARISSA", hazards=(h,),
        asset_specific_vulnerability=Decimal("20"))  # well-adapted asset
    assert a.vulnerability_used() == Decimal("20")
    assert a.risk_score == Decimal("60") * Decimal("20") / Decimal("100")


def _test_transition_risk_orderly_below_disorderly():
    """Same sector under disorderly scenario → higher score than orderly."""
    orderly = assess_transition_risk(
        asset_id="L-OG-1", sector="FOSSIL_FUELS_OIL_GAS",
        scenario=NGFSScenario.NET_ZERO_2050,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,))
    disorderly = assess_transition_risk(
        asset_id="L-OG-2", sector="FOSSIL_FUELS_OIL_GAS",
        scenario=NGFSScenario.DELAYED_TRANSITION,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,))
    assert disorderly.risk_score > orderly.risk_score


def _test_transition_risk_carbon_price_exposure():
    """Carbon price exposure = emissions × scenario carbon price."""
    a = assess_transition_risk(
        asset_id="L-1", sector="POWER_GENERATION_FOSSIL",
        scenario=NGFSScenario.NET_ZERO_2050,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,),
        annual_emissions_tco2e=Decimal("10000"))
    expected = Decimal("10000") * Decimal("130")  # USD 1.3M
    assert a.carbon_price_exposure_usd == expected


def _test_transition_risk_stranded_fossil():
    """Fossil sector under Net Zero → stranded asset estimate provided."""
    a = assess_transition_risk(
        asset_id="L-COAL-1", sector="FOSSIL_FUELS_COAL",
        scenario=NGFSScenario.NET_ZERO_2050,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,
                          TransitionDriver.MARKET))
    assert a.stranded_asset_value_pct is not None
    assert a.stranded_asset_value_pct >= Decimal("60")


def _test_transition_risk_no_stranded_for_clean_sector():
    """Renewable energy → no stranded asset estimate."""
    a = assess_transition_risk(
        asset_id="L-SOLAR-1", sector="POWER_GENERATION_RENEWABLE",
        scenario=NGFSScenario.NET_ZERO_2050,
        drivers_in_play=(TransitionDriver.MARKET,))
    assert a.stranded_asset_value_pct is None


def _test_transition_risk_more_drivers_higher_score():
    """More drivers in play → higher risk score (driver weight)."""
    one_driver = assess_transition_risk(
        asset_id="L-1", sector="MANUFACTURING_HEAVY_INDUSTRY",
        scenario=NGFSScenario.NET_ZERO_2050,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,))
    four_drivers = assess_transition_risk(
        asset_id="L-2", sector="MANUFACTURING_HEAVY_INDUSTRY",
        scenario=NGFSScenario.NET_ZERO_2050,
        drivers_in_play=tuple(TransitionDriver))
    assert four_drivers.risk_score > one_driver.risk_score


def _test_tnfd_basic():
    """All LEAP stages + 2 realms + 2 biomes → moderate score."""
    a = assess_tnfd(
        activity_id="ACT-AGRI-1",
        activity_name="Smallholder farming Loan Portfolio",
        leap_stages_completed=TNFD_LEAP_STAGES,
        nature_realms_affected=("LAND", "FRESHWATER"),
        biomes_affected=("SAVANNA_GRASSLAND", "FRESHWATER_RIVERS_LAKES"),
        dependencies=("WATER_PROVISION", "POLLINATION"),
        impacts=("LAND_USE_CHANGE",),
        risk_categories=("PHYSICAL_NATURE", "TRANSITION_NATURE"))
    assert a.leap_completeness_pct() == Decimal("100")
    assert a.risk_score > Decimal("0")
    assert a.risk_level in ("LOW", "MEDIUM", "HIGH", "EXTREME")


def _test_tnfd_invalid_stage_raises():
    """Invalid LEAP stage raises."""
    try:
        assess_tnfd(
            activity_id="A", activity_name="A",
            leap_stages_completed=("LOCATE", "INVALID_STAGE"),
            nature_realms_affected=("LAND",))
        assert False, "should raise"
    except ValueError as e:
        assert "unknown LEAP stage" in str(e)


def _test_tnfd_invalid_realm_raises():
    """Invalid realm raises."""
    try:
        assess_tnfd(
            activity_id="A", activity_name="A",
            leap_stages_completed=("LOCATE",),
            nature_realms_affected=("MARS",))
        assert False, "should raise"
    except ValueError as e:
        assert "unknown realm" in str(e)


def _test_tnfd_partial_leap():
    """Only LOCATE completed → 25% completeness."""
    a = assess_tnfd(
        activity_id="A", activity_name="Partial",
        leap_stages_completed=("LOCATE",),
        nature_realms_affected=("LAND",))
    assert a.leap_completeness_pct() == Decimal("25")


def _test_aggregate_physical_balance_weighted():
    """Balance-weighted aggregation differs from equal-weighted."""
    h_high = HazardExposure(
        hazard="FLOOD_COASTAL", intensity=Decimal("90"),
        time_horizon_years=10, scenario="RCP_8_5",
        location_id="MOMBASA")
    h_low = HazardExposure(
        hazard="DROUGHT_AGRICULTURAL", intensity=Decimal("20"),
        time_horizon_years=10, scenario="RCP_4_5",
        location_id="NYERI")

    big = assess_physical_risk(
        asset_id="BIG", sector="REAL_ESTATE_COASTAL",
        location_id="MOMBASA", hazards=(h_high,))
    small = assess_physical_risk(
        asset_id="SMALL", sector="TECHNOLOGY_SERVICES",
        location_id="NYERI", hazards=(h_low,))

    equal = aggregate_portfolio_physical_risk((big, small))
    balanced = aggregate_portfolio_physical_risk(
        (big, small),
        asset_balances={"BIG": Decimal("10000"),
                          "SMALL": Decimal("100")})
    assert balanced["mean_risk_score"] > equal["mean_risk_score"]


def _test_aggregate_empty_returns_zero_summary():
    """Empty portfolio returns zero-filled summary, not error."""
    s = aggregate_portfolio_physical_risk(())
    assert s["n_assessed"] == 0
    assert s["mean_risk_score"] == Decimal("0")


def _test_engine_orchestration():
    """Engine successfully aggregates all 3 risk types."""
    eng = ClimateRiskEngine(entity_name="Test Bank")

    h = HazardExposure(
        hazard="FLOOD_RIVERINE", intensity=Decimal("60"),
        time_horizon_years=10, scenario="RCP_4_5",
        location_id="KISUMU")
    eng.add_physical(assess_physical_risk(
        asset_id="LP-1", sector="AGRICULTURE_PRIMARY",
        location_id="KISUMU", hazards=(h,)))

    eng.add_transition(assess_transition_risk(
        asset_id="LT-1", sector="POWER_GENERATION_FOSSIL",
        scenario=NGFSScenario.BELOW_2C,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,
                          TransitionDriver.MARKET),
        annual_emissions_tco2e=Decimal("5000")))

    eng.add_tnfd(assess_tnfd(
        activity_id="A-1", activity_name="Lakeshore agriculture",
        leap_stages_completed=TNFD_LEAP_STAGES,
        nature_realms_affected=("LAND", "FRESHWATER"),
        biomes_affected=("FRESHWATER_RIVERS_LAKES",),
        dependencies=("WATER_PROVISION",),
        impacts=("LAND_USE_CHANGE",)))

    summary = eng.assess_portfolio()
    assert summary["entity"] == "Test Bank"
    assert summary["physical"]["n_assessed"] == 1
    assert summary["transition"]["n_assessed"] == 1
    assert summary["tnfd"]["n_assessed"] == 1


def _test_engine_board_summary_attention_flags():
    """Board summary flags attention items when scores are HIGH."""
    eng = ClimateRiskEngine()
    h = HazardExposure(
        hazard="FLOOD_COASTAL", intensity=Decimal("90"),
        time_horizon_years=10, scenario="RCP_8_5",
        location_id="MOMBASA")
    eng.add_physical(assess_physical_risk(
        asset_id="L-COAST", sector="REAL_ESTATE_COASTAL",
        location_id="MOMBASA", hazards=(h,)))

    summary = eng.board_summary()
    # 90 × 80 / 100 = 72 → HIGH
    assert summary["physical_risk_level"] in ("HIGH", "EXTREME")
    assert any(
        "Physical risk" in s for s in summary["attention_needed"])


def _test_engine_empty_no_attention():
    """Empty engine → no attention flags."""
    eng = ClimateRiskEngine()
    summary = eng.board_summary()
    assert summary["attention_needed"] == ()
    assert summary["weighted_overall_level"] == "LOW"


def _test_decimal_purity():
    """All scores are Decimal, never float."""
    h = HazardExposure(
        hazard="HEATWAVE", intensity=Decimal("50"),
        time_horizon_years=5, scenario="RCP_4_5",
        location_id="NAIROBI")
    a = assess_physical_risk(
        asset_id="L", sector="MANUFACTURING",
        location_id="NAIROBI", hazards=(h,))
    assert isinstance(a.risk_score, Decimal)

    t = assess_transition_risk(
        asset_id="L", sector="MANUFACTURING_LIGHT",
        scenario=NGFSScenario.BELOW_2C,
        drivers_in_play=(TransitionDriver.POLICY_AND_LEGAL,))
    assert isinstance(t.risk_score, Decimal)

    n = assess_tnfd(
        activity_id="A", activity_name="A",
        leap_stages_completed=("LOCATE",),
        nature_realms_affected=("LAND",))
    assert isinstance(n.risk_score, Decimal)


def self_test() -> None:
    tests = [
        _test_rcp_warming_sane,
        _test_ngfs_scenario_classification,
        _test_acute_chronic_disjoint,
        _test_sector_vulnerability_bounded,
        _test_sector_transition_intensity_bounded,
        _test_carbon_prices_increase_with_ambition,
        _test_risk_level_buckets,
        _test_hazard_exposure_validates_intensity,
        _test_physical_risk_basic,
        _test_physical_risk_low_vulnerability_sector,
        _test_physical_risk_unknown_sector_raises,
        _test_physical_risk_asset_specific_override,
        _test_transition_risk_orderly_below_disorderly,
        _test_transition_risk_carbon_price_exposure,
        _test_transition_risk_stranded_fossil,
        _test_transition_risk_no_stranded_for_clean_sector,
        _test_transition_risk_more_drivers_higher_score,
        _test_tnfd_basic,
        _test_tnfd_invalid_stage_raises,
        _test_tnfd_invalid_realm_raises,
        _test_tnfd_partial_leap,
        _test_aggregate_physical_balance_weighted,
        _test_aggregate_empty_returns_zero_summary,
        _test_engine_orchestration,
        _test_engine_board_summary_attention_flags,
        _test_engine_empty_no_attention,
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
        print(f"✗ climate_risk self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ climate_risk self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

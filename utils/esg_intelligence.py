"""utils/esg_intelligence.py — v10.6 Phase 2 deep impl batch 1.

╔════════════════════════════════════════════════════════════════════════╗
║  CLIMATE/ESG INTELLIGENCE — IFRS S1/S2 + KGFT + CRDF + GOVERNANCE      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (deterministic disclosure assembly + classification) ║
║  Implements 5 of 13 Climate/ESG standards from registry:                ║
║    ENH-CLI-01: IFRS S1 General Sustainability Disclosures               ║
║    ENH-CLI-02: IFRS S2 Climate-Related Disclosures                      ║
║    ENH-CLI-08: Scope 1/2/3 Emissions Tracking (portfolio attribution)   ║
║    ENH-CLI-09: Green Asset Classification & Tagging (KGFT-aligned)      ║
║    ENH-CLI-11: Climate Governance (Board Oversight + Roles)             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    IFRS S1 — IFRS Sustainability Disclosure Standards (June 2023)      ║
║    IFRS S2 — Climate-related Disclosures (June 2023)                   ║
║    KGFT   — Kenya Green Finance Taxonomy (CBK, April 2025)             ║
║    CRDF   — Climate Risk Disclosure Framework (CBK, April 2025)        ║
║    CBK Climate Risk Management Framework (April 2021)                  ║
║    GHG Protocol — Corporate Standard + Scope 3 Standard                ║
║    EFFECTIVE 2027-01-01: IFRS S1/S2 mandatory disclosure deadline      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Integrates with utils/esg_reporting.py (TCFD foundation), provides    ║
║  the IFRS S1/S2 layer + Kenya regulatory + portfolio attribution       ║
║  + governance assessment that v10.7 risk modeling and v10.8 climate-   ║
║  adjusted ECL build on.                                                 ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
import warnings
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# 28-digit precision for Kg/Tonne CO2e calculations
getcontext().prec = 28

# Reuse TCFD foundation where helpful
try:
    from utils.esg_reporting import (
        GHG_SCOPES as _GHG_SCOPES_FOUNDATION,
        SCOPE_3_CATEGORIES as _SCOPE_3_CATEGORIES_FOUNDATION,
        CLIMATE_RISK_TYPES as _CLIMATE_RISK_TYPES_FOUNDATION,
    )
    _ESG_REPORTING_AVAILABLE = True
except ImportError:
    _ESG_REPORTING_AVAILABLE = False
    _GHG_SCOPES_FOUNDATION = ("SCOPE_1", "SCOPE_2", "SCOPE_3")
    _SCOPE_3_CATEGORIES_FOUNDATION = tuple(f"CAT_{i}" for i in range(1, 16))
    _CLIMATE_RISK_TYPES_FOUNDATION = (
        "ACUTE_PHYSICAL", "CHRONIC_PHYSICAL",
        "TRANSITION_POLICY", "TRANSITION_TECHNOLOGY",
        "TRANSITION_MARKET", "TRANSITION_REPUTATION",
    )


# ════════════════════════════════════════════════════════════════════════
# Frameworks
# ════════════════════════════════════════════════════════════════════════

class ESGFramework(Enum):
    """Disclosure frameworks supported by the engine."""
    IFRS_S1 = "IFRS_S1"        # General sustainability (June 2023)
    IFRS_S2 = "IFRS_S2"        # Climate-related (June 2023)
    TCFD = "TCFD"              # Task Force on Climate-related Disclosures
    KGFT_CBK = "KGFT_CBK"      # Kenya Green Finance Taxonomy
    CRDF_CBK = "CRDF_CBK"      # Climate Risk Disclosure Framework
    CBK_CRMF = "CBK_CRMF"      # CBK Climate Risk Management Framework 2021

    @classmethod
    def kenya_specific(cls) -> Tuple["ESGFramework", ...]:
        return (cls.KGFT_CBK, cls.CRDF_CBK, cls.CBK_CRMF)

    @classmethod
    def issb_global(cls) -> Tuple["ESGFramework", ...]:
        return (cls.IFRS_S1, cls.IFRS_S2)


# ════════════════════════════════════════════════════════════════════════
# IFRS S1 — General Sustainability Disclosures (per IFRS S1 §10-§22)
# ════════════════════════════════════════════════════════════════════════

# IFRS S1 mandates 4 core content areas across all sustainability topics
IFRS_S1_CORE_CONTENT_AREAS: Tuple[str, ...] = (
    "GOVERNANCE",        # §27-§28: oversight body, management's role
    "STRATEGY",          # §29-§42: sustainability-related risks/opps
    "RISK_MANAGEMENT",   # §43-§47: identification, assessment, monitoring
    "METRICS_AND_TARGETS",  # §48-§51: industry-based, cross-industry
)

# IFRS S1 §B5-§B7: sustainability topic categories
IFRS_S1_TOPIC_CATEGORIES: Tuple[str, ...] = (
    "CLIMATE",
    "WATER_AND_MARINE_RESOURCES",
    "BIODIVERSITY_AND_ECOSYSTEMS",
    "POLLUTION",
    "RESOURCE_USE_AND_CIRCULAR_ECONOMY",
    "WORKFORCE",
    "AFFECTED_COMMUNITIES",
    "CONSUMERS_AND_END_USERS",
    "BUSINESS_CONDUCT",
)


# ════════════════════════════════════════════════════════════════════════
# IFRS S2 — Climate-related Disclosures (per IFRS S2 §6-§35)
# ════════════════════════════════════════════════════════════════════════

# IFRS S2 climate-specific disclosure requirements (29 sub-disclosures)
IFRS_S2_DISCLOSURES: Tuple[str, ...] = (
    # Governance (§6-§7)
    "S2_GOV_BOARD_OVERSIGHT",
    "S2_GOV_MANAGEMENT_ROLE",
    # Strategy (§8-§22)
    "S2_STR_RISKS_OPPORTUNITIES",
    "S2_STR_BUSINESS_MODEL",
    "S2_STR_TRANSITION_PLAN",
    "S2_STR_FINANCIAL_EFFECTS_CURRENT",
    "S2_STR_FINANCIAL_EFFECTS_ANTICIPATED",
    "S2_STR_CLIMATE_RESILIENCE_SCENARIOS",
    # Risk Management (§23-§27)
    "S2_RM_RISK_PROCESS",
    "S2_RM_OPPORTUNITY_PROCESS",
    "S2_RM_INTEGRATION",
    # Metrics & Targets (§28-§37)
    "S2_MT_GHG_SCOPE_1",
    "S2_MT_GHG_SCOPE_2",
    "S2_MT_GHG_SCOPE_3",
    "S2_MT_CLIMATE_RELATED_TRANSITION_RISKS",
    "S2_MT_CLIMATE_RELATED_PHYSICAL_RISKS",
    "S2_MT_CAPITAL_DEPLOYMENT",
    "S2_MT_INTERNAL_CARBON_PRICE",
    "S2_MT_REMUNERATION_LINKAGE",
    "S2_MT_TARGETS_QUANTITATIVE",
    "S2_MT_TARGETS_QUALITATIVE",
)

# IFRS S2 mandates Scope 1/2/3 measurement aligned with GHG Protocol
IFRS_S2_SCOPE_1_MANDATORY = True
IFRS_S2_SCOPE_2_MANDATORY = True
IFRS_S2_SCOPE_3_MANDATORY = True  # Effective Y2 of adoption


# ════════════════════════════════════════════════════════════════════════
# Kenya Green Finance Taxonomy (KGFT) — CBK April 2025
# ════════════════════════════════════════════════════════════════════════

# KGFT 8 high-level green economic activity categories
KGFT_GREEN_CATEGORIES: Tuple[str, ...] = (
    "RENEWABLE_ENERGY",            # solar, wind, hydro, geothermal, biomass
    "ENERGY_EFFICIENCY",           # LED, insulation, efficient appliances
    "SUSTAINABLE_TRANSPORT",       # EVs, BRT, rail, e-mobility
    "GREEN_BUILDINGS",             # IFC EDGE, LEED, BREEAM-certified
    "WATER_AND_WASTEWATER",        # treatment, conservation, sanitation
    "WASTE_MANAGEMENT",            # recycling, circular economy
    "SUSTAINABLE_AGRICULTURE",     # climate-smart, agroforestry
    "BIODIVERSITY_CONSERVATION",   # ecosystem services, restoration
)

# KGFT eligibility criteria — what makes an asset "green"
KGFT_ELIGIBILITY_DIMENSIONS: Tuple[str, ...] = (
    "CLIMATE_MITIGATION",        # GHG reduction
    "CLIMATE_ADAPTATION",        # resilience to physical risks
    "POLLUTION_PREVENTION",      # air, water, soil
    "WATER_PROTECTION",          # quality + scarcity
    "CIRCULAR_ECONOMY",          # resource efficiency
    "BIODIVERSITY_PROTECTION",   # ecosystem health
)

# KGFT alignment levels (graduated: from candidate to certified green)
KGFT_ALIGNMENT_LEVELS: Tuple[str, ...] = (
    "ALIGNED",            # meets all criteria + DNSH (do no significant harm)
    "TRANSITIONING",      # on credible path to alignment
    "ENABLING",           # enables others to be green
    "NON_ALIGNED",        # does not meet criteria
)

# Climate Risk Disclosure Framework (CRDF) — CBK April 2025
CRDF_DISCLOSURE_PILLARS: Tuple[str, ...] = (
    "GOVERNANCE",
    "STRATEGY",
    "RISK_MANAGEMENT",
    "METRICS_AND_TARGETS",
)

CRDF_REPORTING_FREQUENCY = "ANNUAL"  # CBK requires annual climate risk disclosure
CRDF_FIRST_REPORTING_PERIOD = "2025-12-31"
IFRS_S1_S2_MANDATORY_DEADLINE = "2027-01-01"


# ════════════════════════════════════════════════════════════════════════
# Climate governance — IFRS S2 §6-§7 + CBK CRMF Pillar 1
# ════════════════════════════════════════════════════════════════════════

# Required climate governance roles (IFRS S2 + CBK CRMF Apr 2021)
CLIMATE_GOVERNANCE_REQUIRED_ROLES: Tuple[str, ...] = (
    "BOARD_CLIMATE_OVERSIGHT",     # board-level oversight body
    "EXECUTIVE_SPONSOR",           # C-suite sponsor (often CRO or CFO)
    "CLIMATE_RISK_OFFICER",        # day-to-day risk lead
    "ESG_REPORTING_LEAD",          # disclosure assembly
    "BUSINESS_LINE_INTEGRATION",   # CCO/credit committee linkage
)

# Required climate governance practices
CLIMATE_GOVERNANCE_REQUIRED_PRACTICES: Tuple[str, ...] = (
    "BOARD_AGENDA_INCLUSION",      # standing board agenda item
    "QUARTERLY_RISK_REPORTING",    # quarterly RAS reporting
    "CLIMATE_TRAINING_PROGRAM",    # board + senior mgmt training
    "REMUNERATION_LINKAGE",        # IFRS S2 §29(g) — ESG-linked comp
    "INTERNAL_AUDIT_COVERAGE",     # internal audit reviews ESG disclosures
    "EXTERNAL_ASSURANCE",          # third-party verification of metrics
)


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IFRSS1Disclosure:
    """A single IFRS S1 general sustainability disclosure entry."""
    topic_category: str          # one of IFRS_S1_TOPIC_CATEGORIES
    core_content_area: str       # one of IFRS_S1_CORE_CONTENT_AREAS
    disclosure_text: str         # the disclosure narrative
    quantitative_metrics: Mapping[str, Decimal] = field(default_factory=dict)
    period_start: str = ""       # ISO-8601
    period_end: str = ""
    materiality_assessed: bool = False
    notes: str = ""

    def __post_init__(self):
        if self.topic_category not in IFRS_S1_TOPIC_CATEGORIES:
            raise ValueError(
                f"Invalid IFRS S1 topic category: {self.topic_category}")
        if self.core_content_area not in IFRS_S1_CORE_CONTENT_AREAS:
            raise ValueError(
                f"Invalid IFRS S1 core content area: {self.core_content_area}")


@dataclass(frozen=True)
class IFRSS2Disclosure:
    """A single IFRS S2 climate-related disclosure entry."""
    disclosure_id: str           # one of IFRS_S2_DISCLOSURES
    disclosure_text: str
    quantitative_metrics: Mapping[str, Decimal] = field(default_factory=dict)
    period_start: str = ""
    period_end: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.disclosure_id not in IFRS_S2_DISCLOSURES:
            raise ValueError(
                f"Invalid IFRS S2 disclosure ID: {self.disclosure_id}")


@dataclass(frozen=True)
class GreenAssetClassification:
    """KGFT-aligned green asset classification result."""
    asset_id: str
    kgft_category: str           # one of KGFT_GREEN_CATEGORIES; "" if unaligned
    alignment_level: str         # one of KGFT_ALIGNMENT_LEVELS
    eligibility_dimensions: Tuple[str, ...]   # which dimensions met
    dnsh_assessed: bool          # do-no-significant-harm criterion
    evidence_artifacts: Tuple[str, ...] = ()  # links/IDs of supporting docs
    notes: str = ""

    def is_green(self) -> bool:
        """True if classified as ALIGNED with at least one eligibility dim."""
        return (self.alignment_level == "ALIGNED"
                and len(self.eligibility_dimensions) > 0
                and self.dnsh_assessed)


@dataclass(frozen=True)
class PortfolioEmissionsRecord:
    """Scope 1/2/3 emissions with portfolio attribution.

    Extends utils/esg_reporting.GhgInventory with attribution data — what
    portion of emissions is attributable to financed activities.
    """
    period_start: str            # ISO-8601
    period_end: str
    scope_1_tco2e: Optional[Decimal] = None  # direct emissions
    scope_2_tco2e: Optional[Decimal] = None  # purchased electricity
    scope_3_tco2e: Optional[Decimal] = None  # value chain (Cat 1-15)
    scope_3_financed_tco2e: Optional[Decimal] = None  # PCAF Cat 15 financed
    scope_3_categories_breakdown: Mapping[str, Decimal] = field(
        default_factory=dict)
    intensity_per_revenue: Optional[Decimal] = None  # tCO2e/M KES revenue
    intensity_per_loan_kes: Optional[Decimal] = None  # tCO2e/M KES outstanding
    methodology_notes: str = ""

    def total_tco2e(self) -> Optional[Decimal]:
        """Total Scope 1+2+3. None if any scope missing (Rule 1)."""
        if (self.scope_1_tco2e is None
                or self.scope_2_tco2e is None
                or self.scope_3_tco2e is None):
            return None
        return (self.scope_1_tco2e
                + self.scope_2_tco2e
                + self.scope_3_tco2e)

    def financed_share_pct(self) -> Optional[Decimal]:
        """Financed emissions as % of total Scope 3."""
        if (self.scope_3_tco2e is None
                or self.scope_3_financed_tco2e is None
                or self.scope_3_tco2e == 0):
            return None
        return (self.scope_3_financed_tco2e
                / self.scope_3_tco2e * Decimal("100"))


@dataclass(frozen=True)
class ClimateGovernanceAssessment:
    """Result of governance assessment per IFRS S2 §6-§7 + CBK CRMF."""
    period_end: str
    roles_in_place: Tuple[str, ...]      # subset of REQUIRED_ROLES
    practices_in_place: Tuple[str, ...]  # subset of REQUIRED_PRACTICES
    completeness_pct: Decimal             # 0-100
    gaps_identified: Tuple[str, ...]
    notes: str = ""

    def is_compliant(self) -> bool:
        """All required roles + practices present."""
        return (len(self.roles_in_place)
                == len(CLIMATE_GOVERNANCE_REQUIRED_ROLES)
                and len(self.practices_in_place)
                == len(CLIMATE_GOVERNANCE_REQUIRED_PRACTICES))


# ════════════════════════════════════════════════════════════════════════
# Computation functions
# ════════════════════════════════════════════════════════════════════════

def classify_green_asset(
    *,
    asset_id: str,
    economic_activity: str,
    eligibility_dimensions: Sequence[str],
    dnsh_assessed: bool,
    transition_credible: bool = False,
    enabling_role: bool = False,
    evidence_artifacts: Sequence[str] = (),
) -> GreenAssetClassification:
    """Classify an asset against KGFT criteria.

    Parameters
    ----------
    economic_activity : KGFT category candidate or free text
    eligibility_dimensions : which KGFT_ELIGIBILITY_DIMENSIONS the activity meets
    dnsh_assessed : whether do-no-significant-harm has been verified
    transition_credible : True if asset is on credible transition path
    enabling_role : True if asset enables others to be green

    Returns
    -------
    GreenAssetClassification with alignment level and notes.
    """
    valid_dims = tuple(
        d for d in eligibility_dimensions
        if d in KGFT_ELIGIBILITY_DIMENSIONS)
    invalid_dims = tuple(
        d for d in eligibility_dimensions
        if d not in KGFT_ELIGIBILITY_DIMENSIONS)
    notes_parts = []
    if invalid_dims:
        notes_parts.append(f"unrecognized dimensions: {invalid_dims}")

    # Determine KGFT category match
    kgft_category = (
        economic_activity if economic_activity in KGFT_GREEN_CATEGORIES
        else "")

    # Alignment cascade
    if (kgft_category and len(valid_dims) > 0 and dnsh_assessed):
        alignment = "ALIGNED"
    elif transition_credible and kgft_category:
        alignment = "TRANSITIONING"
        notes_parts.append("on credible transition path")
    elif enabling_role:
        alignment = "ENABLING"
        notes_parts.append("enables others' alignment")
    else:
        alignment = "NON_ALIGNED"
        if not dnsh_assessed and kgft_category:
            notes_parts.append("DNSH not assessed — cannot classify ALIGNED")
        if not kgft_category:
            notes_parts.append(
                f"economic_activity '{economic_activity}' not in KGFT taxonomy")

    return GreenAssetClassification(
        asset_id=asset_id,
        kgft_category=kgft_category,
        alignment_level=alignment,
        eligibility_dimensions=valid_dims,
        dnsh_assessed=dnsh_assessed,
        evidence_artifacts=tuple(evidence_artifacts),
        notes="; ".join(notes_parts))


def compute_portfolio_emissions(
    *,
    period_start: str,
    period_end: str,
    scope_1_tco2e: Optional[Decimal] = None,
    scope_2_tco2e: Optional[Decimal] = None,
    scope_3_categories: Optional[Mapping[str, Decimal]] = None,
    scope_3_financed_tco2e: Optional[Decimal] = None,
    revenue_kes_m: Optional[Decimal] = None,
    loan_book_kes_m: Optional[Decimal] = None,
) -> PortfolioEmissionsRecord:
    """Aggregate Scope 1/2/3 emissions with portfolio intensity ratios.

    Honesty Rule 1: any unset scope leaves total=None (cannot infer).
    """
    scope_3_total: Optional[Decimal] = None
    if scope_3_categories:
        if not all(isinstance(v, Decimal) for v in scope_3_categories.values()):
            raise TypeError(
                "scope_3_categories values must be Decimal")
        scope_3_total = sum(
            scope_3_categories.values(), Decimal("0"))

    intensity_rev: Optional[Decimal] = None
    intensity_loan: Optional[Decimal] = None

    if (scope_1_tco2e is not None and scope_2_tco2e is not None
            and scope_3_total is not None):
        total = scope_1_tco2e + scope_2_tco2e + scope_3_total
        if revenue_kes_m and revenue_kes_m > 0:
            intensity_rev = total / revenue_kes_m
        if loan_book_kes_m and loan_book_kes_m > 0:
            intensity_loan = total / loan_book_kes_m

    return PortfolioEmissionsRecord(
        period_start=period_start,
        period_end=period_end,
        scope_1_tco2e=scope_1_tco2e,
        scope_2_tco2e=scope_2_tco2e,
        scope_3_tco2e=scope_3_total,
        scope_3_financed_tco2e=scope_3_financed_tco2e,
        scope_3_categories_breakdown=dict(scope_3_categories or {}),
        intensity_per_revenue=intensity_rev,
        intensity_per_loan_kes=intensity_loan,
        methodology_notes=(
            "GHG Protocol Corporate Standard + Scope 3 + PCAF for financed"))


def assess_ifrs_s1_compliance(
    disclosures: Sequence[IFRSS1Disclosure],
    *,
    required_topics: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Check coverage of IFRS S1 core content areas across required topics.

    Parameters
    ----------
    required_topics : subset of IFRS_S1_TOPIC_CATEGORIES that the entity has
                       deemed material (default = all 9). Per IFRS S1 §13,
                       only material topics need disclosure.

    Returns
    -------
    dict with completeness_pct, missing_combinations, total_required,
    by_topic, by_content_area.
    """
    topics = (
        tuple(required_topics) if required_topics
        else IFRS_S1_TOPIC_CATEGORIES)
    by_topic: Dict[str, set] = {t: set() for t in topics}
    by_content_area: Dict[str, int] = {
        a: 0 for a in IFRS_S1_CORE_CONTENT_AREAS}
    invalid_topics: List[str] = []

    for d in disclosures:
        if d.topic_category in by_topic:
            by_topic[d.topic_category].add(d.core_content_area)
            by_content_area[d.core_content_area] = (
                by_content_area[d.core_content_area] + 1)
        else:
            invalid_topics.append(d.topic_category)

    total_required = len(topics) * len(IFRS_S1_CORE_CONTENT_AREAS)
    total_present = sum(len(s) for s in by_topic.values())
    pct = (Decimal(total_present) / Decimal(total_required) * Decimal("100")
            if total_required > 0 else Decimal("0"))

    missing_combinations: List[Tuple[str, str]] = []
    for t in topics:
        for a in IFRS_S1_CORE_CONTENT_AREAS:
            if a not in by_topic.get(t, set()):
                missing_combinations.append((t, a))

    return {
        "completeness_pct": pct,
        "total_required": total_required,
        "total_present": total_present,
        "missing_combinations": missing_combinations,
        "by_topic_areas_covered": {t: sorted(s) for t, s in by_topic.items()},
        "by_content_area": by_content_area,
        "invalid_topics_seen": invalid_topics,
    }


def assess_ifrs_s2_compliance(
    disclosures: Sequence[IFRSS2Disclosure],
    *,
    scope_3_required: bool = True,
) -> Dict[str, object]:
    """Check coverage of all 21 IFRS S2 disclosure requirements.

    Parameters
    ----------
    scope_3_required : True from Year 2 of adoption. Year 1 transition relief
                       allows Scope 3 deferral per IFRS S2 §B58.
    """
    seen_ids = {d.disclosure_id for d in disclosures}
    required = set(IFRS_S2_DISCLOSURES)
    if not scope_3_required:
        required.discard("S2_MT_GHG_SCOPE_3")
    missing = sorted(required - seen_ids)
    extra = sorted(seen_ids - set(IFRS_S2_DISCLOSURES))
    pct = (Decimal(len(seen_ids & required))
            / Decimal(len(required))
            * Decimal("100")) if required else Decimal("0")
    return {
        "completeness_pct": pct,
        "total_required": len(required),
        "total_present": len(seen_ids & required),
        "missing_disclosures": missing,
        "unrecognized_disclosures": extra,
        "scope_3_required": scope_3_required,
    }


def validate_climate_governance(
    *,
    period_end: str,
    roles_in_place: Sequence[str],
    practices_in_place: Sequence[str],
) -> ClimateGovernanceAssessment:
    """Assess climate governance against IFRS S2 §6-§7 + CBK CRMF Pillar 1.

    Returns assessment with completeness % and gap list.
    """
    valid_roles = tuple(
        r for r in roles_in_place
        if r in CLIMATE_GOVERNANCE_REQUIRED_ROLES)
    valid_practices = tuple(
        p for p in practices_in_place
        if p in CLIMATE_GOVERNANCE_REQUIRED_PRACTICES)

    total_required = (
        len(CLIMATE_GOVERNANCE_REQUIRED_ROLES)
        + len(CLIMATE_GOVERNANCE_REQUIRED_PRACTICES))
    total_present = len(valid_roles) + len(valid_practices)
    pct = (Decimal(total_present) / Decimal(total_required) * Decimal("100")
            if total_required > 0 else Decimal("0"))

    gaps: List[str] = []
    for r in CLIMATE_GOVERNANCE_REQUIRED_ROLES:
        if r not in valid_roles:
            gaps.append(f"missing role: {r}")
    for p in CLIMATE_GOVERNANCE_REQUIRED_PRACTICES:
        if p not in valid_practices:
            gaps.append(f"missing practice: {p}")

    return ClimateGovernanceAssessment(
        period_end=period_end,
        roles_in_place=valid_roles,
        practices_in_place=valid_practices,
        completeness_pct=pct,
        gaps_identified=tuple(gaps),
        notes=(f"Assessed against IFRS S2 §6-§7 + CBK CRMF "
                f"({len(CLIMATE_GOVERNANCE_REQUIRED_ROLES)} roles, "
                f"{len(CLIMATE_GOVERNANCE_REQUIRED_PRACTICES)} practices)"))


def green_book_share_pct(
    classifications: Sequence[GreenAssetClassification],
    *,
    asset_balances: Optional[Mapping[str, Decimal]] = None,
) -> Dict[str, object]:
    """Compute share of book classified as ALIGNED green (KGFT).

    If asset_balances provided, weights by balance. Otherwise, equal-weighted.
    """
    if not classifications:
        return {
            "green_share_pct": Decimal("0"),
            "transitioning_share_pct": Decimal("0"),
            "non_aligned_share_pct": Decimal("0"),
            "total_assessed": 0,
            "weighting": "equal",
        }

    if asset_balances:
        weights = {
            c.asset_id: asset_balances.get(c.asset_id, Decimal("0"))
            for c in classifications}
        total = sum(weights.values(), Decimal("0"))
        weighting = "balance"
    else:
        weights = {c.asset_id: Decimal("1") for c in classifications}
        total = Decimal(len(classifications))
        weighting = "equal"

    if total == 0:
        return {
            "green_share_pct": Decimal("0"),
            "transitioning_share_pct": Decimal("0"),
            "non_aligned_share_pct": Decimal("0"),
            "total_assessed": len(classifications),
            "weighting": weighting,
        }

    aligned = sum(
        weights[c.asset_id] for c in classifications
        if c.alignment_level == "ALIGNED")
    transitioning = sum(
        weights[c.asset_id] for c in classifications
        if c.alignment_level == "TRANSITIONING")
    non_aligned = sum(
        weights[c.asset_id] for c in classifications
        if c.alignment_level == "NON_ALIGNED")

    return {
        "green_share_pct": aligned / total * Decimal("100"),
        "transitioning_share_pct": transitioning / total * Decimal("100"),
        "non_aligned_share_pct": non_aligned / total * Decimal("100"),
        "total_assessed": len(classifications),
        "weighting": weighting,
    }


# ════════════════════════════════════════════════════════════════════════
# High-level engine
# ════════════════════════════════════════════════════════════════════════

class ESGIntelligenceEngine:
    """Orchestrator that integrates IFRS S1/S2 + KGFT + governance.

    v10.6: foundation only. v10.7 will plug climate risk modeling, v10.8
    climate-adjusted ECL, v10.9 KGFT/CRDF reporting outputs, v10.10
    audit gate G120 + arc closure.
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._ifrs_s1: List[IFRSS1Disclosure] = []
        self._ifrs_s2: List[IFRSS2Disclosure] = []
        self._green_assets: List[GreenAssetClassification] = []
        self._emissions: List[PortfolioEmissionsRecord] = []
        self._governance: List[ClimateGovernanceAssessment] = []

    # ── Add ─────────────────────────────────────────────────────────────
    def add_ifrs_s1(self, d: IFRSS1Disclosure) -> None:
        self._ifrs_s1.append(d)

    def add_ifrs_s2(self, d: IFRSS2Disclosure) -> None:
        self._ifrs_s2.append(d)

    def add_green_asset(self, c: GreenAssetClassification) -> None:
        self._green_assets.append(c)

    def add_emissions(self, e: PortfolioEmissionsRecord) -> None:
        self._emissions.append(e)

    def add_governance(self, g: ClimateGovernanceAssessment) -> None:
        self._governance.append(g)

    # ── Assess ──────────────────────────────────────────────────────────
    def assess_all_frameworks(
        self,
        *,
        s1_required_topics: Optional[Sequence[str]] = None,
        s2_scope_3_required: bool = True,
        asset_balances: Optional[Mapping[str, Decimal]] = None,
    ) -> Dict[str, object]:
        """Run all framework assessments in one pass."""
        return {
            "entity": self.entity_name,
            "ifrs_s1": assess_ifrs_s1_compliance(
                self._ifrs_s1, required_topics=s1_required_topics),
            "ifrs_s2": assess_ifrs_s2_compliance(
                self._ifrs_s2, scope_3_required=s2_scope_3_required),
            "kgft_book_share": green_book_share_pct(
                self._green_assets, asset_balances=asset_balances),
            "governance_latest": (
                self._governance[-1] if self._governance else None),
            "emissions_latest": (
                self._emissions[-1] if self._emissions else None),
            "framework_deadlines": {
                "ifrs_s1_s2_mandatory": IFRS_S1_S2_MANDATORY_DEADLINE,
                "crdf_first_period": CRDF_FIRST_REPORTING_PERIOD,
            },
        }

    # ── Board summary (CEO/Board-ready) ─────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        """One-pager view for board climate oversight."""
        ifrs_s2 = assess_ifrs_s2_compliance(self._ifrs_s2)
        kgft = green_book_share_pct(self._green_assets)
        gov = self._governance[-1] if self._governance else None
        emissions = self._emissions[-1] if self._emissions else None

        readiness_status: str
        if ifrs_s2["completeness_pct"] >= Decimal("100"):
            readiness_status = "READY"
        elif ifrs_s2["completeness_pct"] >= Decimal("75"):
            readiness_status = "ON_TRACK"
        elif ifrs_s2["completeness_pct"] >= Decimal("50"):
            readiness_status = "AT_RISK"
        else:
            readiness_status = "URGENT_ACTION_REQUIRED"

        return {
            "entity": self.entity_name,
            "ifrs_s2_completeness_pct": ifrs_s2["completeness_pct"],
            "ifrs_s2_readiness_status": readiness_status,
            "ifrs_s2_missing_count": len(ifrs_s2["missing_disclosures"]),
            "green_book_share_pct": kgft["green_share_pct"],
            "transitioning_share_pct": kgft["transitioning_share_pct"],
            "scope_1_tco2e": (
                emissions.scope_1_tco2e if emissions else None),
            "scope_2_tco2e": (
                emissions.scope_2_tco2e if emissions else None),
            "scope_3_tco2e": (
                emissions.scope_3_tco2e if emissions else None),
            "total_emissions_tco2e": (
                emissions.total_tco2e() if emissions else None),
            "governance_compliant": gov.is_compliant() if gov else None,
            "governance_completeness_pct": (
                gov.completeness_pct if gov else None),
            "governance_gap_count": (
                len(gov.gaps_identified) if gov else None),
            "deadline_ifrs_s1_s2": IFRS_S1_S2_MANDATORY_DEADLINE,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test (run as `python -m utils.esg_intelligence`)
# ════════════════════════════════════════════════════════════════════════

def _test_frameworks_enum_complete():
    """All 6 frameworks present in enum."""
    expected = {"IFRS_S1", "IFRS_S2", "TCFD", "KGFT_CBK", "CRDF_CBK", "CBK_CRMF"}
    actual = {f.value for f in ESGFramework}
    assert actual == expected, f"frameworks mismatch: {actual ^ expected}"


def _test_ifrs_s1_topics_byte_for_byte():
    """IFRS S1 9 topic categories match standard."""
    assert len(IFRS_S1_TOPIC_CATEGORIES) == 9
    assert "CLIMATE" in IFRS_S1_TOPIC_CATEGORIES
    assert "BIODIVERSITY_AND_ECOSYSTEMS" in IFRS_S1_TOPIC_CATEGORIES


def _test_ifrs_s1_core_content_areas():
    """4 core content areas match IFRS S1 standard."""
    assert IFRS_S1_CORE_CONTENT_AREAS == (
        "GOVERNANCE", "STRATEGY", "RISK_MANAGEMENT", "METRICS_AND_TARGETS")


def _test_ifrs_s2_disclosures_count():
    """At least 21 IFRS S2 disclosures (2 gov + 6 strat + 3 RM + 10 MT)."""
    assert len(IFRS_S2_DISCLOSURES) >= 21
    # Scope 1/2/3 mandatory
    assert "S2_MT_GHG_SCOPE_1" in IFRS_S2_DISCLOSURES
    assert "S2_MT_GHG_SCOPE_2" in IFRS_S2_DISCLOSURES
    assert "S2_MT_GHG_SCOPE_3" in IFRS_S2_DISCLOSURES


def _test_kgft_categories_complete():
    """KGFT 8 green categories per CBK Apr 2025."""
    assert len(KGFT_GREEN_CATEGORIES) == 8
    assert "RENEWABLE_ENERGY" in KGFT_GREEN_CATEGORIES
    assert "GREEN_BUILDINGS" in KGFT_GREEN_CATEGORIES


def _test_kgft_alignment_levels():
    """4 alignment levels."""
    assert KGFT_ALIGNMENT_LEVELS == (
        "ALIGNED", "TRANSITIONING", "ENABLING", "NON_ALIGNED")


def _test_governance_required_roles():
    """5 climate governance roles required."""
    assert len(CLIMATE_GOVERNANCE_REQUIRED_ROLES) == 5
    assert "BOARD_CLIMATE_OVERSIGHT" in CLIMATE_GOVERNANCE_REQUIRED_ROLES


def _test_classify_green_asset_aligned():
    """Asset meeting all criteria → ALIGNED."""
    c = classify_green_asset(
        asset_id="LOAN-001",
        economic_activity="RENEWABLE_ENERGY",
        eligibility_dimensions=("CLIMATE_MITIGATION",),
        dnsh_assessed=True,
        evidence_artifacts=("EDGE-cert-2025",))
    assert c.alignment_level == "ALIGNED"
    assert c.is_green() is True
    assert c.kgft_category == "RENEWABLE_ENERGY"


def _test_classify_green_asset_dnsh_failure():
    """Without DNSH assessment, cannot be ALIGNED."""
    c = classify_green_asset(
        asset_id="LOAN-002",
        economic_activity="ENERGY_EFFICIENCY",
        eligibility_dimensions=("CLIMATE_MITIGATION",),
        dnsh_assessed=False)
    assert c.alignment_level == "NON_ALIGNED"
    assert c.is_green() is False
    assert "DNSH" in c.notes


def _test_classify_green_asset_unknown_activity():
    """Activity not in KGFT → NON_ALIGNED with note."""
    c = classify_green_asset(
        asset_id="LOAN-003",
        economic_activity="OIL_AND_GAS",
        eligibility_dimensions=("CLIMATE_MITIGATION",),
        dnsh_assessed=True)
    assert c.alignment_level == "NON_ALIGNED"
    assert "not in KGFT" in c.notes


def _test_classify_green_asset_transitioning():
    """Credible transition path → TRANSITIONING."""
    c = classify_green_asset(
        asset_id="LOAN-004",
        economic_activity="SUSTAINABLE_AGRICULTURE",
        eligibility_dimensions=(),
        dnsh_assessed=False,
        transition_credible=True)
    assert c.alignment_level == "TRANSITIONING"


def _test_compute_emissions_total():
    """Total = Scope 1 + 2 + 3 when all present."""
    e = compute_portfolio_emissions(
        period_start="2025-01-01",
        period_end="2025-12-31",
        scope_1_tco2e=Decimal("1000"),
        scope_2_tco2e=Decimal("2000"),
        scope_3_categories={"CAT_15": Decimal("50000")})
    assert e.total_tco2e() == Decimal("53000")


def _test_compute_emissions_total_missing_rule1():
    """Missing scope → total None (Rule 1 honesty)."""
    e = compute_portfolio_emissions(
        period_start="2025-01-01",
        period_end="2025-12-31",
        scope_1_tco2e=Decimal("1000"),
        scope_3_categories={"CAT_15": Decimal("50000")})
    # Scope 2 missing
    assert e.total_tco2e() is None


def _test_compute_emissions_intensity():
    """Intensity = total / revenue (or loan book)."""
    e = compute_portfolio_emissions(
        period_start="2025-01-01",
        period_end="2025-12-31",
        scope_1_tco2e=Decimal("1000"),
        scope_2_tco2e=Decimal("2000"),
        scope_3_categories={"CAT_15": Decimal("50000")},
        revenue_kes_m=Decimal("10000"),
        loan_book_kes_m=Decimal("100000"))
    assert e.intensity_per_revenue == Decimal("5.3")
    assert e.intensity_per_loan_kes == Decimal("0.53")


def _test_compute_emissions_financed_share():
    """Financed share % computed correctly."""
    e = compute_portfolio_emissions(
        period_start="2025-01-01",
        period_end="2025-12-31",
        scope_1_tco2e=Decimal("100"),
        scope_2_tco2e=Decimal("200"),
        scope_3_categories={"CAT_15": Decimal("1000")},
        scope_3_financed_tco2e=Decimal("800"))
    assert e.financed_share_pct() == Decimal("80")


def _test_assess_ifrs_s1_full_coverage():
    """All 9 topics x 4 areas = 36 disclosures → 100%."""
    disclosures = [
        IFRSS1Disclosure(
            topic_category=t, core_content_area=a,
            disclosure_text=f"{t}-{a}",
            materiality_assessed=True)
        for t in IFRS_S1_TOPIC_CATEGORIES
        for a in IFRS_S1_CORE_CONTENT_AREAS]
    result = assess_ifrs_s1_compliance(disclosures)
    assert result["completeness_pct"] == Decimal("100")
    assert result["missing_combinations"] == []


def _test_assess_ifrs_s1_partial():
    """Climate only → 4 / 36 = 11.1%."""
    disclosures = [
        IFRSS1Disclosure(
            topic_category="CLIMATE", core_content_area=a,
            disclosure_text=f"climate-{a}")
        for a in IFRS_S1_CORE_CONTENT_AREAS]
    result = assess_ifrs_s1_compliance(disclosures)
    expected = Decimal("4") / Decimal("36") * Decimal("100")
    assert result["completeness_pct"] == expected


def _test_assess_ifrs_s1_required_topics_only():
    """If only CLIMATE required, full CLIMATE coverage = 100%."""
    disclosures = [
        IFRSS1Disclosure(
            topic_category="CLIMATE", core_content_area=a,
            disclosure_text=f"climate-{a}")
        for a in IFRS_S1_CORE_CONTENT_AREAS]
    result = assess_ifrs_s1_compliance(
        disclosures, required_topics=("CLIMATE",))
    assert result["completeness_pct"] == Decimal("100")


def _test_assess_ifrs_s2_full():
    """All 21 disclosures present → 100%."""
    disclosures = [
        IFRSS2Disclosure(disclosure_id=d, disclosure_text=d)
        for d in IFRS_S2_DISCLOSURES]
    result = assess_ifrs_s2_compliance(disclosures)
    assert result["completeness_pct"] == Decimal("100")
    assert result["missing_disclosures"] == []


def _test_assess_ifrs_s2_year_one_relief():
    """Year 1 transition relief: Scope 3 not required → still 100% if all others present."""
    disclosures = [
        IFRSS2Disclosure(disclosure_id=d, disclosure_text=d)
        for d in IFRS_S2_DISCLOSURES if d != "S2_MT_GHG_SCOPE_3"]
    result = assess_ifrs_s2_compliance(disclosures, scope_3_required=False)
    assert result["completeness_pct"] == Decimal("100")
    assert "S2_MT_GHG_SCOPE_3" not in result["missing_disclosures"]


def _test_governance_full_compliance():
    """All required roles + practices → compliant."""
    g = validate_climate_governance(
        period_end="2025-12-31",
        roles_in_place=CLIMATE_GOVERNANCE_REQUIRED_ROLES,
        practices_in_place=CLIMATE_GOVERNANCE_REQUIRED_PRACTICES)
    assert g.is_compliant()
    assert g.completeness_pct == Decimal("100")
    assert g.gaps_identified == ()


def _test_governance_partial():
    """Half present → 50% completeness."""
    half_roles = CLIMATE_GOVERNANCE_REQUIRED_ROLES[:3]
    half_pract = CLIMATE_GOVERNANCE_REQUIRED_PRACTICES[:3]
    g = validate_climate_governance(
        period_end="2025-12-31",
        roles_in_place=half_roles,
        practices_in_place=half_pract)
    assert not g.is_compliant()
    assert len(g.gaps_identified) == (
        len(CLIMATE_GOVERNANCE_REQUIRED_ROLES) - 3
        + len(CLIMATE_GOVERNANCE_REQUIRED_PRACTICES) - 3)


def _test_green_book_share_equal_weighted():
    """3 ALIGNED, 1 TRANSITIONING, 1 NON_ALIGNED → 60% green."""
    classifications = [
        GreenAssetClassification(
            asset_id=f"L-{i}", kgft_category="RENEWABLE_ENERGY",
            alignment_level="ALIGNED",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True)
        for i in range(3)
    ] + [
        GreenAssetClassification(
            asset_id="L-4", kgft_category="ENERGY_EFFICIENCY",
            alignment_level="TRANSITIONING",
            eligibility_dimensions=(),
            dnsh_assessed=False),
        GreenAssetClassification(
            asset_id="L-5", kgft_category="",
            alignment_level="NON_ALIGNED",
            eligibility_dimensions=(),
            dnsh_assessed=False),
    ]
    result = green_book_share_pct(classifications)
    assert result["green_share_pct"] == Decimal("60")
    assert result["transitioning_share_pct"] == Decimal("20")


def _test_green_book_share_balance_weighted():
    """Balance-weighted share differs from equal-weighted."""
    classifications = [
        GreenAssetClassification(
            asset_id="BIG", kgft_category="RENEWABLE_ENERGY",
            alignment_level="ALIGNED",
            eligibility_dimensions=("CLIMATE_MITIGATION",),
            dnsh_assessed=True),
        GreenAssetClassification(
            asset_id="SMALL", kgft_category="",
            alignment_level="NON_ALIGNED",
            eligibility_dimensions=(),
            dnsh_assessed=False),
    ]
    balances = {"BIG": Decimal("9000"), "SMALL": Decimal("1000")}
    result = green_book_share_pct(classifications, asset_balances=balances)
    assert result["green_share_pct"] == Decimal("90")
    assert result["weighting"] == "balance"


def _test_engine_assess_all_frameworks():
    """End-to-end assessment via engine."""
    eng = ESGIntelligenceEngine(entity_name="Test Bank")
    eng.add_ifrs_s1(IFRSS1Disclosure(
        topic_category="CLIMATE",
        core_content_area="GOVERNANCE",
        disclosure_text="Board oversees climate"))
    eng.add_ifrs_s2(IFRSS2Disclosure(
        disclosure_id="S2_GOV_BOARD_OVERSIGHT",
        disclosure_text="Board chairs climate committee"))
    eng.add_green_asset(GreenAssetClassification(
        asset_id="LOAN-1", kgft_category="RENEWABLE_ENERGY",
        alignment_level="ALIGNED",
        eligibility_dimensions=("CLIMATE_MITIGATION",),
        dnsh_assessed=True))
    eng.add_emissions(compute_portfolio_emissions(
        period_start="2025-01-01", period_end="2025-12-31",
        scope_1_tco2e=Decimal("100"),
        scope_2_tco2e=Decimal("200"),
        scope_3_categories={"CAT_15": Decimal("1000")}))
    eng.add_governance(validate_climate_governance(
        period_end="2025-12-31",
        roles_in_place=CLIMATE_GOVERNANCE_REQUIRED_ROLES,
        practices_in_place=CLIMATE_GOVERNANCE_REQUIRED_PRACTICES))

    result = eng.assess_all_frameworks()
    assert "ifrs_s1" in result
    assert "ifrs_s2" in result
    assert "kgft_book_share" in result
    assert result["kgft_book_share"]["green_share_pct"] == Decimal("100")
    assert result["governance_latest"].is_compliant()


def _test_engine_board_summary():
    """Board summary returns expected keys + readiness status."""
    eng = ESGIntelligenceEngine()
    for d in IFRS_S2_DISCLOSURES:
        eng.add_ifrs_s2(IFRSS2Disclosure(disclosure_id=d, disclosure_text=d))
    eng.add_governance(validate_climate_governance(
        period_end="2025-12-31",
        roles_in_place=CLIMATE_GOVERNANCE_REQUIRED_ROLES,
        practices_in_place=CLIMATE_GOVERNANCE_REQUIRED_PRACTICES))

    summary = eng.board_summary()
    assert summary["ifrs_s2_completeness_pct"] == Decimal("100")
    assert summary["ifrs_s2_readiness_status"] == "READY"
    assert summary["governance_compliant"] is True
    assert summary["deadline_ifrs_s1_s2"] == "2027-01-01"


def _test_engine_board_summary_urgent():
    """Empty engine → URGENT_ACTION_REQUIRED."""
    eng = ESGIntelligenceEngine()
    summary = eng.board_summary()
    assert summary["ifrs_s2_readiness_status"] == "URGENT_ACTION_REQUIRED"


def _test_invalid_ifrs_s1_topic_rejected():
    """Invalid topic category raises ValueError."""
    try:
        IFRSS1Disclosure(
            topic_category="INVALID_TOPIC",
            core_content_area="GOVERNANCE",
            disclosure_text="test")
        assert False, "should have raised"
    except ValueError as e:
        assert "Invalid IFRS S1 topic" in str(e)


def _test_invalid_ifrs_s2_disclosure_rejected():
    """Invalid disclosure ID raises ValueError."""
    try:
        IFRSS2Disclosure(
            disclosure_id="S2_INVALID",
            disclosure_text="test")
        assert False, "should have raised"
    except ValueError as e:
        assert "Invalid IFRS S2 disclosure" in str(e)


def _test_decimal_purity():
    """All numeric methods return Decimal, not float."""
    e = compute_portfolio_emissions(
        period_start="2025-01-01", period_end="2025-12-31",
        scope_1_tco2e=Decimal("100"),
        scope_2_tco2e=Decimal("200"),
        scope_3_categories={"CAT_15": Decimal("300")},
        revenue_kes_m=Decimal("1000"))
    assert isinstance(e.total_tco2e(), Decimal)
    assert isinstance(e.intensity_per_revenue, Decimal)


def self_test() -> None:
    """Run all self-tests. Invoked by `python -m utils.esg_intelligence`."""
    tests = [
        _test_frameworks_enum_complete,
        _test_ifrs_s1_topics_byte_for_byte,
        _test_ifrs_s1_core_content_areas,
        _test_ifrs_s2_disclosures_count,
        _test_kgft_categories_complete,
        _test_kgft_alignment_levels,
        _test_governance_required_roles,
        _test_classify_green_asset_aligned,
        _test_classify_green_asset_dnsh_failure,
        _test_classify_green_asset_unknown_activity,
        _test_classify_green_asset_transitioning,
        _test_compute_emissions_total,
        _test_compute_emissions_total_missing_rule1,
        _test_compute_emissions_intensity,
        _test_compute_emissions_financed_share,
        _test_assess_ifrs_s1_full_coverage,
        _test_assess_ifrs_s1_partial,
        _test_assess_ifrs_s1_required_topics_only,
        _test_assess_ifrs_s2_full,
        _test_assess_ifrs_s2_year_one_relief,
        _test_governance_full_compliance,
        _test_governance_partial,
        _test_green_book_share_equal_weighted,
        _test_green_book_share_balance_weighted,
        _test_engine_assess_all_frameworks,
        _test_engine_board_summary,
        _test_engine_board_summary_urgent,
        _test_invalid_ifrs_s1_topic_rejected,
        _test_invalid_ifrs_s2_disclosure_rejected,
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
        print(f"✗ esg_intelligence self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ esg_intelligence self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

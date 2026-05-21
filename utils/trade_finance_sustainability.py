"""utils/trade_finance_sustainability.py — v10.77: TF sustainability.

ENH-278 — Sustainable Trade Finance. Cat B — trade_finance arc 7/N.

Diagnostic ESG / climate / sustainability screening engine for
trade finance instruments. Operates entirely with caller-supplied
data — taxonomy, exclusion list, emission factors, ESG attribution
maps are operationally maintained (KGFT updates annually; KBA SFI
periodically; PCAF emission factors per sector update; rating
agency feeds refresh continuously). Same discipline as ENH-274 —
engine does NOT bundle any list, classification, or factor.

Five capabilities:

  1. classify_instrument_sustainability — Apply caller-supplied
     taxonomy (keyword → tier mapping per KGFT / KBA SFI / EU
     Taxonomy / ICC SDG Trade Finance Standards) to instrument
     goods description. Returns SustainabilityClassification with
     ALL matches surfaced (per Rule 1 — operator sees every
     signal, not just the engine's pick) plus a most-conservative
     primary_tier (BROWN > TRANSITION > GREEN > UNCLASSIFIED) and
     a `conflicting` flag when multiple tiers detected.

  2. screen_exclusion_list — Word-boundary-regex match against
     caller-supplied exclusion keywords (coal, tobacco, weapons,
     controversial sectors per KBA SFI). 4-tier ExclusionSeverity
     ladder. Returns hits + 4-tier ScreeningOutcome.

  3. compute_ghg_attribution — PCAF-aligned attributed financed
     emissions: amount_financed × emission_factor where
     emission_factor is sector-specific kg CO2e per KES financed.
     Caller supplies sector_attribution + emission_factors maps.
     Returns sector + factor + attributed_emissions per
     instrument; surfaces UNATTRIBUTED when sector or factor
     missing rather than fabricating zero.

  4. assess_counterparty_esg_risk — Per-counterparty ESG risk
     tier lookup (caller-supplied attribution map). Returns
     applicant + beneficiary risk tiers + worst-of-pair severity
     for the instrument. UNRATED when counterparty not in map.

  5. build_sustainability_report — Portfolio orchestrator:
     green/transition/brown/unclassified shares, total attributed
     emissions, exclusion hits, top-emitting sectors, ESG risk
     distribution.

Per Rule 7, engine NEVER:
  - sets sustainability classifications (taxonomy is caller-
    supplied; engine looks up only)
  - blocks transactions (operator adjudicates per outcome ladder)
  - amends taxonomy or exclusion list (operationally separate)
  - reports to CBK / regulators (climate disclosure flows
    through ENH-CLIM-* engines)
  - adjusts pricing or terms (RM / pricing system territory)
  - sources emission factors or ESG ratings (caller supplies)
  - mutates inputs

Per Rule 1, every output surfaces matched_keywords + sources +
framework_refs (KGFT / KBA SFI / EU Taxonomy / ICC SDG / PCAF
methodology / TCFD / Equator Principles / Rule 7 documentation).

Pure stdlib. No third-party dependencies.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import (
    Dict, List, Mapping, Optional, Sequence, Tuple)

from utils.trade_finance_instruments import (
    TradeInstrument, InstrumentState)

SPEC_DEVIATION_NOTE = (
    "TradeFinanceSustainabilityEngine implements ENH-278 — "
    "diagnostic ESG / climate / sustainability screening for "
    "trade finance instruments. Caller-supplied taxonomy + "
    "exclusion list + emission factors + ESG attribution maps "
    "(operationally maintained per KGFT/KBA SFI/EU Taxonomy "
    "update cadences). Engine bundles no lists. Pure stdlib. "
    "Per Rule 1, every output surfaces matched_keywords + "
    "sources + framework_refs. Per Rule 7, engine DIAGNOSTIC "
    "ONLY — never sets classifications, never blocks "
    "transactions, never amends taxonomy / exclusion list, "
    "never reports to regulators (climate disclosure is ENH-"
    "CLIM-* engines' territory), never adjusts pricing, never "
    "sources factors / ratings (caller supplies), never mutates "
    "inputs."
)

# Word-boundary regex floor — same discipline as ENH-274.
# Substring matches shorter than this are rejected to prevent
# false positives (e.g. 'oil' matching 'recoiling').
MIN_KEYWORD_LENGTH: int = 3


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class SustainabilityTier(Enum):
    """4-tier sustainability classification per KGFT / KBA SFI /
    EU Taxonomy alignment.

    GREEN: clearly aligned with sustainability objectives (e.g.
        renewable energy equipment, climate-resilient agriculture)
    TRANSITION: contributing to transition pathways but not
        already green (e.g. natural gas in some taxonomies,
        energy efficiency retrofits)
    BROWN: misaligned with sustainability objectives (e.g.
        thermal coal, certain heavy industries)
    UNCLASSIFIED: no taxonomy keyword matched — operator may
        either classify manually or accept as out-of-taxonomy
    """
    GREEN = "GREEN"
    TRANSITION = "TRANSITION"
    BROWN = "BROWN"
    UNCLASSIFIED = "UNCLASSIFIED"


class ExclusionSeverity(Enum):
    """4-tier severity for exclusion list hits."""
    CRITICAL = "CRITICAL"   # absolute prohibition (e.g. weapons)
    HIGH = "HIGH"           # bank-level exclusion (e.g. thermal coal)
    MEDIUM = "MEDIUM"       # senior-approval required
    LOW = "LOW"             # disclosure or review-only


class EsgRiskTier(Enum):
    """4-tier ESG risk + UNRATED for counterparties not in map."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    UNRATED = "UNRATED"


class SustainabilityScreeningOutcome(Enum):
    """Outcome ladder for the orchestrator-level decision."""
    ELIGIBLE_GREEN = "ELIGIBLE_GREEN"      # all green, no hits
    ELIGIBLE_TRANSITION = "ELIGIBLE_TRANSITION"
    REVIEW_NEEDED = "REVIEW_NEEDED"        # mixed signals
    SENIOR_APPROVAL = "SENIOR_APPROVAL"    # high-severity hit
    EXCLUDED = "EXCLUDED"                  # critical hit


class GhgAttributionStatus(Enum):
    ATTRIBUTED = "ATTRIBUTED"
    SECTOR_UNKNOWN = "SECTOR_UNKNOWN"      # applicant not in map
    FACTOR_UNKNOWN = "FACTOR_UNKNOWN"      # sector has no factor


# ════════════════════════════════════════════════════════════════════════
# Caller-supplied input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TaxonomyEntry:
    """One entry in the caller-supplied sustainability taxonomy."""
    keyword: str
    tier: SustainabilityTier
    source: str          # e.g. 'KGFT 2025 §3.2', 'EU Taxonomy Annex I'
    justification: str = ""

    def __post_init__(self) -> None:
        if len(self.keyword) < MIN_KEYWORD_LENGTH:
            raise ValueError(
                f"taxonomy keyword '{self.keyword}' shorter than "
                f"{MIN_KEYWORD_LENGTH}-char floor — would risk "
                f"false positives via substring match")
        if self.tier == SustainabilityTier.UNCLASSIFIED:
            raise ValueError(
                "TaxonomyEntry tier cannot be UNCLASSIFIED "
                "(UNCLASSIFIED is the no-match outcome, not a "
                "taxonomy tier)")


@dataclass(frozen=True)
class ExclusionEntry:
    """One entry in the caller-supplied exclusion list."""
    keyword: str
    severity: ExclusionSeverity
    source: str          # e.g. 'KBA SFI 2024 §4.1 — coal phase-out'
    justification: str = ""

    def __post_init__(self) -> None:
        if len(self.keyword) < MIN_KEYWORD_LENGTH:
            raise ValueError(
                f"exclusion keyword '{self.keyword}' shorter than "
                f"{MIN_KEYWORD_LENGTH}-char floor")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SustainabilityMatch:
    """A single keyword match in the goods description."""
    keyword: str
    tier: SustainabilityTier
    source: str
    matched_text: str        # the actual substring matched
    justification: str


@dataclass(frozen=True)
class SustainabilityClassification:
    instrument_id: str
    primary_tier: SustainabilityTier
    all_matches: Tuple[SustainabilityMatch, ...]
    conflicting: bool        # True if matches span multiple tiers
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class ExclusionHit:
    instrument_id: str
    matched_keyword: str
    matched_text: str
    severity: ExclusionSeverity
    source: str
    justification: str


@dataclass(frozen=True)
class ExclusionScreeningResult:
    instrument_id: str
    hits: Tuple[ExclusionHit, ...]
    outcome: SustainabilityScreeningOutcome
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class GhgAttribution:
    instrument_id: str
    sector: Optional[str]
    amount_kes: Decimal
    emission_factor_kgco2e_per_kes: Optional[Decimal]
    attributed_emissions_kgco2e: Optional[Decimal]
    status: GhgAttributionStatus
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class EsgRiskAssessment:
    instrument_id: str
    applicant_id: str
    applicant_risk: EsgRiskTier
    beneficiary_id: str
    beneficiary_risk: EsgRiskTier
    worst_of_pair: EsgRiskTier      # max(applicant, beneficiary)
    framework_refs: Tuple[str, ...]


@dataclass(frozen=True)
class SustainabilityReport:
    as_of_date: str
    instrument_count: int
    total_notional_kes: Decimal
    by_tier_share: Dict[str, Decimal]   # tier value -> share 0..1
    by_tier_notional_kes: Dict[str, Decimal]
    total_attributed_emissions_kgco2e: Decimal
    unattributed_count: int
    top_emitting_sectors: Tuple[Tuple[str, Decimal], ...]
    exclusion_hit_count: int
    exclusion_critical_count: int
    by_esg_tier_count: Dict[str, int]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceSustainabilityEngine:
    """Diagnostic ESG / climate sustainability screening engine."""

    # Tier conservatism ordering (worst-first) — for primary_tier
    # selection when matches conflict, surface the most
    # conservative signal so operator sees the worst case.
    _TIER_CONSERVATISM_ORDER = (
        SustainabilityTier.BROWN,
        SustainabilityTier.TRANSITION,
        SustainabilityTier.GREEN,
    )

    # Severity ordering for ESG risk worst-of-pair
    _ESG_RISK_ORDER = {
        EsgRiskTier.UNRATED: 0,
        EsgRiskTier.LOW: 1,
        EsgRiskTier.MEDIUM: 2,
        EsgRiskTier.HIGH: 3,
        EsgRiskTier.SEVERE: 4,
    }

    @staticmethod
    def _word_boundary_search(
        haystack: str, keyword: str,
    ) -> Optional[str]:
        """Case-insensitive word-boundary search. Returns the
        matched text on hit, None on miss. Same discipline as
        ENH-274 — prevents 'oil' matching 'recoiling'.
        """
        if len(keyword) < MIN_KEYWORD_LENGTH:
            return None
        pattern = (
            r"\b" + re.escape(keyword) + r"\b")
        match = re.search(
            pattern, haystack, flags=re.IGNORECASE)
        return match.group(0) if match else None

    # ─── 1. Sustainability classification ───────────────────────
    def classify_instrument_sustainability(
        self,
        instrument: TradeInstrument,
        taxonomy: Sequence[TaxonomyEntry],
    ) -> SustainabilityClassification:
        """Match goods_description against caller-supplied taxonomy.

        Returns ALL matches (per Rule 1 — operator sees every
        signal, not just the engine's pick) plus most-conservative
        primary_tier and conflicting flag.
        """
        goods = instrument.description_of_goods or ""
        matches: List[SustainabilityMatch] = []
        for entry in taxonomy:
            matched = self._word_boundary_search(
                goods, entry.keyword)
            if matched is None:
                continue
            matches.append(SustainabilityMatch(
                keyword=entry.keyword,
                tier=entry.tier,
                source=entry.source,
                matched_text=matched,
                justification=entry.justification))

        # Determine primary tier — most-conservative-tier-present
        if not matches:
            primary = SustainabilityTier.UNCLASSIFIED
            conflicting = False
        else:
            tiers_seen = {m.tier for m in matches}
            primary = next(
                (t for t in self._TIER_CONSERVATISM_ORDER
                 if t in tiers_seen),
                SustainabilityTier.UNCLASSIFIED)
            conflicting = len(tiers_seen) > 1

        return SustainabilityClassification(
            instrument_id=instrument.instrument_id,
            primary_tier=primary,
            all_matches=tuple(matches),
            conflicting=conflicting,
            framework_refs=(
                "ENH-278 §classify_instrument_sustainability",
                "KGFT (Kenya Green Finance Taxonomy 2025) — "
                "tier definitions caller-supplied",
                "KBA Sustainable Finance Initiative — sector "
                "alignment",
                "EU Taxonomy / ICC SDG Trade Finance Standards "
                "— operator chooses framework",
                "Per Rule 1 — ALL matches surfaced; operator "
                "sees every signal not just engine's pick",
                "Per Rule 7 — engine never sets classifications; "
                "primary_tier is mechanical worst-of-matches "
                "rollup; operator adjudicates conflicting cases",
            ),
        )

    # ─── 2. Exclusion list screening ────────────────────────────
    def screen_exclusion_list(
        self,
        instrument: TradeInstrument,
        exclusion_list: Sequence[ExclusionEntry],
    ) -> ExclusionScreeningResult:
        """Word-boundary-regex match against caller-supplied
        exclusion list. Returns hits + outcome ladder."""
        goods = instrument.description_of_goods or ""
        hits: List[ExclusionHit] = []
        for entry in exclusion_list:
            matched = self._word_boundary_search(
                goods, entry.keyword)
            if matched is None:
                continue
            hits.append(ExclusionHit(
                instrument_id=instrument.instrument_id,
                matched_keyword=entry.keyword,
                matched_text=matched,
                severity=entry.severity,
                source=entry.source,
                justification=entry.justification))

        # Outcome ladder — driven by highest severity hit
        if not hits:
            outcome = (
                SustainabilityScreeningOutcome.ELIGIBLE_GREEN)
        elif any(
            h.severity == ExclusionSeverity.CRITICAL
            for h in hits
        ):
            outcome = SustainabilityScreeningOutcome.EXCLUDED
        elif any(
            h.severity == ExclusionSeverity.HIGH
            for h in hits
        ):
            outcome = (
                SustainabilityScreeningOutcome.SENIOR_APPROVAL)
        elif any(
            h.severity == ExclusionSeverity.MEDIUM
            for h in hits
        ):
            outcome = (
                SustainabilityScreeningOutcome.REVIEW_NEEDED)
        else:
            outcome = (
                SustainabilityScreeningOutcome.REVIEW_NEEDED)

        return ExclusionScreeningResult(
            instrument_id=instrument.instrument_id,
            hits=tuple(hits),
            outcome=outcome,
            framework_refs=(
                "ENH-278 §screen_exclusion_list",
                "Caller-supplied exclusion list — typical sources "
                "include KBA SFI prohibited-sector list, bank "
                "internal policy, regulator-mandated exclusions",
                "Word-boundary regex (\\b) — same discipline as "
                "ENH-274 — substring matches shorter than 3 "
                "characters rejected",
                "Per Rule 7 — engine surfaces hits + outcome; "
                "operator decides whether to proceed; engine "
                "never blocks transactions",
            ),
        )

    # ─── 3. PCAF-aligned GHG attribution ────────────────────────
    def compute_ghg_attribution(
        self,
        instrument: TradeInstrument,
        sector_attribution: Mapping[str, str],
        emission_factors: Mapping[str, Decimal],
    ) -> GhgAttribution:
        """PCAF-aligned attributed financed emissions.

        sector_attribution maps applicant_id → sector_code.
        emission_factors maps sector_code → kg CO2e per KES financed.

        Returns ATTRIBUTED with computed emissions when both
        present; SECTOR_UNKNOWN or FACTOR_UNKNOWN otherwise (per
        Rule 1 — surface the gap rather than fabricate zero).
        """
        sector = sector_attribution.get(instrument.applicant)
        if sector is None:
            return GhgAttribution(
                instrument_id=instrument.instrument_id,
                sector=None,
                amount_kes=instrument.amount_kes,
                emission_factor_kgco2e_per_kes=None,
                attributed_emissions_kgco2e=None,
                status=GhgAttributionStatus.SECTOR_UNKNOWN,
                framework_refs=(
                    "ENH-278 §compute_ghg_attribution",
                    "PCAF (Partnership for Carbon Accounting "
                    "Financials) Global GHG Accounting & "
                    "Reporting Standard for Financed Emissions",
                    "Status: SECTOR_UNKNOWN — applicant not "
                    "in caller-supplied sector_attribution map",
                    "Per Rule 1 — surface gap rather than "
                    "fabricate zero emissions",
                ),
            )
        factor = emission_factors.get(sector)
        if factor is None:
            return GhgAttribution(
                instrument_id=instrument.instrument_id,
                sector=sector,
                amount_kes=instrument.amount_kes,
                emission_factor_kgco2e_per_kes=None,
                attributed_emissions_kgco2e=None,
                status=GhgAttributionStatus.FACTOR_UNKNOWN,
                framework_refs=(
                    "ENH-278 §compute_ghg_attribution",
                    "Status: FACTOR_UNKNOWN — sector "
                    f"'{sector}' has no entry in caller-"
                    "supplied emission_factors map",
                    "Per Rule 1 — surface gap; operator "
                    "supplies factor or accepts unattributed",
                ),
            )
        attributed = (
            instrument.amount_kes * factor
        ).quantize(Decimal("0.01"))
        return GhgAttribution(
            instrument_id=instrument.instrument_id,
            sector=sector,
            amount_kes=instrument.amount_kes,
            emission_factor_kgco2e_per_kes=factor,
            attributed_emissions_kgco2e=attributed,
            status=GhgAttributionStatus.ATTRIBUTED,
            framework_refs=(
                "ENH-278 §compute_ghg_attribution",
                "PCAF Global GHG Accounting & Reporting "
                "Standard — financed emissions methodology",
                "TCFD (Task Force on Climate-Related Financial "
                "Disclosures) — recommended disclosures",
                "Per Rule 7 — engine never sources emission "
                "factors (caller supplies per PCAF data hierarchy "
                "— Score 1 directly reported through Score 5 "
                "estimated proxies)",
            ),
        )

    # ─── 4. Counterparty ESG risk assessment ────────────────────
    def assess_counterparty_esg_risk(
        self,
        instrument: TradeInstrument,
        esg_attribution: Mapping[str, EsgRiskTier],
    ) -> EsgRiskAssessment:
        """Per-counterparty ESG risk lookup. Worst-of-pair is the
        more severe of applicant + beneficiary risks (UNRATED
        treated as least severe — surfaces gap rather than
        masking it as low risk)."""
        app_risk = esg_attribution.get(
            instrument.applicant, EsgRiskTier.UNRATED)
        ben_risk = esg_attribution.get(
            instrument.beneficiary, EsgRiskTier.UNRATED)
        worst = max(
            (app_risk, ben_risk),
            key=lambda t: self._ESG_RISK_ORDER[t])
        return EsgRiskAssessment(
            instrument_id=instrument.instrument_id,
            applicant_id=instrument.applicant,
            applicant_risk=app_risk,
            beneficiary_id=instrument.beneficiary,
            beneficiary_risk=ben_risk,
            worst_of_pair=worst,
            framework_refs=(
                "ENH-278 §assess_counterparty_esg_risk",
                "Caller-supplied ESG risk attribution — typical "
                "sources include MSCI ESG Ratings, Sustainalytics, "
                "ISS ESG, internal ESG screening output",
                "Worst-of-pair surfacing — applicant AND "
                "beneficiary risk both visible; engine does not "
                "smooth or average",
                "Per Rule 7 — engine looks up; never rates; "
                "never adjusts pricing on rating change",
            ),
        )

    # ─── 5. Portfolio sustainability report orchestrator ────────
    def build_sustainability_report(
        self,
        instruments: Sequence[TradeInstrument],
        as_of_date_iso: str,
        taxonomy: Sequence[TaxonomyEntry],
        exclusion_list: Sequence[ExclusionEntry],
        sector_attribution: Mapping[str, str],
        emission_factors: Mapping[str, Decimal],
        esg_attribution: Mapping[str, EsgRiskTier],
    ) -> SustainabilityReport:
        """Portfolio-level rollup across all 4 capabilities.

        Counts only active states (ISSUED / AMENDED / ACTIVE) —
        closed instruments excluded from current portfolio
        snapshot.
        """
        active_states = (
            InstrumentState.ISSUED,
            InstrumentState.AMENDED,
            InstrumentState.ACTIVE)
        active_insts = [
            i for i in instruments
            if i.state in active_states]

        total_notional = sum(
            (i.amount_kes for i in active_insts),
            Decimal("0"))

        by_tier_notional: Dict[str, Decimal] = {
            t.value: Decimal("0")
            for t in SustainabilityTier}
        for inst in active_insts:
            cls = self.classify_instrument_sustainability(
                inst, taxonomy)
            by_tier_notional[cls.primary_tier.value] += (
                inst.amount_kes)

        by_tier_share: Dict[str, Decimal] = {}
        if total_notional > 0:
            for tier_label, notional in by_tier_notional.items():
                by_tier_share[tier_label] = (
                    notional / total_notional
                ).quantize(Decimal("0.0001"))
        else:
            for tier_label in by_tier_notional:
                by_tier_share[tier_label] = Decimal("0")

        # GHG attribution rollup
        total_emissions = Decimal("0")
        unattributed = 0
        sector_emissions: Dict[str, Decimal] = {}
        for inst in active_insts:
            attr = self.compute_ghg_attribution(
                inst, sector_attribution, emission_factors)
            if attr.status == GhgAttributionStatus.ATTRIBUTED:
                total_emissions += (
                    attr.attributed_emissions_kgco2e)
                if attr.sector:
                    sector_emissions[attr.sector] = (
                        sector_emissions.get(
                            attr.sector, Decimal("0"))
                        + attr.attributed_emissions_kgco2e)
            else:
                unattributed += 1
        top_sectors = tuple(
            sorted(
                sector_emissions.items(),
                key=lambda kv: kv[1],
                reverse=True)[:5])

        # Exclusion screening rollup
        total_hits = 0
        critical_hits = 0
        for inst in active_insts:
            r = self.screen_exclusion_list(
                inst, exclusion_list)
            total_hits += len(r.hits)
            critical_hits += sum(
                1 for h in r.hits
                if h.severity == ExclusionSeverity.CRITICAL)

        # ESG risk rollup
        by_esg: Dict[str, int] = {
            t.value: 0 for t in EsgRiskTier}
        for inst in active_insts:
            risk = self.assess_counterparty_esg_risk(
                inst, esg_attribution)
            by_esg[risk.worst_of_pair.value] += 1

        return SustainabilityReport(
            as_of_date=as_of_date_iso,
            instrument_count=len(active_insts),
            total_notional_kes=total_notional,
            by_tier_share=by_tier_share,
            by_tier_notional_kes=by_tier_notional,
            total_attributed_emissions_kgco2e=(
                total_emissions.quantize(Decimal("0.01"))),
            unattributed_count=unattributed,
            top_emitting_sectors=top_sectors,
            exclusion_hit_count=total_hits,
            exclusion_critical_count=critical_hits,
            by_esg_tier_count=by_esg,
            framework_refs=(
                "ENH-278 §build_sustainability_report",
                "Active states only (ISSUED / AMENDED / ACTIVE) "
                "— closed instruments excluded from current "
                "portfolio snapshot",
                "PCAF + TCFD + KGFT + KBA SFI + EU Taxonomy + "
                "Equator Principles framework alignment",
                "Per Rule 1 — surfaces unattributed_count "
                "instead of zeroing missing emissions",
                "Per Rule 7 — report data only; cockpit page "
                "renders; operator interprets; no auto-action",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _make_inst(
    iid="LC-1", goods="solar panels and inverters",
    applicant="GreenCo", beneficiary="SunSupplier",
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
        description_of_goods=goods)


def _green_taxonomy() -> Tuple[TaxonomyEntry, ...]:
    """Sample caller-supplied taxonomy aligned with KGFT 2025."""
    return (
        TaxonomyEntry(
            keyword="solar",
            tier=SustainabilityTier.GREEN,
            source="KGFT 2025 §3.2 — renewable energy",
            justification="Solar PV qualifies under "
                          "renewable energy generation"),
        TaxonomyEntry(
            keyword="wind",
            tier=SustainabilityTier.GREEN,
            source="KGFT 2025 §3.2",
            justification="Wind generation"),
        TaxonomyEntry(
            keyword="natural gas",
            tier=SustainabilityTier.TRANSITION,
            source="EU Taxonomy — transitional activities",
            justification="Lower-carbon transition fuel"),
        TaxonomyEntry(
            keyword="thermal coal",
            tier=SustainabilityTier.BROWN,
            source="KBA SFI — phase-out commitment",
            justification="High-emissions; phase-out by 2030"),
        TaxonomyEntry(
            keyword="coal",
            tier=SustainabilityTier.BROWN,
            source="KGFT 2025 §4.1",
            justification="Coal generally misaligned"),
    )


def _exclusion_list() -> Tuple[ExclusionEntry, ...]:
    return (
        ExclusionEntry(
            keyword="thermal coal",
            severity=ExclusionSeverity.HIGH,
            source="KBA SFI 2024 §4.1 — coal phase-out",
            justification="Coal financing prohibited"),
        ExclusionEntry(
            keyword="weapons",
            severity=ExclusionSeverity.CRITICAL,
            source="Internal policy",
            justification="Absolute prohibition"),
        ExclusionEntry(
            keyword="tobacco",
            severity=ExclusionSeverity.MEDIUM,
            source="ESG screening policy",
            justification="Senior approval required"),
    )


# ─── Classification tests ──────────────────────────────────────

def _test_classify_green():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(
        goods="50 megawatt solar farm equipment")
    cls = eng.classify_instrument_sustainability(
        inst, _green_taxonomy())
    assert cls.primary_tier == SustainabilityTier.GREEN
    assert len(cls.all_matches) == 1
    assert cls.all_matches[0].keyword == "solar"
    assert cls.conflicting is False


def _test_classify_brown():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(
        goods="thermal coal shipment")
    cls = eng.classify_instrument_sustainability(
        inst, _green_taxonomy())
    # Both 'thermal coal' AND 'coal' match — both BROWN, no
    # conflict, primary BROWN
    assert cls.primary_tier == SustainabilityTier.BROWN
    assert cls.conflicting is False
    assert len(cls.all_matches) == 2


def _test_classify_transition():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(
        goods="natural gas turbine equipment")
    cls = eng.classify_instrument_sustainability(
        inst, _green_taxonomy())
    assert cls.primary_tier == SustainabilityTier.TRANSITION


def _test_classify_unclassified():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="bulk cement clinker")
    cls = eng.classify_instrument_sustainability(
        inst, _green_taxonomy())
    assert cls.primary_tier == SustainabilityTier.UNCLASSIFIED
    assert len(cls.all_matches) == 0


def _test_classify_conflicting_surfaces_worst():
    """Mixed signal: solar PV AND coal mentioned. Per Rule 1,
    ALL matches surfaced; primary_tier is most-conservative
    (BROWN, since BROWN > GREEN in conservatism order)."""
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(
        goods="solar panels and coal-fired backup boiler")
    cls = eng.classify_instrument_sustainability(
        inst, _green_taxonomy())
    assert cls.primary_tier == SustainabilityTier.BROWN
    assert cls.conflicting is True
    tiers = {m.tier for m in cls.all_matches}
    assert SustainabilityTier.GREEN in tiers
    assert SustainabilityTier.BROWN in tiers


def _test_classify_word_boundary_no_false_positive():
    """'oil' is NOT in the taxonomy here; substring 'soil' must
    not register a match for any keyword."""
    eng = TradeFinanceSustainabilityEngine()
    # Set up a taxonomy with 'oil' as BROWN
    taxonomy = (
        TaxonomyEntry(
            keyword="oil",
            tier=SustainabilityTier.BROWN,
            source="test",
            justification="x"),)
    # Goods description that contains 'soil' (substring) but
    # not 'oil' as a standalone word
    inst = _make_inst(goods="topsoil for agriculture")
    cls = eng.classify_instrument_sustainability(
        inst, taxonomy)
    # 'soil' must NOT match 'oil' due to word boundary
    assert cls.primary_tier == SustainabilityTier.UNCLASSIFIED


def _test_classify_keyword_too_short_rejected():
    try:
        TaxonomyEntry(
            keyword="oi",      # 2 chars, below floor
            tier=SustainabilityTier.GREEN,
            source="x", justification="x")
        assert False
    except ValueError:
        pass


def _test_classify_unclassified_tier_rejected():
    try:
        TaxonomyEntry(
            keyword="something",
            tier=SustainabilityTier.UNCLASSIFIED,
            source="x", justification="x")
        assert False
    except ValueError:
        pass


# ─── Exclusion screening tests ──────────────────────────────────

def _test_exclusion_clean():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="cement and aggregates")
    r = eng.screen_exclusion_list(inst, _exclusion_list())
    assert r.hits == ()
    assert r.outcome == (
        SustainabilityScreeningOutcome.ELIGIBLE_GREEN)


def _test_exclusion_critical_hit():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="weapons systems components")
    r = eng.screen_exclusion_list(inst, _exclusion_list())
    assert len(r.hits) == 1
    assert r.hits[0].severity == ExclusionSeverity.CRITICAL
    assert r.outcome == (
        SustainabilityScreeningOutcome.EXCLUDED)


def _test_exclusion_high_severity():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="thermal coal cargo")
    r = eng.screen_exclusion_list(inst, _exclusion_list())
    assert any(
        h.severity == ExclusionSeverity.HIGH for h in r.hits)
    assert r.outcome == (
        SustainabilityScreeningOutcome.SENIOR_APPROVAL)


def _test_exclusion_medium_severity():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="bulk tobacco leaves")
    r = eng.screen_exclusion_list(inst, _exclusion_list())
    assert any(
        h.severity == ExclusionSeverity.MEDIUM for h in r.hits)
    assert r.outcome == (
        SustainabilityScreeningOutcome.REVIEW_NEEDED)


# ─── GHG attribution tests ──────────────────────────────────────

def _test_ghg_attributed():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(
        applicant="EnergyCo",
        amount=Decimal("10000000"))
    sector_map = {"EnergyCo": "ENERGY"}
    factors = {"ENERGY": Decimal("0.2500")}    # kg CO2e per KES
    r = eng.compute_ghg_attribution(
        inst, sector_map, factors)
    assert r.status == GhgAttributionStatus.ATTRIBUTED
    # 10m KES × 0.25 = 2.5m kg CO2e
    assert r.attributed_emissions_kgco2e == Decimal(
        "2500000.00")


def _test_ghg_sector_unknown():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(applicant="UnknownCo")
    r = eng.compute_ghg_attribution(
        inst, {}, {})
    assert r.status == GhgAttributionStatus.SECTOR_UNKNOWN
    assert r.attributed_emissions_kgco2e is None


def _test_ghg_factor_unknown():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(applicant="A")
    r = eng.compute_ghg_attribution(
        inst, {"A": "OBSCURE_SECTOR"}, {})
    assert r.status == GhgAttributionStatus.FACTOR_UNKNOWN
    assert r.attributed_emissions_kgco2e is None
    assert r.sector == "OBSCURE_SECTOR"


# ─── ESG risk tests ─────────────────────────────────────────────

def _test_esg_risk_lookup():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(applicant="A", beneficiary="B")
    attribution = {
        "A": EsgRiskTier.MEDIUM,
        "B": EsgRiskTier.HIGH}
    r = eng.assess_counterparty_esg_risk(inst, attribution)
    assert r.applicant_risk == EsgRiskTier.MEDIUM
    assert r.beneficiary_risk == EsgRiskTier.HIGH
    # Worst of (MEDIUM, HIGH) is HIGH
    assert r.worst_of_pair == EsgRiskTier.HIGH


def _test_esg_risk_unrated():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(applicant="A", beneficiary="B")
    r = eng.assess_counterparty_esg_risk(inst, {})
    assert r.applicant_risk == EsgRiskTier.UNRATED
    assert r.beneficiary_risk == EsgRiskTier.UNRATED
    assert r.worst_of_pair == EsgRiskTier.UNRATED


# ─── Report orchestrator tests ──────────────────────────────────

def _test_report_mixed_portfolio():
    eng = TradeFinanceSustainabilityEngine()
    insts = (
        _make_inst(
            iid="L1", goods="solar farm equipment",
            applicant="GreenCo",
            amount=Decimal("5000000")),
        _make_inst(
            iid="L2", goods="thermal coal shipment",
            applicant="CoalCo",
            amount=Decimal("3000000")),
        _make_inst(
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
        "SunSupplier": EsgRiskTier.LOW}    # beneficiaries
    report = eng.build_sustainability_report(
        insts, as_of_date_iso="2026-04-15",
        taxonomy=_green_taxonomy(),
        exclusion_list=_exclusion_list(),
        sector_attribution=sector_map,
        emission_factors=factors,
        esg_attribution=esg)
    assert report.instrument_count == 3
    assert report.total_notional_kes == Decimal("10000000")
    # Tier shares: GREEN 5m / 10m = 0.5; BROWN 3m = 0.3;
    # UNCLASSIFIED 2m = 0.2 (cement has no taxonomy match)
    assert report.by_tier_share[
        SustainabilityTier.GREEN.value] == Decimal("0.5000")
    assert report.by_tier_share[
        SustainabilityTier.BROWN.value] == Decimal("0.3000")
    assert report.by_tier_share[
        SustainabilityTier.UNCLASSIFIED.value] == Decimal(
        "0.2000")
    # Total emissions: 5m × 0.05 + 3m × 0.50 + 2m × 0.20 =
    # 250k + 1.5m + 400k = 2.15m
    assert (
        report.total_attributed_emissions_kgco2e
        == Decimal("2150000.00"))
    assert report.unattributed_count == 0
    # Exclusion: thermal coal is HIGH (not CRITICAL)
    assert report.exclusion_hit_count >= 1
    assert report.exclusion_critical_count == 0


def _test_report_excludes_closed_instruments():
    eng = TradeFinanceSustainabilityEngine()
    from utils.trade_finance_instruments import (
        InstrumentState)
    insts = (
        _make_inst(
            iid="L1", goods="solar",
            state=InstrumentState.ACTIVE,
            amount=Decimal("1000000")),
        _make_inst(
            iid="L2", goods="solar",
            state=InstrumentState.EXPIRED,
            amount=Decimal("5000000")),
    )
    report = eng.build_sustainability_report(
        insts, as_of_date_iso="2026-04-15",
        taxonomy=_green_taxonomy(),
        exclusion_list=(),
        sector_attribution={},
        emission_factors={},
        esg_attribution={})
    # EXPIRED excluded
    assert report.instrument_count == 1
    assert report.total_notional_kes == Decimal("1000000")


def _test_report_empty_portfolio():
    eng = TradeFinanceSustainabilityEngine()
    report = eng.build_sustainability_report(
        (), as_of_date_iso="2026-04-15",
        taxonomy=(), exclusion_list=(),
        sector_attribution={}, emission_factors={},
        esg_attribution={})
    assert report.instrument_count == 0
    assert report.total_notional_kes == Decimal("0")
    assert (
        report.total_attributed_emissions_kgco2e
        == Decimal("0.00"))
    # All shares 0 with empty portfolio (no division by zero)
    for share in report.by_tier_share.values():
        assert share == Decimal("0")


# ─── Discipline tests ───────────────────────────────────────────

def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="solar panels")
    taxonomy = _green_taxonomy()
    exclusion = _exclusion_list()
    eng.classify_instrument_sustainability(inst, taxonomy)
    eng.screen_exclusion_list(inst, exclusion)
    eng.compute_ghg_attribution(inst, {}, {})
    eng.assess_counterparty_esg_risk(inst, {})
    # Inputs unchanged
    assert inst.amount_kes == Decimal("1000000")
    assert inst.description_of_goods == "solar panels"
    # Caller-supplied lists not mutated
    assert len(taxonomy) == 5
    assert len(exclusion) == 3


def _test_full_provenance():
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="solar")
    cls = eng.classify_instrument_sustainability(
        inst, _green_taxonomy())
    refs = " / ".join(cls.framework_refs)
    assert "ENH-278" in refs
    assert "KGFT" in refs
    assert "Rule 7" in refs
    assert "Rule 1" in refs


def _test_caller_supplied_data_discipline():
    """The engine must work with empty taxonomy / exclusion list
    (no bundled data); per Rule 7 + ENH-274 alignment."""
    eng = TradeFinanceSustainabilityEngine()
    inst = _make_inst(goods="anything goes here")
    # Empty taxonomy → UNCLASSIFIED, not crash
    cls = eng.classify_instrument_sustainability(inst, ())
    assert cls.primary_tier == SustainabilityTier.UNCLASSIFIED
    # Empty exclusion → eligible
    r = eng.screen_exclusion_list(inst, ())
    assert r.hits == ()
    assert r.outcome == (
        SustainabilityScreeningOutcome.ELIGIBLE_GREEN)


def self_test() -> None:
    tests = [
        _test_classify_green,
        _test_classify_brown,
        _test_classify_transition,
        _test_classify_unclassified,
        _test_classify_conflicting_surfaces_worst,
        _test_classify_word_boundary_no_false_positive,
        _test_classify_keyword_too_short_rejected,
        _test_classify_unclassified_tier_rejected,
        _test_exclusion_clean,
        _test_exclusion_critical_hit,
        _test_exclusion_high_severity,
        _test_exclusion_medium_severity,
        _test_ghg_attributed,
        _test_ghg_sector_unknown,
        _test_ghg_factor_unknown,
        _test_esg_risk_lookup,
        _test_esg_risk_unrated,
        _test_report_mixed_portfolio,
        _test_report_excludes_closed_instruments,
        _test_report_empty_portfolio,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_caller_supplied_data_discipline,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_sustainability self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_sustainability self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

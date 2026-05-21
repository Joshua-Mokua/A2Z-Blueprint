"""utils/esg_reporting_outputs.py — v10.9 Phase 2 deep impl batch 4.

╔════════════════════════════════════════════════════════════════════════╗
║  ESG REPORTING OUTPUTS — KGFT REPORTS + CRDF + GREENWASHING CONTROLS   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (deterministic disclosure assembly + verification)   ║
║  Implements 3 of 13 Climate/ESG standards from registry:                ║
║    ENH-CLI-03: Kenya Green Finance Taxonomy (KGFT) Report Generation    ║
║    ENH-CLI-04: Climate Risk Disclosure Framework (CRDF) Reporting       ║
║    ENH-CLI-13: Greenwashing Risk Controls + Claim Verification          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    KGFT  — Kenya Green Finance Taxonomy (CBK, April 2025)              ║
║    CRDF  — Climate Risk Disclosure Framework (CBK, April 2025)         ║
║    EU Taxonomy Regulation Art 8 — disclosure analogue                  ║
║    ESMA Guidelines on funds names using ESG-related terms              ║
║    ASA / AdStandards "green claims" guidance                           ║
║    ISO 14021 — Environmental claims labels (Type II)                   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with: utils/esg_intelligence.py (v10.6) for KGFT             ║
║                  utils/climate_risk.py (v10.7) for CRDF risk inputs    ║
║                  utils/climate_ecl_adjustment.py (v10.8) for stress    ║
║                  utils/esg_reporting.py (TCFD foundation)              ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28


# ════════════════════════════════════════════════════════════════════════
# KGFT Report constants
# ════════════════════════════════════════════════════════════════════════

KGFT_REPORT_SECTIONS: Tuple[str, ...] = (
    "GREEN_ASSET_INVENTORY",      # full list of classified assets
    "ALIGNMENT_BY_CATEGORY",       # category → balance breakdown
    "TRANSITIONING_PIPELINE",      # assets on credible transition path
    "DNSH_VERIFICATION",           # do-no-significant-harm evidence
    "EVIDENCE_ARTIFACTS",          # supporting docs/certifications
    "GOVERNANCE_AND_CONTROLS",     # how classification is reviewed
)

KGFT_MIN_REPORTING_FREQUENCY = "ANNUAL"
KGFT_DNSH_REQUIRED_FOR_ALIGNED = True


# ════════════════════════════════════════════════════════════════════════
# CRDF Report constants — CBK April 2025 Climate Risk Disclosure Framework
# ════════════════════════════════════════════════════════════════════════

# CRDF mirrors TCFD's 4 pillars but adds Kenya-specific requirements
CRDF_PILLARS: Tuple[str, ...] = (
    "GOVERNANCE",
    "STRATEGY",
    "RISK_MANAGEMENT",
    "METRICS_AND_TARGETS",
)

# CRDF disclosure requirements per pillar (subset for v10.9 scope)
CRDF_DISCLOSURES: Mapping[str, Tuple[str, ...]] = {
    "GOVERNANCE": (
        "BOARD_OVERSIGHT_DESCRIPTION",
        "MANAGEMENT_ROLE_DESCRIPTION",
        "BOARD_TRAINING_DISCLOSED",
    ),
    "STRATEGY": (
        "CLIMATE_RISKS_OPPORTUNITIES_IDENTIFIED",
        "BUSINESS_MODEL_IMPACT",
        "TRANSITION_PLAN_DESCRIBED",
        "SCENARIO_ANALYSIS_DISCLOSED",
    ),
    "RISK_MANAGEMENT": (
        "RISK_IDENTIFICATION_PROCESS",
        "RISK_INTEGRATION_INTO_ERMF",
        "MONITORING_AND_REPORTING",
    ),
    "METRICS_AND_TARGETS": (
        "SCOPE_1_DISCLOSED",
        "SCOPE_2_DISCLOSED",
        "SCOPE_3_DISCLOSED",
        "TRANSITION_TARGETS_QUANTITATIVE",
        "PHYSICAL_RISK_METRICS",
        "GREEN_BOOK_SHARE_DISCLOSED",
    ),
}

CRDF_REPORTING_FREQUENCY = "ANNUAL"
CRDF_FIRST_PERIOD = "2025-12-31"


# ════════════════════════════════════════════════════════════════════════
# Greenwashing controls
# ════════════════════════════════════════════════════════════════════════

GREENWASHING_RED_FLAGS: Tuple[str, ...] = (
    "VAGUE_LANGUAGE",                  # "eco-friendly", "natural" without specifics
    "UNSUBSTANTIATED_CLAIM",           # no evidence artifacts
    "NO_DNSH_ASSESSMENT",              # claimed green without DNSH
    "MISLEADING_CATEGORY_USE",         # KGFT category cited but unaligned
    "OUTDATED_EVIDENCE",               # certification expired or stale
    "PARTIAL_DISCLOSURE",              # benefits cited, harms omitted
    "CHERRY_PICKED_DATA",              # selective metrics
    "IRRELEVANT_CLAIMS",               # claims unrelated to actual asset
    "CLAIMS_INCONSISTENT_WITH_KGFT",   # claim contradicts classification
)

# Vague language tokens that trigger heuristic red flags
VAGUE_LANGUAGE_TOKENS: Tuple[str, ...] = (
    "eco-friendly", "eco friendly", "environmentally friendly",
    "green", "natural", "sustainable", "clean", "responsible",
    "earth-friendly", "earth friendly", "100% green", "fully green",
    "carbon neutral",
)


class GreenwashingRiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class KGFTReport:
    """KGFT-aligned green book report per CBK April 2025."""
    period_start: str
    period_end: str
    entity_name: str
    total_assets_assessed: int
    aligned_count: int
    transitioning_count: int
    enabling_count: int
    non_aligned_count: int
    aligned_balance_kes: Decimal
    transitioning_balance_kes: Decimal
    total_book_kes: Decimal
    aligned_share_pct: Decimal
    transitioning_share_pct: Decimal
    by_category: Mapping[str, Decimal]   # KGFT category → balance KES
    dnsh_verified_count: int
    sections: Mapping[str, str]
    methodology_notes: str = ""

    def green_book_total_pct(self) -> Decimal:
        """Aligned + transitioning + enabling combined share."""
        if self.total_book_kes == Decimal("0"):
            return Decimal("0")
        return ((self.aligned_balance_kes + self.transitioning_balance_kes)
                / self.total_book_kes * Decimal("100"))


@dataclass(frozen=True)
class CRDFReport:
    """CBK CRDF annual climate risk disclosure report."""
    period_start: str
    period_end: str
    entity_name: str
    pillars: Mapping[str, Mapping[str, str]]   # pillar → {disclosure_id: text}
    completeness_pct: Decimal
    missing_disclosures: Tuple[str, ...]
    submission_date: str
    notes: str = ""

    def is_complete(self) -> bool:
        return self.completeness_pct >= Decimal("100")


@dataclass(frozen=True)
class GreenwashingClaim:
    """A green claim made about an asset, product, or report."""
    claim_id: str
    claim_text: str
    category_referenced: Optional[str] = None    # KGFT category
    asset_id: Optional[str] = None
    dnsh_evidence_present: bool = False
    evidence_artifacts: Tuple[str, ...] = ()
    issued_date: str = ""
    notes: str = ""


@dataclass(frozen=True)
class GreenwashingVerificationResult:
    """Result of verifying a green claim."""
    claim_id: str
    risk_level: str               # GreenwashingRiskLevel value
    red_flags: Tuple[str, ...]    # subset of GREENWASHING_RED_FLAGS
    supported_by_kgft: bool
    referenced_classification_aligned: Optional[bool]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# KGFT report generation
# ════════════════════════════════════════════════════════════════════════

def generate_kgft_report(
    *,
    period_start: str,
    period_end: str,
    entity_name: str,
    classifications: Sequence,         # GreenAssetClassification from v10.6
    asset_balances: Mapping[str, Decimal],
    governance_notes: str = "",
) -> KGFTReport:
    """Generate KGFT-aligned report for the given period.

    Parameters
    ----------
    classifications : sequence of GreenAssetClassification (from utils.esg_intelligence)
    asset_balances : asset_id → outstanding KES balance

    Returns
    -------
    KGFTReport with all 6 sections populated.
    """
    n_total = len(classifications)
    n_aligned = sum(
        1 for c in classifications if c.alignment_level == "ALIGNED")
    n_transitioning = sum(
        1 for c in classifications if c.alignment_level == "TRANSITIONING")
    n_enabling = sum(
        1 for c in classifications if c.alignment_level == "ENABLING")
    n_non_aligned = sum(
        1 for c in classifications if c.alignment_level == "NON_ALIGNED")
    n_dnsh = sum(1 for c in classifications if c.dnsh_assessed)

    aligned_balance = sum(
        (asset_balances.get(c.asset_id, Decimal("0"))
          for c in classifications if c.alignment_level == "ALIGNED"),
        Decimal("0"))
    transitioning_balance = sum(
        (asset_balances.get(c.asset_id, Decimal("0"))
          for c in classifications if c.alignment_level == "TRANSITIONING"),
        Decimal("0"))
    total_book = sum(asset_balances.values(), Decimal("0"))

    aligned_pct = (
        aligned_balance / total_book * Decimal("100")
        if total_book > Decimal("0") else Decimal("0"))
    transitioning_pct = (
        transitioning_balance / total_book * Decimal("100")
        if total_book > Decimal("0") else Decimal("0"))

    # Group by KGFT category
    by_category: Dict[str, Decimal] = {}
    for c in classifications:
        if c.kgft_category and c.alignment_level == "ALIGNED":
            by_category[c.kgft_category] = (
                by_category.get(c.kgft_category, Decimal("0"))
                + asset_balances.get(c.asset_id, Decimal("0")))

    # Build narrative sections
    sections = {
        "GREEN_ASSET_INVENTORY": (
            f"Inventory of {n_total} assets classified against the "
            f"Kenya Green Finance Taxonomy. Of these, {n_aligned} are "
            f"ALIGNED, {n_transitioning} TRANSITIONING, "
            f"{n_enabling} ENABLING, {n_non_aligned} NON_ALIGNED."),
        "ALIGNMENT_BY_CATEGORY": (
            f"Aligned assets distributed across {len(by_category)} KGFT "
            f"categories: {', '.join(sorted(by_category.keys()))}."
            if by_category else "No aligned assets in this period."),
        "TRANSITIONING_PIPELINE": (
            f"{n_transitioning} assets on credible transition pathways "
            f"(carrying balance KES {transitioning_balance})."),
        "DNSH_VERIFICATION": (
            f"DNSH (Do No Significant Harm) verified on {n_dnsh} of "
            f"{n_total} assets ({_pct(n_dnsh, n_total)}%)."),
        "EVIDENCE_ARTIFACTS": (
            f"Evidence artifacts captured for "
            f"{sum(1 for c in classifications if c.evidence_artifacts)} "
            f"assets."),
        "GOVERNANCE_AND_CONTROLS": (
            governance_notes
            or "Classification reviewed by ESG Reporting Lead and "
            "approved by Climate Risk Officer per CBK CRMF Pillar 1."),
    }

    return KGFTReport(
        period_start=period_start,
        period_end=period_end,
        entity_name=entity_name,
        total_assets_assessed=n_total,
        aligned_count=n_aligned,
        transitioning_count=n_transitioning,
        enabling_count=n_enabling,
        non_aligned_count=n_non_aligned,
        aligned_balance_kes=aligned_balance,
        transitioning_balance_kes=transitioning_balance,
        total_book_kes=total_book,
        aligned_share_pct=aligned_pct,
        transitioning_share_pct=transitioning_pct,
        by_category=by_category,
        dnsh_verified_count=n_dnsh,
        sections=sections,
        methodology_notes="Per CBK KGFT April 2025 + EU Taxonomy Article 8 analogue.")


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0"
    return str(int(n / total * 100))


# ════════════════════════════════════════════════════════════════════════
# CRDF report generation
# ════════════════════════════════════════════════════════════════════════

def generate_crdf_report(
    *,
    period_start: str,
    period_end: str,
    entity_name: str,
    disclosures: Mapping[str, Mapping[str, str]],
    submission_date: str,
) -> CRDFReport:
    """Generate CBK CRDF annual report.

    disclosures: pillar → {disclosure_id: narrative_text}.
    Pillars must be subset of CRDF_PILLARS; disclosure_ids must be subset
    of CRDF_DISCLOSURES[pillar]. Missing items surface in missing_disclosures.
    """
    # Validate pillar names
    invalid_pillars = [p for p in disclosures if p not in CRDF_PILLARS]
    if invalid_pillars:
        raise ValueError(
            f"unknown CRDF pillar(s): {invalid_pillars}; "
            f"valid: {CRDF_PILLARS}")

    # Validate disclosure IDs per pillar; collect missing
    pillars_clean: Dict[str, Dict[str, str]] = {}
    missing: List[str] = []
    total_required = 0
    total_present = 0

    for pillar in CRDF_PILLARS:
        required = CRDF_DISCLOSURES[pillar]
        total_required += len(required)
        provided = disclosures.get(pillar, {})

        # Validate IDs
        invalid = [d for d in provided if d not in required]
        if invalid:
            raise ValueError(
                f"unknown CRDF disclosure(s) in pillar {pillar}: "
                f"{invalid}; valid: {required}")

        kept: Dict[str, str] = {}
        for d in required:
            if d in provided and provided[d].strip():
                kept[d] = provided[d]
                total_present += 1
            else:
                missing.append(f"{pillar}/{d}")
        pillars_clean[pillar] = kept

    completeness_pct = (
        Decimal(total_present) / Decimal(total_required) * Decimal("100")
        if total_required > 0 else Decimal("0"))

    return CRDFReport(
        period_start=period_start,
        period_end=period_end,
        entity_name=entity_name,
        pillars=pillars_clean,
        completeness_pct=completeness_pct,
        missing_disclosures=tuple(missing),
        submission_date=submission_date,
        notes=(
            f"Per CBK CRDF April 2025 — {total_required} required "
            f"disclosures across {len(CRDF_PILLARS)} pillars."))


# ════════════════════════════════════════════════════════════════════════
# Greenwashing claim verification
# ════════════════════════════════════════════════════════════════════════

def verify_green_claim(
    claim: GreenwashingClaim,
    *,
    kgft_classifications: Mapping = None,   # asset_id → GreenAssetClassification
) -> GreenwashingVerificationResult:
    """Verify a green claim against KGFT classification + heuristics.

    Heuristic red flags applied:
      - Vague language tokens
      - Missing evidence artifacts
      - Missing DNSH evidence
      - Category referenced doesn't match underlying classification
      - Inconsistency with KGFT classification (claimed green, not aligned)
    """
    flags: List[str] = []
    classifications = kgft_classifications or {}

    text_lower = claim.claim_text.lower()
    if any(t in text_lower for t in VAGUE_LANGUAGE_TOKENS):
        # Vague, but acceptable if backed by evidence + DNSH
        if not (claim.evidence_artifacts and claim.dnsh_evidence_present):
            flags.append("VAGUE_LANGUAGE")

    if not claim.evidence_artifacts:
        flags.append("UNSUBSTANTIATED_CLAIM")

    if not claim.dnsh_evidence_present and claim.category_referenced:
        flags.append("NO_DNSH_ASSESSMENT")

    # Cross-check against KGFT classification (if provided)
    referenced_aligned: Optional[bool] = None
    supported_by_kgft = False
    if claim.asset_id and claim.asset_id in classifications:
        c = classifications[claim.asset_id]
        referenced_aligned = (c.alignment_level == "ALIGNED")
        if claim.category_referenced and c.kgft_category != claim.category_referenced:
            flags.append("MISLEADING_CATEGORY_USE")
        if c.alignment_level not in ("ALIGNED", "TRANSITIONING", "ENABLING"):
            flags.append("CLAIMS_INCONSISTENT_WITH_KGFT")
        else:
            supported_by_kgft = True

    # Risk level cascade
    if len(flags) >= 3 or "CLAIMS_INCONSISTENT_WITH_KGFT" in flags:
        risk_level = GreenwashingRiskLevel.HIGH.value
    elif len(flags) >= 1:
        risk_level = GreenwashingRiskLevel.MEDIUM.value
    else:
        risk_level = GreenwashingRiskLevel.LOW.value

    return GreenwashingVerificationResult(
        claim_id=claim.claim_id,
        risk_level=risk_level,
        red_flags=tuple(flags),
        supported_by_kgft=supported_by_kgft,
        referenced_classification_aligned=referenced_aligned,
        notes=(
            f"flags={len(flags)}; "
            f"kgft_lookup={'yes' if claim.asset_id in classifications else 'no'}"))


def aggregate_greenwashing_risk(
    verifications: Sequence[GreenwashingVerificationResult],
) -> Dict[str, object]:
    """Portfolio-level greenwashing risk summary."""
    if not verifications:
        return {
            "n_verified": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "high_risk_pct": Decimal("0"),
            "common_red_flags": (),
        }

    n = len(verifications)
    high = sum(1 for v in verifications if v.risk_level == "HIGH")
    medium = sum(1 for v in verifications if v.risk_level == "MEDIUM")
    low = sum(1 for v in verifications if v.risk_level == "LOW")

    # Top red flags (frequency-sorted)
    flag_counts: Dict[str, int] = {}
    for v in verifications:
        for f in v.red_flags:
            flag_counts[f] = flag_counts.get(f, 0) + 1
    common = tuple(
        f"{f}:{c}"
        for f, c in sorted(flag_counts.items(),
                            key=lambda kv: kv[1],
                            reverse=True)[:5])

    return {
        "n_verified": n,
        "high_risk_count": high,
        "medium_risk_count": medium,
        "low_risk_count": low,
        "high_risk_pct": Decimal(high) / Decimal(n) * Decimal("100"),
        "common_red_flags": common,
    }


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class ESGReportingOutputsEngine:
    """Orchestrator for KGFT, CRDF, and greenwashing reporting outputs."""

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._classifications: List = []      # GreenAssetClassification
        self._asset_balances: Dict[str, Decimal] = {}
        self._claims: List[GreenwashingClaim] = []
        self._kgft_reports: List[KGFTReport] = []
        self._crdf_reports: List[CRDFReport] = []
        self._verifications: List[GreenwashingVerificationResult] = []

    def add_classification(self, c) -> None:
        self._classifications.append(c)
        # Keep a quick-lookup index
        self._classifications_by_id = {
            x.asset_id: x for x in self._classifications}

    def set_asset_balance(self, asset_id: str, balance_kes: Decimal) -> None:
        self._asset_balances[asset_id] = balance_kes

    def add_claim(self, claim: GreenwashingClaim) -> None:
        self._claims.append(claim)

    def generate_kgft(
        self,
        *,
        period_start: str,
        period_end: str,
        governance_notes: str = "",
    ) -> KGFTReport:
        report = generate_kgft_report(
            period_start=period_start,
            period_end=period_end,
            entity_name=self.entity_name,
            classifications=self._classifications,
            asset_balances=self._asset_balances,
            governance_notes=governance_notes)
        self._kgft_reports.append(report)
        return report

    def generate_crdf(
        self,
        *,
        period_start: str,
        period_end: str,
        disclosures: Mapping[str, Mapping[str, str]],
        submission_date: str,
    ) -> CRDFReport:
        report = generate_crdf_report(
            period_start=period_start,
            period_end=period_end,
            entity_name=self.entity_name,
            disclosures=disclosures,
            submission_date=submission_date)
        self._crdf_reports.append(report)
        return report

    def verify_all_claims(self) -> List[GreenwashingVerificationResult]:
        idx = {c.asset_id: c for c in self._classifications}
        results = [
            verify_green_claim(claim, kgft_classifications=idx)
            for claim in self._claims]
        self._verifications = results
        return results

    def board_summary(self) -> Dict[str, object]:
        kgft_latest = self._kgft_reports[-1] if self._kgft_reports else None
        crdf_latest = self._crdf_reports[-1] if self._crdf_reports else None
        gw_summary = aggregate_greenwashing_risk(self._verifications)

        return {
            "entity": self.entity_name,
            "kgft_aligned_share_pct": (
                kgft_latest.aligned_share_pct if kgft_latest else None),
            "kgft_aligned_balance_kes": (
                kgft_latest.aligned_balance_kes if kgft_latest else None),
            "crdf_completeness_pct": (
                crdf_latest.completeness_pct if crdf_latest else None),
            "crdf_complete": (
                crdf_latest.is_complete() if crdf_latest else None),
            "greenwashing_high_risk_count": (
                gw_summary["high_risk_count"]),
            "greenwashing_high_risk_pct": (
                gw_summary["high_risk_pct"]),
            "n_claims_verified": gw_summary["n_verified"],
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_classification(asset_id, level="ALIGNED", category="RENEWABLE_ENERGY",
                          dnsh=True, dims=("CLIMATE_MITIGATION",),
                          evidence=("EDGE-cert",)):
    """Helper that creates a v10.6 GreenAssetClassification."""
    from utils.esg_intelligence import GreenAssetClassification
    return GreenAssetClassification(
        asset_id=asset_id, kgft_category=category,
        alignment_level=level,
        eligibility_dimensions=dims,
        dnsh_assessed=dnsh,
        evidence_artifacts=evidence)


def _test_kgft_report_basic():
    """Basic KGFT report generates with correct counts."""
    cs = [
        _make_classification("L-1", "ALIGNED"),
        _make_classification("L-2", "ALIGNED", category="GREEN_BUILDINGS"),
        _make_classification("L-3", "TRANSITIONING", category="ENERGY_EFFICIENCY",
                              dnsh=False, dims=()),
        _make_classification("L-4", "NON_ALIGNED", category="",
                              dnsh=False, dims=()),
    ]
    balances = {
        "L-1": Decimal("1000000"), "L-2": Decimal("500000"),
        "L-3": Decimal("300000"), "L-4": Decimal("200000")}
    r = generate_kgft_report(
        period_start="2025-01-01", period_end="2025-12-31",
        entity_name="Test", classifications=cs,
        asset_balances=balances)
    assert r.aligned_count == 2
    assert r.transitioning_count == 1
    assert r.non_aligned_count == 1
    assert r.aligned_balance_kes == Decimal("1500000")
    assert r.total_book_kes == Decimal("2000000")
    assert r.aligned_share_pct == Decimal("75")
    assert "RENEWABLE_ENERGY" in r.by_category
    assert "GREEN_BUILDINGS" in r.by_category


def _test_kgft_report_empty():
    """Empty input yields zero report — no errors."""
    r = generate_kgft_report(
        period_start="2025-01-01", period_end="2025-12-31",
        entity_name="Test", classifications=[], asset_balances={})
    assert r.total_assets_assessed == 0
    assert r.aligned_share_pct == Decimal("0")


def _test_kgft_report_sections_present():
    cs = [_make_classification("L-1", "ALIGNED")]
    r = generate_kgft_report(
        period_start="2025-01-01", period_end="2025-12-31",
        entity_name="Test", classifications=cs,
        asset_balances={"L-1": Decimal("100")})
    for section in KGFT_REPORT_SECTIONS:
        assert section in r.sections


def _test_crdf_report_full():
    """Full CRDF report → 100% complete."""
    full_disclosures = {
        pillar: {d: f"{d} text" for d in CRDF_DISCLOSURES[pillar]}
        for pillar in CRDF_PILLARS}
    r = generate_crdf_report(
        period_start="2025-01-01", period_end="2025-12-31",
        entity_name="Test", disclosures=full_disclosures,
        submission_date="2026-03-01")
    assert r.completeness_pct == Decimal("100")
    assert r.is_complete()
    assert r.missing_disclosures == ()


def _test_crdf_report_partial():
    """Missing disclosures surface in missing_disclosures."""
    partial = {
        "GOVERNANCE": {
            "BOARD_OVERSIGHT_DESCRIPTION": "Board chairs ESG committee."
        },
    }
    r = generate_crdf_report(
        period_start="2025-01-01", period_end="2025-12-31",
        entity_name="Test", disclosures=partial,
        submission_date="2026-03-01")
    assert r.completeness_pct < Decimal("100")
    assert not r.is_complete()
    # 1 of 16 = 6.25%
    total = sum(len(d) for d in CRDF_DISCLOSURES.values())
    expected_pct = Decimal("1") / Decimal(total) * Decimal("100")
    assert r.completeness_pct == expected_pct


def _test_crdf_invalid_pillar_raises():
    try:
        generate_crdf_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="T", disclosures={"BAD_PILLAR": {}},
            submission_date="2026-03-01")
        assert False
    except ValueError as e:
        assert "pillar" in str(e).lower()


def _test_crdf_invalid_disclosure_raises():
    try:
        generate_crdf_report(
            period_start="2025-01-01", period_end="2025-12-31",
            entity_name="T",
            disclosures={"GOVERNANCE": {"FAKE_DISCLOSURE": "x"}},
            submission_date="2026-03-01")
        assert False
    except ValueError as e:
        assert "disclosure" in str(e).lower()


def _test_greenwashing_clean_claim():
    """Well-supported claim → LOW risk."""
    claim = GreenwashingClaim(
        claim_id="C-1",
        claim_text="This loan finances a 50MW solar PV plant per KGFT.",
        category_referenced="RENEWABLE_ENERGY",
        asset_id="L-SOLAR",
        dnsh_evidence_present=True,
        evidence_artifacts=("EDGE-cert", "EIA-2024"))
    cls = {"L-SOLAR": _make_classification(
        "L-SOLAR", "ALIGNED", "RENEWABLE_ENERGY")}
    r = verify_green_claim(claim, kgft_classifications=cls)
    assert r.risk_level == "LOW"
    assert r.supported_by_kgft is True


def _test_greenwashing_vague_no_evidence():
    """Vague language + no evidence → MEDIUM/HIGH risk."""
    claim = GreenwashingClaim(
        claim_id="C-2",
        claim_text="Eco-friendly investment.",
        evidence_artifacts=())
    r = verify_green_claim(claim)
    assert r.risk_level in ("MEDIUM", "HIGH")
    assert "VAGUE_LANGUAGE" in r.red_flags or "UNSUBSTANTIATED_CLAIM" in r.red_flags


def _test_greenwashing_inconsistent_with_kgft():
    """Claim cites green but classification says NON_ALIGNED → HIGH risk."""
    claim = GreenwashingClaim(
        claim_id="C-3",
        claim_text="Sustainable financing for our coal expansion project.",
        category_referenced="RENEWABLE_ENERGY",
        asset_id="L-COAL-1",
        dnsh_evidence_present=False,
        evidence_artifacts=("press-release",))
    cls = {"L-COAL-1": _make_classification(
        "L-COAL-1", "NON_ALIGNED", "", dnsh=False, dims=())}
    r = verify_green_claim(claim, kgft_classifications=cls)
    assert r.risk_level == "HIGH"
    assert "CLAIMS_INCONSISTENT_WITH_KGFT" in r.red_flags


def _test_greenwashing_misleading_category():
    """Claim cites wrong KGFT category vs actual classification."""
    claim = GreenwashingClaim(
        claim_id="C-4",
        claim_text="Renewable energy financing.",
        category_referenced="RENEWABLE_ENERGY",
        asset_id="L-1",
        dnsh_evidence_present=True,
        evidence_artifacts=("doc",))
    cls = {"L-1": _make_classification(
        "L-1", "ALIGNED", "GREEN_BUILDINGS")}
    r = verify_green_claim(claim, kgft_classifications=cls)
    assert "MISLEADING_CATEGORY_USE" in r.red_flags


def _test_aggregate_greenwashing_summary():
    """Aggregate counts and frequency-sorts top red flags."""
    vs = [
        GreenwashingVerificationResult(
            claim_id="C1", risk_level="HIGH",
            red_flags=("VAGUE_LANGUAGE", "UNSUBSTANTIATED_CLAIM"),
            supported_by_kgft=False,
            referenced_classification_aligned=None),
        GreenwashingVerificationResult(
            claim_id="C2", risk_level="HIGH",
            red_flags=("VAGUE_LANGUAGE",),
            supported_by_kgft=False,
            referenced_classification_aligned=None),
        GreenwashingVerificationResult(
            claim_id="C3", risk_level="LOW",
            red_flags=(), supported_by_kgft=True,
            referenced_classification_aligned=True),
    ]
    s = aggregate_greenwashing_risk(vs)
    assert s["n_verified"] == 3
    assert s["high_risk_count"] == 2
    assert s["low_risk_count"] == 1
    assert s["common_red_flags"][0].startswith("VAGUE_LANGUAGE:")


def _test_aggregate_empty():
    s = aggregate_greenwashing_risk(())
    assert s["n_verified"] == 0
    assert s["high_risk_count"] == 0


def _test_engine_orchestration():
    """Engine ties KGFT + CRDF + greenwashing together."""
    eng = ESGReportingOutputsEngine(entity_name="Test Bank")
    eng.add_classification(_make_classification("L-1", "ALIGNED"))
    eng.set_asset_balance("L-1", Decimal("1000000"))
    eng.add_claim(GreenwashingClaim(
        claim_id="C-1",
        claim_text="Renewable energy project.",
        category_referenced="RENEWABLE_ENERGY",
        asset_id="L-1",
        dnsh_evidence_present=True,
        evidence_artifacts=("cert",)))

    kgft = eng.generate_kgft(
        period_start="2025-01-01", period_end="2025-12-31")
    full_disclosures = {
        pillar: {d: f"{d} text" for d in CRDF_DISCLOSURES[pillar]}
        for pillar in CRDF_PILLARS}
    crdf = eng.generate_crdf(
        period_start="2025-01-01", period_end="2025-12-31",
        disclosures=full_disclosures, submission_date="2026-03-01")
    verifs = eng.verify_all_claims()

    summary = eng.board_summary()
    assert summary["kgft_aligned_share_pct"] == Decimal("100")
    assert summary["crdf_complete"] is True
    assert summary["n_claims_verified"] == 1


def _test_decimal_purity():
    cs = [_make_classification("L-1", "ALIGNED")]
    r = generate_kgft_report(
        period_start="2025-01-01", period_end="2025-12-31",
        entity_name="Test", classifications=cs,
        asset_balances={"L-1": Decimal("100")})
    assert isinstance(r.aligned_share_pct, Decimal)
    assert isinstance(r.aligned_balance_kes, Decimal)
    assert isinstance(r.total_book_kes, Decimal)


def self_test() -> None:
    tests = [
        _test_kgft_report_basic,
        _test_kgft_report_empty,
        _test_kgft_report_sections_present,
        _test_crdf_report_full,
        _test_crdf_report_partial,
        _test_crdf_invalid_pillar_raises,
        _test_crdf_invalid_disclosure_raises,
        _test_greenwashing_clean_claim,
        _test_greenwashing_vague_no_evidence,
        _test_greenwashing_inconsistent_with_kgft,
        _test_greenwashing_misleading_category,
        _test_aggregate_greenwashing_summary,
        _test_aggregate_empty,
        _test_engine_orchestration,
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
        print(f"✗ esg_reporting_outputs self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ esg_reporting_outputs self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    # Allow running directly from project root or as `python -m utils.esg_reporting_outputs`
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(_here)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    self_test()

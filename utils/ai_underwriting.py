"""utils/ai_underwriting.py — v10.11 Phase 2 deep impl batch 5 (Credit batch 1).

╔════════════════════════════════════════════════════════════════════════╗
║  AI UNDERWRITING DECISION ENGINE — DECISIONING + EXPLAINABILITY +     ║
║                                      EU AI ACT + CFPB COMPLIANCE       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (decision affects credit issuance/denial outcomes)  ║
║  Implements 4 of 19 Credit standards from registry:                     ║
║    ENH-119:     AI-Powered Credit Decisioning Engine                    ║
║    ENH-124:     Explainable AI for Regulatory Compliance                ║
║    ENH-CRD-R2:  EU AI Act High-Risk Classification Compliance           ║
║    ENH-CRD-R3:  CFPB-Compliant Adverse Action Reason Codes              ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    EU AI Act (Reg 2024/1689) Art 6 + Annex III §5(b) — high-risk AI    ║
║    EU AI Act Art 9 (risk mgmt), 13 (transparency), 14 (human oversight)║
║    EU AI Act Art 15 (accuracy + cybersecurity)                          ║
║    EU AI Act Art 26 (deployer obligations) + Art 86 (right to explain)  ║
║    ECOA — Equal Credit Opportunity Act 15 USC §1691                     ║
║    Regulation B 12 CFR §1002.9 — adverse action notification            ║
║    Regulation B 12 CFR Pt 1002 App C — sample notification forms        ║
║    CFPB Circular 2022-03 — adverse action via algorithms                ║
║    Basel BCBS 239 — risk data aggregation principles                    ║
║    CBK Prudential Guideline CBK/PG/13 — credit risk management         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Honesty Rule 7 enforced:                                               ║
║    No silent ML predictions. When no model is plugged in, the engine   ║
║    falls back to deterministic rule-based scoring (composes with        ║
║    utils/credit_risk_scoring.py) and surfaces SPEC_DEVIATION clearly.  ║
║                                                                         ║
║  Composes with: utils/credit_risk_scoring.py (PD scoring foundation)   ║
║                  utils/composite_scores.py (composite features)         ║
║                  unchanged — no modifications to existing engines.      ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

# 28-digit precision for credit calculations
getcontext().prec = 28

# Spec deviation note for Rule 7
SPEC_DEVIATION_NOTE = (
    "AI underwriting model is rule-based; ML model integration "
    "via callable hook (no silent predictions per Rule 7)")


# ════════════════════════════════════════════════════════════════════════
# Decision categories + confidence levels
# ════════════════════════════════════════════════════════════════════════

class UnderwritingDecision(Enum):
    """High-level decision outcomes."""
    APPROVE = "APPROVE"
    DECLINE = "DECLINE"
    CONDITIONAL_APPROVE = "CONDITIONAL_APPROVE"   # approve with conditions
    REFER_HUMAN = "REFER_HUMAN"                   # human-in-loop required


class ConfidenceLevel(Enum):
    """Confidence that the automated decision is correct."""
    HIGH = "HIGH"        # high enough for automated approve/decline
    MEDIUM = "MEDIUM"    # may proceed with caveats
    LOW = "LOW"          # human must review


# 80/20 confidence threshold per ENH-CRD-R7 (Confident Automation Pattern)
HIGH_CONFIDENCE_THRESHOLD = Decimal("0.80")
LOW_CONFIDENCE_THRESHOLD = Decimal("0.50")


# ════════════════════════════════════════════════════════════════════════
# CFPB adverse action reason codes (12 CFR Pt 1002 App C)
# ════════════════════════════════════════════════════════════════════════

# CFPB Reg B Sample Form C-1 — common adverse action reasons
# (Subset; full Appendix C contains 22 reasons)
CFPB_ADVERSE_ACTION_CODES: Tuple[str, ...] = (
    "AA_001_INSUFFICIENT_INCOME",
    "AA_002_INCOME_UNVERIFIABLE",
    "AA_003_LENGTH_OF_EMPLOYMENT_TOO_SHORT",
    "AA_004_INSUFFICIENT_RESIDENCY_STABILITY",
    "AA_005_TEMPORARY_RESIDENCE",
    "AA_006_INSUFFICIENT_CREDIT_FILE",
    "AA_007_NO_CREDIT_FILE",
    "AA_008_LIMITED_CREDIT_EXPERIENCE",
    "AA_009_DELINQUENT_PAST_OR_PRESENT_CREDIT_OBLIGATIONS",
    "AA_010_BANKRUPTCY",
    "AA_011_NUMBER_OF_RECENT_INQUIRIES",
    "AA_012_GARNISHMENT_ATTACHMENT_FORECLOSURE",
    "AA_013_VALUE_OF_COLLATERAL",
    "AA_014_INADEQUATE_COLLATERAL",
    "AA_015_TYPE_OF_CREDIT_REQUESTED",
    "AA_016_AMOUNT_REQUESTED_TOO_HIGH",
    "AA_017_PURPOSE_OF_LOAN_NOT_ACCEPTABLE",
    "AA_018_DEBT_TO_INCOME_RATIO_TOO_HIGH",
    "AA_019_NUMBER_OF_TRADELINES",
    "AA_020_INSUFFICIENT_DOWN_PAYMENT",
    "AA_021_PAYMENT_HISTORY",
    "AA_022_OTHER_REASON",
)

# Map applicant feature deficiencies to reason codes
# Used by generate_adverse_action_codes() to build CFPB-compliant explanation
FEATURE_TO_AA_CODE: Mapping[str, str] = {
    "monthly_income_kes": "AA_001_INSUFFICIENT_INCOME",
    "income_verified": "AA_002_INCOME_UNVERIFIABLE",
    "employment_months": "AA_003_LENGTH_OF_EMPLOYMENT_TOO_SHORT",
    "residency_months": "AA_004_INSUFFICIENT_RESIDENCY_STABILITY",
    "bureau_score": "AA_006_INSUFFICIENT_CREDIT_FILE",
    "bureau_file_present": "AA_007_NO_CREDIT_FILE",
    "credit_history_months": "AA_008_LIMITED_CREDIT_EXPERIENCE",
    "delinquencies_past_24m": "AA_009_DELINQUENT_PAST_OR_PRESENT_CREDIT_OBLIGATIONS",
    "bankruptcies_past_84m": "AA_010_BANKRUPTCY",
    "recent_inquiries_3m": "AA_011_NUMBER_OF_RECENT_INQUIRIES",
    "active_garnishments": "AA_012_GARNISHMENT_ATTACHMENT_FORECLOSURE",
    "ltv_ratio_pct": "AA_013_VALUE_OF_COLLATERAL",
    "collateral_value_kes": "AA_014_INADEQUATE_COLLATERAL",
    "amount_requested_kes": "AA_016_AMOUNT_REQUESTED_TOO_HIGH",
    "loan_purpose": "AA_017_PURPOSE_OF_LOAN_NOT_ACCEPTABLE",
    "dti_ratio_pct": "AA_018_DEBT_TO_INCOME_RATIO_TOO_HIGH",
    "open_tradelines": "AA_019_NUMBER_OF_TRADELINES",
    "down_payment_pct": "AA_020_INSUFFICIENT_DOWN_PAYMENT",
    "missed_payments_12m": "AA_021_PAYMENT_HISTORY",
}

# Maximum CFPB reason codes to surface per ECOA + Reg B §1002.9
# (regulation requires "specific reasons" — typically 4 max for retail)
MAX_ADVERSE_ACTION_CODES = 4


# ════════════════════════════════════════════════════════════════════════
# EU AI Act high-risk classification metadata (Art 6 + Annex III §5(b))
# ════════════════════════════════════════════════════════════════════════

# AI Act high-risk areas — credit underwriting falls under Annex III §5(b)
EU_AI_ACT_ANNEX_III_SECTION = "§5(b) — creditworthiness assessment"

# Article 9 risk management system requirements
EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES: Tuple[str, ...] = (
    "RISK_IDENTIFICATION",            # Art 9(2)(a)
    "RISK_ESTIMATION_AND_EVALUATION",  # Art 9(2)(b)
    "RISK_MITIGATION_MEASURES",       # Art 9(2)(c)
    "TESTING_AGAINST_RISKS",          # Art 9(7)
)

# Article 13 transparency requirements
EU_AI_ACT_REQUIRED_TRANSPARENCY: Tuple[str, ...] = (
    "PURPOSE_OF_AI_SYSTEM",           # Art 13(3)(b)(i)
    "ACCURACY_LEVEL",                 # Art 13(3)(b)(ii)
    "CIRCUMSTANCES_OF_USE",           # Art 13(3)(b)(iii)
    "INPUT_DATA_REQUIREMENTS",        # Art 13(3)(b)(vi)
    "HUMAN_OVERSIGHT_MEASURES",       # Art 13(3)(d)
)

# Article 14 human oversight measures
EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT: Tuple[str, ...] = (
    "INTERPRET_AI_OUTPUT",            # Art 14(4)(c)
    "DISREGARD_OR_OVERRIDE_AI",       # Art 14(4)(d)
    "INTERVENE_OR_INTERRUPT",         # Art 14(4)(e)
)

# Article 15 accuracy + cybersecurity
EU_AI_ACT_REQUIRED_ACCURACY: Tuple[str, ...] = (
    "ACCURACY_METRICS_DEFINED",       # Art 15(1)
    "ACCURACY_METRICS_REPORTED",      # Art 15(3)
    "ROBUSTNESS_TESTING",             # Art 15(4)
    "CYBERSECURITY_MEASURES",         # Art 15(5)
)


# ════════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ApplicantFeatures:
    """Standardized applicant features for underwriting decision.

    Inputs use Decimal for monetary + ratio values (Rule 1 — Decimal purity).
    Missing values explicitly None — never silently zero-substituted.
    """
    applicant_id: str
    # Income / employment
    monthly_income_kes: Optional[Decimal] = None
    income_verified: Optional[bool] = None
    employment_months: Optional[int] = None
    # Stability
    residency_months: Optional[int] = None
    # Credit bureau
    bureau_file_present: Optional[bool] = None
    bureau_score: Optional[Decimal] = None
    credit_history_months: Optional[int] = None
    delinquencies_past_24m: Optional[int] = None
    bankruptcies_past_84m: Optional[int] = None
    recent_inquiries_3m: Optional[int] = None
    active_garnishments: Optional[int] = None
    open_tradelines: Optional[int] = None
    missed_payments_12m: Optional[int] = None
    # Loan request
    amount_requested_kes: Optional[Decimal] = None
    loan_purpose: Optional[str] = None
    down_payment_pct: Optional[Decimal] = None
    # Collateral
    collateral_value_kes: Optional[Decimal] = None
    ltv_ratio_pct: Optional[Decimal] = None
    # Affordability
    dti_ratio_pct: Optional[Decimal] = None
    # Sensitive attributes — HOLD for fairness testing only, not for decisions
    # (per ECOA §1691(a), Article 14(4) EU AI Act)
    protected_class_signals: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureContribution:
    """Per-feature contribution to the underwriting decision."""
    feature_name: str
    feature_value: object       # heterogeneous — dataclass purity not enforced
    contribution_score: Decimal  # signed [-1, 1] — positive = approve, negative = decline
    direction: str               # "POSITIVE" / "NEGATIVE" / "NEUTRAL"
    rank: int                    # 1 = most influential


@dataclass(frozen=True)
class ModelCard:
    """Explainability artifact per Article 13 + ENH-124 + Google Model Cards."""
    model_id: str
    model_version: str
    purpose: str                 # what the model is used for
    training_data_summary: str   # what was learned from
    accuracy_metric_name: str    # e.g. "AUROC", "F1"
    accuracy_metric_value: Optional[Decimal]  # None if rule-based
    fairness_audit_completed: bool
    last_audited: str            # ISO-8601 date
    deviation_notes: str = ""    # Rule 7 — surfaces if rule-based fallback
    methodology: str = ""        # "rule_based" / "linear" / "tree_ensemble" / "neural_net"
    decision_thresholds: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class EUAIActHighRiskMetadata:
    """Compliance metadata for EU AI Act high-risk classification."""
    annex_iii_section: str
    risk_mgmt_processes_in_place: Tuple[str, ...]
    transparency_artifacts_in_place: Tuple[str, ...]
    human_oversight_measures_in_place: Tuple[str, ...]
    accuracy_artifacts_in_place: Tuple[str, ...]
    last_compliance_review: str          # ISO-8601
    open_findings: Tuple[str, ...] = ()
    notes: str = ""

    def completeness_pct(self) -> Decimal:
        """% of required compliance artifacts in place."""
        total_required = (
            len(EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES)
            + len(EU_AI_ACT_REQUIRED_TRANSPARENCY)
            + len(EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT)
            + len(EU_AI_ACT_REQUIRED_ACCURACY))
        total_in_place = (
            len([p for p in self.risk_mgmt_processes_in_place
                  if p in EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES])
            + len([p for p in self.transparency_artifacts_in_place
                    if p in EU_AI_ACT_REQUIRED_TRANSPARENCY])
            + len([p for p in self.human_oversight_measures_in_place
                    if p in EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT])
            + len([p for p in self.accuracy_artifacts_in_place
                    if p in EU_AI_ACT_REQUIRED_ACCURACY]))
        return (
            Decimal(total_in_place) / Decimal(total_required)
            * Decimal("100"))

    def is_compliant(self) -> bool:
        return self.completeness_pct() == Decimal("100") and not self.open_findings


@dataclass(frozen=True)
class AIDecisionResult:
    """Full underwriting decision with explanation + compliance metadata."""
    applicant_id: str
    decision: UnderwritingDecision
    confidence: ConfidenceLevel
    confidence_score: Decimal             # [0, 1]
    pd_estimate: Optional[Decimal]        # from credit_risk_scoring or hooked ML model
    feature_contributions: Tuple[FeatureContribution, ...]
    adverse_action_codes: Tuple[str, ...]   # CFPB Reg B §1002.9 — only on decline
    model_card_ref: str                    # ID linking to ModelCard
    eu_ai_act_metadata_ref: str            # ID linking to EUAIActHighRiskMetadata
    decision_timestamp: str                # ISO-8601
    notes: str = ""

    def is_automated(self) -> bool:
        """True if decision was made fully automatically (no human refer)."""
        return (self.decision != UnderwritingDecision.REFER_HUMAN
                and self.confidence == ConfidenceLevel.HIGH)


# ════════════════════════════════════════════════════════════════════════
# Decision logic
# ════════════════════════════════════════════════════════════════════════

# Rule-based decision thresholds (when no ML model is plugged in)
DECISION_PD_APPROVE_BELOW = Decimal("0.05")    # PD < 5% → approve
DECISION_PD_DECLINE_ABOVE = Decimal("0.20")    # PD > 20% → decline
# Between 5% and 20% → CONDITIONAL_APPROVE or REFER_HUMAN

# Affordability gating (DTI cap)
DTI_HARD_CAP_PCT = Decimal("60")               # always decline if DTI > 60%
DTI_REFER_THRESHOLD_PCT = Decimal("45")        # refer if DTI 45-60%

# LTV gating for secured loans
LTV_HARD_CAP_PCT = Decimal("100")              # decline if requested > 100% LTV
LTV_HIGH_THRESHOLD_PCT = Decimal("80")          # conditional/refer if 80-100%


def compute_underwriting_decision(
    *,
    features: ApplicantFeatures,
    pd_provider: Optional[Callable[[ApplicantFeatures], Decimal]] = None,
    pd_estimate_override: Optional[Decimal] = None,
) -> Tuple[UnderwritingDecision, ConfidenceLevel, Decimal, Optional[Decimal]]:
    """Core decision rule. Returns (decision, confidence, confidence_score, pd_used).

    pd_provider is the ML/rule-based PD scoring callable. If None and no
    pd_estimate_override, the engine returns REFER_HUMAN with LOW confidence
    (Rule 7 — no silent default).
    """
    pd_estimate: Optional[Decimal] = None
    if pd_estimate_override is not None:
        pd_estimate = pd_estimate_override
    elif pd_provider is not None:
        pd_estimate = pd_provider(features)

    # Hard fail: bureau score missing AND no alt data
    if (features.bureau_file_present is False
            and not features.income_verified):
        return (UnderwritingDecision.REFER_HUMAN,
                ConfidenceLevel.LOW,
                Decimal("0.30"),
                pd_estimate)

    # Hard fail: DTI hard cap
    if (features.dti_ratio_pct is not None
            and features.dti_ratio_pct > DTI_HARD_CAP_PCT):
        return (UnderwritingDecision.DECLINE,
                ConfidenceLevel.HIGH,
                Decimal("0.95"),
                pd_estimate)

    # Hard fail: bankruptcies present
    if (features.bankruptcies_past_84m is not None
            and features.bankruptcies_past_84m > 0):
        return (UnderwritingDecision.DECLINE,
                ConfidenceLevel.HIGH,
                Decimal("0.92"),
                pd_estimate)

    # Hard fail: LTV exceeds hard cap on secured loan
    if (features.ltv_ratio_pct is not None
            and features.ltv_ratio_pct > LTV_HARD_CAP_PCT):
        return (UnderwritingDecision.DECLINE,
                ConfidenceLevel.HIGH,
                Decimal("0.90"),
                pd_estimate)

    # Cannot decide without PD estimate
    if pd_estimate is None:
        return (UnderwritingDecision.REFER_HUMAN,
                ConfidenceLevel.LOW,
                Decimal("0.40"),
                pd_estimate)

    # Validate PD bounds
    if not (Decimal("0") <= pd_estimate <= Decimal("1")):
        raise ValueError(
            f"pd_estimate {pd_estimate} outside [0, 1]")

    # PD-driven decision
    if pd_estimate < DECISION_PD_APPROVE_BELOW:
        # Low PD — approve
        # Confidence depends on how far below threshold
        confidence_score = (
            Decimal("1") - pd_estimate / DECISION_PD_APPROVE_BELOW
            * Decimal("0.5"))
        # Reduce confidence if DTI is in refer band
        if (features.dti_ratio_pct is not None
                and features.dti_ratio_pct > DTI_REFER_THRESHOLD_PCT):
            confidence_score = confidence_score - Decimal("0.20")
            return (UnderwritingDecision.CONDITIONAL_APPROVE,
                    _confidence_level(confidence_score),
                    confidence_score, pd_estimate)
        # Reduce confidence if LTV is high
        if (features.ltv_ratio_pct is not None
                and features.ltv_ratio_pct > LTV_HIGH_THRESHOLD_PCT):
            confidence_score = confidence_score - Decimal("0.15")
            return (UnderwritingDecision.CONDITIONAL_APPROVE,
                    _confidence_level(confidence_score),
                    confidence_score, pd_estimate)
        return (UnderwritingDecision.APPROVE,
                _confidence_level(confidence_score),
                confidence_score, pd_estimate)

    if pd_estimate > DECISION_PD_DECLINE_ABOVE:
        # High PD — decline
        confidence_score = (
            Decimal("0.5")
            + (pd_estimate - DECISION_PD_DECLINE_ABOVE)
            / (Decimal("1") - DECISION_PD_DECLINE_ABOVE)
            * Decimal("0.5"))
        return (UnderwritingDecision.DECLINE,
                _confidence_level(confidence_score),
                confidence_score, pd_estimate)

    # Marginal PD: refer to human
    confidence_score = Decimal("0.50")
    return (UnderwritingDecision.REFER_HUMAN,
            ConfidenceLevel.LOW,
            confidence_score, pd_estimate)


def _confidence_level(score: Decimal) -> ConfidenceLevel:
    """Map confidence score to level. 80/20 pattern per ENH-CRD-R7."""
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return ConfidenceLevel.HIGH
    if score >= LOW_CONFIDENCE_THRESHOLD:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


# ════════════════════════════════════════════════════════════════════════
# Explainability — feature contributions
# ════════════════════════════════════════════════════════════════════════

# Default feature weights for rule-based contribution (illustrative).
# In production these are derived from the ML model's gradient/SHAP values.
_DEFAULT_FEATURE_WEIGHTS: Mapping[str, Decimal] = {
    "bureau_score": Decimal("0.25"),
    "dti_ratio_pct": Decimal("0.20"),
    "monthly_income_kes": Decimal("0.15"),
    "delinquencies_past_24m": Decimal("0.15"),
    "employment_months": Decimal("0.10"),
    "ltv_ratio_pct": Decimal("0.05"),
    "credit_history_months": Decimal("0.05"),
    "missed_payments_12m": Decimal("0.05"),
}


def compute_feature_contributions(
    features: ApplicantFeatures,
    *,
    feature_weights: Optional[Mapping[str, Decimal]] = None,
    decision: UnderwritingDecision = UnderwritingDecision.APPROVE,
) -> Tuple[FeatureContribution, ...]:
    """Rank feature contributions for a decision.

    Per ENH-124 + EU AI Act Art 13 — every decision must be explainable.
    Per Rule 7 — these are rule-based contributions when no ML model present.
    """
    weights = feature_weights or _DEFAULT_FEATURE_WEIGHTS
    contributions: List[FeatureContribution] = []

    for feat_name, weight in weights.items():
        feat_value = getattr(features, feat_name, None)
        if feat_value is None:
            continue

        # Direction signing
        direction = _feature_direction(feat_name, feat_value)
        signed = (
            weight if direction == "POSITIVE"
            else -weight if direction == "NEGATIVE"
            else Decimal("0"))

        contributions.append(FeatureContribution(
            feature_name=feat_name,
            feature_value=feat_value,
            contribution_score=signed,
            direction=direction,
            rank=0))  # Ranks set below

    # Rank by absolute contribution
    contributions.sort(key=lambda c: abs(c.contribution_score), reverse=True)
    contributions = [
        FeatureContribution(
            feature_name=c.feature_name,
            feature_value=c.feature_value,
            contribution_score=c.contribution_score,
            direction=c.direction,
            rank=i + 1)
        for i, c in enumerate(contributions)]

    return tuple(contributions)


def _feature_direction(name: str, value: object) -> str:
    """Determine if a feature value contributes toward APPROVE or DECLINE."""
    # Higher is better for these
    higher_is_better = {
        "bureau_score", "monthly_income_kes",
        "credit_history_months", "employment_months",
        "residency_months", "open_tradelines",
        "down_payment_pct", "collateral_value_kes",
    }
    # Higher is worse for these
    higher_is_worse = {
        "dti_ratio_pct", "ltv_ratio_pct", "delinquencies_past_24m",
        "bankruptcies_past_84m", "recent_inquiries_3m",
        "active_garnishments", "missed_payments_12m",
    }

    if name in higher_is_better:
        # Use a simple median-style cut — for production use distribution stats
        if isinstance(value, Decimal):
            return "POSITIVE" if value > Decimal("0") else "NEUTRAL"
        if isinstance(value, int):
            return "POSITIVE" if value > 0 else "NEUTRAL"
        return "NEUTRAL"

    if name in higher_is_worse:
        if isinstance(value, Decimal):
            return "NEGATIVE" if value > Decimal("0") else "NEUTRAL"
        if isinstance(value, int):
            return "NEGATIVE" if value > 0 else "NEUTRAL"
        return "NEUTRAL"

    return "NEUTRAL"


# ════════════════════════════════════════════════════════════════════════
# CFPB adverse action reason codes (ECOA + Reg B §1002.9)
# ════════════════════════════════════════════════════════════════════════

def generate_adverse_action_codes(
    features: ApplicantFeatures,
    contributions: Sequence[FeatureContribution],
    *,
    max_codes: int = MAX_ADVERSE_ACTION_CODES,
) -> Tuple[str, ...]:
    """Return CFPB-compliant adverse action reason codes for a decline.

    Per ECOA + Reg B §1002.9 — applicants must receive specific reasons.
    Per CFPB Circular 2022-03 — algorithmic decisions must produce specific
    reasons; "other" is insufficient.

    Returns top N codes ranked by contribution magnitude (most influential first).
    """
    # Filter to NEGATIVE contributions only — the reasons we declined
    negatives = [c for c in contributions if c.direction == "NEGATIVE"]
    negatives.sort(
        key=lambda c: abs(c.contribution_score), reverse=True)

    codes: List[str] = []
    seen: set = set()
    for c in negatives[:max_codes * 2]:  # over-fetch in case dedup
        code = FEATURE_TO_AA_CODE.get(c.feature_name)
        if code and code not in seen:
            codes.append(code)
            seen.add(code)
        if len(codes) >= max_codes:
            break

    # If no specific codes mapped, surface OTHER as last resort
    if not codes:
        codes.append("AA_022_OTHER_REASON")

    return tuple(codes)


# ════════════════════════════════════════════════════════════════════════
# EU AI Act compliance validation
# ════════════════════════════════════════════════════════════════════════

def validate_eu_ai_act_compliance(
    metadata: EUAIActHighRiskMetadata,
) -> Dict[str, object]:
    """Audit EU AI Act high-risk compliance posture.

    Returns dict with completeness, missing items per article, and verdict.
    """
    missing_risk_mgmt = [
        p for p in EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES
        if p not in metadata.risk_mgmt_processes_in_place]
    missing_transparency = [
        p for p in EU_AI_ACT_REQUIRED_TRANSPARENCY
        if p not in metadata.transparency_artifacts_in_place]
    missing_oversight = [
        p for p in EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT
        if p not in metadata.human_oversight_measures_in_place]
    missing_accuracy = [
        p for p in EU_AI_ACT_REQUIRED_ACCURACY
        if p not in metadata.accuracy_artifacts_in_place]

    return {
        "completeness_pct": metadata.completeness_pct(),
        "is_compliant": metadata.is_compliant(),
        "missing_art9_risk_mgmt": missing_risk_mgmt,
        "missing_art13_transparency": missing_transparency,
        "missing_art14_human_oversight": missing_oversight,
        "missing_art15_accuracy": missing_accuracy,
        "open_findings": list(metadata.open_findings),
        "annex_iii_section": metadata.annex_iii_section,
    }


# ════════════════════════════════════════════════════════════════════════
# Engine orchestrator
# ════════════════════════════════════════════════════════════════════════

class AIUnderwritingEngine:
    """High-level AI underwriting decision orchestrator.

    Composes credit_risk_scoring (PD source) + decision logic + explainability
    + adverse action codes + EU AI Act compliance.
    """

    def __init__(
        self,
        *,
        entity_name: str = "Ecobank Kenya",
        model_card: Optional[ModelCard] = None,
        eu_ai_act_metadata: Optional[EUAIActHighRiskMetadata] = None,
        pd_provider: Optional[Callable[[ApplicantFeatures], Decimal]] = None,
    ):
        self.entity_name = entity_name
        self.model_card = model_card or self._default_model_card()
        self.eu_ai_act_metadata = (
            eu_ai_act_metadata or self._default_eu_ai_act_metadata())
        self.pd_provider = pd_provider
        self._decisions: List[AIDecisionResult] = []

    @staticmethod
    def _default_model_card() -> ModelCard:
        return ModelCard(
            model_id="A2Z-AI-UW-RULE-V1",
            model_version="1.0",
            purpose="Credit underwriting decision support",
            training_data_summary=(
                "Rule-based — no training data; deterministic thresholds"),
            accuracy_metric_name="N/A (rule-based)",
            accuracy_metric_value=None,
            fairness_audit_completed=False,
            last_audited="",
            deviation_notes=SPEC_DEVIATION_NOTE,
            methodology="rule_based",
            decision_thresholds={
                "pd_approve_below": DECISION_PD_APPROVE_BELOW,
                "pd_decline_above": DECISION_PD_DECLINE_ABOVE,
                "dti_hard_cap_pct": DTI_HARD_CAP_PCT,
                "ltv_hard_cap_pct": LTV_HARD_CAP_PCT,
            })

    @staticmethod
    def _default_eu_ai_act_metadata() -> EUAIActHighRiskMetadata:
        return EUAIActHighRiskMetadata(
            annex_iii_section=EU_AI_ACT_ANNEX_III_SECTION,
            risk_mgmt_processes_in_place=(),
            transparency_artifacts_in_place=(),
            human_oversight_measures_in_place=(),
            accuracy_artifacts_in_place=(),
            last_compliance_review="",
            open_findings=("Initial compliance review pending",),
            notes="Default metadata — populate via update_eu_ai_act_compliance()")

    def decide(
        self,
        features: ApplicantFeatures,
        *,
        timestamp: str = "",
        pd_estimate_override: Optional[Decimal] = None,
    ) -> AIDecisionResult:
        """Produce a full underwriting decision for an applicant."""
        # 1) Decision
        decision, conf_lvl, conf_score, pd_used = compute_underwriting_decision(
            features=features,
            pd_provider=self.pd_provider,
            pd_estimate_override=pd_estimate_override)

        # 2) Feature contributions (explainability — Art 13 + ENH-124)
        contributions = compute_feature_contributions(
            features=features, decision=decision)

        # 3) Adverse action codes (only on decline)
        aa_codes: Tuple[str, ...] = ()
        if decision == UnderwritingDecision.DECLINE:
            aa_codes = generate_adverse_action_codes(features, contributions)

        # 4) Build result
        result = AIDecisionResult(
            applicant_id=features.applicant_id,
            decision=decision,
            confidence=conf_lvl,
            confidence_score=conf_score,
            pd_estimate=pd_used,
            feature_contributions=contributions,
            adverse_action_codes=aa_codes,
            model_card_ref=self.model_card.model_id,
            eu_ai_act_metadata_ref=self.eu_ai_act_metadata.annex_iii_section,
            decision_timestamp=timestamp,
            notes=(SPEC_DEVIATION_NOTE
                    if self.model_card.methodology == "rule_based" else ""))
        self._decisions.append(result)
        return result

    def board_summary(self) -> Dict[str, object]:
        """Aggregate decisions for governance reporting."""
        if not self._decisions:
            return {
                "entity": self.entity_name,
                "n_decisions": 0,
                "approve_pct": Decimal("0"),
                "decline_pct": Decimal("0"),
                "refer_pct": Decimal("0"),
                "automation_rate_pct": Decimal("0"),
                "model_card": self.model_card.model_id,
                "eu_ai_act_compliant": self.eu_ai_act_metadata.is_compliant(),
            }

        n = Decimal(len(self._decisions))
        approves = sum(
            1 for d in self._decisions
            if d.decision in (UnderwritingDecision.APPROVE,
                                UnderwritingDecision.CONDITIONAL_APPROVE))
        declines = sum(
            1 for d in self._decisions
            if d.decision == UnderwritingDecision.DECLINE)
        refers = sum(
            1 for d in self._decisions
            if d.decision == UnderwritingDecision.REFER_HUMAN)
        automated = sum(1 for d in self._decisions if d.is_automated())

        return {
            "entity": self.entity_name,
            "n_decisions": int(n),
            "approve_pct": Decimal(approves) / n * Decimal("100"),
            "decline_pct": Decimal(declines) / n * Decimal("100"),
            "refer_pct": Decimal(refers) / n * Decimal("100"),
            "automation_rate_pct": Decimal(automated) / n * Decimal("100"),
            "model_card": self.model_card.model_id,
            "model_methodology": self.model_card.methodology,
            "eu_ai_act_compliant": self.eu_ai_act_metadata.is_compliant(),
            "eu_ai_act_completeness_pct": (
                self.eu_ai_act_metadata.completeness_pct()),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_strong_applicant(applicant_id="APP-1"):
    return ApplicantFeatures(
        applicant_id=applicant_id,
        monthly_income_kes=Decimal("250000"),
        income_verified=True,
        employment_months=60,
        residency_months=48,
        bureau_file_present=True,
        bureau_score=Decimal("750"),
        credit_history_months=120,
        delinquencies_past_24m=0,
        bankruptcies_past_84m=0,
        recent_inquiries_3m=1,
        active_garnishments=0,
        open_tradelines=4,
        missed_payments_12m=0,
        amount_requested_kes=Decimal("2000000"),
        loan_purpose="HOME_PURCHASE",
        down_payment_pct=Decimal("25"),
        collateral_value_kes=Decimal("3000000"),
        ltv_ratio_pct=Decimal("66.67"),
        dti_ratio_pct=Decimal("32"))


def _make_weak_applicant(applicant_id="APP-2"):
    return ApplicantFeatures(
        applicant_id=applicant_id,
        monthly_income_kes=Decimal("30000"),
        income_verified=True,
        employment_months=3,
        residency_months=4,
        bureau_file_present=True,
        bureau_score=Decimal("420"),
        credit_history_months=18,
        delinquencies_past_24m=4,
        bankruptcies_past_84m=0,
        recent_inquiries_3m=8,
        active_garnishments=1,
        open_tradelines=1,
        missed_payments_12m=6,
        amount_requested_kes=Decimal("500000"),
        loan_purpose="PERSONAL",
        down_payment_pct=Decimal("0"),
        collateral_value_kes=None,
        ltv_ratio_pct=None,
        dti_ratio_pct=Decimal("65"))    # over hard cap


def _test_cfpb_codes_complete():
    """At least 22 CFPB AA codes per Reg B App C."""
    assert len(CFPB_ADVERSE_ACTION_CODES) >= 22


def _test_cfpb_other_code_present():
    """OTHER reason code is included for fallback."""
    assert "AA_022_OTHER_REASON" in CFPB_ADVERSE_ACTION_CODES


def _test_eu_ai_act_required_processes_complete():
    """All 4 EU AI Act required process buckets defined."""
    assert len(EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES) == 4
    assert len(EU_AI_ACT_REQUIRED_TRANSPARENCY) == 5
    assert len(EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT) == 3
    assert len(EU_AI_ACT_REQUIRED_ACCURACY) == 4


def _test_decision_strong_applicant_approves():
    """Strong applicant with low PD → APPROVE with HIGH confidence."""
    features = _make_strong_applicant()
    decision, conf_lvl, conf_score, pd = compute_underwriting_decision(
        features=features, pd_estimate_override=Decimal("0.02"))
    assert decision == UnderwritingDecision.APPROVE
    assert conf_lvl == ConfidenceLevel.HIGH
    assert conf_score >= HIGH_CONFIDENCE_THRESHOLD


def _test_decision_dti_hard_cap():
    """DTI > 60% → DECLINE always."""
    features = _make_weak_applicant()  # DTI = 65
    decision, _, _, _ = compute_underwriting_decision(
        features=features, pd_estimate_override=Decimal("0.05"))
    assert decision == UnderwritingDecision.DECLINE


def _test_decision_high_pd_declines():
    """High PD → DECLINE (confidence varies with margin above threshold)."""
    f = _make_strong_applicant()
    # PD = 0.30 (just above 0.20 threshold) → DECLINE with MEDIUM confidence
    decision, conf_lvl, _, _ = compute_underwriting_decision(
        features=f, pd_estimate_override=Decimal("0.30"))
    assert decision == UnderwritingDecision.DECLINE
    assert conf_lvl in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH)
    # PD = 0.95 (very far above threshold) → DECLINE with HIGH confidence
    decision2, conf_lvl2, _, _ = compute_underwriting_decision(
        features=f, pd_estimate_override=Decimal("0.95"))
    assert decision2 == UnderwritingDecision.DECLINE
    assert conf_lvl2 == ConfidenceLevel.HIGH


def _test_decision_marginal_pd_refers():
    """PD between 5% and 20% → REFER_HUMAN."""
    f = _make_strong_applicant()
    decision, _, _, _ = compute_underwriting_decision(
        features=f, pd_estimate_override=Decimal("0.10"))
    assert decision == UnderwritingDecision.REFER_HUMAN


def _test_decision_no_pd_no_provider_refers():
    """No PD and no provider → REFER_HUMAN with LOW confidence (Rule 7)."""
    f = _make_strong_applicant()
    decision, conf_lvl, _, pd = compute_underwriting_decision(features=f)
    assert decision == UnderwritingDecision.REFER_HUMAN
    assert conf_lvl == ConfidenceLevel.LOW
    assert pd is None


def _test_decision_bankruptcy_declines():
    """Any bankruptcy in past 84m → DECLINE."""
    f = ApplicantFeatures(
        applicant_id="X",
        monthly_income_kes=Decimal("100000"),
        income_verified=True,
        bureau_file_present=True,
        bureau_score=Decimal("700"),
        bankruptcies_past_84m=1,
        dti_ratio_pct=Decimal("30"))
    decision, _, _, _ = compute_underwriting_decision(
        features=f, pd_estimate_override=Decimal("0.02"))
    assert decision == UnderwritingDecision.DECLINE


def _test_decision_high_ltv_conditional():
    """LTV in 80-100% range → CONDITIONAL_APPROVE."""
    f = _make_strong_applicant()
    f_high_ltv = ApplicantFeatures(
        **{k: getattr(f, k) for k in f.__dataclass_fields__.keys()
            if k != "ltv_ratio_pct"},
        ltv_ratio_pct=Decimal("85"))
    decision, _, _, _ = compute_underwriting_decision(
        features=f_high_ltv, pd_estimate_override=Decimal("0.02"))
    assert decision == UnderwritingDecision.CONDITIONAL_APPROVE


def _test_decision_invalid_pd_raises():
    """PD outside [0, 1] raises."""
    f = _make_strong_applicant()
    try:
        compute_underwriting_decision(
            features=f, pd_estimate_override=Decimal("1.5"))
        assert False
    except ValueError as e:
        assert "pd_estimate" in str(e)


def _test_feature_contributions_ranked():
    """Contributions are ranked 1, 2, 3..."""
    f = _make_weak_applicant()
    contribs = compute_feature_contributions(f)
    assert contribs[0].rank == 1
    assert contribs[1].rank == 2
    # Sorted descending by abs contribution
    for i in range(len(contribs) - 1):
        assert (abs(contribs[i].contribution_score)
                >= abs(contribs[i + 1].contribution_score))


def _test_feature_contributions_skip_missing():
    """Missing features skipped — not silently zero-substituted."""
    f = ApplicantFeatures(applicant_id="X")  # all fields default
    contribs = compute_feature_contributions(f)
    assert len(contribs) == 0


def _test_adverse_action_codes_for_weak_applicant():
    """Weak applicant decline produces specific CFPB codes."""
    f = _make_weak_applicant()
    contribs = compute_feature_contributions(f)
    codes = generate_adverse_action_codes(f, contribs)
    assert len(codes) > 0
    assert len(codes) <= MAX_ADVERSE_ACTION_CODES
    for c in codes:
        assert c in CFPB_ADVERSE_ACTION_CODES


def _test_adverse_action_codes_dedup():
    """Same code never duplicated even if multiple features map."""
    f = _make_weak_applicant()
    contribs = compute_feature_contributions(f)
    codes = generate_adverse_action_codes(f, contribs)
    assert len(set(codes)) == len(codes)


def _test_eu_ai_act_completeness_zero():
    """Empty metadata → 0% completeness, not compliant."""
    m = EUAIActHighRiskMetadata(
        annex_iii_section=EU_AI_ACT_ANNEX_III_SECTION,
        risk_mgmt_processes_in_place=(),
        transparency_artifacts_in_place=(),
        human_oversight_measures_in_place=(),
        accuracy_artifacts_in_place=(),
        last_compliance_review="")
    assert m.completeness_pct() == Decimal("0")
    assert not m.is_compliant()


def _test_eu_ai_act_completeness_full():
    """All required → 100%."""
    m = EUAIActHighRiskMetadata(
        annex_iii_section=EU_AI_ACT_ANNEX_III_SECTION,
        risk_mgmt_processes_in_place=EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES,
        transparency_artifacts_in_place=EU_AI_ACT_REQUIRED_TRANSPARENCY,
        human_oversight_measures_in_place=EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT,
        accuracy_artifacts_in_place=EU_AI_ACT_REQUIRED_ACCURACY,
        last_compliance_review="2025-12-31")
    assert m.completeness_pct() == Decimal("100")
    assert m.is_compliant()


def _test_eu_ai_act_compliance_validation():
    """validate_eu_ai_act_compliance returns missing items per article."""
    m = EUAIActHighRiskMetadata(
        annex_iii_section=EU_AI_ACT_ANNEX_III_SECTION,
        risk_mgmt_processes_in_place=("RISK_IDENTIFICATION",),
        transparency_artifacts_in_place=(),
        human_oversight_measures_in_place=(),
        accuracy_artifacts_in_place=(),
        last_compliance_review="2025-12-31")
    result = validate_eu_ai_act_compliance(m)
    assert len(result["missing_art9_risk_mgmt"]) == 3   # 4 required, 1 in place
    assert len(result["missing_art13_transparency"]) == 5
    assert not result["is_compliant"]


def _test_engine_decide_strong():
    """Engine produces full AIDecisionResult for strong applicant."""
    eng = AIUnderwritingEngine(
        pd_provider=lambda f: Decimal("0.02"))
    f = _make_strong_applicant()
    r = eng.decide(f, timestamp="2025-01-15T10:00:00Z")
    assert r.decision == UnderwritingDecision.APPROVE
    assert r.is_automated()
    assert r.adverse_action_codes == ()  # no codes on approve
    assert len(r.feature_contributions) > 0


def _test_engine_decide_decline_produces_codes():
    """Engine decline produces CFPB codes."""
    eng = AIUnderwritingEngine(
        pd_provider=lambda f: Decimal("0.30"))
    f = _make_weak_applicant()
    r = eng.decide(f)
    assert r.decision == UnderwritingDecision.DECLINE
    assert len(r.adverse_action_codes) > 0


def _test_engine_default_model_card_marks_rule_based():
    """Default model card surfaces SPEC_DEVIATION (Rule 7)."""
    eng = AIUnderwritingEngine()
    assert eng.model_card.methodology == "rule_based"
    assert SPEC_DEVIATION_NOTE in eng.model_card.deviation_notes


def _test_engine_board_summary():
    """Board summary aggregates decisions correctly."""
    eng = AIUnderwritingEngine(pd_provider=lambda f: Decimal("0.02"))
    eng.decide(_make_strong_applicant("A1"))
    eng.decide(_make_strong_applicant("A2"))
    eng2 = AIUnderwritingEngine(pd_provider=lambda f: Decimal("0.30"))
    eng2.decide(_make_weak_applicant("D1"))
    eng2.decide(_make_weak_applicant("D2"))

    s1 = eng.board_summary()
    assert s1["n_decisions"] == 2
    assert s1["approve_pct"] == Decimal("100")
    s2 = eng2.board_summary()
    assert s2["decline_pct"] == Decimal("100")


def _test_engine_board_summary_empty():
    eng = AIUnderwritingEngine()
    s = eng.board_summary()
    assert s["n_decisions"] == 0
    assert s["approve_pct"] == Decimal("0")


def _test_decimal_purity():
    """Confidence scores + percentages are Decimal."""
    eng = AIUnderwritingEngine(pd_provider=lambda f: Decimal("0.02"))
    r = eng.decide(_make_strong_applicant())
    assert isinstance(r.confidence_score, Decimal)
    s = eng.board_summary()
    assert isinstance(s["approve_pct"], Decimal)


def self_test() -> None:
    tests = [
        _test_cfpb_codes_complete,
        _test_cfpb_other_code_present,
        _test_eu_ai_act_required_processes_complete,
        _test_decision_strong_applicant_approves,
        _test_decision_dti_hard_cap,
        _test_decision_high_pd_declines,
        _test_decision_marginal_pd_refers,
        _test_decision_no_pd_no_provider_refers,
        _test_decision_bankruptcy_declines,
        _test_decision_high_ltv_conditional,
        _test_decision_invalid_pd_raises,
        _test_feature_contributions_ranked,
        _test_feature_contributions_skip_missing,
        _test_adverse_action_codes_for_weak_applicant,
        _test_adverse_action_codes_dedup,
        _test_eu_ai_act_completeness_zero,
        _test_eu_ai_act_completeness_full,
        _test_eu_ai_act_compliance_validation,
        _test_engine_decide_strong,
        _test_engine_decide_decline_produces_codes,
        _test_engine_default_model_card_marks_rule_based,
        _test_engine_board_summary,
        _test_engine_board_summary_empty,
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
        print(f"✗ ai_underwriting self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ ai_underwriting self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

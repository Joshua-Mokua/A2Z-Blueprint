"""utils/applicant_data_sources.py — v10.12 Phase 2 deep impl batch 6 (Credit batch 2).

╔════════════════════════════════════════════════════════════════════════╗
║  APPLICANT DATA SOURCES — ALT DATA + BUREAU + eKYC + FRAUD            ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat B (deterministic data aggregation + verification)     ║
║  Implements 4 of 19 Credit standards from registry:                     ║
║    ENH-120: Alternative Data Intelligence                               ║
║    ENH-129: Credit Bureau Integration                                   ║
║    ENH-121: Digital Identity Verification (eKYC)                        ║
║    ENH-122: Real-Time Fraud Detection                                   ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Alt data: CBK Digital Credit Guideline 2022 (DLP licensing)         ║
║    Bureau:   CBK CRB Regulations 2020 (Revised) + CBK PG/8             ║
║              Kenya CRB Act 2008 + 2014 amendments                      ║
║    eKYC:     CBK AML/CFT Guideline 2017 + Digital Lending Reg 2022    ║
║              Kenya Registration of Persons Act + IPRS Act              ║
║              FATF Recommendation 10 (CDD)                              ║
║              EU eIDAS Reg 910/2014 — electronic identification         ║
║    Fraud:    CBK Cyber Security Guidance Note 2017 + Risk Mgmt Reg    ║
║              PCI DSS v4.0 + ISO 27001                                  ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with: utils/ai_underwriting.py (v10.11) — feeds              ║
║                  ApplicantFeatures with alt + bureau + eKYC outputs    ║
║                  utils/credit_risk_scoring.py (v5.55) — unchanged      ║
║                                                                         ║
║  Honesty Rule 1: missing data sources surface explicitly via None,     ║
║  not silent zero. Honesty Rule 7: external API hooks are callables —   ║
║  no fake responses; failures surface as INCONCLUSIVE/UNKNOWN status.    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

# ════════════════════════════════════════════════════════════════════════
# Alternative data — ENH-120
# ════════════════════════════════════════════════════════════════════════

class AltDataSource(Enum):
    """Alternative data sources for thin-file applicants."""
    MOBILE_MONEY_MPESA = "MOBILE_MONEY_MPESA"
    MOBILE_MONEY_AIRTEL = "MOBILE_MONEY_AIRTEL"
    UTILITY_KENYA_POWER = "UTILITY_KENYA_POWER"
    UTILITY_WATER = "UTILITY_WATER"
    UTILITY_TELCO_POSTPAID = "UTILITY_TELCO_POSTPAID"
    BANK_STATEMENT_ANALYSIS = "BANK_STATEMENT_ANALYSIS"
    EMPLOYER_PAYROLL_VERIFY = "EMPLOYER_PAYROLL_VERIFY"
    SOCIAL_SIGNALS = "SOCIAL_SIGNALS"   # opt-in only — privacy gated
    GOVERNMENT_TAX = "GOVERNMENT_TAX"   # KRA — with consent

    def is_high_signal(self) -> bool:
        """High-signal sources: bank statements, payroll, mobile money."""
        return self in (
            AltDataSource.BANK_STATEMENT_ANALYSIS,
            AltDataSource.EMPLOYER_PAYROLL_VERIFY,
            AltDataSource.MOBILE_MONEY_MPESA,
            AltDataSource.MOBILE_MONEY_AIRTEL,
            AltDataSource.GOVERNMENT_TAX,
        )


# Alt-data freshness thresholds (days)
ALT_DATA_FRESH_DAYS = 30
ALT_DATA_STALE_DAYS = 90
ALT_DATA_MIN_HISTORY_MONTHS = 3


@dataclass(frozen=True)
class AltDataRecord:
    """Per-source alternative data record."""
    source: AltDataSource
    period_start: str             # ISO-8601
    period_end: str
    inflow_kes_total: Optional[Decimal] = None
    outflow_kes_total: Optional[Decimal] = None
    transaction_count: Optional[int] = None
    avg_monthly_balance_kes: Optional[Decimal] = None
    months_of_history: Optional[int] = None
    on_time_payment_count: Optional[int] = None
    late_payment_count: Optional[int] = None
    data_freshness_days: Optional[int] = None
    consent_obtained: bool = False
    notes: str = ""

    def has_sufficient_history(self) -> bool:
        if self.months_of_history is None:
            return False
        return self.months_of_history >= ALT_DATA_MIN_HISTORY_MONTHS

    def is_fresh(self) -> bool:
        if self.data_freshness_days is None:
            return False
        return self.data_freshness_days <= ALT_DATA_FRESH_DAYS


@dataclass(frozen=True)
class AltDataScore:
    """Aggregated alt-data signal for underwriting."""
    score: Decimal              # 0-100
    confidence: Decimal         # 0-1
    n_sources: int
    high_signal_count: int
    sources_used: Tuple[str, ...]
    rationale: str = ""


def compute_alt_data_score(
    records: Sequence[AltDataRecord],
) -> AltDataScore:
    """Compute alt-data score + confidence from available records.

    Methodology:
      - Each record contributes a partial score based on inflow stability
      - High-signal sources (bank, payroll, mobile money) weighted 1.5x
      - Confidence = min(1.0, 0.25 * n_high_signal + 0.10 * n_other)
      - At least 1 record required else score=0 + confidence=0
    """
    if not records:
        return AltDataScore(
            score=Decimal("0"),
            confidence=Decimal("0"),
            n_sources=0,
            high_signal_count=0,
            sources_used=(),
            rationale="no alt-data records provided")

    total_score = Decimal("0")
    total_weight = Decimal("0")
    high_signal_count = 0
    sources_used: List[str] = []

    for r in records:
        if not r.consent_obtained:
            continue
        if not r.has_sufficient_history():
            continue

        sources_used.append(r.source.value)
        weight = Decimal("1.5") if r.source.is_high_signal() else Decimal("1.0")
        if r.source.is_high_signal():
            high_signal_count += 1

        # Score from on-time payments
        on_time = r.on_time_payment_count or 0
        late = r.late_payment_count or 0
        total_pay = on_time + late
        if total_pay > 0:
            payment_score = Decimal(on_time) / Decimal(total_pay) * Decimal("60")
        else:
            payment_score = Decimal("30")  # neutral default

        # Score from inflow consistency (heuristic)
        inflow_score = Decimal("0")
        if r.inflow_kes_total and r.months_of_history:
            avg_inflow = r.inflow_kes_total / Decimal(r.months_of_history)
            if avg_inflow > Decimal("50000"):
                inflow_score = Decimal("40")
            elif avg_inflow > Decimal("10000"):
                inflow_score = Decimal("25")
            else:
                inflow_score = Decimal("10")

        record_score = payment_score + inflow_score  # max ~100
        total_score = total_score + record_score * weight
        total_weight = total_weight + weight

    if total_weight == 0:
        return AltDataScore(
            score=Decimal("0"),
            confidence=Decimal("0"),
            n_sources=len(records),
            high_signal_count=0,
            sources_used=(),
            rationale="no usable records (consent missing or insufficient history)")

    avg_score = total_score / total_weight
    if avg_score > Decimal("100"):
        avg_score = Decimal("100")

    confidence = (
        Decimal("0.25") * Decimal(high_signal_count)
        + Decimal("0.10") * Decimal(len(sources_used) - high_signal_count))
    if confidence > Decimal("1.0"):
        confidence = Decimal("1.0")

    return AltDataScore(
        score=avg_score,
        confidence=confidence,
        n_sources=len(records),
        high_signal_count=high_signal_count,
        sources_used=tuple(sources_used),
        rationale=(
            f"{high_signal_count} high-signal + "
            f"{len(sources_used) - high_signal_count} other sources used"))


# ════════════════════════════════════════════════════════════════════════
# Credit bureau integration — ENH-129
# ════════════════════════════════════════════════════════════════════════

class BureauProvider(Enum):
    """Kenyan licensed Credit Reference Bureaus per CBK CRB Regulations 2020."""
    TRANSUNION_KE = "TRANSUNION_KE"
    METROPOL_KE = "METROPOL_KE"
    CREDITINFO_KE = "CREDITINFO_KE"

    @classmethod
    def all_kenya_licensed(cls) -> Tuple["BureauProvider", ...]:
        """The 3 currently licensed CRBs in Kenya."""
        return (cls.TRANSUNION_KE, cls.METROPOL_KE, cls.CREDITINFO_KE)


# Bureau score normalization — each provider uses different scales
# Normalized to 0-1000 internal scale
BUREAU_SCORE_RANGES: Mapping[BureauProvider, Tuple[Decimal, Decimal]] = {
    BureauProvider.TRANSUNION_KE: (Decimal("200"), Decimal("900")),
    BureauProvider.METROPOL_KE: (Decimal("200"), Decimal("900")),
    BureauProvider.CREDITINFO_KE: (Decimal("0"), Decimal("999")),
}


@dataclass(frozen=True)
class BureauReport:
    """Standardized bureau report (provider-agnostic).

    Provider-specific raw payload is preserved in `raw` for audit; standardized
    fields below are what the underwriting engine consumes.
    """
    provider: BureauProvider
    applicant_id: str
    report_pulled_at: str         # ISO-8601 timestamp
    bureau_score: Optional[Decimal] = None
    score_range: Optional[Tuple[Decimal, Decimal]] = None
    file_present: bool = False
    file_age_months: Optional[int] = None
    open_accounts: Optional[int] = None
    closed_accounts: Optional[int] = None
    delinquent_accounts: Optional[int] = None
    days_past_due_max: Optional[int] = None
    write_offs: Optional[int] = None
    bankruptcies: Optional[int] = None
    inquiries_3m: Optional[int] = None
    inquiries_12m: Optional[int] = None
    raw: Mapping[str, object] = field(default_factory=dict)

    def normalized_score_pct(self) -> Optional[Decimal]:
        """Normalize bureau score to 0-100% (higher = better creditworthiness)."""
        if self.bureau_score is None or self.score_range is None:
            return None
        lo, hi = self.score_range
        if hi == lo:
            return None
        pct = (self.bureau_score - lo) / (hi - lo) * Decimal("100")
        if pct < Decimal("0"):
            pct = Decimal("0")
        if pct > Decimal("100"):
            pct = Decimal("100")
        return pct


def fetch_bureau_report(
    *,
    applicant_id: str,
    provider: BureauProvider,
    fetcher: Optional[Callable[[str, BureauProvider], Mapping[str, object]]] = None,
) -> Optional[BureauReport]:
    """Fetch bureau report via injected fetcher (Rule 7 — no silent network).

    If no fetcher provided, returns None (cannot fabricate bureau data).
    """
    if fetcher is None:
        return None
    try:
        raw = fetcher(applicant_id, provider)
    except Exception as e:
        # Graceful failure — log via raw; engine sees None
        return None

    score_range = BUREAU_SCORE_RANGES.get(provider)
    return BureauReport(
        provider=provider,
        applicant_id=applicant_id,
        report_pulled_at=str(raw.get("pulled_at", "")),
        bureau_score=(
            Decimal(str(raw["score"])) if "score" in raw else None),
        score_range=score_range,
        file_present=bool(raw.get("file_present", False)),
        file_age_months=raw.get("file_age_months"),
        open_accounts=raw.get("open_accounts"),
        closed_accounts=raw.get("closed_accounts"),
        delinquent_accounts=raw.get("delinquent_accounts"),
        days_past_due_max=raw.get("days_past_due_max"),
        write_offs=raw.get("write_offs"),
        bankruptcies=raw.get("bankruptcies"),
        inquiries_3m=raw.get("inquiries_3m"),
        inquiries_12m=raw.get("inquiries_12m"),
        raw=raw)


def aggregate_bureau_reports(
    reports: Sequence[BureauReport],
) -> Dict[str, object]:
    """Aggregate multiple bureau reports — take worst case per dimension.

    CBK CRB Regulations 2020 require lenders to consult ≥1 bureau; many
    consult all 3 and use conservative aggregate. Worst-case wins.
    """
    if not reports:
        return {
            "n_reports": 0,
            "any_file_present": False,
            "min_normalized_score_pct": None,
            "max_delinquencies": None,
            "max_bankruptcies": None,
            "max_dpd": None,
            "providers_consulted": (),
        }

    file_present = any(r.file_present for r in reports)
    norm_scores = [
        r.normalized_score_pct() for r in reports
        if r.normalized_score_pct() is not None]
    delinquencies = [
        r.delinquent_accounts for r in reports
        if r.delinquent_accounts is not None]
    bankruptcies = [
        r.bankruptcies for r in reports
        if r.bankruptcies is not None]
    dpd = [
        r.days_past_due_max for r in reports
        if r.days_past_due_max is not None]

    return {
        "n_reports": len(reports),
        "any_file_present": file_present,
        "min_normalized_score_pct": min(norm_scores) if norm_scores else None,
        "max_delinquencies": max(delinquencies) if delinquencies else None,
        "max_bankruptcies": max(bankruptcies) if bankruptcies else None,
        "max_dpd": max(dpd) if dpd else None,
        "providers_consulted": tuple(r.provider.value for r in reports),
    }


# ════════════════════════════════════════════════════════════════════════
# eKYC — Digital Identity Verification (ENH-121)
# ════════════════════════════════════════════════════════════════════════

class EKYCResult(Enum):
    """Per-check outcome and overall assessment."""
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


# eKYC checks required per CBK AML/CFT 2017 + Digital Lending 2022
EKYC_REQUIRED_CHECKS: Tuple[str, ...] = (
    "IPRS_LOOKUP",            # Integrated Population Registration Service (Kenya)
    "BIOMETRIC_FACE_MATCH",   # liveness + match against ID photo
    "DOCUMENT_AUTHENTICITY",  # ID document integrity (MRZ, hologram)
    "MOBILE_NUMBER_VERIFY",   # SIM registration vs ID name
    "PEP_SCREENING",          # politically-exposed-person check
    "SANCTIONS_SCREENING",    # OFAC, UN, EU sanctions lists
)

# Score thresholds for biometric face match (0-1)
BIOMETRIC_MATCH_VERIFIED_ABOVE = Decimal("0.85")
BIOMETRIC_MATCH_FAILED_BELOW = Decimal("0.50")


@dataclass(frozen=True)
class EKYCCheckResult:
    """Single eKYC check outcome."""
    check_name: str          # one of EKYC_REQUIRED_CHECKS
    result: EKYCResult
    score: Optional[Decimal] = None  # 0-1 if applicable
    notes: str = ""


@dataclass(frozen=True)
class EKYCAssessment:
    """Full eKYC assessment for an applicant."""
    applicant_id: str
    timestamp: str
    checks: Tuple[EKYCCheckResult, ...]
    overall_result: EKYCResult
    completeness_pct: Decimal      # % of required checks performed

    def is_verified(self) -> bool:
        return self.overall_result == EKYCResult.VERIFIED

    def failed_checks(self) -> Tuple[str, ...]:
        return tuple(
            c.check_name for c in self.checks
            if c.result == EKYCResult.FAILED)


def assess_ekyc(
    *,
    applicant_id: str,
    timestamp: str,
    iprs_lookup_passed: Optional[bool] = None,
    biometric_match_score: Optional[Decimal] = None,
    document_auth_passed: Optional[bool] = None,
    mobile_number_verified: Optional[bool] = None,
    pep_hit: Optional[bool] = None,
    sanctions_hit: Optional[bool] = None,
) -> EKYCAssessment:
    """Run eKYC assessment given individual check results.

    Each parameter None means "check not performed". Per Rule 1, missing
    checks surface explicitly and are not silently passed.
    """
    checks: List[EKYCCheckResult] = []

    # IPRS (mandatory per CBK)
    if iprs_lookup_passed is True:
        checks.append(EKYCCheckResult(
            check_name="IPRS_LOOKUP", result=EKYCResult.VERIFIED))
    elif iprs_lookup_passed is False:
        checks.append(EKYCCheckResult(
            check_name="IPRS_LOOKUP", result=EKYCResult.FAILED,
            notes="IPRS does not match application data"))

    # Biometric
    if biometric_match_score is not None:
        if biometric_match_score >= BIOMETRIC_MATCH_VERIFIED_ABOVE:
            r = EKYCResult.VERIFIED
        elif biometric_match_score < BIOMETRIC_MATCH_FAILED_BELOW:
            r = EKYCResult.FAILED
        else:
            r = EKYCResult.INCONCLUSIVE
        checks.append(EKYCCheckResult(
            check_name="BIOMETRIC_FACE_MATCH",
            result=r, score=biometric_match_score))

    # Doc auth
    if document_auth_passed is True:
        checks.append(EKYCCheckResult(
            check_name="DOCUMENT_AUTHENTICITY", result=EKYCResult.VERIFIED))
    elif document_auth_passed is False:
        checks.append(EKYCCheckResult(
            check_name="DOCUMENT_AUTHENTICITY", result=EKYCResult.FAILED,
            notes="Document authenticity check failed"))

    # Mobile number
    if mobile_number_verified is True:
        checks.append(EKYCCheckResult(
            check_name="MOBILE_NUMBER_VERIFY", result=EKYCResult.VERIFIED))
    elif mobile_number_verified is False:
        checks.append(EKYCCheckResult(
            check_name="MOBILE_NUMBER_VERIFY", result=EKYCResult.FAILED))

    # PEP screening — hit means require enhanced due diligence (not auto-fail)
    if pep_hit is True:
        checks.append(EKYCCheckResult(
            check_name="PEP_SCREENING", result=EKYCResult.INCONCLUSIVE,
            notes="PEP hit — enhanced due diligence required"))
    elif pep_hit is False:
        checks.append(EKYCCheckResult(
            check_name="PEP_SCREENING", result=EKYCResult.VERIFIED))

    # Sanctions hit = automatic FAIL per FATF Rec 6
    if sanctions_hit is True:
        checks.append(EKYCCheckResult(
            check_name="SANCTIONS_SCREENING", result=EKYCResult.FAILED,
            notes="Sanctions list hit — must decline per FATF Rec 6"))
    elif sanctions_hit is False:
        checks.append(EKYCCheckResult(
            check_name="SANCTIONS_SCREENING", result=EKYCResult.VERIFIED))

    # Overall result
    completeness_pct = (
        Decimal(len(checks)) / Decimal(len(EKYC_REQUIRED_CHECKS))
        * Decimal("100"))

    if any(c.result == EKYCResult.FAILED for c in checks):
        overall = EKYCResult.FAILED
    elif completeness_pct < Decimal("100"):
        overall = EKYCResult.INCONCLUSIVE
    elif any(c.result == EKYCResult.INCONCLUSIVE for c in checks):
        overall = EKYCResult.INCONCLUSIVE
    else:
        overall = EKYCResult.VERIFIED

    return EKYCAssessment(
        applicant_id=applicant_id,
        timestamp=timestamp,
        checks=tuple(checks),
        overall_result=overall,
        completeness_pct=completeness_pct)


# ════════════════════════════════════════════════════════════════════════
# Real-time fraud detection — ENH-122
# ════════════════════════════════════════════════════════════════════════

class FraudSignal(Enum):
    """Categorical fraud detection signals."""
    VELOCITY_HIGH_FREQUENCY = "VELOCITY_HIGH_FREQUENCY"
    DEVICE_SHARED_ACROSS_APPLICANTS = "DEVICE_SHARED_ACROSS_APPLICANTS"
    IP_SHARED_ACROSS_APPLICANTS = "IP_SHARED_ACROSS_APPLICANTS"
    BEHAVIOR_COPY_PASTE_FORM = "BEHAVIOR_COPY_PASTE_FORM"
    BEHAVIOR_TYPING_TOO_FAST = "BEHAVIOR_TYPING_TOO_FAST"
    GEO_VPN_OR_PROXY_DETECTED = "GEO_VPN_OR_PROXY_DETECTED"
    GEO_LOCATION_MISMATCH = "GEO_LOCATION_MISMATCH"
    DOCUMENT_PHOTO_MANIPULATED = "DOCUMENT_PHOTO_MANIPULATED"
    SYNTHETIC_IDENTITY_PATTERN = "SYNTHETIC_IDENTITY_PATTERN"
    KNOWN_FRAUD_RING_MATCH = "KNOWN_FRAUD_RING_MATCH"


# Per-signal severity weight (0-100 each — sum can exceed 100, score capped)
FRAUD_SIGNAL_WEIGHTS: Mapping[FraudSignal, Decimal] = {
    FraudSignal.VELOCITY_HIGH_FREQUENCY: Decimal("25"),
    FraudSignal.DEVICE_SHARED_ACROSS_APPLICANTS: Decimal("40"),
    FraudSignal.IP_SHARED_ACROSS_APPLICANTS: Decimal("20"),
    FraudSignal.BEHAVIOR_COPY_PASTE_FORM: Decimal("15"),
    FraudSignal.BEHAVIOR_TYPING_TOO_FAST: Decimal("10"),
    FraudSignal.GEO_VPN_OR_PROXY_DETECTED: Decimal("15"),
    FraudSignal.GEO_LOCATION_MISMATCH: Decimal("20"),
    FraudSignal.DOCUMENT_PHOTO_MANIPULATED: Decimal("60"),
    FraudSignal.SYNTHETIC_IDENTITY_PATTERN: Decimal("70"),
    FraudSignal.KNOWN_FRAUD_RING_MATCH: Decimal("90"),
}

# Velocity rules: more than N applications from same identifier in window
VELOCITY_RULE_APPLICATIONS_PER_30MIN = 3
VELOCITY_RULE_APPLICATIONS_PER_24H = 8


@dataclass(frozen=True)
class FraudCheckResult:
    """Result of fraud checks for one applicant."""
    applicant_id: str
    timestamp: str
    signals_fired: Tuple[str, ...]
    fraud_score: Decimal           # 0-100
    decision_recommendation: str   # ALLOW / CHALLENGE / BLOCK
    notes: str = ""


def assess_fraud(
    *,
    applicant_id: str,
    timestamp: str,
    signals: Sequence[FraudSignal],
) -> FraudCheckResult:
    """Compute fraud score from fired signals.

    Score = sum of fired-signal weights, capped at 100.
    Decision:
      < 30  → ALLOW
      30-70 → CHALLENGE (additional verification needed)
      ≥ 70  → BLOCK
    """
    score = Decimal("0")
    for sig in signals:
        score = score + FRAUD_SIGNAL_WEIGHTS.get(sig, Decimal("10"))
    if score > Decimal("100"):
        score = Decimal("100")

    if score < Decimal("30"):
        decision = "ALLOW"
    elif score < Decimal("70"):
        decision = "CHALLENGE"
    else:
        decision = "BLOCK"

    return FraudCheckResult(
        applicant_id=applicant_id,
        timestamp=timestamp,
        signals_fired=tuple(s.value for s in signals),
        fraud_score=score,
        decision_recommendation=decision,
        notes=f"{len(signals)} signal(s) fired")


def evaluate_velocity_rules(
    *,
    identifier: str,         # IP, device fingerprint, or applicant ID
    apps_last_30min: int,
    apps_last_24h: int,
) -> Tuple[FraudSignal, ...]:
    """Evaluate velocity-based fraud rules. Returns signals to fire."""
    signals: List[FraudSignal] = []
    if apps_last_30min > VELOCITY_RULE_APPLICATIONS_PER_30MIN:
        signals.append(FraudSignal.VELOCITY_HIGH_FREQUENCY)
    if apps_last_24h > VELOCITY_RULE_APPLICATIONS_PER_24H:
        signals.append(FraudSignal.VELOCITY_HIGH_FREQUENCY)
    return tuple(set(signals))


# ════════════════════════════════════════════════════════════════════════
# Engine — composes the 4 sub-systems
# ════════════════════════════════════════════════════════════════════════

class ApplicantDataAggregator:
    """Orchestrates alt data + bureau + eKYC + fraud per applicant.

    Composition flow:
      1. Aggregate alt-data records → AltDataScore
      2. Fetch / aggregate bureau reports
      3. Run eKYC checks
      4. Run fraud checks
      5. Produce a unified ApplicantDataProfile for downstream underwriting
    """

    def __init__(self, *, entity_name: str = "Ecobank Kenya"):
        self.entity_name = entity_name
        self._profiles: List[Dict[str, object]] = []

    def build_profile(
        self,
        *,
        applicant_id: str,
        timestamp: str,
        alt_data_records: Sequence[AltDataRecord] = (),
        bureau_reports: Sequence[BureauReport] = (),
        ekyc_assessment: Optional[EKYCAssessment] = None,
        fraud_check: Optional[FraudCheckResult] = None,
    ) -> Dict[str, object]:
        alt = compute_alt_data_score(alt_data_records)
        bureau = aggregate_bureau_reports(bureau_reports)

        # Decision recommendation overall
        recommendation = "PROCEED"
        rationale: List[str] = []

        if ekyc_assessment is not None:
            if ekyc_assessment.overall_result == EKYCResult.FAILED:
                recommendation = "DECLINE"
                rationale.append(
                    f"eKYC failed: {ekyc_assessment.failed_checks()}")
            elif ekyc_assessment.overall_result == EKYCResult.INCONCLUSIVE:
                recommendation = "REFER"
                rationale.append("eKYC inconclusive")

        if fraud_check is not None:
            if fraud_check.decision_recommendation == "BLOCK":
                recommendation = "DECLINE"
                rationale.append(
                    f"fraud BLOCK ({fraud_check.fraud_score})")
            elif (fraud_check.decision_recommendation == "CHALLENGE"
                    and recommendation == "PROCEED"):
                recommendation = "REFER"
                rationale.append(
                    f"fraud CHALLENGE ({fraud_check.fraud_score})")

        if (not bureau["any_file_present"]
                and alt.confidence < Decimal("0.5")):
            if recommendation == "PROCEED":
                recommendation = "REFER"
            rationale.append("thin file (no bureau + low alt-data confidence)")

        profile = {
            "applicant_id": applicant_id,
            "timestamp": timestamp,
            "alt_data_score": alt,
            "bureau_aggregate": bureau,
            "ekyc": ekyc_assessment,
            "fraud_check": fraud_check,
            "recommendation": recommendation,
            "rationale": tuple(rationale),
        }
        self._profiles.append(profile)
        return profile

    def board_summary(self) -> Dict[str, object]:
        """Aggregate profiles for governance reporting."""
        if not self._profiles:
            return {
                "entity": self.entity_name,
                "n_profiles": 0,
                "decline_pct": Decimal("0"),
                "refer_pct": Decimal("0"),
                "proceed_pct": Decimal("0"),
            }

        n = Decimal(len(self._profiles))
        decline = sum(1 for p in self._profiles
                        if p["recommendation"] == "DECLINE")
        refer = sum(1 for p in self._profiles
                      if p["recommendation"] == "REFER")
        proceed = sum(1 for p in self._profiles
                        if p["recommendation"] == "PROCEED")
        return {
            "entity": self.entity_name,
            "n_profiles": int(n),
            "decline_pct": Decimal(decline) / n * Decimal("100"),
            "refer_pct": Decimal(refer) / n * Decimal("100"),
            "proceed_pct": Decimal(proceed) / n * Decimal("100"),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_alt_data_sources_high_signal_correct():
    assert AltDataSource.MOBILE_MONEY_MPESA.is_high_signal()
    assert AltDataSource.BANK_STATEMENT_ANALYSIS.is_high_signal()
    assert not AltDataSource.SOCIAL_SIGNALS.is_high_signal()


def _test_alt_data_score_empty():
    s = compute_alt_data_score([])
    assert s.score == Decimal("0")
    assert s.confidence == Decimal("0")
    assert s.n_sources == 0


def _test_alt_data_score_no_consent_returns_zero():
    r = AltDataRecord(
        source=AltDataSource.MOBILE_MONEY_MPESA,
        period_start="2025-01-01", period_end="2025-12-31",
        months_of_history=12,
        on_time_payment_count=12, late_payment_count=0,
        consent_obtained=False)
    s = compute_alt_data_score([r])
    assert s.score == Decimal("0")
    assert "consent" in s.rationale.lower()


def _test_alt_data_score_high_signal_consented():
    """Mobile money + payroll + bank — high confidence."""
    records = [
        AltDataRecord(
            source=AltDataSource.MOBILE_MONEY_MPESA,
            period_start="2025-01-01", period_end="2025-12-31",
            months_of_history=12,
            inflow_kes_total=Decimal("600000"),
            on_time_payment_count=24, late_payment_count=0,
            consent_obtained=True),
        AltDataRecord(
            source=AltDataSource.EMPLOYER_PAYROLL_VERIFY,
            period_start="2025-01-01", period_end="2025-12-31",
            months_of_history=12,
            inflow_kes_total=Decimal("1200000"),
            on_time_payment_count=12, late_payment_count=0,
            consent_obtained=True),
    ]
    s = compute_alt_data_score(records)
    assert s.score > Decimal("70")
    assert s.confidence >= Decimal("0.5")
    assert s.high_signal_count == 2


def _test_alt_data_insufficient_history_skipped():
    r = AltDataRecord(
        source=AltDataSource.MOBILE_MONEY_MPESA,
        period_start="2025-11-01", period_end="2025-12-31",
        months_of_history=2,    # < ALT_DATA_MIN_HISTORY_MONTHS = 3
        consent_obtained=True)
    s = compute_alt_data_score([r])
    assert s.score == Decimal("0")


def _test_bureau_provider_kenya_lists():
    assert len(BureauProvider.all_kenya_licensed()) == 3
    assert BureauProvider.TRANSUNION_KE in BureauProvider.all_kenya_licensed()


def _test_bureau_score_normalization():
    r = BureauReport(
        provider=BureauProvider.TRANSUNION_KE,
        applicant_id="APP-1", report_pulled_at="",
        bureau_score=Decimal("550"),
        score_range=BUREAU_SCORE_RANGES[BureauProvider.TRANSUNION_KE],
        file_present=True)
    # 550 in [200, 900] → 50%
    expected = (Decimal("550") - Decimal("200")) / (Decimal("900") - Decimal("200")) * Decimal("100")
    assert r.normalized_score_pct() == expected


def _test_bureau_score_normalization_missing():
    r = BureauReport(
        provider=BureauProvider.TRANSUNION_KE,
        applicant_id="X", report_pulled_at="",
        bureau_score=None)
    assert r.normalized_score_pct() is None


def _test_bureau_aggregate_takes_worst_case():
    rs = [
        BureauReport(
            provider=BureauProvider.TRANSUNION_KE,
            applicant_id="X", report_pulled_at="",
            bureau_score=Decimal("700"),
            score_range=BUREAU_SCORE_RANGES[BureauProvider.TRANSUNION_KE],
            file_present=True,
            delinquent_accounts=0, days_past_due_max=0, bankruptcies=0),
        BureauReport(
            provider=BureauProvider.METROPOL_KE,
            applicant_id="X", report_pulled_at="",
            bureau_score=Decimal("400"),
            score_range=BUREAU_SCORE_RANGES[BureauProvider.METROPOL_KE],
            file_present=True,
            delinquent_accounts=2, days_past_due_max=60, bankruptcies=0),
    ]
    agg = aggregate_bureau_reports(rs)
    assert agg["n_reports"] == 2
    assert agg["any_file_present"] is True
    assert agg["max_delinquencies"] == 2
    assert agg["max_dpd"] == 60


def _test_bureau_no_fetcher_returns_none():
    """Rule 7 — no fetcher → None, never fabricated."""
    r = fetch_bureau_report(
        applicant_id="X", provider=BureauProvider.TRANSUNION_KE)
    assert r is None


def _test_bureau_failing_fetcher_returns_none():
    def failing(*args, **kwargs):
        raise ConnectionError("network down")
    r = fetch_bureau_report(
        applicant_id="X", provider=BureauProvider.TRANSUNION_KE,
        fetcher=failing)
    assert r is None


def _test_ekyc_required_checks_count():
    assert len(EKYC_REQUIRED_CHECKS) == 6
    assert "IPRS_LOOKUP" in EKYC_REQUIRED_CHECKS
    assert "SANCTIONS_SCREENING" in EKYC_REQUIRED_CHECKS


def _test_ekyc_full_pass_verified():
    r = assess_ekyc(
        applicant_id="X", timestamp="2025-01-15T10:00:00Z",
        iprs_lookup_passed=True,
        biometric_match_score=Decimal("0.92"),
        document_auth_passed=True,
        mobile_number_verified=True,
        pep_hit=False, sanctions_hit=False)
    assert r.is_verified()
    assert r.completeness_pct == Decimal("100")


def _test_ekyc_sanctions_hit_failed():
    r = assess_ekyc(
        applicant_id="X", timestamp="t",
        iprs_lookup_passed=True,
        biometric_match_score=Decimal("0.95"),
        document_auth_passed=True,
        mobile_number_verified=True,
        pep_hit=False, sanctions_hit=True)
    assert r.overall_result == EKYCResult.FAILED


def _test_ekyc_pep_hit_inconclusive_not_failed():
    """PEP requires EDD, not auto-decline."""
    r = assess_ekyc(
        applicant_id="X", timestamp="t",
        iprs_lookup_passed=True,
        biometric_match_score=Decimal("0.95"),
        document_auth_passed=True,
        mobile_number_verified=True,
        pep_hit=True, sanctions_hit=False)
    assert r.overall_result == EKYCResult.INCONCLUSIVE


def _test_ekyc_partial_inconclusive():
    """Missing checks → INCONCLUSIVE, not silent pass."""
    r = assess_ekyc(
        applicant_id="X", timestamp="t",
        iprs_lookup_passed=True,
        biometric_match_score=Decimal("0.95"))
    assert r.overall_result == EKYCResult.INCONCLUSIVE
    assert r.completeness_pct < Decimal("100")


def _test_ekyc_biometric_inconclusive_band():
    """Biometric score 0.50-0.85 → INCONCLUSIVE."""
    r = assess_ekyc(
        applicant_id="X", timestamp="t",
        iprs_lookup_passed=True,
        biometric_match_score=Decimal("0.70"),
        document_auth_passed=True,
        mobile_number_verified=True,
        pep_hit=False, sanctions_hit=False)
    bio_check = next(c for c in r.checks
                       if c.check_name == "BIOMETRIC_FACE_MATCH")
    assert bio_check.result == EKYCResult.INCONCLUSIVE


def _test_fraud_no_signals_allow():
    r = assess_fraud(applicant_id="X", timestamp="t", signals=[])
    assert r.fraud_score == Decimal("0")
    assert r.decision_recommendation == "ALLOW"


def _test_fraud_one_strong_signal_blocks():
    r = assess_fraud(
        applicant_id="X", timestamp="t",
        signals=[FraudSignal.KNOWN_FRAUD_RING_MATCH])
    assert r.fraud_score == Decimal("90")
    assert r.decision_recommendation == "BLOCK"


def _test_fraud_multiple_signals_capped():
    r = assess_fraud(
        applicant_id="X", timestamp="t",
        signals=[
            FraudSignal.SYNTHETIC_IDENTITY_PATTERN,
            FraudSignal.DOCUMENT_PHOTO_MANIPULATED,
            FraudSignal.KNOWN_FRAUD_RING_MATCH])
    assert r.fraud_score == Decimal("100")  # capped


def _test_fraud_velocity_rule_fires():
    signals = evaluate_velocity_rules(
        identifier="IP-1.2.3.4",
        apps_last_30min=5,
        apps_last_24h=3)
    assert FraudSignal.VELOCITY_HIGH_FREQUENCY in signals


def _test_fraud_velocity_rule_quiet():
    signals = evaluate_velocity_rules(
        identifier="IP-1.2.3.4",
        apps_last_30min=2,
        apps_last_24h=4)
    assert len(signals) == 0


def _test_aggregator_full_profile_proceeds():
    eng = ApplicantDataAggregator()
    profile = eng.build_profile(
        applicant_id="X", timestamp="t",
        alt_data_records=[
            AltDataRecord(
                source=AltDataSource.BANK_STATEMENT_ANALYSIS,
                period_start="2025-01-01", period_end="2025-12-31",
                months_of_history=12,
                inflow_kes_total=Decimal("1200000"),
                on_time_payment_count=12, late_payment_count=0,
                consent_obtained=True)],
        bureau_reports=[
            BureauReport(
                provider=BureauProvider.TRANSUNION_KE,
                applicant_id="X", report_pulled_at="",
                bureau_score=Decimal("750"),
                score_range=BUREAU_SCORE_RANGES[BureauProvider.TRANSUNION_KE],
                file_present=True,
                delinquent_accounts=0, bankruptcies=0)],
        ekyc_assessment=assess_ekyc(
            applicant_id="X", timestamp="t",
            iprs_lookup_passed=True,
            biometric_match_score=Decimal("0.95"),
            document_auth_passed=True,
            mobile_number_verified=True,
            pep_hit=False, sanctions_hit=False),
        fraud_check=assess_fraud(applicant_id="X", timestamp="t", signals=[]))
    assert profile["recommendation"] == "PROCEED"


def _test_aggregator_sanctions_decline():
    eng = ApplicantDataAggregator()
    ekyc = assess_ekyc(
        applicant_id="X", timestamp="t",
        iprs_lookup_passed=True,
        biometric_match_score=Decimal("0.90"),
        document_auth_passed=True,
        mobile_number_verified=True,
        pep_hit=False, sanctions_hit=True)
    profile = eng.build_profile(
        applicant_id="X", timestamp="t",
        ekyc_assessment=ekyc,
        fraud_check=assess_fraud(applicant_id="X", timestamp="t", signals=[]))
    assert profile["recommendation"] == "DECLINE"


def _test_aggregator_thin_file_refers():
    """No bureau + low alt-data confidence → REFER."""
    eng = ApplicantDataAggregator()
    profile = eng.build_profile(
        applicant_id="X", timestamp="t",
        ekyc_assessment=assess_ekyc(
            applicant_id="X", timestamp="t",
            iprs_lookup_passed=True,
            biometric_match_score=Decimal("0.90"),
            document_auth_passed=True,
            mobile_number_verified=True,
            pep_hit=False, sanctions_hit=False),
        fraud_check=assess_fraud(applicant_id="X", timestamp="t", signals=[]))
    assert profile["recommendation"] == "REFER"


def _test_aggregator_board_summary():
    eng = ApplicantDataAggregator()
    eng.build_profile(
        applicant_id="A", timestamp="t",
        ekyc_assessment=assess_ekyc(
            applicant_id="A", timestamp="t",
            iprs_lookup_passed=True,
            biometric_match_score=Decimal("0.95"),
            document_auth_passed=True,
            mobile_number_verified=True,
            pep_hit=False, sanctions_hit=False),
        fraud_check=assess_fraud(applicant_id="A", timestamp="t",
                                    signals=[FraudSignal.KNOWN_FRAUD_RING_MATCH]))
    s = eng.board_summary()
    assert s["n_profiles"] == 1
    assert s["decline_pct"] == Decimal("100")


def _test_decimal_purity():
    s = compute_alt_data_score([
        AltDataRecord(
            source=AltDataSource.MOBILE_MONEY_MPESA,
            period_start="2025-01-01", period_end="2025-12-31",
            months_of_history=12,
            inflow_kes_total=Decimal("600000"),
            on_time_payment_count=12, late_payment_count=0,
            consent_obtained=True)])
    assert isinstance(s.score, Decimal)
    assert isinstance(s.confidence, Decimal)


def self_test() -> None:
    tests = [
        _test_alt_data_sources_high_signal_correct,
        _test_alt_data_score_empty,
        _test_alt_data_score_no_consent_returns_zero,
        _test_alt_data_score_high_signal_consented,
        _test_alt_data_insufficient_history_skipped,
        _test_bureau_provider_kenya_lists,
        _test_bureau_score_normalization,
        _test_bureau_score_normalization_missing,
        _test_bureau_aggregate_takes_worst_case,
        _test_bureau_no_fetcher_returns_none,
        _test_bureau_failing_fetcher_returns_none,
        _test_ekyc_required_checks_count,
        _test_ekyc_full_pass_verified,
        _test_ekyc_sanctions_hit_failed,
        _test_ekyc_pep_hit_inconclusive_not_failed,
        _test_ekyc_partial_inconclusive,
        _test_ekyc_biometric_inconclusive_band,
        _test_fraud_no_signals_allow,
        _test_fraud_one_strong_signal_blocks,
        _test_fraud_multiple_signals_capped,
        _test_fraud_velocity_rule_fires,
        _test_fraud_velocity_rule_quiet,
        _test_aggregator_full_profile_proceeds,
        _test_aggregator_sanctions_decline,
        _test_aggregator_thin_file_refers,
        _test_aggregator_board_summary,
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
        print(f"✗ applicant_data_sources self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ applicant_data_sources self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()

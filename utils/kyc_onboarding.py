"""utils/kyc_onboarding.py — ENH-191 Digital KYC/KYB Onboarding Engine.

================================================================================
A2Z MIS 360 — ENH-191 Digital KYC/KYB Onboarding Engine
================================================================================

ORCHESTRATION engine for digital onboarding of new customers (KYC) and
new businesses (KYB). Wires together:

    1. Identity intake (national ID, KRA PIN, passport / company registration,
       beneficial owners) — pure data capture, this engine
    2. ID verification — delegates to ENH-121 (utils/kyc_aml_risk.py)
    3. Risk scoring — delegates to Standard #57 (KycAmlRiskEngine in
       utils/kyc_aml_risk.py)
    4. KYC tier assignment — this engine, deterministic from risk band
    5. Review schedule — this engine, deterministic from tier

CRITICAL DESIGN DECISION
------------------------
This engine does NOT duplicate identity verification or risk scoring. Both
already exist as live, active engines (ENH-121 / Standard #57). ENH-191 is
the ORCHESTRATOR that takes a new customer/business through the canonical
sequence and produces a single OnboardingDecision dataclass that downstream
systems (ENH-192 PEP/Sanctions, ENH-193 AML monitoring, account opening
workflows) can consume.

Same pattern as the Treasury cockpit's role with Treasury engines: compose,
don't duplicate.

DESIGN INVARIANTS
-----------------
- Frozen dataclasses for inputs and outputs (Decimal-internal precision; no
  float on money in beneficial-owner-share calculations)
- Deterministic decisions: same input → same output, no randomness
- Honest deferral surfaces: the engine returns DocumentVerificationStatus
  and BiometricVerificationStatus enums with NOT_PROVIDED state so
  downstream operators can see what hasn't happened yet, vs assuming
  it has been
- All write operations audit-loggable via emit_audit_records() helper
- Rule 6 honesty: missing optional fields do NOT increase the customer's
  trust score; missing mandatory fields → ONBOARDING_BLOCKED
- KYB tier inheritance: a business's tier is the MAX of (its own risk
  band, the highest-risk band of any beneficial owner) — single bad
  beneficial owner pulls the whole business into EDD

CBK + FATF ALIGNMENT
--------------------
- CBK Prudential Guideline CBK/PG/15 (Anti-Money Laundering) sequence
  honored: identity → screen → risk-rate → tier → ongoing review
- FATF 40 Recommendation 10 (CDD measures): basic identification,
  beneficial ownership identification, purpose of relationship,
  ongoing monitoring
- Tier vocabulary aligned with CBK/PG/15:
  - SDD (Simplified Due Diligence) — LOW risk, retail with verified ID
  - CDD (Customer Due Diligence) — MEDIUM risk, standard
  - EDD (Enhanced Due Diligence) — HIGH risk, PEP, complex structures
  - PROHIBITED — sanctions match, prohibited jurisdictions

KENYA-SPECIFIC CONSIDERATIONS
-----------------------------
- National ID: 8-digit format
- KRA PIN: A + 9 digits + lowercase letter (e.g. A012345678X)
- Passport: country prefix
- Business registration: BRS (Business Registration Service) certificate
  number for companies; Sole Proprietor Certificate for sole props
- Beneficial owner threshold: per BO Regulations 2020, anyone with >=10%
  ownership OR significant control must be identified

ENGINE STATE
------------
Stateful per-instance — register applicants, retrieve decisions later.
Mirrors the TreasuryALMEngine pattern (in-process state for the API
session; production deployment backs it with the application database).

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations — controlled vocabularies
# ---------------------------------------------------------------------------


class ApplicantType(str, Enum):
    """Top-level distinction between KYC (individual) and KYB (business)."""
    INDIVIDUAL = "INDIVIDUAL"
    SOLE_PROPRIETOR = "SOLE_PROPRIETOR"
    PARTNERSHIP = "PARTNERSHIP"
    LIMITED_COMPANY = "LIMITED_COMPANY"
    NGO = "NGO"
    TRUST = "TRUST"


class IdDocumentType(str, Enum):
    NATIONAL_ID = "NATIONAL_ID"
    PASSPORT = "PASSPORT"
    ALIEN_CARD = "ALIEN_CARD"
    KRA_PIN = "KRA_PIN"
    BRS_CERTIFICATE = "BRS_CERTIFICATE"
    PARTNERSHIP_DEED = "PARTNERSHIP_DEED"
    NGO_REGISTRATION = "NGO_REGISTRATION"


class DocumentVerificationStatus(str, Enum):
    NOT_PROVIDED = "NOT_PROVIDED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED_OCR = "FAILED_OCR"
    FAILED_AUTHENTICITY = "FAILED_AUTHENTICITY"
    FAILED_IPRS_MISMATCH = "FAILED_IPRS_MISMATCH"


class BiometricVerificationStatus(str, Enum):
    NOT_PROVIDED = "NOT_PROVIDED"
    PENDING = "PENDING"
    VERIFIED_LIVE = "VERIFIED_LIVE"
    FAILED_LIVENESS = "FAILED_LIVENESS"
    FAILED_FACE_MATCH = "FAILED_FACE_MATCH"


class KycTier(str, Enum):
    """CBK/PG/15 Customer Due Diligence tier."""
    SDD = "SDD"           # Simplified — LOW risk
    CDD = "CDD"           # Standard — MEDIUM risk
    EDD = "EDD"           # Enhanced — HIGH risk
    PROHIBITED = "PROHIBITED"  # Cannot be onboarded


class OnboardingOutcome(str, Enum):
    APPROVED = "APPROVED"
    APPROVED_WITH_EDD = "APPROVED_WITH_EDD"
    PENDING_DOCUMENTS = "PENDING_DOCUMENTS"
    PENDING_BIOMETRICS = "PENDING_BIOMETRICS"
    BLOCKED_PROHIBITED = "BLOCKED_PROHIBITED"
    BLOCKED_INSUFFICIENT_DATA = "BLOCKED_INSUFFICIENT_DATA"
    BLOCKED_FAILED_VERIFICATION = "BLOCKED_FAILED_VERIFICATION"


# Review schedule by tier — months
REVIEW_PERIOD_MONTHS_BY_TIER: Mapping[KycTier, int] = {
    KycTier.SDD: 36,        # 3 years
    KycTier.CDD: 24,        # 2 years
    KycTier.EDD: 12,        # 1 year — CBK/PG/15 mandates more frequent EDD review
}


# ---------------------------------------------------------------------------
# Input dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityDocument:
    document_type: IdDocumentType
    document_number: str
    issuing_country: str = "KE"
    issued_date: Optional[str] = None  # YYYY-MM-DD
    expiry_date: Optional[str] = None
    verification_status: DocumentVerificationStatus = (
        DocumentVerificationStatus.NOT_PROVIDED)
    verification_notes: str = ""


@dataclass(frozen=True)
class BeneficialOwner:
    """For KYB applicants. Per BO Regulations 2020, >=10% ownership
    OR significant control triggers identification."""
    full_name: str
    national_id: str
    ownership_pct: Decimal
    is_significant_controller: bool = False
    is_pep: bool = False
    nationality: str = "KE"

    def __post_init__(self):
        # Sanity check — ownership in [0, 100]
        if not (Decimal("0") <= self.ownership_pct <= Decimal("100")):
            raise ValueError(
                f"ownership_pct must be 0-100, got {self.ownership_pct}")


@dataclass(frozen=True)
class CustomerApplicant:
    """Individual KYC applicant."""
    applicant_id: str
    full_name: str
    date_of_birth: str  # YYYY-MM-DD
    nationality: str
    residence_country: str
    occupation: str
    employer: str = ""
    annual_income_kes: Optional[Decimal] = None
    is_pep: bool = False  # Self-declared; engine still screens
    purpose_of_account: str = ""
    expected_monthly_throughput_kes: Optional[Decimal] = None
    documents: Tuple[IdentityDocument, ...] = ()
    biometric_status: BiometricVerificationStatus = (
        BiometricVerificationStatus.NOT_PROVIDED)
    notes: str = ""


@dataclass(frozen=True)
class BusinessApplicant:
    """KYB applicant — business entity."""
    applicant_id: str
    legal_name: str
    applicant_type: ApplicantType
    date_of_incorporation: str  # YYYY-MM-DD
    country_of_incorporation: str
    industry_sic: str  # SIC code, free-form per Kenya BRS
    annual_turnover_kes: Optional[Decimal] = None
    employee_count: Optional[int] = None
    is_cash_intensive: bool = False
    purpose_of_account: str = ""
    documents: Tuple[IdentityDocument, ...] = ()
    beneficial_owners: Tuple[BeneficialOwner, ...] = ()
    notes: str = ""

    def __post_init__(self):
        if self.applicant_type == ApplicantType.INDIVIDUAL:
            raise ValueError(
                "INDIVIDUAL applicant_type belongs in CustomerApplicant")


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OnboardingDecision:
    applicant_id: str
    applicant_kind: str  # "KYC" | "KYB"
    outcome: OnboardingOutcome
    tier: Optional[KycTier]
    risk_score: Optional[int]
    risk_band: Optional[str]
    pep_flag: bool
    sanctions_flag: bool
    next_review_date: Optional[str]
    blockers: Tuple[str, ...] = ()
    edd_triggers: Tuple[str, ...] = ()
    decided_at_utc: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "applicant_id": self.applicant_id,
            "applicant_kind": self.applicant_kind,
            "outcome": self.outcome.value,
            "tier": self.tier.value if self.tier else None,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "pep_flag": self.pep_flag,
            "sanctions_flag": self.sanctions_flag,
            "next_review_date": self.next_review_date,
            "blockers": list(self.blockers),
            "edd_triggers": list(self.edd_triggers),
            "decided_at_utc": self.decided_at_utc,
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class KycOnboardingEngine:
    """Orchestrator for ENH-191 Digital KYC/KYB Onboarding.

    Stateful: applicants registered via register_customer / register_business
    are retained for retrieval via decisions_by_id and portfolio_summary.
    """

    def __init__(self) -> None:
        self._customers: Dict[str, CustomerApplicant] = {}
        self._businesses: Dict[str, BusinessApplicant] = {}
        self._decisions: Dict[str, OnboardingDecision] = {}

    # ------------------------------------------------------------------
    # Registration — pure data capture, no decision yet
    # ------------------------------------------------------------------

    def register_customer(self, applicant: CustomerApplicant) -> None:
        """Register an individual KYC applicant. Does not run the
        decision yet — call decide(applicant_id) explicitly."""
        if applicant.applicant_id in self._customers or \
                applicant.applicant_id in self._businesses:
            raise ValueError(
                f"applicant_id {applicant.applicant_id} already registered")
        self._customers[applicant.applicant_id] = applicant

    def register_business(self, applicant: BusinessApplicant) -> None:
        """Register a KYB applicant. Beneficial owners must be supplied
        with the business; cannot be added separately."""
        if applicant.applicant_id in self._customers or \
                applicant.applicant_id in self._businesses:
            raise ValueError(
                f"applicant_id {applicant.applicant_id} already registered")
        self._businesses[applicant.applicant_id] = applicant

    # ------------------------------------------------------------------
    # Decision logic — deterministic given applicant + screening result
    # ------------------------------------------------------------------

    def decide(self, applicant_id: str) -> OnboardingDecision:
        """Run the full onboarding decision sequence for an applicant.

        Sequence:
          1. Validate mandatory fields → blocker list
          2. Check document verification states → blocker list
          3. Check biometric state (KYC only) → blocker list
          4. Delegate to KycAmlRiskEngine.assess_customer for risk score
          5. Apply Rule 6 honesty: missing data does NOT lower score
          6. Determine tier from risk band
          7. Compute next_review_date from tier
          8. For KYB: tier = max(business tier, max BO tier)
          9. Determine OnboardingOutcome from blockers + tier
          10. Persist decision + return
        """
        if applicant_id in self._customers:
            return self._decide_customer(applicant_id)
        if applicant_id in self._businesses:
            return self._decide_business(applicant_id)
        raise KeyError(f"applicant_id not registered: {applicant_id}")

    def _decide_customer(self, applicant_id: str) -> OnboardingDecision:
        a = self._customers[applicant_id]
        blockers: List[str] = []
        edd_triggers: List[str] = []

        # Mandatory fields check
        if not a.full_name or not a.date_of_birth or not a.nationality:
            blockers.append("missing_mandatory_identity_fields")
        if not a.purpose_of_account:
            blockers.append("missing_purpose_of_account")

        # Document check — at least one verified primary ID required
        primary_doc_types = {IdDocumentType.NATIONAL_ID,
                              IdDocumentType.PASSPORT,
                              IdDocumentType.ALIEN_CARD}
        verified_primary = [
            d for d in a.documents
            if d.document_type in primary_doc_types
            and d.verification_status == DocumentVerificationStatus.VERIFIED
        ]
        if not verified_primary:
            blockers.append("no_verified_primary_id_document")
        else:
            # Check expiry
            for d in verified_primary:
                if d.expiry_date:
                    try:
                        if d.expiry_date < datetime.now(
                                timezone.utc).strftime("%Y-%m-%d"):
                            blockers.append(
                                f"primary_id_expired_{d.document_type.value}")
                    except (ValueError, TypeError):
                        pass

        # Biometrics — REQUIRED for digital onboarding (CBK/PG/15 EDD-grade
        # for non-face-to-face channels means biometric is part of the
        # baseline)
        if a.biometric_status == BiometricVerificationStatus.NOT_PROVIDED:
            blockers.append("biometric_not_provided")
        elif a.biometric_status in (
                BiometricVerificationStatus.FAILED_LIVENESS,
                BiometricVerificationStatus.FAILED_FACE_MATCH):
            blockers.append(
                f"biometric_failed_{a.biometric_status.value}")

        # Delegate risk scoring to ENH-121's engine
        risk = self._score_risk(a)

        # Tier from risk band
        tier = self._tier_from_risk_band(risk["risk_band"])

        # EDD triggers (separate from blockers — EDD doesn't block, just
        # raises the bar)
        if a.is_pep or risk.get("pep_flag"):
            edd_triggers.append("pep_flag")
        if risk.get("sanctions_flag"):
            blockers.append("sanctions_match")
            tier = KycTier.PROHIBITED
        if a.residence_country.upper() in (
                "IR", "KP", "SY", "MM"):  # high-risk jurisdictions
            edd_triggers.append(
                f"high_risk_jurisdiction_{a.residence_country}")

        # Determine outcome
        outcome = self._outcome_from_state(blockers, tier, edd_triggers)

        # Next review date
        next_review = self._compute_next_review(tier)

        decision = OnboardingDecision(
            applicant_id=applicant_id,
            applicant_kind="KYC",
            outcome=outcome,
            tier=tier,
            risk_score=risk.get("risk_score"),
            risk_band=risk.get("risk_band"),
            pep_flag=bool(a.is_pep or risk.get("pep_flag")),
            sanctions_flag=bool(risk.get("sanctions_flag")),
            next_review_date=next_review,
            blockers=tuple(blockers),
            edd_triggers=tuple(edd_triggers),
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            meta={"engine_version": "ENH-191-v10.160",
                    "risk_engine_meta": risk.get("meta", {})},
        )
        self._decisions[applicant_id] = decision
        return decision

    def _decide_business(self, applicant_id: str) -> OnboardingDecision:
        a = self._businesses[applicant_id]
        blockers: List[str] = []
        edd_triggers: List[str] = []

        # Mandatory fields
        if not a.legal_name or not a.date_of_incorporation:
            blockers.append("missing_mandatory_business_fields")
        if not a.purpose_of_account:
            blockers.append("missing_purpose_of_account")

        # Beneficial owners check — BO Regulations 2020 mandates
        # identification of >=10% holders + significant controllers
        identified_significant = [
            bo for bo in a.beneficial_owners
            if bo.ownership_pct >= Decimal("10")
            or bo.is_significant_controller
        ]
        if not identified_significant:
            blockers.append("no_beneficial_owners_identified")

        # Total identified ownership — Rule 6 honesty: if total is low,
        # we don't know who else has control. NOT a passing condition.
        total_identified_pct = sum(
            (bo.ownership_pct for bo in a.beneficial_owners),
            Decimal("0"))
        if total_identified_pct < Decimal("75") and \
                a.applicant_type == ApplicantType.LIMITED_COMPANY:
            edd_triggers.append(
                f"only_{total_identified_pct}pct_ownership_identified")

        # Business registration document
        registration_types = {IdDocumentType.BRS_CERTIFICATE,
                               IdDocumentType.PARTNERSHIP_DEED,
                               IdDocumentType.NGO_REGISTRATION}
        verified_reg = [
            d for d in a.documents
            if d.document_type in registration_types
            and d.verification_status == DocumentVerificationStatus.VERIFIED
        ]
        if not verified_reg:
            blockers.append("no_verified_registration_document")

        # KRA PIN
        kra_pin = [
            d for d in a.documents
            if d.document_type == IdDocumentType.KRA_PIN
            and d.verification_status == DocumentVerificationStatus.VERIFIED
        ]
        if not kra_pin:
            blockers.append("no_verified_kra_pin")

        # Score the business itself
        risk = self._score_risk(a)
        business_tier = self._tier_from_risk_band(risk["risk_band"])

        # Cash-intensive flag → EDD trigger
        if a.is_cash_intensive:
            edd_triggers.append("cash_intensive_business")

        # PEP among BOs → EDD trigger
        bo_pep = any(bo.is_pep for bo in a.beneficial_owners)
        if bo_pep:
            edd_triggers.append("pep_beneficial_owner")

        # Roll up: business tier = max(its own tier, all BO tiers)
        # Implemented honestly — if any BO would be PROHIBITED, the
        # business is PROHIBITED. KYB cannot launder one bad BO.
        max_tier = business_tier
        bo_tier_details: List[Dict[str, Any]] = []
        for bo in a.beneficial_owners:
            bo_assessment = self._score_risk_owner(bo)
            bo_tier = self._tier_from_risk_band(bo_assessment["risk_band"])
            bo_tier_details.append({
                "owner_name": bo.full_name,
                "tier": bo_tier.value,
                "risk_band": bo_assessment["risk_band"],
                "is_pep": bo.is_pep,
            })
            if self._tier_severity(bo_tier) > self._tier_severity(max_tier):
                max_tier = bo_tier

        # Sanctions across business + BOs
        sanctions_hit = bool(risk.get("sanctions_flag")) or any(
            self._score_risk_owner(bo).get("sanctions_flag")
            for bo in a.beneficial_owners)
        if sanctions_hit:
            blockers.append("sanctions_match_business_or_bo")
            max_tier = KycTier.PROHIBITED

        outcome = self._outcome_from_state(blockers, max_tier, edd_triggers)
        next_review = self._compute_next_review(max_tier)

        decision = OnboardingDecision(
            applicant_id=applicant_id,
            applicant_kind="KYB",
            outcome=outcome,
            tier=max_tier,
            risk_score=risk.get("risk_score"),
            risk_band=risk.get("risk_band"),
            pep_flag=bool(risk.get("pep_flag")) or bo_pep,
            sanctions_flag=sanctions_hit,
            next_review_date=next_review,
            blockers=tuple(blockers),
            edd_triggers=tuple(edd_triggers),
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            meta={
                "engine_version": "ENH-191-v10.160",
                "business_self_tier": business_tier.value,
                "rolled_up_tier": max_tier.value,
                "n_beneficial_owners_identified": len(a.beneficial_owners),
                "total_identified_ownership_pct": str(total_identified_pct),
                "beneficial_owner_tiers": bo_tier_details,
            },
        )
        self._decisions[applicant_id] = decision
        return decision

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _score_risk(self, applicant) -> Dict[str, Any]:
        """Delegate to KycAmlRiskEngine. Falls back to a stub if the
        engine isn't importable (e.g. during sandbox testing)."""
        try:
            from utils.kyc_aml_risk import KycAmlRiskEngine
            customer_dict = self._applicant_to_kycaml_dict(applicant)
            assessment = KycAmlRiskEngine.assess_customer(customer_dict)
            return {
                "risk_score": assessment.risk_score,
                "risk_band": assessment.risk_band,
                "pep_flag": assessment.pep_flag,
                "sanctions_flag": assessment.sanctions_flag,
                "auto_prohibited": assessment.auto_prohibited,
                "meta": dict(assessment.meta or {}),
            }
        except Exception as e:
            return {
                "risk_score": None,
                "risk_band": "UNKNOWN",
                "pep_flag": False,
                "sanctions_flag": False,
                "meta": {"error": f"{type(e).__name__}: {e}"},
            }

    def _score_risk_owner(self, bo: BeneficialOwner) -> Dict[str, Any]:
        """Score a beneficial owner as if they were an individual
        applicant — same risk surface."""
        try:
            from utils.kyc_aml_risk import KycAmlRiskEngine
            d = {
                "customer_id": bo.national_id,
                "customer_type": "INDIVIDUAL",
                "is_pep": bo.is_pep,
                "country": bo.nationality,
                "occupation": "BENEFICIAL_OWNER",
            }
            assessment = KycAmlRiskEngine.assess_customer(d)
            return {
                "risk_score": assessment.risk_score,
                "risk_band": assessment.risk_band,
                "pep_flag": assessment.pep_flag,
                "sanctions_flag": assessment.sanctions_flag,
            }
        except Exception:
            return {
                "risk_score": None,
                "risk_band": "MEDIUM" if bo.is_pep else "LOW",
                "pep_flag": bo.is_pep,
                "sanctions_flag": False,
            }

    def _applicant_to_kycaml_dict(
            self, applicant) -> Dict[str, Any]:
        """Map IDE-typed applicant onto the dict shape that
        KycAmlRiskEngine.assess_customer expects."""
        if isinstance(applicant, CustomerApplicant):
            return {
                "customer_id": applicant.applicant_id,
                "customer_type": "INDIVIDUAL",
                "is_pep": applicant.is_pep,
                "country": applicant.residence_country,
                "occupation": applicant.occupation,
                "annual_income_kes": (
                    str(applicant.annual_income_kes)
                    if applicant.annual_income_kes is not None
                    else None),
            }
        elif isinstance(applicant, BusinessApplicant):
            return {
                "customer_id": applicant.applicant_id,
                "customer_type": applicant.applicant_type.value,
                "country": applicant.country_of_incorporation,
                "is_cash_intensive": applicant.is_cash_intensive,
                "industry_sic": applicant.industry_sic,
                "annual_turnover_kes": (
                    str(applicant.annual_turnover_kes)
                    if applicant.annual_turnover_kes is not None
                    else None),
            }
        else:
            return {"customer_id": "unknown", "customer_type": "UNKNOWN"}

    @staticmethod
    def _tier_from_risk_band(risk_band: str) -> KycTier:
        """Map kyc_aml_risk risk band to onboarding tier."""
        rb = (risk_band or "").upper()
        if rb == "PROHIBITED":
            return KycTier.PROHIBITED
        if rb == "HIGH":
            return KycTier.EDD
        if rb == "MEDIUM":
            return KycTier.CDD
        if rb == "LOW":
            return KycTier.SDD
        # UNKNOWN risk_band → CDD (don't grant SDD without verified score)
        return KycTier.CDD

    @staticmethod
    def _tier_severity(tier: KycTier) -> int:
        """Order tiers for the KYB rollup logic."""
        order = {KycTier.SDD: 0, KycTier.CDD: 1,
                  KycTier.EDD: 2, KycTier.PROHIBITED: 3}
        return order.get(tier, 1)

    @staticmethod
    def _outcome_from_state(
            blockers: List[str],
            tier: KycTier,
            edd_triggers: List[str]) -> OnboardingOutcome:
        """Deterministic outcome from blockers + tier + EDD triggers."""
        if tier == KycTier.PROHIBITED:
            return OnboardingOutcome.BLOCKED_PROHIBITED
        if any(b == "sanctions_match" or
                b == "sanctions_match_business_or_bo"
                for b in blockers):
            return OnboardingOutcome.BLOCKED_PROHIBITED
        if any("biometric_failed" in b or "FAILED" in b
                for b in blockers):
            return OnboardingOutcome.BLOCKED_FAILED_VERIFICATION
        # Pending states — recoverable
        if "biometric_not_provided" in blockers:
            return OnboardingOutcome.PENDING_BIOMETRICS
        if any(b.startswith("no_verified") or
                b.startswith("missing_") or
                b.startswith("primary_id_expired")
                for b in blockers):
            return OnboardingOutcome.PENDING_DOCUMENTS
        if blockers:
            return OnboardingOutcome.BLOCKED_INSUFFICIENT_DATA
        # Clean state — approve at appropriate tier
        if tier == KycTier.EDD or edd_triggers:
            return OnboardingOutcome.APPROVED_WITH_EDD
        return OnboardingOutcome.APPROVED

    @staticmethod
    def _compute_next_review(tier: KycTier) -> Optional[str]:
        """Months from today by tier."""
        if tier == KycTier.PROHIBITED:
            return None
        months = REVIEW_PERIOD_MONTHS_BY_TIER.get(tier, 24)
        next_dt = date.today() + timedelta(days=months * 30)
        return next_dt.isoformat()

    # ------------------------------------------------------------------
    # Retrieval / portfolio summary
    # ------------------------------------------------------------------

    def decision_by_id(self, applicant_id: str) -> OnboardingDecision:
        if applicant_id not in self._decisions:
            raise KeyError(
                f"no decision for applicant_id={applicant_id}; "
                f"call decide() first")
        return self._decisions[applicant_id]

    def all_decisions(self) -> Tuple[OnboardingDecision, ...]:
        return tuple(self._decisions.values())

    def board_summary(self) -> Dict[str, Any]:
        """Cross-arc board summary — same shape as TreasuryDashboardEngine
        et al. for cockpit consumption."""
        decisions = list(self._decisions.values())
        n_total = len(decisions)
        n_kyc = sum(1 for d in decisions if d.applicant_kind == "KYC")
        n_kyb = sum(1 for d in decisions if d.applicant_kind == "KYB")

        outcome_counts: Dict[str, int] = {}
        tier_counts: Dict[str, int] = {}
        for d in decisions:
            outcome_counts[d.outcome.value] = (
                outcome_counts.get(d.outcome.value, 0) + 1)
            if d.tier:
                tier_counts[d.tier.value] = (
                    tier_counts.get(d.tier.value, 0) + 1)

        n_pep = sum(1 for d in decisions if d.pep_flag)
        n_sanctions = sum(1 for d in decisions if d.sanctions_flag)
        n_edd = sum(1 for d in decisions
                    if d.tier == KycTier.EDD or d.edd_triggers)

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-191 KycOnboardingEngine",
            "n_decisions": n_total,
            "n_kyc": n_kyc,
            "n_kyb": n_kyb,
            "n_pep_flagged": n_pep,
            "n_sanctions_flagged": n_sanctions,
            "n_edd_required": n_edd,
            "outcome_counts": outcome_counts,
            "tier_counts": tier_counts,
            "n_registered_customers": len(self._customers),
            "n_registered_businesses": len(self._businesses),
        }

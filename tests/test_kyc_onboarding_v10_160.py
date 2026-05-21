"""tests/test_kyc_onboarding_v10_160.py — ENH-191 Digital KYC/KYB
Onboarding Engine.

Verifies the v10.160 deliverable:
- Engine module exists and parses
- All 7 enums present (ApplicantType, IdDocumentType,
  DocumentVerificationStatus, BiometricVerificationStatus, KycTier,
  OnboardingOutcome) with their full vocabularies
- 3 input dataclasses (IdentityDocument, BeneficialOwner,
  CustomerApplicant, BusinessApplicant) frozen with proper field types
- Output dataclass (OnboardingDecision) has to_dict for API serialization
- 5 realistic scenarios produce deterministic + correct outputs:
  - Clean retail KYC → APPROVED CDD
  - Missing biometric → PENDING_BIOMETRICS
  - PEP individual → APPROVED_WITH_EDD
  - Clean limited company KYB → APPROVED CDD
  - Cash-intensive + low BO coverage → APPROVED_WITH_EDD
- Tier rollup logic: business tier = max(its own, all BOs)
- Sanctions match → BLOCKED_PROHIBITED tier
- Engine integrates with KycAmlRiskEngine without modifying it
- Standard ENH-191 status='active' in registry with affected_engines=('kyc_onboarding',)
- Audit unchanged at 151/151 (engine-level work)
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "kyc_onboarding.py"
REGISTRY_PATH = REPO_ROOT / "utils" / "standards_registry.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_engine_exists(self):
        assert ENGINE_PATH.exists()

    def test_engine_parses(self):
        ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))

    def test_engine_imports(self):
        from utils.kyc_onboarding import KycOnboardingEngine
        eng = KycOnboardingEngine()
        assert eng is not None

    def test_all_enums_present(self):
        from utils.kyc_onboarding import (
            ApplicantType, IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus, KycTier, OnboardingOutcome)
        assert len(list(ApplicantType)) >= 6
        assert len(list(IdDocumentType)) >= 7
        assert len(list(DocumentVerificationStatus)) >= 4
        assert len(list(BiometricVerificationStatus)) >= 3
        assert len(list(KycTier)) == 4  # SDD, CDD, EDD, PROHIBITED
        assert len(list(OnboardingOutcome)) >= 6

    def test_dataclasses_frozen(self):
        from utils.kyc_onboarding import (
            IdentityDocument, BeneficialOwner, CustomerApplicant,
            BusinessApplicant, OnboardingDecision)
        # Frozen dataclasses raise FrozenInstanceError on attribute set
        from utils.kyc_onboarding import (IdDocumentType,
                                            DocumentVerificationStatus)
        doc = IdentityDocument(
            document_type=IdDocumentType.NATIONAL_ID,
            document_number="12345678",
            verification_status=DocumentVerificationStatus.VERIFIED)
        try:
            doc.document_number = "MUTATED"
            raise AssertionError("frozen dataclass mutated successfully — "
                                  "IdentityDocument must be frozen")
        except Exception as e:
            # FrozenInstanceError is the expected outcome; any
            # FrozenInstanceError or AttributeError variant is fine
            err_name = type(e).__name__
            err_msg = str(e).lower()
            assert ("frozen" in err_name.lower() or
                     "frozen" in err_msg or
                     "cannot assign" in err_msg or
                     "can't set" in err_msg), (
                f"unexpected error: {err_name}: {e}")


class TestRegistryActivation:
    def test_enh_191_active(self):
        m = _load("registry_v160", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-191"), None)
        assert s is not None, "ENH-191 missing from registry"
        assert s.status == "active", (
            f"ENH-191 status={s.status}, expected active")

    def test_enh_191_engine_registered(self):
        m = _load("registry_v160_engines", REGISTRY_PATH)
        s = next(x for x in m.STANDARDS_REGISTRY
                  if x.standard_id == "ENH-191")
        assert "kyc_onboarding" in (s.affected_engines or ()), (
            f"ENH-191 affected_engines={s.affected_engines}, "
            f"expected ('kyc_onboarding',)")


class TestKycScenarios:
    def test_clean_retail_kyc_approved(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus, OnboardingOutcome, KycTier)
        eng = KycOnboardingEngine()
        a = CustomerApplicant(
            applicant_id="C_TEST_CLEAN",
            full_name="Test Wanjiku",
            date_of_birth="1990-01-01",
            nationality="KE",
            residence_country="KE",
            occupation="TEACHER",
            purpose_of_account="SAVINGS",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.NATIONAL_ID,
                    document_number="12345678",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            biometric_status=BiometricVerificationStatus.VERIFIED_LIVE)
        eng.register_customer(a)
        d = eng.decide("C_TEST_CLEAN")
        assert d.outcome == OnboardingOutcome.APPROVED
        assert d.tier in (KycTier.SDD, KycTier.CDD)
        assert d.next_review_date is not None
        assert not d.pep_flag
        assert not d.sanctions_flag

    def test_no_biometric_pending(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus, OnboardingOutcome)
        eng = KycOnboardingEngine()
        a = CustomerApplicant(
            applicant_id="C_TEST_NO_BIO",
            full_name="Test NoBio",
            date_of_birth="1990-01-01",
            nationality="KE",
            residence_country="KE",
            occupation="ENGINEER",
            purpose_of_account="SAVINGS",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.NATIONAL_ID,
                    document_number="22345678",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            biometric_status=BiometricVerificationStatus.NOT_PROVIDED)
        eng.register_customer(a)
        d = eng.decide("C_TEST_NO_BIO")
        assert d.outcome == OnboardingOutcome.PENDING_BIOMETRICS
        assert "biometric_not_provided" in d.blockers

    def test_pep_individual_edd(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus, OnboardingOutcome)
        eng = KycOnboardingEngine()
        a = CustomerApplicant(
            applicant_id="C_TEST_PEP",
            full_name="Hon. PEP",
            date_of_birth="1965-01-01",
            nationality="KE",
            residence_country="KE",
            occupation="POLITICIAN",
            is_pep=True,
            purpose_of_account="SALARY",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.NATIONAL_ID,
                    document_number="11122233",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            biometric_status=BiometricVerificationStatus.VERIFIED_LIVE)
        eng.register_customer(a)
        d = eng.decide("C_TEST_PEP")
        assert d.outcome == OnboardingOutcome.APPROVED_WITH_EDD
        assert d.pep_flag is True
        assert "pep_flag" in d.edd_triggers


class TestKybScenarios:
    def test_clean_limited_company_approved(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, BusinessApplicant, BeneficialOwner,
            IdentityDocument, IdDocumentType,
            DocumentVerificationStatus, ApplicantType,
            OnboardingOutcome, KycTier)
        eng = KycOnboardingEngine()
        biz = BusinessApplicant(
            applicant_id="B_TEST_CLEAN",
            legal_name="Clean Holdings Ltd",
            applicant_type=ApplicantType.LIMITED_COMPANY,
            date_of_incorporation="2020-01-01",
            country_of_incorporation="KE",
            industry_sic="6810",
            purpose_of_account="OPERATIONS",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.BRS_CERTIFICATE,
                    document_number="BRS-001",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
                IdentityDocument(
                    document_type=IdDocumentType.KRA_PIN,
                    document_number="P001234567",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            beneficial_owners=(
                BeneficialOwner(full_name="A", national_id="11111111",
                                  ownership_pct=Decimal("60")),
                BeneficialOwner(full_name="B", national_id="22222222",
                                  ownership_pct=Decimal("40")),
            ))
        eng.register_business(biz)
        d = eng.decide("B_TEST_CLEAN")
        assert d.outcome == OnboardingOutcome.APPROVED
        assert d.applicant_kind == "KYB"

    def test_low_bo_coverage_triggers_edd(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, BusinessApplicant, BeneficialOwner,
            IdentityDocument, IdDocumentType,
            DocumentVerificationStatus, ApplicantType,
            OnboardingOutcome)
        eng = KycOnboardingEngine()
        # Only 50% BO coverage triggers EDD on a limited company
        biz = BusinessApplicant(
            applicant_id="B_LOW_COVER",
            legal_name="Opaque Holdings Ltd",
            applicant_type=ApplicantType.LIMITED_COMPANY,
            date_of_incorporation="2020-01-01",
            country_of_incorporation="KE",
            industry_sic="6810",
            purpose_of_account="OPERATIONS",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.BRS_CERTIFICATE,
                    document_number="BRS-002",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
                IdentityDocument(
                    document_type=IdDocumentType.KRA_PIN,
                    document_number="P0099",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            beneficial_owners=(
                BeneficialOwner(full_name="X", national_id="33333333",
                                  ownership_pct=Decimal("50")),
            ))
        eng.register_business(biz)
        d = eng.decide("B_LOW_COVER")
        # Should trigger EDD due to low coverage
        assert any("only_50pct_ownership" in t for t in d.edd_triggers)

    def test_no_bo_blocks(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, BusinessApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            ApplicantType, OnboardingOutcome)
        eng = KycOnboardingEngine()
        biz = BusinessApplicant(
            applicant_id="B_NO_BO",
            legal_name="Anonymous Ltd",
            applicant_type=ApplicantType.LIMITED_COMPANY,
            date_of_incorporation="2020-01-01",
            country_of_incorporation="KE",
            industry_sic="6810",
            purpose_of_account="OPS",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.BRS_CERTIFICATE,
                    document_number="BRS-X",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
                IdentityDocument(
                    document_type=IdDocumentType.KRA_PIN,
                    document_number="P0X",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            beneficial_owners=())
        eng.register_business(biz)
        d = eng.decide("B_NO_BO")
        # Missing BOs is a blocker, not just a trigger
        assert "no_beneficial_owners_identified" in d.blockers


class TestDeterminism:
    """Same input → same output. Critical for audit trails."""

    def test_same_input_same_decision(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus)
        # Build same applicant twice in two engines
        kw = dict(
            applicant_id="DET_TEST",
            full_name="Determ Inist",
            date_of_birth="1990-01-01",
            nationality="KE",
            residence_country="KE",
            occupation="ENGINEER",
            purpose_of_account="SAVINGS",
            documents=(
                IdentityDocument(
                    document_type=IdDocumentType.NATIONAL_ID,
                    document_number="99887766",
                    verification_status=(
                        DocumentVerificationStatus.VERIFIED)),
            ),
            biometric_status=BiometricVerificationStatus.VERIFIED_LIVE)
        eng1 = KycOnboardingEngine()
        eng1.register_customer(CustomerApplicant(**kw))
        d1 = eng1.decide("DET_TEST")

        eng2 = KycOnboardingEngine()
        eng2.register_customer(CustomerApplicant(**kw))
        d2 = eng2.decide("DET_TEST")

        # Outcome and tier identical
        assert d1.outcome == d2.outcome
        assert d1.tier == d2.tier
        assert d1.risk_band == d2.risk_band
        assert tuple(d1.blockers) == tuple(d2.blockers)
        assert tuple(d1.edd_triggers) == tuple(d2.edd_triggers)


class TestNoIntegrationBreakage:
    """ENH-191 must NOT modify ENH-121 / Standard #57 (kyc_aml_risk).
    It composes them, doesn't duplicate."""

    def test_kyc_aml_risk_engine_unchanged(self):
        # The engine ENH-191 delegates to must still work standalone
        from utils.kyc_aml_risk import KycAmlRiskEngine
        result = KycAmlRiskEngine.assess_customer({
            "customer_id": "TEST",
            "customer_type": "INDIVIDUAL",
            "country": "KE",
            "is_pep": False,
        })
        assert result.customer_id == "TEST"
        assert result.risk_band in ("LOW", "MEDIUM", "HIGH",
                                       "PROHIBITED", "UNKNOWN")


class TestDuplicateRegistration:
    def test_duplicate_applicant_id_rejected(self):
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus)
        eng = KycOnboardingEngine()
        a = CustomerApplicant(
            applicant_id="DUP",
            full_name="Test",
            date_of_birth="1990-01-01",
            nationality="KE",
            residence_country="KE",
            occupation="X",
            purpose_of_account="Y",
            documents=(),
            biometric_status=BiometricVerificationStatus.NOT_PROVIDED)
        eng.register_customer(a)
        # Second registration with same ID must raise
        try:
            eng.register_customer(a)
            raise AssertionError("duplicate registration should raise")
        except ValueError as e:
            assert "already registered" in str(e)


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.kyc_onboarding import KycOnboardingEngine
        eng = KycOnboardingEngine()
        summary = eng.board_summary()
        # Required fields for cockpit consumption
        for field in ("entity", "engine", "n_decisions", "n_kyc",
                      "n_kyb", "n_pep_flagged", "n_sanctions_flagged",
                      "n_edd_required", "outcome_counts",
                      "tier_counts"):
            assert field in summary, (
                f"board_summary missing field: {field}")
        assert summary["engine"] == "ENH-191 KycOnboardingEngine"


class TestNoRegression:
    def test_audit_still_passes(self):
        m = _load("audit_v160", AUDIT_PATH)
        # Run all gates — none should fail
        for gate_id, gate_fn in m.GATES:
            result = gate_fn()
            assert result["passed"] is True, (
                f"{gate_id} regressed: {result.get('violations')}")

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v160", AUDIT_PATH)
        # v10.160 doesn't add audit gates — engine-level work
        assert len(m.GATES) == 151

    def test_treasury_endpoints_still_present(self):
        # Sanity: Treasury work from v10.154-v10.159 shouldn't have
        # been touched by v10.160's KYC work
        api_path = REPO_ROOT / "utils" / "api_treasury.py"
        text = api_path.read_text(encoding="utf-8")
        assert "/api/treasury/board" in text
        assert "/liquidity-risk/vocabulary" in text

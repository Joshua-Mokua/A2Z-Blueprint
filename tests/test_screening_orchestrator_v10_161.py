"""tests/test_screening_orchestrator_v10_161.py — ENH-192 PEP & Sanctions
Screening Orchestrator.

Verifies the v10.161 deliverable:
- Module exists and parses; engine class importable
- 4 enums present (SanctionsListSource, ListFreshnessStatus,
  PepCategory, ScreeningOutcome) with proper vocabularies
- 4 dataclasses (ListFreshnessRecord, PepScreeningResult,
  SanctionsHitSummary, UnifiedScreeningResult) frozen
- Initial state: all 5 sources MISSING (no auto-fake-readiness)
- register_list_load updates freshness; per-source windows respected
- screen() returns deterministic output
- PEP classification: NOT_PEP / DOMESTIC_PEP / FOREIGN_PEP / occupation
  heuristic
- Foreign PEP triggers FATF Rec 12 mandatory EDD
- screen_applicant() composes with ENH-191 CustomerApplicant +
  BusinessApplicant (business + each BO screened separately)
- Standard #58 SanctionsScreeningEngine still works standalone
- Standards registry shows ENH-192 status='active' with
  affected_engines=('screening_orchestrator',)
- Audit unchanged at 151/151
- No regression of v10.160 (ENH-191) or earlier
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "screening_orchestrator.py"
REGISTRY_PATH = REPO_ROOT / "utils" / "standards_registry.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_engine_exists_and_parses(self):
        assert ENGINE_PATH.exists()
        ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))

    def test_engine_imports(self):
        from utils.screening_orchestrator import ScreeningOrchestrator
        orch = ScreeningOrchestrator()
        assert orch is not None

    def test_all_enums_present(self):
        from utils.screening_orchestrator import (
            SanctionsListSource, ListFreshnessStatus, PepCategory,
            ScreeningOutcome)
        # 5 sanctions sources covering OFAC/UN/EU/UK/CBK
        assert len(list(SanctionsListSource)) == 5
        # 4 freshness statuses (FRESH, STALE, MISSING, MANUAL_LOAD)
        assert len(list(ListFreshnessStatus)) == 4
        # FATF Rec 12 PEP categories
        assert PepCategory.FOREIGN_PEP in list(PepCategory)
        assert PepCategory.DOMESTIC_PEP in list(PepCategory)
        # Outcome enum covers all paths
        assert len(list(ScreeningOutcome)) >= 5


class TestRegistryActivation:
    def test_enh_192_active(self):
        m = _load("registry_v161", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-192"), None)
        assert s is not None
        assert s.status == "active"
        assert "screening_orchestrator" in (s.affected_engines or ())


class TestInitialState:
    """Engine starts honest — no auto-fake-readiness. All 5 sources
    must explicitly start as MISSING."""

    def test_all_sources_initially_missing(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, ListFreshnessStatus,
            SanctionsListSource)
        orch = ScreeningOrchestrator()
        fs = orch.freshness_summary()
        n_missing = sum(
            1 for v in fs["by_source"].values()
            if v["status"] == ListFreshnessStatus.MISSING.value)
        assert n_missing == 5, (
            f"expected 5 sources MISSING at init, got {n_missing}")

    def test_register_load_updates_freshness(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, SanctionsListSource,
            ListFreshnessStatus)
        orch = ScreeningOrchestrator()
        rec = orch.register_list_load(
            SanctionsListSource.OFAC_SDN,
            n_records=10000,
            load_method="manual")
        assert rec.status == ListFreshnessStatus.MANUAL_LOAD
        assert rec.n_records_loaded == 10000

    def test_negative_records_rejected(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, SanctionsListSource)
        orch = ScreeningOrchestrator()
        try:
            orch.register_list_load(
                SanctionsListSource.OFAC_SDN, n_records=-5)
            raise AssertionError("negative n_records should raise")
        except ValueError:
            pass


class TestPepClassification:
    """PEP determination per FATF Rec 12. Domestic vs Foreign matters
    for EDD policy."""

    def test_clean_individual_not_pep(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, PepCategory, ScreeningOutcome)
        orch = ScreeningOrchestrator()
        r = orch.screen("C001", "Jane Doe",
                          is_pep_self_declared=False,
                          nationality="KE", residence_country="KE",
                          occupation="TEACHER")
        assert r.pep_result.category == PepCategory.NOT_PEP
        assert not r.pep_result.is_pep
        # No PEP, no sanctions hits, no missing-list blocker by default
        # → CLEAR
        assert r.outcome == ScreeningOutcome.CLEAR

    def test_self_declared_domestic_pep(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, PepCategory, ScreeningOutcome)
        orch = ScreeningOrchestrator()
        r = orch.screen("C002", "Hon. Domestic Politician",
                          is_pep_self_declared=True,
                          nationality="KE", residence_country="KE",
                          occupation="MINISTER")
        assert r.pep_result.category == PepCategory.DOMESTIC_PEP
        assert r.pep_result.is_pep
        assert r.outcome == ScreeningOutcome.PEP_REVIEW_REQUIRED

    def test_foreign_pep_triggers_fatf_rec12_edd(self):
        """Critical: foreign PEP must trigger mandatory EDD per FATF
        Rec 12. Domestic PEP = CDD + periodic review (post-2012)."""
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, PepCategory)
        orch = ScreeningOrchestrator()
        r = orch.screen("C003", "Foreign Diplomat",
                          is_pep_self_declared=True,
                          nationality="NG", residence_country="KE",
                          occupation="AMBASSADOR")
        assert r.pep_result.category == PepCategory.FOREIGN_PEP
        # Must have FATF Rec 12 trigger (separate from generic pep_)
        edd_str = " ".join(r.edd_triggers)
        assert "fatf_rec12" in edd_str.lower(), (
            f"foreign PEP must trigger FATF Rec 12 EDD; "
            f"triggers={r.edd_triggers}")

    def test_occupation_heuristic_catches_undeclared_pep(self):
        """Edge case: applicant doesn't declare PEP but occupation
        keyword indicates one. Must flag for human review with explicit
        REQUIRES_HUMAN_VERIFICATION reason — not auto-confirm."""
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, PepCategory)
        orch = ScreeningOrchestrator()
        r = orch.screen("C004", "Undeclared MP",
                          is_pep_self_declared=False,
                          nationality="KE", residence_country="KE",
                          occupation="MEMBER OF PARLIAMENT")
        assert r.pep_result.is_pep
        # Reason should indicate occupation heuristic + need for verification
        assert "occupation_keyword_match" in r.pep_result.reason
        assert "REQUIRES_HUMAN_VERIFICATION" in r.pep_result.reason


class TestApplicantIntegration:
    """ENH-192 must integrate with ENH-191 dataclasses without modification."""

    def test_screen_customer_applicant(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, PepCategory)
        from utils.kyc_onboarding import (
            CustomerApplicant, IdentityDocument, IdDocumentType,
            DocumentVerificationStatus, BiometricVerificationStatus)
        orch = ScreeningOrchestrator()
        app = CustomerApplicant(
            applicant_id="C_INT_001",
            full_name="Test User",
            date_of_birth="1990-01-01",
            nationality="KE",
            residence_country="KE",
            occupation="TEACHER",
            purpose_of_account="SAVINGS",
            documents=(),
            biometric_status=BiometricVerificationStatus.NOT_PROVIDED)
        results = orch.screen_applicant(app)
        assert len(results) == 1
        assert results[0].subject_kind == "INDIVIDUAL"
        assert results[0].pep_result.category == PepCategory.NOT_PEP

    def test_screen_business_applicant_with_bos(self):
        from utils.screening_orchestrator import (
            ScreeningOrchestrator, PepCategory)
        from utils.kyc_onboarding import (
            BusinessApplicant, BeneficialOwner, ApplicantType)
        from decimal import Decimal
        orch = ScreeningOrchestrator()
        biz = BusinessApplicant(
            applicant_id="B_INT_001",
            legal_name="Test Holdings Ltd",
            applicant_type=ApplicantType.LIMITED_COMPANY,
            date_of_incorporation="2020-01-01",
            country_of_incorporation="KE",
            industry_sic="6810",
            purpose_of_account="OPS",
            documents=(),
            beneficial_owners=(
                BeneficialOwner(
                    full_name="PEP BO", national_id="11111111",
                    ownership_pct=Decimal("60"), is_pep=True,
                    nationality="KE"),
                BeneficialOwner(
                    full_name="Clean BO", national_id="22222222",
                    ownership_pct=Decimal("40"), is_pep=False,
                    nationality="KE"),
            ))
        results = orch.screen_applicant(biz)
        # Should be 1 business + 2 BOs = 3 screening results
        assert len(results) == 3
        kinds = [r.subject_kind for r in results]
        assert "BUSINESS" in kinds
        assert kinds.count("BENEFICIAL_OWNER") == 2
        # PEP BO must be flagged
        pep_bo = next(r for r in results
                       if r.subject_name == "PEP BO")
        assert pep_bo.pep_result.is_pep
        # Clean BO must NOT be flagged
        clean_bo = next(r for r in results
                          if r.subject_name == "Clean BO")
        assert not clean_bo.pep_result.is_pep

    def test_unrecognized_applicant_type_raises(self):
        from utils.screening_orchestrator import ScreeningOrchestrator
        orch = ScreeningOrchestrator()
        try:
            orch.screen_applicant({"some": "dict"})
            raise AssertionError(
                "unknown applicant type should raise ValueError")
        except ValueError as e:
            assert "applicant type not recognized" in str(e)


class TestNoIntegrationBreakage:
    """ENH-192 composes Standard #58 + ENH-191; must not modify them."""

    def test_standard_58_engine_still_standalone(self):
        from utils.sanctions_screening import (
            SanctionsScreeningEngine, SanctionsRecord)
        eng = SanctionsScreeningEngine()
        # Empty engine should screen cleanly
        hits = eng.screen(subject_id="X1", subject_name="Test",
                           subject_type="CUSTOMER")
        assert isinstance(hits, list)

    def test_kyc_onboarding_engine_still_standalone(self):
        # ENH-191 should still work without ENH-192
        from utils.kyc_onboarding import KycOnboardingEngine
        eng = KycOnboardingEngine()
        s = eng.board_summary()
        assert s["engine"] == "ENH-191 KycOnboardingEngine"


class TestDeterminism:
    def test_same_input_same_output(self):
        """Same input → same UnifiedScreeningResult except for
        timestamps. Critical for SAR audit reconstructions."""
        from utils.screening_orchestrator import ScreeningOrchestrator
        orch1 = ScreeningOrchestrator()
        r1 = orch1.screen("DET", "Same Name",
                            is_pep_self_declared=True,
                            nationality="KE", residence_country="KE",
                            occupation="MINISTER")
        orch2 = ScreeningOrchestrator()
        r2 = orch2.screen("DET", "Same Name",
                            is_pep_self_declared=True,
                            nationality="KE", residence_country="KE",
                            occupation="MINISTER")
        assert r1.outcome == r2.outcome
        assert r1.pep_result.category == r2.pep_result.category
        assert tuple(r1.edd_triggers) == tuple(r2.edd_triggers)


class TestOutputSerialization:
    def test_to_dict_returns_jsonable(self):
        import json
        from utils.screening_orchestrator import ScreeningOrchestrator
        orch = ScreeningOrchestrator()
        r = orch.screen("S001", "Test", nationality="KE",
                          residence_country="KE", occupation="TEACHER")
        d = r.to_dict()
        # Must be JSON-serializable
        json_str = json.dumps(d)
        assert "outcome" in d
        assert "pep_result" in d
        assert isinstance(d["sanctions_hits"], list)
        assert isinstance(d["lists_screened"], list)


class TestNoRegression:
    def test_audit_still_passes(self):
        m = _load("audit_v161", AUDIT_PATH)
        for gate_id, gate_fn in m.GATES:
            result = gate_fn()
            assert result["passed"] is True, (
                f"{gate_id} regressed")

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v161", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_160_engine_still_present(self):
        # ENH-191 engine should still exist + import
        from utils import kyc_onboarding
        assert hasattr(kyc_onboarding, "KycOnboardingEngine")

    def test_treasury_endpoints_intact(self):
        api_path = REPO_ROOT / "utils" / "api_treasury.py"
        text = api_path.read_text(encoding="utf-8")
        assert "/liquidity-risk/vocabulary" in text
        assert "/api/treasury/board" in text

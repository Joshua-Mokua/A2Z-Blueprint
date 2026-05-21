"""tests/test_examiner_reporting_v10_165.py — ENH-199 Examiner-Ready
Reporting Portal.

Verifies the v10.165 deliverable:
- Engine module exists, parses, imports
- 3 enums (ExaminationModuleType 8 values, ModuleStatus 4 values,
  PackageStatus 3 values)
- 2 frozen output dataclasses (ExaminationModule, ExaminationPackage)
- build_package assembles 8 modules across 5 upstream engines + 2
  deferred + 1 evidence index
- Missing engines surface as EMPTY_NO_DATA with finding (Rule 6)
- Independent Testing + Training modules always DEFERRED (correct)
- Evidence Index module cross-references customers across engines
- Findings list contains regulator-grade narrative
- Honest deferral surface: export_format_status STRUCTURED_JSON
- Standard ENH-199 status='active' in registry
- Audit unchanged at 151/151
- No regression of v10.160-v10.164 work
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "examiner_reporting.py"
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
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        assert eng is not None

    def test_enums_present(self):
        from utils.examiner_reporting import (
            ExaminationModuleType, ModuleStatus, PackageStatus)
        assert len(list(ExaminationModuleType)) == 8
        assert len(list(ModuleStatus)) == 4
        assert len(list(PackageStatus)) == 3

    def test_module_type_vocabulary(self):
        from utils.examiner_reporting import ExaminationModuleType
        names = {t.value for t in ExaminationModuleType}
        for required in ("CUSTOMER_DUE_DILIGENCE", "SCREENING",
                          "TRANSACTION_MONITORING",
                          "SAR_STR_FILING", "ENTERPRISE_RISK",
                          "EVIDENCE_INDEX", "INDEPENDENT_TESTING",
                          "TRAINING"):
            assert required in names

    def test_dataclasses_frozen(self):
        from utils.examiner_reporting import (
            ExaminationModule, ExaminationModuleType, ModuleStatus)
        m = ExaminationModule(
            module_type=ExaminationModuleType.CDD,
            status=ModuleStatus.POPULATED,
            summary_metrics={}, artifacts=(), findings=(),
            source_engines=())
        try:
            m.module_type = ExaminationModuleType.SCREENING
            raise AssertionError("frozen dataclass mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_199_active(self):
        m = _load("registry_v165", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-199"), None)
        assert s is not None
        assert s.status == "active"
        assert "examiner_reporting" in (s.affected_engines or ())


class TestBuildPackageNoEngines:
    """Rule 6: with no engines wired, modules surface as EMPTY_NO_DATA
    or DEFERRED — no fabricated examination evidence."""

    def test_empty_engines_produce_8_modules(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ModuleStatus)
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="Test Bank",
            period_start="2026-01-01",
            period_end="2026-03-31")
        # All 8 module types should be present even with no engines
        assert len(p.modules) == 8

    def test_no_engines_modules_empty_or_deferred(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ModuleStatus)
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="Test Bank",
            period_start="2026-01-01",
            period_end="2026-03-31")
        for m in p.modules:
            assert m.status in (ModuleStatus.EMPTY_NO_DATA,
                                  ModuleStatus.DEFERRED)

    def test_independent_testing_always_deferred(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ModuleStatus,
            ExaminationModuleType)
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="X", period_start="2026-01-01",
            period_end="2026-03-31")
        it = next(m for m in p.modules
                   if m.module_type ==
                      ExaminationModuleType.INDEPENDENT_TESTING)
        assert it.status == ModuleStatus.DEFERRED
        assert "ENH-201" in it.deferred_reason

    def test_training_always_deferred(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ModuleStatus,
            ExaminationModuleType)
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="X", period_start="2026-01-01",
            period_end="2026-03-31")
        tr = next(m for m in p.modules
                   if m.module_type ==
                      ExaminationModuleType.TRAINING)
        assert tr.status == ModuleStatus.DEFERRED
        assert "ENH-197" in tr.deferred_reason


class TestBuildPackageRequiredFields:
    def test_empty_institution_rejected(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        try:
            eng.build_package(
                institution_name="",
                period_start="2026-01-01",
                period_end="2026-03-31")
            raise AssertionError(
                "empty institution_name should raise")
        except ValueError as e:
            assert "institution_name" in str(e)

    def test_missing_period_rejected(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        try:
            eng.build_package(
                institution_name="X",
                period_start="",
                period_end="2026-03-31")
            raise AssertionError("empty period should raise")
        except ValueError as e:
            assert "period" in str(e).lower()


class TestBuildPackageWithEngines:
    """The headline integration test — full pipeline producing a
    populated examination package."""

    def _build_full_pipeline(self):
        from datetime import datetime
        from decimal import Decimal as _Dec
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus)
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.transaction_monitoring import Transaction
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity,
                                        FilingStatus)
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)

        kyc = KycOnboardingEngine()
        kyc.register_customer(CustomerApplicant(
            applicant_id="X1", full_name="Test",
            date_of_birth="1990-01-01", nationality="KE",
            residence_country="KE", occupation="ENGINEER",
            purpose_of_account="SAVINGS",
            documents=(IdentityDocument(
                document_type=IdDocumentType.NATIONAL_ID,
                document_number="1",
                verification_status=(
                    DocumentVerificationStatus.VERIFIED)),),
            biometric_status=(
                BiometricVerificationStatus.VERIFIED_LIVE)))
        kyc.decide("X1")

        aml = AmlMonitoringEngine()
        aml.monitor_customer("X1", [Transaction(
            txn_id="T1", customer_id="X1", account_id="A1",
            amount_kes=_Dec("50000"),
            txn_type="MOBILE_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))],
            customer_tier="CDD")

        sar = SarFilingEngine()
        cra = ComplianceRiskAssessmentEngine()
        cra.assess(kyc_engine=kyc, aml_engine=aml, sar_engine=sar)
        return kyc, aml, sar, cra

    def test_full_pipeline_produces_populated_package(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ModuleStatus,
            ExaminationModuleType)
        kyc, aml, sar, cra = self._build_full_pipeline()
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="Ecobank Kenya",
            period_start="2026-01-01", period_end="2026-03-31",
            kyc_engine=kyc, aml_engine=aml, sar_engine=sar,
            cra_engine=cra)

        # CDD should be POPULATED
        cdd = next(m for m in p.modules
                    if m.module_type ==
                       ExaminationModuleType.CDD)
        assert cdd.status == ModuleStatus.POPULATED
        assert cdd.summary_metrics["n_decisions"] >= 1

        # Transaction Monitoring POPULATED
        tm = next(m for m in p.modules
                   if m.module_type ==
                      ExaminationModuleType.TRANSACTION_MONITORING)
        assert tm.status == ModuleStatus.POPULATED

        # Enterprise Risk POPULATED
        er = next(m for m in p.modules
                   if m.module_type ==
                      ExaminationModuleType.ENTERPRISE_RISK)
        assert er.status == ModuleStatus.POPULATED
        assert "latest_total_score" in er.summary_metrics

        # Evidence Index should cross-reference engines
        ei = next(m for m in p.modules
                   if m.module_type ==
                      ExaminationModuleType.EVIDENCE_INDEX)
        assert ei.status == ModuleStatus.POPULATED
        assert ei.summary_metrics["n_customers_indexed"] >= 1

    def test_findings_contain_narrative(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ExaminationModuleType)
        kyc, aml, sar, cra = self._build_full_pipeline()
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="Ecobank Kenya",
            period_start="2026-01-01", period_end="2026-03-31",
            kyc_engine=kyc, aml_engine=aml, sar_engine=sar,
            cra_engine=cra)
        # CDD findings should contain the decision count
        cdd = next(m for m in p.modules
                    if m.module_type == ExaminationModuleType.CDD)
        assert any("CDD decisions" in f for f in cdd.findings)


class TestEvidenceIndex:
    """The audit-trail module cross-references customers across all
    engines."""

    def test_indexes_customer_across_3_engines(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ExaminationModuleType,
            ModuleStatus)
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus)
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.transaction_monitoring import Transaction
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity,
                                        FilingStatus)

        # Build pipeline where customer SHARED across engines
        kyc = KycOnboardingEngine()
        kyc.register_customer(CustomerApplicant(
            applicant_id="C1", full_name="Test",
            date_of_birth="1990-01-01", nationality="KE",
            residence_country="KE", occupation="X",
            purpose_of_account="Y",
            documents=(IdentityDocument(
                document_type=IdDocumentType.NATIONAL_ID,
                document_number="1",
                verification_status=(
                    DocumentVerificationStatus.VERIFIED)),),
            biometric_status=(
                BiometricVerificationStatus.VERIFIED_LIVE)))
        kyc.decide("C1")

        aml = AmlMonitoringEngine()
        aml.monitor_customer("C1", [Transaction(
            txn_id="T", customer_id="C1", account_id="A",
            amount_kes=Decimal("1500000"),
            txn_type="CASH_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))],
            customer_tier="EDD")

        sar = SarFilingEngine()
        f = sar.build_filing(
            monitoring_result=aml.result_by_customer("C1"),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[],
            suspicion_narrative="x" * 50)

        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="X",
            period_start="2026-01-01", period_end="2026-03-31",
            kyc_engine=kyc, aml_engine=aml, sar_engine=sar)

        ei = next(m for m in p.modules
                   if m.module_type ==
                      ExaminationModuleType.EVIDENCE_INDEX)
        assert ei.status == ModuleStatus.POPULATED
        # C1 should have entries from all 3 engines
        c1_entry = next(a for a in ei.artifacts
                          if a["customer_id"] == "C1")
        assert "kyc_decisions" in c1_entry
        assert "aml_results" in c1_entry
        assert "sar_filings" in c1_entry


class TestHonestDeferral:
    def test_export_format_status_explicit(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="X",
            period_start="2026-01-01",
            period_end="2026-03-31")
        assert "STRUCTURED_JSON" in p.export_format_status
        assert "operator-side" in p.export_format_status

    def test_two_modules_always_deferred(self):
        from utils.examiner_reporting import (
            ExaminerReportingEngine, ModuleStatus)
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="X",
            period_start="2026-01-01",
            period_end="2026-03-31")
        n_deferred = sum(1 for m in p.modules
                         if m.status == ModuleStatus.DEFERRED)
        assert n_deferred == 2  # IT + Training
        assert len(p.deferred_modules) == 2


class TestPortfolioSummary:
    def test_empty_summary_shape(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        s = eng.board_summary()
        assert s["engine"] == "ENH-199 ExaminerReportingEngine"
        assert s["n_packages"] == 0
        assert "regulatory_basis" in s

    def test_post_build_summary(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        eng.build_package(
            institution_name="X",
            period_start="2026-01-01",
            period_end="2026-03-31")
        s = eng.board_summary()
        assert s["n_packages"] == 1
        assert "latest_package_id" in s

    def test_to_dict_full_serialization(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        p = eng.build_package(
            institution_name="X",
            period_start="2026-01-01",
            period_end="2026-03-31")
        d = p.to_dict()
        for f in ("package_id", "institution_name", "modules",
                   "cluster_health_summary", "deferred_modules",
                   "upstream_engines", "export_format_status"):
            assert f in d
        # modules array should contain dicts with full structure
        assert len(d["modules"]) == 8
        for m in d["modules"]:
            assert "module_type" in m
            assert "status" in m
            assert "findings" in m


class TestNoRegression:
    def test_audit_still_passes(self):
        m = _load("audit_v165", AUDIT_PATH)
        for gate_id, gate_fn in m.GATES:
            result = gate_fn()
            assert result["passed"] is True

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v165", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_164_compliance_risk_still_works(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-198 ComplianceRiskAssessmentEngine")

    def test_v10_163_sar_filing_still_works(self):
        from utils.sar_filing import SarFilingEngine
        eng = SarFilingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-194 SarFilingEngine")

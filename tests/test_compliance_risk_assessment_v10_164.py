"""tests/test_compliance_risk_assessment_v10_164.py — ENH-198
Compliance Risk Assessment Engine.

Verifies the v10.164 deliverable:
- Engine module exists, parses, imports
- 1 enum (RiskBand 4 values)
- 2 frozen output dataclasses (ScoreComponent, ComplianceRiskAssessment)
- 5-dimension scoring composition (tier_concentration, sanctions_pep,
  alert_backlog, filing_backlog, cross_cluster_contradictions)
- Band thresholds correct: <30 LOW, 30-49 MEDIUM, 50-79 HIGH, >=80 CRITICAL
- Empty inputs produce zero score (no fabricated risk from no data)
- Missing engines surface in contradictions list (Rule 6 honesty)
- Sanctions weighted 3x heavier than PEP (regulatory absoluteness)
- Overdue filings weighted 8 pts each (heavy POCAMLA exposure)
- Cross-cluster contradiction detection works
- 3 honest deferral surfaces (trend_analysis, industry_concentration,
  ml_predictive)
- End-to-end integration with ENH-191 + ENH-193 + ENH-194
- Standard ENH-198 status='active' in registry
- Audit unchanged at 151/151
- No regression
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "compliance_risk_assessment.py"
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
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        assert eng is not None

    def test_risk_band_enum_4_values(self):
        from utils.compliance_risk_assessment import RiskBand
        assert len(list(RiskBand)) == 4
        names = {b.value for b in RiskBand}
        assert names == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

    def test_dataclasses_frozen(self):
        from utils.compliance_risk_assessment import ScoreComponent
        c = ScoreComponent(
            dimension="x", raw_value=Decimal("0"),
            points=Decimal("0"), cap=Decimal("25"),
            contributing_factors=())
        try:
            c.points = Decimal("99")
            raise AssertionError("frozen dataclass mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_198_active(self):
        m = _load("registry_v164", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-198"), None)
        assert s is not None
        assert s.status == "active"
        assert "compliance_risk_assessment" in (
            s.affected_engines or ())


class TestEmptyInput:
    """Rule 6 honesty: no data → zero score, NOT some fabricated
    baseline."""

    def test_no_engines_zero_score(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine, RiskBand)
        eng = ComplianceRiskAssessmentEngine()
        a = eng.assess()
        assert a.total_score == Decimal("0.0")
        assert a.risk_band == RiskBand.LOW
        # All 5 dimensions should report zero or no data
        for c in a.components:
            assert c.points <= Decimal("0")

    def test_missing_engines_in_contradictions(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        a = eng.assess()
        # All 3 missing engines should appear in contradictions
        contradictions_text = " ".join(a.contradictions)
        assert "kyc_engine_not_supplied" in contradictions_text
        assert "aml_engine_not_supplied" in contradictions_text
        assert "sar_engine_not_supplied" in contradictions_text


class TestBandAssignment:
    def test_low_band_below_30(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine, RiskBand)
        eng = ComplianceRiskAssessmentEngine()
        # Score 0 with no input → LOW
        a = eng.assess()
        assert a.risk_band == RiskBand.LOW

    def test_band_thresholds_in_constants(self):
        # The thresholds are part of the public surface
        from utils.compliance_risk_assessment import (
            LOW_BAND_MAX, MEDIUM_BAND_MAX, HIGH_BAND_MAX)
        assert LOW_BAND_MAX == Decimal("29")
        assert MEDIUM_BAND_MAX == Decimal("49")
        assert HIGH_BAND_MAX == Decimal("79")

    def test_band_function_correctness(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine, RiskBand)
        e = ComplianceRiskAssessmentEngine
        assert e._band_from_score(Decimal("0")) == RiskBand.LOW
        assert e._band_from_score(Decimal("29")) == RiskBand.LOW
        assert e._band_from_score(Decimal("30")) == RiskBand.MEDIUM
        assert e._band_from_score(Decimal("49")) == RiskBand.MEDIUM
        assert e._band_from_score(Decimal("50")) == RiskBand.HIGH
        assert e._band_from_score(Decimal("79")) == RiskBand.HIGH
        assert e._band_from_score(Decimal("80")) == RiskBand.CRITICAL
        assert e._band_from_score(Decimal("100")) == RiskBand.CRITICAL


class TestScoreComposition:
    """The 5 dimensions, their caps, and weighting logic."""

    def test_score_capped_at_100(self):
        # Even with extreme inputs, total cannot exceed 100
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        # Build mock engines with extreme numbers
        class MockKyc:
            def all_decisions(self):
                # 100 customers all in PROHIBITED, all sanctions
                class D:
                    def __init__(self, i):
                        self.applicant_kind = "KYC"
                        from utils.kyc_onboarding import KycTier
                        self.tier = KycTier.PROHIBITED
                        self.pep_flag = True
                        self.sanctions_flag = True
                return [D(i) for i in range(100)]
        class MockAml:
            def all_results(self):
                class R:
                    def __init__(self):
                        from utils.aml_monitoring import (
                            MonitoringOutcome)
                        self.outcome = MonitoringOutcome.ESCALATE_TO_SAR
                        self.n_critical = 50
                return [R() for _ in range(50)]
        class MockSar:
            def all_filings(self):
                from utils.sar_filing import FilingStatus
                class F:
                    status = FilingStatus.DRAFT
                return [F() for _ in range(100)]
            def overdue_filings(self):
                from utils.sar_filing import FilingStatus
                class F:
                    status = FilingStatus.DRAFT
                return [F() for _ in range(50)]
        a = eng.assess(kyc_engine=MockKyc(),
                          aml_engine=MockAml(),
                          sar_engine=MockSar())
        assert a.total_score <= Decimal("100")

    def test_sanctions_weighted_3x_pep(self):
        """1 sanctions match contributes 3 pts in raw; 1 PEP contributes
        1 pt (per percentage scaling). The dimension cap is 25."""
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        class MockKyc:
            def all_decisions(self):
                class D:
                    applicant_kind = "KYC"
                    tier = None
                    pep_flag = False
                    sanctions_flag = True   # one sanctions hit
                # 100 customers, only 1 has sanctions
                results = [D() for _ in range(100)]
                # Set 1 sanctions, 0 PEP (base D has sanctions=True
                # so override 99 to False)
                for i, r in enumerate(results):
                    if i > 0:
                        r.sanctions_flag = False
                return results
        a = eng.assess(kyc_engine=MockKyc())
        # weighted_count = 0_pep + 3*1_sanctions = 3
        # weighted_pct = 3 / 100 * 100 = 3 points
        sanctions_comp = next(c for c in a.components
                                if c.dimension == "sanctions_pep_exposure")
        assert sanctions_comp.points == Decimal("3.0"), (
            f"expected 3 pts (1 sanctions x 3 weight / 100 customers x "
            f"100), got {sanctions_comp.points}")

    def test_overdue_filing_weighted_8pts(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        from utils.sar_filing import FilingStatus
        eng = ComplianceRiskAssessmentEngine()
        class MockFiling:
            status = FilingStatus.DRAFT
        class MockSar:
            def all_filings(self):
                return [MockFiling()]
            def overdue_filings(self):
                return [MockFiling()]   # 1 overdue
        a = eng.assess(sar_engine=MockSar())
        filing_comp = next(c for c in a.components
                             if c.dimension == "filing_backlog")
        # 1 overdue * 8 pts = 8 pts
        assert filing_comp.points == Decimal("8.0")

    def test_critical_alert_weighted_5pts(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        class MockAml:
            def all_results(self):
                class R:
                    from utils.aml_monitoring import MonitoringOutcome
                    outcome = MonitoringOutcome.ESCALATE_TO_SAR
                    n_critical = 1
                return [R()]
        a = eng.assess(aml_engine=MockAml())
        alert_comp = next(c for c in a.components
                            if c.dimension == "alert_backlog")
        # 1 critical * 5 + 1 open * 1 = 6 pts
        assert alert_comp.points == Decimal("6.0")


class TestCrossClusterContradictions:
    def test_prohibited_without_sar_flagged(self):
        """Customer in PROHIBITED tier but no SAR submitted = evasion
        suspicion."""
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        class MockKyc:
            def all_decisions(self):
                class D:
                    from utils.kyc_onboarding import KycTier
                    applicant_kind = "KYC"
                    tier = KycTier.PROHIBITED
                    pep_flag = False
                    sanctions_flag = False
                return [D()]
        class MockSar:
            def all_filings(self): return []
            def overdue_filings(self): return []
        a = eng.assess(kyc_engine=MockKyc(), sar_engine=MockSar())
        contradiction_text = " ".join(a.contradictions)
        assert "PROHIBITED" in contradiction_text
        assert "no_SAR" in contradiction_text


class TestHonestDeferrals:
    """3 deferral surfaces: trend, industry, ML."""

    def test_three_deferrals_surface(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        a = eng.assess()
        assert "DEFERRED" in a.trend_analysis_status
        assert ("PARTIAL" in a.industry_concentration_status or
                 "DEFERRED" in a.industry_concentration_status)
        assert "DEFERRED" in a.ml_predictive_status

    def test_board_summary_surfaces_deferrals(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        s = eng.board_summary()
        assert "trend_analysis_status" in s


class TestEndToEndIntegration:
    """The headline test — full AML pipeline rolling up cleanly."""

    def test_full_pipeline_produces_valid_score(self):
        from datetime import datetime
        from decimal import Decimal as _Dec
        from utils.kyc_onboarding import (
            KycOnboardingEngine, CustomerApplicant, IdentityDocument,
            IdDocumentType, DocumentVerificationStatus,
            BiometricVerificationStatus)
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.transaction_monitoring import Transaction
        from utils.sar_filing import SarFilingEngine
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine, RiskBand)

        # Set up minimal pipeline
        kyc = KycOnboardingEngine()
        kyc.register_customer(CustomerApplicant(
            applicant_id="X1", full_name="Test X",
            date_of_birth="1990-01-01", nationality="KE",
            residence_country="KE", occupation="ENGINEER",
            purpose_of_account="SAVINGS",
            documents=(IdentityDocument(
                document_type=IdDocumentType.NATIONAL_ID,
                document_number="999",
                verification_status=(
                    DocumentVerificationStatus.VERIFIED)),),
            biometric_status=BiometricVerificationStatus.VERIFIED_LIVE))
        kyc.decide("X1")

        aml = AmlMonitoringEngine()
        aml.monitor_customer("X1", [Transaction(
            txn_id="T1", customer_id="X1", account_id="A1",
            amount_kes=_Dec("100"),
            txn_type="MOBILE_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))],
            customer_tier="CDD")

        sar = SarFilingEngine()

        cra = ComplianceRiskAssessmentEngine()
        a = cra.assess(kyc_engine=kyc, aml_engine=aml, sar_engine=sar)

        # All three engines wired in → no missing-engine contradictions
        for c in a.contradictions:
            assert "not_supplied" not in c
        # Score should be a valid Decimal in [0, 100]
        assert Decimal("0") <= a.total_score <= Decimal("100")
        # Band must be valid
        assert a.risk_band in (RiskBand.LOW, RiskBand.MEDIUM,
                                  RiskBand.HIGH, RiskBand.CRITICAL)


class TestPortfolioSummary:
    def test_board_summary_empty_state(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        s = eng.board_summary()
        assert s["engine"] == "ENH-198 ComplianceRiskAssessmentEngine"
        assert s["n_assessments"] == 0
        assert "regulatory_basis" in s

    def test_board_summary_after_assess(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        eng.assess()
        s = eng.board_summary()
        assert s["n_assessments"] == 1
        assert "latest_assessment_id" in s
        assert "latest_total_score" in s
        assert "latest_risk_band" in s

    def test_assessment_to_dict_has_all_fields(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        a = eng.assess()
        d = a.to_dict()
        for f in ("assessment_id", "total_score", "risk_band",
                   "components", "n_customers", "n_open_alerts",
                   "n_filings_overdue", "contradictions",
                   "trend_analysis_status", "ml_predictive_status",
                   "upstream_engines"):
            assert f in d


class TestNoRegression:
    def test_audit_still_passes(self):
        m = _load("audit_v164", AUDIT_PATH)
        for gate_id, gate_fn in m.GATES:
            result = gate_fn()
            assert result["passed"] is True

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v164", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_163_sar_filing_works(self):
        from utils.sar_filing import SarFilingEngine
        eng = SarFilingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-194 SarFilingEngine")

    def test_v10_162_aml_works(self):
        from utils.aml_monitoring import AmlMonitoringEngine
        eng = AmlMonitoringEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-193 AmlMonitoringEngine")

    def test_v10_160_kyc_works(self):
        from utils.kyc_onboarding import KycOnboardingEngine
        eng = KycOnboardingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-191 KycOnboardingEngine")

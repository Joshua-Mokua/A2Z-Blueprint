"""tests/integration/test_v10_11_ai_underwriting.py — v10.11.

Integration tests for utils/ai_underwriting.py (Phase 2 batch 5 = Credit batch 1).
ENH-119, ENH-124, ENH-CRD-R2, ENH-CRD-R3.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1011EngineImports(unittest.TestCase):
    def test_module_imports(self):
        from utils import ai_underwriting  # noqa: F401

    def test_public_symbols(self):
        from utils import ai_underwriting as m
        for sym in (
            "UnderwritingDecision", "ConfidenceLevel",
            "ApplicantFeatures", "FeatureContribution",
            "ModelCard", "EUAIActHighRiskMetadata",
            "AIDecisionResult",
            "compute_underwriting_decision",
            "compute_feature_contributions",
            "generate_adverse_action_codes",
            "validate_eu_ai_act_compliance",
            "AIUnderwritingEngine",
            "CFPB_ADVERSE_ACTION_CODES",
            "FEATURE_TO_AA_CODE",
            "EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES",
            "EU_AI_ACT_REQUIRED_TRANSPARENCY",
            "EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT",
            "EU_AI_ACT_REQUIRED_ACCURACY",
            "HIGH_CONFIDENCE_THRESHOLD",
            "LOW_CONFIDENCE_THRESHOLD",
            "DTI_HARD_CAP_PCT", "LTV_HARD_CAP_PCT",
            "MAX_ADVERSE_ACTION_CODES",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1011SelfTestPasses(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import ai_underwriting
        ai_underwriting.self_test()


class TestV1011RegistryAlignment(unittest.TestCase):
    def test_4_credit_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "credit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 4)

    def test_v10_11_specific_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "credit" and s.status == "active"}
        for sid in ("ENH-119", "ENH-124", "ENH-CRD-R2", "ENH-CRD-R3"):
            self.assertIn(sid, active_ids,
                            f"{sid} should be active after v10.11")


class TestV1011DecisionLogic(unittest.TestCase):
    """ENH-119 — decision logic correctness."""

    def test_strong_applicant_approves(self):
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine,
            UnderwritingDecision, ConfidenceLevel)
        f = ApplicantFeatures(
            applicant_id="STRONG-1",
            monthly_income_kes=Decimal("250000"),
            income_verified=True, employment_months=60,
            bureau_file_present=True, bureau_score=Decimal("750"),
            credit_history_months=120,
            delinquencies_past_24m=0, bankruptcies_past_84m=0,
            dti_ratio_pct=Decimal("28"))
        eng = AIUnderwritingEngine(pd_provider=lambda x: Decimal("0.02"))
        result = eng.decide(f)
        self.assertEqual(result.decision, UnderwritingDecision.APPROVE)
        self.assertEqual(result.confidence, ConfidenceLevel.HIGH)
        self.assertTrue(result.is_automated())

    def test_dti_hard_cap_declines(self):
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine,
            UnderwritingDecision)
        f = ApplicantFeatures(
            applicant_id="DTI-CAP",
            monthly_income_kes=Decimal("100000"),
            income_verified=True, bureau_file_present=True,
            bureau_score=Decimal("700"),
            dti_ratio_pct=Decimal("65"))
        eng = AIUnderwritingEngine(pd_provider=lambda x: Decimal("0.02"))
        r = eng.decide(f)
        self.assertEqual(r.decision, UnderwritingDecision.DECLINE)

    def test_no_pd_no_provider_refers(self):
        """Rule 7 honesty — no PD source → REFER not silent default."""
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine,
            UnderwritingDecision, ConfidenceLevel)
        f = ApplicantFeatures(
            applicant_id="NO-PD",
            monthly_income_kes=Decimal("100000"),
            income_verified=True, bureau_file_present=True)
        eng = AIUnderwritingEngine()  # no pd_provider
        r = eng.decide(f)
        self.assertEqual(r.decision, UnderwritingDecision.REFER_HUMAN)
        self.assertEqual(r.confidence, ConfidenceLevel.LOW)


class TestV1011Explainability(unittest.TestCase):
    """ENH-124 — explainability + feature contributions."""

    def test_contributions_returned_for_each_decision(self):
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine)
        f = ApplicantFeatures(
            applicant_id="X",
            monthly_income_kes=Decimal("100000"),
            income_verified=True,
            bureau_file_present=True, bureau_score=Decimal("700"),
            dti_ratio_pct=Decimal("30"))
        eng = AIUnderwritingEngine(pd_provider=lambda x: Decimal("0.03"))
        r = eng.decide(f)
        self.assertGreater(len(r.feature_contributions), 0)
        # First contribution is highest-ranked
        self.assertEqual(r.feature_contributions[0].rank, 1)

    def test_missing_features_dont_appear_in_contributions(self):
        """Rule 1 — missing feature is never silently zero-substituted."""
        from utils.ai_underwriting import (
            ApplicantFeatures, compute_feature_contributions)
        f = ApplicantFeatures(applicant_id="EMPTY")
        contribs = compute_feature_contributions(f)
        self.assertEqual(len(contribs), 0)


class TestV1011AdverseActionCodes(unittest.TestCase):
    """ENH-CRD-R3 — CFPB-compliant adverse action reason codes."""

    def test_decline_produces_specific_codes(self):
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine,
            CFPB_ADVERSE_ACTION_CODES)
        f = ApplicantFeatures(
            applicant_id="WEAK",
            monthly_income_kes=Decimal("20000"),
            income_verified=True,
            bureau_file_present=True, bureau_score=Decimal("400"),
            delinquencies_past_24m=5,
            missed_payments_12m=8,
            dti_ratio_pct=Decimal("55"))
        eng = AIUnderwritingEngine(pd_provider=lambda x: Decimal("0.40"))
        r = eng.decide(f)
        self.assertGreater(len(r.adverse_action_codes), 0)
        for code in r.adverse_action_codes:
            self.assertIn(code, CFPB_ADVERSE_ACTION_CODES)

    def test_approve_produces_no_codes(self):
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine)
        f = ApplicantFeatures(
            applicant_id="STRONG",
            monthly_income_kes=Decimal("250000"),
            income_verified=True, employment_months=60,
            bureau_file_present=True, bureau_score=Decimal("780"),
            delinquencies_past_24m=0, dti_ratio_pct=Decimal("25"))
        eng = AIUnderwritingEngine(pd_provider=lambda x: Decimal("0.01"))
        r = eng.decide(f)
        self.assertEqual(r.adverse_action_codes, ())

    def test_max_codes_capped(self):
        """ECOA + Reg B — typically 4 reason codes max for retail."""
        from utils.ai_underwriting import (
            ApplicantFeatures, MAX_ADVERSE_ACTION_CODES,
            compute_feature_contributions, generate_adverse_action_codes)
        # Construct an applicant where many features map to AA codes
        f = ApplicantFeatures(
            applicant_id="MANY",
            monthly_income_kes=Decimal("10000"),
            employment_months=2, residency_months=1,
            bureau_score=Decimal("300"),
            credit_history_months=2,
            delinquencies_past_24m=10,
            recent_inquiries_3m=15,
            active_garnishments=2,
            ltv_ratio_pct=Decimal("99"),
            dti_ratio_pct=Decimal("58"),
            missed_payments_12m=11)
        contribs = compute_feature_contributions(f)
        codes = generate_adverse_action_codes(f, contribs)
        self.assertLessEqual(len(codes), MAX_ADVERSE_ACTION_CODES)


class TestV1011EUAIActCompliance(unittest.TestCase):
    """ENH-CRD-R2 — EU AI Act high-risk compliance."""

    def test_default_metadata_not_compliant(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        eng = AIUnderwritingEngine()
        self.assertFalse(eng.eu_ai_act_metadata.is_compliant())

    def test_full_metadata_compliant(self):
        from utils.ai_underwriting import (
            EUAIActHighRiskMetadata, EU_AI_ACT_ANNEX_III_SECTION,
            EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES,
            EU_AI_ACT_REQUIRED_TRANSPARENCY,
            EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT,
            EU_AI_ACT_REQUIRED_ACCURACY)
        m = EUAIActHighRiskMetadata(
            annex_iii_section=EU_AI_ACT_ANNEX_III_SECTION,
            risk_mgmt_processes_in_place=EU_AI_ACT_REQUIRED_RISK_MGMT_PROCESSES,
            transparency_artifacts_in_place=EU_AI_ACT_REQUIRED_TRANSPARENCY,
            human_oversight_measures_in_place=EU_AI_ACT_REQUIRED_HUMAN_OVERSIGHT,
            accuracy_artifacts_in_place=EU_AI_ACT_REQUIRED_ACCURACY,
            last_compliance_review="2025-12-31")
        self.assertTrue(m.is_compliant())
        self.assertEqual(m.completeness_pct(), Decimal("100"))

    def test_validate_returns_missing_per_article(self):
        from utils.ai_underwriting import (
            EUAIActHighRiskMetadata, EU_AI_ACT_ANNEX_III_SECTION,
            validate_eu_ai_act_compliance)
        m = EUAIActHighRiskMetadata(
            annex_iii_section=EU_AI_ACT_ANNEX_III_SECTION,
            risk_mgmt_processes_in_place=("RISK_IDENTIFICATION",),
            transparency_artifacts_in_place=(),
            human_oversight_measures_in_place=(),
            accuracy_artifacts_in_place=(),
            last_compliance_review="")
        result = validate_eu_ai_act_compliance(m)
        self.assertEqual(len(result["missing_art9_risk_mgmt"]), 3)
        self.assertEqual(len(result["missing_art13_transparency"]), 5)
        self.assertEqual(len(result["missing_art14_human_oversight"]), 3)
        self.assertEqual(len(result["missing_art15_accuracy"]), 4)


class TestV1011BoardSummary(unittest.TestCase):
    def test_board_summary_aggregates_decisions(self):
        from utils.ai_underwriting import (
            ApplicantFeatures, AIUnderwritingEngine)
        eng = AIUnderwritingEngine(pd_provider=lambda x: Decimal("0.02"))
        for i in range(3):
            f = ApplicantFeatures(
                applicant_id=f"A-{i}",
                monthly_income_kes=Decimal("200000"),
                income_verified=True,
                bureau_file_present=True, bureau_score=Decimal("750"),
                delinquencies_past_24m=0,
                dti_ratio_pct=Decimal("28"))
            eng.decide(f)
        s = eng.board_summary()
        self.assertEqual(s["n_decisions"], 3)
        self.assertEqual(s["approve_pct"], Decimal("100"))


class TestV1011RuleHonesty(unittest.TestCase):
    """Honesty Rule 7 — no silent ML predictions."""

    def test_default_engine_marks_rule_based(self):
        from utils.ai_underwriting import (
            AIUnderwritingEngine, SPEC_DEVIATION_NOTE)
        eng = AIUnderwritingEngine()
        self.assertEqual(eng.model_card.methodology, "rule_based")
        self.assertIn(SPEC_DEVIATION_NOTE,
                        eng.model_card.deviation_notes)


class TestV1011IntegrationWithEarlierPhases(unittest.TestCase):
    """v10.11 coexists with v10.6-v10.10 climate engines."""

    def test_climate_and_ai_underwriting_engines_coexist(self):
        from utils.esg_intelligence import ESGIntelligenceEngine
        from utils.ai_underwriting import AIUnderwritingEngine
        esg = ESGIntelligenceEngine(entity_name="Ecobank Kenya")
        uw = AIUnderwritingEngine(entity_name="Ecobank Kenya")
        self.assertEqual(esg.entity_name, uw.entity_name)


if __name__ == "__main__":
    unittest.main()

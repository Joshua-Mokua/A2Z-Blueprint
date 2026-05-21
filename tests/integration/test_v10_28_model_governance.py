"""tests/integration/test_v10_28_model_governance.py — v10.28.

Model Governance arc batch 1: foundation — model inventory + lifecycle +
drift detection (PSI/KS) + validation framework + explainability + bias.
ENH-259 + ENH-261 + ENH-262 + ENH-263 + ENH-265.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1028Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import model_governance  # noqa

    def test_public_symbols(self):
        from utils import model_governance as m
        for sym in (
            # Inventory
            "ModelType", "ModelTier", "EUAIActRiskCategory",
            "DEFAULT_VALIDATION_CADENCE_MONTHS",
            "ModelLifecycleState", "ALLOWED_LIFECYCLE_TRANSITIONS",
            "is_valid_lifecycle_transition", "Model",
            # Drift
            "DriftDetectionMethod", "DriftSeverity",
            "PSI_NO_DRIFT_THRESHOLD",
            "PSI_SMALL_SHIFT_THRESHOLD",
            "PSI_SIGNIFICANT_THRESHOLD",
            "DriftResult", "compute_psi", "detect_drift_psi",
            "compute_ks_statistic", "ks_critical_value",
            "detect_drift_ks", "compute_wasserstein_distance",
            # Validation
            "ValidationGate", "ValidationVerdict",
            "ValidationTestResult",
            "REQUIRED_VALIDATION_GATES_BY_TIER",
            "ValidationReport", "assemble_validation_report",
            # Explainability
            "ExplanationMethod", "ADVERSE_ACTION_CODES",
            "ExplanationResult", "explain_decision",
            "map_features_to_adverse_action",
            # Bias
            "BiasMetric", "BiasVerdict",
            "FOUR_FIFTHS_RULE_THRESHOLD",
            "DEMOGRAPHIC_PARITY_TOLERANCE",
            "BiasResult", "four_fifths_rule_test",
            "demographic_parity_test",
            # Engine
            "ModelGovernanceEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1028SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import model_governance
        model_governance.self_test()


class TestV1028RegistryAlignment(unittest.TestCase):
    def test_5_modgov_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "credit_model_risk"
                    and s.status == "active"]
        self.assertGreaterEqual(len(active), 5)

    def test_v10_28_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "credit_model_risk"
                        and s.status == "active"}
        for sid in ("ENH-259", "ENH-261", "ENH-262",
                       "ENH-263", "ENH-265"):
            self.assertIn(sid, active_ids)


class TestV1028ModelLifecycle(unittest.TestCase):
    """ENH-259 — Model lifecycle."""

    def test_cannot_skip_dev_to_production(self):
        from utils.model_governance import (
            is_valid_lifecycle_transition, ModelLifecycleState)
        self.assertFalse(is_valid_lifecycle_transition(
            ModelLifecycleState.DEVELOPMENT,
            ModelLifecycleState.IN_PRODUCTION))

    def test_retired_is_terminal(self):
        from utils.model_governance import (
            ALLOWED_LIFECYCLE_TRANSITIONS, ModelLifecycleState)
        self.assertEqual(
            len(ALLOWED_LIFECYCLE_TRANSITIONS[
                ModelLifecycleState.RETIRED]), 0)

    def test_tier_1_annual_cadence(self):
        from utils.model_governance import (
            DEFAULT_VALIDATION_CADENCE_MONTHS, ModelTier)
        self.assertEqual(
            DEFAULT_VALIDATION_CADENCE_MONTHS[ModelTier.TIER_1_HIGH], 12)


class TestV1028DriftDetection(unittest.TestCase):
    """ENH-261 — Drift detection."""

    def test_psi_thresholds_industry_standard(self):
        from utils.model_governance import (
            PSI_NO_DRIFT_THRESHOLD,
            PSI_SMALL_SHIFT_THRESHOLD,
            PSI_SIGNIFICANT_THRESHOLD)
        # Per Siddiqi 2017
        self.assertEqual(PSI_NO_DRIFT_THRESHOLD, Decimal("0.10"))
        self.assertEqual(PSI_SMALL_SHIFT_THRESHOLD, Decimal("0.20"))
        self.assertEqual(PSI_SIGNIFICANT_THRESHOLD, Decimal("0.25"))

    def test_psi_identical_distributions_zero(self):
        from utils.model_governance import compute_psi
        base = [Decimal("0.25")] * 4
        psi = compute_psi(
            baseline_distribution=base,
            current_distribution=base)
        self.assertLess(psi, Decimal("0.001"))

    def test_psi_completely_shifted_high(self):
        from utils.model_governance import compute_psi
        base = [Decimal("0.5"), Decimal("0.5"),
                  Decimal("0"), Decimal("0")]
        curr = [Decimal("0"), Decimal("0"),
                  Decimal("0.5"), Decimal("0.5")]
        psi = compute_psi(
            baseline_distribution=base, current_distribution=curr)
        self.assertGreater(psi, Decimal("1.0"))

    def test_detect_psi_insufficient_data_explicit(self):
        """Rule 1 — INSUFFICIENT_DATA explicit, never silent pass."""
        from utils.model_governance import (
            detect_drift_psi, DriftSeverity)
        result = detect_drift_psi(
            test_id="T1", model_id="M1", feature_name="x",
            baseline_distribution=[Decimal("0.5"), Decimal("0.5")],
            current_distribution=[Decimal("0.5"), Decimal("0.5")],
            n_baseline=50, n_current=50,
            test_date="2026-05-01")
        self.assertEqual(result.severity, DriftSeverity.INSUFFICIENT_DATA)

    def test_ks_disjoint_distributions_max(self):
        from utils.model_governance import compute_ks_statistic
        base = [Decimal(str(i)) for i in range(100)]
        curr = [Decimal(str(i + 1000)) for i in range(100)]
        ks = compute_ks_statistic(
            baseline_samples=base, current_samples=curr)
        self.assertEqual(ks, Decimal("1"))

    def test_ks_critical_decreases_with_n(self):
        from utils.model_governance import ks_critical_value
        cv_50 = ks_critical_value(n_baseline=50, n_current=50)
        cv_5000 = ks_critical_value(n_baseline=5000, n_current=5000)
        self.assertGreater(cv_50, cv_5000)


class TestV1028Validation(unittest.TestCase):
    """ENH-262 — Validation framework."""

    def test_tier_1_more_gates_than_tier_3(self):
        from utils.model_governance import (
            REQUIRED_VALIDATION_GATES_BY_TIER, ModelTier)
        t1 = REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_1_HIGH]
        t3 = REQUIRED_VALIDATION_GATES_BY_TIER[ModelTier.TIER_3_LOW]
        self.assertGreater(len(t1), len(t3))

    def test_fail_blocks_overall_verdict(self):
        from utils.model_governance import (
            assemble_validation_report, Model, ModelType,
            ModelTier, EUAIActRiskCategory, ModelLifecycleState,
            ValidationTestResult, ValidationGate,
            ValidationVerdict, REQUIRED_VALIDATION_GATES_BY_TIER)
        model = Model(
            model_id="M1", model_name="X",
            model_type=ModelType.CREDIT_SCORECARD,
            model_tier=ModelTier.TIER_3_LOW,
            eu_ai_act_category=EUAIActRiskCategory.HIGH_RISK,
            current_state=ModelLifecycleState.INTERNAL_TESTING,
            owner_business_unit="X", owner_user_id="alice",
            development_date="2026-01-01")
        results = []
        for gate in REQUIRED_VALIDATION_GATES_BY_TIER[
                ModelTier.TIER_3_LOW]:
            verdict = (ValidationVerdict.FAIL
                         if gate == ValidationGate.DATA_QUALITY
                         else ValidationVerdict.PASS)
            results.append(ValidationTestResult(
                test_result_id=f"VR-{gate.value}",
                model_id="M1", gate=gate, verdict=verdict,
                test_date="2026-05-01"))
        report = assemble_validation_report(
            report_id="REP1", model=model,
            test_results=results,
            report_date="2026-05-01")
        self.assertEqual(report.overall_verdict, ValidationVerdict.FAIL)


class TestV1028Explainability(unittest.TestCase):
    """ENH-263 — Explainability + adverse action."""

    def test_no_provider_requires_provider(self):
        """Rule 7 — no explainer → REQUIRES_PROVIDER, never fabricates."""
        from utils.model_governance import (
            explain_decision, ExplanationMethod)
        result = explain_decision(
            explanation_id="E1", model_id="M1",
            decision_id="D1", method=ExplanationMethod.SHAP,
            features={"x": Decimal("1")})
        self.assertIn("REQUIRES_PROVIDER", result.notes)

    def test_adverse_action_codes_per_cfpb(self):
        from utils.model_governance import ADVERSE_ACTION_CODES
        # Per CFPB Reg B Appendix C
        self.assertIn("Bankruptcy", ADVERSE_ACTION_CODES.get("15", ""))
        self.assertGreaterEqual(len(ADVERSE_ACTION_CODES), 15)

    def test_map_features_to_adverse_action(self):
        from utils.model_governance import (
            ExplanationResult, ExplanationMethod,
            map_features_to_adverse_action)
        explanation = ExplanationResult(
            explanation_id="E1", model_id="M1",
            decision_id="D1", method=ExplanationMethod.SHAP,
            feature_contributions={"delinquency": Decimal("-0.5")},
            base_value=Decimal("0.5"),
            predicted_value=Decimal("0.0"),
            top_n_negative=("delinquency",))
        codes = map_features_to_adverse_action(
            explanation=explanation,
            feature_to_aa_code_map={"delinquency": "16"})
        self.assertIn("16", codes)


class TestV1028BiasMonitoring(unittest.TestCase):
    """ENH-265 — Bias monitoring."""

    def test_four_fifths_threshold_per_eeoc(self):
        from utils.model_governance import FOUR_FIFTHS_RULE_THRESHOLD
        # 29 CFR §1607.4
        self.assertEqual(FOUR_FIFTHS_RULE_THRESHOLD, Decimal("0.80"))

    def test_disparate_impact_detected(self):
        from utils.model_governance import (
            four_fifths_rule_test, BiasVerdict)
        result = four_fifths_rule_test(
            test_id="B1", model_id="M1",
            protected_class="gender",
            reference_group="male", comparison_group="female",
            n_reference_total=1000, n_reference_positive=500,
            n_comparison_total=1000, n_comparison_positive=200,
            test_date="2026-05-01")
        self.assertEqual(result.verdict, BiasVerdict.DISPARATE_IMPACT)

    def test_no_bias_at_equal_rates(self):
        from utils.model_governance import (
            four_fifths_rule_test, BiasVerdict)
        result = four_fifths_rule_test(
            test_id="B1", model_id="M1",
            protected_class="gender",
            reference_group="male", comparison_group="female",
            n_reference_total=1000, n_reference_positive=500,
            n_comparison_total=1000, n_comparison_positive=500,
            test_date="2026-05-01")
        self.assertEqual(result.verdict, BiasVerdict.NO_BIAS_DETECTED)

    def test_insufficient_data_explicit(self):
        from utils.model_governance import (
            four_fifths_rule_test, BiasVerdict)
        result = four_fifths_rule_test(
            test_id="B1", model_id="M1",
            protected_class="x", reference_group="r",
            comparison_group="c",
            n_reference_total=20, n_reference_positive=10,
            n_comparison_total=20, n_comparison_positive=8,
            test_date="2026-05-01")
        self.assertEqual(result.verdict, BiasVerdict.INSUFFICIENT_DATA)


class TestV1028EngineEnforcement(unittest.TestCase):
    """Engine enforces governance preconditions."""

    def _model(self, mid="M1", tier=None, state=None):
        from utils.model_governance import (
            Model, ModelType, ModelTier, EUAIActRiskCategory,
            ModelLifecycleState)
        return Model(
            model_id=mid, model_name=f"M-{mid}",
            model_type=ModelType.CREDIT_SCORECARD,
            model_tier=tier or ModelTier.TIER_2_MEDIUM,
            eu_ai_act_category=EUAIActRiskCategory.HIGH_RISK,
            current_state=state or ModelLifecycleState.DEVELOPMENT,
            owner_business_unit="X", owner_user_id="alice",
            development_date="2026-01-01")

    def test_tier_1_production_blocked_without_validation(self):
        from utils.model_governance import (
            ModelGovernanceEngine, ModelTier, ModelLifecycleState)
        eng = ModelGovernanceEngine()
        model = self._model(
            tier=ModelTier.TIER_1_HIGH,
            state=ModelLifecycleState.APPROVED_FOR_PRODUCTION)
        eng.register_model(model)
        with self.assertRaises(ValueError):
            eng.transition_model(
                model_id="M1",
                to_state=ModelLifecycleState.IN_PRODUCTION,
                actor_user_id="alice", timestamp="t")

    def test_tier_3_no_validation_required(self):
        """Tier 3 → IN_PRODUCTION allowed without validation report."""
        from utils.model_governance import (
            ModelGovernanceEngine, ModelTier, ModelLifecycleState)
        eng = ModelGovernanceEngine()
        model = self._model(
            tier=ModelTier.TIER_3_LOW,
            state=ModelLifecycleState.APPROVED_FOR_PRODUCTION)
        eng.register_model(model)
        updated = eng.transition_model(
            model_id="M1",
            to_state=ModelLifecycleState.IN_PRODUCTION,
            actor_user_id="alice",
            timestamp="2026-05-01T00:00:00Z")
        self.assertEqual(
            updated.current_state, ModelLifecycleState.IN_PRODUCTION)

    def test_actionable_drift_filter(self):
        from utils.model_governance import (
            ModelGovernanceEngine, ModelTier)
        eng = ModelGovernanceEngine()
        eng.register_model(self._model(tier=ModelTier.TIER_2_MEDIUM))
        # No-drift case
        eng.run_psi_drift(
            test_id="T1", model_id="M1", feature_name="x",
            baseline_distribution=[Decimal("0.25")] * 4,
            current_distribution=[Decimal("0.25")] * 4,
            n_baseline=1000, n_current=1000,
            test_date="2026-05-01")
        # Major drift
        eng.run_psi_drift(
            test_id="T2", model_id="M1", feature_name="y",
            baseline_distribution=[
                Decimal("0.5"), Decimal("0.5"),
                Decimal("0.001"), Decimal("0.001")],
            current_distribution=[
                Decimal("0.001"), Decimal("0.001"),
                Decimal("0.5"), Decimal("0.5")],
            n_baseline=1000, n_current=1000,
            test_date="2026-05-01")
        actionable = eng.actionable_drift_results()
        self.assertEqual(len(actionable), 1)
        self.assertEqual(actionable[0].test_id, "T2")


class TestV1028Coexistence(unittest.TestCase):
    """v10.28 coexists with v10.23-v10.27 audit stack."""

    def test_audit_and_modgov_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_trail_certification import (
            AuditTrailCertificationEngine)
        from utils.model_governance import ModelGovernanceEngine
        engines = [
            AuditCoreEngine(entity_name="X"),
            AuditTrailCertificationEngine(entity_name="X"),
            ModelGovernanceEngine(entity_name="X"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

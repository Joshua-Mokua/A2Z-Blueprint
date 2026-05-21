"""tests/integration/test_v10_32_cross_sell_bandit.py — v10.32.

Cross-Sell Bandit pilot: first ML in the platform. The integration
that justifies all 6 closed Phase 2 arcs.

Tests verify:
  - Bandit registers as Tier 1 model in v10.28 ModelGovernanceEngine
  - Tier 1/2 → IN_PRODUCTION blocked without passed validation report
  - Bandit subject to PSI drift detection on contexts (v10.28 ENH-261)
  - Bandit subject to 4/5ths rule bias monitoring (v10.28 ENH-265)
  - Risk appetite (ENH-267) suppresses loan offers for NPL customers
  - Bandit + simulator integration: drive customers through bandit
  - Champion-challenger via v10.29 retraining workflow
  - All protected-attribute features rejected
  - G126 audit gate locks the closure
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1032Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import cross_sell_bandit  # noqa

    def test_public_symbols(self):
        from utils import cross_sell_bandit as m
        for sym in (
            "OfferType", "RISK_BEARING_OFFERS",
            "DEFAULT_OFFER_CATALOG",
            "FORBIDDEN_FEATURE_NAMES", "validate_feature_names",
            "identity_matrix", "matrix_invert",
            "mat_vec_mul", "vec_dot", "vec_outer",
            "CustomerContext",
            "BanditDecision", "BanditFeedback",
            "DEFAULT_LINUCB_ALPHA", "LinUCBArm",
            "BanditConfig", "ValidationGateOutcome",
            "CrossSellBanditEngine",
            "DEFAULT_FEATURE_NAMES", "extract_features_from_bank",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1032SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import cross_sell_bandit
        cross_sell_bandit.self_test()


class TestV1032G126Gate(unittest.TestCase):
    def test_g126_function_exists(self):
        from scripts.audit import gate_cross_sell_bandit_pilot_implemented
        self.assertTrue(callable(
            gate_cross_sell_bandit_pilot_implemented))

    def test_g126_in_gates_list(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertIn("G126", gate_ids)

    def test_g126_after_g125(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertGreater(
            gate_ids.index("G126"), gate_ids.index("G125"))

    def test_total_gate_count_at_least_126(self):
        from scripts.audit import GATES
        self.assertGreaterEqual(len(GATES), 126)

    def test_g126_passes(self):
        from scripts.audit import gate_cross_sell_bandit_pilot_implemented
        r = gate_cross_sell_bandit_pilot_implemented()
        self.assertTrue(
            r["passed"],
            f"G126 should pass; violations: {r.get('violations')}")


class TestV1032StandardsAlignment(unittest.TestCase):
    """ENH-267 Credit Risk Appetite Integration activated."""

    def test_enh_267_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {
            s.standard_id for s in STANDARDS_REGISTRY
            if s.status == "active"}
        self.assertIn("ENH-267", active_ids)

    def test_8_modgov_standards_active(self):
        """v10.28 (5) + v10.29 (2) + v10.32 (1) = 8 active."""
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [
            s for s in STANDARDS_REGISTRY
            if s.subcategory == "credit_model_risk"
            and s.status == "active"]
        self.assertGreaterEqual(len(active), 8)


class TestV1032GovernanceRegistration(unittest.TestCase):
    """Bandit registers as Tier 1 model in v10.28 ModelGovernance."""

    def _make_bandit(self):
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG)
        cfg = BanditConfig(
            config_id="C1", model_id="M-CSB-001",
            feature_names=("balance_log", "tenure_days_log",
                              "n_products", "intercept"),
            offer_catalog=DEFAULT_OFFER_CATALOG,
            alpha=1.0, base_seed="csb-test")
        return CrossSellBanditEngine(config=cfg)

    def test_bandit_registers_as_tier_1_model(self):
        """Bandit is a Tier 1 (HIGH) model — affects credit decisions."""
        from utils.model_governance import (
            Model, ModelType, ModelTier, EUAIActRiskCategory,
            ModelLifecycleState, ModelGovernanceEngine)
        bandit = self._make_bandit()
        modgov = ModelGovernanceEngine(entity_name="Test")
        # Register the bandit as Tier 1 (because affects customer
        # treatment via offer recommendations)
        bandit_model = Model(
            model_id=bandit.config.model_id,
            model_name="Cross-Sell Bandit",
            model_type=ModelType.CROSS_SELL,
            model_tier=ModelTier.TIER_1_HIGH,    # affects treatment
            eu_ai_act_category=EUAIActRiskCategory.LIMITED_RISK,
            current_state=ModelLifecycleState.DEVELOPMENT,
            owner_business_unit="Retail Banking",
            owner_user_id="alice",
            development_date="2026-05-01")
        modgov.register_model(bandit_model)
        retrieved = modgov.get_model(bandit.config.model_id)
        self.assertEqual(retrieved.model_tier, ModelTier.TIER_1_HIGH)

    def test_tier_1_in_production_blocked_without_validation(self):
        """v10.28 enforcement: Tier 1 → IN_PRODUCTION needs validation."""
        from utils.model_governance import (
            Model, ModelType, ModelTier, EUAIActRiskCategory,
            ModelLifecycleState, ModelGovernanceEngine)
        bandit = self._make_bandit()
        modgov = ModelGovernanceEngine(entity_name="Test")
        modgov.register_model(Model(
            model_id=bandit.config.model_id,
            model_name="Cross-Sell Bandit",
            model_type=ModelType.CROSS_SELL,
            model_tier=ModelTier.TIER_1_HIGH,
            eu_ai_act_category=EUAIActRiskCategory.LIMITED_RISK,
            current_state=ModelLifecycleState.APPROVED_FOR_PRODUCTION,
            owner_business_unit="X", owner_user_id="alice",
            development_date="2026-05-01"))
        # Try to transition to IN_PRODUCTION without validation —
        # MUST fail per v10.28 Tier 1 rule
        with self.assertRaises(ValueError) as ctx:
            modgov.transition_model(
                model_id=bandit.config.model_id,
                to_state=ModelLifecycleState.IN_PRODUCTION,
                actor_user_id="alice", timestamp="t")
        self.assertIn("validation", str(ctx.exception).lower())

    def test_tier_1_in_production_allowed_after_pass(self):
        """After full validation report PASS, transition allowed."""
        from utils.model_governance import (
            Model, ModelType, ModelTier, EUAIActRiskCategory,
            ModelLifecycleState, ModelGovernanceEngine,
            ValidationTestResult, ValidationGate,
            ValidationVerdict,
            REQUIRED_VALIDATION_GATES_BY_TIER)
        bandit = self._make_bandit()
        modgov = ModelGovernanceEngine(entity_name="Test")
        modgov.register_model(Model(
            model_id=bandit.config.model_id,
            model_name="Cross-Sell Bandit",
            model_type=ModelType.CROSS_SELL,
            model_tier=ModelTier.TIER_1_HIGH,
            eu_ai_act_category=EUAIActRiskCategory.LIMITED_RISK,
            current_state=ModelLifecycleState.APPROVED_FOR_PRODUCTION,
            owner_business_unit="X", owner_user_id="alice",
            development_date="2026-05-01"))
        # Record PASS for all 11 Tier 1 gates
        for gate in REQUIRED_VALIDATION_GATES_BY_TIER[
                ModelTier.TIER_1_HIGH]:
            modgov.record_validation_test(ValidationTestResult(
                test_result_id=f"VR-{gate.value}",
                model_id=bandit.config.model_id,
                gate=gate,
                verdict=ValidationVerdict.PASS,
                test_date="2026-05-01"))
        modgov.assemble_report(
            report_id="REP-CSB-1",
            model_id=bandit.config.model_id,
            report_date="2026-05-01")
        # Now transition allowed
        updated = modgov.transition_model(
            model_id=bandit.config.model_id,
            to_state=ModelLifecycleState.IN_PRODUCTION,
            actor_user_id="alice",
            timestamp="2026-05-01T00:00:00Z")
        self.assertEqual(
            updated.current_state,
            ModelLifecycleState.IN_PRODUCTION)


class TestV1032RiskAppetiteIntegration(unittest.TestCase):
    """ENH-267 Credit Risk Appetite filter."""

    def _make_bandit(self):
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG)
        return CrossSellBanditEngine(config=BanditConfig(
            config_id="C1", model_id="M",
            feature_names=("balance_log", "intercept"),
            offer_catalog=DEFAULT_OFFER_CATALOG,
            alpha=1.0, base_seed="t"))

    def test_npl_customer_no_loan_offer(self):
        from utils.cross_sell_bandit import (
            CustomerContext, OfferType, RISK_BEARING_OFFERS)
        from utils.virtual_bank_core import LoanStatus
        bandit = self._make_bandit()
        ctx = CustomerContext(
            cif="C1",
            feature_names=("balance_log", "intercept"),
            feature_values=(5.0, 1.0),
            decision_timestamp="t",
            loan_status_observed=LoanStatus.NON_PERFORMING)
        d = bandit.decide(decision_id="D1", context=ctx)
        self.assertNotIn(
            d.chosen_offer, RISK_BEARING_OFFERS)
        self.assertIn(
            OfferType.LOAN_TOPUP, d.suppressed_by_risk_appetite)
        self.assertIn(
            OfferType.CREDIT_CARD, d.suppressed_by_risk_appetite)

    def test_dpd90_customer_no_loan_offer(self):
        """ENH-267 also applies to DELINQUENT_90 (severely delinquent)."""
        from utils.cross_sell_bandit import (
            CustomerContext, RISK_BEARING_OFFERS)
        from utils.virtual_bank_core import LoanStatus
        bandit = self._make_bandit()
        ctx = CustomerContext(
            cif="C1",
            feature_names=("balance_log", "intercept"),
            feature_values=(5.0, 1.0),
            decision_timestamp="t",
            loan_status_observed=LoanStatus.DELINQUENT_90)
        d = bandit.decide(decision_id="D1", context=ctx)
        self.assertNotIn(d.chosen_offer, RISK_BEARING_OFFERS)


class TestV1032BiasSafeguards(unittest.TestCase):
    """No protected attributes in features. Ever."""

    def test_config_rejects_gender(self):
        from utils.cross_sell_bandit import (
            BanditConfig, DEFAULT_OFFER_CATALOG)
        with self.assertRaises(ValueError):
            BanditConfig(
                config_id="C1", model_id="M",
                feature_names=("balance_log", "gender"),
                offer_catalog=DEFAULT_OFFER_CATALOG,
                alpha=1.0, base_seed="t")

    def test_config_rejects_ethnicity_substring(self):
        """customer_ethnicity_token would also be flagged."""
        from utils.cross_sell_bandit import (
            BanditConfig, DEFAULT_OFFER_CATALOG)
        with self.assertRaises(ValueError):
            BanditConfig(
                config_id="C1", model_id="M",
                feature_names=("balance_log",
                                  "customer_ethnicity_score"),
                offer_catalog=DEFAULT_OFFER_CATALOG,
                alpha=1.0, base_seed="t")

    def test_context_rejects_protected_attrs(self):
        from utils.cross_sell_bandit import CustomerContext
        with self.assertRaises(ValueError):
            CustomerContext(
                cif="C1",
                feature_names=("balance_log", "is_pep"),    # is_pep forbidden
                feature_values=(5.0, 0.0),
                decision_timestamp="t")


class TestV1032DriftMonitoring(unittest.TestCase):
    """Bandit context distributions can be monitored via v10.28 PSI."""

    def test_psi_drift_runs_against_bandit_features(self):
        from utils.model_governance import detect_drift_psi
        # Baseline: balanced; current: skewed → significant drift
        baseline = [Decimal("0.25")] * 4
        current = [Decimal("0.50"), Decimal("0.30"),
                      Decimal("0.10"), Decimal("0.10")]
        result = detect_drift_psi(
            test_id="T1", model_id="M-CSB",
            feature_name="balance_log",
            baseline_distribution=baseline,
            current_distribution=current,
            n_baseline=1000, n_current=1000,
            test_date="2026-05-01")
        self.assertNotEqual(
            result.severity.value, "INSUFFICIENT_DATA")
        # Should be measurable drift
        self.assertGreater(
            result.statistic_value, Decimal("0"))


class TestV1032BiasMonitoring(unittest.TestCase):
    """4/5ths rule applies to offer rates by protected class.

    Note: protected class is monitored POST-HOC, never used as features.
    """

    def test_four_fifths_runs_against_offer_rates(self):
        from utils.model_governance import (
            four_fifths_rule_test, BiasVerdict)
        # Hypothetical: bandit makes 50% offer-rate to ref group,
        # 30% to comparison group → potential disparate impact
        result = four_fifths_rule_test(
            test_id="T1", model_id="M-CSB",
            protected_class="gender",
            reference_group="majority",
            comparison_group="minority",
            n_reference_total=1000, n_reference_positive=500,    # 50%
            n_comparison_total=1000, n_comparison_positive=300,  # 30%
            test_date="2026-05-01")
        # Ratio = 30/50 = 0.6 → DISPARATE_IMPACT (< 0.7)
        self.assertEqual(result.verdict, BiasVerdict.DISPARATE_IMPACT)


class TestV1032SimulatorIntegration(unittest.TestCase):
    """Bandit + v10.30-v10.31 simulator: drive customers through bandit."""

    def _make_bank_with_5_customers(self):
        from utils.virtual_bank_core import (
            VirtualBankCore, VirtualBranch, VirtualCustomer,
            VirtualAccount, AccountType, AccountStatus,
            CustomerSegment)
        bank = VirtualBankCore(
            entity_name="Test", base_seed="bandit-sim",
            base_date="2026-01-01")
        bank.add_branch(VirtualBranch(
            branch_code="BR1", branch_name="X",
            region="Y", branch_type="MAIN", n_staff=5))
        for i in range(5):
            cif = f"C{i+1}"
            seg = (CustomerSegment.RETAIL if i < 3
                     else CustomerSegment.SME)
            bank.add_customer(VirtualCustomer(
                cif=cif, full_name=f"C{i+1}",
                segment=seg,
                branch_code="BR1", rm_code="RM1",
                onboarding_date="2025-01-01"))
            bank.add_account(VirtualAccount(
                account_no=f"A{i+1}", cif=cif,
                branch_code="BR1",
                account_type=AccountType.SAVINGS,
                currency="KES",
                balance=Decimal(str(10000 * (i+1))),
                status=AccountStatus.ACTIVE,
                open_date="2025-01-01"))
        return bank

    def test_extract_features_then_decide(self):
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG, DEFAULT_FEATURE_NAMES,
            extract_features_from_bank)
        bank = self._make_bank_with_5_customers()
        bandit = CrossSellBanditEngine(config=BanditConfig(
            config_id="C1", model_id="M",
            feature_names=DEFAULT_FEATURE_NAMES,
            offer_catalog=DEFAULT_OFFER_CATALOG,
            alpha=1.0, base_seed="t"))
        # Make decisions for each customer
        for i in range(5):
            cif = f"C{i+1}"
            ctx = extract_features_from_bank(
                bank=bank, cif=cif,
                feature_names=DEFAULT_FEATURE_NAMES,
                decision_timestamp="2026-05-01T00:00:00Z")
            d = bandit.decide(
                decision_id=f"D{i}", context=ctx)
            self.assertEqual(d.cif, cif)
        self.assertEqual(len(bandit.all_decisions()), 5)

    def test_bandit_learns_from_simulated_rewards(self):
        """Apply rewards; verify chosen arm n_pulls increases."""
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG, DEFAULT_FEATURE_NAMES,
            extract_features_from_bank)
        bank = self._make_bank_with_5_customers()
        bandit = CrossSellBanditEngine(config=BanditConfig(
            config_id="C1", model_id="M",
            feature_names=DEFAULT_FEATURE_NAMES,
            offer_catalog=DEFAULT_OFFER_CATALOG,
            alpha=1.0, base_seed="t"))
        # Drive 5 customers + record alternating rewards
        for i in range(5):
            cif = f"C{i+1}"
            ctx = extract_features_from_bank(
                bank=bank, cif=cif,
                feature_names=DEFAULT_FEATURE_NAMES,
                decision_timestamp="t")
            d = bandit.decide(
                decision_id=f"D{i}", context=ctx)
            bandit.record_feedback(
                feedback_id=f"F{i}",
                decision_id=f"D{i}",
                reward=1.0 if i % 2 == 0 else 0.0,
                feedback_timestamp="t")
        self.assertEqual(len(bandit.all_feedbacks()), 5)
        # At least one arm should have been pulled
        total_pulls = sum(
            arm.n_pulls
            for arm in bandit._arms.values())
        self.assertEqual(total_pulls, 5)


class TestV1032RetrainingIntegration(unittest.TestCase):
    """v10.29 retraining workflow can manage bandit retraining."""

    def test_bandit_retraining_workflow(self):
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine, RetrainingPolicy,
            RetrainingTrigger, RetrainingState,
            ChampionChallengerComparison)
        runtime = ModelGovernanceRuntimeEngine()
        runtime.register_retraining_policy(RetrainingPolicy(
            policy_id="P-CSB-1",
            model_id="M-CSB-001",
            enabled_triggers=(
                RetrainingTrigger.DRIFT_DETECTED,
                RetrainingTrigger.SCHEDULED)))
        # Trigger retraining due to drift
        runtime.trigger_retraining(
            run_id="R1", model_id="M-CSB-001",
            trigger=RetrainingTrigger.DRIFT_DETECTED,
            trigger_evidence="PSI=0.32 on balance_log",
            triggered_at="2026-06-01T00:00:00Z",
            triggered_by_user_id="alice",
            policy_id="P-CSB-1")
        # Walk through states
        for state in (RetrainingState.DATA_PREPARING,
                        RetrainingState.TRAINING,
                        RetrainingState.VALIDATING,
                        RetrainingState.APPROVED,
                        RetrainingState.DEPLOYED_AS_CHALLENGER):
            runtime.transition_retraining(
                run_id="R1", to_state=state,
                actor_user_id="alice", timestamp="t")
        # Attach winning challenger comparison
        runtime.attach_champion_challenger_comparison(
            run_id="R1",
            comparison=ChampionChallengerComparison(
                comparison_id="CC1",
                champion_model_id="M-CSB-001",
                challenger_model_id="M-CSB-001-v2",
                metric_name="offer_acceptance_rate",
                champion_value=Decimal("0.080"),
                challenger_value=Decimal("0.092"),
                improvement_pct=Decimal("15.0"),
                is_statistically_significant=True,
                sample_size=10000,
                comparison_date="2026-06-15"))
        # Promote
        final = runtime.transition_retraining(
            run_id="R1",
            to_state=RetrainingState.PROMOTED_TO_CHAMPION,
            actor_user_id="alice",
            timestamp="2026-06-20T00:00:00Z")
        self.assertEqual(
            final.state, RetrainingState.PROMOTED_TO_CHAMPION)


class TestV1032AllPriorClosureGatesPass(unittest.TestCase):
    """All 7 closure gates pass after v10.32."""

    def test_g120_climate_passes(self):
        from scripts.audit import gate_climate_esg_engines_implemented
        self.assertTrue(gate_climate_esg_engines_implemented()["passed"])

    def test_g121_credit_passes(self):
        from scripts.audit import gate_credit_engines_implemented
        self.assertTrue(gate_credit_engines_implemented()["passed"])

    def test_g122_rms_passes(self):
        from scripts.audit import gate_rms_engines_implemented
        self.assertTrue(gate_rms_engines_implemented()["passed"])

    def test_g123_audit_grc_passes(self):
        from scripts.audit import gate_audit_grc_engines_implemented
        self.assertTrue(gate_audit_grc_engines_implemented()["passed"])

    def test_g124_modgov_passes(self):
        from scripts.audit import gate_model_governance_engines_implemented
        self.assertTrue(
            gate_model_governance_engines_implemented()["passed"])

    def test_g125_virtual_bank_passes(self):
        from scripts.audit import gate_virtual_bank_simulation_implemented
        self.assertTrue(
            gate_virtual_bank_simulation_implemented()["passed"])

    def test_g126_bandit_passes(self):
        from scripts.audit import gate_cross_sell_bandit_pilot_implemented
        self.assertTrue(
            gate_cross_sell_bandit_pilot_implemented()["passed"])


class TestV1032CoexistenceWithFullStack(unittest.TestCase):
    def test_all_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_trail_certification import (
            AuditTrailCertificationEngine)
        from utils.model_governance import ModelGovernanceEngine
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine)
        from utils.virtual_bank_core import VirtualBankCore
        from utils.virtual_bank_simulator import (
            VirtualBankSimulatorEngine)
        from utils.cross_sell_bandit import (
            BanditConfig, CrossSellBanditEngine,
            DEFAULT_OFFER_CATALOG)
        engines = [
            AuditCoreEngine(entity_name="X"),
            AuditTrailCertificationEngine(entity_name="X"),
            ModelGovernanceEngine(entity_name="X"),
            ModelGovernanceRuntimeEngine(entity_name="X"),
            VirtualBankCore(
                entity_name="X", base_seed="s",
                base_date="2026-01-01"),
            VirtualBankSimulatorEngine(entity_name="X"),
            CrossSellBanditEngine(
                entity_name="X",
                config=BanditConfig(
                    config_id="C1", model_id="M",
                    feature_names=("balance_log", "intercept"),
                    offer_catalog=DEFAULT_OFFER_CATALOG,
                    alpha=1.0, base_seed="t")),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


class TestV1032MasterPromptVersion(unittest.TestCase):
    def test_master_prompt_at_v10_32_or_later(self):
        import re
        content = Path("Master_Prompt_v3.md").read_text(encoding="utf-8")
        matches = re.findall(r"v10\.(\d+)", content)
        self.assertTrue(matches)
        self.assertGreaterEqual(max(int(m) for m in matches), 32)


class TestV1032ChangelogPresent(unittest.TestCase):
    def test_changelog_v10_32_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.32.md").exists())


if __name__ == "__main__":
    unittest.main()

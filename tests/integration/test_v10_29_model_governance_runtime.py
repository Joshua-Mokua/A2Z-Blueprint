"""tests/integration/test_v10_29_model_governance_runtime.py — v10.29.

Model Governance arc CLOSURE: vendor model management (ENH-264) +
automated retraining workflow (ENH-266) + G124 audit gate locking the
7-standard closure set.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1029Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import model_governance_runtime  # noqa

    def test_public_symbols(self):
        from utils import model_governance_runtime as m
        for sym in (
            "ModelGovernanceRuntimeEngine",
            "VendorModelTier", "VendorTransparency",
            "DueDiligenceCategory",
            "REQUIRED_DD_CATEGORIES_BY_TIER",
            "DueDiligenceVerdict", "DueDiligenceFinding",
            "VendorModel",
            "DEFAULT_VENDOR_CONCENTRATION_THRESHOLD_PCT",
            "VendorConcentrationAssessment",
            "assess_vendor_concentration",
            "RetrainingTrigger", "RetrainingState",
            "ALLOWED_RETRAINING_TRANSITIONS",
            "is_valid_retraining_transition",
            "DEFAULT_DRIFT_TRIGGER_PSI",
            "DEFAULT_PERFORMANCE_TRIGGER_AUC_DROP",
            "DEFAULT_BIAS_TRIGGER_FOUR_FIFTHS",
            "RetrainingPolicy",
            "ChampionChallengerComparison",
            "RetrainingRun",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1029SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import model_governance_runtime
        model_governance_runtime.self_test()


class TestV1029G124Gate(unittest.TestCase):
    """G124 closure gate verification."""

    def test_g124_function_exists(self):
        from scripts.audit import gate_model_governance_engines_implemented
        self.assertTrue(callable(
            gate_model_governance_engines_implemented))

    def test_g124_in_gates_list(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertIn("G124", gate_ids)

    def test_g124_after_g123(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _fn in GATES]
        self.assertGreater(
            gate_ids.index("G124"), gate_ids.index("G123"))

    def test_total_gate_count_at_least_124(self):
        from scripts.audit import GATES
        self.assertGreaterEqual(len(GATES), 124)

    def test_g124_passes(self):
        from scripts.audit import gate_model_governance_engines_implemented
        r = gate_model_governance_engines_implemented()
        self.assertTrue(r["passed"],
                          f"G124 should pass; violations: "
                          f"{r.get('violations')}")

    def test_g124_summary_reports_closure_set_preserved(self):
        from scripts.audit import gate_model_governance_engines_implemented
        r = gate_model_governance_engines_implemented()
        self.assertIn("closure set 7/7 preserved", r["summary"])


class TestV1029VendorModelManagement(unittest.TestCase):
    """ENH-264 — Vendor model management."""

    def test_tier_1_requires_all_dd_categories(self):
        """Tier 1 vendor model needs all 10 DD categories per OCC 2011-12."""
        from utils.model_governance_runtime import (
            REQUIRED_DD_CATEGORIES_BY_TIER, VendorModelTier,
            DueDiligenceCategory)
        t1 = REQUIRED_DD_CATEGORIES_BY_TIER[VendorModelTier.TIER_1_HIGH]
        self.assertEqual(len(t1), len(DueDiligenceCategory))

    def test_tier_3_requires_minimal_dd(self):
        from utils.model_governance_runtime import (
            REQUIRED_DD_CATEGORIES_BY_TIER, VendorModelTier)
        t1 = REQUIRED_DD_CATEGORIES_BY_TIER[VendorModelTier.TIER_1_HIGH]
        t3 = REQUIRED_DD_CATEGORIES_BY_TIER[VendorModelTier.TIER_3_LOW]
        self.assertLess(len(t3), len(t1))

    def test_dd_completeness_blocks_on_unsatisfactory(self):
        """Even with all categories covered, UNSATISFACTORY blocks."""
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine, VendorModel,
            VendorModelTier, VendorTransparency,
            DueDiligenceFinding, DueDiligenceCategory,
            DueDiligenceVerdict,
            REQUIRED_DD_CATEGORIES_BY_TIER)
        eng = ModelGovernanceRuntimeEngine()
        eng.register_vendor_model(VendorModel(
            vendor_model_id="VM1", vendor_name="X",
            vendor_legal_entity="X Corp",
            vendor_country="US", product_name="Y",
            product_version="1",
            tier=VendorModelTier.TIER_3_LOW,
            transparency=VendorTransparency.LIMITED_DISCLOSURE,
            contract_start_date="2025-01-01",
            contract_end_date="2027-12-31"))
        cats = list(REQUIRED_DD_CATEGORIES_BY_TIER[
            VendorModelTier.TIER_3_LOW])
        for i, cat in enumerate(cats):
            verdict = (DueDiligenceVerdict.UNSATISFACTORY if i == 0
                         else DueDiligenceVerdict.SATISFACTORY)
            eng.record_due_diligence(DueDiligenceFinding(
                finding_id=f"F{i}", vendor_model_id="VM1",
                category=cat, verdict=verdict,
                evidence_count=2, assessor_user_id="alice",
                assessment_date="2026-05-01"))
        status = eng.due_diligence_status("VM1")
        self.assertFalse(status["is_dd_complete"])
        self.assertEqual(status["n_blocking_findings"], 1)

    def test_concentration_threshold_per_cbk(self):
        """CBK Outsourcing Guideline 2018: 25% threshold."""
        from utils.model_governance_runtime import (
            DEFAULT_VENDOR_CONCENTRATION_THRESHOLD_PCT)
        self.assertEqual(
            DEFAULT_VENDOR_CONCENTRATION_THRESHOLD_PCT, Decimal("25"))

    def test_concentration_breach_detected(self):
        from utils.model_governance_runtime import (
            assess_vendor_concentration)
        a = assess_vendor_concentration(
            assessment_id="A1", vendor_name="Acme",
            category="credit_scoring",
            n_models_from_vendor=3,
            n_models_in_category_total=10,
            assessment_date="2026-05-01")
        self.assertEqual(a.concentration_pct, Decimal("30"))
        self.assertTrue(a.is_breach)


class TestV1029RetrainingWorkflow(unittest.TestCase):
    """ENH-266 — Automated retraining workflow."""

    def test_state_machine_cannot_skip_to_promoted(self):
        from utils.model_governance_runtime import (
            is_valid_retraining_transition, RetrainingState)
        self.assertFalse(is_valid_retraining_transition(
            RetrainingState.TRIGGERED,
            RetrainingState.PROMOTED_TO_CHAMPION))

    def test_terminal_states_no_transitions(self):
        from utils.model_governance_runtime import (
            ALLOWED_RETRAINING_TRANSITIONS, RetrainingState)
        for terminal in (
                RetrainingState.PROMOTED_TO_CHAMPION,
                RetrainingState.REJECTED,
                RetrainingState.FAILED):
            self.assertEqual(
                len(ALLOWED_RETRAINING_TRANSITIONS[terminal]), 0)

    def test_promotion_blocked_without_comparison(self):
        """Champion-challenger gate per SR 11-7 §V.B."""
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine, RetrainingTrigger,
            RetrainingState)
        eng = ModelGovernanceRuntimeEngine()
        eng.trigger_retraining(
            run_id="R1", model_id="M1",
            trigger=RetrainingTrigger.MANUAL,
            trigger_evidence="x", triggered_at="t",
            triggered_by_user_id="alice")
        for state in (RetrainingState.DATA_PREPARING,
                        RetrainingState.TRAINING,
                        RetrainingState.VALIDATING,
                        RetrainingState.APPROVED,
                        RetrainingState.DEPLOYED_AS_CHALLENGER):
            eng.transition_retraining(
                run_id="R1", to_state=state,
                actor_user_id="alice", timestamp="t")
        with self.assertRaises(ValueError):
            eng.transition_retraining(
                run_id="R1",
                to_state=RetrainingState.PROMOTED_TO_CHAMPION,
                actor_user_id="alice", timestamp="t")

    def test_promotion_blocked_when_challenger_loses(self):
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine, RetrainingTrigger,
            RetrainingState, ChampionChallengerComparison)
        eng = ModelGovernanceRuntimeEngine()
        eng.trigger_retraining(
            run_id="R1", model_id="M1",
            trigger=RetrainingTrigger.MANUAL,
            trigger_evidence="x", triggered_at="t",
            triggered_by_user_id="alice")
        for state in (RetrainingState.DATA_PREPARING,
                        RetrainingState.TRAINING,
                        RetrainingState.VALIDATING,
                        RetrainingState.APPROVED,
                        RetrainingState.DEPLOYED_AS_CHALLENGER):
            eng.transition_retraining(
                run_id="R1", to_state=state,
                actor_user_id="alice", timestamp="t")
        eng.attach_champion_challenger_comparison(
            run_id="R1",
            comparison=ChampionChallengerComparison(
                comparison_id="C1", champion_model_id="M1",
                challenger_model_id="M1-v2",
                metric_name="AUC",
                champion_value=Decimal("0.72"),
                challenger_value=Decimal("0.728"),
                improvement_pct=Decimal("1.1"),     # < 2% min
                is_statistically_significant=True,
                sample_size=10000,
                comparison_date="2026-05-15"))
        with self.assertRaises(ValueError):
            eng.transition_retraining(
                run_id="R1",
                to_state=RetrainingState.PROMOTED_TO_CHAMPION,
                actor_user_id="alice", timestamp="t")

    def test_promotion_succeeds_when_challenger_wins(self):
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine, RetrainingTrigger,
            RetrainingState, ChampionChallengerComparison)
        eng = ModelGovernanceRuntimeEngine()
        eng.trigger_retraining(
            run_id="R1", model_id="M1",
            trigger=RetrainingTrigger.DRIFT_DETECTED,
            trigger_evidence="PSI=0.35",
            triggered_at="t", triggered_by_user_id="alice")
        for state in (RetrainingState.DATA_PREPARING,
                        RetrainingState.TRAINING,
                        RetrainingState.VALIDATING,
                        RetrainingState.APPROVED,
                        RetrainingState.DEPLOYED_AS_CHALLENGER):
            eng.transition_retraining(
                run_id="R1", to_state=state,
                actor_user_id="alice", timestamp="t")
        eng.attach_champion_challenger_comparison(
            run_id="R1",
            comparison=ChampionChallengerComparison(
                comparison_id="C1", champion_model_id="M1",
                challenger_model_id="M1-v2",
                metric_name="AUC",
                champion_value=Decimal("0.72"),
                challenger_value=Decimal("0.75"),
                improvement_pct=Decimal("4.2"),
                is_statistically_significant=True,
                sample_size=10000,
                comparison_date="2026-05-15"))
        final = eng.transition_retraining(
            run_id="R1",
            to_state=RetrainingState.PROMOTED_TO_CHAMPION,
            actor_user_id="alice",
            timestamp="2026-05-20T00:00:00Z")
        self.assertEqual(
            final.state, RetrainingState.PROMOTED_TO_CHAMPION)


class TestV1029ClosureChangelog(unittest.TestCase):
    """All v10.28-v10.29 CHANGELOGs present."""

    def test_changelog_v10_28_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.28.md").exists())

    def test_changelog_v10_29_exists(self):
        self.assertTrue(Path("CHANGELOG_v10.29.md").exists())


class TestV1029MasterPromptVersion(unittest.TestCase):
    def test_master_prompt_at_v10_29_or_later(self):
        import re
        content = Path("Master_Prompt_v3.md").read_text(encoding="utf-8")
        matches = re.findall(r"v10\.(\d+)", content)
        self.assertTrue(matches)
        self.assertGreaterEqual(max(int(m) for m in matches), 29)


class TestV1029EngineHubIntegration(unittest.TestCase):
    """Engine Hub Tier 12 has both modgov engines."""

    def test_tier_12_in_admin_page(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        self.assertIn("Tier 12", content)

    def test_both_modgov_engines_in_hub(self):
        content = Path("pages/7_admin.py").read_text(encoding="utf-8")
        for engine in (
            "model_governance",
            "model_governance_runtime",
        ):
            self.assertIn(f'"{engine}"', content,
                            f"Engine Hub missing {engine}")


class TestV1029AllRequiredEnginesImport(unittest.TestCase):
    def test_both_modgov_engines_import(self):
        for module in (
            "utils.model_governance",
            "utils.model_governance_runtime",
        ):
            try:
                __import__(module)
            except Exception as e:
                self.fail(f"Failed to import {module}: {e}")


class TestV1029AllPhase2ArcsClosed(unittest.TestCase):
    """All 5 closed Phase 2 arcs have closure gates passing."""

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


class TestV1029CoexistenceWithPriorEngines(unittest.TestCase):
    """v10.29 coexists with v10.23-v10.28 stack."""

    def test_all_modgov_and_audit_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_trail_certification import (
            AuditTrailCertificationEngine)
        from utils.model_governance import ModelGovernanceEngine
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine)
        engines = [
            AuditCoreEngine(entity_name="X"),
            AuditTrailCertificationEngine(entity_name="X"),
            ModelGovernanceEngine(entity_name="X"),
            ModelGovernanceRuntimeEngine(entity_name="X"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

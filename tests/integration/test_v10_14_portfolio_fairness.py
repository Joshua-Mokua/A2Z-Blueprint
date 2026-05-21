"""tests/integration/test_v10_14_portfolio_fairness.py — v10.14.

Phase 2 batch 8 (Credit batch 4): portfolio monitoring + collections + fairness + unstructured.
ENH-126, ENH-128, ENH-CRD-R1, ENH-CRD-R6.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1014Imports(unittest.TestCase):
    def test_portfolio_monitoring_imports(self):
        from utils import portfolio_monitoring  # noqa
    def test_fairness_testing_imports(self):
        from utils import fairness_testing  # noqa

    def test_portfolio_monitoring_public_symbols(self):
        from utils import portfolio_monitoring as m
        for sym in (
            "CBKRiskClassification", "DPDBucket",
            "compute_dpd_bucket", "cbk_classification_for_dpd",
            "EWSSignal", "EWSLevel", "EWS_SIGNAL_SEVERITY",
            "AccountSnapshot", "EWSAssessment",
            "detect_ews_signals", "assess_ews",
            "RollRateAnalysis", "compute_roll_rates",
            "CollectionStrategy", "DEFAULT_COLLECTION_LADDER",
            "CollectionsAssessment", "assign_collection_strategy",
            "UnstructuredSignalType", "UnstructuredSignal",
            "UnstructuredAssessment", "aggregate_unstructured_signals",
            "PortfolioMonitoringEngine",
        ):
            self.assertTrue(hasattr(m, sym), f"missing PM public: {sym}")

    def test_fairness_testing_public_symbols(self):
        from utils import fairness_testing as m
        for sym in (
            "ProtectedAttribute", "FairnessVerdict",
            "OutcomeRecord", "DisparateImpactResult",
            "EqualOpportunityResult", "FairnessReport",
            "compute_disparate_impact_ratio",
            "compute_equal_opportunity_difference",
            "lda_latent_bias_search",
            "generate_fairness_report",
            "FOUR_FIFTHS_THRESHOLD",
            "MIN_GROUP_SAMPLE_SIZE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing FT public: {sym}")


class TestV1014SelfTests(unittest.TestCase):
    def test_portfolio_monitoring_self_test(self):
        from utils import portfolio_monitoring
        portfolio_monitoring.self_test()

    def test_fairness_testing_self_test(self):
        from utils import fairness_testing
        fairness_testing.self_test()


class TestV1014RegistryAlignment(unittest.TestCase):
    def test_17_credit_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "credit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 17)

    def test_v10_14_specific_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "credit" and s.status == "active"}
        for sid in ("ENH-126", "ENH-128", "ENH-CRD-R1", "ENH-CRD-R6"):
            self.assertIn(sid, active_ids)


class TestV1014EarlyWarning(unittest.TestCase):
    """ENH-126 — Early warning system."""

    def test_clean_account_green(self):
        from utils.portfolio_monitoring import (
            AccountSnapshot, assess_ews, EWSLevel)
        s = AccountSnapshot(
            account_id="A", snapshot_at="t",
            outstanding_kes=Decimal("100000"),
            arrears_kes=Decimal("0"), dpd=0)
        a = assess_ews(s)
        self.assertEqual(a.level, EWSLevel.GREEN)

    def test_severe_signal_red(self):
        from utils.portfolio_monitoring import (
            AccountSnapshot, assess_ews, EWSLevel)
        s = AccountSnapshot(
            account_id="A", snapshot_at="t",
            outstanding_kes=Decimal("100000"),
            arrears_kes=Decimal("0"), dpd=0,
            utilization_pct=Decimal("125"))   # limit breach (sev 3)
        a = assess_ews(s)
        self.assertEqual(a.level, EWSLevel.RED)

    def test_dpd_91_180_doubtful_classification(self):
        from utils.portfolio_monitoring import (
            cbk_classification_for_dpd, CBKRiskClassification)
        self.assertEqual(
            cbk_classification_for_dpd(120),
            CBKRiskClassification.DOUBTFUL)

    def test_dpd_181_plus_loss_classification(self):
        from utils.portfolio_monitoring import (
            cbk_classification_for_dpd, CBKRiskClassification)
        self.assertEqual(
            cbk_classification_for_dpd(200),
            CBKRiskClassification.LOSS)


class TestV1014Collections(unittest.TestCase):
    """ENH-128 — Collections strategy."""

    def test_current_account_no_action(self):
        from utils.portfolio_monitoring import (
            AccountSnapshot, assign_collection_strategy,
            CollectionStrategy)
        s = AccountSnapshot(
            account_id="A", snapshot_at="t",
            outstanding_kes=Decimal("100000"),
            arrears_kes=Decimal("0"), dpd=0)
        c = assign_collection_strategy(s)
        self.assertEqual(c.recommended_strategy,
                            CollectionStrategy.NO_ACTION)

    def test_dpd_120_collateralized_repossession(self):
        from utils.portfolio_monitoring import (
            AccountSnapshot, assign_collection_strategy,
            CollectionStrategy)
        s = AccountSnapshot(
            account_id="A", snapshot_at="t",
            outstanding_kes=Decimal("100000"),
            arrears_kes=Decimal("50000"), dpd=120)
        c = assign_collection_strategy(s, has_collateral=True)
        self.assertEqual(c.recommended_strategy,
                            CollectionStrategy.REPOSSESSION)

    def test_recovery_decays_with_dpd(self):
        from utils.portfolio_monitoring import (
            AccountSnapshot, assign_collection_strategy)
        snap = lambda dpd: AccountSnapshot(
            account_id="A", snapshot_at="t",
            outstanding_kes=Decimal("100000"),
            arrears_kes=Decimal("0"), dpd=dpd)
        p_curr = assign_collection_strategy(snap(0))
        p_180 = assign_collection_strategy(snap(200))
        self.assertGreater(p_curr.recovery_probability,
                              p_180.recovery_probability)


class TestV1014Unstructured(unittest.TestCase):
    """ENH-CRD-R6 — Unstructured signals."""

    def test_high_severity_action_required(self):
        from utils.portfolio_monitoring import (
            UnstructuredSignal, UnstructuredSignalType,
            aggregate_unstructured_signals)
        sig = UnstructuredSignal(
            account_id="X",
            signal_type=UnstructuredSignalType.REGULATORY_FILING,
            detected_at="t", source="OFAC",
            confidence=Decimal("0.95"))
        a = aggregate_unstructured_signals([sig])
        self.assertTrue(a.has_action_required)

    def test_low_confidence_filtered(self):
        from utils.portfolio_monitoring import (
            UnstructuredSignal, UnstructuredSignalType,
            aggregate_unstructured_signals)
        sig = UnstructuredSignal(
            account_id="X",
            signal_type=UnstructuredSignalType.NEGATIVE_NEWS,
            detected_at="t", source="blog",
            confidence=Decimal("0.2"))
        a = aggregate_unstructured_signals([sig])
        self.assertFalse(a.has_action_required)
        self.assertEqual(a.signal_count, 0)


class TestV1014FairnessDIR(unittest.TestCase):
    """ENH-CRD-R1 — Disparate impact ratio (4/5ths rule)."""

    def test_close_rates_pass(self):
        from utils.fairness_testing import (
            OutcomeRecord, ProtectedAttribute,
            compute_disparate_impact_ratio, FairnessVerdict)
        protected = [
            OutcomeRecord(
                application_id=f"P{i}",
                decision=("APPROVE" if i < 80 else "DECLINE"),
                protected_attribute=ProtectedAttribute.GENDER,
                protected_value="FEMALE",
                is_reference_group=False)
            for i in range(100)]
        reference = [
            OutcomeRecord(
                application_id=f"R{i}",
                decision=("APPROVE" if i < 90 else "DECLINE"),
                protected_attribute=ProtectedAttribute.GENDER,
                protected_value="MALE",
                is_reference_group=True)
            for i in range(100)]
        r = compute_disparate_impact_ratio(
            protected_records=protected, reference_records=reference)
        self.assertEqual(r.verdict, FairnessVerdict.PASS)

    def test_disparate_rates_violation(self):
        from utils.fairness_testing import (
            OutcomeRecord, ProtectedAttribute,
            compute_disparate_impact_ratio, FairnessVerdict)
        protected = [
            OutcomeRecord(
                application_id=f"P{i}",
                decision=("APPROVE" if i < 40 else "DECLINE"),
                protected_attribute=ProtectedAttribute.GENDER,
                protected_value="FEMALE",
                is_reference_group=False)
            for i in range(100)]
        reference = [
            OutcomeRecord(
                application_id=f"R{i}",
                decision=("APPROVE" if i < 90 else "DECLINE"),
                protected_attribute=ProtectedAttribute.GENDER,
                protected_value="MALE",
                is_reference_group=True)
            for i in range(100)]
        r = compute_disparate_impact_ratio(
            protected_records=protected, reference_records=reference)
        self.assertEqual(r.verdict,
                            FairnessVerdict.POTENTIAL_DISPARATE_IMPACT)
        # 0.40 / 0.90 = 0.444 < 0.80
        self.assertLess(r.disparate_impact_ratio, Decimal("0.80"))

    def test_insufficient_sample(self):
        from utils.fairness_testing import (
            OutcomeRecord, ProtectedAttribute,
            compute_disparate_impact_ratio, FairnessVerdict)
        protected = [OutcomeRecord(
            application_id=f"P{i}", decision="APPROVE",
            protected_attribute=ProtectedAttribute.RACE,
            protected_value="X", is_reference_group=False)
            for i in range(5)]
        reference = [OutcomeRecord(
            application_id=f"R{i}", decision="APPROVE",
            protected_attribute=ProtectedAttribute.RACE,
            protected_value="REF", is_reference_group=True)
            for i in range(5)]
        r = compute_disparate_impact_ratio(
            protected_records=protected, reference_records=reference)
        self.assertEqual(r.verdict, FairnessVerdict.INSUFFICIENT_DATA)


class TestV1014FairnessReport(unittest.TestCase):
    def test_report_aggregates_results(self):
        from utils.fairness_testing import (
            OutcomeRecord, ProtectedAttribute,
            generate_fairness_report)
        protected = [
            OutcomeRecord(
                application_id=f"P{i}",
                decision=("APPROVE" if i < 40 else "DECLINE"),
                protected_attribute=ProtectedAttribute.GENDER,
                protected_value="FEMALE",
                is_reference_group=False)
            for i in range(100)]
        reference = [
            OutcomeRecord(
                application_id=f"R{i}",
                decision=("APPROVE" if i < 80 else "DECLINE"),
                protected_attribute=ProtectedAttribute.GENDER,
                protected_value="MALE",
                is_reference_group=True)
            for i in range(100)]
        report = generate_fairness_report(
            entity_name="Test Bank",
            period_start="2025-01-01", period_end="2025-12-31",
            records=protected + reference)
        self.assertEqual(report.n_total_applications, 200)
        self.assertGreater(len(report.disparate_impact_results), 0)


class TestV1014Coexistence(unittest.TestCase):
    def test_v10_11_v10_14_engines_coexist(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        from utils.portfolio_monitoring import PortfolioMonitoringEngine
        u = AIUnderwritingEngine(entity_name="X")
        p = PortfolioMonitoringEngine(entity_name="X")
        self.assertEqual(u.entity_name, p.entity_name)


if __name__ == "__main__":
    unittest.main()

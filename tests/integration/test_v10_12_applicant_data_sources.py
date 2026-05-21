"""tests/integration/test_v10_12_applicant_data_sources.py — v10.12.

Phase 2 batch 6 (Credit batch 2): alt data + bureau + eKYC + fraud.
ENH-120, ENH-121, ENH-122, ENH-129.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1012Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import applicant_data_sources  # noqa

    def test_public_symbols(self):
        from utils import applicant_data_sources as m
        for sym in (
            "AltDataSource", "AltDataRecord", "AltDataScore",
            "compute_alt_data_score",
            "BureauProvider", "BureauReport", "BUREAU_SCORE_RANGES",
            "fetch_bureau_report", "aggregate_bureau_reports",
            "EKYCResult", "EKYCCheckResult", "EKYCAssessment",
            "EKYC_REQUIRED_CHECKS", "assess_ekyc",
            "FraudSignal", "FraudCheckResult",
            "FRAUD_SIGNAL_WEIGHTS", "assess_fraud",
            "evaluate_velocity_rules",
            "ApplicantDataAggregator",
            "ALT_DATA_FRESH_DAYS", "ALT_DATA_MIN_HISTORY_MONTHS",
            "BIOMETRIC_MATCH_VERIFIED_ABOVE",
            "VELOCITY_RULE_APPLICATIONS_PER_30MIN",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1012SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import applicant_data_sources
        applicant_data_sources.self_test()


class TestV1012RegistryAlignment(unittest.TestCase):
    def test_8_credit_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "credit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 8)

    def test_v10_12_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "credit" and s.status == "active"}
        for sid in ("ENH-120", "ENH-121", "ENH-122", "ENH-129"):
            self.assertIn(sid, active_ids)


class TestV1012AltData(unittest.TestCase):
    """ENH-120 — alternative data intelligence."""

    def test_thin_file_no_alt_data_zero_score(self):
        from utils.applicant_data_sources import compute_alt_data_score
        s = compute_alt_data_score([])
        self.assertEqual(s.score, Decimal("0"))
        self.assertEqual(s.confidence, Decimal("0"))

    def test_consent_required(self):
        from utils.applicant_data_sources import (
            AltDataRecord, AltDataSource, compute_alt_data_score)
        r = AltDataRecord(
            source=AltDataSource.MOBILE_MONEY_MPESA,
            period_start="2025-01-01", period_end="2025-12-31",
            months_of_history=12,
            on_time_payment_count=12, late_payment_count=0,
            consent_obtained=False)
        s = compute_alt_data_score([r])
        self.assertEqual(s.score, Decimal("0"))

    def test_high_signal_records_high_confidence(self):
        from utils.applicant_data_sources import (
            AltDataRecord, AltDataSource, compute_alt_data_score)
        records = [
            AltDataRecord(
                source=AltDataSource.MOBILE_MONEY_MPESA,
                period_start="2025-01-01", period_end="2025-12-31",
                months_of_history=12,
                inflow_kes_total=Decimal("600000"),
                on_time_payment_count=12, late_payment_count=0,
                consent_obtained=True),
            AltDataRecord(
                source=AltDataSource.BANK_STATEMENT_ANALYSIS,
                period_start="2025-01-01", period_end="2025-12-31",
                months_of_history=12,
                inflow_kes_total=Decimal("1800000"),
                on_time_payment_count=24, late_payment_count=0,
                consent_obtained=True),
        ]
        s = compute_alt_data_score(records)
        self.assertGreater(s.score, Decimal("70"))
        self.assertGreaterEqual(s.confidence, Decimal("0.5"))


class TestV1012Bureau(unittest.TestCase):
    """ENH-129 — credit bureau integration."""

    def test_three_kenya_crbs_listed(self):
        from utils.applicant_data_sources import BureauProvider
        self.assertEqual(len(BureauProvider.all_kenya_licensed()), 3)

    def test_no_fetcher_returns_none(self):
        """Rule 7 — no silent fabrication."""
        from utils.applicant_data_sources import (
            fetch_bureau_report, BureauProvider)
        r = fetch_bureau_report(
            applicant_id="X", provider=BureauProvider.TRANSUNION_KE)
        self.assertIsNone(r)

    def test_failing_fetcher_returns_none(self):
        from utils.applicant_data_sources import (
            fetch_bureau_report, BureauProvider)
        r = fetch_bureau_report(
            applicant_id="X", provider=BureauProvider.METROPOL_KE,
            fetcher=lambda *a, **k: (_ for _ in ()).throw(ConnectionError("down")))
        self.assertIsNone(r)

    def test_aggregate_takes_worst_case(self):
        from utils.applicant_data_sources import (
            BureauReport, BureauProvider, BUREAU_SCORE_RANGES,
            aggregate_bureau_reports)
        rs = [
            BureauReport(
                provider=BureauProvider.TRANSUNION_KE,
                applicant_id="X", report_pulled_at="",
                bureau_score=Decimal("700"),
                score_range=BUREAU_SCORE_RANGES[BureauProvider.TRANSUNION_KE],
                file_present=True,
                delinquent_accounts=1, days_past_due_max=15,
                bankruptcies=0),
            BureauReport(
                provider=BureauProvider.METROPOL_KE,
                applicant_id="X", report_pulled_at="",
                bureau_score=Decimal("400"),
                score_range=BUREAU_SCORE_RANGES[BureauProvider.METROPOL_KE],
                file_present=True,
                delinquent_accounts=3, days_past_due_max=90,
                bankruptcies=1),
        ]
        agg = aggregate_bureau_reports(rs)
        self.assertEqual(agg["max_delinquencies"], 3)
        self.assertEqual(agg["max_dpd"], 90)
        self.assertEqual(agg["max_bankruptcies"], 1)


class TestV1012EKYC(unittest.TestCase):
    """ENH-121 — digital identity verification."""

    def test_full_pass_verified(self):
        from utils.applicant_data_sources import assess_ekyc, EKYCResult
        r = assess_ekyc(
            applicant_id="X", timestamp="t",
            iprs_lookup_passed=True,
            biometric_match_score=Decimal("0.95"),
            document_auth_passed=True,
            mobile_number_verified=True,
            pep_hit=False, sanctions_hit=False)
        self.assertEqual(r.overall_result, EKYCResult.VERIFIED)
        self.assertTrue(r.is_verified())

    def test_sanctions_hit_blocks(self):
        from utils.applicant_data_sources import assess_ekyc, EKYCResult
        r = assess_ekyc(
            applicant_id="X", timestamp="t",
            iprs_lookup_passed=True,
            biometric_match_score=Decimal("0.95"),
            document_auth_passed=True,
            mobile_number_verified=True,
            pep_hit=False, sanctions_hit=True)
        self.assertEqual(r.overall_result, EKYCResult.FAILED)

    def test_pep_inconclusive_not_failed(self):
        """PEP requires EDD, not auto-decline."""
        from utils.applicant_data_sources import assess_ekyc, EKYCResult
        r = assess_ekyc(
            applicant_id="X", timestamp="t",
            iprs_lookup_passed=True,
            biometric_match_score=Decimal("0.95"),
            document_auth_passed=True,
            mobile_number_verified=True,
            pep_hit=True, sanctions_hit=False)
        self.assertEqual(r.overall_result, EKYCResult.INCONCLUSIVE)


class TestV1012Fraud(unittest.TestCase):
    """ENH-122 — real-time fraud detection."""

    def test_known_fraud_ring_blocks(self):
        from utils.applicant_data_sources import (
            assess_fraud, FraudSignal)
        r = assess_fraud(
            applicant_id="X", timestamp="t",
            signals=[FraudSignal.KNOWN_FRAUD_RING_MATCH])
        self.assertEqual(r.decision_recommendation, "BLOCK")

    def test_score_capped_at_100(self):
        from utils.applicant_data_sources import (
            assess_fraud, FraudSignal)
        r = assess_fraud(
            applicant_id="X", timestamp="t",
            signals=[
                FraudSignal.SYNTHETIC_IDENTITY_PATTERN,
                FraudSignal.DOCUMENT_PHOTO_MANIPULATED,
                FraudSignal.KNOWN_FRAUD_RING_MATCH])
        self.assertEqual(r.fraud_score, Decimal("100"))

    def test_velocity_rules_fire_appropriately(self):
        from utils.applicant_data_sources import (
            evaluate_velocity_rules, FraudSignal)
        sigs = evaluate_velocity_rules(
            identifier="IP", apps_last_30min=10, apps_last_24h=20)
        self.assertIn(FraudSignal.VELOCITY_HIGH_FREQUENCY, sigs)


class TestV1012Aggregator(unittest.TestCase):
    """End-to-end ApplicantDataAggregator orchestration."""

    def test_clean_full_profile_proceeds(self):
        from utils.applicant_data_sources import (
            ApplicantDataAggregator, AltDataRecord, AltDataSource,
            BureauReport, BureauProvider, BUREAU_SCORE_RANGES,
            assess_ekyc, assess_fraud)
        eng = ApplicantDataAggregator()
        profile = eng.build_profile(
            applicant_id="STRONG", timestamp="t",
            alt_data_records=[
                AltDataRecord(
                    source=AltDataSource.BANK_STATEMENT_ANALYSIS,
                    period_start="2025-01-01", period_end="2025-12-31",
                    months_of_history=12,
                    inflow_kes_total=Decimal("1200000"),
                    on_time_payment_count=12, late_payment_count=0,
                    consent_obtained=True)],
            bureau_reports=[
                BureauReport(
                    provider=BureauProvider.TRANSUNION_KE,
                    applicant_id="STRONG", report_pulled_at="",
                    bureau_score=Decimal("750"),
                    score_range=BUREAU_SCORE_RANGES[BureauProvider.TRANSUNION_KE],
                    file_present=True,
                    delinquent_accounts=0, bankruptcies=0)],
            ekyc_assessment=assess_ekyc(
                applicant_id="STRONG", timestamp="t",
                iprs_lookup_passed=True,
                biometric_match_score=Decimal("0.95"),
                document_auth_passed=True,
                mobile_number_verified=True,
                pep_hit=False, sanctions_hit=False),
            fraud_check=assess_fraud(applicant_id="STRONG", timestamp="t",
                                       signals=[]))
        self.assertEqual(profile["recommendation"], "PROCEED")

    def test_thin_file_refers(self):
        from utils.applicant_data_sources import (
            ApplicantDataAggregator, assess_ekyc, assess_fraud)
        eng = ApplicantDataAggregator()
        profile = eng.build_profile(
            applicant_id="THIN", timestamp="t",
            ekyc_assessment=assess_ekyc(
                applicant_id="THIN", timestamp="t",
                iprs_lookup_passed=True,
                biometric_match_score=Decimal("0.90"),
                document_auth_passed=True,
                mobile_number_verified=True,
                pep_hit=False, sanctions_hit=False),
            fraud_check=assess_fraud(applicant_id="THIN", timestamp="t",
                                       signals=[]))
        self.assertEqual(profile["recommendation"], "REFER")


class TestV1012CoexistenceWithV1011(unittest.TestCase):
    def test_v10_11_and_v10_12_coexist(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        from utils.applicant_data_sources import ApplicantDataAggregator
        u = AIUnderwritingEngine(entity_name="Ecobank Kenya")
        d = ApplicantDataAggregator(entity_name="Ecobank Kenya")
        self.assertEqual(u.entity_name, d.entity_name)


if __name__ == "__main__":
    unittest.main()

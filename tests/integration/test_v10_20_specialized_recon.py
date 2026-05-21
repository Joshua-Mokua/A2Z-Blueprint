"""tests/integration/test_v10_20_specialized_recon.py — v10.20.

Phase 2 batch 3 (RMS arc batch 3): specialized reconciliation surfaces.
ENH-185 (CBK regulatory) + ENH-186 (Nostro/Vostro) + ENH-187 (IC + suspense)
+ ENH-RMS-R6 (real-time KEPSS/PesaLink).
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1020Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import reconciliation_specialized  # noqa

    def test_public_symbols(self):
        from utils import reconciliation_specialized as m
        for sym in (
            # CBK regulatory
            "CBKReturnType", "ReturnFrequency",
            "DEFAULT_RETURN_DEADLINE_DAYS",
            "ReturnStatus", "DeadlineSeverity",
            "CBKReturnRecord", "compute_return_deadline",
            # Nostro/Vostro
            "CorrespondentAccountType", "SwiftMessageType",
            "StaleAgeBucket", "compute_stale_age_bucket",
            "NostroVostroAccount", "StaleItem",
            "FXRevaluationAdjustment", "compute_fx_reval",
            # Intercompany + Suspense
            "IntercompanyEntityType", "IntercompanyCounterparty",
            "SuspenseCategory", "DEFAULT_SUSPENSE_MAX_AGE_DAYS",
            "SuspenseItem",
            # Real-time
            "RealTimePaymentSystem",
            "RealTimeReconciliationConfig",
            "RealTimePaymentObservation",
            "RealTimeMatchVerdict", "RealTimeMatchResult",
            "assess_real_time_match",
            # Engine
            "SpecializedReconciliationEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1020SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import reconciliation_specialized
        reconciliation_specialized.self_test()


class TestV1020RegistryAlignment(unittest.TestCase):
    def test_12_rms_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "rms" and s.status == "active"]
        self.assertGreaterEqual(len(active), 12)

    def test_v10_20_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "rms" and s.status == "active"}
        for sid in ("ENH-185", "ENH-186", "ENH-187", "ENH-RMS-R6"):
            self.assertIn(sid, active_ids)


class TestV1020CBKRegulatory(unittest.TestCase):
    """ENH-185 — CBK regulatory reconciliation."""

    def test_monthly_deadline_is_15_days(self):
        from utils.reconciliation_specialized import (
            CBKReturnType, compute_return_deadline)
        dl = compute_return_deadline(
            return_type=CBKReturnType.MONTHLY_RETURN,
            period_end=date(2026, 4, 30))
        self.assertEqual(dl, date(2026, 5, 15))

    def test_daily_deadline_is_next_day(self):
        from utils.reconciliation_specialized import (
            CBKReturnType, compute_return_deadline)
        dl = compute_return_deadline(
            return_type=CBKReturnType.DAILY_RETURN,
            period_end=date(2026, 4, 30))
        self.assertEqual(dl, date(2026, 5, 1))

    def test_amber_severity_at_3_days(self):
        from utils.reconciliation_specialized import (
            CBKReturnType, CBKReturnRecord, ReturnStatus,
            DeadlineSeverity)
        r = CBKReturnRecord(
            return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
            period_end="2026-04-30", deadline="2026-05-15",
            status=ReturnStatus.PENDING)
        self.assertEqual(
            r.severity(as_of=date(2026, 5, 12)), DeadlineSeverity.AMBER)

    def test_breached_after_deadline(self):
        from utils.reconciliation_specialized import (
            CBKReturnType, CBKReturnRecord, ReturnStatus,
            DeadlineSeverity)
        r = CBKReturnRecord(
            return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
            period_end="2026-04-30", deadline="2026-05-15",
            status=ReturnStatus.PENDING)
        self.assertEqual(
            r.severity(as_of=date(2026, 5, 16)),
            DeadlineSeverity.BREACHED)

    def test_submitted_overrides_severity(self):
        """Even past deadline, SUBMITTED returns OK."""
        from utils.reconciliation_specialized import (
            CBKReturnType, CBKReturnRecord, ReturnStatus,
            DeadlineSeverity)
        r = CBKReturnRecord(
            return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
            period_end="2026-04-30", deadline="2026-05-15",
            status=ReturnStatus.SUBMITTED,
            submitted_at="2026-05-10T16:00:00Z")
        self.assertEqual(
            r.severity(as_of=date(2026, 6, 1)), DeadlineSeverity.OK)


class TestV1020NostroVostro(unittest.TestCase):
    """ENH-186 — Nostro/Vostro reconciliation."""

    def test_stale_age_bucket_thresholds(self):
        from utils.reconciliation_specialized import (
            StaleAgeBucket, compute_stale_age_bucket)
        self.assertEqual(compute_stale_age_bucket(15),
                          StaleAgeBucket.FRESH_0_30)
        self.assertEqual(compute_stale_age_bucket(45),
                          StaleAgeBucket.AGING_31_60)
        self.assertEqual(compute_stale_age_bucket(75),
                          StaleAgeBucket.OVERDUE_61_90)
        self.assertEqual(compute_stale_age_bucket(120),
                          StaleAgeBucket.BREACH_91_PLUS)

    def test_nostro_variance_calculation(self):
        from utils.reconciliation_specialized import (
            NostroVostroAccount, CorrespondentAccountType)
        n = NostroVostroAccount(
            account_id="N1",
            account_type=CorrespondentAccountType.NOSTRO,
            correspondent_bank="JPM_NY", currency="USD",
            our_book_balance_kes_equiv=Decimal("129000000"),
            correspondent_book_balance_kes_equiv=Decimal("128900000"),
            fx_rate_used=Decimal("129.00"))
        self.assertEqual(n.variance_kes(), Decimal("100000"))

    def test_fx_revaluation_kes_per_fcy(self):
        """1M USD reval at +1 KES/USD = +1M KES."""
        from utils.reconciliation_specialized import compute_fx_reval
        r = compute_fx_reval(
            account_id="N1",
            fcy_balance=Decimal("1000000"),
            rate_at_book=Decimal("128.00"),
            rate_at_recon=Decimal("129.00"))
        self.assertEqual(r.reval_amount_kes, Decimal("1000000"))

    def test_stale_item_91_plus_is_breach(self):
        from utils.reconciliation_specialized import (
            StaleItem, StaleAgeBucket)
        item = StaleItem(
            item_id="S1", account_id="N1",
            booking_date="2026-01-01",
            amount_fcy=Decimal("1000"),
            amount_kes_equiv=Decimal("129000"),
            currency="USD")
        # 4+ months later
        self.assertEqual(
            item.aging(as_of=date(2026, 5, 1)),
            StaleAgeBucket.BREACH_91_PLUS)


class TestV1020IntercompanySuspense(unittest.TestCase):
    """ENH-187 — Intercompany + suspense."""

    def test_ic_in_balance_within_tolerance(self):
        from utils.reconciliation_specialized import (
            IntercompanyCounterparty, IntercompanyEntityType)
        c = IntercompanyCounterparty(
            counterparty_id="UG", counterparty_name="Ecobank Uganda",
            entity_type=IntercompanyEntityType.SUBSIDIARY,
            our_balance_kes_equiv=Decimal("100000"),
            their_balance_kes_equiv=Decimal("100000.30"))
        # 30 cent diff < 50 cent default tolerance
        self.assertTrue(c.is_in_balance())

    def test_ic_out_of_balance(self):
        from utils.reconciliation_specialized import (
            IntercompanyCounterparty, IntercompanyEntityType)
        c = IntercompanyCounterparty(
            counterparty_id="TZ", counterparty_name="Ecobank Tanzania",
            entity_type=IntercompanyEntityType.SUBSIDIARY,
            our_balance_kes_equiv=Decimal("200000"),
            their_balance_kes_equiv=Decimal("199000"))
        self.assertFalse(c.is_in_balance())
        self.assertEqual(c.variance_kes(), Decimal("1000"))

    def test_suspense_per_category_aging(self):
        """Different categories have different max ages."""
        from utils.reconciliation_specialized import (
            SuspenseCategory, SuspenseItem)
        cheque = SuspenseItem(
            item_id="C1",
            suspense_category=SuspenseCategory.CHEQUES_IN_CLEARING,
            booking_date="2026-04-01",
            amount_kes=Decimal("10000"))
        dispute = SuspenseItem(
            item_id="D1",
            suspense_category=SuspenseCategory.DEBIT_CARD_DISPUTES,
            booking_date="2026-04-01",
            amount_kes=Decimal("50000"))
        # Both 7 days old: cheque (max 5) overdue, dispute (max 30) fresh
        self.assertTrue(cheque.is_overdue(as_of=date(2026, 4, 8)))
        self.assertFalse(dispute.is_overdue(as_of=date(2026, 4, 8)))


class TestV1020RealTimeKEPSSPesaLink(unittest.TestCase):
    """ENH-RMS-R6 — Real-time KEPSS/PesaLink reconciliation."""

    def _payment(self, payment_id="P1", init="2026-04-23T10:00:00Z",
                    settled=None, amount="1000000"):
        from utils.reconciliation_specialized import (
            RealTimePaymentObservation, RealTimePaymentSystem)
        return RealTimePaymentObservation(
            payment_id=payment_id,
            payment_system=RealTimePaymentSystem.KEPSS,
            initiated_at_utc=init,
            settled_at_utc=settled,
            amount_kes=Decimal(amount))

    def test_sub_30s_is_auto_match(self):
        from utils.reconciliation_specialized import (
            assess_real_time_match, RealTimeMatchVerdict)
        init = self._payment(settled="2026-04-23T10:00:15Z")  # 15s
        r = assess_real_time_match(initiated=init, settled=init)
        self.assertEqual(r.verdict, RealTimeMatchVerdict.MATCHED_AUTO)

    def test_30_to_300s_is_delayed(self):
        from utils.reconciliation_specialized import (
            assess_real_time_match, RealTimeMatchVerdict)
        init = self._payment(init="2026-04-23T10:00:00Z")
        settled = self._payment(settled="2026-04-23T10:01:30Z")  # 90s
        r = assess_real_time_match(initiated=init, settled=settled)
        self.assertEqual(r.verdict, RealTimeMatchVerdict.MATCHED_DELAYED)

    def test_over_300s_is_latency_breach(self):
        from utils.reconciliation_specialized import (
            assess_real_time_match, RealTimeMatchVerdict)
        init = self._payment(init="2026-04-23T10:00:00Z")
        settled = self._payment(settled="2026-04-23T10:10:00Z")  # 600s
        r = assess_real_time_match(initiated=init, settled=settled)
        self.assertEqual(r.verdict, RealTimeMatchVerdict.LATENCY_BREACH)

    def test_amount_mismatch_detected(self):
        from utils.reconciliation_specialized import (
            assess_real_time_match, RealTimeMatchVerdict)
        init = self._payment(amount="1000000")
        settled = self._payment(
            settled="2026-04-23T10:00:10Z", amount="999900")
        r = assess_real_time_match(initiated=init, settled=settled)
        self.assertEqual(r.verdict, RealTimeMatchVerdict.AMOUNT_MISMATCH)

    def test_pending_settlement(self):
        from utils.reconciliation_specialized import (
            assess_real_time_match, RealTimeMatchVerdict)
        init = self._payment()
        r = assess_real_time_match(initiated=init, settled=None)
        self.assertEqual(r.verdict, RealTimeMatchVerdict.SETTLEMENT_PENDING)


class TestV1020EngineEndToEnd(unittest.TestCase):
    """Aggregator works across all 4 specialized surfaces."""

    def test_engine_aggregates_all_surfaces(self):
        from utils.reconciliation_specialized import (
            SpecializedReconciliationEngine,
            CBKReturnType, CBKReturnRecord, ReturnStatus,
            StaleItem,
            IntercompanyCounterparty, IntercompanyEntityType,
            SuspenseItem, SuspenseCategory)
        eng = SpecializedReconciliationEngine()
        eng.add_cbk_return(CBKReturnRecord(
            return_id="R1", return_type=CBKReturnType.MONTHLY_RETURN,
            period_end="2026-04-30", deadline="2026-05-15",
            status=ReturnStatus.PENDING))
        eng.add_stale_item(StaleItem(
            item_id="S1", account_id="N1",
            booking_date="2026-01-01",
            amount_fcy=Decimal("1000"),
            amount_kes_equiv=Decimal("129000"),
            currency="USD"))
        eng.add_ic_counterparty(IntercompanyCounterparty(
            counterparty_id="UG", counterparty_name="Ecobank Uganda",
            entity_type=IntercompanyEntityType.SUBSIDIARY,
            our_balance_kes_equiv=Decimal("100"),
            their_balance_kes_equiv=Decimal("99")))
        eng.add_suspense_item(SuspenseItem(
            item_id="SUS1",
            suspense_category=SuspenseCategory.CHEQUES_IN_CLEARING,
            booking_date="2026-04-01",
            amount_kes=Decimal("10000")))
        s = eng.board_summary(as_of=date(2026, 5, 1))
        self.assertEqual(s["n_cbk_returns"], 1)
        self.assertEqual(s["n_stale_items"], 1)
        self.assertEqual(s["n_critical_stale"], 1)
        self.assertEqual(s["n_ic_counterparties"], 1)
        self.assertEqual(s["n_ic_out_of_balance"], 1)
        self.assertEqual(s["n_suspense_items"], 1)


class TestV1020Coexistence(unittest.TestCase):
    """v10.20 coexists with v10.18 + v10.19."""

    def test_three_rms_engines_coexist(self):
        from utils.reconciliation_matching import (
            ReconciliationMatchingEngine)
        from utils.reconciliation_workflow import (
            ReconciliationWorkflowEngine)
        from utils.reconciliation_specialized import (
            SpecializedReconciliationEngine)
        m = ReconciliationMatchingEngine(entity_name="X")
        w = ReconciliationWorkflowEngine(entity_name="X")
        s = SpecializedReconciliationEngine(entity_name="X")
        for e in (m, w, s):
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

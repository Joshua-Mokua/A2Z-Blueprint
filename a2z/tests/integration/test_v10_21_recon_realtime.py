"""tests/integration/test_v10_21_recon_realtime.py — v10.21.

Phase 2 batch 3 (RMS arc batch 4 — final standards batch before closure).
Standards: ENH-184, ENH-188, ENH-189, ENH-190, ENH-RMS-R7.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1021Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import reconciliation_realtime  # noqa

    def test_public_symbols(self):
        from utils import reconciliation_realtime as m
        for sym in (
            # Cadence
            "ReconCadence", "CADENCE_POLICY", "is_cadence_compliant",
            # Continuous / streaming
            "StreamingWatermark", "LateArrivalRecord",
            "detect_late_arrival",
            # Learning
            "FeedbackOutcome", "LearningFeedback",
            "LearningStats", "LearningStore",
            # Certification
            "CertifierRole", "CertificationStatus",
            "ALLOWED_CERT_TRANSITIONS", "is_valid_cert_transition",
            "CertificationSignoff", "AuditTrailEntry",
            "CertificationRecord",
            # Dashboard
            "DashboardKPI", "DashboardSnapshot",
            "build_dashboard_snapshot",
            # Engine
            "ReconciliationRealtimeEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1021SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import reconciliation_realtime
        reconciliation_realtime.self_test()


class TestV1021RegistryAlignment(unittest.TestCase):
    def test_all_17_rms_active(self):
        """All 17 RMS standards are now active after v10.21."""
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "rms" and s.status == "active"]
        self.assertEqual(len(active), 17)

    def test_no_rms_planned(self):
        """No RMS standards remain in planned status."""
        from utils.standards_registry import STANDARDS_REGISTRY
        planned = [s for s in STANDARDS_REGISTRY
                     if s.subcategory == "rms" and s.status == "planned"]
        self.assertEqual(len(planned), 0)

    def test_v10_21_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "rms" and s.status == "active"}
        for sid in ("ENH-184", "ENH-188", "ENH-189", "ENH-190",
                      "ENH-RMS-R7"):
            self.assertIn(sid, active_ids)


class TestV1021SubMonthlyCadence(unittest.TestCase):
    """ENH-RMS-R7 — Sub-monthly daily reconciliation support."""

    def test_nostro_must_be_at_least_daily(self):
        """CBK CRMF requires daily Nostro recon."""
        from utils.reconciliation_realtime import (
            ReconCadence, is_cadence_compliant)
        self.assertTrue(is_cadence_compliant(
            account_type="NOSTRO", actual_cadence=ReconCadence.DAILY))
        self.assertFalse(is_cadence_compliant(
            account_type="NOSTRO", actual_cadence=ReconCadence.MONTHLY))

    def test_kepss_must_be_real_time(self):
        from utils.reconciliation_realtime import (
            ReconCadence, is_cadence_compliant)
        self.assertTrue(is_cadence_compliant(
            account_type="INTERBANK_KEPSS",
            actual_cadence=ReconCadence.REAL_TIME))
        self.assertFalse(is_cadence_compliant(
            account_type="INTERBANK_KEPSS",
            actual_cadence=ReconCadence.HOURLY))

    def test_real_time_meets_any_policy(self):
        from utils.reconciliation_realtime import (
            ReconCadence, is_cadence_compliant)
        for acc in ("NOSTRO", "GL_TO_CBS", "INTERCOMPANY"):
            self.assertTrue(is_cadence_compliant(
                account_type=acc,
                actual_cadence=ReconCadence.REAL_TIME))


class TestV1021ContinuousReconciliation(unittest.TestCase):
    """ENH-189 — Continuous/Real-time reconciliation."""

    def test_late_arrival_detected(self):
        from utils.reconciliation_realtime import (
            StreamingWatermark, detect_late_arrival)
        wm = StreamingWatermark(
            source_id="GL", watermark_utc="2026-04-23T10:00:00Z")
        late = detect_late_arrival(
            record_id="R1", source_id="GL",
            record_timestamp_utc="2026-04-23T09:50:00Z",   # 10min before wm
            received_at_utc="2026-04-23T10:01:00Z",
            watermark=wm)
        self.assertIsNotNone(late)
        self.assertEqual(late.lateness_seconds, 11 * 60)   # 11min

    def test_in_order_record_not_flagged(self):
        from utils.reconciliation_realtime import (
            StreamingWatermark, detect_late_arrival)
        wm = StreamingWatermark(
            source_id="GL", watermark_utc="2026-04-23T10:00:00Z")
        result = detect_late_arrival(
            record_id="R1", source_id="GL",
            record_timestamp_utc="2026-04-23T10:01:00Z",
            received_at_utc="2026-04-23T10:01:05Z", watermark=wm)
        self.assertIsNone(result)


class TestV1021Learning(unittest.TestCase):
    """ENH-188 — AI-powered reconciliation learning."""

    def test_feedback_recorded(self):
        from utils.reconciliation_realtime import (
            LearningStore, LearningFeedback, FeedbackOutcome)
        ls = LearningStore()
        ls.record_feedback(LearningFeedback(
            feedback_id="F1", proposed_pair_id="P1",
            source_transaction_id="S1", target_transaction_id="T1",
            proposed_match_score=Decimal("0.85"),
            proposed_algorithm="X",
            actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
            reviewer_id="u", timestamp="t"))
        self.assertEqual(ls.feedback_count(), 1)

    def test_no_train_callable_honest_about_no_training(self):
        """Rule 7: explicit no-fab signal when no model wired."""
        from utils.reconciliation_realtime import LearningStore
        ls = LearningStore()
        fired, msg = ls.trigger_training()
        self.assertFalse(fired)
        self.assertIn("no train_callable", msg.lower())

    def test_train_callable_invoked_when_present(self):
        from utils.reconciliation_realtime import (
            LearningStore, LearningFeedback, FeedbackOutcome)
        invocations = []
        def trainer(feedbacks):
            invocations.append(len(feedbacks))
        ls = LearningStore(train_callable=trainer)
        ls.record_feedback(LearningFeedback(
            feedback_id="F1", proposed_pair_id="P1",
            source_transaction_id="S", target_transaction_id="T",
            proposed_match_score=Decimal("0.9"),
            proposed_algorithm="X",
            actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
            reviewer_id="u", timestamp="t"))
        fired, msg = ls.trigger_training()
        self.assertTrue(fired)
        self.assertEqual(invocations, [1])

    def test_stats_aggregation(self):
        from utils.reconciliation_realtime import (
            LearningStore, LearningFeedback, FeedbackOutcome)
        ls = LearningStore()
        for _ in range(8):
            ls.record_feedback(LearningFeedback(
                feedback_id="C", proposed_pair_id="P",
                source_transaction_id="S", target_transaction_id="T",
                proposed_match_score=Decimal("0.9"),
                proposed_algorithm="X",
                actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
                reviewer_id="u", timestamp="t"))
        stats = ls.stats()
        self.assertEqual(stats.confirmation_rate_pct, Decimal("100"))


class TestV1021Certification(unittest.TestCase):
    """ENH-190 — Reconciliation audit & certification."""

    def test_dual_approval_required(self):
        from utils.reconciliation_realtime import (
            CertificationRecord, CertificationStatus, ReconCadence,
            ReconciliationRealtimeEngine, CertifierRole)
        eng = ReconciliationRealtimeEngine()
        eng.register_certification(CertificationRecord(
            cert_id="C1", period_label="2026-04",
            cadence=ReconCadence.MONTHLY, account_type="GL_TO_CBS",
            status=CertificationStatus.DRAFT))
        # Preparer signs off
        eng.transition_certification(
            cert_id="C1", to_status=CertificationStatus.PREPARED,
            actor_user_id="alice", actor_role=CertifierRole.PREPARER,
            timestamp="t1")
        cert = eng.get_certification("C1")
        # Only 1 sign-off so far → not dual-approved
        self.assertFalse(cert.is_dual_approved())
        # Reviewer signs off
        eng.transition_certification(
            cert_id="C1", to_status=CertificationStatus.REVIEWED,
            actor_user_id="bob", actor_role=CertifierRole.REVIEWER,
            timestamp="t2")
        cert = eng.get_certification("C1")
        self.assertTrue(cert.is_dual_approved())

    def test_invalid_skip_raises(self):
        from utils.reconciliation_realtime import (
            CertificationRecord, CertificationStatus, ReconCadence,
            ReconciliationRealtimeEngine, CertifierRole)
        eng = ReconciliationRealtimeEngine()
        eng.register_certification(CertificationRecord(
            cert_id="C1", period_label="2026-04",
            cadence=ReconCadence.MONTHLY, account_type="GL",
            status=CertificationStatus.DRAFT))
        with self.assertRaises(ValueError):
            # Cannot skip from DRAFT directly to SIGNED_OFF
            eng.transition_certification(
                cert_id="C1", to_status=CertificationStatus.SIGNED_OFF,
                actor_user_id="x", actor_role=CertifierRole.CFO,
                timestamp="t")

    def test_audit_trail_immutable(self):
        """Each transition adds an immutable AuditTrailEntry."""
        from utils.reconciliation_realtime import (
            CertificationRecord, CertificationStatus, ReconCadence,
            ReconciliationRealtimeEngine, CertifierRole)
        eng = ReconciliationRealtimeEngine()
        eng.register_certification(CertificationRecord(
            cert_id="C1", period_label="p", cadence=ReconCadence.DAILY,
            account_type="X", status=CertificationStatus.DRAFT))
        eng.transition_certification(
            cert_id="C1", to_status=CertificationStatus.PREPARED,
            actor_user_id="alice", actor_role=CertifierRole.PREPARER,
            timestamp="t1")
        cert = eng.get_certification("C1")
        self.assertEqual(len(cert.audit_entries), 1)
        entry = cert.audit_entries[0]
        self.assertEqual(entry.before_state, "DRAFT")
        self.assertEqual(entry.after_state, "PREPARED")


class TestV1021Dashboard(unittest.TestCase):
    """ENH-184 — Real-time reconciliation dashboard."""

    def test_kpi_status_color_higher_better(self):
        from utils.reconciliation_realtime import DashboardKPI
        # Auto-match 75% with amber=80 → AMBER (below amber threshold)
        k = DashboardKPI(
            kpi_name="Auto-Match", current_value=Decimal("75"),
            threshold_amber=Decimal("80"), threshold_red=Decimal("70"),
            higher_is_better=True, unit="%")
        self.assertEqual(k.status_color(), "AMBER")

    def test_kpi_status_color_lower_better(self):
        from utils.reconciliation_realtime import DashboardKPI
        k = DashboardKPI(
            kpi_name="SLA Breaches", current_value=Decimal("8"),
            threshold_amber=Decimal("5"), threshold_red=Decimal("20"),
            higher_is_better=False, unit="count")
        self.assertEqual(k.status_color(), "AMBER")

    def test_dashboard_snapshot_has_4_kpis(self):
        from utils.reconciliation_realtime import build_dashboard_snapshot
        snap = build_dashboard_snapshot(
            snapshot_at_utc="2026-04-23T10:00:00Z",
            auto_match_rate_pct=Decimal("92"),
            n_open_exceptions=50, n_sla_breaches=2, n_critical_alerts=0)
        self.assertEqual(len(snap.kpis), 4)


class TestV1021EngineEndToEnd(unittest.TestCase):
    def test_engine_aggregates_all_surfaces(self):
        from utils.reconciliation_realtime import (
            ReconciliationRealtimeEngine, ReconCadence,
            CertificationRecord, CertificationStatus, CertifierRole,
            LearningFeedback, FeedbackOutcome,
            build_dashboard_snapshot)
        eng = ReconciliationRealtimeEngine()
        eng.add_snapshot(build_dashboard_snapshot(
            snapshot_at_utc="2026-04-23T10:00:00Z",
            auto_match_rate_pct=Decimal("92"),
            n_open_exceptions=50, n_sla_breaches=2, n_critical_alerts=0))
        eng.register_certification(CertificationRecord(
            cert_id="C1", period_label="p", cadence=ReconCadence.DAILY,
            account_type="GL", status=CertificationStatus.DRAFT))
        eng.record_learning_feedback(LearningFeedback(
            feedback_id="F1", proposed_pair_id="P1",
            source_transaction_id="S", target_transaction_id="T",
            proposed_match_score=Decimal("0.9"),
            proposed_algorithm="X",
            actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
            reviewer_id="u", timestamp="t"))
        s = eng.board_summary()
        self.assertEqual(s["n_snapshots"], 1)
        self.assertEqual(s["n_certifications"], 1)
        self.assertEqual(s["n_learning_feedback"], 1)


class TestV1021Coexistence(unittest.TestCase):
    """All 4 RMS modules coexist (v10.18, v10.19, v10.20, v10.21)."""

    def test_four_rms_modules(self):
        from utils.reconciliation_matching import (
            ReconciliationMatchingEngine)
        from utils.reconciliation_workflow import (
            ReconciliationWorkflowEngine)
        from utils.reconciliation_specialized import (
            SpecializedReconciliationEngine)
        from utils.reconciliation_realtime import (
            ReconciliationRealtimeEngine)
        engines = [
            ReconciliationMatchingEngine(entity_name="X"),
            ReconciliationWorkflowEngine(entity_name="X"),
            SpecializedReconciliationEngine(entity_name="X"),
            ReconciliationRealtimeEngine(entity_name="X"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

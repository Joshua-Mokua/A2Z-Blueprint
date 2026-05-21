"""tests/integration/test_v10_19_reconciliation_workflow.py — v10.19.

Phase 2 batch 3 (RMS deep-impl arc batch 2): exception workflow + memory
+ timing + governed execution.

Standards: ENH-183, ENH-RMS-R2, ENH-RMS-R4, ENH-RMS-R5.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1019Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import reconciliation_workflow  # noqa

    def test_public_symbols(self):
        from utils import reconciliation_workflow as m
        for sym in (
            # Exception types + lifecycle
            "ExceptionType", "ExceptionState",
            "ALLOWED_EXC_TRANSITIONS",
            "is_terminal_exception_state",
            "is_valid_exception_transition",
            "AgingBucket", "compute_aging_bucket",
            "DEFAULT_SLA_DAYS",
            # Assignment
            "AssignmentQueue", "assign_queue",
            "ASSIGNMENT_AMOUNT_TIER_LOW_KES",
            "ASSIGNMENT_AMOUNT_TIER_HIGH_KES",
            # Records
            "ExceptionRecord",
            # Memory layer
            "ResolutionPattern",
            "compute_signature",
            "MEMORY_CONFIDENCE_LOW",
            "MEMORY_CONFIDENCE_MEDIUM",
            "MEMORY_CONFIDENCE_HIGH",
            "confidence_from_occurrences",
            "MemoryLayer",
            # Timing diff
            "TimingDifferenceConfig",
            "TimingDifferenceCandidate",
            "detect_timing_difference",
            # Guards
            "GuardRailType", "GuardRail",
            "GuardCheckResult", "GovernedExecutionDecision",
            "evaluate_guards",
            "DEFAULT_AUTO_RESOLUTION_AMOUNT_LIMIT_KES",
            "DEFAULT_PATTERN_CONFIDENCE_FLOOR",
            # Engine
            "ReconciliationWorkflowEngine",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1019SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import reconciliation_workflow
        reconciliation_workflow.self_test()


class TestV1019RegistryAlignment(unittest.TestCase):
    def test_8_rms_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "rms" and s.status == "active"]
        self.assertGreaterEqual(len(active), 8)

    def test_v10_19_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "rms" and s.status == "active"}
        for sid in ("ENH-183", "ENH-RMS-R2", "ENH-RMS-R4", "ENH-RMS-R5"):
            self.assertIn(sid, active_ids)


class TestV1019ExceptionLifecycle(unittest.TestCase):
    """ENH-183 — Exception Management & Workflow."""

    def test_terminal_states_complete(self):
        from utils.reconciliation_workflow import (
            ExceptionState, is_terminal_exception_state)
        terminals = {
            s for s in ExceptionState if is_terminal_exception_state(s)}
        expected = {
            ExceptionState.AUTO_RESOLVED,
            ExceptionState.MANUALLY_RESOLVED,
            ExceptionState.WRITTEN_OFF,
            ExceptionState.REJECTED_NEEDS_REVERSAL,
        }
        self.assertEqual(terminals, expected)

    def test_invalid_transition_raises(self):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord,
            ReconciliationWorkflowEngine)
        eng = ReconciliationWorkflowEngine()
        eng.register_exception(ExceptionRecord(
            exception_id="E1",
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            state=ExceptionState.NEW,
            created_at="2026-01-01T10:00:00Z",
            amount_kes=Decimal("50000"),
            counterparty_name="ACME"))
        with self.assertRaises(ValueError):
            # NEW → MANUALLY_RESOLVED is invalid (must go via INVESTIGATING)
            eng.transition(
                exception_id="E1",
                to_state=ExceptionState.MANUALLY_RESOLVED,
                actor="x", timestamp="t")

    def test_aging_breach_threshold(self):
        from utils.reconciliation_workflow import (
            AgingBucket, compute_aging_bucket)
        self.assertEqual(compute_aging_bucket(0), AgingBucket.FRESH_0_3)
        self.assertEqual(compute_aging_bucket(31), AgingBucket.BREACH_30_PLUS)

    def test_sla_breach_detected(self):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord)
        exc = ExceptionRecord(
            exception_id="E1",
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            state=ExceptionState.NEW,
            created_at="2026-01-01T10:00:00Z",
            amount_kes=Decimal("50000"),
            counterparty_name="ACME",
            sla_days=5)
        self.assertTrue(exc.is_sla_breached(as_of=date(2026, 1, 10)))
        self.assertFalse(exc.is_sla_breached(as_of=date(2026, 1, 5)))


class TestV1019AssignmentRouting(unittest.TestCase):
    """ENH-183 — Queue routing rules."""

    def test_high_amount_to_mgmt_review(self):
        from utils.reconciliation_workflow import (
            ExceptionType, AssignmentQueue, assign_queue)
        q = assign_queue(
            exception_type=ExceptionType.AMOUNT_MISMATCH,
            amount_kes=Decimal("50000000"))
        self.assertEqual(q, AssignmentQueue.MGMT_REVIEW)

    def test_nostro_hint_routes_to_nostro_desk(self):
        from utils.reconciliation_workflow import (
            ExceptionType, AssignmentQueue, assign_queue)
        q = assign_queue(
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            amount_kes=Decimal("100000"),
            source_hint="NOSTRO_USD")
        self.assertEqual(q, AssignmentQueue.NOSTRO_DESK)


class TestV1019MemoryLayer(unittest.TestCase):
    """ENH-RMS-R2 — Memory-layer architecture."""

    def test_pattern_recorded_and_recalled(self):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord,
            MemoryLayer, MEMORY_CONFIDENCE_LOW)
        mem = MemoryLayer()
        exc = ExceptionRecord(
            exception_id="E1",
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            state=ExceptionState.NEW,
            created_at="2026-01-01T10:00:00Z",
            amount_kes=Decimal("50000"),
            counterparty_name="ACME LTD")
        mem.record_resolution(
            exception_record=exc,
            resolution_action="WRITE_OFF_TO_FX_REVAL",
            gl_account="9991")
        recalled = mem.recall(
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            amount_kes=Decimal("50000"),
            counterparty_name="ACME LTD")
        self.assertIsNotNone(recalled)
        self.assertEqual(recalled.typical_resolution,
                          "WRITE_OFF_TO_FX_REVAL")
        self.assertEqual(recalled.confidence, MEMORY_CONFIDENCE_LOW)

    def test_confidence_grows_with_repeats(self):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord,
            MemoryLayer, MEMORY_CONFIDENCE_MEDIUM, MEMORY_CONFIDENCE_HIGH)
        mem = MemoryLayer()
        for _ in range(15):
            exc = ExceptionRecord(
                exception_id="E", exception_type=ExceptionType.UNMATCHED_SOURCE,
                state=ExceptionState.NEW, created_at="2026-01-01T10:00:00Z",
                amount_kes=Decimal("50000"), counterparty_name="ACME LTD")
            mem.record_resolution(
                exception_record=exc,
                resolution_action="X")
        p = mem.recall(
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            amount_kes=Decimal("50000"),
            counterparty_name="ACME LTD")
        self.assertEqual(p.confidence, MEMORY_CONFIDENCE_HIGH)
        self.assertEqual(p.occurrence_count, 15)


class TestV1019TimingDifference(unittest.TestCase):
    """ENH-RMS-R4 — Timing-difference auto-handling."""

    def _exc(self, created="2026-01-15T00:00:00Z", amount="1000",
              cp="ACME LTD"):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord)
        return ExceptionRecord(
            exception_id="E1",
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            state=ExceptionState.NEW,
            created_at=created,
            amount_kes=Decimal(amount),
            counterparty_name=cp)

    def test_t_plus_1_auto_resolvable(self):
        from utils.reconciliation_workflow import detect_timing_difference
        cand = detect_timing_difference(
            exception=self._exc(),
            candidate_target_value_date="2026-01-16",
            candidate_target_amount_kes=Decimal("1000"),
            candidate_target_counterparty="ACME LTD",
            candidate_target_id="T1")
        self.assertIsNotNone(cand)
        self.assertTrue(cand.can_auto_resolve)

    def test_t_plus_2_review_required(self):
        from utils.reconciliation_workflow import detect_timing_difference
        cand = detect_timing_difference(
            exception=self._exc(),
            candidate_target_value_date="2026-01-17",
            candidate_target_amount_kes=Decimal("1000"),
            candidate_target_counterparty="ACME LTD",
            candidate_target_id="T1")
        self.assertIsNotNone(cand)
        self.assertFalse(cand.can_auto_resolve)

    def test_amount_mismatch_returns_none(self):
        from utils.reconciliation_workflow import detect_timing_difference
        cand = detect_timing_difference(
            exception=self._exc(amount="1000"),
            candidate_target_value_date="2026-01-15",
            candidate_target_amount_kes=Decimal("999"),
            candidate_target_counterparty="ACME LTD",
            candidate_target_id="T1")
        self.assertIsNone(cand)

    def test_beyond_max_lag_returns_none(self):
        from utils.reconciliation_workflow import detect_timing_difference
        cand = detect_timing_difference(
            exception=self._exc(),
            candidate_target_value_date="2026-02-15",   # > 30 days
            candidate_target_amount_kes=Decimal("1000"),
            candidate_target_counterparty="ACME LTD",
            candidate_target_id="T1")
        self.assertIsNone(cand)


class TestV1019GovernedExecution(unittest.TestCase):
    """ENH-RMS-R5 — Governed execution layer (TruePath-style)."""

    def test_amount_limit_blocks_above_threshold(self):
        from utils.reconciliation_workflow import (
            GuardRail, GuardRailType, evaluate_guards)
        guard = GuardRail(
            guard_id="G1", guard_type=GuardRailType.AMOUNT_LIMIT,
            config={"max_amount_kes": Decimal("50000")})
        decision = evaluate_guards(
            action="AUTO_RESOLVE",
            proposed_amount_kes=Decimal("100000"),
            guards=[guard])
        self.assertFalse(decision.is_permitted)

    def test_pattern_confidence_floor_blocks_low(self):
        from utils.reconciliation_workflow import (
            GuardRail, GuardRailType, evaluate_guards)
        guard = GuardRail(
            guard_id="G1",
            guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
            config={"min_confidence": Decimal("0.75")})
        decision = evaluate_guards(
            action="X",
            proposed_amount_kes=Decimal("100"),
            pattern_confidence=Decimal("0.5"),
            guards=[guard])
        self.assertFalse(decision.is_permitted)

    def test_pattern_confidence_floor_allows_high(self):
        from utils.reconciliation_workflow import (
            GuardRail, GuardRailType, evaluate_guards)
        guard = GuardRail(
            guard_id="G1",
            guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
            config={"min_confidence": Decimal("0.75")})
        decision = evaluate_guards(
            action="X",
            proposed_amount_kes=Decimal("100"),
            pattern_confidence=Decimal("0.90"),
            guards=[guard])
        self.assertTrue(decision.is_permitted)

    def test_blocked_counterparty(self):
        from utils.reconciliation_workflow import (
            GuardRail, GuardRailType, evaluate_guards)
        guard = GuardRail(
            guard_id="G1",
            guard_type=GuardRailType.BLOCKED_COUNTERPARTIES,
            config={"blocked": ("OFAC_SANCTIONED",)})
        decision = evaluate_guards(
            action="X",
            proposed_amount_kes=Decimal("100"),
            counterparty="OFAC_SANCTIONED ENTITY",
            guards=[guard])
        self.assertFalse(decision.is_permitted)

    def test_dual_approval_flag(self):
        from utils.reconciliation_workflow import (
            GuardRail, GuardRailType, evaluate_guards)
        guard = GuardRail(
            guard_id="G1",
            guard_type=GuardRailType.REQUIRES_DUAL_APPROVAL,
            config={"amount_threshold_kes": Decimal("100000")})
        decision = evaluate_guards(
            action="X", proposed_amount_kes=Decimal("500000"),
            guards=[guard])
        self.assertTrue(decision.requires_dual_approval)

    def test_per_guard_outcomes_visible(self):
        """Caller sees per-guard pass/fail, not just final permitted flag."""
        from utils.reconciliation_workflow import (
            GuardRail, GuardRailType, evaluate_guards)
        guards = [
            GuardRail(
                guard_id="G1", guard_type=GuardRailType.AMOUNT_LIMIT,
                config={"max_amount_kes": Decimal("50000")}),
            GuardRail(
                guard_id="G2",
                guard_type=GuardRailType.BUSINESS_HOURS_ONLY,
                config={}),
        ]
        decision = evaluate_guards(
            action="X",
            proposed_amount_kes=Decimal("100000"),    # blocks G1
            is_business_hours=False,                   # blocks G2
            guards=guards)
        self.assertFalse(decision.is_permitted)
        self.assertEqual(len(decision.guards_evaluated), 2)
        # Both blocked
        passed = [r.passed for r in decision.guards_evaluated]
        self.assertEqual(passed, [False, False])


class TestV1019EngineEndToEnd(unittest.TestCase):
    """Engine orchestrates lifecycle + memory + guards."""

    def test_known_pattern_with_guards_permits_action(self):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord,
            ReconciliationWorkflowEngine,
            GuardRail, GuardRailType)
        guards = [
            GuardRail(
                guard_id="G1",
                guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
                config={"min_confidence": Decimal("0.75")}),
            GuardRail(
                guard_id="G2",
                guard_type=GuardRailType.AMOUNT_LIMIT,
                config={"max_amount_kes": Decimal("100000")}),
        ]
        eng = ReconciliationWorkflowEngine(guards=guards)
        # Train pattern with 5 occurrences
        for i in range(5):
            exc = ExceptionRecord(
                exception_id=f"E{i}",
                exception_type=ExceptionType.UNMATCHED_SOURCE,
                state=ExceptionState.NEW,
                created_at="2026-01-01T10:00:00Z",
                amount_kes=Decimal("50000"),
                counterparty_name="ACME LTD")
            eng.register_exception(exc)
            eng.record_resolution(
                exception_id=f"E{i}",
                resolution_action="WRITE_OFF",
                gl_account="9991")
        # New exception with same signature
        eng.register_exception(ExceptionRecord(
            exception_id="NEW",
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            state=ExceptionState.NEW,
            created_at="2026-01-10T10:00:00Z",
            amount_kes=Decimal("50000"),
            counterparty_name="ACME LTD"))
        decision = eng.attempt_auto_resolve(
            exception_id="NEW",
            proposed_action="WRITE_OFF")
        self.assertTrue(decision.is_permitted)

    def test_unknown_pattern_with_confidence_guard_blocked(self):
        from utils.reconciliation_workflow import (
            ExceptionType, ExceptionState, ExceptionRecord,
            ReconciliationWorkflowEngine,
            GuardRail, GuardRailType)
        guards = [
            GuardRail(
                guard_id="G1",
                guard_type=GuardRailType.PATTERN_CONFIDENCE_FLOOR,
                config={"min_confidence": Decimal("0.75")}),
        ]
        eng = ReconciliationWorkflowEngine(guards=guards)
        eng.register_exception(ExceptionRecord(
            exception_id="E1",
            exception_type=ExceptionType.UNMATCHED_SOURCE,
            state=ExceptionState.NEW,
            created_at="2026-01-01T10:00:00Z",
            amount_kes=Decimal("50000"),
            counterparty_name="UNFAMILIAR ENTITY"))
        decision = eng.attempt_auto_resolve(
            exception_id="E1",
            proposed_action="WRITE_OFF")
        self.assertFalse(decision.is_permitted)
        self.assertIn("G1", decision.blocked_by_guard_ids)


class TestV1019Coexistence(unittest.TestCase):
    def test_v10_18_v10_19_coexist(self):
        from utils.reconciliation_matching import (
            ReconciliationMatchingEngine)
        from utils.reconciliation_workflow import (
            ReconciliationWorkflowEngine)
        m = ReconciliationMatchingEngine(entity_name="X")
        w = ReconciliationWorkflowEngine(entity_name="X")
        self.assertEqual(m.entity_name, w.entity_name)


if __name__ == "__main__":
    unittest.main()

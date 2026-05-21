"""tests/integration/test_v10_24_audit_controls_issues.py — v10.24.

Phase 2 batch 4 (Audit/GRC arc batch 2): control testing library + issue
tracking + cross-framework mapping + ticketing integration.
ENH-204 + ENH-206 + ENH-AUD-R1 + ENH-AUD-R4.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1024Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import audit_controls_issues  # noqa

    def test_public_symbols(self):
        from utils import audit_controls_issues as m
        for sym in (
            # Issues
            "IssueSource", "IssueStatus", "IssueSeverity",
            "ALLOWED_ISSUE_TRANSITIONS",
            "is_valid_issue_transition", "is_terminal_issue_status",
            "DEFAULT_ISSUE_REMEDIATION_DAYS",
            "IssueAgingBucket", "compute_issue_aging",
            "Issue", "compute_issue_deadline",
            # Test scripts
            "TestScriptLanguage", "TestScheduleStatus",
            "TestScript", "TestSchedule", "TestCoverageReport",
            # Framework
            "ControlFramework",
            "DEFAULT_CROSS_FRAMEWORK_MAPPINGS",
            "FrameworkMapping",
            "get_canonical_concepts",
            "get_frameworks_covered_by_concept",
            "coverage_by_framework",
            # Ticketing
            "TicketingSystem", "TicketStatus",
            "TicketStub", "create_ticket_stub", "sync_ticket_status",
            # Engine
            "AuditControlsIssuesEngine",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1024SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import audit_controls_issues
        audit_controls_issues.self_test()


class TestV1024RegistryAlignment(unittest.TestCase):
    def test_8_audit_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "audit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 8)

    def test_v10_24_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "audit" and s.status == "active"}
        for sid in ("ENH-204", "ENH-206", "ENH-AUD-R1", "ENH-AUD-R4"):
            self.assertIn(sid, active_ids)


class TestV1024IssueTracking(unittest.TestCase):
    """ENH-204 — Issue tracking & remediation."""

    def test_critical_seven_day_deadline(self):
        from utils.audit_controls_issues import (
            IssueSeverity, compute_issue_deadline)
        dl = compute_issue_deadline(
            raised_date=date(2026, 1, 1),
            severity=IssueSeverity.CRITICAL)
        self.assertEqual(dl, date(2026, 1, 8))

    def test_low_ninety_day_deadline(self):
        from utils.audit_controls_issues import (
            IssueSeverity, compute_issue_deadline)
        dl = compute_issue_deadline(
            raised_date=date(2026, 1, 1),
            severity=IssueSeverity.LOW)
        self.assertEqual(dl, date(2026, 4, 1))

    def test_invalid_transition_raises(self):
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine, Issue,
            IssueSource, IssueStatus, IssueSeverity)
        eng = AuditControlsIssuesEngine()
        eng.register_issue(Issue(
            issue_id="I1", source=IssueSource.CONTROL_TEST_FAILURE,
            severity=IssueSeverity.HIGH, status=IssueStatus.OPEN,
            description="x", raised_date="2026-01-01",
            raised_by_user_id="alice"))
        with self.assertRaises(ValueError):
            # OPEN → CLOSED is invalid
            eng.transition_issue(
                issue_id="I1", to_status=IssueStatus.CLOSED,
                actor="x", timestamp="t")

    def test_aging_buckets(self):
        from utils.audit_controls_issues import (
            IssueAgingBucket, compute_issue_aging)
        self.assertEqual(
            compute_issue_aging(
                days_past_deadline=0, days_remaining=20, sla_days=30),
            IssueAgingBucket.FRESH)
        self.assertEqual(
            compute_issue_aging(
                days_past_deadline=5, days_remaining=0, sla_days=30),
            IssueAgingBucket.OVERDUE)
        self.assertEqual(
            compute_issue_aging(
                days_past_deadline=45, days_remaining=0, sla_days=30),
            IssueAgingBucket.AGED)


class TestV1024AutomatedControlTesting(unittest.TestCase):
    """ENH-206 — Automated control testing."""

    def test_schedule_due_detection(self):
        from utils.audit_controls_issues import (
            TestSchedule, TestScheduleStatus)
        sch = TestSchedule(
            schedule_id="S1", script_id="X",
            next_run_date="2026-01-15", cadence_days=7)
        self.assertTrue(sch.is_due(as_of=date(2026, 1, 16)))
        self.assertFalse(sch.is_due(as_of=date(2026, 1, 14)))

    def test_disabled_schedule_not_due(self):
        from utils.audit_controls_issues import (
            TestSchedule, TestScheduleStatus)
        sch = TestSchedule(
            schedule_id="S1", script_id="X",
            next_run_date="2026-01-15", cadence_days=7,
            status=TestScheduleStatus.DISABLED)
        self.assertFalse(sch.is_due(as_of=date(2026, 1, 16)))

    def test_coverage_report_below_threshold(self):
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine, TestScript,
            TestScriptLanguage)
        eng = AuditControlsIssuesEngine()
        eng.register_test_script(TestScript(
            script_id="TS1", target_control_id="CTRL-001",
            script_language=TestScriptLanguage.SQL,
            script_description="x"))
        report = eng.compute_coverage(
            all_control_ids=["CTRL-001", "CTRL-002", "CTRL-003"])
        self.assertEqual(report.n_controls_total, 3)
        self.assertEqual(report.n_controls_with_automated_test, 1)
        self.assertFalse(report.coverage_passes_threshold(threshold_pct=80.0))


class TestV1024CrossFrameworkMapping(unittest.TestCase):
    """ENH-AUD-R1 — Control-graph cross-framework mapping."""

    def test_seed_concepts_loaded(self):
        from utils.audit_controls_issues import get_canonical_concepts
        concepts = get_canonical_concepts()
        # Should have at least 10 seed concepts
        self.assertGreaterEqual(len(concepts), 10)

    def test_access_control_maps_multiple_frameworks(self):
        from utils.audit_controls_issues import (
            ControlFramework, get_frameworks_covered_by_concept)
        fws = get_frameworks_covered_by_concept(
            "ACCESS_CONTROL_LOGICAL")
        self.assertIn(ControlFramework.ISO_27001, fws)
        self.assertIn(ControlFramework.NIST_CSF, fws)
        self.assertIn(ControlFramework.PCI_DSS, fws)

    def test_engine_map_control_by_concept(self):
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine, ControlFramework)
        eng = AuditControlsIssuesEngine()
        mapping = eng.map_control_by_concept(
            control_id="CTRL-A",
            canonical_concept="SEGREGATION_OF_DUTIES")
        framework_set = {fw for fw, _ in mapping.framework_refs}
        self.assertIn(ControlFramework.SOX_404, framework_set)
        self.assertIn(ControlFramework.COSO_IC, framework_set)

    def test_unknown_concept_raises(self):
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine)
        eng = AuditControlsIssuesEngine()
        with self.assertRaises(ValueError):
            eng.map_control_by_concept(
                control_id="X", canonical_concept="MYTHICAL_CONCEPT")


class TestV1024TicketingIntegration(unittest.TestCase):
    """ENH-AUD-R4 — Automated remediation ticketing integration."""

    def _issue(self):
        from utils.audit_controls_issues import (
            Issue, IssueSource, IssueStatus, IssueSeverity)
        return Issue(
            issue_id="I1", source=IssueSource.CONTROL_TEST_FAILURE,
            severity=IssueSeverity.HIGH, status=IssueStatus.OPEN,
            description="x", raised_date="2026-01-01",
            raised_by_user_id="alice")

    def test_no_creator_is_internal_only(self):
        """Rule 7 — no creator → INTERNAL_ONLY draft."""
        from utils.audit_controls_issues import (
            create_ticket_stub, TicketingSystem, TicketStatus)
        stub = create_ticket_stub(
            issue=self._issue(),
            ticketing_system=TicketingSystem.JIRA,
            stub_id="TS1", timestamp="t")
        self.assertEqual(stub.ticketing_system,
                          TicketingSystem.INTERNAL_ONLY)
        self.assertIsNone(stub.external_ticket_id)
        self.assertEqual(stub.status, TicketStatus.DRAFT)

    def test_with_creator_external_id_set(self):
        from utils.audit_controls_issues import (
            create_ticket_stub, TicketingSystem, TicketStatus)
        def fake(i):
            return ("PROJ-123", "https://j/PROJ-123")
        stub = create_ticket_stub(
            issue=self._issue(),
            ticketing_system=TicketingSystem.JIRA,
            stub_id="TS1", timestamp="t",
            ticket_creator=fake)
        self.assertEqual(stub.external_ticket_id, "PROJ-123")
        self.assertEqual(stub.status, TicketStatus.CREATED)

    def test_creator_failure_sync_failed(self):
        from utils.audit_controls_issues import (
            create_ticket_stub, TicketingSystem, TicketStatus)
        def failing(i):
            raise ConnectionError("Jira down")
        stub = create_ticket_stub(
            issue=self._issue(),
            ticketing_system=TicketingSystem.JIRA,
            stub_id="TS1", timestamp="t",
            ticket_creator=failing)
        self.assertEqual(stub.status, TicketStatus.SYNC_FAILED)


class TestV1024EngineEndToEnd(unittest.TestCase):
    def test_full_issue_lifecycle(self):
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine, Issue,
            IssueSource, IssueStatus, IssueSeverity)
        eng = AuditControlsIssuesEngine()
        eng.register_issue(Issue(
            issue_id="I1",
            source=IssueSource.CONTROL_TEST_FAILURE,
            severity=IssueSeverity.HIGH,
            status=IssueStatus.OPEN,
            description="control C1 failed test T1",
            raised_date="2026-01-01",
            raised_by_user_id="auditor",
            deadline_date="2026-01-31"))
        # Walk through the full path
        eng.transition_issue(
            issue_id="I1", to_status=IssueStatus.ASSIGNED,
            actor="x", timestamp="t1")
        eng.transition_issue(
            issue_id="I1", to_status=IssueStatus.IN_PROGRESS,
            actor="y", timestamp="t2")
        eng.transition_issue(
            issue_id="I1", to_status=IssueStatus.PENDING_VERIFICATION,
            actor="z", timestamp="t3")
        eng.transition_issue(
            issue_id="I1", to_status=IssueStatus.CLOSED,
            actor="w", timestamp="2026-01-30T00:00:00Z")
        issue = eng.get_issue("I1")
        self.assertEqual(issue.status, IssueStatus.CLOSED)


class TestV1024Coexistence(unittest.TestCase):
    def test_v10_23_v10_24_audit_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_controls_issues import (
            AuditControlsIssuesEngine)
        a = AuditCoreEngine(entity_name="X")
        b = AuditControlsIssuesEngine(entity_name="X")
        self.assertEqual(a.entity_name, b.entity_name)


if __name__ == "__main__":
    unittest.main()

"""tests/integration/test_v10_23_audit_core.py — v10.23.

Phase 2 batch 4 (Audit/GRC arc batch 1): core audit engine.
ENH-201 (audit universe + planning) + ENH-202 (control monitoring) +
ENH-203 (electronic working papers) + ENH-AUD-R7 (CVR architecture).
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1023Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import audit_core  # noqa

    def test_public_symbols(self):
        from utils import audit_core as m
        for sym in (
            # Universe
            "AuditableEntityType", "RiskRating", "RISK_RATING_VALUE",
            "AuditableEntity",
            # Planning
            "AuditFrequency", "DEFAULT_FREQUENCY_BY_RISK",
            "FREQUENCY_MONTHS",
            "AuditPlanItem", "determine_frequency",
            "is_audit_due", "build_annual_audit_plan",
            # Controls
            "ControlType", "ControlNature", "ControlFrequency",
            "Control", "ControlTestVerdict", "ControlSeverity",
            "DEFAULT_REMEDIATION_DAYS",
            "ControlTestResult", "execute_control_test",
            # Working papers
            "WorkingPaperType", "WorkingPaperStatus",
            "DEFAULT_WORKING_PAPER_RETENTION_YEARS",
            "WorkingPaper", "compute_paper_hash",
            # CVR
            "CVRStage", "CVRConnectorType", "CVRResponseAction",
            "CVRRunResult", "run_connect_validate_respond",
            # Engine
            "AuditCoreEngine", "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1023SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import audit_core
        audit_core.self_test()


class TestV1023RegistryAlignment(unittest.TestCase):
    def test_4_audit_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "audit" and s.status == "active"]
        self.assertGreaterEqual(len(active), 4)

    def test_v10_23_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "audit" and s.status == "active"}
        for sid in ("ENH-201", "ENH-202", "ENH-203", "ENH-AUD-R7"):
            self.assertIn(sid, active_ids)


class TestV1023AuditUniverse(unittest.TestCase):
    """ENH-201 — Audit universe."""

    def test_8_entity_types(self):
        from utils.audit_core import AuditableEntityType
        # Check the major entity types are defined
        for name in ("BUSINESS_LINE", "LEGAL_ENTITY", "PROCESS",
                       "SYSTEM", "GEOGRAPHY", "SUPPORT_FUNCTION",
                       "THIRD_PARTY", "REGULATORY_DOMAIN"):
            self.assertTrue(
                any(e.name == name for e in AuditableEntityType))

    def test_5_tier_risk_rating(self):
        from utils.audit_core import RiskRating, RISK_RATING_VALUE
        self.assertEqual(RISK_RATING_VALUE[RiskRating.VERY_LOW], 1)
        self.assertEqual(RISK_RATING_VALUE[RiskRating.CRITICAL], 5)

    def test_entity_risk_score(self):
        from utils.audit_core import (
            AuditableEntity, AuditableEntityType, RiskRating)
        e = AuditableEntity(
            entity_id="E", entity_name="X",
            entity_type=AuditableEntityType.PROCESS,
            inherent_risk=RiskRating.HIGH,
            residual_risk=RiskRating.MEDIUM)
        self.assertEqual(e.risk_score(), 7)


class TestV1023RiskBasedPlanning(unittest.TestCase):
    """ENH-201 — Risk-based audit planning."""

    def test_critical_to_annual(self):
        from utils.audit_core import (
            RiskRating, AuditFrequency, determine_frequency)
        self.assertEqual(determine_frequency(RiskRating.CRITICAL),
                          AuditFrequency.ANNUAL)

    def test_low_to_triennial(self):
        from utils.audit_core import (
            RiskRating, AuditFrequency, determine_frequency)
        self.assertEqual(determine_frequency(RiskRating.LOW),
                          AuditFrequency.TRIENNIAL)

    def test_plan_prioritizes_by_risk(self):
        from utils.audit_core import (
            AuditableEntity, AuditableEntityType, RiskRating,
            build_annual_audit_plan)
        entities = [
            AuditableEntity(
                entity_id="LOW", entity_name="Low",
                entity_type=AuditableEntityType.PROCESS,
                inherent_risk=RiskRating.LOW,
                residual_risk=RiskRating.LOW,
                last_audit_date=None),
            AuditableEntity(
                entity_id="CRIT", entity_name="Crit",
                entity_type=AuditableEntityType.PROCESS,
                inherent_risk=RiskRating.CRITICAL,
                residual_risk=RiskRating.CRITICAL,
                last_audit_date=None),
        ]
        plan = build_annual_audit_plan(
            entities=entities, fiscal_year=2026,
            as_of=date(2026, 1, 1))
        # Critical entity goes first, in Q1
        self.assertEqual(plan[0].entity_id, "CRIT")
        self.assertEqual(plan[0].planned_quarter, "2026-Q1")

    def test_recently_audited_excluded(self):
        from utils.audit_core import (
            AuditableEntity, AuditableEntityType, RiskRating,
            build_annual_audit_plan)
        entities = [
            AuditableEntity(
                entity_id="JUST", entity_name="Just done",
                entity_type=AuditableEntityType.PROCESS,
                inherent_risk=RiskRating.HIGH,
                residual_risk=RiskRating.HIGH,
                last_audit_date="2025-12-01"),
        ]
        plan = build_annual_audit_plan(
            entities=entities, fiscal_year=2026,
            as_of=date(2026, 1, 1))
        self.assertEqual(len(plan), 0)


class TestV1023ContinuousMonitoring(unittest.TestCase):
    """ENH-202 — Continuous control monitoring."""

    def _control(self, cid="C1", eid="E1"):
        from utils.audit_core import (
            Control, ControlType, ControlNature, ControlFrequency)
        return Control(
            control_id=cid, control_name="X",
            control_description="test",
            entity_id=eid,
            control_type=ControlType.PREVENTIVE,
            control_nature=ControlNature.AUTOMATED,
            control_frequency=ControlFrequency.DAILY)

    def test_no_provider_returns_requires_provider(self):
        """Rule 7 — no automated tester → REQUIRES_PROVIDER, not silent EFFECTIVE."""
        from utils.audit_core import execute_control_test, ControlTestVerdict
        r = execute_control_test(
            control=self._control(), test_id="T1",
            test_date="2026-01-15")
        self.assertEqual(r.verdict, ControlTestVerdict.REQUIRES_PROVIDER)

    def test_critical_failure_seven_day_remediation(self):
        from utils.audit_core import (
            execute_control_test, ControlTestVerdict, ControlSeverity)
        def tester(c):
            return (ControlTestVerdict.DEFICIENT_OPERATING, 100, 80)
        r = execute_control_test(
            control=self._control(), test_id="T1",
            test_date="2026-01-15", automated_tester=tester)
        self.assertEqual(r.severity, ControlSeverity.CRITICAL)
        self.assertEqual(r.remediation_due, "2026-01-22")

    def test_low_failure_ninety_day_remediation(self):
        from utils.audit_core import (
            execute_control_test, ControlTestVerdict, ControlSeverity)
        def tester(c):
            return (ControlTestVerdict.PARTIAL, 100, 1)
        r = execute_control_test(
            control=self._control(), test_id="T1",
            test_date="2026-01-15", automated_tester=tester)
        self.assertEqual(r.severity, ControlSeverity.LOW)
        self.assertEqual(r.remediation_due, "2026-04-15")


class TestV1023WorkingPapers(unittest.TestCase):
    """ENH-203 — Electronic working papers."""

    def test_seven_year_retention(self):
        from utils.audit_core import DEFAULT_WORKING_PAPER_RETENTION_YEARS
        self.assertEqual(DEFAULT_WORKING_PAPER_RETENTION_YEARS, 7)

    def test_paper_integrity_check(self):
        from utils.audit_core import (
            WorkingPaper, WorkingPaperType, compute_paper_hash)
        content = b"audit working paper"
        h = compute_paper_hash(content)
        p = WorkingPaper(
            paper_id="WP1",
            paper_type=WorkingPaperType.TEST_RESULTS,
            audit_engagement_id="ENG1",
            title="t", prepared_by_user_id="alice",
            prepared_at="t", sha256_content_hash=h)
        self.assertTrue(p.integrity_check(current_content=content))
        self.assertFalse(p.integrity_check(current_content=b"tampered"))


class TestV1023ConnectValidateRespond(unittest.TestCase):
    """ENH-AUD-R7 — Connect-Validate-Respond architecture."""

    def _control(self):
        from utils.audit_core import (
            Control, ControlType, ControlNature, ControlFrequency)
        return Control(
            control_id="C1", control_name="X",
            control_description="x", entity_id="E1",
            control_type=ControlType.DETECTIVE,
            control_nature=ControlNature.AUTOMATED,
            control_frequency=ControlFrequency.DAILY)

    def test_full_path_passes(self):
        from utils.audit_core import (
            run_connect_validate_respond, CVRStage,
            CVRResponseAction)
        def conn(c):
            return (True, [{"x": 1}])
        def val(c, d):
            return (1, 0)
        def resp(c, p, f):
            return ()
        r = run_connect_validate_respond(
            run_id="R1", control=self._control(),
            connector=conn, validator=val, responder=resp)
        self.assertTrue(r.fully_completed())
        self.assertIn(CVRResponseAction.NO_ACTION_REQUIRED,
                          r.response_actions_taken)

    def test_failures_trigger_response_actions(self):
        from utils.audit_core import (
            run_connect_validate_respond, CVRResponseAction)
        def conn(c):
            return (True, [{"x": 1}, {"x": 2}])
        def val(c, d):
            return (0, 2)
        def resp(c, p, f):
            return (CVRResponseAction.LOG_FINDING,
                      CVRResponseAction.OPEN_TICKET,
                      CVRResponseAction.ESCALATE_TO_AUDIT_COMMITTEE)
        r = run_connect_validate_respond(
            run_id="R1", control=self._control(),
            connector=conn, validator=val, responder=resp)
        self.assertEqual(len(r.response_actions_taken), 3)

    def test_no_connector_stops_at_connect(self):
        from utils.audit_core import (
            run_connect_validate_respond, CVRStage)
        r = run_connect_validate_respond(
            run_id="R1", control=self._control())
        self.assertEqual(r.stage_completed, CVRStage.CONNECT)
        self.assertFalse(r.connect_success)


class TestV1023EngineEndToEnd(unittest.TestCase):
    def test_engine_overdue_remediations_surface(self):
        from utils.audit_core import (
            AuditableEntity, AuditableEntityType, RiskRating,
            Control, ControlType, ControlNature, ControlFrequency,
            ControlTestVerdict,
            AuditCoreEngine)
        eng = AuditCoreEngine()
        eng.register_entity(AuditableEntity(
            entity_id="E1", entity_name="X",
            entity_type=AuditableEntityType.PROCESS,
            inherent_risk=RiskRating.HIGH,
            residual_risk=RiskRating.HIGH))
        eng.register_control(Control(
            control_id="C1", control_name="X",
            control_description="x", entity_id="E1",
            control_type=ControlType.PREVENTIVE,
            control_nature=ControlNature.AUTOMATED,
            control_frequency=ControlFrequency.DAILY))

        def crit_tester(c):
            return (ControlTestVerdict.DEFICIENT_OPERATING, 10, 9)
        eng.execute_test(
            control_id="C1", test_id="T1",
            test_date="2026-01-01", automated_tester=crit_tester)
        # 7-day deadline → 2026-01-08; check overdue at Jan 15
        overdue = eng.overdue_remediations(as_of=date(2026, 1, 15))
        self.assertEqual(len(overdue), 1)


class TestV1023Coexistence(unittest.TestCase):
    def test_audit_coexists_with_rms(self):
        from utils.audit_core import AuditCoreEngine
        from utils.reconciliation_matching import (
            ReconciliationMatchingEngine)
        from utils.benchmark_rates import BenchmarkRateRegistry
        a = AuditCoreEngine(entity_name="X")
        r = ReconciliationMatchingEngine(entity_name="X")
        b = BenchmarkRateRegistry(entity_name="X")
        for e in (a, r, b):
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()

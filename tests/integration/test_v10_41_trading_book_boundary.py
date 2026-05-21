"""tests/integration/test_v10_41_trading_book_boundary.py — v10.41.

Risk arc continues — Trading Book Boundary classification:
- ENH-MR-008 Trading Book Boundary Classification
- ENH-MR-009 Trading Desk Definition & Risk Factor Mapping
- ENH-MR-010 Boundary Crossing Approval Workflow
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[2]
sys.path.insert(0, str(_ROOT))


class TestV1041Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import trading_book_boundary    # noqa


class TestV1041PublicSurface(unittest.TestCase):
    """Per Rule 1: stable public contract."""

    def test_public_symbols(self):
        from utils import trading_book_boundary as m
        for sym in (
            "BookClassification", "InstrumentType",
            "DeskValidationIssue", "ApprovalStatus",
            "TradingDesk", "BookAssignment",
            "ReclassificationRequest", "ApprovalDecision",
            "BoundaryEngine",
            "PRESUMPTIVE_TRADING_BOOK", "PRESUMPTIVE_BANKING_BOOK",
            "ALL_DEFAULT_DESKS", "build_default_engine",
            "presumptive_classification",
            "DEFAULT_DESK_FX", "DEFAULT_DESK_FIXED_INCOME",
            "DEFAULT_DESK_EQUITY",
            "DEFAULT_SURCHARGE_RATE",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(
                hasattr(m, sym),
                f"trading_book_boundary missing: {sym}")


class TestV1041SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import trading_book_boundary
        trading_book_boundary.self_test()


class TestV1041PresumptiveLists(unittest.TestCase):
    """ENH-MR-008 — presumptive classification per BCBS d352 §A.4."""

    def test_presumption_lists_disjoint(self):
        from utils.trading_book_boundary import (
            PRESUMPTIVE_TRADING_BOOK, PRESUMPTIVE_BANKING_BOOK)
        self.assertEqual(
            PRESUMPTIVE_TRADING_BOOK & PRESUMPTIVE_BANKING_BOOK,
            frozenset())

    def test_listed_equity_presumed_trading_book(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType,
            presumptive_classification)
        self.assertEqual(
            presumptive_classification(InstrumentType.LISTED_EQUITY),
            BookClassification.TRADING_BOOK)

    def test_loan_presumed_banking_book(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType,
            presumptive_classification)
        self.assertEqual(
            presumptive_classification(InstrumentType.LOAN_RECEIVABLE),
            BookClassification.BANKING_BOOK)

    def test_unclassified_returns_none(self):
        from utils.trading_book_boundary import (
            InstrumentType, presumptive_classification)
        self.assertIsNone(
            presumptive_classification(InstrumentType.UNCLASSIFIED))


class TestV1041TradingDesk(unittest.TestCase):
    """ENH-MR-009 — TradingDesk validation."""

    def test_complete_desk_validates_OK(self):
        from utils.market_risk_factors import RiskFactorClass
        from utils.trading_book_boundary import (
            DeskValidationIssue, TradingDesk)
        desk = TradingDesk(
            desk_id="D1", name="Test", head_trader="Alice",
            mandate="Test mandate",
            risk_classes=frozenset({
                RiskFactorClass.FOREIGN_EXCHANGE}),
            default_holding_period_days=1,
            parent_business_unit="Treasury")
        self.assertEqual(
            desk.validate(),
            (DeskValidationIssue.OK,))

    def test_zero_holding_period_rejected(self):
        from utils.market_risk_factors import RiskFactorClass
        from utils.trading_book_boundary import TradingDesk
        with self.assertRaises(ValueError):
            TradingDesk(
                desk_id="D1", name="Test", head_trader="Alice",
                mandate="x",
                risk_classes=frozenset({RiskFactorClass.EQUITY}),
                default_holding_period_days=0,
                parent_business_unit="Treasury")

    def test_empty_risk_classes_rejected(self):
        from utils.trading_book_boundary import TradingDesk
        with self.assertRaises(ValueError):
            TradingDesk(
                desk_id="D1", name="Test", head_trader="Alice",
                mandate="x",
                risk_classes=frozenset(),
                default_holding_period_days=1,
                parent_business_unit="Treasury")

    def test_default_engine_has_3_complete_desks(self):
        from utils.trading_book_boundary import (
            DeskValidationIssue, build_default_engine)
        engine = build_default_engine()
        self.assertEqual(len(engine.all_desks()), 3)
        issues = engine.validate_trading_desk_completeness()
        for desk_id, issue_tuple in issues.items():
            self.assertEqual(
                issue_tuple, (DeskValidationIssue.OK,),
                f"desk {desk_id} has issues")


class TestV1041Classification(unittest.TestCase):
    """ENH-MR-008 — assignment behavior."""

    def test_listed_equity_to_trading_book(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        a = engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        self.assertEqual(
            a.classification, BookClassification.TRADING_BOOK)
        self.assertTrue(a.is_presumptive)

    def test_trading_book_requires_desk(self):
        from utils.trading_book_boundary import (
            InstrumentType, build_default_engine)
        engine = build_default_engine()
        with self.assertRaises(ValueError):
            engine.classify(
                position_id="P1",
                instrument_type=InstrumentType.LISTED_EQUITY,
                effective_date="2026-01-15")

    def test_banking_book_must_not_have_desk(self):
        from utils.trading_book_boundary import (
            InstrumentType, build_default_engine)
        engine = build_default_engine()
        with self.assertRaises(ValueError):
            engine.classify(
                position_id="L1",
                instrument_type=InstrumentType.LOAN_RECEIVABLE,
                effective_date="2026-01-15",
                trading_desk_id="DESK-FI-NAIROBI")

    def test_unknown_desk_rejected(self):
        from utils.trading_book_boundary import (
            InstrumentType, build_default_engine)
        engine = build_default_engine()
        with self.assertRaises(ValueError):
            engine.classify(
                position_id="P1",
                instrument_type=InstrumentType.LISTED_EQUITY,
                effective_date="2026-01-15",
                trading_desk_id="DESK-NONEXISTENT")

    def test_override_requires_justification_and_approver(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        with self.assertRaises(ValueError):
            engine.classify(
                position_id="P1",
                instrument_type=InstrumentType.LISTED_EQUITY,
                effective_date="2026-01-15",
                override_to=BookClassification.BANKING_BOOK,
                # missing justification + approved_by
            )


class TestV1041ReclassificationRequest(unittest.TestCase):
    """ENH-MR-010 — request creation."""

    def test_empty_reason_rejected(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        with self.assertRaises(ValueError):
            engine.request_reclassification(
                request_id="R1", position_id="P1",
                to_book=BookClassification.BANKING_BOOK,
                reason="",
                expected_capital_impact_kes=Decimal("0"),
                requested_by="trader1",
                request_date="2026-02-01")

    def test_no_op_reclassification_rejected(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        with self.assertRaises(ValueError):
            engine.request_reclassification(
                request_id="R1", position_id="P1",
                to_book=BookClassification.TRADING_BOOK,    # same!
                reason="x",
                expected_capital_impact_kes=Decimal("0"),
                requested_by="trader1",
                request_date="2026-02-01")


class TestV1041CapitalSurcharge(unittest.TestCase):
    """ENH-MR-010 — surcharge per BCBS d352 §A.4.5."""

    def test_surcharge_only_when_benefits_bank(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        # Beneficial: positive impact → surcharge
        req_pos = engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="strategic shift",
            expected_capital_impact_kes=Decimal("10000000"),
            requested_by="trader1",
            request_date="2026-02-01")
        self.assertEqual(
            engine.compute_capital_surcharge(req_pos),
            Decimal("10000000"))
        # Non-beneficial: negative impact → no surcharge
        req_neg = engine.request_reclassification(
            request_id="R2", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="risk reduction",
            expected_capital_impact_kes=Decimal("-5000000"),
            requested_by="trader1",
            request_date="2026-02-01")
        self.assertEqual(
            engine.compute_capital_surcharge(req_neg),
            Decimal("0"))

    def test_custom_surcharge_rate(self):
        from utils.trading_book_boundary import (
            BookClassification, BoundaryEngine, InstrumentType,
            ALL_DEFAULT_DESKS)
        # 50% surcharge instead of 100% default
        engine = BoundaryEngine(surcharge_rate=Decimal("0.5"))
        for d in ALL_DEFAULT_DESKS:
            engine.register_desk(d)
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        req = engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="strategic shift",
            expected_capital_impact_kes=Decimal("10000000"),
            requested_by="trader1",
            request_date="2026-02-01")
        self.assertEqual(
            engine.compute_capital_surcharge(req),
            Decimal("5000000"))


class TestV1041ApprovalWorkflow(unittest.TestCase):
    """ENH-MR-010 — Per Rule 7: explicit approval required."""

    def test_approval_requires_approver(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        req = engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="strategic shift",
            expected_capital_impact_kes=Decimal("0"),
            requested_by="trader1",
            request_date="2026-02-01")
        with self.assertRaises(ValueError):
            engine.approve_reclassification(
                request=req,
                approver="",    # empty
                decision_date="2026-02-05",
                decision_id="D1")

    def test_approval_mutates_assignment(self):
        from utils.trading_book_boundary import (
            ApprovalStatus, BookClassification, InstrumentType,
            build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        req = engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="strategic shift",
            expected_capital_impact_kes=Decimal("0"),
            requested_by="trader1",
            request_date="2026-02-01")
        decision, new_a = engine.approve_reclassification(
            request=req,
            approver="senior_mgmt",
            decision_date="2026-02-05",
            decision_id="D1")
        self.assertEqual(decision.status, ApprovalStatus.APPROVED)
        self.assertEqual(
            new_a.classification, BookClassification.BANKING_BOOK)
        self.assertFalse(new_a.is_presumptive)
        # Assignment in registry is updated
        self.assertEqual(
            engine.get_assignment("P1").classification,
            BookClassification.BANKING_BOOK)

    def test_rejection_does_not_mutate(self):
        """Per Rule 7: REJECTED leaves assignment unchanged."""
        from utils.trading_book_boundary import (
            ApprovalStatus, BookClassification, InstrumentType,
            build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        req = engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="x",
            expected_capital_impact_kes=Decimal("0"),
            requested_by="trader1",
            request_date="2026-02-01")
        decision = engine.reject_reclassification(
            request=req,
            approver="senior_mgmt",
            decision_date="2026-02-05",
            decision_id="D1")
        self.assertEqual(decision.status, ApprovalStatus.REJECTED)
        # Assignment still TB
        self.assertEqual(
            engine.get_assignment("P1").classification,
            BookClassification.TRADING_BOOK)

    def test_request_alone_does_not_mutate(self):
        """Per Rule 7: request creation never auto-changes book."""
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="P1",
            instrument_type=InstrumentType.LISTED_EQUITY,
            effective_date="2026-01-15",
            trading_desk_id="DESK-EQ-NAIROBI")
        engine.request_reclassification(
            request_id="R1", position_id="P1",
            to_book=BookClassification.BANKING_BOOK,
            reason="x",
            expected_capital_impact_kes=Decimal("100000000"),
            requested_by="trader1",
            request_date="2026-02-01")
        # Despite huge capital benefit, no auto-approval
        self.assertEqual(
            engine.get_assignment("P1").classification,
            BookClassification.TRADING_BOOK)

    def test_approval_to_trading_book_requires_desk(self):
        from utils.trading_book_boundary import (
            BookClassification, InstrumentType, build_default_engine)
        engine = build_default_engine()
        engine.classify(
            position_id="L1",
            instrument_type=InstrumentType.LOAN_RECEIVABLE,
            effective_date="2026-01-15")
        req = engine.request_reclassification(
            request_id="R1", position_id="L1",
            to_book=BookClassification.TRADING_BOOK,
            reason="repurpose for market making",
            expected_capital_impact_kes=Decimal("0"),
            requested_by="trader1",
            request_date="2026-02-01")
        with self.assertRaises(ValueError):
            engine.approve_reclassification(
                request=req,
                approver="senior_mgmt",
                decision_date="2026-02-05",
                decision_id="D1")    # missing new_trading_desk_id


class TestV1041StandardsRegistry(unittest.TestCase):
    """ENH-MR-008/009/010 active in registry."""

    def test_3_v10_41_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        new_std = [
            s for s in STANDARDS_REGISTRY
            if s.standard_id in (
                "ENH-MR-008", "ENH-MR-009", "ENH-MR-010")]
        self.assertEqual(len(new_std), 3)
        for s in new_std:
            self.assertEqual(s.status, "active")
            self.assertEqual(s.implementation_batch, "v10.41")
            self.assertEqual(
                s.affected_engines, ("trading_book_boundary",))


class TestV1041ScenarioLibrary(unittest.TestCase):
    """5 BOUNDARY-* scenarios PASS when engines wired."""

    def test_5_boundary_scenarios_in_library(self):
        from utils.scenario_simulator import TREASURY_SCENARIO_LIBRARY
        boundary = [
            s for s in TREASURY_SCENARIO_LIBRARY
            if s.scenario_id.startswith("BOUNDARY-")]
        self.assertEqual(len(boundary), 5)

    def test_boundary_scenarios_pass(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY, ScenarioRunner)
        from utils import (
            trading_book_boundary, market_risk_factors)
        engines = {
            "trading_book_boundary": trading_book_boundary,
            "market_risk_factors": market_risk_factors,
        }
        runner = ScenarioRunner(engines=engines)
        boundary = [
            s for s in TREASURY_SCENARIO_LIBRARY
            if s.scenario_id.startswith("BOUNDARY-")]
        for scen in boundary:
            result = runner.run(scen)
            self.assertEqual(
                result.n_failed, 0,
                f"{scen.scenario_id}: {result.n_failed} failures; "
                f"status={result.status}")


class TestV1041StructuralIntegrity(unittest.TestCase):
    """G128 baseline must remain stable after v10.41."""

    def test_no_new_circular_imports(self):
        import json
        from utils.structure_audit_core import (
            StructureAuditEngine, compare_to_baseline)
        baseline_path = (
            _ROOT / "docs" / "structure_audit_baseline.json")
        if not baseline_path.exists():
            self.skipTest("no baseline")
        engine = StructureAuditEngine(project_root=_ROOT)
        result = engine.audit()
        baseline = json.loads(baseline_path.read_text())
        comparison = compare_to_baseline(result, baseline)
        self.assertFalse(
            comparison.is_regression,
            f"v10.41 introduced structural regression: "
            f"{comparison.summary}")


class TestV1041AuditScore(unittest.TestCase):
    """Audit score must remain ≥ 128."""

    def test_audit_score_at_least_128(self):
        import re
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "audit.py")],
            cwd=str(_ROOT),
            capture_output=True, text=True, timeout=180)
        self.assertIn("PASS", result.stdout)
        score_line = next(
            (ln for ln in result.stdout.splitlines()
             if "Score:" in ln), "")
        m = re.search(r"(\d+)/(\d+)", score_line)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 128)


if __name__ == "__main__":
    unittest.main()

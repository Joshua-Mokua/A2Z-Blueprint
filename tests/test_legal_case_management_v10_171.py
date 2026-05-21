"""tests/test_legal_case_management_v10_171.py — ENH-223 Legal Case
Management."""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "legal_case_management.py"
REGISTRY_PATH = REPO_ROOT / "utils" / "standards_registry.py"
ADMIN_PATH = REPO_ROOT / "pages" / "7_admin.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_parses(self):
        ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))

    def test_imports(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        assert LegalCaseManagementEngine() is not None

    def test_enums(self):
        from utils.legal_case_management import (
            CaseStage, CaseOutcome, TransitionOutcome)
        assert len(list(CaseStage)) == 6
        assert len(list(CaseOutcome)) == 7
        assert len(list(TransitionOutcome)) == 4


class TestRegistry:
    def test_active(self):
        m = _load("registry_v171", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-223"), None)
        assert s.status == "active"
        assert "legal_case_management" in s.affected_engines


class TestHubIntegration:
    def test_in_hub(self):
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"legal_case_management"' in admin_text


class TestOpenCase:
    def _eng(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        return LegalCaseManagementEngine()

    def test_default_intake(self):
        from utils.legal_case_management import CaseStage
        eng = self._eng()
        c = eng.open_case(matter_name="X", counterparty="Y",
                            case_type="litigation",
                            materiality="HIGH",
                            lead_counsel="head_of_legal")
        assert c.stage == CaseStage.INTAKE

    def test_invalid_materiality_rejected(self):
        eng = self._eng()
        try:
            eng.open_case(matter_name="X", counterparty="Y",
                            case_type="litigation",
                            materiality="UNKNOWN",
                            lead_counsel="legal")
            raise AssertionError("invalid materiality should raise")
        except ValueError:
            pass

    def test_empty_lead_rejected(self):
        eng = self._eng()
        try:
            eng.open_case(matter_name="X", counterparty="Y",
                            case_type="litigation",
                            materiality="HIGH", lead_counsel="")
            raise AssertionError("empty lead should raise")
        except ValueError:
            pass


class TestCaseLifecycle:
    def _opened(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        c = eng.open_case(matter_name="X", counterparty="Y",
                            case_type="litigation",
                            materiality="HIGH",
                            lead_counsel="legal")
        return eng, c

    def test_intake_to_analysis(self):
        from utils.legal_case_management import (
            CaseStage, TransitionOutcome)
        eng, c = self._opened()
        outcome, c = eng.transition(c.case_id, CaseStage.ANALYSIS,
                                          user="x")
        assert outcome == TransitionOutcome.OK
        assert c.stage == CaseStage.ANALYSIS

    def test_skip_stage_rejected(self):
        from utils.legal_case_management import (
            CaseStage, TransitionOutcome)
        eng, c = self._opened()
        outcome, _ = eng.transition(c.case_id, CaseStage.STRATEGY,
                                          user="x")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_resolution_requires_outcome(self):
        from utils.legal_case_management import (
            CaseStage, CaseOutcome, TransitionOutcome)
        eng, c = self._opened()
        for s in (CaseStage.ANALYSIS, CaseStage.STRATEGY,
                    CaseStage.EXECUTION):
            eng.transition(c.case_id, s, user="x")
        outcome, _ = eng.transition(c.case_id, CaseStage.RESOLUTION,
                                          user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_resolution_with_outcome(self):
        from utils.legal_case_management import (
            CaseStage, CaseOutcome, TransitionOutcome)
        eng, c = self._opened()
        for s in (CaseStage.ANALYSIS, CaseStage.STRATEGY,
                    CaseStage.EXECUTION):
            eng.transition(c.case_id, s, user="x")
        outcome, c = eng.transition(
            c.case_id, CaseStage.RESOLUTION, user="x",
            outcome=CaseOutcome.SETTLED,
            resolution_notes="settled out of court")
        assert outcome == TransitionOutcome.OK
        assert c.outcome == CaseOutcome.SETTLED
        assert c.closed_at_utc != ""

    def test_withdrawn_requires_reason(self):
        from utils.legal_case_management import (
            CaseStage, TransitionOutcome)
        eng, c = self._opened()
        outcome, _ = eng.transition(c.case_id, CaseStage.WITHDRAWN,
                                          user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_withdrawn_from_any_pre_resolution_stage(self):
        from utils.legal_case_management import (
            CaseStage, CaseOutcome, TransitionOutcome)
        eng, c = self._opened()
        eng.transition(c.case_id, CaseStage.ANALYSIS, user="x")
        outcome, c = eng.transition(c.case_id, CaseStage.WITHDRAWN,
                                          user="x", reason="dismissed")
        assert outcome == TransitionOutcome.OK
        assert c.outcome == CaseOutcome.WITHDRAWN


class TestCommunicationsAndBilling:
    def _opened(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        c = eng.open_case(matter_name="X", counterparty="Y",
                            case_type="litigation",
                            materiality="HIGH",
                            lead_counsel="legal")
        return eng, c

    def test_add_communication(self):
        eng, c = self._opened()
        c = eng.add_communication(c.case_id, "lead", "court",
                                        "Filed pleading")
        assert len(c.communications) == 1
        assert c.communications[0].channel == "court"

    def test_empty_communication_rejected(self):
        eng, c = self._opened()
        try:
            eng.add_communication(c.case_id, "lead", "email", "")
            raise AssertionError("empty summary should raise")
        except ValueError:
            pass

    def test_add_billable_entry(self):
        eng, c = self._opened()
        c = eng.add_billable_entry(c.case_id, "internal_counsel",
                                          "Jane", Decimal("3.5"),
                                          "drafting")
        assert len(c.billable_entries) == 1
        assert c.total_hours() == Decimal("3.5")

    def test_billable_hours_aggregate(self):
        eng, c = self._opened()
        c = eng.add_billable_entry(c.case_id, "internal", "A",
                                          Decimal("2"), "x")
        c = eng.add_billable_entry(c.case_id, "external", "B",
                                          Decimal("5.5"), "y")
        assert c.total_hours() == Decimal("7.5")

    def test_negative_hours_rejected(self):
        eng, c = self._opened()
        try:
            eng.add_billable_entry(c.case_id, "internal", "A",
                                          Decimal("-1"), "x")
            raise AssertionError("negative hours should raise")
        except ValueError:
            pass

    def test_link_document_idempotent(self):
        eng, c = self._opened()
        c = eng.link_document(c.case_id, "DOC-001")
        c = eng.link_document(c.case_id, "DOC-001")  # again
        assert len(c.document_refs) == 1


class TestQueries:
    def test_open_vs_resolved(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine, CaseStage, CaseOutcome)
        eng = LegalCaseManagementEngine()
        c1 = eng.open_case("X", "Y", "lit", "HIGH", "legal")
        c2 = eng.open_case("X2", "Y", "lit", "CRITICAL", "legal")
        # Resolve c1 fully
        for s in (CaseStage.ANALYSIS, CaseStage.STRATEGY,
                    CaseStage.EXECUTION):
            eng.transition(c1.case_id, s, user="x")
        eng.transition(c1.case_id, CaseStage.RESOLUTION, user="x",
                          outcome=CaseOutcome.SETTLED,
                          resolution_notes="x")
        assert len(eng.open_cases()) == 1
        assert len(eng.critical_open_cases()) == 1


class TestHonestDeferrals:
    def test_document_storage(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        s = eng.board_summary()
        assert "META_ONLY" in s["document_storage_status"]

    def test_billing(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["billing_integration_status"]


class TestPortfolioSummary:
    def test_shape(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_cases_total", "n_open",
                   "n_critical_open", "stage_counts",
                   "materiality_counts", "outcome_counts",
                   "total_billable_hours",
                   "document_storage_status",
                   "billing_integration_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-223 LegalCaseManagementEngine"


class TestNoRegression:
    def test_audit_passes(self):
        m = _load("audit_v171", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True

    def test_v10_170_obligation_works(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        eng = ObligationTrackingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-222 ObligationTrackingEngine")

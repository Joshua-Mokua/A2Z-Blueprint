"""tests/test_legal_hold_management_v10_175.py — ENH-227"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "legal_hold_management.py"
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
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        assert LegalHoldManagementEngine() is not None

    def test_enums(self):
        from utils.legal_hold_management import (
            HoldStatus, AcknowledgmentStatus, TransitionOutcome)
        assert len(list(HoldStatus)) == 5
        assert len(list(AcknowledgmentStatus)) == 3
        assert len(list(TransitionOutcome)) == 5


class TestRegistry:
    def test_active(self):
        m = _load("registry_v175", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-227"), None)
        assert s.status == "active"
        assert "legal_hold_management" in s.affected_engines


class TestHubIntegration:
    def test_in_hub(self):
        admin = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"legal_hold_management"' in admin


class TestHoldCreation:
    def _eng(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        return LegalHoldManagementEngine()

    def test_create_draft(self):
        from utils.legal_hold_management import HoldStatus
        eng = self._eng()
        h = eng.create_hold(
            matter_reference="CASE-1", title="T",
            trigger_event="trigger", scope_description="scope",
            document_categories=("emails",),
            date_range_start="2024-01-01", date_range_end="",
            issuer_role="head_of_legal")
        assert h.status == HoldStatus.DRAFT

    def test_no_categories_rejected(self):
        eng = self._eng()
        try:
            eng.create_hold("X", "T", "trig", "scope", (),
                              "2024-01-01", "", "head")
            raise AssertionError("empty categories should raise")
        except ValueError:
            pass

    def test_no_trigger_rejected(self):
        eng = self._eng()
        try:
            eng.create_hold("X", "T", "", "scope", ("emails",),
                              "2024-01-01", "", "head")
            raise AssertionError("empty trigger should raise")
        except ValueError:
            pass


class TestCustodianAddition:
    def _drafted(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        h = eng.create_hold("CASE-1", "T", "trig", "scope",
                              ("emails",), "2024-01-01", "",
                              "head_of_legal")
        return eng, h

    def test_add_idempotent(self):
        eng, h = self._drafted()
        a1 = eng.add_custodian(h.hold_id, "EMP-1", "A", "rm")
        a2 = eng.add_custodian(h.hold_id, "EMP-1", "A", "rm")
        assert a1.acknowledgment_id == a2.acknowledgment_id


class TestHoldLifecycle:
    def _draft_with_custodians(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        h = eng.create_hold("CASE-1", "T", "trig", "scope",
                              ("emails",), "2024-01-01", "",
                              "head_of_legal")
        eng.add_custodian(h.hold_id, "EMP-1", "A", "rm")
        eng.add_custodian(h.hold_id, "EMP-2", "B", "co")
        return eng, h

    def test_issue_no_custodians_rejected(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine, HoldStatus,
            TransitionOutcome)
        eng = LegalHoldManagementEngine()
        h = eng.create_hold("CASE-1", "T", "trig", "scope",
                              ("emails",), "2024-01-01", "",
                              "head_of_legal")
        outcome, _ = eng.transition_hold(h.hold_id, HoldStatus.ISSUED,
                                                user="x")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_issue_with_custodians_works(self):
        from utils.legal_hold_management import (
            HoldStatus, TransitionOutcome)
        eng, h = self._draft_with_custodians()
        outcome, h = eng.transition_hold(h.hold_id, HoldStatus.ISSUED,
                                                user="x")
        assert outcome == TransitionOutcome.OK
        assert h.status == HoldStatus.ISSUED

    def test_acknowledged_requires_all_acks(self):
        from utils.legal_hold_management import (
            HoldStatus, TransitionOutcome)
        eng, h = self._draft_with_custodians()
        eng.transition_hold(h.hold_id, HoldStatus.ISSUED, user="x")
        outcome, _ = eng.transition_hold(
            h.hold_id, HoldStatus.ACKNOWLEDGED, user="x")
        assert outcome == TransitionOutcome.REJECTED_NOT_ALL_ACKNOWLEDGED

    def test_acknowledged_with_partial_rejected(self):
        from utils.legal_hold_management import (
            HoldStatus, TransitionOutcome)
        eng, h = self._draft_with_custodians()
        eng.transition_hold(h.hold_id, HoldStatus.ISSUED, user="x")
        acks = eng.acknowledgments_for_hold(h.hold_id)
        eng.record_acknowledgment(acks[0].acknowledgment_id)
        outcome, _ = eng.transition_hold(
            h.hold_id, HoldStatus.ACKNOWLEDGED, user="x")
        assert outcome == TransitionOutcome.REJECTED_NOT_ALL_ACKNOWLEDGED

    def test_acknowledged_with_all(self):
        from utils.legal_hold_management import (
            HoldStatus, TransitionOutcome)
        eng, h = self._draft_with_custodians()
        eng.transition_hold(h.hold_id, HoldStatus.ISSUED, user="x")
        for a in eng.acknowledgments_for_hold(h.hold_id):
            eng.record_acknowledgment(a.acknowledgment_id)
        outcome, h = eng.transition_hold(
            h.hold_id, HoldStatus.ACKNOWLEDGED,
            user="x", reason="all acks in")
        assert outcome == TransitionOutcome.OK
        assert h.status == HoldStatus.ACKNOWLEDGED

    def test_release_requires_reason(self):
        from utils.legal_hold_management import (
            HoldStatus, TransitionOutcome)
        eng, h = self._draft_with_custodians()
        eng.transition_hold(h.hold_id, HoldStatus.ISSUED, user="x")
        outcome, _ = eng.transition_hold(
            h.hold_id, HoldStatus.RELEASED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_revoke_path(self):
        from utils.legal_hold_management import (
            HoldStatus, TransitionOutcome)
        eng, h = self._draft_with_custodians()
        outcome, h = eng.transition_hold(
            h.hold_id, HoldStatus.REVOKED, user="x",
            reason="trigger event resolved without litigation")
        assert outcome == TransitionOutcome.OK
        assert h.status == HoldStatus.REVOKED


class TestAcknowledgments:
    def _ready(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        h = eng.create_hold("CASE-1", "T", "trig", "scope",
                              ("emails",), "2024-01-01", "",
                              "head_of_legal")
        a = eng.add_custodian(h.hold_id, "EMP-1", "A", "rm")
        return eng, a

    def test_record_pending_to_acknowledged(self):
        from utils.legal_hold_management import (
            AcknowledgmentStatus, TransitionOutcome)
        eng, a = self._ready()
        outcome, a = eng.record_acknowledgment(
            a.acknowledgment_id, notes="received")
        assert outcome == TransitionOutcome.OK
        assert a.status == AcknowledgmentStatus.ACKNOWLEDGED

    def test_record_already_acknowledged_rejected(self):
        from utils.legal_hold_management import TransitionOutcome
        eng, a = self._ready()
        eng.record_acknowledgment(a.acknowledgment_id)
        outcome, _ = eng.record_acknowledgment(
            a.acknowledgment_id)
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_escalate_requires_reason(self):
        from utils.legal_hold_management import TransitionOutcome
        eng, a = self._ready()
        outcome, _ = eng.mark_escalated(a.acknowledgment_id,
                                              reason="")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_overdue_filter(self):
        eng, a = self._ready()
        # Force-overdue by checking at a later as-of date
        future_date = "2099-01-01"
        out = eng.overdue_acknowledgments(as_of_date=future_date)
        assert len(out) == 1


class TestHonestDeferrals:
    def test_three(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["automated_preservation_holds_status"]
        assert "DEFERRED" in s["escalation_notification_status"]
        assert "META_ONLY" in s["chain_of_custody_audit_status"]


class TestPortfolioSummary:
    def test_shape(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_holds_total",
                   "n_holds_active", "n_acknowledgments_total",
                   "n_acknowledgments_overdue",
                   "hold_status_counts", "ack_status_counts",
                   "default_ack_deadline_days",
                   "automated_preservation_holds_status",
                   "escalation_notification_status",
                   "chain_of_custody_audit_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-227 LegalHoldManagementEngine"


class TestNoRegression:
    def test_audit(self):
        m = _load("audit_v175", AUDIT_PATH)
        for gid, gfn in m.GATES:
            assert gfn()["passed"] is True

    def test_v10_174_works(self):
        from utils.clause_library import ClauseLibraryEngine
        eng = ClauseLibraryEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-226 ClauseLibraryEngine")

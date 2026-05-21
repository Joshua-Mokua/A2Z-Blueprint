"""tests/test_outside_counsel_portal_v10_172.py — ENH-224"""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "outside_counsel_portal.py"
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
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        assert OutsideCounselPortalEngine() is not None

    def test_enums(self):
        from utils.outside_counsel_portal import (
            CounselStatus, AssignmentStatus, BillingStatus,
            TransitionOutcome)
        assert len(list(CounselStatus)) == 4
        assert len(list(AssignmentStatus)) == 5
        assert len(list(BillingStatus)) == 5
        assert len(list(TransitionOutcome)) == 5


class TestRegistry:
    def test_active(self):
        m = _load("registry_v172", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-224"), None)
        assert s.status == "active"
        assert "outside_counsel_portal" in s.affected_engines


class TestHubIntegration:
    def test_in_hub(self):
        admin = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"outside_counsel_portal"' in admin


class TestUTBMS:
    def test_codes_present(self):
        from utils.outside_counsel_portal import (
            UTBMS_CODES_LITIGATION)
        for code in ("L100", "L210", "L400", "A102", "A106"):
            assert code in UTBMS_CODES_LITIGATION


class TestCounselLifecycle:
    def _eng(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        return OutsideCounselPortalEngine()

    def test_onboard_pending(self):
        from utils.outside_counsel_portal import CounselStatus
        eng = self._eng()
        c = eng.onboard_counsel("Smith & Co", "John", "j@s.co.ke",
                                       "LSK-1")
        assert c.status == CounselStatus.PENDING_VERIFICATION

    def test_empty_bar_rejected(self):
        eng = self._eng()
        try:
            eng.onboard_counsel("X", "Y", "z@x.com", "")
            raise AssertionError("empty bar should raise")
        except ValueError:
            pass

    def test_pending_to_active(self):
        from utils.outside_counsel_portal import (
            CounselStatus, TransitionOutcome)
        eng = self._eng()
        c = eng.onboard_counsel("X", "Y", "z@x.com", "LSK-1")
        outcome, c = eng.transition_counsel(
            c.counsel_id, CounselStatus.ACTIVE, user="admin")
        assert outcome == TransitionOutcome.OK
        assert c.status == CounselStatus.ACTIVE

    def test_suspended_requires_reason(self):
        from utils.outside_counsel_portal import (
            CounselStatus, TransitionOutcome)
        eng = self._eng()
        c = eng.onboard_counsel("X", "Y", "z@x.com", "LSK-1")
        eng.transition_counsel(c.counsel_id, CounselStatus.ACTIVE,
                                  user="admin")
        outcome, _ = eng.transition_counsel(
            c.counsel_id, CounselStatus.SUSPENDED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED


class TestMatterAssignment:
    def _active_counsel(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine, CounselStatus)
        eng = OutsideCounselPortalEngine()
        c = eng.onboard_counsel("X", "Y", "z@x.com", "LSK-1")
        eng.transition_counsel(c.counsel_id, CounselStatus.ACTIVE,
                                  user="admin")
        return eng, c

    def test_assign_pending_rejected(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine, TransitionOutcome)
        eng = OutsideCounselPortalEngine()
        c = eng.onboard_counsel("X", "Y", "z@x.com", "LSK-1")
        outcome, _ = eng.assign_matter(
            c.counsel_id, "M1", "Title",
            "scope", "hourly", Decimal("100000"))
        assert outcome == TransitionOutcome.REJECTED_COUNSEL_NOT_ACTIVE

    def test_assign_active_works(self):
        from utils.outside_counsel_portal import TransitionOutcome
        eng, c = self._active_counsel()
        outcome, a = eng.assign_matter(
            c.counsel_id, "M1", "Title",
            "scope", "hourly", Decimal("500000"))
        assert outcome == TransitionOutcome.OK
        assert a.assignment_id.startswith("ASN-")

    def test_negative_amount_rejected(self):
        eng, c = self._active_counsel()
        try:
            eng.assign_matter(c.counsel_id, "M1", "T", "s", "h",
                                Decimal("-1"))
            raise AssertionError("negative amount should raise")
        except ValueError:
            pass


class TestBillingSubmission:
    def _ready(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine, CounselStatus)
        eng = OutsideCounselPortalEngine()
        c = eng.onboard_counsel("X", "Y", "z@x.com", "LSK-1")
        eng.transition_counsel(c.counsel_id, CounselStatus.ACTIVE,
                                  user="admin")
        outcome, a = eng.assign_matter(
            c.counsel_id, "M1", "Title", "scope", "hourly",
            Decimal("500000"))
        return eng, c, a

    def test_submit_with_valid_utbms(self):
        from utils.outside_counsel_portal import (
            BillingLine, TransitionOutcome)
        eng, c, a = self._ready()
        lines = [
            BillingLine("L120", "strategy",
                          Decimal("3"), Decimal("15000"), "KES"),
            BillingLine("L210", "drafting",
                          Decimal("5"), Decimal("15000"), "KES")]
        outcome, s = eng.submit_billing(c.counsel_id, a.assignment_id,
                                              "INV-1",
                                              "2026-04-01", "2026-04-30",
                                              lines)
        assert outcome == TransitionOutcome.OK
        assert s.total_amount == Decimal("120000")

    def test_submit_invalid_utbms_rejected(self):
        from utils.outside_counsel_portal import BillingLine
        eng, c, a = self._ready()
        bad = [BillingLine("X999", "x", Decimal("1"),
                              Decimal("100"), "KES")]
        try:
            eng.submit_billing(c.counsel_id, a.assignment_id, "INV",
                                  "2026-04-01", "2026-04-30", bad)
            raise AssertionError("invalid UTBMS should raise")
        except ValueError as e:
            assert "UTBMS" in str(e)

    def test_mixed_currency_rejected(self):
        from utils.outside_counsel_portal import BillingLine
        eng, c, a = self._ready()
        mixed = [
            BillingLine("L120", "x", Decimal("1"),
                          Decimal("100"), "KES"),
            BillingLine("L210", "y", Decimal("1"),
                          Decimal("100"), "USD")]
        try:
            eng.submit_billing(c.counsel_id, a.assignment_id, "INV",
                                  "2026-04-01", "2026-04-30", mixed)
            raise AssertionError("mixed currency should raise")
        except ValueError as e:
            assert "currency" in str(e)


class TestBillingLifecycle:
    def _submitted(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine, CounselStatus, BillingLine)
        eng = OutsideCounselPortalEngine()
        c = eng.onboard_counsel("X", "Y", "z@x.com", "LSK-1")
        eng.transition_counsel(c.counsel_id, CounselStatus.ACTIVE,
                                  user="admin")
        _, a = eng.assign_matter(c.counsel_id, "M1", "T", "s", "h",
                                       Decimal("500000"))
        lines = [BillingLine("L120", "x", Decimal("3"),
                                Decimal("15000"), "KES")]
        _, s = eng.submit_billing(c.counsel_id, a.assignment_id, "INV",
                                       "2026-04-01", "2026-04-30", lines)
        return eng, s

    def test_dispute_requires_notes(self):
        from utils.outside_counsel_portal import (
            BillingStatus, TransitionOutcome)
        eng, s = self._submitted()
        eng.transition_billing(s.submission_id,
                                  BillingStatus.UNDER_REVIEW, user="x")
        outcome, _ = eng.transition_billing(
            s.submission_id, BillingStatus.DISPUTED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_approve_path(self):
        from utils.outside_counsel_portal import (
            BillingStatus, TransitionOutcome)
        eng, s = self._submitted()
        eng.transition_billing(s.submission_id,
                                  BillingStatus.UNDER_REVIEW, user="x")
        outcome, s = eng.transition_billing(
            s.submission_id, BillingStatus.APPROVED, user="head")
        assert outcome == TransitionOutcome.OK
        assert s.status == BillingStatus.APPROVED

    def test_dispute_then_approve(self):
        from utils.outside_counsel_portal import (
            BillingStatus, TransitionOutcome)
        eng, s = self._submitted()
        eng.transition_billing(s.submission_id,
                                  BillingStatus.UNDER_REVIEW, user="x")
        eng.transition_billing(s.submission_id,
                                  BillingStatus.DISPUTED, user="x",
                                  review_notes="rate query")
        outcome, s = eng.transition_billing(
            s.submission_id, BillingStatus.APPROVED, user="x")
        assert outcome == TransitionOutcome.OK


class TestQueries:
    def test_active_counsel_filter(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine, CounselStatus)
        eng = OutsideCounselPortalEngine()
        c1 = eng.onboard_counsel("A", "X", "x@a.com", "L1")
        c2 = eng.onboard_counsel("B", "Y", "y@b.com", "L2")
        eng.transition_counsel(c1.counsel_id, CounselStatus.ACTIVE,
                                  user="x")
        assert len(eng.active_counsel()) == 1


class TestHonestDeferrals:
    def test_three_deferrals_present(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        eng = OutsideCounselPortalEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["portal_ui_status"]
        assert "DEFERRED" in s["authentication_status"]
        assert "DEFERRED" in s["ap_integration_status"]


class TestPortfolioSummary:
    def test_shape(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        eng = OutsideCounselPortalEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_counsel_total",
                   "n_counsel_active", "n_assignments_total",
                   "n_submissions_total",
                   "n_submissions_under_review",
                   "approved_billing_totals_by_currency",
                   "n_utbms_codes_supported",
                   "portal_ui_status", "authentication_status",
                   "ap_integration_status", "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-224 OutsideCounselPortalEngine"


class TestNoRegression:
    def test_audit(self):
        m = _load("audit_v172", AUDIT_PATH)
        for gid, gfn in m.GATES:
            assert gfn()["passed"] is True

    def test_v10_171_legal_case_works(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-223 LegalCaseManagementEngine")

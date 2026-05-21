"""tests/test_legal_spend_management_v10_173.py — ENH-225"""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "legal_spend_management.py"
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
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        assert LegalSpendManagementEngine() is not None

    def test_enums(self):
        from utils.legal_spend_management import (
            BudgetStatus, VarianceState, SpendOrigin,
            TransitionOutcome)
        assert len(list(BudgetStatus)) == 2
        assert len(list(VarianceState)) == 4
        assert len(list(SpendOrigin)) == 4
        assert len(list(TransitionOutcome)) == 5


class TestRegistry:
    def test_active(self):
        m = _load("registry_v173", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-225"), None)
        assert s.status == "active"
        assert "legal_spend_management" in s.affected_engines


class TestHubIntegration:
    def test_in_hub(self):
        admin = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"legal_spend_management"' in admin


class TestBudgetCreation:
    def _eng(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        return LegalSpendManagementEngine()

    def test_create_active(self):
        from utils.legal_spend_management import BudgetStatus
        eng = self._eng()
        b = eng.create_budget(matter_id="M1", name="N",
                                  amount=Decimal("100000"),
                                  currency="KES",
                                  period_start="2026-01-01",
                                  period_end="2026-12-31",
                                  owner_role="head_of_legal")
        assert b.status == BudgetStatus.ACTIVE
        assert b.budget_id.startswith("BGT-")

    def test_zero_amount_rejected(self):
        eng = self._eng()
        try:
            eng.create_budget("M1", "N", Decimal("0"), "KES",
                                "2026-01-01", "2026-12-31",
                                "head_of_legal")
            raise AssertionError("zero amount should raise")
        except ValueError:
            pass

    def test_invalid_date_rejected(self):
        eng = self._eng()
        try:
            eng.create_budget("M1", "N", Decimal("100"), "KES",
                                "January 1 2026", "2026-12-31",
                                "head_of_legal")
            raise AssertionError("invalid date should raise")
        except ValueError:
            pass


class TestSpendRecording:
    def _ready(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        b = eng.create_budget("M1", "N", Decimal("1000000"),
                                  "KES", "2026-01-01",
                                  "2026-12-31",
                                  "head_of_legal")
        return eng, b

    def test_record_spend_ok(self):
        from utils.legal_spend_management import (
            SpendOrigin, TransitionOutcome)
        eng, b = self._ready()
        outcome, s = eng.record_spend(
            "M1", SpendOrigin.EXTERNAL_BILLING, Decimal("100"),
            "KES", "x", "Smith", "BIL-1")
        assert outcome == TransitionOutcome.OK
        assert s.spend_id.startswith("SPN-")

    def test_currency_mismatch_rejected(self):
        from utils.legal_spend_management import (
            SpendOrigin, TransitionOutcome)
        eng, b = self._ready()
        outcome, s = eng.record_spend(
            "M1", SpendOrigin.EXTERNAL_BILLING, Decimal("100"),
            "USD", "x", "Smith", "BIL-1")
        assert outcome == TransitionOutcome.REJECTED_CURRENCY_MISMATCH
        assert s is None

    def test_negative_amount_rejected(self):
        from utils.legal_spend_management import SpendOrigin
        eng, b = self._ready()
        try:
            eng.record_spend("M1", SpendOrigin.EXTERNAL_BILLING,
                                Decimal("-1"), "KES", "x", "y")
            raise AssertionError("negative amount should raise")
        except ValueError:
            pass


class TestVarianceComputation:
    """Critical tests for variance threshold transitions."""

    def _scenario(self, spend_amount):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine, SpendOrigin)
        eng = LegalSpendManagementEngine()
        b = eng.create_budget("M1", "N", Decimal("1000000"),
                                  "KES", "2026-01-01",
                                  "2026-12-31", "head_of_legal")
        if spend_amount > 0:
            eng.record_spend("M1", SpendOrigin.EXTERNAL_BILLING,
                                Decimal(spend_amount), "KES", "x",
                                "Smith")
        return eng, b

    def test_zero_spend_on_track(self):
        eng, b = self._scenario(0)
        v = eng.variance_for_budget(b.budget_id)
        assert v["state"] == "ON_TRACK"

    def test_50_percent_on_track(self):
        eng, b = self._scenario(500000)
        v = eng.variance_for_budget(b.budget_id)
        assert v["state"] == "ON_TRACK"

    def test_85_percent_warning(self):
        eng, b = self._scenario(850000)
        v = eng.variance_for_budget(b.budget_id)
        assert v["state"] == "WARNING"

    def test_98_percent_at_limit(self):
        eng, b = self._scenario(980000)
        v = eng.variance_for_budget(b.budget_id)
        assert v["state"] == "AT_LIMIT"

    def test_105_percent_exceeded(self):
        eng, b = self._scenario(1050000)
        v = eng.variance_for_budget(b.budget_id)
        assert v["state"] == "EXCEEDED"

    def test_matters_at_or_over_limit(self):
        eng, b = self._scenario(1100000)
        out = eng.matters_at_or_over_limit()
        assert len(out) == 1
        assert out[0]["state"] == "EXCEEDED"


class TestBudgetClosure:
    def _ready(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        b = eng.create_budget("M1", "N", Decimal("100"),
                                  "KES", "2026-01-01",
                                  "2026-12-31", "head_of_legal")
        return eng, b

    def test_close_requires_reason(self):
        from utils.legal_spend_management import TransitionOutcome
        eng, b = self._ready()
        outcome, _ = eng.close_budget(b.budget_id, user="x",
                                            reason="")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_close_with_reason(self):
        from utils.legal_spend_management import (
            BudgetStatus, TransitionOutcome)
        eng, b = self._ready()
        outcome, b = eng.close_budget(b.budget_id, user="x",
                                            reason="matter resolved")
        assert outcome == TransitionOutcome.OK
        assert b.status == BudgetStatus.CLOSED

    def test_close_already_closed_rejected(self):
        from utils.legal_spend_management import (
            BudgetStatus, TransitionOutcome)
        eng, b = self._ready()
        eng.close_budget(b.budget_id, user="x", reason="x")
        outcome, _ = eng.close_budget(b.budget_id, user="x",
                                           reason="x")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION


class TestRateCards:
    def test_add(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        c = eng.add_rate_card("Smith & Co", "partner",
                                  Decimal("25000"), "KES",
                                  "2026-01-01")
        assert c.firm_name == "Smith & Co"
        assert c.hourly_rate == Decimal("25000")

    def test_negative_rate_rejected(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        try:
            eng.add_rate_card("X", "p", Decimal("-1"), "KES",
                                "2026-01-01")
            raise AssertionError("negative rate should raise")
        except ValueError:
            pass

    def test_filter_by_firm(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        eng.add_rate_card("A", "p", Decimal("100"), "KES",
                            "2026-01-01")
        eng.add_rate_card("A", "associate", Decimal("50"), "KES",
                            "2026-01-01")
        eng.add_rate_card("B", "p", Decimal("80"), "KES",
                            "2026-01-01")
        assert len(eng.rate_cards_for_firm("A")) == 2


class TestQueries:
    def test_spend_by_firm(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine, SpendOrigin)
        eng = LegalSpendManagementEngine()
        eng.create_budget("M1", "N", Decimal("1000000"),
                            "KES", "2026-01-01", "2026-12-31",
                            "head_of_legal")
        eng.record_spend("M1", SpendOrigin.EXTERNAL_BILLING,
                            Decimal("100"), "KES", "x", "Smith")
        eng.record_spend("M1", SpendOrigin.EXTERNAL_BILLING,
                            Decimal("200"), "KES", "y", "Jones")
        out = eng.spend_by_firm()
        assert "Smith" in out and "Jones" in out


class TestHonestDeferrals:
    def test_three_deferrals(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["real_time_ap_reconciliation_status"]
        assert "DEFERRED" in s["rate_negotiation_recommendations_status"]
        assert "META_ONLY" in s["internal_counsel_costing_status"]


class TestPortfolioSummary:
    def test_shape(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_budgets_total",
                   "n_budgets_active",
                   "n_budgets_at_or_over_limit",
                   "n_spend_records", "n_rate_cards",
                   "active_budgets_by_currency",
                   "total_spend_by_currency",
                   "real_time_ap_reconciliation_status",
                   "rate_negotiation_recommendations_status",
                   "internal_counsel_costing_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-225 LegalSpendManagementEngine"


class TestNoRegression:
    def test_audit(self):
        m = _load("audit_v173", AUDIT_PATH)
        for gid, gfn in m.GATES:
            assert gfn()["passed"] is True

    def test_v10_172_works(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        eng = OutsideCounselPortalEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-224 OutsideCounselPortalEngine")

"""tests/test_obligation_tracking_v10_170.py — ENH-222 Obligation &
Renewal Tracking. First Legal arc engine.
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "obligation_tracking.py"
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
        from utils.obligation_tracking import ObligationTrackingEngine
        assert ObligationTrackingEngine() is not None

    def test_enum_cardinalities(self):
        from utils.obligation_tracking import (
            ObligationStatus, ObligationKind, AlertLevel,
            TransitionOutcome)
        assert len(list(ObligationStatus)) == 4
        assert len(list(ObligationKind)) == 6
        assert len(list(AlertLevel)) == 6
        assert len(list(TransitionOutcome)) == 4

    def test_dataclass_frozen(self):
        from utils.obligation_tracking import (
            Obligation, ObligationKind, ObligationStatus)
        o = Obligation(
            obligation_id="x", contract_id="x", counterparty="x",
            title="x", description="x", kind=ObligationKind.OTHER,
            deadline_date="2026-01-01", notice_period_days=0,
            owner_role="x", escalation_role="",
            status=ObligationStatus.ACTIVE,
            registered_at_utc="x")
        try:
            o.title = "MUTATED"
            raise AssertionError("frozen mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_active(self):
        m = _load("registry_v170", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-222"), None)
        assert s is not None
        assert s.status == "active"
        assert "obligation_tracking" in (s.affected_engines or ())


class TestEngineHubIntegration:
    def test_in_hub(self):
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"obligation_tracking"' in admin_text

    def test_tier_31_legal_present(self):
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        assert "Tier 31" in admin_text
        assert "Legal Suite" in admin_text


class TestRegister:
    def _eng(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        return ObligationTrackingEngine()

    def test_register_active(self):
        from utils.obligation_tracking import (
            ObligationKind, ObligationStatus)
        eng = self._eng()
        o = eng.register_obligation(
            contract_id="C1", counterparty="X", title="t",
            description="d", kind=ObligationKind.PAYMENT_DUE,
            deadline_date="2026-12-31", owner_role="finance")
        assert o.status == ObligationStatus.ACTIVE
        assert o.obligation_id.startswith("OBL-")

    def test_empty_owner_rejected(self):
        from utils.obligation_tracking import ObligationKind
        eng = self._eng()
        try:
            eng.register_obligation(
                contract_id="C1", counterparty="X", title="t",
                description="d", kind=ObligationKind.PAYMENT_DUE,
                deadline_date="2026-12-31", owner_role="")
            raise AssertionError("empty owner should raise")
        except ValueError as e:
            assert "owner" in str(e).lower()

    def test_invalid_date_format_rejected(self):
        from utils.obligation_tracking import ObligationKind
        eng = self._eng()
        try:
            eng.register_obligation(
                contract_id="C1", counterparty="X", title="t",
                description="d", kind=ObligationKind.PAYMENT_DUE,
                deadline_date="December 31 2026",
                owner_role="finance")
            raise AssertionError("invalid date should raise")
        except ValueError as e:
            assert "YYYY-MM-DD" in str(e)


class TestAlertLevels:
    """T-90/60/30/7 alert threshold computation."""

    def _make(self, days_offset):
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationKind)
        eng = ObligationTrackingEngine()
        deadline = (datetime.now(timezone.utc) +
                      timedelta(days=days_offset)).strftime("%Y-%m-%d")
        o = eng.register_obligation(
            contract_id="C1", counterparty="X", title="t",
            description="d", kind=ObligationKind.PAYMENT_DUE,
            deadline_date=deadline, owner_role="finance")
        return eng, o

    def test_t_90_returns_notice(self):
        from utils.obligation_tracking import AlertLevel
        eng, o = self._make(85)
        assert eng.alert_level(o) == AlertLevel.NOTICE

    def test_t_60_returns_planning(self):
        from utils.obligation_tracking import AlertLevel
        eng, o = self._make(55)
        assert eng.alert_level(o) == AlertLevel.PLANNING

    def test_t_30_returns_action(self):
        from utils.obligation_tracking import AlertLevel
        eng, o = self._make(25)
        assert eng.alert_level(o) == AlertLevel.ACTION

    def test_t_7_returns_critical(self):
        from utils.obligation_tracking import AlertLevel
        eng, o = self._make(5)
        assert eng.alert_level(o) == AlertLevel.CRITICAL

    def test_past_deadline_returns_breached(self):
        from utils.obligation_tracking import AlertLevel
        eng, o = self._make(-3)
        assert eng.alert_level(o) == AlertLevel.BREACHED

    def test_far_future_returns_none(self):
        from utils.obligation_tracking import AlertLevel
        eng, o = self._make(180)
        assert eng.alert_level(o) == AlertLevel.NONE

    def test_completed_obligation_returns_none(self):
        from utils.obligation_tracking import (
            AlertLevel, ObligationStatus)
        eng, o = self._make(5)
        eng.transition(o.obligation_id, ObligationStatus.COMPLETED,
                          user="x",
                          discharge_evidence="paid")
        # alert_level uses fresh state from engine
        o = eng.obligation_by_id(o.obligation_id)
        assert eng.alert_level(o) == AlertLevel.NONE


class TestTransitions:
    def _active(self):
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationKind)
        eng = ObligationTrackingEngine()
        o = eng.register_obligation(
            contract_id="C1", counterparty="X", title="t",
            description="d", kind=ObligationKind.PAYMENT_DUE,
            deadline_date="2026-12-31", owner_role="finance")
        return eng, o

    def test_completed_requires_evidence(self):
        from utils.obligation_tracking import (
            ObligationStatus, TransitionOutcome)
        eng, o = self._active()
        outcome, _ = eng.transition(
            o.obligation_id, ObligationStatus.COMPLETED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_cancelled_requires_reason(self):
        from utils.obligation_tracking import (
            ObligationStatus, TransitionOutcome)
        eng, o = self._active()
        outcome, _ = eng.transition(
            o.obligation_id, ObligationStatus.CANCELLED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_completed_with_evidence(self):
        from utils.obligation_tracking import (
            ObligationStatus, TransitionOutcome)
        eng, o = self._active()
        outcome, o = eng.transition(
            o.obligation_id, ObligationStatus.COMPLETED,
            user="x", discharge_evidence="paid 2026-12-31 ref TXN")
        assert outcome == TransitionOutcome.OK
        assert o.status == ObligationStatus.COMPLETED
        assert "TXN" in o.discharge_evidence

    def test_unknown_id_rejected(self):
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationStatus,
            TransitionOutcome)
        eng = ObligationTrackingEngine()
        outcome, _ = eng.transition("UNKNOWN",
                                          ObligationStatus.COMPLETED,
                                          user="x")
        assert outcome == TransitionOutcome.REJECTED_NOT_FOUND


class TestQueries:
    def test_obligations_for_contract(self):
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationKind)
        eng = ObligationTrackingEngine()
        eng.register_obligation(
            contract_id="C1", counterparty="X", title="t1",
            description="d", kind=ObligationKind.PAYMENT_DUE,
            deadline_date="2026-12-31", owner_role="x")
        eng.register_obligation(
            contract_id="C1", counterparty="X", title="t2",
            description="d", kind=ObligationKind.DELIVERABLE,
            deadline_date="2026-11-30", owner_role="x")
        eng.register_obligation(
            contract_id="C2", counterparty="Y", title="t3",
            description="d", kind=ObligationKind.PAYMENT_DUE,
            deadline_date="2026-10-31", owner_role="x")
        assert len(eng.obligations_for_contract("C1")) == 2
        assert len(eng.obligations_for_contract("C2")) == 1


class TestHonestDeferrals:
    def test_automated_alerting_deferred(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        eng = ObligationTrackingEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["automated_alerting_status"]

    def test_contract_text_meta_only(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        eng = ObligationTrackingEngine()
        s = eng.board_summary()
        assert "META_ONLY" in s["contract_text_integration_status"]


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        eng = ObligationTrackingEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_obligations_total", "n_active",
                   "n_breached", "n_completed", "alert_counts",
                   "kind_counts", "automated_alerting_status",
                   "contract_text_integration_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-222 ObligationTrackingEngine"


class TestNoRegression:
    def test_audit_passes(self):
        m = _load("audit_v170", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True

    def test_gate_count(self):
        m = _load("audit_count_v170", AUDIT_PATH)
        assert len(m.GATES) == 153

    def test_aml_compliance_still_closed(self):
        m = _load("audit_aml_check", AUDIT_PATH)
        for gid in ("G150", "G151", "G152", "G153"):
            gate = next(g for g in m.GATES if g[0] == gid)
            r = gate[1]()
            assert r["passed"] is True

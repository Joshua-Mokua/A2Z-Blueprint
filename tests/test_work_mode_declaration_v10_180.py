"""tests/test_work_mode_declaration_v10_180.py — v10.180 ENH-156
WorkModeDeclarationEngine tests.

Covers:
- Module shape (enums, dataclasses, engine class exposed)
- Registry activation (status='active', affected_engines populated)
- Tier 32 hub registration in pages/7_admin.py
- Declaration creation with date validation
- Forward-only state machine
- Owner-checked REVOKED transition
- Auto-supersede on overlapping ACTIVE
- Privacy gating on list_for_employee
- Privacy threshold suppression in aggregate
- Honest deferrals visible in board_summary
- No regression of v10.179 closure work
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_module_imports(self):
        from utils import work_mode_declaration as wmd
        assert hasattr(wmd, "WorkModeDeclarationEngine")
        assert hasattr(wmd, "WorkMode")
        assert hasattr(wmd, "DeclarationStatus")
        assert hasattr(wmd, "TransitionOutcome")
        assert hasattr(wmd, "WorkModeDeclaration")
        assert hasattr(wmd, "ALLOWED_TRANSITIONS")
        assert hasattr(wmd, "PRIVACY_MIN_CELL_SIZE")

    def test_work_mode_enum_values(self):
        from utils.work_mode_declaration import WorkMode
        modes = {m.value for m in WorkMode}
        assert modes == {"remote", "hybrid", "onsite", "field"}

    def test_status_enum_has_7_states(self):
        from utils.work_mode_declaration import DeclarationStatus
        assert len(list(DeclarationStatus)) == 7

    def test_terminal_states_have_no_transitions(self):
        from utils.work_mode_declaration import (
            DeclarationStatus, ALLOWED_TRANSITIONS)
        for terminal in (DeclarationStatus.EXPIRED,
                          DeclarationStatus.REVOKED,
                          DeclarationStatus.SUPERSEDED):
            assert ALLOWED_TRANSITIONS[terminal] == frozenset()


class TestRegistry:
    def test_enh_156_active(self):
        m = _load("reg_v180", REPO_ROOT / "utils" / "standards_registry.py")
        s = next(
            (x for x in m.STANDARDS_REGISTRY
             if x.standard_id == "ENH-156"), None)
        assert s is not None
        assert s.status == "active"
        assert s.affected_engines == ("work_mode_declaration",)
        assert s.implementation_batch == "v10.180"


class TestHubIntegration:
    def test_tier_32_present(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "Tier 32 — Resource Optimization Suite" in text
        assert "work_mode_declaration" in text
        assert "WorkModeDeclarationEngine" in text


class TestDeclareCreation:
    def test_declare_creates_in_draft(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode, DeclarationStatus)
        eng = WorkModeDeclarationEngine()
        d = eng.declare(
            "EMP-1", "MGR-1", WorkMode.HYBRID,
            date.today(), date.today() + timedelta(days=30))
        assert d.status == DeclarationStatus.DRAFT
        assert d.declaration_id.startswith("WMD-")

    def test_declare_rejects_inverted_dates(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode)
        eng = WorkModeDeclarationEngine()
        try:
            eng.declare(
                "EMP-1", "MGR-1", WorkMode.HYBRID,
                date.today() + timedelta(days=10),
                date.today())
        except ValueError:
            return
        raise AssertionError("expected ValueError on inverted dates")

    def test_declare_rejects_empty_employee(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode)
        eng = WorkModeDeclarationEngine()
        try:
            eng.declare(
                "", "MGR-1", WorkMode.HYBRID,
                date.today(), date.today() + timedelta(days=10))
        except ValueError:
            return
        raise AssertionError("expected ValueError on empty employee_id")


class TestStateMachine:
    def test_full_happy_path(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, TransitionOutcome)
        eng = WorkModeDeclarationEngine()
        d = eng.declare("E", "M", WorkMode.REMOTE,
                        date.today(), date.today() + timedelta(days=30))
        for to_state in (DeclarationStatus.SUBMITTED,
                          DeclarationStatus.ACKNOWLEDGED,
                          DeclarationStatus.ACTIVE,
                          DeclarationStatus.EXPIRED):
            d, o = eng.transition(d.declaration_id, to_state,
                                   "SYSTEM", "SYSTEM")
            assert o == TransitionOutcome.OK, (
                f"failed at {to_state.value}: {o.value}")
        assert d.status == DeclarationStatus.EXPIRED

    def test_rejects_backward_transition(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, TransitionOutcome)
        eng = WorkModeDeclarationEngine()
        d = eng.declare("E", "M", WorkMode.HYBRID,
                        date.today(), date.today() + timedelta(days=10))
        d, _ = eng.transition(d.declaration_id, DeclarationStatus.SUBMITTED,
                              "EMPLOYEE", "E")
        d, _ = eng.transition(d.declaration_id, DeclarationStatus.ACTIVE,
                              "SYSTEM", "SYSTEM")
        # cannot go back to SUBMITTED
        _, o = eng.transition(d.declaration_id, DeclarationStatus.SUBMITTED,
                              "MANAGER", "M")
        assert o == TransitionOutcome.REJECTED_INVALID_STATE

    def test_terminal_states_are_terminal(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, TransitionOutcome)
        eng = WorkModeDeclarationEngine()
        d = eng.declare("E", "M", WorkMode.HYBRID,
                        date.today(), date.today() + timedelta(days=5))
        # Get to REVOKED terminal
        d, _ = eng.transition(d.declaration_id, DeclarationStatus.REVOKED,
                              "EMPLOYEE", "E", reason="changed mind")
        # Now any transition fails
        _, o = eng.transition(d.declaration_id, DeclarationStatus.ACTIVE,
                              "SYSTEM", "SYSTEM")
        assert o == TransitionOutcome.REJECTED_INVALID_STATE


class TestRevokeOwnership:
    def test_revoke_requires_reason(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, TransitionOutcome)
        eng = WorkModeDeclarationEngine()
        d = eng.declare("E", "M", WorkMode.HYBRID,
                        date.today(), date.today() + timedelta(days=5))
        d, _ = eng.transition(d.declaration_id, DeclarationStatus.SUBMITTED,
                              "EMPLOYEE", "E")
        _, o = eng.transition(d.declaration_id, DeclarationStatus.REVOKED,
                              "EMPLOYEE", "E")
        assert o == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_revoke_blocked_for_other_employee(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, TransitionOutcome)
        eng = WorkModeDeclarationEngine()
        d = eng.declare("E1", "M", WorkMode.HYBRID,
                        date.today(), date.today() + timedelta(days=5))
        d, _ = eng.transition(d.declaration_id, DeclarationStatus.SUBMITTED,
                              "EMPLOYEE", "E1")
        _, o = eng.transition(d.declaration_id, DeclarationStatus.REVOKED,
                              "EMPLOYEE", "E2", reason="x")
        assert o == TransitionOutcome.REJECTED_NOT_OWNER

    def test_hr_admin_can_revoke(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, TransitionOutcome)
        eng = WorkModeDeclarationEngine()
        d = eng.declare("E1", "M", WorkMode.HYBRID,
                        date.today(), date.today() + timedelta(days=5))
        d, _ = eng.transition(d.declaration_id, DeclarationStatus.SUBMITTED,
                              "EMPLOYEE", "E1")
        d, o = eng.transition(d.declaration_id, DeclarationStatus.REVOKED,
                              "HR_ADMIN", "HR-007", reason="termination")
        assert o == TransitionOutcome.OK
        assert d.status == DeclarationStatus.REVOKED


class TestAutoSupersede:
    def test_overlapping_active_supersedes_prior(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus)
        eng = WorkModeDeclarationEngine()
        d1 = eng.declare("E", "M", WorkMode.HYBRID,
                          date.today(), date.today() + timedelta(days=60))
        d1, _ = eng.transition(d1.declaration_id,
                                DeclarationStatus.SUBMITTED,
                                "EMPLOYEE", "E")
        d1, _ = eng.transition(d1.declaration_id,
                                DeclarationStatus.ACTIVE,
                                "SYSTEM", "SYSTEM")
        # Second overlapping declaration becomes ACTIVE
        d2 = eng.declare("E", "M", WorkMode.REMOTE,
                          date.today() + timedelta(days=10),
                          date.today() + timedelta(days=90))
        d2, _ = eng.transition(d2.declaration_id,
                                DeclarationStatus.SUBMITTED,
                                "EMPLOYEE", "E")
        d2, _ = eng.transition(d2.declaration_id,
                                DeclarationStatus.ACTIVE,
                                "SYSTEM", "SYSTEM")
        # d1 should now be SUPERSEDED
        prior = eng.get(d1.declaration_id)
        assert prior.status == DeclarationStatus.SUPERSEDED

    def test_non_overlapping_is_not_superseded(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus)
        eng = WorkModeDeclarationEngine()
        d1 = eng.declare("E", "M", WorkMode.HYBRID,
                          date.today(), date.today() + timedelta(days=10))
        d1, _ = eng.transition(d1.declaration_id,
                                DeclarationStatus.SUBMITTED,
                                "EMPLOYEE", "E")
        d1, _ = eng.transition(d1.declaration_id,
                                DeclarationStatus.ACTIVE,
                                "SYSTEM", "SYSTEM")
        d2 = eng.declare("E", "M", WorkMode.REMOTE,
                          date.today() + timedelta(days=20),
                          date.today() + timedelta(days=50))
        d2, _ = eng.transition(d2.declaration_id,
                                DeclarationStatus.SUBMITTED,
                                "EMPLOYEE", "E")
        d2, _ = eng.transition(d2.declaration_id,
                                DeclarationStatus.ACTIVE,
                                "SYSTEM", "SYSTEM")
        # d1 remains ACTIVE (no overlap)
        prior = eng.get(d1.declaration_id)
        assert prior.status == DeclarationStatus.ACTIVE


class TestPrivacy:
    def test_list_unrelated_employee_returns_empty(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode)
        eng = WorkModeDeclarationEngine()
        eng.declare("E1", "M1", WorkMode.HYBRID,
                    date.today(), date.today() + timedelta(days=10))
        results = eng.list_for_employee("E1", "EMPLOYEE", "E2")
        assert results == []

    def test_list_self_works(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode)
        eng = WorkModeDeclarationEngine()
        eng.declare("E1", "M1", WorkMode.HYBRID,
                    date.today(), date.today() + timedelta(days=10))
        results = eng.list_for_employee("E1", "EMPLOYEE", "E1")
        assert len(results) == 1

    def test_list_manager_works(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode)
        eng = WorkModeDeclarationEngine()
        eng.declare("E1", "M1", WorkMode.HYBRID,
                    date.today(), date.today() + timedelta(days=10))
        results = eng.list_for_employee("E1", "MANAGER", "M1")
        assert len(results) == 1

    def test_list_other_manager_blocked(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode)
        eng = WorkModeDeclarationEngine()
        eng.declare("E1", "M1", WorkMode.HYBRID,
                    date.today(), date.today() + timedelta(days=10))
        results = eng.list_for_employee("E1", "MANAGER", "M2")
        assert results == []

    def test_aggregate_suppresses_small_cells(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus, PRIVACY_MIN_CELL_SIZE)
        eng = WorkModeDeclarationEngine()
        # Only 2 active in DEPT_X — below threshold (5)
        for i in range(2):
            d = eng.declare(
                f"E{i}", "M", WorkMode.HYBRID,
                date.today(), date.today() + timedelta(days=30),
                department="DEPT_X")
            d, _ = eng.transition(d.declaration_id,
                                   DeclarationStatus.SUBMITTED,
                                   "EMPLOYEE", f"E{i}")
            d, _ = eng.transition(d.declaration_id,
                                   DeclarationStatus.ACTIVE,
                                   "SYSTEM", "SYSTEM")
        agg = eng.mode_distribution_by_department(
            date.today(), date.today() + timedelta(days=30))
        assert "DEPT_X" in agg["departments_suppressed_n_lt_threshold"]
        assert "DEPT_X" not in agg["departments_published"]
        assert agg["privacy_threshold"] == PRIVACY_MIN_CELL_SIZE

    def test_aggregate_publishes_above_threshold(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine, WorkMode,
            DeclarationStatus)
        eng = WorkModeDeclarationEngine()
        # 6 active in DEPT_Y — above threshold
        for i in range(6):
            d = eng.declare(
                f"E{i}", "M", WorkMode.HYBRID,
                date.today(), date.today() + timedelta(days=30),
                department="DEPT_Y")
            d, _ = eng.transition(d.declaration_id,
                                   DeclarationStatus.SUBMITTED,
                                   "EMPLOYEE", f"E{i}")
            d, _ = eng.transition(d.declaration_id,
                                   DeclarationStatus.ACTIVE,
                                   "SYSTEM", "SYSTEM")
        agg = eng.mode_distribution_by_department(
            date.today(), date.today() + timedelta(days=30))
        assert "DEPT_Y" in agg["departments_published"]
        assert agg["departments_published"]["DEPT_Y"]["hybrid"] == 6


class TestHonestDeferrals:
    def test_board_summary_names_deferrals(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine)
        eng = WorkModeDeclarationEngine()
        b = eng.board_summary()
        defs = b.get("deferrals", {})
        assert "HRIS_INTEGRATION" in defs
        assert "AUTO_SCHEDULE_SYNC" in defs
        assert "ML_PATTERN_DETECTION" in defs
        for v in defs.values():
            assert "DEFERRED" in v

    def test_board_summary_has_regulatory_basis(self):
        from utils.work_mode_declaration import (
            WorkModeDeclarationEngine)
        eng = WorkModeDeclarationEngine()
        b = eng.board_summary()
        assert "regulatory_basis" in b
        assert "Employment Act" in b["regulatory_basis"]


class TestNoRegression:
    def test_legal_closure_unchanged(self):
        m = _load("audit_post_v180",
                    REPO_ROOT / "scripts" / "audit.py")
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True, (
                f"{gid} regressed after v10.180: "
                f"{r.get('violations')}")

    def test_audit_count_still_155(self):
        m = _load("audit_count_post_v180",
                    REPO_ROOT / "scripts" / "audit.py")
        # v10.180 ships an engine, not a closure — count unchanged
        assert len(m.GATES) == 155

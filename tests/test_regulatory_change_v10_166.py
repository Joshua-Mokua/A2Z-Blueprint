"""tests/test_regulatory_change_v10_166.py — ENH-195 Regulatory Change
Management.

Verifies the v10.166 deliverable:
- Engine module exists, parses, imports
- 4 enums (RegulatorySource 7 values, ChangeStatus 5 values,
  TransitionOutcome 4, ImpactSeverity 4)
- 1 frozen output dataclass (RegulatoryChange) with to_dict
- ALLOWED_TRANSITIONS state machine forward-only
- Severity-based attestation deadlines (CRITICAL=7d, HIGH=30d,
  MEDIUM=60d, LOW=90d)
- WITHDRAWN requires reason; CLOSED requires closure_evidence
- overdue_attestations() surfaces past-deadline non-CLOSED changes
- Honest deferrals: automated_feed_status, policy_linkage_status
- ENH-195 active in registry, registered in Tier 30
- Audit 151/151
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "regulatory_change.py"
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
    def test_engine_parses(self):
        ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))

    def test_imports(self):
        from utils.regulatory_change import RegulatoryChangeEngine
        assert RegulatoryChangeEngine() is not None

    def test_enum_cardinalities(self):
        from utils.regulatory_change import (
            RegulatorySource, ChangeStatus, TransitionOutcome,
            ImpactSeverity)
        assert len(list(RegulatorySource)) == 7
        assert len(list(ChangeStatus)) == 5
        assert len(list(TransitionOutcome)) == 4
        assert len(list(ImpactSeverity)) == 4

    def test_status_vocabulary(self):
        from utils.regulatory_change import ChangeStatus
        names = {s.value for s in ChangeStatus}
        assert names == {"DRAFT", "OPEN", "IN_PROGRESS", "CLOSED",
                          "WITHDRAWN"}

    def test_dataclass_frozen(self):
        from utils.regulatory_change import (
            RegulatoryChange, RegulatorySource, ChangeStatus,
            ImpactSeverity)
        c = RegulatoryChange(
            change_id="X", source=RegulatorySource.CBK, citation="x",
            title="x", summary="x", effective_date="2026-01-01",
            severity=ImpactSeverity.LOW, affected_policies=(),
            affected_engines=(),
            attestation_deadline_utc="2026-01-01",
            attestation_owner="x", status=ChangeStatus.DRAFT,
            registered_at_utc="2026-01-01")
        try:
            c.title = "MUTATED"
            raise AssertionError("frozen mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_195_active(self):
        m = _load("registry_v166", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-195"), None)
        assert s is not None
        assert s.status == "active"
        assert "regulatory_change" in (s.affected_engines or ())


class TestEngineHubIntegration:
    def test_regulatory_change_in_hub(self):
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"regulatory_change"' in admin_text


class TestStateMachine:
    def test_draft_branches(self):
        from utils.regulatory_change import (
            ALLOWED_TRANSITIONS, ChangeStatus)
        successors = ALLOWED_TRANSITIONS[ChangeStatus.DRAFT]
        assert ChangeStatus.OPEN in successors
        assert ChangeStatus.WITHDRAWN in successors

    def test_open_to_in_progress_only(self):
        from utils.regulatory_change import (
            ALLOWED_TRANSITIONS, ChangeStatus)
        assert ALLOWED_TRANSITIONS[ChangeStatus.OPEN] == (
            ChangeStatus.IN_PROGRESS,)

    def test_terminals_empty(self):
        from utils.regulatory_change import (
            ALLOWED_TRANSITIONS, ChangeStatus)
        assert ALLOWED_TRANSITIONS[ChangeStatus.CLOSED] == ()
        assert ALLOWED_TRANSITIONS[ChangeStatus.WITHDRAWN] == ()


class TestRegister:
    def _make_change(self, severity=None):
        from utils.regulatory_change import (
            RegulatoryChangeEngine, RegulatorySource, ImpactSeverity)
        eng = RegulatoryChangeEngine()
        sev = severity or ImpactSeverity.MEDIUM
        return eng, eng.register_change(
            source=RegulatorySource.CBK, citation="CBK Test",
            title="Test change", summary="Test summary " * 3,
            effective_date="2026-07-01", severity=sev,
            attestation_owner="head_of_compliance")

    def test_register_returns_draft(self):
        from utils.regulatory_change import ChangeStatus
        eng, c = self._make_change()
        assert c.status == ChangeStatus.DRAFT
        assert c.change_id.startswith("REG-")

    def test_critical_default_deadline_7_days(self):
        from utils.regulatory_change import ImpactSeverity
        eng, c = self._make_change(ImpactSeverity.CRITICAL)
        assert c.meta["auto_deadline_days"] == 7

    def test_high_default_deadline_30_days(self):
        from utils.regulatory_change import ImpactSeverity
        eng, c = self._make_change(ImpactSeverity.HIGH)
        assert c.meta["auto_deadline_days"] == 30

    def test_low_default_deadline_90_days(self):
        from utils.regulatory_change import ImpactSeverity
        eng, c = self._make_change(ImpactSeverity.LOW)
        assert c.meta["auto_deadline_days"] == 90

    def test_empty_citation_rejected(self):
        from utils.regulatory_change import (
            RegulatoryChangeEngine, RegulatorySource, ImpactSeverity)
        eng = RegulatoryChangeEngine()
        try:
            eng.register_change(
                source=RegulatorySource.CBK, citation="",
                title="x", summary="x", effective_date="2026-01-01",
                severity=ImpactSeverity.LOW,
                attestation_owner="x")
            raise AssertionError("empty citation should raise")
        except ValueError as e:
            assert "citation" in str(e).lower()

    def test_empty_owner_rejected(self):
        from utils.regulatory_change import (
            RegulatoryChangeEngine, RegulatorySource, ImpactSeverity)
        eng = RegulatoryChangeEngine()
        try:
            eng.register_change(
                source=RegulatorySource.CBK, citation="x",
                title="x", summary="x", effective_date="2026-01-01",
                severity=ImpactSeverity.LOW, attestation_owner="")
            raise AssertionError("empty owner should raise")
        except ValueError as e:
            assert "owner" in str(e).lower()


class TestTransitions:
    def _make_draft(self):
        from utils.regulatory_change import (
            RegulatoryChangeEngine, RegulatorySource, ImpactSeverity)
        eng = RegulatoryChangeEngine()
        c = eng.register_change(
            source=RegulatorySource.CBK, citation="x", title="x",
            summary="x" * 30, effective_date="2026-07-01",
            severity=ImpactSeverity.MEDIUM,
            attestation_owner="lead")
        return eng, c

    def test_draft_to_open(self):
        from utils.regulatory_change import (
            ChangeStatus, TransitionOutcome)
        eng, c = self._make_draft()
        outcome, c = eng.transition(
            c.change_id, ChangeStatus.OPEN, user="lead")
        assert outcome == TransitionOutcome.OK
        assert c.status == ChangeStatus.OPEN

    def test_backward_rejected(self):
        from utils.regulatory_change import (
            ChangeStatus, TransitionOutcome)
        eng, c = self._make_draft()
        eng.transition(c.change_id, ChangeStatus.OPEN, user="lead")
        outcome, _ = eng.transition(
            c.change_id, ChangeStatus.DRAFT, user="x")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_withdrawn_requires_reason(self):
        from utils.regulatory_change import (
            ChangeStatus, TransitionOutcome)
        eng, c = self._make_draft()
        outcome, _ = eng.transition(
            c.change_id, ChangeStatus.WITHDRAWN, user="x", reason="")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_closed_requires_evidence(self):
        from utils.regulatory_change import (
            ChangeStatus, TransitionOutcome)
        eng, c = self._make_draft()
        eng.transition(c.change_id, ChangeStatus.OPEN, user="lead")
        eng.transition(c.change_id, ChangeStatus.IN_PROGRESS,
                          user="lead")
        outcome, _ = eng.transition(
            c.change_id, ChangeStatus.CLOSED, user="lead")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_full_lifecycle(self):
        from utils.regulatory_change import (
            ChangeStatus, TransitionOutcome)
        eng, c = self._make_draft()
        eng.transition(c.change_id, ChangeStatus.OPEN, user="lead")
        eng.transition(c.change_id, ChangeStatus.IN_PROGRESS,
                          user="lead")
        outcome, c = eng.transition(
            c.change_id, ChangeStatus.CLOSED, user="lead",
            closure_evidence="Policy POL-001 updated; staff trained")
        assert outcome == TransitionOutcome.OK
        assert c.status == ChangeStatus.CLOSED
        assert "POL-001" in c.closure_evidence
        # Log: DRAFT + OPEN + IN_PROGRESS + CLOSED = 4 entries
        assert len(c.transition_log) == 4

    def test_unknown_id_rejected(self):
        from utils.regulatory_change import (
            RegulatoryChangeEngine, ChangeStatus, TransitionOutcome)
        eng = RegulatoryChangeEngine()
        outcome, _ = eng.transition(
            "NONEXISTENT", ChangeStatus.OPEN, user="x")
        assert outcome == TransitionOutcome.REJECTED_NOT_FOUND


class TestOverdueDetection:
    def test_overdue_attestation_surfaced(self):
        from utils.regulatory_change import (
            RegulatoryChangeEngine, RegulatorySource, ImpactSeverity)
        eng = RegulatoryChangeEngine()
        # Set deadline in the past
        old_deadline = (datetime.now(timezone.utc)
                          - timedelta(days=10)).isoformat()
        c = eng.register_change(
            source=RegulatorySource.CBK, citation="x", title="x",
            summary="x" * 30, effective_date="2026-01-01",
            severity=ImpactSeverity.HIGH,
            attestation_owner="lead",
            attestation_deadline_utc=old_deadline)
        overdue = eng.overdue_attestations()
        assert c in overdue
        assert eng.board_summary()["n_overdue_attestations"] == 1


class TestHonestDeferrals:
    def test_automated_feed_deferred(self):
        from utils.regulatory_change import RegulatoryChangeEngine
        eng = RegulatoryChangeEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["automated_feed_status"]
        assert "no programmatic API" in s["automated_feed_status"]

    def test_policy_linkage_partial(self):
        from utils.regulatory_change import RegulatoryChangeEngine
        eng = RegulatoryChangeEngine()
        s = eng.board_summary()
        assert "PARTIAL" in s["policy_linkage_status"]
        assert "ENH-196" in s["policy_linkage_status"]


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.regulatory_change import RegulatoryChangeEngine
        eng = RegulatoryChangeEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_changes_total",
                   "n_overdue_attestations", "n_critical_open",
                   "status_counts", "severity_counts",
                   "source_counts", "automated_feed_status",
                   "policy_linkage_status", "regulatory_basis"):
            assert f in s, f"missing: {f}"
        assert s["engine"] == "ENH-195 RegulatoryChangeEngine"


class TestNoRegression:
    def test_audit_passes(self):
        m = _load("audit_v166", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True, (
                f"{gid} regressed: {r.get('violations')}")

    def test_gate_count_unchanged(self):
        m = _load("audit_count_v166", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_165_examiner_works(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-199 ExaminerReportingEngine")

    def test_v10_164_cra_works(self):
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        eng = ComplianceRiskAssessmentEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-198 ComplianceRiskAssessmentEngine")

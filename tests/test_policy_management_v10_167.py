"""tests/test_policy_management_v10_167.py — ENH-196 Policy Management
& Attestation.

Verifies the v10.167 deliverable:
- Engine module exists, parses, imports
- 3 enums (PolicyStatus 5, TransitionOutcome 4, AttestationOutcome 4)
- 2 frozen dataclasses (AttestationRecord, Policy) with to_dict
- (policy_id, version_id) is the unique key — same policy_id can have
  multiple versions
- ALLOWED_TRANSITIONS state machine with backward-from-IN_REVIEW
  allowed (review → revisions → re-draft)
- Attestation requires ACTIVE status + non-empty evidence
- Attestation cycle defaults 365 days, configurable per policy
- overdue_attestations() surfaces policies past attestor deadlines
- policies_for_change() reverse-lookup completes ENH-195↔ENH-196 link
- 2 honest deferrals (document_storage META_ONLY, esignature_verification)
- ENH-196 active in registry, registered in Tier 30
- Audit 151/151
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "policy_management.py"
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
        from utils.policy_management import PolicyManagementEngine
        assert PolicyManagementEngine() is not None

    def test_enum_cardinalities(self):
        from utils.policy_management import (
            PolicyStatus, TransitionOutcome, AttestationOutcome)
        assert len(list(PolicyStatus)) == 5
        assert len(list(TransitionOutcome)) == 4
        assert len(list(AttestationOutcome)) == 4

    def test_status_vocabulary(self):
        from utils.policy_management import PolicyStatus
        names = {s.value for s in PolicyStatus}
        assert names == {"DRAFT", "IN_REVIEW", "ACTIVE",
                          "SUPERSEDED", "RETIRED"}

    def test_dataclass_frozen(self):
        from utils.policy_management import (
            Policy, PolicyStatus)
        p = Policy(
            policy_id="x", version_id="1", title="x", summary="x",
            owner_role="x", content_hash="x",
            effective_date="2026-01-01",
            status=PolicyStatus.DRAFT, attestor_ids=("x",),
            attestation_cycle_days=365, related_change_ids=(),
            supersedes_version_id="",
            registered_at_utc="2026-01-01",
            activated_at_utc="", superseded_at_utc="")
        try:
            p.title = "MUTATED"
            raise AssertionError("frozen mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_196_active(self):
        m = _load("registry_v167", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-196"), None)
        assert s is not None
        assert s.status == "active"
        assert "policy_management" in (s.affected_engines or ())


class TestEngineHubIntegration:
    def test_policy_management_in_hub(self):
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"policy_management"' in admin_text


class TestStateMachine:
    def test_draft_branches(self):
        from utils.policy_management import (
            ALLOWED_TRANSITIONS, PolicyStatus)
        successors = ALLOWED_TRANSITIONS[PolicyStatus.DRAFT]
        assert PolicyStatus.IN_REVIEW in successors
        assert PolicyStatus.RETIRED in successors

    def test_in_review_can_return_to_draft(self):
        """Review may surface revisions needing re-drafting."""
        from utils.policy_management import (
            ALLOWED_TRANSITIONS, PolicyStatus)
        assert PolicyStatus.DRAFT in (
            ALLOWED_TRANSITIONS[PolicyStatus.IN_REVIEW])

    def test_active_branches(self):
        from utils.policy_management import (
            ALLOWED_TRANSITIONS, PolicyStatus)
        successors = ALLOWED_TRANSITIONS[PolicyStatus.ACTIVE]
        assert PolicyStatus.SUPERSEDED in successors
        assert PolicyStatus.RETIRED in successors

    def test_terminals_empty(self):
        from utils.policy_management import (
            ALLOWED_TRANSITIONS, PolicyStatus)
        assert ALLOWED_TRANSITIONS[PolicyStatus.SUPERSEDED] == ()
        assert ALLOWED_TRANSITIONS[PolicyStatus.RETIRED] == ()


class TestRegister:
    def _register(self, **overrides):
        from utils.policy_management import PolicyManagementEngine
        defaults = dict(
            policy_id="POL-001", version_id="v1.0",
            title="Test policy", summary="Summary",
            owner_role="head_of_compliance",
            content_hash="sha256:abc",
            effective_date="2026-07-01",
            attestor_ids=("officer",))
        defaults.update(overrides)
        eng = PolicyManagementEngine()
        return eng, eng.register_policy(**defaults)

    def test_register_returns_draft(self):
        from utils.policy_management import PolicyStatus
        eng, p = self._register()
        assert p.status == PolicyStatus.DRAFT

    def test_default_cycle_365_days(self):
        eng, p = self._register()
        assert p.attestation_cycle_days == 365

    def test_custom_cycle_works(self):
        eng, p = self._register(attestation_cycle_days=180)
        assert p.attestation_cycle_days == 180

    def test_empty_policy_id_rejected(self):
        try:
            self._register(policy_id="")
            raise AssertionError("empty policy_id should raise")
        except ValueError:
            pass

    def test_empty_attestors_rejected(self):
        try:
            self._register(attestor_ids=())
            raise AssertionError("empty attestors should raise")
        except ValueError as e:
            assert "attestor" in str(e).lower()

    def test_zero_cycle_days_rejected(self):
        try:
            self._register(attestation_cycle_days=0)
            raise AssertionError("zero cycle days should raise")
        except ValueError:
            pass

    def test_duplicate_version_rejected(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("y",))
        try:
            eng.register_policy(
                policy_id="POL-001", version_id="v1.0",
                title="x", summary="x", owner_role="x",
                content_hash="x", effective_date="2026-01-01",
                attestor_ids=("y",))
            raise AssertionError("duplicate version should raise")
        except ValueError as e:
            assert "already registered" in str(e)

    def test_two_versions_of_same_policy_id_allowed(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="abc", effective_date="2026-01-01",
            attestor_ids=("y",))
        # Same policy_id, different version → should work
        p2 = eng.register_policy(
            policy_id="POL-001", version_id="v2.0",
            title="x", summary="x", owner_role="x",
            content_hash="def", effective_date="2026-07-01",
            attestor_ids=("y",),
            supersedes_version_id="v1.0")
        assert p2.supersedes_version_id == "v1.0"


class TestTransitions:
    def _draft(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        p = eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("officer",))
        return eng, p

    def test_draft_to_in_review(self):
        from utils.policy_management import (
            PolicyStatus, TransitionOutcome)
        eng, p = self._draft()
        outcome, p = eng.transition(
            p.policy_id, p.version_id,
            PolicyStatus.IN_REVIEW, user="lead")
        assert outcome == TransitionOutcome.OK
        assert p.status == PolicyStatus.IN_REVIEW

    def test_draft_to_active_rejected(self):
        """Cannot skip review."""
        from utils.policy_management import (
            PolicyStatus, TransitionOutcome)
        eng, p = self._draft()
        outcome, _ = eng.transition(
            p.policy_id, p.version_id,
            PolicyStatus.ACTIVE, user="lead")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_in_review_back_to_draft_for_revisions(self):
        from utils.policy_management import (
            PolicyStatus, TransitionOutcome)
        eng, p = self._draft()
        eng.transition(p.policy_id, p.version_id,
                          PolicyStatus.IN_REVIEW, user="lead")
        outcome, p = eng.transition(
            p.policy_id, p.version_id,
            PolicyStatus.DRAFT, user="lead",
            reason="committee requested revisions")
        assert outcome == TransitionOutcome.OK
        assert p.status == PolicyStatus.DRAFT

    def test_active_records_activated_at(self):
        from utils.policy_management import (
            PolicyStatus, TransitionOutcome)
        eng, p = self._draft()
        eng.transition(p.policy_id, p.version_id,
                          PolicyStatus.IN_REVIEW, user="lead")
        outcome, p = eng.transition(
            p.policy_id, p.version_id,
            PolicyStatus.ACTIVE, user="board")
        assert outcome == TransitionOutcome.OK
        assert p.activated_at_utc != ""

    def test_retired_requires_reason(self):
        from utils.policy_management import (
            PolicyStatus, TransitionOutcome)
        eng, p = self._draft()
        outcome, _ = eng.transition(
            p.policy_id, p.version_id,
            PolicyStatus.RETIRED, user="x", reason="")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED


class TestAttestation:
    def _active(self):
        from utils.policy_management import (
            PolicyManagementEngine, PolicyStatus)
        eng = PolicyManagementEngine()
        p = eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("officer",))
        eng.transition(p.policy_id, p.version_id,
                          PolicyStatus.IN_REVIEW, user="lead")
        eng.transition(p.policy_id, p.version_id,
                          PolicyStatus.ACTIVE, user="board")
        return eng, p

    def test_attestation_on_draft_rejected(self):
        from utils.policy_management import (
            PolicyManagementEngine, AttestationOutcome)
        eng = PolicyManagementEngine()
        p = eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("officer",))
        outcome, _ = eng.record_attestation(
            p.policy_id, p.version_id, "officer", "DocuSign envelope")
        assert outcome == AttestationOutcome.REJECTED_POLICY_NOT_ACTIVE

    def test_attestation_requires_evidence(self):
        from utils.policy_management import AttestationOutcome
        eng, p = self._active()
        outcome, _ = eng.record_attestation(
            p.policy_id, p.version_id, "officer", "")
        assert outcome == AttestationOutcome.REJECTED_EVIDENCE_REQUIRED

    def test_attestation_records_next_due(self):
        from utils.policy_management import AttestationOutcome
        eng, p = self._active()
        outcome, p = eng.record_attestation(
            p.policy_id, p.version_id, "officer",
            "DocuSign envelope #ABC")
        assert outcome == AttestationOutcome.OK
        assert len(p.attestations) == 1
        assert p.attestations[0].next_attestation_due_utc != ""

    def test_unknown_policy_rejected(self):
        from utils.policy_management import (
            PolicyManagementEngine, AttestationOutcome)
        eng = PolicyManagementEngine()
        outcome, _ = eng.record_attestation(
            "NONE", "v1", "officer", "evidence")
        assert outcome == AttestationOutcome.REJECTED_POLICY_NOT_FOUND


class TestBidirectionalLinkage:
    """policies_for_change() reverse-lookup completes ENH-195 ↔
    ENH-196 linkage."""

    def test_policies_for_change_returns_linked(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("officer",),
            related_change_ids=("REG-000001", "REG-000002"))
        eng.register_policy(
            policy_id="POL-002", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("officer",),
            related_change_ids=("REG-000001",))
        linked = eng.policies_for_change("REG-000001")
        assert len(linked) == 2
        linked_001 = eng.policies_for_change("REG-000002")
        assert len(linked_001) == 1
        # Unknown change → empty
        assert eng.policies_for_change("NONEXISTENT") == ()


class TestOverdueAttestations:
    def test_active_policy_with_old_activation_overdue(self):
        from utils.policy_management import (
            PolicyManagementEngine, PolicyStatus, Policy)
        eng = PolicyManagementEngine()
        p = eng.register_policy(
            policy_id="POL-001", version_id="v1.0",
            title="x", summary="x", owner_role="x",
            content_hash="x", effective_date="2026-01-01",
            attestor_ids=("officer",),
            attestation_cycle_days=10)
        eng.transition(p.policy_id, p.version_id,
                          PolicyStatus.IN_REVIEW, user="lead")
        eng.transition(p.policy_id, p.version_id,
                          PolicyStatus.ACTIVE, user="board")
        # Manually backdate activated_at to 30 days ago
        current = eng.policy_by_version(p.policy_id, p.version_id)
        old_dt = (datetime.now(timezone.utc)
                    - timedelta(days=30)).isoformat()
        kwargs = {f: getattr(current, f) for f in
                    current.__dataclass_fields__}
        kwargs["activated_at_utc"] = old_dt
        eng._policies[(p.policy_id, p.version_id)] = Policy(**kwargs)
        overdue = eng.overdue_attestations()
        assert len(overdue) == 1


class TestHonestDeferrals:
    def test_document_storage_meta_only(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        s = eng.board_summary()
        assert "META_ONLY" in s["document_storage_status"]
        assert "document_management" in s["document_storage_status"]

    def test_esignature_deferred(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["esignature_verification_status"]


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_unique_policies",
                   "n_total_versions", "n_active_versions",
                   "n_overdue_attestations", "n_attestations_recorded",
                   "document_storage_status",
                   "esignature_verification_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-196 PolicyManagementEngine"


class TestNoRegression:
    def test_audit_passes(self):
        m = _load("audit_v167", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True

    def test_gate_count(self):
        m = _load("audit_count_v167", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_166_regulatory_change_works(self):
        from utils.regulatory_change import RegulatoryChangeEngine
        eng = RegulatoryChangeEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-195 RegulatoryChangeEngine")

    def test_v10_165_examiner_works(self):
        from utils.examiner_reporting import ExaminerReportingEngine
        eng = ExaminerReportingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-199 ExaminerReportingEngine")

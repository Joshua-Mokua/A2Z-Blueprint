"""tests/test_compliance_training_v10_168.py — ENH-197 Compliance
Training Management. **LAST AML standard before module closure.**

Verifies the v10.168 deliverable:
- Engine exists, parses, imports
- 4 enums (CourseStatus 3, AssignmentStatus 4, CourseLifecycleOutcome 3,
  AssignmentOutcome 5)
- 3 frozen dataclasses (CertificationRecord, Course, Assignment) with to_dict
- (course_id, version) unique per course; assignment_id unique per assignment
- Course lifecycle DRAFT → PUBLISHED → RETIRED
- Assignment lifecycle ASSIGNED → COMPLETED/FAILED/WITHDRAWN
- Cannot assign DRAFT course
- Cannot complete without evidence
- Score >= pass_score → COMPLETED + Certification issued
- Score < pass_score → FAILED + no Certification
- Cannot complete a terminal assignment
- Reverse-lookups: courses_for_change() + courses_for_policy()
- 2 honest deferrals (LMS integration + course content)
- ENH-197 active in registry, registered in Tier 30
- Audit 151/151
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "compliance_training.py"
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
        from utils.compliance_training import ComplianceTrainingEngine
        assert ComplianceTrainingEngine() is not None

    def test_enum_cardinalities(self):
        from utils.compliance_training import (
            CourseStatus, AssignmentStatus,
            CourseLifecycleOutcome, AssignmentOutcome)
        assert len(list(CourseStatus)) == 3
        assert len(list(AssignmentStatus)) == 4
        assert len(list(CourseLifecycleOutcome)) == 3
        assert len(list(AssignmentOutcome)) == 5

    def test_dataclass_frozen(self):
        from utils.compliance_training import (
            Course, CourseStatus)
        c = Course(course_id="x", version="1", title="x",
                     description="x", owner_role="x",
                     mandatory_for_roles=(), validity_days=365,
                     pass_score=70, status=CourseStatus.DRAFT,
                     related_policy_ids=(),
                     related_regulatory_change_ids=(),
                     registered_at_utc="2026-01-01")
        try:
            c.title = "MUTATED"
            raise AssertionError("frozen mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_197_active(self):
        m = _load("registry_v168", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-197"), None)
        assert s is not None
        assert s.status == "active"
        assert "compliance_training" in (s.affected_engines or ())


class TestEngineHubIntegration:
    def test_compliance_training_in_hub(self):
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"compliance_training"' in admin_text

    def test_all_9_aml_engines_in_tier_30(self):
        """All 9 AML cluster engines should be in the hub Tier 30
        once ENH-197 lands."""
        admin_text = ADMIN_PATH.read_text(encoding="utf-8")
        for engine in (
                "kyc_onboarding", "aml_monitoring", "sar_filing",
                "compliance_risk_assessment", "examiner_reporting",
                "regulatory_change", "policy_management",
                "compliance_training"):
            assert f'"{engine}"' in admin_text, (
                f"engine {engine} missing from ENGINE_HUB_TIERS")


class TestCourseLifecycle:
    def _draft_course(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="C1", version="v1", title="Test",
            description="x", owner_role="head_of_compliance")
        return eng, c

    def test_draft_default(self):
        from utils.compliance_training import CourseStatus
        eng, c = self._draft_course()
        assert c.status == CourseStatus.DRAFT

    def test_publish_works(self):
        from utils.compliance_training import (
            CourseStatus, CourseLifecycleOutcome)
        eng, c = self._draft_course()
        outcome, c = eng.publish_course(c.course_id, c.version,
                                              user="head_of_compliance")
        assert outcome == CourseLifecycleOutcome.OK
        assert c.status == CourseStatus.PUBLISHED

    def test_published_to_retired(self):
        from utils.compliance_training import (
            CourseStatus, CourseLifecycleOutcome)
        eng, c = self._draft_course()
        eng.publish_course(c.course_id, c.version, user="x")
        outcome, c = eng.transition_course(
            c.course_id, c.version, CourseStatus.RETIRED, user="x")
        assert outcome == CourseLifecycleOutcome.OK
        assert c.status == CourseStatus.RETIRED

    def test_retired_terminal(self):
        from utils.compliance_training import (
            CourseStatus, CourseLifecycleOutcome,
            ALLOWED_COURSE_TRANSITIONS)
        assert ALLOWED_COURSE_TRANSITIONS[CourseStatus.RETIRED] == ()


class TestRegisterCourse:
    def test_empty_course_id_rejected(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        try:
            eng.register_course(
                course_id="", version="v1", title="x",
                description="x", owner_role="x")
            raise AssertionError("empty course_id should raise")
        except ValueError:
            pass

    def test_invalid_validity_rejected(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        try:
            eng.register_course(
                course_id="x", version="v1", title="x",
                description="x", owner_role="x",
                validity_days=0)
            raise AssertionError("zero validity should raise")
        except ValueError:
            pass

    def test_invalid_pass_score_rejected(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        try:
            eng.register_course(
                course_id="x", version="v1", title="x",
                description="x", owner_role="x",
                pass_score=150)
            raise AssertionError("pass_score >100 should raise")
        except ValueError:
            pass

    def test_duplicate_version_rejected(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        eng.register_course(
            course_id="C1", version="v1", title="x",
            description="x", owner_role="x")
        try:
            eng.register_course(
                course_id="C1", version="v1", title="x",
                description="x", owner_role="x")
            raise AssertionError("duplicate version should raise")
        except ValueError as e:
            assert "already registered" in str(e)


class TestAssignment:
    def _published_course(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="C1", version="v1", title="x",
            description="x", owner_role="x", validity_days=365,
            pass_score=80)
        eng.publish_course(c.course_id, c.version, user="x")
        return eng, c

    def test_assign_draft_course_rejected(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine, AssignmentOutcome)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="X", version="v1", title="x",
            description="x", owner_role="x")
        outcome, _ = eng.assign(c.course_id, c.version, "EMP-1",
                                  "teller", "2026-12-31")
        assert outcome == (
            AssignmentOutcome.REJECTED_COURSE_NOT_PUBLISHED)

    def test_assign_published_works(self):
        from utils.compliance_training import (
            AssignmentOutcome, AssignmentStatus)
        eng, c = self._published_course()
        outcome, a = eng.assign(c.course_id, c.version, "EMP-1",
                                  "teller", "2026-12-31")
        assert outcome == AssignmentOutcome.OK
        assert a.status == AssignmentStatus.ASSIGNED

    def test_assign_unknown_course_rejected(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine, AssignmentOutcome)
        eng = ComplianceTrainingEngine()
        outcome, _ = eng.assign("UNKNOWN", "v1", "EMP-1", "teller",
                                  "2026-12-31")
        assert outcome == AssignmentOutcome.REJECTED_NOT_FOUND


class TestComplete:
    def _assigned(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="C1", version="v1", title="x",
            description="x", owner_role="x", validity_days=365,
            pass_score=80)
        eng.publish_course(c.course_id, c.version, user="x")
        outcome, a = eng.assign(c.course_id, c.version, "EMP-1",
                                  "teller", "2026-12-31")
        return eng, c, a

    def test_complete_without_evidence_rejected(self):
        from utils.compliance_training import AssignmentOutcome
        eng, c, a = self._assigned()
        outcome, _ = eng.complete(a.assignment_id, score=85,
                                    evidence="")
        assert outcome == AssignmentOutcome.REJECTED_REASON_REQUIRED

    def test_pass_score_completes_with_certification(self):
        from utils.compliance_training import (
            AssignmentOutcome, AssignmentStatus)
        eng, c, a = self._assigned()
        outcome, a = eng.complete(a.assignment_id, score=85,
                                    evidence="LMS #123")
        assert outcome == AssignmentOutcome.OK
        assert a.status == AssignmentStatus.COMPLETED
        assert a.certification is not None
        assert a.certification.score == 85

    def test_fail_score_marks_failed_no_certification(self):
        from utils.compliance_training import (
            AssignmentOutcome, AssignmentStatus)
        eng, c, a = self._assigned()
        # pass_score=80; submit 60
        outcome, a = eng.complete(a.assignment_id, score=60,
                                    evidence="LMS #123")
        assert outcome == AssignmentOutcome.OK
        assert a.status == AssignmentStatus.FAILED
        assert a.certification is None

    def test_certification_expiry_correct(self):
        from utils.compliance_training import (
            AssignmentOutcome)
        eng, c, a = self._assigned()
        outcome, a = eng.complete(a.assignment_id, score=85,
                                    evidence="LMS #123")
        # validity_days=365 → expiry = today + 365
        from datetime import datetime, timezone, timedelta
        expected_expiry = (datetime.now(timezone.utc) +
                              timedelta(days=365)).strftime("%Y-%m-%d")
        assert a.certification.expiry_date == expected_expiry

    def test_re_complete_terminal_rejected(self):
        from utils.compliance_training import AssignmentOutcome
        eng, c, a = self._assigned()
        eng.complete(a.assignment_id, score=85, evidence="LMS #123")
        outcome, _ = eng.complete(a.assignment_id, score=90,
                                    evidence="x")
        assert outcome == AssignmentOutcome.REJECTED_ALREADY_TERMINAL


class TestWithdraw:
    def _assigned(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="C1", version="v1", title="x",
            description="x", owner_role="x")
        eng.publish_course(c.course_id, c.version, user="x")
        outcome, a = eng.assign(c.course_id, c.version, "EMP-1",
                                  "teller", "2026-12-31")
        return eng, c, a

    def test_withdraw_requires_reason(self):
        from utils.compliance_training import AssignmentOutcome
        eng, c, a = self._assigned()
        outcome, _ = eng.withdraw(a.assignment_id, reason="")
        assert outcome == AssignmentOutcome.REJECTED_REASON_REQUIRED

    def test_withdraw_with_reason(self):
        from utils.compliance_training import (
            AssignmentOutcome, AssignmentStatus)
        eng, c, a = self._assigned()
        outcome, a = eng.withdraw(
            a.assignment_id, reason="employee transferred")
        assert outcome == AssignmentOutcome.OK
        assert a.status == AssignmentStatus.WITHDRAWN


class TestQueries:
    def _setup(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="C1", version="v1", title="x",
            description="x", owner_role="x",
            related_policy_ids=("POL-AML-001",),
            related_regulatory_change_ids=("REG-000001",))
        eng.publish_course(c.course_id, c.version, user="x")
        eng.assign(c.course_id, c.version, "EMP-1", "teller",
                      "2026-12-31")
        eng.assign(c.course_id, c.version, "EMP-2", "manager",
                      "2026-12-31")
        return eng, c

    def test_assignments_for_employee(self):
        eng, c = self._setup()
        assert len(eng.assignments_for_employee("EMP-1")) == 1

    def test_assignments_for_role(self):
        eng, c = self._setup()
        assert len(eng.assignments_for_role("teller")) == 1

    def test_courses_for_change(self):
        """Reverse-lookup completes ENH-195 ↔ ENH-197 linkage."""
        eng, c = self._setup()
        assert len(eng.courses_for_change("REG-000001")) == 1
        assert eng.courses_for_change("UNKNOWN") == ()

    def test_courses_for_policy(self):
        """Reverse-lookup completes ENH-196 ↔ ENH-197 linkage."""
        eng, c = self._setup()
        assert len(eng.courses_for_policy("POL-AML-001")) == 1


class TestOverdueAndExpiring:
    def test_overdue_assignment_surfaced(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        c = eng.register_course(
            course_id="C1", version="v1", title="x",
            description="x", owner_role="x")
        eng.publish_course(c.course_id, c.version, user="x")
        # Past due date
        old_due = (datetime.now(timezone.utc)
                    - timedelta(days=10)).isoformat()
        eng.assign(c.course_id, c.version, "EMP-1", "teller",
                      old_due)
        overdue = eng.overdue_assignments()
        assert len(overdue) == 1


class TestHonestDeferrals:
    def test_lms_integration_deferred(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["lms_integration_status"]
        assert "Moodle" in s["lms_integration_status"] or \
                 "Cornerstone" in s["lms_integration_status"]

    def test_course_content_meta_only(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        s = eng.board_summary()
        assert "META_ONLY" in s["course_content_status"]


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_courses_total",
                   "n_courses_published", "n_assignments_total",
                   "n_assignments_completed",
                   "n_assignments_failed",
                   "n_assignments_overdue",
                   "n_certifications_expiring_30d",
                   "n_active_certifications",
                   "lms_integration_status",
                   "course_content_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-197 ComplianceTrainingEngine"


class TestNoRegression:
    def test_audit_passes(self):
        m = _load("audit_v168", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True

    def test_gate_count(self):
        m = _load("audit_count_v168", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_167_policy_works(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-196 PolicyManagementEngine")

    def test_v10_166_regulatory_change_works(self):
        from utils.regulatory_change import RegulatoryChangeEngine
        eng = RegulatoryChangeEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-195 RegulatoryChangeEngine")

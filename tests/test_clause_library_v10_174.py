"""tests/test_clause_library_v10_174.py — ENH-226"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "clause_library.py"
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
        from utils.clause_library import ClauseLibraryEngine
        assert ClauseLibraryEngine() is not None

    def test_enums(self):
        from utils.clause_library import (
            ClauseStatus, ClauseClassification, PlaybookStatus,
            TransitionOutcome)
        assert len(list(ClauseStatus)) == 4
        assert len(list(ClauseClassification)) == 3
        assert len(list(PlaybookStatus)) == 3
        assert len(list(TransitionOutcome)) == 5


class TestRegistry:
    def test_active(self):
        m = _load("registry_v174", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-226"), None)
        assert s.status == "active"
        assert "clause_library" in s.affected_engines


class TestHubIntegration:
    def test_in_hub(self):
        admin = ADMIN_PATH.read_text(encoding="utf-8")
        assert '"clause_library"' in admin


class TestClauseRegistration:
    def _eng(self):
        from utils.clause_library import ClauseLibraryEngine
        return ClauseLibraryEngine()

    def test_register_draft(self):
        from utils.clause_library import (
            ClauseClassification, ClauseStatus)
        eng = self._eng()
        c = eng.register_clause(
            name="X", category="indemnity",
            agreement_types=("vendor_msa",),
            clause_text="text", drafting_notes="notes",
            classification=ClauseClassification.APPROVED,
            author="legal")
        assert c.status == ClauseStatus.DRAFT
        assert c.current_revision().version_number == 1

    def test_no_agreement_types_rejected(self):
        from utils.clause_library import ClauseClassification
        eng = self._eng()
        try:
            eng.register_clause(
                "X", "x", (), "text", "notes",
                ClauseClassification.APPROVED, "legal")
            raise AssertionError("empty agreement_types should raise")
        except ValueError:
            pass

    def test_empty_text_rejected(self):
        from utils.clause_library import ClauseClassification
        eng = self._eng()
        try:
            eng.register_clause(
                "X", "x", ("vendor_msa",), "", "notes",
                ClauseClassification.APPROVED, "legal")
            raise AssertionError("empty text should raise")
        except ValueError:
            pass


class TestClauseLifecycle:
    def _drafted(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification)
        eng = ClauseLibraryEngine()
        c = eng.register_clause(
            "X", "indemnity", ("vendor_msa",), "text", "notes",
            ClauseClassification.APPROVED, "legal")
        return eng, c

    def test_draft_to_approved_path(self):
        from utils.clause_library import (
            ClauseStatus, TransitionOutcome)
        eng, c = self._drafted()
        eng.transition_clause(c.clause_id, ClauseStatus.UNDER_REVIEW,
                                  user="legal")
        outcome, c = eng.transition_clause(
            c.clause_id, ClauseStatus.APPROVED,
            user="head_of_legal")
        assert outcome == TransitionOutcome.OK
        assert c.status == ClauseStatus.APPROVED
        assert c.current_revision().approved_by == "head_of_legal"

    def test_skip_to_approved_rejected(self):
        from utils.clause_library import (
            ClauseStatus, TransitionOutcome)
        eng, c = self._drafted()
        outcome, _ = eng.transition_clause(
            c.clause_id, ClauseStatus.APPROVED, user="x")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_retired_requires_reason(self):
        from utils.clause_library import (
            ClauseStatus, TransitionOutcome)
        eng, c = self._drafted()
        outcome, _ = eng.transition_clause(
            c.clause_id, ClauseStatus.RETIRED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED


class TestRevise:
    def test_revise_creates_new_version(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification, ClauseStatus)
        eng = ClauseLibraryEngine()
        c = eng.register_clause(
            "X", "indemnity", ("vendor_msa",), "v1 text", "v1 notes",
            ClauseClassification.APPROVED, "legal")
        eng.transition_clause(c.clause_id, ClauseStatus.UNDER_REVIEW,
                                  user="x")
        eng.transition_clause(c.clause_id, ClauseStatus.APPROVED,
                                  user="x")
        c = eng.revise_clause(c.clause_id, "v2 text", "v2 notes",
                                  "legal")
        # v2 is now current, status is back to DRAFT
        assert c.current_revision().version_number == 2
        assert c.status == ClauseStatus.DRAFT
        assert len(c.revisions) == 2


class TestPlaybook:
    def _approved_clause(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification, ClauseStatus)
        eng = ClauseLibraryEngine()
        c = eng.register_clause(
            "X", "indemnity", ("vendor_msa",), "text", "notes",
            ClauseClassification.APPROVED, "legal")
        eng.transition_clause(c.clause_id, ClauseStatus.UNDER_REVIEW,
                                  user="x")
        eng.transition_clause(c.clause_id, ClauseStatus.APPROVED,
                                  user="x")
        return eng, c

    def test_create_playbook_with_approved_clause(self):
        from utils.clause_library import (
            PlaybookEntry, TransitionOutcome)
        eng, c = self._approved_clause()
        entries = [PlaybookEntry(1, c.clause_id, "PREFERRED",
                                       "use first")]
        outcome, pb = eng.create_playbook(
            "PB", "vendor_msa", "desc",
            "head_of_legal", entries)
        assert outcome == TransitionOutcome.OK
        assert pb.playbook_id.startswith("PBK-")

    def test_playbook_rejects_prohibited_clause(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification, PlaybookEntry,
            TransitionOutcome)
        eng = ClauseLibraryEngine()
        c = eng.register_clause(
            "Bad", "indemnity", ("vendor_msa",), "bad text", "notes",
            ClauseClassification.PROHIBITED, "legal")
        entries = [PlaybookEntry(1, c.clause_id, "PREFERRED", "x")]
        outcome, pb = eng.create_playbook(
            "PB", "vendor_msa", "desc", "x", entries)
        assert outcome == TransitionOutcome.REJECTED_PROHIBITED_IN_PLAYBOOK
        assert pb is None

    def test_publish_requires_approved_clauses(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification,
            PlaybookEntry, PlaybookStatus, TransitionOutcome)
        eng = ClauseLibraryEngine()
        c = eng.register_clause(
            "X", "indemnity", ("vendor_msa",), "text", "notes",
            ClauseClassification.APPROVED, "legal")
        # Clause is in DRAFT, not APPROVED
        entries = [PlaybookEntry(1, c.clause_id, "PREFERRED", "x")]
        _, pb = eng.create_playbook("PB", "vendor_msa", "desc",
                                          "x", entries)
        outcome, _ = eng.transition_playbook(
            pb.playbook_id, PlaybookStatus.PUBLISHED, user="x")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_publish_with_approved(self):
        from utils.clause_library import (
            PlaybookEntry, PlaybookStatus, TransitionOutcome)
        eng, c = self._approved_clause()
        entries = [PlaybookEntry(1, c.clause_id, "PREFERRED", "x")]
        _, pb = eng.create_playbook("PB", "vendor_msa", "desc",
                                          "x", entries)
        outcome, pb = eng.transition_playbook(
            pb.playbook_id, PlaybookStatus.PUBLISHED, user="x")
        assert outcome == TransitionOutcome.OK
        assert pb.status == PlaybookStatus.PUBLISHED


class TestQueries:
    def test_clauses_for_agreement_type(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification, ClauseStatus)
        eng = ClauseLibraryEngine()
        c1 = eng.register_clause(
            "A", "indemnity", ("vendor_msa",), "x", "y",
            ClauseClassification.APPROVED, "legal")
        c2 = eng.register_clause(
            "B", "indemnity", ("loan_agreement",), "x", "y",
            ClauseClassification.APPROVED, "legal")
        # only c1 will be APPROVED
        eng.transition_clause(c1.clause_id, ClauseStatus.UNDER_REVIEW,
                                  user="x")
        eng.transition_clause(c1.clause_id, ClauseStatus.APPROVED,
                                  user="x")
        out = eng.clauses_for_agreement_type("vendor_msa")
        assert len(out) == 1
        assert out[0].clause_id == c1.clause_id

    def test_prohibited_clauses(self):
        from utils.clause_library import (
            ClauseLibraryEngine, ClauseClassification)
        eng = ClauseLibraryEngine()
        eng.register_clause("A", "x", ("y",), "x", "y",
                              ClauseClassification.APPROVED, "legal")
        eng.register_clause("B", "x", ("y",), "x", "y",
                              ClauseClassification.PROHIBITED,
                              "legal")
        assert len(eng.prohibited_clauses()) == 1


class TestHonestDeferrals:
    def test_three(self):
        from utils.clause_library import ClauseLibraryEngine
        eng = ClauseLibraryEngine()
        s = eng.board_summary()
        assert "DEFERRED" in s["ai_draft_assistance_status"]
        assert "META_ONLY" in s["document_generation_status"]
        assert "DEFERRED" in s["clause_usage_telemetry_status"]


class TestPortfolioSummary:
    def test_shape(self):
        from utils.clause_library import ClauseLibraryEngine
        eng = ClauseLibraryEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_clauses_total",
                   "n_clauses_approved", "n_prohibited_clauses",
                   "n_playbooks_total", "n_playbooks_published",
                   "clause_status_counts",
                   "clause_classification_counts",
                   "playbook_status_counts",
                   "ai_draft_assistance_status",
                   "document_generation_status",
                   "clause_usage_telemetry_status",
                   "regulatory_basis"):
            assert f in s
        assert s["engine"] == "ENH-226 ClauseLibraryEngine"


class TestNoRegression:
    def test_audit(self):
        m = _load("audit_v174", AUDIT_PATH)
        for gid, gfn in m.GATES:
            assert gfn()["passed"] is True

    def test_v10_173_works(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-225 LegalSpendManagementEngine")

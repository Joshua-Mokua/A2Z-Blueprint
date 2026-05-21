"""tests/test_legal_document_management_v10_177.py — ENH-229.

Verifies the Legal Document Management engine (distinct from the KYC
document_management engine).
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


class TestModuleShape:
    def test_imports(self):
        from utils.legal_document_management import (
            LegalDocumentKind, LegalDocumentState, Confidentiality,
            RetentionClass, DiscoveryStatus, TransitionOutcome,
            LegalDocument, DiscoveryRequest,
            LegalDocumentManagementEngine,
        )
        assert LegalDocumentManagementEngine is not None

    def test_legal_doc_kind_has_ten_values(self):
        from utils.legal_document_management import LegalDocumentKind
        assert len(LegalDocumentKind) == 10

    def test_legal_doc_state_has_five_values(self):
        from utils.legal_document_management import LegalDocumentState
        assert len(LegalDocumentState) == 5
        assert LegalDocumentState.DRAFT.value == "DRAFT"
        assert LegalDocumentState.PURGED.value == "PURGED"

    def test_confidentiality_has_four_values(self):
        from utils.legal_document_management import Confidentiality
        assert len(Confidentiality) == 4
        assert Confidentiality.PRIVILEGED.value == "PRIVILEGED"

    def test_retention_class_has_five_values(self):
        from utils.legal_document_management import RetentionClass
        assert len(RetentionClass) == 5
        assert RetentionClass.SEVEN_YEAR.value == "SEVEN_YEAR"
        assert RetentionClass.LITIGATION_HOLD.value == "LITIGATION_HOLD"

    def test_discovery_status_has_four_values(self):
        from utils.legal_document_management import DiscoveryStatus
        assert len(DiscoveryStatus) == 4

    def test_transition_outcome_has_five_values(self):
        from utils.legal_document_management import TransitionOutcome
        assert len(TransitionOutcome) == 5


class TestRegistry:
    def test_enh229_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next((x for x in STANDARDS_REGISTRY
                  if x.standard_id == "ENH-229"), None)
        assert s is not None
        assert s.status == "active"
        assert s.affected_engines == ("legal_document_management",)
        assert s.implementation_batch == "v10.177"


class TestHubIntegration:
    def test_in_tier_31(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "legal_document_management" in text
        assert "LegalDocumentManagementEngine" in text
        assert "ENH-229" in text


class TestRegisterDocument:
    def test_register_creates_draft(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass, LegalDocumentState)
        eng = LegalDocumentManagementEngine()
        d = eng.register_document(
            doc_id="DOC-1", doc_kind=LegalDocumentKind.AGREEMENT,
            title="Test", description="Desc",
            confidentiality=Confidentiality.CONFIDENTIAL,
            retention_class=RetentionClass.SEVEN_YEAR)
        assert d.state == LegalDocumentState.DRAFT
        assert d.version_no == 1
        assert d.purgeable_after is not None  # 7-year retention computed

    def test_register_indefinite_no_purge_date(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        d = eng.register_document(
            doc_id="CR-001", doc_kind=LegalDocumentKind.CORPORATE_RECORD,
            title="Articles of Association", description="d",
            confidentiality=Confidentiality.INTERNAL,
            retention_class=RetentionClass.INDEFINITE)
        assert d.purgeable_after is None

    def test_duplicate_id_rejected(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="DOC-1", doc_kind=LegalDocumentKind.OTHER,
            title="t", description="d",
            confidentiality=Confidentiality.PUBLIC,
            retention_class=RetentionClass.SEVEN_YEAR)
        try:
            eng.register_document(
                doc_id="DOC-1", doc_kind=LegalDocumentKind.OTHER,
                title="t", description="d",
                confidentiality=Confidentiality.PUBLIC,
                retention_class=RetentionClass.SEVEN_YEAR)
            assert False, "should have raised"
        except ValueError:
            pass

    def test_empty_title_rejected(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        try:
            eng.register_document(
                doc_id="X", doc_kind=LegalDocumentKind.OTHER,
                title="   ", description="d",
                confidentiality=Confidentiality.PUBLIC,
                retention_class=RetentionClass.SEVEN_YEAR)
            assert False, "should have raised"
        except ValueError:
            pass


class TestLifecycle:
    def _new_doc(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="L-1", doc_kind=LegalDocumentKind.AGREEMENT,
            title="t", description="d",
            confidentiality=Confidentiality.CONFIDENTIAL,
            retention_class=RetentionClass.SEVEN_YEAR)
        return eng

    def test_full_path(self):
        from utils.legal_document_management import (
            LegalDocumentState, TransitionOutcome)
        eng = self._new_doc()
        for st in (LegalDocumentState.UNDER_REVIEW,
                   LegalDocumentState.APPROVED,
                   LegalDocumentState.ARCHIVED):
            _, out = eng.transition_document("L-1", st)
            assert out == TransitionOutcome.OK

    def test_under_review_back_to_draft_requires_reason(self):
        from utils.legal_document_management import (
            LegalDocumentState, TransitionOutcome)
        eng = self._new_doc()
        eng.transition_document("L-1", LegalDocumentState.UNDER_REVIEW)
        _, out = eng.transition_document(
            "L-1", LegalDocumentState.DRAFT, reason="")
        assert out == TransitionOutcome.REJECTED_REASON_REQUIRED
        _, out = eng.transition_document(
            "L-1", LegalDocumentState.DRAFT, reason="needs revisions")
        assert out == TransitionOutcome.OK

    def test_purge_before_retention_rejected(self):
        from utils.legal_document_management import (
            LegalDocumentState, TransitionOutcome)
        eng = self._new_doc()
        for st in (LegalDocumentState.UNDER_REVIEW,
                   LegalDocumentState.APPROVED,
                   LegalDocumentState.ARCHIVED):
            eng.transition_document("L-1", st)
        _, out = eng.transition_document(
            "L-1", LegalDocumentState.PURGED, reason="cleanup")
        assert out == TransitionOutcome.REJECTED_RETENTION_NOT_DUE

    def test_invalid_jump_rejected(self):
        from utils.legal_document_management import (
            LegalDocumentState, TransitionOutcome)
        eng = self._new_doc()
        # DRAFT → APPROVED is invalid (must go via UNDER_REVIEW)
        _, out = eng.transition_document(
            "L-1", LegalDocumentState.APPROVED)
        assert out == TransitionOutcome.REJECTED_BAD_TRANSITION


class TestVersionBump:
    def test_bump_in_draft(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="V-1", doc_kind=LegalDocumentKind.AGREEMENT,
            title="t", description="d",
            confidentiality=Confidentiality.PUBLIC,
            retention_class=RetentionClass.SEVEN_YEAR)
        v2 = eng.bump_version("V-1")
        assert v2.version_no == 2
        v3 = eng.bump_version("V-1")
        assert v3.version_no == 3

    def test_bump_outside_draft_rejected(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass, LegalDocumentState)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="V-2", doc_kind=LegalDocumentKind.AGREEMENT,
            title="t", description="d",
            confidentiality=Confidentiality.PUBLIC,
            retention_class=RetentionClass.SEVEN_YEAR)
        eng.transition_document("V-2", LegalDocumentState.UNDER_REVIEW)
        try:
            eng.bump_version("V-2")
            assert False, "should have raised"
        except ValueError:
            pass


class TestQueries:
    def _populated(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="A", doc_kind=LegalDocumentKind.AGREEMENT,
            title="t", description="d",
            confidentiality=Confidentiality.CONFIDENTIAL,
            retention_class=RetentionClass.SEVEN_YEAR,
            matter_id="MAT-1")
        eng.register_document(
            doc_id="B", doc_kind=LegalDocumentKind.LEGAL_OPINION,
            title="t", description="d",
            confidentiality=Confidentiality.PRIVILEGED,
            retention_class=RetentionClass.LITIGATION_HOLD,
            matter_id="MAT-1")
        eng.register_document(
            doc_id="C", doc_kind=LegalDocumentKind.COURT_FILING,
            title="t", description="d",
            confidentiality=Confidentiality.INTERNAL,
            retention_class=RetentionClass.SEVEN_YEAR,
            matter_id="MAT-2")
        return eng

    def test_documents_for_matter(self):
        eng = self._populated()
        assert len(eng.documents_for_matter("MAT-1")) == 2
        assert len(eng.documents_for_matter("MAT-2")) == 1
        assert len(eng.documents_for_matter("MAT-99")) == 0

    def test_documents_by_kind(self):
        from utils.legal_document_management import LegalDocumentKind
        eng = self._populated()
        assert len(eng.documents_by_kind(
            LegalDocumentKind.AGREEMENT)) == 1

    def test_privileged_documents(self):
        eng = self._populated()
        priv = eng.privileged_documents()
        assert len(priv) == 1
        assert priv[0].doc_id == "B"


class TestHoldLinkage:
    def test_link_idempotent(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="H-1", doc_kind=LegalDocumentKind.COURT_FILING,
            title="t", description="d",
            confidentiality=Confidentiality.INTERNAL,
            retention_class=RetentionClass.SEVEN_YEAR)
        eng.link_to_hold("H-1", "HOLD-A")
        eng.link_to_hold("H-1", "HOLD-A")  # idempotent
        d = eng.document_by_id("H-1")
        assert d.hold_ids == ("HOLD-A",)
        eng.link_to_hold("H-1", "HOLD-B")
        d = eng.document_by_id("H-1")
        assert d.hold_ids == ("HOLD-A", "HOLD-B")

    def test_documents_for_hold(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="X", doc_kind=LegalDocumentKind.OTHER,
            title="t", description="d",
            confidentiality=Confidentiality.PUBLIC,
            retention_class=RetentionClass.SEVEN_YEAR)
        eng.link_to_hold("X", "HOLD-1")
        assert len(eng.documents_for_hold("HOLD-1")) == 1
        assert len(eng.documents_for_hold("HOLD-99")) == 0


class TestDiscovery:
    def _setup(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        for did, mid in [("D1", "M1"), ("D2", "M1"), ("D3", "M2")]:
            eng.register_document(
                doc_id=did, doc_kind=LegalDocumentKind.AGREEMENT,
                title="t", description="d",
                confidentiality=Confidentiality.PUBLIC,
                retention_class=RetentionClass.SEVEN_YEAR,
                matter_id=mid)
        return eng

    def test_discovery_request_matches_scope(self):
        eng = self._setup()
        req = eng.create_discovery_request(
            request_id="DR-1", requested_by="counsel",
            matter_id="M1")
        assert sorted(req.matched_doc_ids) == ["D1", "D2"]

    def test_empty_scope_rejected(self):
        eng = self._setup()
        try:
            eng.create_discovery_request(
                request_id="DR-2", requested_by="x")
            assert False, "should have raised"
        except ValueError:
            pass

    def test_discovery_lifecycle(self):
        from utils.legal_document_management import (
            DiscoveryStatus, TransitionOutcome)
        eng = self._setup()
        eng.create_discovery_request(
            request_id="DR-1", requested_by="x", matter_id="M1")
        _, out = eng.transition_discovery(
            "DR-1", DiscoveryStatus.IN_PROGRESS)
        assert out == TransitionOutcome.OK
        _, out = eng.transition_discovery(
            "DR-1", DiscoveryStatus.FULFILLED)
        assert out == TransitionOutcome.OK
        # FULFILLED → CLOSED needs no reason
        _, out = eng.transition_discovery(
            "DR-1", DiscoveryStatus.CLOSED)
        assert out == TransitionOutcome.OK

    def test_early_close_requires_reason(self):
        from utils.legal_document_management import (
            DiscoveryStatus, TransitionOutcome)
        eng = self._setup()
        eng.create_discovery_request(
            request_id="DR-X", requested_by="x", matter_id="M1")
        # REQUESTED → CLOSED without reason rejected
        _, out = eng.transition_discovery(
            "DR-X", DiscoveryStatus.CLOSED, reason="")
        assert out == TransitionOutcome.REJECTED_REASON_REQUIRED
        _, out = eng.transition_discovery(
            "DR-X", DiscoveryStatus.CLOSED, reason="duplicate request")
        assert out == TransitionOutcome.OK


class TestHonestDeferrals:
    def test_deferrals_named(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine)
        eng = LegalDocumentManagementEngine()
        b = eng.board_summary()
        for key in (
            "blob_storage_status",
            "version_control_diff_status",
            "automated_retention_purge_status",
            "full_text_search_status",
            "ediscovery_bundle_export_status",
            "access_control_enforcement_status",
            "contract_review_linkage_status",
        ):
            assert key in b
            v = b[key]
            assert "DEFERRED" in v or "META_ONLY" in v


class TestPortfolioSummary:
    def test_engine_name(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine)
        eng = LegalDocumentManagementEngine()
        b = eng.board_summary()
        assert b["engine"] == "ENH-229 LegalDocumentManagementEngine"
        assert "Companies Act" in b["regulatory_basis"]

    def test_board_breakdowns(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine, LegalDocumentKind,
            Confidentiality, RetentionClass)
        eng = LegalDocumentManagementEngine()
        eng.register_document(
            doc_id="X", doc_kind=LegalDocumentKind.AGREEMENT,
            title="t", description="d",
            confidentiality=Confidentiality.PRIVILEGED,
            retention_class=RetentionClass.SEVEN_YEAR)
        b = eng.board_summary()
        assert b["n_documents_total"] == 1
        assert b["n_privileged_documents"] == 1
        assert b["by_kind"]["AGREEMENT"] == 1
        assert b["by_confidentiality"]["PRIVILEGED"] == 1


class TestNoRegression:
    def test_existing_kyc_doc_engine_unchanged(self):
        """utils/document_management.py is for KYC docs and must
        still work — they are completely separate engines."""
        from utils.document_management import DocumentManagementEngine
        eng = DocumentManagementEngine()
        b = eng.board_summary()
        assert b["entity"] == "Ecobank Kenya"

    def test_legal_dashboard_unchanged(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        assert "ENH-228" in eng.board_summary()["engine"]

    def test_legal_hold_unchanged(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        assert "ENH-227" in eng.board_summary()["engine"]

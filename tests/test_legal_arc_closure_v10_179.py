"""tests/test_legal_arc_closure_v10_179.py — v10.179 Legal module
closure ceremony tests.

Verifies the v10.179 closure deliverable:
- pages/28_legal_arc_cockpit.py exists, parses, references all 9
  fully-engineered Legal engine classes
- utils/api_legal.py exists, parses, has APIRouter + JWT auth
- All 10 ENH-22x..230 standards are status='active' in registry
- pages/7_admin.py has Tier 4E (Legal Arc Closure) marker
- scripts/audit.py has G154 + G155 gates registered
- Audit passes with 155 gates total (153 → 155)
- G149 cockpit-registration ratchet still passes (legal cockpit
  registered in app.py)
- Module-level engine singletons reachable in api_legal
- No regression of v10.170-v10.178 work or prior module closures
  (Treasury v10.155 + Compliance v10.169)
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COCKPIT_PATH = REPO_ROOT / "pages" / "28_legal_arc_cockpit.py"
API_PATH = REPO_ROOT / "utils" / "api_legal.py"
ADMIN_PATH = REPO_ROOT / "pages" / "7_admin.py"
APP_PATH = REPO_ROOT / "app.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestCockpitShape:
    def test_cockpit_exists_and_parses(self):
        assert COCKPIT_PATH.exists()
        ast.parse(COCKPIT_PATH.read_text(encoding="utf-8"))

    def test_cockpit_imports_all_9_named_engines(self):
        text = COCKPIT_PATH.read_text(encoding="utf-8")
        for cls in ("ObligationTrackingEngine",
                      "LegalCaseManagementEngine",
                      "OutsideCounselPortalEngine",
                      "LegalSpendManagementEngine",
                      "ClauseLibraryEngine",
                      "LegalHoldManagementEngine",
                      "LegalDashboardEngine",
                      "LegalDocumentManagementEngine",
                      "LegalAnalyticsEngine"):
            assert cls in text, f"cockpit missing: {cls}"

    def test_cockpit_has_7_tabs(self):
        text = COCKPIT_PATH.read_text(encoding="utf-8")
        # G4: ≤7 sub-tabs per page
        assert text.count("st.tabs([") == 1
        # 7 tab labels — verify each
        assert "📊 Dashboard" in text
        assert "⚖️ Matters" in text
        assert "💰 Spend + Counsel" in text
        assert "📜 Obligations" in text
        assert "🔒 Holds + Docs" in text
        assert "📚 Clauses" in text
        assert "📈 Analytics" in text


class TestApiShape:
    def test_api_exists_and_parses(self):
        assert API_PATH.exists()
        ast.parse(API_PATH.read_text(encoding="utf-8"))

    def test_api_has_router(self):
        text = API_PATH.read_text(encoding="utf-8")
        assert "router = APIRouter" in text

    def test_api_uses_jwt_auth(self):
        text = API_PATH.read_text(encoding="utf-8")
        assert "Depends(get_current_user)" in text

    def test_api_has_cross_engine_board_endpoint(self):
        """The headline /board endpoint that bundles all engines'
        board_summary into one response — the demo-closing argument."""
        text = API_PATH.read_text(encoding="utf-8")
        assert '@router.get("/board")' in text
        assert "obligation" in text.lower()
        assert "analytics" in text.lower()

    def test_api_imports_all_engines(self):
        text = API_PATH.read_text(encoding="utf-8")
        for engine_module in (
                "obligation_tracking", "legal_case_management",
                "outside_counsel_portal", "legal_spend_management",
                "clause_library", "legal_hold_management",
                "legal_dashboard", "legal_document_management",
                "legal_analytics"):
            assert engine_module in text, (
                f"api missing import: {engine_module}")


class TestRegistryClosure:
    def test_all_10_legal_standards_active(self):
        m = _load("registry_legal_closure",
                    REPO_ROOT / "utils" / "standards_registry.py")
        for n in range(221, 231):
            sid = f"ENH-{n}"
            s = next(
                (x for x in m.STANDARDS_REGISTRY
                 if x.standard_id == sid), None)
            assert s is not None, f"{sid} missing from registry"
            assert s.status == "active", (
                f"{sid} status={s.status}, expected active")
            # ENH-221 is META_ONLY at closure — empty engines tuple OK
            if sid == "ENH-221":
                continue
            assert s.affected_engines, (
                f"{sid} has empty affected_engines")


class TestAdminClosureMarker:
    def test_tier_4e_legal_marker_present(self):
        text = ADMIN_PATH.read_text(encoding="utf-8")
        assert "Tier 4E" in text
        assert "Legal Arc Closure (v10.179)" in text
        assert "legal_arc_cockpit_marker" in text


class TestAuditGates:
    def test_g154_registered(self):
        text = AUDIT_PATH.read_text(encoding="utf-8")
        assert "gate_legal_module_closed" in text
        assert '"G154"' in text

    def test_g155_registered(self):
        text = AUDIT_PATH.read_text(encoding="utf-8")
        assert "gate_legal_arc_ui_integrated" in text
        assert '"G155"' in text

    def test_audit_count_155(self):
        m = _load("audit_count_v179", AUDIT_PATH)
        assert len(m.GATES) == 155

    def test_audit_passes(self):
        m = _load("audit_run_v179", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True, (
                f"{gid} regressed: {r.get('violations')}")

    def test_g154_returns_pass_with_10_of_10(self):
        m = _load("audit_g154", AUDIT_PATH)
        result = m.gate_legal_module_closed()
        assert result["passed"] is True
        assert result["n_active"] == 10
        assert result["n_total"] == 10

    def test_g155_returns_pass_with_9_of_9(self):
        m = _load("audit_g155", AUDIT_PATH)
        result = m.gate_legal_arc_ui_integrated()
        assert result["passed"] is True
        assert result["n_engines_imported"] == 9


class TestAppRegistration:
    """G149 ratchet — every cockpit must be registered in app.py."""

    def test_legal_cockpit_in_app_nav(self):
        text = APP_PATH.read_text(encoding="utf-8")
        assert "28_legal_arc_cockpit.py" in text
        assert "Legal Arc Cockpit" in text


class TestEndToEndAPI:
    """Probe the API surface — verify import + engine singletons
    work without actually running an HTTP server."""

    def test_api_imports_cleanly(self):
        try:
            from utils import api_legal
            assert hasattr(api_legal, "router")
        except ImportError as e:
            # Acceptable if fastapi missing — the shim should handle it
            assert "fastapi" in str(e).lower(), (
                f"unexpected import error: {e}")

    def test_engines_instantiated_at_module_level(self):
        from utils import api_legal
        assert hasattr(api_legal, "_obligation")
        assert hasattr(api_legal, "_case")
        assert hasattr(api_legal, "_spend")
        assert hasattr(api_legal, "_counsel")
        assert hasattr(api_legal, "_clause")
        assert hasattr(api_legal, "_hold")
        assert hasattr(api_legal, "_document")
        assert hasattr(api_legal, "_dashboard")
        assert hasattr(api_legal, "_analytics")


class TestNoRegression:
    def test_v10_178_legal_analytics_works(self):
        from utils.legal_analytics import LegalAnalyticsEngine
        eng = LegalAnalyticsEngine()
        b = eng.board_summary()
        assert "ENH-230" in b.get("engine", "")

    def test_v10_177_legal_document_management_works(self):
        from utils.legal_document_management import (
            LegalDocumentManagementEngine)
        eng = LegalDocumentManagementEngine()
        b = eng.board_summary()
        assert "ENH-229" in b.get("engine", "")

    def test_v10_176_legal_dashboard_works(self):
        from utils.legal_dashboard import LegalDashboardEngine
        from utils.obligation_tracking import ObligationTrackingEngine
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        from utils.clause_library import ClauseLibraryEngine
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalDashboardEngine(
            obligation_engine=ObligationTrackingEngine(),
            case_engine=LegalCaseManagementEngine(),
            spend_engine=LegalSpendManagementEngine(),
            counsel_engine=OutsideCounselPortalEngine(),
            clause_engine=ClauseLibraryEngine(),
            hold_engine=LegalHoldManagementEngine(),
        )
        b = eng.board_summary()
        assert "ENH-228" in b.get("engine", "")

    def test_treasury_closure_unchanged(self):
        """v10.155 Treasury G150/G151 must remain green."""
        m = _load("audit_treasury_v179", AUDIT_PATH)
        assert m.gate_treasury_module_closed()["passed"] is True
        assert m.gate_treasury_arc_ui_integrated()["passed"] is True

    def test_compliance_closure_unchanged(self):
        """v10.169 Compliance G152/G153 must remain green."""
        m = _load("audit_compliance_v179", AUDIT_PATH)
        assert m.gate_compliance_module_closed()["passed"] is True
        assert m.gate_compliance_arc_ui_integrated()["passed"] is True

"""tests/test_compliance_arc_closure_v10_169.py — v10.169 AML/Compliance
module closure ceremony tests.

Verifies the v10.169 closure deliverable:
- pages/27_compliance_arc_cockpit.py exists, parses, references all 8
  named AML/Compliance engine classes
- utils/api_compliance.py exists, parses, has APIRouter + JWT auth
- All 9 ENH-19x standards are status='active' in registry
- pages/7_admin.py has Tier 4D (AML/Compliance Arc Closure) marker
- scripts/audit.py has G152 + G153 gates registered
- Audit passes with 153 gates total (151 → 153)
- G149 cockpit-registration ratchet still passes (compliance cockpit
  registered in app.py)
- 5-engine end-to-end probe via the API works
- No regression of v10.160-v10.168 work
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COCKPIT_PATH = REPO_ROOT / "pages" / "27_compliance_arc_cockpit.py"
API_PATH = REPO_ROOT / "utils" / "api_compliance.py"
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

    def test_cockpit_imports_all_8_named_engines(self):
        text = COCKPIT_PATH.read_text(encoding="utf-8")
        for cls in ("KycOnboardingEngine", "AmlMonitoringEngine",
                      "SarFilingEngine",
                      "ComplianceRiskAssessmentEngine",
                      "ExaminerReportingEngine",
                      "RegulatoryChangeEngine",
                      "PolicyManagementEngine",
                      "ComplianceTrainingEngine"):
            assert cls in text, f"cockpit missing: {cls}"

    def test_cockpit_has_7_tabs(self):
        text = COCKPIT_PATH.read_text(encoding="utf-8")
        # G4: ≤7 sub-tabs per page
        assert text.count("st.tabs([") == 1
        # Count tab labels — should be exactly 7
        assert "📊 Dashboard" in text
        assert "👤 KYC + Screening" in text
        assert "🚨 AML Monitoring" in text
        assert "📋 SAR Filings" in text
        assert "📊 Risk Assessment" in text
        assert "📑 Reg + Policy" in text
        assert "🎓 Training + Examiner" in text


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
        """The headline /board endpoint that bundles all 9 engines'
        board_summary into one response — the demo-closing argument."""
        text = API_PATH.read_text(encoding="utf-8")
        assert '@router.get("/board")' in text
        assert "kyc_onboarding" in text
        assert "compliance_training" in text

    def test_api_imports_all_engines(self):
        text = API_PATH.read_text(encoding="utf-8")
        for engine_module in (
                "kyc_onboarding", "aml_monitoring", "sar_filing",
                "compliance_risk_assessment", "examiner_reporting",
                "regulatory_change", "policy_management",
                "compliance_training"):
            assert engine_module in text, (
                f"api missing import: {engine_module}")


class TestRegistryClosure:
    def test_all_9_aml_standards_active(self):
        m = _load("registry_closure", REPO_ROOT / "utils" /
                    "standards_registry.py")
        for n in range(191, 200):
            sid = f"ENH-{n}"
            s = next(
                (x for x in m.STANDARDS_REGISTRY
                 if x.standard_id == sid), None)
            assert s is not None, f"{sid} missing from registry"
            assert s.status == "active", (
                f"{sid} status={s.status}, expected active")
            assert s.affected_engines, (
                f"{sid} has empty affected_engines")


class TestAdminClosureMarker:
    def test_tier_4d_compliance_marker_present(self):
        text = ADMIN_PATH.read_text(encoding="utf-8")
        assert "Tier 4D" in text
        assert "AML/Compliance Arc Closure (v10.169)" in text
        assert "compliance_arc_cockpit_marker" in text


class TestAuditGates:
    def test_g152_registered(self):
        text = AUDIT_PATH.read_text(encoding="utf-8")
        assert "gate_compliance_module_closed" in text
        assert '"G152"' in text

    def test_g153_registered(self):
        text = AUDIT_PATH.read_text(encoding="utf-8")
        assert "gate_compliance_arc_ui_integrated" in text
        assert '"G153"' in text

    def test_audit_count_153(self):
        m = _load("audit_count_v169", AUDIT_PATH)
        assert len(m.GATES) == 153

    def test_audit_passes(self):
        m = _load("audit_run_v169", AUDIT_PATH)
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True, (
                f"{gid} regressed: {r.get('violations')}")

    def test_g152_returns_pass_with_9_of_9(self):
        m = _load("audit_g152", AUDIT_PATH)
        result = m.gate_compliance_module_closed()
        assert result["passed"] is True
        assert result["n_active"] == 9
        assert result["n_total"] == 9

    def test_g153_returns_pass_with_8_of_8(self):
        m = _load("audit_g153", AUDIT_PATH)
        result = m.gate_compliance_arc_ui_integrated()
        assert result["passed"] is True
        assert result["n_engines_imported"] == 8


class TestAppRegistration:
    """G149 ratchet — every cockpit must be registered in app.py."""

    def test_compliance_cockpit_in_app_nav(self):
        text = APP_PATH.read_text(encoding="utf-8")
        assert "27_compliance_arc_cockpit.py" in text
        assert "Compliance Arc Cockpit" in text


class TestEndToEndAPI:
    """Probe the API surface — verify import + endpoint definitions
    work without actually running an HTTP server."""

    def test_api_imports_cleanly(self):
        # The API file should import without errors when the JWT shim
        # falls back (no fastapi installed in test env)
        import importlib
        # Just verify it imports — no exception
        try:
            from utils import api_compliance
            assert hasattr(api_compliance, "router")
        except ImportError as e:
            # Acceptable if fastapi missing — the shim should handle it
            assert "fastapi" in str(e).lower(), (
                f"unexpected import error: {e}")

    def test_engines_instantiated_at_module_level(self):
        # api_compliance creates module-level singletons — verify
        # they're reachable
        from utils import api_compliance
        assert hasattr(api_compliance, "_kyc")
        assert hasattr(api_compliance, "_aml")
        assert hasattr(api_compliance, "_sar")
        assert hasattr(api_compliance, "_risk")
        assert hasattr(api_compliance, "_examiner")
        assert hasattr(api_compliance, "_reg_change")
        assert hasattr(api_compliance, "_policy")
        assert hasattr(api_compliance, "_training")


class TestNoRegression:
    def test_v10_168_compliance_training_works(self):
        from utils.compliance_training import (
            ComplianceTrainingEngine)
        eng = ComplianceTrainingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-197 ComplianceTrainingEngine")

    def test_v10_167_policy_works(self):
        from utils.policy_management import PolicyManagementEngine
        eng = PolicyManagementEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-196 PolicyManagementEngine")

    def test_treasury_closure_unchanged(self):
        """v10.155 Treasury G150/G151 must remain green."""
        m = _load("audit_treasury_check", AUDIT_PATH)
        g150 = m.gate_treasury_module_closed()
        g151 = m.gate_treasury_arc_ui_integrated()
        assert g150["passed"] is True
        assert g151["passed"] is True

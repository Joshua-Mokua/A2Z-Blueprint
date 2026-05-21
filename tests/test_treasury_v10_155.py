"""tests/test_treasury_v10_155.py — Phase 2 Treasury Module CLOSURE verification.

Verifies the v10.155 closure batch:
- Treasury cockpit pages/26_treasury_arc_cockpit.py exists and imports all 12 engines
- POST endpoints in utils/api_treasury.py for state-mutating workflows
  (agents approve/reject, alm run-lcr/run-repricing-gap, climate check-breach)
- Cockpit registered in app.py's _treasury_grp (G149 enforcement)
- G150 closure gate exists and passes
- G151 UI integration gate exists and passes
- All 18 Treasury standards still active
- v10.153.1 signature-discipline check: cockpit + API use real
  require_access and audit_log signatures (no invented kwargs)
- No regression of v10.151 Product closure or v10.153 nav hotfix
- Audit suite at 151/151
"""
from __future__ import annotations
import ast
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COCKPIT_PATH = REPO_ROOT / "pages" / "26_treasury_arc_cockpit.py"
API_PATH = REPO_ROOT / "utils" / "api_treasury.py"
APP_PATH = REPO_ROOT / "app.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestCockpitShape:
    def test_cockpit_exists(self):
        assert COCKPIT_PATH.exists()

    def test_cockpit_parses(self):
        ast.parse(COCKPIT_PATH.read_text(encoding="utf-8"))

    def test_cockpit_loads_without_streamlit(self):
        # Sandbox doesn't have Streamlit; cockpit should still load
        # via the graceful-fallback path
        m = _load("cockpit_load", COCKPIT_PATH)
        assert hasattr(m, "STREAMLIT_AVAILABLE")

    def test_cockpit_imports_all_12_engines(self):
        text = COCKPIT_PATH.read_text(encoding="utf-8")
        for cls in (
            "TreasuryIntelligenceEngine", "TreasuryALMEngine",
            "TreasuryDashboardEngine", "TreasuryProductsEngine",
            "AgentOrchestrator", "TreasuryConnectivityEngine",
            "DigitalAssetTreasuryEngine", "UnifiedTreasuryPlatform",
            "LiquidityRiskEngine", "LiquidityStressEngine",
            "IslamicTreasuryEngine", "ClimateTreasuryLimitsEngine",
        ):
            assert cls in text, f"cockpit missing import: {cls}"

    def test_cockpit_seven_or_fewer_tabs(self):
        # G4 tab_counts requires ≤7 sub-tabs per page
        text = COCKPIT_PATH.read_text(encoding="utf-8")
        # The first st.tabs() call is the top-level layout
        match = re.search(r'st\.tabs\(\s*\[(.*?)\]\s*\)', text,
                          re.DOTALL)
        assert match
        tab_block = match.group(1)
        n_tabs = len(re.findall(r'"[^"]*"', tab_block))
        assert n_tabs <= 7, f"cockpit has {n_tabs} top-level tabs, must be ≤7"


class TestCockpitSignatureDiscipline:
    """v10.153.1 lesson codified: cockpit must use real
    require_access(module: str, silent: bool = False) and real
    audit_log(action, username, detail, module, before, after)."""

    def _strip_docs(self, text: str) -> str:
        text = re.sub(r'"""[\s\S]*?"""', '', text)
        text = re.sub(r"'''[\s\S]*?'''", '', text)
        text = re.sub(r'#[^\n]*', '', text)
        return text

    def test_require_access_uses_real_signature(self):
        code = self._strip_docs(
            COCKPIT_PATH.read_text(encoding="utf-8"))
        assert 'require_access("alm_liquidity")' in code, (
            "cockpit must call require_access with a module-id string "
            "(real signature), not roles=... kwargs (the v10.153.1 bug)")

    def test_audit_log_uses_real_signature(self):
        code = self._strip_docs(
            COCKPIT_PATH.read_text(encoding="utf-8"))
        # Find the actual call site (not the stub def)
        # The call site is the multiline call near the bottom of the file
        m = re.search(
            r'audit_log\(\s*\n\s*action="treasury_arc_cockpit\.view"',
            code, re.DOTALL)
        assert m, "couldn't find treasury_arc_cockpit audit_log call"
        # Now check the surrounding 10 lines for proper kwargs
        idx = m.start()
        block = code[idx:idx+500]  # plenty of room for the call
        assert "username=" in block, (
            "audit_log must use username= per real signature")
        assert "detail=" in block, (
            "audit_log must use detail= per real signature")
        # The bad kwargs from v10.153.1
        assert "actor=" not in block, (
            "audit_log must NOT use actor= (v10.153.1 bug)")
        assert "payload=" not in block, (
            "audit_log must NOT use payload= (v10.153.1 bug)")


class TestAPIPostEndpoints:
    """v10.155 ships POST endpoints for state-mutating workflows."""

    def test_pydantic_models_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for model in (
            "AgentApprovalRequest", "AgentRejectionRequest",
            "RunLCRRequest", "RunRepricingGapRequest",
            "ClimateBreachCheckRequest",
        ):
            assert model in text, f"missing Pydantic model: {model}"

    def test_post_endpoints_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in (
            "/agents/approve", "/agents/reject",
            "/alm/run-lcr", "/alm/run-repricing-gap",
            "/climate/check-breach",
        ):
            assert path in text, f"missing POST endpoint: {path}"

    def test_router_post_decorators_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        # At least 5 @router.post decorators for the 5 POST endpoints
        n_post = len(re.findall(r'@router\.post\(', text))
        assert n_post >= 5, (
            f"expected >=5 @router.post decorators, got {n_post}")

    def test_post_endpoints_jwt_protected(self):
        # Every POST endpoint must include Depends(get_current_user)
        text = API_PATH.read_text(encoding="utf-8")
        # Split by @router.post and verify each subsequent block has JWT
        chunks = re.split(r'@router\.post\(', text)
        # First chunk is preamble; rest are post endpoint bodies
        assert len(chunks) >= 6, (
            f"expected >=5 @router.post chunks, got {len(chunks)-1}")
        for i, chunk in enumerate(chunks[1:], start=1):
            # Take up to the next @router.* or end of file
            block = re.split(r'@router\.', chunk)[0]
            assert "Depends(get_current_user)" in block, (
                f"POST endpoint #{i} missing JWT auth: "
                f"{block[:200]}")


class TestNavRegistration:
    """v10.153 G149 enforces this — cockpit must be in app.py."""

    def test_cockpit_registered_in_app(self):
        text = APP_PATH.read_text(encoding="utf-8")
        assert "pages/26_treasury_arc_cockpit.py" in text, (
            "Treasury Arc Cockpit not registered in app.py — "
            "G149 will fail")

    def test_cockpit_in_treasury_grp(self):
        text = APP_PATH.read_text(encoding="utf-8")
        # Find _treasury_grp block and verify cockpit is in it
        m = re.search(r'_treasury_grp\s*=\s*_dg\(\[(.*?)\]\)',
                       text, re.DOTALL)
        assert m, "_treasury_grp block not found"
        section = m.group(1)
        assert "26_treasury_arc_cockpit.py" in section, (
            "Treasury Arc Cockpit must be registered in _treasury_grp")


class TestClosureGates:
    def test_g150_function_exists(self):
        m = _load("audit_g150_exists", AUDIT_PATH)
        assert hasattr(m, "gate_treasury_module_closed")

    def test_g151_function_exists(self):
        m = _load("audit_g151_exists", AUDIT_PATH)
        assert hasattr(m, "gate_treasury_arc_ui_integrated")

    def test_g150_passes(self):
        m = _load("audit_g150_pass", AUDIT_PATH)
        result = m.gate_treasury_module_closed()
        assert result["passed"] is True, (
            f"G150 failed: {result.get('violations')}")
        assert result["n_active"] == 18
        assert result["n_total"] == 18

    def test_g151_passes(self):
        m = _load("audit_g151_pass", AUDIT_PATH)
        result = m.gate_treasury_arc_ui_integrated()
        assert result["passed"] is True, (
            f"G151 failed: {result.get('violations')}")
        assert result["n_engines_imported"] == 12

    def test_gates_registered(self):
        m = _load("audit_g_reg", AUDIT_PATH)
        gate_ids = [g[0] for g in m.GATES]
        assert "G150" in gate_ids
        assert "G151" in gate_ids


class TestPhase2Closure:
    def test_all_18_treasury_standards_active(self):
        m = _load("sr_treasury",
                   REPO_ROOT / "utils" / "standards_registry.py")
        treasury_ids = [
            "CBK-PG-05-LCR",
            *[f"ENH-{n}" for n in range(231, 241)],
            "ENH-LR-001",
            *[f"ENH-TRS-R{n}" for n in range(1, 7)],
        ]
        for sid in treasury_ids:
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None, f"{sid} missing from registry"
            assert std.status == "active", (
                f"{sid} not active: status={std.status}")


class TestNoRegression:
    def test_v10_151_product_gates_still_pass(self):
        m = _load("audit_p_intact_v155", AUDIT_PATH)
        for gate in (m.gate_product_module_closed,
                      m.gate_product_arc_ui_integrated):
            result = gate()
            assert result["passed"] is True

    def test_v10_153_nav_gate_still_passes(self):
        m = _load("audit_n_intact_v155", AUDIT_PATH)
        result = m.gate_cockpits_registered_in_app()
        assert result["passed"] is True
        # Now 10 cockpits (was 9; v10.155 adds Treasury cockpit)
        assert result["n_cockpits_on_disk"] == 10
        assert result["n_cockpits_registered"] == 10

    def test_total_gate_count(self):
        m = _load("audit_count_v155", AUDIT_PATH)
        # v10.154 was 149; v10.155 adds G150 + G151 → 151
        assert len(m.GATES) == 151

    def test_existing_treasury_pages_still_referenced(self):
        # G149 + sanity check we didn't accidentally remove anything
        text = APP_PATH.read_text(encoding="utf-8")
        for existing in ("pages/25_treasury.py", "pages/81_alm.py",
                          "pages/53_irrbb.py", "pages/77_capital.py"):
            assert existing in text, (
                f"existing Treasury-area page {existing} unexpectedly "
                f"removed from app.py")

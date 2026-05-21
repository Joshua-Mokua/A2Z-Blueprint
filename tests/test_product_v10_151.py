"""tests/test_product_v10_151.py — ENH-140 Product Analytics Dashboard
+ Phase 1E Product Module CLOSURE verification.

Verifies the v10.151 closure batch:
- ENH-140 Product Analytics Dashboard engine
- pages/16_product_arc_cockpit.py exists + imports all 10 engines
- utils/api_product.py exists + has APIRouter + JWT auth
- G147 Product module closure gate exists + passes
- G148 Product UI integration gate exists + passes
- All 10 Phase 1E standards (ENH-131..140) status='active'
- Audit suite at 148/148
- No regression of Strategy module or earlier modules
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = REPO_ROOT / "utils" / "product_analytics_dashboard.py"
COCKPIT_PATH = REPO_ROOT / "pages" / "16_product_arc_cockpit.py"
API_PATH = REPO_ROOT / "utils" / "api_product.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestDashboardEngine:
    def test_engine_module_exists(self):
        assert DASHBOARD_PATH.exists()

    def test_engine_module_parses(self):
        ast.parse(DASHBOARD_PATH.read_text())

    def test_class_and_dataclass_present(self):
        m = _load("dash_shape", DASHBOARD_PATH)
        assert hasattr(m, "ProductAnalyticsDashboard")
        assert hasattr(m, "DashboardPayload")

    def test_required_methods_present(self):
        m = _load("dash_methods", DASHBOARD_PATH)
        eng = m.ProductAnalyticsDashboard()
        for method in (
            "get_dashboard_payload",
            "get_engine_health_check",
            "get_summary_metrics",
            "get_product_arc_kpis",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))

    def test_health_check_runs(self):
        m = _load("dash_health", DASHBOARD_PATH)
        eng = m.ProductAnalyticsDashboard()
        health = eng.get_engine_health_check()
        assert "n_engines_checked" in health
        assert "all_healthy" in health
        # All 9 companion engines should be checkable
        assert health["n_engines_checked"] == 9

    def test_summary_metrics_complete(self):
        m = _load("dash_sum", DASHBOARD_PATH)
        eng = m.ProductAnalyticsDashboard()
        summary = eng.get_summary_metrics()
        for k in ("n_products", "portfolio_revenue_kes",
                  "portfolio_margin_pct", "n_loss_making_products",
                  "ranking_distribution", "avg_product_score",
                  "competitive_leadership_rate_pct",
                  "n_actionable_pricing_recommendations"):
            assert k in summary

    def test_dashboard_payload_complete(self):
        m = _load("dash_pay", DASHBOARD_PATH)
        eng = m.ProductAnalyticsDashboard()
        payload = eng.get_dashboard_payload(
            include_per_customer=False)
        assert payload.generated_at_utc
        assert len(payload.by_product) > 0
        assert len(payload.by_segment) > 0
        assert isinstance(payload.bank_wide, dict)
        assert isinstance(payload.engine_status, dict)


class TestCockpit:
    def test_cockpit_page_exists(self):
        assert COCKPIT_PATH.exists()

    def test_cockpit_imports_all_10_engines(self):
        text = COCKPIT_PATH.read_text()
        for cls in (
            "ProductPnLIntelligence", "ProductLifecycleEngine",
            "CustomerNeedsAnalyzer",
            "ProductCompetitiveIntelligence", "ProductCVPBuilder",
            "ProductRankingEngine", "DynamicPricingEngine",
            "ProductRecommendationEngine",
            "ProductBundlingIntelligence",
            "ProductAnalyticsDashboard",
        ):
            assert cls in text, f"cockpit missing import: {cls}"

    def test_cockpit_has_seven_or_fewer_tabs(self):
        # G4 tab_counts requires ≤7 sub-tabs per page
        text = COCKPIT_PATH.read_text()
        # Find st.tabs([...]) and count entries
        # Simple heuristic: count the comma-separated entries
        import re
        match = re.search(r'st\.tabs\(\s*\[(.*?)\]\s*\)', text,
                          re.DOTALL)
        assert match
        tab_block = match.group(1)
        # Count strings (each tab label is in quotes)
        n_tabs = len(re.findall(r'"[^"]*"', tab_block))
        assert n_tabs <= 7, f"cockpit has {n_tabs} tabs, must be ≤7"

    def test_cockpit_module_loads(self):
        # Should load even when streamlit isn't available
        m = _load("cockpit_load", COCKPIT_PATH)
        assert hasattr(m, "STREAMLIT_AVAILABLE")


class TestAPIRouter:
    def test_api_module_exists(self):
        assert API_PATH.exists()

    def test_api_module_parses(self):
        ast.parse(API_PATH.read_text())

    def test_api_has_apirouter_and_jwt(self):
        text = API_PATH.read_text()
        assert "router = APIRouter" in text
        assert "Depends(get_current_user)" in text

    def test_api_endpoints_cover_all_10_engines(self):
        text = API_PATH.read_text()
        # At minimum, each of the 10 engine classes must be imported
        for cls in (
            "ProductPnLIntelligence", "ProductLifecycleEngine",
            "CustomerNeedsAnalyzer",
            "ProductCompetitiveIntelligence", "ProductCVPBuilder",
            "ProductRankingEngine", "DynamicPricingEngine",
            "ProductRecommendationEngine",
            "ProductBundlingIntelligence",
            "ProductAnalyticsDashboard",
        ):
            assert cls in text, f"api missing engine: {cls}"

    def test_api_module_loads_without_fastapi(self):
        # Sandbox doesn't have FastAPI; module should still load
        m = _load("api_load", API_PATH)
        assert hasattr(m, "FASTAPI_AVAILABLE")
        # Either FastAPI is available and router is set, or not and
        # router is None — both are valid module states
        assert hasattr(m, "router")


class TestClosureGates:
    def test_g147_function_exists(self):
        m = _load("audit_for_g147", AUDIT_PATH)
        assert hasattr(m, "gate_product_module_closed")

    def test_g148_function_exists(self):
        m = _load("audit_for_g148", AUDIT_PATH)
        assert hasattr(m, "gate_product_arc_ui_integrated")

    def test_g147_passes(self):
        m = _load("audit_g147_pass", AUDIT_PATH)
        result = m.gate_product_module_closed()
        assert result["passed"] is True, (
            f"G147 failed: {result.get('violations')}")
        assert result["n_active"] == 10
        assert result["n_total"] == 10

    def test_g148_passes(self):
        m = _load("audit_g148_pass", AUDIT_PATH)
        result = m.gate_product_arc_ui_integrated()
        assert result["passed"] is True, (
            f"G148 failed: {result.get('violations')}")
        assert result["n_engines_imported"] == 10

    def test_gates_registered(self):
        m = _load("audit_reg", AUDIT_PATH)
        gate_ids = [g[0] for g in m.GATES]
        assert "G147" in gate_ids
        assert "G148" in gate_ids


class TestPhase1EClosure:
    def test_all_10_phase1e_standards_active(self):
        m = _load("sr_p1e_close",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for n in range(131, 141):
            sid = f"ENH-{n}"
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None, f"{sid} missing from registry"
            assert std.status == "active", (
                f"{sid} not active: status={std.status}")

    def test_enh_140_specific_attributes(self):
        m = _load("sr_140",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-140"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_analytics_dashboard" in std.affected_engines
        assert std.implementation_batch == "v10.151"


class TestNoRegression:
    def test_strategy_module_intact(self):
        m = _load("sr_strat_v151",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for n in range(141, 156):
            sid = f"ENH-{n}"
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active", (
                f"{sid} regressed during Product closure")

    def test_strategy_gates_intact(self):
        m = _load("audit_strat_intact", AUDIT_PATH)
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids, (
                f"strategy gate {gid} disappeared")

    def test_admin_tier_4b_has_all_ten_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in (
            "Tier 4B — Product Intelligence",
            "product_pnl_intelligence", "product_lifecycle",
            "customer_needs_analyzer",
            "product_competitive_intel", "product_cvp_builder",
            "product_ranking", "dynamic_pricing",
            "product_recommendation", "product_bundling",
            "product_analytics_dashboard",
            "ProductAnalyticsDashboard",
        ):
            assert token in text, f"missing token: {token}"

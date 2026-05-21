"""tests/test_strategy_v10_141.py — Strategy UI integration pass.

Verifies the v10.141 Strategy UI deliverables:

1. pages/15_strategy_arc_cockpit.py exists, parses, imports all 15 engines,
   uses require_access + audit_log per house style
2. utils/api_strategy.py exposes 19 endpoints — one per Strategy
   standard's main entrypoint, all JWT-protected via
   Depends(get_current_user), all using Pydantic request models
3. Router is mounted in utils/api.py
4. G146 strategy_arc_ui_integrated audit gate exists, passes, and
   verifies all 15 engine class names appear in the cockpit page
5. No regression — G144 (264/264), G145 (15/15), prior tests still
   pass

This test file is the model for the "UI pass on module closure" norm
adopted from v10.141 forward — every future module closure includes
an analogous test file.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Cockpit page existence + structure ────────────────────────────

class TestCockpitPage:

    @pytest.fixture
    def cockpit_path(self):
        return REPO_ROOT / "pages" / "15_strategy_arc_cockpit.py"

    @pytest.fixture
    def cockpit_text(self, cockpit_path):
        return cockpit_path.read_text(encoding="utf-8")

    def test_cockpit_exists(self, cockpit_path):
        assert cockpit_path.exists(), (
            "pages/15_strategy_arc_cockpit.py must exist for v10.141 "
            "UI pass — Strategy module closure requires cockpit per "
            "v10.46 protocol")

    def test_cockpit_parses(self, cockpit_path):
        ast.parse(cockpit_path.read_text(encoding="utf-8"))

    def test_cockpit_imports_all_15_engines(self, cockpit_text):
        """All 15 Strategy engine classes must be imported."""
        expected = [
            "StrategyFormulationEngine",
            "StrategicOptionsGenerator",
            "StrategyDecompositionEngine",
            "StrategicInitiativePortfolio",
            "EnhancedCascadeEngine",
            "StrategyGapAnalyzer",
            "CorrectiveActionGenerator",
            "StrategyLearningLoop",
            "StakeholderEngagementEngine",
            "StrategyHealthEngine",
            "StrategySimulator",
            "StrategyCommunicationEngine",
            "DailyStrategyIntegration",
            "STOToolkit",
            "StrategyROIAnalytics",
        ]
        missing = [c for c in expected if c not in cockpit_text]
        assert not missing, (
            f"Cockpit page missing imports for: {missing}")

    def test_cockpit_uses_require_access(self, cockpit_text):
        """Per house style, every page calls require_access() at top."""
        assert "require_access(" in cockpit_text, (
            "Cockpit must call require_access() per pages/_access.py "
            "house style")

    def test_cockpit_emits_audit_log(self, cockpit_text):
        """Per user prefs (Other instructions): include audit_log()
        after every write operation."""
        assert "audit_log(" in cockpit_text, (
            "Cockpit must call audit_log() — required per project "
            "discipline")

    def test_cockpit_has_seven_tabs(self, cockpit_text):
        """Cockpit organises 15 engines into 7 lifecycle-phase tabs."""
        # Count distinct tab labels (heuristic by tab emoji)
        for emoji in ("🎯", "📊", "📈", "🔍", "🧠", "🏢", "💰"):
            assert emoji in cockpit_text, (
                f"Cockpit missing tab emoji {emoji}")

    def test_cockpit_calls_engine_methods(self, cockpit_text):
        """Spot-check that representative engine methods are called.

        Note: the cockpit's STO tab calls the 6 individual STO methods
        (one per sub-tab) for lazy evaluation matching the tabbed UX.
        The composite ``get_full_toolkit_payload`` is used by the API
        endpoint instead — verified separately in TestEngineMethodsExist.
        """
        for fragment in (
                ".generate_swot(",
                ".define_strategic_pillars(",
                ".knapsack_optimize(",
                ".cascade_with_engagement(",
                ".analyze_gaps(",
                ".generate_corrective_actions(",
                ".capture_lessons_learned(",
                ".run_engagement_pulse(",
                ".build_dashboard_payload(",
                ".simulate_resource_reallocation(",
                ".distribute_strategy_update(",
                ".get_portfolio(",        # STO sub-tab Portfolio
                ".get_strategy_risks(",   # STO sub-tab Risks
                ".calculate_strategy_roi(",
        ):
            assert fragment in cockpit_text, (
                f"Cockpit missing engine call: {fragment}")


# ─── API router structure ──────────────────────────────────────────

class TestAPIRouter:

    @pytest.fixture
    def api_path(self):
        return REPO_ROOT / "utils" / "api_strategy.py"

    @pytest.fixture
    def api_text(self, api_path):
        return api_path.read_text(encoding="utf-8")

    @pytest.fixture
    def api_tree(self, api_text):
        return ast.parse(api_text)

    def test_api_file_exists(self, api_path):
        assert api_path.exists(), (
            "utils/api_strategy.py must exist for React-ready API "
            "surface")

    def test_api_parses(self, api_path):
        ast.parse(api_path.read_text(encoding="utf-8"))

    def test_router_defined_with_strategy_prefix(self, api_text):
        assert 'APIRouter(prefix="/api/strategy"' in api_text

    def test_at_least_18_endpoints(self, api_tree):
        """One endpoint per Strategy standard's main entrypoint
        (some standards have multiple methods exposed) plus _meta."""
        n_endpoints = 0
        for node in ast.walk(api_tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if (isinstance(dec, ast.Call)
                            and isinstance(dec.func, ast.Attribute)
                            and isinstance(dec.func.value, ast.Name)
                            and dec.func.value.id == "router"
                            and dec.func.attr in (
                                "get", "post", "put", "delete")):
                        n_endpoints += 1
        assert n_endpoints >= 18, (
            f"Expected ≥ 18 endpoints; found {n_endpoints}")

    def test_all_endpoints_jwt_protected(self, api_tree):
        """Per user prefs: all API endpoints must have JWT auth via
        Depends(get_current_user)."""
        for node in ast.walk(api_tree):
            if isinstance(node, ast.FunctionDef):
                is_endpoint = any(
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"
                    and dec.func.attr in (
                        "get", "post", "put", "delete")
                    for dec in node.decorator_list)
                if not is_endpoint:
                    continue
                # Verify a Depends() call exists in defaults
                has_depends = any(
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Name)
                    and d.func.id == "Depends"
                    for d in node.args.defaults)
                assert has_depends, (
                    f"Endpoint {node.name} missing JWT auth "
                    f"(Depends(get_current_user))")

    def test_uses_get_current_user_auth(self, api_text):
        """Verify the JWT helper imported is the canonical one."""
        assert "from utils.auth_jwt import get_current_user" in api_text

    def test_pydantic_models_present(self, api_tree):
        """Verify request payloads use Pydantic for validation."""
        n_models = 0
        for node in ast.walk(api_tree):
            if isinstance(node, ast.ClassDef):
                if any(isinstance(b, ast.Name) and b.id == "BaseModel"
                       for b in node.bases):
                    n_models += 1
        assert n_models >= 10, (
            f"Expected ≥ 10 Pydantic models; found {n_models}")

    def test_meta_endpoint_present(self, api_text):
        """_meta endpoint helps React frontend with route discovery."""
        assert '/_meta' in api_text


# ─── Router mounted in utils/api.py ────────────────────────────────

class TestRouterMounted:

    def test_router_imported_in_api(self):
        api_text = (REPO_ROOT / "utils" / "api.py").read_text(
            encoding="utf-8")
        assert "from utils.api_strategy import router" in api_text, (
            "utils/api.py must import the Strategy router")

    def test_router_mounted_via_include_router(self):
        api_text = (REPO_ROOT / "utils" / "api.py").read_text(
            encoding="utf-8")
        # Look for include_router call near the strategy router
        assert ("strategy_router" in api_text
                and "include_router(strategy_router)" in api_text), (
            "Strategy router must be mounted via "
            "app.include_router(strategy_router)")


# ─── G146 audit gate ────────────────────────────────────────────────

class TestG146UIIntegrationGate:

    def test_g146_in_gates_list(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            gate_ids = [gid for gid, _ in audit.GATES]
        finally:
            sys.path.pop(0)
        assert "G146" in gate_ids, (
            "G146 strategy_arc_ui_integrated must be in GATES")

    def test_g146_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_strategy_arc_ui_integrated()
        finally:
            sys.path.pop(0)
        assert r["passed"], f"G146 failed: {r.get('violations')}"
        assert r["n_engines_imported"] == 15
        assert r["n_engines_expected"] == 15

    def test_g146_detects_missing_cockpit(self, monkeypatch, tmp_path):
        """Confidence test: gate fails when cockpit absent."""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            # Run from a tmp dir with no pages/
            monkeypatch.chdir(tmp_path)
            r = audit.gate_strategy_arc_ui_integrated()
            assert not r["passed"]
        finally:
            sys.path.pop(0)


# ─── Engine method existence (matches what cockpit calls) ──────────

class TestEngineMethodsExist:

    def test_all_called_engine_methods_exist(self):
        """Verify every engine method the cockpit calls actually exists.
        This catches refactor-induced drift between page and engine."""
        from utils.strategy_formulation import StrategyFormulationEngine
        from utils.strategic_options import StrategicOptionsGenerator
        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.initiative_portfolio import StrategicInitiativePortfolio
        from utils.enhanced_cascade import EnhancedCascadeEngine
        from utils.daily_strategy_integration import DailyStrategyIntegration
        from utils.gap_analyzer import StrategyGapAnalyzer
        from utils.corrective_actions import CorrectiveActionGenerator
        from utils.strategy_learning import StrategyLearningLoop
        from utils.stakeholder_engagement import StakeholderEngagementEngine
        from utils.strategy_health import StrategyHealthEngine
        from utils.strategy_simulator import StrategySimulator
        from utils.strategy_communication import StrategyCommunicationEngine
        from utils.sto_toolkit import STOToolkit
        from utils.strategy_roi import StrategyROIAnalytics

        method_map = [
            (StrategyFormulationEngine, "generate_swot"),
            (StrategicOptionsGenerator, "generate_options"),
            (StrategyDecompositionEngine, "define_strategic_pillars"),
            (StrategicInitiativePortfolio, "knapsack_optimize"),
            (StrategicInitiativePortfolio, "get_proposed_initiatives"),
            (EnhancedCascadeEngine, "cascade_with_engagement"),
            (DailyStrategyIntegration, "create_personal_strategy_scorecard"),
            (StrategyGapAnalyzer, "analyze_gaps"),
            (CorrectiveActionGenerator, "generate_corrective_actions"),
            (StrategyLearningLoop, "capture_lessons_learned"),
            (StakeholderEngagementEngine, "run_engagement_pulse"),
            (StakeholderEngagementEngine,
              "run_strategy_contribution_campaign"),
            (StrategyHealthEngine, "build_dashboard_payload"),
            (StrategySimulator, "simulate_resource_reallocation"),
            (StrategySimulator, "what_if_scenario"),
            (StrategyCommunicationEngine, "distribute_strategy_update"),
            (STOToolkit, "get_full_toolkit_payload"),
            (STOToolkit, "get_portfolio"),
            (STOToolkit, "get_strategy_risks"),
            (STOToolkit, "get_upcoming_reviews"),
            (STOToolkit, "get_strategy_analytics"),
            (STOToolkit, "get_meeting_minutes"),
            (STOToolkit, "get_strategy_training"),
            (STOToolkit, "generate_review_pack"),
            (StrategyROIAnalytics, "calculate_strategy_roi"),
        ]
        for cls, method in method_map:
            assert hasattr(cls, method), (
                f"{cls.__name__}.{method} expected by cockpit/API "
                f"but missing")


# ─── No regression ─────────────────────────────────────────────────

class TestNoRegression:

    def test_g144_still_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_qa_spec_complete()
        finally:
            sys.path.pop(0)
        assert r["passed"]

    def test_g145_still_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_strategy_module_closed()
        finally:
            sys.path.pop(0)
        assert r["passed"] and r["n_active"] == 15

    def test_g117_still_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_engine_hub_integration_coverage()
        finally:
            sys.path.pop(0)
        assert r["passed"]

    def test_all_15_strategy_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        for n in range(141, 156):
            sid = f"ENH-{n}"
            s = next(s for s in STANDARDS_REGISTRY
                      if s.standard_id == sid)
            assert s.status == "active"

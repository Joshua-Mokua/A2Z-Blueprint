"""Integration tests for v10.442 — HR engine FastAPI endpoints."""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# Endpoint URL presence
def test_v10442_peer_learning_endpoints():
    t = (REPO / "utils" / "api.py").read_text()
    assert '/api/v1/peer-learning/cards/{staff_code}' in t
    assert '/api/v1/peer-learning/generate-cards' in t
    assert '/api/v1/peer-learning/match-skill' in t


def test_v10442_coaching_endpoint():
    t = (REPO / "utils" / "api.py").read_text()
    assert '/api/v1/coaching/script' in t


def test_v10442_predict_endpoint():
    t = (REPO / "utils" / "api.py").read_text()
    assert '/api/v1/predict/{staff_code}' in t


def test_v10442_gamification_endpoints():
    t = (REPO / "utils" / "api.py").read_text()
    assert '/api/v1/gamification/badges/{staff_code}' in t
    assert '/api/v1/gamification/evaluate/{staff_code}' in t
    assert '/api/v1/gamification/leaderboard' in t


def test_v10442_efficiency_endpoint():
    t = (REPO / "utils" / "api.py").read_text()
    assert '/api/v1/efficiency/{staff_code}' in t


def test_v10442_wellness_endpoints():
    t = (REPO / "utils" / "api.py").read_text()
    assert '/api/v1/wellness/{staff_code}' in t
    assert '/api/v1/wellness/alerts/{manager_code}' in t


# Engine imports
def test_v10442_engine_imports():
    t = (REPO / "utils" / "api.py").read_text()
    for needed in (
        "from utils.peer_learning",
        "from utils.coaching_intelligence",
        "from utils.predictive_performance",
        "from utils.gamification",
        "from utils.efficiency",
        "from utils.wellness",
    ):
        assert needed in t, f"Missing: {needed}"


def test_v10442_api_syntax_valid():
    import ast
    ast.parse((REPO / "utils" / "api.py").read_text())


# All endpoints have auth
def test_v10442_all_new_endpoints_require_auth():
    """All new endpoints must use Depends(get_current_user)."""
    t = (REPO / "utils" / "api.py").read_text()
    # The text between hr-audit/dimension and entry point should have
    # 11 Depends(get_current_user) calls (one per new endpoint)
    # Or simpler: ensure no new endpoint skips auth
    import re
    # Find blocks for each new endpoint
    new_endpoints = [
        "peer_learning_cards_endpoint",
        "peer_learning_generate_endpoint",
        "peer_learning_match_endpoint",
        "coaching_script_endpoint",
        "predict_achievement_endpoint",
        "gamification_badges_endpoint",
        "gamification_evaluate_endpoint",
        "gamification_leaderboard_endpoint",
        "efficiency_endpoint",
        "wellness_assess_endpoint",
        "wellness_alerts_endpoint",
    ]
    for fn_name in new_endpoints:
        assert fn_name in t, f"Endpoint function {fn_name} not found"
        # Find the function block + check it has Depends(get_current_user)
        # somewhere in its signature (before the closing `):`)
        m = re.search(
            rf"def {fn_name}\(([\s\S]*?)\):", t,
        )
        assert m is not None, f"{fn_name} signature not found"
        signature = m.group(1)
        assert "Depends(get_current_user)" in signature, (
            f"{fn_name} signature missing get_current_user dependency"
        )


# HR audit reflects new state
def test_v10442_hr_api_coverage_100_pct():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_api_coverage
    api = audit_api_coverage()
    assert api.api_coverage_pct == 100.0


def test_v10442_hr_all_engines_have_api():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_api_coverage
    api = audit_api_coverage()
    for eng in (
        "peer_learning", "coaching_intelligence", "predictive_performance",
        "gamification", "efficiency", "wellness",
        "staff_onboarding_engine", "staff_exit_engine",
    ):
        assert eng in api.engines_with_api, f"{eng} not in engines_with_api"


def test_v10442_hr_health_above_85():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import hr_full_audit
    a = hr_full_audit()
    assert a.hr_health_pct >= 85.0


# Each engine has a callable handler
def test_v10442_handlers_callable():
    sys.path.insert(0, str(REPO))
    for k in list(sys.modules):
        if k.startswith("utils.api"):
            del sys.modules[k]
    import utils.api as api
    for handler_name in (
        "peer_learning_cards_endpoint",
        "peer_learning_generate_endpoint",
        "peer_learning_match_endpoint",
        "coaching_script_endpoint",
        "predict_achievement_endpoint",
        "gamification_badges_endpoint",
        "gamification_evaluate_endpoint",
        "gamification_leaderboard_endpoint",
        "efficiency_endpoint",
        "wellness_assess_endpoint",
        "wellness_alerts_endpoint",
    ):
        assert hasattr(api, handler_name), f"{handler_name} not in api module"
        assert callable(getattr(api, handler_name))


def test_v10442_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10442_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10442_g328_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10442_hr_engine_endpoints
    r = gate_v10442_hr_engine_endpoints()
    assert r["passed"], r.get("violations")

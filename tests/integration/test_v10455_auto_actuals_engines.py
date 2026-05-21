"""Integration tests for v10.455 — Module-Specific Auto-Actuals Engines.

3 new engines: credit (8 KPIs / 62.5%), admin (5/100%), bsc (5/100%).
Phase 5 rises significantly; avg health 66.8% → 69.3%.
"""

import ast
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def all_modules():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k or "cascade_bsc_360" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    return all_modules_audit()


# ── Engine files exist + parse ──────────────────────────────────────

def test_v10455_three_engines_exist():
    for f in ("credit_actuals_engine.py", "admin_actuals_engine.py",
              "bsc_cascade_actuals_engine.py"):
        assert (REPO / "utils" / f).exists(), f"Missing: {f}"


def test_v10455_engines_parse():
    for f in ("credit_actuals_engine.py", "admin_actuals_engine.py",
              "bsc_cascade_actuals_engine.py"):
        ast.parse((REPO / "utils" / f).read_text())


def test_v10455_engines_api_first():
    """Zero streamlit imports — engines must be API-first."""
    for f in ("credit_actuals_engine.py", "admin_actuals_engine.py",
              "bsc_cascade_actuals_engine.py"):
        text = (REPO / "utils" / f).read_text()
        assert "import streamlit" not in text, f"{f} imports streamlit"


def test_v10455_engines_have_required_api():
    for f in ("credit_actuals_engine.py", "admin_actuals_engine.py",
              "bsc_cascade_actuals_engine.py"):
        text = (REPO / "utils" / f).read_text()
        assert "def compute_kpi_actual" in text
        assert "def audit_auto_actuals_coverage" in text


def test_v10455_engines_have_kpi_registries():
    text = (REPO / "utils" / "credit_actuals_engine.py").read_text()
    assert "CREDIT_KPI_SOURCES" in text
    text = (REPO / "utils" / "admin_actuals_engine.py").read_text()
    assert "ADMIN_KPI_SOURCES" in text
    text = (REPO / "utils" / "bsc_cascade_actuals_engine.py").read_text()
    assert "BSC_KPI_SOURCES" in text


# ── Coverage from each engine ───────────────────────────────────────

def test_v10455_credit_coverage_50_plus():
    for k in list(sys.modules):
        if "credit_actuals_engine" in k:
            del sys.modules[k]
    from utils.credit_actuals_engine import audit_auto_actuals_coverage
    r = audit_auto_actuals_coverage()
    assert r.coverage_pct >= 50.0


def test_v10455_admin_coverage_full():
    for k in list(sys.modules):
        if "admin_actuals_engine" in k:
            del sys.modules[k]
    from utils.admin_actuals_engine import audit_auto_actuals_coverage
    r = audit_auto_actuals_coverage()
    assert r.coverage_pct == 100.0


def test_v10455_bsc_coverage_full():
    for k in list(sys.modules):
        if "bsc_cascade_actuals_engine" in k:
            del sys.modules[k]
    from utils.bsc_cascade_actuals_engine import audit_auto_actuals_coverage
    r = audit_auto_actuals_coverage()
    assert r.coverage_pct == 100.0


def test_v10455_credit_engine_returns_results():
    for k in list(sys.modules):
        if "credit_actuals_engine" in k:
            del sys.modules[k]
    from utils.credit_actuals_engine import compute_kpi_actual
    r = compute_kpi_actual(None, "K004", "2025-12")
    assert r is not None
    assert r.kpi_id == "K004"


def test_v10455_admin_engine_computes_rbac():
    for k in list(sys.modules):
        if "admin_actuals_engine" in k:
            del sys.modules[k]
    from utils.admin_actuals_engine import compute_kpi_actual
    r = compute_kpi_actual(None, "K_ADM_002", "2025-12")
    assert r.actual_value is not None
    assert 0 <= r.actual_value <= 100


def test_v10455_bsc_engine_computes_harmony():
    for k in list(sys.modules):
        if "bsc_cascade_actuals_engine" in k:
            del sys.modules[k]
    from utils.bsc_cascade_actuals_engine import compute_kpi_actual
    r = compute_kpi_actual(None, "K_BSC_004", "2025-12")
    assert r.actual_value == 100.0


# ── Health uplift ───────────────────────────────────────────────────

def test_v10455_admin_phase_5_rose(all_modules):
    """Admin P5 was 44.4%; should rise to 66.7%+ now."""
    assert all_modules.modules["admin"].phase_5.score_pct >= 66.0


def test_v10455_bsc_phase_5_rose(all_modules):
    """BSC P5 was 66.7%; should rise."""
    assert all_modules.modules["bsc_cascade"].phase_5.score_pct >= 80.0


def test_v10455_credit_phase_5_rose(all_modules):
    """Credit P5 was 66.7%; should rise."""
    assert all_modules.modules["credit"].phase_5.score_pct >= 80.0


def test_v10455_avg_health_above_67(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 67.0


def test_v10455_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


def test_v10455_cert_criteria_advancing(all_modules):
    """At least 2 modules have >=8 cert criteria met."""
    high_count = sum(1 for m in all_modules.modules.values()
                    if m.criteria_fully_met >= 8)
    assert high_count >= 2


# ── Upstream ────────────────────────────────────────────────────────

def test_v10455_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10455_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10455_g341_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10455_auto_actuals_engines
    r = gate_v10455_auto_actuals_engines()
    assert r["passed"], r.get("violations")

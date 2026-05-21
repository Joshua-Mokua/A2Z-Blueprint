"""Integration tests for v10.450 — Credit 360 Review + HR 360 Fixes.

Per Joshua pushback: 84.8% was partial. 360 review per doctrine adds
6 new audit dimensions surfacing honest gaps. Honest credit health: 55.5%.
"""

import ast
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def credit_audit_360():
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import credit_full_audit
    return credit_full_audit()


# ── 6 new audit dimensions present (fast) ────────────────────────────

def test_v10450_six_new_audit_functions_present():
    text = (REPO / "utils/credit_section_audit_engine.py").read_text()
    for fn in (
        "def audit_api_coverage",
        "def audit_react_readiness",
        "def audit_postgres_backing",
        "def audit_staff_completeness",
        "def audit_bsc_actuals_wiring",
        "def audit_tab_functionality",
    ):
        assert fn in text, f"Missing audit function: {fn}"


def test_v10450_six_new_dataclasses_present():
    text = (REPO / "utils/credit_section_audit_engine.py").read_text()
    for dc in (
        "class APICoverageAudit",
        "class ReactReadinessAudit",
        "class PostgresBackingAudit",
        "class StaffCompletenessAudit",
        "class BSCActualsWiringAudit",
        "class TabFunctionalityAudit",
    ):
        assert dc in text, f"Missing dataclass: {dc}"


# ── Honest credit health (slow — uses fixture) ───────────────────────

def test_v10450_credit_health_honest_below_75(credit_audit_360):
    """Honest 360 review: must be < 75% (was claimed 84.8% partial)."""
    assert credit_audit_360.credit_health_pct < 75.0, (
        f"Health = {credit_audit_360.credit_health_pct}%, should be < 75% "
        f"with API + BSC actuals at 0%"
    )


def test_v10450_two_critical_findings(credit_audit_360):
    """API + BSC actuals both at 0% = 2 critical findings."""
    assert credit_audit_360.severity_counts.get("critical", 0) >= 2


def test_v10450_api_coverage_zero(credit_audit_360):
    """No credit engines have API endpoints yet."""
    assert credit_audit_360.api_coverage is not None
    assert credit_audit_360.api_coverage.api_coverage_pct < 20.0


def test_v10450_bsc_actuals_zero(credit_audit_360):
    """No credit KPIs auto-populate yet."""
    assert credit_audit_360.bsc_actuals_wiring is not None
    assert credit_audit_360.bsc_actuals_wiring.actuals_auto_pct < 20.0


def test_v10450_staff_completeness_low(credit_audit_360):
    """Only 3 of 12 expected credit roles in cascade = ~25%."""
    assert credit_audit_360.staff_completeness is not None
    assert credit_audit_360.staff_completeness.staff_completeness_pct < 50.0
    # But reporting lines should be intact (Chief Credit → Manager exists)
    assert credit_audit_360.staff_completeness.reporting_lines_intact


def test_v10450_react_readiness_high(credit_audit_360):
    """13 of 14 pages clean."""
    assert credit_audit_360.react_readiness is not None
    assert credit_audit_360.react_readiness.react_readiness_pct >= 80.0


def test_v10450_tab_functionality_100(credit_audit_360):
    """All 14 pages parse + imports resolve."""
    assert credit_audit_360.tab_functionality is not None
    assert credit_audit_360.tab_functionality.functional_pct == 100.0


def test_v10450_rescue_priorities_include_phase_5(credit_audit_360):
    """The biggest gap — BSC actuals — must be a top priority."""
    priorities_text = " ".join(credit_audit_360.rescue_priorities).lower()
    assert "credit_actuals_engine" in priorities_text or "phase 5" in priorities_text
    assert "fastapi" in priorities_text or "phase 3" in priorities_text


# ── HR 360 fixes ─────────────────────────────────────────────────────

def test_v10450_hr_360_has_role_aware_welcome():
    t = (REPO / "pages/81_chief_hr_centre.py").read_text()
    assert "_resolve_chief_hr" in t
    assert "Chief Human Resources Officer" in t
    assert "Viewing as" in t
    assert "_is_chief_hr" in t


def test_v10450_hr_360_has_staff_performance_tab():
    t = (REPO / "pages/81_chief_hr_centre.py").read_text()
    assert "🎯 My Staff Performance" in t
    assert "HR-dept staff" in t
    assert "Performance band distribution" in t


def test_v10450_hr_360_tab_count_seven():
    """6 → 7 tabs after Staff Performance insertion."""
    t = (REPO / "pages/81_chief_hr_centre.py").read_text()
    # Count tab labels in the st.tabs([...]) call
    tab_count = (
        t.count("👥 People Overview") +
        t.count("🎯 My Staff Performance") +
        t.count("📊 HR KPI Auto-Actuals") +
        t.count("🎓 Training & Development") +
        t.count("📋 Performance Programs") +
        t.count("🆕 Onboarding & Exit Risk") +
        t.count("💰 Financial Snapshot")
    )
    assert tab_count >= 7, f"Tab labels found: {tab_count}"


def test_v10450_hr_360_parses():
    ast.parse((REPO / "pages/81_chief_hr_centre.py").read_text())


# ── Backups + upstream ───────────────────────────────────────────────

def test_v10450_backups_present():
    bdir = REPO / "data" / "_v10450_backups"
    assert bdir.exists()
    for f in ("81_chief_hr_centre.py.before",
              "credit_section_audit_engine.py.before"):
        assert (bdir / f).exists(), f"Missing backup: {f}"


def test_v10450_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10450_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10450_g336_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10450_credit_360_review
    r = gate_v10450_credit_360_review()
    assert r["passed"], r.get("violations")

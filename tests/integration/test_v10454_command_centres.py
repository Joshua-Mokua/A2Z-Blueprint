"""Integration tests for v10.454 — Command Centre Construction (Phase 6).

NEW Chief Credit Centre + enhanced HR/BSC/Admin centres → Phase 6 = 100% for all 4 modules.
Avg health: 61.9% → 66.8% (+4.9pp). Crisis: 1 → 0.
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


# ── NEW Chief Credit Centre ─────────────────────────────────────────

def test_v10454_chief_credit_centre_exists():
    assert (REPO / "pages" / "85_chief_credit_centre.py").exists()


def test_v10454_chief_credit_centre_parses():
    ast.parse((REPO / "pages" / "85_chief_credit_centre.py").read_text())


def test_v10454_chief_credit_centre_six_tabs():
    t = (REPO / "pages" / "85_chief_credit_centre.py").read_text()
    for tab in ("Executive Visibility", "Strategic Intelligence",
                "Organ Health", "My Staff Performance",
                "Risk Indicators", "Real-Time"):
        assert tab in t, f"Missing tab: {tab}"


def test_v10454_chief_credit_centre_all_doctrine_keywords():
    t = (REPO / "pages" / "85_chief_credit_centre.py").read_text().lower()
    for kw in ("st.metric", "trend", "forecast", "health", "real-time",
               "live", "sla", "breach", "staff_performance"):
        assert kw in t, f"Missing keyword: {kw}"


# ── Enhanced HR Centre ──────────────────────────────────────────────

def test_v10454_hr_centre_has_strategic_intelligence():
    t = (REPO / "pages" / "81_chief_hr_centre.py").read_text().lower()
    for kw in ("trend", "forecast", "health", "real-time", "sla", "breach"):
        assert kw in t, f"HR Centre missing keyword: {kw}"


# ── Enhanced BSC Centre (1_perform) ─────────────────────────────────

def test_v10454_perform_centre_has_strategic_intelligence():
    t = (REPO / "pages" / "1_perform.py").read_text().lower()
    for kw in ("trend", "forecast", "health", "real-time", "sla",
               "breach", "staff_performance"):
        assert kw in t, f"1_perform missing keyword: {kw}"


def test_v10454_perform_centre_parses():
    ast.parse((REPO / "pages" / "1_perform.py").read_text())


# ── Admin Centre ────────────────────────────────────────────────────

def test_v10454_admin_centre_has_staff_performance_ref():
    t = (REPO / "pages" / "7_admin.py").read_text().lower()
    assert "staff_performance" in t


# ── Phase 6 = 100% for all ──────────────────────────────────────────

def test_v10454_admin_phase_6_full(all_modules):
    assert all_modules.modules["admin"].phase_6.score_pct == 100.0


def test_v10454_hr_phase_6_full(all_modules):
    assert all_modules.modules["hr"].phase_6.score_pct == 100.0


def test_v10454_bsc_phase_6_full(all_modules):
    assert all_modules.modules["bsc_cascade"].phase_6.score_pct == 100.0


def test_v10454_credit_phase_6_full(all_modules):
    assert all_modules.modules["credit"].phase_6.score_pct == 100.0


# ── Aggregate health improvements ───────────────────────────────────

def test_v10454_avg_health_above_65(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 65.0


def test_v10454_no_crisis_modules(all_modules):
    """All modules above 50% now."""
    assert len(all_modules.crisis_modules) == 0


def test_v10454_credit_above_50(all_modules):
    """Credit crossed the 50% threshold."""
    assert all_modules.modules["credit"].doctrine_health_pct >= 50.0


def test_v10454_each_module_certification_progressed(all_modules):
    """Each module has at least 4 of 14 cert criteria met."""
    for key, m in all_modules.modules.items():
        assert m.criteria_fully_met >= 4, (
            f"{key} has only {m.criteria_fully_met}/14 criteria"
        )


# ── Upstream preserved ──────────────────────────────────────────────

def test_v10454_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10454_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10454_g340_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10454_command_centres
    r = gate_v10454_command_centres()
    assert r["passed"], r.get("violations")


# ── Backups ─────────────────────────────────────────────────────────

def test_v10454_backups_present():
    bdir = REPO / "data" / "_v10454_backups"
    assert bdir.exists()
    for f in ("81_chief_hr_centre.py.before", "1_perform.py.before",
              "7_admin.py.before"):
        assert (bdir / f).exists(), f"Backup missing: {f}"

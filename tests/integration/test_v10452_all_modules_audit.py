"""Integration tests for v10.452 — All-Modules Honest Doctrine Audit.

Per Joshua: do the same tests for modules stated as complete.
Result: ALL 4 modules below 60% honest health.
"""

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


# ── Engine structure (fast) ─────────────────────────────────────────

def test_v10452_engine_exists():
    assert (REPO / "utils" / "module_doctrine_audit.py").exists()


def test_v10452_module_registry_has_4_modules():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    for key in ('"admin"', '"hr"', '"bsc_cascade"', '"credit"'):
        assert key in text, f"Missing MODULE_REGISTRY key: {key}"


def test_v10452_dataclasses_present():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    for dc in ("class ModuleConfig", "class PhaseScore",
               "class ModuleDoctrineHealth", "class AllModulesAudit"):
        assert dc in text, f"Missing: {dc}"


def test_v10452_eight_phase_functions():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    for fn in (f"def _phase_{i}" for i in range(1, 9)):
        assert fn in text, f"Missing: {fn}"


def test_v10452_audit_function_signatures():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    for fn in ("def _final_validation", "def _vital_signs",
               "def _diagnostic_principles",
               "def audit_module", "def all_modules_audit"):
        assert fn in text, f"Missing: {fn}"


# ── Honest health revelations (slow — uses fixture) ─────────────────

def test_v10452_all_4_modules_audited(all_modules):
    assert len(all_modules.modules) == 4
    for key in ("admin", "hr", "bsc_cascade", "credit"):
        assert key in all_modules.modules


def test_v10452_admin_below_60(all_modules):
    """Admin claimed 100%, honest must be <60%."""
    assert all_modules.modules["admin"].doctrine_health_pct < 60.0


def test_v10452_hr_below_60(all_modules):
    """HR claimed 88.7%, honest must be <60%."""
    assert all_modules.modules["hr"].doctrine_health_pct < 60.0


def test_v10452_bsc_cascade_below_60(all_modules):
    """BSC claimed 100%, honest must be <60%."""
    assert all_modules.modules["bsc_cascade"].doctrine_health_pct < 60.0


def test_v10452_credit_below_60(all_modules):
    """Credit honest must be <60%."""
    assert all_modules.modules["credit"].doctrine_health_pct < 60.0


def test_v10452_none_certified(all_modules):
    """No module has all 14 final validation criteria met."""
    assert all_modules.certified_count == 0
    for key, m in all_modules.modules.items():
        assert m.certified is False
        assert m.criteria_fully_met < 14


def test_v10452_avg_honesty_gap_big(all_modules):
    """Average honesty gap (claimed vs honest) >=20pp shows systemic over-claim."""
    assert all_modules.avg_honesty_gap_pp >= 20.0


def test_v10452_at_least_3_crisis_modules(all_modules):
    """3 of 4 modules at <50% honest health."""
    assert len(all_modules.crisis_modules) >= 3


def test_v10452_each_module_has_all_audit_components(all_modules):
    """Every module has 8 phases + final_validation + vital_signs + diagnostic."""
    for key, m in all_modules.modules.items():
        for phase_attr in ("phase_1", "phase_2", "phase_3", "phase_4",
                          "phase_5", "phase_6", "phase_7", "phase_8"):
            phase = getattr(m, phase_attr)
            assert phase is not None
            assert len(phase.sub_criteria) >= 4
        assert m.final_validation_pct is not None
        assert m.vital_signs_pct is not None
        assert m.diagnostic_pct is not None


# ── Upstream preserved ──────────────────────────────────────────────

def test_v10452_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10452_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10452_g338_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10452_all_modules_honest_audit
    r = gate_v10452_all_modules_honest_audit()
    assert r["passed"], r.get("violations")

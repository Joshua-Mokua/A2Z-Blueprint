"""Integration tests for v10.467 — Phase 5 BSC Actuals Deepening.

Per Joshua continue + v10.466 roadmap. Closes Phase 5 (the last big
phase gap before final cert). 4-stream attack:
  1. Added 10 new KPIs to kpi_library.json
  2. Built 9 new actuals engines (one per organ that lacked one)
  3. Broadened HR engine coverage from 38% to 100%
  4. Wired BSC triggers in 130_head_analytics_centre

Avg health: 84.0% → 86.4% (+2.4pp). Phase 5 = 88.9% across all 13.
All 13 organs at ≥10/14 cert.
"""

import ast
import json
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


# ── 9 NEW ACTUALS ENGINES ────────────────────────────────────────────

@pytest.mark.parametrize("engine_name", [
    "ict_actuals_engine.py", "finance_actuals_engine.py",
    "treasury_actuals_engine.py", "legal_actuals_engine.py",
    "risk_actuals_engine.py", "compliance_actuals_engine.py",
    "operations_actuals_engine.py", "crm_actuals_engine.py",
    "reporting_analytics_actuals_engine.py",
])
def test_v10467_new_engine_exists_and_parses(engine_name):
    path = REPO / "utils" / engine_name
    assert path.exists(), f"Missing: {engine_name}"
    ast.parse(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("engine_name", [
    "ict_actuals_engine.py", "finance_actuals_engine.py",
    "treasury_actuals_engine.py", "legal_actuals_engine.py",
    "risk_actuals_engine.py", "compliance_actuals_engine.py",
    "operations_actuals_engine.py", "crm_actuals_engine.py",
    "reporting_analytics_actuals_engine.py",
])
def test_v10467_engine_has_required_apis(engine_name):
    text = (REPO / "utils" / engine_name).read_text()
    for required in ("compute_all_actuals", "AUTO_ACTUAL_KEYWORDS",
                    "auto_actual_coverage", "trigger_kpi"):
        assert required in text, f"{engine_name} missing {required}"


@pytest.mark.parametrize("engine_name", [
    "ict_actuals_engine.py", "finance_actuals_engine.py",
    "treasury_actuals_engine.py", "legal_actuals_engine.py",
    "risk_actuals_engine.py", "compliance_actuals_engine.py",
    "operations_actuals_engine.py", "crm_actuals_engine.py",
    "reporting_analytics_actuals_engine.py",
])
def test_v10467_engine_has_bsc_triggers(engine_name):
    text = (REPO / "utils" / engine_name).read_text()
    triggers = text.count("def _bsc_trigger_")
    assert triggers >= 4, f"{engine_name} has {triggers} _bsc_trigger_*; need >=4"


# ── KPI LIBRARY ADDITIONS ────────────────────────────────────────────

def test_v10467_kpi_library_has_metadata():
    kpi = json.loads((REPO/"data"/"kpi_library.json").read_text(encoding="utf-8"))
    assert "_v10467_kpi_additions" in kpi


def test_v10467_kpi_library_has_10_additions():
    kpi = json.loads((REPO/"data"/"kpi_library.json").read_text(encoding="utf-8"))
    added = kpi["_v10467_kpi_additions"]["_added_kpi_codes"]
    assert len(added) >= 10


@pytest.mark.parametrize("kpi_id", [
    "K215", "K216",  # Pipeline staff productivity
    "K230", "K231", "K232", "K233", "K234",  # reporting_analytics
    "K235", "K236", "K237",
])
def test_v10467_kpi_id_added(kpi_id):
    kpi = json.loads((REPO/"data"/"kpi_library.json").read_text(encoding="utf-8"))
    added = kpi["_v10467_kpi_additions"]["_added_kpi_codes"]
    assert kpi_id in added


# ── HR ENGINE BROADENED ──────────────────────────────────────────────

@pytest.mark.parametrize("keyword", [
    "wellness", "attrition", "engagement", "recruit", "onboarding"
])
def test_v10467_hr_engine_has_keyword(keyword):
    text = (REPO/"utils"/"hr_actuals_engine.py").read_text().lower()
    assert keyword in text


# ── 130 CENTRE BSC TRIGGER WIRING ────────────────────────────────────

def test_v10467_130_centre_imports_engine():
    text = (REPO/"pages"/"130_head_analytics_centre.py").read_text()
    assert "reporting_analytics_actuals_engine" in text


def test_v10467_130_centre_has_3plus_trigger_kpi():
    text = (REPO/"pages"/"130_head_analytics_centre.py").read_text()
    assert text.count("trigger_kpi") >= 3


# ── PHASE 5 = 88.9% ALL 13 ORGANS ────────────────────────────────────

@pytest.mark.parametrize("organ", [
    "admin", "hr", "bsc_cascade", "credit", "ict",
    "finance", "treasury", "legal", "risk", "compliance",
    "operations", "crm", "reporting_analytics",
])
def test_v10467_phase_5_above_80_for_organ(all_modules, organ):
    assert all_modules.modules[organ].phase_5.score_pct >= 80.0


# ── HEALTH UPLIFT ────────────────────────────────────────────────────

def test_v10467_avg_health_above_85(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 85.0


def test_v10467_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


def test_v10467_all_13_organs_at_10_cert(all_modules):
    low = [k for k, m in all_modules.modules.items() if m.criteria_fully_met < 10]
    assert not low, f"Organs below 10 cert: {low}"


def test_v10467_at_least_5_organs_at_11_cert(all_modules):
    high = sum(1 for m in all_modules.modules.values() if m.criteria_fully_met >= 11)
    assert high >= 5


# ── NO REGRESSION ────────────────────────────────────────────────────

def test_v10467_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10467_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10467_phase_4_preserved_for_mature_organs(all_modules):
    for organ in ("admin","hr","credit","ict","finance","compliance"):
        assert all_modules.modules[organ].phase_4.score_pct >= 100.0


def test_v10467_zero_orphan_pages():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    all_pgs = sorted([p.name for p in (REPO/"pages").glob("*.py")
                     if not p.name.startswith("_")])
    claimed = set()
    for cfg in MODULE_REGISTRY.values():
        claimed.update(cfg.pages)
    assert [p for p in all_pgs if p not in claimed] == []


def test_v10467_g353_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10467_phase_5_bsc_actuals_deepening
    r = gate_v10467_phase_5_bsc_actuals_deepening()
    assert r["passed"], r.get("violations")


# ── ENGINE FUNCTIONAL SMOKE TESTS ────────────────────────────────────

@pytest.mark.parametrize("module_name,key", [
    ("utils.ict_actuals_engine", "ict"),
    ("utils.finance_actuals_engine", "finance"),
    ("utils.treasury_actuals_engine", "treasury"),
    ("utils.legal_actuals_engine", "legal"),
    ("utils.risk_actuals_engine", "risk"),
    ("utils.compliance_actuals_engine", "compliance"),
    ("utils.operations_actuals_engine", "operations"),
    ("utils.crm_actuals_engine", "crm"),
    ("utils.reporting_analytics_actuals_engine", "reporting_analytics"),
])
def test_v10467_engine_compute_all_actuals_runs(module_name, key):
    """Smoke test - engine.compute_all_actuals() returns >=4 ActualValues."""
    for k in list(sys.modules):
        if module_name.split(".")[-1] in k:
            del sys.modules[k]
    mod = __import__(module_name, fromlist=["compute_all_actuals"])
    results = mod.compute_all_actuals()
    assert len(results) >= 4, f"{module_name} compute_all_actuals returned {len(results)}"


@pytest.mark.parametrize("module_name", [
    "utils.ict_actuals_engine",
    "utils.finance_actuals_engine",
    "utils.treasury_actuals_engine",
    "utils.legal_actuals_engine",
    "utils.risk_actuals_engine",
    "utils.compliance_actuals_engine",
    "utils.operations_actuals_engine",
    "utils.crm_actuals_engine",
    "utils.reporting_analytics_actuals_engine",
])
def test_v10467_engine_coverage_100pct(module_name):
    """Each engine claims 100% AUTO_ACTUAL_KEYWORDS coverage."""
    for k in list(sys.modules):
        if module_name.split(".")[-1] in k:
            del sys.modules[k]
    mod = __import__(module_name, fromlist=["auto_actual_coverage"])
    cov = mod.auto_actual_coverage()
    assert cov["coverage_pct"] == 100.0

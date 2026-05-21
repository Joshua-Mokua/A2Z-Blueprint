"""Integration tests for v10.458 — Stress Test Harness + Scalability Validator.

Closes Final Validation criteria #10 (stress testing) + #14 (capacity plan)
for all 5 organs. Avg health 68.9% → 74.3% (+5.4pp).
"""

import ast
import re
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


# ── Stress harness ──────────────────────────────────────────────────

def test_v10458_stress_harness_exists():
    assert (REPO / "utils" / "stress_test_harness.py").exists()


def test_v10458_stress_harness_parses():
    ast.parse((REPO / "utils" / "stress_test_harness.py").read_text())


def test_v10458_stress_harness_api_first():
    text = (REPO / "utils" / "stress_test_harness.py").read_text()
    assert "import streamlit" not in text


def test_v10458_stress_harness_full_api():
    text = (REPO / "utils" / "stress_test_harness.py").read_text()
    for fn in ("STRESS_TEST_SCENARIOS",
               "def run_stress_test",
               "def run_full_stress_suite",
               "def benchmark_module",
               "def load_test_module",
               "def audit_stress_coverage",
               "class StressTestResult",
               "class BenchmarkReport",
               "class LoadTestReport"):
        assert fn in text, f"Missing: {fn}"


def test_v10458_stress_scenarios_thirteen():
    for k in list(sys.modules):
        if "stress_test_harness" in k:
            del sys.modules[k]
    from utils.stress_test_harness import STRESS_TEST_SCENARIOS
    assert len(STRESS_TEST_SCENARIOS) >= 13


def test_v10458_stress_runs_for_each_module():
    for k in list(sys.modules):
        if "stress_test_harness" in k:
            del sys.modules[k]
    from utils.stress_test_harness import run_full_stress_suite
    for module in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        results = run_full_stress_suite(module)
        assert len(results) >= 13
        assert all(r.module_key == module for r in results)


# ── Scalability validator ───────────────────────────────────────────

def test_v10458_scalability_validator_exists():
    assert (REPO / "utils" / "scalability_validator.py").exists()


def test_v10458_scalability_validator_parses():
    ast.parse((REPO / "utils" / "scalability_validator.py").read_text())


def test_v10458_scalability_api_first():
    text = (REPO / "utils" / "scalability_validator.py").read_text()
    assert "import streamlit" not in text


def test_v10458_scalability_full_api():
    text = (REPO / "utils" / "scalability_validator.py").read_text()
    for fn in ("SCALE_DIMENSIONS",
               "BANK_SIZE_TIERS",
               "def validate_horizontal_scale",
               "def generate_capacity_plan",
               "def project_5year_capacity",
               "def audit_scalability_coverage",
               "class ScaleReadinessReport",
               "class CapacityPlan"):
        assert fn in text, f"Missing: {fn}"


def test_v10458_eight_scale_dimensions():
    for k in list(sys.modules):
        if "scalability_validator" in k:
            del sys.modules[k]
    from utils.scalability_validator import SCALE_DIMENSIONS
    assert len(SCALE_DIMENSIONS) == 8


def test_v10458_four_bank_tiers():
    for k in list(sys.modules):
        if "scalability_validator" in k:
            del sys.modules[k]
    from utils.scalability_validator import BANK_SIZE_TIERS
    assert "current" in BANK_SIZE_TIERS
    assert "year_5_5x" in BANK_SIZE_TIERS
    assert "peak_10x" in BANK_SIZE_TIERS


def test_v10458_capacity_plan_5year():
    for k in list(sys.modules):
        if "scalability_validator" in k:
            del sys.modules[k]
    from utils.scalability_validator import project_5year_capacity
    proj = project_5year_capacity("credit")
    assert "current" in proj.plans
    assert "year_5_5x" in proj.plans
    assert proj.plans["year_5_5x"].customers == 3_500_000


# ── Criteria #10 + #14 met per module ───────────────────────────────

def test_v10458_admin_meets_stress_keywords():
    text = (REPO / "pages" / "7_admin.py").read_text().lower()
    assert re.search(r"stress_test|load_test|benchmark", text)
    assert re.search(r"horizontal_scale|capacity_plan", text)


def test_v10458_hr_centre_meets_stress_keywords():
    text = (REPO / "pages" / "81_chief_hr_centre.py").read_text().lower()
    assert re.search(r"stress_test|load_test|benchmark", text)
    assert re.search(r"horizontal_scale|capacity_plan", text)


def test_v10458_bsc_centre_meets_stress_keywords():
    text = (REPO / "pages" / "1_perform.py").read_text().lower()
    assert re.search(r"stress_test|load_test|benchmark", text)
    assert re.search(r"horizontal_scale|capacity_plan", text)


def test_v10458_credit_centre_meets_stress_keywords():
    text = (REPO / "pages" / "85_chief_credit_centre.py").read_text().lower()
    assert re.search(r"stress_test|load_test|benchmark", text)
    assert re.search(r"horizontal_scale|capacity_plan", text)


def test_v10458_ict_centre_meets_stress_keywords():
    text = (REPO / "pages" / "98_platform_health.py").read_text().lower()
    assert re.search(r"stress_test|load_test|benchmark", text)
    assert re.search(r"horizontal_scale|capacity_plan", text)


# ── Phase 8 stress docs ─────────────────────────────────────────────

def test_v10458_stress_docs_generated():
    for m in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        for d in ("stress_volume", "stress_users"):
            assert (REPO / "docs" / f"{m}_{d}.md").exists()


# ── Health uplift ───────────────────────────────────────────────────

def test_v10458_avg_health_above_72(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 72.0


def test_v10458_credit_jumped(all_modules):
    """Credit was 60.3%; should rise materially with stress + scale."""
    assert all_modules.modules["credit"].doctrine_health_pct >= 70.0


def test_v10458_one_module_at_11_cert(all_modules):
    """HR should reach 11/14 cert criteria."""
    high = max(m.criteria_fully_met for m in all_modules.modules.values())
    assert high >= 11


def test_v10458_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


# ── Upstream ────────────────────────────────────────────────────────

def test_v10458_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10458_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10458_g344_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10458_stress_scalability
    r = gate_v10458_stress_scalability()
    assert r["passed"], r.get("violations")

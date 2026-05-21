"""Integration tests for v10.456 — Flexcube Integration Readiness Facade + ICT as Lungs.

Discovers + wraps the 1,729 LOC existing Flexcube adapter via a thin facade.
Adds ICT as the 5th organ (Lungs per Document 2 organ analogy).
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


# ── Facade exists + correct API ─────────────────────────────────────

def test_v10456_facade_exists():
    assert (REPO / "utils" / "flexcube_integration_readiness.py").exists()


def test_v10456_facade_parses():
    ast.parse((REPO / "utils" / "flexcube_integration_readiness.py").read_text())


def test_v10456_facade_api_first():
    """Zero streamlit imports."""
    text = (REPO / "utils" / "flexcube_integration_readiness.py").read_text()
    assert "import streamlit" not in text


def test_v10456_facade_has_full_api():
    text = (REPO / "utils" / "flexcube_integration_readiness.py").read_text()
    for fn in ("DOMAIN_FETCHERS",
               "def probe_flexcube_readiness",
               "def declare_flexcube_ready",
               "def get_integration_status",
               "def get_data_source_for",
               "def audit_integration_coverage",
               "class ReadinessReport",
               "class IntegrationCoverageAudit"):
        assert fn in text, f"Missing: {fn}"


def test_v10456_facade_seven_domains():
    text = (REPO / "utils" / "flexcube_integration_readiness.py").read_text()
    for d in ("credit", "customer", "deposits", "branch",
              "staff", "treasury", "risk"):
        assert f'"{d}"' in text, f"Missing domain: {d}"


# ── Facade returns expected readiness ───────────────────────────────

def test_v10456_facade_readiness_high():
    for k in list(sys.modules):
        if "flexcube_integration_readiness" in k:
            del sys.modules[k]
    from utils.flexcube_integration_readiness import probe_flexcube_readiness
    rpt = probe_flexcube_readiness()
    assert rpt.integration_score_pct >= 80.0
    assert rpt.adapter_present is True
    assert rpt.adapter_loc >= 500
    assert rpt.fetcher_count >= 10
    assert rpt.virtual_bank_test_harness_present is True


def test_v10456_facade_declare_returns_plan():
    for k in list(sys.modules):
        if "flexcube_integration_readiness" in k:
            del sys.modules[k]
    from utils.flexcube_integration_readiness import declare_flexcube_ready
    plan = declare_flexcube_ready("credit",
                                  ["credit", "customer", "branch"])
    assert plan["module"] == "credit"
    assert plan["ready"] is True
    assert "sources" in plan


def test_v10456_domain_coverage_full():
    for k in list(sys.modules):
        if "flexcube_integration_readiness" in k:
            del sys.modules[k]
    from utils.flexcube_integration_readiness import audit_integration_coverage
    cov = audit_integration_coverage()
    assert cov.coverage_pct >= 80.0


# ── ICT as 5th organ (Lungs) ────────────────────────────────────────

def test_v10456_ict_in_registry():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    assert '"ict"' in text


def test_v10456_ict_organ_role_lungs():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    assert "Lungs" in text


def test_v10456_ict_super_user_role():
    text = (REPO / "utils" / "module_doctrine_audit.py").read_text()
    assert "ICT Super User" in text


def test_v10456_registry_has_5_modules(all_modules):
    assert len(all_modules.modules) == 5
    for key in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        assert key in all_modules.modules


def test_v10456_ict_health_above_55(all_modules):
    """ICT after docs should be 55%+."""
    assert all_modules.modules["ict"].doctrine_health_pct >= 55.0


def test_v10456_ict_phase_1_high(all_modules):
    """ICT docs were generated; Phase 1 should be >=80%."""
    assert all_modules.modules["ict"].phase_1.score_pct >= 80.0


# ── Module centres reference flexcube ───────────────────────────────

def test_v10456_credit_centre_imports_facade():
    text = (REPO / "pages" / "85_chief_credit_centre.py").read_text()
    assert "flexcube_integration_readiness" in text or \
           "declare_flexcube_ready" in text


def test_v10456_hr_centre_imports_facade():
    text = (REPO / "pages" / "81_chief_hr_centre.py").read_text()
    assert "flexcube_integration_readiness" in text


def test_v10456_perform_centre_imports_facade():
    text = (REPO / "pages" / "1_perform.py").read_text()
    assert "flexcube_integration_readiness" in text


def test_v10456_centres_parse():
    for f in ("85_chief_credit_centre.py", "81_chief_hr_centre.py",
              "1_perform.py"):
        ast.parse((REPO / "pages" / f).read_text())


# ── Aggregate ───────────────────────────────────────────────────────

def test_v10456_avg_health_above_65(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 65.0


def test_v10456_zero_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


def test_v10456_each_phase_3_flexcube_credit():
    """Each non-ICT module's Phase 3 includes Flexcube ref now."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    a = all_modules_audit()
    # At least Admin (had it) + HR/BSC/Credit (via facade imports) should now pass EC1
    flexcube_passing = 0
    for key, m in a.modules.items():
        if key == "ict":
            continue  # ICT explicitly counts flexcube engines
        # Find EC1 in P3 sub_criteria
        for sub in m.phase_3.sub_criteria:
            if "Flexcube" in sub.get("c", "") and sub.get("met"):
                flexcube_passing += 1
                break
    assert flexcube_passing >= 3, f"Only {flexcube_passing}/4 modules have Flexcube ref"


# ── Upstream ────────────────────────────────────────────────────────

def test_v10456_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10456_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10456_g342_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10456_flexcube_facade_ict_lungs
    r = gate_v10456_flexcube_facade_ict_lungs()
    assert r["passed"], r.get("violations")

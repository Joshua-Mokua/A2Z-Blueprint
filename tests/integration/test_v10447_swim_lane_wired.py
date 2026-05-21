"""Integration tests for v10.447 — Credit Phase 2: SWIM LANE wired."""

import ast
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def credit_audit_post_wiring():
    for k in list(sys.modules):
        if "credit_section_audit_engine" in k:
            del sys.modules[k]
    from utils.credit_section_audit_engine import credit_full_audit
    return credit_full_audit()


# ── Page-level wiring tests (fast) ────────────────────────────────────

def test_v10447_21_imports_workflow():
    t = (REPO / "pages/21_loan_applications.py").read_text()
    assert "from utils.credit_workflow import" in t


def test_v10447_22_imports_workflow():
    t = (REPO / "pages/22_credit_analysis.py").read_text()
    assert "from utils.credit_workflow import" in t


def test_v10447_23_imports_workflow():
    t = (REPO / "pages/23_credit_admin.py").read_text()
    assert "from utils.credit_workflow import" in t


def test_v10447_21_parses():
    ast.parse((REPO / "pages/21_loan_applications.py").read_text())


def test_v10447_22_parses():
    ast.parse((REPO / "pages/22_credit_analysis.py").read_text())


def test_v10447_23_parses():
    ast.parse((REPO / "pages/23_credit_admin.py").read_text())


def test_v10447_21_has_workflow_tab():
    t = (REPO / "pages/21_loan_applications.py").read_text()
    assert "Workflow Lifecycle" in t
    assert "ApplicationState" in t
    assert "ALLOWED_TRANSITIONS" in t
    assert "evaluate_automation" in t
    assert "determine_tier" in t


def test_v10447_22_has_workflow_context():
    t = (REPO / "pages/22_credit_analysis.py").read_text()
    assert "Awaiting committee" in t
    assert "Committee queue" in t
    assert "determine_tier" in t


def test_v10447_23_has_workflow_lifecycle():
    t = (REPO / "pages/23_credit_admin.py").read_text()
    assert "Workflow position" in t
    assert "DOCUMENTATION_PENDING" in t
    assert "Swim Lane" in t


def test_v10447_backups_created():
    bdir = REPO / "data/_v10447_backups"
    assert bdir.exists()
    for f in ("21_loan_applications.py.before",
              "22_credit_analysis.py.before",
              "23_credit_admin.py.before",
              "_manifest.json.before"):
        assert (bdir / f).exists(), f"Backup missing: {f}"


# ── Audit-level outcome tests (slow — uses fixture) ────────────────

def test_v10447_credit_workflow_wired(credit_audit_post_wiring):
    """The CRITICAL finding from v10.446 must now be resolved."""
    wired = [w["engine"] for w in credit_audit_post_wiring.engine_wiring.wired_engines]
    assert "credit_workflow" in wired


def test_v10447_credit_workflow_in_three_pages(credit_audit_post_wiring):
    """Confirm wiring touched all 3 target pages."""
    cw = next(
        (w for w in credit_audit_post_wiring.engine_wiring.wired_engines
         if w["engine"] == "credit_workflow"),
        None,
    )
    assert cw is not None
    assert "21_loan_applications.py" in cw["in_credit_pages"]
    assert "22_credit_analysis.py" in cw["in_credit_pages"]
    assert "23_credit_admin.py" in cw["in_credit_pages"]


def test_v10447_credit_health_improved(credit_audit_post_wiring):
    """Health must be >= 70% (v10.446 baseline 65.8%)."""
    assert credit_audit_post_wiring.credit_health_pct >= 70.0


def test_v10447_no_critical_findings(credit_audit_post_wiring):
    """The SWIM LANE critical finding is now resolved."""
    assert credit_audit_post_wiring.severity_counts.get("critical", 0) == 0


def test_v10447_engine_wiring_75_pct(credit_audit_post_wiring):
    """6 of 8 engines wired = 75% (was 5/8 = 62.5%)."""
    assert credit_audit_post_wiring.engine_wiring.wiring_coverage_pct >= 75.0


def test_v10447_flow_coverage_85_pct(credit_audit_post_wiring):
    """8 of 9 stages covered = 88.9% (was 6/9 = 66.7%)."""
    assert credit_audit_post_wiring.flow_coverage.flow_completeness_pct >= 85.0


def test_v10447_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10447_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10447_g333_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10447_credit_swim_lane_wired
    r = gate_v10447_credit_swim_lane_wired()
    assert r["passed"], r.get("violations")

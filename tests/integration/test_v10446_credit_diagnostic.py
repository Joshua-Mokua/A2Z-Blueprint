"""Integration tests for v10.446 — Credit Section Diagnostic (Phase 1)."""

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def credit_audit():
    from utils.credit_section_audit_engine import credit_full_audit
    return credit_full_audit()


def test_v10446_engine_exists():
    p = REPO / "utils" / "credit_section_audit_engine.py"
    assert p.exists()
    t = p.read_text()
    for needed in (
        "CREDIT_PAGES", "CREDIT_ENGINES", "FLOW_STAGES", "CROSS_ORGAN_BRIDGES",
        "def audit_module_placement",
        "def audit_page_completeness",
        "def audit_engine_wiring",
        "def audit_flow_coverage",
        "def audit_ifrs9_consolidation",
        "def audit_specialized_products",
        "def credit_full_audit",
        "class CreditSectionAudit",
    ):
        assert needed in t, f"Missing: {needed}"


def test_v10446_zero_streamlit():
    t = (REPO / "utils" / "credit_section_audit_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        t, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10446_credit_pages_thirteen():
    from utils.credit_section_audit_engine import CREDIT_PAGES
    assert len(CREDIT_PAGES) == 13


def test_v10446_credit_engines_eight():
    from utils.credit_section_audit_engine import CREDIT_ENGINES
    assert len(CREDIT_ENGINES) >= 8


def test_v10446_flow_stages_nine():
    from utils.credit_section_audit_engine import FLOW_STAGES
    assert len(FLOW_STAGES) == 9
    stage_ids = [s["id"] for s in FLOW_STAGES]
    for required in ("pipeline", "analysis", "approvals", "administration",
                     "monitoring", "dru", "collateral"):
        assert required in stage_ids, f"Missing flow stage: {required}"


def test_v10446_cross_organ_bridges():
    from utils.credit_section_audit_engine import CROSS_ORGAN_BRIDGES
    assert len(CROSS_ORGAN_BRIDGES) >= 5
    organs = [b["to_organ"] for b in CROSS_ORGAN_BRIDGES]
    for required in ("legal", "compliance", "finance", "risk", "hr"):
        assert required in organs, f"Missing cross-organ bridge: {required}"


def test_v10446_module_placement_clean(credit_audit):
    """All 13 credit pages must be correctly placed in credit dept."""
    assert credit_audit.module_placement.placement_pct == 100.0
    assert len(credit_audit.module_placement.misplaced_pages) == 0


def test_v10446_health_above_60(credit_audit):
    """Baseline credit health from diagnostic should be >= 60%."""
    assert credit_audit.credit_health_pct >= 60.0


def test_v10446_critical_findings_surfaced(credit_audit):
    """v10.446 baseline: credit_workflow was unwired.
    v10.447 fixed this; now we assert it IS wired (forward-only).
    """
    wired = [w["engine"] for w in credit_audit.engine_wiring.wired_engines]
    # v10.446 surfaced this as the #1 critical finding.
    # v10.447 wired credit_workflow into 21+22+23 credit pages.
    assert "credit_workflow" in wired, (
        "credit_workflow should be wired (v10.447 wired the SWIM LANE)"
    )


def test_v10446_flow_gaps_detected(credit_audit):
    """Flow coverage should detect gaps in approvals stage."""
    gap_names = [g["name"] for g in credit_audit.flow_coverage.stages_with_gaps]
    assert any("Approvals" in n or "Swim Lane" in n for n in gap_names)


def test_v10446_rescue_priorities_present(credit_audit):
    """Diagnostic must surface concrete rescue priorities."""
    assert len(credit_audit.rescue_priorities) >= 2


def test_v10446_full_audit_json_serializable(credit_audit):
    json.dumps(credit_audit.to_dict())


def test_v10446_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10446_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10446_g332_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10446_credit_section_diagnostic
    r = gate_v10446_credit_section_diagnostic()
    assert r["passed"], r.get("violations")

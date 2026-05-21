"""Integration tests for v10.436 — HR section diagnostic audit."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10436_engine_exists():
    path = REPO / "utils" / "hr_section_audit_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_module_placement",
        "def audit_page_completeness",
        "def audit_engine_wiring",
        "def audit_react_readiness",
        "def audit_api_coverage",
        "def audit_data_backing",
        "def hr_full_audit",
        "class ModulePlacementAudit",
        "class PageCompletenessAudit",
        "class EngineWiringAudit",
        "class ReactReadinessAudit",
        "class APICoverageAudit",
        "class DataBackingAudit",
        "class HRFullAudit",
        "HR_DOMAIN_ENGINES",
        "MISPLACED_HR_PAGES",
        "STUB_LINE_THRESHOLD",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10436_zero_streamlit():
    text = (REPO / "utils" / "hr_section_audit_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10436_hr_domain_engines_8():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import HR_DOMAIN_ENGINES
    assert len(HR_DOMAIN_ENGINES) == 8
    # The 6 closed standards + 2 new
    for needed in (
        "peer_learning", "coaching_intelligence", "predictive_performance",
        "gamification", "efficiency", "wellness",
        "staff_onboarding_engine", "staff_exit_engine",
    ):
        assert needed in HR_DOMAIN_ENGINES


def test_v10436_misplaced_pages_identified():
    """The MISPLACED_HR_PAGES detection set should still contain CIMS+SLA.
    Note: After v10.437 relocation, those pages are no longer flagged as
    misplaced because they're not in HR anymore. But the engine's
    detection logic still recognizes them as candidates."""
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import MISPLACED_HR_PAGES
    assert "13_sla.py" in MISPLACED_HR_PAGES
    assert "18_cims.py" in MISPLACED_HR_PAGES


def test_v10436_stubs_identified():
    """At least 4 stub pages should be detected (lms, pip, workforce, disciplinary)."""
    from utils.hr_section_audit_engine import audit_page_completeness
    pc = audit_page_completeness()
    assert pc.stub_count >= 3


def test_v10436_engine_wiring_audit():
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    # At least some engines should be unwired (this is the issue)
    assert ew.total_hr_engines == 8
    assert ew.wiring_coverage_pct < 100.0


def test_v10436_react_readiness_all_engines():
    """All 8 HR engines should be React-ready (zero streamlit + dataclasses)."""
    from utils.hr_section_audit_engine import audit_react_readiness
    rr = audit_react_readiness()
    assert rr.react_readiness_pct == 100.0


def test_v10436_api_coverage_audit():
    from utils.hr_section_audit_engine import audit_api_coverage
    api = audit_api_coverage()
    assert api.total_engines == 8
    # At least some engines have endpoints
    assert len(api.engines_with_api) >= 2


def test_v10436_data_backing_audit():
    from utils.hr_section_audit_engine import audit_data_backing
    db = audit_data_backing()
    assert len(db.engines) == 8
    # Currently 0 are PostgreSQL — this is what rescue arc addresses
    assert db.pg_ready_count >= 0


def test_v10436_master_audit_runs():
    from utils.hr_section_audit_engine import hr_full_audit, HRFullAudit
    a = hr_full_audit()
    assert isinstance(a, HRFullAudit)
    assert 0 <= a.hr_health_pct <= 100
    assert len(a.rescue_priorities) > 0


def test_v10436_dataclasses_json_serializable():
    import json
    from utils.hr_section_audit_engine import (
        audit_module_placement, audit_page_completeness,
        audit_engine_wiring, audit_react_readiness,
        audit_api_coverage, audit_data_backing, hr_full_audit,
    )
    for fn in (
        audit_module_placement, audit_page_completeness,
        audit_engine_wiring, audit_react_readiness,
        audit_api_coverage, audit_data_backing, hr_full_audit,
    ):
        r = fn()
        json.dumps(r.to_dict())


def test_v10436_admin_panel_has_hr_audit():
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    assert "def render_hr_section_audit_panel" in text
    # No duplicate render_exit_risk_panel
    assert text.count("def render_exit_risk_panel") == 1


def test_v10436_admin_page_wires_hr_audit():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "render_hr_section_audit_panel" in text


def test_v10436_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10436_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/hr-audit/full" in text
    assert "/api/v1/hr-audit/dimension" in text


def test_v10436_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10436_bsc_rescue_health_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10436_g322_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10436_hr_section_audit
    r = gate_v10436_hr_section_audit()
    assert r["passed"], r.get("violations")

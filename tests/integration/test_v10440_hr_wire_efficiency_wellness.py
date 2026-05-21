"""Integration tests for v10.440 — HR Rescue Batch 3: wire #18 + #19."""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10440_pip_imports_efficiency():
    t = (REPO / "pages" / "43_pip.py").read_text()
    assert "from utils.efficiency" in t


def test_v10440_pip_has_efficiency_insights_tab():
    t = (REPO / "pages" / "43_pip.py").read_text()
    assert "Efficiency Insights" in t


def test_v10440_pip_uses_calculate_efficiency_scores():
    t = (REPO / "pages" / "43_pip.py").read_text()
    assert "calculate_efficiency_scores" in t


def test_v10440_pip_uses_efficiency_engine():
    t = (REPO / "pages" / "43_pip.py").read_text()
    assert "EfficiencyEngine" in t


def test_v10440_pip_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "43_pip.py").read_text())


def test_v10440_people_imports_wellness():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "from utils.wellness" in t


def test_v10440_people_has_wellness_section():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "Wellness" in t


def test_v10440_people_uses_assess_burnout_risk():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "assess_burnout_risk" in t


def test_v10440_people_uses_wellness_engine():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "WellnessEngine" in t


def test_v10440_people_uses_list_alerts_for_manager():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "list_alerts_for_manager" in t


def test_v10440_people_documents_opt_out():
    """Ethical guardrail: wellness page must mention opt-out flag."""
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "wellness_monitoring_disabled" in t


def test_v10440_people_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "2_people.py").read_text())


def test_v10440_hr_audit_wiring_75_pct():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    assert ew.wiring_coverage_pct >= 75.0


def test_v10440_efficiency_wired_in_pip():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    wired = [w["engine"] for w in ew.wired_engines]
    assert "efficiency" in wired


def test_v10440_wellness_wired_in_people():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    wired = [w["engine"] for w in ew.wired_engines]
    assert "wellness" in wired


def test_v10440_hr_health_improved():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import hr_full_audit
    a = hr_full_audit()
    assert a.hr_health_pct >= 65.0


def test_v10440_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10440_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10440_g326_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10440_hr_wire_efficiency_wellness
    r = gate_v10440_hr_wire_efficiency_wellness()
    assert r["passed"], r.get("violations")

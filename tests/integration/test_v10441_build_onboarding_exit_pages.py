"""Integration tests for v10.441 — HR Rescue Batch 4: onboarding + exit pages."""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10441_onboarding_page_exists():
    p = REPO / "pages" / "79_staff_onboarding.py"
    assert p.exists()


def test_v10441_exit_page_exists():
    p = REPO / "pages" / "80_staff_exit.py"
    assert p.exists()


def test_v10441_onboarding_imports_engine():
    t = (REPO / "pages" / "79_staff_onboarding.py").read_text()
    assert "from utils.staff_onboarding_engine" in t


def test_v10441_onboarding_uses_all_4_functions():
    t = (REPO / "pages" / "79_staff_onboarding.py").read_text()
    assert "validate_new_staff" in t
    assert "simulate_onboarding" in t
    assert "audit_staff_completeness" in t
    assert "audit_all_staff_completeness" in t


def test_v10441_onboarding_4_tabs():
    t = (REPO / "pages" / "79_staff_onboarding.py").read_text()
    assert "Simulate Onboarding" in t
    assert "Validate Record" in t
    assert "Per-Staff Audit" in t
    assert "Bank-Wide Audit" in t


def test_v10441_onboarding_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "79_staff_onboarding.py").read_text())


def test_v10441_exit_imports_engine():
    t = (REPO / "pages" / "80_staff_exit.py").read_text()
    assert "from utils.staff_exit_engine" in t


def test_v10441_exit_uses_all_4_functions():
    t = (REPO / "pages" / "80_staff_exit.py").read_text()
    assert "audit_exit_risk" in t
    assert "audit_all_exit_risks" in t
    assert "simulate_exit" in t
    assert "simulate_redistribution" in t


def test_v10441_exit_4_tabs():
    t = (REPO / "pages" / "80_staff_exit.py").read_text()
    assert "Per-Staff Exit Risk" in t
    assert "Top Key-Person Risks" in t
    assert "Redistribution Plan" in t
    assert "Bank-Wide Exit Readiness" in t


def test_v10441_exit_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "80_staff_exit.py").read_text())


def test_v10441_manifest_registers_both():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    for fname in ("79_staff_onboarding.py", "80_staff_exit.py"):
        entry = m["pages"].get(fname)
        assert entry is not None, f"{fname} not in manifest"
        assert entry["department_primary"] == "people_hr"


def test_v10441_manifest_stamp():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "_v10441_new_pages" in m


def test_v10441_backups_exist():
    bd = REPO / "data" / "_v10441_backups"
    assert bd.exists()
    assert (bd / "_manifest.json.before").exists()


def test_v10441_hr_engine_wiring_100_pct():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    assert ew.wiring_coverage_pct == 100.0


def test_v10441_onboarding_engine_wired():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    wired = [w["engine"] for w in ew.wired_engines]
    assert "staff_onboarding_engine" in wired


def test_v10441_exit_engine_wired():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    wired = [w["engine"] for w in ew.wired_engines]
    assert "staff_exit_engine" in wired


def test_v10441_no_should_be_but_arent():
    """v10.441 dynamic: should_be_in_hr_but_arent now empty."""
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_module_placement
    mp = audit_module_placement()
    assert len(mp.should_be_in_hr_but_arent) == 0


def test_v10441_hr_health_above_70():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import hr_full_audit
    a = hr_full_audit()
    assert a.hr_health_pct >= 70.0


def test_v10441_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10441_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10441_g327_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10441_build_onboarding_exit_pages
    r = gate_v10441_build_onboarding_exit_pages()
    assert r["passed"], r.get("violations")

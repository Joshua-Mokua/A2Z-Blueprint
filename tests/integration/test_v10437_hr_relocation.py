"""Integration tests for v10.437 — HR Rescue Batch 1: CIMS + SLA relocation."""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10437_manifest_sla_relocated():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    sla = m["pages"]["13_sla.py"]
    assert sla["department_primary"] == "operations"
    assert sla["module_path"] == "operations.sla_tracker"


def test_v10437_manifest_cims_relocated():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    cims = m["pages"]["18_cims.py"]
    assert cims["department_primary"] == "operations"
    assert cims["module_path"] == "operations.cims"


def test_v10437_manifest_stamp():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "_v10437_relocations" in m
    stamp = m["_v10437_relocations"]
    assert stamp["shipped"] == "v10.437"
    assert len(stamp["relocations"]) == 2


def test_v10437_sla_page_require_access_updated():
    t = (REPO / "pages" / "13_sla.py").read_text()
    assert 'require_access("operations.sla_tracker")' in t
    assert 'require_access("people_hr.sla_tracker")' not in t


def test_v10437_cims_page_require_access_updated():
    t = (REPO / "pages" / "18_cims.py").read_text()
    assert 'require_access("operations.cims")' in t
    assert 'require_access("people_hr.cims")' not in t


def test_v10437_sla_page_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "13_sla.py").read_text())


def test_v10437_cims_page_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "18_cims.py").read_text())


def test_v10437_backups_exist():
    bd = REPO / "data" / "_v10437_backups"
    assert bd.exists()
    for f in ("_manifest.json.before", "13_sla.py.before", "18_cims.py.before"):
        assert (bd / f).exists(), f"Missing backup: {f}"


def test_v10437_hr_audit_zero_misplaced():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_module_placement
    mp = audit_module_placement()
    assert len(mp.misplaced_in_hr) == 0


def test_v10437_hr_audit_5_correctly_placed():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_module_placement
    mp = audit_module_placement()
    assert len(mp.correctly_placed) == 5
    assert "2_people.py" in mp.correctly_placed
    assert "42_lms.py" in mp.correctly_placed
    assert "43_pip.py" in mp.correctly_placed
    assert "58_workforce.py" in mp.correctly_placed
    assert "60_disciplinary.py" in mp.correctly_placed


def test_v10437_hr_health_improved():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import hr_full_audit
    a = hr_full_audit()
    assert a.hr_health_pct >= 55.0  # was 53%, now improved


def test_v10437_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10437_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10437_cims_sub_pages_still_in_operations():
    """v10.437 didn't touch the 5 CIMS sub-pages; they should stay in operations."""
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    for fname in ("105_cims_capture.py", "106_cims_process.py",
                  "107_cims_compliance.py", "108_cims_closure.py",
                  "109_cims_live.py"):
        assert m["pages"][fname]["department_primary"] == "operations"


def test_v10437_g323_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10437_hr_relocation
    r = gate_v10437_hr_relocation()
    assert r["passed"], r.get("violations")

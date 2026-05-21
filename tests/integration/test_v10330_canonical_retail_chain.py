"""Integration tests for v10.330 — Canonical retail chain lock.

10 tests across 4 sections:
  Section 1 — Whitelist tightness (3 tests)
  Section 2 — Hierarchy structure (4 tests)
  Section 3 — Synthesizer alignment (1 test)
  Section 4 — G221 audit gate (2 tests)

Branch performance IS the BM's performance. AM BSC IS aggregate of
their BMs. HoB BSC IS aggregate of their AMs. Chief Retail BSC IS
aggregate of HoB.
"""

import json
import sys
from pathlib import Path


REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Whitelist tightness
# ────────────────────────────────────────────────────────────────────

def test_v10330_bm_parent_set_locked_to_area_manager():
    """role_manager_whitelist['Branch Manager'] is locked to [Area Manager]."""
    cfg = json.loads(
        (REPO / "data" / "org_hierarchy_config.json").read_text()
    )
    wl = cfg.get("role_manager_whitelist", {})
    assert wl.get("Branch Manager") == ["Area Manager"], (
        f"BM parent should be ['Area Manager'], got {wl.get('Branch Manager')}"
    )


def test_v10330_senior_bm_parent_set_locked_to_area_manager():
    """role_manager_whitelist['Senior Branch Manager'] is locked to [Area Manager]."""
    cfg = json.loads(
        (REPO / "data" / "org_hierarchy_config.json").read_text()
    )
    wl = cfg.get("role_manager_whitelist", {})
    assert wl.get("Senior Branch Manager") == ["Area Manager"], (
        f"Senior BM parent should be ['Area Manager'], got {wl.get('Senior Branch Manager')}"
    )


def test_v10330_area_manager_parent_locked_to_head_of_branches():
    """role_manager_whitelist['Area Manager'] is locked to [Head of Branches]."""
    cfg = json.loads(
        (REPO / "data" / "org_hierarchy_config.json").read_text()
    )
    wl = cfg.get("role_manager_whitelist", {})
    assert wl.get("Area Manager") == ["Head of Branches"], (
        f"AM parent should be ['Head of Branches'], got {wl.get('Area Manager')}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Hierarchy structure
# ────────────────────────────────────────────────────────────────────

def test_v10330_all_bms_report_to_area_manager():
    """All 94 active Branch Managers report to an Area Manager."""
    for k in list(sys.modules):
        if k.startswith("utils.virtual_bank"):
            del sys.modules[k]
        if k.startswith("utils.hierarchy_synth"):
            del sys.modules[k]
        if k.startswith("utils.org_hierarchy_config"):
            del sys.modules[k]
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    bms = [
        r for r in u.values()
        if "Branch Manager" in r.role
        and "Assistant" not in r.role
        and "Asst" not in r.role
        and r.active
    ]
    ams = {r.staff_code for r in u.values() if r.role == "Area Manager"}
    misplaced = [r.staff_code for r in bms if r.manager_code not in ams]
    assert not misplaced, (
        f"{len(misplaced)} BMs not under AM: {misplaced[:5]}"
    )


def test_v10330_each_area_manager_has_at_least_5_bms():
    """Each Area Manager has ≥5 BMs reporting to them."""
    for k in list(sys.modules):
        if k.startswith("utils.virtual_bank"):
            del sys.modules[k]
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    ams = [r for r in u.values() if r.role == "Area Manager"]
    bms = [
        r for r in u.values()
        if "Branch Manager" in r.role
        and "Assistant" not in r.role
        and "Asst" not in r.role
        and r.active
    ]
    for am in ams:
        count = sum(1 for r in bms if r.manager_code == am.staff_code)
        assert count >= 5, (
            f"AM {am.staff_code} has only {count} BMs"
        )


def test_v10330_no_senior_bm_supervises_another_bm():
    """No Senior BM has another BM reporting to them (peers, not supervisors)."""
    for k in list(sys.modules):
        if k.startswith("utils.virtual_bank"):
            del sys.modules[k]
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    sbm_codes = {
        r.staff_code for r in u.values()
        if r.role == "Senior Branch Manager"
    }
    all_bms = [
        r for r in u.values()
        if "Branch Manager" in r.role
        and "Assistant" not in r.role
        and "Asst" not in r.role
        and r.active
    ]
    bms_under_sbm = [
        r.staff_code for r in all_bms
        if r.manager_code in sbm_codes
    ]
    assert not bms_under_sbm, (
        f"{len(bms_under_sbm)} BMs report to Senior BMs: "
        f"{bms_under_sbm[:3]}"
    )


def test_v10330_head_of_branches_reports_to_chief_retail():
    """Head of Branches reports to Chief Retail Banking Officer."""
    for k in list(sys.modules):
        if k.startswith("utils.virtual_bank"):
            del sys.modules[k]
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    hobs = [r for r in u.values() if r.role == "Head of Branches"]
    chiefs = {
        r.staff_code for r in u.values()
        if r.role == "Chief Retail Banking Officer"
    }
    assert hobs, "No Head of Branches in universe"
    for hob in hobs:
        assert hob.manager_code in chiefs, (
            f"HoB {hob.staff_code} → {hob.manager_code} (not Chief Retail)"
        )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Synthesizer alignment
# ────────────────────────────────────────────────────────────────────

def test_v10330_synthesizer_combines_senior_bm_with_standard_bm():
    """hierarchy_synth.py treats Senior BMs and standard BMs as peers."""
    synth_src = (REPO / "utils" / "hierarchy_synth.py").read_text()
    # Both BM types should be combined when assigning to AMs
    assert "Senior Branch Manager" in synth_src
    # Code comment indicating v10.330 fix
    assert "v10.330" in synth_src, (
        "hierarchy_synth.py missing v10.330 alignment comment"
    )
    # The corrected Layer 3 should combine both BM types
    assert (
        'by_role.get("Branch Manager", []) +' in synth_src
        and 'by_role.get("Senior Branch Manager", [])' in synth_src
    ), "BM + Senior BM not combined in Layer 3"


# ────────────────────────────────────────────────────────────────────
# Section 4 — G221 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10330_g221_gate_registered():
    """G221 gate function exists and is registered in GATES list."""
    for k in list(sys.modules):
        if k.startswith("scripts.audit"):
            del sys.modules[k]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_module", str(REPO / "scripts" / "audit.py")
    )
    audit_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit_mod)
    assert hasattr(audit_mod, "gate_canonical_retail_chain")
    gate_ids = [gid for gid, _ in audit_mod.GATES]
    assert "G221" in gate_ids


def test_v10330_g221_passes_with_current_state():
    """G221 gate executes cleanly against current platform state."""
    for k in list(sys.modules):
        if k.startswith("scripts.audit"):
            del sys.modules[k]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_module", str(REPO / "scripts" / "audit.py")
    )
    audit_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit_mod)
    result = audit_mod.gate_canonical_retail_chain()
    assert result["passed"], (
        f"G221 failed: {result['violations']}"
    )

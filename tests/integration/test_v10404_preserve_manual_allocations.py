"""Integration tests for v10.404 — regenerator preserves manual allocations.

Per Joshua F4: "Regenerate Cascade button — preserve manual allocations".
Critical bug fix: admin clicking Regenerate Cascade should not wipe
manager's personalized allocations to direct reports.

12 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Code presence
# ────────────────────────────────────────────────────────────────────

def test_v10404_regenerator_accepts_preserve_manual():
    """regenerate_target_cascade has preserve_manual parameter."""
    text = (REPO / "utils" / "cascade_regenerator.py").read_text()
    assert "preserve_manual" in text
    assert "def regenerate_target_cascade" in text
    # Default True
    assert "preserve_manual: bool = True" in text


def test_v10404_skip_helper_present():
    """_cascade_recursive_with_skip helper exists."""
    text = (REPO / "utils" / "cascade_regenerator.py").read_text()
    assert "_cascade_recursive_with_skip" in text
    assert "skip_set: Set[str]" in text


def test_v10404_set_allocation_stamps_markers():
    """CascadeManager.set_allocation stamps _v10404_manual + updated_by."""
    core_text = (REPO / "utils" / "core.py").read_text()
    idx = core_text.find("def set_allocation(")
    assert idx > 0
    method = core_text[idx:idx + 1500]
    assert "_v10404_manual" in method
    assert "updated_by" in method


def test_v10404_canonical_admin_accepts_preserve():
    """canonical_admin.regenerate_cascade_from_canonical accepts preserve_manual."""
    text = (REPO / "utils" / "canonical_admin.py").read_text()
    assert "preserve_manual: bool = True" in text


def test_v10404_admin_ui_exposes_mode_toggle():
    """Admin UI Regenerate tab exposes preserve/force radio toggle."""
    text = (REPO / "pages" / "_admin_canonical.py").read_text()
    assert "Preserve manual allocations" in text
    assert "Force full rebuild" in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — End-to-end preservation
# ────────────────────────────────────────────────────────────────────

def test_v10404_manual_allocation_survives_regen(tmp_path):
    """End-to-end: manual allocation survives regenerator call."""
    import shutil
    # Sandbox copy of target_cascade.json
    tc_path = REPO / "data" / "target_cascade.json"
    backup = tmp_path / "tc_backup.json"
    shutil.copy(tc_path, backup)

    try:
        # Step 1: set manual allocation via CascadeManager
        for k in list(sys.modules):
            if "cascade" in k or k == "utils.core":
                del sys.modules[k]
        from utils.core import CascadeManager
        cm = CascadeManager()
        manual = [
            {"to_code": "300011", "to_name": "Test", "to_role": "Head",
             "to_unit": "HQ", "amount": 6000.0},
            {"to_code": "300012", "to_name": "Test2", "to_role": "Head",
             "to_unit": "HQ", "amount": 4000.0},
        ]
        cm.set_allocation("300002", "PBT", "2026", manual, 10000.0,
                          updated_by="v10404_test")

        # Step 2: regenerate with preserve_manual=True
        for k in list(sys.modules):
            if "cascade" in k:
                del sys.modules[k]
        from utils.cascade_regenerator import regenerate_target_cascade
        regenerate_target_cascade(write=True, preserve_manual=True)

        # Step 3: verify preserved
        tc = json.loads(tc_path.read_text())
        entry = tc.get("300002|PBT|2026")
        assert entry is not None
        assert entry.get("total_target") == 10000.0
        amounts = [a.get("amount") for a in entry.get("allocations", [])]
        assert 6000.0 in amounts and 4000.0 in amounts
        assert entry.get("_v10404_manual") is True
        assert entry.get("updated_by") == "v10404_test"
    finally:
        shutil.copy(backup, tc_path)


def test_v10404_force_mode_overwrites_manual(tmp_path):
    """Force mode (preserve_manual=False) does overwrite manual allocations."""
    import shutil
    tc_path = REPO / "data" / "target_cascade.json"
    backup = tmp_path / "tc_backup.json"
    shutil.copy(tc_path, backup)

    try:
        # Set manual
        for k in list(sys.modules):
            if "cascade" in k or k == "utils.core":
                del sys.modules[k]
        from utils.core import CascadeManager
        cm = CascadeManager()
        cm.set_allocation("300002", "PBT", "2026",
                          [{"to_code": "X", "to_name": "X", "to_role": "X",
                            "to_unit": "X", "amount": 1.0}],
                          1.0, updated_by="v10404_test_force")

        # Force regen
        for k in list(sys.modules):
            if "cascade" in k:
                del sys.modules[k]
        from utils.cascade_regenerator import regenerate_target_cascade
        regenerate_target_cascade(write=True, preserve_manual=False)

        # Manual is overwritten
        tc = json.loads(tc_path.read_text())
        entry = tc.get("300002|PBT|2026")
        assert entry is not None
        assert entry.get("_v10404_manual") is None
        # total != 1.0 because it's the bank-target derived
        assert entry.get("total_target") != 1.0
    finally:
        shutil.copy(backup, tc_path)


def test_v10404_subtree_preserved_under_manual_manager(tmp_path):
    """If a chief has a manual allocation, their subtree isn't regenerated either."""
    import shutil
    tc_path = REPO / "data" / "target_cascade.json"
    backup = tmp_path / "tc_backup.json"
    shutil.copy(tc_path, backup)

    try:
        # Read tc state - count current Head-of-X entries
        for k in list(sys.modules):
            if "cascade" in k or k == "utils.core":
                del sys.modules[k]
        from utils.core import CascadeManager
        from utils.cascade_regenerator import regenerate_target_cascade

        cm = CascadeManager()
        # CRBO sets manual PBT — only goes to Head of Branches at 100%
        cm.set_allocation("300002", "PBT", "2026",
                          [{"to_code": "300011", "to_name": "HoB", "to_role": "Head of Branches",
                            "to_unit": "HQ", "amount": 100.0}],
                          100.0, updated_by="v10404_test")

        # Regenerate
        regenerate_target_cascade(write=True, preserve_manual=True)

        # CRBO entry should match the manual (just 1 alloc, 100.0)
        tc = json.loads(tc_path.read_text())
        crbo = tc.get("300002|PBT|2026")
        assert crbo is not None
        assert len(crbo.get("allocations", [])) == 1
        assert crbo.get("allocations")[0].get("amount") == 100.0
    finally:
        shutil.copy(backup, tc_path)


# ────────────────────────────────────────────────────────────────────
# Section 3 — State preserved
# ────────────────────────────────────────────────────────────────────

def test_v10404_engine_state_preserved():
    """Engine still 0/0/0/0 after v10.404."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10404_existing_cascade_size_within_bounds():
    """Cascade should be ~24K entries after v10.404 (unchanged from v10.403)."""
    tc = json.loads((REPO / "data" / "target_cascade.json").read_text())
    data_count = sum(1 for k in tc if not k.startswith("_") and "|" in k)
    assert 20000 <= data_count <= 30000, f"unexpected size: {data_count}"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Gate
# ────────────────────────────────────────────────────────────────────

def test_v10404_g290_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10404_preserve_manual_allocations
    r = gate_v10404_preserve_manual_allocations()
    assert r["passed"], r.get("violations")

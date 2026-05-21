"""Integration tests for v10.462 — Manifest File Existence Hotfix.

Per Joshua reported StreamlitAPIException: 'Unable to create Page.
The file 82_system_vitals.py could not be found.'
"""

import ast
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10462_loader_has_defensive_filter():
    text = (REPO / "utils" / "page_manifest_loader.py").read_text()
    assert "v10.462" in text, "loader missing v10.462 hotfix marker"
    assert "pages_dir / fname" in text, "loader missing file-existence check"


def test_v10462_loader_has_list_ghost_entries():
    text = (REPO / "utils" / "page_manifest_loader.py").read_text()
    assert "def list_ghost_entries" in text


def test_v10462_loader_parses():
    ast.parse((REPO / "utils" / "page_manifest_loader.py").read_text())


def test_v10462_list_ghost_entries_works():
    """Function should return list of manifest pages whose files are missing."""
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import list_ghost_entries
    ghosts = list_ghost_entries()
    assert isinstance(ghosts, list)


def test_v10462_pages_in_department_filters_ghosts(tmp_path):
    """Temporarily remove a page and verify it's excluded from navigation."""
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils import page_manifest_loader
    from utils.page_manifest_loader import pages_in_department, list_ghost_entries

    target = REPO / "pages" / "82_system_vitals.py"
    backup = tmp_path / "82_system_vitals.py.bak"

    if not target.exists():
        pytest.skip("82_system_vitals.py not in sandbox to test against")

    # Move file aside
    target.rename(backup)
    page_manifest_loader._CACHE = None
    try:
        ghosts = list_ghost_entries()
        assert "82_system_vitals.py" in ghosts, \
            "Ghost detection should find the moved file"

        # Admin pages must NOT include the ghost
        admin = pages_in_department("admin")
        for fname, _ in admin:
            assert fname != "82_system_vitals.py", \
                "pages_in_department should filter ghosts"
    finally:
        backup.rename(target)
        page_manifest_loader._CACHE = None


def test_v10462_current_manifest_has_no_ghosts():
    """The shipped manifest should have zero ghost entries."""
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import list_ghost_entries
    ghosts = list_ghost_entries()
    assert ghosts == [], f"Manifest has ghost entries: {ghosts}"


def test_v10462_82_system_vitals_exists():
    """The file Joshua's error mentioned must be present in shipped state."""
    assert (REPO / "pages" / "82_system_vitals.py").exists()


def test_v10462_g343_enhanced():
    """G343 should now also check file existence."""
    text = (REPO / "scripts" / "audit.py").read_text()
    assert "ghost_entries" in text
    assert "manifest references missing file" in text


def test_v10462_g348_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10462_manifest_file_existence
    r = gate_v10462_manifest_file_existence()
    assert r["passed"], r.get("violations")


def test_v10462_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10462_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10462_10_organ_audit_still_works():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    a = all_modules_audit()
    assert len(a.modules) == 10
    assert a.avg_doctrine_health_pct >= 73.0

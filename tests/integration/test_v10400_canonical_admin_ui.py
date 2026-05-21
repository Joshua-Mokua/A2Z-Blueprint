"""Integration tests for v10.400 — Admin UI for canonical hierarchy editing.

Per Joshua: "reporting lines can be set from the admin" production-time
requirement. MD/admin can edit canonical hierarchy from within the app.

12 tests across 4 sections.
"""

import ast
import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Files exist + structure
# ────────────────────────────────────────────────────────────────────

def test_v10400_canonical_admin_module_exists():
    p = REPO / "utils" / "canonical_admin.py"
    assert p.exists()
    text = p.read_text()
    # Required functions
    for fn in ("load_canonical", "save_canonical", "list_role_managers",
               "list_role_tiers", "get_branch_tier_threshold",
               "set_role_managers", "remove_role", "set_role_tier",
               "set_branch_tier_threshold",
               "regenerate_cascade_from_canonical",
               "validate_canonical", "log_change", "read_change_log"):
        assert f"def {fn}" in text, f"function {fn} missing"


def test_v10400_canonical_admin_is_leaf():
    """No upward utils.* imports at module level (cascade_regenerator imported via importlib)."""
    p = REPO / "utils" / "canonical_admin.py"
    text = p.read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module and node.module.startswith("utils")
                    and node.col_offset == 0):
                assert False, f"canonical_admin imports utils.{node.module} at module level"


def test_v10400_admin_canonical_page_exists():
    p = REPO / "pages" / "_admin_canonical.py"
    assert p.exists()
    text = p.read_text()
    assert "def render_canonical_admin" in text


def test_v10400_admin_canonical_page_imports_backend():
    text = (REPO / "pages" / "_admin_canonical.py").read_text()
    for fn in ("list_role_managers", "list_role_tiers",
               "set_role_managers", "regenerate_cascade_from_canonical"):
        assert fn in text, f"page does not import/use {fn}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — 7_admin.py integration
# ────────────────────────────────────────────────────────────────────

def test_v10400_7_admin_imports_canonical():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "from pages._admin_canonical import render_canonical_admin" in text


def test_v10400_7_admin_has_canonical_tab():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "🎯 Canonical Hierarchy" in text
    assert "render_canonical_admin(sub[7]" in text


# ────────────────────────────────────────────────────────────────────
# Section 3 — Backend behaviour
# ────────────────────────────────────────────────────────────────────

def test_v10400_list_role_managers_returns_canonical():
    for k in list(sys.modules):
        if k.startswith("utils.canonical_admin"):
            del sys.modules[k]
    from utils.canonical_admin import list_role_managers
    rmw = list_role_managers()
    assert isinstance(rmw, dict)
    assert len(rmw) > 50  # post-v10.398 should have 130+ entries
    # Skip meta keys
    for role in rmw:
        assert not role.startswith("_")


def test_v10400_list_role_tiers_returns_canonical():
    for k in list(sys.modules):
        if k.startswith("utils.canonical_admin"):
            del sys.modules[k]
    from utils.canonical_admin import list_role_tiers
    tiers = list_role_tiers()
    assert isinstance(tiers, dict)
    assert "Chief Executive & Managing Director" in tiers
    assert tiers["Chief Executive & Managing Director"] == 0


def test_v10400_validate_canonical_passes():
    for k in list(sys.modules):
        if k.startswith("utils.canonical_admin"):
            del sys.modules[k]
    from utils.canonical_admin import validate_canonical
    v = validate_canonical()
    assert v["valid"], f"canonical not valid: {v['issues']}"


def test_v10400_change_log_can_append():
    """Append to change log and verify."""
    for k in list(sys.modules):
        if k.startswith("utils.canonical_admin"):
            del sys.modules[k]
    from utils.canonical_admin import log_change, read_change_log
    before = len(read_change_log())
    ok = log_change("v10400_unittest", "unittest_probe", "test_target",
                    "old_val", "new_val", "v10.400 test")
    assert ok
    after = read_change_log()
    assert len(after) == before + 1
    last = after[-1]
    assert last["who"] == "v10400_unittest"
    assert last["action"] == "unittest_probe"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Gate + state
# ────────────────────────────────────────────────────────────────────

def test_v10400_engine_state_unchanged():
    """Adding admin UI doesn't change engine results."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10400_g286_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10400_canonical_admin_ui
    r = gate_v10400_canonical_admin_ui()
    assert r["passed"], r.get("violations")

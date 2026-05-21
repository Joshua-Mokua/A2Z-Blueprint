"""Integration tests for v10.346 — Finance Hub Consolidation (Option E sub-batch 2).

12 tests across 5 sections:
  Section 1 — Helper module (3 tests)
  Section 2 — Thin wrapper pages (3 tests)
  Section 3 — Consolidated page (2 tests)
  Section 4 — Shim move architecture (2 tests)
  Section 5 — Audit gate G233 (2 tests)
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Helper module
# ────────────────────────────────────────────────────────────────────

def test_v10346_helper_exports_four_render_functions():
    """utils.finance_hub_render exports 4 render_* fns."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.finance_hub_render")
    import utils.finance_hub_render as r
    for fn in ("render_sbu_performance", "render_sbu_drilldown",
               "render_opex", "render_mgmt_accounts"):
        assert hasattr(r, fn), f"helper missing {fn}"
        assert callable(getattr(r, fn))


def test_v10346_helper_module_size_reasonable():
    """utils/finance_hub_render.py should be in the 2000-3500 line range."""
    path = REPO / "utils" / "finance_hub_render.py"
    assert path.exists()
    lines = len(path.read_text().splitlines())
    assert 2000 <= lines <= 3500, (
        f"helper module is {lines} lines — outside expected 2000-3500 range"
    )


def test_v10346_helper_has_no_pages_layer_violation():
    """utils/finance_hub_render.py must not import from pages.*"""
    import ast
    path = REPO / "utils" / "finance_hub_render.py"
    tree = ast.parse(path.read_text())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("pages."):
                bad.append(f"L{node.lineno}: from {node.module}")
    assert not bad, f"Layer violations: {bad}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Thin wrapper pages
# ────────────────────────────────────────────────────────────────────

def test_v10346_four_old_pages_are_thin_wrappers():
    """Each finance page is now ≤40 lines."""
    expectations = {
        "9_sbu.py":             "render_sbu_performance",
        "10_opex.py":           "render_opex",
        "52_mgmt_accounts.py":  "render_mgmt_accounts",
        "114_sbu_drilldown.py": "render_sbu_drilldown",
    }
    for page_name, expected_fn in expectations.items():
        page = REPO / "pages" / page_name
        assert page.exists()
        lines = len(page.read_text().splitlines())
        assert lines <= 40, f"{page_name} is {lines} lines (>40)"
        assert expected_fn in page.read_text()


def test_v10346_old_pages_preserve_access_gates():
    expectations = {
        "9_sbu.py":             "finance.sbu_performance",
        "10_opex.py":           "operations.opex",
        "52_mgmt_accounts.py":  "finance.mgmt_accounts",
        "114_sbu_drilldown.py": "finance.sbu_performance",
    }
    for page_name, perm in expectations.items():
        src = (REPO / "pages" / page_name).read_text()
        assert "require_access" in src
        assert perm in src


def test_v10346_originals_backed_up():
    backup_dir = REPO / "data" / "_v10346_backups"
    assert backup_dir.exists()
    for orig in ("9_sbu.py.before", "10_opex.py.before",
                 "52_mgmt_accounts.py.before", "114_sbu_drilldown.py.before"):
        assert (backup_dir / orig).exists()
        # Original body must be >300 lines
        assert len((backup_dir / orig).read_text().splitlines()) > 300


# ────────────────────────────────────────────────────────────────────
# Section 3 — Consolidated entry page
# ────────────────────────────────────────────────────────────────────

def test_v10346_consolidated_page_imports_all_four_renders():
    src = (REPO / "pages" / "116_finance_hub.py").read_text()
    for fn in ("render_sbu_performance", "render_sbu_drilldown",
               "render_opex", "render_mgmt_accounts"):
        assert fn in src, f"116 doesn't import {fn}"
    assert "segmented_control" in src or "st.radio" in src


def test_v10346_consolidated_page_in_manifest():
    import json
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "116_finance_hub.py" in m["pages"]
    entry = m["pages"]["116_finance_hub.py"]
    assert entry["module_path"] == "finance.finance_hub"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Shim move architecture
# ────────────────────────────────────────────────────────────────────

def test_v10346_shim_move_canonical_homes_exist():
    """Canonical homes for the 4 shimmed pages modules exist in utils/."""
    for canonical in ("page_shared.py", "page_access.py",
                      "page_cockpit_render.py", "page_manifest_loader.py"):
        canon = REPO / "utils" / canonical
        assert canon.exists(), f"utils/{canonical} missing"


def test_v10346_shim_move_pages_are_re_exports():
    """The original pages/_*.py paths are now thin re-export shims."""
    for shim in ("_shared.py", "_access.py", "_cockpit_render.py",
                 "_manifest_loader.py"):
        path = REPO / "pages" / shim
        assert path.exists(), f"shim pages/{shim} missing"
        text = path.read_text()
        # Re-exports from utils.page_*
        assert "utils.page_" in text, f"shim pages/{shim} not re-exporting"
        # Shims are short — they're just import lines
        assert len(text.splitlines()) <= 25, (
            f"shim pages/{shim} is {len(text.splitlines())} lines, "
            f"should be ≤25"
        )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Audit gate G233
# ────────────────────────────────────────────────────────────────────

def test_v10346_g233_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_finance_hub_consolidation
    result = gate_finance_hub_consolidation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G233"


def test_v10346_g233_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G233", gate_finance_hub_consolidation)' in text

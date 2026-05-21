"""Integration tests for v10.348 — Competitor Hub Consolidation (Option E sub-batch 4).

10 tests across 4 sections:
  Section 1 — Helper module (3 tests)
  Section 2 — Thin wrapper pages (3 tests)
  Section 3 — Consolidated page (2 tests)
  Section 4 — Audit gate G235 (2 tests)
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

def test_v10348_helper_exports_two_render_functions():
    """utils.competitor_hub_render exports 2 render_* functions."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.competitor_hub_render")
    import utils.competitor_hub_render as r
    for fn in ("render_competitor_overview", "render_competitor_workbench"):
        assert hasattr(r, fn), f"helper missing {fn}"
        assert callable(getattr(r, fn))


def test_v10348_helper_no_layer_violation():
    """utils/competitor_hub_render.py must not import from pages/.*"""
    text = (REPO / "utils" / "competitor_hub_render.py").read_text()
    assert "from pages." not in text, (
        "Helper imports from pages.* — layer violation. "
        "Use utils.page_* shims instead."
    )


def test_v10348_helper_module_size_reasonable():
    """utils/competitor_hub_render.py should be roughly 600-1000 lines."""
    path = REPO / "utils" / "competitor_hub_render.py"
    assert path.exists()
    lines = len(path.read_text().splitlines())
    assert 600 <= lines <= 1000, (
        f"helper module is {lines} lines — outside expected 600-1000 range"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Thin wrappers
# ────────────────────────────────────────────────────────────────────

def test_v10348_two_old_pages_are_thin_wrappers():
    expectations = {
        "11_competitor.py":              "render_competitor_overview",
        "93_competitor_intelligence.py": "render_competitor_workbench",
    }
    for page_name, expected_fn in expectations.items():
        page = REPO / "pages" / page_name
        assert page.exists(), f"missing {page_name}"
        lines = len(page.read_text().splitlines())
        assert lines <= 40, f"{page_name} is {lines} lines (>40)"
        assert expected_fn in page.read_text()


def test_v10348_old_pages_preserve_access_gates():
    expectations = {
        "11_competitor.py":              "external.competitor_intel",
        "93_competitor_intelligence.py": "shared.customer_360",
    }
    for page_name, perm in expectations.items():
        src = (REPO / "pages" / page_name).read_text()
        assert "require_access" in src
        assert perm in src


def test_v10348_originals_backed_up():
    backup_dir = REPO / "data" / "_v10348_backups"
    assert backup_dir.exists()
    for orig in ("11_competitor.py.before",
                 "93_competitor_intelligence.py.before"):
        assert (backup_dir / orig).exists(), f"backup {orig} missing"
        assert len((backup_dir / orig).read_text().splitlines()) > 100


# ────────────────────────────────────────────────────────────────────
# Section 3 — Consolidated page
# ────────────────────────────────────────────────────────────────────

def test_v10348_consolidated_page_imports_both_renders():
    src = (REPO / "pages" / "118_competitor_hub.py").read_text()
    for fn in ("render_competitor_overview", "render_competitor_workbench"):
        assert fn in src
    assert "segmented_control" in src or "st.radio" in src


def test_v10348_consolidated_page_in_manifest():
    import json
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "118_competitor_hub.py" in m["pages"]
    entry = m["pages"]["118_competitor_hub.py"]
    assert entry["module_path"] == "external.competitor_hub"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Audit gate G235
# ────────────────────────────────────────────────────────────────────

def test_v10348_g235_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_competitor_hub_consolidation
    result = gate_competitor_hub_consolidation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G235"


def test_v10348_g235_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G235", gate_competitor_hub_consolidation)' in text

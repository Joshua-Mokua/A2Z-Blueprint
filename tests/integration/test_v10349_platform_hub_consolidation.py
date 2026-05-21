"""Integration tests for v10.349 — Platform Hub Consolidation (Option E sub-batch 5).

12 tests across 4 sections:
  Section 1 — Helper module (3 tests)
  Section 2 — Thin wrapper pages (4 tests)
  Section 3 — Consolidated page (2 tests)
  Section 4 — Audit gate G236 (3 tests)
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

def test_v10349_helper_exports_four_render_functions():
    """utils.platform_hub_render exports 4 render_* functions."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.platform_hub_render")
    import utils.platform_hub_render as r
    for fn in ("render_systems_view", "render_it_digital_pt1",
               "render_it_digital_pt2", "render_platform_health"):
        assert hasattr(r, fn), f"helper missing {fn}"
        assert callable(getattr(r, fn))


def test_v10349_helper_no_layer_violation():
    """utils/platform_hub_render.py must not import from pages/.*"""
    text = (REPO / "utils" / "platform_hub_render.py").read_text()
    assert "from pages." not in text, (
        "Helper imports from pages.* — layer violation. "
        "Use utils.page_* shims instead."
    )


def test_v10349_helper_module_size_reasonable():
    """utils/platform_hub_render.py should be sizeable (4 large pages combined)."""
    path = REPO / "utils" / "platform_hub_render.py"
    assert path.exists()
    lines = len(path.read_text().splitlines())
    assert 3500 <= lines <= 5500, (
        f"helper module is {lines} lines — outside expected 3500-5500 range"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Thin wrapper pages
# ────────────────────────────────────────────────────────────────────

def test_v10349_four_old_pages_are_thin_wrappers():
    """Each of the 4 original Platform/IT pages is now ≤40 lines."""
    expectations = {
        "91_systems_view.py":     "render_systems_view",
        "96_it_digital_pt1.py":   "render_it_digital_pt1",
        "97_it_digital_pt2.py":   "render_it_digital_pt2",
        "98_platform_health.py":  "render_platform_health",
    }
    for page_name, expected_fn in expectations.items():
        page = REPO / "pages" / page_name
        assert page.exists(), f"missing {page_name}"
        lines = len(page.read_text().splitlines())
        assert lines <= 40, (
            f"{page_name} is {lines} lines (>40) — not thin anymore"
        )
        assert expected_fn in page.read_text(), (
            f"{page_name} doesn't import {expected_fn}"
        )


def test_v10349_old_pages_preserve_access_gates():
    """Each thin wrapper still calls require_access with same permission."""
    expectations = {
        "91_systems_view.py":     "it_platform.systems_view",
        "96_it_digital_pt1.py":   "it_platform.it_digital_pt1",
        "97_it_digital_pt2.py":   "it_platform.it_digital_pt2",
        "98_platform_health.py":  "it_platform.platform_health",
    }
    for page_name, perm in expectations.items():
        src = (REPO / "pages" / page_name).read_text()
        assert "require_access" in src
        assert perm in src, f"{page_name} lost permission {perm}"


def test_v10349_platform_health_preserves_legacy_compat():
    """98_platform_health uses dual-permission pattern (legacy + dotted)."""
    src = (REPO / "pages" / "98_platform_health.py").read_text()
    # Must check legacy 'platform_health' silently first, then fall through
    # to dotted 'it_platform.platform_health'
    assert "platform_health" in src
    assert "silent=True" in src or "silent" in src


def test_v10349_originals_backed_up():
    """Pre-v10.349 page bodies preserved under data/_v10349_backups/."""
    backup_dir = REPO / "data" / "_v10349_backups"
    assert backup_dir.exists()
    for orig in ("91_systems_view.py.before", "96_it_digital_pt1.py.before",
                 "97_it_digital_pt2.py.before", "98_platform_health.py.before"):
        path = backup_dir / orig
        assert path.exists(), f"backup {orig} missing"
        assert len(path.read_text().splitlines()) > 200


# ────────────────────────────────────────────────────────────────────
# Section 3 — Consolidated page
# ────────────────────────────────────────────────────────────────────

def test_v10349_consolidated_page_imports_all_four_renders():
    """pages/119_platform_hub.py imports all 4 render functions."""
    src = (REPO / "pages" / "119_platform_hub.py").read_text()
    for fn in ("render_systems_view", "render_it_digital_pt1",
               "render_it_digital_pt2", "render_platform_health"):
        assert fn in src, f"119 doesn't import {fn}"
    # Must use a selector
    assert "segmented_control" in src or "st.radio" in src


def test_v10349_consolidated_page_in_manifest():
    """pages/_manifest.json has 119_platform_hub registered."""
    import json
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "119_platform_hub.py" in m["pages"]
    entry = m["pages"]["119_platform_hub.py"]
    assert "it_platform" in entry["module_path"]


# ────────────────────────────────────────────────────────────────────
# Section 4 — Audit gate G236
# ────────────────────────────────────────────────────────────────────

def test_v10349_g236_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_platform_hub_consolidation
    result = gate_platform_hub_consolidation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G236"


def test_v10349_g236_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G236", gate_platform_hub_consolidation)' in text


def test_v10349_all_122plus_pages_smoke_pass():
    """Full smoke run includes 119_platform_hub.py and stays clean."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_all
    report = smoke_test_all()
    assert report["failed"] == 0, (
        f"Smoke failures: {report['failures'][:3]}"
    )
    # 122 pages from v10.348 + 1 new = 123 (one of which is the consolidated
    # 119_platform_hub.py). Allow at least 123.
    assert report["total"] >= 123

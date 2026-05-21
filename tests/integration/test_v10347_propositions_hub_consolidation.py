"""Integration tests for v10.347 — Propositions Hub Consolidation (Option E sub-batch 3).

10 tests across 4 sections:
  Section 1 — Helper module (3 tests)
  Section 2 — Thin wrapper pages (3 tests)
  Section 3 — Consolidated page (2 tests)
  Section 4 — Audit gate G234 (2 tests)
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

def test_v10347_helper_exports_two_render_functions():
    """utils.propositions_hub_render exports 2 render_* functions."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.propositions_hub_render")
    import utils.propositions_hub_render as r
    for fn in ("render_propositions_performance",
               "render_propositions_workbench"):
        assert hasattr(r, fn), f"helper missing {fn}"
        assert callable(getattr(r, fn))


def test_v10347_helper_no_layer_violation():
    """utils/propositions_hub_render.py must not import from pages/."""
    text = (REPO / "utils" / "propositions_hub_render.py").read_text()
    assert "from pages." not in text, (
        "Helper imports from pages.* — layer violation. "
        "Use utils.page_* shims instead."
    )


def test_v10347_helper_module_size_reasonable():
    """utils/propositions_hub_render.py should be roughly 700-1,200 lines."""
    path = REPO / "utils" / "propositions_hub_render.py"
    assert path.exists()
    lines = len(path.read_text().splitlines())
    assert 700 <= lines <= 1200, (
        f"helper module is {lines} lines — outside expected 700-1,200 range"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Thin wrapper pages
# ────────────────────────────────────────────────────────────────────

def test_v10347_both_old_pages_are_thin_wrappers():
    """Both original propositions pages are now ≤40 lines."""
    expectations = {
        "27_propositions.py":           "render_propositions_performance",
        "92_propositions_workbench.py": "render_propositions_workbench",
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


def test_v10347_old_pages_preserve_access_gates():
    """Each thin wrapper still calls require_access with same permission."""
    expectations = {
        "27_propositions.py":           "sales_customer.propositions",
        "92_propositions_workbench.py": "shared.customer_360",
    }
    for page_name, perm in expectations.items():
        src = (REPO / "pages" / page_name).read_text()
        assert "require_access" in src
        assert perm in src, (
            f"{page_name} lost permission {perm}"
        )


def test_v10347_originals_backed_up():
    """Pre-v10.347 page bodies preserved under data/_v10347_backups/."""
    backup_dir = REPO / "data" / "_v10347_backups"
    assert backup_dir.exists(), "backup directory missing"
    for orig in ("27_propositions.py.before",
                 "92_propositions_workbench.py.before"):
        assert (backup_dir / orig).exists(), f"backup {orig} missing"
        # Original was large
        assert len((backup_dir / orig).read_text().splitlines()) > 200


# ────────────────────────────────────────────────────────────────────
# Section 3 — Consolidated page
# ────────────────────────────────────────────────────────────────────

def test_v10347_consolidated_page_imports_both_renders():
    """pages/117_propositions_hub.py imports both render functions."""
    src = (REPO / "pages" / "117_propositions_hub.py").read_text()
    for fn in ("render_propositions_performance",
               "render_propositions_workbench"):
        assert fn in src, f"117 doesn't import {fn}"
    # Must use an area selector
    assert "segmented_control" in src or "st.radio" in src


def test_v10347_consolidated_page_in_manifest():
    """pages/_manifest.json has 117_propositions_hub registered."""
    import json
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "117_propositions_hub.py" in m["pages"]
    entry = m["pages"]["117_propositions_hub.py"]
    assert entry["module_path"] == "sales_customer.propositions_hub"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Audit gate G234
# ────────────────────────────────────────────────────────────────────

def test_v10347_g234_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_propositions_hub_consolidation
    result = gate_propositions_hub_consolidation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G234"


def test_v10347_g234_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G234", gate_propositions_hub_consolidation)' in text

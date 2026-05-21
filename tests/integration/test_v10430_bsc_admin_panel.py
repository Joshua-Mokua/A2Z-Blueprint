"""Integration tests for v10.430 — BSC admin panel UI wire-up."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10430_panel_module_exists():
    path = REPO / "utils" / "bsc_admin_panel.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def render_bsc_health_dashboard",
        "def render_bsc_admin_actions",
        "CATEGORY_REPAIRS",
        "_resolve_repair_fn",
        "_category_status",
        "_render_category_details",
        "_render_repair_button",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10430_all_seven_categories_in_panel():
    """CATEGORY_REPAIRS dict must map all 7 BSC audit categories."""
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    for cat in (
        "staff_coverage", "kpi_completeness", "pillar_canonical",
        "weight_normalization", "library_alignment", "cascade_linkage",
        "duplicate_rows",
    ):
        assert f'"{cat}"' in text, f"CATEGORY_REPAIRS missing: {cat}"


def test_v10430_admin_page_imports_panel():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "from utils.bsc_admin_panel import" in text
    assert "render_bsc_health_dashboard" in text
    assert "render_bsc_admin_actions" in text


def test_v10430_admin_page_has_bsc_health_tab():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "🩺 BSC Health" in text


def test_v10430_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10430_repair_fns_resolve_correctly():
    """All repair dotted-paths in CATEGORY_REPAIRS should resolve to callable."""
    # Need to mock streamlit before import
    class MockSt:
        def __getattr__(self, name): return lambda *a, **k: None
    sys.modules['streamlit'] = MockSt()

    for k in list(sys.modules):
        if "bsc_admin_panel" in k:
            del sys.modules[k]
    from utils.bsc_admin_panel import CATEGORY_REPAIRS, _resolve_repair_fn

    for cat_key, cfg in CATEGORY_REPAIRS.items():
        repair_path = cfg.get("repair")
        if repair_path is not None:
            fn = _resolve_repair_fn(repair_path)
            assert fn is not None, f"Cannot resolve repair for {cat_key}: {repair_path}"
            assert callable(fn), f"Repair for {cat_key} is not callable"


def test_v10430_admin_role_gate_present():
    """Admin page must gate repair buttons behind role check."""
    text = (REPO / "pages" / "7_admin.py").read_text()
    # Search for the specific role check we added
    assert "can_run_repairs" in text or "_can_repair" in text


def test_v10430_panel_pure_ui_no_engine_logic():
    """The panel module should not contain BSC engine logic — only render."""
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    # The panel should NOT define audit/repair functions directly
    assert "def bsc_full_audit" not in text
    assert "def audit_actuals_pillars" not in text
    assert "def repair_bsc_completeness" not in text
    assert "def renormalize_actuals_weights" not in text
    assert "def fix_bsc_codes" not in text
    # But it should USE them via import
    assert "bsc_full_audit" in text  # used


def test_v10430_category_repairs_structure():
    """Each CATEGORY_REPAIRS entry has the right shape."""
    class MockSt:
        def __getattr__(self, name): return lambda *a, **k: None
    sys.modules['streamlit'] = MockSt()
    for k in list(sys.modules):
        if "bsc_admin_panel" in k:
            del sys.modules[k]
    from utils.bsc_admin_panel import CATEGORY_REPAIRS

    for cat_key, cfg in CATEGORY_REPAIRS.items():
        assert "label" in cfg, f"{cat_key} missing 'label'"
        assert "icon" in cfg, f"{cat_key} missing 'icon'"
        assert "help" in cfg, f"{cat_key} missing 'help'"
        assert "repair" in cfg, f"{cat_key} missing 'repair' key"
        if cfg["repair"] is not None:
            assert isinstance(cfg["repair"], tuple)
            assert len(cfg["repair"]) == 2  # (module, fn_name)


def test_v10430_repair_categories_count():
    """5 of 7 categories should have automated repair engines."""
    class MockSt:
        def __getattr__(self, name): return lambda *a, **k: None
    sys.modules['streamlit'] = MockSt()
    for k in list(sys.modules):
        if "bsc_admin_panel" in k:
            del sys.modules[k]
    from utils.bsc_admin_panel import CATEGORY_REPAIRS
    repairable = sum(1 for c in CATEGORY_REPAIRS.values() if c.get("repair") is not None)
    assert repairable == 5, f"Expected 5 repairable categories, got {repairable}"


def test_v10430_bsc_health_still_100():
    """v10.430 is UI-only — BSC health must remain 100%."""
    for k in list(sys.modules):
        if "bsc_audit" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    audit = bsc_full_audit()
    assert audit.overall_health_pct == 100.0


def test_v10430_g316_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10430_bsc_admin_panel
    r = gate_v10430_bsc_admin_panel()
    assert r["passed"], r.get("violations")

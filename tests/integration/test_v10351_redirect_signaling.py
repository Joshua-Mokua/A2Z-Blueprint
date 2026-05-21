"""Integration tests for v10.351 — Thin Redirect Signaling (Option E closure).

Plus the platform_hub UnboundLocalError fix.

13 tests across 4 sections:
  Section 1 — UnboundLocalError fix (2 tests)
  Section 2 — Redirect banner pattern (4 tests)
  Section 3 — Backward compatibility (3 tests)
  Section 4 — Audit gate G237 (4 tests)
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


# All 16 originals + their unified hub
ORIGINALS_TO_HUB = {
    "109_cims_live.py":              "pages/115_live_cockpits.py",
    "110_treasury_live.py":          "pages/115_live_cockpits.py",
    "111_credit_live.py":            "pages/115_live_cockpits.py",
    "112_compliance_live.py":        "pages/115_live_cockpits.py",
    "9_sbu.py":                      "pages/116_finance_hub.py",
    "10_opex.py":                    "pages/116_finance_hub.py",
    "52_mgmt_accounts.py":           "pages/116_finance_hub.py",
    "114_sbu_drilldown.py":          "pages/116_finance_hub.py",
    "27_propositions.py":            "pages/117_propositions_hub.py",
    "92_propositions_workbench.py":  "pages/117_propositions_hub.py",
    "11_competitor.py":              "pages/118_competitor_hub.py",
    "93_competitor_intelligence.py": "pages/118_competitor_hub.py",
    "91_systems_view.py":            "pages/119_platform_hub.py",
    "96_it_digital_pt1.py":          "pages/119_platform_hub.py",
    "97_it_digital_pt2.py":          "pages/119_platform_hub.py",
    "98_platform_health.py":         "pages/119_platform_hub.py",
}


# ────────────────────────────────────────────────────────────────────
# Section 1 — UnboundLocalError fix
# ────────────────────────────────────────────────────────────────────

def test_v10351_render_systems_view_no_shadowing_imports():
    """render_systems_view must not import names already at module top
    inside its body — those become unbound locals."""
    import ast
    tree = ast.parse((REPO / "utils" / "platform_hub_render.py").read_text())

    # Top-level names imported
    top_imports = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                top_imports.add(a.asname or a.name)

    # Find render_systems_view + inspect its inner imports
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "render_systems_view":
            shadowing = []
            for node in ast.walk(fn):
                if isinstance(node, (ast.Import, ast.ImportFrom)) and node is not fn:
                    for a in node.names:
                        nm = a.asname or a.name
                        if nm in top_imports and nm != "*":
                            shadowing.append(nm)
            assert not shadowing, (
                f"render_systems_view re-imports {shadowing} — would shadow "
                f"the module-top imports and cause UnboundLocalError"
            )
            return
    assert False, "render_systems_view not found"


def test_v10351_get_stock_snapshot_accessible_in_systems_view():
    """get_stock_snapshot is imported at module top so it's available
    throughout render_systems_view."""
    text = (REPO / "utils" / "platform_hub_render.py").read_text()
    # Top-level import line
    top_line = [
        l for l in text.splitlines()[:60]
        if "get_stock_snapshot" in l and "from utils.system_stocks" in l
    ]
    assert top_line, "get_stock_snapshot not imported at module top"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Redirect banner pattern
# ────────────────────────────────────────────────────────────────────

def test_v10351_all_16_originals_have_redirect_banner():
    """Each of the 16 originals carries the v10.351 redirect marker."""
    for page_name in ORIGINALS_TO_HUB:
        path = REPO / "pages" / page_name
        assert path.exists(), f"missing {page_name}"
        text = path.read_text()
        assert "v10.351 — Thin redirect" in text, (
            f"{page_name} missing v10.351 redirect banner"
        )


def test_v10351_each_original_links_to_correct_hub():
    """Each original's banner points to the right unified hub."""
    for page_name, hub_path in ORIGINALS_TO_HUB.items():
        path = REPO / "pages" / page_name
        text = path.read_text()
        assert hub_path in text, (
            f"{page_name} does not link to {hub_path}"
        )


def test_v10351_banner_uses_st_info_and_page_link():
    """Banner uses st.info for visual + st.page_link for navigation."""
    sample = (REPO / "pages" / "9_sbu.py").read_text()
    assert "st.info(" in sample
    assert "st.page_link(" in sample


def test_v10351_banner_after_require_access():
    """Banner is positioned AFTER require_access so denied users don't
    see the redirect either (consistent gating)."""
    for page_name in ("9_sbu.py", "27_propositions.py", "109_cims_live.py"):
        text = (REPO / "pages" / page_name).read_text()
        ra_pos = text.index("require_access(")
        banner_pos = text.index("v10.351 — Thin redirect")
        assert ra_pos < banner_pos, (
            f"{page_name}: banner before require_access — denied users "
            f"would see the redirect"
        )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Backward compatibility
# ────────────────────────────────────────────────────────────────────

def test_v10351_originals_still_call_render_function():
    """Each original still calls its render function below the banner
    (bookmarked URLs keep working)."""
    expectations = {
        "9_sbu.py":                      "render_sbu_performance",
        "10_opex.py":                    "render_opex",
        "27_propositions.py":            "render_propositions_performance",
        "109_cims_live.py":              "render_cims_cockpit",
        "91_systems_view.py":            "render_systems_view",
    }
    for page_name, render_fn in expectations.items():
        text = (REPO / "pages" / page_name).read_text()
        assert f"{render_fn}(actor)" in text, (
            f"{page_name} no longer calls {render_fn}(actor)"
        )


def test_v10351_all_originals_still_under_threshold():
    """All 16 originals stay ≤55 lines (banner + thin wrapper)."""
    over = []
    for page_name in ORIGINALS_TO_HUB:
        lines = len((REPO / "pages" / page_name).read_text().splitlines())
        if lines > 55:
            over.append((page_name, lines))
    assert not over, f"Pages over 55 lines: {over}"


def test_v10351_all_originals_preserve_access_gate():
    """Each original still calls require_access — gating not weakened."""
    for page_name in ORIGINALS_TO_HUB:
        text = (REPO / "pages" / page_name).read_text()
        assert "require_access" in text, (
            f"{page_name} lost require_access"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Audit gate G237
# ────────────────────────────────────────────────────────────────────

def test_v10351_g237_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_redirect_signaling
    result = gate_redirect_signaling()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G237"


def test_v10351_g237_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G237", gate_redirect_signaling)' in text


def test_v10351_all_pages_still_smoke_pass():
    """All 123+ pages still smoke-test PASS after redirects."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_all
    r = smoke_test_all()
    assert r["failed"] == 0, f"Smoke regression: {r['failures'][:3]}"
    assert r["pass_rate"] == 1.0


def test_v10351_backups_exist():
    """Pre-v10.351 thin-wrapper bodies preserved (Pattern M)."""
    backup_dir = REPO / "data" / "_v10351_backups"
    assert backup_dir.exists()
    assert len(list(backup_dir.glob("*.py.before"))) == 16

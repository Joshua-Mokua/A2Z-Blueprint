"""Integration tests for v10.345 — Live Cockpit Consolidation (Option E sub-batch 1).

10 tests across 4 sections:
  Section 1 — Helper module (3 tests)
  Section 2 — Thin wrapper pages (3 tests)
  Section 3 — Consolidated page (2 tests)
  Section 4 — Audit gate G232 (2 tests)
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

def test_v10345_helper_exports_four_render_functions():
    """utils.live_cockpit_render exports 4 render_*_cockpit fns."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.live_cockpit_render")
    import utils.live_cockpit_render as r
    for fn in ("render_cims_cockpit", "render_treasury_cockpit",
               "render_credit_cockpit", "render_compliance_cockpit"):
        assert hasattr(r, fn), f"helper missing {fn}"
        assert callable(getattr(r, fn))


def test_v10345_cache_helpers_domain_namespaced():
    """Cache helpers use domain prefix (no collisions across domains)."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    _reimport("utils.live_cockpit_render")
    import utils.live_cockpit_render as r
    helpers = [
        n for n in dir(r)
        if "_cached_" in n and n.startswith("_") and not n.startswith("__")
    ]
    # Each helper name must start with one of the 4 domain prefixes
    valid_prefixes = ("_cims_cached_", "_treasury_cached_",
                      "_credit_cached_", "_compliance_cached_")
    for h in helpers:
        assert any(h.startswith(p) for p in valid_prefixes), (
            f"cache helper {h} does not have a domain prefix"
        )
    # Sanity check: each domain has at least one cache helper
    for prefix in valid_prefixes:
        domain_helpers = [h for h in helpers if h.startswith(prefix)]
        assert domain_helpers, f"no cache helpers found for {prefix}"


def test_v10345_helper_module_size_reasonable():
    """utils/live_cockpit_render.py should be in the 1500-2500 line range
    (extracted bodies of 4 pages combined)."""
    path = REPO / "utils" / "live_cockpit_render.py"
    assert path.exists()
    lines = len(path.read_text().splitlines())
    assert 1500 <= lines <= 2500, (
        f"helper module is {lines} lines — outside expected 1500-2500 range"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Thin wrapper pages
# ────────────────────────────────────────────────────────────────────

def test_v10345_four_old_pages_are_thin_wrappers():
    """Each of the 4 original cockpit pages is now ≤40 lines."""
    expectations = {
        "109_cims_live.py":       "render_cims_cockpit",
        "110_treasury_live.py":   "render_treasury_cockpit",
        "111_credit_live.py":     "render_credit_cockpit",
        "112_compliance_live.py": "render_compliance_cockpit",
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


def test_v10345_old_pages_preserve_access_gates():
    """Each thin wrapper still calls require_access with same permission."""
    expectations = {
        "109_cims_live.py":       "operations.cims_live",
        "110_treasury_live.py":   "treasury_alm.treasury_live",
        "111_credit_live.py":     "credit.credit_live",
        "112_compliance_live.py": "compliance_regulatory.compliance_live",
    }
    for page_name, perm in expectations.items():
        src = (REPO / "pages" / page_name).read_text()
        assert "require_access" in src
        assert perm in src, (
            f"{page_name} lost permission {perm}"
        )


def test_v10345_originals_backed_up():
    """Pre-v10.345 page bodies preserved under data/_v10345_backups/."""
    backup_dir = REPO / "data" / "_v10345_backups"
    assert backup_dir.exists(), "backup directory missing"
    for orig in ("109_cims_live.py.before", "110_treasury_live.py.before",
                 "111_credit_live.py.before", "112_compliance_live.py.before"):
        assert (backup_dir / orig).exists(), f"backup {orig} missing"
        # Backup must be the original (large) body
        assert len((backup_dir / orig).read_text().splitlines()) > 400


# ────────────────────────────────────────────────────────────────────
# Section 3 — Consolidated page
# ────────────────────────────────────────────────────────────────────

def test_v10345_consolidated_page_imports_all_four_renders():
    """pages/115_live_cockpits.py imports all 4 render functions."""
    src = (REPO / "pages" / "115_live_cockpits.py").read_text()
    for fn in ("render_cims_cockpit", "render_treasury_cockpit",
               "render_credit_cockpit", "render_compliance_cockpit"):
        assert fn in src, f"115 doesn't import {fn}"
    # Must use a domain selector (segmented_control or radio fallback)
    assert "segmented_control" in src or "st.radio" in src


def test_v10345_consolidated_page_in_manifest():
    """pages/_manifest.json has 115_live_cockpits registered."""
    import json
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    assert "115_live_cockpits.py" in m["pages"]
    entry = m["pages"]["115_live_cockpits.py"]
    assert entry["module_path"] == "operations.live_cockpits"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Audit gate G232
# ────────────────────────────────────────────────────────────────────

def test_v10345_g232_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_live_cockpit_consolidation
    result = gate_live_cockpit_consolidation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G232"


def test_v10345_g232_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G232", gate_live_cockpit_consolidation)' in text

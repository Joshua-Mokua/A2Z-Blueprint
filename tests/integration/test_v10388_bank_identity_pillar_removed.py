"""Integration tests for v10.388 — Bank Identity pillar weights form removed.

The v10.384 deprecation promise: "removed in v10.388". Promise kept.

8 tests across 3 sections.
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


def _bank_identity_section(text: str) -> str:
    """Return the substring of pages/7_admin.py up to the Branches section.

    The Bank Identity section is in the org_config admin area before the
    "elif Branches" block.
    """
    pos = text.find('elif "Branches" in _org_view')
    return text[:pos] if pos > 0 else text


# ────────────────────────────────────────────────────────────────────
# Section 1 — Doc structure
# ────────────────────────────────────────────────────────────────────

def test_v10388_design_doc_has_8_parts():
    p = REPO / "docs" / "BANK_IDENTITY_PILLAR_WEIGHTS_REMOVED_v10.388.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 9):
        assert f"## Part {part}" in text, f"missing Part {part}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Dead form removed
# ────────────────────────────────────────────────────────────────────

def test_v10388_pillar_widgets_removed_from_bank_identity():
    """The 4 pillar weight number_inputs should be gone from Bank Identity."""
    admin = REPO / "pages" / "7_admin.py"
    section = _bank_identity_section(admin.read_text())
    for removed in ("_pw1,_pw2,_pw3,_pw4", "_fin_wt", "_cust_wt",
                    "_ops_wt", "_ppl_wt"):
        assert removed not in section, (
            f"Bank Identity section still has {removed!r}"
        )


def test_v10388_dead_branch_write_removed():
    """The dead-branch write _org["pillar_weights"] = {...} must be gone."""
    admin = REPO / "pages" / "7_admin.py"
    section = _bank_identity_section(admin.read_text())
    assert '_org["pillar_weights"] = {' not in section, (
        'dead-branch write still present'
    )


def test_v10388_sum_validation_gate_removed():
    """The 'if _wt_total != 100' check is gone — no widgets to total."""
    admin = REPO / "pages" / "7_admin.py"
    section = _bank_identity_section(admin.read_text())
    assert "_wt_total" not in section, (
        "_wt_total reference still in Bank Identity section"
    )


def test_v10388_redirect_notice_present():
    admin = REPO / "pages" / "7_admin.py"
    section = _bank_identity_section(admin.read_text())
    assert "Pillar weights moved" in section
    assert "v10.388" in section


# ────────────────────────────────────────────────────────────────────
# Section 3 — Working tab unchanged + G273 + admin parses
# ────────────────────────────────────────────────────────────────────

def test_v10388_kpi_library_tab_still_functional():
    """v10.386 contract must still hold post-v10.388."""
    admin = REPO / "pages" / "7_admin.py"
    text = admin.read_text()
    assert "save_pillar_weights" in text, "v10.386 contract broken"
    assert "get_pillar_weights_history" in text
    assert "CANONICAL_PILLARS" in text


def test_v10388_admin_parses_cleanly():
    import ast
    admin = REPO / "pages" / "7_admin.py"
    ast.parse(admin.read_text())


def test_v10388_g273_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_v10388_bank_identity_pillar_removed
    r = gate_v10388_bank_identity_pillar_removed()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G273"

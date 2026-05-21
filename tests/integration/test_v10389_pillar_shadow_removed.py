"""Integration tests for v10.389 — Pillar shadow weights removed.

Removed 'weight' field from each entry in kpi_library.json::pillars[].
Structural fields (id, name, color) preserved. Canonical pillar_weights
dict unchanged.

9 tests across 3 sections.
"""

import json
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
# Section 1 — Data file state
# ────────────────────────────────────────────────────────────────────

def test_v10389_no_pillar_entry_has_weight_field():
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    pillars = lib.get("pillars", [])
    assert isinstance(pillars, list)
    for i, p in enumerate(pillars):
        assert isinstance(p, dict)
        assert "weight" not in p, (
            f"pillars[{i}] still has 'weight' field: {p}"
        )


def test_v10389_pillars_still_have_4_entries_with_structural_fields():
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    pillars = lib.get("pillars", [])
    assert len(pillars) == 4
    for p in pillars:
        for required in ("id", "name", "color"):
            assert required in p, f"pillar missing {required}: {p}"


def test_v10389_canonical_pillar_weights_dict_unchanged():
    """The CANONICAL dict (separate from shadow) must still be present and complete."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    pw = lib.get("pillar_weights", {})
    assert isinstance(pw, dict)
    for canonical_pillar in ("Financial", "Customer Focus",
                             "Operational Excellence", "People & Learning"):
        assert canonical_pillar in pw, (
            f"canonical pillar_weights missing {canonical_pillar!r}"
        )
    # Sum should still be ~1.0
    total = sum(float(v) for v in pw.values())
    assert abs(total - 1.0) <= 0.001


def test_v10389_backup_preserved():
    backup = REPO / "data" / "_v10389_backups" / "kpi_library.json.before"
    assert backup.exists(), "v10.389 backup file should be preserved"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Doc + canonical accessor health
# ────────────────────────────────────────────────────────────────────

def test_v10389_design_doc_has_9_parts():
    p = REPO / "docs" / "PILLAR_SHADOW_WEIGHTS_REMOVED_v10.389.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 10):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10389_design_doc_surfaces_finding_n7():
    """The discovered get_active_kpis bug should be documented."""
    p = REPO / "docs" / "PILLAR_SHADOW_WEIGHTS_REMOVED_v10.389.md"
    text = p.read_text()
    assert "Finding N7" in text or "N7" in text
    assert "get_active_kpis" in text


def test_v10389_health_check_shadow_field_now_false():
    """The shadow_pillars_field diagnostic should flip to False."""
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import health_check
    hc = health_check()
    assert hc["shadow_pillars_field"] is False, (
        f"health_check.shadow_pillars_field should be False after v10.389, "
        f"got {hc['shadow_pillars_field']!r}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — G274 + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10389_g274_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_v10389_pillar_shadow_removed
    r = gate_v10389_pillar_shadow_removed()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G274"


def test_v10389_canonical_pillar_weights_module_unaffected():
    """v10.384 canonical accessor module untouched by v10.389."""
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import (
        get_pillar_weights, validate_pillar_weights,
        DEFAULT_BALANCED_WEIGHTS, CANONICAL_PILLARS,
    )
    # Canonical still functional
    pw = get_pillar_weights()
    for p in CANONICAL_PILLARS:
        assert p in pw
    # Validation still works
    ok, _ = validate_pillar_weights(DEFAULT_BALANCED_WEIGHTS)
    assert ok

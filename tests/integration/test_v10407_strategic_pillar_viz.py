"""Integration tests for v10.407 — Strategic Pillar Visualization (E2).

Per QA standards Enhancement #2: Strategic pillar visualization linking
individual targets to bank's 4 pillars.

11 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine module presence
# ────────────────────────────────────────────────────────────────────

def test_v10407_engine_module_exists():
    """utils/pillar_impact_engine.py exists with required API."""
    path = REPO / "utils" / "pillar_impact_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def pillar_breakdown_for_staff",
        "def pillar_breakdown_for_manager",
        "def bank_pillar_weights",
        "def kpi_to_strategic_pillar_map",
        "class PillarSlice",
        "class PillarBreakdown",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10407_engine_has_caches():
    """Module has TARGET_CACHE + ACTUAL_CACHE for performance."""
    text = (REPO / "utils" / "pillar_impact_engine.py").read_text()
    assert "_TARGET_CACHE" in text
    assert "_ACTUAL_CACHE" in text
    assert "clear_cache" in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Engine behavior
# ────────────────────────────────────────────────────────────────────

def test_v10407_bank_pillar_weights_sum_to_one():
    """Bank pillar weights sum to ~1.0."""
    for k in list(sys.modules):
        if "pillar_impact" in k:
            del sys.modules[k]
    from utils.pillar_impact_engine import bank_pillar_weights
    w = bank_pillar_weights()
    assert len(w) >= 3
    total = sum(w.values())
    assert abs(total - 1.0) < 0.01, f"sum = {total}"


def test_v10407_kpi_pillar_map_populated():
    """kpi→pillar map has reasonable count."""
    for k in list(sys.modules):
        if "pillar_impact" in k:
            del sys.modules[k]
    from utils.pillar_impact_engine import kpi_to_strategic_pillar_map
    m = kpi_to_strategic_pillar_map()
    assert len(m) > 50, f"only {len(m)} KPIs in map"


def test_v10407_md_breakdown_works():
    """MD breakdown returns valid structure."""
    for k in list(sys.modules):
        if "pillar_impact" in k:
            del sys.modules[k]
    from utils.pillar_impact_engine import pillar_breakdown_for_staff
    bd = pillar_breakdown_for_staff("300001", "2026")
    assert bd.role
    assert bd.total_kpis > 0
    assert len(bd.pillars) > 0
    # Each pillar should have positive kpi_count
    for p in bd.pillars:
        assert p.kpi_count > 0


def test_v10407_subtree_breakdown_returns_team_summary():
    """Manager subtree breakdown returns team_pillar_summary."""
    for k in list(sys.modules):
        if "pillar_impact" in k or "manager_rollup" in k:
            del sys.modules[k]
    from utils.pillar_impact_engine import pillar_breakdown_for_manager
    team = pillar_breakdown_for_manager("300002", "2026")
    assert team["manager_code"] == "300002"
    assert team["total_subordinates"] >= 100
    assert "team_pillar_summary" in team
    assert len(team["team_pillar_summary"]) > 0


# ────────────────────────────────────────────────────────────────────
# Section 3 — Cascade page wiring
# ────────────────────────────────────────────────────────────────────

def test_v10407_cascade_imports_engine():
    """Cascade page imports pillar_breakdown_for_staff."""
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "from utils.pillar_impact_engine import" in text
    assert "pillar_breakdown_for_staff" in text


def test_v10407_strategic_impact_tab_in_defs():
    """Strategic impact tab added to _tab_defs."""
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "🎯 Strategic impact" in text
    assert '"strategic_impact"' in text


def test_v10407_strategic_tab_handler_present():
    """Tab handler block exists."""
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert '_in_tab("strategic_impact")' in text
    assert "_tab_visible_strategic" in text


def test_v10407_tab_visible_includes_strategic():
    """tab_visible_cascade includes strategic_impact (visible to all)."""
    text = (REPO / "utils" / "core_audit.py").read_text()
    assert '"strategic_impact"' in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — State + gate
# ────────────────────────────────────────────────────────────────────

def test_v10407_engine_state_preserved():
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10407_g293_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10407_strategic_pillar_visualization
    r = gate_v10407_strategic_pillar_visualization()
    assert r["passed"], r.get("violations")

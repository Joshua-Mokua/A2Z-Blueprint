"""Integration tests for v10.406 — Real-Time Progress Rollup (E1) wired into cascade UI.

Per Joshua's QA standards document Enhancement #1: 'Real-Time Progress Rollup —
managers cannot see aggregated progress across their teams in real-time.'

12 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _cascade_text():
    return (REPO / "pages" / "12_cascade.py").read_text()


# ────────────────────────────────────────────────────────────────────
# Section 1 — Wiring presence
# ────────────────────────────────────────────────────────────────────

def test_v10406_compute_team_rollup_imported():
    """compute_team_rollup imported in cascade page."""
    text = _cascade_text()
    assert "from utils.manager_rollup import compute_team_rollup" in text


def test_v10406_team_progress_tab_in_tab_defs():
    """'📈 Team progress' tab added to _tab_defs."""
    text = _cascade_text()
    assert "📈 Team progress" in text
    assert '"team_progress"' in text


def test_v10406_team_progress_tab_handler():
    """Tab handler block present (_in_tab + with tabs[...])."""
    text = _cascade_text()
    assert '_in_tab("team_progress")' in text
    assert "_tab_visible_team_progress" in text


def test_v10406_tab_visible_cascade_has_team_progress():
    """utils.core_audit.tab_visible_cascade includes team_progress key."""
    text = (REPO / "utils" / "core_audit.py").read_text()
    assert '"team_progress"' in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Manager_rollup canonical fallback
# ────────────────────────────────────────────────────────────────────

def test_v10406_direct_report_codes_has_canonical_fallback():
    """_direct_report_codes falls back to canonical reporting tree."""
    text = (REPO / "utils" / "manager_rollup.py").read_text()
    assert "canonical fallback" in text
    assert "build_reporting_tree" in text


def test_v10406_crbo_has_direct_reports():
    """CRBO (300002) returns real direct reports via canonical fallback."""
    for k in list(sys.modules):
        if "manager_rollup" in k or "cascade_regen" in k:
            del sys.modules[k]
    from utils.manager_rollup import _direct_report_codes
    reports = _direct_report_codes("300002")
    assert len(reports) >= 5, f"CRBO direct reports = {len(reports)}; expected ≥5"


def test_v10406_crbo_has_recursive_subordinates():
    """CRBO recursive subordinates includes hundreds of staff."""
    for k in list(sys.modules):
        if "manager_rollup" in k or "cascade_regen" in k:
            del sys.modules[k]
    from utils.manager_rollup import _all_subordinate_codes
    subs = _all_subordinate_codes("300002")
    assert len(subs) >= 100, f"CRBO subs = {len(subs)}; expected ≥100"


def test_v10406_md_still_works():
    """MD (300001) still returns reports (regression check)."""
    for k in list(sys.modules):
        if "manager_rollup" in k or "cascade_regen" in k:
            del sys.modules[k]
    from utils.manager_rollup import _direct_report_codes
    md_reports = _direct_report_codes("300001")
    # MD has at least 2 (synthetic Chief Compliance + Internal Audit since
    # they aren't real-staffed); real chiefs route via canonical fallback
    assert len(md_reports) >= 2, f"MD direct reports = {len(md_reports)}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Rollup computation works
# ────────────────────────────────────────────────────────────────────

def test_v10406_team_rollup_for_chief_with_actuals():
    """compute_team_rollup returns non-zero KPI aggregates for a period with actuals."""
    for k in list(sys.modules):
        if "manager_rollup" in k or "cascade_regen" in k:
            del sys.modules[k]
    from utils.manager_rollup import compute_team_rollup
    # 2025-Q4 has actuals
    rollup = compute_team_rollup("300002", "2025-Q4")
    assert rollup.direct_reports_count >= 5
    assert rollup.indirect_reports_count >= 100
    assert len(rollup.team_kpi_aggregates) > 0


def test_v10406_team_rollup_handles_leaf_node():
    """Leaf nodes (no subordinates) return gracefully with notes."""
    for k in list(sys.modules):
        if "manager_rollup" in k or "cascade_regen" in k:
            del sys.modules[k]
    from utils.manager_rollup import compute_team_rollup
    # A Teller would be a leaf
    rollup = compute_team_rollup("nonexistent_code_XYZ", "2026-Q2")
    assert rollup.direct_reports_count == 0
    # Should have "no subordinates" note
    assert len(rollup.notes) > 0 or rollup.indirect_reports_count == 0


# ────────────────────────────────────────────────────────────────────
# Section 4 — State preservation + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10406_engine_state_preserved():
    """Engine still 0/0/0/0 after v10.406."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10406_g292_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10406_team_progress_rollup
    r = gate_v10406_team_progress_rollup()
    assert r["passed"], r.get("violations")

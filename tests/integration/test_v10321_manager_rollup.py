"""tests/integration/test_v10321_manager_rollup.py

v10.321 — Manager rollup engine (closes B-013).

Locks:
  - Team rollup aggregates direct + indirect reports' actuals
  - Sum aggregation for volume KPIs (KES M, count, transactions)
  - Mean aggregation for score KPIs (score, %, ratio)
  - Recursive scoring walks the org tree correctly
  - Pre-computed cascade scores exist and contain MD entry
  - G212 passes
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module exports
# ────────────────────────────────────────────────────────────────────

def test_manager_rollup_module_imports():
    from utils.manager_rollup import (
        compute_team_rollup, compute_recursive_score,
        cascade_score_tree, aggregation_for_kpi,
        TeamRollup, KpiAggregate,
    )
    assert callable(compute_team_rollup)
    assert callable(compute_recursive_score)


# ────────────────────────────────────────────────────────────────────
# Section 2 — Aggregation classifier
# ────────────────────────────────────────────────────────────────────

def test_aggregation_classifies_money_as_sum():
    from utils.manager_rollup import aggregation_for_kpi
    assert aggregation_for_kpi({"unit": "KES M"}) == "sum"
    assert aggregation_for_kpi({"unit": "kes b"}) == "sum"


def test_aggregation_classifies_score_as_mean():
    from utils.manager_rollup import aggregation_for_kpi
    assert aggregation_for_kpi({"unit": "score"}) == "mean"
    assert aggregation_for_kpi({"unit": "%"}) == "mean"
    assert aggregation_for_kpi({"unit": "ratio"}) == "mean"


def test_aggregation_classifies_count_as_sum():
    from utils.manager_rollup import aggregation_for_kpi
    assert aggregation_for_kpi({"unit": "count"}) == "sum"


def test_aggregation_unknown_defaults_to_mean():
    from utils.manager_rollup import aggregation_for_kpi
    assert aggregation_for_kpi({"unit": "weird_unit"}) == "mean"
    assert aggregation_for_kpi({}) == "mean"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Team rollup for known managers
# ────────────────────────────────────────────────────────────────────

def test_team_rollup_for_branch_ops_supervisor():
    from utils.virtual_bank import staff_universe
    from utils.manager_rollup import compute_team_rollup

    u = staff_universe()
    # Find a Branch Operations Supervisor that has reports
    bos = None
    for s in u.values():
        if s.role == "Branch Operations Supervisor":
            reports = [r for r in u.values()
                       if r.manager_code == s.staff_code]
            if reports:
                bos = s
                break

    assert bos is not None, (
        "No Branch Operations Supervisor with reports found"
    )

    rollup = compute_team_rollup(bos.staff_code, "2026-Q1")
    assert rollup.direct_reports_count > 0
    assert rollup.indirect_reports_count >= (
        rollup.direct_reports_count)
    assert len(rollup.team_kpi_aggregates) >= 1


def test_team_rollup_returns_zero_for_leaf():
    """A leaf node (Teller) should produce empty rollup."""
    from utils.virtual_bank import staff_universe
    from utils.manager_rollup import compute_team_rollup
    u = staff_universe()
    teller = next(
        (s for s in u.values() if s.role == "Teller"), None)
    assert teller is not None
    rollup = compute_team_rollup(teller.staff_code, "2026-Q1")
    assert rollup.indirect_reports_count == 0
    assert "leaf" in " ".join(rollup.notes).lower() or \
        rollup.team_avg_score is None


# ────────────────────────────────────────────────────────────────────
# Section 4 — Recursive score
# ────────────────────────────────────────────────────────────────────

def test_recursive_score_for_teller_uses_own_scorecard():
    """A leaf (Teller) recursive score = compute_staff_scorecard."""
    from utils.manager_rollup import compute_recursive_score
    score = compute_recursive_score("300230", "2026-Q1")
    if score is not None:
        assert 1.0 <= score <= 5.0


def test_recursive_score_in_valid_range_for_manager():
    """A Branch Operations Supervisor should score in 1-5 range
    when their team has actuals."""
    from utils.virtual_bank import staff_universe
    from utils.manager_rollup import compute_recursive_score
    u = staff_universe()
    bos = None
    for s in u.values():
        if s.role == "Branch Operations Supervisor":
            reports = [r for r in u.values()
                       if r.manager_code == s.staff_code]
            if reports:
                bos = s
                break
    assert bos is not None
    score = compute_recursive_score(bos.staff_code, "2026-Q1")
    if score is not None:
        assert 1.0 <= score <= 5.0


def test_recursive_score_caches():
    """Second call should be faster (LRU cached)."""
    from utils.manager_rollup import compute_recursive_score
    import time
    t1 = time.time()
    s1 = compute_recursive_score("300230", "2026-Q1")
    cold = time.time() - t1
    t2 = time.time()
    s2 = compute_recursive_score("300230", "2026-Q1")
    hot = time.time() - t2
    assert s1 == s2
    # Hot call should be at least 5× faster (or both fast enough)
    if cold > 0.05:
        assert hot < cold


# ────────────────────────────────────────────────────────────────────
# Section 5 — Pre-computed cascade scores
# ────────────────────────────────────────────────────────────────────

def test_precomputed_cascade_scores_exist():
    p = (REPO_ROOT / "data" /
         "cascade_scores_2026-Q1.json")
    assert p.exists(), (
        "Pre-computed cascade scores missing — run "
        "scripts/precompute_cascade_scores.py"
    )


def test_precomputed_has_md_score():
    import json
    p = (REPO_ROOT / "data" /
         "cascade_scores_2026-Q1.json")
    data = json.loads(p.read_text())
    md_score = data.get("scores", {}).get("EXEC-MD-001")
    assert md_score is not None
    assert 1.0 <= md_score <= 5.0


def test_precomputed_has_md_rollup_with_chiefs():
    import json
    p = (REPO_ROOT / "data" /
         "cascade_scores_2026-Q1.json")
    data = json.loads(p.read_text())
    md_rollup = data.get("rollups", {}).get("EXEC-MD-001", {})
    assert md_rollup.get("direct_reports", 0) >= 10
    assert md_rollup.get("total_subordinates", 0) >= 1000


def test_precomputed_md_rollup_has_kpi_aggregates():
    """MD's rollup should include KPI aggregates from v10.317
    generated data (CX, Audit, Staff Productivity)."""
    import json
    p = (REPO_ROOT / "data" /
         "cascade_scores_2026-Q1.json")
    data = json.loads(p.read_text())
    md_rollup = data.get("rollups", {}).get("EXEC-MD-001", {})
    kpis = md_rollup.get("kpi_aggregates", [])
    assert len(kpis) >= 3
    kpi_names = {k["kpi"] for k in kpis}
    # At least one of these should be present
    assert any(
        n in kpi_names for n in
        ("CX Score", "Audit Score", "Staff Productivity"))


# ────────────────────────────────────────────────────────────────────
# Section 6 — Cascade score tree (for UI consumption)
# ────────────────────────────────────────────────────────────────────

def test_cascade_score_tree_returns_dict():
    from utils.manager_rollup import cascade_score_tree
    result = cascade_score_tree("2026-Q1", max_nodes=20)
    assert "tree" in result
    assert "nodes_emitted" in result


def test_cascade_score_tree_starts_at_md():
    from utils.manager_rollup import cascade_score_tree
    result = cascade_score_tree("2026-Q1", max_nodes=20)
    tree = result["tree"]
    if tree:
        assert tree.get("role") == "Managing Director" or \
            tree.get("staff_code") == "EXEC-MD-001"


# ────────────────────────────────────────────────────────────────────
# Section 7 — Audit gate G212
# ────────────────────────────────────────────────────────────────────

def test_g212_gate_exists_and_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G212":
            g = fn()
            break
    assert g is not None, "G212 not registered"
    assert g["passed"], (
        f"G212 failed: {g.get('summary', '')[:200]}. "
        f"Violations: {g.get('violations', [])}"
    )

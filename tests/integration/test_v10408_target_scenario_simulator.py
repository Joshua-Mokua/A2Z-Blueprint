"""Integration tests for v10.408 — Target Scenario Simulator (E3).

Per QA standards Enhancement #3: target-cascade what-if simulator.

12 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine module
# ────────────────────────────────────────────────────────────────────

def test_v10408_engine_module_exists():
    path = REPO / "utils" / "target_scenario_simulator.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def load_current_scenario",
        "def simulate_alternative",
        "def compute_scenario",
        "def split_equal",
        "def split_weighted_by_history",
        "def _classify_likelihood",
        "class ScenarioResult",
        "class ComparisonReport",
        "class AllocationRow",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10408_simulator_is_pure_compute():
    """Simulator must not write to target_cascade.json."""
    text = (REPO / "utils" / "target_scenario_simulator.py").read_text()
    # Should NOT have these write patterns
    assert "write_text" not in text or text.count("write_text") == 0
    assert ".save()" not in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Engine behavior
# ────────────────────────────────────────────────────────────────────

def test_v10408_load_current_scenario_crbo():
    """Loading CRBO's PBT cascade returns scenario with reports."""
    for k in list(sys.modules):
        if "target_scenario" in k:
            del sys.modules[k]
    from utils.target_scenario_simulator import load_current_scenario
    cur = load_current_scenario("300002", "PBT", "2026")
    assert cur is not None
    assert cur.kpi == "PBT"
    assert cur.period == "2026"
    assert len(cur.rows) >= 2
    # Coverage should be close to 100%
    assert 90 <= cur.coverage_pct <= 110


def test_v10408_simulate_alternative_returns_comparison():
    """simulate_alternative returns ComparisonReport with both sides."""
    for k in list(sys.modules):
        if "target_scenario" in k:
            del sys.modules[k]
    from utils.target_scenario_simulator import (
        load_current_scenario, simulate_alternative
    )
    cur = load_current_scenario("300002", "PBT", "2026")
    if not cur or len(cur.rows) < 2:
        return  # skip if no data
    alt = [
        {"to_code": cur.rows[0].to_code, "amount": cur.total_target * 0.6},
        {"to_code": cur.rows[1].to_code, "amount": cur.total_target * 0.4},
    ]
    report = simulate_alternative("300002", "PBT", "2026", alt)
    assert report is not None
    assert report.kpi == "PBT"
    assert report.current is not None
    assert report.alternative is not None
    assert len(report.alternative.rows) == 2


def test_v10408_split_equal():
    for k in list(sys.modules):
        if "target_scenario" in k:
            del sys.modules[k]
    from utils.target_scenario_simulator import split_equal
    result = split_equal(1000.0, ["A", "B", "C", "D"])
    assert len(result) == 4
    for r in result:
        assert r["amount"] == 250.0


def test_v10408_classify_likelihood_bands():
    for k in list(sys.modules):
        if "target_scenario" in k:
            del sys.modules[k]
    from utils.target_scenario_simulator import _classify_likelihood
    # Below historical capacity → very likely
    label, score = _classify_likelihood(50.0, 100.0, 100.0)
    assert "very likely" in label.lower()
    assert score >= 0.9
    # Above 1.5x → unrealistic
    label2, score2 = _classify_likelihood(200.0, 100.0, 100.0)
    assert "unrealistic" in label2.lower()
    assert score2 <= 0.2
    # No history → unknown
    label3, score3 = _classify_likelihood(100.0, None, None)
    assert "unknown" in label3.lower()


def test_v10408_coverage_warning_under_allocated():
    """Under-allocation generates a warning note."""
    for k in list(sys.modules):
        if "target_scenario" in k:
            del sys.modules[k]
    from utils.target_scenario_simulator import compute_scenario
    result = compute_scenario(
        name="test",
        manager_code="300002",
        kpi="PBT",
        period="2026",
        allocations=[
            {"to_code": "300012", "amount": 100.0},
            {"to_code": "300013", "amount": 100.0},
        ],
        total_target=1000.0,
    )
    # 200/1000 = 20% coverage
    assert result.coverage_pct < 50
    assert any("Under-allocated" in n for n in result.notes)


# ────────────────────────────────────────────────────────────────────
# Section 3 — Cascade page wiring
# ────────────────────────────────────────────────────────────────────

def test_v10408_cascade_imports_simulator():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "from utils.target_scenario_simulator import" in text
    assert "simulate_alternative" in text


def test_v10408_whatif_tab_in_defs():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "🧪 What-if simulator" in text
    assert '"what_if_simulator"' in text


def test_v10408_whatif_visible_to_managers():
    text = (REPO / "utils" / "core_audit.py").read_text()
    assert '"what_if_simulator": is_mgr' in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — State + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10408_engine_state_preserved():
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10408_g294_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10408_target_scenario_simulator
    r = gate_v10408_target_scenario_simulator()
    assert r["passed"], r.get("violations")

"""tests/test_efficiency.py — Standard #18 EfficiencyEngine tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
RESULTS_FILE = ROOT / "efficiency_correctness_results.json"


class TestStandard18Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "efficiency.py").exists()


@pytest.fixture
def basic_engine():
    from utils.efficiency import EfficiencyEngine
    outputs = {
        ("S001", "2026-04"): {"DEP_GROWTH": 100, "NPL_PCT": 80},
    }
    tasks = {
        ("S001", "2026-04"): [
            {"kpi_id": "DEP_GROWTH", "task": "Make 5 outbound prospect calls today"},
            {"kpi_id": "DEP_GROWTH", "task": "Make 5 outbound prospect calls today"},
            {"kpi_id": "NPL_PCT",    "task": "Call the 3 oldest delinquent accounts today"},
        ],
    }
    peers = {("S001", "2026-04"): ["S002", "S003", "S004"]}
    peer_eff = {
        ("S002", "DEP_GROWTH", "2026-04"): 1.5,
        ("S003", "DEP_GROWTH", "2026-04"): 1.6,
        ("S004", "DEP_GROWTH", "2026-04"): 1.7,
    }
    return EfficiencyEngine(
        outputs_fn=lambda sc, p: outputs.get((sc, p), {}),
        completed_tasks_fn=lambda sc, p: tasks.get((sc, p), []),
        peer_lookup_fn=lambda sc, p: peers.get((sc, p), []),
        peer_efficiency_fn=lambda sc, k, p: peer_eff.get((sc, k, p)),
    )


class TestSpecContract:
    def test_returns_required_keys(self, basic_engine):
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert "personal_efficiency" in r
        assert "vs_peer_average" in r

    def test_meta_block_present(self, basic_engine):
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert "meta" in r
        assert r["meta"]["staff_code"] == "S001"
        assert r["meta"]["period"] == "2026-04"


class TestMathCorrectness:
    def test_dep_growth_efficiency(self, basic_engine):
        # 100 output / 60 minutes = 1.667
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert abs(r["personal_efficiency"]["DEP_GROWTH"] - (100/60)) < 1e-4

    def test_npl_efficiency(self, basic_engine):
        # 80 output / 45 minutes = 1.778
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert abs(r["personal_efficiency"]["NPL_PCT"] - (80/45)) < 1e-4

    def test_vs_peer_ratio_correct(self, basic_engine):
        # peer avg = (1.5+1.6+1.7)/3 = 1.6; mine = 100/60 = 1.667
        # ratio = 1.667/1.6 = 1.042
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert abs(r["vs_peer_average"]["DEP_GROWTH"] - 1.0417) < 1e-3


class TestDefensiveContract:
    def test_kpi_without_proxy_time_skipped(self):
        from utils.efficiency import EfficiencyEngine
        eng = EfficiencyEngine(
            outputs_fn=lambda sc, p: {"DEP_GROWTH": 100, "AML_SLA": 50},
            completed_tasks_fn=lambda sc, p: [
                {"kpi_id": "DEP_GROWTH", "task": "Make 5 outbound prospect calls today"}
            ],
            peer_lookup_fn=lambda sc, p: [],
            peer_efficiency_fn=lambda sc, k, p: None,
        )
        r = eng.calculate_efficiency_scores("S1", "2026-04")
        assert "DEP_GROWTH" in r["personal_efficiency"]
        assert "AML_SLA" not in r["personal_efficiency"]
        assert "AML_SLA" in r["meta"]["kpis_skipped"]

    def test_insufficient_peers_returns_none(self):
        from utils.efficiency import EfficiencyEngine
        eng = EfficiencyEngine(
            outputs_fn=lambda sc, p: {"DEP_GROWTH": 100},
            completed_tasks_fn=lambda sc, p: [
                {"kpi_id": "DEP_GROWTH", "task": "Make 5 outbound prospect calls today"}
            ],
            peer_lookup_fn=lambda sc, p: ["S2"],   # only 1 peer
            peer_efficiency_fn=lambda sc, k, p: 1.5,
        )
        r = eng.calculate_efficiency_scores("S1", "2026-04")
        assert r["vs_peer_average"]["DEP_GROWTH"] is None

    def test_empty_outputs_returns_empty(self):
        from utils.efficiency import EfficiencyEngine
        eng = EfficiencyEngine(
            outputs_fn=lambda sc, p: {},
            completed_tasks_fn=lambda sc, p: [],
            peer_lookup_fn=lambda sc, p: [],
            peer_efficiency_fn=lambda sc, k, p: None,
        )
        assert eng.calculate_efficiency_scores("S1", "2026-04") == {}

    def test_empty_inputs_returns_empty(self, basic_engine):
        assert basic_engine.calculate_efficiency_scores("", "2026-04") == {}
        assert basic_engine.calculate_efficiency_scores("S001", "") == {}

    def test_negative_output_skipped(self):
        from utils.efficiency import EfficiencyEngine
        eng = EfficiencyEngine(
            outputs_fn=lambda sc, p: {"K1": -10},
            completed_tasks_fn=lambda sc, p: [{"kpi_id": "K1", "task": "x"}],
            peer_lookup_fn=lambda sc, p: [], peer_efficiency_fn=lambda sc, k, p: None,
        )
        r = eng.calculate_efficiency_scores("S1", "2026-04")
        assert "K1" not in r["personal_efficiency"]


class TestMetaTransparency:
    def test_kpis_with_proxy_time_listed(self, basic_engine):
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert sorted(r["meta"]["kpis_with_proxy_time"]) == ["DEP_GROWTH", "NPL_PCT"]

    def test_completed_tasks_count(self, basic_engine):
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert r["meta"]["completed_tasks"] == 3

    def test_tasks_per_kpi_breakdown(self, basic_engine):
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert r["meta"]["tasks_per_kpi"] == {"DEP_GROWTH": 2, "NPL_PCT": 1}

    def test_time_estimate_basis_documented(self, basic_engine):
        r = basic_engine.calculate_efficiency_scores("S001", "2026-04")
        assert "time_estimate_basis" in r["meta"]


class TestPersistence:
    def test_save_and_structure(self, tmp_path, monkeypatch):
        from utils import efficiency as eff
        monkeypatch.setattr(eff, "EFFICIENCY_FILE", tmp_path / "scores.json")
        scores = {"personal_efficiency": {"K1": 1.5}, "vs_peer_average": {}}
        ok = eff.save_efficiency_scores("S1", "2026-04", scores)
        assert ok is True

    def test_save_empty_returns_false(self, tmp_path, monkeypatch):
        from utils import efficiency as eff
        monkeypatch.setattr(eff, "EFFICIENCY_FILE", tmp_path / "scores.json")
        assert eff.save_efficiency_scores("S1", "2026-04", {}) is False


# ═══════════════════════════════════════════════════════════════════════
# Correctness harness — Standard #18 spec verification
# ═══════════════════════════════════════════════════════════════════════

EFFICIENCY_SCENARIOS = [
    {"id": "E001",
     "outputs": {"K1": 100}, "tasks": [{"kpi_id": "K1", "task": "generic"}],
     "expected": {"K1": 100/30}},  # 1 generic task = 30 min
    {"id": "E002",
     "outputs": {"K1": 90, "K2": 60},
     "tasks": [
         {"kpi_id": "K1", "task": "generic"},
         {"kpi_id": "K1", "task": "generic"},
         {"kpi_id": "K2", "task": "generic"}],
     "expected": {"K1": 90/60, "K2": 60/30}},
    {"id": "E003",
     "outputs": {"K1": 200},
     "tasks": [
         {"kpi_id": "K1", "task": "Make 5 outbound prospect calls today"},
         {"kpi_id": "K1", "task": "Call the 3 oldest delinquent accounts today"}],
     "expected": {"K1": 200/75}},  # 30+45
    {"id": "E004",
     "outputs": {"K1": 50, "K2": 0}, "tasks": [{"kpi_id": "K1", "task": "generic"}],
     "expected": {"K1": 50/30}},  # K2 has 0 tasks → skipped
    {"id": "E005",
     "outputs": {"K1": 1500000}, "tasks": [{"kpi_id": "K1", "task": "generic"}],
     "expected": {"K1": 1500000/30}},  # large numbers
]


def test_efficiency_correctness_harness():
    """Verify math correctness on labeled scenarios; write G29 artifact."""
    from utils.efficiency import EfficiencyEngine

    matches = 0
    results = []
    for s in EFFICIENCY_SCENARIOS:
        eng = EfficiencyEngine(
            outputs_fn=lambda sc, p, o=s["outputs"]: o,
            completed_tasks_fn=lambda sc, p, t=s["tasks"]: list(t),
            peer_lookup_fn=lambda sc, p: [],
            peer_efficiency_fn=lambda sc, k, p: None,
        )
        r = eng.calculate_efficiency_scores("X", "2026-04")
        actual = r.get("personal_efficiency", {})
        ok = True
        details = {}
        for kpi, expected_eff in s["expected"].items():
            got = actual.get(kpi)
            if got is None:
                ok = False
                details[kpi] = f"missing (expected {expected_eff:.4f})"
            elif abs(got - expected_eff) > 1e-3:
                ok = False
                details[kpi] = f"got {got:.4f}, expected {expected_eff:.4f}"
            else:
                details[kpi] = "ok"
        if ok:
            matches += 1
        results.append({
            "id": s["id"], "matched": ok, "details": details,
        })

    accuracy = matches / len(EFFICIENCY_SCENARIOS) * 100
    artifact = {
        "schema_version": 1,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(EFFICIENCY_SCENARIOS),
        "matches": matches,
        "accuracy_pct": round(accuracy, 2),
        "spec_target_pct": 100.0,
        "all_passed": accuracy >= 100.0,
        "results": results,
    }
    RESULTS_FILE.write_text(json.dumps(artifact, indent=2))

    assert accuracy >= 100.0, (
        f"Math correctness {accuracy:.1f}% < 100%; failures:\n"
        + "\n".join(f"  {r['id']}: {r['details']}" for r in results if not r["matched"])
    )

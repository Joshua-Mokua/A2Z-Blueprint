"""tests/test_volume_eight_batch.py — Standards #49-#52 (v5.54).

Coverage:
  Standard #49 — Initiative Impact Automation (Cat B/C)
  Standard #50 — Stage-Gate Governance (Cat C)
  Standard #51 — Initiative Dependency & Risk Intelligence (Cat B)
  Standard #52 — Initiative Resource Intelligence (Cat B)

Plus one artifact-handoff harness:
  test_initiative_impact_correctness_meets_99_percent →
    initiative_impact_results.json (G53)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


# ═══════════════════════════════════════════════════════════════════════
# Standard #49 — Initiative Impact Automation
# ═══════════════════════════════════════════════════════════════════════

class TestStandard49:
    def test_module_exists(self):
        from utils.initiative_impact import InitiativeImpactEngine
        eng = InitiativeImpactEngine()
        assert hasattr(eng, "auto_link_initiative_to_kpi")
        assert hasattr(eng, "compute_realized_impact")
        assert hasattr(eng, "track_progress")
        assert hasattr(eng, "aggregate_realized_impact")

    def test_spec_literal_initiative_types(self):
        from utils.initiative_impact import INITIATIVE_TYPES
        assert INITIATIVE_TYPES == [
            "KPI_IMPROVEMENT", "REVENUE_GENERATION", "COST_REDUCTION",
            "RISK_MITIGATION", "COMPLIANCE_REMEDIATION",
        ]

    def test_spec_literal_statuses(self):
        from utils.initiative_impact import INITIATIVE_STATUSES
        assert INITIATIVE_STATUSES == ["PROPOSED", "APPROVED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]

    def test_realized_impact_when_completed(self):
        from utils.initiative_impact import InitiativeImpactEngine
        inits = {"I1": {"initiative_id": "I1", "status": "COMPLETED",
                        "initiative_type": "KPI_IMPROVEMENT", "linked_kpi_id": "K1"}}
        actuals = {("K1", "P1"): 100, ("K1", "P2"): 125}
        eng = InitiativeImpactEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            kpi_actuals_fn=lambda k, p: actuals.get((k, p)),
        )
        r = eng.compute_realized_impact("I1", "P1", "P2")
        assert r["status"] == "computed"
        assert r["delta"] == 25.00
        assert r["delta_pct"] == 25.0

    def test_in_progress_returns_progress(self):
        from utils.initiative_impact import InitiativeImpactEngine
        inits = {"I1": {"initiative_id": "I1", "status": "IN_PROGRESS"}}
        miles = {"I1": [{"completed": True}, {"completed": False}]}
        eng = InitiativeImpactEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            milestone_lookup_fn=lambda i: miles.get(i, []),
        )
        r = eng.compute_realized_impact("I1", "P1", "P2")
        assert r["status"] == "in_progress"
        assert r["progress_pct"] == 50.0

    def test_actuals_missing_returns_none(self):
        """Rule 6 — no silent zero substitution."""
        from utils.initiative_impact import InitiativeImpactEngine
        inits = {"I1": {"initiative_id": "I1", "status": "COMPLETED", "linked_kpi_id": "K1"}}
        eng = InitiativeImpactEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            kpi_actuals_fn=lambda k, p: None,
        )
        r = eng.compute_realized_impact("I1", "P1", "P2")
        assert r["delta"] is None
        assert r["status"] == "actuals_missing"

    def test_baseline_zero_returns_pct_none(self):
        """Rule 1 — undefined growth from zero."""
        from utils.initiative_impact import InitiativeImpactEngine
        inits = {"I1": {"initiative_id": "I1", "status": "COMPLETED", "linked_kpi_id": "K1"}}
        actuals = {("K1", "P1"): 0, ("K1", "P2"): 100}
        eng = InitiativeImpactEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            kpi_actuals_fn=lambda k, p: actuals.get((k, p)),
        )
        r = eng.compute_realized_impact("I1", "P1", "P2")
        assert r["delta"] == 100.00
        assert r["delta_pct"] is None


# ═══════════════════════════════════════════════════════════════════════
# Standard #50 — Stage-Gate Governance
# ═══════════════════════════════════════════════════════════════════════

class TestStandard50:
    def test_module_exists(self):
        from utils.stage_gate import StageGateEngine
        eng = StageGateEngine()
        assert hasattr(eng, "request_stage_transition")
        assert hasattr(eng, "get_gate_criteria")
        assert hasattr(eng, "validate_initiative_at_stage")

    def test_spec_literal_stages(self):
        from utils.stage_gate import STAGES
        assert STAGES == ["IDEATION", "DESIGN", "BUILD", "PILOT", "ROLLOUT", "COMPLETED"]

    def test_design_criteria_byte_for_byte(self):
        from utils.stage_gate import STAGE_CRITERIA
        assert STAGE_CRITERIA["DESIGN"] == [
            "business_case_approved", "sponsor_assigned", "estimated_budget_documented",
        ]

    def test_completed_criteria_byte_for_byte(self):
        from utils.stage_gate import STAGE_CRITERIA
        assert STAGE_CRITERIA["COMPLETED"] == [
            "rollout_success_verified", "kpi_baseline_captured", "lessons_learned_documented",
        ]

    def test_unmet_criteria_blocks_transition(self):
        """Rule 4 — default-deny on missing criteria."""
        from utils.stage_gate import StageGateEngine
        inits = {"I1": {"initiative_id": "I1", "stage": "IDEATION"}}
        eng = StageGateEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            criteria_state_fn=lambda i: {},  # nothing met
        )
        r = eng.request_stage_transition("I1", "DESIGN", "user_001")
        assert r["granted"] is False
        assert r["reason"] == "criteria_unmet"
        assert len(r["unmet_criteria"]) == 3

    def test_skip_stage_blocked(self):
        """Forward-only: cannot skip stages."""
        from utils.stage_gate import StageGateEngine
        inits = {"I1": {"initiative_id": "I1", "stage": "IDEATION"}}
        eng = StageGateEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            criteria_state_fn=lambda i: {},
        )
        r = eng.request_stage_transition("I1", "PILOT", "user_001")
        assert r["granted"] is False
        assert "non-sequential" in r["reason"]

    def test_backward_blocked(self):
        """Cannot go backward."""
        from utils.stage_gate import StageGateEngine
        inits = {"I1": {"initiative_id": "I1", "stage": "BUILD"}}
        eng = StageGateEngine(initiative_lookup_fn=lambda i: inits.get(i))
        r = eng.request_stage_transition("I1", "DESIGN", "user_001")
        assert r["granted"] is False
        assert "backward" in r["reason"]

    def test_no_override_methods_exist(self):
        """Rule 4 — no override mode."""
        from utils.stage_gate import StageGateEngine
        eng = StageGateEngine()
        forbidden = ["force_advance", "override_criteria", "admin_skip", "bypass_gate"]
        for m in forbidden:
            assert not hasattr(eng, m), f"forbidden override method present: {m}"


# ═══════════════════════════════════════════════════════════════════════
# Standard #51 — Initiative Dependency & Risk Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard51:
    def test_module_exists(self):
        from utils.initiative_dependency import DependencyIntelligenceEngine
        eng = DependencyIntelligenceEngine()
        assert hasattr(eng, "compute_critical_path")
        assert hasattr(eng, "identify_blocked_initiatives")
        assert hasattr(eng, "risk_propagation")
        assert hasattr(eng, "detect_cycles")

    def test_spec_literal_risk_levels(self):
        from utils.initiative_dependency import RISK_LEVELS
        assert RISK_LEVELS == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def test_critical_path_linear(self):
        from utils.initiative_dependency import DependencyIntelligenceEngine
        inits = {"A": {"initiative_id": "A"}, "B": {"initiative_id": "B"},
                 "C": {"initiative_id": "C"}, "D": {"initiative_id": "D"}}
        deps = {"A": [], "B": ["A"], "C": ["B"], "D": ["C"]}
        eng = DependencyIntelligenceEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            all_initiatives_fn=lambda: list(inits.values()),
            dependency_lookup_fn=lambda i: deps.get(i, []),
        )
        r = eng.compute_critical_path()
        assert r["path"] == ["A", "B", "C", "D"]
        assert r["length"] == 4

    def test_cycle_detection(self):
        from utils.initiative_dependency import DependencyIntelligenceEngine
        inits = {"X": {"initiative_id": "X"}, "Y": {"initiative_id": "Y"}, "Z": {"initiative_id": "Z"}}
        deps = {"X": ["Z"], "Y": ["X"], "Z": ["Y"]}
        eng = DependencyIntelligenceEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            all_initiatives_fn=lambda: list(inits.values()),
            dependency_lookup_fn=lambda i: deps.get(i, []),
        )
        cyc = eng.detect_cycles()
        assert cyc["has_cycles"] is True

    def test_cycle_blocks_critical_path(self):
        """Rule 6 — refuse to compute on broken graph."""
        from utils.initiative_dependency import DependencyIntelligenceEngine
        inits = {"X": {"initiative_id": "X"}, "Y": {"initiative_id": "Y"}}
        deps = {"X": ["Y"], "Y": ["X"]}
        eng = DependencyIntelligenceEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            all_initiatives_fn=lambda: list(inits.values()),
            dependency_lookup_fn=lambda i: deps.get(i, []),
        )
        r = eng.compute_critical_path()
        assert r["error"] is not None
        assert "cycles" in r["error"]

    def test_blocked_initiatives(self):
        from utils.initiative_dependency import DependencyIntelligenceEngine
        inits = {
            "A": {"initiative_id": "A", "status": "COMPLETED"},
            "B": {"initiative_id": "B", "status": "IN_PROGRESS"},
            "C": {"initiative_id": "C", "status": "PROPOSED"},
        }
        deps = {"A": [], "B": ["A"], "C": ["B"]}
        eng = DependencyIntelligenceEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            all_initiatives_fn=lambda: list(inits.values()),
            dependency_lookup_fn=lambda i: deps.get(i, []),
        )
        r = eng.identify_blocked_initiatives()
        # B's pred A is COMPLETED → B unblocked
        # C's pred B is IN_PROGRESS → C blocked
        blocked = [b["initiative_id"] for b in r["blocked"]]
        assert "C" in blocked
        assert "B" not in blocked

    def test_risk_propagation_classifies(self):
        from utils.initiative_dependency import DependencyIntelligenceEngine
        # 7 nodes, K0 → K1..K6 (6 children)
        inits = {f"K{i}": {"initiative_id": f"K{i}", "status": "IN_PROGRESS"}
                  for i in range(7)}
        deps = {"K0": []}
        deps.update({f"K{i}": ["K0"] for i in range(1, 7)})
        eng = DependencyIntelligenceEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            all_initiatives_fn=lambda: list(inits.values()),
            dependency_lookup_fn=lambda i: deps.get(i, []),
        )
        # K0 has 6 downstream → CRITICAL (>5)
        r = eng.risk_propagation("K0")
        assert r["downstream_count"] == 6
        assert r["risk_level"] == "CRITICAL"

    def test_unknown_dependencies_surfaced(self):
        from utils.initiative_dependency import DependencyIntelligenceEngine
        inits = {"P": {"initiative_id": "P", "status": "IN_PROGRESS"}}
        deps = {"P": ["MISSING"]}
        eng = DependencyIntelligenceEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            all_initiatives_fn=lambda: list(inits.values()),
            dependency_lookup_fn=lambda i: deps.get(i, []),
        )
        r = eng.identify_blocked_initiatives()
        assert "MISSING" in r["meta"]["unknown_dependencies"]


# ═══════════════════════════════════════════════════════════════════════
# Standard #52 — Initiative Resource Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard52:
    def test_module_exists(self):
        from utils.initiative_resource import ResourceIntelligenceEngine
        eng = ResourceIntelligenceEngine()
        assert hasattr(eng, "resource_utilization_by_initiative")
        assert hasattr(eng, "detect_overallocation")
        assert hasattr(eng, "budget_burn_by_initiative")
        assert hasattr(eng, "resource_capacity_summary")

    def test_spec_literal_resource_types(self):
        from utils.initiative_resource import RESOURCE_TYPES
        assert RESOURCE_TYPES == ["PEOPLE", "BUDGET", "INFRASTRUCTURE"]

    def test_overallocation_threshold(self):
        from utils.initiative_resource import OVERALLOCATION_THRESHOLD_PCT
        assert int(OVERALLOCATION_THRESHOLD_PCT) == 100

    def test_overallocation_detection(self):
        from utils.initiative_resource import ResourceIntelligenceEngine
        inits = [{"initiative_id": "I1", "status": "IN_PROGRESS"}]
        people = [{"staff_code": "S1", "hours": 200}]
        cap = {("S1", "P"): 100}    # 200 allocated vs 100 capacity = 200%
        eng = ResourceIntelligenceEngine(
            all_initiatives_fn=lambda: inits,
            people_alloc_fn=lambda i, p: people,
            staff_capacity_fn=lambda s, p: cap.get((s, p)),
        )
        r = eng.detect_overallocation("P")
        assert r["summary"]["overallocated_count"] == 1
        assert r["overallocated"][0]["allocation_pct"] == 200.0

    def test_no_capacity_surfaced_explicitly(self):
        """Rule 6 — staff with no capacity record listed explicitly."""
        from utils.initiative_resource import ResourceIntelligenceEngine
        inits = [{"initiative_id": "I1", "status": "IN_PROGRESS"}]
        people = [{"staff_code": "S_NO_CAP", "hours": 50}]
        eng = ResourceIntelligenceEngine(
            all_initiatives_fn=lambda: inits,
            people_alloc_fn=lambda i, p: people,
            staff_capacity_fn=lambda s, p: None,
        )
        r = eng.detect_overallocation("P")
        assert "S_NO_CAP" in r["no_capacity_data"]

    def test_budget_burn_alerts(self):
        from utils.initiative_resource import ResourceIntelligenceEngine
        inits = [
            {"initiative_id": "OVER", "status": "IN_PROGRESS"},
            {"initiative_id": "WARN", "status": "IN_PROGRESS"},
            {"initiative_id": "OK",   "status": "IN_PROGRESS"},
        ]
        budget = {"OVER": 1000, "WARN": 1000, "OK": 1000}
        actual = {("OVER", "P"): 1500, ("WARN", "P"): 850, ("OK", "P"): 500}
        eng = ResourceIntelligenceEngine(
            all_initiatives_fn=lambda: inits,
            budget_alloc_fn=lambda i: budget.get(i),
            budget_actual_fn=lambda i, p: actual.get((i, p)),
        )
        r = eng.budget_burn_by_initiative("P")
        assert r["summary"]["over_count"] == 1
        assert r["summary"]["warning_count"] == 1
        levels = {a["initiative_id"]: a["alert_level"] for a in r["alerts"]}
        assert levels["OVER"] == "OVER"
        assert levels["WARN"] == "WARNING"
        assert "OK" not in levels    # under threshold

    def test_kes_billion_precision(self):
        from utils.initiative_resource import ResourceIntelligenceEngine
        inits = [{"initiative_id": "HUGE", "status": "IN_PROGRESS"}]
        eng = ResourceIntelligenceEngine(
            all_initiatives_fn=lambda: inits,
            budget_alloc_fn=lambda i: "11500000000.50",
            budget_actual_fn=lambda i, p: "11500000000.51",
        )
        r = eng.resource_utilization_by_initiative("P")
        huge = r["initiatives"][0]
        assert huge["budget_allocated"] == 11_500_000_000.50

    def test_completed_excluded_from_overallocation(self):
        from utils.initiative_resource import ResourceIntelligenceEngine
        inits = [
            {"initiative_id": "DONE", "status": "COMPLETED"},
        ]
        people = [{"staff_code": "S1", "hours": 1000}]    # huge alloc
        eng = ResourceIntelligenceEngine(
            all_initiatives_fn=lambda: inits,
            people_alloc_fn=lambda i, p: people if i == "DONE" else [],
            staff_capacity_fn=lambda s, p: 100,
        )
        r = eng.detect_overallocation("P")
        # COMPLETED initiative's allocations excluded
        over = [o["staff_code"] for o in r["overallocated"]]
        assert "S1" not in over


# ═══════════════════════════════════════════════════════════════════════
# G53 harness — Initiative Impact correctness
# ═══════════════════════════════════════════════════════════════════════

def test_initiative_impact_correctness_meets_99_percent():
    """Run all II fixtures and produce initiative_impact_results.json."""
    from utils.initiative_impact import InitiativeImpactEngine

    fixtures_path = FIXTURES_DIR / "initiative_impact_scenarios.json"
    assert fixtures_path.exists(), f"fixtures missing: {fixtures_path}"

    with open(fixtures_path) as f:
        data = json.load(f)
    fixtures = data["fixtures"]

    results = []
    matches = 0
    total = len(fixtures)

    for fx in fixtures:
        inp = fx["input"]
        exp = fx["expected"]

        inits = {inp["initiative_id"]: inp["initiative"]}
        actuals = {(inp["kpi_id"], p): v for p, v in inp.get("actuals", {}).items()}
        eng = InitiativeImpactEngine(
            initiative_lookup_fn=lambda i: inits.get(i),
            kpi_actuals_fn=lambda k, p: actuals.get((k, p)),
        )

        r = eng.compute_realized_impact(
            inp["initiative_id"], inp["baseline_period"], inp["comparison_period"],
        )
        ok = True
        for field in ("status", "delta", "delta_pct", "baseline_value", "comparison_value"):
            if field not in exp:
                continue
            actual = r.get(field)
            expected = exp[field]
            if expected is None:
                if actual is not None:
                    ok = False
            elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                if abs(actual - expected) > 0.01:
                    ok = False
            else:
                if actual != expected:
                    ok = False

        if ok:
            matches += 1
        results.append({
            "id":     fx["id"],
            "label":  fx["label"],
            "matched": ok,
            "diffs": [] if ok else [f"mismatch on fixture {fx['id']}"],
        })

    accuracy = (matches / total * 100) if total > 0 else 0
    artifact = {
        "total_scenarios":  total,
        "correct":          matches,
        "accuracy_pct":     accuracy,
        "spec_target_pct":  99.0,
        "results":          results,
        "fixtures_total":   total,
        "fixtures_matched": matches,
        "match_rate_pct":   accuracy,
    }

    out_path = ROOT / "initiative_impact_results.json"
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2)

    assert accuracy >= 99.0, \
        f"initiative impact correctness {accuracy:.1f}% < 99%; see {out_path}"

"""tests/test_strategy_v10_138.py — v10.138 Phase 1 Strategy standards 7 & 8.

Closes ENH-146 Strategy Execution Gap Analyzer + ENH-147 Corrective
Action Generator — seventh and eighth of 15 Strategy Module standards.

Together these form the strategy execution feedback loop:
  ENH-146 detects gaps with root-cause analysis →
  ENH-147 generates corrective action plans automatically.

Verifies:
  ENH-146 StrategyGapAnalyzer
    1. analyze_gaps returns expected shape
    2. Gap detection threshold: actual < target × 0.9 = gap
    3. Severity: HIGH if actual < target × 0.7, else MEDIUM
    4. No gap when within 10% of target (ratio ≥ 0.9)
    5. Decision-tree root cause precedence: resource > process > skill
    6. UNCLASSIFIED returned when no signals provided
    7. Systemic gap requires 3+ pillars affected by same root cause
    8. Same input → same output (determinism)
    9. AI hook fallback on exception
    10. Closure plan phases by severity

  ENH-147 CorrectiveActionGenerator
    1. generate_corrective_actions returns expected shape
    2. UNDER_RESOURCED → RESOURCE_REALLOCATION action
    3. PROCESS_BOTTLENECK → PROCESS_REDESIGN action
    4. SKILL_GAP → TRAINING action
    5. UNCLASSIFIED → MANUAL_REVIEW action
    6. Expected gap reduction multipliers (0.5/0.7/0.3 per spec)
    7. Prioritization by impact-per-cost ratio (deterministic sort)
    8. AI suggester hook tagged basis=llm
    9. AI suggester fallback on exception
    10. Batch wrapper aggregates correctly

  Hub integration (G117)
    1. All 8 strategy engines (141-147 + 153) appear in admin hub
    2. G117 coverage threshold met (≥ 95%)

  Registry
    1. ENH-146 active with engine
    2. ENH-147 active with engine
    3. Other Strategy standards (148-152, 154-155) still planned

  No regression
    1. G144 264/264
    2. G117 passes (≥ 95%)
    3. ENH-141/142/143/144/145/153 still active
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── ENH-146 StrategyGapAnalyzer ────────────────────────────────────

class TestStrategyGapAnalyzer:

    @pytest.fixture
    def analyzer(self):
        from utils.gap_analyzer import StrategyGapAnalyzer
        return StrategyGapAnalyzer()

    @pytest.fixture
    def pillar(self):
        return {
            "name":            "Test Pillar",
            "owner":           "Test Owner",
            "success_metrics": ["NPS > 75", "CSAT > 4.5",
                                "Digital adoption > 70%"],
        }

    def test_analyze_gaps_shape(self, analyzer, pillar):
        perf = {pillar["name"]: {
            "NPS > 75": {"target": 75, "actual": 60},
            "_signals": {"resource_utilization": 1.30},
        }}
        r = analyzer.analyze_gaps([pillar], perf)
        for f in ("gaps", "systemic_gaps", "total_gap_value",
                  "n_pillars_with_gaps", "recommendations",
                  "closure_plan", "n_high", "n_medium",
                  "generated_at", "basis"):
            assert f in r

    def test_gap_threshold_90_percent(self, analyzer, pillar):
        """actual < 0.9*target = gap; actual >= 0.9*target = no gap."""
        # actual = 0.85 × target → gap
        perf_gap = {pillar["name"]: {
            "NPS > 75": {"target": 100, "actual": 85},
        }}
        r = analyzer.analyze_gaps([pillar], perf_gap)
        assert len(r["gaps"]) == 1

        # actual = 0.95 × target → no gap
        perf_ok = {pillar["name"]: {
            "NPS > 75": {"target": 100, "actual": 95},
        }}
        r2 = analyzer.analyze_gaps([pillar], perf_ok)
        assert len(r2["gaps"]) == 0

    def test_severity_high_below_70(self, analyzer, pillar):
        """actual < 0.7 × target = HIGH severity."""
        perf = {pillar["name"]: {
            "NPS > 75": {"target": 100, "actual": 50},  # 50% → HIGH
        }}
        r = analyzer.analyze_gaps([pillar], perf)
        assert len(r["gaps"]) == 1
        assert r["gaps"][0]["severity"] == "HIGH"

    def test_severity_medium_70_to_90(self, analyzer, pillar):
        """actual 0.7-0.9 × target = MEDIUM severity."""
        perf = {pillar["name"]: {
            "NPS > 75": {"target": 100, "actual": 80},  # 80% → MEDIUM
        }}
        r = analyzer.analyze_gaps([pillar], perf)
        assert r["gaps"][0]["severity"] == "MEDIUM"

    def test_decision_tree_resource_precedence(self, analyzer):
        """All 3 signals → resource branch wins (highest precedence)."""
        rc = analyzer.analyze_root_cause(
            {"name": "X"}, {"name": "Y"},
            {"resource_utilization": 1.30, "process_tat": 12,
             "process_target_tat": 8, "skill_gap_score": 0.50})
        assert rc["category"] == "UNDER_RESOURCED"

    def test_decision_tree_process_precedence(self, analyzer):
        """No resource issue + process + skill → process wins."""
        rc = analyzer.analyze_root_cause(
            {"name": "X"}, {"name": "Y"},
            {"resource_utilization": 1.00, "process_tat": 12,
             "process_target_tat": 8, "skill_gap_score": 0.50})
        assert rc["category"] == "PROCESS_BOTTLENECK"

    def test_decision_tree_skill_precedence(self, analyzer):
        """Only skill signal → skill wins."""
        rc = analyzer.analyze_root_cause(
            {"name": "X"}, {"name": "Y"}, {"skill_gap_score": 0.50})
        assert rc["category"] == "SKILL_GAP"

    def test_unclassified_when_no_signals(self, analyzer):
        rc = analyzer.analyze_root_cause(
            {"name": "X"}, {"name": "Y"}, {})
        assert rc["category"] == "UNCLASSIFIED"
        assert "manual classification" in rc["detail"].lower()

    def test_systemic_gap_requires_3_pillars(self, analyzer):
        """Same root cause must affect 3+ pillars to be flagged
        systemic."""
        # 2 pillars with UNDER_RESOURCED — should NOT be flagged systemic
        pillars = [
            {"name": f"Pillar {i}",
             "success_metrics": ["X > 100"], "owner": "Test"}
            for i in range(2)
        ]
        perf = {f"Pillar {i}": {
            "X > 100": {"target": 100, "actual": 50},
            "_signals": {"resource_utilization": 1.40},
        } for i in range(2)}
        r = analyzer.analyze_gaps(pillars, perf)
        assert len(r["systemic_gaps"]) == 0

        # 3 pillars with UNDER_RESOURCED — flagged systemic
        pillars3 = [
            {"name": f"Pillar {i}",
             "success_metrics": ["X > 100"], "owner": "Test"}
            for i in range(3)
        ]
        perf3 = {f"Pillar {i}": {
            "X > 100": {"target": 100, "actual": 50},
            "_signals": {"resource_utilization": 1.40},
        } for i in range(3)}
        r3 = analyzer.analyze_gaps(pillars3, perf3)
        assert len(r3["systemic_gaps"]) == 1
        assert r3["systemic_gaps"][0]["category"] == "UNDER_RESOURCED"

    def test_determinism(self, analyzer, pillar):
        """Same input → same output."""
        perf = {pillar["name"]: {
            "NPS > 75": {"target": 100, "actual": 65},
            "_signals": {"resource_utilization": 1.30},
        }}
        r1 = analyzer.analyze_gaps([pillar], perf)
        r2 = analyzer.analyze_gaps([pillar], perf)
        # Strip generated_at (timestamp differs)
        del r1["generated_at"]; del r2["generated_at"]
        assert r1 == r2

    def test_ai_root_cause_hook_fallback(self):
        from utils.gap_analyzer import StrategyGapAnalyzer

        def broken(p, m):
            raise RuntimeError("LLM outage")

        a = StrategyGapAnalyzer(ai_root_cause_fn=broken)
        rc = a.analyze_root_cause({"name": "X"}, {"name": "Y"}, {})
        assert rc["category"] == "UNCLASSIFIED"


# ─── ENH-147 CorrectiveActionGenerator ─────────────────────────────

class TestCorrectiveActionGenerator:

    @pytest.fixture
    def generator(self):
        from utils.corrective_actions import CorrectiveActionGenerator
        return CorrectiveActionGenerator()

    def _make_gap(self, root_category, gap_value=20, severity="HIGH",
                  signals=None):
        return {
            "level":           "PILLAR",
            "pillar":          "Test Pillar",
            "metric":          "Test Metric",
            "target":          100,
            "actual":          80,
            "gap":             gap_value,
            "gap_percentage":  20.0,
            "severity":        severity,
            "ratio":           0.80,
            "root_cause":      {
                "category":     root_category,
                "detail":       "test detail",
                "signals_seen": signals or {},
            },
            "owner":           "Test Owner",
        }

    def test_generate_action_shape(self, generator):
        gap = self._make_gap("UNDER_RESOURCED")
        r = generator.generate_corrective_actions(gap)
        for f in ("gap_id", "pillar", "metric", "severity",
                  "root_cause", "recommended_actions",
                  "combined_impact", "total_cost", "n_actions",
                  "generated_at", "basis"):
            assert f in r

    def test_under_resourced_emits_resource_action(self, generator):
        gap = self._make_gap("UNDER_RESOURCED")
        r = generator.generate_corrective_actions(gap)
        types = [a["type"] for a in r["recommended_actions"]]
        assert "RESOURCE_REALLOCATION" in types

    def test_process_bottleneck_emits_process_action(self, generator):
        gap = self._make_gap("PROCESS_BOTTLENECK", signals={
            "process_tat": 12.0, "process_target_tat": 8.0})
        r = generator.generate_corrective_actions(gap)
        types = [a["type"] for a in r["recommended_actions"]]
        assert "PROCESS_REDESIGN" in types

    def test_skill_gap_emits_training_action(self, generator):
        gap = self._make_gap("SKILL_GAP")
        r = generator.generate_corrective_actions(gap)
        types = [a["type"] for a in r["recommended_actions"]]
        assert "TRAINING" in types

    def test_unclassified_emits_manual_review(self, generator):
        gap = self._make_gap("UNCLASSIFIED")
        r = generator.generate_corrective_actions(gap)
        types = [a["type"] for a in r["recommended_actions"]]
        assert "MANUAL_REVIEW" in types

    def test_resource_reduction_multiplier(self, generator):
        """Per spec: resource reallocation closes 50% of gap."""
        gap = self._make_gap("UNDER_RESOURCED", gap_value=20)
        r = generator.generate_corrective_actions(gap)
        resource_action = next(a for a in r["recommended_actions"]
                               if a["type"] == "RESOURCE_REALLOCATION")
        assert resource_action["expected_gap_reduction"] == 10.0  # 0.5 × 20

    def test_process_reduction_multiplier(self, generator):
        """Per spec: process redesign closes 70% of gap."""
        gap = self._make_gap("PROCESS_BOTTLENECK", gap_value=10,
                             signals={"process_tat": 12,
                                      "process_target_tat": 8})
        r = generator.generate_corrective_actions(gap)
        process_action = next(a for a in r["recommended_actions"]
                              if a["type"] == "PROCESS_REDESIGN")
        assert process_action["expected_gap_reduction"] == 7.0  # 0.7 × 10

    def test_training_reduction_multiplier(self, generator):
        """Per spec: training closes 30% of gap."""
        gap = self._make_gap("SKILL_GAP", gap_value=10)
        r = generator.generate_corrective_actions(gap)
        training_action = next(a for a in r["recommended_actions"]
                               if a["type"] == "TRAINING")
        assert training_action["expected_gap_reduction"] == 3.0  # 0.3 × 10

    def test_prioritization_by_impact_per_cost_ratio(self, generator):
        """Actions sorted: highest impact/cost ratio first."""
        actions = [
            {"type": "A", "implementation_cost": 100,
             "expected_gap_reduction": 5},   # ratio 0.05
            {"type": "B", "implementation_cost": 100,
             "expected_gap_reduction": 20},  # ratio 0.20
            {"type": "C", "implementation_cost": 200,
             "expected_gap_reduction": 10},  # ratio 0.05
        ]
        sorted_actions = generator.prioritize_actions(actions)
        assert sorted_actions[0]["type"] == "B"

    def test_zero_cost_actions_sort_last(self, generator):
        actions = [
            {"type": "A", "implementation_cost": 100,
             "expected_gap_reduction": 5},
            {"type": "B", "implementation_cost": 0,
             "expected_gap_reduction": 0},
        ]
        sorted_actions = generator.prioritize_actions(actions)
        assert sorted_actions[0]["type"] == "A"
        assert sorted_actions[1]["type"] == "B"

    def test_ai_suggester_hook(self):
        from utils.corrective_actions import CorrectiveActionGenerator

        def suggester(gap):
            return [{"type": "AI_CUSTOM_ACTION",
                     "description": "AI says do X",
                     "implementation_cost": 1_000_000,
                     "expected_gap_reduction": 5.0}]

        gen = CorrectiveActionGenerator(ai_suggester_fn=suggester)
        gap = {"pillar": "P", "metric": "M", "severity": "HIGH",
               "gap": 10, "root_cause": {"category": "UNDER_RESOURCED"}}
        r = gen.generate_corrective_actions(gap)
        ai_actions = [a for a in r["recommended_actions"]
                      if a.get("basis") == "llm"]
        assert len(ai_actions) == 1
        assert "rule_based+llm" in r["basis"] or "llm+rule_based" in r["basis"]

    def test_ai_suggester_fallback(self):
        from utils.corrective_actions import CorrectiveActionGenerator

        def broken(gap):
            raise RuntimeError("LLM down")

        gen = CorrectiveActionGenerator(ai_suggester_fn=broken)
        gap = {"pillar": "P", "metric": "M", "severity": "HIGH",
               "gap": 10, "root_cause": {"category": "UNDER_RESOURCED"}}
        r = gen.generate_corrective_actions(gap)
        # Falls back to rule-based only, no crash
        assert "rule_based" in r["basis"]

    def test_batch_wrapper(self, generator):
        gaps = [
            self._make_gap("UNDER_RESOURCED", gap_value=20),
            self._make_gap("SKILL_GAP", gap_value=10),
            self._make_gap("UNCLASSIFIED", gap_value=5),
        ]
        r = generator.generate_actions_for_all_gaps(gaps)
        assert r["n_gaps"] == 3
        assert r["n_total_actions"] >= 3
        assert "by_severity" in r


# ─── End-to-end pipeline ────────────────────────────────────────────

class TestEndToEnd:

    def test_full_pipeline_pillar_to_actions(self):
        """ENH-143 → ENH-146 → ENH-147 chain."""
        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.gap_analyzer import StrategyGapAnalyzer
        from utils.corrective_actions import CorrectiveActionGenerator

        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            "digital transformation")

        # Build synthetic perf with gaps
        current_performance = {}
        for p in pillars:
            metrics = {}
            for sm in p["success_metrics"]:
                # Force a gap: target=100, actual=50
                metrics[sm] = {"target": 100, "actual": 50}
            metrics["_signals"] = {"resource_utilization": 1.30}
            current_performance[p["name"]] = metrics

        gap_result = StrategyGapAnalyzer().analyze_gaps(
            pillars, current_performance)
        assert gap_result["n_high"] > 0  # 50% < 70% = HIGH

        action_result = CorrectiveActionGenerator(
        ).generate_actions_for_all_gaps(gap_result["gaps"])
        assert action_result["n_total_actions"] > 0


# ─── Hub integration (G117) ────────────────────────────────────────

class TestHubIntegration:

    def test_all_strategy_engines_in_hub(self):
        """All 8 strategy engines (141/142/143/144/145/146/147/153)
        appear in pages/7_admin.py hub registry."""
        admin_text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        for engine in ("strategy_formulation", "strategic_options",
                       "strategy_decomposition", "initiative_portfolio",
                       "enhanced_cascade", "daily_strategy_integration",
                       "gap_analyzer", "corrective_actions"):
            assert f'"{engine}"' in admin_text, f"{engine} missing from hub"


# ─── Registry flips ─────────────────────────────────────────────────

class TestRegistryFlipped:

    def test_enh_146_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-146")
        assert s.status == "active"
        assert "gap_analyzer" in s.affected_engines

    def test_enh_147_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-147")
        assert s.status == "active"
        assert "corrective_actions" in s.affected_engines

    def test_other_strategy_standards_still_planned(self):
        """At v10.138: ENH-141/142/143/144/145/146/147/153 active.
        Others (148-152, 154-155) still planned."""
        from utils.standards_registry import STANDARDS_REGISTRY
        for n in (148, 149, 150, 151, 152, 154, 155):
            s = next(s for s in STANDARDS_REGISTRY
                     if s.standard_id == f"ENH-{n}")
            assert s.status == "planned", (
                f"ENH-{n} should be planned, got {s.status}")


# ─── No regression ─────────────────────────────────────────────────

class TestNoRegression:

    def test_g144_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_qa_spec_complete()
        finally:
            sys.path.pop(0)
        assert r["passed"] and r["registry_match"] == 264

    def test_g117_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_engine_hub_integration_coverage()
        finally:
            sys.path.pop(0)
        assert r["passed"]

    def test_prior_strategy_standards_still_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        for sid in ("ENH-141", "ENH-142", "ENH-143", "ENH-144",
                    "ENH-145", "ENH-153"):
            s = next(s for s in STANDARDS_REGISTRY
                     if s.standard_id == sid)
            assert s.status == "active", (
                f"{sid} regression: {s.status}")

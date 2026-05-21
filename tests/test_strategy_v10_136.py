"""tests/test_strategy_v10_136.py — v10.136 Phase 1 Strategy standards 3 & 4.

Closes ENH-143 Strategic Pillars & Workstream Contribution Mapping and
ENH-144 Strategic Initiative & Portfolio Management — third and fourth
of 15 Strategy Module standards (#141-155).

Verifies:
  ENH-143 StrategyDecompositionEngine
    1. define_strategic_pillars returns 3-5 pillars (per doc spec)
    2. Selection scored by vision keyword match
    3. Each pillar has required fields (name, owner, success_metrics, workstreams)
    4. map_workstream_contributions produces matrix with department mapping
    5. LLM hook fallback on exception

  ENH-144 StrategicInitiativePortfolio
    1. prioritize_initiatives full pipeline returns expected shape
    2. Knapsack honors budget constraint strictly (total ≤ budget)
    3. Combined score formula: 0.5×strategic + 0.3×roi + 0.2×(100-risk)
    4. Knapsack deterministic — same input → same selection
    5. Initiative normalization handles seed schema (id → initiative_code)
    6. ROI score band mapping correct
    7. Risk score derivation when risk_band missing
    8. Phasing buckets initiatives by duration

  Registry
    1. ENH-143 status='active' with affected_engines=('strategy_decomposition',)
    2. ENH-144 status='active' with affected_engines=('initiative_portfolio',)
    3. ENH-145 through ENH-155 still planned

  No regression
    1. G144 still 264/264
    2. G119 still passes
    3. ENH-141 + ENH-142 still active (v10.135 work intact)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── ENH-143 StrategyDecompositionEngine ────────────────────────────

class TestStrategyDecompositionEngine:

    @pytest.fixture
    def engine(self):
        from utils.strategy_decomposition import StrategyDecompositionEngine
        return StrategyDecompositionEngine()

    def test_pillars_count_in_3_to_5(self, engine):
        pillars = engine.define_strategic_pillars(
            "digital transformation customer experience growth")
        assert 3 <= len(pillars) <= 5

    def test_pillars_have_required_fields(self, engine):
        pillars = engine.define_strategic_pillars("digital growth")
        for p in pillars:
            for f in ("name", "description", "owner",
                      "success_metrics", "workstreams",
                      "target_date", "selection_score", "basis"):
                assert f in p, f"Pillar {p.get('name')} missing {f}"

    def test_pillars_sorted_by_score_desc(self, engine):
        pillars = engine.define_strategic_pillars(
            "digital transformation and AI/ML innovation")
        scores = [p["selection_score"] for p in pillars]
        assert scores == sorted(scores, reverse=True)

    def test_digital_vision_picks_digital_pillar_first(self, engine):
        """Vision heavy with 'digital' keywords should rank Digital
        & Data Transformation pillar highest."""
        pillars = engine.define_strategic_pillars(
            "digital transformation, AI, ML, API, platform innovation")
        assert pillars[0]["name"] == "Digital & Data Transformation"

    def test_workstream_contribution_matrix(self, engine):
        pillars = engine.define_strategic_pillars("digital growth")
        matrix = engine.map_workstream_contributions(pillars)
        assert len(matrix) > 0
        for row in matrix:
            for f in ("pillar", "workstream", "owner",
                      "departments", "role_contributions",
                      "success_criteria", "target_date"):
                assert f in row

    def test_each_workstream_row_has_departments(self, engine):
        pillars = engine.define_strategic_pillars(
            "digital transformation operational excellence")
        matrix = engine.map_workstream_contributions(pillars)
        # At least one row should have ≥ 1 department mapped
        rows_with_depts = [r for r in matrix if r["departments"]]
        assert len(rows_with_depts) > 0

    def test_lead_role_assigned_to_first_dept(self, engine):
        pillars = engine.define_strategic_pillars("digital")
        matrix = engine.map_workstream_contributions(pillars)
        for row in matrix:
            if not row["role_contributions"]:
                continue
            lead = row["role_contributions"][0]
            assert lead["role"] == "Lead"

    def test_basis_rule_based_when_no_llm(self, engine):
        pillars = engine.define_strategic_pillars("digital")
        for p in pillars:
            assert p["basis"] == "rule_based"

    def test_llm_hook_fallback_on_exception(self):
        from utils.strategy_decomposition import StrategyDecompositionEngine

        def broken(template, vision):
            raise RuntimeError("LLM outage")

        engine = StrategyDecompositionEngine(ai_refiner_fn=broken)
        pillars = engine.define_strategic_pillars("digital")
        # Should fall back to rule_based with explanatory note
        for p in pillars:
            assert p["basis"] == "rule_based"
            assert "RuntimeError" in p.get("fallback_reason", "")


# ─── ENH-144 StrategicInitiativePortfolio ──────────────────────────

class TestStrategicInitiativePortfolio:

    @pytest.fixture
    def pillars(self):
        from utils.strategy_decomposition import StrategyDecompositionEngine
        return StrategyDecompositionEngine().define_strategic_pillars(
            "digital transformation and operational excellence")

    @pytest.fixture
    def portfolio(self):
        from utils.initiative_portfolio import StrategicInitiativePortfolio
        return StrategicInitiativePortfolio()

    def test_prioritize_returns_expected_shape(self, portfolio, pillars):
        result = portfolio.prioritize_initiatives(
            pillars, budget_constraint=500_000_000)
        for f in ("selected_initiatives", "deferred_initiatives",
                  "total_cost", "total_expected_roi",
                  "weighted_strategic_score", "recommended_phasing",
                  "budget_used_pct", "n_proposed", "n_selected",
                  "n_deferred", "generated_at", "basis"):
            assert f in result

    def test_budget_constraint_strictly_honored(self, portfolio, pillars):
        """Total cost of selected must be ≤ budget."""
        budget = 200_000_000  # KES 200M
        result = portfolio.prioritize_initiatives(pillars, budget)
        assert result["total_cost"] <= budget, (
            f"Budget overshoot: total {result['total_cost']:,} > "
            f"budget {budget:,}")
        assert result["budget_used_pct"] <= 100.0

    def test_combined_score_formula(self, portfolio, pillars):
        """combined_score = 0.5*strategic + 0.3*roi + 0.2*(100-risk)"""
        result = portfolio.prioritize_initiatives(pillars, 500_000_000)
        for ini in result["selected_initiatives"]:
            expected = round(
                ini["strategic_score"] * 0.5
                + ini["roi_score"] * 0.3
                + (100 - ini["risk_score"]) * 0.2,
                2)
            assert ini["combined_score"] == expected

    def test_knapsack_deterministic(self, portfolio, pillars):
        """Same input → same selection."""
        r1 = portfolio.prioritize_initiatives(pillars, 300_000_000)
        r2 = portfolio.prioritize_initiatives(pillars, 300_000_000)
        codes1 = sorted(i["initiative_code"]
                        for i in r1["selected_initiatives"])
        codes2 = sorted(i["initiative_code"]
                        for i in r2["selected_initiatives"])
        assert codes1 == codes2

    def test_initiative_normalization(self, portfolio):
        """Pre-existing strategic_initiatives.json has 'id', 'name',
        'budget_kes_m' fields. Normalization maps them to canonical
        initiative_code, initiative_name, estimated_cost."""
        from utils.strategy_decomposition import StrategyDecompositionEngine
        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            "digital")
        inis = portfolio.get_proposed_initiatives(pillars)
        for ini in inis:
            assert "initiative_code" in ini
            assert "initiative_name" in ini
            assert "estimated_cost" in ini
            assert "expected_roi" in ini
            assert "duration_months" in ini
            assert "risk_band" in ini

    def test_roi_score_band_mapping(self, portfolio):
        """Verify ROI mapping bands."""
        # 5% → 20
        assert portfolio.calculate_roi_score(
            {"expected_roi": 5}) == 20.0
        # 10% → 40
        assert portfolio.calculate_roi_score(
            {"expected_roi": 10}) == 40.0
        # 20% → 70
        assert portfolio.calculate_roi_score(
            {"expected_roi": 20}) == 70.0
        # Negative → 0
        assert portfolio.calculate_roi_score(
            {"expected_roi": -5}) == 0.0
        # Over 30 → cap near 100
        score_30 = portfolio.calculate_roi_score({"expected_roi": 30})
        assert 80 <= score_30 <= 100

    def test_risk_assessment_uses_risk_band_when_present(self, portfolio):
        """If risk_band field is set, it's returned directly."""
        ini = {"risk_band": 75}
        assert portfolio.assess_risk(ini) == 75.0

    def test_risk_assessment_derives_when_band_missing(self, portfolio):
        """If risk_band absent, derive from cost + duration."""
        # High cost + long duration → high risk
        from utils.initiative_portfolio import (COST_BAND_HIGH,
            COST_BAND_LOW)
        high_risk_ini = {
            "estimated_cost": COST_BAND_HIGH,
            "duration_months": 24,
        }
        assert portfolio.assess_risk(high_risk_ini) >= 70

        low_risk_ini = {
            "estimated_cost": COST_BAND_LOW,
            "duration_months": 6,
        }
        assert portfolio.assess_risk(low_risk_ini) < 50

    def test_phasing_buckets_by_duration(self, portfolio):
        selected = [
            {"initiative_code": "A", "duration_months": 4},   # phase 1
            {"initiative_code": "B", "duration_months": 9},   # phase 2
            {"initiative_code": "C", "duration_months": 18},  # phase 3
        ]
        phasing = portfolio.phase_initiatives(selected)
        ph_dict = {p["phase"]: p["initiative_codes"] for p in phasing}
        assert "A" in ph_dict["Phase 1 (Q1-Q2)"]
        assert "B" in ph_dict["Phase 2 (Q3-Q4)"]
        assert "C" in ph_dict["Phase 3 (Year 2+)"]

    def test_strategic_score_alignment(self, portfolio, pillars):
        """Initiative whose kpi_link matches pillar's success_metrics
        should score higher than one with no overlap."""
        pillar_with_metrics = next(p for p in pillars
                                   if p.get("success_metrics"))
        # Initiative aligned
        aligned = {
            "pillar": pillar_with_metrics["name"],
            "kpi_link": list(pillar_with_metrics["success_metrics"]),
        }
        # Initiative not aligned
        unaligned = {
            "pillar": pillar_with_metrics["name"],
            "kpi_link": [],
        }
        s1 = portfolio.calculate_strategic_score(aligned, pillars)
        s2 = portfolio.calculate_strategic_score(unaligned, pillars)
        assert s1 > s2

    def test_zero_budget_returns_empty_selection(self, portfolio, pillars):
        result = portfolio.prioritize_initiatives(pillars, 0)
        assert result["n_selected"] == 0
        assert result["total_cost"] == 0


# ─── End-to-end pipeline ────────────────────────────────────────────

class TestStrategyPipeline:

    def test_full_pipeline_swot_to_portfolio(self):
        """ENH-141 → ENH-142 → ENH-143 → ENH-144 chains end-to-end."""
        from utils.strategy_formulation import StrategyFormulationEngine
        from utils.strategic_options import StrategicOptionsGenerator
        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.initiative_portfolio import StrategicInitiativePortfolio

        vision = "Digital transformation and customer-centric growth"

        swot = StrategyFormulationEngine().generate_swot()
        options = StrategicOptionsGenerator().generate_options(vision, swot)
        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            vision, options["options"])
        portfolio = StrategicInitiativePortfolio().prioritize_initiatives(
            pillars, budget_constraint=400_000_000)

        # Full pipeline produced output
        assert len(swot["swot"]) == 4
        assert len(options["options"]) == 4
        assert 3 <= len(pillars) <= 5
        assert portfolio["n_proposed"] > 0
        assert portfolio["total_cost"] <= 400_000_000


# ─── Registry flips ─────────────────────────────────────────────────

class TestRegistryFlipped:

    def test_enh_143_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-143")
        assert s.status == "active"
        assert "strategy_decomposition" in s.affected_engines

    def test_enh_144_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-144")
        assert s.status == "active"
        assert "initiative_portfolio" in s.affected_engines

    def test_other_strategy_standards_still_planned(self):
        """At v10.136, ENH-141/142/143/144 active; #145-155 still planned."""
        from utils.standards_registry import STANDARDS_REGISTRY
        for n in range(145, 156):
            s = next(s for s in STANDARDS_REGISTRY
                     if s.standard_id == f"ENH-{n}")
            assert s.status == "planned", (
                f"ENH-{n} should be planned, got {s.status}")


# ─── No regression ─────────────────────────────────────────────────

class TestNoRegression:

    def test_g144_still_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_qa_spec_complete()
        finally:
            sys.path.pop(0)
        assert r["passed"]
        assert r["registry_match"] == 264

    def test_g119_still_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_enhancement_standards_registered()
        finally:
            sys.path.pop(0)
        assert r["passed"]

    def test_enh_141_still_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-141")
        assert s.status == "active"

    def test_enh_142_still_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-142")
        assert s.status == "active"

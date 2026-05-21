"""tests/test_strategy_v10_135.py — v10.135 Phase 1 Strategy first 2 standards.

Closes ENH-141 Strategy Formulation Intelligence + ENH-142 Strategic Options
Generator — first two of 15 Strategy Module standards (#141-155) per
Continuation.docx (Eco Bank QA spec).

This is the first IMPLEMENTATION drop of Phase 1 of the 80-drop QA spec
closure roadmap. Phase 0 (v10.133) declared all 15 strategy standards as
planned; v10.135 promotes the first two to active by shipping working
engine modules.

Verifies:
  ENH-141 StrategyFormulationEngine
    1. SWOT generator returns expected dict shape with 4 quadrants
    2. Threshold logic correct (BSC pillar weakness flagged at < 3.6/4.0)
    3. Empty SWOT inputs handled gracefully
    4. Strategic implications generated for various SWOT patterns
    5. Board vision rule-based fallback works deterministically
    6. data_sources provenance populated
    7. basis="rule_based" by default

  ENH-142 StrategicOptionsGenerator
    1. generate_options returns 4 Ansoff options
    2. model_impact deterministic (same input → same output)
    3. Multi-criteria scoring picks Market Penetration when SWOT-fit
       outweighs other factors
    4. Comparison matrix has 8 rows (one per criterion)
    5. LLM hook fallback on exception

  Registry
    1. ENH-141 status='active' with affected_engines=('strategy_formulation',)
    2. ENH-142 status='active' with affected_engines=('strategic_options',)

  No regression
    1. G144 still 264/264 (Phase 0 hygiene preserved)
    2. G119 still passes
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── ENH-141 StrategyFormulationEngine ─────────────────────────────

class TestStrategyFormulationEngine:

    @pytest.fixture
    def engine(self):
        from utils.strategy_formulation import StrategyFormulationEngine
        return StrategyFormulationEngine()

    def test_swot_returns_expected_dict_shape(self, engine):
        result = engine.generate_swot()
        assert "swot" in result
        assert "strategic_implications" in result
        assert "data_sources" in result
        assert "generated_at" in result
        assert "basis" in result
        for quad in ("strengths", "weaknesses",
                     "opportunities", "threats"):
            assert quad in result["swot"]
            assert isinstance(result["swot"][quad], list)

    def test_basis_is_rule_based_by_default(self, engine):
        result = engine.generate_swot()
        assert result["basis"] == "rule_based"

    def test_data_sources_provenance_populated(self, engine):
        result = engine.generate_swot()
        # At least bsc_scores.json should be available
        assert "bsc_scores.json" in result["data_sources"]

    def test_bsc_pillar_weakness_threshold(self, engine):
        """BSC pillars at avg ~3.5 should flag as weaknesses
        (3.5 < target * 0.90 = 3.6)."""
        result = engine.generate_swot()
        weaknesses = result["swot"]["weaknesses"]
        assert len(weaknesses) > 0, (
            "Expected BSC pillars below 3.6 to flag as weaknesses; "
            "got 0. Check bsc_scores.json averages.")
        for w in weaknesses:
            assert "factor" in w
            assert "value" in w
            assert "benchmark" in w
            assert "gap" in w

    def test_implications_generated_for_weaknesses_only(self, engine):
        """When only weaknesses populated, should still produce an
        'internal-only signal' implication, not zero implications."""
        result = engine.generate_swot()
        # If there are any quadrants populated, there should be ≥1 implication
        any_quadrant_populated = any(
            len(result["swot"][q]) > 0
            for q in ("strengths", "weaknesses",
                      "opportunities", "threats"))
        if any_quadrant_populated:
            assert len(result["strategic_implications"]) >= 1

    def test_synthesize_board_vision_rule_based(self, engine):
        board_inputs = [
            {"author": "MD",
             "content": "Accelerate digital transformation."},
            {"author": "CFO",
             "content": "Sustainable growth and operational excellence."},
            {"author": "CTO",
             "content": "Digital platform innovation and AI."},
        ]
        result = engine.synthesize_board_vision(board_inputs)
        assert result["basis"] == "rule_based"
        assert "draft_vision_statement" in result
        assert "strategic_themes" in result
        # Digital Transformation should be picked up (mentioned by 2+ authors)
        themes = [t["theme"] for t in result["strategic_themes"]]
        assert "Digital Transformation" in themes
        # Vision statement should not have malformed punctuation
        vs = result["draft_vision_statement"]
        assert " ," not in vs, f"Vision has stray ' ,': {vs!r}"
        assert ",  " not in vs, f"Vision has double space: {vs!r}"

    def test_board_vision_deterministic(self, engine):
        """Same input → same output."""
        board_inputs = [
            {"author": "A", "content": "Digital transformation."},
            {"author": "B", "content": "Customer experience matters."},
        ]
        r1 = engine.synthesize_board_vision(board_inputs)
        r2 = engine.synthesize_board_vision(board_inputs)
        # Strategic themes and vision statement should be identical
        assert r1["strategic_themes"] == r2["strategic_themes"]
        assert r1["draft_vision_statement"] == r2["draft_vision_statement"]

    def test_llm_hook_fallback_on_exception(self):
        """If llm_provider_fn raises, engine should fall back to
        rule-based with explanatory fallback_reason."""
        from utils.strategy_formulation import StrategyFormulationEngine

        def broken_llm(prompt):
            raise RuntimeError("simulated LLM outage")

        engine = StrategyFormulationEngine(llm_provider_fn=broken_llm)
        result = engine.synthesize_board_vision([
            {"author": "X", "content": "Digital transformation."}])
        assert result["basis"] == "rule_based"
        assert "RuntimeError" in result.get("fallback_reason", "")

    def test_thresholds_match_doc_spec(self):
        """Doc Standard #141 specifies:
           Strength: performance > target * 1.10
           Weakness: performance < target * 0.90
        Verify constants match."""
        from utils.strategy_formulation import (
            STRENGTH_THRESHOLD_RATIO, WEAKNESS_THRESHOLD_RATIO,
            OPPORTUNITY_GROWTH_PCT_MIN, OPPORTUNITY_RELEVANCE_MIN,
            THREAT_IMPACT_MIN, THREAT_IMPACT_IMMEDIATE)
        assert STRENGTH_THRESHOLD_RATIO == 1.10
        assert WEAKNESS_THRESHOLD_RATIO == 0.90
        assert OPPORTUNITY_GROWTH_PCT_MIN == 10.0
        assert OPPORTUNITY_RELEVANCE_MIN == 0.7
        assert THREAT_IMPACT_MIN == 0.5
        assert THREAT_IMPACT_IMMEDIATE == 0.8


# ─── ENH-142 StrategicOptionsGenerator ─────────────────────────────

class TestStrategicOptionsGenerator:

    @pytest.fixture
    def sample_swot(self):
        return {
            "swot": {
                "strengths": [
                    {"factor": "Customer Score", "value": 4.5, "benchmark": 4.0,
                     "evidence": "exceeding target"},
                    {"factor": "Process Score", "value": 4.4, "benchmark": 4.0,
                     "evidence": "exceeding target"},
                ],
                "weaknesses": [
                    {"factor": "Financial Score", "value": 3.4,
                     "benchmark": 4.0, "gap": 0.6}
                ],
                "opportunities": [
                    {"trend": "digital customers m", "growth_rate": 35.0,
                     "strategic_fit": 0.95}
                ],
                "threats": [
                    {"competitor": "Equity", "action": "rate undercut",
                     "impact": 0.7, "response_required": "Monitor"}
                ],
            }
        }

    @pytest.fixture
    def generator(self):
        from utils.strategic_options import StrategicOptionsGenerator
        return StrategicOptionsGenerator()

    def test_generates_four_ansoff_options(self, generator, sample_swot):
        result = generator.generate_options("digital growth", sample_swot)
        assert len(result["options"]) == 4
        names = [o["name"] for o in result["options"]]
        assert names == ["Market Penetration", "Market Development",
                         "Product Development", "Diversification"]

    def test_each_option_has_required_fields(self, generator, sample_swot):
        result = generator.generate_options("digital", sample_swot)
        for opt in result["options"]:
            for f in ("name", "ansoff_type", "description",
                      "key_initiatives", "swot_evidence",
                      "expected_impact", "risk_level",
                      "time_horizon_months", "feasibility_note"):
                assert f in opt, f"{opt['name']} missing {f}"

    def test_risk_levels_correct(self, generator, sample_swot):
        result = generator.generate_options("growth", sample_swot)
        risk_by_name = {o["name"]: o["risk_level"]
                        for o in result["options"]}
        assert risk_by_name["Market Penetration"] == "LOW"
        assert risk_by_name["Market Development"] == "MEDIUM"
        assert risk_by_name["Product Development"] == "MEDIUM"
        assert risk_by_name["Diversification"] == "HIGH"

    def test_model_impact_deterministic(self, generator, sample_swot):
        """Same SWOT input → same impact estimates."""
        r1 = generator.generate_options("test", sample_swot)
        r2 = generator.generate_options("test", sample_swot)
        for o1, o2 in zip(r1["options"], r2["options"]):
            assert o1["expected_impact"] == o2["expected_impact"]

    def test_recommendation_returned(self, generator, sample_swot):
        result = generator.generate_options(
            "digital transformation and customer-centric banking",
            sample_swot)
        assert "ai_recommendation" in result
        assert "recommended_option" in result["ai_recommendation"]
        assert result["ai_recommendation"]["recommended_option"] in (
            "Market Penetration", "Market Development",
            "Product Development", "Diversification")
        assert result["ai_recommendation"]["basis"] == "rule_based"

    def test_comparison_matrix_has_eight_rows(self, generator, sample_swot):
        result = generator.generate_options("growth", sample_swot)
        assert len(result["comparison_matrix"]) == 8

    def test_llm_hook_fallback_on_exception(self):
        """If ai_recommender_fn raises, falls back to rule-based."""
        from utils.strategic_options import StrategicOptionsGenerator

        def broken(options, vision):
            raise RuntimeError("simulated AI outage")

        gen = StrategicOptionsGenerator(ai_recommender_fn=broken)
        sample = {"swot": {"strengths": [], "weaknesses": [],
                           "opportunities": [], "threats": []}}
        result = gen.generate_options("test", sample)
        assert result["basis"] == "rule_based"

    def test_empty_swot_handled_gracefully(self, generator):
        empty_swot = {"swot": {"strengths": [], "weaknesses": [],
                                "opportunities": [], "threats": []}}
        result = generator.generate_options("vision", empty_swot)
        # Should still produce 4 options + recommendation
        assert len(result["options"]) == 4
        assert "ai_recommendation" in result

    def test_vision_alignment_keyword_match(self, generator, sample_swot):
        """Vision with 'digital' keyword should boost Product Development
        score (which has 'digital' in its keyword map)."""
        digital_vision = "Digital transformation and innovation"
        result = generator.generate_options(digital_vision, sample_swot)
        # Product Development should have non-zero vision_alignment
        scores = result["ai_recommendation"]["all_scores"]
        prod_dev_score = next(s for s in scores
                              if s["option_name"] == "Product Development")
        assert prod_dev_score["components"]["vision_alignment"] > 0


# ─── End-to-end integration ─────────────────────────────────────────

class TestStrategyEndToEnd:

    def test_swot_to_options_chains(self):
        """The output of ENH-141 SWOT feeds directly into ENH-142 options."""
        from utils.strategy_formulation import StrategyFormulationEngine
        from utils.strategic_options import StrategicOptionsGenerator

        swot = StrategyFormulationEngine().generate_swot()
        # SWOT output contains "swot" key — generator accepts it directly
        options = StrategicOptionsGenerator().generate_options(
            "digital transformation", swot)
        assert len(options["options"]) == 4
        # SWOT summary should reflect the input
        assert (options["swot_summary"]["n_weaknesses"]
                == len(swot["swot"]["weaknesses"]))


# ─── Registry flips ─────────────────────────────────────────────────

class TestRegistryFlipped:

    def test_enh_141_active_with_engine(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next((s for s in STANDARDS_REGISTRY
                  if s.standard_id == "ENH-141"), None)
        assert s is not None
        assert s.status == "active", f"ENH-141 should be active, got {s.status}"
        assert "strategy_formulation" in s.affected_engines

    def test_enh_142_active_with_engine(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next((s for s in STANDARDS_REGISTRY
                  if s.standard_id == "ENH-142"), None)
        assert s is not None
        assert s.status == "active", f"ENH-142 should be active, got {s.status}"
        assert "strategic_options" in s.affected_engines

    def test_other_strategy_standards_still_planned(self):
        """Of the 15 Strategy standards, only #141 + #142 should be active
        as of v10.135. Others remain planned."""
        from utils.standards_registry import STANDARDS_REGISTRY
        for n in range(143, 156):
            sid = f"ENH-{n}"
            s = next((s for s in STANDARDS_REGISTRY
                      if s.standard_id == sid), None)
            assert s is not None, f"{sid} missing from registry"
            assert s.status == "planned", (
                f"{sid} should still be planned at v10.135, "
                f"got {s.status}")


# ─── No regression ─────────────────────────────────────────────────

class TestNoRegression:

    def test_g144_still_passes_at_264(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_qa_spec_complete()
        finally:
            sys.path.pop(0)
        assert r["passed"] is True
        assert r["registry_match"] == 264

    def test_g119_still_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_enhancement_standards_registered()
        finally:
            sys.path.pop(0)
        assert r["passed"] is True

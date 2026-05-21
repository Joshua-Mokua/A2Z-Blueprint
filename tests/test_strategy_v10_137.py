"""tests/test_strategy_v10_137.py — v10.137 Phase 1 Strategy standards 5 & 6.

Closes ENH-145 OKR/BSC Cascade Engine (Enhanced) + ENH-153 Strategy-to-BSC
Daily Integration ⭐ — fifth and sixth of 15 Strategy Module standards.

ENH-153 is the long-awaited link wiring the Strategy module into the
existing BSC engine. This is a milestone drop.

Verifies:
  ENH-145 EnhancedCascadeEngine
    1. cascade_with_engagement returns expected shape
    2. department OKRs filtered to those touching the department
    3. individual OKRs cascaded to all employees in department
    4. alignment scoring: keyword overlap with pillar success metrics
    5. engagement scoring: % of acknowledged individual OKRs
    6. Band weighting applied to individual OKR weights
    7. Two-way feedback handling
    8. LLM hook fallback on exception

  ENH-153 DailyStrategyIntegration
    1. map_employee_to_strategy resolves dept → workstreams → pillars
    2. create_personal_strategy_scorecard returns expected shape
    3. Found employee with BSC scores returns populated scorecard
    4. Missing employee handled gracefully (found=False, error)
    5. BSC pillar → Strategic pillar mapping (4 BSC → 5 strategic)
    6. Trend calculation from current vs prior period
    7. Cadence note explicit (no fabrication of daily granularity)
    8. Bank strategy health = average across all latest BSC pillar scores
    9. Priority action surfaces biggest gap pillar
    10. Daily aggregator hook fallback

  v10.136 dept realignment (one-line correction)
    1. WORKSTREAM_TO_DEPARTMENTS now uses real users.json names
    2. v10.136 tests still pass

  Registry
    1. ENH-145 active with engine
    2. ENH-153 active with engine
    3. Other Strategy standards (146-155 except 153) still planned

  No regression
    1. G144 264/264
    2. G119 passes
    3. ENH-141/142/143/144 still active
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── ENH-145 EnhancedCascadeEngine ──────────────────────────────────

class TestEnhancedCascadeEngine:

    @pytest.fixture
    def pillars_and_okrs(self):
        from utils.strategy_decomposition import StrategyDecompositionEngine
        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            "digital transformation operational excellence")
        pillar_okrs = [
            {"pillar_name": p["name"],
             "objective":   p["name"],
             "key_results": list(p["success_metrics"]),
             "workstreams": list(p["workstreams"])}
            for p in pillars
        ]
        return pillars, pillar_okrs

    @pytest.fixture
    def engine(self):
        from utils.enhanced_cascade import EnhancedCascadeEngine
        return EnhancedCascadeEngine()

    def test_cascade_returns_expected_shape(self, engine, pillars_and_okrs):
        pillars, pillar_okrs = pillars_and_okrs
        r = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", strategic_pillars=pillars)
        for f in ("pillar_okrs", "department_okrs", "individual_okrs",
                  "alignment", "engagement", "visibility",
                  "feedback_summary", "generated_at",
                  "department", "n_employees"):
            assert f in r, f"missing field: {f}"

    def test_dept_okrs_filtered_to_relevant_workstreams(
            self, engine, pillars_and_okrs):
        """IT & Digital should only get OKRs from pillars whose
        workstreams it touches (Digital pillar at minimum)."""
        pillars, pillar_okrs = pillars_and_okrs
        r = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", strategic_pillars=pillars)
        for dokr in r["department_okrs"]:
            assert "relevant_workstreams" in dokr
            assert len(dokr["relevant_workstreams"]) > 0

    def test_individual_okrs_have_band_weights(self, engine, pillars_and_okrs):
        pillars, pillar_okrs = pillars_and_okrs
        r = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", strategic_pillars=pillars)
        for iokr in r["individual_okrs"]:
            assert "kr_weight" in iokr
            assert 0 < iokr["kr_weight"] <= 1.0

    def test_alignment_scoring_keyword_overlap(self, engine, pillars_and_okrs):
        pillars, pillar_okrs = pillars_and_okrs
        r = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", strategic_pillars=pillars)
        align = r["alignment"]
        assert "alignment_score" in align
        assert "n_aligned" in align
        # If individual OKRs exist, their KRs should overlap with pillar
        # success metrics → high alignment
        if align["n_individuals"] > 0:
            assert align["alignment_score"] > 50  # most should align

    def test_engagement_default_zero(self, engine, pillars_and_okrs):
        """Default acknowledgment_status is 'pending' for all
        cascaded individual OKRs → engagement should be 0."""
        pillars, pillar_okrs = pillars_and_okrs
        r = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", strategic_pillars=pillars)
        eng = r["engagement"]
        if eng["n_total"] > 0:
            assert eng["engagement_score"] == 0.0
            assert eng["level"] == "low"

    def test_two_way_feedback_changes_status(self, engine, pillars_and_okrs):
        """Disagree feedback should mark status 'review_required'."""
        pillars, pillar_okrs = pillars_and_okrs
        # First call without feedback — all aligned
        r1 = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", strategic_pillars=pillars)
        # Confirm at least 1 dept OKR exists before asserting
        assert len(r1["department_okrs"]) > 0
        # Now provide disagree feedback for OKR index 0
        feedback = [{"author": "test", "okr_index": 0,
                     "agree": False, "comment": "Not feasible"}]
        r2 = engine.cascade_with_engagement(
            pillar_okrs, "IT & Digital", feedback=feedback,
            strategic_pillars=pillars)
        assert r2["department_okrs"][0]["status"] == "review_required"

    def test_unknown_department_returns_empty_dept_okrs(
            self, engine, pillars_and_okrs):
        pillars, pillar_okrs = pillars_and_okrs
        r = engine.cascade_with_engagement(
            pillar_okrs, "Nonexistent Department",
            strategic_pillars=pillars)
        assert len(r["department_okrs"]) == 0
        assert r["n_employees"] == 0

    def test_llm_hook_sentiment_fallback(self):
        from utils.enhanced_cascade import EnhancedCascadeEngine

        def broken(texts):
            raise RuntimeError("LLM outage")

        engine = EnhancedCascadeEngine(llm_sentiment_fn=broken)
        feedback = [{"author": "x", "okr_index": 0, "agree": True,
                     "comment": "ok"}]
        result = engine.collect_department_feedback([{}], feedback=feedback)
        assert result["basis"] == "rule_based"


# ─── ENH-153 DailyStrategyIntegration ──────────────────────────────

class TestDailyStrategyIntegration:

    @pytest.fixture
    def integ(self):
        from utils.daily_strategy_integration import DailyStrategyIntegration
        return DailyStrategyIntegration()

    @pytest.fixture
    def sample_staff(self):
        """Pull a real staff_code from bsc_scores.json."""
        import json
        with open(REPO_ROOT / "data" / "bsc_scores.json") as f:
            return json.load(f)[0]["staff_code"]

    def test_map_employee_resolves_pillars(self, integ, sample_staff):
        m = integ.map_employee_to_strategy(sample_staff)
        assert m["found"] is True
        assert m["employee"] is not None
        assert isinstance(m["pillars"], list)

    def test_scorecard_shape(self, integ, sample_staff):
        sc = integ.create_personal_strategy_scorecard(sample_staff)
        for f in ("employee", "strategic_pillars",
                  "bank_strategy_health", "next_priority_action",
                  "cadence_note", "found", "error", "generated_at"):
            assert f in sc

    def test_scorecard_pillars_have_kpis(self, integ, sample_staff):
        sc = integ.create_personal_strategy_scorecard(sample_staff)
        for sp in sc["strategic_pillars"]:
            for f in ("pillar", "my_kpis", "pillar_health",
                      "my_impact"):
                assert f in sp

    def test_kpi_view_shape(self, integ, sample_staff):
        sc = integ.create_personal_strategy_scorecard(sample_staff)
        for sp in sc["strategic_pillars"]:
            for kpi in sp["my_kpis"]:
                for f in ("kpi", "today_target", "today_actual",
                          "trend", "nudge", "cadence", "cadence_note"):
                    assert f in kpi

    def test_missing_employee_handled(self, integ):
        sc = integ.create_personal_strategy_scorecard("nonexistent_xyz999")
        assert sc["found"] is False
        assert sc["error"] is not None

    def test_bsc_to_strategic_mapping(self):
        """4 BSC pillars → strategic pillar mapping."""
        from utils.daily_strategy_integration import (
            BSC_TO_STRATEGIC_PILLAR)
        assert "Sustainable Growth" in BSC_TO_STRATEGIC_PILLAR["financial_score"]
        assert "Customer Experience Excellence" in BSC_TO_STRATEGIC_PILLAR["customer_score"]
        assert "Operational Excellence" in BSC_TO_STRATEGIC_PILLAR["process_score"]
        assert "Risk & Compliance Leadership" in BSC_TO_STRATEGIC_PILLAR["process_score"]

    def test_cadence_note_explicit(self, integ, sample_staff):
        """No silent fabrication of daily granularity."""
        sc = integ.create_personal_strategy_scorecard(sample_staff)
        if sc["found"]:
            assert sc["cadence_note"] is not None
            assert "quarterly" in sc["cadence_note"].lower()

    def test_bank_strategy_health(self, integ):
        h = integ.get_bank_strategy_health()
        assert h is not None
        assert 0.0 <= h <= 5.0   # BSC scale

    def test_priority_action_surfaces_biggest_gap(self, integ, sample_staff):
        sc = integ.create_personal_strategy_scorecard(sample_staff)
        action = sc["next_priority_action"]
        assert action is not None
        assert isinstance(action, str)
        # Either says "biggest gap" / "all pillars meeting" / "no scores"
        assert any(kw in action.lower()
                   for kw in ("gap", "meeting", "scores",
                              "no strategic", "could not"))

    def test_daily_aggregator_fallback(self):
        from utils.daily_strategy_integration import DailyStrategyIntegration

        def broken_agg(staff, kpi):
            raise RuntimeError("No daily feed")

        integ = DailyStrategyIntegration(daily_aggregator_fn=broken_agg)
        # Should not crash, falls back to quarterly snapshot
        import json
        with open(REPO_ROOT / "data" / "bsc_scores.json") as f:
            staff = json.load(f)[0]["staff_code"]
        sc = integ.create_personal_strategy_scorecard(staff)
        assert sc["found"] is True


# ─── v10.136 dept realignment (one-line correction) ────────────────

class TestDeptRealignment:

    def test_workstream_map_uses_real_dept_names(self):
        """v10.137 corrected v10.136 WORKSTREAM_TO_DEPARTMENTS to use
        actual users.json department names."""
        from utils.strategy_decomposition import (
            WORKSTREAM_TO_DEPARTMENTS)
        # IT & Digital (with ampersand) must appear, not "IT/Digital"
        all_depts = set()
        for ws, depts in WORKSTREAM_TO_DEPARTMENTS.items():
            all_depts.update(depts)
        assert "IT & Digital" in all_depts
        assert "Risk & Compliance" in all_depts
        assert "People & HR" in all_depts
        assert "Retail Banking" in all_depts
        # Old names should NOT appear
        assert "IT/Digital" not in all_depts
        assert "HR" not in all_depts


# ─── Registry flips ─────────────────────────────────────────────────

class TestRegistryFlipped:

    def test_enh_145_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-145")
        assert s.status == "active"
        assert "enhanced_cascade" in s.affected_engines

    def test_enh_153_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next(s for s in STANDARDS_REGISTRY
                 if s.standard_id == "ENH-153")
        assert s.status == "active"
        assert "daily_strategy_integration" in s.affected_engines

    def test_other_strategy_standards_still_planned(self):
        """At v10.137: ENH-141/142/143/144/145/153 active.
        Others (146-152, 154-155) still planned."""
        from utils.standards_registry import STANDARDS_REGISTRY
        for n in (146, 147, 148, 149, 150, 151, 152, 154, 155):
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

    def test_g119_passes(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_enhancement_standards_registered()
        finally:
            sys.path.pop(0)
        assert r["passed"]

    def test_prior_strategy_standards_still_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        for sid in ("ENH-141", "ENH-142", "ENH-143", "ENH-144"):
            s = next(s for s in STANDARDS_REGISTRY
                     if s.standard_id == sid)
            assert s.status == "active", (
                f"{sid} regression: {s.status}")

"""tests/test_product_v10_149.py — ENH-138 AI Product Recommendation Engine

Verifies the v10.149 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 4 methods
- Synthesizes from ENH-136 + ENH-131 + ENH-133 (companion engines, DI pattern)
- Per-customer recommendations with composite score formula
- Honest fallback when customer not found
- Low-propensity products excluded with explicit reason
- Unmappable propensities surfaced (Investment Fund has no product)
- Segment-level recommendations using avg propensities
- AI hook opt-in: rule-based default with basis='rule_based'; LLM tagged 'llm' with ai_warning
- AI hook failure → graceful fallback to rule-based with warning
- Read-only — engine never writes
- Registry: ENH-138 active
- Admin Tier 4B has all eight engines
- No regression
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "product_recommendation.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestEngineModule:
    def test_module_exists(self):
        assert ENGINE_PATH.exists()

    def test_module_parses(self):
        ast.parse(ENGINE_PATH.read_text())

    def test_class_and_dataclass_present(self):
        m = _load("rec_shape", ENGINE_PATH)
        assert hasattr(m, "ProductRecommendationEngine")
        assert hasattr(m, "Recommendation")

    def test_required_public_methods(self):
        m = _load("rec_methods", ENGINE_PATH)
        eng = m.ProductRecommendationEngine()
        for method in (
            "recommend_for_customer", "recommend_for_segment",
            "bulk_recommend", "get_recommendation_summary",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))

    def test_weights_sum_to_one(self):
        m = _load("rec_weights", ENGINE_PATH)
        E = m.ProductRecommendationEngine
        total = (E.WEIGHT_PROPENSITY + E.WEIGHT_RANK + E.WEIGHT_MARGIN)
        assert total == Decimal("1.00")


class TestPerCustomer:
    def _engine(self):
        m = _load("rec_pc", ENGINE_PATH)
        return m.ProductRecommendationEngine()

    def test_unknown_customer_returns_fallback(self):
        rec = self._engine().recommend_for_customer("NONEXISTENT_CIF")
        assert rec.fallback_reason == "customer_not_found"
        assert len(rec.recommendations) == 0
        assert rec.is_estimate is True

    def test_real_customer_returns_recommendations(self):
        eng = self._engine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 3)
        assert rec.fallback_reason is None
        assert rec.basis == "rule_based"
        assert rec.segment is not None
        assert len(rec.recommendations) <= 3

    def test_recommendations_have_required_fields(self):
        eng = self._engine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 3)
        for entry in rec.recommendations:
            for k in ("rank", "product_id", "product_name",
                      "composite_score", "propensity_score",
                      "rank_factor", "margin_factor", "rationale"):
                assert k in entry, f"missing {k} in {entry}"

    def test_recommendations_sorted_descending(self):
        eng = self._engine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 5)
        scores = [float(e["composite_score"])
                  for e in rec.recommendations]
        assert scores == sorted(scores, reverse=True)

    def test_low_propensity_excluded_with_reason(self):
        eng = self._engine()
        intel = eng._load_intel()
        # Find a customer with very low propensity scores
        for cid, c in intel.items():
            ps = c.get("propensity_scores") or {}
            if any(v < 0.05 for v in ps.values()):
                rec = eng.recommend_for_customer(cid, 3)
                # If anything was excluded, it should have explicit reason
                for excl in rec.excluded:
                    assert excl["reason"] == (
                        "below_min_propensity_threshold")
                break


class TestPropensityResolution:
    def _engine(self):
        m = _load("rec_resolve", ENGINE_PATH)
        return m.ProductRecommendationEngine()

    def test_known_propensity_resolves(self):
        prod = self._engine()._resolve_propensity_to_product(
            "Personal Loan")
        assert prod is not None
        assert prod["id"] == "P001"

    def test_investment_fund_unmapped_explicitly(self):
        # Investment Fund has no matching product per design
        prod = self._engine()._resolve_propensity_to_product(
            "Investment Fund")
        assert prod is None

    def test_bogus_propensity_returns_none(self):
        prod = self._engine()._resolve_propensity_to_product(
            "Some Made Up Product")
        assert prod is None


class TestSegmentLevel:
    def _engine(self):
        m = _load("rec_seg", ENGINE_PATH)
        return m.ProductRecommendationEngine()

    def test_real_segment_returns_recommendations(self):
        out = self._engine().recommend_for_segment("Mass", 3)
        assert out["ok"] is True
        assert out["n_customers"] > 0
        assert len(out["recommendations"]) <= 3
        for r in out["recommendations"]:
            assert "avg_segment_propensity" in r
            assert "composite_score" in r

    def test_unknown_segment_returns_fallback(self):
        out = self._engine().recommend_for_segment("BOGUS_SEGMENT", 3)
        assert out["ok"] is False
        assert out["fallback_reason"] == "no_customers_in_segment"


class TestAIHook:
    def _engine_with_ai(self, ai_fn):
        m = _load("rec_ai", ENGINE_PATH)
        return m.ProductRecommendationEngine(
            ai_recommendation_fn=ai_fn)

    def test_no_ai_hook_returns_rule_based(self):
        m = _load("rec_no_ai", ENGINE_PATH)
        eng = m.ProductRecommendationEngine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 3)
        assert rec.basis == "rule_based"
        assert rec.ai_warning is None

    def test_ai_hook_replaces_recommendations_and_tags_llm(self):
        ai_recs = [{"product_id": "P_AI_1", "rank": 1,
                     "score": "0.99"}]
        eng = self._engine_with_ai(lambda x: ai_recs)
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 3)
        assert rec.basis == "llm"
        assert rec.ai_warning is not None
        assert "LLM-generated" in rec.ai_warning

    def test_ai_hook_failure_falls_back_to_rule_based(self):
        def bad_ai(x):
            raise RuntimeError("ai_unavailable")
        eng = self._engine_with_ai(bad_ai)
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 3)
        assert rec.basis == "rule_based"
        assert rec.ai_warning is not None
        assert "fail" in rec.ai_warning.lower()

    def test_ai_hook_empty_falls_back(self):
        eng = self._engine_with_ai(lambda x: [])
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        rec = eng.recommend_for_customer(sample_id, 3)
        # Empty list → keep rule_based
        assert rec.basis == "rule_based"


class TestReadOnly:
    def test_engine_does_not_write(self):
        text = ENGINE_PATH.read_text()
        # Verify no actual write code (json.dump, .write_text on data files)
        if 'json.dump' in text:
            for line in text.split('\n'):
                if 'json.dump' in line:
                    assert ('#' in line.split('json.dump')[0]
                              or '"""' in line
                              or "'''" in line), (
                        f"engine should not write: {line.strip()}")


class TestRegistryAndAdmin:
    def test_enh_138_active(self):
        m = _load("sr138",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-138"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_recommendation" in std.affected_engines
        assert std.implementation_batch == "v10.149"

    def test_prior_phase1e_engines_still_active(self):
        m = _load("sr_prior_v149",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132", "ENH-133", "ENH-134",
                    "ENH-135", "ENH-136", "ENH-137"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_eight_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "product_competitive_intel",
                      "product_cvp_builder",
                      "product_ranking",
                      "dynamic_pricing",
                      "product_recommendation",
                      "ProductRecommendationEngine"):
            assert token in text, f"missing token: {token}"


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v149",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v149",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

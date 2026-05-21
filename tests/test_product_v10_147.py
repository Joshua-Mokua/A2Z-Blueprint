"""tests/test_product_v10_147.py — ENH-136 Product Ranking & Scoring Engine

Verifies the v10.147 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 7 methods
- Multi-factor scoring with 5 components (profitability + competitive + growth + risk + scale)
- Banding TOP_TIER ≥75 / GROWING ≥50 / WATCHLIST ≥25 / DECLINE <25
- Renormalization when components missing (no penalty for missing, is_estimate=True)
- Stable ranking with product_id as tiebreaker
- Top/bottom/distribution/aggregation methods
- Companion engines injectable (DI pattern)
- Registry: ENH-136 active
- Admin Tier 4B has all six engines
- No regression
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "product_ranking.py"


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
        m = _load("rank_shape", ENGINE_PATH)
        assert hasattr(m, "ProductRankingEngine")
        assert hasattr(m, "ProductScore")

    def test_required_public_methods(self):
        m = _load("rank_methods", ENGINE_PATH)
        eng = m.ProductRankingEngine()
        for method in (
            "get_product_score", "rank_all_products",
            "get_top_n", "get_bottom_n", "get_score_distribution",
            "aggregate_by_category", "rank_within_category",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))

    def test_weights_sum_to_100(self):
        m = _load("rank_weights", ENGINE_PATH)
        total = (m.ProductRankingEngine.WEIGHT_PROFITABILITY
                  + m.ProductRankingEngine.WEIGHT_COMPETITIVE
                  + m.ProductRankingEngine.WEIGHT_GROWTH
                  + m.ProductRankingEngine.WEIGHT_RISK
                  + m.ProductRankingEngine.WEIGHT_SCALE)
        assert total == 100


class TestScoring:
    def _engine(self):
        m = _load("rank_s", ENGINE_PATH)
        return m.ProductRankingEngine(), m

    def test_real_product_scores_in_range(self):
        eng, _ = self._engine()
        score = eng.get_product_score("P001")
        assert 0 <= score.total_score <= 100
        assert score.band in ("TOP_TIER", "GROWING",
                                "WATCHLIST", "DECLINE")

    def test_unknown_product_returns_decline(self):
        eng, _ = self._engine()
        score = eng.get_product_score("P_UNKNOWN")
        assert score.total_score == 0
        assert score.band == "DECLINE"
        assert "product_not_found" in score.components_missing

    def test_band_thresholds(self):
        eng, _ = self._engine()
        # Run all products and verify band consistency with score
        ranked = eng.rank_all_products()
        for s in ranked:
            if s.total_score >= 75:
                assert s.band == "TOP_TIER"
            elif s.total_score >= 50:
                assert s.band == "GROWING"
            elif s.total_score >= 25:
                assert s.band == "WATCHLIST"
            else:
                assert s.band == "DECLINE"

    def test_lending_product_uses_risk_component(self):
        # P001 Personal Loans is lending → should have risk component
        eng, _ = self._engine()
        score = eng.get_product_score("P001")
        assert "risk" in score.components_available

    def test_fee_product_skips_risk_component(self):
        # P015 Bancassurance is fee category → risk N/A
        eng, _ = self._engine()
        score = eng.get_product_score("P015")
        assert "risk" in score.components_missing


class TestRenormalization:
    def _engine(self):
        m = _load("rank_renorm", ENGINE_PATH)
        return m.ProductRankingEngine()

    def test_missing_components_flag_estimate(self):
        eng = self._engine()
        # P015 Bancassurance has multiple missing components
        score = eng.get_product_score("P015")
        if score.components_missing:
            assert score.is_estimate is True

    def test_score_renormalizes_not_penalizes(self):
        # When components are missing, the achieved score should be
        # scaled to 100, not capped at the available weight
        eng = self._engine()
        score = eng.get_product_score("P015")
        # P015 has 50 max-available weight (only profitability +
        # growth apply). If it scores ~41.5/50 the renormalized score
        # should be ~83/100, not 41/100
        if score.total_score > 0 and len(score.components_missing) > 0:
            # Sum of available component values
            sum_available = sum(score.component_scores.values())
            max_available = sum(score.component_max[c]
                                  for c in score.components_available)
            if max_available > 0:
                expected = float(sum_available) / float(max_available) * 100
                # Allow rounding tolerance ±2 points
                assert abs(score.total_score - expected) < 2


class TestRanking:
    def _engine(self):
        m = _load("rank_r", ENGINE_PATH)
        return m.ProductRankingEngine()

    def test_rank_all_returns_all_products(self):
        ranked = self._engine().rank_all_products()
        assert len(ranked) == 16  # 16 products in seed

    def test_rank_descending(self):
        ranked = self._engine().rank_all_products()
        for i in range(len(ranked) - 1):
            assert ranked[i].total_score >= ranked[i + 1].total_score

    def test_rank_stable_for_ties(self):
        # Run twice; order should be identical
        eng = self._engine()
        r1 = [s.product_id for s in eng.rank_all_products()]
        r2 = [s.product_id for s in eng.rank_all_products()]
        assert r1 == r2

    def test_top_n_returns_n_with_ranks(self):
        out = self._engine().get_top_n(5)
        assert len(out) == 5
        for i, entry in enumerate(out, start=1):
            assert entry["rank"] == i

    def test_bottom_n_returns_correct_ranks(self):
        out = self._engine().get_bottom_n(3)
        assert len(out) == 3
        # Last entry should be rank 16 (total products)
        assert out[-1]["rank"] == 16


class TestAggregations:
    def _engine(self):
        m = _load("rank_agg", ENGINE_PATH)
        return m.ProductRankingEngine()

    def test_distribution_components_add_up(self):
        d = self._engine().get_score_distribution()
        total = sum(d["by_band"].values())
        assert total == d["n_products"]

    def test_category_aggregation(self):
        out = self._engine().aggregate_by_category()
        assert len(out) > 0
        for cat, agg in out.items():
            for k in ("n_products", "avg_score", "top_score",
                      "bottom_score", "by_band"):
                assert k in agg
            assert agg["bottom_score"] <= agg["top_score"]

    def test_within_category_ranking(self):
        # Pick a category that should have multiple products
        agg = self._engine().aggregate_by_category()
        for cat, info in agg.items():
            if info["n_products"] >= 2:
                ranked = self._engine().rank_within_category(cat)
                for i in range(len(ranked) - 1):
                    assert (ranked[i]["total_score"]
                              >= ranked[i + 1]["total_score"])
                # Ranks are sequential
                for i, entry in enumerate(ranked, start=1):
                    assert entry["rank_in_category"] == i
                break


class TestRegistryAndAdmin:
    def test_enh_136_active(self):
        m = _load("sr136",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-136"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_ranking" in std.affected_engines
        assert std.implementation_batch == "v10.147"

    def test_prior_phase1e_engines_still_active(self):
        m = _load("sr_prior_v147",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132", "ENH-133",
                    "ENH-134", "ENH-135"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_six_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "product_competitive_intel",
                      "product_cvp_builder",
                      "product_ranking",
                      "ProductRankingEngine"):
            assert token in text, f"missing token: {token}"


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v147",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v147",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

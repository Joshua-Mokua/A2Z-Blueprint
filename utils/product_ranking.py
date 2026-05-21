"""utils.product_ranking — Product Ranking & Scoring Engine
(Standard ENH-136, v10.147). Phase 1E Product Module — sixth engine.

Per Continuation.docx §Standard #136 (Eco Bank QA spec):
    Multi-factor product scoring and ranking dashboard.

This is the SIXTH Phase 1E Product standard and the SECOND synthesizer
engine — combines ENH-131 P&L (profitability) + ENH-134 competitive
position + product growth/risk signals into a unified 0-100 score per
product with ranking, banding, and category-level rollups.

Per Rule 7 (No silent ML predictions):
  1. Score formula is fully deterministic — same input → same output
  2. All component weights are NAMED CONSTANTS; banks override
     via constructor arguments
  3. NO predicted scores — engine reports the snapshot computed from
     the underlying engines + data
  4. When a component cannot be computed (e.g. no competitor benchmark
     for a product), score renormalizes over AVAILABLE components and
     flags is_estimate=True with explicit missing_inputs

WHAT THIS MODULE SHIPS
----------------------
1. ProductRankingEngine class with:
   - get_product_score(product_id) — frozen ProductScore result
   - rank_all_products() — full portfolio ordered by score desc
   - get_top_n(n) / get_bottom_n(n)
   - get_score_distribution() — band counts (TOP_TIER/GROWING/
     WATCHLIST/DECLINE)
   - aggregate_by_category() — category-level rollup
   - rank_within_category(category) — products ranked within one
     category

2. Multi-factor score formula (0-100, all components weight-summed):
   - profitability:       30 pts  (from ENH-131 margin, scaled)
   - competitive_position: 25 pts  (LEADER=25 / FOLLOWER=12.5 / LAGGARD=0)
   - growth:              20 pts  (from growth_rate, scaled)
   - risk_adjusted:       15 pts  (from npl_rate, lower is better)
   - scale:               10 pts  (book size as franchise-value proxy)

3. Bands (config-overridable):
   - TOP_TIER:    score ≥ 75
   - GROWING:     50 ≤ score < 75
   - WATCHLIST:   25 ≤ score < 50
   - DECLINE:     score < 25

4. Reads (via companion engines + direct data):
   - data/products.json (16 products)
   - ENH-131 ProductPnLIntelligence (profitability)
   - ENH-134 ProductCompetitiveIntelligence (competitive position)

HONESTY DISCIPLINE
------------------
- Each component score is surfaced in the result so operators see
  HOW the total was built (component_scores dict)
- When a sub-score cannot be computed, the formula RENORMALIZES
  over available components rather than treating missing as zero
  — the result is_estimate=True with missing_inputs trail
- Score banding uses fixed thresholds; bands documented in result
- Category aggregation uses simple book-weighted averages (NAMED
  basis) — never hidden weighting
- Ranking is stable for ties (uses product_id as tiebreaker) so
  same input produces same rank order across runs
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Tuple

from utils.product_pnl_intelligence import ProductPnLIntelligence
from utils.product_competitive_intel import ProductCompetitiveIntelligence

DATA_DIR = Path(__file__).parent.parent / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"


@dataclass(frozen=True)
class ProductScore:
    product_id: str
    name: str
    category: str
    total_score: int                   # 0-100
    band: str                           # TOP_TIER | GROWING | WATCHLIST | DECLINE
    component_scores: Dict[str, Decimal]  # per-component contribution
    component_max: Dict[str, int]        # max possible per component
    components_available: Tuple[str, ...]
    components_missing: Tuple[str, ...]
    profitability_inputs: Dict[str, Any]
    competitive_inputs: Dict[str, Any]
    is_estimate: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "total_score": self.total_score,
            "band": self.band,
            "component_scores": {k: str(v)
                                   for k, v in self.component_scores.items()},
            "component_max": dict(self.component_max),
            "components_available": list(self.components_available),
            "components_missing": list(self.components_missing),
            "profitability_inputs": dict(self.profitability_inputs),
            "competitive_inputs": dict(self.competitive_inputs),
            "is_estimate": self.is_estimate,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductRankingEngine:
    """Multi-factor product scoring + ranking.

    Read-only contract — never writes.
    """

    # Component weights (sum = 100)
    WEIGHT_PROFITABILITY = 30
    WEIGHT_COMPETITIVE = 25
    WEIGHT_GROWTH = 20
    WEIGHT_RISK = 15
    WEIGHT_SCALE = 10

    # Banding
    TOP_TIER_THRESHOLD = 75
    GROWING_THRESHOLD = 50
    WATCHLIST_THRESHOLD = 25

    # Profitability scaling (margin %)
    MARGIN_FLOOR_PCT = Decimal("-30")  # ≤ -30% margin → 0 pts
    MARGIN_CEILING_PCT = Decimal("50")  # ≥ 50% margin → full pts

    # Growth scaling
    GROWTH_FLOOR_PCT = Decimal("-10")
    GROWTH_CEILING_PCT = Decimal("20")

    # Risk scaling (NPL rate; lending only — fee/deposits exempt)
    NPL_FLOOR_PCT = Decimal("0")     # 0% NPL → full risk score
    NPL_CEILING_PCT = Decimal("15")   # ≥ 15% NPL → 0 risk score

    # Scale scaling (book size in KES)
    SCALE_FLOOR_KES = Decimal("0")
    SCALE_CEILING_KES = Decimal("100000000000")  # 100B → full scale score

    def __init__(
        self,
        pnl_engine: Optional[ProductPnLIntelligence] = None,
        competitive_engine: Optional[ProductCompetitiveIntelligence]
                = None,
        products_path: Optional[Path] = None,
    ) -> None:
        self.pnl = pnl_engine or ProductPnLIntelligence()
        self.competitive = (competitive_engine
                              or ProductCompetitiveIntelligence())
        self.products_path = products_path or PRODUCTS_PATH

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def _load_products(self) -> List[Dict[str, Any]]:
        try:
            with open(self.products_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    # ------------------------------------------------------------------
    # Component scoring helpers
    # ------------------------------------------------------------------

    def _scale_to_range(
        self, value: Decimal, floor: Decimal, ceiling: Decimal,
    ) -> Decimal:
        """Linear scale value into [0, 1]. value≤floor → 0; value≥ceiling
        → 1; otherwise linear interpolation."""
        if value <= floor:
            return Decimal("0")
        if value >= ceiling:
            return Decimal("1")
        return ((value - floor) / (ceiling - floor)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _profitability_component(
        self, pnl_result,
    ) -> Tuple[Optional[Decimal], Dict[str, Any]]:
        if pnl_result.margin_pct is None:
            return None, {"margin_pct": None,
                            "reason": "no_margin_data"}
        scaled = self._scale_to_range(
            pnl_result.margin_pct,
            self.MARGIN_FLOOR_PCT, self.MARGIN_CEILING_PCT)
        score = scaled * Decimal(self.WEIGHT_PROFITABILITY)
        return score.quantize(Decimal("0.01")), {
            "margin_pct": str(pnl_result.margin_pct),
            "status": pnl_result.status,
            "scaled_factor": str(scaled),
        }

    def _competitive_component(
        self, comp_landscape,
    ) -> Tuple[Optional[Decimal], Dict[str, Any]]:
        if comp_landscape.status != "ok":
            return None, {"status": comp_landscape.status,
                            "reason": comp_landscape.reason}
        weight = Decimal(self.WEIGHT_COMPETITIVE)
        if comp_landscape.position == "LEADER":
            score = weight
        elif comp_landscape.position == "FOLLOWER":
            score = weight / Decimal("2")
        elif comp_landscape.position == "LAGGARD":
            score = Decimal("0")
        else:
            return None, {"position": comp_landscape.position,
                            "reason": "no_data_position"}
        return score.quantize(Decimal("0.01")), {
            "position": comp_landscape.position,
            "delta_vs_median_bps": comp_landscape.delta_vs_median_bps,
            "n_peers": comp_landscape.n_peers,
        }

    def _growth_component(
        self, product: Dict[str, Any],
    ) -> Tuple[Optional[Decimal], Dict[str, Any]]:
        gr = product.get("growth_rate")
        if gr is None:
            return None, {"growth_rate": None,
                            "reason": "no_growth_data"}
        try:
            gr_dec = Decimal(str(gr))
        except Exception:
            return None, {"growth_rate": str(gr),
                            "reason": "invalid_growth_value"}
        scaled = self._scale_to_range(
            gr_dec, self.GROWTH_FLOOR_PCT, self.GROWTH_CEILING_PCT)
        score = scaled * Decimal(self.WEIGHT_GROWTH)
        return score.quantize(Decimal("0.01")), {
            "growth_rate_pct": str(gr_dec),
            "scaled_factor": str(scaled),
        }

    def _risk_component(
        self, product: Dict[str, Any], pnl_result,
    ) -> Tuple[Optional[Decimal], Dict[str, Any]]:
        # Risk component only applies to lending; deposits/fee skip
        cost_model = pnl_result.cost_model
        if cost_model != "lending":
            return None, {"cost_model": cost_model,
                            "reason": "not_applicable_non_lending"}
        npl = product.get("npl_rate")
        if npl is None:
            return None, {"npl_rate": None,
                            "reason": "no_npl_data"}
        try:
            npl_dec = Decimal(str(npl))
        except Exception:
            return None, {"npl_rate": str(npl),
                            "reason": "invalid_npl_value"}
        # Lower NPL → higher score (invert)
        scaled = Decimal("1") - self._scale_to_range(
            npl_dec, self.NPL_FLOOR_PCT, self.NPL_CEILING_PCT)
        score = scaled * Decimal(self.WEIGHT_RISK)
        return score.quantize(Decimal("0.01")), {
            "npl_rate_pct": str(npl_dec),
            "scaled_factor": str(scaled),
        }

    def _scale_component(
        self, product: Dict[str, Any],
    ) -> Tuple[Optional[Decimal], Dict[str, Any]]:
        book = product.get("actual_book")
        if book is None or book == 0:
            return None, {"actual_book": book,
                            "reason": "no_book_data"}
        try:
            book_dec = Decimal(str(book))
        except Exception:
            return None, {"actual_book": str(book),
                            "reason": "invalid_book_value"}
        scaled = self._scale_to_range(
            book_dec, self.SCALE_FLOOR_KES, self.SCALE_CEILING_KES)
        score = scaled * Decimal(self.WEIGHT_SCALE)
        return score.quantize(Decimal("0.01")), {
            "actual_book_kes": str(book_dec),
            "scaled_factor": str(scaled),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_product_score(self, product_id: str) -> ProductScore:
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)
        if not product:
            return ProductScore(
                product_id=product_id, name="", category="",
                total_score=0, band="DECLINE",
                component_scores={}, component_max={},
                components_available=(),
                components_missing=("product_not_found",),
                profitability_inputs={}, competitive_inputs={},
                is_estimate=True)

        pnl_result = self.pnl.compute_product_pnl(product)
        comp_landscape = self.competitive.get_competitor_landscape(
            product_id)

        # Component scoring
        prof_score, prof_inputs = self._profitability_component(pnl_result)
        comp_score, comp_inputs = self._competitive_component(comp_landscape)
        growth_score, growth_inputs = self._growth_component(product)
        risk_score, risk_inputs = self._risk_component(product, pnl_result)
        scale_score, scale_inputs = self._scale_component(product)

        components_data: List[Tuple[str, int,
                                      Optional[Decimal]]] = [
            ("profitability", self.WEIGHT_PROFITABILITY, prof_score),
            ("competitive", self.WEIGHT_COMPETITIVE, comp_score),
            ("growth", self.WEIGHT_GROWTH, growth_score),
            ("risk", self.WEIGHT_RISK, risk_score),
            ("scale", self.WEIGHT_SCALE, scale_score),
        ]

        component_scores: Dict[str, Decimal] = {}
        component_max: Dict[str, int] = {}
        components_available: List[str] = []
        components_missing: List[str] = []
        max_total_available = Decimal("0")
        score_total_available = Decimal("0")

        for name, weight, score in components_data:
            component_max[name] = weight
            if score is not None:
                component_scores[name] = score
                components_available.append(name)
                max_total_available += Decimal(weight)
                score_total_available += score
            else:
                components_missing.append(name)

        # Renormalize over available components: scale the achieved sum
        # back to the 0-100 scale rather than treating missing as zero
        if max_total_available > 0:
            renormalised = (score_total_available / max_total_available
                              * Decimal("100"))
            total = int(renormalised.quantize(
                Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            total = 0

        # Banding
        if total >= self.TOP_TIER_THRESHOLD:
            band = "TOP_TIER"
        elif total >= self.GROWING_THRESHOLD:
            band = "GROWING"
        elif total >= self.WATCHLIST_THRESHOLD:
            band = "WATCHLIST"
        else:
            band = "DECLINE"

        is_estimate = len(components_missing) > 0

        return ProductScore(
            product_id=product_id,
            name=product.get("name", ""),
            category=product.get("category", ""),
            total_score=total,
            band=band,
            component_scores=component_scores,
            component_max=component_max,
            components_available=tuple(components_available),
            components_missing=tuple(components_missing),
            profitability_inputs=prof_inputs,
            competitive_inputs=comp_inputs,
            is_estimate=is_estimate)

    def rank_all_products(self) -> List[ProductScore]:
        scores = [self.get_product_score(p.get("id", ""))
                  for p in self._load_products()]
        # Stable sort: total_score desc, then product_id asc as tiebreak
        scores.sort(
            key=lambda s: (-s.total_score, s.product_id))
        return scores

    def get_top_n(self, n: int = 5) -> List[Dict[str, Any]]:
        ranked = self.rank_all_products()
        out: List[Dict[str, Any]] = []
        for i, s in enumerate(ranked[:n], start=1):
            out.append({"rank": i, **s.as_dict()})
        return out

    def get_bottom_n(self, n: int = 5) -> List[Dict[str, Any]]:
        ranked = self.rank_all_products()
        # Bottom = last N; rank from the bottom
        bottom = ranked[-n:]
        total = len(ranked)
        out: List[Dict[str, Any]] = []
        for i, s in enumerate(bottom):
            out.append({"rank": total - n + i + 1, **s.as_dict()})
        return out

    def get_score_distribution(self) -> Dict[str, Any]:
        ranked = self.rank_all_products()
        dist = {"TOP_TIER": 0, "GROWING": 0,
                "WATCHLIST": 0, "DECLINE": 0}
        for s in ranked:
            dist[s.band] = dist.get(s.band, 0) + 1
        avg = (sum(s.total_score for s in ranked) / len(ranked)
                if ranked else 0)
        return {
            "n_products": len(ranked),
            "by_band": dist,
            "avg_score": round(avg, 2),
            "top_score": ranked[0].total_score if ranked else None,
            "bottom_score": ranked[-1].total_score if ranked else None,
        }

    def aggregate_by_category(self) -> Dict[str, Dict[str, Any]]:
        ranked = self.rank_all_products()
        by_cat: Dict[str, List[ProductScore]] = {}
        for s in ranked:
            by_cat.setdefault(s.category, []).append(s)
        out: Dict[str, Dict[str, Any]] = {}
        for cat, scores in by_cat.items():
            avg = sum(s.total_score for s in scores) / len(scores)
            top = max(s.total_score for s in scores)
            bottom = min(s.total_score for s in scores)
            out[cat] = {
                "n_products": len(scores),
                "avg_score": round(avg, 2),
                "top_score": top,
                "bottom_score": bottom,
                "by_band": {
                    "TOP_TIER": sum(1 for s in scores
                                      if s.band == "TOP_TIER"),
                    "GROWING": sum(1 for s in scores
                                     if s.band == "GROWING"),
                    "WATCHLIST": sum(1 for s in scores
                                       if s.band == "WATCHLIST"),
                    "DECLINE": sum(1 for s in scores
                                     if s.band == "DECLINE"),
                },
            }
        return out

    def rank_within_category(
        self, category: str,
    ) -> List[Dict[str, Any]]:
        all_ranked = self.rank_all_products()
        in_cat = [s for s in all_ranked if s.category == category]
        out: List[Dict[str, Any]] = []
        for i, s in enumerate(in_cat, start=1):
            out.append({"rank_in_category": i, **s.as_dict()})
        return out


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductRankingEngine()

    dist = eng.get_score_distribution()
    print(f"Distribution: TOP_TIER={dist['by_band']['TOP_TIER']} "
          f"GROWING={dist['by_band']['GROWING']} "
          f"WATCHLIST={dist['by_band']['WATCHLIST']} "
          f"DECLINE={dist['by_band']['DECLINE']} "
          f"of {dist['n_products']}")
    print(f"  avg_score={dist['avg_score']} "
          f"range=[{dist['bottom_score']}, {dist['top_score']}]")
    print()

    print("Top 5:")
    for entry in eng.get_top_n(5):
        print(f"  #{entry['rank']} {entry['product_id']} "
              f"{entry['name']}: {entry['total_score']} "
              f"({entry['band']}) "
              f"missing={list(entry['components_missing'])}")
    print()

    print("Bottom 5:")
    for entry in eng.get_bottom_n(5):
        print(f"  #{entry['rank']} {entry['product_id']} "
              f"{entry['name']}: {entry['total_score']} "
              f"({entry['band']})")
    print()

    print("By category:")
    by_cat = eng.aggregate_by_category()
    for cat, agg in by_cat.items():
        print(f"  {cat}: n={agg['n_products']} "
              f"avg={agg['avg_score']} "
              f"range=[{agg['bottom_score']}, {agg['top_score']}]")
    print()

    # Sample component breakdown
    score = eng.get_product_score("P001")
    print(f"P001 {score.name}: total={score.total_score} ({score.band})")
    print(f"  components_available: {list(score.components_available)}")
    print(f"  components_missing: {list(score.components_missing)}")
    for name, value in score.component_scores.items():
        max_v = score.component_max.get(name, 0)
        print(f"    {name}: {value}/{max_v}")


if __name__ == "__main__":
    _self_test()

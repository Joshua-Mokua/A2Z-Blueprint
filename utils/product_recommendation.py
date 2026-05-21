"""utils.product_recommendation — AI Product Recommendation Engine
(Standard ENH-138, v10.149). Phase 1E Product Module — eighth engine.

Per Continuation.docx §Standard #138 (Eco Bank QA spec):
    AI-powered next-best-product recommendations per customer.

This is the EIGHTH Phase 1E Product standard and the FOURTH synthesizer
engine — combines ENH-133 customer needs + customer propensity_scores
(from data/customer_intelligence.json) + ENH-131 product P&L margins +
ENH-136 product rankings into per-customer next-best-product
recommendations.

Per Rule 7 (No silent ML predictions):
  1. Default rule-based recommendation — deterministic, transparent
     scoring formula combining propensity + product margin + product
     rank
  2. AI hook (`ai_recommendation_fn`) is opt-in and injectable;
     when not supplied, engine returns rule-based result with
     basis="rule_based" tag
  3. When AI is supplied, output tagged basis="llm" so consumers
     know recommendations were LLM-augmented; structural data
     (candidate set, scores, segments) remains rule-based
  4. AI hook failure → graceful fallback to rule-based with warning

WHAT THIS MODULE SHIPS
----------------------
1. ProductRecommendationEngine class with:
   - recommend_for_customer(customer_id, n=3) — top-N recommendations
     for one customer with frozen Recommendation result
   - recommend_for_segment(segment, n=3) — segment-level top
     recommendations (aggregate propensities × product fit)
   - bulk_recommend(customer_ids, n=3) — batch processing
   - get_recommendation_summary() — bank-wide propensity coverage

2. Frozen Recommendation dataclass:
   - customer_id + segment
   - recommendations[] — list of recommended products with score +
     rationale
   - basis: "rule_based" | "llm"
   - is_estimate flag
   - missing_inputs trail
   - ai_warning when AI hook used or failed

3. Rule-based scoring formula (per candidate product):
   score = 0.5 × propensity_score
        + 0.3 × product_rank_factor (ENH-136 ranking, scaled)
        + 0.2 × product_margin_factor (ENH-131 margin, scaled)
   Note: customer is NOT recommended a product they've explicitly
   shown low propensity for (propensity_score < 0.05 → excluded)

4. Reads:
   - data/customer_intelligence.json (3000 customers with
     propensity_scores dict + segment + churn_risk + clv_estimate)
   - data/products.json (16 products)
   - ENH-136 ProductRankingEngine (via injection)
   - ENH-131 ProductPnLIntelligence (via injection)
   - ENH-133 CustomerNeedsAnalyzer (via injection, for context)

HONESTY DISCIPLINE
------------------
- Engine NEVER writes — recommendations are advisory; operators
  decide whether to act
- Honest fallback when customer not in intelligence
- AI hook opt-in with basis tag + ai_warning; AI failure does NOT
  crash the engine
- Score formula documented + deterministic; no opaque ML
- Excluded products (low propensity) surfaced in result so operators
  see what was filtered out
- For segment-level recommendations: aggregate propensities are
  averaged across the segment; engine surfaces n_customers used
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.product_ranking import ProductRankingEngine
from utils.product_pnl_intelligence import ProductPnLIntelligence
from utils.customer_needs_analyzer import CustomerNeedsAnalyzer

DATA_DIR = Path(__file__).parent.parent / "data"
CUSTOMER_INTEL_PATH = DATA_DIR / "customer_intelligence.json"
PRODUCTS_PATH = DATA_DIR / "products.json"


@dataclass(frozen=True)
class Recommendation:
    customer_id: str
    segment: Optional[str]
    recommendations: Tuple[Dict[str, Any], ...]
    excluded: Tuple[Dict[str, Any], ...]
    basis: str                              # "rule_based" | "llm"
    is_estimate: bool
    missing_inputs: Tuple[str, ...] = field(default_factory=tuple)
    ai_warning: Optional[str] = None
    n_candidates_evaluated: int = 0
    fallback_reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "segment": self.segment,
            "recommendations": list(self.recommendations),
            "excluded": list(self.excluded),
            "basis": self.basis,
            "is_estimate": self.is_estimate,
            "missing_inputs": list(self.missing_inputs),
            "ai_warning": self.ai_warning,
            "n_candidates_evaluated": self.n_candidates_evaluated,
            "fallback_reason": self.fallback_reason,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductRecommendationEngine:
    """Per-customer next-best-product recommendations.

    Read-only contract — never writes.
    """

    # Scoring weights (sum = 1.0)
    WEIGHT_PROPENSITY = Decimal("0.50")
    WEIGHT_RANK = Decimal("0.30")
    WEIGHT_MARGIN = Decimal("0.20")

    # Filtering
    MIN_PROPENSITY_FOR_INCLUSION = Decimal("0.05")
    DEFAULT_TOP_N = 3

    # Margin scaling for the margin component
    MARGIN_FLOOR_PCT = Decimal("-30")
    MARGIN_CEILING_PCT = Decimal("50")

    def __init__(
        self,
        ranking_engine: Optional[ProductRankingEngine] = None,
        pnl_engine: Optional[ProductPnLIntelligence] = None,
        needs_engine: Optional[CustomerNeedsAnalyzer] = None,
        ai_recommendation_fn: Optional[
            Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None,
        customer_intel_path: Optional[Path] = None,
        products_path: Optional[Path] = None,
    ) -> None:
        self.ranking = ranking_engine or ProductRankingEngine()
        self.pnl = pnl_engine or ProductPnLIntelligence()
        self.needs = needs_engine or CustomerNeedsAnalyzer()
        self.ai_recommendation_fn = ai_recommendation_fn
        self.customer_intel_path = (customer_intel_path
                                      or CUSTOMER_INTEL_PATH)
        self.products_path = products_path or PRODUCTS_PATH
        self._intel_cache: Optional[Dict[str, Any]] = None
        self._products_cache: Optional[List[Dict[str, Any]]] = None
        self._product_score_cache: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def _load_intel(self) -> Dict[str, Any]:
        if self._intel_cache is None:
            try:
                with open(self.customer_intel_path) as f:
                    self._intel_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._intel_cache = {}
        return self._intel_cache or {}

    def _load_products(self) -> List[Dict[str, Any]]:
        if self._products_cache is None:
            try:
                with open(self.products_path) as f:
                    self._products_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                self._products_cache = []
        return self._products_cache

    # ------------------------------------------------------------------
    # Helpers — match propensity-name to product
    # ------------------------------------------------------------------

    # Propensity_scores keys are product-class names like "Personal Loan",
    # "Mortgage", "Asset Finance". Map to actual product IDs.
    # Note: "Investment Fund" has no exact match in the current 16-product
    # portfolio — engine surfaces this as no_product_resolution. Operators
    # can extend the portfolio or this mapping over time.
    PROPENSITY_TO_PRODUCT_ID: Dict[str, str] = {
        "Personal Loan": "P001",
        "Mortgage": "P002",
        "Asset Finance": "P003",
        "Business Loan": "P005",
        "Fixed Deposit": "P014",
        "Insurance": "P015",
        # "Investment Fund" intentionally absent — no matching product
    }

    def _resolve_propensity_to_product(
        self, propensity_name: str,
    ) -> Optional[Dict[str, Any]]:
        product_id = self.PROPENSITY_TO_PRODUCT_ID.get(propensity_name)
        if not product_id:
            return None
        for p in self._load_products():
            if p.get("id") == product_id:
                return p
        return None

    def _scale_to_unit(
        self, value: Decimal, floor: Decimal, ceiling: Decimal,
    ) -> Decimal:
        if value <= floor:
            return Decimal("0")
        if value >= ceiling:
            return Decimal("1")
        return ((value - floor) / (ceiling - floor)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _get_product_score_cached(self, product_id: str):
        if product_id not in self._product_score_cache:
            self._product_score_cache[product_id] = (
                self.ranking.get_product_score(product_id))
        return self._product_score_cache[product_id]

    # ------------------------------------------------------------------
    # Per-customer recommendation
    # ------------------------------------------------------------------

    def recommend_for_customer(
        self, customer_id: str, n: Optional[int] = None,
    ) -> Recommendation:
        n = n or self.DEFAULT_TOP_N
        intel = self._load_intel().get(str(customer_id))
        if not intel:
            return Recommendation(
                customer_id=customer_id, segment=None,
                recommendations=(), excluded=(),
                basis="rule_based",
                is_estimate=True,
                missing_inputs=("customer_not_found",),
                fallback_reason="customer_not_found")

        segment = intel.get("segment")
        propensity_scores = intel.get("propensity_scores") or {}

        # Build candidate list: each propensity → resolve to product →
        # compute composite score
        candidates: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []

        for prop_name, prop_score_raw in propensity_scores.items():
            try:
                prop_score = Decimal(str(prop_score_raw))
            except Exception:
                continue

            # Filter low-propensity entries
            if prop_score < self.MIN_PROPENSITY_FOR_INCLUSION:
                excluded.append({
                    "propensity_name": prop_name,
                    "propensity_score": str(prop_score),
                    "reason": "below_min_propensity_threshold",
                })
                continue

            product = self._resolve_propensity_to_product(prop_name)
            if not product:
                excluded.append({
                    "propensity_name": prop_name,
                    "propensity_score": str(prop_score),
                    "reason": "no_product_resolution_in_portfolio",
                })
                continue

            product_id = product.get("id", "")

            # Get product rank score (0-100 → scale to 0-1)
            product_score = self._get_product_score_cached(product_id)
            rank_factor = (Decimal(product_score.total_score)
                            / Decimal("100"))

            # Get product margin
            try:
                pnl = self.pnl.compute_product_pnl(product)
                if pnl.margin_pct is not None:
                    margin_factor = self._scale_to_unit(
                        pnl.margin_pct,
                        self.MARGIN_FLOOR_PCT,
                        self.MARGIN_CEILING_PCT)
                else:
                    margin_factor = Decimal("0.5")  # neutral fallback
            except Exception:
                margin_factor = Decimal("0.5")

            # Composite score
            composite = (
                self.WEIGHT_PROPENSITY * prop_score
                + self.WEIGHT_RANK * rank_factor
                + self.WEIGHT_MARGIN * margin_factor)
            composite = composite.quantize(Decimal("0.0001"))

            candidates.append({
                "propensity_name": prop_name,
                "product_id": product_id,
                "product_name": product.get("name", ""),
                "category": product.get("category", ""),
                "composite_score": str(composite),
                "propensity_score": str(prop_score),
                "rank_factor": str(rank_factor),
                "margin_factor": str(margin_factor),
                "rationale": (
                    f"propensity={prop_score} × {self.WEIGHT_PROPENSITY} "
                    f"+ rank={rank_factor} × {self.WEIGHT_RANK} "
                    f"+ margin={margin_factor} × {self.WEIGHT_MARGIN}"),
            })

        # Sort by composite score descending; product_id tiebreaker
        candidates.sort(key=lambda c: (-float(c["composite_score"]),
                                        c["product_id"]))
        top_n = candidates[:n]

        # Apply rank position
        for i, entry in enumerate(top_n, start=1):
            entry["rank"] = i

        n_candidates = len(candidates)
        is_estimate = n_candidates < n
        missing: List[str] = []
        if n_candidates < n:
            missing.append(
                f"only_{n_candidates}_candidates_meet_min_propensity")

        # Apply AI hook if injected
        basis = "rule_based"
        ai_warning: Optional[str] = None

        if self.ai_recommendation_fn is not None:
            try:
                ai_input = {
                    "customer_id": customer_id,
                    "segment": segment,
                    "propensity_scores": propensity_scores,
                    "rule_based_top_n": top_n,
                    "rule_based_excluded": excluded,
                }
                ai_result = self.ai_recommendation_fn(ai_input)
                if isinstance(ai_result, list) and ai_result:
                    # AI may re-rank or replace — accept the list as-is
                    # but tag basis='llm' and warn
                    top_n = ai_result[:n]
                    basis = "llm"
                    ai_warning = (
                        "Recommendations LLM-generated. Candidate set, "
                        "propensity scores, and product rankings remain "
                        "rule-based.")
            except Exception as e:
                ai_warning = (
                    f"AI hook failed ({type(e).__name__}); "
                    "falling back to rule-based recommendations.")

        return Recommendation(
            customer_id=customer_id,
            segment=segment,
            recommendations=tuple(top_n),
            excluded=tuple(excluded),
            basis=basis,
            is_estimate=is_estimate,
            missing_inputs=tuple(missing),
            ai_warning=ai_warning,
            n_candidates_evaluated=n_candidates)

    # ------------------------------------------------------------------
    # Segment-level recommendations
    # ------------------------------------------------------------------

    def recommend_for_segment(
        self, segment: str, n: Optional[int] = None,
    ) -> Dict[str, Any]:
        n = n or self.DEFAULT_TOP_N
        intel = self._load_intel()
        in_segment = [c for c in intel.values()
                       if c.get("segment") == segment]
        if not in_segment:
            return {"ok": False,
                    "segment": segment,
                    "fallback_reason": "no_customers_in_segment"}

        # Aggregate propensities across the segment
        agg_propensities: Dict[str, List[Decimal]] = {}
        for c in in_segment:
            for prop, score in (c.get("propensity_scores") or {}).items():
                try:
                    s = Decimal(str(score))
                except Exception:
                    continue
                agg_propensities.setdefault(prop, []).append(s)

        # Average propensity per product
        avg_propensities: Dict[str, Decimal] = {}
        for prop, scores in agg_propensities.items():
            if not scores:
                continue
            avg = (sum(scores, Decimal("0"))
                    / Decimal(len(scores))).quantize(
                        Decimal("0.0001"))
            avg_propensities[prop] = avg

        # Build candidate list using segment-average propensity in
        # place of per-customer propensity
        candidates: List[Dict[str, Any]] = []
        for prop_name, avg_score in avg_propensities.items():
            if avg_score < self.MIN_PROPENSITY_FOR_INCLUSION:
                continue
            product = self._resolve_propensity_to_product(prop_name)
            if not product:
                continue
            product_id = product.get("id", "")
            product_score = self._get_product_score_cached(product_id)
            rank_factor = (Decimal(product_score.total_score)
                            / Decimal("100"))
            try:
                pnl = self.pnl.compute_product_pnl(product)
                if pnl.margin_pct is not None:
                    margin_factor = self._scale_to_unit(
                        pnl.margin_pct,
                        self.MARGIN_FLOOR_PCT,
                        self.MARGIN_CEILING_PCT)
                else:
                    margin_factor = Decimal("0.5")
            except Exception:
                margin_factor = Decimal("0.5")
            composite = (
                self.WEIGHT_PROPENSITY * avg_score
                + self.WEIGHT_RANK * rank_factor
                + self.WEIGHT_MARGIN * margin_factor).quantize(
                    Decimal("0.0001"))
            candidates.append({
                "propensity_name": prop_name,
                "product_id": product_id,
                "product_name": product.get("name", ""),
                "category": product.get("category", ""),
                "avg_segment_propensity": str(avg_score),
                "composite_score": str(composite),
                "rank_factor": str(rank_factor),
                "margin_factor": str(margin_factor),
            })
        candidates.sort(key=lambda c: (-float(c["composite_score"]),
                                        c["product_id"]))
        top_n = candidates[:n]
        for i, entry in enumerate(top_n, start=1):
            entry["rank"] = i
        return {
            "ok": True,
            "segment": segment,
            "n_customers": len(in_segment),
            "recommendations": top_n,
            "n_candidates_evaluated": len(candidates),
        }

    # ------------------------------------------------------------------
    # Bulk + summary
    # ------------------------------------------------------------------

    def bulk_recommend(
        self, customer_ids: List[str], n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return [self.recommend_for_customer(cid, n).as_dict()
                for cid in customer_ids]

    def get_recommendation_summary(self) -> Dict[str, Any]:
        intel = self._load_intel()
        if not intel:
            return {"ok": False,
                    "fallback_reason": "no_customer_intelligence"}
        # Sample-based summary: count product appearances across all
        # customers' top-3 rule-based recommendations
        product_appearances: Dict[str, int] = {}
        n_evaluated = 0
        for cid in intel.keys():
            rec = self.recommend_for_customer(cid, 3)
            n_evaluated += 1
            for entry in rec.recommendations:
                pid = entry.get("product_id")
                if pid:
                    product_appearances[pid] = (
                        product_appearances.get(pid, 0) + 1)
        ranked_products = sorted(
            product_appearances.items(), key=lambda x: -x[1])
        return {
            "ok": True,
            "n_customers_evaluated": n_evaluated,
            "top_recommended_products": [
                {"product_id": pid, "n_appearances": n,
                 "appearance_rate_pct": round(
                     100.0 * n / n_evaluated, 2) if n_evaluated else 0}
                for pid, n in ranked_products[:10]
            ],
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductRecommendationEngine()
    intel = eng._load_intel()
    sample_id = next(iter(intel.keys()))
    print(f"Sample customer: {sample_id}")
    rec = eng.recommend_for_customer(sample_id, 3)
    print(f"  segment={rec.segment} basis={rec.basis} "
          f"n_evaluated={rec.n_candidates_evaluated}")
    print(f"  Top recommendations:")
    for entry in rec.recommendations:
        print(f"    #{entry['rank']} {entry['product_id']} "
              f"{entry['product_name']}: "
              f"score={entry['composite_score']} "
              f"(prop={entry['propensity_score']})")
    print(f"  Excluded: {len(rec.excluded)}")
    print()

    # Segment-level
    for seg in ("Mass", "Premium"):
        seg_rec = eng.recommend_for_segment(seg, 3)
        if seg_rec.get("ok"):
            print(f"{seg} segment (n={seg_rec['n_customers']}):")
            for r in seg_rec["recommendations"]:
                print(f"  #{r['rank']} {r['product_id']} "
                      f"{r['product_name']}: "
                      f"avg_prop={r['avg_segment_propensity']} "
                      f"score={r['composite_score']}")
            print()

    # Bank-wide summary
    summary = eng.get_recommendation_summary()
    print(f"Bank-wide summary: n_customers={summary['n_customers_evaluated']}")
    print("Top recommended products by frequency:")
    for entry in summary.get("top_recommended_products", [])[:5]:
        print(f"  {entry['product_id']}: {entry['n_appearances']} "
              f"appearances ({entry['appearance_rate_pct']}%)")
    print()

    # AI hook smoke test
    def fake_ai(input_dict):
        return [{"product_id": "P_AI", "rank": 1,
                 "rationale": "AI-mocked"}]
    eng_ai = ProductRecommendationEngine(ai_recommendation_fn=fake_ai)
    rec_ai = eng_ai.recommend_for_customer(sample_id, 3)
    print(f"With AI hook: basis={rec_ai.basis}")
    print(f"  ai_warning: {rec_ai.ai_warning}")


if __name__ == "__main__":
    _self_test()

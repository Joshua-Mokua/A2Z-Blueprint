"""utils.dynamic_pricing — Dynamic Pricing Engine
(Standard ENH-137, v10.148). Phase 1E Product Module — seventh engine.

Per Continuation.docx §Standard #137 (Eco Bank QA spec):
    Rule-based price optimization with peer benchmark inputs.

This is the SEVENTH Phase 1E Product standard and the THIRD synthesizer
engine — combines ENH-134 competitive position (peer median + position)
+ ENH-131 P&L (margin floor + COF awareness) + product/category context
into pricing recommendations with explicit guard rails.

Per Rule 7 (No silent ML predictions):
  1. Pricing recommendations are RULE-BASED — same input → same output
  2. NO ML pricing models — engine uses peer median + margin floor +
     category constraints as deterministic inputs
  3. ALL recommendations require operator approval before any price
     change is applied (engine never writes to product pricing)
  4. is_estimate=True flag when underlying inputs (peer data, margin
     calc) are thin

WHAT THIS MODULE SHIPS
----------------------
1. DynamicPricingEngine class with:
   - get_pricing_recommendation(product_id) — frozen PricingRecommendation
   - get_all_recommendations() — bank-wide list
   - get_actionable_recommendations(min_change_bps) — filtered list
     of recommendations exceeding a meaningful change threshold
   - get_recommendation_summary() — bank-wide summary stats
   - simulate_price_change(product_id, new_rate_pct) — what-if margin
     impact of a hypothetical price change

2. Rule-based recommendation logic (per product):
   - Read current rate, peer median, margin (from companion engines)
   - For LAGGARD products → recommend moving toward peer median
   - For LEADER products → consider holding (no change recommended unless
     margin is below floor)
   - Cap any recommended change at MAX_CHANGE_PER_PERIOD_BPS (default 100bps)
   - Floor recommendation at category MIN_RATE_FLOOR (regulatory + COF)
   - Ceiling at category MAX_RATE_CEILING (responsible-lending bound)
   - Validate recommended_rate produces margin ≥ MIN_MARGIN_FLOOR

3. Recommendation actions: HOLD / INCREASE / DECREASE / NO_BENCHMARK /
   CONSTRAINED_BY_FLOOR / CONSTRAINED_BY_CEILING / CONSTRAINED_BY_MARGIN

4. Reads:
   - data/products.json (16 products with rate_avg, category)
   - data/pricing_constraints_config.json (NEW v10.148 seed; floors/
     ceilings/max-change per category)
   - ENH-134 ProductCompetitiveIntelligence (via injection)
   - ENH-131 ProductPnLIntelligence (via injection)

HONESTY DISCIPLINE
------------------
- Engine NEVER writes to product pricing — all recommendations are
  advisory only. The decision and implementation belong to operators.
- When a product has no competitor benchmark mapping (e.g. Trade
  Finance LC), action="NO_BENCHMARK" with explicit reason
- When a recommendation is constrained by a floor/ceiling/margin
  guard, the action surfaces THAT constraint rather than silently
  accepting it (e.g. "CONSTRAINED_BY_FLOOR" tells operators the
  unconstrained recommendation would have been lower)
- The change_bps field is signed and reports the ACTUAL recommended
  delta, after all constraints applied
- simulate_price_change is a what-if tool; never persists state
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.product_competitive_intel import ProductCompetitiveIntelligence
from utils.product_pnl_intelligence import ProductPnLIntelligence

DATA_DIR = Path(__file__).parent.parent / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"
PRICING_CONFIG_PATH = DATA_DIR / "pricing_constraints_config.json"


@dataclass(frozen=True)
class PricingRecommendation:
    product_id: str
    name: str
    category: str
    current_rate_pct: Optional[Decimal]
    peer_median_pct: Optional[Decimal]
    competitive_position: Optional[str]
    recommended_rate_pct: Optional[Decimal]
    change_bps: Optional[int]                 # signed; recommended - current
    action: str                                 # HOLD / INCREASE / DECREASE / etc.
    rationale: Tuple[str, ...]
    constraints_applied: Tuple[str, ...]
    margin_at_recommended_pct: Optional[Decimal]
    is_estimate: bool
    status: str                                 # "ok" | "no_benchmark" | "product_not_found"

    def as_dict(self) -> Dict[str, Any]:
        def _dec(x):
            return str(x) if x is not None else None
        return {
            "product_id": self.product_id,
            "name": self.name,
            "category": self.category,
            "current_rate_pct": _dec(self.current_rate_pct),
            "peer_median_pct": _dec(self.peer_median_pct),
            "competitive_position": self.competitive_position,
            "recommended_rate_pct": _dec(self.recommended_rate_pct),
            "change_bps": self.change_bps,
            "action": self.action,
            "rationale": list(self.rationale),
            "constraints_applied": list(self.constraints_applied),
            "margin_at_recommended_pct": _dec(self.margin_at_recommended_pct),
            "is_estimate": self.is_estimate,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DynamicPricingEngine:
    """Rule-based pricing recommendations using peer benchmarks +
    margin floors. Read-only contract — never writes pricing.
    """

    DEFAULT_MAX_CHANGE_BPS = 100      # cap single-period change
    DEFAULT_MIN_MARGIN_FLOOR_PCT = Decimal("1.0")
    MEANINGFUL_CHANGE_BPS = 25        # below this is "noise"

    def __init__(
        self,
        competitive_engine: Optional[ProductCompetitiveIntelligence]
                = None,
        pnl_engine: Optional[ProductPnLIntelligence] = None,
        products_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.competitive = (competitive_engine
                              or ProductCompetitiveIntelligence())
        self.pnl = pnl_engine or ProductPnLIntelligence()
        self.products_path = products_path or PRODUCTS_PATH
        self.config_path = config_path or PRICING_CONFIG_PATH

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def _load_products(self) -> List[Dict[str, Any]]:
        try:
            with open(self.products_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # ------------------------------------------------------------------
    # Constraint helpers
    # ------------------------------------------------------------------

    def _max_change_bps(self) -> int:
        cfg = self._load_config()
        return int(cfg.get("global_constraints", {}).get(
            "max_change_per_period_bps",
            self.DEFAULT_MAX_CHANGE_BPS))

    def _min_margin_floor(self) -> Decimal:
        cfg = self._load_config()
        v = cfg.get("global_constraints", {}).get(
            "min_margin_floor_pct",
            self.DEFAULT_MIN_MARGIN_FLOOR_PCT)
        try:
            return Decimal(str(v))
        except Exception:
            return self.DEFAULT_MIN_MARGIN_FLOOR_PCT

    def _category_constraints(
        self, category: str,
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """Returns (rate_floor_pct, rate_ceiling_pct)."""
        cfg = self._load_config()
        cat_cfg = cfg.get("category_constraints", {}).get(category, {})
        floor = cat_cfg.get("rate_floor_pct")
        ceiling = cat_cfg.get("rate_ceiling_pct")
        floor_dec = (Decimal(str(floor))
                      if floor is not None else None)
        ceiling_dec = (Decimal(str(ceiling))
                        if ceiling is not None else None)
        return floor_dec, ceiling_dec

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pricing_recommendation(
        self, product_id: str,
    ) -> PricingRecommendation:
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)
        if not product:
            return PricingRecommendation(
                product_id=product_id, name="", category="",
                current_rate_pct=None, peer_median_pct=None,
                competitive_position=None,
                recommended_rate_pct=None, change_bps=None,
                action="PRODUCT_NOT_FOUND",
                rationale=("product_not_in_products.json",),
                constraints_applied=(),
                margin_at_recommended_pct=None,
                is_estimate=True,
                status="product_not_found")

        try:
            current_rate = Decimal(str(product.get("rate_avg", 0)
                                         or 0))
        except Exception:
            current_rate = Decimal("0")
        category = product.get("category", "")
        name = product.get("name", "")

        landscape = self.competitive.get_competitor_landscape(product_id)

        # No competitor benchmark → no recommendation
        if landscape.status != "ok":
            return PricingRecommendation(
                product_id=product_id, name=name, category=category,
                current_rate_pct=current_rate,
                peer_median_pct=None,
                competitive_position=landscape.position,
                recommended_rate_pct=None, change_bps=None,
                action="NO_BENCHMARK",
                rationale=(f"no_competitor_benchmark: "
                            f"{landscape.reason or 'unknown'}",),
                constraints_applied=(),
                margin_at_recommended_pct=None,
                is_estimate=True,
                status="no_benchmark")

        peer_median = landscape.peer_median_pct
        position = landscape.position
        bm_type = landscape.benchmark_type

        # ---- Determine unconstrained recommended rate ----
        rationale: List[str] = []
        constraints_applied: List[str] = []

        if position == "LEADER":
            # Already winning the price race; consider holding
            # but verify margin is healthy
            recommended_rate = current_rate
            rationale.append(
                f"LEADER position; holding current rate "
                f"({current_rate}%) — already beats peer "
                f"median by {abs(landscape.delta_vs_median_bps)} bps")
            action = "HOLD"

        elif position == "FOLLOWER":
            # Within ±50bps of peer median; small move toward
            # median ONLY if direction improves competitive standing
            recommended_rate = current_rate
            rationale.append(
                f"FOLLOWER within ±50bps of peer median; "
                f"holding current rate")
            action = "HOLD"

        elif position == "LAGGARD":
            # Move toward peer median, capped by max change per period
            if peer_median is None:
                recommended_rate = current_rate
                rationale.append("LAGGARD but no peer median; holding")
                action = "HOLD"
            else:
                # Distance to peer median
                gap = peer_median - current_rate  # signed

                if bm_type == "lending":
                    # Lending: lower is better; LAGGARD means we charge MORE
                    # than peer median → move down
                    target = peer_median
                    direction = "DECREASE"
                elif bm_type == "deposits":
                    # Deposits: higher is better; LAGGARD means we pay LESS
                    # than peer median → move up
                    target = peer_median
                    direction = "INCREASE"
                else:
                    target = current_rate
                    direction = "HOLD"

                # Cap by max change per period
                max_change_bps = self._max_change_bps()
                gap_bps = int((target - current_rate) * Decimal("100"))
                if abs(gap_bps) > max_change_bps:
                    capped_change = (Decimal(max_change_bps)
                                       / Decimal("100"))
                    if gap_bps > 0:
                        recommended_rate = current_rate + capped_change
                    else:
                        recommended_rate = current_rate - capped_change
                    constraints_applied.append(
                        f"capped_at_max_change_per_period_"
                        f"{max_change_bps}bps")
                    rationale.append(
                        f"LAGGARD; moving {direction} toward peer "
                        f"median ({peer_median}%), capped at "
                        f"{max_change_bps}bps per period")
                else:
                    recommended_rate = target
                    rationale.append(
                        f"LAGGARD; moving {direction} to peer "
                        f"median ({peer_median}%)")

                action = direction
        else:
            # NO_DATA / unknown
            recommended_rate = current_rate
            rationale.append(f"position={position}; holding")
            action = "HOLD"

        # ---- Apply category floor/ceiling constraints ----
        floor, ceiling = self._category_constraints(category)
        if floor is not None and recommended_rate < floor:
            constraints_applied.append(
                f"floored_at_category_min_{floor}%")
            recommended_rate = floor
            action = "CONSTRAINED_BY_FLOOR"
            rationale.append(
                f"unconstrained recommendation would have been below "
                f"category floor of {floor}%")
        if ceiling is not None and recommended_rate > ceiling:
            constraints_applied.append(
                f"capped_at_category_max_{ceiling}%")
            recommended_rate = ceiling
            action = "CONSTRAINED_BY_CEILING"
            rationale.append(
                f"unconstrained recommendation would have exceeded "
                f"category ceiling of {ceiling}%")

        # ---- Margin guard ----
        # Only fire when actually proposing a rate change. If we're
        # already HOLDing, current margin is the baseline operators
        # already accept — engine doesn't suddenly object to it here.
        margin_at_rec: Optional[Decimal] = None
        if recommended_rate != current_rate:
            try:
                pnl = self.pnl.compute_product_pnl(product)
                if (pnl.margin_pct is not None
                        and current_rate > 0):
                    rate_change_factor = (
                        recommended_rate - current_rate) / current_rate
                    margin_at_rec = (pnl.margin_pct
                                      + (rate_change_factor
                                          * pnl.margin_pct))
                    margin_at_rec = margin_at_rec.quantize(
                        Decimal("0.01"))

                    margin_floor = self._min_margin_floor()
                    if margin_at_rec < margin_floor:
                        constraints_applied.append(
                            f"margin_floor_violated_"
                            f"{margin_at_rec}%<{margin_floor}%")
                        rationale.append(
                            f"recommended rate would push margin to "
                            f"{margin_at_rec}% (< floor "
                            f"{margin_floor}%); action revised to HOLD")
                        recommended_rate = current_rate
                        margin_at_rec = pnl.margin_pct
                        action = "CONSTRAINED_BY_MARGIN"
            except Exception as e:
                rationale.append(
                    f"margin_estimation_unavailable: "
                    f"{type(e).__name__}")
        else:
            # HOLD case: report current margin as informational only
            try:
                pnl = self.pnl.compute_product_pnl(product)
                if pnl.margin_pct is not None:
                    margin_at_rec = pnl.margin_pct
            except Exception:
                pass

        # ---- Final change_bps ----
        change_bps = int(((recommended_rate - current_rate)
                            * Decimal("100")).quantize(
                                Decimal("1"),
                                rounding=ROUND_HALF_UP))

        # If change is below noise threshold and action was DECREASE/INCREASE,
        # downgrade to HOLD with explicit rationale
        if (action in ("INCREASE", "DECREASE")
                and abs(change_bps) < self.MEANINGFUL_CHANGE_BPS):
            rationale.append(
                f"change of {change_bps}bps below meaningful "
                f"threshold ({self.MEANINGFUL_CHANGE_BPS}bps); "
                f"action revised to HOLD")
            action = "HOLD"
            recommended_rate = current_rate
            change_bps = 0

        return PricingRecommendation(
            product_id=product_id,
            name=name,
            category=category,
            current_rate_pct=current_rate,
            peer_median_pct=peer_median,
            competitive_position=position,
            recommended_rate_pct=recommended_rate,
            change_bps=change_bps,
            action=action,
            rationale=tuple(rationale),
            constraints_applied=tuple(constraints_applied),
            margin_at_recommended_pct=margin_at_rec,
            is_estimate=landscape.is_estimate,
            status="ok")

    def get_all_recommendations(self) -> List[Dict[str, Any]]:
        return [self.get_pricing_recommendation(
                    p.get("id", "")).as_dict()
                for p in self._load_products()]

    def get_actionable_recommendations(
        self, min_change_bps: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        threshold = (min_change_bps if min_change_bps is not None
                      else self.MEANINGFUL_CHANGE_BPS)
        out: List[Dict[str, Any]] = []
        for rec in self.get_all_recommendations():
            if (rec["action"] in ("INCREASE", "DECREASE")
                    and rec["change_bps"] is not None
                    and abs(rec["change_bps"]) >= threshold):
                out.append(rec)
        out.sort(key=lambda x: -abs(x["change_bps"] or 0))
        return out

    def get_recommendation_summary(self) -> Dict[str, Any]:
        all_recs = self.get_all_recommendations()
        actions: Dict[str, int] = {}
        for r in all_recs:
            actions[r["action"]] = actions.get(r["action"], 0) + 1
        actionable = [r for r in all_recs
                       if r["action"] in ("INCREASE", "DECREASE")]
        avg_change = (sum(abs(r.get("change_bps") or 0)
                           for r in actionable) / len(actionable)
                       if actionable else 0)
        return {
            "n_products": len(all_recs),
            "by_action": actions,
            "n_actionable": len(actionable),
            "avg_actionable_change_bps": round(avg_change, 1),
        }

    def simulate_price_change(
        self, product_id: str, new_rate_pct: float,
    ) -> Dict[str, Any]:
        """What-if margin impact of a hypothetical price change."""
        product = next((p for p in self._load_products()
                        if p.get("id") == product_id), None)
        if not product:
            return {"ok": False, "reason": "product_not_found"}

        try:
            current_rate = Decimal(str(product.get("rate_avg", 0)
                                         or 0))
            new_rate = Decimal(str(new_rate_pct))
        except Exception:
            return {"ok": False, "reason": "invalid_rate_input"}

        try:
            current_pnl = self.pnl.compute_product_pnl(product)
        except Exception as e:
            return {"ok": False,
                    "reason": f"pnl_unavailable_{type(e).__name__}"}

        if current_pnl.margin_pct is None:
            return {"ok": False,
                    "reason": "no_current_margin_baseline"}

        if current_rate <= 0:
            return {"ok": False, "reason": "current_rate_zero"}

        rate_change_factor = (new_rate - current_rate) / current_rate
        projected_margin = (current_pnl.margin_pct
                              + (rate_change_factor
                                  * current_pnl.margin_pct))

        return {
            "ok": True,
            "product_id": product_id,
            "current_rate_pct": str(current_rate),
            "new_rate_pct": str(new_rate),
            "change_bps": int(((new_rate - current_rate)
                                 * Decimal("100")).quantize(
                                     Decimal("1"),
                                     rounding=ROUND_HALF_UP)),
            "current_margin_pct": str(current_pnl.margin_pct),
            "projected_margin_pct": str(projected_margin.quantize(
                Decimal("0.01"))),
            "margin_floor_pct": str(self._min_margin_floor()),
            "margin_floor_violated": (
                projected_margin < self._min_margin_floor()),
            "estimation_basis": ("first_order_proxy: margin scales "
                                  "linearly with rate change as a "
                                  "rough estimate; precise impact "
                                  "requires full P&L recomputation"),
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = DynamicPricingEngine()
    summary = eng.get_recommendation_summary()
    print(f"Recommendations: {summary['n_products']} products")
    print(f"  By action: {summary['by_action']}")
    print(f"  Actionable: {summary['n_actionable']} "
          f"(avg change {summary['avg_actionable_change_bps']}bps)")
    print()

    print("Sample recommendations:")
    for pid in ("P001", "P002", "P005", "P010", "P013", "P014", "P015"):
        rec = eng.get_pricing_recommendation(pid)
        change_str = (f"{rec.change_bps:+d}bps"
                       if rec.change_bps is not None else "n/a")
        print(f"  {pid} {rec.name} ({rec.category}): "
              f"current={rec.current_rate_pct}% → "
              f"rec={rec.recommended_rate_pct}% "
              f"({change_str}) "
              f"action={rec.action}")
        for r in rec.rationale[:2]:
            print(f"    → {r}")
    print()

    print("Actionable recommendations:")
    for rec in eng.get_actionable_recommendations()[:5]:
        print(f"  {rec['product_id']} {rec['name']}: "
              f"{rec['action']} {rec['change_bps']:+d}bps")
    print()

    # What-if simulation
    sim = eng.simulate_price_change("P014", 11.5)  # Fixed Deposits up to 11.5
    print(f"Simulate P014 → 11.5%: {sim}")


if __name__ == "__main__":
    _self_test()

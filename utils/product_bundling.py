"""utils.product_bundling — Product Bundling Intelligence
(Standard ENH-139, v10.150). Phase 1E Product Module — ninth engine.

Per Continuation.docx §Standard #139 (Eco Bank QA spec):
    Market basket analysis for product bundling.

This is the NINTH Phase 1E Product standard. Identifies product
combinations that customers tend to acquire together, scores bundle
affinity, and surfaces bundling recommendations for cross-sell
campaigns.

HONESTY DISCIPLINE — DATA LIMITATION DISCLOSED UPFRONT
------------------------------------------------------
Classical market basket analysis requires per-customer per-product
HOLDING data (Customer A holds {P001, P013, P015}; Customer B holds
{P001, P002, P014}; ...). The current `data/customer_intelligence.json`
seed only carries `products_held` as an INTEGER COUNT, not a list of
product IDs. True ground-truth co-occurrence cannot be computed from
this seed.

This engine therefore operates in PROXY MODE — it derives bundle
affinity from `propensity_scores` (customers' propensity-scored next-
products) instead of held products. The result is a propensity-based
bundling signal, not a holdings-based one. Engine is HONEST about
this throughout: every result carries `analysis_basis="propensity_proxy"`
and `is_estimate=True`. The engine surfaces real signal — products
that get high joint propensity scores tend to be sold together — but
operators must understand the limitation.

When per-customer holdings become available (e.g. via FLEXCUBE feed),
this engine can switch to `analysis_basis="holdings"` without changing
the public API.

Per Rule 7 (No silent ML predictions):
  1. Bundle scoring formula is fully deterministic — no ML
  2. Affinity threshold is a NAMED CONSTANT; banks override
  3. Honest fallback when products in a bundle aren't in registry
  4. analysis_basis tag surfaces the proxy nature explicitly

WHAT THIS MODULE SHIPS
----------------------
1. ProductBundlingIntelligence class with:
   - get_bundle_affinity(product_a_id, product_b_id) — pairwise affinity
   - get_top_bundles(min_affinity, top_n) — bank-wide top product pairs
   - get_bundles_for_product(product_id, top_n) — best companions for one product
   - get_segment_bundles(segment, top_n) — segment-specific top bundles
   - get_bundling_summary() — bank-wide signal strength + coverage

2. Frozen BundleAffinity dataclass with:
   - product_a + product_b
   - co_propensity_score (joint signal across customers)
   - support (% of customers with both above threshold)
   - lift (joint vs independent — measure of association)
   - n_customers_evaluated
   - analysis_basis ("propensity_proxy" | "holdings" when available)
   - is_estimate (True for proxy mode)

3. Reads:
   - data/customer_intelligence.json (3000 customers with propensity_scores)
   - data/products.json (16 products)

HONESTY DISCIPLINE
------------------
- analysis_basis tag on every result discloses proxy mode
- is_estimate=True universally in proxy mode
- min_propensity threshold for "interest" is NAMED CONSTANT; below
  threshold is excluded from bundle calculation (consistent with ENH-138)
- Lift > 1.0 means positive association; engine reports raw lift
  (no manipulation)
- Symmetric pairs (A,B) and (B,A) treated as identical to avoid
  double-counting
- Engine NEVER writes
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).parent.parent / "data"
CUSTOMER_INTEL_PATH = DATA_DIR / "customer_intelligence.json"
PRODUCTS_PATH = DATA_DIR / "products.json"

# Map propensity name → product_id (mirrors ENH-138)
PROPENSITY_TO_PRODUCT_ID: Dict[str, str] = {
    "Personal Loan": "P001",
    "Mortgage": "P002",
    "Asset Finance": "P003",
    "Business Loan": "P005",
    "Fixed Deposit": "P014",
    "Insurance": "P015",
}


@dataclass(frozen=True)
class BundleAffinity:
    product_a_id: str
    product_a_name: str
    product_b_id: str
    product_b_name: str
    co_propensity_score: Decimal     # avg joint propensity across customers
    support_pct: Decimal              # % of customers with both above threshold
    lift: Decimal                      # joint / (P(A) × P(B))
    n_customers_evaluated: int
    n_with_both_interest: int
    analysis_basis: str               # "propensity_proxy" | "holdings"
    is_estimate: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "product_a_id": self.product_a_id,
            "product_a_name": self.product_a_name,
            "product_b_id": self.product_b_id,
            "product_b_name": self.product_b_name,
            "co_propensity_score": str(self.co_propensity_score),
            "support_pct": str(self.support_pct),
            "lift": str(self.lift),
            "n_customers_evaluated": self.n_customers_evaluated,
            "n_with_both_interest": self.n_with_both_interest,
            "analysis_basis": self.analysis_basis,
            "is_estimate": self.is_estimate,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductBundlingIntelligence:
    """Product bundling analytics from propensity-score proxy data.

    Read-only contract — never writes.
    """

    # Above-median propensity threshold — the customer must show ABOVE-
    # AVERAGE interest for a product to count toward joint signal.
    # Calibrated to the seed data where overall propensity median is ~0.16.
    # Below 0.05 the customer has been already filtered upstream by ENH-138.
    # Here we want the SIGNAL of meaningful interest, so threshold is
    # higher than the inclusion threshold.
    MIN_PROPENSITY_FOR_INTEREST = Decimal("0.15")
    DEFAULT_MIN_AFFINITY = Decimal("0.5")
    DEFAULT_TOP_N = 5
    ANALYSIS_BASIS_PROXY = "propensity_proxy"
    ANALYSIS_BASIS_HOLDINGS = "holdings"

    def __init__(
        self,
        customer_intel_path: Optional[Path] = None,
        products_path: Optional[Path] = None,
    ) -> None:
        self.customer_intel_path = (customer_intel_path
                                      or CUSTOMER_INTEL_PATH)
        self.products_path = products_path or PRODUCTS_PATH
        self._intel_cache: Optional[Dict[str, Any]] = None
        self._products_cache: Optional[List[Dict[str, Any]]] = None
        # Reverse map from product_id to propensity_name
        self._product_to_propensity = {
            v: k for k, v in PROPENSITY_TO_PRODUCT_ID.items()
        }

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

    def _product_name(self, product_id: str) -> str:
        for p in self._load_products():
            if p.get("id") == product_id:
                return p.get("name", "")
        return ""

    def _propensity_for_product(
        self, customer: Dict[str, Any], product_id: str,
    ) -> Optional[Decimal]:
        prop_name = self._product_to_propensity.get(product_id)
        if not prop_name:
            return None
        scores = customer.get("propensity_scores") or {}
        v = scores.get(prop_name)
        if v is None:
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Core: pairwise affinity
    # ------------------------------------------------------------------

    def get_bundle_affinity(
        self, product_a_id: str, product_b_id: str,
    ) -> Optional[BundleAffinity]:
        if product_a_id == product_b_id:
            return None
        # Both products must be in propensity-resolvable set
        if (product_a_id not in self._product_to_propensity
                or product_b_id not in self._product_to_propensity):
            return None

        intel = self._load_intel()
        if not intel:
            return None

        threshold = self.MIN_PROPENSITY_FOR_INTEREST
        n_total = len(intel)
        n_a_interest = 0
        n_b_interest = 0
        n_both = 0
        joint_score_sum = Decimal("0")

        for cust in intel.values():
            pa = self._propensity_for_product(cust, product_a_id)
            pb = self._propensity_for_product(cust, product_b_id)
            if pa is None or pb is None:
                continue
            a_int = pa >= threshold
            b_int = pb >= threshold
            if a_int:
                n_a_interest += 1
            if b_int:
                n_b_interest += 1
            if a_int and b_int:
                n_both += 1
                # Joint score = geometric mean of propensities
                joint_score_sum += (pa * pb).sqrt() if hasattr(
                    pa * pb, 'sqrt') else (pa * pb)

        if n_total == 0:
            return None

        # Co-propensity = avg joint score across customers with both interests
        if n_both > 0:
            avg_joint = (joint_score_sum
                          / Decimal(n_both)).quantize(
                              Decimal("0.0001"))
        else:
            avg_joint = Decimal("0")

        # Support = fraction of customers with both interests
        support = (Decimal(n_both) / Decimal(n_total)
                    * Decimal("100")).quantize(Decimal("0.01"))

        # Lift = P(A and B) / (P(A) × P(B))
        # If both A and B are universal (n_a or n_b = n_total), lift = 1
        if n_a_interest > 0 and n_b_interest > 0 and n_total > 0:
            p_a = Decimal(n_a_interest) / Decimal(n_total)
            p_b = Decimal(n_b_interest) / Decimal(n_total)
            p_both = Decimal(n_both) / Decimal(n_total)
            denom = p_a * p_b
            lift = (p_both / denom).quantize(Decimal("0.0001")) \
                if denom > 0 else Decimal("1.0")
        else:
            lift = Decimal("0")

        return BundleAffinity(
            product_a_id=product_a_id,
            product_a_name=self._product_name(product_a_id),
            product_b_id=product_b_id,
            product_b_name=self._product_name(product_b_id),
            co_propensity_score=avg_joint,
            support_pct=support,
            lift=lift,
            n_customers_evaluated=n_total,
            n_with_both_interest=n_both,
            analysis_basis=self.ANALYSIS_BASIS_PROXY,
            is_estimate=True)

    # ------------------------------------------------------------------
    # Top bundles bank-wide
    # ------------------------------------------------------------------

    def get_top_bundles(
        self, min_affinity: Optional[float] = None,
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        threshold = (Decimal(str(min_affinity))
                       if min_affinity is not None
                       else self.DEFAULT_MIN_AFFINITY)
        n = top_n or self.DEFAULT_TOP_N

        # Generate all unique product pairs from propensity-mapped products
        product_ids = list(self._product_to_propensity.keys())
        bundles: List[BundleAffinity] = []

        for a, b in combinations(product_ids, 2):
            affinity = self.get_bundle_affinity(a, b)
            if affinity is None:
                continue
            if affinity.support_pct < threshold * Decimal("100"):
                continue
            bundles.append(affinity)

        # Sort by lift descending, then support descending
        bundles.sort(key=lambda x: (-float(x.lift),
                                      -float(x.support_pct)))
        return [b.as_dict() for b in bundles[:n]]

    def get_bundles_for_product(
        self, product_id: str, top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if product_id not in self._product_to_propensity:
            return []
        n = top_n or self.DEFAULT_TOP_N
        bundles: List[BundleAffinity] = []
        for other_id in self._product_to_propensity.keys():
            if other_id == product_id:
                continue
            affinity = self.get_bundle_affinity(product_id, other_id)
            if affinity is not None:
                bundles.append(affinity)
        bundles.sort(key=lambda x: (-float(x.lift),
                                      -float(x.support_pct)))
        return [b.as_dict() for b in bundles[:n]]

    # ------------------------------------------------------------------
    # Segment-specific bundles
    # ------------------------------------------------------------------

    def get_segment_bundles(
        self, segment: str, top_n: Optional[int] = None,
    ) -> Dict[str, Any]:
        n = top_n or self.DEFAULT_TOP_N
        intel = self._load_intel()
        seg_intel = {cid: c for cid, c in intel.items()
                      if c.get("segment") == segment}
        if not seg_intel:
            return {"ok": False,
                    "segment": segment,
                    "fallback_reason": "no_customers_in_segment"}

        threshold = self.MIN_PROPENSITY_FOR_INTEREST
        n_total = len(seg_intel)
        product_ids = list(self._product_to_propensity.keys())
        bundles: List[Dict[str, Any]] = []

        for a, b in combinations(product_ids, 2):
            n_a = n_b = n_both = 0
            joint_sum = Decimal("0")
            for cust in seg_intel.values():
                pa = self._propensity_for_product(cust, a)
                pb = self._propensity_for_product(cust, b)
                if pa is None or pb is None:
                    continue
                a_int = pa >= threshold
                b_int = pb >= threshold
                if a_int:
                    n_a += 1
                if b_int:
                    n_b += 1
                if a_int and b_int:
                    n_both += 1
                    joint_sum += (pa * pb)
            if n_both == 0:
                continue
            support_pct = (Decimal(n_both) / Decimal(n_total)
                            * Decimal("100")).quantize(Decimal("0.01"))
            avg_joint = (joint_sum / Decimal(n_both)
                          ).quantize(Decimal("0.0001"))
            if n_a > 0 and n_b > 0:
                p_a = Decimal(n_a) / Decimal(n_total)
                p_b = Decimal(n_b) / Decimal(n_total)
                p_both = Decimal(n_both) / Decimal(n_total)
                lift = (p_both / (p_a * p_b)
                         ).quantize(Decimal("0.0001")) \
                    if (p_a * p_b) > 0 else Decimal("1.0")
            else:
                lift = Decimal("0")
            bundles.append({
                "product_a_id": a,
                "product_a_name": self._product_name(a),
                "product_b_id": b,
                "product_b_name": self._product_name(b),
                "co_propensity_score": str(avg_joint),
                "support_pct": str(support_pct),
                "lift": str(lift),
                "n_with_both_interest": n_both,
            })

        bundles.sort(key=lambda x: (-float(x["lift"]),
                                      -float(x["support_pct"])))
        return {
            "ok": True,
            "segment": segment,
            "n_customers": n_total,
            "analysis_basis": self.ANALYSIS_BASIS_PROXY,
            "is_estimate": True,
            "top_bundles": bundles[:n],
            "n_bundles_evaluated": len(bundles),
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_bundling_summary(self) -> Dict[str, Any]:
        product_ids = list(self._product_to_propensity.keys())
        n_pairs_possible = len(product_ids) * (len(product_ids) - 1) // 2
        all_bundles = self.get_top_bundles(min_affinity=0.0,
                                             top_n=n_pairs_possible)
        if not all_bundles:
            return {
                "ok": False,
                "fallback_reason": "no_bundles_computed",
                "analysis_basis": self.ANALYSIS_BASIS_PROXY,
            }

        # Lift distribution
        n_strong = sum(1 for b in all_bundles
                        if float(b["lift"]) > 1.5)
        n_positive = sum(1 for b in all_bundles
                          if float(b["lift"]) > 1.0)
        n_weak = sum(1 for b in all_bundles
                       if float(b["lift"]) <= 1.0)
        avg_support = (sum(float(b["support_pct"])
                            for b in all_bundles)
                        / len(all_bundles)) if all_bundles else 0

        return {
            "ok": True,
            "analysis_basis": self.ANALYSIS_BASIS_PROXY,
            "is_estimate": True,
            "n_pairs_evaluated": len(all_bundles),
            "n_pairs_possible": n_pairs_possible,
            "n_strong_associations_lift_gt_1_5": n_strong,
            "n_positive_associations_lift_gt_1": n_positive,
            "n_weak_associations_lift_lte_1": n_weak,
            "avg_support_pct": round(avg_support, 2),
            "mappable_products_count": len(product_ids),
            "data_limitation_note": (
                "products_held in customer_intelligence.json is an "
                "integer count, not a list of product IDs. True "
                "holdings-based market basket analysis requires per-"
                "customer per-product holdings data (e.g. via FLEXCUBE "
                "feed). This engine derives bundle affinity from "
                "propensity_scores as a proxy. Operators should treat "
                "results as directional signal, not ground truth. "
                "Engine surfaces analysis_basis='propensity_proxy' on "
                "every result for transparency."),
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductBundlingIntelligence()
    print("=" * 60)
    print("ENH-139 Product Bundling Intelligence — self-test")
    print("=" * 60)

    summary = eng.get_bundling_summary()
    print(f"\nBundling summary:")
    print(f"  analysis_basis: {summary['analysis_basis']}")
    print(f"  pairs evaluated: {summary['n_pairs_evaluated']}")
    print(f"  strong (lift>1.5): {summary['n_strong_associations_lift_gt_1_5']}")
    print(f"  positive (lift>1): {summary['n_positive_associations_lift_gt_1']}")
    print(f"  weak (lift≤1): {summary['n_weak_associations_lift_lte_1']}")
    print(f"  avg support: {summary['avg_support_pct']}%")
    print()

    print("Top 5 bundles bank-wide:")
    for b in eng.get_top_bundles(min_affinity=0.0, top_n=5):
        print(f"  {b['product_a_name']} + {b['product_b_name']}: "
              f"lift={b['lift']} support={b['support_pct']}% "
              f"(n={b['n_with_both_interest']})")
    print()

    # Segment-level
    for seg in ("Mass", "Premium"):
        out = eng.get_segment_bundles(seg, top_n=3)
        if out.get("ok"):
            print(f"{seg} segment top 3 bundles (n={out['n_customers']}):")
            for b in out["top_bundles"]:
                print(f"  {b['product_a_name']} + {b['product_b_name']}: "
                      f"lift={b['lift']} support={b['support_pct']}%")
            print()

    # Companions for Personal Loan
    print("Best companions for P001 Personal Loans:")
    for b in eng.get_bundles_for_product("P001", top_n=3):
        print(f"  + {b['product_b_name']}: lift={b['lift']} "
              f"support={b['support_pct']}%")
    print()

    print(f"Data limitation note: {summary['data_limitation_note'][:200]}...")


if __name__ == "__main__":
    _self_test()

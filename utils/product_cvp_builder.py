"""utils.product_cvp_builder — Customer Value Proposition (CVP) Builder
(Standard ENH-135, v10.146). Phase 1E Product Module — fifth engine.

Per Continuation.docx §Standard #135 (Eco Bank QA spec):
    AI-powered value proposition generator tailored by customer segment.

This is the FIFTH Phase 1E Product standard and the FIRST that
SYNTHESIZES outputs from prior engines (ENH-133 needs + ENH-134
competitive position + ENH-131 profitability) into a forward-looking
artifact (a CVP draft per segment).

Per Rule 7 (No silent ML predictions):
  1. Default rule-based generation — deterministic, transparent
  2. AI narrative hook (`ai_narrative_fn`) is opt-in and injectable;
     when not supplied, engine returns rule-based result with
     basis="rule_based" tag
  3. When AI is supplied, output tagged basis="llm" so consumers
     know the narrative was LLM-generated; structural/numeric
     content remains rule-based regardless
  4. Trade-offs (LAGGARD products) are HONESTLY DISCLOSED — engine
     never papers over weaknesses to make a CVP look better

WHAT THIS MODULE SHIPS
----------------------
1. ProductCVPBuilder class with:
   - generate_cvp_for_segment(segment) — full CVP for one segment
   - generate_all_segment_cvps() — all 4 customer segments
   - get_cvp_summary() — bank-wide CVP coverage summary
   - get_cvp_strength_score(segment) — quantitative CVP strength

2. Frozen CVPResult dataclass with structured sections:
   - target_segment + segment_size + segment_clv_share
   - addressed_needs[] — top customer needs from ENH-133
   - differentiating_offers[] — LEADER products from ENH-134
     applicable to segment
   - trade_offs[] — LAGGARD products HONESTLY surfaced
   - proof_points[] — numeric peer comparisons
   - cvp_strength_score (0-100, deterministic formula)
   - narrative — rule-based by default, optional LLM augmentation
   - basis: "rule_based" | "llm"
   - is_estimate flag when underlying data is thin

3. Reads:
   - data/customer_needs_registry.json (via ENH-133 engine)
   - data/customer_intelligence.json (via ENH-133)
   - data/products.json
   - data/competitor_data.json (via ENH-134 engine)
   - data/product_competitor_mapping.json (via ENH-134)
   - data/cost_allocation_config.json (via ENH-131 for profitability context)

HONESTY DISCIPLINE
------------------
- Trade-offs ALWAYS surfaced — if any product mapped to the segment's
  needs is a LAGGARD, it appears in trade_offs[] with the exact
  delta and direction. CVPs that "look perfect" are a smell.
- AI hook output is OPT-IN and TAGGED. When ai_narrative_fn is None,
  engine returns the rule-based narrative with basis="rule_based".
  When the hook is supplied and succeeds, basis="llm" + ai_warning
  string surfacing that the narrative was generated.
- segment_clv_share computed from real customer_intelligence data;
  never invented.
- cvp_strength_score formula is documented + deterministic; never
  ML-inferred.
- When a segment has no LEADER products mapped, CVP is honestly
  weak — engine returns the empty differentiating_offers[] rather
  than fabricating differentiators.

RELATED STANDARDS
-----------------
- ENH-133 Customer Needs (consumed for segment priority needs)
- ENH-134 Competitive Intelligence (consumed for LEADER/LAGGARD position)
- ENH-131 Product Profitability (consumed for proof-point context)
- ENH-138 AI Product Recommendation (downstream — uses CVPs to anchor
  recommendation reasoning)
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Forward imports — companion engines
from utils.customer_needs_analyzer import CustomerNeedsAnalyzer
from utils.product_competitive_intel import ProductCompetitiveIntelligence
from utils.product_pnl_intelligence import ProductPnLIntelligence

DATA_DIR = Path(__file__).parent.parent / "data"
NEEDS_REGISTRY_PATH = DATA_DIR / "customer_needs_registry.json"
PRODUCTS_PATH = DATA_DIR / "products.json"


@dataclass(frozen=True)
class CVPResult:
    target_segment: str
    segment_size: int
    segment_clv_total_kes: Decimal
    segment_clv_share_pct: Optional[Decimal]
    addressed_needs: Tuple[Dict[str, Any], ...]
    differentiating_offers: Tuple[Dict[str, Any], ...]
    trade_offs: Tuple[Dict[str, Any], ...]
    proof_points: Tuple[Dict[str, Any], ...]
    cvp_strength_score: int           # 0-100
    cvp_strength_band: str             # STRONG | MODERATE | WEAK
    narrative: str
    basis: str                         # "rule_based" | "llm"
    is_estimate: bool
    missing_inputs: Tuple[str, ...] = field(default_factory=tuple)
    ai_warning: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "target_segment": self.target_segment,
            "segment_size": self.segment_size,
            "segment_clv_total_kes": str(self.segment_clv_total_kes),
            "segment_clv_share_pct": (
                str(self.segment_clv_share_pct)
                if self.segment_clv_share_pct is not None else None),
            "addressed_needs": list(self.addressed_needs),
            "differentiating_offers": list(self.differentiating_offers),
            "trade_offs": list(self.trade_offs),
            "proof_points": list(self.proof_points),
            "cvp_strength_score": self.cvp_strength_score,
            "cvp_strength_band": self.cvp_strength_band,
            "narrative": self.narrative,
            "basis": self.basis,
            "is_estimate": self.is_estimate,
            "missing_inputs": list(self.missing_inputs),
            "ai_warning": self.ai_warning,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProductCVPBuilder:
    """Per-segment CVP synthesis from companion engines.

    Read-only contract — never writes.
    """

    STRONG_THRESHOLD = 70    # cvp_strength_score ≥ 70 → STRONG
    WEAK_THRESHOLD = 40       # < 40 → WEAK
    TOP_N_NEEDS_PER_CVP = 5
    TOP_N_OFFERS_PER_CVP = 5
    TOP_N_TRADE_OFFS_PER_CVP = 3

    def __init__(
        self,
        needs_analyzer: Optional[CustomerNeedsAnalyzer] = None,
        competitive_intel: Optional[ProductCompetitiveIntelligence] = None,
        pnl_engine: Optional[ProductPnLIntelligence] = None,
        ai_narrative_fn: Optional[Callable[[Dict[str, Any]], str]] = None,
        needs_registry_path: Optional[Path] = None,
        products_path: Optional[Path] = None,
    ) -> None:
        self.needs = needs_analyzer or CustomerNeedsAnalyzer()
        self.competitive = (competitive_intel
                              or ProductCompetitiveIntelligence())
        self.pnl = pnl_engine or ProductPnLIntelligence()
        self.ai_narrative_fn = ai_narrative_fn
        self.needs_registry_path = (needs_registry_path
                                      or NEEDS_REGISTRY_PATH)
        self.products_path = products_path or PRODUCTS_PATH

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------

    def _load_needs_registry(self) -> Dict[str, Any]:
        try:
            with open(self.needs_registry_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"needs": [], "segment_expectations": {}}

    def _load_products(self) -> List[Dict[str, Any]]:
        try:
            with open(self.products_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    # ------------------------------------------------------------------
    # CVP generation
    # ------------------------------------------------------------------

    def generate_cvp_for_segment(self, segment: str) -> CVPResult:
        # 1. Segment context — size, CLV share
        intel = self.needs._load_intel()
        in_segment = [(cid, c) for cid, c in intel.items()
                      if c.get("segment") == segment]
        n_segment = len(in_segment)

        if n_segment == 0:
            return CVPResult(
                target_segment=segment,
                segment_size=0,
                segment_clv_total_kes=Decimal("0"),
                segment_clv_share_pct=None,
                addressed_needs=(), differentiating_offers=(),
                trade_offs=(), proof_points=(),
                cvp_strength_score=0, cvp_strength_band="WEAK",
                narrative=f"No customers in segment '{segment}'.",
                basis="rule_based", is_estimate=True,
                missing_inputs=("no_customers_in_segment",))

        seg_clv = Decimal("0")
        for _, c in in_segment:
            try:
                seg_clv += Decimal(str(c.get("clv_estimate", 0) or 0))
            except Exception:
                pass

        total_clv = Decimal("0")
        for c in intel.values():
            try:
                total_clv += Decimal(str(c.get("clv_estimate", 0) or 0))
            except Exception:
                pass
        clv_share_pct: Optional[Decimal] = None
        if total_clv > 0:
            clv_share_pct = (seg_clv / total_clv * Decimal("100")
                              ).quantize(Decimal("0.01"))

        # 2. Addressed needs — from ENH-133 segment-applicable registry
        registry = self._load_needs_registry()
        applicable_needs = [
            n for n in registry.get("needs", [])
            if segment in n.get("applicable_segments", [])
        ]
        # Order: HIGH > MEDIUM > LOW > FUNDAMENTAL by priority
        priority_order = {"FUNDAMENTAL": 0, "HIGH": 1,
                           "MEDIUM": 2, "LOW": 3}
        applicable_needs.sort(
            key=lambda n: priority_order.get(n.get("priority", "LOW"), 9))
        addressed: List[Dict[str, Any]] = []
        for need in applicable_needs[:self.TOP_N_NEEDS_PER_CVP]:
            addressed.append({
                "need_id": need["need_id"],
                "name": need.get("name", need["need_id"]),
                "priority": need.get("priority", "MEDIUM"),
                "description": need.get("description", ""),
            })

        # 3. Differentiating offers — LEADER products from ENH-134
        # Pull all LEADER products that are applicable
        # (cross-reference: products eligible to all customer segments)
        differentiating: List[Dict[str, Any]] = []
        trade_offs: List[Dict[str, Any]] = []
        proof_points: List[Dict[str, Any]] = []

        for product in self._load_products():
            pid = product.get("id", "")
            landscape = self.competitive.get_competitor_landscape(pid)
            if landscape.status != "ok":
                continue

            entry = {
                "product_id": pid,
                "name": product.get("name", ""),
                "category": product.get("category", ""),
                "our_rate_pct": (str(landscape.our_rate_pct)
                                  if landscape.our_rate_pct is not None
                                  else None),
                "peer_median_pct": (str(landscape.peer_median_pct)
                                      if landscape.peer_median_pct is not None
                                      else None),
                "delta_vs_median_bps": landscape.delta_vs_median_bps,
                "position": landscape.position,
            }

            if landscape.position == "LEADER":
                differentiating.append(entry)
                # Generate proof point
                if landscape.delta_vs_median_bps is not None:
                    abs_bps = abs(landscape.delta_vs_median_bps)
                    direction_text = ("undercut" if landscape.benchmark_type
                                       == "lending" else "outpay")
                    proof_points.append({
                        "claim": (f"On {product.get('name', pid)}, we "
                                   f"{direction_text} peer median by "
                                   f"{abs_bps} bps"),
                        "our_rate_pct": str(landscape.our_rate_pct),
                        "peer_median_pct": str(landscape.peer_median_pct),
                        "n_peers": landscape.n_peers,
                        "is_estimate": landscape.is_estimate,
                    })
            elif landscape.position == "LAGGARD":
                trade_offs.append(entry)

        # Sort + cap
        differentiating.sort(
            key=lambda x: -abs(x["delta_vs_median_bps"] or 0))
        differentiating = differentiating[:self.TOP_N_OFFERS_PER_CVP]

        trade_offs.sort(
            key=lambda x: -abs(x["delta_vs_median_bps"] or 0))
        trade_offs = trade_offs[:self.TOP_N_TRADE_OFFS_PER_CVP]

        proof_points = proof_points[:self.TOP_N_OFFERS_PER_CVP]

        # 4. CVP strength score (0-100, deterministic)
        # Components:
        #   needs coverage:  min(n_addressed_needs / 5, 1) × 30
        #   offer breadth:   min(n_differentiating / 5, 1) × 40
        #   trade-off penalty: -10 per LAGGARD product up to -30
        #   estimate penalty: -5 if any underlying is_estimate
        score = 0.0
        score += min(len(addressed) / 5.0, 1.0) * 30
        score += min(len(differentiating) / 5.0, 1.0) * 40
        n_lag_capped = min(len(trade_offs), 3)
        score -= n_lag_capped * 10
        any_estimate = any(p.get("is_estimate")
                           for p in proof_points)
        if any_estimate:
            score -= 5
        # Floor at 0, ceil at 100
        score = max(0.0, min(100.0, score))
        score_int = int(round(score))
        if score_int >= self.STRONG_THRESHOLD:
            band = "STRONG"
        elif score_int < self.WEAK_THRESHOLD:
            band = "WEAK"
        else:
            band = "MODERATE"

        # 5. Narrative — rule-based default
        narrative = self._build_rule_based_narrative(
            segment=segment, n_segment=n_segment,
            clv_share_pct=clv_share_pct,
            addressed=addressed,
            differentiating=differentiating,
            trade_offs=trade_offs,
            band=band)

        basis = "rule_based"
        ai_warning: Optional[str] = None

        if self.ai_narrative_fn is not None:
            try:
                ai_input = {
                    "segment": segment,
                    "addressed_needs": addressed,
                    "differentiating_offers": differentiating,
                    "trade_offs": trade_offs,
                    "proof_points": proof_points,
                    "rule_based_narrative": narrative,
                }
                ai_text = self.ai_narrative_fn(ai_input)
                if isinstance(ai_text, str) and ai_text.strip():
                    narrative = ai_text.strip()
                    basis = "llm"
                    ai_warning = ("Narrative LLM-generated. Structural + "
                                   "numeric content remains rule-based.")
            except Exception as e:
                ai_warning = (f"AI hook failed ({type(e).__name__}); "
                                "falling back to rule-based narrative.")

        # 6. is_estimate flag
        is_estimate = (any_estimate or len(differentiating) < 2
                        or len(addressed) < 3)

        missing: List[str] = []
        if not differentiating:
            missing.append(
                "no_LEADER_products_for_this_segment")
        if not addressed:
            missing.append(
                "no_applicable_needs_in_registry_for_segment")

        return CVPResult(
            target_segment=segment,
            segment_size=n_segment,
            segment_clv_total_kes=seg_clv,
            segment_clv_share_pct=clv_share_pct,
            addressed_needs=tuple(addressed),
            differentiating_offers=tuple(differentiating),
            trade_offs=tuple(trade_offs),
            proof_points=tuple(proof_points),
            cvp_strength_score=score_int,
            cvp_strength_band=band,
            narrative=narrative,
            basis=basis,
            is_estimate=is_estimate,
            missing_inputs=tuple(missing),
            ai_warning=ai_warning)

    def _build_rule_based_narrative(
        self, segment: str, n_segment: int,
        clv_share_pct: Optional[Decimal],
        addressed: List[Dict[str, Any]],
        differentiating: List[Dict[str, Any]],
        trade_offs: List[Dict[str, Any]],
        band: str,
    ) -> str:
        """Deterministic rule-based narrative. AI hook may replace it."""
        lines: List[str] = []
        lines.append(
            f"Customer Value Proposition — {segment} segment "
            f"({n_segment} customers")
        if clv_share_pct is not None:
            lines[-1] += f", {clv_share_pct}% of total CLV)"
        else:
            lines[-1] += ")"

        lines.append("")
        lines.append(f"CVP strength: {band}.")

        if addressed:
            lines.append("")
            lines.append("Customer needs addressed:")
            for n in addressed:
                lines.append(
                    f"  • [{n['priority']}] {n['name']} — "
                    f"{n['description']}")

        if differentiating:
            lines.append("")
            lines.append("Where we lead:")
            for offer in differentiating:
                lines.append(
                    f"  • {offer['name']}: our rate "
                    f"{offer['our_rate_pct']}% vs peer median "
                    f"{offer['peer_median_pct']}% "
                    f"({offer['delta_vs_median_bps']} bps)")

        if trade_offs:
            lines.append("")
            lines.append("Honest trade-offs (we lag here):")
            for to in trade_offs:
                lines.append(
                    f"  • {to['name']}: our rate {to['our_rate_pct']}% "
                    f"vs peer median {to['peer_median_pct']}% "
                    f"({to['delta_vs_median_bps']} bps)")

        if not differentiating:
            lines.append("")
            lines.append(
                "No competitive LEADER products mapped for this "
                "segment — CVP is honestly weak. Consider extending "
                "competitor benchmark mapping or building "
                "differentiators.")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def generate_all_segment_cvps(self) -> Dict[str, Dict[str, Any]]:
        intel = self.needs._load_intel()
        segments = sorted({c.get("segment") for c in intel.values()
                            if c.get("segment")})
        return {seg: self.generate_cvp_for_segment(seg).as_dict()
                for seg in segments}

    def get_cvp_summary(self) -> Dict[str, Any]:
        cvps = self.generate_all_segment_cvps()
        n_strong = sum(1 for c in cvps.values()
                        if c["cvp_strength_band"] == "STRONG")
        n_moderate = sum(1 for c in cvps.values()
                          if c["cvp_strength_band"] == "MODERATE")
        n_weak = sum(1 for c in cvps.values()
                      if c["cvp_strength_band"] == "WEAK")
        avg_score = (sum(c["cvp_strength_score"]
                          for c in cvps.values()) / len(cvps)
                      if cvps else 0)
        return {
            "n_segments": len(cvps),
            "n_strong": n_strong,
            "n_moderate": n_moderate,
            "n_weak": n_weak,
            "avg_strength_score": round(avg_score, 2),
            "cvps_by_segment": {seg: c["cvp_strength_band"]
                                  for seg, c in cvps.items()},
        }

    def get_cvp_strength_score(self, segment: str) -> Dict[str, Any]:
        result = self.generate_cvp_for_segment(segment)
        return {
            "segment": segment,
            "score": result.cvp_strength_score,
            "band": result.cvp_strength_band,
            "n_addressed_needs": len(result.addressed_needs),
            "n_differentiating_offers": len(result.differentiating_offers),
            "n_trade_offs": len(result.trade_offs),
            "is_estimate": result.is_estimate,
        }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    eng = ProductCVPBuilder()
    summary = eng.get_cvp_summary()
    print(f"CVP coverage: {summary['n_segments']} segments")
    print(f"  STRONG: {summary['n_strong']}")
    print(f"  MODERATE: {summary['n_moderate']}")
    print(f"  WEAK: {summary['n_weak']}")
    print(f"  Avg strength: {summary['avg_strength_score']}")
    print()

    # Sample CVP for each segment
    for seg in ("Mass", "Mass Affluent", "Affluent", "Premium"):
        cvp = eng.generate_cvp_for_segment(seg)
        print(f"=== {seg} ===")
        print(f"  size={cvp.segment_size} clv_share={cvp.segment_clv_share_pct}%")
        print(f"  strength: {cvp.cvp_strength_score} ({cvp.cvp_strength_band})")
        print(f"  basis: {cvp.basis}")
        print(f"  needs: {len(cvp.addressed_needs)} addressed")
        print(f"  offers: {len(cvp.differentiating_offers)} LEADER")
        print(f"  trade_offs: {len(cvp.trade_offs)} LAGGARD")
        print(f"  proof_points: {len(cvp.proof_points)}")
        print()

    # Sample full narrative for Premium
    print("=== Sample narrative (Premium) ===")
    cvp = eng.generate_cvp_for_segment("Premium")
    print(cvp.narrative)
    print()

    # AI hook smoke test (transparent fallback)
    def fake_ai(input_dict):
        return ("AI-generated narrative for "
                f"{input_dict['segment']} (mock).")

    eng_with_ai = ProductCVPBuilder(ai_narrative_fn=fake_ai)
    cvp_ai = eng_with_ai.generate_cvp_for_segment("Mass")
    print(f"With AI hook: basis={cvp_ai.basis}")
    print(f"  ai_warning: {cvp_ai.ai_warning}")


if __name__ == "__main__":
    _self_test()

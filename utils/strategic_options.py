"""utils.strategic_options — Strategic Options Generator
(Standard ENH-142, v10.135). Phase 1 Strategy Module — second engine.

Per Continuation.docx §Standard #142 (Eco Bank QA spec):
    StrategicOptionsGenerator — AI-powered strategic option generation
    with impact modeling. Consumes SWOT output from ENH-141 and a board
    vision statement; produces ranked Ansoff-Matrix strategic options
    plus an AI-recommended option and side-by-side comparison matrix.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Impact modeling is rule-based (deterministic) — same SWOT inputs +
     same vision → same options + same impact estimates
  2. AI recommendation hook injectable via ai_recommender_fn at
     construction; when None, recommendation falls back to highest
     scored option per a transparent multi-criteria score
  3. Each option's expected_impact is derived from quantifiable SWOT
     evidence (number of strengths × strength multiplier, etc.) — not
     fabricated

WHAT THIS MODULE SHIPS
----------------------
1. StrategicOptionsGenerator class with:
   - generate_options(vision, swot_analysis) — produces 4 Ansoff-Matrix
     options (Market Penetration, Market Development, Product
     Development, Diversification)
   - model_impact(option_type, swot, vision) — deterministic impact
     estimation
   - ai_recommend_option(options, vision) — rule-based default; LLM
     hook injectable
   - build_comparison_matrix(options) — side-by-side comparison

2. Ansoff Matrix mapping (standard 2×2 strategy taxonomy):
   - Existing products × Existing markets → Market Penetration (LOW risk)
   - Existing products × New markets      → Market Development (MEDIUM)
   - New products    × Existing markets   → Product Development (MEDIUM)
   - New products    × New markets        → Diversification (HIGH)

3. Multi-criteria scoring (transparent, weighted):
   - SWOT-fit score (does the option leverage strengths and address opps?)
   - Risk score (inversely weighted)
   - Time-to-impact (shorter horizons preferred for tactical wins)
   - Vision alignment (rule-based keyword match against vision text)

HONESTY DISCIPLINE
------------------
- All scores are explicit and reproducible from inputs
- "AI-recommended" label only applied when ai_recommender_fn was
  injected; otherwise the recommendation is labeled "rule_based"
- Empty SWOT quadrants degrade gracefully — Market Penetration still
  generated even if internal["strengths"] is empty (with a note)
- No options are "hidden" — all 4 Ansoff cells generate, even if
  one is clearly inferior to another

RELATED STANDARDS
-----------------
- ENH-141 StrategyFormulationEngine — produces the SWOT input
- ENH-143 Strategic Pillars (planned) — consumes selected option
- ENH-144 Strategic Initiative & Portfolio Management (planned) —
  decomposes selected option into initiatives
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.strategic_options")


# ════════════════════════════════════════════════════════════════════
# Constants — Ansoff Matrix archetypes (per Continuation.docx spec)
# ════════════════════════════════════════════════════════════════════

ANSOFF_MARKET_PENETRATION = "market_penetration"
ANSOFF_MARKET_DEVELOPMENT = "market_development"
ANSOFF_PRODUCT_DEVELOPMENT = "product_development"
ANSOFF_DIVERSIFICATION = "diversification"

ALL_OPTION_TYPES = (
    ANSOFF_MARKET_PENETRATION,
    ANSOFF_MARKET_DEVELOPMENT,
    ANSOFF_PRODUCT_DEVELOPMENT,
    ANSOFF_DIVERSIFICATION,
)

# Risk levels per Ansoff
RISK_LEVEL = {
    ANSOFF_MARKET_PENETRATION:  "LOW",
    ANSOFF_MARKET_DEVELOPMENT:  "MEDIUM",
    ANSOFF_PRODUCT_DEVELOPMENT: "MEDIUM",
    ANSOFF_DIVERSIFICATION:     "HIGH",
}

# Time horizons per Ansoff (months)
TIME_HORIZON_MONTHS = {
    ANSOFF_MARKET_PENETRATION:  12,
    ANSOFF_MARKET_DEVELOPMENT:  24,
    ANSOFF_PRODUCT_DEVELOPMENT: 18,
    ANSOFF_DIVERSIFICATION:     36,
}

# Risk-adjusted score weights for ai_recommend_option fallback
WEIGHT_SWOT_FIT = 0.40
WEIGHT_RISK_INVERSE = 0.20      # lower risk → higher score
WEIGHT_TIME_INVERSE = 0.20      # shorter horizon → higher score
WEIGHT_VISION_ALIGNMENT = 0.20

# Risk numeric mapping (lower = better)
RISK_NUMERIC = {"LOW": 1.0, "MEDIUM": 2.0, "HIGH": 3.0}


# ════════════════════════════════════════════════════════════════════
# StrategicOptionsGenerator
# ════════════════════════════════════════════════════════════════════

class StrategicOptionsGenerator:
    """Generate and evaluate strategic alternatives.

    Consumes SWOT output from StrategyFormulationEngine (ENH-141) and
    a vision statement; produces:

    - 4 Ansoff-Matrix options with impact estimates and key initiatives
    - AI-recommended option (rule-based fallback when no LLM injected)
    - Comparison matrix across the 4 options

    Caller pattern:

        from utils.strategy_formulation import StrategyFormulationEngine
        from utils.strategic_options import StrategicOptionsGenerator

        swot = StrategyFormulationEngine().generate_swot()
        vision = "Lead through digital transformation and customer-centric banking"
        opts = StrategicOptionsGenerator().generate_options(vision, swot)
    """

    def __init__(self,
                 ai_recommender_fn: Optional[
                     Callable[[List[Dict], str], Dict]] = None):
        """
        Args:
            ai_recommender_fn: optional callable receiving
                (options_list, vision_str) and returning a dict
                {recommended_option_name, confidence, rationale}.
                When None, falls back to multi-criteria scoring.
        """
        self.ai_recommender_fn = ai_recommender_fn

    # ── Main API ──

    def generate_options(self,
                         vision: str,
                         swot_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate strategic options based on vision and SWOT.

        Args:
            vision: free-text vision statement
            swot_analysis: dict with structure produced by
                StrategyFormulationEngine.generate_swot() — must contain
                at least swot.strengths, swot.weaknesses,
                swot.opportunities, swot.threats keys (each a list).

        Returns:
            {
              "options":            [...4 option dicts...],
              "ai_recommendation":  {...},
              "comparison_matrix":  [...rows...],
              "generated_at":       ISO-8601,
              "basis":              "rule_based" | "llm",
              "vision_used":        str,
              "swot_summary":       {n_strengths, n_weaknesses, ...}
            }
        """
        # Normalize SWOT input
        swot = swot_analysis.get("swot", swot_analysis) or {}
        strengths = swot.get("strengths", []) or []
        weaknesses = swot.get("weaknesses", []) or []
        opportunities = swot.get("opportunities", []) or []
        threats = swot.get("threats", []) or []

        # Build the 4 options
        options = [
            self._build_market_penetration(strengths, weaknesses,
                                           opportunities, threats),
            self._build_market_development(strengths, weaknesses,
                                           opportunities, threats),
            self._build_product_development(strengths, weaknesses,
                                            opportunities, threats),
            self._build_diversification(strengths, weaknesses,
                                        opportunities, threats),
        ]

        # Recommend
        if self.ai_recommender_fn is not None:
            try:
                ai_rec = self.ai_recommender_fn(options, vision)
                ai_rec.setdefault("basis", "llm")
            except Exception as e:
                logger.warning(
                    f"ai_recommender_fn raised {type(e).__name__}: {e}; "
                    f"falling back to rule-based")
                ai_rec = self._rule_based_recommend(options, vision)
        else:
            ai_rec = self._rule_based_recommend(options, vision)

        return {
            "options":           options,
            "ai_recommendation": ai_rec,
            "comparison_matrix": self.build_comparison_matrix(options),
            "generated_at":      datetime.now(timezone.utc).isoformat(),
            "basis":             ai_rec.get("basis", "rule_based"),
            "vision_used":       vision,
            "swot_summary":      {
                "n_strengths":     len(strengths),
                "n_weaknesses":    len(weaknesses),
                "n_opportunities": len(opportunities),
                "n_threats":       len(threats),
            },
        }

    # ── Option builders ──

    def _build_market_penetration(self, s, w, o, t) -> Dict[str, Any]:
        return {
            "name":        "Market Penetration",
            "ansoff_type": ANSOFF_MARKET_PENETRATION,
            "description":
                "Grow market share with existing products in existing "
                "markets. Lowest risk; tactical wins on existing book.",
            "key_initiatives": [
                "Increase sales force effectiveness (RM productivity)",
                "Enhance customer loyalty programs",
                "Competitive pricing adjustments on core products",
                "Cross-sell deepening (products-per-customer ratio)",
            ],
            "swot_evidence": {
                "leverages_strengths": [item.get("factor")
                                        for item in s[:3]],
                "addresses_weaknesses": [],
                "captures_opportunities": [],
                "mitigates_threats":
                    [item.get("competitor") for item in t
                     if item.get("response_required") == "Immediate"],
            },
            "expected_impact": self.model_impact(
                ANSOFF_MARKET_PENETRATION, s, w, o, t),
            "risk_level":      RISK_LEVEL[ANSOFF_MARKET_PENETRATION],
            "time_horizon_months": TIME_HORIZON_MONTHS[
                ANSOFF_MARKET_PENETRATION],
            "time_horizon":    f"{TIME_HORIZON_MONTHS[ANSOFF_MARKET_PENETRATION]} months",
            "feasibility_note":
                "Always feasible — uses existing distribution + products."
                if s else
                "Reduced feasibility — internal strengths data is "
                "missing; verify SWOT inputs.",
        }

    def _build_market_development(self, s, w, o, t) -> Dict[str, Any]:
        return {
            "name":        "Market Development",
            "ansoff_type": ANSOFF_MARKET_DEVELOPMENT,
            "description":
                "Enter new geographic regions or customer segments "
                "with existing products. Medium risk.",
            "key_initiatives": [
                "Expand to new regions (geographic)",
                "Target new customer segments (Diaspora, Women, Youth)",
                "Develop channel partnerships (agency banking expansion)",
                "Partner-distributed offering (white-label arrangements)",
            ],
            "swot_evidence": {
                "leverages_strengths": [item.get("factor")
                                        for item in s[:2]],
                "addresses_weaknesses": [],
                "captures_opportunities":
                    [item.get("trend") for item in o
                     if item.get("strategic_fit", 0) > 0.7][:3],
                "mitigates_threats": [],
            },
            "expected_impact": self.model_impact(
                ANSOFF_MARKET_DEVELOPMENT, s, w, o, t),
            "risk_level":      RISK_LEVEL[ANSOFF_MARKET_DEVELOPMENT],
            "time_horizon_months": TIME_HORIZON_MONTHS[
                ANSOFF_MARKET_DEVELOPMENT],
            "time_horizon":    f"{TIME_HORIZON_MONTHS[ANSOFF_MARKET_DEVELOPMENT]} months",
            "feasibility_note":
                "Recommended when external opportunities present."
                if o else
                "Reduced viability — no high-relevance external "
                "opportunities identified in SWOT.",
        }

    def _build_product_development(self, s, w, o, t) -> Dict[str, Any]:
        return {
            "name":        "Product Development",
            "ansoff_type": ANSOFF_PRODUCT_DEVELOPMENT,
            "description":
                "Launch new products for existing customers. Medium "
                "risk; high upside if R&D capability is mature.",
            "key_initiatives": [
                "Digital lending platform (instant micro-loans)",
                "Wealth management products for affluent segment",
                "Embedded finance APIs for fintech partners",
                "ESG-linked products (green deposits, transition loans)",
            ],
            "swot_evidence": {
                "leverages_strengths": [item.get("factor")
                                        for item in s[:2]],
                "addresses_weaknesses":
                    [item.get("factor") for item in w
                     if "Customer" in str(item.get("factor", ""))
                     or "Process" in str(item.get("factor", ""))],
                "captures_opportunities": [],
                "mitigates_threats":
                    [item.get("competitor") for item in t][:2],
            },
            "expected_impact": self.model_impact(
                ANSOFF_PRODUCT_DEVELOPMENT, s, w, o, t),
            "risk_level":      RISK_LEVEL[ANSOFF_PRODUCT_DEVELOPMENT],
            "time_horizon_months": TIME_HORIZON_MONTHS[
                ANSOFF_PRODUCT_DEVELOPMENT],
            "time_horizon":    f"{TIME_HORIZON_MONTHS[ANSOFF_PRODUCT_DEVELOPMENT]} months",
            "feasibility_note":
                "Recommended when internal capabilities are strong."
                if s else
                "Reduced feasibility — limited evidence of internal "
                "capability strengths in SWOT.",
        }

    def _build_diversification(self, s, w, o, t) -> Dict[str, Any]:
        return {
            "name":        "Diversification",
            "ansoff_type": ANSOFF_DIVERSIFICATION,
            "description":
                "Enter new markets with new products. Highest risk; "
                "transformational upside; typically requires M&A or "
                "joint venture.",
            "key_initiatives": [
                "Acquisition or strategic partnership",
                "Greenfield expansion to new geographies",
                "New business line launch (e.g., Bancassurance subsidiary)",
                "Platform-as-a-service offering for non-bank operators",
            ],
            "swot_evidence": {
                "leverages_strengths": [item.get("factor")
                                        for item in s[:1]],
                "addresses_weaknesses": [],
                "captures_opportunities":
                    [item.get("trend") for item in o
                     if item.get("growth_rate", 0) > 20][:2],
                "mitigates_threats":
                    [item.get("competitor") for item in t
                     if item.get("response_required") == "Immediate"],
            },
            "expected_impact": self.model_impact(
                ANSOFF_DIVERSIFICATION, s, w, o, t),
            "risk_level":      RISK_LEVEL[ANSOFF_DIVERSIFICATION],
            "time_horizon_months": TIME_HORIZON_MONTHS[
                ANSOFF_DIVERSIFICATION],
            "time_horizon":    f"{TIME_HORIZON_MONTHS[ANSOFF_DIVERSIFICATION]} months",
            "feasibility_note":
                "High capital + capability requirement — viable only "
                "with strong balance sheet and proven execution track "
                "record. Validate against capital ratios first.",
        }

    # ── Impact modeling (deterministic) ──

    def model_impact(self,
                     option_type: str,
                     strengths: List[Dict],
                     weaknesses: List[Dict],
                     opportunities: List[Dict],
                     threats: List[Dict]) -> Dict[str, Any]:
        """Deterministic impact estimation based on SWOT density.

        Returns a dict with:
        - revenue_uplift_score: 0-100 (relative; not absolute KES)
        - cost_pressure_score: 0-100 (higher = more cost pressure)
        - risk_exposure_score: 0-100 (higher = more risk)
        - confidence: "low" | "medium" | "high" based on input coverage
        - notes: list of explanatory bullets

        These scores are DELIBERATELY relative (not in KES) because
        absolute revenue projections from SWOT alone would be misleading.
        Banks needing absolute projections must combine these scores
        with their financial planning model (out of scope for ENH-142).
        """
        # Base scores per Ansoff archetype (industry-typical)
        base_revenue = {
            ANSOFF_MARKET_PENETRATION:  35,
            ANSOFF_MARKET_DEVELOPMENT:  55,
            ANSOFF_PRODUCT_DEVELOPMENT: 60,
            ANSOFF_DIVERSIFICATION:     75,
        }[option_type]
        base_cost_pressure = {
            ANSOFF_MARKET_PENETRATION:  20,
            ANSOFF_MARKET_DEVELOPMENT:  45,
            ANSOFF_PRODUCT_DEVELOPMENT: 50,
            ANSOFF_DIVERSIFICATION:     80,
        }[option_type]
        base_risk = {
            ANSOFF_MARKET_PENETRATION:  20,
            ANSOFF_MARKET_DEVELOPMENT:  40,
            ANSOFF_PRODUCT_DEVELOPMENT: 50,
            ANSOFF_DIVERSIFICATION:     85,
        }[option_type]

        # Adjustments based on SWOT density
        adjusted_revenue = base_revenue + len(strengths) * 3 \
            + len(opportunities) * 4
        adjusted_cost = base_cost_pressure + len(weaknesses) * 2
        adjusted_risk = base_risk + len(threats) * 3 + len(weaknesses) * 2

        # Cap scores at 100
        adjusted_revenue = min(adjusted_revenue, 100)
        adjusted_cost = min(adjusted_cost, 100)
        adjusted_risk = min(adjusted_risk, 100)

        # Confidence — how much SWOT data supports this estimate
        total_swot = (len(strengths) + len(weaknesses)
                      + len(opportunities) + len(threats))
        if total_swot >= 6:
            confidence = "high"
        elif total_swot >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        notes = [
            f"Base archetype scores: revenue={base_revenue}, "
            f"cost_pressure={base_cost_pressure}, risk={base_risk}",
            f"SWOT density adjustment: +{len(strengths)*3} revenue from "
            f"strengths, +{len(opportunities)*4} from opportunities",
            f"SWOT density adjustment: +{len(threats)*3} risk from threats, "
            f"+{len(weaknesses)*2} from weaknesses",
        ]
        if total_swot < 3:
            notes.append(
                "WARNING: very thin SWOT input — confidence is LOW. "
                "Populate more data sources (bsc_scores, "
                "tier1_benchmarking, competitor_data) before relying on "
                "these scores for board decisions.")

        return {
            "revenue_uplift_score":  adjusted_revenue,
            "cost_pressure_score":   adjusted_cost,
            "risk_exposure_score":   adjusted_risk,
            "net_value_score":       adjusted_revenue - adjusted_cost / 2
                                       - adjusted_risk / 2,
            "confidence":            confidence,
            "notes":                 notes,
        }

    # ── Recommendation (rule-based fallback) ──

    def _rule_based_recommend(self,
                              options: List[Dict],
                              vision: str) -> Dict[str, Any]:
        """Multi-criteria scoring → highest-scoring option recommended."""
        vision_lower = (vision or "").lower()

        scored_options = []
        for opt in options:
            impact = opt["expected_impact"]
            risk_num = RISK_NUMERIC[opt["risk_level"]]
            time_months = opt["time_horizon_months"]

            # Components
            swot_fit = impact["net_value_score"]   # already 0-100ish
            risk_score = (4.0 - risk_num) * 25.0   # invert: LOW=75, HIGH=25
            time_score = max(0, (48 - time_months) / 48 * 100)  # 0-100
            vision_alignment = self._vision_alignment_score(
                opt, vision_lower)

            total = (
                swot_fit * WEIGHT_SWOT_FIT
                + risk_score * WEIGHT_RISK_INVERSE
                + time_score * WEIGHT_TIME_INVERSE
                + vision_alignment * WEIGHT_VISION_ALIGNMENT
            )

            scored_options.append({
                "option_name":      opt["name"],
                "ansoff_type":      opt["ansoff_type"],
                "total_score":      round(total, 2),
                "components": {
                    "swot_fit":         round(swot_fit, 2),
                    "risk_score":       round(risk_score, 2),
                    "time_score":       round(time_score, 2),
                    "vision_alignment": round(vision_alignment, 2),
                },
            })
        scored_options.sort(key=lambda x: -x["total_score"])

        winner = scored_options[0]
        return {
            "recommended_option": winner["option_name"],
            "ansoff_type":        winner["ansoff_type"],
            "total_score":        winner["total_score"],
            "rationale": (
                f"Highest combined score across SWOT-fit "
                f"(weight {WEIGHT_SWOT_FIT}), risk-inverse "
                f"({WEIGHT_RISK_INVERSE}), time-inverse "
                f"({WEIGHT_TIME_INVERSE}), and vision-alignment "
                f"({WEIGHT_VISION_ALIGNMENT}). "
                f"Components: {winner['components']}."
            ),
            "all_scores":         scored_options,
            "basis":              "rule_based",
            "fallback_reason":
                "No ai_recommender_fn injected; using deterministic "
                "multi-criteria scoring.",
        }

    # Vision-keyword alignment (rule-based)
    OPTION_KEYWORD_MAP = {
        ANSOFF_MARKET_PENETRATION:
            ("share", "growth", "loyalty", "deepen", "penetration"),
        ANSOFF_MARKET_DEVELOPMENT:
            ("expansion", "new market", "diaspora", "regional",
             "geographic", "segment"),
        ANSOFF_PRODUCT_DEVELOPMENT:
            ("digital", "innovation", "new product", "platform",
             "wealth", "embedded", "fintech"),
        ANSOFF_DIVERSIFICATION:
            ("transform", "acquisition", "merger", "diversification",
             "new business", "joint venture"),
    }

    def _vision_alignment_score(self,
                                option: Dict[str, Any],
                                vision_lower: str) -> float:
        """0-100 score based on vision keyword density for option type."""
        keywords = self.OPTION_KEYWORD_MAP.get(option["ansoff_type"], ())
        if not vision_lower or not keywords:
            return 0.0
        hits = sum(1 for kw in keywords if kw in vision_lower)
        return min(100.0, hits * 25.0)   # 4 hits → 100

    # ── Comparison matrix ──

    def build_comparison_matrix(
            self, options: List[Dict]) -> List[Dict[str, Any]]:
        """Side-by-side comparison rows — one row per criterion."""
        if not options:
            return []
        rows = [
            {"criterion": "Risk Level",
             **{opt["name"]: opt["risk_level"] for opt in options}},
            {"criterion": "Time Horizon",
             **{opt["name"]: opt["time_horizon"] for opt in options}},
            {"criterion": "Revenue Uplift Score (0-100)",
             **{opt["name"]: opt["expected_impact"]["revenue_uplift_score"]
                for opt in options}},
            {"criterion": "Cost Pressure Score (0-100)",
             **{opt["name"]: opt["expected_impact"]["cost_pressure_score"]
                for opt in options}},
            {"criterion": "Risk Exposure Score (0-100)",
             **{opt["name"]: opt["expected_impact"]["risk_exposure_score"]
                for opt in options}},
            {"criterion": "Net Value Score",
             **{opt["name"]:
                round(opt["expected_impact"]["net_value_score"], 1)
                for opt in options}},
            {"criterion": "Confidence",
             **{opt["name"]: opt["expected_impact"]["confidence"]
                for opt in options}},
            {"criterion": "Key Initiatives (count)",
             **{opt["name"]: len(opt["key_initiatives"])
                for opt in options}},
        ]
        return rows


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper for cockpit / API use
# ════════════════════════════════════════════════════════════════════

def generate_options(vision: str,
                     swot_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper — instantiate generator and run once."""
    return StrategicOptionsGenerator().generate_options(vision, swot_analysis)

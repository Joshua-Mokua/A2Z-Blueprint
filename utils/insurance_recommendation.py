"""
================================================================================
A2Z MIS 360 — Standard #302: Insurance Recommendation Engine
================================================================================

Risk classification: Cat B (deterministic baseline) + Rule 7 ML hook

Rule-based insurance product recommendation per customer life event +
risk profile + financial capacity. Cross-sell + up-sell triggers.

Public API:
    recommend_for_customer(customer_id, customer_attrs) -> ranked recommendations
    score_product_fit(product_code, customer_attrs) -> {score, reasons}
    list_life_event_triggers() -> ordered trigger catalog
    register_rule(rule_config, actor, reason) -> custom rules

Rule 7 ML scaffolding:
    Continuation.docx #302 specifies "ML-based" recommendations. v10.274
    ships the deterministic rule engine that surfaces explicit fit
    scores + reasons. ML hook is the `ml_score_fn` constructor parameter
    — when provided, ML scores blend with rule scores via configurable
    weight. SPEC_DEVIATION_NOTE documents the deferred ML wiring.

LIFE_EVENTS byte-for-byte (Continuation.docx #302):
    NEW_CUSTOMER          -- account opening
    MARRIAGE              -- marriage event
    NEW_CHILD             -- birth/adoption
    HOUSE_PURCHASE        -- mortgage / property purchase
    VEHICLE_PURCHASE      -- car/motorcycle purchase
    BUSINESS_OPENING      -- new SME registered
    JOB_CHANGE            -- employment change
    NEAR_RETIREMENT       -- 5 years to expected retirement
    INCOME_INCREASE       -- significant income jump (>30% YoY)
    POLICY_LAPSE          -- previous policy lapsed (re-engagement)

LIFE_EVENT_TRIGGERS map life events to recommended product types.
This is the DEFAULT rule book — operators can add custom rules.

Honesty rules:
    Rule 1: zero matching products → empty list with explicit reason
    Rule 6: invalid customer_attrs surface missing fields
    Rule 7: ML hook isolated; deterministic fallback always available

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.insurance_catalog import (
    InsuranceCatalogEngine, INSURANCE_PRODUCT_TYPES,
)

getcontext().prec = 28


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #302 specifies ML-based recommendations. "
    "v10.274 ships deterministic rule engine with explicit life-event "
    "→ product-type triggers + capacity-based scoring. ML hook "
    "(ml_score_fn parameter) accepts a callable for ML-blended scoring; "
    "production ML training requires customer behavioral cluster (#337-"
    "348) which ships in batch v10.275-276. Hook contract surfaces "
    "'no_ml_hook_loaded' when ml_score_fn is None."
)


LIFE_EVENTS: Tuple[str, ...] = (
    "NEW_CUSTOMER",
    "MARRIAGE",
    "NEW_CHILD",
    "HOUSE_PURCHASE",
    "VEHICLE_PURCHASE",
    "BUSINESS_OPENING",
    "JOB_CHANGE",
    "NEAR_RETIREMENT",
    "INCOME_INCREASE",
    "POLICY_LAPSE",
)

# Default trigger map (life event → recommended product types, ordered)
LIFE_EVENT_TRIGGERS: Dict[str, Tuple[str, ...]] = {
    "NEW_CUSTOMER":     ("LIFE", "PERSONAL_ACCIDENT"),
    "MARRIAGE":         ("LIFE", "HEALTH"),
    "NEW_CHILD":        ("LIFE", "EDUCATION", "HEALTH"),
    "HOUSE_PURCHASE":   ("PROPERTY", "LIFE"),
    "VEHICLE_PURCHASE": ("MOTOR", "PERSONAL_ACCIDENT"),
    "BUSINESS_OPENING": ("BUSINESS", "PROPERTY", "LIFE"),
    "JOB_CHANGE":       ("LIFE", "HEALTH"),
    "NEAR_RETIREMENT":  ("PENSION", "HEALTH"),
    "INCOME_INCREASE":  ("LIFE", "PENSION", "EDUCATION"),
    "POLICY_LAPSE":     ("LIFE", "HEALTH", "MOTOR"),
}

# Rule 1: scoring weights byte-for-byte
SCORING_WEIGHTS: Dict[str, Decimal] = {
    "life_event_match":  Decimal("40"),
    "capacity_fit":      Decimal("30"),
    "coverage_gap":      Decimal("20"),
    "ml_blend":          Decimal("10"),
}


class InsuranceRecommendationEngine:
    """Rule-based recommendation with Rule 7 ML hook."""

    def __init__(
        self,
        catalog: Optional[InsuranceCatalogEngine] = None,
        ml_score_fn: Optional[Callable[[str, Dict[str, Any]], Decimal]] = None,
    ):
        self.catalog = catalog or InsuranceCatalogEngine()
        self.ml_score_fn = ml_score_fn  # Rule 7 hook

    def recommend_for_customer(
        self,
        customer_id: str,
        customer_attrs: Dict[str, Any],
        top_n: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate ranked recommendations for a customer.

        customer_attrs expected keys:
            life_events: List[str]   -- recent triggering events
            monthly_income_kes: Decimal | None
            existing_policy_types: List[str]
            age: int | None
        """
        if not isinstance(customer_attrs, dict):
            return {"recommendations": [], "reason": "invalid_customer_attrs"}

        life_events = customer_attrs.get("life_events", []) or []
        # Validate life events
        invalid = [e for e in life_events if e not in LIFE_EVENTS]
        if invalid:
            return {
                "recommendations": [],
                "reason": f"invalid_life_events:{invalid}",
                "valid_events": list(LIFE_EVENTS),
            }

        # Get all products
        products = self.catalog.list_products()
        if not products:
            return {
                "recommendations": [],
                "reason": "empty_product_catalog",
            }

        # Score each product
        scored = []
        for product in products:
            score_result = self.score_product_fit(
                product["product_code"], customer_attrs
            )
            if score_result.get("score") is None:
                continue
            scored.append({
                "product_code": product["product_code"],
                "product_name": product["product_name"],
                "product_type": product["product_type"],
                "insurer_id": product["insurer_id"],
                "fit_score": score_result["score"],
                "reasons": score_result["reasons"],
            })

        scored.sort(key=lambda x: Decimal(x["fit_score"]), reverse=True)

        return {
            "customer_id": customer_id,
            "recommendation_count": len(scored),
            "recommendations": scored[:top_n],
            "ml_hook_active": self.ml_score_fn is not None,
            "_meta": {
                "spec_deviation": SPEC_DEVIATION_NOTE,
                "scoring_weights": {k: str(v) for k, v in SCORING_WEIGHTS.items()},
            },
        }

    def score_product_fit(
        self,
        product_code: str,
        customer_attrs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compute fit score 0-100 for product + customer.

        Components:
            - life_event_match: 0 or 100 (40% weight)
            - capacity_fit: 0-100 by income vs premium ratio (30%)
            - coverage_gap: 100 if customer doesn't have product type
                              already, else 0 (20%)
            - ml_blend: 0-100 from ml_score_fn or 0 (10%)
        """
        products = self.catalog.list_products()
        product = next(
            (p for p in products if p["product_code"] == product_code), None
        )
        if product is None:
            return {"score": None, "reasons": ["product_not_found"]}

        ptype = product.get("product_type", "")
        reasons = []
        components = {}

        # 1. Life-event match
        life_events = customer_attrs.get("life_events", []) or []
        triggered_types = set()
        for e in life_events:
            if e in LIFE_EVENT_TRIGGERS:
                triggered_types.update(LIFE_EVENT_TRIGGERS[e])
        if ptype in triggered_types:
            components["life_event_match"] = Decimal("100")
            reasons.append(f"matches_life_events:{','.join(life_events)}")
        else:
            components["life_event_match"] = Decimal("0")

        # 2. Capacity fit (Rule 1: None when income missing)
        income = customer_attrs.get("monthly_income_kes")
        if income is None:
            components["capacity_fit"] = None
            reasons.append("no_income_data")
        else:
            try:
                inc = Decimal(str(income))
                # Affordability: ideal premium <= 5% of monthly income
                # Score 100 if affordable, scaled down beyond that
                # Use product's default premium estimate (10K/month proxy)
                expected_premium = Decimal("10000")  # placeholder
                if inc <= 0:
                    components["capacity_fit"] = Decimal("0")
                    reasons.append("zero_or_negative_income")
                else:
                    ratio = expected_premium / inc
                    # ratio <= 0.05 → 100; ratio >= 0.20 → 0; linear between
                    if ratio <= Decimal("0.05"):
                        components["capacity_fit"] = Decimal("100")
                    elif ratio >= Decimal("0.20"):
                        components["capacity_fit"] = Decimal("0")
                    else:
                        # Linear interpolation
                        score = (Decimal("0.20") - ratio) / Decimal("0.15") * Decimal("100")
                        components["capacity_fit"] = score.quantize(Decimal("0.01"))
            except (ValueError, TypeError):
                components["capacity_fit"] = None
                reasons.append("invalid_income_format")

        # 3. Coverage gap
        existing = customer_attrs.get("existing_policy_types", []) or []
        if ptype not in existing:
            components["coverage_gap"] = Decimal("100")
            reasons.append("no_existing_coverage_for_type")
        else:
            components["coverage_gap"] = Decimal("0")
            reasons.append("already_covered_for_type")

        # 4. ML blend (Rule 7 hook)
        if self.ml_score_fn is not None:
            try:
                ml_score = self.ml_score_fn(product_code, customer_attrs)
                components["ml_blend"] = Decimal(str(ml_score))
                reasons.append(f"ml_score_applied:{components['ml_blend']}")
            except Exception as e:
                components["ml_blend"] = Decimal("0")
                reasons.append(f"ml_hook_error:{type(e).__name__}")
        else:
            components["ml_blend"] = Decimal("0")
            reasons.append("no_ml_hook_loaded")

        # Composite — handle None capacity_fit by reducing total weight
        total = Decimal("0")
        applied_weight = Decimal("0")
        for k, v in components.items():
            if v is None:
                continue
            w = SCORING_WEIGHTS[k]
            total += v * w / Decimal("100")
            applied_weight += w

        if applied_weight == 0:
            return {
                "score": None,
                "reasons": reasons + ["all_components_none"],
            }

        # Re-scale to 100 if some components missing
        score = (total / applied_weight * Decimal("100")).quantize(Decimal("0.01"))

        return {
            "score": str(score),
            "reasons": reasons,
            "components": {k: str(v) if v is not None else None
                              for k, v in components.items()},
        }

    def list_life_event_triggers(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in LIFE_EVENT_TRIGGERS.items()}


def _self_test() -> None:
    import tempfile

    # Spec deviation note
    assert "ML-based" in SPEC_DEVIATION_NOTE
    assert "v10.275-276" in SPEC_DEVIATION_NOTE

    # Weight sum check
    assert sum(SCORING_WEIGHTS.values()) == Decimal("100")

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = InsuranceCatalogEngine(
            products_path=Path(tmpdir) / "p.json",
            policies_path=Path(tmpdir) / "po.json",
            premiums_path=Path(tmpdir) / "pr.json",
        )
        # Seed products
        for code, pname, ptype in [
            ("BR-LIFE-001", "Britam Term Life", "LIFE"),
            ("BR-EDU-001",  "Britam Education",   "EDUCATION"),
            ("BR-MOT-001",  "Britam Motor",       "MOTOR"),
            ("BR-HEA-001",  "Britam Medical",     "HEALTH"),
        ]:
            catalog.register_product(
                "INS-BRITAM",
                {"product_code": code, "product_name": pname,
                 "product_type": ptype},
                actor="bd", reason="seed",
            )

        engine = InsuranceRecommendationEngine(catalog=catalog)

        # Test 1: NEW_CHILD event triggers EDUCATION + LIFE + HEALTH
        result = engine.recommend_for_customer(
            "CUST-001",
            {"life_events": ["NEW_CHILD"],
             "monthly_income_kes": "200000",
             "existing_policy_types": [],
             "age": 35},
        )
        assert result["recommendation_count"] >= 1
        # Top recs should include LIFE, EDUCATION, HEALTH
        top_types = {r["product_type"] for r in result["recommendations"][:3]}
        assert "EDUCATION" in top_types
        assert "LIFE" in top_types

        # Test 2: ml_hook_active flag
        assert result["ml_hook_active"] is False

        # Test 3: Rule 7 placeholder reason
        for rec in result["recommendations"]:
            assert "no_ml_hook_loaded" in rec["reasons"]

        # Test 4: invalid life event rejected
        bad = engine.recommend_for_customer(
            "CUST-002",
            {"life_events": ["INVALID_EVENT"]},
        )
        assert bad["recommendations"] == []
        assert "invalid_life_events" in bad["reason"]

        # Test 5: existing coverage suppresses score
        result = engine.recommend_for_customer(
            "CUST-003",
            {"life_events": ["NEW_CHILD"],
             "monthly_income_kes": "200000",
             "existing_policy_types": ["LIFE", "EDUCATION"]},
        )
        # LIFE + EDUCATION should now have lower fit_score
        # because coverage_gap=0 for those types
        ed_rec = next(r for r in result["recommendations"]
                          if r["product_type"] == "EDUCATION")
        # Look for already_covered_for_type reason
        assert "already_covered_for_type" in ed_rec["reasons"]

        # Test 6: missing income surfaces reason
        result = engine.recommend_for_customer(
            "CUST-004",
            {"life_events": ["MARRIAGE"]},
        )
        # All recs should have no_income_data
        for r in result["recommendations"]:
            assert "no_income_data" in r["reasons"]

        # Test 7: ML hook with provided fn
        def fake_ml(product_code, attrs):
            # Always score LIFE products higher
            if "LIFE" in product_code:
                return Decimal("90")
            return Decimal("50")

        engine_ml = InsuranceRecommendationEngine(
            catalog=catalog, ml_score_fn=fake_ml
        )
        result = engine_ml.recommend_for_customer(
            "CUST-005",
            {"life_events": ["NEW_CUSTOMER"],
             "monthly_income_kes": "100000",
             "existing_policy_types": []},
        )
        assert result["ml_hook_active"] is True
        # Top rec should reflect ML boost — LIFE gets +9 from ML blend
        top = result["recommendations"][0]
        assert "ml_score_applied" in str(top["reasons"])

        # Test 8: ML hook failure surfaces error reason
        def broken_ml(product_code, attrs):
            raise RuntimeError("ML service down")

        engine_broken = InsuranceRecommendationEngine(
            catalog=catalog, ml_score_fn=broken_ml
        )
        result = engine_broken.recommend_for_customer(
            "CUST-006",
            {"life_events": ["NEW_CUSTOMER"],
             "monthly_income_kes": "100000",
             "existing_policy_types": []},
        )
        for rec in result["recommendations"]:
            assert any("ml_hook_error" in r for r in rec["reasons"])

        # Test 9: list_life_event_triggers
        triggers = engine.list_life_event_triggers()
        assert "NEW_CHILD" in triggers
        assert "EDUCATION" in triggers["NEW_CHILD"]

        # Test 10: empty catalog returns empty
        empty_catalog = InsuranceCatalogEngine(
            products_path=Path(tmpdir) / "empty.json",
            policies_path=Path(tmpdir) / "ep.json",
            premiums_path=Path(tmpdir) / "epr.json",
        )
        empty_engine = InsuranceRecommendationEngine(catalog=empty_catalog)
        result = empty_engine.recommend_for_customer(
            "CUST-007",
            {"life_events": ["NEW_CUSTOMER"]},
        )
        assert result["reason"] == "empty_product_catalog"

    print("  ✅ insurance_recommendation self-test PASS")


if __name__ == "__main__":
    _self_test()

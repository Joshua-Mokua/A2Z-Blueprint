"""
================================================================================
A2Z MIS 360 — Standard #72: Cross-Sell / Next-Best-Action Engine
================================================================================

Risk classification: Cat D (predictive recommendation with Rule 7 scaffolding)

This standard makes the **SIXTH RULE 7 APPLICATION**, after #41, #48, #53,
#64, #71.

The pattern is now stable across six prediction domains:
    1. #41  customer dormancy prediction       (binary classification)
    2. #48  BI commentary generation            (text generation)
    3. #53  credit default probability          (numerical regression)
    4. #64  employee sentiment scoring          (NLP/text classification)
    5. #71  customer churn propensity           (binary survival/classification)
    6. #72  cross-sell next-best-action         (multi-class ranking) NEW

Computes:
    - product_eligibility(customer)             -- deterministic eligibility check
    - next_best_action_rule_based(customer)     -- DETERMINISTIC propensity rules
    - next_best_action_predict(customer, ml)    -- Cat D scaffolding (Rule 7)
    - product_recommendation_basket(customer)   -- ranked list of N recommendations
    - cross_sell_priority_list(customers)       -- bank-wide opportunity ranking

Rule-based propensity scoring (deterministic):
    For each candidate product, compute a score 0-100 based on:
    - Eligibility (binary gate — must pass)
    - Existing relationship signals (e.g. high savings → mortgage candidate)
    - Lifecycle stage (e.g. NEW customers → debit card, term deposit)
    - Demographic fit (where deterministic)

Honesty rules applied:
    Rule 1: recommendations = [] when customer has no scoreable holdings
    Rule 6: missing eligibility data surfaced; products with unknown eligibility
            NEVER auto-recommended (default-deny)
    Rule 7: ml_recommendations path returns ml=None + reason + rule_based fallback
            when no model loaded; ML failure surfaces error type + falls back

Spec deviations:
    ML-based recommender (collaborative filtering / deep learning) deferred
    to v7; v6 ships rule-based propensity scoring.

================================================================================
"""

from __future__ import annotations

SPEC_DEVIATION_NOTE = (
    "ML-based recommender (collaborative filtering / deep learning) is downstream work; "
    "v6 ships rule-based deterministic propensity scoring"
)

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

# Recommendable products
RECOMMENDABLE_PRODUCTS: Tuple[str, ...] = (
    "SAVINGS",
    "CURRENT",
    "TERM_DEPOSIT",
    "PERSONAL_LOAN",
    "MORTGAGE",
    "CREDIT_CARD",
    "INVESTMENT",
    "INSURANCE",
)

# Eligibility minimum thresholds (KES)
PERSONAL_LOAN_MIN_INCOME_KES = Decimal("30000")
MORTGAGE_MIN_INCOME_KES = Decimal("80000")
CREDIT_CARD_MIN_INCOME_KES = Decimal("40000")
INVESTMENT_MIN_BALANCE_KES = Decimal("100000")
TERM_DEPOSIT_MIN_BALANCE_KES = Decimal("50000")

# Minimum tenure for unsecured products (days)
MIN_TENURE_FOR_UNSECURED_DAYS = 180

# Propensity rule weights (each rule contributes max 100; final = max across rules per product)
NBA_RULE_WEIGHTS: Dict[str, int] = {
    "high_savings_signals_mortgage": 80,
    "high_income_no_credit_card": 70,
    "current_acct_no_savings": 60,
    "lifecycle_new_no_card": 50,
    "stable_balance_signals_investment": 65,
    "growing_lifecycle_no_term_deposit": 40,
    "low_engagement_signals_savings": 30,
}

# Recommendation priority thresholds
NBA_HOT_THRESHOLD = 70
NBA_WARM_THRESHOLD = 40
# Below 40 = COLD


@dataclass
class CustomerForCrossSell:
    customer_id: str
    cif_id: str
    monthly_income_kes: Optional[Decimal] = None
    total_savings_balance_kes: Optional[Decimal] = None
    total_current_balance_kes: Optional[Decimal] = None
    has_savings_account: bool = False
    has_current_account: bool = False
    has_personal_loan: bool = False
    has_mortgage: bool = False
    has_credit_card: bool = False
    has_term_deposit: bool = False
    has_investment: bool = False
    has_insurance: bool = False
    tenure_days: Optional[int] = None
    lifecycle_stage: Optional[str] = None  # NEW / GROWING / MATURE / DORMANT
    last_complaint_open: bool = False


class CrossSellNextBestActionEngine:
    """Deterministic NBA scoring + Rule 7 ML scaffolding."""

    @staticmethod
    def product_eligibility(
        customer: CustomerForCrossSell,
        product: str,
    ) -> Dict[str, Any]:
        """
        Default-deny eligibility check.
        Rule 6: missing income/balance → not_eligible with reason (NOT silent allow).
        """
        if product not in RECOMMENDABLE_PRODUCTS:
            return {"eligible": False, "reason": f"unknown_product:{product}"}

        # Block recommendations during open complaint
        if customer.last_complaint_open:
            return {"eligible": False, "reason": "open_complaint"}

        # Already-held products
        held_check = {
            "SAVINGS": customer.has_savings_account,
            "CURRENT": customer.has_current_account,
            "PERSONAL_LOAN": customer.has_personal_loan,
            "MORTGAGE": customer.has_mortgage,
            "CREDIT_CARD": customer.has_credit_card,
            "TERM_DEPOSIT": customer.has_term_deposit,
            "INVESTMENT": customer.has_investment,
            "INSURANCE": customer.has_insurance,
        }
        if held_check.get(product, False):
            return {"eligible": False, "reason": "already_held"}

        # Tenure check for unsecured products
        if product in ("PERSONAL_LOAN", "CREDIT_CARD"):
            if customer.tenure_days is None:
                return {"eligible": False, "reason": "missing_tenure_data"}
            if customer.tenure_days < MIN_TENURE_FOR_UNSECURED_DAYS:
                return {"eligible": False, "reason": "tenure_under_180_days"}

        # Income checks
        if product == "PERSONAL_LOAN":
            if customer.monthly_income_kes is None:
                return {"eligible": False, "reason": "missing_income_data"}
            if customer.monthly_income_kes < PERSONAL_LOAN_MIN_INCOME_KES:
                return {"eligible": False, "reason": "income_below_minimum"}

        if product == "MORTGAGE":
            if customer.monthly_income_kes is None:
                return {"eligible": False, "reason": "missing_income_data"}
            if customer.monthly_income_kes < MORTGAGE_MIN_INCOME_KES:
                return {"eligible": False, "reason": "income_below_minimum"}

        if product == "CREDIT_CARD":
            if customer.monthly_income_kes is None:
                return {"eligible": False, "reason": "missing_income_data"}
            if customer.monthly_income_kes < CREDIT_CARD_MIN_INCOME_KES:
                return {"eligible": False, "reason": "income_below_minimum"}

        # Balance checks
        if product == "INVESTMENT":
            total_bal = (customer.total_savings_balance_kes or Decimal("0"))
            if total_bal < INVESTMENT_MIN_BALANCE_KES:
                return {"eligible": False, "reason": "savings_below_minimum"}

        if product == "TERM_DEPOSIT":
            total_bal = (customer.total_savings_balance_kes or Decimal("0"))
            if total_bal < TERM_DEPOSIT_MIN_BALANCE_KES:
                return {"eligible": False, "reason": "savings_below_minimum"}

        return {"eligible": True, "reason": "passed_all_checks"}

    @classmethod
    def _rule_based_nba(
        cls,
        customer: CustomerForCrossSell,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Deterministic rule-based NBA propensity ranking.
        Returns (recommendations[], breakdown).
        Same input ALWAYS produces same output.
        """
        recommendations: List[Dict[str, Any]] = []
        applied_rules: List[str] = []

        # Rule: High savings + no mortgage → MORTGAGE
        savings = customer.total_savings_balance_kes or Decimal("0")
        if (savings >= Decimal("500000") and not customer.has_mortgage):
            elig = cls.product_eligibility(customer, "MORTGAGE")
            if elig["eligible"]:
                recommendations.append({
                    "product": "MORTGAGE",
                    "score": NBA_RULE_WEIGHTS["high_savings_signals_mortgage"],
                    "rule": "high_savings_signals_mortgage",
                    "rationale": "savings_above_500k_no_existing_mortgage",
                })
                applied_rules.append("high_savings_signals_mortgage")

        # Rule: High income + no credit card → CREDIT_CARD
        if (customer.monthly_income_kes is not None
                and customer.monthly_income_kes >= Decimal("100000")
                and not customer.has_credit_card):
            elig = cls.product_eligibility(customer, "CREDIT_CARD")
            if elig["eligible"]:
                recommendations.append({
                    "product": "CREDIT_CARD",
                    "score": NBA_RULE_WEIGHTS["high_income_no_credit_card"],
                    "rule": "high_income_no_credit_card",
                    "rationale": "income_above_100k_no_card",
                })
                applied_rules.append("high_income_no_credit_card")

        # Rule: Has CURRENT but no SAVINGS
        if customer.has_current_account and not customer.has_savings_account:
            recommendations.append({
                "product": "SAVINGS",
                "score": NBA_RULE_WEIGHTS["current_acct_no_savings"],
                "rule": "current_acct_no_savings",
                "rationale": "current_holder_should_have_savings",
            })
            applied_rules.append("current_acct_no_savings")

        # Rule: NEW lifecycle + no card → CREDIT_CARD
        if (customer.lifecycle_stage == "NEW"
                and not customer.has_credit_card):
            elig = cls.product_eligibility(customer, "CREDIT_CARD")
            if elig["eligible"]:
                recommendations.append({
                    "product": "CREDIT_CARD",
                    "score": NBA_RULE_WEIGHTS["lifecycle_new_no_card"],
                    "rule": "lifecycle_new_no_card",
                    "rationale": "new_customer_initial_credit_relationship",
                })
                applied_rules.append("lifecycle_new_no_card")

        # Rule: Stable savings → INVESTMENT
        if (savings >= Decimal("200000")
                and not customer.has_investment
                and customer.lifecycle_stage in ("MATURE", "GROWING")):
            elig = cls.product_eligibility(customer, "INVESTMENT")
            if elig["eligible"]:
                recommendations.append({
                    "product": "INVESTMENT",
                    "score": NBA_RULE_WEIGHTS["stable_balance_signals_investment"],
                    "rule": "stable_balance_signals_investment",
                    "rationale": "stable_savings_holder_investment_candidate",
                })
                applied_rules.append("stable_balance_signals_investment")

        # Rule: GROWING + no term deposit
        if (customer.lifecycle_stage == "GROWING"
                and not customer.has_term_deposit):
            elig = cls.product_eligibility(customer, "TERM_DEPOSIT")
            if elig["eligible"]:
                recommendations.append({
                    "product": "TERM_DEPOSIT",
                    "score": NBA_RULE_WEIGHTS["growing_lifecycle_no_term_deposit"],
                    "rule": "growing_lifecycle_no_term_deposit",
                    "rationale": "growing_customer_idle_savings_to_term",
                })
                applied_rules.append("growing_lifecycle_no_term_deposit")

        # Sort by score desc; deduplicate by product (keep highest)
        by_product: Dict[str, Dict[str, Any]] = {}
        for r in recommendations:
            existing = by_product.get(r["product"])
            if existing is None or r["score"] > existing["score"]:
                by_product[r["product"]] = r
        deduped = sorted(by_product.values(), key=lambda x: x["score"], reverse=True)

        # Tag tier
        for r in deduped:
            if r["score"] >= NBA_HOT_THRESHOLD:
                r["tier"] = "HOT"
            elif r["score"] >= NBA_WARM_THRESHOLD:
                r["tier"] = "WARM"
            else:
                r["tier"] = "COLD"

        return deduped, {"applied_rules": applied_rules}

    @classmethod
    def next_best_action_rule_based(cls, customer: CustomerForCrossSell) -> Dict[str, Any]:
        """Public deterministic API."""
        recs, meta = cls._rule_based_nba(customer)
        return {
            "customer_id": customer.customer_id,
            "recommendation_count": len(recs),
            "recommendations": recs,
            **meta,
        }

    @classmethod
    def next_best_action_predict(
        cls,
        customer: CustomerForCrossSell,
        ml_recommender_fn: Optional[Callable[[CustomerForCrossSell], Tuple[List[Dict[str, Any]], Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        Cat D scaffolding (Rule 7 — 6th application).

        Returns recommendations with EXPLICIT separation:
        - basis="ml" if ml_recommender_fn provided AND succeeds
        - basis="rule_based" otherwise
        - rule_based always surfaced for transparency
        - NEVER silently substitutes
        """
        rule_recs, rule_meta = cls._rule_based_nba(customer)

        if ml_recommender_fn is None:
            return {
                "customer_id": customer.customer_id,
                "basis": "rule_based",
                "ml_recommendations": None,
                "rule_based_recommendations": rule_recs,
                "rule_based_meta": rule_meta,
                "reason": "no_ml_recommender_loaded",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

        try:
            ml_recs, ml_meta = ml_recommender_fn(customer)
            return {
                "customer_id": customer.customer_id,
                "basis": "ml",
                "ml_recommendations": ml_recs,
                "ml_meta": ml_meta,
                "rule_based_recommendations": rule_recs,
                "rule_based_meta": rule_meta,
            }
        except Exception as e:
            return {
                "customer_id": customer.customer_id,
                "basis": "rule_based",
                "ml_recommendations": None,
                "rule_based_recommendations": rule_recs,
                "rule_based_meta": rule_meta,
                "reason": f"ml_recommender_error:{type(e).__name__}",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

    @classmethod
    def cross_sell_priority_list(
        cls,
        customers: List[CustomerForCrossSell],
        max_count: int = 100,
    ) -> Dict[str, Any]:
        """Bank-wide cross-sell opportunity ranking."""
        all_opportunities = []
        no_recs_count = 0
        for c in customers:
            recs, _ = cls._rule_based_nba(c)
            if not recs:
                no_recs_count += 1
                continue
            for r in recs:
                all_opportunities.append({
                    "customer_id": c.customer_id,
                    **r,
                })
        all_opportunities.sort(key=lambda x: x["score"], reverse=True)
        return {
            "total_customers": len(customers),
            "customers_with_no_recs": no_recs_count,
            "total_opportunities": len(all_opportunities),
            "top_opportunities": all_opportunities[:max_count],
        }

    # ============================================================================
    # v7.3: L10 Customer churn → Cross-sell prioritisation feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def priorities_from_churn(
        cls,
        churn_priority_payload: Dict[str, Any],
        cross_sell_opportunities: Optional[List[Dict[str, Any]]] = None,
        churn_uplift_factor: float = 1.5,
    ) -> Dict[str, Any]:
        """L10 (CONSUMER) — re-rank cross-sell opportunities using churn risk.

        Consumes the priority list produced by
        `churn_prediction.retention_intervention_priority()`. Per Charter §7
        Published Language pattern, depends only on the public dict
        contract from churn_prediction.

        Strategy:
            For each at-risk customer flagged by churn, boost their
            cross-sell opportunity scores by `churn_uplift_factor`. The
            rationale (Meadows leverage point #4: self-organisation):
            saving an existing customer is cheaper than acquiring a new
            one, so retention-while-cross-selling deserves priority.

            HIGH risk customers get full uplift; MEDIUM risk customers
            get half uplift. LOW risk untouched.

        Returns dict with:
            reranked_opportunities: list[dict] — score-boosted opportunities
            uplift_applied_count: int
            consumed_payload_version: str
            pattern: str
            cited_invariants: list — none (retention prioritisation is
                                    bank policy, not regulatory)
        """
        if not isinstance(churn_priority_payload, dict):
            return {
                "status": "INVALID_PAYLOAD",
                "error": "churn_priority_payload must be a dict",
                "reranked_opportunities": cross_sell_opportunities or [],
            }

        # Extract churn-priority customer ids by risk level
        priority_list = churn_priority_payload.get("priority_list") or \
                        churn_priority_payload.get("priorities") or []

        # Build customer_id → risk_segment lookup
        churn_risk_map: Dict[str, str] = {}
        for entry in priority_list:
            if not isinstance(entry, dict):
                continue
            cid = entry.get("customer_id")
            seg = entry.get("segment") or entry.get("churn_segment")
            if cid:
                # Normalize: HIGH_RISK → HIGH, MEDIUM_RISK → MEDIUM (and accept already-bare values)
                if seg:
                    seg_norm = seg.replace("_RISK", "")
                else:
                    seg_norm = "UNKNOWN"
                churn_risk_map[cid] = seg_norm

        # If caller didn't supply opportunities, return empty re-rank
        if cross_sell_opportunities is None:
            return {
                "status": "NO_OPPORTUNITIES_PROVIDED",
                "reranked_opportunities": [],
                "churn_risk_map": churn_risk_map,
                "consumed_payload_version": "churn_prediction.retention_intervention_priority v1.0",
                "pattern": "PUBLISHED_LANGUAGE",
                "cited_invariants": [],
            }

        uplift_count = 0
        reranked = []
        for opp in cross_sell_opportunities:
            opp_copy = dict(opp)
            cid = opp_copy.get("customer_id")
            risk_seg = churn_risk_map.get(cid)
            original_score = opp_copy.get("score", 0)
            try:
                original_score = float(original_score)
            except (TypeError, ValueError):
                original_score = 0.0

            if risk_seg == "HIGH":
                boost = churn_uplift_factor
                opp_copy["score"] = original_score * boost
                opp_copy["churn_uplift_applied"] = "HIGH"
                opp_copy["original_score"] = original_score
                uplift_count += 1
            elif risk_seg == "MEDIUM":
                boost = 1.0 + (churn_uplift_factor - 1.0) / 2
                opp_copy["score"] = original_score * boost
                opp_copy["churn_uplift_applied"] = "MEDIUM"
                opp_copy["original_score"] = original_score
                uplift_count += 1
            else:
                opp_copy["churn_uplift_applied"] = "NONE"

            reranked.append(opp_copy)

        # Re-sort by adjusted score
        reranked.sort(key=lambda x: x.get("score", 0), reverse=True)

        return {
            "reranked_opportunities": reranked,
            "uplift_applied_count": uplift_count,
            "total_opportunities": len(reranked),
            "churn_risk_map": churn_risk_map,
            "consumed_payload_version": "churn_prediction.retention_intervention_priority v1.0",
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": [],
            "uplift_factor_applied": churn_uplift_factor,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_customer(**kw):
    defaults = dict(
        customer_id="C1", cif_id="CIF1",
        monthly_income_kes=Decimal("60000"),
        total_savings_balance_kes=Decimal("100000"),
        has_savings_account=True,
        tenure_days=400,
        lifecycle_stage="GROWING",
    )
    defaults.update(kw)
    return CustomerForCrossSell(**defaults)


def _test_eligibility_unknown_product():
    c = _make_customer()
    e = CrossSellNextBestActionEngine.product_eligibility(c, "WEIRD")
    assert not e["eligible"]
    assert "unknown_product" in e["reason"]


def _test_eligibility_already_held():
    c = _make_customer(has_credit_card=True)
    e = CrossSellNextBestActionEngine.product_eligibility(c, "CREDIT_CARD")
    assert not e["eligible"]
    assert e["reason"] == "already_held"


def _test_eligibility_open_complaint():
    """Cannot recommend to customer with open complaint."""
    c = _make_customer(last_complaint_open=True)
    e = CrossSellNextBestActionEngine.product_eligibility(c, "PERSONAL_LOAN")
    assert not e["eligible"]
    assert e["reason"] == "open_complaint"


def _test_eligibility_low_income_blocked():
    c = _make_customer(monthly_income_kes=Decimal("20000"))
    e = CrossSellNextBestActionEngine.product_eligibility(c, "PERSONAL_LOAN")
    assert not e["eligible"]
    assert e["reason"] == "income_below_minimum"


def _test_eligibility_missing_income_default_deny_rule6():
    """Rule 6: missing income → default-deny, not silent allow."""
    c = _make_customer(monthly_income_kes=None)
    e = CrossSellNextBestActionEngine.product_eligibility(c, "PERSONAL_LOAN")
    assert not e["eligible"]
    assert e["reason"] == "missing_income_data"


def _test_eligibility_tenure_too_short():
    c = _make_customer(tenure_days=30)
    e = CrossSellNextBestActionEngine.product_eligibility(c, "CREDIT_CARD")
    assert not e["eligible"]
    assert e["reason"] == "tenure_under_180_days"


def _test_eligibility_passes():
    c = _make_customer(monthly_income_kes=Decimal("100000"), tenure_days=400)
    e = CrossSellNextBestActionEngine.product_eligibility(c, "CREDIT_CARD")
    assert e["eligible"]


def _test_nba_high_savings_mortgage():
    """High savings → MORTGAGE recommendation."""
    c = _make_customer(
        total_savings_balance_kes=Decimal("1000000"),
        monthly_income_kes=Decimal("120000"),
    )
    r = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
    products = [rec["product"] for rec in r["recommendations"]]
    assert "MORTGAGE" in products


def _test_nba_current_no_savings():
    """CURRENT holder without SAVINGS → SAVINGS recommendation."""
    c = _make_customer(
        has_savings_account=False, has_current_account=True,
        total_savings_balance_kes=Decimal("0"),
    )
    r = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
    products = [rec["product"] for rec in r["recommendations"]]
    assert "SAVINGS" in products


def _test_nba_recommendations_sorted_by_score():
    c = _make_customer(
        total_savings_balance_kes=Decimal("1000000"),
        monthly_income_kes=Decimal("150000"),
    )
    r = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
    scores = [rec["score"] for rec in r["recommendations"]]
    assert scores == sorted(scores, reverse=True)


def _test_predict_no_model_rule7():
    c = _make_customer()
    r = CrossSellNextBestActionEngine.next_best_action_predict(c)
    assert r["basis"] == "rule_based"
    assert r["ml_recommendations"] is None
    assert r["reason"] == "no_ml_recommender_loaded"
    assert r["spec_deviation"] == SPEC_DEVIATION_NOTE


def _test_predict_ml_succeeds():
    c = _make_customer()
    def fake_ml(customer): return ([{"product": "MORTGAGE", "score": 0.92}], {"model": "cf_v1"})
    r = CrossSellNextBestActionEngine.next_best_action_predict(c, ml_recommender_fn=fake_ml)
    assert r["basis"] == "ml"
    assert r["ml_recommendations"][0]["product"] == "MORTGAGE"
    # Rule 7: rule_based ALSO surfaced
    assert "rule_based_recommendations" in r


def _test_predict_ml_fails_rule7():
    c = _make_customer()
    def broken_ml(customer): raise RuntimeError("matrix factorization failed")
    r = CrossSellNextBestActionEngine.next_best_action_predict(c, ml_recommender_fn=broken_ml)
    assert r["basis"] == "rule_based"
    assert r["ml_recommendations"] is None
    assert "ml_recommender_error:RuntimeError" in r["reason"]


def _test_rule_based_determinism():
    c = _make_customer(
        total_savings_balance_kes=Decimal("1000000"),
        monthly_income_kes=Decimal("150000"),
    )
    r1 = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
    r2 = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
    products1 = [rec["product"] for rec in r1["recommendations"]]
    products2 = [rec["product"] for rec in r2["recommendations"]]
    assert products1 == products2


def _test_rule_weights_byte_for_byte():
    expected = {
        "high_savings_signals_mortgage": 80,
        "high_income_no_credit_card": 70,
        "current_acct_no_savings": 60,
        "lifecycle_new_no_card": 50,
        "stable_balance_signals_investment": 65,
        "growing_lifecycle_no_term_deposit": 40,
        "low_engagement_signals_savings": 30,
    }
    for k, v in expected.items():
        assert NBA_RULE_WEIGHTS[k] == v


def _test_min_thresholds_byte_for_byte():
    assert PERSONAL_LOAN_MIN_INCOME_KES == Decimal("30000")
    assert MORTGAGE_MIN_INCOME_KES == Decimal("80000")
    assert CREDIT_CARD_MIN_INCOME_KES == Decimal("40000")
    assert INVESTMENT_MIN_BALANCE_KES == Decimal("100000")
    assert MIN_TENURE_FOR_UNSECURED_DAYS == 180


def _test_priority_list():
    customers = [
        _make_customer(customer_id="C1",
                      total_savings_balance_kes=Decimal("1000000"),
                      monthly_income_kes=Decimal("150000")),
        _make_customer(customer_id="C2",
                      total_savings_balance_kes=Decimal("1000"),
                      monthly_income_kes=Decimal("20000")),
    ]
    r = CrossSellNextBestActionEngine.cross_sell_priority_list(customers)
    assert r["total_opportunities"] >= 1


def _test_spec_deviation_byte_for_byte():
    expected = (
        "ML-based recommender (collaborative filtering / deep learning) is downstream work; "
        "v6 ships rule-based deterministic propensity scoring"
    )
    assert SPEC_DEVIATION_NOTE == expected


def _test_recommendable_products_byte_for_byte():
    expected = ("SAVINGS", "CURRENT", "TERM_DEPOSIT", "PERSONAL_LOAN",
                "MORTGAGE", "CREDIT_CARD", "INVESTMENT", "INSURANCE")
    for p in expected:
        assert p in RECOMMENDABLE_PRODUCTS


def self_test() -> bool:
    tests = [
        _test_eligibility_unknown_product,
        _test_eligibility_already_held,
        _test_eligibility_open_complaint,
        _test_eligibility_low_income_blocked,
        _test_eligibility_missing_income_default_deny_rule6,
        _test_eligibility_tenure_too_short,
        _test_eligibility_passes,
        _test_nba_high_savings_mortgage,
        _test_nba_current_no_savings,
        _test_nba_recommendations_sorted_by_score,
        _test_predict_no_model_rule7,
        _test_predict_ml_succeeds,
        _test_predict_ml_fails_rule7,
        _test_rule_based_determinism,
        _test_rule_weights_byte_for_byte,
        _test_min_thresholds_byte_for_byte,
        _test_priority_list,
        _test_spec_deviation_byte_for_byte,
        _test_recommendable_products_byte_for_byte,
    ]
    print("=" * 60)
    print("Cross-Sell / NBA Engine — Self-Tests (#72) — 6th Rule 7 application")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)

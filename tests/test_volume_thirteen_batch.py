"""
================================================================================
A2Z MIS 360 — Volume Thirteen Batch Tests (Standards #69-#72 Customer Intelligence)
================================================================================

Tests Standards #69 Customer Segmentation, #70 Customer Lifetime Value,
#71 Churn Prediction, #72 Cross-Sell / Next-Best-Action.

Total: 65 unit tests covering RFM segmentation + value tiers, NPV-based CLV,
       Rule 7 churn scaffolding (5th application), and Rule 7 cross-sell
       scaffolding (6th application).

Run via:
    pytest tests/test_volume_thirteen_batch.py -v
================================================================================
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.customer_segmentation import (
    CustomerSegmentationEngine, CustomerRecord, CustomerTransaction,
    RFM_SEGMENTS, VALUE_TIERS,
    VALUE_TIER_HNI_MIN, VALUE_TIER_MASS_AFFLUENT_MIN, VALUE_TIER_MASS_MIN,
    LIFECYCLE_STAGES,
)
from utils.customer_lifetime_value import (
    CustomerLifetimeValueEngine, CustomerForCLV, ProductHolding,
    PRODUCT_TYPES, PRODUCT_YIELDS_PCT,
    DEFAULT_CONTRIBUTION_MARGIN_PCT, DEFAULT_DISCOUNT_RATE_PCT,
    DEFAULT_HORIZON_YEARS, DEFAULT_ANNUAL_SERVICING_COST_KES,
    CLV_HIGH_VALUE_MIN, CLV_MEDIUM_MIN,
    PROFITABILITY_SEGMENTS,
)
from utils.churn_prediction import (
    ChurnPredictionEngine, ChurnSignals,
    CHURN_HIGH_RISK_THRESHOLD, CHURN_MEDIUM_RISK_THRESHOLD, CHURN_LOW_RISK_THRESHOLD,
    CHURN_FEATURE_WEIGHTS, CHURN_SEGMENTS,
    NO_TXN_DAYS_THRESHOLD, BALANCE_DROP_PCT_THRESHOLD, COMPLAINT_OPEN_DAYS_THRESHOLD,
    SPEC_DEVIATION_NOTE as CHURN_SPEC_DEVIATION_NOTE,
)
from utils.cross_sell_nba import (
    CrossSellNextBestActionEngine, CustomerForCrossSell,
    RECOMMENDABLE_PRODUCTS, NBA_RULE_WEIGHTS,
    PERSONAL_LOAN_MIN_INCOME_KES, MORTGAGE_MIN_INCOME_KES,
    CREDIT_CARD_MIN_INCOME_KES, INVESTMENT_MIN_BALANCE_KES,
    MIN_TENURE_FOR_UNSECURED_DAYS,
    NBA_HOT_THRESHOLD, NBA_WARM_THRESHOLD,
    SPEC_DEVIATION_NOTE as NBA_SPEC_DEVIATION_NOTE,
)


# ============================================================================
# #69 Customer Segmentation (16)
# ============================================================================

def _customer(**kw):
    defaults = dict(
        customer_id="C1", cif_id="CIF1",
        onboarded_date=date(2024, 1, 1),
        total_relationship_balance_kes=Decimal("500000"),
        last_transaction_date=date(2026, 1, 1),
    )
    defaults.update(kw)
    return CustomerRecord(**defaults)


def _txn(**kw):
    defaults = dict(
        txn_id="T1", customer_id="C1",
        txn_date=date(2026, 1, 1), amount_kes=Decimal("10000"),
    )
    defaults.update(kw)
    return CustomerTransaction(**defaults)


class TestCustomerSegmentation:

    def test_rfm_segments_byte_for_byte(self):
        for s in ("CHAMPIONS", "LOYAL", "POTENTIAL_LOYALIST", "NEW_CUSTOMERS",
                  "PROMISING", "NEED_ATTENTION", "ABOUT_TO_SLEEP", "AT_RISK",
                  "CANNOT_LOSE_THEM", "HIBERNATING", "LOST"):
            assert s in RFM_SEGMENTS

    def test_value_tier_thresholds_byte_for_byte(self):
        assert VALUE_TIER_HNI_MIN == Decimal("50000000")
        assert VALUE_TIER_MASS_AFFLUENT_MIN == Decimal("5000000")
        assert VALUE_TIER_MASS_MIN == Decimal("100000")

    def test_lifecycle_stages_byte_for_byte(self):
        for s in ("NEW", "GROWING", "MATURE", "DORMANT"):
            assert s in LIFECYCLE_STAGES

    def test_rfm_unscored_rule1(self):
        r = CustomerSegmentationEngine.rfm_scores([_customer()], [], date(2026, 4, 30))
        assert r["unscored_customer_count"] == 1

    def test_rfm_segment_champions(self):
        assert CustomerSegmentationEngine.rfm_segment(5, 5, 5) == "CHAMPIONS"

    def test_rfm_segment_lost_111(self):
        """Critical: (1,1,1) → LOST, not HIBERNATING."""
        assert CustomerSegmentationEngine.rfm_segment(1, 1, 1) == "LOST"

    def test_rfm_segment_cannot_lose(self):
        """High M but low R = lapsed VIP."""
        assert CustomerSegmentationEngine.rfm_segment(1, 3, 5) == "CANNOT_LOSE_THEM"

    def test_value_tier_hni(self):
        c = _customer(total_relationship_balance_kes=Decimal("60000000"))
        r = CustomerSegmentationEngine.value_tier_assignment([c])
        assert r["tier_distribution"]["HNI"] == 1

    def test_value_tier_boundary_5m(self):
        c = _customer(total_relationship_balance_kes=VALUE_TIER_MASS_AFFLUENT_MIN)
        r = CustomerSegmentationEngine.value_tier_assignment([c])
        assert r["tier_distribution"]["MASS_AFFLUENT"] == 1

    def test_value_tier_unassigned_rule6(self):
        """Rule 6: None balance → unassigned, NOT silently bucketed."""
        c = _customer(total_relationship_balance_kes=None)
        r = CustomerSegmentationEngine.value_tier_assignment([c])
        assert r["unassigned_count"] == 1
        for tier in VALUE_TIERS:
            assert r["tier_distribution"][tier] == 0

    def test_lifecycle_new(self):
        c = _customer(onboarded_date=date(2026, 4, 1))
        r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
        assert r["stage"] == "NEW"

    def test_lifecycle_dormant_overrides(self):
        c = _customer(onboarded_date=date(2020, 1, 1),
                      last_transaction_date=date(2025, 1, 1))
        r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
        assert r["stage"] == "DORMANT"

    def test_lifecycle_mature(self):
        c = _customer(onboarded_date=date(2020, 1, 1),
                      last_transaction_date=date(2026, 4, 1))
        r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
        assert r["stage"] == "MATURE"

    def test_lifecycle_missing_onboarded_rule6(self):
        c = _customer(onboarded_date=None)
        r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
        assert r["stage"] is None
        assert r["reason"] == "missing_onboarded_date"

    def test_rfm_zero_score_lost(self):
        assert CustomerSegmentationEngine.rfm_segment(0, 5, 5) == "LOST"

    def test_value_tier_small(self):
        c = _customer(total_relationship_balance_kes=Decimal("50000"))
        r = CustomerSegmentationEngine.value_tier_assignment([c])
        assert r["tier_distribution"]["SMALL"] == 1


# ============================================================================
# #70 Customer Lifetime Value (15)
# ============================================================================

def _holding(**kw):
    defaults = dict(
        holding_id="H1", customer_id="C1",
        product_type="SAVINGS", balance_or_outstanding_kes=Decimal("100000"),
    )
    defaults.update(kw)
    return ProductHolding(**defaults)


def _customer_clv(**kw):
    defaults = dict(
        customer_id="C1", cif_id="CIF1",
        tenure_years=Decimal("3"),
        holdings=[_holding()],
    )
    defaults.update(kw)
    return CustomerForCLV(**defaults)


class TestCustomerLifetimeValue:

    def test_product_yields_byte_for_byte(self):
        expected = {
            "SAVINGS": Decimal("0.5"), "CURRENT": Decimal("3.0"),
            "TERM_DEPOSIT": Decimal("1.0"), "PERSONAL_LOAN": Decimal("12.0"),
            "MORTGAGE": Decimal("4.5"), "CREDIT_CARD": Decimal("18.0"),
            "TRADE_FINANCE": Decimal("6.0"), "INVESTMENT": Decimal("1.0"),
        }
        for k, v in expected.items():
            assert PRODUCT_YIELDS_PCT[k] == v

    def test_clv_segment_thresholds_byte_for_byte(self):
        assert CLV_HIGH_VALUE_MIN == Decimal("500000")
        assert CLV_MEDIUM_MIN == Decimal("50000")

    def test_default_horizon_byte_for_byte(self):
        assert DEFAULT_HORIZON_YEARS == 5
        assert DEFAULT_DISCOUNT_RATE_PCT == Decimal("12.0")
        assert DEFAULT_CONTRIBUTION_MARGIN_PCT == Decimal("60.0")
        assert DEFAULT_ANNUAL_SERVICING_COST_KES == Decimal("2400")

    def test_revenue_basic(self):
        h = _holding(product_type="CURRENT", balance_or_outstanding_kes=Decimal("1000000"))
        r = CustomerLifetimeValueEngine.product_revenue([h])
        assert r["total_annual_revenue_kes"] == "30000.0"

    def test_revenue_excluded_rule6(self):
        h = _holding(balance_or_outstanding_kes=None)
        r = CustomerLifetimeValueEngine.product_revenue([h])
        assert r["excluded_count"] == 1

    def test_revenue_unknown_type_excluded(self):
        h = _holding(product_type="WEIRD")
        r = CustomerLifetimeValueEngine.product_revenue([h])
        assert r["excluded_count"] == 1

    def test_clv_npv_basic(self):
        c = _customer_clv(holdings=[_holding(product_type="CURRENT",
                                              balance_or_outstanding_kes=Decimal("1000000"))])
        r = CustomerLifetimeValueEngine.clv_npv(c)
        assert r["clv_npv_kes"] is not None

    def test_clv_no_holdings_rule1(self):
        c = _customer_clv(holdings=[])
        r = CustomerLifetimeValueEngine.clv_npv(c)
        assert r["clv_npv_kes"] is None

    def test_profitability_high_value(self):
        seg = CustomerLifetimeValueEngine.profitability_segment(Decimal("750000"))
        assert seg == "HIGH_VALUE"

    def test_profitability_medium_boundary(self):
        seg = CustomerLifetimeValueEngine.profitability_segment(CLV_MEDIUM_MIN)
        assert seg == "MEDIUM"

    def test_profitability_unprofitable(self):
        seg = CustomerLifetimeValueEngine.profitability_segment(Decimal("-1000"))
        assert seg == "UNPROFITABLE"

    def test_profitability_unknown_on_none(self):
        assert CustomerLifetimeValueEngine.profitability_segment(None) == "UNKNOWN"

    def test_aggregate(self):
        customers = [_customer_clv(customer_id="C1",
                                   holdings=[_holding(product_type="CURRENT",
                                                      balance_or_outstanding_kes=Decimal("1000000"))])]
        r = CustomerLifetimeValueEngine.clv_aggregate(customers)
        assert r["scored_count"] == 1

    def test_aggregate_no_scoreable_rule1(self):
        customers = [_customer_clv(customer_id=f"C{i}", holdings=[]) for i in range(2)]
        r = CustomerLifetimeValueEngine.clv_aggregate(customers)
        assert r["total_clv_npv_kes"] is None

    def test_npv_determinism(self):
        c = _customer_clv(holdings=[_holding(product_type="CURRENT",
                                              balance_or_outstanding_kes=Decimal("1000000"))])
        r1 = CustomerLifetimeValueEngine.clv_npv(c)
        r2 = CustomerLifetimeValueEngine.clv_npv(c)
        assert r1["clv_npv_kes"] == r2["clv_npv_kes"]


# ============================================================================
# #71 Churn Prediction (15) — 5th Rule 7 application
# ============================================================================

class TestChurnPrediction:

    def test_segment_thresholds_byte_for_byte(self):
        assert CHURN_HIGH_RISK_THRESHOLD == 70
        assert CHURN_MEDIUM_RISK_THRESHOLD == 40
        assert CHURN_LOW_RISK_THRESHOLD == 20

    def test_feature_weights_byte_for_byte(self):
        expected = {
            "no_txn_60_days": 30, "balance_dropping_50pct": 20,
            "complaint_unresolved": 15, "competitor_check": 10,
            "single_product_only": 10, "csat_low": 10,
            "tenure_under_1y": 5,
        }
        for k, v in expected.items():
            assert CHURN_FEATURE_WEIGHTS[k] == v

    def test_feature_weights_sum_100(self):
        assert sum(CHURN_FEATURE_WEIGHTS.values()) == 100

    def test_trigger_thresholds_byte_for_byte(self):
        assert NO_TXN_DAYS_THRESHOLD == 60
        assert BALANCE_DROP_PCT_THRESHOLD == Decimal("50")
        assert COMPLAINT_OPEN_DAYS_THRESHOLD == 14

    def test_segments_byte_for_byte(self):
        for s in ("HIGH_RISK", "MEDIUM_RISK", "LOW_RISK", "STABLE"):
            assert s in CHURN_SEGMENTS

    def test_high_risk_classification(self):
        sig = ChurnSignals(
            customer_id="C1",
            days_since_last_txn=90, balance_drop_pct_90d=Decimal("60"),
            open_complaint_days=20, competitor_cheques_count_30d=2,
            product_holdings_count=1,
        )
        r = ChurnPredictionEngine.churn_score_rule_based(sig)
        assert r["segment"] == "HIGH_RISK"

    def test_stable_classification(self):
        sig = ChurnSignals(
            customer_id="C1", days_since_last_txn=5,
            balance_drop_pct_90d=Decimal("0"), product_holdings_count=4,
            last_csat_score=5, tenure_days=2000,
            competitor_cheques_count_30d=0,
        )
        r = ChurnPredictionEngine.churn_score_rule_based(sig)
        assert r["segment"] == "STABLE"

    def test_predict_no_model_rule7(self):
        sig = ChurnSignals(customer_id="C1", days_since_last_txn=90)
        r = ChurnPredictionEngine.churn_score_predict(sig)
        assert r["basis"] == "rule_based"
        assert r["ml_score"] is None
        assert r["reason"] == "no_ml_churn_model_loaded"
        assert "spec_deviation" in r

    def test_predict_ml_succeeds(self):
        sig = ChurnSignals(customer_id="C1")
        def fake(s): return (0.85, {"model": "rf"})
        r = ChurnPredictionEngine.churn_score_predict(sig, ml_churn_fn=fake)
        assert r["basis"] == "ml"
        assert r["ml_score"] == 0.85
        # Rule 7: rule_based ALSO surfaced
        assert "rule_based_score" in r

    def test_predict_ml_fails_rule7(self):
        sig = ChurnSignals(customer_id="C1")
        def fail(s): raise TimeoutError("down")
        r = ChurnPredictionEngine.churn_score_predict(sig, ml_churn_fn=fail)
        assert r["basis"] == "rule_based"
        assert "ml_churn_error:TimeoutError" in r["reason"]

    def test_determinism(self):
        sig = ChurnSignals(customer_id="C1", days_since_last_txn=90,
                          balance_drop_pct_90d=Decimal("60"),
                          product_holdings_count=1, last_csat_score=2)
        r1 = ChurnPredictionEngine.churn_score_rule_based(sig)
        r2 = ChurnPredictionEngine.churn_score_rule_based(sig)
        assert r1["score"] == r2["score"]

    def test_missing_signals_rule6(self):
        sig = ChurnSignals(customer_id="C1")
        r = ChurnPredictionEngine.churn_score_rule_based(sig)
        assert "days_since_last_txn" in r["missing_signals"]

    def test_intervention_priority(self):
        sigs = [
            ChurnSignals(customer_id="C1", days_since_last_txn=90,
                        balance_drop_pct_90d=Decimal("60"), product_holdings_count=1,
                        last_csat_score=2, tenure_days=100,
                        competitor_cheques_count_30d=1, open_complaint_days=20),
            ChurnSignals(customer_id="C2", days_since_last_txn=5,
                        balance_drop_pct_90d=Decimal("0"), product_holdings_count=4,
                        last_csat_score=5, tenure_days=2000,
                        competitor_cheques_count_30d=0),
        ]
        r = ChurnPredictionEngine.retention_intervention_priority(sigs)
        assert r["priority_list"][0]["customer_id"] == "C1"

    def test_intervention_low_confidence(self):
        sig = ChurnSignals(customer_id="C1")
        r = ChurnPredictionEngine.retention_intervention_priority([sig])
        assert r["low_confidence_count"] == 1

    def test_spec_deviation_byte_for_byte(self):
        expected = (
            "ML-based churn classifier (gradient boosting / neural net) is downstream work; "
            "v6 ships rule-based weighted-sum churn scoring"
        )
        assert CHURN_SPEC_DEVIATION_NOTE == expected


# ============================================================================
# #72 Cross-Sell / NBA (19) — 6th Rule 7 application
# ============================================================================

def _cust_xs(**kw):
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


class TestCrossSellNBA:

    def test_recommendable_products_byte_for_byte(self):
        for p in ("SAVINGS", "CURRENT", "TERM_DEPOSIT", "PERSONAL_LOAN",
                  "MORTGAGE", "CREDIT_CARD", "INVESTMENT", "INSURANCE"):
            assert p in RECOMMENDABLE_PRODUCTS

    def test_rule_weights_byte_for_byte(self):
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

    def test_min_thresholds_byte_for_byte(self):
        assert PERSONAL_LOAN_MIN_INCOME_KES == Decimal("30000")
        assert MORTGAGE_MIN_INCOME_KES == Decimal("80000")
        assert CREDIT_CARD_MIN_INCOME_KES == Decimal("40000")
        assert INVESTMENT_MIN_BALANCE_KES == Decimal("100000")
        assert MIN_TENURE_FOR_UNSECURED_DAYS == 180

    def test_priority_thresholds(self):
        assert NBA_HOT_THRESHOLD == 70
        assert NBA_WARM_THRESHOLD == 40

    def test_eligibility_unknown_product(self):
        e = CrossSellNextBestActionEngine.product_eligibility(_cust_xs(), "WEIRD")
        assert not e["eligible"]

    def test_eligibility_already_held(self):
        c = _cust_xs(has_credit_card=True)
        e = CrossSellNextBestActionEngine.product_eligibility(c, "CREDIT_CARD")
        assert e["reason"] == "already_held"

    def test_eligibility_open_complaint(self):
        """Cannot recommend during open complaint."""
        c = _cust_xs(last_complaint_open=True)
        e = CrossSellNextBestActionEngine.product_eligibility(c, "PERSONAL_LOAN")
        assert e["reason"] == "open_complaint"

    def test_eligibility_low_income(self):
        c = _cust_xs(monthly_income_kes=Decimal("20000"))
        e = CrossSellNextBestActionEngine.product_eligibility(c, "PERSONAL_LOAN")
        assert e["reason"] == "income_below_minimum"

    def test_eligibility_missing_income_default_deny_rule6(self):
        c = _cust_xs(monthly_income_kes=None)
        e = CrossSellNextBestActionEngine.product_eligibility(c, "PERSONAL_LOAN")
        assert not e["eligible"]
        assert e["reason"] == "missing_income_data"

    def test_eligibility_tenure_too_short(self):
        c = _cust_xs(tenure_days=30)
        e = CrossSellNextBestActionEngine.product_eligibility(c, "CREDIT_CARD")
        assert e["reason"] == "tenure_under_180_days"

    def test_eligibility_passes(self):
        c = _cust_xs(monthly_income_kes=Decimal("100000"))
        e = CrossSellNextBestActionEngine.product_eligibility(c, "CREDIT_CARD")
        assert e["eligible"]

    def test_nba_high_savings_mortgage(self):
        c = _cust_xs(total_savings_balance_kes=Decimal("1000000"),
                    monthly_income_kes=Decimal("120000"))
        r = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
        products = [rec["product"] for rec in r["recommendations"]]
        assert "MORTGAGE" in products

    def test_nba_current_no_savings(self):
        c = _cust_xs(has_savings_account=False, has_current_account=True,
                    total_savings_balance_kes=Decimal("0"))
        r = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
        products = [rec["product"] for rec in r["recommendations"]]
        assert "SAVINGS" in products

    def test_nba_sorted_by_score(self):
        c = _cust_xs(total_savings_balance_kes=Decimal("1000000"),
                    monthly_income_kes=Decimal("150000"))
        r = CrossSellNextBestActionEngine.next_best_action_rule_based(c)
        scores = [rec["score"] for rec in r["recommendations"]]
        assert scores == sorted(scores, reverse=True)

    def test_predict_no_model_rule7(self):
        r = CrossSellNextBestActionEngine.next_best_action_predict(_cust_xs())
        assert r["basis"] == "rule_based"
        assert r["ml_recommendations"] is None
        assert r["reason"] == "no_ml_recommender_loaded"

    def test_predict_ml_succeeds(self):
        def fake(c): return ([{"product": "MORTGAGE", "score": 0.9}], {})
        r = CrossSellNextBestActionEngine.next_best_action_predict(_cust_xs(), ml_recommender_fn=fake)
        assert r["basis"] == "ml"
        # Rule 7: rule_based ALSO surfaced
        assert "rule_based_recommendations" in r

    def test_predict_ml_fails_rule7(self):
        def fail(c): raise RuntimeError("oops")
        r = CrossSellNextBestActionEngine.next_best_action_predict(_cust_xs(), ml_recommender_fn=fail)
        assert r["basis"] == "rule_based"
        assert "ml_recommender_error:RuntimeError" in r["reason"]

    def test_priority_list(self):
        customers = [_cust_xs(customer_id="C1",
                              total_savings_balance_kes=Decimal("1000000"),
                              monthly_income_kes=Decimal("150000"))]
        r = CrossSellNextBestActionEngine.cross_sell_priority_list(customers)
        assert r["total_opportunities"] >= 1

    def test_spec_deviation_byte_for_byte(self):
        expected = (
            "ML-based recommender (collaborative filtering / deep learning) is downstream work; "
            "v6 ships rule-based deterministic propensity scoring"
        )
        assert NBA_SPEC_DEVIATION_NOTE == expected

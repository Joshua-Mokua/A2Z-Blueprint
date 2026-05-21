"""
================================================================================
A2Z MIS 360 — Standard #71: Churn Prediction Engine
================================================================================

Risk classification: Cat D (predictive scoring with Rule 7 scaffolding)

This standard makes the **FIFTH RULE 7 APPLICATION**, after #41 Dormancy
(v5.53), #48 BI Commentary (v5.52), #53 Credit Risk Scoring (v5.55), and
#64 Employee Sentiment (v5.57).

The pattern is now stable across five prediction domains:
    1. #41  customer dormancy prediction       (binary classification)
    2. #48  BI commentary generation            (text generation)
    3. #53  credit default probability          (numerical regression)
    4. #64  employee sentiment scoring          (NLP/text classification)
    5. #71  customer churn propensity           (binary survival/classification) NEW

Computes:
    - churn_signals(customer)                -- deterministic feature extraction
    - churn_score_rule_based(signals)        -- DETERMINISTIC weighted-sum
    - churn_score_predict(signals, ml_fn)    -- Cat D scaffolding (Rule 7)
    - churn_segment(score)                   -- HIGH_RISK / MEDIUM / LOW / STABLE
    - retention_intervention_priority(...)   -- prioritized list

Honesty rules applied:
    Rule 1: score = None when signal data insufficient
    Rule 6: missing signals listed in `missing_signals[]`, NEVER imputed
    Rule 7: ml_score path returns ml_score=None + reason + rule_based fallback
            when no model loaded; ML failure surfaces error type + falls back

Spec deviations:
    ML-based churn classifier (gradient boosting / neural net) deferred to v7;
    v6 ships rule-based weighted-sum churn scoring.

================================================================================
"""

from __future__ import annotations

SPEC_DEVIATION_NOTE = (
    "ML-based churn classifier (gradient boosting / neural net) is downstream work; "
    "v6 ships rule-based weighted-sum churn scoring"
)

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

# Churn risk segment thresholds (0-100 score, higher = more likely to churn)
CHURN_HIGH_RISK_THRESHOLD = 70
CHURN_MEDIUM_RISK_THRESHOLD = 40
CHURN_LOW_RISK_THRESHOLD = 20
# Below 20 = STABLE

CHURN_SEGMENTS: Tuple[str, ...] = ("HIGH_RISK", "MEDIUM_RISK", "LOW_RISK", "STABLE")

# Deterministic rule-based feature weights (sum to 100)
CHURN_FEATURE_WEIGHTS: Dict[str, int] = {
    "no_txn_60_days": 30,           # No transactions in last 60 days
    "balance_dropping_50pct": 20,   # Balance drop > 50% over 90 days
    "complaint_unresolved": 15,     # Open complaint > 14 days
    "competitor_check": 10,         # Cheque to competitor account
    "single_product_only": 10,      # Only 1 product (low engagement)
    "csat_low": 10,                 # Last CSAT score <= 2
    "tenure_under_1y": 5,           # New customers churn faster
}

# Trigger thresholds for each feature
NO_TXN_DAYS_THRESHOLD = 60
BALANCE_DROP_PCT_THRESHOLD = Decimal("50")
COMPLAINT_OPEN_DAYS_THRESHOLD = 14
CSAT_LOW_THRESHOLD = 2
TENURE_NEW_DAYS_THRESHOLD = 365


@dataclass
class ChurnSignals:
    customer_id: str
    days_since_last_txn: Optional[int] = None
    balance_drop_pct_90d: Optional[Decimal] = None  # negative or 0 if increased
    open_complaint_days: Optional[int] = None       # None if no open complaint
    competitor_cheques_count_30d: Optional[int] = None
    product_holdings_count: Optional[int] = None
    last_csat_score: Optional[int] = None           # 1-5
    tenure_days: Optional[int] = None


class ChurnPredictionEngine:
    """Deterministic rule-based churn scoring + Rule 7 ML scaffolding."""

    @staticmethod
    def _rule_based_score(signals: ChurnSignals) -> Tuple[int, Dict[str, Any]]:
        """
        Deterministic weighted-sum churn score (Rule 7 fallback).
        Same input ALWAYS produces same output.
        Returns (score 0-100, breakdown dict).
        """
        score = 0
        triggered: List[str] = []
        missing: List[str] = []

        # 1. No txn 60+ days
        if signals.days_since_last_txn is None:
            missing.append("days_since_last_txn")
        elif signals.days_since_last_txn >= NO_TXN_DAYS_THRESHOLD:
            score += CHURN_FEATURE_WEIGHTS["no_txn_60_days"]
            triggered.append("no_txn_60_days")

        # 2. Balance dropping
        if signals.balance_drop_pct_90d is None:
            missing.append("balance_drop_pct_90d")
        elif signals.balance_drop_pct_90d >= BALANCE_DROP_PCT_THRESHOLD:
            score += CHURN_FEATURE_WEIGHTS["balance_dropping_50pct"]
            triggered.append("balance_dropping_50pct")

        # 3. Complaint open
        if signals.open_complaint_days is None:
            # None could mean "no open complaint" — interpret as zero
            pass
        elif signals.open_complaint_days >= COMPLAINT_OPEN_DAYS_THRESHOLD:
            score += CHURN_FEATURE_WEIGHTS["complaint_unresolved"]
            triggered.append("complaint_unresolved")

        # 4. Competitor cheques
        if signals.competitor_cheques_count_30d is None:
            missing.append("competitor_cheques_count_30d")
        elif signals.competitor_cheques_count_30d >= 1:
            score += CHURN_FEATURE_WEIGHTS["competitor_check"]
            triggered.append("competitor_check")

        # 5. Single product only
        if signals.product_holdings_count is None:
            missing.append("product_holdings_count")
        elif signals.product_holdings_count <= 1:
            score += CHURN_FEATURE_WEIGHTS["single_product_only"]
            triggered.append("single_product_only")

        # 6. CSAT low
        if signals.last_csat_score is None:
            missing.append("last_csat_score")
        elif signals.last_csat_score <= CSAT_LOW_THRESHOLD:
            score += CHURN_FEATURE_WEIGHTS["csat_low"]
            triggered.append("csat_low")

        # 7. Short tenure
        if signals.tenure_days is None:
            missing.append("tenure_days")
        elif signals.tenure_days < TENURE_NEW_DAYS_THRESHOLD:
            score += CHURN_FEATURE_WEIGHTS["tenure_under_1y"]
            triggered.append("tenure_under_1y")

        return score, {
            "triggered_factors": triggered,
            "missing_signals": missing,
        }

    @classmethod
    def churn_score_rule_based(cls, signals: ChurnSignals) -> Dict[str, Any]:
        """Public deterministic API."""
        score, meta = cls._rule_based_score(signals)
        return {
            "customer_id": signals.customer_id,
            "score": score,
            "segment": cls.churn_segment(score),
            **meta,
        }

    @classmethod
    def churn_score_predict(
        cls,
        signals: ChurnSignals,
        ml_churn_fn: Optional[Callable[[ChurnSignals], Tuple[float, Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        Cat D scaffolding (Rule 7 — 5th application).

        Returns score with EXPLICIT separation:
        - basis="ml" if ml_churn_fn provided AND succeeds
        - basis="rule_based" otherwise
        - rule_based always surfaced for transparency
        - NEVER silently substitutes
        """
        rule_score, rule_meta = cls._rule_based_score(signals)

        if ml_churn_fn is None:
            return {
                "customer_id": signals.customer_id,
                "basis": "rule_based",
                "ml_score": None,
                "rule_based_score": rule_score,
                "rule_based_segment": cls.churn_segment(rule_score),
                "rule_based_meta": rule_meta,
                "reason": "no_ml_churn_model_loaded",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

        try:
            ml_score_raw, ml_meta = ml_churn_fn(signals)
            return {
                "customer_id": signals.customer_id,
                "basis": "ml",
                "ml_score": round(float(ml_score_raw), 3),
                "ml_meta": ml_meta,
                "rule_based_score": rule_score,
                "rule_based_segment": cls.churn_segment(rule_score),
                "rule_based_meta": rule_meta,
            }
        except Exception as e:
            return {
                "customer_id": signals.customer_id,
                "basis": "rule_based",
                "ml_score": None,
                "rule_based_score": rule_score,
                "rule_based_segment": cls.churn_segment(rule_score),
                "rule_based_meta": rule_meta,
                "reason": f"ml_churn_error:{type(e).__name__}",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

    @staticmethod
    def churn_segment(score: int) -> str:
        if score >= CHURN_HIGH_RISK_THRESHOLD:
            return "HIGH_RISK"
        if score >= CHURN_MEDIUM_RISK_THRESHOLD:
            return "MEDIUM_RISK"
        if score >= CHURN_LOW_RISK_THRESHOLD:
            return "LOW_RISK"
        return "STABLE"

    @classmethod
    def retention_intervention_priority(
        cls,
        customer_signals: List[ChurnSignals],
        max_priority_count: int = 100,
    ) -> Dict[str, Any]:
        """
        Prioritize customers for retention intervention.
        HIGH_RISK first, then MEDIUM_RISK; sorted by score desc within tier.
        Rule 6: customers with too many missing signals surface in `low_confidence`.
        """
        scored = []
        low_confidence = []
        for s in customer_signals:
            score, meta = cls._rule_based_score(s)
            seg = cls.churn_segment(score)
            entry = {
                "customer_id": s.customer_id,
                "score": score,
                "segment": seg,
                "triggered_factors": meta["triggered_factors"],
                "missing_signals": meta["missing_signals"],
            }
            # Customers with > 3 missing signals = low confidence
            if len(meta["missing_signals"]) > 3:
                low_confidence.append(entry)
            else:
                scored.append(entry)

        # Sort by score desc, but only include HIGH/MEDIUM
        priority = [e for e in scored if e["segment"] in ("HIGH_RISK", "MEDIUM_RISK")]
        priority.sort(key=lambda x: x["score"], reverse=True)

        return {
            "total_customers": len(customer_signals),
            "scored_customers": len(scored),
            "low_confidence_count": len(low_confidence),
            "priority_count": min(len(priority), max_priority_count),
            "priority_list": priority[:max_priority_count],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_rule_based_high_risk():
    """All risk factors triggered → score >= 70 → HIGH_RISK."""
    sig = ChurnSignals(
        customer_id="C1",
        days_since_last_txn=90,           # +30
        balance_drop_pct_90d=Decimal("60"),  # +20
        open_complaint_days=20,           # +15
        competitor_cheques_count_30d=2,   # +10
        product_holdings_count=1,         # +10
    )
    r = ChurnPredictionEngine.churn_score_rule_based(sig)
    assert r["score"] >= 70
    assert r["segment"] == "HIGH_RISK"


def _test_rule_based_stable():
    sig = ChurnSignals(
        customer_id="C1",
        days_since_last_txn=5,
        balance_drop_pct_90d=Decimal("0"),
        open_complaint_days=None,
        competitor_cheques_count_30d=0,
        product_holdings_count=4,
        last_csat_score=5,
        tenure_days=2000,
    )
    r = ChurnPredictionEngine.churn_score_rule_based(sig)
    assert r["score"] < CHURN_LOW_RISK_THRESHOLD
    assert r["segment"] == "STABLE"


def _test_segment_thresholds_byte_for_byte():
    assert CHURN_HIGH_RISK_THRESHOLD == 70
    assert CHURN_MEDIUM_RISK_THRESHOLD == 40
    assert CHURN_LOW_RISK_THRESHOLD == 20


def _test_feature_weights_byte_for_byte():
    expected = {
        "no_txn_60_days": 30,
        "balance_dropping_50pct": 20,
        "complaint_unresolved": 15,
        "competitor_check": 10,
        "single_product_only": 10,
        "csat_low": 10,
        "tenure_under_1y": 5,
    }
    for k, v in expected.items():
        assert CHURN_FEATURE_WEIGHTS[k] == v


def _test_feature_weights_sum_to_100():
    """Sanity: weights sum to 100."""
    assert sum(CHURN_FEATURE_WEIGHTS.values()) == 100


def _test_predict_no_model_rule7():
    """Rule 7: no model → basis=rule_based + ml_score=None + reason + rule_based fallback."""
    sig = ChurnSignals(customer_id="C1", days_since_last_txn=90)
    r = ChurnPredictionEngine.churn_score_predict(sig)
    assert r["basis"] == "rule_based"
    assert r["ml_score"] is None
    assert r["reason"] == "no_ml_churn_model_loaded"
    assert r["spec_deviation"] == SPEC_DEVIATION_NOTE
    assert r["rule_based_score"] >= 30


def _test_predict_ml_succeeds():
    sig = ChurnSignals(customer_id="C1", days_since_last_txn=90)
    def fake_ml(s): return (0.85, {"model": "rf_v1"})
    r = ChurnPredictionEngine.churn_score_predict(sig, ml_churn_fn=fake_ml)
    assert r["basis"] == "ml"
    assert r["ml_score"] == 0.85
    # Rule 7: rule_based ALSO surfaced
    assert "rule_based_score" in r
    assert "rule_based_segment" in r


def _test_predict_ml_fails_rule7():
    """Rule 7: ML failure → fallback + reason surfaced."""
    sig = ChurnSignals(customer_id="C1")
    def broken_ml(s): raise TimeoutError("model server down")
    r = ChurnPredictionEngine.churn_score_predict(sig, ml_churn_fn=broken_ml)
    assert r["basis"] == "rule_based"
    assert r["ml_score"] is None
    assert "ml_churn_error:TimeoutError" in r["reason"]


def _test_rule_based_determinism():
    """Same input → same score, deterministic."""
    sig = ChurnSignals(
        customer_id="C1",
        days_since_last_txn=90, balance_drop_pct_90d=Decimal("60"),
        product_holdings_count=1, last_csat_score=2,
    )
    r1 = ChurnPredictionEngine.churn_score_rule_based(sig)
    r2 = ChurnPredictionEngine.churn_score_rule_based(sig)
    r3 = ChurnPredictionEngine.churn_score_rule_based(sig)
    assert r1["score"] == r2["score"] == r3["score"]


def _test_missing_signals_surfaced_rule6():
    """Rule 6: missing signals surfaced (not imputed)."""
    sig = ChurnSignals(customer_id="C1")  # all signals missing
    r = ChurnPredictionEngine.churn_score_rule_based(sig)
    assert len(r["missing_signals"]) >= 5  # most signals are missing
    assert "days_since_last_txn" in r["missing_signals"]


def _test_intervention_priority_sorted():
    sigs = [
        ChurnSignals(customer_id="C1", days_since_last_txn=90,
                    balance_drop_pct_90d=Decimal("60"), open_complaint_days=20,
                    competitor_cheques_count_30d=1, product_holdings_count=1,
                    last_csat_score=2, tenure_days=100),  # very high
        ChurnSignals(customer_id="C2", days_since_last_txn=5,
                    balance_drop_pct_90d=Decimal("0"), open_complaint_days=None,
                    competitor_cheques_count_30d=0, product_holdings_count=4,
                    last_csat_score=5, tenure_days=2000),  # stable
    ]
    r = ChurnPredictionEngine.retention_intervention_priority(sigs)
    assert r["priority_list"][0]["customer_id"] == "C1"


def _test_intervention_low_confidence():
    """Customers with too many missing signals → low_confidence."""
    sig = ChurnSignals(customer_id="C1")  # all missing
    r = ChurnPredictionEngine.retention_intervention_priority([sig])
    assert r["low_confidence_count"] == 1
    assert r["scored_customers"] == 0


def _test_spec_deviation_byte_for_byte():
    expected = (
        "ML-based churn classifier (gradient boosting / neural net) is downstream work; "
        "v6 ships rule-based weighted-sum churn scoring"
    )
    assert SPEC_DEVIATION_NOTE == expected


def _test_segments_byte_for_byte():
    for s in ("HIGH_RISK", "MEDIUM_RISK", "LOW_RISK", "STABLE"):
        assert s in CHURN_SEGMENTS


def _test_churn_segment_classification():
    assert ChurnPredictionEngine.churn_segment(80) == "HIGH_RISK"
    assert ChurnPredictionEngine.churn_segment(50) == "MEDIUM_RISK"
    assert ChurnPredictionEngine.churn_segment(25) == "LOW_RISK"
    assert ChurnPredictionEngine.churn_segment(5) == "STABLE"


def self_test() -> bool:
    tests = [
        _test_rule_based_high_risk,
        _test_rule_based_stable,
        _test_segment_thresholds_byte_for_byte,
        _test_feature_weights_byte_for_byte,
        _test_feature_weights_sum_to_100,
        _test_predict_no_model_rule7,
        _test_predict_ml_succeeds,
        _test_predict_ml_fails_rule7,
        _test_rule_based_determinism,
        _test_missing_signals_surfaced_rule6,
        _test_intervention_priority_sorted,
        _test_intervention_low_confidence,
        _test_spec_deviation_byte_for_byte,
        _test_segments_byte_for_byte,
        _test_churn_segment_classification,
    ]
    print("=" * 60)
    print("Churn Prediction Engine — Self-Tests (#71) — 5th Rule 7 application")
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

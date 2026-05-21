"""
================================================================================
A2Z MIS 360 — Standard #64: Employee Engagement Intelligence Engine
================================================================================

Risk classification: Cat B (deterministic survey aggregation) +
                     Cat D (sentiment scoring with Rule 7 scaffolding)

This standard makes the **FOURTH RULE 7 APPLICATION**, after #41 Dormancy
(v5.53), #48 BI Commentary (v5.52), and #53 Credit Risk Scoring (v5.55).

The pattern is now stable across four prediction domains:
    1. #41  customer dormancy prediction
    2. #48  BI commentary generation
    3. #53  credit default probability
    4. #64  employee sentiment scoring (NEW)

Computes:
    - engagement_score(survey_responses)        -- deterministic 0-100 index
    - eNPS(survey_responses)                    -- employee Net Promoter Score
    - drivers_breakdown(survey_responses)       -- 6 standard drivers
    - sentiment_score(text_responses)           -- Cat D scaffolding (Rule 7)
    - flight_risk_indicators(staff_signals)     -- deterministic, not ML

Honesty rules applied:
    Rule 1: index = None when zero respondents (cannot compute average)
    Rule 6: missing/abstain responses surfaced explicitly, not silently averaged
    Rule 7: sentiment_score uses Cat D scaffolding — when no ML model, returns
            ml_sentiment=None + reason="no_ml_sentiment_model_loaded" plus a
            DETERMINISTIC keyword-based fallback. Never silently substitutes.

Spec deviations:
    LLM-based sentiment classification is downstream work; v6 ships rule-based
    keyword sentiment scoring.

================================================================================
"""

from __future__ import annotations

SPEC_DEVIATION_NOTE = (
    "ML-based sentiment classification is downstream work; "
    "v6 ships rule-based keyword sentiment scoring"
)

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# Spec literals
ENGAGEMENT_DRIVERS: Tuple[str, ...] = (
    "LEADERSHIP",
    "COMPENSATION",
    "GROWTH_DEVELOPMENT",
    "WORK_LIFE_BALANCE",
    "RECOGNITION",
    "PURPOSE_MEANING",
)

# Likert scale (5-point)
LIKERT_MIN = 1
LIKERT_MAX = 5
ENGAGEMENT_SCORE_MAX = 100

# eNPS calculation
ENPS_PROMOTER_MIN_SCORE = 9      # 9-10 are promoters
ENPS_DETRACTOR_MAX_SCORE = 6     # 0-6 are detractors

# Engagement severity bands
ENGAGEMENT_HIGH_THRESHOLD = 75
ENGAGEMENT_MODERATE_THRESHOLD = 60

# Flight risk thresholds (deterministic indicators, NOT ML)
FLIGHT_RISK_FACTOR_WEIGHTS = {
    "engagement_below_40": 30,        # low engagement
    "no_promotion_3y": 20,            # career stagnation
    "compensation_below_p25": 25,     # below-market pay
    "low_manager_rating_consecutive": 15,  # underrated
    "tenure_2_5y": 10,                # most attrition risk window
}
FLIGHT_RISK_HIGH_THRESHOLD = 60      # >=60 score = HIGH
FLIGHT_RISK_MEDIUM_THRESHOLD = 30    # 30-59 = MEDIUM

# Keyword sentiment lexicon (Rule 7 deterministic fallback)
POSITIVE_KEYWORDS = frozenset({
    "love", "great", "excellent", "amazing", "happy", "supportive",
    "growth", "opportunity", "appreciate", "fair", "innovative",
    "team", "respect", "collaborative", "rewarding",
})
NEGATIVE_KEYWORDS = frozenset({
    "hate", "terrible", "awful", "frustrated", "stressed", "burnout",
    "unfair", "toxic", "micromanage", "underpaid", "ignored",
    "discrimination", "harassment", "leaving", "quit",
})


@dataclass
class SurveyResponse:
    response_id: str
    staff_id: str
    survey_period: str  # e.g. "2025_Q4"
    overall_likert: Optional[int] = None  # 1-5
    enps_score: Optional[int] = None      # 0-10
    driver_scores: Dict[str, int] = field(default_factory=dict)  # driver -> 1-5
    text_response: Optional[str] = None
    submitted_at: Optional[str] = None


@dataclass
class StaffSignals:
    """Deterministic signals for flight risk computation."""
    staff_id: str
    engagement_score: Optional[float] = None      # 0-100
    last_promotion_years_ago: Optional[float] = None
    compensation_percentile: Optional[float] = None  # 0-100 within grade
    last_two_ratings: List[str] = field(default_factory=list)
    tenure_years: Optional[float] = None


def _normalize_likert(score: int) -> float:
    """Map Likert 1-5 -> 0-100."""
    if score < LIKERT_MIN:
        score = LIKERT_MIN
    elif score > LIKERT_MAX:
        score = LIKERT_MAX
    return ((score - LIKERT_MIN) / (LIKERT_MAX - LIKERT_MIN)) * 100


class EmployeeEngagementEngine:
    """Deterministic survey aggregation + Rule 7 sentiment scaffolding."""

    @staticmethod
    def engagement_score(responses: List[SurveyResponse]) -> Dict[str, Any]:
        """Aggregate overall engagement index. Rule 1: None when no respondents."""
        valid = [r for r in responses if r.overall_likert is not None
                 and LIKERT_MIN <= r.overall_likert <= LIKERT_MAX]
        abstained = len(responses) - len(valid)

        if not valid:
            return {
                "respondents": 0,
                "abstained": abstained,
                "score": None,
                "severity": None,
                "reason": "no_valid_respondents" if not responses else "all_abstained",
            }

        total = sum(_normalize_likert(r.overall_likert) for r in valid)
        score = total / len(valid)
        if score >= ENGAGEMENT_HIGH_THRESHOLD:
            severity = "HIGH"
        elif score >= ENGAGEMENT_MODERATE_THRESHOLD:
            severity = "MODERATE"
        else:
            severity = "LOW"

        return {
            "respondents": len(valid),
            "abstained": abstained,
            "score": round(score, 2),
            "severity": severity,
        }

    @staticmethod
    def enps(responses: List[SurveyResponse]) -> Dict[str, Any]:
        """
        Employee Net Promoter Score = (promoters% - detractors%).
        Range -100 to +100.
        Rule 1: None when no respondents.
        """
        valid = [r for r in responses if r.enps_score is not None
                 and 0 <= r.enps_score <= 10]
        if not valid:
            return {
                "respondents": 0,
                "enps": None,
                "promoter_count": 0,
                "passive_count": 0,
                "detractor_count": 0,
                "reason": "no_enps_responses",
            }
        promoters = sum(1 for r in valid if r.enps_score >= ENPS_PROMOTER_MIN_SCORE)
        detractors = sum(1 for r in valid if r.enps_score <= ENPS_DETRACTOR_MAX_SCORE)
        passive = len(valid) - promoters - detractors
        enps_val = (promoters / len(valid) - detractors / len(valid)) * 100
        return {
            "respondents": len(valid),
            "promoter_count": promoters,
            "passive_count": passive,
            "detractor_count": detractors,
            "enps": round(enps_val, 1),
        }

    @staticmethod
    def drivers_breakdown(responses: List[SurveyResponse]) -> Dict[str, Any]:
        """Per-driver average score. Rule 6: missing driver scores surfaced."""
        out: Dict[str, Any] = {}
        for driver in ENGAGEMENT_DRIVERS:
            scores = [r.driver_scores.get(driver) for r in responses
                      if driver in r.driver_scores]
            valid_scores = [s for s in scores if s is not None and LIKERT_MIN <= s <= LIKERT_MAX]
            missing = sum(1 for r in responses if driver not in r.driver_scores)
            if not valid_scores:
                out[driver] = {
                    "respondents": 0,
                    "score": None,
                    "missing_count": missing,
                    "reason": "no_valid_responses_for_driver",
                }
            else:
                avg_norm = sum(_normalize_likert(s) for s in valid_scores) / len(valid_scores)
                out[driver] = {
                    "respondents": len(valid_scores),
                    "score": round(avg_norm, 2),
                    "missing_count": missing,
                }
        return out

    # ------------------------------------------------------------------
    # Cat D scaffolding — Rule 7 (4th application)
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_based_sentiment(text: str) -> Tuple[float, Dict[str, Any]]:
        """
        Deterministic keyword-based sentiment fallback (Rule 7).
        Returns score in range [-1.0, +1.0] and breakdown.
        Same input ALWAYS produces same output (verifiable).
        """
        if not text:
            return 0.0, {"positive_hits": [], "negative_hits": [], "neutral": True}
        words = text.lower().split()
        pos_hits = [w for w in words if w in POSITIVE_KEYWORDS]
        neg_hits = [w for w in words if w in NEGATIVE_KEYWORDS]
        if not pos_hits and not neg_hits:
            return 0.0, {"positive_hits": [], "negative_hits": [], "neutral": True}
        pos = len(pos_hits)
        neg = len(neg_hits)
        score = (pos - neg) / max(1, pos + neg)
        return score, {
            "positive_hits": pos_hits[:5],
            "negative_hits": neg_hits[:5],
            "neutral": False,
        }

    @classmethod
    def sentiment_score(
        cls,
        text: str,
        ml_sentiment_fn: Optional[Callable[[str], Tuple[float, Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        Cat D scaffolding (Rule 7 — 4th application).

        Returns sentiment with EXPLICIT separation:
        - basis="ml" if ml_sentiment_fn provided AND succeeds
        - basis="rule_based" otherwise
        - Always returns rule_based_sentiment for transparency
        - NEVER silently substitutes one for the other
        """
        rule_score, rule_meta = cls._rule_based_sentiment(text)

        # No ML model loaded
        if ml_sentiment_fn is None:
            return {
                "basis": "rule_based",
                "ml_sentiment": None,
                "rule_based_sentiment": round(rule_score, 3),
                "rule_based_meta": rule_meta,
                "reason": "no_ml_sentiment_model_loaded",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

        # ML model provided — try it
        try:
            ml_score, ml_meta = ml_sentiment_fn(text)
            return {
                "basis": "ml",
                "ml_sentiment": round(float(ml_score), 3),
                "ml_meta": ml_meta,
                "rule_based_sentiment": round(rule_score, 3),
                "rule_based_meta": rule_meta,
            }
        except Exception as e:
            # ML fails — fall back to rule-based AND surface failure (Rule 7)
            return {
                "basis": "rule_based",
                "ml_sentiment": None,
                "rule_based_sentiment": round(rule_score, 3),
                "rule_based_meta": rule_meta,
                "reason": f"ml_sentiment_error:{type(e).__name__}",
                "spec_deviation": SPEC_DEVIATION_NOTE,
            }

    # ------------------------------------------------------------------
    # Flight risk (deterministic, NOT ML)
    # ------------------------------------------------------------------

    @staticmethod
    def flight_risk_indicators(signals: StaffSignals) -> Dict[str, Any]:
        """
        Compute deterministic flight-risk score from signals.
        NOT ML — explicit weighted-sum of observable indicators.
        Rule 6: missing signals surfaced in `missing_signals`, not imputed.
        """
        score = 0
        triggered: List[str] = []
        missing: List[str] = []

        if signals.engagement_score is None:
            missing.append("engagement_score")
        elif signals.engagement_score < 40:
            score += FLIGHT_RISK_FACTOR_WEIGHTS["engagement_below_40"]
            triggered.append("engagement_below_40")

        if signals.last_promotion_years_ago is None:
            missing.append("last_promotion_years_ago")
        elif signals.last_promotion_years_ago >= 3:
            score += FLIGHT_RISK_FACTOR_WEIGHTS["no_promotion_3y"]
            triggered.append("no_promotion_3y")

        if signals.compensation_percentile is None:
            missing.append("compensation_percentile")
        elif signals.compensation_percentile < 25:
            score += FLIGHT_RISK_FACTOR_WEIGHTS["compensation_below_p25"]
            triggered.append("compensation_below_p25")

        if not signals.last_two_ratings:
            missing.append("last_two_ratings")
        elif (len(signals.last_two_ratings) >= 2
              and all(r in ("DEVELOPING", "UNSATISFACTORY") for r in signals.last_two_ratings[-2:])):
            score += FLIGHT_RISK_FACTOR_WEIGHTS["low_manager_rating_consecutive"]
            triggered.append("low_manager_rating_consecutive")

        if signals.tenure_years is None:
            missing.append("tenure_years")
        elif 2 <= signals.tenure_years <= 5:
            score += FLIGHT_RISK_FACTOR_WEIGHTS["tenure_2_5y"]
            triggered.append("tenure_2_5y")

        if score >= FLIGHT_RISK_HIGH_THRESHOLD:
            severity = "HIGH"
        elif score >= FLIGHT_RISK_MEDIUM_THRESHOLD:
            severity = "MEDIUM"
        else:
            severity = "LOW"

        return {
            "staff_id": signals.staff_id,
            "score": score,
            "severity": severity,
            "triggered_factors": triggered,
            "missing_signals": missing,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_response(**kw):
    defaults = dict(
        response_id="R1", staff_id="S1", survey_period="2025_Q4",
        overall_likert=4, enps_score=8,
        driver_scores={"LEADERSHIP": 4, "COMPENSATION": 3},
    )
    defaults.update(kw)
    return SurveyResponse(**defaults)


def _test_engagement_score_basic():
    resps = [_make_response(overall_likert=5), _make_response(overall_likert=4), _make_response(overall_likert=3)]
    r = EmployeeEngagementEngine.engagement_score(resps)
    # (100 + 75 + 50) / 3 = 75
    assert r["score"] == 75.0
    assert r["severity"] == "HIGH"


def _test_engagement_no_respondents_rule1():
    """Rule 1: no respondents → score=None."""
    r = EmployeeEngagementEngine.engagement_score([])
    assert r["score"] is None
    assert r["respondents"] == 0


def _test_engagement_abstain_tracked_rule6():
    """Rule 6: abstained respondents counted, not imputed."""
    resps = [_make_response(overall_likert=4), _make_response(overall_likert=None)]
    r = EmployeeEngagementEngine.engagement_score(resps)
    assert r["abstained"] == 1
    assert r["respondents"] == 1


def _test_enps_basic():
    resps = [
        _make_response(enps_score=10),
        _make_response(enps_score=9),
        _make_response(enps_score=7),
        _make_response(enps_score=5),  # detractor
    ]
    r = EmployeeEngagementEngine.enps(resps)
    assert r["promoter_count"] == 2
    assert r["passive_count"] == 1
    assert r["detractor_count"] == 1
    # 50% promoters - 25% detractors = 25
    assert r["enps"] == 25.0


def _test_enps_no_respondents_rule1():
    r = EmployeeEngagementEngine.enps([])
    assert r["enps"] is None


def _test_drivers_breakdown():
    resps = [
        _make_response(driver_scores={"LEADERSHIP": 5, "COMPENSATION": 3}),
        _make_response(driver_scores={"LEADERSHIP": 4}),  # missing COMPENSATION
    ]
    r = EmployeeEngagementEngine.drivers_breakdown(resps)
    # LEADERSHIP: avg of 5,4 normalized = (100+75)/2 = 87.5
    assert r["LEADERSHIP"]["score"] == 87.5
    # COMPENSATION had 1 response + 1 missing
    assert r["COMPENSATION"]["respondents"] == 1
    assert r["COMPENSATION"]["missing_count"] == 1
    # Drivers with NO data should have score=None (Rule 1)
    assert r["GROWTH_DEVELOPMENT"]["score"] is None


def _test_sentiment_no_model_rule7():
    """Rule 7: no ML model → ml_sentiment=None + reason + rule_based separately."""
    r = EmployeeEngagementEngine.sentiment_score("I love working here, great team")
    assert r["basis"] == "rule_based"
    assert r["ml_sentiment"] is None
    assert r["reason"] == "no_ml_sentiment_model_loaded"
    assert r["rule_based_sentiment"] > 0  # positive
    assert r["spec_deviation"] == SPEC_DEVIATION_NOTE


def _test_sentiment_negative_rule_based():
    r = EmployeeEngagementEngine.sentiment_score("This place is terrible and toxic")
    assert r["rule_based_sentiment"] < 0


def _test_sentiment_neutral():
    r = EmployeeEngagementEngine.sentiment_score("Just another day at work")
    assert r["rule_based_sentiment"] == 0
    assert r["rule_based_meta"]["neutral"] is True


def _test_sentiment_ml_provided_succeeds():
    def fake_ml(text): return (0.85, {"model": "fake_v1"})
    r = EmployeeEngagementEngine.sentiment_score("I love this", ml_sentiment_fn=fake_ml)
    assert r["basis"] == "ml"
    assert r["ml_sentiment"] == 0.85
    # Rule 7: rule-based is ALSO surfaced for transparency
    assert "rule_based_sentiment" in r


def _test_sentiment_ml_fails_falls_back_rule7():
    """Rule 7: ML failure → fallback + reason surfaced (no silent substitution)."""
    def broken_ml(text): raise ConnectionError("api down")
    r = EmployeeEngagementEngine.sentiment_score("I love this", ml_sentiment_fn=broken_ml)
    assert r["basis"] == "rule_based"
    assert r["ml_sentiment"] is None
    assert "ml_sentiment_error:ConnectionError" in r["reason"]


def _test_sentiment_determinism():
    """Rule-based sentiment must be deterministic (same input → same output)."""
    r1 = EmployeeEngagementEngine.sentiment_score("I love working here")
    r2 = EmployeeEngagementEngine.sentiment_score("I love working here")
    r3 = EmployeeEngagementEngine.sentiment_score("I love working here")
    assert r1["rule_based_sentiment"] == r2["rule_based_sentiment"] == r3["rule_based_sentiment"]


def _test_flight_risk_high():
    s = StaffSignals(
        staff_id="S1", engagement_score=30, last_promotion_years_ago=4,
        compensation_percentile=20, last_two_ratings=["DEVELOPING", "UNSATISFACTORY"],
        tenure_years=3,
    )
    r = EmployeeEngagementEngine.flight_risk_indicators(s)
    # 30 + 20 + 25 + 15 + 10 = 100 = HIGH
    assert r["score"] == 100
    assert r["severity"] == "HIGH"


def _test_flight_risk_low():
    s = StaffSignals(
        staff_id="S1", engagement_score=85, last_promotion_years_ago=1,
        compensation_percentile=60, last_two_ratings=["EXCEEDS", "EXCEEDS"],
        tenure_years=8,
    )
    r = EmployeeEngagementEngine.flight_risk_indicators(s)
    assert r["severity"] == "LOW"


def _test_flight_risk_missing_signals_rule6():
    """Rule 6: missing signals surfaced explicitly."""
    s = StaffSignals(staff_id="S1")
    r = EmployeeEngagementEngine.flight_risk_indicators(s)
    assert "engagement_score" in r["missing_signals"]
    assert "tenure_years" in r["missing_signals"]


def _test_spec_deviation_byte_for_byte():
    expected = (
        "ML-based sentiment classification is downstream work; "
        "v6 ships rule-based keyword sentiment scoring"
    )
    assert SPEC_DEVIATION_NOTE == expected


def self_test() -> bool:
    tests = [
        _test_engagement_score_basic,
        _test_engagement_no_respondents_rule1,
        _test_engagement_abstain_tracked_rule6,
        _test_enps_basic,
        _test_enps_no_respondents_rule1,
        _test_drivers_breakdown,
        _test_sentiment_no_model_rule7,
        _test_sentiment_negative_rule_based,
        _test_sentiment_neutral,
        _test_sentiment_ml_provided_succeeds,
        _test_sentiment_ml_fails_falls_back_rule7,
        _test_sentiment_determinism,
        _test_flight_risk_high,
        _test_flight_risk_low,
        _test_flight_risk_missing_signals_rule6,
        _test_spec_deviation_byte_for_byte,
    ]
    print("=" * 60)
    print("Employee Engagement Engine — Self-Tests (#64)")
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

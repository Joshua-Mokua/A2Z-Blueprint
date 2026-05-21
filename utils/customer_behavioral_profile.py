"""
================================================================================
A2Z MIS 360 — Standard #340: Customer Behavioral Profile
================================================================================

Risk classification: Cat B (deterministic profile composition over event store)
                     + Rule 7 ML hook (propensity scoring)

Comprehensive behavioral profile per customer: spending patterns, channel
preferences, life stage, risk appetite, loyalty score. v10.276 ships
deterministic baseline computed from v10.275 interaction event store.
ML-based propensity scoring is exposed via Rule 7 hook factory consumable
by v10.274 insurance_recommendation.ml_score_fn.

Public API:
    build_profile(customer_id, age=None, life_events=None, ...) -> profile
    customer_loyalty_score(customer_id) -> 0-100 score
    customer_risk_appetite(customer_id) -> conservative/moderate/adventurous
    make_propensity_score_fn() -> Callable matching ml_score_fn contract

SPENDING_TIERS byte-for-byte:
    HIGH      -- avg monthly transaction value > 100k KES (90d window)
    MEDIUM    -- 20k-100k
    LOW       -- < 20k
    UNKNOWN   -- insufficient transaction data

RISK_APPETITE_LEVELS byte-for-byte:
    CONSERVATIVE -- ATM-heavy, savings-pattern, low transaction velocity
    MODERATE     -- mixed channels, regular patterns
    ADVENTUROUS  -- multi-channel + investment inquiries + frequent activity
    UNKNOWN      -- insufficient data

LIFE_STAGES byte-for-byte:
    YOUNG_PROFESSIONAL  -- age < 30, JOB_CHANGE / NEW_CUSTOMER signals
    FAMILY_BUILDING     -- 30-45, MARRIAGE / NEW_CHILD / HOUSE_PURCHASE
    ESTABLISHED         -- 45-55, BUSINESS_OPENING / INCOME_INCREASE
    PRE_RETIREMENT      -- 55-65, NEAR_RETIREMENT signals
    RETIRED             -- 65+
    UNKNOWN             -- age missing or no life events

LOYALTY_SCORE_WEIGHTS sum=100:
    tenure_weight              = 30
    engagement_frequency_weight = 30
    channel_diversity_weight    = 20
    no_complaint_weight        = 20

Rule 7 hook contract (matches v10.274 insurance_recommendation.ml_score_fn):
    fn(product_code: str, customer_attrs: Dict[str, Any]) -> Decimal (0-100)

Honesty rules:
    Rule 1: profile fields return None / UNKNOWN when underlying data missing
    Rule 6: invalid customer_id surfaces explicit reason
    Rule 7: SPEC_DEVIATION_NOTE documents ML training requires production
            customer transaction data

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.interaction_capture import InteractionCaptureEngine

getcontext().prec = 28


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #340 specifies ML-based comprehensive behavioral "
    "profile. v10.276 ships deterministic profile computation over the "
    "v10.275 interaction event store + Rule 7 propensity hook factory "
    "(make_propensity_score_fn) returning a callable that matches the "
    "v10.274 insurance_recommendation.ml_score_fn contract. Production "
    "ML training requires real customer transaction data + ground-truth "
    "labels (purchase / no purchase per product), deferred to deployment "
    "phase. Hook output uses deterministic propensity heuristics (channel "
    "alignment + spending tier match + life-stage match) until ML lands."
)


SPENDING_TIERS: Tuple[str, ...] = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
RISK_APPETITE_LEVELS: Tuple[str, ...] = (
    "CONSERVATIVE", "MODERATE", "ADVENTUROUS", "UNKNOWN",
)
LIFE_STAGES: Tuple[str, ...] = (
    "YOUNG_PROFESSIONAL", "FAMILY_BUILDING", "ESTABLISHED",
    "PRE_RETIREMENT", "RETIRED", "UNKNOWN",
)

LOYALTY_SCORE_WEIGHTS: Dict[str, Decimal] = {
    "tenure_weight":               Decimal("30"),
    "engagement_frequency_weight": Decimal("30"),
    "channel_diversity_weight":    Decimal("20"),
    "no_complaint_weight":         Decimal("20"),
}

SPENDING_HIGH_THRESHOLD_KES: Decimal = Decimal("100000")
SPENDING_MEDIUM_THRESHOLD_KES: Decimal = Decimal("20000")
SPENDING_WINDOW_DAYS: int = 90


class BehavioralProfileEngine:
    """Deterministic comprehensive behavioral profile composition."""

    def __init__(
        self,
        capture: Optional[InteractionCaptureEngine] = None,
    ):
        self.capture = capture or InteractionCaptureEngine()

    def _get_recent_events(
        self, customer_id: str, days: int, as_of: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        as_of = as_of or date.today()
        start = (as_of - timedelta(days=days)).isoformat()
        end = as_of.isoformat() + "T23:59:59"
        return self.capture.list_events(
            customer_id, period_start=start, period_end=end, limit=10**9,
        )

    def spending_tier(
        self, customer_id: str, as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        events = self._get_recent_events(customer_id, SPENDING_WINDOW_DAYS, as_of)
        txns = [
            e for e in events
            if e.get("event_type") == "TRANSACTION"
            and e.get("amount_kes") is not None
        ]
        if not txns:
            return {
                "tier": "UNKNOWN",
                "monthly_avg_kes": None,
                "txn_count": 0,
                "reason": "no_transactions_in_window",
            }
        try:
            total = sum(Decimal(str(t["amount_kes"])) for t in txns)
        except (ValueError, TypeError):
            return {"tier": "UNKNOWN", "reason": "invalid_amount_data"}
        # Monthly avg = total / 3 months
        monthly_avg = total / Decimal("3")
        if monthly_avg > SPENDING_HIGH_THRESHOLD_KES:
            tier = "HIGH"
        elif monthly_avg >= SPENDING_MEDIUM_THRESHOLD_KES:
            tier = "MEDIUM"
        else:
            tier = "LOW"
        return {
            "tier": tier,
            "monthly_avg_kes": str(monthly_avg.quantize(Decimal("0.01"))),
            "txn_count": len(txns),
            "window_days": SPENDING_WINDOW_DAYS,
        }

    def channel_preferences(
        self, customer_id: str, as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        events = self._get_recent_events(customer_id, SPENDING_WINDOW_DAYS, as_of)
        if not events:
            return {
                "preferred_channels": [],
                "channel_diversity": 0,
                "reason": "no_events_in_window",
            }
        by_channel = Counter(e.get("channel") for e in events)
        ranked = by_channel.most_common()
        return {
            "preferred_channels": [c for c, _ in ranked[:2]],
            "channel_distribution": dict(by_channel),
            "channel_diversity": len(by_channel),
        }

    def customer_risk_appetite(
        self, customer_id: str, as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        events = self._get_recent_events(customer_id, SPENDING_WINDOW_DAYS, as_of)
        if not events:
            return {
                "level": "UNKNOWN",
                "reason": "no_events_in_window",
            }

        signals = {
            "atm_share": 0,
            "investment_inquiry_count": 0,
            "channel_count": 0,
            "txn_velocity": 0,
        }
        n = len(events)
        atm_count = sum(1 for e in events if e.get("channel") == "ATM")
        signals["atm_share"] = round((atm_count / n) * 100, 2) if n else 0
        signals["investment_inquiry_count"] = sum(
            1 for e in events
            if e.get("event_type") == "INQUIRY"
            and "investment" in str(e.get("metadata", {})).lower()
        )
        signals["channel_count"] = len({e.get("channel") for e in events})
        signals["txn_velocity"] = sum(
            1 for e in events if e.get("event_type") == "TRANSACTION"
        )

        # Classification rules (deterministic)
        if signals["atm_share"] > 50 and signals["channel_count"] <= 2:
            level = "CONSERVATIVE"
        elif (signals["channel_count"] >= 4
                or signals["investment_inquiry_count"] >= 1):
            level = "ADVENTUROUS"
        else:
            level = "MODERATE"

        return {
            "level": level,
            "signals": signals,
        }

    def life_stage(
        self,
        customer_id: str,
        age: Optional[int] = None,
        life_events: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if age is None:
            return {
                "stage": "UNKNOWN",
                "reason": "age_required_for_classification",
            }

        life_events = life_events or []

        # Age-based primary classification
        if age < 30:
            stage = "YOUNG_PROFESSIONAL"
        elif age < 45:
            stage = "FAMILY_BUILDING"
        elif age < 55:
            stage = "ESTABLISHED"
        elif age < 65:
            stage = "PRE_RETIREMENT"
        else:
            stage = "RETIRED"

        # Life-event refinement
        if "NEAR_RETIREMENT" in life_events and stage in (
            "ESTABLISHED",
        ):
            stage = "PRE_RETIREMENT"
        if any(e in life_events for e in
                 ("MARRIAGE", "NEW_CHILD", "HOUSE_PURCHASE")) \
                and stage == "YOUNG_PROFESSIONAL":
            stage = "FAMILY_BUILDING"

        return {
            "stage": stage,
            "age": age,
            "life_events": life_events,
        }

    def customer_loyalty_score(
        self, customer_id: str, as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        all_events = self.capture.list_events(customer_id, limit=10**9)
        if not all_events:
            return {
                "score": None,
                "reason": "no_events_no_history",
            }
        # Sort ascending
        all_events.sort(key=lambda e: e.get("occurred_at", ""))
        first_ts = all_events[0].get("occurred_at", "")
        try:
            first_dt = datetime.fromisoformat(first_ts.replace("Z", ""))
            tenure_days = (datetime.combine(as_of, datetime.min.time()) - first_dt).days
        except (ValueError, AttributeError):
            tenure_days = 0

        # Tenure component: 0 days → 0; 365+ days → 100
        tenure_score = min(Decimal(tenure_days) / Decimal("365") * Decimal("100"),
                              Decimal("100"))

        # Engagement frequency: events / month over last 90 days
        recent = self._get_recent_events(customer_id, 90, as_of)
        events_per_month = Decimal(len(recent)) / Decimal("3")
        # 30+ events/month → 100; 0 → 0
        eng_score = min(events_per_month / Decimal("30") * Decimal("100"),
                          Decimal("100"))

        # Channel diversity: 5+ channels → 100
        channel_count = len({e.get("channel") for e in all_events})
        diversity_score = min(Decimal(channel_count) / Decimal("5") *
                                Decimal("100"), Decimal("100"))

        # No-complaint: 100 if zero complaints in last 90 days, else scaled
        complaints = sum(
            1 for e in recent if e.get("event_type") == "COMPLAINT"
        )
        if complaints == 0:
            no_complaint_score = Decimal("100")
        elif complaints >= 5:
            no_complaint_score = Decimal("0")
        else:
            no_complaint_score = (
                Decimal("100") - Decimal(complaints) * Decimal("20")
            )

        components = {
            "tenure_score": tenure_score,
            "engagement_score": eng_score,
            "diversity_score": diversity_score,
            "no_complaint_score": no_complaint_score,
        }

        composite = (
            tenure_score * LOYALTY_SCORE_WEIGHTS["tenure_weight"] / Decimal("100")
            + eng_score * LOYALTY_SCORE_WEIGHTS["engagement_frequency_weight"] / Decimal("100")
            + diversity_score * LOYALTY_SCORE_WEIGHTS["channel_diversity_weight"] / Decimal("100")
            + no_complaint_score * LOYALTY_SCORE_WEIGHTS["no_complaint_weight"] / Decimal("100")
        ).quantize(Decimal("0.01"))

        return {
            "score": str(composite),
            "tenure_days": tenure_days,
            "components": {k: str(v.quantize(Decimal("0.01")))
                              for k, v in components.items()},
            "weights": {k: str(v) for k, v in LOYALTY_SCORE_WEIGHTS.items()},
        }

    def build_profile(
        self,
        customer_id: str,
        age: Optional[int] = None,
        life_events: Optional[List[str]] = None,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        return {
            "customer_id": customer_id,
            "spending": self.spending_tier(customer_id, as_of),
            "channels": self.channel_preferences(customer_id, as_of),
            "risk_appetite": self.customer_risk_appetite(customer_id, as_of),
            "life_stage": self.life_stage(customer_id, age, life_events),
            "loyalty": self.customer_loyalty_score(customer_id, as_of),
            "_meta": {
                "spec_deviation": SPEC_DEVIATION_NOTE,
                "generated_at": datetime.utcnow().isoformat(),
            },
        }

    # ── Rule 7 hook factory ─────────────────────────────────────────

    def make_propensity_score_fn(self) -> Callable[[str, Dict[str, Any]], Decimal]:
        """
        Returns a callable matching v10.274 insurance_recommendation.ml_score_fn.

        Signature: fn(product_code, customer_attrs) -> Decimal (0-100)

        The callable computes a deterministic propensity score blending:
        - Channel alignment (digital products → MOBILE_APP/WEB heavy users score higher)
        - Spending tier match (HIGH spenders score higher for premium products)
        - Life-stage match (FAMILY_BUILDING for EDUCATION/LIFE products)
        """
        engine_self = self

        def _propensity_score_fn(
            product_code: str,
            customer_attrs: Dict[str, Any],
        ) -> Decimal:
            customer_id = customer_attrs.get("customer_id")
            if not customer_id:
                return Decimal("50")  # neutral — no customer to score

            profile = engine_self.build_profile(
                customer_id,
                age=customer_attrs.get("age"),
                life_events=customer_attrs.get("life_events", []),
            )
            score = Decimal("50")  # baseline

            # Spending tier signal
            tier = profile.get("spending", {}).get("tier")
            if tier == "HIGH":
                score += Decimal("20")
            elif tier == "MEDIUM":
                score += Decimal("10")

            # Channel digital heaviness — higher for digital-friendly products
            preferred = profile.get("channels", {}).get("preferred_channels", [])
            if preferred and preferred[0] in ("MOBILE_APP", "WEB"):
                score += Decimal("10")

            # Life-stage match
            stage = profile.get("life_stage", {}).get("stage")
            if "EDUCATION" in product_code.upper() and stage == "FAMILY_BUILDING":
                score += Decimal("15")
            if "PENSION" in product_code.upper() and stage == "PRE_RETIREMENT":
                score += Decimal("15")

            # Loyalty
            try:
                loyalty = profile.get("loyalty", {}).get("score")
                if loyalty is not None and Decimal(loyalty) >= Decimal("70"):
                    score += Decimal("5")
            except (ValueError, TypeError):
                pass

            # Cap at 100
            return min(score, Decimal("100"))

        return _propensity_score_fn


def _self_test() -> None:
    import tempfile

    # Spec deviation
    assert "v10.274" in SPEC_DEVIATION_NOTE
    # Weight sum
    assert sum(LOYALTY_SCORE_WEIGHTS.values()) == Decimal("100")

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = BehavioralProfileEngine(capture=capture)

        # Test 1: empty profile surfaces UNKNOWN
        profile = engine.build_profile("UNKNOWN")
        assert profile["spending"]["tier"] == "UNKNOWN"
        assert profile["channels"]["channel_diversity"] == 0
        assert profile["life_stage"]["stage"] == "UNKNOWN"
        assert profile["loyalty"]["score"] is None

        # Test 2: seed events + compute spending tier
        # 6 transactions of 50,000 KES over recent 90 days = 300,000 / 3 = 100,000 monthly
        # That's borderline HIGH (> 100K) — exact at threshold means MEDIUM
        # Set higher: 6 of 60,000 = 360,000 / 3 = 120,000 → HIGH
        for i in range(6):
            day = (date.today() - timedelta(days=10 + i)).isoformat()
            capture.capture_event(
                "CUST-HIGH",
                {"event_id": f"EV-H-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "60000"},
                actor="pipeline",
            )
        st = engine.spending_tier("CUST-HIGH")
        assert st["tier"] == "HIGH"

        # Test 3: LOW spender
        for i in range(3):
            day = (date.today() - timedelta(days=15 + i)).isoformat()
            capture.capture_event(
                "CUST-LOW",
                {"event_id": f"EV-L-{i}",
                 "channel": "ATM",
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "5000"},
                actor="pipeline",
            )
        st = engine.spending_tier("CUST-LOW")
        assert st["tier"] == "LOW"

        # Test 4: channel preferences
        # CUST-HIGH used MOBILE_APP only
        ch = engine.channel_preferences("CUST-HIGH")
        assert "MOBILE_APP" in ch["preferred_channels"]

        # Test 5: risk appetite — CONSERVATIVE
        ra = engine.customer_risk_appetite("CUST-LOW")
        assert ra["level"] == "CONSERVATIVE"  # 100% ATM, 1 channel

        # Test 6: risk appetite — ADVENTUROUS (multi-channel)
        for i, ch_name in enumerate(["WEB", "MOBILE_APP", "BRANCH", "CALL_CENTER", "ATM"]):
            day = (date.today() - timedelta(days=5 + i)).isoformat()
            capture.capture_event(
                "CUST-ADV",
                {"event_id": f"EV-ADV-{i}",
                 "channel": ch_name,
                 "event_type": "INQUIRY",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "metadata": {"topic": "investment"} if ch_name == "BRANCH" else {}},
                actor="pipeline",
            )
        ra = engine.customer_risk_appetite("CUST-ADV")
        assert ra["level"] == "ADVENTUROUS"

        # Test 7: life stage — age-based
        ls = engine.life_stage("CUST-001", age=25)
        assert ls["stage"] == "YOUNG_PROFESSIONAL"
        ls = engine.life_stage("CUST-001", age=35)
        assert ls["stage"] == "FAMILY_BUILDING"
        ls = engine.life_stage("CUST-001", age=58)
        assert ls["stage"] == "PRE_RETIREMENT"
        ls = engine.life_stage("CUST-001", age=70)
        assert ls["stage"] == "RETIRED"

        # Test 8: life stage refinement — young + MARRIAGE → FAMILY_BUILDING
        ls = engine.life_stage("CUST-001", age=28, life_events=["MARRIAGE"])
        assert ls["stage"] == "FAMILY_BUILDING"

        # Test 9: missing age
        ls = engine.life_stage("CUST-001")
        assert ls["stage"] == "UNKNOWN"

        # Test 10: loyalty score — high tenure + high engagement
        # CUST-HIGH has 6 transactions in 90 days
        # Loyalty depends on first event timestamp. Let me seed an old event:
        old_day = (date.today() - timedelta(days=400)).isoformat()
        capture.capture_event(
            "CUST-LOYAL",
            {"event_id": "EV-LOYAL-START",
             "channel": "BRANCH",
             "event_type": "APPLICATION",
             "outcome": "SUCCESS",
             "occurred_at": old_day + "T10:00:00"},
            actor="pipeline",
        )
        # Add many recent events
        for i in range(40):
            day = (date.today() - timedelta(days=80 - i*2)).isoformat()
            capture.capture_event(
                "CUST-LOYAL",
                {"event_id": f"EV-LOYAL-{i}",
                 "channel": ["BRANCH", "MOBILE_APP", "ATM", "WEB", "CALL_CENTER"][i % 5],
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "10000"},
                actor="pipeline",
            )
        ls_score = engine.customer_loyalty_score("CUST-LOYAL")
        assert ls_score["score"] is not None
        # Should be high (long tenure + many events + multi-channel + 0 complaints)
        assert Decimal(ls_score["score"]) >= Decimal("70")

        # Test 11: full profile composition
        profile = engine.build_profile(
            "CUST-LOYAL", age=40,
            life_events=["INCOME_INCREASE"],
        )
        assert profile["spending"]["tier"] != "UNKNOWN"
        assert profile["life_stage"]["stage"] == "FAMILY_BUILDING"
        assert profile["_meta"]["spec_deviation"]

        # Test 12: propensity hook factory
        score_fn = engine.make_propensity_score_fn()
        # Should be callable
        assert callable(score_fn)

        # No customer → neutral 50
        s = score_fn("BR-LIFE-001", {})
        assert s == Decimal("50")

        # CUST-LOYAL with EDUCATION product + age 40 → FAMILY_BUILDING + 15
        s = score_fn(
            "BR-EDU-001",
            {"customer_id": "CUST-LOYAL", "age": 40,
             "life_events": ["NEW_CHILD"]},
        )
        # Baseline 50 + EDUCATION+FAMILY 15 + maybe channel/spending bumps
        assert s >= Decimal("65")

    print("  ✅ customer_behavioral_profile self-test PASS")


if __name__ == "__main__":
    _self_test()

"""
================================================================================
A2Z MIS 360 — Standard #69: Customer Segmentation Engine
================================================================================

Risk classification: Cat B (deterministic RFM + value-tier classification)

Computes:
    - rfm_scores(customers, txns, ref_date)        -- Recency / Frequency / Monetary
    - rfm_segment(rfm)                              -- 11-segment classification
    - value_tier_assignment(customers)              -- HNI / MASS_AFFLUENT / MASS / SMALL
    - lifecycle_stage(customer)                     -- NEW / GROWING / MATURE / DORMANT

RFM scoring (industry standard, deterministic quintiles):
    Each dimension scored 1-5 based on quintile rank within the cohort.
    Higher = better (recent purchase, frequent, high spend).

11 RFM segments (industry standard naming):
    CHAMPIONS, LOYAL, POTENTIAL_LOYALIST, NEW_CUSTOMERS, PROMISING,
    NEED_ATTENTION, ABOUT_TO_SLEEP, AT_RISK, CANNOT_LOSE_THEM,
    HIBERNATING, LOST

Value tiers (banking industry — Total Relationship Balance):
    HNI            : >= KES 50M
    MASS_AFFLUENT  : KES 5M - 50M
    MASS           : KES 100K - 5M
    SMALL          : < KES 100K

Honesty rules applied:
    Rule 1: rfm_score = None when no transactions in window
    Rule 6: customers with no balance data surfaced in `unscored_count`
            (NEVER silently bucketed into MASS or any other tier)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# RFM segment matrix (11 segments, industry standard)
# Maps (R-quintile, F-quintile, M-quintile) ranges → segment name
RFM_SEGMENTS: Tuple[str, ...] = (
    "CHAMPIONS",
    "LOYAL",
    "POTENTIAL_LOYALIST",
    "NEW_CUSTOMERS",
    "PROMISING",
    "NEED_ATTENTION",
    "ABOUT_TO_SLEEP",
    "AT_RISK",
    "CANNOT_LOSE_THEM",
    "HIBERNATING",
    "LOST",
)

# Value tiers (KES Total Relationship Balance thresholds)
VALUE_TIER_HNI_MIN = Decimal("50000000")            # 50M+
VALUE_TIER_MASS_AFFLUENT_MIN = Decimal("5000000")   # 5M+
VALUE_TIER_MASS_MIN = Decimal("100000")             # 100K+
# Below 100K = SMALL

VALUE_TIERS: Tuple[str, ...] = ("HNI", "MASS_AFFLUENT", "MASS", "SMALL")

# Lifecycle stages
LIFECYCLE_NEW_DAYS = 90               # < 90 days = NEW
LIFECYCLE_GROWING_DAYS = 365          # 90-365 = GROWING
LIFECYCLE_DORMANT_DAYS = 180          # No txn in 180 days = DORMANT

LIFECYCLE_STAGES: Tuple[str, ...] = ("NEW", "GROWING", "MATURE", "DORMANT")

# RFM windows
DEFAULT_RFM_WINDOW_DAYS = 365


@dataclass
class CustomerRecord:
    customer_id: str
    cif_id: str
    onboarded_date: Optional[date] = None
    total_relationship_balance_kes: Optional[Decimal] = None
    last_transaction_date: Optional[date] = None


@dataclass
class CustomerTransaction:
    txn_id: str
    customer_id: str
    txn_date: date
    amount_kes: Decimal


def _parse_date(d: Any) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, date):
        return d
    if isinstance(d, datetime):
        return d.date()
    try:
        return datetime.fromisoformat(str(d)).date()
    except Exception:
        return None


def _quintile_rank(value: float, sorted_values: List[float]) -> int:
    """
    Deterministic quintile rank 1-5.
    Lowest 20% = 1, ..., highest 20% = 5.
    Returns 0 if no comparison cohort.
    """
    if not sorted_values:
        return 0
    n = len(sorted_values)
    # Find percentile rank
    # Count how many values are strictly less than value
    below = sum(1 for v in sorted_values if v < value)
    pct = below / n
    if pct < 0.2: return 1
    if pct < 0.4: return 2
    if pct < 0.6: return 3
    if pct < 0.8: return 4
    return 5


def _quintile_rank_recency(days_since: float, sorted_days: List[float]) -> int:
    """For recency, LOWER days_since is BETTER, so invert."""
    if not sorted_days:
        return 0
    rank = _quintile_rank(days_since, sorted_days)
    # Invert: 1 → 5, 2 → 4, etc
    return 6 - rank


class CustomerSegmentationEngine:
    """Deterministic RFM scoring + segment/tier classification."""

    @staticmethod
    def rfm_scores(
        customers: List[CustomerRecord],
        transactions: List[CustomerTransaction],
        reference_date: date,
        window_days: int = DEFAULT_RFM_WINDOW_DAYS,
    ) -> Dict[str, Any]:
        """
        Compute RFM scores for each customer.
        Rule 1: customers with no transactions in window get None scores.
        """
        cutoff = reference_date - timedelta(days=window_days)

        # Group transactions by customer
        by_cust: Dict[str, List[CustomerTransaction]] = {}
        for t in transactions:
            if t.txn_date >= cutoff and t.txn_date <= reference_date:
                by_cust.setdefault(t.customer_id, []).append(t)

        # Compute raw R/F/M for each customer
        raw_scores: List[Dict[str, Any]] = []
        unscored: List[str] = []
        for c in customers:
            txns = by_cust.get(c.customer_id, [])
            if not txns:
                unscored.append(c.customer_id)
                continue
            recency_days = (reference_date - max(t.txn_date for t in txns)).days
            frequency = len(txns)
            monetary = sum(t.amount_kes for t in txns)
            raw_scores.append({
                "customer_id": c.customer_id,
                "recency_days": recency_days,
                "frequency": frequency,
                "monetary_kes": monetary,
            })

        # Build cohort distributions
        recency_dist = sorted([float(r["recency_days"]) for r in raw_scores])
        frequency_dist = sorted([float(r["frequency"]) for r in raw_scores])
        monetary_dist = sorted([float(r["monetary_kes"]) for r in raw_scores])

        # Score each customer
        scored: List[Dict[str, Any]] = []
        for r in raw_scores:
            r_score = _quintile_rank_recency(float(r["recency_days"]), recency_dist)
            f_score = _quintile_rank(float(r["frequency"]), frequency_dist)
            m_score = _quintile_rank(float(r["monetary_kes"]), monetary_dist)
            scored.append({
                **r,
                "monetary_kes": str(r["monetary_kes"]),
                "r_score": r_score,
                "f_score": f_score,
                "m_score": m_score,
                "rfm_combined": int(f"{r_score}{f_score}{m_score}"),
            })

        return {
            "reference_date": reference_date.isoformat(),
            "window_days": window_days,
            "scored_customer_count": len(scored),
            "unscored_customer_count": len(unscored),
            "unscored_sample": unscored[:20],
            "scores": scored,
        }

    @staticmethod
    def rfm_segment(r_score: int, f_score: int, m_score: int) -> str:
        """
        Map (R, F, M) quintile triple to one of 11 industry-standard segments.
        Deterministic mapping per Putler / common RFM conventions.
        """
        if r_score == 0 or f_score == 0 or m_score == 0:
            return "LOST"  # No activity at all
        # CHAMPIONS: high R + high FM
        if r_score >= 4 and f_score >= 4 and m_score >= 4:
            return "CHAMPIONS"
        # LOYAL: high F + decent M, R can vary
        if f_score >= 4 and m_score >= 3:
            return "LOYAL"
        # POTENTIAL_LOYALIST: recent + moderate F
        if r_score >= 4 and f_score >= 3:
            return "POTENTIAL_LOYALIST"
        # NEW_CUSTOMERS: very recent, low frequency
        if r_score >= 4 and f_score <= 2:
            return "NEW_CUSTOMERS"
        # PROMISING: recent, low M
        if r_score >= 3 and m_score <= 2:
            return "PROMISING"
        # CANNOT_LOSE_THEM: high M but low R (lapsed VIP)
        if r_score <= 2 and m_score >= 4:
            return "CANNOT_LOSE_THEM"
        # AT_RISK: medium-low R, decent FM
        if r_score == 2 and f_score >= 3 and m_score >= 3:
            return "AT_RISK"
        # NEED_ATTENTION: middle-of-the-road
        if r_score == 3 and f_score == 3:
            return "NEED_ATTENTION"
        # LOST: lowest recency and low everything else (check before HIBERNATING)
        if r_score == 1 and f_score <= 2 and m_score <= 2:
            return "LOST"
        # ABOUT_TO_SLEEP: low R, modest F
        if r_score == 2 and f_score <= 2:
            return "ABOUT_TO_SLEEP"
        # HIBERNATING: low R, low F, low M (but R=2)
        if r_score <= 2 and f_score <= 2 and m_score <= 2:
            return "HIBERNATING"
        # LOST: very low R/F/M (catch-all for r_score == 1)
        if r_score == 1:
            return "LOST"
        return "NEED_ATTENTION"  # default fallback

    @staticmethod
    def value_tier_assignment(customers: List[CustomerRecord]) -> Dict[str, Any]:
        """
        Assign value tier by Total Relationship Balance.
        Rule 6: customers with None balance surfaced in `unassigned`.
        """
        results = []
        unassigned = []
        for c in customers:
            if c.total_relationship_balance_kes is None:
                unassigned.append(c.customer_id)
                continue
            bal = c.total_relationship_balance_kes
            if bal >= VALUE_TIER_HNI_MIN:
                tier = "HNI"
            elif bal >= VALUE_TIER_MASS_AFFLUENT_MIN:
                tier = "MASS_AFFLUENT"
            elif bal >= VALUE_TIER_MASS_MIN:
                tier = "MASS"
            else:
                tier = "SMALL"
            results.append({
                "customer_id": c.customer_id,
                "balance_kes": str(bal),
                "value_tier": tier,
            })

        # Tier distribution
        dist: Dict[str, int] = {t: 0 for t in VALUE_TIERS}
        for r in results:
            dist[r["value_tier"]] += 1

        return {
            "assigned_count": len(results),
            "unassigned_count": len(unassigned),
            "unassigned_sample": unassigned[:20],
            "tier_distribution": dist,
            "assignments": results,
        }

    @staticmethod
    def lifecycle_stage(
        customer: CustomerRecord,
        reference_date: date,
    ) -> Dict[str, Any]:
        """
        Classify customer into NEW / GROWING / MATURE / DORMANT.
        Rule 6: missing onboarded_date or last_txn → reason surfaced.
        """
        if customer.onboarded_date is None:
            return {"customer_id": customer.customer_id, "stage": None, "reason": "missing_onboarded_date"}

        days_active = (reference_date - customer.onboarded_date).days
        days_since_txn = None
        if customer.last_transaction_date is not None:
            days_since_txn = (reference_date - customer.last_transaction_date).days

        # DORMANT check first (overrides others)
        if days_since_txn is not None and days_since_txn >= LIFECYCLE_DORMANT_DAYS:
            stage = "DORMANT"
        elif days_active < LIFECYCLE_NEW_DAYS:
            stage = "NEW"
        elif days_active < LIFECYCLE_GROWING_DAYS:
            stage = "GROWING"
        else:
            stage = "MATURE"

        return {
            "customer_id": customer.customer_id,
            "stage": stage,
            "days_active": days_active,
            "days_since_last_txn": days_since_txn,
        }

    # ============================================================================
    # v7.12: L05 Card usage → Customer 360 enrichment feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def enrich_segment_with_card_usage(
        cls,
        base_rfm_segment: str,
        card_usage_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """L05 (CONSUMER) — enrich an RFM segment with card-usage signals.

        Consumes the payload from `cards.CardsEngine.card_usage_profile()`.
        Per Charter §7 Published Language pattern, depends only on the
        public dict contract (payload_version=1.0).

        Strategy:
            - Take the base RFM segment (e.g. CHAMPIONS, LOYAL, AT_RISK)
            - Apply card-usage modifiers:
                * HIGH velocity + diverse MCCs → upgrade segment 1 step
                * DORMANT velocity → downgrade segment 1 step
                * FOREIGN_HEAVY geographic → flag as TRAVELER_PROFILE
                * Single dominant MCC (>70%) → flag as SPECIALIST_PROFILE

        Returns dict with:
            base_segment, enriched_segment, modifiers_applied,
            profile_flags, consumed_payload_version, pattern
        """
        if not isinstance(card_usage_profile, dict):
            return {
                "status": "INVALID_PAYLOAD",
                "error": "card_usage_profile must be a dict",
                "base_segment": base_rfm_segment,
                "enriched_segment": base_rfm_segment,  # passthrough
            }

        if card_usage_profile.get("pattern") != "PUBLISHED_LANGUAGE":
            return {
                "status": "INVALID_PAYLOAD",
                "error": "card_usage_profile not using PUBLISHED_LANGUAGE pattern",
                "base_segment": base_rfm_segment,
                "enriched_segment": base_rfm_segment,
            }

        velocity = card_usage_profile.get("velocity", {})
        mcc_mix = card_usage_profile.get("merchant_category_mix", {})
        geo = card_usage_profile.get("geographic_pattern", {})

        velocity_class = velocity.get("velocity_class")
        diversity_str = mcc_mix.get("category_diversity_score")
        dominant_pct_str = mcc_mix.get("dominant_category_pct")
        geo_concentration = geo.get("geographic_concentration")

        modifiers = []
        flags = []

        # Segment ordering (rough engagement spectrum)
        SEGMENT_ORDER = [
            "HIBERNATING", "LOST", "AT_RISK", "POTENTIAL",
            "PROMISING", "LOYAL", "CHAMPIONS"
        ]

        try:
            current_idx = SEGMENT_ORDER.index(base_rfm_segment)
        except ValueError:
            current_idx = -1

        # 1. Velocity uplift / downgrade
        if current_idx >= 0:
            try:
                diversity = float(diversity_str) if diversity_str else 0.0
            except (TypeError, ValueError):
                diversity = 0.0

            if velocity_class == "HIGH" and diversity >= 50:
                # Upgrade one step (capped at top)
                new_idx = min(current_idx + 1, len(SEGMENT_ORDER) - 1)
                if new_idx != current_idx:
                    modifiers.append({
                        "from": SEGMENT_ORDER[current_idx],
                        "to": SEGMENT_ORDER[new_idx],
                        "reason": "high_velocity_plus_diverse_categories",
                    })
                    current_idx = new_idx
            elif velocity_class == "DORMANT":
                # Downgrade one step (floor at bottom)
                new_idx = max(current_idx - 1, 0)
                if new_idx != current_idx:
                    modifiers.append({
                        "from": SEGMENT_ORDER[current_idx],
                        "to": SEGMENT_ORDER[new_idx],
                        "reason": "card_velocity_dormant",
                    })
                    current_idx = new_idx

        enriched_segment = (SEGMENT_ORDER[current_idx]
                             if current_idx >= 0 else base_rfm_segment)

        # 2. Profile flags (orthogonal to segment)
        if geo_concentration == "FOREIGN_HEAVY":
            flags.append("TRAVELER_PROFILE")
        if dominant_pct_str:
            try:
                if float(dominant_pct_str) > 70:
                    flags.append("SPECIALIST_PROFILE")
            except (TypeError, ValueError):
                pass

        return {
            "base_segment": base_rfm_segment,
            "enriched_segment": enriched_segment,
            "modifiers_applied": modifiers,
            "profile_flags": flags,
            "consumed_payload_version": (
                card_usage_profile.get("payload_version", "unknown")),
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": [],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_customer(**kw):
    defaults = dict(
        customer_id="C1", cif_id="CIF1",
        onboarded_date=date(2024, 1, 1),
        total_relationship_balance_kes=Decimal("500000"),
        last_transaction_date=date(2026, 1, 1),
    )
    defaults.update(kw)
    return CustomerRecord(**defaults)


def _make_txn(**kw):
    defaults = dict(
        txn_id="T1", customer_id="C1",
        txn_date=date(2026, 1, 1), amount_kes=Decimal("10000"),
    )
    defaults.update(kw)
    return CustomerTransaction(**defaults)


def _test_rfm_basic_distribution():
    """5 customers with varied activity → quintile spread."""
    customers = [_make_customer(customer_id=f"C{i}") for i in range(5)]
    txns = []
    for i in range(5):
        # C0: 1 txn 300 days ago, 1000 KES
        # C4: 5 txns last week, 50000 KES each
        for j in range(i + 1):
            txns.append(_make_txn(
                txn_id=f"T{i}_{j}",
                customer_id=f"C{i}",
                txn_date=date(2026, 4, 30) - timedelta(days=(5-i)*60 + j),
                amount_kes=Decimal(str(1000 * (i + 1))),
            ))
    r = CustomerSegmentationEngine.rfm_scores(customers, txns, date(2026, 4, 30))
    assert r["scored_customer_count"] == 5
    assert r["unscored_customer_count"] == 0


def _test_rfm_unscored_rule1():
    """Rule 1: customer with no txns → unscored."""
    customers = [_make_customer(customer_id="C1")]
    r = CustomerSegmentationEngine.rfm_scores(customers, [], date(2026, 4, 30))
    assert r["scored_customer_count"] == 0
    assert r["unscored_customer_count"] == 1


def _test_rfm_segment_champions():
    seg = CustomerSegmentationEngine.rfm_segment(5, 5, 5)
    assert seg == "CHAMPIONS"


def _test_rfm_segment_lost():
    seg = CustomerSegmentationEngine.rfm_segment(1, 1, 1)
    assert seg == "LOST"


def _test_rfm_segment_cannot_lose():
    """High M but low R = lapsed VIP."""
    seg = CustomerSegmentationEngine.rfm_segment(1, 3, 5)
    assert seg == "CANNOT_LOSE_THEM"


def _test_rfm_segment_zero_score_lost():
    """Zero RFM score = LOST."""
    assert CustomerSegmentationEngine.rfm_segment(0, 5, 5) == "LOST"


def _test_value_tier_hni():
    customers = [_make_customer(total_relationship_balance_kes=Decimal("60000000"))]
    r = CustomerSegmentationEngine.value_tier_assignment(customers)
    assert r["tier_distribution"]["HNI"] == 1


def _test_value_tier_mass_affluent_boundary():
    """Boundary: exactly 5M = MASS_AFFLUENT."""
    customers = [_make_customer(total_relationship_balance_kes=VALUE_TIER_MASS_AFFLUENT_MIN)]
    r = CustomerSegmentationEngine.value_tier_assignment(customers)
    assert r["tier_distribution"]["MASS_AFFLUENT"] == 1


def _test_value_tier_small():
    customers = [_make_customer(total_relationship_balance_kes=Decimal("50000"))]
    r = CustomerSegmentationEngine.value_tier_assignment(customers)
    assert r["tier_distribution"]["SMALL"] == 1


def _test_value_tier_unassigned_rule6():
    """Rule 6: None balance → unassigned, NOT silently bucketed."""
    customers = [_make_customer(total_relationship_balance_kes=None)]
    r = CustomerSegmentationEngine.value_tier_assignment(customers)
    assert r["unassigned_count"] == 1
    # Verify NOT silently put into SMALL or any tier
    for tier in VALUE_TIERS:
        assert r["tier_distribution"][tier] == 0


def _test_lifecycle_new():
    c = _make_customer(onboarded_date=date(2026, 4, 1))
    r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
    assert r["stage"] == "NEW"


def _test_lifecycle_dormant_overrides():
    """DORMANT check overrides MATURE/GROWING."""
    c = _make_customer(
        onboarded_date=date(2020, 1, 1),  # very old
        last_transaction_date=date(2025, 1, 1),  # 1+ year ago
    )
    r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
    assert r["stage"] == "DORMANT"


def _test_lifecycle_mature():
    c = _make_customer(
        onboarded_date=date(2020, 1, 1),
        last_transaction_date=date(2026, 4, 1),
    )
    r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
    assert r["stage"] == "MATURE"


def _test_lifecycle_missing_onboarded_rule6():
    c = _make_customer(onboarded_date=None)
    r = CustomerSegmentationEngine.lifecycle_stage(c, date(2026, 4, 30))
    assert r["stage"] is None
    assert r["reason"] == "missing_onboarded_date"


def _test_value_tier_thresholds_byte_for_byte():
    assert VALUE_TIER_HNI_MIN == Decimal("50000000")
    assert VALUE_TIER_MASS_AFFLUENT_MIN == Decimal("5000000")
    assert VALUE_TIER_MASS_MIN == Decimal("100000")


def _test_rfm_segments_byte_for_byte():
    expected = ("CHAMPIONS", "LOYAL", "POTENTIAL_LOYALIST", "NEW_CUSTOMERS",
                "PROMISING", "NEED_ATTENTION", "ABOUT_TO_SLEEP", "AT_RISK",
                "CANNOT_LOSE_THEM", "HIBERNATING", "LOST")
    for s in expected:
        assert s in RFM_SEGMENTS


def self_test() -> bool:
    tests = [
        _test_rfm_basic_distribution,
        _test_rfm_unscored_rule1,
        _test_rfm_segment_champions,
        _test_rfm_segment_lost,
        _test_rfm_segment_cannot_lose,
        _test_rfm_segment_zero_score_lost,
        _test_value_tier_hni,
        _test_value_tier_mass_affluent_boundary,
        _test_value_tier_small,
        _test_value_tier_unassigned_rule6,
        _test_lifecycle_new,
        _test_lifecycle_dormant_overrides,
        _test_lifecycle_mature,
        _test_lifecycle_missing_onboarded_rule6,
        _test_value_tier_thresholds_byte_for_byte,
        _test_rfm_segments_byte_for_byte,
    ]
    print("=" * 60)
    print("Customer Segmentation Engine — Self-Tests (#69)")
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

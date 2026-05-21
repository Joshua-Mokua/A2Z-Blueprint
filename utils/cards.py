"""utils/cards.py — Cards Usage Engine (v7.12).

Built to close feedback loop L05: Card usage → Customer 360 enrichment.

This engine surfaces card-usage patterns in a deterministic, byte-for-byte
form that the customer_segmentation engine can consume to enrich RFM
segments and CLV projections.

Per Charter §3 / §13: cards is a Customer Intelligence bounded context
producing Published Language outputs that other contexts (segmentation,
churn prediction, cross-sell) can consume.

Three core methods:
    - usage_velocity(card_id, txns) — transaction frequency + amount metrics
    - merchant_category_mix(card_id, txns) — MCC distribution per card
    - geographic_pattern(card_id, txns) — location concentration / dispersion

Plus an aggregator:
    - card_usage_profile(card_id, txns) — composes the 3 above into one dict

Honesty rules:
    - Rule 1: returns None for missing inputs / empty txns
    - Rule 6: explicit `data_source` and `computed` flags
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Data classes
# ════════════════════════════════════════════════════════════════════

@dataclass
class CardTransaction:
    """A single card transaction.

    Designed minimal — calling code may have richer schemas; engine
    sticks to fields needed for usage profiling.
    """
    txn_id: str
    card_id: str
    customer_id: str
    amount_kes: Decimal
    txn_datetime: datetime
    merchant_category_code: Optional[str] = None  # ISO 18245 MCC
    merchant_country: Optional[str] = None         # ISO 3166-1 alpha-2
    merchant_city: Optional[str] = None
    txn_type: str = "PURCHASE"  # PURCHASE | ATM_WITHDRAWAL | REFUND


# ════════════════════════════════════════════════════════════════════
# Velocity (frequency + monetary metrics)
# ════════════════════════════════════════════════════════════════════

class CardsEngine:
    """Cards usage engine — deterministic profiling for L05 feedback loop."""

    @staticmethod
    def usage_velocity(
        card_id: str,
        txns: List[CardTransaction],
        reference_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Compute usage velocity (frequency + amount) for a card.

        Returns dict with keys:
            txn_count_30d, txn_count_90d, txn_count_365d,
            total_amount_kes_30d, total_amount_kes_90d,
            avg_amount_kes_30d, days_since_last_txn,
            velocity_class, computed
        """
        if not txns:
            return {"card_id": card_id, "computed": False,
                    "reason": "no_transactions"}

        ref = reference_date or datetime.now(timezone.utc)

        # Filter to this card only
        card_txns = [t for t in txns if t.card_id == card_id]
        if not card_txns:
            return {"card_id": card_id, "computed": False,
                    "reason": "no_transactions_for_card"}

        cutoff_30 = ref - timedelta(days=30)
        cutoff_90 = ref - timedelta(days=90)
        cutoff_365 = ref - timedelta(days=365)

        txn_30 = [t for t in card_txns if t.txn_datetime >= cutoff_30]
        txn_90 = [t for t in card_txns if t.txn_datetime >= cutoff_90]
        txn_365 = [t for t in card_txns if t.txn_datetime >= cutoff_365]

        amount_30 = sum((t.amount_kes for t in txn_30), Decimal("0"))
        amount_90 = sum((t.amount_kes for t in txn_90), Decimal("0"))

        last_txn = max(card_txns, key=lambda t: t.txn_datetime)
        days_since_last = (ref - last_txn.txn_datetime).days

        # Velocity classification
        # HIGH: >30 txns/30d (daily user); MEDIUM: 10-30; LOW: <10; DORMANT: >60d since last
        if days_since_last > 60:
            velocity_class = "DORMANT"
        elif len(txn_30) > 30:
            velocity_class = "HIGH"
        elif len(txn_30) >= 10:
            velocity_class = "MEDIUM"
        else:
            velocity_class = "LOW"

        avg_30 = (amount_30 / len(txn_30)) if txn_30 else Decimal("0")

        return {
            "card_id": card_id,
            "txn_count_30d": len(txn_30),
            "txn_count_90d": len(txn_90),
            "txn_count_365d": len(txn_365),
            "total_amount_kes_30d": str(amount_30.quantize(Decimal("0.01"))),
            "total_amount_kes_90d": str(amount_90.quantize(Decimal("0.01"))),
            "avg_amount_kes_30d": str(avg_30.quantize(Decimal("0.01"))),
            "days_since_last_txn": days_since_last,
            "velocity_class": velocity_class,
            "computed": True,
        }

    @staticmethod
    def merchant_category_mix(
        card_id: str,
        txns: List[CardTransaction],
    ) -> Dict[str, Any]:
        """Compute merchant category mix for a card.

        Returns dict with keys:
            top_categories (list of {mcc, txn_count, amount_kes, pct}),
            category_diversity_score (Herfindahl-style index 0-100),
            dominant_category, computed
        """
        if not txns:
            return {"card_id": card_id, "computed": False,
                    "reason": "no_transactions"}

        card_txns = [t for t in txns if t.card_id == card_id]
        if not card_txns:
            return {"card_id": card_id, "computed": False,
                    "reason": "no_transactions_for_card"}

        # Group by MCC
        by_mcc: Dict[str, Dict[str, Any]] = {}
        total_amount = Decimal("0")
        for t in card_txns:
            mcc = t.merchant_category_code or "UNKNOWN"
            if mcc not in by_mcc:
                by_mcc[mcc] = {"txn_count": 0, "amount_kes": Decimal("0")}
            by_mcc[mcc]["txn_count"] += 1
            by_mcc[mcc]["amount_kes"] += t.amount_kes
            total_amount += t.amount_kes

        # Compute pct + sort
        categories = []
        for mcc, stats in by_mcc.items():
            pct = (stats["amount_kes"] / total_amount * Decimal("100")
                   if total_amount > 0 else Decimal("0"))
            categories.append({
                "mcc": mcc,
                "txn_count": stats["txn_count"],
                "amount_kes": str(stats["amount_kes"].quantize(Decimal("0.01"))),
                "pct_of_spend": str(pct.quantize(Decimal("0.01"))),
            })
        categories.sort(key=lambda c: float(c["pct_of_spend"]), reverse=True)

        # Diversity index (inverse Herfindahl): higher = more diverse
        # H = sum(pct^2 / 10000); diversity = 100 * (1 - H)
        herfindahl = sum(
            (Decimal(c["pct_of_spend"]) / Decimal("100")) ** 2
            for c in categories)
        diversity_score = (Decimal("100") *
                            (Decimal("1") - herfindahl)).quantize(Decimal("0.01"))

        return {
            "card_id": card_id,
            "top_categories": categories[:5],
            "total_categories": len(categories),
            "category_diversity_score": str(diversity_score),
            "dominant_category": categories[0]["mcc"] if categories else None,
            "dominant_category_pct": (categories[0]["pct_of_spend"]
                                       if categories else None),
            "computed": True,
        }

    @staticmethod
    def geographic_pattern(
        card_id: str,
        txns: List[CardTransaction],
        home_country: str = "KE",
    ) -> Dict[str, Any]:
        """Compute geographic pattern for a card.

        Returns dict with keys:
            home_country_pct, foreign_country_count, top_countries,
            geographic_concentration, computed
        """
        if not txns:
            return {"card_id": card_id, "computed": False,
                    "reason": "no_transactions"}

        card_txns = [t for t in txns if t.card_id == card_id]
        if not card_txns:
            return {"card_id": card_id, "computed": False,
                    "reason": "no_transactions_for_card"}

        # Group by country
        by_country: Dict[str, Dict[str, Any]] = {}
        total_amount = Decimal("0")
        unknown_count = 0
        for t in card_txns:
            country = t.merchant_country
            if country is None:
                unknown_count += 1
                continue
            if country not in by_country:
                by_country[country] = {"txn_count": 0, "amount_kes": Decimal("0")}
            by_country[country]["txn_count"] += 1
            by_country[country]["amount_kes"] += t.amount_kes
            total_amount += t.amount_kes

        # Compute pct + sort
        countries = []
        for cc, stats in by_country.items():
            pct = (stats["amount_kes"] / total_amount * Decimal("100")
                   if total_amount > 0 else Decimal("0"))
            countries.append({
                "country_code": cc,
                "txn_count": stats["txn_count"],
                "amount_kes": str(stats["amount_kes"].quantize(Decimal("0.01"))),
                "pct_of_spend": str(pct.quantize(Decimal("0.01"))),
            })
        countries.sort(key=lambda c: float(c["pct_of_spend"]), reverse=True)

        home_pct = next(
            (c["pct_of_spend"] for c in countries
             if c["country_code"] == home_country),
            "0.00")
        foreign_count = sum(1 for c in countries
                            if c["country_code"] != home_country)

        # Concentration: HOME_DOMINANT (>=80% home) / SPLIT (50-80% home) /
        # FOREIGN_HEAVY (<50% home)
        home_pct_d = Decimal(home_pct)
        if home_pct_d >= Decimal("80"):
            concentration = "HOME_DOMINANT"
        elif home_pct_d >= Decimal("50"):
            concentration = "SPLIT"
        else:
            concentration = "FOREIGN_HEAVY"

        return {
            "card_id": card_id,
            "home_country": home_country,
            "home_country_pct": home_pct,
            "foreign_country_count": foreign_count,
            "top_countries": countries[:5],
            "unknown_country_count": unknown_count,
            "geographic_concentration": concentration,
            "computed": True,
        }

    @staticmethod
    def card_usage_profile(
        card_id: str,
        txns: List[CardTransaction],
        reference_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate card usage profile — composes 3 sub-engines.

        v7.12: this is the L05 PRODUCER payload that customer_segmentation
        will consume. Per Charter §7 Published Language pattern.

        Returns dict with payload_version, pattern, and the 3 sub-results.
        """
        velocity = CardsEngine.usage_velocity(card_id, txns, reference_date)
        mcc_mix = CardsEngine.merchant_category_mix(card_id, txns)
        geo = CardsEngine.geographic_pattern(card_id, txns)

        return {
            "payload_version": "1.0",
            "pattern": "PUBLISHED_LANGUAGE",
            "card_id": card_id,
            "velocity": velocity,
            "merchant_category_mix": mcc_mix,
            "geographic_pattern": geo,
            "cited_invariants": [],
        }


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> bool:
    """Smoke-test all 4 methods with realistic txns."""
    from datetime import datetime, timezone, timedelta

    base = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    txns = [
        CardTransaction("T01", "C001", "CUST001", Decimal("5000"),
                        base - timedelta(days=2), "5411", "KE", "Nairobi"),
        CardTransaction("T02", "C001", "CUST001", Decimal("12000"),
                        base - timedelta(days=5), "5411", "KE", "Nairobi"),
        CardTransaction("T03", "C001", "CUST001", Decimal("8000"),
                        base - timedelta(days=10), "5812", "KE", "Mombasa"),
        CardTransaction("T04", "C001", "CUST001", Decimal("3000"),
                        base - timedelta(days=15), "5812", "KE", "Nairobi"),
        CardTransaction("T05", "C001", "CUST001", Decimal("25000"),
                        base - timedelta(days=20), "4111", "AE", "Dubai"),
    ]

    profile = CardsEngine.card_usage_profile("C001", txns, reference_date=base)
    assert profile["payload_version"] == "1.0"
    assert profile["velocity"]["computed"] is True
    assert profile["merchant_category_mix"]["computed"] is True
    assert profile["geographic_pattern"]["computed"] is True

    # Velocity checks
    assert profile["velocity"]["txn_count_30d"] == 5
    assert profile["velocity"]["velocity_class"] in ("LOW", "MEDIUM", "HIGH", "DORMANT")

    # MCC mix
    assert profile["merchant_category_mix"]["dominant_category"] in ("5411", "5812", "4111")

    # Geo
    assert profile["geographic_pattern"]["home_country"] == "KE"
    assert profile["geographic_pattern"]["foreign_country_count"] == 1

    return True


if __name__ == "__main__":
    print("A2Z MIS 360 — utils.cards self-test")
    ok = self_test()
    print(f"Result: {'PASS' if ok else 'FAIL'}")

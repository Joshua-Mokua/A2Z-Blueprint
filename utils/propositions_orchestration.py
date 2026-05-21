"""
================================================================================
A2Z MIS 360 — Standard #353: Proposition Orchestration (Next Best Proposition)
================================================================================

Risk classification: Cat C (read-side composition over eligibility +
                              behavioral profile + pricing for ranked
                              per-customer recommendations)

Next-best-action engine for propositions. Per-customer ranked list.
Channel + timing optimization. Composes #351 eligibility + #340 behavioral
profile + #352 pricing.

Public API:
    next_best_propositions(customer_attrs, top_n=5, ml_score_fn=None)
        -> List of ranked propositions
    eligible_propositions_for_customer(customer_attrs)
        -> List of currently eligible propositions
    cross_sell_recommendations(customer_id, customer_attrs, top_n=3)
        -> NBA composition

ORCHESTRATION_RANKING_FACTORS byte-for-byte:
    ELIGIBILITY_PROVISIONAL_PENALTY  -- PROVISIONAL ranks below ELIGIBLE
    PROPENSITY_SCORE                  -- ML score from BehavioralProfileEngine
    CHANNEL_AVAILABILITY              -- match customer's preferred channel
    PRICE_FIT                          -- pricing aligns with customer balance/tier
    NOVELTY                            -- never-shown propositions get small boost

CHANNEL_PRIORITIES byte-for-byte (default channel ordering):
    MOBILE_APP, WEB, BRANCH, CALL_CENTER, EMAIL, SMS, USSD, ATM,
    CHATBOT, SOCIAL_MEDIA

Honesty rules:
    Rule 1: empty NBA list returns explicit reason rather than synthetic
    Rule 6: invalid customer_attrs (no customer_id) handled gracefully
    Rule 7: ranking blends rule-based + optional ml_score_fn (same factory
            pattern as v10.276 BehavioralProfileEngine.make_propensity_score_fn)

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.propositions_catalog import PropositionsCatalogEngine
from utils.propositions_eligibility import PropositionsEligibilityEngine
from utils.propositions_pricing import PropositionPricingEngine


ORCHESTRATION_RANKING_FACTORS: Tuple[str, ...] = (
    "ELIGIBILITY_PROVISIONAL_PENALTY",
    "PROPENSITY_SCORE",
    "CHANNEL_AVAILABILITY",
    "PRICE_FIT",
    "NOVELTY",
)

CHANNEL_PRIORITIES: Tuple[str, ...] = (
    "MOBILE_APP", "WEB", "BRANCH", "CALL_CENTER",
    "EMAIL", "SMS", "USSD", "ATM",
    "CHATBOT", "SOCIAL_MEDIA",
)

PROVISIONAL_PENALTY: Decimal = Decimal("20")
NOVELTY_BOOST: Decimal = Decimal("5")
CHANNEL_MATCH_BOOST: Decimal = Decimal("10")
PRICE_FIT_BOOST: Decimal = Decimal("10")


class PropositionOrchestrationEngine:
    """Per-customer NBA ranking over the active proposition catalog."""

    def __init__(
        self,
        catalog: Optional[PropositionsCatalogEngine] = None,
        eligibility: Optional[PropositionsEligibilityEngine] = None,
        pricing: Optional[PropositionPricingEngine] = None,
        impressions_path: Optional[Path] = None,
    ):
        self.catalog = catalog or PropositionsCatalogEngine()
        self.eligibility = eligibility or PropositionsEligibilityEngine(
            catalog=self.catalog,
        )
        self.pricing = pricing or PropositionPricingEngine(catalog=self.catalog)
        self.impressions_path = (
            impressions_path
            if impressions_path is not None
            else Path(__file__).parent.parent / "data"
                  / "proposition_impressions.json"
        )

    def _load_impressions(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.impressions_path,
                table="proposition_impressions",
                index_cols=("impression_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_impressions(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.impressions_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.impressions_path,
                data=records,
                table="proposition_impressions",
                pk_col="impression_id")
            return True
        except Exception:
            return False

    def eligible_propositions_for_customer(
        self,
        customer_attrs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Return all LIVE propositions that pass eligibility for this customer."""
        live = self.catalog.list_propositions(state="LIVE")
        out = []
        for prop in live:
            check = self.eligibility.check_eligibility(
                prop["proposition_id"], customer_attrs,
            )
            if check.get("eligible"):
                out.append({
                    "proposition_id": prop["proposition_id"],
                    "proposition": prop,
                    "eligibility": check,
                })
        return out

    def _has_been_shown(
        self,
        customer_id: str,
        prop_id: str,
        days_lookback: int = 30,
    ) -> bool:
        """Has this prop been shown to this customer in last N days?"""
        if not customer_id:
            return False
        records = self._load_impressions()
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=days_lookback)).isoformat()
        for r in records:
            if (r.get("customer_id") == customer_id
                    and r.get("proposition_id") == prop_id
                    and r.get("shown_at", "") >= cutoff):
                return True
        return False

    def next_best_propositions(
        self,
        customer_attrs: Dict[str, Any],
        top_n: int = 5,
        ml_score_fn: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Compute ranked NBA list for a customer."""
        cust_id = customer_attrs.get("customer_id")
        if not cust_id:
            return {
                "customer_id": None,
                "propositions": [],
                "reason": "missing_customer_id",
            }

        eligible_list = self.eligible_propositions_for_customer(customer_attrs)
        if not eligible_list:
            return {
                "customer_id": cust_id,
                "propositions": [],
                "reason": "no_eligible_propositions",
            }

        ranked = []
        for entry in eligible_list:
            prop = entry["proposition"]
            check = entry["eligibility"]
            prop_id = prop["proposition_id"]

            score = Decimal("50")  # baseline
            factors: List[str] = []

            # 1. Eligibility outcome — penalize PROVISIONAL
            if check.get("outcome") == "PROVISIONAL":
                score -= PROVISIONAL_PENALTY
                factors.append("provisional_-20")

            # 2. ML / propensity score
            if ml_score_fn is not None:
                try:
                    ml_score = ml_score_fn(prop_id, customer_attrs)
                    score = (score + Decimal(str(ml_score))) / Decimal("2")
                    factors.append(f"ml_score_{ml_score}_blended")
                except Exception:
                    factors.append("ml_score_error_skipped")

            # 3. Channel availability boost
            cust_channel = customer_attrs.get("preferred_channel")
            prop_channels = prop.get("channels", [])
            if cust_channel and cust_channel in prop_channels:
                score += CHANNEL_MATCH_BOOST
                factors.append(f"channel_match_{cust_channel}_+10")

            # 4. Price fit — if customer has spending_tier and pricing exists
            tier = customer_attrs.get("spending_tier")
            try:
                price_result = self.pricing.compute_price(
                    prop_id,
                    {**customer_attrs},
                )
                if price_result.get("price_kes"):
                    factors.append(f"price_{price_result['price_kes']}_kes")
                    # If LOW spender getting discount → boost (price fit)
                    if (tier == "LOW"
                            and "fallback_LOW" in str(price_result.get("factors", []))):
                        score += PRICE_FIT_BOOST
                        factors.append("price_fit_low_tier_+10")
            except Exception:
                pass

            # 5. Novelty — never-shown propositions get a small boost
            if not self._has_been_shown(cust_id, prop_id):
                score += NOVELTY_BOOST
                factors.append("novelty_+5")

            # Cap at 100
            score = min(score, Decimal("100"))
            score = max(score, Decimal("0"))

            ranked.append({
                "proposition_id": prop_id,
                "name": prop.get("name"),
                "score": str(score.quantize(Decimal("0.01"))),
                "factors": factors,
                "eligibility_outcome": check.get("outcome"),
                "preferred_channel_for_customer":
                    cust_channel if cust_channel in prop_channels
                    else (prop_channels[0] if prop_channels else None),
                "available_channels": list(prop_channels),
            })

        # Sort by score desc
        ranked.sort(key=lambda x: Decimal(x["score"]), reverse=True)
        return {
            "customer_id": cust_id,
            "ranked_count": len(ranked),
            "propositions": ranked[:top_n],
            "ranking_factors": list(ORCHESTRATION_RANKING_FACTORS),
        }

    def record_impression(
        self,
        customer_id: str,
        proposition_id: str,
        channel: str,
        actor: str,
        outcome: str = "SHOWN",
    ) -> Dict[str, Any]:
        """Record that a proposition was shown to a customer."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if not customer_id or not proposition_id:
            return {"recorded": False, "error": "customer_and_prop_required"}

        records = self._load_impressions()
        impression_id = (f"IMP-{customer_id}-{proposition_id}-"
                            f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "impression_id": impression_id,
            "customer_id": customer_id,
            "proposition_id": proposition_id,
            "channel": channel,
            "outcome": outcome,
            "actor": actor,
            "shown_at": datetime.utcnow().isoformat(),
        })
        ok = self._save_impressions(records)
        return {"recorded": ok, "impression_id": impression_id}

    def cross_sell_recommendations(
        self,
        customer_attrs: Dict[str, Any],
        top_n: int = 3,
        ml_score_fn: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """NBA filtered to propositions targeting customer's segment + tier."""
        result = self.next_best_propositions(
            customer_attrs, top_n=top_n, ml_score_fn=ml_score_fn,
        )
        # Strict filter: only ELIGIBLE (not PROVISIONAL) for cross-sell
        result["propositions"] = [
            p for p in result.get("propositions", [])
            if p.get("eligibility_outcome") == "ELIGIBLE"
        ][:top_n]
        return result


def _self_test() -> None:
    import tempfile
    from utils.propositions_catalog import APPROVAL_LEVELS

    assert "PROPENSITY_SCORE" in ORCHESTRATION_RANKING_FACTORS
    assert "MOBILE_APP" in CHANNEL_PRIORITIES

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )
        eligibility = PropositionsEligibilityEngine(catalog=catalog)
        pricing = PropositionPricingEngine(
            catalog=catalog,
            strategies_path=Path(tmpdir) / "s.json",
            decisions_path=Path(tmpdir) / "d.json",
        )
        engine = PropositionOrchestrationEngine(
            catalog=catalog, eligibility=eligibility, pricing=pricing,
            impressions_path=Path(tmpdir) / "imp.json",
        )

        # Setup 3 propositions, all live
        def _make_live(prop_id, name, segments, channels, base_price="1000"):
            catalog.register_proposition(
                {"proposition_id": prop_id, "name": name,
                 "owner_role": "head",
                 "channels": channels,
                 "target_segments": segments,
                 "eligibility_criteria": {"min_age": 18}},
                actor="x",
            )
            catalog.submit_for_review(prop_id, actor="x", reason="r")
            catalog.submit_for_approval(prop_id, actor="x", reason="r")
            for level in APPROVAL_LEVELS:
                catalog.record_approval(prop_id, level, "APPROVED",
                                              actor="x", reason="r")
            catalog.activate_proposition(prop_id, actor="x", reason="launch")
            # Add pricing
            pricing.register_pricing_strategy(
                prop_id,
                {"strategy_id": f"STR-{prop_id}",
                 "strategy_type": "FLAT",
                 "base_price_kes": base_price},
                actor="finance", reason="initial",
            )
            pricing.transition_strategy_state(
                f"STR-{prop_id}", "ACTIVE", actor="finance", reason="go",
            )

        _make_live("PROP-DIASP", "Diaspora Wealth",
                      ["DIASPORA"], ["MOBILE_APP", "BRANCH"])
        _make_live("PROP-YOUTH", "Youth Saver",
                      ["YOUTH"], ["MOBILE_APP", "USSD"])
        _make_live("PROP-ANY", "Universal Account",
                      [], ["MOBILE_APP", "WEB", "BRANCH"])

        # Test 1: NBA for diaspora customer
        nba = engine.next_best_propositions({
            "customer_id": "C-DIASP",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
            "spending_tier": "MEDIUM",
        }, top_n=5)
        # Should be eligible for PROP-DIASP and PROP-ANY (not PROP-YOUTH)
        prop_ids = {p["proposition_id"] for p in nba["propositions"]}
        assert "PROP-DIASP" in prop_ids
        assert "PROP-ANY" in prop_ids
        assert "PROP-YOUTH" not in prop_ids

        # Test 2: missing customer_id
        nba = engine.next_best_propositions({})
        assert nba["reason"] == "missing_customer_id"

        # Test 3: customer with no eligible propositions
        nba = engine.next_best_propositions({
            "customer_id": "C-MINOR",
            "kyc_status": "COMPLETE",
            "age": 10,
            "aml_status": "CLEARED",
            "balance_kes": "0",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "CONSERVATIVE",
        })
        assert nba["reason"] == "no_eligible_propositions"

        # Test 4: record impression + novelty erodes
        engine.record_impression(
            "C-DIASP", "PROP-DIASP", "MOBILE_APP",
            actor="orchestrator",
        )
        nba2 = engine.next_best_propositions({
            "customer_id": "C-DIASP",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
            "spending_tier": "MEDIUM",
        }, top_n=5)
        # PROP-DIASP no longer gets novelty boost
        diasp_entry = next(
            p for p in nba2["propositions"]
            if p["proposition_id"] == "PROP-DIASP"
        )
        # Should not include "novelty_+5" in factors
        assert not any("novelty" in f for f in diasp_entry["factors"])

        # Test 5: with ml_score_fn — high score lifts ranking
        def fake_ml(prop_id, attrs):
            if prop_id == "PROP-DIASP":
                return Decimal("90")
            return Decimal("30")

        nba_ml = engine.next_best_propositions({
            "customer_id": "C-DIASP-ML",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
            "spending_tier": "MEDIUM",
        }, ml_score_fn=fake_ml)
        # PROP-DIASP should rank higher than PROP-ANY due to ML score
        first = nba_ml["propositions"][0]
        assert first["proposition_id"] == "PROP-DIASP"

        # Test 6: cross_sell — only ELIGIBLE
        cs = engine.cross_sell_recommendations({
            "customer_id": "C-DIASP",
            "kyc_status": "COMPLETE",
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
            "spending_tier": "MEDIUM",
        })
        for p in cs["propositions"]:
            assert p["eligibility_outcome"] == "ELIGIBLE"

        # Test 7: PROVISIONAL gets penalty
        nba_prov = engine.next_best_propositions({
            "customer_id": "C-PROV",
            "kyc_status": "PENDING",  # → PROVISIONAL
            "segment": "DIASPORA",
            "age": 35,
            "aml_status": "CLEARED",
            "balance_kes": "200000",
            "preferred_channel": "MOBILE_APP",
            "risk_appetite": "MODERATE",
            "spending_tier": "MEDIUM",
        })
        for p in nba_prov["propositions"]:
            assert p["eligibility_outcome"] == "PROVISIONAL"
            assert any("provisional" in f for f in p["factors"])

    print("  ✅ propositions_orchestration self-test PASS")


if __name__ == "__main__":
    _self_test()

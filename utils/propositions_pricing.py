"""
================================================================================
A2Z MIS 360 — Standard #352: Dynamic Pricing for Propositions
================================================================================

Risk classification: Cat A (financial — fairness + compliance guardrails on
                              customer-facing pricing decisions)
                     + Rule 7 ML hook factory

ML-driven pricing per customer + market conditions. A/B test pricing
strategies. Fairness + compliance guardrails. v10.277 ships deterministic
pricing strategies + Rule 7 make_dynamic_price_fn factory consumable by
proposition orchestration / external pricing endpoints. Fairness rails
applied as floor/ceiling enforcement and audit trail.

Public API:
    register_pricing_strategy(prop_id, strategy_data, actor, reason)
    activate_strategy(prop_id, strategy_id, actor, reason)
    compute_price(prop_id, customer_attrs, ml_price_fn=None)
        -> {price_kes, strategy_used, factors, fairness_check}
    fairness_audit(prop_id, period_start, period_end) -> distribution + flags
    make_dynamic_price_fn(behavioral_profile=None) -> Callable

PRICING_STRATEGIES byte-for-byte:
    FLAT             -- single price for all eligible customers
    SEGMENT_TIERED   -- price varies by customer segment
    BEHAVIORAL_TIERED -- price varies by spending tier (HIGH/MEDIUM/LOW)
    DYNAMIC_ML       -- ML hook driven (with deterministic fallback)
    PROMOTIONAL      -- time-bound discount (start_date + end_date)

PRICING_STATES byte-for-byte:
    DRAFT       -- pricing strategy created
    ACTIVE      -- live, applied to eligibility decisions
    SUPERSEDED  -- replaced by a newer strategy (terminal)
    ARCHIVED    -- archived (terminal)

ALLOWED_PRICING_TRANSITIONS (Rule 4):
    DRAFT      → ACTIVE | ARCHIVED
    ACTIVE     → SUPERSEDED | ARCHIVED
    SUPERSEDED → ARCHIVED
    ARCHIVED   → ()  -- terminal

FAIRNESS_GUARDRAILS byte-for-byte:
    FLOOR_PCT    -- minimum price as % of base (e.g. 50% = max 50% discount)
    CEILING_PCT  -- maximum price as % of base (e.g. 200% = max 2x markup)
    MAX_VARIANCE_PCT -- max ratio of highest-to-lowest customer price

DEFAULT_FLOOR_PCT = 50  -- minimum 50% of base
DEFAULT_CEILING_PCT = 200  -- maximum 200% of base
DEFAULT_MAX_VARIANCE_PCT = 400  -- highest customer ≤ 4x lowest customer

Rule 7 hook contract:
    fn(prop_id, customer_attrs, base_price_kes) -> Decimal (final price KES)
    Hook output is clamped to fairness floor/ceiling before return.

Honesty rules:
    Rule 1: pricing decisions return explicit `factors` showing which
            input drove the price; never opaque
    Rule 4: actor + reason mandatory on strategy lifecycle transitions
    Rule 6: invalid strategy_type / state rejected
    Rule 7: SPEC_DEVIATION_NOTE — production ML pricing requires labeled
            historical pricing-elasticity data, deferred

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.propositions_catalog import PropositionsCatalogEngine


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #352 specifies ML-driven pricing per customer + "
    "market conditions. v10.277 ships deterministic pricing strategies "
    "(FLAT, SEGMENT_TIERED, BEHAVIORAL_TIERED, PROMOTIONAL) + Rule 7 "
    "make_dynamic_price_fn factory returning a callable. Production ML "
    "pricing requires labeled historical pricing-elasticity data + "
    "supervised model with fairness constraints, deferred to deployment "
    "phase. The deterministic DYNAMIC_ML fallback applies behavioral "
    "tier (HIGH=1.0x, MEDIUM=1.0x, LOW=0.9x discount for engagement) "
    "until ML lands. All pricing decisions are clamped to fairness "
    "guardrails (FLOOR_PCT=50, CEILING_PCT=200, MAX_VARIANCE_PCT=400)."
)


PRICING_STRATEGIES: Tuple[str, ...] = (
    "FLAT", "SEGMENT_TIERED", "BEHAVIORAL_TIERED",
    "DYNAMIC_ML", "PROMOTIONAL",
)

PRICING_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "SUPERSEDED", "ARCHIVED",
)

ALLOWED_PRICING_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("SUPERSEDED", "ARCHIVED"),
    "SUPERSEDED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

FAIRNESS_GUARDRAILS: Tuple[str, ...] = (
    "FLOOR_PCT", "CEILING_PCT", "MAX_VARIANCE_PCT",
)

DEFAULT_FLOOR_PCT: int = 50
DEFAULT_CEILING_PCT: int = 200
DEFAULT_MAX_VARIANCE_PCT: int = 400


class PropositionPricingEngine:
    """Pricing strategy registry + dynamic price computation."""

    def __init__(
        self,
        catalog: Optional[PropositionsCatalogEngine] = None,
        strategies_path: Optional[Path] = None,
        decisions_path: Optional[Path] = None,
    ):
        self.catalog = catalog or PropositionsCatalogEngine()
        base = Path(__file__).parent.parent / "data"
        self.strategies_path = strategies_path or base / "pricing_strategies.json"
        self.decisions_path = decisions_path or base / "pricing_decisions.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def register_pricing_strategy(
        self,
        prop_id: str,
        strategy_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("strategy_id", "strategy_type", "base_price_kes"):
            if f not in strategy_data or strategy_data[f] is None:
                return {"registered": False, "error": f"missing_field:{f}"}
        if strategy_data["strategy_type"] not in PRICING_STRATEGIES:
            return {
                "registered": False,
                "error": f"invalid_strategy_type:{strategy_data['strategy_type']}",
                "valid_types": list(PRICING_STRATEGIES),
            }
        try:
            base_price = Decimal(str(strategy_data["base_price_kes"]))
            if base_price < 0:
                return {"registered": False, "error": "base_price_negative"}
        except (ValueError, TypeError):
            return {"registered": False, "error": "invalid_base_price_format"}

        records = self._load(self.strategies_path,
                                "pricing_strategies", ("strategy_id",))
        if any(r.get("strategy_id") == strategy_data["strategy_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_strategy_id"}

        record = {
            "strategy_id": strategy_data["strategy_id"],
            "proposition_id": prop_id,
            "strategy_type": strategy_data["strategy_type"],
            "base_price_kes": str(base_price.quantize(Decimal("0.01"))),
            "segment_prices_kes": strategy_data.get("segment_prices_kes", {}),
            "behavioral_tier_multipliers": strategy_data.get(
                "behavioral_tier_multipliers", {}),
            "promotional_start": strategy_data.get("promotional_start"),
            "promotional_end": strategy_data.get("promotional_end"),
            "promotional_discount_pct": strategy_data.get(
                "promotional_discount_pct", 0),
            "fairness_floor_pct": strategy_data.get(
                "fairness_floor_pct", DEFAULT_FLOOR_PCT),
            "fairness_ceiling_pct": strategy_data.get(
                "fairness_ceiling_pct", DEFAULT_CEILING_PCT),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(self.strategies_path, records,
                          "pricing_strategies", "strategy_id")
        return {"registered": ok,
                  "strategy_id": strategy_data["strategy_id"]}

    def transition_strategy_state(
        self,
        strategy_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in PRICING_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.strategies_path,
                                "pricing_strategies", ("strategy_id",))
        for r in records:
            if r.get("strategy_id") == strategy_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_PRICING_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.strategies_path, records,
                                  "pricing_strategies", "strategy_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "strategy_not_found"}

    def get_active_strategy(
        self, prop_id: str,
    ) -> Optional[Dict[str, Any]]:
        records = self._load(self.strategies_path,
                                "pricing_strategies", ("strategy_id",))
        for r in records:
            if (r.get("proposition_id") == prop_id
                    and r.get("state") == "ACTIVE"):
                return r
        return None

    def _apply_fairness(
        self, price: Decimal, base: Decimal,
        floor_pct: int, ceiling_pct: int,
    ) -> Tuple[Decimal, str]:
        floor = base * Decimal(floor_pct) / Decimal("100")
        ceiling = base * Decimal(ceiling_pct) / Decimal("100")
        if price < floor:
            return floor, f"clamped_to_floor_{floor_pct}_pct"
        if price > ceiling:
            return ceiling, f"clamped_to_ceiling_{ceiling_pct}_pct"
        return price, "within_fairness_band"

    def compute_price(
        self,
        prop_id: str,
        customer_attrs: Dict[str, Any],
        ml_price_fn: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        strategy = self.get_active_strategy(prop_id)
        if strategy is None:
            return {
                "prop_id": prop_id,
                "price_kes": None,
                "reason": "no_active_pricing_strategy",
            }

        base = Decimal(strategy["base_price_kes"])
        strategy_type = strategy["strategy_type"]
        floor_pct = strategy.get("fairness_floor_pct", DEFAULT_FLOOR_PCT)
        ceiling_pct = strategy.get("fairness_ceiling_pct", DEFAULT_CEILING_PCT)

        price = base
        factors: List[str] = []

        if strategy_type == "FLAT":
            price = base
            factors.append("flat_base")
        elif strategy_type == "SEGMENT_TIERED":
            seg = customer_attrs.get("segment")
            seg_prices = strategy.get("segment_prices_kes", {})
            if seg and seg in seg_prices:
                try:
                    price = Decimal(str(seg_prices[seg]))
                    factors.append(f"segment_{seg}")
                except (ValueError, TypeError):
                    factors.append(f"segment_{seg}_invalid_price_fallback_base")
            else:
                factors.append("segment_not_in_tiers_fallback_base")
        elif strategy_type == "BEHAVIORAL_TIERED":
            tier = customer_attrs.get("spending_tier")
            multipliers = strategy.get("behavioral_tier_multipliers", {})
            mult = multipliers.get(tier, "1.0")
            try:
                price = base * Decimal(str(mult))
                factors.append(f"tier_{tier}_mult_{mult}")
            except (ValueError, TypeError):
                factors.append(f"tier_{tier}_invalid_mult_fallback_base")
        elif strategy_type == "DYNAMIC_ML":
            if ml_price_fn is not None:
                try:
                    p = ml_price_fn(prop_id, customer_attrs, base)
                    price = Decimal(str(p))
                    factors.append("ml_price_fn_applied")
                except Exception:
                    factors.append("ml_price_fn_error_fallback_base")
            else:
                # Deterministic fallback per SPEC_DEVIATION_NOTE
                tier = customer_attrs.get("spending_tier")
                if tier == "LOW":
                    price = base * Decimal("0.9")
                    factors.append("dynamic_ml_fallback_LOW_-10_pct")
                else:
                    price = base
                    factors.append("dynamic_ml_fallback_base")
        elif strategy_type == "PROMOTIONAL":
            today = date.today().isoformat()
            ps = strategy.get("promotional_start", "")
            pe = strategy.get("promotional_end", "")
            disc = Decimal(str(strategy.get("promotional_discount_pct", 0)))
            if ps and pe and ps <= today <= pe:
                price = base * (Decimal("100") - disc) / Decimal("100")
                factors.append(
                    f"promotional_active_-{disc}_pct"
                )
            else:
                price = base
                factors.append("promotional_outside_window_base")

        # Apply fairness guardrails
        clamped, fairness_note = self._apply_fairness(
            price, base, floor_pct, ceiling_pct,
        )

        result = {
            "prop_id": prop_id,
            "customer_id": customer_attrs.get("customer_id"),
            "price_kes": str(clamped.quantize(Decimal("0.01"))),
            "base_price_kes": str(base.quantize(Decimal("0.01"))),
            "strategy_type": strategy_type,
            "strategy_id": strategy["strategy_id"],
            "factors": factors,
            "fairness_check": fairness_note,
            "computed_at": datetime.utcnow().isoformat(),
        }

        # Audit trail
        decisions = self._load(self.decisions_path,
                                   "pricing_decisions", ("decision_id",))
        decisions.append({
            "decision_id": (f"PRC-{prop_id}-"
                                f"{customer_attrs.get('customer_id', 'X')}-"
                                f"{int(datetime.utcnow().timestamp() * 1000)}"),
            **result,
        })
        self._save(self.decisions_path, decisions,
                     "pricing_decisions", "decision_id")

        return result

    def fairness_audit(
        self,
        prop_id: str,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Audit pricing decisions for fairness violations + variance."""
        records = self._load(self.decisions_path,
                                "pricing_decisions", ("decision_id",))
        in_period = [
            r for r in records
            if r.get("prop_id") == prop_id
            and period_start <= r.get("computed_at", "") <= period_end
        ]
        if not in_period:
            return {
                "prop_id": prop_id,
                "decision_count": 0,
                "reason": "no_decisions_in_period",
            }

        prices: List[Decimal] = []
        clamped_count = 0
        for r in in_period:
            try:
                prices.append(Decimal(r["price_kes"]))
            except (ValueError, TypeError, KeyError):
                continue
            if "clamped" in r.get("fairness_check", ""):
                clamped_count += 1

        if not prices:
            return {"prop_id": prop_id, "decision_count": 0}

        min_p = min(prices)
        max_p = max(prices)
        variance_ratio = (
            (max_p / min_p * Decimal("100")).quantize(Decimal("0.01"))
            if min_p > 0 else None
        )
        variance_violation = (
            variance_ratio is not None
            and variance_ratio > Decimal(DEFAULT_MAX_VARIANCE_PCT)
        )

        return {
            "prop_id": prop_id,
            "period_start": period_start,
            "period_end": period_end,
            "decision_count": len(in_period),
            "min_price_kes": str(min_p),
            "max_price_kes": str(max_p),
            "variance_ratio_pct": str(variance_ratio) if variance_ratio else None,
            "max_variance_threshold_pct": DEFAULT_MAX_VARIANCE_PCT,
            "variance_violation": variance_violation,
            "clamped_decisions": clamped_count,
        }

    def make_dynamic_price_fn(
        self,
        behavioral_profile: Optional[Any] = None,
    ) -> Callable[[str, Dict[str, Any], Decimal], Decimal]:
        """Returns a Callable matching the DYNAMIC_ML strategy's hook.

        Signature: fn(prop_id, customer_attrs, base_price) -> Decimal
        Behavioral_profile parameter accepts a v10.276 BehavioralProfileEngine
        for richer scoring; fallback uses customer_attrs alone.
        """
        engine_self = self

        def _dynamic_price_fn(
            prop_id: str,
            customer_attrs: Dict[str, Any],
            base_price: Decimal,
        ) -> Decimal:
            tier = customer_attrs.get("spending_tier")
            # If no tier in attrs but we have behavioral_profile + customer_id,
            # derive tier from the profile engine
            if tier is None and behavioral_profile is not None:
                cid = customer_attrs.get("customer_id")
                if cid:
                    try:
                        tier_result = behavioral_profile.spending_tier(cid)
                        tier = tier_result.get("tier")
                    except Exception:
                        tier = None

            # Deterministic heuristic: HIGH spenders pay full base (premium pricing
            # would require ML); LOW gets 10% engagement discount; MEDIUM = base.
            if tier == "LOW":
                return base_price * Decimal("0.9")
            if tier == "HIGH":
                return base_price  # do NOT charge HIGH spenders premium without ML
            return base_price  # MEDIUM / UNKNOWN → base

        return _dynamic_price_fn


def _self_test() -> None:
    import tempfile

    assert "DYNAMIC_ML" in PRICING_STRATEGIES
    assert ALLOWED_PRICING_TRANSITIONS["ARCHIVED"] == ()
    assert "v10.277" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )
        engine = PropositionPricingEngine(
            catalog=catalog,
            strategies_path=Path(tmpdir) / "s.json",
            decisions_path=Path(tmpdir) / "d.json",
        )

        # Setup proposition
        catalog.register_proposition(
            {"proposition_id": "PROP-X", "name": "X",
             "owner_role": "h"},
            actor="x",
        )

        # Test 1: register FLAT pricing
        r = engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-1",
             "strategy_type": "FLAT",
             "base_price_kes": "1000"},
            actor="finance", reason="initial flat pricing",
        )
        assert r["registered"]

        # Test 2: invalid strategy_type
        r = engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-X",
             "strategy_type": "INVALID",
             "base_price_kes": "1000"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 3: negative price
        r = engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-X",
             "strategy_type": "FLAT",
             "base_price_kes": "-100"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 4: state lifecycle
        t = engine.transition_strategy_state(
            "STR-1", "ACTIVE", actor="finance", reason="go live",
        )
        assert t["transitioned"]

        # Test 5: skip rejected (DRAFT → SUPERSEDED)
        engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-2",
             "strategy_type": "FLAT",
             "base_price_kes": "1000"},
            actor="finance", reason="draft 2",
        )
        t = engine.transition_strategy_state(
            "STR-2", "SUPERSEDED", actor="x", reason="x",
        )
        assert not t["transitioned"]

        # Test 6: compute FLAT price
        p = engine.compute_price(
            "PROP-X",
            {"customer_id": "C1", "segment": "DIASPORA"},
        )
        assert Decimal(p["price_kes"]) == Decimal("1000.00")
        assert p["strategy_type"] == "FLAT"

        # Test 7: compute SEGMENT_TIERED
        engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-SEG",
             "strategy_type": "SEGMENT_TIERED",
             "base_price_kes": "1000",
             "segment_prices_kes": {"DIASPORA": "800", "YOUTH": "500"}},
            actor="finance", reason="segment tiered",
        )
        # Supersede STR-1
        engine.transition_strategy_state(
            "STR-1", "SUPERSEDED", actor="finance", reason="replaced",
        )
        engine.transition_strategy_state(
            "STR-SEG", "ACTIVE", actor="finance", reason="go live",
        )
        p = engine.compute_price(
            "PROP-X", {"customer_id": "C1", "segment": "DIASPORA"},
        )
        assert Decimal(p["price_kes"]) == Decimal("800.00")
        p = engine.compute_price(
            "PROP-X", {"customer_id": "C2", "segment": "YOUTH"},
        )
        assert Decimal(p["price_kes"]) == Decimal("500.00")

        # Test 8: BEHAVIORAL_TIERED
        engine.transition_strategy_state(
            "STR-SEG", "SUPERSEDED", actor="finance", reason="x",
        )
        engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-TIER",
             "strategy_type": "BEHAVIORAL_TIERED",
             "base_price_kes": "1000",
             "behavioral_tier_multipliers": {
                 "HIGH": "1.0", "MEDIUM": "1.0", "LOW": "0.8",
             }},
            actor="finance", reason="behavioral",
        )
        engine.transition_strategy_state(
            "STR-TIER", "ACTIVE", actor="finance", reason="x",
        )
        p = engine.compute_price(
            "PROP-X", {"customer_id": "C-LOW", "spending_tier": "LOW"},
        )
        assert Decimal(p["price_kes"]) == Decimal("800.00")  # 1000 * 0.8

        # Test 9: DYNAMIC_ML with ml_price_fn provided
        engine.transition_strategy_state(
            "STR-TIER", "SUPERSEDED", actor="x", reason="x",
        )
        engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-ML",
             "strategy_type": "DYNAMIC_ML",
             "base_price_kes": "1000"},
            actor="finance", reason="ml-driven",
        )
        engine.transition_strategy_state(
            "STR-ML", "ACTIVE", actor="finance", reason="x",
        )
        ml_fn = engine.make_dynamic_price_fn()
        p = engine.compute_price(
            "PROP-X",
            {"customer_id": "C-LOW", "spending_tier": "LOW"},
            ml_price_fn=ml_fn,
        )
        # 1000 * 0.9 = 900 (engagement discount)
        assert Decimal(p["price_kes"]) == Decimal("900.00")

        # Test 10: DYNAMIC_ML without ml_fn (fallback)
        p = engine.compute_price(
            "PROP-X",
            {"customer_id": "C-MED", "spending_tier": "MEDIUM"},
        )
        # MEDIUM tier in fallback = base
        assert Decimal(p["price_kes"]) == Decimal("1000.00")
        assert "fallback" in str(p["factors"])

        # Test 11: PROMOTIONAL
        engine.transition_strategy_state(
            "STR-ML", "SUPERSEDED", actor="x", reason="x",
        )
        engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-PROMO",
             "strategy_type": "PROMOTIONAL",
             "base_price_kes": "1000",
             "promotional_start": "2026-01-01",
             "promotional_end": "2027-12-31",
             "promotional_discount_pct": 25},
            actor="finance", reason="quarterly promo",
        )
        engine.transition_strategy_state(
            "STR-PROMO", "ACTIVE", actor="finance", reason="x",
        )
        p = engine.compute_price(
            "PROP-X", {"customer_id": "C-PROMO"},
        )
        # 1000 * 0.75 = 750
        assert Decimal(p["price_kes"]) == Decimal("750.00")

        # Test 12: fairness clamping (ceiling)
        # Hand-craft a strategy that would otherwise exceed ceiling
        # PROMOTIONAL with negative discount → exceeds base. Use BEHAVIORAL.
        engine.transition_strategy_state(
            "STR-PROMO", "SUPERSEDED", actor="x", reason="x",
        )
        engine.register_pricing_strategy(
            "PROP-X",
            {"strategy_id": "STR-EXTREME",
             "strategy_type": "BEHAVIORAL_TIERED",
             "base_price_kes": "1000",
             "behavioral_tier_multipliers": {"HIGH": "5.0"},
             "fairness_floor_pct": 50,
             "fairness_ceiling_pct": 200},
            actor="finance", reason="ceiling test",
        )
        engine.transition_strategy_state(
            "STR-EXTREME", "ACTIVE", actor="finance", reason="x",
        )
        p = engine.compute_price(
            "PROP-X", {"customer_id": "C-HIGH", "spending_tier": "HIGH"},
        )
        # Would be 5000 but ceiling clamps to 2000 (200% of base)
        assert Decimal(p["price_kes"]) == Decimal("2000.00")
        assert "clamped_to_ceiling" in p["fairness_check"]

        # Test 13: no active strategy
        catalog.register_proposition(
            {"proposition_id": "PROP-NO-PRICE", "name": "Y",
             "owner_role": "h"},
            actor="x",
        )
        p = engine.compute_price(
            "PROP-NO-PRICE", {"customer_id": "C1"},
        )
        assert p["price_kes"] is None
        assert p["reason"] == "no_active_pricing_strategy"

        # Test 14: fairness_audit
        audit = engine.fairness_audit(
            "PROP-X", "2026-01-01", "2027-12-31",
        )
        assert audit["decision_count"] >= 5

        # Test 15: empty audit period
        a = engine.fairness_audit(
            "PROP-X", "1900-01-01", "1900-12-31",
        )
        assert a["decision_count"] == 0

    print("  ✅ propositions_pricing self-test PASS")


if __name__ == "__main__":
    _self_test()

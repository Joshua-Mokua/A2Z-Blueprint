"""
================================================================================
A2Z MIS 360 — Standard #103: IFRS 13 Fair Value Measurement Engine
================================================================================

Risk classification: Cat B (deterministic IFRS 13 hierarchy classification +
                            mid-price computation + transfer detection)

Provides:
    - hierarchy_level(...)               -- LEVEL_1 / LEVEL_2 / LEVEL_3
    - validate_valuation_technique(...)  -- MARKET / INCOME / COST approach
    - mid_price(...)                     -- bid-ask midpoint for Level 1
    - transfer_detection(...)            -- inter-level transfer
    - disclosure_pack(...)               -- disclosure requirements per level
    - bid_ask_spread_pct(...)            -- liquidity proxy

3 FAIR_VALUE_HIERARCHY_LEVELS byte-for-byte (IFRS 13.72-90):
    LEVEL_1   -- quoted prices in active markets (most reliable)
    LEVEL_2   -- observable inputs other than Level 1 (yield curves, rates)
    LEVEL_3   -- unobservable inputs (model-derived, illiquid)

3 VALUATION_TECHNIQUES byte-for-byte (IFRS 13.62):
    MARKET_APPROACH    -- prices from market transactions
    INCOME_APPROACH    -- DCF / option pricing (PV of future cash flows)
    COST_APPROACH      -- replacement cost

3 INPUT_OBSERVABILITY byte-for-byte:
    QUOTED_ACTIVE_MARKET, OBSERVABLE_OTHER, UNOBSERVABLE

5 LEVEL_3_INPUTS byte-for-byte (common unobservable inputs):
    PROBABILITY_OF_DEFAULT, LOSS_GIVEN_DEFAULT, ILLIQUIDITY_DISCOUNT,
    MODEL_PARAMETER, BLOCKAGE_DISCOUNT

3 TRANSFER_TYPES byte-for-byte:
    INTO_LEVEL_3       -- becomes more illiquid (worse)
    OUT_OF_LEVEL_3     -- becomes more liquid (better)
    INTER_LEVEL        -- between Level 1 and Level 2

Bid-ask spread thresholds byte-for-byte:
    HIGHLY_LIQUID_BID_ASK_PCT_MAX = 0.5     -- ≤0.5% spread = highly liquid
    LIQUID_BID_ASK_PCT_MAX        = 2       -- 0.5-2% = liquid
    -- > 2% spread = illiquid (Level 1 status questionable)

Honesty rules applied:
    Rule 1: mid_price=None when bid or ask missing
            spread_pct=None when bid is zero
    Rule 6: unknown valuation_technique / observability surfaced
            negative spread (bid > ask) rejected (fail closed)

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 FAIR VALUE HIERARCHY LEVELS byte-for-byte (IFRS 13)
FAIR_VALUE_HIERARCHY_LEVELS: Tuple[str, ...] = (
    "LEVEL_1", "LEVEL_2", "LEVEL_3",
)

# 3 VALUATION TECHNIQUES byte-for-byte (IFRS 13.62)
VALUATION_TECHNIQUES: Tuple[str, ...] = (
    "MARKET_APPROACH", "INCOME_APPROACH", "COST_APPROACH",
)

# 3 INPUT OBSERVABILITY categories byte-for-byte
INPUT_OBSERVABILITY: Tuple[str, ...] = (
    "QUOTED_ACTIVE_MARKET", "OBSERVABLE_OTHER", "UNOBSERVABLE",
)

# 5 LEVEL 3 INPUTS byte-for-byte
LEVEL_3_INPUTS: Tuple[str, ...] = (
    "PROBABILITY_OF_DEFAULT", "LOSS_GIVEN_DEFAULT", "ILLIQUIDITY_DISCOUNT",
    "MODEL_PARAMETER", "BLOCKAGE_DISCOUNT",
)

# 3 TRANSFER TYPES byte-for-byte
TRANSFER_TYPES: Tuple[str, ...] = (
    "INTO_LEVEL_3", "OUT_OF_LEVEL_3", "INTER_LEVEL",
)

# Liquidity thresholds byte-for-byte (bid-ask spread %)
HIGHLY_LIQUID_BID_ASK_PCT_MAX = Decimal("0.5")
LIQUID_BID_ASK_PCT_MAX = Decimal("2")


class FairValueEngine:
    """Deterministic IFRS 13 fair value hierarchy + measurement support."""

    @staticmethod
    def hierarchy_level(
        observability: str,
    ) -> Optional[str]:
        """
        Map input observability to hierarchy level.
        Rule 6: unknown observability returns None.
        """
        if observability not in INPUT_OBSERVABILITY:
            return None
        if observability == "QUOTED_ACTIVE_MARKET":
            return "LEVEL_1"
        if observability == "OBSERVABLE_OTHER":
            return "LEVEL_2"
        return "LEVEL_3"

    @staticmethod
    def validate_valuation_technique(technique: str) -> Dict[str, Any]:
        """Rule 6: unknown technique rejected."""
        if technique not in VALUATION_TECHNIQUES:
            return {"valid": False,
                    "reason": f"unknown_technique:{technique}",
                    "valid_techniques": list(VALUATION_TECHNIQUES)}
        return {"valid": True, "technique": technique}

    @staticmethod
    def mid_price(
        bid: Optional[Decimal],
        ask: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Bid-ask midpoint for Level 1 measurement.
        Rule 1: None when either missing.
        Rule 6: bid > ask rejected (fail closed).
        """
        if bid is None or ask is None:
            return {"mid": None, "computed": False,
                    "reason": "missing_bid_or_ask"}
        if bid > ask:
            return {"mid": None, "computed": False,
                    "reason": "bid_exceeds_ask"}
        if bid < 0 or ask < 0:
            return {"mid": None, "computed": False,
                    "reason": "negative_price"}
        mid = (bid + ask) / Decimal("2")
        return {
            "bid": str(bid),
            "ask": str(ask),
            "mid": str(mid.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def bid_ask_spread_pct(
        bid: Optional[Decimal],
        ask: Optional[Decimal],
    ) -> Optional[Decimal]:
        """
        Spread% = (ask - bid) / bid × 100.
        Rule 1: None when bid=0 or missing.
        """
        if bid is None or ask is None or bid <= 0:
            return None
        return ((ask - bid) / bid) * Decimal("100")

    @staticmethod
    def liquidity_classification(
        spread_pct: Optional[Decimal],
    ) -> Optional[str]:
        """Classify liquidity based on bid-ask spread."""
        if spread_pct is None or spread_pct < 0:
            return None
        if spread_pct <= HIGHLY_LIQUID_BID_ASK_PCT_MAX:
            return "HIGHLY_LIQUID"
        if spread_pct <= LIQUID_BID_ASK_PCT_MAX:
            return "LIQUID"
        return "ILLIQUID"

    @staticmethod
    def transfer_detection(
        old_level: str,
        new_level: str,
    ) -> Dict[str, Any]:
        """
        Detect inter-level transfer per IFRS 13.93(c).
        Same level → no transfer.
        Rule 6: unknown level surfaced.
        """
        if (old_level not in FAIR_VALUE_HIERARCHY_LEVELS
                or new_level not in FAIR_VALUE_HIERARCHY_LEVELS):
            return {"transfer": None, "computed": False,
                    "reason": "unknown_level"}
        if old_level == new_level:
            return {"transfer": None, "transfer_type": None,
                    "computed": True,
                    "reason": "no_transfer"}
        # Level 3 transfers warrant special disclosure
        if new_level == "LEVEL_3":
            transfer_type = "INTO_LEVEL_3"
        elif old_level == "LEVEL_3":
            transfer_type = "OUT_OF_LEVEL_3"
        else:
            transfer_type = "INTER_LEVEL"
        return {
            "old_level": old_level,
            "new_level": new_level,
            "transfer": True,
            "transfer_type": transfer_type,
            "disclosure_required": True,
            "computed": True,
        }

    @staticmethod
    def disclosure_pack(level: str) -> Dict[str, Any]:
        """
        Required disclosures per level.
        Level 3 has the most stringent disclosures.
        Rule 6: unknown level rejected.
        """
        if level not in FAIR_VALUE_HIERARCHY_LEVELS:
            return {"disclosures_required": None, "computed": False,
                    "reason": f"unknown_level:{level}"}
        if level == "LEVEL_1":
            disclosures = ["fair_value", "level"]
        elif level == "LEVEL_2":
            disclosures = ["fair_value", "level", "valuation_technique",
                           "observable_inputs_description"]
        else:  # LEVEL_3
            disclosures = ["fair_value", "level", "valuation_technique",
                           "unobservable_inputs",
                           "sensitivity_analysis",
                           "reconciliation_opening_to_closing",
                           "transfers_into_and_out_of_level_3",
                           "unrealized_gains_losses_in_period"]
        return {
            "level": level,
            "disclosures_required": disclosures,
            "disclosure_count": len(disclosures),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_levels_byte_for_byte():
    expected = ("LEVEL_1", "LEVEL_2", "LEVEL_3")
    for l in expected:
        assert l in FAIR_VALUE_HIERARCHY_LEVELS
    assert len(FAIR_VALUE_HIERARCHY_LEVELS) == 3


def _test_techniques_byte_for_byte():
    expected = ("MARKET_APPROACH", "INCOME_APPROACH", "COST_APPROACH")
    for t in expected:
        assert t in VALUATION_TECHNIQUES


def _test_observability_byte_for_byte():
    expected = ("QUOTED_ACTIVE_MARKET", "OBSERVABLE_OTHER", "UNOBSERVABLE")
    for o in expected:
        assert o in INPUT_OBSERVABILITY


def _test_level_3_inputs_byte_for_byte():
    expected = ("PROBABILITY_OF_DEFAULT", "LOSS_GIVEN_DEFAULT",
                "ILLIQUIDITY_DISCOUNT", "MODEL_PARAMETER", "BLOCKAGE_DISCOUNT")
    for i in expected:
        assert i in LEVEL_3_INPUTS
    assert len(LEVEL_3_INPUTS) == 5


def _test_transfer_types_byte_for_byte():
    expected = ("INTO_LEVEL_3", "OUT_OF_LEVEL_3", "INTER_LEVEL")
    for t in expected:
        assert t in TRANSFER_TYPES


def _test_liquidity_thresholds_byte_for_byte():
    assert HIGHLY_LIQUID_BID_ASK_PCT_MAX == Decimal("0.5")
    assert LIQUID_BID_ASK_PCT_MAX == Decimal("2")


def _test_hierarchy_level_1():
    assert FairValueEngine.hierarchy_level("QUOTED_ACTIVE_MARKET") == "LEVEL_1"


def _test_hierarchy_level_2():
    assert FairValueEngine.hierarchy_level("OBSERVABLE_OTHER") == "LEVEL_2"


def _test_hierarchy_level_3():
    assert FairValueEngine.hierarchy_level("UNOBSERVABLE") == "LEVEL_3"


def _test_hierarchy_unknown_rule6():
    assert FairValueEngine.hierarchy_level("WEIRD") is None


def _test_validate_technique():
    r = FairValueEngine.validate_valuation_technique("INCOME_APPROACH")
    assert r["valid"] is True


def _test_validate_technique_unknown_rule6():
    r = FairValueEngine.validate_valuation_technique("WEIRD")
    assert r["valid"] is False


def _test_mid_price_basic():
    """Bid 100, Ask 102 → mid 101."""
    r = FairValueEngine.mid_price(Decimal("100"), Decimal("102"))
    assert r["mid"] == "101.00"


def _test_mid_price_equal():
    r = FairValueEngine.mid_price(Decimal("100"), Decimal("100"))
    assert r["mid"] == "100.00"


def _test_mid_price_inverted_rule6():
    """Bid > Ask → reject (fail closed)."""
    r = FairValueEngine.mid_price(Decimal("105"), Decimal("100"))
    assert r["computed"] is False


def _test_mid_price_negative_rule6():
    r = FairValueEngine.mid_price(Decimal("-10"), Decimal("100"))
    assert r["computed"] is False


def _test_mid_price_missing_rule1():
    r = FairValueEngine.mid_price(None, Decimal("100"))
    assert r["mid"] is None


def _test_spread_pct_basic():
    """Bid 100, Ask 102 → 2% spread."""
    s = FairValueEngine.bid_ask_spread_pct(Decimal("100"), Decimal("102"))
    assert s == Decimal("2")


def _test_spread_pct_zero_bid_rule1():
    assert FairValueEngine.bid_ask_spread_pct(Decimal("0"), Decimal("100")) is None


def _test_liquidity_highly_liquid():
    """0.3% spread → HIGHLY_LIQUID."""
    assert FairValueEngine.liquidity_classification(Decimal("0.3")) == "HIGHLY_LIQUID"


def _test_liquidity_boundary_highly():
    """Exactly 0.5% → HIGHLY_LIQUID (boundary inclusive)."""
    assert FairValueEngine.liquidity_classification(Decimal("0.5")) == "HIGHLY_LIQUID"


def _test_liquidity_liquid():
    assert FairValueEngine.liquidity_classification(Decimal("1.5")) == "LIQUID"


def _test_liquidity_boundary_liquid():
    """Exactly 2% → LIQUID."""
    assert FairValueEngine.liquidity_classification(Decimal("2")) == "LIQUID"


def _test_liquidity_illiquid():
    assert FairValueEngine.liquidity_classification(Decimal("5")) == "ILLIQUID"


def _test_liquidity_missing_rule1():
    assert FairValueEngine.liquidity_classification(None) is None


def _test_transfer_into_level_3():
    """LEVEL_2 → LEVEL_3 = INTO_LEVEL_3 transfer."""
    r = FairValueEngine.transfer_detection("LEVEL_2", "LEVEL_3")
    assert r["transfer_type"] == "INTO_LEVEL_3"
    assert r["disclosure_required"] is True


def _test_transfer_out_of_level_3():
    r = FairValueEngine.transfer_detection("LEVEL_3", "LEVEL_2")
    assert r["transfer_type"] == "OUT_OF_LEVEL_3"


def _test_transfer_inter_level():
    """LEVEL_1 → LEVEL_2 = INTER_LEVEL."""
    r = FairValueEngine.transfer_detection("LEVEL_1", "LEVEL_2")
    assert r["transfer_type"] == "INTER_LEVEL"


def _test_transfer_no_change():
    r = FairValueEngine.transfer_detection("LEVEL_2", "LEVEL_2")
    assert r["transfer"] is None


def _test_transfer_unknown_rule6():
    r = FairValueEngine.transfer_detection("LEVEL_4", "LEVEL_1")
    assert r["computed"] is False


def _test_disclosure_level_1_minimal():
    """Level 1: only fair_value + level disclosure."""
    r = FairValueEngine.disclosure_pack("LEVEL_1")
    assert r["disclosure_count"] == 2


def _test_disclosure_level_3_extensive():
    """Level 3: 8 disclosures including sensitivity + reconciliation."""
    r = FairValueEngine.disclosure_pack("LEVEL_3")
    assert r["disclosure_count"] == 8
    assert "sensitivity_analysis" in r["disclosures_required"]
    assert "reconciliation_opening_to_closing" in r["disclosures_required"]


def _test_disclosure_unknown_rule6():
    r = FairValueEngine.disclosure_pack("WEIRD")
    assert r["computed"] is False


def self_test() -> bool:
    tests = [
        _test_levels_byte_for_byte,
        _test_techniques_byte_for_byte,
        _test_observability_byte_for_byte,
        _test_level_3_inputs_byte_for_byte,
        _test_transfer_types_byte_for_byte,
        _test_liquidity_thresholds_byte_for_byte,
        _test_hierarchy_level_1,
        _test_hierarchy_level_2,
        _test_hierarchy_level_3,
        _test_hierarchy_unknown_rule6,
        _test_validate_technique,
        _test_validate_technique_unknown_rule6,
        _test_mid_price_basic,
        _test_mid_price_equal,
        _test_mid_price_inverted_rule6,
        _test_mid_price_negative_rule6,
        _test_mid_price_missing_rule1,
        _test_spread_pct_basic,
        _test_spread_pct_zero_bid_rule1,
        _test_liquidity_highly_liquid,
        _test_liquidity_boundary_highly,
        _test_liquidity_liquid,
        _test_liquidity_boundary_liquid,
        _test_liquidity_illiquid,
        _test_liquidity_missing_rule1,
        _test_transfer_into_level_3,
        _test_transfer_out_of_level_3,
        _test_transfer_inter_level,
        _test_transfer_no_change,
        _test_transfer_unknown_rule6,
        _test_disclosure_level_1_minimal,
        _test_disclosure_level_3_extensive,
        _test_disclosure_unknown_rule6,
    ]
    print("=" * 60)
    print("Fair Value Engine — Self-Tests (#103 IFRS 13)")
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

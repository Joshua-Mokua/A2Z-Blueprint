"""
================================================================================
A2Z MIS 360 — Standard #100: Group Consolidation Engine (IFRS 10 / IAS 28)
================================================================================

CENTENNIAL MILESTONE — 100th standard delivered.

Risk classification: Cat B (deterministic consolidation method selection +
elimination computation per IFRS 10 / IAS 28 / IFRS 11)

Provides:
    - consolidation_method(...)         -- determine method by ownership %
    - subsidiary_classification(...)    -- WHOLLY/MAJORITY/ASSOCIATE/JV/BRANCH
    - elimination_amount(...)           -- intra-group elimination
    - non_controlling_interest(...)     -- NCI = (1 - ownership%) × subsidiary equity
    - currency_translation(...)         -- temporal vs current-rate method

5 SUBSIDIARY_TYPES byte-for-byte:
    WHOLLY_OWNED, MAJORITY_OWNED, ASSOCIATE, JOINT_VENTURE, BRANCH

4 CONSOLIDATION_METHODS byte-for-byte (IFRS 10 / IAS 28 / IFRS 11):
    FULL_CONSOLIDATION   -- ownership > 50% (control)
    EQUITY_METHOD        -- 20% ≤ ownership ≤ 50% (significant influence)
    PROPORTIONATE        -- joint operations (IFRS 11)
    COST_METHOD          -- ownership < 20% (no significant influence)

Ownership thresholds byte-for-byte:
    CONTROL_THRESHOLD_PCT              = 50    -- >50% triggers FULL
    SIGNIFICANT_INFLUENCE_THRESHOLD_PCT = 20   -- ≥20% triggers EQUITY
    WHOLLY_OWNED_THRESHOLD_PCT         = 100   -- =100% no NCI

4 ELIMINATION_TYPES byte-for-byte:
    INTRA_GROUP_TRADING        -- inter-co revenue/expense pairs
    INTRA_GROUP_LOANS          -- inter-co receivables/payables
    INTRA_GROUP_DIVIDENDS      -- div paid/received within group
    UNREALIZED_PROFITS         -- unrealised profit on inter-co stock

2 CURRENCY_TRANSLATION_METHODS byte-for-byte (IAS 21):
    TEMPORAL_METHOD     -- monetary at closing rate, non-monetary historical
    CURRENT_RATE_METHOD -- all assets/liabilities at closing rate

3 CONSOLIDATION_FREQUENCIES byte-for-byte:
    MONTHLY     -- subsidiaries
    QUARTERLY   -- associates / joint ventures
    ANNUAL      -- minimum statutory

Honesty rules applied:
    Rule 1: nci=None when ownership_pct missing
            method=None when ownership_pct missing
    Rule 6: ownership > 100% rejected (fail closed)
            unknown subsidiary_type / elimination_type / translation_method
            surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 5 SUBSIDIARY TYPES byte-for-byte
SUBSIDIARY_TYPES: Tuple[str, ...] = (
    "WHOLLY_OWNED", "MAJORITY_OWNED", "ASSOCIATE",
    "JOINT_VENTURE", "BRANCH",
)

# 4 CONSOLIDATION METHODS byte-for-byte (IFRS 10 / IAS 28 / IFRS 11)
CONSOLIDATION_METHODS: Tuple[str, ...] = (
    "FULL_CONSOLIDATION", "EQUITY_METHOD", "PROPORTIONATE", "COST_METHOD",
)

# Ownership thresholds byte-for-byte
CONTROL_THRESHOLD_PCT = Decimal("50")
SIGNIFICANT_INFLUENCE_THRESHOLD_PCT = Decimal("20")
WHOLLY_OWNED_THRESHOLD_PCT = Decimal("100")

# 4 ELIMINATION TYPES byte-for-byte
ELIMINATION_TYPES: Tuple[str, ...] = (
    "INTRA_GROUP_TRADING", "INTRA_GROUP_LOANS",
    "INTRA_GROUP_DIVIDENDS", "UNREALIZED_PROFITS",
)

# 2 CURRENCY TRANSLATION METHODS byte-for-byte (IAS 21)
CURRENCY_TRANSLATION_METHODS: Tuple[str, ...] = (
    "TEMPORAL_METHOD", "CURRENT_RATE_METHOD",
)

# 3 CONSOLIDATION FREQUENCIES byte-for-byte
CONSOLIDATION_FREQUENCIES: Tuple[str, ...] = (
    "MONTHLY", "QUARTERLY", "ANNUAL",
)


class GroupConsolidationEngine:
    """Deterministic IFRS 10 / IAS 28 / IFRS 11 consolidation."""

    @staticmethod
    def consolidation_method(
        ownership_pct: Optional[Decimal],
        is_joint_venture: bool = False,
    ) -> Dict[str, Any]:
        """
        Determine consolidation method by ownership % per IFRS 10/IAS 28/IFRS 11.
        Rule 1: method=None when ownership missing.
        Rule 6: ownership > 100% rejected (fail closed).
        """
        if ownership_pct is None or ownership_pct < 0:
            return {"method": None, "computed": False,
                    "reason": "missing_or_negative_ownership"}
        if ownership_pct > Decimal("100"):
            return {"method": None, "computed": False,
                    "reason": "ownership_exceeds_100pct"}
        # IFRS 11 joint arrangements
        if is_joint_venture:
            return {
                "ownership_pct": str(ownership_pct),
                "method": "PROPORTIONATE",
                "rationale": "joint_venture_per_IFRS_11",
                "computed": True,
            }
        # IFRS 10: control > 50% → full consolidation
        if ownership_pct > CONTROL_THRESHOLD_PCT:
            return {
                "ownership_pct": str(ownership_pct),
                "method": "FULL_CONSOLIDATION",
                "rationale": "control_per_IFRS_10",
                "computed": True,
            }
        # IAS 28: significant influence 20-50% → equity method
        if ownership_pct >= SIGNIFICANT_INFLUENCE_THRESHOLD_PCT:
            return {
                "ownership_pct": str(ownership_pct),
                "method": "EQUITY_METHOD",
                "rationale": "significant_influence_per_IAS_28",
                "computed": True,
            }
        # < 20% → cost / fair value method (IFRS 9 financial asset)
        return {
            "ownership_pct": str(ownership_pct),
            "method": "COST_METHOD",
            "rationale": "no_significant_influence",
            "computed": True,
        }

    @staticmethod
    def subsidiary_classification(
        ownership_pct: Optional[Decimal],
        is_joint_venture: bool = False,
        is_branch: bool = False,
    ) -> Optional[str]:
        """
        Classify into 5 SUBSIDIARY_TYPES.
        Rule 1: None when ownership missing or invalid.
        """
        if ownership_pct is None or ownership_pct < 0 or ownership_pct > Decimal("100"):
            return None
        if is_branch:
            return "BRANCH"
        if is_joint_venture:
            return "JOINT_VENTURE"
        if ownership_pct == WHOLLY_OWNED_THRESHOLD_PCT:
            return "WHOLLY_OWNED"
        if ownership_pct > CONTROL_THRESHOLD_PCT:
            return "MAJORITY_OWNED"
        if ownership_pct >= SIGNIFICANT_INFLUENCE_THRESHOLD_PCT:
            return "ASSOCIATE"
        return None  # below threshold = financial investment, not subsidiary

    @staticmethod
    def elimination_amount(
        elimination_type: str,
        gross_amount: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Compute elimination entry (always 100% reversal of intra-group).
        Rule 1: amount=None when gross missing.
        Rule 6: unknown elimination_type surfaced.
        """
        if elimination_type not in ELIMINATION_TYPES:
            return {"elimination": None, "computed": False,
                    "reason": f"unknown_elimination:{elimination_type}",
                    "valid_types": list(ELIMINATION_TYPES)}
        if gross_amount is None:
            return {"elimination": None, "computed": False,
                    "reason": "missing_gross_amount"}
        # Elimination is always 100% of gross (full reversal)
        return {
            "elimination_type": elimination_type,
            "gross_amount": str(gross_amount),
            "elimination": str(-gross_amount),  # negative = reversal
            "computed": True,
        }

    @staticmethod
    def non_controlling_interest(
        subsidiary_equity: Optional[Decimal],
        parent_ownership_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        NCI = (1 - parent_ownership%) × subsidiary equity (IFRS 10).
        Rule 1: nci=None when inputs missing.
        Rule 6: ownership > 100% rejected.
        """
        if subsidiary_equity is None or parent_ownership_pct is None:
            return {"nci": None, "computed": False,
                    "reason": "missing_inputs"}
        if parent_ownership_pct < 0 or parent_ownership_pct > Decimal("100"):
            return {"nci": None, "computed": False,
                    "reason": "invalid_ownership_pct"}
        # NCI = (100% - ownership%) × equity
        nci_share_pct = Decimal("100") - parent_ownership_pct
        nci = (subsidiary_equity * nci_share_pct) / Decimal("100")
        return {
            "subsidiary_equity": str(subsidiary_equity),
            "parent_ownership_pct": str(parent_ownership_pct),
            "nci_share_pct": str(nci_share_pct),
            "nci": str(nci.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def currency_translation(
        amount_local: Optional[Decimal],
        method: str,
        closing_rate: Optional[Decimal] = None,
        historical_rate: Optional[Decimal] = None,
        is_monetary: bool = True,
    ) -> Dict[str, Any]:
        """
        Translate foreign currency amount per IAS 21.
        TEMPORAL_METHOD: monetary at closing, non-monetary at historical.
        CURRENT_RATE_METHOD: all at closing rate.
        Rule 6: unknown method surfaced.
        """
        if method not in CURRENCY_TRANSLATION_METHODS:
            return {"translated": None, "computed": False,
                    "reason": f"unknown_method:{method}"}
        if amount_local is None:
            return {"translated": None, "computed": False,
                    "reason": "missing_amount"}
        if method == "CURRENT_RATE_METHOD":
            if closing_rate is None or closing_rate <= 0:
                return {"translated": None, "computed": False,
                        "reason": "missing_closing_rate"}
            translated = amount_local * closing_rate
            rate_used = closing_rate
            rate_type = "closing"
        else:  # TEMPORAL_METHOD
            if is_monetary:
                if closing_rate is None or closing_rate <= 0:
                    return {"translated": None, "computed": False,
                            "reason": "missing_closing_rate"}
                translated = amount_local * closing_rate
                rate_used = closing_rate
                rate_type = "closing"
            else:
                if historical_rate is None or historical_rate <= 0:
                    return {"translated": None, "computed": False,
                            "reason": "missing_historical_rate"}
                translated = amount_local * historical_rate
                rate_used = historical_rate
                rate_type = "historical"
        return {
            "method": method,
            "amount_local": str(amount_local),
            "is_monetary": is_monetary,
            "rate_type": rate_type,
            "rate_used": str(rate_used),
            "translated": str(translated.quantize(Decimal("0.01"))),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_subsidiary_types_byte_for_byte():
    expected = ("WHOLLY_OWNED", "MAJORITY_OWNED", "ASSOCIATE",
                "JOINT_VENTURE", "BRANCH")
    for t in expected:
        assert t in SUBSIDIARY_TYPES
    assert len(SUBSIDIARY_TYPES) == 5


def _test_consolidation_methods_byte_for_byte():
    expected = ("FULL_CONSOLIDATION", "EQUITY_METHOD",
                "PROPORTIONATE", "COST_METHOD")
    for m in expected:
        assert m in CONSOLIDATION_METHODS
    assert len(CONSOLIDATION_METHODS) == 4


def _test_thresholds_byte_for_byte():
    assert CONTROL_THRESHOLD_PCT == Decimal("50")
    assert SIGNIFICANT_INFLUENCE_THRESHOLD_PCT == Decimal("20")
    assert WHOLLY_OWNED_THRESHOLD_PCT == Decimal("100")


def _test_elimination_types_byte_for_byte():
    expected = ("INTRA_GROUP_TRADING", "INTRA_GROUP_LOANS",
                "INTRA_GROUP_DIVIDENDS", "UNREALIZED_PROFITS")
    for t in expected:
        assert t in ELIMINATION_TYPES
    assert len(ELIMINATION_TYPES) == 4


def _test_translation_methods_byte_for_byte():
    expected = ("TEMPORAL_METHOD", "CURRENT_RATE_METHOD")
    for m in expected:
        assert m in CURRENCY_TRANSLATION_METHODS


def _test_frequencies_byte_for_byte():
    expected = ("MONTHLY", "QUARTERLY", "ANNUAL")
    for f in expected:
        assert f in CONSOLIDATION_FREQUENCIES


def _test_method_full_consolidation_majority():
    """75% ownership → FULL_CONSOLIDATION."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("75"))
    assert r["method"] == "FULL_CONSOLIDATION"


def _test_method_full_consolidation_wholly():
    """100% ownership → FULL_CONSOLIDATION."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("100"))
    assert r["method"] == "FULL_CONSOLIDATION"


def _test_method_equity():
    """30% → EQUITY_METHOD (significant influence)."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("30"))
    assert r["method"] == "EQUITY_METHOD"


def _test_method_equity_boundary_20():
    """Exactly 20% → EQUITY_METHOD."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("20"))
    assert r["method"] == "EQUITY_METHOD"


def _test_method_equity_boundary_50():
    """Exactly 50% → EQUITY_METHOD (not control, only > 50% controls)."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("50"))
    assert r["method"] == "EQUITY_METHOD"


def _test_method_cost():
    """10% → COST_METHOD."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("10"))
    assert r["method"] == "COST_METHOD"


def _test_method_cost_boundary_19():
    """Just under 20% → COST_METHOD."""
    r = GroupConsolidationEngine.consolidation_method(Decimal("19.99"))
    assert r["method"] == "COST_METHOD"


def _test_method_proportionate_jv():
    """JV with any ownership → PROPORTIONATE."""
    r = GroupConsolidationEngine.consolidation_method(
        Decimal("50"), is_joint_venture=True)
    assert r["method"] == "PROPORTIONATE"


def _test_method_missing_rule1():
    r = GroupConsolidationEngine.consolidation_method(None)
    assert r["method"] is None


def _test_method_invalid_over_100_rule6():
    r = GroupConsolidationEngine.consolidation_method(Decimal("150"))
    assert r["method"] is None


def _test_classification_wholly_owned():
    assert GroupConsolidationEngine.subsidiary_classification(
        Decimal("100")) == "WHOLLY_OWNED"


def _test_classification_majority():
    assert GroupConsolidationEngine.subsidiary_classification(
        Decimal("75")) == "MAJORITY_OWNED"


def _test_classification_associate():
    assert GroupConsolidationEngine.subsidiary_classification(
        Decimal("30")) == "ASSOCIATE"


def _test_classification_jv():
    assert GroupConsolidationEngine.subsidiary_classification(
        Decimal("50"), is_joint_venture=True) == "JOINT_VENTURE"


def _test_classification_branch():
    assert GroupConsolidationEngine.subsidiary_classification(
        Decimal("100"), is_branch=True) == "BRANCH"


def _test_classification_below_threshold_returns_none():
    """< 20% = financial investment, not subsidiary."""
    assert GroupConsolidationEngine.subsidiary_classification(
        Decimal("10")) is None


def _test_elimination_intra_group_trading():
    """Eliminate 5M intra-group trading → -5M."""
    r = GroupConsolidationEngine.elimination_amount(
        "INTRA_GROUP_TRADING", Decimal("5000000"))
    assert r["elimination"] == "-5000000"


def _test_elimination_unknown_type_rule6():
    r = GroupConsolidationEngine.elimination_amount(
        "WEIRD", Decimal("1000000"))
    assert r["computed"] is False


def _test_elimination_missing_amount_rule1():
    r = GroupConsolidationEngine.elimination_amount(
        "INTRA_GROUP_LOANS", None)
    assert r["computed"] is False


def _test_nci_basic():
    """75% ownership of 1M equity → NCI = 25% × 1M = 250K."""
    r = GroupConsolidationEngine.non_controlling_interest(
        Decimal("1000000"), Decimal("75"))
    assert r["nci"] == "250000.00"
    assert r["nci_share_pct"] == "25"


def _test_nci_wholly_owned_zero():
    """100% ownership → NCI=0."""
    r = GroupConsolidationEngine.non_controlling_interest(
        Decimal("1000000"), Decimal("100"))
    assert r["nci"] == "0.00"


def _test_nci_missing_rule1():
    r = GroupConsolidationEngine.non_controlling_interest(
        None, Decimal("75"))
    assert r["computed"] is False


def _test_nci_invalid_over_100_rule6():
    r = GroupConsolidationEngine.non_controlling_interest(
        Decimal("1000000"), Decimal("150"))
    assert r["computed"] is False


def _test_translation_current_rate():
    """1M USD * 130 KES/USD = 130M KES."""
    r = GroupConsolidationEngine.currency_translation(
        Decimal("1000000"), "CURRENT_RATE_METHOD",
        closing_rate=Decimal("130"))
    assert r["translated"] == "130000000.00"
    assert r["rate_type"] == "closing"


def _test_translation_temporal_monetary():
    """Monetary asset → closing rate even under temporal method."""
    r = GroupConsolidationEngine.currency_translation(
        Decimal("1000000"), "TEMPORAL_METHOD",
        closing_rate=Decimal("130"), historical_rate=Decimal("100"),
        is_monetary=True)
    assert r["translated"] == "130000000.00"
    assert r["rate_type"] == "closing"


def _test_translation_temporal_non_monetary():
    """Non-monetary asset → historical rate under temporal method."""
    r = GroupConsolidationEngine.currency_translation(
        Decimal("1000000"), "TEMPORAL_METHOD",
        closing_rate=Decimal("130"), historical_rate=Decimal("100"),
        is_monetary=False)
    assert r["translated"] == "100000000.00"
    assert r["rate_type"] == "historical"


def _test_translation_unknown_method_rule6():
    r = GroupConsolidationEngine.currency_translation(
        Decimal("1000000"), "WEIRD", closing_rate=Decimal("130"))
    assert r["computed"] is False


def _test_translation_missing_rate_rule1():
    r = GroupConsolidationEngine.currency_translation(
        Decimal("1000000"), "CURRENT_RATE_METHOD", closing_rate=None)
    assert r["computed"] is False


def self_test() -> bool:
    tests = [
        _test_subsidiary_types_byte_for_byte,
        _test_consolidation_methods_byte_for_byte,
        _test_thresholds_byte_for_byte,
        _test_elimination_types_byte_for_byte,
        _test_translation_methods_byte_for_byte,
        _test_frequencies_byte_for_byte,
        _test_method_full_consolidation_majority,
        _test_method_full_consolidation_wholly,
        _test_method_equity,
        _test_method_equity_boundary_20,
        _test_method_equity_boundary_50,
        _test_method_cost,
        _test_method_cost_boundary_19,
        _test_method_proportionate_jv,
        _test_method_missing_rule1,
        _test_method_invalid_over_100_rule6,
        _test_classification_wholly_owned,
        _test_classification_majority,
        _test_classification_associate,
        _test_classification_jv,
        _test_classification_branch,
        _test_classification_below_threshold_returns_none,
        _test_elimination_intra_group_trading,
        _test_elimination_unknown_type_rule6,
        _test_elimination_missing_amount_rule1,
        _test_nci_basic,
        _test_nci_wholly_owned_zero,
        _test_nci_missing_rule1,
        _test_nci_invalid_over_100_rule6,
        _test_translation_current_rate,
        _test_translation_temporal_monetary,
        _test_translation_temporal_non_monetary,
        _test_translation_unknown_method_rule6,
        _test_translation_missing_rate_rule1,
    ]
    print("=" * 60)
    print("Group Consolidation Engine — Self-Tests (#100 CENTENNIAL)")
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

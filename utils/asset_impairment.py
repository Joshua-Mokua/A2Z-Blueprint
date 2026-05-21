"""
================================================================================
A2Z MIS 360 — Standard #105: IAS 36 Asset Impairment Engine
================================================================================

Risk classification: Cat B (deterministic recoverable amount + impairment loss)

Provides:
    - recoverable_amount(...)            -- max(VIU, FVLCD)
    - impairment_loss(...)               -- carrying_amount - recoverable_amount
    - validate_impairment_indicator(...) -- external/internal indicator validation
    - cgu_classification(...)            -- INDIVIDUAL_ASSET vs CGU
    - reversal_eligibility(...)          -- reversal allowed except goodwill
    - value_in_use_pv(...)               -- DCF computation

3 RECOVERABLE_AMOUNT_BASES byte-for-byte (IAS 36.6/18):
    VALUE_IN_USE                  -- VIU: DCF of pre-tax future cash flows
    FAIR_VALUE_LESS_COSTS_OF_DISPOSAL  -- FVLCD: market-based valuation
    HIGHER_OF                     -- recoverable = max(VIU, FVLCD)

7 IMPAIRMENT_INDICATORS_EXTERNAL byte-for-byte (IAS 36.12):
    MARKET_VALUE_DECLINE_SIGNIFICANT
    ADVERSE_TECHNOLOGY_CHANGES
    ADVERSE_MARKET_CHANGES
    ADVERSE_LEGAL_CHANGES
    INTEREST_RATE_INCREASE
    NET_ASSETS_EXCEED_MARKET_CAP
    ECONOMIC_DOWNTURN

5 IMPAIRMENT_INDICATORS_INTERNAL byte-for-byte (IAS 36.12):
    PHYSICAL_DAMAGE
    OBSOLESCENCE
    ASSET_HELD_FOR_DISPOSAL_PLAN
    PERFORMANCE_DECLINE
    RESTRUCTURING_PLAN

3 ASSET_TEST_FREQUENCIES byte-for-byte (IAS 36.9-10):
    ANNUAL_MANDATORY              -- goodwill, intangibles with indefinite life
    ANNUAL_IF_INDICATOR           -- intangibles in development
    AT_INDICATOR_TRIGGER          -- standard tangible/intangible

2 ASSET_GROUPINGS byte-for-byte:
    INDIVIDUAL_ASSET              -- standalone test
    CASH_GENERATING_UNIT          -- CGU: smallest group with independent CFs

Reversal byte-for-byte (IAS 36.114-125):
    GOODWILL_REVERSAL_PROHIBITED = True   -- never reverse goodwill impairment
    OTHER_ASSET_REVERSAL_ALLOWED = True   -- subject to ceiling (original CV less depreciation)

Discount rate guidance byte-for-byte (IAS 36.55-57):
    Pre-tax rate that reflects current market assessments of:
    - Time value of money
    - Risks specific to the asset

Honesty rules applied:
    Rule 1: recoverable_amount=None when both VIU and FVLCD missing
            impairment_loss=None when carrying_amount or recoverable missing
    Rule 6: unknown indicator / asset_grouping / test_frequency surfaced
            negative carrying amount rejected (fail closed)
            reversal of goodwill rejected (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 RECOVERABLE AMOUNT BASES byte-for-byte (IAS 36.6/18)
RECOVERABLE_AMOUNT_BASES: Tuple[str, ...] = (
    "VALUE_IN_USE", "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL", "HIGHER_OF",
)

# 7 EXTERNAL impairment indicators byte-for-byte (IAS 36.12)
IMPAIRMENT_INDICATORS_EXTERNAL: Tuple[str, ...] = (
    "MARKET_VALUE_DECLINE_SIGNIFICANT",
    "ADVERSE_TECHNOLOGY_CHANGES",
    "ADVERSE_MARKET_CHANGES",
    "ADVERSE_LEGAL_CHANGES",
    "INTEREST_RATE_INCREASE",
    "NET_ASSETS_EXCEED_MARKET_CAP",
    "ECONOMIC_DOWNTURN",
)

# 5 INTERNAL impairment indicators byte-for-byte (IAS 36.12)
IMPAIRMENT_INDICATORS_INTERNAL: Tuple[str, ...] = (
    "PHYSICAL_DAMAGE",
    "OBSOLESCENCE",
    "ASSET_HELD_FOR_DISPOSAL_PLAN",
    "PERFORMANCE_DECLINE",
    "RESTRUCTURING_PLAN",
)

# 3 TEST FREQUENCIES byte-for-byte (IAS 36.9-10)
ASSET_TEST_FREQUENCIES: Tuple[str, ...] = (
    "ANNUAL_MANDATORY", "ANNUAL_IF_INDICATOR", "AT_INDICATOR_TRIGGER",
)

# 2 ASSET GROUPINGS byte-for-byte
ASSET_GROUPINGS: Tuple[str, ...] = (
    "INDIVIDUAL_ASSET", "CASH_GENERATING_UNIT",
)

# Reversal rules byte-for-byte (IAS 36.114-125)
GOODWILL_REVERSAL_PROHIBITED = True
OTHER_ASSET_REVERSAL_ALLOWED = True


class ImpairmentEngine:
    """Deterministic IAS 36 impairment computation."""

    @staticmethod
    def value_in_use_pv(
        cash_flows: List[Tuple[int, Decimal]],
        discount_rate_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Value in use = PV of future cash flows.
        cash_flows: list of (year_index, amount) tuples.
        Rule 1: None when rate missing or flows empty.
        Rule 6: negative rate rejected.
        """
        if discount_rate_pct is None:
            return {"viu": None, "computed": False,
                    "reason": "missing_discount_rate"}
        if discount_rate_pct < 0:
            return {"viu": None, "computed": False,
                    "reason": "negative_discount_rate"}
        if not cash_flows:
            return {"viu": None, "computed": False,
                    "reason": "empty_cash_flows"}
        rate_decimal = discount_rate_pct / Decimal("100")
        one_plus_r = Decimal("1") + rate_decimal
        viu = Decimal("0")
        for year_index, cf in cash_flows:
            if year_index < 0:
                return {"viu": None, "computed": False,
                        "reason": "negative_year_index"}
            if cf is None:
                return {"viu": None, "computed": False,
                        "reason": "missing_cash_flow"}
            discount_factor = one_plus_r ** year_index
            viu += cf / discount_factor
        return {
            "discount_rate_pct": str(discount_rate_pct),
            "cash_flow_count": len(cash_flows),
            "viu": str(viu.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def recoverable_amount(
        value_in_use: Optional[Decimal],
        fair_value_less_costs_of_disposal: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Recoverable amount = HIGHER OF (VIU, FVLCD) per IAS 36.18.
        If only one is determinable, use that one (IAS 36.20).
        Rule 1: None when BOTH missing.
        """
        if value_in_use is None and fair_value_less_costs_of_disposal is None:
            return {"recoverable_amount": None, "computed": False,
                    "reason": "both_viu_and_fvlcd_missing"}
        # Use the one(s) available
        if value_in_use is None:
            recoverable = fair_value_less_costs_of_disposal
            basis = "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL"
        elif fair_value_less_costs_of_disposal is None:
            recoverable = value_in_use
            basis = "VALUE_IN_USE"
        else:
            # Both available — use higher
            if value_in_use >= fair_value_less_costs_of_disposal:
                recoverable = value_in_use
                basis = "VALUE_IN_USE"
            else:
                recoverable = fair_value_less_costs_of_disposal
                basis = "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL"
        return {
            "value_in_use": (None if value_in_use is None else str(value_in_use)),
            "fvlcd": (None if fair_value_less_costs_of_disposal is None
                      else str(fair_value_less_costs_of_disposal)),
            "recoverable_amount": str(recoverable.quantize(Decimal("0.01"))),
            "basis": basis,
            "computed": True,
        }

    @staticmethod
    def impairment_loss(
        carrying_amount: Optional[Decimal],
        recoverable_amount: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Impairment loss = CA - RA (only if positive, else no impairment).
        Rule 1: None when either missing.
        Rule 6: negative CA rejected.
        """
        if carrying_amount is None or recoverable_amount is None:
            return {"impairment_loss": None, "computed": False,
                    "reason": "missing_inputs"}
        if carrying_amount < 0:
            return {"impairment_loss": None, "computed": False,
                    "reason": "negative_carrying_amount"}
        if recoverable_amount < 0:
            return {"impairment_loss": None, "computed": False,
                    "reason": "negative_recoverable_amount"}
        if carrying_amount > recoverable_amount:
            loss = carrying_amount - recoverable_amount
            impaired = True
        else:
            loss = Decimal("0")
            impaired = False
        return {
            "carrying_amount": str(carrying_amount),
            "recoverable_amount": str(recoverable_amount),
            "impairment_loss": str(loss.quantize(Decimal("0.01"))),
            "impaired": impaired,
            "post_impairment_carrying_amount": str(
                (carrying_amount - loss).quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def validate_impairment_indicator(
        indicator: str,
    ) -> Dict[str, Any]:
        """
        Validate indicator against IAS 36.12 list.
        Rule 6: unknown indicator rejected.
        """
        if indicator in IMPAIRMENT_INDICATORS_EXTERNAL:
            return {"valid": True, "indicator": indicator, "category": "EXTERNAL"}
        if indicator in IMPAIRMENT_INDICATORS_INTERNAL:
            return {"valid": True, "indicator": indicator, "category": "INTERNAL"}
        return {
            "valid": False,
            "reason": f"unknown_indicator:{indicator}",
            "valid_external": list(IMPAIRMENT_INDICATORS_EXTERNAL),
            "valid_internal": list(IMPAIRMENT_INDICATORS_INTERNAL),
        }

    @staticmethod
    def cgu_classification(
        generates_independent_cash_flows: Optional[bool],
    ) -> Optional[str]:
        """
        Classify asset for impairment testing per IAS 36.66.
        If asset alone generates independent CFs → INDIVIDUAL_ASSET.
        Otherwise → must be tested as part of CGU.
        Rule 1: None when input missing.
        """
        if generates_independent_cash_flows is None:
            return None
        if generates_independent_cash_flows:
            return "INDIVIDUAL_ASSET"
        return "CASH_GENERATING_UNIT"

    @staticmethod
    def reversal_eligibility(
        asset_type: str,
    ) -> Dict[str, Any]:
        """
        IAS 36.124: goodwill impairment NEVER reversed.
        Other assets: reversal allowed up to ceiling.
        Rule 6: unknown asset_type surfaced (default conservative=no reversal).
        """
        if asset_type == "GOODWILL":
            return {
                "asset_type": "GOODWILL",
                "reversal_allowed": False,
                "rationale": "goodwill_reversal_prohibited_per_IAS_36.124",
            }
        if asset_type in ("TANGIBLE_ASSET", "INTANGIBLE_ASSET",
                           "CASH_GENERATING_UNIT", "INVESTMENT_PROPERTY"):
            return {
                "asset_type": asset_type,
                "reversal_allowed": True,
                "rationale": "reversal_subject_to_ceiling_per_IAS_36.117-118",
                "ceiling_note": "limited_to_recoverable_amount_or_pre_impairment_CV_less_depreciation",
            }
        return {
            "asset_type": asset_type,
            "reversal_allowed": False,
            "rationale": f"unknown_asset_type:{asset_type}",
            "default": "conservative_no_reversal",
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_recoverable_bases_byte_for_byte():
    expected = ("VALUE_IN_USE", "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL", "HIGHER_OF")
    for b in expected:
        assert b in RECOVERABLE_AMOUNT_BASES
    assert len(RECOVERABLE_AMOUNT_BASES) == 3


def _test_external_indicators_byte_for_byte():
    expected = (
        "MARKET_VALUE_DECLINE_SIGNIFICANT",
        "ADVERSE_TECHNOLOGY_CHANGES",
        "ADVERSE_MARKET_CHANGES",
        "ADVERSE_LEGAL_CHANGES",
        "INTEREST_RATE_INCREASE",
        "NET_ASSETS_EXCEED_MARKET_CAP",
        "ECONOMIC_DOWNTURN",
    )
    for i in expected:
        assert i in IMPAIRMENT_INDICATORS_EXTERNAL
    assert len(IMPAIRMENT_INDICATORS_EXTERNAL) == 7


def _test_internal_indicators_byte_for_byte():
    expected = (
        "PHYSICAL_DAMAGE",
        "OBSOLESCENCE",
        "ASSET_HELD_FOR_DISPOSAL_PLAN",
        "PERFORMANCE_DECLINE",
        "RESTRUCTURING_PLAN",
    )
    for i in expected:
        assert i in IMPAIRMENT_INDICATORS_INTERNAL
    assert len(IMPAIRMENT_INDICATORS_INTERNAL) == 5


def _test_test_frequencies_byte_for_byte():
    expected = ("ANNUAL_MANDATORY", "ANNUAL_IF_INDICATOR", "AT_INDICATOR_TRIGGER")
    for f in expected:
        assert f in ASSET_TEST_FREQUENCIES


def _test_asset_groupings_byte_for_byte():
    expected = ("INDIVIDUAL_ASSET", "CASH_GENERATING_UNIT")
    for g in expected:
        assert g in ASSET_GROUPINGS


def _test_goodwill_reversal_prohibited_byte_for_byte():
    assert GOODWILL_REVERSAL_PROHIBITED is True
    assert OTHER_ASSET_REVERSAL_ALLOWED is True


def _test_viu_basic():
    """1M @ year 1 + 1M @ year 2 @ 5% → ~1.857M."""
    r = ImpairmentEngine.value_in_use_pv(
        [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("5"))
    viu = Decimal(r["viu"])
    assert viu > Decimal("1850000") and viu < Decimal("1865000")


def _test_viu_zero_rate():
    """At 0%, VIU = sum."""
    r = ImpairmentEngine.value_in_use_pv(
        [(1, Decimal("1000000")), (2, Decimal("1000000"))], Decimal("0"))
    assert r["viu"] == "2000000.00"


def _test_viu_missing_rate_rule1():
    r = ImpairmentEngine.value_in_use_pv([(1, Decimal("1000000"))], None)
    assert r["viu"] is None


def _test_viu_negative_rate_rule6():
    r = ImpairmentEngine.value_in_use_pv(
        [(1, Decimal("1000000"))], Decimal("-5"))
    assert r["computed"] is False


def _test_viu_empty_flows_rule1():
    r = ImpairmentEngine.value_in_use_pv([], Decimal("5"))
    assert r["viu"] is None


def _test_recoverable_amount_higher_of_viu():
    """VIU 1M, FVLCD 800K → recoverable = 1M (VIU higher)."""
    r = ImpairmentEngine.recoverable_amount(
        Decimal("1000000"), Decimal("800000"))
    assert r["recoverable_amount"] == "1000000.00"
    assert r["basis"] == "VALUE_IN_USE"


def _test_recoverable_amount_higher_of_fvlcd():
    """VIU 800K, FVLCD 1M → recoverable = 1M (FVLCD higher)."""
    r = ImpairmentEngine.recoverable_amount(
        Decimal("800000"), Decimal("1000000"))
    assert r["recoverable_amount"] == "1000000.00"
    assert r["basis"] == "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL"


def _test_recoverable_amount_only_viu():
    """FVLCD missing → use VIU."""
    r = ImpairmentEngine.recoverable_amount(Decimal("1000000"), None)
    assert r["recoverable_amount"] == "1000000.00"
    assert r["basis"] == "VALUE_IN_USE"


def _test_recoverable_amount_only_fvlcd():
    r = ImpairmentEngine.recoverable_amount(None, Decimal("800000"))
    assert r["recoverable_amount"] == "800000.00"
    assert r["basis"] == "FAIR_VALUE_LESS_COSTS_OF_DISPOSAL"


def _test_recoverable_amount_both_missing_rule1():
    r = ImpairmentEngine.recoverable_amount(None, None)
    assert r["recoverable_amount"] is None


def _test_impairment_loss_basic():
    """CA 1.2M, RA 1M → loss 200K."""
    r = ImpairmentEngine.impairment_loss(
        Decimal("1200000"), Decimal("1000000"))
    assert r["impairment_loss"] == "200000.00"
    assert r["impaired"] is True
    assert r["post_impairment_carrying_amount"] == "1000000.00"


def _test_impairment_loss_no_loss():
    """CA 800K, RA 1M → no impairment."""
    r = ImpairmentEngine.impairment_loss(
        Decimal("800000"), Decimal("1000000"))
    assert r["impairment_loss"] == "0.00"
    assert r["impaired"] is False
    assert r["post_impairment_carrying_amount"] == "800000.00"


def _test_impairment_loss_equal():
    """CA = RA → no impairment (exactly recoverable)."""
    r = ImpairmentEngine.impairment_loss(
        Decimal("1000000"), Decimal("1000000"))
    assert r["impaired"] is False


def _test_impairment_loss_missing_rule1():
    r = ImpairmentEngine.impairment_loss(None, Decimal("1000000"))
    assert r["impairment_loss"] is None


def _test_impairment_loss_negative_ca_rule6():
    r = ImpairmentEngine.impairment_loss(
        Decimal("-100"), Decimal("1000000"))
    assert r["computed"] is False


def _test_indicator_external_valid():
    r = ImpairmentEngine.validate_impairment_indicator("INTEREST_RATE_INCREASE")
    assert r["valid"] is True
    assert r["category"] == "EXTERNAL"


def _test_indicator_internal_valid():
    r = ImpairmentEngine.validate_impairment_indicator("PHYSICAL_DAMAGE")
    assert r["valid"] is True
    assert r["category"] == "INTERNAL"


def _test_indicator_unknown_rule6():
    r = ImpairmentEngine.validate_impairment_indicator("WEIRD")
    assert r["valid"] is False


def _test_cgu_individual():
    """Independent CFs → INDIVIDUAL_ASSET."""
    assert ImpairmentEngine.cgu_classification(True) == "INDIVIDUAL_ASSET"


def _test_cgu_grouped():
    assert ImpairmentEngine.cgu_classification(False) == "CASH_GENERATING_UNIT"


def _test_cgu_missing_rule1():
    assert ImpairmentEngine.cgu_classification(None) is None


def _test_reversal_goodwill_prohibited():
    """IAS 36.124: goodwill never reversed."""
    r = ImpairmentEngine.reversal_eligibility("GOODWILL")
    assert r["reversal_allowed"] is False


def _test_reversal_tangible_allowed():
    r = ImpairmentEngine.reversal_eligibility("TANGIBLE_ASSET")
    assert r["reversal_allowed"] is True


def _test_reversal_intangible_allowed():
    r = ImpairmentEngine.reversal_eligibility("INTANGIBLE_ASSET")
    assert r["reversal_allowed"] is True


def _test_reversal_cgu_allowed():
    r = ImpairmentEngine.reversal_eligibility("CASH_GENERATING_UNIT")
    assert r["reversal_allowed"] is True


def _test_reversal_unknown_default_conservative():
    """Unknown type → conservative no reversal."""
    r = ImpairmentEngine.reversal_eligibility("WEIRD")
    assert r["reversal_allowed"] is False


def self_test() -> bool:
    tests = [
        _test_recoverable_bases_byte_for_byte,
        _test_external_indicators_byte_for_byte,
        _test_internal_indicators_byte_for_byte,
        _test_test_frequencies_byte_for_byte,
        _test_asset_groupings_byte_for_byte,
        _test_goodwill_reversal_prohibited_byte_for_byte,
        _test_viu_basic,
        _test_viu_zero_rate,
        _test_viu_missing_rate_rule1,
        _test_viu_negative_rate_rule6,
        _test_viu_empty_flows_rule1,
        _test_recoverable_amount_higher_of_viu,
        _test_recoverable_amount_higher_of_fvlcd,
        _test_recoverable_amount_only_viu,
        _test_recoverable_amount_only_fvlcd,
        _test_recoverable_amount_both_missing_rule1,
        _test_impairment_loss_basic,
        _test_impairment_loss_no_loss,
        _test_impairment_loss_equal,
        _test_impairment_loss_missing_rule1,
        _test_impairment_loss_negative_ca_rule6,
        _test_indicator_external_valid,
        _test_indicator_internal_valid,
        _test_indicator_unknown_rule6,
        _test_cgu_individual,
        _test_cgu_grouped,
        _test_cgu_missing_rule1,
        _test_reversal_goodwill_prohibited,
        _test_reversal_tangible_allowed,
        _test_reversal_intangible_allowed,
        _test_reversal_cgu_allowed,
        _test_reversal_unknown_default_conservative,
    ]
    print("=" * 60)
    print("Asset Impairment Engine — Self-Tests (#105 IAS 36)")
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

"""
================================================================================
A2Z MIS 360 — Standard #108: IAS 33 Earnings Per Share Engine
================================================================================

Risk classification: Cat B (deterministic basic + diluted EPS per IAS 33)

Provides:
    - basic_eps(...)                     -- per IAS 33.10
    - weighted_avg_shares(...)           -- WANS time-weighted
    - diluted_eps(...)                   -- per IAS 33.30 with potential ordinary shares
    - dilutive_securities_classification(...) -- DILUTIVE / ANTI_DILUTIVE
    - treasury_stock_method(...)         -- options + warrants conversion
    - if_converted_method(...)           -- convertible bonds / preferred

3 EPS_TYPES byte-for-byte (IAS 33):
    BASIC                 -- IAS 33.10
    DILUTED               -- IAS 33.30
    CONTINUING_OPERATIONS -- IAS 33.66 separate disclosure

3 SHARE_TRANSACTION_TYPES byte-for-byte:
    ISSUANCE              -- new shares issued
    BUYBACK               -- treasury share acquisition
    BONUS_OR_SPLIT        -- retrospective adjustment

4 POTENTIAL_ORDINARY_SHARE_TYPES byte-for-byte (IAS 33.7):
    CONVERTIBLE_BONDS
    CONVERTIBLE_PREFERRED_SHARES
    SHARE_OPTIONS_WARRANTS
    CONTINGENTLY_ISSUABLE_SHARES

2 DILUTION_OUTCOMES byte-for-byte (IAS 33.41):
    DILUTIVE              -- include in diluted EPS
    ANTI_DILUTIVE         -- exclude (would increase EPS or reduce loss per share)

3 EPS_PRESENTATION_REQUIREMENTS byte-for-byte (IAS 33.67):
    FACE_OF_INCOME_STATEMENT
    NOTES_RECONCILIATION
    CONTINUING_AND_DISCONTINUED_SEPARATE

Honesty rules applied:
    Rule 1: eps=None when net_income or weighted_shares missing or zero shares
    Rule 6: negative weighted shares rejected (fail closed)
            anti-dilutive securities CANNOT increase diluted EPS (fail closed)
            unknown POS type / dilution outcome surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 EPS TYPES byte-for-byte
EPS_TYPES: Tuple[str, ...] = (
    "BASIC", "DILUTED", "CONTINUING_OPERATIONS",
)

# 3 SHARE TRANSACTION TYPES byte-for-byte
SHARE_TRANSACTION_TYPES: Tuple[str, ...] = (
    "ISSUANCE", "BUYBACK", "BONUS_OR_SPLIT",
)

# 4 POTENTIAL ORDINARY SHARE TYPES byte-for-byte (IAS 33.7)
POTENTIAL_ORDINARY_SHARE_TYPES: Tuple[str, ...] = (
    "CONVERTIBLE_BONDS",
    "CONVERTIBLE_PREFERRED_SHARES",
    "SHARE_OPTIONS_WARRANTS",
    "CONTINGENTLY_ISSUABLE_SHARES",
)

# 2 DILUTION OUTCOMES byte-for-byte (IAS 33.41)
DILUTION_OUTCOMES: Tuple[str, ...] = (
    "DILUTIVE", "ANTI_DILUTIVE",
)

# 3 PRESENTATION REQUIREMENTS byte-for-byte (IAS 33.67)
EPS_PRESENTATION_REQUIREMENTS: Tuple[str, ...] = (
    "FACE_OF_INCOME_STATEMENT",
    "NOTES_RECONCILIATION",
    "CONTINUING_AND_DISCONTINUED_SEPARATE",
)


class EarningsPerShareEngine:
    """Deterministic IAS 33 EPS computation."""

    @staticmethod
    def weighted_avg_shares(
        opening_shares: Optional[Decimal],
        transactions: List[Tuple[str, int, Decimal]],
        period_days: int = 365,
    ) -> Dict[str, Any]:
        """
        Compute weighted average number of shares (WANS).
        transactions: list of (type, day_index, share_count) where:
            type = 'ISSUANCE' / 'BUYBACK' / 'BONUS_OR_SPLIT'
            day_index = day of period (0 = opening) when transaction occurred
            share_count = number of shares (positive)
        BONUS_OR_SPLIT: retrospective adjustment (treat as if at start of period).
        Rule 1: None when opening missing.
        Rule 6: negative shares rejected.
        """
        if opening_shares is None:
            return {"wans": None, "computed": False,
                    "reason": "missing_opening_shares"}
        if opening_shares < 0:
            return {"wans": None, "computed": False,
                    "reason": "negative_opening_shares"}
        if period_days <= 0:
            return {"wans": None, "computed": False,
                    "reason": "invalid_period_days"}
        # Apply bonus/splits retrospectively to opening
        adjusted_opening = opening_shares
        for tx_type, day, shares in transactions:
            if tx_type == "BONUS_OR_SPLIT":
                if shares < 0:
                    return {"wans": None, "computed": False,
                            "reason": "negative_bonus_shares"}
                adjusted_opening += shares
        # Weight remaining transactions by time
        weighted = adjusted_opening * Decimal(period_days)
        for tx_type, day, shares in transactions:
            if tx_type == "BONUS_OR_SPLIT":
                continue  # already adjusted into opening
            if tx_type not in ("ISSUANCE", "BUYBACK"):
                return {"wans": None, "computed": False,
                        "reason": f"unknown_transaction_type:{tx_type}"}
            if shares < 0:
                return {"wans": None, "computed": False,
                        "reason": "negative_shares"}
            if day < 0 or day > period_days:
                return {"wans": None, "computed": False,
                        "reason": "day_out_of_range"}
            days_outstanding = period_days - day
            if tx_type == "ISSUANCE":
                weighted += shares * Decimal(days_outstanding)
            else:  # BUYBACK
                weighted -= shares * Decimal(days_outstanding)
        wans = weighted / Decimal(period_days)
        return {
            "opening_shares": str(opening_shares),
            "adjusted_opening": str(adjusted_opening),
            "transaction_count": len(transactions),
            "wans": str(wans.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def basic_eps(
        net_income: Optional[Decimal],
        weighted_avg_shares: Optional[Decimal],
        preferred_dividends: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Basic EPS = (Net Income - Preferred Dividends) / WANS per IAS 33.10.
        Rule 1: None when net income or shares missing or zero shares.
        """
        if net_income is None or weighted_avg_shares is None:
            return {"basic_eps": None, "computed": False,
                    "reason": "missing_inputs"}
        if weighted_avg_shares <= 0:
            return {"basic_eps": None, "computed": False,
                    "reason": "non_positive_weighted_shares"}
        pref = preferred_dividends if preferred_dividends is not None else Decimal("0")
        earnings_to_ordinary = net_income - pref
        eps = earnings_to_ordinary / weighted_avg_shares
        return {
            "net_income": str(net_income),
            "preferred_dividends": str(pref),
            "earnings_to_ordinary": str(earnings_to_ordinary),
            "weighted_avg_shares": str(weighted_avg_shares),
            "basic_eps": str(eps.quantize(Decimal("0.0001"))),
            "computed": True,
        }

    @staticmethod
    def treasury_stock_method(
        options_outstanding: Optional[Decimal],
        exercise_price: Optional[Decimal],
        avg_market_price: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Treasury stock method per IAS 33.45.
        Net dilutive shares = options - (options × exercise / avg_market)
        Only dilutive when avg_market > exercise (otherwise anti-dilutive, return 0).
        Rule 1: None when inputs missing.
        Rule 6: negative prices rejected.
        """
        if (options_outstanding is None or exercise_price is None
                or avg_market_price is None):
            return {"net_dilutive_shares": None, "computed": False,
                    "reason": "missing_inputs"}
        if exercise_price < 0 or avg_market_price <= 0:
            return {"net_dilutive_shares": None, "computed": False,
                    "reason": "invalid_prices"}
        if options_outstanding < 0:
            return {"net_dilutive_shares": None, "computed": False,
                    "reason": "negative_options"}
        # Anti-dilutive if exercise >= market price (no economic incentive to exercise)
        if exercise_price >= avg_market_price:
            return {
                "options_outstanding": str(options_outstanding),
                "exercise_price": str(exercise_price),
                "avg_market_price": str(avg_market_price),
                "net_dilutive_shares": "0.00",
                "outcome": "ANTI_DILUTIVE",
                "rationale": "exercise_price_>=_avg_market",
                "computed": True,
            }
        # Treasury stock method: assumed buyback at avg market price
        proceeds = options_outstanding * exercise_price
        repurchased_shares = proceeds / avg_market_price
        net_dilutive = options_outstanding - repurchased_shares
        return {
            "options_outstanding": str(options_outstanding),
            "exercise_price": str(exercise_price),
            "avg_market_price": str(avg_market_price),
            "proceeds": str(proceeds.quantize(Decimal("0.01"))),
            "repurchased_shares": str(repurchased_shares.quantize(Decimal("0.01"))),
            "net_dilutive_shares": str(net_dilutive.quantize(Decimal("0.01"))),
            "outcome": "DILUTIVE",
            "computed": True,
        }

    @staticmethod
    def if_converted_method(
        net_income: Optional[Decimal],
        weighted_avg_shares: Optional[Decimal],
        convertible_dividends_or_interest_aftertax: Optional[Decimal],
        conversion_shares: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        If-converted method per IAS 33.49.
        Adjusted EPS = (NI + after-tax dividends/interest) / (WANS + conversion shares)
        Test if dilutive vs basic; only include if dilutive (lower EPS).
        Rule 1: None when inputs missing.
        """
        if (net_income is None or weighted_avg_shares is None
                or convertible_dividends_or_interest_aftertax is None
                or conversion_shares is None):
            return {"adjusted_eps": None, "computed": False,
                    "reason": "missing_inputs"}
        if weighted_avg_shares <= 0:
            return {"adjusted_eps": None, "computed": False,
                    "reason": "non_positive_wans"}
        if conversion_shares < 0:
            return {"adjusted_eps": None, "computed": False,
                    "reason": "negative_conversion_shares"}
        basic = net_income / weighted_avg_shares
        adjusted_numerator = net_income + convertible_dividends_or_interest_aftertax
        adjusted_denominator = weighted_avg_shares + conversion_shares
        if adjusted_denominator <= 0:
            return {"adjusted_eps": None, "computed": False,
                    "reason": "non_positive_adjusted_denom"}
        adjusted = adjusted_numerator / adjusted_denominator
        # Dilutive if adjusted_eps < basic_eps (assuming positive earnings)
        is_dilutive = adjusted < basic
        return {
            "basic_eps_unadjusted": str(basic.quantize(Decimal("0.0001"))),
            "adjusted_eps": str(adjusted.quantize(Decimal("0.0001"))),
            "outcome": "DILUTIVE" if is_dilutive else "ANTI_DILUTIVE",
            "include_in_diluted": is_dilutive,  # fail closed if anti-dilutive
            "computed": True,
        }

    @staticmethod
    def diluted_eps(
        net_income: Optional[Decimal],
        weighted_avg_shares: Optional[Decimal],
        dilutive_potential_shares: Optional[Decimal] = None,
        adjustments_to_numerator: Optional[Decimal] = None,
        preferred_dividends: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Diluted EPS = (NI - pref div + adjustments) / (WANS + dilutive POS).
        Only include POS if dilutive (would lower EPS).
        Rule 1: None when net income or WANS missing.
        """
        if net_income is None or weighted_avg_shares is None:
            return {"diluted_eps": None, "computed": False,
                    "reason": "missing_inputs"}
        if weighted_avg_shares <= 0:
            return {"diluted_eps": None, "computed": False,
                    "reason": "non_positive_wans"}
        pref = preferred_dividends if preferred_dividends is not None else Decimal("0")
        pos = dilutive_potential_shares if dilutive_potential_shares is not None else Decimal("0")
        adj = adjustments_to_numerator if adjustments_to_numerator is not None else Decimal("0")
        if pos < 0:
            return {"diluted_eps": None, "computed": False,
                    "reason": "negative_pos"}
        adjusted_numerator = net_income - pref + adj
        adjusted_denominator = weighted_avg_shares + pos
        diluted = adjusted_numerator / adjusted_denominator
        # Sanity check: diluted should be ≤ basic (otherwise anti-dilutive)
        basic_for_check = (net_income - pref) / weighted_avg_shares
        if diluted > basic_for_check:
            return {"diluted_eps": None, "computed": False,
                    "reason": "anti_dilutive_inputs_must_exclude"}
        return {
            "net_income": str(net_income),
            "preferred_dividends": str(pref),
            "adjustments_to_numerator": str(adj),
            "weighted_avg_shares": str(weighted_avg_shares),
            "dilutive_potential_shares": str(pos),
            "adjusted_numerator": str(adjusted_numerator),
            "adjusted_denominator": str(adjusted_denominator),
            "diluted_eps": str(diluted.quantize(Decimal("0.0001"))),
            "basic_eps_for_check": str(basic_for_check.quantize(Decimal("0.0001"))),
            "computed": True,
        }

    @staticmethod
    def dilutive_securities_classification(
        basic_eps_value: Optional[Decimal],
        eps_with_security: Optional[Decimal],
    ) -> Optional[str]:
        """
        Per IAS 33.41: classify as DILUTIVE or ANTI_DILUTIVE.
        DILUTIVE: eps_with_security < basic_eps (lowers EPS).
        Rule 1: None when inputs missing.
        """
        if basic_eps_value is None or eps_with_security is None:
            return None
        if eps_with_security < basic_eps_value:
            return "DILUTIVE"
        return "ANTI_DILUTIVE"


# ============================================================================
# Self-tests
# ============================================================================

def _test_eps_types_byte_for_byte():
    expected = ("BASIC", "DILUTED", "CONTINUING_OPERATIONS")
    for t in expected:
        assert t in EPS_TYPES


def _test_share_transactions_byte_for_byte():
    expected = ("ISSUANCE", "BUYBACK", "BONUS_OR_SPLIT")
    for t in expected:
        assert t in SHARE_TRANSACTION_TYPES


def _test_pos_types_byte_for_byte():
    expected = (
        "CONVERTIBLE_BONDS",
        "CONVERTIBLE_PREFERRED_SHARES",
        "SHARE_OPTIONS_WARRANTS",
        "CONTINGENTLY_ISSUABLE_SHARES",
    )
    for t in expected:
        assert t in POTENTIAL_ORDINARY_SHARE_TYPES
    assert len(POTENTIAL_ORDINARY_SHARE_TYPES) == 4


def _test_dilution_outcomes_byte_for_byte():
    expected = ("DILUTIVE", "ANTI_DILUTIVE")
    for o in expected:
        assert o in DILUTION_OUTCOMES


def _test_presentation_byte_for_byte():
    expected = (
        "FACE_OF_INCOME_STATEMENT",
        "NOTES_RECONCILIATION",
        "CONTINUING_AND_DISCONTINUED_SEPARATE",
    )
    for p in expected:
        assert p in EPS_PRESENTATION_REQUIREMENTS


def _test_wans_no_transactions():
    """1M opening, no txns → WANS = 1M."""
    r = EarningsPerShareEngine.weighted_avg_shares(
        Decimal("1000000"), [], period_days=365)
    assert r["wans"] == "1000000.00"


def _test_wans_issuance_mid_year():
    """1M opening + 100K issued at day 182 (half year) →
    1M × 365/365 + 100K × 183/365 = 1M + ~50.137K ≈ 1.050137M.
    """
    r = EarningsPerShareEngine.weighted_avg_shares(
        Decimal("1000000"),
        [("ISSUANCE", 182, Decimal("100000"))],
        period_days=365)
    wans = Decimal(r["wans"])
    assert wans > Decimal("1050000") and wans < Decimal("1051000")


def _test_wans_buyback():
    """1M opening - 100K buyback at day 182 → ~950K WANS."""
    r = EarningsPerShareEngine.weighted_avg_shares(
        Decimal("1000000"),
        [("BUYBACK", 182, Decimal("100000"))],
        period_days=365)
    wans = Decimal(r["wans"])
    assert wans < Decimal("1000000") and wans > Decimal("949000")


def _test_wans_bonus_retrospective():
    """1M opening + 200K bonus → 1.2M throughout (retrospective)."""
    r = EarningsPerShareEngine.weighted_avg_shares(
        Decimal("1000000"),
        [("BONUS_OR_SPLIT", 100, Decimal("200000"))],
        period_days=365)
    assert r["wans"] == "1200000.00"
    assert r["adjusted_opening"] == "1200000"


def _test_wans_missing_rule1():
    r = EarningsPerShareEngine.weighted_avg_shares(None, [], 365)
    assert r["wans"] is None


def _test_wans_negative_rule6():
    r = EarningsPerShareEngine.weighted_avg_shares(Decimal("-100"), [], 365)
    assert r["computed"] is False


def _test_basic_eps_basic():
    """1M earnings / 500K shares = $2.00 EPS."""
    r = EarningsPerShareEngine.basic_eps(Decimal("1000000"), Decimal("500000"))
    assert r["basic_eps"] == "2.0000"


def _test_basic_eps_with_preferred():
    """1M earnings - 100K preferred / 500K shares = $1.80 EPS."""
    r = EarningsPerShareEngine.basic_eps(
        Decimal("1000000"), Decimal("500000"), Decimal("100000"))
    assert r["basic_eps"] == "1.8000"


def _test_basic_eps_loss():
    """Loss position → negative EPS."""
    r = EarningsPerShareEngine.basic_eps(Decimal("-500000"), Decimal("500000"))
    assert r["basic_eps"] == "-1.0000"


def _test_basic_eps_missing_rule1():
    r = EarningsPerShareEngine.basic_eps(None, Decimal("500000"))
    assert r["basic_eps"] is None


def _test_basic_eps_zero_shares_rule1():
    r = EarningsPerShareEngine.basic_eps(Decimal("1000000"), Decimal("0"))
    assert r["basic_eps"] is None


def _test_treasury_stock_method_dilutive():
    """100K options @ $10 exercise, $20 avg market.
    Proceeds = 100K × 10 = 1M; buyback = 1M / 20 = 50K shares.
    Net dilutive = 100K - 50K = 50K shares.
    """
    r = EarningsPerShareEngine.treasury_stock_method(
        Decimal("100000"), Decimal("10"), Decimal("20"))
    assert r["net_dilutive_shares"] == "50000.00"
    assert r["outcome"] == "DILUTIVE"


def _test_treasury_stock_method_anti_dilutive():
    """Exercise $20 ≥ avg market $15 → anti-dilutive (no exercise)."""
    r = EarningsPerShareEngine.treasury_stock_method(
        Decimal("100000"), Decimal("20"), Decimal("15"))
    assert r["net_dilutive_shares"] == "0.00"
    assert r["outcome"] == "ANTI_DILUTIVE"


def _test_treasury_stock_method_at_money_anti_dilutive():
    """Exercise = avg market → still anti-dilutive (≥)."""
    r = EarningsPerShareEngine.treasury_stock_method(
        Decimal("100000"), Decimal("20"), Decimal("20"))
    assert r["outcome"] == "ANTI_DILUTIVE"


def _test_treasury_stock_method_missing_rule1():
    r = EarningsPerShareEngine.treasury_stock_method(
        None, Decimal("10"), Decimal("20"))
    assert r["net_dilutive_shares"] is None


def _test_if_converted_dilutive():
    """NI 1M, WANS 500K, after-tax interest 50K, conversion 100K shares.
    Basic = 1M/500K = 2.00; Adjusted = (1M+50K)/(500K+100K) = 1.05M/600K = 1.75
    1.75 < 2.00 → DILUTIVE.
    """
    r = EarningsPerShareEngine.if_converted_method(
        Decimal("1000000"), Decimal("500000"),
        Decimal("50000"), Decimal("100000"))
    assert r["outcome"] == "DILUTIVE"
    assert r["include_in_diluted"] is True


def _test_if_converted_anti_dilutive():
    """When conversion would raise EPS — anti-dilutive."""
    r = EarningsPerShareEngine.if_converted_method(
        Decimal("100000"), Decimal("100000"),
        Decimal("500000"), Decimal("10000"))
    # Basic = 1.00; adjusted = 600K/110K = ~5.45 > 1.00
    assert r["outcome"] == "ANTI_DILUTIVE"
    assert r["include_in_diluted"] is False


def _test_if_converted_missing_rule1():
    r = EarningsPerShareEngine.if_converted_method(
        None, Decimal("500000"), Decimal("50000"), Decimal("100000"))
    assert r["computed"] is False


def _test_diluted_eps_basic():
    """NI 1M, WANS 500K, dilutive 100K → 1M / 600K = 1.6667."""
    r = EarningsPerShareEngine.diluted_eps(
        Decimal("1000000"), Decimal("500000"),
        dilutive_potential_shares=Decimal("100000"))
    assert r["diluted_eps"] == "1.6667"


def _test_diluted_eps_with_adjustments():
    """NI 1M, WANS 500K, dilutive 100K, +50K interest add-back."""
    r = EarningsPerShareEngine.diluted_eps(
        Decimal("1000000"), Decimal("500000"),
        dilutive_potential_shares=Decimal("100000"),
        adjustments_to_numerator=Decimal("50000"))
    assert r["diluted_eps"] == "1.7500"


def _test_diluted_eps_with_preferred():
    """NI 1M, pref 100K, WANS 500K, dilutive 100K."""
    r = EarningsPerShareEngine.diluted_eps(
        Decimal("1000000"), Decimal("500000"),
        dilutive_potential_shares=Decimal("100000"),
        preferred_dividends=Decimal("100000"))
    # (1M - 100K) / 600K = 1.50
    assert r["diluted_eps"] == "1.5000"


def _test_diluted_eps_anti_dilutive_rejected_rule6():
    """Adjustments that make diluted > basic should be rejected."""
    r = EarningsPerShareEngine.diluted_eps(
        Decimal("1000000"), Decimal("500000"),
        dilutive_potential_shares=Decimal("100000"),
        adjustments_to_numerator=Decimal("1000000"))  # Massive add-back
    # Basic = 2.00; Adjusted = (1M + 1M)/600K = 3.33 > 2.00
    assert r["computed"] is False


def _test_diluted_eps_no_pos_equals_basic():
    """No POS → diluted = basic."""
    r = EarningsPerShareEngine.diluted_eps(
        Decimal("1000000"), Decimal("500000"))
    assert r["diluted_eps"] == "2.0000"


def _test_dilutive_classification_dilutive():
    assert EarningsPerShareEngine.dilutive_securities_classification(
        Decimal("2"), Decimal("1.50")) == "DILUTIVE"


def _test_dilutive_classification_anti_dilutive():
    assert EarningsPerShareEngine.dilutive_securities_classification(
        Decimal("2"), Decimal("2.50")) == "ANTI_DILUTIVE"


def _test_dilutive_classification_equal_anti_dilutive():
    """Equal → anti-dilutive (strict <)."""
    assert EarningsPerShareEngine.dilutive_securities_classification(
        Decimal("2"), Decimal("2")) == "ANTI_DILUTIVE"


def _test_dilutive_classification_missing_rule1():
    assert EarningsPerShareEngine.dilutive_securities_classification(
        None, Decimal("2")) is None


def self_test() -> bool:
    tests = [
        _test_eps_types_byte_for_byte,
        _test_share_transactions_byte_for_byte,
        _test_pos_types_byte_for_byte,
        _test_dilution_outcomes_byte_for_byte,
        _test_presentation_byte_for_byte,
        _test_wans_no_transactions,
        _test_wans_issuance_mid_year,
        _test_wans_buyback,
        _test_wans_bonus_retrospective,
        _test_wans_missing_rule1,
        _test_wans_negative_rule6,
        _test_basic_eps_basic,
        _test_basic_eps_with_preferred,
        _test_basic_eps_loss,
        _test_basic_eps_missing_rule1,
        _test_basic_eps_zero_shares_rule1,
        _test_treasury_stock_method_dilutive,
        _test_treasury_stock_method_anti_dilutive,
        _test_treasury_stock_method_at_money_anti_dilutive,
        _test_treasury_stock_method_missing_rule1,
        _test_if_converted_dilutive,
        _test_if_converted_anti_dilutive,
        _test_if_converted_missing_rule1,
        _test_diluted_eps_basic,
        _test_diluted_eps_with_adjustments,
        _test_diluted_eps_with_preferred,
        _test_diluted_eps_anti_dilutive_rejected_rule6,
        _test_diluted_eps_no_pos_equals_basic,
        _test_dilutive_classification_dilutive,
        _test_dilutive_classification_anti_dilutive,
        _test_dilutive_classification_equal_anti_dilutive,
        _test_dilutive_classification_missing_rule1,
    ]
    print("=" * 60)
    print("Earnings Per Share Engine — Self-Tests (#108 IAS 33)")
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

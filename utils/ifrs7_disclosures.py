"""
================================================================================
A2Z MIS 360 — Standard #110: IFRS 7 Financial Instruments Disclosures
================================================================================

Risk classification: Cat B (deterministic disclosure framework + risk metrics)

Implements IFRS 7's quantitative + qualitative disclosure requirements for:
    - Significance of financial instruments
    - Nature and extent of risks
    - Credit risk concentration
    - Liquidity risk maturity analysis
    - Market risk sensitivity

NOTE: separate from existing #85-88 reporting (board reporting / Pillar 3).
This module focuses on the IFRS 7 *financial instrument* disclosures specifically.

Provides:
    - validate_disclosure_class(...)        -- classify by IFRS 7 category
    - credit_risk_concentration(...)        -- single-counterparty / industry concentration
    - liquidity_maturity_buckets(...)       -- contractual maturity analysis
    - market_risk_sensitivity(...)          -- sensitivity to single risk variable
    - hedge_disclosure_pack(...)            -- disclosure requirements per hedge type
    - disclosure_completeness(...)          -- required-vs-provided gap

3 DISCLOSURE_CATEGORIES byte-for-byte (IFRS 7.7):
    SIGNIFICANCE_TO_FINANCIAL_POSITION
    NATURE_AND_EXTENT_OF_RISKS
    QUANTITATIVE_RISK_DATA

3 RISK_TYPES byte-for-byte (IFRS 7.32-42):
    CREDIT_RISK
    LIQUIDITY_RISK
    MARKET_RISK

5 MATURITY_BUCKETS byte-for-byte (IFRS 7.39):
    ON_DEMAND          -- payable on demand
    UP_TO_3_MONTHS     -- ≤ 3 months
    THREE_TO_12_MONTHS -- 3-12 months
    ONE_TO_5_YEARS     -- 1-5 years
    OVER_5_YEARS       -- > 5 years

3 MARKET_RISK_VARIABLES byte-for-byte (IFRS 7.40):
    INTEREST_RATE
    FOREIGN_EXCHANGE
    EQUITY_PRICE

3 HEDGE_TYPES byte-for-byte (IFRS 9.6.5.2):
    FAIR_VALUE_HEDGE
    CASH_FLOW_HEDGE
    NET_INVESTMENT_HEDGE

4 CREDIT_QUALITY_BANDS byte-for-byte:
    INVESTMENT_GRADE        -- AAA to BBB-
    NON_INVESTMENT_GRADE    -- BB+ to B-
    SUB_INVESTMENT_GRADE    -- below B-
    UNRATED                 -- no external rating

Concentration thresholds byte-for-byte:
    SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD = 10  -- single name > 10% = concentration
    INDUSTRY_CONCENTRATION_PCT_THRESHOLD             = 25  -- industry > 25% = concentration

Honesty rules applied:
    Rule 1: completeness=None when required_set empty
            concentration_pct=None when total exposure 0
    Rule 6: unknown disclosure_category / risk_type / maturity_bucket surfaced
            negative exposure rejected (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 3 DISCLOSURE CATEGORIES byte-for-byte (IFRS 7.7)
DISCLOSURE_CATEGORIES: Tuple[str, ...] = (
    "SIGNIFICANCE_TO_FINANCIAL_POSITION",
    "NATURE_AND_EXTENT_OF_RISKS",
    "QUANTITATIVE_RISK_DATA",
)

# 3 RISK TYPES byte-for-byte (IFRS 7.32-42)
RISK_TYPES: Tuple[str, ...] = (
    "CREDIT_RISK", "LIQUIDITY_RISK", "MARKET_RISK",
)

# 5 MATURITY BUCKETS byte-for-byte (IFRS 7.39)
MATURITY_BUCKETS: Tuple[str, ...] = (
    "ON_DEMAND", "UP_TO_3_MONTHS", "THREE_TO_12_MONTHS",
    "ONE_TO_5_YEARS", "OVER_5_YEARS",
)

# 3 MARKET RISK VARIABLES byte-for-byte (IFRS 7.40)
MARKET_RISK_VARIABLES: Tuple[str, ...] = (
    "INTEREST_RATE", "FOREIGN_EXCHANGE", "EQUITY_PRICE",
)

# 3 HEDGE TYPES byte-for-byte (IFRS 9.6.5.2 — disclosed under IFRS 7.22A-24F)
HEDGE_TYPES: Tuple[str, ...] = (
    "FAIR_VALUE_HEDGE", "CASH_FLOW_HEDGE", "NET_INVESTMENT_HEDGE",
)

# 4 CREDIT QUALITY BANDS byte-for-byte
CREDIT_QUALITY_BANDS: Tuple[str, ...] = (
    "INVESTMENT_GRADE", "NON_INVESTMENT_GRADE",
    "SUB_INVESTMENT_GRADE", "UNRATED",
)

# Concentration thresholds byte-for-byte
SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD = Decimal("10")
INDUSTRY_CONCENTRATION_PCT_THRESHOLD = Decimal("25")


class IFRS7DisclosureEngine:
    """Deterministic IFRS 7 financial instruments disclosure framework."""

    @staticmethod
    def validate_disclosure_class(category: str) -> Dict[str, Any]:
        """Rule 6: unknown category rejected."""
        if category not in DISCLOSURE_CATEGORIES:
            return {"valid": False,
                    "reason": f"unknown_category:{category}",
                    "valid_categories": list(DISCLOSURE_CATEGORIES)}
        return {"valid": True, "category": category}

    @staticmethod
    def credit_risk_concentration(
        exposure_amount: Optional[Decimal],
        total_exposure: Optional[Decimal],
        concentration_type: str = "SINGLE_COUNTERPARTY",
    ) -> Dict[str, Any]:
        """
        Compute concentration % vs threshold.
        SINGLE_COUNTERPARTY threshold = 10%; INDUSTRY threshold = 25%.
        Rule 1: None when total_exposure 0 or missing.
        Rule 6: negative exposure rejected.
        """
        if concentration_type not in ("SINGLE_COUNTERPARTY", "INDUSTRY"):
            return {"concentration_pct": None, "computed": False,
                    "reason": f"unknown_concentration_type:{concentration_type}"}
        if exposure_amount is None or total_exposure is None:
            return {"concentration_pct": None, "computed": False,
                    "reason": "missing_inputs"}
        if exposure_amount < 0 or total_exposure <= 0:
            return {"concentration_pct": None, "computed": False,
                    "reason": "invalid_exposure"}
        pct = (exposure_amount / total_exposure) * Decimal("100")
        if concentration_type == "SINGLE_COUNTERPARTY":
            threshold = SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD
        else:
            threshold = INDUSTRY_CONCENTRATION_PCT_THRESHOLD
        # Strict > so exactly threshold does NOT alert
        is_concentrated = pct > threshold
        return {
            "concentration_type": concentration_type,
            "exposure_amount": str(exposure_amount),
            "total_exposure": str(total_exposure),
            "concentration_pct": str(pct.quantize(Decimal("0.01"))),
            "threshold_pct": str(threshold),
            "is_concentrated": is_concentrated,
            "disclosure_required": is_concentrated,
            "computed": True,
        }

    @staticmethod
    def classify_maturity_bucket(
        days_to_maturity: Optional[int],
        on_demand: bool = False,
    ) -> Optional[str]:
        """
        Classify into 5 IFRS 7.39 maturity buckets.
        Rule 1: None when days missing.
        Rule 6: negative days rejected.
        """
        if on_demand:
            return "ON_DEMAND"
        if days_to_maturity is None:
            return None
        if days_to_maturity < 0:
            return None
        if days_to_maturity <= 90:  # 3 months
            return "UP_TO_3_MONTHS"
        if days_to_maturity <= 365:  # 1 year
            return "THREE_TO_12_MONTHS"
        if days_to_maturity <= 1825:  # 5 years
            return "ONE_TO_5_YEARS"
        return "OVER_5_YEARS"

    @staticmethod
    def liquidity_maturity_buckets(
        cash_flows: List[Tuple[int, Decimal]],
        on_demand_amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Aggregate contractual cash flows into 5 IFRS 7.39 buckets.
        cash_flows: list of (days_to_maturity, amount) tuples.
        Rule 1: None when cash_flows empty.
        """
        if not cash_flows and on_demand_amount is None:
            return {"buckets": None, "computed": False,
                    "reason": "empty_cash_flows"}
        buckets: Dict[str, Decimal] = {b: Decimal("0") for b in MATURITY_BUCKETS}
        if on_demand_amount is not None:
            buckets["ON_DEMAND"] = on_demand_amount
        for days, amount in cash_flows:
            if amount is None:
                return {"buckets": None, "computed": False,
                        "reason": "missing_amount"}
            bucket = IFRS7DisclosureEngine.classify_maturity_bucket(days)
            if bucket is None:
                return {"buckets": None, "computed": False,
                        "reason": f"invalid_days:{days}"}
            buckets[bucket] += amount
        total = sum(buckets.values(), start=Decimal("0"))
        return {
            "buckets": {b: str(v.quantize(Decimal("0.01")))
                        for b, v in buckets.items()},
            "total": str(total.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def market_risk_sensitivity(
        risk_variable: str,
        exposure: Optional[Decimal],
        sensitivity_change_pct: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Sensitivity per IFRS 7.40 — impact on profit/equity if risk variable
        changes by sensitivity_change_pct.
        Rule 6: unknown risk variable rejected.
        Rule 1: None when inputs missing.
        """
        if risk_variable not in MARKET_RISK_VARIABLES:
            return {"impact": None, "computed": False,
                    "reason": f"unknown_risk_variable:{risk_variable}"}
        if exposure is None or sensitivity_change_pct is None:
            return {"impact": None, "computed": False,
                    "reason": "missing_inputs"}
        impact = (exposure * sensitivity_change_pct) / Decimal("100")
        return {
            "risk_variable": risk_variable,
            "exposure": str(exposure),
            "sensitivity_change_pct": str(sensitivity_change_pct),
            "impact": str(impact.quantize(Decimal("0.01"))),
            "computed": True,
        }

    @staticmethod
    def hedge_disclosure_pack(hedge_type: str) -> Dict[str, Any]:
        """
        Required disclosures per hedge type per IFRS 7.21A-24F.
        Rule 6: unknown hedge_type rejected.
        """
        if hedge_type not in HEDGE_TYPES:
            return {"disclosures_required": None, "computed": False,
                    "reason": f"unknown_hedge_type:{hedge_type}",
                    "valid_types": list(HEDGE_TYPES)}
        common = ["risk_management_strategy", "hedged_item",
                   "hedging_instrument", "hedge_ratio"]
        if hedge_type == "FAIR_VALUE_HEDGE":
            specific = ["fair_value_changes_PnL", "hedge_ineffectiveness_PnL"]
        elif hedge_type == "CASH_FLOW_HEDGE":
            specific = ["fair_value_changes_OCI", "reclassification_to_PnL",
                        "forecast_transaction_no_longer_expected"]
        else:  # NET_INVESTMENT_HEDGE
            specific = ["fair_value_changes_OCI",
                        "reclassification_on_disposal_of_foreign_operation"]
        all_required = common + specific
        return {
            "hedge_type": hedge_type,
            "disclosures_required": all_required,
            "disclosure_count": len(all_required),
            "computed": True,
        }

    @staticmethod
    def disclosure_completeness(
        required_set: List[str],
        provided_set: List[str],
    ) -> Dict[str, Any]:
        """
        Compute disclosure gap.
        Rule 1: None when required_set empty.
        """
        if not required_set:
            return {"complete": None, "computed": False,
                    "reason": "empty_required_set"}
        missing = [item for item in required_set if item not in provided_set]
        complete = len(missing) == 0
        return {
            "required_count": len(required_set),
            "provided_count": len(provided_set),
            "missing": missing,
            "missing_count": len(missing),
            "complete": complete,
            "completeness_pct": str(
                ((len(required_set) - len(missing)) / len(required_set)
                 * 100)),
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_disclosure_categories_byte_for_byte():
    expected = ("SIGNIFICANCE_TO_FINANCIAL_POSITION",
                "NATURE_AND_EXTENT_OF_RISKS",
                "QUANTITATIVE_RISK_DATA")
    for c in expected:
        assert c in DISCLOSURE_CATEGORIES
    assert len(DISCLOSURE_CATEGORIES) == 3


def _test_risk_types_byte_for_byte():
    expected = ("CREDIT_RISK", "LIQUIDITY_RISK", "MARKET_RISK")
    for r in expected:
        assert r in RISK_TYPES


def _test_maturity_buckets_byte_for_byte():
    expected = ("ON_DEMAND", "UP_TO_3_MONTHS", "THREE_TO_12_MONTHS",
                "ONE_TO_5_YEARS", "OVER_5_YEARS")
    for b in expected:
        assert b in MATURITY_BUCKETS
    assert len(MATURITY_BUCKETS) == 5


def _test_market_variables_byte_for_byte():
    expected = ("INTEREST_RATE", "FOREIGN_EXCHANGE", "EQUITY_PRICE")
    for v in expected:
        assert v in MARKET_RISK_VARIABLES


def _test_hedge_types_byte_for_byte():
    expected = ("FAIR_VALUE_HEDGE", "CASH_FLOW_HEDGE", "NET_INVESTMENT_HEDGE")
    for h in expected:
        assert h in HEDGE_TYPES


def _test_credit_quality_bands_byte_for_byte():
    expected = ("INVESTMENT_GRADE", "NON_INVESTMENT_GRADE",
                "SUB_INVESTMENT_GRADE", "UNRATED")
    for b in expected:
        assert b in CREDIT_QUALITY_BANDS


def _test_concentration_thresholds_byte_for_byte():
    assert SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD == Decimal("10")
    assert INDUSTRY_CONCENTRATION_PCT_THRESHOLD == Decimal("25")


def _test_disclosure_class_valid():
    r = IFRS7DisclosureEngine.validate_disclosure_class("QUANTITATIVE_RISK_DATA")
    assert r["valid"] is True


def _test_disclosure_class_unknown_rule6():
    r = IFRS7DisclosureEngine.validate_disclosure_class("WEIRD")
    assert r["valid"] is False


def _test_concentration_single_above_threshold():
    """120K / 1M = 12% > 10% → concentrated."""
    r = IFRS7DisclosureEngine.credit_risk_concentration(
        Decimal("120000"), Decimal("1000000"), "SINGLE_COUNTERPARTY")
    assert r["concentration_pct"] == "12.00"
    assert r["is_concentrated"] is True


def _test_concentration_single_at_threshold():
    """Exactly 10% → NOT concentrated (strict >)."""
    r = IFRS7DisclosureEngine.credit_risk_concentration(
        Decimal("100000"), Decimal("1000000"), "SINGLE_COUNTERPARTY")
    assert r["concentration_pct"] == "10.00"
    assert r["is_concentrated"] is False


def _test_concentration_industry_threshold():
    """30% industry > 25% → concentrated."""
    r = IFRS7DisclosureEngine.credit_risk_concentration(
        Decimal("300000"), Decimal("1000000"), "INDUSTRY")
    assert r["is_concentrated"] is True


def _test_concentration_zero_total_rule1():
    r = IFRS7DisclosureEngine.credit_risk_concentration(
        Decimal("100000"), Decimal("0"))
    assert r["concentration_pct"] is None


def _test_maturity_on_demand():
    assert IFRS7DisclosureEngine.classify_maturity_bucket(0, on_demand=True) == "ON_DEMAND"


def _test_maturity_up_to_3_months():
    assert IFRS7DisclosureEngine.classify_maturity_bucket(60) == "UP_TO_3_MONTHS"


def _test_maturity_3_months_boundary():
    """Exactly 90 days → UP_TO_3_MONTHS (≤ inclusive)."""
    assert IFRS7DisclosureEngine.classify_maturity_bucket(90) == "UP_TO_3_MONTHS"


def _test_maturity_3_to_12_months():
    assert IFRS7DisclosureEngine.classify_maturity_bucket(180) == "THREE_TO_12_MONTHS"


def _test_maturity_1_year_boundary():
    """365 days → THREE_TO_12_MONTHS."""
    assert IFRS7DisclosureEngine.classify_maturity_bucket(365) == "THREE_TO_12_MONTHS"


def _test_maturity_1_to_5_years():
    assert IFRS7DisclosureEngine.classify_maturity_bucket(1000) == "ONE_TO_5_YEARS"


def _test_maturity_5_years_boundary():
    """1825 days = 5 years → ONE_TO_5_YEARS."""
    assert IFRS7DisclosureEngine.classify_maturity_bucket(1825) == "ONE_TO_5_YEARS"


def _test_maturity_over_5_years():
    assert IFRS7DisclosureEngine.classify_maturity_bucket(2000) == "OVER_5_YEARS"


def _test_maturity_negative_rule6():
    assert IFRS7DisclosureEngine.classify_maturity_bucket(-10) is None


def _test_liquidity_buckets_aggregate():
    r = IFRS7DisclosureEngine.liquidity_maturity_buckets(
        [(60, Decimal("100000")), (200, Decimal("200000")),
         (1000, Decimal("500000")), (2500, Decimal("100000"))],
        on_demand_amount=Decimal("50000"))
    assert r["computed"] is True
    bks = r["buckets"]
    assert bks["ON_DEMAND"] == "50000.00"
    assert bks["UP_TO_3_MONTHS"] == "100000.00"
    assert bks["THREE_TO_12_MONTHS"] == "200000.00"
    assert bks["ONE_TO_5_YEARS"] == "500000.00"
    assert bks["OVER_5_YEARS"] == "100000.00"


def _test_market_sensitivity_interest_rate():
    """100M exposure × 1% rate change = 1M impact."""
    r = IFRS7DisclosureEngine.market_risk_sensitivity(
        "INTEREST_RATE", Decimal("100000000"), Decimal("1"))
    assert r["impact"] == "1000000.00"


def _test_market_sensitivity_fx():
    r = IFRS7DisclosureEngine.market_risk_sensitivity(
        "FOREIGN_EXCHANGE", Decimal("50000000"), Decimal("5"))
    assert r["impact"] == "2500000.00"


def _test_market_sensitivity_unknown_rule6():
    r = IFRS7DisclosureEngine.market_risk_sensitivity(
        "WEIRD", Decimal("100000000"), Decimal("1"))
    assert r["computed"] is False


def _test_hedge_pack_fair_value():
    r = IFRS7DisclosureEngine.hedge_disclosure_pack("FAIR_VALUE_HEDGE")
    assert r["disclosure_count"] == 6  # 4 common + 2 specific


def _test_hedge_pack_cash_flow():
    """CFH has 3 specific disclosures (more onerous than FV hedge)."""
    r = IFRS7DisclosureEngine.hedge_disclosure_pack("CASH_FLOW_HEDGE")
    assert r["disclosure_count"] == 7  # 4 + 3


def _test_hedge_pack_net_investment():
    r = IFRS7DisclosureEngine.hedge_disclosure_pack("NET_INVESTMENT_HEDGE")
    assert r["disclosure_count"] == 6  # 4 + 2


def _test_hedge_pack_unknown_rule6():
    r = IFRS7DisclosureEngine.hedge_disclosure_pack("WEIRD")
    assert r["computed"] is False


def _test_completeness_complete():
    r = IFRS7DisclosureEngine.disclosure_completeness(
        ["a", "b", "c"], ["a", "b", "c", "d"])
    assert r["complete"] is True
    assert r["missing_count"] == 0


def _test_completeness_gap():
    r = IFRS7DisclosureEngine.disclosure_completeness(
        ["a", "b", "c", "d"], ["a", "b"])
    assert r["complete"] is False
    assert r["missing_count"] == 2
    assert "c" in r["missing"]
    assert "d" in r["missing"]


def _test_completeness_empty_required_rule1():
    r = IFRS7DisclosureEngine.disclosure_completeness([], ["a"])
    assert r["complete"] is None


def self_test() -> bool:
    tests = [
        _test_disclosure_categories_byte_for_byte,
        _test_risk_types_byte_for_byte,
        _test_maturity_buckets_byte_for_byte,
        _test_market_variables_byte_for_byte,
        _test_hedge_types_byte_for_byte,
        _test_credit_quality_bands_byte_for_byte,
        _test_concentration_thresholds_byte_for_byte,
        _test_disclosure_class_valid,
        _test_disclosure_class_unknown_rule6,
        _test_concentration_single_above_threshold,
        _test_concentration_single_at_threshold,
        _test_concentration_industry_threshold,
        _test_concentration_zero_total_rule1,
        _test_maturity_on_demand,
        _test_maturity_up_to_3_months,
        _test_maturity_3_months_boundary,
        _test_maturity_3_to_12_months,
        _test_maturity_1_year_boundary,
        _test_maturity_1_to_5_years,
        _test_maturity_5_years_boundary,
        _test_maturity_over_5_years,
        _test_maturity_negative_rule6,
        _test_liquidity_buckets_aggregate,
        _test_market_sensitivity_interest_rate,
        _test_market_sensitivity_fx,
        _test_market_sensitivity_unknown_rule6,
        _test_hedge_pack_fair_value,
        _test_hedge_pack_cash_flow,
        _test_hedge_pack_net_investment,
        _test_hedge_pack_unknown_rule6,
        _test_completeness_complete,
        _test_completeness_gap,
        _test_completeness_empty_required_rule1,
    ]
    print("=" * 60)
    print("IFRS 7 Disclosure Engine — Self-Tests (#110)")
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

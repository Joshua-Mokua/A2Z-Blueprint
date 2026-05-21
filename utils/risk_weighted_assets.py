"""
================================================================================
A2Z MIS 360 — Standard #78: Risk-Weighted Assets (RWA) Engine
================================================================================

Risk classification: Cat B (deterministic Basel III Standardised Approach)

Computes RWA per Basel III Standardised Approach + CBK PG/02:
    - credit_rwa(exposures)            -- credit risk RWA
    - market_rwa(...)                  -- market risk (interest rate + FX + equity)
    - operational_rwa(...)             -- BIA / Standardised approach
    - total_rwa(...)                   -- credit + market + operational

Credit risk weights (Basel III Standardised Approach) byte-for-byte:
    SOVEREIGN_AAA_TO_AA-     : 0%
    SOVEREIGN_A+_TO_A-       : 20%
    SOVEREIGN_BBB+_TO_BBB-   : 50%
    SOVEREIGN_BB+_TO_B-      : 100%
    SOVEREIGN_BELOW_B-       : 150%
    BANK_AAA_TO_AA-          : 20%
    BANK_A+_TO_A-            : 50%
    BANK_BBB+_TO_BBB-        : 50%
    BANK_BELOW_BBB-          : 100%
    CORPORATE_UNRATED        : 100%
    CORPORATE_AAA_TO_AA-     : 20%
    CORPORATE_BBB+_TO_BB-    : 100%
    RETAIL_QUALIFYING        : 75%
    MORTGAGE_RESIDENTIAL     : 35%
    MORTGAGE_COMMERCIAL      : 100%
    PAST_DUE_LT_20PCT_PROVS  : 150%
    PAST_DUE_GTE_20PCT_PROVS : 100%
    EQUITY_LISTED            : 250%
    EQUITY_PRIVATE           : 400%

Operational risk methods:
    BIA (Basic Indicator Approach): 15% × 3-year average of positive gross income
    SA (Standardised Approach):     percentage by business line × 3yr avg GI

Market risk: 8% capital charge × 12.5 = RWA equivalent.

Honesty rules applied:
    Rule 1: weighted_rwa = None when net_position cannot be computed
    Rule 6: exposures with missing/unknown asset class excluded with count surfaced

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# Credit risk weights (Basel III Standardised Approach) byte-for-byte
CREDIT_RISK_WEIGHTS_PCT: Dict[str, Decimal] = {
    # Sovereigns
    "SOVEREIGN_AAA_TO_AA-": Decimal("0"),
    "SOVEREIGN_A+_TO_A-": Decimal("20"),
    "SOVEREIGN_BBB+_TO_BBB-": Decimal("50"),
    "SOVEREIGN_BB+_TO_B-": Decimal("100"),
    "SOVEREIGN_BELOW_B-": Decimal("150"),
    "SOVEREIGN_UNRATED": Decimal("100"),

    # Banks (option 2: based on counterparty rating)
    "BANK_AAA_TO_AA-": Decimal("20"),
    "BANK_A+_TO_A-": Decimal("50"),
    "BANK_BBB+_TO_BBB-": Decimal("50"),
    "BANK_BB+_TO_B-": Decimal("100"),
    "BANK_BELOW_B-": Decimal("150"),
    "BANK_UNRATED": Decimal("50"),

    # Corporates
    "CORPORATE_AAA_TO_AA-": Decimal("20"),
    "CORPORATE_A+_TO_A-": Decimal("50"),
    "CORPORATE_BBB+_TO_BB-": Decimal("100"),
    "CORPORATE_BELOW_BB-": Decimal("150"),
    "CORPORATE_UNRATED": Decimal("100"),

    # Retail and mortgage
    "RETAIL_QUALIFYING": Decimal("75"),
    "RETAIL_NON_QUALIFYING": Decimal("100"),
    "MORTGAGE_RESIDENTIAL": Decimal("35"),
    "MORTGAGE_COMMERCIAL": Decimal("100"),

    # Past due
    "PAST_DUE_LT_20PCT_PROVS": Decimal("150"),
    "PAST_DUE_GTE_20PCT_PROVS": Decimal("100"),

    # Equity
    "EQUITY_LISTED": Decimal("250"),
    "EQUITY_PRIVATE": Decimal("400"),

    # Off-balance-sheet items handled via CCF then risk weight
    "OTHER_ASSETS": Decimal("100"),
}

VALID_ASSET_CLASSES: Tuple[str, ...] = tuple(CREDIT_RISK_WEIGHTS_PCT.keys())

# Credit Conversion Factors (off-balance-sheet)
CCF_PCT: Dict[str, Decimal] = {
    "DIRECT_CREDIT_SUBSTITUTE": Decimal("100"),
    "TRANSACTION_RELATED_CONTINGENT": Decimal("50"),
    "TRADE_RELATED_CONTINGENT": Decimal("20"),
    "COMMITMENTS_GTE_1Y": Decimal("50"),
    "COMMITMENTS_LT_1Y_REVOCABLE": Decimal("0"),
    "COMMITMENTS_LT_1Y_IRREVOCABLE": Decimal("20"),
}

# Operational risk methods
OPERATIONAL_RISK_METHODS: Tuple[str, ...] = (
    "BIA",  # Basic Indicator Approach
    "SA",   # Standardised Approach
    "AMA",  # Advanced Measurement Approach (not implemented)
)
BIA_ALPHA_PCT = Decimal("15")  # Basel III BIA constant
RWA_CONVERSION_FACTOR = Decimal("12.5")  # 1 / 8% capital ratio

# Standardised Approach — beta factors per business line (Basel)
SA_BETA_PCT: Dict[str, Decimal] = {
    "CORPORATE_FINANCE": Decimal("18"),
    "TRADING_AND_SALES": Decimal("18"),
    "RETAIL_BANKING": Decimal("12"),
    "COMMERCIAL_BANKING": Decimal("15"),
    "PAYMENT_AND_SETTLEMENT": Decimal("18"),
    "AGENCY_SERVICES": Decimal("15"),
    "ASSET_MANAGEMENT": Decimal("12"),
    "RETAIL_BROKERAGE": Decimal("12"),
}


@dataclass
class CreditExposure:
    exposure_id: str
    asset_class: str
    exposure_kes: Optional[Decimal] = None  # on-balance-sheet
    off_balance_amount_kes: Optional[Decimal] = None
    off_balance_ccf_category: Optional[str] = None
    crm_eligible_collateral_kes: Optional[Decimal] = None  # credit risk mitigation


@dataclass
class GrossIncomeYear:
    year: int
    gross_income_kes: Optional[Decimal] = None  # for BIA
    business_line_income_kes: Optional[Dict[str, Decimal]] = None  # for SA


class RwaEngine:
    """Deterministic Basel III Standardised Approach RWA computation."""

    @staticmethod
    def credit_rwa(exposures: List[CreditExposure]) -> Dict[str, Any]:
        """
        Credit risk RWA = sum(EAD × risk_weight).
        EAD = on_balance + off_balance × CCF - eligible_collateral.
        Rule 6: exposures with unknown asset_class excluded.
        """
        total_rwa = Decimal("0")
        excluded = []
        per_class: Dict[str, Decimal] = {}
        details = []
        for e in exposures:
            if e.asset_class not in CREDIT_RISK_WEIGHTS_PCT:
                excluded.append(e.exposure_id)
                continue
            on_bal = e.exposure_kes or Decimal("0")
            # Off-balance with CCF
            off_bal_ead = Decimal("0")
            if (e.off_balance_amount_kes is not None
                    and e.off_balance_ccf_category is not None):
                ccf = CCF_PCT.get(e.off_balance_ccf_category)
                if ccf is None:
                    excluded.append(e.exposure_id)
                    continue
                off_bal_ead = e.off_balance_amount_kes * ccf / Decimal("100")
            # CRM (collateral subtraction — simplified standardised approach)
            collateral = e.crm_eligible_collateral_kes or Decimal("0")
            ead = max(Decimal("0"), on_bal + off_bal_ead - collateral)
            risk_weight = CREDIT_RISK_WEIGHTS_PCT[e.asset_class]
            rwa = ead * risk_weight / Decimal("100")
            total_rwa += rwa
            per_class[e.asset_class] = per_class.get(e.asset_class, Decimal("0")) + rwa
            details.append({
                "exposure_id": e.exposure_id,
                "asset_class": e.asset_class,
                "ead_kes": str(ead.quantize(Decimal("0.01"))),
                "risk_weight_pct": str(risk_weight),
                "rwa_kes": str(rwa.quantize(Decimal("0.01"))),
            })
        return {
            "total_credit_rwa_kes": str(total_rwa.quantize(Decimal("0.01"))),
            "exposure_count": len(details),
            "excluded_count": len(excluded),
            "excluded_sample": excluded[:10],
            "per_asset_class": {k: str(v.quantize(Decimal("0.01"))) for k, v in per_class.items()},
            "details": details,
        }

    @staticmethod
    def operational_rwa_bia(
        gross_income_history: List[GrossIncomeYear],
    ) -> Dict[str, Any]:
        """
        Basic Indicator Approach (BIA):
        Operational capital = average of positive gross income × 15%.
        Operational RWA = capital × 12.5.
        """
        positive_years = []
        excluded = []
        for gi in gross_income_history:
            if gi.gross_income_kes is None:
                excluded.append(gi.year)
                continue
            if gi.gross_income_kes > 0:
                positive_years.append(gi.gross_income_kes)
            # Negative or zero years excluded from average per Basel BIA

        if not positive_years:
            return {
                "method": "BIA",
                "operational_capital_kes": "0",
                "operational_rwa_kes": "0",
                "positive_years_count": 0,
                "excluded_year_count": len(excluded),
                "reason": "no_positive_gross_income",
            }

        avg_gi = sum(positive_years) / Decimal(len(positive_years))
        op_capital = avg_gi * BIA_ALPHA_PCT / Decimal("100")
        op_rwa = op_capital * RWA_CONVERSION_FACTOR
        return {
            "method": "BIA",
            "average_gross_income_kes": str(avg_gi.quantize(Decimal("0.01"))),
            "alpha_pct": str(BIA_ALPHA_PCT),
            "operational_capital_kes": str(op_capital.quantize(Decimal("0.01"))),
            "rwa_conversion_factor": str(RWA_CONVERSION_FACTOR),
            "operational_rwa_kes": str(op_rwa.quantize(Decimal("0.01"))),
            "positive_years_count": len(positive_years),
            "excluded_year_count": len(excluded),
        }

    @staticmethod
    def operational_rwa_sa(
        gross_income_history: List[GrossIncomeYear],
    ) -> Dict[str, Any]:
        """
        Standardised Approach (SA): sum across business lines per beta factor.
        Capital(year) = sum_bl(beta_bl × GI_bl); use max(0, sum) per year;
        average over 3 years.
        """
        yearly_capital: List[Decimal] = []
        excluded_years = []
        for gi in gross_income_history:
            if gi.business_line_income_kes is None:
                excluded_years.append(gi.year)
                continue
            year_cap = Decimal("0")
            for bl, amt in gi.business_line_income_kes.items():
                beta = SA_BETA_PCT.get(bl)
                if beta is None:
                    continue
                year_cap += amt * beta / Decimal("100")
            # Floor at 0
            yearly_capital.append(max(Decimal("0"), year_cap))

        if not yearly_capital:
            return {
                "method": "SA",
                "operational_capital_kes": "0",
                "operational_rwa_kes": "0",
                "reason": "no_business_line_data",
                "excluded_year_count": len(excluded_years),
            }
        avg_capital = sum(yearly_capital) / Decimal(len(yearly_capital))
        op_rwa = avg_capital * RWA_CONVERSION_FACTOR
        return {
            "method": "SA",
            "yearly_capital_kes": [str(c.quantize(Decimal("0.01"))) for c in yearly_capital],
            "average_capital_kes": str(avg_capital.quantize(Decimal("0.01"))),
            "operational_rwa_kes": str(op_rwa.quantize(Decimal("0.01"))),
            "excluded_year_count": len(excluded_years),
        }

    @staticmethod
    def market_rwa(market_capital_charge_kes: Optional[Decimal]) -> Dict[str, Any]:
        """
        Market risk RWA = capital charge × 12.5.
        Capital charge is the sum of interest rate risk + FX + equity risk
        components, computed externally.
        Rule 1: None when capital charge missing.
        """
        if market_capital_charge_kes is None:
            return {
                "market_rwa_kes": None,
                "reason": "market_capital_charge_unavailable",
            }
        rwa = market_capital_charge_kes * RWA_CONVERSION_FACTOR
        return {
            "market_capital_charge_kes": str(market_capital_charge_kes.quantize(Decimal("0.01"))),
            "rwa_conversion_factor": str(RWA_CONVERSION_FACTOR),
            "market_rwa_kes": str(rwa.quantize(Decimal("0.01"))),
        }

    @classmethod
    def total_rwa(
        cls,
        credit_exposures: List[CreditExposure],
        gross_income_history: List[GrossIncomeYear],
        market_capital_charge_kes: Optional[Decimal] = None,
        operational_method: str = "BIA",
    ) -> Dict[str, Any]:
        """Aggregate Credit + Market + Operational RWA."""
        credit = cls.credit_rwa(credit_exposures)
        if operational_method == "SA":
            op = cls.operational_rwa_sa(gross_income_history)
        else:
            op = cls.operational_rwa_bia(gross_income_history)
        market = cls.market_rwa(market_capital_charge_kes)

        credit_amt = Decimal(credit["total_credit_rwa_kes"])
        op_amt = Decimal(op.get("operational_rwa_kes", "0") or "0")
        market_amt = (Decimal(market["market_rwa_kes"])
                      if market.get("market_rwa_kes") is not None
                      else Decimal("0"))
        total = credit_amt + op_amt + market_amt
        return {
            "credit_rwa_kes": str(credit_amt.quantize(Decimal("0.01"))),
            "operational_rwa_kes": str(op_amt.quantize(Decimal("0.01"))),
            "market_rwa_kes": str(market_amt.quantize(Decimal("0.01"))) if market.get("market_rwa_kes") is not None else None,
            "total_rwa_kes": str(total.quantize(Decimal("0.01"))),
            "operational_method": operational_method,
            "credit_breakdown": credit,
            "operational_breakdown": op,
            "market_breakdown": market,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _exp(**kw):
    defaults = dict(
        exposure_id="E1", asset_class="CORPORATE_UNRATED",
        exposure_kes=Decimal("100000000"),
    )
    defaults.update(kw)
    return CreditExposure(**defaults)


def _test_sovereign_aaa_zero_weight():
    e = [_exp(asset_class="SOVEREIGN_AAA_TO_AA-")]
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "0.00"


def _test_corporate_unrated_100pct():
    e = [_exp(asset_class="CORPORATE_UNRATED",
              exposure_kes=Decimal("100000000"))]
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "100000000.00"


def _test_mortgage_residential_35pct():
    e = [_exp(asset_class="MORTGAGE_RESIDENTIAL",
              exposure_kes=Decimal("100000000"))]
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "35000000.00"


def _test_retail_qualifying_75pct():
    e = [_exp(asset_class="RETAIL_QUALIFYING",
              exposure_kes=Decimal("100000000"))]
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "75000000.00"


def _test_past_due_150pct():
    e = [_exp(asset_class="PAST_DUE_LT_20PCT_PROVS",
              exposure_kes=Decimal("100000000"))]
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "150000000.00"


def _test_equity_listed_250pct():
    e = [_exp(asset_class="EQUITY_LISTED",
              exposure_kes=Decimal("100000000"))]
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "250000000.00"


def _test_off_balance_with_ccf():
    e = [_exp(exposure_kes=Decimal("0"),
              off_balance_amount_kes=Decimal("100000000"),
              off_balance_ccf_category="COMMITMENTS_GTE_1Y")]
    # 100M × 50% CCF = 50M EAD; × 100% RW = 50M RWA
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "50000000.00"


def _test_collateral_reduces_ead():
    e = [_exp(asset_class="CORPORATE_UNRATED",
              exposure_kes=Decimal("100000000"),
              crm_eligible_collateral_kes=Decimal("30000000"))]
    # EAD = 100M - 30M = 70M; × 100% = 70M RWA
    r = RwaEngine.credit_rwa(e)
    assert r["total_credit_rwa_kes"] == "70000000.00"


def _test_unknown_asset_class_rule6():
    e = [_exp(asset_class="WEIRD")]
    r = RwaEngine.credit_rwa(e)
    assert r["excluded_count"] == 1


def _test_bia_15pct_alpha():
    """3 years, all positive 1B → avg 1B × 15% = 150M cap × 12.5 = 1.875B RWA."""
    history = [
        GrossIncomeYear(year=2023, gross_income_kes=Decimal("1000000000")),
        GrossIncomeYear(year=2024, gross_income_kes=Decimal("1000000000")),
        GrossIncomeYear(year=2025, gross_income_kes=Decimal("1000000000")),
    ]
    r = RwaEngine.operational_rwa_bia(history)
    assert Decimal(r["operational_rwa_kes"]) == Decimal("1875000000.00")


def _test_bia_negative_year_excluded():
    """Negative GI year excluded from average."""
    history = [
        GrossIncomeYear(year=2023, gross_income_kes=Decimal("1000000000")),
        GrossIncomeYear(year=2024, gross_income_kes=Decimal("-500000000")),  # excluded
        GrossIncomeYear(year=2025, gross_income_kes=Decimal("1000000000")),
    ]
    r = RwaEngine.operational_rwa_bia(history)
    # Only 2 positive years; avg = 1B; same RWA as first test
    assert Decimal(r["operational_rwa_kes"]) == Decimal("1875000000.00")


def _test_bia_no_positive_years():
    history = [GrossIncomeYear(year=2023, gross_income_kes=Decimal("-100"))]
    r = RwaEngine.operational_rwa_bia(history)
    assert r["operational_rwa_kes"] == "0"


def _test_market_rwa_basic():
    r = RwaEngine.market_rwa(Decimal("100000000"))
    # 100M × 12.5 = 1.25B
    assert r["market_rwa_kes"] == "1250000000.00"


def _test_market_rwa_none_rule1():
    r = RwaEngine.market_rwa(None)
    assert r["market_rwa_kes"] is None


def _test_total_rwa_aggregation():
    exposures = [_exp(asset_class="CORPORATE_UNRATED",
                     exposure_kes=Decimal("100000000"))]
    history = [GrossIncomeYear(year=y, gross_income_kes=Decimal("1000000000"))
               for y in range(2023, 2026)]
    r = RwaEngine.total_rwa(exposures, history,
                            market_capital_charge_kes=Decimal("100000000"))
    # Credit: 100M; Op: 1.875B; Market: 1.25B; Total: 3.225B
    assert Decimal(r["total_rwa_kes"]) == Decimal("3225000000.00")


def _test_credit_weights_byte_for_byte():
    assert CREDIT_RISK_WEIGHTS_PCT["SOVEREIGN_AAA_TO_AA-"] == Decimal("0")
    assert CREDIT_RISK_WEIGHTS_PCT["CORPORATE_UNRATED"] == Decimal("100")
    assert CREDIT_RISK_WEIGHTS_PCT["MORTGAGE_RESIDENTIAL"] == Decimal("35")
    assert CREDIT_RISK_WEIGHTS_PCT["RETAIL_QUALIFYING"] == Decimal("75")
    assert CREDIT_RISK_WEIGHTS_PCT["PAST_DUE_LT_20PCT_PROVS"] == Decimal("150")
    assert CREDIT_RISK_WEIGHTS_PCT["EQUITY_LISTED"] == Decimal("250")
    assert CREDIT_RISK_WEIGHTS_PCT["EQUITY_PRIVATE"] == Decimal("400")


def _test_ccf_byte_for_byte():
    assert CCF_PCT["DIRECT_CREDIT_SUBSTITUTE"] == Decimal("100")
    assert CCF_PCT["TRADE_RELATED_CONTINGENT"] == Decimal("20")
    assert CCF_PCT["COMMITMENTS_GTE_1Y"] == Decimal("50")
    assert CCF_PCT["COMMITMENTS_LT_1Y_REVOCABLE"] == Decimal("0")


def _test_bia_alpha_byte_for_byte():
    assert BIA_ALPHA_PCT == Decimal("15")
    assert RWA_CONVERSION_FACTOR == Decimal("12.5")


def _test_sa_betas_byte_for_byte():
    assert SA_BETA_PCT["CORPORATE_FINANCE"] == Decimal("18")
    assert SA_BETA_PCT["RETAIL_BANKING"] == Decimal("12")
    assert SA_BETA_PCT["COMMERCIAL_BANKING"] == Decimal("15")


def self_test() -> bool:
    tests = [
        _test_sovereign_aaa_zero_weight,
        _test_corporate_unrated_100pct,
        _test_mortgage_residential_35pct,
        _test_retail_qualifying_75pct,
        _test_past_due_150pct,
        _test_equity_listed_250pct,
        _test_off_balance_with_ccf,
        _test_collateral_reduces_ead,
        _test_unknown_asset_class_rule6,
        _test_bia_15pct_alpha,
        _test_bia_negative_year_excluded,
        _test_bia_no_positive_years,
        _test_market_rwa_basic,
        _test_market_rwa_none_rule1,
        _test_total_rwa_aggregation,
        _test_credit_weights_byte_for_byte,
        _test_ccf_byte_for_byte,
        _test_bia_alpha_byte_for_byte,
        _test_sa_betas_byte_for_byte,
    ]
    print("=" * 60)
    print("RWA Engine — Self-Tests (#78)")
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
